# Rotation khi nhân sự thay đổi

## 1. Tại sao biến động nhân sự liên quan trực tiếp đến vòng đời khóa?

Trong một hệ thống bảo mật, **khóa mật mã (cryptographic key)** không chỉ được quản lý theo thuật toán và thời gian sử dụng. Nó còn gắn với **con người, tài khoản, dịch vụ và quyền vận hành**. Khi một nhân viên nghỉ việc, chuyển nhóm, mất quyền quản trị, thay đổi nhà thầu hoặc không còn giữ vai trò người giám hộ khóa, tổ chức phải đánh giá **có cần thay vật liệu khóa (key rotation) hay chỉ cần thu hồi quyền truy cập và thông tin xác thực**.

Ví dụ: Một nhân viên DevOps rời công ty. Người đó từng có quyền đọc một secret được xuất dưới dạng rõ trên máy làm việc. Việc vô hiệu hóa tài khoản công ty là **cần thiết nhưng không đủ** để bảo đảm người đó không giữ bản sao secret. Nếu secret là HMAC key dùng chung, tổ chức phải xem xét **tạo secret mới, cập nhật consumers và ngừng chấp nhận key cũ**.

Ngược lại, một nhân viên chỉ có quyền gọi **KMS Decrypt** qua định danh IAM, chưa từng có khả năng export plaintext KEK và không có bằng chứng key bị lộ, thì **thu hồi IAM/session/grants, kiểm tra logs và phạm vi quyền có thể là hành động chính**; không mặc định phải re-encrypt mọi dữ liệu trong doanh nghiệp.

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài học **Rotation khi nhân sự thay đổi** thuộc chương **Cryptoperiod và rotation** liên kết:

- Vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy**.
- **DEK/KEK** trong mật mã đối xứng, KMS/HSM và envelope encryption.
- **Private signing keys**, HMAC/PSK, SSH keys, API credentials và certificates.
- **IAM, least privilege, Separation of Duties (SoD), dual control**, inventory và audit.
- Quy trình **Joiner–Mover–Leaver (JML)**, phản ứng sự cố, backup/DR và bằng chứng thực thi.

**Nguyên tắc cốt lõi:** Nhân sự thay đổi là **một tín hiệu bắt buộc đánh giá lại quyền và rủi ro đối với khóa**, không đồng nghĩa trong mọi trường hợp phải thay toàn bộ key material. Quyết định đúng phụ thuộc **ai có khả năng biết/lấy/sử dụng vật liệu**, loại khóa, phạm vi tác động và bằng chứng kiểm soát.

## 2. Phân biệt thu hồi quyền, thay credential và rotation khóa

Những hành động dưới đây phục vụ các mục đích khác nhau:

| Hành động | Tác động chính | Có thay key material không? |
|---|---|---|
| **Disable user / remove IAM role** | Chặn một danh tính truy cập hệ thống | Thường **không** |
| **Revoke sessions/tokens** | Vô hiệu hóa phiên/credential đã cấp | Thường **không**, nhưng token/credential không còn hợp lệ |
| **Revoke KMS grants** | Chặn đường gọi Encrypt/Decrypt/Sign/Unwrap của principal | **Không** |
| **Rotate API token/SSH key/password** | Thay credential chứng minh danh tính hoặc được dùng truy cập | **Có** đối với credential đó |
| **Rotate HMAC/PSK/shared secret** | Thay secret dùng để xác thực/MAC giữa các hệ thống | **Có** |
| **Rotate KEK** | Tạo/chọn material mới để bọc DEK | **Có** đối với KEK; DEK có thể giữ nguyên |
| **Rewrap DEK** | Thay cách bọc DEK bằng KEK mới | **Không** nhất thiết thay DEK |
| **Rotate DEK + re-encrypt** | Thay key trực tiếp mã hóa dữ liệu | **Có**, thường phải mã hóa lại payload |
| **Rotate signing key pair** | Tạo private/public key pair mới cho chữ ký | **Có** |
| **Revoke certificate/trust** | Làm verifier ngừng tin cậy credential/key theo chính sách | Không nhất thiết phá/xóa private key đang tồn tại |
| **Destroy key material** | Loại bỏ khả năng sử dụng material ở miền kiểm soát | Không thể đảo ngược; cần kiểm kê phụ thuộc |

### 2.1. Vì sao chỉ disable account có thể chưa đủ?

Nếu người nghỉ việc đã **biết hoặc có bản sao secret**, chẳng hạn một chuỗi HMAC trong laptop, API token trong script, SSH private key hoặc plaintext DEK trong log, việc khóa account **không thể xóa bản sao nằm ngoài kiểm soát**.

Phải phân biệt:

1. **Quyền gọi hệ thống:** được IAM, KMS policy, SSH server, IdP hoặc API gateway kiểm soát.
2. **Sở hữu/biết vật liệu bí mật:** có thể còn tồn tại sau khi tài khoản mất quyền.
3. **Khả năng sử dụng bí mật ở nơi khác:** ví dụ private signing key đã lộ có thể ký ngoài HSM.
4. **Lịch sử dữ liệu đã bị xem:** đổi khóa không thể làm attacker quên plaintext đã lấy.

### 2.2. Vì sao không luôn cần rotate toàn bộ DEK?

Khi một nhân viên từng giữ quyền **dùng KMS Sign/Decrypt**, nhưng không thể export material, KMS được kiểm soát đúng và không có dấu hiệu compromise, trọng tâm có thể là **thu hồi vai trò, sessions, grants và xác minh audit**. Việc thay hết DEK trong mọi dataset có thể gây downtime, tăng rủi ro migration và làm hỏng backup nếu thực hiện thiếu chuẩn.

Tuy nhiên, nếu quyền Decrypt đã bị **lạm dụng để lấy plaintext data**, hoặc material/credential đã có khả năng bị sao chép, phải đánh giá **phạm vi dữ liệu có thể đã lộ và nhu cầu thay key** riêng biệt.

## 3. Cryptoperiod và event-driven rotation

**Cryptoperiod** là khoảng thời gian sử dụng một key material theo mục đích và trạng thái được cho phép bởi policy. Quản trị khóa thường phân biệt:

- **Originator-usage period:** giai đoạn được phép tạo ciphertext, MAC hoặc chữ ký mới.
- **Recipient-usage period:** giai đoạn còn được phép giải mã/verify dữ liệu lịch sử, tùy key type và policy.
- **Retirement/revocation:** ngừng một hoặc nhiều phép toán; không nhất thiết đồng nghĩa xóa material tức thì.
- **Destruction:** hủy vật liệu khi đã xử lý dependencies, retention và recovery.

### 3.1. Scheduled rotation khác rotation do sự kiện

| Loại sự kiện | Tín hiệu | Hành động thường gặp |
|---|---|---|
| **Theo lịch** | Đến hạn policy hoặc usage budget | Thay material theo cryptoperiod, cutover có kế hoạch |
| **Chuyển nhóm (Mover)** | Role/scopes thay đổi | Thu hồi grants cũ, cấp quyền mới; đánh giá secret từng biết |
| **Nghỉ việc (Leaver)** | Identity hết hiệu lực | Revoke sessions/accounts/credentials ngay theo workflow; đánh giá material exposure |
| **Thu hồi quyền quản trị khóa** | Không còn key custodian | Thay người giữ vai trò, SoD, quorum, recovery custody; rotate khi key/share có nguy cơ |
| **Nhà thầu hết hợp đồng** | Access cần kết thúc | Revoke access; rotate shared/exposed credentials nếu cần |
| **Mất laptop/token** | Có thể bị lộ credential/secret | Incident workflow, rotate credential, đánh giá keys đã export |
| **Nghi ngờ nội gián** | Rủi ro sử dụng sai còn hiện hữu | Containment, thu hồi ưu tiên, rotate theo mức lộ, forensic |
| **Sự cố IAM/KMS grants** | Có quyền ngoài dự kiến | Đóng quyền, audit những operations và xem xét key material compromise |

### 3.2. Cryptoperiod không chỉ là một ngày hết hạn

Một key được đặt expiration năm sau vẫn có thể cần **retire sớm hôm nay** nếu nghi ngờ bị lộ do nhân sự thay đổi. Ngược lại một key đã hết **originator-use period** vẫn có thể cần tồn tại để **Decrypt/Verify historical data** theo retention.

**Không đơn giản xóa mọi khóa cũ khi thay nhân sự.** Khóa có thể bảo vệ archive, encrypted DEKs, certificate history hoặc dữ liệu phải lưu.

### 3.3. Event-driven rotation không thay lịch chính sách

Một hệ thống nên duy trì **cả scheduled cryptoperiod** và **event-driven reassessment**. Không dựa vào việc “nhân sự vừa thay đổi nên đã rotate” để bỏ monitoring nonce limits, usage quotas hoặc expiry policy.

## 4. JML: Joiner, Mover, Leaver trong quản lý khóa

~~~mermaid
flowchart TD
    H["HR / manager event"] --> I{"JML event type"}
    I -->|Joiner| J["Phê duyệt role, least privilege, đào tạo"]
    I -->|Mover| M["Thu hồi quyền cũ, cấp scope mới, đánh giá secret exposure"]
    I -->|Leaver| L["Revoke identity/session/credentials, thu thiết bị"]
    J --> R["Key inventory + access graph"]
    M --> R
    L --> R
    R --> D{"Key material có thể đã bị copy/lộ?"}
    D -->|Không, chứng cứ đủ| A["Revoke/adjust access, audit, không rotate material nếu không cần"]
    D -->|Có hoặc không thể loại trừ| K["Rotate affected keys, rewrap/re-encrypt/trust cutover theo loại"]
    A --> V["Verify + evidence"]
    K --> V
    V --> Z["Đóng change/incident, theo dõi residual risk"]
~~~

### 4.1. Joiner: cấp quyền nhỏ nhất ngay từ đầu

Khi nhân viên mới nhận nhiệm vụ:

- Gán **role theo chức năng**, không gửi master secret qua chat/email.
- Ưu tiên **workload identity** và **KMS operations** thay cho bản copy raw key.
- Thiết lập device trust, MFA, token lifetime, approval và logging.
- Không dùng lại credential mà nhân viên cũ đã biết chỉ vì thuận tiện.
- Phân tách trách nhiệm **operator, approver, auditor, data owner**.

### 4.2. Mover: thu hồi role cũ trước khi quyền bị cộng dồn

Một nhân viên chuyển từ đội vận hành production sang QA có thể **không còn được phép KMS Decrypt hoặc KeyAdmin** ở production. Nếu chỉ thêm role QA nhưng giữ role cũ, quyền hiệu lực sẽ bị tích lũy.

Mỗi Mover event phải:

1. Xác định **quyền cũ không còn cần thiết**.
2. Thu hồi role, grants, sessions và access qua các hệ thống liên quan.
3. Xem những secret nhân viên đã từng **export hoặc có thể đọc rõ**.
4. Cấp quyền mới theo least privilege và kiểm tra cross-role assumptions.
5. Ghi bằng chứng/approval; không tự coi “đã chuyển team” là đã mất quyền.

### 4.3. Leaver: xử lý theo thời điểm hiệu lực và rủi ro

Đối với nghỉ việc thông thường, lịch offboarding cần bảo đảm **identity/session/credential revocation phù hợp thời điểm** và inventory những bí mật người đó biết. Với trường hợp nghi ngờ lạm dụng, cần **containment chủ động** và có thể cần quy trình bảo mật ngoài giờ, đồng thời giữ chứng cứ đúng quy định.

Không dùng một email HR “đã nghỉ việc” làm bằng chứng kỹ thuật rằng mọi token, API key, SSH access, grant và certificate đã bị vô hiệu.

## 5. Phân loại tài sản bị tác động khi nhân sự thay đổi

| Loại tài sản | Điều có thể còn tồn tại sau khi nhân viên rời đi | Hành động phân loại |
|---|---|---|
| **IdP account và SSO sessions** | Phiên truy cập chưa hết hạn, refresh tokens | Disable, revoke sessions, xác minh propagation |
| **IAM role / KMS grant** | Quyền assume role hoặc invoke Decrypt/Sign | Thu hồi role/grants và kiểm tra quyền gián tiếp |
| **SSH keys** | Private key trong laptop cá nhân | Remove authorized key/cert access; rotate credential/key pair khi cần |
| **API token / PAT** | Token trong scripts, browser hoặc CI | Revoke/rotate tokens, kiểm tra service dependencies |
| **HMAC/PSK/shared secret** | Secret có thể được ghi nhớ/copy | Generate secret mới, phân phối lại, ngừng chấp nhận old |
| **Private signing key** | Khả năng đã export hoặc giữ bản sao | Kiểm tra non-exportable HSM, đổi key/trust nếu có nguy cơ |
| **KEK trong KMS/HSM** | Operator có thể từng cấp/điều chỉnh quyền | Revoke grants/policy; đánh giá export/backup/material exposure |
| **DEK dữ liệu** | Plaintext DEK có thể từng nằm trong RAM/log/export | Đánh giá DEK nào đã lộ, re-encrypt theo rủi ro |
| **Certificate/client identity** | Certificate/private key trên endpoint | Revoke/rotate cert và cập nhật trust |
| **Recovery shares / backup keys** | Người giữ còn nắm recovery share | Thay custodian, đánh giá quorum/reconstitution |
| **Application service accounts** | Credential dùng chung nhiều người | Xác định owner, rotate nếu có người rời đi biết secret |
| **Key management scripts/CI secrets** | Secret trong repo, job logs, artifacts | Quét, thu hồi, chuyển sang secret provisioning an toàn |

**Đừng nhầm danh mục credentials với key material**: credential dùng để **đăng nhập KMS** bị lộ cần rotate/revoke credential; chưa chắc mọi KEK trong KMS đã bị lộ. Ngược lại nếu raw KEK bị export, đổi credential **không khắc phục** khả năng attacker dùng KEK ngoài KMS.

## 6. Quyết định có cần rotate key material hay không

Quyết định nên dựa trên **đường tiếp xúc với material**, **loại secret** và **khả năng kiểm chứng**.

| Tình huống nhân sự | Bằng chứng/rủi ro | Hành động thường phù hợp |
|---|---|---|
| Nhân viên chỉ đọc dashboard audit KMS | Không có quyền Decrypt, export hoặc grants | Thu hồi quyền dashboard; không tự động rotate DEK/KEK |
| Nhân viên có quyền KMS Decrypt nhưng không export KEK | Principal mất quyền; audit không thấy misuse | Thu hồi grants/sessions, kiểm tra dữ liệu đã truy cập; đánh giá thêm theo threat model |
| Người đã biết shared HMAC secret | Có thể giữ bản copy | **Rotate shared HMAC secret**, cập nhật tất cả peers |
| Người giữ PAT/SSH private key | Credential có khả năng còn trên thiết bị | Revoke/rotate credential và xóa trust cũ |
| Người có bản sao plaintext DEK | Có nguy cơ giải mã offline | **Thay DEK và đánh giá re-encrypt** dữ liệu liên quan |
| Người có plaintext KEK hoặc backup key | Có thể unwrap nhiều DEKs offline | **Thay KEK**, đánh giá DEK đã lộ, rewrap/re-encrypt theo sự cố |
| HSM operator đổi vai trò, private key non-exportable | Không có dấu hiệu key material ra ngoài, nhưng có quyền Sign | Thu hồi quyền Sign/KeyAdmin; xét misuse audit và trust policy |
| Private signing key đã bị xuất hoặc sao chép | Có thể tạo chữ ký ngoài HSM | **Key pair mới**, cập nhật certificate/JWKS/verifiers, đánh giá chữ ký |
| Recovery share holder rời đi | Có thể vẫn giữ share | Thay custodian/share hoặc reconstitute secret theo threshold/quorum policy |
| Nghi ngờ nội gián truy xuất dữ liệu | Không thể tin kết luận “không lộ” từ logs thiếu | Containment + incident assessment + material rotation theo scope |

### 6.1. Khi chỉ thu hồi quyền là đủ, và khi nào không?

**Access revocation** chủ yếu giải quyết hành vi **sử dụng trong hệ thống** sau khi bị thu hồi. **Key material rotation** giải quyết rủi ro bí mật đã có thể nằm **ngoài hệ thống kiểm soát**.

Khi không chắc nhân viên đã có thể copy secret hay chưa, không nên tự suy đoán. Cần kiểm tra **exportability, KMS API permissions, audit events, secret manager reads, endpoint posture, access logs, source/CI artifacts và đường backup**. Nếu chứng cứ không đầy đủ, nêu **residual uncertainty** và đánh giá rủi ro theo dữ liệu.

### 6.2. Rotating mọi key không phải chiến lược luôn an toàn hơn

Thay hàng loạt keys thiếu kiểm soát có thể gây:
- Không mở được ciphertext hoặc archive.
- Mất khả năng Verify chữ ký lịch sử.
- Dừng dịch vụ khi consumers chưa cập nhật.
- Tái tạo key lộ ra CI, chat và logs trong lúc khẩn cấp.
- IAM tạm thời bị mở quá rộng để kịp migration.

**Rotation phải có scope, cutover, verification và rollback/recovery plan**. Khẩn cấp không có nghĩa bỏ quy trình bảo vệ secret.

## 7. Vai trò con người và Separation of Duties

Trong key management, những người sau đây không nên mặc nhiên là một:

- **Key owner:** quyết định mục đích, cryptoperiod và chấp nhận rủi ro.
- **Key custodian/HSM operator:** vận hành key lifecycle và bảo vệ material.
- **KMS/IAM administrator:** quản trị policy và grants theo quy trình.
- **Data owner:** phê duyệt ai được dùng key để xử lý dữ liệu nghiệp vụ.
- **Rotation executor:** chạy workflow chuyển key và consumer cutover.
- **Security approver:** duyệt thao tác nhạy cảm, đặc biệt export/delete/recovery.
- **Auditor:** kiểm tra events và bằng chứng độc lập.

### 7.1. Khi người giữ vai trò đặc quyền rời đi

Nếu nhân viên rời vai trò **key custodian** hoặc approver duy nhất, cần xử lý đồng thời:

1. **Thu hồi quyền** và credentials cá nhân.
2. **Bổ nhiệm người thay thế** theo SoD/maker-checker.
3. **Cập nhật quorum, HSM operator cards hoặc recovery shares** nếu quy trình dùng chúng.
4. **Kiểm tra effective permissions** của các role gián tiếp, trust boundaries và emergency accounts.
5. **Bảo vệ availability:** không để tổ chức mất khả năng rotation/recovery vì không còn người đủ quyền.
6. **Đánh giá material exposure:** có secret/share nào cần thay ngay không?

### 7.2. Dual control và split knowledge

Một số quy trình nhạy cảm sử dụng **hai người phê duyệt** hoặc phân chia key shares để không ai tự mình khôi phục/xuất master secret. Khi một share holder rời đi, không nhất thiết phải thay toàn bộ master secret nếu vẫn bảo đảm threshold và rủi ro, nhưng cần **xem xét re-share/reconstitution theo policy**, inventory share copies và thu hồi khả năng tham gia.

**Không gửi toàn bộ share hoặc master key qua chat** để thay người giữ cho nhanh.

## 8. Quy trình offboarding khóa phải đi cùng IAM và IdP

~~~mermaid
sequenceDiagram
    participant H as HR / Manager
    participant I as IdP / IAM
    participant K as KMS/HSM
    participant A as Application / Secret Manager
    participant S as Security/Audit
    H->>S: Thông báo mover/leaver + effective time
    S->>I: Disable/modify roles, revoke sessions/tokens
    I-->>S: Effective permissions readback
    S->>K: Remove grants/roles, protect key policy
    K-->>S: Key permission state + audit
    S->>A: Revoke PAT/SSH/shared secrets khi cần
    A-->>S: Recipient cutover + ownership evidence
    S->>S: Assess exposure and decide rotation per key type
    S-->>H: Closure evidence, exceptions, residual risk
~~~

### 8.1. Những đường quyền cần kiểm tra

Một nhân viên không có KMS Decrypt trực tiếp có thể vẫn có:

- **AssumeRole** vào một decryption workload.
- **CreateGrant/ChangeKeyPolicy** cho chính mình.
- **IAM PassRole**, quyền triển khai pod/job dùng service account đặc quyền.
- Quyền đọc **secret manager** chứa HMAC/credentials.
- Quyền truy cập **CI/CD logs và deployment secrets**.
- Quyền vào **break-glass role**, vault unseal/recovery ceremony.
- Quyền quản lý trusted JWKS/CA, có thể thay public keys mà verifier chấp nhận.

Đánh giá **effective permissions và quyền có thể tự cấp thêm**, không chỉ nhóm quyền HR/IdP hiển thị.

### 8.2. Identity revocation có thể không lan truyền tức thì

Một số credentials hoặc client sessions có TTL, caching hoặc offline access. Sau DisableAccount, cần xác minh:

- Sessions/tokens cũ còn khả dụng không?
- KMS grants hoặc role sessions có cần thu hồi độc lập?
- Endpoint certificate/SSH key còn được server chấp nhận không?
- Service account có credential được chia sẻ ngoài IdP không?
- Có service nào dùng credential tĩnh của người rời đi không?

**Đánh dấu HR ticket “closed” không tự chứng minh mọi đường truy cập kỹ thuật đã mất hiệu lực.**

## 9. Cryptoperiod khi chủ sở hữu hoặc người quản lý khóa thay đổi

### 9.1. Key ownership khác material possession

Thay **key owner** trên inventory không làm thay key material. Tuy nhiên, owner mới cần:

- Nhận trách nhiệm phê duyệt purpose, usage limits và cryptoperiod.
- Kiểm tra grants, services phụ thuộc và key policies.
- Xác minh có đường recovery hợp lệ và backup/DR.
- Kiểm tra audit, policy exceptions và người giữ quyền export.
- Quyết định có cần **event-driven rotation** dựa trên material exposure.

### 9.2. Originator-use và recipient-use khi nhân sự thay đổi

Ví dụ một signing key đã được dùng ký trong nhiều năm:

- Nhân viên cũ không còn được phép **Sign** mới sau khi rời vai trò.
- Hệ thống có thể vẫn cần **Verify** chữ ký lịch sử với public key/certificate liên quan theo chính sách.
- Nếu private key bị lộ, cần revoke trust/certificate hoặc điều chỉnh policy Verify theo sự cố.
- Xóa public verification key không làm xóa chữ ký cũ; nhưng có thể làm mất khả năng kiểm chứng dữ liệu hợp lệ.

**Không đặt một thời điểm duy nhất để “xóa mọi dấu vết khóa”** nếu còn nhu cầu pháp lý, kiểm toán và phục hồi.

### 9.3. Quyết định theo security strength và usage budget

Dù nhân sự không thay, cryptoperiod có thể phải kết thúc do key tuổi cao, số lần AEAD Encrypt, nonce/counter budget, chính sách thuật toán hoặc thay đổi tiêu chuẩn nội bộ. **Personnel rotation là một trigger bổ sung**, không thay quản trị kỹ thuật của key usage.

## 10. Runbook chuẩn: nhận sự kiện, thu hồi quyền, đánh giá và rotation

Một quy trình đáng tin phải **kết nối HR–IAM–KMS–application–security–data owner**, có idempotency, thời điểm hiệu lực và bằng chứng readback.

~~~mermaid
flowchart TD
    A["HR/manager: xác nhận JML event"] --> B["Xác định identity, effective time, severity"]
    B --> C["Thu hồi role, sessions, tokens, grants theo scope"]
    C --> D["Inventory các keys và credentials liên quan"]
    D --> E["Đánh giá exposure + khả năng sử dụng ngoài hệ thống"]
    E --> F{"Có cần thay secret/material?"}
    F -->|Chưa cần, evidence đủ| G["Xác minh access denial + audit"]
    F -->|Có hoặc nghi compromise| H["Generate replacement theo policy"]
    H --> I["Cutover producers, consumers, trusted recipients"]
    I --> J["Rewrap / re-encrypt / trust update theo loại key"]
    J --> K["Verify, restore, stop old use"]
    G --> L["Lưu evidence và residual risk"]
    K --> L
    L --> M["Hoàn tất change/incident và giám sát"]
~~~

### 10.1. Bước 1: nhận sự kiện và xác định mức khẩn

Input tối thiểu:

- **Event ID** ổn định, loại JOINER/MOVER/LEAVER/INCIDENT.
- Identity/person và aliases trong IdP, cloud, source-control, CI, VPN, secret manager.
- Thời điểm effective, vùng hệ thống/nhóm liên quan.
- Cấp độ rủi ro, có nghi ngờ credential hoặc key compromise không.
- Người chịu trách nhiệm phối hợp, approver và deadline theo chính sách.
- Những điều kiện đặc biệt: legal hold, đang điều tra, nghỉ việc đột xuất.

Nếu nghi ngờ nội gián, **không đợi đến kỳ rotation hằng tháng**; kích hoạt quy trình containment phù hợp.

### 10.2. Bước 2: thu hồi quyền trước khi phát sinh thêm lạm dụng

Tùy sự kiện và chính sách:

1. Disable/restrict identity; revoke active sessions, refresh tokens, PAT và SSH access.
2. Revoke **KMS grants**, quyền AssumeRole/PassRole, KeyAdmin, Sign/Decrypt/Unwrap.
3. Khóa khả năng sửa **key policy, IAM roles, HSM settings và audit destinations**.
4. Thu hồi VPN, bastion, CI deployment credentials, Kubernetes access và secret manager grants.
5. Đọc lại **effective permissions**, thử những negative access tests phù hợp.
6. Không tự phá hoặc xóa log có giá trị điều tra.

**Thứ tự có thể phải điều chỉnh** để tránh báo động nội gián hoặc giữ dịch vụ hoạt động; nhưng quyết định này phải nằm trong incident/HR/security workflow được phép, không do một developer tự chọn.

### 10.3. Bước 3: dựng access graph và key inventory

Truy vết các con đường:

~~~text
Employee identity
    |
    +-- SSO / IAM roles
    |      +-- KMS Sign / Decrypt grants
    |      +-- CreateGrant / ChangeKeyPolicy / AssumeRole
    |
    +-- Device / SSH / API tokens
    |
    +-- Secret manager / CI / source / logs
    |      +-- Shared HMAC, PSK, database credential
    |
    +-- HSM custodian / recovery shares
    |
    +-- Datasets / tenant scopes
           +-- DEKs --> encrypted DEKs --> KEKs
           +-- Signing keys --> public trust/JWKS/certs
~~~

Nếu key inventory không có mối liên hệ **key material ↔ owner ↔ consumers ↔ datasets ↔ backups**, sẽ khó chọn scope rotation mà không gây lỗi dịch vụ.

### 10.4. Bước 4: phân loại theo *exposure*, không chỉ theo vai trò

Câu hỏi quan trọng: **Người rời vai trò có thể lấy một bản sao key và dùng nó sau khi mất IAM hay không?**

- KMS có **non-exportable** thực sự không?
- Có quyền **Decrypt** để lấy plaintext DEK hoặc dữ liệu không?
- Có quyền **GenerateDataKey** trả plaintext DEK về JVM không?
- Secret manager cho phép đọc HMAC/PSK rõ không?
- Có truy cập source/CI/log/backup chứa secret không?
- Có thiết bị bị mất, hay token từng sử dụng từ endpoint không tin cậy không?
- Có đường self-escalation để export/cấp grant hay không?

Kết quả nên ghi: **NO_EVIDENCE_OF_MATERIAL_ACCESS**, **POTENTIALLY_EXPOSED**, **CONFIRMED_EXPOSED** hoặc trạng thái tương đương, kèm **mức độ tin cậy chứng cứ**. Không suy “không thấy event ExportKey” thành an toàn nếu logging chưa bao phủ.

### 10.5. Bước 5: lên phương án cutover theo loại secret

Nếu cần rotate:

- Sinh material **mới thực sự**, không chỉ đổi alias.
- Xác định **new key ID/version, algorithm, purpose, owner và cryptoperiod**.
- Cập nhật consumer inventory và lịch cutover, negative tests.
- Phân phối wrapped key hoặc credential qua kênh xác thực, không gửi raw key qua chat/HTTP plaintext.
- Kiểm tra old-key acceptance đã dừng đúng phạm vi.
- Chỉ xử lý destroy khi **backup/retention/key dependencies** đã được xác minh.

### 10.6. Bước 6: xác minh và đóng vụ việc

Một thay đổi chỉ được đóng sau khi có bằng chứng từ **IdP/IAM/KMS và application**, không chỉ trạng thái của ticket. Ghi rõ **những loại key đã rotate, những loại chỉ revoke quyền, lý do, test results và rủi ro còn lại**.

## 11. Rotation HMAC, PSK và secret dùng chung giữa nhiều người

**Shared secret** thường là loại phải rotation sớm nhất khi một người từng biết giá trị rõ ràng, vì không có cơ chế từ xa nào xóa chắc chắn bản sao mà người đó giữ.

Ví dụ một đội từng dùng **HMAC key chung** để xác thực webhook của nhiều ứng dụng. Một thành viên chuyển sang phòng ban không còn nhiệm vụ liên quan. Nếu thành viên đó có quyền đọc nguyên HMAC secret trong secret manager, tổ chức cần xem xét thay secret của phạm vi này.

### 11.1. Quy trình rotation an toàn

1. **Generate secret mới** bằng CSPRNG/KMS/secret manager được duyệt.
2. Tạo **version mới** (ví dụ v2), gán đúng purpose và owner.
3. **Provision v2** tới producers/consumers bằng authenticated channel, giới hạn quyền.
4. Cho phép kiểm chứng **MAC theo key ID/version** trong một cửa sổ ngắn nếu policy và giao thức yêu cầu.
5. Chuyển producers sang **ký/tạo MAC bằng v2 duy nhất**.
6. Xác nhận mọi consumer đã nhận v2 và đo old-version traffic.
7. **Ngừng chấp nhận v1** theo thời điểm policy, kể cả các workers offline.
8. Revoke hoặc destroy v1 theo retention/dependencies và incident severity.
9. Audit chứng cứ consumer cutover và lỗi rollback/replay.

### 11.2. Dual-read tạm thời có rủi ro

Trong migration, verifier có thể tạm nhận v1 và v2 để tránh downtime. Nhưng nếu **v1 đã bị lộ**, giữ nhận v1 tiếp tục cho attacker khả năng giả mạo. Phải quyết định **có được duy trì compatibility window hay không** theo severity, không áp dụng dual-read mặc định cho mọi incident.

### 11.3. Replay và key version

Một webhook MAC hợp lệ dưới key v1 có thể bị replay nếu giao thức thiếu timestamp/challenge/nonce/operation state. Rotation không thay thế **anti-replay**. Khi v1 bị chặn, verify phải **từ chối v1**, không fallback vô hạn chỉ vì legacy consumer chưa cập nhật.

### 11.4. Tránh master shared secret cho toàn tổ chức

Nếu một HMAC/PSK dùng cho nhiều environments, services hoặc tenants, mỗi lần nhân sự thay đổi có thể buộc rotation diện rộng. **Tách secret theo purpose, environment, tenant và consumer scope** từ đầu giúp giảm blast radius và dễ thực hiện leaver rotation.

## 12. Rotation KEK trong KMS/HSM khi thay key custodian

**KEK (Key Encryption Key)** thường bảo vệ nhiều DEKs. Một người rời vai trò KMS/HSM operator không nhất thiết đồng nghĩa họ đã biết KEK rõ.

### 12.1. Khi KEK không exportable và audit đáng tin

Nếu KEK được tạo trong KMS/HSM, policy không cho export raw bytes và người đó chỉ có quyền quản trị đã được kiểm soát, hành động ưu tiên thường gồm:

- Revoke **KMS KeyAdmin/ChangeKeyPolicy/CreateGrant** và login của người đó.
- Kiểm tra quyền gián tiếp, KMS grant/role sessions.
- Thay custodians/quorum và quyền recovery nếu người đó nắm share.
- Rà soát KMS logs: Sign/Decrypt/Unwrap, policy modifications và attempted exports.
- Đánh giá nhu cầu **KEK rotation** theo key policy và mức độ tin cậy của kiểm soát.
- Verify tính khả dụng của DEKs/datasets/backup trước khi thực hiện thay material.

**Không kết luận “non-exportable = không có rủi ro”**. Principal từng có quyền Decrypt có thể đã **lấy plaintext DEK** qua API, hoặc lạm dụng KMS như oracle để lấy plaintext data.

### 12.2. Khi KEK đã có thể bị sao chép

Nếu KEK được export dưới dạng rõ, backup thiếu kiểm soát hoặc người đó nắm material đủ khôi phục KEK:

1. Xử lý như **potential/confirmed KEK compromise** theo evidence.
2. Ngừng các phép Wrap mới dưới KEK cũ.
3. Sinh **KEK mới** trong miền bảo vệ được phê duyệt.
4. Rewrap những DEKs còn cần sử dụng, cập nhật keyRef/material version.
5. Đánh giá những **encrypted DEK blobs** có thể đã bị attacker thu thập trước đây.
6. Nếu attacker có khả năng unwrap DEKs cũ, đánh giá **thay DEK và re-encrypt** dữ liệu có nguy cơ.
7. Test restore và xác minh consumers đã cutover.
8. Giữ/retire/destroy KEK cũ đúng dependencies, không xóa mất dữ liệu còn hợp lệ.

### 12.3. Rewrap DEK không phải re-encrypt payload

~~~mermaid
flowchart TD
    P["Ciphertext + AES-GCM nonce/tag"] --> D["DEK-A"]
    D --> W1["Wrapped DEK dưới KEK-v1"]
    W1 --> R["KMS Rewrap"]
    R --> W2["Wrapped DEK dưới KEK-v2"]
    W2 --> P
    N["Payload vẫn dùng DEK-A; không đổi ciphertext"] --> P
~~~

Sơ đồ biểu diễn ý nghĩa logic, không phải biến đổi ciphertext trực tiếp. Khi **DEK-A không lộ**, rewrap dưới KEK-v2 có thể đủ cho **planned KEK rotation**. Nhưng nếu DEK-A đã lộ, **rewrap không khiến DEK trở lại bí mật**.

### 12.4. KEK rotation không reset nonce state của DEK

Đổi KEK nhưng vẫn dùng **DEK-A** cho AES-GCM không tạo nonce namespace mới. Mọi writer dùng DEK-A vẫn phải tránh tái sử dụng **(DEK-A, nonce)**, kể cả sau rotation và restart.

## 13. Rotation DEK khi nhân sự có thể đã lấy dữ liệu

**DEK (Data Encryption Key)** trực tiếp bảo vệ ciphertext. Nếu một người có thể đã lấy **plaintext DEK**, những ciphertext hiện tại và các bản sao cũ có thể giải mã được bên ngoài hệ thống.

### 13.1. Quy trình thay DEK

1. Xác định DEK material và **tất cả objects/tenants/backups** được mã hóa bởi material đó.
2. Containment: chặn Encrypt mới dưới DEK cũ nếu cần theo severity.
3. Generate DEK mới, đúng thuật toán, entropy và key usage policy.
4. Decrypt/Verify ciphertext cũ dưới quyền được phê duyệt.
5. **Re-encrypt payload** dưới DEK mới với nonce/tag/AAD đúng.
6. Wrap DEK mới dưới KEK phù hợp.
7. Cập nhật encrypted DEK, nonce, ciphertext/tag, key reference/version **một cách nhất quán**.
8. Verify integrity, tenant authorization và backup restore.
9. Cutover readers/writers; retire/revoke material cũ sau dependency review.

**Đổi keyRef trong metadata không phải thay DEK** nếu ciphertext vẫn được mã hóa bằng DEK cũ.

### 13.2. Hậu quả dữ liệu đã bị lộ

Ngay cả khi re-encrypt hoàn tất, attacker đã có plaintext trước đó vẫn giữ được nội dung. Cần đánh giá **data exposure, dữ liệu nhạy cảm, trách nhiệm thông báo và evidence** theo chính sách.

### 13.3. Tránh hủy DEK cũ trước khi tất cả consumers đã chuyển

Trong quá trình migration có thể cần một số readers hỗ trợ DEK cũ cho dữ liệu lịch sử; nhưng **không cho producer tiếp tục Encrypt mới dưới material đã bị revoke hoặc compromise**. Thời gian chuyển phụ thuộc incident severity và business continuity, không mặc định mở compatibility window dài.

## 14. Rotation private signing keys và trust khi người ký thay đổi

Chữ ký số có hai bình diện:

- **Private signing key:** dùng tạo chữ ký; phải được bảo vệ và hạn chế người được phép Sign.
- **Public verification key/certificate:** dùng kiểm tra chữ ký; có thể cần duy trì cho lịch sử dù private key đã nghỉ.

### 14.1. Người từng có quyền Sign nhưng không export private key

Một người rời vai trò người ký được ủy quyền. Nếu private key **non-exportable trong HSM**, chữ ký được tạo qua HSM và audit đủ đáng tin, có thể trọng tâm là:

1. Revoke **Sign authorization và sessions** của người đó.
2. Thu hồi quyền thay signing policy/quorum và approval.
3. Kiểm tra những chữ ký được tạo gần thời điểm chuyển vai trò.
4. Cập nhật owner/approver và signer identity mapping.
5. Xem chính sách có yêu cầu **signing key mới khi đổi người ký** hay không (đặc biệt key gắn danh tính cá nhân).

**Không mặc định một khóa ký tổ chức và một khóa ký cá nhân là cùng loại.** Khóa gắn danh tính cá nhân thường có chính sách khác khóa thuộc một ứng dụng/doanh nghiệp.

### 14.2. Khi private key đã bị lộ

Nếu người nghỉ việc có thể giữ bản sao private key:

- Tạo **key pair mới** trong HSM/KMS hoặc miền bảo vệ phù hợp.
- Cập nhật **certificate/JWKS/trust store/recipients** theo mục đích.
- Revoke/disable old signing authorization và **thông báo verifiers** theo trust policy.
- Đánh giá token/chữ ký đã phát hành, những thời điểm ký và cơ chế timestamp.
- Thiết kế **cutover** để dữ liệu mới dùng key mới, dữ liệu lịch sử được xử lý theo chính sách bằng chứng.
- Không chỉ DisableKey trong HSM: attacker có thể ký **ngoài HSM** bằng bản sao đã lấy.

### 14.3. JWT signing key và kid

Nếu một nhân sự từng giữ private key ký JWT hoặc có quyền đẩy secret lên CI, phải đánh giá nguy cơ **forge token**. Rotation cần:

1. Key mới, kid mới và public JWKS được phân phối qua issuer đáng tin.
2. Signing producer chuyển key, verifiers cập nhật trust và algorithm allowlist.
3. Nếu old key compromise, xử lý **old tokens, revocation/expiry, cache refresh** theo severity.
4. Không chấp nhận tùy ý JWKS URL/kid do token chưa xác thực tự chỉ đến.
5. Audit thay đổi issuer/trust chain và xác minh không có verifier còn tin old compromised key.

### 14.4. Public key không phải secret cần rotate vì bị xem

Việc một nhân viên biết **public key** của tổ chức không phải lý do rotate private key. Nhưng nếu có thể **thay public key trong trust store** hoặc phân phối key giả, cần khắc phục **authorization và trust distribution** vì có nguy cơ impersonation/MITM.

## 15. SSH keys, API tokens, certificates và máy của người rời đi

Nhóm credentials này thường liên quan **quyền truy cập** nhiều hơn dữ liệu đã mã hóa, nhưng chúng có thể trở thành đường để chiếm KMS/secret manager.

### 15.1. SSH

- Loại bỏ public key của người rời đi khỏi **authorized_keys**, bastion, Git hosting hoặc SSH CA policy theo kiến trúc.
- Vô hiệu chứng chỉ SSH/session nếu cần; kiểm tra máy/laptop còn giữ private key.
- Nếu nhiều người dùng chung một SSH private key, cần **thay cặp khóa chung** và chấm dứt thói quen dùng chung.
- Kiểm tra automation sử dụng private key cá nhân; chuyển sang **service identity** có owner và rotation rõ.

### 15.2. API/PAT và service credentials

- Thu hồi PAT/API token thuộc tài khoản cá nhân.
- Tìm script/bot sử dụng token của người rời đi.
- Cấp credential mới theo service account/workload identity **không phụ thuộc người đó**.
- Cập nhật consumers và kiểm tra không có job ngầm dùng token cũ.
- Không sao chép token cũ vào ticket để “chuyển giao”.

### 15.3. mTLS/client certificates

Nếu private key của client certificate nằm trên thiết bị của nhân viên:

- Xác định certificate thuộc **user identity hay service identity**.
- Revoke/rotate certificate/key pair tương ứng, cập nhật trust anchors khi cần.
- Xác minh revoked cert không còn được chấp nhận sau cache/OCSP/CRL policy.
- Không thay toàn bộ TLS server keys nếu rủi ro chỉ giới hạn ở client credential và không có exposure khác.

### 15.4. Thiết bị, browser sessions và local vault

Thu hồi laptop, điện thoại, FIDO tokens, local vault sessions, VPN access và SSH agent credentials theo policy. Một **lệnh remote wipe** có thể giảm nguy cơ nhưng không phải bằng chứng tuyệt đối mọi secret từng được sao chép đã biến mất.

## 16. HSM custodians, recovery shares và break-glass access

Một số tổ chức lưu key trong HSM hoặc có **threshold recovery/unseal**. Khi một custodian rời vai trò, cần xem mức độ người đó có thể tham gia khôi phục/điều khiển key.

### 16.1. Những trường hợp cần đánh giá

| Tình huống | Rủi ro | Hành động |
|---|---|---|
| Chỉ có HSM operator login | Có thể thực hiện thao tác theo quyền cũ | Revoke identity/policy, audit |
| Có smartcard/token của operator | Có thể còn credential vật lý | Thu hồi, thay/revoke credential và test deny |
| Giữ recovery share chưa bị thu hồi | Có thể tham gia quorum ngoài ý muốn | Thay share/custodian hoặc reconstitute theo policy |
| Là người duyệt duy nhất | Mất SoD/availability | Bổ nhiệm người mới, maker-checker |
| Có bản copy raw KEK/backup material | Có thể unwrap offline | Incident rotation và đánh giá DEK exposure |
| Có quyền sửa audit/config | Che dấu sử dụng sai | Thu hồi admin rights, bảo vệ evidence |

### 16.2. Re-share không đồng nghĩa rekey toàn bộ

Trong một **threshold scheme**, có thể cần thay shares/custodians theo cơ chế được thiết kế mà không nhất thiết thay mọi DEK trong doanh nghiệp. Tuy nhiên, nếu **threshold đủ shares** đã có khả năng lộ, phải đánh giá **master secret compromise** và rotation/reconstitution theo đúng tính chất của scheme.

### 16.3. Break-glass đúng cách

Trường hợp người rời đi từng giữ quyền khẩn cấp, tổ chức cần:

- Giữ ít nhất một **recovery path hợp lệ** sau khi revoke.
- Dùng **JIT emergency role** với TTL, approval và audit.
- Không “để chung một mật khẩu emergency” mà ai cũng từng biết.
- Thử khả năng phục hồi có kiểm soát, không chờ đến outage mới phát hiện thiếu custodian.

## 17. Quản lý inventory cho quyết định rotation

Một key registry nên hỗ trợ truy vấn **key/material ↔ người/role ↔ principal ↔ consumers ↔ dữ liệu**.

| Thuộc tính | Ví dụ | Tác dụng khi có Leaver/Mover |
|---|---|---|
| keyId/materialVersion | orders-dek-v12 | Định danh material thực |
| keyType/algorithm/usage | AES-GCM DEK; HMAC-SHA256; ECDSA Sign | Chọn cách rotate tương ứng |
| owner/custodian | team-payments / role-key-admin | Tìm người quyết định và người thực thi |
| exportability/provenance | HSM non-exportable; imported; generated | Đánh giá khả năng copy material |
| recipient principals | svc-orders-prod, contractor-role | Xác định ai từng có quyền |
| IAM grants/policy revision | grant-219, policy-v4 | Revoke và readback đúng thay đổi |
| data dependencies | invoices-2024..2026, backups | Cân nhắc re-encrypt/rewrap và destruction |
| cryptoperiod | originator-use-end, recipient-use-end | Xác định khi nào ngừng Encrypt/Sign mới |
| rotation history | priorKeyId, cutoverTime | Truy tìm key cũ và xử lý rollback |
| audit refs | KMS event IDs, approval IDs | Chứng minh hành động đã diễn ra |
| status | active/retired/revoked/pending-destroy/destroyed | Phân biệt logic lifecycle và provider state |

### 17.1. Nếu không biết người đó từng thấy secret nào?

**Không có inventory** không có nghĩa rủi ro bằng 0. Cần rà soát source, CI, secret manager access histories, key export logs, endpoint configuration và các tài liệu vận hành. Ghi nhận **những nguồn chứng cứ không còn hoặc chưa được bật** trước khi chấp nhận risk.

### 17.2. Đừng ghi plaintext secret vào inventory

Inventory chỉ cần **tham chiếu, metadata và permissions**, không cần raw KEK/DEK/private key. Một bảng tổng hợp có tất cả secret rõ sẽ trở thành single point of compromise.

## 18. Audit và bằng chứng đóng offboarding

Một audit event minh họa cho kỹ thuật thu hồi và rotation:

~~~json
{
  "changeId": "jml-event-2087",
  "eventType": "LEAVER",
  "identityRef": "employee-archived-42",
  "effectiveAt": "2026-11-28T02:00:00Z",
  "action": "REVOKE_KMS_GRANT",
  "keyRef": "kms/prod/orders-kek",
  "grantRef": "grant-219",
  "executedBy": "iam-automation-prod",
  "result": "SUCCESS",
  "verifiedAt": "2026-11-28T02:02:00Z",
  "evidenceRef": "audit-event-4491"
}
~~~

**Không đặt password, plaintext key, bearer token hay toàn bộ PII vào audit**. Identity references có thể cần pseudonymization và kiểm soát quyền xem theo chính sách riêng tư.

### 18.1. Những bằng chứng nên thu thập

- HR/manager event và thời điểm hiệu lực được phê duyệt.
- IdP disable/session revocation results.
- IAM/KMS grants và **effective permissions readback**.
- Secret manager/CI/SSH/API token revocation status.
- Key inventory & impact matrix cho material cần rotate.
- Chứng cứ **Generate new material, distribution, consumer cutover**.
- Negative tests chứng minh principal cũ không còn quyền.
- Nếu thay DEK: re-encryption coverage và restore test.
- Nếu thay signing key: trust propagation/JWKS/certificate status.
- Đối với outstanding exceptions: owner, deadline và risk acceptance.

### 18.2. Không coi HTTP 200 hoặc ticket DONE là final verification

Một API gọi thành công có thể chỉ cho biết yêu cầu **được nhận**, chưa chứng minh mọi regions/consumers đã cập nhật, grant đã mất hiệu lực hoặc key cũ không còn được chấp nhận.

### 18.3. Bảo vệ audit khỏi người bị thu hồi quyền

Nếu nhân viên có quyền **xóa logs, sửa KMS policy hoặc CI evidence**, cần thu hồi và cô lập các quyền đó, giữ evidence độc lập. Không kết luận “không có misuse” nếu audit không được bật đầy đủ.

## 19. Khôi phục dữ liệu, backup và crypto-shredding khi đổi nhân sự

Tác động lớn của rotation là khả năng **tiếp tục Decrypt/Verify dữ liệu lịch sử**.

### 19.1. Backup cần cả ciphertext và khả năng dùng key

Backup ciphertext/encrypted DEK chỉ có thể restore khi còn:

- Nonce, authentication tag, AAD/context schema và format version.
- Encrypted DEK và **đúng KEK material/key reference**.
- KMS/HSM recovery path, permissions và DR roles hợp lệ.
- Reader tương thích với thuật toán/version lịch sử.

**Nếu Destroy KEK vì operator nghỉ việc trong khi archive còn DEKs chỉ được bọc bởi KEK đó, dữ liệu có thể mất vĩnh viễn.**

### 19.2. Retire khác Destroy

**Retire** có thể chặn Encrypt/Sign mới nhưng giữ Decrypt/Verify lịch sử theo policy. **Destroy** loại bỏ material khi đã không còn phụ thuộc. Một Leaver event không phải lý do tự động destroy mọi key mà nhân viên từng quản trị.

### 19.3. Crypto-shredding và ngưỡng bảo đảm

Nếu mục tiêu là làm dữ liệu không còn giải mã được bằng cách hủy key, cần biết mọi bản sao/recovery path và **scope của key**. Không hủy KEK dùng chung cho nhiều tenants để xóa dữ liệu một nhân viên. Đồng thời, **hủy key ở KMS không thể xóa bản sao raw key mà người đó đã mang đi**.

### 19.4. DR khi key custodian rời tổ chức

Một rủi ro vận hành khác là **chỉ còn một người biết cách phục hồi HSM/quorum**. Offboarding phải chuyển giao kiến thức thủ tục, recovery roles và evidence đủ cho diễn tập restore, nhưng **không copy raw master key sang wiki hoặc ticket** để bàn giao.

## 20. Java 17: công cụ lập kế hoạch đánh giá rotation theo biến động nhân sự

Một hệ thống tự động hóa offboarding nên **phân loại và tạo công việc cần kiểm tra**, không tự động DestroyKey hay Reencrypt toàn bộ dữ liệu chỉ từ một sự kiện HR. Ví dụ Java 17 dưới đây nhận **loại sự kiện JML, loại secret và khả năng vật liệu đã lộ** để đưa ra nhóm hành động cần người có thẩm quyền xác minh.

**Đây là policy-planning demo**, không phải implementation KMS/IdP. Nó **không gọi cloud API, không thu hồi tài khoản thật, không rotate key thật**. Trong production cần source-of-truth về quyền, human approval cho thao tác rủi ro, idempotency, security evidence và status từ provider.

~~~java
import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;

public final class PersonnelRotationPlanner {
    public enum ChangeType {
        JOINER, MOVER, LEAVER, SECURITY_INCIDENT
    }

    public enum KeyKind {
        API_CREDENTIAL,
        SHARED_HMAC_OR_PSK,
        DATA_ENCRYPTION_KEY,
        KEY_ENCRYPTION_KEY,
        PRIVATE_SIGNING_KEY,
        NON_EXPORTABLE_KMS_KEY,
        RECOVERY_SHARE
    }

    public enum ReviewAction {
        APPROVE_LEAST_PRIVILEGE,
        REVOKE_OLD_ACCESS,
        REVOKE_ACTIVE_SESSIONS,
        REVIEW_EFFECTIVE_IAM,
        REVIEW_KMS_AND_SECRET_AUDIT,
        PRESERVE_EVIDENCE,
        ASSESS_MATERIAL_EXPOSURE,
        ROTATE_API_CREDENTIAL,
        ROTATE_SHARED_SECRET,
        ASSESS_NEW_DEK_AND_REENCRYPT,
        ASSESS_NEW_KEK_AND_REWRAP,
        ASSESS_SIGNING_KEY_AND_TRUST,
        ASSESS_RECOVERY_SHARE_RECONSTITUTION,
        VERIFY_CONSUMER_CUTOVER,
        VERIFY_BACKUP_RESTORE
    }

    public record PersonnelEvent(
        String changeId,
        ChangeType type,
        boolean suspectedCompromise
    ) {}

    public record KeyObservation(
        KeyKind kind,
        boolean plaintextMaterialAccessPossible,
        boolean materialCopySuspected,
        boolean keyWasNonExportable
    ) {}

    public record ReviewPlan(
        String changeId,
        Set<ReviewAction> requestedReviews,
        boolean requiresSecurityApproval
    ) {}

    public static ReviewPlan plan(
            PersonnelEvent event,
            KeyObservation observation) {
        Objects.requireNonNull(event);
        Objects.requireNonNull(event.changeId());
        Objects.requireNonNull(event.type());
        Objects.requireNonNull(observation);
        Objects.requireNonNull(observation.kind());

        if (event.changeId().isBlank()) {
            throw new IllegalArgumentException(
                "Missing change ID");
        }

        EnumSet<ReviewAction> actions =
            EnumSet.of(
                ReviewAction.REVIEW_EFFECTIVE_IAM,
                ReviewAction.REVIEW_KMS_AND_SECRET_AUDIT);

        if (event.type() == ChangeType.JOINER) {
            actions.add(ReviewAction.APPROVE_LEAST_PRIVILEGE);
            return new ReviewPlan(
                event.changeId(), Set.copyOf(actions), false);
        }

        // Mover/Leaver/Incident: phải kiểm tra thu hồi quyền.
        actions.add(ReviewAction.REVOKE_OLD_ACCESS);
        actions.add(ReviewAction.REVOKE_ACTIVE_SESSIONS);
        actions.add(ReviewAction.ASSESS_MATERIAL_EXPOSURE);

        if (event.suspectedCompromise()) {
            actions.add(ReviewAction.PRESERVE_EVIDENCE);
        }

        boolean materialRisk =
            observation.plaintextMaterialAccessPossible()
            || observation.materialCopySuspected();

        if (materialRisk) {
            switch (observation.kind()) {
                case API_CREDENTIAL ->
                    actions.add(
                        ReviewAction.ROTATE_API_CREDENTIAL);
                case SHARED_HMAC_OR_PSK ->
                    actions.add(
                        ReviewAction.ROTATE_SHARED_SECRET);
                case DATA_ENCRYPTION_KEY -> {
                    actions.add(
                        ReviewAction.ASSESS_NEW_DEK_AND_REENCRYPT);
                    actions.add(
                        ReviewAction.VERIFY_BACKUP_RESTORE);
                }
                case KEY_ENCRYPTION_KEY -> {
                    actions.add(
                        ReviewAction.ASSESS_NEW_KEK_AND_REWRAP);
                    actions.add(
                        ReviewAction.VERIFY_BACKUP_RESTORE);
                }
                case PRIVATE_SIGNING_KEY ->
                    actions.add(
                        ReviewAction.ASSESS_SIGNING_KEY_AND_TRUST);
                case RECOVERY_SHARE ->
                    actions.add(
                        ReviewAction
                            .ASSESS_RECOVERY_SHARE_RECONSTITUTION);
                case NON_EXPORTABLE_KMS_KEY -> {
                    // "Non-exportable" cần verify tại provider,
                    // không suy diễn chỉ từ nhãn của record.
                    actions.add(
                        ReviewAction.REVIEW_KMS_AND_SECRET_AUDIT);
                }
            }
            actions.add(ReviewAction.VERIFY_CONSUMER_CUTOVER);
        }

        if (event.suspectedCompromise()
                && observation.kind()
                    == KeyKind.PRIVATE_SIGNING_KEY) {
            actions.add(
                ReviewAction.ASSESS_SIGNING_KEY_AND_TRUST);
        }

        // Nếu material non-exportable, vẫn phải xét
        // lạm dụng API, grants và plaintext outputs.
        if (observation.keyWasNonExportable()) {
            actions.add(
                ReviewAction.REVIEW_KMS_AND_SECRET_AUDIT);
        }

        boolean approvalRequired =
            materialRisk || event.suspectedCompromise();

        return new ReviewPlan(
            event.changeId(),
            Set.copyOf(actions),
            approvalRequired);
    }

    public static void main(String[] args) {
        var event = new PersonnelEvent(
            "jml-2087", ChangeType.LEAVER, false);
        var exposure = new KeyObservation(
            KeyKind.SHARED_HMAC_OR_PSK,
            true,
            false,
            false);

        ReviewPlan review = plan(event, exposure);
        System.out.println(review.changeId());
        System.out.println(review.requestedReviews());
        // Không in raw secret hoặc IAM credentials.
    }
}
~~~

### 20.1. Điều ví dụ muốn dạy

- **JOINER** hướng về phê duyệt least privilege, không tự xoay mọi key.
- **MOVER/LEAVER** luôn kích hoạt rà soát quyền và sessions.
- Khi **plaintext HMAC/PSK có thể đã bị biết**, cần xét **rotate material**, không chỉ revoke IAM.
- Khi **DEK có nguy cơ lộ**, phải đưa **re-encryption assessment** vào kế hoạch.
- Khi **KEK có nguy cơ lộ**, đưa **rewrap cùng đánh giá DEK** vào kế hoạch.
- Khi **signing private key có nguy cơ lộ**, phải đánh giá **public trust và chữ ký lịch sử**.
- Khi người giữ **recovery share** rời đi, cần xét lại quorum/custody.
- **KMS non-exportable** không phải lý do bỏ qua việc xem xét Sign/Decrypt misuse hoặc các dữ liệu đã được giải mã.

### 20.2. Những giới hạn không được bỏ qua

Đoạn code **không tự kết luận an toàn và không thực hiện key rotation**. Thực tế cần:

1. Xác minh observation từ **KMS/IdP/secret manager/endpoint**.
2. Tách **plaintext key exposure** với **việc một người có quyền gọi API Decrypt**.
3. Định nghĩa **key scope** và tất cả consumers/datasets liên quan.
4. Thêm workflow **maker-checker/approval** theo mức độ rủi ro.
5. Thêm durable event log, idempotency key, retries và reconciliation.
6. Thực thi bằng SDK của provider với IAM tối thiểu, không hard-code keys.
7. Thu thập readback, negative tests, restore test và evidence.
8. Có quyền **dừng/hủy một plan chưa an toàn trước khi chạy**.

Đặc biệt, **review action không phải quyết định bắt buộc đổi material**; quyết định sau cùng phụ thuộc policy, threat model và chứng cứ.

### 20.3. Vì sao không gọi DeleteKey trong listener HR?

Việc lắng nghe một event rồi chạy **KMS ScheduleDeleteKey** ngay có thể làm mất DEKs, backups hoặc dữ liệu cần lưu, kể cả khi event được gửi nhầm. Những thao tác irreversible phải thông qua **dependency checks, approval và provider confirmation**; listener chỉ nên kích hoạt workflow có khả năng quan sát và dừng đúng cách.

## 21. Thiết kế workflow thực thi và trạng thái nhất quán

Một hệ thống production cần tách rõ **request accepted**, **access revoked**, **material rotated**, **consumers cut over**, **old material retired**, **backup restored** và **closure verified**.

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED: HR event received
    RECEIVED --> IDENTITIES_VERIFIED: Resolve principals
    IDENTITIES_VERIFIED --> ACCESS_REVOKING: Execute revocation
    ACCESS_REVOKING --> ACCESS_VERIFIED: Readback + negative tests
    ACCESS_VERIFIED --> EXPOSURE_ASSESSED: Inventory + evidence
    EXPOSURE_ASSESSED --> ROTATION_PLANNED: Material risk / policy trigger
    EXPOSURE_ASSESSED --> CLOSED: No rotation required + approval
    ROTATION_PLANNED --> MATERIAL_GENERATED: KMS/HSM create version
    MATERIAL_GENERATED --> CONSUMERS_UPDATING: Distribute credentials
    CONSUMERS_UPDATING --> CUTOVER_VERIFIED: Producers/readers validated
    CUTOVER_VERIFIED --> DEPENDENCIES_CLEARED: Restore + archive checks
    DEPENDENCIES_CLEARED --> CLOSED: Retirement/revocation completed
    CLOSED --> [*]
~~~

### 21.1. Idempotency và event duplication

HR webhooks/queues có thể giao lại một event. Nếu mỗi delivery tự sinh một key mới hoặc thu hồi quyền không đúng lúc, có thể gây churn và downtime.

- Dùng **changeId/eventId** ổn định.
- Ghi trạng thái workflow và kết quả provider.
- Nếu nhận lại sự kiện, đối chiếu trước khi chạy lại.
- Không coi KMS API timeout là “chưa thực hiện”; thực hiện **readback/reconciliation**.
- Không làm mất khả năng khôi phục chỉ vì workflow chạy hai lần.

### 21.2. Thứ tự revoke và rotate

Khi nghi ngờ compromise, **containment quyền** thường ưu tiên; nhưng nếu secret đã bị copy, đồng thời phải chuẩn bị **material mới** và chuyển consumers. Thứ tự chính xác cần tính đến:

- Độ khẩn, khả năng attacker tiếp tục sử dụng credential.
- Các hệ thống sẽ dừng hoạt động khi ngừng old secret.
- Dữ liệu nào sẽ được giải mã để migration.
- Có thể tạo **parallel verified path** với key mới không.
- Ai phê duyệt khả năng giữ old key trong cửa sổ ngắn.
- Có được **dual-verify** trong thời gian tương thích hay không (không mặc định với key bị compromise).

### 21.3. Separation of duties trong workflow tự động

Một service xử lý HR event **không nên có toàn quyền KMS CreateGrant, Decrypt, Delete và thay audit logs**. Có thể tách:

- HR event validator.
- Access revocation executor.
- Risk assessor + key owner.
- Rotation approver.
- Restricted key rotation worker.
- Independent verification/audit worker.

Mọi service chỉ được cấp **đúng operation và resource scope** nó cần.

## 22. Case study A: nhà thầu biết HMAC webhook secret chung

Một nhóm tích hợp nhận webhook từ đối tác. Secret HMAC chung được lưu trong secret manager nhưng mọi kỹ sư nhóm từng được quyền đọc raw value. Một nhà thầu hết hợp đồng vào cuối tháng.

### 22.1. Vì sao chỉ xóa tài khoản chưa đủ?

Người đó từng có khả năng lưu một bản sao HMAC secret. Secret có thể được dùng **ngoài secret manager** để tạo một MAC hợp lệ. Revoke tài khoản không thể khiến bản sao đã tải về biến mất.

### 22.2. Kế hoạch xử lý

~~~mermaid
sequenceDiagram
    participant H as HR / Owner
    participant V as Secret manager
    participant P as Webhook sender
    participant R as Webhook verifier
    participant A as Audit
    H->>V: Revoke contractor access + active sessions
    H->>V: Create new HMAC secret v2
    V-->>P: Provision v2 qua IAM/TLS
    V-->>R: Provision v2 qua IAM/TLS
    P->>R: Webhook mới ký bằng v2
    R-->>A: Verify + record version usage
    H->>R: End old-key acceptance v1
    R-->>A: Denied requests under v1
~~~

1. Revoke tài khoản, role, sessions và quyền đọc secret manager của nhà thầu.
2. Generate **HMAC secret mới** và chọn version/cryptoperiod.
3. Provision đến **mọi producer/consumer** theo least privilege.
4. Chuyển sender sang ký v2, xác minh webhook verifier v2 hoạt động.
5. Ngừng chấp nhận v1 sau khoảng thích hợp với policy và mức độ rủi ro.
6. Tìm bản sao v1 trong **CI logs, code, wiki, backups, DLQ**.
7. Audit old secret use và xử lý các requests nghi giả mạo.

### 22.3. Rủi ro compatibility

Nếu verifier tạm nhận cả v1 và v2, nhà thầu có thể tiếp tục giả MAC bằng v1. Nếu có bằng chứng misuse hoặc nghi ngờ cao, **không dùng một cửa sổ tương thích dài** chỉ để tránh một service legacy bị gián đoạn.

### 22.4. Thiết kế lâu dài

- Không cho mọi developer đọc HMAC secret thật.
- Tách secrets theo partner/application/environment.
- Dùng key ID/version và expiry rõ, anti-replay cho messages.
- Đặt owner và quy trình rotation tự động có kiểm thử.
- Không gửi raw secret trong email/chat/ticket để bàn giao.

## 23. Case study B: KMS administrator chuyển nhóm

Một KMS administrator được luân chuyển từ production sang một nhóm QA. KEK của hệ thống thanh toán nằm trong cloud KMS, cấu hình **non-exportable**, quản lý encrypted DEKs của nhiều hóa đơn.

### 23.1. Sai lầm phổ biến

Nhóm dự án đề nghị **re-encrypt toàn bộ kho hóa đơn ngay** vì người đó từng là KeyAdmin. Điều này có thể chưa đúng nếu:

- KMS giữ key material an toàn và không cho export.
- Người đó chỉ có quyền policy/admin, chưa từng có Decrypt/Unwrap.
- Không có dấu hiệu grants/credential compromise hoặc chính sách truy cập sai.
- Từng quyền được bảo vệ bởi SoD và audit đủ tin cậy.

**Không kết luận chưa cần rotate chỉ từ nhãn “non-exportable”**: phải kiểm tra quyền có hiệu lực và log thay đổi grants/policy, KMS operations.

### 23.2. Quy trình đánh giá đúng

1. Thu hồi **KeyAdmin, ChangeKeyPolicy, CreateGrant, AssumeRole** cũ.
2. Revoke các sessions/credentials của người đó liên quan production.
3. Xác minh có thể **tự cấp Decrypt/Unwrap** qua quyền gián tiếp trước đây hay không.
4. Kiểm tra policy changes, grants, KMS Decrypt/Sign/Unwrap events.
5. Tìm evidence của **plaintext DEK exposure** từ các ứng dụng có quyền KMS.
6. Thay owner/approver, bảo đảm SoD và recovery path liên tục.
7. Quyết định theo exposure: có thể chỉ **IAM revoke + audit**, hoặc KEK rotate/rewrap nếu policy yêu cầu hoặc có rủi ro material.
8. Nếu DEK/plaintext data đã lộ, đánh giá **re-encrypt** và data incident.

### 23.3. Nếu quyết định rotate KEK theo chính sách

- Tạo KEK v2.
- Chuyển việc bọc **DEK mới** sang KEK v2.
- Rewrap các DEKs cũ cần di chuyển, với key references/material versions được ghi đúng.
- Test decrypt và backup restore.
- Retire KEK v1 theo dependency/recipient-use period.
- Không reset AES-GCM nonce state của DEKs còn nguyên.

**Bài học:** Rotation khi nhân sự thay đổi phải dựa trên **bản chất quyền và khả năng sở hữu material**, không chỉ tên chức danh.

## 24. Case study C: nhân viên sở hữu khóa ký riêng rời tổ chức

Một hệ thống ký JWT bằng private key nằm trong file trên server được quản lý bởi một nhân viên. Người này nghỉ việc, nhưng nhiều services vẫn verify token bằng public key tương ứng.

### 24.1. Threat model

- Có khả năng nhân viên giữ bản sao private key.
- Attacker có private key có thể tạo **chữ ký hợp lệ ngoài server**.
- Disable nhân viên trong IAM không ngăn sử dụng private key ở bên ngoài.
- Chỉ thay **kid trong config** mà không thay private key bytes không giảm rủi ro.
- Verifiers có thể cache JWKS hoặc chấp nhận old key đến hết token TTL.
- Token cũ và chữ ký lịch sử có retention/trust semantics riêng.

### 24.2. Kế hoạch đổi khóa có kiểm soát

1. Revoke account, sessions, CI/deployment privileges và server SSH access của nhân viên.
2. Tạo **key pair mới** trong KMS/HSM hoặc miền bảo vệ phù hợp.
3. Cập nhật signing service dùng private key mới và kid mới.
4. Phân phối public verification key qua **issuer/JWKS đáng tin**.
5. Kiểm tra verifier algorithm/issuer/audience/trust policy.
6. Xử lý old key trust và JWTs còn hiệu lực theo severity (expiry, revocation, cache).
7. Nếu key cũ compromise, chặn việc tạo token mới và đánh giá token giả trong lịch sử.
8. Không xóa bằng chứng/chứng chỉ lịch sử nếu policy yêu cầu verification.
9. Theo dõi old-kid usage và những verifiers chưa cutover.

### 24.3. Có bắt buộc ngay lập tức reject mọi token cũ?

Phụ thuộc **mức compromise, token lifetime, key scope và yêu cầu sẵn sàng dịch vụ**. Nếu private key đã có thể bị attacker dùng để forge token, tiếp tục trust old key tạo rủi ro lớn; phải xử lý theo incident policy. Nếu chỉ thay key theo kế hoạch và chưa có material exposure, một overlap window có thể là lựa chọn được phê duyệt, với phạm vi và thời hạn rõ.

**Bài học:** Chữ ký số đòi hỏi quản lý **cả private material và trust của verifier**, không chỉ đổi quyền người ký.

## 25. Case study D: người giữ recovery share rời đi

Một tổ chức dùng HSM backup/recovery với quorum nhiều người. Một custodian nghỉ việc nhưng vẫn còn nắm một recovery share.

### 25.1. Sai lầm nguy hiểm

- Chỉ thu hồi IAM account, bỏ qua smartcard/share vật lý.
- Chụp ảnh share rồi gửi cho người thay thế qua ticket.
- Tạo một plaintext master secret chung để khỏi phụ thuộc quorum.
- Hủy HSM key ngay để “không còn share cũ”, làm mất dữ liệu lịch sử.
- Gỡ một custodian mà không bổ nhiệm người mới, dẫn đến **không đạt threshold phục hồi**.

### 25.2. Cách quản lý

1. Kiểm kê **HSM operator card, share, token, recovery quorum** liên quan.
2. Thu hồi credential vật lý và quyền phần mềm của người rời đi.
3. Bổ nhiệm người thay thế được đào tạo và phê duyệt.
4. Theo tính chất scheme, **re-share/reconstitute** hoặc rotate secret nếu share exposure đủ nguy cơ.
5. Diễn tập recovery có giám sát, không tạo raw master key ra chat/wiki.
6. Bảo đảm key owner/approver/auditor tách biệt và logs được giữ.
7. Giữ DEKs/KEKs cần cho backup theo retention; chỉ destroy khi dependencies cleared.

**Bài học:** Với key custody và HSM, rotation khi nhân sự thay đổi còn là **quản trị người giữ quyền phục hồi**, không chỉ mật mã của dữ liệu.

## 26. Ưu tiên, thời hạn và kế hoạch cutover

Không có một con số **SLA xoay khóa duy nhất** phù hợp mọi loại nhân sự, dữ liệu và key type. Tổ chức cần định nghĩa thời hạn theo **threat model, phân loại dữ liệu, mức độ compromise, contractual/legal requirements và khả năng tự động hóa**.

### 26.1. Phân tầng ưu tiên minh họa

| Mức rủi ro | Dấu hiệu | Hướng xử lý |
|---|---|---|
| **Khẩn cấp** | Confirmed leak của private signing key/KEK/DEK hoặc insider misuse đang diễn ra | Containment tức thời theo incident policy; generate replacement và cutover theo scope |
| **Cao** | Nhân sự rời đi từng biết shared production HMAC/PSK, có thể giữ bản sao | Revoke access; rotate secret và chặn old acceptance theo deadline được phê duyệt |
| **Trung bình** | Người từng có quyền Decrypt/KeyAdmin thay vai trò, exposure chưa rõ | Revoke quyền, forensic/audit review, quyết định material rotation theo kết quả |
| **Thấp** | Chỉ có read-only public metadata/audit, không có key access | Cập nhật role/owner, readback và đóng evidence |

Đây là **ví dụ phân loại**, không phải quy định toàn cầu; một sự kiện liên quan dữ liệu nhạy cảm hoặc ảnh hưởng pháp lý có thể nâng mức ưu tiên dù khả năng lộ thấp.

### 26.2. Vì sao phải có cutover plan?

Cấp secret mới mà chưa chuyển consumer có thể gây:

- Token/MAC verification thất bại hàng loạt.
- Service mất quyền KMS Decrypt/Sign.
- Old producer tiếp tục phát dữ liệu dưới key cũ.
- DEK phiên bản mới không được lưu cùng wrapped DEK đúng.
- Backup restore thất bại nếu KEK cũ bị xóa.
- Verifier cache JWKS/certificate cũ không chấp nhận chữ ký mới.

Vì vậy cần **xác minh end-to-end**, không chỉ thấy KMS API báo RotateKey thành công.

### 26.3. Rollback và giới hạn của rollback

Khi rotated credential vì **lộ secret**, “rollback” về old compromised secret có thể mở lại lỗ hổng. Kế hoạch rollback phải ưu tiên **khôi phục dịch vụ bằng phiên bản mới hợp lệ**, ví dụ sửa consumer config/grants/metadata, thay vì khôi phục vật liệu đã bị compromise.

Với planned rotation chưa có compromise, một khoảng chuyển tiếp có thể được duyệt nếu key policy cho phép và được giới hạn thời gian, nhưng phải có dấu hiệu theo dõi **old key usage** và ngày ngừng chấp nhận.

## 27. Ma trận kiểm thử JML và rotation theo nhân sự

| Tình huống | Kết quả mong đợi |
|---|---|
| Nhân viên mới được gán role KeyAdmin không có approval | Policy từ chối |
| Mover từ production sang QA | Roles/grants production bị gỡ, quyền mới chỉ theo QA |
| Leaver disable SSO | Các session/tokens liên quan được revoke theo policy |
| Leaver còn có active AssumeRole session | Kiểm tra thực tế, chặn đường quyền còn hiệu lực |
| Người không có Decrypt vẫn có CreateGrant/ChangeKeyPolicy | Effective permissions review phát hiện khả năng tự nâng quyền |
| Người rời đi có SSH key trên bastion | Public key/cert bị gỡ khỏi trust và test login bị từ chối |
| Leaver có Git PAT trong CI pipeline | PAT bị rotate/revoke, pipeline chuyển service account |
| Nhân viên chỉ xem KMS audit dashboard | Không bắt buộc rotate raw KEK chỉ vì họ biết key ID |
| Người có quyền Decrypt nhưng KEK non-exportable | IAM revoke và audit review; quyết định material theo exposure |
| Người từng biết HMAC production | New material được generate, consumers cutover, old acceptance dừng |
| Webhook consumer chưa nhận HMAC v2 | Workflow không báo cutover hoàn tất |
| HMAC v1 bị compromise nhưng verifier chấp nhận v1 vô hạn | Negative test thất bại; policy cần chặn |
| Leaver giữ một recovery share | Custody/quorum được rà soát, re-share/reconstitute theo scheme |
| Thu hồi một HSM custodian khiến quorum không đủ | Recovery availability test phát hiện |
| Private signing key có thể đã export | Rotation/trust/JWKS/verifier updates được thực hiện theo incident |
| Chỉ đổi kid nhưng giữ private bytes cũ | Review không chấp nhận là key rotation |
| Token ký bằng old compromised key vẫn được accept | Verifier risk policy phát hiện/deny theo phương án |
| Rotate KEK-v1 sang KEK-v2 | Wrapped DEK/keyRef updated; DEK/ciphertext có thể giữ nguyên nếu phù hợp |
| KEK rotate mà nonce counter của DEK reset | Kiểm thử phát hiện sai key identity |
| Plaintext DEK đã lộ nhưng chỉ rewrap | Review yêu cầu đánh giá thay DEK/re-encrypt |
| DEK rotation thành công | Payload nonce/tag/ciphertext và encryptedDEK nhất quán |
| KMS outage khi rotation | Không fallback raw KEK trong chat/config |
| Rotation worker có quyền DeleteKey quá rộng | Least privilege/SoD test từ chối |
| HR event bị giao lại hai lần | Idempotent; không lặp material changes ngoài kế hoạch |
| KMS API timeout sau khi đã thực hiện | Readback/reconciler xác định trạng thái đúng |
| Một consumer offline trong lúc cutover | Theo dõi version/epoch, không tuyên bố xong sớm |
| Old service tiếp tục Sign sau leaver effective time | Alert và chặn theo policy |
| Snapshot còn encrypted DEK chỉ bọc bởi KEK-v1 | Destruction guard chặn xóa v1 |
| Hủy KEK mà chưa có restore test | Workflow từ chối cho tới dependency clearance |
| Admin cố tự phê duyệt việc export recovery key | Maker-checker policy từ chối |
| Audit sink bị người rời đi sửa/xóa | Independent audit control phát hiện hoặc chặn |
| JML event thiếu identity aliases | Workflow không âm thầm bỏ qua accounts còn tồn tại |
| Leaver account bị disable nhưng token còn dùng được | Negative test phát hiện propagation gap |
| Ngày cryptoperiod đến hạn dù không có JML | Scheduled rotation vẫn chạy |
| Incident đã re-encrypt nhưng có data bị lộ trước đó | Báo cáo residual risk, không tuyên bố dữ liệu quá khứ bí mật trở lại |
| Key inventory không biết owner hoặc dataset dependency | Không tự Destroy; mở remediation ticket |
| Audit về rotation | Có actor, approver, key refs/version, outcomes, không chứa raw key material |

### 27.1. Negative tests quan trọng hơn “ticket DONE”

Cần kiểm tra **người cũ không còn thực hiện được hành động bị cấm**:

- API KMS Decrypt/Sign/Wrap/Unwrap bằng principal cũ.
- Role assumption hoặc CreateGrant thông qua đường quyền gián tiếp.
- SSH/VPN/API token từng cấp.
- Secret manager read/export.
- Sign/Verify old-key acceptance theo chính sách.
- Truy cập dữ liệu/tenant ngoài phạm vi sau Mover event.

Không chạy destructive tests hoặc thử đọc dữ liệu production bằng credential thật ngoài môi trường thử nghiệm/ủy quyền. Chỉ thực hiện các kiểm tra phù hợp chính sách và không làm lộ secret trong test output.

### 27.2. Các kiểm thử không thể “chứng minh điều không xảy ra”

Audit thiếu coverage có thể không ghi nhận một lần export hoặc read. Nếu không có evidence đủ, phải **ghi uncertainty** và điều chỉnh kế hoạch theo rủi ro. Không lấy việc không tìm được log lộ secret làm chứng nhận chắc chắn secret chưa từng bị copy.

## 28. Những sai lầm thường gặp

| Sai lầm | Vì sao rủi ro | Thay thế |
|---|---|---|
| Mọi Leaver đều phải re-encrypt toàn bộ database | Không phân biệt loại quyền và exposure, tăng downtime | Exposure-based scope/approval |
| Chỉ disable IdP nhưng bỏ session/token/grants | Quyền cũ có thể còn hiệu lực | Revoke sessions/credentials, readback effective IAM |
| Người cũ biết HMAC secret nhưng chỉ revoke account | Có thể giữ raw secret | Rotate shared secret và chặn v1 |
| Đổi tên key alias rồi coi đã rotate | Material cũ không đổi | Generate material version mới thật |
| KMS KEK auto-rotate được coi là rotate toàn bộ DEKs | DEKs có thể giữ nguyên bytes | Phân biệt KEK rewrap với DEK re-encrypt |
| Rewrap DEK đã lộ | Attacker vẫn có plaintext DEK | Thay DEK và đánh giá re-encrypt |
| Tin non-exportable đồng nghĩa không thể misuse | KMS vẫn có thể bị gọi như Sign/Decrypt oracle | IAM/SoD/audit/business authorization |
| Chỉ nhìn role name, bỏ CreateGrant/AssumeRole | Có thể self-escalate | Effective permissions và role graph |
| Không rotate PAT dùng trong CI sau leaver | Token vẫn chạy automation | Chuyển sang workload identity, revoke credential |
| Gửi shared secret cho người thay thế qua email/chat | Tạo thêm bản sao không kiểm soát | Provision qua KMS/secret manager |
| Thu hồi role nhưng để lại HSM recovery share | Người cũ vẫn có yếu tố phục hồi | Re-share/custody update/quorum checks |
| Xóa master key khi key custodian nghỉ | Mất dữ liệu phụ thuộc | Dependency graph, restore test rồi mới hủy |
| Thay private signing key nhưng không cập nhật verifier | Chữ ký mới lỗi hoặc old compromised key vẫn được tin | JWKS/cert/trust rollout và audit |
| Đổi kid nhưng giữ bytes private key | Không làm key khó đoán hơn | Key pair mới từ nguồn tin cậy |
| Cho verifier tin key do token tự khai | Attacker có thể chỉ key giả | Trusted issuer/JWKS và allowlist |
| Quên offline consumers khi rotate | Old secret vẫn được dùng | Inventory, cutover evidence và expiry |
| Cho dual-verify vô hạn sau compromise | Old key vẫn giả mạo được | Hạn thời gian; chặn theo severity |
| Không tính snapshot/backup khi migration | Restore không dùng được key mới | Backup/DR dependency kiểm thử |
| Tạo raw KEK backup để “phòng mất người giữ” | Bản copy mới tăng nguy cơ lộ | HSM recovery/quorum đúng policy |
| HR event tự gọi DeleteKey | Có thể xóa key do gửi event lỗi | Approval/verification/dependency guard |
| Dùng audit log chứa plaintext DEK | Tạo nguồn secret leak | Chỉ refs và metadata |
| Cho KeyAdmin xóa KMS audit | Khó phát hiện misuse | Independent audit/SoD |
| Thời hạn scheduled rotation bị bỏ qua vì “vừa offboard xong” | Key vẫn có thể hết cryptoperiod/usage | Quản lý hai trigger riêng |
| Không làm negative access tests | Không biết quyền cũ đã mất thật chưa | Test deny theo role/scope |
| Không có fallback owner/recovery custodian | Business continuity suy giảm | Handover SoD và DR rehearsals |

## 29. Câu hỏi tự kiểm tra

**Câu 1. Nhân viên rời công ty có luôn bắt buộc thay mọi KEK/DEK không?**

**Trả lời:** Không. Phải đánh giá liệu họ có thể đã biết/lấy material hoặc lạm dụng quyền. Thu hồi identity, sessions, IAM grants và audit luôn quan trọng; rotation material phụ thuộc loại khóa, exposure và policy.

**Câu 2. Khác biệt quan trọng giữa revoke access và rotate key material là gì?**

**Trả lời:** Revoke chặn khả năng dùng hệ thống qua một identity; rotate thay bytes khóa/credential để giảm rủi ro bản sao secret từng bị giữ ngoài hệ thống.

**Câu 3. Một nhân viên biết rõ HMAC secret trước khi nghỉ, disable SSO có đủ không?**

**Trả lời:** Thường không. Họ có thể giữ bản sao, nên cần đánh giá rotate shared secret và ngừng verifier chấp nhận old version.

**Câu 4. Chỉ đổi KMS alias từ v1 sang v2 có tạo key mới không?**

**Trả lời:** Không được suy vậy. Cần chứng minh key material thực sự được thay; alias có thể chỉ là reference.

**Câu 5. Vì sao KEK rotation thường có thể dùng rewrap?**

**Trả lời:** Khi DEK chưa lộ, có thể bọc cùng DEK dưới KEK mới mà không re-encrypt payload. Tuy nhiên nếu DEK/KEK compromise, cần đánh giá nguy cơ và thay DEK tương ứng.

**Câu 6. Nếu plaintext DEK đã lộ, rewrap có đủ không?**

**Trả lời:** Không. Bản sao DEK cũ vẫn có thể giải mã dữ liệu; phải xem xét thay DEK và re-encrypt.

**Câu 7. Key non-exportable trong HSM có ngăn người có quyền Sign giả mạo chứng từ không?**

**Trả lời:** Không tự động. Người có quyền có thể lạm dụng HSM như signing oracle nếu thiếu business approval và key usage controls.

**Câu 8. Khi người ký số đổi vai trò, điều gì cần làm với verifier?**

**Trả lời:** Kiểm tra quyền Sign và trust policy; nếu private signing key thay hoặc lộ, phải cập nhật public verification trust/JWKS/certificate và xem xét chữ ký/token lịch sử.

**Câu 9. Mover event chỉ cần thêm role mới là đủ không?**

**Trả lời:** Không. Phải thu hồi role/grants/sessions cũ để tránh quyền bị cộng dồn.

**Câu 10. Một người không có Decrypt trực tiếp nhưng có CreateGrant có thể gây rủi ro gì?**

**Trả lời:** Có thể tự cấp quyền hoặc tạo đường lạm dụng Key API. Cần kiểm tra effective permissions và self-escalation.

**Câu 11. Vì sao không hủy KEK ngay khi key custodian nghỉ?**

**Trả lời:** Encrypted DEK, archive và backup có thể phụ thuộc KEK đó; hủy sớm có thể gây mất dữ liệu vĩnh viễn.

**Câu 12. Nhân viên giữ một HSM recovery share cần xử lý như thế nào?**

**Trả lời:** Thu hồi quyền và vật giữ, rà soát threshold/custody, re-share/reconstitute hoặc rotate theo scheme và evidence; duy trì khả năng recovery.

**Câu 13. Tại sao việc gửi key mới qua chat để bàn giao không phù hợp?**

**Trả lời:** Tạo bản sao secret ngoài quyền và retention policy. Hãy dùng KMS/secret manager, authenticated provisioning hoặc HSM key ceremony phù hợp.

**Câu 14. Event HR được gửi lại hai lần có được khiến KMS sinh hai key mới không?**

**Trả lời:** Không mặc định. Workflow phải idempotent theo eventId/changeId và readback trạng thái trước khi thực hiện lại.

**Câu 15. Vì sao chỉ thấy KMS API thành công chưa chứng minh rotation hoàn tất?**

**Trả lời:** Consumers, JWKS verifiers, backup/DR và old-key acceptance có thể chưa chuyển; cần cutover/readback/end-to-end tests.

**Câu 16. Nếu auditing không ghi nhận lần ExportKey nào, có chắc secret chưa từng bị lộ không?**

**Trả lời:** Không nếu provider/export path/log coverage không đầy đủ hoặc secret đã xuất qua CI/log. Cần ghi sự không chắc chắn và đánh giá rủi ro.

**Câu 17. Cryptoperiod còn liên quan gì sau khi đã offboard nhân viên?**

**Trả lời:** Key vẫn phải tuân originator/recipient-use periods, expiry, algorithm strength, usage limits và scheduled rotation; JML chỉ là một trigger bổ sung.

**Câu 18. Đổi private signing key có tự làm chữ ký cũ không thể Verify không?**

**Trả lời:** Không. Chữ ký lịch sử có thể cần public key/trust tương ứng; việc chấp nhận hay từ chối phụ thuộc verification/revocation policy và bằng chứng thời gian.

**Câu 19. Vì sao re-encrypt dữ liệu sau sự cố không thể thu hồi thông tin đã lộ?**

**Trả lời:** Attacker có thể đã có plaintext hoặc bản sao key/ciphertext trước khi migration; key mới không xóa thông tin đó.

**Câu 20. Đóng một Leaver event cần bằng chứng kỹ thuật nào?**

**Trả lời:** Readback IdP/IAM/KMS/credential revocation, material exposure assessment, consumer cutover nếu rotation, negative access tests, backup/restore validation và audit/approval references.

## 30. Checklist triển khai Rotation khi nhân sự thay đổi

Trước khi đóng một sự kiện JML liên quan đến key management:

- **Event:** xác định JOINER/MOVER/LEAVER/INCIDENT, identity aliases, effective time, approver và severity?
- **Owner:** có data owner, key owner, custodian và security approver đúng vai trò?
- **Scope:** đã xác định người đó có access hoặc material possession đối với key/credential nào?
- **Identity:** IdP, SSO sessions, VPN, SSH, PAT, workload credentials đã được thu hồi/giới hạn?
- **Effective IAM:** đã kiểm tra role assumption, CreateGrant, ChangeKeyPolicy, PassRole và các đường self-escalation?
- **Material vs access:** đã phân biệt thay credential, revoke grant với rotate KEK/DEK/signing/HMAC material?
- **Exposure:** có bằng chứng exportability, plaintext access, secret manager/CI reads, endpoint incidents và KMS logs?
- **HMAC/PSK:** nếu secret từng được biết, có version mới, consumer cutover và old acceptance cutoff?
- **Private signing key:** có kiểm tra non-exportable, Sign audit, JWKS/cert/trust của verifiers và lịch sử ký?
- **KEK:** nếu rotate, có rewrap encrypted DEKs đúng scope, lưu keyRef/version và thử restore?
- **DEK:** nếu đã có thể lộ, đã đánh giá replace DEK/re-encrypt và sự cố dữ liệu?
- **Nonce:** KEK rewrap không reset nonce namespace của DEK còn giữ nguyên?
- **HSM/recovery:** đã thay custodians, smartcards, shares/quorum và giữ recovery path đúng chính sách?
- **Distribution:** không gửi plaintext keys qua chat, email, HTTP plaintext, logs hoặc CI artifacts?
- **Cryptoperiod:** originator-use/recipient-use periods, scheduled rotation và usage budgets được tôn trọng?
- **Continuity:** có plan cắt chuyển producers/consumers, retry, idempotency, khả năng phục hồi khi KMS timeout?
- **Audit:** có event IDs, approvals, key IDs/versions, operation outcomes mà không có raw secrets?
- **Verification:** có negative tests chứng minh principal cũ không thể Sign/Decrypt/Export/AssumeRole?
- **Backups:** encrypted DEKs, key material/version, retention và restore test đã được rà soát?
- **Revocation:** token/cert/grant, cache và old key acceptance được xử lý theo severity?
- **Destruction:** không xóa key còn dependencies; phân biệt PENDING_DELETION với DESTROYED có xác nhận?
- **Residual risk:** dữ liệu/secret có thể đã bị copy được ghi nhận và được xử lý theo incident policy?
- **Closure:** tất cả exceptions có owner, deadline, risk acceptance, bằng chứng và trạng thái cuối rõ ràng?

**Ghi nhớ:** **Rotation khi nhân sự thay đổi** không phải hành động “đổi toàn bộ khóa theo danh sách nhân viên nghỉ việc”. Đó là **quy trình đánh giá và cắt quyền theo danh tính, sau đó thay đúng những credentials/keys có nguy cơ tiếp tục bị sử dụng ngoài kiểm soát**. **Revoke IAM, rotate shared secret, rewrap KEK, re-encrypt dưới DEK mới và cập nhật trust của signing key** là các thao tác khác nhau. Chỉ khi kết hợp **JML, key inventory, KMS/HSM, IAM, SoD, cryptoperiod, envelope encryption, audit, backup/DR, verification và incident response** thì việc thay đổi nhân sự mới không kéo theo lỗ hổng sử dụng khóa hoặc mất khả năng phục hồi dữ liệu.
