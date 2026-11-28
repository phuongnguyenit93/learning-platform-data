# Rotation theo thời gian — Lập lịch thay khóa theo cryptoperiod

## 1. Rotation theo thời gian là gì?

**Rotation theo thời gian (time-based key rotation)** là quy trình **chủ động đưa vật liệu khóa mới vào sử dụng theo một lịch hoặc thời hạn đã được chính sách xác định**, đồng thời chuyển khóa cũ sang trạng thái thích hợp và xử lý các phụ thuộc còn tồn tại. Ví dụ: hệ thống có lịch đánh giá và thay khóa ký định kỳ; trước ngày chuyển đổi, nó tạo private/public key pair mới, phân phối public key đến verifier, sau đó chỉ ký mới bằng private key mới.

Rotation không chỉ là **đổi tên alias**, **đặt thời hạn trên dashboard**, **đổi password của keystore**, hay **đổi policy IAM**. Một lượt thay khóa có ý nghĩa mật mã khi **key material được thay** hoặc khi nền tảng thực hiện loại rotation vật liệu tương đương đúng semantics; sau đó các workload phải sử dụng đúng phiên bản mới cho hoạt động mới.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chủ đề thuộc chương **Cryptoperiod và rotation**, kết nối vòng đời khóa **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy** với mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, phân quyền và kiểm toán.

Một thiết kế rotation tốt phải trả lời:

1. **Khi nào** không còn được tạo phép toán mật mã mới bằng khóa hiện tại?
2. **Khóa nào** được sinh/thay, bằng nguồn ngẫu nhiên và ranh giới bảo vệ nào?
3. **Dữ liệu, phiên, chữ ký hoặc các bên nhận nào** còn cần khóa cũ sau mốc chuyển đổi?
4. **Ai có quyền** tạo khóa, kích hoạt, chuyển alias, rewrap dữ liệu, retire và destroy?
5. **Bằng chứng nào** chứng minh cutover, khả năng đọc lại, thu hồi và phục hồi đã đạt?

> **Nguyên tắc cốt lõi:** **Kết thúc cryptoperiod cho hoạt động tạo mới không đồng nghĩa mọi hoạt động sử dụng khóa cũ đều bị cấm ngay lập tức.** Quyền Encrypt/Sign mới và quyền Decrypt/Verify lịch sử phải được xác định riêng theo thuật toán, loại khóa và chính sách.

### 1.1. Ví dụ đơn giản

Giả sử **Invoice Service** dùng khóa đối xứng **DEK-v1** để mã hóa hóa đơn. Chính sách yêu cầu sau một thời gian nhất định phải dùng **DEK-v2** cho bản ghi mới. Khi đến hạn:

- **Encrypt mới:** Chỉ dùng DEK-v2 sau khi v2 được kích hoạt.
- **Decrypt hóa đơn cũ:** Có thể còn cần DEK-v1 cho dữ liệu chưa được mã hóa lại.
- **Wrapped DEK và key ID:** Metadata phải cho biết phiên bản nào bảo vệ từng ciphertext.
- **Hủy DEK-v1:** Chỉ thực hiện khi không còn phụ thuộc hợp lệ hoặc đã có phương án chuyển đổi/khôi phục được kiểm chứng.

Nếu hệ thống xóa DEK-v1 ngay khi tạo DEK-v2, các hóa đơn cũ có thể trở thành **không thể giải mã**. Ngược lại, nếu vẫn mã hóa hóa đơn mới bằng v1 vì cache chưa đổi, rotation chỉ thành công về mặt quản trị, không thành công về mặt vận hành.

## 2. Cryptoperiod, lifetime, expiry và rotation khác nhau thế nào?

**Cryptoperiod** là khoảng thời gian mà một khóa được **cho phép sử dụng để thực hiện một hoặc nhiều chức năng mật mã đã xác định**, theo chính sách và mục đích. Một khóa có thể có nhiều **giai đoạn sử dụng khác nhau** tùy vai trò bên tạo và bên nhận thông tin.

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Key generation time** | Thời điểm sinh vật liệu khóa | KMS tạo key-v2 lúc 08:00 |
| **Activation time** | Thời điểm khóa được phép dùng cho chức năng mới | Key-v2 được bật Sign lúc 10:00 |
| **Originator-usage period** | Giai đoạn khóa được dùng để **tạo bảo vệ mới** | Encrypt mới hoặc Sign tài liệu mới |
| **Recipient-usage period** | Giai đoạn khóa được dùng để **xử lý dữ liệu đã bảo vệ trước đó** | Decrypt ciphertext cũ hoặc Verify chữ ký cũ |
| **Cryptoperiod** | Khoảng sử dụng theo chức năng và policy | Một lịch dùng KEK để Wrap DEK mới |
| **Rotation deadline** | Mốc chính sách yêu cầu chuyển sang vật liệu khóa mới | Cutover trước khi hết kỳ |
| **Retirement** | Dừng dùng khóa cho hoạt động tạo mới; còn có thể có quyền lịch sử | KEK-v1 chỉ Unwrap blobs cũ |
| **Revocation/disable** | Chặn một hoặc nhiều thao tác vì policy hoặc sự cố | Dừng Sign bằng private key bị nghi lộ |
| **Destruction** | Loại bỏ key material theo quy trình | Hủy DEK sau khi hết retention |
| **Certificate expiry** | Mốc hiệu lực của certificate theo PKI | Certificate TLS hết hạn; khác cryptoperiod của key material |

### 2.1. Mốc sinh khóa không nhất thiết là mốc kích hoạt

Một cặp khóa ký có thể được sinh trước **ngày cutover** để phía xác minh đăng ký public key và kiểm tra tính tương thích. Do đó:

~~~text
Ngày tạo key-v2  →  Kiểm thử và phân phối public key-v2
                →  Ngày active Sign-v2
                →  Hết thời hạn Sign-v2
                →  Giai đoạn Verify lịch sử (nếu policy cho phép)
                →  Hủy private key-v2 khi đủ điều kiện
~~~

Nếu policy tính thời hạn từ **createdAt** nhưng scheduler lại tính từ **activatedAt**, hệ thống sẽ lệch lịch. Phải định nghĩa **mốc bắt đầu và loại period** trong policy, lưu nhất quán ở inventory.

### 2.2. Thời hạn chứng chỉ không phải chính cryptoperiod

Một certificate mới có thể được **cấp lại bằng public key cũ** nếu quy trình cho phép. Như vậy **gia hạn certificate không tự thay private key**. Ngược lại, khi thay private key, cần phát hành/đăng ký public key/certificate phù hợp, nhưng thời hạn này có thể khác tuổi thọ vật liệu khóa và khoảng thời gian người nhận còn tin chữ ký lịch sử.

Đặc biệt với TLS:

- **Certificate validity** kiểm soát điều kiện xác minh danh tính theo PKI.
- **Private signing key use** quyết định endpoint có thể dùng khóa để xác thực handshake mới hay không.
- **TLS traffic keys** được dẫn xuất theo handshake/session, không phải bản sao của certificate private key.

Không chỉ xem ngày hết hạn certificate rồi kết luận **mọi khóa phiên và mọi DEK đều đã được rotate**.

### 2.3. Retirement không phải destruction

Một khóa đã hết quyền dùng **Encrypt/Sign mới** có thể còn cần cho **Decrypt/Verify**. Ngược lại, nếu private key đã bị **compromised**, chính sách có thể buộc chặn cả một số dạng sử dụng lịch sử hoặc đánh giá độ tin cậy của chữ ký.

Vì thế nên **quản lý trạng thái theo operation**, không đơn giản dùng một cờ active=true cho toàn bộ Encrypt, Decrypt, Sign, Verify và Unwrap.

## 3. Vì sao phải rotate theo thời gian?

Rotation chủ động giúp giới hạn **khoảng thời gian một khóa được tiếp tục dùng cho hoạt động mới**, làm cho kế hoạch thay khóa trở thành một quy trình đều đặn, đồng thời hỗ trợ crypto agility và giảm phụ thuộc vào material cũ. Tuy nhiên, lợi ích an ninh cụ thể phụ thuộc **kiểu khóa, lượng dữ liệu, primitive, tình trạng bị lộ và độ dài thời gian giữ dữ liệu**.

### 3.1. Mục tiêu bảo mật

- **Giới hạn sử dụng key material:** Không để một khóa tạo dữ liệu/chữ ký mới vô thời hạn.
- **Giảm phạm vi sử dụng theo thời gian:** Nếu một khóa bị lộ ở một thời điểm, khóa mới có thể hạn chế các hoạt động tương lai; dữ liệu cũ có thể vẫn bị ảnh hưởng.
- **Hạn chế tích lũy usage:** Theo dõi số phép Encrypt/Sign, lượng dữ liệu, nonce/message limits; xoay trước ngưỡng nguy hiểm.
- **Crypto agility:** Tạo cơ hội chuyển thuật toán, key size, KMS/HSM provider hoặc chính sách.
- **Thực thi kiểm soát:** Buộc rà soát IAM, owner, môi trường, key inventory, trust distribution và DR định kỳ.
- **Tăng khả năng ứng phó sự cố:** Có sẵn runbook, key versioning và phương án rollback an toàn.

### 3.2. Rotation không tự xóa rủi ro quá khứ

| Tình huống | Rotation có ích ở đâu? | Điều rotation không tự làm |
| --- | --- | --- |
| Raw DEK cũ bị lộ | Dùng DEK mới cho dữ liệu mới | Không biến ciphertext cũ và raw DEK đã bị lấy thành an toàn |
| Raw KEK cũ bị lộ | Ngừng Wrap bằng KEK cũ, chuyển key domain | Không làm mất những bản KEK/wrapped DEK attacker đã sao chép |
| Private signing key cũ bị lộ | Tạo signer mới, ngừng Sign bằng v1 | Không tự làm verifier từ chối chữ ký giả v1 |
| MAC key chia sẻ bị lộ | Chuyển cả hai phía sang key v2 | Không tự loại bỏ HMAC tag giả được tạo với v1 |
| KMS IAM role quá rộng | Rotation tạo điểm rà soát grants | Không thay quyền bị cấp sai nếu policy vẫn như cũ |
| AES-GCM nonce bị tái sử dụng | Khóa mới giới hạn sự cố tương lai | Không sửa được nonce reuse dưới DEK cũ |
| Public key trust registry bị tráo | Có cơ hội cấp key/trust mới an toàn | Không tự phục hồi issuer trust nếu attacker vẫn kiểm soát registry |

**Không dùng câu “đã rotate hôm nay” làm bằng chứng hệ thống không bị ảnh hưởng bởi một key compromise xảy ra hôm qua.** Phải điều tra dữ liệu đã mã hóa, chữ ký đã phát hành và những bản sao bị lộ.

### 3.3. Rotation phải đi cùng inventory

Không thể biết cần thay khóa nào nếu chỉ có tên tệp hoặc alias. Mỗi khóa nên có:

- **Key ID, version, algorithm, key usage và purpose**.
- **Owner, environment, tenant/data domain, workload principals**.
- **Creation/activation/rotation deadline** và chính sách period.
- **State per operation** như SignActive/VerifyHistorical hoặc WrapActive/UnwrapHistorical.
- **KMS/HSM/keystore reference**, export policy và dependency graph.
- **Danh sách ciphertext/wrapped DEK, chứng chỉ, bên nhận public key hoặc MAC key** đang phụ thuộc.
- **Backup/DR footprint, incident/change ID và bằng chứng audit**.

## 4. Chọn khoảng rotation theo rủi ro, không sao chép một con số

Không tồn tại một chu kỳ cố định “an toàn cho mọi khóa”. Khoảng phù hợp phụ thuộc **loại primitive, độ mạnh, lượng sử dụng, dữ liệu, lịch sử sự cố, chính sách pháp lý và khả năng vận hành**. Các tiêu chuẩn/quy định chuyên ngành có thể đặt giới hạn riêng; cần kiểm tra phiên bản và hệ thống áp dụng trước khi đưa vào policy.

| Tiêu chí | Câu hỏi | Hệ quả lên lịch |
| --- | --- | --- |
| **Mục đích** | Encrypt at rest, Sign JWT, TLS, HMAC, KEK, ephemeral session? | Thời hạn và hoạt động lịch sử khác nhau |
| **Data sensitivity** | PII, tài chính, chứng cứ pháp lý hay dữ liệu ít nhạy cảm? | Có thể cần rotation và kiểm soát chặt hơn |
| **Threat model** | DB leak, API abuse, raw key compromise, insider? | Cần chuẩn bị emergency rotation bên cạnh lịch |
| **Algorithm strength** | Thuật toán/key size còn phù hợp thời gian bảo vệ không? | Có thể cần chuyển thuật toán trước hạn |
| **Use limits** | Bao nhiêu Encrypt/Sign, bytes, nonce/IV và messages? | Có thể phải rotate **trước** ngày lịch |
| **Key distribution** | Bao nhiêu clients/partners/regions cùng phụ thuộc? | Cần thời gian chuẩn bị, staged rollout |
| **Data retention** | Dữ liệu cần đọc lại bao lâu? | Recipient/decryption period có thể dài hơn kỳ Encrypt |
| **Backup/DR** | Snapshots cũ còn wrapped DEK/cert nào? | Chưa được destroy quá sớm |
| **Operational risk** | Rotation có tự động, idempotent và được test không? | Chọn lịch không gây outage hàng loạt |
| **Provider semantics** | KMS auto-rotation thay material hay chỉ alias? | Xác định chính xác hành động cần có |

### 4.1. Mẫu minh họa về chính sách chu kỳ

Các giá trị sau là **ví dụ bài học**, không phải yêu cầu chung của NIST, ISO, PCI hay bất kỳ cơ quan nào. Mỗi tổ chức phải xây policy được phê duyệt dựa trên nguy cơ và tiêu chuẩn áp dụng.

| Key purpose | Chu kỳ thử nghiệm minh họa | Điều kiện bổ sung |
| --- | --- | --- |
| **JWT signing key** | Đánh giá và thay theo lịch nội bộ, chẳng hạn mỗi quý | Phát public key v2 trước cutover, expiry/token caches |
| **AES KEK cho envelope** | Đánh giá mỗi năm hoặc theo chính sách KMS | Phân biệt auto-material rotation và rewrap wrapped DEKs |
| **AES DEK per dataset** | Thay khi kết thúc một kỳ dữ liệu hoặc sớm hơn theo usage | AEAD nonce budget, volume và retention |
| **Shared HMAC webhook secret** | Thay theo lịch có phối hợp đối tác | Overlap hữu hạn, key ID, chống replay |
| **TLS server private key/certificate** | Theo certificate/PKI policy riêng | Có re-key thật hay chỉ reissue certificate? |
| **Ephemeral TLS traffic/session keys** | Theo handshake/rekey của giao thức | Không chạy scheduler ứng dụng để thay từng key phiên |

**Không lấy các chu kỳ ví dụ làm cấu hình production mặc định.** Đặc biệt, calendar-driven rotation **không được vượt** giới hạn do key usage/nonce hoặc chính sách khẩn cấp đặt ra.

### 4.2. Policy có thể đặt deadline từ nhiều nguồn

Một quy tắc có thể tính:

~~~text
rotationRequiredAt = thời điểm sớm nhất trong các giới hạn có hiệu lực:
  createdAt + maximumAgeFromCreation
  activatedAt + maximumActiveUsageDuration
  approvedAbsoluteCutoverDate
  cryptographicUsageLimitReached
  compliance/policyChangeDeadline
  incidentEmergencyDeadline
~~~

Các điều kiện này **không luôn cùng loại thời gian**: usage count và nonce exhaustion là **điều kiện**, không chỉ là Instant. Trong thực tế scheduler phải quan sát cả **clock** và **metrics/state events**, không chỉ chờ một cron job hằng đêm.

### 4.3. Tách lịch tạo khóa và lịch chuyển đổi

Nếu nhiều bên nhận cần chuẩn bị public key hoặc secret v2, cần có:

- **Preparation window:** Tạo v2, kiểm thử, cấp quyền và cập nhật verifiers.
- **Activation/cutover:** Thời điểm bắt đầu Sign/Encrypt/Wrap bằng v2.
- **Observation window:** Đảm bảo không còn writers/senders sử dụng v1 trái policy.
- **Historical-use window:** Cho Decrypt/Verify/Unwrap cũ theo policy.
- **Destruction eligibility:** Chỉ sau dependency review, retention và phê duyệt.

**Không lên lịch sinh v2 cùng giây với lúc v1 hết hạn** nếu còn PKI/JWKS caches, đối tác offline hoặc quy trình thẩm định HSM cần hoàn tất trước.

## 5. Rotation theo lịch và rotation theo sự kiện

**Time-based rotation** là **planned/proactive control**. **Event-driven rotation** là phản ứng với thay đổi trong hệ thống hoặc rủi ro. Hệ thống đáng tin cậy thường kết hợp cả hai.

| Tín hiệu | Loại | Cách xử lý |
| --- | --- | --- |
| Đến mốc cryptoperiod theo policy | Theo thời gian | Chuẩn bị cutover, thay vật liệu khóa và xác minh kết quả |
| Số Encrypt/bytes/nonce gần usage limit | Theo usage | Rotate sớm hơn deadline lịch |
| Key/certificate/algorithm không còn phù hợp | Theo chính sách | Migration thuật toán/độ mạnh và cập nhật consumers |
| Nhân viên/đối tác có quyền secret rời tổ chức | Theo thay đổi quyền/rủi ro | Thu hồi quyền, đánh giá cần rotate secret được chia sẻ |
| Phát hiện raw key leak | Khẩn cấp | Containment, key replacement, data/trust impact assessment |
| HSM/KMS principal bị chiếm | Khẩn cấp | Chặn grants, audit API abuse, cân nhắc rotate key theo phạm vi |
| Public trust/JWKS registry bị sửa trái phép | Khẩn cấp | Khôi phục trust source và điều tra chữ ký/key đã chấp nhận |
| DR failover sang vùng khác | Theo vận hành | Kiểm tra key availability/identity, không tự phát raw KEK |

### 5.1. Đến hạn và phát hiện compromise là hai đường quyết định khác nhau

Nếu private signing key bị lộ, không thể nói “đợi ba tháng nữa đến lịch rotation”. Cần **emergency revocation** theo mức rủi ro và kế hoạch phát public key mới.

Nếu chỉ đến hạn định kỳ và không có dấu hiệu lộ, có thể thiết kế **overlap hữu hạn** cho Verify cũ hoặc HMAC key trong thời gian chuyển tiếp, miễn đúng policy. **Không áp dụng cửa sổ chấp nhận khóa đã compromised** như planned rotation thông thường.

### 5.2. Rotation deadline phải được thực thi

Một cảnh báo “key overdue” là tín hiệu; **không tự ngăn writer dùng key cũ**. Cần quyết định rõ policy khi quá hạn:

- Chặn **Encrypt/Sign/Wrap mới** bằng material cũ sau mốc cưỡng chế nếu an toàn/kinh doanh yêu cầu.
- Duy trì **Decrypt/Verify/Unwrap lịch sử** theo chính sách.
- Báo động hoặc chuyển sang chế độ degradation an toàn, không bỏ bảo vệ.
- Cho phép exception **có owner, expiry, approval và audit**, không mở rộng vô thời hạn.

**Không tự fallback sang v1 đã bị revoke** khi v2/KMS lỗi. Sự cố availability phải được xử lý bằng HA/DR và runbook được phê duyệt.

## 6. State machine cho vòng đời rotation

Một hệ thống có thể dùng tên trạng thái khác nhau, nhưng cần **ngữ nghĩa rõ cho từng operation**.

~~~mermaid
stateDiagram-v2
    [*] --> PRE_ACTIVE: Sinh key và đăng ký metadata
    PRE_ACTIVE --> ACTIVE: Phê duyệt cutover
    ACTIVE --> RETIRED: Không dùng cho operation tạo mới
    ACTIVE --> SUSPENDED: Sự cố/điều tra
    SUSPENDED --> ACTIVE: Phê duyệt khôi phục khi an toàn
    SUSPENDED --> REVOKED: Xác nhận không còn được tin
    RETIRED --> REVOKED: Phát hiện compromise
    RETIRED --> DESTROY_PENDING: Hết dữ liệu/bằng chứng phụ thuộc
    REVOKED --> DESTROY_PENDING: Xác minh retention và recovery
    DESTROY_PENDING --> DESTROYED: Thực thi hủy và kiểm chứng
    DESTROYED --> [*]
~~~

**Sơ đồ chỉ mô tả mô hình policy**, không phải semantics mặc định của một KMS cụ thể. Các provider có thể có **Enabled/Disabled, PendingDeletion, PendingImport, Unavailable** hoặc trạng thái khác. Khi tích hợp, phải ánh xạ từng trạng thái thật sang những operation được phép.

### 6.1. Những quyền có thể thay đổi theo state

| State | Encrypt/Sign/Wrap mới | Decrypt/Verify/Unwrap lịch sử | Điều kiện |
| --- | --- | --- | --- |
| **PRE_ACTIVE** | Thường không | Chỉ test/provision theo phạm vi được duyệt | Chưa cutover |
| **ACTIVE** | Được phép theo IAM/purpose | Theo policy | Đúng key version, algorithm và principal |
| **RETIRED** | **Không** | Có thể được phép | Dữ liệu/chữ ký cũ và retention còn tồn tại |
| **SUSPENDED** | Chặn hoặc giới hạn | Tùy rủi ro và mục tiêu điều tra | Quyết định IR/Security |
| **REVOKED** | **Không** | Thường bị hạn chế; Verify lịch sử cần quy tắc riêng | Đã mất tin cậy hoặc không được phép |
| **DESTROY_PENDING** | **Không** | Chỉ đường phục hồi đặc biệt nếu được phê duyệt | Đang kiểm tra deletion/retention |
| **DESTROYED** | **Không** | Không thể dùng key material đã hủy qua backend đó | Chứng cứ hủy và bản sao cần đánh giá |

**Public verification key có thể còn cần để Verify chữ ký lịch sử sau khi private signing key đã destroy.** Ngược lại, khi private key bị compromised, verifier cần thêm **trust/revocation policy**; kết quả toán học Verify=true **không đủ để chấp nhận**.

### 6.2. Tách canCreate và canConsume

Một thiết kế tốt có thể định nghĩa hai quyết định:

~~~text
canCreateNewProtection(key, at, principal, purpose)
canConsumeHistoricalProtection(key, at, record, trustEvidence)
~~~

Trong đó:

- **Create** gồm Encrypt, Wrap, Sign hoặc tạo MAC mới.
- **Consume** gồm Decrypt, Unwrap, Verify hoặc kiểm tra MAC cũ theo profile.

Không dùng một hàm **isActive(key)** chung rồi cho cả tạo mới và đọc lịch sử; nó thường dẫn tới một trong hai lỗi: **mất dữ liệu cũ** hoặc **tiếp tục dùng khóa hết hạn để bảo vệ dữ liệu mới**.

### 6.3. Kích hoạt phải có mốc có thể kiểm toán

Một alias như **current-billing-signer** có thể trỏ sang key-v2 sau khi cutover. Nhưng alias chỉ là con trỏ; hệ thống cần lưu **key ID/version thực đã dùng cho từng chữ ký**. Nếu chỉ lưu alias, khi alias chuyển mục tiêu, có thể không xác định được khóa nào đã ký chứng từ cũ.

Với ciphertext, envelope cũng cần chứa **key version hoặc encrypted data key blob đủ để KMS biết phiên bản**, không chỉ chuỗi “current”.

## 7. Timeline triển khai một lượt rotation có kiểm soát

Thay vì chỉ có “ngày hết hạn”, hãy xem rotation như một **change procedure** gồm các pha.

~~~mermaid
flowchart TD
    DISCOVER["Inventory + dependency graph<br/>key ID, owner, consumers, backups"] --> POLICY["Đánh giá cryptoperiod, usage limits<br/>và phạm vi dữ liệu"]
    POLICY --> NEW["Sinh key material v2 trong ranh giới được duyệt"]
    NEW --> PREPARE["Chuẩn bị IAM/HSM policy,<br/>public trust, grants, code/schema"]
    PREPARE --> TEST["Test v2: Sign/Verify, Encrypt/Decrypt,<br/>KMS access và negative cases"]
    TEST --> GATE{"Approval + readiness<br/>đã đạt?"}
    GATE -->|"Chưa"| HOLD["Giữ v1 theo policy hiện hành;<br/>cảnh báo deadline và xử lý blocker"]
    HOLD --> PREPARE
    GATE -->|"Đạt"| CUTOVER["Atomic cutover: chỉ NEW operations dùng v2"]
    CUTOVER --> VERIFY["Readback: metadata, logs,<br/>consumer acknowledgements, error rates"]
    VERIFY --> DR{"Dữ liệu, backups, DR<br/>và readers lịch sử an toàn?"}
    DR -->|"Chưa"| MIGRATE["Rewrap/re-encrypt/điều chỉnh consumer<br/>theo phụ thuộc được xác minh"]
    MIGRATE --> VERIFY
    DR -->|"Đạt"| RETIRE["Retire v1 cho hoạt động tạo mới"]
    RETIRE --> DESTROY["Chỉ destroy khi đủ retention, approval<br/>và bằng chứng kiểm chứng"]
~~~

### 7.1. Pha 1 — Chuẩn bị

**Owner** lập danh sách:

- Đơn vị dùng khóa: services, pods, jobs, đối tác, mobile/offline clients.
- Key purpose và thuật toán: AES DEK, KMS KEK, signing, HMAC, TLS identity.
- Những nơi tham chiếu: alias, key resource ID, certificate/JWKS, API config.
- Dữ liệu/chữ ký phụ thuộc và tuổi thọ bản sao: database, object store, cache, backup, DR.
- Constraints: quota KMS, latency, key activation/certificate issuance và lịch thay đổi.

### 7.2. Pha 2 — Sinh và kiểm thử khóa mới

Key-v2 được tạo bằng **CSPRNG/KMS/HSM** có tham số/độ mạnh đúng. Không copy raw key-v1 rồi sửa tên hoặc chỉ reissue certificate khi policy yêu cầu **material mới**.

Chuẩn bị:

- **Least-privilege grants** cho đúng environment/workload/operation.
- Public verification key/certificate mới nếu có signing key rotation.
- Key ID/version mapping và policy validation.
- Kế hoạch trở lại trạng thái an toàn nếu v2 chưa thể dùng.

### 7.3. Pha 3 — Cutover

Đối với writer/signer, quyết định sử dụng khóa phải **dựa trên trạng thái có thẩm quyền**:

~~~text
Before T_cutover:  New Encrypt/Sign/Wrap uses key-v1 (if still allowed)
At/after T_cutover: New Encrypt/Sign/Wrap uses key-v2
Historical reads:   Resolve key version recorded with old data
~~~

Nếu hệ thống có nhiều instances, không cho mỗi instance tự đoán “current key” từ file config đã cache. Cần **atomic/consistently versioned control-plane state**, kiểm tra epoch hoặc cơ chế phối hợp phù hợp.

### 7.4. Pha 4 — Readback và đóng đợt

Một lần API Rotate thành công không chứng minh mọi workload đã chuyển. Cần:

- Lấy mẫu hoặc đối soát **dữ liệu mới chỉ dùng key-v2**.
- Kiểm tra tỷ lệ Sign/Encrypt/Wrap bằng v1 sau deadline.
- Test **Decrypt/Verify lịch sử** qua đúng version và dữ liệu thật đã được phép.
- Giám sát lỗi, latency, certificate chain và JWKS cache.
- Đối soát các jobs chậm, khách hàng offline, DR và backup.
- Ghi **change ID, cutover time, key ID/v1→v2, approval, validation result**.

**Không đánh dấu COMPLETED nếu một region hoặc một consumer quan trọng vẫn dùng v1 ngoài cửa sổ được phê duyệt.**

## 8. Originator-usage và recipient-usage trong rotation

Sự khác nhau giữa thời gian **tạo bảo vệ mới** và thời gian **xử lý dữ liệu cũ** là trọng tâm của quản lý cryptoperiod.

### 8.1. Đối với AES DEK

- **Originator use:** Encrypt payload bằng DEK.
- **Recipient use:** Decrypt ciphertext đã tạo bằng DEK.
- **Khi đến hạn:** Encrypt mới dưới DEK mới; dữ liệu cũ tiếp tục giải mã bằng DEK cũ nếu còn nằm trong retention và key vẫn được tin.

Nếu muốn hủy DEK cũ, cần **re-encrypt** dữ liệu dưới DEK mới hoặc xác nhận ciphertext không còn cần. Việc **rewrap cùng DEK cũ** bằng một KEK mới **không thay DEK** và không làm mất rủi ro của DEK cũ.

### 8.2. Đối với KEK

- **Originator use:** Wrap DEK mới bằng KEK.
- **Recipient use:** Unwrap những wrapped DEKs đã tạo.
- **Khi đến hạn:** Ngừng Wrap bằng KEK cũ; chọn KEK v2 cho wraps mới, nhưng không hủy KEK v1 nếu còn wrapped DEK cần đọc.

Một số KMS **automatic rotation** thay **material nội bộ của một logical KMS key** nhưng vẫn giải mã blobs cũ. Trong trường hợp đó, việc ứng dụng **không tự rewrap** mọi encrypted DEK có thể là hành vi đúng theo semantics provider. Cần kiểm tra dịch vụ thật, không suy ra từ nhãn “auto rotate”.

### 8.3. Đối với signing key

- **Originator use:** Tạo chữ ký mới bằng private signing key.
- **Recipient use:** Verify chữ ký trước đó bằng public verification key.
- **Khi đến hạn:** Sinh key pair v2, chỉ Sign mới bằng private v2; lưu public v1/certificate/evidence để Verify lịch sử theo chính sách.

**Private signer v1 không cần được giữ chỉ để xác minh chữ ký cũ**. Nhưng dữ liệu xác minh/timestamps/trust chain có thể cần giữ, và trạng thái compromise của v1 có thể ảnh hưởng đánh giá chữ ký lịch sử.

### 8.4. Đối với HMAC shared key

HMAC dùng **một secret** để tạo và kiểm tra MAC. Giai đoạn chuyển tiếp có thể cho phép verifier kiểm tra tag được tạo từ v1/v2, nhưng:

- Key ID/version phải có định tuyến rõ.
- Cửa sổ chấp nhận v1 phải **hữu hạn** trong planned rotation.
- Không thử mọi HMAC keys một cách vô hạn hoặc thiếu kiểm soát.
- HMAC chính nó **không chống replay**: cần timestamp/request ID/nonce được MAC và trạng thái chống lặp.
- Nếu secret v1 bị lộ, chấp nhận HMAC v1 tiếp tục tạo cơ hội cho giả mạo.

### 8.5. Đối với key agreement/traffic keys

Với TLS 1.3 hoặc các giao thức an toàn hiện đại, ephemeral key shares và traffic keys được thiết lập/theo dõi trong **giao thức phiên**. Scheduler thay KEK hay JWT signing key **không tự thay traffic keys của kết nối TLS đang sống**.

Đừng tự chèn cron job vào quá trình sinh key material của TLS để “rotate ephemeral keys hằng tháng”. Hãy dùng đúng **handshake/key update/session lifecycle** theo giao thức và cấu hình provider.

## 9. Rotation trong envelope encryption: KEK khác DEK

**Envelope encryption** tách hai lớp bảo vệ:

~~~text
Payload ciphertext = AEAD_Encrypt(DEK, plaintext, nonce, AAD)
Wrapped DEK        = Wrap(KEK, DEK)
Record metadata    = payloadAlg, nonce, tag, wrappedDEK, KEK ref/version, schema
~~~

Nếu cần thay KEK, có hai trường hợp thường nhầm lẫn:

### 9.1. Rewrap khi KEK đổi nhưng DEK vẫn được phép sử dụng

~~~text
Old: WrappedDEK_v1 = Wrap(KEK_v1, DEK_a)
New: WrappedDEK_v2 = Wrap(KEK_v2, DEK_a)
Payload ciphertext vẫn mã hóa bằng DEK_a
~~~

Lợi ích: có thể thay KEK hoặc KMS policy mà **không bắt buộc đọc lại toàn bộ payload** để mã hóa lại. Nhưng:

- **DEK_a không thay đổi**; nonce usage, dữ liệu lịch sử và raw DEK compromise vẫn như trước.
- Cần **atomic update** giữa wrappedDEK blob và KEK reference/version.
- Cần xử lý **backups/DR** chứa wrapped DEK v1.
- Nếu dùng **KMS ReEncrypt** với encrypted data key blob, đó có thể là re-encrypt **blob DEK**, không phải payload.

### 9.2. Re-encrypt khi chính DEK cần thay

~~~text
Old: C_old = AEAD_Encrypt(DEK_a, P, nonce_old, aad)
New: C_new = AEAD_Encrypt(DEK_b, P, nonce_new, aad_new)
New: WrappedDEK_b = Wrap(KEK_active, DEK_b)
~~~

Thao tác này đòi hỏi:

1. Quyền hợp lệ để mở dữ liệu cũ.
2. Sinh **DEK_b mới** bằng CSPRNG/KMS.
3. Giải mã **C_old**, chỉ dùng plaintext sau khi kiểm tra tag/AAD.
4. Mã hóa lại bằng DEK_b với nonce mới, schema/context phù hợp.
5. Ghi **C_new + nonce/tag + wrapped DEK_b + version** nhất quán.
6. Kiểm thử đọc và chỉ retire/hủy đường cũ khi đủ retention/backup evidence.

**Thay KEK không phải đáp án cho mọi trường hợp muốn giảm tuổi thọ DEK.** Hệ thống phải có **cryptoperiod riêng cho KEK và DEK**, cùng dependency graph giữa hai lớp.

### 9.3. KMS automatic rotation có thể không đổi ciphertext

Một dịch vụ có thể giữ logical key ID không đổi trong khi tự thay key material để **Encrypt/Wrap mới**, đồng thời lưu material cũ để Decrypt/Unwrap. Trái lại, một dịch vụ khác có thể yêu cầu tạo resource mới và rewrap dữ liệu.

Vì vậy cần kiểm tra:

- Auto rotation **thực sự thay material nào** và ở lớp nào?
- Existing wrapped DEK blobs có cần thay ngay không?
- Key ID/version nào được trả trong ciphertext hoặc metadata?
- Tính năng **Disable/Delete** ảnh hưởng toàn logical key hay chỉ một material version?
- Backup, multi-region và import/export có duy trì khả năng giải mã không?

**Không ghi trong policy “auto rotate KMS hằng năm = toàn bộ DEK và dữ liệu đã được mã hóa lại”** nếu nền tảng chỉ thay KEK material cho operation mới.

## 10. AES-GCM và usage limits: lịch không phải lá chắn cho nonce

Rotation theo thời gian là một phần của key hygiene, nhưng **AEAD nonce reuse** và giới hạn số phép mã hóa có thể xảy ra **trước deadline**.

### 10.1. Nonce phải duy nhất dưới cùng key

Với **AES-GCM**, nonce/IV **không được tái sử dụng dưới cùng DEK**. Nếu nhiều instances dùng chung một DEK và mỗi instance chạy counter từ 0, nonce collisions có thể xảy ra ngay trong ngày đầu tiên, dù chính sách sẽ rotate sau một tháng.

Các lựa chọn cần đánh giá:

- **DEK per object/message** theo threat model để hạn chế số phép Encrypt của cùng DEK.
- **Uniqueness scheme** phân vùng nonce/counter giữa writers theo giao thức đã được đánh giá.
- Giới hạn **max messages, max bytes và max time** đối với một DEK.
- Giám sát usage và rotate trước ngưỡng; không đợi cron job nếu sắp vượt giới hạn.

**Rewrap KEK không reset nonce budget của DEK**, vì DEK không thay.

### 10.2. Dùng nonce ngẫu nhiên vẫn cần ngân sách xác suất va chạm

Nonce ngẫu nhiên 96-bit cho AES-GCM thường được dùng trong nhiều ví dụ. Nhưng độ an toàn phụ thuộc **số lần dùng một key, khả năng phân phối CSPRNG, rủi ro trùng nonce và giới hạn bảo mật của mode**.

Không thể kết luận “mỗi lần Encrypt tự random nonce nên không bao giờ trùng”. Với lưu lượng lớn và lifetime dài, thiết kế phải tính toán/giới hạn đúng chuẩn áp dụng hoặc chuyển mô hình DEK.

### 10.3. Rotation phải có mốc ngắn hơn giới hạn usage

Một quy tắc thực thi có thể là:

~~~text
Rotate when:
    now >= scheduledCutover
 OR encryptCount >= allowedCount
 OR encryptedBytes >= allowedBytes
 OR nonceAllocator signals exhaustion
 OR risk/incident forces emergency rotation
~~~

Thực tế **allowedCount/allowedBytes** phụ thuộc primitive, mode, nonce construction, threat model và tiêu chuẩn; không dùng một con số ngẫu nhiên. KMS/cryptographic provider có thể có limits riêng.

### 10.4. Rotation không tự khôi phục thông điệp đã bị sửa/giải mã

Nếu attacker đã lợi dụng nonce reuse làm lộ thông tin hay giả mạo tag của ciphertext cũ, thay DEK từ ngày mai **không sửa được dữ liệu cũ**. Cần điều tra phạm vi, xác minh/integrity lại dữ liệu theo khả năng, cân nhắc re-encrypt và thông báo theo chính sách.

## 11. Rotation của chữ ký số, JWT/JWKS và chứng chỉ TLS

Thay signing key theo thời gian không chỉ là đổi private key. **Public verification key phải được phân phối và tin cậy đúng cách**, còn chữ ký/token cũ cần chính sách xử lý độc lập.

### 11.1. Planned signing-key rotation

Một quy trình đề xuất:

1. **Tạo private/public signing pair v2** bằng thuật toán/cường độ được phê duyệt; private key ở KMS/HSM nếu policy yêu cầu.
2. **Đăng ký public verification key v2** vào PKI, certificate registry hoặc JWKS issuer **trước cutover**.
3. **Verifier readiness:** Kiểm tra các bên nhận có nguồn trust và có thể Verify v2; đo cache TTL, đồng bộ regions và đối tác.
4. **Cutover:** Sign mới chỉ bằng private v2; ghi **key ID/version** trên message/token hoặc metadata.
5. **Observe:** Theo dõi lỗi Verify, tỷ lệ Sign bằng v1 sau cutover, những consumer chưa cập nhật.
6. **Retire private v1:** Cấm Sign mới; giữ public v1 cho Verify lịch sử khi policy và tình trạng tin cậy cho phép.
7. **Destroy private v1** sau approval và xác nhận hết nhu cầu ký hợp lệ; giữ verification evidence theo retention.

~~~mermaid
sequenceDiagram
    participant AO as Application owner
    participant HSM as KMS/HSM signer
    participant TRUST as PKI / JWKS registry
    participant V as Verifier / partner
    AO->>HSM: Tạo signing key pair v2
    HSM-->>AO: Key ID v2 + public material
    AO->>TRUST: Đăng ký trusted public key v2
    V->>TRUST: Refresh và xác thực issuer/key v2
    TRUST-->>V: Public key v2
    V-->>AO: Readiness/ack v2 nếu quy trình yêu cầu
    AO->>HSM: Cutover Sign mới từ v1 sang v2
    HSM-->>V: Signed message + key ID v2
    V->>V: Verify v2 và kiểm tra issuer/audience/purpose
    AO->>HSM: Retire private v1 cho Sign mới
    Note over AO,V: Verify v1 lịch sử và revocation theo policy riêng
~~~

### 11.2. JWT rotation không đồng nghĩa thu hồi mọi JWT đã ký

Một JWT được ký bằng key-v1 có thể còn hiệu lực theo **exp/aud/iss** khi signer đã chuyển sang v2. Với planned rotation, issuer có thể giữ public-v1 trong JWKS để verifier kiểm tra token chưa hết hạn.

Nhưng khi private-v1 bị **compromised**, attacker có thể tạo JWT có chữ ký toán học hợp lệ. Chỉ đổi private signer sang v2 **không khiến JWT giả v1 bị từ chối** ở các verifier còn tin v1. Cần kế hoạch **key revocation, cache invalidation, token/session invalidation và scope assessment** theo sự cố.

**Không lấy JWT header kid làm nguồn trust.** Verifier phải giới hạn issuer và allowed algorithms từ cấu hình đáng tin cậy; khi v1 bị revoked, không fallback nhận token ký bằng v1 chỉ vì JWKS cache lỗi.

### 11.3. Certificate renewal không luôn sinh new key pair

Với chứng chỉ TLS, cần phân biệt:

- **Renew/reissue certificate với cùng key pair:** Certificate bytes/serial/validity thay, nhưng private material không đổi.
- **Rekey:** Sinh key pair mới và phát hành certificate phù hợp; thực sự thay private material.
- **Trust anchor rotation:** Thay CA/intermediate hoặc trust roots; ảnh hưởng chain validation ngoài leaf certificate.

Nếu policy yêu cầu thay private key theo thời gian, **đếm số lần renew certificate là không đủ**. Cần bằng chứng key pair mới, key ID/fingerprint mới và app đang dùng nó.

### 11.4. Application reload và kết nối đang mở

Thay file keystore hoặc secret version trên disk không bảo đảm:

- JVM đã reload **KeyManager/SSLContext**.
- Các kết nối TLS cũ tự động được thiết lập lại bằng certificate v2.
- Load balancer, sidecar hoặc proxy đã cập nhật private key/cert.
- Các clients đã cập nhật trust anchors/pins.

Runbook phải kiểm tra **handshakes mới, certificate presented, service identity và mTLS authorization**, đồng thời tính đến connection draining hoặc restart có kiểm soát.

### 11.5. Chữ ký số dài hạn và timestamp

Với chứng từ cần Verify nhiều năm, planned signing rotation phải giữ:

- **Original signed bytes** và signature bytes.
- Public verification key/certificate chain tương ứng với thời điểm.
- Thông tin **thời điểm ký đáng tin cậy** khi profile yêu cầu.
- Revocation/certificate validation evidence, algorithm profile và trust policy lịch sử.

Không tự coi timestamp nằm trong message đã ký là **trusted timestamp**: nếu private key bị lộ, attacker có thể tạo một chữ ký giả với trường thời gian tự khai. Cần mô hình chứng cứ thích hợp.

## 12. Rotation của MAC/shared secret giữa nhiều bên

Với HMAC hoặc secret dùng chung giữa service và đối tác, **cả bên tạo lẫn bên kiểm tra MAC đều biết raw secret**. Rotation yêu cầu sự phối hợp khó hơn public-key Verify vì không thể công bố một “public HMAC key”.

### 12.1. Phân phối v2 cho đúng người nhận

Quy trình có thể gồm:

- Tạo **MAC key-v2 mới** bằng CSPRNG/secret manager, tách dev/test/prod và từng đối tác khi cần.
- Phân phối qua **kênh xác thực và cơ chế bảo vệ được phê duyệt**; không gửi Base64 raw key qua email tùy tiện.
- Mỗi bên xác minh **key ID/version, purpose, activation date, expiry/overlap**.
- Gửi acknowledgement mà không tiết lộ raw key.
- Chuyển bên tạo MAC sang v2 theo mốc cutover; verifier chọn key theo **authenticated key ID/context** và thời hạn cho phép.

### 12.2. Khoảng chấp nhận song song có giới hạn

Trong planned rotation, một verifier có thể tạm chấp nhận HMAC-v1 cho các thông điệp **thật sự được tạo trước cutover** và HMAC-v2 cho thông điệp mới, tùy giao thức.

**Lưu ý:** Nếu thông điệp không mang key ID/timestamp/nonce được MAC và không có anti-replay state, chỉ cho phép “thử cả v1 và v2” có thể khiến attacker phát lại thông điệp cũ hoặc che giấu việc bên gửi chưa chuyển khóa.

Quy định:

1. Key ID là nhãn routing, phải được ràng buộc với **nội dung đã MAC hoặc context đáng tin cậy**.
2. Thời gian overlap có deadline tuyệt đối.
3. Các bên gửi không được tiếp tục tạo MAC v1 sau cutover.
4. Replay/idempotency checks vẫn được áp dụng.
5. Khi v1 bị compromised, xử lý **emergency cutoff** thay vì planned overlap.

### 12.3. Vì sao không giữ v1 “để tương thích mãi mãi”?

Nếu verifier luôn chấp nhận MAC-v1, attacker còn biết secret-v1 vẫn có thể tạo tag hợp lệ. Rotation **không giảm phạm vi rủi ro quá khứ** nếu quá trình xác minh cứ chấp nhận khóa cũ vô thời hạn.

Khi một đối tác không thể chuyển đúng hạn, cần **exception có approval và phạm vi rõ**, hoặc cơ chế chuyển giao nghiệp vụ được đánh giá; không âm thầm mở rộng thời gian.

## 13. Thiết kế scheduler rotation an toàn

Scheduler là cơ chế kích hoạt; **nó không phải authority duy nhất** quyết định một khóa có được dùng. Quyền sử dụng phải được thực thi bởi **key state/policy và nơi thực hiện cryptographic operation**.

### 13.1. Kiến trúc phối hợp

~~~mermaid
flowchart LR
    INVENTORY["Key inventory<br/>createdAt, activatedAt, deadline, state"] --> SCHED["Rotation scheduler<br/>time + usage signals"]
    METRICS["Usage/nonce/incident signals"] --> SCHED
    SCHED --> PLAN["Change request + policy validation"]
    PLAN --> LOCK["Rotation lease / idempotency key"]
    LOCK --> PROVISION["KMS/HSM Generate key-v2"]
    PROVISION --> APPROVAL["Approval + readiness gate"]
    APPROVAL --> CUTOVER["Atomic active-version update"]
    CUTOVER --> APPS["Writers / Signers / Consumers"]
    APPS --> VERIFY["Readback, negative tests, telemetry"]
    VERIFY --> RETIRE["Retire old for new operations"]
    RETIRE --> INVENTORY
    VERIFY --> AUDIT["Audit + incident/change record"]
~~~

Một hệ thống có thể chọn **timer/cron, workflow engine, event bus hoặc KMS managed rotation**; cần chứng minh những điều sau:

- **Không có hai rotations cạnh tranh** tạo v2 và v3 bất ngờ vì scheduler chạy lặp.
- **Retry idempotent** sau timeout, partial success hoặc leader failover.
- **Atomic/consistent cutover** giữa version và policy theo backend.
- **Readback verification** xác nhận mọi writer/signer đã chuyển.
- **Out-of-band trigger** khi key bị lộ hoặc usage limit sắp vượt.
- **Audit approval** cho những bước nhạy cảm như Delete/ChangePolicy.

### 13.2. Không dùng alias mutable làm toàn bộ lịch sử

Alias như **current-data-kek** hoặc **current-jwt-signer** hữu ích cho **Encrypt/Sign mới**, nhưng nếu ciphertext hoặc chữ ký cũ chỉ lưu alias đó, sau khi alias chuyển sang v2 có thể không biết **version nào đã được dùng**.

Định dạng nên lưu:

~~~json
{
  "recordId": "invoice-42",
  "envelopeVersion": 2,
  "algorithm": "AES-256-GCM",
  "keyRef": "kek-resource-id",
  "keyMaterialVersion": "v3-or-provider-opaque-reference",
  "nonce": "base64-of-nonce",
  "wrappedDek": "base64-of-encrypted-data-key",
  "ciphertextAndTag": "base64-of-payload"
}
~~~

**Đây là ví dụ metadata, không phải schema một KMS cụ thể.** Một số managed KMS lưu version nội bộ trong ciphertext blob, nên ứng dụng không nhất thiết nhận field version vật liệu; inventory và API phải phản ánh semantics thật. Không tự tạo field giả rồi cho rằng provider có thể giải mã dựa trên giá trị đó.

### 13.3. Idempotency khi job chạy lặp

Giả sử scheduler chạy lúc 00:00, tạo key-v2 nhưng mất kết nối trước khi lưu trạng thái. Lần chạy lại lúc 00:05 không nên tự tạo key-v3 chỉ vì **status local chưa cập nhật**.

Một thiết kế hợp lý:

- **rotationRequestId** ổn định cho cùng key và kỳ rotation.
- **Lease/lock có giới hạn** để một leader thực thi tại một thời điểm.
- Reconcile với KMS/HSM bằng **resource references**, không chỉ dựa local memory.
- Nếu key-v2 đã tồn tại, kiểm tra **algorithm/owner/purpose/state** trước khi tiếp tục.
- Chỉ cutover khi **approval/readiness** còn hiệu lực.
- CAS/optimistic concurrency khi đổi **activeVersion**.
- Lưu audit ngay cả với các lần retry bị từ chối.

### 13.4. Clock, timezone và DST

Một lỗi phổ biến là thiết kế “rotate vào ngày 1 hằng tháng lúc 00:00” nhưng các server dùng timezone khác nhau hoặc thời điểm DST bị nhảy/trùng.

Khuyến nghị thiết kế:

- Lưu **Instant UTC** cho createdAt, activatedAt, nextDueAt và effectiveCutover.
- Nếu nghiệp vụ cần “đầu tháng tại một múi giờ”, hãy lưu **ZoneId và lịch calendar rõ ràng**, chuyển thành Instant một lần cho từng kỳ.
- Quy định cách xử lý giờ **không tồn tại hoặc lặp** khi DST; không dựa vào cấu hình timezone ngầm của container.
- Dùng **Clock** tiêm vào code để có thể test chính xác các mốc.
- Phân biệt **Duration** (khoảng thời gian thực) với **Period** (tháng/năm theo lịch). Không mặc định một “tháng” là 30 ngày nếu policy nói đầu tháng lịch.

Việt Nam hiện dùng Asia/Ho_Chi_Minh (UTC+07:00), nhưng hệ thống đa vùng vẫn nên lưu UTC và không thiết kế phụ thuộc một server có timezone cố định.

### 13.5. Time source và clock drift

Một scheduler dùng đồng hồ local bị lệch có thể thực hiện cutover quá sớm hoặc quá muộn. Khi key state có tính pháp lý/độ nhạy cao:

- Đồng bộ NTP và giám sát clock drift.
- Lấy thời gian effective từ **control plane có thẩm quyền**.
- Tránh phụ thuộc vào thông điệp timestamp do client chưa xác thực cung cấp.
- Dùng version/epoch để bảo đảm monotonic cutover dù có failover.
- Nếu thời gian không đáng tin, fail safely và báo động theo policy; không tự chọn phiên bản ngẫu nhiên.

## 14. Mẫu policy/inventory cho rotation theo thời gian

Một bản policy nên xác định **mốc, hoạt động được phép và hành động khi quá hạn**, không chỉ một số nguyên **rotationDays**.

~~~yaml
# MẪU KHÁI NIỆM - không phải cấu hình API KMS cụ thể.
keyId: billing-data-kek
owner: billing-platform
environment: production
purpose: wrap-invoice-dek
algorithmPolicy: approved-aes-key-wrapping
rotationPolicy:
  policyId: billing-kek-rotation-v2
  basis: activation-time
  plannedInterval: P6M           # 6 tháng lịch; chỉ là ví dụ nội bộ
  zone: UTC
  prepareBefore: P14D
  usageLimitRequired: true       # giới hạn thực phải cấu hình riêng
  incidentOverride: true
  overdueBehavior: block-new-wrap
  historicalUnwrap: allow-if-retired-and-authorized
  requireApproval: true
  requireDRReadback: true
  destructionRequiresDependencyReview: true
activeKey:
  resourceRef: kms/billing/kek-v3
  materialVersion: provider-specific
  activatedAt: "2026-09-01T00:00:00Z"
  state: ACTIVE
pendingKey:
  resourceRef: kms/billing/kek-v4
  state: PRE_ACTIVE
  cutoverPlannedAt: "2027-03-01T00:00:00Z"
audit:
  recordPrincipalKeyVersionResult: true
  neverLogRawKey: true
~~~

**Lưu ý:** P6M ở đây là **six-month calendar period**, còn **prepareBefore=P14D** là duration/period theo cách triển khai của policy engine. Các trường đều là **minh họa**; không được copy thẳng vào KMS SDK và cho rằng KMS tự áp dụng.

### 14.1. Những trường cần có trong inventory thực

Ngoài policy ở trên, inventory nên theo dõi:

- **Previous/current/next key references** với version thực.
- **Creation/activation/retire/revoke/deletion timestamps** và sự khác nhau giữa planned/actual.
- **Data dependencies**: encrypted objects, wrapped DEKs, client JWKS caches, certificates, backups.
- **IAM grants/consumers** và region/tenant ownership.
- **KMS provider semantics**: auto-material rotation, key ID alias rules, deletion waiting period.
- **Change/incident ID, approvers, cutover acknowledgement và test evidence**.

**Không lưu raw KEK, DEK, HMAC secret hoặc private signing key** trong policy/inventory; đó là metadata và bằng chứng quản trị, không phải một secret store mới.

## 15. Java 17: quyết định một key đã đến hạn rotation hay chưa

Đoạn Java sau minh họa **policy gate cho việc tạo bảo vệ mới**. Nó không sinh private signing key, không gọi KMS và không thay thế control plane, mà thể hiện cách:

- Sử dụng **Clock** và **Instant** để test tại đúng thời điểm deadline.
- Phân biệt **ACTIVE** với **RETIRED/REVOKED**.
- Xét **thời hạn** và **usage limits**; chỉ cần một điều kiện đạt ngưỡng là phải dừng tạo mới.
- Không tự động dùng khóa cũ khi key mới chưa sẵn sàng.
- Giữ quyết định **Decrypt/Verify lịch sử** riêng với quyền Encrypt/Sign mới.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public final class RotationPolicyDemo {
    private RotationPolicyDemo() {}

    enum State { PRE_ACTIVE, ACTIVE, RETIRED, SUSPENDED, REVOKED }

    record KeyVersion(
            String keyId,
            String purpose,
            State state,
            Instant activatedAt,
            Instant originatorUseEndsAt,
            boolean historicalUseApproved
    ) {}

    record UsageSnapshot(
            long encryptOperations,
            long encryptedBytes
    ) {}

    record UsagePolicy(
            long maximumEncryptOperations,
            long maximumEncryptedBytes
    ) {}

    record Decision(
            boolean allowNewEncryption,
            boolean rotationRequired,
            String reason
    ) {}

    static Decision evaluateNewEncryption(
            KeyVersion key,
            UsageSnapshot usage,
            UsagePolicy limits,
            Clock clock
    ) {
        Objects.requireNonNull(key);
        Objects.requireNonNull(usage);
        Objects.requireNonNull(limits);
        Objects.requireNonNull(clock);
        Instant now = clock.instant();

        if (!"invoice-data-encryption".equals(key.purpose())) {
            return new Decision(false, false, "PURPOSE_MISMATCH");
        }
        if (key.state() != State.ACTIVE) {
            return new Decision(false, false, "NOT_ACTIVE");
        }
        if (key.activatedAt() == null ||
                now.isBefore(key.activatedAt())) {
            return new Decision(false, false, "NOT_YET_EFFECTIVE");
        }
        if (key.originatorUseEndsAt() == null ||
                !now.isBefore(key.originatorUseEndsAt())) {
            return new Decision(false, true, "CRYPTOPERIOD_ENDED");
        }
        if (usage.encryptOperations() < 0 ||
                usage.encryptedBytes() < 0 ||
                limits.maximumEncryptOperations() <= 0 ||
                limits.maximumEncryptedBytes() <= 0) {
            return new Decision(false, false, "INVALID_USAGE_METADATA");
        }
        if (usage.encryptOperations() >=
                limits.maximumEncryptOperations() ||
                usage.encryptedBytes() >= limits.maximumEncryptedBytes()) {
            return new Decision(false, true, "USAGE_LIMIT_REACHED");
        }
        return new Decision(true, false, "ALLOWED");
    }

    static boolean allowHistoricalDecryption(
            KeyVersion key,
            boolean callerAuthorizedForRecord
    ) {
        return callerAuthorizedForRecord &&
                key.historicalUseApproved() &&
                (key.state() == State.ACTIVE ||
                 key.state() == State.RETIRED);
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-28T00:00:00Z"),
                ZoneOffset.UTC);
        Instant activation = Instant.parse("2026-05-28T00:00:00Z");
        Instant deadline = activation.plus(Duration.ofDays(184));

        KeyVersion v1 = new KeyVersion(
                "invoice-dek-v1", "invoice-data-encryption",
                State.ACTIVE, activation, deadline, true);

        UsagePolicy limits = new UsagePolicy(
                100_000, 1_000_000_000L); // Chỉ là ngưỡng demo.
        UsageSnapshot used = new UsageSnapshot(1000, 4096);

        Decision atDeadline = evaluateNewEncryption(
                v1, used, limits, clock);
        System.out.println("New Encrypt allowed: " +
                atDeadline.allowNewEncryption());
        System.out.println("Rotation required: " +
                atDeadline.rotationRequired());
        System.out.println("Decision: " + atDeadline.reason());

        KeyVersion retired = new KeyVersion(
                v1.keyId(), v1.purpose(), State.RETIRED,
                v1.activatedAt(), v1.originatorUseEndsAt(), true);
        System.out.println("Historical Decrypt allowed: " +
                allowHistoricalDecryption(retired, true));
        System.out.println("Unauthorized Decrypt allowed: " +
                allowHistoricalDecryption(retired, false));
    }
}
~~~

**Điểm cần nhận ra:** Đoạn mã cố ý dùng **184 ngày** thay vì gọi đó là “6 tháng” bởi **Duration** tính ngày/giây, còn **calendar period** phải được tính qua date/time API với ZoneId phù hợp. Mốc deadline phải được **policy engine lập và lưu trước**, không để mỗi request tự diễn giải lại chu kỳ theo timezone ngầm.

### 15.1. Lưu ý về kết quả chạy tại mốc ví dụ

Trong ví dụ, activation là **2026-05-28T00:00:00Z**, cộng **184 ngày** thì deadline là **2026-11-28T00:00:00Z**. Đồng hồ cố định đúng tại deadline, điều kiện **now.isBefore(endAt)** không còn đúng.

Kết quả dự kiến:

~~~text
New Encrypt allowed: false
Rotation required: true
Decision: CRYPTOPERIOD_ENDED
Historical Decrypt allowed: true
Unauthorized Decrypt allowed: false
~~~

Một ứng dụng có thể dùng policy yêu cầu **ngừng Encrypt** đúng tại deadline, trong khi vẫn **Decrypt dữ liệu cũ** nếu caller được phép và key RETIRED vẫn được giữ hợp lệ. Không có suy luận nào cho rằng bất kỳ key bị REVOKED cũng được Decrypt.

### 15.2. Vì sao code không tự gọi Rotate?

Một hàm **evaluateNewEncryption** chỉ quyết định có cho phép một thao tác hay không. Việc tạo/kích hoạt key mới cần:

- **Idempotent rotation workflow**, approval và khóa chống cạnh tranh.
- KMS/HSM CreateKey/GenerateDataKey theo loại vật liệu.
- Key policy, grant và trạng thái PRE_ACTIVE/ACTIVE.
- Consumer/readiness validation và audit.
- Tương tác với vùng/instance đang chạy.

Nếu để từng request Java tự “gặp deadline thì generate một key”, nhiều requests đồng thời có thể tạo hàng loạt keys không có inventory hoặc mapping nhất quán.

### 15.3. Hạn chế của mô hình minh họa

1. **UsageSnapshot không atomic** với Encrypt. Production phải đồng bộ usage budget hoặc dùng provider/encryption service bảo đảm không vượt ngưỡng do concurrency.
2. **Một lần Encrypt có thể vượt max bytes** dù count trước đó còn nhỏ; cần dự báo bytes sắp mã hóa, giới hạn input và cơ chế reserve/commit.
3. **Historical Decrypt** còn phải chọn đúng key version từ envelope, kiểm tra tenant/resource authorization và AEAD tag/AAD. Boolean trên chỉ là một policy gate.
4. **KeyState có thể không hoàn toàn khớp trạng thái backend**. Phải đối soát KMS/HSM state và IAM, không chỉ tin record local.
5. **Duration.ofDays** không thay thế lịch theo tháng/năm hay chính sách compliance.
6. **Không có cơ chế nonce allocation hoặc key material** trong ví dụ; đây là bài minh họa về deadline, không phải AES service.

## 16. Java 17: chọn key version khi Encrypt mới và Decrypt cũ

Một yêu cầu quan trọng khác là **key version affinity**: ciphertext được mã hóa dưới v1 phải được đọc bằng v1 cho đến khi được re-encrypt, dù **Encrypt mới** đã chuyển sang v2.

Ví dụ này dùng **AES-GCM** với key-v1/key-v2 mới sinh trong bộ nhớ để cho thấy bản chất của version routing. **Không sử dụng làm code quản lý KEK production**: keys trong ví dụ nằm trong JVM, không có persistence, IAM hay KMS wrapping.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Map;
import java.util.Set;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class VersionedAeadDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private VersionedAeadDemo() {}

    record Envelope(
            String keyVersion,
            byte[] nonce,
            byte[] ciphertextAndTag
    ) {}

    static SecretKey freshAes256() throws Exception {
        KeyGenerator gen = KeyGenerator.getInstance("AES");
        gen.init(256, RNG);
        return gen.generateKey();
    }

    static Envelope encryptNew(
            String activeVersion,
            byte[] plaintext,
            byte[] trustedAad,
            Map<String, SecretKey> keys,
            Set<String> allowedNewVersions
    ) throws Exception {
        if (!allowedNewVersions.contains(activeVersion)) {
            throw new SecurityException("Key not active for Encrypt");
        }
        SecretKey dek = keys.get(activeVersion);
        if (dek == null) {
            throw new SecurityException("Unknown active key");
        }
        byte[] nonce = new byte[12];
        RNG.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(trustedAad);
        return new Envelope(
                activeVersion, nonce, cipher.doFinal(plaintext));
    }

    static byte[] decryptHistorical(
            Envelope saved,
            byte[] expectedTrustedAad,
            Map<String, SecretKey> keys,
            Set<String> historicalReadVersions,
            boolean callerAuthorized
    ) throws Exception {
        if (!callerAuthorized ||
                !historicalReadVersions.contains(saved.keyVersion()) ||
                saved.nonce().length != 12) {
            throw new SecurityException("Historical read denied");
        }
        SecretKey dek = keys.get(saved.keyVersion());
        if (dek == null) {
            throw new SecurityException("Missing historical key");
        }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(128, saved.nonce()));
        cipher.updateAAD(expectedTrustedAad);
        return cipher.doFinal(saved.ciphertextAndTag());
    }

    public static void main(String[] args) throws Exception {
        SecretKey v1 = freshAes256();
        SecretKey v2 = freshAes256();
        Map<String, SecretKey> inventory = Map.of(
                "dek-v1", v1, "dek-v2", v2);
        byte[] aad = "tenant-a/invoice-42/purpose=invoice-v1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Hoa don cu"
                .getBytes(StandardCharsets.UTF_8);

        // Trước cutover: chỉ Encrypt mới bằng v1.
        Envelope oldRecord = encryptNew(
                "dek-v1", plaintext, aad, inventory, Set.of("dek-v1"));

        // Sau cutover: chỉ Encrypt mới bằng v2, nhưng vẫn đọc v1.
        Envelope newRecord = encryptNew(
                "dek-v2", plaintext, aad, inventory, Set.of("dek-v2"));

        byte[] oldPlain = decryptHistorical(
                oldRecord, aad, inventory, Set.of("dek-v1", "dek-v2"), true);
        byte[] newPlain = decryptHistorical(
                newRecord, aad, inventory, Set.of("dek-v1", "dek-v2"), true);

        System.out.println("Old version: " + oldRecord.keyVersion());
        System.out.println("New version: " + newRecord.keyVersion());
        System.out.println("Old readable: " +
                java.util.Arrays.equals(plaintext, oldPlain));
        System.out.println("New readable: " +
                java.util.Arrays.equals(plaintext, newPlain));
    }
}
~~~

Kết quả dự kiến:

~~~text
Old version: dek-v1
New version: dek-v2
Old readable: true
New readable: true
~~~

### 16.1. Từ demo đến production

Trong môi trường thật:

- **DEK không nên được nhét vào Map dùng chung vô hạn**. Có thể dùng wrapped DEK cạnh ciphertext, KEK trong KMS/HSM và quyền Unwrap giới hạn.
- **Key reference/version cần được bảo vệ tính toàn vẹn** và kiểm tra nằm trong allowlist/tenant scope; không tin hoàn toàn chuỗi do client đưa vào.
- **AAD phải được tạo từ metadata đã xác thực** (tenant/record/purpose), không lấy từ một request chưa có quyền.
- **Nonce uniqueness dưới cùng DEK** phải được quản lý với usage limits và concurrency.
- **Map và Set trong demo không phải policy authority bền vững**; dùng control plane/IAM/KMS state có chứng cứ.
- **Record byte arrays có thể bị sửa**; production cần immutable envelopes/defensive copying, giới hạn kích thước và parser an toàn.
- **Retire v1 không đồng nghĩa có thể xóa key-v1 ngay**; chỉ sau khi dữ liệu cũ được re-encrypt hoặc hết nghĩa vụ lưu trữ.
- **AEADBadTagException** phải dẫn tới từ chối plaintext; không retry dưới key khác hoặc bỏ AAD để làm cho Decrypt thành công.

### 16.2. Rotation theo thời gian và re-encryption khác lịch

Code này **chỉ đổi key cho dữ liệu mới**. Nếu policy yêu cầu “sau một năm, toàn bộ ciphertext cũng phải được re-encrypt bằng DEK mới”, đó là **một migration job riêng**:

1. Tìm record tham chiếu DEK-v1.
2. Giải mã theo quyền và kiểm tra tag/AAD.
3. Sinh/vận hành DEK-v2 theo policy với nonce mới.
4. Ghi envelope mới bằng transaction/optimistic version lock.
5. Đọc lại và đối soát backups/DR.
6. Chỉ xóa DEK-v1 khi dependency review đạt.

**Không coi job đổi alias Encrypt mới là bằng chứng mọi dữ liệu đã được re-encrypt.**

## 17. Multi-tenant, multi-region và rotation đồng thời

Một ứng dụng có hàng trăm tenants và nhiều regions có thể cùng chạy rotation; nếu không định nghĩa **scope**, một lần thay khóa có thể dẫn tới gián đoạn diện rộng hoặc tenant này dùng nhầm key của tenant khác.

### 17.1. Chọn phạm vi policy và vật liệu khóa

| Mô hình | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| **DEK per object/record** | Dễ giới hạn blast radius và vòng đời từng object | Nhiều wrapped DEKs, metadata và unwrap calls |
| **DEK per tenant** | Dễ lên lịch/thu hồi theo tenant | Nonce/usage và dữ liệu phụ thuộc lớn hơn |
| **DEK per batch/data domain** | Cân bằng chi phí và mức cô lập | Cần mapping rõ record → DEK version |
| **KEK riêng per tenant/domain** | IAM/KMS scope riêng, có thể migrate theo miền | Nhiều key resources/policies, chi phí vận hành |
| **Shared KEK với context và grants chặt** | Ít key resources hơn | Blast radius lớn hơn, authorization rất quan trọng |
| **Signing pair per issuer/purpose** | Ít nhầm JWT/receipt/release keys | Cần quản lý nhiều public key versions và consumer rollouts |

Không có yêu cầu tuyệt đối “mỗi tenant phải rotate một tháng một lần”. Lựa chọn **cryptoperiod và phạm vi khóa** phải xuất phát từ threat model, retention, đặc tính thuật toán và khả năng vận hành.

### 17.2. Avoid thundering herd tại cùng deadline

Nếu tất cả tenants có lịch **ngày 1 hằng tháng lúc 00:00**, scheduler có thể đồng thời tạo hàng nghìn KMS keys, gọi unwrap/re-encrypt quá lớn, gặp quota/throttling và gây outage.

Nên:

- Phân bố **preparation windows** và migration workloads qua các khoảng được policy cho phép.
- Giới hạn concurrency, tốc độ KMS/DB và có retry/backoff có kiểm soát.
- Ưu tiên những keys **gần usage limit, bị nghi lộ hoặc có dependency lớn**.
- Dùng **deadline tuyệt đối**: scheduling jitter không được đẩy vật liệu cũ vượt thời hạn cưỡng chế.
- Tách **cutover** thường nhanh với **rewrap/re-encrypt backlog** vốn có thể kéo dài.
- Giám sát phần việc chưa hoàn tất, không tuyên bố mọi tenants đã rotate chỉ vì scheduler không còn job mới.

### 17.3. Cross-region consistency

Trong hệ thống multi-region, một region có thể đã chuyển writer sang v2 trong khi region khác vẫn cache v1. Khi yêu cầu chính sách là cutover toàn cục:

1. Phát **policy/version epoch** từ nguồn có thẩm quyền.
2. Xác minh v2 được tạo, cấp quyền và có thể dùng ở các regions cần thiết.
3. Chặn hoạt động **Create bằng v1** sau khi epoch có hiệu lực.
4. Ghi key version **vật liệu thực đã sử dụng** cạnh ciphertext/signature.
5. Phát hiện các instances bị cách ly mạng hoặc giữ cache cũ.
6. Không bỏ qua sự khác biệt **KMS regional keys/replication semantics**; không mặc định cùng alias có cùng key material ở mọi region.

**Consistency requirement phụ thuộc nghiệp vụ:** Có nơi chấp nhận một giai đoạn chuyển tiếp hữu hạn, nơi khác cần cutover nghiêm ngặt. Điều quan trọng là chính sách, metadata và tests phải phản ánh quyết định đó.

### 17.4. IAM và tenant scope

Một principal được phép **Decrypt với KEK của tenant A** không tự được phép đọc tất cả records của tenant A, càng không được đọc B. Khi key version chuyển, phải giữ:

- KMS/IAM grants đúng resource, tenant, environment và operation.
- Application authorization theo record và data ownership.
- AEAD AAD/encryption context từ nguồn tin cậy, không hoàn toàn do client tự khai.
- Key ID/version allowlist và trạng thái không bị revoked cho thao tác đang yêu cầu.

Đừng dùng rotation để vô tình **mở rộng quyền từ KEK-v1 sang KEK-v2** bằng việc cấp tạm wildcard permissions rồi quên thu hồi.

## 18. Backup, DR và dữ liệu lịch sử trong vòng đời rotation

Rotation chỉ thật sự an toàn nếu những **ciphertexts và chữ ký còn phải giữ** vẫn được xử lý đúng sau migration và disaster recovery.

### 18.1. Snapshot trước cutover

Ví dụ:

~~~text
T0: Backup chứa wrappedDEK dưới KEK-v1
T1: Production rewrap những wrappedDEKs sang KEK-v2
T2: Production ngừng dùng KEK-v1
T3: KEK-v1 bị destroy
T4: DR restore backup T0
~~~

Nếu dữ liệu tại T0 còn cần phục hồi, nhưng KEK-v1 đã bị hủy và không có cơ chế recovery khác, **DR restore có thể thất bại dù bản backup còn nguyên**. Vì vậy, việc hủy một KEK phụ thuộc **toàn bộ bản sao dữ liệu và retention**, không chỉ database đang phục vụ.

### 18.2. Không lưu raw KEK ngoài inventory để “phòng thân”

Một file chứa raw KEK cũ đặt ở ổ USB hoặc ticket nội bộ không phải DR strategy phù hợp khi policy yêu cầu non-exportable. Nó làm yếu ranh giới KMS/HSM và khiến destruction/crypto-erasure không còn kiểm chứng được.

Giải pháp tùy môi trường:

- **Managed KMS recovery/replication** theo semantics provider.
- **HSM secure backup/quorum** được phê duyệt.
- **Rewrap backup data keys** hoặc khôi phục/migrate encrypted data theo thủ tục được kiểm soát.
- **Recovery key domain** riêng khi kiến trúc đã được review.
- Kiểm thử readback sau restore bằng **key versions và trust hiện hành**.

### 18.3. Restore không được hồi sinh key đã revoked

Một backup cũ có thể chứa:

- Alias trỏ tới signer-v1 đã compromised.
- KMS IAM grant chưa bị thu hồi.
- Truststore/JWKS public-v1 đã hết hiệu lực.
- Key inventory state ACTIVE cũ.
- DEK plaintext cache hoặc secret manager version cũ.

Khi restore, cần đối soát **revocation epoch, tombstones, key state/IAM policy hiện hành**, không chỉ nạp lại snapshot và mở traffic. Một key bị thu hồi **không được trở lại ACTIVE** vì môi trường DR dùng dữ liệu cấu hình cũ.

### 18.4. Khi nào destroy được khóa cũ?

Đặt **destruction eligibility** độc lập với **rotation completed**. Các kiểm tra thường gồm:

1. Không còn Encrypt/Sign/Wrap mới bằng key cũ.
2. Những ciphertext/wrapped DEKs còn cần đã được rewrap/re-encrypt hoặc còn recovery path được phê duyệt.
3. Những chữ ký lịch sử còn phải Verify có đủ public trust/certificate/timestamp evidence.
4. Backup/DR và các bản sao của raw key được kiểm kê.
5. Legal hold/retention không ngăn hủy.
6. Owner và Security/KMS admin phê duyệt theo policy.
7. KMS/HSM deletion state thật đã được kiểm tra; phân biệt scheduled/pending với executed.

**Xóa key không đồng nghĩa xóa dữ liệu attacker đã lấy được**. Crypto-shredding có ý nghĩa trong phạm vi các bản sao do tổ chức còn kiểm soát và khi không còn đường giải mã hợp lệ khác.

## 19. Rotation gặp lỗi: fail closed nhưng không mất dữ liệu

Một quy trình rotation tự động có thể hỏng ở mọi bước. Cần phân loại lỗi và chọn **hành vi an toàn**, không đưa ra một câu lệnh “rollback về v1” vô điều kiện.

| Lỗi | Nguy cơ | Cách xử lý |
| --- | --- | --- |
| **Không tạo được key-v2** | Overdue hoặc cutover chưa sẵn sàng | Cảnh báo, retry/idempotent; chặn tạo mới khi policy bắt buộc |
| **v2 được tạo nhưng chưa có grants** | Writer/Signer bị lỗi sau cutover | Readiness test quyền trước khi activate |
| **Public-v2 chưa tới verifier** | Chữ ký mới không thể Verify | Chuẩn bị JWKS/cert distribution trước cutover |
| **Alias đổi nhưng app cache v1** | Encrypt/Sign vẫn dùng v1 sau deadline | Key version telemetry, invalidation, hard policy gate |
| **KMS throttling khi rewrap hàng loạt** | Timeouts và migration backlog | Concurrency limit, backoff, phân kỳ workload |
| **Metadata update không atomic** | Wrapped DEK và KEK ref lệch | Transaction/CAS, idempotent job, readback |
| **Data migration sai AAD/tag** | Không đọc được dữ liệu hoặc integrity failure | Chặn publish bản lỗi, giữ bản hợp lệ, điều tra chính xác |
| **Service offline trong cutover** | Dùng version cũ khi trở lại | Startup reconciliation, minimum epoch enforcement |
| **DR restore từ snapshot cũ** | Key grants/trust bị hồi sinh | Reconcile key state với control plane hiện hành |
| **Clock drift hoặc DST** | Thực hiện rotation lệch mốc | UTC Instant, ZoneId policy, monitoring |
| **v1 compromised trong planned overlap** | Attacker tiếp tục lợi dụng v1 | Emergency revoke, không giữ overlap planned |
| **Destroy v1 quá sớm** | Mất dữ liệu còn cần Decrypt | Dependency preflight và recovery review |

### 19.1. Hai kiểu rollback phải phân biệt

**Operational rollback khi v1 vẫn được tin:** Nếu v2 chưa hoạt động và policy cho phép, có thể cần một phương án khôi phục kiểm soát trong **approved exception window**. Phải ghi approval, thời gian và dữ liệu được bảo vệ.

**Security rollback về v1 đã compromised/revoked:** **Không được thực hiện.** Dùng v3 hoặc đường HA/DR an toàn; không giảm mức bảo vệ chỉ để hoàn thành request.

### 19.2. Overdue behavior cần được xác định trước

Một hệ thống có thể chọn:

- **Fail closed:** Từ chối Encrypt/Sign/Wrap mới bằng material đã quá hạn. Phù hợp khi chính sách tuyệt đối không cho phép vượt mốc.
- **Grace period được phê duyệt:** Cho phép giới hạn operations ở v1 trong một cửa sổ rõ ràng khi v1 **không bị nghi compromise**, kèm audit và owner approval.
- **Degraded mode an toàn:** Cho đọc dữ liệu lịch sử theo quyền nhưng chặn tạo bản mã/chữ ký mới cho đến khi v2 sẵn sàng.

Không được **im lặng tiếp tục dùng key cũ mãi mãi**, hoặc fallback sang hardcoded key/test secret khi KMS lỗi.

### 19.3. HSM/KMS còn cần thực thi state

Nếu app chỉ nhìn deadline trong local config mà principal vẫn được KMS Sign/Encrypt bằng v1, một service cũ hoặc bị chiếm có thể bỏ qua local check. Cần thực thi **IAM/key attributes/policy** ở đúng ranh giới có thể kiểm soát, đồng thời audit các thao tác trái kỳ vọng.

Trong hệ thống không thể gắn deadline ngay ở HSM, phải thiết kế **authorization gateway hoặc key service** với policy version có thẩm quyền, không coi comment hoặc enum local là đủ.

## 20. Incident-driven rotation và key compromise

Lịch định kỳ không phải giải pháp duy nhất. Khi xuất hiện thông tin mới về nguy cơ, **thời hạn rotation phải được rút ngắn** hoặc điều chỉnh ngay theo incident response.

### 20.1. Phân loại sự cố

| Sự cố | Phạm vi ảnh hưởng có thể xảy ra | Cần làm ngoài thay key |
| --- | --- | --- |
| **Raw DEK bị lộ** | Dữ liệu được mã hóa dưới DEK đó | Re-encrypt dữ liệu còn cần, đánh giá ciphertext attacker có |
| **Raw KEK bị lộ** | Nhiều DEK đã Wrap dưới KEK | Thay KEK, đánh giá wrapped DEK cũ, có thể phải thay DEKs/re-encrypt |
| **KMS Unwrap grant bị lạm dụng** | Những DEK mà principal đã/được phép giải bọc | Thu hồi grant, điều tra audit, giới hạn data access |
| **Private signing key bị lộ** | Chữ ký giả, token/chứng từ bị ảnh hưởng | Phân phối public-v2 và revocation tới verifiers |
| **HSM Sign API bị lạm dụng** | Ký trái phép dù raw key có thể chưa lộ | Chặn principal, điều tra nội dung/tần suất ký |
| **Shared MAC key bị lộ** | Đối tác/receiver có thể nhận MAC giả | Phân phối key mới, chống replay, dừng tin v1 |
| **Public trust registry bị thay** | Verifier tin public key của attacker | Khôi phục trust source, thu hồi key giả, kiểm tra sessions |
| **CSPRNG/DRBG lỗi khi sinh khóa** | Một tập khóa có thể yếu ngay từ lúc tạo | Khoanh vùng các keys đã sinh, tái tạo từ nguồn tin cậy |

### 20.2. Workflow xử lý

1. **Triage:** Nhận diện key ID/version, algorithm, purpose, owner, environment và dấu hiệu compromise.
2. **Containment:** Tạm khóa quyền Sign/Encrypt/Unwrap hoặc key trust đang gây rủi ro; bảo toàn audit.
3. **Scope:** Liệt kê ciphertext, wrapped DEKs, public-key consumers, signed tokens/documents và backups có phụ thuộc.
4. **Replacement:** Sinh key mới từ ranh giới an toàn, không copy secret cũ.
5. **Distribution:** Thay IAM grants, phân phối public verification key/certificate hoặc MAC key đến recipients được xác thực.
6. **Data remediation:** Rewrap **nếu chỉ KEK policy thay**, re-encrypt **khi DEK exposure đòi hỏi**, xử lý signatures/tokens theo policy.
7. **Validation:** Negative tests đối với key cũ, kiểm tra readback, KMS operation logs và consumer caches.
8. **Closure:** Lưu evidence, rủi ro tồn dư và điều kiện xử lý backups/DR, không tuyên bố tất cả bản sao đã bị xóa nếu chưa có chứng cứ.

### 20.3. Vì sao planned rotation không đủ cho compromise?

Giả sử v1 có lịch thay ngày 01-12, nhưng raw key bị lấy ngày 20-11. Đợi đến 01-12 tạo v2 vẫn để attacker **tạo chữ ký giả hoặc giải mã dữ liệu** trong khoảng còn lại.

Ngay cả sau 01-12, nếu attacker đã giữ **raw key và ciphertext/token cũ**, việc thay material tại nguồn **không xóa quyền sử dụng của bản sao ngoài hệ thống**. Cần đánh giá **trust revocation, data access và lịch sử sự cố**.

## 21. Case study: rotation theo thời gian cho nền tảng hóa đơn Java

Một nền tảng nhiều tenant dùng:

- **Billing API:** Tạo và lưu hóa đơn được mã hóa bằng **AES-GCM DEK**.
- **Envelope encryption:** DEK được bọc bởi **KEK trong managed KMS**.
- **Invoice Signing Service:** Ký hóa đơn đã phát hành bằng **private signing key trong HSM**.
- **Webhook Gateway:** Gửi thông báo tới đối tác với **HMAC key** được chia sẻ theo chính sách.
- **Partner Verifiers:** Xác minh chữ ký và tính hợp lệ của hóa đơn bằng **public verification key**.
- **SRE/Security/Data owner:** Quản lý lịch, IAM grants, KMS, retention, incident response và DR.

Các key types không có cùng cryptoperiod chỉ vì cùng xuất hiện trong một hóa đơn:

| Key | Operation mới | Operation lịch sử | Tác động khi rotate |
| --- | --- | --- | --- |
| **DEK invoice domain** | AES-GCM Encrypt | AES-GCM Decrypt | Dữ liệu mới dùng DEK mới, dữ liệu cũ cần đường đọc |
| **KMS KEK** | Wrap encrypted data keys mới | Unwrap blobs cũ | Có thể dùng KMS rotation hoặc rewrap theo provider |
| **Private invoice signer** | Sign chứng từ mới | Private key không cần Verify | Public key/certificate v2 phải được phân phối |
| **Public verification key** | Verify v2 và lịch sử theo policy | Verify v1 nếu trust/retention cho phép | Key registry, cache và lịch sử chứng cứ |
| **Shared webhook HMAC** | Tạo MAC mới | Kiểm tra MAC v1 trong overlap hữu hạn | Hai phía phải cutover và chống replay |
| **TLS ephemeral traffic key** | Theo TLS session/key schedule | Theo session lifecycle | Không phụ thuộc deadline của KEK hay JWT signer |

### 21.1. Kịch bản planned rotation

**Tình huống:** Security policy nội bộ quyết định có một đợt cutover KEK và signing key vào đầu kỳ vận hành tới, còn DEK rotation dựa thêm trên usage. Đây là **lịch minh họa**, không phải chu kỳ tiêu chuẩn bắt buộc.

**Pha A — Hai tuần trước cutover**

1. Application owner kiểm kê KEK-v3, signer-v7, DEK domains, ciphertext và partners.
2. KMS tạo KEK-v4 hoặc xác minh tính năng rotation đã phê duyệt; HSM sinh signing pair-v8.
3. IAM grants được chuẩn bị theo **least privilege**, không cấp wildcard quyền admin tạm thời.
4. Public signing key-v8 được đăng vào trusted registry/JWKS/certificate profile phù hợp.
5. Partner verifier test v8 và xác nhận sẵn sàng; webhook receiver chuẩn bị HMAC-v2 nếu liên quan.
6. SRE dry-run một tập encrypted data keys/records và DR restore.

**Pha B — Cutover**

1. Control plane công bố **rotation epoch 8** và thời điểm hiệu lực bằng UTC Instant.
2. **Wrap mới** sử dụng KEK-v4 nếu policy/provider yêu cầu resource mới.
3. **Sign mới** sử dụng private signer-v8, cấm Sign v7.
4. **Encrypt mới** sử dụng DEK active theo riêng policy của DEK; không tự coi việc đổi KEK đã thay DEK.
5. Các writer instances phải ghi actual key ID/version; telemetry phát hiện instance nào vẫn dùng v7/v3.

**Pha C — Sau cutover**

1. Verify các chữ ký v8 tại partner; đọc dữ liệu cũ bằng version đúng.
2. Chạy rewrap backlog nếu yêu cầu; mỗi update có concurrency control, readback và audit.
3. Đối soát snapshots/DR, data retention và outstanding wrapped DEKs.
4. Retire những key versions không được dùng tạo mới.
5. Không destroy KEK-v3 trước khi toàn bộ recovery obligations đã được xử lý.

### 21.2. Thất bại: một instance còn cache key-v1

Giả sử một pod Java không restart được và tiếp tục dùng **signer-v7** sau cutover. Nếu private v7 còn ở trạng thái HSM ACTIVE với IAM grant rộng, pod có thể ký mới dù central registry đã ghi v8.

Biện pháp:

- HSM/key service chặn Sign bằng v7 sau deadline theo policy.
- Startup/readiness gate của pod so sánh **minimum accepted epoch** với control plane.
- Log/metrics gồm **actual key version** của mỗi Sign.
- Alert nếu có phép Sign v7 sau cutover.
- Cung cấp đường retry an toàn với signer v8; không âm thầm chấp nhận v7.

**Điểm học:** Thay alias trong file cấu hình không phải bằng chứng cryptoperiod đã được thực thi ở nơi giữ private key.

### 21.3. Thất bại: rewrap hoàn tất ở primary nhưng không ở backup

Nếu backup T0 vẫn chứa wrapped DEKs dưới KEK-v3, xóa KEK-v3 có thể làm restore thất bại. Application owner phải lấy dependency list và test DR, hoặc có recovery mechanism được phê duyệt với retention rõ ràng.

Không “giải quyết” bằng cách xuất raw KEK-v3 thành file không kiểm soát. Kiểm soát bản sao khóa chính là lý do hệ thống sử dụng managed KMS/HSM.

### 21.4. Sự cố: private signer-v7 bị lộ trước cutover

Đây không còn là planned rotation:

1. IR cô lập credential/KMS grants và đánh giá raw key exposure.
2. HSM/issuer ngừng Sign v7, phân phối trạng thái revocation tới partner verifiers.
3. Kích hoạt signer-v8 hoặc tạo key mới từ ranh giới sạch theo policy khẩn cấp.
4. Đối soát chữ ký/tokens đã phát hành trong khoảng nghi lộ; không chỉ nhìn key ID.
5. Xem xét trusted timestamp/evidence cho hóa đơn lịch sử.
6. Không dùng planned overlap cho v7 chỉ để đối tác cũ còn Verify; áp dụng quyết định trust dựa trên sự cố và chứng cứ thời gian.

## 22. Kiểm toán và các chỉ số chứng minh rotation thành công

Rotation cần **evidence** chứ không chỉ status trên dashboard.

### 22.1. Audit record nên có

| Trường | Vai trò |
| --- | --- |
| **rotationRequestId / changeId / incidentId** | Idempotency và nguồn phê duyệt |
| **keyId, oldVersion, newVersion** | Xác định material đang thay |
| **owner, environment, tenant, purpose** | Phạm vi trách nhiệm |
| **algorithm / provider / storage boundary** | Kiểm tra ranh giới mật mã |
| **cryptoperiodPolicyId / policyVersion** | Giải thích lý do deadline và cutover |
| **createdAt / activatedAt / retiredAt** | Thời gian thực, không chỉ kế hoạch |
| **plannedDueAt / actualCutoverAt** | Đo trễ và vi phạm policy |
| **principal / approver / operation** | Separation of duties |
| **KMS/HSM response / key state** | Bằng chứng thao tác backend |
| **consumer ack / instance versions** | Relying parties và writers đã chuyển chưa |
| **rewrap/re-encrypt counts** | Số bản ghi đã migration và còn outstanding |
| **backup/DR validation** | Chứng minh đường recovery |
| **revocation/destruction status** | Phân biệt queued, pending, completed |
| **exception/residual-risk record** | Không báo hoàn tất quá mức bằng chứng |

**Không lưu raw private signing key, DEK, KEK, MAC secret hoặc plaintext dữ liệu** vào audit log. Key IDs và context có thể mang business metadata nên cũng phải phân loại/giới hạn quyền xem.

### 22.2. Những chỉ số nên đo

- **Rotation overdue count:** Số keys quá hạn cho operation tạo mới.
- **Key age by purpose:** Phân phối tuổi khóa theo loại và environment.
- **Time to cutover:** Độ trễ từ scheduledDueAt đến actual cutover.
- **Old-key new-use count:** Số Sign/Encrypt/Wrap mới vẫn dùng version cũ sau deadline.
- **Consumer readiness coverage:** Tỷ lệ partners/regions/instances có thể dùng v2.
- **Migration coverage:** Số wrapped DEKs/ciphertexts còn phụ thuộc material cũ.
- **KMS/HSM error rate and latency:** Lỗi/quota/timeout trong giai đoạn migration.
- **Historical read success:** Dữ liệu cũ vẫn Decrypt/Verify được theo policy.
- **Revocation propagation lag:** Độ trễ khiến key compromised bị chặn thực tế.
- **DR recovery coverage:** Có bằng chứng restore đúng với dữ liệu và key versions còn giữ.
- **Unexpected grants/policy drift:** Quyền mới vượt phê duyệt trong đợt rotation.

### 22.3. Cảnh báo gắn với hành động

| Alert | Hành động đề xuất |
| --- | --- |
| Key sẽ hết hạn trong preparation window | Mở ticket, tạo v2 và test readiness |
| Đến deadline nhưng v2 chưa active | Chặn operation mới theo policy; incident/escalation |
| Old-key Sign sau cutover | Cô lập instance/grant, xem xét khả năng ký trái phép |
| Old-key Encrypt sau cutover | Khoanh vùng ciphertext mới sai key, sửa writer và audit |
| Wrapped DEKs còn dùng KEK sắp destroy | Chặn deletion, hoàn tất recovery/migration |
| JWKS cache chưa có public-v2 | Hỗ trợ rollout hoặc thay lịch cutover có phê duyệt |
| Key v1 revoked nhưng DR restore làm active | Ngăn traffic, reconcile trust/IAM state |
| Usage/nonce sắp vượt giới hạn trước deadline | Rotate khẩn cấp theo usage, không đợi lịch |

**Thresholds phải do chính sách và dữ liệu vận hành quyết định**, không tự coi mọi mức cảnh báo là mục tiêu chuẩn chung.

## 23. Kiểm thử rotation theo thời gian

### 23.1. Ma trận kiểm thử thời gian và trạng thái

| Bài kiểm thử | Kết quả mong đợi |
| --- | --- |
| **now ngay trước deadline** | Cho phép tạo mới nếu state/usage/authorization đều hợp lệ |
| **now đúng tại deadline** | Từ chối tạo mới bằng key cũ theo exclusive-end rule |
| **now sau deadline** | Key cũ không còn Encrypt/Sign/Wrap mới |
| **Key PRE_ACTIVE trước cutover** | Không dùng cho production operation tạo mới |
| **Key RETIRED nhưng có ciphertext lịch sử hợp lệ** | Có thể Decrypt nếu policy và IAM cho phép |
| **Key REVOKED/compromised** | Không tạo mới; Verify/Decrypt tùy trust/incident policy |
| **Clock lệch hoặc đổi timezone** | Hệ thống dùng UTC Instant/control plane, không trượt mốc |
| **Lịch đầu tháng rơi vào DST transition** | ZoneId rule định nghĩa rõ và conversion ổn định |
| **CreatedAt khác activatedAt** | Deadline được tính từ mốc policy định nghĩa |
| **Usage limit đạt trước deadline** | Dừng/rotate trước mốc lịch |
| **Một request vượt bytes budget còn lại** | Không Encrypt nếu reservation/budget không đủ |
| **Mất inventory state của key** | Không tự chấp nhận tạo mới với key không rõ trạng thái |

### 23.2. Ma trận vận hành, data và trust

| Bài kiểm thử | Kết quả mong đợi |
| --- | --- |
| Scheduler nhận cùng event hai lần | Idempotent, không tự sinh nhiều active keys |
| Hai rotation workers chạy đồng thời | Chỉ một cutover hợp lệ; version/CAS giữ nhất quán |
| Tạo v2 xong nhưng mất kết nối trước ghi inventory | Reconcile KMS resource, không tạo v3 trái ý |
| KMS-v2 grant chưa sẵn sàng | Không cutover mù; readiness gate báo lỗi |
| Một pod cache alias-v1 | Telemetry phát hiện, local/hard policy gate chặn new-use |
| Thay private signing key | Verifiers tin public-v2 từ đúng issuer trước khi ký mới |
| Old JWT key bị compromise | Revocation/invalidations và cache được xử lý đúng |
| Renew certificate nhưng reuse private key | Không báo “rekey done” nếu policy cần material mới |
| Planned HMAC key rotation | Sender và verifier chuyển v2, overlap hữu hạn, chống replay |
| HMAC-v1 compromised trong overlap | V1 không được tiếp tục chấp nhận theo planned schedule |
| KEK-v1 rewrap sang KEK-v2 | Wrapped DEK blob/key reference đổi, payload vẫn đọc được |
| DEK-v1 cần thay | Re-encrypt payload bằng DEK-v2, dùng nonce mới |
| AES-GCM tag/AAD bị sửa | Từ chối Decrypt, không thử fallback sai |
| Metadata/wrapped DEK update bị race | CAS/transaction tránh mismatch |
| KMS outage trong rotation | Fail closed/retry bounded, không dùng raw hardcoded key |
| Primary thành công, DR dùng snapshot cũ | Recovery path có thể dùng đúng key hoặc blocker rõ |
| Destroy key còn dữ liệu phụ thuộc | Dependency/retention preflight từ chối |
| Restore IAM/JWKS từ backup trước revoke | Không hồi sinh trust/key state cũ |

### 23.3. Vấn đề cần kiểm tra bằng thực nghiệm

**Unit test hàm dueAt chưa đủ**. Cần:

- **Clock-injection tests** cho exact boundary, timezone và calendar month.
- **Integration tests** với KMS/HSM/secret manager API thật ở môi trường được cấp quyền.
- **Negative tests** cho key retired/revoked, cross-tenant và algorithm mismatch.
- **Chaos/failure tests** cho timeout, KMS throttling, partial write, leader failover.
- **Restore drills** để chứng minh backup lịch sử còn đọc được.
- **Canary rollout** và đo những writer/consumer sử dụng v2 thực tế.
- **Security incident tabletop** để kiểm tra rút ngắn lịch rotation khi compromise.

Không coi "đã tạo key-v2 thành công" là kết quả nghiệm thu cuối nếu ứng dụng vẫn tạo ciphertext mới dưới key-v1.

## 24. Các lỗi thường gặp khi rotation theo thời gian

| Anti-pattern | Hậu quả | Khắc phục |
| --- | --- | --- |
| **Một chu kỳ cố định cho mọi key types** | Không phản ánh cryptoperiod và threat model | Policy theo purpose, volume, algorithm và retention |
| **Xem dueAt là ngày bắt buộc destroy** | Mất khả năng Decrypt/Verify lịch sử | Tách originator period và recipient period |
| **Thay alias rồi tuyên bố đã thay vật liệu khóa** | Alias có thể vẫn trỏ key cũ | Xác minh key ID/fingerprint/material version |
| **Gia hạn certificate rồi gọi là rekey** | Private signing key có thể chưa đổi | Sinh pair mới và kiểm tra provenance |
| **Đổi KEK rồi báo mọi DEK đã rotate** | Raw DEKs và nonce budget vẫn cũ | Tách KEK rewrap và DEK re-encrypt |
| **Chỉ đặt cron, không cưỡng chế deadline** | Old key vẫn được Encrypt/Sign mãi | Policy gate ở nơi thực hiện crypto + telemetry |
| **Chọn key theo current alias khi Decrypt dữ liệu cũ** | Mở không được ciphertext v1 | Lưu version/wrapped key reference đúng |
| **Xóa key v1 ngay sau cutover** | Backup/ciphertext cũ mất đường đọc | Dependency inventory, migration và retention |
| **Giữ key-v1 làm fallback sau khi revoked** | Kẻ tấn công tiếp tục sử dụng bí mật bị lộ | Emergency cutoff và DR an toàn |
| **Tự tạo key mới trong từng request gặp deadline** | Race, nhiều versions, không có inventory | Scheduler có lease/idempotency/approval |
| **Cron job hằng tháng ở timezone ngầm** | Rotation lệch giờ/ngày hoặc DST | UTC Instant, ZoneId và Calendar rule |
| **Đếm tháng bằng 30 ngày** | Sai lịch chính sách | Period/ZonedDateTime cho calendar schedule |
| **Không đếm Encrypt/nonce trước deadline** | Có thể vượt giới hạn AEAD | Usage-triggered rotation và budget |
| **Một DEK cho nhiều writers dùng cùng counter nonce từ 0** | GCM nonce reuse | Thiết kế nonce allocation hoặc scope DEK độc lập |
| **KMS auto-rotation được hiểu là re-encrypt DB** | Không có migration thật, hiểu sai mức bảo vệ | Kiểm tra semantics provider và blob versions |
| **Lưu chỉ alias, không lưu actual key version** | Không thể truy vết dữ liệu/chữ ký | Key ID/version trong envelope, signature metadata, audit |
| **Không chuẩn bị verifiers trước Sign-v2** | Token/chứng từ mới bị từ chối | Pre-publish trusted public v2, readiness tests |
| **Giữ JWT signing public-v1 mãi dù raw private v1 lộ** | Chữ ký giả có thể tiếp tục được chấp nhận | Revocation propagation, cache invalidation |
| **HMAC verifier thử mọi keys không giới hạn** | Old secret vẫn có thể giả mạo, khó audit | Key ID, overlap hữu hạn, anti-replay |
| **Tạm cấp IAM wildcard cho migration rồi quên thu hồi** | Tăng quyền quá mức sau rotation | Scoped grants, expiry, dual control, audit |
| **Không dùng CAS khi rewrap** | Metadata mismatch, mất khả năng đọc | Atomic update, optimistic locking, readback |
| **Primary rotate xong thì destroy ngay** | DR/snapshots lịch sử không đọc được | Backup dependency checks và restore drills |
| **Chỉ kiểm tra status=WRITTEN/ROTATED trong dashboard** | Không chứng minh actual key use đã chuyển | Kiểm tra KMS logs, ciphertext metadata, instance versions |
| **Log raw key hoặc plaintext để debug rotation** | Tạo đường rò bí mật mới | Log key ID, operation, result và correlation |

## 25. Checklist đánh giá policy rotation theo thời gian

Trước khi triển khai hoặc nghiệm thu, hãy trả lời:

1. **Mục đích:** Đây là DEK, KEK, signing key, TLS private key, shared MAC key hay session key?
2. **Cryptoperiod:** Có phân biệt thời gian tạo bảo vệ mới và thời gian xử lý dữ liệu cũ?
3. **Cơ sở chu kỳ:** Interval được xác định theo threat model, thuật toán, lượng dùng, dữ liệu và chính sách áp dụng?
4. **Time origin:** Deadline tính từ createdAt, activatedAt hay mốc calendar được phê duyệt?
5. **Time representation:** Mốc hiệu lực lưu bằng UTC Instant; calendar policy có ZoneId và DST rule rõ?
6. **Usage threshold:** Có theo dõi nonce/count/bytes hoặc giới hạn provider có thể buộc rotate sớm?
7. **Emergency trigger:** Có đường rút ngắn hạn khi raw key leak, IAM abuse, thuật toán yếu hoặc compromise?
8. **Owner:** Có application owner, security approver, data owner và KMS/HSM operator phù hợp?
9. **Key inventory:** Có key ID/version, purpose, owner, state, environment, region, consumers và dependencies?
10. **Material:** Có sinh key mới thực sự khi policy yêu cầu, không chỉ đổi alias/certificate/password?
11. **Private material boundary:** Có HSM/KMS, non-exportability và grants phù hợp?
12. **Preflight:** v2 đã được tạo, policy/IAM cấp quyền, test Sign/Encrypt/Wrap và negative cases?
13. **Verifier/recipient readiness:** Public keys, certificates, JWKS hoặc HMAC secrets đã tới đúng người nhận?
14. **Cutover:** Active version có được cập nhật atomic/versioned và tất cả writers/senders có làm theo?
15. **Old-key create operations:** Sau deadline, v1 có bị chặn đối với Sign/Encrypt/Wrap mới?
16. **Historical-use:** Decrypt/Verify/Unwrap cũ có được định tuyến theo key version và đúng policy?
17. **Encryption metadata:** Envelope giữ wrapped DEK, nonce/tag, AAD/algorithm và key reference chính xác?
18. **KEK/DEK separation:** Có phân biệt auto KEK rotation, rewrap DEK và re-encrypt payload?
19. **Concurrent migration:** Rotation jobs có lease, idempotency, retry và CAS/transaction?
20. **Multi-tenant:** Có tách quyền/keys theo environment, tenant, purpose và kiểm tra record authorization?
21. **KMS capacity:** Deadline, KMS quota, API latency và batch backlog có được tính cùng một kế hoạch?
22. **Backup/DR:** Snapshots cũ có đường restore hợp lệ trước khi destroy key?
23. **Revocation:** Key bị compromised có bị chặn trong KMS/HSM và tại verifiers/cache?
24. **Rollback:** Có kế hoạch khôi phục an toàn không hồi sinh key revoked?
25. **Destruction:** Retention/legal hold/dependency review và approval được kiểm tra trước hủy?
26. **Audit:** Có planned/actual timestamps, old/new versions, approver, operation, result và incident links không lộ bí mật?
27. **Monitoring:** Có alert overdue, old-key new-use, migration backlog, trust distribution lag và KMS outage?
28. **Verification:** Có negative tests, readback, cross-region checks và restore drills cho cả planned/emergency rotation?
29. **Exceptions:** Mọi grace period có owner, expiry, giới hạn scope và evidence?
30. **Continuous review:** Chính sách được rà soát sau sự cố, thay thuật toán/KMS provider và thay đổi data retention?

## 26. Ghi nhớ

- **Rotation theo thời gian** là quy trình thay **key material cho hoạt động mới** theo một cryptoperiod được quản lý; nó không chỉ là đổi alias, password hoặc certificate.
- **Cryptoperiod có ngữ nghĩa theo operation.** Encrypt/Sign/Wrap mới thường phải chuyển v2 ở cutover; Decrypt/Verify/Unwrap dữ liệu lịch sử có thể còn cần v1 theo policy.
- **Chu kỳ rotation phải dựa trên risk/algorithm/usage/retention và tiêu chuẩn áp dụng**, không sao chép một con số cho mọi key types.
- **Scheduled deadline không thay usage limits**, đặc biệt là yêu cầu nonce duy nhất dưới cùng AES-GCM DEK và các giới hạn số phép Encrypt.
- **KEK rotation, DEK rewrap và payload re-encrypt là những thao tác khác nhau.** Rewrap không đổi DEK hoặc xóa rủi ro của raw DEK đã lộ.
- **Signing-key rotation đòi hỏi trusted public-key rollout.** JWKS/PKI/certificate cache và chữ ký lịch sử phải có kế hoạch; certificate renewal không nhất thiết thay private material.
- **KMS automatic rotation có semantics theo provider.** Không mặc định nó thay mọi DEK/ciphertext hoặc tự quản lý toàn bộ retention.
- **Scheduler phải idempotent và versioned**, dùng mốc UTC rõ ràng, hỗ trợ nhiều instances/regions, readback và kiểm soát các key cũ sau cutover.
- **Không destroy key chỉ vì đã quá hạn tạo mới.** Backup, DR, wrapped DEKs, ciphertext và verification evidence có thể còn phụ thuộc.
- **Sự cố compromise phải kích hoạt emergency rotation/revocation**, không chờ lịch. Thay key không thu hồi raw material đã bị attacker lấy.
- **Audit và kiểm thử âm tính** phải chứng minh thực tế key v1 không còn tạo protection mới, v2 đã được dùng và dữ liệu cũ còn an toàn theo policy.

Để đánh giá **rotation theo thời gian**, hãy đặt ba câu hỏi: **“Khóa này đến hạn ngừng tạo bảo vệ mới dựa trên điều kiện nào?”, “Những ciphertext, chữ ký và bên nhận nào còn phụ thuộc vào khóa cũ?”, “Bằng chứng nào cho thấy mọi writer/signer đã chuyển sang khóa mới mà không gây mất dữ liệu hoặc hồi sinh key đã bị thu hồi?”** Khi trả lời được bằng **policy, key inventory, KMS/HSM state, key-version telemetry và kết quả kiểm thử**, rotation mới trở thành một kiểm soát bảo mật có thể vận hành và kiểm chứng.





