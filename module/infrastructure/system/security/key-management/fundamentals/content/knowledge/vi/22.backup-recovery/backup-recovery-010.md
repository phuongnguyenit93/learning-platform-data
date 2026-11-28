# Quorum cho key recovery: Khôi phục khóa với kiểm soát M-of-N

Một doanh nghiệp dùng **KMS/HSM** để bảo vệ KEK gốc, khóa ký của hệ thống thanh toán và dữ liệu mã hóa nhiều năm. Khi trung tâm dữ liệu chính gặp sự cố, đội vận hành cần khôi phục khả năng truy cập. Nếu chỉ một quản trị viên có thể lấy backup key và restore toàn bộ khóa, một tài khoản bị chiếm có thể trở thành điểm phá vỡ toàn bộ hệ thống. Nếu yêu cầu cả mười người cùng có mặt, việc khôi phục lại có thể bất khả thi khi có người nghỉ phép, mất liên lạc hoặc gặp thảm họa.

**Quorum cho key recovery** giải quyết bài toán này bằng cách yêu cầu một **ngưỡng M trong tổng số N người hoặc phần bí mật độc lập** cùng tham gia theo một quy trình được kiểm soát. Ví dụ, cấu hình **3-of-5** cho phép khôi phục khi có ít nhất ba custodian hợp lệ trong năm người được chỉ định. Một người đơn lẻ không đủ quyền thực hiện recovery; tổ chức vẫn có khả năng phục hồi khi một hoặc hai custodian không sẵn sàng.

Tuy nhiên, cụm từ **M-of-N** có thể mô tả những cơ chế rất khác nhau: **quorum phê duyệt**, **split knowledge**, **Shamir Secret Sharing**, **HSM M-of-N authentication** hoặc **threshold cryptography**. Chúng không thể thay thế lẫn nhau. Cần xác định rõ quorum đang kiểm soát **ai được phép ra lệnh**, **ai nắm share**, hay **phép toán mật mã được phân tán thế nào**.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài này kết nối vòng đời khóa từ tạo, cấp phát, lưu trữ, sử dụng, xoay vòng đến thu hồi và hủy với **backup/restore, KMS/HSM, envelope encryption, key hierarchy, kiểm soát truy cập, separation of duties và audit**. Mục tiêu là thiết kế một quy trình có thể **khôi phục được, chống lạm dụng và kiểm chứng được**, không biến backup thành một bản sao bí mật có quyền truy cập quá rộng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **quorum M-of-N** và phân biệt quorum approval, split knowledge, Shamir Secret Sharing và threshold cryptography.
2. Phân biệt **key backup, key recovery, data recovery, key escrow, restore và disaster recovery**.
3. Chọn ngưỡng M/N theo cân bằng giữa **khả dụng, chống thông đồng, nguy cơ mất share và mức độ ảnh hưởng của khóa**.
4. Thiết kế vai trò **key owner, recovery custodian, security officer, HSM operator, approver và auditor** với separation of duties.
5. Hiểu cách một **HSM/KMS** triển khai quorum hoặc backup/restore, và vì sao hành vi phụ thuộc sản phẩm/provider.
6. Bảo vệ share bằng **custody độc lập, xác thực mạnh, mã hóa khi lưu/truyền, kiểm kê, rotation và thu hồi**.
7. Thiết kế **recovery ceremony** có xác minh mục đích, người tham gia, key identity/version, approvals, dual control và audit evidence.
8. Phân biệt khôi phục **KEK/DEK, private signing key, HMAC secret và CA root key**, tránh khôi phục nhầm material hoặc mở rộng blast radius.
9. Lập kế hoạch **backup dependency, recovery testing, RTO/RPO, quorum availability, incident response và post-recovery validation**.
10. Đọc ví dụ **Java 17** mô phỏng quorum authorization và hiểu vì sao code đếm approval không phải triển khai Shamir hay HSM threshold.

## 2. Vì sao key recovery cần quorum?

### 2.1. Một khóa có thể là điểm phụ thuộc của rất nhiều dữ liệu

Trong envelope encryption:

~~~text
Customer records
      |
      | Encrypt bằng DEK
      v
Content ciphertext + nonce + tag
      |
      | DEK được Wrap bằng KEK
      v
Encrypted DEK (EDK)
      |
      | KEK được quản lý trong KMS/HSM
      v
Key hierarchy / recovery material
~~~

Nếu **KEK bị mất hoàn toàn** và không có đường phục hồi hợp lệ, EDK có thể không mở được; khi đó ciphertext vẫn còn nhưng dữ liệu không thể khôi phục bằng hệ thống bình thường. Nếu **backup/recovery root key bị lộ**, attacker có thể có khả năng khôi phục hoặc mở nhiều khóa phụ thuộc.

Quorum bảo vệ một thao tác rất nhạy cảm: **đưa quyền recovery trở lại trạng thái có thể sử dụng**. Nhưng nó không thay thế backup đầy đủ, metadata, thuật toán, KMS/HSM, ciphertext và quyền truy cập dữ liệu.

### 2.2. Hai mục tiêu xung đột

| Mục tiêu | Câu hỏi thiết kế |
|---|---|
| **Security** | Bao nhiêu người thông đồng mới đủ khôi phục? Một custodian bị chiếm có thể làm gì? |
| **Availability** | Nếu một hoặc hai người không có mặt, tổ chức có khôi phục đúng hạn không? |
| **Integrity** | Làm sao chắc đúng key, đúng version, đúng backup và không bị thay thế? |
| **Confidentiality** | Có ai nhìn thấy raw key trong lúc tạo share, phục hồi hoặc import không? |
| **Accountability** | Ai đề xuất, ai duyệt, ai thực hiện, ai xác minh kết quả? |
| **Recoverability** | Đã thực sự thử restore trong môi trường DR và đo RTO/RPO chưa? |

**Quorum quá thấp** làm tăng nguy cơ thông đồng hoặc chiếm đủ số share. **Quorum quá cao** làm tăng nguy cơ không thể phục hồi khi có nhân sự nghỉ việc, mất thiết bị hoặc thảm họa. M/N phải dựa trên threat model, phân tán địa lý/tổ chức và mức độ criticality của khóa.

### 2.3. Một tình huống 3-of-5

Giả sử năm custodian được chỉ định:

| Custodian | Vai trò | Miền lưu giữ độc lập |
|---|---|---|
| A | Security custodian | Site Bắc |
| B | Platform custodian | Site Trung |
| C | Key management custodian | Site Nam |
| D | Risk/continuity custodian | Kho offline độc lập |
| E | HSM operations custodian | Site DR |

Với ngưỡng **M=3, N=5**:

- A+B+C có thể đạt quorum nếu cả ba xác thực và đáp ứng policy.
- A+B chưa đủ; không được “mượn” approval của một người vắng mặt.
- Ba approvals từ cùng một tài khoản hoặc cùng một share index không được tính thành ba người độc lập.
- Ba người cùng một site có thể tạo rủi ro **common-mode failure**; số lượng người không thay thế tính độc lập của nơi lưu giữ.

Ví dụ này là mô hình tổ chức. Thực tế, một HSM có thể yêu cầu **M token/card/share cụ thể**, còn một workflow KMS có thể yêu cầu **M approvals độc lập**. Cần đọc semantics của provider thay vì suy ra từ nhãn “3-of-5”.

## 3. Phân biệt năm cơ chế thường bị gọi chung là quorum

### 3.1. Quorum approval: N người phê duyệt một hành động

Một hệ thống workflow có thể yêu cầu **ít nhất M approvers khác nhau** đồng ý trước khi một operator được thực hiện recovery. Ví dụ:

~~~text
Recovery request
    -> Verify incident/ticket + key identity
    -> Collect approvals from M distinct authorized people
    -> Validate expiry, role, MFA, SoD
    -> Execute approved restore in HSM/KMS
    -> Audit outcome
~~~

Ở đây, quorum kiểm soát **quyền thực hiện hành động**. Các approvers không nhất thiết nắm một phần key material. Nếu một service account vẫn có thể gọi API restore trực tiếp mà không qua workflow, quorum approval ở tầng giao diện có thể bị bypass.

### 3.2. Split knowledge / dual control

**Split knowledge** chia thông tin bí mật thành các phần mà một cá nhân không biết toàn bộ bí mật. **Dual control** yêu cầu ít nhất hai người cùng kiểm soát hoặc thực hiện một thao tác nhạy cảm.

Ví dụ, hai custodians cùng tham gia nhập các phần activation secret của một HSM. Từng người chỉ biết phần của mình. Cơ chế cụ thể có thể là:

- Mỗi người giữ một phần **PIN/activation secret** độc lập.
- HSM yêu cầu hai người xác thực trước khi cho phép thao tác.
- Một quy trình vận hành yêu cầu hai người cùng hiện diện và kiểm tra màn hình/biên bản.

**Dual control không mặc nhiên là M-of-N secret sharing**. Một hệ thống hai người cùng bấm approve có thể vẫn chỉ là workflow approval; một hệ thống split secret có thể yêu cầu kết hợp material. Cần xác định chính xác điều gì được chia.

### 3.3. Shamir Secret Sharing: Chia một secret thành N shares, cần M shares

**Shamir Secret Sharing (SSS)** là một cơ chế mật mã threshold. Một secret được biểu diễn trong một trường hữu hạn và tạo thành các share sao cho:

- Có ít nhất **M shares hợp lệ, khác nhau** thì có thể khôi phục secret.
- Có ít hơn **M shares** thì không thu được thông tin về secret trong mô hình lý tưởng của scheme.
- Có thể tạo **N shares** từ một secret với threshold M, trong điều kiện triển khai đúng.

Ví dụ **3-of-5**: tạo năm shares từ một recovery secret; bất kỳ ba shares hợp lệ có thể tái tạo secret, còn một hoặc hai shares không đủ.

Với trường hữu hạn thích hợp, ý tưởng toán học là đa thức:

\[
f(x)=s+a_1x+a_2x^2+\cdots+a_{M-1}x^{M-1}
\]

Trong đó **s** là secret, các hệ số ngẫu nhiên được chọn trong trường hữu hạn, và share thứ i chứa một điểm **(x_i, f(x_i))**. M điểm khác nhau cho phép nội suy để lấy lại **f(0)=s**. Ít hơn M điểm không xác định duy nhất đa thức bậc M-1.

**Không tự viết thuật toán Shamir bằng code ứng dụng để backup production keys.** Cần thư viện/thiết bị đã được đánh giá, encoding chính xác, entropy, integrity, share authentication, versioning và quy trình ceremony. Bài học này tập trung vào policy và vận hành; ví dụ Java sau chỉ mô phỏng **quorum approval**, không chứa implementation SSS.

### 3.4. HSM M-of-N authentication / quorum control

Một số HSM có cơ chế quản trị yêu cầu một số lượng **security officer tokens, smart cards, activation cards hoặc credentials** cùng tham gia trước khi thực hiện một số hành động. Có thể có:

- Quorum cho **activate/deactivate security domain**.
- Quorum cho **backup/restore** hoặc thay đổi cấu hình nhạy cảm.
- **M-of-N operator authentication** cho thao tác quản trị.
- Backup key/secret được bảo vệ bằng cơ chế HSM-specific.

Đây là **hành vi phụ thuộc sản phẩm, firmware, partition/domain và cấu hình**. Không được giả định mọi HSM đều dùng Shamir, mọi quorum đều áp dụng cho từng crypto operation hoặc raw private key luôn được chia thành shares.

### 3.5. Threshold cryptography: Phép toán được phân tán

Trong **threshold signature** hoặc threshold decryption, nhiều participants cùng tạo kết quả mật mã theo giao thức mà private key có thể **không bao giờ được tái tạo hoàn chỉnh tại một máy**.

Điều này khác với Shamir recovery:

| Cơ chế | Mục tiêu | Secret có được tái tạo tại một điểm không? |
|---|---|---|
| **Quorum approval** | N người phê duyệt hành động | Không liên quan trực tiếp tới key bytes |
| **Shamir Secret Sharing** | Chia và phục hồi một secret | Thường có thể tái tạo secret trong recovery boundary |
| **HSM M-of-N authentication** | Kiểm soát quyền quản trị/activation | Tùy HSM; key có thể luôn nằm trong thiết bị |
| **Threshold signing/decryption** | Phân tán chính phép toán mật mã | Có thể không bao giờ tái tạo full private key |

Không gọi một workflow “3 approvers” là **threshold signature**. Threshold cryptography có protocol, key generation/resharing, share verification, network assumptions và threat model riêng.

## 4. Key backup, key recovery và data recovery

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Key backup** | Tạo bản backup được bảo vệ của key material hoặc key object theo provider | HSM backup blob được wrap bằng backup key |
| **Key recovery** | Khôi phục khả năng dùng key sau mất/hỏng/DR | Restore HSM object hoặc reconstruct recovery secret |
| **Data backup** | Lưu ciphertext và metadata cần thiết để phục hồi dữ liệu | Snapshot DB chứa ciphertext, EDK, nonce, AAD schema |
| **Data recovery** | Khôi phục dữ liệu và quyền đọc hợp lệ | Restore DB + KMS/HSM keys + IAM/policy |
| **Key escrow** | Bên được chỉ định giữ khả năng khôi phục key theo điều kiện | Escrow key theo policy và dual control |
| **Disaster recovery (DR)** | Khôi phục dịch vụ trong một sự cố lớn | Region DR, HSM backup, restore runbook, RTO/RPO |

**Backup thành công không chứng minh recovery thành công.** Một file backup có thể bị hỏng, không tương thích firmware, thiếu wrapping key, thiếu share, sai version hoặc không có quyền restore.

### 4.1. Data recovery cần nhiều hơn key

Để phục hồi một bản ghi envelope, có thể cần:

1. Ciphertext và authentication tag.
2. Nonce/IV và thuật toán đúng.
3. AAD/encryption context đúng phiên bản.
4. Encrypted DEK (EDK) hoặc provider ciphertext blob.
5. KEK/key version và quyền Unwrap.
6. Key registry/metadata, tenant/resource mapping.
7. Application schema/format version và authorization.

Nếu chỉ backup **KEK** mà mất ciphertext, dữ liệu không phục hồi được. Nếu chỉ backup **ciphertext** mà mất KEK/EDK dependencies, dữ liệu cũng có thể không mở được.

### 4.2. Không backup một key bằng chính nó

Backup key cần có **key hierarchy độc lập**. Không thể chỉ nói “mã hóa backup của KEK bằng chính KEK đó” rồi cho rằng đã có đường phục hồi nếu KEK mất. Cần một **backup wrapping key/recovery root** được bảo vệ độc lập, với quorum và quy trình recovery riêng.

~~~text
Production KEK
    -> Wrap DEKs
    -> EDKs trong data store

Recovery root / backup wrapping key
    -> Bảo vệ backup material hoặc HSM backup blob
    -> Có custody, quorum, offline protection riêng

Recovery of recovery root
    -> Phải có trust boundary cao hơn/độc lập
    -> Không tạo vòng phụ thuộc không thể phá
~~~

**Recovery hierarchy phải được vẽ và kiểm tra dependency**, nếu không có thể rơi vào vòng tròn: cần key A để mở backup B, nhưng cần backup B để khôi phục key A.

## 5. Thiết kế ngưỡng M-of-N

### 5.1. Ba câu hỏi chọn threshold

1. **Bao nhiêu shares/custodians bị mất mà tổ chức vẫn cần phục hồi được?**
2. **Bao nhiêu shares/custodians bị compromise mà tổ chức vẫn muốn secret chưa thể bị tái tạo?**
3. **Có bao nhiêu miền độc lập thật sự?** Người, thiết bị, địa điểm, tổ chức, identity provider và kênh liên lạc.

Ví dụ 3-of-5:

- Có thể chịu **hai shares không sẵn sàng** và vẫn còn ba shares để recovery.
- Theo tính chất threshold lý tưởng, **hai shares bị lộ vẫn chưa đủ** tái tạo secret.
- Nhưng nếu ba shares bị thông đồng/lộ, ngưỡng đã bị đạt.
- Nếu ba shares bị mất cùng lúc, recovery không còn khả thi bằng bộ shares đó.

### 5.2. M/N không tự quyết định độ an toàn

Một cấu hình 3-of-5 có thể yếu nếu:

- Ba shares nằm trong cùng một phòng hoặc cùng một password manager.
- Một admin có quyền lấy cả ba.
- Cả năm custodians dùng chung IdP/thiết bị bị compromise.
- Shares được gửi qua cùng một email hoặc ticket.
- Recovery workflow cho phép một người sửa danh sách custodian và tự approve.

Một cấu hình 2-of-3 phân tán độc lập, có xác thực mạnh, dual control và audit đôi khi có posture tốt hơn một cấu hình 4-of-7 chỉ tồn tại trên giấy.

### 5.3. Availability model (giả định độc lập)

Nếu mỗi custodian có xác suất sẵn sàng **p**, và các sự kiện availability độc lập, xác suất có ít nhất M trong N người sẵn sàng là:

\[
P(\text{quorum})=\sum_{k=M}^{N}\binom{N}{k}p^k(1-p)^{N-k}
\]

Ví dụ với **3-of-5** và mỗi người sẵn sàng 90%, xác suất có quorum theo giả định độc lập là khoảng **99,14%**. Nhưng đây chỉ là mô hình đơn giản; mất điện một site, outage IdP hoặc sự kiện địa chính trị có thể làm nhiều custodian cùng mất khả năng tham gia. **Common-mode failures** làm giả định độc lập sai.

### 5.4. Ma trận trade-off

| Threshold | Điểm mạnh | Rủi ro |
|---|---|---|
| **1-of-N** | Khôi phục dễ, availability cao | Một người bị chiếm đủ quyền |
| **2-of-3** | Có dual control cơ bản, chịu một người vắng | Hai người thông đồng/compromise đủ đạt ngưỡng |
| **3-of-5** | Cân bằng cho nhiều hệ thống nhạy cảm | Phải vận hành năm custodians và quản lý share |
| **4-of-5** | Cần nhiều người hơn để đạt quorum | Chỉ chịu một người mất/vắng |
| **5-of-5** | Tất cả phải tham gia | Dễ bị khóa recovery khi một người mất tích, nghỉ việc hoặc thiết bị hỏng |

Không có ngưỡng chuẩn áp cho mọi key. **Root CA recovery**, **tenant KEK**, **database DEK** và **test environment key** có impact khác nhau; quorum và custody phải theo classification.

## 6. Custodian, role và separation of duties

### 6.1. Các vai trò cần phân biệt

| Vai trò | Trách nhiệm | Quyền không mặc định có |
|---|---|---|
| **Key owner** | Chịu trách nhiệm business purpose, retention, risk và recovery requirement | Tự giữ đủ recovery shares |
| **Recovery custodian** | Giữ một share/token được giao, bảo đảm custody và tham gia ceremony | Tự khôi phục key hoặc phê duyệt mọi hành động |
| **Recovery coordinator** | Mở incident/ticket, kiểm tra điều kiện, điều phối người tham gia | Nhìn raw key/share của người khác |
| **Security officer** | Xác minh threat model, approvals, policy và containment | Tự sửa audit hoặc tự đạt quorum |
| **HSM/KMS operator** | Thực hiện restore/activate/import theo procedure | Đơn phương lấy recovery material |
| **Backup custodian** | Quản lý media/backup blob và chain of custody | Có cả wrapping key và quyền restore |
| **Independent auditor** | Xem evidence, đối soát participants và kết quả | Tự thao tác trên production key |
| **Business approver** | Xác nhận nhu cầu khôi phục dịch vụ/dữ liệu | Thay đổi technical trust policy |

Một người có thể giữ nhiều vai trò ở hệ thống nhỏ, nhưng phải đánh giá **xung đột quyền**. Đối với khóa có blast radius lớn, tách **đề xuất, phê duyệt, thực hiện và kiểm chứng**.

### 6.2. Một custodian không nên kiểm soát toàn bộ đường recovery

Ví dụ phân tách:

~~~text
Custodian A: giữ share 1 (offline sealed envelope)
Custodian B: giữ share 2 (HSM security token)
Custodian C: giữ share 3 (secure vault ở site khác)
Custodian D: giữ share 4 (recovery token riêng)
Custodian E: giữ share 5 (DR location)

Recovery coordinator:
    có thể mở request và xem status
    không thể tự đọc/reconstruct shares

HSM operator:
    có thể chạy restore command
    không thể tự đạt quorum hoặc lấy share của custodian

Auditor:
    quan sát ceremony và đối chiếu evidence
    không tham gia vào key material
~~~

Sơ đồ chỉ là ví dụ. **Một share nằm trong vault nhưng một admin có quyền mở vault, reset MFA và tải file** có thể không độc lập như thiết kế. Cần đánh giá **effective control**, không chỉ đếm số tên người.

### 6.3. Tính độc lập cần có chiều sâu

Quorum nên phân tán trên nhiều trục:

- **Human:** custodians khác nhau, không dùng chung danh tính hoặc delegated account.
- **Organizational:** tránh toàn bộ share thuộc một quản lý hoặc một nhóm có thể bị ép buộc đồng thời.
- **Physical:** tách site, vault, thiết bị và backup media.
- **Logical:** tách IdP, admin domain, MFA factor, role và approval workflow khi hợp lý.
- **Temporal:** không cho một người thu thập các shares lần lượt qua một quy trình không có giám sát.
- **Operational:** không cho cùng một pipeline/automation có quyền truy cập tất cả share stores.

**Độc lập tuyệt đối rất khó**; ví dụ nhiều hệ thống có cùng cloud identity provider hoặc cùng mạng quản trị. Hãy ghi rõ dependency chung và kiểm thử tình huống mất chính dependency đó.

## 7. Quản lý shares và recovery material

### 7.1. Một share là một tài sản nhạy cảm

Mỗi share cần được quản lý như một **secret có vòng đời**:

| Thuộc tính | Cần ghi nhận |
|---|---|
| **Share set ID** | Bộ shares thuộc cùng một lần tạo/recovery secret |
| **Share index** | Định danh duy nhất trong bộ, tránh trùng/lặp |
| **Threshold/total** | M và N theo policy được phê duyệt |
| **Target key identity** | Key ID/version, purpose và HSM/KMS domain |
| **Algorithm/format** | Scheme/version, encoding, parameters theo implementation |
| **Custodian identity** | Ai chịu trách nhiệm giữ share |
| **Creation/rotation time** | Khi tạo, thay set hoặc đổi custodian |
| **Integrity/authenticity** | Cách xác minh share không bị thay thế/sửa |
| **Storage/custody location** | Vault/device/site và access controls |
| **Status** | Active, sealed, transferred, revoked, destroyed, suspected exposed |

Không đưa **share bytes, PIN, activation secret hoặc recovery password** vào key inventory/log thông thường. Inventory lưu metadata và custody evidence; share material nằm trong storage được phê duyệt.

### 7.2. Bảo vệ share khi lưu

- **Mã hóa at rest** bằng cơ chế phù hợp, key bảo vệ độc lập với share set đang được backup.
- Dùng **tamper-evident packaging/seals** cho media vật lý nếu quy trình yêu cầu.
- Cất ở **vault hoặc thiết bị riêng**, có access log và người quản lý.
- Tách share với **share set metadata, recovery procedure và target system details** khi cần giảm khả năng attacker ghép đủ thông tin.
- Kiểm kê định kỳ, xác minh **custodian vẫn còn đủ điều kiện** và media chưa bị thay.
- Không chụp ảnh/scan hoặc đưa vào email/chat/ticket để “dự phòng”.
- Có quy trình **transfer custody** khi nhân sự nghỉ việc, chuyển vai trò hoặc thiết bị bị mất.

### 7.3. Bảo vệ share khi truyền và sử dụng

Nếu share được chuyển tới recovery boundary:

- Dùng **kênh xác thực và mã hóa**, endpoint đã được xác minh.
- Tránh tạo file tạm không kiểm soát, clipboard, shell history, debug dump và crash dump.
- Kiểm tra **share set ID, index, threshold, keyRef/version và integrity** trước khi kết hợp.
- Chỉ đưa share vào **approved HSM/recovery tool**; ưu tiên scheme cho phép reconstruction trong HSM hoặc secure boundary.
- Hạn chế thời gian share/secret tồn tại trong memory và xóa bản tạm theo khả năng của nền tảng.
- Audit **ai tham gia, hành động nào, thời điểm và kết quả**, không audit nội dung bí mật.

### 7.4. Share rotation và custodian replacement

Khi một custodian rời tổ chức:

1. Xác minh share của người đó đang ở đâu, trạng thái seal/device và có dấu hiệu exposure không.
2. **Không chỉ sửa tên custodian trong inventory** rồi tiếp tục coi share cũ đã an toàn.
3. Theo implementation, có thể tạo lại **share set mới** từ secret/key hoặc dùng protocol **resharing** được hỗ trợ.
4. Thu hồi credential/token/vault access cũ; thu hồi hoặc tiêu hủy share cũ theo quy trình.
5. Kiểm thử threshold recovery bằng bộ shares mới; đối soát key identity/version.
6. Cập nhật custody record, approvals và audit.

**Thay một share không nhất thiết giống thay một custodian**. Với Shamir thông thường, đổi bộ custodians có thể yêu cầu **re-sharing/re-generation**; với threshold cryptography, resharing là một protocol riêng và phải tương thích implementation.

### 7.5. Share bị mất, nghi lộ hoặc hỏng

| Sự kiện | Hành động |
|---|---|
| **Một share mất** nhưng còn ít nhất M shares an toàn | Đánh giá exposure, tạo share set/custody mới, loại bỏ bộ cũ theo policy |
| **Share nghi bị lộ** nhưng chưa đủ threshold | Không tự coi secret đã an toàn tuyệt đối; điều tra, rotate/reshare sớm theo risk |
| **M shares có thể đã bị lộ** | Xem secret/key compromise; cô lập và thay material, đánh giá dữ liệu phụ thuộc |
| **Share hỏng/không đọc được** | Dùng share dự phòng hợp lệ nếu policy có; không tự giảm threshold |
| **Share set metadata mất** | Dùng backup inventory/ceremony records đáng tin; không đoán index/version |
| **Custodian không còn liên lạc** | Kích hoạt succession/continuity policy; không giả danh hoặc bypass quorum |

**Không hạ M chỉ vì thiếu người** trong lúc sự cố. Thay đổi threshold là một security policy change cần approval riêng, impact assessment và có thể phải tạo lại share set.

## 8. Recovery ceremony: Quy trình khôi phục có kiểm soát

### 8.1. Trước ceremony: Xác minh yêu cầu

Recovery coordinator mở request với:

- **Incident/change ticket** và lý do: DR, HSM failure, key migration, lost material hoặc test định kỳ.
- **Target key identity:** key ID/version, purpose, algorithm, provider/partition, tenant/environment.
- **Recovery scope:** restore key object, reconstruct backup wrapping key, restore CA signing domain hay mở data archive.
- **Business owner/impact:** dịch vụ nào phụ thuộc, RTO/RPO, dữ liệu có legal hold không.
- **Expected M/N:** ngưỡng và danh sách custodian được phê duyệt.
- **Approved environment:** HSM/DR site, firmware/provider compatibility và secure workstation.
- **Recovery authority:** ai approve, ai operate, ai witness/audit.

Không cho phép request chung chung như **“khôi phục tất cả key production”** mà không có scope và key inventory.

### 8.2. Trong ceremony

~~~mermaid
sequenceDiagram
    participant CO as Recovery Coordinator
    participant A as Custodian A
    participant B as Custodian B
    participant C as Custodian C
    participant OP as HSM/KMS Operator
    participant AU as Independent Auditor
    CO->>AU: Mở ceremony, incident ID, target keyRef
    CO->>A: Xác thực identity + custody share
    CO->>B: Xác thực identity + custody share
    CO->>C: Xác thực identity + custody share
    A-->>OP: Approve/submit share 1 qua secure interface
    B-->>OP: Approve/submit share 2 qua secure interface
    C-->>OP: Approve/submit share 3 qua secure interface
    OP->>OP: Verify M-of-N, share set, target, policy
    OP->>OP: Restore/reconstruct trong approved boundary
    OP-->>CO: Kết quả, key identity/version, status
    AU->>AU: Đối soát approvals, audit và evidence
~~~

Các bước kiểm soát:

1. **Hai người xác minh target key** từ ticket/inventory và provider console độc lập.
2. **Xác thực từng custodian** bằng identity riêng, MFA/hardware token và custody check.
3. Xác minh **share set/version/index**; từ chối share trùng, share sai bộ hoặc share đã revoked.
4. Đạt threshold M theo **policy hiện hành**, không chấp nhận approval từ người không thuộc danh sách.
5. Thực hiện restore/reconstruct bằng **tool/provider được phê duyệt**, trong secure boundary.
6. Kiểm tra key attributes: **key ID/version, algorithm, usage, exportability, state, policy và owner**.
7. Chỉ mở quyền cần thiết, ưu tiên **temporary grant** và time-bound recovery role.
8. Ghi audit outcome và cleanup material tạm theo khả năng.

### 8.3. Sau ceremony: Xác minh key và dữ liệu

Không kết thúc chỉ vì lệnh restore trả success. Cần:

- So **key fingerprint/identifier hoặc provider object identity** với backup/manifest được phê duyệt, nếu scheme hỗ trợ kiểm tra.
- Kiểm tra **algorithm, key usage, policy, exportability, state và tenant scope**.
- Dùng **test vector/synthetic ciphertext** đã chuẩn bị để xác nhận Encrypt/Decrypt hoặc Sign/Verify đúng purpose.
- Khôi phục một mẫu **wrapped DEK + ciphertext + AAD** để kiểm tra end-to-end data recovery.
- Kiểm tra **KMS/HSM audit, IAM grants, key versions và replication**.
- Gỡ temporary permissions, đóng session, thu hồi activation credentials theo policy.
- Niêm phong lại share/media, xác nhận custody và lập post-ceremony report.

**Không Sign một tài liệu production hoặc Decrypt dữ liệu khách hàng thật chỉ để chứng minh HSM đã khôi phục** nếu có test material tương đương. Recovery validation phải có scope và dữ liệu được phê duyệt.

### 8.4. Nếu ceremony thất bại

Nếu không đủ M custodian, share không khớp hoặc HSM từ chối:

1. Dừng quy trình; **không hạ threshold** hoặc dùng share của người khác.
2. Giữ evidence và audit, không để lộ share material.
3. Phân loại lỗi: identity, custody, share set/version, device/firmware, HSM partition, policy, backup corruption hoặc dependency.
4. Mở incident/continuity path đúng thẩm quyền.
5. Dùng alternate recovery site hoặc share dự phòng **chỉ khi đã được policy phê duyệt và kiểm tra integrity**.
6. Ghi rõ RTO bị ảnh hưởng và quyết định risk acceptance/escalation.

## 9. KMS/HSM: Quorum và backup/restore phụ thuộc provider

### 9.1. Không phải mọi KMS đều cho khách hàng export key

| Kiểu dịch vụ | Cách recovery có thể hoạt động | Điều phải xác minh |
|---|---|---|
| **Provider-managed KMS key** | Provider chịu trách nhiệm durability/replication; customer có thể không export key material | Service recovery SLA, region/account controls, deletion behavior, key access policy |
| **Customer-managed HSM key** | Backup/restore key object qua HSM-native backup hoặc secure replication | Backup format, M-of-N controls, firmware/partition compatibility |
| **BYOK/imported key** | Customer bảo vệ source material và quy trình import/backup | Import wrapping key, exportability, key origin, backup lifecycle |
| **On-prem HSM cluster** | Replicate/restore secure objects giữa partitions/devices | Quorum cards, security domain, backup key, quorum policy |
| **Software keystore** | Backup encrypted keystore và secret/password bảo vệ | Password custody, file integrity, access logs, copies in CI/DR |

**Một KMS có automatic durability không nhất thiết hỗ trợ Shamir shares do customer quản lý.** Một HSM có M-of-N security officer cards không nhất thiết cho phép customer tự split raw private key. Cần phân biệt **provider service availability**, **key material backup**, **key object restore** và **customer approval quorum**.

### 9.2. Các lớp quorum có thể cùng tồn tại

Một recovery flow có thể có nhiều lớp:

1. **Business approval quorum:** M người duyệt nhu cầu recovery.
2. **HSM security officer quorum:** M token/operator credentials kích hoạt domain/backup restore.
3. **Cryptographic recovery shares:** M shares tái tạo recovery wrapping secret.
4. **IAM approval:** quyền tạm thời để operator gọi API restore.

Không được cộng gộp thành **“đã đủ 3-of-5”** nếu ba điều kiện khác nhau. Cần ghi riêng mỗi ngưỡng, người tham gia và evidence.

### 9.3. Restore backup blob không phải reconstruct key

Một HSM backup blob có thể được **mã hóa bằng backup wrapping key và gắn với security domain**. Restore có thể yêu cầu:

- HSM tương thích và đã được initialize đúng.
- Backup wrapping key/secret và quorum authorization.
- Cùng hoặc tương thích firmware, partition, security domain.
- Quyền restore và kiểm tra integrity.

Trong mô hình này, **raw key có thể không rời HSM**. Quorum mở quyền restore, còn thiết bị thực hiện import/restore object. Đừng mô tả mọi HSM backup như việc thu thập M mảnh private key rồi ghép trong laptop.

### 9.4. Provider questions trước khi thiết kế

- Quorum áp dụng cho **backup, restore, key generation, activation, policy change hay key use**?
- M/N do customer cấu hình hay provider cố định?
- Custodian có phải **security officer** hay có thể là workload principal?
- Shares/tokens được tạo và phân phối bằng quy trình nào? Có integrity/versioning không?
- Backup có thể restore sang **region/site/HSM khác** không?
- Key ID/material version sau restore có giữ nguyên không?
- Provider hỗ trợ **non-exportable restore** và audit evidence gì?
- Nếu một custodian mất token/share, có succession/resharing procedure nào?
- Disable/destroy key có ảnh hưởng backup/replica như thế nào?
- Provider có giới hạn số lần thử, lockout, recovery window hoặc dual-control semantics không?

## 10. Quorum cho từng loại khóa

### 10.1. Root KEK / recovery wrapping key

Đây thường là tài sản có blast radius cao. Quorum có thể bảo vệ **recovery root** hoặc quyền restore HSM backup. Cần:

- Custody offline hoặc HSM-native backup.
- Phân tán địa lý/tổ chức và dual control.
- Recovery root không nằm cùng storage/identity domain với ciphertext/backup được bảo vệ.
- Test restore từ DR site và xác minh đúng key fingerprint/object.
- Quy trình rotation/resharing khi custodian rời tổ chức.

### 10.2. Tenant KEK

Nếu mỗi tenant có KEK riêng, recovery nên giới hạn **đúng tenant, đúng key version**. Không dùng một quorum có quyền tự động mở mọi tenant nếu business requirement không cần. Tách:

- Quyền **restore KEK object**.
- Quyền **Unwrap EDK** cho application.
- Quyền **đọc plaintext record** của user/service.

Một custodian được phép tham gia khôi phục KEK không mặc nhiên có quyền xem dữ liệu tenant.

### 10.3. DEK

Trong envelope encryption, DEK thường được tạo theo object/record/batch và được Wrap bởi KEK. Recovery thường **khôi phục KEK hoặc KMS/HSM access** để mở EDK, không nhất thiết backup từng plaintext DEK riêng lẻ.

Nếu DEK cần escrow/backup riêng, phải xem xét blast radius, number of wrapped copies và khả năng re-encrypt. Không đưa hàng loạt plaintext DEKs vào một archive chỉ để đơn giản hóa recovery.

### 10.4. Private signing key

Recovery private signing key có thể giúp duy trì signing service, nhưng **cũng khôi phục khả năng tạo chữ ký mới dưới identity cũ**. Do đó:

- Quorum restore phải có **business approval và key-purpose restriction**.
- Kiểm tra key/certificate còn đáng tin, chưa compromised/revoked.
- Nếu key bị compromise, thường cần **keypair/certificate mới**, không restore lại material bị lộ để tiếp tục Sign.
- Public key/certificate chain và timestamp evidence có thể được backup riêng cho historical Verify; không cần private key chỉ để Verify.

### 10.5. CA root/intermediate key

CA private key có thể cấp chứng thư và/hoặc ký CRL theo profile. Recovery phải có **PKI governance, ceremony và HSM quorum** nghiêm ngặt:

- Kiểm tra CA identity, policy, serial database, audit và issuance state.
- Không cho một người tự restore rồi phát hành certificate.
- Kiểm soát key usage **keyCertSign/cRLSign** và CA constraints.
- Test chain, CRL/OCSP signer và disaster recovery theo CA policy.
- Nếu CA key đã compromise, **không restore để tiếp tục dùng**; cần distrust/rollover hierarchy.

### 10.6. HMAC/shared secret

HMAC secret thường được chia sẻ giữa nhiều bên. Recovery có thể làm tăng số bên biết secret, kéo theo nguy cơ impersonation. Cân nhắc:

- Tạo secret mới và phối hợp phân phối tới partners.
- Giới hạn secret theo partner/protocol/tenant.
- Quorum phê duyệt export/restore, không gửi raw secret qua kênh chung.
- Anti-replay, grace period, key ID/version và revoke secret cũ.

## 11. Quorum không tự chữa được key compromise

Một backup/secret share có thể giúp khôi phục khả năng vận hành, nhưng nếu material đã bị lộ:

- **Khôi phục lại cùng key bytes** không loại bỏ bản sao attacker đang giữ.
- **Reconstruct secret từ M shares** không tự chứng minh secret chưa bị sao chép trước đó.
- **HSM non-exportable** không ngăn attacker dùng quyền Sign/Decrypt nếu principal bị compromise.
- **Quorum approval** có thể bị bypass nếu một admin có direct API access ngoài workflow.

Phải phân biệt:

| Sự cố | Hướng phản ứng |
|---|---|
| **Mất HSM/thiết bị**, key chưa compromise | Restore theo quorum, xác minh key identity và integrity |
| **Mất một share**, còn đủ shares an toàn | Khôi phục/reshare theo policy, điều tra custody |
| **Nghi share lộ**, chưa đạt threshold | Cô lập, điều tra, tạo share set mới/rotate secret theo risk |
| **Đủ M shares bị lộ** | Xem recovery secret/key có thể compromise; thay material và đánh giá dữ liệu |
| **Private key đã bị export/copy** | Không restore để tiếp tục tin; rotate keypair/certificate hoặc data keys |
| **Chỉ operator credential bị chiếm** | Revoke identity/sessions/grants, audit operations và đánh giá key use |

**Recovery và incident response có thể cần chạy song song**: một luồng giữ khả năng khôi phục dịch vụ, luồng khác xác định có cần thay key material hay không. Không vì DR khẩn cấp mà bỏ qua quyết định trust.

## 12. Java 17: Mô phỏng quorum approval 3-of-5

Ví dụ sau mô phỏng **quorum authorization** trước khi operator được phép chạy một recovery action. Nó kiểm tra:

- Có incident/request hợp lệ và target key đúng scope.
- Có ít nhất **M custodians khác nhau** trong N custodian được phép.
- Mỗi approval gắn đúng **keyRef và action**.
- Custodian còn active, có role **RECOVERY_CUSTODIAN**, xác thực và MFA thành công.
- Approval còn hạn, đã đồng ý rõ ràng và thuộc đúng request.
- **Separation of duties:** requester/operator không tự tính vào quorum.
- Nếu policy yêu cầu, các custodian phải đến từ **domain/site độc lập**.

**Đây không phải Shamir Secret Sharing, không chứa key bytes, không ghép share và không gọi KMS/HSM.** Các cờ authenticated/MFA/incidentValidated trong demo chỉ là dữ liệu giả lập. Production cần approval có chữ ký/identity đáng tin, workflow chống sửa, provider enforcement và audit bền vững.

~~~java
import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class QuorumApprovalDemo {

    enum Role {
        RECOVERY_CUSTODIAN,
        KEY_OWNER,
        HSM_OPERATOR,
        SECURITY_APPROVER,
        AUDITOR
    }

    enum Action {
        RESTORE_HSM_BACKUP,
        RESTORE_KEY_OBJECT,
        RECONSTRUCT_RECOVERY_SECRET
    }

    record Custodian(
            String id,
            String independentDomain,
            boolean active,
            Set<Role> roles) {
        Custodian {
            if (id == null || id.isBlank()
                    || independentDomain == null
                    || independentDomain.isBlank()) {
                throw new IllegalArgumentException(
                        "Invalid custodian identity");
            }
            roles = Set.copyOf(Objects.requireNonNull(roles));
        }
    }

    record RecoveryPolicy(
            int threshold,
            int totalCustodians,
            String targetKeyRef,
            Action action,
            boolean requireDistinctDomains,
            Map<String, Custodian> custodians) {
        RecoveryPolicy {
            if (threshold < 1 || totalCustodians < threshold
                    || custodians == null
                    || custodians.size() != totalCustodians) {
                throw new IllegalArgumentException(
                        "Invalid M-of-N policy");
            }
            Objects.requireNonNull(targetKeyRef);
            Objects.requireNonNull(action);
            custodians = Map.copyOf(custodians);
        }
    }

    record RecoveryRequest(
            String incidentId,
            String requesterId,
            String executorId,
            String targetKeyRef,
            Action action,
            boolean incidentValidated,
            boolean scopeApproved) {
        RecoveryRequest {
            Objects.requireNonNull(incidentId);
            Objects.requireNonNull(requesterId);
            Objects.requireNonNull(executorId);
            Objects.requireNonNull(targetKeyRef);
            Objects.requireNonNull(action);
        }
    }

    // Approval metadata only; this is NOT a Shamir share.
    record Approval(
            String approvalId,
            String custodianId,
            String targetKeyRef,
            Action action,
            boolean authenticated,
            boolean mfaVerified,
            boolean approved,
            Instant expiresAt) {
        Approval {
            Objects.requireNonNull(approvalId);
            Objects.requireNonNull(custodianId);
            Objects.requireNonNull(targetKeyRef);
            Objects.requireNonNull(action);
            Objects.requireNonNull(expiresAt);
        }
    }

    record Decision(
            boolean allowed,
            int validApprovals,
            String reason) {}

    static Decision evaluate(
            RecoveryPolicy policy,
            RecoveryRequest request,
            List<Approval> approvals,
            Instant now) {

        Objects.requireNonNull(policy);
        Objects.requireNonNull(request);
        Objects.requireNonNull(approvals);
        Objects.requireNonNull(now);

        if (request.incidentId().isBlank()
                || !request.incidentValidated()
                || !request.scopeApproved()) {
            return new Decision(false, 0, "REQUEST_NOT_APPROVED");
        }
        if (!policy.targetKeyRef().equals(request.targetKeyRef())
                || policy.action() != request.action()) {
            return new Decision(false, 0, "TARGET_OR_ACTION_MISMATCH");
        }
        if (request.requesterId().equals(request.executorId())) {
            return new Decision(false, 0, "REQUESTER_CANNOT_EXECUTE");
        }

        Set<String> seenCustodians = new HashSet<>();
        Set<String> seenDomains = new HashSet<>();
        Set<String> seenApprovalIds = new HashSet<>();

        for (Approval approval : approvals) {
            if (approval == null
                    || approval.approvalId().isBlank()
                    || !seenApprovalIds.add(approval.approvalId())) {
                return new Decision(false, 0, "INVALID_OR_DUPLICATE_APPROVAL");
            }
            if (!seenCustodians.add(approval.custodianId())) {
                return new Decision(false, 0, "DUPLICATE_CUSTODIAN");
            }
            if (approval.custodianId().equals(request.requesterId())
                    || approval.custodianId().equals(request.executorId())) {
                return new Decision(false, 0, "SEPARATION_OF_DUTIES_VIOLATION");
            }

            Custodian custodian =
                    policy.custodians().get(approval.custodianId());
            if (custodian == null || !custodian.active()
                    || !custodian.roles().contains(
                            Role.RECOVERY_CUSTODIAN)) {
                return new Decision(false, 0, "CUSTODIAN_NOT_AUTHORIZED");
            }
            if (!approval.authenticated() || !approval.mfaVerified()
                    || !approval.approved()
                    || !now.isBefore(approval.expiresAt())) {
                return new Decision(false, 0, "APPROVAL_NOT_VALID");
            }
            if (!policy.targetKeyRef().equals(
                        approval.targetKeyRef())
                    || policy.action() != approval.action()) {
                return new Decision(false, 0, "APPROVAL_SCOPE_MISMATCH");
            }
            if (policy.requireDistinctDomains()
                    && !seenDomains.add(
                            custodian.independentDomain())) {
                return new Decision(false, 0, "DOMAIN_NOT_INDEPENDENT");
            }
        }

        if (approvals.size() < policy.threshold()) {
            return new Decision(
                    false, approvals.size(), "QUORUM_NOT_REACHED");
        }
        return new Decision(
                true, approvals.size(), "QUORUM_APPROVED");
    }

    private static Approval approval(
            String id, String keyRef, Action action, Instant expiry) {
        return new Approval(
                "approval-" + id,
                id,
                keyRef,
                action,
                true,  // Demo only: authenticated identity
                true,  // Demo only: MFA verified
                true,  // Demo only: explicitly approved
                expiry);
    }

    private static void print(
            String label, Decision decision) {
        System.out.println(label + ": "
                + decision.allowed() + " / "
                + decision.validApprovals() + " / "
                + decision.reason());
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-28T00:00:00Z");
        Instant expiry = now.plusSeconds(900);
        String keyRef = "production-recovery-root/v4";
        Action action = Action.RESTORE_HSM_BACKUP;

        Map<String, Custodian> custodians = Map.of(
                "A", new Custodian("A", "site-north", true,
                        Set.of(Role.RECOVERY_CUSTODIAN)),
                "B", new Custodian("B", "site-central", true,
                        Set.of(Role.RECOVERY_CUSTODIAN)),
                "C", new Custodian("C", "site-south", true,
                        Set.of(Role.RECOVERY_CUSTODIAN)),
                "D", new Custodian("D", "offline-vault", true,
                        Set.of(Role.RECOVERY_CUSTODIAN)),
                "E", new Custodian("E", "dr-site", true,
                        Set.of(Role.RECOVERY_CUSTODIAN)));

        RecoveryPolicy policy = new RecoveryPolicy(
                3, 5, keyRef, action, true, custodians);
        RecoveryRequest request = new RecoveryRequest(
                "INC-2026-0042",
                "coordinator",
                "hsm-operator",
                keyRef,
                action,
                true,
                true);

        Approval a = approval("A", keyRef, action, expiry);
        Approval b = approval("B", keyRef, action, expiry);
        Approval c = approval("C", keyRef, action, expiry);
        Approval d = approval("D", keyRef, action, expiry);

        print("Two approvals",
                evaluate(policy, request, List.of(a, b), now));
        print("Three independent approvals",
                evaluate(policy, request, List.of(a, b, c), now));
        print("Duplicate custodian",
                evaluate(policy, request,
                        List.of(a, b, approval("A", keyRef, action, expiry)),
                        now));
        print("Wrong target key",
                evaluate(policy, request,
                        List.of(a, b, approval(
                                "C", "other-key/v1", action, expiry)),
                        now));
        print("Expired approval",
                evaluate(policy, request,
                        List.of(a, b, approval(
                                "C", keyRef, action, now)),
                        now));
        print("Requester attempts to approve",
                evaluate(policy, request,
                        List.of(a, b, approval(
                                "coordinator", keyRef, action, expiry)),
                        now));
        print("Four approvals",
                evaluate(policy, request,
                        List.of(a, b, c, d), now));
    }
}
~~~

Lưu thành **QuorumApprovalDemo.java** và chạy với **JDK 17+**:

~~~bash
javac QuorumApprovalDemo.java
java QuorumApprovalDemo
~~~

Kết quả logic dự kiến:

~~~text
Two approvals: false / 2 / QUORUM_NOT_REACHED
Three independent approvals: true / 3 / QUORUM_APPROVED
Duplicate custodian: false / 0 / DUPLICATE_CUSTODIAN
Wrong target key: false / 0 / APPROVAL_SCOPE_MISMATCH
Expired approval: false / 0 / APPROVAL_NOT_VALID
Requester attempts to approve: false / 0 / SEPARATION_OF_DUTIES_VIOLATION
Four approvals: true / 4 / QUORUM_APPROVED
~~~

### 12.1. Điều gì được kiểm tra?

| Điều kiện | Lý do |
|---|---|
| 3 distinct custodians | Không đếm một người nhiều lần |
| Mỗi custodian active và đúng role | Không nhận approval từ người đã offboard |
| MFA và authenticated identity | Giảm nguy cơ giả mạo approval |
| KeyRef/action match | Không dùng approvals của key này cho key khác |
| Expiry | Không tái sử dụng approval cũ |
| Domain diversity | Tránh tất cả approvers cùng một failure domain |
| Requester/operator tách biệt | Separation of duties |
| Incident/scope approved | Không phục hồi key không có mục đích rõ |

### 12.2. Giới hạn của demo

1. **Không có chữ ký số cho approval**: production phải xác minh approval từ IdP/workflow đáng tin, chống sửa/replay.
2. **Không có Shamir shares**: code chỉ đếm approvals, không tạo/ghép bí mật.
3. **Không có KMS/HSM**: không thực hiện restore hay reconstruct key.
4. **MFA là boolean giả lập**: không thay authenticator/hardware-backed identity.
5. **Domain là chuỗi cấu hình**: production phải xác minh independence thực tế, không nhận domain từ người gửi.
6. **Không có audit persistence**: production ghi event bất biến và correlation ID.
7. **Không có distributed locking/transaction**: concurrent approvals cần workflow state machine và chống double execution.
8. **Không có policy versioning**: production cần ghi policy revision/effective time, không cho downgrade.
9. **Không có emergency succession**: quy trình custodian mất tích/offboard cần được thiết kế riêng.
10. **Không kiểm tra share integrity**: nếu dùng SSS/HSM tokens, phải xác minh share set/index/authenticity theo implementation.

**Điểm học được:** Quorum approval chỉ chứng minh đủ người hợp lệ đồng ý cho **một recovery action cụ thể**. Nó không chứng minh secret được chia bằng Shamir, key đã được phục hồi đúng hoặc dữ liệu đã khôi phục thành công.

## 13. Threat model: Quorum có thể thất bại như thế nào?

### 13.1. Threats với confidentiality

| Nguy cơ | Tác động | Kiểm soát |
|---|---|---|
| **M custodians thông đồng** | Đạt threshold và khôi phục secret ngoài mục đích | Custodian independence, audit, alert, time-bound recovery |
| **Một admin kiểm soát nhiều share stores** | Quorum danh nghĩa nhưng thực tế một người đủ quyền | Effective-control review, tách IAM/vault/site |
| **Share bị copy từ clipboard/log/crash dump** | Secret material xuất hiện ngoài custody | Secure interface, dump controls, no raw secret logging |
| **Backup wrapping key và shares cùng bị lấy** | Attacker có thể mở backup material | Independent hierarchy, offline custody, quorum khác |
| **Recovery workstation bị compromise** | Share/secret có thể bị lấy trong ceremony | Dedicated hardened host, attestation, isolation, rebuild |
| **Share gửi qua email/chat/ticket** | Nhiều bản sao khó thu hồi | Prohibit plaintext transfer, approved channel |
| **Custodian bị phishing/coercion** | Approval/share bị sử dụng trái phép | Hardware MFA, verification callback, two-person witness |
| **Fake recovery request** | Custodian bị lừa tham gia recovery ngoài mục tiêu | Incident ticket validation, out-of-band approval |
| **Share set substitution** | Shares của key/version khác bị trộn | Set ID, target keyRef, integrity/version checks |
| **Replay approval cũ** | Lặp lại recovery không được phép | Request nonce, expiry, one-time approval, signed audit |

### 13.2. Threats với availability

| Nguy cơ | Tác động | Kiểm soát |
|---|---|---|
| **M shares bị mất/hỏng** | Không đạt threshold, key không thể phục hồi | Redundant custody, inventory, tested spare/resharing |
| **N-M+1 custodians không sẵn sàng** | Số người còn lại dưới M | Succession plan, geographic distribution, on-call roster |
| **Một site outage làm mất nhiều shares** | Common-mode failure | Phân tán địa lý và dependency |
| **HSM firmware không tương thích backup** | Restore thất bại | Compatibility matrix, vendor-supported upgrade path |
| **Recovery root mất cùng production site** | Không mở được backup ở DR | Independent root custody và DR location |
| **Quorum quá cao** | Không kịp RTO | Availability modeling và ceremony drills |
| **Threshold bị hạ sai lúc sự cố** | Security suy yếu để đổi availability | Separate policy change approval; không bypass |
| **Custodian offboarding không chuyển giao** | Mất share hoặc mất quyền tham gia | Succession/custody transfer trước ngày rời |

### 13.3. Threats với integrity và accountability

- **Wrong key restored:** backup của key test được import thành key production hoặc ngược lại.
- **Old backup rollback:** restore một phiên bản policy/key cũ có quyền rộng hơn.
- **Share index collision:** cùng một index bị tính hai lần hoặc shares từ bộ khác bị ghép.
- **Policy downgrade:** threshold M bị hạ hoặc danh sách custodian bị sửa ngay trong recovery.
- **Unapproved key export:** recovery biến thành export raw key không nằm trong scope.
- **Audit deletion:** operator vừa thực hiện restore vừa có quyền xóa evidence.
- **Concurrent ceremony:** hai workflow cùng restore hoặc rotate key, dẫn tới trạng thái không nhất quán.

Kiểm soát:

1. **Immutable key identity/version** và backup manifest có integrity/authenticity.
2. **Policy revision** được phê duyệt và không thể bị request tự thay đổi.
3. Kiểm tra **share set ID/index/threshold** trước khi combine.
4. Tách **recovery authorization** khỏi **export permission**.
5. Ghi audit ra hệ thống độc lập hoặc tamper-evident store.
6. Dùng **one-time ceremony ID, locking và idempotency** để chống replay/concurrency.
7. Xác minh **key fingerprint/provider object metadata** sau restore.

### 13.4. Insider collusion và common-mode failure

Một sơ đồ 3-of-5 có thể bị phá nếu:

~~~text
Custodian A, B, C đều thuộc cùng một nhóm admin
Tất cả shares ở cùng một vault
Một global administrator có thể reset identity/MFA của cả ba
Một pipeline CI đọc được mọi share file

=> N=5 trên giấy, nhưng failure domain thực tế có thể chỉ là 1.
~~~

Review quorum phải trả lời: **ai có thể thực sự lấy được share, reset quyền của custodian, thay đổi policy, hoặc can thiệp thiết bị**? Phân tán số người nhưng giữ chung root admin credential không tạo independence thật.

## 14. Disaster recovery: Kết nối quorum với RTO/RPO

### 14.1. Recovery objective

- **RTO (Recovery Time Objective):** thời gian tối đa mục tiêu để khôi phục dịch vụ.
- **RPO (Recovery Point Objective):** mức dữ liệu/thời điểm có thể chấp nhận mất khi phục hồi.

Quorum có thể là một phần lớn của RTO: phải tìm đủ custodians, xác thực, mở vault, restore HSM và verify key. Nếu yêu cầu dịch vụ trở lại trong 30 phút nhưng custodian cần bay tới site khác trong 6 giờ, thiết kế không đáp ứng RTO.

### 14.2. Ước lượng recovery time

~~~text
T_recovery =
    T_detect + T_decision
  + T_contact_custodians
  + T_quorum_approval
  + T_access_backup_media
  + T_HSM_restore
  + T_key_validation
  + T_data_restore
  + T_service_reconnect
~~~

Các bước có thể chạy song song, nhưng phải xác định **critical path**. Đừng chỉ đo thời gian lệnh HSM restore; thời gian tìm đủ người và khôi phục trust/IAM cũng thuộc RTO.

### 14.3. Dependency graph của một recovery

~~~mermaid
flowchart TD
    A["Encrypted database backup"] --> B["Envelope metadata + EDK"]
    B --> C["Tenant KEK / key object"]
    C --> D["KMS/HSM key backup"]
    D --> E["Backup wrapping key / recovery root"]
    E --> F["M-of-N custody + quorum"]
    F --> G["HSM restore / recovery"]
    G --> H["IAM, policies, key versions"]
    H --> I["Decrypt/verify sample data"]
    I --> J["Restore application service"]
    K["Schema + AAD + format metadata"] --> I
    L["Trusted identity + resource authorization"] --> J
~~~

Nếu một dependency thiếu, **key restore có thể thành công nhưng data recovery vẫn thất bại**. Ví dụ key object đã được restore nhưng database backup thiếu EDK hoặc AAD schema.

### 14.4. Recovery runbook theo giai đoạn

**Trước sự cố**

- Xác định critical keys, key owners, purpose, version và dependency graph.
- Định nghĩa M/N cho từng loại recovery, không áp một quorum chung cho mọi key.
- Tạo backup theo provider-supported mechanism và bảo vệ backup wrapping key độc lập.
- Phân phối shares/tokens tới custodians; kiểm tra custody và succession.
- Xác định DR sites, HSM compatibility, RTO/RPO, identity dependencies.
- Diễn tập ceremony và end-to-end data restore với dữ liệu synthetic.

**Trong sự cố**

- Xác minh incident, scope, target keyRef/version và mức độ compromise.
- Cô lập production/backup credentials bị ảnh hưởng.
- Gọi đúng custodians và đạt quorum theo policy đang có hiệu lực.
- Restore đúng backup object trong HSM/secure environment.
- Verify key identity, usage, exportability, policy và state.
- Restore data/EDK/AAD/schema; test Decrypt/Verify bằng quyền đúng.
- Mở temporary grants và khôi phục service theo từng bước.

**Sau sự cố**

- Thu hồi temporary permissions, close sessions và niêm phong lại shares.
- Kiểm tra audit, backup copies, old shares và key material exposure.
- Nếu có dấu hiệu compromise, rotate/replace key và re-encrypt/re-sign theo risk.
- Đối soát RTO/RPO, dữ liệu thiếu, dependency chưa khôi phục.
- Tạo post-incident report và action items cho quorum/custody.

### 14.5. Recovery và key rotation sau khôi phục

Sau DR, không mặc định restored key tiếp tục là **active write key**. Cần quyết định:

- Giữ restored version để **historical decrypt/verify** hay active cho new use?
- Có bằng chứng backup/DR environment đã bị attacker truy cập không?
- Có cần **rotate recovery root, backup wrapping key hoặc share set** sau ceremony?
- Có key material nào đã được import vào boundary kém tin cậy hơn?
- Có phải cập nhật KMS aliases, IAM policies, key registry và consumer caches?

Nếu key bị lộ trong sự cố, **restore nguyên material cũ để tiếp tục dùng** có thể tái tạo compromise. Recovery success và security recovery là hai quyết định khác nhau.

## 15. Kiểm thử quorum và recovery

### 15.1. Quorum authorization tests

| Test case | Kỳ vọng | Điều cần chứng minh |
|---|---|---|
| M-1 custodians hợp lệ | **DENY** | Không đạt threshold |
| M custodians độc lập hợp lệ | **ALLOW** | Đạt quorum |
| Một custodian gửi approval hai lần | **DENY/không tăng count** | Unique identity |
| Approver không thuộc roster | **DENY** | Custodian authorization |
| Custodian đã offboard | **DENY** | Lifecycle identity |
| MFA thất bại | **DENY** | Authentication strength |
| Approval hết hạn | **DENY** | Freshness |
| Approval cho key A dùng để restore key B | **DENY** | Scope binding |
| Approval cho RESTORE dùng cho EXPORT | **DENY** | Action binding |
| Requester cũng là custodian approver | **DENY nếu SoD yêu cầu** | Separation of duties |
| Operator tự approve request mình thực hiện | **DENY nếu SoD yêu cầu** | Independent approval |
| M approvals cùng một domain | **DENY nếu policy yêu cầu diversity** | Failure-domain independence |
| Policy revision cũ | **DENY** | Anti-rollback |
| Approval replay ở ceremony khác | **DENY** | One-time request binding |

### 15.2. Shamir/secret-share tests

Nếu dùng SSS, cần test bằng implementation đã được đánh giá:

- **M-1 shares** không khôi phục được secret.
- **M shares** từ đúng share set khôi phục đúng secret.
- M shares có **duplicate index** phải bị từ chối.
- Trộn shares từ **share set/version khác** phải thất bại.
- Share bị sửa/hỏng được phát hiện bằng integrity/authentication mechanism phù hợp.
- Shares không bị lộ qua logs, crash dumps, telemetry hoặc temporary files.
- Re-sharing/rotation tạo bộ mới và bộ cũ bị retire/zeroize theo procedure.
- Khôi phục ở DR boundary tạo cùng key identity/fingerprint khi semantics yêu cầu.

**Không test bằng cách cố lấy đủ shares của production key trong một máy developer**. Dùng test secret và environment đã được phê duyệt.

### 15.3. HSM/KMS restore tests

- Backup blob được restore lên thiết bị/partition tương thích.
- HSM yêu cầu đúng **M-of-N tokens/security officers** cho thao tác được chỉ định.
- Restore sai domain/backup key bị từ chối.
- Key usage/algorithm/exportability sau restore khớp manifest.
- KMS IAM/key policy vẫn enforce đúng principal và operation.
- Restore không vô tình chuyển key từ disabled/retired sang active new-use.
- Audit log có request ID, operator, custodian, keyRef/version và outcome.
- KMS region outage được xử lý theo DR plan mà không hardcode secret.

### 15.4. End-to-end data recovery tests

Một test DR có ý nghĩa phải:

1. Restore **ciphertext backup** và metadata.
2. Đạt quorum khôi phục đúng KEK/backup root.
3. Restore/resolve EDK và wrapping context.
4. Decrypt synthetic record với **nonce, AAD, algorithm và key version** đúng.
5. Verify integrity; dữ liệu sai hoặc tenant sai bị từ chối.
6. Xác nhận application authorization và audit.
7. Đo **RTO/RPO thực tế**.
8. Thu hồi temporary grants và đóng ceremony.

**HSM restore thành công chưa chứng minh database restore thành công**; ngược lại database restore thành công chưa chứng minh key hierarchy có thể phục hồi.

## 16. Case study: Khôi phục KEK production sau khi HSM chính bị hỏng

### 16.1. Bối cảnh

Một nền tảng thanh toán có:

~~~text
Production:
  HSM cluster A ở site chính
  Tenant KEK v7 bảo vệ EDK của invoice DEKs
  Database chứa ciphertext, EDK, nonce, AAD schema

Recovery:
  HSM backup blob B-2026-11
  Backup wrapping key trong custody độc lập
  5 recovery custodians, threshold 3-of-5
  HSM DR cluster B ở site khác

Services:
  Billing Reader, Billing Writer, Migration Worker
~~~

HSM cluster A gặp lỗi phần cứng và không thể phục hồi tại chỗ. Không có dấu hiệu key material bị compromise; sự cố được phân loại là **availability failure**.

### 16.2. Thiết kế sai cần tránh

~~~text
Operator tải backup blob và recovery secret về laptop.
Operator dùng tài khoản admin chung để restore.
Key được import vào software keystore tạm.
Billing Reader được cấp quyền Decrypt mọi tenant.
Không có audit/custodian attendance.
~~~

Thiết kế này phá custody, tạo raw-key exposure, bỏ quorum và mở quyền dữ liệu quá rộng.

### 16.3. Quy trình 3-of-5

**Bước 1 — Declare recovery.** Incident commander xác nhận HSM outage, target **KEK-v7**, backup ID, purpose, RTO và scope tenant.

**Bước 2 — Verify backup.** Backup custodian và auditor xác minh manifest, backup timestamp, integrity và tương thích DR HSM. Không tải material ra ngoài approved boundary.

**Bước 3 — Call custodians.** Liên hệ A–E bằng kênh xác thực độc lập; xác minh identity/MFA và share set version. Nếu chỉ A+B có mặt, **chưa đủ quorum**.

**Bước 4 — Conduct ceremony.** A+B+C tham gia. HSM/operator xác minh M-of-N, security domain, action RESTORE_HSM_BACKUP và target keyRef.

**Bước 5 — Restore inside HSM.** Backup object được restore vào DR HSM theo provider-supported flow. Key material không xuất raw ra laptop.

**Bước 6 — Validate.** Kiểm tra key object identity, algorithm, usage, non-exportability, state và key policy. Dùng synthetic EDK/ciphertext đã chuẩn bị để thử Unwrap/Decrypt.

**Bước 7 — Restore service.** Cập nhật KMS/HSM endpoint và IAM grants theo tenant/reader scope; mở traffic dần và theo dõi lỗi.

**Bước 8 — Close ceremony.** Thu hồi temporary roles, xác nhận shares được niêm phong, audit đầy đủ và đo RTO.

### 16.4. Kết quả và câu hỏi hậu kiểm

- **Data recovery** thành công vì ciphertext, EDK, AAD và KEK version cùng được phục hồi.
- Không cần thay DEK nếu material không compromise và key identity/backup integrity đúng.
- Không tự động chuyển KEK-v7 thành new-write key nếu incident policy yêu cầu kiểm tra trước.
- Custodians A/B/C không có quyền đọc invoice plaintext; Billing Reader vẫn phải qua application authorization.
- Nếu DR HSM dùng provider object ID mới, registry cần mapping **old keyRef → restored object** có audit và validation.

Sau sự cố, cần hỏi: vì sao HSM chính hỏng, backup gần nhất đến đâu, DR có đủ capacity, custodian có đạt quorum trong RTO, firmware có tương thích, temporary grants đã gỡ và recovery root có cần rotation/resharing không?

## 17. Incident response: Khi quorum hoặc recovery material bị compromise

### 17.1. Một share bị nghi lộ

1. Xác định share set ID, custodian, index, nơi lưu và thời gian nghi lộ.
2. Kiểm tra attacker có thể lấy thêm shares qua shared admin/IdP/site không.
3. Nếu còn dưới threshold, vẫn **cô lập và đánh giá**; không coi việc chưa đủ M là không có rủi ro.
4. Kích hoạt **reshare/recovery secret rotation** theo scheme và provider.
5. Thu hồi share cũ, token, vault access và approval credentials.
6. Kiểm tra audit xem có ceremony/recovery bất thường.

### 17.2. Đủ M shares hoặc recovery secret đã bị lộ

1. Coi recovery secret/key có khả năng **compromised**.
2. Cô lập backup/recovery endpoint, revoke access và sessions.
3. Xác định những key objects/data keys có thể khôi phục hoặc mở.
4. Tạo recovery root/share set mới và bảo vệ bằng quorum độc lập.
5. Rotate/replace các keys bị ảnh hưởng; rewrap/re-encrypt dữ liệu theo risk.
6. Kiểm tra bản backup cũ, EDK, logs, exports và offline copies.
7. Không tiếp tục dùng lại raw key material chỉ vì restore được.

### 17.3. Custodian thông đồng hoặc giả mạo approval

- Suspend quyền custodian liên quan, giữ nguyên evidence.
- Kiểm tra **approval signatures, MFA events, request IDs, policy revision, source device và physical access logs**.
- Thu hồi các temporary grants và session đã phát.
- Đánh giá có đủ M shares/approvals thực tế hay chỉ workflow bị bypass.
- Xem xét thay threshold/roster qua change control độc lập.
- Tăng giám sát các recovery requests và key use sau thời điểm nghi vấn.

### 17.4. Không đủ quorum trong DR

Không tự hạ M hoặc lấy share của một người đang vắng mặt. Có thể:

- Kích hoạt **alternate custodians/succession** đã được chỉ định từ trước.
- Dùng backup site/quorum path khác đã được kiểm thử.
- Thực hiện business continuity với **degraded mode** không cần key bị khóa, nếu threat model cho phép.
- Escalate tới governance/incident commander để quyết định risk acceptance có kiểm soát.

Nếu không còn recovery path hợp lệ, cần ghi rõ **không thể phục hồi key**; không tạo một đường bypass bí mật rồi gọi đó là DR.

## 18. Governance, audit và kiểm kê recovery

### 18.1. Những gì phải audit

| Sự kiện | Metadata nên ghi | Không ghi |
|---|---|---|
| **Create/rotate share set** | Set ID/version, M/N, target keyRef, algorithm/provider, approver | Share bytes, secret coefficients |
| **Assign/transfer custodian** | Custodian ID, role, custody location, actor, time, approval | PIN/activation secret |
| **Open recovery request** | Incident ID, reason, target keyRef, scope, RTO, requester | Raw key hoặc plaintext data |
| **Approval** | Approver identity, MFA result, action, policy revision, expiry, request ID | OTP, recovery token secret |
| **Quorum reached/not reached** | Valid count, M/N, domain diversity, rejection reason | Nội dung share |
| **HSM/KMS restore** | Provider request ID, device/partition, key object ID/version, outcome | Exported private key |
| **Key validation** | Fingerprint/identifier, algorithm, usage, state, exportability | Key material |
| **Temporary grant** | Principal, actions, scope, effective time, expiry, revocation | Access token |
| **Recovery test** | Test dataset ID, result, RTO/RPO, errors | Production plaintext |
| **Destroy/retire share** | Set ID, custody evidence, approvals, destruction confirmation | Share content |

Audit cần **integrity, access control, retention và time synchronization**. Recovery coordinator/operator không nên có quyền sửa hoặc xóa evidence của chính ceremony họ thực hiện.

### 18.2. Metric để phát hiện recovery drift

- Số key critical **không có backup hoặc recovery owner**.
- Số share set thiếu custodian, thiếu location hoặc có **custodian đã offboard**.
- Tỷ lệ **recovery drill thành công** và RTO/RPO thực tế.
- Số request **không đạt quorum**, thời gian chờ custodian.
- Số lần dùng **break-glass/alternate custodian**.
- Số share/custody records có version không khớp keyRef hoặc backup manifest.
- Số recovery approvals **hết hạn, replay, duplicate hoặc sai action scope**.
- Số backup blobs không restore được do firmware/provider incompatibility.
- Số key objects restored nhưng **IAM/usage/exportability** lệch baseline.
- Số recovery roots dùng chung failure domain với production backups.
- Số key dependencies chưa được xác minh trong DR.
- Số temporary grants còn tồn tại sau ceremony.

**Không có recovery request trong năm không chứng minh quy trình sẵn sàng**. Có thể đơn giản là chưa từng thử. Cần drill định kỳ và kiểm thử thay đổi sau khi đổi custodian, HSM firmware, provider, identity platform hoặc key hierarchy.

### 18.3. Change control cho threshold và roster

Thay đổi **M, N, custodian roster, custody location, recovery algorithm hoặc provider** là thay đổi security-sensitive:

1. Ghi rõ lý do và threat model.
2. Phân tích ảnh hưởng security/availability và các failure domains.
3. Xác định có cần **reshare/re-generation** hay không theo scheme.
4. Phê duyệt bởi người độc lập với người triển khai.
5. Thực hiện ceremony với set mới, verify recovery bằng test secret.
6. Thu hồi/tiêu hủy shares cũ theo quy trình và lưu audit.
7. Cập nhật inventory/runbook/DR contacts.

**Không thay threshold bằng một chỉnh sửa config đơn lẻ** nếu recovery secret/share set được tạo theo threshold cũ. Đặc biệt, giảm M có thể đòi hỏi một **share set mới** chứ không chỉ thay con số trong policy.

### 18.4. Integrity của Shamir shares

Shamir Secret Sharing bảo vệ tính bí mật theo threshold, nhưng **bản thân tính chất secret sharing không tự xác thực mọi share**. Một share bị thay hoặc nhập sai có thể khiến quá trình khôi phục thất bại hoặc cho kết quả sai.

Các scheme/implementation có thể dùng **authenticated storage, MAC/signature cho từng share, verifiable secret sharing (VSS), commitments hoặc provider-specific integrity controls**. Lựa chọn phải phù hợp threat model và tránh làm lộ secret qua cách xác minh.

Kiểm tra:

- Share có đúng **set ID, version, index, threshold, target key identity**?
- Share integrity/authenticity được xác minh trước khi combine?
- Có phát hiện duplicate index và share set mix-up?
- Có thể xác minh reconstructed key bằng **known fingerprint/public key/test vector** mà không log raw material?
- Nếu một share sai, quy trình có fail closed và giữ custody evidence?

Không dùng một **checksum không xác thực** làm bằng chứng chống attacker có thể sửa cả share lẫn checksum. Integrity metadata cần được bảo vệ bằng trust boundary độc lập.

## 19. Checklist triển khai quorum cho key recovery

1. **Scope:** Đã xác định key family, purpose, key ID/version, provider, tenant và dữ liệu phụ thuộc?
2. **Recovery goal:** Cần restore key object, reconstruct secret, recover data hay restore toàn dịch vụ?
3. **Mechanism:** Đã phân biệt approval quorum, split knowledge, Shamir SSS, HSM M-of-N và threshold cryptography?
4. **Provider semantics:** Đã xác minh M/N áp dụng cho hành động nào và HSM/KMS thực thi ra sao?
5. **Threshold:** M/N được chọn từ threat model, availability và khả năng thông đồng/mất share?
6. **Independence:** Custodians có tách biệt về human, organization, site, identity, device và admin domains?
7. **Roles:** Key owner, custodian, coordinator, operator, security officer và auditor có nhiệm vụ/quyền rõ?
8. **SoD:** Requester/operator không thể tự đạt quorum hoặc tự duyệt hành động mình thực hiện?
9. **Custody:** Mỗi share/token có người giữ, location, status, version và transfer procedure?
10. **Share confidentiality:** Shares không nằm trong email, chat, ticket, source control, CI log hoặc shared drive?
11. **Share integrity:** Có kiểm tra set ID, index, version, target key và authenticity/integrity?
12. **Storage:** Shares/backup blobs được bảo vệ at rest và có access logs?
13. **Transport:** Recovery material chỉ đi qua approved secure channel và boundary?
14. **Recovery root:** Backup wrapping key/recovery root độc lập với material nó bảo vệ?
15. **No circular dependency:** Có thể khôi phục recovery root mà không cần chính root đó?
16. **Key hierarchy:** Có sơ đồ dependency từ data ciphertext/EDK tới DEK/KEK/backup root?
17. **Data metadata:** Ciphertext, nonce, tag, AAD, algorithm và key version được backup đầy đủ?
18. **Key purpose:** Restored key có đúng purpose, usage, algorithm và tenant scope?
19. **Exportability:** Restore không vô tình làm key non-exportable trở thành exportable?
20. **Policy:** IAM/grants và HSM attributes sau restore khớp baseline được duyệt?
21. **RTO/RPO:** Thời gian liên hệ đủ M custodians, ceremony, HSM restore và data recovery đã được đo?
22. **Succession:** Custodian nghỉ việc/mất thiết bị có transfer/alternate process?
23. **Lost share:** Có quy trình xử lý mất/hỏng/nghi lộ mà không tự hạ threshold?
24. **Resharing:** Thay custodian/threshold có procedure tạo share set mới và retire set cũ?
25. **Ceremony:** Có incident/ticket, target keyRef, participants, dual control, witnesses và checklist?
26. **One-time approval:** Approvals gắn request ID/action/keyRef, có expiry và chống replay?
27. **Secure execution:** Reconstruction/restore diễn ra trong HSM hoặc approved boundary, không trên laptop tùy tiện?
28. **Validation:** Có verify key identity/fingerprint, algorithm, state, usage và synthetic data?
29. **End-to-end restore:** Đã thử khôi phục ciphertext + EDK + AAD + schema, không chỉ HSM object?
30. **DR site:** HSM/provider/firmware/partition và trust dependencies tương thích?
31. **Temporary access:** Grants/session chỉ tồn tại trong recovery window và được thu hồi sau đó?
32. **Audit:** Có immutable/tamper-evident evidence cho request, approvals, restore, test và cleanup?
33. **Incident response:** Có quy trình riêng khi share lộ, đủ M shares bị lộ hoặc operator bị compromise?
34. **Compromise distinction:** Không restore lại raw key đã bị lộ để tiếp tục tin cậy?
35. **Backup copies:** Đã rà primary, archive, replicas, offline media và escrow trước khi destroy?
36. **Threshold change:** Có approval độc lập và re-generation/resharing khi cần?
37. **Drill:** Recovery được diễn tập định kỳ và sau mọi thay đổi quan trọng?
38. **Metrics:** Theo dõi quorum availability, failed drills, stale custody, temporary grants và RTO/RPO?
39. **Audit privacy:** Logs không ghi share bytes, raw key, PIN, OTP hoặc plaintext?
40. **Final acceptance:** Có bằng chứng vừa khôi phục đúng key/data vừa từ chối request không đủ quorum hoặc sai scope?

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Quorum 3-of-5 nghĩa là gì?

**Trả lời:** Cần ít nhất ba thành phần hợp lệ, khác nhau trong tổng số năm được chỉ định, theo đúng cơ chế và policy. Hai người không đủ; không được đếm một người nhiều lần.

**Câu 2.** Quorum approval có đồng nghĩa Shamir Secret Sharing không?

**Trả lời:** **Không.** Approval quorum là nhiều người phê duyệt hành động; Shamir chia secret thành shares để khôi phục secret theo threshold.

**Câu 3.** Split knowledge khác dual control thế nào?

**Trả lời:** Split knowledge phân chia thông tin bí mật để một người không biết toàn bộ; dual control yêu cầu nhiều người cùng kiểm soát/thực hiện hành động. Một hệ thống có thể dùng cả hai nhưng chúng không đồng nghĩa.

**Câu 4.** Trong Shamir 3-of-5, hai shares có đủ khôi phục secret không?

**Trả lời:** **Không**, theo scheme lý tưởng và implementation đúng, cần ít nhất ba shares khác nhau.

**Câu 5.** Ba shares bị compromise trong scheme 3-of-5 có ý nghĩa gì?

**Trả lời:** Threshold đã đạt; secret có thể được khôi phục. Cần xem recovery secret/key là compromised và xử lý thay material, không chỉ thay tên custodian.

**Câu 6.** M-of-N có thể chịu đồng thời bao nhiêu shares mất và bao nhiêu shares lộ?

**Trả lời:** Không có một con số kết hợp chung. Mất shares ảnh hưởng availability; lộ shares ảnh hưởng confidentiality. Phải đánh giá số shares còn hợp lệ, số shares attacker có thể thu thập và failure domains.

**Câu 7.** Một HSM ghi “3-of-5” có chắc đang dùng Shamir không?

**Trả lời:** **Không.** Nó có thể là security officer token authentication hoặc cơ chế provider-specific. Cần đọc tài liệu/semantics của HSM.

**Câu 8.** Threshold signature có phải ghép ba private-key shares thành private key đầy đủ rồi ký không?

**Trả lời:** **Không nhất thiết;** mục tiêu của nhiều threshold-signature schemes là phân tán phép toán và không tái tạo full private key tại một điểm.

**Câu 9.** Backup key thành công có chứng minh data recovery thành công không?

**Trả lời:** **Không.** Cần ciphertext, EDK, nonce, AAD, schema, key material, policy và quyền truy cập phù hợp; phải thử restore end-to-end.

**Câu 10.** Có nên mã hóa backup KEK bằng chính KEK đó rồi coi như có recovery?

**Trả lời:** **Không.** Nếu KEK mất thì backup cũng không mở được. Cần backup wrapping/recovery root độc lập và kiểm tra dependency graph.

**Câu 11.** Một custodian có share nhưng không có role Recovery Custodian còn được tính vào quorum không?

**Trả lời:** **Không theo policy yêu cầu role đó.** Phải xác thực identity, status, custody và authorization.

**Câu 12.** Nếu requester đồng thời là một trong M approvers, có vấn đề gì?

**Trả lời:** Có thể vi phạm **separation of duties**. Với recovery nhạy cảm, requester/operator cần tách khỏi approvers theo policy.

**Câu 13.** Vì sao phải gắn approval với keyRef và action?

**Trả lời:** Để approval restore key A không thể bị replay cho key B hoặc đổi thành export/destroy action.

**Câu 14.** Có thể giảm threshold từ 3 xuống 2 khi một custodian đi nghỉ không?

**Trả lời:** **Không tự ý.** Đây là thay đổi security policy, có thể yêu cầu tạo lại share set và phê duyệt độc lập.

**Câu 15.** Nếu một custodian nghỉ việc, chỉ đổi tên trong inventory là đủ?

**Trả lời:** **Không.** Cần thu hồi identity/vault access, đánh giá share cũ, resharing/re-generation nếu cần và kiểm thử bộ shares mới.

**Câu 16.** HSM backup blob có nhất thiết chứa raw private key để operator đọc không?

**Trả lời:** **Không.** Provider có thể dùng backup format được bảo vệ, restore bên trong HSM và giữ material non-exportable.

**Câu 17.** Non-exportable key có nghĩa không thể bị lạm dụng?

**Trả lời:** **Không.** Principal có quyền Sign/Decrypt có thể dùng key như oracle dù không export được raw bytes.

**Câu 18.** Một quorum approval ở giao diện có đủ nếu operator vẫn gọi API restore trực tiếp được không?

**Trả lời:** **Không.** Quorum phải được enforce ở control plane/provider hoặc qua identity/permissions khiến direct API bypass không thể xảy ra.

**Câu 19.** Ba shares cùng nằm trong một vault do một admin kiểm soát có thật sự độc lập không?

**Trả lời:** **Không.** Effective control và common-mode failure quan trọng hơn số người hoặc số phong bì trên giấy.

**Câu 20.** Shamir Secret Sharing tự xác thực share có bị thay không?

**Trả lời:** **Không tự động.** Cần integrity/authenticity controls, share set/index validation hoặc cơ chế verifiable sharing phù hợp.

**Câu 21.** Khi một share bị mất nhưng còn đủ M shares an toàn, có cần làm gì?

**Trả lời:** Có. Điều tra custody/exposure, loại bỏ hoặc reshare bộ cũ theo policy, thu hồi access và cập nhật inventory.

**Câu 22.** Khi M shares đã bị lộ, có thể chỉ tạo thêm một share mới không?

**Trả lời:** **Không đủ.** Secret cũ đã có thể bị tái tạo; cần thay/re-generate recovery secret hoặc key material liên quan và đánh giá dữ liệu phụ thuộc.

**Câu 23.** Khôi phục signing private key đã bị compromise có giải quyết sự cố không?

**Trả lời:** **Không.** Restore cùng raw material giữ nguyên compromise. Cần keypair/certificate mới, revoke trust cũ và xử lý chữ ký/artifact bị ảnh hưởng.

**Câu 24.** Quorum recovery cho KEK có cho custodian quyền xem plaintext tenant data không?

**Trả lời:** **Không mặc nhiên.** Quyền restore key, quyền Unwrap và quyền đọc record là các lớp riêng.

**Câu 25.** RTO có bao gồm thời gian tìm đủ custodian không?

**Trả lời:** **Có.** Thời gian liên hệ, xác thực, ceremony, restore, verify và reconnect service đều ảnh hưởng RTO.

**Câu 26.** Nếu HSM restore trả success, có thể đóng DR incident ngay không?

**Trả lời:** **Chưa.** Phải xác minh đúng key identity/attributes, restore sample data, IAM, audit, RTO/RPO và cleanup.

**Câu 27.** Có nên dùng production plaintext để thử recovery?

**Trả lời:** Không nếu có test vector/synthetic data đủ đại diện. Recovery validation phải theo scope và dữ liệu được phê duyệt.

**Câu 28.** Backup wrapping key và backup blob cùng bị lấy có thể tạo rủi ro gì?

**Trả lời:** Attacker có thể mở backup material tùy scheme; cần custody/quorum và failure domain độc lập.

**Câu 29.** Vì sao phải phân biệt key recovery với incident response?

**Trả lời:** Recovery khôi phục khả năng dùng key; incident response quyết định key/material còn đáng tin không. Khôi phục cùng key đã lộ có thể phục hồi availability nhưng không khôi phục security.

**Câu 30.** Khi nào có thể destroy old share set?

**Trả lời:** Sau khi bộ mới được tạo/kiểm thử, custody và recovery path mới được xác nhận, old access bị thu hồi, dependencies/backup được rà soát và có approval/audit.

## 21. Tổng kết

**Quorum cho key recovery** là một cơ chế kiểm soát việc khôi phục khóa nhạy cảm bằng cách yêu cầu đủ số người hoặc thành phần độc lập. M-of-N giúp cân bằng **khả năng phục hồi** với **nguy cơ một người đơn lẻ hoặc một nhóm nhỏ chiếm quyền**, nhưng con số threshold không tự bảo đảm security nếu custody, identity, provider policy và audit yếu.

Các nguyên tắc phải giữ:

- **Nói rõ loại quorum:** approval, split knowledge, Shamir shares, HSM M-of-N và threshold cryptography có semantics khác nhau.
- **Chọn M/N theo threat model:** tính cả shares mất/lộ, custodian availability, site/IdP common-mode và thời gian RTO.
- **Custody độc lập:** mỗi share/token có owner, location, integrity, lifecycle và succession; không để một admin kiểm soát tất cả.
- **Recovery ceremony có kiểm soát:** đúng incident, keyRef/version, action, M approvals, separation of duties, secure HSM boundary và audit.
- **Backup hierarchy không vòng tròn:** recovery root phải được bảo vệ độc lập với key/backup mà nó mở.
- **Verify end-to-end:** khôi phục đúng key attributes, EDK/ciphertext/AAD, IAM và dữ liệu; backup success không bằng data recovery success.
- **Tách recovery khỏi trust decision:** key đã compromise không trở nên an toàn chỉ vì quorum khôi phục được nó.
- **Diễn tập và kiểm kê:** test RTO/RPO, alternate custodians, DR site, share rotation, backup restore và failure scenarios.

**Điểm cốt lõi:** Quorum chỉ có giá trị khi **đủ người đúng thẩm quyền, đúng shares, đúng key/version, đúng hành động và đúng boundary** cùng tham gia. Kết hợp **M-of-N, custody độc lập, HSM/KMS enforcement, separation of duties, recovery drills và audit** giúp tổ chức phục hồi khóa mà không biến chính con đường phục hồi thành điểm yếu lớn nhất.
