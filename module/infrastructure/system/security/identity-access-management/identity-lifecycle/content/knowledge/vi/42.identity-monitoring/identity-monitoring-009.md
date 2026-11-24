# Identity detection trong IAM: phát hiện rủi ro xoay quanh danh tính và quyền truy cập

> **Chương:** Identity monitoring  
> **Bài:** Identity detection  
> **Module:** SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE  
> **Ngữ cảnh:** Quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)** từ xác minh, tạo tài khoản, cấp quyền đến rà soát và thu hồi khi thay đổi vai trò. Bài kết nối **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và việc giảm quyền truy cập tồn dư**.

## 1. Identity detection là gì?

Một tài khoản nhân viên đã Leaver được IdP đánh dấu disabled nhưng vẫn có khóa API dùng được ở một SaaS. Một service principal không còn owner lại được cấp role quản trị production. Hoặc một nhân viên đang giữ quyền thấp bỗng được thêm vào group đặc quyền mà không có access request hợp lệ.

Những ví dụ này có thể không làm phát sinh **đăng nhập thất bại**. Nếu chỉ quan sát màn hình sign-in của IdP, đội bảo mật có thể bỏ sót. Hệ thống cần phát hiện các **biến động, quyền và hành vi có rủi ro gắn với identity** trên nhiều hệ thống.

**Identity detection** trong phạm vi **Identity monitoring** là quá trình **thu thập tín hiệu, đối chiếu ngữ cảnh danh tính và quyền, phát hiện những trạng thái/hành vi không phù hợp với kiểm soát dự kiến, rồi tạo bằng chứng để xác minh và phản ứng**.

Khái niệm ở đây chủ yếu liên quan **identity threat detection và control detection**, không phải thao tác **identity proofing** (xác minh con người là ai lúc đăng ký). Nó có quan hệ với **Identity Threat Detection and Response (ITDR)** nhưng không mặc định đồng nghĩa một sản phẩm ITDR cụ thể.

### 1.1. Identity detection trả lời câu hỏi gì?

- Principal nào đang tạo sự kiện: người, guest, service account, workload hay API client?
- Principal đó có **căn cứ tồn tại, owner, trạng thái vòng đời và entitlement** hợp lệ không?
- Sự kiện là login, grant, role elevation, group update, credential issuance, token use hay resource access?
- Điều gì **bất thường** hoặc **trái control có hiệu lực**?
- Chứng cứ đến từ authority nào và có đáng tin không?
- Rủi ro có ảnh hưởng tới resource, tenant, privileged action hay dữ liệu nào?
- Cần triage, step-up, revoke, containment, reconciliation hay mở audit finding?
- Sau phản ứng, target đã **thực sự chặn đường quyền** hay mới nhận một lệnh?

### 1.2. Phân biệt “phát hiện” với “khẳng định bị xâm nhập”

Phát hiện một role tồn dư có thể đủ căn cứ để kết luận **control deficiency**, nhưng chưa đủ nói kẻ tấn công đã khai thác role. Ngược lại, một login lạ có thể chỉ do VPN. Hệ thống cần diễn giải rõ:

| Mức kết luận | Ví dụ | Việc tiếp theo |
|---|---|---|
| **Observation** | Một event group.add không có request link | Xác minh correlation/context |
| **Anomaly** | Một principal đăng nhập bằng thiết bị lạ | Enrich, triage theo risk |
| **Policy violation** | User Leaver được phép login sau cutoff | Containment và xác minh target |
| **Suspected compromise** | MFA fatigue + session mới + privileged actions | Điều tra ưu tiên, cân nhắc chặn theo policy |
| **Confirmed compromise** | Có bằng chứng chiếm quyền và hành vi trái phép | Incident response có phạm vi rõ |
| **Control finding** | Workflow SCIM không bao phủ direct grants | CAPA, owner, retest |

**Identity detection là bước tạo tín hiệu và chứng cứ; việc gắn nhãn compromise cần đánh giá riêng, có thể do SOC/incident team xác nhận.**

### 1.3. Mục tiêu học tập

Sau bài này, người đọc có thể:

1. Xác định đối tượng và phạm vi detection cho human và non-human identities.
2. Xây nguồn telemetry từ HRIS/IdP/SSO/SCIM/PAM/cloud/API, đủ để nối identity–credential–session–grant–resource.
3. Phân biệt rule dựa chính sách, anomaly, graph analytics, sequence detection và posture finding.
4. Phát hiện sai lệch ở Joiner–Mover–Leaver, privileged access, credential/trust và residual access.
5. Thiết kế chuẩn dữ liệu, correlation, versioning, điều kiện loại trừ và evidence confidence.
6. Viết detection logic có thể thử nghiệm, giải thích và quản trị theo version.
7. Xử lý false positives, telemetry gaps, containment và target verification.
8. Đo độ bao phủ, hiệu lực detection và chất lượng phản ứng mà không đánh đồng alert count với an toàn.

## 2. Ranh giới với các hoạt động IAM liên quan

Identity detection nằm giữa nhiều chức năng IAM. Các hệ thống đó tạo ra **expected state** và **observed state** để so sánh.

| Hoạt động | Nhiệm vụ chính | Identity detection bổ sung gì? |
|---|---|---|
| **Identity proofing** | Kiểm tra danh tính lúc enrollment | Theo dõi enrollment bất thường, identity duplication |
| **Authentication** | Xác thực principal | Phát hiện login/MFA/session risk |
| **Authorization** | Quyết định action/resource được phép | Phát hiện privilege escalation, stale policy, cross-tenant access |
| **Provisioning** | Tạo account và cấp quyền | Phát hiện cấp sai, quá sớm, thiếu approval |
| **Deprovisioning** | Thu hồi account/grants/session | Phát hiện quyền còn usable sau cutoff |
| **Identity governance / IGA** | Owner, approvals, access requests/reviews | Phát hiện orphan, SoD conflict, invalid reviewer |
| **Identity Security Posture** | Đánh giá cấu hình, inventory, đường quyền | Phát hiện exposure/standing privilege, không nhất thiết có attack |
| **Identity logging** | Lưu hành động, trạng thái và evidence | Correlate các logs thành kết luận/risk signal |
| **SIEM / UEBA** | Phân tích đa nguồn và hành vi | Bổ sung identity graph, JML, effective entitlement |
| **ITDR** | Phát hiện và hỗ trợ phản ứng với identity threats | Dùng identity detections làm đầu vào triage/response |
| **Incident response** | Khoanh vùng, loại trừ và phục hồi sự cố | Xác minh dấu hiệu rồi thực hiện hành động có kiểm soát |

### 2.1. Detection không thay authorization

Detector phát hiện một API call trái policy rồi báo alert **không bảo đảm API đã chặn call**. Resource server/policy enforcement point vẫn phải thực thi authorization. Monitoring là lớp quan sát và phát hiện, không phải lý do cho phép fail-open.

### 2.2. Detection không thay recertification

Access review xác nhận business need qua owner định kỳ; detection có thể phát hiện grant mới hoặc quyền tồn dư giữa các kỳ. Phát hiện một quyền “lâu không sử dụng” không tự xác định quyền đó không còn hợp lệ; cần đánh giá owner, dependencies và policy.

### 2.3. Posture và active-threat detection

Một service principal có standing admin role không được review là **posture risk** ngay cả khi không có token issuance đáng ngờ. Ngược lại, token được dùng từ runtime ngoài trust boundary có thể là **active threat signal**. Có thể cùng severity cao, nhưng bằng chứng và response khác nhau.

## 3. Các đối tượng cần đặt vào bản đồ phát hiện

Một identity thường liên kết với nhiều đối tượng kỹ thuật. Chỉ lưu email hoặc một User ID trong IdP không đủ.

| Đối tượng | Ví dụ | Liên quan detection |
|---|---|---|
| **Business identity** | employee-1042, partner-64 | Trạng thái JML, owner, sponsor |
| **Target account** | SaaS user, database login | Account còn active không? |
| **Principal / subject** | Cloud service principal, federated subject | Ai thực sự được xác thực? |
| **Credential** | Password verifier, API key, certificate, passkey reference | Có bị tạo, lộ, rotate hay dùng sai? |
| **Session** | IdP session, RP session, PAM privileged session | Có còn hiệu lực sau revoke? |
| **OAuth token/grant** | Access/refresh token, client grant, consent | Issuer/audience/scope/lifetime/trust |
| **Role/entitlement** | finance.approve, cloud.roles.admin | Quyền được cấp và còn cần? |
| **Group/attribute** | IdP group, department, tenant, classification | RBAC/ABAC mapping và freshness |
| **Resource** | Finance report, production database | Action nào nguy hiểm? |
| **Owner/sponsor** | Team kỹ thuật, quản lý dự án, partner sponsor | Ai phê duyệt/thu hồi? |
| **Workload** | CI job, Kubernetes ServiceAccount, integration connector | Runtime nào được dùng credential? |
| **Approval/exception** | Access request, JIT activation, time-bound exception | Hành vi có căn cứ không? |

### 3.1. Phân biệt identity và account

Một nhân viên nghỉ việc là **business identity**. Người đó có thể có năm target accounts và hai RP sessions; disable IdP account không chứng minh mọi đường truy cập đã bị chặn.

### 3.2. Non-human principal không luôn có HRIS record

Một service principal có thể có owner trong service catalog, deployment inventory và hợp đồng vendor. Detection cần xác định nguồn vòng đời phù hợp; không coi thiếu HRIS employeeId là lỗi cho mọi workload.

### 3.3. Quyền có nhiều đường cấp

Một account có thể được phép report.read qua group A, direct ACL B hoặc role được kế thừa từ organization. Detection cần xem **effective access**. Gỡ A thành công mà B vẫn hợp lệ không nhất thiết là failure nếu mục tiêu chỉ revoke A; nhưng là failure nếu policy yêu cầu không còn mọi đường đọc resource đó.

### 3.4. Ba thời gian cần tách

- **Business effectiveAt:** khi Joiner/Mover/Leaver có hiệu lực.
- **Observation time:** khi telemetry/target cho biết trạng thái.
- **Enforcement time:** khi target bắt đầu thực sự chặn/cấp quyền, đôi khi chỉ đo được một khoảng.

Không gán time của API response hoặc SIEM ingestion làm thời điểm thực thi quyền nếu không có evidence.

## 4. Identity graph: mô hình liên kết danh tính–quyền–tài nguyên

Một **identity graph** mô tả các nút và quan hệ giữa principals, accounts, roles, credentials, sessions, resources và approvals.

~~~mermaid
flowchart LR
    HR[HRIS Identity] -->|mapsTo| IDP[IdP Account]
    IDP -->|federatesAs| SAAS[SaaS Account]
    IDP -->|memberOf| GR[Finance Group]
    GR -->|mapsTo| ROLE[Report Export Role]
    ROLE -->|permits| REP[Sensitive Report]
    SAAS -->|directGrant| ROLE
    SAAS -->|hasSession| SESS[RP Session]
    HR -->|status| JML[JML State]
    OWNER[Business Owner] -->|approves| ROLE
    NHI[Workload Principal] -->|usesTrust| STS[Token Issuer]
    STS -->|issues| TOKEN[Access Token]
    TOKEN -->|accesses| REP
~~~

Đồ thị này là mô hình khái niệm. Các quan hệ như mapsTo, memberOf, hasGrant và issues phải được **đối soát từ nguồn tin cậy**, không suy đoán từ tên giống nhau.

### 4.1. Identity resolution

Một tài khoản bên ngoài có subject **sub** thuộc issuer A không tự đồng nhất với một tài khoản khác cùng email ở issuer B. Nên dùng namespace như:

~~~text
humanIdentityKey = HRIS_SOURCE + immutableEmployeeId
federatedKey     = issuer + subject
targetAccountKey = targetSystem + tenant + stableTargetAccountId
workloadKey      = trustIssuer + subject + audience + environment
~~~

Tùy provider, key có thể cần thêm organization, cloud account, workload namespace hoặc token-binding profile. Email/display name chỉ phục vụ tìm kiếm phụ trợ.

### 4.2. Detection dựa trên graph

Ví dụ:

- User Leaver có cạnh hasActiveSession tới application quan trọng.
- Service principal không còn cạnh hasOwner nhưng có cạnh hasAdminRole.
- Một actor có canApprove và canGrant cho cùng request trái SoD.
- Một external guest có cạnh canAccess tới tài nguyên ngoài tenant dự kiến.
- Một role xuất hiện đường cấp gián tiếp qua group nesting mà deprovision plan bỏ sót.
- Một workload identity được trusted bởi hai environments trái policy.

### 4.3. Graph là ảnh chụp theo thời gian, không phải sự thật vĩnh viễn

Quan hệ thay đổi khi nhân viên Mover, group được chỉnh, consent hết hạn hoặc policy role đổi. Đồ thị cần timestamps, sourceVersion và **as-of query** để tránh dùng quyền hôm nay giải thích sai một sign-in tháng trước.

### 4.4. Rủi ro over-linking

Gộp hai principals vì trùng username có thể tạo false alert hoặc làm lộ dữ liệu giữa tenants. Identity resolution phải có confidence và mapping evidence; khi không chắc, dùng UNKNOWN và yêu cầu đối chiếu, không tự merge.

## 5. Chuẩn hóa telemetry: không chỉ log đăng nhập

Một chương trình Identity detection cần sự kiện từ **identity control plane**, **authentication plane** và **data plane**.

| Nguồn | Event tiêu biểu | Thông tin cung cấp |
|---|---|---|
| **HRIS/contract** | Joiner, Mover, Leaver, sponsor change | Desired identity lifecycle |
| **IdP/directory** | User status, group change, credential reset | Authentication identity và account state |
| **SSO/OIDC/SAML** | Auth request/result, token issuance, RP login | Trust và session boundary |
| **MFA** | Enrollment, reset, challenge/deny/approve | Assurance và recovery risk |
| **SCIM** | User PATCH, Group membership, error, readback | Provision/deprovision state |
| **IGA/access request** | Request, approval, expiration, recertification | Business authorization context |
| **PAM/PIM** | Admin activation, privileged session | Elevated access state |
| **Cloud IAM** | Role binding, trust update, principal creation | Privilege/control-plane changes |
| **Application/API** | Resource PERMIT/DENY, local role change | Data-plane effective access |
| **Token issuer / vault** | Token/key/cert creation, rotation, revoke | Credential/trust lifecycle |
| **CI/CD/runtime** | Job identity, deployment, namespace, region | Workload expected behavior |
| **Inventory/CMDB** | System criticality, owner, target capability | Risk context, responsibility |
| **SIEM/case system** | Alert disposition, incident, finding | Feedback, audit history |

### 5.1. Một normalized event cần các trường nào?

~~~text
eventId, eventType, schemaVersion
eventTime, ingestedAt, observedAt
producerId, sourceSystem, sourceTrustLevel
tenantId, principalType, principalId, issuer
targetSystemId, targetAccountId, resourceId
operation, outcome, normalizedErrorCode
authMethod, tokenGrantType, sessionRef
roleId, entitlementId, grantSource, policyVersion
lifecycleStatus, lifecycleVersion, effectiveAt
requestId, correlationId, causationId
approvalRef, actorRef, riskTier, evidenceRef
~~~

Không có mọi trường trên từng event; áp dụng schema theo loại sự kiện, đánh dấu trường vắng là **UNKNOWN hoặc NOT_APPLICABLE** đúng nghĩa. Không gán thiếu MFA record thành MFA_BYPASSED khi chưa đủ bằng chứng.

### 5.2. Data provenance và trust

Sự kiện producer phải được xác thực. Client có thể khai địa chỉ IP/username không đúng; server phải dùng nguồn trusted proxy và account mapping. Detection rule không nên để một HTTP header tự khai principalId hoặc department quyết định role entitlement.

### 5.3. Sensitive data và secret redaction

Không đưa password, OTP, API secret, raw access/refresh token, private key, raw session cookie hoặc đầy đủ PII vào event stream. Nếu cần đối chiếu token/session, lưu opaque reference do server tạo và giới hạn quyền truy cập.

### 5.4. Event time và ingestion time

Một IAM event phát lúc 09:00 có thể tới SIEM lúc 09:03. Correlation nên dùng eventTime đã kiểm chứng, xét clock skew và message delay. Không bỏ qua alert vì event đến trễ, cũng không tính ingest timestamp thành business effectiveAt.

### 5.5. Coverage và telemetry gaps

Một target không phát local role events là **blind spot**, không phải bằng chứng “không có direct grants”. Thiết kế health checks, inventory reconciliation, ingest lag monitoring, dead-letter handling và evidence limitations.

## 6. Kiến trúc Identity detection end-to-end

~~~mermaid
flowchart TD
    SOURCES[HRIS / IdP / SCIM / PAM / Cloud / SaaS / Vault] --> INGEST[Trusted Event Ingestion]
    INGEST --> NORMAL[Validate / Normalize / Deduplicate]
    NORMAL --> HIST[Audit Event Store]
    NORMAL --> JOIN[Identity Resolution + Time Context]
    CATALOG[Identity Graph / Owner / Grants / JML] --> JOIN
    POLICY[Approved Policies + Exceptions] --> DETECT[Rules / Correlation / Anomaly Models]
    JOIN --> DETECT
    DETECT --> RISK[Signal Confidence + Business Impact]
    RISK --> CASE[Case / SIEM / ITDR / Alert]
    CASE --> TRIAGE[Analyst or Approved Automation]
    TRIAGE --> ACT[Contain / Revoke / Step-up / Fix Control]
    ACT --> VERIFY[Target Readback / Resource Deny]
    VERIFY --> AUDIT[Evidence + Outcome + Feedback]
    HIST --> AUDIT
    AUDIT --> TUNE[Detection QA / Tuning / Regression]
    TUNE --> DETECT
~~~

### 6.1. Thu thập và chuẩn hóa

Giữ raw source reference và normalized version, kiểm schema, xác thực producer và loại duplication theo eventId hoặc nguồn định danh phù hợp. Không nhầm retry attempt với event độc lập dẫn tới đếm sai.

### 6.2. Enrichment theo trạng thái hiệu lực

Khi đánh giá một login tại thời điểm T, nếu nhân viên chuyển team ngày T+1, không dùng department tại T+1 để phán xét quyền ở T. Identity graph, JML status và role assignments phải hỗ trợ **temporal join/as-of**.

### 6.3. Detection và risk prioritization

Rule dựa policy có thể xác định một violation ngay cả khi hành vi chưa từng được quan sát. Anomaly model giúp tìm mẫu mới chưa định nghĩa, nhưng cần explainability, versioning và confidence. Risk assessment xem phạm vi tài sản, entitlement và exploitability.

### 6.4. Triage và response

Detection sinh alert không đồng nghĩa đã chặn. SOC/ITDR hoặc automation được duyệt cần xác minh, quyết định phản ứng và lưu bằng chứng. Với quyền đặc biệt, có thể ưu tiên containment trước khi root cause analysis hoàn tất.

### 6.5. Target verification

Một SCIM PATCH hoặc IdP disable ACK không chứng minh RP session, API key hoặc direct grant bị chặn. Cần target readback, token/session state hoặc resource-deny evidence phù hợp với access path trong scope.

## 7. Danh mục use case Identity detection

Nên phân use case theo **rủi ro và kiểm soát** thay vì chỉ theo vendor logs.

| Use case | Detection signal | Điều phải kiểm tra |
|---|---|---|
| **Unauthorized Joiner access** | Account có quyền trước effectiveAt | Preboarding policy, account enabled vs created |
| **Stale Mover grant** | Role cũ active sau role change | Effective grants, approved overlap |
| **Leaver residual access** | Successful auth/API PERMIT sau cutoff | SourceVersion, target sessions/tokens |
| **Orphan human account** | Target account không map active identity | Service/shared account ngoại lệ? |
| **Orphan service principal** | Có role/credential nhưng không owner | Service inventory, dependency |
| **Privileged grant without approval** | Admin role added thiếu access request | Emergency/JIT approval |
| **SoD conflict** | User có approve và execute quyền xung đột | Policy version, scope |
| **MFA factor changed** | Enrollment/recovery/reset bất thường | Verified owner, approval |
| **Dormant account activated** | Principal lâu không dùng lại auth | Rehire, migration, compromise |
| **Password spray / MFA fatigue** | Auth failure bursts, prompts | Client/proxy errors, user context |
| **New OAuth consent** | App được cấp scopes nhạy cảm | Authorized app/client và user intent |
| **Token trust anomaly** | Issuer/subject/audience hoặc runtime lạ | STS/trust binding |
| **Over-privileged workload** | NHI có standing admin vượt purpose | Deployment need, permitted resource |
| **Credential after retirement** | Old key/token tiếp tục được dùng | Rotation window, target observed |
| **Cross-tenant permission** | Resource PERMIT ở tenant khác policy | Trust/role isolation |
| **Review remediation gap** | Decision REVOKE nhưng target grant active | Readback và ticket status |
| **Identity log gap** | HRIS event không có IAM workflow | Source-to-sink reconciliation |
| **Suspicious delegation** | New role assumption/impersonation | Authorized actor, SoD, audit |
| **Secondary grant creation** | User tạo API key/link/role trước Leaver | Lifecycle scope, token/grant inventory |
| **Mass privilege/group change** | Nhiều admins/users bị đổi cùng lúc | Approved campaign, connector compromise |

### 7.1. Chọn use case theo criticality

Một tổ chức có thể ưu tiên Leaver critical access, privileged grants và service credentials trước các anomaly nhẹ. Không chọn hàng chục rules chỉ để có nhiều alerts nếu chưa có owner, nguồn bằng chứng và response.

### 7.2. Detection phải nêu expected vs observed

Mỗi use case cần định nghĩa:

~~~text
Expected:
  Theo policy/JML/approval, điều gì phải đúng?

Observed:
  Từ target/log có bằng chứng trạng thái nào?

Gap:
  Điều kiện nào trái policy hoặc có risk signal?

Confidence:
  Source/timestamp/mapping có đáng tin?

Action:
  Ai xác minh, containment nào an toàn, khi nào closure?
~~~

### 7.3. Scope đóng vai trò quyết định

Nếu Mover rời Finance nhưng vẫn được baseline.view hợp lệ, detector không nên báo mọi Finance read là violation. Cần biết action, resource, direct vs inherited grants và exception.

## 8. Các loại detection và ưu/nhược điểm

### 8.1. Policy-based / deterministic detection

Quy tắc rõ như **“Leaver với status=TERMINATED nhưng target account được xác minh vẫn ACTIVE sau cutoff được duyệt”**. Dễ giải thích và audit; chất lượng phụ thuộc dữ liệu authoritative, cutoff, capability và role mapping.

### 8.2. Threshold và sequence detection

Ví dụ một account có nhiều failed MFA prompts trong cửa sổ, rồi privileged login và reset credential. Cần định nghĩa window, event order, correlation key và dedup. Bursts không tự chứng minh compromise.

### 8.3. Statistical / behavioral anomaly

So sánh principal với lịch sử/peer-group theo thiết bị, thời gian, ứng dụng, action. Có false positives với Joiner cold start, approved travel, on-call và workload deployments. Model cần drift detection và feedback.

### 8.4. Graph/path analytics

Tìm đường quyền mới dẫn tới production-admin, orphan account có grant tới dữ liệu nhạy cảm hoặc SoD path. Độ chính xác phụ thuộc inventory và khả năng phân giải nested groups, direct ACL và cross-system grants.

### 8.5. Reconciliation-based detection

Lập desired-state từ HRIS/IGA và observed-state từ target. So sánh theo mỗi identity/account/grant. Hữu ích phát hiện missed deprovision, silent drift hoặc sync failure. Không dùng một lệnh connector success thay readback.

### 8.6. Rule signatures vs unseen attacks

Rules mô tả known patterns tốt; anomaly giúp thấy khác thường chưa được viết thành rule. Nhưng cả hai có thể bỏ sót actor dùng credential hợp lệ, session hijack hoặc hoạt động ít nổi bật. Cần đa nguồn và defense-in-depth.

### 8.7. Hard policy checks không được bị score làm mất

Nếu user Leaver có successful privileged access sau cutoff, một điểm “thiết bị quen thuộc” không được hạ sự kiện thành safe nếu policy cấm. Policy violations được xác minh cần lối xử lý ưu tiên độc lập với anomaly score.

## 9. Phát hiện sai lệch Joiner–Mover–Leaver

**JML** cung cấp expected state mạnh hơn “một hành vi trông lạ”. Detection nên lấy sự kiện và cutoff từ nguồn nghiệp vụ được phê duyệt, đối chiếu trạng thái account/grant tại target và hành vi truy cập thực tế.

### 9.1. Joiner: account có trước không đồng nghĩa quyền đã được mở

Một nhân viên có thể được tạo account trước ngày bắt đầu để hoàn tất giấy tờ hoặc đăng ký thiết bị. Điều cần giám sát là **quyền production hoặc quyền truy cập dữ liệu có hiệu lực trước policy cutoff**.

~~~text
HRIS startAt:            2026-12-01T02:00:00Z
Identity accountCreated: 2026-11-27T09:00:00Z
IdP accountEnabled:      2026-12-01T02:00:00Z
SaaS roleGranted:        2026-11-29T10:00:00Z
SaaS resourceAccess:     PERMIT tại 2026-11-29T10:05:00Z

Nếu policy chỉ cho phép dùng SaaS từ startAt:
    Bất thường đáng điều tra = quyền và access trước cutoff
    Không phải bản thân accountCreated sớm
~~~

Cần xác minh timezone, grant path, identity mapping và exception preboarding. Nếu policy cho phép quyền hạn chế cho onboarding trước ngày bắt đầu, detector phải phân biệt resource được phép và tài nguyên production.

### 9.2. Mover: cấp quyền mới nhưng không gỡ quyền cũ

Một workflow có thể hoàn tất quyền mới ở Operations mà quên quyền Finance. Detection so sánh:

- **Before:** quyền/group/role cũ và resource scope.
- **Desired after Mover:** quyền cần giữ, thêm và thu hồi.
- **Observed after Mover:** effective grants tại IdP và target.
- **Cutoff:** thời điểm quyền cũ không còn căn cứ.
- **Overlaps:** có phê duyệt giữ quyền tạm thời không?

Một rule đơn giản “mọi Finance access sau Mover đều nguy hiểm” có thể tạo false positive với baseline viewer hợp lệ. Nên phát hiện **grant cụ thể chưa gỡ** hoặc **resource action trái effective policy**.

### 9.3. Leaver: phân biệt login attempt và access thực tế

| Tín hiệu sau effectiveAt | Có thể kết luận | Chưa thể kết luận |
|---|---|---|
| IdP denied login | IdP từ chối request cụ thể | Mọi RP sessions đã chấm dứt |
| IdP successful login | Có dấu hiệu vi phạm nếu identity/cutoff đúng | Người login chắc chắn là attacker |
| SaaS account active | Account chưa đạt expected state | Có exfiltration |
| SCIM revoke HTTP 204 | Connector nhận phản hồi tích cực | Direct grants/tokens đều hết |
| RP session còn active | Có đường session đáng rà soát | Mọi endpoint đều PERMIT |
| API PERMIT với token cũ | Tại endpoint đó vẫn có access | Toàn bộ ứng dụng còn mở |
| Role absent qua readback | Grant cụ thể đã vắng mặt | Không còn mọi grant khác |

### 9.4. Phát hiện quyền tồn dư phải theo desired state và observed state

~~~mermaid
sequenceDiagram
    participant HR as HRIS
    participant IAM as JML Orchestrator
    participant IDP as IdP
    participant SaaS as Target SaaS
    participant DET as Identity Detection
    HR->>IAM: Leaver effectiveAt + sourceVersion
    IAM->>IDP: Disable principal
    IAM->>SaaS: Revoke account/grants
    IDP-->>DET: Authentication/disable evidence
    SaaS-->>DET: Target account and role readback
    IAM-->>DET: Desired state and operation results
    DET->>DET: Compare per access path, cutoff and version
    DET-->>IAM: PARTIAL / residual grant alert nếu còn quyền
~~~

**Không biến việc gửi command thành bằng chứng effective revocation.** Để tuyên bố verified, cần target readback hoặc bằng chứng enforcement theo access path và policy.

### 9.5. Out-of-order Mover sau Leaver

Một event Mover version 108 có thể tới trễ sau Leaver version 109. Nếu sync job cũ lại thêm group, detection phải phát hiện **grant recreated after revoke** và trigger reconciliation. Dùng sourceVersion/lifecycleVersion cùng effectiveAt; không tin thứ tự message bus.

### 9.6. Guest, contractor và partner lifecycle

Contractor/guest có thể có sponsor/contract effectiveAt thay HRIS employee termination. Detection cần map authority, sponsor, entitlement expiry, guest invites và local sessions. **Thiếu employeeId HRIS không tự có nghĩa guest identity bất hợp lệ.**

### 9.7. Cross-system closure

Một Leaver workflow có 12 targets và 11 verified, 1 target còn production-admin phải được xem là PARTIAL. Detection nên alert critical target, owner, overdue duration và containment; không chỉ biểu thị completion 91,7% để che rủi ro.

## 10. Authorization detection: RBAC, ABAC, SoD và privilege drift

Authentication trả lời “ai đã xác thực”; authorization trả lời “principal được làm gì trên resource nào”. Nhiều identity risks nằm ở phần thứ hai.

### 10.1. Các tín hiệu về role và entitlement

- Role admin được thêm không có approvalRef hợp lệ.
- Standing privilege tồn tại ngoài JIT/PAM activation window.
- Role definition bất ngờ thêm permission nhạy cảm.
- Group nesting làm nhiều principals kế thừa quyền mới.
- Quyền direct ACL tồn tại dù IdP group bị gỡ.
- ABAC policy dùng department/tenant/classification không còn đúng.
- Principal có hai vai trò xung đột theo SoD.
- Guest được phép resource ngoài tenant/sponsor scope.
- Role hoặc share link được tạo ngay trước Leaver.

### 10.2. Graph/path analysis là cần thiết khi quyền được kế thừa

~~~text
employee-1042
    memberOf: finance-analysts
    memberOf: emergency-admins (tạm thời)
finance-analysts -> report.view
emergency-admins -> finance.production.delete

Nếu emergency-admins quá hạn:
  Gỡ group membership; kiểm tra quyền delete đã mất
  Không giả định chỉ một grant source cấp delete
~~~

Rule cần xem effective entitlement graph và policy, không chỉ một sự kiện group.add.

### 10.3. Phân biệt thay role hợp lệ với privilege escalation sai

Một JIT admin activation trong cửa sổ được duyệt có thể bình thường nhưng vẫn cần audit. Không tự coi privileged grant bất kỳ là compromise. Xác minh:

1. Request/approval authority và đúng resource.
2. Người yêu cầu có thể tự phê duyệt không?
3. Role/grant có thời hạn và scope?
4. Subject có active/JML status hợp lệ?
5. Thao tác có xuất phát từ trusted execution context?
6. Grant đã thực sự hết ở target sau expiry?

### 10.4. SoD có phạm vi và ngữ nghĩa

Một người vừa tạo lệnh thanh toán vừa tự phê duyệt có thể vi phạm chính sách Segregation of Duties. Nhưng không kết luận dựa vào hai role names nếu policy cho phép dual-hat ở môi trường test hoặc có exceptional approval. Phải kiểm tra resource, environment, transaction and effective policy version.

### 10.5. ABAC và nguồn thuộc tính

Một claim department=Finance có thể đến từ IdP còn stale sau Mover. Nếu RP cache role cũ và cho export, detection nên báo **authorization freshness gap**. Không tin department do browser tự khai, sử dụng trusted source và effective timestamps.

### 10.6. Phát hiện quyền được cấp từ con đường khác

Khi role A bị revoke mà quyền tương đương còn qua group B, system cần so expected result:

- Nếu chỉ yêu cầu xóa **grant A**, có thể VERIFIED cho grant A.
- Nếu yêu cầu xóa **mọi quyền export**, phải xem B là residual path.
- Nếu B là baseline viewer không có export, không được thu hồi thừa chỉ để giảm cảnh báo.

## 11. Authentication, SSO và session-centered detection

Identity detection dùng tín hiệu login anomaly nhưng phải vượt ra ngoài login.

### 11.1. Những tín hiệu authentication thường hữu ích

- Password spray hoặc credential stuffing trên nhiều principals.
- Một device/browser mới kèm MFA denial burst.
- Đăng nhập vào admin app khác baseline.
- Legacy protocol được dùng để tránh controls mong đợi.
- MFA factor được enroll/reset ngay trước privileged action.
- Guest sign-in từ issuer/tenant không được ủy quyền.
- Dormant account login sau thời gian không sử dụng.
- Successful login sau account disable/Leaver cutoff.

Không coi một IP lạ là bằng chứng compromise; VPN, SASE egress và mobile carrier có thể làm sai geo location.

### 11.2. IdP session và RP session là hai lớp

Một người đăng nhập tại IdP rồi ứng dụng ERP tạo local session. IdP disabled user không mặc định chấm dứt local ERP session; SSO logout cũng phụ thuộc khả năng front/back-channel và RP implementation.

Detection cần phân biệt **authentication events**, **RP session creation/use**, **token issuance** và **resource authorization**.

### 11.3. OAuth và OIDC có nhiều loại token

| Đối tượng | Chức năng | Detection concern |
|---|---|---|
| **ID token** | Xác nhận authentication tới OIDC client | Issuer/sub/audience/nonce profile |
| **Access token** | Truy cập resource theo audience/scope/policy | Use sau revoke, sai resource |
| **Refresh token** | Xin access token mới theo authorization | Reuse/issuance sau disabled nếu policy yêu cầu |
| **Client credential** | Client/workload xác thực tới AS | Secret misuse, trust wrong runtime |
| **RP cookie/session** | Ứng dụng giữ phiên nội bộ | Long-lived stale session/role |
| **OAuth consent/grant** | Ủy quyền cho client trong phạm vi | New sensitive grant, approval, retention |

Một token refresh từ backend không nhất thiết là **interactive login mới**. Không dùng human impossible-travel detector trên mọi OAuth token issuance.

### 11.4. Step-up MFA không tự tạo authorization

MFA nâng mức đảm bảo danh tính, không tự cấp finance.approve hoặc cloud-admin. Sau step-up, resource server vẫn kiểm tra role/ABAC/resource policy. Detection có thể ghi thiếu step-up cho action nhạy cảm nếu policy yêu cầu, nhưng cần correlation giữa action và đúng authentication session.

### 11.5. Session fixation và token replay

Một custom RP callback giữ anonymous session ID sau login có thể bị session fixation; detection thường cần session lifecycle tests hoặc instrumentation, không chỉ IP log. Token replay sử dụng bearer token bị biết/lấy lại là nhóm tín hiệu khác; tránh gộp mọi token anomaly thành login anomaly.

### 11.6. Account recovery và MFA reset

Attackers có thể nhắm đường recovery thay vì mật khẩu chính. Detectors nên giám sát factor removal/replacement, recovery approvals, credential issuance, new device, session reauthentication và privileged action theo cùng principal/time context.

### 11.7. Chống suy diễn từ log trống

Không thấy successful login sau Leaver không chứng minh user mất mọi quyền. Một old access token hoặc local API key có thể tạo API PERMIT mà không có sign-in event tương ứng.

## 12. Non-human identity detection: workload, service, integration

**Non-human identities (NHI)** bao gồm service principals, API clients, managed identities, workloads, robots và integration accounts. Chúng thường không có hành vi tương tự con người.

### 12.1. Baseline NHI phù hợp

| Thuộc tính | Ví dụ expected | Điều cần đối chiếu |
|---|---|---|
| Runtime | order-sync worker ở production | Cloud account, namespace, deployment |
| Trust issuer | Approved OIDC issuer | Issuer/certificate chain |
| Subject | Repo/branch/service account được phép | Federation trust condition |
| Audience | API target xác định | Resource/token profile |
| Actions | orders.read, invoices.create | RBAC/ABAC least privilege |
| Schedule | Batch theo lịch | Approved emergency rerun |
| Credential | Managed identity hoặc vault key | Rotation/last-used/owner |
| Tenant | Một tenant theo hợp đồng | Cross-tenant access |
| Lifecycle | ACTIVE tới service retirement | Issuance/access sau endAt |

### 12.2. Các use case NHI đáng ưu tiên

- Service principal owner rỗng nhưng có admin role.
- Stale secret hoặc key version cũ còn được dùng sau rotation.
- Client credentials grant xuất phát từ runtime không hợp lệ.
- Workload federation nhận subject/branch rộng hơn chính sách.
- Production service có secret trùng với dev/staging.
- API scope tự tăng mà không có business approval.
- Token issuance sau service retired.
- Integration connector dùng credential có quyền SCIM admin tại target lạ.
- Service identity tạo secondary keys/principals trước khi bị thu hồi.

### 12.3. Cloud location không phải địa điểm của con người

Một workload chạy qua nhiều cloud regions trong deployment migration có thể phát token từ IP khác nhau. Không dùng detector “impossible travel” cho NHI như với người. Dùng identity/trust/runtime/expected resource và approved deployment events.

### 12.4. Workload federation cần kiểm trust claims

Khi CI job đổi branch hoặc repository, trust policy có thể quyết định token issuance. Detection kiểm tra trusted issuer, subject, audience, environment, repository ownership và cloud role binding. Không tin các trường claims không có chữ ký/nguồn đáng tin.

### 12.5. Owner Leaver khác service Leaver

Một kỹ sư owner backup service nghỉ việc không có nghĩa phải tắt ngay job đang hợp lệ. Đánh giá:

- Thu hồi quyền human vào vault, CI, cloud role và admin portal.
- Chỉ định owner mới và reviewer.
- Kiểm tra secret từng bị export/download.
- Rotate/revoke credential nếu rủi ro yêu cầu.
- Không xóa service account khi business dependency vẫn active.
- Khi **service chính thức retired**, revoke trust/role/credentials và verify.

### 12.6. SCIM connector là NHI có quyền đặc biệt

Connector dùng SCIM có thể tạo/disable User và thêm/gỡ Group. Một bất thường ở connector cần kết hợp token issuance, source HRIS request, target operations, approval và affected principals; cảnh báo mass changes không có source event hợp lệ.

## 13. Detection cho recertification, owner và policy expiry

Có những sai lệch không cần attack event để phát hiện.

### 13.1. Access review không bao phủ đủ inventory

Một campaign có thể đạt 100% reviewer decisions nhưng bỏ sót 30% local roles và service accounts. Detector **coverage** phải so review snapshot với inventory có version/tenant/source, không chỉ đếm quyết định.

### 13.2. Quyết định REVOKE chưa được thực thi

Khi reviewer chọn REVOKE, đây là **desired change**. Nếu target vẫn có grant, đó là **remediation gap**. Detection cần operation IDs, target readback, pending/partial status và SLO. Không coi REVOKE click là bằng chứng effective revoke.

### 13.3. Orphan ownership

Owner không còn active, sponsor mất hợp đồng hoặc group không có reviewer hợp lệ có thể làm quyền không được giám sát. Detector nên phát hiện thiếu ownership và gửi tới steward có thẩm quyền; không tự assign owner ngẫu nhiên.

### 13.4. Time-bound entitlements và exceptions

Quyền JIT/temporary grant quá expiresAt nhưng target vẫn ACTIVE là một use case rủi ro. Các ngoại lệ được chấp thuận phải có scope, approver, compensating control, owner, expiry và review date. Exception không biến trạng thái tồn dư thành “đã được revoke”.

### 13.5. SoD trong approval

Một actor vừa request vừa approve và thực thi grant có thể trái separation policy. Cần xem role/action/resource/actor thực tế và ngoại lệ hợp lệ, không kết luận từ trùng displayName.

## 14. Risk scoring và mức độ ưu tiên trong identity detection

Phát hiện nhiều tín hiệu không đồng nghĩa tất cả có cùng mức khẩn. Một số tình huống nên dùng **hard policy violation**, số khác cần correlation và probabilistic confidence.

### 14.1. Ba chiều tách biệt

1. **Signal/anomaly strength:** mức khác so với expected baseline.
2. **Evidence confidence:** độ đáng tin của nguồn, mapping, completeness.
3. **Business impact:** quyền hiệu lực, resource sensitivity, tenant scope và blast radius.

Ví dụ một IP geo mới có anomaly score cao nhưng confidence thấp; một production-admin grant không có approval có confidence cao và impact lớn dù account vẫn đăng nhập từ thiết bị quen thuộc.

### 14.2. Mẫu rule-based score minh họa

~~~text
New device + unusual app              +15
MFA denial burst                      +20
Sensitive privileged resource         +25
Credible new OAuth consent anomaly    +20
Trusted known managed runtime         -10

Score = clamp(0, 100, weighted features)

Hard policy violation độc lập:
  Verified Leaver principal được PERMIT sau cutoff
  hoặc admin role grant trái explicit deny/approval policy
~~~

Trọng số **chỉ để minh họa**. Production cần hiệu chỉnh theo dữ liệu, historical cases và risk policy. Không để feature “trusted IP” triệt tiêu hard policy violation.

### 14.3. Các tín hiệu không độc lập

MFA push burst và nhiều failed auth events có thể đến từ cùng nguyên nhân; unfamiliar country và impossible travel đều dựa một IP geo. Nếu cộng điểm không kiểm feature dependency, score bị thổi phồng. Dùng correlation/dedup và confidence.

### 14.4. Priority mapping

| Risk level giả định | Điều kiện minh họa | Hướng xử lý |
|---|---|---|
| **Informational** | Một telemetry data gap đơn lẻ | Tạo data-quality task |
| **Low** | New app login của Joiner có approval | Audit, theo dõi |
| **Medium** | Device mới và có một signal authentication khác | Step-up hoặc analyst review |
| **High** | Privileged role grant thiếu authorization evidence | Ưu tiên điều tra/containment theo policy |
| **Critical** | Verified compromise hoặc high-impact access còn usable trái control | Incident response khẩn theo runbook |

Đây không phải hệ severity chung; đội bảo mật cần tiêu chí và escalation path theo chức năng.

### 14.5. Confidence thấp không cho phép mặc định safe

Nếu target role inventory không đầy đủ, không được suy không có admin. Ghi DATA_GAP hoặc UNKNOWN; với môi trường critical có thể cần fail-safe access policy độc lập với monitoring.

## 15. Sequence detection: phát hiện chuỗi sự kiện tạo quyền nguy hiểm

Một chuỗi identity events có thể nguy hiểm hơn từng event riêng.

### 15.1. Chuỗi có thể phản ánh account takeover

~~~text
T1: nhiều failed sign-in hoặc MFA denials
T2: successful login với context mới
T3: MFA method / recovery settings changed
T4: new OAuth app consent hoặc API key created
T5: privileged resource access / export
~~~

Đây là **kịch bản điều tra**, không phải bằng chứng chắc chắn rằng mọi bước có cùng attacker. Cần authentication request/session/actor correlation, source provenance, approval và user verification.

### 15.2. Chuỗi có thể phản ánh privilege persistence

~~~text
T1: principal được JIT admin trong change window
T2: tạo new service principal / long-lived credential
T3: JIT grant hết hạn
T4: secondary service principal vẫn có standing privileged role
~~~

Detection phải xem **secondary grants** sinh ra từ elevated session. Thu hồi JIT role ở user không mặc định xóa principal/key đã tạo.

### 15.3. Chuỗi có thể phản ánh sync drift

~~~text
T1: HRIS Leaver version 109
T2: IAM revoke finance group
T3: SaaS readback group absent
T4: retry cũ Mover version 108 thêm group trở lại
T5: SaaS resource request PERMIT
~~~

Detectors kiểm tra version ordering và **re-grant after revoke**, không chỉ check trạng thái một lần.

### 15.4. Correlation không dựa email đơn thuần

Chuỗi events phải link cùng issuer+principalId+tenant khi có thể và theo session/client refs tin cậy. Một IP có thể đại diện nhiều người qua NAT; một username có thể tồn tại trong hai tenants.

### 15.5. Event lateness và temporal windows

Một app audit event có thể ingest muộn hơn IdP events. Dùng eventTime/source version, windows có margin và cập nhật case khi evidence đến. Không giả định thứ tự arrival bằng causality.

## 16. Threat modeling: identity attack paths và detection gaps

Trong threat modeling, một đường rủi ro thường gồm **entry point → identity/credential → granted path → resource action → hậu quả**.

### 16.1. Ví dụ attack path theo quyền, không theo giao diện

~~~text
Credential bị lộ
    -> Client có thể xác thực tới token issuer
    -> Service principal có role rộng
    -> Access token đúng audience được cấp
    -> Resource server PERMIT sensitive action
    -> Dữ liệu có thể bị export/modified
~~~

Detection points gồm credential use ngoài runtime hợp lệ, token issuance sai trust, privilege scope, data-plane anomaly và audit resource action.

### 16.2. Những điểm mù thường gặp

| Blind spot | Lý do | Biện pháp |
|---|---|---|
| Chỉ có IdP login logs | Bỏ RP sessions/local API keys | Thu thập target authz/token logs |
| Chỉ có SCIM logs | Bỏ direct SaaS ACL | Target inventory + readback |
| Chỉ theo người dùng | Bỏ service principals | NHI registry/trust telemetry |
| Chỉ xem role names | Bỏ nested grants và ABAC | Effective entitlement graph |
| Chỉ đếm failed logins | Bỏ stolen valid credential | Successful auth + resource events |
| Chỉ xem current state | Mất sai lệch lịch sử | Temporal snapshots/versioning |
| Chỉ xem command result | Nhầm ACK với enforcement | Target verification |
| Chỉ dùng IP geo | Nhiều false positives | Device/runtime context và confidence |
| Thiếu approved exceptions | Báo nhầm JIT/migration | Time-bound approved exception registry |
| Mất SIEM events | Tưởng không có anomaly | Heartbeat/source-to-sink reconciliation |

### 16.3. Không suy “không thấy alert” là an toàn

Không có alert có thể vì attack chưa diễn ra, tín hiệu quá yếu, dữ liệu thiếu, rule không được chạy hoặc pipeline lỗi. Nên ghi coverage, detection assumptions và residual risk.

### 16.4. Detection control khác preventive control

Ngăn account Leaver truy cập bằng server-side authorization là **preventive**. Alert sau khi access được PERMIT là **detective**. Tổ chức cần cả hai, không dựa vào SOC phát hiện để bù vô hạn cho thiếu revoke.

## 17. Thiết kế event schema và detection case

Một detection đáng tin phải giải thích được từ **sự kiện nguồn**, **ngữ cảnh IAM**, **rule**, tới **kết luận và hành động**. Nên tách event, detection signal và case.

### 17.1. Normalized identity event — JSON minh họa

~~~json
{
  "eventId": "id-event-2841",
  "schemaVersion": "1.0",
  "eventType": "ROLE_GRANT",
  "eventTime": "2026-11-23T09:00:04Z",
  "ingestedAt": "2026-11-23T09:00:06Z",
  "producer": {
    "system": "cloud-iam",
    "tenantId": "tenant-a",
    "trustLevel": "VERIFIED"
  },
  "actor": {
    "principalId": "svc-iam-connector-prod",
    "principalType": "SERVICE"
  },
  "subject": {
    "principalId": "employee-1042",
    "principalType": "HUMAN",
    "identitySource": "hris",
    "lifecycleVersion": 108,
    "lifecycleStatus": "ACTIVE"
  },
  "target": {
    "systemId": "cloud-prod",
    "tenantId": "tenant-a",
    "resourceId": "project-finance-prod",
    "entitlementId": "cloud-role-admin"
  },
  "operation": {
    "action": "GRANT_ROLE",
    "outcome": "SUCCESS",
    "approvalRef": null,
    "policyVersion": "privilege-policy-v4"
  },
  "correlation": {
    "requestId": "iam-operation-229",
    "workflowId": "jml-change-1042-11",
    "causationId": "source-event-108"
  }
}
~~~

Tất cả IDs là giả lập. **approvalRef=null trong event không chứng minh không có approval**: cần đối chiếu request registry đúng tenant, role và thời điểm. Nếu registry timeout, trạng thái phải là UNKNOWN, không được kết luận không có phê duyệt.

### 17.2. Detection alert có nguồn chứng cứ

~~~json
{
  "detectionId": "identity-det-2841",
  "type": "PRIVILEGED_GRANT_WITHOUT_VALID_APPROVAL",
  "detectorVersion": "2.3.0",
  "policyVersion": "privilege-policy-v4",
  "subjectRef": "employee-1042",
  "actorRef": "svc-iam-connector-prod",
  "tenantId": "tenant-a",
  "targetRef": "cloud-prod/project-finance-prod",
  "risk": {
    "severity": "HIGH",
    "signalConfidence": "HIGH",
    "businessImpact": "HIGH",
    "status": "PENDING_VALIDATION"
  },
  "evidenceRefs": [
    "id-event-2841",
    "approval-lookup-2841",
    "role-readback-2841"
  ],
  "observations": {
    "rolePresent": true,
    "approvalState": "NOT_FOUND_IN_AUTHORITATIVE_REGISTRY"
  },
  "response": {
    "recommended": "PRIVILEGE_REVIEW_AND_CONTAINMENT",
    "owner": "cloud-iam-oncall"
  },
  "createdAt": "2026-11-23T09:00:15Z"
}
~~~

Ví dụ này là mẫu event tự thiết kế, không phải định dạng chuẩn của SIEM/ITDR. Tình trạng pending vẫn cần analyst kiểm tra evidence, nguồn approval và exception.

### 17.3. Case cần bằng chứng và giới hạn

Một investigation case nên có: detector version, event IDs, provenance, identity/tenant mapping, effective role, JML sourceVersion, approval/exception check, target observed state, response, owner, evidenceRef, outcome và giới hạn coverage. Không lưu raw bearer tokens, password, OTP, private key hoặc đầy đủ HRIS record.

### 17.4. EventId không phải caseId

Một event có thể sinh nhiều signal, nhiều events có thể gom vào một case; mỗi response có operationId/attemptId riêng. Tách identifiers để tránh đếm trùng và giữ được audit trail của các lần retry.

## 18. Detection-as-code: rule YAML minh họa

Một rule cần **owner, version, nguồn yêu cầu, scope, test cases, response và rollback**. Cấu hình sau là schema giả lập dùng giảng dạy.

~~~yaml
identityDetection:
  ruleId: IAM-LEAVER-RESIDUAL-ACCESS
  version: "1.0"
  ownerTeam: identity-security
  purpose: "Phát hiện access path còn mở sau Leaver cutoff"
  scope:
    principalTypes: [HUMAN, CONTRACTOR, GUEST]
    targetRiskTiers: [CRITICAL, HIGH]
  requiredSources:
    - authoritative-lifecycle
    - target-account-inventory
    - resource-authorization-events
  joinKeys:
    - tenantId
    - immutablePrincipalId
    - targetSystemId
  timeSemantics:
    compareAgainst: effectiveAt
    requireSourceVersion: true
    allowLateEvents: true
  conditions:
    all:
      - authoritativeStatus: LEAVER
      - targetEventAfterEffectiveAt: true
      - targetAccessOutcome: PERMIT
      - policyProhibitsAccess: true
  dataQuality:
    missingIdentityMapping: NEEDS_ENRICHMENT
    missingTargetEvidence: UNKNOWN
    neverTreatTimeoutAsAbsent: true
  response:
    severity: HIGH
    action: CREATE_CASE_AND_REVIEW_CONTAINMENT
    verification: TARGET_ACCESS_PATH_READBACK
  exceptions:
    mustBeApproved: true
    mustHaveExpiry: true
    mustHaveOwner: true
  audit:
    includeRuleVersion: true
    redactSecrets: true
~~~

### 18.1. Tại sao rule không chỉ kiểm IdP login?

Một API PERMIT qua RP session/old access token có thể không tạo interactive sign-in mới. Rule quan sát **resource authorization sau cutoff**, liên kết identity/source state và policy.

### 18.2. Time-bound exceptions

Những exceptions hợp lệ phải có approval, resource/action scope, owner và expiry. Không cho một exception tổng quát “ignore employee-1042 forever” triệt tiêu mọi detection sau này.

### 18.3. Deployment report-only và enforce

Với rule mới có false-positive risk, chạy report-only trên data fixtures và dữ liệu được phép trước khi cho phép auto-containment. Cần tests, monitoring, approved policy, kill switch và escalation path; không dùng một threshold chưa hiệu chỉnh để block production toàn diện.

### 18.4. Regression cases tối thiểu

Test: Leaver+API PERMIT, Leaver+DENY, Joiner pre-start permitted/denied theo scope, Mover có grant cũ hợp lệ, approved exception, missing mapping, target readback timeout và event version cũ đến muộn.

## 19. Pseudocode: xử lý một Identity detection event

### 19.1. Pipeline logic

~~~text
function evaluateIdentityEvent(raw):
    e = trustedIngestion.validateNormalize(raw)

    if e INVALID:
        quarantineWithReason(raw.reference)
        return DATA_QUALITY_CASE

    if durableDedup.wasSeen(e.producer, e.eventId):
        return DUPLICATE_HANDLED

    subject = identityResolver.resolve(
        e.identitySource, e.issuer,
        e.tenantId, e.immutablePrincipalId
    )

    if subject UNRESOLVED:
        emitMappingGap(e)
        return NEEDS_ENRICHMENT

    graph = temporalIdentityGraph.loadAsOf(
        subject, e.eventTime, e.sourceVersion
    )
    policy = approvedPolicyRegistry.effectiveAt(e.eventTime)
    exceptions = exceptionRegistry.validFor(
        subject, e.targetResource, e.action, e.eventTime
    )

    signals = evaluateRulesAndSequences(
        e, graph, policy, exceptions
    )
    confidence = evidenceConfidence(e, graph)
    impact = effectiveAccessImpact(e, graph)

    decision = riskPolicy.evaluate(signals, confidence, impact)

    audit.appendDecision(
        eventRef=e.reference,
        detectorVersion=policy.version,
        signals=signals,
        outcome=decision,
        redactSecrets=true
    )

    if decision needsReview:
        createOrUpdateCase(subject, e, decision)

    if decision requiresApprovedContainment:
        executeAndVerifyAtTarget(e, decision)

    return decision
~~~

Pseudocode không tự bảo đảm exactly-once, transaction atomicity với SaaS hoặc tính hợp lệ mọi policy. Production cần durable events, retry/idempotency, concurrency guards, outbox và observability.

### 19.2. UNKNOWN không phải LOW

Target readback timeout hoặc không tìm được identity mapping chỉ chứng minh **không đủ dữ liệu**, không phải grant đã mất hoặc account an toàn. Detection cần data-quality alerts và escalation theo asset risk.

### 19.3. Chống event sai thứ tự

Không để Mover v108 đến sau Leaver v109 hồi sinh role. Dùng sourceVersion, effectiveAt, current desired state và rule về rehire/identity incarnation.

### 19.4. Kết quả response cần được readback

Detector gửi revoke, target ACK chưa phải quyền đã hết. Ghi operation request, response, observed role/token/session state và kết quả resource authorization ở scope cần kiểm tra.

## 20. Java: mô hình đơn giản phân biệt SIGNAL và POLICY_VIOLATION

Đoạn Java mô phỏng **cách trình bày quyết định**, không phải hệ thống xác thực/token/authorization hoàn chỉnh.

~~~java
import java.time.Instant;
import java.util.Objects;

enum AccountState { ACTIVE, LEAVER, UNKNOWN }
enum AccessOutcome { PERMIT, DENY, UNKNOWN }
enum FindingKind {
    VERIFIED_POLICY_VIOLATION, SIGNAL, INSUFFICIENT_DATA, NONE
}

record IdentityObservation(
        String principalId,
        String tenantId,
        Instant eventTime,
        Instant lifecycleEffectiveAt,
        AccountState accountState,
        AccessOutcome accessOutcome,
        boolean sensitiveResource,
        boolean unusualDevice
) {}

record DetectionResult(
        FindingKind kind,
        int illustrativeScore,
        String reason
) {}

final class IdentityDetectionPolicy {

    static DetectionResult evaluate(IdentityObservation o) {
        Objects.requireNonNull(o, "observation");
        Objects.requireNonNull(o.principalId(), "principalId");
        Objects.requireNonNull(o.tenantId(), "tenantId");
        Objects.requireNonNull(o.eventTime(), "eventTime");

        if (o.accountState() == AccountState.UNKNOWN
                || o.accessOutcome() == AccessOutcome.UNKNOWN) {
            return new DetectionResult(
                    FindingKind.INSUFFICIENT_DATA, 0, "Context incomplete");
        }

        boolean leaverAfterCutoff =
                o.accountState() == AccountState.LEAVER
                && o.lifecycleEffectiveAt() != null
                && !o.eventTime().isBefore(o.lifecycleEffectiveAt());

        if (leaverAfterCutoff
                && o.accessOutcome() == AccessOutcome.PERMIT) {
            // Requires independently verified identity mapping and policy scope.
            return new DetectionResult(
                    FindingKind.VERIFIED_POLICY_VIOLATION,
                    100, "Permitted access after Leaver cutoff");
        }

        int score = 0; // Illustrative, not calibrated.
        if (o.unusualDevice()) score += 15;
        if (o.sensitiveResource()) score += 25;

        if (score > 0) {
            return new DetectionResult(
                    FindingKind.SIGNAL, score, "Review supporting evidence");
        }
        return new DetectionResult(FindingKind.NONE, 0, "No sample signal");
    }
}
~~~

### 20.1. Điều kiện ngoài đoạn code

Input flags phải đến từ event/identity context đáng tin; policy phải xác định access sau cutoff thật sự không được phép, xử lý approved exceptions, identity lifecycle versions và mapping target. Account LEAVER chưa chứng minh mọi request bị cấm nếu có trường hợp được policy cho phép cụ thể.

### 20.2. Tại sao UNKNOWN không được coi an toàn?

Nếu quyền cloud-admin không thể truy vấn, không thể kết luận không có role. Đoạn code trả INSUFFICIENT_DATA để buộc kiểm tra evidence. Hệ thống thật có thể phân bổ confidence và xử lý DATA_GAP riêng risk score.

### 20.3. Unit test cần kiểm những gì?

ACTIVE+PERMIT, LEAVER+DENY, LEAVER+PERMIT sau cutoff, LEAVER trước cutoff, UNKNOWN identity, UNKNOWN outcome, missing effectiveAt, sensitive resource và cross-tenant mapping. Tests cho containment chạy ở module có sandbox/mock target riêng, không thử tắt production users ngoài phê duyệt.

## 21. PostgreSQL: truy vấn các ứng viên Identity detection

Các câu SQL sau dùng **read models giả định**; tổ chức cần điều chỉnh theo event schema, temporal join, target capabilities, authorization và retention thực tế. Kết quả query là **candidates**, chưa tự là sự cố.

### 21.1. Privileged grant thiếu approvalRef trong log

~~~sql
SELECT
    g.tenant_id,
    g.subject_principal_id,
    g.target_system_id,
    g.entitlement_id,
    g.event_time,
    g.correlation_id
FROM normalized_identity_events AS g
WHERE g.event_type = 'ROLE_GRANT'
  AND g.outcome = 'SUCCESS'
  AND g.is_privileged = TRUE
  AND g.event_time >= :windowStart
  AND g.event_time < :windowEnd
  AND g.tenant_id = :authorizedTenantId
  AND g.approval_ref IS NULL;
~~~

Thiếu approvalRef trong log không chắc thiếu approval thật; phải tra authoritative approval registry và xét lỗi correlation/ingestion.

### 21.2. API PERMIT sau Leaver cutoff

Giả định lifecycle_intervals lưu lịch sử theo valid_from/valid_until (cả hai không null) và đã resolve đúng principal/tenant:

~~~sql
SELECT
    a.tenant_id,
    a.principal_id,
    a.target_system_id,
    a.resource_id,
    a.action,
    a.event_time,
    l.effective_at,
    a.correlation_id
FROM normalized_access_events AS a
JOIN lifecycle_intervals AS l
  ON a.principal_id = l.principal_id
 AND a.tenant_id = l.tenant_id
 AND a.event_time >= l.valid_from
 AND a.event_time < l.valid_until
WHERE l.lifecycle_state = 'LEAVER'
  AND a.event_time >= l.effective_at
  AND a.outcome = 'PERMIT'
  AND a.event_time >= :windowStart
  AND a.event_time < :windowEnd
  AND a.tenant_id = :authorizedTenantId;
~~~

Nếu interval có đầu cuối mở, cần xử lý NULL. Query còn phải xét rehire/new identity incarnation, approved exception, resource policy và độ tin cậy mapping trước khi kết luận vi phạm.

### 21.3. Service principal chưa có owner nhưng vẫn có grants

~~~sql
SELECT
    p.tenant_id,
    p.principal_id,
    p.environment,
    p.last_review_at,
    COUNT(g.entitlement_id) AS active_grants
FROM service_principals AS p
JOIN active_entitlement_grants AS g
  ON g.principal_id = p.principal_id
 AND g.tenant_id = p.tenant_id
WHERE p.owner_team_id IS NULL
  AND p.status = 'ACTIVE'
  AND p.tenant_id = :authorizedTenantId
GROUP BY
    p.tenant_id, p.principal_id,
    p.environment, p.last_review_at
HAVING COUNT(g.entitlement_id) > 0;
~~~

Xác minh service catalog/change records trước khi gắn nhãn orphan: đây có thể là lỗi đồng bộ owner field.

### 21.4. Phát hiện regrant sau revoke

~~~sql
SELECT
    g.tenant_id, g.principal_id, g.entitlement_id,
    g.event_time AS grant_time, prior.latest_revoke_time
FROM normalized_role_events AS g
JOIN LATERAL (
    SELECT MAX(r.event_time) AS latest_revoke_time
    FROM normalized_role_events AS r
    WHERE r.tenant_id = g.tenant_id
      AND r.principal_id = g.principal_id
      AND r.entitlement_id = g.entitlement_id
      AND r.event_type = 'ROLE_REVOKE'
      AND r.outcome = 'SUCCESS'
      AND r.event_time < g.event_time
) AS prior ON prior.latest_revoke_time IS NOT NULL
WHERE g.event_type = 'ROLE_GRANT'
  AND g.outcome = 'SUCCESS'
  AND g.tenant_id = :authorizedTenantId
  AND g.event_time >= :windowStart
  AND g.event_time < :windowEnd;
~~~

Không phải regrant nào cũng trái phép: có thể có access request mới hợp lệ. Kiểm sourceVersion, current JML desired state, grant scope, approval và target readback.

### 21.5. Review REVOKE nhưng target vẫn ACTIVE

~~~sql
SELECT
    r.review_item_id,
    r.principal_id,
    r.target_system_id,
    r.entitlement_id,
    r.decided_at,
    g.observed_at,
    g.grant_status
FROM access_review_decisions AS r
JOIN observed_entitlement_states AS g
  ON g.tenant_id = r.tenant_id
 AND g.principal_id = r.principal_id
 AND g.target_system_id = r.target_system_id
 AND g.entitlement_id = r.entitlement_id
WHERE r.decision = 'REVOKE'
  AND g.grant_status = 'ACTIVE'
  AND g.observed_at >= r.decided_at
  AND r.tenant_id = :authorizedTenantId;
~~~

Cần xét remediation SLA, exception và target freshness. Decision click lúc 09:00 chưa đồng nghĩa cần revoke tức thì nếu policy có cutoff khác.

### 21.6. Dữ liệu truy vấn phải được bảo vệ

Tenant filter cần bắt nguồn từ scope được backend ủy quyền, không chỉ query parameter do client tùy ý đặt. Bảo vệ exports và logs, tránh leak principal/entitlement. Dùng COUNT(DISTINCT operationId) khác COUNT(attemptId) khi thống kê retries.

## 22. Playbook triage: từ alert tới xác minh

### 22.1. Bước 1 — kiểm event và source

- Rule/detector version, event type và exact condition?
- Producer được xác thực, time/correlation đáng tin?
- Outcome là SUCCESS, DENY, PENDING, ACK hay UNKNOWN?
- Có duplicate, retry, message delay hoặc mất telemetry?
- Actor và subject là principals nào, tenant/issuer nào?

### 22.2. Bước 2 — kiểm context danh tính

- Human, guest, contractor, integration hay workload?
- Current/as-of JML status và effectiveAt, lifecycleVersion?
- Owner/sponsor có hợp lệ và còn active?
- Có Mover/rehire/migration/secret rotation vừa xảy ra?
- Entitlement nào và hiệu lực trên resource nào?

### 22.3. Bước 3 — đối chiếu approval và policy

- Policy version nào có hiệu lực lúc event?
- Access request, PAM JIT, exception/consent có authority?
- Permission đến từ direct grant, group, ABAC hay ACL nào?
- Có đường thứ hai vẫn cho access sau revoke?
- Resource action có thực sự bị PERMIT không?

### 22.4. Bước 4 — kiểm chuỗi và tài nguyên

- Có login anomaly, MFA reset, consent, API key issuance hay role escalation?
- Có resource export, privileged action hoặc secondary grant?
- Token/session được phát và được dùng ở nơi nào?
- Các events có cùng session/auth request ID tin cậy, hay chỉ tình cờ chung IP?
- Có hành vi tương tự trên nhiều principals hoặc applications?

### 22.5. Bước 5 — phân loại kết quả

| Disposition | Ý nghĩa | Hành động |
|---|---|---|
| **BENIGN_EXPECTED** | Hành vi có căn cứ và bằng chứng | Lưu triage outcome, tuning đúng scope |
| **AUTHORIZED_EXCEPTION** | Ngoại lệ còn hiệu lực | Theo dõi expiry/risk |
| **CONTROL_DEFICIENCY** | Sai lệch kiểm soát đã chứng minh | CAPA và audit finding nếu phù hợp |
| **SUSPICIOUS_UNCONFIRMED** | Tín hiệu mạnh, chưa đủ kết luận | Step-up/containment theo risk |
| **CONFIRMED_COMPROMISE** | Có evidence chiếm quyền | Incident response |
| **DATA_INSUFFICIENT** | Mapping/evidence chưa đủ | Enrichment và source health task |
| **DETECTOR_DEFECT** | Rule/schema gây cảnh báo sai | Fix rule, regression tests |

### 22.6. Triage không đòi password/OTP

Xác minh user bằng kênh tin cậy của tổ chức, không yêu cầu đọc mật khẩu, OTP, backup code hoặc bấm approve MFA push chỉ để chứng minh người dùng là chủ account.

### 22.7. Không xóa evidence khi đóng alert

Ghi caseId, detectionId, reviewer, actor, timestamps, reason, evidenceRefs, owner, response và verification. BENIGN không đồng nghĩa raw source event phải xóa khỏi retention được phê duyệt.

## 23. Containment và response đúng access path

Một detection cần đưa tới kiểm soát giảm rủi ro, không chỉ ticket.

### 23.1. Hành động có thể phù hợp

1. Yêu cầu reauthentication/step-up.
2. Chặn new login ở IdP nếu căn cứ đủ.
3. Invalidate IdP/RP/PAM sessions theo capability.
4. Rotate/revoke password, client secret, certificate, API key hoặc refresh token bị lộ.
5. Gỡ direct grants, group/role hoặc JIT activation trái policy.
6. Disable service principal/STS trust khi workload retired hoặc bị chiếm.
7. Deny resource API bằng policy enforcement point.
8. Điều tra delegated grants, OAuth consent, secondary credentials.
9. Mở incident hoặc audit finding với root cause/owner.
10. Thực hiện target readback, verify effective access và cập nhật trạng thái.

### 23.2. Tách command và outcome

~~~text
DETECTION_RAISED
RESPONSE_APPROVED
REVOKE_COMMAND_SENT
TARGET_ACKNOWLEDGED
TARGET_READBACK_OBSERVED
ACCESS_PATH_VERIFIED_REVOKED
CASE_CLOSED
~~~

Timeout hoặc 5xx ở readback là UNKNOWN/PARTIAL. HTTP 204 không chứng minh token/session/grant ở mọi target đã bị chặn.

### 23.3. Hạn chế của token revocation

Self-contained bearer token có thể tiếp tục được chấp nhận đến expiry nếu resource server không hỗ trợ online status/denylist. Phải xác định actual provider behavior, residual window và compensating control, không giả định IdP disable cắt mọi access tức thì.

### 23.4. Auto-containment cần an toàn vận hành

False positive trên SCIM connector, emergency admin hoặc CI runner có thể làm outage. Automation cần scope hẹp, owner, approval, circuit breaker, kill switch, audit và cách restore hợp lệ. Với compromise nghiêm trọng được chứng minh, containment nhanh vẫn cần theo runbook.

### 23.5. Recovery đúng JML

Khi mở lại account, đối chiếu current desired entitlement và status. Không restore mọi role cũ, nhất là những grants đã hết hạn hoặc không còn business need.

### 23.6. Verification đóng vòng lặp

Đảm bảo target state và resource access outcome đạt yêu cầu trong phạm vi, exception được quản trị, owner và evidence đều rõ. Không đóng theo trạng thái “Done” của request khi access path vẫn còn.

## 24. Governance, audit integrity và privacy của Identity detection

Identity telemetry tiết lộ quyền nhân sự, ứng dụng, tài sản nhạy cảm và các thay đổi cấp cao. Chính monitoring cũng phải bảo vệ khỏi lạm dụng.

### 24.1. Phân quyền cho thành phần

| Thành phần | Nên làm | Không nên |
|---|---|---|
| Collector | Đọc đúng audit sources | Có IAM super-admin mặc định |
| Detection engine | Đọc context, tạo case | Tự sửa mọi quyền |
| Response executor | Revoke theo scoped approval | Có quyền không giới hạn |
| SOC analyst | Xem case thuộc phạm vi | Export secrets/PII hàng loạt |
| Rule owner | Thay rule theo change control | Xóa audit history |
| Auditor | Xem evidence/decision trail | Giữ production credential |

### 24.2. Tamper-evident, không tự coi tamper-proof

Append-only event history, immutable storage, hash/signature hoặc external replication có thể giúp phát hiện sửa đổi. Nhưng nếu một actor điều khiển data và signing keys, vẫn có nguy cơ; cần trust separation, access logs và key custody.

### 24.3. Data minimization

Không đưa password, OTP, raw access/refresh token, private key, session cookie hoặc HRIS sensitive details không cần thiết vào SIEM/case notes. Dùng immutable surrogate IDs và evidenceRef có quyền truy cập riêng.

### 24.4. Tenant isolation

Một actor ở tenant A không thể xem case và quyền ở tenant B bằng việc biết case ID. Enforce ở API, query, evidence store và export; frontend filters chỉ là hỗ trợ giao diện.

### 24.5. Retention và purpose limitation

Retention phải theo pháp luật/chính sách, data classification, incident evidence và privacy; không có con số chung. Không dùng late-night sign-in, thiết bị mới hay nơi làm việc để suy đoán hiệu suất/đặc điểm nhạy cảm của người dùng ngoài mục tiêu bảo mật.

### 24.6. Rule change là sự kiện đáng monitoring

Rule, allowlist, suppression, scoring thresholds và response actions cần version/owner/review/test/rollback. Bất thường khi một detector critical bị disable hoặc suppression được thêm ngoài change window cũng là identity security signal.

## 25. Case study 1: Leaver đã disabled ở IdP nhưng SaaS vẫn PERMIT

### 25.1. Bối cảnh giả lập

Một doanh nghiệp dùng HRIS, IdP, Finance SaaS và một IAM orchestrator có SCIM connector. Nhân viên U nghỉ việc lúc 17:00 theo giờ Việt Nam; policy yêu cầu ngắt mọi access tới Finance SaaS từ cutoff, không chỉ chặn sign-in mới.

**Business source:** HRIS đã xác nhận Leaver với immutable subjectId, effectiveAt và sourceVersion.  
**Desired:** IdP disabled, Finance SaaS account/grants/sessions không thể tiếp tục truy cập trái policy.  
**Risk:** finance.report.export là action nhạy cảm.

### 25.2. Timeline và quan sát

| Giờ (UTC+07:00) | Event | Ý nghĩa |
|---|---|---|
| 17:00:00 | HRIS Leaver effectiveAt | Quyền phải hết theo policy |
| 17:00:02 | IAM gửi disable IdP | Lệnh đã gửi |
| 17:00:03 | IdP báo disabled | Chặn một phần đường xác thực |
| 17:00:05 | SCIM PATCH User.active=false tại SaaS, HTTP 204 | Chưa chứng minh phiên/token hết |
| 17:00:08 | Target readback account.active=false | Account state đạt |
| 17:01:00 | RP session còn active | Cần đánh giá session access |
| 17:02:00 | Resource API PERMIT finance.report.export | **Residual access có chứng cứ** |
| 17:02:10 | Detection tạo high-risk case | Correlate source–target–resource |
| 17:03:00 | App owner revoke local session/role | Remediation initiated |
| 17:04:00 | Resource API DENY cùng scoped action | Evidence về access path |
| 17:05:00 | Reconciliation tất cả scoped access paths | Có thể xem closure theo policy |

Dữ liệu hoàn toàn là ví dụ. Một DENY tại endpoint chưa đủ chứng minh **tất cả** quyền khác đã hết.

### 25.3. Detection pipeline đã làm gì?

1. Nối HRIS subjectId với IdP và Finance targetAccountId.
2. Nhận Leaver effectiveAt/sourceVersion.
3. Nhận SCIM ACK và target account state.
4. Nhận Finance API audit PERMIT từ application/session còn hoạt động.
5. Kiểm action/resource/tenant thuộc phạm vi cấm sau cutoff.
6. Tạo case **CONFIRMED_POLICY_VIOLATION** theo kiểm soát có hiệu lực, không tự khẳng định “attacker đã export”.
7. Đề xuất containment và alert app owner.
8. Ghi kết quả revoke + target readback/evidence.
9. Đánh giá có cần **audit finding về deprovisioning gap** hay không.

### 25.4. Root cause nào có thể xảy ra?

- Provider giữ local session sau khi SCIM disable.
- Direct SaaS role nằm ngoài SCIM role mapping.
- Orchestrator coi HTTP 204 là toàn bộ verified.
- Token resource server không kiểm entitlement mới.
- App không có integration với central session revocation.
- SIEM thiếu data-plane logs nên trước đó không thấy residual access.

Không khẳng định một nguyên nhân chỉ từ dòng PERMIT; cần kiểm tra provider capability và session/resource logs.

### 25.5. Nếu IP login không bất thường?

Use case vẫn quan trọng: quyền tiếp tục được dùng sau cutoff dù source IP quen thuộc và không có MFA anomaly. Đây là lý do **Identity detection phải rộng hơn Login anomaly**.

### 25.6. Không làm mất dữ liệu nghiệp vụ

Deprovision account không đồng nghĩa xóa invoices hoặc reports. Data retention/owner handover là workflow riêng, có thể tạo detection nếu tài liệu còn share ra ngoài trái policy nhưng không tự xóa dữ liệu hợp lệ.

## 26. Case study 2: service principal mồ côi còn production-admin

### 26.1. Bối cảnh

Một integration worker dùng service principal có quyền đọc đơn hàng từ SaaS A và ghi invoices vào SaaS B. Người tạo integration đã Leaver. Service vẫn phục vụ kinh doanh, nhưng registry thiếu owner, credential chưa rotate và role được nâng lên admin từ một change ticket cũ.

### 26.2. Signals và quyết định

~~~text
Identity type: SERVICE
Workload status: ACTIVE
Technical owner: UNKNOWN
Business owner: Finance Operations
Source entitlement: orders.read
Target entitlement: invoices.create, iam.roles.admin
Expected target actions: invoices.create
Credential last rotation: outside approved window
Recent token issuance: từ runtime khác baseline
~~~

Không một tín hiệu đơn lẻ chứng minh compromise; nhưng combination của **orphan ownership + excessive privilege + unusual runtime** đáng để ưu tiên triage.

### 26.3. Các bước điều tra

1. Xác minh principal ID, issuer/audience và target tenant.
2. Kiểm service catalog/change tickets và team thực sự sở hữu.
3. Kiểm role admin có business need hoặc approved JIT không.
4. Kiểm workload trust conditions, CI/job subject, runtime và resource actions.
5. Xác định ai còn đọc/rotate secret trong vault.
6. Phân biệt token từ deployment migration hợp lệ với credential leakage.
7. Ghi actual effective grants, last-used và risk window.
8. Quyết định giảm quyền theo approved desired state, không tự xóa job.

### 26.4. Corrective action có thể cần

- Gán technical owner mới, giữ business owner và review date.
- Thu hồi quyền human admin/vault của nhân viên Leaver.
- Gỡ iam.roles.admin nếu không có căn cứ, giữ invoices.create cần thiết.
- Rotate/revoke credential cũ, test overlap/cutover.
- Ràng buộc trust với đúng runtime/repository/namespace.
- Thêm resource-level RBAC/ABAC và event correlation.
- Kiểm chứng key cũ không còn usable và role admin đã mất.
- Cập nhật registry, audit/monitoring và kế hoạch retirement.

### 26.5. Rủi ro tự động “xử lý mọi orphan bằng disable”

Tắt service production khi chưa biết dependency có thể ngắt hóa đơn. Identity detection tạo **bằng chứng và ưu tiên xử lý**, còn quyết định containment phải theo business impact, risk và chính sách. Nếu có bằng chứng compromise nghiêm trọng, có thể phải cô lập ngay theo incident runbook.

## 27. KPI, SLI/SLO và chất lượng Identity detection

Một chương trình tốt cần đo **bao phủ, hiệu quả phát hiện, thời gian phản ứng và giảm quyền tồn dư**, không chỉ số alerts.

| KPI/SLI | Câu hỏi | Lưu ý |
|---|---|---|
| Source telemetry coverage | Có bao nhiêu systems/protocols gửi events? | Không dùng số nguồn bỏ qua chất lượng |
| Identity mapping coverage | Bao nhiêu principals có mapping tin cậy? | Không gộp theo email |
| Effective-grant coverage | Bao nhiêu roles/ACLs có inventory/readback? | Direct local grants thường bị bỏ sót |
| JML-to-target reconciliation lag | Events mất bao lâu tới observed target state? | ACK khác verified |
| High-risk residual access | Bao nhiêu quyền nguy hiểm còn mở sau cutoff? | Ưu tiên hơn raw alert count |
| Verified detection cases | Tỷ lệ case có evidence/triage disposition | Không đồng nghĩa TP rate |
| Precision | TP/(TP+FP) trên tập có nhãn đáng tin | Cần ground truth và cohort |
| Recall | TP/(TP+FN) | Không tính được chỉ từ alerted cases |
| False positive rate | FP/(FP+TN) | Phụ thuộc định nghĩa benign population |
| Mean time to detect | Từ event tới detection | Clock/source delay |
| Mean time to triage | Từ alert tới disposition | Không phải root cause fix |
| Mean time to contain | Từ signal tới verified containment | Không phải mọi grant đã revoke |
| Repeat identity findings | Control gap tái diễn | Xem scope và criteria versions |
| Suppression/exception age | Blind spots tồn tại bao lâu? | Approval và expiry |
| Rule health | Rules bị disable/thay đổi không hợp lệ? | Detection infrastructure integrity |
| Critical NHI without owner | Orphan privileged workloads | Registry và owner quality |
| Audit evidence completeness | Case có provenance và verification? | Chất lượng hơn số lượng |

### 27.1. Precision, recall cần dữ liệu có nhãn

~~~text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
FPR       = FP / (FP + TN)
~~~

Nếu chỉ có các alerts đã triage, rất khó biết FN. Dùng incident retrospectives, red-team simulations được phê duyệt và safe synthetic cases để cải thiện đánh giá, không công bố recall “99%” khi thiếu ground truth.

### 27.2. Time-to-ACK, time-to-readback, time-to-enforce khác nhau

~~~text
Business cutoff -> Detection
Detection -> Response command
Command -> Target ACK
ACK -> Target readback
Readback -> Final verified case closure
~~~

Một quyền có thể bị chặn trước lúc readback; **time-to-verified** không luôn bằng actual enforcement time. Nếu chỉ biết 09:00 còn PERMIT, 09:05 đã DENY, enforcement thực tế nằm trong khoảng quan sát.

### 27.3. Nhóm metrics theo severity và identity type

Đừng để một nghìn viewer alerts làm lu mờ hai production-admin violations. Báo breakdown theo privileged/human/NHI/guest, target risk tier, Leaver/Mover và high-impact resources.

### 27.4. Data gap cần có KPI riêng

Một tuần có 0 alerts vì SIEM mất dữ liệu không phải chương trình tốt. Giám sát source heartbeat, ingest lag, dropped events, schema validation failures, unknown mappings và rules disabled.

### 27.5. Không tối ưu dashboard bằng cách giảm scope

Alerts ít đi có thể do false positives được xử lý hoặc do bỏ non-human principals khỏi monitoring. Cần kiểm audit universe, target inventory và method/version khi so sánh các kỳ.

## 28. Ma trận kiểm thử Identity detection

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Joiner account CREATED trước startDate, vẫn DISABLED | Không tự vi phạm |
| Joiner được PERMIT production trước allowed effectiveAt | Policy candidate theo scope |
| Mover được cấp Operations role hợp lệ | Không auto alert |
| Mover còn Finance privileged grant quá cutoff | Residual-role alert |
| Mover stale event đến sau Leaver | Không hồi sinh desired state |
| Leaver IdP login bị DENY | Không kết luận successful compromise |
| Leaver SaaS local login SUCCESS sau cutoff | High priority, xác minh mapping |
| Leaver old access token có API PERMIT | Residual data-plane access |
| Leaver SCIM PATCH 204 | Chỉ ACK, không auto verified |
| Leaver target readback timeout | UNKNOWN, không PASS |
| Rehire với identity incarnation mới | Không gộp sai với Leaver trước |
| Guest sponsor/contract expired | Check guest source/target sessions |
| Role admin thêm có approved JIT window | Kiểm proof, không gắn nhầm compromise |
| Role admin thêm thiếu approval field | Lookup registry trước kết luận |
| Actor tự request/approve trái SoD policy | Detection violation có evidence |
| Direct grant nằm ngoài IdP group | Identity graph phát hiện |
| Nested group cấp quyền gián tiếp | Phân tích effective access |
| ABAC department stale sau Mover | Freshness/authorization signal |
| Sensitive OAuth consent mới | Check actor, scopes và owner |
| MFA reset trước privileged login | Correlate chuỗi events |
| RP session còn sau IdP disable | Monitor session/resource path |
| Old token còn hạn nhưng AS đã revoke refresh | Phân biệt token lifecycle |
| Service principal không có owner | Review catalog và risk |
| Service token từ runtime mới có approved migration | Context giảm false positive |
| Workload issuer/subject không thuộc trust | High risk trust violation |
| Dev principal có production-admin | Cross-environment alert |
| Old credential vẫn usable sau rotation cutoff | Credential residual alert |
| Service retired vẫn xin token mới | Post-retirement anomaly |
| SCIM connector thay hàng trăm group không có HRIS event | Mass-change case |
| Review decision REVOKE, grant vẫn active | Remediation detection sau SLO |
| Một resource PERMIT sau revoke | Không tự suy mọi resources còn mở |
| Một endpoint DENY | Không tự suy mọi quyền đã hết |
| Approved exception còn hạn đúng scope | Điều chỉnh severity/handling |
| Exception hết hạn, quyền còn | Alert/escalation |
| Email giống nhau ở hai issuers | Không merge principals |
| Source X-Forwarded-For không tin cậy | Không dùng làm authoritative IP |
| Log thiếu principal mapping | NEEDS_ENRICHMENT, không safe |
| Log source outage | Source health alert |
| Event duplicate retry | Không nhân số findings |
| Events đến không theo thứ tự | Temporal correlation/version guard |
| Rule critical bị disable ngoài change window | Detection governance alert |
| Case chứa raw session token | Test fail về data protection |
| Analyst reclassifies false positive | Có evidence, suppression scoped |
| Auto-block break-glass trong outage | Test safeguards và escalation |
| Automated revoke ACK nhưng target vẫn active | Case PARTIAL, chưa VERIFIED |
| Tenant A đọc case của tenant B | Authorization DENY |
| Historical report as-of T | Không dùng future events để làm sai bối cảnh |

### 28.1. Test theo hai lớp

- **Logic layer:** Rule có phát hiện đúng khi data đã chuẩn hóa?
- **End-to-end layer:** Event nguồn có đi qua ingestion, identity resolution, detection, case, response và target verification không?

Một rule logic hoàn hảo vẫn vô dụng khi source IdP/SaaS mất logs.

### 28.2. Negative cases quan trọng

Test cả các hành vi hợp lệ dễ gây nhầm: approved travel, new device, JIT admin, Mover có overlap, service deployment migration và data-plane action có baseline grant hợp lệ.

### 28.3. Không thử nghiệm gây hại trên production

Dùng test accounts, fake records, replay fixtures có kiểm soát và sandbox/mock target. Không cần thử tạo privileged key trái phép hoặc phá session của user thật để đánh giá detection.

## 29. Những hiểu lầm thường gặp trong Identity detection

**“Identity detection chỉ là xem failed logins.”** Không. Nhiều rủi ro nằm ở role grants, sessions, API keys, workloads, direct ACL và vòng đời tài khoản.

**“Bất thường là bằng chứng có attacker.”** Anomaly là dấu hiệu cần xác minh; compromise đòi bằng chứng phù hợp.

**“IdP đã disable nghĩa mọi ứng dụng đều chặn.”** RP sessions, local logins và access tokens có hành vi riêng; cần target verification.

**“SCIM HTTP 204 là deprovision hoàn tất.”** Response ACK không mặc định gỡ direct role, local session hoặc API key.

**“Không thấy login sau Leaver nghĩa không còn access.”** Old access token/session có thể vẫn tạo resource PERMIT.

**“Một role đã gỡ là user không còn quyền.”** Quyền có thể tới từ group khác, inherited role hoặc direct ACL; phải xem effective access.

**“Role name giống nhau nghĩa cùng quyền.”** Permission mapping và resource scope khác giữa hệ thống/tenant/version.

**“Một email tương ứng một identity duy nhất.”** Email có thể đổi, trùng hoặc tái dùng; cần immutable source/issuer/tenant mapping.

**“Có access review 100% completion thì mọi quyền hợp lệ.”** Review coverage và remediation verification khác quyết định KEEP/REVOKE.

**“Dùng MFA rồi thì token/session không bị chiếm.”** MFA không ngăn tất cả session theft, replay hoặc recovery abuse.

**“Một API request 403 chứng minh toàn bộ target an toàn.”** Chỉ nói endpoint và điều kiện request cụ thể bị từ chối.

**“Token ngắn hạn làm service principal không có standing risk.”** Workload trust và role còn thì có thể xin token mới.

**“Service account phải có lịch làm việc, vị trí địa lý như người.”** Dùng runtime/issuer/subject/audience/deployment context cho NHI.

**“Owner nghỉ thì phải disable tất cả workload họ tạo.”** Cần xét service business lifecycle và bàn giao; thu hồi quyền human riêng.

**“Không có owner field tức chắc chắn service không có owner.”** Có thể là inventory sync gap; xác minh trước.

**“Không tìm thấy approvalRef trong event nghĩa không có approval.”** Cần đối chiếu authoritative registry, time/tenant và errors.

**“Risk score cao chắc chắn là compromise.”** Score phụ thuộc model, data quality và confidence; cần triage.

**“Một trusted network có thể bỏ qua mọi policy violation.”** Trusted network không triệt tiêu expired grant hoặc verified Leaver access.

**“Tự động block càng nhiều càng an toàn.”** False positive có thể cắt SCIM connector hoặc break-glass, gây outage.

**“Tăng threshold để giảm alerts là tối ưu.”** Có thể giảm false positives nhưng tăng false negatives; cần đo quality/coverage.

**“Không có alert nghĩa identity posture tốt.”** Có thể mất telemetry, detector disabled hoặc thiếu asset inventory.

**“Sau khi reviewer bấm Done, finding đã được sửa.”** Cần kiểm tra target state, evidence và root cause.

**“Một rule duy nhất đủ phát hiện mọi identity threat.”** Cần policy checks, statistical signals, graph, temporal reconciliation và response.

**“Dữ liệu càng chi tiết, có raw token càng tiện điều tra.”** Raw credentials trong logs tạo một bề mặt rủi ro mới; dùng metadata và references.

**“Đổi status Leaver thành ACTIVE bằng event đến muộn là bình thường.”** Cần versioning và policy về rehire/incarnation, tránh regrant từ Mover cũ.

## 30. Bài tập tình huống có hướng phân tích

### Bài tập A — Nhân viên Mover còn role Finance

Nhân viên U chuyển sang Operations, được cấp Operations viewer nhưng Finance approver vẫn active sau cutoff.

**Câu hỏi:** Đây là login anomaly hay entitlement anomaly? Cần evidence nào?

**Hướng phân tích:** Đây chủ yếu là **stale authorization/privilege accumulation**. Cần HRIS effectiveAt, desired grants, approval ngoại lệ, target role readback, effective access và session cache. Action là revoke role cũ và sửa quy trình Mover.

### Bài tập B — API token cũ vẫn được dùng sau Leaver

IdP user disabled, không có sign-in mới, nhưng data plane ghi API PERMIT bằng token phát trước Leaver.

**Hướng phân tích:** Đường token/session còn hiệu lực, không phải interactive login mới. Kiểm token issuer/audience/resource, policy cutoff và provider revocation; containment và readback theo access path, đánh giá deprovision finding.

### Bài tập C — Service principal sinh token từ region mới

Một workload đã được chuyển cloud region theo change ticket, token issuance từ egress IP mới.

**Hướng phân tích:** Dùng approved deployment, trusted issuer/subject/audience và runtime inventory; không coi hai cloud regions là impossible travel của con người. Vẫn kiểm role scope và trust.

### Bài tập D — Group được gỡ nhưng direct ACL vẫn cho đọc

SCIM gỡ Finance group; resource API vẫn cho report.read qua direct ACL đã được cấp cho người đó.

**Hướng phân tích:** Nếu mục tiêu chỉ gỡ group, có thể group revoke đã verified; nếu policy yêu cầu không còn report.read, direct ACL là residual path. Detection phải căn cứ desired state, không chỉ API outcome đơn lẻ.

### Bài tập E — Role admin thêm bởi automation không có approvalRef

Connector ghi ROLE_GRANT với approvalRef=null, nhưng access request system có một approval hợp lệ khác ID.

**Hướng phân tích:** Cần correlation/mapping theo operationId, principal, role, resource và thời điểm. Có thể là telemetry gap. Không kết luận malicious grant trước khi tra authority và exception.

### Bài tập F — Reviewer 100% KEEP nhưng quyền mồ côi

Campaign đạt 100% decisions, nhưng 20 service principals không nằm inventory và ba owners đã Leaver.

**Hướng phân tích:** Đây là review **coverage/ownership finding**, không phải bằng chứng mọi granted roles hợp lệ. Sửa inventory, reassignment và retest.

### Bài tập G — Leaver event đến muộn

HRIS gửi Leaver effectiveAt 17:00, IAM nhận 17:08, ứng dụng có API PERMIT 17:03.

**Hướng phân tích:** Quyền tồn dư trong khoảng theo cutoff; tách source lag, IAM processing lag, target enforcement lag. Không đổi effectiveAt thành lúc event được ingest để cải thiện báo cáo.

### Bài tập H — Detector mới không có alerts

Từ sau lần deploy, dashboard hiển thị không có privileged grants bất thường nhưng cloud IAM collector đã ngừng gửi events.

**Hướng phân tích:** Cần source heartbeat, pipeline lag và synthetic safe events; không kết luận posture đã an toàn.

### Bài tập I — Một privileged grant tái xuất hiện sau revoke

IAM đã gỡ admin role và readback absent. Sau vài phút, role trở lại vì retry của một event provisioning cũ.

**Hướng phân tích:** Detection regrant-after-revoke, kiểm sourceVersion/causation, target readback và event ordering. Sửa orchestrator và tạo remediation case; tránh xóa log failed attempts.

### Bài tập J — Analyst thêm allowlist vĩnh viễn

Một admin đi công tác, bị báo geo anomaly; analyst allowlist mọi lần login của admin đó vô thời hạn.

**Hướng phân tích:** Suppression quá rộng làm mất các tín hiệu tương lai. Chỉ suppress use case/scope/time cụ thể có approval; vẫn giữ monitoring MFA, privilege change và token usage.

### Bài tập K — Break-glass đang dùng hợp lệ

Trong outage, account khẩn cấp được kích hoạt theo incident reference. Rule “first privileged login in 90 days” báo Critical.

**Hướng phân tích:** Alert có thể đúng về rarity nhưng activity có approval. Triage với PAM/incident evidence; không auto disable break-glass thiếu safeguards, vẫn audit actions và post-incident revoke.

### Bài tập L — Một account xuất hiện ở hai tenants

Hai người cùng có email alias trùng nhưng thuộc các IdP issuers/tenants khác nhau. SIEM gộp events và báo impossible travel.

**Hướng phân tích:** Identity resolution sai. Dùng issuer+subject+tenant/target IDs, giữ mapping provenance, kiểm cảnh báo bị ảnh hưởng và bổ sung regression test.

## 31. Checklist thiết kế và vận hành Identity detection

1. **Purpose:** chương trình phát hiện threat/control nào, có owner và scope?
2. **Universe:** con người, guest, contractor, service identities được bao phủ?
3. **Sources:** HRIS, IdP, SSO/RP, SCIM, IGA, PAM, cloud, SaaS, API logs đủ?
4. **Producer trust:** events, hooks, token metadata được xác thực?
5. **Schema:** principal, tenant, eventTime, action/outcome và policyVersion rõ?
6. **Mapping:** immutable subject/issuer/target namespace thay email đơn thuần?
7. **Identity graph:** account–role–credential–session–resource liên kết đủ?
8. **Temporal:** as-of mapping, effectiveAt và lifecycleVersion có lưu?
9. **Dedup:** eventId/operationId/attemptId không bị đếm trùng?
10. **Data quality:** UNKNOWN khác SAFE và NOT_APPLICABLE?
11. **Coverage:** source-to-sink reconciliation/heartbeat/ingest lag có theo dõi?
12. **Asset risk:** tài nguyên/entitlement critical được phân loại?
13. **Joiner:** cấp quyền trước cutoff được phát hiện theo policy?
14. **Mover:** quyền cũ, ABAC attributes và role cache được rà?
15. **Leaver:** IdP disabled có kiểm target residual access?
16. **Guests:** contract/sponsor lifecycle được xử lý?
17. **RBAC:** group, nested roles, direct grants được tính effective?
18. **ABAC:** attribute provenance, freshness và resource context?
19. **SoD:** request/approve/execute conflicts được phát hiện theo policy?
20. **Privileged:** standing admin, JIT, PAM và break-glass có rules riêng?
21. **SSO:** phân biệt IdP session và RP application sessions?
22. **OAuth:** access/refresh/ID tokens và client consent được phân biệt?
23. **MFA:** recovery, factor changes và step-up có correlation?
24. **Login anomaly:** password spray, devices, geo có confidence/context?
25. **NHI:** registry/owner, runtime, issuer/subject/audience và trust được audit?
26. **Credential:** creation, rotation, old-key usage và retire có tracking?
27. **Workload lifecycle:** service retirement không lẫn human owner Leaver?
28. **SCIM connector:** privileged operations có source event/owner?
29. **Access review:** campaign coverage khác decision/remediation status?
30. **Exceptions:** phê duyệt, owner, scope, expiry và controls được quản trị?
31. **Detection types:** policy, anomaly, graph, sequence và reconciliation có phân vai?
32. **Scoring:** confidence, feature dependencies và impact tách biệt?
33. **Hard violations:** không bị low score hoặc trusted IP xóa tín hiệu?
34. **Rule version:** owner, release, tests, rollback và monitoring rule changes?
35. **Correlation:** events nối theo session/request/actor IDs đáng tin?
36. **Late events:** sourceVersion và out-of-order không tái cấp quyền?
37. **Triage:** analyst có case, disposition và evidence references?
38. **User verification:** không yêu cầu password, OTP hay MFA approval?
39. **Response:** containment được duyệt, đúng scope, có rollback?
40. **Target readback:** ACK không thay verified effective access?
41. **Residual windows:** access tokens và local sessions được xét riêng?
42. **False positives:** approved travel, migration và on-call được xem xét?
43. **False negatives:** incident retrospectives giúp tìm missed detections?
44. **NHI safeguards:** không auto-disable production job khi chưa hiểu dependency?
45. **Data minimization:** không log secrets, tokens và PII không cần?
46. **Tenant isolation:** API/case/evidence/export có server-side authorization?
47. **Audit integrity:** append-only, privileged changes và retention controls?
48. **Metrics:** precision/recall chỉ tính trên cohorts có nhãn đáng tin?
49. **SLO:** detection, triage, containment và verification được định nghĩa?
50. **Coverage reporting:** không lấy 0 alerts làm bằng chứng an toàn?
51. **Testing:** positive, negative, partial failure và concurrency được thử?
52. **Incident path:** confirmed compromise có escalation nhanh?
53. **CAPA:** repeated control gap có root cause, owner và retest?
54. **Governance:** tài liệu, policy review và exception expiry được cập nhật?

## 32. Tổng kết

**Identity detection** trong chương **Identity monitoring** là hoạt động **phát hiện những trạng thái, quyền và hành vi bất thường hoặc trái chính sách trên toàn bộ đồ thị danh tính**, không chỉ theo dõi đăng nhập thất bại.

Nó cần kết hợp:

- **Nguồn sự thật về vòng đời:** HRIS, contract, service registry, Joiner–Mover–Leaver, effectiveAt.
- **Identity graph:** human/NHI principal, account, credential, session/token, role, resource, owner.
- **Telemetry đa lớp:** IdP/SSO/OIDC/SAML, SCIM/IGA/PAM, cloud IAM, SaaS và resource access.
- **Detection phù hợp:** policy violations, behavioral anomalies, sequence, privilege paths, target reconciliation.
- **Đánh giá có căn cứ:** identity mapping, source provenance, confidence, business impact và approved exceptions.
- **Phản ứng an toàn:** triage, step-up, scoped revoke, containment và kiểm chứng tại target.
- **Audit/learning loop:** outcome, root cause, false positives, telemetry gaps, tests, rule versions và privacy controls.

Đối với IAM theo **Joiner–Mover–Leaver**, mục tiêu cuối cùng là bảo đảm quyền được **cấp đúng lúc, thay đổi đúng phạm vi và thu hồi thực sự khi không còn căn cứ**. IdP disable, SCIM ACK hay một alert đóng ticket không đủ để chứng minh mọi quyền đã chấm dứt. Cần đối chiếu **desired state với observed effective access**, xem xét account/session/token, service principals và các đường grant trực tiếp.

**Ghi nhớ:** **Phát hiện có giá trị không nằm ở số cảnh báo tạo ra, mà ở khả năng chỉ ra đúng danh tính–quyền–tài nguyên bị ảnh hưởng, cung cấp bằng chứng đáng tin, kích hoạt hành động tương xứng và xác minh rủi ro/quyền truy cập tồn dư thực sự đã giảm.**











