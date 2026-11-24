# On-call IAM: vận hành trực ca, phân loại sự cố và bảo vệ vòng đời danh tính

## 1. On-call IAM là gì và tại sao cần?

**On-call IAM** là chế độ trực vận hành để đội phụ trách **Identity and Access Management (IAM)** có thể tiếp nhận, đánh giá, phối hợp và xử lý kịp thời những tình huống về danh tính, xác thực, phân quyền hoặc thu hồi truy cập ngoài giờ làm việc thông thường. Người trực không chỉ “mở khóa tài khoản”; họ còn phải bảo vệ hệ thống khi IdP gặp sự cố, credential bị lộ, provisioning thất bại hoặc tài khoản đã nghỉ việc vẫn còn quyền.

Trong chương **IAM operations** của module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, on-call gắn với toàn bộ **Joiner–Mover–Leaver (JML)**, từ xác minh danh tính, tạo tài khoản/cấp quyền, cập nhật quyền khi đổi vai trò đến thu hồi khi rời tổ chức. Trực ca phải hiểu các phụ thuộc **Identity Provider (IdP), Single Sign-On (SSO), SCIM, RBAC/ABAC, tài khoản dịch vụ, PAM, audit** và phải ưu tiên giảm **quyền truy cập tồn dư**.

Ba kết quả quan trọng của một ca trực tốt:

1. **Tính sẵn sàng:** người dùng hợp lệ và dịch vụ trọng yếu có thể xác thực/truy cập theo chính sách hoặc được hỗ trợ qua phương án khẩn cấp đã phê duyệt.
2. **Tính an toàn:** quyền không còn hợp lệ được chặn kịp thời; sự cố không được “sửa” bằng cách tắt MFA, tăng quyền vô điều kiện hay bật lại người đã nghỉ.
3. **Tính truy vết:** mỗi quyết định có người chịu trách nhiệm, timestamp, incident ID, bằng chứng kỹ thuật, đường escalation và trạng thái follow-up.

**Sau bài học, bạn có thể** tổ chức lịch trực Primary/Secondary, lập checklist trước và sau ca, triage cảnh báo IAM, phân cấp P0–P3 theo tác động/rủi ro, áp runbook xử lý JML/SSO/provisioning/credential và bàn giao những sự cố chưa hoàn tất mà không mất ngữ cảnh.

> **Lưu ý:** Các mức độ ưu tiên, SLA, thời gian phản hồi và cơ chế cảnh báo trong tài liệu chỉ là mô hình tham chiếu. Hệ thống thực phải tuân thủ SLA/SLO, chính sách bảo mật, tổ chức nhân sự và công cụ đang dùng; không tự coi một ví dụ là quy định bắt buộc.

## 2. Phạm vi của ca trực IAM

### 2.1. Các nhiệm vụ thường thuộc on-call

| Nhóm | Tín hiệu | Mục tiêu xử lý |
|---|---|---|
| **IdP/SSO** | Đăng nhập lỗi hàng loạt, OIDC/SAML thất bại, MFA provider không khả dụng | Khoanh vùng, khôi phục xác thực đúng chính sách |
| **Directory/account** | Account lockout storm, directory replication lỗi, user active sai | Xác định nguồn, tránh mở khóa nhầm |
| **Provisioning** | SCIM/API trả 401/403/409/429/5xx, queue tích tụ | Khôi phục đồng bộ, đọc lại actual state |
| **JML Joiner** | Người mới chưa tạo account hoặc thiếu quyền thiết yếu | Cấp đúng vai trò sau identity proofing/approval |
| **JML Mover** | Quyền mới thiếu, quyền cũ chưa gỡ, SoD conflict | Sửa delta cấp/thu hồi, giảm residual access |
| **JML Leaver** | Nhân viên/nhà thầu đã nghỉ vẫn active tại SaaS, còn session/token | Ưu tiên chặn lối truy cập và kiểm chứng |
| **Access compromise** | Credential lộ, sign-in đáng ngờ, token hoặc role admin bị lạm dụng | Containment, phối hợp SOC và revoke |
| **Privileged/emergency** | PAM/JIT không hoạt động, cần break-glass để khôi phục hệ thống | Kích hoạt có phê duyệt, giới hạn và hậu kiểm |
| **Service identity** | Workload không lấy được token, secret rotation gây outage | Khôi phục an toàn mà không dùng admin cá nhân |
| **Audit/compliance** | Thiếu log IAM trọng yếu, thay đổi quyền ngoài workflow | Bảo vệ bằng chứng, xác định owner và escalation |

### 2.2. Những việc on-call không tự ý thực hiện

- Tự cấp quyền admin hoặc bỏ quy trình phê duyệt vì ticket được đánh dấu “urgent”.
- Bật lại tài khoản đang **Terminated, Suspended hoặc security hold** khi chưa có lệnh hợp lệ từ nguồn chủ quản.
- Vô hiệu hóa MFA, Conditional Access, xác minh chữ ký OIDC/SAML hoặc audit diện rộng để tránh báo lỗi.
- Dùng mật khẩu, OTP, recovery code, token của người khác để “thử” hoặc yêu cầu người dùng gửi credential qua chat.
- Xóa dữ liệu/account theo hàng loạt khi chưa xem retention, legal hold, workload dependency và approval.
- Chỉnh policy dùng chung ngoài quyền hạn on-call, vượt quá phạm vi incident/change.

Với trường hợp vượt quyền hạn, nhiệm vụ của người trực là **containment được phép, bảo vệ chứng cứ và chuyển đúng owner**, không phải tự hoàn thành mọi thao tác bằng mọi giá.

## 3. Kiến trúc phụ thuộc cần nắm khi trực

~~~mermaid
flowchart LR
    HR[HRIS / Sponsor] --> EVT[Sự kiện Joiner - Mover - Leaver]
    EVT --> IAM[Bộ điều phối IAM]
    POLICY[RBAC / ABAC / Approval] --> IAM
    IAM --> IDP[IdP / Directory]
    IDP --> MFA[MFA / Risk Engine]
    IDP -->|OIDC / SAML SSO| APP[Ứng dụng SaaS / Nội bộ]
    IAM -->|SCIM / Connector| APP
    IAM --> PAM[PAM / JIT / Break-glass]
    IAM --> WORK[Service Accounts / Workload]
    APP --> LOC[Local Role / Token / Session]
    IDP --> LOG[Audit / SIEM / Monitoring]
    APP --> LOG
    PAM --> LOG
    WORK --> LOG
    LOG --> PAGE[Alert Routing / On-call]
    PAGE --> IC[Primary / Secondary / SOC / SRE]
~~~

**Phân biệt hai luồng chính:**

- **Authentication:** IdP/SSO/MFA xác nhận người đăng nhập, phát token hoặc assertion, rồi ứng dụng tạo phiên. SSO thành công chưa chắc user đã được ứng dụng provision hoặc có quyền phù hợp.
- **Provisioning/authorization:** JML, RBAC/ABAC và SCIM/API tạo/gỡ account, nhóm, role và entitlement ở target. Connector trả 2xx không đồng nghĩa mọi role hay session đã đổi; cần **readback actual state** và khi cần kiểm tra **effective access**.

Điều này quyết định tuyến escalation: lỗi IdP làm nhiều app không xác thực được khác với **chỉ một SaaS trả 403** sau khi IdP đã cấp token thành công; một user không vào được vì thiếu role khác với user bị khóa do security policy hoạt động đúng.

## 4. Tổ chức đội trực: Primary, Secondary và các vai trò liên quan

| Vai trò | Trách nhiệm | Khi cần chuyển tiếp |
|---|---|---|
| **Primary On-call IAM** | Nhận pager, xác nhận tín hiệu, triage, mở incident và thực thi runbook được phép | Khi vượt phạm vi, không thể xác minh hoặc có nguy cơ cao |
| **Secondary / Backup IAM** | Hỗ trợ kỹ thuật, nhận ca khi Primary không phản hồi, kiểm tra chéo thay đổi nhạy cảm | Khi Primary quá tải, không có đủ quyền hoặc cần second pair of eyes |
| **Incident Commander (IC)** | Điều phối sự cố lớn, quyết định severity, liên lạc và chuyển trạng thái | Khi ảnh hưởng nhiều hệ thống, nhiều nhóm hoặc cần emergency change |
| **SOC / Security Duty** | Xác minh tấn công, bảo vệ bằng chứng, ra quyết định containment bảo mật | Khi credential bị lộ, account takeover hoặc hoạt động đáng ngờ |
| **SRE/Platform/Network** | Điều tra hạ tầng, DNS, TLS, directory, queue, API availability | Khi root cause vượt IdP config hoặc là platform outage |
| **Application Owner** | Kiểm tra local account, role, session, API key và business impact | Khi SCIM chưa đủ để revoke hoặc app báo sai quyền |
| **HR / Contractor Sponsor** | Xác nhận nguồn danh tính, loại JML, ngày hiệu lực, trạng thái hợp lệ | Khi cần xác định Leaver, Mover, rehire hoặc sai nguồn |
| **PAM / Privileged Access Owner** | Quản lý tài khoản đặc quyền, đường break-glass, session privileged | Khi cần khôi phục quyền quản trị có kiểm soát |

### 4.1. Không để một người vừa yêu cầu vừa duyệt đặc quyền

Với thay đổi nhạy cảm, **separation of duties (SoD)** phải được giữ theo policy: người thực thi không mặc nhiên là người phê duyệt. Ngoài giờ, tổ chức cần định nghĩa kênh approval thay thế trước khi xảy ra sự cố (IC, Security Duty, application owner hoặc người trực được ủy quyền), tránh “không có ai nên tự duyệt”.

### 4.2. Luồng liên lạc dự phòng

Runbook phải có kênh gọi điện/on-call bridge và danh bạ escalation hoạt động **kể cả khi IdP/SSO/email nội bộ bị lỗi**. Không chỉ lưu toàn bộ thông tin khôi phục trong một wiki yêu cầu đăng nhập vào chính IdP có thể mất khả dụng. Bản dự phòng phải bảo vệ quyền đọc, bí mật và được kiểm thử.

## 5. Thiết kế lịch trực và nguyên tắc chuyển ca

### 5.1. Lịch trực cần thể hiện

- Khung thời gian ca theo **múi giờ rõ ràng**, ngày lễ và lịch nghỉ; tránh hiểu sai giờ UTC.
- **Primary** và **Secondary** riêng, cùng phương án dự phòng nếu cả hai mất kết nối.
- Phân loại trách nhiệm của đội IAM so với SOC/SRE/Support.
- Điều kiện gọi ngoài giờ, ứng dụng/trạng thái ưu tiên và giới hạn workload.
- Người chịu trách nhiệm các incident **đang mở** khi đổi ca.
- Kênh pager chính và dự phòng; cách xác nhận alert thực sự đến người trực.
- Mẫu handoff, cách tìm runbook, dashboard, inventory và chính sách truy cập.

Không công bố thông tin liên lạc cá nhân hay lịch bảo mật trên kênh công khai. Chỉ người cần thiết được xem lịch đầy đủ và phương án truy cập khẩn.

### 5.2. Trước ca: readiness checklist

1. Xác nhận ca trực trên hệ thống phân công, người backup, cách liên lạc và phạm vi trực.
2. Kiểm tra quyền IAM **thông thường** cần thiết để xem dashboard, log và ticket; không giữ admin thường trực chỉ vì on-call.
3. Kiểm thử an toàn cơ chế pager/ack, kênh incident bridge và đường gọi Secondary.
4. Kiểm tra dashboard IdP/SSO/MFA, SCIM provisioning, JML backlog, PAM, secret manager và log pipeline.
5. Xem các sự cố đang mở, thay đổi gần đây (IdP signing key, policy, connector credential, SCIM mapping), maintenance windows và deployment sắp diễn ra.
6. Xác nhận **runbook và emergency access path** có thể tìm được; không tự kích hoạt break-glass để “thử” ngoài exercise đã phê duyệt.
7. Đọc danh sách target/owner ngoại lệ, Leaver pending revoke, drift privileged và deadline cần xử lý trong ca.
8. Ghi lại trạng thái ban đầu và rủi ro được bàn giao.

### 5.3. Cuối ca: handoff tối thiểu

Một ca chỉ hoàn thành khi người nhận **xác nhận** đã nhận các việc còn mở, đặc biệt Leaver chưa thu hồi xong hoặc ngoại lệ quyền admin. Không chỉ để ghi chú trong chat rồi offline.

| Nội dung cần bàn giao | Ví dụ thông tin |
|---|---|
| Incident/ticket | ID, severity, owner, trạng thái, thời điểm mở |
| Tác động | IdP region nào, app nào, bao nhiêu nhóm người bị ảnh hưởng |
| Điều đã biết | Dữ liệu nguồn, triệu chứng, log/event ID, điều không chắc chắn |
| Thao tác đã làm | Containment, rollback, retry, revoke, approver, evidence |
| Quyền/truy cập còn tồn dư | Target, session/token/credential, mức rủi ro, deadline |
| Việc tiếp theo | Ai làm gì, thời điểm check lại, điều kiện escalation |
| Liên hệ | Owner ứng dụng, IC/SOC/SRE và backup |

## 6. Alert routing và phân loại tín hiệu

### 6.1. Các nguồn cảnh báo IAM

| Nguồn | Cảnh báo khả dụng | Nguy cơ false positive |
|---|---|---|
| **IdP sign-in logs** | Tăng login failure, MFA errors, token issuance failure | User nhập sai password, thay đổi lưu lượng |
| **SAML/OIDC app telemetry** | Invalid signature, redirect mismatch, callback lỗi | Chỉ một app hỏng sau release |
| **SCIM/API connector** | Retry tăng, HTTP 4xx/5xx/429, queue delay | Vendor rate limit theo lịch |
| **JML orchestrator** | Leaver chưa deprovision, Mover còn quyền cũ | Event source đến trễ hoặc mapping đổi |
| **PAM/SOC** | Unexpected admin role, break-glass usage, suspicious session | Bài test được duyệt nhưng thiếu event tag |
| **Directory** | Account lockout storm, replication delay, credential backend timeout | Scheduled job dùng secret cũ |
| **Secret manager/workloads** | Key rotation lỗi, token exchange 401/403, secret read bất thường | Workload deploy version mới |
| **Reconciliation/access reviews** | Orphan account, excess entitlement, expired guest | ID mapping sai, workload hợp lệ nhưng ít dùng |

### 6.2. Chống “pager fatigue”

Không nên page P0 cho mọi lỗi đăng nhập của một user. Alert cần **ngưỡng phù hợp baseline**, chiều thời gian, scope, khả năng ảnh hưởng và chất lượng dữ liệu. Các sự kiện mức thấp có thể đi vào queue giờ hành chính; cảnh báo bảo mật có rủi ro cao vẫn cần tuyến escalation riêng.

Gợi ý phân tầng:

- **Page ngay:** nghi compromise admin đang hoạt động, Leaver khẩn còn truy cập dữ liệu nhạy cảm, mất SSO diện rộng, thất bại revoke quyền trọng yếu, break-glass usage bất thường.
- **Page theo mức tác động:** SCIM backlog kéo dài qua deadline JML, MFA lỗi diện rộng, connector không hoạt động ở ứng dụng thiết yếu.
- **Ticket/queue:** drift ít nhạy cảm có owner, user lockout đơn lẻ, account review định kỳ không có dấu hiệu abuse.

Tuyến page phải tách rõ **hệ thống đang down** với **phát hiện an ninh**; nếu một sự kiện vừa ảnh hưởng khả dụng vừa nghi tấn công, IAM và SOC cần cùng điều phối.

## 7. Severity: mức ưu tiên và quyết định escalation

| Mức tham khảo | Tình huống điển hình | Hành động ban đầu |
|---|---|---|
| **P0 / Critical** | IdP diện rộng ngừng phát phiên mới cho dịch vụ trọng yếu; admin account bị chiếm quyền; Leaver khẩn còn quyền nhạy cảm đang hoạt động | Ack khẩn, gọi IC/SOC/SRE theo quy trình, containment ngay trong quyền hạn |
| **P1 / High** | MFA lỗi ảnh hưởng nhiều đội; Mover giữ quyền admin cũ trái SoD; deprovision SaaS quan trọng thất bại | IAM + owner đích xử lý ưu tiên, giám sát tới khi quyền được xác minh |
| **P2 / Medium** | Một ứng dụng SAML lỗi sau thay cert; nhóm Joiner không có role làm gián đoạn công việc | Triage, sửa cấu hình/provisioning theo change, xác minh và cập nhật người dùng |
| **P3 / Low** | User lockout đơn lẻ hoặc drift có owner, không ảnh hưởng bảo mật tức thì | Ticket hỗ trợ hoặc chuyển queue giờ hành chính |

**Chú ý:** bảng trên là ví dụ, không phải thời gian đáp ứng bắt buộc. Severity nên kết hợp **business impact, security impact, số người/tài nguyên bị ảnh hưởng, độ nhạy dữ liệu, thời điểm JML có hiệu lực, khả năng còn truy cập trái phép**.

### 7.1. Khi nào cần nâng severity?

Nâng khi phát hiện privilege escalation, exfiltration, khóa ký IdP bị nghi lộ, session Leaver còn sống, phạm vi lỗi lan từ một ứng dụng sang toàn tenant, thao tác khắc phục gây outage mới hoặc cơ chế break-glass không hoạt động. Không giữ P2 chỉ vì ticket ban đầu gắn P2.

### 7.2. Khi nào giảm severity?

Giảm sau khi có bằng chứng containment và tác động đã hạn chế, không phải chỉ vì “ít ticket hơn”. Có thể **dịch vụ đã phục hồi** nhưng **security remediation** vẫn chưa xong; phải giữ issue con và owner/deadline rõ ràng.

## 8. SOP-OC01 — Nhận page, ACK và dựng timeline

**Trigger:** Pager, alert manager, support escalation hoặc thông báo sự cố khẩn từ SOC/owner.

**Owner:** Primary IAM; Secondary tự nhận nếu Primary không ACK theo chính sách.

1. **ACK** theo công cụ trực ca và ghi thời điểm nhận; xem chính xác alert rule, target, khoảng thời gian và biểu đồ.
2. **Xác minh tính thật:** có lỗi hạ tầng, người dùng bị ảnh hưởng hay dữ liệu quan sát chỉ là nhiễu? Không thử login nhiều lần bằng account người dùng thật gây lockout.
3. **Mở/ghép incident:** tránh tạo nhiều incident cho cùng root cause, gắn `incident_id` và correlation/request ID.
4. **Xác định blast radius:** region, tenant, ứng dụng, nhóm người, service identities, đặc quyền, loại dữ liệu.
5. **Xác định thời điểm bắt đầu và thay đổi gần nhất:** deployment IdP, rotate signing key, policy, DNS, directory, SCIM, HR event và PAM change.
6. **Phân loại kỹ thuật:** IdP/SSO, MFA, directory, SCIM/provisioning, authorization, credential, cloud IAM hoặc JML source.
7. **Đánh giá Security:** có Leaver đang active, token/credential nghi lộ, grant admin bất thường hay dấu hiệu abuse không?
8. **Chọn severity và liên hệ backup/IC/SOC/SRE/owner** đúng bảng escalation.
9. **Bảo vệ bằng chứng:** ID sự kiện, timestamps có múi giờ, log đã che secret, trạng thái before/after. Không copy token, cookie, password, OTP hoặc nội dung nhân sự nhạy cảm vào ticket.
10. **Thông báo trạng thái ban đầu:** mô tả sự cố xác nhận được, phạm vi biết được, hành động containment, phần chưa rõ và cập nhật tiếp theo theo cadence tổ chức.

### 8.1. Mẫu timeline tối thiểu

~~~yaml
incident_id: IAM-ONCALL-EXAMPLE-901
timezone: Asia/Ho_Chi_Minh
event_type: SSO_FAILURE
first_observed_at: "2026-11-23T21:10:00+07:00"
alert_fired_at: "2026-11-23T21:11:00+07:00"
primary_ack_at: "2026-11-23T21:12:00+07:00"
scope:
  tenant: corporate-idp
  applications:
    - employee-portal
    - payroll-app
observed_symptoms:
  - oidc-token-endpoint-timeout
  - signin-new-session-failure
initial_severity: P1
owner: iam-primary-oncall
escalation:
  - sre-platform-oncall
  - soc-duty-officer
evidence_refs:
  - idp-signin-event-904
  - app-trace-211
status: INVESTIGATING
~~~

Đây là ví dụ giả lập, không chứa dữ liệu bí mật. Cần giữ phần “fact” tách khỏi “hypothesis”; không ghi “IdP down” nếu mới chỉ biết một ứng dụng báo không thể đăng nhập.

## 9. SOP-OC02 — Quy trình triage 5 câu hỏi

1. **Ai đang bị ảnh hưởng?** Một account, một role, ứng dụng, region, toàn tenant hay các service accounts?
2. **Lỗi xảy ra ở bước nào?** HR event, provisioning, IdP authentication, MFA challenge, OIDC/SAML, app authorization hay API resource?
3. **Desired state là gì?** User đang Active/Mover/Terminated? Role theo RBAC/ABAC là gì? Có approval/expiry/SoD không?
4. **Actual và effective access hiện thế nào?** Tài khoản còn active, role direct/inherited, local grants, session/token hoặc API key còn hiệu lực không?
5. **Đường giảm rủi ro an toàn là gì?** Retry có kiểm soát, sửa mapping, revoke ở target, dùng runbook khẩn được duyệt, escalation SOC hoặc tạm dừng cấp quyền?

### 9.1. Bảng chẩn đoán nhanh

| Triệu chứng | Điểm cần đọc | Kết luận sơ bộ và tuyến owner |
|---|---|---|
| Tất cả app SSO timeout | IdP health, network/DNS/TLS, MFA, directory | IAM + SRE/IdP owner |
| Chỉ một app lỗi redirect | OIDC redirect URI, SAML ACS, cert, metadata | IAM + application owner |
| IdP login thành công, app báo user missing | SCIM provisioning, app account mapping | IAM connector + app owner |
| App trả 403 nhưng có user | RBAC/ABAC, claim, policy, role cục bộ | App owner + IAM policy |
| Nhiều user lockout cùng lúc | Retry source, stale credential, SOC telemetry | IAM + SOC/Platform |
| Leaver app còn active | HR state, IdP, SCIM revoke, local login/token | IAM + app owner + SOC nếu nhạy cảm |
| Secret/service principal báo 401 | Vault rotation, token/credential, scope, trust | Platform/Workload owner |
| Break-glass được dùng ngoài lịch | PAM events, approval, session/actor | PAM + SOC |

Không dùng cùng một biện pháp cho mọi lỗi “Access denied”. Một **403 do policy đúng** không phải lý do cấp thêm admin; một **401 do connector secret hết hạn** không thể sửa bằng cách gỡ MFA của người dùng.

## 10. SOP-OC03 — Incident IdP/SSO/MFA ngoài giờ

### 10.1. Khoanh vùng

1. Đọc **sign-in logs** theo request/correlation ID, failure code, thời gian và app.
2. So sánh đăng nhập mới với session đang còn tồn tại; app có thể vẫn hoạt động với cookie/token cũ.
3. Kiểm tra **một ứng dụng khác dùng cùng IdP** bằng tài khoản thử nghiệm được phép để phân biệt lỗi nền tảng với lỗi app.
4. Kiểm tra network/DNS/TLS, issuer, endpoint, JWKS/signing key/certificate, SAML metadata, directory và MFA provider.
5. Kiểm tra thay đổi gần nhất: rotation chứng chỉ, client secret, Conditional Access, app registration, time skew và policy mapping.
6. Với spike login failure, phối hợp SOC kiểm tra password spraying/credential abuse, không mặc định là outage.

### 10.2. Khôi phục theo đúng lớp

| Lớp lỗi | Hướng xử lý |
|---|---|
| Network/DNS/TLS | SRE/Network owner khôi phục đường kết nối theo change đã duyệt; không tắt TLS verification |
| Directory/backend | Kiểm tra health/replication/password validation và nguồn account |
| MFA | Kiểm tra provider/policy, dùng kênh recovery có identity proofing; không tắt MFA toàn tenant |
| OIDC | Kiểm tra redirect URI, client authentication, issuer, audience, signing keys và session |
| SAML | Kiểm tra ACS, entity ID, audience, signature/certificate, thời gian assertion |
| App authorization | Xác minh user/role SCIM, group, RBAC/ABAC, direct grants và phiên cũ |
| IdP regional outage | Xem failover/continuity đã được kiểm thử, cần IC/Security và audit |

**Không** vô hiệu hóa kiểm tra chữ ký JWT/SAML, issuer, audience hoặc hết hạn chỉ để giảm số lỗi đăng nhập. Nếu phải dùng break-glass, áp SOP khẩn cấp và xác nhận thu hồi sau incident.

### 10.3. Mốc đóng nhánh dịch vụ

Canary đăng nhập mới đúng policy → MFA và claims chính xác → ứng dụng tạo session và thực hiện hành động hợp lệ → kiểm tra cảnh báo lỗi trở về mức bình thường → xử lý backlog JML còn tồn. Không kết luận IAM hoàn toàn phục hồi khi chỉ login thành công nhưng Leaver chưa được revoke.

## 11. SOP-OC04 — Xử lý provisioning/SCIM thất bại

**Tín hiệu:** job FAILED, event treo queue, SCIM 401/403/409/429, 5xx hoặc timeout; user thiếu role hoặc còn account dù JML đã đổi.

### 11.1. Đọc bốn tầng

1. **Source:** HRIS/sponsor phát event đúng người, source version, effective time và approval chưa?
2. **Policy:** RBAC/ABAC mapping, SoD, role catalog, attribute có sai không?
3. **Connector:** request được gửi chưa, correlation ID, status, retry count và API permission?
4. **Target:** account/role/group/direct grants/session thực tế ra sao? API response không thay cho readback.

### 11.2. Ma trận lỗi phổ biến

| Lỗi | Quyết định on-call |
|---|---|
| `400/422` | Payload/schema hoặc business rule sai, chuyển owner sửa mapping/source, không retry payload y nguyên vô hạn |
| `401/403` | Connector credential/scope thiếu, xử lý qua vault/approved change, không cấp quyền rộng tùy tiện |
| `404` | Resource không tồn tại hoặc ID sai; tra immutable mapping, readback trước create |
| `409` | Trùng identity/unique field; không merge account dựa riêng email |
| `412` | ETag/version không khớp nếu target hỗ trợ; đọc lại rồi tính diff |
| `429` | Rate limit; tôn trọng `Retry-After`, bounded backoff có jitter |
| `5xx/timeout` | Chưa chắc request thất bại; đánh dấu `UNKNOWN` và đối soát trước retry |
| `2xx nhưng vẫn lệch quyền` | Async job, mapping, cache, local role hoặc group kế thừa; kiểm tra effective access |

### 11.3. Điều kiện retry an toàn

- Dùng `event_id`, `subject_id` và `source_version` để bảo vệ khỏi duplicate/out-of-order.
- Một event Joiner/Mover cũ không được **enable lại Leaver** mới.
- Với create timeout, đọc actual trước khi POST thêm account có thể trùng.
- Retry có budget; quá hạn phải chuyển exception có owner và deadline, nhất là Leaver.
- Không chạy lại toàn workflow khiến target đã VERIFIED bị cấp quyền lần nữa.

## 12. SOP-OC05 — JML khẩn trong ca trực

### 12.1. Joiner: ưu tiên đúng quyền hơn “có account là xong”

Một người mới có thể bị chặn onboarding vì IdP, MFA enrollment hoặc SCIM. On-call:

1. Xác nhận nhân sự/sponsor, ngày hiệu lực và identity proofing.
2. Xác định app nào bắt buộc trong ca, app nào có thể bàn giao sang giờ hành chính.
3. Kiểm tra account IdP, SSO, SCIM và entitlement; không tự tạo local admin hoặc cấp role vượt approval.
4. Nếu cần đường onboarding đặc biệt, áp workflow exception được phê duyệt, scope và expiry.
5. Sau phục hồi, đối soát account duplicate và quyền đã cấp bằng tay; đóng khi target bắt buộc đã VERIFIED.

### 12.2. Mover: xử lý cả quyền mới và quyền cũ

Ví dụ nhân viên chuyển Support → Finance; app Finance cấp `finance-reader` nhưng Support không gỡ `support-editor`.

On-call phải kiểm tra:

- Sự kiện Mover mới nhất và ngày hiệu lực.
- Delta `KEEP` / `GRANT` / `REVOKE` / `REVIEW`.
- SoD và approval cho quyền tạm chuyển tiếp nếu có.
- Group, role trực tiếp, role kế thừa và session/token ở cả ứng dụng cũ/mới.
- Việc thu hồi đã VERIFIED, không chỉ nhóm IdP đổi tên.

**Không** báo Mover completed khi user đã vào được Finance nhưng vẫn truy cập dữ liệu Support ngoài nhiệm vụ.

### 12.3. Leaver: ưu tiên containment truy cập tồn dư

Khi HR hoặc nguồn nhà thầu đã xác nhận Leaver có hiệu lực, on-call cần ưu tiên:

1. Xác minh đúng subject ID bất biến, nguồn và thời điểm hiệu lực, tránh khóa nhầm người.
2. Chặn IdP/SSO/VPN/PAM và đường truy cập tập trung còn điều khiển được theo quyền hạn.
3. Thu hồi ở **SaaS, cloud, app-local account**, PAT/API token, SSH key, refresh token/session nếu được hỗ trợ và phù hợp.
4. Với connector lỗi, dùng thao tác đích **được ủy quyền** và ghi bằng chứng; không chờ SCIM hồi phục mới chặn local login.
5. Kiểm tra job cũ có thể re-enable account và cập nhật desired state/lifecycle guard.
6. Mọi target chưa kiểm chứng phải ở `EXCEPTION_OPEN`, có owner, rủi ro, deadline và containment thay thế.
7. Chỉ báo fully offboarded khi các lối truy cập bắt buộc đã xác minh theo policy.

### 12.4. Nhà thầu, guest, tài khoản dùng chung

Guest/B2B và contractor có thể **không có HR record như nhân viên**. On-call phải kiểm tra sponsor, contract end và quyền ứng dụng; không xóa nhầm guest hợp lệ vì không thấy trong HRIS. Với shared/legacy account, phối hợp owner/PAM, tránh mất khả năng truy trách nhiệm và credential không kiểm soát.

## 13. SOP-OC06 — Credential bị lộ, account takeover và quyền bất thường

**Trigger:** secret scanner, user báo phishing, sign-in bất thường, PAT/API key lộ, service account key thất thoát, role admin được cấp không rõ approval.

**Trọng tâm ca trực:** containment theo quyền được phép, bảo vệ chứng cứ, chuyển SOC khi nghi compromise. On-call không tự kết luận “an toàn” chỉ vì đã reset password.

### 13.1. Các bước

1. Tạo incident và xác định credential loại gì: password, refresh/access token, PAT, API key, SSH/private key, MFA recovery hay signing key.
2. Xác định issuer, owner, app/resource, scope, exposure window và mức tác động.
3. **Không dán giá trị secret/token vào ticket hoặc chat**; dùng ID, key fingerprint và audit references.
4. Theo chỉ đạo/đặc quyền được ủy quyền, disable/revoke ở **đúng issuer hoặc target**. Password reset ở IdP không nhất thiết vô hiệu hóa PAT/session độc lập.
5. Rà token/session đã phát, credential dẫn xuất, MFA methods, OAuth consent, quyền admin/grants mới và local persistence.
6. Nếu service secret cần rotate, phối hợp owner/workload, secret manager và kế hoạch triển khai để tránh gián đoạn không cần thiết.
7. Xác minh credential cũ không còn dùng được theo cơ chế target; quyền hiệu lực quay về desired state.
8. Giữ timeline và bằng chứng cho SOC, giao owner điều tra phạm vi, dữ liệu truy cập và recurrence.

### 13.2. Không biến security incident thành “reset password ticket”

Phishing có thể dẫn tới takeover khi attacker đã thêm MFA method, tạo token mới hoặc grant quyền cho tài khoản khác. Reset password chỉ xử lý một phần. Người trực cần phối hợp SOC để đánh giá **quyền phát sinh sau compromise** và token/session ngoài luồng SSO.

## 14. SOP-OC07 — Account lockout và lỗi xác thực cục bộ

Một user bị lockout không luôn là sự cố P0; nhiều lockout đồng thời có thể do stale credential, bot/attack hoặc directory lỗi.

1. Xác nhận người yêu cầu qua identity proofing, account và trạng thái JML.
2. Kiểm tra nguồn lockout: user nhập sai, thiết bị/email client lưu password cũ, automation, VPN, directory, IdP MFA/risk policy.
3. Kiểm tra pattern nhiều account/IP để phát hiện password spraying/compromise; mời SOC nếu cần.
4. **Không mở khóa** account Terminated/Suspended/security hold chỉ vì Help Desk đề nghị.
5. Với user hợp lệ, xử lý nguồn retry trước hoặc song song với unlock qua công cụ được phép, tránh khóa lại ngay.
6. Nếu nghi lộ credential, áp incident response và revoke session/token thay vì chỉ unlock.
7. Kiểm tra đăng nhập hợp lệ thành công và role đúng; ghi audit actor/thời điểm.

Đừng yêu cầu người dùng cung cấp password hiện tại, OTP hoặc recovery code. Không tắt lockout threshold toàn hệ thống để giảm ticket.

## 15. SOP-OC08 — Service account, workload và connector secrets

Tài khoản phi con người có owner kỹ thuật/nghiệp vụ, policy cloud, token/secret và chu kỳ deployment riêng; một lỗi có thể làm ngừng service mà không xuất hiện trong dashboard user sign-in.

| Tình huống | Kiểm tra | Hướng xử lý |
|---|---|---|
| API client 401 sau rotation | Vault version, credential deployment, scope | Cập nhật bản đúng qua secret manager; revoke key cũ |
| Workload federation token failure | Issuer/trust, JWKS, service principal | Platform owner khôi phục trust, thử trên phạm vi tối thiểu |
| Service account 403 | RBAC/ABAC/cloud role, resource scope | Sửa quyền tối thiểu theo approval, không cấp admin toàn project |
| Job im lặng sau Mover/Leaver owner | Technical/business owner và dependency | Bàn giao owner, rotate secret/thu hồi quyền cá nhân |
| Cloud principal không có owner | CMDB/workload catalog, logs | Phân loại suspect orphan, không xóa trước kiểm tra dependency |
| Key/token bị lộ | Issuer, scope, secret store, requests | SOC containment, rotate/revoke, rà credential dẫn xuất |

**Quy tắc:** không thay service account credential bằng token admin cá nhân của người trực. Không xóa account automation production chỉ vì người tạo đã nghỉ; cần chuyển ownership có kiểm soát và loại bỏ quyền cá nhân tồn dư.

## 16. SOP-OC09 — Emergency access và break-glass

On-call có thể cần đặc quyền để khôi phục IdP hoặc thu hồi quyền Leaver khi đường IAM thông thường bị lỗi. Cần phân biệt:

- **JIT/PAM elevation:** người đủ điều kiện nhận role hẹp, trong thời gian ngắn, có approval và audit.
- **Break-glass:** đường dự phòng được thiết kế/đăng ký trước, chỉ kích hoạt khi điều kiện khẩn phù hợp, với owner, credential protection, logging và hậu kiểm.
- **App-local emergency admin:** chỉ dùng khi ứng dụng có cơ chế được phê duyệt và biết cách revoke.

### 16.1. Nguyên tắc kích hoạt

1. Có incident thật, mục đích, target và người thao tác đã xác minh.
2. Đúng người còn **Active**, không bị Leaver/security hold; requester không tự phê duyệt đặc quyền khi policy cần độc lập.
3. Scope tối thiểu, TTL và owner rõ ràng; không mặc định Global Admin.
4. Credential lấy qua kênh an toàn, không chia sẻ trong ticket/chat.
5. Ghi session/audit, giám sát thay đổi nhạy cảm và báo SOC/PAM theo chính sách.
6. Khi hoàn tất, revoke **grant, session, token/credential và local bypass**, đối soát ở target.
7. Nếu IdP/SSO đang lỗi, dùng phương án đã kiểm thử; không vô hiệu xác minh chữ ký hoặc MFA toàn tenant.

### 16.2. Break-glass bị dùng không có incident

Một alert cho thấy tài khoản break-glass đăng nhập ngoài lịch kiểm thử phải được chuyển SOC/PAM và đối chiếu actor, session, approval, hành động. Không bỏ qua chỉ vì “đây là account khẩn”; mọi lần sử dụng phải có lý do và hậu kiểm.

## 17. SOP-OC10 — Phối hợp incident và thông báo trạng thái

### 17.1. Chu kỳ cập nhật

Người trực phải truyền đạt **fact → impact → action → risk → next update** bằng câu ngắn, nhất quán với incident commander. Cadence tùy severity và chính sách. Không tự tuyên bố “đã khắc phục” khi mới thực hiện một lệnh thay đổi chưa được readback.

Ví dụ thông báo nội bộ:

> Đã xác nhận các lần đăng nhập SSO mới của hai ứng dụng gặp lỗi timeout từ IdP. Người dùng có phiên đang hoạt động có thể chưa bị ảnh hưởng. IAM và SRE đang kiểm tra token endpoint và thay đổi cấu hình gần nhất. Chưa có bằng chứng xác nhận nguyên nhân gốc. Những yêu cầu Leaver khẩn vẫn được theo dõi theo đường thu hồi tại hệ thống đích.

### 17.2. Vai trò của IC và on-call

- **IC:** kiểm soát mức độ, ưu tiên, phối hợp các đội và thông báo stakeholder.
- **IAM Primary:** cung cấp chẩn đoán, hành động, risk và evidence; điều phối IAM/PAM app owner.
- **Secondary:** hỗ trợ triage và làm người kiểm tra chéo thay đổi nhạy cảm.
- **SOC:** quản lý phần điều tra security, containment và bằng chứng lạm dụng.
- **Application Owner/SRE:** xác minh business transaction/availability sau thay đổi.

Tránh việc nhiều người đồng thời chỉnh cùng một policy, account hoặc group mà không điều phối. Có thể áp cơ chế **incident change log và một người thực thi tại một target**; mọi thay đổi phải ghi actor/timestamp.

### 17.3. Khi nào cần escalated decision?

Escalate ngay nếu không xác định đúng identity, cần vượt policy, không thể revoke credential/Leaver, mất tính toàn vẹn audit, phát hiện signing key lộ, có nguy cơ mất dữ liệu hoặc phương án khẩn đang thất bại. Không xử lý bằng im lặng hoặc thử đổi quyền ngẫu nhiên.

## 18. Handoff kỹ thuật khi incident chưa đóng

### 18.1. Mẫu handoff một trang

~~~yaml
handoff_ref: IAM-SHIFT-EXAMPLE-902
timezone: Asia/Ho_Chi_Minh
shift_ending_at: "2026-11-23T22:00:00+07:00"
outgoing_primary: iam-primary-shift-a
incoming_primary: iam-primary-shift-b
incoming_ack_at: "2026-11-23T21:55:00+07:00"
open_incidents:
  - incident_id: IAM-INC-902
    severity: P1
    problem: SCIM_REVOKE_DELAY
    target_system: customer-saas
    affected_scope: terminated-contractor-account
    lifecycle_event_ref: leaver-event-402
    actual_target_state: DISABLE_PENDING
    containment: app-local-session-revoked
    evidence_refs:
      - scim-response-502
      - app-audit-211
    risk: LOCAL_API_KEY_PENDING_CONFIRMATION
    next_action: owner-verify-key-revocation
    owner: app-owner-oncall
    escalation: iam-secondary-and-soc
    next_check_at: "2026-11-23T22:15:00+07:00"
    exception_status: OPEN
pending_changes:
  - change-ref: connector-credential-rotation-103
    status: WAITING_FOR_VERIFICATION
known_gaps:
  - saas-token-inventory-not-complete
~~~

Đây là **dữ liệu minh họa**, không có tên người thật hoặc bí mật. Handoff nên theo mẫu thống nhất, ID có thể truy vết và owner tương ứng.

### 18.2. Điều không được đánh mất khi chuyển ca

- Một **Leaver còn lối vào** cần ưu tiên hơn ticket về thiếu quyền thông thường.
- Những target `UNKNOWN`/`EXCEPTION_OPEN` cần theo dõi riêng; không trộn vào trạng thái “connector đã retry”.
- Session/token/role tạm từ break-glass có thể còn hiệu lực dù Incident Commander tuyên bố dịch vụ phục hồi.
- Change mới triển khai nhưng chưa verify có thể gây regression qua ca tiếp theo.
- Hypothesis chưa xác nhận phải được đánh dấu rõ, tránh người nhận diễn giải như root cause.
- Người nhận cần xác nhận bằng kênh trực; nếu không có ACK, chuyển Secondary/IC.

## 19. Đọc lại actual state và đóng incident bằng bằng chứng

**Một incident IAM có thể thành công ở lớp API nhưng thất bại ở lớp quyền hiệu lực.** Ví dụ SCIM trả 204 khi disable user, nhưng SaaS còn local session/API key; hoặc IdP healthy nhưng SAML app vẫn dùng certificate cũ.

### 19.1. Ma trận kiểm chứng

| Sự kiện | Bằng chứng hành động | Bằng chứng kết quả |
|---|---|---|
| Joiner | IdP/SCIM create và approval | Account đúng người, đúng role ở ứng dụng bắt buộc |
| Mover | Grant mới và revoke role cũ | Quyền mới được phép, quyền cũ bị từ chối, SoD đúng |
| Leaver | IdP disable, app revoke, key/session actions | Không còn đường đăng nhập/truy cập không hợp lệ tại target |
| IdP outage | Service recovery, config change | Canary OIDC/SAML, MFA/Conditional Access, app session đúng |
| Credential leak | Revoke/rotate tại issuer | Credential cũ bị từ chối; key mới scope tối thiểu |
| PAM break-glass | Grant/session logs và revoke | Không còn emergency privilege/token, hậu kiểm hoàn tất |
| Service account error | Vault/role change và owner approval | Workload hoạt động trong đúng resource scope |

### 19.2. Phân biệt ba trạng thái

| Trạng thái | Ý nghĩa | Đóng được chưa? |
|---|---|---|
| `REQUESTED` | Đã gửi yêu cầu thay đổi | Chưa |
| `APPLIED` | Connector/API/PAM báo thay đổi đã được xử lý | Chưa chắc |
| `VERIFIED` | Target actual và quyền hiệu lực đạt desired state | Có thể đóng hạng mục |
| `EXCEPTION_OPEN` | Một phần trạng thái không xác minh hoặc còn rủi ro | Không được báo fully resolved |

Nếu còn ngoại lệ nhưng dịch vụ chính hoạt động, có thể đóng nhánh availability và giữ **security remediation** với người chịu trách nhiệm, hạn xử lý và giám sát. Không ghi “IAM safe” hoặc “fully offboarded” khi còn token/grant có thể được sử dụng.

## 20. Chỉ số SLI/SLO, chất lượng trực ca và cải tiến sau sự cố

### 20.1. Những chỉ số nên đo

| Metric | Ý nghĩa |
|---|---|
| **Page acknowledge latency** | Từ cảnh báo đến xác nhận có người chịu trách nhiệm |
| **Time to triage** | Từ ACK đến xác định sơ bộ scope, severity và tuyến xử lý |
| **Time to containment** | Từ phát hiện rủi ro đến khi chặn được đường truy cập nguy hiểm |
| **Time to verified recovery** | Từ incident đến khi luồng đăng nhập/quyền đích được kiểm chứng |
| **Leaver revocation latency** | Từ JML effective time tới lúc quyền và credential ở target đã verified revoked |
| **Provisioning backlog age** | Tuổi của event JML chưa hoàn tất và số target đang retry/unknown |
| **Escalation accuracy** | Tỷ lệ page đúng đội/owner, không vòng qua nhiều nhóm |
| **False-positive page rate** | Số alert không cần đánh thức ca trực, giảm pager fatigue |
| **Handoff completeness** | Tỷ lệ incident mở có owner, evidence, next action và ACK ca mới |
| **Emergency privilege residue** | Quyền/credential khẩn cấp còn hoạt động sau TTL hoặc incident |
| **On-call burnout signals** | Phân bố số page/giờ ngủ gián đoạn giữa các ca, theo quy định quyền riêng tư |
| **Post-incident action closure** | Tỷ lệ action items gốc đã có owner và xác minh hoàn thành |

**Không tối ưu số lượng ticket đóng thay cho an toàn.** Ticket đóng nhanh nhưng Leaver vẫn có PAT hoặc Mover vẫn admin là kết quả xấu. Nên báo cáo riêng availability recovery và risk remediation.

### 20.2. Từ sự cố đến bài học hệ thống

Sau các P0/P1 hoặc sự cố lặp lại, tổ chức nên thực hiện post-incident review **không đổ lỗi cá nhân**, tập trung vào timeline, root cause, detection gap, hành động hữu ích, thiếu hụt runbook, khả năng test và cải tiến kiến trúc.

Hạng mục cải tiến có thể gồm:

- Tăng chất lượng cảnh báo theo **service/target/JML risk**.
- Cải thiện identity mapping với immutable ID.
- Đối soát tự động SCIM/app-local grants và session/token.
- Thêm circuit breaker/backoff để tránh lockout storm.
- Giảm standing admin bằng PAM/JIT, kiểm thử break-glass theo lịch được duyệt.
- Chuẩn hóa dashboard và source-of-truth owner cho service identities.
- Chạy game-day về IdP outage, SCIM revoke failure và emergency access cleanup.

## 21. Mẫu checklist thực hành theo giai đoạn

### 21.1. Trước ca

- [ ] Đúng Primary/Secondary, lịch giờ và kênh liên lạc.
- [ ] Pager, dashboard và ticket hoạt động trong phạm vi quyền thường ngày.
- [ ] Runbook, danh bạ owner và phương án liên lạc dự phòng có thể tìm được.
- [ ] Đã xem incident còn mở, connector retry, Leaver pending và emergency grants chưa đóng.
- [ ] Có người nhận trách nhiệm rõ cho từng ngoại lệ.

### 21.2. Khi nhận alert

- [ ] Đã ACK và mở/gắn incident ID.
- [ ] Đã xác minh alert, scope, source, timeline và risk.
- [ ] Đã phân biệt IdP/SSO, provisioning, RBAC/ABAC, credential và JML.
- [ ] Đã kiểm tra có Leaver/credential/privileged abuse cần containment ngay.
- [ ] Đã gọi đúng IC/SOC/SRE/app owner theo severity.
- [ ] Đã giữ evidence bằng tham chiếu, không copy secret.
- [ ] Đã thực hiện runbook được phép và có log thao tác.

### 21.3. Trước khi đóng hoặc chuyển ca

- [ ] Trạng thái **actual/effective** ở target phù hợp desired state.
- [ ] Session/token/API key/PAM grant khẩn đã được xử lý khi liên quan.
- [ ] Leaver không còn lối truy cập không hợp lệ đã biết.
- [ ] Change có approval, actor, timestamp và evidence.
- [ ] Ngoại lệ còn mở có owner, deadline, next check và containment.
- [ ] Người nhận ca đã ACK handoff hoặc Secondary/IC tiếp quản.
- [ ] Post-incident action items có owner và hướng ngăn tái diễn.

## 22. Bài tập tình huống dành cho on-call

### Tình huống A — 02:00, nhiều ứng dụng không đăng nhập được

Portal và payroll cùng báo sign-in timeout, trong khi ticketing có một số phiên cũ vẫn hoạt động. Status page IdP chưa cập nhật.

**Hướng xử lý:** ACK, kiểm tra request ID và canary an toàn ở nhiều app, phân biệt IdP/token endpoint với mạng/MFA, gọi SRE/IC theo scope. Kiểm tra Leaver khẩn vẫn có đường revoke tại app, tránh công bố root cause khi chưa có bằng chứng. Sau khôi phục, canary OIDC/SAML và reconcile JML backlog.

### Tình huống B — 03:15, HR phát Leaver khẩn nhưng SCIM trả 503

Nhà thầu vẫn truy cập SaaS bằng PAT và local login dù IdP disabled.

**Hướng xử lý:** xác minh subject/Leaver authoritative event, gọi app owner/SOC, chặn local user/PAT/session qua đường được ủy quyền, giữ SCIM target exception, retry có giới hạn và verify tại app. Không chờ connector hồi phục mới chặn PAT; không báo fully offboarded khi chưa readback.

### Tình huống C — 22:20, account lockout đồng loạt

30 user bị khóa, dashboard cho thấy một job dùng password cũ sau rotation, đồng thời SOC ghi nhận sign-in failure khác thường từ bên ngoài.

**Hướng xử lý:** điều tra song song nguồn automation retry và tín hiệu attack, ngăn retry storm qua owner, điều phối SOC cho phần credential abuse. Không unlock hàng loạt trước khi giải quyết nguyên nhân, không tắt lockout threshold toàn tenant.

### Tình huống D — 00:30, service account không lấy được token

Connector production trả 401 sau đợt rotate secret. Responder đề xuất dùng token admin cá nhân để chạy job.

**Hướng xử lý:** xác minh secret version, scope, issuer, owner, workload deployment; sửa qua vault/change được duyệt, rollout và kiểm thử đúng môi trường. Không dùng admin token cá nhân hoặc cấp global admin để khắc phục.

### Tình huống E — Mover đã cập nhật quyền mới nhưng còn admin cũ

IdP đã cấp `finance-reader`; app Support vẫn giữ direct admin role và session của Mover.

**Hướng xử lý:** xác nhận Mover version/time, ưu tiên revoke admin role và session có quyền cũ, xem SoD, sửa mapping/workflow rồi verify quyền Support không còn và Finance vẫn đúng. Severity dựa trên dữ liệu/tác động, không coi là “sai nhỏ” vì user vẫn làm việc được.

### Tình huống F — Break-glass được kích hoạt mà không có incident

Một cảnh báo PAM ghi nhận tài khoản emergency admin được dùng ngoài giờ nhưng không có ticket/changelog.

**Hướng xử lý:** gọi SOC/PAM, xác minh actor, session, approval, hành động và liệu có drill hợp lệ. Nếu không xác minh được, containment theo policy, bảo vệ log, điều tra credential và hậu kiểm. Không xóa dấu vết hoặc bỏ qua vì account có tên “emergency”.

### Tình huống G — Sau ca, một grant khẩn vẫn còn

Primary hết ca, incident production đã phục hồi, PAM báo role JIT expired nhưng ứng dụng vẫn chấp nhận access token đặc quyền.

**Hướng xử lý:** giữ `EXCEPTION_OPEN`, chuyển ca có ACK và owner, revoke token/session hoặc deny tại đích theo khả năng, verify hành động admin bị từ chối. Không đóng access chỉ vì TTL trong portal hết.

### Tình huống H — Chỉ một user không truy cập app

IdP sign-in thành công, MFA hợp lệ nhưng app trả 403. User yêu cầu cấp admin ngay vì có buổi demo.

**Hướng xử lý:** kiểm tra account provisioning và RBAC/ABAC, role/mapping, policy/approval và session; giải quyết theo yêu cầu quyền hợp lệ, không cấp admin để tránh lỗi. Nếu không khẩn theo chính sách, bàn giao support/owner theo SLA bình thường.

### Tình huống I — Hai ca trực cùng sửa một tenant policy

Ca sắp hết giờ đã rollback một Conditional Access rule; ca tiếp nhận chưa thấy log, định sửa một rule khác gây tác động rộng.

**Hướng xử lý:** dừng thao tác trùng, thống nhất ownership và change log, kiểm tra actual policy/version, đánh giá root cause và phạm vi ảnh hưởng, lập kế hoạch với IC/Security. Không triển khai nhiều thay đổi IAM policy song song không điều phối.

## 23. Kết luận: một ca trực IAM an toàn và có thể kiểm toán

**On-call IAM** không chỉ là phản hồi nhanh khi người dùng không đăng nhập được; đó là năng lực bảo vệ **đúng danh tính, đúng quyền, đúng thời điểm** trong điều kiện áp lực cao. On-call phải hiểu mối liên hệ giữa HR/JML, IdP/SSO/MFA, SCIM provisioning, RBAC/ABAC, PAM và các đường credential/token độc lập; phải phân biệt sự cố khả dụng với sai lệch quyền hiệu lực.

Ca trực chỉ được coi là hoàn tất có trách nhiệm khi **mọi việc đang mở có owner**, những quyền có rủi ro được chặn hoặc quản lý ngoại lệ rõ ràng, thay đổi đã có **readback và verification**, và người nhận ca có đủ thông tin để tiếp tục. Thực hành nhất quán các nguyên tắc này giúp tổ chức giảm quyền tồn dư sau Mover/Leaver, tránh làm yếu chính sách khi cứu dịch vụ và duy trì năng lực kiểm toán trong toàn bộ vòng đời danh tính.
