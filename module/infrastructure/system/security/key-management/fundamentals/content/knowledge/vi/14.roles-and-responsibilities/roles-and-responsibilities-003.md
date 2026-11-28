# Security administrator: Vai trò quản trị an ninh trong quản lý khóa mật mã

Một nền tảng thương mại điện tử có ba nhóm hệ thống: **Billing Service** ký hóa đơn, **Customer Data Service** mã hóa hồ sơ bằng AES-GCM và **Identity Service** ký access token. Các khóa được quản lý trong KMS/HSM. Khi đội phát triển cần cấp quyền cho một service mới, khi khóa đến hạn xoay vòng hoặc khi phát hiện credential bị lộ, **ai được thay đổi chính sách truy cập và trạng thái khóa?** Người đó có nên mặc nhiên được xuất private key, giải mã mọi hồ sơ hoặc ký hóa đơn thay Billing Service không?

**Security administrator (người quản trị an ninh)** là vai trò chịu trách nhiệm **thiết lập, thực thi hoặc quản trị các chính sách bảo vệ hệ thống mật mã** trong phạm vi được giao: kiểm soát quyền, ranh giới tin cậy, cấu hình bảo vệ khóa, quy trình phê duyệt, giám sát và phản ứng sự cố. Trong thiết kế tốt, **quyền quản trị chính sách không tự động đồng nghĩa quyền sử dụng hoặc biết key material**. Một người có thể được phép đình chỉ khóa bị nghi lộ nhưng không được gọi **Decrypt** để đọc dữ liệu khách hàng; một workload có thể được phép **Sign** nhưng không được sửa chính sách để tự nâng quyền.

Trong chương **Vai trò và trách nhiệm** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài này liên hệ vai trò Security administrator với vòng đời khóa **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**, đồng thời kết nối mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, quyền truy cập và kiểm toán. Chức danh có thể khác nhau giữa các tổ chức và nhà cung cấp; điều quan trọng là **quyền hạn, trách nhiệm, giới hạn và điểm thực thi kiểm soát** phải được xác định tường minh.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **Security administrator** làm gì và không được mặc nhiên làm gì trong hệ thống key management.
2. Phân biệt **Security administrator**, **Key owner**, **Key custodian**, **KMS/HSM operator**, **Crypto user/workload**, **Auditor** và **Incident responder**.
3. Xây dựng **RACI** và **separation of duties** cho các thao tác Create, Grant, Revoke, Sign, Decrypt, Rotate, Disable, Backup và Destroy.
4. Thiết kế chính sách **least privilege**, **deny by default**, **dual control/four-eyes** và **break-glass** có thời hạn.
5. Liên kết kiểm soát của quản trị viên với **key identifier/version, purpose, tenant, environment, cryptoperiod và lifecycle state**.
6. Lập runbook cấp quyền, xoay vòng, khôi phục và phản ứng sự cố có **audit trail** và chứng cứ thực thi.
7. Hiểu ví dụ Java 17 kiểm tra **vai trò, phạm vi, tách nhiệm vụ và quyền crypto** mà không nhầm mã demo với KMS policy thực tế.

## 2. Trách nhiệm cốt lõi của Security administrator

Trước hết cần phân biệt hai nhóm hoạt động:

- **Control plane:** tạo/chỉnh quy tắc truy cập, quản lý chính sách, cấu hình ranh giới, duyệt thay đổi, tạm khóa hoặc lên kế hoạch xoay vòng.
- **Data plane:** thực sự dùng khóa để **Encrypt, Decrypt, Sign, Verify, GenerateMac, Wrap, Unwrap, DeriveKey**.

Security administrator chủ yếu thực hiện hoặc kiểm soát **control-plane operations**. Việc có quyền control plane rộng không tự cho phép bypass kiểm tra ở data plane, cũng không tự bảo vệ được khóa nếu người quản trị có thể **tạo quyền Decrypt cho chính mình** mà không có phê duyệt độc lập.

~~~mermaid
flowchart TD
    SA["Security administrator"] --> CP["Control plane: policy, role, lifecycle, review"]
    KO["Key owner"] --> AP["Phê duyệt mục đích và phạm vi nghiệp vụ"]
    AP --> CP
    CP --> IAM["IAM/key policy và KMS/HSM attributes"]
    W["Authenticated workload"] --> DP["Data plane: Encrypt / Decrypt / Sign"]
    IAM --> DP
    DP --> K["KMS/HSM hoặc crypto service thực thi"]
    CP --> AUD["Audit events"]
    DP --> AUD
    AU["Independent auditor"] --> AUD
~~~

### 2.1. Những việc điển hình thuộc trách nhiệm của Security administrator

| Nhóm trách nhiệm | Công việc cụ thể | Bằng chứng cần có |
|---|---|---|
| **Chính sách mật mã** | Định nghĩa thuật toán, key size/curve, purpose, exportability, nơi lưu, cryptoperiod | Policy ID/version, phê duyệt, ngày hiệu lực |
| **IAM và phân quyền** | Cấp/thu hồi quyền theo principal, key ID/version, tenant, action | Grant/revoke request, actor, approver, scope |
| **Key storage controls** | Yêu cầu KMS/HSM, non-exportable khi cần, key wrapping và phân tách môi trường | Provider/config/attributes, kết quả kiểm thử |
| **Phân tách nhiệm vụ** | Chặn một người vừa thay policy vừa tự dùng/duyệt quyền nguy hiểm | RACI, role bindings, SoD check |
| **Lifecycle controls** | Điều phối Activate, Suspend, Rotate, Retire, Destroy theo policy | State transition, reason, effective time |
| **Audit và monitoring** | Bảo đảm ghi log đủ metadata, cảnh báo thao tác bất thường | Audit trail, alert, review report |
| **Quản trị sự cố** | Khẩn cấp chặn lạm dụng, khoanh vùng key/credential, hỗ trợ rotate/revoke | Incident ID, timeline, quyết định và hành động |
| **Compliance và kiến trúc** | Kiểm tra thiết kế với security baseline và yêu cầu tổ chức | Design review, risk acceptance, test evidence |
| **Khả năng phục hồi** | Yêu cầu backup/restore, key continuity, quản trị quyền khôi phục | Restore drill, dependency inventory, approval |

**Security administrator không nhất thiết trực tiếp chạy mọi lệnh trong bảng.** Ở nhiều tổ chức, người quản trị an ninh **định nghĩa/duyệt policy**, còn **KMS platform operator** thực hiện thay đổi hạ tầng theo ticket và một người khác kiểm tra kết quả. Vai trò chính xác là quyết định tổ chức, không chỉ là tên trên giao diện.

### 2.2. Những quyền không nên cấp mặc định

- **Export raw KEK, root key hoặc private signing key:** mở rộng phạm vi lộ key material; ưu tiên non-exportable phù hợp.
- **Decrypt toàn bộ dữ liệu khách hàng:** quyền quản trị IAM không có nghĩa có nhu cầu đọc plaintext.
- **Sign hóa đơn/tài liệu tùy ý:** phải có kiểm tra nghiệp vụ và workload identity riêng; tránh biến quyền quản trị thành *signing oracle*.
- **Tự cấp quyền CryptoUse rồi tự phê duyệt:** phá **separation of duties**.
- **Vừa quản trị vừa xóa/sửa audit trail của chính mình:** mất khả năng điều tra độc lập.
- **Destroy key production mà không có dependency review:** có thể làm mất dữ liệu dài hạn.
- **Dùng credential hoặc root secret chung giữa test và production:** làm sụp ranh giới bảo vệ.

Không nên diễn giải thành “Security administrator không bao giờ có quyền data plane” trong mọi sản phẩm. Một số cơ chế recovery hoặc tổ chức nhỏ có thể yêu cầu quyền đặc biệt. Khi đó phải có **ngoại lệ minh bạch, scope hẹp, approval độc lập, thời hạn, giám sát và thu hồi sau sử dụng**.

## 3. Phân biệt vai trò: Ai sở hữu khóa và ai được dùng?

Các tên bên dưới là **mô hình tổ chức tham khảo**, không phải bộ role chuẩn áp dụng cho mọi KMS/HSM.

| Vai trò | Trách nhiệm chính | Không nên mặc định có quyền |
|---|---|---|
| **Security administrator** | Security policy, IAM guardrails, thay đổi và sự cố | Decrypt/Sign/Export raw key vì là admin |
| **Key owner / business owner** | Quyết định mục đích, phân loại, chủ dữ liệu, nhu cầu truy cập và retention | Thực hiện thao tác HSM, tự thay security baseline |
| **Key custodian** | Chịu trách nhiệm giữ, phân phối hoặc vận hành bảo quản material theo mô hình tổ chức | Toàn quyền đọc dữ liệu nghiệp vụ của owner |
| **KMS/HSM platform operator** | Vận hành HSM partition, availability, provider configuration và maintenance | Đọc raw private key hoặc tự cấp quyền sử dụng tùy ý |
| **Cryptographic user / workload** | Gọi Encrypt/Decrypt/Sign/Unwrap theo service identity và scope | ChangePolicy, Export, Destroy, grant self |
| **Developer/application owner** | Triển khai client, thuật toán, error handling, key references và testing | Nhận production secret trong source code hoặc debug |
| **Independent auditor** | Đối soát key inventory, audit events, policy và evidence | Ký hoặc giải mã bằng key production |
| **Incident responder** | Điều tra, cô lập, hạn chế quyền và thực hiện runbook khẩn cấp | Không giới hạn thời gian với break-glass permissions |
| **Recovery/backup custodian** | Duy trì backup/restore theo security domain và phê duyệt | Export raw material hoặc khôi phục ngoài môi trường được duyệt |

**Người giữ khóa (custodian)** và **người quyết định mục đích khóa (owner)** có thể là hai người khác nhau. Một ứng dụng có thể là **principal** thực hiện phép toán, còn Key owner là một nhóm chịu trách nhiệm nghiệp vụ. Chính sách phải mô tả cả **human roles** và **machine identities**, thay vì dùng cùng một tài khoản admin cho mọi thao tác.

### 3.1. Ví dụ separation of duties

Một thay đổi cấp quyền **Unwrap** cho Customer Data Service có thể cần:

1. **Application owner** tạo request, chỉ rõ tenant, key family, operation và lý do.
2. **Key owner** xác nhận dữ liệu và phạm vi nghiệp vụ thuộc quyền service.
3. **Security administrator** kiểm tra rule least privilege, key state, environment, thời hạn và xung đột SoD.
4. **KMS operator** hoặc hệ thống tự động được cấp quyền triển khai thay đổi được phê duyệt.
5. **Independent auditor** truy vết record về quyết định và kiểm tra quyền thực thi thực tế.

**Không giao mọi bước cho một tài khoản “super-admin”** chỉ để quy trình nhanh. Nếu một người có đủ quyền phê duyệt cho chính mình, sửa policy và che audit, việc KMS lưu khóa non-exportable vẫn không chặn được lạm dụng **Decrypt/Sign API**.

## 4. Ma trận RACI cho các thao tác quản lý khóa

**R (Responsible)** là người thực hiện; **A (Accountable)** chịu trách nhiệm quyết định cuối; **C (Consulted)** được tham vấn; **I (Informed)** được thông báo. RACI bên dưới là **ví dụ thiết kế** phải điều chỉnh theo quy mô tổ chức, điều kiện provider và policy.

Viết tắt: **SA** = Security administrator; **KO** = Key owner; **OP** = KMS/HSM operator; **WU** = Workload owner/crypto user; **AU** = Auditor; **IR** = Incident responder.

| Hoạt động | SA | KO | OP | WU | AU | IR |
|---|---|---|---|---|---|---|
| Ban hành baseline storage/algorithm/IAM | **A/R** | C | C | C | C | I |
| Đề nghị khóa mới theo purpose | C | **A** | R | R | I | I |
| Provision key và policy sau duyệt | **A** | C | **R** | I | I | I |
| Cấp quyền Encrypt/Sign/Unwrap | **R** | **A** | C | C | I | I |
| Chạy Encrypt/Decrypt/Sign nghiệp vụ | I | **A** | I | **R** | I | I |
| Review IAM, grants và key usage | **A/R** | C | C | C | C | I |
| Rotate theo kế hoạch | **A** | C | **R** | R | I | I |
| Emergency suspend/revoke credential | **A** | C | R | I | I | **R** |
| Quyết định migrate/re-encrypt dữ liệu | C | **A** | C | **R** | I | C |
| Hủy key material sau dependency review | **A** | C | **R** | C | I | C |
| Audit độc lập và kiểm tra evidence | C | I | I | I | **A/R** | C |

**Giới hạn của RACI:** ký hiệu “A” trong bảng không tự trao quyền kỹ thuật. Một **approval chain** có thể cần thêm Legal, Compliance, Privacy hoặc hai người phê duyệt cho hoạt động nhạy cảm. Tổ chức phải ánh xạ bảng này thành **role assignments, IAM bindings, provider controls, ticket workflow và audit log**.

### 4.1. Dual control và split knowledge

Hai khái niệm dễ nhầm:

- **Dual control (two-person/four-eyes):** một hành động nhạy cảm chỉ hoàn tất khi có **ít nhất hai chủ thể độc lập** tham gia/phê duyệt theo chính sách.
- **Split knowledge:** không một người riêng lẻ có đủ thông tin để tái tạo một secret được chia theo cơ chế được thiết kế an toàn.

Dual control của một thao tác **DestroyKey** không tự bảo đảm key material được chia secret. Split knowledge cũng không tự bảo đảm IAM của API **Decrypt** được phân tách. Nếu cần threshold cryptography hoặc secret sharing, dùng **cơ chế được kiểm chứng**, không tự cắt KEK làm hai chuỗi rồi coi an toàn.

## 5. Chính sách quyền truy cập: Vai trò, hành động, đối tượng và ngữ cảnh

Một rule quyền sử dụng khóa nên được biểu diễn như một quyết định dựa trên các chiều:

~~~text
Decision = Authorize(
    authenticatedPrincipal,
    principalRoles,
    operation,
    keyId + keyVersion,
    keyType + keyPurpose,
    keyLifecycleState,
    tenant + resource + environment,
    policyVersion + approval + time
)
~~~

Hệ thống chỉ nên cho phép khi **mọi điều kiện cần thiết đều thỏa**. Một principal là Security administrator không mặc nhiên được Sign hoặc Decrypt chỉ vì có role quản trị.

### 5.1. Ví dụ phân chia quyền

| Action | Security admin | Billing Service | Customer Service | Auditor |
|---|---|---|---|---|
| **Read key metadata/state** | Theo scope quản trị | Chỉ key mình dùng | Chỉ key mình dùng | Read-only có kiểm soát |
| **Manage key policy/grants** | Theo workflow có approval | **Deny** | **Deny** | **Deny** |
| **Sign với billing private key** | **Deny mặc định** | **Allow** theo purpose và business check | Deny | Deny |
| **Decrypt/Unwrap customer DEK** | **Deny mặc định** | Deny | **Allow** theo tenant/record | Deny |
| **Export raw private key/KEK** | **Deny mặc định** | Deny | Deny | Deny |
| **Suspend key** | Allow theo quyền và lý do | Deny | Deny | Deny |
| **Destroy key** | Chỉ theo approval/dual control | Deny | Deny | Deny |
| **Read audit events** | Theo chức năng | Giới hạn dịch vụ | Giới hạn dịch vụ | **Read-only** theo scope |

Phân quyền phải được thực thi ở **KMS/HSM/key service** và các bước nghiệp vụ, không chỉ ở một màn hình quản trị. **Key policy** và **IAM role** có thể cùng tác động: nếu một lớp cấp quyền rộng quá mức hoặc có đường bypass, phải đánh giá khả năng vượt qua toàn bộ điều kiện.

### 5.2. Least privilege theo thời gian và phạm vi

- **Principal:** workload identity riêng, không dùng chung tài khoản admin hoặc credentials dài hạn nếu có thể.
- **Key scope:** key ID/version, provider account/partition, tenant và environment rõ ràng.
- **Operation:** chỉ cho Sign, Decrypt, Wrap, Unwrap hoặc DeriveKey thực sự cần.
- **Purpose:** không dùng private signing key cho giải mã chỉ vì key type hỗ trợ một cơ chế khác.
- **Resource context:** kiểm tra quyền của caller đối với bản ghi/tenant trước khi gọi KMS.
- **TTL:** quyền tạm thời hết hạn, có thu hồi và không tự gia hạn khi thiếu review.
- **Monitoring:** ghi audit mọi lần cấp quyền và những phép toán nhạy cảm, phát hiện bất thường.

Nếu một API nhận **keyId** từ request, keyId chỉ là metadata lookup, **không phải một bearer credential**. Admin phải bảo đảm hệ thống không trở thành *confused deputy*: service có quyền KMS rộng bị dùng để giải mã dữ liệu thuộc tenant khác.

### 5.3. Mô hình chính sách minh họa

~~~yaml
policyId: key-admin-governance-v1
environment: production
defaultDecision: DENY
rules:
  - subjectRole: SECURITY_ADMINISTRATOR
    actions: [READ_KEY_METADATA, PROPOSE_POLICY, SUSPEND_KEY]
    keyScope: approved-application-keys
    rawKeyExport: DENY
    cryptographicUse: DENY
  - subjectRole: BILLING_WORKLOAD
    actions: [SIGN]
    keyPurpose: BILLING_SIGNATURE
    tenantIsolation: REQUIRED
    keyState: ACTIVE
  - subjectRole: CUSTOMER_DATA_WORKLOAD
    actions: [UNWRAP]
    keyPurpose: DATA_KEY_PROTECTION
    tenantIsolation: REQUIRED
    keyState: ACTIVE
  - subjectRole: INDEPENDENT_AUDITOR
    actions: [READ_AUDIT, READ_KEY_METADATA]
    cryptographicUse: DENY
highRiskChanges:
  actions: [GRANT_UNWRAP, ENABLE_KEY_EXPORT, DESTROY_KEY]
  independentApproval: REQUIRED
  ticketAndReason: REQUIRED
  immutableAuditRecord: REQUIRED
breakGlass:
  scope: LIMITED
  expiry: REQUIRED
  postUseReview: REQUIRED
~~~

Đây là **pseudo-policy phục vụ bài học**, **không phải cú pháp cấu hình AWS KMS, Azure Key Vault, Google Cloud KMS hay PKCS#11**. Một công cụ cấu hình sản phẩm thực có thể dùng vai trò, condition, policy document, permission boundary và grant khác nhau. Trước khi triển khai, cần chứng minh các rule đã được **ánh xạ đúng** sang enforcement points.

## 6. Vai trò của Security administrator trong từng giai đoạn vòng đời khóa

Một khóa không chỉ có trạng thái Active. Việc tạo mới, sử dụng trong cryptoperiod, tạm đình chỉ, xoay vòng, phục hồi và hủy đều có quyết định bảo mật riêng. Security administrator giúp định nghĩa **điều kiện cho mỗi chuyển trạng thái**.

~~~mermaid
flowchart TD
    A["Request key: owner, purpose, risk tier"] --> B["Security review: algorithm, storage, IAM"]
    B --> C["Generate/Import trong provider được phê duyệt"]
    C --> D["Register key ID, version, state, dependencies"]
    D --> E["Approve + Activate"]
    E --> F["Use trong cryptoperiod với audit"]
    F --> G{"Rotation hoặc cảnh báo an ninh?"}
    G -->|"Định kỳ"| H["Rotate key / update active reference"]
    G -->|"Nghi sự cố"| S["Suspend + incident review"]
    H --> I["Migrate/Rewrap/Re-encrypt khi cần"]
    S --> J{"Key compromised?"}
    J -->|"Không, sau kiểm tra"| E
    J -->|"Có hoặc không thể tin cậy"| I
    I --> K["Retire theo dependency/retention"]
    K --> L["Approve destruction và kiểm tra backup"]
    L --> M["Destroy + giữ audit/tombstone"]
~~~

Sơ đồ là một **mô hình quản trị minh họa**. Không phải mọi KMS hỗ trợ đủ mọi state hay cho chuyển trạng thái theo thứ tự trên. Khi một khóa **đã được xác nhận compromised**, việc quay về Active không phải nhánh khôi phục thông thường; cần **thay key material**, xét revoke và dữ liệu lịch sử.

### 6.1. Key generation: Tạo khóa đúng chuẩn và đúng ranh giới

Security administrator cần kiểm tra:

1. **Mục đích:** AES-256-GCM cho data encryption, HMAC key cho MAC, Ed25519/ECDSA/RSA-PSS cho ký, KEK cho wrapping. Không cho “một khóa làm tất cả” chỉ để giảm số lượng key.
2. **Nguồn entropy:** CSPRNG/provider được chấp thuận, tham số sinh khóa đủ mạnh. Một ID ngẫu nhiên không thay thế nguồn entropy của chính key material.
3. **Nơi tạo:** KMS/HSM nếu policy yêu cầu non-exportable; quy trình import có phê duyệt và bảo vệ material nếu tạo ngoài.
4. **Thuộc tính:** key ID/version, algorithm, allowed usage, owner, tenant, environment, exportability, cryptoperiod.
5. **Tính tách biệt:** staging/prod, khách hàng/tenant, service và key purpose có ranh giới rõ.
6. **Bằng chứng:** creation event, người đề nghị, người duyệt, provider/key handle và kết quả kiểm tra.

**Không nên để một người vừa tạo private key, tự đánh dấu non-exportable trên giấy, rồi giữ bản sao raw key ngoài KMS**. Khi private key đã sinh ngoài ranh giới tin cậy, cần kiểm tra đường đi và bản sao ngoài hệ thống trước khi tuyên bố non-exportable.

### 6.2. Provisioning: Cấp quyền và phân phối key reference

Khóa được tạo nhưng chưa chắc được phép dùng. Giai đoạn provisioning cần:

- Xác thực **workload identity** và owner của workload.
- Phê duyệt **key scope, purpose, tenant và operation** theo hợp đồng.
- Cấp **key reference/handle** thay vì gửi raw KEK/private key nếu không cần thiết.
- Đảm bảo metadata/trust anchor/JWKS được phát hành qua nguồn đáng tin.
- Tách permission **ManagePolicy** khỏi **Sign/Decrypt** và khỏi **ReadAudit/DeleteAudit**.
- Kiểm tra bằng **negative tests**: service có quyền Sign phải bị từ chối khi gọi Export/Decrypt/Destroy.

Một key alias như **billing-current** có thể giúp chọn version cho thao tác mới. Security administrator phải yêu cầu application lưu **key ID/version thực tế** trong metadata của ciphertext/chữ ký để các thao tác lịch sử không bị ảnh hưởng khi alias chuyển.

### 6.3. Storage: Quyết định ai có thể tiếp cận material

Với **root KEK** và **private signing key**, policy thường ưu tiên **KMS/HSM với export controls**, key attributes phù hợp và backup/restore trong security domain được chấp thuận. Với **plaintext DEK** phục vụ local AES-GCM, phải xác định nơi material xuất hiện trong process memory, cache, log, dump và thời điểm cleanup.

Security administrator nên kiểm tra **đồng thời**:

| Tài sản | Confidentiality controls | Use controls |
|---|---|---|
| Root key/KEK | Không raw export trái policy; storage boundary, secure backup | Chỉ Wrap/Unwrap/Derive theo scope, approval |
| Private signing key | Non-exportable nếu được yêu cầu; không PEM trong Git/image | Chỉ Sign thông điệp đã được nghiệp vụ duyệt |
| HMAC key | Secret store/KMS phù hợp, không log | Chỉ GenerateMac/VerifyMac theo purpose |
| Plaintext DEK | Không lưu cùng ciphertext; TTL ngắn; cache/dump policy | Chỉ Encrypt/Decrypt đúng tenant/record |
| Public verification key | Integrity, origin, issuer/cert trust | Không nhận kid/URL tùy ý từ attacker |
| KDF root/PRK/derived key | Root được cô lập; PRK/OKM ngắn hạn | DeriveKey chỉ cho purpose/tenant được phép |

**Không đồng nhất bảo vệ byte khóa với bảo vệ phép toán.** Một KMS giữ KEK non-exportable vẫn có thể bị lạm dụng khi service role có quyền **Unwrap mọi wrapped DEK**.

### 6.4. Operation: Theo dõi việc dùng khóa hợp lệ

Security administrator cần đảm bảo logging metadata và các giới hạn sử dụng phù hợp:

- **Sign:** principal nào ký, key ID/version nào, purpose, request ID, kết quả policy và nghiệp vụ.
- **Decrypt/Unwrap:** workload và tenant, tập dữ liệu nào được phép, tần suất bất thường và thời hạn quyền.
- **GenerateMac/VerifyMac:** phân biệt tạo MAC với xác minh MAC, chống replay ở tầng giao thức.
- **DeriveKey:** ai có quyền dẫn xuất từ root, scope thông tin **info/context**, có cho caller tự đặt tenant khác không.
- **AES-GCM:** nguyên tắc **nonce duy nhất theo DEK** phải được application/protocol đảm bảo; quản trị viên xét usage limits và key rotation.
- **Public-key Verify:** chính sách về trust store, JWKS issuer, certificate revocation và thời gian chấp nhận key cũ.

Không log plaintext, root key, PRK/OKM, raw DEK, private key hoặc bearer token chỉ để đo việc dùng khóa. Nếu muốn đánh giá bất thường, dùng **metadata có giới hạn**, tokenized references và hệ thống audit có phân quyền.

### 6.5. Rotation: Chính sách xoay vòng theo đúng loại khóa

| Đối tượng | Tác động của rotation | Vai trò Security administrator |
|---|---|---|
| **KEK** | Có thể cần rewrap DEK; ciphertext payload có thể giữ nguyên nếu AAD/schema tương thích | Phê duyệt key mới, grants, migration và thời hạn nghỉ khóa cũ |
| **DEK** | Dữ liệu muốn đổi key cần giải mã/mã hóa lại | Xác định dependency, encryption scope và kiểm soát migration |
| **Private signing key** | Sign mới với version mới; public key cũ có thể còn cần Verify | Kiểm soát JWKS/certificate publication, trust và revoke |
| **HMAC key** | Tag mới dùng key mới; verifier có thể cần chấp nhận tag cũ một thời gian | Xác định grace period và chống replay |
| **KDF root** | Derived keys mới thay đổi; dữ liệu cũ không tự đọc được với root mới | Version hóa KDF/salt/info, thiết kế recovery/migration |

**Rewrap DEK không sửa được một DEK đã bị lộ**. Nếu thay KEK nhưng giữ cùng DEK, dữ liệu vẫn có thể bị giải mã bởi đối thủ sở hữu DEK. Nếu signing private key bị lộ, chặn KMS Sign không vô hiệu hóa bản sao offline; cần xử lý trust và chuỗi chữ ký lịch sử.

### 6.6. Suspension, revocation và destruction

Security administrator thường có quyền **khẩn cấp suspend/disable** theo runbook hoặc đề nghị thực hiện. Nhưng:

- **Suspend** giữ material, tạm chặn theo policy và có thể phục hồi sau điều tra.
- **Revoke** có thể liên quan key usage, certificate trust, token/session hoặc quyền principal; đây không phải một thao tác duy nhất ở mọi hệ thống.
- **Compromised** là tình huống material hoặc quyền sử dụng không còn đáng tin; không chỉ đổi state về Active.
- **Destroy** cần xác minh dependencies, backup, escrow, retention/legal hold, khả năng khôi phục và approval.

Một key **retired** có thể vẫn cần Decrypt dữ liệu cũ hoặc Verify chữ ký; một key **suspended do nghi lộ** có thể bị cấm cả Decrypt. Quy tắc cụ thể phụ thuộc policy và khả năng provider. Không lấy một boolean **enabled** để diễn tả toàn bộ trạng thái vòng đời.

## 7. Phân tách quyền tại KMS/HSM và ứng dụng

KMS/HSM là **điểm thực thi quan trọng** nhưng không tự biết mọi quy tắc nghiệp vụ. Security administrator cần xác định rõ ranh giới giữa IAM, key policy, ứng dụng và cryptographic provider.

~~~mermaid
sequenceDiagram
    participant App as Business workload
    participant API as AuthN/AuthZ layer
    participant KM as Key policy / KMS
    participant AUD as Audit service
    App->>API: Yêu cầu thao tác, resourceId, keyRef
    API->>API: Xác thực identity + quyền tenant/resource
    API->>KM: Crypto operation với keyId/version/purpose đã kiểm tra
    KM->>KM: Kiểm tra key state, key policy, IAM và allowed operation
    KM-->>API: Result hoặc Denied
    API->>AUD: principal, keyRef, operation, decision, requestId
    API-->>App: Kết quả được phép / lỗi phù hợp
    Note over API,KM: Admin thay đổi policy không phải quyền giải mã mặc định
~~~

### 7.1. Ví dụ phân tách trong chữ ký số

Giả sử **Billing Service** cần ký hóa đơn bằng private key Ed25519 trong HSM:

1. **Billing owner** duyệt quy tắc hóa đơn nào được phát hành.
2. **Security administrator** duyệt scope quyền Sign theo workload identity, key ID/version và purpose **BILLING_SIGNATURE**.
3. **KMS operator** triển khai key/policy đã duyệt.
4. **Billing Service** thực hiện kiểm tra nghiệp vụ và gửi đúng dữ liệu cần ký cho crypto provider.
5. **HSM/KMS** chỉ thực hiện Sign khi trạng thái và quyền tương ứng hợp lệ.
6. **Auditor** có thể truy vết approval và Sign events nhưng không được lấy private key.

Nếu Security administrator có quyền **sửa policy để tự trở thành Billing Service** mà không cần approval độc lập, cơ chế SoD bị mất. Nếu Billing Service kiểm tra nghiệp vụ không đầy đủ, KMS có thể được dùng làm signing oracle dù private key không xuất ra ngoài.

### 7.2. Ví dụ phân tách trong envelope encryption

**Customer Data Service** dùng AES-GCM với DEK ngẫu nhiên, còn KEK được bảo vệ trong KMS:

~~~text
Customer Data Service:
  - Có quyền truy cập record đã được xác thực
  - Có quyền GenerateDataKey/Unwrap đúng tenant/resource
  - Dùng plaintext DEK ngắn hạn để AES-GCM

KMS/HSM:
  - Giữ KEK theo policy, có thể non-exportable
  - Kiểm tra principal, key state, key usage
  - Audit Wrap/Unwrap

Security administrator:
  - Ban hành rule tenant isolation và grants
  - Không tự có quyền đọc hồ sơ hoặc plaintext DEK
  - Review usage, cache/TTL và incident response
~~~

Tệp database có thể chứa **ciphertext + nonce + tag + wrapped DEK + keyRef**. Một bản ghi không được chứa **plaintext DEK** chỉ vì ứng dụng muốn khôi phục dễ hơn. Nhưng nếu DEK đã được đưa vào JVM, việc suspend KEK ở KMS **không tự xóa bản DEK trong cache**. Administrator cần định nghĩa **cache invalidation, workload stop/revoke và thời điểm state thực sự có hiệu lực**.

### 7.3. Root KDF và quyền dẫn xuất

Một root secret với HKDF có thể tạo nhiều derived keys qua **salt/info**. **Domain separation** làm đầu ra cho các purpose khác nhau có tính chất tách biệt khi được dùng đúng, nhưng nếu một workload có quyền **DeriveKey tùy ý** từ root, nó có thể tạo các khóa của tenant khác.

Security administrator phải bảo đảm:

- Mỗi request DeriveKey ràng buộc **principal + tenant + purpose + version** từ nguồn đáng tin.
- **Info** được encode không nhập nhằng và có version.
- Root/PRK không được xuất trái policy; derived key cache bị giới hạn.
- Khi root bị nghi lộ, đổi nhãn info không thay thế root rotation.

Không dùng **HKDF(password)** làm cơ chế password hashing đăng nhập: mật khẩu con người thường entropy thấp và cần Argon2id/scrypt/PBKDF2 theo chính sách phù hợp.

## 8. Quy trình phê duyệt thay đổi quyền và trạng thái khóa

Security administrator không nên sửa policy trực tiếp mà không có **dấu vết yêu cầu và điều kiện xét duyệt**.

~~~mermaid
sequenceDiagram
    participant Req as Application/Key owner
    participant SA as Security administrator
    participant AP as Independent approver
    participant OP as Provisioning automation
    participant KM as KMS/HSM
    participant AU as Audit
    Req->>SA: Request: keyRef, principal, action, tenant, purpose, ticket
    SA->>SA: Kiểm tra least privilege, state, conflicts, expiry
    SA->>AP: Review thay đổi rủi ro cao
    AP-->>SA: Approve/Reject bằng danh tính riêng
    alt Được phê duyệt
        SA->>OP: Thực thi policy change có revision
        OP->>KM: Update grant/state theo provider
        KM-->>OP: Kết quả enforcement
        OP->>AU: Actor, approver, keyRef, before/after, outcome
        OP-->>Req: Quyền đã sẵn sàng / lỗi cụ thể
    else Bị từ chối
        SA->>AU: Denied + reason + ticket
        SA-->>Req: Denied
    end
~~~

Một request tốt có **principal**, **key ID/version**, **operation**, **tenant/environment**, **mục đích nghiệp vụ**, **thời gian hiệu lực**, **reason/ticket**, **người duyệt** và **giới hạn rủi ro**. Đối với thao tác khẩn cấp như suspend khóa bị nghi lộ, tổ chức có thể cho phép Security administrator thực hiện **ngay lập tức theo quyền khẩn cấp đã phê duyệt trước**, rồi yêu cầu review và audit sau đó. Không nên bắt chờ phê duyệt thông thường khi trì hoãn sẽ khiến thiệt hại tăng, nhưng cũng không cho phép hành động không truy vết.

### 8.1. Fail closed và kiểm tra hậu triển khai

Một policy thay đổi thành công ở control plane chưa chắc đã có hiệu lực ở mọi data plane. Cần kiểm tra:

1. KMS/HSM trả trạng thái/grant mới đúng key ID/version.
2. Workload được cấp quyền có thể chạy **đúng operation**, không có quyền khác.
3. Workload không được cấp quyền bị **từ chối thật**, kể cả đường gọi trực tiếp.
4. Bản cache/phiên cũ, region khác và in-flight requests có giới hạn được công bố.
5. Audit event có actor, approver, revision và kết quả nhất quán.

Nếu không đọc được policy hoặc KMS tạm thời mất kết nối, **không tự động fallback** sang raw key mặc định hoặc bypass IAM. Đường phục hồi phải là một quy trình được phê duyệt riêng.

### 8.2. Quy trình break-glass

Khi sự cố nghiêm trọng, có thể cần quyền tạm thời cao hơn quyền thường ngày. Một thiết kế break-glass phải có:

- **Identity riêng** có cơ chế xác thực mạnh, không dùng secret chung lâu dài.
- **Phạm vi nhỏ nhất:** key reference, operation, tenant, môi trường và khoảng thời gian cụ thể.
- **Approval/dual control** theo loại sự cố và policy, trừ thao tác cô lập khẩn cấp có cơ chế hậu kiểm riêng.
- **Audit và thông báo** tới Security/SOC ngay lúc kích hoạt.
- **Automatic expiry/revocation** khi kết thúc, kiểm tra không còn quyền rộng.
- **Post-incident review** xác định nguyên nhân và trách nhiệm, lưu bằng chứng.

**Break-glass không đồng nghĩa cho phép xuất root KEK hoặc private key bản rõ**. Nhiều sự cố có thể được giải quyết bằng **suspend, rotate, đổi grants, phục hồi key handle/backup trong KMS** hoặc migration có kiểm soát.

## 9. Java 17: Policy gate cho Security administrator và crypto workload

Ví dụ sau minh họa **tách quyền quản trị an ninh khỏi quyền dùng khóa**. Nó mô hình hóa:

- Security administrator có thể đề nghị hoặc kiểm tra **thay đổi policy** nhưng **không tự có quyền Sign**.
- Chỉ **crypto workload** đúng tenant, đúng purpose và được cấp quyền mới được gọi phép toán.
- Một thay đổi **GRANT_USE** hoặc **DESTROY** có nguy cơ cao cần **independent Key owner approval**.
- Tạm đình chỉ khóa theo tình huống khẩn cấp là một thao tác **quản trị** có ticket và lý do.
- **State SUSPENDED** chặn crypto operation theo mẫu policy **deny-by-default**.

Code chỉ kiểm tra **metadata và quyết định**; nó **không chứa private key hoặc DEK**, không thực hiện Sign/Decrypt và không ghi policy vào KMS. Trong production, IAM/key policy của KMS/HSM, identity provider và audit service phải thực thi và ghi nhận quyết định tương ứng. Các boolean đại diện cho kiểm tra đã xảy ra ở bên ngoài **không thay thế xác thực thực tế**.

~~~java
import java.util.Set;

public final class SecurityAdministratorDemo {
    enum Role {
        SECURITY_ADMINISTRATOR, KEY_OWNER,
        CRYPTO_WORKLOAD, INDEPENDENT_AUDITOR
    }

    enum CryptoOperation {
        SIGN, DECRYPT, ENCRYPT, UNWRAP, GENERATE_MAC
    }

    enum AdminAction {
        GRANT_USE, SUSPEND, DESTROY
    }

    enum State {
        ACTIVE, SUSPENDED, RETIRED, DESTROYED
    }

    enum Storage {
        HSM, APPROVED_KMS, PLAINTEXT_FILE
    }

    record Actor(
            String principalId, Role role, String tenantId) {
        Actor {
            if (principalId == null || principalId.isBlank()
                    || role == null || tenantId == null
                    || tenantId.isBlank()) {
                throw new IllegalArgumentException("Invalid actor");
            }
        }
    }

    record KeyInfo(
            String keyId, int version, String tenantId,
            String purpose, State state, Storage storage,
            boolean rawExportAllowed,
            Set<CryptoOperation> allowedOperations) {
        KeyInfo {
            if (keyId == null || keyId.isBlank() || version < 1
                    || tenantId == null || tenantId.isBlank()
                    || purpose == null || purpose.isBlank()
                    || state == null || storage == null
                    || allowedOperations == null) {
                throw new IllegalArgumentException("Invalid key metadata");
            }
            allowedOperations = Set.copyOf(allowedOperations);
        }
    }

    record Decision(boolean allowed, String reason) {}

    // Đây chỉ là authorization demo; không phải KMS enforcement.
    static Decision authorizeCrypto(
            Actor caller, KeyInfo key, CryptoOperation operation,
            boolean iamAuthorized, boolean resourceAuthorized) {
        if (caller.role() != Role.CRYPTO_WORKLOAD) {
            return new Decision(false, "ADMIN_OR_OTHER_ROLE_NO_CRYPTO");
        }
        if (!caller.tenantId().equals(key.tenantId())
                || !iamAuthorized || !resourceAuthorized) {
            return new Decision(false, "TENANT_OR_IAM_DENIED");
        }
        if (key.state() != State.ACTIVE) {
            return new Decision(false, "KEY_NOT_ACTIVE");
        }
        if (!key.allowedOperations().contains(operation)) {
            return new Decision(false, "KEY_PURPOSE_DENIED");
        }
        if (key.storage() == Storage.PLAINTEXT_FILE
                || key.rawExportAllowed()) {
            // Quy tắc minh họa cho private signing key critical.
            return new Decision(false, "STORAGE_POLICY_DENIED");
        }
        return new Decision(true, "ALLOW_CRYPTO_OPERATION");
    }

    // Kiểm tra một thay đổi nguy cơ cao. KHÔNG thực hiện thay đổi.
    static Decision reviewHighRiskChange(
            Actor proposer, Actor approver, KeyInfo key,
            AdminAction action, String ticket,
            boolean dependenciesReviewed) {
        if (proposer.role() != Role.SECURITY_ADMINISTRATOR) {
            return new Decision(false, "ADMIN_ROLE_REQUIRED");
        }
        if (approver.role() != Role.KEY_OWNER
                || proposer.principalId().equals(approver.principalId())) {
            return new Decision(false, "INDEPENDENT_APPROVAL_REQUIRED");
        }
        if (!proposer.tenantId().equals(key.tenantId())
                || !approver.tenantId().equals(key.tenantId())) {
            return new Decision(false, "TENANT_SCOPE_DENIED");
        }
        if (ticket == null || ticket.isBlank()) {
            return new Decision(false, "TICKET_REQUIRED");
        }
        if (action != AdminAction.GRANT_USE
                && action != AdminAction.DESTROY) {
            return new Decision(false, "WRONG_APPROVAL_WORKFLOW");
        }
        if (action == AdminAction.DESTROY) {
            if (!dependenciesReviewed || key.state() == State.ACTIVE) {
                return new Decision(false, "DEPENDENCIES_OR_STATE_DENIED");
            }
        }
        return new Decision(true, "APPROVED_FOR_IMPLEMENTATION");
    }

    // Emergency suspend được phép theo runbook có ticket/audit.
    static Decision reviewEmergencySuspend(
            Actor admin, KeyInfo key, String incidentId) {
        if (admin.role() != Role.SECURITY_ADMINISTRATOR
                || !admin.tenantId().equals(key.tenantId())) {
            return new Decision(false, "ADMIN_SCOPE_DENIED");
        }
        if (incidentId == null || incidentId.isBlank()) {
            return new Decision(false, "INCIDENT_ID_REQUIRED");
        }
        if (key.state() != State.ACTIVE) {
            return new Decision(false, "INVALID_STATE_TRANSITION");
        }
        return new Decision(true, "SUSPEND_REQUEST_ALLOWED");
    }

    static void show(String label, Decision result) {
        System.out.println(label + ": " + result.allowed()
                + " / " + result.reason());
    }

    public static void main(String[] args) {
        Actor securityAdmin = new Actor(
                "security-admin-1", Role.SECURITY_ADMINISTRATOR,
                "tenant-42");
        Actor keyOwner = new Actor(
                "billing-owner", Role.KEY_OWNER, "tenant-42");
        Actor billingService = new Actor(
                "billing-service", Role.CRYPTO_WORKLOAD, "tenant-42");
        Actor otherTenantService = new Actor(
                "other-service", Role.CRYPTO_WORKLOAD, "tenant-OTHER");

        KeyInfo signingKey = new KeyInfo(
                "billing-sign-v3", 3, "tenant-42", "BILLING_SIGNATURE",
                State.ACTIVE, Storage.HSM, false,
                Set.of(CryptoOperation.SIGN));

        show("Billing service Sign",
                authorizeCrypto(billingService, signingKey,
                        CryptoOperation.SIGN, true, true));
        show("Security administrator Sign",
                authorizeCrypto(securityAdmin, signingKey,
                        CryptoOperation.SIGN, true, true));
        show("Other tenant Sign",
                authorizeCrypto(otherTenantService, signingKey,
                        CryptoOperation.SIGN, true, true));
        show("Wrong crypto operation",
                authorizeCrypto(billingService, signingKey,
                        CryptoOperation.DECRYPT, true, true));

        show("Admin self-approval",
                reviewHighRiskChange(securityAdmin, securityAdmin,
                        signingKey, AdminAction.GRANT_USE,
                        "SEC-123", false));
        show("Independent approval",
                reviewHighRiskChange(securityAdmin, keyOwner,
                        signingKey, AdminAction.GRANT_USE,
                        "SEC-123", false));
        show("Emergency suspend",
                reviewEmergencySuspend(
                        securityAdmin, signingKey, "INC-456"));

        KeyInfo suspended = new KeyInfo(
                signingKey.keyId(), signingKey.version(),
                signingKey.tenantId(), signingKey.purpose(),
                State.SUSPENDED, signingKey.storage(),
                signingKey.rawExportAllowed(),
                signingKey.allowedOperations());
        show("Sign after suspend",
                authorizeCrypto(billingService, suspended,
                        CryptoOperation.SIGN, true, true));
        show("Destroy without dependency review",
                reviewHighRiskChange(securityAdmin, keyOwner, suspended,
                        AdminAction.DESTROY, "SEC-789", false));
    }
}
~~~

Lưu thành **SecurityAdministratorDemo.java** và chạy với **JDK 17+**:

~~~bash
javac SecurityAdministratorDemo.java
java SecurityAdministratorDemo
~~~

Kết quả dự kiến:

~~~text
Billing service Sign: true / ALLOW_CRYPTO_OPERATION
Security administrator Sign: false / ADMIN_OR_OTHER_ROLE_NO_CRYPTO
Other tenant Sign: false / TENANT_OR_IAM_DENIED
Wrong crypto operation: false / KEY_PURPOSE_DENIED
Admin self-approval: false / INDEPENDENT_APPROVAL_REQUIRED
Independent approval: true / APPROVED_FOR_IMPLEMENTATION
Emergency suspend: true / SUSPEND_REQUEST_ALLOWED
Sign after suspend: false / KEY_NOT_ACTIVE
Destroy without dependency review: false / DEPENDENCIES_OR_STATE_DENIED
~~~

### 9.1. Điều demo chứng minh

- **Security admin là vai trò quản trị**, không có quyền Sign mặc định.
- **Dù caller tự nhận IAM đã được cấp**, tenant và role vẫn phải đúng trong mô hình này.
- **Purpose-specific operation** không tự chuyển từ Sign sang Decrypt.
- **Tự phê duyệt** bị từ chối; một Key owner khác mới đủ điều kiện xét đề nghị.
- **Suspended** chặn phép toán mật mã của key trong mô hình fail-closed.
- **Destroy** chỉ có thể tiến hành theo workflow khi có dependency review và trạng thái phù hợp.

### 9.2. Điều demo chưa bảo đảm trong production

1. **Không có kiểm tra danh tính thật:** principalId/role/tenantId chỉ là dữ liệu truyền vào. Provider identity, token validation và session security phải được triển khai riêng.
2. **Không có IAM/KMS thực:** không có lệnh KeyPolicy, Grant, Sign hoặc Destroy thật. Việc trả **APPROVED_FOR_IMPLEMENTATION** chỉ cho biết request hợp lệ theo rule demo.
3. **Không bảo đảm four-eyes độc lập về mặt tổ chức:** hai chuỗi principalId khác nhau vẫn có thể do một người kiểm soát. Cần hệ thống identity và quy tắc độc lập thực.
4. **Không có persistence/concurrency:** state và policy trong hệ thống phân tán phải có revision, event ordering, transaction và protection trước thao tác đồng thời.
5. **Không có workload attestation hoặc token scope:** một workload có thể được phép Sign nhưng vẫn phải kiểm tra nghiệp vụ để không ký dữ liệu ngoài ý muốn.
6. **Không có audit bền vững:** production phải log thay đổi và sử dụng bằng cơ chế độc lập; demo chỉ in kết quả kiểm tra.
7. **Chưa xử lý decrypt-only/verify-only:** trạng thái Retired/Suspended/Compromised có quy tắc tùy policy, không được tự nới.
8. **Không thể chặn secret đã export:** local DEK, session key hoặc private key nằm ngoài KMS có thể vẫn bị sử dụng khi key gốc đã Suspended.
9. **Storage policy chỉ minh họa cho critical signing key:** không nên áp cùng rule non-exportable/operation cho mọi DEK, public key hoặc HMAC key.
10. **Không thay thế security testing:** cần kiểm tra data-plane enforcement, direct API bypass, key version, audit, backup và incident response.

## 10. Incident response: Security administrator làm gì khi có sự cố khóa?

Một Security administrator phải giúp tổ chức trả lời **khóa hoặc quyền dùng khóa nào bị ảnh hưởng, hành động khẩn cấp nào cần thực hiện, ai chịu trách nhiệm phục hồi và bằng chứng nào chứng minh sự cố đã được xử lý**. Không nên chỉ đổi alias hoặc tạo khóa mới rồi kết luận xong.

### 10.1. Kịch bản A: Workload credential có quyền Unwrap bị lộ

Giả sử **Customer Data Service** dùng KMS để Unwrap DEK và giải mã bằng AES-GCM. Credential của service có dấu hiệu xuất hiện trong một repository không được phép.

**Runbook minh họa:**

1. **Tạo incident:** ghi mã sự cố, thời điểm phát hiện, key IDs/versions, tenant và service identity liên quan.
2. **Cô lập credential:** thu hồi token/credential, khóa role grants liên quan hoặc đình chỉ workload theo mức rủi ro. Nếu cần tạm chặn key trong KMS, kiểm tra tác động tới dữ liệu và dịch vụ.
3. **Rà soát audit:** kiểm tra các lần Decrypt/Unwrap, request ID, principal, key reference và khoảng thời gian nghi vấn. Không tải toàn bộ raw key hoặc plaintext vào hệ thống điều tra.
4. **Kiểm tra material đã xuất:** xác định DEK plaintext từng được cấp, cache TTL, số instance và khả năng đối thủ đã thu thập ciphertext.
5. **Giới hạn blast radius:** thu hẹp grants theo tenant, purpose và key version; bảo vệ các workload khác dùng chung role.
6. **Chọn migration:** nếu chỉ credential bị lộ nhưng chưa có bằng chứng DEK bị lấy, điều tra theo rủi ro; nếu **DEK bị lộ**, cân nhắc thay DEK và re-encrypt dữ liệu.
7. **Khôi phục:** cấp identity/credential mới có scope đúng, kiểm thử deny/allow, khôi phục traffic có giám sát.
8. **Hậu kiểm:** review root cause, IAM design, cache policy, phát hiện bất thường, lập kế hoạch cải tiến.

**Rewrap DEK bằng KEK mới không sửa được việc plaintext DEK đã bị lộ.** Security administrator phải phối hợp với key owner để quyết định khả năng ảnh hưởng dữ liệu và phạm vi re-encryption.

### 10.2. Kịch bản B: Private signing key nghi bị xuất trái phép

Giả sử private key ký JWT bị nghi xuất khỏi HSM hoặc một bản PEM cũ còn nằm trong CI artifact.

- **Ngay lập tức:** xác định key ID/version và trạng thái tin cậy, dừng Sign mới qua đường bị ảnh hưởng và thu hồi credential có nguy cơ.
- **Điều tra:** key material có thật sự bị xuất hay chỉ có quyền Sign bị lạm dụng? Những chữ ký/token nào có thể đã được tạo?
- **Thay khóa:** tạo signing key mới trong provider được phê duyệt, không dùng lại seed hoặc private key cũ.
- **Cập nhật verifier:** chính sách issuer, JWKS, certificate/trust chain, thời gian cache, token revocation và session invalidation.
- **Xử lý lịch sử:** chữ ký trước sự cố **không tự mất hiệu lực toán học**, nhưng quyết định tin cậy phụ thuộc thời điểm, bằng chứng, revocation policy và yêu cầu nghiệp vụ/pháp lý.
- **Review:** tách quyền đọc CI artifact khỏi quyền production, kiểm tra secret scanning và quy trình key export.

**Chỉ disable Sign trong KMS không ngăn đối thủ ký offline nếu đã có bản private key**. Security administrator phải xử lý cả **trust distribution** và token/session đã phát, không chỉ trạng thái KMS.

### 10.3. Kịch bản C: Mất khóa hoặc KMS không khả dụng

Sự cố sẵn sàng **khác** sự cố lộ bí mật. Nếu KMS không khả dụng:

- Không tự tạo **DEK mặc định** hoặc hardcode KEK dự phòng trong mã.
- Xác định **key/version và ciphertext dependencies** để tránh dùng sai khóa.
- Kiểm tra **HA/DR, replication, secure backup/restore** đã được phê duyệt; phân tách quyền restore với quyền đọc dữ liệu.
- Nếu đã rotate và chỉ alias mới được lưu, cần kiểm tra khả năng giải mã lịch sử bằng key references thực.
- Tránh **hủy key** chỉ vì không có traffic; một khóa ít sử dụng có thể vẫn cần cho archive nhiều năm.
- Đối với emergency recovery, áp dụng **scope, approval, TTL và audit** ngay cả khi đang có áp lực khôi phục dịch vụ.

**Không lấy lý do availability để bỏ qua secrecy hoặc IAM**. Security administrator phải cân bằng mục tiêu **confidentiality, integrity và availability** bằng các quy trình đã được thử nghiệm trước.

## 11. Kiểm toán và đo lường hiệu quả công việc

Vai trò Security administrator không kết thúc sau khi cấp policy. **Audit evidence** cần đủ để độc lập tái dựng *ai đã thay đổi quyền, vì sao, thay đổi có hiệu lực từ lúc nào, ai đã dùng khóa và kết quả là gì*.

### 11.1. Những sự kiện cần ghi

| Event | Metadata thiết yếu | Không được ghi |
|---|---|---|
| **Create/ImportKey** | actor, key ID/version, key purpose, tenant, provider, approval | Raw key bytes, private-key seed |
| **Grant/Revoke** | principal, scope, operation, ticket, approver, policy revision | Credential/token bí mật |
| **Sign/Decrypt/Unwrap** | principal, key ref, operation, tenant, request ID, result | Plaintext, DEK, nội dung nhạy cảm |
| **Rotate/AliasChange** | old/new reference, owner, effective time, migration status | Raw KEK/DEK |
| **Suspend/Disable** | incident/reason, actor, state revision, effective region | Private key, root secret |
| **Backup/Restore** | security domain, approval, provider outcome, restore-test ID | Raw backup secret nếu không bắt buộc theo contract |
| **DestroyKey** | dependency review, legal/retention status, approvals, provider evidence | Material đã hủy hoặc bản sao bất hợp lệ |
| **BreakGlassActivation** | actor, approvers, key scope, TTL, actions, post-review | Secret hỗ trợ khẩn cấp |

Audit log nên có **tính toàn vẹn, phân quyền và retention** độc lập với người có khả năng sửa key policy. Không nên để Security administrator hoặc operator có thể **xóa/sửa dấu vết của chính mình** mà không bị phát hiện.

### 11.2. Audit metadata không phải dữ liệu tuyệt đối vô hại

Key ID, tenant ID, tên môi trường, tên customer hoặc resource path có thể lộ cấu trúc vận hành và thông tin khách hàng. Log phải được bảo vệ bằng IAM và retention phù hợp, đồng thời giảm PII không cần thiết. Với hệ thống nhiều tenant, **auditor được phép đọc metadata** không có nghĩa được xem mọi dữ liệu nhạy cảm của tenant.

### 11.3. Chỉ số vận hành gợi ý

- **Số key không có owner/purpose/cryptoperiod** trong inventory.
- **Số service roles có quyền Decrypt/Sign/Unwrap rộng** hơn scope được duyệt.
- **Tỷ lệ thay đổi key policy có ticket, approver độc lập và audit event**.
- **Số key production ở trạng thái không phù hợp** hoặc quá hạn rotation.
- **Số lần break-glass**, phạm vi/TTL và tỷ lệ đã review sau sự kiện.
- **Số raw key exports hoặc key backup ngoài policy** được phát hiện.
- **Số key bị mất mapping version hoặc có alias drift** giữa registry và KMS.
- **Số lần restore test thành công** với dữ liệu mẫu và đúng key version.
- **Thời gian phát hiện/thu hồi credential có quyền ký/giải mã** khi sự cố.
- **Số quyền không dùng quá lâu** và tiến độ thu hồi theo least privilege.

Các chỉ số phải được giải thích theo **rủi ro và coverage**. Ví dụ “không có KeyExport audit event” không chứng minh private key không tồn tại trong Git hoặc backup; cần kiểm tra cả bề mặt bên ngoài provider.

## 12. Threat model: Khi Security administrator được thiết kế sai

| Sai lầm | Rủi ro | Biện pháp |
|---|---|---|
| Dùng một tài khoản admin chung cho nhiều người | Không quy trách nhiệm, credential lộ ảnh hưởng rộng | Danh tính cá nhân/workload riêng, MFA và audit |
| Security admin tự cấp **Decrypt** rồi tự duyệt | Vượt SoD, truy cập trái phép dữ liệu khách hàng | Independent approval, permission boundary, detection |
| Admin có thể **xóa audit logs** của chính mình | Không còn chứng cứ điều tra | Audit store độc lập, immutable/append-only theo thiết kế |
| Chỉ quản lý policy qua UI | Caller có thể bỏ qua UI và gọi KMS trực tiếp | Enforcement tại KMS/HSM/crypto gateway |
| Quyền Sign không ràng buộc nghiệp vụ | Workload bị chiếm trở thành signing oracle | Business authorization, scope, rate limit và audit |
| Unwrap quyền toàn tenant/production | Cross-tenant data exposure, confused deputy | Fine-grained grants, resource authorization |
| Chỉ lưu alias, không lưu key version | Rotate gây mất khả năng decrypt/verify lịch sử | Immutable key references, migration plan |
| Key material ở Git, image hoặc log | Bí mật bị sao chép ngoài KMS/HSM | Không raw export; secret scanning và rotation khi lộ |
| Giữ plaintext DEK quá lâu trong cache | Revocation không ngăn sử dụng offline | TTL, invalidation, workload shutdown |
| Khóa AES-GCM dùng lại nonce | Mất bí mật/toàn vẹn dù IAM tốt | Nonce uniqueness per DEK, invocation limits |
| HKDF root cấp DeriveKey tùy context | Khóa của tenant khác có thể bị dẫn xuất | Context allowlist, authenticated tenant, key hierarchy |
| Break-glass không thời hạn hoặc không audit | “Ngoại lệ” trở thành quyền thường trực | TTL, scope, approval và post-incident review |
| Hủy KEK trước khi rewrap/decrypt archive | Mất dữ liệu không khôi phục được | Dependency inventory, backup/restore drill |
| Rewrap DEK đã lộ rồi coi là an toàn | Đối thủ vẫn có plaintext DEK | Đánh giá thay DEK, re-encrypt, incident scope |
| Chỉ disable KMS khi private key đã export | Đối thủ vẫn ký offline | Revoke trust, rotate key, revoke token/session |
| Quyền admin tập trung không giám sát | Một credential có blast radius toàn hệ thống | Hierarchy theo environment/tenant, SoD và alerting |
| Thay role bindings khi KMS lỗi để “chạy tạm” | Fail-open, mất boundary và audit | Controlled recovery, không bypass KMS policy |
| Không review quyền sau nhân sự đổi nhóm | Privilege tồn tại quá lâu | JML lifecycle, định kỳ access review, revoke |

**Security administrator cũng là một đối tượng cần được kiểm soát.** Mục tiêu không phải “tin admin tuyệt đối”, mà là giảm tác động nếu một tài khoản, một người hoặc một automation có quyền quản trị bị chiếm hoặc mắc lỗi.

## 13. Case study: Nền tảng nhiều tenant và sự cố cấp quyền sai

Giả sử một hệ thống có **Payment Service**, **Identity Service**, **Customer Data Service**, **Security Admin Console**, **KMS** và **SIEM/Audit**. Một kỹ sư đề nghị cấp cho Customer Data Service quyền **Decrypt toàn bộ KEK production** để xử lý nhanh một backlog.

### 13.1. Thiết kế chưa an toàn

~~~text
role=customer-data-svc
allow=["kms:Decrypt", "kms:Unwrap", "kms:ManageKey"]
resources=["*"]

Yêu cầu được áp dụng ngay bởi admin.
Không có key owner review.
Không ghi ticket hoặc key version.
~~~

Vấn đề:

1. **Resources="*"** mở rộng blast radius sang tenant/service khác.
2. **ManageKey** không phải nhu cầu của một workload giải mã dữ liệu.
3. Key ID do caller gửi có thể khiến service truy cập dữ liệu của tenant không thuộc quyền.
4. Không có approval/audit phù hợp nên khó xác định ai chấp nhận rủi ro.
5. Nếu credential bị đánh cắp, đối thủ có đường gọi Decrypt/Unwrap rất rộng dù KEK non-exportable.

### 13.2. Luồng đề xuất của Security administrator

1. **Thu thập yêu cầu:** xác định backlog thuộc tenant nào, dữ liệu nào, khối lượng, thời hạn và owner.
2. **Review kiến trúc:** kiểm tra liệu cần Unwrap theo bản ghi hay có thể dùng service chuyên dụng với ràng buộc resource.
3. **Policy tối thiểu:** chỉ key references/versions của tenant được phép, operation cần thiết và thời gian hiệu lực.
4. **Independent Key owner approval:** owner dữ liệu xác nhận phạm vi nghiệp vụ; Security administrator kiểm tra rule và SoD.
5. **Provisioning qua automation:** cập nhật KMS policy/grants theo revision, không trao raw KEK/DEK cho nhóm vận hành.
6. **Negative tests:** workload bị từ chối với key khác tenant, wrong purpose, Export, Destroy và stale key versions.
7. **Audit:** ghi request, approval, policy diff, key ID/version, data-plane usage và kết quả.
8. **Operations:** kiểm soát nonce AES-GCM, DEK cache TTL và hiệu năng, không tạo bản sao khóa mới để “đỡ gọi KMS”.
9. **Expiry/review:** tự thu hồi quyền tạm thời sau backlog, đối soát grants và lưu evidence.
10. **Response:** nếu phát hiện Decrypt ngoài dự kiến, đình chỉ credential hoặc key theo runbook, khoanh vùng và đánh giá ảnh hưởng dữ liệu.

### 13.3. Kết quả mong muốn

Hệ thống vẫn giải quyết được backlog, nhưng **không cấp quyền quản trị hoặc giải mã vượt nhu cầu**, có thể chứng minh ai duyệt quyền và key version nào được dùng. Khi cần rotate KEK/DEK hoặc xử lý sự cố, inventory và audit cho phép xác định **tập dữ liệu, workload và key dependencies** chính xác.

**Giới hạn:** Ví dụ không đưa ra một cấu hình IAM cụ thể. Mỗi provider có semantics khác nhau về tài nguyên, alias, key version, encryption context và grant. Trước triển khai phải kiểm thử trên provider thật, không chỉ dựa vào file pseudo-policy hoặc code Java.

## 14. Checklist của Security administrator trước khi đưa hệ thống vào production

1. **Ownership:** mỗi key family/version có key owner, security administrator, operator và contact incident rõ ràng?
2. **RACI:** ai đề nghị, phê duyệt, triển khai, sử dụng, kiểm toán và hủy khóa? Có người tự phê duyệt chính mình không?
3. **Identity:** user/workload dùng danh tính riêng, xác thực mạnh, không chia sẻ super-admin credential?
4. **Least privilege:** grants giới hạn keyRef/version, environment, tenant, purpose, operation, TTL và resource?
5. **Separation of duties:** quyền quản trị policy tách khỏi raw key export, Sign/Decrypt và xóa audit?
6. **Key generation:** thuật toán, nguồn entropy, provider, key size và key purpose đã được chấp thuận?
7. **Storage:** root/KEK/private key giữ trong approved KMS/HSM khi phù hợp, export controls và backup domain có bằng chứng?
8. **DEK/cache:** wrapped DEK được lưu đúng, plaintext DEK trong memory có scope/TTL/cleanup và giới hạn dump?
9. **AAD/nonce:** AES-GCM dùng nonce không trùng với cùng DEK và AAD/metadata được ràng buộc đúng?
10. **Signing:** public key được phát hành từ nguồn tin cậy, JWKS/certificate rotation/trust policy có kế hoạch?
11. **KDF:** DeriveKey không cho caller tùy chọn tenant/purpose hoặc root secret trái quyền?
12. **Lifecyle states:** Active, Suspended, Retired, Compromised, Destroyed có operation policy và effective time rõ?
13. **Rotation:** DEK, KEK, signing key, HMAC key, root key có migration, versioning và dependency review phù hợp?
14. **Audit:** log actor, approver, key ID/version, operation, decision, reason, ticket mà không log raw secret?
15. **Independent auditor:** có quyền đối soát nhưng không tự Sign/Decrypt hoặc sửa dấu vết?
16. **Break-glass:** có approval, scope nhỏ, expiration, alert và review sau khi dùng?
17. **DR/recovery:** backup/restore đã thử, retention và key material destruction được kiểm soát?
18. **Incident response:** đã có runbook cho credential lộ, key compromise, API abuse, nonce reuse và KMS outage?
19. **Policy drift:** có đối chiếu key registry, KMS/HSM state, alias/grants và workload thực tế?
20. **Negative tests:** đã thử trường hợp admin tự Sign, workload dùng wrong key, cross-tenant và direct-API bypass?

### Câu hỏi tự kiểm tra

**Câu 1.** Security administrator có phải là người luôn được xem raw private key và giải mã mọi dữ liệu không?

**Trả lời:** **Không.** Quản trị security policy là một nhóm quyền khác với sử dụng key material. Thực hiện Sign/Decrypt/Export phải có authorization riêng và nguyên tắc tối thiểu.

**Câu 2.** KMS giữ private key non-exportable thì có thể bỏ kiểm tra quyền Sign của workload không?

**Trả lời:** **Không.** Caller vẫn có thể yêu cầu KMS ký nội dung trái phép. Cần IAM, business authorization, purpose, rate limits và audit.

**Câu 3.** Key owner có thể tự đề nghị, tự phê duyệt và tự triển khai quyền Decrypt production không?

**Trả lời:** **Không nên.** Với quyền nguy cơ cao, cần separation of duties và phê duyệt độc lập theo policy để giảm lạm dụng/quyết định sai.

**Câu 4.** Dual control có đồng nghĩa KEK được chia thành hai nửa không?

**Trả lời:** **Không.** Dual control là yêu cầu nhiều chủ thể tham gia quyết định/thao tác; split knowledge là cách phân tách hiểu biết về secret theo cơ chế riêng.

**Câu 5.** Nếu Security administrator thay state của KEK sang SUSPENDED, plaintext DEK đã cache trong JVM có tự biến mất không?

**Trả lời:** **Không.** Phải quản lý cache TTL/invalidation, phiên/workload và các bản sao ngoài KMS. Cần xác định state enforcement thực sự.

**Câu 6.** Rewrap một DEK đã bị lộ bằng KEK mới có làm DEK an toàn trở lại không?

**Trả lời:** **Không.** Đối thủ vẫn giữ DEK đã lộ; cần đánh giá thay DEK, re-encrypt dữ liệu và phạm vi ciphertext bị ảnh hưởng.

**Câu 7.** Vì sao Security administrator phải quan tâm tới nonce AES-GCM dù không trực tiếp mã hóa dữ liệu?

**Trả lời:** Vì policy về cryptoperiod, key usage limits và thiết kế nhiều instance ảnh hưởng tới khả năng nonce bị lặp. Nguồn nonce/chiến lược uniqueness phải được kiểm soát ở tầng ứng dụng/giao thức.

**Câu 8.** Một chữ ký Ed25519 vẫn Verify thành công sau khi private key bị suspend. Có thể kết luận sự kiện ký đó hợp pháp?

**Trả lời:** **Không.** Verify chứng minh tính hợp lệ mật mã với public key, nhưng quyết định tin cậy còn phụ thuộc issuer, thời gian, trạng thái khóa, policy và bằng chứng sự cố.

**Câu 9.** Một auditor có quyền đọc audit logs có nên được cấp quyền quản trị key policy để “tiện kiểm tra” không?

**Trả lời:** **Không mặc định.** Audit độc lập cần hạn chế quyền tự thay dữ liệu được kiểm toán. Có thể cấp quyền read-only phù hợp.

**Câu 10.** Nếu người dùng gửi key ID của tenant khác, một service được IAM cho Unwrap rộng có an toàn khi thực hiện ngay không?

**Trả lời:** **Không.** Cần kiểm tra tenant và resource từ nguồn danh tính đáng tin, đúng purpose, key version và quyền của caller; không coi key ID là giấy phép.

**Câu 11.** Khi KMS ngừng hoạt động, có thể dùng raw KEK hardcode như fallback để tiếp tục giao dịch không?

**Trả lời:** **Không.** Đó là đường bypass storage/IAM và tạo secret exposure. Cần HA/DR hoặc quy trình khôi phục được phê duyệt, kiểm soát và kiểm toán.

**Câu 12.** Security administrator chỉ cần ban hành policy YAML là hoàn thành trách nhiệm chưa?

**Trả lời:** **Chưa.** Cần ánh xạ và kiểm chứng policy tại KMS/HSM/crypto gateway, kiểm thử đường từ chối, audit, rotation, backup/restore, kiểm tra drift và phản ứng sự cố.

**Điểm cốt lõi:** **Security administrator bảo vệ hệ thống quản lý khóa bằng cách quản trị chính sách, quyền hạn, ranh giới tin cậy, thay đổi vòng đời và bằng chứng kiểm toán — không phải bằng quyền sử dụng mọi khóa.** Thiết kế tốt tách **Security administrator, Key owner, operator, workload và auditor**, áp dụng **least privilege, deny by default, independent approval và break-glass có kiểm soát**, đồng thời thực thi chính sách tại KMS/HSM và ứng dụng. Khi những nguyên tắc này được kết hợp với **envelope encryption, chữ ký số, KDF, rotation, backup, thu hồi và hủy khóa**, tổ chức mới có thể quản lý key material xuyên suốt vòng đời và giới hạn thiệt hại khi xảy ra sự cố.
