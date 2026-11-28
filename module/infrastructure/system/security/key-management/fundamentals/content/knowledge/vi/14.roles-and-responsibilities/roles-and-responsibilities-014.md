# Thu hồi quyền của nhân sự rời tổ chức: Offboarding an toàn trong quản lý khóa mật mã

Một kỹ sư phụ trách nền tảng thanh toán chuẩn bị rời tổ chức. Tài khoản SSO của người đó được vô hiệu hóa đúng thời điểm, nhưng họ từng có quyền **KMS Decrypt**, quản trị một **HSM partition**, sử dụng **break-glass account**, đọc secret trong CI/CD, và từng tải một bản **private signing key** dùng trong hệ thống cũ. Liệu chỉ khóa tài khoản SSO đã đủ để bảo vệ khóa mật mã?

**Chưa đủ.** Khóa SSO có thể ngăn những phiên đăng nhập mới qua nhà cung cấp danh tính, nhưng **token hiện còn hiệu lực, phiên đã mở, credential độc lập, quyền cấp gián tiếp, bản sao key material, tài khoản chia sẻ và các hệ thống ngoài SSO** có thể vẫn sử dụng được. Một phần dữ liệu đã bị sao chép trước đó cũng không thể “thu hồi” chỉ bằng thay đổi IAM.

**Thu hồi quyền của nhân sự rời tổ chức** (*leaver offboarding*) là một quy trình có kiểm soát nhằm **chấm dứt kịp thời các khả năng truy cập và sử dụng tài nguyên**, bảo vệ bí mật từng nằm trong tầm kiểm soát của người rời đi, **chuyển giao quyền sở hữu/khả năng vận hành hợp pháp** và giữ bằng chứng kiểm toán. Đối với key management, cần giải quyết đồng thời **quyền truy cập**, **key material đã xuất**, **quyền sử dụng API mật mã**, **quyền quản trị chính sách**, **quy trình khôi phục** và **vòng đời khóa**.

Trong chương **Vai trò và trách nhiệm** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, nội dung kết nối nghiệp vụ nhân sự với hệ thống mật mã: AES-GCM, HMAC, RSA/Ed25519, chữ ký số, KMS/HSM, envelope encryption, key inventory, phân quyền, xoay vòng, thu hồi và hủy khóa. Mục tiêu không phải tự động xóa mọi khóa liên quan đến nhân sự, mà là **loại bỏ năng lực truy cập trái phép trong khi giữ an toàn và khả năng khôi phục của dịch vụ**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **disable identity**, **revoke session/token**, **revoke IAM grant**, **rotate credential/key**, **retire/destroy key** và **xử lý bản sao đã lộ**.
2. Kiểm kê quyền **trực tiếp, kế thừa, tạm thời, bên ngoài SSO, qua tài khoản chia sẻ và machine identity** liên quan đến người rời tổ chức.
3. Phối hợp **HR, quản lý trực tiếp, Key owner, Security administrator, IAM operator, KMS/HSM custodian, SOC và auditor** bằng RACI, mốc hiệu lực và bằng chứng.
4. Thiết kế quy trình **trước thời điểm nghỉ, tại thời điểm cắt quyền, sau nghỉ và điều tra ngoại lệ**, bao gồm nhân sự đột xuất.
5. Đánh giá khi nào cần **rotate API key, password, HMAC secret, KEK, DEK, private signing key hoặc HSM recovery share** thay vì chỉ xóa role.
6. Kiểm thử khả năng truy cập bị từ chối thực tế, kiểm soát **token/cache/propagation**, và giữ key lifecycle không bị đứt gãy.
7. Viết mô hình **offboarding policy** bằng Java 17 để sinh nhiệm vụ và phát hiện thiếu phê duyệt/bằng chứng, đồng thời nhận diện giới hạn của mô hình.

## 2. Phạm vi: Người rời đi có thể còn giữ những khả năng nào?

Từ góc độ an ninh, **quyền không chỉ là một role xuất hiện trong màn hình IAM**. Người rời tổ chức có thể có nhiều loại *capability* ở các tầng khác nhau.

| Nhóm quyền/tài sản | Ví dụ | Điều phải xác minh khi offboarding |
|---|---|---|
| **Danh tính gốc** | SSO, IdP, directory account, VPN, workstation | Identity bị disable, MFA recovery/re-enrollment bị kiểm soát, thiết bị/sessions được xử lý |
| **Cloud/KMS IAM** | KMS Encrypt, Decrypt, Sign, CreateGrant, PutKeyPolicy, DisableKey | Direct/indirect grants, group memberships, role assumptions và quyền ở mọi account/project/region |
| **HSM administration** | Security Officer, Crypto Officer, HSM partition admin | Slot/partition rights, PIN/token, quorum, recovery roles và session mở |
| **Ứng dụng/quản trị** | Key inventory, secret vault, CI/CD, Git, deployment dashboard | Quyền xem secret, thay policy/alias, chạy pipeline, cấp quyền cho người khác |
| **Token/credential** | API key, SSH key, PAT, OAuth refresh token, service token | Revoke token, rotate shared secret, xóa trust của public SSH key, cắt quyền cấp lại |
| **Key material xuất được** | PEM private key, plaintext DEK, HMAC key, KDF root | Khả năng đã có bản sao ngoài hệ thống; đánh giá thay vật liệu và phạm vi ảnh hưởng |
| **Tài khoản dùng chung** | Emergency/break-glass, operator account, shared automation | Thay secret/thiết bị xác thực, loại khỏi quorum, bảo đảm người cũ không còn khả năng dùng |
| **Machine identity liên quan** | Bot/service account do nhân sự tạo, CI deploy token, app registration | Chuyển owner, đánh giá credential/cert và grants; không vô hiệu tùy tiện workload đang chạy |
| **Backup/recovery** | Recovery key, HSM share, escrow, offline vault, DR instructions | Thay quyền và vật liệu recovery khi có rủi ro; duy trì khả năng khôi phục |
| **Bên thứ ba và offline** | SaaS, Git mirror, partner portal, exported certificate/private key | Thu hồi tại provider/đối tác; bản copy offline không thể bị xóa bằng SSO |

### 2.1. Những gì một lệnh disable SSO thường không giải quyết

~~~text
Disable SSO account
    |
    +-- Có thể ngăn login mới qua IdP
    |
    +-- Không mặc nhiên thu hồi mọi access token/JWT đang còn hạn
    +-- Không mặc nhiên xóa API key, PAT, SSH private key đã cấp
    +-- Không mặc nhiên chấm dứt HSM session/credential độc lập
    +-- Không mặc nhiên xóa DEK/HMAC/private key đã sao chép
    +-- Không tự cập nhật policy ở SaaS/KMS tenant nằm ngoài federation
    +-- Không tự chuyển quyền sở hữu service account hoặc khóa sản xuất
~~~

Tác động thật của **disable**, **revoke** và **logout** phụ thuộc **IdP, federation, token semantics, session lifetime và provider API**. Không tuyên bố đã cắt toàn bộ truy cập nếu mới chỉ thấy một thuộc tính account.enabled=false.

### 2.2. Quyền và bản sao bí mật khác nhau

Một người có quyền **KMS Decrypt** nhưng không thể xuất KEK vẫn có thể **lạm dụng API** để nhận plaintext hoặc DEK nếu policy quá rộng. Thu hồi grant và credential làm giảm năng lực gọi API trong tương lai; nó **không thu hồi plaintext đã đọc**.

Một người từng tải **private signing key PEM** có thể ký offline bằng bản sao đó sau khi mọi tài khoản tổ chức bị tắt. Khi có căn cứ key material đã bị sao chép hoặc không còn đáng tin, cần đánh giá **rotate, revoke trust, thay DEK và re-encrypt** tương ứng; chỉ tắt IAM không giải quyết bản sao.

Ngược lại, **không cần hủy một KEK production chỉ vì nhân sự từng có quyền xem key ID và metadata**, nếu họ không có đường tiếp cận bí mật và các quyền sử dụng đã được thu hồi hiệu quả. Quyết định phải dựa trên **threat model và bằng chứng**, không phải một quy tắc hủy khóa thiếu phân loại.

## 3. Các khái niệm thu hồi cần phân biệt

| Thao tác | Bề mặt tác động | Điều không thể kết luận |
|---|---|---|
| **Disable/delete user identity** | Đăng nhập và danh tính ở IdP/directory theo provider | Mọi phiên/token và tất cả hệ thống đã bị vô hiệu tức thì |
| **Remove IAM role/group/grant** | Chính sách cho các request mới qua enforcement point | Secret đã xuất, credential offline hoặc role assumption đang sống bị xóa |
| **Revoke refresh token/session** | Khả năng tiếp tục hoặc làm mới phiên theo provider | Một JWT access token đã phát sẽ bị tất cả verifier offline từ chối ngay |
| **Rotate shared credential** | Mật khẩu/API key/token mới thay thế giá trị cũ | Bản cũ tự mất hiệu lực nếu bên nhận vẫn chấp nhận nó |
| **Disable/Suspend KMS key** | Crypto operation qua KMS theo chính sách/sản phẩm | Private key/DEK đã export bị xóa; mọi ciphertext cũ đều không đọc được |
| **Rotate KEK** | Tạo/chuyển KEK mới; có thể rewrap DEK | DEK đã bị lộ trở nên an toàn trở lại |
| **Rotate DEK** | Thay key mã hóa dữ liệu; cần re-encrypt nếu chuyển dữ liệu cũ | Bản mã trước đây bị đối thủ thu thập tự động hết rủi ro |
| **Rotate/revoke signing key** | Thay private key và cập nhật public-key trust/JWKS/certificate | Chữ ký lịch sử tự mất hiệu lực toán học |
| **Destroy key material** | Hủy trong ranh giới xác định theo provider | Đã hủy mọi bản sao, backup, cache và đường tái dẫn xuất |
| **Disable user-owned service account** | Các tác vụ dùng account có thể dừng | Phù hợp nếu bot vẫn đang phục vụ production |

**Nguyên tắc:** Offboarding ưu tiên **thu hồi năng lực của người rời tổ chức**; thay đổi vòng đời key material là quyết định riêng dựa trên **exposure, tính tin cậy và khả năng duy trì dịch vụ**.

## 4. Vai trò và trách nhiệm trong quy trình leaver

Tổ chức cần mô tả **ai báo sự kiện nhân sự, ai đánh giá quyền, ai thu hồi, ai duyệt rotation và ai xác minh độc lập**. Một tài khoản quản trị có thể thực hiện kỹ thuật nhiều bước, nhưng không nên có khả năng **tự phê duyệt và xóa audit của chính mình**.

### 4.1. Bảng phân công tham khảo

| Vai trò | Trách nhiệm | Không nên làm mặc định |
|---|---|---|
| **HR/People Operations** | Xác nhận sự kiện leaver, thời điểm hiệu lực, loại hợp đồng và yêu cầu pháp lý | Cấp quyền KMS hoặc đánh giá crypto exposure một mình |
| **Line manager** | Liệt kê dự án, bàn giao tài sản, đề cử owner thay thế, xác nhận dịch vụ phụ thuộc | Giữ account nhân sự để chạy bot hoặc tiếp tục truy cập sau thời điểm cắt |
| **Security administrator** | Đánh giá blast radius, chính sách IAM/KMS/HSM, scope và phối hợp thu hồi | Mặc nhiên tự Decrypt/Sign hoặc tự approve quyền rủi ro cao |
| **IAM/IdP operator** | Disable identity, revoke phiên/token và quyền định danh | Kết luận tất cả credential ngoài IdP đã bị thu hồi |
| **Key owner** | Xác định material có exposure không, phê duyệt rotate/re-encrypt theo dependency | Hủy khóa ảnh hưởng dữ liệu mà chưa kiểm tra khôi phục |
| **KMS/HSM custodian/operator** | Revoke grants/partition memberships, xử lý key/custodian/quorum theo policy | Xuất raw root/KEK/private key ngoài vùng kiểm soát |
| **Application/service owner** | Chuyển machine identity ownership, rotate credential và kiểm thử workload | Để người rời tổ chức tiếp tục sở hữu pipeline/deploy bot |
| **SOC/Incident responder** | Điều tra nguy cơ lộ khóa, phiên bất thường và hành động khẩn cấp | Dùng ticket/leaver process để che dấu một incident compromise |
| **Independent auditor** | Đối soát bằng chứng, exception, thời điểm cắt quyền và test từ chối | Tự sửa quyền hay nhật ký đang kiểm toán |

### 4.2. RACI minh họa

**R:** thực hiện; **A:** chịu trách nhiệm quyết định; **C:** được tham vấn; **I:** được thông báo. Viết tắt **HR**, **LM** (line manager), **SA** (Security administrator), **IAM**, **KO** (Key owner), **OP** (KMS/HSM operator), **AU** (Auditor).

| Công việc | HR | LM | SA | IAM | KO | OP | AU |
|---|---|---|---|---|---|---|---|
| Xác nhận thời điểm leaver và thông tin đầu vào | **A/R** | C | I | I | I | I | I |
| Kiểm kê quyền và secret exposure | I | R | **A/R** | R | C | R | I |
| Disable identity, revoke sessions và IAM | I | I | **A** | **R** | C | R | I |
| Thu hồi HSM custodian/quorum/admin role | I | I | **A** | C | C | **R** | I |
| Chuyển service account, key ownership | I | **A** | C | R | **R** | C | I |
| Quyết định rotate key material có nguy cơ lộ | I | C | **R** | C | **A** | R | I |
| Phê duyệt hủy khóa / crypto-erasure | I | C | **R** | I | **A** | R | C |
| Kiểm tra không còn quyền và đối soát evidence | I | C | R | R | C | C | **A/R** |

Ma trận chỉ là **mẫu tham khảo**, không phải chuẩn bắt buộc. Với thao tác rủi ro cao như hủy root KEK hoặc xuất recovery material, có thể cần **dual control/two-person approval, Legal/Compliance hoặc custodian quorum** theo chính sách. RACI phải ánh xạ thành danh tính thật và provider permissions, không chỉ ghi trong tài liệu.

## 5. Phân loại ca rời tổ chức và thời điểm cắt quyền

Không nên áp cùng lịch trình cho mọi ca:

| Trường hợp | Mục tiêu xử lý | Lưu ý |
|---|---|---|
| **Nghỉ có kế hoạch** | Chuẩn bị inventory, chuyển ownership và đặt thời điểm cắt quyền chính xác | Không cắt quyền trước thời điểm hợp lệ khi chưa có lý do/phê duyệt |
| **Chấm dứt đột xuất/rủi ro cao** | Điều phối HR–Security–IAM cắt quyền đồng thời theo mốc đã được phê duyệt | Tập trung ngăn việc cấp lại token, revoke phiên và credential độc lập |
| **Kết thúc hợp đồng nhà thầu** | Thu hồi cả danh tính và truy cập qua nhà cung cấp/đối tác | Kiểm tra SaaS, VPN, khóa SSH, cloud external identity |
| **Chuyển phòng ban/quyền** | Thu hồi quyền cũ theo policy, chỉ cấp quyền mới phù hợp | Không giữ mọi quyền chỉ vì người đó vẫn làm trong công ty |
| **Tạm nghỉ/đình chỉ truy cập** | Tạm vô hiệu theo chính sách, có điều kiện khôi phục | Phân biệt suspension với leaver vĩnh viễn và key destruction |
| **Người giữ HSM share/quorum rời đi** | Đảm bảo quorum/recovery không còn phụ thuộc người cũ | Thay người giữ share theo quy trình thiết bị có chứng cứ |

**Mốc thu hồi phải dựa trên sự kiện nhân sự đã được xác thực và chính sách áp dụng**, tránh suy đoán ý định từ email chưa chính thức. Không cần đưa quy định pháp luật cụ thể vào thuật toán; HR/Legal quyết định quyền lợi, bảo quản hồ sơ và thời điểm thực thi theo bối cảnh thực.

### 5.1. Một timeline vận hành

~~~mermaid
flowchart LR
    A["T-: HR xác nhận leaver + effective time"] --> B["T-: Inventory quyền, owner, secret exposure"]
    B --> C["T-: Kế hoạch cắt quyền + phương án continuity"]
    C --> D["T0: Disable identity và revoke grants/sessions"]
    D --> E["T0+: Rotate shared/compromised credentials theo rủi ro"]
    E --> F["T0+: Negative tests + audit evidence"]
    F --> G["T+: Đối soát, xử lý exception, bàn giao hoàn tất"]
~~~

Trong sơ đồ, **T0** là thời điểm hiệu lực theo sự kiện HR/decision được phê duyệt, không mặc định là nửa đêm hoặc ngày nhân sự gửi đơn. Với leaver rủi ro cao, những bước chuẩn bị có thể diễn ra bí mật trong nhóm có thẩm quyền; với leaver thông thường, hoạt động bàn giao được phối hợp trước T0.

### 5.2. Không dùng số giờ cố định như một bảo đảm toàn cục

Một tổ chức có thể đặt **SLA** hoặc thời hạn tối đa cho từng nhóm hệ thống, nhưng **không có một số phút hợp lệ cho mọi provider/session**. Token có TTL dài, offline verifier, HSM partition ngoài federation hoặc SaaS khó tích hợp có thể khiến khả năng truy cập còn sau một thao tác disable. SLA cần có:

- **Thời điểm hiệu lực** được xác thực và đồng bộ.
- **Mức ưu tiên theo rủi ro** (KMS admin, HSM officer, secret export, signing key, DEK cache).
- **Bằng chứng trạng thái ở data plane**, không chỉ sự kiện gửi lệnh.
- **Ngoại lệ tồn đọng** có owner, lý do, thời hạn và biện pháp giảm thiểu.

Offboarding chỉ được gọi là hoàn tất khi các nghĩa vụ đã được kiểm tra, hoặc **ngoại lệ được quản lý minh bạch**; không đổi ticket sang Done chỉ vì một API trả mã 200.

## 6. Runbook từng bước: Từ thông báo HR đến xác minh hoàn tất

### 6.1. Giai đoạn chuẩn bị: Xây bản đồ quyền và phụ thuộc

Trước T0, Security administrator hoặc quy trình identity governance cần liên kết **person ID được HR xác nhận** với **identity và capability** thực tế:

1. **Xác định định danh:** employee/contractor ID, IdP account, external identities, privileged identity, cloud identities, email và tên đăng nhập cũ; đối chiếu chắc chắn để không cắt nhầm người trùng tên.
2. **Tìm quyền trực tiếp:** IAM bindings, KMS key policy/grants, HSM role, vault ACL, secret read/export permission, PKI enrollment, CI/CD role, Git admin và cloud access.
3. **Tìm quyền kế thừa:** nhóm directory, nested groups, federated roles, permission sets, session policy, sudo/PAM, workspace và quyền được cấp từ dự án.
4. **Tìm credential độc lập:** PAT, SSH keys, API tokens, mTLS client certificates, TOTP/recovery codes, hardware tokens, app passwords và khóa truy cập đối tác.
5. **Tìm secret từng tiếp cận:** root/KEK, DEK export, HMAC key, private signing key, KDF root, CI secret, HSM recovery/backup share; phân biệt **có quyền sử dụng** với **đã nhìn thấy raw material**.
6. **Tìm machine identities và tài sản phụ thuộc:** service account, bot, pipeline, certificate owner, webhook, HSM custodian role và dự án không còn owner khác.
7. **Gán trách nhiệm:** mỗi tài sản có hệ thống thực thi, người triển khai revoke, key owner, thời điểm mục tiêu và điều kiện kiểm chứng.

**Không kết luận một secret đã bị lấy cắp chỉ vì người đó có quyền truy cập.** Cần xem **exportability, audit, thời gian truy cập, môi trường, policy và dấu hiệu sự cố**. Nhưng với secret **đã được chia sẻ như mật khẩu chung hoặc recovery code**, không thể thu hồi “kiến thức” của người cũ; phải đánh giá thay giá trị và cắt khả năng dùng bản cũ.

### 6.2. Lập kế hoạch continuity trước khi cắt

Nếu một nhân sự là **owner duy nhất của KMS key, CI/CD pipeline hoặc HSM quorum**, cắt tài khoản khi chưa chuyển giao có thể làm tổ chức không còn khả năng rotate/restore. Chuẩn bị:

- Một **Key owner** và **Technical owner** mới có quyền phù hợp; kiểm tra không vi phạm SoD.
- Danh mục **key ID/version, purpose, alias, environment, tenant, cryptoperiod và dependent datasets**.
- Quyền của automation được chuyển sang **machine identity do tổ chức quản lý**, không dùng tài khoản cá nhân để vận hành service.
- Kịch bản **rollover/rotation** nếu shared credential hay private key có exposure.
- HSM recovery quorum có đủ người độc lập, không phụ thuộc nhân sự sắp rời.
- Kế hoạch phối hợp **identity revocation** với **credential/key rotation**, tránh cửa sổ dùng song song không kiểm soát.

Chuyển ownership **không có nghĩa sao chép raw KEK/private key cho người mới**. Với KMS/HSM non-exportable, người mới nhận **quyền và trách nhiệm quản trị được phê duyệt**, còn key material giữ trong ranh giới ban đầu.

### 6.3. Tại T0: Cắt khả năng truy cập của người rời tổ chức

~~~mermaid
sequenceDiagram
    participant HR as HR authorized event
    participant Flow as Offboarding orchestrator
    participant IDP as IdP/Session service
    participant IAM as IAM/KMS/HSM
    participant APP as SaaS/Vault/CI/PKI
    participant Audit as Audit store
    HR->>Flow: Leaver(employeeId, effectiveAt, caseId)
    Flow->>Flow: Validate identity + scope + approvals
    Flow->>IDP: Disable sign-in, revoke session/refresh access
    IDP-->>Flow: Provider results + effective time
    Flow->>IAM: Revoke grants, privileged role, HSM memberships
    IAM-->>Flow: Provider results + remaining sessions
    Flow->>APP: Revoke PAT/SSH/cert, vault, CI and SaaS access
    APP-->>Flow: Revocation results or exceptions
    Flow->>Audit: Per-system actions, outcome, timestamp, evidence ref
    Flow-->>HR: Status: complete or open exceptions
~~~

**Quan trọng:** Sơ đồ chỉ thể hiện **các nhóm thao tác**. API thực tế có thể **không thu hồi được access token đã ký**, không lập tức kết thúc session HSM hoặc không quản lý được credential tại hệ thống bên thứ ba. Phải ghi nhận kết quả riêng từng hệ thống và cách giảm thiểu cửa sổ còn hiệu lực.

Đường cắt quyền thực tế bao gồm:

1. Disable **primary identity** và loại khỏi **nhóm/role còn quyền** theo IdP, cloud và hệ thống trong phạm vi.
2. Revoke **active sessions, refresh tokens, device grants, MFA enrollments, app passwords** theo khả năng IdP/provider.
3. Revoke **personal access tokens, API keys, SSH authorized keys, VPN/client certificates, cloud access keys** thuộc principal.
4. Revoke **KMS/HSM admin rights, grants, ability to modify key policy/alias, access to partitions/slots**; kiểm tra grant được tạo trực tiếp hay gián tiếp.
5. Cắt **CI/CD, source repositories, secret manager, backup console, SIEM, key inventory và provider portals**, gồm tài khoản ngoài SSO.
6. Xử lý **shared account/break-glass credential** mà người đó biết: thay credential, re-enroll yếu tố xác thực, phân phối cho người được phép mới, kiểm thử bản cũ bị từ chối.
7. Khóa hoặc thu hồi **thiết bị/agent** trong phạm vi chính sách; xử lý local credential, SSH agent, downloaded secret, VPN và nguồn cấp token.
8. Chuyển ownership của service/bot và certificate sang owner mới; **không disable bừa service account đang được production sử dụng**.

### 6.4. Sau T0: Verify khả năng truy cập thực, không chỉ cấu hình

Với từng hệ thống/role, phải có bằng chứng theo provider contract:

| Cần xác minh | Bằng chứng tốt hơn một checkbox |
|---|---|
| Đăng nhập mới bị chặn | IdP sign-in state và test được kiểm soát với test identity / kết quả deny |
| Token không thể làm mới | Refresh-token revocation result và TTL/introspection behavior |
| Session cũ không còn quyền | Provider session termination hoặc thời điểm hết hạn đã ghi nhận; kiểm tra state |
| KMS admin/Decrypt/Sign grants bị thu hồi | List policy/grants theo resource và **negative test** an toàn |
| HSM officer/custodian đã bị loại | Partition membership, session/token status và quorum review |
| PAT/API key/SSH key không còn được chấp nhận | Provider revoke result, resource denial và key inventory updated |
| Shared credential đã xoay vòng | Credential version mới được cấp cho principals hợp lệ; bản cũ bị vô hiệu |
| Service không bị gián đoạn | Synthetic tests với machine identity/owner mới, không dùng credential của leaver |
| Audit đầy đủ | Event IDs, actor, keyRef, effective timestamp, decision, exception record |

**Không yêu cầu người đã rời tổ chức đăng nhập lại để test**, không chia sẻ mật khẩu production để “thử có còn vào được không”. Dùng **provider-side evidence**, tài khoản thử có kiểm soát, session metadata hoặc phương pháp xác minh do IAM/Security chấp thuận. Cần bảo đảm người kiểm chứng không vô tình được cấp secret hoặc quyền quá rộng.

### 6.5. Ngoại lệ và điều kiện đóng hồ sơ

Mọi trường hợp không thể thu hồi tức thì phải ghi **exception ID**, hệ thống, key/credential reference, người chịu trách nhiệm, mức rủi ro, thời điểm dự kiến đóng, **compensating control** và kết quả giám sát. Ví dụ: một JWT access token tự chứa chưa hết hạn có thể vẫn được verifier offline chấp nhận; cần dựa vào TTL, danh sách deny/session version, thay trust khi có căn cứ và hạn chế truy cập ở resource layer tùy thiết kế.

**Không giữ toàn bộ ticket ở trạng thái Completed** nếu vẫn còn **unbounded privileged access** mà không có biện pháp giảm thiểu. Đồng thời không phá hủy khóa chỉ để có chỉ số “100% access revoked”. Hai nghĩa vụ **thu hồi người dùng** và **bảo đảm liên tục dữ liệu** phải được hoàn thành đúng ranh giới.

## 7. Từng loại credential và cách xử lý

### 7.1. SSO, OAuth/OIDC, JWT và các phiên đang sống

- **SSO/IdP:** disable user, loại khỏi groups và thu hồi phiên theo khả năng dịch vụ. Kiểm tra session ở ứng dụng không luôn là cùng session của IdP.
- **OAuth refresh token:** nhiều provider hỗ trợ thu hồi một token hoặc toàn bộ phiên; phải xem contract và delegated clients.
- **JWT access token:** nếu verifier chỉ kiểm chữ ký, audience, issuer và expiration **offline**, disable user ở IdP có thể **không** làm JWT hết hiệu lực tức thì. Cần TTL hợp lý, introspection/session revocation/version, resource-level authorization hoặc cơ chế denylist khi threat model yêu cầu.
- **OIDC/SAML federation:** ứng dụng có thể giữ session riêng dù IdP đã khóa; tích hợp logout, session termination và provisioning/deprovisioning theo công nghệ được hỗ trợ.
- **Temporary cloud credentials/assumed role:** thu hồi quyền cấp role mới chưa chắc chặn tất cả phiên đã phát; kiểm tra session revocation, explicit deny và TTL của nhà cung cấp.

**Không rotate toàn bộ JWT signing private key chỉ vì một nhân viên có session người dùng bị thu hồi.** Rotation của signing key là quyết định khác, phù hợp khi key material/signing capability bị ảnh hưởng. Nếu dùng thay signing key, phải phối hợp **JWKS/certificate, kid, caches, token validity, issuer trust** để không tạo gián đoạn hoặc chấp nhận token giả.

### 7.2. SSH keys, API keys, PAT và mTLS certificates

| Loại | Thu hồi ở đâu? | Kiểm tra |
|---|---|---|
| **SSH public key** | Authorized keys, Git host, bastion hoặc certificate authority/trust policy | Key không còn được chấp nhận ở mọi host/provider có liên quan |
| **SSH private key đã nằm ngoài tổ chức** | Không thể thu hồi bản sao bằng xóa file local | Loại public-key trust/credential; rotate hệ thống chia sẻ nếu cần |
| **PAT / personal API key** | Provider issuing token | Đã revoke cụ thể token, không chỉ disable SSO |
| **Shared API key** | Service nhận/xác thực khóa | Cấp khóa mới cho consumer hợp lệ rồi **vô hiệu khóa cũ** |
| **mTLS client certificate** | Certificate/identity trust service, gateway, PKI revocation | CRL/OCSP hoặc trust update theo hệ thống; xét cache/expiry |
| **Service certificate/key** | Workload và secret manager | Kiểm tra nó có phụ thuộc người rời không; chuyển owner/rotate khi cần |

**Certificate revocation không tự làm private key biến mất.** Những ứng dụng không kiểm tra certificate status có thể vẫn chấp nhận certificate cũ. Khi có nguy cơ, cần cập nhật trust và gateway/session policy, không chỉ phát CRL mà bỏ qua verifier.

### 7.3. Tài khoản dùng chung và break-glass

Shared admin account là rủi ro cao vì **không thể chỉ gỡ membership của một người để lấy lại tính bí mật của password đã chia sẻ**. Quy trình nên:

1. Inventory toàn bộ nơi người rời tổ chức từng được cấp shared credential.
2. Đổi password/API key/recovery code hoặc yếu tố xác thực theo cơ chế sản phẩm.
3. Thu hồi credential cũ; ngăn access từ thiết bị không được phép.
4. Cấp credential mới cho những người còn có trách nhiệm, theo vault/PAM và dual control.
5. Kiểm tra tài khoản dùng chung không còn quyền tự cấp raw key export ngoài policy.
6. Ghi audit, lý do thay, actor, hiệu lực và test phương án recovery.

Với **break-glass credential**, cần đặc biệt tránh khóa mất hoàn toàn đường khôi phục khi chưa có owner/quorum thay thế. Nhưng không được giữ credential cũ chỉ vì tiện: cần kế hoạch thay thế **trước hoặc phối hợp cùng mốc cắt quyền**.

### 7.4. Machine identities: Không xóa bot chỉ vì owner là người rời

Service account có thể được **tạo bởi** một nhân viên nhưng **thuộc về tổ chức** và đang chạy production. Trước khi disable:

- Tìm **workload/certificate/deployment/pipeline** phụ thuộc.
- Chuyển sang **owner, approver và on-call** mới có thể kiểm chứng.
- Xóa human impersonation/delegated grants của người cũ.
- Rotate secret nếu người cũ có thể xem hoặc xuất bản sao mà policy yêu cầu.
- Kiểm tra không còn **personal OAuth consent hoặc PAT** làm credential cho automation.
- Đưa machine identity về quản lý bằng workload identity/federation và secret store được chấp thuận nếu khả thi.
- Test workload chạy bình thường **không nhờ human account cũ**; nếu không, kế hoạch migration phải ưu tiên trước T0 nhưng không gia hạn quyền người rời.

**Không đưa user access token còn hạn của người rời vào pipeline để “chạy tạm”**, vì điều đó kéo dài quyền cá nhân và phá audit ownership.

## 8. Thu hồi quyền KMS/HSM: Các đường truy cập dễ sót

### 8.1. KMS key policy, grants và alias

Một người có thể nắm nhiều loại quyền độc lập:

| Quyền | Nguy cơ nếu còn sau nghỉ |
|---|---|
| **Describe/List key** | Lộ metadata, cấu trúc tenant/environment hoặc tập dữ liệu |
| **Encrypt/Decrypt/Wrap/Unwrap** | Dùng crypto API để tiếp cận plaintext/DEK hoặc mã hóa trái phép |
| **Sign/GenerateMac** | Phát hành chữ ký/tag hợp lệ ngoài thẩm quyền |
| **CreateGrant/ManagePolicy** | Tự cấp quyền cho principal hoặc automation khác, kể cả quyền sử dụng khóa |
| **Create/Import/Rotate key** | Tạo hoặc đưa key material ngoài chuẩn vào luồng vận hành |
| **Disable/ScheduleDeletion/Destroy** | Phá availability hoặc gây mất dữ liệu khó khôi phục |
| **Backup/Restore/Export** | Tạo bản sao material hoặc khôi phục trong security domain trái phép |

Security administrator phải kiểm tra **IAM + resource policy + grants + trust policy + cross-account roles + principal được giả định + service integration**. Một quyền có thể được cấp qua nested group hoặc temporary grant do người đó tạo cho một service account khác. Chỉ xóa role trực tiếp mà không đối soát **grant đã tạo** có thể bỏ sót đường thực thi.

**Alias** là tên tham chiếu, không phải security boundary. Xóa alias của người rời không có nghĩa key material đã bị disable, và **đổi alias** có thể làm bản mã lịch sử không giải mã đúng nếu application không lưu key ID/version thực.

### 8.2. HSM Security Officer, Crypto Officer và custodian share

HSM có thể tách **security officer**, **crypto officer**, **partition administrator**, **key custodian**, người giữ **smart card/PIN/token** và các **quorum/recovery shares**. Quyền và thao tác thay đổi theo thiết bị/provider; không mặc định mọi HSM dùng cùng tên role hoặc cho phép cùng cơ chế backup.

Khi một custodian rời tổ chức:

1. Xác minh **slot/partition** mà họ có quyền, các HSM cluster/backup HSM và session còn mở.
2. Thu hồi hoặc thay thế **smart card, MFA device, HSM token, login secret và recovery share** theo quy trình thiết bị.
3. Đảm bảo **quorum còn đủ người độc lập** để vận hành hoặc restore mà không cần người rời.
4. Thay các thành phần bí mật của quorum/recovery nếu policy và threat model yêu cầu; dùng **API/protocol chuẩn của HSM**, không tự ghép/cắt secret.
5. Phân tách quyền **thay custodian** với quyền **export/destroy key material**.
6. Kiểm tra **secure backup, remote HSM, region dự phòng và DR rehearsal**, không chỉ partition chính.
7. Ghi audit và bằng chứng hoàn tất mà không ghi key share, PIN hoặc private key.

**Thu hồi quyền người giữ share** không đồng nghĩa tự động đổi key material đang được HSM bảo vệ. Việc có cần rekey/reshare hoặc key rotation là quyết định theo **cơ chế backup/quorum và nguy cơ người cũ có bản sao secret**.

### 8.3. Zero-trust: Verify ở data plane

Một policy editor có thể báo đã gỡ **kms:Decrypt** nhưng một session hoặc token còn hiệu lực vẫn được gọi API do propagation/cache. Kiểm tra thành công phải xác định **thời điểm hiệu lực, nơi enforcement, phiên nào còn hợp lệ, key version nào và provider đã đồng bộ chưa**.

Tương tự, **KMS non-exportable KEK** không ngăn một process đang giữ plaintext DEK tiếp tục giải mã **offline**. Nếu người rời có thể điều khiển một workload đó, phải thu hồi quyền quản trị/điều khiển workload và credential, không chỉ cắt quyền trực tiếp tới KEK.

## 9. Có phải rotate mọi khóa mà người rời tổ chức từng dùng?

**Không.** “Từng sử dụng KMS key” có thể chỉ là được phép gọi API **Sign** bằng private key non-exportable; không đồng nghĩa đã biết raw private key. Nhưng “từng có quyền xem secret” hoặc “đã nhận raw DEK” có thể tạo ra khả năng sao chép không thể thu hồi. Vì thế phải phân loại theo **khả năng truy cập, bằng chứng, mức rủi ro và tính liên tục**.

### 9.1. Ma trận quyết định theo vật liệu và quyền

| Tài sản/tình huống | Bước tối thiểu khi nghỉ | Khi nào đánh giá rotation/migration? |
|---|---|---|
| **KMS KEK non-exportable; chỉ có quyền Describe** | Revoke IAM/metadata access, kiểm tra grants | Khi có chứng cứ misconfiguration hoặc khả năng gọi Unwrap/Decrypt ngoài policy |
| **KEK non-exportable; có quyền Unwrap** | Revoke grants, sessions, workload access và audit usage | Nếu dữ liệu/DEK có thể đã bị thu thập; tùy điều tra, có thể thay KEK và xử lý DEK |
| **Raw KEK/root secret đã được chia sẻ** | Cắt quyền sử dụng bản cũ và cô lập hệ thống | **Ưu tiên đánh giá thay root/KEK**, rewrap/migrate dữ liệu, vì kiến thức raw secret không thu hồi được |
| **DEK plaintext đã được export hoặc nằm trong file cá nhân** | Cắt đường truy cập, xác định record và key versions | Có thể phải **tạo DEK mới và re-encrypt** dữ liệu nếu không còn tin cậy material cũ |
| **Private signing key chỉ qua Sign API non-exportable** | Revoke Sign/grants, session, kiểm tra audit | Nếu key material không lộ, không mặc nhiên rotate; nếu Sign API bị lạm dụng, đánh giá token/chữ ký và policy |
| **Private signing key PEM đã từng gửi cho người đó** | Thu hồi đường phân phối và cảnh báo key owner | **Ưu tiên rotate/revoke trust** theo rủi ro vì chữ ký offline có thể được tạo |
| **Shared HMAC key/API secret** | Rotate secret và chặn bản cũ theo kế hoạch | Nếu đã biết/shared với leaver, thường cần thay vì không thể thu hồi tri thức secret |
| **KDF root/IKM có thể truy cập raw** | Revoke secret access; xác minh nơi chứa các bản sao | Đánh giá thay root và các derived keys; đổi HKDF info **không** sửa root đã lộ |
| **HSM quorum/recovery share** | Thu hồi vai trò, thay người giữ, bảo vệ thiết bị | Reshare/rekey/rotate theo provider nếu share cũ còn có giá trị hoặc rủi ro |
| **Public key/certificate công khai** | Chuyển owner/trust inventory nếu cần | Không rotate vì public key được biết; chỉ thay nếu private key/trust có vấn đề |
| **Service account do nhân sự sở hữu** | Chuyển owner, cắt human delegation | Rotate credential nếu có thể đã biết/đã xuất; không tắt production bot tùy tiện |

Một người **có quyền sử dụng** khóa không mặc nhiên có quyền **xuất material**. Ngược lại, một lần xuất material có thể làm yêu cầu rotation trở nên cấp thiết dù mọi grants đã được thu hồi.

### 9.2. Envelope encryption: Rewrap KEK khác re-encrypt DEK

Giả sử Customer Service lưu bản mã AES-GCM và wrapped DEK:

~~~text
plaintext --AES-GCM(DEK-v7, nonce, AAD)--> ciphertext + tag
DEK-v7  --Wrap(KEK-v3)------------------> wrapped DEK

Trường hợp A: chỉ thay KEK
    wrapped DEK mới = Wrap(KEK-v4, DEK-v7)
    Có thể giữ ciphertext payload nếu AAD/metadata contract cho phép.

Trường hợp B: DEK-v7 có thể đã lộ
    tạo DEK-v8 mới
    decrypt dữ liệu cũ qua đường được cấp phép
    encrypt lại bằng DEK-v8 và nonce mới theo policy
    cập nhật ciphertext/tag/metadata/keyRef và kiểm thử restore
~~~

Nếu **DEK-v7 bị lộ**, chỉ rewrap nó bằng KEK-v4 **không cứu được tính bí mật của ciphertext được bảo vệ bởi DEK-v7**. Security administrator và Key owner phải quyết định re-encrypt và xử lý dữ liệu đã có khả năng bị thu thập.

Nếu **metadata chứa KEK key version bên trong AES-GCM AAD**, rewrap rồi đổi trường version mà không xử lý AAD sẽ khiến authentication tag không hợp lệ. Phải có thiết kế rõ ranh giới **payload AAD** và **wrapping metadata**, hoặc thực hiện re-authentication/re-encryption tương ứng.

**Nonce AES-GCM cần duy nhất theo cùng DEK.** Nhân sự rời đi không làm reset nonce counter hoặc tổng số invocation. Khi thay DEK, nonce history của version cũ vẫn phải được xem trong vận hành/forensics; đừng “khôi phục” nonce state từ snapshot cũ và tái sử dụng cùng DEK.

### 9.3. Chữ ký số và JWKS: Khóa người dùng khác khóa issuer

Nếu một nhân sự nghỉ việc, **không cần rotate JWT issuer signing key chỉ vì nhân sự từng dùng token được ký bởi issuer đó**. Token của nhân sự phải bị thu hồi qua identity/session/authorization theo khả năng hệ thống.

Nhưng nếu nhân sự từng giữ **raw private issuer key** hoặc có khả năng tạo chữ ký ngoài kiểm soát, cần phối hợp:

1. Tạo **private signing key mới** từ provider/CSPRNG đáng tin.
2. Dừng Sign bằng key cũ và cập nhật các application sử dụng nó.
3. Cập nhật **JWKS/kid, certificate/trust chain**, TTL và verifier caches theo quy trình.
4. Quyết định token/session đang lưu hành nào phải bị từ chối ngay, dựa vào độ tin cậy của private key cũ và phạm vi sự cố.
5. Lưu bằng chứng chữ ký lịch sử theo mục đích; toán học **Verify(signature, old public key)** có thể vẫn trả true dù key bị ngừng sử dụng.

Đối với **certificate PKI**, thu hồi chứng thư thông qua đúng cơ chế và phạm vi của CA, kiểm tra cách verifier nhận trạng thái thu hồi. **KMS DisableKey không tự phát CRL hoặc cập nhật trust store**.

### 9.4. Root/derived keys và HMAC

Root secret có thể dẫn xuất nhiều key qua **HKDF**. Nếu người rời tổ chức biết root secret, họ có thể tái tạo các derived keys nếu biết salt/info/context hoặc nếu những giá trị đó có thể đoán được. **Chỉ xóa một PRK/OKM khỏi memory hoặc thay info label không phải crypto-erasure** khi root cũ còn tồn tại ngoài tầm kiểm soát.

Với **HMAC**, người biết cùng secret có thể tạo tag hợp lệ; không thể chứng minh sender cụ thể chỉ từ tag. Khi rotate HMAC secret, cần đồng bộ phía gửi/nhận, quản lý **key version**, khoảng chấp nhận tag cũ, expiration và **anti-replay**, đồng thời đảm bảo bên nhận cuối cùng từ chối secret cũ.

### 9.5. Không hủy khóa bằng cách làm mất dữ liệu

Trước khi disable vĩnh viễn hoặc destroy KEK/DEK:

- Xác định **ciphertext, wrapped DEK, backup, archive, replica và dữ liệu lưu trữ dài hạn** còn phụ thuộc key/version nào.
- Xác định có cần **Decrypt/Verify** dữ liệu lịch sử theo policy, tranh chấp pháp lý hoặc retention.
- Thử **restore/migration** bằng bản ghi được cấp phép.
- Bảo đảm đã chuyển owner và khả năng quản trị **non-exportable key** sang những principal hợp lệ.
- Xác định **backup/copies, escrow, cached DEK và các đường derived key** trước khi nói về crypto-erasure.

**Xóa một tài khoản leaver, xóa alias hoặc xóa một dòng key inventory đều không tương đương hủy key material.** Ngược lại, destroy key material sai thời điểm có thể gây mất dữ liệu không thể phục hồi.

## 10. Các race condition và bề mặt còn hiệu lực sau revoke

### 10.1. Time-of-check/time-of-use và eventual consistency

Trong môi trường phân tán, một lệnh revoke có thể:

- Cập nhật **IdP** nhưng một **session ở ứng dụng** vẫn còn.
- Thu hồi **KMS grant** nhưng token/role session cũ chưa hết hạn theo provider.
- Gỡ **HSM user** nhưng một session/handle đang dùng có thể còn đặc tính riêng.
- Cập nhật **credential vault** nhưng copy đã được lấy ra trước đó vẫn tồn tại.
- Gỡ **Git role** nhưng branch, archive hoặc clone local đã được tải về.
- Thay **JWT signing key** nhưng một verifier giữ JWKS cache cũ.
- Disable **KEK** nhưng **plaintext DEK cached** tiếp tục được dùng cho AES-GCM trong JVM.

Không nên diễn giải tình trạng này thành “hệ thống chắc chắn không an toàn” trong mọi provider; cần **xem contract của từng hệ thống, thời điểm effective và giới hạn chấp nhận**. Quan trọng là không đánh đồng **request accepted** với **revoke completed everywhere**.

### 10.2. Không cho stale event cấp lại quyền

Nếu offboarding được đồng bộ qua event bus:

~~~text
T1: GRANT(role=KMS_ADMIN, revision=17)
T2: REVOKE(role=KMS_ADMIN, revision=18)

Consumer nhận REVOKE revision=18 trước.
Event GRANT revision=17 đến muộn.

=> Không được áp GRANT cũ để mở quyền lại.
~~~

Điều phối nên dùng **event IDs, revision/correlation IDs, idempotent operations và kiểm soát thứ tự**. Các thao tác tạo quyền mới cho leaver sau **effectiveAt** phải được phát hiện và chặn theo policy; không chỉ thu hồi một lần rồi tin rằng nhóm sync không thêm họ trở lại.

### 10.3. Phân biệt thu hồi quyền và đóng session workload

Nếu một nhân sự có quyền quản trị Kubernetes hoặc CI/CD, họ có thể để lại một workload với **service account hợp lệ** đang chạy. Khi tắt quyền người dùng:

- Không tự hủy workload nếu nó phục vụ nghiệp vụ hợp pháp.
- Loại bỏ khả năng người rời tổ chức **triển khai mã, đổi secret hoặc điều khiển workload**.
- Chuyển owner, xem lại **pipeline approval, branch protection, image provenance, service credentials**.
- Khi có nghi ngờ mã hoặc secret đã bị sửa trái phép, coi đó là **sự cố supply-chain/workload compromise** và ứng phó theo phạm vi.

Một **service-account token còn hợp lệ** không tự đồng nghĩa do leaver đang sử dụng; phải đối chiếu **người kiểm soát, quyền tạo token, hoạt động bất thường và nguồn gốc credential**.

## 11. Offboarding và key inventory: Metadata cần thiết

Một hệ thống có key inventory tốt giúp trả lời câu hỏi **“người rời tổ chức từng có quyền gì với những khóa nào?”** mà không cần đọc raw key material.

### 11.1. Bản ghi khóa tối thiểu

| Trường | Ý nghĩa |
|---|---|
| **keyId + version + provider scope** | Tham chiếu đúng khóa trong account/partition/region và lịch sử |
| **key type/algorithm/purpose** | KEK, DEK, HMAC, private signing key, root KDF; Sign/Decrypt/Wrap |
| **owner và technical custodian** | Ai chịu trách nhiệm, ai có quyền vận hành/khôi phục |
| **tenant/environment** | Phân tách production/staging và khách hàng |
| **lifecycle state/cryptoperiod** | Active, suspended, retired, compromised, destroyed theo model |
| **exportability/storage location** | HSM/KMS/vault/local keystore, raw export policy |
| **grants/roles/authorization sources** | User/group/service/role cùng scope và nguồn cấp quyền |
| **dependencies** | Ciphertext, wrapped DEK, JWT issuer, certificate, HSM recovery share |
| **audit/events** | Sign/Decrypt/Unwrap, policy changes, rotations, key access exceptions |

### 11.2. Bản ghi nhiệm vụ offboarding

~~~yaml
caseId: LEAVER-EXAMPLE-014
subjectRef: employee-internal-042
effectiveAt: "2026-12-01T09:00:00Z"
scope:
  environments: [production, staging]
  sensitiveKeyActions: [DECRYPT, SIGN, UNWRAP, MANAGE_POLICY]
actions:
  - id: disable-identity
    system: enterprise-idp
    ownerRole: IAM_OPERATOR
    requiredEvidence: [provider-status, effective-time]
  - id: revoke-kms-grants
    system: approved-kms
    ownerRole: SECURITY_ADMINISTRATOR
    requiredEvidence: [grant-diff, negative-test]
  - id: review-shared-secrets
    system: secret-inventory
    ownerRole: KEY_OWNER
    requiredEvidence: [exposure-assessment, rotation-decision]
  - id: transfer-service-ownership
    system: workload-inventory
    ownerRole: APPLICATION_OWNER
    requiredEvidence: [new-owner, continuity-test]
completion:
  unresolvedExceptionOwner: REQUIRED
  independentReview: REQUIRED
~~~

Đây là **schema minh họa**, không phải file cấu hình tự động có thể chạy, và các mã/định danh trong ví dụ không chỉ tới người thật. Dữ liệu HR mang tính cá nhân nhạy cảm, cần chỉ chứa **mã nội bộ/thuộc tính tối thiểu** ở hệ thống Security ticket; không sao chép toàn bộ hồ sơ nhân sự vào key inventory hoặc audit public.

### 11.3. Đối soát từ nhiều nguồn

Không thể dựa hoàn toàn vào **một bản export IAM**. Nên đối soát **HR roster → IdP/groups → cloud roles → KMS/HSM grants/partitions → secret manager → CI/CD → app-level RBAC → SaaS/partners → service ownership → audit usage**, theo quyền read-only phù hợp. Không để công cụ kiểm kê có toàn quyền Decrypt/Export chỉ để lấy metadata.

Một khóa **không được dùng trong 12 tháng** chưa chắc có thể hủy, vì nó có thể là key dùng đọc archive hoặc verify chữ ký dài hạn. Một quyền **không xuất hiện trong log gần đây** cũng chưa chắc không tồn tại, do log coverage hoặc retention có giới hạn.

## 12. Java 17: Mô hình lập kế hoạch thu hồi quyền và kiểm tra bằng chứng

Để minh họa nguyên tắc **“offboarding là tập nhiệm vụ có điều kiện và bằng chứng”**, ví dụ Java 17 dưới đây nhận danh sách các **quyền/tài sản liên quan** đến một leaver và tạo **remediation plan**:

- **Identity:** disable và xử lý session.
- **KMS grant:** revoke và xác minh không còn thao tác được.
- **Shared credential:** rotate và xác minh giá trị cũ bị từ chối.
- **Exported secret:** chuyển thành **security review** để quyết định rotation; không tự động destroy key.
- **Machine identity:** chuyển ownership và kiểm thử continuity trước khi coi hoàn tất.
- **HSM custodian:** thu hồi vai trò và review quorum/recovery share.

**Lưu ý an toàn:** Code là mô hình **policy/checklist**, **không gọi IdP, KMS/HSM, không tạo hay xuất khóa, không thực thi revoke hoặc rotate**. Trong production phải tích hợp API có xác thực, quyền hạn, audit, retry và kiểm tra trạng thái của đúng provider. Không tin dữ liệu boolean tự khai từ người dùng để chứng minh công việc đã hoàn tất.

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class LeaverOffboardingPolicyDemo {
    enum Risk {
        STANDARD, ELEVATED
    }

    enum Category {
        HUMAN_IDENTITY, KMS_GRANT, SHARED_CREDENTIAL,
        EXPORTED_SECRET, MACHINE_IDENTITY, HSM_CUSTODIAN
    }

    enum Action {
        DISABLE_IDENTITY, REVOKE_SESSIONS, REVOKE_KMS_GRANT,
        ROTATE_SHARED_SECRET, REVIEW_KEY_ROTATION,
        TRANSFER_MACHINE_OWNER, VERIFY_SERVICE_CONTINUITY,
        REVOKE_HSM_ROLE, REVIEW_HSM_RECOVERY,
        VERIFY_ACCESS_DENIED
    }

    // Không đưa private key hoặc raw secret vào inventory.
    record Exposure(
            String resourceId,
            Category category,
            boolean rawSecretMayBeKnown,
            boolean sharedCredential,
            boolean productionDependency) {
        Exposure {
            if (resourceId == null || resourceId.isBlank()
                    || category == null) {
                throw new IllegalArgumentException("Invalid exposure");
            }
        }
    }

    record LeaverCase(
            String caseId,
            String personRef,
            String effectiveAt,
            Risk risk,
            List<Exposure> exposures) {
        LeaverCase {
            if (caseId == null || caseId.isBlank()
                    || personRef == null || personRef.isBlank()
                    || effectiveAt == null || effectiveAt.isBlank()
                    || risk == null || exposures == null) {
                throw new IllegalArgumentException("Invalid leaver case");
            }
            exposures = List.copyOf(exposures);
        }
    }

    record Task(
            String resourceId,
            Action action,
            boolean independentApproval,
            String reason) {
        Task {
            Objects.requireNonNull(resourceId);
            Objects.requireNonNull(action);
            Objects.requireNonNull(reason);
        }

        String id() {
            return resourceId + ":" + action.name();
        }
    }

    // Evidence ở đây là dữ liệu giả lập do một verifier tin cậy
    // cung cấp; KHÔNG phải chứng cứ bảo mật tự thân.
    record Evidence(
            String taskId,
            boolean providerConfirmed,
            boolean independentlyReviewed,
            String auditReference) {
        Evidence {
            Objects.requireNonNull(taskId);
            Objects.requireNonNull(auditReference);
        }
    }

    private static void add(
            Map<String, Task> result,
            Exposure exposure,
            Action action,
            boolean approvalRequired,
            String reason) {
        Task task = new Task(
                exposure.resourceId(), action, approvalRequired, reason);
        result.putIfAbsent(task.id(), task);
    }

    static List<Task> plan(LeaverCase leaver) {
        Map<String, Task> result = new LinkedHashMap<>();

        for (Exposure exposure : leaver.exposures()) {
            switch (exposure.category()) {
                case HUMAN_IDENTITY -> {
                    add(result, exposure, Action.DISABLE_IDENTITY,
                            false, "Chặn login mới theo effective time");
                    add(result, exposure, Action.REVOKE_SESSIONS,
                            false, "Xử lý session/token còn hiệu lực");
                    add(result, exposure, Action.VERIFY_ACCESS_DENIED,
                            false, "Xác minh IdP và ứng dụng");
                }
                case KMS_GRANT -> {
                    add(result, exposure, Action.REVOKE_KMS_GRANT,
                            false, "Thu hồi IAM/key grants theo scope");
                    add(result, exposure, Action.VERIFY_ACCESS_DENIED,
                            false, "Kiểm tra data-plane denial");
                }
                case SHARED_CREDENTIAL -> {
                    add(result, exposure, Action.ROTATE_SHARED_SECRET,
                            true, "Bản cũ có thể được người rời biết");
                    add(result, exposure, Action.VERIFY_ACCESS_DENIED,
                            false, "Credential cũ phải bị từ chối");
                }
                case EXPORTED_SECRET -> {
                    add(result, exposure, Action.REVIEW_KEY_ROTATION,
                            true, "Đánh giá rủi ro raw key material");
                    add(result, exposure, Action.VERIFY_ACCESS_DENIED,
                            false, "Cắt các đường truy cập hiện tại");
                }
                case MACHINE_IDENTITY -> {
                    add(result, exposure, Action.TRANSFER_MACHINE_OWNER,
                            true, "Không để workload thiếu owner");
                    add(result, exposure,
                            Action.VERIFY_SERVICE_CONTINUITY,
                            false, "Workload phải chạy không cần leaver");
                }
                case HSM_CUSTODIAN -> {
                    add(result, exposure, Action.REVOKE_HSM_ROLE,
                            false, "Xóa quyền partition/officer");
                    add(result, exposure, Action.REVIEW_HSM_RECOVERY,
                            true, "Thay custodian, kiểm tra quorum");
                    add(result, exposure, Action.VERIFY_ACCESS_DENIED,
                            false, "Kiểm tra HSM session/role");
                }
            }

            // Các điều kiện phụ không phụ thuộc duy nhất category.
            if (exposure.sharedCredential()
                    && exposure.category() != Category.SHARED_CREDENTIAL) {
                add(result, exposure, Action.ROTATE_SHARED_SECRET,
                        true, "Credential dùng chung có thể đã biết");
            }
            if (exposure.rawSecretMayBeKnown()
                    && exposure.category() != Category.EXPORTED_SECRET) {
                add(result, exposure, Action.REVIEW_KEY_ROTATION,
                        true, "Có thể có bản sao secret ngoài hệ thống");
            }
            if (exposure.productionDependency()
                    && exposure.category() != Category.MACHINE_IDENTITY) {
                add(result, exposure,
                        Action.VERIFY_SERVICE_CONTINUITY,
                        false, "Không làm hỏng production/restore");
            }
        }

        // Risk ELEVATED có thể đẩy nhanh quy trình theo policy.
        // Không tự động hủy toàn bộ khóa chỉ vì leaver rủi ro cao.
        return List.copyOf(result.values());
    }

    static List<String> incompleteTasks(
            List<Task> tasks, List<Evidence> evidences) {
        Map<String, Evidence> byTaskId = new LinkedHashMap<>();
        for (Evidence evidence : evidences) {
            if (byTaskId.putIfAbsent(evidence.taskId(), evidence) != null) {
                throw new IllegalArgumentException(
                        "Duplicate evidence for one task");
            }
        }
        List<String> missing = new ArrayList<>();
        for (Task task : tasks) {
            Evidence proof = byTaskId.get(task.id());
            if (proof == null
                    || !proof.providerConfirmed()
                    || proof.auditReference().isBlank()
                    || (task.independentApproval()
                            && !proof.independentlyReviewed())) {
                missing.add(task.id());
            }
        }
        return List.copyOf(missing);
    }

    public static void main(String[] args) {
        LeaverCase leaver = new LeaverCase(
                "LEAVER-EXAMPLE-014",
                "employee-internal-042",
                "2026-12-01T09:00:00Z",
                Risk.ELEVATED,
                List.of(
                    new Exposure("corporate-idp",
                            Category.HUMAN_IDENTITY,
                            false, false, false),
                    new Exposure("customer-kek-grant",
                            Category.KMS_GRANT,
                            false, false, true),
                    new Exposure("breakglass-console",
                            Category.SHARED_CREDENTIAL,
                            true, true, true),
                    new Exposure("legacy-signing-pem",
                            Category.EXPORTED_SECRET,
                            true, false, true),
                    new Exposure("billing-deploy-bot",
                            Category.MACHINE_IDENTITY,
                            false, false, true),
                    new Exposure("hsm-partition-a",
                            Category.HSM_CUSTODIAN,
                            false, false, true)
                ));

        List<Task> tasks = plan(leaver);
        System.out.println("Planned tasks: " + tasks.size());
        for (Task task : tasks) {
            System.out.println(task.id()
                    + " | approval=" + task.independentApproval());
        }

        // Không có chứng cứ từ provider/approver thì KHÔNG đóng case.
        List<String> incomplete = incompleteTasks(
                tasks, List.of());
        System.out.println("Can close without evidence: "
                + incomplete.isEmpty());

        // Các Evidence giả lập chỉ minh họa cách tính completeness.
        List<Evidence> proof = tasks.stream()
                .map(task -> new Evidence(
                        task.id(), true, true,
                        "AUDIT-DEMO-" + task.action()))
                .toList();
        System.out.println("All simulated tasks verified: "
                + incompleteTasks(tasks, proof).isEmpty());
    }
}
~~~

Lưu thành **LeaverOffboardingPolicyDemo.java**, chạy bằng **JDK 17+**:

~~~bash
javac LeaverOffboardingPolicyDemo.java
java LeaverOffboardingPolicyDemo
~~~

Kết quả gồm danh sách task IDs. Hai dòng kết luận mong đợi:

~~~text
Can close without evidence: false
All simulated tasks verified: true
~~~

Đây là **kết quả mô phỏng**, không phải bằng chứng hệ thống thực đã bị thu hồi quyền. Việc đưa **true** vào Evidence trong ví dụ chỉ có giá trị để kiểm thử logic danh sách nhiệm vụ; thực tế phải xác minh provider response, policy revision, thời điểm hiệu lực, approval và negative tests qua một dịch vụ được ủy quyền.

### 12.1. Cách đưa mô hình vào kiến trúc thật

Một hệ thống enterprise có thể tách:

~~~mermaid
flowchart TD
    HR["HR event: employee ID + effective time"] --> ORCH["Offboarding orchestrator"]
    ORCH --> GOV["Identity governance: quyền trực tiếp/kế thừa"]
    GOV --> REG["Key/secret inventory và ownership"]
    REG --> PLAN["Task plan + risk/approval"]
    PLAN --> IDP["IdP, sessions, token providers"]
    PLAN --> KMS["IAM/KMS/HSM, grants, custodians"]
    PLAN --> APPS["Vault, CI/CD, PKI, SaaS, machine identity"]
    IDP --> EV["Provider evidence"]
    KMS --> EV
    APPS --> EV
    EV --> REVIEW["Independent review + exceptions"]
    REVIEW --> AUD["Audit + closure decision"]
~~~

Với mỗi action phải định nghĩa **idempotency key, retry semantics, timeout, quyền thực thi tối thiểu, provider-specific capability và rollback/compensation**. Đối với lỗi tạm thời, nên retry những lệnh idempotent theo contract; **không tự tạo user token/secret mới rồi gửi vào log**. Với key destruction hoặc rotation có tác động mạnh, yêu cầu workflow riêng có approval và thử restore trước khi cho phép.

### 12.2. Những giới hạn bảo mật của code

1. **Không xác thực HR event:** personRef/effectiveAt chưa gắn với nguồn tin cậy hoặc chữ ký event; production phải xác minh và chống replay.
2. **Không phân giải nhóm/role kế thừa:** Exposure list là input giả, cần connector/identity governance để đối soát entitlement thật.
3. **Không thực hiện revoke/rotate:** code chỉ sinh checklist; kết quả success phải đến từ provider được kiểm tra.
4. **Evidence có thể bị giả mạo:** cần protected audit source, principal, timestamp, revision và người review độc lập.
5. **Không bảo đảm ngăn mọi token đã phát:** quyền hiệu lực còn phụ thuộc thời gian, cache, session và provider contracts.
6. **Không tự hủy material:** review key rotation là một tác vụ đánh giá, không phải quyền quyết định thay toàn bộ KEK/DEK.
7. **Không nêu đủ workflow pháp lý:** HR/Legal định nghĩa mốc, retention và thiết bị, ứng dụng không tự đoán.
8. **Không thay thế SoD:** cờ independentlyReviewed do mô phỏng cung cấp; hệ thống thực phải ngăn một người tự đóng cả vai trò requester và approver.
9. **Không điều phối theo hệ thống phân tán:** chưa có exactly-once semantics, event order, state persistence và multi-region propagation.
10. **Không chứa bí mật:** key ID/credential reference là metadata, không có raw key để tránh tạo bản sao nguy hiểm trong demo.

## 13. Kiểm thử: Chứng minh quyền đã bị từ chối và dịch vụ vẫn hoạt động

Chỉ gửi lệnh revoke không đủ để kết luận thành công. Các bài test nên kiểm tra **an ninh và khả năng vận hành**, gắn với system-of-record.

### 13.1. Bảng test offboarding

| Test case | Kết quả mong đợi | Cần chú ý |
|---|---|---|
| Leaver đăng nhập mới qua IdP | **DENY** tại thời điểm hiệu lực | Test an toàn và theo chính sách, không dùng tài khoản của người đã nghỉ |
| Refresh token của leaver | **DENY/Revoked** theo provider | Kiểm tra token family và client liên quan |
| Access token đã phát trước T0 | Bị hạn chế theo **TTL/revocation contract** đã thiết kế | Không khẳng định mọi JWT offline bị deny ngay |
| Cloud role session còn sống | Bị giới hạn/thu hồi theo provider | Phải xem session duration và explicit deny behavior |
| KMS **Decrypt/Sign** bằng leaver principal | **DENY** sau khi policy có hiệu lực | Kiểm tra đúng key ID/version, không chỉ alias |
| Người khác cùng nhóm vẫn được dùng khóa | **ALLOW** đúng scope nếu policy yêu cầu | Tránh thu hồi nhầm cả service/tenant |
| API key/PAT cá nhân | **DENY** từ issuing service | Không chỉ xóa record khỏi inventory |
| Shared secret cũ | **DENY**, secret mới hoạt động với authorized clients | Chặn cửa sổ song song không kiểm soát |
| HSM officer/partition role | **DENY** với quyền cũ; quorum mới đủ | Kiểm tra session và backup/DR partition |
| Machine identity thuộc dự án | **ALLOW** cho workload đúng quyền sau chuyển owner | Không dựa vào token của leaver |
| KMS key lịch sử cho Decrypt/Verify | Vẫn khả dụng theo key lifecycle và approved principals | Không destroy vì người cũ đã rời |
| Sự kiện cấp lại grant cũ đến muộn | Không cho **re-grant** quyền của leaver | Revision, deprovisioned marker và reconciliation |
| Key material từng export | Có **security review** và quyết định material rotation | IAM deny không chứng minh bản sao đã bị xóa |
| Audit event | Có actor, time, provider, scope, result, evidence ref | Không lưu raw secret, PII ngoài nhu cầu |

### 13.2. Cách kiểm tra mà không gây sự cố mới

- **Đừng** thử KMS Decrypt production bằng cách đưa dữ liệu nhạy cảm thật vào script của người kiểm thử.
- Dùng **key/test ciphertext chuyên dụng**, environment được phê duyệt và principal có điều kiện giống quyền cần kiểm tra; hoặc xác nhận provider denial qua audit/config API đáng tin.
- **Đừng** cho auditor mượn private key hay password tài khoản rời tổ chức chỉ để kiểm tra.
- Với **service continuity**, dùng synthetic transaction có kiểm soát: kiểm thử Sign, Wrap/Unwrap, decrypt mẫu, deploy pipeline và backup/restore trên key versions được cho phép.
- Nếu provider hỗ trợ policy simulation, sử dụng nó như **bằng chứng bổ trợ**, không thay thế thử dữ liệu thực tế ở data plane khi cần và được phê duyệt.
- Kiểm tra **negative tests** và **positive tests**: quyền của leaver bị deny, workload hợp pháp không bị mất quyền.

### 13.3. Phân biệt ba mức xác nhận

1. **Request acknowledgment:** một API nhận yêu cầu disable/revoke — chưa chắc áp dụng hoàn toàn.
2. **Configuration verified:** trạng thái mới có mặt ở IdP/KMS/HSM — vẫn có thể có session/cache ngoài phạm vi.
3. **Effective access verified:** các đường truy cập có ý nghĩa đã bị từ chối theo contract, ngoại lệ/TTL còn lại được ghi nhận và giám sát.

Một hệ thống audit tốt phải phân biệt ba mức này. Với crypto service dùng local DEK, **đường offline** chỉ có thể được khống chế bằng việc hạn chế thiết bị/process/bản sao, không thể kiểm thử KMS grant một cách gián tiếp rồi kết luận local memory đã sạch.

## 14. Audit, riêng tư và bằng chứng hoàn tất

### 14.1. Log những gì?

| Trường | Vì sao cần |
|---|---|
| **Case ID và person reference nội bộ** | Liên kết tới sự kiện HR đã được xác thực, hạn chế phơi bày PII |
| **EffectiveAt và executedAt** | Phân biệt mốc cắt quyền dự kiến và thời điểm hệ thống thực thi |
| **System/provider, account/partition/region** | Xác định phạm vi kỹ thuật của quyết định |
| **Credential/key ID/version, operation** | Biết quyền hoặc key material nào được xử lý |
| **Actor, approver, owner** | Truy trách nhiệm và separation of duties |
| **Before/after state và policy revision** | Phát hiện stale grant, quyền tái sinh và drift |
| **Provider result và effective time** | Không nhầm request accepted với access revoked |
| **Verification evidence reference** | Kết nối negative test, reconciliation, continuity test |
| **Exception ID, risk/compensating controls** | Không che giấu quyền còn tồn đọng |

**Không log** raw KEK/DEK, private-key seed, HSM PIN/share, PAT, API password, refresh/access token, plaintext khách hàng hoặc thông tin nhân sự ngoài phạm vi cần thiết. Audit log nên có **quyền truy cập độc lập, bảo vệ tính toàn vẹn, retention và quy trình xem xét**.

### 14.2. Không biến offboarding thành việc thu thập quá mức dữ liệu nhân sự

Key inventory chỉ cần biết **principal/owner reference** và quyền liên quan; HR record có thể chứa thông tin cá nhân nhạy cảm không phục vụ an ninh mật mã. Chia sẻ dữ liệu theo **need-to-know**, retention, quyền truy cập và quy định áp dụng; không ghi nhận suy đoán về lý do nghỉ việc trong log kỹ thuật.

Thông tin “người rời có thể đã biết secret” là một **nhận định exposure** cần xác minh, không phải lời kết luận họ đã đánh cắp bí mật. Khi có bằng chứng truy cập trái phép, xử lý qua kênh incident response/Legal có thẩm quyền, không suy diễn hoặc đưa nhận định cá nhân vào audit log công khai.

### 14.3. Tiêu chí đóng hồ sơ

Một case được đóng khi:

1. Sự kiện HR và person-to-identity mapping đã xác thực.
2. Entitlement inventory có coverage hợp lý theo hệ thống liên quan.
3. Direct/indirect grants, sessions và credential được thu hồi theo contract.
4. Shared secrets và raw-material exposure đã có quyết định rotation/migration hoặc risk acceptance được phê duyệt.
5. Machine identities, key owners và HSM recovery/quorum có owner mới; continuity tests đạt.
6. Có bằng chứng kỹ thuật của **effective denial** hoặc các hạn chế về TTL/propagation đã được nêu rõ.
7. Exception còn lại có owner, deadline, compensating control và lịch review.
8. Audit và independent review hoàn tất; không có raw secret trong ticket.

**Hồ sơ đóng không chứng minh xóa được bản sao dữ liệu mà một người đã từng mang đi**. Nó chứng minh quy trình đã xử lý khả năng truy cập còn tồn tại, đánh giá exposure và có kế hoạch ứng phó/rotation theo bằng chứng.

## 15. Threat model: Những lỗi offboarding phổ biến

| Sai lầm | Hậu quả có thể xảy ra | Biện pháp |
|---|---|---|
| Chỉ disable SSO | PAT, refresh token, app session hoặc HSM login còn hiệu lực | Inventory nhiều hệ thống, revoke/verify từng lớp |
| Chỉ xóa IAM role trực tiếp | Nested groups, cross-account role và grants còn quyền | Entitlement graph, reconciliation theo provider |
| Bỏ sót người giữ recovery share HSM | Người cũ vẫn tham gia hoặc thao túng quorum | Thay custodian/share theo quy trình HSM |
| Quên break-glass/shared password | Credential từng biết vẫn dùng được | Rotate và thu hồi bản cũ, áp dụng PAM |
| Xóa service account do leaver tạo | CI/CD, API, batch job hoặc business service ngừng hoạt động | Transfer ownership và kiểm tra continuity trước/sau |
| Giữ personal PAT trong pipeline | Quyền leaver sống qua automation | Chuyển sang workload identity/credential thuộc tổ chức |
| Thu hồi KMS nhưng không kiểm tra key cache | Plaintext DEK đã xuất vẫn sử dụng được offline | Cache policy, access to workload, session/device controls |
| Nhầm **KMS key ID** với secret | Hủy/rotate vô cớ gây downtime mà bỏ sót quyền thực | Đánh giá exportability, key usage và exposure thật |
| Từng biết private key PEM nhưng chỉ disable Sign | Có thể ký offline bằng bản sao | Key replacement, trust/certificate/JWKS response |
| Lộ DEK nhưng chỉ rewrap KEK | DEK lộ vẫn mở được ciphertext | Thay DEK, đánh giá re-encrypt và dữ liệu bị ảnh hưởng |
| Hủy KEK khi chưa kiểm tra archive | Không thể mở wrapped DEK cũ | Dependency inventory, restore/migration test |
| Đổi signing key mà quên JWKS caches | Token/chữ ký hợp pháp bị từ chối hoặc khóa cũ còn được tin sai | Trust/version publication và revocation plan |
| Tin mọi JWT bị revoke tức thì | Verifier offline vẫn chấp nhận token còn hạn | TTL/introspection/denylist/session policy |
| Không xét multi-region/async grants | Một region hoặc consumer nhận event cũ cấp lại quyền | Effective-time tracking, revisions, reconciliation |
| Admin tự cấp quyền, tự duyệt và sửa audit | Mất separation of duties và chứng cứ | Dual control, immutable audit, độc lập review |
| Log raw key/token để chứng minh revoke | Tạo sự cố bí mật mới | Chỉ log metadata, provider evidence và test refs |
| Đóng case khi chỉ có API 200 | Không có xác nhận quyền thật bị chặn | Negative tests, effective enforcement evidence |
| Tự suy đoán lý do nghỉ việc | Xử lý sai policy và lộ dữ liệu nhân sự | Sự kiện HR xác thực, tối thiểu dữ liệu, đúng vai trò |
| Rotate mọi key mà leaver từng thấy metadata | Gián đoạn lớn, bỏ sót nguồn exposure thật | Risk-based decision, phân biệt key material với key ID |
| Bỏ sót external contractors/SaaS | Credential độc lập còn sử dụng được | Third-party inventory và provider-specific revoke |

## 16. Case study: Kỹ sư KMS/HSM rời đội thanh toán

### 16.1. Bối cảnh

Một kỹ sư nền tảng tham gia vận hành **Billing Service** và **Customer Service**. Họ có tài khoản SSO, quyền quản trị KMS một số key families, một HSM Security Officer role, được cấp quyền xem secret của pipeline cũ, là owner của **billing-ci-bot**, và từng tham gia quy trình recovery backup. Billing ký hóa đơn bằng private key non-exportable trong HSM; Customer Service lưu dữ liệu bằng AES-GCM với DEK được wrap bởi tenant KEK trong KMS.

Yêu cầu nghiệp vụ: **cắt quyền con người đúng thời điểm nhưng không làm gián đoạn ký hóa đơn, đọc dữ liệu cũ hoặc khôi phục thảm họa**.

### 16.2. Phương án sai

Một automation chỉ disable SSO account và xóa nhân sự khỏi nhóm **developers**. Các nguy cơ còn lại:

- **HSM Officer** dùng credential độc lập vẫn có thể thao tác.
- **PAT** của pipeline cũ vẫn chưa bị revoke.
- **billing-ci-bot** dùng personal token của kỹ sư.
- **Break-glass share** vẫn có thể được người cũ sử dụng.
- KMS **CreateGrant** đã cấp trước đó chưa được rà soát.
- Không biết private key/HMAC secret nào có thể đã được xuất qua CI artifact.

### 16.3. Phương án có kiểm soát

1. **HR xác nhận T0 và person reference**; Security xác thực mapping đến mọi privileged identities.
2. **Inventory quyền:** liệt kê KMS policy/grants, HSM partition, vault secrets, cloud roles, CI credentials, bot ownership và recovery share.
3. **Chuyển ownership:** phân công Billing owner mới cho bot và key family, HSM custodian mới, kiểm tra quorum và DR.
4. **Chuẩn bị credential hợp pháp mới:** thay personal PAT trong pipeline bằng workload credential do tổ chức quản lý; test deployment không dùng tài khoản leaver.
5. **T0:** IdP/IAM revoke sessions, loại khỏi cloud/KMS grants, HSM role, secret manager, Git, CI và SaaS ngoài federation.
6. **Xử lý shared secrets:** rotate các credential từng được biết, thu hồi bản cũ; đánh giá HSM recovery share theo provider contract.
7. **Đánh giá key material:** key ký non-exportable với chỉ quyền Sign cần audit/authorization review; nếu không có dấu hiệu raw key lộ, **không mặc nhiên destroy**. Nếu phát hiện bản **HMAC key raw** trong CI artifact người đó có thể lấy, ưu tiên rotation và cập nhật verifier.
8. **Envelope encryption:** giữ KEK/key versions cần thiết để đọc archive; nếu có bằng chứng plaintext DEK lộ, lập kế hoạch thay DEK và re-encrypt dữ liệu.
9. **Xác minh:** negative tests cho principal bị thu hồi, positive tests cho Billing Sign, Customer Unwrap/Decrypt theo policy và backup recovery.
10. **Audit và closure:** độc lập xác nhận theo evidence, exception có deadline, không ghi secret trong ticket.

### 16.4. Kết quả mong đợi

Người rời tổ chức không còn **đăng nhập, thực hiện thao tác KMS/HSM, cấp quyền hoặc dùng credential đã chia sẻ** trong phạm vi offboarding sau thời điểm hiệu lực và giới hạn provider được xác nhận. Billing/Customer vẫn chạy bằng **machine identity và key owner hợp lệ**. Trường hợp có raw key exposure được xử lý bằng risk-based rotation và migration; **không hủy đại trà** những khóa đang bảo vệ dữ liệu lịch sử.

## 17. Checklist offboarding chuyên biệt cho key management

1. **HR trigger:** event có nguồn tin cậy, person reference, effective time và case ID?
2. **Account mapping:** đã nhận diện đúng IdP, privileged/secondary identity và external accounts?
3. **Direct/indirect access:** đã rà IAM group, role assumptions, resource policies, KMS grants và SaaS permissions?
4. **Tokens/sessions:** đã revoke hoặc kiểm soát TTL của refresh/access token, SSO/app session, PAT, API keys, VPN/SSH?
5. **KMS permissions:** Decrypt/Sign/Unwrap/CreateGrant/ManagePolicy/Export/Destroy có bị thu hồi theo scope?
6. **HSM roles:** Security Officer/Crypto Officer, partition access, token/PIN, quorum/recovery shares đã xử lý?
7. **Shared secrets:** mọi giá trị người rời có thể biết đã được đánh giá rotation và có bằng chứng bản cũ bị từ chối?
8. **Raw material exposure:** private signing key, HMAC secret, KEK/root, DEK hoặc PRK/OKM đã xuất có được đánh giá riêng?
9. **Machine identities:** bot, service account, CI/CD, certificate owner và workload identity đã chuyển ownership?
10. **Key inventory:** key ID/version, owner, purpose, state, provider location và dependencies còn đúng sau bàn giao?
11. **Cryptographic continuity:** AES-GCM ciphertext, wrapped DEK, JWT/JWKS, HMAC verification và archive còn được phục vụ đúng policy?
12. **Rotation decision:** đã phân biệt rewrap KEK, re-encrypt DEK, thay signing key và root KDF theo material exposure?
13. **Data-plane enforcement:** có bằng chứng deny trên provider, không chỉ thông báo “API request accepted”?
14. **Multi-region/cache:** phiên, TTL, propagation và sự kiện grant cũ có được xử lý hoặc ghi exception?
15. **Break-glass:** tài khoản chia sẻ, khóa recovery và quyền khẩn cấp có owner/quorum hợp lệ sau leaver?
16. **Separation of duties:** người duyệt rotation/destruction độc lập với người thực hiện/kiểm toán theo policy?
17. **Backup/DR:** restore key versions đã được kiểm tra trước khi bất kỳ hành động destroy nào?
18. **Logs/PII:** audit đủ actor/keyRef/time/outcome nhưng không lộ raw secret hoặc lý do nghỉ việc không cần thiết?
19. **Incident response:** nếu có dấu hiệu key compromise hoặc API abuse, đã mở incident riêng và xử lý phạm vi?
20. **Closure:** mọi nhiệm vụ có evidence hoặc exception có owner/deadline/compensating control và independent review?

### Câu hỏi tự kiểm tra

**Câu 1.** Vô hiệu hóa SSO account có chắc chặn ngay JWT access token đã phát tới một verifier chỉ Verify offline không?

**Trả lời:** **Không.** Verifier offline có thể chấp nhận JWT còn hạn cho đến khi thay đổi cơ chế revocation/trust hoặc hết TTL. Cần xem chính sách token và authorization layer.

**Câu 2.** Kỹ sư từng có quyền Sign bằng private key non-exportable trong HSM. Có bắt buộc destroy private key ngay khi họ nghỉ không?

**Trả lời:** **Không mặc định.** Thu hồi quyền/credential và rà audit trước; rotate/revoke key nếu có bằng chứng key material hoặc năng lực ký đã bị lạm dụng theo risk assessment. Hủy tùy tiện có thể phá dữ liệu/chữ ký lịch sử.

**Câu 3.** Người đó từng biết shared break-glass password. Gỡ họ khỏi nhóm admin có đủ không?

**Trả lời:** **Không.** Họ có thể vẫn biết mật khẩu. Cần thay shared secret và yếu tố xác thực theo provider, thu hồi bản cũ và kiểm tra continuity của tài khoản khẩn cấp.

**Câu 4.** Vì sao không disable ngay service account của pipeline chỉ vì owner trước đó đã nghỉ?

**Trả lời:** Nó có thể là machine identity phục vụ production. Cần chuyển ownership, tách credential cá nhân, rotate secret có exposure và test workload chạy bình thường.

**Câu 5.** Thu hồi KMS Unwrap grant có làm plaintext DEK đã cache trong JVM biến mất không?

**Trả lời:** **Không.** Bản DEK cached có thể tiếp tục dùng offline. Phải xét quyền điều khiển workload, cache TTL/invalidation, phiên và material exposure.

**Câu 6.** Rewrap DEK đã lộ bằng KEK mới có phục hồi tính bí mật của dữ liệu được mã hóa bởi DEK đó không?

**Trả lời:** **Không.** Ai có DEK cũ vẫn có thể giải mã ciphertext liên quan. Cần đánh giá thay DEK, re-encrypt dữ liệu và phạm vi bản mã đã bị thu thập.

**Câu 7.** Người giữ một recovery share HSM nghỉ việc có đồng nghĩa phải hủy toàn bộ root KEK đang nằm trong HSM không?

**Trả lời:** **Không nhất thiết.** Phải thu hồi/thay custodian, kiểm tra quorum và cơ chế reshare/rekey theo provider, đánh giá rủi ro share cũ và đảm bảo khả năng khôi phục.

**Câu 8.** Một sự kiện GRANT cũ đến sau sự kiện REVOKE mới; hệ thống có nên áp sự kiện đến sau không?

**Trả lời:** **Không.** Cần kiểm tra revision/event order, deprovisioned state và reconciliation để không tái cấp quyền người rời.

**Câu 9.** Sau khi disable user, liệu Key owner có thể xóa KEK khi chưa kiểm tra archive không?

**Trả lời:** **Không.** Dữ liệu lịch sử có thể cần KEK để Unwrap DEK. Phải rà dependency, retention và thử restore/migration trước khi destroy.

**Câu 10.** Nếu nhân sự từng đọc raw private signing key PEM, chỉ thu hồi quyền Sign ở KMS đã đủ chưa?

**Trả lời:** **Chưa.** Bản sao PEM vẫn có thể tạo chữ ký offline. Cần đánh giá key rotation, public-key trust/certificate/JWKS, token/session revocation và incident scope.

**Câu 11.** Vì sao cần thử cả DENY và ALLOW sau offboarding?

**Trả lời:** Phải vừa chứng minh người rời **không còn quyền**, vừa xác nhận những workload/owners hợp pháp **vẫn chạy bình thường**. Một lệnh revoke phá production không phải offboarding thành công.

**Câu 12.** Một case đã có API response 200 cho tất cả lệnh revoke có nên đóng ngay không?

**Trả lời:** **Không tự động.** Cần kiểm tra hiệu lực data plane, sessions/tokens còn sống, shared secret exposure, ownership, continuity, audit và những exception còn mở.

**Điểm cốt lõi:** **Thu hồi quyền của nhân sự rời tổ chức trong key management không chỉ là tắt một tài khoản.** Cần phối hợp HR–IAM–Security–Key owner–KMS/HSM–Audit để **tìm mọi đường dùng khóa, cắt quyền đúng thời điểm, xử lý token/credential/bản sao, đánh giá key rotation theo mức lộ, chuyển giao owner và xác minh denial thực tế**. Phân biệt rõ **revoke access**, **rotate key material** và **destroy key** giúp giảm nguy cơ lộ dữ liệu mà không làm mất khả năng giải mã, xác minh chữ ký hoặc khôi phục hoạt động của tổ chức.
