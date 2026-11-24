# Mã hóa, versioning, retention và vòng đời đối tượng

## 1. Bảo vệ dữ liệu trong toàn bộ vòng đời

Một ứng dụng Spring Boot lưu file trong Google Cloud Storage (GCS) cần trả lời nhiều câu hỏi hơn việc upload và download thành công. Dữ liệu phải được mã hóa như thế nào? Ai có quyền quản lý khóa? Nếu người dùng ghi đè hoặc xóa nhầm object thì có thể khôi phục không? Tài liệu phải được giữ tối thiểu bao lâu? Khi hết thời hạn nghiệp vụ, object có thể tự chuyển sang storage class rẻ hơn hoặc được xóa như thế nào?

Cloud Storage cung cấp nhiều cơ chế để giải quyết các yêu cầu này:

- **Encryption:** mã hóa dữ liệu khi lưu trữ, dùng khóa do Google quản lý, khóa Cloud KMS do khách hàng quản lý, khóa do khách hàng cung cấp hoặc mã hóa ở phía ứng dụng.
- **Object Versioning:** giữ các phiên bản object cũ khi object live bị thay thế hoặc xóa.
- **Soft Delete:** giữ object đã xóa trong một khoảng thời gian để có thể khôi phục.
- **Retention policy và holds:** ngăn object bị xóa hoặc thay thế trước thời điểm cho phép.
- **Object Lifecycle Management:** tự động chuyển storage class hoặc xóa object khi thỏa các điều kiện cấu hình.

Bài học thuộc chương **Google Cloud Storage** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này tập trung vào bảo vệ dữ liệu, quản lý phiên bản, thời hạn lưu giữ và tự động hóa vòng đời object trong Cloud Storage.

Sau bài học, bạn có thể:

- Phân biệt Google-managed encryption, CMEK, CSEK và client-side encryption.
- Cấu hình Cloud KMS key cho bucket hoặc từng object.
- Hiểu vai trò service agent, quyền Cloud KMS và rủi ro khi disable/destroy key version.
- Giải thích Object Versioning, noncurrent version và generation.
- Khôi phục soft-deleted object và hiểu giới hạn của quá trình restore.
- Thiết kế bucket retention policy, Bucket Lock, Object Retention Lock và object holds.
- Viết lifecycle rule theo age, prefix, storage class, noncurrent time và số phiên bản mới hơn.
- Cấu hình các tính năng bằng Java Storage client và gcloud CLI.
- Tính đến IAM, chi phí, audit log và kiểm thử khôi phục trong ứng dụng Spring Boot.

> **Phạm vi phiên bản:** Ví dụ dùng Google Cloud Storage Java client (artifact com.google.cloud:google-cloud-storage) và gcloud CLI. Hãy quản lý dependency bằng BOM phù hợp với baseline Java/Spring của dự án, đồng thời kiểm tra Javadoc của version thực tế. Các bucket, project, object và key trong ví dụ là dữ liệu minh họa. Những thao tác khóa retention policy hoặc phá hủy Cloud KMS key version có thể không thể đảo ngược; chỉ thực hiện sau khi đã kiểm tra quy trình và tài nguyên liên quan.

## 2. Bức tranh tổng thể

Mã hóa, versioning, soft delete, retention và lifecycle không phải các tên gọi khác nhau của cùng một tính năng. Chúng bảo vệ những rủi ro khác nhau.

~~~mermaid
flowchart TD
    APP["Spring Boot application"] --> WRITE["Create / update object"]
    WRITE --> ENC["Encryption at rest"]
    ENC --> LIVE["Live object generation"]
    LIVE --> VERSION["Object Versioning"]
    LIVE --> RETENTION["Retention policy / holds"]
    LIVE --> LIFECYCLE["Lifecycle Management"]
    LIVE --> DELETE["Delete request"]
    DELETE --> SOFT["Soft Delete"]
    VERSION --> NONCURRENT["Noncurrent generations"]
    SOFT --> RESTORE["Restore as a new live generation"]
    NONCURRENT --> CLEAN["Lifecycle cleanup"]
    SOFT --> CLEAN
    KMS["Cloud KMS / key governance"] -. "CMEK key access" .-> ENC
    AUDIT["IAM + Audit Logs + monitoring"] -. "Governance" .-> WRITE
    AUDIT -. "Governance" .-> DELETE
~~~

| Cơ chế | Câu hỏi được giải quyết | Điều cơ chế không tự giải quyết |
| --- | --- | --- |
| Encryption | Ai có thể giải mã dữ liệu đã lưu? | Không ngăn người có quyền đọc tải object |
| Object Versioning | Có thể lấy lại phiên bản bytes trước đó không? | Không bảo vệ khỏi xóa cả bucket |
| Soft Delete | Có thể phục hồi object/bucket vừa bị xóa không? | Không cung cấp phiên bản đọc được trong trạng thái soft-deleted |
| Retention policy | Object phải được giữ ít nhất bao lâu? | Không tự tạo bản backup độc lập |
| Object hold | Có thể tạm ngăn xóa/thay thế object cụ thể không? | Không tự xác định thời điểm nghiệp vụ cần gỡ hold |
| Lifecycle Management | Khi nào chuyển storage class hoặc xóa object? | Không bỏ qua retention hoặc hold |

Một thiết kế có thể kết hợp nhiều cơ chế. Ví dụ, bucket lưu hồ sơ hợp đồng có thể dùng CMEK, retention policy đã khóa, soft delete và lifecycle rule để quản lý chi phí. Bucket chứa file tạm có thể dùng mã hóa mặc định, soft delete ngắn hoặc tắt theo chính sách, không bật Object Versioning và đặt lifecycle cleanup.

## 3. Các lựa chọn mã hóa trong Cloud Storage

Cloud Storage luôn mã hóa dữ liệu server-side trước khi ghi xuống đĩa. Mã hóa mặc định được Google quản lý và không yêu cầu ứng dụng tự tạo khóa hoặc thêm thao tác mã hóa.

Ngoài mã hóa mặc định, Cloud Storage cung cấp ba lựa chọn chính:

| Cơ chế | Ai quản lý khóa? | Khóa được sử dụng ở đâu? | Use case |
| --- | --- | --- | --- |
| Google-managed encryption (mặc định) | Google | Cloud Storage mã hóa/giải mã trong dịch vụ | Phần lớn ứng dụng cần encryption at rest |
| Customer-managed encryption key (CMEK) | Khách hàng quản lý qua Cloud KMS | Service agent của Cloud Storage dùng key trong Cloud KMS | Compliance, kiểm soát key lifecycle, audit |
| Customer-supplied encryption key (CSEK) | Khách hàng tự quản lý bên ngoài GCS | Client gửi key trong request cần mã hóa/giải mã | Hệ thống có quy trình quản lý khóa riêng |
| Client-side encryption | Ứng dụng hoặc hệ thống khóa của khách hàng | Mã hóa trước khi gửi bytes lên GCS | Cần kiểm soát dữ liệu rõ trước khi rời ứng dụng |

Một object chỉ dùng một trong các phương thức mã hóa object này tại một thời điểm. CMEK và CSEK là server-side encryption: Cloud Storage nhận dữ liệu rồi mã hóa trước khi lưu. Client-side encryption mã hóa dữ liệu trước khi gửi; sau đó Cloud Storage vẫn mã hóa ciphertext theo cơ chế server-side mặc định.

### 3.1. Google-managed encryption

Đây là lựa chọn mặc định. Cloud Storage tự quản lý key material, mã hóa/giải mã và luân chuyển khóa nội bộ. Ứng dụng tiếp tục dùng Storage.create, Storage.reader, Blob.downloadTo như bình thường.

Ưu điểm:

- Không phải quản lý private key hoặc key ring.
- Không cần thêm quyền Cloud KMS cho service agent.
- Không phải sửa code upload/download.
- Phù hợp với đa số ứng dụng cần mã hóa dữ liệu at rest.

Mã hóa mặc định không làm object trở thành private theo nghĩa IAM. Principal có storage.objects.get vẫn có thể đọc object qua API. Hãy tiếp tục thiết kế IAM, UBLA, Public Access Prevention và authorization nghiệp vụ.

### 3.2. Khi nào chọn CMEK?

Chọn CMEK khi tổ chức cần quản lý vòng đời khóa, phân quyền sử dụng khóa, audit hoạt động mã hóa hoặc đáp ứng chính sách compliance yêu cầu customer-controlled key.

CMEK cho phép kiểm soát:

- Key ring và key location.
- Key version, rotation schedule và primary version.
- Principal/service agent được phép sử dụng key.
- Audit log về việc sử dụng key.
- Thời điểm disable hoặc destroy key version.

CMEK không có nghĩa metadata object đều được mã hóa bằng key đó. Cloud Storage dùng CMEK cho object data và một số checksum/hash; nhiều metadata còn lại vẫn được bảo vệ bằng khóa server-side của dịch vụ. Vì vậy không đưa thông tin bí mật vào object name, bucket name hoặc custom metadata.

### 3.3. Khi nào chọn CSEK?

CSEK phù hợp khi tổ chức có hệ thống quản lý khóa ngoài Google Cloud và cần tự cung cấp AES-256 key cho mỗi request liên quan đến object.

Cloud Storage không lưu raw CSEK. Khi upload, ứng dụng gửi khóa; khi đọc, tải hoặc copy object, ứng dụng phải cung cấp đúng key đã dùng. Nếu mất khóa, dữ liệu đã mã hóa bằng khóa đó không thể được giải mã lại.

CSEK tăng trách nhiệm quản lý khóa đáng kể. Chỉ dùng khi có quy trình backup, rotation, recovery và kiểm soát truy cập key material đã được kiểm chứng.

### 3.4. Khi nào cần client-side encryption?

Client-side encryption hữu ích khi ứng dụng cần đảm bảo plaintext không được gửi tới Cloud Storage. Ứng dụng mã hóa bytes trước khi upload và giải mã sau khi download. Cloud Storage chỉ nhận ciphertext.

Đổi lại, ứng dụng phải tự quản lý:

- Thuật toán, nonce/IV và format ciphertext.
- Key encryption key và data encryption key.
- Key rotation và re-encryption.
- Integrity/authentication tag.
- Version của định dạng dữ liệu mã hóa.
- Khả năng khôi phục khi key bị mất hoặc bị thu hồi.

Không tự thiết kế thuật toán mật mã. Dùng thư viện mật mã đã được kiểm chứng và một hệ thống quản lý khóa chuyên dụng.

## 4. Cấu hình CMEK với Cloud KMS

### 4.1. Thành phần và luồng truy cập

Khi bucket dùng CMEK, Cloud Storage service agent của project thực hiện encryption/decryption bằng Cloud KMS key. Ứng dụng vẫn gọi Storage API bằng workload identity và IAM object permission thông thường.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant IAM as IAM
    participant GCS as Cloud Storage
    participant Agent as Storage service agent
    participant KMS as Cloud KMS

    App->>IAM: Xác thực workload
    App->>GCS: Upload object
    GCS->>Agent: Yêu cầu mã hóa bằng CMEK
    Agent->>KMS: Encrypt bằng key version hiện hành
    KMS-->>Agent: Wrapped data key
    Agent-->>GCS: Hoàn tất encryption
    GCS-->>App: Object metadata + generation
    App->>GCS: Download object
    GCS->>Agent: Yêu cầu giải mã
    Agent->>KMS: Decrypt data key
    KMS-->>Agent: Data key
    Agent-->>GCS: Hoàn tất decryption
    GCS-->>App: Object bytes
~~~

Cloud Storage service agent có dạng:

`service-PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com`

Lấy đúng service agent của project chứa bucket trước khi cấp quyền. Không dùng runtime service account của Spring Boot thay cho service agent trong cấu hình CMEK.

### 4.2. Quyền IAM cho CMEK

Cấp role `roles/cloudkms.cryptoKeyEncrypterDecrypter` cho Cloud Storage service agent trên đúng CryptoKey. Role này cho phép service agent mã hóa và giải mã bằng key.

Các điều kiện quan trọng:

- Cloud KMS key ring phải ở location tương thích với bucket.
- Bucket multi-region hoặc dual-region có quy tắc location tương ứng; không tự chọn một region gần nhất.
- Chỉ dùng symmetric encryption key cho CMEK của Cloud Storage.
- Cloud KMS API và Cloud Storage API phải được bật.
- Runtime application vẫn cần IAM permission storage.objects.create/get/list/delete theo nghiệp vụ.
- Người quản trị key và người vận hành bucket có thể là hai nhóm principal khác nhau.

Không cấp roles/cloudkms.admin cho runtime service chỉ để upload file. Service agent cần quyền encrypt/decrypt; ứng dụng không cần trực tiếp đọc key material.

### 4.3. Tạo key và cấp quyền

Ví dụ tạo key ring và key trong location tương thích với bucket:

~~~bash
gcloud kms keyrings create document-keyring \
  --location=asia-southeast1 \
  --project=training-platform-security

gcloud kms keys create document-key \
  --keyring=document-keyring \
  --location=asia-southeast1 \
  --purpose=encryption \
  --project=training-platform-security
~~~

Lấy service agent của project chứa bucket:

~~~bash
gcloud storage service-agent \
  --project=training-platform-dev
~~~

Cấp quyền encrypt/decrypt cho service agent trên CryptoKey:

~~~bash
gcloud kms keys add-iam-policy-binding document-key \
  --keyring=document-keyring \
  --location=asia-southeast1 \
  --project=training-platform-security \
  --member="serviceAccount:service-PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com" \
  --role="roles/cloudkms.cryptoKeyEncrypterDecrypter"
~~~

Thay PROJECT_NUMBER bằng project number thực tế của project chứa bucket. Ví dụ chỉ minh họa; xác minh key location, project sở hữu key và service agent trước khi áp dụng.

### 4.4. Đặt CMEK mặc định cho bucket

Một bucket có thể cấu hình default KMS key để object mới sử dụng key đó khi request không chỉ định encryption method khác.

~~~bash
gcloud storage buckets update gs://training-documents-archive \
  --default-encryption-key=projects/training-platform-security/locations/asia-southeast1/keyRings/document-keyring/cryptoKeys/document-key
~~~

Đổi default key chỉ ảnh hưởng object được tạo sau khi cấu hình có hiệu lực. Object cũ vẫn dùng key version đã mã hóa trước đó cho tới khi được rewrite.

### 4.5. Chỉ định CMEK cho một object

Java client hỗ trợ Storage.BlobWriteOption.kmsKeyName:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.nio.charset.StandardCharsets;

public Blob uploadWithCmek(
        Storage storage,
        String bucket,
        String objectName,
        String kmsKeyName,
        String content) {

    BlobInfo info = BlobInfo.newBuilder(bucket, objectName)
            .setContentType("text/plain; charset=utf-8")
            .build();

    return storage.create(
            info,
            content.getBytes(StandardCharsets.UTF_8),
            Storage.BlobWriteOption.kmsKeyName(kmsKeyName));
}
~~~

kmsKeyName là resource name đầy đủ của CryptoKey. Nếu bucket đã có default KMS key và request không chỉ định key khác, Cloud Storage sử dụng default key. Nếu request chỉ định key cụ thể, key đó được ưu tiên cho object.

## 5. Rotation, thay key và re-encryption

### 5.1. Key rotation không tự re-encrypt object cũ

Cloud KMS có thể tạo key version mới và chuyển primary version. Các thao tác mã hóa mới sẽ dùng primary version mới. Object cũ vẫn được giải mã bằng key version đã dùng lúc object được ghi; key version cũ phải tiếp tục ở trạng thái dùng được.

Ví dụ:

| Thời điểm | Key version primary | Object mới | Object cũ |
| --- | --- | --- | --- |
| T1 | version 1 | A dùng version 1 | A dùng version 1 |
| T2 | version 2 | B dùng version 2 | A vẫn dùng version 1 |
| T3 | version 3 | C dùng version 3 | A/B vẫn dùng key version cũ |

Không disable hoặc destroy version 1 chỉ vì primary version đã chuyển sang version 2. Object đang dùng version 1 có thể không tải, copy hoặc rewrite được nếu version đó bị disable/destroy.

### 5.2. Re-encrypt object hiện có

Để chuyển object sang key mới hoặc key version mới, cần rewrite object. Thao tác này đọc dữ liệu bằng khóa hiện tại và ghi lại object bằng khóa đích. Có thể dùng gcloud storage objects update hoặc Storage rewrite/copy API.

~~~bash
gcloud storage objects update \
  gs://training-documents-archive/contracts/contract-001.pdf \
  --encryption-key=projects/training-platform-security/locations/asia-southeast1/keyRings/document-keyring/cryptoKeys/document-key
~~~

Với hàng triệu object, cân nhắc Storage batch operations, manifest, prefix, rate limit và giám sát lỗi. Sau re-encryption, xác minh metadata kmsKeyName của object đã chuyển sang key đích.

Nếu bucket bật Object Versioning, noncurrent generations vẫn có thể dùng key cũ. Chuyển live generation không tự chuyển toàn bộ noncurrent versions. Cần kiểm kê và xử lý các version cũ theo retention/lifecycle policy trước khi disable/destroy key cũ.

### 5.3. Disable và destroy key version

- **Disable:** object dùng key version đó tạm thời không giải mã được. Nếu bật lại key version, dữ liệu có thể truy cập lại.
- **Destroy:** key material bị phá hủy; object phụ thuộc version đó không thể giải mã lại.
- **Primary version bị disable/destroy:** không thể dùng key làm encryption key mới cho tới khi có primary version hợp lệ.

Trước khi disable hoặc destroy, lập danh sách object dùng key version, re-encrypt sang key khác hoặc Google-managed encryption, kiểm tra noncurrent versions và theo dõi lỗi truy cập. Việc destroy key version đang bảo vệ object có thể làm mất dữ liệu vĩnh viễn; storage charges của object vẫn tiếp tục cho tới khi object được xóa.

Đối với object trong bucket có locked retention policy hoặc Object Retention Lock, Cloud KMS có thêm ràng buộc khi destroy key version. Không xem việc khóa retention là một lý do để bỏ qua quy trình quản lý key.

## 6. Customer-Supplied Encryption Keys (CSEK)

### 6.1. Mô hình khóa

CSEK dùng khóa AES-256 do ứng dụng cung cấp. Khóa cần được mã hóa Base64 khi truyền vào Java API. Cloud Storage không lưu raw key; khi đọc object, client phải cung cấp đúng key đã dùng lúc upload.

CSEK thích hợp khi tổ chức có hệ thống quản lý khóa ngoài Google Cloud. Đổi lại, mọi thành phần có thể đọc object cần lấy được key đúng cách từ key vault hoặc Secret Manager. Không lưu CSEK trong source code, application.yml, container image hoặc log.

### 6.2. Upload bằng CSEK

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.nio.charset.StandardCharsets;

public Blob uploadWithCsek(
        Storage storage,
        String bucket,
        String objectName,
        String base64Aes256Key,
        String content) {

    BlobInfo info = BlobInfo.newBuilder(bucket, objectName)
            .setContentType("text/plain; charset=utf-8")
            .build();

    return storage.create(
            info,
            content.getBytes(StandardCharsets.UTF_8),
            Storage.BlobWriteOption.encryptionKey(base64Aes256Key));
}
~~~

base64Aes256Key phải là AES-256 key được mã hóa Base64 đúng định dạng. Ví dụ không tự sinh key từ mật khẩu người dùng. Dùng cryptographically secure random generator hoặc key management system chuyên dụng.

### 6.3. Download bằng CSEK

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.nio.file.Path;

public void downloadWithCsek(
        Storage storage,
        String bucket,
        String objectName,
        String base64Aes256Key,
        Path destination) {

    Blob blob = storage.get(
            BlobId.of(bucket, objectName),
            Storage.BlobGetOption.decryptionKey(base64Aes256Key));

    if (blob == null) {
        throw new IllegalStateException("Object không tồn tại");
    }

    blob.downloadTo(
            destination,
            Blob.BlobSourceOption.decryptionKey(base64Aes256Key));
}
~~~

Ví dụ dùng key cho cả metadata GET và download. Tùy method được gọi, Java client có thể cần BlobGetOption.decryptionKey hoặc BlobSourceOption.decryptionKey. Nếu thiếu key hoặc cung cấp sai key, thao tác giải mã thất bại.

### 6.4. Rotation CSEK

Để đổi CSEK, Cloud Storage cần đọc object bằng old key và rewrite bằng new key:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public Blob rotateCsek(
        Storage storage,
        String bucket,
        String objectName,
        String oldBase64Key,
        String newBase64Key) {

    BlobId id = BlobId.of(bucket, objectName);

    Storage.CopyRequest request = Storage.CopyRequest.newBuilder()
            .setSource(id)
            .setSourceOptions(
                    Storage.BlobSourceOption.decryptionKey(oldBase64Key))
            .setTarget(
                    id,
                    Storage.BlobTargetOption.encryptionKey(newBase64Key))
            .build();

    return storage.copy(request).getResult();
}
~~~

Nếu object lớn, CopyWriter có thể cần nhiều RPC; gọi copyChunk() cho tới khi hoàn tất. Kiểm tra generation, checksum và khả năng đọc sau khi rotation. Nếu Object Versioning bật, các noncurrent versions vẫn được mã hóa bằng key cũ cho tới khi được xử lý riêng.

### 6.5. Quy tắc vận hành CSEK

- Không log raw key hoặc Base64 key.
- Không gửi key qua URL hoặc query parameter.
- Lưu key trong Secret Manager hoặc hệ thống HSM/key vault phù hợp.
- Phân quyền lấy key theo workload và môi trường.
- Có backup/recovery plan cho key material.
- Gắn key version ID nội bộ với object metadata ở database nếu cần tra cứu.
- Kiểm thử đọc object sau khi restart ứng dụng và sau khi rotate key.
- Không destroy key cũ khi còn object hoặc noncurrent generation phụ thuộc key đó.

## 7. Client-side encryption

Với client-side encryption, ứng dụng mã hóa bytes trước khi gửi lên GCS. Cloud Storage lưu ciphertext và vẫn áp dụng server-side encryption mặc định hoặc CMEK ở lớp lưu trữ.

~~~mermaid
flowchart LR
    PLAIN["Plaintext"] --> APPENC["Application encryption"]
    APPENC --> CIPHER["Ciphertext"]
    CIPHER --> GCS["Cloud Storage"]
    GCS --> CIPHER2["Ciphertext download"]
    CIPHER2 --> APPDEC["Application decryption"]
    APPDEC --> PLAIN2["Plaintext"]
    KEY["Key management system"] -. "Encryption/decryption key" .-> APPENC
    KEY -. "Encryption/decryption key" .-> APPDEC
~~~

Client-side encryption có thể phù hợp khi yêu cầu bảo mật không cho phép plaintext xuất hiện trong dịch vụ lưu trữ. Nhưng ứng dụng phải tự thiết kế format dữ liệu, key hierarchy, nonce/IV, authenticated encryption, key rotation và recovery.

Một thiết kế phổ biến là envelope encryption:

1. Tạo Data Encryption Key (DEK) cho object hoặc nhóm object.
2. Mã hóa file bằng authenticated encryption như AES-GCM.
3. Dùng Key Encryption Key (KEK) trong Cloud KMS để wrap DEK.
4. Lưu ciphertext và wrapped DEK cùng metadata không nhạy cảm.
5. Khi đọc, unwrap DEK rồi giải mã và xác minh authentication tag.

Không lưu plaintext DEK lâu dài. Nếu object metadata lưu wrapped key hoặc encryption format version, hãy giới hạn thông tin đó và không đặt dữ liệu bí mật trong object name.

## 8. Object Versioning

### 8.1. Versioning hoạt động thế nào?

Object Versioning được bật ở cấp bucket. Khi một live object bị thay thế hoặc xóa, phiên bản cũ trở thành **noncurrent version** và vẫn tồn tại trong bucket cho tới khi được xóa rõ ràng hoặc bị lifecycle rule xử lý.

Mỗi generation có cùng object name nhưng định danh phiên bản riêng. Ví dụ:

| Thời điểm | Thao tác | Live generation | Noncurrent versions |
| --- | --- | --- | --- |
| T1 | Upload lần đầu | 100 | Không có |
| T2 | Ghi đè object | 101 | 100 |
| T3 | Ghi đè lần nữa | 102 | 100, 101 |
| T4 | Xóa live object | Không có | 100, 101, 102 |

Noncurrent version có thể được đọc nếu request chỉ định generation cụ thể. Khi xóa một noncurrent version, nếu bucket có Soft Delete thì version đó có thể chuyển sang soft-deleted state trước khi bị xóa vĩnh viễn.

### 8.2. Bật Object Versioning

~~~bash
gcloud storage buckets update gs://training-documents-archive \
  --versioning
~~~

Tắt versioning:

~~~bash
gcloud storage buckets update gs://training-documents-archive \
  --no-versioning
~~~

Tắt versioning chỉ ngăn bucket tạo thêm noncurrent versions cho các lần thay thế/xóa tiếp theo. Các version đã tồn tại vẫn còn và cần được quản lý riêng.

### 8.3. Cấu hình bằng Java

~~~java
import com.google.cloud.storage.BucketInfo;
import com.google.cloud.storage.Storage;

public void enableVersioning(
        Storage storage,
        String bucketName) {

    BucketInfo bucketInfo = BucketInfo.newBuilder(bucketName)
            .setVersioningEnabled(true)
            .build();

    storage.update(bucketInfo);
}
~~~

Đây là thao tác quản trị bucket, cần IAM permission storage.buckets.update. Hãy dùng bucket test khi thực hành và kiểm tra cấu hình hiện tại trước khi thay đổi.

### 8.4. Đọc một generation cụ thể

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public Blob readVersion(
        Storage storage,
        String bucket,
        String objectName,
        long generation) {

    return storage.get(
            BlobId.of(bucket, objectName, generation));
}
~~~

Để tải bytes của version đó, dùng BlobId chứa generation trong storage.reader() hoặc Blob.downloadTo(). Không chỉ dùng object name nếu cần đảm bảo lấy đúng phiên bản đã duyệt.

### 8.5. Khôi phục noncurrent version

Có thể copy một noncurrent generation thành object live mới. Việc khôi phục tạo generation mới; không làm generation cũ trở lại thành live generation với cùng ID.

~~~bash
gcloud storage cp \
  gs://training-documents-archive/reports/annual.pdf#OLD_GENERATION \
  gs://training-documents-archive/reports/annual.pdf
~~~

Trước khi restore, xác minh object hiện tại và quyết định có được phép ghi đè không. Nếu versioning đang bật, live version bị ghi đè sẽ trở thành noncurrent version.

### 8.6. Chi phí và giới hạn

- Mỗi noncurrent version được tính storage theo storage class của nó.
- Không có giới hạn mặc định về số object versions có thể tích lũy.
- Object Versioning không bảo vệ dữ liệu khi toàn bộ bucket bị xóa.
- Xóa noncurrent version có thể chịu early deletion charges tùy storage class và thời gian lưu.
- Lifecycle Management nên được dùng để giới hạn số lượng hoặc tuổi của noncurrent versions.

Versioning phù hợp với dữ liệu cần lịch sử thay đổi. Nếu mục tiêu chính là khôi phục object/bucket bị xóa nhầm, cần đánh giá Soft Delete.

## 9. Soft Delete

### 9.1. Cơ chế

Soft Delete giữ object hoặc bucket đã bị xóa trong một khoảng thời gian. Trong thời gian này, resource ở trạng thái soft-deleted: không đọc hoặc ghi như object live, nhưng có thể liệt kê và restore. Hết retention duration, resource được xóa vĩnh viễn.

Với các bucket hỗ trợ Soft Delete, cấu hình mặc định hiện hành thường là 7 ngày. Có thể tùy chỉnh thời gian giữ từ 3 đến 90 ngày; đặt duration bằng 0 để tắt. Một số loại bucket/capability không hỗ trợ Soft Delete.

Soft-deleted object không xuất hiện trong list thông thường. Phải dùng flag/filter riêng để xem chúng.

### 9.2. Liệt kê object đã xóa mềm

~~~bash
gcloud storage ls \
  gs://training-documents-archive/** \
  --soft-deleted
~~~

Liệt kê version soft-deleted của một object:

~~~bash
gcloud storage ls \
  gs://training-documents-archive/reports/annual.pdf \
  --soft-deleted
~~~

### 9.3. Khôi phục một generation

~~~bash
gcloud storage restore \
  gs://training-documents-archive/reports/annual.pdf#DELETED_GENERATION
~~~

Java Storage client cũng có Storage.restore(BlobId); BlobId phải chứa generation:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public Blob restoreSoftDeleted(
        Storage storage,
        String bucket,
        String objectName,
        long deletedGeneration) {

    BlobId deletedVersion = BlobId.of(
            bucket,
            objectName,
            deletedGeneration);

    return storage.restore(deletedVersion);
}
~~~

Quyền restore gồm storage.objects.restore và storage.objects.create. Nếu restore gây ghi đè object live cùng tên, principal còn cần quyền delete phù hợp.

### 9.4. Restore tạo generation mới

Restore tạo một bản live mới trong cùng bucket:

- Object có generation mới.
- Metageneration được đặt lại về 1.
- Create time là thời điểm restore.
- Soft delete time và hard delete time được xóa khỏi bản live mới.
- Nếu bucket dùng Autoclass, object được restore về Standard storage class.
- Nếu đã có live object cùng tên, object hiện tại có thể bị overwrite; với versioning, bản live cũ trở thành noncurrent.

Vì vậy, restore là một thao tác ghi object mới dựa trên dữ liệu đã xóa. Hãy kiểm tra object live hiện tại và generation trước khi restore.

### 9.5. Cấu hình Soft Delete

~~~bash
gcloud storage buckets update gs://training-documents-archive \
  --soft-delete-duration=14d
~~~

Ví dụ đặt thời gian giữ object đã xóa là 14 ngày. Với bucket chứa dữ liệu tạm hoặc cache có số lượng object rất lớn, Soft Delete có thể làm tăng đáng kể chi phí lưu trữ. Cần cân nhắc thời gian giữ theo khả năng phục hồi cần thiết.

### 9.6. So sánh Object Versioning và Soft Delete

| Tiêu chí | Object Versioning | Soft Delete |
| --- | --- | --- |
| Mục đích | Lưu các phiên bản object trước đó | Phục hồi resource đã bị xóa |
| Trạng thái dữ liệu | Noncurrent version có thể đọc | Soft-deleted object không đọc được |
| Khôi phục | Copy version thành live object mới | Restore thành live object mới |
| Xóa bucket | Không bảo vệ khỏi bucket deletion | Có thể giữ bucket đã xóa trong thời gian soft-delete |
| Chi phí | Lưu nhiều generation | Lưu object đã xóa trong retention duration |
| Quản lý tự động | Lifecycle rule xóa noncurrent versions | Hết soft-delete duration thì hard delete |

Có thể bật cả Object Versioning và Soft Delete. Đây là lớp bảo vệ nhiều cấp nhưng cần lifecycle và budget để tránh lưu dữ liệu lâu hơn mong muốn.

## 10. Bucket Retention Policy và Bucket Lock

### 10.1. Retention policy là gì?

Bucket retention policy đặt thời gian lưu tối thiểu cho object trong bucket. Object không thể bị xóa hoặc thay thế trước khi đạt tuổi lưu giữ quy định. Chính sách áp dụng cho object hiện có và object mới sau khi policy có hiệu lực.

Ví dụ, retention period là 365 ngày:

- Object đã tồn tại 30 ngày cần được giữ thêm 335 ngày.
- Object đã tồn tại 400 ngày có thể đủ điều kiện xóa/thay thế nếu không có hold hoặc retention khác.
- Object mới được ghi đè sẽ có thời điểm tạo mới và bắt đầu thời gian retention mới.

Nếu thao tác xóa/thay thế vi phạm bucket retention policy, Cloud Storage từ chối với lỗi retention policy chưa được đáp ứng. Lifecycle Delete cũng phải chờ object đủ retention period.

### 10.2. Cấu hình retention period

~~~bash
gcloud storage buckets update gs://training-documents-archive \
  --retention-period=365d
~~~

Đọc cấu hình:

~~~bash
gcloud storage buckets describe \
  gs://training-documents-archive \
  --format="default(retention_policy)"
~~~

Retention period được tính bằng giây trong API. CLI cho phép biểu diễn bằng ngày, tuần, tháng, năm hoặc giây. Thời gian tối đa theo tài liệu hiện hành là 100 năm.

### 10.3. Bucket Lock

Khi retention policy chưa khóa, quản trị viên có thể tăng, giảm hoặc gỡ policy. Khi đã **lock**:

- Không thể giảm retention period.
- Không thể gỡ retention policy.
- Có thể tăng retention period.
- Không thể xóa bucket khi còn object chưa đủ retention period.
- Cloud Storage tạo lien trên project để ngăn xóa project trong khi bucket lock còn hiệu lực.

Lock là thao tác không thể đảo ngược. Đây là cơ chế dành cho yêu cầu immutable storage/compliance; cần quy trình phê duyệt, xác minh bucket, retention period và kế hoạch lưu giữ trước khi thực hiện.

~~~bash
gcloud storage buckets update gs://training-documents-archive \
  --lock-retention-period
~~~

Không chạy lệnh lock trên bucket production chỉ để thử nghiệm. Hãy dùng bucket test riêng, và chỉ lock khi đã kiểm tra kỹ tác động lâu dài.

### 10.4. Bucket retention và Object Versioning

Khi Object Versioning bật, một live object có thể trở thành noncurrent version dù chưa hết retention period. Tuy nhiên, phiên bản đó vẫn phải được giữ theo retention policy và không thể bị xóa trước hạn. Điều này cho phép giữ lại lịch sử phiên bản nhưng ngăn xóa dữ liệu trước thời điểm được phép.

### 10.5. Retention không thay thế backup

Bucket Lock giúp ngăn object bị xóa sớm trong bucket. Nó không thay thế bản sao độc lập ở project/account khác, kế hoạch disaster recovery hoặc kiểm soát xóa toàn bộ project. Hãy thiết kế backup/replication theo yêu cầu RPO/RTO và failure domain của hệ thống.

## 11. Object Retention Lock và object holds

### 11.1. Object Retention Lock

Bucket retention policy áp dụng cùng một khoảng thời gian tối thiểu cho object trong bucket. Object Retention Lock cho phép đặt thời điểm retain-until và chế độ retention riêng cho từng object, với điều kiện bucket đã bật object retention.

Hai mode cần hiểu:

- **Unlocked:** cấu hình có thể được sửa hoặc gỡ theo điều kiện dịch vụ và quyền phù hợp.
- **Locked:** không thể giảm thời gian hoặc gỡ cấu hình retention của object; thao tác lock là không thể đảo ngược.

Ví dụ cập nhật retention configuration cho một object bằng CLI:

~~~bash
gcloud storage objects update \
  gs://training-documents-archive/contracts/contract-001.pdf \
  --retain-until=2028-02-15T05:30:00Z \
  --retention-mode=Unlocked
~~~

Khi cần lock object retention, phải đánh giá lại ngày retain-until và hậu quả không thể rút ngắn. Không áp dụng retention lock cho object tạm, file staging hoặc component object cần cleanup.

Nếu sửa một retention configuration Unlocked hiện có theo hướng lock hoặc rút ngắn retain-until, một số lệnh gcloud yêu cầu thêm cờ `--override-unlocked-retention`. Hãy xác minh trạng thái hiện tại và quyền quản trị trước khi dùng cờ này; nó không biến thao tác thành một thay đổi an toàn hoặc có thể rollback.

### 11.2. Temporary hold

Temporary hold là cờ trên object. Khi bật, object không thể bị xóa hoặc thay thế. Khi gỡ hold, thời gian retention bucket không bị reset.

Use case: giữ một file trong lúc điều tra hoặc xử lý sự cố, sau đó gỡ hold khi được phê duyệt.

### 11.3. Event-based hold

Event-based hold giữ object cho tới khi một sự kiện nghiệp vụ xảy ra. Khi gỡ event-based hold, thời gian lưu giữ trong bucket retention policy được tính lại từ thời điểm gỡ hold.

Use case: hồ sơ khoản vay phải được giữ cho tới khi khoản vay tất toán; sau khi tất toán, hệ thống gỡ hold và bắt đầu tính thời hạn lưu giữ theo chính sách.

### 11.4. Đặt hold bằng Java

Java client cung cấp BlobInfo.Builder.setTemporaryHold và setEventBasedHold. Các API này có thể mang trạng thái Beta/Pre-GA tùy version thư viện; hãy kiểm tra Javadoc và điều khoản Pre-GA trước khi dùng trong production.

~~~java
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.BlobId;

BlobInfo heldObject = BlobInfo.newBuilder(
        BlobId.of(bucket, objectName))
    .setContentType("application/pdf")
    .setTemporaryHold(true)
    .setEventBasedHold(true)
    .build();
~~~

Khi tạo object, truyền BlobInfo vào Storage.create. Nếu cập nhật hold trên object hiện có, đọc Blob trước, tạo BlobInfo từ toBuilder(), thay cờ hold và cập nhật với generation/metageneration precondition.

### 11.5. Ma trận tác động

| Cơ chế | Ngăn xóa? | Ngăn thay thế? | Có thể sửa metadata? | Thời gian được tính như thế nào? |
| --- | --- | --- | --- | --- |
| Bucket retention | Có, trước hạn | Có, trước hạn | Có | Từ thời điểm object được lưu trong bucket |
| Object retention locked | Có, trước retain-until | Có, trước retain-until | Metadata editable có thể vẫn sửa | Theo retain-until của object |
| Temporary hold | Có | Có | Có | Không reset bucket retention clock |
| Event-based hold | Có | Có | Có | Khi gỡ hold, bucket retention clock bắt đầu lại |
| Soft Delete | Sau delete, giữ bản soft-deleted | Không phải cơ chế chặn ghi đè trước delete | Không sửa soft-deleted object | Theo soft delete retention duration |

Object holds không đồng nghĩa với encryption hoặc IAM. Principal vẫn cần quyền phù hợp để đặt/gỡ hold; việc gỡ hold phải gắn với quy trình nghiệp vụ và audit trail.

## 12. Object Lifecycle Management

### 12.1. Mô hình rule

Lifecycle Management tự động thực hiện một action khi object thỏa tất cả điều kiện trong rule. Mỗi rule có đúng một action:

- Delete: xóa object hoặc version phù hợp.
- SetStorageClass: chuyển object sang storage class khác.
- AbortIncompleteMultipartUpload: hủy multipart upload chưa hoàn tất theo điều kiện tương ứng.

Kết quả của action Delete còn phụ thuộc cấu hình bucket. Nếu Object Versioning bật, xóa live object làm generation đó trở thành noncurrent version. Nếu versioning không bật nhưng Soft Delete bật, object đã xóa chuyển sang soft-deleted state. Khi xóa một noncurrent version trong bucket có Soft Delete, version đó cũng có thể chuyển sang soft-deleted state. Vì vậy, lifecycle rule không đồng nghĩa với việc bytes bị xóa vĩnh viễn ngay tại thời điểm rule chạy.

Các điều kiện thường dùng:

| Condition | Ý nghĩa |
| --- | --- |
| age | Số ngày kể từ khi object được tạo |
| createdBefore | Object được tạo trước một ngày UTC |
| customTimeBefore | Custom-Time của object trước ngày quy định |
| daysSinceCustomTime | Số ngày kể từ Custom-Time |
| daysSinceNoncurrentTime | Số ngày kể từ khi object trở thành noncurrent |
| noncurrentTimeBefore | Noncurrent version trước một ngày |
| isLive | Chỉ áp dụng cho live hoặc noncurrent version |
| numNewerVersions | Có ít nhất N phiên bản mới hơn |
| matchesPrefix | Tên object bắt đầu bằng prefix |
| matchesSuffix | Tên object kết thúc bằng suffix |
| matchesStorageClass | Object thuộc một hoặc nhiều storage class |
| sizeAboveBytes / sizeBelowBytes | Kích thước bytes vượt ngưỡng hoặc dưới ngưỡng |

Tất cả điều kiện được khai báo trong một rule phải đồng thời thỏa. Ví dụ age=365 và matchesPrefix=["reports/"] chỉ áp dụng cho object trong prefix reports/ đã đủ 365 ngày.

### 12.2. Xóa object tạm sau 30 ngày

Ví dụ lifecycle JSON:

~~~json
{
  "rule": [
    {
      "action": {
        "type": "Delete"
      },
      "condition": {
        "age": 30,
        "matchesPrefix": [
          "tmp/"
        ]
      }
    }
  ]
}
~~~

Rule trên yêu cầu object trong prefix tmp/ đạt 30 ngày mới đủ điều kiện xóa. Lifecycle action chạy bất đồng bộ; ứng dụng không được giả định object sẽ biến mất đúng vào thời điểm điều kiện vừa thỏa.

### 12.3. Xóa noncurrent versions sau 90 ngày

Khi bucket bật Object Versioning, cần quản lý các noncurrent versions. Ví dụ:

~~~json
{
  "rule": [
    {
      "action": {
        "type": "Delete"
      },
      "condition": {
        "isLive": false,
        "daysSinceNoncurrentTime": 90
      }
    }
  ]
}
~~~

Rule này chỉ áp dụng cho noncurrent versions đã trở thành noncurrent ít nhất 90 ngày. Nó không xóa live version.

Có thể dùng numNewerVersions để giữ lại một số lượng phiên bản gần nhất. Ví dụ, xóa version khi đã có ít nhất 5 version mới hơn:

~~~json
{
  "rule": [
    {
      "action": {
        "type": "Delete"
      },
      "condition": {
        "isLive": false,
        "numNewerVersions": 5
      }
    }
  ]
}
~~~

Cấu hình thực tế cần kiểm tra yêu cầu lưu giữ, soft delete và retention policy. Lifecycle Delete không vượt qua object hold hoặc retention period.

### 12.4. Chuyển storage class theo tuổi object

Ví dụ chuyển object trong prefix archive/ sang Coldline sau 90 ngày:

~~~json
{
  "rule": [
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "COLDLINE"
      },
      "condition": {
        "age": 90,
        "matchesPrefix": [
          "archive/"
        ],
        "matchesStorageClass": [
          "STANDARD"
        ]
      }
    }
  ]
}
~~~

Storage class thường gặp:

| Storage class | Minimum storage duration | Retrieval fee |
| --- | ---: | --- |
| Standard | Không có | Không |
| Nearline | 30 ngày | Có |
| Coldline | 90 ngày | Có |
| Archive | 365 ngày | Có |

Chọn class theo tần suất đọc, thời gian lưu và chi phí truy xuất. Nếu object bị xóa trước minimum storage duration, early deletion charges có thể áp dụng. Lifecycle SetStorageClass có ưu thế chi phí so với rewrite thủ công trong nhiều trường hợp; vẫn cần tính chi phí lưu trữ, operation và retrieval theo pricing hiện hành.

### 12.5. Autoclass

Autoclass cho phép Cloud Storage tự chuyển storage class theo mức độ truy cập. Khi bucket bật Autoclass, không dùng matchesStorageClass condition trong lifecycle rule. Hãy chọn Autoclass hoặc các lifecycle transition rule theo cách quản lý phù hợp; tránh cấu hình xung đột khiến việc dự đoán storage class khó khăn.

### 12.6. Gắn lifecycle config vào bucket

Dùng gcloud:

~~~bash
gcloud storage buckets update gs://training-documents-archive \
  --lifecycle-file=lifecycle.json
~~~

Có thể đọc lại cấu hình bucket bằng:

~~~bash
gcloud storage buckets describe \
  gs://training-documents-archive
~~~

Không áp dụng lifecycle Delete trên toàn bucket nếu chưa xác minh prefix, age, versioning, retention, hold và soft delete. Hãy thử với bucket test có object mẫu và quan sát kết quả.

## 13. Cấu hình Lifecycle Management bằng Java

Java client hỗ trợ BucketInfo.LifecycleRule, LifecycleAction và LifecycleCondition.

Ví dụ xóa object trong prefix tmp/ sau 30 ngày:

~~~java
import com.google.cloud.storage.Bucket;
import com.google.cloud.storage.BucketInfo.LifecycleRule;
import com.google.cloud.storage.BucketInfo.LifecycleRule.LifecycleAction;
import com.google.cloud.storage.BucketInfo.LifecycleRule.LifecycleCondition;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageClass;
import java.util.List;

public void configureTempCleanup(
        Storage storage,
        String bucketName) {

    Bucket bucket = storage.get(bucketName);

    LifecycleRule cleanupRule = new LifecycleRule(
            LifecycleAction.newDeleteAction(),
            LifecycleCondition.newBuilder()
                    .setAge(30)
                    .setMatchesPrefix(List.of("tmp/"))
                    .build());

    bucket.toBuilder()
            .setLifecycleRules(List.of(cleanupRule))
            .build()
            .update();
}
~~~

Ví dụ thay đổi lifecycle config của bucket. Nếu bucket đã có các rule, hãy đọc cấu hình hiện tại và hợp nhất rule mới; không vô tình thay toàn bộ danh sách rule đang có.

Ví dụ chuyển storage class:

~~~java
LifecycleRule coldlineRule = new LifecycleRule(
        LifecycleAction.newSetStorageClassAction(StorageClass.COLDLINE),
        LifecycleCondition.newBuilder()
                .setAge(90)
                .setMatchesPrefix(List.of("archive/"))
                .setMatchesStorageClass(List.of(StorageClass.STANDARD))
                .build());
~~~

Một số lifecycle conditions mới chỉ được hỗ trợ ở các version Java client mới hơn. Hãy kiểm tra Javadoc và BOM; không dùng version thư viện cũ rồi giả định mọi condition trên dịch vụ đều được SDK hỗ trợ.

## 14. Thiết kế Spring Boot cho bucket policy và vòng đời

### 14.1. Tách runtime permission và provisioning permission

Ứng dụng runtime thường chỉ cần đọc/ghi object theo nghiệp vụ. Các thao tác quản trị như thay default KMS key, bật versioning, đặt retention policy, lock bucket hoặc sửa lifecycle config nên được thực hiện bởi pipeline provisioning hoặc principal quản trị chuyên biệt.

| Workload | Quyền điển hình |
| --- | --- |
| Document API upload/download | storage.objects.create/get |
| Document API list | storage.objects.list |
| Cleanup worker | storage.objects.delete trong phạm vi phù hợp |
| Restore operator | storage.objects.restore, storage.objects.create và quyền cần thiết khi overwrite |
| Bucket provisioning | storage.buckets.create/update/get |
| CMEK service agent | cloudkms.cryptoKeyEncrypterDecrypter trên key |
| Key administrator | Quản trị Cloud KMS theo vai trò tách biệt |

Không cấp roles/storage.admin cho mọi service chỉ vì một worker cần upload. Dùng bucket scope và custom role khi cần thu hẹp quyền.

### 14.2. Storage bean

Nếu ứng dụng đã dùng Spring Framework on Google Cloud starter và starter đã auto-configure Storage, inject bean đó. Nếu tự cấu hình:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GcsConfiguration {

    @Bean
    Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Dùng ADC hoặc workload identity. Không đưa service account JSON private key hoặc CSEK vào source code.

### 14.3. Cấu hình theo môi trường

~~~yaml
app:
  gcs:
    bucket: training-documents-dev
    default-kms-key: projects/training-platform-security/locations/asia-southeast1/keyRings/document-keyring/cryptoKeys/document-key
    lifecycle-policy-managed-by: infrastructure
~~~

Các property là ví dụ. Bucket dev, staging và production nên có policy phù hợp với loại dữ liệu và môi trường. Không cho client gửi bucket hoặc KMS key name tùy ý trong API upload.

### 14.4. Phân tách service nghiệp vụ và service quản trị

Một ứng dụng có thể tổ chức các thành phần:

- DocumentStorageService: upload/download/list/delete theo nghiệp vụ.
- ObjectVersionService: lưu generation, truy vấn version và restore bản cũ.
- RetentionPolicyService: kiểm tra thời điểm object được phép xóa và trạng thái hold.
- LifecycleProvisioning: cập nhật lifecycle config trong deployment pipeline.
- EncryptionPolicyService: kiểm tra KMS key name, bucket default encryption và trạng thái key.

Không để một controller người dùng gọi trực tiếp API lock retention hoặc destroy key. Đây là thao tác quản trị có phạm vi ảnh hưởng lớn và cần quy trình kiểm soát riêng.

## 15. Theo dõi, audit và kiểm kê object

Một chính sách chỉ có hiệu lực khi có thể quan sát và kiểm tra.

Các trường metadata hữu ích:

- Bucket/object name hoặc document ID nội bộ.
- Generation và metageneration.
- KMS key name nếu object dùng CMEK.
- Storage class và thời điểm chuyển class.
- Retention expiration time hoặc retain-until time.
- Temporary hold/event-based hold.
- Soft delete time/hard delete time nếu object đã xóa mềm.
- Create/update time và size.

Không ghi raw CSEK, access token hoặc nội dung file vào log. Object name và custom metadata có thể được đọc bằng principal có quyền; tránh đưa thông tin nhạy cảm vào các trường này.

Các tín hiệu cần theo dõi:

- Lỗi 403 do thiếu IAM hoặc Cloud KMS permission.
- Lỗi giải mã sau khi key version bị disable.
- Tỷ lệ object noncurrent và soft-deleted.
- Số object đến hạn lifecycle nhưng chưa được dọn.
- Tổng bytes theo storage class và số generation.
- Số object đang bị hold hoặc retention.
- Lỗi restore và số lần khôi phục.
- Chi phí Cloud KMS HSM/EKM nếu sử dụng key thuộc loại đó.

Dùng Cloud Audit Logs để truy vết thao tác IAM, key, bucket và object. Dùng Storage Insights/inventory reports hoặc BigQuery để kiểm kê số lượng lớn object theo kmsKeyName, storage class, generation, create time và metadata.

## 16. Chi phí và các trade-off

| Cơ chế | Lợi ích | Chi phí/rủi ro vận hành |
| --- | --- | --- |
| Google-managed encryption | Đơn giản, mặc định | Ít quyền kiểm soát key lifecycle hơn CMEK |
| CMEK software key | Kiểm soát key, audit và quyền | Quản lý Cloud KMS/IAM; HSM/EKM có quota/chi phí riêng |
| CSEK | Khóa do khách hàng kiểm soát | Key distribution, backup, rotation và recovery phức tạp |
| Client-side encryption | Plaintext được mã hóa trước khi upload | Ứng dụng tự chịu trách nhiệm cryptography và key lifecycle |
| Object Versioning | Khôi phục phiên bản cũ | Lưu nhiều generation và tăng storage cost |
| Soft Delete | Khôi phục object/bucket vừa xóa | Lưu object deleted trong retention duration |
| Bucket Lock | Immutable retention mạnh | Không thể rút ngắn/gỡ policy; bucket khó dọn/xóa |
| Lifecycle | Tự động quản lý tuổi và storage class | Rule sai có thể xóa nhầm; action không chạy đúng thời điểm tức thì |

Early deletion charges có thể áp dụng khi object ở Nearline, Coldline hoặc Archive bị xóa/thay thế trước minimum storage duration. Thời gian object ở trạng thái live, noncurrent và soft-deleted có thể được tính vào thời gian lưu tối thiểu tùy cơ chế. Khi dùng lifecycle hoặc versioning, cần tính cả số bản object và thời gian giữ thực tế.

Với bucket chứa dữ liệu tạm, versioning + soft delete dài ngày + retention lock có thể làm chi phí tăng mạnh. Với bucket lưu hồ sơ pháp lý, chi phí và thao tác quản trị phức tạp có thể là lựa chọn cần thiết để đáp ứng yêu cầu lưu giữ.

## 17. Kiểm thử encryption, versioning và retention

### 17.1. Unit test

Kiểm tra logic nghiệp vụ và adapter:

- Bucket được chọn theo môi trường, không lấy từ client request.
- Upload dùng đúng KMS key theo policy.
- Không log CSEK hoặc key material.
- Object record lưu generation, size và storage class.
- Document không được đánh dấu READY trước khi upload và kiểm tra metadata thành công.
- Cleanup worker không xóa object còn retention hoặc hold.
- Lifecycle configuration được tạo từ cấu hình đã duyệt.

Mock Storage chỉ kiểm tra logic ứng dụng; không chứng minh Cloud KMS permission, bucket retention hoặc soft delete đang hoạt động thật.

### 17.2. Integration test trên project GCP riêng

1. Tạo bucket test ở location tương thích với KMS key.
2. Cấp Cloud Storage service agent quyền encrypt/decrypt trên key.
3. Upload object bằng default CMEK và kiểm tra kmsKeyName.
4. Thử upload bằng key cụ thể khác và xác minh metadata.
5. Thử download khi service agent thiếu quyền key; xác nhận request thất bại.
6. Rotate KMS primary version, upload object mới và kiểm tra key version.
7. Re-encrypt một object mẫu rồi xác minh object có thể đọc.
8. Bật Object Versioning, ghi đè object và kiểm tra noncurrent generation.
9. Bật Soft Delete, xóa object, liệt kê soft-deleted object và restore theo generation.
10. Đặt retention policy chưa khóa, thử delete trước hạn và xác nhận bị từ chối.
11. Đặt temporary/event-based hold và kiểm tra delete/overwrite.
12. Cấu hình lifecycle trên prefix test và xác minh action sau khi rule đủ điều kiện.
13. Dọn tài nguyên theo chính sách test, kiểm tra object versions và soft-deleted objects còn lại.

Không khóa retention policy hoặc destroy key version trong integration test thông thường. Nếu cần kiểm thử hành vi không thể đảo ngược, dùng project/bucket/key dành riêng cho test và quy trình phê duyệt riêng.

### 17.3. Fault injection

Mô phỏng:

- Cloud KMS key version bị disable.
- Storage service agent bị thu hồi quyền KMS.
- Runtime service account thiếu storage.objects.create.
- Upload object mới nhưng database update thất bại.
- Ghi đè object khi Object Versioning đang bật.
- Delete object đang có hold.
- Restore soft-deleted object khi đã có live object cùng tên.
- Lifecycle Delete chạy trên object còn retention.
- Noncurrent version tồn tại lâu hơn dự kiến do thiếu lifecycle rule.
- KMS rotation hoàn tất nhưng một số noncurrent versions vẫn dùng key cũ.

Kết quả cần đạt: hệ thống không đánh dấu file sẵn sàng sai, không xóa dữ liệu trái retention, có thể xác định object dùng key version nào và có quy trình khôi phục được kiểm thử.

## 18. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Upload CMEK trả 403 | Storage service agent thiếu quyền Cloud KMS | Cấp roles/cloudkms.cryptoKeyEncrypterDecrypter trên đúng key |
| CMEK key không dùng được | Key location không tương thích với bucket | Kiểm tra location bucket/key ring |
| Download object CMEK thất bại | Key version bị disable/destroy hoặc service agent mất quyền | Kiểm tra KMS key version và IAM |
| Sau rotation, object cũ vẫn dùng key cũ | Rotation không tự re-encrypt object | Rewrite object và kiểm tra noncurrent versions |
| CSEK download trả lỗi giải mã | Thiếu/sai AES-256 key | Tra key version trong key vault và cung cấp đúng decryption key |
| Mất quyền đọc CSEK object | Key material bị mất | Khôi phục từ key backup; nếu không còn key thì không thể giải mã |
| Version count tăng liên tục | Không có lifecycle cleanup noncurrent versions | Thêm daysSinceNoncurrentTime hoặc numNewerVersions |
| Delete object bị từ chối | Retention policy, object retention hoặc hold | Kiểm tra retention expiration và hold state |
| Lifecycle không xóa object | Điều kiện chưa đủ, hold hoặc retention còn hiệu lực | Kiểm tra tất cả điều kiện và thời điểm policy |
| Restore tạo object live khác | Restore tạo generation mới | Cập nhật database với generation mới |
| Restore ghi đè file hiện tại | Đã có live object cùng object name | Kiểm tra live generation trước khi restore |
| Chi phí tăng sau khi bật versioning | Nhiều noncurrent versions được giữ | Thêm lifecycle rule và kiểm tra retention yêu cầu |
| Soft-deleted object không xuất hiện trong list | List thông thường ẩn soft-deleted resources | Dùng --soft-deleted hoặc API filter |
| Lock retention không thành công | Thiếu bucket update permission hoặc metageneration mismatch | Đọc bucket metadata mới và kiểm tra IAM |

## 19. Ví dụ chính sách theo loại dữ liệu

### 19.1. Tài liệu giao dịch

Yêu cầu: cần mã hóa có kiểm soát, lưu giữ tối thiểu theo chính sách và có audit.

- Dùng CMEK với key ring cùng location tương thích bucket.
- Tách runtime identity, Storage service agent và key administrator.
- Dùng retention policy theo thời hạn pháp lý.
- Chỉ lock bucket sau khi compliance/legal và vận hành xác nhận.
- Dùng Soft Delete để có khoảng khôi phục nếu phù hợp.
- Audit các thao tác restore, delete, key rotation và IAM change.

### 19.2. File người dùng có thể cập nhật

Yêu cầu: cho phép người dùng thay thế file nhưng cần khôi phục bản trước đó.

- Dùng Google-managed encryption hoặc CMEK theo yêu cầu.
- Bật Object Versioning.
- Lưu generation hiện tại trong database.
- Dùng generation precondition khi replace/delete.
- Lifecycle xóa noncurrent versions sau thời hạn được duyệt.
- Dùng Soft Delete nếu cần thêm cửa sổ khôi phục sau khi xóa version.

### 19.3. File tạm và cache

Yêu cầu: thời gian tồn tại ngắn, khối lượng lớn và chi phí thấp.

- Dùng mã hóa mặc định.
- Không bật Bucket Lock.
- Không bật Object Versioning nếu không cần lịch sử.
- Chọn Soft Delete duration phù hợp hoặc tắt nếu policy cho phép.
- Lifecycle xóa prefix tmp/ sau TTL.
- Giới hạn size và quota khi upload.
- Theo dõi số object và tổng bytes để tránh tích lũy dữ liệu ngoài dự kiến.

### 19.4. Hồ sơ điều tra hoặc legal hold

Yêu cầu: giữ object cho tới khi có sự kiện hoặc quyết định giải phóng.

- Dùng temporary hold hoặc event-based hold theo semantics nghiệp vụ.
- Ghi người đặt hold, lý do, thời điểm và người phê duyệt.
- Gỡ hold qua workflow có audit.
- Nếu có bucket retention policy, hiểu rõ event-based hold làm reset thời điểm bắt đầu tính retention.
- Không dùng lifecycle để cố xóa object đang bị hold.

## 20. So sánh với AWS S3 và Azure Blob Storage

| Khía cạnh | Google Cloud Storage | Amazon S3 | Azure Blob Storage |
| --- | --- | --- | --- |
| Mã hóa mặc định | Server-side encryption do Google quản lý | SSE-S3 mặc định cho object mới | Storage Service Encryption mặc định |
| Khóa khách hàng quản lý | CMEK qua Cloud KMS | SSE-KMS qua AWS KMS | Customer-managed key qua Azure Key Vault |
| Khóa khách hàng cung cấp | CSEK trong request | SSE-C | Customer-provided keys |
| Client-side encryption | Ứng dụng tự mã hóa bytes | S3 Encryption Client | Client-side encryption SDK |
| Versioning | Object Versioning, generation | S3 Versioning, Version ID | Blob versioning |
| Soft delete/recovery | Soft Delete và restore | Delete markers/versioning, object recovery tùy tính năng | Soft delete cho blob/container |
| Retention/immutable | Bucket Lock, Object Retention Lock, holds | S3 Object Lock governance/compliance | Immutable Blob Storage policies/legal holds |
| Lifecycle | Delete, SetStorageClass và multipart cleanup | Expiration, transition, abort multipart | Delete, tiering và version management |

Các provider có tên tính năng tương tự nhưng semantics khác nhau. Generation của GCS không đồng nghĩa với S3 Version ID hoặc Azure Version ID. CMEK không đồng nghĩa với toàn bộ cấu hình KMS của provider khác. Adapter đa cloud nên chuẩn hóa các hành vi nghiệp vụ như encrypt, retain, restore, listVersions và applyLifecycle, còn từng adapter giữ chi tiết key reference, version token, hold và retention API.

## 21. Bài tập thực hành tổng hợp

**Bối cảnh:** Xây ứng dụng Spring Boot document-api quản lý hồ sơ hợp đồng và file tạm trong hai bucket riêng. Hồ sơ hợp đồng cần mã hóa bằng CMEK, lưu tối thiểu 7 năm và có khả năng khôi phục phiên bản. File tạm chỉ cần tồn tại 30 ngày.

### Nhiệm vụ A — Encryption

1. Tạo Cloud KMS key ring và symmetric key ở location tương thích với bucket.
2. Lấy Storage service agent của project.
3. Cấp roles/cloudkms.cryptoKeyEncrypterDecrypter trên CryptoKey.
4. Cấu hình default CMEK cho bucket hợp đồng.
5. Upload object và xác minh kmsKeyName.
6. Rotate primary key version và giải thích vì sao object cũ vẫn cần key version cũ.
7. Re-encrypt một object test và kiểm tra khả năng đọc.

### Nhiệm vụ B — Versioning và Soft Delete

1. Bật Object Versioning trên bucket hợp đồng.
2. Upload một object, ghi generation vào database.
3. Ghi đè object và xác minh generation cũ thành noncurrent.
4. Xóa live object trong bucket test có Soft Delete.
5. Liệt kê soft-deleted generation và restore.
6. Cập nhật document record theo generation mới sau restore.

### Nhiệm vụ C — Retention và holds

1. Đặt bucket retention period theo yêu cầu thử nghiệm.
2. Thử xóa object trước hạn và xử lý lỗi.
3. Đặt temporary hold cho một object.
4. Gỡ temporary hold theo workflow có audit.
5. Đặt event-based hold và quan sát thời điểm retention bắt đầu lại sau khi gỡ.
6. Trên bucket test riêng, mô phỏng Bucket Lock và giải thích vì sao không thể rút ngắn/gỡ policy sau khi lock.

### Nhiệm vụ D — Lifecycle

1. Tạo rule xóa object trong prefix tmp/ sau 30 ngày.
2. Tạo rule xóa noncurrent versions sau 90 ngày.
3. Tạo rule chuyển object archive/ sang Coldline khi đủ tuổi.
4. Giải thích vì sao lifecycle không xóa object đang hold hoặc chưa hết retention.
5. Kiểm tra storage class và chi phí minimum duration.

### Nhiệm vụ E — Spring Boot và kiểm thử

- Tạo Storage bean qua ADC/workload identity.
- Tách runtime role và provisioning role.
- Lưu generation, kmsKeyName và retention metadata cần thiết trong document record.
- Không lưu CSEK hoặc private key trong source code.
- Test upload/download CMEK, restore, versioning, hold và lifecycle trên project riêng.
- Kiểm tra audit logs, key version và object generation.
- So sánh thiết kế với AWS S3 và Azure Blob Storage.

**Tiêu chí đạt:** Ứng dụng sử dụng đúng encryption mode; có thể xác định key bảo vệ object; quản lý version và khôi phục object; không xóa trước retention/hold; lifecycle cleanup đúng prefix/age; và có integration test chứng minh behavior của Cloud Storage thật.

## 22. Ghi nhớ

- Cloud Storage luôn mã hóa server-side theo mặc định; chỉ chọn CMEK/CSEK/client-side encryption khi yêu cầu kiểm soát khóa đòi hỏi.
- CMEK cần Cloud Storage service agent có quyền encrypt/decrypt trên Cloud KMS key; key location phải tương thích với bucket.
- Rotation CMEK không tự re-encrypt object cũ; phải rewrite và kiểm tra cả noncurrent versions trước khi disable/destroy key cũ.
- CSEK yêu cầu client cung cấp đúng key khi đọc; mất key có thể làm dữ liệu không thể khôi phục.
- Object Versioning giữ noncurrent generations nhưng không bảo vệ khỏi xóa bucket.
- Soft Delete giữ object/bucket đã xóa trong thời gian cấu hình và restore tạo generation mới.
- Retention policy ngăn xóa/thay thế trước hạn; Bucket Lock không thể đảo ngược.
- Temporary hold và event-based hold đều chặn delete/overwrite; event-based hold có semantics riêng khi bắt đầu lại retention clock.
- Lifecycle rule có một action và tất cả conditions phải thỏa; Delete không vượt qua retention hoặc hold.
- Kiểm soát chi phí bằng lifecycle, storage class phù hợp, Soft Delete duration và giới hạn noncurrent versions.
- Trong Spring Boot, tách runtime permission khỏi bucket/key provisioning và audit các thao tác khôi phục, rotation, retention.

### Tài liệu tham khảo

- [Data encryption options — Cloud Storage](https://docs.cloud.google.com/storage/docs/encryption)
- [Customer-managed encryption keys](https://docs.cloud.google.com/storage/docs/encryption/customer-managed-keys)
- [Use customer-managed encryption keys](https://docs.cloud.google.com/storage/docs/encryption/using-customer-managed-keys)
- [Customer-supplied encryption keys](https://docs.cloud.google.com/storage/docs/encryption/customer-supplied-keys)
- [Use customer-supplied encryption keys](https://docs.cloud.google.com/storage/docs/encryption/using-customer-supplied-keys)
- [Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Soft Delete overview](https://docs.cloud.google.com/storage/docs/soft-delete)
- [Use soft-deleted objects](https://docs.cloud.google.com/storage/docs/use-soft-deleted-objects)
- [Request preconditions and object generations](https://docs.cloud.google.com/storage/docs/request-preconditions)
- [Bucket Lock and retention policies](https://docs.cloud.google.com/storage/docs/bucket-lock)
- [Object Retention Lock](https://docs.cloud.google.com/storage/docs/object-lock)
- [Object holds](https://docs.cloud.google.com/storage/docs/object-holds)
- [Object Lifecycle Management](https://docs.cloud.google.com/storage/docs/lifecycle)
- [Storage classes](https://docs.cloud.google.com/storage/docs/storage-classes)
- [Java Storage interface](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Java BlobInfo](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.BlobInfo)
- [Java BucketInfo](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.BucketInfo)
- [Java BlobWriteOption](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobWriteOption)
- [Java BlobSourceOption](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobSourceOption)
