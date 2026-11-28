# Emergency compromise policy (Chính sách ứng phó khẩn khi khóa mật mã bị xâm phạm)

## 1. Emergency compromise policy là gì?

**Emergency compromise policy** là bộ quy tắc xác định **khi nào, ai được phép, làm gì, theo trình tự và bằng chứng nào** khi một khóa mật mã hoặc **khả năng sử dụng khóa** bị lộ, bị nghi xâm phạm hoặc bị lạm dụng. Chính sách phải cho phép **ngăn thiệt hại ngay**, nhưng không biến tình huống khẩn cấp thành quyết định hủy khóa không thể khôi phục hoặc thay đổi thiếu kiểm toán.

Ví dụ, một principal có quyền gọi KMS **Decrypt/Unwrap** bị chiếm quyền. KEK có thể vẫn là khóa non-exportable trong HSM, nhưng kẻ tấn công có thể sử dụng KMS như **decryption oracle**. Nếu chỉ tạo KEK mới mà không cô lập IAM principal và điều tra những DEK đã bị unwrap, khả năng mất dữ liệu vẫn tồn tại.

Trong chương **Key policy** thuộc module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chính sách khẩn cấp liên kết vòng đời **tạo, cấp phát, lưu, sử dụng, xoay vòng, thu hồi và hủy** với AES/DEK/KEK, mật mã bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, IAM và audit.

Một chính sách có thể thực thi cần trả lời sáu câu hỏi:

1. **Trigger:** dấu hiệu nào khiến tổ chức chuyển sang phản ứng khẩn cấp?
2. **Authority:** ai được chặn quyền lập tức, ai phê duyệt thao tác không thể hoàn nguyên?
3. **Scope:** vật liệu khóa, phiên bản, dữ liệu, tenant, consumer và trust nào bị ảnh hưởng?
4. **Action:** cần cô lập, suspend, rotate, rewrap, re-encrypt hay revoke theo thứ tự nào?
5. **Verification:** KMS/HSM, ứng dụng, verifier, cache, backup và đối tác thực sự cập nhật chưa?
6. **Evidence:** ai quyết định, vì sao, vào lúc nào, kết quả và rủi ro còn lại là gì?

> **Lưu ý:** Những vai trò, mức severity và trạng thái trong bài là mô hình thiết kế tham khảo. Chúng không phải trạng thái hay thời hạn mặc định của mọi KMS, HSM hoặc quy định pháp luật. Mỗi tổ chức cần hiệu chỉnh theo thuật toán, hệ thống, phân loại dữ liệu và chính sách đã phê duyệt.

## 2. Compromise không chỉ có nghĩa là private key bị đánh cắp

Cần phân biệt **vật liệu khóa bị lộ** với **quyền sử dụng khóa bị lạm dụng**, vì hành động ứng phó khác nhau.

| Loại tình huống | Ví dụ | Nguy cơ chính |
|---|---|---|
| **Key-material exposure** | Private signing key hoặc plaintext DEK xuất hiện trong log, image, bản sao bị truy cập | Đối thủ có thể dùng bản sao ở ngoài KMS/HSM |
| **KMS/HSM API misuse** | Token workload bị chiếm để gọi Sign, Decrypt, Unwrap | Khóa không export vẫn bị sử dụng trái phép |
| **Unauthorized policy change** | Một grant/role lạ được cấp Encrypt, Sign hoặc ChangeKeyPolicy | Mở rộng chủ thể có khả năng dùng hoặc thay chính sách |
| **Weak key generation** | Khóa được sinh từ timestamp hoặc CSPRNG có seed cố định | Key material dễ đoán dù không có log lấy trộm |
| **Algorithm/protocol misuse** | AES-GCM tái sử dụng nonce với cùng DEK, ECDSA nonce k bị lỗi | Có thể phá bí mật hoặc xác thực mà không cần lấy private key |
| **Trust compromise** | Public key/JWKS/trust store bị thay hoặc chứng chỉ bị cấp sai | Verifier có thể tin chữ ký/danh tính giả |
| **Distribution/backup exposure** | Khóa được đưa vào repo, CI artifact hoặc backup sai quyền | Nhiều bản sao khó thu hồi |
| **Suspected compromise** | Bất thường về Sign/Unwrap, dấu hiệu endpoint bị chiếm | Cần containment trong lúc điều tra; chưa được suy diễn quá mức |

Hai câu hỏi cần điều tra độc lập:

- **Key bytes có thể đã rời ranh giới bảo vệ?** Nếu có, DisableKey trong KMS không ngăn đối thủ dùng bản sao.
- **Một chủ thể có thể đã dùng key qua API mà không lấy key bytes?** Nếu có, cần cô lập IAM, đánh giá giao dịch và dữ liệu đã được xử lý.

**Không thấy sự kiện ExportKey không chứng minh khóa chưa từng bị lộ.** Phải xem khả năng provider, cấu hình export, các bản sao đã tồn tại, memory dump, log, backup và giới hạn quan sát thực tế.

## 3. Tài sản và phạm vi ảnh hưởng cần điều tra

| Tài sản | Nếu bị xâm phạm | Câu hỏi bắt buộc |
|---|---|---|
| **DEK AES-GCM** | Dữ liệu dưới DEK có thể giải mã; lỗi nonce còn ảnh hưởng tính toàn vẹn | Dataset, key version, nonce, tag, AAD và backup nào? |
| **KEK/KMS key** | Nhiều encrypted DEK có thể bị unwrap | Bao nhiêu tenant, DEK, grants, API callers và bản sao? |
| **HMAC/PSK secret** | Bất kỳ bên biết secret có thể tạo MAC | Những bên nào đang giữ bản sao, có thể đồng bộ rotation không? |
| **Private signing key** | Có thể tạo chữ ký/token/chứng từ giả | Verifier, certificate, JWKS, key ID và thời gian tin cậy nào? |
| **CA/trust root/certificate** | Có thể mạo danh, phát hành hoặc chấp nhận sai danh tính | Những client nào dùng trust store hoặc pinning cũ? |
| **RNG/DRBG state** | Nhiều key/token được sinh trong cùng thời kỳ có thể dự đoán | Từ thời điểm nào, host/VM nào, key versions nào? |
| **Recovery/backup key** | Có thể mở nhiều dataset và bản sao | Có thể đổi đường recovery mà không mất dữ liệu hợp lệ không? |
| **IAM principal** | Nhiều key có thể bị dùng mà không lộ material | API Sign/Decrypt/Unwrap nào đã được gọi và được phép? |

**Phải định danh đúng vật liệu khóa.** Key alias có thể trỏ từ v1 sang v2; hai alias cũng có thể trỏ đến cùng vật liệu. Inventory nên kết hợp **provider, account/project, region, key ID, material version, algorithm, usage, origin, owner và cryptoperiod**.

### 3.1. Blast radius không chỉ là số key

Một KEK bảo vệ 10.000 DEK có thể nguy hiểm hơn nhiều DEK cô lập. Một signing key phục vụ issuer dùng chung có thể ảnh hưởng hàng loạt đối tác dù chỉ tồn tại một key pair. Xem xét:

- **Phạm vi dữ liệu/tenant:** ai có thể mất bí mật hoặc mất khả năng giải mã?
- **Phạm vi quyền:** ai được Sign, Decrypt, Wrap/Unwrap, Rotate và ChangePolicy?
- **Phạm vi niềm tin:** những verifier/JWKS/CA nào tin public key liên quan?
- **Phạm vi thời gian:** key được tạo, dùng, nghi lộ từ lúc nào; dữ liệu lịch sử còn lưu bao lâu?
- **Bản sao ngoài kiểm soát:** plaintext key, tokens, snapshots và backups có thể còn ở đâu?

**Không xóa KEK chỉ vì nó bị nghi lộ** nếu chưa biết những encrypted DEK/backup còn phụ thuộc; hành động phá hủy có thể khiến tổ chức không thể phục hồi dữ liệu hợp lệ.

## 4. Trigger và phân loại severity

Không nên viết chính sách chỉ với câu “khi phát hiện khóa lộ”. Cần trigger quan sát được cùng cơ chế escalation.

| Trigger | Dấu hiệu ví dụ | Phản ứng ban đầu |
|---|---|---|
| **Confirmed secret exposure** | Private key được tìm thấy trong repository công khai | Cô lập, chặn dùng, điều tra bản sao, chuẩn bị khóa mới |
| **Credible suspected exposure** | Heap dump chứa DEK được lưu ở nơi trái chính sách | Bảo vệ chứng cứ, hạn chế quyền, xác minh phạm vi |
| **Unauthorized Sign/Decrypt** | Calls bất thường theo principal/region/tenant | Thu hồi credential/grant và kiểm tra lịch sử |
| **Policy drift nguy hiểm** | Grants hoặc key policy mở rộng trái phê duyệt | Chặn quyền bổ sung, đối chiếu change/audit |
| **Weak generation / entropy failure** | RNG tạo secret từ seed cố định | Dừng tạo secret mới và khoanh vùng khóa đã phát hành |
| **GCM nonce collision** | Phát hiện trùng cặp (key, nonce) | Ngừng encrypt dưới DEK bị ảnh hưởng và điều tra confidentiality/integrity |
| **Trust compromise** | Public key issuer/JWKS bị thay trái phép | Chặn trust không hợp lệ, phân phối thông tin đúng nguồn |

Phân loại severity minh họa:

| Cấp | Mô tả tham khảo | Nhịp xử lý |
|---|---|---|
| **Critical** | Private key/KEK production lộ rõ, Sign/Unwrap đang bị lạm dụng, nhiều tenant chịu ảnh hưởng | Containment ngay theo thẩm quyền break-glass; điều phối sự cố |
| **High** | Nghi lộ có bằng chứng tin cậy, nhưng chưa biết phạm vi | Hạn quyền tạm, điều tra, chuẩn bị rotation |
| **Elevated** | Policy drift ở phạm vi nhỏ hoặc phát hiện nguy cơ chưa khai thác | Review theo SLA rủi ro, kiểm soát bù trừ |
| **Monitoring** | Tín hiệu yếu, chưa có bằng chứng compromise | Ghi finding, bổ sung dữ liệu, nâng cấp nếu xuất hiện dấu hiệu mới |

Một key non-exportable vẫn có thể tạo sự cố **Critical** nếu kẻ tấn công có quyền gọi Sign/Decrypt đủ rộng. Không được tự hạ severity chỉ vì HSM không cho export private key.

## 5. Nguyên tắc chính sách

Một emergency compromise policy nên dựa trên:

1. **Contain first, recover safely:** chặn đường gây thiệt hại, bảo toàn chứng cứ; không vội destroy.
2. **Least privilege và fail-safe:** quyền khẩn có phạm vi và thời hạn; không dùng fallback cryptography yếu.
3. **Version-aware decisions:** áp đúng key material/version, owner, tenant và consumers.
4. **Separate duties:** phân tách điều phối, thao tác KMS/HSM, phê duyệt hủy và kiểm tra độc lập.
5. **End-to-end revocation:** kiểm tra KMS/IAM, applications, verifier, public trust, cache và backups.
6. **Evidence-based closure:** chỉ coi hoàn tất khi hậu điều kiện được kiểm chứng, không phải khi có HTTP 200/ACK.
7. **No silent reinstatement:** khóa thực sự bị compromise không được tự động REVOKED → ACTIVE khi sự cố đóng.

**Nguyên tắc nghiệp vụ:** khả năng giải mã dữ liệu hợp lệ và nghĩa vụ lưu giữ là một phần của an toàn; nhưng tính sẵn sàng không được dùng làm lý do âm thầm mở lại quyền Sign/Unwrap đã bị lộ.

## 6. Vai trò, quyền hạn và break-glass

| Vai trò | Trách nhiệm chính | Không tự động được phép |
|---|---|---|
| **Incident commander** | Ưu tiên containment, điều phối, escalation, phê duyệt phương án khôi phục | Xuất plaintext DEK hoặc xóa mọi khóa |
| **Security responder** | Xác minh dấu hiệu, yêu cầu suspend/revoke, điều tra | Destroy key material không cần approval |
| **KMS/HSM operator** | Thực hiện chính sách key, grants, rotation, đọc provider state | Tự phê duyệt và xóa log |
| **Accountable key owner** | Purpose, cryptoperiod, dependency, chấp nhận rủi ro | Decrypt/Sign mọi dữ liệu mặc nhiên |
| **Data/application owner** | Tác động dữ liệu, migration và khôi phục dịch vụ | Bypass key policy |
| **PKI/trust owner** | Cập nhật certificate/JWKS/trust/CRL/OCSP | Dùng private signing key nếu chỉ cần Verify |
| **Independent auditor** | Kiểm tra bằng chứng, hậu kiểm và ngoại lệ | Thực thi thao tác phá hủy |

### 6.1. Cơ chế break-glass

**Break-glass** cần cho phép ngăn ngay một cuộc tấn công, nhưng có kiểm soát:

- **Trigger/incident ID** rõ; ghi đúng key ID/version, tác nhân và lý do.
- Danh tính mạnh, MFA và quyền nâng cao được **giới hạn thời gian (TTL)**.
- **Scope tối thiểu**: revoke grant hoặc suspend key version cụ thể, không cấp sẵn quyền delete toàn bộ key store.
- Audit độc lập và cảnh báo khi dùng quyền khẩn; người dùng không được xóa dấu vết.
- Bắt buộc hậu kiểm theo quy trình, thu hồi quyền khẩn sau sự cố.
- Các hành động **không thể phục hồi** thường yêu cầu kiểm kê phụ thuộc, approval độc lập và kiểm tra backup.

**Emergency disable** có thể được thực hiện ngay, rồi hậu kiểm. **Permanent destruction** thường không nên được tự động hóa chỉ dựa trên cảnh báo ban đầu vì có nguy cơ mất dữ liệu.

### 6.2. Không để break-glass trở thành cửa hậu

Một account khẩn có quyền quá rộng, không giám sát có thể trở thành nguồn sự cố. Cần kiểm tra credential lifecycle, nơi lưu secret, separation of duties, TTL, khả năng thực hiện thao tác và bằng chứng toàn bộ yêu cầu.

## 7. Quy trình tổng thể: phát hiện tới đóng sự cố

~~~mermaid
flowchart TD
    A["Alert hoặc credible compromise signal"] --> B["Triage: key ID/version, owner, scope"]
    B --> C["Contain: IAM, grants, key usage, token/session"]
    C --> D["Bảo toàn bằng chứng, đánh giá blast radius"]
    D --> E["Generate replacement và chuẩn bị consumers"]
    E --> F["Cutover: DEK/KEK, signer, trust, traffic"]
    F --> G["Revoke / retire vật liệu cũ"]
    G --> H["Xác minh KMS + app + verifier + cache + backup"]
    H --> I["Phục hồi dịch vụ, monitor, hậu kiểm"]
    D --> J{"Bằng chứng còn thiếu?"}
    J -->|Có| K["Giữ containment và điều tra tiếp"]
    K --> D
~~~

Đây là luồng **logic**, không quy định mọi bước luôn chạy tuần tự: containment, tạo khóa thay thế, điều tra và chuẩn bị consumer có thể diễn ra song song theo quyền và ưu tiên.

### 7.1. Chuẩn bị trước sự cố

Một chính sách khẩn cấp sẽ khó thực hiện nếu không có:

- Key inventory gồm owner, type, key version, origin, usage, cryptoperiod, provider, tenant.
- Dependency map: KEK → encrypted DEK → ciphertext/backup; signing key → certificate/JWKS → verifier.
- IAM break-glass đã được diễn tập, logs độc lập và thông tin on-call.
- Runbook riêng cho DEK, KEK, HMAC/PSK, signing key, TLS, recovery key.
- Đường GenerateKey/GenerateDataKey từ CSPRNG/KMS/HSM đã đánh giá.
- Kế hoạch cutover/rollback an toàn, tránh tái sử dụng nonce AES-GCM.
- Đầu mối data owner, risk owner, compliance và đối tác ngoài nếu cần thông báo.

### 7.2. Pha 1 — Triage

Tạo incident ID; xác định thời gian nghi bắt đầu, account/region, key material version, thuật toán, owner, principals, service, trạng thái KMS, chứng cứ và mức độ chắc chắn.

Phân biệt **sự thật quan sát** với **giả thuyết**: một lượt Decrypt sai không chứng minh private key đã bị xuất, nhưng sự thiếu vắng log cũng không chứng minh không có lạm dụng.

### 7.3. Pha 2 — Containment

Tùy rủi ro:

- Revoke credential/token/session và các KMS grants/key policy trái phép.
- Suspend/disable key hoặc chặn **Sign/Encrypt/Wrap mới** ở nơi thực thi.
- Cô lập host/workload bị chiếm, kiểm tra access path và network controls.
- Nếu signing trust bị xâm phạm, phối hợp chặn tin khóa cũ tại verifier.
- Giữ khả năng phục hồi dữ liệu cần thiết theo quyền đặc biệt, không phá hủy sớm.
- **Không** tự sinh key tạm bằng java.util.Random, timestamp hoặc secret hard-code khi KMS lỗi.

### 7.4. Pha 3 — Điều tra tác động

Đọc audit, kiểm tra key origin/export policy, backup, data/ciphertext references, lần Sign/Decrypt/Unwrap bất thường, principal bị ảnh hưởng, consumers và trust state.

**Không tải private key/DEK rõ về máy điều tra để so sánh nếu metadata và provider API đã đủ**. Bản thân hoạt động điều tra không được tạo thêm một đường rò mới.

### 7.5. Pha 4 — Rotation và migration

Tạo **vật liệu khóa mới thật sự** từ nguồn mạnh, phân quyền theo IAM và owner. Cập nhật producers/consumers; với DEK cần cân nhắc re-encrypt, với KEK rewrap nếu phù hợp, với signing key phải phân phối public trust, với HMAC phải đồng bộ mọi bên giữ secret.

### 7.6. Pha 5 — Xác minh hậu điều kiện

Đọc lại KMS/HSM để xác minh các quyền bị cấm thực sự bị từ chối; đối chiếu application traffic, cache, verifier, backup và các bản ghi chưa chuyển. Đóng sự cố khi có **bằng chứng** và **rủi ro còn lại được xử lý/chấp nhận đúng thẩm quyền**.

## 8. State machine trong tình huống compromise

~~~mermaid
stateDiagram-v2
    [*] --> PRE_ACTIVE: Generate / Import
    PRE_ACTIVE --> ACTIVE: Activate với guard
    ACTIVE --> SUSPENDED: Suspected compromise
    SUSPENDED --> REVOKED: Compromise/risk confirmed
    ACTIVE --> REVOKED: Emergency revoke
    SUSPENDED --> ACTIVE: Cleared + approval
    ACTIVE --> RETIRED: Planned rotation
    RETIRED --> REVOKED: Later discovery
    RETIRED --> PENDING_DELETION: Dependencies cleared
    REVOKED --> PENDING_DELETION: Evidence and recovery handled
    PENDING_DELETION --> DESTROYED: Provider confirms destruction
    DESTROYED --> [*]
~~~

Đây là **mô hình minh họa**, không phải trạng thái chung của mọi provider. Trong hệ thống thật cần tách **business lifecycle state**, **desired state**, **observed KMS/HSM state** và **public trust propagation**.

| Trạng thái | Ý nghĩa | Hành động khi khẩn cấp |
|---|---|---|
| **ACTIVE** | Được phép sử dụng theo purpose/cryptoperiod | Hạn quyền nếu phát hiện rủi ro |
| **SUSPENDED** | Tạm chặn trong khi điều tra | Chặn thực tế ở KMS/IAM, không chỉ UI |
| **REVOKED** | Rút quyền hoặc niềm tin | Ngăn dùng key; cập nhật verifier/cache/đối tác nếu liên quan |
| **RETIRED** | Ngừng tạo dữ liệu/chữ ký mới | Không dùng retire thay cho response khi key đang bị lộ |
| **PENDING_DELETION** | Đã lên lịch hủy sau kiểm tra phụ thuộc | Không ghi DESTROYED khi chưa hủy thật |
| **DESTROYED** | Đã xác nhận hủy vật liệu trong phạm vi quản lý | Không suy rằng đối thủ đã mất bản sao lộ trước đó |

**REVOKED không nên tự trở lại ACTIVE.** Nếu incident chỉ là false positive và key đang SUSPENDED, resume cần đánh giá và phê duyệt; với vật liệu đã bị lộ thì sinh khóa mới thường là lựa chọn an toàn hơn.

## 9. Runbook cho DEK bị lộ hoặc sinh yếu

**DEK (Data Encryption Key)** trực tiếp mã hóa dữ liệu bằng AES-GCM hoặc AEAD tương đương. Khi plaintext DEK bị lộ:

1. Xác định DEK material version và mọi dataset/object/tenant/backup có ciphertext phụ thuộc.
2. Chặn **Encrypt mới** bằng DEK cũ trên mọi writer, bao gồm retry, batch và service đa vùng.
3. Tạo DEK mới độc lập bằng CSPRNG/KMS theo chính sách.
4. Mã hóa lại dữ liệu dưới DEK mới bằng thuật toán/nonce/AAD/tag đúng, kiểm chứng readback và toàn vẹn.
5. Với AES-GCM, quản lý tính duy nhất của **(DEK, nonce)** xuyên restart/failover và các writer.
6. Giữ Decrypt cũ theo quyền phục hồi có kiểm soát nếu quá trình migration chưa hoàn tất.
7. Kiểm kê backup/retention và kiểm tra restore trước khi hủy DEK cũ.
8. Đánh giá dữ liệu có thể đã bị đối thủ giải mã trước khi rotate: **thay khóa không thu hồi được thông tin đã lộ**.

**Không chỉ rewrap plaintext DEK cũ** rồi gọi đó là rotation DEK. Rewrap đổi lớp bảo vệ DEK, không thay vật liệu DEK.

### 9.1. Khi AES-GCM nonce bị trùng

Tái sử dụng cùng nonce với cùng key có thể phá bí mật và xác thực. Phải ngừng encrypt dưới cấu hình lỗi, xác định key/nonce/messages liên quan và chuyển DEK theo phương án được đánh giá. **Không sửa trường nonce của ciphertext cũ**: ciphertext và tag đã gắn với nonce ban đầu.

## 10. Runbook cho KEK/KMS key bị xâm phạm

**KEK (Key Encryption Key)** có thể bảo vệ nhiều DEK trong envelope encryption. Phải phân biệt **lộ vật liệu KEK** với **lạm dụng quyền API**.

### 10.1. Chỉ phát hiện IAM/API misuse

- Cô lập principal/session, grants, key policies và network path bị lạm dụng.
- Xác định những calls **Unwrap/Decrypt/GenerateDataKey** trái phép và DEK/dữ liệu có thể đã bị truy cập.
- Kiểm tra non-exportable policy, key origin, lịch sử import/export và backup trước khi kết luận có lộ key bytes.
- Đánh giá việc các DEK đã bị unwrap trong thời gian bị lạm dụng có cần được thay và re-encrypt không.
- Xác minh các calls cũ bị từ chối và cập nhật IAM ở mọi account/region liên quan.

### 10.2. KEK material đã lộ

Nếu đối thủ có KEK và encrypted DEK đã thu thập, họ có thể giải bọc DEK tùy cơ chế và metadata. Khi đó:

1. Sinh KEK mới trong ranh giới an toàn và chặn việc tiếp tục dùng KEK cũ.
2. Kiểm kê mọi encrypted DEK, tenant, object, snapshot và backup liên quan.
3. **Không coi rewrap đơn thuần là đủ**: đối thủ có thể đã unwrap DEK cũ hoặc có bản sao encrypted DEK và KEK cũ.
4. Đánh giá tạo DEK mới và **re-encrypt** phạm vi dữ liệu có thể bị ảnh hưởng.
5. Không destroy KEK cũ trước khi xử lý khả năng phục hồi dữ liệu hợp lệ.
6. Thu hồi quyền và xử lý bản sao; đánh giá dữ liệu đã có thể bị lộ.

### 10.3. Rotation theo kế hoạch khác compromise

Nếu KEK chưa bị lộ và mục đích chỉ là rotation thông thường, **rewrap DEK** có thể đủ khi cơ chế hỗ trợ. Không áp máy móc nhận định này cho sự cố lộ KEK/DEK.

## 11. Runbook cho private signing key bị xâm phạm

Private signing key dùng ký JWT, chứng từ, bản phát hành hoặc chứng chỉ cần được xử lý ở **hai phía: quyền tạo chữ ký mới và niềm tin của bên xác minh**.

~~~mermaid
flowchart TD
    A["Private signing key có nguy cơ lộ"] --> B["Chặn Sign và cô lập IAM principal"]
    B --> C["Generate key material mới"]
    C --> D["Phân phối public key/certificate đáng tin"]
    D --> E["Chuyển signer sang key version mới"]
    E --> F["Revoke trust key cũ theo policy"]
    F --> G["Kiểm tra JWKS, cert cache và verifier"]
    G --> H["Điều tra chữ ký/token lịch sử"]
    H --> I["Bảo toàn evidence, hủy private key khi đủ điều kiện"]
~~~

Những điểm quan trọng:

- **Disable trong KMS** không ngăn đối thủ đã sao chép private key tạo chữ ký ở nơi khác.
- **Public key vẫn Verify đúng toán học** ngay cả khi private key bị disabled hoặc destroyed. Verifier phải áp dụng trust/issuer/certificate policy.
- Chữ ký được tạo qua HSM trong thời gian một **workload bị chiếm quyền** có thể hợp lệ về mặt mật mã nhưng **không được phê duyệt về nghiệp vụ**.
- Chữ ký lịch sử cần đánh giá theo **thời điểm tạo đáng tin, trạng thái key/certificate, audit và yêu cầu pháp lý**. Không mặc nhiên gọi tất cả là giả hoặc tin tất cả.
- Public verification key/certificate có thể cần giữ sau khi private signing key đã hủy để hỗ trợ điều tra, lưu giữ và xác minh lịch sử.

### 11.1. JWT/JWS, kid và JWKS cache

Đổi signer từ key v1 sang v2 chưa hoàn tất revocation nếu một service vẫn cache public key v1 và tiếp tục chấp nhận token do khóa lộ tạo ra. Cần kiểm tra **issuer, audience, expiration, algorithm allowlist, kid mapping, nguồn JWKS đáng tin, cache TTL và token revocation**.

**kid chỉ là một key identifier**, không phải bằng chứng danh tính hay trust; không tải public key từ vị trí không đáng tin do token tùy ý chỉ định.

## 12. Runbook cho HMAC/PSK, TLS và khóa phiên

### 12.1. HMAC/shared secret

Khi HMAC/PSK secret bị lộ:

1. Kiểm kê mọi bên giữ secret, API/tenant và version.
2. Chặn hoặc giới hạn chấp nhận MAC mới dưới khóa cũ theo mức rủi ro.
3. Sinh secret mới độc lập và phân phối qua kênh được xác thực.
4. Xác định cửa sổ chuyển đổi nếu cần, với chống replay, scope và thời gian giới hạn.
5. Thu hồi bản sao cũ ở secret manager, consumer, CI/deployment và backup theo quy trình.

**Bất kỳ bên nào biết HMAC key đều có thể tạo MAC**, nên một MAC hợp lệ không chứng minh chính xác bên giữ secret nào đã tạo nó.

### 12.2. TLS signing key và ephemeral agreement

Khi TLS certificate signing private key lộ, đối thủ có thể mạo danh handshake mới nếu client còn tin khóa cũ. Cần cấp phát key/certificate mới, cập nhật trust và cơ chế thu hồi thích hợp.

**Forward secrecy** từ phiên dùng (EC)DHE đúng cách có thể bảo vệ lưu lượng lịch sử khi *chỉ* khóa xác thực dài hạn bị lộ về sau, nhưng **không bảo đảm** khi ephemeral secrets, traffic keys, key logs, plaintext hoặc trạng thái phiên đã bị lấy. Phải điều tra theo giao thức và bằng chứng.

### 12.3. Session tickets, PSK, token

Session resumption ticket key/PSK có vòng đời riêng. Chỉ thay certificate không tự vô hiệu mọi session ticket, bearer token hoặc credential. Cần kiểm tra **lifetime, scope, replay, khả năng chấp nhận phiên đã phát hành và nơi lưu trữ**; revoke/rotate đúng thành phần.


## 13. KMS/HSM, registry và verifier: ba lớp cần đồng bộ

Một key registry có thể ghi **REVOKED**, trong khi:

- KMS vẫn báo **Enabled** và IAM còn cho một principal gọi Decrypt.
- Một ứng dụng cache **key reference** và vẫn tiếp tục Encrypt bằng DEK cũ.
- Verifier JWT/TLS vẫn tin **public key/certificate** đã bị thu hồi.
- Một batch job offline chưa đọc policy mới.
- Backup/recovery còn bản sao KEK hoặc encrypted DEK phụ thuộc.

Vì vậy chính sách cần tách:

| Thành phần | Trạng thái cần quan sát | Hậu điều kiện khẩn |
|---|---|---|
| **Registry/control plane** | desiredState, materialVersion, incident ID, revision | Đúng phiên bản và chính sách đã được quyết định |
| **KMS/HSM provider** | observed key state, grants, key policy, operation result | Các thao tác bị cấm thực sự bị từ chối |
| **IAM/workload** | Token, role, principal, key permissions, STS/session | Danh tính bị chiếm không còn dùng key |
| **Producer/encryptor/signer** | Key version dùng cho hoạt động tạo mới | Không phát hành dữ liệu/chữ ký mới bằng key nghi lộ |
| **Consumer/decryptor** | Key reference, permissions, fallback, cache | Chỉ xử lý lịch sử theo quyền recovery được phê duyệt |
| **Verifier/trust store** | Public key/JWKS/certificate, cache, issuer/trust policy | Không tin tùy tiện khóa đã revoke cho hoạt động mới |
| **Backup/DR** | Encrypted DEKs, old KEK, key escrow | Có phương án khôi phục hợp lệ trước khi destroy |

~~~mermaid
flowchart TD
    I["Incident command + security approval"] --> W["Transition workflow"]
    W --> R["Registry desired state / revision"]
    W --> K["KMS/HSM, IAM & grants"]
    W --> C["Application producers/consumers"]
    W --> V["PKI/JWKS/Verifier trust"]
    K --> O["Provider observed state"]
    C --> P["Key/version in active traffic"]
    V --> T["Trust propagation evidence"]
    O --> Q{"Các hậu điều kiện đạt?"}
    P --> Q
    T --> Q
    Q -->|Chưa| E["Giữ containment; retry & reconcile"]
    Q -->|Rồi| A["Finalize + audit + approval"]
~~~

**Provider ACK không đồng nghĩa transition hoàn tất.** Nếu provider chặn Sign nhưng issuer còn cache hoặc client vẫn tin key bị lộ, cần tiếp tục theo dõi **trust propagation**.

### 13.1. Mapping state theo khả năng thực của provider

Một KMS có thể chỉ hỗ trợ Enabled/Disabled/PendingDeletion; ứng dụng lại cần SUSPENDED/RETIRED/REVOKED. Không được mặc định các tên đó có cùng ngữ nghĩa.

Ví dụ, khi một KEK đang **RETIRED**, policy có thể cấm **Wrap mới** nhưng cho phép **Unwrap lịch sử** đối với một số workload. Nếu provider không có phân quyền đủ chi tiết, kiến trúc cần thực thi qua lớp dịch vụ tin cậy, thay key boundary hoặc chấp nhận một phương án migration khác đã được đánh giá.

### 13.2. Disable không thay thu hồi trust

Với private signing key đã bị đánh cắp, disable API Sign chỉ ngăn ký **qua provider đó**. Người có bản sao private key vẫn có thể ký ở nơi khác. Phải phối hợp cập nhật những nơi **tiêu thụ và tin public key**.

## 14. Tính nhất quán, idempotency và thứ tự ưu tiên trong khẩn cấp

Một hệ thống phân tán dễ gặp xung đột:

- Rotation bình thường yêu cầu **ACTIVE → RETIRED**.
- Điều tra khẩn yêu cầu **ACTIVE → REVOKED**.
- Một workflow cũ retry **SUSPENDED → ACTIVE**.
- Event bus phát một event **ACTIVE** cũ sau event **REVOKED**.

Nếu không chống ghi đè, khóa nguy hiểm có thể được tái kích hoạt.

### 14.1. Expected revision và compare-and-swap

Mỗi request cần key ID/version và **expectedStateRevision**. Registry cập nhật bằng compare-and-swap:

~~~sql
-- Cú pháp minh họa, tùy DB và lược đồ.
UPDATE key_version_registry
SET desired_state = :target_state,
    state_revision = state_revision + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE key_id = :key_id
  AND material_version = :material_version
  AND desired_state = :expected_state
  AND state_revision = :expected_revision;
~~~

Khi không có dòng nào được cập nhật, phải **đọc lại trạng thái và đánh giá guard**, không bỏ điều kiện revision để cố hoàn thành yêu cầu cũ.

### 14.2. Thứ tự ưu tiên: compromise áp đảo rotation stale

Khi có evidence đáng tin dẫn tới REVOKED, một event ACTIVATE cũ không được tự đưa key trở về ACTIVE. Sử dụng **monotonic incident version, revision, fencing token hoặc workflow priority** phù hợp thiết kế để chặn stale writer. Không dùng thuật toán “last writer wins” mù quáng cho revocation.

### 14.3. Provider API và DB không nằm trong một transaction

Một lệnh DisableKey ở KMS và UPDATE registry thường không chia sẻ ACID transaction. Cách điều phối an toàn:

1. Tạo **transition intent** với operation ID/idempotency key và event type.
2. Thiết lập **deny trên đường thực thi** càng sớm càng tốt khi hạn chế quyền.
3. Gọi KMS/IAM/PKI API có retry theo policy.
4. **Đọc lại observed state** sau mỗi thay đổi trọng yếu.
5. Finalize registry kèm audit/outbox khi đạt hậu điều kiện.
6. Reconciler xử lý những operation còn APPLYING/VERIFYING quá lâu.
7. Nếu có lỗi, **giữ fail-safe**, không tự rollback thành ACTIVE.

Idempotency giúp nhận biết request lặp nhưng **không bảo đảm exactly-once trên mọi hệ thống**. Các lần retry phải tránh tạo thêm key versions, lịch hủy hoặc grants ngoài dự kiến.

## 15. Mẫu chính sách theo từng kiểu compromise

Một **policy matrix** giúp responder quyết định nhanh nhưng vẫn phải đánh giá blast radius và provider.

| Sự kiện | Biện pháp ngăn đầu tiên | Thay vật liệu? | Di chuyển phụ thuộc? | Thu hồi trust? |
|---|---|---|---|---|
| **Plaintext DEK lộ** | Chặn Encrypt mới, cô lập source | Thường cần DEK mới | Thường re-encrypt dữ liệu liên quan | Thường không áp dụng public trust |
| **KEK lộ dạng rõ** | Chặn Wrap/Unwrap, kiểm kê grants | KEK mới; đánh giá DEK liên quan | Rewrap và có thể re-encrypt nếu DEK có thể lộ | Không trực tiếp, trừ hệ thống khác liên quan |
| **KMS principal bị chiếm** | Revoke credential/grants/session | Theo phạm vi API misuse | Đánh giá những DEK/secret đã bị truy cập | Nếu Sign bị lạm dụng, cần xem verifier |
| **Private signing key lộ** | Disable Sign và chặn IAM | Có | Phát hành key mới, cập nhật signer | **Có**, verifier/certificate/JWKS |
| **HMAC/PSK lộ** | Chặn MAC cũ theo risk, revoke credential | Có | Phân phối secret mới tới mọi bên | Có cơ chế đổi key acceptance tương ứng |
| **RNG yếu trong thời kỳ** | Dừng GenerateKey từ source lỗi | Có, với keys bị ảnh hưởng | Theo từng key type/data | Có nếu signing/public identity keys bị ảnh hưởng |
| **AES-GCM nonce reuse** | Chặn encrypt dưới key lỗi | Thường tạo DEK mới | Đánh giá re-encrypt và dữ liệu đã bị ảnh hưởng | Không phải vấn đề public trust trực tiếp |
| **Trust store/JWKS bị tráo** | Chặn nguồn trust giả, rollback có kiểm soát | Tùy mức lộ signing key | Cập nhật consumer caches | **Có**, xử lý niềm tin và danh tính |

**Không coi bảng là hệ thống ra quyết định tự động.** Với sự cố signing key liên quan chứng từ tài chính, nghĩa vụ pháp lý về chữ ký lịch sử có thể yêu cầu bước riêng. Với DEK đã bị lấy cắp, thay khóa không khắc phục bản sao plaintext đã được giải mã.

## 16. Tránh phá vỡ khả năng khôi phục khi containment

Một chính sách khẩn tốt phải xử lý **mâu thuẫn giữa bí mật và tính sẵn sàng**.

### 16.1. Fail-safe khác với xóa sớm

**Fail-safe:** nếu không thể xác thực key policy hoặc provider có lỗi, hệ thống không được tự dùng key dự phòng yếu hoặc mở quyền Sign/Decrypt trái phép.

**Không xóa sớm:** nếu một KEK đang bảo vệ backup, destroy ngay có thể gây mất dữ liệu không thể phục hồi. Có thể **disable và cô lập**, giữ đường recovery dưới quyền đặc biệt, kiểm kê và migrate trước khi destroy.

### 16.2. Kiểm kê trước irreversible actions

Trước khi ScheduleDelete/Destroy:

- Có bao nhiêu **encrypted DEK/ciphertext** còn phụ thuộc KEK/DEK?
- Có bản sao **backup/archive/DR/offline** chưa được migrate?
- Có **legal hold, retention hoặc điều tra** cần dữ liệu/khóa?
- Signing key có cần giữ **public key/chứng chỉ/timestamp** để xác minh lịch sử?
- Có thể **restore** bằng đường khóa thay thế trên môi trường kiểm thử được kiểm soát?
- Ai đã phê duyệt destruction và ai xác nhận provider đã hủy?

**Scheduled deletion không phải destruction.** Chỉ cập nhật trạng thái DESTROYED sau khi có bằng chứng provider thực sự đã hủy trong phạm vi quản lý. Cũng không thể “hủy từ xa” mọi bản sao mà kẻ tấn công đã lấy.

### 16.3. Nếu business phải ngừng hoạt động tạm thời

Sự gián đoạn do containment có thể cần thiết để ngăn tổn thất tiếp diễn. Quyết định mở lại phải dựa trên **khóa mới, quyền và trust đã kiểm chứng**, không phải chỉ vì một chỉ số availability bị giảm.

## 17. Audit, forensic evidence và bảo vệ bí mật khi điều tra

**Audit** là bằng chứng cho hai mục tiêu: **điều gì đã xảy ra** và **biện pháp ngăn ngừa có thực sự hiệu lực không**.

Một event minh họa:

~~~json
{
  "eventType": "KEY_EMERGENCY_CONTAINMENT",
  "incidentId": "SEC-2026-241",
  "operationId": "op-key-9381",
  "keyRef": "kms/prod-ap-southeast-1/payments-kek/v2",
  "signal": "UNAUTHORIZED_UNWRAP",
  "decision": "SUSPEND_KEY_AND_REVOKE_PRINCIPAL",
  "actor": "security-response-workflow",
  "approverRefs": ["approval-117"],
  "policyVersion": 3,
  "requestedAt": "2026-11-28T02:01:00Z",
  "providerConfirmedAt": "2026-11-28T02:01:25Z",
  "observedResult": "DISABLED",
  "consumerPropagation": "IN_PROGRESS"
}
~~~

Bản ghi này chỉ là **schema minh họa**, không phải payload chuẩn của mọi dịch vụ.

### 17.1. Metadata cần ghi

- **Key identity:** provider, account, region, ID/version, algorithm, key usage, origin.
- **Actor và quyền:** workload/identity, incident ID, reason, approval, break-glass usage.
- **Change:** state trước/sau, desired vs observed provider state, policy/grants thay đổi.
- **Timeline:** thời điểm nghi lộ, phát hiện, containment, cutover, revoke, verify và close.
- **Dependency:** encrypted DEK/dataset, certificate/JWKS/consumer refs, backup scope.
- **Verification:** kết quả negative tests, provider confirmation, trust propagation, exception và residual risk.
- **Evidence integrity:** nguồn log, timestamp, retention, phạm vi truy cập và bằng chứng chống chỉnh sửa trái phép.

### 17.2. Những gì tuyệt đối không cần đưa vào log

Không ghi plaintext **DEK, KEK, private signing key, ECDSA nonce k, HMAC secret, RNG seed/state, bearer token còn hiệu lực**, hoặc plaintext nhạy cảm chỉ để phục vụ debugging. Mỗi bản sao bí mật trong log có thể trở thành một compromise mới.

Một fingerprint của **public key** có thể hỗ trợ đối chiếu, nhưng **không tự chứng minh danh tính** của chủ thể nếu nguồn public key không đáng tin. Đừng dùng hash của dữ liệu có không gian giá trị nhỏ mà không đánh giá khả năng suy ra nội dung.

### 17.3. Chứng cứ về sự vắng mặt của hoạt động

Không tìm thấy lệnh Decrypt trong audit **không chứng minh** không có lạm dụng: có thể thiếu quyền đọc log, vùng không được thu thập, log retention quá ngắn hoặc key material đã bị sử dụng ngoài KMS. Báo cáo phải nói rõ **coverage, thời kỳ và hạn chế chứng cứ**.

## 18. Policy-as-code: mẫu khai báo có thể kiểm tra

Một chính sách nên đủ cụ thể để đội triển khai biến thành kiểm soát IAM, workflow và cảnh báo. Mẫu sau là **định dạng minh họa cho bài học**, không phải cú pháp import trực tiếp vào AWS/Azure/GCP KMS:

~~~yaml
policyName: key-compromise-emergency
policyVersion: 3
scope:
  environments: [production, staging]
  keyTypes: [DEK, KEK, HMAC, SIGNING, RECOVERY]
triggers:
  - CONFIRMED_SECRET_EXPOSURE
  - SUSPECTED_KEY_COMPROMISE
  - UNAUTHORIZED_SIGN_OR_UNWRAP
  - WEAK_KEY_GENERATION
  - CRYPTO_NONCE_MISUSE
  - TRUST_COMPROMISE
containment:
  requireIncidentId: true
  requireKeyMaterialVersion: true
  allowBreakGlassSuspend: true
  disableUnsafeOperations: true
  forbidWeakRandomFallback: true
recovery:
  replacementMustUseApprovedGenerator: true
  requireDataDependencyInventory: true
  requireConsumerTrustVerification: true
  verifyKmsObservedState: true
  allowAutomaticDestroy: false
destruction:
  requireDependencyClearance: true
  requireRetentionReview: true
  requireIndependentApproval: true
  requireProviderDestructionEvidence: true
audit:
  logSecretMaterial: false
  requireOperationId: true
  requireActorAndReason: true
  requirePostIncidentReview: true
~~~

**Policy-as-code chưa đủ nếu không được thực thi.** Cần kiểm tra runtime thực sự chặn Sign/Decrypt hoặc grants; KMS provider có thể có API, trạng thái, scope và quyền khác nhau. Không được tuyên bố khóa đã REVOKED chỉ từ việc cập nhật một file cấu hình.

### 18.1. Guard của bước hủy

Một công cụ có thể chặn yêu cầu destruction nếu:

- Chưa chứng minh các DEK/dataset/backup phụ thuộc đã được xử lý.
- Chưa có approval độc lập theo mức rủi ro.
- Provider chưa báo hủy thực tế.
- Một workflow incident khác đang điều tra key material.
- Lệnh được gửi cho **alias** thay vì material version chính xác.

Chỉ cần một guard không đạt, workflow phải giữ **PENDING/REVIEW**, không tự đổi trực tiếp thành DESTROYED.

## 19. Java 17: mô hình hóa quyết định phản ứng khẩn

Ví dụ dưới đây là **pure policy decision logic**: từ loại tín hiệu và metadata khóa, đề xuất các hành động cần review. Nó **không gọi KMS, không tắt key thật, không xóa secret và không tự xác thực IAM**; điều này giúp phân biệt **lớp ra quyết định** với **lớp thực thi có quyền**.

~~~java
import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;

public final class EmergencyCompromisePolicyExample {

    enum KeyKind { DEK, KEK, SIGNING, HMAC, RECOVERY }
    enum Signal {
        CONFIRMED_MATERIAL_EXPOSURE,
        SUSPECTED_COMPROMISE,
        API_MISUSE,
        WEAK_KEY_GENERATION,
        TRUST_COMPROMISE
    }
    enum Action {
        REVOKE_CALLER,
        SUSPEND_UNSAFE_USAGE,
        PRESERVE_EVIDENCE,
        INVENTORY_DEPENDENCIES,
        GENERATE_REPLACEMENT,
        REENCRYPT_DATA_REVIEW,
        REWRAP_DEK_REVIEW,
        REVOKE_VERIFIER_TRUST,
        DISTRIBUTE_NEW_SECRET,
        REQUIRE_MANUAL_APPROVAL
    }

    record KeyContext(
        String keyId,
        String materialVersion,
        KeyKind kind,
        boolean production,
        boolean dependenciesKnown,
        boolean exportedOrExposed
    ) {}

    record Incident(
        String incidentId,
        Signal signal,
        String reason
    ) {}

    record Decision(
        Set<Action> proposedActions,
        boolean destructiveActionAllowed,
        String explanation
    ) {}

    static Decision assess(KeyContext key, Incident incident) {
        Objects.requireNonNull(key);
        Objects.requireNonNull(incident);
        if (key.keyId() == null || key.keyId().isBlank()
                || key.materialVersion() == null
                || key.materialVersion().isBlank()
                || incident.incidentId() == null
                || incident.incidentId().isBlank()
                || incident.reason() == null
                || incident.reason().isBlank()) {
            throw new IllegalArgumentException(
                "Incident, key identity and reason are required");
        }
        Objects.requireNonNull(key.kind());
        Objects.requireNonNull(incident.signal());

        EnumSet<Action> actions = EnumSet.of(
            Action.PRESERVE_EVIDENCE,
            Action.INVENTORY_DEPENDENCIES,
            Action.SUSPEND_UNSAFE_USAGE,
            Action.REQUIRE_MANUAL_APPROVAL
        );

        if (incident.signal() == Signal.API_MISUSE) {
            actions.add(Action.REVOKE_CALLER);
        }

        if (key.exportedOrExposed()
                || incident.signal()
                    == Signal.CONFIRMED_MATERIAL_EXPOSURE
                || incident.signal()
                    == Signal.WEAK_KEY_GENERATION) {
            actions.add(Action.GENERATE_REPLACEMENT);
        }

        switch (key.kind()) {
            case DEK -> actions.add(Action.REENCRYPT_DATA_REVIEW);
            case KEK -> actions.add(Action.REWRAP_DEK_REVIEW);
            case SIGNING -> {
                actions.add(Action.GENERATE_REPLACEMENT);
                actions.add(Action.REVOKE_VERIFIER_TRUST);
            }
            case HMAC -> actions.add(Action.DISTRIBUTE_NEW_SECRET);
            case RECOVERY -> actions.add(Action.GENERATE_REPLACEMENT);
        }

        if (incident.signal() == Signal.TRUST_COMPROMISE) {
            actions.add(Action.REVOKE_VERIFIER_TRUST);
        }

        // Destruction is NEVER automatically authorized by this engine.
        // Even if dependenciesKnown is true, approval and KMS evidence
        // must be checked by an independent destructive workflow.
        boolean destructiveActionAllowed = false;

        String explanation = key.dependenciesKnown()
            ? "Review evidence, approve replacement and verify cutover"
            : "Unknown dependencies: contain but do not destroy";

        return new Decision(
            Set.copyOf(actions),
            destructiveActionAllowed,
            explanation
        );
    }

    public static void main(String[] args) {
        KeyContext key = new KeyContext(
            "payments-kek", "v2", KeyKind.KEK,
            true, false, false);

        Incident incident = new Incident(
            "SEC-2026-241",
            Signal.API_MISUSE,
            "Unexpected Unwrap calls from compromised workload");

        Decision decision = assess(key, incident);
        if (!decision.proposedActions()
                .contains(Action.REVOKE_CALLER)
                || decision.destructiveActionAllowed()) {
            throw new IllegalStateException("Policy decision error");
        }
        System.out.println(decision.explanation());
    }
}
~~~

### 19.1. Ví dụ minh họa được gì?

- Có **key ID/material version**, signal và incident reason bắt buộc.
- Mọi sự cố đều yêu cầu **bảo toàn chứng cứ và kiểm kê phụ thuộc**.
- Khi có API misuse, đề xuất **cô lập caller**.
- Hành động khác nhau theo loại khóa: **DEK → review re-encrypt; KEK → review rewrap; SIGNING → revoke trust; HMAC → phân phối secret mới**.
- Không cho một engine chỉ dựa vào signal **tự động hủy key material**.
- Các action là **đề xuất**, không phải kết luận rằng thao tác đã hoàn thành.

### 19.2. Vì sao không cho code gọi DisableKey trực tiếp?

Một chương trình đơn giản không thể biết tất cả **IAM approvals, provider behavior, encrypted DEK dependencies, legal holds, trust propagation và backup**. Production cần:

1. **IAM + policy guards** từ nguồn đáng tin, không nhận boolean approved từ client.
2. **Idempotency key/incident ID** để ngăn retry nhân đôi thao tác.
3. **Optimistic locking** theo revision và key version.
4. **Orchestration KMS/HSM**, đọc lại trạng thái, outbox/reconciliation.
5. Phân tách **emergency suspend** với **irreversible destruction**.
6. Audit độc lập, negative tests và xác nhận consumer đã cập nhật.
7. Quy trình phản ứng và mức severity theo hệ thống thực tế.

Đây là ví dụ giúp học cách tách **policy decision** khỏi **policy enforcement**, không phải hệ thống quản trị khóa sản xuất.

## 20. Mục tiêu vận hành, cảnh báo và rủi ro tồn dư

Các chỉ số không nên chỉ đo “thời gian đóng ticket”. Cần theo dõi mức độ khống chế thực tế:

| Chỉ số | Cách hiểu |
|---|---|
| **Time to detect** | Từ hành vi đầu tiên quan sát được tới khi hệ thống phát hiện |
| **Time to contain** | Từ khi phát hiện tới khi những đường dùng khóa nguy hiểm bị chặn có bằng chứng |
| **Unverified revocations** | Số key đã requested revoke nhưng provider/consumer chưa xác nhận |
| **Stale verifier exposure** | Số issuer/client còn trust key bị lộ theo dữ liệu quan sát |
| **Affected key versions** | Những vật liệu và phiên bản trong blast radius |
| **Data migration completion** | Tỷ lệ dữ liệu/DEK đã rewrap hoặc re-encrypt và được kiểm thử |
| **Break-glass audits completed** | Số lần dùng quyền khẩn đã được hậu kiểm độc lập |
| **Residual risk exceptions** | Những điểm chưa thể xử lý, owner/phê duyệt và thời hạn |
| **Backup restore assurance** | Kết quả chứng minh dữ liệu hợp lệ còn khôi phục được sau thay key |

**Không có một SLA cố định áp dụng cho mọi key.** Chính sách nên định nghĩa mục tiêu theo loại dữ liệu, mức criticality, số lượng consumer và yêu cầu pháp lý. Một khóa signing cho hệ thống giao dịch có thể cần hành động nhanh hơn khóa test đã disabled, nhưng việc destroy lại phụ thuộc nhiều bằng chứng hơn.

### 20.1. Theo dõi tới lúc kết thúc thật

Nếu KMS trả kết quả thành công nhưng client offline chưa cập nhật public trust, trạng thái nên được mô tả là **containment partly complete**, không phải “all systems secure”. Bất cứ exception nào phải có **owner, hạn hiệu lực, kiểm soát bù trừ và kế hoạch giải quyết**.

## 21. Case study A: lạm dụng quyền Unwrap ở nền tảng đa tenant

Một nền tảng Java lưu hồ sơ, mỗi dataset dùng **AES-GCM DEK** được bảo vệ dưới **KEK trong KMS**. Giám sát phát hiện workload A gọi Unwrap hàng loạt ngoài tenant được phê duyệt.

### 21.1. Điều tra ban đầu

- **Fact:** có các API calls bất thường, principal và key version xác định.
- **Uncertainty:** chưa có bằng chứng KEK non-exportable đã bị xuất; chưa biết plaintext DEK và dữ liệu nào bị truy cập.
- **Risk:** đối thủ có thể lấy DEK qua những calls đã chạy và dùng để decrypt ciphertext đã thu thập.

### 21.2. Thực hiện chính sách

1. Cô lập workload credential, revoke grants và kiểm tra các principal liên quan.
2. Tạm chặn đường Unwrap nguy hiểm, giữ recovery path có kiểm soát cho dữ liệu cần thiết.
3. Kiểm kê DEK/dataset đã được unwrap trong cửa sổ nghi lộ, đối chiếu KMS audit và application logs.
4. Sinh key material mới nếu cần; đánh giá thay DEK/re-encrypt những dataset có nguy cơ.
5. Rewrap DEK dưới KEK mới khi phù hợp và có kế hoạch cho backups.
6. Xác minh service hợp lệ vẫn decrypt được dữ liệu sau cutover và principal bị chiếm không còn quyền.
7. Ghi residual risk cho dữ liệu có thể đã bị truy cập trước khi containment.

**Bài học:** chỉ rotate KEK hoặc chỉ disable principal chưa đủ để kết luận những DEK đã bị trả về trong thời gian bị lạm dụng vẫn bí mật.

## 22. Case study B: lộ signing key phát hành chứng từ

Một dịch vụ ký chứng từ bằng private key **v3** trong HSM. Có bằng chứng một bản sao của private key từng được export và được lưu tại nơi không còn kiểm soát.

### 22.1. Phản ứng đúng

1. Chặn quyền Sign v3, cô lập credential/copying path và lưu evidence an toàn.
2. Sinh signing key v4 từ nguồn tin cậy, kiểm soát non-exportable và key usage.
3. Phát hành public key/chứng chỉ v4 theo quy trình đáng tin.
4. Chuyển signer sang v4, cập nhật verifier và chính sách chấp nhận thuật toán.
5. Rút trust của v3 theo chính sách CA/JWKS/issuer, theo dõi cache và client ngoại tuyến.
6. Điều tra chứng từ v3 trong thời kỳ nghi lộ: thời điểm, phê duyệt nghiệp vụ, log ký, timestamp.
7. Lưu public key/chứng cứ lịch sử theo retention; hủy private v3 khi đủ điều kiện, không xem hủy là cách xóa bản sao trong tay đối thủ.

### 22.2. Lỗi cần tránh

- Chỉ đổi **kid** nhưng vẫn dùng cùng private material.
- Chỉ disabled v3 ở HSM mà không cập nhật verifier.
- Tuyên bố mọi chứng từ lịch sử đều giả chỉ vì private key bị lộ sau này.
- Ghi private key ra log để hỗ trợ điều tra.

## 23. Case study C: lỗi nguồn randomness làm nhiều khóa yếu

Một phiên bản dịch vụ Java từng tạo key bằng **java.util.Random** với seed gần thời gian khởi động. Dù khóa AES dài 256 bit, entropy của nguồn seed có thể thấp.

**Chính sách khẩn cần:**

1. Dừng code sinh khóa lỗi và **không fallback sang seed yếu** khi CSPRNG không khả dụng.
2. Xác định thời gian triển khai, host, tenant, tất cả key material được sinh và public key tương ứng.
3. Đánh giá DEK/KEK/signing/HMAC/credential nào được tạo trong giai đoạn lỗi.
4. Sinh key material mới bằng **SecureRandom/KeyGenerator hoặc KMS/HSM** đã được phê duyệt.
5. Chuyển dữ liệu, trust và consumers tùy loại khóa; chú ý backup và nonce state sau restore.
6. Đối với private signing keys nghi yếu, cập nhật verifier/issuer và đánh giá chữ ký lịch sử.
7. Kiểm thử code review, pipeline/deployment và môi trường snapshot/fork để ngăn tái diễn.

**Reseed hôm nay không làm các khóa yếu được tạo hôm qua mạnh lên.** Những key versions đã phát hành cần được quản lý và thay thế theo phạm vi rủi ro.

## 24. Ma trận diễn tập và kiểm thử emergency policy

| Tình huống kiểm thử | Kết quả mong đợi |
|---|---|
| Bị lộ DEK, caller yêu cầu chỉ rewrap | Workflow cảnh báo chưa thay DEK; review re-encrypt |
| KEK non-exportable nhưng IAM Unwrap bị chiếm | Cô lập principal và đánh giá các DEK đã unwrap |
| Private signing key bị lộ | Chặn Sign và revoke trust ở verifier |
| Certificate/JWKS cache còn key cũ | Không báo propagation hoàn tất |
| AES-GCM nonce reuse được xác nhận | Dừng Encrypt dưới key bị ảnh hưởng, review tác động |
| HMAC secret ở nhiều consumers | Phát hành secret mới, kiểm tra từng nơi đã cập nhật |
| RNG lỗi khi GenerateKey | Không fallback sang java.util.Random/timestamp |
| Revoke request từ principal không có quyền | Từ chối và audit |
| Break-glass hợp lệ | Chặn được usage theo scope, audit và quyền hết hạn đúng |
| Break-glass yêu cầu Destroy ngay | Từ chối nếu thiếu approval/dependency evidence |
| Hai workflow rotate/revoke đồng thời | Revoke không bị request cũ ghi đè |
| Retry cùng operation ID sau timeout | Không tạo thao tác phá hủy/cấp quyền lặp |
| KMS Disable thành công, registry update lỗi | Reconciliation phát hiện, fail-safe được giữ |
| Registry REVOKED nhưng KMS vẫn cho Sign | Kiểm thử thất bại, yêu cầu chặn ở data plane |
| KMS disabled nhưng verifier vẫn chấp nhận chữ ký mới từ key lộ | Báo trust chưa thu hồi |
| KEK còn encrypted DEK trong backup | Không hủy trước khi xử lý dependency |
| ScheduleDelete trả ACK | Không đánh dấu DESTROYED khi chưa xác nhận hủy thật |
| Chữ ký lịch sử cần kiểm tra | Có public key/certificate và evidence theo policy |
| Session ticket còn hiệu lực sau đổi TLS certificate | Đánh giá/thu hồi resumption secret riêng |
| Audit sự cố | Đủ key ID/version, actor, reason, approvals, results, không có secret |
| Client ngoại tuyến chưa nhận trust update | Ghi rủi ro tồn dư và phương án xử lý |
| Khôi phục sau containment | Chỉ mở lại bằng key/version và quyền đã kiểm chứng |

**Diễn tập phải bao gồm multi-account, multi-region, nhiều instance, cache, job offline, backup/DR và nhà cung cấp bên ngoài.** Chạy test đơn vị với trạng thái REVOKED không chứng minh mọi consumer đã ngừng tin khóa cũ.

## 25. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách phòng ngừa |
|---|---|---|
| Chỉ đổi field status=REVOKED | KMS vẫn cho API dùng khóa | Verify provider observed state và IAM |
| Hủy KEK ngay khi báo incident | Mất đường Unwrap dữ liệu/backup hợp lệ | Contain trước, inventory/rewrap/migration rồi mới hủy |
| Coi HSM non-exportable nghĩa không thể bị lạm dụng | Signing/decryption oracle qua IAM | Phân biệt key-material exposure và API misuse |
| Rewrap DEK đã bị lộ rồi tuyên bố an toàn | Đối thủ vẫn có plaintext DEK | Thay DEK và re-encrypt nếu cần |
| Chỉ đổi key alias | Key material cũ vẫn được dùng | Tạo version/vật liệu mới độc lập |
| Chỉ disabled signing key | Verifier có thể tiếp tục tin private key bị sao chép | Revoke public trust/cert và xử lý cache |
| Xóa public key và timestamp lịch sử | Mất bằng chứng kiểm tra chữ ký cũ | Retain theo chính sách |
| Không xử lý JWT/session ticket/token | Credential cũ vẫn hoạt động | Thu hồi/kiểm tra từng loại credential |
| Ghi plaintext keys vào forensic logs | Tạo thêm điểm rò rỉ | Chỉ lưu metadata, evidence bảo vệ |
| Giữ quyền break-glass vĩnh viễn | Tạo đường lạm dụng mới | TTL/MFA/audit/hậu kiểm |
| Reopen key sau incident bởi workflow stale | Tái kích hoạt key bị lộ | Revision, fencing và deny REVOKED → ACTIVE |
| Bỏ qua cache/đối tác ngoại tuyến | Revocation chỉ đúng ở control plane | Trust propagation và residual-risk tracking |
| Không xét source entropy và VM restore | Secret tiếp tục được sinh yếu/lặp | Đánh giá RNG, rotate các key bị ảnh hưởng |
| Không audit quyền ChangedKeyPolicy | Không biết ai mở grants nguy hiểm | Independent IAM/KMS audit |
| Kết luận hết rủi ro vì không thấy log | Phạm vi log không đầy đủ hoặc key dùng bên ngoài | Nêu rõ giới hạn evidence |

## 26. Câu hỏi tự kiểm tra

**Câu 1. Emergency compromise policy khác rotation policy thông thường ra sao?**

**Trả lời:** Rotation định kỳ có thể chuyển giao theo kế hoạch; emergency compromise policy ưu tiên containment, blast-radius assessment, rút quyền/niềm tin, thay khóa và xác minh sự cố khi nguy cơ đang tồn tại.

**Câu 2. KMS key non-exportable có thể bị lạm dụng không?**

**Trả lời:** Có. Workload có quyền Sign/Decrypt/Unwrap bị chiếm vẫn có thể yêu cầu KMS thực hiện phép toán trái phép.

**Câu 3. Có thể xóa ngay KEK khi nghi lộ không?**

**Trả lời:** Không mặc nhiên. Phải đánh giá encrypted DEK, dữ liệu, backup và khả năng restore; containment có thể được thực hiện trước destructive action.

**Câu 4. Vì sao disable private signing key chưa đủ?**

**Trả lời:** Đối thủ có bản sao private key vẫn có thể ký ngoài KMS, còn verifier vẫn có thể tin public key cũ. Cần revoke trust và kiểm tra propagation.

**Câu 5. Rewrap DEK có khắc phục lộ plaintext DEK không?**

**Trả lời:** Không. Nếu DEK đã lộ, kẻ tấn công vẫn dùng nó giải mã ciphertext tương ứng; thường phải đánh giá thay DEK/re-encrypt.

**Câu 6. Khi nào có thể cho responder dùng break-glass?**

**Trả lời:** Khi trigger khẩn được thỏa, với danh tính mạnh, quyền giới hạn, audit độc lập và hậu kiểm theo policy.

**Câu 7. Khác biệt giữa SUSPENDED và REVOKED là gì?**

**Trả lời:** SUSPENDED là tạm ngừng trong khi điều tra, có thể resume sau đánh giá; REVOKED biểu thị rút quyền/niềm tin và không nên tự động khôi phục vật liệu đã bị lộ.

**Câu 8. Vì sao phải đọc lại observed KMS state?**

**Trả lời:** Registry desiredState hoặc HTTP ACK không chứng minh thao tác bị cấm đã bị từ chối trong KMS/HSM thật.

**Câu 9. Chữ ký cũ có mặc nhiên giả khi signing key bị lộ?**

**Trả lời:** Không. Phải kiểm tra chứng cứ về thời điểm tạo chữ ký, policy tin cậy, trạng thái chứng chỉ và nghiệp vụ; phép Verify toán học một mình không đủ.

**Câu 10. Forward secrecy có bảo vệ mọi lưu lượng cũ khi TLS signing key lộ không?**

**Trả lời:** Không bảo đảm tuyệt đối. Nó bảo vệ trong mô hình cụ thể khi ephemeral/traffic secrets và bản rõ chưa lộ; phải xem giao thức và sự cố thực tế.

**Câu 11. Sau khi sửa CSPRNG yếu, khóa cũ có tự mạnh lên không?**

**Trả lời:** Không. Phải kiểm kê và thay những khóa được sinh từ nguồn yếu, cùng xử lý dữ liệu/chứng cứ liên quan.

**Câu 12. Tại sao cần operation ID và revision?**

**Trả lời:** Để retry có kiểm soát và ngăn yêu cầu stale/rotation cũ ghi đè quyết định REVOKED mới.

**Câu 13. Có nên cho một policy engine tự động DeleteKey khi gặp cảnh báo nghi compromise?**

**Trả lời:** Không. Destruction cần kiểm tra phụ thuộc, retention, approval và provider evidence vì có thể gây mất dữ liệu không thể khôi phục.

**Câu 14. JWT kid có chứng minh public key đáng tin không?**

**Trả lời:** Không. kid chỉ giúp tra key; trust phải dựa vào issuer/key distribution đáng tin và toàn bộ chính sách xác minh.

**Câu 15. Khi nào có thể đóng một incident liên quan khóa?**

**Trả lời:** Khi containment, key cutover, KMS/IAM enforcement, trust propagation, data migration và audit đã được xác minh theo scope; các rủi ro còn lại được ghi và chấp nhận bởi người có thẩm quyền.

## 27. Checklist áp dụng vào thiết kế thực tế

Trước khi phê duyệt một **emergency compromise policy**, cần kiểm tra:

- **Inventory:** xác định key ID/material version, key type, owner, provider, environment, cryptoperiod và origin?
- **Trigger:** confirmed/suspected exposure, API misuse, trust/entropy/nonce failure có điều kiện rõ?
- **Scope:** xác định DEK, KEK, ciphertext, encrypted DEK, tenant, backup, HMAC peers, signing verifiers và phiên còn hoạt động?
- **Roles:** incident commander, security responder, KMS/HSM operator, data owner, PKI owner và auditor có thẩm quyền rõ?
- **Break-glass:** MFA, TTL, quyền tối thiểu, audit độc lập và hậu kiểm có sẵn?
- **Containment:** có thể chặn API Sign/Encrypt/Unwrap và IAM principals tại đường thực thi?
- **Replacement:** có thể GenerateKey an toàn từ CSPRNG/KMS/HSM, không dùng vật liệu cũ hoặc alias giả?
- **Data migration:** biết khi nào chỉ rewrap KEK, khi nào phải thay DEK và re-encrypt?
- **Signing trust:** public key/JWKS/certificate, CRL/OCSP, cache, client offline và lịch sử được xử lý?
- **Protocol:** AES-GCM nonce uniqueness, HMAC rotation, TLS resumption và token revocation có được xem xét?
- **Consistency:** có desired/observed state, revision, idempotency, outbox, retry, reconciliation và chống stale workflow?
- **Destruction:** có inventory dependencies, backup/retention review, independent approval và provider destruction evidence?
- **Audit:** ghi actor, reason, policy version, operation ID, timestamps, kết quả mà không ghi secret material?
- **Verification:** negative tests ở KMS, ứng dụng, verifier, cache và restore có được thực hiện?
- **Drills:** đã diễn tập compromise DEK/KEK/signing/HMAC, VM rollback, network/KMS outage và client offline?
- **Residual risk:** có owner, deadline, kiểm soát bù trừ và bằng chứng chấp nhận risk exception khi chưa xử lý được mọi nơi?

**Ghi nhớ:** **Emergency compromise policy** không phải nút “xóa khóa khẩn cấp”. Đó là quy trình **phân loại compromise → cô lập khả năng sử dụng → điều tra phụ thuộc → sinh vật liệu an toàn → chuyển dữ liệu và niềm tin → xác minh hiệu lực → quản lý bằng chứng và rủi ro tồn dư**. Một chính sách tốt kết hợp **KMS/HSM, DEK/KEK, envelope encryption, chữ ký số, IAM, kiểm toán, rotation, revocation và destruction** để vừa ngăn rò rỉ hoặc giả mạo, vừa tránh làm mất dữ liệu hợp lệ do phản ứng vội vàng.
