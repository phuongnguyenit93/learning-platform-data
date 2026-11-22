# Mã hóa khi lưu trữ, khi truyền và envelope encryption

Dữ liệu trong hệ thống AWS cần được bảo vệ ở nhiều trạng thái: khi nằm trên đĩa, khi di chuyển qua mạng và trong lúc ứng dụng xử lý. Mã hóa giúp giảm nguy cơ lộ nội dung khi storage media, snapshot, backup, network traffic hoặc artifact bị truy cập trái phép. Tuy nhiên, hiệu quả của mã hóa phụ thuộc vào cách quản lý khóa, phân quyền giải mã, cấu hình TLS và quy trình vận hành.

AWS cung cấp các lớp mã hóa tích hợp trong dịch vụ như Amazon S3, EBS, RDS và EFS; AWS Key Management Service (AWS KMS) quản lý key material và quyền sử dụng khóa. Với ứng dụng cần tự mã hóa dữ liệu trước khi gửi/lưu, **envelope encryption** dùng một data key để mã hóa nội dung, rồi dùng một key quản lý cấp cao hơn để bảo vệ data key. Cách này giúp xử lý dữ liệu lớn mà không phải gửi toàn bộ plaintext qua KMS.

Bài thuộc chương **Mã hóa, secret và chứng chỉ**, mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung kết nối KMS, S3, EBS, RDS, EFS, TLS, AWS Certificate Manager và ứng dụng Java/Spring Boot để lựa chọn lớp bảo vệ phù hợp, quản lý vòng đời khóa và vận hành an toàn.

> **Nguyên tắc:** Encryption bảo vệ confidentiality và integrity ở đúng phạm vi thuật toán cung cấp; authorization vẫn quyết định ai được đọc hoặc giải mã. Không có khóa phù hợp và quyền `kms:Decrypt`, ciphertext không tự biến thành plaintext. Không ghi plaintext data keys, secrets hoặc private keys vào log, source control, artifact hay ticket.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt encryption at rest, encryption in transit và encryption in use.
2. Giải thích vai trò của symmetric encryption, asymmetric encryption, hash và authenticated encryption.
3. Phân biệt data key với KMS key/wrapping key.
4. Mô tả envelope encryption và luồng `GenerateDataKey`/`Decrypt`.
5. Giải thích encryption context và vì sao không được đưa dữ liệu nhạy cảm vào context.
6. So sánh S3 SSE-S3, SSE-KMS, DSSE-KMS, SSE-C và client-side encryption.
7. Cấu hình default encryption cho S3 bucket và kiểm tra object encryption.
8. Giải thích KMS key policy, IAM policy, grants và cross-account key access.
9. Chọn cách mã hóa phù hợp cho EBS, RDS, EFS và backup/snapshot.
10. Giải thích TLS handshake, certificate chain, hostname validation và HTTPS.
11. Dùng AWS Certificate Manager (ACM) để quản lý certificate cho dịch vụ tích hợp.
12. Enforce TLS cho S3 và các endpoint ứng dụng.
13. Phân biệt automatic KMS key rotation với re-encryption/migration sang key mới.
14. Thiết kế quyền decrypt least privilege và tách nhiệm vụ key administration.
15. Điều tra lỗi access denied, invalid ciphertext, certificate và TLS handshake.
16. Thực hành envelope encryption và kiểm tra encryption trên AWS sandbox.

## 2. Ba trạng thái bảo vệ dữ liệu

| Trạng thái | Dữ liệu đang ở đâu? | Rủi ro chính | Biện pháp |
|---|---|---|---|
| At rest | S3 objects, EBS volumes, RDS storage, EFS, snapshots, backup | Truy cập storage/snapshot trái phép, mất thiết bị, bản sao bị lộ | Server-side/client-side encryption, KMS, access control |
| In transit | Internet, VPC, service-to-service, client-to-API, replication | Eavesdropping, tampering, man-in-the-middle | TLS/HTTPS, certificate validation, private connectivity |
| In use | RAM, process memory, query result, application runtime | Memory dump, compromised process, debug/log exposure | Least privilege, isolation, memory hygiene, confidential computing khi phù hợp |

Mã hóa at rest không tự bảo vệ dữ liệu sau khi ứng dụng đã giải mã trong RAM. TLS bảo vệ kênh truyền, không ngăn một endpoint đã bị compromise đọc plaintext. Mã hóa không thay thế IAM, network segmentation, patching, monitoring, backup và incident response.

### 2.1. Encryption at rest

Dịch vụ lưu trữ mã hóa dữ liệu trước khi ghi xuống storage media và giải mã khi principal được phép đọc. Với managed service, AWS có thể xử lý phần lớn thao tác cryptographic trong service; ứng dụng vẫn cần chọn key type, policy và encryption settings phù hợp.

Ví dụ:

- S3 mã hóa object bằng SSE-S3 mặc định; có thể chọn SSE-KMS hoặc DSSE-KMS.
- EBS mã hóa volume và snapshot bằng KMS key.
- RDS mã hóa database storage, automated backups, snapshots và read replicas theo các giới hạn dịch vụ.
- EFS mã hóa file system data at rest bằng KMS key; client có thể dùng TLS khi mount.
- Backup và bản sao dữ liệu cần giữ encryption boundary tương ứng.

### 2.2. Encryption in transit

TLS tạo kênh mã hóa giữa client và server. Certificate cho phép client xác minh server đang kết nối đúng hostname và certificate chain được tin cậy. TLS cũng bảo vệ tính toàn vẹn của record trong phiên kết nối.

Trong AWS, dùng HTTPS cho public APIs, TLS cho database connections, TLS giữa load balancer và targets khi cần, và private connectivity/VPC endpoints để giảm exposure. Private network không tự đồng nghĩa traffic đã được mã hóa.

### 2.3. Encryption in use

Khi ứng dụng xử lý dữ liệu, plaintext thường tồn tại trong process memory. Bảo vệ lớp này cần controls khác như workload isolation, IAM least privilege, không dump memory chứa secrets, giới hạn debug/heap dumps, và cân nhắc Nitro Enclaves/confidential computing cho use case đặc biệt. Đây là lớp bổ sung, không phải tính năng tự động có khi bật KMS.

## 3. Nền tảng mật mã cần biết

### 3.1. Symmetric và asymmetric encryption

| Đặc điểm | Symmetric encryption | Asymmetric encryption |
|---|---|---|
| Khóa | Cùng một secret key để encrypt/decrypt | Public key và private key liên hệ toán học |
| Hiệu năng | Nhanh, phù hợp dữ liệu lớn | Chậm hơn, thường dùng cho key exchange, signatures hoặc bảo vệ key nhỏ |
| Ví dụ | AES-256-GCM | RSA, elliptic-curve cryptography |
| Ứng dụng | Mã hóa object, volume, file, database | TLS certificate, digital signatures, key wrapping trong một số mô hình |

AWS KMS symmetric encryption keys thường phù hợp cho data encryption và envelope encryption. KMS asymmetric keys có thể dùng cho encrypt/decrypt hoặc sign/verify theo key usage; không dùng asymmetric KMS key để gọi `GenerateDataKey` cho symmetric data key.

### 3.2. Authenticated encryption

Mã hóa hiện đại nên cung cấp confidentiality và authentication/integrity. AES-GCM là một authenticated encryption with associated data (AEAD) mode: ngoài ciphertext, thuật toán tạo authentication tag để phát hiện ciphertext/AAD bị thay đổi.

Các yếu tố quan trọng:

- Nonce/IV phải được tạo và sử dụng đúng yêu cầu của thuật toán.
- Không tái sử dụng nonce với cùng key trong cách dùng AES-GCM thông thường.
- Authentication tag phải được xác minh trước khi chấp nhận plaintext.
- Additional authenticated data (AAD) được xác thực cùng ciphertext nhưng không bị mã hóa.

Không tự thiết kế thuật toán hoặc format mã hóa cho production. Dùng thư viện được duy trì như AWS Encryption SDK hoặc cơ chế mã hóa native của dịch vụ, theo algorithm suite và commitment policy được tài liệu khuyến nghị.

### 3.3. Hash và digital signature không thay thế encryption

Hash một chiều tạo digest để kiểm tra dữ liệu có thay đổi hay không; hash không giúp khôi phục plaintext. Digital signature dùng private key ký và public key xác minh nguồn gốc/tính toàn vẹn; chữ ký không che nội dung. TLS thường kết hợp certificate, chữ ký, key exchange và symmetric session keys để xác thực peer và mã hóa dữ liệu truyền.

## 4. Key hierarchy: KMS key và data key

Một hệ thống mã hóa thường có nhiều tầng khóa:

- **KMS key (wrapping key):** khóa quản lý trong AWS KMS, kiểm soát bằng key policy/IAM/grants.
- **Data key (DEK):** khóa đối xứng dùng mã hóa dữ liệu thực tế.
- **Encrypted data key (EDK):** bản data key đã được mã hóa bởi KMS key; có thể lưu cùng ciphertext.
- **Plaintext data key:** chỉ tồn tại trong bộ nhớ của tiến trình cần mã hóa/giải mã; phải được xóa khỏi bộ nhớ sớm nhất có thể.

~~~mermaid
flowchart TD
    KMS["AWS KMS key<br/>Key policy + IAM"]
    KMS -->|"Encrypt / wrap"| EDK["Encrypted data key (EDK)"]
    KMS -->|"GenerateDataKey"| DEK["Plaintext data key (DEK)"]
    DEK -->|"AES-GCM"| CT["Encrypted application data"]
    EDK --> STORE["Store EDK + ciphertext + metadata"]
    CT --> STORE
    STORE -->|"Read"| APP["Authorized application"]
    APP -->|"Decrypt EDK through KMS"| KMS
    KMS -->|"Plaintext DEK over TLS"| APP
    APP -->|"Decrypt ciphertext"| DATA["Plaintext data in memory"]
~~~

KMS key không trực tiếp mã hóa file/object lớn trong quy trình `GenerateDataKey`. Ứng dụng dùng plaintext data key để mã hóa dữ liệu bên ngoài KMS, còn KMS chỉ bảo vệ data key. Với server-side encryption do S3/EBS/RDS quản lý, service xử lý data key và KMS integration thay ứng dụng.

### 4.1. Vì sao dùng envelope encryption?

- **Hiệu năng:** dữ liệu lớn được mã hóa cục bộ bằng symmetric data key, không phải gửi từng byte qua KMS.
- **Giới hạn KMS calls:** chỉ cần KMS operation để tạo hoặc giải mã data key theo envelope.
- **Quản lý tập trung:** KMS key policy kiểm soát ai được wrap/unwrap data keys.
- **Di động:** encrypted data key có thể lưu cạnh ciphertext để sau này giải mã khi principal có quyền.
- **Rotation:** có thể re-encrypt data key bằng KMS key mới mà không nhất thiết mã hóa lại toàn bộ payload, nếu format và quy trình ứng dụng hỗ trợ.

Encrypted data key không tự đủ để giải mã. Cần đúng KMS key, đúng encryption context (nếu có), quyền decrypt và ciphertext tương ứng.

## 5. Envelope encryption với AWS KMS

### 5.1. Luồng mã hóa

1. Ứng dụng gọi `GenerateDataKey` trên symmetric KMS key, có thể truyền `EncryptionContext`.
2. KMS trả plaintext data key và encrypted data key.
3. Ứng dụng dùng plaintext data key với thư viện mã hóa đã được kiểm chứng để mã hóa plaintext thành ciphertext.
4. Ứng dụng lưu ciphertext, encrypted data key, nonce/IV, authentication tag và metadata cần thiết.
5. Ứng dụng xóa/zeroize plaintext data key khỏi memory sau khi dùng.

### 5.2. Luồng giải mã

1. Ứng dụng đọc ciphertext, encrypted data key và metadata.
2. Ứng dụng gọi KMS `Decrypt` với encrypted data key và encryption context chính xác.
3. KMS xác minh authorization, key state và context rồi trả plaintext data key.
4. Ứng dụng xác minh authentication tag và giải mã ciphertext.
5. Ứng dụng xóa plaintext data key khỏi memory.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant KMS as AWS KMS
    participant Store as Object/Database storage
    App->>KMS: GenerateDataKey(KMS key, context)
    KMS-->>App: Plaintext DEK + encrypted DEK
    App->>App: Encrypt payload with DEK (AEAD)
    App->>Store: Store ciphertext + EDK + nonce/tag/context metadata
    Store-->>App: Retrieve encrypted record
    App->>KMS: Decrypt(EDK, same context)
    KMS-->>App: Plaintext DEK
    App->>App: Verify tag and decrypt payload
    App->>App: Clear plaintext DEK from memory
~~~

### 5.3. Tạo data key bằng AWS CLI

Ví dụ yêu cầu KMS tạo AES-256 data key:

~~~bash
aws kms generate-data-key \
  --key-id arn:aws:kms:ap-southeast-1:123456789012:key/11111111-2222-3333-4444-555555555555 \
  --key-spec AES_256 \
  --encryption-context Application=orders,Environment=production \
  --region ap-southeast-1
~~~

Response chứa `Plaintext` và `CiphertextBlob`. Không chạy lệnh này trong terminal dùng chung hoặc ghi output vào log vì response chứa plaintext data key ở dạng base64. Trong ứng dụng, đọc trực tiếp response vào memory, mã hóa payload rồi giải phóng plaintext key. Lưu `CiphertextBlob` cùng ciphertext và metadata không bí mật.

Nếu workflow chỉ cần tạo encrypted data key để lưu và chưa cần mã hóa payload trong cùng bước, KMS có API `GenerateDataKeyWithoutPlaintext` trả về encrypted data key mà không trả plaintext data key. Khi cần mã hóa dữ liệu, ứng dụng phải lấy plaintext data key qua quy trình được thiết kế riêng. API này không thay thế `GenerateDataKey` cho trường hợp ứng dụng cần plaintext key ngay để encrypt.

### 5.4. Encryption context

Encryption context là tập key-value không bí mật được KMS dùng như additional authenticated data cho các symmetric cryptographic operations. Ví dụ:

~~~json
{
  "Application": "orders",
  "Environment": "production",
  "RecordType": "invoice"
}
~~~

Khi giải mã encrypted data key, phải cung cấp encryption context giống hệt, phân biệt chữ hoa/chữ thường. Context được ghi plaintext trong CloudTrail và không được mã hóa; không đưa customer name, email, account number, secret hoặc dữ liệu nhạy cảm vào đây.

Context có thể dùng để:

- Phân biệt mục đích sử dụng key.
- Tăng auditability trong CloudTrail.
- Ràng buộc KMS grants/policies bằng condition keys.
- Ngăn encrypted data key bị dùng trong sai ngữ cảnh nếu ứng dụng xác minh context nhất quán.

### 5.5. AWS Encryption SDK

AWS Encryption SDK triển khai envelope encryption và quản lý message format, data keys, algorithm suites, authentication và key commitment. Với ứng dụng tự mã hóa file/message, ưu tiên dùng SDK thay vì tự xây dựng format mã hóa. SDK có thể sử dụng KMS keyring để wrap data keys và cho phép lưu encrypted message ở S3, database hoặc hệ thống khác.

SDK không tự quản lý IAM permission, KMS key lifecycle, application authorization hoặc plaintext memory trong mọi ngôn ngữ/runtime. Ứng dụng vẫn phải kiểm soát keyring, encryption context, commitment policy, dependency version và quyền decrypt.


## 6. Mã hóa dữ liệu trong Amazon S3

Amazon S3 hỗ trợ server-side encryption (SSE) và client-side encryption. Từ 05/01/2023, S3 tự động áp dụng SSE-S3 cho mọi object mới được upload; mọi bucket đều có cấu hình mã hóa mặc định. Nếu yêu cầu kiểm soát key policy, audit decrypt hoặc dual-layer encryption, chọn SSE-KMS/DSSE-KMS. Encryption mặc định không tự mã hóa lại object cũ đã tồn tại trước khi cấu hình được áp dụng.

### 6.1. Các lựa chọn S3 encryption

| Cơ chế | Key do ai quản lý? | Đặc điểm | Use case |
|---|---|---|---|
| SSE-S3 | Amazon S3 | AES-256, S3 quản lý key và rotation; mặc định cho object mới | Phần lớn workload cần at-rest encryption cơ bản |
| SSE-KMS | AWS KMS key | Kiểm soát key policy/IAM, audit KMS usage, customer-managed key | Dữ liệu nhạy cảm, separation of duties, cross-account access |
| DSSE-KMS | Hai lớp encryption do S3 và KMS quản lý | Dual-layer server-side encryption; tăng lớp bảo vệ theo yêu cầu compliance | Yêu cầu dual-layer encryption |
| SSE-C | Customer-provided key trong mỗi request | S3 không lưu key; caller phải cung cấp đúng key cho mọi request liên quan | Use case có key custody đặc thù; tăng gánh nặng vận hành |
| Client-side encryption | Ứng dụng/customer | Mã hóa trước khi gửi lên S3; S3 chỉ nhận ciphertext | Cần plaintext không xuất hiện tại service hoặc muốn kiểm soát crypto format |

SSE-S3, SSE-KMS và DSSE-KMS đều mã hóa object data ở phía server trước khi lưu xuống disk; không mặc định coi object key, user metadata hoặc thông tin nằm ngoài object body là ciphertext. Không đưa PII/secret vào object key hoặc metadata nếu không có yêu cầu bảo vệ riêng. SSE-C yêu cầu client gửi key qua HTTPS; S3 không lưu key nên mất key sẽ mất khả năng giải mã. Client-side encryption bảo vệ dữ liệu trước khi gửi nhưng ứng dụng phải quản lý key, metadata, decrypt path và tương thích format.

### 6.2. Cấu hình default encryption bằng SSE-S3

Ví dụ đặt default encryption của bucket thành SSE-S3:

~~~json
{
  "Rules": [
    {
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }
  ]
}
~~~

Áp dụng:

~~~bash
aws s3api put-bucket-encryption \
  --bucket company-private-data \
  --server-side-encryption-configuration file://s3-encryption.json
~~~

S3 hiện mặc định SSE-S3 cho mọi bucket/object mới; lệnh này minh họa cách khai báo rõ cấu hình trong IaC hoặc runbook. Cấu hình bucket không tự re-encrypt object cũ. Muốn thay encryption cho object hiện có, phải thực hiện copy/rewrite hoặc batch operation theo kế hoạch.

### 6.3. Cấu hình SSE-KMS và S3 Bucket Key

Ví dụ default encryption dùng customer-managed KMS key:

~~~json
{
  "Rules": [
    {
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "arn:aws:kms:ap-southeast-1:123456789012:key/11111111-2222-3333-4444-555555555555"
      },
      "BucketKeyEnabled": true
    }
  ]
}
~~~

Áp dụng:

~~~bash
aws s3api put-bucket-encryption \
  --bucket company-private-data \
  --server-side-encryption-configuration file://s3-kms-encryption.json
~~~

S3 Bucket Keys có thể giảm số request tới KMS và chi phí SSE-KMS bằng cách dùng bucket-level key để giảm tần suất gọi KMS cho object. Nó không thay đổi encryption boundary của object và không thay thế KMS authorization. Khi Bucket Keys được bật, encryption context mà S3 dùng cho KMS có thể ở phạm vi bucket ARN thay vì object ARN; đánh giá ảnh hưởng đến policy conditions, audit context và khả năng truy vết trước khi bật.

### 6.4. Quyền cần có với SSE-KMS

Để upload object dùng SSE-KMS, principal thường cần:

- Quyền S3 như `s3:PutObject` trên bucket/object.
- Quyền KMS `kms:GenerateDataKey` trên key phù hợp.
- KMS key policy hoặc grant cho phép principal dùng key.

Để tải object về và giải mã, principal thường cần:

- Quyền S3 `s3:GetObject`.
- Quyền KMS `kms:Decrypt`.
- Key policy/grant cho phép principal decrypt.

Multipart upload và một số thao tác khác có thể cần thêm KMS permissions như `kms:Decrypt`. Hãy kiểm tra API/service-specific permissions, không copy một policy mẫu vào production mà chưa xác minh. Nếu key ở account khác, cần cả identity policy ở caller account và key policy ở key-owning account; dùng key ARN khi tham chiếu cross-account.

### 6.5. DSSE-KMS và SSE-C

DSSE-KMS cung cấp hai lớp server-side encryption, một lớp do S3 quản lý và một lớp dùng AWS KMS. Chọn khi yêu cầu compliance/security yêu cầu dual-layer encryption; đánh giá chi phí, service compatibility và giới hạn tính năng trước khi dùng.

SSE-C yêu cầu client gửi customer-provided key qua TLS cho các request cần key. S3 không lưu key và không thể khôi phục nếu key mất. Không đưa key vào command line, shell history, logs hoặc monitoring labels. Với phần lớn hệ thống mới, SSE-KMS hoặc client-side encryption thường dễ quản trị hơn SSE-C.

### 6.6. Kiểm tra encryption của object

Kiểm tra default bucket encryption:

~~~bash
aws s3api get-bucket-encryption \
  --bucket company-private-data
~~~

Kiểm tra metadata của object:

~~~bash
aws s3api head-object \
  --bucket company-private-data \
  --key reports/annual-report.pdf
~~~

Xem các field như `ServerSideEncryption`, `SSEKMSKeyId` và `BucketKeyEnabled` nếu response cung cấp. S3 Inventory cũng có thể xuất encryption status để kiểm tra hàng loạt. Không suy ra object cũ đã được re-encrypt chỉ từ default encryption config.

### 6.7. Enforce encryption policy

Bucket policy có thể từ chối upload nếu request không dùng SSE-KMS hoặc dùng sai KMS key ARN. Ví dụ dưới đây là policy minh họa yêu cầu mọi `PutObject` chỉ dùng một KMS key cụ thể:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyUploadsWithoutApprovedKmsKey",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::company-private-data/*",
      "Condition": {
        "StringNotEqualsIfExists": {
          "s3:x-amz-server-side-encryption": "aws:kms"
        }
      }
    },
    {
      "Sid": "DenyUploadsWithUnapprovedKmsKey",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::company-private-data/*",
      "Condition": {
        "StringNotEqualsIfExists": {
          "s3:x-amz-server-side-encryption-aws-kms-key-id": "arn:aws:kms:ap-southeast-1:123456789012:key/11111111-2222-3333-4444-555555555555"
        }
      }
    }
  ]
}
~~~

Hai statement dùng `StringNotEqualsIfExists` để từ chối nếu client không gửi header hoặc gửi giá trị khác. Vì vậy policy này cố ý yêu cầu client chỉ rõ SSE-KMS và đúng key ARN; request không gửi header sẽ bị từ chối dù bucket có default encryption. Nếu muốn dựa vào default encryption cho request không gửi header, thiết kế policy khác và xác minh object encryption sau upload. Test upload, multipart, replication và service integrations trong sandbox trước khi enforce.

## 7. Mã hóa EBS, RDS, EFS và backup

### 7.1. Amazon EBS

EBS encryption dùng AWS KMS để mã hóa data at rest cho volume và snapshot. Khi tạo encrypted volume, dữ liệu ghi xuống volume, snapshot tạo từ volume và dữ liệu truyền giữa instance với volume được mã hóa theo cơ chế dịch vụ.

- Có thể bật EBS encryption by default theo Region.
- Có thể chọn KMS key mặc định cho các volume mới.
- Snapshot của encrypted volume tiếp tục được mã hóa.
- Copy snapshot có thể chọn KMS key khác để đổi encryption key.
- Không thể chuyển trực tiếp một volume đã tồn tại từ unencrypted sang encrypted bằng cách bật flag; thường cần tạo snapshot/copy hoặc tạo encrypted volume mới rồi migrate dữ liệu.
- Khi attach volume, principal cần quyền KMS phù hợp; EC2/EBS có service integration và grants liên quan.

Kiểm tra cấu hình account/Region:

~~~bash
aws ec2 get-ebs-encryption-by-default \
  --region ap-southeast-1

aws ec2 get-ebs-default-kms-key-id \
  --region ap-southeast-1
~~~

Bật encryption by default:

~~~bash
aws ec2 enable-ebs-encryption-by-default \
  --region ap-southeast-1
~~~

Bật default chỉ áp dụng cho volume mới sau khi cấu hình có hiệu lực; không tự mã hóa volume hiện hữu.

### 7.2. Amazon RDS

RDS encryption at rest dùng KMS key cho underlying storage, automated backups, snapshots và read replicas theo engine/feature support. Một số quy tắc quan trọng:

- Chọn KMS key khi tạo DB instance/cluster; không thể bật encryption tại chỗ cho DB instance chưa mã hóa.
- Để mã hóa database chưa mã hóa, tạo snapshot, copy snapshot với KMS key, rồi restore thành DB instance mới được mã hóa.
- Khi copy snapshot sang Region khác, cần key trong Region đích và quyền sử dụng key tương ứng.
- Automated backups và snapshots kế thừa encryption của database theo hành vi dịch vụ.
- TLS cần được cấu hình riêng cho kết nối database client; at-rest encryption không mã hóa SQL traffic.

### 7.3. Amazon EFS

EFS mã hóa file system data at rest bằng KMS key khi tạo file system. Có thể dùng AWS managed key hoặc customer managed key theo yêu cầu kiểm soát. Đối với encryption in transit, dùng EFS mount helper với TLS khi mount file system. Không nhầm encryption at rest của EFS với TLS mount option.

### 7.4. AWS Backup và bản sao

Backup encryption phụ thuộc resource type và cách backup được tạo. Một số resource backup kế thừa encryption key từ resource nguồn; AWS Backup vault cũng có encryption key cho backup copies theo service support. Khi copy backup cross-account/cross-Region, cần kiểm tra:

- Source key và destination key ở đúng Region/account.
- Key policy/grant cho AWS Backup/service role.
- Destination vault policy và IAM role.
- Restore permissions và quyền decrypt.
- Quy trình key retention/deletion không làm backup không thể restore.

Thực hiện restore test định kỳ. Một backup được mã hóa tốt nhưng không thể giải mã/restore vì key đã disable hoặc bị xóa vẫn là một backup thất bại.

## 8. AWS KMS: key types, policy và quyền sử dụng

### 8.1. AWS owned, AWS managed và customer managed keys

| Loại key | Ai quản lý? | Policy/rotation | Khi nào dùng? |
|---|---|---|---|
| AWS owned key | AWS service sở hữu | Không xem/quản lý trực tiếp trong account; service quyết định | Mã hóa mặc định nội bộ của service |
| AWS managed key | AWS service tạo/quản lý trong account | Key policy do AWS quản lý; rotation tự động hàng năm | Muốn dùng KMS integration nhanh với quyền quản lý hạn chế |
| Customer managed key | Khách hàng tạo/quản lý | Tự quản lý key policy, grants, aliases, rotation, disable/delete | Cần audit, separation, cross-account hoặc custom access control |

Customer managed key cho phép kiểm soát rõ ai có quyền administer key và ai có quyền cryptographic operations. Quyền quản lý key (`kms:EnableKey`, `kms:PutKeyPolicy`, `kms:ScheduleKeyDeletion`) nên tách khỏi quyền sử dụng key (`kms:Encrypt`, `kms:Decrypt`, `kms:GenerateDataKey`).

### 8.2. Key policy và IAM policy

KMS key policy là resource policy chính, xác định ai có thể sử dụng/quản lý KMS key. IAM policy chỉ có hiệu lực cấp quyền KMS khi key policy cho phép IAM policies trong account tham gia authorization, hoặc thông qua grants. Không thể giả định attach `kms:Decrypt` IAM policy là đủ cho mọi KMS key.

Các thành phần:

- **Key policy:** quyền gốc trên KMS key.
- **IAM identity policy:** quyền của user/role nếu key policy cho phép IAM authorization.
- **Grant:** cấp quyền cryptographic operation cho principal/service trong phạm vi xác định.
- **Permissions boundary/SCP:** giới hạn quyền tối đa, không cấp thêm quyền.
- **Encryption context conditions:** ràng buộc operation theo context nếu use case hỗ trợ.

Ví dụ key policy statement cho một application role được phép dùng key qua S3 trong một Region:

~~~json
{
  "Sid": "AllowOrdersRoleThroughS3",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::123456789012:role/OrdersApplicationRole"
  },
  "Action": [
    "kms:GenerateDataKey",
    "kms:Decrypt"
  ],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "kms:ViaService": "s3.ap-southeast-1.amazonaws.com"
    }
  }
}
~~~

Đây là statement minh họa cho key policy; cần bổ sung key administration statement và điều kiện resource/encryption context phù hợp với bucket/object. `kms:ViaService` giới hạn operation được gọi qua S3 ở Region đã nêu. Khi dùng S3 Bucket Keys hoặc cross-account access, xác minh encryption context và principal behavior thực tế trước khi thêm condition.

### 8.3. Least privilege cho decrypt

Không cấp `kms:*` cho toàn bộ application roles. Tách theo hành vi:

- Upload/encrypt role: `kms:GenerateDataKey` hoặc `kms:Encrypt` khi cần.
- Download/decrypt role: `kms:Decrypt`.
- Key administrator: quản lý policy, rotation, disable và deletion schedule; không nhất thiết được decrypt dữ liệu.
- Audit role: đọc metadata/CloudTrail, không nhất thiết có decrypt.
- Backup/restore role: quyền KMS và service actions đúng với restore workflow.

Với resource policies và cross-account use, principal ở account khác thường cần identity policy trong account của họ và key policy ở account sở hữu key cho phép access. Tránh `Principal: "*"` hoặc wildcard resource/conditions quá rộng.


## 9. Encryption in transit với TLS và chứng chỉ

TLS (Transport Layer Security) bảo vệ dữ liệu truyền giữa hai endpoint. HTTPS là HTTP chạy trên TLS. TLS cung cấp confidentiality, integrity và xác thực server dựa trên certificate; mutual TLS (mTLS) có thể xác thực cả client lẫn server khi ứng dụng cần identity ở tầng transport.

### 9.1. TLS handshake ở mức khái niệm

1. Client gửi ClientHello với TLS versions, cipher suites và các tham số handshake hỗ trợ.
2. Server trả ServerHello và certificate chain.
3. Client xác minh certificate chain, hostname, validity period và trust anchor.
4. Hai bên hoàn tất key exchange để tạo session keys.
5. Application data được truyền bằng symmetric authenticated encryption.

TLS 1.2 và TLS 1.3 đều được sử dụng rộng rãi. Ưu tiên TLS 1.2 trở lên, tắt protocol/cipher yếu theo compatibility requirements và cập nhật TLS libraries. Không bỏ qua hostname validation hoặc chấp nhận self-signed certificate ngoài trust model đã được phê duyệt.

### 9.2. AWS Certificate Manager

AWS Certificate Manager (ACM) cấp và quản lý TLS certificates cho các dịch vụ AWS tích hợp như Application Load Balancer, CloudFront, API Gateway và một số endpoint khác. ACM hỗ trợ public certificates và private certificates qua ACM Private CA.

- Public certificate được dùng cho hostname public; cần xác minh domain ownership bằng DNS hoặc email theo phương thức hỗ trợ.
- ACM tự động gia hạn public certificates đủ điều kiện khi certificate vẫn được sử dụng bởi dịch vụ tích hợp và validation conditions còn đáp ứng.
- Imported certificates không được ACM tự động gia hạn; owner phải theo dõi expiry và import certificate mới.
- Private CA phù hợp cho internal PKI, private services và mTLS; cần quản lý CA hierarchy, issuance policy, revocation và chi phí.
- Certificate trong ACM có phạm vi Region đối với phần lớn dịch vụ regional; CloudFront certificate phải được tạo/import tại Region mà CloudFront yêu cầu (us-east-1).

Không coi certificate là secret API key. Certificate public có thể công khai; private key phải được bảo vệ. Không commit private key hoặc keystore password vào source control.

### 9.3. TLS cho các dịch vụ AWS

| Kết nối | Biện pháp |
|---|---|
| Browser → CloudFront/ALB/API Gateway | HTTPS listener/custom domain với ACM certificate |
| Service → S3 | HTTPS/TLS, bucket policy từ chối HTTP |
| Application → RDS/Aurora | TLS database connection, verify server certificate/hostname theo driver |
| EC2/ECS/EKS → internal service | HTTPS/TLS hoặc mTLS theo trust model |
| Client → EFS | EFS mount helper với TLS |
| Service → AWS API | AWS SDK/CLI HTTPS endpoint; giữ certificate validation bật |

VPC, subnet private, security group và VPC endpoint giúp kiểm soát network reachability. Chúng không thay thế TLS nếu yêu cầu confidentiality/integrity trên transport.

### 9.4. Enforce HTTPS trên S3

Bucket policy có thể từ chối mọi request không dùng HTTPS:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::company-private-data",
        "arn:aws:s3:::company-private-data/*"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    }
  ]
}
~~~

Có thể giới hạn TLS version tối thiểu bằng condition key `s3:TlsVersion`. Ví dụ sau từ chối TLS thấp hơn 1.2:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyOldTls",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::company-private-data",
        "arn:aws:s3:::company-private-data/*"
      ],
      "Condition": {
        "NumericLessThan": {
          "s3:TlsVersion": "1.2"
        }
      }
    }
  ]
}
~~~

Test policy với clients, replication, logging, AWS service integrations và VPC endpoints trước khi áp dụng production. TLS enforcement có thể làm client cũ hoặc integration dùng protocol không đáp ứng bị từ chối.

### 9.5. TLS cho RDS

RDS/Aurora có certificate authority bundles để client xác minh server certificate. Cấu hình driver/JDBC connection string để yêu cầu TLS và verify server identity; với PostgreSQL/MySQL, tham số cụ thể tùy engine và driver. Không chỉ bật TLS ở server mà bỏ qua certificate validation ở client.

Với Java, sử dụng JDBC driver được cập nhật, trust store chứa CA bundle phù hợp và cấu hình SSL mode/verify-full tương ứng với engine. Khi AWS rotate RDS server certificates, cập nhật CA bundle và test kết nối trước thời điểm cutover.

## 10. KMS key rotation và key lifecycle

Rotation làm giảm thời gian sử dụng một phiên bản cryptographic key material, nhưng không thay thế key access review, incident response hay data re-encryption. Cần phân biệt rotation material bên trong cùng logical KMS key với migration sang một KMS key mới.

### 10.1. Automatic rotation

AWS KMS hỗ trợ automatic rotation cho customer managed symmetric encryption keys có key material do AWS KMS tạo (`Origin = AWS_KMS`). Khi bật rotation:

- Mặc định KMS tạo key material mới mỗi 365 ngày.
- Có thể chọn rotation period từ 90 đến 2.560 ngày.
- Key ID, ARN, policy, alias và permissions của logical KMS key không đổi.
- Khi decrypt ciphertext cũ, KMS tự chọn key material cũ phù hợp.
- AWS managed keys được AWS tự động rotate hàng năm; customer managed keys cần bật rotation nếu muốn.
- AWS owned keys do service sở hữu và quyết định rotation.

Automatic rotation không hỗ trợ asymmetric keys, HMAC keys, imported key material hoặc custom key stores; các trường hợp này cần quy trình manual rotation phù hợp.

AWS KMS cũng hỗ trợ on-demand rotation cho symmetric encryption keys có key material do AWS KMS tạo hoặc imported key material. On-demand rotation không thay đổi lịch automatic rotation đã cấu hình. Asymmetric/HMAC keys và custom key stores cần quy trình manual rotation hoặc migration theo loại key.

Bật rotation:

~~~bash
aws kms enable-key-rotation \
  --key-id alias/app-data-key \
  --rotation-period-in-days 365 \
  --region ap-southeast-1
~~~

Kiểm tra:

~~~bash
aws kms get-key-rotation-status \
  --key-id alias/app-data-key \
  --region ap-southeast-1
~~~

### 10.2. Rotation khác migration sang key mới

| Tình huống | Logical key ARN | Dữ liệu cũ | Hành động |
|---|---|---|---|
| KMS automatic rotation | Không đổi | KMS giữ key material cũ để decrypt | Không cần sửa ciphertext chỉ vì rotation |
| On-demand rotation | Không đổi | Vẫn decrypt bằng material phù hợp | Theo dõi CloudTrail/rotation status |
| Chuyển sang KMS key mới | Thay đổi | Ciphertext vẫn cần key cũ cho đến khi re-encrypt | ReEncrypt data keys hoặc copy/rewrite resource |
| Lộ key/compromise | Có thể cần thay key/policy và re-encrypt | Đánh giá data exposure và key access | Incident response, containment, migration |

Khi chuyển sang KMS key mới, không xóa key cũ trước khi xác nhận tất cả ciphertext, snapshots, backups, replicas và archives đã được re-encrypt hoặc không còn cần. `ReEncrypt` có thể re-encrypt ciphertext/key material từ KMS key nguồn sang key đích mà không trả plaintext về caller; với envelope encryption, có thể chỉ cần re-wrap encrypted data key nếu application format hỗ trợ.

### 10.3. Disable, schedule deletion và recovery

- `DisableKey` ngăn cryptographic operations mới dùng key nhưng không xóa key material.
- `ScheduleKeyDeletion` đặt pending deletion period; trong thời gian chờ có thể cancel deletion.
- Khi key bị xóa vĩnh viễn, dữ liệu chỉ còn ciphertext được bảo vệ bởi key đó có thể không thể giải mã.
- Alias chỉ là tên tham chiếu; đổi alias không tự re-encrypt data.
- Rotation không giải quyết key compromise nếu attacker đã lấy plaintext data key hoặc plaintext dữ liệu.

Không schedule deletion key đang được resource, backup, log archive hoặc application sử dụng nếu chưa có inventory và restore test.

## 11. Chọn mô hình mã hóa theo yêu cầu

| Nhu cầu | Lựa chọn thường phù hợp | Điểm cần kiểm tra |
|---|---|---|
| S3 object cần encryption mặc định, ít vận hành | SSE-S3 | Bucket/object encryption status |
| S3 dữ liệu nhạy cảm cần audit key usage | SSE-KMS với customer managed key | Key policy, KMS cost, decrypt role |
| S3 cần dual-layer encryption | DSSE-KMS | Service compatibility, cost, compliance |
| Application tự mã hóa trước khi lưu | AWS Encryption SDK + KMS keyring | Data key lifecycle, message format, context |
| EBS volume/snapshot | EBS encryption với KMS | Default encryption, snapshot copy, restore |
| RDS database | RDS encryption at creation + TLS client | Snapshot migration, CA bundle, DB engine |
| EFS file system | KMS at rest + TLS mount | Key access và mount helper |
| Public API endpoint | ACM certificate + HTTPS/TLS | DNS validation, renewal, TLS policy |
| Internal service mTLS | Private CA + client/server certificates | Trust distribution, rotation, revocation |
| Dữ liệu cần archive dài hạn | SSE-KMS/S3 + retention/restore plan | Không xóa key trước archive lifecycle |

Không chọn encryption algorithm chỉ theo nhãn “AES-256”. Cần xác định threat model, ai nắm key, ai có quyền decrypt, ciphertext nằm ở đâu, key có thể rotate/disable không, và dữ liệu phải khôi phục được trong bao lâu.


## 12. Troubleshooting encryption và KMS

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| S3 AccessDenied khi upload SSE-KMS | Thiếu s3:PutObject, kms:GenerateDataKey hoặc key policy không cho phép | IAM policy, KMS key policy/grant, bucket policy |
| S3 AccessDenied khi download | Thiếu s3:GetObject hoặc kms:Decrypt | Object key ARN, key state, key policy và cross-account permissions |
| KMSInvalidStateException | Key disabled, pending deletion hoặc state không hỗ trợ operation | DescribeKey, key state, deletion schedule |
| InvalidCiphertextException | EDK sai/hỏng, dùng sai KMS key hoặc encryption context không khớp | Ciphertext blob, key ARN, context exact/case-sensitive |
| Ứng dụng không giải mã được sau key rotation | Nhầm rotation material với key migration hoặc key cũ đã bị xóa | Key ID/ARN, key material retention, ciphertext metadata |
| S3 object cũ vẫn dùng encryption cũ | Default encryption chỉ áp dụng object mới | HeadObject, S3 Inventory, copy/rewrite plan |
| EBS volume không attach | Principal/service không có KMS grant/permission hoặc key disabled | KMS key state, grants, CloudTrail, EC2 events |
| RDS snapshot copy thất bại | Thiếu quyền decrypt/encrypt hoặc key ở sai Region | Source/destination key policy, snapshot Region, IAM role |
| TLS handshake failure | TLS version/cipher không tương thích, trust chain hoặc hostname sai | Client/server TLS logs, CA bundle, certificate SAN/expiry |
| ACM certificate không renew | Domain validation record mất hoặc certificate không còn được dùng đúng cách | ACM renewal status, DNS validation, integrated service |
| Client kết nối S3 bị deny | HTTP bị bucket policy từ chối hoặc TLS thấp hơn minimum | aws:SecureTransport, s3:TlsVersion, client TLS version |

### 12.1. Kiểm tra KMS key metadata

~~~bash
aws kms describe-key \
  --key-id alias/app-data-key \
  --region ap-southeast-1

aws kms get-key-policy \
  --key-id alias/app-data-key \
  --policy-name default \
  --region ap-southeast-1

aws kms list-grants \
  --key-id alias/app-data-key \
  --region ap-southeast-1
~~~

Xác minh key ARN, key state, key usage, origin, multi-Region property và key policy. Với service integration, kiểm tra grants được tạo cho service principal/resource.

### 12.2. Kiểm tra rotation

~~~bash
aws kms get-key-rotation-status \
  --key-id alias/app-data-key \
  --region ap-southeast-1

aws kms list-key-rotations \
  --key-id alias/app-data-key \
  --region ap-southeast-1
~~~

`GetKeyRotationStatus` cho biết automatic rotation status; `ListKeyRotations` cho biết lịch sử rotation đã hoàn tất nếu key hỗ trợ API này. Không kết luận key đã được rotate chỉ vì policy yêu cầu rotation; phải kiểm tra trạng thái thực tế.

### 12.3. Điều tra bằng CloudTrail

CloudTrail ghi lại các KMS API calls như `GenerateDataKey`, `Decrypt`, `Encrypt`, `ReEncrypt`, `DisableKey`, `PutKeyPolicy` và rotation operations. Khi điều tra:

1. Xác định `eventTime`, `eventSource = kms.amazonaws.com`, `eventName`.
2. Đọc `userIdentity` để xác định role/user/service.
3. Xem key ID/ARN và encryption context nếu có.
4. Kiểm tra `errorCode`/`errorMessage` để phân biệt authorization, invalid state và ciphertext/context errors.
5. Correlate với S3/EBS/RDS/Secrets Manager event và application logs.
6. Không log plaintext key hoặc secret khi debug.

## 13. Lỗi thiết kế thường gặp

### 13.1. Cho rằng encryption mặc định giải quyết mọi rủi ro

S3 SSE-S3 bảo vệ object at rest nhưng không ngăn principal có `s3:GetObject` tải plaintext. KMS encryption cũng không thay authorization. Cần bucket policy, IAM least privilege, access point policy, logging và data classification.

### 13.2. Lưu plaintext data key quá lâu

Plaintext data key chỉ cần tồn tại trong thời gian mã hóa/giải mã. Không cache không giới hạn, không ghi log và không truyền qua queue/output. Nếu ứng dụng cần cache, đặt TTL, giới hạn scope, bảo vệ memory và đánh giá rủi ro.

### 13.3. Đưa dữ liệu nhạy cảm vào encryption context

Encryption context xuất hiện plaintext trong CloudTrail. Chỉ dùng non-secret identifiers như Application, Environment, RecordType hoặc opaque resource ID đã được đánh giá; không dùng PII hoặc credential.

### 13.4. Dùng một KMS key cho mọi workload

Một key dùng chung có thể tạo blast radius lớn và làm khó separation of duties. Phân chia key theo data classification, account, environment hoặc workload khi cần; tránh tạo quá nhiều key không có owner/lifecycle.

### 13.5. Xóa key trước khi kiểm tra backup

KMS key bị xóa vĩnh viễn có thể khiến snapshot, object và backup không thể giải mã. Trước khi disable/schedule deletion, inventory mọi resource dùng key, test restore và xác minh thời gian retention.

### 13.6. Coi private subnet là encryption in transit

Traffic trong private VPC vẫn có thể bị quan sát/tamper bởi endpoint hoặc workload đã compromise. Dùng TLS/mTLS theo threat model và verify certificates ở client.

### 13.7. Tự xây cryptographic format

Tự chọn nonce, key derivation, serialization, authentication tag hoặc rotation format dễ tạo lỗi khó phát hiện. Dùng AWS Encryption SDK hoặc native service encryption; nếu bắt buộc tự triển khai, cần cryptographic design review chuyên môn và test interoperability.

## 14. Bài thực hành trên AWS sandbox

### 14.1. Lab A — S3 SSE-S3 và SSE-KMS

1. Tạo bucket sandbox riêng.
2. Kiểm tra default encryption hiện tại bằng get-bucket-encryption.
3. Upload một object test và kiểm tra head-object.
4. Tạo customer managed symmetric KMS key trong cùng Region.
5. Cấu hình bucket default encryption thành SSE-KMS và bật Bucket Key.
6. Upload object khác; kiểm tra ServerSideEncryption, SSEKMSKeyId và BucketKeyEnabled.
7. Dùng role thiếu kms:Decrypt thử tải object; quan sát AccessDenied.
8. Cấp quyền đúng trong sandbox và xác minh download thành công.

### 14.2. Lab B — Envelope encryption với KMS

1. Tạo symmetric customer managed KMS key và alias.
2. Tạo một ứng dụng test dùng AWS SDK hoặc AWS Encryption SDK.
3. Gọi GenerateDataKey với AES_256 và encryption context không nhạy cảm.
4. Dùng SDK mã hóa plaintext test và lưu ciphertext cùng encrypted data key.
5. Xóa plaintext data key khỏi memory sau encryption.
6. Đọc record, gọi Decrypt với đúng context và giải mã payload.
7. Thử thay đổi một field trong context; xác nhận decrypt thất bại.
8. Thử role không có kms:Decrypt; xác nhận authorization bị từ chối.

### 14.3. Lab C — TLS enforcement cho S3

1. Tạo bucket sandbox và upload object test.
2. Thêm bucket policy từ chối request khi aws:SecureTransport = false.
3. Dùng HTTPS client truy cập object và xác minh thành công.
4. Thử HTTP nếu endpoint/client cho phép; xác nhận bị deny.
5. Kiểm tra CloudTrail event tlsDetails nếu có.
6. Thử policy minimum TLS version trong sandbox sau khi xác minh client compatibility.

### 14.4. Lab D — EBS encryption by default

1. Chọn sandbox Region và kiểm tra EBS encryption by default.
2. Bật default encryption và chỉ định KMS key nếu lab yêu cầu.
3. Tạo EBS volume test.
4. Kiểm tra Encrypted và KmsKeyId bằng describe-volumes.
5. Tạo snapshot và kiểm tra encryption.
6. Copy snapshot sang key khác nếu cần minh họa key migration.
7. Không thử disable/delete key đang bảo vệ resource cần giữ.

### 14.5. Lab E — KMS rotation

1. Tạo customer managed symmetric KMS key có origin AWS_KMS.
2. Bật automatic rotation với period mặc định hoặc period phù hợp sandbox.
3. Dùng get-key-rotation-status xác nhận trạng thái.
4. Ghi nhận key ARN không đổi khi rotation material.
5. Giải mã ciphertext đã tạo trước rotation để xác minh KMS vẫn dùng material phù hợp.
6. So sánh với migration sang một KMS key mới: re-encrypt/rewrap data key và kiểm tra ciphertext.
7. Không schedule deletion key cho tới khi hoàn tất kiểm tra restore.

### 14.6. Lab F — ACM và TLS endpoint

1. Có một domain test và quyền tạo DNS validation record.
2. Request public certificate bằng ACM trong Region phù hợp với dịch vụ.
3. Validate domain ownership.
4. Attach certificate vào ALB listener hoặc API Gateway custom domain.
5. Kiểm tra HTTPS, hostname và certificate chain bằng browser/openssl s_client.
6. Xác minh TLS version và expiry; xem ACM renewal status.
7. Không dùng private key/certificate của production cho lab.

## 15. Checklist review encryption trước khi production

### Data classification và architecture

- [ ] Đã phân loại dữ liệu và xác định confidentiality/integrity requirements?
- [ ] Đã xác định dữ liệu ở rest, in transit và in use?
- [ ] Chọn server-side hay client-side encryption có lý do?
- [ ] Đã xác định ai cần decrypt và ở account/Region nào?
- [ ] Đã tính đến snapshots, replicas, backups, exports và archives?

### Key management

- [ ] Key type/origin/Region phù hợp use case?
- [ ] Key policy, IAM policy và grants được review?
- [ ] Encrypt/decrypt/admin roles được tách theo least privilege?
- [ ] Encryption context chỉ chứa non-secret metadata?
- [ ] Rotation policy phù hợp loại key?
- [ ] Có inventory trước khi disable/schedule deletion?
- [ ] Cross-account/cross-Region permissions được kiểm tra?

### At rest

- [ ] S3 default encryption đúng SSE-S3/SSE-KMS/DSSE-KMS?
- [ ] Object cũ đã được inventory và re-encrypt nếu yêu cầu?
- [ ] SSE-KMS key policy cho phép đúng service/principal?
- [ ] EBS/RDS/EFS encryption được bật khi tạo resource?
- [ ] Snapshot/backup copy giữ encryption đúng?
- [ ] Có restore test và key recovery plan?

### In transit

- [ ] HTTPS/TLS được enforce trên public/internal endpoints cần thiết?
- [ ] TLS minimum version/cipher policy phù hợp?
- [ ] Certificate hostname, chain và expiry được kiểm tra?
- [ ] ACM renewal status và DNS validation được theo dõi?
- [ ] Database clients xác minh certificate thay vì chỉ bật TLS?
- [ ] Không dùng HTTP hoặc bỏ qua certificate validation?

### Operations

- [ ] Plaintext data keys/secrets/private keys không vào logs/artifacts?
- [ ] CloudTrail theo dõi KMS/key policy/rotation operations?
- [ ] Có alert cho key disable, deletion schedule và policy changes?
- [ ] Có runbook xử lý AccessDenied, invalid ciphertext và TLS errors?
- [ ] Có lịch review key owners, grants, rotation và restore readiness?

## 16. Câu hỏi tự đánh giá

1. Encryption at rest, in transit và in use khác nhau thế nào?
2. Encryption có thay thế IAM authorization không?
3. Symmetric và asymmetric encryption khác nhau ở đâu?
4. AES-GCM cung cấp những thuộc tính nào?
5. Hash và digital signature khác encryption thế nào?
6. KMS key khác data key ra sao?
7. Envelope encryption giải quyết vấn đề nào?
8. GenerateDataKey trả về những giá trị nào?
9. Vì sao ứng dụng phải xóa plaintext data key khỏi memory?
10. Encrypted data key được lưu cùng ciphertext để làm gì?
11. Encryption context là gì và có phải secret không?
12. Vì sao encryption context phải khớp chính xác khi decrypt?
13. Vì sao không đưa PII/secret vào encryption context?
14. AWS Encryption SDK hỗ trợ envelope encryption như thế nào?
15. SSE-S3, SSE-KMS và DSSE-KMS khác nhau ở đâu?
16. S3 SSE-S3 mặc định áp dụng cho object mới từ thời điểm nào?
17. Default bucket encryption có tự mã hóa object cũ không?
18. SSE-C có rủi ro vận hành nào nếu mất customer key?
19. Upload/download S3 SSE-KMS thường cần những KMS permissions nào?
20. S3 Bucket Keys giúp giảm chi phí nào?
21. EBS encryption by default có mã hóa volume đã tồn tại không?
22. Vì sao RDS database chưa mã hóa cần snapshot/copy/restore để bật encryption?
23. EFS at-rest encryption khác TLS mount như thế nào?
24. AWS owned, AWS managed và customer managed KMS keys khác nhau ra sao?
25. Vì sao key policy là thành phần quan trọng trong KMS authorization?
26. Khi nào cần cross-account key policy cùng IAM identity policy?
27. Automatic KMS key rotation hỗ trợ những loại key nào?
28. Default KMS automatic rotation period là bao lâu và custom range hiện tại là bao nhiêu?
29. Automatic rotation khác migration sang key mới thế nào?
30. Vì sao xóa KMS key có thể làm backup không thể restore?
31. TLS handshake xác minh điều gì?
32. ACM hỗ trợ quản lý certificate cho những dịch vụ nào?
33. Vì sao imported certificate không được ACM tự động gia hạn?
34. aws:SecureTransport và s3:TlsVersion dùng để enforce điều gì?
35. Vì sao private subnet không tự đảm bảo encryption in transit?
36. Cần kiểm tra gì khi TLS handshake hoặc certificate validation thất bại?

### Định hướng đáp án

- **At rest/in transit/in use:** storage encryption, TLS transport và memory/workload isolation bảo vệ các trạng thái khác nhau.
- **Envelope:** KMS bảo vệ data key; data key mã hóa payload; lưu encrypted data key cùng ciphertext; plaintext key chỉ tồn tại ngắn trong memory.
- **S3:** SSE-S3 mặc định cho object mới; SSE-KMS có KMS authorization/audit; DSSE-KMS có dual-layer; SSE-C đòi hỏi caller bảo vệ key.
- **KMS authorization:** key policy là nền tảng; IAM/grants bổ sung quyền theo cấu hình key policy; least privilege và separation of duties.
- **Rotation:** automatic rotation thay key material trong cùng logical key; migration sang key mới cần re-encrypt/rewrap và giữ key cũ cho đến khi dữ liệu không còn phụ thuộc.
- **TLS/ACM:** HTTPS bảo vệ channel; client phải validate certificate/hostname; ACM gia hạn certificate đủ điều kiện được tích hợp, imported certificates cần owner quản lý.

## 17. Tài liệu AWS chính thức

1. [AWS KMS key concepts](https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html) — KMS keys, data keys, key material và key hierarchy.
2. [Generate data keys](https://docs.aws.amazon.com/kms/latest/developerguide/data-keys.html) — GenerateDataKey, plaintext/encrypted data key và decrypt flow.
3. [GenerateDataKey API](https://docs.aws.amazon.com/kms/latest/APIReference/API_GenerateDataKey.html) — Request, key spec và encryption context.
4. [Encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html) — AAD, CloudTrail visibility và policy constraints.
5. [AWS Encryption SDK concepts](https://docs.aws.amazon.com/encryption-sdk/latest/developer-guide/concepts.html) — Envelope encryption, keyrings và algorithm suites.
6. [AWS Encryption SDK supported algorithm suites](https://docs.aws.amazon.com/encryption-sdk/latest/developer-guide/supported-algorithms.html) — AES-GCM, key derivation, signatures và key commitment.
7. [Protecting data with encryption in Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingEncryption.html) — SSE-S3, SSE-KMS, DSSE-KMS, SSE-C và client-side options.
8. [Configuring default S3 bucket encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/default-bucket-encryption.html) — Default encryption behavior và bucket configuration.
9. [S3 server-side encryption with AWS KMS](https://docs.aws.amazon.com/AmazonS3/latest/userguide/specifying-kms-encryption.html) — SSE-KMS permissions và configuration.
10. [S3 Bucket Keys](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-key.html) — Giảm KMS request volume/cost cho SSE-KMS.
11. [Protecting data in transit with Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingEncryptionInTransit.html) — TLS 1.2/1.3, aws:SecureTransport và s3:TlsVersion.
12. [Amazon EBS encryption](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-encryption.html) — Volume/snapshot encryption và KMS integration.
13. [Amazon RDS encrypted DB instances](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.Encryption.html) — RDS storage, snapshot và migration encryption.
14. [Amazon EFS encryption](https://docs.aws.amazon.com/efs/latest/ug/encryption.html) — At-rest encryption và KMS key.
15. [Rotate AWS KMS keys](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html) — Automatic/on-demand/manual rotation và key material.
16. [Enable automatic KMS key rotation](https://docs.aws.amazon.com/kms/latest/developerguide/rotating-keys-enable.html) — Rotation period và supported key types.
17. [KMS key policies](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html) — Key policy, IAM authorization và grants.
18. [AWS Certificate Manager User Guide](https://docs.aws.amazon.com/acm/latest/userguide/acm-overview.html) — Public/private certificates, integrations và renewal.
19. [ACM managed renewal](https://docs.aws.amazon.com/acm/latest/userguide/managed-renewal.html) — Điều kiện và quy trình tự động gia hạn.
20. [Amazon RDS SSL/TLS connections](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html) — TLS, CA certificates và client configuration.

> **Ghi nhớ cuối bài:** Mã hóa at rest bảo vệ dữ liệu trên storage; TLS bảo vệ dữ liệu trên đường truyền; envelope encryption dùng data key để mã hóa payload và KMS key để bảo vệ data key. Phân quyền decrypt, encryption context, key rotation, certificate validation, backup restore và key lifecycle quyết định hệ thống có vừa an toàn vừa khôi phục được hay không.

