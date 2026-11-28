# Backup policy – Chính sách sao lưu và khôi phục khóa mật mã

**Backup policy (chính sách sao lưu)** trong quản lý khóa mật mã là tập hợp quy tắc xác định **khóa nào cần khả năng khôi phục, dữ liệu và metadata nào phải được bảo vệ, ai được sao lưu/khôi phục, bằng cơ chế nào, ở đâu, trong bao lâu, khi nào kiểm tra và khi nào phải xóa bản sao**. Mục tiêu không đơn giản là có thêm bản copy: một bản sao khóa không được bảo vệ có thể khiến tất cả bản mã hoặc chữ ký của hệ thống bị xâm phạm.

Trong chương **Key policy** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, backup policy phải bao phủ toàn bộ vòng đời khóa: **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**. Nó liên kết khóa AES/DEK, KEK, khóa ký bất đối xứng, HMAC, KMS/HSM, envelope encryption, phân quyền, phục hồi sau thảm họa (**Disaster Recovery – DR**) và kiểm toán.

> **Nguyên tắc quan trọng:** **Không phải mọi khóa đều nên được sao lưu dưới dạng vật liệu khóa.** Một số khóa phải được phục hồi qua cơ chế chính thức của KMS/HSM; một số khóa tạm thời phải bị hủy khi hết phiên; một số bí mật nếu mất thì dữ liệu được bảo vệ có thể không bao giờ khôi phục được. Sao lưu an toàn phải được thiết kế theo **mục đích của khóa, khả năng của nhà cung cấp và các phụ thuộc dữ liệu thực tế**.

## 1. Backup policy giải quyết những rủi ro nào?

Giả sử Billing Service dùng AES-GCM để mã hóa dữ liệu hóa đơn bằng **DEK (Data Encryption Key)**; mỗi DEK được bọc bằng **KEK (Key Encryption Key)** trong KMS. Nếu mất DEK hoặc mất khả năng giải bọc DEK, có thể còn nguyên ciphertext nhưng **không thể giải mã**. Ngược lại, nếu bản backup chứa KEK dạng rõ bị đánh cắp, kẻ tấn công có thể mở nhiều DEK và đọc dữ liệu.

Một chính sách sao lưu khóa cần giải quyết đồng thời:

1. **Mất khóa hoặc metadata:** xóa nhầm, lỗi phần cứng, mất vùng triển khai, sai thao tác vận hành.
2. **Gián đoạn dịch vụ:** KMS/HSM/PKI không sẵn sàng, thất bại khi chuyển vùng hoặc phục hồi workload.
3. **Ransomware và phá hoại:** kẻ tấn công xóa cả khóa hoạt động lẫn backup nằm trong cùng miền quyền.
4. **Lộ backup:** một bản xuất private key, KEK hoặc khóa MAC trở thành đường tắt để vượt qua kiểm soát ở KMS/HSM.
5. **Restore nhầm phiên bản:** dữ liệu mới phụ thuộc vào key version vừa tạo, nhưng backup chỉ có phiên bản cũ.
6. **Phục hồi đưa khóa đã thu hồi trở lại:** môi trường DR dùng trust store/policy cũ nên cho phép ký, giải mã hoặc xác minh bằng khóa bị compromise.
7. **Hủy không triệt để:** secret còn trong backup sau khi hệ thống tuyên bố đã crypto-shred.

**Availability** và **confidentiality** có thể tạo ra mâu thuẫn: nhiều bản sao giúp tăng khả năng phục hồi nhưng cũng tăng điểm có thể lộ khóa. Backup policy phải cân bằng bằng **phân loại khóa, bảo vệ bản sao và kiểm thử khôi phục**.

## 2. Phân biệt những thứ cần sao lưu

“Backup khóa” có thể chỉ các đối tượng rất khác nhau. Cần ghi chính xác **đối tượng được sao lưu** và **cơ chế khôi phục**.

| Đối tượng | Có thể cần backup? | Bảo vệ và lưu ý |
| --- | --- | --- |
| **Vật liệu khóa bí mật** | Tùy key type và khả năng export/recovery được phê duyệt. | Chỉ sao lưu qua cơ chế KMS/HSM, key wrapping hoặc escrow được phép; tránh plaintext. |
| **Public key/chứng chỉ** | Có, để duy trì trust và xác minh lịch sử. | Không cần giữ bí mật như private key nhưng phải bảo vệ **nguồn gốc, tính toàn vẹn và trạng thái thu hồi**. |
| **Key ID, version, alias và ownership** | Có, thường rất cần. | Phải đủ để liên kết ciphertext hoặc signature với phiên bản khóa đúng. |
| **IAM policy/key usage/approval** | Có, dưới dạng cấu hình và lịch sử có kiểm soát. | Restore không được tự mở lại quyền đã bị thu hồi. |
| **Wrapped DEK, ciphertext, nonce/tag/AAD** | Có, theo chính sách bảo vệ dữ liệu. | Thiếu một trong các thành phần cần thiết có thể khiến dữ liệu không đọc được. |
| **Backup manifest và dependency graph** | Có, để biết bản sao nào cần khóa nào. | Phải chống sửa đổi và tránh tạo phụ thuộc vòng trong khôi phục. |
| **Nhật ký kiểm toán/bằng chứng hủy** | Có, theo retention và tuân thủ. | Bảo vệ tính toàn vẹn, không chứa secret rõ. |
| **Session traffic key/ephemeral ECDH secret** | Thông thường **không**. | Nên tồn tại ngắn hạn; sao lưu kéo dài phạm vi ảnh hưởng và có thể làm suy yếu forward secrecy. |

Một **snapshot database** chứa bản mã chưa phải backup có thể phục hồi nếu khóa giải mã và **key version** không còn truy cập được. Ngược lại, sao lưu KEK mà không lưu wrapped DEK, context hoặc dữ liệu bị mã hóa cũng chưa hoàn thành kế hoạch DR.

### 2.1. Key backup, key replication và redundancy

- **Backup:** bản lưu có cơ chế bảo vệ và khả năng phục hồi một trạng thái cần thiết, thường độc lập về lỗi vận hành.
- **Replication:** nhân bản hoặc đồng bộ giữa node/region nhằm duy trì tính sẵn sàng; lỗi hoặc thao tác xóa có thể lan sang bản sao.
- **High availability (HA):** hệ thống có thể tiếp tục cung cấp phép toán khi một thành phần lỗi.
- **Escrow/recovery material:** vật liệu hoặc cơ chế được giữ để khôi phục theo chính sách, thường có kiểm soát quyền chặt hơn vận hành hàng ngày.

**HA hoặc replication không tự tương đương bản backup độc lập.** Ví dụ, nếu thao tác xóa khóa được đồng bộ sang các replica, có thêm region chưa đủ bảo đảm khả năng khôi phục. Phải tìm hiểu **khả năng, giới hạn, thời gian lưu và hành vi xóa** của từng KMS/HSM.

## 3. Phân loại khóa để quyết định có sao lưu hay không

| Nhóm | Ví dụ | Chính sách khuyến nghị theo mục đích |
| --- | --- | --- |
| **KEK/master key lưu trữ** | KMS key dùng WRAP/UNWRAP DEK. | Yêu cầu chiến lược **DR được nhà cung cấp hỗ trợ**, kiểm kê phụ thuộc và phục hồi bản mã; hạn chế tối đa xuất key material. |
| **DEK đối xứng** | AES-256-GCM mã hóa tệp, bảng, bản ghi. | Bảo vệ **wrapped DEK** và metadata giải mã cùng dữ liệu; chỉ giữ DEK rõ trong RAM khi cần. |
| **Private key giải mã dài hạn** | RSA-OAEP hoặc private key phục vụ dữ liệu tồn tại lâu. | Cần kế hoạch khôi phục vì mất khóa có thể khiến dữ liệu vĩnh viễn không đọc được. |
| **Private key ký số** | Ed25519/ECDSA/RSA-PSS ký phát hành và sự kiện. | Cân bằng availability với rủi ro tạo chữ ký giả; có thể chọn HSM-protected backup hoặc tạo khóa thay thế, tùy yêu cầu lịch sử/pháp lý. |
| **Khóa TLS/mTLS identity** | Private key gắn với chứng chỉ workload. | Nhiều hệ thống ưu tiên **cấp phát lại key pair/certificate** hơn là xuất private key; phải có quy trình cập nhật trust. |
| **Khóa HMAC/KMAC** | MAC cho webhook hoặc dịch vụ nội bộ. | Nếu cần kiểm tra tag cũ, giữ phiên bản an toàn trong thời hạn được phép; phân vùng theo tenant và purpose. |
| **PSK/recovery secret** | Bí mật chia sẻ hoặc vật liệu phục hồi. | Cần quyền rất hạn chế, retention/version rõ, có thể phục hồi hoặc cấp lại theo giao thức. |
| **Ephemeral/session secret** | ECDHE private key, TLS traffic key. | Không backup trừ thiết kế đặc thù đã được đánh giá; xóa khi hết vòng đời. |
| **Pepper cho password hashing** | Bí mật dùng thêm vào quy trình xác minh mật khẩu. | Cần phương án availability và rotation riêng; mất pepper có thể khiến xác minh bản ghi phụ thuộc thất bại. |

**Không mặc định rằng khóa “non-exportable” không thể được bảo vệ trước sự cố.** Một số HSM hỗ trợ **backup/restore nội bộ** bằng cơ chế được nhà cung cấp thiết kế, giữ bí mật trong miền bảo mật; một số dịch vụ KMS có cơ chế khả dụng/khôi phục mà ứng dụng không nhìn thấy. Tuy nhiên **không được suy ra khả năng restore nếu chưa kiểm chứng tài liệu và cấu hình dịch vụ**.

Tương tự, **BYOK (Bring Your Own Key)** hoặc imported key material có thể có quy tắc sao lưu/khôi phục khác khóa KMS sinh nội bộ. Tổ chức phải biết **ai giữ bản gốc, có cần giữ bản sao nguồn không và nếu material nhập bị xóa có được nhập lại hay không**.

## 4. Những thành phần tối thiểu của một backup policy

Một policy khả thi cần chỉ rõ **ai làm gì, với khóa nào và bằng chứng nào chứng minh có thể phục hồi**.

| Nhóm điều khoản | Câu hỏi phải trả lời |
| --- | --- |
| **Scope** | Bao gồm account, region, môi trường, tenant, key families và loại secret nào? |
| **Owner** | Ai chịu trách nhiệm, ai phê duyệt, ai được phép restore? |
| **Classification** | Khóa nào cần phục hồi; khóa nào tuyệt đối không xuất/backup? |
| **Custody/backup method** | Provider-managed recovery, HSM secure backup hay wrapped-key escrow theo cơ chế được duyệt? |
| **Key version** | Làm sao giữ các phiên bản còn cần cho decrypt/verify, không chỉ alias hiện tại? |
| **Dependencies** | Ciphertext/DEK, backup, archive, consumer và trust store nào phụ thuộc khóa? |
| **Protection** | Mã hóa bản sao, bảo vệ KEK phục hồi, integrity, isolation, immutability và phân quyền? |
| **RPO/RTO** | Có thể mất tối đa bao nhiêu metadata/key versions; phục hồi trong mục tiêu thời gian nào? |
| **Frequency/trigger** | Sao lưu theo lịch hay theo sự kiện Create/Import/Rotate/PolicyChange? |
| **Retention/deletion** | Lưu bao lâu, khi nào thu hồi hoặc hủy toàn bộ bản sao, ngoại lệ pháp lý? |
| **Testing** | Kiểm thử restore thực tế bao lâu một lần và ai xác nhận kết quả? |
| **Incident response** | Nếu backup hoặc khóa bị lộ, có thể cô lập, thu hồi và thay khóa thế nào? |
| **Audit** | Ghi nhận ai export, sao lưu, xem metadata, phục hồi, thay policy và hủy? |

Chỉ tiêu cụ thể phải dựa trên **mức độ quan trọng của dữ liệu**, chính sách tuân thủ, khả năng nhà cung cấp và đo kiểm thực tế; không thể dùng một RPO/RTO duy nhất cho mọi loại khóa.

### 4.1. Ví dụ mẫu policy dạng YAML

Đây là **mẫu minh họa nghiệp vụ**, không phải cấu hình chạy trực tiếp được trên một KMS/HSM:

~~~yaml
policyId: "key-backup-policy/billing-prod/v1"
scope:
  owner: "billing-security"
  environment: "production"
  keyFamilies: ["billing-kek", "billing-identity"]
  tenantBoundary: "billing"
rules:
  preserveDecryptDependencies: true
  preserveMaterialVersionsUntilSafeRetirement: true
  forbidPlaintextKeyExport: true
  requireIndependentRecoveryTrustDomain: true
  requireRestoreDrill: true
recovery:
  method: "PROVIDER_SUPPORTED_RECOVERY"
  backupLocationRef: "approved-dr-location"
  protectorRef: "independent-recovery-domain"
  rpoTarget: "policy-defined-and-tested"
  rtoTarget: "policy-defined-and-tested"
authorization:
  requestedByRole: "recovery-operator"
  approvedByRole: "security-approver"
  requireSeparationOfDuties: true
retention:
  rule: "until-dependencies-and-retention-verified"
  deletionRequiresApproval: true
audit:
  enabled: true
  immutableEvidenceRef: "approved-audit-store"
~~~

Các giá trị như **PROVIDER_SUPPORTED_RECOVERY**, **independent-recovery-domain** chỉ diễn đạt yêu cầu. Phần triển khai thực phải xác minh **provider có hỗ trợ phương án đó, quyền thực tế đã hạn chế và restore đã được thử thành công**. Trường `forbidPlaintextKeyExport` trong YAML không tự ngăn việc xuất secret nếu IAM/HSM policy vẫn cho phép.

## 5. Kiến trúc sao lưu: giữ khả năng phục hồi mà không lộ khóa

Một kiến trúc có thể phân tách **dịch vụ chạy bình thường** khỏi **miền kiểm soát phục hồi**.

~~~mermaid
flowchart TD
    APP["Billing Service"] --> DB["Ciphertext + nonce/tag + wrapped DEK"]
    APP --> KMS["KMS/HSM: KEK và quyền unwrap"]
    DB --> DATA_BACKUP["Backup dữ liệu có phiên bản"]
    KMS --> RECOVERY["Cơ chế recovery được provider hỗ trợ"]
    INVENTORY["Key inventory: owner/version/dependencies"] --> META_BACKUP["Backup metadata & audit có bảo vệ"]
    DATA_BACKUP --> DR["Môi trường DR được cách ly"]
    RECOVERY --> DR
    META_BACKUP --> DR
    POLICY["Phê duyệt, IAM, kiểm soát đa bên"] --> DR
    DR --> VERIFY["Đối soát key/version/trust và thử giải mã"]
~~~

**Backup dữ liệu và khả năng khôi phục khóa phải được thiết kế cùng nhau.** Có thể giữ bản mã ở một vùng, nhưng nếu toàn bộ khóa bảo vệ nó nằm trong cùng failure domain và không có recovery path hợp lệ, việc sao lưu riêng database không bảo đảm tính sẵn sàng.

### 5.1. Bảo mật bản backup

- **Confidentiality:** vật liệu khóa chỉ được sao lưu dưới cơ chế **wrap/secure backup** phù hợp; không tạo plaintext key dump.
- **Integrity/authenticity:** metadata và backup manifest cần cơ chế xác thực phù hợp, chẳng hạn chữ ký số, MAC hoặc AEAD theo giao thức; checksum thuần không chứng minh nguồn phát hành.
- **Isolation:** giữ bản backup trong **tài khoản/miền quản trị hoặc thiết bị/vùng độc lập** theo threat model, tránh một credential có thể xóa cả production và bản sao.
- **Immutability:** hỗ trợ giữ bản sao không thể sửa/xóa trong khoảng thời gian cần thiết, nhưng phải có ngoại lệ được quản lý cho vòng đời secret và yêu cầu xóa.
- **Access control:** tách quyền **Backup, Restore, Export/Import, Destroy, Approve**; cần ghi audit cho thao tác nhạy cảm.
- **Least exposure:** không đưa file backup bí mật vào repository, CI artifact, email, ticket hay môi trường phát triển.
- **Key separation:** khóa bảo vệ bản backup phải có phạm vi sử dụng và người quản lý riêng theo thiết kế.

**Một backup mã hóa chỉ an toàn đến mức khóa dùng bảo vệ nó và quyền truy cập vào khóa đó được bảo vệ.** Dùng một passphrase yếu rồi lưu cùng file backup không tạo ranh giới an toàn hữu ích.

### 5.2. Phụ thuộc vòng trong khôi phục (bootstrap problem)

Ví dụ, tổ chức dùng **KEK A** để mã hóa bản sao của chính **KEK A**, nhưng không còn cách khác lấy A khi KMS chính đã mất. Backup có tồn tại mà không thể mở.

~~~text
Backup KEK A --encrypted with--> KEK A
          ^                        |
          +------------------------+
                 Circular dependency
~~~

Cần thiết kế **recovery root** hoặc cơ chế provider-native có **trust domain và khả năng truy cập độc lập** với thành phần có thể bị mất. Nó có thể là HSM backup domain, tài nguyên KMS phục hồi do nhà cung cấp hỗ trợ hoặc phương án escrow được phê duyệt.

**Không tự bịa key escrow bằng cách cắt chuỗi secret thành nhiều phần plaintext.** Khi chính sách yêu cầu **m-of-n recovery/quorum**, phải dùng cơ chế threshold/secret sharing hoặc quản lý quyền nhiều bên được triển khai đúng chuẩn và hỗ trợ bởi giải pháp tương ứng, kiểm thử cả trường hợp thiếu một người/thiết bị.

## 6. RPO, RTO và phiên bản khóa

**RPO (Recovery Point Objective)** mô tả mức mất mát trạng thái có thể chấp nhận khi phục hồi; **RTO (Recovery Time Objective)** là mục tiêu thời gian đưa chức năng trở lại. Với quản lý khóa, cần đo thêm **khả năng phục hồi chính xác các key versions** đang bảo vệ dữ liệu.

Một ví dụ: lúc 10:00 hệ thống backup metadata; 10:05 tạo **KEK v5** hoặc **DEK v27** rồi dùng để mã hóa dữ liệu mới; 10:08 sự cố phá hủy trạng thái chưa được bảo vệ. Nếu backup chỉ còn v4/v26, dữ liệu được mã hóa từ 10:05 có thể không đọc được, dù database được phục hồi thành công.

Do đó với khóa có thể trở thành **điểm phụ thuộc không thể thay thế**, policy có thể yêu cầu:

1. Sinh khóa trong hệ thống có **recovery guarantee phù hợp**.
2. **Ghi metadata/key version/backup reference bền vững** trước khi cho phép dùng khóa bảo vệ dữ liệu không thể tái tạo.
3. Kiểm tra cơ chế khôi phục đã được xác thực và đạt chính sách.
4. Chỉ sau đó mới đưa version vào **ACTIVE** cho workload tương ứng.
5. Đối soát data snapshots và key-version snapshots theo một **mốc phục hồi nhất quán**.

Không suy diễn rằng “backup chạy mỗi ngày” sẽ có RPO một ngày **chấp nhận được** với mọi khóa. Với dữ liệu không thể tái tạo, mất một DEK mới có thể làm mất toàn bộ nhóm bản ghi được mã hóa dưới DEK đó.

### 6.1. RTO cần đo toàn chuỗi phụ thuộc

Thời gian phục hồi không chỉ là lúc KMS bắt đầu trả về API. Một phép DR thực tế có thể cần:

- Phục hồi account/role/quyền và đường mạng an toàn.
- Khôi phục **metadata, wrapped DEK, bản mã và phiên bản tương ứng**.
- Kích hoạt KMS/HSM hoặc cơ chế recovery được nhà cung cấp hỗ trợ.
- Phê duyệt quyền truy cập và cấp lại workload identity.
- Đối chiếu trạng thái **revoked/retired/compromised** trước khi mở luồng traffic.
- Thử decrypt/verify với mẫu kiểm chứng được phép và khôi phục ứng dụng.

**RTO phải tính cả thời gian con người phê duyệt** nếu cơ chế escrow/quorum yêu cầu nhiều người cùng tham gia. Không nên loại bỏ phê duyệt bảo mật chỉ để đạt một con số RTO trên giấy.

## 7. Backup policy và quan hệ DEK/KEK trong envelope encryption

Trong **envelope encryption**, **DEK** mã hóa dữ liệu; **KEK** bảo vệ DEK. Một kế hoạch phục hồi cần quản lý cả hai loại khóa và version.

~~~mermaid
flowchart LR
    K1["KEK v1: predecessor"] --> K2["KEK v2: current"]
    K1 --> W1["Wrapped DEK A bằng v1"]
    K2 --> W2["Wrapped DEK B bằng v2"]
    W1 --> D1["Ciphertext/backup A"]
    W2 --> D2["Ciphertext/backup B"]
    I["Inventory: mapping key version"] --> W1
    I --> W2
~~~

**Đường mũi tên từ KEK sang wrapped DEK là quan hệ bảo vệ**, còn mũi tên v1 → v2 là quan hệ version/predecessor. Hai quan hệ này không được trộn lẫn khi quyết định retire hoặc destroy.

### 7.1. Khi xoay KEK

- **KEK rotation:** dùng KEK mới cho hoạt động wrap mới.
- **Rewrap DEK:** thay lớp bọc của DEK dưới KEK mới nếu cần, không nhất thiết thay DEK hoặc ciphertext.
- **Dual-read/multi-version recovery:** trong giai đoạn chuyển tiếp, hệ thống có thể cần quyền unwrap với KEK cũ để đọc bản ghi/bản sao còn phụ thuộc.
- **Đối soát:** inventory phải tìm toàn bộ wrapped DEK, snapshot, archive và bản sao lưu vẫn dùng version cũ.
- **Retire/destroy:** chỉ hủy KEK cũ khi tất cả dependency và retention được xử lý hoặc có quyết định không còn cần khả năng giải mã được phê duyệt.

Một số KMS tự quản lý lịch sử vật liệu dưới cùng key ID, nên ứng dụng có thể không cần chỉ định key version khi decrypt. Tuy nhiên backup policy vẫn phải hiểu **nhà cung cấp bảo đảm điều gì và trường hợp xóa khóa nào khiến dữ liệu mất khả năng phục hồi**.

### 7.2. Khi DEK hoặc KEK bị lộ

**Rotate KEK không tự làm dữ liệu cũ an toàn nếu DEK đã bị lộ.** Rewrap cùng một DEK dưới KEK mới chỉ thay lớp bảo vệ khóa; dữ liệu đã bị lộ dưới DEK đó cần được đánh giá phạm vi và có thể phải **re-encrypt bằng DEK mới**.

Nếu **KEK đã bị lộ**, cần điều tra DEK nào có thể đã được unwrap, bản backup nào có thể truy cập, và những actor nào có quyền thao tác. Phương án recovery phải bao gồm **đánh giá mức độ compromise**, không chỉ chuyển sang key ID mới.

### 7.3. Nếu cố ý crypto-shred

**Crypto-shredding** dựa trên việc khiến dữ liệu mã hóa không còn đường giải mã hợp lệ bằng cách hủy vật liệu khóa cần thiết. Backup policy phải tương thích với mục đích này:

- Xác định **DEK/KEK nào thực sự phải không còn khôi phục được**.
- Kiểm kê **mọi bản sao khóa, escrow, provider backups, HSM replicas và recovery secret** trong phạm vi kiểm soát.
- Xem xét **các DEK đã xuất, plaintext data copies và dữ liệu được mã hóa lại** nếu tồn tại.
- Kiểm tra chính sách retention, legal hold và thời điểm có thể hủy bản backup.
- Lưu **bằng chứng hủy** mà không lưu bản sao bí mật có thể dùng để phục hồi khóa.

**Không thể tuyên bố crypto-shredding hoàn tất nếu còn backup cho phép tái tạo đúng khóa cần hủy.** Nếu một nền tảng không hỗ trợ hủy riêng từng material version, chính sách phải phản ánh giới hạn đó và thiết kế phạm vi mã hóa phù hợp từ đầu.

## 8. Khóa ký số, chứng chỉ và khả năng xác minh lịch sử

Backup private key ký số cần được đánh giá khác private key giải mã:

- Với **private key giải mã**, mất khóa có thể khiến ciphertext lịch sử không khôi phục được.
- Với **private key ký**, việc xác minh chữ ký cũ thường chỉ cần **public key/chứng chỉ đáng tin**, không nhất thiết cần giữ private key.
- Sao lưu private signing key **mở rộng số nơi có thể tạo chữ ký hợp lệ**, làm tăng rủi ro giả mạo.
- Một số quy trình ký nhạy cảm có thể yêu cầu HSM-protected backup/escrow; một số quy trình có thể chọn **phát hành key pair mới** thay vì sao lưu private key.

**Giữ private key ký không đồng nghĩa giữ bằng chứng lịch sử.** Hệ thống có thể cần bảo lưu **public key, chứng chỉ, chain, trạng thái thu hồi, manifest, timestamp đáng tin và nhật ký phát hành**. Tùy giao thức/pháp lý, verifier cần đánh giá trạng thái trust tại thời điểm ký chứ không chỉ hôm nay.

### 8.1. Không khôi phục vô điều kiện khóa đã bị thu hồi

Một backup được tạo trước sự cố có thể chứa private key S1 và IAM policy cho phép **SIGN**. Sau khi S1 bị nghi lộ, tổ chức chuyển S2 vào hoạt động và vô hiệu hóa S1. Nếu DR restore snapshot cũ, **S1 không được tự động có lại quyền Sign**.

Quy trình restore phải đối chiếu **latest revocation state, trusted signer registry, certificates và các quyết định sự cố** từ nguồn được phép, đồng thời **fail closed** với thao tác nhạy cảm cho tới khi xác minh xong.

**Tính toàn vẹn backup không đồng nghĩa tính hợp lệ hiện tại của policy cũ.** Một snapshot nguyên vẹn từ thời điểm trước thu hồi vẫn có thể chứa cấu hình không còn được phép.

## 9. Quy trình restore an toàn

Một **restore drill** có giá trị hơn một báo cáo “backup successful”. Cần thử khôi phục trong ranh giới có kiểm soát theo quy trình đã phê duyệt.

### 9.1. Các bước đề xuất

1. **Kích hoạt sự kiện DR:** phân loại lỗi/sự cố, xác định phạm vi phục hồi và quyết định ai được phê duyệt.
2. **Khóa đường thao tác nguy hiểm:** cô lập môi trường DR; không tự động mở SIGN/DECRYPT/UNWRAP cho workload chưa xác thực.
3. **Xác minh backup:** kiểm tra nguồn, chữ ký/MAC/AEAD hoặc cơ chế integrity và version manifest theo chuẩn đã chọn.
4. **Xác định điểm phục hồi:** đối chiếu data snapshot với **key/material versions**, wrapped DEK, ciphertext, certificates và policy state.
5. **Khôi phục trust/custody:** thực hiện provider-native restore hoặc quy trình HSM/escrow đã được duyệt, không xuất secret rõ vào máy vận hành.
6. **Khôi phục cấu hình có kiểm soát:** IAM/key usage, owner, tenant mapping, trust stores; áp dụng lại trạng thái thu hồi mới nhất.
7. **Kiểm thử mật mã:** với mẫu dữ liệu thử hoặc dữ liệu được phép, xác minh decrypt/unwrap, chữ ký/certificate, đúng key ID và encryption context.
8. **Kiểm tra chính sách an toàn:** không có khóa đã compromised được kích hoạt; không chấp nhận signer/thuật toán đã bị cấm; không có quyền vượt phạm vi tenant.
9. **Chuyển traffic theo phê duyệt:** bật ứng dụng/consumer sau khi đủ chứng cứ, không dựa chỉ vào API báo `ACTIVE`.
10. **Ghi audit và post-incident review:** lưu actor, backup ID, kết quả, thời gian, chênh lệch RPO/RTO và kế hoạch khắc phục.

**Một phép restore chỉ chứng minh những gì đã kiểm tra.** Khôi phục thành công một mẫu DEK không chứng minh mọi backup hoặc tenant đều giải mã được; cần thiết kế bộ mẫu có tính đại diện theo **key families, versions, provider, data age và failure domain**.

### 9.2. Kiểm thử các trường hợp thất bại

| Bài kiểm tra | Kết quả an toàn kỳ vọng |
| --- | --- |
| Backup có manifest bị sửa | Từ chối, ghi audit, không khôi phục key material. |
| Thiếu KEK predecessor vẫn còn dữ liệu phụ thuộc | Báo BLOCKER phục hồi cho dữ liệu liên quan, không tuyên bố DR PASS. |
| IAM policy cũ cho phép ứng dụng bị thu hồi | Không kích hoạt quyền đó sau restore. |
| Người phục hồi không đạt điều kiện phê duyệt/quorum | Từ chối thao tác, không tiết lộ secret. |
| Mất toàn bộ vùng production | Có recovery path được kiểm thử ngoài failure domain theo chính sách. |
| Một bản sao backup bị xóa hoặc ransomware sửa | Tìm được bản sao còn hợp lệ hoặc công bố rõ khả năng không phục hồi. |
| Signing key bị compromised nằm trong snapshot cũ | Không cho phép ký mới bằng khóa đó; cập nhật trust policy. |
| Key version mới được dùng ngay trước sự cố | Phát hiện và đối chiếu đúng version hoặc ghi nhận vi phạm RPO. |
| Secret bị yêu cầu crypto-shred | Không thể khôi phục từ bản sao còn thuộc phạm vi quản trị sau khi hủy hoàn tất. |

## 10. Java 17: đánh giá metadata theo backup policy

Ví dụ Java sau mô phỏng một **policy gate** kiểm tra metadata và bằng chứng khôi phục. Nó **không gọi API xuất/nhập khóa và không cầm key material**. Mục tiêu là minh họa cách hệ thống có thể phát hiện vi phạm trước khi tuyên bố một key family “đã sẵn sàng DR”.

Giả định: danh sách bằng chứng được thu thập từ các hệ thống có thẩm quyền, đã xác thực trước đó. Trong thực tế, các giá trị như `restoreTestPassed` phải đến từ **kết quả restore drill được kiểm chứng**, không phải một boolean do người gọi tự khai.

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class KeyBackupPolicyDemo {
    enum Kind { KEK, DEK, SIGNING, EPHEMERAL }
    enum Method { PROVIDER_RECOVERY, HSM_SECURE_BACKUP,
                  APPROVED_WRAPPED_ESCROW, NONE }

    record KeyRef(String family, String version) {}

    record KeyAsset(
            KeyRef ref,
            Kind kind,
            boolean exportable,
            boolean hasHistoricalDependencies,
            Method recoveryMethod,
            String recoveryProtectorId,
            boolean providerSupportsRestore) {}

    record BackupEvidence(
            KeyRef ref,
            Instant verifiedAt,
            Instant lastRestoreTestAt,
            boolean integrityVerified,
            boolean isolatedCopy,
            boolean restoreTestPassed) {}

    static List<String> evaluate(
            KeyAsset key, BackupEvidence evidence, Instant now) {
        java.util.ArrayList<String> problems = new java.util.ArrayList<>();

        if (key.kind() == Kind.EPHEMERAL) {
            if (key.recoveryMethod() != Method.NONE) {
                problems.add("EPHEMERAL_MUST_NOT_BE_BACKED_UP");
            }
            return problems;
        }

        if (!key.exportable()
                && key.recoveryMethod() == Method.APPROVED_WRAPPED_ESCROW) {
            problems.add("NON_EXPORTABLE_KEY_CANNOT_BE_EXPORTED");
        }

        if (key.recoveryMethod() == Method.PROVIDER_RECOVERY
                && !key.providerSupportsRestore()) {
            problems.add("PROVIDER_RESTORE_NOT_SUPPORTED");
        }

        if (key.recoveryMethod() != Method.NONE
                && key.ref().family().equals(key.recoveryProtectorId())) {
            problems.add("CIRCULAR_RECOVERY_DEPENDENCY");
        }

        // Chỉ những khóa cần lịch sử/khả năng phục hồi mới bắt buộc
        // có bằng chứng trong chính sách minh họa này.
        if (!key.hasHistoricalDependencies()) {
            return problems;
        }
        if (key.recoveryMethod() == Method.NONE) {
            problems.add("NO_RECOVERY_METHOD_FOR_DEPENDENCIES");
            return problems;
        }
        if (evidence == null || !key.ref().equals(evidence.ref())) {
            problems.add("MISSING_VERSION_MATCHED_EVIDENCE");
            return problems;
        }
        if (!evidence.integrityVerified() || !evidence.isolatedCopy()) {
            problems.add("BACKUP_PROTECTION_NOT_VERIFIED");
        }
        if (!evidence.restoreTestPassed()
                || evidence.lastRestoreTestAt() == null
                || evidence.lastRestoreTestAt().isBefore(
                        now.minus(90, ChronoUnit.DAYS))) {
            problems.add("RESTORE_DRILL_MISSING_OR_STALE");
        }
        if (evidence.verifiedAt() == null
                || evidence.verifiedAt().isBefore(
                        now.minus(7, ChronoUnit.DAYS))) {
            problems.add("EVIDENCE_NOT_RECENT");
        }
        return problems;
    }

    public static void main(String[] args) {
        Instant now = Instant.now();
        KeyRef kekV3 = new KeyRef("billing-kek", "v3");
        KeyRef kekV4 = new KeyRef("billing-kek", "v4");
        KeyRef session = new KeyRef("tls-session", "transient");

        List<KeyAsset> keys = List.of(
                new KeyAsset(kekV3, Kind.KEK, false, true,
                        Method.PROVIDER_RECOVERY, "independent-dr", true),
                new KeyAsset(kekV4, Kind.KEK, false, true,
                        Method.PROVIDER_RECOVERY, "independent-dr", true),
                new KeyAsset(session, Kind.EPHEMERAL, false, false,
                        Method.NONE, null, false));

        Map<KeyRef, BackupEvidence> evidence = new HashMap<>();
        evidence.put(kekV3, new BackupEvidence(
                kekV3, now.minus(1, ChronoUnit.DAYS),
                now.minus(30, ChronoUnit.DAYS), true, true, true));
        // Cố ý thiếu evidence cho v4 để phát hiện version chưa được bảo vệ.

        for (KeyAsset key : keys) {
            List<String> errors = evaluate(
                    key, evidence.get(key.ref()), now);
            String result = errors.isEmpty() ? "POLICY_METADATA_PASS"
                    : String.join(",", errors);
            System.out.println(key.ref() + ": " + result);
        }
    }
}
~~~

### 10.1. Hiểu đúng kết quả

- **KEK v3** đủ trường minh họa sẽ trả về `POLICY_METADATA_PASS`, nhưng **không chứng minh dữ liệu thật phục hồi được**; đó là trách nhiệm của các phép restore test bên ngoài.
- **KEK v4** có dependency nhưng thiếu evidence theo version sẽ được gắn `MISSING_VERSION_MATCHED_EVIDENCE`, thay vì tin vào backup của v3.
- **Khóa phiên tạm thời** không bị yêu cầu sao lưu và không có vật liệu khóa được giữ trong ví dụ.
- Nếu key được đánh dấu **non-exportable**, công cụ từ chối phương án escrow yêu cầu **xuất** vật liệu khóa từ key đó. Điều này không nói provider-native recovery chắc chắn khả thi: phải kiểm chứng riêng.
- Các mốc **7 ngày/90 ngày** chỉ là **giá trị minh họa** để thấy cách kiểm tra độ mới. Chu kỳ thật phải theo rủi ro và policy, có thể khác theo loại khóa.
- Trường `recoveryProtectorId` chỉ giúp phát hiện vòng phụ thuộc **trực tiếp**, không thay thế kiểm tra **đồ thị phụ thuộc nhiều tầng**.
- Demo không đối chiếu policy IAM, backup manifest thực, hạ tầng đa region, secret leakage, tình trạng revoked hay crypto-shredding; **không được dùng như kết luận DR PASS cho production**.

## 11. Vòng đời và retention của bản sao khóa

Backup policy cần theo sát các thay đổi vòng đời:

| Giai đoạn khóa | Điều kiện đối với backup/recovery | Cảnh báo |
| --- | --- | --- |
| **Generate** | Xác định khóa có cần khả năng khôi phục không; kiểm tra nguồn entropy và custody. | Không mở đường dùng dữ liệu lâu dài nếu key recovery chưa được bảo đảm theo policy. |
| **Register/Provision** | Ghi owner, key ID/version, usage, phương pháp recovery, nguồn và người phê duyệt. | Thiếu metadata khiến restore nhầm khóa hoặc nhầm tenant. |
| **Store** | Bảo vệ bản sao theo cơ chế hỗ trợ, kiểm soát IAM, isolation, integrity. | Backup rõ hoặc cùng quyền xóa với production. |
| **Use** | Gắn data/ciphertext/signature với phiên bản khóa; giám sát việc phát sinh dependency mới. | Key version mới dùng trước khi recovery sẵn sàng. |
| **Rotate** | Bảo vệ successor và duy trì predecessor còn cần đọc/verify lịch sử. | Xóa bản cũ ngay khi alias current chuyển. |
| **Retire/Disable** | Hạn chế thao tác mới nhưng cân nhắc nhu cầu giải mã/xác minh lịch sử. | Backup restore tái kích hoạt quyền cũ ngoài policy. |
| **Revoke/Compromise** | Cô lập và đánh giá bản sao, cập nhật trust và quyền, điều tra lộ backup. | Một bản backup cũ còn chứa secret bị lộ hoặc trust đã lỗi thời. |
| **Destroy** | Kiểm kê và hủy tất cả bản sao thuộc phạm vi, lưu bằng chứng, xử lý retention. | Tuyên bố crypto-shred khi vẫn còn đường khôi phục. |

### 11.1. Retention không chỉ dựa trên thời gian

Một câu lệnh “giữ backup 30 ngày” có thể xung đột với dữ liệu lưu 7 năm, hoặc ngược lại giữ private key ký quá lâu dù không còn nhu cầu. Chính sách phải tính:

- **Cryptoperiod/key lifetime** và thời hạn sử dụng khóa cho thao tác mới.
- **Thời hạn lưu trữ dữ liệu**, bản sao, snapshot và archive liên quan.
- **Nhu cầu kiểm chứng chữ ký/chứng chỉ lịch sử** và bằng chứng thời gian.
- **Yêu cầu pháp lý hoặc legal hold** nếu áp dụng.
- **Kế hoạch tiêu hủy bí mật** và việc nền tảng có thật sự cho xóa mọi bản sao trong thời gian mong muốn không.

**Retention của dữ liệu đã mã hóa không tự là retention của private key ký.** Mỗi loại có tiêu chí phục hồi và chứng cứ khác nhau.

## 12. Phân quyền, kiểm toán và kiểm soát nội bộ

Vì phục hồi khóa có thể khôi phục quyền đọc dữ liệu hoặc tạo chữ ký, đây là **thao tác đặc quyền cao**. Một backup policy cần xác định vai trò:

| Vai trò | Quyền thường phù hợp | Điều không nên được mặc định |
| --- | --- | --- |
| **Service owner** | Khai báo dependency, nhu cầu DR, đánh giá RPO/RTO. | Không tự có quyền export root key. |
| **Backup operator** | Chạy backup/kiểm tra trạng thái theo quy trình. | Không mặc định được giải mã hoặc xem secret. |
| **Recovery approver** | Phê duyệt restore với căn cứ và phạm vi rõ. | Không mặc định được thay policy một mình. |
| **KMS/HSM administrator** | Quản trị key objects/policy theo nhiệm vụ. | Không tự được đọc dữ liệu ứng dụng hoặc vượt quorum. |
| **Security/incident responder** | Quyết định cô lập, thu hồi trust, đánh giá sự cố. | Không tự mở lại khóa compromised. |
| **Auditor** | Xem nhật ký, bằng chứng, kết quả restore drill. | Không cần quyền Sign/Decrypt/Unwrap/Export. |

Trong hệ thống rủi ro cao, dùng **separation of duties**, **dual control/quorum**, phương thức xác thực mạnh và phê duyệt độc lập cho thao tác khôi phục, xuất bản sao hoặc hủy.

### 12.1. Audit nên ghi gì?

- **BackupCreated:** backup reference, key family/version, method, actor, policy ID, thời điểm và kết quả.
- **BackupIntegrityVerified:** phiên bản manifest, cơ chế xác thực, kết quả, nơi lưu evidence.
- **RestoreRequested/Approved/Denied:** người yêu cầu/duyệt, lý do, phạm vi, sự cố liên quan.
- **RestoreTested:** môi trường thử, mẫu versions/datasets, thời gian RTO, kết quả và lỗi.
- **KeyPolicyReconciled:** danh tính/ủy quyền phiên bản hiện hành sau restore, trạng thái revoke.
- **BackupDeleted/KeyDestroyed:** điều kiện retention, phụ thuộc đã giải quyết và bằng chứng thao tác.

**Không log khóa rõ, HSM backup blob nhạy cảm, plaintext passphrase, seed, DEK hoặc private key**. Ngay cả vị trí recovery và quan hệ key dependencies cũng cần phân loại quyền truy cập thích hợp.

## 13. Tình huống thực tế: phục hồi hệ thống thanh toán

Một tổ chức vận hành ba hệ thống:

- **Billing Service:** dữ liệu hóa đơn AES-GCM, DEK bọc dưới KEK trong KMS.
- **Payment Service:** private key Ed25519 ký sự kiện; Ledger Service giữ public key và chính sách xác minh.
- **API Gateway:** dùng TLS/mTLS và chứng chỉ workload.

### 13.1. Sự cố mất vùng triển khai KMS

**Trước sự cố:** tổ chức đã kiểm thử cơ chế recovery/region resilience được KMS hỗ trợ; inventory ghi key family/version, owner, wrapped DEK và backup dependencies. Public key, certificates và trust policies cũng được lưu có bảo vệ.

**Khi xảy ra sự cố:**

1. Chặn thao tác nhạy cảm không được phép, chuyển điều phối tới đội DR.
2. Khôi phục kho dữ liệu ở **mốc phục hồi có thể đối chiếu key versions**.
3. Khôi phục khả năng dùng KEK thông qua cơ chế KMS/HSM được phê duyệt, không xuất plaintext KEK ra máy vận hành.
4. Áp dụng IAM/trust và danh sách revoked hiện hành trước khi cho phép Decrypt/Sign.
5. Thử unwrap các DEK đại diện, giải mã bản mã với nonce/tag/AAD phù hợp và đối chiếu kết quả đã biết.
6. Thử xác minh các sự kiện Payment ký bằng public key còn được tin theo lịch sử.
7. Đo RTO và ghi các key versions hoặc backup chưa được phục hồi; chỉ trả traffic khi đạt tiêu chí.

**Kết luận:** Nếu **KEK v5 chưa có recovery path**, một bản DB backup chứa wrapped DEK dưới v5 có thể không giải mã được. Policy phải phát hiện việc này **trước khi** v5 mã hóa dữ liệu không thể thay thế.

### 13.2. Sự cố khóa ký bị nghi lộ

Private key ký S1 bị nghi lộ; Payment Service đã chuyển sang S2. Một snapshot DR cũ vẫn chứa policy S1 có quyền SIGN.

- Restore snapshot **không được bật lại quyền Sign S1**.
- Ledger Service cần cập nhật **trust/revocation policy**, không chỉ kiểm tra chữ ký toán học.
- Các chữ ký lịch sử có thể cần public key S1 cùng bằng chứng thời gian/trạng thái theo chính sách.
- Backup của private key S1 cần được cô lập, đánh giá và tiêu hủy theo phương án xử lý sự cố và retention phù hợp.

**Đây là lý do backup policy phải phối hợp với incident response và key rotation policy**, thay vì được xem như một việc hạ tầng độc lập.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Backup private key/KEK dạng rõ để “chắc ăn” | Tạo thêm điểm lộ dữ liệu hoặc khả năng ký giả. | Provider-native secure backup, approved wrapped import/export hoặc escrow chuẩn khi được phép. |
| Tin multi-region replication là backup bất biến | Xóa nhầm hoặc compromise có thể lan sang replica. | Phân tích failure domain và hành vi delete, có lớp recovery độc lập khi cần. |
| Chỉ backup ciphertext, quên wrapped DEK/key version | Dữ liệu còn nhưng không giải mã được. | Bảo vệ metadata và đường phục hồi DEK/KEK cùng data snapshot. |
| Backup chỉ current alias, bỏ predecessor | Dữ liệu ký/mã hóa lịch sử mất khả năng verify/decrypt. | Giữ mapping key material version và dependencies. |
| Restore policy cũ mà không đối soát revocation | Khóa đã bị lộ được mở lại quyền. | Reconcile IAM/trust và trạng thái sự cố trước khi sử dụng. |
| Backup KEK mã hóa bằng chính KEK đó | Không thể bootstrap khi KEK gốc mất. | Recovery root độc lập, tránh circular dependency. |
| Một admin có quyền sao lưu, export, restore, xóa | Kẻ chiếm quyền có thể lấy hoặc phá toàn bộ khóa. | Dual control, quorum, least privilege, audit. |
| Backup thành công nhưng chưa từng restore thử | Không biết có thể mở đúng key và dữ liệu không. | Kiểm thử khôi phục đại diện, fail scenarios và đo RPO/RTO. |
| Kích hoạt key version trước khi recovery bảo đảm | Phát sinh bản mã mới không thể phục hồi khi sự cố. | Gating theo readiness và key-version evidence. |
| Dùng cùng secret cho production và DR không phân quyền | Mở rộng phạm vi compromise. | Tách trust domain, kiểm soát quyền và cơ chế recovery an toàn. |
| Xem non-exportable là không thể mất khóa | Có thể thiếu cơ chế restore hoặc bị xóa theo provider. | Xác minh khả năng DR của dịch vụ, thử restore bằng quy trình hỗ trợ. |
| Xóa một alias rồi coi đã crypto-shred | Secret vẫn còn trong key object, backup hoặc replica. | Kiểm kê tất cả bản sao và bằng chứng hủy thực. |
| Hủy KEK v1 khi backup còn DEK bọc dưới v1 | Không thể phục hồi archive. | Dependency inventory và restore testing trước hủy. |
| Chỉ rotate KEK sau khi DEK đã lộ | Ciphertext cũ vẫn có nguy cơ giải mã. | Đánh giá thay DEK/re-encrypt và phạm vi bản sao bị lộ. |
| Dùng checksum công khai như bằng chứng nguồn backup | Attacker sửa cả backup và checksum. | Xác thực manifest/backup bằng cơ chế mật mã có trust phù hợp. |
| Lưu backup quá lâu mà không xử lý khóa đã thu hồi | Secret bị lộ tồn tại hoặc có thể tái kích hoạt. | Retention theo lifecycle, xử lý compromised và kiểm soát destroy. |

## 15. Checklist để phê duyệt backup policy

Trước khi áp dụng chính sách, người thiết kế nên xác minh:

1. **Phạm vi** khóa/dữ liệu/certificates/metadata được bảo vệ đã được xác định chưa?
2. **DEK, KEK, signing key, identity key, MAC key và ephemeral secret** có được phân loại riêng không?
3. Khóa nào thực sự có recovery path? **Nhà cung cấp đã xác nhận và kiểm thử khả năng restore chưa?**
4. Có quy định **key material version**, predecessor và các phụ thuộc ciphertext/backup không?
5. Backup có dùng **secure wrapping/escrow/provider-native recovery**, không plaintext key dump không?
6. Recovery root có **độc lập với miền lỗi** cần khôi phục và không có phụ thuộc vòng không?
7. Quyền Backup/Restore/Export/Approve/Destroy có được tách và yêu cầu quorum thích hợp không?
8. Có chống sửa/xóa backup, xác thực nguồn manifest và lưu lịch sử audit không?
9. RPO có xử lý **key version mới ngay trước sự cố**? RTO có tính cả approval và kiểm thử không?
10. Restore đã được thử với **key cũ và key mới**, dữ liệu ở backup, nhiều tenant/region chưa?
11. Quy trình restore có áp **revocation/trust/IAM hiện hành** trước khi mở quyền sử dụng không?
12. Khi rotate KEK, chính sách phân biệt **rewrap DEK** với **thay DEK và re-encrypt** không?
13. Khi một key bị compromised, có thể định vị mọi bản sao và cấm dùng lại khóa đó không?
14. Khi cần crypto-shred, đã xác nhận **mọi đường khôi phục secret** trong phạm vi cần hủy chưa?
15. Có owner, lịch review, KPI và bằng chứng chứng minh khả năng khôi phục theo yêu cầu không?

## 16. Câu hỏi tự kiểm tra

1. Backup policy khác replication và high availability ở mục tiêu nào?
2. Vì sao có backup ciphertext mà thiếu DEK/KEK có thể vẫn làm mất dữ liệu?
3. Một key KMS **non-exportable** có tự bảo đảm luôn phục hồi được không? Cần xác minh gì?
4. Trong envelope encryption, backup cần ghi lại thông tin nào để tìm đúng key version giải mã?
5. Vì sao **RPO với key material version mới** đôi khi phải nghiêm ngặt hơn chu kỳ backup database?
6. Thế nào là **circular recovery dependency**? Làm sao tránh nó?
7. Vì sao backup private key ký có rủi ro khác backup private key giải mã?
8. Một bản backup cũ được xác thực toàn vẹn có được phép khôi phục quyền SIGN của khóa đã thu hồi không?
9. Vì sao chỉ có “backup completed” chưa đủ chứng minh đạt RTO?
10. **Rotate KEK** khác **rotate DEK** thế nào khi DEK đã bị lộ?
11. Nếu muốn **crypto-shredding**, vì sao các bản backup và escrow phải được đưa vào phạm vi kiểm kê?
12. Quyền của người chạy backup, người duyệt restore và người hủy khóa cần được phân tách ra sao?
13. Tại sao phục hồi metadata key inventory và certificate trust vẫn quan trọng dù public key không phải bí mật?
14. Khi restore một hệ thống nhiều tenant, phải kiểm soát điều gì để tránh tenant A có quyền giải mã dữ liệu tenant B?

**Ghi nhớ:** **Backup policy** là chính sách **bảo đảm có thể khôi phục những khóa và thông tin cần thiết, đồng thời không làm lộ hoặc tái kích hoạt bí mật sai chính sách**. Thiết kế đúng phải kết hợp **phân loại khóa, key ID/version và dependency inventory, KMS/HSM recovery được hỗ trợ, bảo vệ backup, RPO/RTO, restore drill, tách quyền, audit, rotation, revocation và destruction**. Không nên đo thành công bằng số file đã sao lưu, mà bằng **khả năng phục hồi đúng dữ liệu, đúng phiên bản và đúng quyền trong tình huống sự cố thực tế**.
