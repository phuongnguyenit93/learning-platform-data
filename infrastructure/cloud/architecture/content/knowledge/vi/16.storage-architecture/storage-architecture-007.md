# Mã hóa lưu trữ và kiểm soát truy cập dữ liệu

## 1. Bảo vệ dữ liệu phải đi cùng thiết kế lưu trữ

Một ứng dụng cloud có thể lưu dữ liệu ở nhiều nơi: relational database, object storage, block volume, file share, cache, snapshot, backup, queue, log và bản sao phân tích. Chỉ bật một tùy chọn “encryption at rest” trên database chưa đủ để chứng minh toàn bộ dữ liệu được bảo vệ. Cần biết **dữ liệu nào được lưu ở đâu, ai có thể đọc hoặc sửa, khóa mã hóa được quản lý thế nào, bản sao tồn tại bao lâu và làm sao khôi phục khi có sự cố**.

Trong module **CLOUD_ARCHITECTURE**, thiết kế lưu trữ phải xuất phát từ yêu cầu nghiệp vụ và được đánh giá cùng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected. Mã hóa làm giảm rủi ro khi dữ liệu lưu trữ hoặc truyền qua mạng bị truy cập trái phép; kiểm soát truy cập giới hạn những danh tính và workload được phép sử dụng dữ liệu; quản lý khóa và audit giúp duy trì khả năng bảo vệ trong toàn bộ vòng đời.

Sau bài này, bạn có thể:

- Phân loại dữ liệu và lập bản đồ nơi dữ liệu được lưu, sao chép và truyền đi.
- Phân biệt mã hóa at rest, in transit và encryption at the application/field level.
- Giải thích symmetric encryption, envelope encryption, KMS, HSM và key hierarchy.
- Thiết kế IAM/RBAC/ABAC, resource policy, network policy và quyền truy cập workload theo least privilege.
- Phân biệt quyền quản lý khóa với quyền đọc dữ liệu đã giải mã.
- Bảo vệ backup, snapshot, replica, log và dữ liệu xuất khỏi storage chính.
- Lập kế hoạch rotation, revocation, recovery và audit.
- Kiểm chứng trade-off giữa bảo mật, độ tin cậy, hiệu năng và chi phí.

## 2. Bắt đầu từ dữ liệu và threat model

Ví dụ xuyên suốt là **BookingCloud**, ứng dụng cho thuê thiết bị theo khung giờ. Hệ thống lưu hồ sơ khách hàng, booking, lịch thiết bị, ảnh sản phẩm, chứng từ thanh toán, log vận hành và báo cáo.

### 2.1. Phân loại dữ liệu trước khi chọn dịch vụ

| Nhóm dữ liệu | Ví dụ | Phân loại minh họa | Yêu cầu bảo vệ |
|---|---|---|---|
| Dữ liệu công khai | Ảnh thiết bị đã duyệt, danh mục công khai | Public | Bảo vệ tính toàn vẹn, nguồn nội dung và quyền ghi |
| Dữ liệu nghiệp vụ | Booking ID, slot, trạng thái đơn | Internal | Authentication, authorization, encryption, audit thay đổi |
| Dữ liệu cá nhân | Email, số điện thoại, địa chỉ giao nhận | Confidential/personal | Hạn chế truy cập, encryption, purpose/retention, log redaction |
| Dữ liệu tài chính | Payment reference, hóa đơn, đối soát | Restricted tùy chính sách | Quyền rất hẹp, audit đầy đủ, retention và integrity |
| Credential/secret | DB password, API key, private key | Secret | Secret manager/HSM, rotation, không ghi vào log hoặc image |
| Telemetry | Trace, error, access log | Operational, có thể chứa PII | Minimize/redact, RBAC, retention và audit |
| Backup/snapshot | Bản sao database và volume | Bằng hoặc cao hơn dữ liệu gốc | Mã hóa, quyền riêng, retention, restore test và kiểm soát xóa |

Mức phân loại cụ thể phải theo chính sách doanh nghiệp và quy định áp dụng; không có một nhãn phổ quát tự động xác định mọi nghĩa vụ pháp lý. Một backup của dữ liệu cá nhân vẫn là dữ liệu cá nhân; chuyển dữ liệu sang một bucket khác không làm giảm độ nhạy cảm.

### 2.2. Vẽ data lifecycle

Theo dõi mỗi loại dữ liệu từ lúc thu thập đến khi xóa:

1. **Create/collect:** dữ liệu phát sinh từ client, đối tác, import hoặc hệ thống nội bộ.
2. **Ingest:** qua TLS, API gateway, identity/authentication và validation.
3. **Process:** đi qua compute, queue, cache hoặc workflow.
4. **Store:** database, object, block/file storage và index.
5. **Share/use:** đọc bởi service khác, analyst, partner hoặc công cụ vận hành.
6. **Copy/backup:** replica, snapshot, export, archive, log và disaster recovery region.
7. **Retain/delete:** hết mục đích sử dụng, hết thời hạn giữ hoặc có yêu cầu xóa; phải xét cả bản sao và legal hold.

~~~mermaid
flowchart LR
    C["Collect / API"] --> P["Process / compute"]
    P --> D[("Primary database")]
    P --> O[("Object storage")]
    D --> R["Read replica / cache"]
    D --> B["Backup / snapshot"]
    O --> A["Archive / replication"]
    P --> L["Logs / traces"]
    R --> U["Authorized users / services"]
    B --> DR["Recovery environment"]
    A --> DR
    L --> OBS["Operations / security teams"]
    D --> X["Retention / deletion"]
    O --> X
    B --> X
    L --> X
~~~

Sơ đồ là góc nhìn vòng đời dữ liệu. Từng mũi tên cần được gắn owner, identity, mục đích, transport security, retention và quyền. Replica, cache, backup và telemetry thường bị bỏ quên khi chỉ review database chính.

### 2.3. Xác định threat model

Hãy hỏi ai có thể truy cập, từ đâu, với quyền nào và hậu quả là gì:

- Kẻ tấn công lấy được ổ đĩa, snapshot, backup hoặc object export.
- Một IAM role hoặc service account bị lộ/chiếm quyền.
- Nhân viên có quyền rộng tải dữ liệu khách hàng không đúng mục đích.
- Application bị khai thác và dùng quyền database của service để đọc tenant khác.
- Secret hoặc encryption key bị lộ trong source code, image, log hoặc CI artifact.
- Người có quyền xóa dữ liệu xóa cả backup hoặc khóa cần thiết để restore.
- Một workflow gửi dữ liệu qua endpoint sai hoặc provider bên thứ ba ngoài dự kiến.
- Log/trace/DLQ chứa token, email, địa chỉ hoặc payload nhạy cảm.

Mã hóa at rest giúp bảo vệ một số tình huống như media bị lấy ra khỏi môi trường chạy; nó không ngăn được một application role hợp lệ đọc dữ liệu rồi xuất đi. Vì vậy cần phối hợp mã hóa, authorization, network controls, monitoring và data minimization.

## 3. Ba lớp bảo vệ: at rest, in transit và in use

### 3.1. Encryption at rest

Mã hóa at rest bảo vệ dữ liệu khi được lưu trên media hoặc trong dịch vụ lưu trữ. Với cloud managed storage, provider thường cung cấp server-side encryption; tùy dịch vụ, mã hóa có thể được bật mặc định hoặc cần cấu hình.

Đối tượng cần kiểm tra:

- Database files, tablespace, transaction logs, temporary files và automated backups.
- Object và các version của object, multipart upload còn dang dở, replication destination.
- Block volume, file share và local/ephemeral disk nếu chứa dữ liệu nhạy cảm.
- Snapshot, image, backup copy và archive.
- Search index, cache persistence, queue storage và data warehouse.

Không suy ra mọi thành phần phụ trợ đã được mã hóa chỉ vì database có encryption at rest. Cần kiểm tra tài liệu dịch vụ để biết phạm vi mã hóa, key ownership, default behavior, cách xử lý bản sao và giới hạn.

### 3.2. Encryption in transit

Mã hóa in transit bảo vệ dữ liệu trên đường truyền giữa client, service, database, queue, storage endpoint, region và bên thứ ba. TLS/HTTPS là lựa chọn phổ biến cho kết nối IP; một số kết nối nội bộ hoặc giao thức riêng có cơ chế bảo vệ tương ứng.

| Đường truyền | Câu hỏi kiểm soát |
|---|---|
| Browser/mobile → API | TLS, hostname/certificate validation, token và session security |
| API → database | TLS connection, kiểm tra chứng chỉ server, DB identity/role |
| API → object storage | HTTPS, workload identity, bucket/object policy |
| Service → queue | TLS, publisher/consumer identity và quyền topic/queue |
| Worker → payment/email provider | TLS, endpoint allowlist, secret/token scope |
| Primary → replica/backup region | Encryption, peer identity, network route và key availability |
| App → log/trace backend | TLS, payload minimization và quyền ghi/đọc |

TLS chỉ bảo vệ dữ liệu trên chặng kết nối tương ứng. Nếu TLS kết thúc ở proxy hoặc gateway, dữ liệu được giải mã tại đó và hop tiếp theo cần được đánh giá riêng. Mã hóa in transit cũng không chứng minh service đích là đúng nếu client bỏ qua certificate/hostname verification.

### 3.3. Encryption in use và application-level encryption

Trong lúc ứng dụng xử lý dữ liệu, plaintext có thể xuất hiện trong memory, process, runtime hoặc tại service giải mã. Một số workload nhạy cảm có thể cân nhắc confidential computing/Trusted Execution Environment (TEE) để giảm khả năng host/hypervisor quan sát memory trong các mô hình được hỗ trợ. Tuy nhiên, TEE có giới hạn về workload, threat model, attestation và vận hành; nó không thay authorization hoặc input validation.

**Field-level/application-level encryption** mã hóa một số trường nhạy cảm trước khi ghi vào database. Cách này có thể giảm khả năng database operator hoặc một số truy vấn đọc plaintext, nhưng làm phức tạp search, indexing, sorting, key rotation và ứng dụng. Không phải trường nào cũng cần mã hóa riêng; cần xác định ai được phép giải mã và chức năng nào cần plaintext.

| Phương án | Bảo vệ tốt trong tình huống | Giới hạn |
|---|---|---|
| Storage encryption at rest | Media/snapshot bị truy cập ngoài dịch vụ hoặc thiếu quyền giải mã khóa | Application/service có quyền hợp lệ vẫn có thể đọc plaintext |
| TLS in transit | Nghe lén/sửa dữ liệu trên đường truyền | Không bảo vệ endpoint đã bị chiếm quyền |
| Field-level encryption | Giới hạn plaintext ở một số service/key holder | Truy vấn, tìm kiếm và vận hành khóa phức tạp |
| Confidential computing | Một số rủi ro quan sát memory từ host/platform | Phụ thuộc TEE, attestation và workload support |

## 4. Thuật toán và mô hình mã hóa cơ bản

### 4.1. Symmetric encryption

Mã hóa đối xứng dùng cùng một secret key cho encrypt và decrypt. Thuật toán như AES-GCM có thể cung cấp confidentiality và integrity/authentication khi nonce và key được sử dụng đúng cách.

Nguyên tắc thực hành:

- Chọn thuật toán và mode được chuẩn hóa, được thư viện/provider hỗ trợ.
- Không tự thiết kế thuật toán hoặc protocol mã hóa.
- Dùng nonce/IV đúng quy tắc của mode; đặc biệt không tái sử dụng nonce theo cách nguy hiểm với cùng key.
- Xác minh authentication tag khi giải mã; dữ liệu bị sửa phải bị từ chối.
- Giữ key riêng khỏi ciphertext và bảo vệ cả bản backup của key.
- Ghi metadata như key ID, algorithm/version và context cần thiết để phục hồi/rotation.

### 4.2. Asymmetric cryptography

Mã hóa bất đối xứng dùng cặp public key/private key. Public key có thể được chia sẻ; private key phải được bảo vệ. Mô hình này thường dùng cho key exchange, chữ ký số, identity và bootstrap trust.

Không nên mặc định mã hóa toàn bộ file lớn bằng RSA. Thực tế thường dùng hybrid/envelope encryption: dùng public key hoặc KMS để bảo vệ một data key đối xứng, còn data key mã hóa payload bằng thuật toán đối xứng hiệu quả.

### 4.3. Hash và encryption là hai việc khác nhau

- **Encryption** có thể giải mã trở lại nếu có key phù hợp.
- **Cryptographic hash** tạo digest một chiều; dùng kiểm tra integrity hoặc lưu verifier trong một số trường hợp, không dùng để khôi phục plaintext.
- **Password hashing** cần thuật toán chuyên dụng có salt và cost factor phù hợp, không lưu password bằng reversible encryption hoặc hash nhanh thông thường.
- **Digital signature** xác nhận nguồn gốc/tính toàn vẹn theo public-key verification; không tự mã hóa nội dung.

## 5. Envelope encryption và KMS

Với lượng dữ liệu lớn, ứng dụng/storage service thường mã hóa bằng một **Data Encryption Key (DEK)**. Một **Key Encryption Key (KEK)** hoặc key trong KMS bảo vệ DEK. Ciphertext và encrypted DEK được lưu cùng metadata cần thiết.

### 5.1. Luồng envelope encryption

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Application
    participant KMS as Key Management Service
    participant Store as Encrypted storage

    App->>KMS: Generate data key under KEK
    KMS-->>App: Plaintext DEK + encrypted DEK
    App->>App: Encrypt payload with plaintext DEK
    App->>App: Remove plaintext DEK from use
    App->>Store: Store ciphertext + encrypted DEK + metadata
    Store-->>App: Write confirmed
    App->>Store: Read ciphertext + encrypted DEK
    Store-->>App: Encrypted object and key metadata
    App->>KMS: Decrypt encrypted DEK (authorized identity)
    KMS-->>App: Plaintext DEK
    App->>App: Verify tag and decrypt payload
~~~

Sơ đồ mô tả mô hình tổng quát. Với managed database/object storage, chính dịch vụ lưu trữ có thể thực hiện server-side encryption và dùng KMS thay cho application tự cầm plaintext DEK. Cần hiểu ai gọi KMS, key grant/policy nào được dùng và dữ liệu đã giải mã xuất hiện ở đâu.

### 5.2. Vai trò của KMS

Key Management Service thường hỗ trợ tạo/import key theo loại dịch vụ; quản lý key policy, IAM grants và quyền dùng key; encrypt/decrypt hoặc generate data key; rotation theo chính sách; disable, schedule deletion hoặc revoke grant; tích hợp với database, object storage, volume, backup và service khác.

**KMS không tự động giải quyết mọi quyền dữ liệu.** Một role có quyền đọc object vẫn cần quyền giải mã nếu object dùng customer-managed key; ngược lại, quyền gọi KMS decrypt không tự cấp quyền đọc object. Quyền thường là giao của nhiều policy: identity policy, resource policy, key policy/grant, network và service-specific controls.

### 5.3. Provider-managed key, cloud-managed key và customer-managed key

| Kiểu quản lý khóa | Ai chịu trách nhiệm chính | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Provider-managed/default key | Provider quản lý lifecycle, khách cấu hình ít | Dễ sử dụng, ít vận hành | Ít khả năng kiểm soát policy, audit/rotation tùy dịch vụ |
| Customer-managed key trong KMS | Khách hàng kiểm soát policy, grants và lifecycle; provider vận hành KMS infrastructure | Kiểm soát truy cập, disable/revoke, audit và separation of duties tốt hơn | Cần owner, rotation, quota/cost, recovery và governance |
| External/HSM-backed key | Tổ chức hoặc dịch vụ HSM quản lý một phần key custody | Yêu cầu kiểm soát/custody cao hơn | Độ phức tạp, latency, availability và trách nhiệm vận hành tăng |

Tên gọi khác nhau giữa cloud provider. Đọc đúng tài liệu sản phẩm: “customer-managed” không nhất thiết có nghĩa key material không bao giờ nằm trong hạ tầng provider; mức HSM, exportability, region scope và recovery khác nhau.

## 6. Vòng đời khóa: tạo, dùng, xoay vòng và thu hồi

Khóa mã hóa là một tài sản cần quản lý như một dịch vụ quan trọng:

1. **Create/provision:** tạo key trong KMS/HSM hoặc import theo quy trình được kiểm soát.
2. **Classify/assign owner:** ghi purpose, data classification, environment, owner, region và resource dependencies.
3. **Authorize:** policy riêng cho administrator, key user, auditor và recovery role.
4. **Use:** workloads gọi encrypt/decrypt/generate data key bằng identity ngắn hạn; tránh xuất plaintext key khi không cần.
5. **Rotate:** thay key version theo policy/trigger, kiểm thử khả năng đọc dữ liệu cũ.
6. **Monitor:** cảnh báo thao tác bất thường, grant/policy change, decrypt spikes và key expiry nếu loại key có hạn.
7. **Disable/revoke:** phản ứng khi nghi bị lộ; xác định ngay ảnh hưởng đến workload đang chạy.
8. **Retire/delete:** chỉ xóa khi mọi dữ liệu phụ thuộc đã được chuyển/retention hoàn tất và có phê duyệt.

### 6.1. Rotation không phải lúc nào cũng cần mã hóa lại toàn bộ dữ liệu ngay

Một số KMS hỗ trợ automatic key rotation bằng cách giữ key material/version cũ để vẫn giải mã ciphertext được tạo trước đó; hành vi cụ thể phụ thuộc key type và provider. Với envelope encryption, có thể rewrap encrypted DEK dưới KEK version mới mà không phải đọc và mã hóa lại toàn bộ payload, nếu thiết kế và dịch vụ hỗ trợ.

Phân biệt:

- **Rotate KEK/KMS key:** thay phiên bản khóa dùng bảo vệ data key.
- **Rotate DEK:** tạo data key mới cho dữ liệu hoặc object mới.
- **Re-encrypt data:** giải mã dữ liệu rồi mã hóa lại bằng key/algorithm mới.
- **Rewrap DEK:** giải mã DEK bằng KEK cũ rồi mã hóa lại DEK bằng KEK mới, không nhất thiết đụng tới payload ciphertext.

Không khẳng định “bật automatic rotation là mọi dữ liệu cũ đã được re-encrypt”. Cần xác minh semantics của dịch vụ và có kế hoạch cho dữ liệu, backup và key version.

### 6.2. Rủi ro khi disable hoặc delete key

Nếu key cần để giải mã backup bị disable, deleted hoặc mất quyền, dữ liệu có thể vẫn tồn tại nhưng không thể truy cập. Key deletion có thể gây mất dữ liệu không thể phục hồi.

Trước khi disable/delete:

- Tra cứu resource, snapshot, backup, object version và region phụ thuộc key.
- Xác định có bản mã nào cần giữ theo retention/legal hold không.
- Test đọc dữ liệu bằng key version mới hoặc recovery key.
- Có approval hai người/role separation với thao tác phá hủy.
- Dùng deletion waiting period/pending deletion nếu provider hỗ trợ; theo dõi hủy lịch xóa khi phát hiện phụ thuộc.
- Lưu audit và xác nhận sau thao tác.

Một key không có owner hoặc không có inventory là rủi ro availability nghiêm trọng, không chỉ là vấn đề bảo mật.

## 7. Kiểm soát truy cập: ai được làm gì với dữ liệu?

Encryption và authorization giải quyết hai câu hỏi khác nhau:

- Mã hóa: người không có khả năng giải mã có đọc được nội dung hữu ích không?
- Authorization: identity nào được phép thực hiện hành động nào trên resource nào, trong điều kiện nào?

Ngay cả khi ciphertext được bảo vệ, một service role bị cấp quyền decrypt/read quá rộng vẫn có thể xuất dữ liệu plaintext.

### 7.1. Các lớp policy

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Identity/IAM policy | Role/user nào được gọi action? | Booking API role được đọc một số prefix object |
| Resource policy | Resource chấp nhận principal nào? | Bucket policy chỉ cho phép account/role được duyệt |
| Key policy/grant | Identity nào được dùng key và action nào? | Worker có decrypt key phục vụ thumbnail |
| Network control | Traffic đến resource từ đâu? | Private endpoint, security group, firewall, egress restriction |
| Application authorization | User được đọc record nào? | Chủ booking hoặc staff có quyền xem đơn |
| Data/tenant policy | Tenant, row hoặc object scope nào? | Tenant A không đọc object thuộc tenant B |

Các lớp này bổ sung nhau; một lớp allow không nên vô tình mở rộng toàn bộ hệ thống nếu lớp khác thiếu kiểm soát.

### 7.2. RBAC và ABAC

**Role-Based Access Control (RBAC)** cấp quyền theo role:

| Role | Quyền ví dụ |
|---|---|
| booking-api | Đọc/ghi booking qua API hoặc DB role giới hạn |
| thumbnail-worker | Đọc object đầu vào, ghi thumbnail output |
| backup-service | Tạo backup theo phạm vi được duyệt |
| data-analyst | Đọc view đã mask/aggregate, không đọc credential |
| security-auditor | Đọc audit log, không sửa dữ liệu nghiệp vụ |
| key-admin | Quản trị policy/lifecycle key, không mặc định có quyền đọc plaintext business data |

**Attribute-Based Access Control (ABAC)** quyết định quyền theo thuộc tính như environment, data classification, tenant, resource tag, purpose, network identity hoặc thời gian. Ví dụ role được đọc object chỉ khi environment=production, data-domain=booking và tenant scope phù hợp.

RBAC dễ quản lý khi số role nhỏ, nhiệm vụ ổn định. ABAC linh hoạt hơn ở môi trường nhiều tenant/resource nhưng policy có thể khó debug. Một thiết kế thực tế có thể kết hợp RBAC cho nhóm nhiệm vụ và ABAC cho scope tài nguyên.

### 7.3. Least privilege và separation of duties

- Cấp quyền nhỏ nhất cần thiết và trong thời gian cần thiết.
- Ưu tiên role/workload identity ngắn hạn thay cho access key tĩnh.
- Tách quyền tạo key, sử dụng key, sửa policy, đọc backup và xóa key.
- Production role không dùng chung với dev/test nếu có thể.
- Hạn chế quyền wildcard trên resource/action; dùng resource ARN/prefix/condition cụ thể.
- Định kỳ xem quyền unused, role kế thừa và policy drift.
- Truy cập break-glass phải có phê duyệt, MFA, thời hạn, audit và review sau sự cố.

## 8. Ví dụ policy cho BookingCloud

### 8.1. Bản đồ identity và data access

~~~mermaid
flowchart TB
    subgraph APP["Application identities"]
      API["booking-api role"]
      TH["thumbnail-worker role"]
      AN["analyst role"]
      BK["backup role"]
    end
    subgraph DATA["Data resources"]
      DB[("Booking DB")]
      BUCKET[("Object bucket")]
      SNAP[("Backup / snapshots")]
    end
    subgraph KEYS["Key management"]
      KDB["Database KMS key"]
      KOBJ["Object KMS key"]
      KBACK["Backup KMS key"]
    end
    API -->|"Read/write scoped rows"| DB
    API -->|"Put approved object"| BUCKET
    TH -->|"Read source prefix"| BUCKET
    TH -->|"Write thumbnail prefix"| BUCKET
    AN -->|"Read masked view"| DB
    BK -->|"Create/copy backup"| SNAP
    DB --> KDB
    BUCKET --> KOBJ
    SNAP --> KBACK
~~~

Sơ đồ minh họa các quyền logic. Trong một cloud cụ thể, DB/object storage gọi KMS thay cho application hoặc application gọi KMS trực tiếp; quyền service-linked role/grant có thể khác. Phải kiểm tra principal thực sự xuất hiện trong audit log.

### 8.2. Ví dụ policy theo nguyên tắc

Ví dụ YAML chính sách logic cho worker:

~~~yaml
identity: thumbnail-worker
environment: production
permissions:
  - action: object.read
    resource: bucket://booking-uploads/source/*
  - action: object.write
    resource: bucket://booking-assets/thumbnails/*
  - action: key.decrypt
    resource: key://booking-uploads-key
conditions:
  requireTls: true
  allowedWorkloadIdentity: booking-thumbnail-service
  denyPublicAccess: true
  denyOtherTenants: true
explicitlyDenied:
  - object.delete
  - database.admin
  - key.scheduleDeletion
~~~

Đây là pseudoconfiguration, không phải policy syntax dùng được trực tiếp cho AWS/Azure/GCP. Khi triển khai, cần map sang IAM/resource policy/KMS grants đúng provider và kiểm tra cả quyền gián tiếp như role assumption, wildcard, permissions boundary và inherited group.

### 8.3. Quyền database không thay phân quyền nghiệp vụ

Database role của Booking API có thể được phép SELECT/INSERT/UPDATE trên một số bảng. Nhưng API vẫn phải kiểm tra người dùng hiện tại có quyền đọc booking cụ thể hay không.

~~~sql
SELECT booking_id, status, created_at
FROM bookings
WHERE booking_id = :booking_id
  AND tenant_id = :tenant_id;
~~~

Điều kiện tenant/user scope phải lấy từ identity đã xác minh, không tin tenant_id tùy ý do client gửi. Có thể áp dụng row-level security nếu database hỗ trợ và được cấu hình đúng; tuy vậy cần kiểm tra connection pooling/session context để không rò quyền giữa request.

## 9. Bảo vệ từng loại storage

### 9.1. Relational database

Kiểm tra:

- Encryption at rest cho storage, transaction log, automated backup và snapshot.
- TLS cho connection; verify server identity/certificate.
- Database authentication bằng IAM/managed identity hoặc credential quản lý trong secret manager.
- DB role tối thiểu; tách schema/table/operation theo service.
- Row-level access hoặc application authorization cho tenant/object.
- Audit connection, role grant, privilege change và truy cập nhạy cảm.
- Backup/PITR, retention, deletion, encryption key dependency và restore test.

Encryption at rest không thay parameterized query, SQL injection defense, masking hoặc giới hạn quyền đọc bảng.

### 9.2. Object storage

Object storage thường có bucket/container-level policy và object-level metadata/version. Kiểm tra public access block/default private policy, access point và cross-account access; encryption default và customer-managed key nếu yêu cầu; TLS-only policy, signed URL expiry và giới hạn method/scope; versioning, object lock/retention và lifecycle transition; replication destination, inventory report, multipart upload và delete marker; access log/data events và quyền xóa version.

Signed URL là bearer capability: ai có URL trong thời gian hiệu lực có thể thực hiện hành động được ký. Không log URL đầy đủ, không đặt expiry quá dài và chỉ cấp method/object cần thiết.

### 9.3. Block và file storage

Với block volume và file share:

- Bật mã hóa cho volume mới và xác minh snapshot/clone cũng được mã hóa theo yêu cầu.
- Kiểm soát attach/mount bằng identity, security group/network và storage export policy.
- Tách volume theo workload/tenant khi blast radius hoặc quyền yêu cầu.
- Bảo vệ filesystem permission, ownership, mount option và secret trên node.
- Kiểm tra vùng dữ liệu, replica, snapshot, key và khả năng attach khi failover.

Encryption của volume không bảo vệ khỏi process có quyền mount volume và đọc file. Quyền ở OS/filesystem và application vẫn cần giới hạn.

### 9.4. Cache, queue, search và analytics

Những service “tạm” vẫn có thể chứa dữ liệu nhạy cảm:

- Cache có thể lưu token, profile hoặc session; đặt TTL, TLS, authentication và private networking.
- Queue có thể giữ payload trong retention/replay/DLQ; tối thiểu hóa dữ liệu, mã hóa và giới hạn quyền đọc.
- Search index có thể sao chép nhiều trường PII; áp mapping, field access hoặc masking.
- Data lake/warehouse có thể có raw zone và curated zone; dùng catalog/classification, column/row policy, lineage và retention.
- Log/traces có thể ghi request body/header; redaction ở nguồn và kiểm soát quyền truy cập.

## 10. Backup, snapshot, replica và disaster recovery

Backup không chỉ là một bản copy khác. Nó thường chứa đầy đủ hoặc nhiều hơn dữ liệu gốc và có thể bị kẻ tấn công nhắm đến để vô hiệu hóa khả năng khôi phục.

### 10.1. Các yêu cầu phải xác minh

| Vấn đề | Câu hỏi |
|---|---|
| Encryption | Backup/snapshot có mã hóa và dùng key nào? |
| Access | Ai tạo, đọc, copy, restore và delete? |
| Isolation | Backup có account/project/vault tách biệt không? |
| Immutability | Có retention lock/WORM/object lock phù hợp không? |
| Cross-region | Key có tồn tại và được phép dùng ở region đích không? |
| Retention | Lịch giữ và xóa có phù hợp policy/legal hold? |
| Integrity | Có checksum, catalog và xác minh backup complete? |
| Recovery | Có test restore theo RTO/RPO và runbook không? |

~~~mermaid
flowchart LR
    DB[("Primary DB")] --> BK["Backup service"]
    BK --> ENC["Encrypt with backup key"]
    ENC --> VAULT["Isolated backup vault"]
    VAULT --> COPY["Cross-region/account copy"]
    COPY --> REC["Restore in recovery environment"]
    REC --> VERIFY["Verify data + application"]
    VERIFY --> READY["Recovery ready"]
~~~

Một snapshot thành công chưa chứng minh ứng dụng có thể phục hồi. Cần thử restore database, key permission, network, secrets, schema, application và business transaction. Nếu key chỉ tồn tại ở region nguồn hoặc recovery role không được dùng key, backup copy có thể vô dụng.

### 10.2. Immutable backup và separation of duties

Ransomware hoặc tài khoản bị chiếm có thể tìm cách xóa backup cùng dữ liệu chính. Có thể giảm rủi ro bằng backup account/vault riêng, access cross-account hạn chế; immutable retention/object lock theo policy; role tạo backup không có quyền xóa; role xóa cần approval riêng; MFA/approval cho thao tác phá hủy; alert khi retention lock hoặc backup policy bị thay; key quản lý riêng và quy trình recovery có kiểm thử.

Immutable không đồng nghĩa lưu vô hạn. Phải cân bằng retention, legal hold, privacy deletion, chi phí và quy định áp dụng.

## 11. Rotation, migration và re-encryption khi thay khóa

Thay key có thể là hoạt động bình thường hoặc ứng phó key compromise. Hai trường hợp cần mức khẩn cấp và kế hoạch khác nhau.

### 11.1. Rotation định kỳ

1. Kiểm tra loại key và khả năng automatic rotation.
2. Xác định ciphertext nào phụ thuộc key/version.
3. Bật hoặc tạo key version mới theo quy trình.
4. Kiểm tra dịch vụ vẫn đọc được dữ liệu cũ.
5. Nếu cần, rewrap DEK hoặc re-encrypt payload theo batch.
6. Theo dõi lỗi decrypt, latency và usage của key version cũ.
7. Chỉ retire key cũ khi hết phụ thuộc, retention và restore path.

### 11.2. Khi nghi ngờ key bị lộ

- Xác định phạm vi: key, principal, workload, ciphertext, thời điểm và khả năng attacker có ciphertext.
- Disable/restrict key hoặc revoke grant theo incident playbook; cân nhắc tác động availability trước thao tác diện rộng.
- Rotate credentials và workload identity có liên quan.
- Tạo key mới và re-encrypt/rewrap dữ liệu bị ảnh hưởng.
- Kiểm tra backup, replica, export, log và bản copy ngoài region.
- Tìm decrypt bất thường, policy change và data exfiltration trong audit.
- Đánh giá nghĩa vụ thông báo và lưu bằng chứng theo incident response process.

Không xóa key ngay khi nghi bị lộ nếu điều đó phá hủy khả năng điều tra hoặc khôi phục. Cần cô lập và kiểm soát quyền theo playbook, rồi quyết định lifecycle dựa trên phạm vi thực tế.

## 12. Audit và phát hiện truy cập bất thường

Mã hóa/permissions là preventive controls; audit và detection giúp phát hiện khi kiểm soát bị lạm dụng hoặc cấu hình sai.

Nên ghi nhận principal/role/service identity đã truy cập resource; action read/write/delete/decrypt/grant/rotate/disable/schedule deletion; resource/key ID, environment/region và policy context cần thiết; thời gian, source network, request ID/correlation ID và kết quả; thay đổi IAM/resource/key policy và người phê duyệt; access tới backup vault, snapshot, DLQ và export.

Không ghi plaintext data, token hoặc private key vào audit log. Audit log nên được bảo vệ chống sửa/xóa bởi chính workload được audit; dùng account/project hoặc sink có quyền riêng, retention và integrity control.

### 12.1. Các tín hiệu cảnh báo

- Một role đột nhiên decrypt nhiều object hoặc nhiều customer/tenant.
- Truy cập từ region/network/source identity chưa từng thấy.
- Nhiều lần AccessDenied liên tiếp sau thay policy.
- Key disable, grant mới, policy wildcard hoặc schedule deletion ngoài change window.
- Backup vault bị xóa/retention lock thay đổi.
- Public access/bucket policy hoặc database network exposure thay đổi.
- DLQ/export/log truy cập tăng bất thường.

Một alert không tự kết luận có tấn công. Cần enrichment với deployment change, owner, workload baseline và incident response.

## 13. Thiết kế mẫu cho BookingCloud

| Thành phần | Dữ liệu | Encryption | Identity/access | Audit/recovery |
|---|---|---|---|---|
| Booking DB | Booking, customer reference | At rest + TLS | API DB role; application-level tenant checks | DB audit, backup/PITR, restore test |
| Customer contact table/fields | Email, phone | At rest; field-level nếu threat model yêu cầu | Chỉ service cần dùng contact; masking cho analyst | Access log, retention/deletion workflow |
| Object bucket | Ảnh gốc, thumbnail | At rest với key phù hợp + HTTPS | Upload/read role theo prefix; public chỉ cho asset đã duyệt | Versioning, lifecycle, access events, backup |
| Queue/event | Booking event, processing task | At rest/in transit theo dịch vụ | Producer/consumer permission riêng | Retention, DLQ, replay audit |
| Backup vault | DB/volume/object copies | Key riêng hoặc policy được duyệt | Backup role tạo; recovery role restore; delete tách riêng | Immutable retention, cross-region restore test |
| Logs/traces | Request metadata, errors | At rest + TLS ingest | App ghi; ops/security đọc theo nhiệm vụ | Redaction, retention, tamper protection |
| KMS | KEK/DEK protection | HSM/KMS theo dịch vụ | Key admin và key user tách biệt | Key policy audit, rotation, recovery |

Không nhất thiết dùng một key cho mọi resource. Tách key theo data domain, environment, region hoặc blast radius khi giúp quản lý quyền và incident tốt hơn; tránh tạo quá nhiều key tới mức không quản lý nổi owner/rotation.

## 14. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi review | Bằng chứng cần có |
|---|---|---|
| **Operational Excellence** | Ai sở hữu key, policy, backup và rotation? Khi decrypt lỗi ai xử lý? | Key inventory, IaC, runbook, alert, audit và restore drill |
| **Security** | Dữ liệu có được mã hóa ở mọi chặng cần thiết? Quyền đọc/decrypt có tối thiểu? | Threat model, IAM/resource/key policy, TLS verification, access review |
| **Reliability** | Disable/rotation key hoặc mất region có làm hệ thống không đọc được dữ liệu? | Key recovery, cross-region key design, backup/restore test, RTO/RPO |
| **Performance Efficiency** | KMS calls, field-level encryption và audit ảnh hưởng latency/throughput? | p95/p99, cache/key reuse có kiểm soát, load test và quota |
| **Cost Optimization** | KMS request, HSM, log retention, backup và re-encryption tốn bao nhiêu? | Cost theo key/request/data volume và retention |
| **Sustainability** | Có lưu trữ/bản sao thừa hoặc giữ dữ liệu lâu hơn mục đích? | Retention, lifecycle, duplicate copy inventory và deletion evidence |

Managed encryption giảm công việc vận hành nhưng không xóa trách nhiệm về phân quyền, key lifecycle và kiểm chứng restore. Một cấu hình bảo mật chỉ có ý nghĩa khi tổ chức vận hành nó đúng qua thay đổi và sự cố.

## 15. Bài thực hành: review chính sách lưu trữ và quyền

Một nhóm đề xuất:

> “Dùng một bucket và một KMS key cho tất cả môi trường. Tất cả backend dùng chung role admin để đọc object. Backup nằm trong cùng account với dữ liệu chính. Log lưu nguyên request body để dễ debug. Database đã bật encryption at rest nên không cần TLS nội bộ.”

Hãy review thiết kế:

**Bài 1 — Data inventory:** liệt kê dữ liệu BookingCloud, phân loại và nơi tồn tại gồm primary DB, object, cache, queue, log, snapshot và backup.

**Bài 2 — Encryption:** vẽ đường truyền từ client tới API, API tới DB/object/queue, replica và backup. Nêu chặng cần TLS, dữ liệu nào cần at-rest encryption và trường hợp nên cân nhắc field-level encryption.

**Bài 3 — Key management:** đề xuất key separation theo environment/data domain, role key admin/key user, rotation, recovery và quy trình xử lý key compromise.

**Bài 4 — Authorization:** thiết kế role cho booking API, thumbnail worker, analyst, backup và auditor. Viết nguyên tắc bucket/resource/key policy; phân biệt quyền object read và quyền KMS decrypt.

**Bài 5 — Backup:** thiết kế vault tách biệt, immutability/retention, cross-region copy và restore test. Chỉ ra vì sao backup cùng account có blast radius lớn.

**Bài 6 — Audit:** chọn ít nhất năm event cần cảnh báo, ví dụ decrypt spike, key policy change, public bucket access, backup deletion và access chéo tenant.

**Bài 7 — Trade-off:** so sánh provider-managed key, customer-managed KMS key và HSM-backed key về kiểm soát, availability, chi phí, latency và trách nhiệm.

### Khung kết quả tự kiểm tra

| Đề xuất ban đầu | Vấn đề | Hướng cải tiến |
|---|---|---|
| Một role admin dùng chung | Blast radius lớn, khó quy trách nhiệm | Role theo workload, least privilege, short-lived identity |
| Một key cho mọi môi trường | Dev compromise ảnh hưởng production; policy khó tách | Key/domain separation theo environment và sensitivity |
| Backup cùng account | Attacker xóa cả data lẫn recovery copy | Backup vault/account riêng, immutable retention |
| Log nguyên request body | Có thể lộ token và PII | Redaction ở nguồn, schema log tối thiểu |
| Chỉ mã hóa database at rest | Không bảo vệ chặng truyền hoặc resource khác | TLS, bucket/queue/backup encryption và permission review |
| Quyền đọc object mặc định đồng nghĩa decrypt | Hai lớp policy khác nhau | Kiểm tra resource policy và key policy/grant riêng |

Đây là hướng phân tích. Cấu hình cuối phải theo provider và chính sách dữ liệu thực tế.

## 16. Checklist trước khi đưa storage vào production

- [ ] Có data inventory, classification, owner, purpose và retention cho từng data store/copy.
- [ ] Encryption at rest đã bật/được xác minh cho DB, object, volume, snapshot, backup, cache/queue có dữ liệu nhạy cảm.
- [ ] TLS/hostname verification được áp dụng cho các chặng truyền cần bảo vệ.
- [ ] Đã xác định nơi plaintext xuất hiện khi app/service xử lý và nơi cần field-level encryption/TEE nếu threat model yêu cầu.
- [ ] Key có owner, purpose, environment, policy, rotation và recovery path.
- [ ] Key admin, key user, backup, delete và auditor được tách role phù hợp.
- [ ] IAM/resource/key/network/application policy tuân least privilege và tenant scope.
- [ ] Không có secret trong source code, image, log, IaC state công khai hoặc example.
- [ ] Backup/snapshot có encryption, isolation, immutability/retention và cross-region recovery phù hợp.
- [ ] Restore test chứng minh cả dữ liệu, key, network, identity và ứng dụng hoạt động.
- [ ] Log/audit có redaction, retention, quyền đọc và integrity protection.
- [ ] Có cảnh báo cho decrypt bất thường, policy/key change, public access và backup deletion.
- [ ] Quy trình rotation/revocation/re-encryption đã được kiểm thử và có người chịu trách nhiệm.
- [ ] Đã đo latency, quota, chi phí KMS/storage/audit và tác động tới SLO.

Mã hóa lưu trữ và kiểm soát truy cập dữ liệu là hai lớp bảo vệ bổ sung. Mã hóa giúp giảm khả năng đọc dữ liệu khi storage hoặc đường truyền bị lộ; authorization giới hạn identity nào được dùng dữ liệu; key lifecycle, backup và audit duy trì khả năng bảo vệ và phục hồi theo thời gian. Thiết kế tốt phải theo được toàn bộ vòng đời dữ liệu, từ nguồn tạo đến bản sao cuối cùng, đồng thời chứng minh bằng policy, log và restore test.
