# Dual run trong di trú hệ thống IAM

> **Chương:** IAM migration  
> **Chủ đề:** Dual run  
> **Phạm vi:** Quản lý vòng đời danh tính trong Identity and Access Management (IAM) theo Joiner–Mover–Leaver (JML), từ xác minh danh tính, tạo account và cấp quyền tới rà soát và thu hồi khi thay đổi vai trò. Nội dung liên kết identity source, directory, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, quyền tồn dư và kiểm toán.

## 1. Mục tiêu bài học

Sau khi hoàn thành bài, bạn có thể:

1. Phân biệt **dual run**, **shadow run**, **parallel run**, **coexistence**, **pilot**, **cutover** và **rollback** trong di trú IAM.
2. Thiết kế giai đoạn hệ cũ và hệ mới cùng tồn tại mà mỗi loại dữ liệu/quyền vẫn có nguồn có thẩm quyền và writer rõ ràng.
3. Giữ liên tục một danh tính chuẩn khi ID từ HRIS, directory, IdP, SCIM hoặc application khác nhau.
4. Xử lý Joiner–Mover–Leaver, nhóm/role RBAC/ABAC, SSO, session/token và tài khoản phi con người xuyên hai hệ.
5. So sánh kết quả của hệ cũ/mới theo **ngữ nghĩa quyền truy cập**, phát hiện drift có ý nghĩa thay vì chỉ so chuỗi hoặc số bản ghi.
6. Thiết lập guardrail cho ghi kép, sự kiện cũ đến muộn, dữ liệu nguồn thiếu, tạo account trùng, bulk grant/revoke và rollback.
7. Lập kế hoạch từng cohort, diễn tập lỗi, đo KPI và nghiệm thu dual run dựa trên bằng chứng trước khi retire hệ cũ.

**Tình huống xuyên suốt:** Doanh nghiệp chuyển IAM từ directory/IdP cũ sang hệ mới trong khi vẫn vận hành các ứng dụng dùng SSO và SCIM. Một số nhân viên được chuyển trước, các nhóm khác chưa chuyển. Nếu nhân viên chuyển phòng ban hoặc nghỉ việc đúng lúc, hệ cũ và mới phải phản ánh cùng quyết định quyền hợp lệ mà không vô tình mở lại tài khoản đã bị thu hồi.

## 2. Dual run là gì?

**Dual run** là giai đoạn hai kiến trúc hoặc hai đường xử lý IAM cũ–mới cùng được duy trì có kiểm soát để đối chiếu kết quả, chuyển dần khối lượng công việc và chứng minh khả năng vận hành trước khi hệ cũ được ngừng sử dụng. Tùy mục tiêu, đường mới có thể chỉ tính thử hoặc thực sự phục vụ một nhóm người dùng/ứng dụng.

Khái niệm này không bắt buộc phải có **hai hệ cùng ghi production**. Ngược lại, hai writer không điều phối cùng sửa user, group hoặc entitlement thường là nguồn gây sai lệch và cấp quyền tồn dư.

| Khái niệm | Đường cũ | Đường mới | Mục tiêu |
|---|---|---|---|
| **Shadow run** | Phục vụ production, giữ quyền ghi hiện hữu | Đọc dữ liệu, tính quyết định mô phỏng, không tác động đích | So mapping và policy trước khi chuyển |
| **Parallel validation** | Xử lý theo đường hiện hành | Xử lý tương đương rồi so normalized results | Chứng minh logic và dữ liệu |
| **Coexistence** | Tiếp tục phục vụ những cohort/ứng dụng chưa chuyển | Phục vụ cohort/ứng dụng đã chuyển | Chuyển dần với ranh giới trách nhiệm |
| **Dual run có kiểm soát** | Có thể vừa xử lý workload được phân công vừa cho phép so sánh | Cùng tồn tại trong cửa sổ giới hạn | Vận hành chuyển tiếp và đánh giá độ ổn định |
| **Dual write** | Ghi trạng thái ở một đích | Ghi trạng thái ở đích khác hoặc cùng đích | Chỉ an toàn khi có owner/ordering/idempotency và ranh giới rõ |
| **Cutover** | Giảm/đóng traffic hoặc quyền ghi | Nhận traffic/quyền ghi chính thức | Chuyển hệ có thẩm quyền |
| **Rollback/failback** | Nhận lại những phần cần phục hồi theo kế hoạch | Tạm dừng hoặc giảm vai trò | Phục hồi kiểm soát mà không làm sai JML |

Một thiết kế tốt nêu rõ **dual run đang so cái gì**, **hệ nào thực sự phục vụ ai**, **hệ nào được phép ghi trường gì** và **điều kiện nào cho phép kết thúc**.

### 2.1. Ví dụ kiến trúc cơ bản

~~~mermaid
flowchart LR
    SRC["HRIS / nguồn nhà thầu có thẩm quyền"] --> EV["Chuẩn hóa sự kiện và version"]
    EV --> IAM["IAM/IGA policy và canonical identity"]
    IAM --> OLD["Pipeline IAM cũ"]
    IAM --> NEW["Pipeline IAM mới"]
    OLD --> T1["Directory/IdP hoặc ứng dụng cũ"]
    NEW -. "Shadow / dry-run" .-> CMP["Bộ so sánh kết quả"]
    OLD --> CMP
    NEW --> T2["Đích mới: chỉ với cohort được cấp quyền"]
    T1 --> REC["Đối soát trạng thái thực tế"]
    T2 --> REC
    CMP --> AUD["Audit, drift, guardrail, go/no-go"]
    REC --> AUD
~~~

Sơ đồ là một mô hình tham chiếu. Ở shadow mode, nhánh mới **chỉ tính thử**; ở coexistence, nhánh mới ghi tới **đích và cohort được phê duyệt**. Không có đường nào mặc nhiên được phép ghi đè trạng thái còn lại.

### 2.2. Vì sao IAM khó dual run hơn dịch vụ thông thường?

Trong một dịch vụ chỉ đọc, hai hệ có thể trả cùng dữ liệu rồi so kết quả. Với IAM, một sự kiện như **terminate employee** có thể dẫn tới vô hiệu hóa đăng nhập, gỡ nhóm, thu hồi đặc quyền, vô hiệu hóa account ứng dụng và xử lý session/token. Nếu hai đường cùng ghi không điều phối, kết quả có thể là:

- Account mới bị tạo trùng vì ID tại hai directory khác nhau;
- Quyền đã thu hồi được pipeline cũ cấp trở lại;
- Role trong ứng dụng dao động giữa hai trạng thái;
- Chỉ IdP mới chặn leaver, nhưng trust/phiên cũ vẫn hoạt động;
- Cả hai connector cho rằng mình có thẩm quyền cập nhật nhóm;
- Snapshot lỗi khiến hệ hiểu nhầm hàng nghìn user đã nghỉ việc.

Vì vậy, kiểm thử dual run phải bao gồm **state transition** và **effective access**, không chỉ kết quả xác thực thành công.

## 3. Nguyên tắc bất biến cần bảo toàn

Trước khi thiết kế luồng song song, nhóm IAM, bảo mật, vận hành, HR và chủ ứng dụng cần thống nhất:

| Bất biến | Cách xác minh |
|---|---|
| **Một chủ thể được nhận diện nhất quán** | Old/new IDs đều liên kết với canonical person ID đã xác minh |
| **Nguồn có thẩm quyền xác định vòng đời** | HRIS/nguồn hợp đồng còn quyết định trạng thái JML |
| **Không có writer tranh chấp ngoài thiết kế** | Ma trận ownership theo thuộc tính, role, hệ đích và cohort |
| **Quyền có căn cứ chính sách hiện hành** | So desired entitlement với actual access tại ứng dụng |
| **Mover được thu hồi quyền cũ** | Kiểm thử gỡ group/role, direct grant, PAM và quyền theo record |
| **Leaver bị chặn trên mọi đường còn hoạt động** | Kiểm tra IdP cũ/mới, local auth, session, token, API |
| **Sự kiện lặp/trễ không khôi phục quyền** | Idempotency, version và effective time có kiểm chứng |
| **Nguồn dữ liệu lỗi không thành mass deprovision** | Hold/quarantine khi snapshot rỗng hoặc thay đổi bất thường |
| **Có thể điều tra và phục hồi** | Mapping version, policy version, event ID, actor, approver, audit |
| **Giai đoạn chuyển tiếp có ngày kết thúc và điều kiện thoát** | Rõ KPI, owner, kế hoạch retire trust/connector/credential cũ |

Hai đường có thể có khác biệt kỹ thuật được chấp nhận, ví dụ object ID hoặc định dạng claim, nhưng phải tạo ra **cùng quyết định nghiệp vụ có hiệu lực** đối với người dùng khi đó là mục tiêu đã thống nhất.

## 4. Xác định phạm vi: chạy song song những gì?

Dự án IAM có thể triển khai dual run ở một hoặc nhiều tầng.

| Tầng | Thành phần cũ/mới | Vấn đề cần đối soát |
|---|---|---|
| **Identity source** | HRIS-A và HRIS-B, vendor source | Trạng thái hợp đồng, ngày hiệu lực, mã nhân viên, manager |
| **Identity registry** | Bảng canonical identity và source links | Cùng chủ thể, không duplicate/merge nhầm |
| **Directory** | AD/LDAP cũ và directory mới | Account, attribute, group, nested membership, SID/ACL |
| **IdP / Federation** | IdP-A và IdP-B | Subject/NameID, issuer, MFA, SAML/OIDC trust, phiên |
| **IAM/IGA policy** | Role engine hoặc workflow cũ/mới | Decision create/grant/revoke, SoD, policy exception |
| **Provisioning** | SCIM/API connector cũ/mới | User/group resource, writer, retry, deactivate |
| **Application** | Ứng dụng/tenant cũ và mới | Role/entitlement, record ownership, local account |
| **Privileged access** | PAM, vault, admin workflow | Quyền nâng cao, secret, phiên quản trị, break-glass |
| **Non-human identity** | Bot, workload identity, service principal | Owner, client ID, scope, certificate/secret, token |

Không nhất thiết chuyển mọi tầng cùng lúc. Ví dụ đổi HRIS nhưng giữ IdP có thể chỉ chạy hai feed dữ liệu ở shadow; đổi IdP có thể cần trust song song theo ứng dụng; chuyển application có thể cần SCIM provisioning tới cả hai app trong một thời gian giới hạn.

### 4.1. Lập inventory phụ thuộc

Cho mỗi thành phần, ghi:

- Owner kỹ thuật và owner nghiệp vụ;
- Số lượng user/group/role/service account trong phạm vi;
- Source of authority và writer;
- Endpoint, API credential, trust, signing key, certificate, callback;
- Mốc thời gian đồng bộ, SLA, khả năng event và snapshot;
- Thuộc tính dùng cho identity matching và authorization;
- Cơ chế session/token invalidation;
- Phụ thuộc với hệ khác, đặc biệt legacy LDAP, local login và direct grant;
- Khả năng read-only, shadow, rollback và data retention.

Ví dụ app CRM hỗ trợ OIDC SSO nhưng vẫn giữ local API token; khi đổi IdP, dual run phải theo dõi **cả đăng nhập qua IdP và API token** vì leaver có thể còn truy cập bằng đường thứ hai.

## 5. Chọn mô hình dual run phù hợp

### 5.1. Shadow mode: có thể đối chiếu mà chưa cấp quyền

Ở shadow mode:

1. Pipeline cũ nhận event nguồn và tiếp tục vận hành production.
2. Pipeline mới nhận **bản sao sự kiện được kiểm soát** hoặc snapshot tương ứng.
3. Pipeline mới resolve identity, tính attribute/group/role mapping và dự kiến lệnh provision.
4. Lệnh mới **không được ghi** tới hệ đích production; chỉ lưu desired state mô phỏng.
5. Bộ so sánh chuẩn hóa kết quả cũ/mới để tìm chênh lệch.
6. Owner phân loại chênh lệch: tương đương, được chấp thuận, lỗi mapping, lỗi quyền hoặc dữ liệu nguồn thiếu.

Shadow là điểm khởi đầu thường hữu ích vì chưa tạo thêm đường tác động; nhưng **không chứng minh connector, token, session hoặc quyền hiệu lực tại ứng dụng mới** nếu chưa chạy pilot thực tế.

### 5.2. Pilot theo cohort

Khi kết quả shadow đã đủ tin cậy, cho một tập người dùng/ứng dụng đại diện đi qua hệ mới:

- Cohort được định nghĩa rõ, có người duyệt, ngày hiệu lực và khả năng quay lại.
- Policy IAM vẫn dùng trạng thái JML có thẩm quyền.
- Writer của từng đích/cohort phải được phân công rõ.
- Khả năng truy cập ứng dụng cũ được ghi nhận và kiểm soát.
- Kết quả thực tế được đọc lại và so với desired state.

Cohort nên có user bình thường, người có nhiều role, manager, admin đặc quyền, người làm từ xa, nhà thầu, guest, service account owner, joiner tương lai, mover, leaver và ứng dụng legacy.

### 5.3. Coexistence: chia trách nhiệm theo ứng dụng hoặc cohort

Ví dụ:

| Ranh giới | Pipeline cũ | Pipeline mới |
|---|---|---|
| Nhân viên nhóm A chưa chuyển | Writer cho directory/IdP/app đã chỉ định | Đọc/so sánh, không tự ghi |
| Nhân viên nhóm B đã chuyển | Đọc hoặc chỉ cập nhật các đích legacy vẫn hợp lệ | Writer cho đích mới đã được phê duyệt |
| Role chung dùng cả hai ứng dụng | Tính từ một policy owner duy nhất | Nhận cùng desired state, ghi đúng target |
| Leaver ở mọi cohort | Thu hồi trên đường cũ còn cho phép truy cập | Thu hồi trên đường mới còn cho phép truy cập |

Hai connector có thể cùng nhận **một quyết định JML** rồi ghi **hai hệ đích khác nhau**, nếu từng target/writer được quản lý độc lập. Điều cần tránh là hai writer cạnh tranh cập nhật **cùng trạng thái quyền của cùng resource** mà không có cơ chế đồng thuận/điều phối.

### 5.4. Federation bridge và dual IdP

Một số dự án dùng broker hoặc federation bridge giữ mặt giao tiếp ổn định cho ứng dụng khi đổi upstream IdP. Đây là lựa chọn có điều kiện:

- Subject/NameID mà ứng dụng nhìn thấy phải được xác minh;
- MFA/conditional access của cả hai đường phải đáp ứng policy;
- Trust cũ không được trở thành đường vòng tránh leaver;
- Broker là một dependency cần giám sát, có phương án khôi phục và audit;
- Không giả định mọi ứng dụng đều hỗ trợ hai issuer/IdP cùng lúc.

## 6. Nguồn có thẩm quyền và quyền ghi trong dual run

**Vấn đề trung tâm:** đồng thời chạy hai hệ không đồng nghĩa có hai nguồn chân lý.

### 6.1. Ma trận authority theo trường và cohort

| Dữ liệu/quyết định | Trước dual run | Trong dual run | Sau cutover |
|---|---|---|---|
| Trạng thái nhân viên | HRIS chính thức | Một HRIS được duyệt; nguồn mới shadow hoặc theo cohort | HRIS mới theo hợp đồng |
| Trạng thái nhà thầu | Vendor/contractor source | Nguồn hợp đồng có thẩm quyền | Vẫn từ nguồn hợp đồng được duyệt |
| Canonical person ID | Identity registry | Giữ bất biến, bổ sung source links | Giữ bất biến |
| Department, manager | HRIS/owner tổ chức | Writer theo thuộc tính và cohort | Owner mới nếu đã chuyển |
| MFA/đăng nhập | IdP hiện hữu | IdP phục vụ từng app/cohort, có chính sách rõ | IdP đích |
| Business role | IAM/IGA và owner nghiệp vụ | Một policy owner và phiên bản được chốt | IAM/IGA đích |
| Group/entitlement | Connector theo target | Một writer cho mỗi target/resource | Writer đích |
| Local app role | Chủ ứng dụng hoặc IAM theo hợp đồng | Không có hai writer tranh chấp | Theo ownership đã phê duyệt |
| Audit/reconciliation | Hệ hiện hành | Thu cả hai hệ, nối correlation ID | Hệ mới + lịch sử theo retention |

Nếu một hệ được phép sửa thuộc tính nhưng hệ kia đồng bộ ngược cùng trường, trạng thái có thể dao động. Trong dual run cần bảng chi tiết: **ai được ghi field nào, vào resource nào, cho cohort nào, tại thời điểm nào**.

### 6.2. Single writer không có nghĩa chỉ có một pipeline

Có thể có nhiều thành phần xử lý: event bus, identity resolver, policy evaluator, provisioning connector, reconciliation worker. **Single writer** là yêu cầu quyền ghi cuối cùng với một tập trạng thái cụ thể. Thiết kế cho phép cả hai pipeline tính kết quả nhưng chỉ một bên được áp dụng thay đổi đối với resource tương ứng.

### 6.3. Cơ chế chuyển quyền ghi an toàn

1. Chốt phạm vi và owner của cohort/đích.
2. Ghi phiên bản mapping/policy và mốc event.
3. Tạm dừng writer cũ đối với phần được chuyển.
4. Đảm bảo backlog cũ đã được xử lý hoặc lưu để deduplicate.
5. Bật writer mới với quyền tối thiểu và cơ chế idempotency.
6. Đối soát actual state trước khi mở rộng traffic.
7. Giữ khả năng pause nhanh nếu phát hiện quyền sai hoặc sự kiện hàng loạt.

Nếu cutover thất bại giữa chừng, không tự bật đồng thời cả hai writer; phải quyết định rõ owner phục hồi.

## 7. Bảo toàn identity continuity khi hai hệ có ID khác nhau

### 7.1. Không dùng email làm khóa ghép duy nhất

Một người có thể có:

- Source ID trong HRIS-A và HRIS-B khác nhau;
- Directory object ID mới, SID khác nếu đổi AD domain/forest;
- OIDC issuer + sub hoặc SAML NameID mới khi đổi IdP;
- SCIM id khác ở từng service provider;
- Application user ID riêng tại app cũ và mới;
- Email, UPN, display name hoặc manager thay đổi.

**Canonical person ID** do identity registry/IAM quản trị giúp liên kết các đối tượng này qua các namespace. Email chỉ là thuộc tính có thể đổi/tái sử dụng, không đủ để tự xác nhận chủ thể.

### 7.2. Bảng crosswalk minh họa

~~~yaml
canonicalPersonId: person-00628
personType: employee
sourceLinks:
  - system: hris-a
    sourceId: E1928
  - system: hris-b
    sourceId: W80441
federatedSubjects:
  - idp: idp-a
    issuer: https://old-idp.example.org/
    subject: old-subject-100
  - idp: idp-b
    issuer: https://new-idp.example.org/
    subject: new-subject-872
accounts:
  - application: crm-old
    accountId: crm-old-user-681
  - application: crm-new
    accountId: crm-new-user-290
verification:
  evidence: verified-hr-crosswalk
  approvedByRole: identity-steward
  version: 5
~~~

Đây là dữ liệu **mô phỏng**; không phải schema chuẩn hay định danh thật. Bảng liên kết cần bảo vệ như dữ liệu nhạy cảm, có owner, phiên bản, bằng chứng matching và retention.

### 7.3. Các trạng thái mapping phải xử lý riêng

| Tình huống | Phản ứng an toàn |
|---|---|
| Một source ID liên kết rõ với canonical ID | Cho phép mapping theo bằng chứng đã duyệt |
| Hai người có cùng email | Không auto-merge; kiểm tra namespace và chủ thể |
| Người đổi email/họ tên | Giữ canonical ID, cập nhật thuộc tính liên hệ |
| Nhà thầu chuyển thành nhân viên | Xác minh cùng chủ thể, tính lại tư cách và role |
| Một account app trỏ đến hai người | Dừng auto-link, cách ly và điều tra ngay |
| Một người có account thường và admin riêng | Duy trì persona/account purpose, không gộp quyền |
| Guest từ tenant khác cùng địa chỉ email | Tách federation/tenant context, kiểm tra sponsor |
| Account không rõ owner | Xác minh orphan hay non-human identity trước khi xử lý |

Tách **link** (kết nối các account đã xác minh thuộc cùng chủ thể) với **merge** (hợp nhất hồ sơ/dữ liệu từng được coi là độc lập). Merge có rủi ro cao hơn, cần quy trình riêng.

## 8. Sự kiện JML: trạng thái hiện hành phải thống nhất

Hai pipeline có thể nhận cùng một sự kiện nhưng xử lý ở thời điểm khác nhau. Thiết kế phải bảo đảm quyết định cuối cùng dựa trên **trạng thái JML có thẩm quyền**, không dựa trên thao tác đến sau cùng.

### 8.1. Joiner

Với người mới:

- Xác minh danh tính và canonical ID trước khi tạo/link account;
- Chuẩn bị tài khoản đúng chính sách, tách **tồn tại account** với **được phép hoạt động**;
- Không cấp quyền trước effective date nếu policy không cho phép;
- Xác minh JIT/SCIM không tạo duplicate khi cùng user có mặt ở hai IdP/app;
- Đối soát MFA, SSO, group và quyền app thực tế ở cohort đã chuyển.

Một nhân viên chưa tới ngày làm việc có thể xuất hiện trong HRIS và directory nhưng không được coi là user đang active cho mọi ứng dụng.

### 8.2. Mover

Khi người dùng chuyển từ Sales sang Finance:

1. Nguồn có thẩm quyền phát event với thời điểm hiệu lực.
2. IAM tính lại business role và thuộc tính ABAC theo policy hiện hành.
3. Thu hồi nhóm/role Sales cũ và quyền cấp trực tiếp đã hết lý do.
4. Cấp role Finance sau kiểm tra SoD và phê duyệt phù hợp.
5. Áp thay đổi ở **cả hệ cũ và mới đang còn phục vụ truy cập**.
6. Kiểm thử quyền dữ liệu: không còn xem/sửa record Sales trái chính sách.
7. Kiểm tra session/token và app cache có thể giữ claim cũ trong thời gian nhất định.

Nếu chỉ cập nhật đích mới còn app cũ cho phép đăng nhập, user vẫn có thể dùng quyền Sales cũ qua đường legacy.

### 8.3. Leaver

Với người đã rời tổ chức, phải:

- Chặn đăng nhập qua tất cả IdP và đường local còn hoạt động;
- Disable account/thu hồi group, role, direct grant ở các ứng dụng liên quan;
- Xử lý session, refresh token, API key, SSH key và credential theo khả năng từng hệ;
- Thu hồi privileged access và xác minh PAM;
- Bàn giao owner tài nguyên, service account và dữ liệu theo policy;
- Đọc trạng thái thực tế sau khi yêu cầu revoke, đo SLA và lưu audit.

**Một hệ đã disable user không chứng minh hệ còn lại cũng đã disable.** Chỉ cần một trust cũ hoặc token còn hợp lệ là user có thể tiếp tục truy cập.

### 8.4. Rejoiner và người dùng bên ngoài

Người quay lại phải được xác minh lại; link theo chính sách và **tính quyền từ đầu**, không tự phục hồi mọi role cũ. Nhà thầu có nguồn hợp đồng và thời hạn riêng; khách/đối tác có sponsor, tenant và expiry. Đừng phụ thuộc hoàn toàn vào HRIS nhân viên để xử lý tất cả.

### 8.5. Tránh hồi sinh quyền do sự kiện cũ

~~~text
09:00  User đang ở role Sales
09:10  Mover: sang Finance, event version 22
09:12  Hai đích áp desired state Finance, gỡ Sales
09:15  Retry của event version 21: add Sales
09:16  Nếu áp theo thời điểm nhận => Sales quay lại (SAI)
09:16  Nếu kiểm tra version/state => bỏ event cũ (ĐÚNG)
~~~

Để giải quyết các trường hợp sửa hồi tố, cần quy tắc ưu tiên và phiên bản từ nguồn đáng tin thay vì chỉ so timestamp của máy chủ nhận event.

## 9. Chuẩn hóa trạng thái trước khi so sánh hai hệ

Dữ liệu thô của hệ cũ và mới không nhất thiết giống nhau. So sánh nên dựa trên **mô hình trạng thái chuẩn**.

### 9.1. Ví dụ normalized identity state

~~~yaml
canonicalPersonId: person-00628
lifecycle:
  state: active
  effectiveAt: "2026-11-23T09:00:00+07:00"
  sourceVersion: 22
attributes:
  department: finance
  employmentType: employee
  managerCanonicalId: person-00104
accounts:
  - target: idp-a
    expectedEnabled: true
  - target: idp-b
    expectedEnabled: true
entitlements:
  - target: crm-new
    role: finance-reader
    scope: cost-center-C101
  - target: crm-old
    role: finance-report-view
    scope: cost-center-C101
policyVersion: 11
mappingVersion: 5
~~~

Hai role khác tên có thể cùng quyền nghiệp vụ theo contract được phê duyệt. Ngược lại, hai role cùng tên vẫn có thể khác scope. Do đó, canonical comparison cần xét **action, resource, scope, conditions, approval và effective time**.

### 9.2. Những chiều cần so

| Chiều | Hệ cũ | Hệ mới | Điều kiện chấp nhận |
|---|---|---|---|
| Chủ thể | Old source/account IDs | New source/account IDs | Cùng canonical person ID được xác minh |
| Trạng thái JML | User active/disabled | User active/disabled | Cùng trạng thái có hiệu lực cho phần đang phục vụ |
| Thuộc tính tổ chức | Department/manager code cũ | Mã chuẩn mới | Cùng ngữ nghĩa và nguồn authority |
| Quyền | Legacy group/role | Target role/ABAC | Tương đương hành vi trong scope được phê duyệt |
| MFA/SSO | Policy tại IdP-A | Policy tại IdP-B | Đáp ứng yêu cầu bảo mật, không bypass |
| Session/token | Phiên và token legacy | Phiên và token mới | Không còn đường truy cập trái SLA |
| Account ứng dụng | Legacy account ID | New app account ID | Cùng user/owner dữ liệu, không duplicate |
| Audit | Event/log hệ cũ | Event/log hệ mới | Truy được correlation ID, actor, kết quả |

Không so bằng cách yêu cầu **mọi cột giống hệt**; hãy chuẩn hóa trước và chỉ cho phép những khác biệt được reviewer chấp thuận.

## 10. Reconciliation và phân loại drift

**Reconciliation** là lấy desired state được IAM/IGA phê duyệt so với actual state đọc từ directory, IdP, ứng dụng, SCIM target và hệ đặc quyền.

### 10.1. Ba loại chênh lệch khác nhau

- **Raw difference:** cùng thông tin được mã hóa khác, ví dụ FIN-01 và finance.
- **Expected difference:** hệ cũ/mới có cách biểu diễn khác đã được phê duyệt, hoặc cohort chưa chuyển.
- **Security-relevant drift:** user bị cấp sai role, app account trùng, quyền không được thu hồi, policy MFA yếu đi hoặc quyền dữ liệu bị mở rộng.

Một bộ so sánh tốt phân loại nguyên nhân, không biến toàn bộ khác biệt về định dạng thành incident bảo mật.

### 10.2. Ma trận xử lý

| Sai lệch | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Cùng người nhưng có hai app account ngoài dự kiến | JIT/SCIM cùng tạo hoặc sai matching | Pause auto-create, xác minh linking |
| IdP-B không có user hợp lệ | Connector lỗi hoặc source link thiếu | Retry có kiểm soát, không tạo account mù |
| Department khác giữa hai nguồn | Lookup code, thay đổi chưa có hiệu lực | Kiểm tra authority, mapping version, effective time |
| Role ở đích rộng hơn nguồn | Mapping theo tên hoặc mất team scope | Cô lập quyền, sửa policy, owner phê duyệt |
| Leaver active ở một IdP | Deprovision trễ, trust cũ còn mở | Chặn đường truy cập, điều tra SLA |
| App-local role còn sau remove group | Direct grant/connector không quản lý role cục bộ | Thu hồi theo owner và kiểm chứng actual access |
| Ứng dụng mới chưa phản ánh thay đổi | Eventual consistency, queue/rate limit | Đo lag theo SLA, retry và ticket |
| Hai writer đảo trạng thái liên tục | Đồng bộ hai chiều, xung đột authority | Pause writer, sửa rule/ownership |
| Số user giảm mạnh trong snapshot | Nguồn batch thiếu, lỗi filter/export | Hold bulk action, xác minh nguồn |
| Tài khoản dịch vụ không có owner | Registry chưa được chuyển | Review, bàn giao owner hoặc thu hồi có kiểm soát |

### 10.3. Tính đến độ trễ được phép

Hai hệ có thể khác nhau trong một khoảng ngắn do replication, event queue hoặc cache. Bộ so sánh nên:

1. Gắn watermark/version cho snapshot;
2. So những bản ghi đã qua khoảng đệm hợp lý cho eventual consistency;
3. Phân biệt **pending** và **failed**;
4. Tăng mức ưu tiên với lỗi liên quan leaver hoặc đặc quyền;
5. Đo reconciliation lag và tuổi của drift;
6. Kiểm tra cuối cùng tại **hệ thực thi quyền** thay vì chỉ tại queue.

Không dùng độ trễ kỹ thuật làm lý do cho phép leaver tiếp tục truy cập ngoài SLA đã được phê duyệt.

### 10.4. Read-only không có nghĩa tự động an toàn

Một ứng dụng cũ có chế độ chỉ đọc vẫn có thể chứa thông tin nhạy cảm. Nếu account leaver vẫn đọc được dữ liệu tại hệ cũ, đó là truy cập trái phép dù hệ không cho sửa. Quyền đọc, API export và token phải được quản lý trong suốt coexistence.

## 11. SSO và hai Identity Provider

### 11.1. Xác định đường đăng nhập của từng ứng dụng

Với mỗi ứng dụng:

- SP/RP có chấp nhận đồng thời hai IdP/issuer không?
- Nếu chỉ chấp nhận một IdP, router/broker hay cutover ứng dụng sẽ hoạt động thế nào?
- OIDC **issuer + sub** hoặc SAML **issuer + NameID** có thay đổi không?
- App có liên kết account hiện hữu bằng internal ID hay sẽ tạo account mới?
- MFA, conditional access, device trust và session policy có tương đương không?
- Chứng thư ký, JWKS, ACS/redirect URI và logout có được cấu hình/kiểm thử đúng không?
- Đường login local hoặc federation bên thứ ba có còn hoạt động không?

**OIDC sub** là định danh theo issuer, đôi khi là pairwise theo client. Email không thay thế được cặp issuer + sub để ghép người. Với SAML, NameID format và issuer phải được đánh giá theo hợp đồng ứng dụng.

### 11.2. Token/phiên sống lâu hơn cutover

Khi đổi IdP hoặc gỡ group, session ứng dụng có thể tiếp tục tồn tại. ID token, access token, refresh token, cookie, API key và session local có vòng đời khác nhau.

Thiết kế leaver và emergency revoke cần:

- Biết IdP nào vẫn được ứng dụng tin cậy;
- Có API/process revoke session/refresh token nếu hệ hỗ trợ;
- Biết token tự chứa có thể có hiệu lực tới khi hết hạn;
- Đặt session lifetime, step-up và reauthentication theo rủi ro;
- Đối soát đường truy cập thật từ ứng dụng/resource server;
- Ghi nhận những hệ không có khả năng thu hồi tức thời để có SLA và biện pháp giảm rủi ro.

Không tự hạ yêu cầu MFA chỉ để tăng tỷ lệ login success trong pilot. Nếu cần ngoại lệ, phải giới hạn đối tượng, thời hạn và có phê duyệt/audit.

## 12. SCIM, connector và đồng bộ quyền song song

### 12.1. Những định danh phải giữ đúng phạm vi

SCIM có **id** do service provider cấp và **externalId** do phía client quản lý. Khi app cũ/mới đều nhận provisioning, mỗi ứng dụng có thể cấp User.id/Group.id khác nhau cho cùng canonical person/group.

Ví dụ:

| Giá trị | Hệ phát hành/phạm vi | Cách dùng |
|---|---|---|
| Canonical person ID | Identity registry | Liên kết cùng người qua hai hệ |
| Old SCIM User.id | Application cũ | Thao tác với user resource ở SP cũ |
| New SCIM User.id | Application mới | Thao tác với resource ở SP mới |
| SCIM externalId | Client IAM theo hợp đồng | Liên kết identity với resource được provider hỗ trợ |
| Group.id | Từng SCIM SP | Tham chiếu thành viên trong provider đó |
| OIDC issuer + sub | IdP issuer | Xác thực chủ thể cho RP |

Không copy ID của service provider cũ vào trường resource ID của provider mới, trừ khi hệ đích tài liệu hóa rõ một cơ chế migration hỗ trợ việc đó.

### 12.2. Kỹ thuật provisioning an toàn

- **Idempotency:** event được gửi lại không tạo account/role lặp ngoài dự kiến.
- **Deterministic mapping:** cùng input và mapping version cho cùng quyết định.
- **Retry/backoff:** tuân rate limit và phân biệt lỗi tạm thời/lỗi dữ liệu.
- **Per-target outcome:** không coi một batch thành công nếu một ứng dụng không cập nhật.
- **Ordering:** event cũ không ghi đè trạng thái mới.
- **Membership semantics:** thêm/gỡ phần tử thay vì vô tình replace toàn bộ group.
- **Soft delete/disable:** hiểu khác biệt vendor và retention.
- **Reconciliation:** đọc lại account/group/role thực tế, bao gồm direct grant.
- **Pause switch:** có thể ngừng writer đang gây sai hàng loạt.

Một SCIM API trả thành công chỉ chứng minh lời gọi được xử lý theo cơ chế của SP, không chứng minh API key, phiên hoặc quyền cục bộ đã mất hiệu lực.

### 12.3. Chế độ vận hành được kiểm soát

~~~yaml
dualRun:
  mode: cohort-coexistence
  sourceOfTruth:
    lifecycle: authoritative-hr
    canonicalIdentity: identity-registry
    businessRoles: iam-policy
  cohorts:
    - name: group-a
      primaryIdentityPath: old-idp
      productionWriter: old-connector
    - name: group-b
      primaryIdentityPath: new-idp
      productionWriter: new-connector
  comparison:
    normalizeIdentity: true
    normalizeEntitlements: true
    readActualTargetState: true
  controls:
    quarantineAmbiguousIdentity: true
    holdUnexpectedBulkChanges: true
    checkEventVersion: true
    auditChanges: true
~~~

YAML trên là **ví dụ hợp đồng cấu hình do bài học tự định nghĩa**, không phải file cấu hình chuẩn của một sản phẩm IAM. Mục tiêu là diễn đạt trạng thái primary, writer, comparator và guardrail một cách minh bạch.

## 13. Nhóm, role, RBAC/ABAC và SoD xuyên hai hệ

### 13.1. Chuyển theo quyền có hiệu lực

Directory group và role ứng dụng không luôn tương đương 1:1.

| Cấu hình nguồn | Cấu hình đích | Điều cần xác minh |
|---|---|---|
| Sales-HCM group | TeamReader + scope=HCM | Không xem dữ liệu team khác |
| FinanceApprover | FinanceApprove với hạn mức | Quy trình duyệt và SoD |
| Nested Sales group | Direct target membership nếu đích không hỗ trợ nested | Không bỏ sót hoặc giữ thừa quyền |
| Legacy admin | Một số admin role tối thiểu | Không tự cấp global admin |
| Direct app export role | Quyền xuất dữ liệu nhạy cảm có approval | Không mặc định di chuyển mọi exception |
| Contractor project group | Project role có ngày hết hạn | Thu hồi khi hết hợp đồng |

Đánh giá theo **action, resource, scope, conditions**. Tên group/role giống nhau không đủ chứng minh tương đương; một nhóm IdP đúng cũng không bảo đảm role tại ứng dụng đã được cập nhật.

### 13.2. Dynamic và nested group

Khi nguồn cũ hỗ trợ nested group nhưng đích chỉ nhận direct membership, bộ tính quyền có thể cần mở rộng effective membership. Cần kiểm soát cycle, namespace, group owner, group không tồn tại, duplicate và nhiều đường cấp cùng một entitlement.

Dynamic group dựa trên department hoặc employmentType cần dùng thuộc tính chuẩn hóa và source có thẩm quyền. Giá trị thiếu/không rõ không được chuyển thành một role mặc định mạnh.

### 13.3. SoD qua hai hệ

Người dùng có thể giữ role Requester ở app cũ và nhận role Approver ở app mới. Kiểm tra SoD **trên tổ hợp quyền xuyên hệ**, không chỉ từng app riêng lẻ.

Ví dụ: cùng người không được tạo vendor ở ERP-Legacy và duyệt thanh toán vendor đó ở ERP-Cloud nếu chính sách phân tách nhiệm vụ cấm. Dual run phải có danh mục hành động xung đột và phát hiện quyền hợp nhất.

### 13.4. Quyền trực tiếp và ngoại lệ

Một số quyền không nằm trong group/SCIM: local admin, delegated permission, record ACL, database grant và PAM entitlement. Phải inventorize, gán owner, chuyển khi hợp lệ và thu hồi khi hết lý do. Ngoại lệ tạm thời phải có expiry/approver và được review sau go-live.

## 14. Guardrail: bảo vệ khỏi sự cố hàng loạt

### 14.1. Trạng thái nguồn không đầy đủ không phải leaver

Có ít nhất các loại input:

- Snapshot đầy đủ được xác thực;
- Partial update chỉ có các field thay đổi;
- Event explicit terminated có hiệu lực;
- Nguồn timeout/không khả dụng;
- Batch bị cắt, lỗi filter hoặc trả về tập rỗng bất thường.

Nếu pipeline mới hiểu “user không có trong snapshot lỗi” là “đã nghỉ việc”, nó có thể gửi hàng nghìn lệnh deactivate. Thiết kế phải tách **source unavailable/incomplete** khỏi **confirmed leaver**.

### 14.2. Điều kiện hold / yêu cầu xác minh

- Số account bị disable hoặc group membership bị gỡ tăng bất thường;
- Số account không mapping được vượt baseline;
- Một department/tenant mất gần hết user trong một batch;
- Tăng đột biến cấp role đặc quyền hoặc admin;
- Chênh lệch quyền vượt phạm vi được phê duyệt;
- Mapping một account tới nhiều canonical identities;
- Sự kiện đến sai thứ tự làm thay đổi trạng thái leaver;
- IdP/application quan trọng có tỷ lệ login/provisioning failure tăng mạnh.

**Ngưỡng cụ thể phải xác lập theo dữ liệu baseline, quy mô và rủi ro**, không lấy con số ví dụ làm chuẩn. Hold chỉ ảnh hưởng thao tác nghi vấn; đường xử lý sự kiện leaver đáng tin vẫn cần đáp ứng SLA.

### 14.3. Bảo vệ production trong shadow mode

Pipeline shadow chỉ cần read permission và môi trường tính toán thích hợp. Không dùng credential có quyền ghi production nếu không cần. Tách audit và dữ liệu test, tránh gửi thông báo hoặc thay đổi account thật từ job dry-run.

## 15. Data flow, event ordering và idempotency

### 15.1. Các mốc thời gian

Một lifecycle event có thể có:

| Trường | Ý nghĩa |
|---|---|
| eventId | Khóa deduplicate |
| sourceSystem | Hệ có thẩm quyền phát sự kiện |
| sourceVersion/sequence | Thứ tự logic trong nguồn |
| effectiveAt | Thời điểm thay đổi có hiệu lực nghiệp vụ |
| emittedAt | Thời điểm phát sự kiện |
| receivedAt | Thời điểm IAM nhận |
| processedAt | Thời điểm hệ áp dụng |
| mappingVersion/policyVersion | Quy tắc dùng để tính quyết định |

Nếu quy tắc nguồn không có sequence tin cậy, cần cơ chế đối chiếu trạng thái hiện hành từ nguồn có thẩm quyền. Chỉ dùng receivedAt làm thứ tự có thể biến sự kiện cũ gửi lại thành cập nhật mới.

### 15.2. Mã giả quyết định trước khi ghi

~~~text
processIdentityEvent(event):
    verifyTrustedSource(event)
    if alreadyProcessed(event.eventId):
        return NO_OP

    person = resolveVerifiedCanonicalIdentity(event)
    if person is ambiguous:
        quarantine(event)
        return NEED_REVIEW

    if event.version < currentAcceptedVersion(person):
        return STALE_EVENT

    current = fetchAuthoritativeLifecycleState(person)
    desired = evaluateCurrentPolicy(
        person, current, mappingVersion, approvedExceptions
    )

    shadowResult = evaluateNewPipelineWithoutWriting(person, desired)
    compareNormalizedPolicyResults(desired, shadowResult)

    if unexpectedBulkGrantOrRevoke(desired):
        pauseAffectedWriterAndRequestApproval(event)
        return HOLD

    for each target in authorizedTargets(person.cohort):
        applyIdempotentlyUsingAssignedWriter(target, desired)
        reconcileActualTargetAccess(target, person, desired)

    audit(event.eventId, person.id, mappingVersion, results)
~~~

Đây là **pseudocode** cho cách nghĩ về control plane, không phải mã production. Pipeline thực tế cần transaction/queue hoặc outbox phù hợp, xử lý cạnh tranh, retry, timeout, partial failure, dấu vết và kiểm soát quyền connector.

### 15.3. Dual write và thất bại từng phần

Ví dụ lệnh disable user thành công ở IdP-A nhưng thất bại ở IdP-B. Không thể coi event “DONE” chỉ vì một đích thành công. Cần trạng thái **per-target**, retry có kiểm soát, cảnh báo theo mức rủi ro và đối soát thực tế.

Với các thao tác không đảo ngược như revoke credential, xóa account, chuyển owner dữ liệu hoặc gửi thông báo, cần cân nhắc idempotency và bù trừ riêng; không gọi lại mù mà không xem trạng thái hiện hành.

## 16. Quy trình triển khai dual run từ đầu đến cuối

### Giai đoạn 1 — Discover và xác định mục tiêu

1. Chỉ rõ dự án thay identity source, directory, IdP, application hay nhiều tầng.
2. Lập inventory user, group, role, account ứng dụng, service identity, token và dependency.
3. Xác định mô hình dữ liệu chuẩn, identity crosswalk và authority theo thuộc tính.
4. Xác định desired state và quyền hiệu lực cần bảo toàn ở từng ứng dụng.
5. Chụp baseline SLA JML, login failure, provisioning error, drift và access review.
6. Định nghĩa mục tiêu chứng minh của shadow/dual run và tiêu chí thoát.

### Giai đoạn 2 — Chuẩn bị môi trường và hợp đồng

1. Thiết kế canonical identity mapping old/new IDs có bằng chứng.
2. Viết attribute, group, role và app account mapping có phiên bản.
3. Cấu hình hệ mới, trust/connector và quyền read-only cho shadow.
4. Xây comparator chuẩn hóa output theo ngữ nghĩa business role/effective access.
5. Cấu hình logging, correlation ID, dashboard, cảnh báo, quarantine và guardrail.
6. Thiết lập single writer matrix, cohort boundaries và kế hoạch rollback.
7. Xác minh dữ liệu nhạy cảm được hạn chế theo chính sách retention/privacy.

### Giai đoạn 3 — Shadow/dry-run

- Chạy các event joiner/mover/leaver điển hình qua cả hai engine.
- So normalized identity, role, policy decision và thời điểm hiệu lực.
- Thử unknown department, null/absent field, manager reference chưa resolve, duplicate email.
- Thử event lặp/sai thứ tự, source batch rỗng, connector timeout trong môi trường an toàn.
- Phân loại chênh lệch, sửa rule hoặc xử lý exception với owner.
- Chỉ coi shadow đạt khi các khác biệt security-relevant được giải thích/chấp thuận.

### Giai đoạn 4 — Pilot có traffic và provisioning thật

Chọn một cohort đại diện về đơn vị, role, thiết bị, ứng dụng, nhà thầu và quyền đặc quyền. Kiểm thử:

- SSO/MFA/conditional access qua đường đích;
- Account linking, SCIM create/update/disable và JIT;
- Quyền cho phép/bị từ chối, ABAC scope và SoD;
- Token/session revocation, app-local role và legacy access;
- Service job, workload OAuth, owner và secret rotation;
- Quyền thu hồi của mover/leaver phát sinh trong cửa sổ;
- Failover, dừng writer, phục hồi với event delta.

### Giai đoạn 5 — Coexistence theo cohort

1. Xác nhận go/no-go của cohort theo KPI và bằng chứng.
2. Chuyển quyền ghi/traffic từng phần theo ma trận đã phê duyệt.
3. Ghi watermark event, snapshot và mapping/policy version.
4. Áp delta JML theo trạng thái mới nhất; ngăn duplicate và stale event.
5. Đọc actual state từ cả hệ cũ và mới, phân biệt expected vs security drift.
6. Xử lý incident và exception có owner, SLA, rollback trigger.
7. Chỉ mở rộng cohort khi quyền hiệu lực và revocation đạt.

### Giai đoạn 6 — Cutover toàn bộ và retire

- Khẳng định hệ mới có thẩm quyền rõ cho các luồng đã chuyển.
- Đối soát user, group, role, MFA, session/token, app-local direct grant và workload.
- Kiểm tra không còn phụ thuộc có quyền truy cập qua IdP/connector/app cũ ngoài phạm vi được duyệt.
- Thu hồi credential, signing trust, client, API key, account local và quyền admin cũ theo kế hoạch.
- Giữ mapping/audit đủ lâu cho kiểm toán và rollback theo retention policy.
- Nghiệm thu bằng evidence của owner bảo mật, IAM, vận hành và ứng dụng.

## 17. KPI và exit criteria

Không dùng một KPI duy nhất như “100% user sync” để quyết định kết thúc dual run.

| KPI | Cách đo | Ý nghĩa |
|---|---|---|
| **Verified identity mapping coverage** | Identity có old/new links được xác minh / tổng trong phạm vi | Nguy cơ sai người/duplicate |
| **Normalized policy agreement** | Quyết định quyền tương đương / tổng quyết định đủ điều kiện so | Logic policy và mapping |
| **Entitlement drift** | Quyền actual khác desired, tách loại và risk | Lỗi cấp/thu hồi quyền |
| **Privileged drift / SoD violations** | Số quyền đặc quyền/role xung đột ngoài phê duyệt | Rủi ro cao cần ưu tiên |
| **Duplicate/orphan account rate** | Account trùng/vô chủ ngoài thiết kế / tổng account | Chất lượng linking và lifecycle |
| **Provisioning success/latency** | Tác vụ đạt trạng thái mong đợi và độ trễ từng target | Khả năng vận hành connector |
| **Leaver revocation latency** | Thời gian từ effective leaver đến khi các đường truy cập được thu hồi | Tuân SLA và giảm quyền tồn dư |
| **SSO/MFA failure rate** | Lỗi theo app, cohort, browser, thiết bị và nguyên nhân | Ảnh hưởng người dùng, chính sách |
| **Reconciliation lag** | Trễ giữa thay đổi nguồn và phát hiện/điều chỉnh drift | Tính kịp thời |
| **Unresolved exceptions** | Số lượng và tuổi các ca chờ phê duyệt | Khả năng kết thúc cohort |
| **Old-path dependency count** | Số ứng dụng/token/client còn cần đường cũ | Điều kiện retire |
| **Rollback rehearsal result** | Kết quả phục hồi đúng JML và quyền | Mức sẵn sàng khi sự cố |

**Exit criteria** cần được phê duyệt từ đầu, ưu tiên zero unresolved **critical security drift** trong phạm vi theo policy tổ chức, test leaver/privileged pass, ownership rõ và các ngoại lệ còn mở được quản lý. Những con số cụ thể do đơn vị vận hành đặt từ baseline và mức rủi ro; không coi ví dụ này là tiêu chuẩn áp dụng mọi tổ chức.

## 18. Bảo mật và kiểm toán trong giai đoạn song song

### 18.1. Quyền cho pipeline

- Shadow engine nên dùng quyền **read-only** và tách credential khỏi production writer.
- Writer phải có quyền tối thiểu theo resource/capability, không mặc định Global Admin.
- API secret, signing key, token được quản lý qua secret manager/vault và rotate theo runbook.
- Tách vai trò người phê duyệt grant đặc quyền với người thực thi migration khi cần.
- Mapping/crosswalk chứa PII phải được mã hóa, phân quyền và retention phù hợp.
- Group/role exception có owner, expiry và review.
- Break-glass được quản trị, giám sát và diễn tập độc lập khi federation lỗi.

### 18.2. Audit trail cần giữ

| Trường audit | Mục đích |
|---|---|
| eventId, correlationId | Liên kết nguồn → IAM cũ/mới → các target |
| canonicalPersonId, old/new account IDs | Xác định đúng chủ thể trong hai hệ |
| sourceSystem, sourceVersion, effectiveAt | Giải thích trạng thái vòng đời được dùng |
| mappingVersion, policyVersion | Giải thích sự khác biệt quyết định |
| cohort, target, writer | Biết hệ nào có quyền ghi vào thời điểm thay đổi |
| before/after, desired/actual | Tái dựng quyền và phát hiện drift |
| actor, approver, exception, ticket | Trách nhiệm phê duyệt và xử lý |
| timestamp, outcome, retry, error | Điều tra latency, partial failure hoặc incident |

Không ghi password, raw access token, refresh token, private key hay dữ liệu nhân sự nhạy cảm không cần thiết vào log. Nếu lưu claim/attribute để đối soát, phải áp data minimization và che dữ liệu khi phù hợp.

## 19. Tài khoản dịch vụ và workload identity trong dual run

Các tài khoản phi con người thường không nhận trạng thái JML trực tiếp từ HRIS, nhưng vẫn có owner là người hoặc bộ phận.

| Thành phần | Cần đối soát trước/sau | Rủi ro |
|---|---|---|
| OAuth client/service principal | Client ID, issuer, audience, scope, owner | Token cũ vẫn dùng, scope đích rộng |
| Bot tích hợp | App account, API role, webhook token | Tạo duplicate bot hoặc mất owner |
| CI/CD job | Federation trust, secret/certificate, permission | Job lỗi hoặc đặc quyền quá mức |
| Service account hệ điều hành | Directory/group và service dependency | Hỏng xác thực, vẫn có credential cũ |
| Break-glass admin | Khả năng truy cập khi IdP lỗi, MFA, audit | Bị khóa ngoài hoặc trở thành đường vòng |
| Workload từ bên thứ ba | Partner trust, owner, expiry | Kết nối cũ tiếp tục có quyền |

Một workflow dual run phù hợp cho bot:

1. Inventory workload, owner, target và quyền hiện tại.
2. Tạo identity/credential đích có quyền tối thiểu.
3. Chạy integration test với dữ liệu an toàn; theo dõi API behavior và audit.
4. Chuyển client/endpoint theo owner đã phê duyệt.
5. Thu hồi hoặc rotate token cũ khi đường mới đạt; kiểm tra còn ai sử dụng credential cũ.
6. Nếu owner cá nhân nghỉ việc, chuyển trách nhiệm qua registry và access review; không tự cắt job production mà chưa đánh giá phụ thuộc.

Non-human identity cần **vòng đời ownership, credential và entitlement** riêng, dù con người chịu trách nhiệm có thể tham gia JML.

## 20. Cutover và rollback: khôi phục trạng thái, không khôi phục mù quyền

### 20.1. Cutover checklist

Trước khi chấp thuận:

- [ ] Có inventory thành phần, ứng dụng, IdP, connector, token, group và owner.
- [ ] Đã xác minh identity crosswalk và role/attribute mapping.
- [ ] Có single writer matrix cho từng target/cohort, không còn cạnh tranh ghi chưa giải quyết.
- [ ] Shadow và pilot đã chứng minh policy/effective access, gồm negative test.
- [ ] JML joiner, mover, leaver, rejoiner, contractor và service identity đã được thử.
- [ ] Có guardrail cho source rỗng, mapping mơ hồ và bulk grant/revoke.
- [ ] Có snapshot, event watermark, delta replay, audit và đối soát.
- [ ] MFA, SSO, SCIM, local auth, session/token revocation và PAM đạt test.
- [ ] Có người phê duyệt go/no-go, on-call và phương án incident.
- [ ] Rollback đã được diễn tập với JML phát sinh sau snapshot.

### 20.2. Sự cố nào kích hoạt pause/failback?

- Mapping sai người, ứng dụng gắn dữ liệu vào account khác;
- Cấp role đặc quyền hoặc scope dữ liệu ngoài phê duyệt;
- Leaver vẫn đăng nhập được qua đường cũ/mới;
- Mất SSO/MFA trên diện rộng ở hệ thống trọng yếu;
- Provisioning lỗi lan rộng, queue tăng không kiểm soát;
- Nguồn HRIS/contractor thiếu dữ liệu và tạo bulk revoke;
- Một writer tự ghi đè trạng thái của writer đã chuyển;
- Phát hiện quyền ngoài policy hoặc SoD violation mức nghiêm trọng.

Cần xác định **khi nào pause riêng một target/cohort, khi nào failback rộng hơn** theo playbook đã phê duyệt.

### 20.3. Runbook rollback

1. **Pause writer gây lỗi**, giữ event log, mapping/policy version, snapshot và backlog.
2. Phân loại quyền truy cập nào còn hợp lệ theo **trạng thái JML hiện hành**.
3. Xác định hệ có thẩm quyền về lifecycle, role và từng target trong phương án phục hồi.
4. Khôi phục routing/trust/connector theo thứ tự kiểm soát; không mở đồng thời hai writer tranh chấp.
5. Tính lại desired entitlement và replay delta có deduplication/order.
6. Không kích hoạt lại leaver hoặc phục hồi role đã thu hồi hợp lệ sau mốc snapshot.
7. Đối soát actual account/group/role, SSO/MFA, token/session và PAM trên cả đường cũ/mới.
8. Ghi incident, nguyên nhân, người duyệt và các thay đổi cần bổ sung trước khi thử cutover lại.

**Rollback không phải chỉ đổi DNS hay login URL về cũ.** Những thay đổi như xóa account, merge identity, revoke credential hoặc di chuyển ownership dữ liệu có thể không hoàn nguyên đầy đủ.

## 21. Case study: chuyển từ IAM-A sang IAM-B theo từng phòng ban

Một công ty giả định có **1.400 nhân viên, 120 nhà thầu, 30 ứng dụng**, dùng HRIS chính, AD/IdP-A và một số SCIM connector. Công ty muốn chuyển sang directory/IdP-B và IAM policy engine mới.

### 21.1. Khảo sát và thiết kế

Nhóm phát hiện:

- 18 ứng dụng SAML/OIDC, 8 ứng dụng nhận SCIM/API và 4 ứng dụng vẫn có LDAP/local auth;
- Một số app lưu user bằng ID nội bộ, nên phải pre-link khi đổi subject;
- 12 nhóm quyền có nested membership;
- Một ứng dụng giữ direct role không được SCIM quản lý;
- Hai bot tích hợp có API key cũ;
- Nhiều event mover/contractor expiry phát sinh mỗi ngày.

Nhóm giữ HRIS là nguồn trạng thái nhân viên và hệ quản lý nhà thầu làm nguồn hợp đồng. Canonical ID giữ nguyên; các source/account IDs cũ và mới được nối bằng bảng crosswalk có phê duyệt.

### 21.2. Shadow run

Trong giai đoạn shadow, IAM-B đọc sự kiện và tính desired role nhưng không ghi production. Bộ so sánh phát hiện:

1. Department FIN-01 ở HRIS cũ đổi thành finance ở mô hình mới: **khác định dạng nhưng cùng ngữ nghĩa**, không phải security drift.
2. Mapping nhóm Sales_HCM sang role SalesManager ở app mới làm mở dữ liệu toàn tenant: **security drift nghiêm trọng**, phải sửa role scope.
3. Một số manager reference chưa resolve: đưa vào quarantine, không đoán manager qua email.
4. Một retry mover cũ có nguy cơ cấp lại quyền đã bị thu hồi: bổ sung version/state check.

Nhóm chỉ mở pilot sau khi sửa mapping và phê duyệt các khác biệt còn lại.

### 21.3. Pilot và coexistence

Chuyển thử một phòng ban có user thường, admin được giám sát, nhà thầu và service account. Trong thời gian đó:

- IAM-A còn xử lý các cohort chưa chuyển;
- IAM-B ghi những đích/cohort đã được ủy quyền;
- Bộ policy dùng cùng desired state đã được owner quản trị;
- Cả hai hệ đều ghi audit và đọc actual access để đối soát;
- Leaver phải được xử lý trên bất kỳ IdP/ứng dụng nào vẫn còn truy cập được.

Một nhân viên chuyển từ Sales sang Finance trong pilot. IAM-B cấp Finance nhưng app cũ còn quyền xuất Sales do direct grant. Reconciliation phát hiện và chủ ứng dụng thu hồi quyền cục bộ, sau đó kiểm thử API/export thật.

### 21.4. Sự cố nguồn dữ liệu thiếu

Một batch HRIS trong ví dụ bị thiếu phần lớn hồ sơ vì lỗi xuất dữ liệu. Nếu pipeline coi mọi user vắng trong batch là leaver, hàng loạt account có thể bị disable. Guardrail phát hiện nguồn không đủ và chuyển batch sang trạng thái hold; dữ liệu nguồn được đối chiếu trước khi cho phép thao tác. Các sự kiện leaver hợp lệ, được xác minh độc lập, vẫn được xử lý theo SLA.

### 21.5. Nghiệm thu và đóng hệ cũ

Mỗi cohort chỉ đạt khi:

- Account linking và role scope đúng;
- Không có security drift nghiêm trọng đang mở;
- SSO/MFA và SCIM/API hoạt động đúng, gồm leaver revoke;
- App-local permission, token và service identity đã được rà soát;
- Có audit, mapping version, exception owner và rollback rehearsal.

Sau ổn định, tổ chức mới đóng trust/connector/credential cũ không còn cần, lưu crosswalk theo retention và ký nghiệm thu.

**Điểm rút ra:** Dual run là cách kiểm chứng có điều kiện trước khi chuyển quyền vận hành. Nó chỉ an toàn khi mỗi quyền có owner, mỗi identity có liên kết đã xác minh và mỗi đường truy cập còn hoạt động đều chịu cùng chính sách vòng đời.

## 22. Bộ kiểm thử nghiệm thu

| Mã | Tình huống | Kết quả mong đợi |
|---|---|---|
| T01 | Shadow pipeline nhận event đang xử lý ở production | Chỉ tạo output so sánh, không ghi đích |
| T02 | Hệ cũ/mới có email giống nhưng subject khác | Link đúng canonical ID, không tạo account mới |
| T03 | Hai người trùng email hoặc email tái sử dụng | Không auto-merge, có quarantine |
| T04 | HRIS đổi source ID khi di trú | Bảo toàn source crosswalk và identity continuity |
| T05 | Joiner có start date tương lai | Không cấp quyền trước mốc hợp lệ |
| T06 | Mover đổi department | Cấp mới và thu hồi quyền cũ tại các đích còn phục vụ |
| T07 | Leaver trong coexistence | Chặn IdP cũ/mới, app local, session/token theo SLA |
| T08 | Rejoiner | Xác minh lại, không tự phục hồi role cũ |
| T09 | Contractor expiry | Thu hồi theo nguồn hợp đồng có thẩm quyền |
| T10 | Partial HRIS update thiếu field trạng thái | Không tự disable user |
| T11 | Snapshot nguồn rỗng do lỗi | Chặn mass deprovision và cảnh báo |
| T12 | Sự kiện JML trùng | Idempotent, không tạo account/grant kép |
| T13 | Mover event cũ đến sau leaver | Không hồi sinh user/quyền |
| T14 | Hai writer cố cập nhật cùng group | Phát hiện, chỉ writer được phép ghi |
| T15 | Role cũ/mới cùng tên nhưng khác scope | Permission diff phát hiện và chặn cấp quá |
| T16 | Role khác tên nhưng cùng hành vi | Comparator phân loại tương đương hợp lệ |
| T17 | Nested group ở hệ cũ, đích không hỗ trợ | Effective membership chính xác và revoke đúng |
| T18 | Dynamic group thiếu department | Không gán role rộng; có xử lý ngoại lệ |
| T19 | SoD conflict xuyên app cũ/mới | Chặn hoặc xử lý theo policy/approval |
| T20 | SCIM client mới map nhầm User.id | Không cập nhật sai resource, quarantine |
| T21 | JIT và SCIM cùng có thể tạo user | Không sinh duplicate account |
| T22 | SCIM trả 2xx nhưng app role chưa đổi | Reconciliation thấy pending/drift |
| T23 | Một target SCIM lỗi, target khác thành công | Per-target status và retry/ticket |
| T24 | Group SCIM bị replace sai danh sách | Guardrail/nghiệm thu phát hiện membership mất bất thường |
| T25 | Token cũ còn group claim | Session/token được xử lý theo SLA và capability |
| T26 | App có local login không qua IdP | Leaver vẫn bị chặn ở đường local |
| T27 | App có direct admin grant | Review và thu hồi nếu hết lý do |
| T28 | Admin access qua PAM trong dual run | MFA, approval, audit và quyền tối thiểu đạt |
| T29 | Service account owner nghỉ việc | Bàn giao owner và review credential/permission |
| T30 | OAuth workload chuyển issuer/client | API access theo scope mới, credential cũ được retire |
| T31 | Một app không hỗ trợ hai IdP | Cutover riêng theo runbook và rollback được thử |
| T32 | User hợp lệ đọc record trong team | Được phép |
| T33 | Cùng user đọc record ngoài team | Bị từ chối cả UI/API |
| T34 | Group/policy changes đang pending replication | Comparator phân biệt lag với drift vượt SLA |
| T35 | Source/new pipeline có version khác | Audit ghi rõ phiên bản và quyết định |
| T36 | Cắt traffic giữa lúc có event JML | Delta replay không mất hoặc lặp thay đổi |
| T37 | Rollback sau sự kiện leaver mới | Không bật lại account đã bị thu hồi hợp lệ |
| T38 | Rollback sau mover mới | Không tự phục hồi role cũ |
| T39 | Giới hạn API/rate limit trong pilot | Retry/backoff, không bỏ qua thất bại |
| T40 | Retire IdP-A khi còn app legacy | Exit criteria chặn hoặc có ngoại lệ/owner và bảo vệ phù hợp |

Với mỗi case cần lưu **expected/actual result, cohort, system/tenant, user/account ID mô phỏng, policy/mapping version, correlation ID, thời điểm, người kiểm tra và exception**. Đặc biệt, các ca **negative authorization**, leaver và privileged access phải được xác minh tại hệ thực thi quyền.

## 23. Checklist bàn giao

### Trước dual run

- [ ] Có danh sách những tầng IAM được chuyển và owner của từng thành phần.
- [ ] Đã định nghĩa mục tiêu shadow, pilot, coexistence và exit criteria.
- [ ] Có canonical identity crosswalk old/new được xác minh.
- [ ] Có attribute/role mapping version, scope, SoD và quyền app-local.
- [ ] Có ma trận source of authority/single writer theo field/target/cohort.
- [ ] Có event ID, version/effective time, idempotency, retry, partial failure handling.
- [ ] Có baseline, nguồn đầy đủ, guardrail bulk grant/revoke và quarantine.
- [ ] Có thiết kế SSO/MFA/SCIM, session/token, PAM và service identity.
- [ ] Có comparator normalized state, audit, dashboard và reconciliation.
- [ ] Có test plan, runbook cutover/rollback, on-call và người duyệt.

### Trong dual run

- [ ] Shadow không ghi production trái quyền.
- [ ] Không có hai writer tranh chấp trạng thái cùng resource.
- [ ] Các cohort có owner và thời điểm chuyển rõ.
- [ ] Identity/account và quyền thực tế được đối soát thường xuyên.
- [ ] Joiner/Mover/Leaver, contractor và rejoiner được xử lý theo policy hiện hành.
- [ ] Drift đặc quyền, SoD và account leaver được ưu tiên.
- [ ] Exception có owner, SLA, ticket và ngày hết hạn.
- [ ] Phát hiện source lỗi, queue tồn và sự kiện sai thứ tự.
- [ ] Token, local login, legacy trust và workload không bị bỏ quên.

### Trước khi retire hệ cũ

- [ ] Đã xác nhận các ứng dụng và đường truy cập còn phụ thuộc hệ cũ.
- [ ] Đã nghiệm thu role/entitlement thực tế cùng negative tests.
- [ ] Chỉ số mapping, drift, JML latency và provisioning đạt ngưỡng được duyệt.
- [ ] Không còn quyền đặc quyền tồn dư ngoài phê duyệt.
- [ ] Rollback/failback và xử lý delta JML đã được diễn tập.
- [ ] Credential, connector, token/trust cũ có kế hoạch thu hồi rõ.
- [ ] Mapping và audit được lưu theo retention, quyền xem được giới hạn.
- [ ] Owner bảo mật, nghiệp vụ, IAM và vận hành đã xác nhận kết thúc.

## 24. Những anti-pattern thường gặp

**Cho hai pipeline cùng ghi một group/role:** các thay đổi dao động và sự kiện cũ có thể cấp lại quyền. Cần single writer theo resource/cohort và event ordering.

**Coi shadow run thành công là đủ:** shadow không chứng minh token/session hay connector đích thật. Cần pilot với actual access và failure tests.

**So chuỗi raw thay vì ngữ nghĩa quyền:** thấy khác biệt giả do đổi mã hoặc bỏ sót role cùng tên nhưng rộng hơn. Chuẩn hóa và so action/resource/scope.

**Dùng email làm khóa link:** có thể tạo duplicate hoặc chiếm nhầm account. Dùng canonical ID và crosswalk đã xác minh.

**Chỉ kiểm tra đăng nhập:** không phát hiện direct grant, quyền theo record và token cũ. Test positive/negative authorization cùng reconciliation.

**Cắt nguồn cũ ngay sau khi chuyển vài ứng dụng:** các app legacy hoặc bot còn phụ thuộc. Inventory và exit criteria phải đầy đủ.

**Gửi lệnh leaver chỉ tới một IdP:** người dùng có thể đi qua IdP/trust cũ hoặc app local. Quản lý mọi đường truy cập đang tồn tại.

**Dùng snapshot cũ khi rollback:** hồi sinh user và role đã bị thu hồi. Tính lại desired state từ JML hiện hành rồi replay delta.

**Xem bản export thiếu là lệnh mass deactivate:** gây sự cố lớn khi nguồn lỗi. Kiểm tra quality và guardrail.

**Quên workload và admin khẩn cấp:** token cũ, service principal hoặc đặc quyền không owner còn tồn tại. Quản lý registry/PAM và credential lifecycle.

**Không định nghĩa thời điểm kết thúc dual run:** hai kiến trúc kéo dài, khó kiểm toán và tăng diện tấn công. Có exit criteria, ownership và kế hoạch retire.

## 25. Câu hỏi tự kiểm tra

1. Dual run khác shadow mode và active-active dual write ở điểm nào?
2. Vì sao không nên có hai writer cùng sửa group membership tại một service provider?
3. Một nhân viên đã đổi IdP nhưng email giữ nguyên; làm sao xác minh đúng account?
4. Sự khác biệt giữa normalized policy agreement và so sánh group name là gì?
5. Nếu một app chỉ cho phép một issuer OIDC, có những hướng thiết kế cutover nào?
6. Một leaver trong coexistence cần được thu hồi quyền trên những đường truy cập nào?
7. Tại sao chặn user trong IdP không mặc nhiên kết thúc session của ứng dụng?
8. Nếu một batch HRIS rỗng, hệ thống cần phân biệt trạng thái nào trước khi deprovision?
9. Khi event mover cũ đến sau leaver, điều gì quyết định nó bị bỏ qua?
10. Vì sao cần so role theo action, resource, scope và condition?
11. Lúc nào sự khác biệt về định dạng thuộc tính chỉ là expected difference?
12. Nếu SCIM trả thành công nhưng quyền ứng dụng chưa đổi, KPI và reconciliation phản ánh ra sao?
13. Tại sao kiểm thử SoD phải xét cả quyền ở app cũ và app mới?
14. Một service account có owner nghỉ việc cần xử lý thế nào trong dual run?
15. Những bằng chứng nào đủ để phê duyệt kết thúc giai đoạn coexistence?
16. Nếu phải rollback sau một đợt mover và leaver mới, làm sao không hồi sinh quyền cũ?

**Gợi ý:** Trả lời dựa trên canonical identity, source authority, single writer, trạng thái JML mới nhất, desired/actual state, phiên/token, group/role mapping và bằng chứng kiểm toán.

## 26. Thuật ngữ và tài liệu tham khảo

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Dual run** | Giai đoạn IAM cũ/mới cùng tồn tại có kiểm soát |
| **Shadow mode** | Pipeline mới tính thử, không tác động production |
| **Coexistence** | Hệ cũ/mới phục vụ các phần workload được phân công |
| **Cutover / rollback** | Chuyển vận hành chính thức / phục hồi có kiểm soát |
| **Source of authority** | Nguồn được phép xác nhận dữ liệu hoặc quyết định |
| **Single writer** | Một bên chịu quyền ghi cuối cùng cho một phần trạng thái |
| **Canonical identity** | Danh tính chuẩn liên kết các ID ở nhiều hệ |
| **Crosswalk** | Bảng liên kết subject/account IDs cũ và mới |
| **Desired / actual state** | Trạng thái kỳ vọng theo chính sách / trạng thái thật tại đích |
| **Reconciliation / drift** | Đối soát và chênh lệch giữa hai trạng thái |
| **JML** | Joiner–Mover–Leaver: gia nhập, chuyển vai trò, rời tổ chức |
| **IdP / SSO / MFA** | Nhà cung cấp danh tính / đăng nhập một lần / xác thực nhiều yếu tố |
| **SCIM** | Chuẩn quản lý User/Group giữa client và service provider |
| **RBAC / ABAC / SoD** | Quyền theo role / thuộc tính / phân tách nhiệm vụ |
| **PAM** | Privileged Access Management, quản trị đặc quyền |
| **Idempotency** | Xử lý lặp không tạo tác động lặp ngoài dự kiến |
| **Effective time** | Mốc thay đổi có hiệu lực nghiệp vụ |
| **Watermark / event version** | Mốc và phiên bản hỗ trợ replay/đối soát |
| **Guardrail / quarantine** | Kiểm soát dừng an toàn / cách ly dữ liệu mơ hồ |

Tài liệu nền tảng để tra cứu khi triển khai:

- **RFC 7643 — SCIM Core Schema:** user/group, id, externalId, các thuộc tính và quy tắc biểu diễn.
- **RFC 7644 — SCIM Protocol:** create, update, PATCH, search và tương tác client/service provider.
- **OpenID Connect Core 1.0:** issuer, subject, ID token và xác thực liên hợp.
- **SAML 2.0 Core và Bindings (OASIS):** assertion, NameID, trust và federation.
- **NIST SP 800-53:** các nguyên tắc kiểm soát truy cập, least privilege, audit và access review.
- **Tài liệu chính thức của HRIS, directory, IdP, IAM/IGA, PAM và ứng dụng đích:** account linking, federation, SCIM group behavior, token/session revocation, backup/restore, khả năng dual trust và giới hạn thực tế. Hành vi cụ thể phụ thuộc sản phẩm và phiên bản.

**Tiêu chuẩn đánh giá cuối cùng:** Dual run IAM đạt mục đích khi người dùng tiếp tục được nhận diện chính xác, chính sách cấp và thu hồi quyền được thực thi nhất quán theo JML hiện hành, không còn quyền tồn dư không hợp lệ, các đường truy cập cũ/mới được kiểm soát và tổ chức có đủ bằng chứng để chuyển quyền vận hành hoặc phục hồi an toàn.

