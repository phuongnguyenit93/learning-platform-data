# Dormant account: phát hiện và xử lý tài khoản ngủ quên trong giám sát danh tính IAM

Một nhân viên đã chuyển phòng ban từ nhiều tháng trước. Tài khoản ứng dụng cũ của họ vẫn ở trạng thái `enabled`, vẫn thuộc nhóm có quyền đọc dữ liệu khách hàng, nhưng hệ thống không thấy lần đăng nhập tương tác nào trong thời gian dài. Có thể đây là tài khoản không còn cần thiết; cũng có thể người dùng truy cập qua SSO và ứng dụng chỉ ghi phiên API chứ không ghi trực tiếp `lastLogin`. Nếu tự động khóa theo một trường thời gian thiếu ngữ cảnh, tổ chức có thể gián đoạn công việc hợp lệ. Nếu bỏ mặc, tài khoản trở thành điểm yếu khó nhận ra.

**Dormant account** (tài khoản không được sử dụng trong một khoảng thời gian theo tiêu chí giám sát) là trạng thái đánh giá về **mức độ hoạt động của một tài khoản**, không phải một loại tài khoản hay trạng thái kỹ thuật được chuẩn hóa giữa mọi hệ thống. Một tài khoản có thể **đang bật nhưng lâu không dùng**; một tài khoản cũng có thể **không có login tương tác nhưng vẫn có API token, session, chứng chỉ hoặc tác vụ nền đang hoạt động**. Vì vậy, phát hiện dormant account cần xác định **mục đích, chủ sở hữu, nguồn chứng cứ hoạt động, ngưỡng thời gian, độ bao phủ quan sát và quyền truy cập còn hiệu lực**, rồi mới chọn biện pháp xử lý.

Bài thuộc chương **Identity monitoring**, chủ đề **Dormant account**, trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Phạm vi mô-đun là quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**: xác minh, tạo tài khoản, cấp quyền, rà soát, thu hồi khi thay đổi vai trò; tích hợp **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và kiểm soát quyền truy cập tồn dư.

Sau bài học, người học có thể:

- Phân biệt **dormant**, **never-used**, **inactive**, **disabled**, **orphaned**, **stale account** và **unused entitlement**.
- Xác định bằng chứng **interactive sign-in, token/API use, session activity, workload authentication và resource action** cho từng loại tài khoản.
- Thiết kế quy tắc phát hiện theo **ngưỡng thời gian, độ nhạy tài nguyên, đặc quyền, ownership, HRIS/JML và độ tin cậy telemetry**.
- Xây dựng quy trình **phát hiện → xác minh → phân loại → thông báo → hạn chế/disable → thu hồi → kiểm chứng → lưu bằng chứng**.
- Kết nối xử lý dormant account với **IdP/SSO/SCIM/PAM**, ứng dụng SaaS, quyền RBAC/ABAC, tài khoản máy và thiết bị.
- Phòng tránh khóa nhầm **service principal theo lịch, tài khoản break-glass, tài khoản dự phòng, invited users chưa kích hoạt, thiết bị offline**.
- Thiết kế **mẫu policy, truy vấn minh họa, giả mã, runbook, tình huống, kiểm thử, KPI và checklist** phục vụ vận hành.

## 1. Dormant account là gì?

Ở mức tổng quát, tài khoản được coi là dormant nếu **không có hoạt động được chấp nhận làm bằng chứng sử dụng** trong một khoảng thời gian do chính sách xác định, tính từ một mốc thời gian đáng tin, **và tổ chức có đủ độ bao phủ quan sát để kết luận**.

Một quy tắc minh họa:

~~~text
Account status: ENABLED
Account purpose: human employee access
Last qualified interactive use: 120 days ago
Observation coverage: sufficient
Dormancy threshold: 90 days (policy example)

=> DORMANT_CANDIDATE
=> Validate lifecycle, ownership, SSO/API activity and exceptions
=> Do not automatically infer "safe to delete"
~~~

**90 ngày hoặc 120 ngày trong bài chỉ là số minh họa**, không phải chuẩn bắt buộc cho tất cả tài khoản, sản phẩm hoặc ngành. Một tài khoản quản trị đặc quyền có thể cần kiểm sớm hơn, trong khi tài khoản phục vụ hoạt động theo quý có thể có chu kỳ hợp lệ khác.

### 1.1. Tại sao tài khoản ngủ quên gây rủi ro?

- **Attack surface tồn dư:** tài khoản vẫn enabled và có thể dùng mật khẩu, session, token hoặc phương thức khôi phục cũ.
- **Privilege creep:** quyền đã cấp trước Mover hoặc dự án cũ vẫn còn dù người dùng không cần.
- **Ownership gap:** account không còn người quản lý, sponsor hoặc workload owner phù hợp.
- **Bỏ sót offboarding:** một tài khoản local/SaaS không được xóa khi nhân viên Leaver.
- **MFA/credential hygiene yếu:** yếu tố xác thực, recovery method hoặc khóa cũ có thể không được rà soát.
- **License và chi phí:** tài khoản không cần thiết có thể tiếp tục tiêu thụ license, nhưng tiết kiệm chi phí không được lấn át kiểm soát nghiệp vụ.
- **Khó phát hiện compromise:** attacker có thể ưu tiên tài khoản ít người theo dõi và đã quên tồn tại.
- **Báo cáo sai:** inventory account enabled có thể làm tưởng tổ chức có nhiều người sử dụng hoặc nhiều owner hợp lệ.

### 1.2. Không phải tài khoản lâu không dùng nào cũng cần xóa

Tài khoản break-glass hợp lệ phải **hiếm khi được dùng**. Workload chạy báo cáo cuối năm có thể không phát sự kiện suốt nhiều tháng. Tài khoản đang chờ Start date của Joiner không nên bị đánh giá theo cùng ngưỡng với nhân viên đã ACTIVE. **Dormancy là một finding cần phân loại, không phải bản án tự động.**

## 2. Phân biệt các khái niệm dễ nhầm

| Khái niệm | Định nghĩa vận hành | Ví dụ | Có thể còn truy cập không? |
| --- | --- | --- | --- |
| **Dormant account** | Không có bằng chứng sử dụng đủ mới theo ngưỡng và policy. | App user enabled, không có qualified activity 120 ngày. | Có thể **có**, nếu enabled/credential còn hợp lệ. |
| **Never-used account** | Chưa từng thấy hoạt động sử dụng hợp lệ kể từ mốc tạo/activation. | User mới được tạo nhưng chưa đăng nhập. | Có thể có nếu account đã enabled. |
| **Inactive account** | Từ đa nghĩa: có thể chỉ không hoạt động hoặc bị vô hiệu tùy sản phẩm. | Vendor dùng `inactive` cho account bị khóa. | Phải kiểm semantics của hệ thống đích. |
| **Disabled/suspended account** | Trạng thái kỹ thuật không cho một số đường đăng nhập theo sản phẩm. | IdP user bị disabled. | **Có thể còn session/token/other paths**. |
| **Orphaned account** | Không còn liên kết owner/Person/Engagement/workload có thẩm quyền. | Local admin còn sau Leaver, không xác định owner. | Có thể có, thường ưu tiên điều tra. |
| **Stale account record** | Metadata không được cập nhật hoặc bản ghi tồn dư không chính xác. | Email cũ, manager cũ, bản ghi trùng. | Tùy account thực tế. |
| **Unused entitlement** | Một quyền cụ thể không được sử dụng dù account có hoạt động. | User login hàng ngày nhưng không bao giờ dùng admin role. | Có; không đồng nghĩa dormant account. |
| **Dormant credential** | Key/token/certificate ít hoặc không thấy dùng. | API key còn hiệu lực nhưng không có API use. | Có thể có và cần quản lý riêng. |
| **Service/workload idle** | Không có activity theo mô hình hoạt động của workload. | Job chỉ chạy mỗi quý. | Tùy lịch và trạng thái deploy. |
| **Deleted/deprovisioned** | Bản ghi/quyền đã được loại bỏ theo phạm vi cụ thể. | App account đã bị xóa. | Vẫn cần kiểm local sessions, backups, copies và credential khác. |

**Quan trọng:** Không suy `disabled=true` từ “không login 90 ngày”; cũng không suy “đã thu hồi mọi quyền” từ việc chuyển trạng thái user sang disabled ở một IdP.

### 2.1. Dormant account khác unused entitlement

~~~text
User U đăng nhập vào ứng dụng mỗi ngày.
Role Reader được dùng mỗi ngày.
Role ProductionAdmin không được dùng 180 ngày.

Account U: ACTIVE, không dormant.
ProductionAdmin entitlement: UNUSED/STALE CANDIDATE.
Action: review/revoke unused admin entitlement, không nhất thiết disable U.
~~~

Tách hai vấn đề sẽ tránh khóa người dùng đang làm việc và giúp **least privilege** chính xác hơn.

### 2.2. Dormant không đồng nghĩa bị xâm nhập

Một account không có login có thể do người dùng không cần ứng dụng. Ngược lại, đột nhiên có login thành công sau 180 ngày im lặng là **tín hiệu đáng xem**, nhưng không tự chứng minh đó là attacker. Cần xác minh user, device, method, resource action và thay đổi nghiệp vụ.

## 3. Dormant account là một finding có ngữ cảnh

Một record dormant hữu ích cần có:

~~~text
who/what:      accountId + principalType + issuer/tenant/application
owner:         Person/Engagement, sponsor or workload ownerTeam
purpose:       reason account exists; expected usage pattern
status:        current enabled/disabled/account lifecycle state
activity:      last qualified use + source + time + coverage
entitlements:  effective RBAC/ABAC/PAM/local grants
risk:          privilege, resource sensitivity, credential/session state
threshold:     policy/rule version, observation window
conclusion:    candidate / verified dormant / exception / unknown
next action:   review, notify, restrict, disable, revoke or retain
evidence:      sourceRefs + queryTime + readback
~~~

### 3.1. Hai câu hỏi không được bỏ qua

1. **Tài khoản có thực sự không được sử dụng?** Cần dữ liệu hợp lệ và đủ nguồn.
2. **Tài khoản có còn được phép tồn tại và giữ quyền không?** Cần HRIS/JML, chủ sở hữu, mục đích, role và risk.

Tài khoản không dormant vẫn có thể phải revoke ngay do Leaver; tài khoản dormant nhưng được phê duyệt để dự phòng có thể phải **giữ, cô lập và kiểm tra định kỳ**, chứ không disable vô điều kiện.

## 4. Phân loại các account cần giám sát

| Loại | Ví dụ | Tín hiệu activity chính | Cần lưu ý |
| --- | --- | --- | --- |
| **Human workforce** | IdP user nhân viên. | Successful interactive auth và app/resource use. | HRIS Engagement, Start/End date, Mover. |
| **Contractor/partner/guest** | Guest SaaS, federated user. | External sign-in, app actions, sponsor check. | Contract expiry, trust issuer, owner. |
| **Privileged account** | Admin riêng, PAM eligible account. | Privileged auth, elevation, resource admin actions. | Dormant account và unused privilege cần tách. |
| **Emergency/break-glass** | Tài khoản khẩn cấp được kiểm soát. | Emergency use / heartbeat tests có kế hoạch. | Hiếm dùng là **bình thường**; ưu tiên kiểm readiness. |
| **Service account** | Batch account, LDAP bind account. | Non-interactive auth, jobs, API calls, service logs. | Không dựa last interactive login. |
| **Workload identity** | Cloud service principal, pod/VM identity. | Token issuance/exchange, workload/API activity. | Deployment, rotation, ownerTeam, lifecycle. |
| **API key/PAT principal** | Token của automation. | API gateway resource use, token lastUsed. | Token có thể dùng dù không có sign-in mới. |
| **Device/machine account** | Domain computer account, client cert. | Machine authentication, heartbeat/management. | Không nhầm device lặng với owner Leaver. |
| **Local application user** | SaaS local fallback admin. | App auth/session/authorization logs. | Có thể bypass IdP và SCIM. |
| **Federated shadow account** | Bản ghi local của IdP user. | RP/SP login và local app activity. | Không thấy ở IdP ≠ không hoạt động. |

### 4.1. Identity inventory phải rộng hơn danh sách IdP

Nếu chỉ lấy danh sách user từ IdP, tổ chức có thể bỏ sót:
- Local account được tạo trực tiếp trong SaaS.
- Admin account phụ, directory cũ hoặc tenant phụ.
- PAT, service principals và shared technical accounts.
- SAML SP/RP sessions độc lập với IdP.
- Service credentials ở CI/CD, cloud hoặc database.

**Nguồn inventory phải gồm những nơi thực sự có thể cấp/giữ quyền truy cập**, có owner và timestamp.

## 5. Hoạt động nào được coi là “sử dụng”?

“Last login” không giống “last meaningful account use”. Cần định nghĩa **qualified activity** cho từng principal type và mục đích.

| Tín hiệu | Có thể chứng minh | Không tự chứng minh |
| --- | --- | --- |
| **Successful interactive sign-in** | User đã xác thực qua đường đó vào thời điểm ghi nhận. | Người dùng đã dùng ứng dụng quan trọng hoặc quyền cụ thể. |
| **Failed sign-in** | Có ai đó/tiến trình đã thử đăng nhập. | Account đang được chủ hợp lệ sử dụng. |
| **MFA challenge issued** | Có bước challenge được khởi tạo. | Factor verified hoặc login success. |
| **IdP SSO login** | Người dùng xác thực ở IdP. | Mọi ứng dụng đã truy cập hoặc local account có hoạt động. |
| **SAML/OIDC RP session created** | Ứng dụng tạo phiên sau federation validation. | Một quyền admin đã được dùng. |
| **API/resource request allowed** | Một credential/session được chấp nhận cho action. | Có người đang tương tác; có thể automation. |
| **Refresh token usage** | Có token family/credential đang được dùng. | Có lần user reauthentication mới. |
| **Background polling/heartbeat** | Tiến trình hoặc thiết bị có kết nối. | Có người thực sự sử dụng tính năng. |
| **Privileged role activation** | Quyền nâng cao được kích hoạt theo cơ chế hỗ trợ. | Đã thực hiện lệnh nhạy cảm ở target. |
| **Actual privileged action** | Resource ghi nhận việc dùng quyền cụ thể. | Một lần login mới ở cùng thời điểm. |
| **Service credential authentication** | Workload/script dùng key/token. | Owner là người đã login. |
| **Job execution record** | Job chạy hoặc gọi service. | Credential được kiểm authorization ở resource nếu chỉ là scheduler ACK. |
| **Device enrollment/check-in** | Endpoint agent còn kết nối. | Account người dùng có hoạt động. |

### 5.1. Phân biệt hai mục tiêu

**Dormant human interactive account** có thể dùng mốc đăng nhập tương tác nếu mục đích là đo tần suất người dùng vào ứng dụng. **Dormant security principal** cần kiểm thêm mọi đường credential có thể làm phát sinh quyền thực tế (session, API key, service login).

Một hệ thống có thể cần **hai chỉ số khác nhau**:

~~~text
lastInteractiveAuthAt
lastEffectiveAccessAt
~~~

Nếu một người không login tương tác 180 ngày nhưng PAT cá nhân vẫn gọi API mỗi đêm:
- Về **interactive use**: không có tương tác gần đây.
- Về **effective access**: không thể coi account hoàn toàn không hoạt động.
- Về **rủi ro**: cần điều tra PAT, owner, phạm vi và lifecycle; có thể đưa ra finding về automation dùng human credential.

### 5.2. Không gộp login thất bại thành account activity

Một attacker thử sai password mỗi ngày không biến tài khoản thành “đang được sử dụng hợp lệ”. **Failed authentication** là tín hiệu điều tra tấn công, không nên reset dormancy clock của account owner.

## 6. LastLogin, lastUsed, lastSeen và lastActivity khác nhau

Một số sản phẩm có trường `lastLogin`, `lastSignIn`, `lastUsed`, `lastSeen`, `passwordLastSet` hoặc `accountCreatedAt`. Không có nghĩa thống nhất giữa vendor.

| Trường | Ý nghĩa có thể có | Cần xác minh trước khi dùng |
| --- | --- | --- |
| **lastLogin** | Lần đăng nhập thành công, có thể chỉ interactive. | Có bao gồm SSO, API, legacy clients không? |
| **lastSignIn** | Một hoặc nhiều loại sign-in. | Interactive/non-interactive và success/failure có tách không? |
| **lastUsed** | Lần credential/app/token được dùng. | Thao tác gì, nguồn nào, có độ trễ/caching không? |
| **lastSeen** | Lần thiết bị/agent kết nối. | Là activity của device hay user account? |
| **lastActivityAt** | Mốc hoạt động theo định nghĩa app. | Có heartbeat/polling/refresh token không? |
| **lastPasswordChange** | Lần thay mật khẩu. | Không phải proof of access. |
| **createdAt** | Lúc account record được tạo. | Có pre-provision, invitation hoặc chưa active không? |
| **disabledAt** | Lúc bị disable theo một nguồn. | Session/token/app-local credential đã bị chặn chưa? |

### 6.1. Bắt buộc có data contract cho từng nguồn

Ví dụ cần hỏi app owner:

~~~text
Field: lastLogin
Source: saas-app-a
Definition: successful interactive login at SP
Does it include OAuth API token calls? NO
Does it include SSO auto-login? YES if SP creates a new session
Timestamp lag: up to 24 hours (example)
Time zone: UTC
Retention: per source policy
Missing value: UNKNOWN / NEVER_OBSERVED? must be distinguished
Owner: application-identity-team
~~~

Không nên lấy `lastLogin = null` làm bằng chứng tài khoản chưa từng được dùng nếu vendor **chưa cung cấp lịch sử hoặc log đã hết retention**.

## 7. Dormancy threshold và cửa sổ quan sát

Một chính sách có thể quy định:

~~~text
Dormancy rule:
    account must be in monitored scope
    AND lastQualifiedActivityAt older than threshold
    AND observationCoverage sufficient
    AND no approved usage exception contradicts this conclusion
    AND not already handled as higher-priority lifecycle/security event
~~~

### 7.1. Ngưỡng phải theo loại tài khoản và risk

| Principal/risk tier | Chính sách minh họa | Tại sao cần khác nhau |
| --- | --- | --- |
| **Employee app account** | Rà soát sau khoảng không dùng theo owner policy. | Có thể là account không còn phục vụ nhiệm vụ. |
| **Privileged account** | Đánh giá sớm hơn hoặc theo chu kỳ review riêng. | Quyền admin tồn dư có mức tác động cao. |
| **Contractor/guest** | Đồng thời kiểm contract/sponsor expiry và inactivity. | End date có thể quan trọng hơn dormancy. |
| **Service principal** | Kiểm lịch chạy job/deployment, owner và API use. | Có thể được dùng định kỳ theo quý/năm. |
| **Break-glass** | Không dùng dormancy để tự khóa; kiểm readiness và misuse. | Hiếm sử dụng là thiết kế có chủ ý. |
| **Invited/not-yet-active** | Dùng thời gian từ invitation/Start date và provisioning rule. | Không nhầm never-used với failed adoption. |
| **Device/machine account** | Dùng heartbeat/machine auth và asset lifecycle policy. | Không có interactive user login. |

**Không có mốc “90 ngày là bắt buộc” áp dụng mọi môi trường.** Ví dụ 30/60/90/180 ngày chỉ có giá trị khi được đưa vào policy phù hợp tài nguyên, lịch nghiệp vụ và độ tin cậy log.

### 7.2. Cửa sổ quan sát phải đủ dài

Nếu tổ chức lưu login log 30 ngày nhưng dùng ngưỡng dormant 180 ngày, kết luận “không thấy login trong 180 ngày” **không được dữ liệu hiện có chứng minh**, trừ khi có nguồn `lastUsed` đáng tin lưu lịch sử dài hơn.

Cần phân biệt:
- **Confirmed no qualifying activity** trong toàn bộ cửa sổ.
- **No observed activity in available data**, chỉ đủ chứng minh một đoạn.
- **Unknown** do coverage/retention/ingestion gap.

### 7.3. Grace period

Một quy trình có thể có giai đoạn thông báo/remediation trước khi disable, nhưng **grace period không được vượt hard revoke của Leaver hoặc security compromise**. Grace chỉ áp khi account vẫn đủ điều kiện và rủi ro chấp nhận được.

## 8. Tạo inventory hợp nhất theo namespace

Một inventory đáng tin không nên gộp tài khoản chỉ vì cùng email hoặc tên hiển thị.

~~~text
AccountIdentity:
  issuerId / directoryId / tenantId
  accountId / stable subjectId
  principalType
  applicationId or scope
  accountState
  createdAt
  lastQualifiedUseAt
  sourceCoverageRef
  personId / engagementId or workloadId / ownerTeam
  entitlementRefs
  session/token/credentialRefs
  riskTier
  dormancyState
~~~

### 8.1. Identity correlation

- **PersonId:** con người được xác định qua nguồn có thẩm quyền.
- **EngagementId:** một quan hệ làm việc/hợp đồng với Start/End date; có thể đổi khi Rehire.
- **AccountId:** tài khoản cụ thể ở IdP hoặc SaaS; một Person có thể có nhiều.
- **Issuer/tenant:** namespace của ID để tránh trùng giữa hệ thống.
- **WorkloadId/ownerTeam:** principal máy độc lập với người tạo nó.
- **DeviceId:** danh tính thiết bị riêng; thiết bị có thể bàn giao.

### 8.2. Khi correlation không chắc

~~~text
accountId = saas-admin-17
ownerPersonId = UNKNOWN
lastInteractiveUse = 170 days ago
accountEnabled = TRUE
role = ADMIN

=> ORPHANED_OR_UNRESOLVED_OWNER + POSSIBLE_DORMANCY
=> HIGH_PRIORITY_REVIEW, not auto-assign to a matching email
~~~

Không nên cập nhật ownership theo suy đoán. Nếu nguồn không liên kết chắc với Person/Engagement, cần triage với app owner/HR/IAM; đồng thời đánh giá rủi ro hiệu lực của quyền admin.

## 9. Kiến trúc tham chiếu cho dormant account monitoring

~~~mermaid
flowchart LR
    HR["HRIS / Contract<br/>Person + Engagement + JML"] --> INV["Identity Inventory & Correlation"]
    IDP["IdP / Directory<br/>Sign-in + user state"] --> INV
    SaaS["SaaS / App local accounts<br/>Sessions + effective use"] --> INV
    PAM["PAM / privileged audit"] --> INV
    M2M["API / STS / workload audit"] --> INV
    ASSET["Device / asset / owner registry"] --> INV
    INV --> QUAL["Activity qualification<br/>coverage + freshness"]
    QUAL --> RULE["Dormancy classifier<br/>risk tier + policy version"]
    RULE --> CASE["Review queue<br/>owner + evidence + deadline"]
    CASE --> IGA["IGA / IdP / SCIM / PAM<br/>Restrict / disable / revoke"]
    IGA --> VERIFY["Target readback & effective access verification"]
    VERIFY --> AUD["Audit / Metrics / Exception review"]
    AUD --> RULE
~~~

### 9.1. Vai trò các lớp

| Lớp | Trách nhiệm | Sai lầm cần tránh |
| --- | --- | --- |
| **Inventory** | Tìm tất cả account/credentials có khả năng truy cập. | Chỉ lấy user IdP rồi bỏ local/SaaS/PAT. |
| **Correlation** | Nối account với Person/Engagement hoặc workload owner. | Dùng email/IP như stable identity. |
| **Activity collector** | Thu thập authentication + API/resource usage đúng nguồn. | Chỉ dùng last interactive login cho service account. |
| **Classifier** | So với threshold và độ đủ của evidence. | `null=old` hoặc missing data=inactive. |
| **Reviewer** | Xác định mục đích, rủi ro, tài khoản cần giữ. | Tự approve ngoại lệ không thời hạn. |
| **Provisioning/Deprovisioning** | Áp thao tác thực tế lên hệ thống. | Chỉ đổi desired state. |
| **Verifier** | Kiểm account, session, token, role/grant đã bị chặn. | Đồng nhất connector ACK với revoke thành công. |
| **Audit/KPI** | Ghi kết quả, exception, coverage và stale state. | Báo 100% khi còn nguồn không quan sát được. |

## 10. Độ tin cậy hoạt động: eventTime, ingestTime, nguồn và freshness

Một account “không có login gần đây” có thể do:
- Thực sự không ai sử dụng.
- Collector mất kết nối hoặc bị rate limit.
- SSO ứng dụng không gửi `lastLogin`.
- API token đang hoạt động nhưng nguồn app không được tích hợp.
- Event được ingest muộn.
- Log đã bị xóa theo retention.
- Tenant/issuer mapping sai.
- Account thực chất được dùng qua kênh local legacy.

### 10.1. Các mốc cần lưu

| Trường | Nghĩa |
| --- | --- |
| **eventTime** | Lúc hành động/xác thực xảy ra theo nguồn. |
| **observedAt** | Lúc sensor/platform quan sát. |
| **ingestedAt** | Lúc pipeline nhận dữ liệu. |
| **effectiveAt** | Mốc hiệu lực thay đổi HRIS/JML nếu có. |
| **evaluatedAt** | Lúc classifier xác định dormant. |
| **lastDataCoverageAt** | Lúc gần nhất nguồn được xác minh đang quan sát đầy đủ. |
| **sourceVersion** | Phiên bản log/cursor/schema/policy. |

### 10.2. Ví dụ dữ liệu đến muộn

~~~text
2026-12-01 08:00  Account used legitimately.
2026-12-01 09:00  Dormancy classifier runs on stale snapshot.
2026-12-01 09:05  Activity event from 08:00 arrives.
~~~

Nếu classifier đã đề xuất disable lúc 09:00 dựa dữ liệu cũ, phải có **pre-action recheck, review/approval hoặc guard điều kiện**. Không để một job phát hiện batch biến account hợp lệ thành disabled khi telemetry vừa cập nhật.

### 10.3. Phân biệt UNKNOWN và DORMANT

Một quy tắc có độ tin cậy tốt trả về các trạng thái như:

~~~text
ACTIVE_OBSERVED
DORMANT_CANDIDATE
DORMANT_VERIFIED
NEVER_USED_CANDIDATE
UNKNOWN_INSUFFICIENT_COVERAGE
EXEMPT_VALIDATED
REVIEW_PENDING
RESTRICTED
DISABLED_PENDING_VERIFICATION
REVOKED_VERIFIED
~~~

Đây là **taxonomy minh họa**; không phải trạng thái chuẩn của SCIM hoặc mọi IdP. Mục đích là ngăn hệ thống gắn nhãn `DORMANT_VERIFIED` khi **chưa đủ chứng cứ**.

## 11. Joiner: never-used account và preboarding

Một Joiner có thể được tạo account vài tuần trước ngày bắt đầu để chuẩn bị thiết bị, MFA và học nội quy.

### 11.1. Các tình huống cần phân biệt

| Tình huống | Nhận định | Hành động minh họa |
| --- | --- | --- |
| Account tạo trước Start date, chưa login. | Đúng kỳ vọng nếu chưa được mở quyền. | Theo dõi preboarding, không coi account bị bỏ quên. |
| Start date đã qua, user chưa activation. | `NEVER_USED_CANDIDATE`. | Liên hệ manager/Helpdesk, kiểm provisioning. |
| Invitation chưa được nhận vì email sai. | Onboarding workflow issue. | Sửa nguồn và gửi lại theo quy trình. |
| Account admin được tạo sớm không có owner. | Owner/privilege risk. | Giới hạn grant, rà soát ngay. |
| User đã SSO nhưng app không cập nhật lastLogin. | Telemetry mismatch. | Điều tra SP activity; không khóa theo null. |

### 11.2. Chỉ báo adoption khác security

Đếm “chưa đăng nhập lần nào” có thể giúp Helpdesk hỗ trợ Joiner, nhưng **không nên tự diễn dịch là nhân viên không làm việc**. IAM chỉ đánh giá **sự cần thiết và an toàn của account**, dựa vào dữ liệu có thẩm quyền và mục tiêu giám sát.

### 11.3. Không tự mở toàn bộ quyền khi login lần đầu

Nếu user được pre-provision role nhạy cảm, một login thành công không tự cho phép mọi action. Cần kiểm **Start date, least privilege, approval, device trust và auth assurance**.

## 12. Mover: tài khoản ứng dụng cũ trở nên dormant

Sau khi Mover, một account từng cần cho vai trò trước đó có thể không còn được dùng, trong khi người dùng vẫn ACTIVE ở IdP và các ứng dụng khác.

### 12.1. Ví dụ

~~~text
User: SRE -> Product (Mover effective: 2026-10-01)
Main SSO: active daily
Production console account: no login after 2026-10-01
Old production-admin grant: still ACTIVE
~~~

Điều cần xử lý không chỉ là account dormant:
1. Kiểm Mover effectiveAt và entitlement theo role mới.
2. Rà soát **old production-admin grant** có phải thu hồi ngay theo policy không.
3. Kiểm session/token/PAM eligibility còn tồn dù không có interactive login.
4. Disable/delete local account nếu không còn mục đích, sau khi có bằng chứng đủ và quy trình an toàn.
5. Xác minh target role/credential/session không còn cho access.

**Không nên chờ ngưỡng dormant 90 ngày mới xử lý quyền cũ lẽ ra phải revoke tại Mover.**

### 12.2. Account dormant và entitlement dormant song song

Account Product mới có thể dùng thường xuyên; account SaaS SRE cũ là dormant; role ProductionAdmin gán vào một account khác cũng không dùng. Cần giám sát **cả account lifecycle và entitlement usage**, với phạm vi/cách đo riêng.

### 12.3. SoD và role changes

Nếu người dùng được giữ account và quyền cũ sau khi chuyển sang vai trò tạo/duyệt giao dịch khác, có thể phát sinh **SoD conflict**. Risk thấp hay account không login gần đây **không loại bỏ** xung đột quyền hiệu lực.


## 13. Leaver: không chờ dormancy threshold để thu hồi quyền

**Leaver** là sự kiện thay đổi tư cách truy cập, không phải sự kiện “lâu không sử dụng”. Nếu HRIS xác nhận termination effectiveAt, chính sách phải xử lý revoke theo thời điểm có hiệu lực. **Không chờ 30/90/180 ngày không login** để chấm dứt quyền của người đã nghỉ.

### 13.1. Các lớp phải xem xét

| Lớp | Trạng thái cần kiểm | Rủi ro tồn dư |
| --- | --- | --- |
| **HRIS/Engagement** | Person/Engagement TERMINATED, effectiveAt đúng. | Email/account khác có thể chưa map Person. |
| **IdP/directory** | Account disabled hoặc quyền đăng nhập mới bị chặn. | IdP SSO session cũ có thể còn. |
| **SCIM/SaaS** | User `active=false`, group removed, local grants xử lý. | App-local account và direct roles chưa đổi. |
| **PAM/JIT** | Role eligibility, elevation/session, vault checkout. | Admin token hoặc SSH session vẫn hoạt động. |
| **API/PAT** | Refresh/access tokens, API keys và PAT cá nhân. | Không có interactive login vẫn gọi API được. |
| **Device/PKI** | Certificate, device owner binding, VPN/ZTNA. | Máy chưa thu hồi hoặc credential vẫn hợp lệ. |
| **Workload ownership** | Job dùng credential người nghỉ. | Automation phụ thuộc tài khoản Leaver. |
| **Resource/PEP** | Quyền thực tế bị từ chối. | Connector ACK không đồng nghĩa effective revoke. |

### 13.2. Tình huống “dormant nhưng đã Leaver”

~~~text
Account A: no sign-in for 120 days
HRIS: termination effectiveAt = 3 months ago
App account: ENABLED
Role: EXPORT_CUSTOMER_DATA

Classification:
  PRIMARY = LEAVER_RESIDUAL_ACCESS
  SECONDARY = DORMANT_ACCOUNT_SIGNAL

Priority:
  Immediate lifecycle/security remediation, not routine 90-day review
~~~

### 13.3. Tài khoản đã disabled vẫn cần xác minh

Một account `disabled` có thể:
- Còn token được phát trước khi disable.
- Còn local application session độc lập.
- Có API key/PAT không đi qua user login.
- Còn direct role/grant trong hệ thống con.
- Chưa được xử lý ở ứng dụng không đồng bộ SCIM.

Do đó **DORMANT → DISABLED** là bước xử lý, không phải bằng chứng đã **REVOKED_VERIFIED**.

## 14. Rehire, account reuse và identity collision

Một người được tuyển lại có thể sử dụng email cũ hoặc account ID được tái kích hoạt theo chính sách. Tuy nhiên:
- **Engagement mới** không tự kế thừa quyền, approval, PAT, role đặc quyền của Engagement cũ.
- Không hồi sinh session cũ chỉ vì account được enabled trở lại.
- Cần identity proofing/rehire workflow, current manager, Start date và least privilege.
- Có thể yêu cầu tạo account mới hoặc rebind theo chính sách hệ thống; phải có lịch sử và chứng cứ.
- Nếu email đã tái cấp cho người khác, không được gộp hai Person chỉ vì email giống nhau.

### 14.1. Ví dụ đánh giá

~~~text
Person P had Engagement E1 (ended).
App account A (linked to E1) was dormant and disabled.
Person P starts Engagement E2 (new hiring).

Not allowed:
  Auto-enable A with all old entitlements and old sessions.

Required:
  Establish current identity + employment,
  approve access for E2,
  verify credentials/factors,
  issue current scoped grants and new sessions,
  preserve audit lineage of E1 separately.
~~~

### 14.2. Tài khoản dùng chung càng khó phân loại

Shared account có thể được nhiều người dùng không có attribution. Dormancy based on `lastLogin` không trả lời **ai** đã sử dụng. Với hệ thống nhạy cảm nên chuyển sang **named accounts hoặc credential checkout có actor, approval, session monitoring**, nếu không khả thi cần owner và kiểm soát bù rõ ràng.

## 15. Privileged dormant accounts và PAM

Tài khoản có đặc quyền cao thường gây rủi ro lớn ngay cả khi không dùng gần đây. Nhưng **PAM có thể làm user admin ít khi login trực tiếp theo thiết kế**; cần phân loại đúng.

### 15.1. Những đối tượng khác nhau

| Đối tượng | Dấu hiệu hoạt động | Quyết định tiềm năng |
| --- | --- | --- |
| **Standing admin account** | Interactive privileged sign-ins, target admin actions. | Rà soát tồn tại và chuyển JIT nếu phù hợp. |
| **PAM-managed vault account** | Checkout/session/credential rotation theo vault. | Kiểm owner, scope, vault state và mục đích. |
| **JIT eligibility** | User có eligibility nhưng không activation. | Đây có thể là **unused entitlement**, không phải account dormant. |
| **JIT activation** | Lần kích hoạt, grant effectiveAt, TTL và target action. | Cần kiểm quyền được sử dụng/đã revoke. |
| **App-local admin** | Login trực tiếp ngoài IdP. | Cần onboard log riêng, ưu tiên orphan review. |
| **Emergency admin** | Hiếm khi dùng, readiness test được phê duyệt. | Giữ theo quy trình emergency, không disable theo ngưỡng chung. |

### 15.2. Không hiểu absence of admin login là không còn quyền

Một user không login admin console 180 ngày nhưng vẫn giữ group production-admin. Điều cần xem:
- Group membership trực tiếp/lồng nhau.
- PAM eligibility và standing role.
- SSH keys, cloud role assumptions, service credentials.
- App-local admin grants.
- Session/token tuổi dài, credential còn hiệu lực.

**Quyền chưa được sử dụng không đồng nghĩa quyền không thể bị khai thác**.

### 15.3. Tài khoản break-glass

Tài khoản break-glass có thể được thiết kế để **không sử dụng trong hoạt động thường ngày**. Nếu detector tự disable sau 90 ngày không login, tổ chức có nguy cơ không khôi phục được IdP/PAM khi outage.

Thay vào đó:
1. Inventory riêng `accountPurpose=EMERGENCY_ACCESS`.
2. Xác minh owner/escrow, credential custody và nơi có thể dùng.
3. Thực hiện **readiness test được phê duyệt** định kỳ, không tạo quyền rộng ngoài policy.
4. Giám sát **mọi lần sử dụng thật**, cảnh báo ngay và yêu cầu post-event review.
5. Áp kiểm soát time-bound và thu hồi sau activation.
6. Kiểm khả năng hoạt động khi IdP bình thường không sẵn sàng, có audit/monitoring bù.

**Exempt khỏi auto-disable vì dormancy không có nghĩa exempt khỏi giám sát và review.**

## 16. Dormant service account, workload identity và API credential

Đối với non-human identities, “lâu không thấy interactive login” thường **không có ý nghĩa**. Hệ thống phải hiểu **job schedule, token issuance, API activity, credential lifetime và ownerTeam**.

### 16.1. Các kiểu non-human principal

- **Directory service account:** ứng dụng dùng LDAP/Kerberos/mTLS hoặc bind credential.
- **Cloud service principal:** workload dùng client credentials/role assumption.
- **Managed/workload identity:** token được issuer cấp dựa trên runtime/context.
- **CI/CD principal:** pipeline deploy, scheduled workflows.
- **Device account:** máy trạm, server, IoT/OT, device certificate.
- **API key/PAT:** credential gắn account con người hoặc principal kỹ thuật.
- **Database technical user:** batch/reporting account không có login web.

### 16.2. Bằng chứng meaningful use cho workload

| Nguồn | Evidence | Không nên suy |
| --- | --- | --- |
| **Authorization server/STS** | Token issued/exchanged cho principal, audience và time. | Token chắc chắn được API chấp nhận. |
| **API gateway/resource** | Token/certificate được chấp nhận cho action. | Có human interactive login. |
| **Scheduler** | Job started/completed, expected cadence. | Credential chắc còn hiệu lực hoặc action được phép. |
| **mTLS/PKI** | Certificate authentication result, expiry/revocation. | Host sạch malware và role đúng. |
| **Deployment/CI** | Workload deployed/removed, run history. | Mọi credential đã được rotate/revoke. |
| **Secrets manager** | Credential read/rotation/lease events. | Credential đã được sử dụng ở target. |
| **Host/EDR** | Health, runtime evidence, service process. | Người tạo workload còn là owner. |

### 16.3. Workload theo mùa

~~~text
Service: annual-audit-export
Expected schedule: once per year (approved calendar)
Last job run: 10 months ago
Last API use: 10 months ago
Credential still valid
OwnerTeam: finance-controls

General 90-day rule => DORMANT_CANDIDATE (false positive risk)
Workload-specific rule =>
    check approved schedule, deployment lifecycle,
    owner attestation, credential hardening and next-run readiness
~~~

Không vì job theo năm mà cấp ngoại lệ vô hạn. Có thể giảm exposure bằng **credential ngắn hạn được cấp gần lúc chạy, default disabled hoặc JIT activation**, dựa khả năng hệ thống.

### 16.4. Service account orphaned

Nếu ownerTeam không còn tồn tại, repo/deployment đã bị xóa và API credential vẫn enabled, đây là **orphan/credential risk**. Điều tra không được chỉ dựa số ngày không dùng: kiểm inventory, cloud IAM grants, secret vault, networking, API logs, phụ thuộc nghiệp vụ và quyền revoke thực tế.

### 16.5. Không giữ PAT cá nhân sau Leaver

Khi nhân viên nghỉ, script tiếp tục dùng PAT của họ không thể được “hợp lệ hóa” bằng cách giữ user account ACTIVE. Chuyển workload sang **principal độc lập, ownerTeam rõ, least privilege, rotation và audit**, rồi revoke PAT cũ có xác minh ở API.

## 17. Guest, contractor và tài khoản đối tác ngủ quên

Tài khoản guest/partner thường có sponsor, endDate hoặc external IdP.

### 17.1. Hai đường cần theo dõi

**Contract lifecycle:**
- Hợp đồng/sponsor còn hiệu lực?
- Access review/approval còn giá trị?
- Quyền và resource scope còn cần thiết?

**Usage:**
- User có SSO/federated sign-in, app session hoặc resource activity không?
- Log có đủ cho tenant của đối tác không?
- External issuer có thay đổi hoặc account bị revoke không?

### 17.2. Không lấy inactivity thay hợp đồng

Nếu contractor endDate đã qua, phải xử lý **Leaver/contractor termination** trước, dù lần login mới nhất là hôm qua. Ngược lại, một external consultant hợp đồng còn hiệu lực nhưng chưa cần dùng ứng dụng hai tháng có thể cần xác nhận sponsor, không tự khóa nếu ngưỡng và hoàn cảnh chưa đáp ứng.

### 17.3. Khó khăn identity correlation

External account có thể được thay đổi NameID/email tại federation. Không tự gộp theo display name, IP hoặc email tương đồng. Dùng issuer/tenant + stable subject khi có, liên kết sponsor/guest record theo nguồn đáng tin.

## 18. Dormant device/machine identity và quyền truy cập từ thiết bị

Một device account có thể không có login con người nhưng vẫn:
- Cung cấp mTLS client authentication.
- Dùng certificate cho VPN/ZTNA.
- Gửi heartbeat hoặc MDM/EDR telemetry.
- Chạy service dưới machine identity.
- Giữ cached user session hoặc credential cục bộ.

### 18.1. Asset state và account state tách biệt

| Device state | Account/credential observation | Điều cần kiểm |
| --- | --- | --- |
| **ASSIGNED** | Không có machine auth mới. | Agent offline hay device không còn dùng? |
| **LOST/STOLEN** | Certificate còn hạn. | Revoke/deny server-side ngay theo policy. |
| **TRANSFERRED** | Credential gắn owner cũ. | Re-enroll/rebind và cleanup local sessions. |
| **RETIRED** | Device account vẫn enabled. | PKI/IdP/MDM cleanup, target deny. |
| **EPHEMERAL VM** | Instance không còn, credential vẫn tồn. | Lease expiry, cloud/workload identity deprovision. |

**Device heartbeat không chứng minh người dùng đang dùng account nghiệp vụ**, và absence of heartbeat không chứng minh mọi credential máy đã vô hiệu.

### 18.2. Liên kết Device trust với Dormancy

Thiết bị dormant hoặc ngừng check-in có thể làm **posture UNKNOWN/STALE**, ảnh hưởng Conditional Access; đây là **điều kiện thiết bị**, không phải bằng chứng user đã nghỉ việc. Nếu device bị LOST, **hard security revoke** phải ưu tiên trước lịch dormancy thông thường.


## 19. IdP, SSO và sai lệch “last login”

### 19.1. Nhiều lớp phiên

~~~text
IdP / Directory login
      ↓
SAML/OIDC federation response
      ↓
Relying Party (SP) local session
      ↓
API access token / app cookie
      ↓
Resource action
~~~

Mỗi lớp có thể ghi mốc riêng:
- IdP `lastSuccessfulSignIn`.
- SP `lastFederatedLogin`.
- App `lastSessionCreated`/`lastAction`.
- OAuth server `lastTokenIssued`/`lastRefresh`.
- Resource `lastAuthorizedAPIUse`.

### 19.2. Ví dụ mismatch

~~~text
IdP last successful login: today 08:00
SaaS A lastLogin: 200 days ago
SaaS A API lastAccess: today 09:00 via PAT
SCIM user active: true
~~~

Kết luận hợp lý:
- **SaaS A interactive use có thể dormant** nếu logs đầy đủ.
- **Account/credential đang có effective API use**, không thể kết luận toàn bộ principal dormant.
- Cần rà soát vì sao PAT tồn tại, chủ thể nào sở hữu, scope nào, JML gì.

### 19.3. Refresh token và access token

Access token có thể tồn tại vài phút, refresh token dài hơn; **token issuance không tương đương user reauthentication mới**. Một account không interactive login vẫn có thể lấy token mới qua refresh. Muốn thu hồi phải xét **token family/session/issuer/resource**, không dựa cookie web tự xóa.

### 19.4. Logout SSO không bảo đảm logout mọi SaaS

Khi IdP session hết hạn hoặc account bị disable, SP local session có thể còn. Khi xử lý dormant account, cần kiểm **application session lifecycle, API calls và resource authorization**, không chỉ IdP audit.

## 20. SCIM provisioning và trạng thái dormant

SCIM hỗ trợ provisioning User/Group giữa hệ thống, thường có thuộc tính như `active`. **Không có một field SCIM chuẩn duy nhất mang ý nghĩa “dormant account theo chính sách doanh nghiệp”**.

### 20.1. Phân biệt phát hiện và xử lý

~~~text
Detection:
  App account exists, enabled, no qualified use 120 days.

Decision:
  Owner confirms no longer required, review approved.

Provisioning:
  IGA/IdP sends SCIM update active=false
  or app-specific disable workflow.

Verification:
  Readback app user state + effective permissions,
  sessions and API credentials according to app capabilities.
~~~

### 20.2. Connector ACK không chứng minh effective access

| Bằng chứng | Có thể chứng minh | Không chứng minh |
| --- | --- | --- |
| SCIM HTTP 204/200 | Provider chấp nhận request ở mức API. | Account/session/token chắc chắn không còn dùng được. |
| SCIM `active=false` readback | Trạng thái user ở provider theo cơ chế đó. | App-local fallback admin/PAT/SSO session đã revoked. |
| Group removed | Membership đã thay đổi theo provider. | Không có direct role, nested group hoặc token stale. |
| IdP account disabled | New sign-in qua IdP bị hạn chế. | Local SaaS account hoặc API key độc lập bị cắt. |
| API PEP DENY | Một đường resource không còn chấp nhận. | Mọi đường ứng dụng và tenant khác đều chặn. |

### 20.3. Dormant accounts nhiều tenant

Một account có thể enabled ở tenant A nhưng disabled ở tenant B. Không được đánh dấu globally revoked chỉ vì đã xử lý một tenant. Inventory/provisioning phải định danh **target system + tenant + accountId + entitlement refs**.

## 21. Đánh giá rủi ro và ưu tiên xử lý dormant account

Dormancy chỉ là một đầu vào; mức ưu tiên nên xét thêm:
- **Có còn enabled?** Credential/role có khả năng đăng nhập?
- **Privilege:** admin, finance approval, export, privileged service account?
- **Resource sensitivity:** production, PII, billing, secrets, customer data.
- **Ownership:** có người/chủ hệ thống được xác minh hay orphaned?
- **JML:** Leaver/Mover/contract expired?
- **Credential:** mật khẩu, session, PAT, certificate, SSH key, refresh token.
- **Security telemetry:** suspicious use, failed attempts, leaked credentials.
- **Observation confidence:** độ đủ activity logs/retention.
- **Business criticality:** service outage risk khi disable.
- **Exception:** có emergency/seasonal use được phê duyệt không?

### 21.1. Priority matrix

| Kết hợp | Mức ưu tiên minh họa | Hành động |
| --- | --- | --- |
| Leaver + enabled admin/app credential. | Critical, theo lifecycle/security policy. | Chặn/điều tra ngay, không chờ dormancy review. |
| Orphan + privileged + credentials có hiệu lực. | High. | Xác định owner, hạn chế rủi ro, review/revoke có kiểm. |
| Human app account dormant, không privileged, owner hợp lệ. | Routine/Medium. | Notify owner, xác minh need, xử lý theo policy. |
| Approved break-glass account hiếm khi dùng. | Special class. | Readiness test, monitor usage, không auto-disable. |
| Seasonal workload còn owner, lịch hợp lệ. | Exception/Review. | Xác thực purpose, next use, giảm credential exposure. |
| Logs thiếu toàn bộ 90 ngày. | Unknown/data-quality risk. | Khôi phục coverage, không auto disable từ absence of evidence. |

### 21.2. Điểm rủi ro không tự tạo thẩm quyền

Một score cao có thể ưu tiên investigation, nhưng **hành động disable production service** vẫn cần biết phụ thuộc và thẩm quyền (trừ trường hợp security incident với emergency response đã ủy quyền). Điểm thấp cũng không cho phép giữ account của Leaver có quyền sensitive.

## 22. Luồng xử lý end-to-end có phê duyệt và xác minh

~~~mermaid
flowchart TD
    A["Inventory accounts + credentials + owners"] --> B["Collect qualified usage & coverage"]
    B --> C{"Coverage sufficient?"}
    C -->|"No"| U["UNKNOWN / source gap<br/>owner + remediation"]
    C -->|"Yes"| D["Classify dormancy + lifecycle + risk"]
    D --> E{"Hard revoke? Leaver / confirmed compromise"}
    E -->|"Yes"| F["Security/JML immediate revoke workflow"]
    E -->|"No"| G{"Exception / special account?"}
    G -->|"Yes"| H["Verify purpose, approval, expiry, readiness"]
    G -->|"No"| I["Notify owner + confirm business need"]
    I --> J{"Still needed?"}
    J -->|"Yes"| K["Reconfirm access / narrower scope / review date"]
    J -->|"No"| L["Controlled restriction / disable / deprovision"]
    F --> M["Revoke credentials + session/grants as applicable"]
    L --> M
    M --> N["Target readback + effective access verification"]
    N --> O{"All required paths verified?"}
    O -->|"Yes"| P["Close with audit and evidence"]
    O -->|"No"| Q["Exception / incident with owner and deadline"]
    Q --> N
    H --> P
    K --> P
~~~

### 22.1. Bước 1 — Discover và snapshot

Lấy account inventory theo system/tenant, principalType, account status, entitlements, owner và associated credentials. **Chỉ đọc các thông tin được ủy quyền**, tuân thủ chính sách bảo mật dữ liệu.

### 22.2. Bước 2 — Qualify activity

Thu và chuẩn hóa sign-in/session/API/privileged/workload evidence theo account. Dùng **source provenance, eventTime, retention và completeness** để quyết định có đủ cơ sở nhận diện dormant không.

### 22.3. Bước 3 — Correlate JML

Nối account với Person/Engagement hoặc workload owner. **Leaver/compromise phải đi đường xử lý khẩn**; dormant thông thường không được trì hoãn hard revoke.

### 22.4. Bước 4 — Risk and business validation

Gửi finding tới owner/manager/sponsor đã được xác minh; kiểm phụ thuộc, lịch sử dự án, lý do cần giữ, license và khả năng thay bằng least privilege.

### 22.5. Bước 5 — Controlled action

Tùy policy: remove unused role, restrict login, suspend, disable, revoke credentials/token, hoặc deprovision. **Không có thao tác nào phù hợp cho mọi account**.

### 22.6. Bước 6 — Verify

Đọc lại target account/grants và kiểm session/token/API/PAM paths theo khả năng. Ghi `VERIFIED` cho những đường đã kiểm; `UNVERIFIABLE` hoặc `PENDING` cho phần còn tồn.

## 23. Thông báo owner, phê duyệt và ngoại lệ có hạn

Dormant monitoring thường ảnh hưởng người dùng hợp lệ, nên cần **workflow có accountability**.

### 23.1. Mẫu thông tin trong review request

~~~text
Finding ID: DORM-2026-0018
Source: saas-finance-app / tenant-a / account-194
PrincipalType: HUMAN
Person/Engagement: verified current employee (reference only)
Last qualified interactive use: 2026-07-01
Last effective API use: none observed in complete window
Observation coverage: 2026-07-01 through 2026-12-01
Entitlements: Reader + Export (Export unused)
Risk tier: Medium/High because data export permission
Suggested action: remove unused Export role; verify need for account
Owner: application manager
Review dueAt: according to organization policy
Evidence: source snapshot refs and detector version
~~~

### 23.2. Kết quả reviewer nên có enum rõ

| Decision | Ý nghĩa | Điều kiện |
| --- | --- | --- |
| **CONFIRM_NO_LONGER_REQUIRED** | Account/quyền không còn cần. | Chuyển remediation theo quy trình. |
| **KEEP_WITH_BUSINESS_JUSTIFICATION** | Vẫn cần cho nhiệm vụ hợp lệ. | Scope, thời hạn review lại, least privilege. |
| **APPROVED_EXCEPTION** | Account đặc biệt như seasonal/break-glass. | Reason, owner, compensating controls, expiry. |
| **TRANSFER_OWNER** | Người chịu trách nhiệm đổi. | Kiểm nguồn và transfer, không tự đổi bằng email. |
| **NEEDS_INVESTIGATION** | Thiếu thông tin hoặc nghi rủi ro. | Giao ticket và SLA, không auto ALLOW. |
| **REJECT_FINDING_DATA_ERROR** | Dữ liệu quan sát sai. | Lưu bằng chứng, sửa pipeline, rerun. |

### 23.3. Không để quá hạn tự động thành approved

Nếu reviewer không trả lời, state nên là `OVERDUE/ESCALATED`, và biện pháp cần theo policy/risk tier. **Silence không phải xác nhận tiếp tục giữ quyền**, cũng không phải bằng chứng đã có quyền disable service quan trọng tùy tiện.

### 23.4. SoD và self-approval

Người sở hữu admin account hoặc requester có thể không được **tự phê duyệt giữ quyền đặc biệt**. Kiểm Person/Engagement canonical thay vì coi hai account IDs khác nhau là hai người độc lập.

## 24. Disable, revoke, delete và archive có tác dụng khác nhau

| Hành động | Dùng khi nào | Không đủ cho |
| --- | --- | --- |
| **Remove entitlements** | Account còn cần, role cụ thể không dùng. | Account/session credential vẫn có thể đăng nhập. |
| **Suspend/Disable** | Tạm chặn đường login/provisioned account. | Token/session/app-local credential còn hoạt động. |
| **Revoke sessions** | Ngăn active sessions tiếp tục. | PAT/API keys và role direct grant khác. |
| **Revoke/rotate credentials** | Ngăn password/key/token/certificate cũ. | Không tự xóa mọi entitlement. |
| **Deprovision/Delete user** | Không còn nhu cầu account, theo retention/regulation. | Có thể ảnh hưởng audit identity reference và downstream data. |
| **Archive record** | Giữ chứng cứ governance đúng thời hạn. | Không có nghĩa credential đã bị revoke. |
| **Transfer workload ownership** | Service vẫn cần nhưng owner/credential không phù hợp. | Chưa đủ nếu khóa cũ còn hiệu lực. |
| **Quarantine/Restrict** | Có rủi ro, cần điều tra hoặc giảm phạm vi. | Không phải trạng thái cuối nếu quyền dư chưa đóng. |

### 24.1. Không xóa vội khi còn dependencies

Trước khi disable/delete service principal hoặc account hệ thống:
- Kiểm scheduled jobs, integrations, certificates và downstream dependencies.
- Có owner kỹ thuật xác nhận và đường thay thế.
- Kiểm quy tắc retention/audit và chính sách recovery.
- Lên thời điểm thay đổi, rollback phù hợp và monitoring.
- Xử lý credentials/roles tồn dư, không chỉ đổi tên principal.

### 24.2. Delete không luôn giúp audit tốt hơn

Nếu xóa account khiến log cũ mất identity reference hoặc không thể tra cứu incident, hệ thống có thể lưu **tombstone/audit reference được bảo vệ** đúng retention mà không giữ credential hay quyền. Chính sách xóa dữ liệu phải tính tới nghĩa vụ liên quan và quyền riêng tư, không dùng retention vô hạn.


## 25. Khôi phục hoặc tái kích hoạt tài khoản dormant

Một tài khoản được disable vì dormancy có thể cần được sử dụng trở lại. **Enable lại account không nên là thao tác đảo trạng thái `disabled=false` đơn giản**.

### 25.1. Các điều kiện trước khi re-enable

1. **Xác minh chủ thể:** Person/Engagement hoặc workload/ownerTeam hiện tại có thẩm quyền.
2. **Xác nhận business need:** action/resource nào cần, thời hạn bao lâu.
3. **Kiểm lifecycle:** không còn Leaver, Mover thiếu role, contract expired, incident hold.
4. **Rà soát entitlement:** chỉ cấp lại role tối thiểu, không restore blanket grants.
5. **Khôi phục credential an toàn:** reset/rotate mật khẩu, API key, certificate hoặc factor theo policy; không dùng secret cũ bị nghi lộ.
6. **MFA, device trust và session:** áp yêu cầu xác thực hiện hành, không mở lại old session/token.
7. **Approval/SoD:** đặc biệt với account privileged hoặc truy cập tài chính.
8. **Ghi audit:** ai yêu cầu/duyệt, target, reason, policy và verified result.

### 25.2. Đặc biệt với Rehire

Nếu người đã nghỉ trở lại, workflow **Joiner/Rehire** tạo tư cách mới; không mặc định re-enable old app account cùng toàn bộ quyền E1. Nếu không thể thay account vì ràng buộc kỹ thuật, phải có **explicit rebind và full entitlement review**.

### 25.3. Workload reactivation

Một service principal dormant chỉ nên được mở lại sau khi:
- OwnerTeam/deployment hợp lệ xác nhận.
- Credential mới được cấp hoặc rotated.
- Scope/issuer/tenant/resource được kiểm.
- Dependency tests trong staging khi khả thi.
- Token cũ không được dùng để mở lại đường truy cập không được kiểm soát.

## 26. Mẫu policy YAML cho dormant account monitoring

~~~yaml
# Minh họa nội bộ; không phải schema chuẩn của SCIM, IGA hoặc một SIEM.
policyId: IDENTITY-DORMANCY-MONITORING
policyVersion: 4
scope:
  accountTypes:
    - HUMAN_EMPLOYEE
    - CONTRACTOR
    - PRIVILEGED
    - WORKLOAD
  excludesFromAutomaticDisable:
    - EMERGENCY_ACCESS
    - APPROVED_SEASONAL_WORKLOAD

activityEvidence:
  requireTrustedSource: true
  requireCompleteObservationWindow: true
  acceptedHumanSignals:
    - SUCCESSFUL_INTERACTIVE_AUTH
    - QUALIFIED_APP_ACTIVITY
  acceptedWorkloadSignals:
    - AUTHORIZED_API_USE
    - VERIFIED_WORKLOAD_RUN
  ignoredForHumanUse:
    - FAILED_LOGIN
    - MFA_CHALLENGE_SENT
    - PASSIVE_DEVICE_HEARTBEAT

classification:
  exampleHumanThresholdDays: 90
  examplePrivilegedReviewDays: 30
  whenNoActivityButCoverageMissing: UNKNOWN_INSUFFICIENT_COVERAGE
  whenNeverUsedAndBeforeStartDate: PREBOARDING
  whenLeaver: ROUTE_TO_JML_REVOKE
  whenConfirmedCredentialCompromise: ROUTE_TO_SECURITY_RESPONSE

review:
  requireOwnerConfirmation: true
  requireIndependentApprovalForPrivilegedRetention: true
  reviewDueBy: POLICY_DEFINED_SLA
  onOverdue: ESCALATE_PER_RISK
  exceptionRequires:
    - purpose
    - owner
    - scope
    - expiresAt
    - compensatingControls

remediation:
  actions:
    - REMOVE_UNUSED_ENTITLEMENTS
    - RESTRICT
    - DISABLE
    - REVOKE_CREDENTIALS_AND_SESSIONS
    - DEPROVISION_WHEN_APPROVED
  requireTargetReadback: true
  unresolvedTargets: OPEN_EXCEPTION_WITH_OWNER
audit:
  recordPolicyVersion: true
  redactSecrets: true
  distinguishRequestedAcknowledgedVerified: true
~~~

### 26.1. Đọc đúng phạm vi mẫu

- Các số ngày trong `exampleHumanThresholdDays` chỉ minh họa, phải được phê duyệt theo risk và ngành nghề.
- `APPROVED_SEASONAL_WORKLOAD` không được tự exempt nếu chưa có owner/approval hiện hành.
- `PREBOARDING` không đồng nghĩa được mở quyền production.
- `ROUTE_TO_JML_REVOKE` phải ưu tiên hơn dormancy review.
- Các hành động remediation **không được tự động thực thi từ ví dụ** mà thiếu workflow/authorization.

## 27. Pseudocode phân loại dormant account có kiểm coverage

~~~text
classifyDormancy(account, now):
    inventory = loadAccountWithTenantIssuerAndOwner(account)
    lifecycle = loadAuthoritativeLifecycle(inventory)
    permissions = loadEffectiveEntitlements(inventory)

    if lifecycle.isLeaverOrExpiredContract(now):
        return LEAVER_REVOKE_PRIORITY
    if confirmedCredentialCompromise(inventory):
        return SECURITY_RESPONSE_PRIORITY

    if account.purpose == EMERGENCY_ACCESS:
        return EMERGENCY_READINESS_REVIEW

    rule = loadVersionedDormancyRule(
        account.principalType,
        permissions.riskTier,
        account.purpose
    )

    if lifecycle.isPreboardingBeforeStartDate(now):
        return PREBOARDING_TRACKING

    signals = collectQualifiedActivityEvidence(
        account,
        rule.observationWindow,
        rule.acceptedSignalTypes,
        trustedSourcesOnly=true
    )

    if not signals.coverageComplete:
        return UNKNOWN_INSUFFICIENT_COVERAGE

    if account.principalType in [SERVICE, WORKLOAD, DEVICE]:
        if not validatePurposeAndExpectedCadence(account):
            return OWNER_DEPENDENCY_REVIEW

    lastUse = signals.latestQualifiedEventTime
    if lastUse is null:
        baseline = authorizedActivationOrCreationDate(account)
        if baseline is unknown:
            return UNKNOWN_INSUFFICIENT_CONTEXT
        if now - baseline < rule.neverUsedGrace:
            return NOT_YET_DUE
        return NEVER_USED_CANDIDATE

    if now - lastUse >= rule.dormancyThreshold:
        return DORMANT_CANDIDATE

    return ACTIVE_OBSERVED
~~~

**Đây là giả mã**, không phải chương trình chạy trực tiếp. Policy triển khai cần xử lý eventTime/effectiveAt, timezone, concurrency, retries, evidence de-duplication, account scopes và trạng thái khác nhau giữa nguồn. `DORMANT_CANDIDATE` là một **đầu vào của review**, không tự đồng nghĩa quyền disable đã được phê duyệt.

### 27.1. Pre-action recheck

Một job scan có thể tạo finding lúc 08:00 nhưng đến 16:00 mới thực hiện disable. Phải kiểm lại:
- Account ID/tenant vẫn là cùng principal.
- Owner/Engagement và purpose chưa đổi.
- Có hoạt động hợp lệ mới không.
- Approval còn thời hạn và đúng request version không.
- Có lease/job critical mới phát sinh không.
- Có security event nào cần chuyển workflow ưu tiên cao hơn không.

### 27.2. Không tự reset dormancy bởi failed login

Nếu attacker thử mật khẩu sai sau 90 ngày, `lastFailedAttemptAt` có thể mới nhưng `lastQualifiedUseAt` vẫn cũ. Cần **một finding security riêng**; việc có attempts không làm account trở thành “đang được chủ hợp lệ dùng”.

## 28. SQL minh họa để tìm ứng viên dormant

Giả sử có **bảng snapshot/warehouse đã chuẩn hóa** với:
- `accounts` gồm `tenant_id, account_id, principal_type, created_at, enabled, owner_id, account_purpose`.
- `qualified_activity` gồm `tenant_id, account_id, event_time, event_type`, chỉ chứa sự kiện **được xác minh là activity hợp lệ**.
- `coverage_windows` chứng minh các source bắt buộc có dữ liệu đầy đủ trong cửa sổ theo policy.

~~~sql
-- SQL minh họa theo PostgreSQL; không chạy trực tiếp nếu chưa có
-- schema thực, kiểm quyền truy cập và policy threshold đã phê duyệt.
WITH last_qualified_use AS (
    SELECT
        tenant_id,
        account_id,
        MAX(event_time) AS last_use_at
    FROM qualified_activity
    WHERE event_type IN (
        'SUCCESSFUL_INTERACTIVE_AUTH',
        'QUALIFIED_APP_ACTIVITY'
    )
    GROUP BY tenant_id, account_id
)
SELECT
    a.tenant_id,
    a.account_id,
    a.principal_type,
    a.owner_id,
    a.created_at,
    l.last_use_at,
    c.coverage_start,
    c.coverage_end
FROM accounts AS a
LEFT JOIN last_qualified_use AS l
    ON l.tenant_id = a.tenant_id
   AND l.account_id = a.account_id
JOIN coverage_windows AS c
    ON c.tenant_id = a.tenant_id
   AND c.account_id = a.account_id
WHERE a.enabled = TRUE
  AND a.principal_type = 'HUMAN_EMPLOYEE'
  AND a.account_purpose <> 'EMERGENCY_ACCESS'
  AND c.coverage_start <= (CURRENT_TIMESTAMP - INTERVAL '90 days')
  AND c.coverage_end >= CURRENT_TIMESTAMP
  AND (
        (l.last_use_at IS NOT NULL
         AND l.last_use_at < (CURRENT_TIMESTAMP - INTERVAL '90 days'))
        OR
        (l.last_use_at IS NULL
         AND a.created_at < (CURRENT_TIMESTAMP - INTERVAL '90 days'))
      );
~~~

### 28.1. Cảnh báo quan trọng về truy vấn

1. Đây chỉ tạo **candidate list**, chưa kiểm HRIS/Leaver, Mover, Start date, business exception, approver, indirect API use hoặc actual resource grants.
2. `coverage_windows` ở đây là một **bảng khái niệm**; sản phẩm thật phải chứng minh không có khoảng trống, source đủ cho từng app, không phải chỉ có hai timestamps.
3. Query chỉ chọn `HUMAN_EMPLOYEE`: **không dùng cho workload hoặc break-glass**.
4. `last_use_at IS NULL` không tự có nghĩa never-used nếu hoạt động không nằm trong pipeline hoặc mất retention.
5. `CURRENT_TIMESTAMP` và so sánh timestamp cần chuẩn timezone/clock.
6. Cần xử lý lịch sử account đổi ID, account tái tạo, tenant migration và late events.
7. Nếu account được tạo trước Start date, thời gian từ `created_at` chưa phù hợp để kết luận dormant.
8. Tài khoản bị disabled trong một target nhưng enabled ở target khác cần inventory từng target.

### 28.2. Vì sao không viết DELETE ngay trong SQL?

Một báo cáo detection không nên thực hiện `DELETE FROM accounts WHERE last_use_at < ...`. Quy trình xóa account cần **authorization, dependency analysis, retention, audit và target verification**. Truy vấn dùng để **phân loại và kiểm tra**, không phải cấp quyền xóa.

## 29. Mô hình dữ liệu finding và remediation

### 29.1. Các thực thể nên tách

| Entity | Trường tiêu biểu | Vai trò |
| --- | --- | --- |
| **AccountRecord** | accountId, issuer/tenant, type, enabled, createdAt. | Đối tượng kiểm tra. |
| **OwnerBinding** | personId/engagementId hoặc ownerTeam, validFrom/To. | Trách nhiệm và tư cách. |
| **ActivityEvidence** | source, eventType, eventTime, evidenceRef. | Chứng cứ về sử dụng. |
| **CoverageCertificate** | source, window, freshness, gaps, validatedAt. | Chứng minh có/không đủ dữ liệu. |
| **EntitlementSnapshot** | resource, role, source, effectiveAt/version. | Rủi ro quyền hiện có. |
| **DormancyFinding** | findingId, threshold, lastUse, state, riskTier, policyVersion. | Quyết định phân loại. |
| **ReviewDecision** | reviewer, outcome, scope, expiry, reason, SoD check. | Phê duyệt/ngoại lệ. |
| **RemediationTask** | target, requestedAt, acknowledgedAt, verifiedAt, result. | Hành động trên hệ thống đích. |
| **Exception** | owner, residualRisk, mitigation, dueAt, status. | Đường chưa thể khép kín. |
| **AuditEvent** | actor, action, source/target refs, timestamp. | Truy vết và kiểm toán. |

### 29.2. JSON giả định

~~~json
{
  "eventType": "DORMANT_ACCOUNT_FINDING",
  "schemaVersion": "dormancy-finding-v1",
  "findingId": "dorm-20261201-0018",
  "evaluatedAt": "2026-12-01T10:00:00+07:00",
  "tenantId": "tenant-a",
  "applicationId": "finance-saas",
  "accountId": "acct-194",
  "principalType": "HUMAN",
  "personId": "person-1042",
  "engagementId": "EMP-5812",
  "accountEnabled": true,
  "createdAt": "2025-11-01T09:00:00+07:00",
  "lastQualifiedUseAt": "2026-07-01T13:00:00+07:00",
  "activityEvidenceRefs": ["activity-ref-881"],
  "observationCoverage": {
    "start": "2026-07-01T00:00:00+07:00",
    "end": "2026-12-01T10:00:00+07:00",
    "complete": true,
    "sources": ["saas-auth", "saas-api"]
  },
  "policyId": "IDENTITY-DORMANCY-MONITORING",
  "policyVersion": 4,
  "thresholdDays": 90,
  "dormancyState": "DORMANT_CANDIDATE",
  "riskTier": "HIGH",
  "entitlementRefs": ["finance-export-grant"],
  "reviewOwner": "finance-application-owner",
  "nextAction": "OWNER_REVIEW",
  "evidenceIntegrityRef": "evidence-bundle-772"
}
~~~

**JSON giả định**, không phải chuẩn SCIM/IdP. Account ID và timestamp chỉ để minh họa. Không nên lưu raw credential/token trong finding; chỉ lưu reference đủ để điều tra có kiểm soát.

### 29.3. Các trạng thái remediation cần tách

~~~text
FINDING_CREATED
OWNER_REVIEW_PENDING
OWNER_CONFIRMED_NO_NEED
DISABLE_REQUESTED
DISABLE_ACKNOWLEDGED
ACCOUNT_DISABLED_READBACK
CREDENTIALS_REVOKED_READBACK
SESSION_ACCESS_VERIFIED_DENIED
REVOKED_VERIFIED
CLOSED
~~~

Không tự đi thẳng từ `DISABLE_REQUESTED` sang `CLOSED`. Với app không hỗ trợ API readback, sử dụng `UNVERIFIABLE` với risk owner và biện pháp giảm thiểu.

## 30. Case study 1 — SSO hoạt động nhưng app lastLogin không cập nhật

**Bối cảnh giả định:** user Hà ACTIVE, IdP có login hàng ngày. SaaS A ghi `lastLogin` cách đây 150 ngày nên detector đề xuất disable. App owner cho biết những truy cập gần đây dùng SSO auto-session, còn source `lastLogin` chỉ cập nhật khi login bằng password local.

### 30.1. Dấu hiệu

| Nguồn | Quan sát |
| --- | --- |
| **HRIS** | Hà đang ACTIVE. |
| **IdP** | Login mỗi ngày. |
| **SaaS `lastLogin`** | 150 ngày trước. |
| **SaaS API/action audit** | Có hoạt động read report trong tuần. |
| **Observation coverage** | App local password log đủ nhưng không bao phủ toàn bộ access. |

### 30.2. Kết luận đúng

- Không kết luận **SaaS A account hoàn toàn dormant** từ một field.
- Có thể xác định **không có local-password login gần đây**, nhưng SSO/API activity là sử dụng thực tế.
- Sửa data contract hoặc kết hợp app action logs để nhận diện qualified use.
- Không disable người dùng chỉ vì một snapshot sai ngữ nghĩa.

### 30.3. Bài học

**LastLogin phụ thuộc nguồn và giao thức.** Mỗi vendor định nghĩa một kiểu activity; phải có evidence coverage và hiểu đúng trường trước khi thực hiện disable tự động.

## 31. Case study 2 — Leaver còn tài khoản local admin bỏ quên

**Bối cảnh giả định:** nhân viên Bình nghỉ việc ba tháng trước. IdP account đã disabled, nhưng hệ thống quản trị SaaS vẫn giữ local admin `admin-binh` enabled. Không có login 120 ngày.

### 31.1. Phân loại

~~~text
Account: admin-binh (local SaaS)
HRIS: Engagement TERMINATED three months ago
Last login: 120 days ago
Role: SUPER_ADMIN
Current state: ENABLED

Priority: LEAVER_RESIDUAL_PRIVILEGED_ACCESS
Secondary signal: dormant
~~~

### 31.2. Xử lý

1. Identity mapping chắc chắn tới Person/Engagement Bình.
2. Ưu tiên incident/JML revoke theo chính sách, không chờ review dormant 90 ngày.
3. Kiểm session/PAT/local password/recovery methods và direct grants.
4. Disable/revoke theo thẩm quyền có hiệu lực.
5. Readback và xác minh admin API/login không còn chấp nhận credential trong phạm vi.
6. Đánh giá truy cập/hành động từ termination effectiveAt đến khi chặn.
7. Ghi residual-access window, root cause và sửa inventory/connector.

### 31.3. Bài học

Tài khoản dormant có thể là **triệu chứng của offboarding thiếu hoàn chỉnh**; không nên chỉ đặt tên ticket “unused account cleanup” khi có account Leaver mang quyền cao.

## 32. Case study 3 — Workload báo cáo theo quý bị gắn nhầm dormant

**Bối cảnh giả định:** service principal `quarterly-report-runner` chạy cuối mỗi quý. Sau hai tháng không có activity, detector chung đề xuất khóa vì ngưỡng 60 ngày.

### 32.1. Kiểm bằng chứng

- Scheduler có lịch quý được owner phê duyệt và deploy còn hợp lệ.
- Last API use là kỳ trước, các log đúng tần suất.
- OwnerTeam và dependency graph đầy đủ.
- Credential/certificate có hạn và trong kho an toàn, chưa nghi compromise.
- Privileges chỉ cho một báo cáo cụ thể; không có admin scope.
- Có thể dùng JIT/short-lived credential thay vì giữ secret dài hạn.

### 32.2. Quyết định đúng

**Không auto-disable chỉ theo rule của human account.** Có thể giữ trong nhóm `APPROVED_PERIODIC_WORKLOAD` có expiry/review date, giám sát lần chạy kế tiếp, và giảm exposure bằng token/credential ngắn hạn. Nếu job bị decommission thì phải revoke dù chưa chạm threshold.

### 32.3. Bài học

**Expected cadence và business purpose là thành phần thiết yếu** để phân loại dormant đối với machine identities.


## 33. Case study 4 — Break-glass bị khóa bởi job dormant

**Bối cảnh giả định:** tổ chức có tài khoản khẩn `break-glass-1` dùng khi IdP thường gặp sự cố. Account hiếm khi đăng nhập; một automation dùng cùng ngưỡng 90 ngày của nhân viên và tự disable vì “không sử dụng”.

### 33.1. Hậu quả

Trong một outage, đội IAM không thể truy cập đường phục hồi vì break-glass đã bị disabled; muốn mở lại phải truy cập chính IdP đang lỗi. Đây là **vòng phụ thuộc gây rủi ro continuity**, không phải thành tựu làm sạch account.

### 33.2. Thiết kế đúng

1. Tách purpose `EMERGENCY_ACCESS` trong account catalog.
2. Không áp auto-disable dormancy của user thường.
3. Yêu cầu owner, escrow, credential custody, MFA/kiểm soát phù hợp khả năng khẩn.
4. Thực hiện readiness tests được phê duyệt và có audit, không biến mọi test thành permanent privileged session.
5. Mỗi lần sử dụng thật cần alert, actor attribution, incidentRef và hậu kiểm độc lập.
6. Theo dõi certificate/key expiry, rotation và việc target thật còn nhận credential.
7. Đóng phiên/rotate/revoke sau sự kiện theo policy, bảo đảm quyền không còn tồn dư.

### 33.3. Bài học

**“Ít dùng” có thể là trạng thái mong muốn** của tài khoản khẩn. Kiểm soát đúng là **readiness + usage detection + governance**, không tự xóa vì im lặng.

## 34. Case study 5 — Người tái tuyển và tài khoản chưa từng kích hoạt

**Bối cảnh giả định:** Lan nghỉ việc tháng 6, sau đó tái tuyển tháng 12. Một app cũ còn account cùng email, `lastLogin` null vì vendor vừa thay logging. IGA thấy Lan mới ACTIVE nên dự kiến re-enable app account cũ với nhóm quyền trước đây.

### 34.1. Những rủi ro bị che

| Dữ liệu | Điều cần lưu ý |
| --- | --- |
| **Same email** | Không chứng minh cùng Engagement hay owner hiện tại. |
| **New HRIS Engagement** | Entitlement cần được tính theo nhiệm vụ mới. |
| **Old app account** | Có thể chứa direct roles, PAT, old factors và recovery settings. |
| **`lastLogin=null`** | Có thể do data migration/retention, không chắc never-used. |
| **Old SSO sessions** | Không được hồi sinh khi app account re-enabled. |
| **New manager/department** | Có thể yêu cầu SoD/approval mới. |

### 34.2. Quyết định

- Xác minh canonical Person và Engagement mới, không chỉ email.
- Coi account cũ là **identity/linking review** và credential risk nếu còn secrets.
- Áp role từ E2 theo least privilege, loại bỏ direct grants không được duyệt.
- Cấp factor/credential hiện hành, tạo phiên mới, không kích hoạt lại token family cũ.
- Kiểm target readback và quyền thực tế, giữ audit lịch sử E1 tách biệt.

### 34.3. Bài học

**Dormancy finding, never-used state và rehire authorization là các vấn đề khác nhau**. Một giá trị null không được dùng để bỏ qua toàn bộ vòng đời danh tính.

## 35. Threat model, bảo vệ quyền riêng tư và rủi ro trong việc tự động hóa

### 35.1. Threat model

| Rủi ro | Biểu hiện | Kiểm soát |
| --- | --- | --- |
| **Account forgotten** | Account enabled lâu không dùng, role nhạy cảm. | Inventory + least privilege review. |
| **Offboarding gap** | Leaver giữ app-local account hoặc PAT. | Person/Engagement correlation + verified revoke. |
| **Activity log blind spot** | Không thấy SSO/API dù có truy cập. | Multi-source coverage và data contracts. |
| **False activity inflation** | Heartbeat hoặc failed login reset clock. | Qualified activity taxonomy. |
| **Malicious activity after dormancy** | Một login bất thường sau nhiều tháng. | Risk correlation với device/session/resource. |
| **Credential misuse** | API key của người nghỉ vẫn dùng. | Credential inventory, rotation, workload owner. |
| **Denial of service from auto-disable** | Service job theo mùa bị khóa. | Principal-specific policies, dependency verification. |
| **Emergency access unavailability** | Break-glass bị dormant job disable. | Dedicated governance và readiness testing. |
| **Source tampering** | Người có admin quyền sửa `lastUsed` hoặc xóa log. | Provenance, audit integrity và SoD. |
| **Event ordering race** | Event sử dụng mới đến sau disable. | Pre-action recheck, versions và remediation correction. |
| **Cross-tenant identity collision** | Account cùng tên/ID được merge sai. | Issuer/tenant namespace, stable IDs. |
| **Privacy overcollection** | Thu quá nhiều hành vi chi tiết để tính “dùng”. | Data minimization, scoped queries, retention. |
| **Unreviewed exception** | Exemption vô thời hạn giữ quyền dư. | Owner, expiry, review và compensating controls. |
| **Recovery bypass** | Re-enable account với old role/session. | Full identity/credential/entitlement revalidation. |

### 35.2. Dữ liệu activity có thể nhạy cảm

Dữ liệu đăng nhập và hành động ứng dụng phản ánh thói quen làm việc, vị trí mạng và nội dung hoạt động. Chỉ thu thập **dữ liệu cần thiết để đánh giá account access** theo mục đích được cho phép:
- Ưu tiên event type, timestamp, source, account/owner reference và resource class.
- Không đưa raw password, OTP, session cookie, access/refresh token, PAT, private key vào log.
- Giảm IP/location hoặc dùng class khi đủ đáp ứng.
- Phân quyền theo IAM/SOC/app owner, audit các lần truy vấn/export.
- Có retention/deletion phù hợp chính sách và quy định áp dụng; không khẳng định một thời hạn universal.
- Bảo vệ backups, reporting pipeline và log extracts khỏi truy cập trái phép.

### 35.3. Không dùng dormancy làm đánh giá năng suất con người

Một ứng dụng không có login không chứng minh người dùng “không làm việc”. Bài toán IAM là **tài khoản/quyền có cần tồn tại và có an toàn không**, không phải kết luận hiệu suất hay hành vi cá nhân. Chỉ dùng dữ liệu cho mục đích được phê duyệt, với hạn chế phù hợp.

### 35.4. Kiểm tra gian lận trong approval

Người sở hữu account admin không nên có thể tự phê duyệt ngoại lệ indefinite cho chính mình. Kết hợp review độc lập, scoped approvals, SoD, expiry và history. Nếu detector/source bị thao túng, không dùng một điểm “dormancy false” để bỏ qua hard-revoke từ JML.

## 36. Ma trận kiểm thử Dormant account monitoring

Kiểm thử phải bao gồm **phát hiện, độ đầy đủ evidence, phân loại theo principal, approval, remediation và effective-access readback**. Các expected dưới đây là mục tiêu minh họa; cần điều chỉnh ngưỡng và hành động theo policy được duyệt.

| ID | Tiền điều kiện và hành động thử trong môi trường được phép | Expected |
| --- | --- | --- |
| **DA-01** | Human account enabled, 120 ngày không qualified use, coverage đủ, ngưỡng 90 ngày. | DORMANT_CANDIDATE + review, chưa tự delete. |
| **DA-02** | Human account có login hợp lệ hôm qua. | ACTIVE_OBSERVED, không gắn nhầm dormant. |
| **DA-03** | Account không có login nhưng API activity được xác minh hôm qua. | Không kết luận toàn bộ principal không hoạt động; phân loại riêng interactive use. |
| **DA-04** | Account có 100 failed logins mới, không successful use. | Không reset dormancy clock; tạo security finding riêng. |
| **DA-05** | MFA challenge sent, không verified. | Không tính là successful qualified login. |
| **DA-06** | SaaS `lastLogin=null` nhưng nguồn không có historical coverage. | UNKNOWN_INSUFFICIENT_COVERAGE. |
| **DA-07** | IdP SSO success và SP action trong tuần, SP lastLogin cũ. | Correlation dùng actual app activity, không auto-disable. |
| **DA-08** | Event qualified use đến muộn trước bước disable. | Pre-action recheck hủy/điều chỉnh remediation theo policy. |
| **DA-09** | Joiner trước Start date, chưa login. | PREBOARDING, không dormant routine. |
| **DA-10** | Joiner sau Start date chưa login, coverage đủ. | NEVER_USED_CANDIDATE, kiểm onboarding/helpdesk. |
| **DA-11** | Mover giữ old admin group, không dùng gần đây. | Rà soát/revoke theo Mover entitlement, không chờ threshold. |
| **DA-12** | Leaver account enabled còn PAT. | Leaver security/JML priority, xử lý credential/session. |
| **DA-13** | User ACTIVE dùng daily login, admin entitlement không dùng. | UNUSED_ENTITLEMENT finding, không dormant account. |
| **DA-14** | Một Person có hai accounts local/SSO. | Tách account IDs, nối Person đúng nguồn. |
| **DA-15** | Email được tái cấp cho Person khác. | Không merge accounts/persons theo email đơn lẻ. |
| **DA-16** | Rehire Engagement E2, old session/token E1. | Old credential/session không được tái kích hoạt. |
| **DA-17** | Contractor đã hết hợp đồng nhưng vẫn login. | Contractor termination workflow, không chỉ dormancy. |
| **DA-18** | Partner federated account không có IdP logs nội bộ. | UNKNOWN/đối chiếu SP/partner evidence, không vội dormant. |
| **DA-19** | Workload chạy theo quý, không use 60 ngày. | Dựa expected cadence và owner exception, tránh auto-disable. |
| **DA-20** | Workload ownerTeam đã bị xóa, credential còn enabled. | Orphan/high-priority review và kiểm dependency. |
| **DA-21** | PAT cá nhân vẫn gọi API sau khi owner Leaver. | Finding residual access, credential migration/revoke. |
| **DA-22** | Break-glass hiếm khi dùng, readiness hợp lệ. | Không auto-disable, vẫn giám sát usage/expiry. |
| **DA-23** | Break-glass dùng không có incident phê duyệt. | Security alert/independent review. |
| **DA-24** | Device retired nhưng certificate còn hợp lệ. | Device/PKI revoke workflow, không chỉ user dormancy. |
| **DA-25** | App-local admin không xuất hiện trong IdP inventory. | Discovery bổ sung local account/path. |
| **DA-26** | SCIM `active=false` được ACK nhưng local session còn. | Không báo verified cho tới khi target access được chặn hoặc giới hạn công bố. |
| **DA-27** | SaaS group removed, direct local role còn. | Reconciliation phát hiện effective grant tồn dư. |
| **DA-28** | Reviewer overdue, không trả lời. | Escalation theo policy; không auto-approve. |
| **DA-29** | Người có hai account tự approve giữ role đặc quyền. | SoD conflict được phát hiện qua canonical Person. |
| **DA-30** | Approved exception hết expiry. | Cần review/revoke, không auto-gia hạn vô hạn. |
| **DA-31** | Re-enable dormant human account. | Identity proofing, current approval/role, new credential/session. |
| **DA-32** | Disable service principal đang có dependency critical. | Pre-action dependency gate/owner validation, không phá job ngoài policy. |
| **DA-33** | Source logs mất một tenant trong 90 ngày. | UNKNOWN/coverage alert, không coi không hoạt động. |
| **DA-34** | Event duplicate do retry. | Dedup không đếm thành activity riêng và giữ provenance. |
| **DA-35** | Account enabled ở tenant A, disabled ở tenant B. | Tách trạng thái theo target/tenant, không báo globally disabled. |
| **DA-36** | Revoke requested nhưng target API vẫn chấp nhận token. | FAILED/OPEN residual access, không VERIFIED. |
| **DA-37** | Tài khoản đã disabled nhưng còn ở audit retention. | Không nhầm record lưu trữ với account có quyền. |
| **DA-38** | Test detection 90 ngày nhưng log history mới 30 ngày. | Insufficient coverage/threshold, không fabricated result. |
| **DA-39** | Role không dùng nhưng account có tác vụ hợp lệ. | Least privilege role cleanup, không account disable. |
| **DA-40** | Null lastUsed, createdAt có trước Start date còn xa. | Preboarding logic, không lấy createdAt làm baseline hợp lệ. |

### 36.1. Các bất biến quan trọng

~~~text
Leaver effective revoke must not wait for dormant threshold.
A dormant candidate is not automatically authorized for deletion.
Missing activity telemetry must not be interpreted as verified zero use.
Failed login and MFA challenge sent are not qualified successful use.
Break-glass accounts require separate readiness policy.
Machine/workload dormancy must use expected cadence and resource use.
A role unused does not imply the whole account is dormant.
Disabled at one IdP does not prove all active tokens are invalid.
Target ACK is not effective-access verification.
Rehire does not inherit old Engagement permissions automatically.
Review overdue does not equal approved exception.
Verified revoke requires scope-specific target evidence.
~~~

### 36.2. Kiểm cả đường hợp lệ

Nếu rule chỉ kiểm negative cases, nó có thể disable mọi thứ và đạt tỷ lệ “không còn dormant account” giả tạo. Cần kiểm **người dùng hợp lệ, job theo quý và break-glass** vẫn có đường sử dụng theo policy, đồng thời **Leaver và account không cần** bị xử lý đúng.

### 36.3. Kiểm thử có kiểm soát

Dùng tenant staging, account giả, token/credential thử nghiệm, calendar fixture và audit giả. Không thử credential người khác hoặc vô hiệu production service để chứng minh detector. Sau khi test, cleanup và readback mọi grant, token, account, exception do test tạo ra.


## 37. KPI và báo cáo Dormant account monitoring

Chỉ số phải đo được **độ bao phủ, chất lượng phân loại, xử lý quyền thực tế và rủi ro**, không chỉ số lượng account đã disable.

### 37.1. KPI gợi ý

| KPI | Định nghĩa/diễn giải | Lưu ý |
| --- | --- | --- |
| **Account inventory coverage** | Accounts/principals thuộc phạm vi đã được kiểm kê ÷ population nguồn có thẩm quyền. | Cần inventory độc lập, không lấy chính mẫu đã ingest làm mẫu số. |
| **Activity evidence coverage** | Accounts có đủ qualified activity sources cho policy window ÷ accounts cần giám sát. | Không tính `lastLogin=null` là đủ coverage. |
| **Dormant candidate rate** | Candidates được phát hiện ÷ accounts in-scope có evidence đủ. | Không trộn UNKNOWN vào dormant. |
| **Verified dormant rate** | Findings được reviewer xác nhận dormant ÷ findings có đủ kết luận. | Phụ thuộc sampling/risk tier. |
| **Never-used rate** | Accounts đã qua grace mà chưa qualified use ÷ accounts trong nhóm phù hợp. | Không đưa preboarding vào denominator sai. |
| **Orphaned account rate** | Accounts không có owner có thẩm quyền ÷ in-scope accounts. | Đặc biệt quan trọng với local admin và workload. |
| **Dormant privileged exposure** | Enabled privileged dormant accounts hoặc grants có quyền nhạy cảm. | Nên báo cả số đường quyền thực tế. |
| **Post-Leaver residual access** | Accounts/credentials/resources còn cho phép sau termination trái policy. | Đo theo effectiveAt và PEP evidence. |
| **Review completion SLA** | Findings được xử lý đúng hạn ÷ findings đến hạn. | Không tính auto-approved overdue. |
| **Owner response latency** | Từ notify tới decision hợp lệ. | Nên tách app owner, manager, sponsor. |
| **Disable/deprovision success** | Targets đạt trạng thái mong đợi và readback ÷ targets cần xử lý. | Provider ACK không tính VERIFIED. |
| **Effective revoke verification** | Access paths xác minh không còn dùng được ÷ required paths. | Tách PATH_UNVERIFIABLE. |
| **Session/token residual** | Token/API/session còn được chấp nhận sau action phải revoke. | Rủi ro thường bị bỏ sót. |
| **False dormant findings** | Findings được chứng minh sai do telemetry hoặc account purpose ÷ findings đủ kết luận. | Xem nguồn lỗi và sửa detector. |
| **Special account exception hygiene** | Break-glass/seasonal exceptions có owner, expiry, controls ÷ tổng cần ngoại lệ. | Giữ special account vẫn phải review. |
| **Telemetry freshness / gaps** | Delay và missing windows theo IdP/app/PAM/API. | Không suy 0 activity khi collector outage. |
| **Service dependency incidents** | Sự cố job/app do disable nhầm account. | Cần tính risk của automation. |
| **Recovery/re-enable compliance** | Reactivations có identity/approval/credential/role review đầy đủ ÷ lần kích hoạt lại. | Tránh hồi sinh quyền E1. |
| **License reclamation** | Licenses được thu hồi sau verified deprovision. | Chỉ là lợi ích bổ sung, không thay security objectives. |

### 37.2. Một bản báo cáo giả định

~~~text
DORMANT ACCOUNT MONITORING — EXAMPLE ONLY
As-of: 2026-12-01 10:00 +07:00
Scope: Workforce + 8 SaaS apps + 2 privileged directories

Accounts inventoried in scope: 5,000
Accounts with sufficient activity evidence: 4,600
Accounts with insufficient coverage: 400

Among 4,600 fully observed:
  Active/meaningful use within policy window: 4,100
  Dormant candidates: 400
  Never-used candidates: 100

Candidate review outcomes:
  Verified no longer required: 260
  Confirmed still needed with justification: 80
  Incorrect due to source semantics: 60
  Awaiting review: 100

Remediation:
  Targets disabled/roles revoked and verified: 180
  Targets pending owner/connector/dependency: 80
  Confirmed post-Leaver residual privileged paths: 2
  Emergency accounts excluded from auto-disable: 6
  Open exception items beyond due date: 12

Priorities:
  1. Contain two confirmed Leaver privileged residual paths.
  2. Fix 400 accounts with incomplete activity coverage.
  3. Resolve 12 overdue exceptions.
  4. Verify outstanding deprovision paths before reporting closure.
~~~

**Tất cả số liệu là giả định**. Phần `Candidate review outcomes` có tổng 500 (260 + 80 + 60 + 100), tương ứng 400 dormant candidates + 100 never-used candidates; `remediation` 180 + 80 = 260 confirmed no-longer-required. Không được kết luận “100% account an toàn” vì còn 400 accounts thiếu evidence và hai quyền Leaver đã xác nhận tồn dư.

### 37.3. Những mẫu số phải được công bố

- Ứng dụng, tenant, IdP và loại principal nào thuộc phạm vi?
- Coverage kỳ nào, nguồn nào đủ dữ liệu?
- Ngưỡng nào dùng cho account người, privileged và workload?
- Tài khoản disabled có được đếm trong denominator?
- Có bao nhiêu local admin/PAT ngoài inventory?
- Bao nhiêu finding chỉ là candidate, bao nhiêu đã xác minh?
- Có đường credential/session chưa đọc lại được không?

### 37.4. KPI theo mức rủi ro

Một tỷ lệ dormant 5% toàn hệ thống có thể ít quan trọng hơn **một orphaned production admin account**. Báo cáo nên có phân nhóm theo **privileged, resource sensitivity, JML status, credential exposure và độ chắc của evidence**, tránh chỉ nêu trung bình tổng.

## 38. Runbook điều tra và xử lý dormant account

### Bước 1 — Xác định finding, scope và trạng thái nguồn

Thu:
- `findingId`, `policyVersion`, `evaluatedAt`.
- `issuerId/tenantId/accountId` và target application.
- `principalType`, owner/Person/Engagement/workload.
- `lastQualifiedUseAt`, loại nguồn và cửa sổ coverage.
- Account state, entitlement, credential/session refs, risk tier.

**Không đưa password, PAT, access/refresh token hoặc session cookie vào ticket.**

### Bước 2 — Kiểm độ tin cậy của kết luận dormant

Tìm bằng chứng:
- SSO/app local login, resource actions và token use.
- Job logs, API gateway, STS/PKI đối với workload.
- MDM/device logs nếu liên quan (nhưng không lấy heartbeat làm activity của human).
- Pipeline lag, missed pages, rate limits, retention và source schema.
- Account migration/rename/tenant scope làm activity không khớp IDs.

Nếu thiếu coverage, chuyển `UNKNOWN_INSUFFICIENT_COVERAGE`, không khẳng định dormant.

### Bước 3 — Kiểm authoritative lifecycle

- **Leaver/contract expired:** chuyển workflow thu hồi theo effectiveAt.
- **Mover:** thu hồi quyền không còn cần, kể cả khi account hoạt động.
- **Joiner/preboarding:** phân biệt chưa bắt đầu với never-used sau activation.
- **Rehire:** xác minh Engagement mới và role mới.
- **Service/workload:** ownerTeam, mục đích, lịch và dependencies.
- **Break-glass:** phân loại riêng, kiểm readiness và bất kỳ lần dùng bất thường.

### Bước 4 — Đánh giá privilege và tác động

Rà soát:
- RBAC/ABAC roles trực tiếp/lồng nhau.
- PAM/JIT standing eligibility, active elevation, vault/SSH keys.
- API/PAT, refresh/access token family, device certificates.
- Local admin, alternate sign-in, shared technical credentials.
- Dữ liệu nhạy cảm, production/OT availability và người bị ảnh hưởng.

### Bước 5 — Thông báo và review có trách nhiệm

Gửi finding có evidence refs tới owner được xác minh. Đặt hạn, escalation và SoD theo mức risk. Khi owner xác nhận vẫn cần, ghi **reason, scope, next review**; khi không cần, mở remediation. Không biến silence thành keep/disable vô điều kiện ngoài policy.

### Bước 6 — Thực hiện thao tác có kiểm soát

Theo mức rủi ro và khả năng target:
- Remove role/entitlement không dùng.
- Restrict hoặc disable login cho account không còn cần.
- Revoke API keys/PAT/refresh tokens/session và PAM eligibility tương ứng.
- Rotate service credentials khi migration.
- Deprovision/delete theo retention và quy trình được duyệt.
- Bảo đảm khả năng audit và cơ chế recovery hợp lệ.

### Bước 7 — Readback và kiểm effective access

Chỉ kết luận `REVOKED_VERIFIED` trong scope khi đã có bằng chứng:
- Account/role state đúng ở target.
- Các credential/session liên quan đã bị revoke theo khả năng hệ thống.
- API/PEP không còn cho hành động trái policy trong các test được ủy quyền.
- Các đường chưa kiểm được có exception, owner và mitigation.
- Không còn jobs/credential bị bỏ sót ngoài phạm vi phát hiện.

### Bước 8 — Đóng và cải tiến

Lưu evidence, root cause, chủ thể được xác minh, kết quả user/owner, timestamps, policy, target và audit. Nếu source sai, cập nhật data contract và chạy lại detector; nếu Leaver có quyền dư, sửa JML reconciliation/connector/session handling.

## 39. Phân công trách nhiệm (Operating model)

| Vai trò | Trách nhiệm |
| --- | --- |
| **HRIS/People Ops** | Person, Engagement, Start/End/Move dates, nhân sự và contractor status. |
| **IAM/IGA** | Inventory/linking, access review, entitlement, JML deprovision workflow. |
| **IdP/Directory owner** | Account sign-in state, auth evidence, session/token behavior. |
| **Application/SaaS owner** | Account/local auth, app activity semantics, business need, target readback. |
| **PAM/Privileged owner** | Admin/break-glass classification, privilege grants, JIT evidence. |
| **Workload/Platform owner** | Service principal, job calendar, deployment, credential lifecycle. |
| **UEM/EDR/PKI owner** | Device identity, machine certificates, posture và revocation evidence. |
| **SOC/Detection** | Dormant account misuse, suspicious reactivation, compromised credentials. |
| **Data/SIEM engineering** | Activity collection, normalization, timestamps, source health, dedup. |
| **Security/Risk governance** | Threshold, exception, risk tiers, SoD, policy approval, residual risk. |
| **Compliance/Privacy** | Purpose/retention, data minimization, access controls và audit. |
| **Internal Audit** | Đánh giá bằng chứng và hiệu lực kiểm soát một cách độc lập. |

### 39.1. Nguồn có thẩm quyền phải theo thuộc tính

HRIS có thể là authoritative cho Engagement; app owner cho business purpose; IdP cho authentication event; API gateway cho resource use; PKI cho certificate; PAM cho privilege; asset inventory cho device ownership. **Không có một bảng duy nhất tự đáng tin về mọi thuộc tính**.

### 39.2. Quản trị thay đổi

Khi thay đổi IdP/SSO connector, thêm SaaS app, sửa token TTL, migrate tenant, đổi SCIM mapping hoặc giới thiệu máy chạy job theo lịch, phải cập nhật:
- Activity semantics và source inventory.
- Account identity correlation.
- Policy thresholds và exceptions.
- Regression tests cho detection/revoke.
- Report scope/denominator và data retention.
- Owner và escalation routes.

### 39.3. Quy tắc release kiểm soát

Không nên triển khai auto-disable diện rộng nếu:
- Chưa chứng minh coverage của activity sources.
- Không có inventory của workload/break-glass.
- Chưa kiểm cách cứu service quan trọng khi bị khóa nhầm.
- JML effectiveAt hoặc identity mapping chưa tin cậy.
- Thiếu dry run/shadow findings và manual review cho high-risk.
- Không thể kiểm được kết quả ở target.

## 40. Những sai lầm thường gặp khi giám sát dormant account

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| **Null lastLogin = account never used.** | Khóa nhầm do thiếu telemetry. | Kiểm history, data semantics, coverage. |
| **Dùng một ngưỡng cho mọi loại principal.** | Break-glass/service theo quý bị khóa. | Policy theo principalType, purpose và risk. |
| **Dùng failed logins làm activity.** | Tấn công khiến account thoát dormant. | Chỉ qualified successful use; failures là security signals. |
| **Chỉ kiểm IdP.** | Bỏ SaaS local, PAT, SSH/DB và API access. | Inventory mọi auth/credential path. |
| **SSO login = mọi app được sử dụng.** | Tính active sai cho unused SaaS accounts. | App/RP/resource usage evidence. |
| **Không login = không còn credential activity.** | PAT/refresh token vẫn dùng. | Token/API/workload audit. |
| **Chỉ dùng email làm khóa.** | Nhầm Person khi rename/rehire. | Issuer/tenant/stable IDs và Engagement. |
| **Chờ 90 ngày xử lý Leaver.** | Quyền tồn dư sau termination. | JML hard revoke ưu tiên. |
| **Chờ dormant mới rà soát admin grant.** | Privilege creep kéo dài. | Continuous/access review theo role/SoD. |
| **Disable break-glass vì hiếm dùng.** | Mất kênh khôi phục sự cố. | Dedicated readiness/exemption policy. |
| **Disable service principal vì không interactive login.** | Gián đoạn production job. | Expected cadence, job/API use, dependency analysis. |
| **Không xét Start date.** | Preboarding bị coi dormant. | Lifecycle-aware baseline. |
| **Tự approve khi owner không trả lời.** | Giữ quyền vô hạn. | Escalation, risk-based policy. |
| **Cho owner tự giữ quyền admin vô thời hạn.** | SoD/self-approval risk. | Independent approval, expiry. |
| **SCIM ACK = đã revoke mọi quyền.** | Session/API key còn hoạt động. | Target readback, PEP verification. |
| **Chỉ xóa account mà không revoke token.** | Access paths tiếp tục hoạt động. | Credential/session/grant inventory. |
| **Re-enable với roles cũ.** | Rehire/đổi nhiệm vụ kế thừa quyền dư. | Identity proofing + current role approval. |
| **Data collector outage ⇒ không có activity.** | False dormant findings diện rộng. | Source heartbeat/coverage validation. |
| **Chỉ báo tỷ lệ dormant toàn hệ thống.** | Che admin/Leaver critical findings. | Risk-tiered KPI và paths. |
| **Xóa record audit khi deprovision.** | Mất truy vết incident. | Tombstone/evidence retention theo policy. |
| **Thu thập quá mức hành vi người dùng.** | Privacy/exposure risk. | Purpose limitation, minimization, access audit. |
| **Coi reviewer ACK là quyền thực tế đã mất.** | Kết luận closure sai. | Verify effective access ở target. |

## 41. Checklist triển khai Dormant account monitoring

### 41.1. Inventory và danh tính

1. Đã kiểm kê account ở **IdP, directory, SaaS, PAM, API, cloud/workload và local auth paths** chưa?
2. Có phân biệt **HUMAN, CONTRACTOR/GUEST, PRIVILEGED, EMERGENCY, SERVICE/WORKLOAD và DEVICE** không?
3. Mỗi account có **issuer/tenant/accountId** ổn định và không gộp theo email đơn lẻ không?
4. Account human có **Person/Engagement** current/previous được xác minh không?
5. Account workload có **ownerTeam, purpose, expected cadence và dependencies** không?
6. Có phát hiện **orphan account** và **unused entitlement** riêng với dormant account không?

### 41.2. Hoạt động và chứng cứ

7. Mỗi source có định nghĩa rõ `lastLogin`/`lastUsed`/`lastActivity` và interactive/non-interactive không?
8. Có dữ liệu **app/API/session/token/privileged/workload use** khi cần không?
9. Có loại **failed login, MFA challenge sent, device heartbeat** khỏi qualified human use khi policy yêu cầu không?
10. Có biết **observation window đầy đủ, retention, ingestion lag và source outage** không?
11. `NULL` hoặc không có log có được phân biệt **NEVER_USED** với **UNKNOWN** không?
12. Có phân biệt **eventTime, effectiveAt, ingestedAt, evaluatedAt và timezone** không?
13. Có dedup/retry handling và cập nhật finding khi late event đến không?
14. Có kiểm proof/provenance và bảo vệ log khỏi spoof/tamper không?

### 41.3. JML và các account đặc biệt

15. Joiner trước Start date có được phân biệt với never-used sau activation không?
16. Mover có rà soát **unused old role/privilege** không cần chờ dormant threshold không?
17. Leaver và contractor expired có được **hard-revoke** theo effectiveAt không?
18. Rehire có **Engagement mới**, credentials/roles/current approvals được kiểm lại không?
19. Tài khoản break-glass có **readiness, independent review và alert**, không auto-disable không?
20. Service/workload có **expected schedule, API/token use và ownerTeam** phù hợp không?
21. Device/machine account có xét **asset lifecycle, credential/PKI và UEM telemetry** riêng không?
22. Có rà soát **PAM JIT/standing admin, SoD và direct grants** không?
23. Có phát hiện PAT/API key thuộc Person Leaver vẫn hoạt động không?

### 41.4. Workflow và thu hồi

24. Candidate có **review owner, dueAt, policyVersion, riskTier và evidence refs** không?
25. Reviewer không trả lời có được **escalate**, không auto-approve, theo policy không?
26. Exception có **mục đích, owner, scope, expiry và compensating controls** không?
27. Có pre-action recheck để tránh khóa account vừa có qualified activity không?
28. Trước khi disable service principal có **dependency validation và kế hoạch an toàn** không?
29. Có phân biệt **remove role, restrict, disable, revoke sessions/keys, delete và archive** không?
30. SCIM/IdP/PAM actions có được **readback target state** không?
31. Có kiểm **API/session/token/credential effective denial** theo phạm vi phù hợp không?
32. Các đường `UNVERIFIABLE` có ticket, owner, mitigation và dueAt không?
33. Re-enable có **identity proofing, approval, least privilege, credential rotation và new session** không?

### 41.5. Kiểm thử, đo lường và dữ liệu

34. Có test positive/negative cho **human active, Leaver, preboarding, privileged, break-glass, workload theo mùa** không?
35. Có test **null lastLogin, outage, delayed event, duplicate, cross-tenant mapping** không?
36. Có test **SCIM ACK nhưng token còn dùng**, quyền direct grant và session API không?
37. KPI có nêu **mẫu số, coverage, UNKNOWN, risk tier và effective revocation** không?
38. Có bảo vệ **PII, raw secrets, audit trail, retention và export** đúng quy định không?
39. Có review source schema/policy sau **IdP/SSO/SCIM/app migration** không?
40. Có xác minh cleanup của test accounts/credentials và không làm gián đoạn service thực không?

## 42. Kết luận: Dormant account là dấu hiệu phải xác minh, không phải lý do khóa tự động

~~~text
ACCOUNT INVENTORY
    Account / Issuer / Tenant / PrincipalType
                    ↓
AUTHORITATIVE LIFECYCLE & OWNER
    Person–Engagement / Workload / Asset
    Joiner–Mover–Leaver + Business purpose
                    ↓
QUALIFIED ACTIVITY EVIDENCE
    Interactive login + SSO / App actions
    API / PAT / Token / PAM / Machine use
                    ↓
COVERAGE, FRESHNESS & DORMANCY POLICY
    Threshold by type/risk, UNKNOWN != DORMANT
                    ↓
OWNER REVIEW & RISK-BASED DECISION
    Keep / Narrow role / Exception / Revoke
                    ↓
CONTROLLED TARGET REMEDIATION
    IdP / SCIM / SaaS / PAM / PKI / Session
                    ↓
EFFECTIVE-ACCESS READBACK & AUDIT
    Verified deny, open gaps, evidence and KPI
~~~

**Ghi nhớ:** **Dormant account là tài khoản được nhận diện ít hoặc không có hoạt động hợp lệ trong một cửa sổ được chính sách định nghĩa và có chứng cứ quan sát đủ tin cậy**. Nó **khác** tài khoản disabled, orphaned, never-used, quyền ít dùng hay credential máy hoạt động theo lịch. Phải tách **interactive login** khỏi **SSO, API/token, PAM và workload use**, không suy `lastLogin=null` thành “không bao giờ dùng”. Trong IAM **Joiner–Mover–Leaver**, sự kiện **Leaver/Mover và thu hồi quyền tồn dư** có thể cần xử lý ngay, không được đợi ngưỡng dormant. Với **break-glass, service account, Rehire và guest**, cần chính sách riêng, ownership, dependency và ngoại lệ có hạn. Việc xử lý chỉ hoàn chỉnh khi **IdP/SSO/SCIM/RBAC/ABAC/PAM, session/credential và các resource/API thực sự đã thực thi kết quả**, được kiểm chứng bằng readback, log, review và KPI có mẫu số/độ bao phủ rõ ràng.

