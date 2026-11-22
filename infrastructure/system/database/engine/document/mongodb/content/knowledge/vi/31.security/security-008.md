# Mã hóa dữ liệu lưu trữ và quản lý khóa theo mô hình triển khai trong MongoDB

## 1. Bài toán bảo mật: dữ liệu có thể bị lộ khi không có truy vấn nào chạy

Một hệ thống MongoDB có thể có xác thực, phân quyền người dùng, firewall và TLS nhưng vẫn gặp rủi ro nếu ổ đĩa, snapshot hoặc bản sao lưu bị truy cập ngoài ý muốn:

- Kỹ thuật viên tháo ổ cứng của máy chủ hỏng và mang đi xử lý.
- Snapshot volume được sao chép sang tài khoản cloud khác do cấu hình IAM sai.
- Một bản sao lưu cũ được lưu trên ổ cứng không mã hóa.
- Dữ liệu được di chuyển từ một máy ảo sang máy khác trong quá trình vận hành.
- Nhân sự có quyền quản lý hạ tầng nhưng không được phép đọc nội dung nghiệp vụ lấy được các files của WiredTiger.
- Một khóa mã hóa bị vô hiệu hóa, làm cụm dữ liệu không thể khởi động hoặc không thể phục hồi từ backup.

**Encryption at rest — mã hóa dữ liệu lưu trữ** — nhằm bảo vệ các bytes khi chúng nằm ở phương tiện lưu trữ, đặc biệt trong trường hợp bên không có khóa giải mã lấy được bản sao dữ liệu.

**Quản lý khóa** quyết định ai có thể giải mã, khả năng xoay khóa, khôi phục sau sự cố, đáp ứng yêu cầu audit và tác động của việc mất hoặc thu hồi khóa.

Đối với MongoDB, cách triển khai khác nhau giữa:

1. **MongoDB Atlas** — dịch vụ quản lý, có mã hóa mặc định và tùy chọn **customer-managed keys (CMK)**.
2. **MongoDB Enterprise tự quản lý** — hỗ trợ **Encrypted Storage Engine** của WiredTiger, với **KMIP** hoặc **local keyfile**.
3. **MongoDB Community tự quản lý** — không có tính năng Encrypted Storage Engine dành riêng cho Enterprise; có thể bảo vệ dữ liệu bằng mã hóa ở tầng hệ điều hành, ổ đĩa hoặc cloud block storage.
4. **Kiến trúc client-side encryption** — mã hóa trường dữ liệu trước khi gửi tới MongoDB; đây là một lớp bảo vệ khác và không thay thế việc phân tích bảo vệ dữ liệu khi lưu trữ.

> **Nguyên tắc xuyên suốt:** mã hóa dữ liệu mạnh nhưng quản lý khóa yếu không mang lại bảo vệ như mong đợi. Đồng thời, mã hóa ổ đĩa **không** thay thế TLS, authentication, authorization, backup protection hoặc kiểm soát truy cập trên máy đang chạy.

---

## 2. Xác định đúng mục tiêu bảo vệ trước khi chọn công nghệ

Cùng một cụm MongoDB có nhiều bề mặt rủi ro:

| Tình huống | Encryption at rest có giúp không? | Cần cơ chế bổ sung |
| --- | --- | --- |
| Kẻ tấn công lấy bản sao đĩa nhưng **không có khóa** | Có, đây là mục tiêu cốt lõi | KMS/key isolation |
| Snapshot hoặc volume nằm ngoài máy đang chạy | Có, nếu snapshot/volume được mã hóa và quản lý khóa đúng | IAM, snapshot access policy |
| Kẻ tấn công đăng nhập MongoDB bằng user có quyền đọc dữ liệu | **Không đủ** | RBAC, authentication, auditing |
| Kẻ tấn công chiếm được tiến trình `mongod` và bộ nhớ khi khóa đang được sử dụng | **Không đủ** | Host security, process isolation, monitoring |
| Traffic giữa application và MongoDB bị nghe lén | Không | TLS, certificate validation |
| Dữ liệu nhạy cảm không muốn server thấy plaintext | Không | CSFLE/Queryable Encryption với key management phù hợp |
| File JSON/CSV được export rồi gửi qua email | Không tự động | Mã hóa output và kênh phân phối |
| Khóa giải mã bị xóa vĩnh viễn | Có thể làm dữ liệu **không thể đọc** | Key backup/recovery, lifecycle governance |
| Mã hóa thành công nhưng user vẫn có quyền quá rộng | Không giải quyết quyền quá rộng | Least privilege, role review |

Một câu hỏi kiến trúc quan trọng:

> **Người cần bị ngăn đọc dữ liệu là ai, và ở trạng thái nào của hệ thống?**

Nếu mục tiêu chỉ là chống lộ dữ liệu từ **ổ cứng bị mất**, disk encryption có thể đủ với các điều kiện thích hợp. Nếu mục tiêu là ngăn **DBA hoặc tiến trình MongoDB** đọc một trường nhạy cảm, cần đánh giá client-side encryption. Nếu mục tiêu là chống **rò rỉ trên đường truyền**, cần TLS.

---

## 3. Phân biệt ba trạng thái của dữ liệu

```text
Application memory
       |
       |  Data in transit
       v
TLS connection
       |
       v
mongod memory / query execution
       |
       |  Data at rest encryption boundary
       v
WiredTiger / filesystem / storage volume
       |
       v
Disk, snapshot, backup media
```

### 3.1. Data at rest

Dữ liệu đã được ghi và lưu trên:

- Storage files của database.
- Journal và những files liên quan, tùy lớp mã hóa.
- Storage volumes, virtual disks, snapshots.
- Backup archives, object storage hoặc external disks.

**Cần xét phạm vi thực tế của từng lớp mã hóa.** Encrypted Storage Engine, full-disk encryption và encrypted backup archive không có cùng boundary; chẳng hạn application log, core dump và một tệp `mongodump` xuất ra bên ngoài có thể không tự thuộc phạm vi bảo vệ của ESE.

### 3.2. Data in transit

Dữ liệu đi qua network:

- Client ↔ `mongod`/`mongos`.
- Replica set members ↔ nhau.
- Shards/config servers/routers.
- KMS/KMIP ↔ MongoDB hoặc cloud control plane.

Bảo vệ bằng **TLS**, xác minh hostname/certificate và network access controls.

### 3.3. Data in use

Dữ liệu đang được truy vấn/xử lý trong memory:

- Storage encryption thông thường phải giải mã dữ liệu để database vận hành.
- Một user hợp lệ có đủ quyền có thể vẫn nhận plaintext.
- Các secrets trong memory cần host/process security.

Nếu cần giảm mức tin cậy đặt vào database server, hãy nghiên cứu **Client-Side Field Level Encryption (CSFLE)** hoặc **Queryable Encryption**, nhận thức rõ giới hạn truy vấn và key vault riêng.

---

## 4. Mô hình mã hóa theo lớp — kiến trúc tổng quan

```text
                        Application
                             |
                             | TLS
                             v
                       MongoDB Server
                             |
        +--------------------+--------------------+
        |                                         |
        v                                         v
 Data files / WiredTiger                    DB process memory
        |
        +--> ESE database-level encryption
        |         (MongoDB Enterprise hoặc
        |          Atlas dùng CMK theo cấu hình)
        |
        v
 Filesystem / storage volume
        |
        +--> volume-level encryption
        |         (cloud storage, LUKS, BitLocker...)
        |
        v
 Physical disks / cloud snapshots
```

Các lớp **có thể cùng tồn tại**. Ví dụ Atlas Core mặc định dùng mã hóa volume của cloud provider; khi bật CMK database-level encryption, có thêm một lớp mã hóa.

Tuy nhiên, **nhiều lớp không đồng nghĩa mọi rủi ro đều biến mất**: nếu cùng một service account có quyền đọc cả database lẫn khóa, quyền hạn quá rộng vẫn là vấn đề.

---

## 5. AES-256, envelope encryption và các loại khóa

Trong quản lý khóa, cần phân biệt:

| Thuật ngữ | Đối tượng | Mục đích |
| --- | --- | --- |
| **Data Encryption Key (DEK)** | Khóa mã hóa dữ liệu | Dùng để mã hóa bytes thực tế. |
| **Key Encryption Key (KEK)** | Khóa mã hóa một khóa khác | Bảo vệ DEK/master key. |
| **Master Key** | Khóa gốc trong một cấp phân hệ | Bảo vệ database keys hoặc key material trung gian. |
| **Customer-Managed Key (CMK)** | Khóa do khách hàng quản lý trong KMS | Cho phép tổ chức sở hữu/quản trị vòng đời và quyền sử dụng khóa. |
| **Key version** | Phiên bản material của một logical key | Duy trì khả năng giải mã dữ liệu cũ trong rotation. |
| **Key ID / key ARN / key URI** | Định danh khóa trong KMS | Thường an toàn hơn trao raw key material, nhưng vẫn là thông tin vận hành cần quản lý. |

### 5.1. Envelope encryption

Thay vì dùng một customer master key để trực tiếp mã hóa từng trang dữ liệu, có nhiều cấp:

```text
Customer-managed key (CMK) / external master key
                        |
                        v
       Encrypt/wrap MongoDB master key
                        |
                        v
          MongoDB master key (wrapped)
                        |
                        v
            Encrypt database keys
                        |
                        v
            Per-database encryption keys
                        |
                        v
              Encrypt database files
```

Ở Atlas Core với CMK, tài liệu MongoDB mô tả: CMK mã hóa **MongoDB Master Keys**, MongoDB Master Keys mã hóa **per-database encryption keys**, và những khóa database đó bảo vệ dữ liệu WiredTiger.

### 5.2. Tại sao nhiều cấp khóa?

- Không phải gửi toàn bộ dữ liệu sang KMS để mã hóa từng block.
- Giảm số thao tác KMS và giảm độ trễ.
- Có thể **thay đổi cách wrap key** mà không nhất thiết phải viết lại toàn bộ dữ liệu.
- Mỗi node/database có key material riêng theo kiến trúc.
- CMK có thể được quản trị bởi IAM/KMS ngoài database.

### 5.3. Key rotation không đồng nghĩa data re-encryption

Có ít nhất ba hoạt động khác nhau:

1. **Rotate CMK/key version**: quản lý key material của customer key provider.
2. **Rewrap/rotate master key**: tạo hoặc mã hóa lại lớp khóa trung gian.
3. **Rotate data encryption keys và mã hóa lại dữ liệu**: cần thay key dùng để bảo vệ data pages, có thể yêu cầu rebuild/initial sync hoặc phương pháp riêng.

Các hành động này khác nhau về phạm vi, chi phí, thời gian và khả năng phục hồi.

---

## 6. Mô hình triển khai 1: MongoDB Atlas mặc định

Theo tài liệu MongoDB Atlas hiện hành, **encryption at rest luôn được bật**, sử dụng **AES-256** và không thể tắt.

### 6.1. Atlas Core

Đối với Atlas Core:

- Cloud provider mã hóa storage volumes.
- Cloud provider vận hành key management mặc định.
- Không cần tự cấu hình key để có lớp mã hóa storage volume.
- Có thể bật **database-level encryption bằng customer-managed key** theo điều kiện của tier/deployment.

```text
Atlas Core mặc định

MongoDB data
     |
     v
Cloud storage volume encryption
     |
     v
Encrypted cloud disk/snapshot
     |
     +--> cloud provider-managed key
```

**Không khẳng định** rằng mã hóa volume mặc định nghĩa là đã có customer-managed key của công ty. Hai khái niệm là khác nhau.

### 6.2. Atlas Infinite

Tài liệu năm 2026 còn mô tả **Atlas Infinite** (public preview). Với mô hình compute/storage tách rời, dữ liệu được mã hóa ở cấp database trên compute node **trước khi tới lớp lưu trữ dùng chung**; MongoDB quản lý khóa mặc định cho mỗi organization và tự xoay khóa định kỳ.

Trong public preview:

- Customer-managed keys được hỗ trợ qua **AWS KMS**.
- Không tự giả định Azure Key Vault hoặc Google Cloud KMS đã có khả năng CMK tương tự cho Atlas Infinite.
- Có những hạn chế về restore cross-project/cross-organization.

**Đừng suy ra mọi tính năng Atlas Infinite áp dụng cho mọi Atlas Core/Flex hoặc mọi bản MongoDB Server.** Kiểm tra edition/plan và deployment options cụ thể.

### 6.3. Shared Responsibility Model

Atlas phụ trách những thành phần platform được MongoDB quản lý. Khách hàng vẫn có trách nhiệm:

- Ai được tạo cluster?
- Ai được đọc dữ liệu?
- Ai được bật/tắt key management?
- Quyền IAM của KMS principal?
- Thời gian sống và lưu trữ khóa?
- Metadata/data classification?
- Backup retention và incident response?
- Kiểm toán và cảnh báo truy cập?

“Atlas đã mã hóa” không tự chứng minh ứng dụng đáp ứng mọi quy định pháp lý.

---

## 7. Atlas CMK/BYOK: thêm quyền kiểm soát khóa

**Customer-managed keys (CMK)** còn được gọi **Bring Your Own Key (BYOK)** theo bối cảnh Atlas. Người dùng tạo/sở hữu khóa trong hệ thống KMS của cloud provider rồi cấp Atlas quyền sử dụng khóa để mã hóa lớp master key.

Những provider của **Atlas Core**:

| KMS provider | Dịch vụ |
| --- | --- |
| AWS | AWS Key Management Service (AWS KMS) |
| Microsoft Azure | Azure Key Vault |
| Google Cloud | Google Cloud KMS |

Một điều đáng lưu ý: tài liệu Atlas nói provider quản lý khóa **không nhất thiết phải trùng với provider chạy cluster**, tùy tính năng/cấu hình hỗ trợ. Nhưng cấu hình cross-cloud có thể làm tăng độ phức tạp về network, IAM, latency, chính sách data residency và vận hành.

### 7.1. Cấu trúc khi bật CMK trong Atlas Core

```text
Customer's cloud account
  |
  +-- AWS KMS / Azure Key Vault / Google Cloud KMS
         |
         | CMK: Encrypt/Decrypt MongoDB master keys
         |
         v
MongoDB Atlas project configuration
         |
         v
Atlas cluster node
  |
  +-- MongoDB Master Key  [encrypted by CMK]
         |
         +-- Per-database encryption keys
                  |
                  v
            Encrypted data files

+ Cloud provider volume encryption remains enabled.
```

**CMK không phải khóa mã hóa trực tiếp mọi document của ứng dụng**. Nó bảo vệ cấp khóa dùng để tiếp tục giải mã những data keys nội bộ.

### 7.2. Đặt quyền ở cấp project, bật theo cluster

Quy trình tổng quát:

1. Tạo CMK trong KMS của tổ chức.
2. Tạo IAM role/service principal/service account cho Atlas sử dụng theo provider.
3. Chỉ cấp hành động encrypt/decrypt và những thao tác bắt buộc khác trong contract KMS.
4. Cấu hình provider/key ID trong Atlas project.
5. Bật customer key management cho các clusters đủ điều kiện.
6. Kiểm tra KMS validation, cluster availability và backup requirements.
7. Cấu hình alert cho key state, IAM/credential và network failures.

Một số Atlas deployments như Flex không hỗ trợ CMK. Không giả định có thể bật CMK trên mọi gói dịch vụ.

### 7.3. Khi bật/tắt CMK có thể phát sinh thay đổi lớn

Tài liệu Atlas cho biết bật/tắt customer key management có thể kích hoạt initial sync để mã hóa lại dữ liệu và **rebuild MongoDB Search/Vector Search indexes**. Vì vậy đây là một thay đổi hạ tầng cần:

- Maintenance/capacity plan.
- Theo dõi replication lag.
- Kiểm tra indexes và search availability.
- Rollback/restore plan.
- Kiểm chứng tính sẵn sàng và chi phí.

Không xem việc bật CMK như một toggle không có tác động vận hành.

---

## 8. AWS KMS với Atlas: kiểm soát quyền thực tế

Ví dụ tổ chức chạy Atlas Core nhưng lưu CMK ở AWS KMS:

```text
Organization AWS Account
  |
  +-- KMS key ARN
  |
  +-- IAM role / key policy
         |
         | Atlas được phép dùng key theo policy
         v
MongoDB Atlas project
         |
         v
Atlas cluster with CMK
```

### 8.1. Những thành phần cần thiết

- Key ARN hoặc key identifier đúng.
- AWS account/region đúng.
- KMS key state là enabled.
- IAM role/trust policy phù hợp với Atlas integration.
- Key policy cho phép role cần thiết sử dụng CMK.
- Kiểm soát ai được **disable**, **delete**, **schedule deletion** hoặc thay policy.
- Audit thông qua AWS CloudTrail/KMS logs.
- Nếu có key rotation, hiểu cách provider giữ khả năng giải mã ciphertext cũ.

### 8.2. Tránh quyền quá rộng

Không cấp quyền kiểu:

```json
{
  "Action": "kms:*",
  "Resource": "*"
}
```

cho service principal của database một cách vô điều kiện. Đây là ví dụ **anti-pattern**, không phải policy triển khai.

Thay vào đó, dùng policy tối thiểu theo tài liệu tích hợp Atlas và audit các permission thực sự được yêu cầu.

### 8.3. Key ID khác raw key

Trong cấu hình Atlas, application/operator thường cung cấp **identifier** và quyền KMS integration, không phải chép raw 256-bit key vào source code.

Giữ key material trong KMS/HSM và hạn chế quyền truy xuất theo nguyên tắc **separation of duties**.

---

## 9. Azure Key Vault với Atlas

Trong môi trường Azure, CMK được lưu ở **Azure Key Vault**.

Mô hình:

```text
Azure subscription
   |
   +-- Key Vault
          |
          +-- Key / key version
          +-- Access policies / RBAC
          +-- Firewall / private networking
                 |
                 v
             MongoDB Atlas
                 |
                 v
            Encrypted storage
```

Những lưu ý:

- Identity/service principal dùng đúng quyền theo tích hợp.
- Cấp quyền KMS ở vault/key scope cần thiết, không cho toàn subscription.
- Kiểm tra Key Vault firewall, IP allowlists, private endpoints theo phương thức triển khai.
- Bật soft-delete/purge protection theo chính sách và yêu cầu của provider.
- Không dùng cùng credentials cho mọi môi trường dev/staging/prod.
- Kiểm tra khả năng phục hồi **đúng key version** đã dùng cho snapshot.

Atlas có thể cần các quyền và network paths bổ sung cho data validation/backup. Nếu firewall chặn những hoạt động này, một phần chức năng có thể lỗi dù cluster đang chạy.

---

## 10. Google Cloud KMS với Atlas

Với Google Cloud KMS, thiết kế gồm:

- Project và KMS key ring.
- CryptoKey và key versions.
- Service account/identity cho Atlas theo tích hợp.
- IAM permissions cần cho encryption/decryption.
- Region/location của key và chính sách data residency.
- Cloud Audit Logs.
- Key rotation và retention của phiên bản key cũ.

```text
Google Cloud project
   |
   +-- Cloud KMS
       +-- key ring
           +-- CryptoKey
               +-- key versions
                    |
                    v
                 Atlas CMK
                    |
                    v
            MongoDB master keys
```

Nếu vô hiệu hóa hoặc hủy **key version** còn được dùng để giải mã dữ liệu/snapshot, backup có thể không restore được. Cần hiểu sự khác nhau giữa tạo version mới và xóa version cũ.

### 10.1. Key location và cluster region

Không áp đặt một quy tắc “key phải ở cùng region” cho mọi loại Atlas deployment nếu tài liệu provider không yêu cầu như vậy. Thay vào đó kiểm tra:

1. Restriction của Atlas integration hiện hành.
2. Cloud KMS location availability.
3. Data residency/compliance.
4. Latency và network availability.
5. Khả năng restore sang region khác.

---

## 11. Tại sao thu hồi khóa có thể làm database ngừng hoạt động?

CMK là quyền kiểm soát khả năng giải mã. Nếu Atlas không thể sử dụng khóa do khách hàng quản lý:

- Một cluster vẫn đang chạy có thể tiếp tục phục vụ trong một số trường hợp network/KMS outage tạm thời.
- Nhưng restart/validation có thể yêu cầu key access.
- Atlas có cơ chế kiểm tra định kỳ tính hợp lệ của credentials/key.
- Nếu credentials vô hiệu hoặc key bị disable/delete, Atlas có thể **vô hiệu hóa cluster** ở lần kiểm tra hợp lệ kế tiếp.
- Cluster bị disabled sẽ không đọc/ghi dữ liệu cho đến khi cấu hình quyền/khóa hợp lệ được khôi phục.

Không phát biểu rằng “mất kết nối KMS một giây sẽ dừng toàn bộ cluster ngay” — tài liệu phân biệt **key invalidation** với **temporary network unavailable**.

### 11.1. Chặn truy cập không giống xóa dữ liệu

Nếu disable CMK, data files vẫn có thể tồn tại ở storage nhưng hệ thống **không thể giải mã**. Đây là rủi ro availability nghiêm trọng.

Nếu key đã bị xóa vĩnh viễn và không thể phục hồi, backup/data được bảo vệ bởi key đó có thể **không thể truy cập nữa**.

### 11.2. Runbook KMS incident

1. Phân biệt lỗi network/IAM, credential expired, key disabled hay key destroyed.
2. Bảo toàn logs và key IDs, không reset CMK cấu hình bừa.
3. Xác định những clusters, snapshots và search deployments phụ thuộc key.
4. Phục hồi IAM/credentials hoặc re-enable/recover key version theo provider.
5. Yêu cầu Atlas/KMS revalidation bằng quy trình hỗ trợ.
6. Kiểm tra cluster healthy và các backups vẫn restore được.
7. Sau incident, cải thiện key deletion protection, alerting và break-glass access.

Không dùng việc tắt CMK như phương án “chữa” lỗi key unavailable nếu không có kế hoạch do vendor xác nhận.

---

## 12. Key rotation trong Atlas: ba sự kiện khác nhau

Tài liệu Atlas Core cho biết khi sử dụng customer KMS, Atlas tự **xoay MongoDB Master Keys ít nhất mỗi 90 ngày**, với rolling process, không nhất thiết viết lại toàn bộ data pages.

Điều đó **không** có nghĩa Atlas tự xoay **customer-managed key trong tài khoản KMS của bạn**.

| Công việc | Ai chịu trách nhiệm chính? | Tác động |
| --- | --- | --- |
| Rotate MongoDB Master Keys (Atlas Core với CMK) | Atlas | Theo cơ chế nền tảng; có maintenance/rolling behavior |
| Rotate customer CMK/key material | Tổ chức và KMS provider | Policy, key versions, old ciphertext compatibility |
| Re-encrypt toàn bộ dữ liệu dưới key hierarchy mới | Tùy operation/migration | Có thể cần initial sync/rebuild |
| Kiểm thử restore snapshot dùng key cũ | Tổ chức + Atlas | Chứng minh key history còn dùng được |
| Thu hồi key bị lộ | Tổ chức | Cần đánh giá incident và re-encryption scope |

### 12.1. Rotation không phải xóa khóa cũ

Một chính sách an toàn:

- Tạo key version mới hoặc rotate theo provider.
- Xác nhận decryption của dữ liệu/snapshot đã tạo từ trước.
- Giữ các version cần thiết theo retention.
- Giám sát lỗi KMS access.
- Chỉ vô hiệu/xóa phiên bản cũ sau khi đã biết **không còn dữ liệu phụ thuộc** hoặc có kế hoạch crypto-erasure hợp lệ.

### 12.2. Rotation cần runbook phục hồi

Mục tiêu “rotate mỗi 90 ngày” là điều kiện governance. Giá trị thật nằm ở việc **dữ liệu và backup vẫn giải mã được** sau xoay khóa.

Một rotation thành công trên dashboard KMS chưa chứng minh snapshot 6 tháng trước vẫn khôi phục được.

---

## 13. Mô hình triển khai 2: MongoDB Enterprise self-managed

MongoDB Enterprise trên WiredTiger hỗ trợ **Encrypted Storage Engine (ESE)**.

Khác với mã hóa block device thông thường, ESE mã hóa **data files ở tầng storage engine** bằng các database keys. MongoDB dùng hệ key hierarchy để bảo vệ keys nội bộ.

### 13.1. Mô hình xử lý

```text
MongoDB Enterprise mongod
       |
       +-- Data query in memory
       |
       v
WiredTiger Encrypted Storage Engine
       |
       +-- Per-database keys
       |        |
       |        v
       |  Internal key store (encrypted)
       |        |
       v        v
Encrypted files on dbPath
                ^
                |
            Master key
                ^
                |
        KMIP server or local keyfile
```

Ở self-managed ESE:

- Database keys được quản lý bên trong server, chỉ lưu ra disk trong dạng encrypted.
- Master key phải được quản lý tách khỏi dữ liệu trong thiết kế hỗ trợ.
- Đặc tả cho phép **KMIP key manager** (được khuyến nghị) hoặc **local keyfile**.
- Không dùng cùng những option cấu hình Enterprise ESE trên MongoDB Community Edition.

### 13.2. Cipher modes

Theo MongoDB Manual, mặc định Encrypted Storage Engine dùng **AES256-CBC**. Trên Linux, MongoDB Enterprise còn hỗ trợ **AES256-GCM**. Tài liệu hiện hành lưu ý GCM không còn được hỗ trợ làm block cipher của ESE trên Windows.

Không đổi cipher mode trong production chỉ vì nghe nói GCM “tốt hơn” mà chưa xét version, FIPS, backup/restore và kế hoạch vận hành.

### 13.3. Không tự bật ESE cho dữ liệu đã tồn tại bằng một cờ

MongoDB không trực tiếp mã hóa nguyên một dbPath **đang chứa dữ liệu không mã hóa** chỉ bằng cách thêm `enableEncryption: true` rồi restart.

Đối với replica set đang có dữ liệu, tài liệu hướng dẫn dùng **rolling initial sync** để từng member tạo encrypted dbPath mới, sync lại, rồi chuyển primary.

Cần backup, capacity, replication window, write quorum và rollback plan.

---

## 14. Self-managed Enterprise: KMIP thay vì giữ khóa trên máy database

**KMIP — Key Management Interoperability Protocol** — cho phép MongoDB Enterprise giao tiếp với thiết bị/dịch vụ key manager tương thích.

```text
                Key Management System
                    (KMIP server)
                         |
                  TLS + identity
                         |
                         v
               MongoDB Enterprise
                  mongod process
                         |
                         v
              WiredTiger encrypted data
```

### 14.1. Vì sao KMIP được khuyến nghị?

- Tách master key khỏi máy chủ database.
- Audit được hoạt động key access.
- Có policy activation/rotation/revocation.
- Có thể dùng thiết bị HSM/key appliance theo yêu cầu.
- Phân tách quyền MongoDB admin và KMS admin.
- Đáp ứng những yêu cầu quản trị khóa chặt chẽ hơn local file.

### 14.2. Các operation KMIP cần có

Tài liệu hiện hành liệt kê các operation cần cấp cho KMIP server trong cấu hình mặc định:

- `Create`.
- `Get`.
- `Activate`.
- `GetAttributes`.
- `Encrypt`.
- `Decrypt`.

Một số behavior khác khi dùng legacy KMIP protocol. Đừng chỉ mở port 5696 rồi cho rằng integration sẽ chạy: còn phải có đúng phiên bản protocol, server certificate, client certificate và quyền key operations.

### 14.3. Cấu hình mongod.conf minh họa

```yaml
storage:
  dbPath: /var/lib/mongodb

security:
  enableEncryption: true
  kmip:
    serverName: "kmip.internal.example"
    port: 5696
    serverCAFile: "/etc/mongodb/kmip-ca.pem"
    clientCertificateFile: "/etc/mongodb/kmip-client.pem"

replication:
  replSetName: rs0
```

**Đây là cấu hình khái niệm cho một node mới hoặc dbPath đã chuẩn bị hợp lệ**, không phải lệnh an toàn để áp ngay vào production đang chạy.

Điều kiện còn thiếu trong ví dụ:

- Hostname thực và DNS.
- Chứng chỉ được cấp/trusted.
- TLS/hostname verification và network access.
- MongoDB Enterprise license/version.
- Replica set member configuration khác.
- Secrets/certificate permissions.
- Monitoring, backup và recovery.

### 14.4. Xác minh tên máy trong certificate

MongoDB kiểm tra tên KMIP server so với SAN/CN theo quy tắc TLS. Nếu hostname hoặc IP không khớp certificate, mongod có thể không khởi động.

Không giải quyết bằng cách tắt xác minh TLS một cách tùy tiện. Cấp certificate đúng tên/CA.

---

## 15. Self-managed Enterprise: Local Key Management

Local keyfile là cách để MongoDB ESE sử dụng master key từ một **file do quản trị viên bảo vệ**.

Ví dụ cấu hình:

```yaml
storage:
  dbPath: /var/lib/mongodb

security:
  enableEncryption: true
  encryptionKeyFile: /etc/mongodb/ese-master-key
```

Ví dụ **tạo keyfile ở môi trường thử nghiệm** bằng công cụ mã hóa phù hợp:

```bash
# Chạy trên host tự quản lý, với quyền và đường dẫn phù hợp.
openssl rand -base64 32 > /etc/mongodb/ese-master-key

# Chỉ tài khoản vận hành mongod được đọc keyfile.
chmod 600 /etc/mongodb/ese-master-key
```

Tài liệu yêu cầu nội dung keyfile là base64-encoded key material phù hợp; owner/permission phải đáp ứng yêu cầu của `mongod`. Trong production, tạo khóa bằng secret provisioning/KMS workflow được kiểm soát và tránh xuất khóa qua shell history hoặc nơi log được thu thập.

### 15.1. Không dùng keyfile với ý nghĩa sai

MongoDB có **hai thứ rất dễ nhầm**:

| Tên | Công dụng |
| --- | --- |
| `security.keyFile` | Internal authentication giữa các thành viên cluster (shared secret) |
| `security.encryptionKeyFile` | Master key file cho Encrypted Storage Engine |

Hai file **không phải một**, không dùng chung chỉ vì đều tên “keyfile”.

### 15.2. Local key management có giới hạn nghiêm trọng

MongoDB Manual nhấn mạnh:

- Quản trị local keyfile có thể không đáp ứng nhiều quy định quản trị khóa.
- Keyfile phải được bảo vệ rất chặt.
- **Key rotation không khả dụng với local key management** theo cơ chế rotate master key được tài liệu hỗ trợ.
- Nếu mất keyfile và không có bản khôi phục tương thích, dữ liệu ESE có thể không giải mã được.

Do đó, với hệ thống có yêu cầu rotation/audit/HSM/compliance, **ưu tiên KMIP key manager** thay vì chỉ bảo vệ một keyfile local.

### 15.3. Backup keyfile độc lập với data

Không giữ keyfile và toàn bộ encrypted backup cùng một thư mục public. Nhưng cũng **không được quên backup keyfile**; một backup data không có khóa cần thiết sẽ không restore được.

Giải pháp hợp lý là escrow trong secret manager an toàn, quyền truy cập hạn chế, offline recovery procedure và diễn tập khôi phục.

---

## 16. MongoDB Community self-managed: mã hóa ở hạ tầng

MongoDB Community Edition không có native WiredTiger Encrypted Storage Engine dành cho Enterprise. Nhưng không vì thế mà dữ liệu Community “không thể mã hóa khi lưu”.

Các lựa chọn hạ tầng:

- **Linux LUKS/dm-crypt**.
- **Windows BitLocker**.
- **Cloud block volume encryption**, ví dụ volume được provider quản lý.
- Encrypted filesystems hoặc storage arrays.
- Managed disks có khóa do customer hoặc platform quản lý theo sản phẩm.

```text
MongoDB Community mongod
          |
          v
      WiredTiger
          |
          v
     Filesystem
          |
          v
  Encrypted block device
  (LUKS / BitLocker / cloud)
          |
          v
     Physical disk
```

### 16.1. Điều bảo vệ được

Nếu một người chỉ lấy được **encrypted disk image** mà không có khóa:

- Data files và nhiều filesystem blocks không đọc được.
- Các file khác nằm trong cùng encrypted filesystem có thể cũng được bảo vệ.
- Volume snapshot có thể được mã hóa theo quy tắc cloud/storage.

### 16.2. Điều không bảo vệ được

Khi volume đã unlock và `mongod` đang chạy:

- Process có thể đọc file và trả dữ liệu.
- Root/admin của hệ điều hành có thể có năng lực can thiệp vào máy/keys.
- Database user có quyền vẫn truy vấn được plaintext.
- Export/file copy ra ổ ngoài chưa mã hóa có thể thành plaintext.

Mã hóa block storage và ESE có **different threat boundaries**. Không ghi trong kiến trúc rằng “LUKS hoàn toàn tương đương ESE/KMIP” cho mọi compliance requirement.

### 16.3. Những đường dẫn cần rà soát

- `storage.dbPath` và các files dữ liệu.
- Journal và tệp tạm liên quan nếu có.
- Backup destination.
- Dumps/exported files.
- Core dumps/swap files.
- Application logs, diagnostics và crash reports.
- CI/CD artifacts hoặc local developer copies.

Nếu `dbPath` nằm trong encrypted volume nhưng backup job ghi `mongodump` ra thư mục ngoài volume đó, backup có thể **không được bảo vệ**.

---

## 17. Chọn mô hình theo trách nhiệm vận hành

| Tiêu chí | Atlas mặc định | Atlas + CMK | Enterprise ESE + KMIP | Enterprise ESE + local keyfile | Community + disk encryption |
| --- | --- | --- | --- | --- | --- |
| Lớp mã hóa chính | Cloud volume / Atlas edition | Thêm DB-level CMK layer | WiredTiger ESE | WiredTiger ESE | Filesystem/block device |
| Ai vận hành MongoDB storage? | Atlas | Atlas | Tổ chức | Tổ chức | Tổ chức |
| Ai kiểm soát master/CMK? | Platform | Khách hàng tại KMS | Khách hàng/KMIP appliance | Người quản trị keyfile | Khách hàng hoặc cloud provider |
| KMS outage ảnh hưởng startup? | Theo platform | Có thể | Có thể | Local keyfile availability | Theo disk unlock/KMS |
| Rotation do bên nào? | Platform | Platform + khách hàng | Khách hàng theo KMIP runbook | Giới hạn, không có local rotation workflow | Theo OS/cloud storage |
| Cấu hình phức tạp? | Thấp | Trung bình–cao | Cao | Trung bình | Tùy hạ tầng |
| Phù hợp audit key usage? | Theo platform controls | KMS audit | KMIP appliance audit | Hạn chế | Theo KMS/OS |
| Mã hóa dữ liệu khi server process đang đọc? | Không theo nghĩa client-side | Không theo nghĩa client-side | Không | Không | Không |

Nếu yêu cầu doanh nghiệp là **customer control over encryption keys**, không chỉ thấy “disk encrypted” rồi đánh dấu đã đạt yêu cầu. Phải xác định **ai có khả năng disable/delete/rotate key**.

---

## 18. Phạm vi bảo vệ của encryption at rest: điểm thường bị bỏ sót

### 18.1. Dữ liệu đang ở RAM

Dù storage engine mã hóa file, `mongod` cần giải mã để thực hiện query. Dữ liệu và một số key material tồn tại trong memory của tiến trình trong thời gian hoạt động.

Cần:

- OS hardening.
- Giới hạn shell/admin access.
- Memory dump/core dump policy.
- EDR/monitoring.
- Patch management.
- Incident response khi máy chủ bị chiếm quyền.

### 18.2. Dữ liệu trên network

Phải dùng TLS:

```text
App -- TLS --> mongos/mongod
MongoDB nodes -- TLS --> each other
Database or Atlas -- secure KMS channel --> key provider
```

Không tắt hostname verification hoặc bỏ qua certificate validation để xử lý nhanh lỗi cấu hình.

### 18.3. Logs và observability

Application logs có thể chứa query parameters, user IDs, tokens, document fragments nếu ứng dụng log bừa. ESE không tự mã hóa một log được ship ra external service.

Cần data minimization, redaction, log retention và access control.

### 18.4. Temporary files và backup exports

Nếu job dùng:

```bash
mongodump --archive=backup.archive
```

thì không tự suy ra file `backup.archive` được mã hóa theo ESE. Đây là dữ liệu xuất qua client/protocol, cần bảo vệ riêng bằng encryption ở destination hoặc backup pipeline.

### 18.5. Snapshots

Cloud snapshot encryption có thể khác với MongoDB ESE. Bản sao snapshot cần cả storage ciphertext và key access hợp lệ để restore; các snapshot có thể giữ key dependencies từ thời điểm tạo.

---

## 19. Encryption at rest và mã hóa ở phía client: không phải đối thủ

MongoDB có hai nhóm bảo vệ **in-use encryption**:

- **Client-Side Field Level Encryption (CSFLE)**.
- **Queryable Encryption (QE)**.

Với những giải pháp này, driver có thể mã hóa field nhạy cảm **trước khi truyền tới MongoDB**. Server nhìn thấy encrypted field data thay vì plaintext đối với fields được bảo vệ, theo cấu hình và loại truy vấn được hỗ trợ.

```text
Application
    |
    +-- encrypt selected fields
    |       using DEK
    v
TLS ciphertext payload
    |
    v
MongoDB stores encrypted field values
    |
    +-- plus encryption at rest of storage files
```

### 19.1. Hai hệ key hierarchy khác nhau

**Server-side encryption at rest**:

```text
CMK / ESE master key
    -> database keys
    -> storage files
```

**Client-side encryption**:

```text
Customer Master Key in KMS
    -> wraps Data Encryption Keys (DEKs)
    -> DEKs stored encrypted in key vault collection
    -> encrypted application fields
```

Ngay cả khi cùng dùng tên AWS KMS hoặc Azure Key Vault, **key vault, quyền truy cập và mục đích** có thể khác.

### 19.2. Ví dụ nghiệp vụ

Document:

```javascript
{
  _id: "CUSTOMER-100",
  name: "Nguyễn Văn A",
  identityNumber: "<sensitive encrypted field>",
  city: "Hà Nội"
}
```

Nếu chỉ mã hóa storage, một user/DBA có quyền đọc `identityNumber` vẫn có thể nhận plaintext.

Với CSFLE/QE, application quản lý mã hóa field, server có thể chỉ thấy ciphertext của field đó; tùy chế độ và phiên bản, một số loại query trên encrypted fields có thể khả dụng.

### 19.3. Giới hạn

- Không phải mọi operator và aggregation stage đều dùng trên encrypted fields.
- Queryable Encryption và CSFLE có quy tắc tương thích/version khác nhau.
- Key material và key vault phải được backup/quản lý độc lập.
- Có thể có chi phí mã hóa/index/metadata và thay đổi application architecture.
- Không mặc định client-side encryption che toàn bộ metadata, document structure hay access patterns.

**Không quảng cáo client-side encryption là lý do tắt TLS hoặc bỏ qua encrypted backups.** Các lớp bảo vệ bổ sung cho nhau.

---

## 20. Thiết kế quyền quản trị khóa theo least privilege

Một mô hình doanh nghiệp nên tách vai trò:

| Vai trò | Quyền điển hình | Không nên có nếu không cần |
| --- | --- | --- |
| MongoDB DBA | Vận hành cluster, collections/indexes | Tự xóa CMK hoặc disable all keys |
| KMS administrator | Quản lý policies, lifecycle, recovery | Đọc mọi dữ liệu ứng dụng |
| Security auditor | Xem logs, key events, alerts | Decrypt data/key material |
| Deployment automation | Cấu hình theo môi trường | Wildcard admin trên mọi project/account |
| Application runtime | Kết nối/query theo role | Quyền đổi KMS key policy |
| Break-glass operator | Quyền khẩn cấp có audit | Dùng thường xuyên, không log |

### 20.1. Separation of duties

Không để một người duy nhất có thể:

1. Đọc toàn bộ dữ liệu.
2. Thay đổi KMS key policy.
3. Xóa toàn bộ backups.
4. Xóa audit logs.

Ít nhất cần các controls như MFA, approvals, audit trail, bounded access và incident escalation.

### 20.2. Định danh KMS không phải bí mật duy nhất

Key ARN/URI thường là **identifier**, không phải raw secret key. Tuy nhiên, tránh public chi tiết tài khoản, region, vault path hoặc internal topology không cần thiết. Credentials/trust policies vẫn phải được bảo vệ.

### 20.3. Không dùng một key cho mọi môi trường

Nên tách:

```text
kms/prod/customer-data
kms/staging/customer-data
kms/dev/test-data
```

để giảm blast radius. Dev có thể dùng synthetic data và khóa riêng; không copy production keys sang laptop.

---

## 21. Key lifecycle: từ tạo mới đến hủy an toàn

Một khóa không có vòng đời quản trị dễ trở thành lỗ hổng hoặc rủi ro gián đoạn.

```text
Key design and classification
             |
             v
         Key creation
             |
             v
        Activate / grant
             |
             v
           In use
             |
      +------+------+
      |             |
      v             v
   Rotate       Revoke/disable
      |             |
      v             v
 Keep old       Incident/
 versions       restore decision
      |
      v
 Confirm no live data/backups depend on old key
      |
      v
 Archive or destroy under approved policy
```

### 21.1. Tạo khóa

- Dùng KMS/HSM hoặc cryptographically secure random generator.
- Không tạo từ password, timestamp, project name hoặc hardcoded strings.
- Chọn key algorithm và key usage phù hợp provider/feature.
- Ghi nhận owner, purpose, environment, rotation period và retention.
- Hạn chế người được thực hiện thao tác Create/Delete.

### 21.2. Kích hoạt và cấp quyền

- Chỉ đúng principals cần giải mã được dùng key.
- Có chính sách riêng cho backup validation/restore.
- Giới hạn network egress đến KMS/KMIP.
- Tạo alerts cho policy changes.
- Theo dõi key ID đang active trên từng cluster.

### 21.3. Xoay khóa

- Xác định đó là CMK rotation, master-key rotation hay database-key rollover.
- Kiểm tra tính tương thích snapshot và old key versions.
- Không làm đồng thời ở tất cả nodes nếu runbook yêu cầu rolling.
- Kiểm tra cluster health và replication quorums.

### 21.4. Hủy khóa

Key destruction là hành động ảnh hưởng dữ liệu, đôi khi **không thể đảo ngược**. Chỉ thực hiện sau khi:

- Data classification và retention đã cho phép.
- Đã biết chính xác các clusters/backups phụ thuộc.
- Đã có phê duyệt liên quan.
- Đã diễn tập khôi phục hoặc xác nhận không cần khôi phục.
- Có audit trail.

**Crypto-shredding** có thể được dùng để làm dữ liệu không thể giải mã, nhưng chỉ là chiến lược hợp lệ khi hiểu hết các bản sao và phụ thuộc khóa.

---

## 22. Self-managed: chuyển replica set từ không mã hóa sang ESE

Tài liệu MongoDB yêu cầu **không khởi động ESE với key mới trên dbPath vốn chứa dữ liệu không mã hóa**. Cách chuyển replica set hiện hữu là rolling initial sync.

### 22.1. Quy trình khái niệm

```text
Replica set ban đầu:
  primary     plaintext dbPath
  secondary A plaintext dbPath
  secondary B plaintext dbPath
```

Các giai đoạn:

1. Backup và xác minh restore; kiểm tra replica set health/quorum.
2. Chuẩn bị KMIP/keyfile, certificates, permissions, networking cho node A.
3. Chuyển secondary A sang dbPath mới hợp lệ và bật encryption.
4. Thực hiện initial sync từ source để tạo dữ liệu được mã hóa.
5. Chờ node A khỏe và bắt kịp.
6. Thực hiện tương tự cho secondary B.
7. Step down primary có kiểm soát, bảo đảm quorum.
8. Chuyển primary cũ sang secondary và initial sync với ESE.
9. Kiểm tra toàn bộ members, read/write continuity và backup.

**Không** dùng một lệnh reset dbPath theo ví dụ internet khi chưa có backup/approval. Xóa data directory có thể gây mất dữ liệu nếu replication chưa đảm bảo.

### 22.2. Rolling migration không phải zero-risk

Có thể gặp:

- Initial sync kéo dài.
- Oplog window không đủ.
- Thiếu disk capacity.
- KMS/KMIP unreachable.
- Certificate mismatch.
- Write concern failures.
- Primary election hoặc lag.
- Old backups không theo cùng encryption state.

Cần maintenance window, monitoring và rollback plan phù hợp.

---

## 23. Self-managed KMIP master-key rotation

MongoDB cung cấp quy trình xoay master key trên replica set members dùng KMIP.

Các nguyên tắc:

- **Không rotate nhiều replica set members đồng thời** nếu có thể làm mất write quorum.
- Rotate secondaries tuần tự, chờ khỏe rồi xử lý primary sau controlled stepdown.
- Dùng option `--kmipRotateMasterKey` hoặc setting cấu hình tương ứng trong runbook MongoDB.
- Quá trình có thể làm `mongod` kết thúc sau khi rotation hoàn tất; phải khởi động lại bình thường theo hướng dẫn.
- Rotation master key **rewrap encrypted keystore**, không nhất thiết re-encrypt toàn bộ dữ liệu.

### 23.1. Cấu hình/command chỉ mang tính định hướng

```bash
# Ví dụ khung cú pháp. Không chạy trực tiếp trong production
# nếu chưa đối chiếu tài liệu và runbook phiên bản.
mongod \
  --enableEncryption \
  --kmipRotateMasterKey \
  --kmipServerName kmip.internal.example \
  --kmipServerCAFile /etc/mongodb/kmip-ca.pem \
  --kmipClientCertificateFile /etc/mongodb/kmip-client.pem
```

Trong production, còn cần dbPath, replication settings, port và các tham số node bình thường. Ví dụ trên **không phải cấu hình chạy hoàn chỉnh**.

### 23.2. Local keyfile không dùng workflow này

Tài liệu nhấn mạnh **không hỗ trợ key rotation khi dùng local key management** theo cách KMIP. Nếu yêu cầu rotation định kỳ, cần đổi chiến lược key management hoặc rebuild/re-encrypt với kế hoạch triển khai riêng.

---

## 24. Lưu ý đặc biệt với AES256-GCM và filesystem restore

MongoDB Enterprise trên Linux hỗ trợ ESE cipher **AES256-GCM**. GCM là authenticated encryption và cần quản lý IV/counter đúng.

Theo MongoDB Manual:

- Sau một số trường hợp **hot backup restore**, MongoDB có khả năng phát hiện trạng thái “dirty” key và roll over theo cơ chế được hỗ trợ.
- Với **cold filesystem snapshot restore**, hệ thống có thể không tự phát hiện việc reuse IV, gây rủi ro confidentiality/integrity.
- MongoDB cung cấp `--eseDatabaseKeyRollover` cho tình huống đặc thù này.

Đây **không phải** option master-key rotation thông thường:

| Option | Mục tiêu |
| --- | --- |
| `--kmipRotateMasterKey` | Rotate KMIP master key / rewrap keystore |
| `--eseDatabaseKeyRollover` | Rollover database keys trong tình huống ESE AES256-GCM filesystem restore theo tài liệu |

Không dùng hai option thay thế cho nhau. Trước một restore ESE-GCM, phải đọc runbook của phiên bản MongoDB đang dùng để tránh **IV reuse**.

---

## 25. Backups: dữ liệu mã hóa có đủ để restore không?

Một backup có thể hoàn toàn đầy đủ về mặt bytes nhưng **không sử dụng được** vì thiếu khóa, chính sách IAM hoặc key versions cần thiết.

### 25.1. Ba kiểu backup phổ biến

| Loại backup | Lưu ý |
| --- | --- |
| Encrypted cloud volume snapshot | Cần key KMS/storage thích hợp để restore |
| File-system snapshot của ESE | Cần ESE master key/keystore và xử lý cipher-specific restore |
| Logical backup (mongodump/export) | Output có thể là plaintext; phải bảo vệ riêng |

### 25.2. Backup của Atlas

Atlas encrypts snapshot volumes. Khi dùng customer-managed keys, restore có thể phụ thuộc key đã dùng lúc snapshot được tạo. Nếu key invalid, snapshot có thể không phục hồi được.

Đừng chỉ ghi “backup thành công” vào checklist. Cần kiểm thử **restore thực tế** ở môi trường cô lập với đúng key permissions.

### 25.3. Backup của Enterprise ESE

Phải lưu:

- Data snapshot.
- Thông tin/configuration cần cho decryption.
- Khả năng truy cập KMIP master key hoặc khôi phục keyfile.
- Mapping đúng keys/versions.
- Phiên bản MongoDB và các option cipher.

**Không** lưu toàn bộ raw master key và encrypted data trong cùng một public backup không được bảo vệ.

### 25.4. Backup của Community + disk encryption

Nếu backup là snapshot của encrypted volume, policy có thể kế thừa volume encryption. Nếu backup được đọc qua `mongodump` rồi ghi sang object storage, output **có thể không được mã hóa** trừ khi destination hoặc archive có lớp mã hóa riêng.

---

## 26. Disaster recovery: hai chiều kiểm thử

Một hệ thống tốt cần trả lời cả hai câu hỏi:

1. **Data files có còn không?**
2. **Key cần để giải mã data files có còn và sử dụng được không?**

### 26.1. Kịch bản A — mất host, còn key

- Provision host mới.
- Restore encrypted backup.
- Khôi phục cấu hình TLS/KMIP/KMS permissions.
- Mở khóa đúng key.
- Chạy integrity checks và application smoke test.

### 26.2. Kịch bản B — còn data, mất key

- Kiểm tra backup/escrow của key.
- Xem provider có soft-delete/recover key version không.
- Không cố “đổi sang key mới” để giải mã ciphertext cũ; key mới không tự thay key cũ.
- Nếu không có khả năng khôi phục, dữ liệu có thể mất vĩnh viễn về mặt truy cập.

### 26.3. Kịch bản C — còn key nhưng không có quyền

- Xác định IAM/service principal/network policy bị thay đổi.
- Regrant quyền tối thiểu.
- Kiểm tra KMS audit logs.
- Retry restart/restore theo runbook.
- Không hardcode credential admin thay vì sửa identity integration.

### 26.4. Kịch bản D — restore snapshot cũ sau rotation

- Snapshot có thể cần old key version.
- Không xóa old key material trước retention cutoff.
- Test restore ở staging sau mỗi thay đổi key lifecycle.
- Kiểm tra dữ liệu ở application level, không chỉ thấy service mở port.

---

## 27. Sharded cluster: không chỉ mã hóa shard primary

Một sharded cluster có nhiều thành phần:

```text
Application
     |
     v
   mongos
     |
     +--> Shard replica set A
     |       primary + secondaries
     |
     +--> Shard replica set B
     |       primary + secondaries
     |
     +--> Config server replica set
             primary + secondaries
```

### 27.1. Mỗi nơi giữ data files đều cần được xét

- Shard `mongod` members giữ collection data.
- Config server replica set giữ sharding metadata và các dữ liệu cấu hình.
- Backup/snapshot của tất cả members/shards cần chính sách bảo vệ.
- `mongos` là router không phải data file store như shard `mongod`, nhưng cấu hình, logs, credentials và endpoints vẫn cần bảo mật.

Không chỉ bật encryption ở shard chính rồi bỏ qua secondary/config servers.

### 27.2. KMS network là dependency toàn cụm

Một thay đổi DNS, firewall hoặc certificate trên KMIP có thể ảnh hưởng nhiều members khi restart. Cần redundancy/HA cho KMIP service và kiểm chứng từ tất cả hosts, AZs và regions.

### 27.3. Key separation theo môi trường và cluster

Nên xác định rõ policy có một CMK chung cho tất cả clusters của project hay các CMK tách biệt theo classification/environment. Dùng một CMK quá rộng tăng blast radius; dùng quá nhiều keys làm quản trị phức tạp.

---

## 28. Atlas và Search/Vector Search khi bật CMK

Một thay đổi cấu hình encryption at rest không chỉ tác động database files.

Tài liệu Atlas hiện hành nêu bật/tắt customer key management có thể:

- Kích hoạt initial sync.
- Re-encrypt dữ liệu cluster.
- Rebuild MongoDB Search và MongoDB Vector Search indexes.

Do đó khi lên kế hoạch:

1. Thống kê Search/Vector Search indexes.
2. Ước lượng thời gian build và capacity.
3. Xác định cần bật **Search Node Data Encryption/CMK** riêng theo cấu hình Atlas hỗ trợ hay không.
4. Giám sát query latency, index availability và resource pressure.
5. Kiểm tra dependency KMS đối với các nút search theo tài liệu hiện hành.

Không cho rằng vì cluster DB đã bật CMK thì **mọi search node, derived index và external export** đều tự động dùng đúng cùng chính sách key. Xác minh từng thành phần.

---

## 29. Multi-cloud và key residency

Doanh nghiệp có thể chạy MongoDB ở một provider nhưng giữ CMK ở provider khác. Điều này dẫn tới:

- Cross-cloud authentication.
- Network egress/IP allowlists.
- KMS endpoint latency.
- Khả năng khôi phục nếu một provider gặp sự cố.
- Data residency/legal requirements.
- Pricing của key usage, API requests và network.
- Monitoring/auditing nằm ở hai hệ thống.

### 29.1. Ví dụ ra quyết định

```text
MongoDB Atlas cluster: Cloud A / Region X
CMK:                 Cloud B / Region Y

Questions:
  - Atlas feature có cho phép provider này?
  - Ai giữ KMS role/service principal?
  - Đường mạng cross-cloud có ổn định?
  - Có phù hợp data residency không?
  - Nếu Cloud B outage, restart cluster ra sao?
  - Backup restore cần những keys/regions nào?
```

**Đừng chọn cross-cloud key placement chỉ vì muốn “an toàn hơn”.** Phải có một threat model rõ và vận hành KMS đủ độ tin cậy.

---

## 30. Giám sát encryption/key management

Các signals hữu ích:

| Metric/Signal | Vì sao cần |
| --- | --- |
| Cluster encryption enabled | Xác nhận control đang áp dụng |
| CMK configured vs default only | Phân biệt mức sở hữu khóa |
| Key state enabled/disabled | Tránh gián đoạn do key invalid |
| KMS credential expiration | Ngăn lỗi authentication |
| KMS access denied count | Phát hiện sai policy hoặc attack |
| KMIP connection latency/failure | Phụ thuộc vào KMS availability |
| Key rotation due date | Governance |
| Last completed master-key rotation | Audit |
| Unexpected key policy changes | Security incident |
| Cluster/node restart failures | Có thể do không mở được master key |
| Replica lag và initial sync status | Quan trọng khi enable encryption |
| Search index rebuild state | Sau thay đổi CMK |
| Backup encrypted status | Tránh bản sao plaintext |
| Backup restore test success | Chứng minh dữ liệu thực sự phục hồi được |
| Number of dependent snapshots per key version | Chống xóa old keys |
| OS volume encryption state | Với Community/infra model |
| Audit records for KMS use | Phát hiện bất thường |

### 30.1. Định nghĩa alert quan trọng

Nên có cảnh báo cho:

- KMS key scheduled deletion.
- CMK disabled hoặc pending destruction.
- IAM role/key policy bị đổi.
- KMS validation failure.
- KMIP certificate sắp hết hạn.
- Backup restore test thất bại.
- Key rotation quá hạn.
- DB node fail restart vì key unavailable.

### 30.2. Log tối thiểu

Log có thể ghi:

```text
clusterId
environment
keyIdentifier (đã che/redact theo policy)
operation
timestamp
principal
result
requestId
```

**Không log raw key material, passphrase, decrypted data hay full credentials.** Nếu key IDs là sensitive trong chính sách tổ chức, redaction ở logs vẫn cần.

---

## 31. Kiểm tra trạng thái mã hóa trong self-managed deployment

Một số thông tin có thể kiểm tra từ host/configuration:

### 31.1. Đọc cấu hình mongod

```yaml
security:
  enableEncryption: true
  kmip:
    serverName: "kmip.internal.example"
```

Hoặc:

```yaml
security:
  enableEncryption: true
  encryptionKeyFile: /etc/mongodb/ese-master-key
```

Đây là bằng chứng cấu hình ESE trên Enterprise. Nó cần được đối chiếu với **effective running process** và log khởi động thành công; chỉ nhìn vào file config không chứng minh node đang chạy với config đó.

### 31.2. Xem thông tin command-line options

Với quyền phù hợp:

```javascript
db.adminCommand({
  getCmdLineOpts: 1
});
```

Kết quả có thể cho biết startup options. Không xuất toàn bộ output vào ticket công khai vì có thể lộ đường dẫn, endpoint, filenames hoặc settings nhạy cảm.

### 31.3. Trên Linux dùng encrypted volume

Các lệnh chẩn đoán **chỉ đọc** có thể hỗ trợ:

```bash
lsblk -f

# Nếu đã biết tên mapping LUKS hợp lệ:
cryptsetup status mongodb-data
```

Không chạy lệnh `cryptsetup luksFormat`, `mkfs` hoặc thay đổi partition trên máy có dữ liệu chỉ để “kiểm tra encryption” — những thao tác đó có thể phá hủy dữ liệu.

### 31.4. Trên Windows

BitLocker có các công cụ quản trị trạng thái volume, nhưng kiểm tra phải gắn với **volume thực sự chứa dbPath**. Việc system drive đã encrypt không chứng minh data drive, backup drive và pagefile đều được bảo vệ.

---

## 32. Kiểm tra trong Atlas

Trong Atlas, kiểm tra ít nhất:

1. Edition/cluster tier.
2. Mức mã hóa mặc định theo Atlas Core hay Infinite.
3. CMK có được bật trên **đúng cluster** không.
4. Project key-management provider và key ID.
5. Trạng thái KMS validation.
6. Backup/snapshot encryption và restore requirements.
7. Search node/derived index encryption configuration nếu có.
8. IAM roles và permissions của các operator.
9. KMS audit events và alert configuration.
10. Data residency/security policies của project.

### 32.1. Default encryption không phải bằng chứng CMK

Một báo cáo compliance nên tách:

```text
Encryption at rest: ENABLED
Mechanism: Atlas default cloud volume encryption
Customer-managed key: NO
```

và:

```text
Encryption at rest: ENABLED
Mechanism: Atlas database-level + underlying volume
Customer-managed key: YES
KMS provider: AWS/Azure/GCP (theo edition)
Key state: VALID
```

Chỉ viết “AES-256 enabled” có thể thiếu thông tin đáp ứng yêu cầu “key ownership by customer”.

---

## 33. Mã hóa và performance

Mã hóa có thể ảnh hưởng CPU, I/O, cache, thời gian startup và thao tác backup/restore.

| Chi phí | Mô tả |
| --- | --- |
| CPU mã hóa/giải mã | Tùy cipher, hardware acceleration và workload |
| KMS/KMIP round trips | Thường gắn với key unwrap/initialization/rotation, không phải mỗi query |
| Startup latency | Phụ thuộc KMS availability và key access |
| Initial sync/re-encryption | Có thể kéo dài khi bật mã hóa ở cluster đã có dữ liệu |
| Key rotation | Cần rolling operations/maintenance |
| Backup storage | Snapshot ciphertext, metadata và key dependencies |
| Monitoring/alerting | Cần logs từ MongoDB và provider |
| Compliance operations | Audit, policies, drills, break-glass |

### 33.1. Không mặc định mã hóa làm mọi truy vấn chậm rất nhiều

AES có thể được CPU hỗ trợ bằng phần cứng. Overhead thực tế phụ thuộc hardware, storage engine, tỷ lệ cache hit, workload read/write và provider.

Cần benchmark:

- Read throughput.
- Write latency p50/p95/p99.
- CPU utilization.
- Initial sync time.
- Node restart with KMS.
- Backup/restore duration.
- Under KMS latency/failure simulation.

### 33.2. Không dùng encryption làm lý do bỏ index tuning

Nếu query không có index và scan hàng triệu documents, bật/tắt ESE không sửa được query plan. Vẫn cần index, schema và workload optimization riêng.

---

## 34. Ví dụ: thiết kế bảo mật cho ứng dụng SaaS lưu hợp đồng

Yêu cầu:

- MongoDB Atlas Core.
- Tenant data isolation.
- Một số hợp đồng chứa ID cá nhân.
- Backup phải khôi phục được trong 5 năm.
- Khách hàng yêu cầu CMK.
- Có nhu cầu tìm kiếm theo tên hợp đồng.

Đề xuất các lớp:

```text
SaaS Application
  |
  +-- Authenticated tenant context
  +-- Field-level policy cho dữ liệu nhạy cảm
  +-- TLS to Atlas
  |
  v
MongoDB Atlas Core
  |
  +-- Default volume encryption
  +-- CMK-backed database-level encryption
  +-- RBAC / auditing / network restrictions
  |
  +-- Backups / snapshots
        |
        +-- Key dependency inventory
        +-- Restore drills
  |
  +-- Search indexes
        |
        +-- Data classification
        +-- Search-node encryption policy
```

### 34.1. Các quyết định cần ghi nhận

- KMS provider nào quản lý CMK?
- Khóa theo project, cluster hay môi trường?
- Ai có quyền disable/delete?
- Có key deletion protection?
- Snapshot 5 năm sẽ phụ thuộc key versions nào?
- Trường ID cá nhân có cần client-side encryption?
- Search indexes có được phép index field nhạy cảm không?
- Khi khách hàng rời SaaS, xóa logical data và backup retention ra sao?

### 34.2. Những điểm không nên làm

- Dùng một IAM role vừa đọc toàn bộ hợp đồng vừa delete CMK.
- Sao chép snapshot sang môi trường dev dùng plaintext.
- Tự ghi `identityNumber` vào logs khi app decrypt.
- Bỏ qua testing cho restore từ key version cũ.
- Giả định Atlas CMK tự động mã hóa mọi exported PDF/CSV.

---

## 35. Ví dụ: MongoDB Enterprise trong data center

Yêu cầu:

- Replica set ba nodes.
- Không được đặt raw encryption master key trên cùng database host.
- Có thiết bị HSM/KMIP của tổ chức.
- Yêu cầu xoay khóa định kỳ.
- Thời gian dừng thấp.

Mô hình:

```text
              KMIP/HSM HA
                /    \
               v      v
            Node A  Node B  Node C
            mongod  mongod  mongod
               |      |      |
               v      v      v
            ESE dbPaths encrypted
```

### 35.1. Lộ trình

1. Chuẩn bị KMIP HA, DNS, certificates và network.
2. Cấp đúng operations/permissions.
3. Kiểm tra node test có thể start với encrypted dbPath.
4. Diễn tập backup/restore + key access.
5. Lên rolling initial sync cho replica set hiện có.
6. Giám sát health/quorum.
7. Viết runbook master-key rotation theo từng member.
8. Kiểm tra outage/expiry của KMIP certificate.
9. Tách key admin, DBA và audit privileges.

### 35.2. Vì sao không dùng local keyfile ở đây?

Yêu cầu “master key không nằm trên DB host” và “rotation có audit” không phù hợp với một keyfile local được quản lý thủ công. KMIP có boundary và governance rõ hơn.

---

## 36. Ví dụ: MongoDB Community trên một máy Linux

Yêu cầu:

- Ứng dụng nội bộ quy mô vừa.
- Self-managed Community.
- Tránh lộ dữ liệu từ disk image khi máy bị mất.
- Không có Enterprise ESE hoặc KMIP.

Mô hình có thể dùng:

```text
Application --TLS--> MongoDB Community
                         |
                         v
                       dbPath
                         |
                         v
                 LUKS-encrypted volume
                         |
                         v
                       disk
```

Các trách nhiệm bắt buộc:

1. Volume chứa **đúng dbPath** được encrypt.
2. Có chính sách unlock key/passphrase (TPM, recovery key, secret manager...).
3. Recovery key được backup độc lập.
4. Backup exports cũng được mã hóa.
5. Không để sensitive data trong logs/plaintext dumps.
6. Có host hardening, RBAC, TLS và firewall.
7. Có restore drill trên host mới.

**Không nói rằng cộng đồng Community có tùy chọn `security.enableEncryption` ESE như Enterprise.** Giải pháp ở đây hoạt động ở tầng OS/storage.

---

## 37. Rủi ro khi dùng chung khóa

Một key cho quá nhiều clusters có thể tạo **blast radius** lớn:

```text
KMS key K1
  |
  +-- production cluster A
  +-- production cluster B
  +-- staging cluster C
  +-- snapshot archive D
```

Nếu K1 bị disable/delete, nhiều hệ thống có thể cùng chịu ảnh hưởng.

Ngược lại, tạo mỗi file một CMK riêng cho at-rest cluster encryption có thể tăng complexity không cần thiết.

### 37.1. Chọn granularity phù hợp

Dựa vào:

- Environment (prod/staging/dev).
- Data classification.
- Business ownership.
- Regulatory boundaries.
- Geography.
- Restore/retention requirement.
- Number of clusters.
- Operational burden.

Ví dụ:

```text
prod-finance-cmk
prod-general-cmk
staging-cmk
dev-cmk
```

Tên chỉ minh họa chính sách phân tách; không đại diện một API key path bắt buộc.

### 37.2. Cẩn thận khi share CMK qua tenants

Nếu nhiều tenants có yêu cầu tự quản khóa riêng, một CMK ở project-level có thể không đáp ứng full tenant-specific key control. Khi đó cần đánh giá kiến trúc tách cluster/project hoặc client-side per-tenant keys theo yêu cầu, không giả định có thể gán một CMK cho từng document trong Atlas storage encryption.

---

## 38. Sự khác biệt giữa rotate, revoke và crypto-delete

| Hành động | Ý nghĩa | Rủi ro |
| --- | --- | --- |
| **Rotate** | Thay key material/version theo policy | Old backup cần old key |
| **Rewrap** | Mã hóa lại data/master key bằng KEK mới | Cần giữ tính tương thích hierarchy |
| **Re-encrypt** | Mã hóa lại bản thân dữ liệu bằng DEK mới | Tốn I/O, có thể cần migration |
| **Disable** | Tạm ngăn key sử dụng | Cluster/startup/restore có thể fail |
| **Revoke IAM grant** | Thu hồi quyền principal | Có thể chặn key access không đổi material |
| **Schedule deletion** | Đặt key vào quy trình xóa | Nguy cơ mất dữ liệu nếu không hủy lệnh |
| **Destroy** | Xóa key material vĩnh viễn | Có thể mất khả năng giải mã không thể phục hồi |
| **Crypto-shred** | Dùng việc phá hủy khóa để hủy quyền truy cập data | Chỉ có ý nghĩa nếu không còn bản plaintext/key copy khác |

Đừng dùng từ “rotate” thay cho “xóa key cũ”; hai hành động có hệ quả hoàn toàn khác.

---

## 39. Những lỗi triển khai phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| MongoDB Enterprise không start khi bật ESE | KMIP không truy cập được, certificate/key không đúng | Xem startup logs, kiểm tra KMIP/TLS/permissions |
| Bật encryption trên dbPath cũ bị lỗi | Dữ liệu chưa được encrypt | Rolling initial sync/migration theo tài liệu |
| MongoDB Community báo unknown/unsupported encryption option | ESE là Enterprise feature | Dùng Enterprise hoặc OS-level disk encryption |
| Atlas CMK không bật được | Tier/deployment không hỗ trợ hoặc quyền Project Owner thiếu | Kiểm tra requirements |
| Atlas shutdown sau key policy change | Key disabled/credentials invalid | Khôi phục KMS access theo runbook |
| Cluster chạy nhưng restart không lên sau KMS outage | Không thể lấy master key khi startup | HA KMS, network, credential recovery |
| Snapshot restore fail sau rotation | Old key/version không còn quyền | Khôi phục quyền/key version |
| Backup tồn tại nhưng đọc ra plaintext | Logical export không có encryption riêng | Encrypt backup output/destination |
| KMIP TLS hostname mismatch | SAN/CN không khớp | Cấp đúng certificate |
| KMIP client certificate expired | PKI rotation chậm | Renew sớm, cảnh báo |
| Local keyfile mất | Không có escrow/recovery | Đây có thể là data loss vĩnh viễn |
| DB user vẫn đọc plaintext | At-rest encryption không chống user hợp lệ | RBAC/CSFLE/QE |
| Query bị sniff trên network | Chưa có TLS | Bật TLS/cert verification |
| Atlas Search build lại khi bật CMK | Initial sync/encryption operation tác động Search | Capacity/maintenance/monitor |
| KMS audit log không có event mong đợi | Sai principal, audit config, operation path | Kiểm tra integration và key usage |
| Dev cluster đọc được prod data | Key/data access segregation không tốt | Tách keys, data, IAM, backups |
| ESE GCM restore cold snapshot có rủi ro | IV/key reuse | Theo hướng dẫn `--eseDatabaseKeyRollover` |
| Key rotation làm mất quorum | Nhiều nodes bị thay cùng lúc | Rolling per-member procedures |
| Có disk encryption nhưng logs lộ dữ liệu | Logs nằm ngoài boundary | Log redaction/encryption |
| Có CMK nhưng dữ liệu ứng dụng export không encrypt | CMK chỉ bảo vệ at-rest layer | Output encryption/access policy |

---

## 40. Checklist triển khai theo từng mô hình

### 40.1. Atlas

- [ ] Đã xác định Atlas edition/tier và encryption default?
- [ ] Đã xác nhận customer-managed keys có thật sự bắt buộc?
- [ ] Provider KMS và key location hợp lệ?
- [ ] Key policy/IAM tối thiểu?
- [ ] Atlas project và từng cluster được bật đúng?
- [ ] Search nodes/backup data có policy tương ứng?
- [ ] Key state và validation alerts đang hoạt động?
- [ ] Đã tính tác động initial sync/rebuild Search indexes?
- [ ] Đã có lịch xoay CMK và nắm rõ Atlas tự xoay master keys?
- [ ] Đã kiểm thử snapshot restore với key version cũ?

### 40.2. Enterprise self-managed

- [ ] WiredTiger và Enterprise ESE khả dụng?
- [ ] Chọn KMIP hoặc local keyfile theo compliance?
- [ ] KMIP HA/certificates/permissions đã kiểm chứng?
- [ ] Keyfile/local secrets không nằm trong Git/log?
- [ ] dbPath đã được tạo đúng encryption state?
- [ ] Replication members/config servers có cùng security policy?
- [ ] Đã thử backup/restore với đúng cipher mode?
- [ ] Có runbook KMIP master key rotation theo từng member?
- [ ] Nếu AES256-GCM, hiểu rủi ro cold filesystem restore?
- [ ] Đã giám sát errors/quorum/restarts liên quan KMS?

### 40.3. Community + storage encryption

- [ ] Volume/disk chứa dbPath được mã hóa?
- [ ] Có recovery key/TPM/secret manager policy?
- [ ] Backup exports và logs được bảo vệ?
- [ ] User/root access được harden?
- [ ] Có kiểm chứng startup sau host loss?
- [ ] Có TLS và RBAC?
- [ ] Có audit cho unlock key/access?
- [ ] Có rõ phạm vi mã hóa không bao trùm client-side data?

---

## 41. Bộ câu hỏi kiến trúc trước khi quyết định

1. Deployment của bạn là Atlas Core, Atlas Infinite, Enterprise hay Community?
2. Dữ liệu cần bảo vệ khỏi mất **disk image**, **snapshot** hay **DBA**?
3. Có yêu cầu **khách hàng sở hữu khóa** hay platform-managed là đủ?
4. KMS/KMIP có độ sẵn sàng đủ cho startup/recovery không?
5. Ai được disable/delete key?
6. Có cơ chế soft-delete/purge protection?
7. Dữ liệu và backup phải được giữ bao lâu?
8. Trong thời gian đó có bao nhiêu key versions sẽ cần duy trì?
9. Có yêu cầu region/data residency?
10. Có cần mã hóa một số fields trước khi gửi vào database không?
11. Thay đổi encryption ảnh hưởng replica sync và Search indexes ra sao?
12. Nếu key provider mất một ngày, ứng dụng và DR có kế hoạch gì?
13. Có test khôi phục trên host/region mới không?
14. Rotation là đổi CMK material hay database master-key rewrap?
15. Đã chứng minh logs, exports và backups đều được bảo vệ?
16. Có phương án đánh giá chi phí CPU/IO/KMS?
17. Có tenant-specific key control hay chỉ project-level CMK?
18. Có audit/compliance evidence đủ để giải thích trách nhiệm từng bên?

---

## 42. Bài tập vận dụng có đáp án

### Bài 1 — Atlas mặc định

Một Atlas Core cluster chưa bật CMK.

**Hỏi:** Dữ liệu có được mã hóa khi lưu trữ không?

**Đáp án:** Có. Atlas bật encryption at rest mặc định, với volume encryption do cloud provider quản lý. Nhưng **không phải customer-managed DB-level key**.

### Bài 2 — Customer-managed key

Tổ chức muốn tự vô hiệu hóa khóa, giữ audit KMS và điều khiển quyền decrypt.

**Hỏi:** Mô hình Atlas nào phù hợp?

**Đáp án:** Atlas với CMK/BYOK trên deployment hỗ trợ, kết hợp KMS policy, recovery và key deletion protection.

### Bài 3 — MongoDB Community

Nhóm chạy Community trong data center và muốn mã hóa disk khi mất máy.

**Hỏi:** Có thể dùng `security.enableEncryption` giống Enterprise không?

**Đáp án:** Không. Native Encrypted Storage Engine là Enterprise feature. Có thể dùng LUKS/BitLocker hoặc storage-level encryption.

### Bài 4 — Disk encryption và DBA

MongoDB có ESE, nhưng một user có role `readWriteAnyDatabase` đọc được dữ liệu.

**Hỏi:** Tại sao?

**Đáp án:** ESE bảo vệ at-rest bytes. Khi database đang chạy, server giải mã cho các queries hợp lệ theo RBAC. Cần least privilege và cân nhắc CSFLE/QE nếu muốn server không thấy một số plaintext fields.

### Bài 5 — Local keyfile vs KMIP

Security policy yêu cầu audit key use và rotate master key định kỳ.

**Hỏi:** Nên chọn gì cho Enterprise?

**Đáp án:** KMIP-compatible key manager, không phải local keyfile.

### Bài 6 — Mất keyfile

Có encrypted `dbPath` backup nhưng local keyfile đã bị xóa vĩnh viễn.

**Hỏi:** Có thể chỉ tạo keyfile khác để decrypt không?

**Đáp án:** Không. Một khóa mới không thể tự giải mã ciphertext đã mã hóa dưới khóa cũ. Phải có key backup/recovery tương thích.

### Bài 7 — Atlas rotation

Atlas tự rotate MongoDB Master Keys định kỳ khi dùng CMK.

**Hỏi:** Có nghĩa customer KMS CMK cũng được Atlas tự rotate không?

**Đáp án:** Không. Quản trị CMK và key versions thuộc KMS/customer policy.

### Bài 8 — Snapshot sau rotation

Một snapshot hai năm trước được bảo vệ bởi key version cũ; tổ chức xóa key version đó.

**Hỏi:** Hậu quả?

**Đáp án:** Snapshot có thể không thể restore. Cần duy trì old key versions theo retention và restore testing.

### Bài 9 — Logical backup

MongoDB Enterprise ESE đang bật. Nhóm chạy `mongodump` ra ổ USB không mã hóa.

**Hỏi:** Output chắc chắn encrypted không?

**Đáp án:** Không. Logical export được tạo qua API có thể chứa plaintext, phải mã hóa destination/archive riêng.

### Bài 10 — KMS mất mạng

KMS unreachable trong một khoảng ngắn.

**Hỏi:** Atlas cluster đang chạy có chắc chắn dừng ngay lập tức?

**Đáp án:** Không được khẳng định như vậy. Atlas phân biệt temporary connectivity và invalid credentials/key; restart/validation có thể bị ảnh hưởng. Cần runbook và HA KMS.

### Bài 11 — Primary và secondaries

Một replica set Enterprise chỉ bật ESE trên primary.

**Hỏi:** Đã bảo vệ hoàn chỉnh chưa?

**Đáp án:** Chưa. Secondaries cũng chứa data files; các members phải có chính sách mã hóa và migration thích hợp.

### Bài 12 — KMIP certificate

MongoDB Enterprise node kết nối tới KMIP server có certificate không khớp hostname.

**Hỏi:** Có thể xảy ra gì?

**Đáp án:** `mongod` có thể không khởi động do TLS hostname verification. Sửa DNS/certificate đúng, không tắt verification.

### Bài 13 — CBC vs GCM

Một ESE deployment trên Linux dùng AES256-GCM, restore từ cold filesystem snapshot.

**Hỏi:** Cần chú ý điều gì?

**Đáp án:** MongoDB cảnh báo nguy cơ IV reuse; làm theo runbook sử dụng `--eseDatabaseKeyRollover` khi phù hợp.

### Bài 14 — Different key scopes

Nhiều production clusters phụ thuộc cùng một CMK.

**Hỏi:** Rủi ro?

**Đáp án:** Blast radius lớn nếu key bị vô hiệu/xóa. Cân nhắc key separation theo environment/data classification.

### Bài 15 — Field-level

Tổ chức muốn database admin không đọc được số định danh cá nhân, nhưng MongoDB vẫn phải lưu dữ liệu.

**Hỏi:** Chỉ bật ESE có đủ không?

**Đáp án:** Không. Xem CSFLE/Queryable Encryption và kiểm soát key vault ở client.

### Bài 16 — Search index

Team bật/tắt CMK trên Atlas Core và thấy Search indexes rebuild.

**Hỏi:** Có phải lỗi ngẫu nhiên không?

**Đáp án:** Không nhất thiết. Tài liệu Atlas ghi nhận re-encryption/initial sync có thể rebuild Search/Vector Search indexes; cần maintenance/capacity plan.

### Bài 17 — Rotation vs deletion

Security officer đề xuất xóa ngay toàn bộ old KMS key versions sau rotation.

**Hỏi:** Có an toàn không?

**Đáp án:** Không nếu còn dữ liệu/snapshots mã hóa bằng các versions đó. Cần xác định dependencies trước khi destroy.

### Bài 18 — Encryption compliance

Một team báo cáo “AES-256 đã bật, chắc chắn đạt PCI-DSS/HIPAA”.

**Hỏi:** Kết luận có hợp lệ không?

**Đáp án:** Không. Mã hóa là một security control; compliance còn yêu cầu IAM, audit, governance, incident response, retention và các điều kiện khác theo phạm vi áp dụng.

### Bài 19 — Biện pháp dự phòng

Một CMK phụ thuộc một service principal có credential sắp hết hạn.

**Hỏi:** Nên làm gì?

**Đáp án:** Alert và rotation credential trước hạn, xác nhận Atlas/KMS validation, chuẩn bị break-glass, không đợi cluster lỗi.

### Bài 20 — Encryption keyfile confusion

Admin dùng cùng file cho `security.keyFile` và `security.encryptionKeyFile`.

**Hỏi:** Vì sao không nên?

**Đáp án:** Hai mục đích khác nhau — internal authentication và ESE master-key file — cần tách policy, nội dung, quyền và rotation.

---

## 43. Tài liệu MongoDB chính thức

- [MongoDB — Encryption at Rest](https://www.mongodb.com/docs/manual/core/security-encryption-at-rest/): Encrypted Storage Engine, cipher modes, key hierarchy và KMIP/keyfile.
- [MongoDB — Configure Encryption](https://www.mongodb.com/docs/manual/tutorial/configure-encryption/): Enterprise ESE, KMIP, local keyfile và encrypt existing data bằng rolling initial sync.
- [MongoDB — Rotate Encryption Keys](https://www.mongodb.com/docs/manual/tutorial/rotate-encryption-key/): rolling rotation, KMIP master key rotation, giới hạn local key management.
- [MongoDB — Self-Managed Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/): `security.enableEncryption`, `security.encryptionCipherMode`, KMIP options.
- [MongoDB — Atlas Encryption at Rest Overview](https://www.mongodb.com/docs/atlas/security-encryption-at-rest-overview/): Atlas Core/Infinite, AES-256, CMK hierarchy, backups và rotation.
- [MongoDB — Encryption at Rest using Customer Key Management](https://www.mongodb.com/docs/atlas/security-kms-encryption/): KMS providers, yêu cầu quyền, cấu hình và key validation.
- [MongoDB — Manage Customer Keys with AWS KMS](https://www.mongodb.com/docs/atlas/security-aws-kms/): AWS IAM/key policy và key lifecycle.
- [MongoDB — Manage Customer Keys with Azure Key Vault](https://www.mongodb.com/docs/atlas/security-azure-kms/): Azure Key Vault và access policies.
- [MongoDB — Manage Customer Keys with Google Cloud KMS](https://www.mongodb.com/docs/atlas/security-gcp-kms/): GCP key hierarchy và service account.
- [MongoDB — Storage Engine and Cloud Backup Encryption](https://www.mongodb.com/docs/atlas/backup/cloud-backup/cloud-backup-encryption/): snapshot security và key dependencies.
- [MongoDB — Access an Encrypted Snapshot](https://www.mongodb.com/docs/atlas/tutorial/access-encrypted-snapshot/): restore snapshots dùng customer key.
- [MongoDB — In-Use Encryption](https://www.mongodb.com/docs/manual/core/security-in-use-encryption/): CSFLE và Queryable Encryption.
- [MongoDB — Choosing In-Use Encryption](https://www.mongodb.com/docs/manual/core/queryable-encryption/about-qe-csfle/): khác nhau giữa hai phương pháp client-side.
- [MongoDB — TLS/SSL](https://www.mongodb.com/docs/manual/core/security-transport-encryption/): mã hóa đường truyền.
- [MongoDB — Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/): các lớp bảo vệ ngoài encryption.
- [MongoDB — Backups](https://www.mongodb.com/docs/manual/core/backups/): backup và phục hồi.

**Lưu ý phiên bản:** Những khả năng về Atlas Core/Infinite, availability theo tier, key provider, self-managed ESE cipher, CSFLE/QE và backup/restore thay đổi theo MongoDB Server/FCV/driver/edition. Hãy đối chiếu tài liệu của deployment thực tế và thử trên staging trước khi sửa bất kỳ key policy nào.

## 44. Kết luận

**Mã hóa dữ liệu lưu trữ** trong MongoDB không phải một cấu hình chung cho mọi môi trường:

- **Atlas:** dữ liệu được mã hóa mặc định; Atlas Core có thể bổ sung database-level encryption dùng **CMK/BYOK** trên deployments hỗ trợ. Atlas Infinite có kiến trúc storage riêng và các hạn chế CMK theo giai đoạn hỗ trợ.
- **Enterprise self-managed:** dùng **WiredTiger Encrypted Storage Engine**, ưu tiên **KMIP** khi cần key separation, rotation và audit; local keyfile có giới hạn quản trị/rotation.
- **Community self-managed:** mã hóa ở **OS/block storage/cloud volume** thay vì Enterprise ESE.
- **Client-side encryption:** khi yêu cầu bảo vệ một số fields ngay cả đối với database server, cần thêm CSFLE/Queryable Encryption và key vault riêng.

Các cấp **CMK → master key → database keys** giúp mã hóa theo mô hình envelope encryption, nhưng vận hành hiệu quả đòi hỏi quản lý **key lifecycle, IAM, certificate, rotation, backup, key versions và KMS availability**. Mất khóa có thể nghiêm trọng như mất dữ liệu; snapshot không có key restore được là một bản backup không sử dụng được.

Cuối cùng, encryption at rest chỉ là **một lớp trong defense-in-depth**. TLS, RBAC, audit, bảo vệ logs/exports, host hardening và diễn tập disaster recovery vẫn bắt buộc theo threat model.

**Mã hóa bảo vệ bytes nằm trên đĩa; quản lý khóa đúng cách bảo vệ khả năng kiểm soát và khả năng khôi phục toàn bộ hệ thống.**
