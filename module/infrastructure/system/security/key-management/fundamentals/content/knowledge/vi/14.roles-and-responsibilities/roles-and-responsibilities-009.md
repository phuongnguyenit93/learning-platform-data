# Separation of duties (Phân tách nhiệm vụ trong quản lý khóa mật mã)

## 1. Separation of duties là gì?

**Separation of duties (SoD – phân tách nhiệm vụ)** là nguyên tắc tổ chức trách nhiệm và quyền hạn sao cho **một cá nhân, tài khoản hoặc thành phần hệ thống không thể tự mình hoàn thành toàn bộ chuỗi hành động nhạy cảm** mà không có cơ chế kiểm soát độc lập.

Trong **quản lý khóa mật mã**, SoD ngăn những tình huống như:

- Một người **tạo khóa, tự phê duyệt, xuất plaintext key, sửa key policy rồi xóa nhật ký**.
- Một quản trị viên **tự cấp quyền KMS Decrypt**, dùng quyền đó đọc dữ liệu và xóa bằng chứng.
- Một dịch vụ vừa **ký chứng từ**, vừa **phê duyệt nội dung cần ký**, không có một nguồn xác thực nghiệp vụ độc lập.
- Một operator có thể **hủy KEK** mà không cần chủ dữ liệu xác nhận các encrypted DEK và backup đã được di chuyển.

SoD là **kiểm soát về con người, quy trình và công nghệ**, không phải thuật toán mật mã. Một hệ thống dùng AES-256, RSA, ECDSA và HSM vẫn có thể yếu nếu mọi quyền tập trung vào một chủ thể.

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chủ đề này bao phủ vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy khóa**, đồng thời kết nối **KMS/HSM, DEK/KEK, envelope encryption, chữ ký số, IAM và kiểm toán**.

**Mục tiêu:** người có khả năng **yêu cầu** hành động không mặc nhiên được **phê duyệt**, người được **thực thi** không được tự **xác nhận mình đã làm đúng**, và người có quyền **dùng key** không được tự **thay chính sách kiểm soát key**.

~~~mermaid
flowchart LR
    Q["Người yêu cầu thay đổi"] --> A["Người phê duyệt độc lập"]
    A --> O["Operator / workflow thực thi"]
    O --> K["KMS/HSM thực hiện thao tác"]
    K --> V["Verifier / control độc lập"]
    V --> L["Audit có bảo vệ"]
    L --> R["Định kỳ tái chứng thực quyền"]
~~~

Sơ đồ thể hiện **các vai trò kiểm soát logic**; không bắt buộc mỗi vai trò là một nhân viên riêng trong mọi doanh nghiệp. Điều bắt buộc là **các xung đột nhiệm vụ được xác định, quyền không tập trung ngoài mức chấp nhận rủi ro, và có kiểm soát bù trừ khi không thể tách hoàn toàn**.

## 2. Vì sao SoD quan trọng với khóa mật mã?

Khóa mật mã là **điểm tập trung quyền lực**: ai có hoặc có thể dùng khóa thường có khả năng giải mã, tạo MAC, ký hoặc truy cập dữ liệu phụ thuộc.

| Tài sản | Quyền rủi ro nếu tập trung | Kết quả có thể xảy ra |
|---|---|---|
| **AES DEK** | Generate + read plaintext key + Decrypt dữ liệu + sửa audit | Lộ dữ liệu nhạy cảm và khó truy vết |
| **KMS KEK** | ChangeKeyPolicy + Unwrap + ScheduleDeletion | Giải bọc nhiều DEK hoặc làm mất khả năng khôi phục |
| **Private signing key** | Phê duyệt chứng từ + Sign + sửa lịch sử nghiệp vụ | Chữ ký mật mã hợp lệ trên nội dung không được phép |
| **CA private key** | Cấp phát danh tính + Sign certificate + thêm trust root | Phát hành chứng chỉ giả được nhiều hệ thống tin |
| **HMAC/PSK secret** | Phân phối secret + cấp quyền hệ thống xác minh + ghi log | Mạo danh một bên chia sẻ secret |
| **Recovery key** | Lưu giữ + truy xuất + sử dụng + xóa bản sao | Mở dữ liệu diện rộng không cần kiểm tra thứ hai |
| **IAM/KMS admin role** | Cấp quyền + tự dùng quyền + xóa audit | Vượt qua toàn bộ ranh giới kiểm soát |

### 2.1. Mô hình đe dọa

SoD nhằm giảm rủi ro từ:

1. **Insider cố ý lạm dụng**: người có quyền hợp lệ sử dụng sai mục đích.
2. **Credential compromise**: một principal bị chiếm quyền không đủ để thao túng toàn bộ quy trình.
3. **Human error**: quyết định xóa/rotate/thu hồi có người hoặc kiểm soát độc lập phát hiện sai.
4. **Workflow abuse**: thao tác bảo mật đúng về kỹ thuật nhưng không có phê duyệt nghiệp vụ.
5. **Audit tampering**: người gây sự cố không thể dễ dàng xóa dấu vết trong hệ thống do mình quản lý.

**Giới hạn:** SoD không loại bỏ nguy cơ **thông đồng** giữa nhiều người, lỗi logic trong hệ thống phê duyệt hoặc việc một kẻ tấn công chiếm đồng thời nhiều tài khoản. Vì vậy cần thêm MFA, IAM, HSM, bảo vệ nhật ký, giám sát và diễn tập.

## 3. SoD khác least privilege, dual control và split knowledge

Các thuật ngữ liên quan nhưng **không thay thế nhau**.

| Khái niệm | Câu hỏi giải quyết | Ví dụ |
|---|---|---|
| **Separation of duties** | Những nhiệm vụ nào **không được do cùng chủ thể kiểm soát trọn vẹn**? | Người sửa key policy không tự duyệt thay đổi |
| **Least privilege** | Mỗi chủ thể chỉ cần **quyền tối thiểu nào**? | Service chỉ được Encrypt, không được DeleteKey |
| **Dual control / four-eyes** | Thao tác nhạy cảm có cần **ít nhất hai người/kiểm soát độc lập**? | Hai người phê duyệt tạo backup copy của recovery key |
| **Split knowledge** | Bí mật có được **chia thành các phần** để không ai biết toàn bộ không? | Chia recovery secret thành shares theo một cơ chế đã được thiết kế |
| **Two-person integrity** | Thao tác chỉ được thực hiện khi hai chủ thể đủ thẩm quyền tham gia? | Kích hoạt chế độ recovery của HSM cần hai người |
| **RBAC** | Gán quyền qua vai trò như thế nào? | Key operator, key owner, auditor |
| **ABAC** | Gán quyền theo thuộc tính/ngữ cảnh nào? | Chỉ production operator thuộc nhóm A và có incident ticket |
| **PAM/JIT** | Quyền đặc biệt có được cấp **tạm thời** và giám sát không? | Cấp quyền Rotate trong một maintenance window |
| **Independent audit** | Có kiểm tra bên ngoài người thực thi không? | Auditor đọc event KMS và log registry độc lập |

**Ví dụ phân biệt:** Hai người cùng biết đầy đủ một plaintext KEK và cùng bấm nút phê duyệt là **dual control trên giao diện**, nhưng **không phải split knowledge**. Ngược lại, chia một secret thành nhiều mảnh mà **một người giữ đủ ngưỡng mảnh** thì chưa đạt mục tiêu SoD thực tế.

### 3.1. Dual control không đồng nghĩa mọi việc phải chờ hai người

Việc **GetPublicKey** hoặc **Verify** chữ ký có thể không cần phê duyệt thủ công mỗi lần. Trái lại, thao tác **thay key policy, xuất khóa, bật quyền recovery, hủy KEK hoặc thay trust root** thường có rủi ro cao và cần kiểm soát nhiều tầng.

Áp dụng SoD **theo rủi ro**. Đưa người duyệt vào mọi request Encrypt có thể khiến hệ thống không vận hành được; cách tốt hơn là phân tách **định nghĩa chính sách** và **thực thi thao tác thường ngày** bằng ràng buộc IAM/KMS.

## 4. Các vai trò chủ chốt

| Vai trò | Trách nhiệm | Không mặc nhiên nên có |
|---|---|---|
| **Accountable key owner** | Purpose, key classification, cryptoperiod, quyết định lifecycle | Quyền đọc key material hoặc tự vượt policy |
| **Data owner** | Dữ liệu nào, tenant nào, retention và yêu cầu phục hồi | Quyền thao tác HSM |
| **Key custodian / operator** | Vận hành KMS/HSM, backup, health, cấu hình | Tự phê duyệt mọi thay đổi hoặc Decrypt dữ liệu |
| **Security policy administrator** | Viết policy, kiểm soát key usage, đánh giá rủi ro | Khả năng tự dùng mọi key theo policy vừa viết |
| **IAM administrator** | Quản lý định danh, quyền, grants, federation | Dùng quyền KMS Decrypt không liên quan |
| **Key creator / provisioning workflow** | Generate và đăng ký key, metadata | Tự kích hoạt mọi key ngoài approval |
| **Application cryptographic consumer** | Encrypt, Decrypt, Sign, Verify, Wrap/Unwrap theo nghiệp vụ | ChangeKeyPolicy, ExportKey hoặc ScheduleDelete |
| **Approver / change authority** | Chấp thuận thay đổi rủi ro cao theo bằng chứng | Tự thực thi/che dấu mọi thao tác |
| **Incident responder** | Containment, revoke, hạn quyền khẩn | Permanent destruction không cần guard |
| **Auditor** | Kiểm tra event, evidence, policy exceptions | Quản lý và xóa audit của mình |
| **PKI/trust administrator** | Quản lý certificate, public trust, revocation | Tự ký mọi danh tính bằng CA private key ngoài quy trình |
| **Recovery custodian** | Bảo quản shares hoặc đường recovery | Tự khôi phục toàn bộ bí mật khi không đủ điều kiện |

### 4.1. Owner khác operator và consumer

**Owner** chịu trách nhiệm về *mục đích và quyết định*, **operator** duy trì hạ tầng, **consumer** gọi phép toán được phép. Ví dụ một team thanh toán sở hữu KEK, đội hạ tầng vận hành KMS, ứng dụng Payment Service gọi Wrap/Unwrap theo quyền và đội an ninh kiểm tra sự kiện.

Không gán **service account** làm owner chỉ vì nó gọi Decrypt. Robot có thể là **consumer**, nhưng trách nhiệm quản trị cần một **nhóm/người có khả năng phê duyệt và nhận cảnh báo**.

## 5. Ma trận RACI trong vòng đời khóa

**RACI** phân định:

- **R – Responsible:** trực tiếp thực hiện công việc.
- **A – Accountable:** chịu trách nhiệm cuối cùng và quyết định.
- **C – Consulted:** được tham vấn trước quyết định.
- **I – Informed:** được thông báo.

Bảng là **ví dụ tổ chức**, không phải luật cố định. Mỗi hoạt động nên có **một vai trò A rõ ràng**; với các thao tác nhạy cảm, **R và A không nên là cùng một người/tài khoản**, trừ khi có kiểm soát bù trừ được phê duyệt.

| Hoạt động | Key owner | KMS operator | Security approver | App/data owner | Auditor |
|---|---|---|---|---|---|
| Định nghĩa purpose/cryptoperiod | **A** | C | C | **R** | I |
| Generate key đúng policy | A | **R** | C | C | I |
| Phê duyệt Activate/ChangePolicy | C | R khi thực thi | **A** | C | I |
| Cấp quyền Encrypt/Decrypt/Sign | A về nhu cầu | R cấu hình | **A** về control nếu rủi ro cao | C | I |
| Thực hiện Encrypt/Decrypt thường ngày | I | I | I | **A/R** qua service được phép | I |
| Rotation theo kế hoạch | **A** | **R** | C | C/R cutover | I |
| Emergency suspend/revoke | C/A theo policy | **R** | A hoặc hậu kiểm break-glass | C | I |
| Backup/recovery path | A | **R** | C/A nếu high-risk | C | I |
| Lập lịch hủy | A về dependency | **R** | **A** về destructive approval | C | I |
| Kiểm tra audit và policy drift | C | C | C | I | **A/R** |

Một ô A trong bảng không cấp quyền API tự động. **IAM/KMS grants** và **workflow approval** mới là nơi quyết định một principal có thể hành động gì.

### 5.1. RACI không thay thế xung đột quyền

RACI là tài liệu trách nhiệm. Nó không đủ nếu hai role được gán cho **cùng một người**, hoặc nếu một principal có thể tạo thêm role cho chính mình. Vì vậy phải kiểm tra **danh tính thực tế, quyền trực tiếp, inherited roles, group membership, emergency privileges và service accounts**.

## 6. Phân loại xung đột nhiệm vụ (SoD conflicts)

Một **SoD conflict** xảy ra khi một chủ thể có thể tổ hợp các quyền tạo thành một đường tấn công hoặc một thao tác không được giám sát.

| Tổ hợp quyền | Vì sao nguy hiểm? | Chính sách gợi ý |
|---|---|---|
| **GenerateKey + ApproveActivation** | Tự tạo và tự đưa khóa vào production | Tách approver hoặc phê duyệt chính sách tự động độc lập |
| **ChangeKeyPolicy + Decrypt/Unwrap** | Tự mở quyền rồi giải mã | Tách policy admin khỏi data-plane consumer |
| **ExportKey + đọc dữ liệu/backup** | Có thể lấy key và ciphertext | Cấm export hoặc dual control đặc biệt |
| **Sign + duyệt nội dung chứng từ** | Chứng từ giả có chữ ký mật mã hợp lệ | Business approval tách khỏi cryptographic signing |
| **IssueCertificate + TrustRootManagement** | Tự phát hành và tự làm hệ thống tin | Tách CA issuance, trust administration và audit |
| **ScheduleDelete/Destroy + approve destruction** | Hủy key không cần người thứ hai | Independent approval + dependency checks |
| **RotateKey + sửa key version mapping không audit** | Có thể trỏ alias tới vật liệu lạ | Version pinning, change evidence và review |
| **ChangeIAM + grant own privileged access** | Tự nâng quyền qua nhóm/role | Privilege escalation detection, PAM và policy boundary |
| **PerformCryptoOperation + edit audit logs** | Khó truy vết gian lận | Central immutable/tamper-evident audit do nhóm độc lập quản lý |
| **Backup key material + restore độc lập** | Có thể phục hồi secret trái phép | Recovery custodian separation, approval và giám sát |

### 6.1. Static SoD và dynamic SoD

- **Static SoD:** không cho cùng principal hoặc một người đồng thời sở hữu hai role xung đột, ví dụ PolicyAdmin và PrivilegedDecryptor.
- **Dynamic SoD:** một người có thể được phép đảm nhiệm hai chức năng ở những bối cảnh khác nhau, nhưng **không được tự yêu cầu và phê duyệt cùng operation**, hoặc không được sử dụng hai vai trò trong cùng phiên/quy trình.

Ví dụ một chuyên gia vừa là developer vừa có vai trò reviewer, nhưng **không được tự duyệt yêu cầu rotation do chính mình tạo**. Đây là ràng buộc trên **identity và operation**, không chỉ trên tên role.

### 6.2. Xung đột bắc cầu (transitive conflict)

Một người không có trực tiếp Decrypt nhưng có quyền **ModifyIamRole** rồi có thể gán Decrypt cho chính mình vẫn tạo rủi ro. Kiểm tra SoD phải tính **khả năng nâng quyền và quyền tạo/sửa policy**, không chỉ giao quyền hiện tại.

## 7. SoD trong bước sinh khóa (Generate)

Sinh khóa đúng không chỉ cần CSPRNG và algorithm phù hợp. Phải bảo đảm **key origin, purpose, owner, usage và export policy** không bị một bên tự đặt tùy ý mà thiếu kiểm soát.

Luồng tham khảo:

~~~mermaid
sequenceDiagram
    participant O as Service/Data owner
    participant P as Policy approver
    participant W as Key provisioning workflow
    participant K as KMS/HSM
    participant A as Audit system

    O->>W: Request key: purpose, algorithm, owner
    W->>P: Validate classification, usage, policy
    P-->>W: Approve hoặc reject với evidence
    W->>K: Generate key material dưới scope được phép
    K-->>W: Key reference/version và metadata
    W->>A: Event: approver, actor, key ID, result
    W-->>O: Key reference; không trả secret trái policy
~~~

Những điểm cần kiểm soát:

1. Người yêu cầu ghi rõ **mục đích, loại khóa, owner và môi trường**.
2. Policy engine hoặc approver độc lập kiểm tra algorithm, key size/curve, exportability, cryptoperiod, phân loại dữ liệu.
3. Workflow thực thi GenerateKey với quyền **giới hạn đúng provider/account/tenant**.
4. Nếu private signing key hoặc KEK phải non-exportable, xác minh ranh giới thực tế của KMS/HSM.
5. Đăng ký key ID/version, owner và policy; audit **không chứa plaintext DEK hoặc private key**.
6. Chỉ Activate/cấp usage sau khi có bằng chứng kiểm tra cần thiết.

**Không để creator tự đổi key origin hoặc import một secret yếu rồi tự tuyên bố đó là khóa mới an toàn.** KMS/HSM không tự tăng entropy cho vật liệu khóa yếu đã được import.

## 8. SoD trong cấp phát và lưu trữ khóa

### 8.1. Phân phối secret khác phân phối public key

- **Symmetric key, HMAC key, plaintext DEK và private key** phải được truyền/lưu trong ranh giới bí mật, chỉ tới consumer được phép.
- **Public verification key/certificate** có thể công khai nhưng phải có nguồn tin cậy; thay thế nó trong trust store là thao tác nhạy cảm dù public key không bí mật.
- **KMS key ID/alias** thường là reference, không phải secret; nhưng có thể tiết lộ metadata tổ chức, vẫn cần chính sách xem phù hợp.

**SoD áp dụng cả lên cấu hình phân phối.** Một developer không nên được tự upload public key mới vào danh sách trust của mọi verifier mà không có chứng cứ quyền phát hành.

### 8.2. KMS/HSM và ranh giới kỹ thuật

Một HSM có thể bảo vệ private key khỏi export, song ai có quyền **Sign** vẫn có thể lạm dụng phép ký nếu đầu vào không được xác thực. Vì vậy nên tách:

- **Key administrator:** tạo/sắp xếp key, cấu hình policies.
- **Crypto user:** gọi Sign/Decrypt/Wrap theo purpose.
- **Security officer:** phê duyệt và kiểm tra thay đổi rủi ro.
- **Auditor:** kiểm tra event độc lập.
- **Recovery operator:** thực thi recovery theo policy riêng.

Tên vai trò thật tùy nhà cung cấp HSM/KMS. **Không suy rằng một “Security Officer” có cùng quyền trên mọi HSM**, hoặc mọi KMS hỗ trợ dual control ở mức API. Cần xác minh tính năng, cấu hình và chính sách hiện hành.

## 9. SoD trong sử dụng DEK/KEK và envelope encryption

**Envelope encryption** thường dùng **DEK** mã hóa dữ liệu và **KEK** bảo vệ DEK. SoD cần duy trì giữa chủ dữ liệu, consumer, owner KEK và quyền KMS.

~~~mermaid
flowchart TD
    D["Data owner: policy và phân loại"] --> P["Approval + tenant authorization"]
    P --> A["Application: AES-GCM với DEK"]
    K["KMS/HSM: KEK non-exportable"] --> W["Wrap/Unwrap DEK theo IAM"]
    W --> A
    A --> S["Ciphertext + nonce + tag + encrypted DEK"]
    I["IAM admin: quản lý roles"] --> W
    U["Audit team độc lập"] --> L["Audit KMS và nghiệp vụ"]
    W --> L
    A --> L
~~~

### 9.1. Ví dụ phân quyền

| Chủ thể | Quyền nên có | Quyền nên tránh |
|---|---|---|
| **Service Encryptor** | GenerateDataKey hoặc Encrypt/Wrap trong tenant được phép | DeleteKey, ChangeKeyPolicy, ExportKEK |
| **Service Decryptor** | Decrypt/Unwrap cho dữ liệu được nghiệp vụ cho phép | Tự thêm grants, quản trị tenant khác |
| **KMS key operator** | Quản lý key version, health, rotation theo approval | Tự giải mã dữ liệu người dùng |
| **Data owner** | Phê duyệt phân loại, retention, recovery scope | KMS Decrypt không cần thiết |
| **Security approver** | Review thay đổi policy, xử lý sự cố | Quyền read plaintext key |
| **Auditor** | Read audit metadata, finding, grants | Tự sửa/xóa log hoặc dùng KEK |

Trong một số API KMS, GenerateDataKey có thể trả **plaintext DEK trong ứng dụng**. Điều này không tự vi phạm SoD nếu kiến trúc cho phép và app có quyền tương ứng, nhưng ứng dụng phải kiểm soát **vòng đời DEK trong RAM, logging, key scope, nonce uniqueness và tenant authorization**.

### 9.2. Policy KMS không thay business authorization

Một KMS có thể kiểm tra service có quyền Decrypt, nhưng **không biết người dùng cuối có được xem hóa đơn X hay không** trừ khi có thiết kế ràng buộc được kiểm chứng (ví dụ encryption context cộng với kiểm tra nghiệp vụ). **Service phải xác thực người dùng/tenant trước khi gọi KMS**.

Nếu ứng dụng dùng key từ tenant A cho dữ liệu tenant B, lỗi nằm ở logic dữ liệu/ủy quyền ngay cả khi key policy không bị phá.

### 9.3. Nonce và secret usage

SoD không giải quyết lỗi **AES-GCM nonce reuse**. Cần kiểm soát thiết kế nonce uniqueness dưới từng DEK, phân tách writer/counter, kiểm thử retry/restore và giới hạn traffic. Đây là kiểm soát mật mã độc lập phải kết hợp SoD.

## 10. SoD trong chữ ký số và hệ thống PKI

Đối với chữ ký số, có **hai loại ủy quyền khác nhau**:

1. **Business authorization:** nội dung nào được phê duyệt để ký, ai có quyền phê duyệt?
2. **Cryptographic authorization:** principal nào được gọi Sign bằng private key nào?

Khi chỉ có lớp thứ hai, một service bị chiếm quyền có thể gọi HSM Sign và tạo **chữ ký toán học hợp lệ trên tài liệu không được duyệt**.

### 10.1. Workflow ký chứng từ có SoD

~~~mermaid
sequenceDiagram
    participant U as Người tạo yêu cầu
    participant B as Business approver
    participant S as Signing service
    participant H as HSM
    participant V as Verifier/Audit

    U->>B: Gửi chứng từ và transaction ID
    B-->>S: Chứng cứ phê duyệt đã xác thực
    S->>S: Kiểm tra amount, tenant, hash, approval scope
    S->>H: Sign nội dung đã ràng buộc với yêu cầu
    H-->>S: Signature
    S-->>V: Document + signature + key ID + approval reference
    V->>V: Verify signature và policy/nghiệp vụ
~~~

Chứng cứ phê duyệt nên **ràng buộc chính xác nội dung hoặc digest, phiên bản, mục đích, danh tính và thời hạn** để tránh một approval cho chứng từ A bị tái sử dụng cho chứng từ B.

**Người phê duyệt chứng từ không được tự chạy workflow ký mà bỏ qua bước kiểm tra**, và signer không được tự làm reviewer của giao dịch mà chính mình phát hành.

### 10.2. Phân tách vận hành PKI

Đối với CA và certificate lifecycle, cần đánh giá xung đột giữa:

- Yêu cầu cấp chứng chỉ và **xác minh danh tính**.
- Phê duyệt nội dung chứng chỉ và **CA signing operations**.
- Cấu hình CA/trust root và **kiểm toán issuance**.
- Phân phối public trust và **quyền thay key của issuer**.
- Thu hồi chứng chỉ và **quản lý dữ liệu/biên bản sự cố**.

**Public key không bí mật**, nhưng việc đưa public key sai vào trust store có thể khiến hệ thống tin kẻ mạo danh. Vì vậy quyền ChangeTrustStore/PublishJWKS có mức rủi ro khác với GetPublicKey/Verify.

## 11. SoD trong rotation có kế hoạch

Rotation thường là chuỗi thao tác nhiều người hoặc nhiều dịch vụ thực hiện:

~~~mermaid
flowchart LR
    O["Owner đề xuất rotation"] --> P["Approver kiểm tra kế hoạch"]
    P --> G["KMS operator Generate v2"]
    G --> A["Activate sau readiness checks"]
    A --> C["App team cutover traffic"]
    C --> V["Independent verification"]
    V --> R["Retire v1, giữ dependency"]
    R --> D["Destruction approval khi đủ điều kiện"]
~~~

### 11.1. KEK rotation khác DEK rotation

- **KEK rotation:** khi vật liệu KEK cũ chưa bị lộ và kiến trúc envelope encryption hỗ trợ, có thể **rewrap** những DEK dưới KEK mới, chưa nhất thiết re-encrypt toàn bộ dữ liệu.
- **DEK rotation:** thường đòi hỏi **mã hóa lại dữ liệu** dưới DEK mới.
- **Signing key rotation:** cần phát hành public verification key/chứng chỉ mới, cập nhật verifier và xử lý chữ ký lịch sử.

SoD cần phân tách **người đề xuất và phê duyệt**, **người thực hiện KMS**, và **người xác nhận dữ liệu/trust thực sự đã chuyển**. Không hủy key cũ chỉ vì operator đã thấy API GenerateKey thành công.

### 11.2. Người thực hiện không tự xác nhận đủ điều kiện hủy

Ví dụ, một người vừa chạy script rewrap vừa ghi “mọi DEK đã được xử lý” có thể bỏ sót backup. **Data owner** hoặc workflow kiểm kê độc lập phải xác minh số encrypted DEK, object, archive, thời hạn retention và khả năng restore trước khi phê duyệt destruction.

## 12. SoD trong suspend, revoke và destroy

Các bước này khác nhau về khả năng hoàn nguyên.

| Hành động | Rủi ro | Kiểm soát SoD |
|---|---|---|
| **Suspend** | Có thể làm gián đoạn ứng dụng, nhưng thường đảo ngược được theo provider | Cho responder quyền có giới hạn, audit và xác nhận hậu điều kiện |
| **Resume** | Có thể mở lại đường bị lộ | Người xác minh rủi ro độc lập; không tự phục hồi REVOKED |
| **Revoke** | Rút quyền/trust ở nhiều consumer, ảnh hưởng giao dịch | Incident approval/hậu kiểm, trust propagation |
| **ScheduleDelete** | Bắt đầu đếm tới thao tác phá hủy, ảnh hưởng backup | Dependency clearance + approval độc lập |
| **Destroy** | Có thể mất dữ liệu vĩnh viễn | Dual control, retention/backup review và provider evidence |

### 12.1. Không phá hủy khi còn DEK phụ thuộc

Nếu KEK bị hủy trước khi tất cả encrypted DEK cần thiết đã rewrap/migrate, doanh nghiệp có thể mất dữ liệu hợp lệ. Kiểm soát phù hợp không chỉ là “hai người cùng nhấn Delete”; cả hai cần **bằng chứng phụ thuộc được kiểm tra độc lập**.

### 12.2. Thu hồi key ký cần cập nhật verifier

Disable private key ở HSM **không khiến public verification key tự mất hiệu lực**. Nếu private key bị sao chép, kẻ tấn công có thể ký ngoài HSM. PKI/trust owner phải xử lý certificate revocation, JWKS, trust store và cache; auditor xác minh propagation.

### 12.3. Chỉ xác nhận DESTROYED khi đã hủy thật

ScheduleDeletion và destruction có thể cách nhau một khoảng theo provider. Không cho caller tự đặt trạng thái DESTROYED rồi xóa log. **Observed KMS/HSM state và bằng chứng xử lý backup** phải được xác nhận, và không thể khẳng định mọi bản sao bị đánh cắp đã bị hủy từ xa.

## 13. Áp SoD bằng IAM, RBAC, ABAC và policy boundaries

RACI/RBAC là điểm xuất phát; việc kiểm soát thật nằm ở **quyền API, identity và điều kiện thực thi**.

### 13.1. Role tách theo control plane và data plane

~~~text
Control plane:
  KeyPolicyAdmin: tạo/thay policy, không được Decrypt.
  KeyLifecycleOperator: rotate/disable theo approval, không tự duyệt.
  IAMAdmin: cấp/quản trị role, không tự dùng secret.
  Auditor: đọc audit, không xóa log.

Data plane:
  EncryptService: Encrypt / Wrap trong scope hợp lệ.
  DecryptService: Decrypt / Unwrap đúng tenant.
  SigningService: Sign nội dung đã được duyệt.
  Verifier: Verify bằng public key đáng tin.
~~~

Đây là mô hình logic. Khả năng tách chi tiết quyền **phụ thuộc KMS/HSM và API**. Một số provider không phân biệt mọi quyền theo cách giống nhau, nên cần kiểm tra tài liệu và thử negative permissions.

### 13.2. ABAC và context binding

Một policy có thể ràng buộc thao tác với:

- **Environment/tenant:** production vs staging; tenant A vs tenant B.
- **Key purpose:** Encrypt, Decrypt, Sign, Wrap, Unwrap.
- **Source identity/workload:** service principal, workload identity, project, cluster.
- **Time and change context:** maintenance window, JIT privilege, approval reference.
- **Request context:** encryption context/AAD nếu provider hỗ trợ và được ứng dụng kiểm tra.
- **Device/network posture:** chỉ khi có dữ liệu đáng tin và policy hỗ trợ.

**Không coi các trường do client tự gửi là nguồn sự thật**. Ví dụ client truyền “approved=true” hoặc “tenant=VIP” không đủ để KMS/ứng dụng cho phép mở khóa nếu không có xác thực và kiểm tra quyền đáng tin.

### 13.3. Không chỉ nhìn tên role

Một tài khoản có thể **kế thừa** quyền qua nhiều nhóm, role assumption, temporary credentials hoặc policy grant. Người không có Decrypt trực tiếp nhưng có thể **tự sửa IAM để gán Decrypt** vẫn tạo đường vượt SoD. Chính sách kiểm toán phải đánh giá **effective permissions và privilege escalation paths**.
## 14. Dual control và nguyên tắc nhiều người tham gia

**Dual control** là yêu cầu tối thiểu hai chủ thể được ủy quyền tham gia một thao tác quan trọng. Trong quản lý khóa, điều này có thể là **maker-checker** (một người đề xuất, người khác duyệt), **two-person operation** (hai người cùng tham gia vận hành) hoặc **n-of-m approval** (một ngưỡng phê duyệt trong tập người có quyền).

### 14.1. Những hành động thường cần dual control

| Hành động | Vì sao rủi ro cao? | Hình thức kiểm soát |
|---|---|---|
| Export plaintext key nếu policy cho phép | Bản sao bí mật có thể rời miền bảo vệ | Approval độc lập, giới hạn phạm vi, ghi đầy đủ evidence |
| Thay key policy để mở quyền Decrypt/Sign | Có thể cho phép lạm dụng dữ liệu/chữ ký | Maker-checker + kiểm tra policy diff |
| Phục hồi master/recovery key | Có thể mở nhiều dữ liệu hoặc thay quyền gốc | HSM M-of-N hoặc workflow nhiều người tùy khả năng |
| Thay CA/trust root | Có thể làm hệ thống tin danh tính giả | Approval độc lập và kiểm tra trust propagation |
| ScheduleDelete/Destroy KEK | Có thể mất khả năng khôi phục hàng nghìn DEK | Dependency clearance + dual approval |
| Revoke signing key dùng rộng | Có thể làm gián đoạn nhiều verifier và giao dịch | Incident authority + hậu kiểm, theo mức khẩn |
| Thay đổi quy tắc SoD | Có thể tự vô hiệu các kiểm soát | Quản lý security policy độc lập, code review và audit |

### 14.2. Kiểm tra hai người thật, không chỉ hai tài khoản

Hai user IDs khác nhau có thể cùng thuộc một người hoặc cùng một credential dùng chung. Nếu chính sách yêu cầu hai cá nhân độc lập, workflow cần dùng **định danh người đã được xác thực** (ví dụ stable person ID từ directory), không chỉ so sánh tên đăng nhập.

Cũng cần xác minh:

- **Requester không phải approver** trên cùng change request.
- Hai approver thật sự **đủ thẩm quyền** tại thời điểm ký duyệt.
- Approval ràng buộc với **key ID, material version, hành động và nội dung thay đổi**.
- Một approval cũ không bị dùng lại cho request khác.
- Không ai có thể **sửa payload sau khi đã được duyệt** mà bỏ qua vòng approval.
- Người thực thi không thể **tự tạo approval giả** trong cùng hệ thống do mình kiểm soát.

### 14.3. Approval quorum không đồng nghĩa threshold cryptography

Chính sách yêu cầu **hai chữ ký duyệt** cho DestroyKey không có nghĩa khóa được chia thành hai share. Một HSM có thể cho phép một role hợp lệ thực thi API sau khi workflow nhận đủ approval. Trong khi đó, **threshold cryptography** thực sự phân bố bí mật hoặc khả năng tính toán mật mã giữa các bên theo một protocol cụ thể.

Cần ghi rõ hệ thống đang dùng **quorum phê duyệt**, **quorum vận hành của HSM**, hay **ngưỡng mật mã**, vì các giả định an toàn khác nhau.

## 15. Split knowledge và quản lý recovery secret

**Split knowledge** là nguyên tắc hạn chế việc một người nắm toàn bộ bí mật có khả năng kiểm soát hệ thống. Có thể được triển khai bằng một cơ chế chia bí mật đã được đánh giá, chẳng hạn **Shamir's Secret Sharing** trong thiết kế phù hợp, hoặc tính năng quorum/recovery do HSM hỗ trợ.

Ví dụ khái niệm: một recovery secret được chia thành **5 shares**, muốn tái tạo cần **ít nhất 3 shares** (3-of-5). Mỗi share đơn lẻ không cho phép tái tạo theo giả định và cách triển khai của sơ đồ chia bí mật.

~~~text
Recovery secret (trong ranh giới tin cậy)
                  |
        Chia theo cơ chế 3-of-5
                  |
          +-------+-------+-------+-------+
          |       |       |       |       |
        Share1  Share2  Share3  Share4  Share5
          |       |       |       |       |
        PersonA PersonB PersonC PersonD PersonE

  Khôi phục: bất kỳ 3 shares hợp lệ được xử lý
  qua quy trình recovery đã xác thực và kiểm toán.
~~~

### 15.1. Điều kiện để split knowledge có ý nghĩa

1. **Phân phối thực sự độc lập:** các shares không cùng được lưu trong một file hoặc một vault mà một người có thể đọc tất cả.
2. **Bảo vệ share:** mỗi phần có bảo mật lưu trữ, xác thực, kiểm soát truy xuất và xử lý khi mất.
3. **Môi trường tái tạo:** chỉ khôi phục trong hệ thống được phép, giảm thời gian tồn tại plaintext secret và bảo vệ khỏi memory/log leakage.
4. **Đúng tập chủ thể:** kiểm soát việc một người nắm nhiều shares, kể cả do thay đổi nhân sự.
5. **Recovery drill:** thử khôi phục định kỳ với dữ liệu thử hoặc quy trình an toàn, kiểm tra ngưỡng, khả năng thay người giữ share.
6. **Giới hạn:** khôi phục thành công không tự chứng minh người thực hiện được phép dùng secret cho mọi mục đích.

**Không tự viết Shamir/threshold code để dùng production** nếu thư viện, quy trình phân phối và ranh giới bảo mật chưa được kiểm chứng. Cần đánh giá cả nguy cơ lộ thông tin qua chia sẻ, thay thế shares, lưu trữ và việc tổ hợp trong RAM.

### 15.2. HSM quorum và split knowledge khác nhau

Một HSM có thể yêu cầu nhiều operator xác thực trước khi mở một chức năng đặc quyền nhưng **key material không rời HSM**. Đây có thể là dual control rất tốt mà **không cần ai nắm share của KEK dạng rõ**. Không mặc định HSM nào cũng có cùng chức năng M-of-N hoặc tên role.

### 15.3. Nếu một recovery custodian nghỉ việc

Cần thu hồi quyền, thay thế người giữ share hoặc tái phân phối secret theo cơ chế được phê duyệt. Không tự gửi bản sao share cho người mới qua email. Tất cả quy trình phải có **owner, inventory, approval, chain of custody và audit**.

## 16. Workflow maker-checker có thể kiểm chứng

Một workflow SoD nên được thiết kế thành **chuỗi trạng thái có evidence**, không đơn giản là checkbox “Approved”.

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> VALIDATING: Kiểm tra input, identity, scope
    VALIDATING --> WAITING_APPROVAL: Đúng policy
    VALIDATING --> REJECTED: Thiếu quyền hoặc conflict
    WAITING_APPROVAL --> APPROVED: Đạt quorum và no self-approval
    WAITING_APPROVAL --> REJECTED: Từ chối / hết hạn
    APPROVED --> EXECUTING: Phân công operator hoặc workflow
    EXECUTING --> VERIFYING: Provider trả kết quả
    VERIFYING --> COMPLETED: Readback và audit thành công
    VERIFYING --> REQUIRES_ATTENTION: Hậu điều kiện không đạt
    COMPLETED --> [*]
    REJECTED --> [*]
~~~

### 16.1. Bằng chứng cần có trong từng yêu cầu

| Nhóm | Trường gợi ý | Ý nghĩa |
|---|---|---|
| **Đối tượng** | provider, account, keyId, materialVersion | Đúng vật liệu cần thay |
| **Tác vụ** | requestedAction, purpose, parameter digest | Phân biệt ChangePolicy, Rotate, Revoke, Destroy |
| **Người yêu cầu** | requesterPersonId, service principal, team | Ngăn tự duyệt và kiểm tra owner |
| **Người duyệt** | approverPersonIds, roles, approval timestamps | Đạt quorum độc lập |
| **Phê duyệt** | policyVersion, signed request digest, expiresAt | Không dùng lại duyệt cũ sau khi sửa nội dung |
| **Triển khai** | operator/service, operationId, expectedRevision | Idempotency và chống stale request |
| **Kết quả** | desiredState, observedProviderState, effectiveAt | Không tin chỉ vào ACK |
| **Kiểm toán** | incident/change ID, evidenceRefs, audit event ID | Truy vết độc lập |

**Hash/digest của yêu cầu** cần được tính từ **canonical representation** có ranh giới trường, version, key ID và parameters rõ ràng. Không chỉ hash một chuỗi ghép không có encoding rồi coi nó là ràng buộc an toàn.

### 16.2. Approval có vòng đời

Approval có thể **hết hạn, bị thu hồi, hoặc mất hiệu lực** khi scope/actor/key state thay đổi. Trước khi thực thi phải kiểm tra lại:

- Request chưa bị thay nội dung.
- Key version chưa bị REVOKED/DESTROYED bởi workflow khác.
- Approver chưa mất quyền hoặc thay đổi nhiệm vụ theo chính sách.
- Số approval còn đủ và không phải của cùng một người.
- Data dependency/retention guard vẫn hợp lệ.

Khi một guard đổi, request phải được đánh giá và phê duyệt lại nếu policy yêu cầu, không chỉ tiếp tục dựa trên trạng thái cũ.

## 17. Quyền khẩn cấp (break-glass) và SoD

SoD không được khiến hệ thống **không thể chặn cuộc tấn công đang diễn ra**. Ví dụ private signing key bị lộ hoặc principal đang Unwrap DEK trái phép cần có **emergency containment** ngay.

Giải pháp là **phân biệt thao tác chặn có thể đảo ngược** với **thao tác phá hủy không thể hoàn nguyên**.

| Loại thao tác khẩn | Mức phê duyệt tham khảo | Hậu kiểm |
|---|---|---|
| Thu hồi session token/credential bị chiếm | Responder có thẩm quyền, scope giới hạn | Audit ngay và review incident |
| Disable grant hoặc Suspend key | Break-glass theo policy, có thể không chờ hai người | Bắt buộc hậu kiểm và kiểm tra availability |
| Revoke trust của key ký bị lộ | Incident authority, PKI/trust owner phối hợp | Xác minh verifier và client cache |
| Tạo replacement key | Operator/workflow được phê duyệt trước về thuật toán và scope | Audit và đối chiếu vật liệu/version |
| Delete/Destroy KEK/DEK | Không tự động dựa vào một cảnh báo | Dependency inventory, approval độc lập, provider confirmation |
| Khôi phục quyền sau incident | Đánh giá độc lập, không tự tái ACTIVE vật liệu bị lộ | Kiểm tra lại IAM/policy, evidence và audit |

### 17.1. Break-glass policy phải nêu rõ

- **Ai được kích hoạt?** Một identity mạnh, MFA, on-call/incident role.
- **Khi nào?** Incident ID, trigger, phạm vi, severity.
- **Được làm gì?** Chỉ actions cần thiết với key version cụ thể.
- **Trong bao lâu?** TTL ngắn, quyền JIT tự hết hạn hoặc bị thu hồi.
- **Ai theo dõi?** Auditor/SOC nhận alert, log lưu nơi không thể sửa bởi responder.
- **Ai hậu kiểm?** Independent reviewer xác nhận mục đích, hành động, hiệu lực, rủi ro còn lại.
- **Điều cấm?** Tự ExportKey/Destroy tất cả key, xóa audit, bỏ qua retention.

### 17.2. Không nhầm “có hai người xem” với thực thi SoD

Nếu hai người chỉ cùng đăng nhập bằng một super-admin account thì không có attribution độc lập. Tổ chức cần identity riêng, phân quyền, audit và cơ chế ngăn thao tác của một người khi thiếu quorum.

## 18. SoD cho service accounts, CI/CD và automation

Trong hệ thống Java/microservices, rất nhiều hành động được chạy bởi **pipeline và workload identity**, không phải người thao tác trực tiếp.

### 18.1. Những đường vượt kiểm soát dễ bị bỏ sót

- Một CI token có thể **sửa KMS policy**, triển khai signer và xóa audit logs.
- Pipeline tự chạy rotation rồi **tự phê duyệt output** bằng chính credential đó.
- Developer có thể sửa **IaC policy** và merge ngay vào protected branch không cần code review.
- Một workload có quyền **AssumeRole** để tự nâng từ Encryptor sang KeyAdmin.
- Terraform/service principal được cấp quyền **ScheduleDelete** cho mọi key trong account.
- Một test/staging principal có quyền sử dụng production KEK.

SoD cần được áp ở **tất cả các điểm nơi quyền có thể phát sinh**, bao gồm source control, CI/CD, secret stores, IaC, cloud IAM, KMS grants và các quyền điều chỉnh chính sách.

### 18.2. Controls khuyến nghị

| Điểm kiểm soát | Thiết kế |
|---|---|
| **Source code / IaC** | Pull request review độc lập; code owner cho policy/crypto changes; protected branch |
| **Build pipeline** | Artifact provenance, tách build và production deploy approval |
| **Production deployment** | JIT workload credentials, approval theo change/incident khi nhạy cảm |
| **KMS resource creation** | Provisioner chỉ Generate/Tag trong scope; không tự Export/Delete |
| **IAM policy change** | Policy-as-code tests, diff review, deny privilege escalation |
| **Crypto operation** | App workload chỉ có usage cần thiết; không có admin rights |
| **Audit** | Centralize logs tới hệ thống/nhóm có quyền quản lý độc lập |
| **Environment segregation** | Production KEK/private keys tách test/staging, không chia sẻ vật liệu |
| **Service account ownership** | Có owner con người/team active, rotation và offboarding |

### 18.3. Đường tự nâng quyền

Đánh giá **effective permissions**: một user không có Decrypt trực tiếp nhưng có quyền sửa role policy và assume role rồi Decrypt vẫn tạo SoD conflict. Bộ kiểm tra phải phân tích cả **quyền cấp quyền, quyền ủy quyền, delegation chains và session role combinations**.

## 19. Java 17: ví dụ kiểm tra xung đột và self-approval

Đoạn mã dưới đây minh họa **policy decision logic**, không thao tác key thật. Nó kiểm tra:

- Requester có quyền yêu cầu loại action tương ứng.
- Approvers có role SECURITY_APPROVER.
- **Không có self-approval** theo person ID, kể cả cùng người dùng nhiều account.
- Approval phải gắn đúng **request ID, key reference, nội dung thay đổi (digest)** và còn trong thời hạn.
- Thao tác **Destroy** đòi hỏi **hai approver độc lập**, còn ChangePolicy/Rotate cần một approver trong mô hình minh họa.
- **Emergency Suspend** cho phép incident responder khởi động containment theo policy và phải hậu kiểm.

Code này **không nhận roles, personId hoặc approvals từ JSON do người dùng tự khai**; production cần lấy từ identity provider/workflow được xác thực.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class SeparationOfDutiesExample {

    enum Role {
        KEY_OWNER, KEY_OPERATOR, SECURITY_APPROVER,
        INCIDENT_RESPONDER, AUDITOR
    }

    enum Action {
        ROTATE, CHANGE_POLICY, DESTROY,
        EMERGENCY_SUSPEND
    }

    record Actor(
        String subjectId,
        String personId,
        Set<Role> roles
    ) {
        boolean has(Role role) {
            return roles != null && roles.contains(role);
        }
    }

    record ChangeRequest(
        String requestId,
        String keyRef,
        String changeDigest,
        Actor requester,
        Action action,
        Instant createdAt,
        String incidentId
    ) {}

    record Approval(
        String requestId,
        String keyRef,
        String changeDigest,
        Actor approver,
        Instant approvedAt
    ) {}

    record Decision(boolean allowed, String reason) {}

    private static boolean nonBlank(String value) {
        return value != null && !value.isBlank();
    }

    static Decision evaluate(
        ChangeRequest request,
        List<Approval> approvals,
        Instant now
    ) {
        if (request == null || request.requester() == null
                || request.action() == null
                || request.createdAt() == null
                || !nonBlank(request.requestId())
                || !nonBlank(request.keyRef())
                || !nonBlank(request.changeDigest())
                || !nonBlank(request.requester().personId())) {
            return new Decision(false, "Invalid request");
        }

        Actor requester = request.requester();

        // Emergency containment is a separately bounded permission.
        if (request.action() == Action.EMERGENCY_SUSPEND) {
            boolean ok = requester.has(Role.INCIDENT_RESPONDER)
                && nonBlank(request.incidentId());
            return new Decision(
                ok,
                ok ? "Emergency suspend: audit and review required"
                   : "Responder permission/incident missing"
            );
        }

        if (!requester.has(Role.KEY_OWNER)
                && !requester.has(Role.KEY_OPERATOR)) {
            return new Decision(false, "Requester not authorized");
        }

        int required = request.action() == Action.DESTROY ? 2 : 1;
        Set<String> independentApprovers = new HashSet<>();

        if (approvals != null) {
            for (Approval approval : approvals) {
                if (approval == null || approval.approver() == null
                        || approval.approvedAt() == null) {
                    continue;
                }

                Actor approver = approval.approver();
                if (!approver.has(Role.SECURITY_APPROVER)
                        || !nonBlank(approver.personId())) {
                    continue;
                }

                // Same human cannot self-approve, even via another login.
                if (approver.personId().equals(requester.personId())) {
                    continue;
                }

                // Exact request and approved content must match.
                if (!request.requestId().equals(approval.requestId())
                        || !request.keyRef().equals(approval.keyRef())
                        || !request.changeDigest()
                            .equals(approval.changeDigest())) {
                    continue;
                }

                // Example policy: approvals valid for at most two hours.
                Instant expiry = approval.approvedAt()
                    .plus(Duration.ofHours(2));
                if (approval.approvedAt().isBefore(request.createdAt())
                        || approval.approvedAt().isAfter(now)
                        || expiry.isBefore(now)) {
                    continue;
                }

                independentApprovers.add(approver.personId());
            }
        }

        if (independentApprovers.size() < required) {
            return new Decision(
                false, "Insufficient independent approvals"
            );
        }
        return new Decision(true, "Policy preconditions satisfied");
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-28T02:00:00Z");

        Actor owner = new Actor(
            "account-owner-1", "person-001",
            Set.of(Role.KEY_OWNER)
        );
        Actor approver1 = new Actor(
            "account-reviewer-1", "person-002",
            Set.of(Role.SECURITY_APPROVER)
        );
        Actor approver2 = new Actor(
            "account-reviewer-2", "person-003",
            Set.of(Role.SECURITY_APPROVER)
        );

        ChangeRequest destroy = new ChangeRequest(
            "chg-1001",
            "kms/prod/payments-kek/v2",
            "sha256-of-canonical-approved-change",
            owner,
            Action.DESTROY,
            now.minus(Duration.ofMinutes(10)),
            null
        );

        Approval a1 = new Approval(
            destroy.requestId(), destroy.keyRef(),
            destroy.changeDigest(), approver1,
            now.minus(Duration.ofMinutes(5))
        );
        Approval a2 = new Approval(
            destroy.requestId(), destroy.keyRef(),
            destroy.changeDigest(), approver2,
            now.minus(Duration.ofMinutes(4))
        );

        Decision denied = evaluate(destroy, List.of(a1), now);
        Decision allowed = evaluate(
            destroy, List.of(a1, a2), now
        );

        if (denied.allowed() || !allowed.allowed()) {
            throw new IllegalStateException("SoD guard failed");
        }
        System.out.println("SoD decision guard OK");
    }
}
~~~

### 19.1. Ranh giới và giới hạn của ví dụ

Đây chỉ là **đề xuất quyết định policy**. Chữ *allowed* ở đây có nghĩa **đạt một số điều kiện SoD**, không phải được phép xóa khóa thật ngay:

- Vẫn cần xác minh **IAM tại runtime**, owner, data classification, retention, legal hold và backup.
- Approval phải được lưu/truy xuất từ **workflow có xác thực**, ràng buộc với payload canonical và chống sửa đổi.
- **Destroy** cần kiểm tra encrypted DEK/dependency graph và khả năng recovery; hai approval không thay điều kiện này.
- Cần **expected revision/CAS**, operation ID, idempotency, provider readback và audit.
- Phải ngăn một người quản trị IAM tự cấp role SECURITY_APPROVER để vượt SoD.
- Nếu có nhiều account cho cùng một người, **personId** phải là định danh đáng tin, không do người dùng tự đặt.
- Break-glass ở ví dụ **chưa thực thi** TTL, audit hay hậu kiểm; production bắt buộc bổ sung.
- Không dùng output của ví dụ để trực tiếp gọi KMS ScheduleDelete khi chưa qua workflow hoàn chỉnh.

### 19.2. Vì sao “hai approver” không đủ?

Nếu cả hai người đều ký một request cũ, nhưng sau đó operator đổi **keyRef** hoặc phạm vi dữ liệu bị hủy, approval không còn áp dụng. Phải ràng buộc người duyệt với **nội dung và phiên bản request**, và kiểm tra **guard tại thời điểm thực thi**.

## 20. Audit, policy-as-code và phát hiện SoD conflicts

### 20.1. Audit cần độc lập với người thực thi

Một event thay đổi key policy có thể chứa:

~~~json
{
  "eventType": "KEY_POLICY_CHANGE",
  "operationId": "op-20261128-101",
  "keyRef": "kms/prod/payments-kek/v2",
  "requestedBy": "person-001",
  "approvedBy": ["person-002", "person-003"],
  "executedBy": "kms-lifecycle-workflow",
  "policyVersionBefore": 4,
  "policyVersionAfter": 5,
  "requestDigestRef": "approval-bound-change-digest",
  "reason": "Planned rotation",
  "providerResult": "CONFIRMED",
  "evidenceRefs": ["change-1001", "dependency-report-827"],
  "occurredAt": "2026-11-28T02:10:00Z"
}
~~~

Đây là **schema minh họa**. Nhật ký cần đủ để truy vết **người yêu cầu, người duyệt, người thực thi, key version, policy diff, thời gian, kết quả provider và hậu điều kiện**, không lưu plaintext DEK/private keys, HMAC secret, RNG seed hoặc bearer token còn hiệu lực.

### 20.2. Phát hiện xung đột vai trò từ IAM

Một truy vấn SQL minh họa từ bảng role assignments đã được chuẩn hóa:

~~~sql
-- Ví dụ gần PostgreSQL; dữ liệu vai trò phải phản ánh
-- cả quyền kế thừa/effective permissions khi đưa vào production.
SELECT
    subject_id,
    COUNT(DISTINCT CASE
        WHEN role_name = 'KEY_POLICY_ADMIN'
        THEN role_name END) AS policy_admin_roles,
    COUNT(DISTINCT CASE
        WHEN role_name = 'PRIVILEGED_DECRYPTOR'
        THEN role_name END) AS decrypt_roles
FROM effective_role_assignment
WHERE environment = 'production'
GROUP BY subject_id
HAVING COUNT(DISTINCT CASE
           WHEN role_name = 'KEY_POLICY_ADMIN'
           THEN role_name END) > 0
   AND COUNT(DISTINCT CASE
           WHEN role_name = 'PRIVILEGED_DECRYPTOR'
           THEN role_name END) > 0;
~~~

**Truy vấn chỉ minh họa một cặp xung đột ở cấp subject.** Khi có nhiều tài khoản của cùng người, service identities, AssumeRole, delegated access hoặc quyền tạo grants, phải phân tích thêm **person ID, relationship và privilege escalation paths**.

### 20.3. Policy-as-code cho SoD

Một policy mô tả logic có thể như sau (không phải cấu hình trực tiếp của KMS cụ thể):

~~~yaml
policy: cryptographic-key-separation-of-duties
version: 1
scope:
  environments: [production]
  keyCategories: [KEK, DEK, SIGNING, HMAC, RECOVERY]
conflictingRoles:
  - [KEY_POLICY_ADMIN, PRIVILEGED_DECRYPTOR]
  - [AUDIT_LOG_ADMIN, CRYPTO_OPERATOR]
  - [CA_ISSUER_ADMIN, TRUST_ROOT_ADMIN]
approvalRules:
  changeKeyPolicy:
    minimumIndependentApprovers: 1
    disallowRequesterApproval: true
  destroyKeyMaterial:
    minimumIndependentApprovers: 2
    requireDependencyClearance: true
    requireProviderDestructionEvidence: true
  emergencySuspend:
    allowAuthorizedResponder: true
    requireIncidentId: true
    requirePostIncidentReview: true
security:
  enforceEffectivePermissions: true
  requirePersonIdentity: true
  requireApprovalBoundToChangeDigest: true
  allowAutomaticPermanentDestroy: false
audit:
  separateAuditAdministration: true
  logSecretMaterial: false
~~~

**Cảnh báo:** file YAML chỉ diễn đạt policy; hệ thống vẫn cần **enforcement thực tế** tại IAM, workflow, KMS/HSM, source control và ứng dụng. Không báo compliance chỉ vì file policy tồn tại.

## 21. Kiểm thử SoD và các đường vượt kiểm soát

| Tình huống kiểm thử | Kết quả kỳ vọng |
|---|---|
| Developer xin GenerateKey trong scope của mình | Được xử lý theo workflow, không tự cấp mọi key usage |
| Người yêu cầu tự duyệt bằng cùng account | Bị từ chối |
| Người yêu cầu dùng tài khoản thứ hai cùng personId để duyệt | Bị từ chối |
| Hai approvers thuộc hai person IDs hợp lệ duyệt Destroy | Vượt bước SoD, **chưa tự đủ điều kiện Destroy** |
| Approval gắn với key v1 bị dùng cho v2 | Từ chối |
| Request content đổi sau approval | Approval mất hiệu lực |
| Approver mất role trước khi thực thi | Đánh giá lại theo policy |
| Key operator có ChangeKeyPolicy nhưng không Decrypt | Không thể tự mở quyền Decrypt cho mình |
| IAM admin có thể tự AssumeRole Decryptor | Phát hiện đường tự nâng quyền và chặn |
| App chỉ có Encrypt thử gọi ScheduleDelete | Bị KMS/IAM từ chối và có audit |
| Signing service ký nội dung không có business approval | Bị từ chối ở application workflow |
| Approver tự sửa audit evidence | Không có quyền, phát cảnh báo |
| HSM recovery cần quorum | Thiếu quorum không cho recovery |
| Một người sở hữu nhiều recovery shares trái policy | Finding và yêu cầu phân phối lại |
| Service account không có accountable owner | Finding, không coi robot là owner lâu dài |
| CI sửa key policy và tự merge | Branch protection/approval phải chặn |
| Production KEK được gọi từ staging principal | Bị policy từ chối |
| Rotate KEK, có encrypted DEK trong backup | Không cho Destroy sớm |
| Revoke signing key nhưng verifier vẫn cache public key | Báo propagation chưa hoàn tất |
| Break-glass suspend từ authorized responder | Chỉ chặn scope được phép, audit và hậu kiểm |
| Break-glass cố ExportKey hoặc Destroy ngoài policy | Bị từ chối |
| Hai workflow cùng sửa key version | CAS/revision ngăn stale operation |
| Provider API thất bại giữa workflow | Không gắn COMPLETED khi chưa readback |
| Auditor chạy review | Đọc được metadata, không có plaintext secret |
| Thay người/nhóm giữ quyền | Thu hồi quyền cũ và tái chứng thực role conflicts |

Cần kiểm thử **negative permissions**, tức là chứng minh người **không được** phép thực hiện thao tác nguy hiểm **thực sự bị từ chối** ở IAM/KMS/HSM, chứ không chỉ kiểm tra UI không hiển thị nút.

## 22. Case study: nền tảng hóa đơn dùng KMS và chữ ký số

Một nền tảng Java lưu hóa đơn qua **AES-GCM DEK**, DEK được wrap bằng **KEK trong KMS**. Hóa đơn đã duyệt được ký bằng **private signing key trong HSM**. Tổ chức có ba nhóm:

- **Payments team:** quản lý nghiệp vụ, dữ liệu và yêu cầu.
- **Platform/Security:** vận hành KMS/HSM, IAM và lifecycle.
- **Audit/Compliance:** kiểm tra chứng cứ và thay đổi đặc quyền.

### 22.1. Thiết kế ban đầu nguy hiểm

Một quản trị viên có thể:

1. Tạo key mới.
2. Thêm quyền Decrypt/Sign cho tài khoản của mình.
3. Dùng quyền đó mở dữ liệu và ký chứng từ.
4. Sửa cấu hình verifier cho tin public key mới.
5. Xóa audit event trong cloud account.
6. Hủy KEK cũ mà không kiểm tra backups.

Dù AES-GCM, ECDSA và HSM đều hoạt động đúng về mặt thuật toán, **năng lực tấn công tập trung vào một tài khoản**.

### 22.2. Thiết kế lại với SoD

~~~mermaid
flowchart TD
    B["Business approver: chấp thuận giao dịch"] --> S["Signing workload: kiểm tra approval"]
    S --> H["HSM: Sign theo key usage"]
    D["Data owner: chính sách retention"] --> R["Rotation request"]
    R --> A["Security approver độc lập"]
    A --> K["KMS operator: rotate/rewrap"]
    K --> V["Data owner kiểm tra restore + dependencies"]
    V --> X["Destruction approval độc lập"]
    IAM["IAM admin: quyền tối thiểu"] --> K
    IAM --> S
    AUD["Audit riêng: theo dõi sự kiện"] --> L["Bằng chứng KMS/HSM/workflow"]
    H --> L
    K --> L
~~~

Những thay đổi cụ thể:

- **Business approval** được gắn với hash/nội dung của hóa đơn; signer chỉ ký sau khi kiểm tra approval.
- **Key operator** không có quyền Decrypt dữ liệu sản xuất nếu không cần.
- **Key-policy changes** được review bởi approver không phải requester.
- **Rotation KEK** có owner, migration và kiểm tra encrypted DEK/backups.
- **Public trust/JWKS** được phân phối qua pipeline có phê duyệt riêng.
- **Audit logs** gửi về miền quyền độc lập, không cho operator xóa.
- **Break-glass** chỉ dùng ngăn khẩn, có TTL, audit và hậu kiểm.

### 22.3. Khi phát hiện account signer bị chiếm

1. Incident responder dùng quyền tạm thời để **cô lập signer và chặn Sign**.
2. Security và key owner xác định private key có bị export không, signer đã ký nội dung gì.
3. Sinh signing key mới bằng HSM và phê duyệt kích hoạt.
4. PKI/trust owner cập nhật verifier, JWKS/cache và chính sách thu hồi.
5. Data/application owner rà soát các hóa đơn liên quan, không mặc nhiên coi chữ ký hợp lệ là được duyệt.
6. Auditor xác nhận đường signer cũ đã bị chặn, audit đầy đủ và các ngoại lệ còn lại có owner.

**Bài học:** SoD không làm thay công việc ứng phó sự cố; nó giúp giảm thiệt hại từ một account bị chiếm và bảo đảm thay đổi quyền/trust có người kiểm tra độc lập.

## 23. Theo dõi hiệu lực SoD bằng chỉ số vận hành

| Chỉ số | Cách đo | Mục đích |
|---|---|---|
| **Open SoD conflicts** | Số xung đột quyền còn tồn tại | Xác định diện rủi ro chưa giải quyết |
| **High-risk toxic combinations** | Cặp quyền PolicyAdmin+Decryptor, Destroy+Approver... | Ưu tiên xử lý đường lạm dụng |
| **Self-approval attempts** | Request bị từ chối do requester=approver | Giám sát hành vi sai/quy trình lỗi |
| **Effective-permissions coverage** | Principal được đánh giá / principal thuộc scope | Tránh báo sạch vì bỏ sót IAM |
| **Privileged access duration** | Thời gian tồn tại JIT/break-glass privileges | Giảm quyền đặc biệt tồn tại lâu |
| **Unreviewed break-glass uses** | Số event khẩn chưa hậu kiểm | Phát hiện lỗ hổng governance |
| **Independent approval validity** | Tỷ lệ approval đúng actor, scope, digest, TTL | Chất lượng maker-checker |
| **Audit integrity coverage** | Tỷ lệ KMS/HSM events được đẩy tới audit độc lập | Giảm nguy cơ che dấu |
| **Owner attestation freshness** | Key owners còn hoạt động và xác minh đúng hạn | Không để keys vô chủ |
| **Destruction dependency clearance** | Tỷ lệ destructive requests có bằng chứng backup/DEK checks | Hạn nguy cơ mất dữ liệu |
| **Negative IAM test pass rate** | Tỷ lệ các hành động không được phép thực sự bị từ chối | Kiểm chứng enforcement |

**Không chỉ tối ưu số lượng approval**. Nhiều yêu cầu được duyệt nhanh nhưng cả approver và requester cùng một người là vi phạm SoD. Một policy nghiêm nhưng có nhiều **backdoor IAM** cũng không hiệu quả.

### 23.1. Tái chứng thực định kỳ

Khi nhân viên nghỉ việc, chuyển team, service bị ngừng hoặc có role mới, cần rà soát **group memberships, service principals, HSM operator roles, recovery custodians, emergency accounts và policy exceptions**.

SoD là kiểm soát **liên tục**, không phải một lần điền RACI rồi để nguyên nhiều năm.

## 24. Ngoại lệ khi tổ chức nhỏ và nguy cơ thông đồng

Một tổ chức nhỏ có thể không đủ nhân sự để tách mọi role. Điều đó không nên dẫn tới giả vờ “hai accounts là hai người độc lập”.

**Kiểm soát bù trừ** có thể gồm:

- Sử dụng **managed KMS/HSM** với key origin, non-exportability và audit độc lập.
- Thực hiện review **bởi người ngoài quy trình** định kỳ thay vì tự kiểm tra.
- Giới hạn **JIT privileges**, MFA và ghi lại session quản trị.
- Tự động hóa **policy-as-code negative tests** và cảnh báo tăng quyền.
- Tách **audit sink** sang account/hệ thống do một chủ thể khác quản lý.
- Bảo vệ **destructive actions** bằng phê duyệt từ business/data owner ngoài đội vận hành.
- Đặt **time-bound risk exceptions** với owner, hạn hết hiệu lực và kế hoạch cải thiện.

Tuy nhiên, **compensating controls không biến một người thành hai chủ thể độc lập**. Cần ghi rõ **rủi ro còn lại và người chấp nhận**, không khai rằng một biện pháp tương đương hoàn toàn khi nó không ngăn được gian lận có chủ ý.

### 24.1. Cẩn trọng với collusion

Hai người cùng thông đồng vẫn có thể phê duyệt hành động gian lận. Một số kiểm soát bổ sung gồm **quorum lớn hơn, rotation of approvers, independent auditing, limit/rate controls, alerting bất thường, HSM non-exportability** và dữ liệu chứng cứ khó sửa đổi. Không có một số lượng approver cố định nào đảm bảo không thể bị thông đồng.

## 25. Câu hỏi tự kiểm tra

**Câu 1. Separation of duties giải quyết vấn đề gì?**

**Trả lời:** Ngăn một chủ thể đơn lẻ có đủ quyền để thực hiện trọn chuỗi thao tác nhạy cảm mà không có kiểm soát độc lập, ví dụ thay key policy rồi tự giải mã dữ liệu và xóa audit.

**Câu 2. SoD có giống least privilege không?**

**Trả lời:** Không. Least privilege giới hạn lượng quyền của mỗi chủ thể; SoD phân tách những nhiệm vụ không nên do cùng chủ thể kiểm soát. Hai nguyên tắc bổ sung cho nhau.

**Câu 3. Dual control và split knowledge khác nhau như thế nào?**

**Trả lời:** Dual control yêu cầu nhiều chủ thể tham gia/duyệt một thao tác; split knowledge chia bí mật hoặc thông tin để một người không giữ toàn bộ. Một approval quorum không mặc nhiên là secret sharing.

**Câu 4. Tại sao KeyPolicyAdmin và Decryptor không nên cùng thuộc một principal?**

**Trả lời:** Người đó có thể tự mở quyền giải mã rồi dùng quyền, khó kiểm soát mục đích. Phải tách policy control và data-plane usage hoặc có kiểm soát bù trừ rõ ràng.

**Câu 5. Hai tài khoản khác nhau cùng thuộc một người có đủ dual control không?**

**Trả lời:** Không nếu chính sách yêu cầu hai người độc lập. Workflow phải kiểm tra identity của người thật và ngăn self-approval qua tài khoản thứ hai.

**Câu 6. Vì sao signing key trong HSM vẫn cần business approval?**

**Trả lời:** HSM có thể ký hợp lệ bất kỳ nội dung mà principal được quyền gửi. Chữ ký hợp lệ về mật mã không chứng minh nội dung đã được nghiệp vụ phê duyệt.

**Câu 7. Người vận hành KMS có bắt buộc là owner khóa không?**

**Trả lời:** Không. Operator chịu trách nhiệm vận hành, owner chịu trách nhiệm purpose, cryptoperiod, phạm vi dữ liệu và quyết định lifecycle.

**Câu 8. Tại sao chỉ hai người bấm nút DeleteKey chưa đủ an toàn?**

**Trả lời:** Còn phải có bằng chứng encrypted DEK/backup/retention đã được xử lý và provider thực sự xác nhận hủy. Hai approval không thay dependency check.

**Câu 9. Có nên chờ đủ hai approver mới được chặn khóa đang bị lạm dụng không?**

**Trả lời:** Không nhất thiết. Break-glass có thể cho incident responder chặn kịp thời theo quyền giới hạn, với audit và hậu kiểm.

**Câu 10. Static SoD và dynamic SoD khác gì?**

**Trả lời:** Static SoD không cho cùng chủ thể sở hữu đồng thời các roles xung đột; dynamic SoD ngăn cùng chủ thể thực hiện các chức năng xung đột trong một operation hoặc phiên cụ thể.

**Câu 11. Owner tag trên KMS có đủ thay RACI và IAM enforcement không?**

**Trả lời:** Không. Tag là metadata cần xác minh, còn RACI xác định trách nhiệm và IAM/KMS mới thực thi quyền.

**Câu 12. Nếu một người có thể sửa IAM rồi tự gán Decrypt, có SoD conflict không?**

**Trả lời:** Có. Phải đánh giá quyền có hiệu lực và đường tự nâng quyền, không chỉ quyền Decrypt trực tiếp.

**Câu 13. Vì sao auditor không nên quản lý và xóa logs mà mình đang kiểm tra?**

**Trả lời:** Điều đó làm mất tính độc lập và tạo khả năng che giấu sự cố. Audit nên có ranh giới quyền riêng và bảo vệ chống sửa/xóa trái phép.

**Câu 14. Split knowledge 3-of-5 có tự ngăn lộ bí mật không?**

**Trả lời:** Không tuyệt đối. Còn phụ thuộc cách bảo vệ/phân phối shares, môi trường khôi phục, việc một người có giữ nhiều shares hay không và khả năng thông đồng.

**Câu 15. SoD có giúp sửa lỗi tái sử dụng AES-GCM nonce không?**

**Trả lời:** Không trực tiếp. Cần kiểm soát nonce uniqueness theo DEK; SoD hỗ trợ quản trị việc triển khai, review và ứng phó khi lỗi được phát hiện.

## 26. Checklist áp dụng vào hệ thống quản lý khóa

Trước khi kết luận một kiến trúc quản lý khóa đã có SoD thích hợp, xác nhận:

- **Asset scope:** DEK, KEK, HMAC/PSK, signing key, CA key, recovery key và key versions đã được kiểm kê?
- **Ownership:** accountable key owner, data owner, custodian, consumer và auditor có được xác minh?
- **RACI:** người yêu cầu, người duyệt, người thực thi và người xác nhận đã được phân định cho từng giai đoạn?
- **Static SoD:** có chặn cặp role xung đột như ChangePolicy+Decrypt, ChangeAudit+CryptoOperations, ApproveDestroy+Destroy?
- **Dynamic SoD:** requester không tự duyệt cùng operation, kể cả khi có nhiều accounts?
- **Effective permissions:** có đánh giá quyền kế thừa, grants, role assumption và self-privilege escalation?
- **Dual control:** hành động high-risk có approval/quorum phù hợp, binding tới key ID/version và payload?
- **Split knowledge:** nếu dùng recovery shares, có bảo vệ độc lập, ngưỡng đúng, quy trình recovery và diễn tập?
- **Generate/provision:** có kiểm tra algorithm, entropy/CSPRNG, export policy, owner và Activate approval?
- **KMS/HSM:** key admins tách crypto users, provider thật sự thực thi restrictions và audit?
- **Envelope encryption:** KEK/DEK usage, IAM, tenant authorization, nonce uniqueness và backup được quản lý?
- **Signing:** business approval, private-key Sign, PKI/trust distribution và verifier độc lập?
- **Rotation:** key mới thật sự, consumer cutover, encrypted DEK rewrap hoặc dữ liệu re-encrypt khi cần?
- **Revocation/destruction:** có emergency containment, dependency clearance, independent approval và provider readback?
- **Automation:** CI/CD, IaC, service accounts và staging không thể tự cấp quyền production?
- **Break-glass:** danh tính mạnh, JIT/TTL, scope giới hạn, audit và hậu kiểm?
- **Audit:** logs độc lập, chống sửa đổi, chứa actor/approver/key ID/version/evidence nhưng không chứa secret?
- **Verification:** có negative IAM tests, maker-checker tests, kiểm tra cache/trust, restore drills, race conditions?
- **Exceptions:** mọi trường hợp không thể phân tách hoàn toàn có owner, thời hạn, compensating controls và residual risk?

**Ghi nhớ:** **Separation of duties** không thay thuật toán AES, RSA, chữ ký số hoặc tính năng KMS/HSM. Nó là **cấu trúc trách nhiệm và quyền kiểm soát** bảo đảm không ai có thể tự tạo, phê duyệt, dùng sai, thu hồi hoặc hủy khóa quan trọng mà thiếu rào chắn độc lập. Khi kết hợp **least privilege, dual control, split knowledge khi phù hợp, IAM/RBAC/ABAC, key lifecycle, DEK/KEK, envelope encryption, PKI, audit và emergency break-glass**, SoD giúp giảm nguy cơ lạm dụng và sai sót trong cả vòng đời khóa.

