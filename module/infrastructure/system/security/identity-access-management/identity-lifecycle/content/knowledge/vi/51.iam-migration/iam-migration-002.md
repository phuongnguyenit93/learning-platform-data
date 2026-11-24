# Di trú directory trong quản lý vòng đời danh tính (IAM)

> **Chương:** IAM migration  
> **Bài học:** Di trú directory  
> **Phạm vi:** Quản lý vòng đời danh tính theo Joiner–Mover–Leaver (JML), kết nối identity source, directory, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích directory giữ vai trò gì trong kiến trúc IAM và phân biệt **di trú directory** với thay nguồn dữ liệu danh tính hoặc thay IdP.
2. Xác định các phụ thuộc thường bị bỏ sót: LDAP bind, nhóm lồng nhau, SID/ACL, Kerberos, GPO, tài khoản dịch vụ, ứng dụng cũ và thiết bị.
3. Thiết kế bảng ánh xạ định danh giữa directory cũ và mới mà không dựa duy nhất vào email hay tên đăng nhập.
4. Chọn chiến lược di trú, tổ chức đồng tồn tại, đồng bộ và chuyển đổi quyền ghi có kiểm soát.
5. Chứng minh sau chuyển đổi, người dùng vẫn đăng nhập đúng, được cấp đúng quyền và bị thu hồi kịp thời khi trạng thái lao động thay đổi.
6. Xây dựng kế hoạch pilot, cutover, đối soát, khôi phục và nghiệm thu có thể kiểm chứng.

**Tình huống xuyên suốt:** Doanh nghiệp cần chuyển từ directory cũ sang directory mới. Người dùng có thể vẫn dùng cùng email, nhưng đối tượng tài khoản, mã đối tượng, nhóm, thông tin đăng nhập và quyền trên các hệ thống liên quan có thể thay đổi. Làm thế nào để tài khoản mới thật sự thuộc về đúng người và không làm mất kiểm soát truy cập?

## 2. Directory là gì và di trú directory thay đổi điều gì?

Directory là dịch vụ lưu trữ, tra cứu và quản lý các đối tượng như user, group, computer, service account cùng các thuộc tính, quan hệ thành viên và đôi khi cả thông tin phục vụ xác thực. LDAP là một giao thức thường dùng để truy cập directory; Active Directory (AD), các triển khai LDAP và cloud directory có kiến trúc, khả năng và giới hạn khác nhau.

| Thành phần | Nhiệm vụ điển hình | Câu hỏi khi di trú |
|---|---|---|
| **Identity source** | Xác nhận dữ liệu gốc như nhân sự đang làm việc, hợp đồng, ngày vào/nghỉ | Ai có thẩm quyền nói người này còn thuộc tổ chức không? |
| **Directory** | Chứa account, group, thuộc tính, quan hệ đối tượng; có thể tham gia xác thực | Object nào ở directory mới tương ứng với object cũ? |
| **Identity Provider (IdP)** | Xác thực, MFA, phát hành SAML/OIDC token, quản lý phiên | Ứng dụng có nhận ra cùng một chủ thể sau cutover? |
| **IAM/IGA** | Điều phối JML, tính quyền, phê duyệt, cấp/thu hồi và rà soát quyền | Quy tắc cấp và thu hồi quyền có còn chạy đúng không? |
| **Ứng dụng và tài nguyên** | Thực thi quyền cục bộ qua role, group, ACL, token hoặc tài khoản riêng | Quyền thực tế còn đúng khi group/ID thay đổi không? |

Di trú directory có thể là đổi LDAP server, nâng cấp/chuyển forest AD, hợp nhất domain, chuyển tenant cloud directory hoặc chuyển mô hình hybrid sang cloud. Mỗi trường hợp có mức độ thay đổi khác nhau. Chuyển máy chủ trong cùng một directory có thể bảo toàn nhiều định danh đối tượng; **tạo directory hoặc tenant mới thường tạo ra định danh đối tượng mới**, dù UPN hay email được giữ.

~~~mermaid
flowchart LR
    HR["HRIS / nguồn nhà thầu"] --> IAM["IAM/IGA: JML và chính sách quyền"]
    IAM --> O["Directory cũ"]
    IAM --> N["Directory mới"]
    O -. "Đối chiếu ánh xạ và trạng thái" .-> N
    N --> IDP["IdP / MFA / SSO"]
    IDP --> APP["Ứng dụng SAML/OIDC"]
    N --> LDAP["Ứng dụng LDAP / Kerberos"]
    IAM --> SCIM["Provisioning SCIM / API"]
    SCIM --> APP
    N --> AUDIT["Nhật ký và đối soát"]
    APP --> AUDIT
    LDAP --> AUDIT
~~~

Đường đăng nhập qua IdP, đường truy cập LDAP/Kerberos và đường cấp quyền SCIM/API phải được đánh giá **riêng**. Đăng nhập SSO thành công chưa chứng minh một tài khoản cục bộ đã được liên kết đúng hoặc quyền cũ đã được thu hồi.

## 3. Phạm vi và những bất biến cần giữ

Một dự án có thể chỉ thay directory backend, hoặc bao gồm đổi domain/forest, tenant, issuer SSO và thiết bị. Hãy khoanh rõ tài nguyên nào nằm trong phạm vi: người dùng nội bộ, nhà thầu, nhóm, máy trạm, máy chủ, ứng dụng, tài khoản đặc quyền, service account, khóa/secret, máy chủ LDAP và hạ tầng mạng.

Trước triển khai, thống nhất các **bất biến**:

| Bất biến | Kiểm chứng |
|---|---|
| Một chủ thể thực chỉ có một danh tính chuẩn được xác minh | Mỗi cặp account cũ/mới trỏ đến một canonical person ID có bằng chứng |
| Không ghép người chỉ vì trùng email, họ tên hoặc UPN | Những ca mơ hồ được cách ly để phê duyệt thủ công |
| Account mới chỉ nhận quyền có cơ sở nghiệp vụ hợp lệ | So sánh desired entitlements với quyền thực tế tại ứng dụng |
| Leaver không lấy lại quyền do đồng bộ trễ hoặc rollback | Thử disable, revoke session/token và kiểm tra các account độc lập |
| Mover nhận quyền mới và mất quyền vai trò cũ | Kiểm thử cả cấp, thu hồi, ngoại lệ và quyền trực tiếp |
| Thay đổi có lịch sử và có thể truy nguyên | Lưu mapping version, nguồn sự kiện, actor, approver, thời điểm, kết quả |
| Không có hai bộ điều khiển vô tình tranh quyền ghi | Có ma trận ownership cho từng thuộc tính và giai đoạn |
| Sự cố batch hoặc connector không gây vô hiệu hóa hàng loạt | Có guardrail, pause, dry-run và xác minh trước bulk action |

Nếu mất một trong các bất biến, việc “chuyển đủ số lượng account” không đủ để nghiệm thu.

## 4. Khảo sát hiện trạng trước khi thiết kế

### 4.1. Lập inventory có chủ sở hữu

Mỗi directory, identity source, IdP và ứng dụng cần có owner kỹ thuật, owner nghiệp vụ, trạng thái sử dụng, loại account, cách xác thực, cách cấp quyền, SLA phục hồi, yêu cầu lưu vết và phương án xử lý khi không còn directory cũ.

Các nhóm phụ thuộc thường gặp:

- **Danh tính người dùng:** employee, contractor, guest, external identity, user đã nghỉ nhưng cần lưu trữ lịch sử.
- **Nhóm:** security group, distribution group, nhóm lồng nhau, nhóm động, role đồng bộ xuống ứng dụng và nhóm quản trị.
- **Ứng dụng:** LDAP simple bind, LDAP search, LDAPS, Kerberos/NTLM, SAML, OIDC, SCIM, API độc quyền, account cục bộ.
- **Hạ tầng:** DNS/domain discovery, domain controller, replication, trust, certificate, proxy/firewall, thời gian hệ thống và độ sẵn sàng liên vùng.
- **Thiết bị/tài nguyên:** máy join domain, GPO, profile, home folder, file share, ACL, printer, Wi-Fi/VPN, máy chủ, job scheduler.
- **Danh tính phi con người:** service account, ứng dụng có credential riêng, bot, workload identity, tài khoản break-glass và tài khoản PAM.

Ví dụ inventory ứng dụng:

| Ứng dụng | Nhận dạng user bằng | Cấp quyền dựa trên | Đầu mối xử lý |
|---|---|---|---|
| Cổng nội bộ | SAML NameID / OIDC subject | Role tại ứng dụng | Nhóm SSO + chủ ứng dụng |
| Dịch vụ báo cáo cũ | LDAP DN / bind | Group DN hoặc group name | Nhóm directory + ứng dụng |
| File share | SID / ACL | Nhóm bảo mật | Nhóm hệ điều hành + chủ dữ liệu |
| CRM | Account ID cục bộ, liên kết IdP | SCIM group và direct role | Nhóm IAM + chủ CRM |
| Job tích hợp | Service principal / credential | Quyền API hoặc hệ thống | Owner service account |

**Bài tập inventory thực tế:** tìm mọi thành phần đang tham chiếu hard-coded tới domain name, base DN, group DN, SID, UPN suffix, LDAP URL hoặc certificate của directory cũ. Những tham chiếu này có thể khiến cutover lỗi dù bản ghi user đã đủ.

### 4.2. Chụp baseline và đo hiện trạng

Lưu snapshot có kiểm soát của các đối tượng và thuộc tính phục vụ mapping; số lượng user/group đang hoạt động; trạng thái JML; membership (kể cả nhóm lồng); quyền đặc quyền; số lần đăng nhập lỗi; số tài khoản orphan; độ trễ provision/deprovision. Không đưa password, secret, raw token hoặc dữ liệu nhân sự nhạy cảm không cần thiết vào báo cáo.

Phân biệt:

- **Trạng thái nguồn mong muốn:** người còn hợp đồng, thuộc đơn vị nào, cần quyền gì.
- **Trạng thái directory:** account, thuộc tính, nhóm, trạng thái khóa.
- **Trạng thái hệ đích:** account, role, ACL, session/token, khóa ứng dụng.

Ba trạng thái có thể khác nhau ngay trước khi di trú; phải ghi nhận drift có sẵn để không quy mọi chênh lệch cho dự án mới.

## 5. Ánh xạ danh tính: giữ đúng người khi object ID đổi

### 5.1. Những khóa trông giống nhau nhưng không thay thế nhau

| Định danh | Phạm vi và ý nghĩa | Lưu ý |
|---|---|---|
| **Canonical person ID** | Khóa ổn định của chủ thể trong identity registry/IAM | Nên độc lập directory và không tái sử dụng |
| **Object GUID / object ID** | Khóa đối tượng trong directory hoặc tenant cụ thể | Có thể đổi khi tạo object ở nơi mới |
| **SID** (AD) | Định danh bảo mật dùng trong kiểm soát truy cập Windows | ACL phụ thuộc SID; SID mới không mặc nhiên có quyền cũ |
| **DN** (LDAP) | Đường dẫn của đối tượng trong cây directory | Thay khi đổi OU/cấu trúc, thường không phù hợp làm khóa bền vững |
| **UPN / username** | Tên đăng nhập | Có thể đổi suffix, trùng sau sáp nhập hoặc bị tái sử dụng |
| **Email** | Thuộc tính liên hệ | Không đủ bằng chứng để tự động hợp nhất identity |
| **OIDC `issuer + sub`** | Cặp xác định chủ thể theo issuer trong federation | Đổi IdP/issuer có thể khiến ứng dụng coi là user khác |
| **SCIM `id` / `externalId`** | ID tại service provider / ID liên kết do client quản lý | Phạm vi khác nhau; phải theo hợp đồng tích hợp |

Đặc biệt với AD, `objectGUID` và `objectSid` không đồng nghĩa. Một ứng dụng tìm user theo email có thể hoạt động, trong khi file share vẫn từ chối vì ACL chỉ ghi SID cũ. SIDHistory đôi khi hỗ trợ tương thích trong một số kịch bản AD và điều kiện trust thích hợp; đây là lựa chọn có điều kiện về bảo mật và tương thích, **không phải giải pháp mặc định**, cũng không áp dụng cho mọi cloud directory.

### 5.2. Bảng mapping có bằng chứng

Giả sử một nhân viên có identity chuẩn `person-01234`, account cũ `OLDDOMAIN\\lan.n` và account mới `NEWDOMAIN\\lan.nguyen`. Giữ ánh xạ rõ ràng:

~~~yaml
canonicalPersonId: person-01234
personType: employee
status: active
links:
  - directory: old-ad
    objectId: "old-object-guid-1234"   # minh họa, không phải GUID thật
    securityId: "old-sid-1234"          # minh họa, không phải SID thật
    username: "lan.n"
  - directory: new-ad
    objectId: "new-object-guid-5678"   # minh họa
    securityId: "new-sid-5678"          # minh họa
    username: "lan.nguyen"
mapping:
  evidence: "HR-confirmed-person-link"
  approvedBy: "identity-steward"
  version: 4
~~~

Mẫu trên chỉ mô tả **ý tưởng bảng liên kết**; không phải schema sản phẩm, cũng không chứa ID thật. Có thể lưu tên hệ thống, loại danh tính, thời gian hiệu lực, nguồn bằng chứng và phiên bản mapping. Không sử dụng thông tin minh họa như mã hợp lệ để gọi API.

Quy trình matching an toàn:

1. Ưu tiên liên kết qua canonical person ID và bảng chuyển đổi old ID → new ID có xác minh từ nguồn có thẩm quyền.
2. Nếu thiếu mapping, đối chiếu nhiều bằng chứng đáng tin cậy, như hồ sơ nhân sự và chủ sở hữu định danh; không tự nối chỉ bằng email.
3. Nếu một account khớp nhiều người, hoặc nhiều account có thể thuộc một người, đưa vào **quarantine** để xác minh.
4. Áp ràng buộc duy nhất: một cặp `(directory, objectId)` chỉ liên kết với một canonical identity tại cùng thời điểm.
5. Lưu người phê duyệt, lý do, dấu vết trước/sau và cách xử lý trường hợp tái tuyển dụng, contractor chuyển employee, đổi họ tên.

**Phân biệt link với merge:** link nối object đã xác minh với cùng một người; merge hợp nhất hai hồ sơ từng được coi là hai chủ thể. Merge cần quy trình chặt hơn vì có thể gộp nhầm lịch sử truy cập và quyền.

## 6. Những phụ thuộc kỹ thuật đặc thù của directory

### 6.1. LDAP schema, DN và bộ lọc

Directory mới có thể khác cách lưu `uid`, `sAMAccountName`, `userPrincipalName`, `memberOf`, `manager`, trạng thái account và quy tắc kiểm tra group membership. `memberOf` không luôn phản ánh đầy đủ nhóm lồng nhau hoặc logic của mọi loại directory. Ứng dụng có thể tìm user dưới một `baseDN` cố định hoặc filter theo một object class cũ.

Checklist kỹ thuật cho từng LDAP client:

- Địa chỉ server/port, DNS, cơ chế khám phá endpoint và khả năng failover.
- Base DN, bind DN, scope tìm kiếm, filter, attribute mapping, phân trang và giới hạn truy vấn.
- LDAPS/StartTLS, chuỗi certificate, xác thực hostname, chính sách TLS và quyền của bind account.
- Quy tắc phân giải nhóm lồng, nhóm động, phân biệt chữ hoa/chữ thường theo ứng dụng.
- Chính sách cache membership, TTL và hành vi khi directory không khả dụng.

Không nên tắt kiểm tra TLS hoặc sử dụng bind account có quyền quản trị diện rộng chỉ để “cho ứng dụng chạy lại”.

### 6.2. AD: domain, forest, SID, ACL và thiết bị

Trong môi trường Active Directory, di trú còn có thể ảnh hưởng tới:

- **Trust và xác thực:** quan hệ tin cậy giữa domain/forest, đường đi Kerberos, DNS và đồng bộ thời gian.
- **SID/ACL:** NTFS, SMB share, quyền đối tượng, local group trên server, quyền của tác vụ chạy bằng account cũ.
- **Group Policy (GPO):** mapping đến OU, security filtering, script đăng nhập, cấu hình bảo mật trên thiết bị.
- **Service Principal Name (SPN):** chủ sở hữu SPN và Kerberos ticket của dịch vụ; SPN trùng hoặc mất có thể làm xác thực thất bại.
- **Domain-joined device:** account máy, trust với domain, profile người dùng và khả năng đăng nhập khi ở ngoài mạng.
- **Service identity:** Windows service, scheduled task, application pool, delegation và cấu hình credential.

Nếu chuyển forest/domain, phải kiểm thử tác động đến ACL bằng danh sách tài nguyên thực tế. Không được suy luận rằng copy group name là đã bảo toàn quyền. Việc chuyển hoặc duy trì SIDHistory, khi được hỗ trợ, cần đánh giá bảo mật, quy tắc trust, lọc SID và kế hoạch loại bỏ quyền thừa.

### 6.3. Cloud directory, hybrid và tenant

Ở môi trường cloud/hybrid, directory cũ và mới có thể cùng tồn tại nhưng có **object ID khác nhau**, cùng với thay đổi về nguồn đồng bộ, domain đã xác minh, thiết bị, chính sách truy cập, phương thức đăng nhập và liên kết ứng dụng. Một số tài nguyên SaaS còn gắn user bằng ID cục bộ riêng.

Đừng giả định rằng chuyển cùng UPN sẽ tự giữ nguyên MFA registration, session, device registration, role quản trị hoặc profile ứng dụng. Phải kiểm thử từng khả năng theo thiết kế nhà cung cấp và thực trạng tenant. Nếu có cả directory tại chỗ và cloud, ghi rõ nơi nào là writer của từng thuộc tính, nơi nào chỉ đồng bộ/nhận bản sao.

### 6.4. Mật khẩu, phiên và chứng thực

Không phải mọi phương thức di trú đều di chuyển được password hash hoặc credential; khả năng phụ thuộc hệ nguồn, hệ đích và quy trình được hỗ trợ. Lập phương án hợp lệ cho reset/đăng ký lại khi cần, MFA, tài khoản khẩn cấp và trải nghiệm đăng nhập ngày đầu. Nếu thay issuer/subject SSO, phải thực hiện account linking có kiểm chứng trước cutover để tránh tạo account ứng dụng mới.

Kiểm thử session, refresh token, ứng dụng offline, VPN và tài nguyên không dùng SSO. **Khóa user tại directory** có thể chưa chấm dứt phiên, token hoặc quyền trực tiếp ở mọi ứng dụng.

## 7. Chọn chiến lược di trú

| Chiến lược | Cách làm | Phù hợp | Điểm cần kiểm soát |
|---|---|---|---|
| **Parallel / coexistence** | Directory cũ và mới cùng tồn tại trong cửa sổ chuyển đổi | Phụ thuộc nhiều, cần quan sát so sánh | Nguồn có thẩm quyền, đồng bộ có hướng, tránh vòng lặp ghi |
| **Phased / theo cohort** | Chuyển từng nhóm phòng ban, ứng dụng hoặc địa điểm | Quy mô vừa/lớn | Ranh giới group, trust, tài nguyên chia sẻ giữa cohort |
| **Application-first** | Cập nhật app hỗ trợ directory mới trước khi chuyển user | Nhiều LDAP client cũ | Mapping user và cơ chế fallback của từng app |
| **Big-bang** | Cắt toàn bộ tại một thời điểm | Hệ nhỏ, ít phụ thuộc, rollback đã tập dượt | Phạm vi ảnh hưởng lớn nếu matching hoặc SSO lỗi |
| **Rebuild with link** | Tạo object mới, bảo toàn mapping và chuyển quyền có kiểm soát | Tenant/forest hoàn toàn mới | Định danh thay đổi, ACL/SSO/account linking |

Đối với hệ lớn, thường dùng **inventory → mapping → shadow read/dry-run → pilot → chuyển từng cohort → đối soát → ngừng hệ cũ**. Shadow mode dùng để so sánh trạng thái và quyết định trước khi phát sinh thay đổi trên production; không tự tạo hai luồng cấp/thu hồi quyền song song.

## 8. Thiết kế ownership và đồng tồn tại an toàn

Trong mỗi giai đoạn, phải chỉ định một nguồn có thẩm quyền cho từng thuộc tính và một writer có trách nhiệm cho từng đối tượng đích.

| Dữ liệu/tác vụ | Trước cutover | Trong coexistence | Sau cutover |
|---|---|---|---|
| Trạng thái hợp đồng, JML | HRIS/nguồn nhà thầu | Vẫn từ nguồn chính thức | Không đổi nếu dự án chỉ thay directory |
| Canonical person ID | Identity registry | Giữ ổn định; xác minh ánh xạ | Giữ ổn định |
| Account/attribute directory | Writer cũ | Writer theo cohort/thuộc tính, có khóa điều phối | Writer mới |
| Nhóm/entitlement | IAM/IGA hoặc owner được chỉ định | So sánh, chuyển theo mapping, chặn ghi tranh chấp | IAM/IGA hoặc owner được chỉ định |
| Xác thực SSO/MFA | IdP hiện tại | Routing/trust theo thiết kế đã thử | IdP theo kiến trúc đích |
| Audit và reconciliation | Thu thập từ hệ cũ | Thu cả hai phía, gắn correlation ID | Thu từ đích và lưu lịch sử hệ cũ |

Một mô hình lỗi phổ biến là provisioner A cập nhật directory mới, còn đồng bộ ngược B lại ghi thuộc tính cũ và tạo vòng lặp. Cần xác định chiều đồng bộ, thuộc tính được phép ghi, thứ tự sự kiện, idempotency key và quyền tạm dừng mỗi luồng.

Với event JML, áp dụng **thứ tự logic theo version/effective time**, deduplicate các event ID trùng và kiểm tra trạng thái hiện hành trước khi replay. Sự kiện mover cũ không được ghi đè sự kiện leaver mới. Khoảng trễ replication phải được phản ánh vào SLA và kiểm thử.

### Ví dụ xử lý sự kiện an toàn (mã giả)

~~~text
process(event):
    validateSourceAndSignature(event)
    if alreadyProcessed(event.id): return "NO_OP"
    person = resolveVerifiedCanonicalPerson(event)
    if person is ambiguous: quarantine(event); return "REVIEW"
    if event.version < currentAcceptedVersion(person): return "STALE"
    desired = evaluatePolicies(person, event, approvedExceptions)
    if isUnexpectedBulkChange(desired): pauseForApproval(event); return "HOLD"
    applyIdempotentlyToAuthorizedTargets(desired)
    reconcileActualAgainstDesired(person)
    audit(event.id, person.id, desired, results)
~~~

Đây là pseudocode minh họa luồng kiểm soát; hệ thống thật cần xử lý transaction/queue, đồng thời và partial failure theo kiến trúc riêng.

## 9. Quy trình triển khai từ đầu đến nghiệm thu

### Giai đoạn 1 — Discover & design

1. Khoanh phạm vi, lập inventory account/group/app/device/ACL/service account và owner.
2. Chụp baseline; thu thập mapping identity, group, role, application binding.
3. Chuẩn hóa schema, naming, UPN suffix, OU/group structure và phân quyền quản trị.
4. Đánh giá khả năng tương thích xác thực, API, LDAPS, trust, certificate và phục hồi.
5. Xác định single writer, tiêu chí no-go, mức rủi ro chấp nhận và owner phê duyệt.

### Giai đoạn 2 — Build & map

1. Chuẩn bị directory mới, cấu hình HA, log, audit, monitoring, quyền connector tối thiểu.
2. Tạo/link account bằng mapping đã được chứng thực; cách ly bản ghi mơ hồ.
3. Di chuyển nhóm có kiểm soát, xác minh nested membership và nhóm đặc quyền.
4. Chuyển cấu hình ứng dụng, LDAP binding, SSO/SCIM, service identity và đường tin cậy theo kế hoạch.
5. Thử thuộc tính JML và quyền kỳ vọng ở chế độ dry-run trước khi cho writer tác động.

### Giai đoạn 3 — Pilot

Chọn cohort đủ đại diện: nhân viên thường, người có nhiều group, mover, leaver, nhà thầu, admin được giám sát, người dùng remote, ứng dụng LDAP cũ, file share và ít nhất một tài khoản dịch vụ quan trọng. Đo đăng nhập, độ trễ cấp/thu hồi và chênh lệch quyền; xử lý lỗi ở pilot trước khi mở rộng.

### Giai đoạn 4 — Cutover

1. Xác nhận go/no-go dựa trên mapping coverage, lỗi chưa xử lý, backup/restore, phương án liên lạc và trực vận hành.
2. Tạm dừng hoặc chuyển hướng writer theo ranh giới đã duyệt; ghi nhận mốc phiên bản/snapshot và event backlog.
3. Chuyển traffic đăng nhập/bind và provisioning theo cohort; kiểm tra DNS, TLS, SSO, LDAP, group, ứng dụng, service account.
4. Replay delta JML từ mốc chuẩn, có deduplication, ordering và đối soát; không đánh mất leaver mới phát sinh.
5. Xác nhận quyền hiện hành ở hệ đích, đặc biệt ACL, direct grant, PAM và các phiên tồn dư.

### Giai đoạn 5 — Stabilize & retire

Theo dõi drift, lỗi đăng nhập, provisioning, authentication latency và incident theo cohort. Chỉ ngừng directory/connector/trust cũ khi đã xác nhận không còn phụ thuộc hợp lệ, có kế hoạch retention cho audit/mapping và đã thu hồi quyền quản trị/secret không còn cần. Không xóa ngay dữ liệu nguồn chỉ vì cutover đã đạt.

## 10. Bảo toàn Joiner–Mover–Leaver

Di trú directory là một phần của vòng đời danh tính, nên **mọi thao tác cấp quyền phải phản ánh trạng thái nhân sự hiện tại**.

| Sự kiện | Hành vi cần giữ | Kiểm tra sau chuyển đổi |
|---|---|---|
| **Joiner** | Xác minh danh tính; tạo/link đúng một account; kích hoạt và cấp role ở thời điểm hợp lệ | Không nhân đôi user, không cấp sớm, MFA đúng |
| **Mover** | Cập nhật thuộc tính, nhóm và RBAC/ABAC; thu hồi role cũ, xử lý SoD | Không giữ group/direct grant/PAM cũ trái chính sách |
| **Leaver** | Disable đường đăng nhập; thu hồi token, account app, quyền trực tiếp, khóa liên quan | Không đăng nhập lại bằng directory cũ hoặc mới, không còn quyền ngoài SLA |
| **Rejoiner** | Xác minh lại, quyết định link/tạo mới theo chính sách | Không tự phục hồi group/privilege trước đây |
| **Contractor hết hạn** | Dựa vào nguồn nhà thầu có thẩm quyền và thời hạn hợp đồng | Không bị bỏ sót vì không có hồ sơ HRIS |

**Rủi ro đặc biệt:** quá trình import nhóm từ directory cũ có thể vô tình cấp lại quyền mà chính sách hiện tại đã thu hồi. Quyền phải được tính từ desired state đang có, rồi so sánh với group/ACL cũ để chuyển những gì vẫn được phép. Nếu có exception tạm thời, cần ghi owner, lý do, thời hạn hết hiệu lực và người phê duyệt.

Với **service account** không nằm trong HRIS, áp dụng registry có owner, mục đích, quyền tối thiểu, nơi dùng credential, lịch rotate và phương án bàn giao khi owner cá nhân rời tổ chức. Không tự xóa account dịch vụ theo sự kiện leaver mà chưa kiểm tra phụ thuộc; đồng thời không để nó trở thành orphan account.

## 11. Cấp quyền, SSO, SCIM và đường truy cập ngoài SSO

### 11.1. RBAC/ABAC và group

RBAC cấp quyền theo role; ABAC dùng thuộc tính được quản trị như đơn vị, loại hợp đồng, location hoặc độ nhạy tài nguyên. Khi chuyển directory:

- Chuẩn hóa thuộc tính trước khi policy chạy; chẳng hạn mã đơn vị `FN` ở directory cũ và `FINANCE` ở nơi mới phải có quy tắc tương đương được phê duyệt.
- Ánh xạ group cũ → group mới dựa trên **ý nghĩa quyền**, không dựa tên chuỗi đơn thuần.
- Kiểm tra nested group, group owner, dynamic membership, delegated admin, quyền trực tiếp và chính sách SoD.
- Kiểm thử actual access: có thành viên group không đồng nghĩa file share/ứng dụng đã cấp đúng quyền nếu ACL hoặc app mapping còn tham chiếu ID cũ.

### 11.2. SSO và federation

Ứng dụng OIDC nên nhận diện principal bằng giá trị `iss + sub` ổn định trong phạm vi issuer; với SAML, kiểm tra NameID, issuer, certificate, attribute và cách app link user. Di trú directory backend có thể giữ nguyên issuer nếu IdP giữ cấu hình, nhưng **không được mặc định** subject sẽ bất biến. Nếu thay tenant/issuer, pre-link account có kiểm chứng và thử cả login, logout, MFA, session revocation.

### 11.3. SCIM và provisioning

SCIM hoặc API thường tạo/cập nhật/deactivate user và group tại ứng dụng. Xác minh rõ `id` do service provider phát hành, `externalId` do client quản lý, khóa đối sánh riêng của vendor và chính sách soft-delete. API retry phải idempotent; chạy lại một event không được tạo thêm account hoặc cấp thêm quyền.

Phải kiểm tra trường hợp ứng dụng có **direct entitlement** không được quản lý qua SCIM. Gỡ group trong directory/SCIM có thể không xóa direct role hay API token tại ứng dụng; reconciliation cần đọc trạng thái thật từ ứng dụng.

## 12. Đối soát, giám sát và guardrail

### 12.1. Đối soát hai chiều logic

So sánh **desired state** (theo source có thẩm quyền + chính sách + exception) với **actual state** (directory mới + IdP + ứng dụng + ACL/PAM). Không coi directory cũ là nguồn chân lý về quyền sau cutover.

| Sai lệch | Nguyên nhân khả dĩ | Hành động |
|---|---|---|
| User mới không liên kết được với canonical ID | ID mới, thiếu mapping, dữ liệu mơ hồ | Quarantine, xác minh bằng chứng, không tự merge |
| User không đăng nhập được dù có account | TLS/bind, federation subject, MFA, policy, device | Phân nhóm lỗi, kiểm thử từng đường xác thực |
| Thiếu quyền file share | ACL còn SID cũ, group mapping sai | Kiểm chứng ACL thực tế, sửa theo chủ tài nguyên |
| Quyền cũ vẫn tồn tại | Direct grant, nested group, connector không revoke | Thu hồi theo policy, xác minh tại đích |
| Nhiều account được tạo cho một người | Matching/SCIM retry sai, hai writer | Pause, fix linking và quy tắc idempotency |
| Role dao động qua lại | Đồng bộ hai chiều không có ownership | Ngừng writer tranh chấp, chỉnh authority/version |
| Nhiều user bị disable cùng lúc | Source thiếu dữ liệu, filter lỗi, batch rỗng | Giữ bulk action, xác minh nguồn và owner |

### 12.2. Các số đo nên theo dõi

- **Mapping coverage:** identity trong phạm vi có mapping đã xác minh / tổng identity trong phạm vi.
- **Duplicate và orphan rate:** tỷ lệ account trùng hoặc không có chủ thể/owner hợp lệ.
- **Provisioning success/latency:** tỷ lệ thành công và độ trễ tạo/sửa/vô hiệu hóa ở các hệ đích.
- **Leaver revocation latency:** thời gian từ mốc hiệu lực đến khi mọi đường truy cập trong phạm vi bị thu hồi.
- **SSO/LDAP/Kerberos authentication failure rate:** lỗi theo từng ứng dụng, địa điểm, cohort và loại xác thực.
- **Entitlement drift:** chênh lệch quyền kỳ vọng với quyền thực tế (gồm nhóm, direct grant, ACL).
- **Service dependency errors:** lỗi job, service login, certificate, LDAP bind sau chuyển đổi.
- **Replication/reconciliation lag:** độ trễ để thay đổi được nhìn thấy và đối soát.

Ngưỡng báo động phải dựa trên baseline thực tế và mức chấp nhận được, không sử dụng con số minh họa như SLA mặc định. Ví dụ, một batch thiếu 30% record người đang hoạt động nên bị chặn để xác minh thay vì tự xem toàn bộ là leaver.

### 12.3. Audit và bảo vệ dữ liệu

Ghi event ID/correlation ID, canonical person ID, object mapping trước/sau, policy version, source, actor/approver, timestamp, target, kết quả, retry và exception. Bảo vệ bảng mapping như dữ liệu nhạy cảm: phân quyền tối thiểu, mã hóa, retention, kiểm soát truy cập và tránh ghi credential/raw token vào log.

## 13. Kiểm thử và tiêu chí nghiệm thu

| Mã | Tình huống | Điều kiện đạt |
|---|---|---|
| T01 | User đổi UPN/email trong lúc di trú | Còn đúng canonical identity; không tạo account thứ hai |
| T02 | Hai người trùng tên hoặc email tái sử dụng | Không tự động link/merge; có hàng đợi xác minh |
| T03 | Joiner có ngày bắt đầu tương lai | Tạo/enable đúng thời điểm, cấp quyền đúng role |
| T04 | Mover sang phòng ban khác | Thu hồi role cũ và cấp role mới; kiểm tra SoD |
| T05 | Leaver phát sinh trong lúc cutover | Chặn mọi đường đăng nhập trong phạm vi và revoke đúng SLA |
| T06 | Một batch source/LDAP export bị thiếu | Không mass disable; có cảnh báo và hold |
| T07 | Event lặp hoặc đến sai thứ tự | Không tạo trùng account, không phục hồi quyền đã thu hồi |
| T08 | LDAP app dùng base DN/group DN cũ | Truy vấn thành công với cấu hình mới và quyền đúng |
| T09 | File share dùng SID/ACL cũ | Người hợp lệ truy cập được; người không hợp lệ bị chặn |
| T10 | Kerberos service, SPN hoặc scheduled task | Job/service hoạt động với identity và quyền đích |
| T11 | App SSO/SCIM có account cũ | Được pre-link, không trùng user, đúng role và MFA |
| T12 | Service account có owner là leaver | Có owner thay thế, credential được quản lý, không gián đoạn ngoài kế hoạch |
| T13 | Directory mới/connector không khả dụng | Phản ứng an toàn, không cấp/thu hồi hàng loạt sai |
| T14 | Rollback sau khi có mover/leaver mới | Không phát lại sự kiện cũ để cấp sai quyền |

Nghiệm thu cần bằng chứng trực tiếp: kết quả truy cập ứng dụng, kết quả LDAP/SSO, bản đối soát role/ACL, log thực thi JML, số liệu pilot, biên bản phê duyệt ngoại lệ và kết quả thử rollback. Không chỉ dùng số lượng account được copy.

## 14. Cutover, go/no-go và rollback

### 14.1. Checklist trước go-live

- [ ] Có inventory đầy đủ cùng owner cho directory, group, ứng dụng, service account, ACL và thiết bị trong phạm vi.
- [ ] Bảng mapping có bằng chứng; ca mơ hồ được xử lý hoặc cách ly.
- [ ] Có ma trận authority/single writer và giới hạn bulk changes.
- [ ] Đã kiểm thử JML, SSO/MFA, LDAP/Kerberos, SCIM, group, ACL, VPN và app quan trọng.
- [ ] Có baseline, chỉ số theo dõi, cảnh báo, on-call và quy trình incident.
- [ ] Đã diễn tập dừng đồng bộ, rollback và replay delta JML.
- [ ] Có phương án account quản trị khẩn cấp bảo mật, độc lập khi federation gặp sự cố.
- [ ] Owner bảo mật và owner nghiệp vụ duyệt tiêu chí go/no-go.

### 14.2. Khi nào cần dừng?

Những tình huống có thể kích hoạt pause hoặc rollback theo ngưỡng đã định: mapping nhầm chủ thể, cấp quyền đặc quyền sai, mất đăng nhập diện rộng, leaver vẫn truy cập được, ứng dụng cốt lõi không thể xác thực, drift tăng đột biến hoặc dữ liệu nguồn không đầy đủ. Dừng đúng connector/writer gây lỗi và giữ log bằng chứng để điều tra.

### 14.3. Rollback không phải chỉ “đổi DNS về cũ”

Nếu đã có JML mới trong thời gian cutover, rollback phải áp dụng **trạng thái nhân sự hiện hành**:

1. Tạm dừng writer và cô lập thay đổi lỗi; giữ snapshot, backlog và audit.
2. Xác định các sự kiện joiner/mover/leaver kể từ mốc chuyển đổi.
3. Chọn lại nguồn/writer có thẩm quyền, xử lý xung đột theo version và effective time.
4. Replay có kiểm soát; không tạo account trùng, không phục hồi quyền đã thu hồi hợp lệ.
5. Kiểm thử xác thực, nhóm, ACL, service account và quyền ứng dụng sau khôi phục.
6. Chỉ mở lại đồng bộ khi đã hiểu nguyên nhân và có quyết định của owner.

Không phải mọi thao tác có thể đảo ngược hoàn toàn: xóa object, đổi mật khẩu, rotate secret, chuyển tài nguyên tenant hoặc thay danh tính đăng nhập của ứng dụng có thể cần quy trình phục hồi riêng. Vì vậy nên giữ hệ cũ dưới dạng có kiểm soát trong cửa sổ chuyển đổi, tránh các hành động phá hủy sớm.

## 15. Case study: chuyển AD cũ sang directory mới

Giả sử tổ chức có 800 nhân viên, 60 nhà thầu, 30 ứng dụng, nhiều file share và một hệ thống báo cáo cũ dùng LDAP. Nhóm dự án chọn chuyển ba cohort theo đơn vị kinh doanh.

**Khảo sát:** 14 ứng dụng dùng SSO, 10 ứng dụng đọc LDAP/group, 6 ứng dụng có credential hoặc quyền cục bộ. Một số file share dùng ACL tham chiếu SID cũ; ba scheduled task dùng service account thuộc domain cũ. Đó là những phụ thuộc phải được xử lý ngoài việc tạo user mới.

**Mapping:** identity registry giữ canonical person ID; object ID mới được gắn với cùng người sau khi xác minh bằng nguồn nhân sự và bảng mapping. Các hồ sơ trùng tên nhưng thiếu bằng chứng bị cách ly. Nhóm quyền được chuyển theo access policy hiện tại, không sao chép mù toàn bộ membership cũ.

**Pilot:** nhóm thử với nhân viên mới, người vừa đổi bộ phận, nhà thầu sắp hết hạn, người dùng VPN và người có quyền file share. Pilot phát hiện một app LDAP tìm trong OU cũ và một file share chưa cập nhật ACL. Nhóm sửa cấu hình ứng dụng, xử lý quyền theo owner rồi đối soát lại.

**Cutover:** các cohort được chuyển theo lịch; quyền ghi được chuyển từng phần, theo dõi SSO/LDAP, group, service account và queue provisioning. Một leaver phát sinh trong cửa sổ cutover được xử lý từ sự kiện nhân sự mới nhất và bị disable trên cả những đường truy cập vẫn còn hoạt động. Bằng chứng thu hồi được lưu vào audit.

**Nghiệm thu:** tổ chức chỉ kết thúc cohort sau khi cả đăng nhập lẫn quyền thực tế đã đạt chính sách, không có mapping mơ hồ đang tự động cấp quyền, các lỗi có owner và SLA xử lý; sau giai đoạn ổn định mới gỡ trust/connector/credential cũ.

**Điểm cần nhớ:** Di trú thành công phải giữ **identity continuity**, **access correctness** và **lifecycle correctness**. Đếm đủ 860 hồ sơ trong directory mới không chứng minh ba điều đó.

## 16. Sai lầm thường gặp và cách tránh

1. **Dùng email hoặc UPN làm khóa ghép duy nhất.** Dùng canonical ID, mapping có bằng chứng và cơ chế quarantine.
2. **Chỉ chuyển user, bỏ qua group/ACL.** Inventory và kiểm thử actual access tại file share, ứng dụng và PAM.
3. **Giữ hai writer không có authority rõ ràng.** Chỉ định writer theo attribute/cohort, kiểm tra thứ tự event và vòng lặp đồng bộ.
4. **Đánh đồng SSO hoạt động với toàn bộ quyền đúng.** Đối soát cả LDAP/Kerberos, SCIM, direct grant, session/token.
5. **Xem source vắng record là leaver.** Chặn bulk change khi input thiếu hoặc bất thường; xác minh với nguồn có thẩm quyền.
6. **Quên service account, SPN, GPO hoặc thiết bị.** Đưa chúng vào inventory/pilot và có owner xử lý riêng.
7. **Chỉ thử đường đi thành công.** Thử replay, partial failure, invalid mapping, network outage, mass disable và rollback.
8. **Xóa directory cũ quá sớm.** Chỉ retire khi phụ thuộc đã đóng, đã lưu audit/mapping cần thiết và có phương án khôi phục.

## 17. Câu hỏi tự kiểm tra

1. Tại sao hai account có cùng email trước và sau di trú chưa đủ chứng minh thuộc cùng một người?
2. Vì sao một tài khoản AD mới đã vào đúng security group nhưng vẫn không mở được file share cũ?
3. Một ứng dụng LDAP dùng group DN cố định cần được kiểm thử những gì trước khi đổi directory?
4. Khi mover thay vai trò đúng lúc cutover, làm thế nào để tránh phục hồi quyền cũ?
5. Sự khác biệt giữa object ID, SID, LDAP DN, OIDC `iss + sub` và SCIM `externalId` ảnh hưởng tới việc liên kết tài khoản ra sao?
6. Tại sao không nên tự disable toàn bộ user thiếu trong một batch đồng bộ?
7. Một service account thuộc domain cũ cần được quản lý thế nào để tránh gián đoạn dịch vụ?
8. Rollback sang directory cũ sau khi một nhân viên nghỉ việc có cần cập nhật sự kiện leaver không? Vì sao?

**Gợi ý:** Liên hệ các bất biến về chủ thể, mapping ID theo phạm vi, quyền thực tế, source authority, idempotency và thứ tự sự kiện. Trả lời theo cả đường xác thực **và** đường cấp/thu hồi quyền.

## 18. Thuật ngữ và tài liệu tham khảo

| Thuật ngữ | Nghĩa |
|---|---|
| **Directory / LDAP** | Dịch vụ danh bạ đối tượng / giao thức truy cập danh bạ |
| **DN / OU** | Distinguished Name / Organizational Unit |
| **AD forest / domain** | Phạm vi tổ chức và quản trị của Active Directory |
| **SID / ACL** | Định danh bảo mật / danh sách kiểm soát truy cập |
| **Kerberos / SPN** | Cơ chế vé xác thực / tên định danh dịch vụ |
| **IdP / SSO / MFA** | Nhà cung cấp định danh / đăng nhập một lần / xác thực đa yếu tố |
| **SCIM** | Giao thức chuẩn hóa quản lý user/group giữa các hệ thống |
| **JML** | Joiner–Mover–Leaver: vào, đổi vai trò và rời tổ chức |
| **RBAC / ABAC / SoD** | Kiểm soát theo vai trò / thuộc tính / phân tách nhiệm vụ |
| **Coexistence / cutover / rollback** | Cùng tồn tại / chuyển chính thức / khôi phục có kiểm soát |
| **Reconciliation** | Đối soát trạng thái kỳ vọng với trạng thái thật |
| **Idempotency** | Chạy lại cùng một thao tác không gây tác động lặp ngoài ý muốn |

Nguồn nền tảng để tra cứu khi thiết kế triển khai:

- **RFC 4510–4519:** họ tài liệu LDAP và các khái niệm directory liên quan.
- **RFC 7643 và RFC 7644:** SCIM core schema và protocol.
- **OpenID Connect Core 1.0:** issuer/subject và hành vi xác thực liên hợp.
- **Tài liệu chính thức của hệ directory/IdP/ứng dụng đang dùng:** object identity, trust, LDAPS, Kerberos, MFA, federation, SCIM, account linking, SID/ACL, backup và rollback; hành vi cụ thể phụ thuộc sản phẩm và phiên bản.

**Tiêu chuẩn đánh giá cuối cùng:** Sau khi thay directory, cùng một người phải tiếp tục được nhận dạng đúng, đăng nhập an toàn, chỉ có quyền còn hợp lệ và bị thu hồi đầy đủ khi thay đổi vai trò hoặc rời tổ chức — với đủ bằng chứng để kiểm toán và phục hồi khi cần.
