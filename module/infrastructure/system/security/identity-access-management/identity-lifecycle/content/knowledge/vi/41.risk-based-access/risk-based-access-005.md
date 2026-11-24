# Behavior signal trong Risk-based access: nhận diện hành vi bất thường và ra quyết định truy cập theo rủi ro

**Behavior signal** (*tín hiệu hành vi*) là **quan sát có nguồn gốc, thời điểm và ngữ cảnh rõ ràng về cách một chủ thể đang hoặc đã tương tác với hệ thống**. Trong **risk-based access** (kiểm soát truy cập dựa trên rủi ro), các tín hiệu như **kiểu đăng nhập, chuỗi thất bại–thành công, thay đổi tần suất gọi API, thao tác truy cập tài nguyên nhạy cảm hoặc mẫu hành động đặc quyền** có thể được dùng để ước lượng rủi ro và điều chỉnh quyết định xác thực/ủy quyền.

Ví dụ: nhân viên thuộc đội Support thường đăng nhập từ thiết bị đã đăng ký, đọc các ticket được phân công và hiếm khi xuất dữ liệu hàng loạt. Trong một phiên, hệ thống ghi nhận **nhiều lần xác thực thất bại**, tiếp đó **đăng nhập thành công bằng một client mới**, rồi **yêu cầu tải số lượng lớn hồ sơ ngoài phạm vi công việc**. Mỗi dấu hiệu riêng lẻ có thể có lời giải thích hợp lệ. Khi ghép thành **chuỗi có thứ tự, gắn đúng identity, session, resource và baseline**, chúng có thể tạo tín hiệu rủi ro đủ mạnh để yêu cầu **phishing-resistant MFA, xác minh lại phiên, hạn chế thao tác, chuyển rà soát hoặc từ chối hành động cụ thể**, tùy chính sách.

Bài thuộc chương **Risk-based access** của module **Security — Identity and Access Management (IAM) — Identity Lifecycle**. Phạm vi là quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh, tạo account, cấp quyền, rà soát, thay đổi vai trò và thu hồi; liên kết **HRIS, IdP, SSO, OAuth/OIDC, SCIM, RBAC/ABAC, PAM/JIT, non-human identities, kiểm toán và giảm quyền tồn dư**. Chủ đề này giải thích **tín hiệu hành vi được tạo, chuẩn hóa, kết hợp, đánh giá và dùng như thế nào trong IAM**, đồng thời nêu rõ giới hạn kỹ thuật, quyền riêng tư và rủi ro cảnh báo sai.

> **Nguyên tắc quan trọng:** **Behavior signal không phải proof of identity, không phải kết luận một người có ý đồ xấu và không phải authorization grant.** Nó là **đầu vào quan sát** cho risk assessment. Cần phân biệt **phát hiện bất thường**, **ước lượng xác suất/rủi ro**, **quyết định policy** và **thực thi thực tế tại ứng dụng/API**. Một sự kiện bất thường chưa đủ để khẳng định account bị chiếm; ngược lại, một phiên “hành vi bình thường” chưa chắc an toàn.

## 1. Vì sao Identity Lifecycle cần behavior signal?

Mô hình cấp quyền tĩnh giả định rằng khi user đăng nhập thành công và có role hợp lệ, họ có thể tiếp tục sử dụng quyền cho đến khi role/session thay đổi. Trong thực tế, **rủi ro biến động nhanh hơn chu kỳ cấp quyền**:

- Credential bị đánh cắp sau khi một phiên đã được tạo.
- Token của OAuth client bị sao chép sang runtime lạ.
- Một nhân viên Mover vẫn còn role cũ tại SaaS.
- Một user có quyền đọc hợp lệ nhưng tải dữ liệu hàng loạt ngoài quy luật.
- Một tài khoản đặc quyền kích hoạt JIT rồi sửa chính sách audit.
- Một service account ít hoạt động đột nhiên tạo hàng trăm credentials.
- Một Leaver vẫn còn app-local session hoặc long-lived token.
- Một account đang bị credential stuffing trước khi đăng nhập thành công.

**Behavior signal giúp xác định khi nào cần kiểm tra lại quyết định truy cập** trong suốt vòng đời của account/role/session, thay vì chỉ nhìn lần đăng nhập đầu tiên.

### 1.1. Câu hỏi cần trả lời

1. **Chủ thể nào?** Person ID, privileged account, OAuth client, workload identity hay service account?
2. **Đã làm gì?** Authentication, API action, role change, export, session elevation?
3. **Bằng chứng đến từ đâu?** IdP, resource server, PAM, EDR, SCIM connector, network gateway?
4. **Có gì bất thường?** So với lịch sử cá nhân, nhóm tương đồng, workload contract hay chính sách?
5. **Mức tin cậy của tín hiệu?** Clock, completeness, source attestation, false-positive rate?
6. **Mức tác động?** Hành động là xem một hồ sơ công khai hay xóa production role?
7. **Quyết định nào phù hợp?** Allow, step-up, restrict, deny, monitor, queue for review?
8. **Có chặn được thật không?** PEP ở API/target có kiểm resource/action theo chính sách không?
9. **Sau quyết định có evidence không?** Audit, appeal, override có kiểm soát, target readback.

### 1.2. Không thay thế các kiểm soát nền tảng

Behavior signal chỉ **bổ sung**:
- Identity proofing, đăng ký device/workload và quản trị account.
- MFA, passkeys và credential protection.
- Session/token validation.
- RBAC/ABAC và least privilege.
- SoD/approval và PAM/JIT cho đặc quyền.
- SCIM/target deprovisioning.
- Log integrity, incident response, access recertification.

Một hệ thống không được coi “risk score thấp” là giấy phép bỏ qua **mandatory deny** do Leaver, expired grant, thiếu quyền resource hoặc vi phạm policy không thể miễn trừ.

## 2. Phân biệt signal, feature, anomaly, risk score và policy decision

Các khái niệm này thường bị trộn lẫn, dẫn đến hệ thống tự động từ chối thiếu căn cứ.

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Raw event** | Bằng chứng từ nguồn về hành động hoặc ngữ cảnh. | IdP event: login failed lúc 09:01. |
| **Behavior signal** | Quan sát hành vi được diễn giải có ngữ cảnh và nguồn. | 8 failures từ cùng account trong 10 phút. |
| **Feature** | Giá trị tính toán để đưa vào rule/model. | `failedLoginCount10m=8`. |
| **Baseline** | Phân bố/đặc trưng hành vi kỳ vọng trong ngữ cảnh. | Thường 0–1 failure/10 phút. |
| **Anomaly** | Khoảng lệch khỏi baseline. | Failure burst không thường gặp. |
| **Threat indicator** | Dấu hiệu liên quan kỹ thuật tấn công, có thể không phải behavior. | Source IP nằm trong feed botnet có độ tin cậy cao. |
| **Risk score** | Tổng hợp nhiều tín hiệu + độ tin cậy + impact. | `risk=72/100` theo mô hình minh họa. |
| **Policy decision** | Kết quả quy tắc cấp quyền. | `STEP_UP` cho thao tác export. |
| **Enforcement** | Hành động thực tế tại PEP/target. | API yêu cầu xác thực lại hoặc trả deny. |
| **Outcome feedback** | Kết quả xác minh để cải thiện phát hiện. | Người dùng xác nhận travel hợp lệ; analyst đóng case. |

**Một tín hiệu rủi ro cao không tự cấp quyền cho hệ thống an ninh làm mọi thứ**. Quyết định cần có policy owner, phạm vi tác động, logging, thời hạn và khả năng khôi phục.

### 2.1. Tín hiệu hành vi không đồng nghĩa mọi thuộc tính rủi ro

- `loginCountLastHour` là **behavioral feature**.
- `deviceCompliant=false` là **device posture/context signal**.
- `sourceIpReputation=highRisk` là **threat intelligence/context**.
- `resourceSensitivity=critical` là **impact/context**.
- `userDepartment=Finance` là **identity attribute** từ HRIS.
- `employeeIsLeaver=true` là **lifecycle state** và có thể là hard deny.
- `impossibleTravelFlag` là **derived anomaly**, cần kiểm tính tin cậy của geo và timing.

Tất cả có thể tham gia **risk assessment**, nhưng gắn nhãn sai sẽ làm khó đánh giá dữ liệu và giải thích quyết định.

### 2.2. Đừng dùng “AI anomaly” như nguồn sự thật

Một mô hình thống kê/ML có thể chỉ ra bất thường, nhưng:
- Hành vi hợp lệ cũng có thể mới/lạ.
- Attacker có thể bắt chước baseline.
- Dữ liệu training có thể bị sai, thiếu hoặc đã bị tấn công.
- Một nhóm người thường làm việc ca đêm có baseline khác.
- Mô hình không chứng minh legal/HR/business entitlement.

Cần có **explainable reason codes, calibration, human review và hard policy constraints**.

## 3. Danh mục behavior signals trong IAM

| Nhóm | Signal ví dụ | Nguồn chính | Rủi ro gợi ý |
| --- | --- | --- | --- |
| **Authentication sequence** | Liên tiếp sai mật khẩu rồi thành công. | IdP, SSO, AD, VPN. | Password spraying, compromised credential, typo. |
| **MFA interaction** | Nhiều prompt bị từ chối/timeout rồi thành công. | IdP MFA events. | MFA fatigue, lỗi thiết bị hoặc workflow. |
| **Session behavior** | Tạo nhiều session song song lạ. | IdP, gateway, target app. | Session misuse, shared credential. |
| **API usage** | Tần suất gọi API tăng bất thường. | API gateway, resource server. | Automation misuse, token theft, batch hợp lệ. |
| **Sensitive action** | Export nhiều hồ sơ hoặc thay policy. | Application/PEP audit. | Data exfiltration hoặc emergency work. |
| **Privileged elevation** | JIT activation ngoài thói quen/mục đích. | PAM, IGA, cloud IAM. | Privilege misuse, incident hợp lệ. |
| **Role/grant change** | Tự tạo role, thêm member admin group. | IAM, SCIM, SaaS/cloud target. | Escalation/persistence. |
| **Cross-resource access** | Truy cập nhiều tenants/projects mới. | API/DB/cloud logs. | Lateral movement, expanded assignment. |
| **Workflow deviation** | Bỏ bước approval hoặc hành động trước phê duyệt. | IGA, PAM, business app. | SoD bypass hoặc lỗi orchestration. |
| **Non-human identity** | Service principal dùng từ host/runner lạ. | AS, CI, cloud, workload issuer. | Client secret/token copied. |
| **Temporal pattern** | Hoạt động đột biến ngoài lịch thường. | Auth/API/PAM events. | Misuse hoặc on-call incident. |
| **Geographic/network transition** | Session từ nguồn mạng rất khác trước. | IdP/VPN/network telemetry. | Proxy/travel/VPN/credential theft. |

**Một số cột là tín hiệu hành vi; một số có thêm ngữ cảnh mạng và thiết bị.** Cần đặt tín hiệu cùng **identity, session, time window, target và business context**.

### 3.1. Dữ liệu bảo đảm chất lượng quyết định

Tín hiệu nên có tối thiểu:
- `signalId` và `signalType`.
- `subjectIdentityId`, `subjectKind`.
- `sourceSystem` và trust level.
- `eventTime` và `receivedAt`.
- `observedValue`, `baselineRef`, `featureWindow` nếu là anomaly.
- `confidence` hoặc reliability estimate, không chỉ severity.
- `targetResourceRef`, `sessionRef`, `correlationId`.
- `modelVersion`, `ruleVersion` và evidence references.
- Privacy classification và retention policy.

### 3.2. Tránh gán “nguy hiểm” cho yếu tố cá nhân nhạy cảm

Không dựa vào chủng tộc, giới tính, tôn giáo, tình trạng sức khỏe, khuynh hướng chính trị hay đặc tính cá nhân nhạy cảm để quyết định đáng tin hay không. Hành vi truy cập nên được đánh giá từ **hoạt động bảo mật liên quan nhiệm vụ và tài nguyên**, với dữ liệu tối thiểu và quy trình fairness/privacy.

## 4. Kiến trúc thu thập signal từ nguồn IAM

~~~mermaid
flowchart TD
    HR["HRIS / contractor registry / JML"] --> N["Identity context service"]
    IDP["IdP/SSO/MFA login events"] --> ING["Authenticated event ingestion"]
    API["API gateway / resource PEP events"] --> ING
    PAM["PAM / privileged session"] --> ING
    SCIM["SCIM + target access changes"] --> ING
    END["EDR/device posture + network"] --> ING
    N --> JOIN["Identity binding and time-window join"]
    ING --> JOIN
    JOIN --> F["Signal normalization + feature windows"]
    F --> B["Behavior baselines / rule or model"]
    B --> R["Risk assessment + policy constraints"]
    R --> D["PDP decision: permit/step-up/restrict/deny"]
    D --> P["Target IdP/API/PAM PEP enforcement"]
    P --> A["Decision audit + outcomes / feedback"]
    A --> B
~~~

### 4.1. Không gom mọi event theo email

Một người có thể có:
- HR person ID.
- IdP subject ID.
- Privileged/admin account.
- SaaS-local account.
- OAuth client hoặc delegated workload.
- Session IDs trên nhiều ứng dụng.

Email có thể đổi/tái sử dụng; một account có thể được chuyển owner. Nên có **identity correlation** theo stable IDs có authority và lịch sử hiệu lực, không gộp hai người vì trùng email hay display name.

### 4.2. Machine identity khác human identity

Một OAuth client thực hiện `client_credentials` có thể không có end user. Không gắn hành vi API client cho người từng tạo secret chỉ vì họ là creator. Cần liên kết **service catalog owner, logical workload identity, clientId, issuer, runtime/runner và target**.

### 4.3. Signal source có thể bị trễ hoặc bị chiếm

Một detector có thể nhận event từ IdP sau 20 giây, từ target SaaS sau 10 phút và từ PAM gần real time. Việc **join theo timestamp** cần hiểu data freshness, clock skew, out-of-order và delivery semantics. Không tuyên bố một tín hiệu “real-time” khi nguồn phải batch export hàng giờ.

## 5. Login behavior: đăng nhập, sai mật khẩu và MFA

### 5.1. Credential failure sequence

Ví dụ chuỗi:

~~~text
09:01  USER_LOGIN_FAILED (source A)
09:02  USER_LOGIN_FAILED (source A)
09:02  USER_LOGIN_FAILED (source A)
09:03  USER_LOGIN_FAILED (source A)
09:04  USER_LOGIN_SUCCESS (source A)
~~~

Một feature có thể là `failureThenSuccessIn5m=true`. Tuy nhiên:
- Người dùng có thể gõ sai do đổi mật khẩu.
- Password manager có thể dùng credential cũ.
- Account có thể bị password spraying từ nhiều nguồn.
- SSO gateway có thể gộp retries.
- MFA failure khác primary credential failure.

Cần đối chiếu **loại thất bại, source binding, device registration, session và phát hiện tấn công đa account**.

### 5.2. MFA behavior

Các dấu hiệu:
- Nhiều MFA pushes liên tiếp khi user nói không khởi tạo.
- MFA requests từ login flows không quen thuộc.
- User chấp nhận một prompt sau nhiều lần từ chối.
- Đăng ký authenticator mới ngay sau sign-in lạ.
- Gỡ yếu tố xác thực cũ trong cùng chuỗi.
- Recovery code/authenticator reset bất thường.

Đáp ứng có thể là **step-up bằng phishing-resistant MFA hoặc helpdesk identity verification** theo policy, session containment và cảnh báo. Không ép người dùng lặp prompt push hàng loạt vì **MFA fatigue** có thể làm tăng rủi ro.

### 5.3. “Success sau failures” không luôn là account compromise

Detector cần phân biệt:
- `wrong_password`, `invalid_client`, `session_expired`, `mfa_cancelled`, `network_timeout`.
- Username enumeration hoặc false-positive do đổi thiết bị.
- Thời điểm user password reset.
- Các automation jobs cố đăng nhập bằng secret cũ.
- Failures từ source không liên quan với successful session.

Báo cáo nên ghi **candidate suspicious chain** thay vì kết luận chắc chắn “kẻ tấn công đã đăng nhập”.

## 6. Session behavior: thay đổi trong một phiên đã xác thực

Sau khi login thành công, rủi ro vẫn có thể thay đổi.

### 6.1. Những dấu hiệu cần xét

- Session bắt đầu từ device chưa được ghi nhận.
- Thao tác mới xuất hiện sau thời gian idle rất lâu.
- Chuyển đột ngột giữa các nhóm resource không liên quan.
- Phiên có hành vi crawl/enumerate thay vì workflow thông thường.
- Cookie/token bị sử dụng từ nhiều host/network không phù hợp trust context.
- Tần suất gọi endpoint nhạy cảm tăng cao.
- Session đi từ đọc dữ liệu sang thay IAM role hoặc export toàn bộ.
- Token audience hoặc scope được sử dụng ngoài use case dự kiến.

Một số dấu hiệu như **IP/host change** là context; rủi ro thực sự cần xét **session binding, proxy/VPN, token proof-of-possession và target action**.

### 6.2. Continuous assessment

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant APP as Application / PEP
    participant R as Risk assessment
    participant IDP as IdP / MFA
    U->>APP: Access app with existing session
    APP->>R: Subject/session + requested action/resource
    R-->>APP: Normal risk -> Permit
    U->>APP: Request sensitive export
    APP->>R: Updated behavior + target sensitivity
    R-->>APP: Elevated risk -> Step-up required
    APP->>IDP: Re-authenticate / phishing-resistant MFA
    IDP-->>APP: Assurance result tied to session
    APP->>R: Re-evaluate current policy
    R-->>APP: Permit scoped action or Deny
~~~

**Step-up thành công không tự khiến mọi resource được phép truy cập.** PEP vẫn phải kiểm **RBAC/ABAC và object/tenant authorization**.

### 6.3. “Continuous” không nhất thiết mỗi mili giây

Có thể đánh giá rủi ro:
- Tại đăng nhập.
- Khi refresh token/session renewal.
- Trước một high-impact action.
- Khi có event threat/identity lifecycle mới.
- Khi IdP/target hỗ trợ event-driven claims/session evaluation.

Tần suất đánh giá phải cân bằng hiệu năng, độ trễ signal và risk. Không hứa một PEP dùng JWT offline có khả năng **thu hồi tức thời** nếu không được thiết kế.

## 7. API và dữ liệu: khác biệt giữa workload hợp lệ và exfiltration

### 7.1. Tăng tốc độ không tự động là tấn công

Một service chạy batch cuối tháng có thể:
- Gọi 100.000 requests trong một giờ.
- Đọc nhiều bản ghi liên tục.
- Bắt đầu vào nửa đêm.
- Chạy song song từ nhiều nodes.

Với một human support account, hành vi tương tự có thể bất thường. Vì vậy phải xét:
- Subject type: human hay workload.
- Business schedule: batch/incident/maintenance.
- Resource sensitivity và scope đã cấp.
- Expected throughput và service SLO.
- Historical/peer baseline theo use case.
- Actions là read, export, delete, update IAM policy hay không.

### 7.2. Các feature tiêu biểu

| Feature | Diễn giải | Lưu ý |
| --- | --- | --- |
| `apiRequests5m` | Số request trong 5 phút. | Traffic spikes hợp lệ, retries. |
| `uniqueResources15m` | Số đối tượng/tài nguyên khác nhau được truy cập. | Bulk report có thể cần. |
| `sensitiveReads1h` | Read actions trên resource nhạy cảm trong 1 giờ. | Phải dựa classification thực. |
| `exportBytes15m` | Tổng lượng dữ liệu xuất. | Size estimate, compression, missing telemetry. |
| `failedAuthorizationRate` | Tỷ lệ Deny do thiếu quyền. | App bugs có thể sinh retries. |
| `newEndpointCount24h` | Số loại API chưa từng dùng theo baseline. | Deployment mới là thay đổi hợp lệ. |
| `distinctTenants1h` | Số tenant khác nhau được access. | Multi-tenant service hợp lệ. |
| `roleChanges10m` | Số grant/role/policy changes. | Admin change window có kế hoạch. |

Không đặt ngưỡng “hơn N request = attacker” áp dụng chung. Baseline và **allowed business operation** quyết định ý nghĩa rủi ro.

### 7.3. Chặn bằng target authorization, không dùng score để cấp quyền mới

Nếu API yêu cầu `reports:export` nhưng subject chỉ có `reports:read`, phải **DENY vì thiếu entitlement** dù score thấp. Risk-based access chỉ có thể **thắt chặt hoặc yêu cầu thêm điều kiện** trong tập quyền hợp lệ; không được tự tạo grant mới để “thưởng cho user đáng tin”.

## 8. Behavior signal cho privileged access, PAM và JIT

Các hành động đặc quyền có tác động lớn và cần nguồn signal đặc thù:

- JIT activation ngoài approved change/incident window.
- Yêu cầu role rộng bất thường so với nhiệm vụ.
- Checkout privileged credential nhiều lần ngắn.
- Mở phiên từ jump host không được đăng ký.
- Thực hiện lệnh sửa IAM policy, logging, encryption keys hoặc credential store.
- Session có thao tác khác với ticket purpose.
- Tạo mới privileged account, API key hoặc SSH key.
- Gia hạn nhiều lần để giữ privileged activation liên tục.
- Logout/PAM session close nhưng target session vẫn hoạt động.

### 8.1. High impact là risk context khác behavior

Một lệnh xóa log có thể rất nhạy cảm dù user chưa từng có anomaly. Policy có thể yêu cầu **independent approval/JIT/step-up** chỉ vì action impact cao; behavioral anomaly **không phải điều kiện bắt buộc** để áp security control.

### 8.2. SoD là hard constraint khi bắt buộc

Một user vừa là người tạo payment và người approve payment có thể vi phạm SoD dù hành vi đều “giống ngày hôm trước”. Risk engine phải không ghi đè **SoD hard deny** bằng “user thường làm vậy nên risk thấp”. Nếu có exception hợp lệ, cần **risk owner/approver, scope/time, compensating control và audit**, không chỉ score.

### 8.3. Session recording và intent

PAM recording có thể giúp điều tra lệnh thực tế, nhưng **video/command log không tự xác định intent**. Ghép ticket, command, target config diff, change window và post-use review. Không bật thu thập nội dung nhạy cảm quá mức khi chỉ cần metadata và bảo đảm quyền riêng tư.

## 9. Human Joiner: baseline lạnh và danh tính mới

**Cold start** xảy ra khi user mới không có lịch sử đủ dài.

### 9.1. Không phạt Joiner chỉ vì “chưa từng đăng nhập”

Một nhân viên mới có thể:
- Lần đầu dùng device mới.
- Đăng nhập từ địa điểm lần đầu.
- Mở nhiều ứng dụng trong onboarding.
- Đăng ký MFA/passkey lần đầu.
- Xin các quyền baseline cho team.

Nếu detector coi mọi hoạt động chưa từng có là bất thường cao, Joiner sẽ liên tục bị chặn. Cần:
- HRIS verified start date và role/department.
- Onboarding workflow/approved app assignments.
- Thiết bị được đăng ký và compliance state.
- Peer baseline có chọn lọc (cùng job function, không lấy nhân khẩu học nhạy cảm).
- Initial monitoring và step-up cho action nhạy cảm, không blanket deny.
- Tăng weight của personal baseline khi đã có đủ dữ liệu.

### 9.2. Eligibility vẫn phải được xác minh

Một Joiner chưa qua identity proofing hoặc chưa đến effective start date không được cấp quyền chỉ vì “hành vi giống nhân viên chính thức”. Behavior signal **không thay employment/contract authorization**.

### 9.3. Không dùng historical email làm baseline cho người mới

Nếu địa chỉ email từng thuộc nhân viên cũ, tái dùng baseline có thể:
- Làm sai ngữ cảnh tài khoản.
- Gộp activity hai người.
- Gây privacy leak.
- Ẩn anomaly hoặc báo sai.

Binding phải theo **person ID, immutable subject và employment episode** theo policy.

## 10. Human Mover: mô hình hành vi phải đổi theo nhiệm vụ

Khi Lan chuyển từ Operations sang Finance, những hành vi trước đây là bình thường — vào production host, sửa cluster, chạy `kubectl` — có thể **không còn business basis**.

### 10.1. Điều sai khi dùng baseline lịch sử trần

Một detector có thể nói:
> “Lan đã thao tác production admin mỗi tuần trong sáu tháng, hôm nay thao tác đó không bất thường.”

Nhưng HRIS xác nhận Mover có effectiveAt hôm nay và OpsAdmin không còn hợp lệ. **Lifecycle policy override baseline**: target phải revoke/deny quyền cũ dù hành vi “bình thường” xét về thống kê.

### 10.2. Làm mới baseline sau Mover

- Lấy authoritative role/assignment mới.
- Đánh dấu thay đổi **baseline epoch** hoặc phân tách trước/sau effectiveAt.
- Dùng peer baseline tạm thời cho nhóm mới nếu phù hợp.
- Không dùng activity từ role cũ để cấp trust cho resource mới.
- Giám sát attempts vào resource cũ hoặc direct grant cũ.
- Kiểm tra SCIM/PAM/target provisioning drift.
- Cập nhật owner/approver/SoD context.

### 10.3. Handover có ngoại lệ

Nếu người chuyển nhóm cần bàn giao trong thời hạn ngắn, tạo **approved temporary entitlement/exception** có scope/time. Không lấy score thấp để hợp thức hóa quyền không còn trong assignment. Log phải ghi **reason, approver, validUntil và target readback**.

## 11. Human Leaver: hard deny không phụ thuộc độ “bình thường”

Một nhân viên đã có Leaver effectiveAt theo nguồn authoritative không tiếp tục được dùng IAM quyền thông thường chỉ vì họ đăng nhập từ thiết bị quen thuộc.

### 11.1. Các lớp cần revoke

- Human IdP/SSO sessions và MFA factors theo policy.
- SCIM/target accounts, group memberships.
- Direct grants, RBAC roles và ABAC attribute-derived permissions.
- PAM/JIT eligibility, privileged sessions và emergency entitlements.
- OAuth refresh tokens, application sessions và PATs/SSH keys khi liên quan.
- Vault/CI/CD/credential management roles.
- Quyền quản trị machine identities và secrets từng được biết.

**Risk score thấp không được phục hồi hoặc kéo dài quyền sau effective Leaver**. Nếu legal hold/investigation cần bảo toàn records, tách lưu evidence khỏi quyền truy cập đang hoạt động.

### 11.2. Behavior signals hỗ trợ tìm residual access

Một detector có thể báo:
- API token tiếp tục dùng sau disable.
- App-local login sau offboarding.
- Service secret bị sử dụng từ workstation người đã nghỉ.
- Privileged session không đóng.
- Role cũ tự xuất hiện do dynamic group re-provision.

Nhưng không chờ detector phát hiện mới revoke. **JML event là trigger thực thi**, behavior signals là lớp **xác minh, giám sát và phát hiện bypass**.

### 11.3. Rehire

Một người tái tuyển cần được đánh giá theo role/identity episode hiện tại. Không tự mang về **risk trust, role grants hoặc active sessions** từ lần làm việc cũ. Dữ liệu lịch sử có thể được giữ cho kiểm toán theo policy nhưng không dùng vô điều kiện để cấp quyền.

## 12. Device, network và location: tín hiệu ngữ cảnh bổ trợ

**Device posture**, **IP reputation**, **ASN/network**, **location estimate** thường tham gia risk scoring. Chúng không phải lúc nào cũng là **behavior signal** và có giới hạn.

| Context | Tác dụng | Giới hạn |
| --- | --- | --- |
| Device managed/compliant | Tăng độ tin cậy vào endpoint theo policy. | Device compliance không chứng minh người đang thao tác. |
| Phishing-resistant MFA | Tăng assurance xác thực. | Không thay authorization theo resource. |
| IP reputation | Gợi ý nguồn lạm dụng/automation. | NAT/VPN/shared IP và feed có thể sai. |
| ASN/network transition | Phát hiện nguồn kết nối khác thường. | Mobile carrier/proxy có thể đổi thường xuyên. |
| Geolocation estimate | Hỗ trợ phân tích hành trình đăng nhập. | Vị trí IP không phải vị trí vật lý chính xác. |
| Device fingerprint | So sánh môi trường client. | Dễ thay đổi/spoof, có rủi ro privacy. |
| Time of day | Context cho lịch làm việc/on-call. | Ca đêm, du lịch, giờ linh hoạt hợp lệ. |
| Resource classification | Tăng impact nếu action thành công. | Không là bằng chứng actor nguy hiểm. |

### 12.1. “Impossible travel” cần giải thích chặt

Ví dụ:
- 09:00 login từ IP được định vị ở Singapore.
- 09:10 login từ IP được định vị ở Hà Nội.
- Hai login gắn cùng identity.

Detector có thể phát **travel-speed anomaly**, nhưng:
- Người dùng có thể dùng VPN hoặc secure web gateway.
- GeoIP không chính xác đến cấp thiết bị.
- Một session có thể được refresh bằng token từ cloud proxy.
- Hai sự kiện có thể không đại diện cho hai địa điểm vật lý của người.
- Log time/clock skew có thể gây đảo thứ tự.

Kết luận thích hợp là **signal cần xác minh**; có thể step-up hoặc điều tra tùy sensitivity, không tự nói người dùng đã thực sự di chuyển phi vật lý.

### 12.2. Device trust không đồng nghĩa permission

Một managed laptop có `compliant=true` vẫn không cho phép người dùng truy cập bảng lương nếu họ thiếu quyền. Trong ABAC, device posture là **một điều kiện bổ sung** chứ không phải nguồn tạo permission.

## 13. UEBA, baseline và phát hiện bất thường

**UEBA (User and Entity Behavior Analytics)** là tập kỹ thuật phân tích hành vi của **người dùng và thực thể** (kể cả service accounts) để hỗ trợ phát hiện hoạt động không phù hợp với ngữ cảnh/baseline. Không phải mọi doanh nghiệp cần ML phức tạp; một số quy tắc có evidence và precision tốt có thể giá trị hơn.

### 13.1. Các kiểu baseline

1. **Self baseline:** lịch sử của chính identity/khối thời gian tương ứng.
2. **Peer baseline:** nhóm có job function và resource scope tương tự.
3. **Entity contract baseline:** định mức workflow của một service/bot/job.
4. **Absolute policy boundary:** ngưỡng bắt buộc vì dữ liệu nhạy cảm, không phụ thuộc thống kê.
5. **Seasonal baseline:** chu kỳ tuần, tháng, kỳ khóa sổ, on-call.
6. **Post-change baseline:** sau Mover, deployment hoặc policy change.

### 13.2. Chọn peer group có cơ sở nghiệp vụ

Gộp tất cả “employees” làm một baseline thường sai: SRE trực đêm, finance closing và support tickets khác nhau. Peer groups nên dựa **job role/function, system purpose, permissions và operational schedule**, có kiểm tra fairness/coverage. Không xây baseline dựa trên thuộc tính cá nhân nhạy cảm không cần cho bảo mật.

### 13.3. Baseline có thể bị attacker “đầu độc”

Nếu attacker kiểm soát account lâu và tăng tốc độ export từ từ, baseline tự học có thể coi hành vi xấu là bình thường. Giảm nguy cơ bằng:
- Không auto-learn từ mọi event chưa qua đánh giá.
- Loại known incidents/suspicious periods khỏi training theo policy.
- Giới hạn mức baseline có thể dịch chuyển.
- Có absolute hard rules cho hành động không bao giờ hợp lệ.
- Human review cho anomaly drift.
- Independent policy/context features.

### 13.4. Một baseline có chất lượng phải versioned

Ghi `baselineVersion`, thời gian tập dữ liệu, số samples, population và chất lượng. Nếu model cập nhật, một signal từ hôm qua phải **có thể giải thích theo model/baseline version tại thời điểm quyết định**, không tính lại rồi thay lịch sử.

## 14. Feature engineering: biến event thành signal có thể kiểm tra

Một feature có thể được tính trên rolling window:

~~~text
failedLoginCount(subject, 10m)
distinctSourceNetworks(subject, 1h)
sensitiveResourceReads(subject, 15m)
newPrivilegedActions(subject, 7d)
exportedBytes(subject, 1h)
newOAuthClientCredentials(subject, 24h)
pimActivationCount(subject, 30d)
servicePrincipalNewRunner(subject, 7d)
~~~

### 14.1. Time windows phải rõ

`15m` có thể là:
- 15 phút theo **eventTime**.
- 15 phút theo **receivedAt**.
- Một cửa sổ tumbling hoặc sliding.
- Event-time window có watermark xử lý out-of-order.

Không trộn lẫn ngữ nghĩa. Một event đến trễ có thể cần cập nhật analytics nhưng **không hồi tố một quyết định đã thực thi** nếu policy không định nghĩa cơ chế đó; thay vào đó ghi **late evidence/reassessment event**.

### 14.2. Count và rate có thể lừa

Một service gọi 1.000 lần/giờ nhưng có retries khi downstream lỗi. Nếu không phân biệt unique business actions và retry attempts, detector báo exfiltration sai. Có thể cần:
- Distinct correlation ID.
- Response status, latency, retry metadata.
- Pagination/bulk export endpoint.
- Bytes thực sự trả về, không chỉ request count.
- Data classification và tenant.
- Expected batch window.

### 14.3. Percentile và robust statistics

Một feature như `apiRequests5m=300` chỉ đáng chú ý nếu so với baseline phù hợp. Có thể dùng:
- Median, interquartile range (IQR) thay vì chỉ mean/std khi dữ liệu lệch.
- Percentile (p95/p99) theo identity/workload cohort.
- Cumulative rate change.
- Distinct resources/actions vs total events.
- Whitelisted **business schedule** có expiry, không tắt detector vô hạn.

**Percentile rất cao không tự chứng minh tấn công**; hãy kết hợp action sensitivity, current entitlement và nguồn credential.

### 14.4. Feature freshness và confidence

Một EDR signal mới nhưng không có dữ liệu 30 phút có thể không nên được hiểu `healthy=true`. Cần ba trạng thái:
- Healthy/valid recently.
- Unhealthy/risky.
- **Unknown/stale/unavailable**.

Dùng `missing=false` cho mọi giá trị không thấy sẽ làm giảm risk giả tạo.

## 15. Tính risk score: ví dụ định lượng có giới hạn

Một công thức minh họa:

\[
R = \operatorname{clip}_{[0,100]}\left(B + \sum_{i=1}^{n}w_i s_i\right)
\]

Trong đó:
- \(B\): base risk theo policy và context được phép.
- \(s_i\): feature/signal được chuẩn hóa, không phải chỉ nhãn “high”.
- \(w_i\): trọng số theo hiệu lực thực nghiệm/risk analysis.
- `clip` giới hạn khoảng 0–100.

**Đây không phải tiêu chuẩn chung hoặc mô hình có xác suất được hiệu chỉnh.** Điểm 70/100 không tự có nghĩa “70% account đã bị chiếm”.

### 15.1. Ví dụ cộng điểm để hiểu logic

| Signal/context | Điểm minh họa | Lý do |
| --- | ---: | --- |
| 6 lần sai credential trước một login thành công. | +20 | Authentication sequence anomaly. |
| Login từ client/device chưa có trust binding. | +15 | Unfamiliar access context. |
| Session đột nhiên yêu cầu export nhạy cảm. | +25 | High-impact behavioral deviation. |
| Đã xác minh phishing-resistant MFA trong phiên. | -15 | Authentication assurance control theo policy. |
| Context/identity data bị thiếu nhiều. | +10 hoặc yêu cầu review | Missing evidence không tự là an toàn. |
| **Ví dụ tổng sau clip** | **55** | Dùng cho bài học, không phải model production. |

**Không cộng các signal tương quan như thể độc lập**. Cùng một sự cố proxy có thể tạo “geo lạ”, “device lạ”, “network lạ”; cộng ba lần không kiểm soát sẽ thổi phồng rủi ro.

### 15.2. Hard deny đứng ngoài scoring

~~~text
if identity.lifecycleState == LEAVER:
    DENY
else if not RBAC_ABAC_entitlement_allows(action, resource):
    DENY
else if applicable_SoD_hard_violation:
    DENY
else:
    evaluate_behavior_and_context_risk()
~~~

Nếu đã thiếu quyền, một risk score thấp **không được** biến thành Permit. Nếu risk score cao, policy có thể **thắt chặt** cho action đáng ra được phép.

### 15.3. Risk thresholds phải dựa vào đo lường

Ví dụ minh họa:
- `0–29`: policy bình thường, ghi audit.
- `30–59`: step-up cho action nhạy cảm.
- `60–79`: restrict action/bắt xác minh lại.
- `80–100`: deny action và mở điều tra.

**Không dùng các ngưỡng này như khuyến nghị universal**. Phải calibrate theo labeled outcomes, action impact, false positives, recovery procedures, regulatory/privacy constraints và risk appetite của tổ chức.

## 16. PDP/PEP: tín hiệu biến thành quyết định truy cập như thế nào?

**Risk assessment** không phải PEP. Một API phải **thực thi** policy rõ ràng.

| Thành phần | Vai trò |
| --- | --- |
| **PIP** | Cung cấp authoritative identity, JML, device, threat/behavior features, resource context. |
| **PDP** | Đánh giá policy dựa entitlement + điều kiện/risk và trả decision. |
| **PEP** | Enforce ở IdP, API gateway, application, cloud, DB/PAM target. |
| **PAP** | Quản lý policy versions, thresholds, approval và exception. |
| **Audit/feedback** | Lưu decision evidence, actual outcome và false-positive feedback. |

### 16.1. Một chuỗi decision

~~~mermaid
flowchart TD
    A["Subject + requested action/resource"] --> B["Authentication and token validity"]
    B --> C{"Identity ACTIVE, assignment valid?"}
    C -->|Không| D["DENY: hard lifecycle policy"]
    C -->|Có| E{"Entitlement RBAC/ABAC + SoD valid?"}
    E -->|Không| D
    E -->|Có| F["Obtain behavior/context features + freshness"]
    F --> G["Risk evaluation with policy version"]
    G --> H{"Risk/action threshold"}
    H -->|Low| I["PERMIT within existing scope"]
    H -->|Elevated| J["STEP_UP / RESTRICT / REVIEW"]
    H -->|Critical| D
    I --> L["Target PEP action + audit"]
    J --> L
    D --> L
~~~

### 16.2. Cách giải thích reason code

Không nên chỉ ghi `decision=DENY, score=88`. Cần metadata:
- `reasonCodes=["FAILED_LOGIN_BURST","UNFAMILIAR_DEVICE","SENSITIVE_EXPORT"]`.
- Evidence time window/source freshness.
- Policy/model version.
- Resource sensitivity.
- Required next action (MFA, appeal, SOC review).
- Decision expiry/reevaluation trigger.
- Target enforcement result.

**Không tiết lộ detection secrets cho attacker**; user-facing error nên hỗ trợ khôi phục mà không cho phép dò ngưỡng/rule, trong khi audit nội bộ đủ để giải thích.

### 16.3. No standing privilege by low score

Không định nghĩa “risk thấp ⇒ tự cấp GlobalAdmin/ProductionWrite”. **Cấp entitlement** vẫn qua IGA/approval và authority. Behavior-driven trust chỉ có thể tác động **conditions/assurance** trong phạm vi permission đã được cấp.

## 17. Adaptive controls: step-up, restrict, revoke và monitor

| Quyết định | Ý nghĩa | Trường hợp hợp lý |
| --- | --- | --- |
| **PERMIT** | Cho thao tác trong phạm vi quyền hiện hành. | Risk/context đáp ứng chính sách. |
| **STEP_UP** | Yêu cầu assurance cao hơn trước action. | Access từ device lạ tới resource nhạy cảm. |
| **RESTRICT** | Giảm chức năng: read-only, chặn export hoặc scope hẹp. | Session có anomaly nhưng chưa đủ deny toàn bộ. |
| **DENY** | Từ chối action/phiên. | Missing entitlement, Leaver, high-confidence compromise. |
| **REVOKE_SESSION** | Chấm dứt session/token theo khả năng target. | Session hijack/compromise signal đáng tin. |
| **QUARANTINE** | Cô lập credential/device/workload theo playbook. | Compromise có scope rõ, risk cao. |
| **MONITOR/REVIEW** | Cho phép có audit và human investigation. | Low-confidence anomaly, false-positive cost cao. |
| **TEMPORARY_EXCEPTION** | Cho use case hợp lệ theo policy đã duyệt. | On-call/travel/DR có controls và expiry. |

### 17.1. Step-up không nên bị lạm dụng

Nếu liên tục ép MFA mỗi request, user có thể bỏ qua cảnh báo hoặc bị push fatigue. Nên:
- Dùng phishing-resistant methods khi phù hợp.
- Cache assurance level trong **ràng buộc thời gian/session/action** hợp lý.
- Không tin `mfa=true` từ client header.
- Có giới hạn số lần challenge và phương án account recovery.
- Reevaluate sau session binding/token change hoặc risk trigger.
- Không bỏ hard deny sau khi step-up pass.

### 17.2. Restrict theo action lành tính hơn khóa cả account trong vài trường hợp

Nếu có anomaly export nhưng user vẫn cần đọc ticket:
- Chặn `export:bulk` trước.
- Giữ `ticket:read` nếu policy cho phép và risk chưa high-confidence.
- Yêu cầu security review cho quyền nhạy cảm.
- Thông báo người dùng cách xác minh.
- Log decision và recovery path.

**Không bảo đảm luôn có thể restrict một action** nếu ứng dụng chỉ có coarse role. Khi không có PEP đủ chi tiết, phải nêu limitation và chọn phương án bảo vệ phù hợp.

### 17.3. Thời hạn của quyết định rủi ro

Risk evaluation có **validity window/TTL**. Một kết quả “trusted device 09:00” không nên dùng vô hạn đến 17:00 khi device bị đánh dấu compromised lúc 10:00. Cần event-driven invalidation hoặc recheck theo policy.

## 18. Token và session: risk thay đổi sau lúc phát access token

Một access token có thể được phát khi risk thấp nhưng user/token sau đó bị compromise.

### 18.1. Self-contained JWT và quyền tồn dư

~~~text
09:00  Client nhận access token, exp=10:00
09:10  Behavior engine thấy risk cao
09:12  IdP đánh dấu session revoked
09:15  Resource API chỉ kiểm chữ ký/audience/exp
09:20  API vẫn chấp nhận token cũ

Nếu API không kiểm current authorization/revocation:
  Hành động có thể tiếp tục tới 10:00.
~~~

Cần mô tả chính xác **revocation latency**. Một signal risk cao tại IdP không tự động chặn mọi offline resource server.

### 18.2. Những lựa chọn kiểm soát

- Access token TTL ngắn khi phù hợp.
- Token introspection với opaque tokens hoặc cơ chế được hỗ trợ.
- Request-time authorization truy vấn policy/session status.
- Revoke refresh token và application sessions.
- Token/session version hoặc revocation list phù hợp threat model.
- Event-driven notification tới targets hỗ trợ.
- Step-up before privileged action.
- Target-side deny/containment khi không thể revoke token ngay.
- Giám sát API activity sau revoke.

### 18.3. ID token, access token và refresh token khác nhau

**OIDC ID token** phục vụ xác thực user tại relying party; **OAuth access token** cho resource server theo grant; **refresh token** xin token mới. Behavior signal có thể dẫn tới **step-up/login lại** hoặc revoke tokens, nhưng cần tác động **đúng loại credential và session**. Không dùng ID token làm API bearer token.

### 18.4. Continuous access evaluation phụ thuộc nền tảng

Một số hệ sinh thái hỗ trợ cơ chế **event/claim challenge hoặc continuous access evaluation**. Khả năng này không đồng nhất giữa IdP/SaaS/API và không bảo đảm mọi JWT tự chứa được revoke tức thời. Phải đo **từ lúc signal → decision → target denial** thay vì chỉ đọc trạng thái tại IdP.

## 19. Behavior signal cho non-human account và workload identity

**Non-human identities (NHI)** bao gồm service accounts, OAuth clients, machine/workload identities, CI/CD principals, bots, RPA và một số device identities. Chúng thường chạy liên tục, có batch bursts, autoscale và **không có hành vi giống người**.

### 19.1. Baseline theo workload contract

Với `billing-etl-prod`:
- Job hợp lệ: chạy mỗi đêm theo lịch.
- Nguồn: runner/cluster được đăng ký.
- Token issuer: IdP/workload federation được tin.
- Audience: `finance-api`.
- Scope: `finance:summary.write`.
- Target: dataset/tenant cụ thể.
- Owner team: Finance Data Platform.

Các signal quan trọng là **sự lệch khỏi contract này**:
- Token request từ workstation/runner lạ.
- Client Credentials token cấp cho resource chưa từng phê duyệt.
- Access ngoài lịch công việc và không có incident/change hợp lệ.
- Xin thêm app-only admin role hoặc tạo secret mới.
- Truy cập tenant khác hoặc cloud region lạ.
- Token exchange từ issuer/subject không nằm trong trust binding.
- Machine identity vẫn hoạt động sau khi service catalog ghi retired.
- Dùng credential từ nhiều runtime không khớp deployment inventory.

### 19.2. Không lấy IP hoặc tần suất làm định danh chắc chắn

Cloud autoscaling và NAT có thể khiến IP thay đổi liên tục. Shared egress làm nhiều workloads xuất hiện dưới cùng một IP. Nên ưu tiên:
- Logical workload identity.
- Issuer và signed subject/audience.
- Cluster/project/namespace/serviceAccount binding.
- Runtime/job ID và deployment provenance.
- Scoped token claims từ issuer đáng tin.
- Cloud resource/principal IDs.
- Owner/business service metadata.

**Một OAuth client ID/secret bị chia sẻ** không thể tự xác định chính xác runner nào đã dùng secret. Muốn attribution theo workload, cần issuer trust và telemetry phù hợp.

### 19.3. RPA là một phân nhóm riêng

Unattended robot có thể đăng nhập GUI, click nhanh, hoạt động ngoài giờ và lặp thao tác giống automation. Không dùng baseline của người dùng thường để tự động chặn RPA. Thay vào đó:
- Bám job schedule, runner và orchestrator identity.
- Theo dõi transaction types và business limits.
- Giám sát shared credential exposure.
- Giữ **maker/checker SoD** cho giao dịch tài chính.
- Tách human owner và robot execution actor.
- Theo dõi exception interactive login theo thời hạn.

### 19.4. Machine lifecycle và Leaver của owner

Khi một owner con người Leaver, machine identity có thể vẫn cần chạy. Behavior engine nên:
1. Thu hồi human control đến vault/CI/CD/cloud IAM.
2. Kiểm tra secret từng được người đó đọc/copy.
3. Chuyển owner và approver.
4. Duy trì workload legitimate theo least privilege.
5. Giám sát access từ human-origin workstation hoặc old tokens.
6. Khi service thật sự retired, chặn app-only grants và token/session access.

**Không tự disable workload sản xuất chỉ vì owner nghỉ**, cũng không bỏ qua việc xử lý shared secrets.

## 20. Behavior signal và thay đổi quyền qua SCIM, RBAC/ABAC

### 20.1. SCIM là provisioning, không phải risk protocol

**SCIM 2.0** có thể đồng bộ User/Group ở một số targets. SCIM không cung cấp một chuẩn chung cho `behaviorRiskScore` hay cơ chế **continuous session revocation** trên mọi SaaS. Tùy ứng dụng, runtime risk decision có thể cần IdP conditional access, API gateway, PAM hoặc enforcement point tại target.

Một hành vi có thể khiến IAM:
- Đánh dấu account để security review.
- Thu hồi một temporary group entitlement.
- Chuyển session sang read-only.
- Kích hoạt deprovision nếu source authority/business process quy định.
- Yêu cầu step-up khi target hỗ trợ.

Nhưng **không viết `active=false` vào SCIM chỉ vì một anomaly yếu** nếu hành động sẽ disable cả workload hoặc chặn người dùng mà chưa có authority/policy.

### 20.2. Phân biệt risk response và entitlement lifecycle

| Sự kiện | Hành động phù hợp | Căn cứ |
| --- | --- | --- |
| User login từ network mới, vẫn có role hợp lệ. | Step-up/monitor cho action nhạy cảm. | Risk context, không thay role. |
| Mover mất nhiệm vụ OpsAdmin. | Revoke entitlement cũ, readback. | HRIS/role policy; **không phụ thuộc score**. |
| Suspicious PAM session có dấu hiệu bị chiếm. | Contain session, revoke/rotate theo playbook. | High-confidence security response. |
| Service retired, OAuth client vẫn active. | Disable client, revoke app grants/tokens. | Service lifecycle source. |
| Missing SCIM target membership sau grant. | Reconcile provisioning mismatch. | Desired vs actual state. |
| Dynamic group tái cấp quyền đã revoke. | Sửa authoritative group rule/attribute. | Provisioning governance. |

### 20.3. RBAC xác định được phép làm gì

Role như `SupportReader` chỉ cho đọc tickets; risk engine không được trao thêm `BulkExporter` nếu score giảm. **RBAC/ABAC = giới hạn quyền tối đa hợp lệ**; behavior-based conditions có thể làm truy cập **nghiêm ngặt hơn**.

### 20.4. ABAC nên dùng thuộc tính có provenance

ABAC policy có thể xét:
- `subject.role`/assignment từ HRIS/IGA.
- `subject.lifecycleState`.
- `session.authnAssurance` từ IdP.
- `device.posture` từ hệ thống quản lý thiết bị.
- `environment.riskLevel` từ risk engine.
- `resource.classification` và tenant ở resource server.
- `action`/resource cụ thể.

Không tin `risk=low` hoặc `deviceTrusted=true` do HTTP request tự khai. PEP phải lấy quyết định từ **nguồn tin cậy** với TTL/claims binding, đồng thời kiểm object-level authorization.

### 20.5. Cẩn thận với dynamic attributes và stale cache

Một PDP có thể cache `riskLow=true` 15 phút. Sau 3 phút, user trở thành Leaver hoặc security phát hiện token theft. Nếu PEP không invalidate cache, request vẫn có thể Permit. Cache TTL phải **phù hợp độ nhạy action, freshness và hard-lifecycle event**, không kéo dài permission ngoài hạn grant/session.

## 21. Risk-based access và Approval/SoD/Access review

### 21.1. Behavior signal giúp ưu tiên rà soát, không thay người phê duyệt

Một access recertification campaign có thể xếp ưu tiên:
- Privileged users truy cập tài nguyên chưa từng liên quan nhiệm vụ.
- Service accounts lâu không dùng nhưng còn app-only roles rộng.
- Entitlements từng bị từ chối nhiều lần nhưng nay được gán.
- Accounts có token/privileged session activity sau Leaver effectiveAt.
- Users có repeated access deny vào resources ngoài scope.
- JIT activations liên tục và hết hạn/gia hạn bất thường.

**Signal là evidence cho reviewer**, không tự trở thành quyết định **REVOKE/KEEP** khi workflow yêu cầu owner/risk approver đánh giá.

### 21.2. No-self-approval

Một user có thể tự tạo approval record trong chính ứng dụng mà họ có quyền quản trị; behavior engine không được coi chữ ký của cùng person qua account khác là independent approval. Cần kiểm:
- **Person identity binding** giữa human, privileged và service accounts.
- Delegation authority và effective period.
- Resource/role owner độc lập khi SoD bắt buộc.
- Approval request version/scope.
- Target grant outcome và audit trail.

### 21.3. Risk signal có thể phát hiện exception bị lạm dụng

Ví dụ exception cho `ProductionReader` đến 17:00, nhưng beneficiary:
- Gia hạn mỗi ngày không có incident mới.
- Chuyển từ read sang admin.
- Sử dụng ngoài resource scope.
- Dùng cùng credential từ nguồn mạng bất thường.

Đây là lý do **điều tra và re-evaluate exception**. Nếu action nằm ngoài scope đã duyệt thì **Deny theo policy** dù detector chưa tính được anomaly.

### 21.4. Không cản trở emergency recovery sai cách

Một break-glass account ít dùng chắc chắn có behavior pattern hiếm. Nếu rule “rare login ⇒ lock account” áp vô điều kiện, tổ chức có thể mất đường khôi phục chính IdP/PAM. Thiết kế cần:
- Recovery path pre-authorized, được kiểm thử độc lập.
- Custody và actor attribution.
- Monitoring/alert mạnh khi dùng.
- Risk-based action constraints và post-use review.
- Không phụ thuộc hoàn toàn vào PDP/IdP đang lỗi.

**Alert và accountability** có thể bắt buộc, nhưng không nhất thiết khóa một recovery account đang phục hồi hệ thống trong thời điểm khó nhất, trừ chính sách và threat model yêu cầu.

## 22. Data quality: risk engine không thể mạnh hơn nguồn tín hiệu

### 22.1. Độ đầy đủ và độ trễ

Một decision thực tế phải biết:
- IdP sign-in feed còn hoạt động không?
- Target API audit có coverage cho endpoint đang xét không?
- Event pipeline trễ bao lâu?
- Có event bị drop/retry/out-of-order không?
- EDR posture cập nhật lần cuối khi nào?
- HRIS role change có effectiveAt hay chỉ ingestion timestamp?
- Có missing signals do privacy/retention restrictions không?

Một feature `failedLogins5m=0` có thể có nghĩa **không thấy failures**, chứ không nhất thiết **đã chứng minh không có failures**.

### 22.2. Missingness là trạng thái riêng

~~~text
devicePosture =
    COMPLIANT
    NON_COMPLIANT
    UNKNOWN
    STALE
    UNAVAILABLE

Nên tránh:
    null -> COMPLIANT
    missing failedLoginCount -> 0 chắc chắn
~~~

Khi nguồn unavailable, policy cần lựa chọn theo action impact:
- Monitor hoặc request step-up.
- Từ chối thao tác privileged/sensitive nếu không kiểm chứng đủ điều kiện.
- Đưa vào hàng đợi manual review.
- Cho một recovery path được thiết kế riêng nếu critical availability cần.

**Không mở mọi API khi risk engine timeout**. Nhưng cũng không tự làm sập toàn bộ production bằng cách chặn mọi low-impact action vì một dashboard chậm; phân loại risk và có degraded-mode policy rõ.

### 22.3. Clock skew và ordering

~~~text
IdP eventTime:          09:01:00
Target receivedAt:      09:00:58
PAM eventTime:          09:00:55
Collector receivedAt:   09:01:10

Timestamps khác nguồn không tự tạo total order tin cậy.
~~~

Dùng stable correlation ID, per-source sequence, trusted receive time và event-time watermarks. Với JML, **effectiveAt của nguồn HR authoritative** quan trọng hơn việc SIEM thấy event sớm hay muộn.

### 22.4. Log integrity liên quan trực tiếp risk quality

Nếu attacker có thể sửa log hành vi hoặc tắt collector:
- Có thể làm điểm rủi ro giảm giả tạo.
- Có thể tạo false positives đánh vào user mục tiêu.
- Có thể làm mất bằng chứng sau compromise.
- Có thể đầu độc baseline.

Cần **authenticated transport, source identity, append-only/tamper-evident audit, gap detection, out-of-band alerts và quyền truy cập log theo SoD**. Không coi data pipeline tự động là trusted chỉ vì nó thuộc cùng tổ chức.

### 22.5. Identity linking failure là lỗi nghiêm trọng

Khi một service user dùng chung cho ba jobs, events cùng `accountId` có thể bị trộn. Phải ghi:
- Account/principal identity.
- Logical workload identity nếu xác minh được.
- Runtime/job ID.
- Owner team.
- Target resource và token issuer.
- Confidence của attribution.

Không khẳng định một người thật làm action chỉ vì tên creator của service principal trùng hồ sơ nhân viên.

## 23. Privacy, fairness và tính minh bạch của behavior analytics

Behavior analytics có thể tạo dữ liệu rất chi tiết về hoạt động nhân viên; triển khai phải dựa trên **mục đích bảo mật chính đáng, dữ liệu tối thiểu, quyền hạn và nghĩa vụ pháp lý tại nơi áp dụng**.

### 23.1. Chỉ thu dữ liệu liên quan kiểm soát truy cập

Thường đủ để phát hiện rủi ro:
- Identity/account ID có kiểm soát.
- Action/endpoint/resource classification.
- Timestamp và success/deny.
- Device/network context cần thiết.
- Session/correlation IDs.
- Feature counts, anomaly reason codes.
- Credential/token reference, **không lưu full secret/token**.

Không mặc định cần:
- Ghi phím người dùng liên tục.
- Toàn bộ nội dung email, chat hoặc tài liệu.
- Dữ liệu sức khỏe hoặc đặc tính cá nhân nhạy cảm.
- Location tracking độ phân giải cao ngoài mục tiêu an ninh.
- Lưu vô hạn lịch sử thao tác của nhân viên.

### 23.2. Keystroke dynamics và behavioral biometrics

Một số công nghệ dùng **typing cadence, mouse dynamics hoặc các behavioral biometrics** để đánh giá session continuity. Chúng có thể tạo dữ liệu nhạy cảm và có false positives do accessibility needs, thiết bị hoặc điều kiện sử dụng. Nếu áp dụng, cần:
- Cơ sở pháp lý và thông báo theo quy định.
- Privacy/security impact assessment.
- Hạn chế raw collection; cân nhắc feature protection.
- Đánh giá precision/recall và tác động đến nhóm người dùng.
- Giải pháp thay thế khi user không thể đáp ứng.
- Không coi biometric anomaly là bằng chứng phạm tội hoặc ý đồ xấu.

### 23.3. Fairness và kiểm soát thiên lệch

Một rule “đăng nhập đêm = nguy hiểm” có thể tạo tác động không cân xứng cho người trực ca, làm việc từ xa hoặc có múi giờ khác. Có thể giảm sai lệch bằng:
- On-call roster và approved schedule.
- Per-role/workload baselines.
- False-positive tracking theo use case hợp lệ.
- Review từ Security, Privacy, HR/Legal khi áp dụng.
- Không sử dụng protected/sensitive attributes làm proxy vô căn cứ.
- Có challenge/review/appeal path cho user bị block sai.

### 23.4. Giải thích quyết định mà không lộ detector

Một user được yêu cầu step-up có thể nhận thông báo: “Hoạt động hiện tại cần xác minh bổ sung để bảo vệ tài khoản”. SOC/auditor có thể thấy **reason codes, source/event refs, model version, policy owner và thời gian**. Không cần hiển thị chi tiết ngưỡng detection hoặc nguồn threat intelligence bí mật cho mọi client.

### 23.5. Retention và quyền truy cập

Signal/feature/baseline cần:
- Thời hạn lưu theo nhu cầu điều tra và luật.
- Role-based access cho data analysts/SOC.
- Separation of duties cho người vận hành engine và người phê duyệt policy.
- Encryption và audit đối với exports.
- Data minimization ở cross-border flows.
- Cơ chế xóa/ẩn danh khi hết căn cứ, trừ legal hold/retention hợp pháp.

## 24. Adversarial behavior: attacker có thể thao túng tín hiệu

### 24.1. Evasion bằng hành vi “rất bình thường”

Attacker có thể:
- Dùng chính device/session đã bị chiếm.
- Truy cập vào giờ làm việc quen thuộc.
- Tăng request rate từ từ.
- Chỉ gọi API user đã dùng trước đây.
- Ẩn trong batch jobs.
- Lạm dụng một account có baseline overprivileged từ lâu.

Vì thế **absence of anomaly không đồng nghĩa absence of compromise**. Hard policies, least privilege, credential/session binding và independent detections vẫn cần.

### 24.2. Model poisoning

Nếu risk engine tự học từ mọi sự kiện:
1. Attacker bắt đầu export nhiều hơn từng chút.
2. Dữ liệu không được đánh dấu suspicious.
3. Baseline tăng dần.
4. Một đợt export lớn sau đó không còn bất thường.

Giảm nguy cơ:
- Data lineage và model training approvals.
- Exclude known compromise windows.
- Absolute policy thresholds cho high-impact actions.
- Giới hạn tốc độ baseline drift.
- Separate production evaluation và training pipelines.
- Canary/challenger models và periodic human review.

### 24.3. Alert flooding và feedback abuse

Attacker có thể gửi nhiều anomalous events để làm quá tải SOC; hoặc tạo tín hiệu giả để khóa account người khác. Cần:
- Rate limits và event dedup.
- Alert correlation theo campaign/session/identity.
- Confidence scoring và evidence validation.
- Phân biệt DoS/risk-engine attack với account compromise.
- Manual override có thẩm quyền khi cần.
- Logging actions của analysts/risk admins.

### 24.4. Manipulating source metadata

Nếu endpoint tin `X-Forwarded-For` hoặc client-supplied `deviceId` không qua trusted proxy, attacker có thể giả source/location. Chỉ dùng headers từ **trusted ingress chain** và binding do IdP/device management phát, không tin dữ liệu tự khai.

### 24.5. Defender phải bảo vệ chính risk policy

Một compromised cloud admin có thể cố:
- Đổi score threshold.
- Xóa signal rules.
- Tắt model runtime.
- Sửa historical audit.
- Gắn một account vào allowlist vô hạn.
- Chỉnh source-to-identity mappings.

Các thao tác **policy/model/allowlist changes** phải có **independent approval, immutable audit, JIT/PAM và integrity monitoring** tương xứng.

## 25. Failure mode và đường xử lý khi signal không khả dụng

### 25.1. Rủi ro của fail-open

Một API có logic:

~~~text
try:
    risk = riskService.score(request)
except Timeout:
    return PERMIT
~~~

Nếu attacker làm risk service timeout, mọi sensitive action có thể đi qua **fail-open**. Đây là lỗi thiết kế nguy hiểm khi risk check là điều kiện bắt buộc.

### 25.2. Fail-safe không đồng nghĩa chặn tất cả công việc

Một chính sách theo impact:

| Action/context | Risk service unavailable | Xử lý gợi ý |
| --- | --- | --- |
| Read public content đã được phép. | Low impact. | Có thể tiếp tục theo baseline policy và ghi degraded mode. |
| Read internal tickets. | Medium impact. | Có thể step-up/monitor hoặc restrict theo policy. |
| Export dữ liệu nhạy cảm. | High impact. | Deny/review/step-up nếu thiếu mandatory signal. |
| Grant GlobalAdmin hoặc tạo privileged secret. | Critical impact. | Không bypass hard authorization; dùng approval/JIT. |
| Khôi phục IdP/PAM bị outage. | Recovery path có dependency failure. | Dùng **pre-designed break-glass** riêng có custody và hậu kiểm. |
| Service-to-service job quan trọng. | Availability critical. | Grace/degraded policy có scope/time rõ, monitor và reconcile. |

**Đây là ví dụ định hướng, không phải policy universal.** Doanh nghiệp phải xác định mandatory vs optional signals, giới hạn degraded mode và cơ chế incident response.

### 25.3. Không dùng một số mặc định cho mọi missing signal

~~~text
Bad:
  missing riskScore -> 0 (low)
  missing device posture -> trusted

Better:
  riskEvaluation.status = UNAVAILABLE
  devicePosture.status = UNKNOWN
  evaluateDegradedPolicy(action, resourceSensitivity, subjectType)
~~~

### 25.4. Recovery không phá SoD/availability

Tài khoản break-glass được thiết kế để sửa IdP nên không thể phụ thuộc hoàn toàn vào IdP đang lỗi. Tuy nhiên không tự cấp `Permit` cho mọi admin API khi risk engine down. Chuẩn bị **recovery authority riêng, access scope, credential custody, alert/evidence offline và rotation/post-use verification**.

## 26. Signal taxonomy và JSON event mẫu

Một sự kiện normalization có thể như sau:

~~~json
{
  "signalId": "sig-2026-11588",
  "signalType": "FAILED_LOGIN_THEN_SUCCESS",
  "subject": {
    "identityId": "person-2048",
    "identityType": "HUMAN",
    "accountRef": "idp-user-9008"
  },
  "context": {
    "sessionRef": "session-882",
    "sourceSystem": "idp-prod",
    "resourceRef": "finance-portal",
    "tenantRef": "tenant-vn"
  },
  "observation": {
    "windowStart": "2026-11-23T09:00:00+07:00",
    "windowEnd": "2026-11-23T09:10:00+07:00",
    "failedLoginCount": 7,
    "successCount": 1,
    "baselineVersion": "auth-baseline-v5",
    "confidence": "MEDIUM"
  },
  "provenance": {
    "eventRefs": ["evt-1001", "evt-1002", "evt-1008"],
    "eventTime": "2026-11-23T09:08:00+07:00",
    "receivedAt": "2026-11-23T02:08:04Z",
    "schemaVersion": "behavior-signal-v2"
  },
  "lifecycle": {
    "subjectState": "ACTIVE",
    "assignmentRef": "finance-analyst-2026"
  },
  "privacy": {
    "classification": "SECURITY_TELEMETRY",
    "retentionPolicyRef": "security-signals-policy"
  }
}
~~~

**Đây là JSON minh họa nội bộ**, không phải schema chuẩn OAuth/SCIM/IdP hay giao thức trao đổi risk score phổ quát. Các giá trị `confidence` cần định nghĩa/đo lường; không suy `MEDIUM` tương đương một xác suất cụ thể.

### 26.1. Event risk decision cần tách riêng

~~~json
{
  "decisionId": "risk-dec-2026-992",
  "subjectIdentityId": "person-2048",
  "sessionRef": "session-882",
  "requestedAction": "finance:report.export",
  "targetResourceRef": "finance-reports-vn",
  "decision": "STEP_UP",
  "reasonCodes": [
    "AUTH_FAILURE_BURST",
    "UNFAMILIAR_CLIENT_CONTEXT",
    "SENSITIVE_EXPORT_REQUEST"
  ],
  "risk": {
    "score": 67,
    "scale": "EXAMPLE_0_100",
    "modelVersion": "risk-engine-v4",
    "featureFreshness": "CURRENT"
  },
  "policy": {
    "policyVersion": "iam-conditional-access-v9",
    "entitlementCheck": "PASSED",
    "soDCheck": "PASSED",
    "requiredAssurance": "PHISHING_RESISTANT_MFA"
  },
  "enforcement": {
    "status": "PENDING",
    "targetRef": "finance-portal"
  },
  "audit": {
    "evaluatedAt": "2026-11-23T09:08:10+07:00",
    "correlationId": "request-2026-9192"
  }
}
~~~

`STEP_UP` là **decision**; trường `enforcement.status=PENDING` nhắc rằng ứng dụng đích chưa chắc đã thực hiện thành công. Cần event **challenge succeeded/failed, action permitted/denied, session revoked** và target evidence khi đóng case.

### 26.2. Tránh lưu sensitive content

Không log raw password, OTP, full access token, refresh token, client secret, private key hoặc full session cookie. Với exports, có thể dùng **bytes/count/classification/resource reference** thay vì nội dung dữ liệu. Audit pipeline cần integrity, access controls và retention.

## 27. Pseudocode: pipeline tạo tín hiệu và chấm điểm

~~~text
function evaluateBehaviorRisk(request, trustedNow):
    identity = resolveAuthoritativeIdentity(request.subject)
    if identity missing or identity.state != ACTIVE:
        return DENY(reason="IDENTITY_INACTIVE")

    if not entitlementAllows(identity, request.action, request.resource):
        return DENY(reason="MISSING_ENTITLEMENT")

    if mandatorySoDConstraintViolated(identity, request):
        return DENY(reason="SOD_POLICY")

    eventWindow = loadNormalizedEvents(
        identity.id,
        request.sessionRef,
        requiredWindowFor(request.action)
    )

    quality = evaluateSourceFreshnessAndCompleteness(eventWindow)
    if quality.missingMandatorySignals:
        return degradedModeDecision(request, quality, trustedNow)

    features = computeFeaturesWithCorrectEventTimeSemantics(
        eventWindow,
        identity,
        request.resource,
        trustedNow
    )

    baseline = loadVersionedBaseline(
        identity.id,
        identity.currentAssignment,
        identity.kind
    )

    anomalies = compareFeaturesToBaseline(features, baseline)
    context = loadTrustedRiskContext(request, identity)

    risk = calibratedRiskModel(
        anomalies,
        context,
        request.action,
        request.resource
    )

    decision = policyEvaluate(
        identity,
        request.action,
        request.resource,
        risk,
        quality
    )

    auditDecisionWithSourceRefsAndPolicyVersion(decision)
    return decision
~~~

Đây là **pseudocode khái niệm**, không phải API chuẩn IAM. Cần xử lý transaction boundaries, idempotency, model drift, async updates, signed trust context và resource authorization tại target.

### 27.1. Không lưu score như attribute HRIS vĩnh viễn

`riskScore` thay đổi theo **thời gian, session, action và resource**. Không đồng bộ một score hiện thời thành `departmentRisk` trong HRIS rồi dùng nó làm role lâu dài. HRIS là nguồn authoritative cho employment/assignment; risk engine là nguồn evaluation có TTL/conditions.

### 27.2. Decision phải ràng buộc target và request

Một kết quả “Lan step-up thành công để xem ticket 123” không tự cho phép “Lan export bảng lương tenant khác”. Nếu dùng **risk decision token/capability**, ràng buộc đúng subject, audience, action, resource, session, issuedAt/expiry và replay controls.

## 28. Java minh họa: chính sách ưu tiên hard constraints

Đoạn Java bên dưới minh họa **quy tắc ưu tiên business/authorization hard deny trước risk outcome**. Không có network/IdP integration và **không phải risk scoring engine production**.

~~~java
import java.util.Objects;

public final class RiskGate {
    public enum Decision {
        PERMIT, STEP_UP, RESTRICT, DENY, REVIEW
    }

    public record Input(
            boolean identityActive,
            boolean entitlementValid,
            boolean soDAllows,
            boolean mandatorySignalsAvailable,
            int riskScore,
            boolean sensitiveAction
    ) {}

    public static Decision decide(Input in) {
        Objects.requireNonNull(in, "input");

        // Hard lifecycle, entitlement and non-waivable SoD checks first.
        if (!in.identityActive()
                || !in.entitlementValid()
                || !in.soDAllows()) {
            return Decision.DENY;
        }

        // Missing mandatory signals: no silent "risk=0" fallback.
        if (!in.mandatorySignalsAvailable()) {
            return in.sensitiveAction() ? Decision.DENY : Decision.REVIEW;
        }

        if (in.riskScore() < 0 || in.riskScore() > 100) {
            return Decision.REVIEW; // Invalid model output, not Permit.
        }

        // Training-only thresholds; NOT universal production policy.
        if (in.riskScore() >= 80) {
            return Decision.DENY;
        }
        if (in.riskScore() >= 60) {
            return Decision.RESTRICT;
        }
        if (in.riskScore() >= 30 && in.sensitiveAction()) {
            return Decision.STEP_UP;
        }
        return Decision.PERMIT;
    }
}
~~~

### 28.1. Giới hạn của Java demo

- `record` yêu cầu phiên bản Java hỗ trợ record (ví dụ Java 17); ví dụ không là code Spring Security tự động.
- Thang điểm/ngưỡng chỉ minh họa, **chưa hiệu chỉnh, không được đưa thẳng vào production**.
- Không xử lý identity binding, signature validation, model calibration, session binding hoặc RBAC resource level đầy đủ.
- `mandatorySignalsAvailable=false` cần **degraded-mode policy thực tế** và recovery path; ví dụ chỉ cho thấy không fail-open.
- `RESTRICT` phải được PEP triển khai đúng action; nếu PEP không làm được, cần policy khác.
- `STEP_UP` phải dẫn tới authentication assurance thực, sau đó **re-evaluate** trước khi Permit.
- Không có human oversight/appeal và audit code; hệ thống thật phải thêm.

### 28.2. Test unit tối thiểu

~~~text
Input: active=false, score=0             -> DENY
Input: role missing, score=0             -> DENY
Input: SoD violation, score=0            -> DENY
Input: sensitive=true, missingSignals    -> DENY in demo
Input: score=70, sensitive=true          -> RESTRICT in demo
Input: score=40, sensitive=true          -> STEP_UP in demo
Input: score=20, role valid              -> PERMIT in demo
Input: score=-1                          -> REVIEW
~~~

**Unit test của decision logic không chứng minh target đã thực thi.** Cần integration test với PEP, token/session lifecycle và target resource scope.

## 29. Streaming/event processing: at-least-once, duplicates và time windows

### 29.1. Một pipeline thực tế

~~~mermaid
flowchart LR
    SRC["IdP / PAM / API / SCIM events"] --> Q["Authenticated event bus"]
    Q --> VAL["Schema + provenance validation"]
    VAL --> DED["Idempotent dedup + identity binding"]
    DED --> WIN["Event-time windows + watermark"]
    WIN --> FEAT["Feature store with TTL"]
    FEAT --> BASE["Versioned baselines"]
    BASE --> RISK["Risk evaluator / policy service"]
    RISK --> PEP["PDP/PEP response"]
    PEP --> AUD["Immutable audit + analyst feedback"]
    AUD --> BASE
~~~

### 29.2. At-least-once delivery và duplicate feature counts

Một event retry có thể tạo hai messages. Nếu tăng `failedLoginCount10m` hai lần, risk có thể bị thổi phồng. Cần:
- Event IDs duy nhất theo source/stream.
- Dedup key và replay tolerance.
- Per-source sequence hoặc ingestion identifiers.
- Watermark xử lý events đến trễ.
- Idempotent feature updates.
- TTL rõ cho feature store.

Không mặc định “exactly once” ở broker đồng nghĩa **exactly once end-to-end** khi producer/consumer/retries khác nhau.

### 29.3. Out-of-order và late evidence

Một target API event tới sau 10 phút có thể cho biết session đã export nhạy cảm **trước** quyết định cho phép. Không sửa lịch sử decision để giả rằng detector đã biết trước. Ghi một **reassessment/correction event**:
- Decision at time T với signals có sẵn khi đó.
- Late signal received at T+10.
- New decision/remediation hiện tại.
- Incident scope và reason codes.
- Audit chain giữ cả hai.

### 29.4. Feedback loop phải được kiểm soát

SOC đóng alert là false positive không có nghĩa mọi event tương tự tương lai đều an toàn. Analyst feedback có thể:
- Gắn label cho training/threshold review.
- Gợi ý exception có scope/time.
- Tăng chất lượng baseline.
- Tránh lặp alert trùng một incident.

Nhưng **không tự động allowlist identity vĩnh viễn** khi một case được đóng. Thay đổi model/policy phải qua owner/versioned approval, đặc biệt với privileged access.

## 30. Case study A — Đăng nhập từ thiết bị mới và yêu cầu export

**Bối cảnh:** An là nhân viên Finance có `FinanceReportsReader` tại `finance-portal`. Lúc 08:30, An đăng nhập bằng thiết bị chưa đăng ký, dùng network khác thường. Sau đó An yêu cầu tải tất cả báo cáo có dữ liệu nhạy cảm.

### 30.1. Phân loại từng tín hiệu

| Quan sát | Loại | Cần xác minh |
| --- | --- | --- |
| Client/device lần đầu thấy. | Device context + novelty behavior. | Device registration và trust. |
| IP thuộc vùng/ASN chưa từng dùng. | Network context. | VPN/proxy, IP geo reliability. |
| User vừa nhập sai MFA hai lần. | Authentication behavior. | MFA method, attempt chain, user report. |
| Request bulk export vượt baseline. | Application behavior. | Business deadline, report/task authorization. |
| Resource classification = restricted. | Impact context. | Data owner policy. |
| Role hiện tại chỉ đọc báo cáo, không export bulk. | Entitlement check. | Đây là **hard deny** nếu thiếu permission. |

### 30.2. Quyết định đúng

Nếu An **không có entitlement export**, API trả **DENY** bất kể risk score. Nếu An có quyền export:
- IdP/API có thể yêu cầu phishing-resistant step-up.
- PEP kiểm user, tenant, scope, report IDs và policy.
- Anomaly cao có thể giới hạn lượng dữ liệu hoặc đưa export vào review.
- SOC có thể đối chiếu incident/change calendar và user verification.
- Audit lưu sources, decision, enforcement và follow-up.

### 30.3. Điều không nên kết luận

“An ở nước ngoài nên chắc chắn bị hack” là một kết luận quá mức: IP có thể nằm sau VPN. “An bấm MFA đúng nên mọi export đều hợp lệ” cũng sai: MFA là **authentication assurance**, không phải authorization cho dữ liệu.

### 30.4. Nếu là false positive

An đã được giao xuất báo cáo trước hạn kiểm toán. Security kiểm approval, cấp đúng `export` entitlement có thời hạn, ghi exception hợp lệ nếu cần và cập nhật context/baseline có kiểm soát. **Không allowlist toàn bộ hành vi tương lai** hoặc gỡ MFA cho cả Finance group.

## 31. Case study B — Mover vẫn được vào production nhờ direct grant

**Bối cảnh:** Bình từng là SRE, sử dụng `ProductionOperator` thường xuyên. HRIS chuyển Bình sang Support lúc 09:00. IAM gỡ group Ops tại IdP nhưng một **direct role assignment** trong cloud chưa được xóa.

### 31.1. Signals

- HRIS `MOVER_EFFECTIVE` lúc 09:00.
- IdP group `SRE-Production` đã removed.
- Cloud API `service:restart` được gọi lúc 09:20 bằng principal của Bình.
- Behavior engine thấy action **rất quen thuộc** theo baseline cũ.
- SCIM/connector target readback vẫn cho thấy direct permission.

### 31.2. Phân tích

Một detector chỉ xét **thống kê lịch sử** có thể bỏ qua rủi ro. Nhưng **HRIS assignment effectiveAt** khiến quyền Ops mất căn cứ. Cần:
1. Hard lifecycle/role policy chặn action không còn được phép.
2. IAM/IGA reconcile **direct grants, nested roles và resource policies**.
3. Revoke active PAM/JIT eligibility/session/token nếu liên quan.
4. Đánh giá action đã thực hiện sau cutoff.
5. Cập nhật baseline cho role Support.
6. Ghi rõ event source, readback và remediation.

### 31.3. Bài học

**Behavior signal không thể thay thế desired-state entitlement reconciliation.** Đối với Mover, điều từng bình thường có thể không còn hợp lệ ngay tại thời điểm hiệu lực thay đổi.

## 32. Case study C — OAuth client secret bị lộ, workload behavior đổi

**Bối cảnh:** `billing-etl-prod` là job hợp lệ dùng OAuth Client Credentials để cập nhật bảng summary vào ban đêm. Một client secret xuất hiện trong CI log; sau đó AS ghi token requests từ nguồn chưa nằm trong danh sách runner hợp lệ.

### 32.1. Behavioral signals của machine identity

- Client bắt đầu xin token ngoài schedule.
- Token endpoint thấy một source network/runner mới.
- `grant_type=client_credentials` hợp lệ nhưng call pattern sai contract.
- API requests tăng đột biến và truy cập một resource khác.
- Một request xin scope nhạy cảm hơn.
- Secret read event ở vault trùng thời điểm sự cố CI.

### 32.2. Quy trình response

- Xác định client ID, owner, secret version, allowed grant/scope.
- Đối chiếu AS logs, runner trust, workload ID và target API actions.
- Contain: revoke/rotate secret, giới hạn token issuance và permission theo incident playbook.
- Nếu attacker chiếm runner, xử lý compromised runtime/issuer trust; rotation một mình không đủ.
- Rà soát tokens đã phát, refresh/access sessions và resource authorization.
- Giữ job hợp lệ hoạt động bằng credential mới/cutover an toàn khi khả thi.
- Readback rằng secret cũ bị từ chối, quyền target đúng desired.
- Báo owner, Security và audit evidence.

### 32.3. Không nhầm human creator với runtime actor

Người từng tạo OAuth client có thể đã nghỉ. Token requests vẫn đại diện **machine principal**, không tự chứng minh người đó đã gửi. Attribution cần runtime/CI/cloud telemetry và chứng cứ thực tế. Song người đó từng có quyền đọc secret là **một hướng điều tra exposure**, không phải bằng chứng quy trách nhiệm.

## 33. Case study D — PAM JIT bất thường nhưng có incident hợp lệ

**Bối cảnh:** SRE trực ca kích hoạt privileged JIT lúc 02:00 để phục hồi cluster. Detector báo “ngoài giờ” và “rare GlobalAdmin use”.

### 33.1. Vì sao không được auto-lock đơn giản?

- Ca trực đêm là lịch hợp lệ.
- Incident severity cao.
- Break-glass/JIT có thể là đường duy nhất sửa outage.
- Khóa account có thể kéo dài thời gian phục hồi.
- Nhưng quyền GlobalAdmin vẫn có tác động lớn và cần audit chặt.

### 33.2. Quy trình phù hợp

1. Xác định incident ID, on-call roster và owner.
2. Kiểm approved emergency authority/approval route.
3. Chỉ activate role/action tối thiểu, hạn rõ.
4. Sử dụng PAM/JIT session logging, source/device trust.
5. Monitor commands/role modifications bất thường.
6. Khi incident đóng, revoke session/grant/token/credential theo policy.
7. Independent post-use review, target readback.
8. Nếu anomaly lệch cả incident scope, mở investigation/containment.

### 33.3. Giải quyết mâu thuẫn

**Risk-based access không nên hy sinh availability bằng cách khóa đường khẩn đã được thiết kế**, cũng không mặc định “incident đang mở ⇒ mọi action đều an toàn”. Cần kết hợp **business context, least privilege, time-bound authority và independent audit**.

## 34. Case study E — Leaver vẫn còn session tại SaaS

**Bối cảnh:** HRIS phát Leaver cho Cường lúc 17:00. IdP disable lúc 17:02, SCIM target trả HTTP 204 lúc 17:03; một SaaS local session từ trước vẫn thực hiện action lúc 17:15.

### 34.1. Hai lỗi thường gặp

1. IAM báo offboarding complete chỉ dựa vào IdP/SCIM response.
2. Behavior engine chỉ nhìn sign-in events mới; session cũ không đăng nhập lại nên **không có anomaly auth**.

### 34.2. Cần kiểm những gì?

~~~text
HRIS:         LEAVER effectiveAt 17:00
IdP:          DISABLED at 17:02
SCIM:         HTTP 204 at 17:03
SaaS app:     ACTIVE_SESSION at 17:15
Target API:   SENSITIVE_ACTION PERMITTED at 17:15
IAM closure:  REMEDIATION_REQUIRED
~~~

- Disable app-local session và revoke refresh/access token theo capability.
- Gỡ direct grants/nested group memberships.
- Đối soát source-of-authority và dynamic re-provision.
- Negative-test một action an toàn trong phạm vi được phép.
- Điều tra hành động sau cutoff và mở incident nếu cần.
- Chỉ `VERIFIED_CLOSED` khi actual access bị chặn đúng policy.

### 34.3. Behavior signal đóng vai trò gì?

Tín hiệu **“activity after Leaver effectiveAt”** là phát hiện hữu ích, nhưng **không được chờ nó xuất hiện** trước khi revoke. Hard JML trigger phải vận hành độc lập; signal giúp đo residual access, xác định đường bypass và phát hiện truy cập sau cutoff.

## 35. Case study F — Nhiều lần thất bại do lỗi ứng dụng, không phải tấn công

**Bối cảnh:** Một release mới làm ứng dụng gửi refresh-token request bằng credential cũ. AS ghi nhiều `invalid_client`, risk engine cảnh báo brute force đối với `orders-service-prod`.

### 35.1. Phân tích sai dễ gặp

“Có 10.000 lần thất bại thì chắc credential attack” bỏ qua khả năng retry loop. Cần:
- Deployment/change timeline.
- Client ID, credential version reference.
- Error category `invalid_client` vs network retry.
- Source runner và workload identity.
- Token requests per unique business operation.
- Recent rotation/expiration.
- AS logs và health metrics.

### 35.2. Response đúng

Nếu là bug deployment, sửa credential propagation/retry policy và bảo đảm secret cũ vẫn bị revoke theo kế hoạch. Không tắt toàn bộ detector hoặc allowlist mọi `invalid_client` của service. Giữ rule phát hiện **request từ nguồn ngoài runtime hợp lệ** và alert về high-privilege app-only grants.

### 35.3. Bài học

**Quality of context** quan trọng không kém feature count. Một signal có precision thấp gây **alert fatigue**, làm SOC khó phát hiện sự cố thật.

## 36. Ma trận kiểm thử behavior signal và risk-based access

| Test | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| **T1 — Known activity** | User active, role phù hợp, normal session. | Permit đúng scope, ghi decision tối thiểu. |
| **T2 — Missing entitlement** | Score thấp nhưng không có quyền export. | Deny do AuthZ, không cấp role mới. |
| **T3 — Leaver** | HRIS effective Leaver, score 0. | Hard deny/revoke theo JML. |
| **T4 — Mover** | User từng OpsAdmin, nay role khác. | Baseline epoch cập nhật; old grant bị revoke. |
| **T5 — Joiner cold start** | Device/app lần đầu, onboarding hợp lệ. | Không blanket deny; dùng peer/business context. |
| **T6 — MFA fatigue** | Nhiều prompts rồi một approval. | Step-up/incident assessment theo risk. |
| **T7 — Failed-success sequence** | Login failures rồi success từ same source. | Signal tạo đúng, không tự kết luận compromise. |
| **T8 — Unreliable geo** | VPN đổi location trong vài phút. | Context uncertainty, tránh auto convict. |
| **T9 — Token replay** | JWT cũ dùng sau risk revoke. | Đo target enforcement/revocation lag, remediation. |
| **T10 — Missing signal** | EDR offline, high-impact export request. | Degraded policy, không missing→trusted. |
| **T11 — PDP timeout** | Risk service unavailable. | Không fail-open privileged action. |
| **T12 — Recovery** | IdP/PAM outage, need break-glass. | Đường khẩn độc lập có scope/custody/audit. |
| **T13 — Dynamic baseline poisoning** | Export tăng dần trong nhiều tuần. | Hard rules/drift monitoring vẫn phát hiện misuse. |
| **T14 — Peer mismatch** | SRE so với nhân viên hành chính. | Không dùng cohort không phù hợp. |
| **T15 — Duplicate events** | Broker replay một login failure. | Idempotent feature count. |
| **T16 — Late event** | SCIM audit tới trễ. | Reassessment event, không sửa giả lịch sử. |
| **T17 — Clock skew** | Event time lệch collector. | Time provenance và sequence được giữ. |
| **T18 — OAuth workload** | Client credentials từ runner không được tin. | Alert/contain với issuer/subject/runner context. |
| **T19 — RPA batch** | Robot click nhanh, lịch hợp lệ. | Baseline theo bot contract, tránh human anomaly false positive. |
| **T20 — Shared credential** | Hai jobs dùng một key. | Không khẳng định actor cụ thể nếu attribution không đủ. |
| **T21 — API tenant change** | User/service gọi tenant không có quyền. | Resource-level deny dù score thấp. |
| **T22 — Sensitive PAM action** | Privileged role sửa audit policy. | JIT/approval/SoD; high-impact monitoring. |
| **T23 — JIT extension** | Renew nhiều lần không có incident. | Risk/expiry review; không standing privilege. |
| **T24 — Risk rule modified** | Admin hạ threshold trái phép. | Policy change audit + independent approval alert. |
| **T25 — Feedback abuse** | Analyst đóng alert để tạo allowlist vô hạn. | Feedback review, scoped exception/expiry. |
| **T26 — False positive appeal** | User hợp lệ bị chặn. | Recovery/appeal path, outcome feedback. |
| **T27 — Resource classification** | Same request tới data restricted vs public. | Impact-aware policy/decision. |
| **T28 — Low-confidence signal** | Một geo anomaly không có chứng cứ khác. | Step-up/review theo risk, không auto kết luận hack. |
| **T29 — Source integrity** | Attacker sửa log để ẩn request. | Tamper/gap detection, cross-source reconciliation. |
| **T30 — Session binding** | Step-up completed cho action A, dùng cho action B khác. | Re-evaluate action/resource policy. |
| **T31 — Post-deprovision activity** | Leaver token còn gọi API. | Residual access incident, target readback. |
| **T32 — Privacy** | Signal pipeline log plaintext OTP/token. | Validation fail, redaction/containment. |
| **T33 — Model score invalid** | Risk model trả NaN/âm/giá trị thiếu. | Error/degraded policy, không Permit mặc định. |
| **T34 — Target lacks restriction** | PDP trả RESTRICT nhưng API chỉ biết Permit/Deny. | Policy fallback rõ, không báo đã enforce. |
| **T35 — Rotated machine secret** | API vẫn 200 nhờ cached token sau V2 rotation. | Token acquisition/old-secret rejection được test riêng. |
| **T36 — Archived event** | Risk score được tính lại sau model update. | Giữ quyết định gốc + model/rule version, không rewrite audit. |

### 36.1. Test qua ba lớp

- **Detection tests:** signal/baseline đúng theo event input, duplicates/late arrivals.
- **Policy tests:** hard constraints không bị bypass, thresholds/step-up/restrict hợp lý.
- **Enforcement tests:** target thực sự chặn/giảm quyền, tokens/sessions cũ được xử lý.

Một unit test cho risk model **không chứng minh effective access** của ứng dụng đã được bảo vệ.

### 36.2. Dùng synthetic test thay vì dữ liệu riêng tư thật

Trong integration testing, tạo identities, sessions và events giả được ủy quyền. Không tải dataset khách hàng thật hoặc tái phát token production để “test exfiltration detector”. Kiểm thử production cần scope/runbook/approval, dùng negative tests không phá hủy khi phù hợp.

## 37. Đánh giá hiệu quả: precision, recall, calibration và drift

### 37.1. Những metric phát hiện

| Metric | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| **Precision** | Trong alerts được gắn positive, bao nhiêu thật sự được xác nhận theo label? | Label có thể thiếu/không đại diện. |
| **Recall** | Trong incidents thật đã biết, detector phát hiện được bao nhiêu? | Không quan sát được toàn bộ unseen attacks. |
| **False-positive rate** | Tỷ lệ trường hợp hợp lệ bị báo. | Định nghĩa population và action context. |
| **False-negative rate** | Tỷ lệ sự cố bỏ sót trong bộ đánh giá. | Hiếm khi biết toàn bộ thực tế. |
| **Alert volume per analyst** | Khả năng vận hành/triage. | Ít alerts không chắc bảo mật tốt. |
| **Time-to-detect** | Từ activity đến reliable signal/alert. | Clock skew và ingestion lag. |
| **Time-to-enforce** | Từ risk decision đến target thực sự chặn. | IdP state có thể khác API session. |
| **Calibration** | Risk score có tương quan phù hợp với outcome/risk band không? | Score không tự là xác suất. |
| **Coverage by identity type** | Human/service/privileged/RPA có telemetry và policy không? | 100% IdP users không bao phủ app-local/cloud NHI. |
| **Concept/model drift** | Hành vi hợp lệ và detector performance đổi theo thời gian. | Đổi lịch công việc, product release, attack adaptation. |
| **Challenge success rate** | Tỷ lệ step-up thành công/thất bại. | MFA bị ép nhiều làm trải nghiệm xấu. |
| **User friction** | Thời gian/challenges gây gián đoạn cho tác vụ hợp lệ. | Phải cân cùng security outcome. |
| **JML residual access** | Activity sau Mover/Leaver effectiveAt. | Không nên chờ signal để revoke. |
| **Reviewer overturn rate** | Quyết định tự động được SOC/owner sửa. | Overturn không luôn chứng minh model sai, có thể do missing context. |

### 37.2. Công thức phân loại minh họa

Nếu có bộ đánh giá với nhãn phù hợp:

\[
\text{Precision}=\frac{TP}{TP+FP},\qquad
\text{Recall}=\frac{TP}{TP+FN}
\]

Trong đó `TP` là true positives, `FP` false positives, `FN` false negatives. Nếu mẫu số bằng 0, metric cần đánh dấu **not defined**, không âm thầm điền 100%.

### 37.3. Không tối ưu chỉ một metric

Tăng recall bằng cách khóa mọi activity “khác thường” có thể khiến:
- Helpdesk quá tải.
- SRE không sửa được sự cố.
- RPA/ETL dừng không cần thiết.
- Người dùng tìm cách bypass an toàn.
- Analyst bỏ qua cảnh báo do quá nhiều false positives.

Cần trade-off theo **resource impact, workflow criticality, risk tolerance và human-review capacity**.

### 37.4. Model drift khi ứng dụng đổi tính năng

Một phiên bản mới có endpoint bulk report được phê duyệt. Detector cũ có thể coi tất cả use case mới là anomaly. Cần:
1. Gắn service deployment/version vào telemetry.
2. Theo dõi distribution shift và cohort.
3. Kiểm tra approval/business task.
4. Điều chỉnh baseline/threshold qua change governance.
5. Replay synthetic cases và regression tests.
6. Giữ model version cũ cho historical audit.

### 37.5. Đánh giá riêng nhóm NHI/privileged

Machine clients, PAM sessions, human web sessions có **base rates và hành vi khác nhau**. Một chỉ số tổng có thể che nhóm có false-negative cao. Nên báo cáo precision/coverage riêng theo identity type, action sensitivity và target platform.

## 38. Anti-patterns thường gặp trong behavior-driven access

| Sai lầm | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| “Login từ IP lạ ⇒ chắc chắn hack”. | False positives do VPN/NAT/geo. | Kết hợp session/device/action và confidence. |
| Dùng risk score thấp để bypass missing role. | Privilege escalation. | Hard RBAC/ABAC/SoD/JML deny trước scoring. |
| User Leaver vẫn được Permit vì device quen. | Access sau offboarding. | Lifecycle effectiveAt override baseline. |
| Mover vẫn giữ baseline role cũ. | Quyền không còn căn cứ bị hợp thức hóa. | Baseline epoch + entitlement reconciliation. |
| Xem mọi batch job chạy đêm là đáng ngờ. | NHI/RPA false positives. | Workload contract, schedules và owner. |
| Cộng tương quan “IP lạ, geo lạ, ASN lạ” ba lần. | Inflated score. | Feature dependence/correlation control. |
| Không theo dõi missing event source. | Silent false-low risk. | Freshness/completeness và degraded policy. |
| PDP timeout thì cho phép mọi admin action. | Fail-open bypass. | Risk-tiered fail-safe + recovery route riêng. |
| Đánh dấu account “đáng tin vĩnh viễn” sau một MFA. | Stale trust/session hijack. | Assurance TTL, continuous reevaluation. |
| Tin token JWT cũ sẽ bị revoke ngay sau IdP alert. | Residual API access. | Target enforcement/revocation-lag tests. |
| Dùng email làm identity key xuyên hệ thống. | Gộp nhầm người, nhất là rehire. | Stable IDs và effective identity binding. |
| Dùng client-provided `risk=0`. | Client tự spoof trust. | Trusted PDP/context, signed/bound claims. |
| Chỉ ghi score, không ghi reason/source. | Không giải thích hay audit được. | Reason codes, policy/model version, evidence refs. |
| Treat anomaly như phán quyết đạo đức. | Thiếu công bằng và sai nghiêm trọng. | Human review, privacy/fairness controls. |
| Thu raw keystrokes vô hạn “để ML tốt hơn”. | Privacy/data exposure. | Purpose-limited data minimization. |
| Mọi analyst có thể tự sửa threshold/allowlist. | Insider bypass/detection tampering. | SoD, approvals, integrity logs. |
| Auto-train cả incident activity. | Baseline poisoning. | Labeled data governance, drift limits. |
| Bật challenge MFA liên tục cho mọi anomaly. | MFA fatigue, gián đoạn. | Risk/action-aware step-up và recovery. |
| Dashboard risk PASS thay target readback. | False assurance. | Enforce + verify actual access. |
| Dùng một score cho mọi action/resource. | Không phân biệt public vs sensitive. | Resource-impact-aware policy. |
| Chỉ có IdP logs, bỏ app-local sessions và OAuth clients. | Blind spots. | Multi-source target/NHI telemetry. |
| Ủy quyền permanent exception cho mọi on-call. | Standing privilege. | Scoped/time-bound exception, JIT and audit. |
| Alert feedback tự tạo global allowlist. | Detector có thể bị lợi dụng. | Controlled model/policy change. |
| Không lưu decision version lúc model update. | Historical audit sai. | Immutable decision history and versioned model. |

## 39. Checklist triển khai Behavior signal cho IAM

### 39.1. Chuẩn bị nguồn và mục tiêu

- [ ] Xác định ranh giới: behavior signal vs device/network context vs lifecycle state.
- [ ] Có inventory IdP/SSO/PAM/SCIM/API/EDR/HRIS/CI và target audit coverage.
- [ ] Xác định use cases: credential theft, session hijack, privileged misuse, residual access.
- [ ] Phân loại human, privileged, service/workload, RPA và emergency identities.
- [ ] Stable identity binding và source-of-authority per attribute.
- [ ] Log source/time/receivedAt/schema/correlation IDs được chuẩn hóa.
- [ ] Không nhận client-provided claims làm trusted risk evidence.
- [ ] Có freshness/heartbeat/gap/duplicate/out-of-order controls.
- [ ] Dữ liệu được thu tối thiểu, có privacy/retention review.
- [ ] Business owner/risk owner được chỉ định cho policies.

### 39.2. Baseline, score và policy

- [ ] Chọn per-subject/peer/workload contract baseline có lý do.
- [ ] Cold-start Joiner và Mover baseline reset được xử lý.
- [ ] Loại historical activity không còn hợp lệ sau role change.
- [ ] Baseline/model/feature versions và training provenance được lưu.
- [ ] Có calibration, false positives/negatives và drift monitoring.
- [ ] Không cộng trùng signals tương quan mà không có kiểm soát.
- [ ] Hard deny cho Leaver, missing entitlement và SoD bắt buộc.
- [ ] Policy theo action/resource sensitivity và available controls.
- [ ] Missing signals có trạng thái UNKNOWN/STALE, không auto-low-risk.
- [ ] Threshold/allowlist changes qua approval/SoD và có audit.
- [ ] Có degraded-mode policy cho IdP/PDP/risk-service outage.

### 39.3. Enforcement và vận hành

- [ ] PEP có thể thực thi Permit/Step-up/Restrict/Deny đúng resource/action.
- [ ] Token/session lifetimes và revocation lag được đo ở target.
- [ ] API/object/tenant permissions được recheck khi cần.
- [ ] PAM/JIT/emergency flows có owner, limits và log độc lập.
- [ ] Service credentials/owner changes được liên kết JML.
- [ ] Mover/Leaver trigger gỡ quyền ngay theo effective state, không chờ anomaly.
- [ ] Readback/negative test cho quyền đã revoke ở target.
- [ ] Risk decision audit chứa reason/source/model/policy/target/outcome.
- [ ] User step-up/appeal và SOC investigation workflow hoạt động.
- [ ] Security incidents và feedback được dùng cải thiện model có quản trị.
- [ ] Không đóng `VERIFIED_CLOSED` khi app session/token/grant còn đường truy cập trái phép.
- [ ] Test tích cực, tiêu cực, outage, latency, race và false positives định kỳ.

## 40. Bài tập tự kiểm tra

### 40.1. Bài A — Behavior hay context?

Phân loại `failedLoginCount=7`, `deviceCompliant=false`, `resourceSensitivity=critical`, `geoIpCountry=SG`, `department=Finance` và `employeeState=Leaver` thành behavior, context, identity attribute hoặc lifecycle hard state. Những dữ liệu nào không được coi là risk “hành vi xấu” chỉ vì có giá trị khác thường?

### 40.2. Bài B — Risk thấp nhưng quyền không đủ

User có risk score 9/100 nhưng không có `payments:refund`. Có được cấp quyền refund vì device đã verified? Nêu thứ tự hard authorization, risk evaluation và PEP enforcement.

### 40.3. Bài C — Joiner cold start

Nhân viên mới mở 15 ứng dụng trong hai giờ onboarding và dùng device lần đầu. Detector coi 15 new apps là anomaly. Hãy thiết kế onboarding context/peer baseline, MFA và điều kiện nào vẫn nên chặn hard.

### 40.4. Bài D — Mover và baseline cũ

SRE đổi sang Finance nhưng tiếp tục dùng quyền production direct grant. Vì sao “họ luôn làm điều này” không phải cơ sở Permit? Phác họa JML event, target reconciliation và baseline epoch.

### 40.5. Bài E — Leaver còn access token

IdP disabled lúc 17:00, nhưng access token cũ vẫn gọi API lúc 17:25. Risk engine phát anomaly lúc 17:30. Hãy chỉ ra đâu là trigger bắt buộc và đâu là phát hiện sau, cùng evidence cần để đóng offboarding.

### 40.6. Bài F — Impossible travel

Một user đăng nhập từ hai IP ở hai nước trong 7 phút. Những nguyên nhân nào ngoài account takeover có thể gây signal này? Bạn sẽ yêu cầu step-up hay deny trong trường hợp resource public, internal và restricted như thế nào?

### 40.7. Bài G — OAuth Client Credentials

`billing-etl` bình thường chạy 01:00, bỗng xin token từ runner lạ lúc 15:00. Vì sao không nên gán hoạt động này cho người từng tạo secret? Thiết kế source binding, token log, owner handover và incident response.

### 40.8. Bài H — RPA và false positive

RPA xử lý invoice hàng tháng có thể gửi 50.000 UI actions trong ca chạy. Làm sao tách workload contract khỏi human behavior baseline và vẫn giữ transaction SoD/security monitoring?

### 40.9. Bài I — Feedback poisoning

Một attacker cố tăng request rate mỗi ngày để hệ thống tự học mức mới. Đề xuất hard policy boundary, training data governance, drift monitoring và independent target audit.

### 40.10. Bài J — PDP outage

Risk service mất mạng khi user yêu cầu export 2 triệu hồ sơ, trong khi một service chỉ đọc metadata công khai vẫn chạy. Thiết kế degraded policies khác nhau và explain vì sao blanket fail-open hoặc fail-closed đều có thể có vấn đề.

### 40.11. Bài K — Một score, hai actions

Cùng user có score 55/100. Họ muốn xem ticket được giao và muốn tạo GlobalAdmin credential. Có nên có cùng quyết định không? Hãy xét action impact, hard permissions, SoD/PAM/JIT, step-up và audit.

### 40.12. Bài L — Token revocation lag

AS báo session revoked lúc 09:10 nhưng API tự xác minh JWT có `exp=10:00`. Nêu vì sao dashboard IdP “blocked” chưa đủ, và các cơ chế request-time authorization/deny/token TTL cần đánh giá.

### 40.13. Bài M — Data minimization

Đề xuất dùng toàn bộ phím gõ, nội dung email và lịch sử GPS dài hạn để tìm anomaly. Hãy lập risk/privacy assessment và thiết kế bộ features tối thiểu thay thế.

### 40.14. Bài N — SIEM integrity

Detector báo score thấp vì IdP feed đã im lặng 60 phút. Hãy phân biệt “không có failed logins” với “không có logs”, đề xuất heartbeat, gap detection và xử lý UNKNOWN.

### 40.15. Bài O — Đo chất lượng

Model mới tăng recall từ 70% lên 85%, nhưng false positives khiến SOC quá tải và emergency workflows bị block. Làm sao đánh giá trade-off theo action, precision, user friction, recovery availability và model drift?

### 40.16. Bài P — Case audit

Một user bị deny export và Security override để đáp ứng deadline. Những fields nào cần trong decision log, approval/exception, modelVersion, reason codes, target enforcement và post-incident access review để bảo đảm traceability?

**Điểm cần ghi nhớ:** **Behavior signal** trong **Risk-based access** là **tín hiệu quan sát về hành vi của human hoặc machine identity theo thời gian và ngữ cảnh**, không phải kết luận độc lập rằng một chủ thể đáng tin hay nguy hiểm. Cần tách **raw events → features/baseline → anomalies → risk assessment → policy decision → PEP enforcement**, với **identity binding, confidence, freshness, privacy, audit và review**. Trong IAM **Joiner–Mover–Leaver**, **employment/assignment/entitlement và SoD hard rules luôn có thẩm quyền cao hơn score**; risk-based checks chỉ tăng khả năng phát hiện, step-up, hạn chế và phản ứng với hành vi rủi ro trong phạm vi quyền hợp lệ. Đối với **IdP/SSO, OAuth tokens, SCIM, RBAC/ABAC, PAM/JIT và service/workload identities**, phải xác minh **actual target session/token/grant** và đo **decision-to-enforcement latency**, tránh để **risk score đẹp nhưng quyền tồn dư vẫn dùng được**.





