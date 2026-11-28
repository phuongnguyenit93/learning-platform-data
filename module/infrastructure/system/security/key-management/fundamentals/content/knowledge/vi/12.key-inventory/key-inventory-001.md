# Key inventory là gì? – Kiểm kê khóa mật mã để quản lý an toàn toàn bộ vòng đời

**Key inventory (kiểm kê khóa mật mã)** là hoạt động **xác định, ghi nhận, đối soát và duy trì thông tin về các khóa mật mã** đang được một tổ chức tạo, sở hữu, lưu giữ hoặc sử dụng. Một bản kiểm kê tốt trả lời được: *Có những khóa nào? Chúng bảo vệ dữ liệu/danh tính gì? Ai chịu trách nhiệm? Nằm ở đâu? Đang ở trạng thái nào? Khóa nào phụ thuộc khóa nào? Khi xoay vòng, thu hồi hoặc hủy sẽ ảnh hưởng đến đâu?*

Trong chương **Key inventory** thuộc module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, kiểm kê khóa là nền tảng quản trị cho vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**. Nó kết nối khóa AES/DEK, KEK, cặp khóa bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán thành một bức tranh có thể giám sát và xử lý sự cố.

> **Nguyên tắc bảo mật:** Key inventory chủ yếu chứa **metadata và tham chiếu đã được phân quyền**, **không phải một kho sao chép private key, DEK, KEK hay seed bí mật dưới dạng rõ**. Thu gom mọi bí mật về một bảng để “kiểm kê cho tiện” sẽ tạo ra một điểm rò rỉ cực kỳ nguy hiểm.

## 1. Vì sao phải kiểm kê khóa?

Giả sử Billing Service mã hóa hóa đơn bằng các **DEK AES-GCM**; mỗi DEK được **wrap** dưới một **KEK** do KMS quản lý. Một hệ thống khác ký sự kiện bằng **Ed25519**, còn cổng API dùng khóa TLS để xác thực dịch vụ. Không có key inventory, đội vận hành có thể gặp các vấn đề:

- Biết KMS có vài trăm key ID nhưng **không biết key nào thuộc dịch vụ hoặc tenant nào**.
- Một khóa ký cũ vẫn được consumer tin cậy sau khi chủ quản đã thay khóa mới.
- Khóa mã hóa lưu trữ quá hạn nhưng không ai biết **những bản mã hoặc bản sao lưu nào** còn cần nó.
- Một KEK bị nghi lộ nhưng không thể tìm nhanh **các DEK được bọc bằng KEK đó**.
- Có khóa nằm trong secret store, máy ảo, pipeline CI hoặc HSM **không nằm trong danh sách chính thức**.
- Tổ chức muốn triển khai chính sách thuật toán mới nhưng không biết **những hệ thống nào vẫn dùng thuật toán cũ**.

Key inventory biến các câu hỏi trên thành dữ liệu quản trị có thể truy vấn, đối chiếu và lập kế hoạch. Nó giúp giảm **orphan keys (khóa không có người chịu trách nhiệm)**, **shadow keys (khóa tồn tại ngoài quản trị được phê duyệt)**, **stale keys (khóa/bản ghi không còn cập nhật)** và **unknown dependencies (phụ thuộc chưa được biết)**.

**Kiểm kê không đồng nghĩa đã kiểm soát được khóa.** Danh sách đầy đủ mà quyền Sign/Decrypt/Unwrap vẫn bị cấp quá rộng, hoặc private key vẫn bị in vào log, không làm hệ thống an toàn. Inventory là cơ sở để **thực thi chính sách**, chứ không thay thế chính sách.

## 2. Phân biệt key inventory với các hệ thống gần giống

| Khái niệm | Trọng tâm | Khác với key inventory ở đâu? |
| --- | --- | --- |
| **Key inventory** | Bức tranh cập nhật về khóa, owner, usage, nơi quản lý, trạng thái và phụ thuộc. | Có thể tổng hợp từ nhiều công cụ, chứa cả khóa do bên ngoài quản lý. |
| **Key registry** | Đăng ký định danh, nguồn gốc và metadata cho một khóa; có thể là điểm kiểm soát kích hoạt. | Registry thường là một **nguồn dữ liệu** cho inventory; inventory còn cần phát hiện khóa ngoài registry. |
| **KMS (Key Management Service)** | Tạo, lưu giữ, sử dụng, xoay hoặc vô hiệu hóa khóa qua API và policy. | Một KMS không nhất thiết biết mọi khóa ở KMS khác, HSM, máy chủ, CI hay nhà cung cấp ngoài. |
| **HSM (Hardware Security Module)** | Bảo vệ và sử dụng key material trong ranh giới phần cứng. | Inventory có thể ghi **tham chiếu HSM**, không xuất private/secret key để kiểm kê. |
| **Secret manager** | Lưu và cấp phát các secret (API token, mật khẩu, khóa...). | Không phải secret nào cũng là khóa mật mã và không phải mọi khóa đều nằm trong secret manager. |
| **CMDB / asset inventory** | Máy chủ, ứng dụng, nhóm sở hữu, quan hệ tài sản CNTT. | Có thể liên kết owner/workload với khóa nhưng không có đủ metadata mật mã. |
| **Certificate inventory** | Chứng chỉ, hạn dùng, issuer, public key và hệ thống sử dụng. | Certificate không phải private key; nhiều khóa không có certificate. |
| **Cryptographic inventory / CBOM** | Tài sản và phụ thuộc mật mã rộng hơn: thuật toán, thư viện, chứng chỉ, key, protocol. | Key inventory tập trung vào **đối tượng khóa và vòng đời khóa**; có thể cung cấp dữ liệu cho báo cáo mật mã rộng hơn. |

Ví dụ, KMS có thể trả về `keyId` và `keyState`, nhưng **không biết bản mã trong database đã được chép vào backup nào**. Ứng dụng, kho dữ liệu và CMDB cần cung cấp thêm thông tin phụ thuộc. Không nên cố “sửa” vấn đề bằng cách sao chép DEK rõ vào hệ thống inventory.

### 2.1. Inventory không phải “danh sách các chuỗi key”

Một danh sách như:

~~~text
key-001
key-002
key-003
~~~

chỉ là tập ID. Nó chưa trả lời **khóa bảo vệ gì, owner là ai, còn được sử dụng không, có khả năng thu hồi không, và nếu hủy sẽ xảy ra chuyện gì**. Inventory có ích khi nó **định danh đúng các phiên bản key material** và liên kết chúng với các yếu tố vận hành.

## 3. Phạm vi các đối tượng cần kiểm kê

Không phải mọi bit mật mã phải tồn tại dưới dạng một bản ghi dài hạn. Phạm vi nên dựa trên **mức độ quan trọng, thời hạn tồn tại và khả năng quản trị**.

| Loại đối tượng | Ví dụ | Thông tin cần đặc biệt quan tâm |
| --- | --- | --- |
| **DEK đối xứng** | Khóa AES-256-GCM mã hóa bảng, tệp, bản ghi. | Tập dữ liệu/tenant, key version, thuật toán/mode, số bản mã phụ thuộc và KEK đang wrap. |
| **KEK / wrapping key** | KMS key bọc nhiều DEK. | Vị trí giữ khóa, quyền wrap/unwrap, bản đồ phụ thuộc DEK và tác động khi vô hiệu hóa. |
| **Khóa ký số** | Ed25519/RSA-PSS ký sự kiện, token, artifact. | Owner, key usage SIGN, public key/chứng chỉ tương ứng, consumer tin cậy, lịch rotate/revoke. |
| **Khóa giải mã bất đối xứng** | Private key RSA-OAEP bảo vệ khóa phiên/DEK. | Ciphertext phụ thuộc, nơi giữ private key, khả năng khôi phục dữ liệu lịch sử. |
| **Khóa MAC** | HMAC-SHA-256 xác thực webhook. | Các bên chia sẻ secret, phạm vi API, cách xoay và cửa sổ chấp nhận tag cũ. |
| **Khóa TLS/mTLS** | Private key chứng chỉ server hoặc workload. | Certificate, identity, trust domain, ngày hết hạn, vị trí dùng và đường tự động gia hạn. |
| **Khóa ký phát hành** | Ký JAR, OCI image hoặc manifest. | Repository, release workflow, identity được tin cậy, giới hạn quyền Sign và bằng chứng kiểm toán. |
| **Khóa gốc/master/backup** | Khóa phục hồi hoặc khóa cấp cao trong HSM. | Ranh giới bảo vệ, quyền đa bên, mức ảnh hưởng hệ thống khi bị mất hoặc hủy. |
| **Pepper hoặc khóa KDF** | Bí mật phụ trợ cho password hashing hoặc dẫn xuất khóa theo mục đích. | Nơi lưu, phiên bản, chủ quản và kế hoạch rotate/migration. |
| **Khóa phiên tạm thời** | ECDHE ephemeral secret, TLS traffic key. | Thường theo dõi **cơ chế phát hành, phiên và chính sách** thay vì giữ từng secret trong registry lâu dài. |

**Ví dụ cần phân biệt:** Một chứng chỉ TLS chứa **public key**; private key của nó có thể nằm trong HSM hoặc ở một hệ thống khác. Kiểm kê chứng chỉ chưa chắc đã chứng minh private key đang được bảo vệ đúng.

Với DEK theo từng bản ghi, có thể có hàng triệu khóa. Không nhất thiết lập một row thủ công cho mỗi DEK trong một bảng trung tâm; có thể dùng **inventory phân cấp**, thống kê theo nhóm và **metadata/manifest có thể truy vấn** để tìm chính xác khóa cần thiết khi khôi phục, xoay vòng hoặc xóa dữ liệu.

## 4. Những metadata cần có trong một bản ghi key inventory

Một schema có thể được chia theo các nhóm sau:

| Nhóm | Ví dụ thuộc tính | Tại sao cần? |
| --- | --- | --- |
| **Định danh** | `keyId`, `keyVersion`, `providerId`, `alias`, `fingerprint` | Chọn chính xác khóa và phân biệt phiên bản cũ/mới. |
| **Thuật toán** | AES-256-GCM, HMAC-SHA-256, Ed25519, RSA-PSS; key size/curve | Xác định key usage và kế hoạch chuyển thuật toán. |
| **Mục đích** | ENCRYPT, DECRYPT, SIGN, VERIFY, WRAP, UNWRAP, DERIVE | Ngăn tái sử dụng khóa sai mục đích. |
| **Sở hữu** | owner team, workload, tenant, môi trường, data classification | Xác định người duyệt, phạm vi dữ liệu và đường ứng phó sự cố. |
| **Nguồn gốc** | generated in KMS/HSM, imported BYOK, external provider | Đánh giá ranh giới tin cậy và trách nhiệm bảo vệ. |
| **Nơi lưu** | KMS resource URI, HSM slot/object reference, secret reference | Biết cách định vị khóa **không cần đưa secret vào inventory**. |
| **Trạng thái** | ACTIVE, DISABLED, RETIRED, COMPROMISED, PENDING_DELETION | Phân biệt khả năng dùng mới và nhu cầu giải mã/xác minh lịch sử. |
| **Thời hạn** | created, activated, lastUsed, nextReview, expires, rotationPolicy | Nhận biết khóa quá tuổi, sắp hết hạn hoặc cần xem xét. |
| **Phụ thuộc** | wrappedBy, wrappingVersion, service consumers, dataset IDs | Đánh giá phạm vi tác động khi thay, thu hồi hoặc hủy. |
| **Chính sách quyền** | allowed principals, key usage policy reference, separation of duties | Kiểm tra least privilege và quyền nhạy cảm. |
| **Bằng chứng** | KMS audit reference, certificate/attestation reference, approval ID | Truy xuất lịch sử mà không sao chép dữ liệu nhạy cảm. |
| **Chất lượng dữ liệu** | source, observedAt, reconciliationStatus, confidence | Biết bản ghi lấy từ đâu, còn mới hay đã lỗi thời. |

**Không phải trường nào cũng nên công khai cho toàn bộ nhân viên.** Tên key, đường dẫn backup, tenant và quan hệ giữa dịch vụ có thể tiết lộ kiến trúc bảo mật. Inventory cần **RBAC/ABAC, phân vùng tenant và giới hạn dữ liệu trả về** như một hệ thống quản trị nhạy cảm.

### 4.1. Khóa định danh, alias và fingerprint khác nhau

- **Key ID:** định danh do KMS/registry quản lý; phạm vi duy nhất phụ thuộc nhà cung cấp và hệ thống.
- **Key version:** phiên bản **vật liệu khóa thực sự được dùng**. Alias `billing-current` có thể trỏ từ v1 sang v2, nên bản mã cần metadata đủ để tìm lại phiên bản cũ.
- **Alias:** tên thuận tiện để các ứng dụng trỏ tới khóa hiện tại; **không mặc định bất biến**.
- **Fingerprint:** giá trị băm của public key theo encoding xác định, ví dụ SHA-256 trên X.509 SPKI DER. Nó **không tự chứng minh người sở hữu public key**.
- **Certificate serial/issuer:** định danh chứng chỉ, **không đồng nghĩa định danh private key** hay KMS key object.

Một key ID có thể đại diện cho đối tượng KMS quản lý **nhiều phiên bản**. Chính sách inventory phải ghi rõ đơn vị quản lý là **key object** hay **key material version**; với dữ liệu giải mã cần có khả năng truy tới phiên bản tương ứng.

### 4.2. Ví dụ bản ghi inventory

~~~yaml
inventoryId: "crypto-inventory/billing-kek/v4"
keyRef:
  provider: "organization-kms"
  resourceId: "kms://prod/billing/kek"
  materialVersion: 4
metadata:
  algorithm: "AES-256"
  purpose: ["WRAP", "UNWRAP"]
  owner: "billing-security"
  environment: "production"
  tenantScope: "billing"
  origin: "KMS_GENERATED"
  custody: "KMS_HSM_MANAGED"
  exportable: false
lifecycle:
  state: "ACTIVE"
  createdAt: "2026-09-15T00:00:00Z"
  nextReviewAt: "2027-01-15T00:00:00Z"
dependencies:
  wrappedDekCount: 1240
  dependencyIndexRef: "metadata://billing/wrapped-deks"
security:
  accessPolicyRef: "policy://billing-kek-v4"
  auditStreamRef: "audit://kms/billing"
observed:
  source: "KMS_METADATA_API"
  observedAt: "2026-11-28T00:00:00Z"
  reconciliation: "MATCHED"
~~~

Đây là **schema minh họa**, không phải cấu trúc tiêu chuẩn hoặc thông tin về khóa có thật. Inventory **không lưu KEK dạng rõ**, cũng không cần lưu mật khẩu, seed, plaintext hoặc toàn bộ wrapped DEK nếu một kho chuyên dụng đã quản lý dữ liệu đó.

**Tính nhất quán với dữ liệu thực:** Trường `wrappedDekCount` có thể là số ước lượng/lần đồng bộ gần nhất. Nếu cần quyết định hủy KEK, không chỉ tin con số mà phải có **đối soát dependencies từ các kho dữ liệu và backup**.

## 5. Các nguồn phát hiện khóa và độ tin cậy của chúng

Một inventory thường phải tổng hợp thông tin từ nhiều nguồn:

1. **KMS/HSM:** liệt kê key objects, versions, states, aliases, access policies, lịch xoay và một số audit events qua API có quyền đọc metadata.
2. **Secret manager:** tham chiếu các secret được phân loại là khóa, version và owner, không đọc secret value khi không cần.
3. **PKI/CA/certificate manager:** public certificates, serial, issuer, key usage, danh tính và trạng thái hết hạn/thu hồi.
4. **Ứng dụng, database và storage:** key ID/version, encryption context, dữ liệu nào được mã hóa dưới DEK/KEK nào; snapshot/backup nào còn chứa bản mã.
5. **CI/CD và artifact registry:** signing key refs, danh tính build/release, trust policy được consumer sử dụng.
6. **CMDB/IAM và dịch vụ định danh:** nhóm sở hữu, workload, môi trường, principal được cấp quyền sử dụng key.
7. **Cloud accounts, vùng triển khai và tổ chức khác:** khóa ở nhiều account/region/subscription/provider cần có vùng quan sát riêng và kế hoạch đối soát.
8. **Kiểm tra cấu hình và phát hiện “shadow keys”:** tìm dấu hiệu khóa nằm ngoài kho chuẩn qua phương pháp được ủy quyền, có giới hạn thu thập và quy trình xử lý an toàn.

**Discovery phải tránh tự tạo sự cố.** Nếu một công cụ quét thấy private key nằm trong repository hoặc image, nên báo **vị trí/tham chiếu, fingerprint hoặc cảnh báo đã lọc** cho nhóm có quyền, không copy toàn bộ private key vào key inventory, hệ thống metrics hay ticket công khai.

### 5.1. Inventory không thể chỉ dựa vào một API ListKeys

Một API có thể liệt kê key metadata nhưng:

- Không thấy khóa ngoài account hoặc region được truy cập.
- Không biết private key đã bị xuất/copy trước đây hay chưa.
- Không thấy **mọi bản sao của bản mã** cần một DEK cụ thể.
- Không biết consumer nào còn chấp nhận một public key sau khi rotate.
- Không phân biệt khóa hoạt động với một **bản ghi metadata không còn sử dụng** nếu thiếu telemetry đáng tin.

**Sự vắng mặt trong một nguồn không chứng minh khóa không tồn tại.** Inventory phải ghi rõ **phạm vi quan sát, thời điểm dữ liệu, quyền đọc và mức đầy đủ**. Không gán “coverage 100%” khi chưa có bằng chứng về phạm vi được kiểm kê.

### 5.2. Nguồn gốc và chất lượng dữ liệu

Một khóa có thể được thấy trong KMS nhưng owner lại lấy từ tag do người dùng tự nhập; phần KMS state có độ tin cậy khác trường owner chưa kiểm chứng. Do đó nên lưu **source-of-truth theo thuộc tính**:

| Thuộc tính | Nguồn có thẩm quyền thường dùng | Cách kiểm tra |
| --- | --- | --- |
| Key state và material version | KMS/HSM metadata | Đối chiếu API và thời điểm quan sát. |
| Owner/workload | Hệ thống quản lý danh tính, CMDB hoặc đăng ký có phê duyệt | So khớp nhóm đang hoạt động và quyền chịu trách nhiệm. |
| Data dependencies | Encryption metadata tại ứng dụng/storage, backup catalog | Đếm và truy xuất bản mã phụ thuộc theo key version. |
| Signer trust | PKI/JWKS/trust policy của verifier | Kiểm tra consumer đang dùng nguồn public key nào. |
| Last used | Audit log từ điểm sử dụng khóa | Xem phạm vi log, thời gian lưu và độ trễ; **không suy từ thiếu log là key không dùng**. |
| Planned rotation | Chính sách quản lý khóa | Đối chiếu trạng thái triển khai và ngoại lệ được duyệt. |

Khi hai nguồn mâu thuẫn, không nên tự chọn giá trị mới nhất rồi xóa dấu vết. Cần ghi **drift/conflict**, nguồn, mức ưu tiên và người chịu trách nhiệm xử lý.

## 6. Mối quan hệ phụ thuộc: phần quan trọng nhất của inventory

Một key không tồn tại cô lập. **Dependency mapping** giúp hiểu tác động trước khi xoay, thu hồi, chuyển nhà cung cấp hoặc hủy khóa.

~~~mermaid
flowchart TD
    ROOT["Root / master key do HSM quản lý"] --> KEK["KEK: billing v4"]
    KEK --> W1["Wrapped DEK A"]
    KEK --> W2["Wrapped DEK B"]
    W1 --> DATA1["Invoice records: tenant A"]
    W1 --> BACKUP1["Snapshot / backup còn lưu"]
    W2 --> DATA2["Invoice records: tenant B"]
    SIGN["Signing key S2"] --> EVENT["Sự kiện đã ký"]
    SIGN --> TRUST["Ledger Service trust store"]
    TLS["TLS identity key"] --> CERT["Chứng chỉ và service identity"]
    CERT --> CLIENTS["Các client còn kết nối"]
~~~

**Không phải mũi tên nào cũng là quan hệ mật mã trực tiếp.** Mũi tên có thể biểu diễn **key wraps key**, **ciphertext encrypted by key**, **signature created by key**, **consumer trusts public key** hoặc **workload uses key**. Hệ thống dữ liệu nên lưu **loại cạnh** để tránh hiểu sai.

Ví dụ:

~~~text
KEK-v4 --WRAPS--> DEK-invoice-A-v2
DEK-invoice-A-v2 --ENCRYPTS--> invoice-partition-2026-11
invoice-partition-2026-11 --COPIED_TO--> backup-2026-11-28
signing-S2 --SIGNS--> payment-event-batch-1024
ledger-service --TRUSTS_PUBLIC_KEY_OF--> signing-S2
~~~

Quan hệ này tạo ra **blast radius (phạm vi ảnh hưởng)** có thể tính toán. Nếu KEK bị vô hiệu hóa, những DEK nào không unwrap được? Nếu signing key bị lộ, bao nhiêu consumer còn tin khóa đó? Nếu một DEK bị lộ, những phân vùng dữ liệu nào cần đánh giá re-encrypt?

### 6.1. Rotate KEK và rotate DEK khác nhau

- **Rotate KEK / rewrap DEK:** thay khóa bọc, rồi bọc lại DEK dưới KEK mới theo cơ chế được hỗ trợ. **Dữ liệu thường không cần được mã hóa lại** nếu DEK vẫn giữ nguyên.
- **Rotate DEK:** tạo DEK mới và chuyển dữ liệu sang khóa đó, thường cần **mã hóa lại dữ liệu** hoặc một kế hoạch di chuyển tương ứng.
- **Rotate signing key:** sinh cặp khóa mới, công bố public key mới **trước** khi phát hành chữ ký mới; dữ liệu ký cũ có thể cần public key/chứng chỉ cũ để xác minh theo policy.
- **Rotate TLS key/certificate:** cần cập nhật certificate, trust và các endpoint, đồng thời xử lý session hiện hữu theo giao thức.

**Nếu DEK đã bị lộ, chỉ rewrap cùng DEK dưới KEK mới không bảo vệ được bản mã cũ**. Ngược lại, nếu hủy KEK cũ khi vẫn còn DEK chưa được rewrap hoặc backup chứa DEK chỉ được bọc dưới KEK cũ, dữ liệu có thể mất khả năng khôi phục.

### 6.2. Inventory phải bao phủ backup và disaster recovery

Một database đã di chuyển sang DEK mới chưa chắc đồng nghĩa mọi **backup, replica, archive và immutable snapshot** đã chuyển. Trước khi hủy khóa, cần đánh giá:

1. Những bản sao lưu nào vẫn mã hóa dưới DEK/KEK cũ?
2. Có đường khôi phục hợp lệ khi phiên bản khóa cũ đã bị disable không?
3. Chính sách retention yêu cầu giữ dữ liệu hoặc bằng chứng ký bao lâu?
4. Có thể kiểm tra restore trên môi trường phù hợp mà không làm lộ secret?
5. Nếu định dùng **crypto-shredding**, đã loại bỏ toàn bộ bản sao khóa và đường giải mã khác theo phạm vi mong muốn chưa?

Một inventory chỉ liệt kê **khóa hiện đang active** không đủ để quyết định **hủy** một khóa cũ.

## 7. Quy trình xây dựng và duy trì key inventory

~~~mermaid
flowchart TD
    SCOPE["Xác định phạm vi: account, region, app, tenant"] --> COLLECT["Thu thập metadata từ KMS/HSM, PKI, ứng dụng"]
    COLLECT --> NORMALIZE["Chuẩn hóa key ID, version, type, owner, purpose"]
    NORMALIZE --> LINK["Liên kết workload, ciphertext, certificate, backups"]
    LINK --> RECON["Đối soát nguồn thẩm quyền và snapshot inventory"]
    RECON --> DECIDE{"Phát hiện vấn đề?"}
    DECIDE -->|Có| TICKET["Gắn mức độ, owner, xử lý ngoại lệ"]
    DECIDE -->|Không| APPROVE["Chốt snapshot/trạng thái hiện tại"]
    TICKET --> APPROVE
    APPROVE --> AUDIT["Lưu dấu vết và cập nhật theo lịch/sự kiện"]
    AUDIT --> COLLECT
~~~

Một quy trình triển khai thực tế:

1. **Xác định phạm vi và owner** cho cloud accounts, KMS/HSM, ứng dụng, tenant, certificates, CI/CD và key stores.
2. **Thu thập chỉ metadata cần thiết**, ưu tiên API có quyền đọc; không tự gọi ExportKey/GetSecretValue để xây inventory.
3. **Chuẩn hóa định danh** theo provider + account/region/namespace + key ID + material version khi cần; tránh xung đột giữa các hệ thống.
4. **Liên kết dữ liệu phụ thuộc** từ ứng dụng/storage, PKI, trust policies, backup catalog và CMDB.
5. **Kiểm tra chất lượng dữ liệu**: thiếu owner, trạng thái mâu thuẫn, key usage sai, ngày hết hạn, nguồn chưa rõ, record trùng.
6. **Đối soát thường xuyên** giữa inventory và nguồn thực; ghi nhận khóa mới, bị disable/xóa, thay permission, đổi alias hoặc xuất hiện consumer mới.
7. **Phân loại cảnh báo** và giao việc cho owner; các thay đổi có rủi ro lớn cần phê duyệt, bằng chứng và thời hạn xử lý.
8. **Lưu lịch sử và audit** cho nguồn dữ liệu, thay đổi metadata, quyết định khắc phục và thời điểm xác minh lại.

**Không xóa một bản ghi khỏi inventory ngay khi nguồn KMS không còn trả về khóa.** Có thể do lỗi quyền, API, vùng quét hoặc khóa đã bị xóa nhưng vẫn còn ciphertext/consumer liên quan. Cần chuyển sang trạng thái cần điều tra và giữ lịch sử thích hợp.

### 7.1. Khóa mới, khóa ngoài quản lý và inventory drift

**Drift** là chênh lệch giữa trạng thái đang được quản lý và trạng thái quan sát thực tế:

- Key hiện diện trong KMS nhưng **không có trong inventory**.
- Inventory ghi **ACTIVE** nhưng KMS đã **DISABLED**.
- Key có owner được ghi nhưng nhóm owner đã giải thể.
- Policy cho phép ứng dụng A nhưng IAM thực tế còn cho cả ứng dụng B dùng `Decrypt`.
- Key đã retire nhưng log cho thấy vẫn có lệnh **Encrypt/Sign** mới.
- Một certificate/key đã được thay nhưng consumer vẫn tin public key cũ ngoài cửa sổ cho phép.
- Inventory không biết DEK cũ còn được dùng ở các backup.

**Đối soát nên ưu tiên đọc từ các nguồn có thẩm quyền**, không tin hoàn toàn vào nhãn/tags do workload tự khai. Khi có sự cố đọc nguồn, nên ghi **UNKNOWN/STALE**, không tự kết luận tất cả khóa đã biến mất.

### 7.2. Ai chịu trách nhiệm?

| Vai trò | Trách nhiệm chính |
| --- | --- |
| **Crypto/security governance** | Định nghĩa schema, policy, tiêu chuẩn thuật toán, ngoại lệ và mức độ ưu tiên rủi ro. |
| **KMS/HSM administrator** | Quản lý tài sản khóa và quyền thao tác ở nhà cung cấp, cung cấp API/audit metadata. |
| **Service/data owner** | Xác nhận mục đích, tenant, dữ liệu phụ thuộc, kế hoạch rotate/retire và phục hồi. |
| **Platform/DevOps/SRE** | Tự động hóa discovery, reconciliation, cảnh báo, backup/DR và kiểm soát CI/CD. |
| **PKI/identity team** | Quản lý chứng chỉ, trust anchors, service identity, quy trình gia hạn/thu hồi. |
| **Audit/compliance** | Kiểm tra bằng chứng thay đổi, owner, thời hạn, quyền truy cập và chính sách hủy. |

Nên có **owner chịu trách nhiệm thực sự**, cùng đường liên hệ khi người đó nghỉ việc hoặc workload bị ngừng vận hành. “Owner: platform” mà không có người/nhóm chịu trách nhiệm cụ thể có thể vẫn là **orphan key** trên thực tế.

## 8. Ví dụ Java 17: đối soát metadata khóa và phát hiện drift

Đoạn mã sau minh họa **reconciliation** giữa một snapshot key inventory và metadata mới lấy từ nguồn có thẩm quyền. Nó kiểm tra **key version chưa đăng ký**, **bản ghi không còn quan sát**, **khóa sắp hết hạn**, và **khóa không active nhưng vẫn có dữ liệu phụ thuộc**.

**Giới hạn:** Đây là demo thuần trong bộ nhớ, không truy cập KMS thật và **không chứa key material**. Các trường ID, ngày và dependencies đều là dữ liệu giả lập. Khi triển khai cần tích hợp API của KMS/HSM, kho dữ liệu và audit theo quyền đọc tối thiểu; không dùng kết quả một lần quét để tự động xóa khóa.

~~~java
import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class KeyInventoryDemo {
    enum State { ACTIVE, RETIRED, DISABLED }

    record KeyRef(String id, int version) {}

    record KeyMeta(
            KeyRef ref,
            String owner,
            String usage,
            State state,
            LocalDate expiresAt,
            KeyRef wrappingKey) {}

    record DataDependency(String objectId, KeyRef keyRef) {}

    static void reconcile(
            List<KeyMeta> authoritative,
            Map<KeyRef, KeyMeta> inventorySnapshot,
            List<DataDependency> dependencies,
            LocalDate today) {

        Map<KeyRef, KeyMeta> observed = new HashMap<>();
        for (KeyMeta key : authoritative) {
            observed.put(key.ref(), key);
        }

        Map<KeyRef, Integer> dependencyCounts = new HashMap<>();
        for (DataDependency item : dependencies) {
            dependencyCounts.merge(item.keyRef(), 1, Integer::sum);
        }

        for (KeyMeta key : authoritative) {
            KeyRef ref = key.ref();

            if (!inventorySnapshot.containsKey(ref)) {
                System.out.println("DISCOVERED_NOT_IN_INVENTORY: " + ref);
            }
            if (key.owner() == null || key.owner().isBlank()) {
                System.out.println("MISSING_OWNER: " + ref);
            }
            if (key.expiresAt() != null
                    && !key.expiresAt().isAfter(today.plusDays(30))) {
                System.out.println("REVIEW_EXPIRY: " + ref);
            }

            int dependents = dependencyCounts.getOrDefault(ref, 0);
            if (key.state() != State.ACTIVE && dependents > 0) {
                System.out.println("REVIEW_INACTIVE_WITH_DEPENDENCIES: "
                        + ref + ", references=" + dependents);
            }

            if (key.wrappingKey() != null
                    && !observed.containsKey(key.wrappingKey())) {
                System.out.println("WRAPPING_KEY_NOT_OBSERVED: " + ref);
            }
        }

        for (KeyRef ref : inventorySnapshot.keySet()) {
            if (!observed.containsKey(ref)) {
                System.out.println("INVENTORY_RECORD_NOT_OBSERVED: " + ref);
            }
        }
    }

    public static void main(String[] args) {
        LocalDate today = LocalDate.now();

        KeyRef signing = new KeyRef("kms/prod/payment-sign", 2);
        KeyRef kek = new KeyRef("kms/prod/billing-kek", 4);
        KeyRef legacyDek = new KeyRef("kms/prod/legacy-dek", 1);
        KeyRef oldRef = new KeyRef("kms/old/stale-reference", 1);

        KeyMeta signingMeta = new KeyMeta(
                signing, "payment-service", "SIGN",
                State.ACTIVE, today.plusDays(90), null);
        KeyMeta kekMeta = new KeyMeta(
                kek, "billing-service", "WRAP",
                State.ACTIVE, today.plusDays(12), null);
        KeyMeta legacyMeta = new KeyMeta(
                legacyDek, "billing-service", "ENCRYPT",
                State.DISABLED, today.minusDays(5), kek);

        // Snapshot cũ chưa có KEK v4; vẫn chứa một record không quan sát.
        Map<KeyRef, KeyMeta> inventorySnapshot = Map.of(
                signing, signingMeta,
                legacyDek, legacyMeta,
                oldRef, new KeyMeta(oldRef, "legacy-team", "SIGN",
                        State.RETIRED, today.minusDays(50), null));

        // Metadata giả lập lấy từ KMS/HSM.
        List<KeyMeta> authoritative = List.of(
                signingMeta, kekMeta, legacyMeta);

        // Một tập dữ liệu cũ vẫn ghi nhận bị mã hóa bởi DEK v1.
        List<DataDependency> dependencies = List.of(
                new DataDependency("archive/invoice-2025", legacyDek));

        reconcile(authoritative, inventorySnapshot, dependencies, today);
    }
}
~~~

Ví dụ sẽ phát hiện ít nhất **KEK v4 chưa có trong snapshot inventory**, **KEK v4 sắp tới kỳ hết hạn**, **DEK legacy đang DISABLED nhưng còn archive phụ thuộc**, và **bản ghi cũ không còn xuất hiện ở nguồn mới**.

### 8.1. Những điều ví dụ chưa làm

- **Không truy cập KMS/API thật**; không xác minh IAM thực tế, thuật toán, backup hoặc ciphertext đã được di chuyển.
- **Không tự động hủy hoặc mở quyền khóa**: drift cần được điều tra, phê duyệt và xử lý theo policy.
- **Không tính đủ dependency graph** của KEK → DEK → ciphertext → backup; chỉ đếm tham chiếu trực tiếp.
- **Không có authentication, rate limit, pagination, retry, backoff, audit bền vững** hoặc xử lý nhiều vùng/tenant.
- Khi một API nguồn thất bại hoặc quyền đọc bị hạn chế, không được coi mọi key vắng mặt là đã bị xóa.
- **Độ nhạy cảm của metadata** cũng cần được bảo vệ: tên key và đường dẫn dữ liệu nên được lọc khi đưa vào log/dashboard.

Đối với production, nên sử dụng **typed metadata client**, định danh version rõ ràng, thu thập tăng dần theo sự kiện khi có thể và **periodic full reconciliation** để khắc phục sự kiện bị mất.

## 9. Vòng đời khóa dưới góc nhìn inventory

| Giai đoạn | Inventory cần làm gì? | Rủi ro nếu bỏ qua |
| --- | --- | --- |
| **Tạo** | Ghi nhận nguồn sinh CSPRNG/KMS/HSM, thuật toán, owner và key usage. | Khóa yếu hoặc shadow key không được phát hiện. |
| **Cấp phát/đăng ký** | Gắn key ID/version, scope, policy, nơi quản lý và chứng cứ phê duyệt. | Không biết ai có quyền dùng khóa hoặc sử dụng sai mục đích. |
| **Lưu trữ** | Theo dõi tham chiếu custody, exportability, backup và bản sao có thẩm quyền. | Lộ vật liệu khóa, không biết bản sao ở đâu. |
| **Sử dụng** | Ghi nhận workload consumers, encrypt/sign/unwrap usage và trạng thái quyền. | Khóa nghỉ hưu vẫn bị dùng; quyền API quá rộng. |
| **Xoay vòng** | Liên kết old/new versions, alias migration, rewrap/re-encrypt và consumer readiness. | Bản mã không giải mã được hoặc release/chữ ký mới bị từ chối. |
| **Thu hồi/vô hiệu hóa** | Đánh dấu phạm vi trust, affected consumers, sự cố và bằng chứng cập nhật quyền. | Khóa lộ tiếp tục được sử dụng/trusted. |
| **Hủy** | Kiểm kê tất cả dependencies, backups, retention; lưu trạng thái và bằng chứng hủy. | Mất dữ liệu vĩnh viễn hoặc secret còn tồn tại trái chính sách. |

**Trạng thái vòng đời không phải một enum chung cho mọi provider.** `RETIRED` có thể có nghĩa ngừng mã hóa mới nhưng vẫn được giải mã lịch sử; `REVOKED` của chứng chỉ ảnh hưởng việc một verifier có còn tin khóa công khai hay không; `DISABLED` ở KMS có thể chặn ngay API decrypt/unwrap. Inventory cần lưu **ý nghĩa trạng thái theo hệ thống**, thay vì hợp nhất thiếu kiểm soát.

### 9.1. Khi chuẩn bị thu hồi/hủy

Một quy trình an toàn nên bắt đầu bằng câu hỏi:

1. Khóa nào và **phiên bản nào** đang bị thu hồi?
2. Khóa được sử dụng cho **ENCRYPT/DECRYPT, SIGN/VERIFY, WRAP/UNWRAP** hay mục đích khác?
3. Những ciphertext, wrapped DEK, certificate, tokens, bản release hoặc backups nào còn phụ thuộc?
4. Có đường di chuyển, rewrap, re-encrypt hoặc key version mới chưa?
5. Các consumer đã cập nhật trust/authorization theo yêu cầu chưa?
6. Có nhu cầu **xác minh chữ ký lịch sử** hoặc **khôi phục dữ liệu lịch sử** không?
7. Đã có phê duyệt, kiểm thử khôi phục và bằng chứng thao tác hủy chưa?

Với **crypto-shredding**, inventory đặc biệt quan trọng: muốn hủy dữ liệu thông qua hủy khóa cần xác minh **mọi bản sao DEK/KEK và mọi đường giải mã còn có thể tồn tại**. Chỉ chuyển trạng thái trong bảng inventory sang `DESTROYED` mà vật liệu khóa vẫn tồn tại thì chưa phải hủy bằng mật mã.

## 10. Ưu tiên rủi ro và các chỉ số theo dõi

Inventory thường tạo nhiều cảnh báo; cần ưu tiên theo **mức nhạy cảm của khóa, phạm vi phụ thuộc, trạng thái sử dụng và khả năng khắc phục**.

### 10.1. Ví dụ phân loại rủi ro

| Tình huống | Hướng ưu tiên | Vì sao? |
| --- | --- | --- |
| KEK production phục vụ nhiều DEK bị nghi lộ | **Khẩn cấp** | Có thể ảnh hưởng lượng dữ liệu rất lớn và nhiều tenant. |
| Signing key bị lộ nhưng consumer vẫn tin | **Khẩn cấp** | Có thể chấp nhận chữ ký giả hoặc bản phát hành giả. |
| Khóa mới xuất hiện không có owner/nguồn xác thực | **Cao** | Chưa biết key usage, quyền và phạm vi ảnh hưởng. |
| Khóa DISABLED còn nhiều ciphertext phụ thuộc | **Cao** | Rủi ro không khôi phục/giải mã khi cần. |
| Chứng chỉ sắp hết hạn và không có kế hoạch gia hạn | **Cao** | Nguy cơ gián đoạn kết nối/xác thực dịch vụ. |
| Key metadata không được đối soát trong nhiều tuần | **Tùy phạm vi** | Có thể che giấu drift hoặc hoạt động ngoài policy. |
| Khóa RETIRED không còn phụ thuộc và đủ điều kiện hủy | **Theo lịch** | Cần xử lý tồn đọng và hoàn thiện bằng chứng hủy. |

Mức ưu tiên trên chỉ minh họa; hệ thống thật cần **policy và quy trình ứng phó** để xác định mức độ nghiêm trọng, SLA, quyền phê duyệt và cách tránh tự động hủy nhầm.

### 10.2. KPI nên có

- **Coverage theo phạm vi đã xác định:** số key versions được kiểm kê/đối soát ÷ số key versions phát hiện từ **các nguồn có thẩm quyền trong phạm vi**. Không diễn giải thành độ phủ toàn tổ chức nếu phạm vi nguồn còn thiếu.
- **Owner completeness:** tỷ lệ key versions có owner hợp lệ và liên hệ được.
- **Policy compliance:** tỷ lệ khóa có thuật toán, usage, quyền và thời hạn phù hợp theo chính sách.
- **Upcoming expiry/rotation:** số khóa/chứng chỉ sắp đến hạn nhưng chưa có kế hoạch.
- **Unmanaged/shadow key alerts:** số đối tượng phát hiện ngoài registry/quản lý và thời gian khắc phục.
- **Stale observations:** số bản ghi không còn được xác minh trong cửa sổ thời gian yêu cầu.
- **Dependency completeness:** tỷ lệ DEK/KEK có liên kết ciphertext/backup/consumer cần thiết theo scope.
- **Critical drift age:** thời gian từ lúc phát hiện xung đột nghiêm trọng đến khi owner giải quyết.
- **Orphan keys:** số khóa có owner không còn hợp lệ hoặc mất đường liên hệ.

**Thận trọng với KPI 100%:** Không thể tự biết mẫu số “tất cả khóa trong tổ chức” chỉ bằng chính inventory đang cố xây dựng. Chỉ nên báo **coverage của các nguồn đã được kiểm tra**, kèm giới hạn vùng/quyền/tần suất. Ngoài ra cần theo dõi **false positives** để cảnh báo không làm nhóm vận hành mất niềm tin.

## 11. Bảo mật của chính hệ thống key inventory

Inventory có thể không giữ private key nhưng vẫn rất nhạy cảm: ai có nó có thể biết nơi lưu khóa, owner, đường dẫn dữ liệu, hệ thống nào chưa rotate và các điểm có tác động lớn.

Áp dụng các kiểm soát:

1. **Read-only discovery ở mức tối thiểu:** quyền liệt kê metadata khác quyền `Decrypt`, `Sign`, `Unwrap`, `ExportKey` hoặc `GetSecretValue`.
2. **RBAC/ABAC và tenant boundaries:** đội Billing chỉ nhìn chi tiết cần thiết về khóa Billing; quản trị/audit được cấp quyền theo vai trò.
3. **Mã hóa dữ liệu inventory khi lưu/truyền:** dùng TLS, kiểm soát database/storage và giải pháp mã hóa phù hợp; không hard-code credential để lấy metadata.
4. **Toàn vẹn và lịch sử thay đổi:** ghi actor, thời điểm, nguồn, trước/sau và phê duyệt khi thay ownership hoặc trust mapping.
5. **Tách quyền:** người duyệt policy/đánh dấu `DESTROYED` không mặc nhiên có quyền hủy khóa trong KMS.
6. **Giảm dữ liệu nhạy cảm:** không thu thập secret bytes; token, password, DEK/KEK, private key, seed và shared secret phải ở kho được chỉ định.
7. **Bảo vệ truy vấn và xuất báo cáo:** lọc dữ liệu theo người dùng; giới hạn bulk export; tránh đưa quan hệ phụ thuộc nhạy cảm vào dashboard công khai.
8. **Cảnh báo bất thường:** phát hiện chỉnh owner, trust key, trạng thái hoặc policy trái quy trình; theo dõi truy cập inventory hàng loạt.
9. **Khả năng phục hồi:** backup metadata và phục hồi chính inventory, nhưng không coi backup inventory là backup vật liệu khóa.
10. **Kiểm tra chất lượng connector:** API pagination, IAM scope, rate limit, retry, lỗi một vùng, snapshot consistency và event loss.

Một **discovery connector** bị cấp quyền quá rộng có thể trở thành điểm truy cập nguy hiểm ngay cả khi giao diện inventory chỉ dùng quyền đọc. Hãy phân tách credential và chặn những phương thức không cần thiết ngay tại IAM/provider.

## 12. Tình huống thực tế: kiểm kê khóa cho nền tảng thanh toán

Giả sử nền tảng có ba thành phần:

- **Payment Service:** ký sự kiện bằng Ed25519; Ledger Service phải biết đúng public key/version.
- **Billing Service:** mã hóa hóa đơn bằng AES-GCM, DEK được bọc dưới KEK trong KMS.
- **API Gateway:** dùng TLS/mTLS và chứng chỉ được quản lý bởi PKI.

### 12.1. Tạo inventory ban đầu

| Đối tượng | Owner | Phụ thuộc | Điều cần theo dõi |
| --- | --- | --- | --- |
| Signing key `payment-sign-S2` | Payment Security | Ledger Service trust store, sự kiện đã ký | Key usage, public key distribution, cửa sổ tin S1/S2, audit Sign. |
| KEK `billing-kek-v4` | Billing Security | Wrapped DEKs theo tenant và backup | Quyền Unwrap, số DEK phụ thuộc, kế hoạch rotate/rewrap. |
| DEK `invoice-A-v2` | Billing Service | Bản mã tenant A, archive, snapshot | Nonce/key usage, bản mã còn phải đọc, khả năng re-encrypt. |
| TLS identity `gateway-2026` | Platform Identity | Chứng chỉ, ingress, mTLS clients | Ngày hết hạn, trust chain, key custody và gia hạn. |

Đội vận hành thiết lập **đối soát KMS/PKI định kỳ**, đồng thời ứng dụng Billing phát hành metadata giúp truy vấn những bản mã đang phụ thuộc DEK/KEK; consumer Ledger báo nhận dạng public key được phép tin.

### 12.2. Sự cố giả định và cách inventory hỗ trợ

**Tình huống A – KEK bị nghi lộ:** Inventory tìm tất cả DEK đang `WRAPPED_BY` KEK đó, dữ liệu/backup liên quan và workload có quyền Unwrap. Đội bảo mật có căn cứ để vô hiệu hóa quyền phù hợp, chuẩn bị KEK mới, rewrap và đánh giá có cần re-encrypt khi DEK cũng bị lộ.

**Tình huống B – khóa ký cũ:** Payment Service đã chuyển từ S1 sang S2, nhưng Ledger vẫn tin S1 vô thời hạn. Inventory nhận biết **trust dependency chưa được gỡ**; policy có thể yêu cầu rút ngắn cửa sổ tin cũ, bảo vệ chữ ký lịch sử và cập nhật verifier.

**Tình huống C – hủy DEK quá sớm:** DEK invoice-A-v1 đã RETIRED nhưng snapshot cũ còn dữ liệu phụ thuộc. Inventory cảnh báo không hủy trước khi dữ liệu được di chuyển hoặc có chính sách hủy/retention phù hợp.

**Tình huống D – shadow key trong CI:** Có một secret dùng ký artifact tồn tại ngoài KMS/trust policy đã phê duyệt. Quy trình phát hiện sẽ tạo cảnh báo cho nhóm sở hữu; không chép secret vào inventory. Đội phát hành phải xác định có cần thu hồi hoặc xoay khóa và điều tra release đã ký hay không.

### 12.3. Kế hoạch kiểm tra và xử lý sự cố

Khi cần hành động khẩn cấp, inventory hỗ trợ:

1. **Khoanh vùng:** key ID/material version, thuật toán, trạng thái, owner và nơi giữ khóa.
2. **Đánh giá ảnh hưởng:** tìm ciphertext, wrapped DEK, consumer, chứng chỉ, artifacts và backups phụ thuộc.
3. **Chọn hành động:** chặn thao tác mới, giảm quyền API, rotate/rewrap/re-encrypt, cập nhật trust hoặc revoke theo chính sách.
4. **Xác minh phục hồi:** kiểm tra data restore, giải mã/xác minh lịch sử và chức năng ứng dụng.
5. **Lưu bằng chứng:** audit actor, quyết định, key refs, thời điểm, kết quả và phạm vi còn tồn tại.

**Lưu ý:** Quyết định vô hiệu hóa/hủy phải do thành phần có quyền và quy trình phê duyệt tương ứng thực hiện. Inventory cung cấp **dữ liệu ra quyết định**, không nên trở thành một công cụ có thể xóa hàng loạt key chỉ bằng một thao tác tìm kiếm.

## 13. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Chỉ lấy danh sách từ một KMS rồi tuyên bố “đã kiểm kê đầy đủ” | Bỏ sót các account, HSM, secret stores, CI và khóa ngoài hệ thống. | Định nghĩa scope, liên kết nhiều nguồn và báo độ phủ theo nguồn. |
| Sao chép private key/DEK vào bảng inventory | Tạo nơi lưu secret tập trung dễ lộ. | Chỉ lưu metadata, fingerprint công khai và tham chiếu có kiểm soát. |
| Không phân biệt key alias và material version | Giải mã dữ liệu cũ sai phiên bản hoặc không thể restore. | Lưu key ID/version thực tế của ciphertext và lịch sử alias. |
| Thiếu owner hoặc owner không còn tồn tại | Không ai chịu trách nhiệm rotate/thu hồi/hủy. | Xác nhận ownership định kỳ và có cơ chế escalation. |
| Không ghi data dependencies | Hủy KEK/DEK trong khi còn dữ liệu cần đọc. | Dependency graph gồm ciphertext, wrapped DEK, backups và consumers. |
| Thấy không có audit log rồi kết luận key không dùng | Có thể do log thiếu, retention hoặc connector thiếu quyền. | Ghi chất lượng quan sát và đối chiếu đa nguồn. |
| Coi trạng thái DISABLED của KMS là đã xóa mọi bản sao khóa | Key material còn ở backup/export/instance. | Phân biệt disable, revoke, destroy và kiểm kê bản sao hợp lệ. |
| Chỉ cập nhật inventory khi tạo key, không đồng bộ khi rotate | Metadata/trust dần sai thực tế. | Event-driven updates + periodic full reconciliation. |
| Tự động hủy khóa vì “không còn trong inventory” | Nguy cơ mất dữ liệu vĩnh viễn. | Điều tra chênh lệch và kiểm tra phụ thuộc trước hủy. |
| Không gắn quyền SIGN/UNWRAP với key usage | Cho ứng dụng dùng khóa sai mục đích hoặc quyền quá rộng. | So policy với IAM và usage thực tế. |
| Tin rằng chứng chỉ là private key | Không biết nơi lưu và mức bảo vệ khóa tương ứng. | Theo dõi certificate và private-key custody riêng. |
| Công bố inventory chi tiết cho mọi tenant | Rò rỉ kiến trúc và phạm vi dữ liệu nhạy cảm. | RBAC/ABAC, giới hạn truy vấn và log truy cập. |
| Chỉ đếm tổng số khóa để đo tuân thủ | Không biết khóa nào rủi ro và phụ thuộc dữ liệu gì. | KPI ownership, freshness, policy drift và dependencies. |
| Rotate KEK rồi bỏ qua DEK đã bị lộ | Dữ liệu cũ vẫn có thể bị giải mã. | Phân biệt rewrap với rotate DEK/re-encrypt. |
| Không theo dõi public key consumer đang tin | Khóa ký bị lộ vẫn có thể tạo chữ ký được chấp nhận. | Liên kết trusted signer, issuer và verifier policy vào inventory. |

## 14. Checklist triển khai và câu hỏi tự kiểm tra

### Checklist cho người xây dựng hệ thống

1. Phạm vi inventory có bao gồm đủ cloud accounts, regions, HSM, PKI, CI/CD, secret stores và hệ thống dữ liệu cần kiểm soát chưa?
2. Mỗi key object/**material version** có định danh rõ, owner còn hoạt động và key usage được phép không?
3. Inventory có giữ **metadata thay vì secret bytes**; các connector có quyền đọc tối thiểu không?
4. Có phân biệt DEK, KEK, signing key, identity key, MAC key, certificate và ephemeral key không?
5. Có nguồn thông tin đủ tin cậy cho state, version, owner, policy, last-used và dependencies không?
6. Dữ liệu có lưu `source`, `observedAt` và trạng thái đối soát để phân biệt “không thấy” với “không tồn tại” không?
7. Có tìm được tất cả DEK/ciphertext/backup phụ thuộc một KEK cần retire không?
8. Có biết những consumer nào còn tin một signing public key đã bị revoke không?
9. Có cảnh báo owner mất liên hệ, thuật toán yếu, quyền rộng, khóa quá hạn, drift và shadow key không?
10. Có quá trình phê duyệt, ghi audit, khôi phục và thu hồi khi xảy ra sự cố không?

### Câu hỏi tự kiểm tra

1. **Key inventory** khác **key registry** và **KMS** ở đâu?
2. Vì sao key inventory không nên lưu private key, KEK, DEK hoặc seed bí mật dạng rõ?
3. Tại sao chỉ có key ID và trạng thái ACTIVE là chưa đủ để quyết định rotate/hủy?
4. Vì sao phải lưu **key material version**, không chỉ alias `current`?
5. Một signing key S1 đã RETIRED nhưng vẫn còn chữ ký lịch sử; inventory cần theo dõi những gì?
6. Một KEK dùng wrap 10.000 DEK; nếu bị nghi lộ, dependency graph giúp xử lý ra sao?
7. Khi một bản ghi biến mất khỏi API ListKeys, có thể kết luận khóa đã bị hủy an toàn không?
8. Tỷ lệ coverage của inventory có ý nghĩa gì nếu connector chỉ có quyền đọc một cloud account?
9. Vì sao việc thiếu sự kiện trong audit log chưa chứng minh khóa không còn được sử dụng?
10. Có nên tự động xóa mọi key `DISABLED` để giảm chi phí vận hành không?
11. Khi một DEK bị lộ, rotate KEK có thay thế re-encrypt dữ liệu được không?
12. Key inventory hỗ trợ phân quyền, crypto agility và kế hoạch chuyển thuật toán như thế nào?

**Ghi nhớ:** **Key inventory** là hệ thống quan sát và quản trị **khóa mật mã cùng các quan hệ phụ thuộc**, không phải kho tập trung bí mật. Một inventory có giá trị phải ghi nhận **đúng key ID/phiên bản, thuật toán, owner, key usage, nơi lưu, trạng thái, chính sách, nguồn quan sát và ciphertext/consumer/backup phụ thuộc**, được đối soát liên tục và bảo vệ bằng quyền tối thiểu. Nhờ đó, tổ chức mới có cơ sở để **xoay vòng, thu hồi, hủy khóa, ứng phó sự cố và kiểm toán** mà không vô tình làm lộ khóa hoặc mất khả năng khôi phục dữ liệu.
