# Subject trong Authorization: xác định đúng chủ thể trước khi cấp quyền

**Subject (chủ thể)** trong **Authorization** là thực thể đang tìm cách thực hiện một **hành động (action)** trên một **tài nguyên (resource)** trong một **ngữ cảnh (context)** cụ thể. Subject có thể là một người dùng đã xác thực, ứng dụng, tiến trình, workload, service account hoặc một chủ thể được đại diện hợp lệ. Hệ thống phân quyền phải xác định **đúng subject, trạng thái hiện tại và những thuộc tính đáng tin cậy** trước khi trả lời: *chủ thể này có được phép thực hiện hành động đó với tài nguyên này ngay bây giờ không?*

Trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, việc xác định subject liên quan trực tiếp đến **vòng đời danh tính Joiner–Mover–Leaver (JML)**: từ xác minh danh tính, tạo tài khoản và cấp quyền lúc gia nhập, đến cập nhật quyền khi chuyển vai trò, rồi thu hồi khi rời tổ chức. **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán** đều có thể cung cấp dữ liệu để xác định hoặc đánh giá subject, nhưng mỗi thành phần có nhiệm vụ khác nhau.

**Điểm then chốt:** Subject không chỉ là một chuỗi `userId` trong request. Đó là **danh tính/định danh bảo mật đã được xác lập trong ranh giới tin cậy**, gắn với nguồn thuộc tính, quan hệ làm việc và điều kiện phân quyền có thể thay đổi theo thời gian. Nếu lấy một định danh do client tự gửi rồi coi là subject được tin cậy, hệ thống có thể cấp quyền cho nhầm người hoặc mở đường cho tấn công giả mạo, truy cập chéo tenant và quyền tồn dư.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa **subject** trong quyết định authorization và phân biệt với **identity, account, principal, actor, role, resource**.
2. Xác định chủ thể hợp lệ trong các tình huống **người dùng, workload, service account, khách chưa xác thực, nhà thầu liên kết** và ủy quyền hành động.
3. Mô tả cách subject xuất hiện trong **request context** và cách **PEP/PDP/PIP** dùng dữ liệu này.
4. Nhận biết định danh ổn định như **`(iss, sub)` trong OIDC** và các lưu ý khi ánh xạ SAML/SCIM/directory.
5. Sử dụng **role và thuộc tính subject** để xây dựng kiểm tra **RBAC/ABAC**, kết hợp trạng thái account, engagement và quan hệ với tài nguyên.
6. Phân tích **delegation, impersonation, multi-tenant, token claim cũ và session** mà không nhầm người thực hiện với người được đại diện.
7. Thiết kế kiểm soát khi **Joiner, Mover, Leaver** để giảm quyền truy cập tồn dư ở nhiều ứng dụng.
8. Kiểm tra, ghi log và giải thích quyết định cho phép/từ chối mà không lộ dữ liệu hoặc bí mật xác thực.

## 2. Subject là gì trong một quyết định cấp quyền?

Xét một request:

> Nhân viên Mai muốn **đọc** báo cáo doanh thu **R-2026-15** lúc 09:00 từ ứng dụng báo cáo.

Một quyết định có thể được mô hình hóa:

~~~text
AuthorizationRequest = {
  subject:  Mai / danh tính đã xác thực,
  action:   "report.read",
  resource: báo cáo R-2026-15,
  context:  tenant, thời gian, phiên, mức xác thực, thiết bị...
}
Decision = PERMIT hoặc DENY (có thể kèm nghĩa vụ/điều kiện)
~~~

**Subject** là phía yêu cầu truy cập; **resource** là đối tượng được bảo vệ; **action** chỉ thao tác cần thực hiện. Chính sách có thể xét thêm môi trường, trạng thái dữ liệu, chủ sở hữu tài nguyên hoặc giới hạn nhiệm vụ.

Một subject **không được phép** có thể đã đăng nhập thành công. Ví dụ, Mai qua SSO đúng nhưng không thuộc bộ phận được đọc báo cáo tài chính. Việc xác thực chỉ xác lập một phần **ai đang yêu cầu**, không tự tạo quyền `report.read`.

### 2.1. Subject có luôn là con người không?

**Không.** Trong các mô hình kiểm soát truy cập, subject có thể là **tiến trình hoặc thực thể** thực hiện hoạt động. Trong IAM doanh nghiệp, có các dạng điển hình:

- Một **nhân viên** truy cập ứng dụng sau khi đăng nhập.
- Một **nhà thầu/đối tác** truy cập theo engagement và sponsor còn hiệu lực.
- Một **backend service** gọi API bằng workload identity.
- Một **automation job** chạy theo lịch với scope tối thiểu.
- Một **quản trị viên** hành động qua phiên đặc quyền được phê duyệt.
- Một **dịch vụ trung gian** được ủy quyền thực hiện thao tác thay mặt người dùng.

Subject phải được mô hình hóa phù hợp loại thực thể; không giả định mọi token đều đại diện một nhân viên hoặc mỗi account đều có địa chỉ email.

## 3. Phân biệt Subject, Identity, Account, Principal, Actor và Role

Những thuật ngữ này liên hệ chặt chẽ nhưng không đồng nhất.

| Thuật ngữ | Cách hiểu trong IAM | Ví dụ |
|---|---|---|
| **Identity** | Bản ghi/khái niệm nhận diện một cá nhân hoặc workload trong hệ thống quản lý danh tính | `personId=P-2048` hoặc `workloadId=W-17` |
| **Account** | Tài khoản tại một hệ thống cụ thể dùng để truy cập hoặc được cấp quyền | `crmUserId=CRM-810`, account LDAP |
| **Principal** | Định danh bảo mật hoặc thực thể được hệ thống xác thực nhận diện; ý nghĩa cụ thể tùy nền tảng | `Principal` trong Java Security, Kerberos principal |
| **Subject** | Thực thể mà yêu cầu authorization đang xét quyền | Người dùng P-2048 muốn đọc hóa đơn |
| **Actor** | Thực thể thật sự thực hiện thao tác, có thể khác chủ thể được đại diện trong delegation | Service xử lý yêu cầu thay mặt Mai |
| **Role** | Nhóm trách nhiệm/quyền hoặc nhãn chính sách gán cho chủ thể | `finance_analyst` |
| **Resource** | Đối tượng đang được bảo vệ | Báo cáo, ticket, bảng dữ liệu, project |
| **Entitlement / grant** | Quyền được cấp có căn cứ, qua role/nhóm/direct grant | `invoice.read@region=south` |

### 3.1. Identity không phải account

Một người có thể có một **identity ổn định** nhưng nhiều account tại IdP, CRM, Git và VPN. Một service có thể có workload identity và nhiều credential hoặc account ứng dụng. IAM cần **ánh xạ đúng identity ↔ account tại từng hệ thống** để cấp và thu hồi quyền.

Ví dụ:

~~~text
Identity:
  personId: P-2048

Accounts:
  IdP:   IDP-908
  CRM:   CRM-1102
  Git:   git-mai
  VPN:   VPN-0047

Authorization subject canonical:
  tenant: company-vn
  type: HUMAN
  id: P-2048
~~~

Không suy ra rằng `CRM-1102` và `git-mai` thuộc cùng một người chỉ dựa trên tên hiển thị. Phải có **mapping có nguồn xác minh**.

### 3.2. Principal và Subject có thể trùng nhau về đại diện, nhưng không phải từ đồng nghĩa tuyệt đối

Trong một framework, đối tượng `Principal` có thể thể hiện tên người đã xác thực; trong một hệ thống khác, `Subject` là tập hợp nhiều principal và credential; trong mô hình policy, subject là một thực thể trong authorization request. Vì vậy, khi đọc mã hoặc tài liệu API phải nắm **ngữ nghĩa của nền tảng cụ thể**, không chuyển thuật ngữ một cách máy móc.

Trong bài này, **subject** là khái niệm phân quyền tổng quát: **ai hoặc thực thể nào đang được đánh giá quyền truy cập**.

### 3.3. Role không phải subject

`finance_analyst` là một role, không phải định danh duy nhất của Mai. Hai người cùng role vẫn có thể khác **tenant, vùng dữ liệu, dự án, mức phê duyệt hoặc trạng thái hợp đồng**. Phân quyền chỉ dựa trên role mà bỏ qua resource/context có thể mở quyền quá rộng.

## 4. Các loại Subject trong hệ thống doanh nghiệp

| Loại subject | Nguồn định danh có thể sử dụng | Điều kiện riêng cần kiểm tra |
|---|---|---|
| **Human employee** | HR → IAM → IdP/account | Engagement active, role hiện tại, phạm vi dữ liệu |
| **Contractor** | VMS/hợp đồng → sponsor → IAM | Hạn hợp đồng, dự án, sponsor và quyền theo engagement |
| **External federated user** | IdP đối tác qua SAML/OIDC + liên kết nội bộ | Issuer/tenant đúng, mapping, chính sách truy cập đối tác |
| **Service/workload** | Service catalog, workload identity, client registration | Owner kỹ thuật, audience/scope, môi trường, secret/khóa |
| **Privileged human session** | Subject người dùng + phiên PAM/JIT | Phê duyệt đặc quyền, time-bound, mục đích thao tác |
| **Anonymous/guest** | Không có user identity được xác thực hoặc guest marker có kiểm soát | Chỉ tài nguyên công khai hoặc phạm vi guest được thiết kế |
| **Delegated subject** | Người dùng hoặc workload gốc + actor được ủy quyền | Quyền ủy quyền, thời hạn, chuỗi actor và audit |
| **Shared/legacy account** | Account cục bộ không phân biệt người thực hiện | Rủi ro truy vết; cần owner, kiểm soát và kế hoạch thay thế |

**Subject chưa xác thực** không được giả danh thành tài khoản nội bộ mặc định. Nếu ứng dụng có trang công khai, có thể biểu diễn `anonymous` một cách tường minh và chỉ cho các hành động public đã được chính sách cho phép.

## 5. Xây dựng subject từ thông tin đáng tin cậy

Một cách biểu diễn logic:

~~~json
{
  "subject": {
    "kind": "HUMAN",
    "canonicalId": "P-2048",
    "tenantId": "company-vn",
    "identityProvider": "https://idp.example.test",
    "providerSubject": "user-8fd2",
    "accountStatus": "ACTIVE",
    "engagementIds": ["ENG-713"],
    "roles": ["finance_analyst"],
    "attributesVersion": 27
  },
  "action": "invoice.read",
  "resource": {
    "id": "INV-2039",
    "tenantId": "company-vn",
    "projectId": "PRJ-31",
    "region": "south"
  },
  "context": {
    "requestedAt": "2026-12-01T09:00:00+07:00",
    "authenticationAssurance": "POLICY_ACCEPTED"
  }
}
~~~

Đây là **schema minh họa**, không phải chuẩn chung hay dữ liệu cá nhân thật. Những trường như `roles`, `accountStatus` và `engagementIds` cần được lấy từ **nguồn có thẩm quyền** hoặc cơ chế xác minh phù hợp; không lấy tùy ý từ body của API request.

### 5.1. Nguồn từng loại dữ liệu

| Dữ liệu subject | Nguồn đáng tin thường gặp | Cần tránh |
|---|---|---|
| Định danh người nội bộ | IAM/HR correlation đã xác minh | Ghép identity chỉ theo email/tên |
| Trạng thái employment/engagement | HR/VMS hoặc hệ thống hợp đồng | Tin claim cũ sau Leaver |
| Định danh phiên | IdP/AS hoặc session service đáng tin | Nhận `userId` tự khai từ trình duyệt |
| Group/role | IAM/IGA/ứng dụng theo quyền quản trị | Tin một header `X-Role` do client gửi |
| Thuộc tính tenant | Tenant resolver đáng tin, policy và account mapping | Dựa hoàn toàn vào query `tenantId` |
| Owner workload | Service catalog / inventory chính thức | Lấy người tạo key làm owner vĩnh viễn |
| Mức xác thực | Kết quả IdP/OIDC/SAML đã kiểm chứng | Tin chuỗi `mfa=true` tự gửi |
| Điều kiện thiết bị | Dịch vụ/device posture được tin cậy | Tin một header không được xác minh |

**Nguyên tắc:** Thuộc tính nằm trong một token có chữ ký **có thể đáng tin về nguồn phát hành**, nhưng vẫn cần kiểm tra **issuer, audience, thời gian, loại token, subject mapping, chính sách và độ mới** trước khi dùng làm căn cứ cấp quyền.

## 6. Định danh Subject ổn định và khả năng ánh xạ giữa hệ thống

Định danh không ổn định là nguyên nhân thường gặp của lỗi cấp quyền sai hoặc không thu hồi được quyền khi Mover/Leaver.

### 6.1. OIDC: `(iss, sub)`

Với **OIDC ID token**, `sub` là định danh subject do OpenID Provider phát hành. Để tránh nhầm giữa các issuer, ứng dụng thường định danh subject bằng **cặp `(issuer, subject)`**, không chỉ `sub`.

~~~text
Issuer A: https://idp-a.example.test
sub:      4129

Issuer B: https://idp-b.example.test
sub:      4129

=> Hai subject không được tự coi là cùng một người.
~~~

Một số nhà cung cấp hỗ trợ **pairwise subject identifiers**, trong đó cùng một người có thể có `sub` khác nhau giữa các client/sector theo thiết kế bảo vệ riêng tư. Nếu tổ chức cần liên kết người qua ứng dụng, phải dùng **quy trình mapping có thẩm quyền**, không tự suy ra từ email.

**Lưu ý:** Với **OAuth access token**, ý nghĩa `sub` và các claim tùy profile/token type; trong **Client Credentials**, `sub` có thể đại diện client/workload. Không mặc định `sub` của mọi access token đều là ID nhân viên.

### 6.2. SAML: NameID và định danh liên kết

SAML assertion có thể chứa **NameID** và các attribute khác. Các định dạng NameID có ngữ nghĩa khác nhau (ví dụ persistent, transient, email). Ứng dụng phải biết **IdP nào phát hành, NameID format nào đang sử dụng, mapping nào đã được phê duyệt**.

- Email NameID có thể đổi, được tái cấp hoặc không phù hợp làm khóa bất biến.
- Transient NameID không nên được dùng làm khóa tài khoản lâu dài.
- Persistent identifier có thể hữu ích cho ánh xạ ổn định trong phạm vi hợp đồng tin cậy.
- Khi thay IdP hoặc liên kết đối tác, cần kiểm chứng account linking, không chỉ ghép theo tên hiển thị.

### 6.3. SCIM: `id` và `externalId`

Trong SCIM, **`id`** thường là định danh resource do **service provider** quản lý; **`externalId`** là thuộc tính do bên provisioning cung cấp để hỗ trợ tương quan theo phạm vi của bên đó. Chúng không mặc nhiên là một mã toàn cầu chung cho tất cả ứng dụng.

**Ví dụ:** IAM map `personId=P-2048` với `scimUserId=7ab3` tại CRM và `externalId=P-2048`. Khi thu hồi, IAM phải nhắm đúng resource ở CRM; không xóa một user khác chỉ vì tên trùng.

### 6.4. Directory: DN, SID, GUID và giới hạn di chuyển

Trong LDAP/Active Directory, **Distinguished Name (DN)** có thể thay đổi nếu đối tượng được di chuyển hoặc đổi tên. Các định danh như `objectGUID` hoặc `objectSid` có vai trò khác nhau, với lưu ý đặc thù về domain/forest migration và phạm vi định danh. Không nên tự giả định một thuộc tính duy nhất **bất biến xuyên mọi lần chuyển hệ thống**.

Trong thực tế, IAM thường cần **canonical identity ID riêng**, cộng các mapping tới directory object, IdP subject và account đích, với hồ sơ thay đổi được kiểm toán.

## 7. Subject trong luồng Authentication → Authorization

Một request chỉ đáng tin khi ứng dụng xác lập subject qua **đường xác thực phù hợp**, sau đó đưa subject vào **authorization context** không thể bị client tùy ý thay.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Client / Browser
    participant I as IdP / SSO
    participant P as PEP / API
    participant D as PDP / Policy engine
    participant S as IAM / PIP dữ liệu
    participant R as Resource

    U->>C: Truy cập chức năng
    C->>I: Authentication qua giao thức được duyệt
    I-->>C: Kết quả đã xác thực / token
    C->>P: Request + session hoặc access token
    P->>P: Kiểm token/phiên và ánh xạ subject
    P->>S: Lấy trạng thái, role, thuộc tính nếu cần
    S-->>P: Identity và dữ liệu hiện hành
    P->>D: Subject + action + resource + context
    D-->>P: PERMIT / DENY và điều kiện
    P->>R: Chỉ thực thi nếu PERMIT
    R-->>P: Kết quả hành động
    P-->>C: Phản hồi
~~~

**PEP (Policy Enforcement Point)** là nơi thực thi quyết định cho phép/từ chối. **PDP (Policy Decision Point)** là nơi đánh giá policy; **PIP (Policy Information Point)** cung cấp các thuộc tính phục vụ đánh giá. Các thành phần này có thể cùng nằm trong một service hoặc tách riêng.

### 7.1. Kiểm token và ánh xạ subject

Nếu API dùng access token, các bước thường gồm:

1. Xác minh **loại token** thích hợp để gọi API.
2. Kiểm tra chữ ký hoặc introspection/trạng thái theo kiến trúc.
3. Đối chiếu **issuer, audience, thời hạn và các ràng buộc** được yêu cầu.
4. Xác định `sub` hoặc định danh client theo profile token.
5. Ánh xạ sang **canonical subject** trong đúng tenant.
6. Kiểm tra trạng thái subject/engagement theo policy, nhất là với quyền nhạy cảm.
7. Đánh giá authorization với **resource cụ thể**, không chỉ scope chung.

**ID token không phải access token cho API.** ID token được dùng cho client/RP kiểm chứng sự kiện đăng nhập theo OIDC; gửi ID token đến API chỉ vì có `sub` và chữ ký hợp lệ là nhầm ranh giới giao thức.

### 7.2. Không lấy subject trực tiếp từ request body

Ví dụ nguy hiểm:

~~~http
POST /api/invoices/INV-2039/approve
Authorization: Bearer VALID_TOKEN_FOR_USER_B

{
  "subjectId": "USER_A",
  "approved": true
}
~~~

Nếu backend dùng `subjectId=USER_A` từ JSON để quyết định quyền của request, user B có thể mạo danh user A. API phải lấy **subject đang thực hiện** từ **security context đã kiểm chứng**, còn trường `subjectId` trong body — nếu nghiệp vụ thật sự cần — phải được xem là **dữ liệu đích** và kiểm tra quyền tác động đến đối tượng đó.

## 8. Subject trong RBAC: gán vai trò và kích hoạt vai trò

**Role-Based Access Control (RBAC)** gán người dùng/chủ thể vào các **role** đã được quản trị, rồi gán permission cho role. Trong nhiều mô hình, session có thể kích hoạt một tập role phù hợp.

~~~text
Subject: P-2048
  Roles assigned:
    finance_analyst
    expense_submitter

Role: finance_analyst
  Permissions:
    invoice.read
    report.read

Role: expense_submitter
  Permissions:
    expense.create

Request:
  subject=P-2048, action=invoice.read
  => Chỉ PERMIT nếu role được phép, đang hợp lệ
     và mọi điều kiện khác đều đạt.
~~~

### 8.1. Role phải gắn với đúng chủ thể và trạng thái

Một subject có thể thuộc role `finance_analyst` nhưng:

- Hợp đồng đã hết hạn.
- Đang bị đình chỉ hoặc Leaver đã có hiệu lực.
- Chưa hoàn tất mức MFA cần thiết cho hành động đặc quyền.
- Đang xử lý tài nguyên của tenant khác.
- Có xung đột **Separation of Duties (SoD)** với vai trò phê duyệt.
- Chỉ được truy cập dự án A, không phải mọi dữ liệu Finance.

Vì vậy, **role membership không phải câu trả lời cuối cùng cho mọi request**.

### 8.2. Role và nhóm đồng bộ từ IdP

Một nhóm trong directory hoặc IdP **có thể** được dùng để suy ra role, nhưng cần mapping có owner, quy tắc cấp quyền và vòng đời. Không mặc định rằng tên nhóm từ đối tác ngoài như `Admins` được phép trở thành role admin nội bộ.

Các thay đổi nhóm qua **SCIM/API** phải được xác minh ở ứng dụng. Nếu một nhóm cũ vẫn lưu trong cache hoặc token, Mover có thể giữ quyền ngoài dự kiến.

## 9. Subject trong ABAC: thuộc tính, tài nguyên và ngữ cảnh

**Attribute-Based Access Control (ABAC)** đánh giá thuộc tính subject cùng thuộc tính resource, action và environment/context. Nó hữu ích khi hai người cùng role nhưng khác phạm vi.

Ví dụ chính sách:

> Chỉ cho phép một nhân viên Finance đang hoạt động đọc hóa đơn nếu người đó thuộc đúng tenant, có nhiệm vụ tại dự án chứa hóa đơn, và yêu cầu thỏa mãn mức bảo đảm xác thực.

Một mô hình minh họa:

~~~text
Permit subject S đọc invoice R khi và chỉ khi:
  S.accountStatus == ACTIVE
  AND S.engagementStatus == ACTIVE
  AND S.tenantId == R.tenantId
  AND "finance_analyst" thuộc S.roles
  AND R.projectId thuộc S.authorizedProjectIds
  AND Context.authenticationAssurance đáp ứng policy
  AND Action == "invoice.read"
~~~

### 9.1. Các thuộc tính thường xét

| Nhóm thuộc tính | Ví dụ | Lưu ý |
|---|---|---|
| **Subject** | `subject.kind`, `department`, `projectIds`, `employmentStatus` | Phải có nguồn rõ và đủ mới |
| **Resource** | `ownerId`, `tenantId`, `classification`, `projectId` | Lấy từ backend/trusted data, không tin client tự khai |
| **Action** | `read`, `update`, `approve`, `export` | Hành động có độ nhạy khác nhau |
| **Environment** | Thời gian, trạng thái thiết bị, mạng, rủi ro phiên | Cần dữ liệu đáng tin và cách xử lý khi không có |
| **Relationship** | Subject là owner, reviewer hoặc thành viên dự án của resource | Có thể kết hợp quan hệ với RBAC/ABAC |

**Cần phân biệt** `workLocation` do HR xác nhận với geolocation suy từ IP của request. Nếu chính sách yêu cầu “đang thuộc cơ sở HCM”, không tự sửa thuộc tính đó theo một IP dùng VPN hoặc proxy.

### 9.2. Ví dụ Java kiểm quyền theo subject

Mã sau minh họa phần **quyết định nghiệp vụ** của API. Giả định lớp xác thực ở trước đó đã kiểm chứng token và xây dựng `SubjectContext`; không dùng mã này thay thư viện xác thực hoặc policy engine đã được đánh giá.

~~~java
import java.util.Set;

record SubjectContext(
    String id,
    String tenantId,
    boolean accountActive,
    boolean engagementActive,
    Set<String> roles,
    Set<String> authorizedProjectIds,
    boolean assuranceSatisfied
) {}

record Invoice(
    String id,
    String tenantId,
    String projectId
) {}

final class InvoiceAuthorization {
    static boolean canRead(SubjectContext subject, Invoice invoice) {
        if (subject == null || invoice == null) return false;
        if (!subject.accountActive() || !subject.engagementActive()) {
            return false;
        }
        if (!subject.assuranceSatisfied()) return false;
        if (!subject.tenantId().equals(invoice.tenantId())) return false;
        if (!subject.roles().contains("finance_analyst")) return false;
        return subject.authorizedProjectIds().contains(invoice.projectId());
    }
}
~~~

**Giới hạn của ví dụ:** Trong production phải kiểm dữ liệu null/immutable, nguồn role/thuộc tính, thời điểm hiệu lực, loại subject, cache, SoD và quyền chi tiết. `authorizedProjectIds` phải được lấy từ cơ chế có thẩm quyền; nếu client có thể tự điền danh sách đó, policy bị vô hiệu hóa.

## 10. PEP, PDP, PIP, PAP và trách nhiệm đối với Subject

Một hệ thống phân quyền có thể được phân tách thành các điểm sau:

| Thành phần | Vai trò | Liên hệ subject |
|---|---|---|
| **PEP – Policy Enforcement Point** | Chặn request và thực thi quyết định | Truyền subject đã xác thực và từ chối khi không được phép |
| **PDP – Policy Decision Point** | Đánh giá policy cho request | So sánh role/attribute subject với resource/action/context |
| **PIP – Policy Information Point** | Cung cấp dữ liệu thuộc tính phục vụ chính sách | Đưa trạng thái JML, project, role đáng tin |
| **PAP – Policy Administration Point** | Quản trị, phê duyệt và phiên bản chính sách | Xác định ai được gán quyền gì theo quy tắc |
| **IAM / IGA** | Quản lý identity và entitlement theo vòng đời | Cập nhật trạng thái subject, grant và source-of-truth |
| **Audit / reconciliation** | Truy vết kết quả và đối soát quyền hiệu dụng | Phát hiện subject bị cấp quyền ngoài chính sách |

~~~mermaid
flowchart TD
    U["Request từ user / workload"] --> PEP["PEP: kiểm session / token<br/>và xây dựng subject"]
    PEP --> PDP["PDP: đánh giá policy"]
    PAP["PAP: policy đã duyệt"] --> PDP
    PIP["PIP: trạng thái JML,<br/>role, resource attributes"] --> PDP
    PDP --> DEC{"Decision?"}
    DEC -->|PERMIT| A["PEP thực thi có giới hạn"]
    DEC -->|DENY / INDETERMINATE| N["PEP từ chối hoặc xử lý<br/>theo policy an toàn"]
    A --> AUD["Audit / reconciliation"]
    N --> AUD
~~~

Với policy không thể đánh giá vì thiếu trạng thái subject quan trọng, **không mặc định PERMIT**. Các hệ thống có thể phân biệt `DENY`, `NOT_APPLICABLE` hoặc `INDETERMINATE` theo policy engine; cách tổng hợp phải được định nghĩa trước. Những ngoại lệ cho ứng dụng ít rủi ro phải được duyệt riêng, không trở thành “fail-open” toàn cục.

## 11. Phạm vi tenant và chủ thể trong hệ thống đa khách hàng

Trong **multi-tenant application**, cùng một email hoặc tên người dùng có thể xuất hiện ở nhiều tenant. Một subject thường cần **tenant context** được xác minh, và một user có thể có **membership/role khác nhau theo từng tenant**.

Ví dụ:

~~~text
Canonical person: P-2048

Tenant A:
  subject membership: active
  roles: ["viewer"]
  allowed projects: ["A-01"]

Tenant B:
  subject membership: suspended
  roles: ["editor"]  (dữ liệu cũ)

Request:
  tenantId=B, action=document.update, resource tenant=B

Decision: DENY
  vì membership tại B đang suspended,
  dù cùng người đang active ở tenant A.
~~~

Các quy tắc quan trọng:

1. Xác định **tenant yêu cầu** từ route/resource và security context đáng tin.
2. Kiểm **subject có membership hợp lệ ở tenant đó không**, không chỉ subject tồn tại toàn hệ thống.
3. So sánh **tenant của resource và subject context**; không tin tenant ID do body tự khai.
4. Role/permission phải có **scope tenant hoặc project** khi chính sách yêu cầu.
5. Không dùng email hay ID số ngắn làm khóa phân quyền xuyên tenant.
6. Ghi log cả canonical subject, tenant, action, resource reference và quyết định theo mức bảo vệ dữ liệu.

Nếu API chỉ kiểm token hợp lệ mà bỏ qua tenant, nó dễ mắc lỗi **Broken Object Level Authorization (BOLA)** hoặc truy cập chéo tenant.

## 12. Subject và bảo mật cấp đối tượng: BOLA/IDOR

**Insecure Direct Object Reference (IDOR)** và **Broken Object Level Authorization (BOLA)** xuất hiện khi ứng dụng truy cập một object theo ID nhưng không xác minh **subject có quyền trên object đó**.

Ví dụ:

~~~http
GET /api/invoices/INV-2039
Authorization: Bearer ACCESS_TOKEN_FOR_MAI
~~~

Backend có thể kiểm `reports.read` rồi trả về hóa đơn, nhưng nếu hóa đơn thuộc dự án không được Mai phụ trách, quyết định đó vẫn sai. Cần kiểm:

- Subject đã được xác định đúng và engagement còn hiệu lực.
- Resource thuộc đúng tenant và dự án được bảo trợ.
- Action `invoice.read` hợp lệ với role và chính sách.
- Có hạn chế dữ liệu theo classification, site, owner hoặc workflow không.
- Cache hoặc kết quả lookup không làm lẫn quyền giữa các subject.

**Đừng coi việc ẩn nút trên giao diện là authorization.** API, background job và đường truy cập dữ liệu vẫn phải thực thi kiểm soát ở nơi thích hợp.

## 13. Ủy quyền và hành động thay mặt: Subject khác Actor

Trong một số kiến trúc, **actor** thực hiện request không phải subject được đại diện hoặc người sở hữu dữ liệu. Ví dụ, dịch vụ xử lý đơn hàng gọi API thanh toán **thay mặt** người dùng; nhân viên hỗ trợ được phép thao tác trên tài khoản khách hàng; hệ thống đồng bộ được ủy quyền cập nhật ticket.

Cần phân biệt:

| Khái niệm | Ví dụ | Vấn đề cần kiểm soát |
|---|---|---|
| **End-user / represented subject** | Khách hàng C-301 | Người có quyền/chủ thể được đại diện |
| **Actor thực hiện** | Service payment-worker | Ai thực sự gọi API và sở hữu credential |
| **Delegation grant** | C-301 cho phép payment-worker xử lý đơn hàng | Scope, consent/căn cứ, hết hạn và revocation |
| **Effective authorization context** | Actor + subject + scope + resource | Có được làm hành động này thay mặt người đó không? |

### 13.1. Không suy ra ủy quyền chỉ vì request có `onBehalfOf`

Đây là lỗi nguy hiểm:

~~~json
{
  "onBehalfOf": "executive-user",
  "action": "payment.approve",
  "resourceId": "PAY-991"
}
~~~

Nếu backend nhận đối tượng trên từ bất kỳ client nào và dùng `onBehalfOf` làm subject chính, kẻ tấn công có thể mạo danh người khác. Hệ thống phải **xác minh actor, grant ủy quyền hợp lệ, phạm vi, thời điểm và resource** bằng cơ chế tin cậy; request chỉ mang tham chiếu nghiệp vụ chưa phải bằng chứng ủy quyền.

### 13.2. Delegation và impersonation cần kiểm toán riêng

- **Delegation hợp lệ:** Có quyết định cho phép cụ thể, phạm vi, thời hạn và khả năng thu hồi.
- **Admin impersonation/support mode:** Có workflow phê duyệt, lý do sử dụng, giới hạn hành động, cảnh báo và audit.
- **Token exchange/on-behalf-of:** Chỉ sử dụng khi giao thức, AS và policy triển khai đúng; không tự thiết kế token “đóng vai” bằng cách sửa claim.
- **Service-to-service:** Xác thực workload của actor và áp quyền actor, không gắn ngầm identity con người vào mọi job.

Log nên ghi **actor thực tế và subject được đại diện**, cùng căn cứ ủy quyền, để tránh mọi hành động đều “trông như” được người dùng cuối trực tiếp thực hiện.

## 14. Subject, Authentication Assurance và phiên

Một subject có thể được xác lập bởi một lần xác thực hợp lệ, nhưng **mức bảo đảm và độ mới của xác thực** có thể chưa đủ cho một action nhạy cảm.

Ví dụ:

- Nhân viên xem dashboard công khai nội bộ từ phiên SSO bình thường.
- Cùng subject muốn thay đổi credential tài khoản quản trị.
- Chính sách yêu cầu **step-up authentication**, thiết bị được quản lý hoặc phê duyệt JIT/PAM trước thao tác.

**MFA/step-up không tự cấp role.** Sau khi step-up thành công, subject vẫn cần entitlement hợp lệ; một người ngoài nhóm quản trị không trở thành admin chỉ vì đã dùng passkey.

### 14.1. Khi token chứa subject cũ

Một JWT access token có thể chứa `sub`, role/scope và `exp`. Sau khi Mover, những claim đã phát trước đó **không tự thay đổi**. Nếu Resource Server chỉ kiểm chữ ký và hạn token, quyền cũ có thể còn được thực thi đến lúc token hết hạn.

Các kiểm soát tùy kiến trúc gồm:

- Giới hạn **thời hạn token** theo rủi ro.
- Introspection hoặc kiểm trạng thái hiện hành khi phù hợp.
- Policy/version check đối với quyền nhạy cảm.
- Invalidate session/authorization cache khi Mover/Leaver.
- Thu hồi refresh token, access token hoặc grant qua khả năng được hỗ trợ.
- **Readback quyền hiệu dụng tại API**, không chỉ kiểm trạng thái IdP.

**Từ góc nhìn authorization, subject phải được xét theo trạng thái hiện tại cần thiết cho hành động**, không mặc định “token còn hạn = mọi quyền lúc phát vẫn được giữ” khi chính sách yêu cầu thu hồi sớm.

## 15. Subject trong Joiner: định danh, tạo account và quyền ban đầu

Trong **Joiner**, tổ chức cần liên kết người mới với subject ổn định trước khi cấp quyền.

~~~text
Nguồn HR / VMS
    ↓  identity proofing và xác nhận engagement
IAM / IGA
    ↓  canonical identity ID và thời điểm hiệu lực
IdP / Directory
    ↓  account + authenticator + nhóm
SCIM / API provisioning
    ↓  account ứng dụng và mapping chính xác
Authorization policy
    ↓  subject + role/attribute + resource
Ứng dụng/API
    → PERMIT hoặc DENY dựa trên quyền thực tế
~~~

### Điều kiện cần kiểm tra

1. Người mới đã được **xác minh đủ mức theo chính sách**.
2. `personId`/subject ID ổn định, không trùng với người cũ hoặc account đang tồn tại.
3. Engagement có **nguồn phê duyệt và mốc hiệu lực** rõ.
4. Account đích đã được ánh xạ với đúng identity, không chỉ cùng email.
5. Role ban đầu được cấp theo **least privilege**, đúng bộ phận/dự án/tenant.
6. Phương thức xác thực và MFA đã được đăng ký đúng.
7. Ứng dụng/RS đã **readback** trạng thái và entitlement; không nhầm “lệnh SCIM thành công” với “quyền đã đúng”.

**Ví dụ:** Account đã được tạo trước ngày bắt đầu làm việc nhưng `engagementEffectiveAt` chưa tới. Việc người dùng hoàn thành kích hoạt authenticator theo quy trình onboarding **không có nghĩa** họ được phép truy cập dữ liệu công việc trước thời điểm được phê duyệt.

## 16. Subject trong Mover: giữ identity, thay căn cứ phân quyền

**Mover** là biến cố người dùng chuyển phòng ban, dự án, địa điểm hoặc trách nhiệm. Thông thường subject ID vẫn giữ nguyên, nhưng **role, group, scope, điều kiện ABAC và quyền hiệu dụng** phải được tính lại.

Giả sử Linh chuyển từ dự án A sang B:

~~~text
Subject canonical: P-301        (không đổi)
Trước Mover:
  engagement: active
  project: A
  roles: [analyst]
  permissions: document.read@A, report.export@A

Sau Mover mong muốn:
  engagement: active
  project: B
  roles: [analyst]
  permissions: document.read@B

Phải thêm:       document.read@B
Phải thu hồi:    document.read@A, report.export@A
Giữ nguyên:      identity và các quyền toàn tổ chức còn hợp lệ
~~~

### 16.1. Sai lầm thường gặp: chỉ thêm quyền mới

Nếu IAM chỉ thêm nhóm B, subject có thể tiếp tục thấy dữ liệu A. Cần tính:

~~~text
DesiredAccess = quyền còn được phép sau Mover
EffectiveAccess = quyền ứng dụng thực tế đang chấp nhận

ToGrant  = DesiredAccess - EffectiveAccess
ToRevoke = EffectiveAccess - DesiredAccess
~~~

Công thức khái niệm chưa giải quyết mọi trường hợp **nhiều nguồn grant**. Nếu subject còn engagement khác hợp lệ với A, không nên xóa quyền đó bừa bãi; cần ghi **nguồn cấp quyền (grant provenance)** và kiểm tra lại quyền hiệu dụng.

### 16.2. Thuộc tính subject có thể chậm đồng bộ

HR/VMS đã cập nhật nhiệm vụ nhưng:

- IdP vẫn phát group cũ.
- SCIM chưa cập nhật quyền ở ứng dụng.
- Session chứa claim trước Mover.
- Directory replica chưa thấy group mới.
- API còn cache project membership cũ.

Do đó Mover chưa hoàn tất chỉ vì bản ghi HR đã thay. Cần **đối soát source-of-truth → policy → target account → authorization tại API**.

## 17. Subject trong Leaver: không còn căn cứ thì không còn quyền

**Leaver** là giai đoạn chấm dứt quan hệ làm việc, hợp đồng hoặc engagement theo chính sách. Một subject có thể:

- Không còn **bất kỳ engagement hợp lệ nào**, cần chặn quyền truy cập công việc.
- Chỉ kết thúc **một engagement** nhưng vẫn có engagement khác hợp lệ, cần thu hồi đúng phạm vi.
- Rời vai trò owner của service account, cần chuyển giao ownership và xử lý credential riêng.

### 17.1. Vô hiệu hóa account không đủ để xác minh hoàn tất

Khi HR báo Leaver:

1. IAM xác định đúng **canonical subject** và những account liên quan.
2. IdP/directory vô hiệu hóa hoặc giới hạn account theo chính sách.
3. SCIM/API hoặc cơ chế thay thế thu hồi role, group, direct grant tại ứng dụng.
4. Session, refresh/access token, PAT, API key và đường truy cập độc lập được đánh giá/thu hồi theo yêu cầu.
5. PEP/RS phải từ chối request thuộc subject **không còn eligible**, kể cả nếu token cũ chưa hết hạn khi chính sách yêu cầu chặn.
6. Quyền hiệu dụng tại các target bắt buộc được **readback** và lưu bằng chứng.
7. Những target chưa xác minh có owner, trạng thái lỗi/chờ, hạn xử lý và biện pháp bù trừ.

**Không tự kết luận Leaver hoàn tất khi chỉ thấy `active=false` trong IdP.** Một ứng dụng legacy có account local hoặc một API sử dụng token tự chứa có thể vẫn chấp nhận truy cập.

### 17.2. Subject có nhiều engagement

Ví dụ một contractor kết thúc dự án A nhưng còn hợp đồng B đến hết tháng:

~~~text
Subject: contractor-P-91
Engagement A: ENDED
Engagement B: ACTIVE

Desired entitlements:
  Được giữ: repo.read@B
  Phải gỡ:  repo.admin@A, ticket.manage@A

Account IdP:
  Có thể vẫn ACTIVE để phục vụ B theo policy.
~~~

**Không đồng nhất “Leaver của một engagement” với “xóa danh tính của cá nhân khỏi toàn hệ thống”.** Cần kiểm tra quyền A đã mất hiệu lực, quyền B vẫn có căn cứ và mọi token/role không thể tràn phạm vi giữa hai dự án.

### 17.3. Rejoiner và account reuse

Khi người quay lại, IAM cần xác minh họ là **đúng subject cũ** hoặc liên kết identity theo quy trình được duyệt, kiểm lại authenticator và thuộc tính JML. **Không tự phục hồi vai trò, nhóm và session cũ** chỉ vì account được kích hoạt lại.

## 18. Subject của workload và service account

Với hệ thống máy đến máy, **workload** là subject riêng, không phải người quản trị từng tạo credential.

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| **Workload subject** | `W-REPORT-SYNC` | Thực thể đang gọi API |
| **Service/client account** | `client_id=report-sync` | Định danh client được AS công nhận |
| **Service owner** | Data Platform team | Chịu trách nhiệm mục đích và vòng đời |
| **Credential** | Khóa riêng, certificate, managed identity | Chứng minh quyền kiểm soát workload/client |
| **Entitlement** | `invoice.read@production` | Quyền cần cho nhiệm vụ |
| **Target resource** | API hóa đơn | Nơi thực thi authorization |

### 18.1. Client Credentials không có người dùng tương tác

Trong **OAuth 2.0 Client Credentials**, client có thể lấy access token sau khi xác thực bằng credential được phép. Đây là một **grant máy đến máy**; API không nên suy ra có một nhân viên đã đăng nhập từ token này.

Nếu `sub` trong access token đại diện client/workload theo profile, hệ thống phải xử lý như **subject loại SERVICE**, áp quyền đúng client và không sử dụng các quy tắc chỉ dành cho con người (ví dụ HR employee status) để thay thế quản trị workload.

### 18.2. Không đưa mật khẩu người vào job

Một job chạy hằng đêm không nên dùng mật khẩu của nhân viên DevOps. Nếu nhân viên đó Mover/Leaver, job có thể bị lỗi hoặc tiếp tục dùng credential người đã rời tổ chức.

Nên dùng workload identity/service account có:

- Chủ sở hữu kỹ thuật và ứng dụng tương ứng rõ ràng.
- Scope/audience, môi trường và quyền tối thiểu.
- Credential ngắn hạn hoặc managed identity khi nền tảng hỗ trợ.
- Secret manager, rotation, giám sát và khả năng thu hồi.
- Kiểm chứng quyền hiệu dụng và dependency trước khi thay đổi phá vỡ production.

### 18.3. Ownerless service account

Một account máy có thể vẫn hợp lệ trong khi owner đã nghỉ. Không xóa ngay chỉ vì `ownerId` rỗng; phải **kiểm tra workload và phụ thuộc**, bổ nhiệm owner mới có trách nhiệm, rà soát quyền và xử lý credential cũ theo rủi ro. Nếu workload đã ngừng hoặc không còn căn cứ, tiến hành deprovision và readback theo chính sách.

## 19. Các rủi ro bảo mật khi xác định Subject sai

| Rủi ro | Mô tả | Kiểm soát phù hợp |
|---|---|---|
| **Subject spoofing** | Client tự gửi `userId` của người khác | Subject lấy từ security context đã kiểm chứng |
| **BOLA/IDOR** | Token đúng nhưng đọc tài nguyên không được phép | Authorization ở API theo resource, tenant, action |
| **Cross-tenant access** | Role ở tenant A được dùng tại tenant B | Scope tenant trong subject và resource |
| **Token substitution** | ID token/token của API khác được chấp nhận | Kiểm token type, issuer, audience, chữ ký/thời hạn |
| **Account mislinking** | Ghép người theo email/tên trùng | Canonical ID, mapping có thẩm quyền, kiểm danh tính |
| **Stale attributes** | Group/role cũ sau Mover/Leaver | TTL/cache invalidation, readback, current-state checks |
| **Privilege accumulation** | Chỉ thêm role, không gỡ quyền cũ | Recompute desired access, grant provenance |
| **Impersonation abuse** | Admin/support đóng vai subject không có phê duyệt | Grant ủy quyền, phạm vi, time-bound, log actor |
| **Confused deputy** | Service có quyền rộng bị dùng để truy cập thay client không đủ quyền | Bound actor/subject/resource/scope, kiểm cả hai phía |
| **Overprivileged service account** | Workload dùng quyền admin toàn hệ thống | Least privilege, owner, credential lifecycle |
| **Fail-open authorization** | Không lấy được thuộc tính thì cho phép | Deny by default hoặc degraded mode được duyệt |
| **Inaccurate audit attribution** | Log chỉ ghi người được đại diện, bỏ actor | Ghi cả actor, effective subject và căn cứ |
| **Group/role name collision** | Tin group ngoài trùng tên role nội bộ | Mapping theo issuer/tenant và policy |
| **Missing Leaver propagation** | IdP disabled nhưng app/session còn active | Deprovision đa hệ thống, revoke và kiểm chứng |

### 19.1. Confused deputy là gì?

Một service có quyền rộng như `billing.admin` có thể bị một client quyền thấp yêu cầu thực hiện thay thao tác không được phép. Nếu service chỉ kiểm **quyền của chính nó** mà không kiểm **quyền ủy quyền và tài nguyên gắn với subject gốc**, nó có thể trở thành **confused deputy**.

Thiết kế an toàn cần kiểm **actor được phép thực hiện loại thao tác này không, subject gốc có quyền với tài nguyên không và delegation có hợp lệ không**. Chỉ một access token hợp lệ của service không đủ để bỏ qua chính sách của end user khi giao thức là hành động thay mặt.

### 19.2. Không sửa lỗi bằng cách mở rộng quyền toàn hệ thống

Nếu một subject bị từ chối truy cập do thiếu role hoặc mapping sai, không nên xử lý bằng cách gán `admin` hoặc bỏ kiểm tenant. Cần xác định **đang lỗi authentication, identity mapping, provisioning hay authorization**, rồi sửa đúng lớp.

## 20. Tình huống thực hành 1: nhân viên chuyển bộ phận

**Bối cảnh:** Phương đang là nhân viên hỗ trợ khách hàng và được quyền xem ticket tại dự án A. Từ ngày 01/12, Phương chuyển sang phân tích tài chính ở dự án B. HR đã cập nhật vai trò, nhưng ứng dụng ticket vẫn giữ `support_agent@A`. Phương đăng nhập SSO thành công với cùng subject ID.

### Điều gì vẫn đúng?

- Subject của Phương **vẫn là cùng một identity**, trừ khi có quy trình migration đặc biệt.
- Authentication qua SSO có thể hoàn toàn hợp lệ.
- Mức MFA có thể tiếp tục đạt, nhưng không tự chứng minh được quyền dự án.

### Điều gì cần thay đổi?

1. IAM nhận sự kiện Mover từ nguồn có thẩm quyền.
2. Tính lại role và thuộc tính subject theo dự án B.
3. Cấp quyền B khi đã có căn cứ; thu hồi grant A không còn hợp lệ.
4. SCIM/API đồng bộ tới ứng dụng, kiểm quyền trực tiếp ngoài nhóm.
5. Session, token và cache chứa quyền A được đánh giá theo policy.
6. Đọc lại quyền thực tế tại API: `ticket.read@A` phải bị từ chối nếu không còn grant hợp lệ, `invoice.read@B` chỉ được cho phép khi đầy đủ điều kiện.
7. Lưu bản ghi Mover và bằng chứng đối soát.

**Lỗi phổ biến:** Thấy `sub` không đổi rồi cho rằng role cũng không đổi. **Subject ID ổn định để truy vết**, còn entitlement phải cập nhật theo vòng đời.

## 21. Tình huống thực hành 2: nhà thầu liên kết và hai tenant

**Bối cảnh:** Chuyên gia ngoài công ty đăng nhập qua OIDC IdP của đối tác. Cùng email `consultant@example.test` xuất hiện ở hai tenant khách hàng. Ứng dụng dùng email làm khóa user toàn cục và nhận `tenantId` từ request body.

### Rủi ro

- Email có thể trùng, đổi hoặc tái sử dụng.
- `sub` có thể chỉ duy nhất trong phạm vi issuer; một đối tác khác có thể dùng cùng chuỗi `sub`.
- `tenantId` trong request body có thể bị sửa để truy cập dữ liệu tenant khác.
- Hết engagement ở tenant A nhưng còn engagement ở B không được xử lý đúng.

### Cách thiết kế

1. Xác minh issuer và ID token/access token phù hợp giao thức.
2. Ánh xạ `(iss, sub)` hoặc định danh federation đã phê duyệt sang canonical subject.
3. Quản lý **membership/engagement theo tenant** với sponsor, quyền và thời hạn riêng.
4. Lấy resource tenant từ dữ liệu backend, so sánh với membership đã xác minh.
5. Khi engagement A kết thúc, thu hồi role/grant A; giữ B chỉ khi còn căn cứ.
6. Readback quyền hiệu dụng và log issuer/subject/tenant theo mức bảo vệ cần thiết.

**Bài học:** **Subject phải được ràng buộc với issuer và phạm vi tenant**, không chỉ một email thuận tiện cho giao diện.

## 22. Tình huống thực hành 3: backend được ủy quyền thao tác thay người dùng

**Bối cảnh:** Một web app cho phép nhân viên đặt hàng. Backend gọi API phê duyệt vận chuyển bằng service account có scope `shipment.manage`. Client gửi tham số `requestedBy=user-123`.

**Nguy cơ:** Nếu API chỉ tin service account và đọc `requestedBy` làm người yêu cầu, bất kỳ user nào có thể yêu cầu service xử lý shipment của người khác.

**Thiết kế cần kiểm tra:**

- Actor backend được xác thực bằng workload credential và có quyền gọi API phù hợp.
- Subject/end user đã được xác thực qua luồng đáng tin; request không tự mạo danh.
- Ủy quyền on-behalf-of hoặc mô hình truyền context được AS/API hỗ trợ và bảo vệ.
- Resource `shipmentId` thuộc đúng tenant và user/project được phép.
- Action được kiểm theo vai trò của end user và scope của actor khi nghiệp vụ yêu cầu.
- Log ghi **cả actor service lẫn subject end user**; không mất tính truy vết.
- Khi người dùng Leaver hoặc grant hết hạn, hành động thay mặt họ phải bị chặn theo policy.

## 23. Kiểm toán quyết định theo Subject

Một bản ghi kiểm toán hữu ích cần phân biệt **thông tin nhận diện**, **lý do quyết định** và **dữ liệu nhạy cảm không được lưu**.

~~~json
{
  "decisionId": "AUTHZ-2026-1189",
  "requestTime": "2026-12-01T09:11:21+07:00",
  "subject": {
    "kind": "HUMAN",
    "canonicalId": "P-2048",
    "tenantId": "company-vn",
    "identityProvider": "https://idp.example.test"
  },
  "actor": {
    "kind": "HUMAN",
    "canonicalId": "P-2048"
  },
  "action": "invoice.read",
  "resourceRef": "INV-2039",
  "policyVersion": "invoice-access-v6",
  "decision": "DENY",
  "reasonCode": "PROJECT_SCOPE_MISMATCH",
  "evidence": {
    "subjectAttributesVersion": 27,
    "engagementStatus": "ACTIVE",
    "tokenValidation": "PASS"
  },
  "correlationId": "REQ-9021"
}
~~~

Đây là ví dụ học tập; không phải log thật. Hệ thống thực tế cần cân bằng khả năng truy vết với **quyền riêng tư và thời hạn lưu dữ liệu**.

### 23.1. Nên ghi gì?

| Nhóm | Ví dụ có ích | Tránh |
|---|---|---|
| Subject | Canonical ID, loại, tenant theo quyền truy cập log | Thông tin giấy tờ không cần thiết |
| Actor/delegation | Ai thao tác, ai được đại diện, grant reference | Mạo danh thành người dùng để che actor |
| Authentication context | Issuer, cách kiểm chứng, mức bảo đảm được chấp nhận | Token nguyên văn, mật khẩu, OTP |
| Resource/action | ID tham chiếu, hành động, tenant hoặc classification khi phù hợp | Sao chép toàn bộ dữ liệu nhạy cảm |
| Policy | Policy ID/version, reason code, PERMIT/DENY | Tiết lộ toàn bộ logic phòng vệ trên giao diện công khai |
| Lifecycle | Mốc hiệu lực, trạng thái engagement, version | Toàn bộ hồ sơ HR |
| Readback | Target, trạng thái quyền thực tế, thời điểm | Secret và dữ liệu không liên quan |

### 23.2. Chỉ số chất lượng authorization theo Subject

- **Unknown/unmapped subjects:** Request hoặc account không ánh xạ được subject đáng tin.
- **Inactive subject access attempts:** Yêu cầu từ subject đã Leaver hoặc engagement hết hiệu lực.
- **Cross-tenant denies:** Lần từ chối do phạm vi tenant, phân tích cả lỗi và dấu hiệu tấn công.
- **Stale subject attributes:** Thuộc tính/group/role quá hạn hoặc khác source-of-truth.
- **Residual access after Mover/Leaver:** Quyền hiệu dụng còn trái trạng thái mong muốn.
- **Delegation audit completeness:** Tỷ lệ hành động thay mặt có actor, subject và căn cứ ủy quyền.
- **Service subject ownership coverage:** Workload có owner, mục đích và quyền được rà soát.
- **Authorization decision latency:** Chi phí lấy attribute và thực thi policy, cùng khả năng chịu lỗi.
- **Policy evaluation errors:** Request thiếu dữ liệu quan trọng dẫn đến `INDETERMINATE` và cách xử lý.
- **Readback coverage:** Tỷ lệ thay đổi JML được xác minh ở các ứng dụng bắt buộc.

Các chỉ số phải phục vụ **quyền truy cập đúng và khả năng điều tra**, không khuyến khích nới chính sách chỉ để tăng tỷ lệ PERMIT.

## 24. Bài tập tự kiểm tra

**Câu 1:** Một user gửi body `{"userId":"admin"}` nhưng token thuộc nhân viên bình thường. API phải dùng giá trị nào để xác định subject?

**Gợi ý:** Sử dụng subject từ **security context đã xác thực và kiểm chứng**, không tự tin body `userId`. Nếu body biểu diễn user đích, phải kiểm quyền thao tác lên user đó.

**Câu 2:** `sub="123"` từ issuer A và `sub="123"` từ issuer B có mặc định là một subject không?

**Gợi ý:** Không. Trong OIDC cần xét `(iss, sub)` và quy trình account mapping có thẩm quyền.

**Câu 3:** Service account gọi API qua Client Credentials. Có thể kết luận một nhân viên đã đăng nhập từ `sub` trong access token không?

**Gợi ý:** Không. `sub` trong token máy đến máy có ngữ nghĩa theo profile và có thể là client/workload; cần loại subject chính xác.

**Câu 4:** Người dùng có role `finance_analyst`. Có được xem mọi hóa đơn không?

**Gợi ý:** Không tự động. Kiểm resource tenant, project, engagement và điều kiện ABAC/SoD.

**Câu 5:** Sau Mover, `personId` không đổi nhưng group cũ vẫn còn trong JWT. Có thể coi quyền cũ vẫn hợp lệ không?

**Gợi ý:** Không nếu chính sách đã thu hồi. Cần xem token lifecycle, cache và quyền hiệu dụng tại RS.

**Câu 6:** Contractor hết dự án A nhưng còn dự án B. Có cần xóa toàn bộ identity không?

**Gợi ý:** Phải xét engagement và grant theo dự án. Thu hồi A; giữ B nếu còn hợp lệ và account đáp ứng chính sách.

**Câu 7:** Backend gọi API thay người dùng. Audit chỉ ghi `subjectId` của end user. Thiếu gì?

**Gợi ý:** Cần ghi **actor thực hiện**, phương thức/grant ủy quyền và phạm vi, không chỉ represented subject.

**Câu 8:** Policy engine không lấy được `employmentStatus`. Để “giữ dịch vụ hoạt động”, ứng dụng mặc định cho phép mọi action. Có phù hợp không?

**Gợi ý:** Không. Thiếu dữ liệu bảo mật quan trọng cần được xử lý theo chính sách an toàn; không fail-open mặc định.

**Câu 9:** Nhóm `Admins` từ IdP đối tác có được map trực tiếp thành admin của ứng dụng nội bộ không?

**Gợi ý:** Không tự động. Cần mapping đã duyệt, nguồn tin cậy và cấp quyền theo tenant/ứng dụng/engagement.

**Câu 10:** Người dùng hoàn tất MFA mạnh nhưng không thuộc dự án của tài nguyên. Kết quả authorization là gì?

**Gợi ý:** DENY nếu không có grant khác hợp lệ. MFA tăng độ tin vào phiên, không tạo quyền nghiệp vụ.

## 25. Checklist thiết kế và kiểm tra Subject trong Authorization

- [ ] **Định nghĩa:** Hệ thống đã mô tả rõ subject, identity, account, principal, actor và role chưa?
- [ ] **Loại chủ thể:** Có phân biệt human, contractor, federated user, workload, anonymous và delegation?
- [ ] **Nguồn xác thực:** Subject được hình thành từ token/phiên đã kiểm chứng, không từ tham số client tự khai?
- [ ] **Định danh:** Dùng canonical ID và mapping đáng tin; OIDC xét `(iss, sub)`, không gộp theo email?
- [ ] **Tenant:** Subject membership và resource tenant được kiểm tra ở backend, tránh truy cập chéo tenant?
- [ ] **Account lifecycle:** Account/engagement hiện hành, hiệu lực và trạng thái đình chỉ/Leaver được kiểm tra?
- [ ] **Role/attributes:** Quyền RBAC và thuộc tính ABAC có nguồn có thẩm quyền, phiên bản và độ mới?
- [ ] **Resource/action:** Policy xét tài nguyên và thao tác cụ thể, không chỉ “đã login” hoặc có scope?
- [ ] **PEP/PDP:** Điểm thực thi không bỏ qua quyết định policy; thiếu dữ liệu quan trọng không mở quyền tùy tiện?
- [ ] **OIDC/SAML/SCIM:** Đã kiểm token/assertion và account mapping đúng; provisioning không bị nhầm với authorization?
- [ ] **Direct grants:** Đã xét nhóm lồng nhau, ACL, role cục bộ, token và các nguồn grant ngoài IAM?
- [ ] **Delegation:** Có xác minh actor, represented subject, grant/scope, TTL và ghi log hai bên?
- [ ] **MFA/step-up:** Mức xác thực đáp ứng chính sách nhưng không được thay thế kiểm tra entitlement?
- [ ] **Joiner:** Identity proofing, account activation và role ban đầu đúng người, đúng thời điểm?
- [ ] **Mover:** Tính thêm/thu hồi quyền, xử lý claim/session/cache cũ và đối soát ứng dụng?
- [ ] **Leaver:** Chặn account, phiên/token, entitlement theo engagement và xác minh quyền hiệu dụng?
- [ ] **Service account:** Workload có identity, owner, credential và quyền tối thiểu tách khỏi nhân viên?
- [ ] **Audit:** Có subject, actor nếu ủy quyền, tenant, action, resource, policy và kết quả không lộ secret?
- [ ] **Readback:** Có bằng chứng target thực sự áp quyết định JML, không chỉ ghi nhận lệnh đã gửi?
- [ ] **Ngoại lệ:** Những subject không xác định, account mồ côi hoặc policy không đánh giá được có owner xử lý và thời hạn?

**Ghi nhớ:** **Subject là chủ thể được đánh giá quyền trong một yêu cầu Authorization**, không phải một chuỗi user ID tùy ý do ứng dụng khách cung cấp. Xác định subject đúng đòi hỏi **định danh ổn định, ánh xạ identity–account đáng tin, trạng thái và thuộc tính hiện hành, ranh giới tenant, cùng sự phân biệt người dùng–workload–actor được ủy quyền**. Sau xác thực qua **IdP/SSO**, hệ thống vẫn phải áp **RBAC/ABAC tại tài nguyên**, đồng bộ thay đổi qua **SCIM/API**, bảo vệ phiên/token và đối soát theo **Joiner–Mover–Leaver** để cấp đúng quyền và thu hồi được quyền truy cập tồn dư.
