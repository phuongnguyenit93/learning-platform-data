# Purpose — Mục đích sử dụng khóa trong Key inventory

## 1. Purpose trong key inventory là gì?

**Purpose** là **mục đích sử dụng đã được phê duyệt của một khóa mật mã**. Trong **key inventory** (sổ kiểm kê khóa), trường này trả lời câu hỏi: **“Khóa này tồn tại để bảo vệ tài sản, quy trình hay giao thức nào, và được phép thực hiện những chức năng mật mã nào trong phạm vi đó?”**

Ví dụ, cùng là khóa AES-256 nhưng hai tài sản dưới đây **không có cùng purpose**:

- `billing-record-dek-v3`: mã hóa các bản ghi hóa đơn của hệ thống Billing bằng AES-GCM.
- `billing-kek-v2`: bọc/giải bọc các DEK của hệ thống Billing theo cơ chế quản lý khóa.

Tương tự, một private key dùng **ký hóa đơn điện tử** không nên tự động được sử dụng để ký **JWT xác thực** hoặc **bản phát hành phần mềm**, dù thư viện có thể thực hiện phép ký với cùng thuật toán.

Trong phạm vi mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, Purpose là điểm nối giữa **mục tiêu nghiệp vụ** và **quản trị vòng đời khóa**: tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy. Khái niệm này cũng giúp kết nối mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

> **Nguyên tắc:** **Một khóa chỉ nên có những mục đích đã được chấp thuận rõ ràng.** Việc ghi `purpose` vào inventory **không tự cưỡng chế được chính sách**: ứng dụng, IAM, KMS/HSM, giao thức và quy trình vận hành phải thực sự chặn việc sử dụng ngoài mục đích.

### Ví dụ ngắn

Một hệ thống có hai private signing key ECDSA P-256:

~~~text
keyId: billing-invoice-signing-v2
purpose: INVOICE_SIGNATURE
allowedOperation: Sign
approvedWorkload: billing-invoice-signer

keyId: identity-access-token-signing-v5
purpose: ACCESS_TOKEN_SIGNATURE
allowedOperation: Sign
approvedWorkload: identity-token-issuer
~~~

Cả hai đều có khả năng tạo chữ ký ECDSA, nhưng **mục đích kinh doanh, bên được phép sử dụng, loại dữ liệu được ký, thời hạn lưu và cách ứng cứu sự cố khác nhau**. Nếu chỉ có trường `algorithm=ECDSA`, tổ chức không thể giải thích vì sao một phép ký là hợp lệ.

## 2. Phân biệt Purpose, algorithm, key usage và permission

Những khái niệm dưới đây thường xuất hiện cùng một bản ghi nhưng **không thay thế nhau**.

| Thuộc tính | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **Purpose** | Tại sao khóa tồn tại và bảo vệ cái gì? | `INVOICE_SIGNATURE`, `CUSTOMER_DATA_AT_REST` |
| **Algorithm** | Phép mật mã sử dụng là gì? | `AES-256-GCM`, `ECDSA P-256`, `HMAC-SHA-256` |
| **Key type** | Khóa thuộc loại nào? | Symmetric secret, RSA private/public, EC agreement key |
| **Key usage** | Khóa được phép dùng với loại thao tác mật mã nào? | Sign, Verify, Encrypt, Decrypt, Wrap, Unwrap, Derive |
| **IAM permission** | Ai có quyền gọi thao tác trên key resource? | Service account được `Sign` trên một key ID |
| **Data scope** | Dữ liệu/đối tượng nào được bảo vệ? | Hóa đơn tenant A, token của identity service |
| **Environment** | Khóa được dùng ở đâu? | Production, staging, development |
| **Key state** | Khóa đang ở trạng thái vòng đời nào? | Pre-activation, Active, Suspended, Deactivated |
| **Cryptoperiod** | Trong khoảng nào được phép sử dụng để bảo vệ dữ liệu mới? | Từ ngày kích hoạt đến ngày kết thúc dùng mới |
| **Owner/custodian** | Ai chịu trách nhiệm quyết định và vận hành? | Billing security owner / KMS team |

Có thể mô hình hóa một **quyết định sử dụng khóa hợp lệ** như sau:

~~~text
Allowed(request, key) =
    key.purpose == request.approvedPurpose
    AND request.dataScope matches key.approvedDataScope
    AND request.environment == key.environment
    AND requestedOperation is allowed by key.keyUsage
    AND caller has required permission on exact key/version
    AND key state and cryptoperiod allow this operation
    AND algorithm/protocol constraints are satisfied
    AND required business approvals are satisfied
~~~

Đây là **mô hình logic**, không phải một quy tắc có thể tự động áp dụng cho mọi dịch vụ KMS. Một số nhà cung cấp chỉ hiểu thuật toán, key ID và quyền API; điều kiện như “đã phê duyệt hóa đơn” phải được thực thi ở **tầng nghiệp vụ**.

### Cùng một operation không đồng nghĩa cùng purpose

`Sign` có thể dùng cho chứng thư TLS, hóa đơn, manifest phần mềm, JWT hoặc xác nhận giao dịch. Nếu hệ thống chỉ kiểm tra `operation=Sign`, một key có thể bị dùng cho **nhiều loại dữ liệu khác nhau** trái với chính sách.

Ngược lại, một purpose có thể yêu cầu hơn một operation theo vòng đời. Ví dụ **bảo vệ dữ liệu lưu trữ** có thể cho phép `Encrypt` khi key đang active và `Decrypt` có kiểm soát để xử lý dữ liệu cũ sau khi key ngừng mã hóa mới. **Mục đích không nên bị giản lược thành tên một API.**

## 3. Vì sao key inventory phải ghi rõ Purpose?

### 3.1. Ngăn tái sử dụng khóa sai mục đích

**Key reuse** trái mục đích làm tăng *blast radius* khi khóa bị lộ và dễ gây lỗi giao thức. Nếu một signing key bị dùng chung cho phát hành JWT và ký hóa đơn, sự cố ở identity service có thể ảnh hưởng cả tính tin cậy của hóa đơn, dù hai quy trình cần biện pháp ứng cứu và thời hạn lưu khác nhau.

### 3.2. Xác định quyền tối thiểu

Khi có purpose rõ ràng, hệ thống có thể cấp quyền theo **đúng key + operation + workload + environment + data scope**, thay vì cấp một vai trò rộng như “ứng dụng được sử dụng mọi khóa”.

### 3.3. Hỗ trợ rotation và khả năng giải mã dữ liệu cũ

Purpose quyết định cách thay khóa:

- **Signing key:** ngừng ký mới bằng bản cũ, nhưng giữ thông tin xác minh lịch sử theo chính sách.
- **DEK:** khi đổi DEK có thể phải mã hóa lại dữ liệu phụ thuộc.
- **KEK:** khi đổi KEK có thể chỉ cần **rewrap** DEK, không nhất thiết mã hóa lại ciphertext dữ liệu.
- **HMAC key:** phải tính đến tag/webhook còn chờ xác minh và cửa sổ retry.
- **ECDH ephemeral key:** tồn tại ngắn, thường không cần lưu như một khóa quản trị lâu dài cho từng phiên.

Nếu inventory chỉ ghi `purpose=security`, đội vận hành sẽ không biết xử lý thế nào khi key đến hạn hoặc bị nghi lộ.

### 3.4. Tạo bằng chứng kiểm toán

Auditor cần trả lời được: **Vì sao khóa được tạo? Ai phê duyệt? Tài sản nào phụ thuộc? Mỗi lượt sử dụng có đúng phạm vi?** Trường Purpose là một thành phần của câu trả lời, đi cùng owner, policy, key version, log và bằng chứng vận hành.

## 4. Các nhóm Purpose thường gặp

Danh mục dưới đây là **taxonomy minh họa**; tổ chức có thể định nghĩa mã mục đích riêng, nhưng phải giữ ngữ nghĩa rõ ràng và ổn định.

| Purpose đề xuất | Key material thường gặp | Chức năng chính | Tài sản được bảo vệ |
| --- | --- | --- | --- |
| `DATA_AT_REST_ENCRYPTION` | DEK đối xứng, ví dụ AES-GCM | Encrypt/Decrypt | Bản ghi hoặc đối tượng lưu trữ |
| `DEK_KEY_WRAPPING` | KEK trong KMS/HSM | Wrap/Unwrap DEK | Khóa dữ liệu và khả năng phục hồi |
| `BACKUP_ENCRYPTION` | DEK/KEK dành cho backup | Encrypt/Decrypt/Wrap | Bản backup, archive |
| `INVOICE_SIGNATURE` | Private signing key RSA-PSS/ECDSA | Sign hóa đơn | Chữ ký hóa đơn |
| `SOFTWARE_RELEASE_SIGNATURE` | Private signing key | Sign artifact/manifest | Bản phát hành phần mềm |
| `ACCESS_TOKEN_SIGNATURE` | Private signing key hoặc HMAC key theo giao thức | Sign/MAC token | Token xác thực |
| `TLS_SERVER_AUTHENTICATION` | Private key và chứng thư phù hợp | Xác thực máy chủ theo TLS | Danh tính server trong phiên |
| `SESSION_KEY_AGREEMENT` | ECDH/X25519 private agreement key | Derive shared secret | Thiết lập bí mật phiên |
| `WEBHOOK_AUTHENTICATION` | HMAC key | Generate/Verify MAC | Thông điệp webhook |
| `PASSWORD_DERIVED_KEY_WRAP` | KEK dẫn xuất từ mật khẩu | Wrap/Unwrap DEK | Dữ liệu người dùng bị khóa bằng password |
| `RECOVERY_KEY_WRAP` | Recovery KEK trong KMS hoặc vật liệu recovery được phê duyệt | Unwrap/Wrap theo quy trình | Khôi phục DEK khi mất đường chính |
| `CA_CERTIFICATE_SIGNING` | CA private signing key | Ký chứng thư/CRL theo PKI | Hạ tầng tin cậy chứng thư |
| `TIMESTAMP_TOKEN_SIGNING` | TSA private signing key | Ký timestamp token | Bằng chứng thời gian |
| `DEVICE_ATTESTATION` | Private key phần cứng/thiết bị | Ký attestation theo giao thức | Danh tính và trạng thái thiết bị |

**Không tự suy ra** một KMS hỗ trợ tất cả những loại khóa và operation này. Cloud KMS, HSM, TPM, PKCS#11 token và keystore có bộ thuật toán, chính sách xuất khóa và quyền rất khác nhau.

### Trường hợp “một khóa nhiều mục đích”

Trong một số giao thức hoặc hệ thống kế thừa, nhiều operation có thể được cho phép trên cùng key material. Không nên tự động kết luận mọi trường hợp là sai, nhưng phải **ghi rõ các mục đích được phê duyệt**, phân tích tương tác thuật toán, ranh giới tin cậy và hậu quả khi compromise.

Với hệ thống mới, **tách khóa theo mục đích** thường là lựa chọn dễ kiểm soát hơn: signing key khác agreement key; signing key phát hành phần mềm khác signing key phát hành token; DEK khác KEK.

## 5. Purpose theo từng loại vật liệu và vòng đời khóa

### 5.1. DEK: khóa dùng mã hóa dữ liệu

Một DEK AES-GCM có purpose `DATA_AT_REST_ENCRYPTION` phải xác định **loại dữ liệu, tenant, phiên bản và phạm vi bản ghi**. Key inventory cần gắn DEK hoặc nhóm DEK với những ciphertext có thể cần giải mã khi key bị đình chỉ hoặc thay thế.

Ngoài Purpose, việc dùng AES-GCM đòi **nonce không lặp dưới cùng khóa** và kiểm tra tag/AAD. Mục đích đúng không bù được lỗi nonce hay lộ key material.

### 5.2. KEK: khóa dùng bảo vệ khóa khác

Một KEK có purpose `DEK_KEY_WRAPPING` không nên được sử dụng trực tiếp để mã hóa mọi bản ghi. Trong **envelope encryption**, DEK mã hóa dữ liệu; KEK bọc DEK và có vòng đời riêng.

Khi KEK thay từ `v1` sang `v2`, các wrapped DEK cũ có thể vẫn cần `v1` để giải bọc hoặc rewrap có kiểm chứng. Vì vậy mục đích `DEK_KEY_WRAPPING` gắn với **khả năng khôi phục dữ liệu lịch sử**, không chỉ chức năng mã hóa hiện tại.

### 5.3. Private signing key

Signing key cần chỉ rõ **đối tượng ký và chính sách phê duyệt**, không chỉ ghi `SIGN`.

Ví dụ:

~~~text
purpose = SOFTWARE_RELEASE_SIGNATURE
scope   = product:billing-service; channel:production
caller  = approved-release-signing-workload
input   = manifest/digest từ pipeline đã được phê duyệt
~~~

Ngay cả khi private key **non-exportable** trong HSM, kẻ tấn công chiếm quyền `Sign` vẫn có thể biến dịch vụ thành **signing oracle** nếu không kiểm tra nội dung nghiệp vụ.

### 5.4. HMAC key

Một HMAC key dùng `WEBHOOK_AUTHENTICATION` nên được tách theo đối tác, tenant hoặc nhóm rủi ro khi phù hợp. Vì hai bên giữ cùng khóa có thể tạo MAC, Purpose còn phải xác định **nhóm chủ thể được chia sẻ bí mật** và cơ chế thu hồi/phân phối khi một bên bị xâm nhập.

### 5.5. ECDH/X25519 key

`SESSION_KEY_AGREEMENT` dành cho thỏa thuận khóa, không phải ký số. Với **static agreement key**, inventory có thể ghi key ID, owner, peer trust và cryptoperiod. Với **ephemeral ECDHE key**, thông thường cần quản lý **chính sách và sự kiện phiên** thay vì tạo một record quản trị lâu dài cho mỗi private scalar.

ECDH thuần túy **không tự xác thực peer**; Purpose phải liên kết với giao thức có xác thực và KDF đúng, ví dụ TLS 1.3 ở chế độ phù hợp.

### 5.6. Khóa dẫn xuất từ mật khẩu

Một **password verifier** không phải DEK/KEK và không nên được dùng để giải mã dữ liệu. Nếu password dùng dẫn xuất KEK để bọc DEK, inventory nên mô tả purpose `PASSWORD_DERIVED_KEY_WRAP` cùng đường recovery, KDF parameters và trách nhiệm bảo vệ. **Không ghi password, KEK dẫn xuất hoặc recovery secret dạng rõ** vào inventory.

## 6. Purpose phải cụ thể đến mức nào?

Nếu trường Purpose quá ngắn, ví dụ `ENCRYPTION`, nó không thể phân biệt khóa dùng cho **database**, **backup**, **webhook** hay **wrapping**. Nếu quá dài thành văn bản tùy tiện cho từng team, hệ thống khó tìm kiếm, phân quyền và kiểm toán.

Một thiết kế thực tế có thể tách thành **mục đích có mã chuẩn** và **ngữ cảnh**:

~~~text
purposeId          = DATA_AT_REST_ENCRYPTION
purposeDescription = Mã hóa hồ sơ hóa đơn đã chốt
businessService    = billing-platform
dataClassification = CONFIDENTIAL
dataDomain         = invoice-records
tenantScope        = tenant-A
environment        = production
allowedOperations  = [Encrypt, Decrypt]
keyType            = symmetric
algorithm          = AES-256-GCM
~~~

Như vậy:

- **`purposeId`** hỗ trợ policy, phân loại và báo cáo.
- **`purposeDescription`** giải thích ý nghĩa nghiệp vụ.
- **`dataDomain`, `tenantScope`, `environment`** giới hạn phạm vi.
- **`allowedOperations`**, **`keyType`**, **`algorithm`** kiểm soát khả năng kỹ thuật.
- Các trường **owner, approval, state, cryptoperiod** thuộc governance và lifecycle.

### Quy tắc đặt tên Purpose

1. Dùng **mã ổn định**, nhất quán chữ hoa/gạch dưới hoặc quy ước của tổ chức.
2. Tên nói rõ **đối tượng và hành vi** khi cần, ví dụ `INVOICE_SIGNATURE` thay vì `SIGN`.
3. Không dùng mô tả quá chung như `MISC`, `GENERAL_SECURITY`, `TEST` cho production.
4. Nếu scope thay đổi nhiều, lưu **trường riêng** thay vì nhồi toàn bộ vào mã Purpose.
5. Có **version taxonomy** để biết một mã cũ được hiểu thế nào trong kiểm toán lịch sử.
6. Không xem tên key hoặc alias là nguồn chân lý duy nhất của Purpose.

**Tên resource như `prod-key-7` không phải Purpose.** Chỉ đổi tên key thành `payment-signing` cũng không thay đổi được key usage, IAM hay bằng chứng phê duyệt.

## 7. Mô hình dữ liệu key inventory có Purpose

Một bản ghi inventory không chỉ là danh sách tên khóa. Nó phải cho biết **lý do tồn tại, vị trí bảo vệ, các bên có quyền và phụ thuộc vòng đời**.

### Ví dụ YAML — khóa ký hóa đơn

~~~yaml
inventoryRecordVersion: "1"
keyId: "billing-invoice-signing-v2"
keyVersion: "v2"
environment: "production"
serviceName: "billing-platform"
purpose:
  id: "INVOICE_SIGNATURE"
  taxonomyVersion: "2026-01"
  description: "Ký các hóa đơn đã được phê duyệt"
  dataDomain: "invoice-documents"
  allowedOperations:
    - "Sign"
  prohibitedUses:
    - "JWT issuance"
    - "Software release signing"
    - "Key agreement"
crypto:
  keyType: "EC private signing key"
  algorithm: "ECDSA P-256 with SHA-256"
  keyMaterialLocation: "HSM key handle, không chứa private key"
  exportPolicy: "NON_EXPORTABLE"
governance:
  owner: "billing-key-owner"
  custodian: "security-key-custodian"
  approvedWorkloads:
    - "billing-invoice-signer"
  approvalReference: "approval-id"
  policyVersion: "signing-policy-v4"
lifecycle:
  state: "ACTIVE"
  activatedAtUtc: "2026-11-01T00:00:00Z"
  newUseUntilUtc: "2027-11-01T00:00:00Z"
  rotationPlanReference: "rotation-plan-id"
  legacyVerificationPolicy: "verify-historical-invoices"
audit:
  keyCreationEvent: "audit-event-id"
  currentPolicyReview: "review-id"
~~~

Đây là **schema minh họa**, không phải một tài nguyên KMS có thể tạo trực tiếp. **Metadata không tự cấp quyền, không tự ký dữ liệu và không chứng minh trạng thái HSM là chính xác**. Mọi trường cần được kiểm tra với nguồn có thẩm quyền.

### Ví dụ YAML — KEK cho DEK hóa đơn

~~~yaml
keyId: "billing-dek-wrapping-kek-v3"
keyVersion: "v3"
purpose:
  id: "DEK_KEY_WRAPPING"
  description: "Bọc DEK cho dữ liệu hóa đơn production"
  dataDomain: "invoice-records"
  allowedOperations:
    - "WrapKey"
    - "UnwrapKey"
  explicitlyNotFor:
    - "Direct record encryption"
    - "Document signing"
crypto:
  keyType: "symmetric KMS-managed key"
  algorithm: "Cơ chế key wrap/KMS được phê duyệt"
  keyMaterialLocation: "KMS key resource"
governance:
  owner: "billing-data-protection-owner"
  custodian: "platform-kms-team"
  approvedWorkloads:
    - "billing-encryption-service"
lifecycle:
  state: "ACTIVE"
  oldWrappedDekHandling: "Theo retention và kế hoạch rewrap"
dependencies:
  inventoryMapping: "DEK version -> wrappedKey -> KEK version"
~~~

**Không lưu raw DEK, KEK, HMAC secret hay private key** trong key inventory. Các bản bọc, key ID và metadata có thể cần lưu ở tầng dữ liệu, nhưng phải áp dụng quyền riêng, integrity và chính sách sao lưu tương ứng.

### Những field thường tối thiểu

| Nhóm thông tin | Trường gợi ý | Vì sao cần |
| --- | --- | --- |
| **Định danh** | `keyId`, `keyVersion`, `providerResourceId`, `alias` | Nhận đúng vật liệu và phiên bản |
| **Purpose** | `purposeId`, `description`, `taxonomyVersion` | Xác định mục tiêu đã phê duyệt |
| **Phạm vi** | `service`, `environment`, `tenant`, `dataDomain` | Chặn dùng nhầm bối cảnh |
| **Mật mã** | `keyType`, `algorithm`, `keyUsage`, `exportPolicy` | Kiểm tra khả năng kỹ thuật |
| **Quản trị** | `owner`, `custodian`, `policyRef`, `approvalRef` | Gắn trách nhiệm và quyết định |
| **Vòng đời** | `state`, `createdAt`, `activatedAt`, `newUseUntil`, `rotationPlan` | Quản lý sử dụng và retirement |
| **Phụ thuộc** | `dependentData`, `signingClients`, `wrappedDekVersions` | Tránh hủy/đổi sai |
| **Kiểm toán** | `createdBy`, `lastReview`, `lastUse`, `auditCorrelation` | Điều tra và chứng minh tuân thủ |

**Không bắt buộc tất cả nhà cung cấp hoặc mọi khóa phải có chính xác tập field này.** Inventory cần phân biệt **bắt buộc**, **không áp dụng** và **chưa biết** thay vì điền giá trị giả cho đủ form.

## 8. Purpose phải được cưỡng chế ở đâu?

Mục đích được khai báo là **chính sách quản trị**. Việc thực thi phân tán ở nhiều lớp:

~~~mermaid
flowchart TD
    Owner[Key owner và người phê duyệt] --> Policy[Định nghĩa Purpose + scope + key usage]
    Policy --> Inventory[Key inventory và lifecycle registry]
    Inventory --> Control[Control plane: activation, rotation, policy]
    App[Ứng dụng yêu cầu Sign/Encrypt/Unwrap] --> Business[Kiểm tra loại dữ liệu và phê duyệt]
    Business --> Gate[Purpose + tenant + environment + state gate]
    Inventory --> Gate
    Gate -->|Sai Purpose/quyền| Deny[Từ chối và audit]
    Gate -->|Đúng policy| KMS[KMS/HSM: kiểm tra principal + operation + key state]
    KMS -->|Allowed| Crypto[Cryptographic operation]
    KMS -->|Denied| Deny
    Crypto --> Audit[Audit: key version, purpose, caller, result]
    Deny --> Audit
    Control --> KMS
~~~

### 8.1. Tầng nghiệp vụ

Kiểm tra đối tượng cần bảo vệ. Ví dụ key `INVOICE_SIGNATURE` chỉ được ký digest của **hóa đơn đã chốt và được phê duyệt**, không ký bất kỳ byte nào do client gửi lên.

KMS/HSM thường không hiểu hóa đơn nào đã được duyệt, nên **non-exportable private key không thay thế business approval**.

### 8.2. Tầng IAM/KMS/HSM

Cấp **least privilege** cho danh tính thực hiện operation trên đúng key resource. Tách người quản trị policy khỏi người dùng khóa. Chặn xuất private key nếu có thể; đánh giá API `Sign`, `Decrypt`, `DeriveKey`, `GenerateMac`, `Wrap/Unwrap` mà provider hỗ trợ.

**KMS có thể không hiểu `purposeId`**. Khi đó tổ chức phải ánh xạ Purpose thành danh tính, resource, IAM condition, key policy, application route và quy trình kiểm tra cụ thể. Nếu tài khoản ứng dụng gọi được trực tiếp API bỏ qua gateway, chỉ gắn Purpose ở gateway là **không đủ**.

### 8.3. Tầng dữ liệu và giao thức

Các giao thức có thể có ràng buộc bổ sung: **AAD, key ID/version, algorithm suite, canonical serialization, transcript**, mục đích cert/key usage và phân tách hướng truyền. Tất cả phải được kiểm tra đúng chuẩn.

Không nên đưa thông tin như `purpose=invoice-sign` vào AAD hoặc một tag JSON rồi cho rằng đã có **authorization**. AAD chỉ được bảo vệ toàn vẹn nếu AEAD được triển khai đúng; quyền sử dụng khóa vẫn phải được xác nhận độc lập.

### 8.4. Kiểm toán liên tục

Inventory ghi mục đích **dự kiến**; audit xác nhận hoạt động **thực tế** có phù hợp không. Cần đối chiếu các lượt dùng key với purpose, principal, key state, phiên bản policy và phạm vi dữ liệu, thay vì chỉ đo số lượng API call.

## 9. Ánh xạ Purpose vào chuẩn và metadata giao thức

Một số định dạng có trường gần giống Purpose nhưng **không biểu diễn đầy đủ ngữ cảnh nghiệp vụ**.

| Cơ chế | Trường/khái niệm liên quan | Giới hạn |
| --- | --- | --- |
| **X.509 certificate** | `KeyUsage`, `ExtendedKeyUsage (EKU)`, certificate policies | Ràng buộc mục đích chứng thư/khóa theo PKI, **không thay** phê duyệt ký hóa đơn hay policy ứng dụng |
| **JWK/JWKS** | `use` như `sig`/`enc`, `key_ops` như `sign`/`verify`/`encrypt` | Là metadata khai báo/đặc tả sử dụng, phải được bên nhận và policy thực thi |
| **PKCS#11/HSM** | Key attributes và cơ chế như `CKA_SIGN`, `CKA_DECRYPT`, `CKA_DERIVE` khi được hỗ trợ | Giới hạn thao tác token, nhưng không tự biết invoice/tenant cụ thể |
| **Cloud KMS** | Key type, key usage, supported operations, IAM/grants, key state | Field cụ thể và khả năng chặn theo operation tùy nhà cung cấp |
| **Java JCA/JCE** | `Key` algorithm, `Signature`, `Cipher`, `KeyAgreement`, keystore alias | Không tự kiểm tra mục đích nghiệp vụ chỉ từ thuật toán và alias |
| **Audit/CMDB/inventory nội bộ** | `purposeId`, owner, environment, data scope, approval | Cần đồng bộ và kiểm chứng với resource thật |

### X.509 KeyUsage không phải Purpose đầy đủ

Một chứng thư có thể khai báo `digitalSignature`. Điều đó **không** có nghĩa private key có quyền ký mọi tài liệu của tổ chức. EKU như `serverAuth` giúp các bên kiểm tra ngữ cảnh sử dụng chứng thư TLS, nhưng các trường PKI không thay cho IAM, chính sách phát hành và xác nhận danh tính tại tầng ứng dụng.

**TLS 1.3** có thể dùng private authentication key để ký/xác thực handshake và ECDHE ephemeral key để thỏa thuận bí mật phiên. Đừng ghi cả hai là “TLS encryption key” rồi dùng chung vật liệu.

### JWK `use` và `key_ops`

Trong JWK, `use` mô tả nhóm mục đích như chữ ký hoặc mã hóa; `key_ops` có thể mô tả operation cụ thể. Chúng **không phải bằng chứng rằng bên phát hành khóa đáng tin**. Bên xác minh JWT phải kiểm soát **issuer, audience, thuật toán được chấp nhận, nguồn JWKS tin cậy và key ID**, không chọn một public key bất kỳ chỉ vì nó có `use=sig`.

### PKCS#11 và nhà cung cấp KMS

Các thuộc tính như `CKA_SIGN` hoặc `CKA_DERIVE` có thể giúp chặn sai loại phép toán ở HSM. Nhưng một HSM không tự hiểu “chữ ký này thuộc hóa đơn tenant B”, trừ khi giải pháp có thêm logic và chính sách ràng buộc đầu vào theo thiết kế. **Purpose cần cả business gate và cryptographic operation gate.**

## 10. Java 11+: ví dụ policy gate theo Purpose

Ví dụ sau minh họa **kiểm tra Purpose + operation + principal + environment + tenant + trạng thái** trước khi gọi phép toán mật mã. Đây là code giáo dục sử dụng **metadata**, **không tạo khóa thật, không gọi KMS/HSM**. Mục tiêu là nhìn rõ vì sao hai signing key có cùng thuật toán không thể được hoán đổi tùy ý.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.EnumSet;
import java.util.Objects;

public final class KeyPurposePolicyDemo {

    enum Purpose {
        INVOICE_SIGNATURE,
        ACCESS_TOKEN_SIGNATURE,
        RECORD_ENCRYPTION,
        DEK_WRAPPING,
        WEBHOOK_MAC,
        SESSION_AGREEMENT
    }

    enum Operation {
        SIGN, VERIFY, ENCRYPT, DECRYPT,
        WRAP, UNWRAP, GENERATE_MAC, VERIFY_MAC, DERIVE_KEY
    }

    enum State {
        PRE_ACTIVATION, ACTIVE, SUSPENDED,
        DEACTIVATED, COMPROMISED, DESTROYED
    }

    static final class KeyMetadata {
        final String id;
        final Purpose purpose;
        final String environment;
        final String tenant;
        final String approvedPrincipal;
        final State state;
        final Instant activeFrom;
        final Instant newUseUntil;
        final EnumSet<Operation> permitted;

        KeyMetadata(
                String id, Purpose purpose, String environment,
                String tenant, String approvedPrincipal, State state,
                Instant activeFrom, Instant newUseUntil,
                EnumSet<Operation> permitted) {

            if (id == null || id.isEmpty() || purpose == null
                    || environment == null || tenant == null
                    || approvedPrincipal == null || state == null
                    || activeFrom == null || newUseUntil == null
                    || !activeFrom.isBefore(newUseUntil)
                    || permitted == null) {
                throw new IllegalArgumentException("Invalid key metadata");
            }
            this.id = id;
            this.purpose = purpose;
            this.environment = environment;
            this.tenant = tenant;
            this.approvedPrincipal = approvedPrincipal;
            this.state = state;
            this.activeFrom = activeFrom;
            this.newUseUntil = newUseUntil;
            this.permitted = permitted.clone();
        }
    }

    static void requireAuthorizedNewUse(
            KeyMetadata key, Purpose requestedPurpose, Operation operation,
            String principal, String environment, String tenant, Clock clock) {

        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(clock, "clock");

        // Fail closed nếu thiếu/sai mục đích hoặc principal/scope.
        if (requestedPurpose == null || requestedPurpose != key.purpose
                || operation == null
                || !key.approvedPrincipal.equals(principal)
                || !key.environment.equals(environment)
                || !key.tenant.equals(tenant)) {
            throw new SecurityException("Purpose or scope denied");
        }
        if (key.state != State.ACTIVE
                || !key.permitted.contains(operation)) {
            throw new SecurityException("Key state or operation denied");
        }

        Instant now = clock.instant();
        if (now.isBefore(key.activeFrom)
                || !now.isBefore(key.newUseUntil)) {
            throw new SecurityException("Outside new-use cryptoperiod");
        }
    }

    public static void main(String[] args) {
        Clock demo = Clock.fixed(
                Instant.parse("2030-01-15T10:00:00Z"), ZoneOffset.UTC);
        Instant from = Instant.parse("2030-01-01T00:00:00Z");
        Instant until = Instant.parse("2031-01-01T00:00:00Z");

        KeyMetadata invoiceKey = new KeyMetadata(
                "billing-invoice-sign-v2",
                Purpose.INVOICE_SIGNATURE,
                "production", "tenant-a", "billing-invoice-signer",
                State.ACTIVE, from, until, EnumSet.of(Operation.SIGN));

        requireAuthorizedNewUse(
                invoiceKey, Purpose.INVOICE_SIGNATURE, Operation.SIGN,
                "billing-invoice-signer", "production", "tenant-a", demo);
        System.out.println("Invoice signing: allowed");

        try {
            requireAuthorizedNewUse(
                    invoiceKey, Purpose.ACCESS_TOKEN_SIGNATURE, Operation.SIGN,
                    "billing-invoice-signer", "production", "tenant-a", demo);
            throw new AssertionError("Wrong purpose must fail");
        } catch (SecurityException expected) {
            System.out.println("Token signing with invoice key: denied");
        }

        try {
            requireAuthorizedNewUse(
                    invoiceKey, Purpose.INVOICE_SIGNATURE, Operation.ENCRYPT,
                    "billing-invoice-signer", "production", "tenant-a", demo);
            throw new AssertionError("Wrong operation must fail");
        } catch (SecurityException expected) {
            System.out.println("Encrypt with invoice key: denied");
        }

        try {
            requireAuthorizedNewUse(
                    invoiceKey, Purpose.INVOICE_SIGNATURE, Operation.SIGN,
                    "billing-invoice-signer", "production", "tenant-b", demo);
            throw new AssertionError("Wrong tenant must fail");
        } catch (SecurityException expected) {
            System.out.println("Cross-tenant signing: denied");
        }
    }
}
~~~

**Kết quả dự kiến:**

~~~text
Invoice signing: allowed
Token signing with invoice key: denied
Encrypt with invoice key: denied
Cross-tenant signing: denied
~~~

### Điều ví dụ chứng minh

- Hai yêu cầu cùng `SIGN` có thể được xử lý khác nhau theo **business Purpose**.
- **Tenant, environment và principal** là một phần của phạm vi, không thể suy ra từ tên thuật toán.
- Key chỉ được dùng trong trạng thái `ACTIVE`, thời hạn mới và operation đã cho phép.
- Kiểm tra không dựa đơn thuần vào `keyId` hoặc alias.

### Những gì phải bổ sung trong production

1. **Nguồn metadata đáng tin**: caller không được tự tạo object KeyMetadata với Purpose giả.
2. **Xác thực thực tế principal**, tenant và nội dung yêu cầu; không tin ba chuỗi do client gửi.
3. **Business approval**: một invoice phải đã được phê duyệt trước khi được ký.
4. **IAM và key policy ở KMS/HSM**: service không được bỏ qua policy gate để gọi thẳng provider.
5. **Key version/revision** và kiểm soát race/TOCTOU: key có thể bị suspend sau lúc app đọc metadata.
6. **Loại khóa/thuật toán** tương thích với operation, và key usage thực tế tại provider.
7. **Quy tắc cho xử lý dữ liệu lịch sử**: ví dụ `Decrypt` của DEK deactivated có thể vẫn được cho phép theo một policy riêng; hàm trên chỉ xét **new use**.
8. **Audit có toàn vẹn** và kiểm tra âm tính để chứng minh các đường dùng sai bị chặn.

**Không dùng mã giả lập này làm bộ phân quyền duy nhất.** Nó có giá trị minh họa cách tách business Purpose khỏi operation, nhưng không có khả năng bảo vệ vật liệu khóa.

## 11. Purpose và vòng đời: từ đề xuất đến hủy

Purpose phải được xác định **trước khi tạo khóa**, được kiểm tra khi cấp phát và được giữ làm tham chiếu khi khóa chuyển trạng thái.

| Giai đoạn | Trách nhiệm liên quan Purpose | Bằng chứng |
| --- | --- | --- |
| **Đề xuất** | Định nghĩa mục đích, dữ liệu, nghiệp vụ, rủi ro, cryptoperiod | Approval, data classification, key owner |
| **Tạo** | Chọn key type/algorithm/entropy theo Purpose | Key ID, algorithm, provenance, KMS/HSM event |
| **Pre-activation** | Kiểm tra usage, IAM, scope, client readiness, backup | Negative tests, policy review, sign-off |
| **Active** | Cho phép đúng operation, principal, data scope | KMS logs, application audit, compliance checks |
| **Suspended** | Chặn sử dụng trong lúc điều tra hoặc theo chính sách | Incident record, deny evidence, cache handling |
| **Deactivated** | Ngừng bảo vệ dữ liệu mới; xử lý legacy theo Purpose | Dependency inventory và retention |
| **Compromised** | Đánh giá dữ liệu/chữ ký/tag/phiên theo Purpose | Blast-radius analysis, rotation/revocation plan |
| **Destroyed** | Hủy vật liệu sau khi hết phụ thuộc và lưu giữ | Destruction approval và kiểm chứng backup |

### Purpose có được thay đổi sau khi khóa đã tạo?

**Không nên thay đổi tùy tiện.** Ví dụ đổi `purposeId` của một private signing key từ `INVOICE_SIGNATURE` thành `ACCESS_TOKEN_SIGNATURE` trong DB **không tạo ra một khóa mới**, không thu hồi các chữ ký đã ký và không thay đổi nguy cơ cross-protocol.

Nếu nhu cầu thay đổi về bản chất, cách an toàn thường là:

1. **Đề xuất purpose mới** và rà soát thuật toán/key usage/rủi ro.
2. **Tạo key material mới** với owner, scope và quyền tương ứng, thay vì tái nhãn khóa cũ.
3. Chuyển client/đối tác sang public key/chứng thư hoặc key version mới.
4. Xử lý dữ liệu, chữ ký, MAC và ciphertext cũ theo retention.
5. Ngừng dùng khóa cũ cho nghiệp vụ mới, sau đó hủy đúng chính sách.

Một thay đổi **mô tả thuần túy** như sửa lỗi chính tả hoặc bổ sung tên team có thể được quản trị bằng metadata revision, nhưng vẫn phải có lịch sử chỉnh sửa để auditor hiểu **Purpose nào đã được phê duyệt tại thời điểm sử dụng**.

### Trạng thái và Purpose khác nhau

Key ở `ACTIVE` **chưa đủ** để được dùng: operation phải đúng Purpose. Key ở `SUSPENDED` phải chặn cả những operation vốn hợp lệ theo Purpose. Key `DEACTIVATED` có thể vẫn cần `Decrypt` dữ liệu cũ hoặc xác minh bằng public key tùy thiết kế.

Tránh kết luận “key đã active nên mọi việc sử dụng nó đều được phép”.

## 12. Purpose trong rotation, rewrap và khôi phục dữ liệu

### 12.1. Rotation signing key

Khi thay `billing-invoice-signing-v1` bằng `v2`, Purpose `INVOICE_SIGNATURE` được giữ nhưng **key material, key ID/version, chứng thư và chính sách** phải được quản trị như một phiên bản mới. Phân phối thông tin xác minh trước khi ký hóa đơn mới, và giữ khả năng kiểm tra **chữ ký lịch sử** bằng public key/chứng thư `v1` theo retention.

Việc kết thúc quyền `Sign` của `v1` không tự hủy giá trị kiểm tra chữ ký cũ. Đồng thời, nếu `v1` bị compromise, cần đánh giá các chữ ký liên quan theo bằng chứng thời gian và PKI, chứ không chỉ nhìn kết quả phép toán `Verify`.

### 12.2. Rotation KEK

Khóa có Purpose `DEK_KEY_WRAPPING` thường có hai hoạt động liên quan: bọc DEK mới và giải bọc DEK cũ. Khi `kek-v2` active để **wrap mới**, `kek-v1` có thể phải được giữ với quyền **unwrap** giới hạn đến khi hoàn thành rewrap.

**Rewrap** nghĩa là giải bọc một DEK dưới KEK cũ rồi bọc DEK đó dưới KEK mới theo quy trình được phép; ciphertext dữ liệu sử dụng DEK thường có thể giữ nguyên. Nhưng nếu **DEK đã lộ**, rewrap không khôi phục tính bí mật của dữ liệu cũ.

### 12.3. Rotation DEK

Nếu Purpose `DATA_AT_REST_ENCRYPTION`, thay DEK có thể yêu cầu mã hóa lại dữ liệu để tránh tiếp tục phụ thuộc khóa cũ. Ngoài key version, inventory cần ghi **phụ thuộc giữa dữ liệu, wrapped DEK, KEK và thuật toán/nonce** để thực hiện rotation an toàn.

### 12.4. Recovery purpose

**Recovery key** phải có Purpose cụ thể, chẳng hạn `RECOVERY_KEY_WRAP`, và không được mở rộng thành quyền giải mã tùy ý. Phục hồi qua KMS/HSM nên yêu cầu chứng thực/phê duyệt phù hợp, giới hạn **ai, dữ liệu nào, trong bao lâu**, ghi audit và thu hồi quyền break-glass sau sử dụng.

Nếu một dịch vụ tuyên bố dữ liệu là **end-to-end/zero-knowledge**, việc có recovery KEK phía server có thể thay đổi đáng kể mô hình bí mật. Purpose và quyền của recovery path phải được mô tả chính xác cho người dùng/tổ chức.

## 13. Quy trình cấp Purpose và phân tách trách nhiệm

### Ai có quyền quyết định Purpose?

| Vai trò | Trách nhiệm | Hạn chế |
| --- | --- | --- |
| **Key owner** | Phê duyệt Purpose, dữ liệu/mục đích, risk tier và cryptoperiod | Không tự động có quyền dùng key material |
| **Key custodian** | Tạo/lưu/rotate key, cấu hình KMS/HSM theo Purpose đã duyệt | Không tự sửa Purpose để cấp quyền cho chính mình |
| **Application owner** | Định nghĩa use case, data scope, workflow và dependency | Không tự phê duyệt vượt yêu cầu an ninh |
| **Security reviewer** | Kiểm tra thuật toán, separation of duties, IAM, blast radius | Không dùng phê duyệt để bypass technical gate |
| **IAM/KMS administrator** | Chuyển Purpose thành quyền/key policy/provider settings | Không tự mở quyền `Decrypt/Sign` ngoài phê duyệt |
| **Auditor** | Đối chiếu metadata, sử dụng thực tế, thay đổi và retention | Không sửa dữ liệu kiểm toán hoặc lấy key material |

### Luồng phê duyệt đề xuất

~~~mermaid
sequenceDiagram
    participant App as Application owner
    participant Owner as Key owner
    participant Sec as Security reviewer
    participant KM as Key custodian / KMS
    participant Inv as Inventory / Control plane
    participant Run as Workload
    App->>Owner: Đề xuất Purpose + data scope + operations
    Owner->>Sec: Yêu cầu rà soát rủi ro và thuật toán
    Sec-->>Owner: Điều kiện và khuyến nghị
    Owner->>Inv: Phê duyệt purposeId/version
    Inv->>KM: Yêu cầu tạo khóa theo policy
    KM->>KM: Sinh/bảo vệ key material phù hợp
    KM-->>Inv: Key ID/version + metadata, không gửi secret
    Inv->>KM: Kích hoạt quyền đã được phê duyệt
    Run->>KM: Cryptographic operation với key ID
    KM-->>Inv: Audit event (caller, operation, result)
    Inv->>Owner: Báo cáo sử dụng và rà soát định kỳ
~~~

Sơ đồ minh họa phân tách trách nhiệm. **Phê duyệt trong inventory không tự bảo đảm quyền IAM đã khớp**; phải có kiểm thử chính sách thực tế và rà soát ngoại lệ.

### Trường hợp khẩn cấp

Nếu cần tạm đình chỉ hoặc thay khóa gấp, quyền incident response phải được định trước, có audit và phê duyệt hậu kiểm theo chính sách. Không dùng khẩn cấp để cho phép một khóa ngoài Purpose ký mọi nội dung hoặc giải mã mọi dữ liệu mà không giới hạn.

## 14. Đối soát Purpose với key thực tế

Một inventory lâu ngày không được đối soát có thể không còn phản ánh môi trường. Ví dụ alias đã trỏ sang key khác, service account có grant mới hoặc một ứng dụng vẫn dùng key cũ ngoài phạm vi.

### Quy trình đối soát

1. **Lập danh sách key resources thực tế** từ KMS/HSM/keystore phù hợp theo quyền đã phê duyệt.
2. Ghép với **key ID/version, resource ID và alias history** trong inventory; không dựa duy nhất vào tên hiển thị.
3. So sánh **algorithm, type, state, key usage, export policy** giữa inventory và provider.
4. Kiểm tra **IAM, key policy, grants và principal** có khớp Purpose và data scope đã phê duyệt không.
5. Đối chiếu **audit use**: operation nào, từ workload nào, trên key version nào, ở thời điểm nào.
6. Đối soát **dependency**: dữ liệu, chứng thư, artifact, partner, webhook và wrapped DEK còn liên quan.
7. Ghi nhận **orphan key**, key không có Purpose, key có Purpose mơ hồ, key quá hạn rotation hoặc key bị dùng ngoài mục đích.
8. Mở issue/incident, chỉ định owner và thời hạn xử lý; không tự xóa key chưa rõ dependency.

### Những tín hiệu bất thường nên cảnh báo

| Tín hiệu | Khả năng rủi ro | Hành động đầu tiên |
| --- | --- | --- |
| Key `INVOICE_SIGNATURE` được service phát JWT gọi `Sign` | Dùng sai Purpose hoặc principal bị chiếm | Chặn grant, điều tra yêu cầu và chữ ký đã tạo |
| KEK có lưu lượng `Encrypt` dữ liệu trực tiếp ngoài thiết kế | Dùng sai vai trò khóa | Kiểm tra policy và phạm vi dữ liệu |
| Không tìm thấy owner hoặc approval cho key active | Thiếu trách nhiệm và kiểm soát | Đánh dấu cần review, hạn chế thay đổi rủi ro |
| Key production được gọi từ staging | Vượt môi trường | Kiểm tra danh tính, network, IAM và credential |
| Alias trỏ sang phiên bản khác nhưng inventory chưa cập nhật | Sai key version/cutover | Đối soát routing và dependency |
| Còn `Sign` sau khi key deactivated | Vi phạm vòng đời | Cô lập, kiểm tra cache/grant và audit |
| Có wrapped DEK phụ thuộc KEK chuẩn bị hủy | Nguy cơ mất dữ liệu | Dừng lịch hủy, lập kế hoạch rewrap/retention |

### Phân biệt “không có log” với “không có sử dụng”

Không phải mọi lần dùng raw DEK trong bộ nhớ đều có log KMS. Một ứng dụng có thể giải bọc DEK một lần rồi dùng hàng nghìn lần. Vì vậy đánh giá Purpose cần kết hợp **log KMS, log ứng dụng, cache, key version và telemetry nghiệp vụ** ở mức phù hợp. Không tuyên bố “key không dùng” chỉ vì không thấy API call gần đây.

## 15. Tình huống thiết kế: Billing có ba mục đích khác nhau

Giả sử `billing-platform` xử lý hồ sơ hóa đơn, phát hành chữ ký số và cung cấp webhook cho đối tác. Nhóm phát triển ban đầu đề xuất dùng “một master key cho tiện” và đặt Purpose chung là `BILLING_SECURITY`.

Thiết kế đó khó vận hành vì các mục đích có **mô hình bí mật và quyền khác nhau**.

### Phân tách khóa đề xuất

| Nhu cầu | Purpose | Key loại gì? | Quyền chính | Phụ thuộc cần theo dõi |
| --- | --- | --- | --- | --- |
| Mã hóa hồ sơ hóa đơn | `DATA_AT_REST_ENCRYPTION` | DEK AES-GCM | Encrypt/Decrypt | Ciphertext, nonce, AAD, key version |
| Bọc DEK | `DEK_KEY_WRAPPING` | KEK trong KMS | Wrap/Unwrap | Wrapped DEK và kế hoạch rewrap |
| Ký hóa đơn | `INVOICE_SIGNATURE` | Private signing key HSM | Sign theo workflow | Public key/chứng thư, verifier |
| Xác thực webhook | `WEBHOOK_AUTHENTICATION` | HMAC key theo đối tác | Generate/Verify MAC | Partner key version, retry, rotation |
| Ký access token | `ACCESS_TOKEN_SIGNATURE` | Signing key của identity service | Sign token | Issuer, audience, JWKS, expiration |

~~~mermaid
flowchart TD
    Invoice[Hóa đơn sau khi chốt] --> AEAD[AES-GCM với DEK có Purpose DATA_AT_REST]
    AEAD --> C[(Ciphertext + nonce + AAD)]
    DEK[DEK ngẫu nhiên] --> AEAD
    KEK[KMS KEK có Purpose DEK_KEY_WRAPPING] --> W[Wrap / Unwrap DEK]
    DEK --> W
    W --> C
    Invoice --> Approval[Kiểm tra phê duyệt nghiệp vụ]
    Approval --> Sign[HSM signing key: INVOICE_SIGNATURE]
    Sign --> Signature[Chữ ký và thông tin xác minh]
    Event[Webhook event] --> MAC[HMAC key: WEBHOOK_AUTHENTICATION]
    MAC --> Tag[Tag cho đối tác]
    Auth[Identity service] --> Token[Key: ACCESS_TOKEN_SIGNATURE]
    Token --> JWT[JWT được phát hành]
~~~

### Điều gì xảy ra khi một khóa bị lộ?

- Nếu **HMAC key của đối tác A** bị lộ, tập trung xử lý webhook của đối tác đó; không nhất thiết phải thay signing key hóa đơn.
- Nếu **signing key hóa đơn** bị lộ, đánh giá chữ ký và chứng thư hóa đơn; không dùng nó để xoay hoặc khôi phục DEK.
- Nếu **KEK** bị nghi lộ, đánh giá các wrapped DEK và đường unwrap; **rewrap** có thể cần, nhưng nếu DEK đã bị lấy thì phải xét mã hóa lại.
- Nếu **DEK** bị lộ, dữ liệu được mã hóa bởi chính DEK đó có thể bị ảnh hưởng dù KEK chưa lộ.
- Nếu **key ký JWT** bị lộ, xử lý chính sách tin cậy token, JWKS, token đã phát và session; không nhầm với quy trình thu hồi chứng thư ký hóa đơn.

**Purpose giúp giới hạn blast radius và xác định runbook đúng**, nhưng chỉ có hiệu quả khi thực tế không dùng chung key material hoặc quyền giữa các mục đích.

## 16. Xử lý sự cố: phát hiện khóa bị dùng sai Purpose

Tình huống: audit ghi nhận `identity-token-issuer` gọi `Sign` trên key có Purpose `INVOICE_SIGNATURE`. Có thể do cấu hình key ID sai, IAM quá rộng, bug chọn alias hoặc tài khoản bị chiếm.

### Runbook khái niệm

1. **Xác nhận thực thể:** Key ID/version thật, Purpose/approval tại thời điểm xảy ra, principal gọi API, operation, thuật toán và kết quả.
2. **Cô lập đường sai:** Tạm dừng grant hoặc route cho phép gọi `Sign` trái Purpose; nếu nghi compromise nghiêm trọng, thực hiện suspend key theo quy trình.
3. **Bảo toàn log:** Ghi request ID, artifact/digest, thời gian, nguồn, policy version, key state và những lần gọi liên quan; không log private key hay token bí mật.
4. **Xác định nguyên nhân:** Sai mapping alias, thiếu tenant check, copy nhầm credential, phân quyền rộng hay attacker có chủ ý.
5. **Đánh giá đầu ra đã tạo:** Có chữ ký nào trên JWT/dữ liệu ngoài scope không? Bên nào đang chấp nhận public key của khóa? Có hậu quả phát hành hay pháp lý?
6. **Khắc phục:** Tách signing key nếu cần, sửa policy IAM, key-selection logic, negative tests và hồ sơ Purpose. Nếu key material đã lộ, thay khóa và xử lý niềm tin/chứng thư.
7. **Khôi phục có phê duyệt:** Kiểm tra từ chối sử dụng sai Purpose ngay tại đường KMS/HSM và trong ứng dụng; theo dõi sau triển khai.
8. **Hậu kiểm:** Cập nhật taxonomy, quy trình cấp quyền, owner, cảnh báo và bài kiểm thử regression.

### Khi nào cần thay khóa?

Một lần gọi sai Purpose **không tự động chứng minh private key đã bị lộ**. Quyết định thay khóa phụ thuộc phạm vi lạm dụng, khả năng xuất key material, đặc tính giao thức, mức tin cậy của những chữ ký đã phát và chính sách tổ chức. Nhưng **không nên chỉ sửa nhãn Purpose** để hợp thức hóa việc sử dụng sai đã xảy ra.

## 17. Sai lầm thường gặp và hướng xử lý

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Ghi `purpose=security` cho mọi key | Không kiểm soát được phạm vi và vòng đời | Taxonomy có mã và mô tả rõ |
| Chỉ lưu algorithm, bỏ Purpose | Không phân biệt hai key cùng AES/ECDSA | Purpose + scope + usage + IAM |
| Dùng một signing key cho JWT và hóa đơn | Tăng blast radius và khó thu hồi | Tách cặp khóa, policy và owner |
| Coi `keyId`/alias là bằng chứng Purpose | Alias có thể đổi hoặc bị cấu hình nhầm | Inventory với approval, key version, source of truth |
| Viết Purpose trong DB nhưng KMS vẫn cấp `Sign` rộng | Caller bỏ qua ứng dụng vẫn dùng key | Least privilege ở provider và policy gate |
| Cho DEK làm KEK chỉ vì cùng là AES | Trộn vai trò, khó rotation và audit | Phân tách DEK/KEK theo thiết kế |
| Dùng private ECDSA key cho ECDH tùy tiện | Lẫn key usage và mô hình đe dọa | Khóa riêng cho ký và thỏa thuận |
| Tin metadata JWK `use=sig` từ nguồn không tin cậy | Nhận public key ngoài trust policy | Kiểm tra issuer/algorithm/trust source |
| Cho rằng cert có `digitalSignature` nên được ký mọi tài liệu | Nhầm quyền PKI với ủy quyền nghiệp vụ | Business approval + IAM + PKI |
| Đổi Purpose của key cũ bằng cách sửa tên | Không đổi vật liệu, dữ liệu và quyền cũ | Tạo key mới nếu mục tiêu thực sự đổi |
| Hủy KEK cũ sau khi đổi Purpose/version | Mất khả năng unwrap bản bọc cũ | Dependency mapping và rewrap |
| Hủy signing key rồi xóa cả public certificate | Không xác minh chữ ký lịch sử | Retention public key/chứng thư/bằng chứng |
| Ghi DEK/private key vào inventory để “kiểm kê đủ” | Lộ secret trên CMDB hoặc log | Chỉ lưu key ID, handle và metadata |
| Không rà soát các grant mới | Quyền thực tế lệch Purpose | Reconciliation định kỳ và cảnh báo |
| Không phân biệt production/staging/tenant | Dùng khóa sai môi trường hoặc khách hàng | Scope riêng, IAM và negative test |
| Coi key không có API call là không còn dùng | DEK cache và dữ liệu cũ vẫn phụ thuộc | Kết hợp dependency inventory, application audit |
| Chỉ kiểm tra thao tác đúng, không thử thao tác sai | Có thể bypass Purpose gate | Negative tests và deny auditing |

## 18. Checklist thiết kế trường Purpose trong Key inventory

Trước khi duyệt một key mới hoặc rà soát key đang active, hãy kiểm tra:

1. **Định nghĩa:** Purpose có mã chuẩn, mô tả nghiệp vụ và taxonomy version rõ ràng, không quá chung?
2. **Tài sản:** Đã biết dữ liệu, giao thức, tài liệu, token hoặc DEK nào được bảo vệ?
3. **Phạm vi:** `environment`, `tenant`, `service`, `dataDomain` và đối tác có được xác định?
4. **Crypto role:** Key là DEK, KEK, signing key, HMAC key, agreement key hay recovery key?
5. **Algorithm:** Thuật toán, độ dài/curve, tham số có phù hợp Purpose và chính sách bảo mật?
6. **Allowed operations:** Có phân biệt Encrypt/Decrypt, Wrap/Unwrap, Sign/Verify, MAC và DeriveKey đúng loại khóa?
7. **Business approval:** Ai duyệt yêu cầu trước thao tác `Sign` hoặc `Unwrap` nhạy cảm? HSM/KMS có hiểu được điều kiện đó không?
8. **IAM:** Principal nào được phép dùng đúng key/version? Người quản trị có thể tự cấp quyền trái Purpose không?
9. **Enforcement:** Có chặn sai Purpose tại ứng dụng và đường API KMS/HSM, không chỉ dựa vào tên/metadata?
10. **State/cryptoperiod:** Key chỉ được sử dụng trong trạng thái và thời hạn phù hợp; các thao tác legacy có policy riêng?
11. **Inventory fields:** Key ID, version, provider resource, owner, custodian, approval, data scope, location và audit refs có đủ?
12. **Key material:** Inventory tuyệt đối không chứa private key, DEK, KEK, HMAC secret, recovery secret hoặc password dạng rõ?
13. **Rotation:** Đã có lịch rotate và kế hoạch xử lý dữ liệu/tag/chữ ký/phiên phụ thuộc theo Purpose?
14. **Recovery:** DEK/KEK có backup, rewrap, restore và retention; signing key có giữ chứng cứ xác minh lịch sử?
15. **Cross-purpose reuse:** Có phát hiện vật liệu khóa được dùng cho hai Purpose ngoài phê duyệt, hoặc một alias trỏ sai key version?
16. **Reconciliation:** Có đối chiếu inventory với key resources, IAM/grants, chứng thư và log sử dụng thực tế?
17. **Audit:** Có ghi purposeId, key ID/version, caller, operation, thời điểm, kết quả, approval mà không lộ secret?
18. **Incident response:** Có runbook phân biệt lộ DEK/KEK, signing key, HMAC key, ECDH key và sử dụng ngoài Purpose?
19. **Kích hoạt/hủy:** Có kiểm tra readiness trước Active và dependency trước Destroyed; không xóa key chỉ vì đổi alias?
20. **Rà soát định kỳ:** Owner có xác nhận Purpose còn phù hợp với kiến trúc, chính sách và dữ liệu thực tế?

### Ghi nhớ

**Purpose** là lý do một khóa được tạo và **phạm vi sử dụng được chấp thuận** trong **key inventory**. Nó khác **algorithm**, **key usage**, **IAM permission**, **key state** và **cryptoperiod**, dù các thuộc tính này phải nhất quán với nhau. Một inventory hữu ích cần ghi **purposeId, mô tả, data scope, environment, owner, custodian, key ID/version, allowed operations, approval và dependency**, không lưu key material bí mật. Đối với **DEK/KEK, khóa ký số, HMAC, ECDH và recovery key**, Purpose quyết định cách phân quyền, kiểm toán, rotation, xử lý compromise và lưu giữ dữ liệu lịch sử. **Mục đích chỉ là metadata cho tới khi được cưỡng chế bằng policy thực tế tại ứng dụng và KMS/HSM**. Tách khóa theo mục đích, đối soát thường xuyên và kiểm thử từ chối sử dụng sai giúp vòng đời khóa mật mã an toàn, có trách nhiệm và có thể kiểm chứng.
