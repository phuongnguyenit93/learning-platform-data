# Key custodian — Người bảo quản và vận hành khóa mật mã

## 1. Key custodian là ai và vì sao vai trò này quan trọng?

**Key custodian** là cá nhân, nhóm hoặc chức năng được tổ chức **giao trách nhiệm bảo quản, quản trị kỹ thuật và duy trì các biện pháp kiểm soát đối với vật liệu khóa mật mã** trong phạm vi được ủy quyền. Key custodian thường vận hành hoặc quản lý hệ thống lưu trữ và sử dụng khóa như **KMS (Key Management Service)**, **HSM (Hardware Security Module)**, keystore, secret manager, thiết bị phần cứng và những quy trình backup, rotation, khôi phục hoặc hủy khóa.

Ví dụ, doanh nghiệp có dịch vụ `billing-invoice-signer` dùng private key để ký hóa đơn. **Key owner** thuộc bộ phận chịu trách nhiệm hóa đơn quyết định khóa chỉ dùng ký hóa đơn sản xuất, cryptoperiod và tiêu chí thu hồi. **Key custodian** thuộc nhóm quản trị khóa bảo đảm private key được tạo trong HSM phù hợp, gắn đúng định danh, cấp quyền tối thiểu cho workload được phê duyệt, theo dõi trạng thái và thực thi rotation theo quy trình. **Key user** là dịch vụ ký được cho phép gọi API `Sign` sau khi nội dung hóa đơn đã được phê duyệt.

Một điểm thường bị hiểu sai: **Key custodian không đồng nghĩa người sở hữu khóa theo nghiệp vụ, không mặc nhiên có quyền biết private key dạng rõ và không mặc nhiên được ký hay giải mã bất kỳ dữ liệu nào**.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, vai trò này gắn với vòng đời khóa **từ tạo, cấp phát, lưu trữ, sử dụng, xoay vòng đến thu hồi và hủy**, đồng thời là một mắt xích khi thiết kế mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, IAM và kiểm toán.

> **Nguyên tắc cốt lõi:** **Custodianship là trách nhiệm bảo vệ và vận hành khóa dưới chính sách đã được phê duyệt, không phải quyền sử dụng không giới hạn đối với mọi bí mật.** Tổ chức phải tách được **người quyết định mục đích**, **người vận hành biện pháp bảo vệ**, **người thực hiện phép toán mật mã** và **người kiểm tra độc lập**.

### Mục tiêu sau bài học

1. Phân biệt **key custodian**, **key owner**, **key user**, **security reviewer** và **auditor**.
2. Thiết kế ranh giới quyền với KMS/HSM, quản trị key inventory và vòng đời.
3. Giải thích cách custodian tham gia sinh khóa, lưu trữ, cấp quyền, backup, rotation, suspend và destroy.
4. Hiểu việc thực thi **separation of duties**, dual control, key ceremony và audit trong những bối cảnh cần thiết.
5. Vận dụng mô hình trách nhiệm cho **DEK/KEK**, khóa ký số, HMAC key, private agreement key và recovery key.

## 2. Phân biệt Key custodian với các vai trò liên quan

Tên chức danh thực tế có thể khác nhau: *key administrator*, *HSM operator*, *cryptographic officer*, *key manager* hoặc một nhóm vận hành. Không nên tự đồng nhất mọi chức danh này, vì quyền chi tiết phụ thuộc chính sách và sản phẩm.

| Vai trò | Câu hỏi họ chịu trách nhiệm | Ví dụ quyết định/hành động |
| --- | --- | --- |
| **Key owner** | **Tại sao** khóa tồn tại, dùng cho dữ liệu nào, chấp nhận rủi ro gì? | Phê duyệt purpose, cryptoperiod, scope, rotation và việc cho phép khôi phục |
| **Key custodian** | Khóa được **tạo, bảo quản, phân phối quyền, bảo trì và tiêu hủy** ra sao theo phê duyệt? | Cấu hình key policy, tạo tài nguyên trong HSM/KMS, vận hành backup, thực hiện rotation |
| **Key user / cryptographic operator** | Ai dùng khóa để thực hiện **phép toán nghiệp vụ**? | Workload được gọi `Encrypt`, `Sign`, `GenerateMac`, `Unwrap` theo scope |
| **Application owner** | Ứng dụng có dùng đúng key/version/protocol và xử lý kết quả đúng không? | Thiết kế luồng ký, AAD, nonce, cache, rollover và xử lý lỗi |
| **Security reviewer / approver** | Thiết kế và ngoại lệ có đáp ứng yêu cầu an ninh không? | Đánh giá algorithm, IAM, separation of duties, incident và chính sách |
| **Auditor** | Có bằng chứng các quyết định và thao tác thực tế tuân thủ chính sách không? | Đối soát key inventory, audit log, approval và nhật ký rotation |
| **Incident responder** | Phải cô lập cái gì, bằng cách nào và trong bao lâu khi nghi lộ khóa? | Suspend key, thu hồi grant, đánh giá dữ liệu đã lộ, yêu cầu thay khóa |
| **Cloud/HSM provider** | Hạ tầng cung cấp những tính năng và bảo đảm kỹ thuật nào? | Vận hành module, API tạo khóa, bảo vệ vật liệu theo phạm vi dịch vụ |

**Key owner có thể kiêm custodian trong một tổ chức nhỏ**, nhưng khi mức rủi ro cao, cần đánh giá việc tách vai trò hoặc các **kiểm soát bù trừ**. Ngay cả khi hai vai trò thuộc cùng bộ phận, **phê duyệt và thực thi nên có bằng chứng độc lập phù hợp với rủi ro**.

### Ví dụ ranh giới quyết định

Nếu chủ hệ thống yêu cầu cấp quyền `Decrypt` cho một dịch vụ hỗ trợ khách hàng:

- **Key owner** xác định có cho phép đọc dữ liệu theo nghiệp vụ không, phạm vi và điều kiện.
- **Security reviewer** đánh giá rủi ro và yêu cầu MFA, giới hạn tenant, theo dõi hoặc phê duyệt bổ sung.
- **Key custodian** thiết lập IAM/key policy đúng quyết định, thử deny ngoài phạm vi và lưu evidence.
- **Ứng dụng** chịu trách nhiệm không tự động giải mã dữ liệu chỉ vì API KMS cho phép.
- **Auditor** kiểm tra sự khớp giữa quyết định và các lượt dùng key thực tế.

Không nên để custodian tự cấp quyền cho chính mình rồi dùng `Decrypt` để “kiểm tra dữ liệu” mà không có nhiệm vụ và phê duyệt.

## 3. RACI và separation of duties trong quản lý khóa

**RACI** là một cách phân công trách nhiệm: **Responsible** là bên thực thi, **Accountable** là bên chịu trách nhiệm quyết định, **Consulted** là bên được tham vấn và **Informed** là bên cần được thông báo.

Bảng sau là **mô hình tham khảo**, không phải chuẩn bắt buộc cho mọi công ty:

| Hoạt động | Key owner | Key custodian | Key user / App owner | Security reviewer | Auditor |
| --- | --- | --- | --- | --- | --- |
| Định nghĩa purpose/data scope | **A** | C | **R/C** | C | I |
| Chọn thuật toán và cryptoperiod | **A** | **R/C** | C | **C/R** | I |
| Sinh/tạo tài nguyên khóa | A | **R** | I | C | I |
| Thiết lập key policy và IAM | **A** | **R** | C | C | I |
| Dùng khóa ký/mã hóa production | A cho chính sách | I | **R** | C khi cần | I |
| Phê duyệt rotation | **A** | **R** triển khai | C | C | I |
| Thực thi suspend khẩn cấp | I/A theo runbook | **R** | R cô lập ứng dụng | **A/R** cho ứng cứu | I |
| Phê duyệt resume sau sự cố | **A** | R áp dụng | C | **C/A** theo quy trình | I |
| Backup/restore key material | A theo chính sách | **R** | C | C | I |
| Phê duyệt hủy khóa | **A** | R thực thi | C xác nhận phụ thuộc | C | I |
| Kiểm tra nhật ký và compliance | I | C | C | C | **R** |

Không nên coi một ô RACI là **quyền IAM**. Một người có trách nhiệm **giám sát** không có nghĩa được truy cập raw key material, và người **Responsible for rotation** không mặc nhiên có thể tự phê duyệt hủy vĩnh viễn.

### Separation of duties bảo vệ khỏi điều gì?

Nó giảm khả năng một người hoặc một tài khoản thực hiện trọn chuỗi:

~~~text
Tự tạo key -> Tự sửa key policy -> Tự cấp Decrypt/Sign
-> Tự sử dụng bí mật -> Tự xóa hoặc sửa audit
~~~

Một thiết kế có **sự phân tách nhiệm vụ phù hợp** làm khó việc lạm dụng đặc quyền không bị phát hiện và giúp rà soát quyết định sau sự cố.

Nhưng cần hiểu hạn chế: hai tài khoản đăng nhập khác nhau **không phải hai người kiểm soát độc lập** nếu cùng do một admin nắm credential. Dual control chỉ có ý nghĩa khi **căn cước, thiết bị xác thực, quyền và luồng phê duyệt thực sự độc lập**.

## 4. Trách nhiệm của custodian theo từng giai đoạn vòng đời khóa

~~~mermaid
flowchart TD
    A[Key owner phê duyệt mục đích và chính sách] --> B[Custodian tạo/tiếp nhận key material]
    B --> C[Đăng ký inventory và bảo vệ KMS/HSM]
    C --> D[Pre-activation: kiểm tra IAM, policy, sẵn sàng sử dụng]
    D --> E[Active: giám sát và hỗ trợ vận hành]
    E --> F{Rủi ro hoặc đến hạn?}
    F -->|Rotation theo kế hoạch| G[Tạo v2 và cutover có kiểm soát]
    F -->|Nghi compromise| H[Suspend/cô lập và ứng cứu]
    G --> I[Deactivated: xử lý dữ liệu/chữ ký cũ]
    H --> J[Thay key hoặc resume theo đánh giá]
    J --> I
    I --> K{Hết phụ thuộc và retention?}
    K -->|Chưa| L[Giữ legacy access tối thiểu và rà soát]
    L --> K
    K -->|Rồi| M[Phê duyệt và chứng thực destruction]
~~~

Các tên **Pre-activation, Active, Suspended, Deactivated, Compromised, Destroyed** là trạng thái **logic**. Không phải KMS nào cũng hỗ trợ từng tên này như trạng thái resource; custodian phải ánh xạ thành quyền và hoạt động thực thi theo **semantics của nhà cung cấp**.

| Giai đoạn | Trách nhiệm của key custodian | Bằng chứng cần giữ |
| --- | --- | --- |
| **Tạo/nhập** | Xác minh thuật toán, nguồn ngẫu nhiên, vị trí tạo, quyền export | Key ID/version, request, provenance, HSM/KMS event |
| **Pre-activation** | Chặn sử dụng production trước phê duyệt; kiểm tra IAM và metadata | Negative test, policy version, phê duyệt activation |
| **Active** | Duy trì quyền tối thiểu, trạng thái, backup/DR, log và giám sát | Audit dùng khóa, review định kỳ, owner |
| **Rotation** | Tạo v2, chuẩn bị client, cutover, migration và retirement | Key version, rewrap/re-encrypt progress, kết quả kiểm thử |
| **Suspended** | Áp dụng biện pháp cô lập, kiểm tra chặn thực tế | Incident ID, grant changes, deny evidence |
| **Deactivated** | Ngừng new use, giữ legacy operation được phép nếu cần | Dependency inventory, data restore/verify evidence |
| **Compromised** | Phối hợp điều tra, thay key, thu hồi quyền và trust | Timeline, phạm vi ảnh hưởng, hành động ứng cứu |
| **Destroyed** | Tiêu hủy đúng quy trình, rà soát backup/replica | Approval, provider evidence, destruction record |

### Không đánh đồng trạng thái KMS với trạng thái nghiệp vụ

Một key `Enabled` trong KMS vẫn có thể **chưa active cho nghiệp vụ** vì chưa được key owner phê duyệt. Một key `Deactivated` có thể còn cần dùng để `Decrypt` dữ liệu cũ; nếu custodian disable toàn bộ resource, ứng dụng có thể mất khả năng truy cập.

Nhiệm vụ của custodian là **thực thi chính sách chi tiết**, không chỉ bật/tắt resource theo tên trạng thái.

## 5. Sinh khóa: custodian chịu trách nhiệm chất lượng nguồn tạo

Khóa an toàn phải được **sinh bằng nguồn entropy và cơ chế mật mã phù hợp**. Custodian chịu trách nhiệm vận hành, chọn môi trường và kiểm tra bằng chứng của quá trình này theo thiết kế đã duyệt.

### Các điểm cần kiểm tra trước khi tạo

1. **Key type / algorithm:** AES-256, RSA, EC P-256, X25519, HMAC key, KEK hoặc DEK có đúng mục đích và năng lực sản phẩm không?
2. **Nguồn ngẫu nhiên:** CSPRNG/DRBG của HSM/KMS hoặc provider được chấp thuận; không dùng timestamp, seed cố định, PRNG mô phỏng hoặc thông tin dễ đoán để tạo bí mật.
3. **Vị trí sinh key:** Sinh **bên trong HSM/KMS** khi cần hạn chế xuất private key; nếu import key material, phải đánh giá **nguồn gốc** và quá trình bảo vệ trong lúc vận chuyển.
4. **Key usage:** Chỉ bật `Sign`, `Decrypt`, `Wrap`, `DeriveKey`... đúng chức năng và chính sách.
5. **Export policy:** Non-exportable ở nơi có hỗ trợ và phù hợp mục tiêu; không tự xuất khóa vì thuận tiện.
6. **Định danh:** Key ID/version, owner, environment, purpose, cryptoperiod và dependency inventory.
7. **Kiểm thử:** Kiểm tra cấu hình và tính năng provider, không cần xuất private key ra file để “chứng minh khóa tồn tại”.

### Key ceremony và nhiều người chứng kiến

Trong các môi trường yêu cầu mức bảo đảm cao như CA signing, HSM master/root key hoặc khôi phục khóa đặc biệt, tổ chức có thể tổ chức **key ceremony**: một buổi vận hành theo kịch bản phê duyệt trước, có các vai trò độc lập, log/bằng chứng và quy tắc xử lý thất bại.

**Dual control**, **split knowledge** và **M-of-N/threshold** có liên quan nhưng **không đồng nghĩa**:

- **Dual control:** Một thao tác nhạy cảm đòi sự tham gia hoặc phê duyệt của ít nhất hai bên được ủy quyền.
- **Split knowledge:** Không một người riêng lẻ nắm đủ thông tin bí mật để tái tạo toàn bộ khóa trong quy trình được thiết kế theo phương pháp này.
- **M-of-N/threshold:** Cần một số tối thiểu trong tổng số thành viên/share hoặc thiết bị để thực hiện hành động, theo cơ chế cụ thể.
- **Audit witness:** Có người chứng kiến/kiểm toán và bằng chứng sự kiện; người đó không nhất thiết giữ key share.

**Không phải mọi KMS/cloud HSM đều hỗ trợ key shares hoặc ngưỡng M-of-N theo cùng cách.** Không tự chia byte một AES key thành các đoạn rồi cho rằng đạt split knowledge; phải dùng một cơ chế đã được đánh giá và quy trình quản trị tương ứng.

## 6. Lưu trữ, bảo vệ vật liệu và phân tách quyền trong KMS/HSM

### 6.1. Vì sao bảo quản khóa không có nghĩa đọc khóa?

Với **private signing key không xuất được**, custodian có thể cấu hình trạng thái, IAM và chứng thư mà **không sở hữu private key dạng rõ**. Tương tự, với KEK được quản lý trong KMS, ứng dụng có thể dùng API được phép mà không nhận raw KEK.

Sự phân tách này giảm nguy cơ rò rỉ từ máy trạm quản trị, ticket hỗ trợ, logs hoặc backup không kiểm soát.

### 6.2. Các nhóm quyền thường cần tách

| Nhóm quyền | Ví dụ thao tác | Ai thường cần |
| --- | --- | --- |
| **Key administration** | Create, update policy, enable/disable, schedule deletion | Custodian được ủy quyền |
| **Key usage** | Encrypt, Decrypt, Sign, GenerateMac, DeriveKey | Workload/key user đúng mục đích |
| **Grant management** | Tạo/thu hồi grant cho principal | Admin được kiểm soát bởi policy |
| **Key export/import** | Import material hoặc xuất khi sản phẩm cho phép | Chỉ quy trình đặc biệt, kiểm soát chặt |
| **Recovery/backup** | Backup, restore, replicate theo cơ chế được hỗ trợ | Custodian/recovery role chuyên trách |
| **Approval** | Chấp nhận thay mục đích, rotation, mở quyền nhạy cảm | Key owner hoặc bên phê duyệt độc lập |
| **Audit review** | Đọc log, kiểm tra sử dụng bất thường | Auditor/security reviewer |

**Bẫy quyền gián tiếp:** Một admin có thể không có quyền `Decrypt` trực tiếp nhưng có quyền **sửa policy/grant** để tự cấp `Decrypt`. Vì vậy cần kiểm soát **khả năng tự nâng quyền**, không chỉ xét tên action hiện tại của role.

### 6.3. Bảo vệ cấu hình và secret

Custodian phải bảo đảm:

- Key policies, IAM roles, HSM partitions và trust settings được cấu hình theo **least privilege**.
- Quyền quản trị có MFA/thiết bị xác thực mạnh và quyền tạm thời khi phù hợp.
- Quy trình quản trị key có **change control**, review và lưu lịch sử version.
- Không đưa raw private key, HMAC secret, DEK/KEK hay seed RNG vào wiki, code repository, log, ticket, CI output hoặc chat.
- Metadata như key ID, owner, purpose, algorithm và policy reference được tách khỏi vật liệu bí mật.
- Thao tác xuất khóa hoặc tạo bản sao backup chỉ được thực hiện nếu chính sách và sản phẩm cho phép; có hạn chế đường vận chuyển, phân quyền và kiểm toán.

### KMS không phải phép thay thế cho thiết kế ứng dụng

Nếu custodian cấu hình KMS chặn `Encrypt` nhưng ứng dụng vẫn giữ plaintext DEK trong cache, các phép mã hóa/giải mã có thể tiếp tục **không đi qua KMS**. Ngược lại, key non-exportable ngăn xuất private key nhưng một workload đã có quyền `Sign` vẫn có thể ký nội dung không được phép nếu thiếu business approval.

Vì thế custodian cần phối hợp với application owner để hiểu **đường sử dụng thật**, đặc biệt là cache, session, queued jobs và các bên phụ thuộc.

## 7. Key inventory và metadata mà custodian cần quản lý

**Key inventory** là công cụ vận hành quan trọng để biết tổ chức đang giữ khóa nào, tại đâu, dùng bởi ai và còn phụ thuộc gì. Custodian thường chịu trách nhiệm cập nhật **thông tin kỹ thuật đáng tin**, nhưng **purpose và risk acceptance** vẫn thuộc phạm vi phê duyệt của key owner.

### Bản ghi mẫu

~~~yaml
keyId: "billing-invoice-signing-v2"
keyVersion: "v2"
purpose: "INVOICE_SIGNATURE"
environment: "production"
tenantScope: "billing"
algorithm: "ECDSA-P256-SHA256"
keyMaterialLocation: "HSM key handle / provider resource ID"
exportPolicy: "NON_EXPORTABLE"
lifecycleState: "ACTIVE"
createdAtUtc: "2030-01-02T08:00:00Z"
activatedAtUtc: "2030-01-10T00:00:00Z"
newUseUntilUtc: "2031-01-10T00:00:00Z"
owner: "billing-key-owner"
custodian: "platform-key-management"
approvedWorkload: "billing-invoice-signer"
approvedOperations:
  - "Sign"
keyPolicyVersion: "hsm-policy-v4"
certificateReference: "cert-record-id"
rotationPlanReference: "rotation-record-id"
recoveryPolicyReference: "approved-recovery-policy"
lastReviewReference: "security-review-id"
auditCorrelationReference: "key-create-event-id"
~~~

Bản ghi chỉ là **ví dụ cấu trúc**, không phải YAML cloud KMS có thể chạy ngay. **Không lưu private key hoặc raw symmetric key** trong inventory.

### Các nhóm trường và ý nghĩa

| Nhóm | Thông tin gợi ý | Tại sao custodian cần |
| --- | --- | --- |
| **Danh tính** | Key ID/version, provider resource ID, alias history | Tránh tác động nhầm phiên bản |
| **Mục đích** | Purpose, data domain, tenant, environment | Ngăn dùng khóa ngoài phạm vi |
| **Mật mã** | Algorithm, key type, key usage, export policy | Đảm bảo đúng chức năng |
| **Quản trị** | Owner, custodian, approval, IAM/key policy | Biết ai quyết định và ai thực thi |
| **Vòng đời** | State, cryptoperiod, rotation, destruction eligibility | Không dùng quá hạn hoặc xóa sớm |
| **Phụ thuộc** | Wrapped DEK versions, ciphertext, client/cert/trust, backup | Đảm bảo khả năng giải mã/xác minh |
| **Kiểm toán** | Created by, policy change, last review, audit references | Đối soát thực tế với phê duyệt |

Một khóa **không có owner hoặc purpose** không nên được xem là hoàn toàn hợp lệ chỉ vì KMS báo trạng thái `Enabled`. Custodian cần đưa khóa đó vào danh sách xử lý và yêu cầu chủ sở hữu xác nhận.

## 8. Cấp phát và phân phối khóa: “distribution” phải đúng đối tượng

Trách nhiệm **distribution** không đơn giản là gửi file chứa khóa tới người cần dùng. Với môi trường hiện đại, nhiều phương án **không yêu cầu phân phối raw key material**.

### 8.1. Đối với public key và chứng thư

Public verification key thường được công bố qua JWKS, PKI hoặc kênh trust được thiết kế. Custodian có thể thực thi phân phối chứng thư/metadata theo phê duyệt; bên nhận vẫn phải **xác minh nguồn tin cậy, key ID, hostname/identity và chính sách**.

### 8.2. Đối với symmetric key/DEK/KEK

Ưu tiên cấp **quyền gọi API KMS/HSM** thay vì phát plaintext key. Nếu một DEK cần được đưa vào bộ nhớ ứng dụng để dùng AES-GCM, thiết kế phải hạn chế thời gian lưu rõ, áp dụng least privilege, kiểm soát cache, không log và chuẩn bị phương án xóa/revoke theo mục tiêu rủi ro.

### 8.3. Đối với HMAC secret chia sẻ với đối tác

Một số giao thức yêu cầu cả sender và receiver có **cùng HMAC key**. Khi đó custodian cần đường phân phối bí mật được bảo vệ, phiên bản hóa, giới hạn đối tác và kiểm tra receipt theo chính sách. Không gửi secret qua email/chat không kiểm soát rồi chỉ “xóa tin nhắn” để coi như đã an toàn.

### 8.4. Đối với ECDH/X25519

**Private agreement key không được gửi cho đối tác** trong ECDH thông thường; các bên trao đổi **public key có xác thực** để tính shared secret. Custodian quản lý static agreement key theo chính sách và phối hợp với application owner về **peer authentication, curve, key usage và cryptoperiod**.

**Ephemeral ECDHE key** thường do giao thức tạo cho mỗi handshake, tồn tại ngắn; custodian có thể kiểm soát **cấu hình và provider**, thay vì duyệt thủ công từng private key phiên.

## 9. Vận hành sử dụng khóa: Key custodian không phải Key user

Một kiến trúc đúng có thể gồm ba cổng kiểm soát:

~~~mermaid
flowchart TD
    U[Workload yêu cầu sử dụng khóa] --> B[Business approval và data scope]
    B --> P[Application gate: purpose, tenant, state, key version]
    P -->|Không đạt| D[Từ chối và audit]
    P -->|Đạt| K[KMS/HSM: principal, operation, policy, key state]
    K -->|Không đạt| D
    K -->|Đạt| C[Cryptographic operation]
    C --> L[Audit theo key ID, caller, operation, result]
    D --> L
    O[Key owner phê duyệt purpose] --> P
    S[Key custodian quản trị policy/rotation] --> K
    A[Auditor đọc bằng chứng] --> L
~~~

**Custodian** bảo đảm lớp IAM/provider và trạng thái khóa được áp dụng; **application owner/key user** bảo đảm ngữ nghĩa nghiệp vụ đầu vào và giao thức.

Ví dụ, HSM không tự biết tài liệu được đưa tới `Sign` đã được phê duyệt là hóa đơn cuối cùng. Một key custodian **không nên được giao quyền ký mọi digest để “kiểm tra hộ ứng dụng”**. Kiểm thử có thể thực hiện với dữ liệu mẫu/quy trình đặc biệt được phê duyệt.

### Quy tắc bảo vệ lúc key được sử dụng

- Workload chỉ có quyền trên **đúng key ID/version** và environment/tenant cần thiết.
- Không tự fallback sang key cũ hoặc key test khi lệnh bị từ chối.
- Không in các secret vào log, metric label, exception, heap dump hoặc artifact.
- Kiểm soát truy cập vào nguồn metadata/state; caller không được tự tuyên bố một khóa `ACTIVE`.
- Khi có quyết định suspend, xử lý cả grants, cache, session và request đang chạy.
- Ghi audit đủ để truy nguyên operation, không ghi raw plaintext hoặc private material.

## 10. Vai trò custodian trong rotation của DEK/KEK

### 10.1. Envelope encryption có hai tầng khóa

Trong **envelope encryption**, **DEK ngẫu nhiên** mã hóa dữ liệu (thường bằng AES-GCM), còn **KEK** bảo vệ DEK qua wrap/unwrap hoặc cơ chế KMS phù hợp. Custodian chịu trách nhiệm giúp hệ thống tách rõ hai vai trò này.

~~~mermaid
flowchart LR
    Plain[Hóa đơn plaintext] --> Enc[AES-GCM dùng DEK ngẫu nhiên]
    DEK[DEK] --> Enc
    Enc --> Stored[(Ciphertext + nonce + tag + key version)]
    DEK --> Wrap[Wrap DEK]
    KEK[KEK trong KMS/HSM] --> Wrap
    Wrap --> Stored
    Stored --> Read[Reader: lấy wrapped DEK đúng version]
    Read --> Unwrap[Unwrap qua KMS/HSM theo quyền]
    KEK --> Unwrap
    Unwrap --> Dec[AEAD Decrypt và kiểm tra tag]
~~~

### 10.2. Nếu xoay KEK

Custodian có thể:

1. Sinh `KEK-v2` bằng KMS/HSM, cấu hình policy và owner.
2. Đảm bảo `KEK-v2` chưa được dùng cho production trước phê duyệt/cutover.
3. Phối hợp triển khai **reader hỗ trợ key version mới** trước khi writer đổi sang v2.
4. Cho phép **Wrap mới bằng v2** và ngừng Wrap mới bằng v1 theo chính sách.
5. Thực hiện/giám sát **rewrap DEK** hoặc cơ chế migration do provider hỗ trợ.
6. Đối soát wrapped DEK, backup và archive còn phụ thuộc v1 trước khi retire/hủy.

**Rewrap** có thể giữ nguyên DEK và ciphertext. Nhưng nếu **DEK đã bị lộ**, việc bọc DEK đó bằng KEK khác **không khôi phục tính bí mật** của dữ liệu lịch sử.

### 10.3. Nếu xoay DEK

Khi thay **DEK mã hóa trực tiếp dữ liệu**, có thể cần **re-encrypt** các bản mã cũ và cập nhật nonce, AAD, tag, key ID. Nếu dùng AES-GCM, phải bảo đảm **không lặp nonce dưới cùng khóa**.

Custodian chịu trách nhiệm về **bảo vệ khóa và quyền**; application/data owner chịu trách nhiệm tính đúng đắn của việc di chuyển dữ liệu và xác minh nội dung.

### 10.4. Chính sách tự động rotation của KMS

Một số KMS có thể tự xoay **backing key material** trong một logical key resource, nhưng điều này **không mặc nhiên làm toàn bộ ciphertext trong database được mã hóa lại**, không tự thay mọi private signing key hoặc key của đối tác.

Custodian phải hiểu rõ sự khác nhau giữa **logical resource**, **material version**, **application key version** và **alias** của sản phẩm đang dùng.

## 11. Khóa ký số, PKI, HMAC và agreement key: trách nhiệm riêng

### 11.1. Private signing key

Với ECDSA/RSA-PSS/Ed25519 key dùng ký hóa đơn hoặc artifact:

- Sinh key pair theo nguồn an toàn, lý tưởng ở vùng bảo vệ được yêu cầu.
- Hạn chế quyền export private key, giới hạn `Sign` cho workload hợp lệ.
- Phân phối public key/chứng thư; kiểm tra mục đích, chain và key usage theo chính sách.
- Theo dõi cryptoperiod, chứng thư, timestamp và kế hoạch **giữ thông tin xác minh chữ ký cũ**.
- Khi nghi lộ khóa, cô lập quyền, đánh giá những chữ ký đã tạo và khả năng giả mạo.

**Verify bằng public key** thường không cần private signing key đã nghỉ dùng; vì vậy không nên xóa mọi chứng thư cũ chỉ vì đã rotate khóa ký.

### 11.2. HMAC key

HMAC dùng **cùng secret** cho tạo và kiểm tra MAC. Nếu cần xoay khóa webhook, custodian phải phối hợp việc phát secret mới đến sender/receiver, key version, grace period và xử lý retry. Khác với verify chữ ký số, **verify HMAC vẫn cần secret**.

Một đối tác có HMAC key bị lộ có thể giả mạo MAC trong phạm vi biết secret; chỉ ngừng tạo MAC mới bằng key cũ **không chặn được bên nhận còn chấp nhận key đó**.

### 11.3. Private ECDH/X25519 key

Custodian theo dõi static agreement key, quyền `DeriveKey`, curve và việc phân phối public key có xác thực. **ECDH thuần túy không tự ngăn man-in-the-middle**; việc xác thực peer và ràng buộc transcript thuộc giao thức/ứng dụng.

Với ephemeral ECDHE keys, trách nhiệm quản trị thiên về **cấu hình giao thức, RNG, provider, kiểm thử và ứng cứu**, không phải lưu private scalar của từng handshake trong inventory dài hạn.

### 11.4. Recovery và password-derived key

Nếu một KEK được dẫn xuất từ mật khẩu, **reset mật khẩu đăng nhập không tự phục hồi được KEK cũ**. Custodian phải phối hợp với data owner về recovery wrap hoặc đường phục hồi độc lập theo chính sách, chứ không tạo một “master password” không kiểm soát.

Các khóa phục hồi và backup có mức nhạy cảm cao: quyền `Unwrap` có thể cần MFA, phê duyệt độc lập, phạm vi hẹp và audit rõ ràng.

## 12. Backup, restore và disaster recovery dưới trách nhiệm custodian

**Khóa có thể bị mất dù dữ liệu vẫn còn.** Nếu KEK bị hủy và mọi wrapped DEK phụ thuộc vào nó không còn đường giải bọc, dữ liệu mã hóa có thể trở nên không thể phục hồi. Ngược lại, backup không bảo vệ đúng có thể tạo bản sao key material ngoài kiểm soát.

### Những câu hỏi phải trả lời trước khi backup

1. **Khóa có xuất được không?** HSM/KMS có thể chỉ cho phép backup/replication theo cơ chế riêng; không phải mọi key non-exportable có thể tải về thành file.
2. **Backup cái gì?** Key material, key handle, wrapped key, metadata, chứng thư, IAM/policy, grant, hay phương tiện khôi phục do sản phẩm cung cấp?
3. **Ai giữ và mở backup?** Có dual control, key shares hoặc recovery officer theo mức rủi ro không?
4. **Khôi phục vào đâu?** Cùng HSM cluster, cùng account/region hay thiết bị DR khác; điều kiện trust và key usage ra sao?
5. **Làm thế nào chứng minh restore?** Kiểm tra trên môi trường được phép với dữ liệu mẫu và phép toán phù hợp, tránh phải xuất plaintext key.
6. **Retention và destruction:** Khi xóa key chính, có backup/replica vẫn giữ vật liệu hoặc wrapped DEK phụ thuộc không?

### Recovery không phải quyền mặc định của mọi custodian

Không nên cấp quyền `Decrypt` hoặc `Unwrap` cho một operator chỉ vì người đó vận hành backup. Nếu tổ chức cần **break-glass**, quy trình nên có danh tính riêng, chứng thực mạnh, approval, giới hạn thời gian, dữ liệu và số thao tác, cùng audit độc lập.

### Restore có thể đổi bối cảnh tin cậy

Khôi phục key material sang môi trường DR đòi rà soát **identity, tenant, IAM, policy, provider, chứng thư và các bản sao**. Không vì key sử dụng thuật toán AES-256 mà mặc định backup có thể được restore an toàn ở bất cứ nơi nào có AES.

## 13. Suspend, compromise và hủy khóa: trách nhiệm xử lý sự cố

Một key custodian cần biết cách **đình chỉ mà không xóa vĩnh viễn**, và biết lúc nào phải chuyển tình huống sang **compromise response**.

### 13.1. Suspend và disable

Khi có dấu hiệu rủi ro, custodian có thể thực thi `DisableKey`, thay grant/IAM hoặc chặn operation theo cơ chế KMS/HSM — **chỉ trong phạm vi được ủy quyền**. Sau đó phải:

- Xác minh tác dụng chặn bằng negative tests an toàn.
- Kiểm tra khả năng **còn DEK plaintext trong cache** hoặc session/traffic key đã cấp.
- Đánh giá tác động availability: disable một KEK có thể khiến hàng nghìn bản ghi không còn unwrap được.
- Phân biệt chặn **Sign mới** với khả năng **Verify chữ ký lịch sử** qua public key.

### 13.2. Nếu key material đã compromise

**Chỉ thay trạng thái `Suspended` không làm bản sao khóa bị đánh cắp biến mất.** Tổ chức cần:

1. Cô lập đường truy cập và danh tính liên quan.
2. Xác định đối thủ có raw key, credential KMS, ciphertext, wrapped DEK hoặc output ký hay không.
3. Tạo key material mới từ nguồn đáng tin nếu cần; không dùng lại khóa đã lộ.
4. Rà soát dữ liệu/chữ ký/token/phiên lịch sử phụ thuộc khóa.
5. Rewrap hoặc re-encrypt phù hợp — **nếu DEK đã lộ, chỉ rewrap không đủ**.
6. Thu hồi chứng thư, grant, JWKS trust hoặc thay secret đối tác theo trường hợp.
7. Lưu bằng chứng, báo cáo key owner/security/đối tác và xử lý theo yêu cầu tổ chức.

### 13.3. Destroy là thao tác nhạy cảm

Hủy khóa phải dựa trên **phê duyệt của key owner, kiểm tra hết phụ thuộc, retention, backup và khả năng phục hồi**. Custodian không nên dùng DeleteKey để “giải quyết nhanh” một sự cố nếu còn dữ liệu chưa thể mở bằng key khác.

Phải kiểm tra semantics **pending deletion**, **scheduled deletion**, **permanent destruction** và khả năng phục hồi của provider. Một alias bị xóa hoặc một tài nguyên `Disabled` không đồng nghĩa vật liệu khóa đã bị tiêu hủy.

## 14. Quy trình key ceremony và dual control khi rủi ro cao

Trong môi trường có HSM root key, CA private signing key hoặc recovery secret đặc biệt, custodian có thể đóng vai trò **operator chính** của buổi key ceremony nhưng không nhất thiết nắm độc quyền thông tin bí mật.

### Ví dụ quy trình chuẩn bị

~~~mermaid
sequenceDiagram
    participant Owner as Key owner
    participant Sec as Security reviewer
    participant Cust as Key custodian
    participant HSM as HSM/KMS
    participant Audit as Witness / Auditor
    Owner->>Sec: Phê duyệt mục đích và key ceremony plan
    Sec-->>Cust: Điều kiện thuật toán, role, môi trường và kiểm soát
    Cust->>Audit: Thông báo lịch, participants, checklist
    Audit-->>Cust: Xác nhận kiểm soát đầu vào
    Cust->>HSM: Tạo key theo cơ chế được phê duyệt
    HSM-->>Cust: Key handle/public metadata, không xuất secret
    Cust->>HSM: Áp dụng policy và giới hạn quyền sử dụng
    Audit->>Audit: Ghi nhật ký kiểm tra, serial/time/approval
    Cust->>Owner: Báo cáo key ID, kết quả và evidence
    Owner-->>Cust: Cho phép activation theo quy trình riêng
~~~

### Điều cần chứng minh

- **Người tham gia**: danh tính, quyền, vai trò và sự độc lập.
- **Môi trường**: HSM/firmware/provider, chính sách, tình trạng cấu hình được xác nhận.
- **Thao tác**: loại key, tham số, key ID, mục đích, hạn chế export, key usage.
- **Bằng chứng**: biên bản, chứng cứ test, mã tham chiếu, audit có bảo vệ toàn vẹn.
- **Ngoại lệ/thất bại**: ai được dừng, rollback, cách xử lý key tạo dở và thông báo.

Không ghi giá trị private key hoặc key share vào biên bản không được bảo vệ. Không mặc định video quay màn hình có hiển thị secret là bằng chứng tốt; nó có thể tạo thêm rủi ro rò rỉ.

## 15. Audit: custodian phải chứng minh điều gì?

**Có trách nhiệm vận hành** không có nghĩa cần thể hiện mọi bí mật trong audit. Audit hữu ích nên ghi **quyết định, danh tính, key metadata và kết quả** ở mức phục vụ điều tra mà không tiết lộ vật liệu khóa.

### Mẫu event minh họa

~~~yaml
eventType: "KEY_ROTATION_APPLIED"
keyId: "billing-kek-v3"
keyVersion: "v3"
purpose: "DEK_KEY_WRAPPING"
environment: "production"
requestedBy: "billing-data-owner"
approvedBy: "security-approver"
executedBy: "kms-custodian-a"
sourceState: "PRE_ACTIVATION"
targetState: "ACTIVE"
effectiveAtUtc: "2030-03-01T00:00:00Z"
changeTicketRef: "change-record-id"
policyRevision: "kms-policy-r12"
providerResult: "SUCCESS"
negativeTestRef: "deny-test-id"
dependentKeyMigrationRef: "rewrap-progress-id"
correlationId: "request-id"
~~~

Bản mẫu **không phải schema API chuẩn**; dữ liệu phải khớp event của nhà cung cấp và hệ thống identity/approval thực.

### Những event cần audit

| Event | Mục tiêu |
| --- | --- |
| `KEY_CREATED` / `KEY_IMPORTED` | Biết nguồn tạo và cấu hình |
| `POLICY_CHANGED` / `GRANT_CHANGED` | Phát hiện thay đổi quyền và đường leo thang |
| `KEY_ACTIVATED` / `KEY_SUSPENDED` | Truy ngược thay đổi khả năng sử dụng |
| `KEY_ROTATED` / `ALIAS_CHANGED` | Phân biệt đổi vật liệu với đổi routing |
| `SIGN` / `DECRYPT` / `UNWRAP` | Phát hiện sử dụng bất thường theo phạm vi provider hỗ trợ |
| `BREAK_GLASS_GRANTED` | Kiểm soát quyền khôi phục đặc biệt |
| `BACKUP_CREATED` / `RESTORE_TESTED` | Đối soát khả năng DR |
| `KEY_DELETION_SCHEDULED` / `KEY_DESTROYED` | Chứng minh điều kiện và thực thi tiêu hủy |

### Chỉ số giúp phát hiện rủi ro

- Số key active **thiếu owner/custodian/purpose**.
- Số grant có quyền vượt mức được phê duyệt hoặc cho phép principal tự nâng quyền.
- Số key đến hạn rotation hoặc quá cryptoperiod vẫn được dùng tạo dữ liệu mới.
- Lượt `Sign`, `Decrypt`, `Unwrap` bất thường theo key ID, workload, region hoặc tenant.
- Số key `Suspended` còn phát sinh operation thành công sau thời điểm chặn.
- Số wrapped DEK/backup/chứng thư còn phụ thuộc khóa sắp hủy.
- Tỉ lệ thử restore/negative test thành công và thời điểm review lần cuối.

**Không coi không có API call KMS là không còn phụ thuộc**: DEK có thể còn trong cache hoặc backup; các chữ ký cũ còn cần public key/chứng thư để kiểm tra.

## 16. Ví dụ Java 11+: phân tách quyền custodian và key user

Ví dụ sau mô phỏng một **policy gate** trên metadata: custodian được phép **thực thi rotation khi có phê duyệt độc lập của key owner**, còn **workload ký** chỉ được dùng key `ACTIVE` với Purpose `INVOICE_SIGNATURE`. Custodian **không tự động có quyền `Sign`**, và key user **không được quản trị key**.

Đây là minh họa logic cho việc phân tách trách nhiệm, **không tạo khóa thật hoặc gọi KMS/HSM**. Production phải có IAM/approval thực, không tin các object do client tự gửi.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public final class KeyCustodianSeparationDemo {
    enum Role {
        KEY_OWNER,
        KEY_CUSTODIAN,
        KEY_USER,
        AUDITOR
    }

    enum KeyState {
        PRE_ACTIVATION,
        ACTIVE,
        SUSPENDED,
        DEACTIVATED,
        COMPROMISED,
        DESTROYED
    }

    enum Action {
        ROTATE,
        SIGN
    }

    static final class Actor {
        final String identity;
        final Role role;

        Actor(String identity, Role role) {
            this.identity = Objects.requireNonNull(identity);
            this.role = Objects.requireNonNull(role);
        }
    }

    static final class KeyRecord {
        final String keyId;
        final String purpose;
        final String approvedSigner;
        final KeyState state;
        final Instant newUseUntil;

        KeyRecord(String keyId, String purpose, String approvedSigner,
                  KeyState state, Instant newUseUntil) {
            this.keyId = Objects.requireNonNull(keyId);
            this.purpose = Objects.requireNonNull(purpose);
            this.approvedSigner = Objects.requireNonNull(approvedSigner);
            this.state = Objects.requireNonNull(state);
            this.newUseUntil = Objects.requireNonNull(newUseUntil);
        }
    }

    static final class Approval {
        final String keyId;
        final Action action;
        final String requestedBy;
        final Actor approver;
        final Instant expiresAt;

        Approval(String keyId, Action action, String requestedBy,
                 Actor approver, Instant expiresAt) {
            this.keyId = Objects.requireNonNull(keyId);
            this.action = Objects.requireNonNull(action);
            this.requestedBy = Objects.requireNonNull(requestedBy);
            this.approver = Objects.requireNonNull(approver);
            this.expiresAt = Objects.requireNonNull(expiresAt);
        }
    }

    static void requireRotationAuthorization(
            Actor custodian, KeyRecord key, Approval approval, Clock clock) {
        Objects.requireNonNull(custodian);
        Objects.requireNonNull(key);
        Objects.requireNonNull(approval);
        Objects.requireNonNull(clock);

        // Không cho phép người sử dụng khóa tự quản trị.
        if (custodian.role != Role.KEY_CUSTODIAN) {
            throw new SecurityException("Custodian role required");
        }
        // Chính sách minh họa: owner phải phê duyệt riêng hành động ROTATE.
        if (approval.action != Action.ROTATE
                || !approval.keyId.equals(key.keyId)
                || approval.approver.role != Role.KEY_OWNER
                || approval.approver.identity.equals(custodian.identity)
                || !approval.requestedBy.equals(custodian.identity)
                || !clock.instant().isBefore(approval.expiresAt)) {
            throw new SecurityException("Independent approval required");
        }
        if (key.state == KeyState.COMPROMISED
                || key.state == KeyState.DESTROYED) {
            throw new SecurityException("Use incident workflow");
        }

        // Vẫn cần kiểm tra approval do hệ thống đáng tin cấp và trạng thái KMS.
    }

    static void requireInvoiceSignAuthorization(
            Actor caller, KeyRecord key, Clock clock) {
        Objects.requireNonNull(caller);
        Objects.requireNonNull(key);
        Objects.requireNonNull(clock);

        if (caller.role != Role.KEY_USER
                || !caller.identity.equals(key.approvedSigner)
                || !"INVOICE_SIGNATURE".equals(key.purpose)
                || key.state != KeyState.ACTIVE
                || !clock.instant().isBefore(key.newUseUntil)) {
            throw new SecurityException("SIGN not authorized");
        }
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2030-03-01T12:00:00Z"), ZoneOffset.UTC);
        KeyRecord key = new KeyRecord(
                "billing-signing-v2", "INVOICE_SIGNATURE",
                "billing-invoice-signer", KeyState.ACTIVE,
                Instant.parse("2031-01-01T00:00:00Z"));
        Actor custodian = new Actor("kms-admin-a", Role.KEY_CUSTODIAN);
        Actor owner = new Actor("billing-key-owner", Role.KEY_OWNER);
        Actor signer = new Actor("billing-invoice-signer", Role.KEY_USER);

        Approval rotateApproval = new Approval(
                key.keyId, Action.ROTATE, custodian.identity,
                owner, Instant.parse("2030-03-02T00:00:00Z"));

        requireRotationAuthorization(
                custodian, key, rotateApproval, clock);
        System.out.println("Custodian rotation: approved");

        requireInvoiceSignAuthorization(signer, key, clock);
        System.out.println("Workload SIGN: allowed");

        try {
            requireInvoiceSignAuthorization(custodian, key, clock);
            throw new AssertionError("Custodian must not SIGN by default");
        } catch (SecurityException expected) {
            System.out.println("Custodian SIGN: denied");
        }

        try {
            requireRotationAuthorization(
                    signer, key, rotateApproval, clock);
            throw new AssertionError("Signer must not ROTATE");
        } catch (SecurityException expected) {
            System.out.println("Workload ROTATE: denied");
        }
    }
}
~~~

**Kết quả dự kiến:**

~~~text
Custodian rotation: approved
Workload SIGN: allowed
Custodian SIGN: denied
Workload ROTATE: denied
~~~

### Những gì ví dụ minh họa đúng

- Custodian chỉ thực thi **rotation có phê duyệt**, không tự quyết định purpose.
- Workload có quyền **ký hóa đơn**, không có quyền quản trị vòng đời.
- Phê duyệt phải gắn **đúng key ID, action, người yêu cầu và thời hạn**.
- Khóa `COMPROMISED` không được đem qua workflow rotation thường mà cần xử lý sự cố.

### Những điều phải bổ sung trước production

1. **Nguồn identity và approval đáng tin**, xác thực mạnh/MFA, chữ ký hoặc cơ chế chống giả mạo quyết định; không nhận `Actor(Role.KEY_OWNER)` do caller tự tạo.
2. **Policy của KMS/HSM** chặn trực tiếp quyền `Sign` của custodian và quyền admin của workload; kiểm tra khả năng một admin tự cấp grant.
3. **Purpose, tenant, environment, cryptoperiod**, trạng thái provider và key material version phải được xác minh với nguồn thực.
4. **State machine nhất quán**: revision, idempotency, kiểm soát TOCTOU giữa approval và áp dụng policy.
5. **Quy trình key replacement**: tạo key mới, preflight, cutover, di chuyển dữ liệu/chứng thư và legacy access; hàm `requireRotationAuthorization` **không thực hiện rotation**.
6. **Chặn sử dụng ngoài dữ liệu được phê duyệt**: một key user có quyền `Sign` vẫn cần business authorization trên nội dung hóa đơn.
7. **Log và monitoring**: approval ID, key ID, principal, operation, result, policy version, không ghi key material.
8. **Break-glass và incident response** có chính sách độc lập, không được tự bypass bằng cách dùng cùng một role.

## 17. Case study: Signing key hóa đơn và custodian trong quy trình thực tế

Một doanh nghiệp sử dụng `billing-invoice-signer` để ký hóa đơn bằng private key `billing-signing-v1` nằm trong HSM. Đơn vị muốn đổi sang `billing-signing-v2`.

### Phân công

- **Key owner (Billing):** phê duyệt việc thay khóa, các đối tượng ký, cryptoperiod, thời điểm cutover.
- **Key custodian (Platform Security):** tạo key v2 trong HSM, cấu hình quyền, đăng ký key inventory, kiểm thử an toàn và vận hành cutover.
- **PKI/Trust team:** phát hành/phân phối chứng thư hoặc public verification key phù hợp.
- **Application owner:** triển khai chọn key version, kiểm tra quy trình phê duyệt hóa đơn và xử lý ký lỗi.
- **Security reviewer:** rà soát separation of duties, thuật toán, HSM controls và kế hoạch rollback.
- **Auditor:** đối chiếu quyết định, nhật ký sự kiện và kết quả rollout.

### Luồng triển khai

~~~mermaid
sequenceDiagram
    participant Owner as Billing key owner
    participant Cust as Key custodian
    participant HSM as HSM
    participant App as Invoice signer
    participant Ver as Invoice verifier
    participant Audit as Auditor
    Owner->>Cust: Phê duyệt rotation và purpose v2
    Cust->>HSM: Sinh signing-v2, non-exportable nếu được hỗ trợ
    HSM-->>Cust: Key ID + public key
    Cust->>Ver: Phân phối metadata/certificate v2
    Ver-->>Cust: Sẵn sàng xác minh key v2
    Cust->>HSM: Áp dụng policy, negative tests
    Cust->>Owner: Báo cáo preflight và yêu cầu activation
    Owner-->>Cust: Phê duyệt cutover
    Cust->>App: Cập nhật routing sang key v2 qua control plane
    App->>HSM: Sign với workload identity đã được duyệt
    HSM-->>App: Chữ ký bằng key v2
    Cust->>HSM: Ngừng Sign mới bằng v1 theo policy
    Cust->>Audit: Kết quả cutover + key inventory + log
    Note over Ver: Tiếp tục kiểm tra chữ ký v1 lịch sử khi được phép
~~~

### Hai lỗi cần phòng tránh

**Lỗi 1 — Cấp custodian quyền `Sign` để kiểm tra.** Nhóm vận hành có thể vô tình trở thành người ký thay cho nghiệp vụ. Cách phòng tránh là dùng phép kiểm tra bằng nguồn test được phê duyệt, hoặc chức năng kiểm tra tích hợp có cơ chế audit/giới hạn đúng, không mở `Sign` production vô điều kiện.

**Lỗi 2 — Xóa khóa v1 ngay sau khi chuyển.** Khóa v1 có thể không còn được dùng ký mới, nhưng các chữ ký lịch sử còn cần public key/chứng thư/bằng chứng và ứng dụng vẫn có thể có tài liệu đang xử lý. Phải **kiểm kê phụ thuộc** và áp dụng retention trước khi hủy private key.

## 18. Case study: Custodian xử lý sự cố KEK có grant quá rộng

Giả sử một service account của ứng dụng test bất ngờ có quyền `Unwrap` với **KEK production** dùng bọc DEK của nhiều khách hàng. Đây có thể là lỗi IAM hoặc dấu hiệu lạm dụng đặc quyền.

### Bước xử lý phù hợp

1. **Phát hiện và ghi nhận:** KMS audit cho thấy test identity gọi `Unwrap` trên `billing-kek-v3`.
2. **Cô lập:** Nhóm ứng cứu/custodian thu hồi grant hoặc suspend key theo phạm vi và thẩm quyền, đồng thời xem xét các principal liên quan.
3. **Đánh giá tác động:** Xác định có raw DEK được trả về hay không, khách hàng nào phụ thuộc và có plaintext DEK trong cache.
4. **Giữ availability khi hợp lý:** Nếu rủi ro chỉ ở một grant, việc thu hồi grant có thể giảm tác động hơn disable toàn bộ KEK; quyết định dựa vào mức độ khẩn cấp.
5. **Điều tra:** Đối chiếu owner approval với policy thực, ai thay IAM, dữ liệu nào được unwrap.
6. **Thay khóa khi cần:** Nếu KEK/DEK đã lộ, xác định trường hợp phải rewrap hay re-encrypt; không đánh đồng hai thao tác.
7. **Khôi phục và phê duyệt:** Chỉ mở lại đúng quyền sau kiểm tra; ghi âm bản policy/approval, negative test và log.
8. **Rút kinh nghiệm:** Thêm cảnh báo cấp quyền trái environment, giới hạn cấp grant, kiểm tra self-escalation và lịch đối soát.

### Vì sao không chỉ rotate KEK là đủ?

Nếu kẻ tấn công đã nhận được **DEK plaintext** từ một lệnh `Unwrap`, thì bọc lại DEK đó bằng KEK mới không ngăn họ sử dụng bản sao DEK. Cần đánh giá dữ liệu/ciphertext lịch sử và **thay DEK, mã hóa lại** khi cần, đồng thời thực hiện điều tra và các nghĩa vụ ứng cứu phù hợp.

### Vì sao không chỉ disable KEK là đủ?

Ứng dụng có thể còn DEK plaintext trong RAM/cache và tiếp tục giải mã **không gọi KMS**. Một số dịch vụ khác có thể không đọc được dữ liệu vì cần unwrap mới. Custodian phải kết hợp control plane, IAM, cache containment và phối hợp application owner thay vì coi một thao tác disable là hoàn tất.

## 19. Những sai lầm thường gặp về vai trò Key custodian

| Sai lầm | Hậu quả | Biện pháp |
| --- | --- | --- |
| Gọi custodian là owner rồi tự phê duyệt purpose | Thiếu trách nhiệm nghiệp vụ và kiểm soát độc lập | RACI, owner approval, giới hạn quyền |
| Trao custodian quyền `Sign/Decrypt` không cần thiết | Có thể ký/giải mã ngoài mục đích | Tách admin và usage IAM |
| Admin không có `Decrypt` nhưng được tự sửa policy để cấp quyền | Leo thang đặc quyền gián tiếp | Kiểm soát grant/policy change, dual control |
| Ghi private key vào inventory để “kiểm kê đầy đủ” | Lộ bí mật và mở rộng bề mặt tấn công | Chỉ lưu key ID/handle/metadata |
| Sinh khóa bằng PRNG yếu rồi nhập vào HSM | Key material vẫn dễ đoán | Tạo từ CSPRNG/DRBG tin cậy |
| Dùng cùng key cho signing và key agreement | Trộn purpose và blast radius | Tách key usage/material theo thiết kế |
| Coi HSM non-exportable bảo đảm không thể lạm dụng | Signing oracle vẫn có thể tồn tại | Business approval, IAM và audit |
| Coi KMS `Enabled` là được owner phê duyệt | Dùng key trước activation hoặc sai purpose | Lifecycle policy gate + provider enforcement |
| Tin `DisableKey` sẽ xóa mọi bản sao DEK | Cached DEK vẫn có thể hoạt động | Cache/session containment |
| Hủy KEK ngay khi tạo KEK mới | Không unwrap được DEK/backup cũ | Rewrap, dependency và retention checks |
| Chỉ rewrap khi DEK đã lộ | Ciphertext cũ vẫn có thể bị giải mã | Re-encrypt và đánh giá tác động dữ liệu |
| Không lưu chứng thư/public key của signing key cũ | Không verify được chữ ký lịch sử | Retention bằng chứng xác minh |
| Cho một người tạo, duyệt và hủy key không giám sát | Dễ lạm dụng và khó điều tra | Dual control/separation khi rủi ro yêu cầu |
| Tự chia key bằng cách cắt byte thành nhiều phần | Không tạo split knowledge an toàn | Cơ chế threshold/sharing chuẩn được đánh giá |
| Nhận approval dạng chuỗi từ client | Có thể giả vai trò và mở quyền | Source of truth đáng tin, ký/kiểm chứng quyết định |
| Chỉ kiểm tra API KMS, không kiểm tra workflow nghiệp vụ | Có thể ký/giải mã nội dung không được phép | Policy gate ở cả application và provider |
| Không thử restore backup | Kế hoạch phục hồi có thể không hoạt động | DR drill với dữ liệu/khóa được phép |
| Bỏ qua alias/key version khi xoay | Sai key được dùng, khó đọc dữ liệu cũ | Inventory và cutover audit theo version |
| Xóa audit sau sự cố để giảm log | Mất bằng chứng và không còn truy nguyên | Retention và bảo vệ tính toàn vẹn audit |
| Không có runbook khi owner/custodian nghỉ việc | Không ai phê duyệt hoặc quản trị key | Chuyển giao trách nhiệm, quyền và inventory |

## 20. Checklist cho đội vận hành Key custodian

Trước khi nhận trách nhiệm custodianship hoặc rà soát một hệ thống quản lý khóa, cần kiểm tra:

1. **Phân công:** Có key owner, custodian, key user, security reviewer và auditor rõ ràng? Người thực thi có được ủy quyền bằng chính sách?
2. **Purpose:** Mỗi key có mục đích, data domain, tenant, environment, approved operations và cryptoperiod?
3. **Key inventory:** Có key ID/version, provider resource, algorithm, location, backup, dependency và approval references mà không chứa secret?
4. **Nguồn tạo:** CSPRNG/DRBG, loại key và chính sách import/export có được đánh giá?
5. **HSM/KMS:** Cấu hình module, key type, key policy, trạng thái, grant và khả năng DR có được hiểu đúng semantics của sản phẩm?
6. **Separation of duties:** Role admin có thể tự cấp `Sign/Decrypt/Unwrap` không? Những thao tác rủi ro cao có approval/dual control độc lập?
7. **Credential bảo vệ quyền quản trị:** MFA hoặc thiết bị xác thực mạnh, least privilege, quyền tạm thời, giới hạn break-glass?
8. **Pre-activation:** Đã thử chặn new-use trước phê duyệt ở provider, không chỉ kiểm tra database flag?
9. **Production use:** Workload có quyền trên đúng key/version, purpose, tenant, environment và operation; application có business approval?
10. **Đối xứng:** Với AES-GCM, có nonce không lặp, tag/AAD đúng, DEK/KEK tách biệt và inventory dữ liệu phụ thuộc?
11. **Bất đối xứng:** Với RSA/ECC signing key, có phân phối public key/chứng thư, đúng usage và khả năng verify lâu dài?
12. **HMAC/ECDH:** Shared secret được phân phối đúng đối tác; agreement key có peer authentication và KDF phù hợp?
13. **Rotation:** Có lịch/trigger theo rủi ro, preflight, cutover, rewrap/re-encrypt, rollback và giữ legacy operation tối thiểu?
14. **Backup/DR:** Có kiểm thử phục hồi, cơ chế provider phù hợp và phân quyền với recovery key không?
15. **Suspend:** Có cô lập nhanh principal/grant/key, kiểm tra cache, session và in-flight operation?
16. **Compromise:** Có quy trình phân biệt IAM credential lộ, KEK lộ, DEK lộ, private signing key lộ và ảnh hưởng dữ liệu lịch sử?
17. **Destroy:** Có phê duyệt, xác minh không còn wrapped DEK/backup phụ thuộc, log xóa và điều kiện retention?
18. **Audit:** Có log identity, operation, policy change, key ID/version, result và approval mà không lộ key material?
19. **Giám sát:** Có cảnh báo grant bất thường, dùng key ngoài cryptoperiod, new-use khi suspended, key thiếu owner/custodian?
20. **Thay đổi nhân sự:** Có quy trình thu hồi quyền của custodian cũ, chuyển giao HSM role, khóa hardware token và cập nhật RACI?
21. **Kiểm thử âm tính:** Có chứng minh workload không gọi được admin API và custodian không được dùng API ký/giải mã ngoài quyền?
22. **Đánh giá định kỳ:** Owner và custodian có cùng rà soát purpose, quyền, trạng thái, DR và các phụ thuộc trước khi kết luận key an toàn?

### Ghi nhớ

**Key custodian** là người hoặc nhóm **được giao bảo quản và vận hành kỹ thuật khóa mật mã**, bảo đảm key material và các quyền sử dụng được kiểm soát đúng chính sách. **Key owner quyết định mục đích và rủi ro**, **key user thực hiện phép toán nghiệp vụ**, còn **auditor/security reviewer** kiểm tra sự phù hợp và bằng chứng. Custodian cần hiểu **vòng đời khóa, KMS/HSM, IAM, entropy, key inventory, rotation, backup/restore, suspend, compromise và destroy**, đồng thời phối hợp với ứng dụng xử lý **DEK/KEK, chữ ký số, HMAC, ECDH và recovery key**. Vai trò này có giá trị nhất khi quyền quản trị **không mặc nhiên trở thành quyền `Sign`, `Decrypt`, `Unwrap`**, khi việc phê duyệt và thực thi được tách phù hợp với rủi ro, và khi mỗi quyết định đều **kiểm chứng được qua audit**. Bảo vệ khóa không chỉ là bảo vệ file chứa secret: đó là vận hành **toàn bộ hệ thống kiểm soát quanh khóa** một cách có trách nhiệm.
