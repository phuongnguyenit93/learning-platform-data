# Phát hiện key không có owner trong Key inventory

## 1. Key không có owner là gì?

**Key không có owner (unowned key)** là khóa mật mã đang tồn tại trong hệ thống nhưng **không có chủ thể chịu trách nhiệm được xác định, có thể liên hệ và có thẩm quyền** đối với mục đích sử dụng, vòng đời, quyền truy cập và ứng phó sự cố của khóa đó.

Trong thực tế, một khóa có thể vẫn hoạt động dù nhóm từng tạo ra nó đã giải thể, ứng dụng đã ngừng triển khai hoặc metadata sở hữu bị thiếu. Đây là một **lỗ hổng quản trị**, ngay cả khi key material vẫn được bảo vệ trong KMS/HSM.

Ví dụ: khóa **payments-kek-v2** đang được dùng để giải bọc DEK cho hóa đơn lịch sử. Trường owner trống vì Payment Service đã chuyển sang nhóm khác. Nếu vận hành viên xóa khóa vì “không có người quản lý”, dữ liệu có thể không giải mã được. Nếu không ai nhận trách nhiệm, khóa có thể tồn tại quá thời hạn, giữ quyền Unwrap rộng và không được xoay vòng khi có sự cố.

Trong chương **Key inventory** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, phát hiện key không có owner là bước nối **kiểm kê tài sản mật mã** với vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**, đồng thời liên quan mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, IAM và kiểm toán.

**Mục tiêu của bài:** xác định khóa chưa có chủ thể chịu trách nhiệm, phân biệt các trường hợp không rõ ownership, tìm đủ bằng chứng để xử lý, **không tự động xóa hoặc vô hiệu hóa khóa chỉ vì thiếu owner**.

### 1.1. Phân biệt các trường hợp

| Thuật ngữ | Diễn giải | Hướng xử lý |
|---|---|---|
| **Unowned key** | Chưa có owner hợp lệ trong registry/chính sách | Tìm và chỉ định owner có trách nhiệm |
| **Unknown owner** | Có metadata nhưng không xác minh được ai thực sự chịu trách nhiệm | Đối chiếu service catalog, danh bạ và bằng chứng sử dụng |
| **Inactive owner** | Đã gán owner nhưng tài khoản/nhóm không còn hoạt động | Chuyển giao ownership qua phê duyệt |
| **Orphaned key** | Không còn liên hệ tới hệ thống/chủ thể được xác nhận, hoặc hệ thống sở hữu đã ngừng | Kiểm tra phụ thuộc, khả năng còn cần giải mã/xác minh |
| **Stale ownership** | Có owner nhưng thông tin xác nhận đã quá cũ hoặc không còn đúng | Yêu cầu tái chứng thực ownership |
| **Shared ownership ambiguous** | Nhiều nhóm cùng nhận hoặc phủ nhận trách nhiệm | Chọn một accountable owner và làm rõ các vai trò phối hợp |
| **Retired key with dependencies** | Không dùng cho dữ liệu mới nhưng vẫn cần cho dữ liệu/chữ ký cũ | Giữ quyền sử dụng lịch sử có kiểm soát; chưa được tự xóa |

**Unowned không đồng nghĩa unused**, **unused không đồng nghĩa safe to delete**, và **một tên owner được điền trong tag không tự chứng minh ownership đã hợp lệ**.

## 2. Owner của một khóa thực sự chịu trách nhiệm về điều gì?

Owner không phải chỉ là email đặt trong metadata. Đây là một **vai trò quản trị có trách nhiệm** đối với khóa cụ thể.

Một mô hình rõ ràng có thể gồm:

| Vai trò | Trách nhiệm chính | Điều cần phân biệt |
|---|---|---|
| **Accountable key owner** | Chịu trách nhiệm cuối cùng về mục đích, vòng đời, quyền, rủi ro và quyết định chuyển giao/hủy | Thường nên là nhóm hoặc đơn vị bền vững, có người đại diện |
| **Technical custodian** | Vận hành KMS/HSM, cấu hình, backup, monitoring và hỗ trợ sự cố | Có thể quản lý thiết bị nhưng không quyết định dữ liệu thuộc ai |
| **Application/service owner** | Giải thích ứng dụng nào dùng key, loại dữ liệu và ảnh hưởng nếu thay/khóa | Không nhất thiết có quyền quản trị key policy |
| **Data owner** | Chịu trách nhiệm phân loại, retention và mục đích xử lý dữ liệu | Quyết định về dữ liệu không tự trao quyền dùng private key |
| **Security approver** | Phê duyệt một số thay đổi nhạy cảm hoặc chấp nhận rủi ro | Không nhất thiết là owner lâu dài |
| **Auditor** | Xác minh trách nhiệm, thay đổi và bằng chứng | Nên độc lập với quyền sửa/hủy khóa |

**Thiết kế khuyến nghị:** mỗi key material/version quan trọng có **một accountable owner rõ ràng**, kèm **custodian** và các bên phối hợp nếu cần. Nếu doanh nghiệp dùng nhóm làm owner, danh bạ nhóm phải có người/on-call nhận cảnh báo và cơ chế thay thế khi thay đổi tổ chức.

### 2.1. Vì sao một service account không phải luôn là owner?

Một IAM principal như **svc-payments-prod** có thể được phép gọi Decrypt. Nó cho biết **ai đang sử dụng quyền**, nhưng không chứng minh ai có thẩm quyền thay policy, duyệt rotation hay quyết định xóa khóa.

Tương tự:

- Người tạo khóa (*creator*) có thể đã nghỉ việc.
- Người quản trị cloud account không nhất thiết sở hữu dữ liệu ứng dụng.
- Tag ghi **team=core** có thể đã hết hiệu lực.
- Public key hoặc certificate subject nêu danh tính chứng chỉ, không thay thế người chịu trách nhiệm quản lý private key.

Vì vậy, việc phát hiện owner không thể chỉ lấy **createdBy** hoặc IAM caller rồi tự gán làm owner.

### 2.2. Gán owner ở cấp nào?

Tùy hệ thống, cần theo dõi ở các cấp khác nhau:

~~~text
Organization / business unit
            |
        Service / tenant
            |
       Logical key ID / alias
            |
       Material version v1
            |
       Material version v2
            |
     Data / signature dependencies
~~~

Owner của **logical key** có thể kế thừa xuống các **material versions**, nhưng phải có quy tắc rõ ràng. Khi một version cũ được giữ để giải mã lịch sử, owner của v2 có thể thay đổi dù alias đã trỏ sang v3.

**Không gộp các phiên bản có trạng thái và phụ thuộc khác nhau vào một bản ghi duy nhất** nếu điều đó làm mất khả năng kiểm toán hoặc quyết định hủy.

## 3. Tại sao key không có owner nguy hiểm?

| Nhóm rủi ro | Biểu hiện |
|---|---|
| **Bí mật dữ liệu** | Không ai giới hạn Decrypt/Unwrap, khóa HMAC tồn tại quá lâu, các principal cũ vẫn có quyền |
| **Giả mạo danh tính** | Private signing key chưa được rotate/revoke, verifier vẫn tin public key/certificate cũ |
| **Tính sẵn sàng** | Khóa bị xóa khi còn ciphertext, encrypted DEK hoặc backup phụ thuộc |
| **Quản lý vòng đời** | Không có người quyết định cryptoperiod, rotation, disable, revocation và destruction |
| **IAM** | Không ai rà soát key policy, quyền cross-account, service principals và break-glass |
| **Kiểm toán** | Không xác định được ai phê duyệt tạo/sử dụng/thay đổi khóa |
| **Ứng phó sự cố** | Khó khoanh vùng owner, consumer, dữ liệu và người ra quyết định |
| **Tuân thủ/quản trị** | Thiếu bằng chứng về trách nhiệm, phân loại và retention |
| **Chi phí/độ phức tạp** | Khóa không dùng vẫn tồn tại, nhưng việc dọn dẹp bừa bãi có thể phá hệ thống |

**Hai nguy cơ đối nghịch** phải cân bằng: giữ một khóa rủi ro mà không ai chăm sóc, và xóa nhầm khóa vẫn bảo vệ dữ liệu quan trọng. Do đó workflow phát hiện phải ưu tiên **xác minh phụ thuộc và ownership**, không dùng auto-delete để “làm sạch KPI”.

## 4. Phạm vi kiểm kê: những loại key nào cần tìm owner?

Không phải mọi byte tạm thời trong RAM đều cần một bản ghi inventory riêng. Nhưng **khóa được quản lý, sử dụng lâu dài, có ảnh hưởng đến dữ liệu/danh tính hoặc có phiên bản** thường cần ownership.

| Loại tài sản | Owner nên được xác định ở đâu? | Điểm đặc thù |
|---|---|---|
| **KEK trong KMS/HSM** | Key registry + data/service owner | Một KEK có thể bảo vệ nhiều encrypted DEK và tenant |
| **DEK dài hạn hoặc có bản mã lưu trữ** | Registry/metadata dataset, service hoặc tenant chịu trách nhiệm | Phải lần được encrypted DEK, object và KEK phụ thuộc |
| **Private signing key** | Dịch vụ phát hành/chủ thể sở hữu danh tính + key custodian | Phải kiểm tra certificate, JWKS, trust store, revocation |
| **Public verification key / certificate** | Hệ thống quản lý danh tính và verifier policy | Không phải bí mật nhưng cần xác định nguồn tin cậy và retention |
| **HMAC/PSK secret** | Chủ hệ thống phát hành và consumer | Các bên giữ chung secret có thể tạo MAC, cần quản lý phân phối |
| **RSA/ECDH key được quản lý** | Dịch vụ và giao thức sử dụng | Phân biệt key usage và phạm vi tồn tại |
| **Secrets trong vault/keystore** | Service owner + secret custodian | Phải xác nhận đó là khóa mật mã, không chỉ một chuỗi cấu hình |
| **Khóa phục hồi/backup** | Chủ hệ thống khôi phục và bộ phận an ninh | Có thể có quyền giải mã phạm vi rộng, cần dual control |
| **Ephemeral session key của TLS** | Quy trình thư viện/protocol và service owner, không nhất thiết từng session | Tập trung vào cấu hình nguồn ngẫu nhiên, retention và policy, thay vì ghi mỗi phiên vào registry |

**Chọn ranh giới đúng:** một khóa ephemeral phát sinh hàng triệu lần không cần tạo hàng triệu bản ghi ownership. Nhưng **static signing key, KMS key, long-lived DEK/KEK, HMAC secret, backup key** cần có một vòng đời nhận diện được.

## 5. Nguồn dữ liệu để phát hiện owner

Một phát hiện đáng tin thường cần **liên kết nhiều nguồn**, không dựa hoàn toàn vào tag của một hệ thống.

| Nguồn | Có thể lấy metadata gì? | Giới hạn |
|---|---|---|
| **KMS API / key metadata** | Key ID, algorithm, usage, origin, creation date, enabled state, aliases/tags, policy | Tag có thể thiếu/sai; trạng thái không mô tả tất cả consumer |
| **HSM inventory** | Key handle/label, slot, purpose, non-exportable policy, creator/custodian | Danh tính kinh doanh có thể không nằm trong HSM |
| **Secret manager/vault** | Secret path, metadata version, tags, ACL, service references | Không phải mọi secret đều là key; một secret có thể chứa nhiều giá trị |
| **PKI/certificate manager** | Certificate ID, subject, issuer, expiry, key reference, renewal workflow | Subject không đủ xác minh accountable key owner |
| **Service catalog/CMDB** | Service ID, owner team, business criticality, lifecycle, environment | Catalog có thể cập nhật chậm hoặc không liên kết key |
| **IAM/directory** | Team/principal có tồn tại, đang active không, quyền và vai trò | Có quyền dùng khóa không đồng nghĩa owner |
| **Audit logs** | Gần đây ai gọi Encrypt/Decrypt/Sign/Unwrap, từ workload nào | Không đủ chứng minh ownership; thiếu log không chứng minh không dùng |
| **IaC/deployment metadata** | Key resource đang được ứng dụng nào khai báo/sử dụng | Khai báo có thể khác thực tế, có workload đã triển khai từ lâu |
| **Data catalog/backup inventory** | Dataset, encrypted DEK, backup và data-retention dependencies | Có thể chưa bao phủ dữ liệu ngoại tuyến hoặc lưu trữ cũ |
| **Incident/change system** | Ai duyệt tạo/rotate/revoke, lý do và người liên hệ | Ticket cũ không luôn phản ánh owner hiện tại |

### 5.1. Khám phá tài sản và bảo vệ quyền truy cập

Một scanner kiểm kê nên **chỉ đọc metadata cần thiết** qua quyền read-only, không cần Decrypt, ExportKey hoặc đọc plaintext DEK. Phân tách quyền:

- **Inventory collector:** List/Describe/GetMetadata và đọc audit metadata.
- **Ownership resolver:** đối chiếu service catalog, directory, approval workflow.
- **Security reviewer:** xem findings và evidence, đánh giá rủi ro.
- **Key operator:** thực hiện thay đổi key policy hoặc state **sau khi được phê duyệt**.

Nếu các API khác nhau buộc phải dùng quyền đặc biệt, cần giới hạn phạm vi và kiểm toán độc lập. **Không quét nội dung bí mật bằng cách dump tất cả private keys hoặc DEK về một máy chỉ để nhận diện owner.**

### 5.2. Bao phủ tài khoản, vùng và môi trường

Một inventory chỉ liệt kê **một cloud account ở một region** sẽ bỏ sót KMS keys, backups hoặc HSM ở phạm vi khác. Thiết kế phải có danh sách **scope** gồm account/project/subscription, region, tenant, environment và provider.

Ngoài metadata kết quả, lưu **thời điểm thu thập, độ phủ và lỗi**: thiếu quyền ở một vùng phải được báo **SCAN_INCOMPLETE**, không được suy rằng vùng đó không có khóa.

## 6. Metadata tối thiểu để đánh giá ownership

Một bản ghi key inventory nên chứa các trường tối thiểu sau:

| Nhóm | Trường gợi ý | Mục đích |
|---|---|---|
| **Identity** | provider, accountId, region, keyId, materialVersion, alias | Định danh duy nhất và tránh gộp các khóa trùng tên |
| **Classification** | keyType, algorithm, keyUsage, purpose, environment, tenantScope | Đánh giá tác động và chính sách |
| **Ownership** | accountableTeamId, technicalCustodianId, serviceId, contactRoute | Xác định người chịu trách nhiệm và kênh liên hệ |
| **Validation** | ownerVerifiedAt, verifiedBy, evidenceRef, ownershipSource | Biết owner được xác minh bằng bằng chứng nào và từ khi nào |
| **Lifecycle** | createdAt, activatedAt, state, cryptoperiod, rotationDueAt | Xử lý expiry, rotation, revocation |
| **Access** | policyRef, allowedPrincipals, lastObservedUseAt | Phát hiện quyền và sử dụng; không kết luận an toàn chỉ từ last-used |
| **Dependencies** | encryptedDekCount, datasetRefs, certificateRefs, backupRefs | Ngăn hủy nhầm khi còn dữ liệu/chữ ký phụ thuộc |
| **Scan** | discoveredAt, lastSeenAt, scanScope, scanStatus | Chứng minh kết quả còn mới và phạm vi quét |

Một ví dụ **chỉ lưu metadata, không lưu key material**:

~~~yaml
# Ví dụ quy ước nội bộ, không phải schema KMS bắt buộc.
provider: managed-kms
accountId: prod-platform-01
region: ap-southeast-1
keyId: payments-kek
materialVersion: v2
algorithm: AES-256-KEY-WRAP
keyUsage: wrap-dek
environment: production
serviceId: payment-service
accountableTeamId: ""
technicalCustodianId: platform-security
state: RETIRED
createdAt: "2025-04-12T09:00:00Z"
ownerVerifiedAt: null
lastObservedUseAt: "2026-11-21T10:35:00Z"
encryptedDekCount: 1842
scanStatus: COMPLETE
~~~

**Kết luận từ ví dụ:** owner trống là một finding. Nhưng khóa vẫn có **1.842 encrypted DEK phụ thuộc** và còn được dùng gần đây; tuyệt đối không suy rằng có thể xóa khóa.

### 6.1. Key ID và version là khóa định danh, không phải owner

Tên alias như **payments-kek** dễ hiểu nhưng có thể trỏ sang vật liệu khác sau rotation. Một khóa của cùng tên ở hai account khác nhau cũng không phải cùng tài sản.

Inventory cần định danh bằng tổ hợp **provider + account/tenant + location + keyId + materialVersion** hoặc một ID ổn định tương đương. Khi provider không cung cấp version vật liệu công khai, phải ghi lại mô hình version thực tế của hệ thống và tránh tự tạo thông tin không có bằng chứng.

## 7. Tiêu chí phát hiện key không có owner

Có thể chia findings thành nhiều nhóm thay vì nhét tất cả vào một cờ boolean:

| Mã finding | Điều kiện | Ví dụ |
|---|---|---|
| **MISSING_OWNER** | Không có accountable owner/team ID hợp lệ | Trường owner rỗng/null |
| **UNKNOWN_OWNER** | Owner ID có giá trị nhưng không tồn tại trong directory/catalog | Tag team=legacy-ops đã bị xóa |
| **INACTIVE_OWNER** | Owner/team không còn active hoặc không có người nhận trách nhiệm | Nhóm đã giải thể |
| **OWNER_NOT_CONFIRMED** | Chưa có bằng chứng chấp nhận ownership hoặc thời hạn xác minh đã quá | Owner tag vừa thêm nhưng không được phê duyệt |
| **STALE_OWNER_ATTESTATION** | Owner verification quá hạn theo chính sách | Lần cuối xác nhận từ nhiều năm trước |
| **SERVICE_DECOMMISSIONED** | Service gắn với key đã decommissioned nhưng key còn tồn tại | Dịch vụ đã ngừng, KEK vẫn có quyền |
| **AMBIGUOUS_OWNER** | Nhiều owner xung đột hoặc dữ liệu từ các nguồn không nhất quán | KMS tag team-A, CMDB team-B |
| **INVENTORY_INCOMPLETE** | Scanner không truy cập được nguồn cần thiết để xác nhận | Lỗi quyền đọc HSM/region |
| **UNRESOLVED_DEPENDENCY** | Key chưa xác định rõ nơi sử dụng/phụ thuộc | Không có reference nhưng vẫn xuất hiện audit calls |

**Điểm cốt lõi:** những mã này là **dấu hiệu cần điều tra**, không phải một quyết định hủy khóa tự động.

### 7.1. Thứ tự kiểm tra nên áp dụng

1. Chuẩn hóa **key identity** để loại trùng bản ghi.
2. Kiểm tra **phạm vi quét** có đủ và dữ liệu còn mới không.
3. Kiểm tra **accountable owner** không null/blank.
4. Đối chiếu owner ID với **directory/team registry**.
5. Kiểm tra owner/team **đang hoạt động và có kênh liên hệ**.
6. Đối chiếu **service ID và service owner** trong service catalog.
7. Kiểm tra **bằng chứng ownership attestation** và thời điểm xác minh.
8. Đối chiếu **IAM usage, audit, IaC, encrypted DEK/certificate dependencies**.
9. Ghi findings với **evidence, mức tin cậy, severity, người được giao xử lý và SLA**.

Một owner trống có thể được gợi ý bằng service catalog, nhưng không tự “sửa” registry trước khi **người có thẩm quyền nhận trách nhiệm**.

## 8. Phát hiện tự động bằng pipeline kiểm kê

~~~mermaid
flowchart TD
    K["KMS/HSM & secret metadata"] --> N["Chuẩn hóa key inventory"]
    I["IAM & audit usage"] --> N
    C["Service catalog / team directory"] --> N
    D["Data catalog / encrypted DEK refs"] --> N
    N --> Q["Kiểm tra coverage & data freshness"]
    Q --> R["Resolver: owner, service, custodian"]
    R --> F["Rule engine: missing/invalid/stale/ambiguous"]
    F --> S["Risk scoring + evidence"]
    S --> T["Finding / ticket / owner confirmation"]
    T --> V["Gán owner & kiểm chứng phụ thuộc"]
    V --> A["Update registry + audit + tái quét"]
~~~

Pipeline cần có hai tính chất:

- **Repeatable:** chạy lại cùng dữ liệu không tạo hàng loạt ticket trùng; key ID/version + finding type là khóa định danh phù hợp cho issue.
- **Evidence-based:** kết quả cho biết nguồn nào, thời điểm nào, trường nào thiếu, nguồn nào mâu thuẫn và hành động tiếp theo được đề xuất.

### 8.1. Phân biệt authoritative source và tín hiệu suy đoán

Ví dụ **service catalog** là nơi quy định owner của dịch vụ; **KMS tag** là nhãn do người tạo hoặc IaC gắn; **audit log** cho biết principal sử dụng; **Git/IaC** cho biết ai từng tạo cấu hình.

Có thể sắp xếp mức tin cậy theo quy ước:

| Bằng chứng | Giá trị | Không được kết luận |
|---|---|---|
| Owner đã attested qua workflow được duyệt | Có trách nhiệm được xác nhận tại thời điểm attestation | Không bảo đảm owner còn active nếu dữ liệu cũ |
| Service catalog với owner/team active | Có ứng viên owner tốt | Không chứng minh service thật sự chịu trách nhiệm key cụ thể |
| KMS tag owner/team | Hữu ích để tra cứu | Không tự chứng minh tag chưa lỗi thời |
| IAM principal có quyền Decrypt/Sign | Cho biết bề mặt sử dụng | Quyền không đồng nghĩa ownership |
| Audit principal vừa dùng key | Có consumer thực tế đáng liên hệ | Người gọi gần nhất không nhất thiết là accountable owner |
| Tác giả IaC/creator | Giúp truy vết lịch sử | Creator có thể là automation hoặc đã nghỉ việc |

Nếu hai nguồn uy tín mâu thuẫn, tạo finding **AMBIGUOUS_OWNER** để duyệt, không chọn ngẫu nhiên bên mới hơn.

## 9. Tránh false positive khi phát hiện

Một máy quét quá đơn giản thường tạo nhiều cảnh báo không hữu ích:

**Trường hợp 1: khóa mới tạo.** Vừa GenerateKey có thể chưa kịp hoàn thành provisioning metadata. Có thể quy định **grace period ngắn** để chờ đăng ký owner, nhưng phải có người chịu trách nhiệm tạm trong workflow và không kích hoạt production nếu chính sách yêu cầu owner đầy đủ.

**Trường hợp 2: khóa retired.** Ít hoặc không có Encrypt/Sign mới là điều bình thường. Nhưng vẫn có Decrypt/Verify cho dữ liệu lịch sử. Đừng gọi là unused chỉ vì last encryption đã lâu.

**Trường hợp 3: key version kế thừa owner.** Một material version cũ có thể kế thừa ownership của logical key, miễn chính sách kế thừa minh bạch, owner thực sự đã chấp nhận và inventory không mất các thông tin version riêng.

**Trường hợp 4: không có audit gần đây.** Có thể vì dữ liệu lưu trữ chỉ được đọc theo quý hoặc log chưa bao phủ mọi region. Không dùng điều kiện “không thấy lời gọi trong 30 ngày” để tự kết luận khóa không cần thiết.

**Trường hợp 5: chứng chỉ đã hết hạn.** Certificate expiry không có nghĩa private key đã hủy, cũng không chứng minh không còn chữ ký lịch sử cần xác minh.

**Trường hợp 6: khóa trong môi trường thử nghiệm.** Vẫn cần owner và chính sách phù hợp; chỉ khác mức ưu tiên so với khóa production chứa dữ liệu nhạy cảm.

**Trường hợp 7: workload dùng service account chung.** Cần ánh xạ tới ứng dụng và accountable owner. Không gán owner là email robot chỉ vì robot thực hiện GenerateKey.

## 10. Risk scoring để ưu tiên điều tra

Không phải mọi key không có owner đều có cùng rủi ro. Một khóa production có quyền Unwrap nhiều DEK nên được xử lý trước một secret test đã vô hiệu hóa và không còn consumer.

Một mô hình điểm minh họa, **không phải chuẩn bảo mật bắt buộc**:

| Yếu tố | Điểm |
|---|---:|
| Khóa production hoặc môi trường quan trọng | +3 |
| Key dùng Decrypt/Unwrap hoặc Sign sản xuất | +3 |
| Có dữ liệu/credential/consumer đang phụ thuộc | +3 |
| IAM permission rộng, cross-account hoặc public exposure không phù hợp | +2 |
| Có sử dụng gần đây qua audit đáng tin | +2 |
| Owner không tồn tại hoặc team đã giải thể | +2 |
| Khóa đang retired/disabled nhưng chưa rõ phụ thuộc | +1 |

Có thể dùng tổng điểm để **xếp hàng điều tra**, ví dụ 10+ ưu tiên cao, 5–9 trung bình, ít hơn 5 ưu tiên thấp hơn. Ngưỡng này chỉ là ví dụ cần được hiệu chỉnh theo tổ chức. **Không cộng điểm rồi tự động disable/delete**.

### 10.1. Cần tách độ nghiêm trọng khỏi độ tin cậy bằng chứng

- **Severity:** nếu giả định owner không có và key bị lạm dụng/xóa, hậu quả có thể lớn đến đâu?
- **Evidence confidence:** dữ liệu để kết luận finding đã đầy đủ, mới và có thể xác minh không?

Ví dụ một key có vẻ đang bảo vệ 10.000 bản ghi nhưng scanner thiếu quyền đọc KMS policy: **severity có thể cao, confidence thấp**. Nên ưu tiên bổ sung dữ liệu trước khi đưa ra hành động phá hủy.

## 11. SQL: tìm owner thiếu, không hợp lệ hoặc không active

Giả sử một kho inventory dùng các bảng **key_asset**, **team_directory**, **service_catalog**. Mỗi bản ghi key_asset chỉ chứa metadata, không chứa plaintext key material.

~~~sql
-- Lược đồ minh họa, cú pháp gần PostgreSQL.
CREATE TABLE team_directory (
    team_id VARCHAR(120) PRIMARY KEY,
    is_active BOOLEAN NOT NULL
);

CREATE TABLE service_catalog (
    service_id VARCHAR(120) PRIMARY KEY,
    owner_team_id VARCHAR(120),
    is_active BOOLEAN NOT NULL
);

CREATE TABLE key_asset (
    provider VARCHAR(50) NOT NULL,
    account_id VARCHAR(120) NOT NULL,
    region VARCHAR(80) NOT NULL,
    key_id VARCHAR(200) NOT NULL,
    material_version VARCHAR(80) NOT NULL,
    service_id VARCHAR(120),
    accountable_team_id VARCHAR(120),
    lifecycle_state VARCHAR(40) NOT NULL,
    environment VARCHAR(40) NOT NULL,
    last_seen_at TIMESTAMP NOT NULL,
    owner_verified_at TIMESTAMP,
    PRIMARY KEY (
        provider, account_id, region, key_id, material_version
    )
);
~~~

Truy vấn phát hiện **owner thiếu/không tồn tại/không active**:

~~~sql
SELECT
    k.provider, k.account_id, k.region,
    k.key_id, k.material_version, k.lifecycle_state,
    k.accountable_team_id, k.service_id,
    CASE
        WHEN k.accountable_team_id IS NULL
             OR TRIM(k.accountable_team_id) = ''
            THEN 'MISSING_OWNER'
        WHEN t.team_id IS NULL
            THEN 'UNKNOWN_OWNER'
        WHEN t.is_active = FALSE
            THEN 'INACTIVE_OWNER'
        ELSE 'VALID'
    END AS ownership_finding
FROM key_asset AS k
LEFT JOIN team_directory AS t
    ON t.team_id = k.accountable_team_id
WHERE k.lifecycle_state <> 'DESTROYED'
  AND (
      k.accountable_team_id IS NULL
      OR TRIM(k.accountable_team_id) = ''
      OR t.team_id IS NULL
      OR t.is_active = FALSE
  );
~~~

**Giải thích:**

- **LEFT JOIN** giữ cả key không tìm thấy bản ghi owner trong directory.
- Kiểm tra **NULL và blank** để phát hiện thiếu owner.
- Không coi một team ID đã bị xóa là hợp lệ chỉ vì tag vẫn còn.
- Không loại hết key **RETIRED/REVOKED**, vì chúng có thể còn phụ thuộc và cần owner điều phối.
- Loại DESTROYED chỉ khi inventory có bằng chứng hủy thật; nếu trạng thái hủy chưa xác minh, phải quản lý như finding khác.

Truy vấn trên **chưa kiểm tra owner attestation, service decommissioned, stale scan hoặc phân quyền IAM**. Cần thêm các rules riêng.

### 11.1. Phát hiện service đã ngừng hoạt động

~~~sql
SELECT k.key_id, k.material_version, k.service_id,
       s.owner_team_id AS candidate_team_id
FROM key_asset k
LEFT JOIN service_catalog s ON s.service_id = k.service_id
WHERE k.lifecycle_state <> 'DESTROYED'
  AND (
      k.service_id IS NULL
      OR s.service_id IS NULL
      OR s.is_active = FALSE
  );
~~~

**candidate_team_id không phải owner được xác nhận.** Nếu service đã decommissioned, team cũ có thể hỗ trợ điều tra, nhưng cần một owner mới hoặc người chấp nhận trách nhiệm hợp lệ.

### 11.2. Không biến scanner thành người quyết định hủy

SQL giúp tạo **finding**, không cho biết khóa có thể xóa an toàn hay chưa. Muốn đề xuất hủy còn phải kiểm tra **encrypted DEK, ciphertext, backups, certificate usage, retention, legal hold, IAM và phê duyệt**.

## 12. Java 17: phát hiện key không có owner theo dữ liệu inventory

Ví dụ sau minh họa **logic phát hiện metadata** không phụ thuộc SDK cloud. Chương trình không gọi KMS, không xuất khóa và **không thay đổi trạng thái key**; nó chỉ tạo findings để người có quyền xem xét.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class UnownedKeyDetector {

    enum Issue {
        MISSING_OWNER,
        UNKNOWN_OWNER,
        INACTIVE_OWNER,
        STALE_ATTESTATION,
        UNKNOWN_SERVICE,
        SERVICE_DECOMMISSIONED,
        INCOMPLETE_SCAN
    }

    record Team(String id, boolean active) {}

    record Service(String id, boolean active, String ownerTeamId) {}

    record KeyAsset(
        String keyId,
        String materialVersion,
        String environment,
        String lifecycleState,
        String accountableTeamId,
        String serviceId,
        Instant ownerVerifiedAt,
        boolean scanComplete
    ) {}

    record Finding(
        String keyRef,
        String priority,
        Set<Issue> issues
    ) {}

    private static boolean blank(String s) {
        return s == null || s.isBlank();
    }

    static List<Finding> detect(
        List<KeyAsset> assets,
        Map<String, Team> teams,
        Map<String, Service> services,
        Instant now
    ) {
        List<Finding> findings = new ArrayList<>();
        Instant verificationLimit = now.minus(Duration.ofDays(180));

        for (KeyAsset key : assets) {
            // Khóa thực sự đã hủy chỉ còn theo dõi trong audit/retention.
            if ("DESTROYED".equals(key.lifecycleState())) {
                continue;
            }

            EnumSet<Issue> issues = EnumSet.noneOf(Issue.class);

            if (!key.scanComplete()) {
                issues.add(Issue.INCOMPLETE_SCAN);
            }

            if (blank(key.accountableTeamId())) {
                issues.add(Issue.MISSING_OWNER);
            } else {
                Team owner = teams.get(key.accountableTeamId());
                if (owner == null) {
                    issues.add(Issue.UNKNOWN_OWNER);
                } else if (!owner.active()) {
                    issues.add(Issue.INACTIVE_OWNER);
                }
            }

            if (key.ownerVerifiedAt() == null
                    || key.ownerVerifiedAt()
                          .isBefore(verificationLimit)) {
                issues.add(Issue.STALE_ATTESTATION);
            }

            if (blank(key.serviceId())
                    || !services.containsKey(key.serviceId())) {
                issues.add(Issue.UNKNOWN_SERVICE);
            } else if (!services.get(key.serviceId()).active()) {
                issues.add(Issue.SERVICE_DECOMMISSIONED);
            }

            if (!issues.isEmpty()) {
                // Đơn giản hóa chỉ để xếp hàng xử lý, không tính
                // rủi ro thật nếu chưa biết usage/dependencies.
                boolean critical = "production".equalsIgnoreCase(
                    key.environment()
                ) && (
                    issues.contains(Issue.MISSING_OWNER)
                    || issues.contains(Issue.UNKNOWN_OWNER)
                    || issues.contains(Issue.INACTIVE_OWNER)
                );

                findings.add(new Finding(
                    key.keyId() + "/" + key.materialVersion(),
                    critical ? "HIGH_REVIEW" : "REVIEW",
                    Set.copyOf(issues)
                ));
            }
        }
        return findings;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-28T02:00:00Z");

        Map<String, Team> teams = Map.of(
            "platform-security", new Team("platform-security", true),
            "legacy-payments", new Team("legacy-payments", false)
        );

        Map<String, Service> services = Map.of(
            "payment-service",
            new Service("payment-service", true, "platform-security"),
            "legacy-billing",
            new Service("legacy-billing", false, "legacy-payments")
        );

        List<KeyAsset> assets = List.of(
            new KeyAsset(
                "payments-kek", "v2", "production", "RETIRED",
                "", "legacy-billing", null, true
            ),
            new KeyAsset(
                "orders-signing", "v5", "production", "ACTIVE",
                "platform-security", "payment-service",
                now.minus(Duration.ofDays(30)), true
            )
        );

        for (Finding finding :
                detect(assets, teams, services, now)) {
            // Chỉ in ID/metadata, không in key material.
            System.out.println(finding);
        }
    }
}
~~~

### 12.1. Những gì ví dụ đã làm được

- Kiểm tra **owner trống, không tồn tại hoặc inactive**.
- Đối chiếu **service lifecycle** để phát hiện service đã ngừng.
- Kiểm tra **owner attestation cũ** theo ngưỡng minh họa 180 ngày.
- Phân biệt **scan incomplete** với kết luận owner chính xác.
- Tạo **findings dạng metadata**, không gọi Disable/Delete/ExportKey.
- Giữ lại key đang **RETIRED** trong phạm vi đánh giá, vì có thể cần đọc dữ liệu cũ.

### 12.2. Giới hạn của ví dụ

- Hai khóa có cùng keyId/version ở account hoặc region khác nhau có thể bị trùng trong chuỗi keyRef; production phải dùng **định danh chuẩn hóa đầy đủ**.
- Ngưỡng **180 ngày** là ví dụ; tổ chức cần quy định theo rủi ro.
- Không có **IAM entitlements, usage logs, dependency graph, evidence confidence, approval workflow** hay dữ liệu từ SDK KMS.
- Một service active có thể có owner khác; ví dụ chỉ ghi finding, không tự gán service owner vào key.
- Không cập nhật database hoặc KMS, nên **không thực hiện remediation**.
- Mã giả định scanner và directory đưa dữ liệu đáng tin; production phải có xác thực nguồn và kiểm tra freshness.

**Điểm an toàn:** Công cụ tìm key không có owner trước hết nên là **read-only detector**. Khi cần thay metadata/quyền/trạng thái, chuyển sang workflow đã phê duyệt với audit rõ ràng.


## 13. Từ finding đến owner được xác nhận

Phát hiện key không có owner chỉ là bước đầu. Mục tiêu tiếp theo là **chuyển một cảnh báo thành ownership có trách nhiệm và có bằng chứng**, không phải đơn giản gán trường owner cho hết trống.

### 13.1. Quy trình xác minh ownership

~~~mermaid
flowchart TD
    F["Finding: key chưa có owner hợp lệ"] --> E["Thu thập evidence & dependency"]
    E --> C["Liên hệ service/data owner ứng viên"]
    C --> D{"Có người nhận trách nhiệm?"}
    D -->|Có| A["Kiểm tra quyền, purpose, cryptoperiod"]
    A --> P["Phê duyệt chuyển/gán ownership"]
    P --> R["Cập nhật registry + contact/on-call"]
    R --> V["Tái quét, lưu attestation và audit"]
    D -->|Không| S["Escalate đến security/risk owner"]
    S --> T["Tạm quản lý rủi ro, giới hạn thay đổi"]
    T --> E
~~~

Một hồ sơ xử lý nên trả lời:

1. **Key nào?** Provider/account/region/key ID/material version, algorithm, environment.
2. **Mục đích gì?** Encrypt, Decrypt, Sign, Unwrap, HMAC, key agreement, recovery.
3. **Dữ liệu/danh tính nào phụ thuộc?** Encrypted DEK, ciphertext, certificate, token, backup, ứng dụng đang gọi KMS.
4. **Ai đã tạo và ai dùng?** Bằng chứng KMS audit/IaC/deployment, không tự suy creator/consumer thành owner.
5. **Ai nhận trách nhiệm?** Team hiện còn hoạt động, đại diện/on-call và phạm vi quyền.
6. **Phê duyệt nào?** Owner mới, security reviewer và data owner khi rủi ro yêu cầu.
7. **Ngày tái xác nhận?** Owner attestation, thời hạn rà soát và escalation nếu không phản hồi.

### 13.2. Không được tự gán owner chỉ vì ứng viên được suy ra

Nếu KMS tag là team-A, service catalog ghi team-B và audit cho thấy một service của team-C vừa gọi Decrypt, scanner phải ghi **ownerCandidates** với nguồn chứng cứ riêng. Việc chọn owner cuối cùng là **quyết định quản trị được xác minh**, trừ khi tổ chức đã thiết kế một quy tắc gán mang tính thẩm quyền được phê duyệt.

Một event minh họa sau khi xác minh:

~~~json
{
  "eventType": "KEY_OWNER_ASSIGNED",
  "keyRef": "managed-kms/prod-platform-01/ap-southeast-1/payments-kek/v2",
  "previousOwner": null,
  "newAccountableTeamId": "payments-platform",
  "technicalCustodianId": "platform-security",
  "evidenceRefs": ["catalog-service-284", "change-9021"],
  "approvedBy": "security-review-workflow",
  "attestedAt": "2026-11-28T03:00:00Z",
  "verificationDueAt": "2027-02-28T03:00:00Z"
}
~~~

Đây là dữ liệu minh họa. Một hệ thống thật còn cần **actor identity, operation ID, revision, policy version** và khả năng lưu audit chống sửa đổi trái phép.

### 13.3. Nếu không tìm được owner ngay?

Có thể đặt khóa vào **quy trình quản lý tạm thời**:

- Gắn finding **OWNER_UNRESOLVED**, trạng thái xử lý và một **risk coordinator** được ủy quyền.
- Hạn chế quyền **thay key policy, tạo grant mới, rotate hoặc delete** tùy mức độ và khả năng ảnh hưởng.
- Thực hiện giám sát các lời gọi **Decrypt/Sign/Unwrap** và các principal sử dụng.
- Giao deadline/escalation tới owner của tài sản cấp cao hơn, ví dụ chủ cloud account hoặc business unit.
- Không tự nhận rằng **risk coordinator** là accountable owner lâu dài nếu họ chỉ xử lý sự cố tạm thời.
- Không tự vô hiệu hóa một KEK đang bảo vệ backup hoặc dữ liệu có nghĩa vụ lưu giữ.

**Tài sản chưa rõ owner không thể bị bỏ quên chỉ vì đã có người theo dõi finding.** Cần có kế hoạch kết thúc bằng một trong các kết quả: owner được xác nhận, khóa được chuyển giao, khóa được retired/revoked theo policy hoặc hủy an toàn sau khi đã giải quyết phụ thuộc.

## 14. Dependency graph: điều kiện bắt buộc trước khi xử lý key mồ côi

Muốn quyết định một khóa có thể nghỉ hưu hoặc hủy không, phải hiểu **những gì sẽ mất khả năng hoạt động khi khóa biến mất**.

~~~mermaid
flowchart TD
    O["Accountable owner / service"] --> K["KEK trong KMS"]
    K --> D1["Encrypted DEK - dataset A"]
    K --> D2["Encrypted DEK - dataset B"]
    D1 --> C1["Ciphertext A & backup A"]
    D2 --> C2["Ciphertext B & archive B"]
    O --> S["Signing key trong HSM"]
    S --> CERT["Certificate / public key"]
    CERT --> V1["Verifier service"]
    CERT --> V2["External partner"]
    S --> HIST["Chữ ký lịch sử / chứng từ"]
~~~

Trong sơ đồ, mũi tên biểu thị **quan hệ phụ thuộc hoặc trách nhiệm**, không có nghĩa KEK mã hóa trực tiếp plaintext của dataset. KEK bảo vệ DEK; DEK mới là khóa mã hóa dữ liệu bằng AES-GCM hoặc cơ chế phù hợp.

### 14.1. Với KEK

Cần xác định:

- Những **encrypted DEK** nào được wrap dưới KEK đó, ở dataset/tenant nào.
- Các bản sao backup, archive hoặc vùng DR có còn phụ thuộc không.
- Ứng dụng nào gọi **Unwrap/Decrypt** và theo lịch nào.
- Có cơ chế **rewrap** sang KEK mới đã được kiểm chứng chưa.
- Khi kiểm tra thử restore, dữ liệu có thể giải mã được bằng đường khóa mới không.

**Rotation KEK** có thể chỉ cần rewrap DEK nếu DEK chưa bị lộ và cơ chế hỗ trợ. **Hủy KEK trước khi rewrap** có thể làm dữ liệu không thể khôi phục.

### 14.2. Với DEK

Cần xác định ciphertext và metadata AEAD liên quan: **nonce/IV, authentication tag, AAD, key reference, backup**. Khi thay DEK, dữ liệu thường phải được **mã hóa lại** bằng DEK mới. Chỉ thay wrapping KEK không khắc phục việc plaintext DEK cũ đã bị lộ.

### 14.3. Với signing key

Cần tìm:

- Ai còn gọi **Sign** dưới private key.
- Public key/chứng chỉ tương ứng được phân phối tới **verifier/trust store/JWKS** nào.
- Chữ ký/token/chứng từ lịch sử cần xác minh bao lâu.
- Certificate expiry/revocation và bằng chứng thời gian được xử lý như thế nào.
- Có kế hoạch phát hành key version mới và cập nhật mọi verifier chưa.

**Hủy private signing key không nhất thiết làm mất khả năng Verify bằng public key**, nhưng việc rút niềm tin đối với khóa cũ và đánh giá chữ ký lịch sử phải tuân thủ policy. Public key không cần bí mật song vẫn có **owner và trách nhiệm quản lý trust**.

### 14.4. Với HMAC/PSK

Một HMAC/PSK secret có thể được sao chép cho nhiều bên. Mọi bên biết bí mật đều có khả năng tạo MAC tương ứng. Vì vậy cần kiểm kê:

- Bên phát hành và từng consumer đang giữ secret.
- Kênh phân phối, phiên bản và lịch rotation đồng bộ.
- Secret có được lưu trong vault hoặc hard-code ở nơi khác không.
- Có cách chặn chấp nhận tag từ phiên bản bị lộ không.

Không coi một service duy nhất nhìn thấy trong audit là owner của mọi bản sao HMAC key.

## 15. Playbook xử lý theo trạng thái và mức độ rủi ro

Một finding cần được điều phối dựa trên **lifecycle state, quyền sử dụng, phụ thuộc và độ tin cậy thông tin**.

| Tình huống | Hành động đầu tiên | Điều phải tránh |
|---|---|---|
| **ACTIVE + không owner + nhiều Decrypt/Sign** | Incident/risk review, xác định consumer, IAM và người chịu trách nhiệm | Disable hoặc delete đột ngột gây mất dịch vụ |
| **ACTIVE + owner inactive** | Chuyển giao ownership qua service catalog và phê duyệt | Tự gán tài khoản robot làm owner |
| **RETIRED + còn encrypted DEK** | Xác nhận dependency, tìm owner mới, lập kế hoạch rewrap/retention | Hủy khi chưa kiểm tra restore |
| **RETIRED + có chữ ký lịch sử** | Bảo toàn public key/chứng cứ, xác định policy kiểm tra lịch sử | Xóa hết certificate/public key ngay |
| **REVOKED + owner không còn** | Chỉ định incident coordinator, xác minh chặn KMS/trust và xử lý bản sao | Coi REVOKED là bằng chứng mọi nơi đã an toàn |
| **PENDING_DELETION + ownership mơ hồ** | Tạm dừng/đánh giá thao tác hủy nếu provider còn cho phép và policy yêu cầu | Đánh dấu DESTROYED trước khi xác minh |
| **SUSPENDED + owner thiếu** | Điều tra và giữ biện pháp ngăn lạm dụng cần thiết | Resume chỉ để loại finding |
| **Key đã DESTROYED và có bằng chứng** | Giữ audit/retention theo chính sách | Khôi phục giả hoặc đánh dấu key vẫn ACTIVE |
| **Chưa thấy usage nhưng scan thiếu quyền** | Khắc phục scan scope và thu thập bằng chứng | Kết luận không dùng và xóa |

### 15.1. Tách hành động đảo ngược được và không đảo ngược được

**Gán owner, tạo ticket, giới hạn quyền thay policy** thường có thể hoàn nguyên theo workflow. **Delete/Destroy** private key hoặc KEK có thể dẫn tới hậu quả không thể đảo ngược. Càng khó hoàn nguyên, yêu cầu phê duyệt, bằng chứng phụ thuộc và diễn tập khôi phục càng cần chặt chẽ.

### 15.2. Nếu phát hiện khóa có dấu hiệu bị lộ

Thiếu owner có thể trùng với một sự cố thực sự:

1. Cô lập principal nghi ngờ bị chiếm quyền hoặc chặn thao tác nguy hiểm **qua KMS/IAM**.
2. Xác định ranh giới key material: có bị **export/copy** hay chỉ bị lạm dụng API?
3. Sinh key replacement an toàn bằng CSPRNG/KMS/HSM phù hợp.
4. Chuyển dữ liệu, verifier hoặc consumer sang khóa mới.
5. Áp dụng **revocation/trust update** tại các hệ thống phụ thuộc.
6. Điều tra dữ liệu/chữ ký/token lịch sử chịu ảnh hưởng.
7. Chỉ hủy key material theo chính sách và bằng chứng sau khi đã xử lý phụ thuộc.

**Một private key đã bị sao chép không thể bị “hủy từ xa” trên máy đối thủ** bằng cách DisableKey ở KMS. Cần thu hồi **niềm tin** hoặc thay bí mật trong các hệ thống liên quan.

## 16. Owner và key lifecycle: gắn trách nhiệm từ đầu

Nếu việc phát hiện owner chỉ chạy sau nhiều năm, hệ thống sẽ tích lũy nhiều tài sản không ai chịu trách nhiệm. Nên bổ sung ownership vào **mọi giai đoạn vòng đời**:

~~~mermaid
flowchart LR
    G["Generate / Import"] --> P["Register owner + purpose"]
    P --> A["Activate sau owner attestation"]
    A --> U["Use & monitor owner changes"]
    U --> R["Rotate, chuyển owner/version đúng"]
    R --> T["Retire: giữ owner cho phụ thuộc lịch sử"]
    T --> V["Revoke / incident response"]
    V --> D["Destroy khi được duyệt và có bằng chứng"]
    C["Service/team decommissioned"] --> X["Reconcile owner và dependencies"]
    X --> U
~~~

| Giai đoạn | Kiểm tra ownership bắt buộc về mặt thiết kế |
|---|---|
| **Generation** | Ai yêu cầu tạo, purpose, service/tenant và accountable team là gì? |
| **Provisioning** | Ai nhận quyền, metadata owner có được đăng ký/attested không? |
| **Activation** | Owner active, contact route hợp lệ, policy và key usage đã được duyệt chưa? |
| **Usage** | IAM/principal và consumer thay đổi có được owner biết không? |
| **Rotation** | Owner có trách nhiệm cho cả version mới và những version lịch sử chưa xóa không? |
| **Suspension/Revocation** | Ai nhận cảnh báo và có quyền quyết định trong tình huống khẩn cấp? |
| **Retirement** | Ai quản lý decrypt/verify lịch sử, backup và thời hạn retention? |
| **Destruction** | Ai kiểm kê phụ thuộc, duyệt hủy và xác nhận bằng chứng provider? |

### 16.1. Offboarding người và dịch vụ

Khi nhân viên rời tổ chức, nhóm đổi tên hoặc service decommissioned, workflow nên **tự động phát hiện keys có ownership liên quan**.

Chỉ chuyển quyền IAM hoặc xóa tài khoản cá nhân là chưa đủ. Cần:

- Chuyển **accountable team** sang tổ chức tiếp nhận.
- Thay **technical custodian** và contact route nếu cần.
- Đánh giá quyền còn sót của principal cũ, grants và API credentials.
- Xác định backup và encrypted DEK còn phụ thuộc.
- Ghi **owner change event** và yêu cầu xác nhận.
- Đối với signing key, rà soát certificate ownership, renewal và trust distribution.

**Không tạo owner giả vĩnh viễn như “unknown” hay “nobody” chỉ để trường metadata không rỗng.** Có thể dùng trạng thái chưa giải quyết, nhưng phải có người chịu trách nhiệm xử lý finding.

## 17. IAM và kiểm toán quá trình tìm owner

### 17.1. Phân quyền phát hiện khác phân quyền xử lý

| Vai trò | Quyền nên có | Không mặc nhiên cần |
|---|---|---|
| **Inventory scanner** | Read metadata, list keys, lấy trạng thái và nguồn audit được phép | ExportKey, Decrypt, DeleteKey |
| **Ownership analyst** | Đọc inventory, service catalog, tạo finding và đề xuất owner | Sign, Unwrap, ChangePolicy |
| **Accountable owner** | Chấp nhận trách nhiệm, đánh giá usage/rotation, yêu cầu thay đổi | Quyền đọc plaintext key |
| **Key operator** | Thực hiện thay đổi KMS/HSM sau phê duyệt | Tự bypass IAM hoặc tự duyệt mọi việc |
| **Security approver** | Kiểm soát trường hợp rủi ro, revocation và hủy | Tự có quyền giải mã toàn bộ dữ liệu |
| **Auditor** | Kiểm tra bằng chứng/đường đi của quyết định | Sửa ownership và trạng thái khóa |

**Owner không nhất thiết là principal được quyền Encrypt/Decrypt/Sign.** Quản trị ownership và quyền thao tác mật mã nên được tách để tránh một người vừa phê duyệt vừa lạm dụng khóa mà thiếu giám sát.

### 17.2. Audit trail tối thiểu của finding

~~~json
{
  "findingId": "orphan-key-20261128-014",
  "findingType": "MISSING_OWNER",
  "keyRef": "managed-kms/prod-platform-01/ap-southeast-1/payments-kek/v2",
  "scanId": "inventory-scan-20261128",
  "scopeCoverage": "COMPLETE",
  "observedAt": "2026-11-28T02:30:00Z",
  "evidenceRefs": [
    "kms-key-metadata-001",
    "service-catalog-284",
    "audit-usage-201"
  ],
  "priority": "HIGH_REVIEW",
  "assignee": "security-key-governance",
  "workflowState": "OWNER_REVIEW",
  "decision": null
}
~~~

Trong thực tế, audit cần thêm **người thay đổi metadata, owner cũ/mới, approver, revision, timestamps, kết quả KMS/trust update**, và tham chiếu tới incident/change ticket. Không đưa secret hoặc plaintext payload vào evidence.

### 17.3. Đừng để công cụ quét trở thành nguồn rò bí mật

Inventory cần **định danh và metadata**; không cần lấy **private key, DEK dạng rõ, HMAC secret, password, seed/CSPRNG state hoặc bearer token** về kho tập trung.

Ngay cả key references và tenant IDs cũng có thể nhạy cảm về tổ chức; áp quyền đọc, retention và tránh lộ trong dashboard hoặc email không được bảo vệ.

## 18. Chỉ số đo lường và vòng phản hồi

Đếm số khóa thiếu tag là chưa đủ. Một chương trình key governance tốt cần biết **phạm vi quét, trạng thái owner, thời gian xử lý và rủi ro còn mở**.

| Chỉ số | Công thức/cách đo | Ý nghĩa |
|---|---|---|
| **Inventory coverage** | Số scope quét thành công / scope phải quét | Thiếu coverage thì tỉ lệ unowned có thể bị đánh giá sai |
| **Owner completeness** | Key in-scope có owner ID / tổng key in-scope | Bề mặt metadata, chưa chứng minh owner hợp lệ |
| **Verified ownership rate** | Key có owner active và attestation còn hiệu lực / key in-scope | Chỉ số thực chất hơn completeness |
| **Open unowned findings** | Số finding MISSING/UNKNOWN/INACTIVE chưa giải quyết | Công việc còn tồn đọng |
| **High-risk unowned keys** | Số key rủi ro cao và chưa có owner hợp lệ | Ưu tiên phản ứng |
| **Time to assign owner** | Thời gian từ phát hiện tới attestation hợp lệ | Hiệu quả remediation |
| **Stale attestation rate** | Key cần tái xác minh / key in-scope | Kiểm soát drift theo thời gian |
| **False-positive rate** | Finding được reviewer xác nhận không hợp lệ / tổng finding đã review | Chất lượng detector |

Ví dụ, nếu có 1.000 key in-scope, 980 key có owner tag nhưng chỉ 850 owner được xác minh còn hoạt động, **owner completeness = 98%**, còn **verified ownership rate = 85%**. Hai chỉ số trả lời **những câu hỏi khác nhau**.

### 18.1. SLA và escalation

SLA xử lý nên phụ thuộc **rủi ro, môi trường, usage và quyền**. Có thể quy định mức khẩn cao hơn cho khóa có quyền Sign sản xuất hoặc Unwrap rất nhiều DEK. Thời hạn cụ thể phải do tổ chức phê duyệt, không lấy một mốc thời gian minh họa làm tiêu chuẩn bắt buộc.

Một finding cần có **assignee, due date, escalation path, trạng thái, bằng chứng xử lý** và khả năng đóng/mở lại khi dữ liệu thay đổi.

### 18.2. Ngoại lệ có thời hạn

Một trường hợp không thể tìm owner ngay có thể được cấp **risk exception** có thời hạn:

- Người chấp nhận rủi ro có thẩm quyền.
- Lý do và phạm vi khóa cụ thể.
- Kiểm soát bù trừ: hạn quyền, tăng audit, không cấp grants mới...
- Thời hạn hết hiệu lực, người theo dõi và điều kiện tái đánh giá.

**Risk exception không đồng nghĩa đã giải quyết ownership.** Dashboard nên vẫn phản ánh khóa chưa có owner hợp lệ, nhưng phân biệt finding có exception được duyệt với finding bị bỏ mặc.

## 19. Tình huống thực hành: KEK không có owner trong hệ thống thanh toán

Một nền tảng thanh toán nhiều tenant đang có **KEK payments-v2** trong KMS:

| Thuộc tính | Giá trị |
|---|---|
| Key type | AES-256 KEK |
| Environment | Production |
| State | RETIRED |
| KMS tag owner | Trống |
| serviceId | legacy-payment-gateway |
| Service catalog | Service đã decommissioned |
| lastObservedUseAt | Có các lời gọi Unwrap gần đây từ batch reconciliation |
| encrypted DEK references | 1.842 |
| Backup | Có archive theo quý |
| IAM principal | Một service cũ còn quyền Unwrap |

### 19.1. Phát hiện

Scanner ghi các finding:

- **MISSING_OWNER:** không có accountable team hợp lệ.
- **SERVICE_DECOMMISSIONED:** service liên kết đã ngừng hoạt động.
- **UNRESOLVED_DEPENDENCY:** cần xác định batch reconciliation và archive.
- **POTENTIAL_STALE_PERMISSION:** IAM còn service cũ; đây là finding về quyền, cần xác minh thêm.

**Không** tạo finding “SAFE_TO_DELETE” chỉ vì khóa RETIRED.

### 19.2. Điều tra

1. Tra cứu encrypted DEK và dataset để xác định bên đang chịu trách nhiệm dữ liệu hóa đơn.
2. Liên hệ chủ hệ thống **Ledger/Reconciliation** hiện tại và security custodian.
3. Kiểm tra lời gọi Unwrap từ batch hợp lệ hay từ workload lạ; xác thực danh tính, quyền và thời điểm.
4. Xác nhận archive theo quý có còn cần KEK v2 không.
5. Kiểm tra khả năng rewrap DEK sang KEK mới và diễn tập khôi phục dữ liệu.
6. Xác định phạm vi dữ liệu theo tenant và nghĩa vụ lưu giữ.
7. Ghi nhận owner được duyệt cùng contact/on-call, metadata và audit.

### 19.3. Kế hoạch xử lý

- Gán **accountable owner** cho đơn vị nhận trách nhiệm từ service cũ.
- Hạn chế quyền Unwrap cho những principal thực sự cần; không thay đổi dữ liệu trái phép.
- Đảm bảo các DEK mới được wrap dưới KEK đang ACTIVE, không dùng v2 cho dữ liệu mới.
- Nếu khả thi, **rewrap 1.842 encrypted DEK** và kiểm tra dữ liệu đọc/restore.
- Tiếp tục giữ v2 RETIRED trong thời gian còn bản sao lưu chưa chuyển đổi.
- Chỉ lên lịch hủy sau khi **kiểm tra tất cả dependencies/backup/retention và phê duyệt**.
- Scanner tái kiểm tra metadata owner; audit ghi lại toàn bộ quá trình.

**Bài học:** ownerless key detection có giá trị không chỉ vì tìm tag trống, mà vì phát hiện một **chuỗi phụ thuộc chưa được quản lý**, từ chủ dữ liệu tới IAM và KEK/DEK.

## 20. Trường hợp signing key và certificate không có owner

Một tổ chức có **private signing key** trong HSM dùng để ký JWT và phiếu phê duyệt. Chủ ứng dụng cũ đã giải thể, certificate sắp hết hạn, nhưng hệ thống xác minh vẫn tải public key từ JWKS.

Một bài toán cần giải đồng thời:

1. **Ai sở hữu private signing key?** Đơn vị phát hành token/chứng từ, không phải chỉ HSM operator.
2. **Ai quản lý verifier?** Các hệ thống tin public key và chính sách issuer/audience.
3. **Ai chịu trách nhiệm renewal/rotation?** Nhóm phải cập nhật key version và JWKS.
4. **Ai xử lý incident?** Người có quyền điều phối disable Sign và revoke trust.
5. **Ai giữ bằng chứng lịch sử?** Đối với chứng từ ký số, có thể cần public key/certificate và trusted timestamp.

**Chữ ký toán học hợp lệ không tự chứng minh rằng chủ thể ký hiện còn được tin.** Public key phải được gắn đúng danh tính, purpose và thời hạn chính sách. Nếu private key bị lộ, chỉ đổi owner tag không giải quyết nguy cơ mạo danh.

Với JWT/JWS, trường **kid** là định danh hỗ trợ chọn public key, không phải bằng chứng trust; phải xác thực nguồn JWKS/issuer và kiểm tra thuật toán, claims, expiry và quyền.

## 21. Ma trận kiểm thử detector và quy trình remediation

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Owner field null hoặc blank | MISSING_OWNER |
| Owner ID có giá trị nhưng directory không có | UNKNOWN_OWNER |
| Owner team không active | INACTIVE_OWNER |
| Owner attestation quá hạn | STALE_ATTESTATION |
| Service đã decommissioned | SERVICE_DECOMMISSIONED |
| Scanner thiếu quyền đọc một region | INVENTORY_INCOMPLETE, không tuyên bố không có keys |
| Key trùng alias ở hai account | Không gộp nhầm asset |
| Key có nhiều material versions | Mỗi version có trạng thái/phụ thuộc riêng |
| Creator khác service owner | Không tự suy creator thành owner |
| IAM principal còn gọi Decrypt | Ghi consumer evidence, không tự đổi accountable owner |
| Key RETIRED có encrypted DEK đang phụ thuộc | Vẫn tạo finding ownership, không tự hủy |
| Private signing key thiếu owner | Phát hiện cả trách nhiệm certificate/trust/verifier |
| Owner tag đã sửa nhưng team không attested | Finding chưa được đóng hợp lệ |
| Owner có attestation hợp lệ, team active | Không tạo lỗi missing/unknown/inactive |
| Hai nguồn owner mâu thuẫn | AMBIGUOUS_OWNER, yêu cầu reviewer |
| Nguồn audit không có dữ liệu gần đây | Không tự kết luận key unused |
| Remediation request từ principal không có quyền | Từ chối theo IAM/workflow |
| Attempt auto-delete key unowned | Bị ngăn vì detector read-only |
| Retry ticket cùng key/version/finding | Không tạo hàng loạt ticket trùng |
| Rewrap DEK rồi dự định hủy KEK cũ | Kiểm chứng restore, backup và retention trước |
| Khi KMS/API lỗi giữa workflow | Giữ trạng thái chưa hoàn tất, retry/reconcile an toàn |
| Audit metadata của finding | Có actor, evidence, reason, version, timestamps; không có secret |

Các bài kiểm thử nên bao phủ **multi-account/multi-region, cache, retry, phần quyền, stale service catalog, owner handover và khóa trong backup/archive**. Mỗi finding đóng được phải có **bằng chứng và khả năng tái kiểm tra**.

## 22. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Khắc phục |
|---|---|---|
| Coi creator là owner hiện tại | Gán trách nhiệm cho tài khoản automation/người đã nghỉ | Dùng owner attestation và service catalog |
| Gán owner bằng tag bất kỳ | Metadata đủ nhưng không có người nhận trách nhiệm | Kiểm tra team active, contact và approval |
| Chỉ quét một cloud account/region | Bỏ sót khóa và báo cáo sai coverage | Scope registry và cảnh báo scan failures |
| Dùng Key ID không chứa account/region/version | Gộp nhầm khóa hoặc phiên bản | Composite identity ổn định |
| Không phân biệt owner với custodian | Người vận hành HSM bị coi là chủ dữ liệu | RACI và accountable owner rõ ràng |
| Dùng last-used rỗng làm bằng chứng unused | Xóa nhầm backup key hoặc khóa lịch sử | Kiểm tra dependency/retention và độ phủ logs |
| Tự disable mọi key thiếu owner | Phá ứng dụng và khả năng khôi phục | Read-only detection, risk-based review |
| Xóa KEK mà chưa rewrap encrypted DEK | Mất khả năng giải mã dữ liệu | Dependency graph, rewrap, thử restore |
| Hủy private signing key mà xóa luôn public key lịch sử | Mất chứng cứ xác minh tài liệu cũ | Retain public key/chứng cứ theo policy |
| Không xét IAM/cross-account grants | Khóa vẫn được dùng bởi principal cũ | Entitlement review và least privilege |
| Chỉ gán owner cho logical alias, bỏ quên v1 | Version cũ không ai quản lý | Inventory theo material version |
| Đóng finding khi owner tự ghi text bất kỳ | Dễ giả mạo hoặc ownership không thật | Workflow attestation có xác thực |
| Không có SLA và escalation | Ticket tồn tại mãi | Priority, owner review, due date, escalation |
| Bỏ qua trạng thái scan incomplete | Tưởng mọi asset đã được kiểm soát | Coverage/freshness dashboard |
| Thu hồi KMS key nhưng không cập nhật verifier | Chữ ký cũ/giả vẫn có thể được chấp nhận | Trust propagation và incident workflow |
| Đưa private key/DEK vào inventory | Tạo nguồn rò rỉ tập trung | Chỉ lưu metadata và key references |
| Coi risk exception là owner hợp lệ | Che giấu trách nhiệm thiếu | Theo dõi exception riêng và tái đánh giá |

## 23. Câu hỏi tự kiểm tra

**Câu 1. Key có tag owner khác rỗng đã chắc có owner hợp lệ chưa?**

**Trả lời:** Chưa. Cần xác minh team tồn tại, còn hoạt động, có kênh liên hệ và đã chấp nhận trách nhiệm theo quy trình.

**Câu 2. Tại sao IAM principal có quyền Sign không tự động là owner của signing key?**

**Trả lời:** Principal chỉ cho biết ai có khả năng gọi Sign; accountable owner chịu trách nhiệm về mục đích, quyền, rotation, revocation và incident.

**Câu 3. Có thể tự xóa key không thấy usage trong 90 ngày không?**

**Trả lời:** Không. Log có thể thiếu và một số key chỉ dùng theo quý hoặc phục vụ backup, decrypt, chữ ký lịch sử. Phải kiểm tra dependencies và retention.

**Câu 4. MISSING_OWNER khác UNKNOWN_OWNER ra sao?**

**Trả lời:** MISSING_OWNER là owner field trống/thiếu; UNKNOWN_OWNER là có ID nhưng không tìm thấy trong nguồn danh bạ được tin.

**Câu 5. Vì sao phải kiểm kê theo key version?**

**Trả lời:** Version cũ có thể RETIRED nhưng còn ciphertext hoặc chứng cứ lịch sử, trong khi alias đã trỏ sang version mới. Gộp chúng làm mất khả năng đánh giá rủi ro.

**Câu 6. Scanner cần quyền ExportKey hoặc Decrypt không?**

**Trả lời:** Thông thường không. Chỉ cần List/Describe metadata, nguồn usage, IAM và dependencies theo quyền read-only.

**Câu 7. Một KEK không có owner có thể hủy sau khi gán owner tạm không?**

**Trả lời:** Không. Còn phải xác minh encrypted DEK, dữ liệu, backup, retention, phê duyệt và bằng chứng hủy an toàn.

**Câu 8. Rotation KEK khác rotation DEK thế nào?**

**Trả lời:** KEK thường có thể được thay bằng cách rewrap DEK nếu phù hợp; thay DEK thường cần mã hóa lại dữ liệu phụ thuộc.

**Câu 9. Vì sao public key cũng cần ownership dù không phải secret?**

**Trả lời:** Vì nó tham gia trust, phân phối, chứng chỉ, xác minh chữ ký lịch sử, rotation và revocation.

**Câu 10. Có thể tự lấy owner từ service catalog rồi đóng finding không?**

**Trả lời:** Chỉ khi quy tắc suy luận được phê duyệt là authoritative và đã đáp ứng yêu cầu attestation. Nếu không, service owner chỉ là ứng viên cần xác nhận.

**Câu 11. Severity khác evidence confidence như thế nào?**

**Trả lời:** Severity đo hậu quả tiềm tàng; confidence đo mức đáng tin/đầy đủ của bằng chứng. Khóa rủi ro cao nhưng scan thiếu dữ liệu cần được điều tra khẩn chứ không được xóa.

**Câu 12. Nếu private signing key bị lộ, đổi owner có đủ không?**

**Trả lời:** Không. Phải chặn Sign, thay key, cập nhật verifier/trust và điều tra chữ ký/token liên quan.

**Câu 13. Vì sao team đã giải thể phải kích hoạt owner reconciliation?**

**Trả lời:** Vì trách nhiệm quay vòng, thu hồi, phản ứng sự cố và xử lý dữ liệu lịch sử sẽ không còn người được xác định thực hiện.

**Câu 14. Cần audit gì khi gán lại owner?**

**Trả lời:** Key ID/version, owner cũ/mới, lý do, actor, approver, evidence, thời điểm và kết quả, không chứa key material.

**Câu 15. Một risk exception có làm finding hết tồn tại không?**

**Trả lời:** Không. Exception chỉ là quyết định chấp nhận rủi ro có thời hạn và kiểm soát bù trừ; trạng thái owner vẫn phải được phản ánh đúng.

## 24. Checklist triển khai và ghi nhớ

Trước khi kết luận hệ thống đã kiểm soát các khóa thiếu owner, hãy kiểm tra:

- **Scope:** đã kiểm kê đủ provider, account, region, environment, HSM, vault, certificate và backup?
- **Identity:** key ID/material version được chuẩn hóa, không gộp nhầm aliases hoặc tài khoản?
- **Metadata:** có accountable owner, custodian, service, purpose, thuật toán, key usage và trạng thái?
- **Validity:** owner team còn active, có contact/on-call và attestation đúng thời hạn?
- **Evidence:** tag, service catalog, IAM, audit và dữ liệu phụ thuộc được đối chiếu, có confidence/freshness?
- **Classification:** MISSING, UNKNOWN, INACTIVE, AMBIGUOUS và INCOMPLETE_SCAN được phân biệt?
- **Dependencies:** encrypted DEK, ciphertext, backup, certificate, JWKS, token và consumers đã được liên kết?
- **Risk:** severity có xét production, Encrypt/Decrypt/Sign/Unwrap, quyền IAM và tác động dữ liệu?
- **Workflow:** có owner acceptance, approval, SLA, escalation, temporary risk coordinator và audit?
- **Safety:** scanner chỉ đọc metadata, không tự ExportKey, Disable, Revoke hoặc Delete?
- **Lifecycle:** mọi key mới có owner trước ACTIVE; service/team offboarding kích hoạt owner reconciliation?
- **Rotation/revocation:** có kế hoạch rewrap/re-encrypt, public-key trust update và xử lý lịch sử khi phát hiện rủi ro?
- **Metrics:** coverage, verified ownership rate, high-risk findings, tuổi finding và exception còn hiệu lực được theo dõi?
- **Validation:** tái quét sau remediation, kiểm thử false positive, retry, IAM và trường hợp phụ thuộc backup?
- **Security:** inventory, findings và logs không chứa key material hoặc secret nhạy cảm?

**Ghi nhớ:** **Phát hiện key không có owner** không phải một phép kiểm tra xem trường owner có rỗng không. Đó là quá trình **kiểm kê chính xác, đối chiếu nguồn tin cậy, xác minh trách nhiệm, nhận diện phụ thuộc, ưu tiên rủi ro và xử lý có kiểm soát**. Kết hợp **key inventory, IAM, KMS/HSM, DEK/KEK, envelope encryption, chữ ký số, rotation/revocation/destruction và audit** giúp ngăn cả hai thảm họa: khóa nguy hiểm bị bỏ mặc và khóa còn cần thiết bị hủy nhầm.
