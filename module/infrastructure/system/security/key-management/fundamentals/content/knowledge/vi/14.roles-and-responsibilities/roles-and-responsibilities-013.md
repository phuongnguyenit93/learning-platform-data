# Access review: rà soát quyền truy cập và quyền sử dụng khóa mật mã

## 1. Vì sao access review quan trọng trong key management?

Một doanh nghiệp sử dụng **KMS/HSM** để bảo vệ KEK của hệ thống thanh toán và private signing key của dịch vụ phát hành chứng từ. Các khóa được sinh đúng thuật toán, nằm trong thiết bị được kiểm soát và có chính sách rotation. Nhưng sau một đợt triển khai, tài khoản dịch vụ xử lý báo cáo được cấp thêm quyền **Unwrap/Decrypt** trên nhiều key; một nhân viên chuyển bộ phận vẫn giữ quyền thay key policy; một tài khoản khẩn cấp tiếp tục tồn tại sau khi sự cố kết thúc.

Nếu chỉ kiểm tra **khóa có bị xuất ở dạng rõ hay không**, doanh nghiệp có thể bỏ sót vấn đề chính: một chủ thể không được phép vẫn có thể **sử dụng khóa bằng API**. Kẻ tấn công chiếm được principal có quyền Sign có thể tạo chữ ký giả mà không biết private key. Tương tự, một principal có quyền KMS Unwrap rộng có thể khôi phục DEK để giải dữ liệu dù KEK non-exportable.

**Access review** là hoạt động rà soát có hệ thống các **quyền truy cập và quyền thực hiện thao tác mật mã** của người dùng, workload, service account, nhóm, vai trò và bên thứ ba đối với **khóa, KMS/HSM, secret stores, dữ liệu và cơ chế trust**. Review nhằm xác nhận quyền đó còn **cần thiết, hợp lệ, đúng phạm vi, được phê duyệt, có thời hạn và có người chịu trách nhiệm**.

Một access review tốt phải trả lời năm câu hỏi:

1. **Ai** có thể thực sự gọi thao tác mật mã hoặc thay chính sách?
2. **Đối với khóa/tài nguyên nào**, thuộc tenant, environment và mục đích nào?
3. **Thao tác gì** được phép: Encrypt, Decrypt, Sign, Unwrap, DeriveKey, Export, ChangePolicy...?
4. **Vì sao quyền tồn tại**, ai phê duyệt, đến bao giờ, có được sử dụng đúng không?
5. **Phải giữ, giảm, thu hồi hay điều tra** quyền nào, và bằng chứng thực thi ở đâu?

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, access review kết nối **vòng đời khóa**, **mật mã đối xứng/bất đối xứng**, **chữ ký số**, **KMS/HSM**, **envelope encryption**, **IAM**, **audit** và vai trò người chịu trách nhiệm đối với khóa.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt access review với **policy review, access request, recertification, technical audit** và xử lý sự cố.
- Mô hình hóa **subject – entitlement – resource – operation – context** trong quản trị quyền mật mã.
- Phân tích **effective permissions**, kể cả group inheritance, role assumption, resource policy, grants, trust relationship, cross-account và đường truy cập dự phòng.
- Xây dựng **RACI** giữa key owner, data owner, custodian, administrator, security reviewer, auditor, workload owner và approver.
- Áp dụng **least privilege, separation of duties, just-in-time access, dual control** và xử lý quyền khẩn cấp.
- Rà soát quyền cho **DEK, KEK, root keys, signing keys, MAC keys, ECDH/session keys, trust stores và recovery materials**.
- Thiết kế lịch review **định kỳ, theo sự kiện và liên tục**; không để người rời tổ chức hoặc khóa retired giữ quyền dư.
- Sử dụng bằng chứng từ **KMS/HSM, IAM, inventory, runtime, audit log và ticket** mà không xuất secret.
- Đọc ví dụ **Java 17** phân tích access snapshot, đánh dấu grants bất thường và tạo đề xuất review.
- Quản lý **findings, người khắc phục, thời hạn, retest và sign-off** theo nguy cơ thực tế.

## 2. Access review nằm ở đâu trong hệ thống kiểm soát?

Access review không chỉ là gửi email hỏi quản lý “còn cần tài khoản này không?”. Đây là một phần của chu trình:

~~~mermaid
flowchart LR
    REQ["Yêu cầu quyền + lý do nghiệp vụ"] --> APPROVE["Owner/approver đánh giá"]
    APPROVE --> PROVISION["IAM/KMS/HSM cấp quyền có giới hạn"]
    PROVISION --> USE["Workload sử dụng khóa"]
    USE --> LOG["Audit và theo dõi"]
    LOG --> REVIEW["Access review: quyền thực tế + nhu cầu"]
    REVIEW --> DEC{"Giữ / giảm / thu hồi / điều tra?"}
    DEC -->|"Giữ có căn cứ"| USE
    DEC -->|"Giảm hoặc thu hồi"| FIX["Thay grant, role, session, credential"]
    FIX --> VERIFY["Xác minh effective access mới"]
    VERIFY --> LOG
~~~

### 2.1. Phân biệt các hoạt động liên quan

| Hoạt động | Câu hỏi trọng tâm | Kết quả chính |
| --- | --- | --- |
| **Access request** | Có nên cấp quyền mới cho chủ thể này không? | Approval và grant mới có phạm vi |
| **Provisioning** | Làm sao cấu hình IAM/key policy/grant đúng? | Quyền được cấp trên hệ thống |
| **Access review/recertification** | Quyền **đang tồn tại** có còn cần và đúng không? | Keep/reduce/revoke/investigate, evidence |
| **Cryptographic policy review** | Quy tắc thuật toán, vòng đời và quyền có còn phù hợp? | Baseline chính sách được sửa hoặc xác nhận |
| **Key inventory review** | Danh sách key, owner, custodian và state có đúng? | Inventory được đối soát |
| **Key usage monitoring** | Ai đang dùng quyền và có bất thường không? | Alert, investigation và audit |
| **Incident response** | Quyền/khóa đang bị lạm dụng hoặc lộ? | Containment, investigation, recovery |

Chẳng hạn **policy review** kết luận mọi DEK của tenant phải có quyền Decrypt giới hạn. **Access review** truy ra role nào thực sự có quyền Decrypt trên những key IDs đó và liệu tất cả còn cần quyền.

### 2.2. Access review không thay thế authorization tại runtime

Khi một application nhận yêu cầu đọc hóa đơn, nó vẫn phải xác thực người gọi và kiểm tra **tenant/resource ownership** trước mỗi thao tác phù hợp. Một buổi review đã duyệt quyền cho workload **không tự cho phép workload đọc mọi hóa đơn**.

**Review là kiểm soát phòng ngừa/phát hiện ở cấp quản trị; authorization là kiểm soát phải được thực thi tại thời điểm thao tác.** Hai lớp này bổ trợ nhau.

### 2.3. Access review không chứng minh key material chưa từng bị lộ

Ngay cả khi tất cả grants được thu hồi hôm nay, một attacker trước đó đã sao chép plaintext DEK hoặc private key **vẫn có thể giữ bản sao**. Do đó cần phân biệt:

- **Permission exposure:** quyền quá rộng hoặc không còn phù hợp.
- **Key usage compromise:** quyền KMS/HSM đã bị sử dụng trái phép.
- **Key material compromise:** raw secret bị lấy ra khỏi ranh giới quản lý.
- **Data compromise:** plaintext hoặc bản mã/DEK liên quan đã bị truy cập.
- **Policy compromise:** đối tượng có thể thay grant, trust, key state hoặc xóa bằng chứng.

Kết quả access review phải ghi **loại rủi ro** thay vì mặc định “thu hồi permission là đủ”.

## 3. Đơn vị cần rà soát: subject, resource, operation và context

Để review có thể kiểm chứng, hãy mô tả mỗi quyền bằng một **entitlement**:

~~~text
Entitlement =
  Subject/Principal
  + Resource/Key ID hoặc phạm vi tài nguyên
  + Action/Operation
  + Conditions/Context
  + Grant source và trust path
  + Expiry/Approval/Owner
  + Effective status và audit evidence
~~~

### 3.1. Subject không chỉ là người

Những chủ thể thường gặp:

- **Con người:** security engineer, key administrator, custodian, auditor, incident responder.
- **Workload identities:** Java microservice, batch job, serverless function, container workload.
- **Service accounts:** non-human principals dùng CI/CD, hệ thống tích hợp hoặc backup.
- **Groups/roles:** nhóm IAM, role được assume, quyền kế thừa.
- **Cross-account/federated identity:** tổ chức hoặc đối tác khác được cấp quyền.
- **Emergency identities:** tài khoản break-glass, HSM recovery operators.
- **Device/agent identities:** phần mềm giám sát hoặc HSM client của nhà cung cấp.

Một người đã nghỉ việc có thể bị khóa login cá nhân nhưng vẫn có **service token, smart card hoặc shared credential** hoạt động. Review phải kiểm tra **con đường sử dụng thực tế**.

### 3.2. Resource không chỉ là tên khóa

| Resource | Ví dụ | Hậu quả nếu quyền sai |
| --- | --- | --- |
| **DEK** | Khóa mã hóa hóa đơn tenant A | Lộ nội dung dữ liệu tương ứng |
| **KEK/KMS key** | Key bọc nhiều DEK | Có thể unwrap nhiều data keys |
| **Root/master/derivation key** | IKM dẫn xuất nhiều khóa con | Một quyền DeriveKey rộng ảnh hưởng nhiều purpose |
| **Private signing key** | Ký manifest/receipt/JWT | Có thể tạo chữ ký giả |
| **HMAC key** | Xác thực webhook nội bộ | Có thể tạo MAC giả nếu có secret/GenerateMac |
| **Trust store/JWKS registry** | Public verification keys đáng tin | Có thể thay khóa xác minh, chấp nhận signer giả |
| **KMS key policy/grant** | Quyền quản trị một key | Có thể cấp lại quyền bị thu hồi |
| **HSM partition/quorum** | Ranh giới vận hành phần cứng | Có thể thay key attributes, recovery hoặc hủy |
| **Backup/recovery shares** | Phục hồi KEK/root | Có thể tái tạo hoặc đánh mất quyền giải mã |
| **Audit log/control plane** | Nhật ký Sign/Decrypt/grants | Có thể che giấu misuse |

Một role không có quyền Decrypt nhưng được **UpdateKeyPolicy/CreateGrant** cũng có thể nguy hiểm nếu tự cấp lại Decrypt. Vì vậy review không chỉ tìm trực tiếp action Decrypt.

### 3.3. Context của quyền

Một grant có thể hợp lệ chỉ khi các điều kiện cùng đúng:

- **Environment:** production hoặc staging, không được lẫn.
- **Tenant/data class:** chỉ tài nguyên của nhóm được phép.
- **Purpose:** wrap DEK, ký release, mã hóa hóa đơn, kiểm tra HMAC...
- **Operation:** Encrypt khác Decrypt; Sign khác Verify.
- **Resource ID/version:** chỉ một tập key IDs hoặc alias được kiểm soát.
- **Time:** thời hạn cấp quyền; chỉ hoạt động trong cửa sổ bảo trì.
- **Network/device/workload identity:** nguồn gọi được phép nếu hệ thống hỗ trợ.
- **Approval/ticket:** cấp theo thay đổi có phê duyệt còn hiệu lực.
- **Cryptoperiod/key state:** key còn được dùng cho operation này không.

**Quyền theo resource và key không tự giải quyết business authorization.** KMS có thể biết “tenant A” trong encryption context nhưng không biết người dùng có quyền xem **invoice #154** hay không.

## 4. Vai trò và trách nhiệm: ai có quyền quyết định?

### 4.1. Ma trận vai trò

| Vai trò | Trách nhiệm với access review | Không nên mặc định có |
| --- | --- | --- |
| **Key owner** | Xác nhận use case, purpose, key lifetime và quyền cần thiết | Raw KEK/private key |
| **Data/application owner** | Chứng minh workload cần quyền với tenant/dataset nào | Quyền thay key policy tùy ý |
| **Key custodian** | Cung cấp inventory, state, custody, access paths, recovery evidence | Decrypt/Sign mọi dữ liệu |
| **IAM/KMS/HSM administrator** | Xuất effective grants, thực thi thay đổi đã duyệt | Tự phê duyệt quyền của chính mình |
| **Security/access reviewer** | Đánh giá entitlement, risk, SoD và ngoại lệ | Quyền dùng raw key |
| **Independent verifier/auditor** | Kiểm tra bằng chứng và xác nhận closure | Quyền sửa log hoặc policy |
| **Risk/exception approver** | Chấp nhận residual risk theo thẩm quyền có hạn | Được miễn yêu cầu bảo mật mặc định |
| **Incident responder** | Cô lập quyền khi nghi misuse, bảo vệ evidence | Quyền break-glass vĩnh viễn |
| **Principal owner/manager** | Xác nhận identity còn hoạt động và nhiệm vụ thực tế | Quyết định mọi key usage khi không hiểu kỹ thuật |

### 4.2. Cách giao trách nhiệm RACI

Trong mô hình RACI, **R** là người thực hiện, **A** chịu trách nhiệm cuối, **C** được tham vấn và **I** được thông báo.

| Hoạt động | Key owner | Custodian/KMS admin | App owner | Security reviewer | Auditor |
| --- | --- | --- | --- | --- | --- |
| Xác định Decrypt/Sign cần thiết | A | C | R | C | I |
| Thu entitlement/effective permissions | C | R | R cho app-layer | A | C |
| Quyết định keep/reduce/revoke | A theo phạm vi rủi ro | C | R giải thích nhu cầu | R đánh giá | C |
| Thực thi revoke/grant reduction | I | R | C | A/giám sát | I |
| Retest/đối chiếu quyền mới | C | C | C | R | A hoặc xác nhận độc lập |
| Cập nhật inventory và audit | A/C | R | C | R kiểm tra | C |
| Emergency containment | I/C | R theo runbook | R khi liên quan | A/điều phối | I |

**Không nhất thiết mọi tổ chức dùng đúng bảng này**. Điều bắt buộc là tránh vòng tự duyệt: một người không nên **tự đề xuất, tự cấp, tự xác nhận và tự xóa bằng chứng** cho một quyền rủi ro cao.

### 4.3. Các câu hỏi nên hỏi owner

- Quyền này còn phục vụ **nhiệm vụ hiện tại** hay là di sản từ một dự án đã đóng?
- Đây là quyền cần **liên tục** hay chỉ trong một cửa sổ bảo trì?
- Có thể thay **Decrypt toàn bộ** bằng một API trả dữ liệu đã lọc/đã ẩn thông tin không?
- Có cần **Sign** không, hay chỉ cần **Verify** bằng public key?
- Có cần **Unwrap** không, hay chỉ cần **Encrypt/GenerateDataKey**?
- Cần truy cập đúng những **key IDs, tenants, environments** nào?
- Có biện pháp **JIT, thời hạn, approval kép** cho thao tác nguy hiểm?
- Nếu quyền bị giảm, luồng nghiệp vụ nào sẽ hỏng; có kiểm thử trước không?

Nếu owner không thể giải thích **mục đích nghiệp vụ cụ thể**, đó là tín hiệu cần review sâu; không tự động kết luận quyền phải xóa ngay khi nó ảnh hưởng backup/khôi phục, nhưng không thể PASS không có căn cứ.

## 5. Phân loại quyền mật mã theo mức rủi ro

Rà soát quyền phải dựa vào **khả năng thực tế mà quyền cung cấp**, không chỉ tên hành động.

| Key operation | Mục đích hợp lệ | Rủi ro khi quyền quá rộng |
| --- | --- | --- |
| **Encrypt** | Bảo vệ dữ liệu mới | Có thể mã hóa dưới key/purpose sai, làm dữ liệu không truy xuất được |
| **Decrypt** | Đọc dữ liệu đã mã hóa | Tiếp cận plaintext hoặc DEK tương ứng |
| **GenerateDataKey** | Cấp DEK và wrapped DEK theo KMS model | Có thể nhận plaintext DEK, tạo bản mã ngoài policy |
| **WrapKey** | Bọc DEK bằng KEK | Sử dụng KEK sai context, phát hành wrapped data keys không đúng |
| **UnwrapKey** | Khôi phục DEK khi được phép | Có thể đọc nhiều DEK và dữ liệu lịch sử |
| **Sign** | Tạo chữ ký được ủy quyền | Giả mạo phát hành, token, manifest, chứng từ |
| **Verify** | Kiểm tra chữ ký/MAC bằng nguồn khóa thích hợp | Nếu thay trust registry có thể xác thực nhầm; raw HMAC key còn có thể tạo MAC |
| **GenerateMac** | Tạo MAC dưới HMAC key | Có thể tạo thông điệp giả được hệ thống tin |
| **VerifyMac** | Xác minh MAC qua KMS/HSM không xuất secret | Thường ít rủi ro hơn GenerateMac nếu API giữ secret; còn rủi ro oracle/lạm dụng tài nguyên |
| **DeriveKey/KeyAgreement** | Dẫn xuất shared/session/subkeys | Có thể mở rộng phạm vi khi root/static secret dùng cho nhiều mục đích |
| **Export/ImportKey** | Migration/backup theo quy trình | Export có thể làm lộ raw key; import sai có thể thay key material tin cậy |
| **Create/UpdateGrant** | Cấp thao tác mật mã có thời hạn | Có thể vượt qua hạn chế bằng tự cấp quyền |
| **PutKeyPolicy/ChangeTrust** | Đổi quyền hoặc nguồn tin cậy | Có thể nâng quyền và chuyển trust sang attacker |
| **Disable/ScheduleDeletion/Destroy** | Ngừng sử dụng hoặc xóa theo lifecycle | Có thể gây mất dữ liệu, gián đoạn dịch vụ |
| **Recovery/Backup admin** | Khôi phục khả năng giải mã | Có thể vượt IAM thường hoặc lấy recovery material |
| **Audit delete/retention change** | Quản trị nhật ký | Có thể che giấu lạm dụng trước đó |

**Các tên API chỉ đại diện khái niệm.** KMS/HSM của từng nhà cung cấp hỗ trợ tên action, key type, grant constraints và semantics khác nhau; khi review phải ánh xạ **quyền thực tế của provider**, không tự áp dụng bảng tên này như chính sách IAM.

### 5.1. Decrypt và Sign không nên được hiểu giống nhau

**Decrypt/Unwrap** có thể gây lộ bí mật; **Sign/GenerateMac** có thể gây giả mạo nguồn. Một tài khoản chỉ cần **Verify chữ ký số** thường không cần quyền Sign/private key. Một service chỉ phát hành ciphertext mới có thể không cần quyền đọc toàn bộ lịch sử.

Trong hệ thống HMAC, nếu phía kiểm tra có **raw HMAC secret**, về mặt mật mã nó cũng có thể tạo MAC; chính sách “Verify-only” thực sự cần **ranh giới API không xuất key**, như KMS/HSM hỗ trợ nếu phù hợp.

### 5.2. Quyền quản trị là đường nâng quyền gián tiếp

Đừng giới hạn truy vấn access review thành:

~~~text
Who has Decrypt?
Who has Sign?
~~~

Phải thêm:

~~~text
Who can change policy/grants so they can get Decrypt or Sign?
Who can assume a role that has those permissions?
Who can replace trusted verification keys?
Who can read recovery shares or backup key material?
Who can change audit retention or disable logging?
~~~

Một người không có Decrypt trực tiếp nhưng có thể tạo grant cấp cho chính mình **vẫn là principal rủi ro cao**.

## 6. Effective access: quyền thực tế khác quyền khai báo

### 6.1. Vì sao chỉ xem IAM policy là chưa đủ?

Một principal có thể được quyền từ nhiều đường:

- Gán quyền trực tiếp.
- **Group membership** và nested groups.
- Vai trò được **assume** hoặc quyền qua federation.
- Trust relationship giữa accounts/projects/organizations.
- **Resource-based policies** ở KMS key hoặc secret store.
- **Grants** được tạo ngoài quy trình thường lệ.
- Permission inheritance từ namespace/partition.
- External identity provider và workload identity federation.
- Session credentials còn hiệu lực.
- **Break-glass** hoặc recovery channel.
- Quyền trực tiếp trên HSM console, smart card, backup vault.

~~~mermaid
flowchart LR
    P["Principal: billing-worker"] --> G["Nhóm / assumed role"]
    P --> F["Federated identity / session"]
    G --> I["Identity policy"]
    F --> I
    I --> E{"Effective permission evaluation"}
    K["KMS key policy / grants"] --> E
    C["Conditions: key ID, context, region"] --> E
    E --> A["Decrypt / Unwrap / Sign / Admin actions"]
    A --> B["Business authorization vẫn cần riêng"]
~~~

**Effective permission** được xác định bằng **ngữ nghĩa cấp/deny/condition của nền tảng IAM cụ thể**, không thể kết luận từ phép **hợp (union) đơn giản** của mọi policy. Ví dụ các cơ chế explicit deny, permissions boundary hoặc session policies có thể hạn chế quyền; một số resource grants lại mở những đường khác. Reviewer phải sử dụng **công cụ phân tích quyền thực tế** phù hợp provider và xác nhận những điều kiện ảnh hưởng tới quyết định.

### 6.2. Đọc quyền như đồ thị

Một đồ thị có thể có đường:

~~~text
contractor account
     -> federated identity
     -> group "platform-operators"
     -> assume role "kms-admin-prod"
     -> permission to edit key grants
     -> grant Decrypt to secondary principal
     -> KMS Unwrap production KEKs
~~~

Nếu chỉ kiểm tra danh sách principal **trực tiếp** gắn vào key, reviewer có thể bỏ sót toàn bộ đường này.

Cần xây dựng **access path** tới quyền nguy hiểm, bao gồm quyền trung gian như AssumeRole, CreateGrant, PassRole, credential impersonation, read secret và edit policy.

### 6.3. Effective access cần xét điều kiện

Ví dụ cùng một role có thể có quyền:

~~~text
Decrypt key K
IF environment=production
AND workload identity=billing-reader
AND encryption context tenant=tenant-A
AND session time < approved expiration
~~~

Kết luận “role có Decrypt” mà không xét điều kiện có thể **quá báo**; kết luận “role chỉ có Decrypt tenant A” khi encryption context do caller tùy ý đặt lại có thể **bỏ sót**. Review nên kiểm tra **nguồn dữ liệu tạo condition** và khả năng attacker vượt điều kiện.

### 6.4. Deny, allow và unknown phải được ghi khác nhau

Khi không có quyền liệt kê grant ở một account hoặc region, kết quả đúng là **INSUFFICIENT_EVIDENCE**, không phải “không có quyền”. Khi tool không mô phỏng được điều kiện phức tạp, nên đánh dấu **NEEDS_MANUAL_VERIFICATION**, không tự coi quyền đã bị chặn.

Để đánh giá access chính xác cần hiểu các nguồn:

| Dạng bằng chứng | Giá trị | Hạn chế |
| --- | --- | --- |
| Declared IAM policy | Cho biết policy được viết như thế nào | Chưa xét tất cả đường quyền |
| Effective permission analyzer | Phân tích quyền khả dụng theo provider | Có thể không bao phủ điều kiện ngoài IAM |
| KMS/HSM access log | Cho biết thao tác thực sự đã xảy ra | Không chứng minh quyền chưa từng được dùng là vô hại |
| Runtime negative test | Xác nhận trường hợp DENY cụ thể | Không tự chứng minh mọi principal/condition |
| Inventory + owner approval | Chứng minh quyền được chấp thuận | Không chứng minh grants runtime khớp approval |
| Business resource authorization test | Chặn đọc sai tenant/record | Không thay KMS resource-level IAM |

## 7. Scope: những ranh giới cần bao phủ

### 7.1. Chọn population đầy đủ

Một access review phải xác định rõ:

- Tất cả **production accounts/projects/subscriptions** thuộc scope.
- Key regions/partitions, bao gồm key replica và HSM partitions.
- Data stores, backup vaults và recovery regions.
- KMS aliases/versions, keys trong trạng thái Active/Disabled/PendingDeletion.
- Workload identities, con người, groups, service accounts, external principals.
- Key classes: DEK, KEK, root, signing, HMAC, static DH/PSK, recovery materials.
- Admin/trust/config actions ngoài tác vụ Encrypt/Decrypt.
- Quyền tồn tại ngoài IAM thường: card/token vật lý, break-glass và offline secret shares.

Nếu chỉ chọn các keys đang **ACTIVE**, reviewer có thể bỏ sót quyền Unwrap các KEK retired nhưng vẫn mở được backup.

### 7.2. Đối soát key inventory hai chiều

~~~text
Approved key inventory ── join(key ID/version) ── Actual KMS/HSM
          |                                      |
      Inventory-only                          Actual-only
     Stale/missing key                        Unregistered key
          \                                      /
             Cần điều tra scope, owner, grants
~~~

Mỗi key nên có **owner, custodian, purpose, environment, tenant scope, cryptoperiod, state, key usage, recovery dependencies và approval references**. Nếu không biết owner, không thể recertify quyền một cách đáng tin.

### 7.3. Access review của trust cũng là access review

Một role có thể **không Sign** nhưng có quyền **thay public verification key** hoặc trust store; nó có thể khiến verifier tin một signer giả. Do đó scope cần bao gồm **PKI/JWKS registry, trust anchors, certificate issuance và signer registration**.

Tương tự, quyền sửa **TLS server identity/certificate**, hoặc tắt certificate validation ở client, có thể phá xác thực peer trong key establishment dù private keys được bảo vệ tốt.

## 8. Tần suất rà soát: định kỳ, theo sự kiện và liên tục

Không có một nhịp review chuẩn cho mọi tổ chức. Tần suất phụ thuộc **phạm vi tác động, mức đặc quyền, thời gian tồn tại credential, dữ liệu và mức biến động**.

### 8.1. Một lịch theo rủi ro minh họa

| Nhóm quyền | Nhịp ví dụ | Trigger bổ sung |
| --- | --- | --- |
| Root/KEK HSM admin, CreateGrant, ScheduleDeletion | Hàng quý hoặc thường xuyên hơn theo rủi ro | Bất kỳ key policy hoặc custody change |
| KMS Decrypt/Unwrap/Sign trên production nhạy cảm | Hàng tháng/quý với giám sát liên tục | Role change, key misuse, grant mới |
| KMS Encrypt/GenerateDataKey giới hạn theo service | Theo vòng review của workload | Workload deploy, tenant scope change |
| Public verification/trust registry admin | Theo thay đổi + review định kỳ | CA/JWKS/cert rotation |
| Break-glass/recovery operator | Sau mỗi lần sử dụng và theo kỳ đặc biệt | Incident/restore/key ceremony |
| Non-human service identities | Định kỳ theo service lifecycle | Decommission, secret expiry, owner change |
| Quyền vào backup/escrow vật liệu khóa | Theo data retention và sensitivity | Recovery test fail, custodian departure |

Các mốc trên **chỉ là phương án quản trị tham khảo**, không phải một yêu cầu pháp lý hoặc tiêu chuẩn cụ thể. Nếu nhóm vận hành đã có automated permission drift detection, một số chênh lệch có thể được phát hiện gần thời gian thực; **quyết định rủi ro** vẫn cần người chịu trách nhiệm.

### 8.2. Những sự kiện cần review ngay

- Nhân viên **joiner–mover–leaver**: vào nhóm, chuyển vị trí, nghỉ việc.
- Workload bị thay owner, kết thúc dự án, thay service account hoặc chuyển region.
- Tạo grant mới hoặc thay **KMS key policy, trust anchors, signing key**.
- Private key/DEK bị nghi lộ hoặc quyền KMS Sign/Decrypt được sử dụng bất thường.
- **Rotation, revocation, emergency disable, break-glass**.
- Triển khai **KMS/HSM provider mới**, migration tài khoản hoặc backup/recovery redesign.
- Phát hiện **key inventory mismatch**, orphan keys hoặc ngoại lệ đã hết hạn.
- Một service bắt đầu xử lý **dữ liệu nhạy cảm hơn hoặc nhiều tenant hơn**.
- Lỗ hổng ở identity federation hoặc quyền quản trị cloud thay đổi.
- Kiểm tra audit phát hiện **shared admin account** hoặc thao tác không có ticket.

### 8.3. Không chờ kỳ review khi có lạm dụng

Nếu đang có bằng chứng **Decrypt trái phép**, phải kích hoạt **incident response ngay**, cô lập principal/grant, bảo vệ logs và đánh giá dữ liệu; không chờ chủ tài khoản “recertify” trong email hàng quý. Access review sau đó tìm **nguyên nhân và kiểm soát đã bỏ sót**.

## 9. Quy trình access review đầu-cuối

### 9.1. Các bước tổng quát

1. **Xác định baseline**: policy version, IAM expectations, cryptographic usage và key inventory được phê duyệt.
2. **Định nghĩa scope**: môi trường, accounts, services, keys, tenants, action categories, review date.
3. **Thu evidence từ nguồn tin cậy**: actual grants, group paths, role assumptions, KMS/HSM key attributes, audit.
4. **Chuẩn hóa entitlement**: principal, key ID/alias/version, action, conditions, source, time, effective privilege.
5. **Đối soát với owner/custodian**: người chịu trách nhiệm và lý do nghiệp vụ.
6. **Phân loại rủi ro**: quyền trực tiếp, quyền nâng cấp gián tiếp, data scope và blast radius.
7. **Ra quyết định**: KEEP, REDUCE, REVOKE, TIME_BOUND, NEEDS_INVESTIGATION hoặc APPROVED_EXCEPTION.
8. **Phê duyệt thay đổi**: kiểm soát SoD và xác minh người duyệt có thẩm quyền.
9. **Thực thi thay đổi** trong IAM/KMS/HSM, trust registry và các đường credential liên quan.
10. **Kiểm tra lại effective access** qua snapshot hoặc negative test phù hợp.
11. **Ghi evidence và closure** với owner, deadline, actual effect và reviewer độc lập.
12. **Giám sát sau review**, cập nhật inventory, metrics và lần review kế tiếp.

~~~mermaid
flowchart TD
    A["Trigger / Review scope"] --> B["Key inventory + policy baseline"]
    B --> C["Observed IAM/KMS/HSM/trust paths"]
    C --> D{"Đủ và đáng tin evidence?"}
    D -->|"Không"| GAP["INSUFFICIENT_EVIDENCE"]
    D -->|"Có"| E["Analyze effective permissions + SoD + usage"]
    E --> F["Owner/independent reviewer quyết định"]
    F --> G{"Keep / Reduce / Revoke / Investigate?"}
    G -->|"Keep hợp lý"| K["Recertify có expiry + evidence"]
    G -->|"Reduce/Revoke"| H["Change IAM/grants/credentials"]
    G -->|"Investigate"| I["Security assessment / incident response"]
    H --> J["Retest effective access + DENY"]
    J --> L["Closure evidence + review packet"]
    K --> L
    I --> L
    GAP --> L
    L --> M["Monitoring / next review trigger"]
~~~

### 9.2. Cách xử lý bằng chứng thiếu

Nếu một HSM partition không trả grants cho reviewer, không được báo **PASS** chỉ vì không thấy tài khoản nào có quyền. Ghi **INSUFFICIENT_EVIDENCE**, nêu account/partition bị thiếu, yêu cầu evidence có phạm vi đọc phù hợp và báo hạn xử lý.

Nếu phát hiện actor có quyền quá rộng nhưng snapshot không xác định điều kiện thật, gắn **NEEDS_MANUAL_VERIFICATION** và hạn/owner. Không được **hợp thức hóa quyền** bằng một approval được tạo sau khi đã phát hiện mà không có phân tích rủi ro.

### 9.3. Review record phải gắn phiên bản chính sách

Một entitlement có thể được coi là hợp lệ theo **policy v2** nhưng trở thành quá rộng khi **policy v3** yêu cầu tenant isolation. Review cần lưu:

~~~text
reviewId
reviewAsOf + timezone
policyVersion + effectiveDate
scope + population
entitlement snapshot source/time
reviewer/approver identity
decision + justification
remediation + retest evidence
nextReviewDate / trigger
~~~

Thiếu phiên bản chính sách khiến lịch sử khó được tái hiện, nhất là sau khi role/policy thay đổi.

## 10. Rà soát quyền theo vòng đời nhân sự và workload

### 10.1. Joiner–mover–leaver (JML)

**Joiner:** chỉ cấp quyền sau khi xác nhận job function, owner approval, khóa cụ thể và điều kiện. Tránh sao chép tất cả quyền của người tiền nhiệm.

**Mover:** khi chuyển nhóm, thực hiện **remove-before-add** hoặc kế hoạch đồng bộ quyền có kiểm soát. Không mặc định cộng vai trò mới lên mọi vai trò cũ. Kiểm tra IAM group, HSM operator card, recovery shares và trust administration.

**Leaver:** thu hồi quyền console, token, assumed roles, offline shares và account đã cấp. Cần xem **service accounts do người đó quản lý**; khóa tài khoản người dùng không tự thu hồi shared credentials.

### 10.2. Non-human identities

Service account thường không có “manager” theo nghĩa con người; vì thế phải có:

- **Workload owner** và hệ thống/namespace chịu trách nhiệm.
- Danh sách key IDs/purpose cần dùng.
- **Credential lifecycle**: expiry, rotation, federation/secretless khi có thể.
- Quyền theo environment và tenant, không dùng chung staging–production.
- Kiểm tra trạng thái dịch vụ: active, decommissioned, replacement.
- Audit cho **workload–key–operation** thay vì chỉ người quản trị console.
- Thời hạn và review theo service deployments/migration.

Một pipeline CI/CD có quyền Sign release không cần giữ quyền **Decrypt customer database**. Một worker đã xóa khỏi cluster nhưng service account/token vẫn tồn tại là **orphaned privilege**.

### 10.3. External principals và federation

Đối tác hoặc vendor có thể cần quyền hỗ trợ thời hạn ngắn. Review nên kiểm tra:

- Trust relationship có được duyệt và có scope môi trường không?
- Quyền được **assume** qua principal thực hay shared credential?
- Key ID, action, condition và thời gian hết hạn có hạn chế?
- Có phương án revoke khi hợp đồng hoặc ticket kết thúc?
- Audit có phân biệt đối tác nào thực hiện thao tác?
- Có chính sách tránh vendor cấp quyền cho principal thứ ba?

Không chỉ gỡ tên vendor khỏi bảng quản trị mà bỏ sót **role trust policy** hoặc token còn hiệu lực.

## 11. Phân tách nhiệm vụ, dual control và quyền khẩn cấp

### 11.1. Separation of duties (SoD)

Những tổ hợp quyền nên được xem xét đặc biệt:

| Tổ hợp | Nguy cơ |
| --- | --- |
| **Grant administrator + Decrypt** | Tự cấp/mở rộng quyền đọc dữ liệu |
| **Signer + trusted verifier registry editor** | Tạo chữ ký giả và thay khóa tin cậy |
| **Key destroyer + recovery evidence editor** | Phá dữ liệu và sửa dấu vết |
| **KMS admin + audit deletion** | Lạm dụng khóa và che giấu log |
| **Security approver + self-requester** | Tự phê duyệt thay đổi rủi ro |
| **HSM recovery shares holder + sole operator** | Vượt quorum/đơn điểm quyền |
| **Application admin + unrestricted tenant KMS Unwrap** | Bypass phân quyền dữ liệu nhiều tenant |

Không phải mọi cặp vai trò trên đều **bất hợp pháp** trong mọi doanh nghiệp; quyết định phụ thuộc threat model và compensating controls. Tuy nhiên, reviewer cần nhận diện **khả năng tự nâng quyền và che giấu hành động**.

### 11.2. Dual control và quorum

Với root, master KEK hoặc private signing key trọng yếu, có thể yêu cầu:

- Hai người độc lập phê duyệt thay key policy.
- Quorum HSM cho recovery/export/destruction nếu provider hỗ trợ.
- Người thực thi và người xác nhận không phải cùng một identity.
- Break-glass được phê duyệt theo sự cố và có kiểm toán sau đó.

**Dual approval không đồng nghĩa split knowledge**. Secret sharing m-of-n chia khả năng tái tạo bí mật; dual approval chia trách nhiệm quyết định. Hệ thống có thể dùng cả hai.

### 11.3. Break-glass phải được review ngay sau dùng

Quyền khẩn cấp cần:

1. **Lý do/sự cố** và người chịu trách nhiệm.
2. Scope rõ (key, action, environment, tenant, thời gian).
3. Approval hoặc quy trình kích hoạt khẩn cấp được định nghĩa.
4. Ghi audit đầy đủ, bảo vệ integrity, không log raw key.
5. **Automatic expiry/revoke** nếu nền tảng hỗ trợ, cộng với xác minh thủ công.
6. Kiểm tra hành động đã thực hiện và dữ liệu bị tác động.
7. **Independent post-use review** và remediation nếu quyền còn tồn tại.

Không cấp một “super-admin dùng khi có chuyện” không có người sở hữu, không có lịch kiểm tra và không biết có thể gọi Decrypt/Sign trên những khóa nào.

## 12. Access review cho KMS/HSM và envelope encryption

### 12.1. Phân biệt DEK và KEK

Trong **envelope encryption**:

~~~text
Plaintext ----Encrypt(AES-GCM, DEK)----> Ciphertext + tag + nonce
DEK ----------Wrap(KEK in KMS)--------> WrappedDEK

Reader đã phân quyền:
  KMS Unwrap(wrapped DEK, đúng context/key policy)
  -> nhận plaintext DEK trong thời gian ngắn
  -> AES-GCM Decrypt với expected AAD
  -> xử lý plaintext khi tag hợp lệ
~~~

Những quyền phải review:

- Ai được **GenerateDataKey** và nhận plaintext DEK?
- Ai được **Unwrap/Decrypt KEK**?
- Đối với **wrapped DEK nào, thuộc tenant/resource nào**?
- Ai được **Rotate KEK, ChangePolicy, ScheduleDeletion**?
- Có quyền export raw DEK/KEK ở đường phụ nào?
- Có backup service giữ DEK/KEK lâu hơn cryptoperiod?
- KMS grants và application authorization có cùng ranh giới không?

### 12.2. KMS context không thay business authorization

Một **encryption context** có thể gồm tenant ID/purpose/environment; KMS kiểm tra nó theo API. Nhưng nếu caller **có quyền Decrypt và tự chọn context** hoặc context không ràng buộc danh tính, tenant isolation chưa chắc được bảo đảm.

Reviewer nên kiểm tra:

1. KMS grant có giới hạn key/action và các conditions khi hỗ trợ.
2. Ứng dụng dựng context từ **nguồn đã xác thực**.
3. Quyền **principal→tenant→object** được kiểm tra ở business layer.
4. **AES-GCM AAD** của bản mã dữ liệu liên kết resource đúng cách.
5. **Key version/nonce/tag** lưu đủ để giải mã hợp lệ và rotation.
6. Không cache plaintext DEK vô hạn sau khi grant bị thu hồi.

**KMS encryption context của wrapped DEK, AAD của ciphertext dữ liệu và business authorization là ba cơ chế khác nhau.** Access review phải đánh giá chúng phối hợp, không đánh dấu PASS vì chỉ có một.

### 12.3. Non-exportable không đồng nghĩa không sử dụng được

Private key hoặc KEK được giữ **non-exportable** trong HSM vẫn có thể được dùng qua API **Sign/Decrypt/Unwrap**. Một principal có quyền Sign quá rộng là rủi ro ngay cả khi raw private key chưa từng rời HSM.

Ngược lại, một principal có quyền **Verify** chữ ký Ed25519 bằng public key đáng tin không cần private key Sign; không nên nâng quyền vì “hai thao tác cùng một cặp khóa”.

### 12.4. Recovery pathways cần được review độc lập

Nếu bị mất KMS key nhưng có **backup/escrow/quorum shares**, người giữ các phần này có thể trở thành **con đường sử dụng khóa đặc quyền**, đôi khi vượt IAM thường ngày.

Review nên bao gồm:

- Ai được kích hoạt restore và ai phê duyệt.
- Bao nhiêu custodian/quorum cần tham gia.
- Các share còn đúng người giữ và có được thay khi leaver?
- Có thể phục hồi trong test mà không làm lộ raw key?
- Những bản backup của KEK thuộc môi trường/region nào.
- Ai có quyền xóa recovery material hoặc hủy bản sao cuối.
- Key dependencies có trong inventory/retention plan không.

**Không nên xóa mọi quyền đọc khóa cũ khi backup còn cần phục hồi**, nhưng phải hạn chế operation, người được phép và cửa sổ khôi phục. Quyền duy trì dữ liệu cũ không phải giấy phép Decrypt mọi thứ vô thời hạn.

## 13. Access review cho chữ ký số, HMAC, KDF và key agreement

### 13.1. Digital signatures

Một private signing key ký release manifest hoặc webhook là **định danh tin cậy**. Review phải hỏi:

- Workload nào có **Sign**, trên key ID nào?
- Có thể ký payload bất kỳ hay service xác thực **schema/purpose/issuer**?
- Ai được thay **public verification key/JWKS/trust anchor**?
- Có key cũ đang được dùng **Sign mới** sau rotation không?
- Có ngăn **cross-purpose signing** giữa token, release và chứng từ không?
- Người chỉ cần Verify có thật sự không có private signing material?

**Verify=true với public key do attacker cung cấp không chứng minh identity**; access review của trust registry quan trọng tương đương quyền Sign.

### 13.2. HMAC/MAC

Với HMAC key:

- Principal có **raw secret** có thể tạo MAC chứ không chỉ Verify.
- KMS/HSM hỗ trợ **GenerateMac/VerifyMac** riêng có thể giúp tách quyền.
- Secret chia sẻ giữa quá nhiều services tạo blast radius lớn.
- Rotation phải định nghĩa cửa sổ chấp nhận old tags, anti-replay và key IDs.
- Không cho nhóm debug/monitoring đọc HMAC secret để kiểm tra sự kiện.

Một hệ thống webhook có HMAC hợp lệ vẫn cần **timestamp/event ID/nonce hoặc idempotency** khi giao thức cần chống replay.

### 13.3. HKDF/root và derived keys

Một root/master secret dùng tạo khóa con qua HKDF cần review **quyền DeriveKey** vì người có quyền quá rộng có thể tạo khóa nhiều purpose/tenant.

Các nguyên tắc:

- Dùng **domain separation** rõ cho encrypt/MAC/wrap, tenant, version và role.
- Không để người dùng tự do chọn nhãn có thể chạm domain ngoài phạm vi.
- Hạn chế quyền gọi trên root; ưu tiên keys khác nhau cho các phạm vi rủi ro cao.
- Không coi HKDF nhanh là password-based KDF cho password yếu.
- Nếu root lộ, không giả định đổi nhãn HKDF làm an toàn dữ liệu cũ.

### 13.4. Key agreement và TLS

Private key X25519/ECDH có thể phục vụ key establishment. Với Java services thông thường, **TLS 1.3/JSSE** nên quản lý ephemeral keys/session secrets theo giao thức. Access review tập trung:

- Ai có quyền với **long-term signing credential/PSK**.
- Ai thay **TLS trust/config** hoặc bật key logging.
- Các session secrets có được xuất qua debug/monitoring không.
- Có shared TLS session keys/PSK được lưu không đúng mục đích không.
- Quyền đọc certificate private keys và keystore passwords có giới hạn không.
- Có xác thực đúng peer, tránh MITM trước khi cấp quyền nghiệp vụ không.

**Forward secrecy** trước việc lộ long-term signing key không bảo vệ traffic nếu attacker đã lấy **session keys/traffic secrets** từ log hoặc chiếm endpoint khi phiên đang hoạt động. Access review phải xét đường tiếp cận những secrets đó, không chỉ certificate management.
## 14. Quyết định access review: giữ, giảm, thu hồi hay điều tra?

Một reviewer không nên chỉ chọn “Approve” hoặc “Reject” cho cả vai trò. Entitlement cần được quyết định ở **độ hạt hợp lý**, gắn với key/action/context.

### 14.1. Các quyết định phổ biến

| Quyết định | Khi nào dùng? | Hành động và bằng chứng |
| --- | --- | --- |
| **KEEP / RECERTIFY** | Quyền còn cần, đúng key/action/context và chưa vượt policy | Owner xác nhận justification + review date |
| **REDUCE** | Chỉ cần một phần key IDs, tenants hoặc actions hiện tại | Thu hẹp grant, kiểm tra đường quyền khác |
| **REVOKE** | Không còn nhiệm vụ, principal nghỉ việc, key retired hoặc entitlement không được phê duyệt | Thu hồi grant/role/token và kiểm tra DENY |
| **TIME_BOUND** | Chỉ cần trong maintenance/recovery window | Grant có expiry, ticket, audit, xác nhận hết hạn |
| **REQUIRE_SECOND_APPROVAL** | Sign/Destroy/root operation có blast radius lớn | Tách approver/executor, dual control |
| **INVESTIGATE** | Quyền bất thường hoặc audit có dấu hiệu lạm dụng | Security assessment/incident response |
| **INSUFFICIENT_EVIDENCE** | Thiếu IAM path, key owner, policy snapshot | Thu evidence; không PASS |
| **APPROVED_EXCEPTION** | Rủi ro đã được chấp thuận đúng scope/expiry | Có risk owner và compensating controls, không giả an toàn |

### 14.2. Justification không nên mơ hồ

Justification yếu:

> Tài khoản này thuộc đội backend, cần quyền Decrypt.

Justification có thể kiểm chứng:

> Workload billing-reader-prod được phép Unwrap DEK của tenant A thuộc tập hóa đơn được ứng dụng phân quyền; key ID nằm trong danh sách billing KEK production được kiểm soát, chỉ cần Decrypt/Unwrap; không cần Sign, Export, ChangePolicy hoặc quyền trên tenant B. Quyền có owner và review date, được đối soát với ticket và audit.

Một bản review nên ghi **tài nguyên, thao tác, principal, business need, approval, scope và thời hạn**; không dựa vào việc tài khoản “ít khi dùng” để kết luận quyền vô hại.

### 14.3. Thu hồi quyền có thể ảnh hưởng availability

Giả sử KEK-v1 đã ngừng dùng để **Wrap dữ liệu mới** nhưng backup lịch sử vẫn cần **Unwrap** trong recovery. Access review có thể giảm quyền thường trực thành đường **restore-only có approval** thay vì xóa mọi khả năng truy cập.

**Không tự động hủy khóa, xóa backup hay khóa emergency recovery chỉ vì quyền ít sử dụng.** Cần đánh giá key dependencies, ownership, retention và kế hoạch ứng phó trước khi thực hiện thay đổi có thể không đảo ngược.

### 14.4. Mỗi quyết định phải có closure criteria

Đối với **REVOKE**, việc reviewer nhấn nút Reject không chứng minh quyền đã bị thu hồi. Closure nên có:

1. Change/ticket được phê duyệt.
2. Quyền trực tiếp và đường kế thừa được xóa hoặc hạn chế.
3. Credential/session/grant cache có hiệu lực được đánh giá và xử lý.
4. Một snapshot effective permission mới và/hoặc negative test cho action/key tương ứng.
5. Audit xác nhận hành động và người thực hiện.
6. Người có trách nhiệm độc lập xác minh phạm vi đã đạt.

Với **KEEP**, closure cần **business justification và approval còn hiệu lực**. Với **INVESTIGATE**, cần kết quả điều tra và quyết định tiếp theo, không dừng ở một status không có deadline.

## 15. Evidence, audit và tính toàn vẹn của access review

### 15.1. Thu đúng dữ liệu, không xuất key

Một chương trình access review thường cần:

| Evidence | Mục đích | Không cần lấy |
| --- | --- | --- |
| IAM effective permission report | Hiểu quyền sau khi kết hợp policies/conditions | Access tokens, private credentials |
| KMS key policies và grants | Biết ai có quyền theo key ID và operation | Raw KEK/DEK |
| HSM partition/roles metadata | Kiểm tra operator và quorum | HSM root secret/recovery shares |
| Key inventory | Đối chiếu owner, custodian, state, purpose, cryptoperiod | Plaintext keys |
| Joiner–mover–leaver records | Kiểm tra chủ thể còn hoạt động và thuộc nhóm nào | Dữ liệu nhân sự không cần thiết |
| Application authorization mapping | Xác nhận principal–tenant–resource | Plaintext hóa đơn khách hàng |
| KMS/HSM usage events | Điều tra quyền đã được dùng ra sao | Secret/payload nhạy cảm |
| Change approvals/tickets | Xác định ai đã phê duyệt grant | Password, unredacted tokens |
| Trust registry metadata | Xác định người có thể đổi public key/CA | Private signing keys |
| Backup/restore results | Kiểm tra khả năng khôi phục hợp lệ | Recovery material dạng rõ |
| CI/runtime negative tests | Chứng minh DENY/least privilege | Production keys và key logs |

Dữ liệu như **principal IDs, tenant IDs, key IDs** có thể vẫn nhạy cảm ở mức metadata. Chỉ phát cho reviewers có quyền và lưu theo retention policy; không đăng nguyên permission graph lên kênh công khai.

### 15.2. Snapshot phải có provenance

~~~yaml
evidenceId: access-review-kms-snapshot-example
reviewId: key-access-review-2026q4-example
collectedAt: "2026-11-28T02:00:00Z"
sourceType: EFFECTIVE_IAM_AND_KMS_GRANTS
sourceRef: "evidence-store://immutable/reference"
scope:
  environment: production
  services:
    - billing-api
    - payment-worker
  accountScope: "production-account"
  regionScope: "approved-key-regions"
collectorRole: security-readonly-reviewer
coverage: COMPLETE_FOR_DECLARED_SCOPE
containsRawKeyMaterial: false
integrityEvidenceRef: "evidence-store://integrity-proof"
policyBaselineVersion: "key-access-policy-v3"
~~~

Đây là **dữ liệu giả định để học**, không phải định dạng bắt buộc. Trường integrityEvidenceRef không tự chứng minh evidence đúng; hệ thống cần **kiểm chứng** chữ ký/bảo vệ bất biến/quyền tạo evidence và lưu provenance.

### 15.3. Audit trail phải phản ánh thao tác thật

Một access review có thể có các sự kiện:

~~~text
REVIEW_STARTED
SCOPE_DEFINED / BASELINE_SELECTED
ENTITLEMENT_SNAPSHOT_COLLECTED
OWNER_DECISION_RECORDED
SECURITY_ESCALATION_CREATED
GRANT_CHANGE_APPROVED
GRANT_REVOKED_OR_REDUCED
EFFECTIVE_ACCESS_RETESTED
INDEPENDENT_VERIFICATION_COMPLETED
REVIEW_SIGNED_OFF
~~~

Mỗi event nên mang **timestamp, reviewId, key/action/principal reference, actor role, decision, ticket/evidence reference và outcome**, theo chính sách privacy/security.

Không để một tài khoản có khả năng **CreateGrant + Decrypt + xóa audit log** vừa điều khiển thay đổi vừa xóa dấu vết. Audit cần quyền xem/sửa/xóa tách biệt và lưu trữ có tính toàn vẹn phù hợp.

### 15.4. Không suy luận từ “không thấy dùng”

Một quyền có thể **không xuất hiện trong usage logs** vì:

- Chức năng hiếm khi được gọi, như disaster recovery.
- Logging không đầy đủ hoặc retention quá ngắn.
- Principal thuộc account/region chưa thu thập.
- Service đang chờ lịch chạy cuối năm.
- Quyền được cấp nhưng chưa bị lạm dụng.

Vì vậy **unused ≠ unnecessary** và **unused ≠ safe**. Review cần business justification, owner và risk assessment; dữ liệu usage chỉ là một nguồn bổ sung.

## 16. Mẫu access review packet

Một bản review packet tốt phải trả lời được: **đã review ai, với quyền gì, theo policy nào, có bằng chứng nào, quyết định nào, ai thực thi và đã kiểm tra lại chưa**.

~~~yaml
reviewId: access-review-billing-2026q4-example
reviewType: periodic-plus-event-driven
reviewAsOf: "2026-11-28"
policyBaselineVersion: key-access-policy-v3
scope:
  environment: production
  keyClasses: [KEK, DEK, SIGNING, HMAC]
  services: [billing, payment, release-publisher]
  identityTypes: [HUMAN, WORKLOAD, EXTERNAL, EMERGENCY]
  includesAdminAndRecoveryPaths: true
reviewRoles:
  accountableOwnerRole: security-access-governance
  keyOwnerRole: billing-platform
  custodianRole: crypto-operations
  independentReviewerRole: security-assurance
coverage:
  declaredEntitlements: 180
  resolvedEffectiveEntitlements: 174
  missingEvidenceEntitlements: 6
  sourceRef: "evidence-store://review-snapshot"
decisions:
  keep: 147
  reduce: 13
  revoke: 8
  investigate: 6
  insufficientEvidence: 6
findings:
  - findingId: AR-001
    principalId: billing-maintenance
    keyId: billing-kek-prod
    operation: DECRYPT
    severity: HIGH
    reason: grant-not-approved-for-maintenance-role
    recommendedAction: REVOKE_AND_INVESTIGATE
    remediationOwnerRole: platform-security
    dueRef: "response-sla/high-risk"
    state: OPEN
  - findingId: AR-002
    principalId: former-crypto-operator
    resource: hsm-recovery-partition
    operation: RECOVERY_ADMIN
    severity: HIGH
    reason: owner-leaver-access-remains
    recommendedAction: REVOKE_RECOVERY_ACCESS_AND_VERIFY
    remediationOwnerRole: crypto-operations
    state: READY_FOR_RETEST
residualRiskRef: "risk-register/access-review-residual"
evidenceManifestRef: "evidence-store://immutable-review-manifest"
decisionApprovalRef: "change/access-review-signoff"
nextReviewTrigger: "next-window-or-material-permission-change"
~~~

Số liệu và tên trong ví dụ **không phản ánh hệ thống thực tế**. Một review có **missingEvidenceEntitlements** không thể được tuyên bố “100% pass” chỉ nhờ phần quyết định KEEP. Từng finding có thể có risk owner và residual risk khác nhau; packet cần giải thích rõ scope.

## 17. Java 17: bộ phát hiện sai lệch access snapshot theo key/operation

### 17.1. Bài toán mô phỏng

Đội security nhận hai nguồn dữ liệu đã được chuẩn hóa:

1. **Approved entitlements**: những cặp principal–key–operation–tenant đã được owner duyệt và còn trong thời hạn.
2. **Observed entitlements**: những quyền **được công cụ IAM/KMS thực tế xác định là có hiệu lực**, có nguồn và thời điểm thu thập.

Bộ phân tích sẽ phát hiện:

- Principal đã bị deactivated mà vẫn có quyền.
- Quyền xuất hiện nhưng **không nằm trong approved entitlements**.
- Quyền cấp từ nguồn **không rõ** hoặc snapshot không đầy đủ.
- Quyền tồn tại sau expiration.
- Sai environment hoặc tenant scope.
- Key không có owner/custodian hoặc không còn tồn tại trong registry.
- Operation nhạy cảm cần review rủi ro cao.
- Approval đã hết hiệu lực nhưng grants chưa thu hồi.
- Key ở trạng thái **retired** vẫn có quyền **Encrypt/Sign mới**.

**Đây là bộ kiểm tra trên snapshot đáng tin**, không phải hệ thống tự tính effective permissions từ JSON IAM. Nó chỉ **đề xuất findings** và không tự động sửa chính sách hoặc xóa khóa.

### 17.2. Mã Java 17

~~~java
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class KeyAccessReviewDemo {

    enum Operation {
        ENCRYPT, DECRYPT, WRAP, UNWRAP, SIGN, VERIFY,
        GENERATE_MAC, VERIFY_MAC, DERIVE_KEY,
        MANAGE_GRANTS, MANAGE_TRUST, DESTROY_KEY
    }

    enum KeyState {
        ACTIVE, LEGACY_READ_ONLY, DISABLED, DESTROYED
    }

    enum Severity {
        CRITICAL, HIGH, MEDIUM
    }

    record Principal(
        String id,
        String ownerTeam,
        boolean active,
        String environment
    ) {}

    record KeyAsset(
        String id,
        String ownerTeam,
        String custodianTeam,
        String environment,
        String tenantScope,
        KeyState state
    ) {}

    // Một grant đã được owner phê duyệt tại thời điểm review.
    // "validThrough" là ngày cuối được dùng, tính cả ngày đó.
    record Approved(
        String principalId,
        String keyId,
        Operation operation,
        String environment,
        String tenantScope,
        LocalDate validThrough,
        String approvalRef
    ) {}

    // Snapshot của quyền có hiệu lực đã được provider phân tích.
    // "expiresOn" dùng cùng quy tắc ngày cuối như validThrough.
    record Observed(
        String principalId,
        String keyId,
        Operation operation,
        String environment,
        String tenantScope,
        LocalDate expiresOn,
        String accessPathRef
    ) {}

    record Snapshot(
        LocalDate collectedAt,
        boolean coverageComplete,
        List<Observed> entitlements
    ) {}

    record Finding(
        String code,
        Severity severity,
        String principalId,
        String keyId,
        String explanation
    ) {}

    // Đối chiếu theo cả môi trường và tenant để không nhầm
    // một quyền dev với cùng tên principal ở production.
    private static String identity(
        String principal, String key, Operation operation,
        String environment, String tenant) {

        return String.join("|",
            principal, key, operation.name(), environment, tenant);
    }

    private static boolean highRisk(Operation operation) {
        return switch (operation) {
            case DECRYPT, UNWRAP, SIGN, GENERATE_MAC,
                 DERIVE_KEY, MANAGE_GRANTS, MANAGE_TRUST,
                 DESTROY_KEY -> true;
            default -> false;
        };
    }

    private static boolean createsNewMaterial(Operation operation) {
        return switch (operation) {
            case ENCRYPT, WRAP, SIGN, GENERATE_MAC -> true;
            default -> false;
        };
    }

    private static void add(
        List<Finding> findings,
        String code, Severity severity,
        Observed grant, String explanation) {

        findings.add(new Finding(code, severity,
            grant.principalId(), grant.keyId(), explanation));
    }

    static List<Finding> review(
        LocalDate reviewDate,
        Map<String, Principal> principals,
        Map<String, KeyAsset> keys,
        List<Approved> approved,
        Snapshot snapshot) {

        Objects.requireNonNull(reviewDate);
        List<Finding> findings = new ArrayList<>();

        long ageDays = ChronoUnit.DAYS.between(
            snapshot.collectedAt(), reviewDate);
        if (!snapshot.coverageComplete()
                || ageDays < 0 || ageDays > 7) {
            findings.add(new Finding(
                "EVIDENCE-SCOPE", Severity.HIGH,
                "*", "*",
                "Incomplete or stale/future-dated evidence snapshot"));
        }

        Map<String, Approved> approvals = new HashMap<>();
        for (Approved entry : approved) {
            String id = identity(
                entry.principalId(), entry.keyId(),
                entry.operation(), entry.environment(),
                entry.tenantScope());
            approvals.put(id, entry);
        }

        Set<String> seenObserved = new HashSet<>();
        for (Observed grant : snapshot.entitlements()) {
            String id = identity(
                grant.principalId(), grant.keyId(),
                grant.operation(), grant.environment(),
                grant.tenantScope());

            if (!seenObserved.add(id)) {
                add(findings, "DUPLICATE-EFFECTIVE-ENTRY",
                    Severity.MEDIUM, grant,
                    "Duplicate in normalized effective-access snapshot");
            }

            Principal actor = principals.get(grant.principalId());
            KeyAsset key = keys.get(grant.keyId());

            if (actor == null || !actor.active()) {
                add(findings, "INACTIVE-OR-UNKNOWN-PRINCIPAL",
                    Severity.HIGH, grant,
                    "No active trusted identity for observed access");
            } else if (!actor.environment().equals(
                    grant.environment())) {
                add(findings, "PRINCIPAL-ENVIRONMENT",
                    Severity.HIGH, grant,
                    "Principal environment differs from entitlement");
            }

            if (key == null) {
                add(findings, "UNKNOWN-KEY",
                    Severity.HIGH, grant,
                    "Key reference is absent from approved inventory");
                continue;
            }

            if (key.ownerTeam() == null
                    || key.ownerTeam().isBlank()
                    || key.custodianTeam() == null
                    || key.custodianTeam().isBlank()) {
                add(findings, "KEY-OWNER-CUSTODIAN",
                    Severity.MEDIUM, grant,
                    "Key owner or custodian is missing");
            }

            if (!key.environment().equals(
                    grant.environment())
                    || !key.tenantScope().equals(
                    grant.tenantScope())) {
                add(findings, "CROSS-SCOPE-ACCESS",
                    Severity.HIGH, grant,
                    "Environment or tenant scope does not match key");
            }

            if (key.state() == KeyState.DISABLED
                    || key.state() == KeyState.DESTROYED) {
                add(findings, "KEY-STATE",
                    Severity.HIGH, grant,
                    "Entitlement remains for disabled/destroyed key");
            } else if (key.state() == KeyState.LEGACY_READ_ONLY
                    && createsNewMaterial(grant.operation())) {
                add(findings, "LEGACY-WRITE",
                    Severity.HIGH, grant,
                    "Legacy key granted new Encrypt/Sign/Wrap/MAC");
            }

            Approved expected = approvals.get(id);
            if (expected == null) {
                add(findings, "UNAPPROVED-EFFECTIVE-ACCESS",
                    highRisk(grant.operation())
                        ? Severity.CRITICAL : Severity.HIGH,
                    grant,
                    "No matching approved principal-key-operation-scope");
            } else if (expected.validThrough() == null
                    || expected.validThrough().isBefore(reviewDate)) {
                add(findings, "APPROVAL-EXPIRED",
                    Severity.HIGH, grant,
                    "Owner approval is missing expiry or already expired");
            }

            if (grant.expiresOn() != null
                    && grant.expiresOn().isBefore(reviewDate)) {
                add(findings, "EXPIRED-GRANT-STILL-EFFECTIVE",
                    Severity.HIGH, grant,
                    "Effective privilege observed after grant expiration");
            }

            if (highRisk(grant.operation())
                    && (grant.accessPathRef() == null
                        || grant.accessPathRef().isBlank())) {
                add(findings, "MISSING-ACCESS-PATH",
                    Severity.MEDIUM, grant,
                    "Sensitive privilege has no traceable access path");
            }
        }
        return List.copyOf(findings);
    }

    public static void main(String[] args) {
        LocalDate today = LocalDate.of(2026, 11, 28);

        Map<String, Principal> principals = Map.of(
            "billing-reader", new Principal(
                "billing-reader", "billing", true, "production"),
            "former-operator", new Principal(
                "former-operator", "security", false, "production"),
            "maintenance", new Principal(
                "maintenance", "platform", true, "production"));

        Map<String, KeyAsset> keys = Map.of(
            "billing-kek", new KeyAsset(
                "billing-kek", "billing", "crypto-ops",
                "production", "tenant-A", KeyState.ACTIVE),
            "legacy-kek", new KeyAsset(
                "legacy-kek", "billing", "crypto-ops",
                "production", "tenant-A",
                KeyState.LEGACY_READ_ONLY));

        List<Approved> approved = List.of(
            new Approved("billing-reader", "billing-kek",
                Operation.UNWRAP, "production", "tenant-A",
                today.plusMonths(1), "change/approved-reader"));

        Snapshot snapshot = new Snapshot(
            today, true, List.of(
                // Đã được phê duyệt, đúng tenant.
                new Observed("billing-reader", "billing-kek",
                    Operation.UNWRAP, "production", "tenant-A",
                    today.plusMonths(1), "role/billing-reader"),
                // Quyền cũ của người đã nghỉ việc.
                new Observed("former-operator", "billing-kek",
                    Operation.MANAGE_GRANTS,
                    "production", "tenant-A", null,
                    "group/legacy-kms-admin"),
                // Quyền Decrypt chưa có owner approval.
                new Observed("maintenance", "billing-kek",
                    Operation.DECRYPT, "production", "tenant-A",
                    today.plusDays(7), "grant/maintenance"),
                // Có Encrypt mới trên key read-only.
                new Observed("maintenance", "legacy-kek",
                    Operation.ENCRYPT, "production", "tenant-A",
                    today.plusDays(7), "role/legacy-worker")));

        List<Finding> findings =
            review(today, principals, keys, approved, snapshot);

        System.out.println("Findings: " + findings.size());
        for (Finding f : findings) {
            System.out.println(
                f.severity() + " | " + f.code() + " | "
                + f.principalId() + " | " + f.keyId());
        }
    }
}
~~~

Kết quả dự kiến:

~~~text
Findings: 5
HIGH | INACTIVE-OR-UNKNOWN-PRINCIPAL | former-operator | billing-kek
CRITICAL | UNAPPROVED-EFFECTIVE-ACCESS | former-operator | billing-kek
CRITICAL | UNAPPROVED-EFFECTIVE-ACCESS | maintenance | billing-kek
HIGH | LEGACY-WRITE | maintenance | legacy-kek
HIGH | UNAPPROVED-EFFECTIVE-ACCESS | maintenance | legacy-kek
~~~

### 17.3. Code chứng minh điều gì?

1. **Phê duyệt theo độ hạt**: so sánh principal, key, operation, environment và tenant; không xem một approval tổng quát là đủ.
2. **Principal inactive** vẫn có effective grant → finding.
3. **ManageGrants** không được bỏ qua chỉ vì không trực tiếp Decrypt.
4. **Decrypt chưa được phê duyệt** trên KEK production là quyền rủi ro cao.
5. **Legacy key** không nên tiếp tục cấp quyền tạo bản mã/chữ ký mới trong mô hình read-only.
6. **Owner/custodian** của key phải tồn tại trong registry.
7. **Snapshot thiếu hoặc cũ** không được xem là PASS.
8. **Không có khóa bí mật** nào được đọc hoặc in trong công cụ review.
9. Hàm chỉ tạo **findings để con người kiểm tra**, không tự xóa grants.
10. Những quyền có approval phù hợp và không có sai lệch sẽ không tạo finding trong ví dụ.

### 17.4. Giới hạn cần hiểu trước khi áp dụng thực tế

- Các đối tượng **Principal, KeyAsset, Approved, Observed** trong demo giả định **được nạp từ hệ thống đáng tin**. Không được để người dùng tự khai active=true hoặc tự thêm approval.
- Effective permissions **không thể tính chính xác chỉ bằng cách hợp mọi policy**. Cần provider-specific evaluator hỗ trợ explicit denies, boundaries, resource policies, grants và điều kiện.
- Công cụ không tính **gián tiếp** đường AssumeRole → CreateGrant → Decrypt, không đọc HSM physical tokens hoặc backup vault. Production cần threat-driven graph analysis.
- Một quyền có trạng thái **DISABLED** có thể không gọi được KMS lúc đó; việc thấy entitlement trên key disabled là **finding cần làm rõ**, không tự khẳng định thao tác đang khả dụng.
- Cách dùng thời hạn **LocalDate validThrough** trong demo là quy ước “ngày cuối hợp lệ”. Production cần timestamp có múi giờ, session expiry và event time nhất quán.
- Approval trong demo chỉ được đối chiếu theo các trường chính; production phải xác minh **signature/issuer, ticket, trạng thái, approval scope, thời hạn và revocation**.
- Không kiểm tra nội dung ciphertext, **AES-GCM nonce/AAD/tag**, business authorization hay trust chain chỉ qua metadata grant.
- Không tự động thu hồi quyền trên production từ findings. Quyền recovery/bảo trì cần **impact assessment** và control khi thay đổi.
- Không thay được **KMS key policy/IAM**, không áp đặt quyền trên attacker đã lấy raw key/DEK.
- Cần xử lý alias/version, pagination, partial access, key replicas, độ trễ eventual consistency và duplicate grants theo provider.
- Baseline có thể cho phép **exceptions đã phê duyệt** có expiry; demo chưa mô hình hóa đầy đủ, nên không đánh dấu finding bằng “exception approved” chỉ vì có một chuỗi trong request.

Ví dụ này thể hiện nguyên tắc **“phân tích quyền đã cấp so với quyền được phép và tạo evidence rõ ràng”**, không phải hệ thống IAM simulator hoàn chỉnh.

## 18. Tình huống thực tế A: quyền KMS Decrypt bị mở rộng qua nhóm IAM

### 18.1. Bối cảnh

BillingService mã hóa hóa đơn bằng DEK, bọc các DEK dưới KEK production. Nhóm platform cấp quyền maintenance tạm thời trong một đợt sửa lỗi. Sau ba tháng, role vẫn có **Decrypt/Unwrap** trên nhiều key và có thể assume từ một nhóm lớn.

### 18.2. Access review phát hiện

- Key inventory và algorithm đều hợp lệ.
- KMS key non-exportable, nhưng quyền Decrypt/Unwrap của role vẫn hoạt động.
- Approval bảo trì đã hết hạn.
- Effective access path chạy qua **group → assume role → KMS grant**.
- Key usage logs có một số lời gọi sau đợt bảo trì.
- Business owner không xác nhận được nhu cầu hiện tại.

### 18.3. Xử lý đúng

1. Điều tra những lần gọi Decrypt có hợp lệ, dữ liệu/tenant nào bị ảnh hưởng.
2. Nếu có dấu hiệu misuse đang diễn ra, kích hoạt **incident containment ngay**.
3. Thu hồi grant và role assumption không cần thiết, không chỉ sửa một policy ở account con.
4. Giảm quyền maintenance sang **JIT + key IDs cụ thể + approved window**.
5. Kiểm tra toàn bộ **backup access, session credential và DEK cache** liên quan.
6. Xác minh lại **effective access** và negative tests cho Decrypt key không thuộc scope.
7. Ghi evidence, remediation owner, thời hạn và independent closure.

**Chỉ rotate KEK không xử lý nguyên nhân nếu KMS grant quá rộng được tạo lại trên KEK mới.**

## 19. Tình huống thực tế B: người giữ recovery material nghỉ việc

Một key custodian rời công ty. IAM console access đã bị thu hồi, nhưng nhân viên đó từng giữ **một recovery share offline** của root/KEK cấp cao.

Review cần xét:

- Đây có phải **split knowledge** với ngưỡng m-of-n không?
- Nếu một share bị lộ, có còn đủ ngưỡng để attacker tái tạo secret không?
- Có cần **replace/refresh shares** hoặc tái thiết lập recovery configuration theo quy trình?
- Custodian mới có đủ quyền vận hành mà không phá SoD không?
- Có kiểm soát nơi giữ share vật lý, smart cards và chain of custody không?
- Recovery test có thể tiếp tục khi mất một operator hoặc một site không?
- KMS grants/tokens/service accounts do người cũ quản lý có còn sống không?

Không coi “user bị disable” là đã xóa khả năng dùng **offline recovery materials**. Nhưng cũng không tự hủy root/KEK làm mất dữ liệu; phải có **key dependency analysis** và quy trình recovery/rotation được phê duyệt.

## 20. Tình huống thực tế C: signing pipeline và trust registry

Một release pipeline dùng **Ed25519 signing key** trong HSM để ký manifest bản phát hành. Release engineer có quyền gọi Sign. Một role của cùng pipeline được cấp **quyền sửa JWKS/trusted verification key registry** dùng bởi hệ thống tải artifact.

Vấn đề không chỉ là Sign:

- **Sign permission** có thể tạo chữ ký hợp lệ trên payload chưa được phê duyệt.
- **Edit trust registry** có thể thay public key verifier tin, cho phép một khóa giả mạo mới.
- Một principal có cả hai quyền làm tăng khả năng **tạo và hợp thức hóa artifact giả**, khó điều tra nếu còn xóa được audit.
- Nếu key dùng chung cho release và API tokens, quyền Sign có thể vượt **purpose separation**.

Phương án:

- Tách **release signer identity** khỏi **trust registry maintainer**.
- Ký payload có schema, source commit/build provenance và approval.
- Trust changes được kiểm tra độc lập, gắn release process và audit.
- Giới hạn Sign theo key ID/purpose và triển khai có hạn.
- Bảo vệ **private key non-exportable**, nhưng đồng thời kiểm tra **ai có thể gọi HSM Sign**.
- Negative tests: pipeline không thể Sign theo khóa token, không thể tự đổi trust anchor.
- Khi có sự cố, đánh giá **artifacts đã ký và khóa/trust từng được công bố**, không chỉ rotate signing key.

## 21. Tình huống thực tế D: thu hồi quyền trước khi hủy KEK cũ

Một KEK cũ ở trạng thái retired vẫn bảo vệ các wrapped DEKs trong backup. Một đợt access review dự định thu hồi tất cả quyền Unwrap vì “không còn dùng trong production”.

Cần phân biệt:

- **Encrypt/Wrap mới:** có thể bị cấm sau rotation.
- **Decrypt/Unwrap cũ:** có thể vẫn cần qua đường **restore-only**.
- **Key deletion:** phải có inventory dependency, owner approval và restore tests.
- **Emergency recovery operator:** cần quyền có giới hạn/thời hạn/quorum, không phải Decrypt toàn bộ 24/7.

Một kết quả review hợp lý có thể là:

~~~text
REVOKE: grants Unwrap thường trực của workloads không còn dùng.
KEEP_WITH_CONSTRAINT: quyền restore-only, chỉ khi có approval,
                      time-bound credentials, audit và key ID cụ thể.
VERIFY: chạy restore test với backup phiên bản cũ.
BLOCK: destroy KEK trước khi giải quyết dependencies.
~~~

**Access review tốt phải giảm rủi ro mà không vô tình phá khả năng khôi phục dữ liệu.**

## 22. Findings, remediation và xác minh đóng việc

### 22.1. Một finding có thể kiểm toán

~~~yaml
findingId: AR-2026-047-example
reviewId: access-review-billing-2026q4-example
policyVersion: key-access-policy-v3
principalId: billing-maintenance
identityType: WORKLOAD
resource:
  keyId: billing-kek-prod
  operation: UNWRAP
  environment: production
  tenantScope: multi-tenant
observedAccessPathRef: "evidence-store://snapshot/grant-path"
expectedScope: "approved-maintenance-window-only"
actualScope: "no-expiration"
severity: HIGH
findingType: EXCESS_PRIVILEGE
riskDescription: "Có thể unwrap DEK ngoài cửa sổ phê duyệt."
businessOwnerRole: billing-platform
remediationOwnerRole: iam-platform
recommendedDecision: REDUCE_OR_REVOKE
duePolicyRef: "risk-sla/high"
currentStatus: OPEN
changeApprovalRef: "change/restrict-kms-grants"
closureRequires:
  - effective-permission-snapshot
  - negative-access-test
  - independent-reviewer-verification
~~~

### 22.2. Severity phải phản ánh blast radius

| Mức | Tình huống thường thấy | Hướng hành động |
| --- | --- | --- |
| **CRITICAL** | Principal lạ có Sign/Unwrap/root admin quyền rộng và có dấu hiệu misuse | Incident response/containment ngay |
| **HIGH** | Quyền Decrypt/Sign không có approval, key policy admin có thể tự nâng quyền | Giảm quyền nhanh, điều tra usage và xác minh |
| **MEDIUM** | Expiry/owner thiếu hoặc access path chưa đầy đủ nhưng đã có hạn chế khác | Thu bổ sung evidence, sửa process/config |
| **LOW** | Metadata review không nhất quán không thay đổi effective rights | Cập nhật registry và kiểm tra lại |

Mức rủi ro **phụ thuộc loại khóa, dữ liệu, exposure, môi trường và hệ quả nghiệp vụ**. Một thiếu sót owner tưởng nhỏ có thể thành HIGH khi khiến root recovery không thực hiện được.

### 22.3. Phân biệt kết quả

- **OPEN:** sai lệch xác nhận và chưa được xử lý.
- **INVESTIGATING:** đang tìm nguồn quyền hoặc dữ liệu bị ảnh hưởng.
- **MITIGATED:** biện pháp tạm thời giảm rủi ro, còn nợ xử lý gốc.
- **READY_FOR_RETEST:** team thực thi tuyên bố đã sửa.
- **RESOLVED_VERIFIED:** quyền mới đã được kiểm chứng độc lập.
- **ACCEPTED_RISK:** risk owner đã chấp thuận có hạn, còn phải giám sát.
- **INSUFFICIENT_EVIDENCE:** chưa thể kết luận.

Không đóng finding bằng “đã gửi yêu cầu IAM” hoặc “chủ role xác nhận”. Cần **kiểm chứng quyền thực tế sau thay đổi**.

## 23. Metrics và báo cáo access review

### 23.1. Những chỉ số hữu ích

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Entitlement coverage** | Bao nhiêu quyền thực tế được review trong tổng population |
| **Owner/custodian coverage** | Bao nhiêu key/entitlement có người chịu trách nhiệm hợp lệ |
| **Unapproved high-risk grants** | Quyền Sign/Decrypt/Unwrap/Derive/Admin thiếu approval |
| **Stale privileges** | Quyền còn sau JML, dự án đóng hoặc expiry |
| **Excess-privilege reduction** | Quyền đã được giảm/xóa có xác minh |
| **Break-glass post-use review** | Quyền khẩn cấp được đóng và đối soát sau dùng |
| **Access drift detection time** | Thời gian từ grant sai đến phát hiện |
| **Remediation time by severity** | Tốc độ khắc phục sai lệch với mức rủi ro |
| **Repeat findings** | Quyền dư quay lại sau khi đã đóng finding |
| **Evidence completeness** | Review cases có đủ nguồn, scope và timestamp |
| **Independent closure rate** | Findings đã retest bởi người không tự thực thi |
| **Key lifecycle access alignment** | Key retired/revoked có giảm quyền dùng mới |
| **Emergency recovery readiness** | Khả năng phục hồi được duy trì trong phạm vi kiểm soát |

Một dashboard “100% access reviewed” có thể đánh lừa nếu hệ thống chỉ đếm **quyền trong inventory** mà không đếm các grants từ account khác. Hãy kiểm tra **population, denominator, account/region coverage và evidence limitations**.

### 23.2. Các tín hiệu cần giám sát liên tục

- Role mới có **Decrypt/Unwrap/Sign** rộng hơn approved profile.
- Bất thường trong CreateGrant, PutKeyPolicy, ChangeTrust hoặc ScheduleDeletion.
- Workload vừa decommission nhưng vẫn có KMS usage.
- Principal đã chuyển nhóm nhưng vẫn giữ HSM administrator privileges.
- Quyền tạm thời không bị thu hồi sau incident.
- Signing key retired còn bị dùng Sign mới.
- KEK key disabled nhưng ứng dụng vẫn decrypt nhờ DEK raw cache dài hạn.
- Backup operator vào KMS ngoài restore window.
- Trusted public key registry thay đổi ngoài change approval.
- Audit KMS bị tắt hoặc retention bị sửa bất thường.

Những tín hiệu này nên **tạo ticket/cảnh báo có owner**, không chỉ tăng số trên dashboard.

## 24. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| **Review danh sách role, không review effective permissions** | Bỏ sót quyền kế thừa/assume/grant | Phân tích đường quyền thực tế theo provider |
| **Chỉ review human users** | Workload/service accounts bị bỏ quên | Bao phủ non-human identities |
| **Không review admin/trust quyền gián tiếp** | Có thể tự cấp Sign/Decrypt | Xem CreateGrant, policy, trust và recovery |
| **Key owner tự duyệt quyền của mình** | Xung đột lợi ích | Review/approval độc lập tương xứng rủi ro |
| **Approve vì “trước giờ vẫn dùng”** | Kéo dài quyền thừa | Business need theo scope hiện tại |
| **Không lưu policy version** | Không tái hiện được quyết định | Baseline và effective dates rõ |
| **Coi KMS non-exportable là không có rủi ro** | API Decrypt/Sign bị lạm dụng | Kiểm tra usage grants và workload |
| **Chỉ quan sát usage, quyền không dùng thì PASS** | Quyền chưa dùng vẫn nguy hiểm | Dùng approval, threat model và least privilege |
| **Thu hồi chỉ từ một group** | Role assumption/token còn đường khác | Retest toàn bộ effective access path |
| **Tin tenant do caller tự khai** | Có thể cross-tenant access | Context từ identity/resource đã xác thực |
| **Coi Decrypt cấp quyền đọc mọi record** | Bỏ business authorization | Kiểm tra principal–tenant–object |
| **Không xem keystore/key logs** | Private/session secrets bị lộ qua debug | Secrets hygiene và runtime access review |
| **Không xét backup/recovery** | Mất hoặc vượt quyền phục hồi | Review custodian, quorum, restore paths |
| **Xóa tất cả quyền KEK retired ngay** | Không restore backup cũ | Tách write permissions và recovery-only |
| **Giữ break-glass grant vô hạn** | Admin access âm thầm tồn tại | JIT expiry, post-use review |
| **Review thiếu region/account vẫn PASS** | Bỏ sót grants | Mark INSUFFICIENT_EVIDENCE |
| **Không có remedation owner/deadline** | Finding kéo dài | SLA theo severity, escalation |
| **Đóng finding khi ticket vừa được tạo** | Quyền chưa thay | Retest, negative test và audit |
| **Dán raw DEK/private key vào evidence** | Review làm rò bí mật | Chỉ key IDs, metadata và redacted evidence |
| **Chỉ review định kỳ** | Grant xấu tồn tại nhiều tháng | Event-driven + drift detection |
| **Rotation key được coi là revoke mọi quyền** | Grant/quyền có thể vẫn rộng | Chỉnh IAM và kiểm tra data/key exposure |

## 25. Checklist triển khai access review cho key management

### Chuẩn bị và trách nhiệm

1. Có **policy/baseline version** và review window được phê duyệt chưa?
2. Scope bao phủ **environment, accounts, regions, partitions, tenants, providers** chưa?
3. Đã đưa tất cả **DEK/KEK/root/signing/HMAC/trust/recovery assets** vào phạm vi phù hợp?
4. Có danh mục **human, workload, service account, external và emergency principals**?
5. Mỗi key có **owner, custodian, purpose, state, cryptoperiod và dependency**?
6. Owner có hiểu **quyền và nhu cầu nghiệp vụ** trước khi quyết định keep?
7. Người review có độc lập với người tự cấp grant nhạy cảm không?
8. Có **risk-based cadence** và trigger ngay khi role/key/trust thay đổi?

### Effective access và least privilege

9. Đã xét quyền **trực tiếp, group, assumed role, cross-account, resource policy và grants**?
10. Có phân biệt **explicit deny/conditions/boundaries** theo ngữ nghĩa provider?
11. Có tìm quyền **nâng cấp gián tiếp** qua CreateGrant/ChangePolicy/AssumeRole không?
12. Decrypt/Unwrap có bị giới hạn key ID, tenant/purpose và môi trường?
13. Sign/GenerateMac có purpose scope, quyền payload và chính sách chứng thực đúng?
14. Verify có lấy public key/trust từ **nguồn được xác thực**?
15. DeriveKey/KeyAgreement/static secret có giới hạn root và key usage?
16. Export/Import, recovery và raw key access có policy/risk approval cụ thể?
17. Có phân biệt KMS IAM với **business authorization theo tenant và record**?
18. Có kiểm tra **KMS encryption context và AES-GCM AAD** được dựng từ nguồn tin cậy?
19. Có review cache DEK, session tokens, HSM cards và offline recovery shares?
20. Không còn **principal inactive, orphan service accounts hoặc shared admin credentials** ngoài chính sách?

### Vòng đời và sự cố

21. Quyền Encrypt/Sign mới có tuân thủ **key state và cryptoperiod**?
22. Với key retired, Decrypt/Verify/Unwrap lịch sử có bị hạn chế và audit?
23. Kế hoạch rotation có kiểm tra **revoke grants trên key cũ/mới**?
24. Trước khi thu hồi quyền recovery, có xét **backup KEK/DEK dependencies**?
25. Break-glass có time limit, audit và independent post-use review?
26. Khi phát hiện key misuse có chuyển **incident response ngay**?
27. Có phân biệt raw key compromise, key usage compromise và policy compromise?
28. Có đánh giá **session/credential caching** sau khi revoke?

### Evidence và closure

29. Evidence phản ánh **effective privileges** từ nguồn đáng tin và đúng phạm vi?
30. Có **timestamp, source, account, region, policy version và integrity reference**?
31. Review ghi **KEEP/REDUCE/REVOKE/TIME_BOUND/INVESTIGATE** với justification?
32. Thiếu evidence có được ghi rõ, không mặc định PASS?
33. Findings có severity, business owner, remediation owner và deadline?
34. Những findings rủi ro cao có compensating controls và escalation?
35. Thực thi grant changes qua quy trình phê duyệt, không tự thay quyền ngoài policy?
36. Đã lấy **snapshot mới và negative tests** sau khi revoke?
37. Closure có người xác minh độc lập và audit references?
38. Không đưa raw secret, password, recovery share hoặc token vào review packet?
39. Review packet thể hiện scope limitations và residual risk trung thực?
40. Có metrics về quyền thừa, remediation, access drift và repeat findings?
41. Có kế hoạch review theo kỳ tiếp theo và trigger theo sự kiện mới?
42. Có quy trình kiểm tra **key trust registry**, certificate lifecycle và HSM operators ngoài IAM thông thường?

## 26. Câu hỏi tự kiểm tra

**Câu 1.** Access review khác cryptographic policy review ở điểm nào?

**Đáp án:** Access review tập trung **ai đang có quyền gì trên key/tài nguyên nào, còn cần quyền không và quyền có được áp dụng đúng không**. Policy review còn đánh giá **bản thân yêu cầu/chính sách** về thuật toán, lifecycle, trust, recovery và cách thực thi có còn phù hợp.

**Câu 2.** KEK nằm trong HSM và non-exportable. Có cần review quyền Unwrap/Decrypt của workload không?

**Đáp án:** Có. Một workload có quyền Unwrap/Decrypt có thể dùng API để mở DEK hoặc dữ liệu dù không xuất được KEK. Bảo vệ key material không thay kiểm soát **key usage**.

**Câu 3.** Một user không có Decrypt trực tiếp nhưng có quyền CreateGrant cho chính mình. Có đáng xem là rủi ro cao không?

**Đáp án:** Có. Quyền quản trị có thể **tự nâng lên quyền dùng khóa**. Review phải phân tích đường quyền gián tiếp và kiểm soát SoD, không chỉ danh sách quyền Decrypt trực tiếp.

**Câu 4.** Một role được phép Decrypt KEK cho tenant A nhưng ứng dụng không kiểm tra invoice ownership. Access review có đủ để ngăn đọc sai invoice không?

**Đáp án:** Không. Access review hạn chế quyền sử dụng khóa, nhưng **business authorization** trên từng record vẫn phải được kiểm tra lúc xử lý yêu cầu. KMS context/AAD có thể bổ trợ, không thay toàn bộ quyền nghiệp vụ.

**Câu 5.** Vì sao một tài khoản đã nghỉ việc vẫn có thể tạo nguy cơ sau khi tắt login cá nhân?

**Đáp án:** Người đó có thể còn **shared service credential, assumed-role access, HSM smart card, offline recovery share hoặc token**. Quy trình leaver phải rà soát toàn bộ đường quyền.

**Câu 6.** Vì sao không được kết luận PASS khi một HSM region không cho reviewer liệt kê grants?

**Đáp án:** Đó là **INSUFFICIENT_EVIDENCE**. Không có quyền quan sát không chứng minh không có quyền nguy hiểm. Phải thu thêm evidence hoặc nêu rõ limitation.

**Câu 7.** Một quyền KMS Decrypt đã không được sử dụng suốt sáu tháng. Có thể tự thu hồi ngay mà không kiểm tra owner không?

**Đáp án:** Không nhất thiết. Nó có thể phục vụ disaster recovery ít khi dùng. Cần owner, data retention, backup dependencies và có thể chuyển sang **JIT restore-only** thay vì xóa khả năng khôi phục.

**Câu 8.** Chữ ký Ed25519 được Verify thành công với public key trong request. Đã xác thực người ký chưa?

**Đáp án:** Chưa. Public key phải đến từ **trust registry/certificate/JWKS đã được xác thực**. Quyền thay trust registry cũng cần access review.

**Câu 9.** Vì sao VerifyMac-only có thể khác quyền có raw HMAC key?

**Đáp án:** Ai có raw HMAC key có thể tính MAC cho thông điệp tùy ý. VerifyMac-only chỉ có ý nghĩa hạn chế khi API/KMS/HSM **giữ secret** và không cho principal tạo MAC hoặc xuất key.

**Câu 10.** Sau khi revoke grant KMS, có chắc plaintext DEK không còn tồn tại ở workload bị chiếm không?

**Đáp án:** Không. DEK có thể đã được lấy/cached trước đó hoặc attacker đã sao chép. Phải đánh giá **key usage/material compromise, cache, session và dữ liệu ảnh hưởng**, không chỉ IAM state mới.

**Câu 11.** Vì sao reviewer cần đánh giá quyền trên backup/recovery vault?

**Đáp án:** Một principal không có Decrypt thường ngày vẫn có thể **khôi phục KEK/root** qua backup/quorum và tiếp cận dữ liệu. Đây là đường quyền đặc quyền có thể nằm ngoài IAM của API trực tuyến.

**Câu 12.** Dual control có đồng nghĩa split knowledge không?

**Đáp án:** Không. Dual control yêu cầu **nhiều chủ thể độc lập phê duyệt/thực thi**; split knowledge chia khả năng tái tạo bí mật thành các phần. Cả hai có thể cùng được áp dụng cho HSM root/recovery.

**Câu 13.** Key cũ đã hết cryptoperiod cho Encrypt mới nhưng backup còn cần Unwrap. Access review xử lý thế nào?

**Đáp án:** Thu hồi/giảm quyền tạo dữ liệu mới, giữ **restore-only/legacy read có hạn** nếu chính sách cho phép, có approval/audit và kiểm tra khả năng restore trước khi hủy KEK.

**Câu 14.** Tại sao role có Sign và quyền sửa trusted JWKS lại nguy hiểm?

**Đáp án:** Nó có thể vừa **tạo chữ ký**, vừa **thay khóa mà verifier tin**, làm suy yếu separation of duties và provenance. Review phải xét cả key operation lẫn quyền quản trị trust.

**Câu 15.** Vì sao KeyAccessReviewDemo không thể dùng trực tiếp làm IAM engine production?

**Đáp án:** Code chỉ so sánh snapshot giả định đã đáng tin và approvals theo trường mô phỏng. Nó không giải đầy đủ **IAM semantics, key/resource conditions, cross-account, token sessions, physical access hoặc business authorization**, và không có quyền enforcing ở KMS.

**Câu 16.** Nếu reviewer đánh dấu REVOKE nhưng chưa kiểm tra quyền đã biến mất khỏi KMS, finding đóng được chưa?

**Đáp án:** Chưa. Cần **thực thi thay đổi, snapshot effective permission mới/negative test và xác minh độc lập**; một quyết định không tự thay runtime.

**Câu 17.** Khi nào nên kích hoạt incident response thay vì chỉ ghi access review finding?

**Đáp án:** Khi có bằng chứng hoặc nghi vấn hợp lý về **lạm dụng đang diễn ra, raw key compromise, quyền đặc biệt bị chiếm hoặc tác động dữ liệu**, cần containment/điều tra ngay; review tiếp tục đánh giá nguyên nhân và cải tiến.

**Câu 18.** Vì sao một review “100% completed” vẫn có thể không đáng tin?

**Đáp án:** Nếu population bỏ sót service accounts, cross-region keys, HSM recovery hoặc grants gián tiếp; nếu thiếu evidence nhưng vẫn được tính PASS; hoặc nếu closure không retest. Cần xem **scope, denominator và provenance**.

**Câu 19.** Access review có thay nhu cầu dùng AES-GCM nonce đúng hoặc TLS certificate validation không?

**Đáp án:** Không. Review quyền là một lớp quản trị. **Cryptographic correctness** (nonce/AAD/tag, trust, authenticated key establishment) và **authorization runtime** vẫn phải được kiểm tra/triển khai riêng.

**Câu 20.** Thế nào là một quyết định KEEP an toàn?

**Đáp án:** Principal vẫn hoạt động, nhu cầu nghiệp vụ cụ thể, key/action/tenant/environment đúng, approval còn hiệu lực, quyền không rộng hơn cần thiết, được đánh giá về SoD/nguồn quyền và có **thời điểm review tiếp theo**.

## 27. Kết luận

**Access review là quá trình xác nhận và điều chỉnh những quyền thực tế đang cho phép người hoặc workload sử dụng khóa mật mã.** Điều cốt lõi không phải số lượng role được ký duyệt, mà là **ai thật sự có thể Encrypt, Decrypt, Unwrap, Sign, GenerateMac, DeriveKey, Export, thay key policy hoặc khôi phục bí mật**, thông qua những đường quyền nào, với mục đích và thời hạn nào.

Một hệ thống Java dùng **KMS/HSM, DEK/KEK, envelope encryption, chữ ký số, HMAC, KDF và TLS** cần kết hợp **key owner/custodian, IAM effective permissions, business authorization theo tenant/resource, least privilege, separation of duties, just-in-time/break-glass governance và audit**. Review phải bao phủ cả **nhân sự, service accounts, quyền gián tiếp, trust registry, backup/recovery và vòng đời khóa**.

**Review chỉ được coi là hoàn tất khi các quyền đã được đánh giá trên bằng chứng đáng tin, sai lệch có người chịu trách nhiệm, hành động thay đổi đã thực thi và quyền thực tế được xác minh lại.** Giảm quyền không nên gây mất khả năng phục hồi dữ liệu; ngược lại, khả năng khôi phục cũng không phải lý do giữ Decrypt/Sign không giới hạn.
