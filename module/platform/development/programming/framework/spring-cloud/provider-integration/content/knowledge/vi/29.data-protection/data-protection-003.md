# Mã hóa phía máy chủ, phía ứng dụng và quản lý khóa

Một ứng dụng Spring Boot lưu đơn hàng, hồ sơ khách hàng hoặc tài liệu lên dịch vụ managed cần trả lời ba câu hỏi: **dữ liệu được mã hóa ở đâu**, **ai nắm quyền kiểm soát khóa**, và **ai có thể đọc dữ liệu sau khi lưu**. Chỉ bật mã hóa mặc định của object storage hoặc database chưa chắc bảo vệ dữ liệu khỏi mọi principal có quyền đọc dịch vụ. Ngược lại, tự mã hóa mọi byte trong ứng dụng cũng tạo thêm trách nhiệm quản lý khóa, version, backup và khôi phục.

Ba mô hình thường gặp là **server-side encryption (SSE)**, **client-side encryption (CSE)** và **envelope encryption**. SSE để dịch vụ lưu trữ mã hóa dữ liệu khi ghi xuống media; CSE mã hóa dữ liệu trong ứng dụng trước khi gửi; envelope encryption dùng một khóa dữ liệu ngắn hạn (DEK) để mã hóa payload và một khóa quản lý (KEK) trong KMS để bảo vệ DEK. Các cloud provider cung cấp dịch vụ quản lý khóa riêng, nhưng nguyên tắc thiết kế và trách nhiệm của ứng dụng vẫn cần được hiểu rõ.

Bài thuộc chương **Bảo vệ dữ liệu** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud, bao gồm danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử và đánh giá khác biệt giữa các cloud provider. Trọng tâm bài là chọn mô hình mã hóa theo threat model, tích hợp KMS/Key Vault/Cloud KMS và thiết kế vòng đời khóa an toàn.

## 1. Mục tiêu học tập và tình huống xuyên suốt

Sau bài này, bạn có thể:

1. Phân biệt mã hóa khi truyền, mã hóa khi lưu, SSE, CSE và envelope encryption.
2. Giải thích sự khác nhau giữa provider-managed key, customer-managed key (CMK), customer-provided key và application-managed key.
3. Chọn SSE hay CSE theo dữ liệu, yêu cầu compliance, quyền truy cập và khả năng tìm kiếm.
4. Thiết kế envelope encryption với AES-GCM, DEK, KEK và authenticated additional data.
5. Dùng AWS KMS, Azure Key Vault Keys hoặc Google Cloud KMS để wrap/unwrap DEK.
6. Cấp quyền tối thiểu cho workload và tách quyền runtime khỏi quyền quản trị khóa.
7. Lập kế hoạch key rotation, rewrapping, disable, recovery và destruction.
8. Kiểm thử ciphertext, integrity, key version, quyền decrypt và log để tránh lộ plaintext.

Tình huống: `document-service` lưu hợp đồng PDF và thông tin nhạy cảm của khách hàng. File được lưu ở object storage, metadata được lưu trong database, ứng dụng chạy trên Kubernetes và có thể triển khai ở AWS, Azure hoặc Google Cloud.

| Dữ liệu | Mục tiêu bảo vệ |
| --- | --- |
| PDF hợp đồng | Không để người có quyền đọc bucket nhưng không có quyền ứng dụng tự giải mã nội dung |
| Metadata không nhạy cảm | Dùng SSE/TDE của dịch vụ managed để bảo vệ media |
| Mã định danh khách hàng | Có thể cần CSE ở cấp trường nếu DBA/operator không được đọc plaintext |
| DEK | Không lưu plaintext cùng ciphertext; chỉ giữ bản đã wrap bằng KMS |
| KEK | Lưu và quản lý trong KMS/Key Vault; giới hạn quyền unwrap/decrypt |

~~~mermaid
flowchart TD
    A["Spring Boot document-service"] --> B["Sinh DEK cho một object"]
    B --> C["AES-256-GCM mã hóa payload"]
    B --> D["KMS / Key Vault / Cloud KMS wrap DEK"]
    C --> E["Ciphertext + nonce + tag"]
    D --> F["Wrapped DEK + key reference"]
    E --> G["Object storage"]
    F --> G
    G --> H["Khi đọc: lấy wrapped DEK"]
    H --> I["KMS unwrap DEK"]
    I --> J["AES-GCM xác minh tag và giải mã"]
    J --> K["Plaintext chỉ trong phạm vi ứng dụng được phép"]
~~~

**Nguyên tắc cốt lõi:** KMS bảo vệ và kiểm soát khóa; thuật toán mã hóa bảo vệ dữ liệu; IAM/RBAC quyết định workload nào được yêu cầu thao tác với khóa. Ba lớp phải được thiết kế cùng nhau.

## 2. Mã hóa khi truyền và mã hóa khi lưu

### 2.1. Encryption in transit

Mã hóa khi truyền bảo vệ dữ liệu trên đường mạng, thường dùng TLS 1.2/1.3. Ví dụ:

- Spring Boot gọi HTTPS tới S3, Azure Blob Storage hoặc Google Cloud Storage.
- SDK lấy token OAuth từ Microsoft Entra ID hoặc gọi KMS API.
- Service-to-service giao tiếp qua mTLS nếu cần xác minh cả hai phía.

TLS bảo vệ request/response trên đường truyền, nhưng khi request tới service và được xử lý, service có thể nhìn thấy plaintext tùy mô hình. TLS không thay thế mã hóa dữ liệu trong storage.

### 2.2. Encryption at rest

Mã hóa khi lưu bảo vệ dữ liệu trên media, snapshot hoặc backup. Dịch vụ managed có thể tự động mã hóa dữ liệu trước khi ghi xuống storage:

- Object storage mã hóa object và bản sao lưu.
- Database dùng Transparent Data Encryption (TDE) hoặc cơ chế encryption at rest.
- Disk/volume được mã hóa ở lớp block storage.

SSE/TDE thường **minh bạch với ứng dụng**: ứng dụng gửi plaintext qua TLS, service mã hóa khi lưu và giải mã khi principal được phép đọc. Điều này bảo vệ media bị đánh cắp hoặc bản backup bị truy cập ngoài dịch vụ, nhưng không tự ngăn một principal có quyền đọc dữ liệu qua API.

### 2.3. Encryption at application layer

CSE mã hóa payload **trước khi gửi tới storage hoặc database**. Dịch vụ lưu trữ nhận ciphertext, không có khóa giải mã ứng dụng nên không thể đọc plaintext.

CSE có thể bảo vệ trước một số rủi ro như:

- Operator có quyền đọc object nhưng không có quyền unwrap DEK.
- Snapshot/backup bị sao chép ra khỏi hệ thống.
- Storage account hoặc bucket bị truy cập trái phép nhưng attacker không có KMS permission.
- Một số trường dữ liệu cần mã hóa ở mức field để giảm phạm vi người có thể đọc.

CSE không che giấu mọi metadata: object name, kích thước, thời gian, tenant identifier, access pattern và metadata không mã hóa vẫn có thể lộ. Cần thiết kế cả tên object và metadata nếu chúng nhạy cảm.

## 3. Server-side encryption (SSE)

### 3.1. Luồng hoạt động

~~~text
Spring Boot
    |
    | plaintext qua HTTPS/TLS
    v
Object storage / database service
    |
    | service mã hóa khi ghi
    v
Encrypted media / snapshot / backup
    |
    | service giải mã khi principal được phép đọc
    v
Plaintext response qua TLS
~~~

Với SSE, ứng dụng không cần tự sinh DEK cho từng object. Dịch vụ lưu trữ hoặc database quản lý việc mã hóa/giải mã và tương tác với KMS nếu chọn customer-managed key.

### 3.2. Các lựa chọn khóa

| Lựa chọn | Ai quản lý key material? | Mức kiểm soát |
| --- | --- | --- |
| Provider-managed key | Cloud provider | Dễ vận hành; ít quyền kiểm soát vòng đời và audit key theo nhu cầu riêng |
| Customer-managed key (CMK) | Khách hàng quản lý key resource/policy trong KMS; provider vẫn vận hành hạ tầng KMS | Kiểm soát quyền sử dụng, rotation, disable và audit |
| Customer-provided key | Khách hàng cung cấp key trong request | Kiểm soát trực tiếp key nhưng có trách nhiệm lưu giữ và gửi key an toàn |
| Application-managed key | Ứng dụng hoặc hệ thống riêng quản lý | Linh hoạt, nhưng trách nhiệm lớn; thường kết hợp envelope encryption |

**Customer-managed key không có nghĩa ứng dụng nhận private key hoặc raw key material.** Thông thường, KMS giữ key material và workload chỉ được phép gọi các thao tác mã hóa/giải mã hoặc tạo data key.

### 3.3. SSE trên AWS

Các lựa chọn phổ biến với Amazon S3:

| Chế độ | Ý nghĩa |
| --- | --- |
| SSE-S3 | S3 tự quản lý key cho mã hóa object |
| SSE-KMS | S3 dùng AWS KMS key; có thể chọn AWS managed key hoặc customer managed KMS key |
| DSSE-KMS | Dual-layer server-side encryption với hai lớp mã hóa được dịch vụ quản lý |
| SSE-C | Client cung cấp key cho từng request; S3 thực hiện mã hóa/giải mã phía server |

Ví dụ AWS SDK for Java 2.x yêu cầu SSE-KMS cho object:

~~~java
PutObjectRequest request = PutObjectRequest.builder()
        .bucket(bucketName)
        .key(objectKey)
        .serverSideEncryption(ServerSideEncryption.AWS_KMS)
        .ssekmsKeyId(kmsKeyArn)
        .build();

s3Client.putObject(request, RequestBody.fromFile(file));
~~~

Đây là ví dụ khái niệm cho S3 PutObject; cần thêm dependency S3 SDK và xử lý file/stream theo ứng dụng. Nếu bucket đã có default bucket encryption SSE-KMS, có thể không cần chỉ định header cho từng object; nhưng cần xác minh bucket policy và encryption configuration.

Khi dùng SSE-KMS, principal upload thường cần quyền KMS tương ứng để S3 tạo data key; principal đọc cần quyền decrypt theo key policy/IAM và bucket policy. Chính sách thực tế còn phụ thuộc S3 Bucket Key, cross-account access, grants và service integration. Không chỉ cấp quyền S3 GetObject rồi giả định KMS permission tự có.

**SSE-C không phải CSE.** Client gửi key tới S3 qua HTTPS, nhưng S3 vẫn mã hóa/giải mã ở phía server. Nếu yêu cầu storage service chỉ nhìn thấy ciphertext, cần CSE trước khi upload.

### 3.4. SSE trên Azure Storage

Azure Storage mã hóa dữ liệu at rest mặc định bằng encryption at rest. Có thể chọn:

- Microsoft-managed keys: nền tảng quản lý key.
- Customer-managed keys trong Azure Key Vault hoặc Managed HSM: tổ chức kiểm soát key resource và policy.
- Customer-provided keys trong một số dịch vụ/luồng hỗ trợ: client cung cấp key cho service thực hiện mã hóa server-side.

Với Blob Storage CMK, cần cấu hình identity mà Storage sử dụng để truy cập Key Vault và cấp quyền key phù hợp. Đây có thể là managed identity của storage account/service, không nhất thiết là identity của Spring Boot. Phải phân biệt principal gọi Blob API với principal mà Azure Storage dùng để truy cập Key Vault.

Spring Boot vẫn gọi Blob SDK qua HTTPS; ứng dụng không cần tự mã hóa nội dung chỉ vì Storage đang dùng CMK. Nếu cần bảo vệ plaintext trước cả storage service, dùng CSE.

### 3.5. SSE trên Google Cloud Storage

Google Cloud Storage hỗ trợ:

- Google-managed encryption keys mặc định.
- Customer-managed encryption keys (CMEK) thông qua Cloud KMS.
- Customer-supplied encryption keys (CSEK) cho các use case được hỗ trợ.

Khi dùng CMEK, Cloud Storage service agent cần quyền sử dụng CryptoKey phù hợp. Service account của Spring Boot vẫn cần quyền object storage; quyền KMS của service agent và quyền IAM của workload là hai principal khác nhau.

Google Cloud Storage có thể sử dụng key version theo cấu hình CMEK. Khi thay đổi primary version, object mới được ghi có thể dùng version mới; object cũ không tự động được mã hóa lại chỉ vì primary version đổi.

### 3.6. Database và volume

Mã hóa ở lớp database/volume phù hợp để bảo vệ data files, logs, backup và snapshot:

| Dịch vụ | Cơ chế thường gặp |
| --- | --- |
| Amazon RDS/Aurora | Storage encryption với AWS KMS |
| Azure SQL Database | Transparent Data Encryption; có lựa chọn customer-managed key |
| Azure Database for PostgreSQL/MySQL | Encryption at rest theo khả năng dịch vụ và cấu hình |
| Google Cloud SQL | Encryption at rest; CMEK ở các cấu hình được hỗ trợ |
| Persistent disk/managed disk | Disk encryption và customer-managed key tùy dịch vụ |

TDE không thay thế CSE cho một cột dữ liệu nhạy cảm nếu DBA hoặc principal database được phép truy vấn plaintext. Nếu yêu cầu database engine không đọc được một field, cần mã hóa ở application layer trước khi ghi.

## 4. Client-side encryption (CSE)

### 4.1. Luồng hoạt động

~~~text
Spring Boot application
    |
    | 1. Sinh/lấy DEK
    | 2. AES-GCM encrypt plaintext
    | 3. KMS wrap DEK bằng KEK
    v
Ciphertext + nonce + authentication tag
Wrapped DEK + key reference + metadata
    |
    | HTTPS
    v
Object storage / database
    |
    | Chỉ lưu ciphertext và wrapped DEK
    v
Khi đọc: app lấy envelope -> KMS unwrap DEK -> AES-GCM decrypt
~~~

Với CSE, storage không thực hiện giải mã nội dung. Ứng dụng phải có quyền unwrap DEK và đúng metadata để giải mã.

### 4.2. Khi nào nên dùng CSE?

| Yêu cầu | CSE có phù hợp? |
| --- | --- |
| Storage operator không được đọc plaintext | Có |
| Chỉ muốn mã hóa disk/backup và vẫn cho service đọc object | SSE thường đủ |
| Mã hóa một vài field PII trước khi ghi DB | Có thể phù hợp |
| Cần server-side search/filter trực tiếp trên nội dung | Khó hơn; cần thiết kế index/token riêng |
| Cần xử lý video lớn hoặc streaming | Có thể, nhưng cần chunking/streaming format và quản lý nonce/tag theo chunk |
| Cần chia sẻ file cho nhiều tenant với quyền khác nhau | Có thể, nhưng cần mô hình key per tenant/recipient và access control rõ |
| Không có quy trình lưu giữ/khôi phục khóa | Chưa nên triển khai CSE |

CSE tăng tính bảo mật nhưng cũng tăng độ phức tạp vận hành. Mất KEK hoặc mất mọi bản wrapped DEK có thể làm dữ liệu không thể khôi phục dù object storage vẫn còn nguyên.

### 4.3. Những gì CSE không tự bảo vệ

- **Metadata:** object name, tenant, timestamp, content length, tags và access pattern có thể vẫn lộ.
- **Application runtime:** khi ứng dụng giải mã, plaintext có trong memory và có thể xuất hiện trong heap dump, log hoặc crash report.
- **Credential compromise:** attacker chiếm được workload identity có quyền unwrap có thể yêu cầu KMS giải mã.
- **Authorization:** encryption không thay thế quyền truy cập theo tenant/user; cần kiểm tra quyền trước khi unwrap.
- **Integrity ngoài payload:** AES-GCM xác thực ciphertext/AAD, nhưng không tự bảo vệ mọi metadata nếu metadata không nằm trong AAD.

## 5. Envelope encryption: DEK và KEK

### 5.1. Hai cấp khóa

- **DEK (Data Encryption Key):** khóa mã hóa dữ liệu thực tế, ví dụ AES-256.
- **KEK (Key Encryption Key):** khóa trong KMS dùng để wrap/unwrap DEK; không dùng trực tiếp để mã hóa file lớn.
- **Wrapped DEK:** DEK đã được mã hóa bởi KEK, có thể lưu cùng ciphertext.
- **Key reference:** định danh KMS key/Key Vault key/CryptoKey và có thể kèm version.

~~~mermaid
flowchart TD
    P["Plaintext payload"] --> E["AES-256-GCM"]
    D["DEK: AES-256"] --> E
    E --> C["Ciphertext + nonce + tag"]
    D --> W["KMS Wrap / Encrypt DEK"]
    K["KEK trong KMS"] --> W
    W --> WD["Wrapped DEK"]
    C --> O["Encrypted object envelope"]
    WD --> O
    M["Key ID + algorithm + format version + AAD context"] --> O
~~~

### 5.2. Vì sao không dùng KEK mã hóa file trực tiếp?

KMS thường giới hạn kích thước plaintext được mã hóa trực tiếp và tối ưu cho thao tác quản lý khóa. Mã hóa một file lớn bằng API KMS:

- Tăng latency và chi phí.
- Có thể vượt giới hạn kích thước request.
- Buộc payload đi qua KMS thay vì mã hóa local.
- Khó stream và khó kiểm soát memory.

Envelope encryption chỉ gửi **DEK nhỏ** tới KMS để wrap/unwrap. Payload được mã hóa cục bộ bằng AES-GCM.

### 5.3. Quy trình mã hóa

1. Ứng dụng xác thực principal và kiểm tra quyền ghi object.
2. Yêu cầu KMS tạo DEK hoặc tự sinh DEK bằng SecureRandom/KeyGenerator.
3. Nhận plaintext DEK trong bộ nhớ và wrapped DEK.
4. Sinh nonce ngẫu nhiên duy nhất cho lần mã hóa với DEK đó.
5. Mã hóa plaintext bằng AES-256-GCM; đưa metadata quan trọng vào AAD.
6. Lưu ciphertext, nonce, wrapped DEK, key reference, thuật toán và format version.
7. Xóa best-effort bản sao DEK plaintext khỏi vùng nhớ có thể kiểm soát.

### 5.4. Quy trình giải mã

1. Xác thực người dùng/tenant và quyền đọc object.
2. Đọc envelope; kiểm tra format version, key reference và metadata.
3. Gọi KMS unwrap DEK với đúng encryption context.
4. Dùng DEK và nonce để giải mã AES-GCM.
5. GCM xác minh authentication tag; nếu sai, từ chối plaintext.
6. Trả plaintext trong phạm vi được phép và không ghi vào log.
7. Xóa best-effort DEK khỏi bộ nhớ sau khi hoàn tất.

**Không trả một phần plaintext trước khi xác minh GCM tag thành công.** Với API streaming, phải thiết kế buffering/chunk authentication để dữ liệu chưa xác minh không được tiêu thụ như dữ liệu hợp lệ.

## 6. Chọn thuật toán và định dạng envelope

### 6.1. AES-256-GCM

AES-GCM là authenticated encryption with associated data (AEAD): vừa mã hóa vừa kiểm tra integrity/authenticity.

| Tham số | Giá trị gợi ý |
| --- | --- |
| Cipher | AES/GCM/NoPadding |
| Key size | 256 bit (32 byte) |
| Nonce/IV | 96 bit (12 byte) |
| Authentication tag | 128 bit (16 byte) |
| AAD | Context không bí mật nhưng cần được xác thực |
| Nonce rule | Không bao giờ tái sử dụng nonce với cùng một DEK |

Không dùng ECB. CBC chỉ mã hóa mà không tự xác thực; nếu phải dùng mode cũ cần encrypt-then-MAC đúng cách. Với ứng dụng mới, ưu tiên AEAD như AES-GCM hoặc ChaCha20-Poly1305 nếu nền tảng hỗ trợ theo chính sách.

### 6.2. Nonce/IV

Nonce GCM không cần bí mật, nhưng **phải duy nhất với một key**. Tái sử dụng nonce cùng DEK có thể làm lộ thông tin và phá vỡ bảo đảm integrity.

Cách đơn giản cho mỗi object:

- Tạo DEK mới cho từng object/envelope.
- Sinh nonce 12 byte từ SecureRandom.
- Lưu nonce cùng ciphertext.
- Không dùng lại DEK/nonce pair cho lần mã hóa khác.

Với một DEK dùng cho rất nhiều record, cần cơ chế nonce uniqueness có kiểm soát và giới hạn số lần sử dụng. Tránh tự thiết kế counter nếu không có khả năng đồng bộ và chống trùng lặp giữa nhiều instance.

### 6.3. Authenticated Additional Data (AAD)

AAD là metadata được xác thực cùng ciphertext nhưng không được mã hóa. Có thể chứa:

- Tenant ID.
- Object ID.
- Logical record type.
- Schema/format version.
- Application namespace.

Ví dụ AAD gắn object vào tenant:

~~~text
tenant=tenant-42
object=contract-2026-001
purpose=contract-pdf
format=v1
~~~

Khi giải mã phải tạo đúng AAD như lúc mã hóa. Nếu attacker thay object ID hoặc tenant ID trong metadata, GCM tag verification sẽ thất bại. Không đưa dữ liệu bí mật vào AAD vì AAD được lưu/quan sát ở dạng plaintext.

Với AWS KMS, encryption context là metadata bổ sung được KMS xác thực trong thao tác Encrypt/Decrypt; nó **không bí mật** và có thể xuất hiện trong CloudTrail. Không đưa PII, token hoặc dữ liệu nhạy cảm vào encryption context.

### 6.4. Định dạng envelope lưu trữ

Một record có thể được biểu diễn như sau:

~~~json
{
  "formatVersion": 1,
  "algorithm": "AES-256-GCM",
  "keyProvider": "aws-kms",
  "keyReference": "arn:aws:kms:region:account:key/key-id",
  "wrappedDek": "base64...",
  "nonce": "base64...",
  "ciphertext": "base64...",
  "context": {
    "tenantId": "tenant-42",
    "objectId": "contract-2026-001"
  }
}
~~~

Đây là **mô hình dữ liệu minh họa**, không phải format chuẩn của mọi SDK. Cần version hóa schema, giới hạn kích thước metadata, xác thực context và định nghĩa migration. Không lưu plaintext DEK hoặc KEK trong envelope.

Với payload lớn, có thể lưu ciphertext trong object storage và envelope metadata ở header/sidecar/database. Phải bảo đảm metadata không thể bị tách khỏi object hoặc thay thế mà không được phát hiện; đưa các trường quan trọng vào AAD.

## 7. Mẫu mã hóa Java trong Spring Boot

Phần này minh họa lớp mã hóa độc lập cloud. Adapter KMS cụ thể sẽ cung cấp DEK và wrapped DEK. Ứng dụng không tự lưu KEK.

### 7.1. Model và interface cho key provider

~~~java
package com.example.protection;

public record DataKeyMaterial(byte[] plaintextKey, byte[] wrappedKey, String keyReference) {
}
~~~

~~~java
package com.example.protection;

import java.util.Map;

public interface DataKeyProvider {
    DataKeyMaterial generateDataKey(
            String keyReference,
            Map<String, String> kmsEncryptionContext);

    byte[] unwrapDataKey(
            String keyReference,
            byte[] wrappedKey,
            Map<String, String> kmsEncryptionContext);
}
~~~

Implementations gọi AWS KMS, Azure Key Vault hoặc Google Cloud KMS. Chỉ adapter có quyền cần thiết mới được phép wrap/unwrap; service nghiệp vụ không cần biết chi tiết SDK.

**Tách hai loại context:** AAD dạng byte được AES-GCM xác thực cùng payload; KMS encryption context là metadata riêng do provider hỗ trợ (AWS KMS dùng map key/value, Azure Key Vault wrap không có tham số tương đương). Không giả định hai giá trị này là cùng một format. Chỉ đưa metadata không nhạy cảm vào KMS context; phải tái tạo chính xác context khi unwrap.

### 7.2. Envelope model

~~~java
package com.example.protection;

public record EncryptedEnvelope(
        int formatVersion,
        String algorithm,
        String keyReference,
        byte[] wrappedKey,
        byte[] nonce,
        byte[] ciphertext) {
}
~~~

Trong production, record có mảng byte cần defensive copy khi tạo và trả về để tránh caller thay đổi nội dung sau khi xác thực. Có thể dùng immutable value object và serializer version hóa.

### 7.3. AES-GCM service

~~~java
package com.example.protection;

import java.util.Map;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.stereotype.Service;

@Service
public class EnvelopeEncryptionService {
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int KEY_BYTES = 32;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    private final DataKeyProvider keyProvider;
    private final SecureRandom secureRandom = new SecureRandom();

    public EnvelopeEncryptionService(DataKeyProvider keyProvider) {
        this.keyProvider = keyProvider;
    }

    public EncryptedEnvelope encrypt(
            byte[] plaintext,
            byte[] aad,
            String keyReference,
            Map<String, String> kmsEncryptionContext) throws Exception {

        DataKeyMaterial material =
                keyProvider.generateDataKey(keyReference, kmsEncryptionContext);

        byte[] dek = material.plaintextKey();
        byte[] nonce = new byte[NONCE_BYTES];
        secureRandom.nextBytes(nonce);

        try {
            if (dek.length != KEY_BYTES) {
                throw new IllegalStateException("Expected a 256-bit DEK");
            }

            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(
                    Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(dek, "AES"),
                    new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(aad);

            byte[] ciphertext = cipher.doFinal(plaintext);

            return new EncryptedEnvelope(
                    1,
                    "AES-256-GCM",
                    material.keyReference(),
                    material.wrappedKey(),
                    nonce,
                    ciphertext);
        } finally {
            // Best-effort cleanup; JVM/provider may retain internal copies.
            Arrays.fill(dek, (byte) 0);
        }
    }

    public byte[] decrypt(
            EncryptedEnvelope envelope,
            byte[] aad,
            Map<String, String> kmsEncryptionContext) throws Exception {

        if (envelope.formatVersion() != 1
                || !"AES-256-GCM".equals(envelope.algorithm())) {
            throw new IllegalArgumentException("Unsupported envelope format");
        }

        byte[] dek = keyProvider.unwrapDataKey(
                envelope.keyReference(),
                envelope.wrappedKey(),
                kmsEncryptionContext);

        try {
            if (dek.length != KEY_BYTES) {
                throw new IllegalStateException("Invalid DEK length");
            }

            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(
                    Cipher.DECRYPT_MODE,
                    new SecretKeySpec(dek, "AES"),
                    new GCMParameterSpec(TAG_BITS, envelope.nonce()));
            cipher.updateAAD(aad);

            // doFinal verifies the GCM authentication tag before returning plaintext.
            return cipher.doFinal(envelope.ciphertext());
        } finally {
            Arrays.fill(dek, (byte) 0);
        }
    }
}
~~~

Mẫu trên tập trung vào logic AEAD. Trong production cần bổ sung:

- Defensive copy và validation kích thước của mọi field.
- Kiểm tra tenant/object authorization **trước** khi gọi unwrap.
- Ràng buộc AAD với object/tenant ID lấy từ trusted request context.
- Error mapping không tiết lộ ciphertext, key hoặc plaintext.
- Timeout/retry có giới hạn cho KMS.
- Metrics về key reference/version nhưng không ghi secret.
- Streaming/chunked encryption cho file lớn.
- Kiểm thử tamper, wrong AAD, wrong key và version migration.

Không dùng throws Exception rộng trong service production; chuyển lỗi KMS, lỗi format và lỗi authentication tag thành exception/domain error riêng.

### 7.4. Sinh DEK local thay vì KMS GenerateDataKey

Một provider có thể tự sinh AES key bằng JCA rồi gọi KMS để wrap:

~~~java
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, new SecureRandom());
SecretKey dek = generator.generateKey();

byte[] plaintextDek = dek.getEncoded();
// Gọi KMS wrap/encrypt với plaintextDek.
// Lưu wrapped DEK; không lưu plaintextDek.
~~~

Đây là mô hình phổ biến với Key Vault RSA wrap và Cloud KMS encrypt. Với AWS KMS, có thể dùng GenerateDataKey để KMS sinh cả plaintext DEK và ciphertext blob trong cùng thao tác, giảm việc tự sinh và wrap.

## 8. Tích hợp AWS KMS

### 8.1. GenerateDataKey

AWS KMS có API GenerateDataKey trả về:

- Plaintext: DEK để ứng dụng mã hóa dữ liệu.
- CiphertextBlob: DEK đã được KMS mã hóa bằng KMS key.
- Key ID và metadata liên quan.

Ví dụ AWS SDK for Java 2.x:

~~~java
GenerateDataKeyResponse response = kmsClient.generateDataKey(
        GenerateDataKeyRequest.builder()
                .keyId(kmsKeyArn)
                .keySpec(DataKeySpec.AES_256)
                .encryptionContext(Map.of(
                        "tenant", tenantId,
                        "purpose", "contract"))
                .build());

byte[] plaintextDek = response.plaintext().asByteArray();
byte[] wrappedDek = response.ciphertextBlob().asByteArray();
~~~

Ứng dụng dùng plaintextDek cho AES-GCM và lưu wrappedDek trong envelope. Sau khi dùng, xóa best-effort plaintext key khỏi bộ nhớ. Encryption context phải được gửi lại nguyên vẹn khi decrypt; không dùng dữ liệu do người gọi tùy ý truyền mà chưa xác thực.

### 8.2. Decrypt DEK

~~~java
DecryptResponse response = kmsClient.decrypt(
        DecryptRequest.builder()
                .ciphertextBlob(SdkBytes.fromByteArray(wrappedDek))
                .encryptionContext(Map.of(
                        "tenant", tenantId,
                        "purpose", "contract"))
                .build());

byte[] plaintextDek = response.plaintext().asByteArray();
~~~

AWS KMS dùng metadata trong ciphertext blob để xác định key cần giải mã; có thể chỉ định key ID trong một số tình huống theo API. Với envelope cross-account hoặc nhiều key, lưu key ARN/resource reference để audit và hỗ trợ migration.

### 8.3. IAM và key policy

Workload dùng AWS KMS GenerateDataKey cần quyền `kms:GenerateDataKey`; đọc envelope và unwrap DEK cần quyền `kms:Decrypt`. Nếu adapter gọi KMS Encrypt/Decrypt trực tiếp để wrap DEK, cấp các action tương ứng. Key policy và IAM policy đều có thể tham gia quyết định quyền.

Encryption context:

- Không bí mật; có thể được ghi vào CloudTrail.
- Phải khớp giữa GenerateDataKey/Encrypt và Decrypt.
- Có thể dùng trong IAM condition để giới hạn ngữ cảnh sử dụng key.
- Không chứa email, số tài khoản, token hoặc PII.

### 8.4. SSE-KMS và CSE với AWS KMS là hai việc khác nhau

| SSE-KMS | CSE envelope |
| --- | --- |
| S3 gọi KMS theo cấu hình encryption của bucket/object | Ứng dụng gọi KMS để tạo/wrap DEK |
| S3 nhận plaintext và mã hóa ở server | S3 chỉ nhận ciphertext |
| S3 giải mã khi principal được phép đọc | Ứng dụng unwrap DEK rồi giải mã |
| Cần quyền S3 và quyền KMS theo luồng SSE | Cần quyền S3 và quyền KMS của ứng dụng |
| Ít code crypto hơn | Tự chịu trách nhiệm format, nonce, AAD và migration |

Không nhầm việc bật default SSE-KMS trên bucket với việc ứng dụng đã mã hóa payload trước upload.

## 9. Tích hợp Azure Key Vault Keys

### 9.1. Key Vault key và secret khác nhau

- **Key Vault Secret:** lưu một giá trị nhạy cảm như password hoặc token.
- **Key Vault Key:** đối tượng khóa hỗ trợ các thao tác cryptographic như wrap/unwrap, encrypt/decrypt hoặc sign/verify tùy loại key.
- **Key Vault Certificate:** quản lý certificate và liên kết với key/secret tương ứng theo mô hình dịch vụ.

Envelope encryption nên dùng **Key Vault Key** cho KEK, không lưu DEK plaintext trong Secret. Có thể dùng Azure Key Vault hoặc Managed HSM tùy yêu cầu bảo vệ key material và isolation.

### 9.2. Wrap/unwrap DEK bằng RSA-OAEP-256

Ví dụ dùng Azure SDK for Java:

~~~java
CryptographyClient cryptoClient = new CryptographyClientBuilder()
        .keyIdentifier(keyIdentifier)
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildClient();

WrapResult wrapped = cryptoClient.wrapKey(
        KeyWrapAlgorithm.RSA_OAEP_256,
        plaintextDek);

byte[] wrappedDek = wrapped.getEncryptedKey();

UnwrapResult unwrapped = cryptoClient.unwrapKey(
        KeyWrapAlgorithm.RSA_OAEP_256,
        wrappedDek);

byte[] plaintextDek = unwrapped.getKey();
~~~

Tên import và package có thể thay đổi theo phiên bản azure-security-keyvault-keys; kiểm tra BOM Azure SDK đang dùng. Key phải là RSA có kích thước/thuộc tính tương thích với thuật toán wrap. RSA-OAEP-256 phù hợp để wrap một DEK 32 byte; không dùng RSA để mã hóa PDF hoặc object lớn.

### 9.3. Quyền và identity

Workload cần token Microsoft Entra ID và quyền cryptographic operation trên key. Với Azure RBAC, role như **Key Vault Crypto User** phù hợp cho ứng dụng cần thực hiện thao tác cryptographic được phép; quyền thực tế còn phụ thuộc key type, operation và scope. Không dùng **Key Vault Secrets User** thay cho quyền dùng Key Vault Key.

Nếu Azure Storage sử dụng CMK, principal được cấp quyền Key Vault có thể là **managed identity của Storage account** hoặc service principal mà dịch vụ yêu cầu, không nhất thiết là identity Spring Boot. Tách rõ:

- Spring Boot identity: quyền gọi Blob/Key Vault API nếu ứng dụng trực tiếp wrap/unwrap.
- Storage service identity: quyền dùng key để SSE-CMK.
- Key administrator: quyền tạo/rotate/disable key và policy.

### 9.4. Key version

Key Vault key identifier có thể bao gồm version. Envelope nên lưu key ID/version đã wrap DEK. Khi key mới trở thành version hiện hành, DEK cũ vẫn cần unwrap được bằng version cũ cho tới khi hoàn tất rewrap hoặc hết retention. Không xóa/disable version cũ chỉ vì version mới đã được tạo.

## 10. Tích hợp Google Cloud KMS

### 10.1. Encrypt DEK bằng Cloud KMS

Google Cloud KMS có API Encrypt/Decrypt phù hợp để bảo vệ DEK nhỏ. Payload ứng dụng được mã hóa local bằng AES-GCM; chỉ DEK được gửi tới KMS.

Ví dụ Java client:

~~~java
CryptoKeyName keyName = CryptoKeyName.of(
        projectId, locationId, keyRingId, cryptoKeyId);

EncryptResponse response = kmsClient.encrypt(
        EncryptRequest.newBuilder()
                .setName(keyName.toString())
                .setPlaintext(ByteString.copyFrom(plaintextDek))
                .setAdditionalAuthenticatedData(ByteString.copyFrom(contextBytes))
                .build());

byte[] wrappedDek = response.getCiphertext().toByteArray();
~~~

Khi giải mã DEK:

~~~java
DecryptResponse response = kmsClient.decrypt(
        DecryptRequest.newBuilder()
                .setName(keyName.toString())
                .setCiphertext(ByteString.copyFrom(wrappedDek))
                .setAdditionalAuthenticatedData(ByteString.copyFrom(contextBytes))
                .build());

byte[] plaintextDek = response.getPlaintext().toByteArray();
~~~

Cloud KMS Encrypt API có giới hạn kích thước plaintext (64 KiB cho symmetric encrypt); do đó chỉ gửi DEK nhỏ, không gửi file/object lớn. AAD phải giống hệt khi decrypt. Với key version, API sử dụng primary version khi encrypt và ciphertext mang metadata để KMS xác định version giải mã phù hợp.

### 10.2. IAM và service account

Principal gọi Cloud KMS cần quyền phù hợp, ví dụ role `roles/cloudkms.cryptoKeyEncrypterDecrypter` ở CryptoKey hoặc scope phù hợp. Dùng Workload Identity Federation/Workload Identity trên môi trường cloud thay vì tải service account JSON key dài hạn vào container.

Nếu dùng CMEK cho Cloud Storage, **Cloud Storage service agent** cần quyền encrypt/decrypt trên CryptoKey; quyền này khác quyền của Spring Boot service account dùng Storage API.

### 10.3. Cloud KMS và envelope encryption

Google Cloud KMS cũng hỗ trợ các thư viện client-side encryption ở cấp ứng dụng trong một số ngôn ngữ/sản phẩm. Nếu tự xây format, phải quản lý version, nonce, AAD, wrapped DEK và serialization như các phần trước. Không trộn định dạng envelope tự thiết kế với format của thư viện cloud mà không có migration/compatibility plan.

## 11. So sánh các dịch vụ quản lý khóa

| Tiêu chí | AWS KMS | Azure Key Vault / Managed HSM | Google Cloud KMS |
| --- | --- | --- | --- |
| Đối tượng khóa | KMS key | Key Vault key / HSM key | CryptoKey và CryptoKeyVersion |
| Tạo DEK | GenerateDataKey | Sinh DEK local rồi WrapKey | Sinh DEK local rồi Encrypt |
| Wrap/unwrap | Encrypt/Decrypt hoặc GenerateDataKey/Decrypt | WrapKey/UnwrapKey | Encrypt/Decrypt |
| Workload identity | IAM role, STS, workload identity | Microsoft Entra ID, Managed Identity | Service account, Workload Identity Federation |
| Quyền thao tác | IAM + key policy/grant | Azure RBAC hoặc access policy | IAM roles trên key |
| Key rotation | Automatic/on-demand rotation tùy key type | Tạo version mới/rotation policy tùy key type | Tạo CryptoKeyVersion mới và chuyển primary |
| Audit | CloudTrail/KMS events | Azure Monitor/Key Vault audit logs | Cloud Audit Logs |
| Service-side encryption | S3, RDS và dịch vụ tích hợp KMS | Storage, SQL và dịch vụ tích hợp CMK | Cloud Storage, BigQuery, Cloud SQL và dịch vụ hỗ trợ CMEK |

Mỗi provider có cách biểu diễn key version, policy và principal khác nhau. Adapter nên che giấu API cụ thể nhưng **không được che giấu khác biệt về authorization, key version hoặc audit**.

## 12. Quản lý vòng đời khóa

Khóa là tài sản có vòng đời. Việc tạo key mới chỉ là khởi đầu.

### 12.1. Các trạng thái vận hành

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Enabled
    Enabled --> Rotating
    Rotating --> Enabled: New writes use new version
    Enabled --> Disabled: Suspend use
    Disabled --> Enabled: Restore if safe
    Disabled --> ScheduledForDestruction
    ScheduledForDestruction --> Disabled: Cancel if supported
    ScheduledForDestruction --> Destroyed
    Destroyed --> [*]
~~~

Các giai đoạn:

1. **Create:** tạo key với loại/thuộc tính/region phù hợp.
2. **Enable:** cấp quyền tối thiểu cho workload cần dùng.
3. **Use:** ghi lại key reference/version và audit operation.
4. **Rotate:** chuyển hoạt động mã hóa mới sang version mới.
5. **Rewrap/Re-encrypt:** xử lý DEK hoặc dữ liệu đã mã hóa theo chính sách.
6. **Disable:** ngừng sử dụng version cũ sau khi xác minh không còn phụ thuộc.
7. **Destroy:** chỉ thực hiện sau retention, backup và recovery validation.

### 12.2. Rotation không đồng nghĩa re-encryption

Khi KMS key rotation, cần phân biệt:

| Hành động | Điều gì thay đổi? |
| --- | --- |
| KMS automatic rotation | Key material version mới được tạo/được dùng cho thao tác encrypt mới; KMS thường vẫn giải mã ciphertext cũ bằng version cần thiết |
| Tạo key version mới | Primary/current version có thể đổi; các object đã mã hóa vẫn giữ envelope cũ |
| Rewrap DEK | DEK plaintext được unwrap bằng KEK cũ rồi wrap lại bằng KEK mới; payload ciphertext không đổi |
| Re-encrypt payload | Dữ liệu được giải mã rồi mã hóa lại bằng DEK mới; tốn I/O và có thể cần downtime/streaming |
| Disable/destroy old key | Có thể khiến envelope/object cũ không giải mã được nếu vẫn phụ thuộc key đó |

**Rotation key không tự động re-encrypt toàn bộ object hoặc database.** Với SSE, dịch vụ quản lý cách dùng key cho data mới và cách giải mã dữ liệu cũ theo tính năng của dịch vụ. Với CSE, ứng dụng phải quản lý wrapped DEK và có thể cần rewrap.

### 12.3. Rewrap DEK

Khi chỉ muốn thay KEK mà giữ payload ciphertext:

1. Đọc envelope và wrapped DEK.
2. Dùng KEK cũ unwrap DEK trong memory.
3. Dùng KEK mới wrap cùng DEK.
4. Ghi envelope metadata mới với key reference/version mới.
5. Xác minh decrypt được bằng key mới.
6. Sau khi toàn bộ object/backup/replica đã chuyển, mới cân nhắc disable key cũ.

Payload ciphertext không thay đổi vì DEK không đổi. Rewrap có thể giảm chi phí so với giải mã/mã hóa lại payload lớn. Nhưng nếu DEK đã bị lộ hoặc thuật toán DEK bị yếu, rewrap không đủ; phải tạo DEK mới và re-encrypt payload.

### 12.4. Backup, retention và recovery

Trước khi disable/destroy key, xác minh:

- Có bao nhiêu object/row/backup/snapshot còn phụ thuộc key version này?
- Có replica hoặc archive ở region/account/project khác không?
- Có thể restore backup cũ bằng key hiện có không?
- Key Vault soft-delete/purge protection hoặc cơ chế deletion protection đã được bật theo policy chưa?
- Ai được quyền schedule deletion/purge?
- Có quy trình phục hồi key/identity/permissions sau incident không?

Mất key có thể đồng nghĩa mất dữ liệu vĩnh viễn. Không xóa key dựa trên việc object storage hiện tại không còn object tham chiếu; backup, archive và bản sao offline có thể vẫn cần key cũ.

## 13. Quyền truy cập và separation of duties

### 13.1. Quyền runtime tối thiểu

| Principal | Quyền nên có |
| --- | --- |
| Spring Boot workload | Gọi API storage và thao tác KMS cần cho nghiệp vụ |
| Storage service identity | Dùng CMK theo yêu cầu dịch vụ SSE |
| Key administrator | Tạo, rotate, disable và quản lý policy |
| Security auditor | Đọc audit/config metadata, không mặc định có decrypt |
| Backup/recovery operator | Quyền khôi phục theo quy trình kiểm soát, có audit |

Tách quyền **encrypt** và **decrypt** nếu threat model yêu cầu. Một workload chỉ ghi archive có thể được phép tạo DEK/encrypt nhưng không có quyền đọc/unwrap. Một service phân tích có thể được cấp decrypt cho đúng dataset/tenant.

### 13.2. Scope và policy

- Tạo key riêng cho production và non-production.
- Cân nhắc key riêng theo tenant hoặc data classification nếu yêu cầu isolation.
- Giới hạn quyền theo key resource, không dùng wildcard toàn account/subscription/project.
- Dùng condition/context để giới hạn encryption context nếu KMS hỗ trợ.
- Không chia sẻ cùng một KMS key cho mọi ứng dụng chỉ vì thuận tiện.
- Theo dõi thay đổi key policy, grants, IAM binding và access policy.
- Kiểm soát quyền unwrap/decrypt vì đây là quyền có thể biến ciphertext thành plaintext.

### 13.3. Authorization trước khi unwrap

Một API tải file không nên gọi KMS decrypt trước khi xác minh caller có quyền đọc object. Trình tự phù hợp:

1. Xác thực user/service caller.
2. Kiểm tra tenant/object ownership và business authorization.
3. Đọc envelope metadata.
4. Xác minh key reference và context thuộc object được phép.
5. Gọi KMS unwrap.
6. AES-GCM decrypt và trả dữ liệu.

Nếu unwrap trước rồi mới kiểm tra quyền, KMS audit log sẽ ghi các lần giải mã không cần thiết và có thể tạo side channel. Cần giới hạn rate và giám sát các thao tác decrypt bất thường.

## 14. Bảo vệ dữ liệu trong Spring Boot

### 14.1. Cấu hình key reference, không cấu hình raw KEK

Ví dụ cấu hình ứng dụng:

~~~yaml
app:
  encryption:
    provider: azure-key-vault
    key-reference: "${APP_ENCRYPTION_KEY_ID}"
    algorithm: AES-256-GCM
    envelope-version: 1
~~~

APP_ENCRYPTION_KEY_ID chỉ là resource identifier của key, không phải key material hoặc password. Credential để gọi KMS lấy từ Managed Identity, AWS IAM role hoặc Google Workload Identity.

Không đặt DEK/KEK plaintext trong application.yml, Config Server, environment variable, Docker image hoặc database.

### 14.2. Tách adapter theo provider

Một cấu trúc package có thể là:

~~~text
com.example.protection
  DataKeyProvider.java
  DataKeyMaterial.java
  EncryptedEnvelope.java
  EnvelopeEncryptionService.java
  aws/
    AwsKmsDataKeyProvider.java
  azure/
    AzureKeyVaultDataKeyProvider.java
  gcp/
    GoogleCloudKmsDataKeyProvider.java
~~~

Business service phụ thuộc DataKeyProvider và EnvelopeEncryptionService. Adapter chứa chi tiết SDK và identity. Điều này giúp test AES-GCM không cần cloud thật, đồng thời integration test từng adapter riêng.

### 14.3. Không dùng một key cho mọi mục đích

Tách key theo mục đích:

- DEK cho payload/object.
- KEK cho wrap DEK.
- Key ký token hoặc JWT.
- Key ký webhook.
- Key mã hóa database field.

Không tái sử dụng cùng key cho encryption, signing, TLS và password hashing. Password người dùng nên dùng password hashing chuyên dụng (Argon2id/bcrypt/PBKDF2 theo policy), không mã hóa reversible bằng AES/KMS như một secret thông thường.

### 14.4. Giới hạn plaintext lifetime

- Chỉ giải mã khi nghiệp vụ cần.
- Tránh giữ plaintext trong cache dài hạn.
- Không log request/response chứa dữ liệu nhạy cảm.
- Hạn chế heap dump, core dump và crash report.
- Xóa best-effort byte array chứa DEK/plaintext khi không còn cần.
- Dùng streaming để tránh giữ toàn bộ file lớn trong heap.
- Bảo vệ temporary files và swap theo chính sách môi trường.
- Không gửi plaintext tới tracing/metrics/error reporting.

Xóa mảng byte trong Java là best-effort; JVM, JIT hoặc provider có thể tạo bản sao nội bộ. Với yêu cầu kiểm soát key memory cao, đánh giá HSM, process isolation hoặc crypto provider chuyên dụng.

## 15. Kiểm thử mã hóa và quản lý khóa

### 15.1. Unit test cho AES-GCM

Kiểm tra round-trip:

~~~java
@Test
void encryptThenDecryptReturnsOriginal() throws Exception {
    byte[] plaintext = "contract-data".getBytes(StandardCharsets.UTF_8);
    byte[] aad = "tenant=tenant-42;object=contract-1"
            .getBytes(StandardCharsets.UTF_8);

    EncryptedEnvelope envelope = service.encrypt(
            plaintext, aad, "test-key-reference", java.util.Map.of());

    byte[] restored = service.decrypt(envelope, aad, java.util.Map.of());

    assertThat(restored).isEqualTo(plaintext);
}
~~~

Unit test dùng fake DataKeyProvider, không gọi KMS. Cần thêm test tamper:

- Sửa một byte ciphertext.
- Sửa nonce.
- Sửa wrapped DEK.
- Thay tenant/object AAD.
- Dùng key reference không tồn tại.
- Đổi format version/algorithm.
- Dùng envelope thiếu field hoặc field vượt kích thước cho phép.

Các trường hợp thay ciphertext, nonce hoặc AAD phải làm GCM authentication thất bại; không trả plaintext.

### 15.2. Test permission và provider adapter

Dùng KMS/Key Vault/Cloud KMS dev key:

1. Workload có quyền GenerateDataKey/WrapKey/Encrypt.
2. Workload có quyền Decrypt/Unwrap.
3. Principal không có quyền decrypt phải bị từ chối.
4. Key disabled hoặc version không còn usable phải tạo lỗi rõ.
5. Encryption context/AAD sai phải không giải mã được.
6. Cross-tenant object phải bị business authorization chặn trước khi unwrap.
7. Log/audit không chứa plaintext DEK, payload hoặc secret.

### 15.3. Kiểm thử rotation

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Tạo KEK version mới | Dữ liệu mới dùng version theo policy |
| Envelope cũ dùng KEK version cũ | Vẫn giải mã được trong thời gian retention |
| Rewrap DEK sang KEK mới | Ciphertext payload không đổi, envelope decrypt được |
| Disable key cũ quá sớm | Test phải phát hiện object/backup còn phụ thuộc |
| Re-encrypt với DEK mới | Plaintext trước/sau giống nhau, metadata mới hợp lệ |
| KMS timeout/429 | Retry có giới hạn, không lặp vô hạn |
| KMS unavailable | Fail closed với dữ liệu cần giải mã; không fallback raw key |

### 15.4. Kiểm thử khôi phục backup

Một quy trình backup chỉ hoàn chỉnh khi chứng minh có thể decrypt lại:

1. Tạo object và envelope trong môi trường dev.
2. Backup object, metadata và wrapped DEK.
3. Khôi phục sang bucket/account/project thử nghiệm.
4. Cấp quyền KMS theo quy trình recovery.
5. Giải mã và so sánh checksum plaintext.
6. Kiểm tra key version cũ còn khả dụng.
7. Ghi lại thời gian khôi phục và người thực hiện.

Không kiểm thử destruction trên key production để chứng minh backup. Dùng key riêng cho test destructive lifecycle.

## 16. Chọn mô hình theo yêu cầu

| Yêu cầu | Mô hình phù hợp | Lý do |
| --- | --- | --- |
| Bảo vệ disk/backup, service được phép đọc plaintext | SSE/TDE với provider-managed hoặc CMK | Minh bạch, ít code crypto |
| Kiểm soát key và audit thao tác decrypt của service | SSE với CMK | KMS policy và audit riêng |
| Storage operator không được đọc nội dung object | CSE envelope encryption | Storage chỉ lưu ciphertext |
| Chỉ mã hóa vài field PII trong database | Field-level CSE | Giới hạn phạm vi plaintext |
| File lớn cần streaming | Envelope + chunked AEAD | Không cần tải toàn bộ vào memory |
| Nhiều service/tenant có quyền khác nhau | DEK riêng theo object/tenant và KEK policy phù hợp | Tách blast radius và quyền decrypt |
| Cần tìm kiếm nội dung mã hóa | Cần thiết kế index/token riêng | Ciphertext thông thường không hỗ trợ search/filter trực tiếp |

Không nên áp dụng CSE cho mọi dữ liệu một cách máy móc. CSE có chi phí KMS, latency, key lifecycle và khả năng khôi phục cao hơn SSE. Chọn theo classification và threat model.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Upload thành công nhưng app không decrypt được | Thiếu wrapped DEK, sai key reference hoặc AAD | Kiểm tra envelope metadata và context |
| KMS trả AccessDenied/403 | Principal thiếu quyền key operation hoặc key policy từ chối | Kiểm tra đúng runtime identity, scope và policy |
| AES-GCM báo AEADBadTagException | Ciphertext/nonce/AAD sai, dữ liệu bị sửa hoặc DEK không đúng | Từ chối plaintext; điều tra integrity và metadata |
| KMS decrypt thành công nhưng AES fail | DEK không tương ứng ciphertext hoặc format mismatch | Kiểm tra version/algorithm/serialization |
| Object cũ không đọc được sau rotation | Key version cũ bị disable/destroy hoặc metadata bị mất | Phục hồi quyền/key theo quy trình; kiểm tra backup |
| SSE-KMS upload bị từ chối | Thiếu KMS GenerateDataKey hoặc key policy không cho S3 service/request | Kiểm tra bucket policy, IAM, key policy và encryption setting |
| Azure Storage CMK không hoạt động | Storage identity thiếu quyền Key Vault key hoặc key không khả dụng | Kiểm tra identity của Storage account, Key Vault network và role |
| GCS CMEK trả lỗi permission | Cloud Storage service agent thiếu quyền trên CryptoKey | Cấp role cho service agent đúng project/key |
| Latency tăng khi đọc file | KMS unwrap cho mỗi object hoặc retry | Cache metadata an toàn, tối ưu batch/stream và kiểm tra quota |
| Rotation không làm dữ liệu cũ đổi key | Rotation chỉ ảnh hưởng encryption operation mới | Lập kế hoạch rewrap/re-encrypt theo policy |
| Heap dump có plaintext/DEK | Plaintext tồn tại trong JVM memory | Giảm lifetime, kiểm soát dump, streaming và process access |

## 18. Bài tập thực hành tổng hợp

`document-service` cần lưu hợp đồng PDF và metadata cho nhiều tenant:

- Object storage bật SSE bằng customer-managed key.
- Nội dung PDF phải được CSE để storage operator không đọc được plaintext.
- Mỗi object có DEK AES-256-GCM riêng.
- DEK được wrap bởi KMS key theo môi trường.
- Metadata tenant/object được ràng buộc bằng AAD.
- Có quy trình rotation KEK không cần mã hóa lại payload nếu chỉ thay KEK.

**Nhiệm vụ:**

1. Chọn SSE-KMS/CMEK cho lớp storage và giải thích lợi ích của lớp SSE bổ sung.
2. Thiết kế envelope format có formatVersion, algorithm, keyReference, wrappedDek, nonce, ciphertext.
3. Tạo DEK riêng cho từng object, dùng AES-GCM và nonce 12 byte.
4. Gắn tenant ID/object ID vào AAD nhưng không đưa PII vào AWS KMS encryption context.
5. Cấp quyền decrypt chỉ cho service đọc hợp đồng; service upload chỉ có quyền cần thiết để tạo/wrap DEK nếu thiết kế cho phép.
6. Viết unit test tamper ciphertext và sai AAD.
7. Viết integration test KMS permission, key version và backup restore.
8. Rewrap DEK từ KEK cũ sang KEK mới, xác minh ciphertext payload không đổi.
9. Chỉ disable key cũ sau khi kiểm kê mọi object, backup và replica.

**Câu hỏi tự đánh giá:**

- Vì sao SSE-KMS không ngăn storage service trả plaintext cho principal có quyền đọc?
- SSE-C khác CSE ở đâu?
- Vì sao KMS chỉ wrap DEK thay vì mã hóa trực tiếp file PDF?
- Vì sao nonce GCM phải duy nhất với một DEK?
- AAD có được mã hóa không? Nên đặt tenant/object ID ở đâu?
- Khi đổi KEK, trường hợp nào chỉ cần rewrap DEK?
- Vì sao rotation không đồng nghĩa re-encryption?
- Principal nào cần quyền KMS khi dùng Azure Storage CMK hoặc GCS CMEK?
- Điều gì xảy ra nếu key cũ bị destroy trong khi backup vẫn cần decrypt?

**Đáp án định hướng:** SSE service giải mã khi principal được phép đọc; SSE-C vẫn mã hóa server-side còn CSE mã hóa trước khi gửi; DEK nhỏ giúp giảm giới hạn/latency KMS; nonce reuse phá vỡ GCM security; AAD được xác thực nhưng không mã hóa; rewrap giữ DEK nên payload không đổi; key rotation thường không tự xử lý ciphertext cũ; Storage service agent dùng CMK theo dịch vụ; mất key cũ có thể mất dữ liệu vĩnh viễn.

## 19. Tài liệu tham khảo chính thức

- [AWS KMS – GenerateDataKey](https://docs.aws.amazon.com/kms/latest/APIReference/API_GenerateDataKey.html): sinh plaintext data key và encrypted data key cho envelope encryption.
- [AWS KMS – Encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html): AAD của KMS, yêu cầu khớp khi decrypt và lưu ý metadata không bí mật.
- [AWS S3 – Using server-side encryption with AWS KMS keys](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingKMSEncryption.html): SSE-KMS, permissions và key behavior.
- [AWS S3 – Client-side encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingClientSideEncryption.html): mã hóa phía client và envelope concepts.
- [Microsoft Learn – Azure Storage encryption for data at rest](https://learn.microsoft.com/en-us/azure/storage/common/storage-service-encryption): encryption at rest và customer-managed keys.
- [Microsoft Learn – Customer-managed keys for Azure Storage](https://learn.microsoft.com/en-us/azure/storage/common/customer-managed-keys-overview): Key Vault/Managed HSM và identity của Storage.
- [Microsoft Learn – Key Vault cryptography](https://learn.microsoft.com/en-us/azure/key-vault/keys/about-keys-details): key types, cryptographic operations, wrap/unwrap và version.
- [Google Cloud – Cloud Storage encryption](https://cloud.google.com/storage/docs/encryption): Google-managed, CMEK và customer-supplied keys.
- [Google Cloud – Use customer-managed encryption keys](https://cloud.google.com/kms/docs/cmek): tích hợp CMEK, service agent và quyền KMS.
- [Google Cloud KMS – Encrypt and decrypt data](https://cloud.google.com/kms/docs/encrypt-decrypt): API Encrypt/Decrypt và giới hạn payload.
- [Google Cloud – Envelope encryption](https://cloud.google.com/kms/docs/envelope-encryption): DEK/KEK và mô hình mã hóa dữ liệu lớn.
- [Java Cryptography Architecture – Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html): AES-GCM, authenticated encryption và API JCA.

**Ghi nhớ:** SSE bảo vệ dữ liệu ở storage và thường minh bạch với ứng dụng; CSE giữ plaintext trong phạm vi ứng dụng được phép; envelope encryption dùng DEK để mã hóa payload và KMS/Key Vault để bảo vệ DEK. Thiết kế tốt phải giữ được **ciphertext, metadata, key reference, quyền unwrap, rotation và backup** đồng bộ trong suốt vòng đời dữ liệu.
