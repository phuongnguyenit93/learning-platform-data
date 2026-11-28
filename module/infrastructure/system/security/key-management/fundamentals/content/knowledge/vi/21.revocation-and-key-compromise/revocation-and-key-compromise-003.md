# Emergency revocation (Thu hồi khẩn cấp quyền và khả năng sử dụng khóa mật mã)

## 1. Emergency revocation là gì?

**Emergency revocation** là quy trình **vô hiệu hóa khẩn cấp những quyền truy cập, thông tin xác thực hoặc khả năng sử dụng khóa không còn đáng tin**, thường được kích hoạt khi phát hiện **lộ khóa, chiếm đoạt tài khoản, lạm dụng KMS/HSM, giả mạo chữ ký, mất thiết bị chứa secret hoặc hành vi bất thường**.

Khác với rotation theo lịch, mục tiêu đầu tiên của emergency revocation là **containment**: chặn ngay việc tạo thêm thiệt hại. Việc thay key material, re-encrypt dữ liệu, cập nhật trust và hủy khóa có thể xảy ra tiếp theo nhưng **không phải thao tác đồng nhất**.

Ví dụ: một workload identity bị chiếm và có quyền gọi KMS Decrypt trên KEK của dịch vụ thanh toán. Nhóm bảo mật có thể cần **thu hồi phiên, revoke KMS grants và chặn principal** ngay. Nhưng xóa KEK lập tức có thể làm hàng triệu encrypted DEK không còn giải bọc được, ảnh hưởng dữ liệu và backup. Cần **chặn kẻ tấn công mà không phá hủy đường phục hồi hợp lệ**.

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài này thuộc chương **Revocation và compromise**, kết nối kiến thức về **khóa đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, IAM, cryptoperiod, audit và toàn bộ vòng đời khóa**.

**Nguyên tắc:** Thu hồi khẩn cấp là **quy trình nhiều lớp**, phải làm rõ **thu hồi quyền nào, đối với ai, đối với material hay operation nào, có hiệu lực từ lúc nào và được xác minh bằng bằng chứng gì**.

## 2. Bốn mục tiêu của một cuộc thu hồi khẩn cấp

| Mục tiêu | Câu hỏi cần trả lời | Ví dụ hành động |
|---|---|---|
| **Containment** | Làm sao chặn kẻ tấn công tiếp tục dùng quyền/khóa? | Revoke session, deny grant, disable key use, khóa compromised workload |
| **Preserve evidence** | Có thể điều tra ai dùng key, khi nào, với dữ liệu nào? | Bảo toàn KMS/IAM/audit events, time correlation, snapshot theo quy trình |
| **Safe replacement** | Làm sao cấp material/trust mới mà không làm lộ tiếp? | Rotate HMAC/DEK/KEK/signing key; đổi credentials, rollout consumer |
| **Recover & validate** | Hệ thống có hoạt động an toàn và còn đọc được dữ liệu hợp lệ? | End-to-end deny tests, decrypt/verify test, DR restore, audit review |

### 2.1. Emergency revocation không đồng nghĩa DestroyKey

**Disable/revoke** thường là việc vô hiệu hóa quyền hoặc operation trong miền kiểm soát. **Destroy** là hành động loại bỏ key material, có thể không đảo ngược. Trong một sự cố, **DisableKey hoặc deny KMS access có thể chặn hành vi mới**, nhưng **DestroyKey sai thời điểm có thể gây mất dữ liệu vĩnh viễn**.

Đặc biệt, khi attacker đã giữ **bản sao plaintext key** ngoài KMS, việc DisableKey ở KMS **không thể xóa bản sao đó**.

### 2.2. Thu hồi kịp thời nhưng không hành động mù

Quy trình khẩn có thể có quyền **break-glass** và đường phê duyệt rút gọn đã được quy định từ trước. Tuy nhiên, cần giữ **traceability, scope chính xác và khả năng ngăn irreversible changes**. Không dùng lý do khẩn cấp để đưa raw KEK lên chat hoặc tắt audit.

## 3. Phân biệt revoke, disable, rotate, retire và destroy

| Khái niệm | Ý nghĩa | Có đổi key bytes? | Mối nguy nếu hiểu sai |
|---|---|---|---|
| **Revoke user/session/token** | Chặn identity hoặc credential được dùng nữa | Thay/thu hồi credential, không nhất thiết đổi data key | Token cache hoặc session cũ vẫn tồn tại |
| **Revoke KMS grant/IAM** | Chặn principal gọi API với key | Không | Principal có thể dùng role/grant đường khác |
| **Disable key** | KMS/HSM từ chối operation mới theo semantics provider | Không | Cache plaintext DEK và bản sao export vẫn dùng được |
| **Rotate KEK** | Thay vật liệu bảo vệ DEK | Có với KEK | DEK cũ có thể chưa được thay |
| **Rewrap DEK** | Bọc lại DEK hiện tại dưới KEK khác | Không với DEK | Không khắc phục DEK plaintext đã lộ |
| **Rotate DEK** | Tạo data key mới | Có | Phải cập nhật ciphertext/nonce/tag nếu muốn thay key thực sự |
| **Re-encrypt** | Mã hóa lại plaintext bằng DEK mới | Có cho key/ciphertext | Có rủi ro migration/data consistency |
| **Revoke signing trust** | Verifier ngừng chấp nhận khóa/certificate theo policy | Không mặc nhiên | Verifier cache có thể còn chấp nhận chữ ký giả |
| **Retire key** | Dừng một số key usages, có thể giữ Decrypt/Verify lịch sử | Không nhất thiết | Nhầm với destruction |
| **Destroy key** | Hủy material ở miền quản lý sau kiểm kê | Material không còn tại provider | Không khôi phục dữ liệu còn phụ thuộc; không xóa bản sao attacker |

### 3.1. Ba câu hỏi cần tách bạch

1. **Đường vào nào bị lộ?** Credential, workload IAM, KMS policy, secret manager, thiết bị, private key file.
2. **Vật liệu nào có thể bị lộ?** Plaintext DEK, KEK, HMAC secret, private signing key, recovery share, hay chỉ keyRef.
3. **Khả năng nào attacker vẫn giữ sau khi revoke?** Truy cập API, giải mã offline, ký ngoài HSM, giả MAC, đọc backup đã tải xuống.

Một tài khoản bị chiếm **không tự động đồng nghĩa mọi KEK bị export**. Ngược lại, nếu plaintext private key đã bị đánh cắp, chỉ đổi mật khẩu IdP **không loại bỏ** khả năng ký ngoài hệ thống.

## 4. Khi nào cần kích hoạt emergency revocation?

Các trigger tiêu biểu:

- KMS/HSM audit cho thấy **Decrypt, Sign, Unwrap, CreateGrant hoặc thay key policy bất thường**.
- Một **plaintext DEK/KEK/HMAC secret/private signing key** xuất hiện trong repository, log, ticket, email hoặc external storage.
- Lộ **cloud credential, service account token, CI secret hoặc signing credential** có thể gọi crypto APIs.
- Mất thiết bị chứa private key, SSH identity, recovery share hoặc credentials có thể chưa được bảo vệ.
- Tài khoản có quyền key administration bị nghi chiếm đoạt hoặc insider misuse.
- Certificate/issuer/trust anchor bị compromise hoặc key signing bị nghi giả mạo.
- Phát hiện **AES-GCM nonce reuse**, dùng key ngoài cryptoperiod, hoặc mất kiểm soát key origin/material.
- HSM/custodian quorum bị xâm phạm hoặc key material bị import/export ngoài policy.
- Có **đề nghị thu hồi từ owner/CA/đối tác** với bằng chứng hợp lệ.
- Bên nhận trong hợp tác không còn được phép giữ key hoặc biết shared secret.

### 4.1. Không đồng nhất trigger với kết luận đã bị đánh cắp

Một detector báo “KMS Decrypt bất thường” là **dấu hiệu cần điều tra**, chưa chứng minh raw KEK bị lộ. Ngược lại, secret được commit lên repo công khai có thể coi là **potentially compromised** ngay cả khi không có bằng chứng ai đã đọc.

### 4.2. Mức khẩn phụ thuộc phạm vi

Một shared HMAC key dùng cho toàn bộ webhook có mức ảnh hưởng khác với DEK riêng một tài liệu. **Key scope, sensitivity, số consumers, cách key được phân phối, trust exposure, khả năng điều tra và business impact** quyết định priority.

## 5. Threat model: ai đang giữ quyền hoặc bản sao key?

~~~mermaid
flowchart TD
    A["Incident signal"] --> B{"Điều gì có thể bị lộ?"}
    B -->|IAM/session/token| I["Revoke identity + grants + sessions"]
    B -->|Raw DEK| D["Stop DEK Encrypt + replace/re-encrypt assessment"]
    B -->|Raw KEK| K["Stop new Wrap + KEK rotation + assess DEKs"]
    B -->|Signing private key| S["Stop Sign + new key pair + verifier trust update"]
    B -->|HMAC/PSK| H["New secret + consumer rollout + reject old"]
    B -->|Recovery shares| R["Secure quorum + re-share/reconstitute"]
    B -->|Unknown| U["Contain broad access, preserve evidence, scope investigation"]
    I --> V["Verify controls + impact + recovery"]
    D --> V
    K --> V
    S --> V
    H --> V
    R --> V
    U --> V
~~~

| Attacker có gì? | Khả năng vẫn tồn tại sau KMS/IAM revoke | Điều cần xem xét |
|---|---|---|
| Chỉ còn access token đang dùng | Token/session có thể vẫn hiệu lực ở cache | Revoke credential, kiểm tra propagation |
| Có role tự cấp CreateGrant | Có thể tái tạo quyền Decrypt | Kiểm tra effective permissions và deny privilege escalation |
| Có plaintext DEK | Giải mã ciphertext đã thu thập **offline** | Thay DEK, re-encrypt, đánh giá dữ liệu đã lộ |
| Có plaintext KEK | Có thể unwrap encrypted DEKs đã lấy | KEK mới, đánh giá DEK exposure và re-encrypt |
| Có private signing key | Có thể tạo chữ ký hợp lệ bên ngoài HSM | Revoke verifier trust, rotate key pair |
| Có shared HMAC/PSK | Có thể tạo MAC/request giả | Thay secret, reject old key theo policy |
| Chỉ có key ID và ciphertext | Chưa mặc nhiên có quyền Decrypt | Bảo vệ context/IAM/metadata; đánh giá dữ liệu nhạy cảm |
| Có backup database + IAM credentials | Có thể truy cập cả ciphertext và KMS | Containment cả storage và key permission |

### 5.1. Non-exportable không đồng nghĩa không thể misuse

Một KEK hoặc private signing key **non-exportable** trong HSM/KMS giảm nguy cơ lấy raw bytes, nhưng attacker có quyền **Decrypt/Sign** vẫn có thể sử dụng KMS như **oracle**. Phải thu hồi quyền và đánh giá những operation đã được thực hiện.

### 5.2. Logs không có nghĩa mọi hành vi đều quan sát được

Nếu audit chưa được bật, đã bị xóa hoặc chỉ ghi nhận một số APIs, việc “không thấy ExportKey” **không chứng minh material chưa bị lộ**. Báo cáo cần nêu rõ **độ bao phủ** và **bất định còn lại**.

## 6. Quy trình tổng thể: Detect → Contain → Assess → Replace → Verify

~~~mermaid
sequenceDiagram
    participant D as Detector/SOC
    participant C as Incident commander
    participant I as IAM/IdP
    participant K as KMS/HSM
    participant A as App/Key owner
    participant V as Verification/Audit
    D->>C: Alert + evidence refs
    C->>I: Revoke sessions/credentials/roles theo scope
    I-->>C: Effective access readback
    C->>K: Deny grants/operations hoặc disable theo runbook
    K-->>C: Provider observed key state + audit
    C->>A: Inventory impacted keys/data/consumers
    A-->>C: Exposure assessment + recovery dependencies
    C->>A: Approve replacement/cutover plan
    A->>K: Create new material / rewrap theo key type
    A->>V: Verify consumer deny/allow, decrypt, trust, backup
    V-->>C: Evidence + residual risk
~~~

### 6.1. Containment không chờ đủ mọi kết luận forensic

Nếu compromised credential đang tiếp tục gọi KMS, cần **chặn thêm thiệt hại** bằng đường đã phê duyệt. Đội điều tra có thể tiếp tục khoanh vùng material và affected data sau bước chặn quyền.

### 6.2. Chỉ thay material theo scope đã xác định

Một emergency action không nên mặc nhiên re-encrypt mọi dataset nếu scope chỉ ở một tenant, một DEK hoặc một shared token. Tuy nhiên, nếu **key scope quá rộng** hoặc inventory thiếu, phạm vi rủi ro có thể lớn hơn quan sát ban đầu.

### 6.3. Readback là bắt buộc

Một API trả success chỉ xác nhận request theo semantics của provider. Cần xác minh **effective IAM, KMS observed state, token/session TTL, application cache, active workers và verifiers**.

## 7. Phân vai chỉ huy và Separation of Duties

| Vai trò | Trách nhiệm trong emergency revocation | Không mặc nhiên được làm |
|---|---|---|
| **Incident commander** | Quyết định mức độ, ưu tiên, phạm vi, thông báo | Tự lấy raw KEK để debug |
| **Security analyst** | Điều tra alert, audit, affected principals | Tự sửa/xóa evidence |
| **IAM/IdP executor** | Revoke credentials, sessions, roles và grants | Destroy mọi data key |
| **Key owner/custodian** | Quyết định material scope, lifecycle, recovery | Bỏ qua approval cho irreversible action |
| **KMS/HSM operator** | Disable/rotate/wrap theo policy và audit | Decrypt business data ngoài quyền |
| **Application/data owner** | Dừng producer, kiểm tra consumers và data impact | Bypass AEAD verification |
| **DR/backup owner** | Xác minh dependencies và restore | Tạo plaintext KEK backup tùy tiện |
| **Independent approver/auditor** | Duyệt ngoại lệ và giữ evidence | Một mình tự cấp quyền rồi xóa log |

### 7.1. Break-glass phải được chuẩn bị trước khi có sự cố

Break-glass là **đường khẩn cấp có kiểm soát**: identity riêng, approval hoặc dual control thích hợp, TTL/JIT privileges, audit và test định kỳ. Không dùng một master password chung được gửi qua chat để “mở khóa”.

### 7.2. Không để người đang bị nghi compromise tự phê duyệt

Nếu key owner/administrator có thể chính là đối tượng nghi ngờ, luồng emergency phải cho phép **người độc lập có thẩm quyền** đánh giá và thi hành thu hồi, đồng thời giữ chain of custody cho bằng chứng.

### 7.3. Bảo vệ availability

Trước khi disable KEK bao trùm toàn hệ thống, xác định ảnh hưởng tới decrypt service, business continuity, quy trình thanh toán, backups và quy định lưu trữ. Có thể chọn **revoke principal hoặc khóa một grant cụ thể** trước khi chọn DisableKey toàn bộ, tùy khả năng containment.

## 8. Những hành động đầu tiên theo trình tự ưu tiên

Đây là **trình tự tham chiếu**, không phải một SLA cố định. Tổ chức cần đặt giới hạn thời gian theo severity, dữ liệu và yêu cầu vận hành.

1. **Xác nhận tín hiệu:** loại incident, time window, affected identity/keyRef, nguồn chứng cứ.
2. **Kiểm soát truy cập:** revoke compromised sessions/credentials, tạm deny IAM/grants, cô lập workload hoặc endpoint.
3. **Khóa đường tự tái cấp quyền:** kiểm tra AssumeRole, CreateGrant, ChangeKeyPolicy, PassRole và CI/CD deployment.
4. **Chặn misuse thêm:** disable Sign/Encrypt hoặc key-specific operation theo runbook khi cần, đồng thời cân nhắc impact.
5. **Bảo toàn evidence:** lưu audit/KMS/IdP logs, correlation IDs và key policy revisions trong miền độc lập.
6. **Khoanh vùng:** vật liệu nào có khả năng lộ, ciphertext/data nào liên quan, consumers nào đang cache key.
7. **Chọn replacement:** credential, HMAC, DEK, KEK, signing key, certificate hay recovery shares.
8. **Rollout an toàn:** generate material mới từ nguồn tin cậy, cấp quyền và key references đúng, cập nhật consumers.
9. **Kiểm chứng:** negative access tests, end-to-end crypto operations, trust propagation, backup restore.
10. **Đóng hoặc theo dõi:** ghi việc đã làm, exceptions, residual exposure, owner và post-incident corrections.

### 8.1. Freeze new use, nhưng có thể cần giữ historical use

Ví dụ **DEK cũ** không được tiếp tục dùng Encrypt mới sau compromise, nhưng decrypt cũ có thể vẫn cần cho quá trình migration được ủy quyền. Phải hạn chế **principal và operation** trong thời gian chuyển, không để KMS Decrypt mở rộng vô hạn.

### 8.2. Điều gì tuyệt đối không nên làm?

- Đưa raw KEK/DEK vào chat, ticket hoặc audit để nhiều người “kiểm tra”.
- Bỏ qua TLS/mTLS hoặc xác thực certificate khi triển khai đường thay khóa.
- Tắt audit hoặc xóa event để giảm nhiễu.
- Chỉnh ciphertext/nonce/tag bằng tay thay vì re-encrypt đúng.
- Tự động DeleteKey ngay sau một alert chưa được scoped.
- Tạo “fallback master key” hard-code khi KMS outage.
- Trả plaintext chưa AEAD-verify vì cần khôi phục gấp.

## 9. Thu hồi khẩn IAM, sessions và KMS grants

**Identity compromise** là một nguyên nhân thường gặp hơn raw KEK export. Phải đóng **tất cả đường hiệu lực**, không chỉ DisableUser ở IdP.

### 9.1. Các lớp quyền cần kiểm tra

| Lớp | Ví dụ | Cần xác minh |
|---|---|---|
| **Human identity** | SSO/MFA, VPN, cloud console | Session và refresh token còn dùng được không? |
| **Workload identity** | Pod role, service account, instance profile | Token/credential có được cấp lại không? |
| **Assumable roles** | Role chaining, PassRole, federation | Attacker có thể tự quay lại qua role khác không? |
| **KMS permissions** | Decrypt, Encrypt, GenerateDataKey, Sign, CreateGrant | Có grant hoặc key policy ngoài IAM chính không? |
| **Key administration** | ScheduleDeletion, ChangeKeyPolicy | Có quyền self-escalation hoặc phá key không? |
| **Secret manager** | GetSecretValue, update grants | Có secret rõ khác bị đọc hoặc copy không? |
| **App business layer** | Tenant/object authorization | Có decryption oracle ngay cả khi IAM là role hợp lệ không? |
| **Audit/config** | Cloud logging, CI/CD, event sinks | Có thể xóa chứng cứ hoặc tái triển khai quyền không? |

### 9.2. Disable identity chưa đủ nếu cached token còn tồn tại

Một số session có TTL, khả năng offline hoặc cần refresh ở nhiều thành phần. Phải kiểm tra cơ chế revoke của provider, **effective policy propagation** và runtime status. Không tuyên bố “revoke tức thì ở mọi nơi” nếu hệ thống không có bảo đảm đó.

### 9.3. Negative test có phạm vi

Sử dụng **môi trường kiểm thử, canary principal hoặc thao tác vô hại được phê duyệt** để xác minh compromised principal không còn quyền Decrypt/Sign/AssumeRole. Không dùng key production hoặc dữ liệu nhạy cảm làm thử nghiệm tùy tiện.

### 9.4. Thay credential có thể cần ngay cả khi không thay DEK/KEK

Nếu cloud access key hoặc OAuth token lộ, hãy **revoke/rotate credential đó**. Sau đó điều tra xem credential có bị dùng để gọi KMS hoặc export plaintext DEK hay không; quyết định data-key rotation dựa trên **evidence và rủi ro**, không dựa duy nhất vào sự hiện diện của IAM key bị lộ.

## 10. KMS/HSM key state: Disable không phải Destroy

Tùy provider, key có các trạng thái tương tự **Enabled, Disabled, PendingDeletion, Deleted/Destroyed**, nhưng **tên, khả năng API và cách propagation** có thể khác nhau. Không áp một state model duy nhất cho mọi KMS/HSM.

### 10.1. DisableKey/deny grants tác động thế nào?

- Có thể chặn một số **KMS cryptographic operations mới** với key đó theo chính sách provider.
- Không xóa **plaintext DEK đã phát hành hoặc cache** tại ứng dụng.
- Không xóa **bản sao KEK đã export** nếu cơ chế từng cho export.
- Có thể làm nhiều consumers Decrypt/Unwrap thất bại nếu cùng KEK đang được dùng rộng.
- Có thể ảnh hưởng **khả năng khôi phục backup** trong thời gian disabled.
- Cần được audit cùng thời điểm và actor.

### 10.2. Khi nào DisableKey có thể quá rộng?

Nếu chỉ một service role bị chiếm nhưng KEK của nhiều tenants được chia sẻ, DisableKey có thể khiến mọi tenant mất khả năng Unwrap. Một lựa chọn containment có thể là **deny principal/grants bị chiếm, khóa workload, ngừng cấp credentials** rồi đánh giá có cần DisableKey toàn bộ.

**Không coi đây là quy tắc ưu tiên bắt buộc:** nếu chính key material bị lộ hoặc policy yêu cầu, phải áp dụng containment mạnh hơn dựa trên sự cố.

### 10.3. ScheduleDeletion không phải emergency off-switch

Lên lịch xóa khóa không nhất thiết đồng nghĩa đã hủy material tức thời, và có thể tạo rủi ro availability. Mỗi provider có **waiting period, cancelability và semantics** riêng. Quy trình khẩn phải phân biệt **disable/deny operations** với **destruction có kiểm chứng**.

### 10.4. HSM emergency operations

Với HSM, có thể có **key attributes, activation state, usage flags, operator roles, quorum hoặc tamper response**. Một thay đổi flags/permissions có thể chặn operations trong HSM, nhưng **không xóa private key đã bị export** hoặc những kết quả Sign/Decrypt được phát hành trước đó.

## 11. Thu hồi khẩn khi DEK bị lộ

**DEK (Data Encryption Key)** trực tiếp mã hóa dữ liệu; trong envelope encryption, nó thường được bọc bởi KEK và lưu dưới dạng **encrypted DEK** cạnh ciphertext.

Nếu một DEK dạng rõ bị lộ, attacker có thể giải mã **ciphertexts đã thu thập dưới DEK đó** mà không cần truy cập KMS nữa. Vì vậy **chỉ revoke KMS principal hoặc rewrap DEK dưới KEK mới chưa đủ** để bảo vệ các bản mã chịu ảnh hưởng.

### 11.1. Hành động cần đánh giá

1. **Khoanh vùng DEK material thực tế**, không chỉ key alias hoặc record ID.
2. Xác định những object/tenant/archive/backup được mã hóa dưới material đó.
3. Chặn các producers tiếp tục **Encrypt mới** với DEK có nguy cơ.
4. Tạo DEK mới bằng CSPRNG/KMS với key usage và key scope đúng.
5. Di chuyển producers tới DEK mới; tránh gây **AES-GCM nonce reuse** khi replay hoặc khôi phục state.
6. Xem xét **re-encrypt** dữ liệu cần bảo vệ, với quy trình Decrypt/Verify ciphertext cũ rồi Encrypt lại dưới DEK mới/nonce mới.
7. Cập nhật encrypted DEK, nonce, tag, keyRef, format version một cách nhất quán.
8. Rà soát bản sao dữ liệu/DEK ở endpoints, caches, logs, object versions và backup.
9. Báo cáo **dữ liệu có thể đã lộ trước migration**, vì re-encrypt không thể thu hồi kiến thức attacker đã lấy.
10. Retire/revoke material cũ đúng policy, không Destroy trước khi dữ liệu hợp lệ cần phục hồi đã được xử lý.

### 11.2. Ví dụ envelope trước và sau

~~~text
Trước sự cố:
  ciphertext = AES-GCM(DEK-A, nonce-A, plaintext, aad)
  encryptedDek = Wrap(KEK-1, DEK-A)

Sau khi DEK-A có thể đã lộ:
  DEK-B = GenerateFreshDataKey()
  plaintext = VerifyAndDecrypt(DEK-A, ciphertext, nonce-A, aad)
  newCiphertext = AES-GCM(DEK-B, freshNonce-B, plaintext, aadNew)
  newEncryptedDek = Wrap(KEK-2, DEK-B)
~~~

Đây là luồng khái niệm, không phải mã chạy; trong thực tế phải có **transaction/CAS, idempotency, authz, memory handling, integrity checks, quota và recovery plan**.

### 11.3. Không thay nonce trong database để "sửa" ciphertext

Nonce là tham số của phép mã hóa đã tạo ciphertext/tag. Chỉnh nonce bytes mà không tái mã hóa hợp lệ thường làm tag thất bại. Cũng không thể sửa sự cố **đã reuse nonce dưới AES-GCM** bằng cách đổi KEK.

## 12. Thu hồi khẩn khi KEK bị lộ

**KEK (Key Encryption Key)** thường bảo vệ nhiều DEKs. Một bản sao plaintext KEK có thể cho phép attacker **unwrap những encrypted DEKs đã lấy được**, ngay cả khi KMS account của họ bị khóa.

### 12.1. Quy trình phân loại

| Tình huống | Rủi ro | Phản ứng |
|---|---|---|
| KEK non-exportable, chỉ role IAM bị chiếm | Attacker có thể từng gọi KMS API nhưng chưa chắc có raw KEK | Thu hồi quyền, audit API usage; đánh giá data exposure |
| KEK có khả năng export dưới dạng rõ | Attacker có thể unwrap offline | Tạo KEK mới, đánh giá encrypted DEKs đã bị thu thập |
| KEK raw bytes đã xác nhận bị lộ | Tất cả wrapped DEKs liên quan có thể có nguy cơ | Containment, KEK replacement, phân loại DEK và re-encrypt khi cần |
| KEK shared nhiều tenants | Blast radius lớn | Xác định tất cả dependent encrypted DEKs, clients và backups |
| KEK chỉ bị disable trong KMS | Operations mới có thể bị chặn | Bản sao KEK ngoài KMS, nếu có, không bị xóa |

### 12.2. KEK rotation và DEK rewrap

Nếu KEK chưa bị lộ hoặc không có bằng chứng DEK liên quan đã bị giải bọc trái phép, có thể có quy trình **rewrap** DEKs dưới KEK mới để giảm phụ thuộc KEK cũ.

Nhưng khi plaintext KEK có thể đã bị lấy cùng encrypted DEK blobs, **rewrap hôm nay không thay đổi khả năng attacker đã mở DEKs cũ trước đây**. Phải đánh giá **DEK rotation/re-encryption** theo mức độ rủi ro.

### 12.3. Không Destroy KEK trong lúc chưa kiểm kê phụ thuộc

~~~mermaid
flowchart TD
    K["KEK-v1 nghi compromise"] --> A["Encrypted DEK thuộc tenant A"]
    K --> B["Encrypted DEK thuộc tenant B"]
    K --> C["Archive/backup versions"]
    K --> D["DR replicas và offline consumers"]
    A --> E["Inventory + rewrap/re-encrypt plan"]
    B --> E
    C --> E
    D --> E
    E --> V["Readback + restore/decrypt verification"]
    V --> R["Retire/revoke/destroy đúng policy"]
~~~

**Disable** KEK có thể là biện pháp containment cần thiết, nhưng **Destroy** chỉ được xem xét khi dependency graph, retention, legal hold và recovery path đã được rà soát.

### 12.4. KEK rotation không reset nonce state của DEK

Nếu DEK-A được bọc lại từ KEK-v1 sang KEK-v2, **DEK material không đổi**. Với AES-GCM, mọi writer còn sử dụng DEK-A vẫn phải bảo đảm **nonce uniqueness dưới DEK-A**, không được reset counter do thay keyRef.

## 13. Thu hồi khẩn private signing key và năng lực ký

Khi **private signing key** đã lộ, attacker có thể tạo chữ ký hợp lệ **ngoài hệ thống ký**, kể cả sau khi HSM/KMS báo Disabled. Việc chặn KMS Sign chỉ làm ngừng **đường sử dụng trong KMS**, không vô hiệu bản sao raw key ở bên ngoài.

### 13.1. Những việc khác nhau phải phối hợp

- **Stop signing:** chặn principal/workload đang phát chữ ký mới dưới material nghi lộ.
- **Generate replacement:** tạo key pair mới từ nguồn tin cậy trong HSM/KMS nếu phù hợp.
- **Update trust:** phân phối public verification key/certificate/JWKS và policy mới đến verifiers.
- **Revoke old trust:** làm verifiers từ chối chữ ký không được phép dưới key cũ theo incident policy.
- **Handle existing signatures:** phân biệt chữ ký lịch sử hợp lệ, bằng chứng thời gian, token còn hạn và chữ ký có thể bị giả.
- **Audit affected content:** xác định thời gian lộ, issued signatures, approvals và bản ghi có nghi ngờ giả mạo.

### 13.2. HSM non-exportable nhưng Sign API bị lạm dụng

Nếu private key không exportable, attacker có thể chưa có raw material, nhưng đã gửi **dữ liệu tùy ý để HSM ký** nếu thiếu business approval. Khi đó cần revoke Sign privileges, điều tra **những message digests/chứng từ đã ký** và bảo vệ approval workflow. **Không thể chỉ xem key material an toàn rồi bỏ qua việc giả mạo nghiệp vụ**.

### 13.3. JWT/JWS và JWKS caches

Với một issuer ký JWT:

1. Tạo signing key pair mới và key identifier mới theo issuer policy.
2. Chuyển signer sang material mới.
3. Phân phối public key mới qua **JWKS endpoint đã được tin cậy**, không dựa vào URL do token tự khai.
4. Xem **cache lifetime, token TTL, trust propagation** ở các verifiers.
5. Nếu key cũ compromise, đánh giá **reject old kid/token**, active sessions và khả năng attacker đã forge.
6. Đảm bảo verifier kiểm tra issuer, audience, algorithm allowlist, expiry và policy riêng.

**Đổi kid mà không thay bytes private key không phải rotation thực sự.** **Xóa JWKS entry** cũng không tự bảo đảm mọi verifier đã hết cache key cũ.

### 13.4. Chữ ký lịch sử và bằng chứng thời gian

Việc revoke trust hôm nay không đồng nghĩa mọi chữ ký từ nhiều năm trước đều giả. Cần quy tắc phân biệt **thời điểm ký được chứng minh, certificate status tại thời điểm đó, timestamp, archive validation và chính sách pháp lý**. Không xóa public key/certificate history tùy tiện nếu cần kiểm tra chữ ký hợp lệ.

## 14. Thu hồi khẩn HMAC, PSK và shared secrets

**HMAC key/PSK** thường tồn tại ở **nhiều endpoints**. Nếu một bên giữ secret bị compromise, không thể thu hồi khả năng tạo MAC/giả mạo chỉ bằng cách disable một account.

### 14.1. Playbook

1. Khoanh vùng **tất cả producers, verifiers và consumers** biết key cũ.
2. Chặn endpoint/credential bị chiếm.
3. Tạo **shared secret version mới** bằng nguồn ngẫu nhiên phù hợp.
4. Provision tới các bên hợp lệ qua authenticated channel hoặc secret manager, không đưa secret lên email/chat/log.
5. Chuyển producers dùng version mới; đảm bảo verifiers đã sẵn sàng.
6. **Ngừng chấp nhận key cũ** theo mức độ sự cố và policy, không giữ dual-verify vô hạn.
7. Đánh giá webhook/API requests có MAC bất thường và replay/nonce/sequence checks.
8. Audit old-key usage, key ID/version, consumer cutover và rủi ro còn lại.

### 14.2. Compatibility window cần được phê duyệt

Trong planned rotation, verifier có thể tạm hỗ trợ hai phiên bản có thời hạn. **Trong confirmed compromise**, giữ chấp nhận secret cũ nghĩa là attacker có thể tiếp tục giả MAC. Không tự động bật compatibility window dài chỉ vì một consumer legacy chưa nâng cấp.

### 14.3. HMAC rotation không tự chữa replay

Một MAC hợp lệ có thể bị phát lại nếu protocol thiếu **timestamp, sequence, operation ID hoặc challenge state**. Bản thay thế cần ràng buộc version/purpose, chống replay và hạn chế việc attacker đưa bản tin cũ tới sau cutover.

## 15. Thu hồi khẩn certificates và PKI trust

Certificate revocation thuộc miền **xác thực public-key identity**. Nó khác với việc xóa hoặc rotate một data-encryption KEK.

### 15.1. Các thành phần cần phân biệt

| Thành phần | Bị thu hồi ở đâu? | Giới hạn |
|---|---|---|
| **End-entity TLS certificate** | CA/PKI policy, CRL/OCSP/trust configuration theo hệ sinh thái | Client có thể chưa kiểm tra hoặc cache status |
| **Private key của certificate** | Tạo key pair mới; chặn đường dùng tại HSM/endpoint | Bản sao attacker giữ vẫn có thể tồn tại |
| **Intermediate/Root CA** | Trust stores, PKI incident process | Blast radius rất lớn, cần phối hợp rộng |
| **mTLS client identity** | CA policy, workload registry và server authorization | Existing sessions có thể còn hiệu lực |
| **JWT issuer signing certificate/key** | JWKS/issuer trust và token policy | JWKS cache/token lifetime cần xử lý |

### 15.2. TLS connection đã thiết lập có thể tồn tại

Thu hồi certificate của client không nhất thiết chấm dứt **mọi kết nối đã được thiết lập trước đó**. Cần xét session termination, credential propagation, reverse proxies, service mesh và cache theo thiết kế.

### 15.3. Không tin revoke status chỉ vì đã gửi request

CRL/OCSP/CA response có thể có **độ trễ công bố, TTL/cache** hoặc client không cấu hình bắt buộc kiểm tra revocation trong một số môi trường. Kiểm thử cần xác định **verifiers thực sự từ chối identity đã bị revoke**, không chỉ CA trả success.

### 15.4. Trust-anchor compromise cần kế hoạch riêng

Nếu CA hoặc public-key distribution channel bị chiếm, việc thay một end-entity certificate có thể không đủ. Cần **trust-store rollout, signer identity revalidation, client compatibility và incident coordination**. Đây có thể là một emergency lớn với mục tiêu tránh spoofing ở nhiều hệ thống.

## 16. Emergency revocation khi có lỗi sử dụng nonce hoặc AEAD

Không phải mọi compromise bắt đầu từ việc raw key bị đánh cắp. Ví dụ **AES-GCM nonce reuse** dưới cùng DEK có thể làm suy yếu confidentiality và integrity ngay khi key vẫn được giữ bí mật.

### 16.1. Phản ứng với nonce reuse

- Chặn **Encrypt mới** dưới DEK có lỗi.
- Xác minh cặp **DEK material + nonce** bị lặp giữa những Encrypt operations riêng.
- Phân biệt trùng event logging với hai phép mã hóa độc lập.
- Xác định data/ciphertexts/backups có thể bị ảnh hưởng.
- Tạo **DEK mới** và di chuyển producers.
- Đánh giá **re-encrypt** bản mã cũ và khả năng dữ liệu đã bị lộ/giả mạo.
- Sửa counter allocator, retry, multiwriter/snapshot restore và kiểm thử failover.

**Rewrap DEK dưới KEK khác hoặc sửa nonce trong metadata không chữa reuse đã xảy ra**.

### 16.2. AEAD tag failure không tự chứng minh nonce reuse

Tag thất bại có thể do sai key, nonce, AAD, ciphertext, format hoặc cố ý sửa dữ liệu. Ngược lại, **cặp bản mã GCM bị nonce reuse vẫn có thể tự verify tag thành công**. Điều tra phải dựa vào key/nonce usage evidence, không chỉ số lỗi Decrypt.

### 16.3. Không bỏ xác thực để khôi phục

Không cho Decrypt trả plaintext chưa xác thực hoặc bỏ AAD chỉ vì KMS/key metadata vừa được thay trong sự cố. Quy trình khôi phục phải giữ **integrity/authenticity** của dữ liệu.

## 17. Application cache, phiên đã mở và khả năng thu hồi không đồng bộ

Một nguồn gây hiểu nhầm lớn: **provider cho biết key đã Disabled**, nhưng ứng dụng vẫn dùng **plaintext DEK đã lấy từ trước** hoặc phiên KMS/credential còn hiệu lực.

### 17.1. Những bản sao có thể tồn tại

- Plaintext DEK trong JVM heap, native crypto buffers và data-key cache.
- HMAC/PSK trong memory của nhiều verifier.
- Signing key trên disk, HSM session hoặc signing agent.
- API tokens/JWTs trong browser và worker queues.
- Secret manager responses cache, sidecars, service-mesh proxy.
- Snapshots, heap dumps, error logs và temporary files.
- Offline devices/batch jobs chưa nhận được revoke event.

### 17.2. Cache invalidation là một phần của emergency revocation

Nếu policy yêu cầu chặn Decrypt ngay, không chỉ revoke KMS grant mà còn cần **invalidate local DEK caches và hạn chế những workloads đang giữ DEK rõ**. Có thể phải **terminate/restart** một số processes, thay session credentials hoặc cô lập instances.

Nhưng **restart** không tự xóa persistent caches hoặc bản sao attacker đã sao chép, và **Arrays.fill** trên byte array trong Java chỉ là best-effort đối với mảng mà code kiểm soát.

### 17.3. Một revocation event có thể đến muộn

Trong hệ thống đa vùng/queue:

- Một consumer offline có thể tiếp tục dùng old key khi reconnect nếu thiếu epoch check.
- IAM policy changes có thể cần thời gian propagation.
- JWT verifier có thể cache JWKS.
- Secret manager clients có thể giữ bản plaintext cũ.
- Backup restore có thể khởi động lại container với **configuration hoặc credential phiên bản cũ**.

Cần định nghĩa **key epoch/material version/permission revision** và điều kiện **fail closed đối với old material** khi policy đòi hỏi.

### 17.4. Revocation không hủy khả năng offline

Nếu một kẻ tấn công đã tải raw DEK/KEK/private key trước đó, không có sự kiện cache invalidation nào xóa được bản sao nằm ngoài quyền quản lý. Đây là lý do **rotation material và xử lý dữ liệu/trust** có thể cần thiết ngay cả sau khi revoke permissions thành công.

## 18. Backup, DR và điều kiện ngừng sử dụng khóa cũ

Một hệ thống chỉ có ciphertext/encrypted DEK nhưng không còn key material để unwrap có thể **mất dữ liệu vĩnh viễn**. Emergency revocation cần cân bằng confidentiality với availability và retention.

### 18.1. Dependency graph

~~~text
KEK-v1
  |
  +-- Encrypted DEK của dataset Orders
  |      +-- Ciphertext + nonce/tag/AAD
  |      +-- Archived object versions
  |
  +-- Encrypted DEK của dataset Billing
  |
  +-- Snapshots / backups / replicas
  |
  +-- DR sites / offline recovery procedures
~~~

Nếu KEK-v1 bị compromise và chuẩn bị destroy, cần biết **DEKs ở mọi nơi còn phụ thuộc** và đã được rewrap/re-encrypt khi phù hợp.

### 18.2. Recovery test cần Decrypt thật

Các bước kiểm thử DR có ý nghĩa:

1. Restore metadata format, encrypted DEK và ciphertext.
2. Xác minh trusted tenant/object binding, AAD, nonce, tag.
3. Dùng đúng KMS/HSM key reference/material version và recovery principal được phê duyệt.
4. Unwrap và **Decrypt/Verify** dữ liệu mẫu.
5. Kiểm tra ứng dụng dùng đúng version/cryptoperiod, không tự quay về key cũ.
6. Xác minh audit được ghi và không tạo bản copy plaintext KEK/DEK ngoài policy.

### 18.3. Retire, disable và destroy cần có tiêu chí riêng

- **Retire:** không dùng key để tạo bản mã/chữ ký mới.
- **Disable:** provider chặn thao tác phù hợp trạng thái.
- **Destroy:** key material được hủy theo cơ chế provider, có xác nhận.
- **Crypto-shredding:** mục tiêu làm ciphertext không thể giải mã khi không còn key material/recovery path hợp lệ.

**Xóa key reference khỏi database không phải bằng chứng crypto-shredding**. Và nếu attacker đã giữ một bản raw key, Destroy tại KMS không thể hủy bản sao của họ.

## 19. Evidence, audit và hậu kiểm

Emergency revocation là một thay đổi an ninh có thể phá vỡ hệ thống nếu không ghi rõ **ai, cái gì, khi nào và vì sao**.

### 19.1. Audit event minh họa

~~~json
{
  "incidentId": "sec-ir-2026-118",
  "actionId": "revocation-004",
  "action": "REVOKE_KMS_GRANT",
  "principalRef": "workload-orders-prod",
  "keyRef": "kms/prod/orders-kek",
  "grantRef": "grant-219",
  "reasonCode": "SUSPECTED_CREDENTIAL_COMPROMISE",
  "requestedBy": "incident-commander-role",
  "approvedBy": "security-approver-role",
  "providerResult": "SUCCESS",
  "effectiveStateVerified": true,
  "observedAt": "2026-11-28T03:00:00Z"
}
~~~

Đây là **schema minh họa**, không phải payload tiêu chuẩn của một nhà cung cấp. Trong triển khai thật, phải có evidence references và thời điểm đọc lại trạng thái. **Không log raw DEK/KEK, private key, HMAC secret, bearer token hoặc plaintext nhạy cảm**.

### 19.2. Cần trả lời được những câu hỏi nào?

1. Identity/credential nào bị nghi lộ? Đã revoke ở những miền nào?
2. Có đường AssumeRole/CreateGrant/ChangeKeyPolicy nào còn mở?
3. Key material nào liên quan, key origin/exportability ra sao?
4. Dữ liệu/ciphertexts/DEKs/signatures nào có nguy cơ?
5. Ai phê duyệt DisableKey, rotate, re-encrypt hoặc trust change?
6. Những KMS operations nào đã xảy ra trong time window và độ bao phủ audit là bao nhiêu?
7. Có consumer/region/cache nào vẫn dùng old key?
8. Những historical data/backup nào vẫn cần old material?
9. Test nào chứng minh revoked principal không còn khả năng được phép?
10. Residual risk/data exposure nào chưa thể loại trừ?

### 19.3. Nhật ký phải được bảo vệ độc lập

Nếu compromised KeyAdmin có thể **sửa policy, tự cấp quyền rồi xóa audit**, điều tra có thể không còn bằng chứng. Cần separation of duties, retention, append-only/immutable audit controls theo năng lực hệ thống và access restrictions phù hợp.

### 19.4. Chỉ báo cho phép đóng sự cố

Closure không chỉ là “API revoke trả success”. Phải xem:

- Containment chứng minh effective.
- Material/trust thay thế đã cutover.
- Old-key acceptance/usage bị chặn đúng nơi.
- Consumer paths và offline workers đã được xử lý.
- Data integrity và DR restoration được kiểm tra.
- Evidence đầy đủ hoặc rõ ràng về lỗ hổng coverage.
- Risk owner chấp thuận những exceptions còn lại.

## 20. Workflow trạng thái và idempotency trong thu hồi khẩn

Alert có thể được gửi lại nhiều lần từ SIEM, queue hoặc webhook. Nếu mỗi lần nhận alert đều tự tạo một KEK mới hoặc gọi ScheduleDeletion, hệ thống có thể gây lỗi availability nghiêm trọng. Cần quản lý **incidentId, actionId, state transitions, evidence và reconciliation**.

~~~mermaid
stateDiagram-v2
    [*] --> TRIAGED: Nhận alert
    TRIAGED --> CONTAINING: Xác minh scope tạm
    CONTAINING --> CONTAINED: Effective deny/readback
    CONTAINED --> SCOPING: Inventory/evidence
    SCOPING --> REPLACEMENT_APPROVED: Cần material/trust mới
    SCOPING --> MONITORING: Access-only incident
    REPLACEMENT_APPROVED --> CUTTING_OVER: Generate và rollout material
    CUTTING_OVER --> VERIFIED: End-to-end tests và DR
    VERIFIED --> MONITORING: Old use bị chặn
    MONITORING --> CLOSED: Risk owner chấp nhận residual risk
    CLOSED --> [*]
~~~

### 20.1. Guard cho workflow

1. Một action phải có **incident ID + action ID + provider resource ID + desired state**.
2. Trước khi thao tác, đọc **key material/reference, resource policy, current state**.
3. Retry cần **idempotency** theo API thực tế; nếu timeout thì **readback**, không đoán đã thành công hay thất bại.
4. Không cho duplicate event rotate/revoke sai resource vì alias vừa chuyển phiên bản.
5. Không để một alert thô tự gọi **DestroyKey, xóa trust anchor hoặc re-encrypt dữ liệu toàn tổ chức**.
6. Log cả **request, approval, provider outcome và effective verification** với timestamp và actor.
7. Cần cơ chế **stop/pause** workflow trước hành động irreversible.

### 20.2. Rollback của khóa đã compromise không bình thường

Nếu old HMAC/private signing key đã bị xác nhận lộ, quay về old material chỉ để phục hồi dịch vụ có thể **mở lại khả năng giả mạo**. Sửa consumer config/IAM cho **material mới hợp lệ** thường tốt hơn tái kích hoạt key cũ. Trường hợp ngoại lệ phải có scope, time limit và approval.

## 21. Java 17: mô hình lập kế hoạch emergency revocation

Đoạn Java sau chỉ **đề xuất các loại hành động cần đánh giá**. Nó không gọi KMS SDK, không revoke credential thật, không tự tạo material, không thực thi DeleteKey. Production cần **executor có IAM tối thiểu, approval độc lập, key inventory và readback provider**.

~~~java
import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;

public final class EmergencyRevocationPlanner {
    public enum Asset {
        CLOUD_CREDENTIAL,
        DEK,
        KEK,
        PRIVATE_SIGNING_KEY,
        SHARED_HMAC_OR_PSK,
        NON_EXPORTABLE_HSM_KEY,
        RECOVERY_SHARE
    }

    public enum Exposure {
        ACCESS_MISUSE_SUSPECTED,
        MATERIAL_POSSIBLY_EXPOSED,
        MATERIAL_CONFIRMED_EXPOSED
    }

    public enum Review {
        REVOKE_SESSIONS_AND_TOKENS,
        REVOKE_IAM_ROLES_AND_KMS_GRANTS,
        CHECK_EFFECTIVE_PERMISSIONS,
        PRESERVE_EVIDENCE_AND_AUDIT,
        INVENTORY_DEPENDENCIES,
        CHECK_CACHED_KEY_MATERIAL,
        VERIFY_REVOKED_ACCESS,
        ROTATE_COMPROMISED_CREDENTIAL,
        ASSESS_NEW_DEK_AND_REENCRYPT,
        ASSESS_NEW_KEK_AND_REWRAP,
        ASSESS_AFFECTED_DEKS,
        ASSESS_SIGNING_KEY_AND_VERIFIER_TRUST,
        ASSESS_NEW_SHARED_SECRET,
        ASSESS_RECOVERY_SHARE_CHANGE,
        VERIFY_CONSUMER_CUTOVER,
        VERIFY_BACKUP_RESTORE,
        REQUIRE_INDEPENDENT_APPROVAL
    }

    public record Incident(
        String incidentId,
        Asset asset,
        Exposure exposure
    ) {}

    public record Plan(
        String incidentId,
        Set<Review> actions,
        boolean securityApprovalRequired
    ) {}

    public static Plan plan(Incident incident) {
        Objects.requireNonNull(incident);
        Objects.requireNonNull(incident.incidentId());
        Objects.requireNonNull(incident.asset());
        Objects.requireNonNull(incident.exposure());
        if (incident.incidentId().isBlank()) {
            throw new IllegalArgumentException("Missing incident ID");
        }

        EnumSet<Review> a = EnumSet.of(
            Review.REVOKE_SESSIONS_AND_TOKENS,
            Review.REVOKE_IAM_ROLES_AND_KMS_GRANTS,
            Review.CHECK_EFFECTIVE_PERMISSIONS,
            Review.PRESERVE_EVIDENCE_AND_AUDIT,
            Review.INVENTORY_DEPENDENCIES,
            Review.CHECK_CACHED_KEY_MATERIAL,
            Review.VERIFY_REVOKED_ACCESS,
            Review.VERIFY_CONSUMER_CUTOVER
        );

        boolean materialRisk =
            incident.exposure() != Exposure.ACCESS_MISUSE_SUSPECTED;

        switch (incident.asset()) {
            case CLOUD_CREDENTIAL ->
                a.add(Review.ROTATE_COMPROMISED_CREDENTIAL);

            case DEK -> {
                if (materialRisk) {
                    a.add(Review.ASSESS_NEW_DEK_AND_REENCRYPT);
                    a.add(Review.VERIFY_BACKUP_RESTORE);
                }
            }
            case KEK -> {
                if (materialRisk) {
                    a.add(Review.ASSESS_NEW_KEK_AND_REWRAP);
                    a.add(Review.ASSESS_AFFECTED_DEKS);
                    a.add(Review.VERIFY_BACKUP_RESTORE);
                }
            }
            case PRIVATE_SIGNING_KEY -> {
                if (materialRisk) {
                    a.add(Review.ASSESS_SIGNING_KEY_AND_VERIFIER_TRUST);
                }
            }
            case SHARED_HMAC_OR_PSK -> {
                if (materialRisk) {
                    a.add(Review.ASSESS_NEW_SHARED_SECRET);
                }
            }
            case NON_EXPORTABLE_HSM_KEY -> {
                // Không kết luận raw material bị lộ chỉ vì
                // một principal từng có quyền gọi Sign/Decrypt.
                a.add(Review.CHECK_EFFECTIVE_PERMISSIONS);
            }
            case RECOVERY_SHARE -> {
                if (materialRisk) {
                    a.add(Review.ASSESS_RECOVERY_SHARE_CHANGE);
                    a.add(Review.VERIFY_BACKUP_RESTORE);
                }
            }
        }

        if (materialRisk) {
            a.add(Review.REQUIRE_INDEPENDENT_APPROVAL);
        }

        return new Plan(
            incident.incidentId(),
            Set.copyOf(a),
            materialRisk
        );
    }

    public static void main(String[] args) {
        Incident incident = new Incident(
            "sec-ir-118",
            Asset.DEK,
            Exposure.MATERIAL_POSSIBLY_EXPOSED
        );
        Plan p = plan(incident);
        System.out.println(p.incidentId());
        System.out.println(p.actions());
        // Không in plaintext DEK, KEK hoặc bearer token.
    }
}
~~~

### 21.1. Ví dụ minh họa ranh giới quyết định

- **CLOUD_CREDENTIAL:** phải xem xét credential rotation/revoke; điều tra KMS usage trước khi kết luận DEK/KEK cần thay.
- **DEK exposed:** cần review DEK replacement/re-encryption và data exposure.
- **KEK exposed:** cần review KEK replacement/rewrap và các DEKs mà attacker có thể đã giải bọc.
- **PRIVATE_SIGNING_KEY exposed:** cần trust/JWKS/certificate update, không chỉ DisableSign.
- **HMAC secret exposed:** cần chuyển secret version và ngừng verifier chấp nhận old key.
- **HSM non-exportable:** không tự suy material lộ, nhưng phải điều tra Sign/Decrypt misuse.
- **RECOVERY_SHARE exposed:** cần review quorum/custody, khả năng tái cấu trúc shares hoặc đổi secret.

### 21.2. Những gì code chưa thực hiện

Code này không kết nối IdP/IAM/KMS/HSM, không xác minh principal, không phân tích nhiều key assets cùng lúc, không bảo đảm dữ liệu đã lộ, không có provider-specific state machine và không có enforcement về timing.

Bộ thực thi production cần:

1. Nhận **identity và approval từ trust boundary độc lập**, không tin fields người gọi tự khai.
2. Sử dụng **key inventory và dependency graph** có owner/version.
3. Giới hạn operations theo least privilege; ngăn self-escalation.
4. Có **audit immutable, idempotency, retries, error handling và readback**.
5. Kiểm tra **rollback, DR, archived ciphertext và verifier trust** trước key destruction.
6. Kích hoạt negative tests hoặc canary theo phạm vi cho phép.
7. Có con người phê duyệt những thay đổi irreversible/rủi ro rộng.

**Kết quả Planner là kế hoạch cần review, không phải lệnh bắt buộc thực thi mọi rotation.**

## 22. Multi-region, offline workers và revocation propagation

KMS state đổi ở một region không có nghĩa mọi nơi đều lập tức ngừng dùng key material. Một workload có thể đã giữ **plaintext DEK/HMAC secret** từ trước, hoặc verifiers đang cache public key cũ.

| Thành phần | Rủi ro | Kiểm soát |
|---|---|---|
| **KMS ở nhiều regions** | Policy/grants/material state không giống nhau | Readback theo region/provider semantics |
| **Offline producer** | Tiếp tục Encrypt bằng DEK cũ khi reconnect | Material version, key epoch và cryptoperiod checks |
| **Secret manager cache** | Ứng dụng còn HMAC/DEK cũ | Invalidate, bounded TTL và workload isolation |
| **JWKS verifier** | Vẫn tin signing key bị revoke | Cache policy, explicit deny và token expiry handling |
| **mTLS session** | Phiên cũ còn hoạt động | Session termination và identity policy |
| **Queue/DLQ** | Replayed old activation events | Idempotent, monotonic epoch và event-version guard |
| **DR snapshot** | Khôi phục config/credential cũ | Post-restore validation, deny controls và key inventory |
| **Encrypted DEK ở archive** | Còn phụ thuộc KEK đã disable | KMS recovery plan và restore test |

### 22.1. Key version và alias

Một alias mới trỏ tới key v2 không xóa **plaintext material v1 trong RAM** hay các KMS key references đã ghi trong records. Cần theo dõi **old-key-use metrics, consumer activation state, grants và backup dependencies**.

### 22.2. Phân phối key mới không được tạo sự cố mới

Không gửi raw DEK/KEK/HMAC key qua HTTP plaintext, URL, chat hoặc debug logs để cutover nhanh. Dùng KMS/HSM API, wrapped DEK, authenticated workload identity và channel phù hợp.

## 23. Ba chiều tác động: bí mật, toàn vẹn và sẵn sàng

Emergency revocation có thể gây ảnh hưởng khác nhau trên ba trục:

- **Confidentiality:** attacker đã Decrypt hoặc lấy bản sao material chưa?
- **Integrity/authenticity:** attacker có thể tạo chữ ký/MAC giả hoặc sửa dữ liệu hợp lệ không?
- **Availability:** thao tác revoke/disable/destroy có thể làm ngừng sản xuất hoặc không thể restore không?

### 23.1. Thay key không xóa data breach lịch sử

Nếu plaintext đã bị lấy trước sự cố, re-encrypt hôm nay không khiến người có plaintext “quên” được. Phải đánh giá **data exposure, notification obligations và forensic limitations** theo policy.

### 23.2. Trust bị thu hồi không lan truyền thần kỳ

Một verifier của đối tác có thể còn cache JWKS/certificate, tiếp tục chấp nhận chữ ký dưới key cũ. Cần trao đổi **revocation propagation, cache lifetimes và contract-specific validation**.

### 23.3. Availability không biện hộ cho old compromised key vô hạn

Nếu cần giữ key cũ cho Decrypt lịch sử hoặc migration, điều đó không đồng nghĩa cho phép **Sign/Encrypt/MAC mới** bằng material đã bị lộ. Cần tách usage policy và đặt **deadline, audit, approved exception**.

## 24. Emergency revocation khi nhân sự/thiết bị thay đổi

Một Leaver/Mover event có thể chỉ cần thu hồi quyền. Nhưng nếu người đó từng **biết shared HMAC key, giữ raw private signing key, hoặc giữ HSM recovery share**, tổ chức cần đánh giá material/trust rotation.

### 24.1. Các đường cần rà soát

- IdP sessions, refresh tokens, cloud accounts và AssumeRole.
- KMS grants, Sign/Decrypt/Unwrap/CreateGrant/ChangeKeyPolicy.
- SSH keys, PAT, CI/CD credentials và code repositories.
- Local vault/cache, endpoint, lost devices và browser sessions.
- HSM operator cards, recovery quorum và secret shares.
- Public trust/certificate management và signer approvals.

### 24.2. Đừng đánh đồng quyền truy cập với việc đã sao chép key

Một operator có quyền điều hành **HSM non-exportable** chưa chắc đã biết raw KEK; nhưng operator đó có thể đã gọi Decrypt/Sign trái phép hoặc thay grants. Xác minh effective permissions và audit trước khi quyết định material rotation.

### 24.3. Thu hồi recovery share

Thay custodian phải đi cùng **thu hồi smartcard/credentials, kiểm tra threshold/quorum, re-share/reconstitute khi phù hợp và diễn tập recovery**. Không xuất raw master key sang wiki để “bàn giao khẩn”.

## 25. Case study A: workload identity bị chiếm và lạm dụng KMS Decrypt

Một dịch vụ thanh toán dùng KMS Unwrap để lấy plaintext DEK tạm, mã hóa/giải mã hóa đơn bằng AES-GCM. Attacker lấy được **workload credential** và gọi KMS Decrypt trên hàng loạt encrypted DEKs.

### 25.1. Điều gì bị lộ?

KMS có thể không cho xuất raw KEK, nhưng API Decrypt đã **có thể trả plaintext DEK** cho caller theo thiết kế. Do đó không thể chỉ dựa vào nhãn **KEK non-exportable** để kết luận dữ liệu vẫn bí mật.

### 25.2. Phản ứng

1. Thu hồi compromised credential, sessions, assume-role capability và KMS grants.
2. Chặn đường self-escalation như CreateGrant/ChangeKeyPolicy và CI/CD job giả danh workload.
3. Bảo toàn KMS audit và correlated data-access events.
4. Xác định những DEKs đã bị Unwrap hoặc có khả năng bị truy cập trong incident window.
5. Tìm ciphertext/tenant/object và backups tương ứng.
6. Đánh giá **replace affected DEKs/re-encrypt**, đồng thời rà soát KEK policy và grants.
7. Rollout workload identity mới với least privilege và KMS context đúng.
8. Kiểm tra negative permissions của principal cũ, positive decrypt của workload hợp lệ.
9. Ghi residual risk vì plaintext DEKs/dữ liệu đã có thể nằm ngoài hệ thống.

### 25.3. Điều không nên tuyên bố

- “Raw KEK không bị export nên không có data breach.”
- “Đã rotate KEK, vì vậy mọi DEK mà attacker có trước đó tự hết hiệu lực.”
- “KMS trả success cho revoke grant tức là mọi worker cache DEK đã bị chặn.”

**Bài học:** Thu hồi IAM/KMS grants là **containment**, còn xử lý **plaintext DEKs đã có thể bị lấy** cần một kế hoạch khác.

## 26. Case study B: plaintext DEK xuất hiện trong CI log

Một pipeline debug đã vô tình in DEK thành base64 trong CI logs. DEK này bảo vệ một dataset đã được backup; KEK bọc DEK vẫn nằm an toàn trong KMS.

### 26.1. Vì sao chỉ DisableKey chưa đủ?

Kẻ đã đọc log có thể decode base64 và sở hữu **DEK dạng rõ**. Họ có khả năng giải mã ciphertext đã thu thập **offline**, không cần KMS. Do vậy **revoke CI credential, Disable KEK hoặc rewrap DEK** không xóa được bản DEK đã bị lộ.

### 26.2. Playbook

1. Dừng code path log key, cô lập access bất thường và bảo toàn evidence.
2. Kiểm kê log replicas, exports, snapshots, build artifacts và người có quyền truy cập.
3. Xác định DEK material, encrypted records, key scope, key version và data classification.
4. Chặn Encrypt mới dưới DEK cũ.
5. Generate **DEK mới** bằng KMS/CSPRNG, cập nhật producers.
6. Đánh giá **Decrypt/Verify rồi Re-encrypt** các ciphertext bị ảnh hưởng dưới DEK/nonce/tag mới.
7. Kiểm tra AAD/tenant binding và backup restore.
8. Đánh giá khả năng dữ liệu đã bị lấy, yêu cầu thông báo và residual risk.
9. Thêm secret-scanning, logging redaction và negative tests cho pipelines.

**Bài học:** Secret lộ trong log có thể là compromise vật liệu, không chỉ compromise quyền truy cập.

## 27. Case study C: private JWT signing key bị đánh cắp

Một ứng dụng phát JWT bằng private key lưu trong file. File bị sao chép trái phép. Verifiers ở nhiều regions dùng JWKS và có cache với TTL khác nhau.

### 27.1. Tác động

Attacker có private key có thể **ký token ở ngoài hệ thống**. Những verifiers còn trust public key cũ có thể chấp nhận signature hợp lệ về toán học, dù token không do issuer thật tạo.

### 27.2. Phản ứng

1. Cô lập máy chủ, revoke compromised credential và dừng Sign bằng material cũ.
2. Tạo signing key pair mới trong HSM/KMS hoặc key store được quản lý.
3. Cập nhật signer, kid và public JWKS từ nguồn issuer đáng tin.
4. Xem xét **thu hồi old public-key trust** và những JWTs còn hiệu lực theo incident severity.
5. Kiểm tra **issuer, audience, algorithm allowlist, token expiry và cache propagation** tại verifiers.
6. Giám sát old kid usage, token bất thường, access từ môi trường chưa refresh.
7. Giữ bằng chứng cần cho signatures/tokens lịch sử mà không tiếp tục cho old compromised key Sign.
8. Báo cáo giới hạn của việc invalidate: verifiers offline/cache có thể chưa nhận revoke.

### 27.3. Điều không đủ

- Chỉ **DisableSign** trong KMS/HSM nếu private key đã có bản sao bên ngoài.
- Chỉ **đổi kid** nhưng giữ nguyên private key bytes.
- Chỉ **xóa JWKS entry** mà không xác minh effective verifier trust.
- Chỉ xem signature hợp lệ rồi khẳng định token do issuer hợp lệ phát hành.

**Bài học:** Thu hồi khóa ký phải phối hợp **material mới, verifier trust, token/session invalidation và xử lý lịch sử**.

## 28. Case study D: Disable KEK quá rộng gây outage và DR thất bại

Một vai trò IAM bị chiếm có thể gọi Decrypt bằng KEK chung cho ba tenant. Nhóm vận hành Disable KEK toàn bộ mà chưa có dependency inventory.

### 28.1. Hệ quả

- Readers không thể Unwrap encrypted DEKs trong KMS.
- API nghiệp vụ dừng, trong khi một số instances cache plaintext DEKs vẫn hoạt động.
- Backup restore thất bại vì KEK bị Disabled.
- Emergency team cân nhắc Destroy KEK, có thể gây **mất khả năng giải mã vĩnh viễn** khi archive còn phụ thuộc.

### 28.2. Cách xử lý đúng phạm vi

1. Trước hết đánh giá khả năng **revoke principal-specific IAM/grant/session**, cô lập workload và khóa quyền tự cấp lại.
2. Nếu bắt buộc DisableKey, incident commander phải ghi rõ **blast radius, approved continuity plan và safety constraints**.
3. Bảo toàn ciphertext, encrypted DEK, keyRef/material version, nonce/tag/AAD và backup metadata.
4. Chuẩn bị KEK mới và workflow **rewrap** hoặc re-encrypt theo mức exposure.
5. Kiểm thử authorized readers và **restore bằng DR role** có approval.
6. Theo dõi DEK caches, offline consumers và old-key-use metrics.
7. Không gọi Destroy trước dependency clearance, retention review và provider evidence.
8. Ghi lý do đã chọn Disable toàn bộ thay vì chỉ deny principal, kể cả hiệu quả thực tế.

**Bài học:** Emergency containment phải có **đúng scope và bằng chứng**, không áp dụng máy móc “disable tất cả” hoặc “chỉ đổi IAM” cho mọi sự cố.

## 29. Ma trận kiểm thử emergency revocation

Kiểm thử phải bao gồm **positive path** của các workload hợp lệ và **negative path** của principal/key đã bị revoke.

| Tình huống | Kết quả mong đợi |
|---|---|
| Cloud access token bị revoke | Không còn sử dụng được operation theo provider policy |
| SSO disabled nhưng refresh token còn hoạt động | Phát hiện và xử lý propagation gap |
| Không có KMS Decrypt nhưng có CreateGrant | Effective permission review phát hiện self-escalation |
| IAM principal cố sửa key policy sau revoke | Bị chặn |
| KMS grant revoked, ứng dụng còn cached DEK | Cache/workload kiểm soát đường dùng cũ |
| KMS DisableKey | KMS từ chối thao tác theo semantics provider |
| KMS key disabled nhưng attacker giữ raw KEK | Báo cáo không tuyên bố raw material đã bị thu hồi |
| Emergency API timeout giữa chừng | Readback và reconcile thay vì đoán trạng thái |
| SIEM gửi cùng alert ba lần | Workflow idempotent theo incident/action IDs |
| Alias đổi trước khi action được thực thi | Resource/material verification ngăn thao tác nhầm |
| Incident bot thử ScheduleDeletion không approval | Safety policy từ chối |
| Role có quyền xóa audit events | Independent audit/SoD chặn hoặc phát hiện |
| Plaintext DEK lộ trong CI log | Có replacement/re-encryption review và impact assessment |
| Chỉ rewrap DEK đã lộ | Không được kết luận remediate hoàn chỉnh |
| Raw KEK có thể bị sao chép | Inventory wrapped DEKs và potential DEK exposure |
| Rotate KEK nhưng DEK giữ nguyên | Nonce state của DEK không reset |
| AES-GCM nonce reuse | Stop new Encrypt dưới DEK và điều tra affected ciphertext |
| Signing private key raw bị lộ | Verifier trust/JWKS/cert policy được cập nhật |
| JWT verifier vẫn cache old compromised key | Propagation test báo chưa hoàn tất |
| JWT chứa alg/kid giả | Algorithm/issuer/trust allowlist từ chối |
| HSM key non-exportable nhưng Sign API bị misuse | Incident audit xem các chữ ký đã tạo |
| Shared HMAC secret lộ | Producers/verifiers chuyển key; old acceptance chấm dứt |
| Verifier dual-accept secret đã lộ vô hạn | Negative policy test phát hiện |
| Certificate bị CA revoke | Client/mesh thực sự không tiếp tục tin theo policy |
| mTLS session vẫn còn sau revoke | Session control được kiểm tra |
| IAM state đã đổi ở Region A nhưng Region B chưa đổi | Cross-region readback phát hiện |
| Offline writer reconnect với DEK/epoch cũ | Policy chặn new Encrypt khi cần |
| Replay activation message cho old key | Monotonic version/idempotency ngăn hồi sinh |
| Disable KEK khiến DR không thể restore | Recovery test phát hiện và có kế hoạch xử lý |
| ScheduleDeletion chưa hoàn thành | Không báo key đã Destroyed |
| Archive còn encrypted DEK dưới KEK cũ | Dependency guard không cho destruction |
| Crypto-shredding nhưng raw key đã nằm ngoài KMS | Không tuyên bố mọi bản mã chắc chắn không thể đọc |
| Caller tráo tenant/object metadata | Business authorization và AAD/context từ chối |
| Audit/log thiếu các operation quan trọng | Closure ghi rõ evidence gap và residual risk |
| New material được rollout qua HTTP plaintext | Security test từ chối |
| Break-glass không có TTL, independent approval hoặc audit | Policy cảnh báo/chặn |
| Incident đã CLOSED nhưng old-key-use vẫn xuất hiện | Monitoring mở lại hoặc báo escalation |
| Re-encryption hoàn tất nhưng data đã bị đọc trước đó | Báo cáo residual data exposure trung thực |

### 29.1. Không chỉ thử đường bị từ chối

Cũng cần xác minh:

- Workload mới có thể Decrypt/Verify dữ liệu hợp lệ với đúng DEK/KEK/format.
- Payload AEAD tag/AAD kiểm tra thành công và không bị bỏ qua.
- Producer mới không Encrypt/Sign dưới material cũ.
- JWT verifiers nhận chữ ký hợp lệ từ issuer mới và từ chối old compromised key theo policy.
- Backup restore vẫn thực hiện được ở miền DR đã phê duyệt.
- Audit vẫn ghi đầy đủ actor/keyRef/version/outcome mà không có plaintext secret.

### 29.2. Kiểm thử an toàn

Các negative tests nên dùng **canary identity/test keys và môi trường được phép**; không sử dụng raw production KEK hoặc xóa key thật chỉ để chứng minh deny. Với hệ thống production, chọn những thao tác read-only/harmless có đủ authorization và có giám sát.

## 30. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách phòng |
|---|---|---|
| Revoke IAM rồi nghĩ raw key bị xóa | Attacker vẫn giữ material offline | Phân biệt identity compromise và material exposure |
| Disable KMS key nhưng bỏ qua cached DEK | Một số processes vẫn dùng DEK | Cache invalidation/worker isolation |
| Tự Destroy KEK khi thấy alert | Mất dữ liệu và backup phụ thuộc | Approval, inventory, restore test |
| ScheduleDeletion được báo là Destroyed | Trạng thái sai thực tế | Provider readback và event evidence |
| Rewrap DEK rõ đã lộ và cho là an toàn | DEK cũ vẫn giải mã được ciphertext | New DEK/re-encrypt assessment |
| Đổi alias mà không thay key bytes | Không giải quyết lộ material | Generate actual new material |
| Đổi ciphertext/nonce/tag bằng tay | AEAD authentication thất bại | Decrypt/Verify và re-encrypt đúng |
| Reset nonce counter khi KEK rotate | GCM nonce reuse dưới DEK cũ | Giữ nonce namespace theo DEK material |
| Bỏ tag verification để đọc backup | Chấp nhận plaintext chưa xác thực | Fail closed và recovery workflow |
| Key non-exportable được coi không thể bị lạm dụng | Sign/Decrypt oracle vẫn có thể hoạt động | Effective IAM, business authz, audit |
| Revoke Sign trong HSM nhưng private key raw đã bị lộ | Attacker vẫn ký offline | Key pair mới + verifier trust revocation |
| Chỉ xóa public key trên một JWKS | Verifiers khác còn cache old key | Trust rollout/TTL và thực tế kiểm thử |
| Xóa mọi public key lịch sử | Không verify được chữ ký hợp lệ | Archive validation policy |
| Chỉ revoke CA certificate mà không kiểm tra clients | Client có thể chưa nhận trạng thái | End-to-end trust revocation test |
| Dual-verify HMAC đã lộ vô thời hạn | Attacker tiếp tục giả MAC | Chính sách cutoff theo severity |
| Gửi new secret qua chat để cắt chuyển | Tạo thêm secret leak | Authenticated provisioning |
| Chỉ nhìn tên role, không xem CreateGrant/AssumeRole | Đường tự cấp lại quyền | Effective permission graph |
| Không quản lý scope theo tenant/application | Sự cố ảnh hưởng diện rộng | Key separation/least privilege |
| Không có idempotency | Duplicate alert gây rotate/disable lặp | Incident/action IDs và state machine |
| Tin HTTP 200 là đã thu hồi hoàn toàn | Chỉ có thể là request accepted | State readback, deny tests |
| Bỏ quên offline consumers/regions | Old material tiếp tục được chấp nhận | Key epochs, propagation monitoring |
| Xóa logs để giảm nhiễu | Mất evidence quan trọng | Independent audit protection |
| Re-encrypt xong tuyên bố không có data breach | Dữ liệu đã lộ không thu hồi được | Exposure/impact assessment |
| Dùng một shared emergency password | Có thể đã được nhiều người biết | Break-glass/JIT/quorum |
| Xóa keyRef gọi là crypto-shredding | Key material/recovery path có thể còn | Verify actual destruction |
| Bỏ qua cryptoperiod vì "đang xử lý sự cố" | Old key vẫn được dùng ngoài hạn mức | Owner, policy, cutover deadline |

## 31. Câu hỏi tự kiểm tra

**Câu 1. Emergency revocation có đồng nghĩa với xóa ngay mọi key liên quan không?**

**Trả lời:** Không. Mục tiêu đầu tiên là containment; Destroy có thể làm mất ciphertext/backups và không xóa raw key mà attacker đã sao chép. Phải phân biệt revoke quyền, disable operations, rotate material và destruction.

**Câu 2. Thu hồi KMS grant có làm mất plaintext DEK đã được ứng dụng cache không?**

**Trả lời:** Không. KMS có thể ngăn Unwrap mới, nhưng DEK đã trả ra vẫn có thể tồn tại trong RAM/cache và cần biện pháp consumer-side.

**Câu 3. Nếu attacker chỉ lấy cloud access token, có bắt buộc re-encrypt mọi dữ liệu không?**

**Trả lời:** Không mặc định. Cần revoke credential, điều tra quyền/operations và xem attacker có lấy DEK/plaintext data hay không; quyết định key rotation theo exposure và policy.

**Câu 4. KEK non-exportable có loại bỏ mọi rủi ro compromise không?**

**Trả lời:** Không. Attacker có quyền KMS Decrypt/Sign vẫn có thể lạm dụng API; raw KEK không export không bảo đảm DEKs hoặc plaintext data chưa bị trả ra.

**Câu 5. Tại sao rewrap DEK không giải quyết DEK đã lộ?**

**Trả lời:** Rewrap đổi lớp bọc, không đổi plaintext DEK bytes. Bản DEK attacker đang giữ vẫn giải mã ciphertext cũ.

**Câu 6. KEK bị lộ có thể ảnh hưởng cả những encrypted DEK đã lưu trước đây không?**

**Trả lời:** Có. Nếu attacker có KEK và các wrapped DEKs cũ tương ứng, họ có thể unwrap offline. Phải đánh giá dữ liệu lịch sử và DEK rotation/re-encryption theo rủi ro.

**Câu 7. Nếu private signing key đã bị sao chép, DisableSign trong HSM có đủ không?**

**Trả lời:** Không. Attacker có thể ký ngoài HSM. Cần key pair mới và cập nhật verifier trust/JWKS/certificate, cùng điều tra chữ ký đã phát sinh.

**Câu 8. Xóa old kid khỏi một JWKS endpoint có khiến mọi verifier ngừng chấp nhận ngay không?**

**Trả lời:** Không chắc. Verifiers có thể cache JWKS, giữ token và có trust configuration khác. Cần propagation tests.

**Câu 9. Shared HMAC secret bị lộ cần làm gì?**

**Trả lời:** Tạo secret mới, chuyển producers/verifiers hợp lệ, ngừng chấp nhận old version theo incident policy, đồng thời đánh giá replay và events đã giả mạo.

**Câu 10. Vì sao không tự động bật dual-verify lâu dài khi HMAC bị compromise?**

**Trả lời:** Khi verifier còn tin key cũ, attacker giữ secret cũ vẫn có thể tạo MAC hợp lệ.

**Câu 11. Certificate revoked tại CA có tự chấm dứt mọi TLS session đã mở không?**

**Trả lời:** Không mặc nhiên. Phải xem client/server revocation checking, cache và session termination.

**Câu 12. ScheduleDeletion và Destroyed có giống nhau không?**

**Trả lời:** Không. ScheduleDeletion là trạng thái/quy trình theo provider, chưa nhất thiết hủy vật liệu. Cần xác minh kết quả thực tế.

**Câu 13. Tại sao phải xem effective IAM permissions chứ không chỉ role name?**

**Trả lời:** Một principal có thể tự cấp quyền hoặc vào role khác qua AssumeRole/CreateGrant/ChangeKeyPolicy, ngay cả khi không có Decrypt trực tiếp.

**Câu 14. Vì sao không sửa nonce trong record cũ khi phát hiện AES-GCM nonce reuse?**

**Trả lời:** Nonce là đầu vào khi Encrypt. Sửa metadata mà không Encrypt lại hợp lệ sẽ phá tag; phải đánh giá replacement DEK và re-encrypt đúng.

**Câu 15. Có thể giữ old KEK cho Decrypt lịch sử mà ngừng dùng Encrypt/Wrap mới không?**

**Trả lời:** Có thể nếu hệ thống/provider/policy hỗ trợ phân biệt usage và authorization; phải giám sát access nghiêm ngặt và xử lý khi key material thực sự bị compromise.

**Câu 16. Tại sao emergency DisableKey có thể gây outage?**

**Trả lời:** Nhiều datasets/tenants có thể cần KEK đó để Unwrap DEK. Không có restore path phù hợp thì business operations/DR sẽ thất bại.

**Câu 17. Khi KMS API revoke trả timeout, có nên gọi ngay lần nữa mà không kiểm tra?**

**Trả lời:** Không mặc định. Cần readback/reconciliation và idempotency theo provider để biết trạng thái thực tế.

**Câu 18. Đã re-encrypt dữ liệu, có thể tuyên bố attacker không còn biết plaintext cũ?**

**Trả lời:** Không. Nếu plaintext đã bị lấy, rotation không thể thu hồi kiến thức hoặc bản sao đã tồn tại.

**Câu 19. Một incident có thể coi là contained chỉ nhờ ticket DONE không?**

**Trả lời:** Không. Cần evidence về hiệu lực của access deny, kiểm tra cached/offline consumers, key/trust cutover, audit và negative tests phù hợp.

**Câu 20. Crypto-shredding có thành công nếu một người từng copy raw DEK ra ngoài KMS không?**

**Trả lời:** Không thể chứng minh chỉ bằng cách Destroy key tại provider, vì bản copy đó có thể vẫn giải mã dữ liệu. Cần đánh giá mọi material copies và recovery paths.

## 32. Checklist triển khai và đóng sự cố

Trước khi đánh dấu hoàn tất **Emergency revocation**, hãy kiểm tra:

- **Trigger:** incident signal, time window, affected identity/keyRef, severity và owner được xác định?
- **Containment:** compromised sessions/tokens, IAM/KMS grants và đường self-escalation đã bị chặn?
- **Key material:** xác định rõ raw DEK/KEK/private signing/HMAC/PSK/recovery share có thể đã lộ chưa?
- **Scope:** có key inventory liên kết material, owners, consumers, tenants, datasets và backups?
- **KMS/HSM:** Disable/revoke/rotate/destroy được phân biệt theo provider semantics?
- **Non-exportable:** đã kiểm tra Sign/Decrypt/GenerateDataKey API misuse, không chỉ tính exportability?
- **DEK:** khi raw DEK có nguy cơ lộ, đã đánh giá new DEK/re-encrypt và dữ liệu đã bị xem?
- **KEK:** khi KEK lộ, đã đánh giá affected wrapped DEKs, rewrap và khả năng thay DEK?
- **Signing:** private key mới, JWKS/certificate/trust rollout và old-token handling đã được kiểm thử?
- **HMAC:** shared secret version mới, consumer cutover và old acceptance cutoff theo severity?
- **PKI:** revocation checking, cache, TLS/mTLS sessions và trust anchors đã được xử lý?
- **Nonce/AEAD:** không reset nonce state sai khi KEK rewrap; tag/AAD luôn được xác thực?
- **Cache:** plaintext DEK/secret/tokens trong memory/sidecar/offline workers đã được đánh giá?
- **Multi-region:** effective deny/readback và trust propagation được kiểm tra ở từng vùng cần thiết?
- **Audit:** evidence về actor, approval, operation, keyRef/material version, result được bảo vệ độc lập?
- **No secret logging:** không có raw key/token/plaintext nhạy cảm trong logs, tracing, CI hoặc tickets?
- **Workflows:** idempotency, incident/action IDs, retries, provider timeout reconciliation và stop controls có hoạt động?
- **SoD:** irreversible actions có independent approval; break-glass có TTL, scope và audit?
- **Backup/DR:** encrypted DEKs, key versions, nonce/tag/AAD và recovery principal đã được kiểm thử restore thật?
- **Retirement/Destruction:** không Destroy khi dependencies chưa được clearance; xác nhận provider state thay vì đoán?
- **Testing:** negative access, old-key-use, verifier/JWKS, HMAC cutoff, crypto round-trip và DR đều đạt?
- **Residual risk:** dữ liệu/secret đã có thể bị attacker lấy trước containment được báo cáo đúng?
- **Closure:** có owner, evidence, outstanding exceptions, deadline, hậu kiểm và monitoring tiếp diễn?

**Ghi nhớ:** **Emergency revocation** không phải một nút “xóa khóa”. Đây là quy trình **nhanh chóng chặn quyền đang bị lạm dụng, đánh giá vật liệu và dữ liệu có nguy cơ, thay đúng khóa/credential hoặc trust bị compromise, kiểm tra hiệu lực ở mọi consumer/region và bảo đảm khả năng phục hồi dữ liệu hợp lệ**. **Revoke IAM không xóa bản sao raw DEK; rewrap KEK không thay DEK; DisableSign không ngăn private key đã lộ ký ở ngoài HSM; và DestroyKey sớm có thể làm mất dữ liệu mãi mãi.** Kết hợp **KMS/HSM, IAM, envelope encryption, AEAD, chữ ký số, cryptoperiod, SoD, audit, backup/DR, negative tests và incident response** để xử lý sự cố đúng mức, có bằng chứng và kiểm soát được hậu quả.
