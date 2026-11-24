# Mapping nhóm và role khi di trú IAM

> **Chương:** IAM migration  
> **Chủ đề:** Mapping nhóm và role  
> **Phạm vi:** Quản lý vòng đời danh tính trong Identity and Access Management (IAM) theo Joiner–Mover–Leaver (JML), từ xác minh, tạo account và cấp quyền đến rà soát và thu hồi khi thay đổi vai trò. Nội dung liên kết directory, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **group**, **role**, **permission**, **entitlement**, **claim**, **membership** và **quyền hiệu lực** khi chuyển đổi hệ thống IAM.
2. Lập inventory nhóm/role trong directory, IdP, IAM/IGA, ứng dụng và hệ thống đặc quyền; xác định owner cùng nguồn có thẩm quyền của từng quyền.
3. Xây dựng **bảng ánh xạ nhóm và role** theo ý nghĩa nghiệp vụ và phạm vi quyền, không dựa đơn thuần vào tên hiển thị.
4. Chuyển membership trực tiếp, nhóm lồng nhau, nhóm động và role theo thuộc tính mà không cấp thừa hoặc bỏ sót quyền.
5. Duy trì các hành vi Joiner–Mover–Leaver qua SSO, SCIM/API, RBAC/ABAC, quyền cấp trực tiếp và những hệ không dùng SSO.
6. Thiết kế pilot, kiểm thử quyền cho phép và bị từ chối, reconciliation, cutover, rollback và bộ chỉ số giám sát.
7. Ngăn role explosion, đặc quyền tồn dư, xung đột SoD, tài khoản dịch vụ vô chủ và thay đổi hàng loạt do nguồn dữ liệu lỗi.

**Bài toán xuyên suốt:** Doanh nghiệp chuyển từ Active Directory (AD) và một ứng dụng CRM cũ sang directory/IdP cùng CRM mới. Nhóm **GG_Sales_HCM** ở hệ cũ chứa cả nhân viên bán hàng và quản lý, còn role **SalesManager** trong CRM mới mặc định xem tất cả khách hàng trên toàn tenant. Làm sao tạo bản đồ nhóm và role bảo toàn chức năng cần thiết nhưng không biến người chỉ được xem một nhóm khách hàng thành người xem dữ liệu toàn công ty?

## 2. Hiểu đúng các lớp group, role và permission

Những thuật ngữ này thường được dùng thay nhau trong giao tiếp, nhưng khác biệt quyết định kết quả di trú.

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **Identity / principal** | Chủ thể được nhận diện và xác thực | Nhân viên, nhà thầu, service account |
| **Group** | Tập hợp principal hoặc group khác, có owner và quy tắc thành viên | Nhóm Sales-HCM trong directory |
| **Role** | Vai trò có tập quyền/chức năng định nghĩa rõ | CRM team reader, invoice approver |
| **Permission** | Một hành động được phép trên loại tài nguyên hoặc phạm vi | customer.read, invoice.approve |
| **Entitlement** | Quyền được gán thực tế cho principal hoặc account trong hệ thống | User A có role TeamReader ở tenant X |
| **Claim** | Dữ liệu trong assertion/token từ IdP cho ứng dụng | Department, group identifier, role name |
| **Membership** | Quan hệ thành viên của principal với group/role theo chính sách | Person-007 vào Sales-HCM |
| **Effective access** | Quyền thực tế sau khi áp tất cả policy, scope, điều kiện và deny | User đọc được record của team HCM, không đọc team Hà Nội |

Group có thể chỉ dùng để nhận thông báo, phân phối email hoặc phục vụ hiển thị; **không phải group nào cũng cấp quyền bảo mật**. Một nhóm bảo mật ở directory có thể được map sang role trong ứng dụng nhưng các ứng dụng khác vẫn có role cục bộ riêng.

**Role** là một khái niệm nghiệp vụ hoặc kỹ thuật có quyền cụ thể. Cùng tên “Manager” ở hai hệ thống chưa chắc có cùng quyền, cùng phạm vi tài nguyên hay cùng điều kiện quản lý.

### 2.1. Sơ đồ đường đi từ chủ thể đến quyền

~~~mermaid
flowchart LR
    SRC["HRIS / nguồn hợp đồng"] --> IAM["IAM/IGA: JML, role catalog"]
    IAM --> ID["Canonical identity"]
    ID --> G["Directory/IdP group"]
    G --> R["Ứng dụng: role binding"]
    IAM --> SCIM["SCIM/API provisioning"]
    SCIM --> R
    R --> E["Permission / entitlement"]
    E --> P["Policy theo tenant, team, record"]
    P --> ACT["Effective access"]
    IAM --> AUDIT["Reconciliation và audit"]
    ACT --> AUDIT
~~~

Luồng xác thực (SSO) và luồng cấp quyền (SCIM/API, group/role binding) có thể chạy độc lập. Người dùng đăng nhập được qua IdP mới **không chứng minh** rằng role cũ đã bị thu hồi tại ứng dụng.

## 3. Các bất biến bảo mật cần giữ trong quá trình mapping

Trước khi thay group hoặc role, thống nhất những điều kiện không được vi phạm:

| Bất biến | Cách chứng minh |
|---|---|
| **Cùng chủ thể phải giữ liên kết ổn định** | Old/new account cùng canonical identity đã xác minh |
| **Quyền không được rộng hơn chính sách** | So sánh effective permissions, không so tên role |
| **Mọi grant có lý do và owner hợp lệ** | Entitlement catalog, approval, expiry và audit |
| **Mover không giữ role đã hết hiệu lực** | Test grant mới **và** revoke role cũ, gồm direct grant |
| **Leaver mất quyền ở mọi hệ đích đúng SLA** | Test IdP, SCIM, app-local account, token và phiên |
| **SoD không bị phá vỡ sau khi hợp nhất role** | Kiểm tra tổ hợp quyền xung đột theo ngữ nghĩa |
| **Nhóm đặc quyền phải được giám sát riêng** | Owner, approval, MFA/PAM và access review |
| **Không mất khả năng truy vết** | Mapping version, chính sách, event, actor, approver, before/after |
| **Nguồn lỗi không gây bulk grant/revoke sai** | Guardrail, dry-run, quarantine và pause writer |

Một số quyền có thể được thiết kế thay đổi sau di trú do yêu cầu nghiệp vụ, nhưng **mọi thay đổi phạm vi phải được phê duyệt** và kiểm thử với tài nguyên thật. Không gọi chênh lệch đó là “tương đương” nếu role mới cho phép nhiều hơn.

## 4. Khảo sát hiện trạng: từ membership đến quyền hiệu lực

### 4.1. Lập inventory cho từng group và role

Mỗi nhóm/role cần hồ sơ tối thiểu:

- ID bất biến hoặc ID trong phạm vi hệ thống; tên, namespace, tenant, directory/ứng dụng sở hữu.
- Loại: security group, distribution group, dynamic group, nested group, application-local group, privileged group.
- Owner nghiệp vụ, owner kỹ thuật, approver và nguồn có thẩm quyền về membership.
- Mục đích, tập đối tượng hợp lệ, điều kiện gia nhập/rời nhóm và thời hạn.
- Quan hệ nhóm con/nhóm cha, người dùng trực tiếp, thành viên được suy ra và các ngoại lệ.
- Role/permission đích mà group đang cấp; tài nguyên, action và scope thực tế.
- Đường cập nhật: HRIS→IAM, IAM→directory, IdP claims, SCIM Group, API app hoặc admin thủ công.
- Số thành viên, mức nhạy cảm, quyền đặc quyền và lịch sử rà soát.
- Đường thu hồi: remove group, revoke role trực tiếp, deactivate account, token/session, PAM.

Ví dụ inventory:

| Đối tượng nguồn | Loại | Ý nghĩa thực tế | Rủi ro |
|---|---|---|---|
| GG_Sales_HCM | Security group AD | Nhân viên team HCM đọc dữ liệu khách hàng thuộc team | App mới map sang role xem toàn tenant |
| GG_CRM_Export | Security group | Xuất báo cáo tổng hợp | Role đích có khả năng xuất toàn bộ PII |
| GG_Finance_Approver | Group nghiệp vụ | Duyệt thanh toán trong ngưỡng | Xung đột SoD với người tạo thanh toán |
| DL_AllStaff | Distribution list | Nhận email thông báo | Nhầm thành nhóm cấp quyền |
| CRM_Local_Admin | Role cục bộ | Quản trị tenant CRM cũ | Không tồn tại trong export IdP |
| PAM_DB_Admin | Nhóm đặc quyền | Quản trị CSDL theo phiên phê duyệt | Di trú thiếu cơ chế PAM/MFA |
| BOT_Integration | Service principal | Gọi API đồng bộ khách hàng | Không có owner hoặc secret quản lý |

### 4.2. Kiểm kê cả nguồn quyền trực tiếp

Một thành viên có thể nhận quyền không qua directory group:

- Role cấp trực tiếp ở ứng dụng;
- Quyền chia sẻ theo record/project;
- Quyền admin được gán thủ công hoặc qua PAM;
- ACL filesystem, database grant và cloud resource policy;
- OAuth delegated consent, personal access token hoặc API key;
- Quyền khách/partner theo hợp đồng;
- Quyền tạm thời có ticket hoặc ngoại lệ chưa hết hạn.

Nếu chỉ export group từ AD, dự án có thể bỏ sót toàn bộ các quyền này. Cần **đối soát actual access tại đích** và xác định phương án xử lý quyền nằm ngoài phạm vi tự động hóa.

### 4.3. Lấy baseline và xác định độ tin cậy

Lưu snapshot có kiểm soát của group catalog, membership trực tiếp/gián tiếp, role binding, app entitlement, SoD violation, account active/inactive và audit. Thống kê số nhóm không owner, nhóm không còn dùng, quyền cục bộ và những thuộc tính bị thiếu.

**Baseline** phân biệt drift đã có trước migration với lỗi mới xuất hiện. Snapshot nên gắn source timestamp/version và có bảo vệ dữ liệu; không cần thu thập password, secret hoặc raw access token.

## 5. Identity continuity: khóa nhóm và chủ thể có phạm vi riêng

### 5.1. Không coi group name là định danh bền vững

Nhóm có thể bị đổi tên, chuyển OU, chuyển tenant, thay object ID hoặc được tạo lại. Hai nhóm cùng tên ở hai tổ chức có thể có quyền khác nhau.

| ID / thuộc tính | Phạm vi và cách dùng | Lưu ý |
|---|---|---|
| **Canonical person ID** | Chủ thể thực trong identity registry | Bền vững, không phụ thuộc email |
| **Directory object ID/GUID** | User/group trong directory cụ thể | Đổi khi tạo object trong tenant khác |
| **AD SID** | Định danh bảo mật trong Windows | ACL có thể tham chiếu SID cũ; không bằng group name |
| **Group DN** | Đường dẫn LDAP của group | Có thể đổi khi chuyển OU |
| **IdP group ID** | Group trong tenant IdP | Claim có thể mang ID hoặc tên tùy cấu hình |
| **SCIM Group id** | Resource group tại ứng dụng đích | Phải dùng ID từ chính service provider đó |
| **App role ID** | Vai trò tại ứng dụng/tenant | Có thể đổi khi chuyển sản phẩm hoặc tenant |
| **Display name** | Nhãn hiển thị cho người vận hành | Dễ trùng/đổi, không làm khóa tự động duy nhất |
| **OIDC issuer + sub** | Định danh user trong liên hợp OIDC | Không dùng email thay thế subject khi link |

Duy trì **crosswalk** nhóm và tài khoản theo cấu trúc: source system + tenant + source group ID → target system + tenant + target group/role ID, cùng canonical person ID cho các thành viên đã xác minh.

### 5.2. Mapping cần phạm vi tenant và loại account

Một người có thể có account thông thường, account admin riêng, guest trong tenant đối tác và service identity phụ trách job. Không tự hợp nhất mọi account về một account đích chỉ vì cùng email.

Một group ở tenant A có thể cùng tên với group ở tenant B nhưng khác owner và quyền. **Namespace của hệ nguồn** là một phần bắt buộc của khóa mapping; **type** và **scope** ngăn nhầm group thông báo thành group bảo mật.

### 5.3. Ví dụ crosswalk minh họa

~~~yaml
mappingVersion: 4
source:
  system: old-ad
  tenant: corp-vn
  groupId: old-guid-1001
  displayName: GG_Sales_HCM
  groupType: security
target:
  application: crm-cloud
  tenant: corp-vn
  roles:
    - roleId: team-reader
      scope:
        kind: team
        value: hcm
ownership:
  businessOwner: sales-ops-owner
  securityApprover: iam-role-owner
mappingStatus: verified
evidenceRef: entitlement-review-2026-q4
~~~

Đây là **hợp đồng minh họa** cho bài học, không phải cú pháp tiêu chuẩn của SCIM hay một IdP. Điểm cốt lõi là phải ánh xạ **cả role lẫn scope**, có thể tra cứu nguồn gốc, owner, phê duyệt và phiên bản.

## 6. Xác định nguồn có thẩm quyền của membership và role

Không có một hệ duy nhất luôn sở hữu toàn bộ quyền.

| Thuộc tính/quyết định | Nguồn có thẩm quyền điển hình | Ai ghi tới đích? |
|---|---|---|
| Người đang làm việc, phòng ban, quản lý | HRIS/nguồn nhân sự | IAM/IGA điều phối |
| Nhà thầu còn hợp đồng, sponsor | Vendor/contractor management | IAM/IGA hoặc connector được chỉ định |
| Canonical identity và liên kết account | Identity registry | Bộ máy account linking được phê duyệt |
| Business role theo vị trí | IAM/IGA + owner nghiệp vụ | Entitlement/provisioning engine |
| Role theo ticket phê duyệt | Workflow IGA hoặc owner ứng dụng | Connector hoặc admin được ủy quyền |
| Dynamic group dựa trên thuộc tính | Policy engine hoặc IdP theo thiết kế | Group engine có thẩm quyền |
| Role cục bộ đặc thù | Chủ ứng dụng theo hợp đồng | Ứng dụng hoặc IAM, một writer rõ |
| Privileged role | PAM/IAM + security approver | PAM/workflow được quản trị |
| Quyền service identity | Service owner/workload registry | Workload platform/connector |

**Single writer** phải được xác định theo từng entitlement và giai đoạn. Nếu IdP group và app-local role đều có thể cấp quyền tương tự, cần quyết định ai có thẩm quyền cuối cùng và có đồng bộ thu hồi hay không.

### 6.1. Tách membership có thẩm quyền với membership quan sát được

Một nhân viên thuộc team Sales vì HR xác nhận và IAM policy tính ra điều đó. Việc directory đang có một membership cũ không tự chứng minh người đó tiếp tục đủ điều kiện. Trong migration:

1. Đọc **desired membership** từ nguồn/chính sách có thẩm quyền.
2. So với **actual membership** trong directory/IdP/app.
3. Giải thích ngoại lệ đã phê duyệt.
4. Cập nhật theo thời gian hiệu lực và rule version.
5. Thu hồi membership không còn lý do, kể cả entitlement app-local liên quan.

## 7. Ánh xạ group → role theo ngữ nghĩa

### 7.1. Năm kiểu ánh xạ phổ biến

| Kiểu mapping | Tình huống | Cách quản trị |
|---|---|---|
| **1 group → 1 role** | Nhóm FinanceReader cũ và role đích cùng quyền, scope | Xác minh hành vi, owner và negative test |
| **1 group → nhiều role** | Group cũ gộp read, edit, export; đích chia nhỏ | Chỉ cấp các role có lý do, không copy cả bộ mặc định |
| **Nhiều group → 1 role** | Hai nhóm cũ đại diện một chức năng nghiệp vụ | Kiểm tra việc hợp nhất có vô tình tăng scope hay không |
| **Group → role + thuộc tính scope** | Sales_HCM → TeamReader chỉ team HCM | Bắt buộc kiểm thử record-level/tenant-level |
| **Không mapping** | Nhóm email, nhóm không owner, role lỗi thời | Chỉ bỏ sau đánh giá phụ thuộc, theo dõi ngoại lệ |

Mapping còn có thể là **đổi từ role sang ABAC**, hoặc **role cũ được thay bằng quyền khác** có phê duyệt. Không coi mọi ánh xạ là một phép đổi tên.

### 7.2. Ma trận ví dụ

Giả sử CRM cũ có ba nhóm:

| Group nguồn | Quyền thực tế cũ | Đích đề xuất | Bài kiểm tra bắt buộc |
|---|---|---|---|
| GG_Sales_HCM | Đọc/sửa khách hàng thuộc team HCM | TeamReader + TeamEditor, scope=HCM | Không đọc/sửa khách hàng của team khác |
| GG_Sales_Export | Xuất báo cáo của team được giao | ExportTeamData, scope=team | Không export dữ liệu toàn tenant |
| GG_Fin_Approver | Duyệt thanh toán tối đa theo ngưỡng | FinanceApprover với limit từ policy | Không tự duyệt chứng từ do mình tạo |
| GG_CRM_Admin | Quản lý cấu hình CRM cũ | Các admin role tối thiểu, phê duyệt lại | Không mặc định cấp global admin |
| DL_Company_News | Danh sách nhận thông báo | Không map thành entitlement | Không phát sinh quyền app |

Mỗi dòng cần có owner, approver, reference tài liệu quyền cũ, mapping version, phương án rollback và tình trạng xác minh. Các quyền không có tương đương phải đưa vào review.

### 7.3. Cách đánh giá tính tương đương

Không so “role name cũ = role name mới”. Hãy so theo bộ ba:

**(action, resource, scope)** và các điều kiện như MFA, thời gian hiệu lực, SoD, tenant, ownership hoặc classification.

Ví dụ:

- Cũ: **customer.read** trên các record của team HCM.
- Mới: **customer.read** trên toàn tenant.
- Kết luận: **không tương đương**, dù tên role đều là SalesReader.

Có thể lập **permission diff**:

| Hành vi | Cũ cho phép | Mới dự kiến | Quyết định |
|---|---|---|---|
| Đọc khách HCM | Có | Có | Giữ |
| Sửa khách HCM | Có | Có | Giữ khi đúng role |
| Đọc khách Hà Nội | Không | Có | Sai: phải giới hạn scope |
| Export dữ liệu toàn tenant | Không | Có | Sai: không cấp |
| Quản trị cấu hình | Không | Không | Giữ từ chối |

**Negative authorization** quan trọng ngang với kiểm thử thành công. Nếu chỉ đăng nhập và mở được vài record hợp lệ, có thể bỏ sót privilege escalation.

## 8. Nhóm lồng nhau, nhóm động và group ownership

### 8.1. Membership trực tiếp và gián tiếp

Ví dụ:

~~~text
user: person-0142
  memberOf: GG_Sales_HCM
GG_Sales_HCM
  memberOf: GG_CRM_Readers
GG_CRM_Readers
  grants: crm.team.read
~~~

Người dùng có thể không xuất hiện trực tiếp trong **GG_CRM_Readers** nhưng vẫn có quyền do nhóm lồng. Một số ứng dụng, IdP hoặc SCIM connector **không hỗ trợ nested membership theo cách giống AD**.

Khi chuyển:

1. Thu thập cạnh thành viên **user → group** và **group → parent group**.
2. Phân loại cạnh có thẩm quyền và ngoại lệ.
3. Phát hiện group cycle, depth quá lớn, group rỗng hoặc group ngoài tenant.
4. Tính **effective membership** theo chính sách đích; không giả định target tự mở rộng nhóm lồng.
5. Nếu cần flatten, chỉ tạo membership trực tiếp từ nguồn đáng tin, ghi lý do và phiên bản.
6. Khi membership nguồn bị gỡ, tính lại effective membership để thu hồi đúng quyền, tránh bỏ sót quyền từ đường đi khác.

**Chu trình nhóm:** A chứa B và B chứa A không được làm thuật toán duyệt vô hạn; cần kiểm tra visited set và xử lý theo chính sách.

### 8.2. Nhóm động

Dynamic group có thể dựa trên biểu thức như **department=finance** và **employmentType=employee**. Di trú phải chuyển cả:

- Quy tắc đánh giá và bảng mã thuộc tính;
- Nguồn có thẩm quyền, thời điểm hiệu lực và độ trễ tính membership;
- Tập các exclusion được duyệt;
- Quy tắc xử lý null, unknown hoặc thuộc tính chưa đồng bộ;
- Khả năng sản phẩm đích có cùng toán tử/semantics hay không.

Nếu IdP mới tính group theo rule khác, cùng một nhân viên có thể được thêm/gỡ quyền sai. So kết quả từ tập người dùng đại diện và dữ liệu test lỗi trước khi dùng chính thức.

### 8.3. Không trộn group dành cho thông báo với group bảo mật

Distribution list và nhóm cộng tác có thể phục vụ email hoặc trò chuyện, không có ý nghĩa quyền truy cập. Việc “nhập tất cả group” rồi gán application role theo pattern tên sẽ có nguy cơ cấp quyền ngoài chính sách. Cần danh mục loại group, owner và mapping trạng thái **không cấp quyền** cho những group không liên quan.

## 9. Xung đột SoD và các role đặc quyền

### 9.1. Kiểm tra SoD theo quyền thực tế

**Separation of Duties (SoD)** ngăn một chủ thể đồng thời sở hữu những quyền có thể tạo xung đột nghiệp vụ, ví dụ:

- Tạo nhà cung cấp và duyệt thanh toán cho cùng nhà cung cấp;
- Tạo yêu cầu chi và phê duyệt cuối cùng;
- Quản trị tài khoản và tự phê duyệt quyền quản trị của chính mình.

Nếu hệ cũ có role **Requester** và **Approver** tách riêng, nhưng role đích **FinanceManager** gộp cả hai, mapping 2→1 có thể phá SoD dù nhìn chung số role ít đi.

Đánh giá **effective action set** sau khi mở rộng role, group lồng và quyền direct grant; thử role combination trước khi áp dụng.

### 9.2. Privileged Access Management (PAM)

Nhóm như Domain Admins, Cloud Owner, Security Admin, Database Admin, CI/CD Admin cần quy trình riêng:

- Inventory tài khoản privileged, service principal, break-glass và owner;
- Tái phê duyệt quyền nhạy cảm, ưu tiên **just-in-time/just-enough privilege** khi hệ thống hỗ trợ;
- MFA phù hợp, phê duyệt độc lập, giám sát phiên và secret rotation;
- Không tự map role “Admin” cũ sang admin toàn tổ chức;
- Có kế hoạch disable trust/credential cũ sau cutover;
- Kiểm thử cả phiên, token hoặc key cấp trước thời điểm thu hồi.

Đặc quyền tạm thời được cấp để migration cần **expiry, owner, ticket và access review sau go-live**.

## 10. SSO, OIDC/SAML và role/group claim

### 10.1. Xác thực không tự bảo đảm phân quyền

IdP có thể xác thực principal và đưa claim về nhóm/role. Ứng dụng quyết định cách nhận diện user và cấp quyền thực tế. Tùy sản phẩm, claim có thể gồm:

- Group display name;
- Group object ID;
- Role name/ID;
- Department, tenant, team hoặc các thuộc tính dùng cho ABAC.

**OIDC không chuẩn hóa một group claim dùng chung cho mọi IdP.** Các nhà cung cấp có cơ chế claim, giới hạn số lượng group và xử lý group overage khác nhau. SAML Attribute Statement cũng phụ thuộc metadata/contract của mỗi SP.

### 10.2. Điểm cần kiểm tra khi đổi IdP

| Thành phần | Câu hỏi kiểm thử |
|---|---|
| **OIDC issuer + sub** | Ứng dụng có link đúng user hay tạo account khác vì issuer/sub thay? |
| **SAML issuer/NameID** | SP nhận đúng principal sau khi đổi trust/NameID format? |
| **Group claim ID/name** | Ứng dụng match theo ID hay chuỗi, có case sensitivity không? |
| **Nested membership** | IdP/app có expand hay chỉ xét direct group? |
| **Group overage** | Khi quá nhiều nhóm, app có xử lý cơ chế fallback được hỗ trợ? |
| **Token lifetime/cache** | Gỡ group có làm mất quyền đúng thời hạn hay token cũ còn hợp lệ? |
| **Role/tenant scope** | Claim có mang đủ ngữ cảnh để quyết định quyền? |
| **MFA/conditional access** | Quyền nhạy cảm còn có bước xác thực cần thiết? |

**Không** biến ID token hoặc access token của một hệ thành bằng chứng cho quyền ở hệ khác nếu chưa xác minh issuer, audience, chữ ký, hạn dùng và policy. Token có thể đã được phát trước khi role bị thu hồi; revoke session/refresh token hoặc thời hạn hiệu lực phải được xử lý theo khả năng nền tảng.

## 11. Mapping group và role qua SCIM/API provisioning

### 11.1. SCIM quản lý resource gì?

SCIM 2.0 chuẩn hóa User, Group và các thao tác quản lý resource giữa client và service provider, nhưng mỗi provider có khả năng thực thi riêng.

- **User.id** và **Group.id**: ID do service provider đích cấp;
- **externalId**: giá trị phía client quản lý để liên kết resource, không mặc định là ID toàn cục;
- **Group.members**: danh sách resource thành viên, trong đó value tham chiếu resource ID ở **SP đích**;
- **Group.displayName**: nhãn có thể đổi hoặc trùng theo ngữ cảnh, không nên dùng làm khóa ghép duy nhất;
- **User.groups**: tùy schema/capability, thường phản ánh membership và có tính read-only; không giả định có thể sửa user.groups để thay membership;
- **active**: trạng thái user tại SP; disable user không tự bảo đảm toàn bộ token hoặc direct role đã bị thu hồi.

Không coi Group.id của AD/IdP cũ bằng Group.id của SCIM provider mới.

### 11.2. Ví dụ Group resource minh họa

~~~json
{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
  "displayName": "CRM-Team-HCM-Readers",
  "externalId": "iam-group-sales-hcm-reader",
  "members": [
    {
      "value": "target-user-1042",
      "type": "User"
    },
    {
      "value": "target-user-2058",
      "type": "User"
    }
  ]
}
~~~

Ví dụ sử dụng ID giả. **members.value** phải là target resource ID thực tế được SP công nhận. Không copy old AD SID, user email hoặc canonical person ID vào đó nếu SP mong đợi SCIM User.id.

### 11.3. PATCH membership có kiểm soát

Ví dụ thao tác thêm một user vào group đích qua SCIM PATCH:

~~~json
{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "add",
      "path": "members",
      "value": [
        {
          "value": "target-user-3117",
          "type": "User"
        }
      ]
    }
  ]
}
~~~

Đây là payload minh họa; cần xác minh Group.id target, URI, authorization và cách provider xử lý lỗi/trùng. Với **remove**, cần chỉ rõ phần tử cần gỡ theo cú pháp PATCH được provider hỗ trợ; tránh **replace toàn bộ members** khi chỉ muốn gỡ một người.

### 11.4. Các giới hạn phải thử

- Support Group CRUD, PATCH và lọc thành viên có đúng như tài liệu provider?
- Có hỗ trợ group lồng nhau hoặc dynamic group không?
- Khi User bị disable, membership và direct role có tự mất hiệu lực không?
- Ứng dụng map Group thành role bằng ID hay tên? Có quy tắc tenant không?
- API rate limit, retry/backoff, ETag/version và eventual consistency xử lý ra sao?
- Khi SCIM client thay đổi, có thể **link resource đã tồn tại** thay vì tạo duplicate không?
- Một lệnh thành công có thật sự thay đổi quyền trong app hay cần chờ/đối soát thêm?

SCIM Group membership là một phần của provisioning. **App-local role, direct grant, delegated permission và credential** thường cần API hoặc quy trình riêng.

## 12. RBAC, ABAC và tính quyền theo ngữ cảnh

### 12.1. RBAC không thay thế tất cả ràng buộc dữ liệu

RBAC cho biết role nào chứa các permission. Tuy nhiên, nhiều quyền phụ thuộc scope:

- Team HCM chỉ đọc record HCM;
- Manager đọc dữ liệu của direct reports;
- Nhà thầu chỉ truy cập project còn hợp đồng;
- Nhân viên chỉ xuất dữ liệu đã được phân loại phù hợp;
- Quyền nhạy cảm chỉ dùng trong thời gian đã được phê duyệt.

**ABAC** dùng thuộc tính chủ thể, tài nguyên và ngữ cảnh để quyết định quyền. Khi chuyển role catalog, cần chuyển cả rule sử dụng các thuộc tính như department, cost center, employmentType, location, manager hoặc ownership.

### 12.2. Policy minh họa

~~~text
allow customer.read when:
    person.lifecycleState == ACTIVE
    AND person.businessRole includes SALES_READER
    AND person.teamId == resource.ownerTeamId
    AND person.tenantId == resource.tenantId

allow customer.export when:
    person.lifecycleState == ACTIVE
    AND person.businessRole includes SALES_EXPORT_APPROVED
    AND approval.isValidAt(now)
    AND resource.classification <= approval.allowedClassification
~~~

Đây là mã giả, không phải cú pháp của một authorization engine. Phải kiểm tra hành vi thực tế của app/gateway và dùng dữ liệu test phù hợp.

### 12.3. Mapping giá trị thuộc tính trước khi dùng policy

Nếu HRIS cũ dùng **FIN-01** còn nguồn mới dùng **Finance**, việc map group theo giá trị chuỗi thô có thể làm mất hoặc cấp sai quyền. Mapping thuộc tính cần chuẩn hóa **có thẩm quyền**, rồi IAM mới tính policy.

Các giá trị **unknown, null, missing, inactive** không được gom thành một default role mạnh. Với thuộc tính chưa đáng tin, đưa quyết định cấp quyền phụ thuộc thuộc tính đó vào hàng đợi xử lý có kiểm soát. Với sự kiện leaver hợp lệ, vẫn phải ưu tiên thu hồi theo policy.

## 13. Joiner–Mover–Leaver trong mapping group/role

### 13.1. Joiner

Khi một nhân viên mới gia nhập:

1. Identity source xác nhận trạng thái và effective date.
2. IAM xác minh canonical identity và account đã tồn tại để tránh duplicate.
3. Chính sách xác định business role ban đầu từ department, job function, manager, contract.
4. Mapping role tạo group membership hoặc entitlement trong ứng dụng đích.
5. IdP/SSO, MFA, SCIM/API được cấu hình theo quyền tối thiểu.
6. Account/quyền nhạy cảm chỉ có hiệu lực theo thời điểm và approval.
7. Reconciliation chứng minh đúng account, đúng role và không có quyền vượt phạm vi.

Chuẩn bị account trước ngày bắt đầu không đồng nghĩa được phép kích hoạt toàn bộ quyền ngay.

### 13.2. Mover

Khi chuyển vai trò, **thao tác thu hồi ít nhất quan trọng ngang thao tác cấp mới**.

Ví dụ nhân viên Minh đổi từ Sales-HCM sang Procurement:

- Gỡ khỏi Sales group theo chính sách;
- Thu hồi TeamEditor, SalesExport và direct grant đã hết lý do;
- Cấp role Procurement mới sau kiểm tra SoD và approval;
- Áp chính sách bàn giao có thời hạn nếu thực sự cần overlap;
- Xác minh token/session/cache và mọi ứng dụng có quyền cục bộ;
- Ghi audit effective time, role before/after và owner duyệt.

**Sai lầm:** Chỉ thêm nhóm Procurement vào IdP mà bỏ qua nhóm Sales cũ và quyền CRM app-local. Sau vài lần đổi bộ phận, user tích lũy quyền ngày càng rộng (**access creep**).

### 13.3. Leaver

Khi nguồn có thẩm quyền xác nhận người nghỉ việc:

- Vô hiệu hóa các đường đăng nhập tương ứng;
- Gỡ/thu hồi group, app role, delegated permission và privileged access;
- Thu hồi API token, refresh token, SSH key hoặc session theo khả năng hệ thống;
- Xử lý owner của tài nguyên và service account do người đó quản lý;
- Đối soát actual state ở directory, IdP, SCIM, PAM và ứng dụng không dùng SSO;
- Đo latency thu hồi theo SLA.

**Không** xem một user biến mất khỏi batch export là bằng chứng leaver. Nếu export rỗng do lỗi kết nối, tự xóa group hàng loạt có thể gây sự cố quy mô lớn.

### 13.4. Rejoiner, nhà thầu, nghỉ tạm thời

| Trạng thái | Nguyên tắc |
|---|---|
| **Rejoiner** | Xác minh lại chủ thể; tính quyền từ trạng thái hiện hành, không tự phục hồi role cũ |
| **Contractor expiry** | Nguồn hợp đồng/đối tác có thẩm quyền quyết định thời hạn quyền |
| **Leave of absence** | Áp policy tạm khóa/hạn chế phù hợp, không đánh đồng với leaver vĩnh viễn |
| **Guest/partner** | Role gắn sponsor, tenant và expiry; cần rà soát định kỳ |
| **Owner service account rời tổ chức** | Bàn giao owner, đánh giá scope/secret trước khi tiếp tục workload |

## 14. Tài khoản phi con người và quyền machine-to-machine

Các workload như bot, CI/CD agent, job đồng bộ, service account và ứng dụng OAuth client credentials thường không có record HRIS trực tiếp.

Cần một **registry non-human identity** ghi:

- Workload/principal ID, hệ thống/tenant, mục đích sử dụng;
- Owner chịu trách nhiệm, backup owner và bộ phận;
- Nhóm/role/API scope/permission được cấp;
- Credential, certificate hoặc federated workload trust được quản lý ở đâu;
- Thời hạn, lịch access review, rotate/revoke, last-used và audit;
- Phụ thuộc sản xuất và kế hoạch bàn giao khi owner rời tổ chức.

Mapping nhóm máy sang role mới phải theo **quyền tối thiểu thực sự cần cho job**. Không tự đưa mọi service account vào Global Admin chỉ để phục hồi nhanh các tích hợp. Khi user owner nghỉ việc, quản lý **ownership lifecycle** độc lập với trạng thái account của workload; tránh xóa nhầm job quan trọng nhưng cũng không chấp nhận bot vô chủ.

## 15. Thiết kế mapping contract có version

Bảng mapping nên được quản lý như một **hợp đồng dữ liệu và authorization**, có thể đọc, review, test và audit.

| Trường | Vai trò |
|---|---|
| mappingId/version | Định danh phiên bản mapping |
| sourceSystem/sourceTenant/sourceGroupId | Group nguồn trong namespace chính xác |
| sourceGroupType | Security, distribution, dynamic, privileged, application-local |
| sourceEffectivePermission | Hành động/phạm vi đã được xác minh |
| targetSystem/targetTenant | Ứng dụng hoặc directory đích |
| targetGroupIds/targetRoleIds | ID resource/role cần gán |
| targetScope | Team, project, tenant, resource hoặc thuộc tính ABAC |
| matchingRequirements | Quy tắc identity/link và loại account |
| membershipRule | Direct, nested expansion, dynamic evaluation, exception |
| SoD/riskTier | Xung đột và mức nhạy cảm |
| authority/writer | Nguồn có thẩm quyền và connector thực hiện |
| effectiveDate/expiry | Thời gian quyền có hiệu lực và hết hiệu lực |
| owner/approver/evidence | Trách nhiệm và bằng chứng tương đương |
| validation/failureAction | Kiểm thử, hold, quarantine, reject |
| audit/reconciliation | Cách xác minh sau provisioning |

### 15.1. Ví dụ hợp đồng YAML

~~~yaml
mappingId: sales-hcm-to-crm-v2
version: 2
source:
  system: old-ad
  tenant: corp-vn
  groupId: old-guid-1001
  groupType: security
  membershipMode: direct-and-nested
target:
  system: crm-cloud
  tenant: corp-vn
  groupExternalId: iam-sales-hcm
  roles:
    - id: team-reader
      scope:
        teamId: HCM
    - id: team-editor
      scope:
        teamId: HCM
authority:
  membership: iam-policy-engine
  roleApproval: sales-business-owner
  provisioningWriter: iam-scim-connector
validation:
  checkEffectivePermission: true
  checkSoD: true
  unknownAccountAction: quarantine
  bulkChangeAction: hold-for-review
governance:
  ownerRole: sales-ops
  securityApproverRole: iam-role-owner
  evidenceRef: role-review-2026-11
~~~

Mẫu là **DSL minh họa**, không phải định nghĩa YAML chuẩn của AD/IdP/SCIM. Khi triển khai, cần quy định schema thật, logic xử lý lỗi và phương pháp kiểm thử.

### 15.2. Phân biệt các phiên bản

- **Identity crosswalk version:** người/account cũ và mới được liên kết ra sao.
- **Group catalog version:** group ID, type, owner và ngữ nghĩa.
- **Role mapping version:** group nguồn nào → role đích nào, scope nào.
- **Attribute rule version:** cách tính dynamic membership.
- **Policy version:** điều kiện RBAC/ABAC/SoD có hiệu lực.
- **Source event version:** trạng thái JML nào là mới nhất.

Audit phải chỉ ra một grant phát sinh từ mapping và policy version nào; tránh không truy lại được nguyên nhân quyền sau khi rule thay đổi.

## 16. Kiến trúc coexistence và cơ chế đồng bộ

Trong thời gian chuyển đổi, directory/IdP và ứng dụng cũ/mới có thể cùng tồn tại. Cần xác định rõ hệ nào được **đọc**, hệ nào được **ghi**, hệ nào có **thẩm quyền quyết định quyền**.

| Giai đoạn | Nguồn quyết định role | Đường ghi | Điều cần kiểm soát |
|---|---|---|---|
| Trước cutover | IAM/IGA/owner hiện tại | Connector cũ | Snapshot và drift baseline |
| Shadow/dry-run | IAM/IGA hiện tại; mapping mới chỉ tính thử | Production writer cũ | Không tạo quyền mới từ thử nghiệm |
| Pilot/cohort | IAM/IGA theo policy được duyệt | Writer được chỉ định từng đích/cohort | Không đồng bộ vòng lặp, không bỏ quên leaver |
| Cutover | IAM/IGA với mapping/role version chốt | Writer mới theo cohort | Delta event, idempotency, guardrail |
| Ổn định | IAM/IGA và application owner | Writer đích | Reconciliation và review |
| Retire | Hệ đích đã nghiệm thu | Đóng writer/trust/credential cũ | Không còn đường cấp quyền tồn dư |

### 16.1. Ngăn vòng lặp group synchronization

Ví dụ:

- Connector A ghi nhóm Sales mới từ IAM vào IdP-B.
- Connector B đọc lại nhóm Sales cũ từ IdP-A và ghi đè membership trên IdP-B.
- A nhìn thấy drift và ghi lại.
- B tiếp tục đồng bộ cũ, tạo dao động và dễ cấp lại quyền đã thu hồi.

Giải pháp: chỉ định source of authority và writer, tách chiều đồng bộ, gắn event/version và **không dùng last-write-wins theo thời gian đến** một cách mù quáng.

### 16.2. Event cũ không được mở lại role đã thu hồi

~~~text
09:00  Minh có role Sales
09:10  Sự kiện Mover sang Procurement có hiệu lực
09:12  IAM thu hồi Sales, cấp Procurement
09:15  Sự kiện retry cũ "add Sales" đến muộn
09:16  Nếu chỉ chạy thao tác đến sau cùng: Sales được cấp lại (SAI)
~~~

Cần dùng version/sequence, effective time, idempotency và kiểm tra desired state **hiện hành**, đặc biệt khi có leaver. Đồng thời phải xử lý event bị sửa hồi tố theo quy tắc nguồn có thẩm quyền.

## 17. Bộ máy tính effective membership và entitlement

### 17.1. Nguyên tắc xử lý an toàn

1. Nhận source event từ nguồn được xác thực.
2. Resolve canonical identity và account ID đích có bằng chứng.
3. Kiểm tra trạng thái JML, phiên bản event, hợp đồng nguồn có thẩm quyền.
4. Tính membership dựa trên group trực tiếp, lồng nhau và động; giới hạn/cô lập dữ liệu lỗi.
5. Map group → role/entitlement theo mapping version và ngữ nghĩa quyền.
6. Áp ABAC, scope, policy exception và SoD.
7. Tính **desired entitlements**; so với actual state.
8. Phát lệnh create/update/grant/revoke qua writer được phép, có idempotency.
9. Đọc lại quyền thực tế; log kết quả, cảnh báo drift và xử lý thất bại từng phần.

### 17.2. Mã giả minh họa

~~~text
onIdentityOrMembershipEvent(event):
    requireTrustedSource(event)

    if alreadyProcessed(event.eventId):
        return NO_OP

    person = resolveVerifiedCanonicalIdentity(event)
    if person is ambiguous:
        quarantine(event)
        return REVIEW_REQUIRED

    if isStale(event, currentAcceptedVersion(person)):
        return STALE

    membership = calculateEffectiveMembership(
        person, directGroups, nestedGraph, dynamicRules
    )

    desired = evaluateCurrentAccessPolicy(
        person, membership, roleMappingVersion,
        approvedExceptions, effectiveTime
    )

    if hasSoDConflict(desired) or hasUnapprovedPrivilege(desired):
        holdForReview(person, desired)
        return HOLD

    if unexpectedMassGrantOrRevoke(desired):
        holdBulkChangeForApproval(event)
        return HOLD

    applyIdempotentlyUsingAuthorizedWriter(person, desired)
    reconcileActualAccessAndSessions(person)
    audit(event, person, roleMappingVersion, desired)
~~~

Mã trên chỉ là **pseudocode**. Hệ production phải có kiểm tra source signature, kiểm soát cạnh tranh, hàng đợi, retry/backoff, bù trừ partial failure, giới hạn quyền connector và cơ chế dừng an toàn.

### 17.3. Lưu ý khi membership graph lớn

- Không duyệt đệ quy vô hạn khi có group cycle;
- Không chỉ dựa vào số group trực tiếp để ước tính quyền;
- Chú ý membership qua tenant/domain/trust;
- Định nghĩa xử lý group không tồn tại, bị xóa hoặc owner không xác định;
- Với dynamic rule, chấp nhận độ trễ có giới hạn và đo reconciliation lag;
- Phân biệt **tập quan hệ thành viên** với **tập role hiệu lực** để xử lý nhiều đường cấp cùng một quyền;
- Khi xóa một cạnh membership, quyền chỉ thực sự mất nếu không còn đường hợp lệ khác hoặc quyền trực tiếp.

## 18. Kiểm thử di trú theo tính chất quyền

Không chỉ kiểm tra group count hoặc role count. Một nhóm 100 thành viên bị giảm còn 99 có thể là thu hồi hợp lệ; đồng thời 100 thành viên đủ nhưng toàn bộ sai scope vẫn có thể vi phạm bảo mật.

### 18.1. Positive và negative authorization

Với mỗi mapping nhạy cảm, tạo cặp kiểm thử:

- User thuộc Sales-HCM **được** đọc record thuộc team HCM;
- Cùng user **không được** đọc record team Hà Nội;
- Người có role FinanceApprover **được** duyệt đúng ngưỡng;
- Người đó **không được** duyệt giao dịch mình tạo nếu SoD cấm;
- Nhà thầu chỉ được truy cập project còn hạn;
- Leaver không được login bằng SSO, local auth, session cũ hoặc API token còn trong phạm vi.

### 18.2. Các nhóm tình huống cần bao phủ

| Nhóm kiểm thử | Ví dụ |
|---|---|
| Identity matching | User đổi email, duplicate, guest nhiều tenant |
| Group topology | Nested group, cycle, nhóm rỗng, nhóm động |
| Role equivalence | Role 1→nhiều, nhiều→1, role bị loại bỏ |
| Scope | Tenant, team, record, field, export |
| SoD/PAM | Tổ hợp role xung đột, admin với quyền tạm |
| Protocol | SSO claim, SCIM Group, direct app grant |
| JML | Joiner tương lai, mover, leaver, rejoiner, contractor |
| Failure | Source batch thiếu, API timeout, event sai thứ tự |
| Recovery | Rollback khi đã có JML mới, token cũ, tài khoản dịch vụ |

## 19. Cutover: kiểm soát thay đổi role thật

### 19.1. Các bước trước cutover

1. Khóa phiên bản group catalog, role mapping, identity crosswalk, policy và danh sách exception.
2. Chụp baseline actual memberships/entitlements có quyền truy cập phù hợp.
3. Kiểm tra owner và approver cho từng nhóm đặc quyền hoặc role nhạy cảm.
4. Xác minh pilot chứng minh cả quyền **được** và **không được** dùng.
5. Xác định single writer theo từng hệ, cohort và nhóm/role.
6. Chuẩn bị event backlog, mốc delta, rate limit, retry, rollback và người trực.
7. Đặt guardrail cho bulk grant/revoke, lỗi mapping và source quality.
8. Chỉ chuyển khi có quyết định go/no-go từ người có trách nhiệm.

### 19.2. Cutover theo cohort

Ví dụ chuyển nhóm Sales-HCM:

- Đọc danh sách người còn active theo JML hiện hành;
- Resolve account đích bằng canonical identity;
- Tính role/ABAC scope từ hợp đồng mapping đã duyệt;
- Provision group/role vào ứng dụng mới, dùng ID của provider đích;
- Gỡ quyền cũ không còn hợp lệ, kiểm tra ngoại lệ còn hạn;
- Thử SSO và quyền thật trên dữ liệu HCM và ngoài HCM;
- Tiếp tục xử lý các event JML phát sinh trong cửa sổ chuyển đổi;
- Theo dõi lag, drift và sự cố trước khi mở rộng cohort.

Không coi user “có mặt trong group ở IdP-B” là đủ nếu app vẫn gán role cục bộ không tương đương.

### 19.3. Ngưỡng dừng

Dừng writer hoặc cohort có vấn đề khi gặp: mapping sai chủ thể, role đặc quyền cấp ngoài phê duyệt, quyền mở rộng scope, leaver vẫn truy cập, nguồn thiếu dữ liệu, nhiều membership bị thu hồi bất thường hoặc SCIM/API trả lỗi kéo dài. Ngưỡng cụ thể phải dựa baseline/risk của tổ chức và được chấp thuận trước, không dùng ngưỡng ví dụ như mặc định.

## 20. Reconciliation và giám sát drift

**Desired state**: vai trò và quyền hợp lệ theo nguồn danh tính, policy IAM/IGA, mapping đã duyệt và ngoại lệ còn hiệu lực.

**Actual state**: nhóm và role đang tồn tại ở directory/IdP/ứng dụng, quyền được thực thi thực tế, direct grant, PAM, session và token.

| Sai lệch | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| User active thiếu group đích | SCIM lỗi, ID không map được | Retry có kiểm soát/ticket, tránh duplicate |
| User leaver vẫn có role | Deprovision thất bại hoặc app-local role | Thu hồi đúng đường, kiểm chứng actual access |
| Role đích quá rộng | Mapping theo tên, mất team scope | Chỉnh policy/role và cách ly quyền nhạy cảm |
| Group IdP đúng nhưng app role sai | App mapping theo tên/claim khác | Sửa liên kết, đối soát app-local entitlement |
| Group lồng bị bỏ sót | Target không expand nested group | Tính effective membership có kiểm soát |
| Quyền còn sau remove group | Nhiều đường cấp hoặc direct grant | Xác định nguyên nhân và thu hồi quyền không hợp lệ |
| Hai group/role writer tranh nhau | Đồng bộ hai chiều không có authority | Pause writer, sửa ownership/version |
| Group mất phần lớn member | Source batch lỗi, replace toàn bộ danh sách | Guardrail hold và xác minh nguồn |
| SoD vi phạm sau hợp nhất role | Mapping n→1 gộp quyền xung đột | Tách role/giới hạn hành động, phê duyệt |
| Admin role không owner | Quên PAM hoặc orphan service account | Điều tra, gán owner/review hoặc revoke |

### 20.1. KPI

- **Verified mapping coverage:** số nhóm/role trong phạm vi có mapping được owner xác minh / tổng số cần chuyển.
- **Membership reconciliation accuracy:** tỷ lệ thành viên kỳ vọng khớp trạng thái thực tế, phân biệt direct và indirect.
- **Role/entitlement drift:** tỷ lệ quyền hoặc role thực tế khác desired state.
- **Privileged access drift:** số đặc quyền không có approval hoặc vượt scope; ưu tiên hơn chỉ số chung.
- **SoD violation count:** số tổ hợp quyền xung đột còn hiệu lực.
- **Duplicate/orphan group rate:** nhóm trùng ngoài thiết kế hoặc thiếu owner.
- **Provisioning success/latency:** tỷ lệ và độ trễ thay đổi group/role đến đích.
- **Leaver revocation latency:** từ effective time đến khi các đường truy cập trong phạm vi bị thu hồi.
- **Unresolved exception aging:** thời gian ca mapping/SoD/direct grant chưa được owner xử lý.
- **Source/reconciliation lag:** thời gian trễ cập nhật, thời gian phát hiện sai lệch.
- **Token/session revocation coverage:** các đích kiểm tra thu hồi hoặc thời hạn của quyền cũ.

**KPI không thay thế kiểm thử hành vi.** Một role có đúng tên và đúng số thành viên vẫn có thể cho phép xem dữ liệu ngoài phạm vi.

## 21. Rollback phải bảo toàn JML hiện hành

Rollback mapping role không chỉ là thay tên group trở về bản cũ. Sau cutover có thể đã xảy ra mover, leaver, role approval, account disable và entitlement revoke hợp lệ.

### 21.1. Runbook phục hồi

1. **Pause writer** gây lỗi, ghi incident, giữ snapshot, mapping/policy version và event backlog.
2. Xác định những thay đổi JML, phê duyệt, exception và thu hồi có hiệu lực sau mốc cutover.
3. Chọn source/writer có thẩm quyền theo phương án rollback đã duyệt.
4. Rebuild **desired entitlements từ trạng thái hiện hành**, không khôi phục mù membership cũ.
5. Replay lệnh idempotent, chặn duplicate/late event và giữ audit.
6. Kiểm tra SSO, SCIM, application-local role, PAM, session/token và scope dữ liệu.
7. Đối soát người đã nghỉ, quyền đặc quyền và role xung đột trước khi mở traffic.
8. Ghi nguyên nhân, biện pháp phòng ngừa và quyết định có thử cutover lại.

Không phải mọi hành động đều đảo ngược hoàn toàn: token/secret đã thu hồi, role đã xóa, account đã hợp nhất, dữ liệu đã chia sẻ hoặc group thay đổi SID có thể cần phục hồi riêng. Phải thử các giới hạn từ pilot.

### 21.2. Ví dụ nguy cơ hồi sinh quyền

10:00 snapshot cho thấy Lan thuộc group Finance; 10:30 Lan chuyển Procurement và quyền Finance bị gỡ; 11:00 rollback bằng snapshot 10:00 sẽ cấp lại Finance trái policy.

Giải pháp là áp lại **sự kiện mover 10:30 và quyền được phê duyệt hiện hành** khi phục hồi. Cùng nguyên tắc đối với leaver và contractor hết hạn.

## 22. Case study: hợp nhất AD group vào role CRM SaaS

Giả sử một tổ chức có **1.200 nhân viên**, **100 nhà thầu**, hai domain AD và CRM-Legacy. Dự án chuyển sang directory/IdP mới và CRM SaaS. Số liệu trong case study chỉ nhằm minh họa, không phải benchmark.

### 22.1. Inventory và phát hiện

- 280 security group, trong đó 35 nhóm lồng nhau;
- 20 group không rõ owner, phải rà soát;
- 18 nhóm có quyền CRM, một số role app được cấp trực tiếp;
- Một role **SalesManager** mới cho phép xem record toàn tenant, trong khi group Sales-HCM cũ chỉ đọc record HCM;
- Một số nhà thầu tham gia nhóm dự án qua guest account, expiry được quản lý ở nguồn hợp đồng;
- 6 bot kết nối CRM bằng API credential riêng.

### 22.2. Quyết định mapping

Chủ ứng dụng và IAM xác nhận:

1. GG_Sales_HCM → TeamReader/TeamEditor với teamId=HCM, không dùng SalesManager toàn tenant.
2. GG_CRM_Export → role ExportTeamData riêng; các direct export grant cũ cần approval lại.
3. GG_Fin_Approver → FinanceApprover có hạn mức và SoD, không gộp với Requester.
4. Distribution list không map sang security role.
5. Nhóm không owner được quarantine; các nhóm không còn dùng được retire theo phụ thuộc thực tế.
6. Bot có owner và API scope được cấp theo job, không thêm vào group quản trị toàn cầu.

### 22.3. Pilot và hai lỗi phát hiện

**Lỗi 1 — Nested group:** Một nhóm được lồng trong CRM_Readers ở AD nhưng IdP mới chỉ gửi membership trực tiếp. User hợp lệ không có quyền trong CRM. Nhóm triển khai tính effective membership ở IAM và provision target membership theo contract đã duyệt, sau đó kiểm tra remove membership.

**Lỗi 2 — Mover giữa cutover:** Nhân viên Minh chuyển team HCM sang Hà Nội sau snapshot. Một job nhập group cũ vẫn gán TeamEditor HCM. Hệ thống sửa bằng cách đối soát desired membership từ event JML mới nhất trước khi cấp quyền, gỡ HCM và cấp scope Hà Nội nếu hợp lệ.

### 22.4. Kiểm thử quyền và nghiệm thu

Các reviewer kiểm tra:

- Người Sales-HCM đọc được khách hàng HCM, bị từ chối record Hà Nội;
- Người FinanceApprover không được tự duyệt giao dịch mình tạo;
- Leaver bị chặn ở IdP, CRM và API cũ trong SLA;
- Nhà thầu hết hạn mất group dự án;
- Bot tiếp tục chạy với scope được duyệt nhưng token cũ bị thu hồi;
- Nhóm đặc quyền không có owner không được tự cấp role đích;
- Bảng mapping, quyết định và audit cho từng cohort có thể truy vết.

Sau khi reconciliation và access review đạt, tổ chức mới dừng connector cũ và retire group/trust không còn được sử dụng.

**Bài học:** Thành công của mapping group/role nằm ở **tập quyền thực tế trên đúng tài nguyên và đúng thời điểm**, chứ không nằm ở việc tên nhóm và số thành viên trông giống nhau.

## 23. Bộ kiểm thử nghiệm thu

| Mã | Tình huống | Kết quả mong đợi |
|---|---|---|
| T01 | Group nguồn và đích cùng tên nhưng scope khác | Không mặc định mapping; owner duyệt theo quyền |
| T02 | Đổi tên group, giữ ID nguồn | Không tạo group mới hoặc gán sai |
| T03 | Hai tenant có group cùng tên | Mapping tách namespace/tenant |
| T04 | User đổi email | Link đúng canonical identity, không mất membership |
| T05 | Một user có account thường và admin riêng | Không tự gộp role đặc quyền vào account thường |
| T06 | Nhóm lồng hai cấp | Effective membership chính xác |
| T07 | Group có cycle | Không vòng lặp vô hạn, có xử lý theo policy |
| T08 | Target không hỗ trợ nested group | Flatten có kiểm soát, revoke đúng khi membership nguồn mất |
| T09 | Dynamic group với thuộc tính thiếu | Không tự cấp role rộng; có cảnh báo |
| T10 | Distribution list tên giống security group | Không cấp role ứng dụng |
| T11 | Mapping 1 group → nhiều role | Chỉ cấp các role cần thiết theo scope |
| T12 | Nhiều group → một role | Không phá SoD hoặc mở rộng quyền |
| T13 | Role mới giống tên nhưng rộng hơn | Không cấp khi chưa giới hạn/phê duyệt |
| T14 | Role FinanceRequester và Approver xung đột | SoD bị chặn hoặc xử lý theo policy |
| T15 | Group admin/PAM | Có approval, MFA, owner và audit |
| T16 | SCIM Group.members dùng ID user đích | Update đúng member, không nhầm old ID |
| T17 | SCIM PATCH remove một member | Không thay toàn bộ membership |
| T18 | Event lặp hoặc retry | Idempotent, không tạo group/grant trùng |
| T19 | Event mover đến sau leaver | Không hồi sinh account/quyền |
| T20 | Joiner chưa đến effective date | Không kích hoạt role quá sớm |
| T21 | Mover đổi phòng ban | Cấp mới, thu hồi cũ và direct grant |
| T22 | Leaver trong coexistence | Mất quyền tại app cũ/mới và đường token theo SLA |
| T23 | Contractor hết hạn | Gỡ quyền theo nguồn hợp đồng có thẩm quyền |
| T24 | Rejoiner | Không tự phục hồi role cũ không còn lý do |
| T25 | Source batch rỗng do lỗi | Không mass revoke; giữ để xác minh |
| T26 | Bulk group add bất thường | Guardrail hold, security review |
| T27 | Group claim quá nhiều hoặc bị thiếu | Ứng dụng dùng cơ chế hỗ trợ, không bỏ qua xác minh |
| T28 | Token cũ còn claim role | Thu hồi/giảm hiệu lực theo thiết kế và SLA |
| T29 | App có direct grant ngoài SCIM | Reconciliation phát hiện và xử lý |
| T30 | Service account owner nghỉ việc | Bàn giao owner và review scope/credential |
| T31 | Account có group đúng nhưng API mở record ngoài team | Negative authorization phát hiện và chặn |
| T32 | Rollback sau sự kiện mover/leaver | Không khôi phục quyền đã thu hồi hợp lệ |
| T33 | Đối soát quyền từ nhiều đường cấp | Chỉ thu hồi quyền khi không còn lý do hợp lệ |
| T34 | Source và target có role mapping version khác | Audit chỉ rõ quyết định và chênh lệch |
| T35 | SCIM provider trả thành công nhưng app chưa áp quyền | Reconciliation phát hiện độ trễ/lỗi và ticket |

Ghi bằng chứng cho mỗi case: **expected/actual result, cohort, tenant, test identity, app resource, mapping/policy version, timestamp, event/correlation ID, owner, exception và phương án xử lý**. Không coi một test “login OK” là nghiệm thu quyền.

## 24. Checklist trước và sau go-live

### Trước cutover

- [ ] Có inventory group, role, permission, owner, tenant và loại group.
- [ ] Có account/identity crosswalk được xác minh, không match bằng tên/email duy nhất.
- [ ] Có mapping contract theo action, resource, scope và rule version.
- [ ] Có danh sách nested/dynamic group, nhóm không owner và special group.
- [ ] Có owner phê duyệt mapping đặc quyền/SoD và quyền theo record.
- [ ] Có single writer, dependency graph, guardrail, dry-run và audit.
- [ ] Đã thử JML, SCIM, SSO/claims, app-local role, PAM và service identity.
- [ ] Có kiểm thử positive/negative authorization cho ứng dụng trọng yếu.
- [ ] Có snapshot, delta replay, cutover/rollback runbook và người trực sự cố.
- [ ] Có ngưỡng go/no-go dựa trên baseline và mức độ rủi ro.

### Sau cutover

- [ ] Membership/entitlement ở đích đã đối soát với desired state.
- [ ] Role đặc quyền và SoD không phát sinh ngoài phê duyệt.
- [ ] Leaver, mover, nhà thầu, rejoiner chạy đúng SLA và policy.
- [ ] App-local direct grant, token/session và access ngoài SSO đã được rà soát.
- [ ] Service account, bot, guest có owner và expiry/review hợp lệ.
- [ ] Có ticket/owner/hạn xử lý cho mọi exception còn mở.
- [ ] Trust, credential, connector và group cũ không còn dùng đã được retire theo kế hoạch.
- [ ] Mapping, phê duyệt, audit và bằng chứng kiểm thử được lưu theo retention.

## 25. Những sai lầm cần tránh

**Đổi tên group rồi cho là tương đương:** Role đích có thể cấp nhiều quyền hơn. So action/resource/scope và thử quyền bị từ chối.

**Chỉ copy direct membership:** Bỏ sót nested/dynamic membership hoặc làm mất quyền cần thiết. Tính effective graph có kiểm soát.

**Copy toàn bộ group bao gồm distribution list:** Tăng nguy cơ cấp quyền ngoài chính sách. Phân loại group theo mục đích và owner.

**Gộp nhiều role thành một role mạnh:** Có thể phá SoD hoặc mở rộng quyền dữ liệu. Rà soát theo từng permission.

**Dùng group name hoặc email làm khóa:** Dễ trùng/đổi giữa domain/tenant. Dùng ID trong đúng namespace và canonical identity.

**Tin rằng group ở IdP đồng nghĩa quyền đã đổi tại app:** Direct grant, token và app-local role có vòng đời riêng. Cần đối soát actual state.

**Chỉ thêm role mới cho mover:** Người đổi vai trò tích lũy quyền cũ. Tính lại desired state và kiểm thử revoke.

**Xem batch thiếu là lệnh gỡ toàn bộ membership:** Có thể mass deprovision do nguồn lỗi. Phân biệt snapshot đủ với partial update và đặt guardrail.

**Không quản lý nhóm đặc quyền và service account:** Role admin dư hoặc bot vô chủ tồn tại dài hạn. Dùng PAM/IGA, owner, approval và expiry.

**Rollback snapshot nguyên xi:** Có thể kích hoạt lại leaver hoặc cấp role cũ. Replay sự kiện JML mới nhất và audit.

## 26. Câu hỏi tự kiểm tra

1. Group, role, permission và entitlement khác nhau như thế nào?
2. Vì sao group cùng tên ở hai tenant không đủ bằng chứng để mapping tự động?
3. Một role SalesManager ở app mới rộng hơn ở app cũ; bạn cần so gì để phát hiện?
4. Khi chuyển nhóm lồng sang IdP không hỗ trợ nested membership, phải làm gì?
5. Vì sao nhóm distribution list không nên tự động được chuyển thành security role?
6. SoD có thể bị phá vỡ khi mapping nhiều role vào một role mới như thế nào?
7. Vì sao SCIM Group.members.value không thể lấy trực tiếp old AD SID?
8. Nhân viên chuyển Sales sang Finance: những đường quyền nào cần thu hồi?
9. Khi user đã nghỉ còn refresh token hoặc direct app role, tại sao disable ở IdP chưa đủ?
10. Một source batch rỗng ảnh hưởng như thế nào đến membership và cách bảo vệ ra sao?
11. Làm sao chứng minh một user bị từ chối đọc record ngoài team sau migration?
12. Role của bot có cần được quản trị giống role người dùng hay không?
13. Tại sao cần cùng lúc mapping version, policy version và event version?
14. Rollback sau mover/leaver phải dựa vào trạng thái nào?
15. Khi một permission được cấp qua hai group, việc xóa một membership có tự động xóa permission đó không?

**Gợi ý:** Tập trung vào identity continuity, nguồn có thẩm quyền, group topology, quyền theo hành vi và scope, desired/actual reconciliation, JML effective time, token/session và audit.

## 27. Thuật ngữ và tài liệu nền tảng

| Thuật ngữ | Diễn giải |
|---|---|
| **Group / membership** | Nhóm chủ thể / quan hệ thành viên |
| **Nested/dynamic group** | Nhóm lồng nhau / nhóm tính thành viên từ quy tắc |
| **Role / permission** | Vai trò / hành động được phép |
| **Entitlement** | Quyền đã gán cho principal trong hệ đích |
| **RBAC / ABAC** | Kiểm soát truy cập theo vai trò / thuộc tính |
| **SoD** | Separation of Duties: ngăn tổ hợp quyền xung đột |
| **IAM / IGA / PAM** | Quản lý quyền truy cập / quản trị danh tính / quản trị đặc quyền |
| **IdP / SSO / MFA** | Nhà cung cấp danh tính / đăng nhập một lần / xác thực đa yếu tố |
| **SCIM** | Giao thức provisioning tài nguyên User/Group |
| **JML** | Joiner–Mover–Leaver: vào, chuyển và rời tổ chức |
| **Canonical identity** | Khóa định danh chủ thể ổn định |
| **Effective access** | Quyền thực sự sau khi áp các điều kiện liên quan |
| **Source of authority** | Nguồn có quyền xác nhận trạng thái/quyết định |
| **Single writer** | Một bên có thẩm quyền ghi một lớp dữ liệu/quyền |
| **Reconciliation / drift** | Đối soát trạng thái kỳ vọng với sai lệch thực tế |
| **Coexistence / cutover / rollback** | Cùng tồn tại / chuyển chính thức / phục hồi có kiểm soát |
| **Idempotency** | Chạy lại thao tác không tạo tác động lặp ngoài ý muốn |

Tài liệu để tham khảo khi thiết kế thực tế:

- **RFC 7643 — SCIM Core Schema:** User/Group, members, externalId, các thuộc tính và tính chất schema.
- **RFC 7644 — SCIM Protocol:** create, PATCH, search, delete và tương tác với service provider.
- **OpenID Connect Core 1.0:** issuer/subject, ID token và định danh tài khoản trong liên hợp.
- **SAML 2.0 Core và Bindings (OASIS):** NameID, assertion và attribute statements.
- **NIST SP 800-53:** các nguyên tắc least privilege, access control, kiểm toán và quản lý quyền.
- **Tài liệu chính thức của directory, IdP, IGA, PAM và ứng dụng đích:** group ID, nested/dynamic membership, role claim, SCIM support, direct grant, API, session/token revocation và giới hạn cụ thể của từng sản phẩm.

**Tiêu chí quyết định:** Mapping nhóm và role chỉ thành công khi **đúng chủ thể có đúng quyền trên đúng tài nguyên, đúng thời điểm**, các quyền đã hết lý do được thu hồi cả tại ứng dụng, các xung đột đặc quyền được kiểm soát và toàn bộ quá trình có bằng chứng để đối soát, kiểm toán và phục hồi.

