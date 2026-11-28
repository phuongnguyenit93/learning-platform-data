# Suspend key – Tạm đình chỉ khóa mật mã khi nghi ngờ rủi ro hoặc cần cô lập sử dụng

**Suspend key** (tạm đình chỉ khóa mật mã) là hành động **tạm ngừng một số hoặc toàn bộ khả năng sử dụng khóa trong một phạm vi kiểm soát**, nhằm ngăn các thao tác mật mã mới, cô lập nghi vấn compromise, hoặc tạo thời gian điều tra mà **chưa thực hiện ngay thao tác hủy vật liệu khóa không thể đảo ngược**. Mục tiêu của việc suspend là **giảm rủi ro trong hiện tại và bảo toàn khả năng ra quyết định tiếp theo**; nó **không tự chứng minh khóa vẫn bí mật**, không tự vô hiệu mọi bản sao bên ngoài và không thay thế quy trình **revoke, rotate, re-encrypt, cập nhật trust hoặc destroy** khi sự cố yêu cầu.

Trong chương **Revocation và compromise** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, việc đình chỉ khóa nằm giữa **sử dụng khóa** và **thu hồi/xử lý khóa có nguy cơ bị lộ**. Nó liên hệ trực tiếp với toàn bộ vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**, mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, IAM, key inventory, cryptoperiod, audit và backup/DR.

> **Nguyên tắc quan trọng nhất:** **Tạm dừng khả năng gọi KMS không thể buộc kẻ tấn công quên raw key đã biết.** Ngược lại, **disable một KEK** khi dữ liệu vẫn phụ thuộc vào nó có thể làm ứng dụng hợp lệ **không unwrap được DEK** và gây gián đoạn lớn. Suspend phải có **phạm vi, mục tiêu, quyền phê duyệt, đường khôi phục và tiêu chí kết thúc**, không phải nút “an toàn tuyệt đối”.

## 1. Suspend key là gì?

Có ba cách phổ biến để một tổ chức triển khai ý tưởng “suspend”:

1. **Tạm dừng ở mức ứng dụng/chính sách sử dụng:** không tạo thêm ciphertext hoặc chữ ký mới bằng một key; tiếp tục một số thao tác đọc/Verify cũ nếu policy cho phép. Ví dụ: Sign bằng S1 bị tắt nhưng Verify chữ ký lịch sử vẫn được xét theo quy tắc riêng.
2. **Tạm dừng quyền truy cập:** thu hồi hoặc tạm khóa grants, service accounts, role sessions hoặc key policy cho một nhóm principal/operation. Key material vẫn nằm trong KMS/HSM; những principal khác có thể tiếp tục sử dụng nếu chính sách chủ động cho phép.
3. **Tạm vô hiệu hóa key object tại KMS/HSM:** provider chặn một tập thao tác mật mã trên key được disable. Cơ chế và phạm vi **phụ thuộc dịch vụ và loại key**, đôi khi chặn cả Decrypt/Unwrap lẫn Encrypt/Wrap, không chỉ chặn new writes.

Trong cả ba trường hợp, tổ chức cần biết **mình đã đình chỉ *key material*, *key object*, *key usage*, *principal* hay *trust acceptance***. Chúng là các lớp khác nhau.

### 1.1. Mục tiêu của suspend

- **Containment:** giảm hoặc dừng đường sử dụng khóa có dấu hiệu bị lạm dụng.
- **Time to investigate:** giữ key material và bằng chứng trong khi xác minh rủi ro.
- **Limit further signing/encryption:** chặn các thao tác tạo mới không còn được phê duyệt.
- **Reversible response khi thích hợp:** có đường khôi phục dịch vụ sau khi nguyên nhân được xử lý và khóa được chứng minh vẫn có thể tin cậy.
- **Controlled migration:** tạo điều kiện chuyển sang key successor hoặc bảo đảm luồng sử dụng cũ không tiếp tục phát sinh dữ liệu mới.
- **Auditability:** lưu dấu ai ra quyết định, phạm vi, vì sao, thời hạn, bên nào bị ảnh hưởng và kết quả kiểm tra.

**Đừng coi tính đảo ngược là một lời hứa luôn được phép resume.** Nếu điều tra xác nhận private key đã lộ, thường cần **rotate/revoke** thay vì bật lại nó. Việc suspend có thể là bước tạm trên đường tới **revocation cuối cùng**.

### 1.2. Ví dụ ngắn

Payment Service ký payment events bằng private signing key S1 trong HSM. SOC phát hiện một workload lạ vừa gọi Sign S1. Đội bảo mật có thể:

1. Chặn workload lạ hoặc revoke credential ngay.
2. Tạm dừng Sign mới bằng S1 trong phạm vi phù hợp.
3. Điều tra những chữ ký đã tạo và các consumer còn tin S1.
4. Sinh key S2 theo phê duyệt, phân phối public key S2 và chuyển signer.
5. Quyết định **resume S1 hay revoke vĩnh viễn** dựa vào bằng chứng compromise.

Nếu S1 là khóa ký chính của giao dịch đang chạy, việc disable toàn bộ có thể gây outage. Một phương án containment có thể **chặn principal bất thường trước**, triển khai signer dự phòng và chỉ sau đó disable S1, tùy mức nghiêm trọng. Tuy nhiên nếu tiếp tục cho S1 Sign có thể gây thiệt hại không chấp nhận được, an toàn có thể cần ưu tiên hơn tính sẵn sàng.

## 2. Suspend, revoke, disable, retire, expire và destroy khác nhau thế nào?

Trong các hệ thống, tên trạng thái thường không thống nhất. Điều cần hiểu là **hiệu ứng bảo mật thực**.

| Khái niệm | Mục đích | Có thể đảo ngược? | Hậu quả cần kiểm |
| --- | --- | --- | --- |
| **Suspend** | Đình chỉ sử dụng trong khi điều tra, bảo trì hoặc chuyển đổi. | **Có thể**, tùy policy và loại sự cố. | Phải xác minh operation nào thật sự bị chặn. |
| **Disable key** | Vô hiệu hóa key object theo API provider. | Có thể có `EnableKey`, nhưng không phải mọi key state/provider đều hỗ trợ. | Có thể chặn cả Decrypt/Unwrap và gây mất availability. |
| **Revoke access/grant** | Cắt quyền của một actor/identity. | Có thể cấp lại quyền hợp lệ sau phê duyệt. | Session còn sống, propagation và quyền khác vẫn có thể tồn tại. |
| **Revoke trust/certificate** | Ngừng chấp nhận một identity hoặc public key theo trust policy. | Tùy cơ chế; không giả định có thể hoàn tác. | Consumer caches, offline Verify, CRL/OCSP và chính sách thời gian. |
| **Retire key** | Kết thúc dùng cho tác vụ mới, có thể giữ quyền đọc lịch sử. | Phụ thuộc lifecycle policy. | Không nhầm read-only legacy với disabled toàn bộ key object. |
| **Expire/cryptoperiod end** | Hết cửa sổ sử dụng hoặc hợp lệ theo policy. | Thường cần successor/exception riêng; không tự kéo dài. | Khóa hết hạn vẫn có thể cần để giải mã dữ liệu cũ. |
| **Rotate key** | Tạo/chuyển sang vật liệu hoặc key version mới. | Không nên tự quay lại key đã compromise. | Consumer compatibility, dữ liệu/chữ ký cũ và backup. |
| **Destroy/delete key** | Loại bỏ key material theo cơ chế được phê duyệt. | Có thể **không thể đảo ngược**. | Có thể mất khả năng decrypt dữ liệu/restore lâu dài. |

### 2.1. Suspend là trạng thái nghiệp vụ, disable là thao tác kỹ thuật

Một tổ chức có thể định nghĩa:

~~~text
Policy state = SUSPENDED
Provider key state = ENABLED
Allowed operations = { VERIFY_PUBLIC_HISTORICAL } (nếu phù hợp)

Hoặc:
Policy state = SUSPENDED
Provider key state = DISABLED
Allowed provider crypto operations = tùy hợp đồng KMS/HSM
~~~

Hai cấu hình này không tương đương. Nếu cần **giữ Decrypt legacy nhưng cấm Encrypt mới**, một lệnh **disable toàn bộ KMS key** có thể không đáp ứng mục tiêu. Có thể phải dùng **application policy, IAM permissions theo operation, key version routing hoặc key successor** để thực thi phân tách đó.

**Không được tuyên bố `SUSPENDED` đã chặn sử dụng nếu chỉ đổi một cờ trong database mà các service khác bỏ qua cờ ấy.** Tính hiệu lực phải được chứng minh bằng **negative tests tại điểm thực thi**.

### 2.2. “Certificate hold” không phải suspend phổ quát

Trong một số hệ PKI, có thể gặp trạng thái/chỉ báo **certificate hold** hoặc cơ chế tạm dừng chứng chỉ. **Không được suy rằng mọi CA, OCSP responder, client hoặc hệ thống PKI đều hỗ trợ hủy hold/resume giống nhau**. Certificate revocation, KMS key disable và ứng dụng tạm dừng Sign là những cơ chế khác nhau, cần theo **contract và profile thực tế**.

## 3. Suspend ở lớp nào của hệ thống?

~~~mermaid
flowchart TD
    CALLER["Principal / workload / người dùng"] --> IAM["Identity, session, IAM grants"]
    IAM --> APP["Application authorization + key-use policy"]
    APP --> KMS["KMS/HSM key object"]
    KMS --> OPS["Sign / Encrypt / Unwrap / Decrypt"]
    OPS --> OUT["Ciphertext, wrapped DEK, signature, plaintext tạm"]
    APP --> TRUST["Registry / JWKS / PKI trust"]
    TRUST --> VER["Verify public signature tại consumer"]
    OUT --> STORAGE["Object storage / cache / backup"]
~~~

Có thể đặt điều khiển **suspend** ở một hoặc nhiều lớp:

- **Identity layer:** revoke credential/session, khóa role.
- **Authorization layer:** chặn service hoặc tenant cụ thể.
- **Key use policy layer:** cấm operation mới trên key, dù key object còn enabled.
- **Provider key layer:** disable key object hoặc sửa quyền crypto theo API.
- **Trust layer:** không còn chấp nhận chữ ký hay public-key binding theo policy.
- **Data layer:** chặn đọc plaintext hoặc chuyển sang DEK/KEK mới.
- **Replication/backup layer:** bảo đảm nguồn phục hồi không hồi sinh policy/key state cũ.

Một sự cố nghiêm trọng có thể cần áp dụng **nhiều lớp đồng thời**. Ví dụ revoke IAM principal không xử lý các DEK đã được trả về dưới dạng plaintext trước đó; disable private signing key không tự làm Ledger ngừng tin chữ ký cũ nếu Ledger Verify hoàn toàn offline.

## 4. Khi nào nên suspend thay vì lập tức destroy?

Một số tình huống phù hợp để cân nhắc suspension:

| Tình huống | Tại sao suspend hữu ích? | Điều phải xác minh |
| --- | --- | --- |
| **Nghi ngờ principal lạm dụng Sign** | Dừng ký mới để điều tra, chưa kết luận private key đã bị lấy ra. | Source identity, KMS Sign logs, session/grants, signer availability. |
| **Nghi một key được dùng sai purpose** | Ngừng phát sinh dữ liệu mới, giữ đường đọc phục vụ migration. | Key usage, ciphertext dependencies, policy scope. |
| **IAM policy cấp nhầm quyền Decrypt** | Khóa principal/grant nhanh trong khi rà soát truy cập. | Có Decrypt/Unwrap thành công hay DEK/plaintext bị trả ra không? |
| **Kiểm toán phát hiện legacy algorithm** | Cấm new-write yếu; cần thời gian chuyển các bản ghi lịch sử. | Cryptoperiod, reader compatibility, migration kế hoạch. |
| **Khóa có thể bị lỗi cấu hình HSM/KMS** | Tạm dừng operation nhạy cảm trong lúc xác minh key provenance. | Key generation/import, backup, audit và provider status. |
| **Vận hành bảo trì khóa có rủi ro** | Cô lập usage trong thời gian thay infrastructure theo runbook. | RPO/RTO, cutover, rollback có kiểm soát. |
| **Private key nghi lộ qua CI artifact** | Chặn Sign/Decrypt, bảo toàn evidence và đánh giá rotate. | Raw key đã có thể bị copy, ai tải artifact và timeline. |
| **Có lệnh pháp lý/chính sách đóng băng usage** | Ngăn sử dụng mới nhưng giữ evidence/retention theo yêu cầu. | Nghĩa vụ lưu trữ, phạm vi quyền, approval. |

**Không nên chỉ suspend rồi chờ vô thời hạn** khi có bằng chứng raw DEK, KEK hoặc private key đã lộ. Khi đó phải coi đây là sự cố **material compromise**, đánh giá **rotate/re-encrypt/revoke trust**, và chỉ giữ state suspend như một bước containment ngắn.

### 4.1. Những trường hợp suspend không đủ

- **DEK rõ bị lộ:** kẻ tấn công vẫn có thể giải mã ciphertext đã lấy; cần xem DEK rotation và re-encryption.
- **KEK rõ bị lộ:** attacker có thể unwrap các wrapped DEK đã giữ ngoài KMS; disable key object không làm họ quên KEK.
- **Private signer rõ bị lộ:** attacker có thể ký bằng bản copy ngoài HSM; chỉ disable HSM object không bảo vệ verifier.
- **HMAC/PSK lộ:** bên không được phép có thể tạo MAC hoặc giả mạo phiên theo protocol; cần secret rotation và consumer transition.
- **Sai trust mapping:** chỉ suspend một KMS key không gỡ public key giả khỏi mọi verifier cache/trust store.
- **Ciphertext bị dùng mode/nonce yếu:** key disable không cải thiện dữ liệu đã tạo; cần phân tích và migration đúng lớp.
- **Credential IAM bị lộ:** phải thu hồi credential/session/grants, không chỉ sửa bảng trạng thái key.

## 5. Quyết định phạm vi suspend theo loại khóa

| Loại khóa | Operation cần kiểm soát | Tác động tới hệ thống |
| --- | --- | --- |
| **AES-GCM DEK** | Dừng Encrypt/Decrypt theo key ID/DEK lineage tại ứng dụng/KMS theo thiết kế. | Nếu plaintext DEK cache ở app, disable KEK không chắc chặn hết việc dùng DEK. |
| **KMS KEK / wrapping key** | Chặn GenerateDataKey/Wrap, có thể Unwrap/Decrypt khi provider disable. | Wrapped DEK cũ có thể không mở được, ảnh hưởng Billing/DR. |
| **Signing private key** | Chặn Sign trên key/principal; xem trust/revocation ở verifier. | Người nhận có thể vẫn Verify chữ ký S1 offline. |
| **Public key/certificate** | Chặn trust acceptance cho purpose/issuer phù hợp. | Không cần “hủy” public key bytes; phải cập nhật consumer policy. |
| **HMAC/PSK** | Chặn dùng secret để Sign/Verify MAC, Auth hoặc phiên. | Tất cả bên cùng dùng secret phải phối hợp secret successor. |
| **TLS identity key / session secret** | Chặn xác thực mới, thu hồi credential/session theo giao thức. | Kết nối đang tồn tại có thể tiếp tục, chính sách timeout rất quan trọng. |
| **Root/CA key** | Chặn issuance/signing và trust theo phạm vi, quorum và PKI policy. | Blast radius lớn; không thể dùng runbook như DEK của một file. |
| **HSM recovery/backup shares** | Khóa quyền dùng recovery path/duyệt quorum. | Có thể ảnh hưởng khôi phục sau thảm họa và key destruction. |

### 5.1. Riêng với KEK và envelope encryption

Trong envelope encryption:

~~~text
Invoice plaintext
   |
   v
AES-GCM encrypt bằng DEK-A
   |
   +--> Ciphertext + nonce + tag + AAD
   |
   +--> DEK-A được wrap dưới KEK-3
             |
             v
          WrappedDEK-A
~~~

Khi **disable KEK-3**, một service chưa có DEK rõ trong RAM thường không thể gọi KMS để **unwrap WrappedDEK-A** nếu provider chặn Unwrap. Dữ liệu **vẫn nằm trong DB**, nhưng khả năng giải mã trực tuyến có thể mất.

Ngược lại, một service đã cache DEK-A dạng rõ có thể **vẫn decrypt được dữ liệu** cho tới khi cache bị xóa hoặc process dừng. Điều này có nghĩa:

- **Disable KEK không đồng nghĩa vô hiệu mọi bản sao DEK.**
- **Dữ liệu mã hóa không tự bị xóa** khi disable.
- **RPO/RTO và khôi phục** cần key versions/đường unwrap còn hợp lệ.
- Nếu mục tiêu là chỉ **dừng new writes** dưới KEK-3, chuyển writer sang KEK-4 và khóa `GenerateDataKey/Wrap` theo policy có thể phù hợp hơn disable toàn bộ.
- Nếu KEK-3 có khả năng compromised, việc cho phép legacy Unwrap cần được **security owner phê duyệt** với hạn và audit; không tự coi availability là lý do bật lại.

### 5.2. Riêng với chữ ký số

Private key S1 ký payment events. Nếu KMS bị disable:

- **KMS Sign(S1)** có thể bị từ chối khi key object thực sự disabled.
- **Verify(signature, public S1)** ở Ledger **không cần gọi KMS Sign**, vì phép xác minh có thể thực hiện offline.
- **Các chữ ký đã tồn tại không đổi bytes** khi S1 bị suspend.
- Nếu muốn Ledger ngừng chấp nhận chữ ký mới bằng S1, phải cập nhật **trust/acceptance/revocation policy** và xử lý caches.
- Với chữ ký lịch sử, cần phân biệt **tính đúng về toán học** với **giá trị tin cậy/nghiệp vụ theo timeline**.

Đừng báo “S1 đã được thu hồi khỏi toàn hệ thống” chỉ vì `DisableKey` ở KMS thành công.

## 6. Trạng thái khóa và chuyển trạng thái an toàn

Một tổ chức có thể xây state model nội bộ:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: Provision & approve
    ACTIVE --> SUSPEND_REQUESTED: Incident/policy approved
    SUSPEND_REQUESTED --> SUSPENDED: Provider/policy deny verified
    SUSPEND_REQUESTED --> SUSPEND_REQUESTED: Retry/reconcile
    SUSPENDED --> RESUME_REQUESTED: Evidence + independent approval
    RESUME_REQUESTED --> ACTIVE: Provider/policy allow verified
    SUSPENDED --> REVOKED: Compromise confirmed / policy
    REVOKED --> DESTROY_PENDING: Retention & dependency review
    DESTROY_PENDING --> DESTROYED: Authorized destruction
~~~

**Đây là state model nghiệp vụ minh họa.** Provider có thể có trạng thái `Enabled`, `Disabled`, `PendingDeletion` hoặc trạng thái khác; **không giả định** mapping một-một giữa model này và API thực tế.

### 6.1. Vì sao cần hai giai đoạn khi suspend?

Có hai hệ thống không dễ transaction chung:

1. **Key registry/policy store** giữ trạng thái và intent.
2. **KMS/HSM provider** thực thi key operation/key state.

Nếu gọi provider disable trước rồi registry update thất bại, registry vẫn báo Active nhưng KMS đã khóa. Nếu update registry trước rồi provider disable thất bại, các consumer phụ thuộc vào KMS vẫn có thể sử dụng khóa nếu **không đọc policy registry**.

Một phương án bền vững:

- Ghi **SUSPEND_REQUESTED** theo CAS/transaction và tạo audit/outbox event.
- Bảo đảm mọi **policy-aware callers** từ chối thao tác nguy hiểm ngay khi thấy intent.
- Gọi KMS/HSM với **canonical key reference** đã được phê duyệt.
- Đọc lại provider state và **kiểm thử negative operation** theo kế hoạch.
- Chỉ chuyển **SUSPENDED** khi kiểm chứng đúng cơ chế cần thiết.
- Khi provider call timeout, **retry/reconcile** từ trạng thái intent thay vì khẳng định đã hoàn tất.

**Không có “atomic distributed transaction” miễn phí** giữa KMS và database. Phải có **reconciliation**, idempotency và audit.

### 6.2. Các trạng thái phải fail closed

| Policy state | Thao tác Sign/Encrypt mới | Legacy Decrypt/Verify | Tác vụ vận hành |
| --- | --- | --- | --- |
| **ACTIVE** | Theo IAM/key-use policy hiện hành. | Theo policy. | Bình thường. |
| **SUSPEND_REQUESTED** | **Deny** trong mọi policy-aware caller. | Theo quy trình sự cố đã phê duyệt; không mặc định. | Disable/revoke, reconcile, audit. |
| **SUSPENDED** | **Deny** theo phạm vi được định nghĩa và xác minh. | Chỉ khi cơ chế/incident policy cho phép. | Điều tra, migrate, recovery readiness. |
| **RESUME_REQUESTED** | **Deny** cho tới khi hoàn tất toàn bộ kiểm tra. | Theo policy. | Approval, verify security state. |
| **REVOKED** | **Deny**; không tự resume. | Xem riêng trường hợp dữ liệu/chữ ký lịch sử. | Successor, migration, retirement. |
| **DESTROY_PENDING** | **Deny**; bảo toàn hồ sơ hủy. | Có thể không hoạt động tùy provider. | Retention/dependency review. |
| **DESTROYED** | Không thể dùng vật liệu theo miền provider đã hủy. | Không thể decrypt nếu không còn đường bản sao hợp lệ. | Audit evidence, residual risk. |

**Một cờ trạng thái trong database không đủ để bảo vệ đường Sign/Decrypt nếu có caller đi thẳng tới KMS**, không qua policy gate. Do đó phải cấu hình **IAM/provider enforcement, identity restrictions và các đường bypass được loại bỏ**.

## 7. Quy trình W1–W8 khi tạm đình chỉ khóa

~~~mermaid
flowchart TD
    DETECT["W1 Phát hiện bất thường"] --> TRIAGE["W2 Triage key type/actor/usage"]
    TRIAGE --> SCOPE["W3 Inventory và blast radius"]
    SCOPE --> APPROVE["W4 Chọn scope, approver và containment"]
    APPROVE --> INTENT["W5 Ghi intent, deny paths và gọi provider"]
    INTENT --> VERIFY["W6 Đọc provider state, negative tests"]
    VERIFY --> MONITOR["W7 Audit, monitor, recover/migrate"]
    MONITOR --> END{"W8 Kết luận"}
    END -->|Không compromise và có approval| RESUME["Controlled resume"]
    END -->|Compromise/policy cấm| REVOKE["Revoke/rotate/re-encrypt"]
    END -->|Chưa đủ bằng chứng| HOLD["Giữ suspend + rà soát định kỳ"]
    HOLD --> MONITOR
~~~

### W1 – Phát hiện và khởi tạo incident

Nguồn có thể gồm KMS Sign/Decrypt spikes, role/grant change, secret leakage scan, certificate mismatch, bất thường trong AEAD errors hoặc yêu cầu vận hành.

Tạo **incident ID**, ghi loại tài sản, key reference, principal, thời điểm và người chịu trách nhiệm. Không copy raw key vào ticket.

### W2 – Triage: khóa nào, nghi vấn gì?

Trả lời:

- Đó là **raw DEK, KEK, private signing key, HMAC/PSK, public trust binding hay chỉ KMS credential**?
- **Material đã thực sự rời KMS/HSM chưa?** Có KMS `Decrypt/Unwrap` thành công tới principal sai không?
- Mục đích key: Encrypt/Decrypt, Wrap/Unwrap, Sign/Verify, TLS auth hay recovery?
- Thuộc tenant, application, environment và cryptographic domain nào?
- Key usage còn theo policy hiện hành không? Có phiên/consumer offline?
- Dữ liệu/chữ ký nào đang phụ thuộc và có phải bảo vệ tính sẵn sàng đặc biệt?

**Đừng dựa vào tên alias một mình.** Alias có thể trỏ tới key object khác, đặc biệt khi rotate; inventory cần **canonical provider resource ID, material version hoặc thông tin mà provider bảo đảm**.

### W3 – Kiểm kê phụ thuộc và rủi ro

~~~text
Key S1 / KEK-3
  |
  +-- OWNER --> Security/Billing/Payment
  +-- ACTIVE_OPERATIONS --> Sign / GenerateDataKey / Unwrap
  +-- ALLOWED_PRINCIPALS --> workloads, roles, grants
  +-- WRAPS --> DEK-A, DEK-B -> ENCRYPTS --> invoices/backup
  +-- SIGNS --> payment events -> VERIFIED_BY --> Ledger/partners
  +-- REPLICA / BACKUP --> DR region, recovery slots
  +-- PREDECESSOR/SUCCESSOR --> key versions
~~~

Phải biết **blast radius** trước khi disable một key có nhiều consumer. Tuy nhiên sự cố có nguy cơ khẩn cấp có thể yêu cầu **containment trước khi inventory hoàn chỉnh**; runbook cần quy định ai có quyền quyết định ưu tiên đó.

### W4 – Chọn biện pháp ít rộng nhất nhưng đủ hiệu quả

Một số lựa chọn:

1. **Block một principal/grant** nếu nguyên nhân là credential bị cấp sai, chưa có bằng chứng key material lộ.
2. **Stop new writes/new Sign** bằng policy để chuẩn bị rotation, giữ read cũ trong giới hạn nếu phù hợp.
3. **Disable key object** nếu chính key không còn được tin hoặc cần chặn rộng toàn bộ thao tác theo provider.
4. **Isolate service/network/session** nếu các đường gọi KMS không thể được chặn tức thì bằng policy đang có.
5. **Revoke verifier trust hoặc token acceptance** nếu nguy cơ nằm ở chữ ký, certificate hoặc public-key mapping.
6. **Rotate/re-encrypt** khi raw key hoặc dữ liệu đã có thể bị lộ.

**Chọn biện pháp hẹp hơn không có nghĩa chọn biện pháp yếu hơn**. Cần căn cứ **nguy cơ còn tiếp diễn**, khả năng thực thi và tác động tới dịch vụ.

### W5 – Ghi quyết định và thi hành

Ghi ít nhất:

- Key ref/canonical resource ID, domain, key family và owner.
- Incident/approval reference; danh tính actor đã xác thực.
- Reason code, scope: những operations/principals bị chặn.
- Mốc hiệu lực và **thời hạn xem lại**; runbook liên lạc.
- Trạng thái trước/sau tại registry và provider.
- Dự kiến hậu quả về decrypt/sign/restore.
- Recovery owner, yêu cầu negative tests và audit.

**Không cấp `kms:*` cho migration/operator chỉ để thao tác nhanh.** Áp dụng **least privilege, JIT và separation of duties** nếu nền tảng hỗ trợ.

### W6 – Xác minh suspend có hiệu lực

Không chỉ nhìn UI báo **Disabled**. Cần kiểm tra phù hợp với threat model:

- **Principal sai** không thể Sign/Decrypt/Unwrap sau propagation.
- **Ứng dụng khác** không bỏ qua registry/policy gate.
- **New writes** không còn dùng key bị suspend.
- **Cached DEKs/session secrets** được xử lý theo chiến lược cụ thể.
- **Ledger/verifiers** không chấp nhận chữ ký mới từ key không còn được tin, nếu đây là mục tiêu.
- **Read/restore path** có đúng kết quả mong đợi: được chặn nếu incident yêu cầu, hoặc giữ được bằng đường riêng đã duyệt.
- **Audit events** cho thấy thao tác và outcome, không chứa secret.

Khi hệ thống dùng cache hoặc IAM eventual consistency, **“API đổi policy thành công” không có nghĩa chặn tức thì trên mọi node**. Cần đo độ trễ và thực hiện containment bổ sung nếu window rủi ro không chấp nhận được.

### W7 – Giám sát và điều tra

- Theo dõi **attempts bị từ chối**, KMS Sign/Decrypt/Unwrap mới và grant changes.
- Lập timeline với provider audit, application authorization và data access.
- Giám sát tỉ lệ lỗi của ứng dụng hợp lệ và RTO/RPO.
- Kiểm snapshots/archives/key versions và DR readiness.
- Xác định raw material/credential đã ra ngoài trust boundary chưa.
- Có thể phải **tạo successor**, rewrap DEK, re-encrypt dữ liệu, rotate signing key hoặc reset tokens.
- Cập nhật **thời hạn suspend**; không để trạng thái treo quên nhiều tháng.

### W8 – Resume, revoke hoặc tiếp tục đình chỉ

Đây là **quyết định riêng**, không tự động từ “đã qua 24 giờ”:

- **Resume:** chỉ khi có bằng chứng phù hợp rằng key vẫn được phép dùng, nguyên nhân đã sửa, policy/trust/backup được kiểm và người có thẩm quyền duyệt.
- **Revoke/rotate:** khi key material đã/được đánh giá có thể compromise hoặc risk policy không còn chấp nhận key cũ.
- **Tiếp tục suspend:** khi điều tra chưa hoàn tất, có owner, mốc xem lại và phương án đảm bảo availability.

**Không được dùng application rollback để âm thầm EnableKey rồi tái mở một key đang trong incident**.

## 8. Thiết kế quyền, thời gian và sự phê duyệt

### 8.1. Separation of duties

| Vai trò | Trách nhiệm | Không nên có mặc định |
| --- | --- | --- |
| **Security/key owner** | Quyết định lý do suspend/resume, material compromise và chuyển successor. | Chạy mọi phép Sign/Decrypt bằng khóa. |
| **Incident commander** | Ưu tiên containment so với availability và điều phối các nhóm. | Bypass audit hoặc tự xóa evidence. |
| **KMS/HSM operator** | Thực hiện disable/grant adjustments/restore theo approval. | Decrypt toàn bộ dữ liệu khách hàng không liên quan. |
| **Application owner** | Cập nhật key-use policy, cutover writers, verify impact và recovery. | Thay đổi trust root/KMS policy ngoài scope. |
| **IAM/platform team** | Revoke principal/session/grants, chống privilege escalation. | Export KEK/private signing key để điều tra. |
| **Data owner** | Xác định dữ liệu chịu ảnh hưởng, retention, nghĩa vụ và DR. | Tự quyết định thuật toán/key profile ngoài security policy. |
| **SRE/DR team** | Thực hiện canary, restore drills, monitor và phục hồi. | Tự resume khóa compromise để sửa outage. |
| **Auditor/SOC** | Bảo vệ logs, đối chiếu event/timeline, hậu kiểm. | Raw key materials hoặc HSM recovery shares. |

### 8.2. Phải tách quyền Suspend và Resume

Đặc biệt với một key nghi compromise, người được phép **suspend khẩn cấp** không nhất thiết được phép **resume**.

- **Suspend** có thể được ủy quyền nhanh trong tình huống khẩn cấp với audit ngay.
- **Resume** nên cần **điều tra, evidence và approval độc lập**, nhất là với root KEK, signer hoặc trust root.
- **Destroy** phải có approval/retention/dependency riêng; không nằm trong nút suspend.
- **Hạn cho suspension** là thời điểm cần rà soát, **không phải auto-enable**.
- **Break-glass** cần scope, actor, TTL, audit và thu hồi quyền đặc biệt sau xử lý.

### 8.3. Thời gian và cryptoperiod

Giả sử signing key S1 có originator-usage period tới T2 nhưng người vận hành suspend tại T1 vì nghi lạm dụng. Việc suspend **có thể kết thúc quyền Sign sớm hơn T2**. Sau đó:

- Nếu S1 được chứng minh còn an toàn, **resume chỉ hợp lệ trong cryptoperiod còn cho phép**, không kéo dài period cũ một cách ngầm.
- Nếu key đã expired/retired, **không bật lại new Sign chỉ vì incident được đóng**.
- Verify chữ ký cũ có thể theo policy lịch sử/timestamp, không đồng nghĩa S1 được phép Sign mới.

Tương tự với KEK, cần phân biệt **new Wrap/GenerateDataKey** và **legacy Unwrap/Decrypt**. Một số provider key disable không cho phép điều khiển riêng hai loại operation; phải chọn đúng cơ chế.

## 9. Java 17: điều phối Suspend key với state, KMS và CAS

Ví dụ dưới đây tập trung vào **điều phối trạng thái và xác minh**, không tự xây thuật toán mã hóa. Nó dùng Java 17 để mô hình hóa:

- **Approval** đến từ workflow có kiểm tra danh tính, không phải input tự khai.
- **Key registry** giữ canonical key reference, domain, purpose, revision và incident.
- **KMS adapter** chỉ thao tác trên key object được phê duyệt.
- **Compare-and-swap (CAS)** ghi intent trước, sau đó gọi provider và xác nhận state.
- **Audit outbox** ghi bền vững cùng transaction trạng thái, không log secret.
- **Idempotency:** nếu retry khi intent đang tồn tại, tiếp tục reconcile thay vì tạo transition mâu thuẫn.
- **Fail closed:** policy-aware consumers phải từ chối new sensitive operations ngay tại `SUSPEND_REQUESTED`.

**Giới hạn quan trọng:** `KeyProvider` là **interface giả định của kiến trúc**, không phải một API KMS có sẵn hoặc cùng tên trên mọi nhà cung cấp. Production phải map trạng thái và hành vi theo provider, xử lý eventual consistency, permissions, async disable, timeout, retries và audit thật.

~~~java
import java.util.Objects;

public final class KeySuspensionCoordinator {
    enum RegistryState {
        ACTIVE, SUSPEND_REQUESTED, SUSPENDED,
        RESUME_REQUESTED, REVOKED, DESTROY_PENDING, DESTROYED
    }

    enum ProviderState {
        ENABLED, DISABLED, UNAVAILABLE, OTHER
    }

    enum Result {
        SUSPENDED, ALREADY_SUSPENDED,
        CONFLICT, PROVIDER_NOT_CONFIRMED
    }

    // Metadata ở registry đáng tin, không chứa raw key bytes.
    record KeyRecord(
            String canonicalKeyRef,
            String domain,
            String purpose,
            RegistryState state,
            long revision,
            String incidentRef) {}

    // Approval phải được xác thực chữ ký/quyền/hạn ở ApprovalGate.
    record SuspensionApproval(
            String incidentRef,
            String canonicalKeyRef,
            String actorRef,
            String reasonCode,
            String approvedScope) {}

    record ProviderMetadata(
            String canonicalKeyRef,
            ProviderState state) {}

    interface ApprovalGate {
        void requireApprovedSuspension(
                SuspensionApproval approval,
                KeyRecord key);
    }

    interface KeyRegistry {
        KeyRecord load(String canonicalKeyRef);

        // Update trạng thái + revision + incidentRef + audit outbox
        // trong CÙNG transaction nếu revision/state khớp.
        boolean transitionWithAuditOutbox(
                KeyRecord observed,
                RegistryState next,
                String incidentRef,
                String reasonCode);
    }

    interface KeyProvider {
        // Phải truy vấn resource canonical, không dùng alias tùy ý.
        ProviderMetadata describe(String canonicalKeyRef)
                throws Exception;

        // Yêu cầu disable phải idempotent/reconcile được.
        // KHÔNG xóa hoặc export material.
        void disable(String canonicalKeyRef) throws Exception;
    }

    private final ApprovalGate approvals;
    private final KeyRegistry registry;
    private final KeyProvider provider;

    public KeySuspensionCoordinator(
            ApprovalGate approvals,
            KeyRegistry registry,
            KeyProvider provider) {
        this.approvals = Objects.requireNonNull(approvals);
        this.registry = Objects.requireNonNull(registry);
        this.provider = Objects.requireNonNull(provider);
    }

    private static void validate(SuspensionApproval request) {
        if (request == null
                || request.incidentRef() == null
                || request.incidentRef().isBlank()
                || request.canonicalKeyRef() == null
                || request.canonicalKeyRef().isBlank()
                || request.actorRef() == null
                || request.actorRef().isBlank()
                || request.reasonCode() == null
                || request.reasonCode().isBlank()
                || !"DISABLE_PROVIDER_KEY".equals(
                        request.approvedScope())) {
            throw new SecurityException("Invalid suspension request");
        }
    }

    private ProviderMetadata inspectMatching(String keyRef)
            throws Exception {
        ProviderMetadata metadata = provider.describe(keyRef);
        if (metadata == null
                || !keyRef.equals(metadata.canonicalKeyRef())
                || metadata.state() == null) {
            throw new SecurityException("Untrusted provider key identity");
        }
        return metadata;
    }

    public Result suspend(SuspensionApproval request)
            throws Exception {
        validate(request);

        KeyRecord original = registry.load(
                request.canonicalKeyRef());
        if (original == null
                || !request.canonicalKeyRef().equals(
                        original.canonicalKeyRef())
                || original.domain() == null
                || original.domain().isBlank()
                || original.purpose() == null
                || original.purpose().isBlank()
                || original.state() == null) {
            throw new SecurityException("Unknown or invalid key");
        }

        // Duyệt đúng key/domain/purpose/incident/actor;
        // chỉ trusted approval service mới cấp authorization.
        approvals.requireApprovedSuspension(request, original);

        if (original.state() == RegistryState.REVOKED
                || original.state() == RegistryState.DESTROY_PENDING
                || original.state() == RegistryState.DESTROYED
                || original.state() == RegistryState.RESUME_REQUESTED) {
            throw new SecurityException("Key state forbids suspension");
        }

        if (original.state() == RegistryState.SUSPENDED) {
            // Không tin mỗi registry: xác minh provider nữa.
            if (inspectMatching(original.canonicalKeyRef()).state()
                    != ProviderState.DISABLED) {
                throw new SecurityException("Key state drift");
            }
            return Result.ALREADY_SUSPENDED;
        }

        if (original.state() == RegistryState.ACTIVE) {
            // Ghi intent trước khi gọi external KMS.
            // Policy-aware callers PHẢI từ chối khi thấy intent.
            if (!registry.transitionWithAuditOutbox(
                    original,
                    RegistryState.SUSPEND_REQUESTED,
                    request.incidentRef(), request.reasonCode())) {
                return Result.CONFLICT;
            }
        } else if (original.state() == RegistryState.SUSPEND_REQUESTED) {
            if (!request.incidentRef().equals(original.incidentRef())) {
                throw new SecurityException(
                        "Different incident owns suspension intent");
            }
        } else {
            throw new SecurityException("Unsupported state");
        }

        // Đọc lại để tránh ghi đè một incident/transition khác.
        KeyRecord intent = registry.load(request.canonicalKeyRef());
        if (intent == null
                || intent.state() != RegistryState.SUSPEND_REQUESTED
                || !request.incidentRef().equals(intent.incidentRef())) {
            return Result.CONFLICT;
        }

        ProviderMetadata before = inspectMatching(
                intent.canonicalKeyRef());
        if (before.state() == ProviderState.ENABLED) {
            provider.disable(intent.canonicalKeyRef());
        } else if (before.state() != ProviderState.DISABLED) {
            return Result.PROVIDER_NOT_CONFIRMED;
        }

        ProviderMetadata after = inspectMatching(
                intent.canonicalKeyRef());
        if (after.state() != ProviderState.DISABLED) {
            // Giữ SUSPEND_REQUESTED để retry/reconcile.
            return Result.PROVIDER_NOT_CONFIRMED;
        }

        // CAS: chỉ chốt khi intent vẫn thuộc cùng revision/incident.
        boolean committed = registry.transitionWithAuditOutbox(
                intent, RegistryState.SUSPENDED,
                request.incidentRef(), "PROVIDER_DISABLED_CONFIRMED");

        return committed ? Result.SUSPENDED : Result.CONFLICT;
    }

    // RESUME là workflow RIÊNG: phải kiểm evidence, approvals,
    // cryptoperiod, material compromise, IAM và provider state.
    // Không có auto-enable hoặc auto-resume ở đây.
}
~~~

### 9.1. Vì sao mã không gọi DisableKey ngay từ đầu?

Nếu gọi KMS trước khi ghi **intent**, một process crash có thể làm KMS khóa trong khi key registry vẫn báo **ACTIVE**. Ghi intent và audit trước giúp các consumer hiểu key đang trong quá trình đình chỉ và giúp retry biết cần tiếp tục thao tác nào.

**Nhưng đây không phải bảo đảm đồng bộ tuyệt đối**: một application đi thẳng tới KMS và bỏ qua registry vẫn có thể dùng khóa cho tới khi provider disable có hiệu lực. Trong tình huống khẩn cấp, phải bổ sung **IAM/network/session containment** và negative verification.

### 9.2. Điều mã *cố ý* không làm

- Không xuất raw DEK, KEK, private signing key hay HSM material.
- Không chọn key reference từ request body chưa được xác thực; **ApprovalGate** phải kiểm authoritatively.
- Không gọi `DeleteKey`/`ScheduleDeletion`; suspend không phải destruction.
- Không hỗ trợ tùy tiện chuyển từ `REVOKED` hoặc `DESTROYED` về `ACTIVE`.
- Không tự **Enable** key sau thời hạn; resume là một workflow có approval độc lập.
- Không tuyên bố provider đã disabled nếu `describe()` không xác nhận.
- Không ghi audit raw secrets; outbox phải chứa **metadata và reason codes đã phân loại**.
- Không nhầm `SUSPEND_REQUESTED` với **đã chặn mọi đường dùng khóa**.

### 9.3. Các điều cần bổ sung trước production

1. **Provider state mapping:** nhiều HSM/KMS có key states và API khác nhau; một số không hỗ trợ toggle disable/enable.
2. **Provider confirmation:** ngay cả `describe=DISABLED` cũng có thể chưa bao quát tất cả consumer/cache; cần negative tests thực tế.
3. **IAM scopes:** key reference/actor/operation phải có kiểm soát từ cả registry và provider; audit role và escalation paths.
4. **Approval authenticity:** `SuspensionApproval` là dữ liệu có cấu trúc, **không tự mang tính tin cậy**. Gate phải kiểm quyền, chữ ký/approval record, TTL và request context.
5. **Transactional outbox:** event phải được ghi bền vững cùng revision change; event delivery/retry cần idempotency và không lộ secret.
6. **Reconciliation loop:** xử lý provider disable đã thành công nhưng CAS finalize fail, job bị restart, timeout hoặc state drift.
7. **Competing requests:** hai incident/operator có thể tranh cùng key; phải có CAS, ownership và escalation thay vì ghi đè.
8. **Read path:** cần xác minh hệ thống hiểu `SUSPEND_REQUESTED`, không có fallback sang alias/key khác.
9. **Resume protocol:** workflow riêng với evidence, inventory, cryptoperiod, provider enablement, propagation và test.
10. **Risk/availability:** KEK đang giữ DEK cho hàng triệu records có thể gây outage khi disable; cần runbook/DR.
11. **Metrics:** theo dõi suspend duration, providers status, denied operations, sessions, caches, reconciliations.
12. **Tests:** integration negative tests với principal/key resource được phê duyệt; không thử thao tác production ngoài scope.

**Không coi mã minh họa là cơ chế quản trị HSM production.** Nó chỉ thể hiện chỗ cần có trạng thái, kiểm chứng và ranh giới trách nhiệm.

## 10. Resume key: chỉ thực hiện khi còn đủ điều kiện tin cậy

Một bài học về suspend phải giải thích cả **điều kiện cho phép tiếp tục**.

### 10.1. Trường hợp có thể cân nhắc resume

- Sự cố hóa ra là **false positive** sau điều tra, không có bằng chứng raw material rò rỉ.
- KMS key bị disable phục vụ **bảo trì có phê duyệt**, không vì compromise.
- Sai policy/permission đã sửa, credential bị lộ đã revoke và operator chứng minh **key material chưa bị truy xuất trái phép** trong phạm vi điều tra.
- Dependency/DR được kiểm tra, key vẫn nằm trong **cryptoperiod/usage policy** cho phép.
- Application, verifier và clients đã hiểu key/trust version hiện tại.
- Security/key owner và approver độc lập xác nhận resume phù hợp với threat model.

**Không có đủ log không tương đương chứng minh không có sự cố**. Nếu key đã có thể bị export raw qua đường không được ghi audit, quyết định resume phải thận trọng và nêu rõ residual risk.

### 10.2. Điều kiện tối thiểu trước resume

| Nhóm kiểm | Câu hỏi bắt buộc |
| --- | --- |
| **Incident decision** | Vì sao suspend? Kết luận điều tra và residual risk là gì? |
| **Material custody** | Raw key có thể đã bị copy? KMS/HSM attestation/provenance còn tin cậy? |
| **Cryptoperiod** | Key có còn được phép new Encrypt/Sign hay chỉ read/Verify legacy? |
| **IAM/session** | Role/grant/credential sai đã revoke và không còn đường leo thang? |
| **Algorithm/profile** | Primitive/mode/nonce/key strength vẫn phù hợp policy? |
| **Dependencies** | Các consumer, data objects, backups và DR có trạng thái nhất quán? |
| **Trust acceptance** | Verifier/JWKS/PKI có biết current revoke/version state? |
| **Provider state** | Key thực sự được phép Enable lại theo provider và approval? |
| **Rollout** | Đã có canary, negative tests, audit/monitoring, rollback an toàn? |
| **Independent approval** | Ai chịu trách nhiệm quyết định bật lại, theo thời hạn nào? |

### 10.3. Quy trình resume có kiểm soát

1. Lập **resume proposal** gắn với incident, root cause và bằng chứng.
2. Kiểm key **không thuộc trạng thái REVOKED/DESTROY_PENDING/DESTROYED** và key usage còn hiệu lực.
3. Kiểm owner, approval độc lập và phạm vi consumer.
4. Ghi `RESUME_REQUESTED`, giữ **deny new operations**.
5. Nếu có provider disable, thực hiện **enable** theo API/phê duyệt.
6. Xác nhận provider key state; triển khai policy/consumer readiness.
7. Chạy positive + negative tests được phép: đúng principal hoạt động, sai principal vẫn bị chặn.
8. CAS chuyển `ACTIVE` khi hoàn tất; ghi audit/outbox và monitor sát trong giai đoạn đầu.

Nếu bất kỳ bước nào cho thấy **material compromise có thể xảy ra**, ưu tiên **rotate/revoke** thay vì cưỡng ép resume.

## 11. Suspension không tự giải quyết compromise

### 11.1. DEK bị lộ

Nếu raw DEK-A đã ra khỏi ranh giới tin cậy:

~~~text
Ciphertext-A = AES-GCM-Encrypt(DEK-A, invoice, nonce, AAD)
DEK-A đã lộ --> attacker có ciphertext có thể giải mã.

Disable KEK hoặc suspend app --> không xóa DEK-A khỏi attacker.
Re-wrap DEK-A dưới KEK-B --> vẫn là DEK-A.

Khôi phục bảo vệ cho dữ liệu cần giữ bí mật:
  DEK-B = GenerateFreshKey()
  Ciphertext-B = AES-GCM-Encrypt(DEK-B, invoice, nonce mới, AAD phù hợp)
  WrappedDEK-B = Wrap(KEK được duyệt, DEK-B)
~~~

Cần đánh giá **DEK scope, ciphertext đã bị truy cập, backups và lịch sử plaintext**. Re-encrypt dữ liệu hiện hành có thể bảo vệ về sau nhưng **không lấy lại thông tin attacker đã đọc**.

### 11.2. KEK bị lộ

Raw KEK có thể mở nhiều wrapped DEKs. Suspend key object tại KMS không xóa raw KEK bên ngoài. Phản ứng có thể cần:

- Tạo **KEK successor** và chuyển new wraps.
- Re-wrap **DEKs được đánh giá còn an toàn**, qua KMS/HSM được duyệt.
- Với DEK có khả năng đã bị lộ qua raw KEK và wrapped blobs bị tiếp cận, đánh giá **DEK rotation/re-encryption**, không chỉ re-wrap.
- Đối soát old KEK dependencies, archive, snapshots và DR.
- Chặn/thu hồi quyền bất thường, giữ bằng chứng.
- Không hủy KEK cũ khi vẫn cần recovery mà chưa có phương án thay thế.

### 11.3. Private signing key bị lộ

Nếu private key S1 đã bị sao chép, kẻ tấn công có thể tiếp tục **Sign ngoài KMS**. Dù KMS disable S1, những chữ ký bằng bản copy có thể vẫn Verify hợp lệ toán học.

Phải:

1. Ngăn Sign mới qua hệ hợp lệ và cô lập đường rò.
2. Tạo S2 trong KMS/HSM và chuyển signer.
3. Phân phối **public key S2** tới verifiers qua trust path được xác thực.
4. Cập nhật **current key acceptance, issuer, audience, key usage, revocation**.
5. Xác minh event/artifact trong giai đoạn nghi ngờ compromise; chống replay/idempotency.
6. Không tự resume S1 chỉ vì attacker không còn hiện diện trong KMS logs.

### 11.4. KMS credential bị lộ nhưng key non-exportable

Cần thu hồi **credential/role/grants/session** và điều tra **Sign/Decrypt/Unwrap đã xảy ra**, nhưng không mặc định raw KEK hay private signing key đã bị export. Mức ảnh hưởng phụ thuộc **quyền API**:

- `Sign` có thể đủ tạo chữ ký giả dù raw key không rời HSM.
- `DecryptDataKey` có thể trả plaintext DEK cho workload sai.
- `CreateGrant/ChangeKeyPolicy` có thể duy trì quyền lạm dụng.
- `ScheduleKeyDeletion` có thể gây availability incident.

Ngược lại, nếu raw key đã bị copy từ trước, **revoke IAM là chưa đủ**. Cần báo cáo đúng loại exposure.

## 12. Caching, session, key replication và điểm mù

### 12.1. DEK cache ở ứng dụng

KMS chỉ kiểm quyền **khi API được gọi**. Sau khi app nhận plaintext DEK, nó có thể cache key theo TTL hoặc count. Suspend KEK có thể **không ảnh hưởng tới DEK-A trong cache**.

Biện pháp tùy threat model:

- **Invalidate DEK cache** khi key family bị suspend hoặc compromise, thông qua cơ chế được triển khai/test.
- Hạn chế **TTL, usage limits, memory retention** và quyền debug/dump.
- Theo dõi service instances chưa nhận sự kiện suspend.
- Không log DEK hoặc wrapped DEK nguyên khối vào APM/trace.
- Nếu chính DEK đã lộ, phải đánh giá **DEK rotation**, không tin cache clear là đủ.

### 12.2. Offline Verify và verifier cache

Một public key/certificate có thể đã được cache ở nhiều nơi. Khi private signer bị suspend:

- Một verifier có thể vẫn chấp nhận chữ ký S1 vì chưa tải policy mới.
- JWT/key lookup có thể dùng JWKS cache nhiều giờ.
- Một số artifacts được Verify offline không thấy KMS state.
- Trust revocation phải có **distribution, TTL, monotonic version và failure handling**.

**Không đồng nhất “KMS Sign bị chặn” với “chữ ký mới bằng bản copy S1 bị từ chối”.**

### 12.3. Key replica và HSM clustering

- Một key object có thể được replicated tới nhiều vùng/HSM nodes theo contract nhà cung cấp.
- Disable ở primary có thể có **propagation semantics** riêng cho replicas.
- Key inventory cần biết **replication group, account, region, material origin và backup**.
- Không giả định gọi Disable một key ID bất kỳ là đã thay trạng thái toàn bộ key family.
- DR keys có thể được bảo vệ trong miền production recovery được phê duyệt, nhưng không được trở thành kênh bypass suspend.

### 12.4. Kết nối/sessions đang chạy

Revoke TLS identity key hoặc IAM credential không tự chấm dứt mọi phiên đang tồn tại nếu protocol/session management cho phép. Có thể cần:

- Chấm dứt connection/session hoặc điều chỉnh session TTL.
- Vô hiệu hóa resumption tickets/token nơi triển khai hỗ trợ.
- Xác minh role/policy propagation.
- Từ chối refresh sessions từ credential bị revoke.
- Kiểm tra các node sau sự kiện key state change.

**Một chính sách suspend phải định nghĩa hiệu lực theo thời gian**, không chỉ boolean trong database.

## 13. Backup/DR: cân bằng containment và khả năng khôi phục

Một key nằm ở ranh giới giữa security và availability. Nếu KEK cũ bị disable, hệ thống có thể không đọc được snapshots cũ; nếu bật lại quá sớm, sự cố có thể tiếp diễn.

### 13.1. Những thứ phải đối soát

| Nguồn | Câu hỏi |
| --- | --- |
| **Primary DB** | Ciphertexts nào đang dùng wrapped DEK dưới key bị suspend? |
| **Backups/snapshots** | Bản sao lịch sử cần key version nào để restore? |
| **Cold archive/object storage** | Có dữ liệu ngoài đường migration online không? |
| **Key inventory** | WRAPS/ENCRYPTS/SIGNS dependencies, predecessor/successor có đầy đủ? |
| **KMS/HSM backup** | Provider có phục hồi key material khi disable/restore không? |
| **DR region/account** | Có đường decrypt/verify hợp lệ, theo approval và current incident state? |
| **Caches/queues** | Có DEK/plaintext key hoặc công việc new Sign/Encrypt đang chờ? |
| **PKI/JWKS registry** | Snapshot cũ có key trust đã bị revoke không? |

### 13.2. RPO/RTO có thể thay đổi khi suspend

- **RPO:** lượng trạng thái dữ liệu được phép mất sau sự cố.
- **RTO:** thời gian mục tiêu phục hồi dịch vụ.

Khi suspend KEK, có thể **không đáp ứng RTO** nếu chưa có successor hoặc đường legacy read được phép. Đội Incident/SRE/Security phải quyết định **chấp nhận gián đoạn, giới hạn Decrypt, chuyển traffic hoặc làm migration** theo rủi ro.

**Không dùng “DR emergency” để tự bật lại key compromised**. Break-glass phải có review, scope, audit và kế hoạch khóa lại.

### 13.3. Restore snapshot có thể hồi sinh rủi ro

Một snapshot cũ có thể chứa:

- Key registry state `ACTIVE` trước khi suspend.
- IAM grants hoặc trust metadata đã bị revoke.
- Application config trỏ tới key cũ.
- Wrapped DEK đang phụ thuộc vào KEK bị đình chỉ.

Sau restore, cần **reconcile với incident state và current revocation policy**, không phục hồi nguyên xi quyền và key acceptance của snapshot.

### 13.4. Suspend khác crypto-shredding

Suspend **giữ key material** để có khả năng xử lý tiếp. Crypto-shredding là một mục tiêu khác: làm dữ liệu **không còn đường giải mã** trong phạm vi được xác định thông qua loại bỏ key material tương ứng.

**Không được tuyên bố dữ liệu đã crypto-shred chỉ vì key object Disabled**. Ngược lại, nếu key thực sự bị destroy khi không còn backup, dữ liệu có thể mất khả năng phục hồi vĩnh viễn.

## 14. Audit, alert và bằng chứng

### 14.1. Mẫu audit sự kiện suspend

~~~json
{
  "eventType": "KEY_SUSPENSION_CONFIRMED",
  "incidentRef": "INC-2026-KEY-073",
  "keyRef": "kms-prod-payment-signing-s1",
  "cryptographicDomain": "production",
  "keyPurpose": "SIGN_PAYMENT_EVENT",
  "actorRef": "approved-security-operator",
  "reasonCode": "SUSPECTED_UNAUTHORIZED_SIGN",
  "scope": "DISABLE_PROVIDER_KEY",
  "registryState": "SUSPENDED",
  "providerState": "DISABLED",
  "policyVersion": "key-incident-policy-v5",
  "outcome": "CONFIRMED",
  "correlationId": "opaque-request-ref"
}
~~~

**Đây chỉ là event minh họa.** Không log **raw DEK/KEK/private key, seed, credential, recovery shares, wrapped key blob lớn, plaintext dữ liệu hoặc toàn bộ KMS SDK response**. Key IDs/tenantRefs có thể là metadata nhạy cảm; áp phân quyền với audit.

### 14.2. Những sự kiện cần ghi khác

- `SUSPEND_REQUESTED`, `SUSPEND_PROVIDER_CALL`, `SUSPEND_CONFIRMED` hoặc `SUSPEND_RECONCILIATION_REQUIRED`.
- IAM grant/session/token đã revoke, và negative check có hiệu lực.
- New Sign/Encrypt attempts bị deny, retries và source principal.
- Provider key state drift, replica inconsistency.
- Legacy Decrypt/Verify exceptions được cấp có hạn.
- Policy/registry version và authorizer/approver.
- Successor creation, cutover, rewrap/re-encrypt và trust publication.
- Resume proposal, evidence review, approval, provider enable và post-enable tests.
- Backup restore test, key dependency backlog, retention và destruction quyết định sau đó.

### 14.3. Đối chiếu KMS và application audit

KMS có thể biết **workload gọi Decrypt trên KEK nào**, nhưng không biết **người dùng cuối có quyền xem invoice hay không**. Để điều tra:

~~~text
API request / authenticated user / tenant
       |
       v
Application authorization decision
       |
       v
KMS request ID + workload principal + key ref + operation
       |
       v
Encrypted object ID / key version / incident timeline
~~~

**Cần correlation ID và audit metadata đã phân loại** ở hai phía. Không dùng raw key bytes để nối log.

### 14.4. Metrics hữu ích

- Thời gian từ `DETECTED` tới `SUSPEND_REQUESTED` rồi `CONFIRMED`.
- Số provider operations bị chặn sau thời điểm suspend.
- Số node/cache/sessions chưa cập nhật key-use policy.
- KMS `AccessDenied`, Sign/Decrypt/Unwrap bất thường.
- Số wrapped DEKs hoặc ciphertexts phụ thuộc KEK suspended.
- Tỷ lệ new writes đã chuyển sang key successor.
- Số verifier còn tin signer cũ ngoài policy.
- Số incident quá thời hạn review, không có owner.
- DR restore failures do key disable.
- Số trường hợp **state drift** giữa registry và provider.

**Không chỉ đo số nút “Suspend” đã được bấm.** Kết quả cần đo **hiệu lực bảo mật và ảnh hưởng hệ thống**.

## 15. Kiểm thử: chứng minh suspend có hiệu lực

| Kịch bản | Kết quả kỳ vọng |
| --- | --- |
| Key đang Active, approval hợp lệ | Ghi intent và audit, provider disable, xác nhận state mới. |
| Approval thiếu hoặc sai actor | **Deny**, không gọi provider. |
| Request key ref khác canonical registry/provider | **Deny**, không đổi state. |
| Hai operators suspend cùng key | CAS ngăn ghi đè; retry idempotent. |
| Gọi provider disable thành công, DB finalize fail | Giữ intent/reconcile, không báo thành công giả. |
| KMS timeout sau disable | Retry kiểm provider state, không delete key. |
| Provider đang PendingDeletion hoặc không hỗ trợ disable | Báo không phù hợp, không giả vờ Suspended. |
| Principal sai gọi Sign sau suspend | **Bị từ chối** theo cơ chế được triển khai. |
| Principal sai gọi Decrypt/Unwrap sau suspend | Bị từ chối nếu scope yêu cầu; audit đúng. |
| App còn DEK cache | Kiểm invalidate/cache TTL; không giả định KMS disable chặn hết. |
| Ledger Verify chữ ký S1 offline | Vẫn có thể Verify toán học; trust policy quyết định acceptance. |
| JWT/JWKS cache còn public key cũ | Có cập nhật revocation/TTL/monotonic version theo policy. |
| KEK disabled trong khi DB còn wrapped DEKs | Có cảnh báo availability/DR và read policy rõ. |
| KMS provider disable chưa propagate | Chưa tuyên bố chặn toàn hệ thống; containment bổ sung. |
| Incident chứng minh raw signing key bị lộ | **Không resume**, chuyển rotate/revoke + trust update. |
| False positive với bằng chứng đáng tin | Resume theo workflow approval riêng và kiểm cryptoperiod. |
| Key đã retired/expired | Không bật new Sign/Encrypt chỉ vì đóng incident. |
| DR restore snapshot trước suspend | Không hồi sinh policy/trust/key state cũ. |
| Log/trace/audit được quét | Không chứa raw key, credentials hoặc plaintext. |
| Legacy read exception hết hạn | Từ chối, không giữ bypass vĩnh viễn. |

### 15.1. Unit test chưa đủ

Một unit test có thể chứng minh coordinator gọi `provider.disable()` và chuyển `SUSPENDED` trong mock. Nhưng không chứng minh **IAM principal thực tế bị chặn**, session/caches đã invalidated hoặc PKI verifiers ngừng tin khóa đó.

Với production, cần **integration/negative tests được phê duyệt** trên key tài nguyên an toàn, đúng môi trường và scope. **Không thử disable hoặc Sign/Decrypt production ngoài quyền và kế hoạch đã phê duyệt**.

### 15.2. Read-only legacy không tự động an toàn

Nếu suspending KEK vì **một actor bị lạm dụng**, để các actor khác decrypt theo policy có thể được chấp thuận. Nếu chính **KEK đã compromise**, giữ legacy Unwrap không mặc định an toàn. Tất cả exception phải gắn **incident, actor, purpose, TTL và audit**.

## 16. Tình huống thực tế: Billing, Payment và Ledger

Giả sử một nền tảng có:

- **Billing Service:** mã hóa hóa đơn bằng AES-256-GCM; DEK do KMS sinh và bọc bằng KEK-Billing.
- **Payment Service:** ký payment events bằng private Ed25519 key S1 nằm trong KMS/HSM.
- **Ledger Service:** Verify các payment events bằng public key S1/S2 đã được xác thực trong trust registry; kiểm quyền và chống replay.

### 16.1. Tình huống A – Nghi sai IAM trên Billing KEK

SOC phát hiện principal thử nghiệm có `DecryptDataKey` trên Billing production KEK. Chưa có bằng chứng raw KEK bị lộ.

**Containment phù hợp:**

1. Chặn grants/session của principal thử nghiệm; sửa policy/assume-role path.
2. Tạm đình chỉ quyền Unwrap ngoài workload được phép hoặc disable KEK nếu rủi ro yêu cầu.
3. Đối chiếu provider audit để xác định đã có lượt `DecryptDataKey` thành công nào.
4. Kiểm plaintext DEK có được trả về non-prod/log/cache không.
5. Đánh giá tỷ lệ Billing operations cần KEK; triển khai key successor/DR nếu cần.
6. Test principal test không thể gọi KMS production và data authorization vẫn chặn tenant sai.
7. Quyết định resume hay rotate theo bằng chứng; không coi revoke IAM là đã “xóa” mọi DEK từng trả ra.

**Điểm cần nhớ:** Nếu chỉ disable KEK, Billing có thể không đọc được hóa đơn cũ, trong khi DEK đã cache vẫn có thể được dùng. Biện pháp cần kết hợp **provider policy, app cache, audit và availability**.

### 16.2. Tình huống B – Payment Sign bất thường

Một workload cũ bất ngờ gọi `Sign(S1)`. Không rõ private key S1 có bị lộ ngoài HSM hay không.

**Runbook:**

1. Suspend Sign S1 hoặc chặn principal lạ theo severity.
2. Giữ audit KMS request IDs và signed event IDs đã được phân loại.
3. Kiểm tra S1 **non-exportable** và những đường import/backup có liên quan.
4. Chuẩn bị S2 signer; Ledger nhận public key S2 qua trusted registry.
5. Điều tra các chữ ký S1 đã được chấp nhận, kiểm issuer/tenant/authorization và replay.
6. Nếu chứng minh chỉ là job cũ không phép nhưng key material không bị compromise, cân nhắc resume có approval; nếu có nguy cơ lộ, **revoke/rotate và chặn acceptance**.

**Điểm cần nhớ:** Disable private key chỉ chặn Sign ở một ranh giới KMS; **Verifier vẫn có thể chấp nhận chữ ký S1** nếu trust policy chưa đổi.

### 16.3. Tình huống C – KEK sai usage khi rotate

Billing chuẩn bị chuyển KEK v3 → v4. Một pipeline tiếp tục tạo wrapped DEK mới dưới v3 dù v3 đã hết originator-usage period.

**Cách xử lý:**

1. Chặn `GenerateDataKey/Wrap` mới dưới v3 bằng **policy enforce được**, chuyển writer sang v4.
2. Duy trì legacy `Unwrap` dưới v3 theo policy nếu vẫn cần đọc dữ liệu cũ và key không compromise.
3. Re-wrap DEKs sang v4 theo provider API hỗ trợ, dùng CAS khi cập nhật blob/key version.
4. Đối soát archives/snapshots/DR trước khi disable toàn bộ v3.
5. Không hủy v3 khi còn wrapped DEKs cần phục hồi.
6. Kiểm metrics không còn new wraps dưới v3.

**Điểm cần nhớ:** Trường hợp này có thể phù hợp **retire originator usage**, không nhất thiết **DisableKey toàn bộ**.

### 16.4. Tình huống D – Raw DEK bị lộ qua log

Một bản log debug chứa plaintext DEK-A. Suspend KEK liên quan có thể giúp containment ở một số đường dùng, nhưng **không giải quyết sự cố material exposure**.

Cần truy vết records được mã hóa bằng DEK-A, hạn chế truy cập ciphertext/log, sinh DEK mới, đánh giá **re-encrypt dữ liệu**, scan logs/archives theo retention và ghi nhận residual risk của dữ liệu lịch sử.

**Điểm cần nhớ:** **Đừng dùng state Suspended để đóng incident** khi bí mật đã được phân phối sai.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Coi Suspend = Destroy | Dễ đưa ra quyết định mất dữ liệu không cần thiết hoặc báo sai bảo mật. | Phân biệt key usage state và material destruction. |
| Coi Suspend = Revoke vĩnh viễn | Không có workflow review/resume hoặc không biết lúc nào cần rotate. | Có lifecycle transition, incident policy và owner. |
| Chỉ đổi `status=SUSPENDED` trong DB | Caller đi thẳng tới KMS vẫn dùng key. | Provider/IAM policy enforcement, negative tests. |
| Disable KEK để chỉ ngừng new writes | Decrypt old data có thể ngừng toàn bộ. | Per-operation policy/cutover nếu supported. |
| Disable KEK rồi coi DEK cache vô hiệu | App vẫn giữ raw DEK trong RAM. | Cache invalidation/TTL, app controls. |
| Disable signing key rồi coi Ledger không Verify | Offline public-key verification vẫn thực hiện. | Trust/acceptance/revocation rollout. |
| Auto-enable theo timeout mà không review | Khóa compromised được dùng lại. | TTL chỉ để review; resume approval độc lập. |
| Resume sau khi raw key đã lộ | Attacker vẫn có key material cũ. | Rotate/revoke và đánh giá dữ liệu/chữ ký lịch sử. |
| Hủy KEK khi archive vẫn cần Unwrap | Backup không thể phục hồi. | Dependency scan và DR drill. |
| Chỉ revoke một IAM grant | Principal có thể có role khác hoặc session còn hiệu lực. | Rà toàn bộ access paths và propagation. |
| Coi KMS disable tức thì ở mọi replica | Một số vùng/nodes/cache còn dùng key. | Provider semantics và reconciliation/negative tests. |
| Dùng alias thay canonical key ID | Suspend nhầm key hoặc bỏ sót material version. | Authoritative registry và provider identity matching. |
| Để caller chọn key ID cần suspend | Dẫn đến denial of service/privilege abuse. | ApprovalGate, authorization, scope whitelist. |
| Một người vừa đề xuất vừa tự resume root key | Mất separation of duties. | Dual control/quorum cho key nhạy cảm. |
| Tin KMS `DescribeKey=Disabled` là toàn hệ an toàn | Không xét app caches, offline Verify, raw copies. | End-to-end validation và exposure analysis. |
| Không có intent/CAS giữa registry và provider | State drift, retry gây hành vi sai. | State machine, transactional outbox, reconciliation. |
| Không ghi incident ID/approval | Không truy ra lý do hoặc ai chịu trách nhiệm. | Typed audit metadata, immutable retention. |
| Log raw DEK/KEK để debug Suspend | Tạo thêm một đường lộ key. | No-secret logging, metadata allowlist. |
| Bật lại key sau DB restore | Hồi sinh quyền/trust đã revoked. | Reconcile với current incident/security state. |
| Coi certificateHold là API chung | Client/CA có thể không hỗ trợ resume/revocation như tưởng. | Kiểm provider/PKI profile và acceptance semantics. |
| Coi legacy-read luôn an toàn | Có thể tiếp tục cho attacker dùng key compromised. | Scope/TTL/approval theo loại incident. |
| Dùng `kms:*` cho break-glass | Mở đường Decrypt/Export/Delete quá rộng. | JIT least privilege, quorum và audit. |
| Đóng incident khi API disable trả success | Chưa biết mọi consumer và phiên đã bị chặn. | Negative tests, caches, audit, dependency metrics. |
| Nhầm key expired với key có thể resume | Vi phạm cryptoperiod và key usage policy. | Kiểm state/cryptoperiod trước mọi resume. |

## 18. Checklist khi Suspend key

1. **Định danh:** key ID/version/canonical resource, owner, domain, purpose được xác minh chưa?
2. **Lý do:** incident, policy exception hoặc bảo trì nào yêu cầu suspend?
3. **Exposure:** raw secret đã/được đánh giá có thể lộ, hay chỉ sai credential/grant?
4. **Operation:** cần chặn Sign, Encrypt, Wrap, Decrypt, Unwrap, Verify hay tất cả?
5. **Principal:** ai đang có quyền và những role/grant/session nào phải revoke?
6. **Mode thực thi:** suspend ở app/policy, IAM hay key object? Có đường bypass không?
7. **Provider semantics:** API disable có chặn operation nào, có thể enable lại không?
8. **Dependencies:** DEKs, ciphertext, signers, consumers, backups, replica, DR đã được inventory chưa?
9. **Availability:** tác động tới online decrypt, Sign, latency, RPO/RTO được đánh giá chưa?
10. **Approval:** actor/approver độc lập và scope/incident được xác thực chưa?
11. **Intent:** có CAS/status `SUSPEND_REQUESTED` và audit trước provider call chưa?
12. **Fail closed:** các caller có deny new operations khi intent xuất hiện không?
13. **Provider verification:** đã xác minh canonical identity và state thực tế chưa?
14. **Negative tests:** principal/key/tenant sai còn gọi được crypto operation không?
15. **Cache/session:** cached DEKs, JWT/JWKS, sessions và HSM replicas được xử lý chưa?
16. **Audit:** event, actor, reason, policy version và correlation ID được ghi mà không lộ secret chưa?
17. **Monitoring:** có alert key use tiếp diễn và state drift sau suspend không?
18. **Investigation:** đã đối chiếu KMS Sign/Decrypt/Unwrap với application authorization chưa?
19. **Successor:** có cần key mới, re-wrap/re-encrypt/re-sign hoặc trust update không?
20. **Cryptoperiod:** key có còn nằm trong period cho new-use nếu dự kiến resume không?
21. **Resume criteria:** có đủ evidence, owner, độc lập approval và kiểm thử sau enable không?
22. **Revocation:** nếu compromise xác nhận, đã chuyển từ suspend sang rotate/revoke chưa?
23. **Backups/DR:** snapshot sau restore có hồi sinh policy/key state cũ không?
24. **No destructive shortcut:** có tránh hủy key khi chưa kiểm retention/dependencies không?
25. **Review date:** ai xem lại incident nếu vẫn suspended và vào lúc nào?
26. **Residual risk:** những plaintext/chữ ký đã có thể bị attacker lấy trước containment được ghi nhận chưa?

## 19. Câu hỏi tự kiểm tra

1. **Suspend key** là trạng thái nghiệp vụ hay một API duy nhất tồn tại trên mọi KMS?
2. Vì sao suspend có thể là bước containment tốt nhưng không bảo đảm một secret đã lộ trở lại bí mật?
3. **Disable key object** khác **revoke IAM grant** ở điểm nào?
4. Nếu chỉ muốn cấm Encrypt mới nhưng cần Decrypt cũ, vì sao disable toàn bộ KEK có thể không phù hợp?
5. Nếu app đã cache DEK rõ, lệnh disable KEK có chắc chặn mọi Decrypt không?
6. Vì sao offline Verify bằng public S1 vẫn có thể chạy khi private S1 bị disable trong HSM?
7. Khi nào nên chọn suspend, và khi nào cần rotate/revoke ngay?
8. Điều gì xảy ra nếu hủy KEK trước khi biết backup nào vẫn cần nó?
9. Tại sao cần **canonical resource ID** thay vì alias khi đình chỉ key?
10. Vì sao phải có `SUSPEND_REQUESTED` thay vì chỉ ACTIVE và SUSPENDED?
11. Khi provider disable thành công nhưng registry CAS thất bại, runbook cần làm gì?
12. Một lời gọi provider báo `Disabled` đủ để tuyên bố tất cả sessions/replicas đã bị chặn chưa?
13. Người có quyền suspend khẩn cấp có nên được tự resume một key nghi compromise không?
14. Những bằng chứng nào cần có trước khi resume?
15. Suspend có làm thay đổi cryptoperiod hoặc kéo dài validity của key không?
16. Nếu raw DEK bị lộ, re-wrap DEK dưới KEK mới có chữa được không?
17. Nếu raw KEK bị lộ, vì sao phải đánh giá cả các wrapped DEKs cũ?
18. Nếu private signer bị lộ, cần sửa cả signer và verifier như thế nào?
19. Nếu chỉ KMS credential bị lộ, tại sao phải điều tra Sign/Decrypt/Unwrap history?
20. KMS/HSM non-exportable key có thể bị lạm dụng mà không cần export như thế nào?
21. Vì sao cần đối chiếu application audit và provider audit?
22. Những dữ liệu nào audit được phép chứa, và những secrets nào tuyệt đối không nên ghi?
23. Một DR snapshot có thể hồi sinh rủi ro đã bị suspend như thế nào?
24. Vì sao mỗi sự kiện suspend phải có owner, review deadline và residual-risk assessment?
25. Negative test nào cho thấy suspension thật sự hiệu lực ở **điểm dùng khóa**?
26. Điểm khác biệt giữa **suspend key**, **retire key** và **crypto-shredding** là gì?

**Ghi nhớ:** **Suspend key** là **biện pháp tạm đình chỉ quyền sử dụng hoặc trạng thái key object nhằm cô lập rủi ro**, không phải phương pháp khôi phục bí mật đã lộ. Muốn triển khai an toàn cần biết **key type, operation, canonical key identity, IAM/provider semantics, cryptoperiod, cache, public verifier trust, data/backup dependencies**, cùng **approval, state machine, CAS, reconciliation, audit và negative tests**. **Resume** chỉ phù hợp khi key **vẫn còn đáng tin và được phê duyệt sử dụng**; nếu material compromise hoặc policy không còn chấp nhận, phải chuyển sang **revoke/rotate/re-encrypt/trust update** theo đúng loại khóa. Chỉ khi đánh giá được cả **hiệu lực containment, khả năng phục hồi và rủi ro lịch sử**, trạng thái suspend mới có giá trị bảo mật thực tế.
