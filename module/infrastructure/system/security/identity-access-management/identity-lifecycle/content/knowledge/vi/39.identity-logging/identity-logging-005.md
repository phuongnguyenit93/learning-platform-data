# Deprovisioning log trong IAM: ghi nhận và chứng minh việc thu hồi quyền

> **Chương:** Identity logging  
> **Bài:** Deprovisioning log  
> **Module:** SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE  
> **Ngữ cảnh:** Quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản và cấp quyền đến rà soát, đổi vai trò và thu hồi. Liên kết HRIS, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán để giảm **quyền truy cập tồn dư**.

## 1. Deprovisioning log là gì?

Một nhân viên rời công ty lúc 17:00. Hệ thống nhân sự phát sự kiện Leaver, IAM gửi yêu cầu vô hiệu tài khoản tại IdP và gỡ quyền ở ba ứng dụng SaaS. Portal IAM hiện chữ “Success” lúc 17:01. Nhưng lúc 17:04, một SaaS vẫn cho phép export dữ liệu bằng session trước đó.

Để biết chuyện gì đã xảy ra, phải phân biệt **sự kiện nghiệp vụ**, **quyết định thu hồi**, **lệnh kỹ thuật**, **phản hồi của connector**, **trạng thái thực tế** và **kết quả xác minh**.

**Deprovisioning log** là tập bản ghi có cấu trúc, có thể truy vết và kiểm toán về toàn bộ tiến trình **vô hiệu danh tính/tài khoản, gỡ entitlement, cắt phiên/token/credential và xác minh không còn đường truy cập trái chính sách**.

Log trả lời những câu hỏi:

- **Ai hoặc điều gì** khởi tạo deprovision?
- **Vì sao** phải thu hồi: Leaver, Mover, hợp đồng hết hạn, incident hay access review?
- **Đối tượng nào** cần xử lý: identity, account, role, group membership, local grant, session hay API key?
- **Khi nào** nghiệp vụ yêu cầu ngừng quyền, lệnh được gửi, target đáp ứng và bằng chứng xuất hiện?
- **Hệ thống nào** đã thực thi, hệ thống nào còn pending hoặc lỗi?
- **Quyền nào thực sự đã mất**, quyền nào vẫn tồn tại qua đường cấp khác?
- **Ai chịu trách nhiệm** khắc phục residual access và khi nào có thể đóng workflow?

### 1.1. Log không phải một dòng “User deleted”

Một hành động disable User ở IdP chỉ là một phần. Người dùng có thể vẫn có local SaaS account, direct database grant, OAuth refresh token, API key, share link hoặc phiên SSO/RP còn hiệu lực.

**Không thể suy “đã thu hồi toàn bộ” chỉ vì một API trả HTTP 200/204 hoặc status IAM chuyển sang DONE.** Cần bằng chứng theo từng target và cơ chế truy cập.

### 1.2. Mục tiêu của bài

Sau bài học, người đọc có thể:

1. Thiết kế event log cho deprovisioning theo JML và các nguyên nhân khác.
2. Phân biệt intended state, command result và observed effective access.
3. Correlate các bước giữa HRIS, IAM, IdP, SCIM, SSO, SaaS, PAM và cloud IAM.
4. Xử lý đúng retry, duplicate, out-of-order event, timeout, lỗi một phần.
5. Ghi bằng chứng xác minh và tính thời gian quyền tồn dư mà không thổi phồng mức hoàn tất.
6. Bảo vệ log khỏi sửa/xóa, lộ PII, secret và truy cập trái phép.
7. Xây dashboard, cảnh báo và kiểm thử độ tin cậy của chuỗi sự kiện.

## 2. Deprovisioning khác disable, delete và revoke

| Thao tác | Mục tiêu | Điều chưa thể kết luận |
|---|---|---|
| **Disable identity** | Chặn identity theo authority, ví dụ IdP | Mọi SaaS session đã hết |
| **Disable target account** | Chặn account ở ứng dụng đích | Các API keys/direct grants khác đã hết |
| **Delete account** | Xóa object ở target theo semantics provider | Dữ liệu nghiệp vụ đã được lưu/giữ đúng |
| **Remove group membership** | Gỡ một đường cấp role | Không còn local/direct role hoặc group khác |
| **Revoke entitlement** | Thu hồi permission/grant cụ thể | Phiên/token cũ không còn sử dụng được |
| **Revoke refresh token** | Chặn lấy access token mới theo provider contract | Access token đã phát không còn hạn |
| **Terminate session** | Kết thúc một session cụ thể | Mọi session ở các RP khác cũng chấm dứt |
| **Rotate credential** | Thay key/secret | Principal không còn quyền ở target |
| **Deprovision workflow** | Điều phối các bước theo desired state | Hoàn tất trừ khi được verified |

**Deprovisioning** thường là quá trình gồm nhiều đối tượng và nhiều hệ thống. Quyết định cuối cùng có thể là: disable account, xóa một entitlement, retire một service identity hoặc chuyển owner tài nguyên, tùy chính sách.

### 2.1. Một người có nhiều account

Một identity nhân viên có thể ánh xạ sang user ở IdP, CRM, source control, database và một số local accounts. Mỗi target có **targetAccountId** riêng. Deprovision log cần ghi danh tính nguồn ổn định và mapping đích để không xử lý sai người có cùng email/tên.

### 2.2. Hết một quyền không nhất thiết disable cả tài khoản

Một người Mover khỏi Finance nhưng vẫn thuộc công ty: gỡ finance.export có thể là đủ ở ứng dụng đó; không mặc định disable toàn bộ SSO account. Log phải ghi **subject–action–resource–grant** được thu hồi, không chỉ event “User disabled”.

### 2.3. Không xóa dữ liệu doanh nghiệp tùy tiện

Leaver không phải lệnh xóa invoice, repository hoặc document do người ấy từng tạo. Tài nguyên cần retention, handover và owner mới. Deprovision log phải tách **access removal** với **business data preservation**.

## 3. Bốn lớp sự thật cần tách trong log

Một thiết kế đáng tin phải theo dõi các lớp khác nhau:

1. **Business event:** điều gì khiến quyền phải thay đổi? Ví dụ HRIS Leaver effectiveAt=17:00.
2. **Desired state:** IAM xác định account/grant/session nào phải bị disable/revoke.
3. **Command/ack:** connector gửi request và nhận kết quả giao thức từ target.
4. **Observed/effective state:** target readback hoặc kiểm chứng chứng minh quyền cần gỡ đã bị chặn.

Ví dụ:

~~~text
17:00:00   HRIS: Leaver có hiệu lực
17:00:01   IAM: TARGET_DESIRED=DISABLED
17:00:02   Connector: PATCH gửi đến SaaS
17:00:03   SaaS: HTTP 204
17:00:04   IAM: đọc lại account, thấy active=false
17:02:00   Audit: session SaaS cũ vẫn thực hiện export
17:04:00   SaaS: session thực sự bị chặn
17:05:00   IAM: xác minh không còn đường quyền theo phạm vi
~~~

Nếu gọi kết quả 17:00:03 là “toàn bộ truy cập đã hết”, doanh nghiệp đã **đánh đồng ACK với enforcement**.

### 3.1. Log sự kiện khác log trạng thái tổng hợp

Event log phản ánh các lần chuyển trạng thái và bằng chứng; dashboard thường hiển thị trạng thái hiện tại được **suy ra từ chuỗi event**. Không nên overwrite history bằng một dòng status mới mà không biết nguyên nhân, thời điểm và attempt nào tạo kết quả.

### 3.2. Command success không phải business success

HTTP 2xx có thể chỉ nghĩa request hợp lệ/đã nhận; còn quyền chưa đồng bộ qua SaaS hoặc target session. Ngược lại, một retry nhận “member not found” có thể phù hợp với trạng thái mong muốn sau khi thao tác đầu đã thành công, nhưng chỉ được coi idempotent success khi **target identity và trạng thái thực tế được kiểm chứng**.

### 3.3. Một access path bị xóa, path khác có thể còn

Gỡ membership group A không làm user mất resource.read nếu direct ACL B vẫn hợp lệ. Deprovision log phải đánh giá expected effective access: quyền đang cần thu hồi được đóng hay vẫn tồn tại qua cấp quyền khác, và quyền khác hợp lệ nào phải được giữ.

## 4. Kiến trúc phát sinh, thu thập và kiểm chứng log

~~~mermaid
flowchart TD
    HR[HRIS / Contract / Ticket / Incident] --> ORCH[IAM / IGA Deprovision Orchestrator]
    ORCH --> PLAN[Desired-state Plan + Audit Events]
    PLAN --> IDP[IdP / SSO / Directory]
    PLAN --> SCIM[SCIM / SaaS Connectors]
    PLAN --> CLOUD[Cloud IAM / DB / PAM / API]
    IDP --> RESULT[Operation Results]
    SCIM --> RESULT
    CLOUD --> RESULT
    RESULT --> RECON[Target Readback / Reconciliation]
    RECON --> EVID[Evidence Store]
    PLAN --> PIPE[Central Log Pipeline]
    RESULT --> PIPE
    EVID --> PIPE
    PIPE --> SIEM[SIEM / Detection / Dashboard]
    SIEM --> ALERT[Incident / Escalation]
    RECON --> CLOSE{All required access paths verified?}
    CLOSE -- Có --> DONE[VERIFIED_CLOSED]
    CLOSE -- Chưa --> PARTIAL[PARTIAL / RETRY / CONTAIN]
~~~

### 4.1. Business source và IAM orchestrator

HRIS, contract system, project assignment hoặc incident tool là nguồn của **nguyên nhân nghiệp vụ**. IAM nhận sự kiện, xác minh tính hợp lệ, tính desired state và phát operations. Không được tin một webhook tự khai employeeStatus=TERMINATED nếu chưa được xác thực theo contract/issuer.

### 4.2. Connector logs

Connector ghi mọi attempt: request ID, target, operation type, start/end time, response class, retryability và lỗi đã chuẩn hóa. Không log raw secret, bearer token hoặc toàn bộ payload nhạy cảm.

### 4.3. Target logs

IdP, SaaS, database và cloud IAM có thể có log riêng về account disabled, role removed, session terminated hoặc resource authorization. Dùng chúng làm **bằng chứng bổ sung**; không mặc định target audit logs có đủ độ chi tiết hoặc thời gian thực.

### 4.4. Evidence và audit chain

Khi readback, cần biết ai kiểm tra, kiểm tra ID/grant nào, thời điểm observedAt và trạng thái gì. Một dòng “verified=true” không có evidence reference hoặc rule cụ thể sẽ rất khó kiểm toán.

### 4.5. SIEM không phải enforcement engine

SIEM hỗ trợ thu thập, correlation và cảnh báo, nhưng thường **không trực tiếp chặn quyền**. Việc revoke phải được thực thi ở IdP, target, resource server, PAM hoặc policy enforcement point tương ứng.

## 5. Event model: một workflow, nhiều target, nhiều attempts

Một identity Leaver có thể liên quan 8 hệ thống; trong mỗi target có nhiều operation, và mỗi operation có thể retry.

Mô hình khái niệm:

~~~text
Workflow
  workflowId / correlationId
  sourceEventId
  subjectId, lifecycleVersion, effectiveAt
  reason, policyVersion
  targetPlans[]
    targetSystemId, tenantId, targetAccountId
    desiredState
    grantIds / sessionIds / credentialRefs (tham chiếu an toàn)
    operations[]
      operationId
      attemptId
      requestAt / responseAt
      resultClass / retryability
    evidence[]
      evidenceId, observedAt, verificationMethod, outcome
~~~

### 5.1. Workflow ID

Gom toàn bộ các bước do cùng một yêu cầu deprovision. Một workflow có thể sinh nhiều target plans và operations.

### 5.2. Source event ID và causation ID

- **sourceEventId:** ID bất biến của sự kiện HRIS/ticket/incident.
- **causationId:** event/request đã khiến event hiện tại được sinh ra.
- **correlationId:** ID để nối các event cùng hành trình nghiệp vụ.
- **operationId:** thao tác đích được mong muốn.
- **attemptId:** từng lần gửi/retry cụ thể.

Không dùng một ID duy nhất cho tất cả, vì retry có thể tạo nhiều attempts cho **cùng một operation**, còn cùng workflow có nhiều operations.

### 5.3. Stable subject ID

Lưu immutable subject ID và target account ID ở namespace cụ thể. Email, displayName và username có thể đổi hoặc tái cấp, nên chỉ là thuộc tính hỗ trợ tìm kiếm, không phải khóa duy nhất để thu hồi.

### 5.4. Grant ID và resource scope

Khi gỡ Finance group, phải ghi chính xác membership/entitlement và resource/tenant. Không chỉ lưu “role removed” mà thiếu identity, scope và grant source: điều đó khiến kết quả không thể tái hiện.

## 6. Trạng thái deprovisioning và tiêu chuẩn hoàn tất

Đề xuất một state model để diễn giải nhật ký. Tên trạng thái là ví dụ, không phải enum chuẩn của mọi hệ IAM.

| Trạng thái | Ý nghĩa | Chưa có nghĩa |
|---|---|---|
| **RECEIVED** | Đã nhận source event | Sự kiện đã xác thực/hợp lệ |
| **VALIDATED** | Source, identity, policy hợp lệ | Target đã được xử lý |
| **PLANNED** | Có desired-state operations | Lệnh đã chạy |
| **DISPATCHED** | Đã gửi command | Target đã áp dụng |
| **ACKNOWLEDGED** | Target phản hồi nhận/thực hiện operation | Mọi đường quyền bị chặn |
| **VERIFYING** | Đang kiểm tra actual state | Có bằng chứng đủ |
| **VERIFIED_REVOKED** | Đã xác minh đúng grant/access path | Toàn workflow đã đóng |
| **VERIFIED_CLOSED** | Tất cả yêu cầu thuộc phạm vi đã đạt | Quyền khác của user cũng bị xóa |
| **RETRY_PENDING** | Có lỗi tạm, chờ retry | Đã thất bại vĩnh viễn |
| **PARTIAL** | Một số target/grants còn open hoặc chưa đủ evidence | Có thể tuyên bố complete |
| **FAILED** | Operation lỗi cần xử lý | Các bước khác cũng thất bại |
| **ESCALATED** | Đã gán owner để khắc phục/risk decision | Quyền tự mất |
| **EXCEPTION_APPROVED** | Có ngoại lệ policy được phê duyệt | Residual access không còn rủi ro |

### 6.1. Workflow-level và target-level status

Một workflow 10 target với 9 target verified, 1 target unreachable phải là **PARTIAL**, không phải VERIFIED_CLOSED. Dashboard cần hiển thị cả tiến độ tổng và **tên target chưa xử lý**.

### 6.2. Command vs observed state

Nếu operation remove group trả ACK, nên ghi ACKNOWLEDGED rồi VERIFYING. Chỉ sau readback chứng minh membership bị xóa và effective access theo yêu cầu mới đánh dấu VERIFIED_REVOKED.

### 6.3. Exception không được dùng để che quyền tồn dư

Có thể có ngoại lệ giữ quyền để phục vụ điều tra/continuity, nhưng phải ghi approval authority, lý do, scope, thời hạn, compensating controls, owner và ngày rà soát. Không “sửa log” thành VERIFIED chỉ để tổng hợp campaign 100%.

## 7. Những timestamp không được đánh đồng

| Trường | Ý nghĩa |
|---|---|
| **eventCreatedAt** | Source tạo event |
| **effectiveAt** | Thời điểm quyền phải mất hiệu lực theo nghiệp vụ |
| **receivedAt** | IAM nhận event |
| **validatedAt** | Xác minh source/policy/identity |
| **plannedAt** | Tính desired state |
| **dispatchedAt** | Gửi command tới connector/target |
| **respondedAt** | Nhận phản hồi từ target |
| **targetObservedAt** | Readback quan sát actual state |
| **enforcedAt** | Target bắt đầu chặn quyền, nếu có bằng chứng xác định được |
| **verifiedAt** | IAM kết luận bằng chứng thu hồi đạt yêu cầu |
| **closedAt** | Đóng workflow sau khi xử lý mọi path |
| **ingestedAt** | Pipeline log nhận bản ghi |
| **sourceVersion** | Version thứ tự sự kiện từ nguồn có thẩm quyền |

### 7.1. Timestamp sự kiện vs thời điểm nhận log

Một log target tạo lúc 17:02 nhưng SIEM ingest lúc 17:10. Không tự coi target mới thu hồi ở 17:10; cũng không sử dụng timestamp do client tự khai để chứng minh đã thu hồi sớm hơn.

### 7.2. EnforcedAt có thể không đo chính xác

Nếu chỉ biết API còn cho phép lúc 17:01 và đã từ chối lúc 17:05, thời điểm enforce thực tế nằm trong khoảng quan sát. Có thể ghi **observedRevokedAt=17:05** và phân biệt với exactEnforcedAt không biết, thay vì tự gán 17:05 là thời điểm chính xác.

### 7.3. Thời gian UTC và múi giờ nghiệp vụ

Lưu event instants ở UTC (ví dụ định dạng ISO 8601 với Z) và giữ timezone/cơ sở tính ngày của nghiệp vụ khi cần. Deadline “17:00 giờ địa phương” phải được chuyển thành instant đúng trước khi so sánh; không cộng trừ mơ hồ giữa máy chủ khác timezone.

### 7.4. Đồng bộ đồng hồ

IdP, IAM, target, gateway, Redis và SIEM cần đồng hồ ổn định và độ lệch được giám sát. Clock drift làm sai thứ tự/audit/SLA. Dùng event sequencing/source version khi timestamp không đủ để xác định nhân quả.

## 8. Một bản ghi deprovisioning log cần gì?

Các nhóm trường nên được thiết kế cùng privacy và audit policies:

| Nhóm | Trường hữu ích |
|---|---|
| **Event** | eventId, eventType, schemaVersion, emittedAt |
| **Correlation** | workflowId, correlationId, causationId, sourceEventId |
| **Identity** | subjectId, subjectType, targetAccountId, identitySource |
| **Tenant/resource** | tenantId, targetSystemId, resourceId, entitlementId |
| **Trigger** | triggerType, reasonCode, effectiveAt, sourceVersion |
| **Authorization** | requestedBy/initiatedBy, approvedBy, approvalRef, policyVersion |
| **Operation** | operationId, action, desiredState, attemptId, idempotencyKey |
| **Command result** | requestAt, responseAt, HTTP status, targetErrorCode, retryable |
| **Observed state** | targetObservedAt, observedState, verificationMethod, evidenceRef |
| **Workflow state** | status, owner, nextAction, nextRetryAt, escalationRef |
| **Security** | integrity metadata, actor/producer trust, log redaction class |
| **Audit context** | resultReason, ticketId, source/target correlation IDs |

### 8.1. Actor không chỉ là username

Deprovision có thể do HRIS event tự động, IAM service principal thực thi, manager approve và target connector gửi lệnh. Log nên phân biệt:

- **Business initiator:** nguồn/actor tạo lý do.
- **Decision authority:** người/policy có thẩm quyền.
- **Technical executor:** workload hoặc connector gửi operation.
- **Verifier:** hệ thống/người xác minh kết quả.

Không gộp mọi hành động dưới “admin” hoặc “system” vì sẽ mất trách nhiệm và khả năng điều tra.

### 8.2. Không log secret hay token

Không lưu password, API secret, refresh/access token, raw session cookie, private key, recovery codes hoặc toàn bộ Authorization header. Nếu cần bằng chứng credential đã revoke, lưu **credential ID/reference và trạng thái**, không lưu giá trị bí mật.

### 8.3. Privacy by design

Danh sách nhân sự nghỉ việc và quyền nhạy cảm có thể là dữ liệu cá nhân/bảo mật tổ chức. Cần phân quyền xem log, tối thiểu hóa PII, retention phù hợp và cơ chế xử lý dữ liệu theo chính sách/pháp luật áp dụng.

### 8.4. Schema version

Event schema sẽ tiến hóa. Mỗi bản ghi nên có schemaVersion để parser/SIEM hiểu đúng sự khác biệt giữa các phiên bản; không tự diễn giải các trường thiếu là success.

## 9. Ví dụ JSON: log workflow và bằng chứng target

### 9.1. Event Leaver được chấp nhận

Đây là một schema minh họa, không phải tiêu chuẩn bắt buộc của SCIM, IdP hay SIEM.

~~~json
{
  "eventId": "evt-leaver-20261123-001",
  "eventType": "DEPROVISION_PLAN_CREATED",
  "schemaVersion": "1.0",
  "workflowId": "deprov-wf-2841",
  "sourceEventId": "hris-leaver-118",
  "correlationId": "jml-employee-1042-2841",
  "subject": {
    "subjectId": "employee-1042",
    "subjectType": "HUMAN",
    "identitySource": "hris"
  },
  "trigger": {
    "type": "LEAVER",
    "reasonCode": "EMPLOYMENT_ENDED",
    "sourceVersion": 108,
    "effectiveAt": "2026-11-23T10:00:00Z"
  },
  "authorization": {
    "policyVersion": "jml-deprovision-v7",
    "initiator": "hris-connector",
    "decisionAuthority": "approved-leaver-policy"
  },
  "desiredState": "NO_ACCESS",
  "targetsPlanned": [
    "idp-tenant-a",
    "finance-saas-tenant-a",
    "source-control-org-a"
  ],
  "status": "PLANNED",
  "emittedAt": "2026-11-23T10:00:01Z"
}
~~~

Các ID và tên trong JSON đều giả lập. Không lưu tên, email, hợp đồng hay nội dung nhân sự vượt nhu cầu kiểm toán trong event nếu immutable ID và nguồn tham chiếu đã đủ.

### 9.2. Event gửi và nhận command tại một target

~~~json
{
  "eventId": "evt-scim-attempt-002",
  "eventType": "DEPROVISION_COMMAND_RESULT",
  "schemaVersion": "1.0",
  "workflowId": "deprov-wf-2841",
  "operationId": "op-finance-disable-01",
  "attemptId": "op-finance-disable-01-attempt-1",
  "correlationId": "jml-employee-1042-2841",
  "causationId": "evt-leaver-20261123-001",
  "target": {
    "systemId": "finance-saas",
    "tenantId": "tenant-a",
    "targetAccountId": "saas-user-987"
  },
  "executor": "scim-provisioning-connector",
  "operation": "DISABLE_USER",
  "desiredState": "DISABLED",
  "dispatchedAt": "2026-11-23T10:00:04Z",
  "respondedAt": "2026-11-23T10:00:05Z",
  "transport": {
    "protocol": "HTTPS",
    "httpStatus": 204
  },
  "resultClass": "ACKNOWLEDGED",
  "verificationStatus": "PENDING",
  "retryable": false,
  "policyVersion": "jml-deprovision-v7"
}
~~~

HTTP 204 ở ví dụ thể hiện response theo một giao thức. Nó **không tự chứng minh mọi session, local role hoặc API key đã bị chặn**.

### 9.3. Event readback và xác minh

~~~json
{
  "eventId": "evt-finance-readback-003",
  "eventType": "DEPROVISION_VERIFICATION",
  "schemaVersion": "1.0",
  "workflowId": "deprov-wf-2841",
  "operationId": "op-finance-disable-01",
  "correlationId": "jml-employee-1042-2841",
  "target": {
    "systemId": "finance-saas",
    "tenantId": "tenant-a",
    "targetAccountId": "saas-user-987"
  },
  "observedState": {
    "accountActive": false,
    "managedGroupGrantsPresent": false,
    "localSessionsStillActive": "UNKNOWN"
  },
  "verification": {
    "method": "TARGET_READBACK",
    "observedAt": "2026-11-23T10:00:08Z",
    "evidenceRef": "evidence/finance-check-003",
    "scope": ["account", "managed-groups"],
    "outcome": "PARTIAL"
  },
  "nextAction": "CHECK_SESSION_TERMINATION",
  "owner": "finance-saas-owner"
}
~~~

Readback chứng minh **account và managed groups đã đạt trạng thái mong muốn** trong phạm vi quan sát; session vẫn UNKNOWN. Chưa được chuyển toàn target hay workflow thành VERIFIED_CLOSED.

### 9.4. Event final closure

Chỉ phát sự kiện đóng khi các **access paths trong phạm vi** đã verified hoặc được xử lý theo exception hợp lệ, có trace:

~~~json
{
  "eventId": "evt-deprov-final-010",
  "eventType": "DEPROVISION_WORKFLOW_CLOSED",
  "workflowId": "deprov-wf-2841",
  "correlationId": "jml-employee-1042-2841",
  "status": "VERIFIED_CLOSED",
  "verifiedTargets": 3,
  "requiredTargets": 3,
  "verificationSummaryRef": "evidence/deprov-wf-2841-summary",
  "closedAt": "2026-11-23T10:04:30Z",
  "policyVersion": "jml-deprovision-v7"
}
~~~

Nếu một target còn UNKNOWN hoặc PARTIAL, event cuối **không được** gắn status VERIFIED_CLOSED theo tiêu chí nêu trên.

## 10. Deprovisioning log trong SCIM provisioning

SCIM thường dùng để quản lý tài nguyên User/Group và group membership. Nó là một công cụ hữu ích trong JML, nhưng không định nghĩa một thao tác chuẩn duy nhất chấm dứt mọi access path của mọi SaaS.

| Trường hợp | Operation có thể dùng | Bằng chứng cần |
|---|---|---|
| Leaver tại SaaS | Cập nhật User.active thành false nếu provider hỗ trợ | Account state và session behavior |
| Mover mất role | Gỡ membership/role tương ứng | Group readback và role mapping |
| Contractor hết hạn | Disable target account và grants theo policy | Target account, token/local grants |
| Dừng access chỉ trên một project | Gỡ group/direct grant scope đó | Project-level effective access |
| Account không còn tồn tại | GET/search/resource lookup | Đúng target account ID và không còn đường quyền |

### 10.1. SCIM User.active=false là trạng thái account, không phải “xóa hết”

Nếu SaaS hỗ trợ active=false, request có thể disable target User. Nhưng **browser session, bearer token hoặc direct grants ngoài SCIM** có thể có hành vi riêng. Phải kiểm tra contract của provider trước khi đánh dấu hoàn tất.

### 10.2. Group membership removal

Một User bị gỡ khỏi Finance group có thể còn quyền thông qua nested group, direct role, object ACL hoặc group khác. Log cần ghi grantSource, entitlementId và resourceScope, rồi xác minh mức quyền có hiệu lực sau thay đổi.

### 10.3. SCIM PATCH/DELETE success khác verification

- HTTP 200/204 có thể cho biết request đã xử lý ở API layer.
- HTTP 202 (nếu endpoint dùng) có thể phản ánh xử lý bất đồng bộ.
- HTTP 404 có thể nghĩa object không tồn tại, nhưng cũng có thể do mapping sai tenant/ID hoặc endpoint không đúng.
- HTTP 409/412 có thể liên quan conflict/version theo contract.
- HTTP 429/5xx thường cần retry/backoff nếu policy cho phép.

**Không tự coi mọi 404 là success**: phải xác định đúng target account và trạng thái thực tế; nếu không, có nguy cơ bỏ sót account vẫn còn tồn tại ở ID khác.

### 10.4. SCIM không thay toàn bộ SSO/API token revocation

SCIM cập nhật User/Group không mặc định chấm dứt IdP session, RP session, access token, refresh token hay credential được tạo qua API khác. Deprovisioning log cần có các event riêng khi policy yêu cầu thu hồi chúng.

### 10.5. SCIM connector là principal đặc quyền

Log cũng phải theo dõi **ai dùng credential của SCIM connector** để disable người khác. Một attacker chiếm connector có thể gây mass-disable hoặc gán group sai. Lưu executor service identity, approval/source event, target IDs và alert khi operation bất thường.

## 11. Phối hợp IdP, SSO, OAuth/OIDC và phiên ứng dụng

Một người dùng có thể đăng nhập qua IdP rồi giữ phiên tại từng RP/SaaS. Deprovision log không nên gộp các cơ chế này.

### 11.1. IdP disable và application session

Vô hiệu identity tại IdP thường chặn một số hoạt động đăng nhập/token issuance tương lai, nhưng không mặc định làm mọi ứng dụng đích từ chối các session đã phát. Log cần phản ánh:

~~~text
IdP identity disabled: VERIFIED
New SSO login denied: VERIFIED
RP session terminated: PENDING
SaaS local session invalidated: UNKNOWN
API access via old token: CHECK_REQUIRED
~~~

Không xuất VERIFIED_CLOSED toàn bộ khi policy yêu cầu ngắt RP sessions mà các bước đó vẫn chưa xác minh.

### 11.2. OAuth access token khác refresh token

- **Access token:** bearer token để gọi resource server; có expiry/profile riêng.
- **Refresh token:** có thể xin access token mới nếu vẫn hợp lệ theo authorization server.
- **ID token:** trong OIDC thường phục vụ xác nhận đăng nhập cho client/RP, không phải vé dùng tùy ý cho API.

Thu hồi refresh token có thể chặn **issuance mới**, nhưng access token tự chứa đã phát có thể còn hợp lệ đến exp nếu resource server không có online status check, denylist hoặc cơ chế revocation thích hợp.

### 11.3. Session/Tokens cần event riêng

Ví dụ các event types có thể là:

~~~text
IDP_ACCOUNT_DISABLED
SSO_SESSION_TERMINATION_REQUESTED
SSO_SESSION_TERMINATED
RP_SESSION_REVOKE_REQUESTED
RP_SESSION_REVOKE_VERIFIED
REFRESH_TOKEN_REVOKED
ACCESS_TOKEN_RESIDUAL_WINDOW_IDENTIFIED
RESOURCE_AUTHORIZATION_DENIED_AFTER_REVOKE
~~~

Không mặc định every vendor hỗ trợ revoke tất cả tokens tức thời. Nếu không thể chứng minh access token đã bị chặn, ghi **risk/exception và deadline** thay vì dấu VERIFIED giả.

### 11.4. SSO session expiry không thay entitlement expiry

Một user có session còn hạn nhưng finance.export đã bị thu hồi do Mover. Resource server vẫn phải thực thi RBAC/ABAC và policy liên quan. Logging nên ghi entitlement revoked và kết quả authorization thực tế khi cần.

## 12. Joiner, Mover và Leaver trong deprovisioning logs

Deprovision không chỉ là nhân viên nghỉ việc. Nó có thể được kích hoạt bởi mọi sự kiện khiến quyền hiện hữu không còn phù hợp.

### 12.1. Joiner: rollback cấp quyền lỗi

Nhân viên mới được provision account vào SaaS, nhưng request bị hủy trước ngày bắt đầu. Nếu policy yêu cầu rollback, log phải ghi rõ **những tài khoản/grants đã tạo**, lý do rollback, operations thu hồi và readback. Không gọi rollback là Leaver của người chưa từng active nếu quy trình cần phân biệt nghiệp vụ.

### 12.2. Mover: gỡ quyền vai trò cũ

Ví dụ nhân viên đổi từ Finance sang Operations:

~~~text
Before:
    finance.report.export: ACTIVE
    finance.invoice.approve: ACTIVE

After:
    finance.report.export: REVOKED
    finance.invoice.approve: REVOKED
    operations.dashboard.view: ACTIVE
~~~

Log phải ghi **thu hồi Finance** và cấp Operations như các operations riêng; không xóa account toàn cục nếu user còn nhiệm vụ hợp lệ.

### 12.3. Leaver: xử lý toàn bộ access paths

Leaver effectiveAt có thể yêu cầu:

1. Disable/chặn login mới tại IdP.
2. Thu hồi sessions và tokens phù hợp.
3. Disable target accounts hoặc gỡ direct entitlements.
4. Xử lý PAM/JIT roles và access activations.
5. Gỡ share links, delegated rights, local user accounts, API keys nếu thuộc scope.
6. Bàn giao owner tài nguyên cần giữ.
7. Readback từng target; phát hiện quyền tồn dư.
8. Báo cáo timeline, residual lag và trạng thái verified/partial.

Deprovisioning log phải giữ dấu vết của **cả các bước thành công lẫn các bước thất bại**.

### 12.4. Contract end và guest/partner

Guest có thể không có record HRIS đầy đủ. Nguồn có thẩm quyền có thể là sponsor, contract/project system hoặc identity governance workflow. Log cần reason, owner, cutoff, app-specific target list và chứng cứ.

### 12.5. Source event đến muộn

Nếu HRIS phát event Leaver effectiveAt 17:00 nhưng IAM nhận lúc 17:08, ghi cả effectiveAt và receivedAt. Độ trễ nguồn/queue là một phần residual exposure, không chuyển cutoff thành 17:08 để báo cáo đẹp hơn.

## 13. Service identities, integration accounts và non-human deprovision

Vòng đời workload có thể khác vòng đời nhân viên.

| Thay đổi | Human identity | Service/integration identity |
|---|---|---|
| Owner đổi team | Gỡ quyền người cũ | Reassign owner/reviewer, kiểm tra grants |
| Owner Leaver | Disable login, revoke personal entitlements | Không xóa service đang phục vụ kinh doanh vô điều kiện |
| Workload retired | Không nhất thiết liên quan HRIS | Revoke trust, role, credential và token issuance |
| Connector ngừng hoạt động | Không xóa user target tùy tiện | Revoke API grants/secret/consent riêng |
| Credential rotated | Người có thể bị rút quyền quản trị vault | Grant của principal không tự mất |

### 13.1. Các event của service identity

~~~text
SERVICE_IDENTITY_RETIRE_REQUESTED
WORKLOAD_TRUST_BINDING_REMOVED
ROLE_ASSIGNMENT_REMOVED
CLIENT_SECRET_REVOKED
CERTIFICATE_REVOKED
TOKEN_ISSUANCE_DISABLED
TARGET_PERMISSION_VERIFIED_ABSENT
SERVICE_IDENTITY_RETIRED
~~~

Log từng loại vì rotate secret không giống revoke role; chặn issuance mới không chứng minh mọi access token cũ đã hết.

### 13.2. Owner Leaver không tự là service Leaver

Khi một kỹ sư nghỉ, backup job production có thể vẫn cần hoạt động. Log phải thể hiện **handover owner**, thu hồi quyền truy cập vault/IAM của người nghỉ, kiểm tra secrets đã từng export và điều chỉnh trust/grants của workload nếu rủi ro yêu cầu.

### 13.3. Quyền phi con người không hiện trong SCIM

Service principals, managed identities, cloud role bindings, certificates và workload federation thường được quản lý qua API riêng; không mặc định SCIM bao quát hết. Inventory và deprovision logs phải có target adapters tương ứng.

### 13.4. Shared integration account

Một technical user phục vụ ba connectors; khi một connector nghỉ, xóa cả account có thể làm hai tích hợp còn lại ngừng. Log cần business dependency, scope từng integration và **thu hồi quyền đúng phạm vi**, hoặc thực hiện dự án tách principal.

## 14. Retry, idempotency và xử lý event sai thứ tự

Hệ thống phân tán không bảo đảm mỗi message được xử lý đúng một lần hoặc theo thứ tự tuyệt đối. Deprovisioning logger phải chịu được retry, duplicate và delayed response mà **không xóa mất nguyên nhân hoặc tái cấp quyền sai**.

### 14.1. Operation ID khác attempt ID

Một operation REMOVE_ROLE có thể retry ba lần:

~~~text
operationId = revoke-finance-role-42
attemptId  = revoke-finance-role-42-attempt-1   -> TIMEOUT
attemptId  = revoke-finance-role-42-attempt-2   -> HTTP 204
attemptId  = revoke-finance-role-42-attempt-3   -> DUPLICATE_SKIPPED

Verified target observation: ROLE_ABSENT
~~~

Metric phải đếm **một operation** và nhiều attempts; không tính ba yêu cầu như ba quyền đã thu hồi.

### 14.2. Idempotency

Retry gỡ grant đã mất thường nên đạt cùng desired state mà không gây lỗi nghiệp vụ nghiêm trọng. Tuy nhiên log vẫn phải lưu attempt và cách xác minh. Không dùng idempotency như lý do tự chuyển những response mơ hồ thành success.

### 14.3. Chống Mover cũ đến sau Leaver

~~~mermaid
sequenceDiagram
    participant HR as HRIS
    participant IAM as IAM Processor
    participant T as Target SaaS
    HR->>IAM: Mover version=108
    HR->>IAM: Leaver version=109
    IAM->>T: Revoke quyền theo Leaver
    T-->>IAM: ACK
    IAM->>T: Readback + Verify
    Note over IAM: Retry Mover v108 đến muộn
    IAM->>IAM: So sánh sourceVersion và desired state
    IAM-->>IAM: SKIP_STALE_EVENT; không tái cấp
~~~

Log phải ghi stale event đã được bỏ qua cùng version và correlation, thay vì chỉ im lặng discard làm khó điều tra.

### 14.4. Race giữa grant và revoke

Một job Joiner/Group sync có thể đang thêm group cùng lúc với Leaver revoke. Cần desired state version, optimistic concurrency hoặc fencing phù hợp. Deprovision logs nên ghi conflict/reconciliation outcomes và cảnh báo nếu target lại xuất hiện quyền đã gỡ.

### 14.5. Timeout là trạng thái UNKNOWN, không chắc thất bại

Connector gửi PATCH, network timeout, nhưng target có thể đã apply. Không lập tức kết luận FAILED hoặc resend theo cách tạo tác dụng phụ không kiểm soát. Check status/readback trước khi retry và dùng idempotent operations khi provider hỗ trợ.

### 14.6. Dead-letter queue

Event không xử lý được sau retry policy có thể vào DLQ; log cần workflowId, operationId, normalized error, retryCount, nextAction, owner và escalation. **DLQ không phải trạng thái hoàn tất**.

## 15. Partial failure và risk-based containment

Một workflow có 8 target; 7 target verified, 1 target vẫn cho phép API call. Ghi tổng workflow **PARTIAL**, nêu target, quyền và risk tier.

### 15.1. Không lấy trung bình để tuyên bố đóng

~~~text
Required targets: 8
Verified targets: 7
Pending critical target: cloud-admin
Target completion: 87.5%
Workflow closure: PARTIAL
~~~

87,5% tiến độ không có nghĩa 87,5% rủi ro đã được loại bỏ: quyền admin còn tồn dư có thể quan trọng hơn các quyền viewer đã thu hồi.

### 15.2. Containment theo mức rủi ro

Nếu target tạm lỗi, có thể dùng biện pháp được phê duyệt như chặn tài khoản tại upstream gateway, revoke session ở lớp khác, hạn chế network path hoặc bật policy deny. Không tuyên bố đó là target revoke nếu chưa readback; log rõ **compensating control**, owner, start/end và hiệu lực được xác minh.

### 15.3. Bằng chứng cho ngoại lệ

Exception record nên có:

- Identity/grant/target cụ thể.
- Lý do tồn dư, mức rủi ro và tác động nghiệp vụ.
- Người chấp thuận có thẩm quyền.
- Giới hạn scope và duration.
- Biện pháp giảm rủi ro tạm thời.
- Deadline sửa và thời điểm review lại.
- Evidence đã chặn đường nguy hiểm nào.

### 15.4. Reopen workflow

Nếu sau VERIFIED_CLOSED, reconciliation phát hiện role tồn dư mới hoặc một grant cũ đã bị tái tạo, không xóa lịch sử closure. Ghi **REOPENED/DRIFT_DETECTED** event với mối liên hệ đến workflow gốc và tạo remediation thích hợp.

## 16. Kiểm chứng quyền đã mất bằng target evidence

**Readback** là kiểm tra trạng thái thực tế từ authority/target. Tùy hệ thống, có thể gồm account status, role bindings, group memberships, token/session state và kiểm thử resource authorization có kiểm soát.

### 16.1. Xác minh theo access path

| Access path | Bằng chứng thường hữu ích |
|---|---|
| IdP login | Identity disabled, new login bị chặn |
| SaaS local account | Target account disabled/deleted theo semantics |
| SCIM group role | Group membership absent, role mapping đúng |
| Direct cloud role | IAM policy/binding readback không còn |
| DB direct grant | Database role/GRANT đã bị gỡ |
| OAuth refresh token | Revocation/status ở AS nếu hỗ trợ |
| OAuth access token | Resource-side expiry/revoke/deny theo profile |
| Browser/RP session | Session store invalidated hoặc API denial |
| PAM/JIT activation | Activation/session ended |
| Service credential | Key/cert/trust binding revoked, issuance disabled |
| Share link/delegation | Share/delegation removed hoặc hạn hiệu lực |
| Derived grants | Secondary principals/keys/roles được rà đúng scope |

### 16.2. Negative test là bằng chứng, không phải trò thử trái phép

Trong môi trường được phép, có thể kiểm tra rằng test principal đã revoke không còn thực hiện action trên test resource. Không dùng tài khoản nhân viên thực hoặc API key production để “thử xem còn quyền không” ngoài phạm vi kiểm thử có phê duyệt.

### 16.3. Một lần HTTP 403 không chứng minh toàn bộ hệ thống

403 trên endpoint A không bảo đảm endpoint B, local login, share link hoặc refresh token đã bị chặn. Verification phải định nghĩa scope, access path, test method và coverage phù hợp risk.

### 16.4. Quyền còn qua grant hợp lệ khác

Nếu user có report.read qua baseline group B vẫn hợp lệ sau khi thu hồi temporary grant A, hành động read có thể tiếp tục được cho phép. Cần biết **mục tiêu revoke là grant A hay toàn bộ khả năng đọc**. Không báo FAIL chỉ vì quyền hợp lệ khác còn; cũng không báo SUCCESS nếu mục tiêu là chặn toàn bộ access nhưng user còn đường khác.

### 16.5. Bằng chứng thiếu là UNKNOWN

Một API readback bị 5xx, timeout hoặc trả danh sách không đầy đủ không chứng minh grant không tồn tại. Ghi UNKNOWN/PENDING_VERIFICATION và kế hoạch retry/escalation, tránh biến “không nhìn thấy” thành “không có”.

## 17. Tính toàn vẹn, chống sửa/xóa và chain of custody

Deprovisioning log có thể là bằng chứng kiểm toán/điều tra. Nếu admin hoặc connector vừa thu hồi quyền vừa có thể xóa log của chính mình mà không có dấu vết, bằng chứng yếu.

### 17.1. Append-only và immutable audit trail

Nên thiết kế luồng ghi **append-only** cho sự kiện quan trọng. Khi một operation thất bại rồi được xử lý thành công, thêm event mới; không sửa dòng lỗi trong lịch sử thành success.

Có thể dùng:

- Audit store có write-once/immutable retention khi nền tảng hỗ trợ.
- Phân tách quyền ghi, đọc, thay retention và xóa.
- Tamper-evident hashing/signing hoặc hash chain được thiết kế đúng.
- Replication sang kho log độc lập với hệ IAM/connector.
- Backup và kiểm tra phục hồi để tránh mất bằng chứng.
- Cảnh báo khi pipeline log ngừng hoặc audit configuration thay đổi.
- Đồng bộ clock, sequence, log provenance và truy vết source.

### 17.2. Tamper-evident khác tamper-proof

Hash, chữ ký số hoặc object lock có thể **giúp phát hiện sửa đổi** và tăng mức bảo đảm, nhưng không tự bảo vệ khỏi mọi thao tác của privileged administrators hoặc compromised signing keys. Thiết kế trust separation, key custody, retention lock, external verification và quyền truy cập mới quyết định hiệu lực.

### 17.3. Event corrections không xóa event gốc

Nếu targetAccountId trong một event bị map sai, phát sự kiện **CORRECTION** có before/after reference và người phê duyệt; không âm thầm overwrite lịch sử. Cần giữ bằng chứng việc phát hiện sai và remediation tương ứng.

### 17.4. Chain of custody cho incident

Khi incident response thu thập logs, cần ghi nguồn, công cụ, thời điểm thu thập, checksum/signature khi phù hợp, người xử lý và mọi lần chuyển giao. Không gửi thẳng access tokens hay thông tin PII không cần thiết vào ticket công khai.

### 17.5. Idempotent writer không được làm mất attempt history

Một operation retry ba lần nên có một operationId và **ba attempt records**; cơ chế dedup có thể tránh ghi cùng eventId trùng nhưng không được làm biến mất các attempts riêng.

## 18. Quyền truy cập log, bảo mật dữ liệu và retention

Log identity có thể cho thấy ai nghỉ việc, ai có quyền sản xuất, hệ thống nhạy cảm nào còn lỗ hổng thu hồi. Do đó chính **log pipeline** cũng phải được bảo vệ theo least privilege.

### 18.1. Data minimization

Không cần ghi tên đầy đủ, số giấy tờ, email cá nhân, token hoặc chi tiết nhân sự khi immutable subjectId và source reference đủ để điều tra có kiểm soát.

Nếu cần liên hệ người thật để xử lý compliance, lưu mapping trong kho có quyền truy cập chặt hơn, không nhân rộng PII vào mọi collector.

### 18.2. Encryption và phân quyền

- Mã hóa khi truyền và khi lưu theo yêu cầu tổ chức.
- RBAC/ABAC: reviewer chỉ xem đối tượng thuộc phạm vi được duyệt.
- Tách tenant: không để dashboard tenant A lộ identity của tenant B.
- Tách quyền vận hành connector khỏi quyền xóa/đổi log retention.
- Audit truy cập log, search/export và thay đổi cấu hình.
- Giới hạn quyền xuất khối lượng lớn dữ liệu identity.
- Bảo vệ evidence references khỏi path traversal hoặc IDOR.

### 18.3. Retention phù hợp, không bịa thời hạn chung

Thời gian giữ logs phụ thuộc luật/quy định áp dụng, chính sách nội bộ, mức rủi ro, loại evidence và legal hold. Không có con số retention duy nhất áp dụng cho mọi IAM.

Khi xóa theo policy, cần xử lý metadata, bản sao, backup và external SIEM phù hợp; không giữ PII vô hạn chỉ vì “audit”.

### 18.4. Khả năng tra cứu và tối thiểu quyền

Một auditor có thể cần đọc evidence và các quyết định; không cần xem raw secret. Một on-call engineer có thể cần xem operation error, nhưng không cần HRIS sensitive reason đầy đủ. Thiết kế view/log projection theo audience.

### 18.5. Masking không làm mất khả năng correlation

Dùng immutable surrogate IDs, correlation IDs và references để vẫn nối được chuỗi sự kiện sau khi loại bỏ PII. Nếu dùng hash định danh người, cần đánh giá nguy cơ re-identification/dictionary attacks và quản trị key/salt.

## 19. Log pipeline: chuẩn hóa và phát hiện mất dữ liệu

Một event deprovision có thể đi qua HRIS, message bus, IAM, connector và SIEM. Logs riêng lẻ thường khác format/time/semantic; ingestion layer cần **canonical event model** và validation.

### 19.1. Event envelope

Nên có những thuộc tính chung:

~~~text
eventId
eventType
schemaVersion
eventTime / ingestedAt
producerId / producerType
trustDomain / tenant
workflowId / correlationId / causationId
subjectId / targetSystemId
operationId / attemptId
status / reason
policyVersion
integrityMetadata
~~~

Các trường chỉ có ý nghĩa nếu producer được xác thực và có rule validation, không chỉ vì JSON có field.

### 19.2. Producer authentication

Một webhook giả từ Internet không được phép tạo log Leaver “đáng tin” khiến IAM thu hồi tài khoản tùy ý. Message producer phải được xác thực, request có anti-replay/idempotency controls và policy quyết định event nguồn nào là authority.

### 19.3. Schema validation

Khi event thiếu subjectId hoặc targetSystemId, không tự hoàn thành workflow. Có thể đưa vào quarantine/dead-letter có lý do, cảnh báo owner và kiểm tra mapping trước khi tiếp tục.

### 19.4. Missing event detection

Nếu IAM có command DISPATCHED nhưng sau một khoảng SLA không có ACK hoặc VERIFICATION, cần alert. Nếu source HRIS có 10 Leaver events nhưng IAM chỉ nhận 9, cần có **source-to-sink reconciliation**; không tin “không có log” nghĩa là không có thay đổi nhân sự.

### 19.5. Duplicate/out-of-order ingestion

SIEM có thể nhận ACK trước PLAN do độ trễ mạng. Correlation bằng workflowId, eventId và sourceVersion để tái hiện causality; không dùng thứ tự ingest để kết luận luôn rằng ACK diễn ra trước lệnh.

### 19.6. Target log không đầy đủ

Một số SaaS không xuất session-level logs hoặc không hỗ trợ native revoke. Ghi rõ **evidence capability và khoảng thiếu**, chuyển sang biện pháp bù trừ/verification phù hợp, không phát minh event từ dữ liệu không tồn tại.

## 20. KPI, SLI/SLO và định nghĩa latency

Có nhiều cách đo tiến độ, nhưng phải ghi rõ **tử số, mẫu số, timestamp và phạm vi**.

| Chỉ số | Định nghĩa gợi ý | Không nên nhầm |
|---|---|---|
| Event processing coverage | Source events được IAM nhận/validate trên số events thuộc scope | Không phải quyền đã thu hồi |
| Plan completeness | Required access paths đã được nhận diện | Không phải target đã áp dụng |
| Command dispatch rate | Operations đã gửi/operations planned | Không phải ACK rate |
| Acknowledgement rate | Operations ACK/operations sent | Không phải verified rate |
| Verified target rate | Target plans đã xác minh/required target plans | Không phải overall workflow closure |
| Verified workflow rate | Workflows hoàn tất mọi path/workflows đến hạn | Không thay risk-tier breakdown |
| Retry/backlog count | Attempts và operations còn mở | Không được cộng mỗi retry thành một grant |
| Partial/unknown rate | Workflows còn thiếu evidence | Không được coi success |
| Time-to-ack | respondedAt − dispatchedAt | Không đo revoke enforcement |
| Time-to-verified | verifiedAt − effectiveAt | Upper bound về mốc xác minh, không luôn exact enforce |
| Residual access observed | Access được cho phép trái policy sau effectiveAt | Cần target access evidence |
| High-risk pending age | Tuổi của quyền đặc biệt chưa đóng | Một quyền admin có thể nghiêm trọng |

### 20.1. Công thức về verification rate

~~~text
Verified Workflow Rate (%) =
    count(workflow đạt VERIFIED_CLOSED trong cohort)
    / count(workflow cần deprovision trong cohort)
    * 100
~~~

Phải định nghĩa cohort (ngày phát sinh hay effectiveAt), cutoff báo cáo, exclusions được chấp thuận và N/A khi mẫu số bằng 0.

### 20.2. Time-to-verified không bằng enforced latency chính xác

Nếu target đã chặn lúc 17:03 nhưng IAM readback xác minh lúc 17:05, **time-to-verified** từ 17:00 là 5 phút. Không khẳng định quyền tồn dư chính xác 5 phút. Nếu có resource-side evidence cho thời điểm chặn, mới có thể đo gần hơn **time-to-enforced**.

### 20.3. Phân tách các thành phần độ trễ

~~~text
Source lag          = receivedAt - effectiveAt
Planning lag        = plannedAt - receivedAt
Dispatch lag        = dispatchedAt - plannedAt
Target ACK lag      = respondedAt - dispatchedAt
Verification lag    = verifiedAt - respondedAt
Total verified lag  = verifiedAt - effectiveAt
~~~

Chú ý trường hợp effectiveAt trong tương lai: lag trước cutoff có thể âm; khi đó metric cần định nghĩa rõ planned/scheduled processing thay vì đánh dấu vi phạm.

### 20.4. SLO theo risk tier

Mục tiêu thu hồi quyền cloud-admin có thể chặt hơn quyền viewer. Không tự áp một con số cố định cho mọi tổ chức; policy owner phải xác định SLO, risk tier, exception path, escalation và điều kiện được tính pass/fail.

### 20.5. Đừng để tỷ lệ cao che lỗi nghiêm trọng

~~~text
99 quyền viewer đã thu hồi và verified
1 quyền organization-admin vẫn ACTIVE
Workflow target progress: 99%
Security objective: CHƯA HOÀN TẤT
~~~

Theo dõi số quyền critical/high còn mở, owner, giờ quá hạn và biện pháp containment ngoài tỷ lệ phần trăm.

### 20.6. Metrics nên đo riêng nguồn JML

Joiner rollback, Mover role cleanup, Leaver full deprovision, access request expiry và incident revoke có phạm vi/SLO khác nhau. Phân nhóm để không lấy thành công của tác vụ đơn giản che khó khăn ở Leaver.

## 21. SQL phân tích Deprovisioning logs

Dữ liệu minh họa dùng PostgreSQL với hai bảng logic:

- **deprov_workflows:** mỗi workflow một hàng tóm tắt theo desired state đã được xác minh từ event log.
- **deprov_targets:** mỗi required target plan một hàng, chứa trạng thái verified/partial và timestamps.

Các bảng này là **read model/materialized projection** từ audit events, không thay immutable log gốc.

### 21.1. Tỷ lệ workflow verified theo reason

~~~sql
SELECT
    reason_code,
    COUNT(*) AS total_workflows,
    COUNT(*) FILTER (
        WHERE status = 'VERIFIED_CLOSED'
    ) AS verified_workflows,
    COUNT(*) FILTER (
        WHERE status IN ('PARTIAL', 'FAILED', 'ESCALATED')
    ) AS unresolved_workflows,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE status = 'VERIFIED_CLOSED'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS verified_pct
FROM deprov_workflows
WHERE effective_at >= :windowStart
  AND effective_at < :windowEnd
  AND tenant_id = :authorizedTenantId
GROUP BY reason_code;
~~~

Truy vấn chỉ đúng nếu read model áp dụng policy exclusions và trạng thái verified nhất quán. Trường tenant lấy từ authorization server-side, không tin query parameter chưa được kiểm tra.

### 21.2. Tìm target chưa xác minh

~~~sql
SELECT
    workflow_id,
    target_system_id,
    target_account_id,
    operation_type,
    status,
    effective_at,
    last_attempt_at,
    next_retry_at,
    escalation_owner
FROM deprov_targets
WHERE status NOT IN ('VERIFIED_REVOKED', 'VERIFIED_CLOSED')
  AND effective_at <= :trustedNow
  AND tenant_id = :authorizedTenantId
ORDER BY risk_rank DESC, effective_at ASC;
~~~

Ở hệ thống thật, danh sách terminal statuses phụ thuộc expected state. Một target xác minh giữ quyền baseline hợp lệ có thể có disposition khác VERIFIED_REVOKED; cần chuẩn hóa policy để không báo sai.

### 21.3. Tính time-to-verified

~~~sql
SELECT
    risk_tier,
    COUNT(*) AS verified_count,
    AVG(
        EXTRACT(EPOCH FROM (verified_at - effective_at))
    ) AS avg_seconds_to_verified,
    MAX(
        EXTRACT(EPOCH FROM (verified_at - effective_at))
    ) AS max_seconds_to_verified
FROM deprov_workflows
WHERE status = 'VERIFIED_CLOSED'
  AND verified_at IS NOT NULL
  AND effective_at <= verified_at
  AND tenant_id = :authorizedTenantId
GROUP BY risk_tier;
~~~

Đây là metric **thời gian đến bằng chứng verified**, không phải thời điểm chính xác target enforced revoke. Các workflow chưa verified phải được báo cùng backlog, tránh survivorship bias.

### 21.4. Phát hiện tiến trình đóng sai

~~~sql
SELECT workflow_id, closed_at, verified_targets, required_targets
FROM deprov_workflows
WHERE status = 'VERIFIED_CLOSED'
  AND verified_targets < required_targets;
~~~

Đây chỉ là một invariant giản lược. Nên còn kiểm tra **mọi required access path** có evidence hợp lệ, không chỉ count target bằng nhau.

### 21.5. Tránh đếm trùng do retry

Không JOIN một workflow trực tiếp với nhiều attempts rồi COUNT(*) để suy số workflow. Chọn unique workflowId/operationId hoặc aggregate per operation trước; attempts là metric riêng.

## 22. Java và pseudocode: logging không đồng nghĩa enforcement

### 22.1. Java: event dữ liệu được chuẩn hóa

~~~java
import java.time.Instant;

record DeprovisionAuditEvent(
        String eventId,
        String workflowId,
        String operationId,
        String subjectId,
        String targetSystemId,
        String eventType,
        String outcome,
        Instant occurredAt,
        String correlationId,
        String policyVersion
) {
    DeprovisionAuditEvent {
        if (eventId == null || workflowId == null
                || subjectId == null || eventType == null
                || occurredAt == null) {
            throw new IllegalArgumentException("Missing audit fields");
        }
    }
}
~~~

Record chỉ định nghĩa cấu trúc tối thiểu; production cần schema validation đầy đủ, event IDs unique, tenant/risk metadata và logging sink an toàn, không chứa raw credentials.

### 22.2. Pseudocode: xử lý command và verification

~~~text
function deprovisionTarget(plan):
    assert plan.sourceEventTrusted
    assert plan.lifecycleVersion >= currentAcceptedVersion
    assert plan.authorizationValid

    operation = getOrCreateIdempotentOperation(
        plan.workflowId, plan.targetId, plan.desiredState
    )
    audit.append(PLANNED, operation)

    try:
        result = targetAdapter.apply(operation)
        audit.append(COMMAND_RESULT, safeSummary(result))

    catch Timeout:
        audit.append(OUTCOME_UNKNOWN, retryContext(operation))
        scheduleReadbackBeforeRetry(operation)
        return PENDING_VERIFICATION

    observation = targetAdapter.readActualState(operation)
    audit.append(VERIFICATION_OBSERVED, safeSummary(observation))

    if observation.isUnavailable:
        assignOwnerAndRetry(operation)
        return PARTIAL

    if not evidencePolicy.satisfied(plan, observation):
        escalateOrRetryWithContainment(operation)
        return PARTIAL

    markTargetVerified(operation, observation.evidenceRef)
    audit.append(TARGET_VERIFIED, referenceOnly(observation))
    return VERIFIED_REVOKED
~~~

Đây là pseudocode định hướng, không bảo đảm atomicity giữa target API và audit sink. Hệ thống thực cần outbox/inbox hoặc các mẫu reliability tương đương, tránh quyền đã thay đổi nhưng log bị mất hoặc log nói thành công khi target chưa apply.

### 22.3. Transactional outbox và mất log

Trong hệ thống phân tán, không thể đơn giản commit đồng thời IAM database và SaaS API bằng một transaction thông thường. Có thể dùng:

1. Ghi desired-state operation và audit/outbox record cùng transaction ở IAM.
2. Worker đọc outbox, gửi command có idempotency/correlation.
3. Ghi attempt result dưới event ID riêng.
4. Reconcile actual target state bất kể response success/timeout.
5. Chỉ khi evidence policy đạt mới đóng target và workflow.
6. Nếu event pipeline lỗi, giữ outbox để retry và cảnh báo.

### 22.4. Không log raw request body

Nếu SCIM PATCH chứa thuộc tính nhân sự, không đưa nguyên payload vào audit stream nếu không cần. Lưu operation type, field names cần kiểm toán, target references và digest/secure evidence reference nếu policy cho phép. Credential trong HTTP Authorization header tuyệt đối không được log.

### 22.5. State transitions phải có phiên bản

Nếu worker A ghi PARTIAL còn worker B ghi VERIFIED_CLOSED dựa trên nguồn cũ, cần optimistic version/compare-and-swap hoặc transaction để ngăn đóng sai. Mọi event vẫn được lưu, còn read model chỉ phản ánh transition hợp lệ.

## 23. SIEM detection và cảnh báo cần hành động

Một số rule có ích:

| Rule | Điều kiện minh họa | Hành động |
|---|---|---|
| **Leaver past cutoff** | effectiveAt đã qua, workflow chưa verified | Escalate owner theo risk/SLO |
| **Critical entitlement remaining** | Cloud/PAM admin còn active sau cutoff | Containment khẩn theo policy |
| **Repeated connector failures** | Retry vượt ngưỡng, same target | Incident/connector health |
| **No verification evidence** | ACK không có readback trong SLO | Trigger readback/alert |
| **Post-deprovision access** | Resource log có PERMIT sau effectiveAt | Điều tra residual access |
| **Stale grant reappeared** | Reconciliation thấy role đã revoke quay lại | Reopen + kiểm tra event ordering |
| **Mass disable anomaly** | Connector disable nhiều principals bất thường | Kiểm tra compromise/change plan |
| **Untrusted event producer** | Leaver event sai signature/issuer | Quarantine và cảnh báo |
| **Audit gap** | Source events > IAM workflows | Pipeline/source reconciliation |
| **Logging config changed** | Retention/ingest bị tắt không phê duyệt | Security alert |
| **Service token after retirement** | Token issuance sau trust revoke deadline | Rà trust/credential còn tồn tại |
| **Cross-tenant operation** | target tenant không khớp plan | Block operation và điều tra |

### 23.1. Alert phải có ngữ cảnh

Một alert hữu ích chứa workflow ID, target, subject reference, risk tier, cutoff, current state, error class, owner, link tới evidence và next action. Không nhúng session IDs hoặc toàn bộ dữ liệu nhân sự.

### 23.2. False positives và quyền hợp lệ khác

Nếu user vẫn có read qua baseline role được phép sau Mover, một resource PERMIT có thể không phải residual grant. Rule cần xác định **action/resource/grant path** thuộc phạm vi phải gỡ; tránh cảnh báo vô căn cứ hoặc bỏ sót đường quyền gián tiếp.

### 23.3. Circuit breaker và containment

Connector lỗi hàng loạt có thể cần pause các operations nguy hiểm, nhưng không được để một hàng đợi Leaver critical không ai xử lý. Alert routing, fallback runbook và owner nên được chuẩn bị trước.

### 23.4. Health của chính log pipeline

Nếu collector ngừng nhận event, dashboard trống có thể trông như “không có deprovision failures”. Cần heartbeat, queue lag, dropped event count, source-to-sink reconciliation và cảnh báo pipeline outage.

## 24. Case study: Leaver, ba target và một session còn sống

### 24.1. Bối cảnh

Nhân viên An rời tổ chức lúc **17:00 ngày 23/11/2026, giờ Việt Nam (UTC+07:00)**. HRIS là nguồn có thẩm quyền, IAM thực hiện workflow cho:

- **IdP:** chặn đăng nhập mới và xử lý IdP session theo policy.
- **Finance SaaS:** disable account, gỡ nhóm, xử lý local session và token nếu được hỗ trợ.
- **Source control:** gỡ organization membership và direct repository grants.

Đây là case study giả lập. Không có tên, account hoặc event thật nào được sử dụng.

### 24.2. Timeline và trạng thái

| Giờ (UTC+07:00) | Hệ thống | Event | Có chứng minh toàn bộ đã hết quyền? |
|---|---|---|---|
| 17:00:00 | HRIS | Leaver effectiveAt | Chưa |
| 17:00:01 | IAM | Source event validated, plan 3 targets | Chưa |
| 17:00:02 | IdP connector | DISABLE dispatched | Chưa |
| 17:00:03 | IdP | ACK, new login disabled | Chưa |
| 17:00:05 | Finance connector | SCIM PATCH active=false, HTTP 204 | Chưa |
| 17:00:08 | Finance SaaS | Account inactive; session status UNKNOWN | Chưa |
| 17:00:12 | Source control | Membership removal ACK | Chưa |
| 17:01:00 | IAM | IdP/SSO evidence verified theo scope | Chưa |
| 17:02:00 | Finance API audit | Phiên cũ vẫn export được | **Chưa; residual access** |
| 17:03:00 | Source control | Role membership absent và verified | Chưa |
| 17:04:00 | Finance | Session terminated, export denied | Chưa tự đủ nếu còn đường khác |
| 17:05:00 | IAM | Target reconciliation đủ scope, workflow closed | **Đủ trong scope đã định** |

### 24.3. Ghi gì khi phát hiện export sau cutoff?

Phát các event liên quan:

~~~text
DEPROVISION_COMMAND_RESULT (Finance: ACKNOWLEDGED)
DEPROVISION_VERIFICATION (Finance account: DISABLED)
RESIDUAL_ACCESS_OBSERVED (Finance export: PERMIT at 17:02)
SESSION_REVOKE_REQUESTED
SESSION_REVOKE_VERIFIED
TARGET_VERIFICATION_COMPLETED
DEPROVISION_WORKFLOW_CLOSED
~~~

RESIDUAL_ACCESS_OBSERVED phải có resource/action, policy, session/grant reference được bảo vệ, time, owner và evidenceRef. Nó quan trọng hơn việc portal chỉ hiển thị finance-account=DISABLED.

### 24.4. Những chỉ số có thể kết luận

- **Time-to-ACK Finance:** từ 17:00:05 dispatch tới response tương ứng; không phải thời gian chặn quyền.
- **Time-to-verified workflow:** 5 phút từ Leaver effectiveAt tới 17:05:00.
- **Residual access được quan sát:** một lệnh export được phép lúc 17:02:00, sau cutoff.
- **Exact enforcement time:** không biết nếu chỉ thấy PERMIT lúc 17:02 và DENY lúc 17:04. Có thể mô tả **enforcement diễn ra trong khoảng quan sát**, không giả định đúng một mốc.
- **Audit gap:** nếu Finance API không có log các requests, sẽ khó khẳng định có hay không residual access.

### 24.5. Nếu tài khoản còn một direct role khác

Ngay cả sau local session revoke, user có thể có direct API grant không đi qua SCIM. Workflow phải giữ PARTIAL khi role đó nằm trong scope cần thu hồi. Bản log cần chỉ rõ access path và target evidence riêng.

### 24.6. Điểm học được

**ACK của connector không thay bằng chứng quyền đã mất.** Một deprovisioning log tốt phải giữ cả nguyên nhân, thời gian thực thi, khoảng quyền tồn dư, các lỗi và lần xác minh cuối; không sửa timeline để che độ trễ.

## 25. Ma trận kiểm thử Deprovisioning log

| Tình huống | Kết quả log/hệ thống kỳ vọng |
|---|---|
| Leaver event hợp lệ từ HRIS | VALIDATED với sourceEventId, effectiveAt |
| Event từ producer chưa xác thực | Quarantine/REJECTED, không tự thu hồi |
| Thiếu subjectId | Validation failure, không coi success |
| Email đổi trước Leaver | Mapping theo immutable ID |
| Hai tenant có cùng local account ID | Target tenant namespace đúng |
| Mover làm mất một role | Log đúng entitlement, không disable toàn account |
| Joiner rollback một grant | Có reason và evidence riêng |
| SCIM 204 sau disable | ACK, chưa auto VERIFIED |
| SCIM 202 xử lý async | PENDING, polling/readback |
| SCIM 404 vì ID sai | Không tự coi verified |
| SCIM 404 vì object đã thực sự absent | Verify mapping/trạng thái trước khi kết luận |
| SCIM timeout sau command | UNKNOWN, readback trước retry |
| HTTP 429 từ SaaS | Retry/backoff, giữ status open |
| HTTP 5xx từ target | PARTIAL/RETRY_PENDING, alert nếu quá hạn |
| Duplicate sourceEventId | Idempotent processing, audit duplicate |
| Retry cùng operation ba lần | Một operation, ba attempts |
| Mover version cũ đến sau Leaver | SKIP_STALE_EVENT, không tái cấp |
| Concurrent Joiner và Leaver | Desired state mới nhất thắng theo policy |
| Tạm mất SIEM | Outbox/buffer retry, phát hiện audit gap |
| Log timestamp target lệch | Đánh dấu clock skew/freshness |
| Target chỉ xác minh account inactive | Session/token vẫn UNKNOWN nếu chưa kiểm |
| IdP disabled, RP session còn | Workflow chưa closed theo session scope |
| Refresh token bị revoke, access token còn | Log các đường riêng và residual window |
| Group gỡ nhưng direct role còn | PARTIAL khi total access phải hết |
| Gỡ grant A, grant B hợp lệ còn | Không xóa nhầm grant B |
| Một target critical chưa verified | Toàn workflow PARTIAL |
| Service owner nghỉ, workload còn cần | Handover và thu hồi human grants, không xóa service |
| Service retired nhưng STS vẫn cấp token | Alert trust/issuance còn mở |
| Target readback trả dữ liệu stale | PENDING, kiểm tra freshness |
| Target không có audit API | Ghi capability gap/compensating evidence |
| Log chứa raw bearer token | Test fail và xử lý lộ dữ liệu |
| Người duyệt tự xóa audit logs | Bị chặn hoặc có tamper alert |
| Exclusion không có approval | Không xóa khỏi denominator |
| Dashboard không có workflows vì pipeline down | Health alert, không báo 100% |
| Report từ snapshot quá khứ | Không dùng events sau as-of |
| Evidence target xác nhận state rồi drift | Reopen workflow và log drift |
| Deprovision đã verified, log correction | Append correction event, không overwrite |
| Actor thuộc tenant A xem log tenant B | Authorization DENY |
| Target retries tạo duplicate operation | Cùng operationId, no double-counting |
| Deadline qua nhưng owner chưa xử lý | Overdue/escalation theo policy |
| Event không có schemaVersion | Quarantine hoặc hỗ trợ rõ version fallback |
| Dispatched nhưng không có ACK sau SLA | Missing-ACK alert |
| ACK rồi không có verification | Missing-evidence alert |
| Một action được phép sau effectiveAt | RESIDUAL_ACCESS_OBSERVED + investigation |

### 25.1. Test không được dựa trên dashboard một mình

Cần đối chiếu audit event log, operation store, target readback và resource access outcome. Một dashboard hiện VERIFIED_CLOSED có thể chỉ đang hiển thị read-model lỗi hoặc chưa cập nhật.

### 25.2. Boundary tests về thời gian

Kiểm tra quyền trước effectiveAt, đúng effectiveAt và sau đó; log riêng eventCreatedAt, receivedAt, dispatchedAt, observedAt. Không “sửa” thời điểm cutoff theo lúc job chạy.

### 25.3. Test fail-safe

Khi evidence service, target API hoặc SIEM không khả dụng, hệ thống không tự kết luận quyền đã mất. Giữ trạng thái chưa verified và kích hoạt escalation theo mức rủi ro.

### 25.4. Test privacy và integrity

Dùng test principals/tenant giả, không dùng dữ liệu nhân viên thật hoặc raw tokens. Kiểm tra thay log lịch sử bị phát hiện, truy cập ngoài scope bị chặn và retention deletion có kiểm soát.

## 26. Những hiểu lầm thường gặp

**“IAM đã gửi lệnh, tức tài khoản đã bị thu hồi.”** DISPATCHED chỉ là lệnh gửi đi.

**“SCIM trả 204 là xong hết mọi quyền.”** Không chứng minh local session, direct grant hoặc API key đã mất.

**“Log ghi success nghĩa là người dùng không truy cập được.”** Phải biết success là ACK, observed account state hay effective-access verification.

**“Xóa account IdP là xóa tất cả SaaS accounts.”** SSO, SCIM và local SaaS accounts có vòng đời riêng.

**“Revoke refresh token chặn ngay access token đã phát.”** Không mặc định; tùy token/resource server profile.

**“Không thấy log truy cập nữa nghĩa là không còn quyền.”** Có thể telemetry thiếu, pipeline lỗi hoặc job chưa hoạt động.

**“Tôi biết email nên không cần identity ID.”** Email có thể đổi/tái sử dụng; cần immutable IDs và target mapping.

**“Mọi HTTP 404 khi revoke đều là success.”** Có thể targetId sai hoặc account ở nơi khác.

**“Dùng log ingest time làm thời điểm Leaver effective.”** Ingest time không phải business effectiveAt.

**“Retry ba lần nghĩa là đã thu hồi ba quyền.”** Có ba attempts cho một operation.

**“Một target còn admin nhưng tổng hoàn tất 99% vẫn đạt.”** Workflow critical chưa đầy đủ.

**“Hết session SSO nghĩa role tại database đã hết.”** Database grant có thể độc lập.

**“Rotate secret nghĩa service identity đã deprovision.”** Principal/trust/role cần quản trị riêng.

**“Owner nghỉ thì xóa mọi service accounts.”** Cần phân biệt human JML với workload lifecycle.

**“Một request 403 chứng minh toàn hệ thống đã chặn.”** Chỉ là bằng chứng tại một endpoint/scope.

**“UNKNOWN có thể tính success khi SLA hết.”** Không có bằng chứng không phải bằng chứng thành công.

**“Cập nhật status trong database là audit đầy đủ.”** Cần event history, actor, time, operation và evidence.

**“Log được lưu trong database là không thể bị sửa.”** Cần phân quyền, tamper evidence và retention controls.

**“Càng log nhiều PII, token càng dễ điều tra.”** Có thể tạo rủi ro dữ liệu nghiêm trọng; dùng references và logging tối thiểu.

**“Không cần kiểm tra log pipeline vì SIEM vốn luôn nhận hết.”** Pipeline cũng có outage, lag và dropped messages.

## 27. Bài tập tự đánh giá

### Bài tập A — SCIM PATCH success, session còn hoạt động

Connector gọi disable User và nhận HTTP 204. Năm phút sau người dùng vẫn sử dụng SaaS cookie để export.

**Phân tích:** Command ACK không phải enforcement. Log deprovision phải có target account result, session state, residual access event, escalation và readback sau remediation. Kiểm tra provider-specific session/token behavior.

### Bài tập B — Mover được xử lý sau Leaver

IAM đã gỡ quyền theo Leaver version 110. Một event Mover version 109 được retry và thêm người dùng lại vào Finance group.

**Phân tích:** Thiếu version guard/desired-state check. Ghi stale event, ngăn regrant, reconcile group và mở incident nếu target có quyền tồn dư.

### Bài tập C — Một workflow còn một target rủi ro cao

Nhân viên có 9 target, 8 target verified, một cloud role organization-admin chưa revoke vì target outage.

**Phân tích:** Không đóng toàn workflow. Ghi PARTIAL, critical target owner, cutoff, containment, next retry và high-risk escalation.

### Bài tập D — Kỹ sư owner service account nghỉ

Kỹ sư quản lý một backup workload nghỉ việc, nhưng job vẫn cần phục vụ doanh nghiệp.

**Phân tích:** Log thu hồi quyền cá nhân, bàn giao owner, đánh giá secret export và trust. Không xóa workload hợp lệ theo phản xạ; đưa service principal vào review riêng.

### Bài tập E — Log được sửa thành Success sau retry

Lần đầu revoke timeout. Lần sau được verified; hệ thống xóa dòng timeout cũ rồi chỉ giữ success.

**Phân tích:** Audit history bị mất. Phải giữ attempt đầu và attempt sau, cùng readback evidence, khi cần append correction event; dashboard có thể tổng hợp trạng thái mới nhất.

### Bài tập F — SIEM thiếu event

HRIS phát 20 Leaver events, IAM chỉ tạo 19 workflows do message bị rơi. SIEM hiển thị 19/19 completed.

**Phân tích:** Completion không phản ánh coverage. Cần source-to-sink reconciliation, missing-event alert, queue/DLQ monitoring và đối soát nguồn nhân sự.

### Bài tập G — Quyền hợp lệ khác còn lại

Nhân viên Mover mất grant Finance report.export qua group A, nhưng vẫn có một baseline viewer grant B để đọc báo cáo công khai.

**Phân tích:** Phải ghi chính xác mục tiêu A bị revoked; không xóa B nếu hợp lệ. Nếu policy cấm toàn bộ Finance access, cần xét lại scope và revoke các đường khác.

### Bài tập H — Token cũ còn hạn

IAM gỡ role production lúc 09:00, access token có exp 10:00, API kiểm tra mỗi signature và expiry.

**Phân tích:** Grant revoked và token valid là hai trạng thái khác nhau. Cần thiết kế entitlement freshness/revocation/containment, lưu risk window và không tuyên bố toàn data-plane access đã hết.

### Bài tập I — Account xóa nhưng audit chứa PII không cần

Log giữ toàn bộ HRIS record, passport number và raw session token để “sau này audit”.

**Phân tích:** Dư dữ liệu và tạo rủi ro rò rỉ. Lưu immutable identity reference, reasonCode, policyVersion, evidenceRef; giới hạn PII, mã hóa và áp dụng retention/legal hold phù hợp.

## 28. Checklist thiết kế Deprovisioning log

1. **Source:** sự kiện đến từ HRIS, contract, ticket hay incident system đáng tin?
2. **Reason:** triggerType và reasonCode rõ, không chỉ ghi “delete user”?
3. **EffectiveAt:** cutoff nghiệp vụ và timezone được xác định?
4. **Identity:** immutable subjectId, subjectType, sourceVersion đúng?
5. **Mapping:** targetAccountId, tenant, environment và principal ID chính xác?
6. **Scope:** account, group, direct grant, session, token, credential được liệt kê?
7. **Owner:** có business owner, technical executor và verifier?
8. **Approval:** authority/policyVersion và exception có dấu vết?
9. **Correlation:** workflowId, operationId, attemptId, eventId, causationId?
10. **Desired state:** từng target và entitlement cần có trạng thái gì?
11. **Command:** action, requestAt, transport result và normalized error?
12. **ACK:** không bị nhầm với effective access?
13. **Readback:** observedAt, method, scope và evidenceRef có đầy đủ?
14. **Partial:** target nào còn UNKNOWN/PARTIAL và next action?
15. **Retries:** có idempotency, retryCount, DLQ và backoff?
16. **Version:** Mover cũ không tái cấp quyền sau Leaver?
17. **Concurrency:** Joiner/Mover/Revoke xử lý theo desired-state version?
18. **SCIM:** hiểu đúng active=false, Group PATCH, DELETE và capability?
19. **SSO:** IdP disable có xử lý RP sessions khi cần?
20. **OAuth:** access/refresh token lifecycle được ghi riêng?
21. **RBAC/ABAC:** xác minh action/resource/tenant và grant sources?
22. **NHI:** service principal, integration account, trust, key, certificate có inventory?
23. **Human JML:** Leaver của owner không tự xóa workload còn cần?
24. **Credential hygiene:** không log raw tokens, secret, cookie hay password?
25. **Audit integrity:** append-only, tamper evidence và privileged access controls?
26. **Privacy:** PII minimization, RBAC/ABAC cho log viewer, tenant isolation?
27. **Retention:** lưu theo luật/policy, xử lý legal holds và deletion?
28. **Clock:** eventTime, effectiveAt, observedAt, ingestedAt không bị trộn?
29. **Metrics:** time-to-ack khác time-to-verified và actual enforced?
30. **SLO:** risk tiers, cutoff, retry/escalation ownership được công bố?
31. **SIEM:** alert residual PERMIT, logging gap, critical target chưa verified?
32. **Pipeline health:** heartbeat, queue lag, missing events và dropped logs?
33. **Coverage:** source-to-sink và target inventory đều được đối soát?
34. **Verification:** tests/readback ở mọi access path thuộc scope?
35. **Drift:** revoke rồi grant tái xuất hiện phải reopen?
36. **Dashboard:** không coi 99% progress là all-access-removed?
37. **Reporting:** numerator/denominator, as-of, schemaVersion, reason được định nghĩa?
38. **Testing:** 404, timeout, 429, concurrency, clock skew, session stale và failure?
39. **Incident:** có runbook, risk containment và audit trail?
40. **Technical closure:** chỉ VERIFIED_CLOSED khi bằng chứng đủ cho policy scope?

## 29. Tổng kết

**Deprovisioning log** là chuỗi bằng chứng cho thấy một quyết định thu hồi quyền đã đi từ **nguồn nghiệp vụ** qua **IAM orchestration**, **connector/target command**, tới **trạng thái quan sát được** và **xác minh quyền truy cập thực tế**.

Thiết kế tốt phải tách:

- **Business event và effectiveAt:** căn cứ và deadline thu hồi.
- **Desired state:** quyền/account/session nào phải chấm dứt.
- **Command/ACK:** tác vụ đã gửi và phản hồi giao thức.
- **Target evidence:** quyền ở hệ thống đích thực tế đã thay đổi ra sao.
- **Verified closure:** mọi access path thuộc phạm vi đều đạt điều kiện kiểm chứng.
- **Audit integrity và privacy:** log tin cậy, truy vết được nhưng không lộ secret hoặc PII quá mức.

Trong **Joiner–Mover–Leaver**, hệ thống phải theo dõi IdP, SSO, SCIM, RBAC/ABAC, local grants, session/token, cloud IAM, PAM và service accounts theo **đúng vòng đời của từng đối tượng**. Retry, delay, duplicate, target outage hoặc pipeline mất log phải tạo trạng thái điều tra được, không bị che bằng nhãn “Success”.

**Ghi nhớ:** **Log “đã gửi lệnh thu hồi” không phải bằng chứng “không còn quyền truy cập”.** Chỉ khi có **target readback hoặc bằng chứng enforcement phù hợp, đầy đủ theo scope và có audit trail** mới có thể tuyên bố deprovisioning được xác minh, qua đó giảm **quyền truy cập tồn dư**.







