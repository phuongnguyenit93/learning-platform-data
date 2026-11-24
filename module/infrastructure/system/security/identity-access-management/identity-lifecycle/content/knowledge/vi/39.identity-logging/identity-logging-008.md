# Log correlation trong IAM: liên kết sự kiện danh tính xuyên hệ thống

**Log correlation (tương quan nhật ký)** là quá trình **liên kết những bản ghi sự kiện thuộc cùng một yêu cầu, chuỗi nghiệp vụ, chủ thể hoặc thay đổi quyền** để tái dựng điều gì đã xảy ra qua nhiều thành phần. Trong quản lý danh tính, câu hỏi không chỉ là “IdP có log đăng nhập không?”, mà còn là: **“Một nhân viên đã chuyển vai trò lúc nào, hệ thống nào nhận sự kiện, quyền nào được cấp/thu hồi, token hoặc phiên cũ còn sử dụng được không, và bằng chứng nào chứng minh quyết định cuối tại API?”**

Bài **“Log correlation”** thuộc chương **Identity logging** của module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Phạm vi module bao gồm quản lý danh tính theo **Joiner–Mover–Leaver (JML)** từ xác minh, tạo account và cấp quyền đến rà soát/thu hồi khi thay đổi nhiệm vụ; tích hợp **IdP, SSO, SCIM, RBAC/ABAC, service account**, kiểm toán và giảm **quyền truy cập tồn dư**. Vì vậy, log correlation phải nối được **sự kiện vòng đời** với **quyết định authorization tại ứng dụng đích**, không dừng ở trạng thái một ticket hoặc một connector.

**Tình huống mở đầu:** 09:00, nhân viên Mai chuyển từ bộ phận tạo thanh toán sang bộ phận phê duyệt. HRIS phát event; IGA tạo yêu cầu gỡ quyền Creator; IdP xóa group; SCIM trả HTTP 204. Đến 09:07, Finance API vẫn cho Mai tạo payment bằng phiên cũ. Nếu các log chỉ có “success” rời rạc, tổ chức dễ báo rằng thu hồi đã thành công. Khi có correlation, có thể liên kết **lifecycle event → grant change → SCIM target account → access token/session → API decision**, phân biệt **APPLIED** ở connector với **VERIFIED DENY** tại Resource Server.

## 1. Mục tiêu và giới hạn của log correlation

Log correlation phục vụ nhiều mục đích, nhưng cần phân biệt kết luận có thể chứng minh từ từng nguồn:

| Mục tiêu | Câu hỏi phải trả lời | Bằng chứng cần có |
| --- | --- | --- |
| **Troubleshooting** | Vì sao user không đăng nhập được sau Joiner? | HRIS activation, provisioning, IdP account, SSO request, API error. |
| **Access governance** | Grant theo role có được phê duyệt và áp dụng đúng? | Request ID, approval, policy version, target readback. |
| **Deprovisioning verification** | Người đã Leaver còn thực hiện được action không? | EffectiveAt, revoke events, API/PEP outcomes, verifiedAt. |
| **Threat detection** | Có access bất thường hoặc token cũ bị lạm dụng không? | Login/token issuance, subject/client, source signals, resource actions. |
| **Forensics** | Chuỗi thao tác do ai, công cụ nào, trên object nào? | Trusted actor, session/transaction, resource, event provenance. |
| **SLA/operations** | Mất bao lâu từ thay đổi quyền tới việc thực sự bị chặn? | EffectiveAt, appliedAt, verifiedAt từng target, clock quality. |
| **Compliance/audit** | Ai yêu cầu, ai phê duyệt, ai thi hành, ai xác minh? | Actor roles, approvals, policy, immutable/protected evidence. |

**Log correlation không tự động là audit completeness hay causality proof.** Hai sự kiện cùng subject hoặc cùng khoảng thời gian có thể **không** liên quan; một trace cho thấy request đã đến API không chứng minh DB transaction đã commit. Cần **correlation keys đáng tin, quan hệ nghiệp vụ rõ ràng, trạng thái thực thi và phạm vi quan sát**.

## 2. Phân biệt log, event, trace, audit record và metric

| Khái niệm | Đối tượng | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| **Application log** | Thông điệp runtime hoặc nghiệp vụ. | “SCIM PATCH completed”. | Có thể thiếu schema, không đủ bằng chứng access. |
| **Security event** | Sự kiện liên quan xác thực, quyền, chính sách. | LOGIN_FAILED, ROLE_REVOKED. | Một event đơn lẻ chưa có bối cảnh JML. |
| **Audit record** | Bản ghi trách nhiệm/quyết định có provenance, retention và kiểm soát integrity. | Ai duyệt yêu cầu admin. | Chỉ có giá trị nếu kiểm được nguồn và đúng phạm vi. |
| **Distributed trace** | Các spans của một luồng request xuyên service. | HR webhook → IGA → connector. | Thường không bao phủ workflow bất đồng bộ kéo dài nhiều ngày. |
| **Metric** | Số đo tổng hợp. | P95 provisioning latency. | Không cung cấp bản ghi từng subject. |
| **Correlation graph** | Liên kết các sự kiện qua causal/business keys. | Event Mover dẫn tới 3 revoke tasks. | Chất lượng phụ thuộc nguồn identity mapping và links. |

Ví dụ, một trace ID có thể liên kết request IGA với connector, trong khi **campaign access review** tồn tại hàng tuần và gồm hàng nghìn trace IDs. Ngược lại, một API request có thể có một trace gồm nhiều spans nhưng không biết **request đó thuộc access grant nào** nếu hệ thống không ghi business/correlation IDs.

## 3. Những nguồn log trong vòng đời danh tính

~~~mermaid
flowchart LR
    HR["HRIS / Joiner–Mover–Leaver"] --> IGA["IGA / Access request & approval"]
    IGA --> IDP["IdP / Directory / MFA"]
    IGA --> SCIM["SCIM / Provisioning connector"]
    IDP --> SSO["SSO / OAuth / OIDC / SAML"]
    SCIM --> APP["SaaS / ERP / Local roles"]
    SSO --> APP
    APP --> API["Resource Server / PEP / Domain actions"]
    IGA --> E["Normalized event pipeline"]
    HR --> E
    IDP --> E
    SCIM --> E
    SSO --> E
    APP --> E
    API --> E
    E --> SIEM["SIEM / Audit store / Reconciliation"]
~~~

| Nguồn | Event điển hình | ID liên kết có thể có |
| --- | --- | --- |
| **HRIS** | PERSON_JOINED, ROLE_CHANGED, EMPLOYMENT_ENDED. | Stable workforce ID, lifecycleEventId, revision. |
| **IGA** | ACCESS_REQUESTED, APPROVED, REJECTED, REVOKE_PLANNED. | RequestId, approvalId, entitlementId, subjectRef. |
| **IdP** | ACCOUNT_CREATED, AUTH_SUCCESS, MFA_CHALLENGED, GROUP_REMOVED. | IdP subject ID, session ID, requestRef. |
| **OAuth Authorization Server** | TOKEN_ISSUED, REFRESH_REJECTED, GRANT_REVOKED. | Issuer, clientId, subjectRef, protected token reference. |
| **SSO/SAML SP** | ASSERTION_ACCEPTED, SESSION_CREATED, LOGOUT_PROCESSED. | Issuer + persistent NameID mapping, SP session ref. |
| **SCIM connector** | PATCH_SENT, PATCH_ACK, RETRY_SCHEDULED. | JobId, operationId, target userId, SCIM requestRef. |
| **Target SaaS/ERP** | ROLE_CHANGED, ACCOUNT_DISABLED, LOCAL_ACL_UPDATED. | Target account ID, permission/resource ID. |
| **API/PEP** | AUTHZ_ALLOW, AUTHZ_DENY, TRANSACTION_COMMITTED. | Verified actor, resource, request/trace, policy version. |
| **PAM/CI/CD/workload** | ROLE_ACTIVATED, SERVICE_TOKEN_ISSUED, JOB_EXECUTED. | Principal/workload ID, activation/runId, trust context. |
| **Audit/verification worker** | NEGATIVE_PROBE_RUN, REVOKE_VERIFIED, COVERAGE_GAP. | VerificationId, targetId, evidenceRef, verifiedAt. |

**Không phải tất cả nguồn đều có cùng trường ID hoặc cùng clock**. Bài toán kỹ thuật là **chuẩn hóa schema và xác minh mapping** thay vì nối trực tiếp mọi log theo một chuỗi email.

## 4. Correlation ID, trace ID, span ID, session ID và subject ID

Các ID khác nhau trả lời **những câu hỏi khác nhau**. Dùng sai ID có thể gây false positives hoặc mất khả năng điều tra.

| Trường | Phạm vi đúng | Ví dụ khái niệm | Điều không được suy |
| --- | --- | --- | --- |
| **correlationId** | Một business operation/workflow hoặc một request theo thiết kế. | corr-access-4821. | Một ID luôn đại diện một người hoặc chứng minh nhân quả. |
| **traceId** | Một distributed trace trong hệ thống tracing. | 32 ký tự hex theo W3C Trace Context. | Một trace bao trùm toàn vòng đời JML nhiều ngày. |
| **spanId** | Một span/đoạn thực thi trong trace. | 16 ký tự hex theo W3C Trace Context. | Dùng độc lập như stable business ID. |
| **parentSpanId** | Quan hệ parent-child của span. | Reference từ request trước. | Mọi sự kiện cùng request phải là con trực tiếp. |
| **requestId** | Một HTTP/API call hoặc message handling attempt. | req-2026-1042. | Retry sẽ luôn dùng lại ID này. |
| **operationId** | Một thao tác cấp/thu hồi có thể được retry. | op-revoke-782. | Connector ack chứng minh target DENY. |
| **lifecycleEventId** | Một event JML nghiệp vụ. | jml-move-142. | Tất cả target updates đã hoàn thành. |
| **subjectId** | Stable principal trong một authority. | person-4821, app-report-prod. | ID từ hai issuer/tenant khác nhau luôn trùng chủ thể. |
| **idpSessionRef** | Phiên đăng nhập trong phạm vi IdP. | sess-ref-91. | Trạng thái của mọi SP session hay access token. |
| **oauthGrantRef** | Authorization grant/client connection. | grant-ref-32. | Token phát từ grant đó đều còn hoạt động. |
| **tokenRef/jti** | Tham chiếu token khi có, thường trong phạm vi issuer. | token-ref-7. | jti luôn có hoặc là secret cần lưu thô. |
| **targetAccountId** | Account ID trong ứng dụng đích. | erp-user-1057. | Tương đương email hoặc workforceId nếu chưa xác minh. |
| **resourceId** | Object nghiệp vụ đang được thao tác. | payment-2026-150. | Cùng object đồng nghĩa cùng transaction attempt. |
| **jobRunId** | Một execution attempt của batch/workload. | run-20261123-0200. | Retry theo cùng business operation đã thành công. |

### Hệ quy chiếu ID

**ID có thể chỉ duy nhất trong một phạm vi**. Ví dụ subject của OIDC nên được hiểu cùng **issuer**, userId SCIM cùng **target system/tenant**, token jti cùng **issuer/token type** theo contract, session ID cùng hệ thống phát hành.

~~~text
Canonical principal key (mô hình):
  identityAuthority + tenant + immutableSubjectId

Target account key:
  targetSystem + targetTenant + targetAccountId

Token reference key:
  issuer + tokenType + protectedTokenReference
~~~

**Không dùng email, displayName, username hoặc IP làm khóa định danh duy nhất.** Những trường đó có thể thay đổi, tái sử dụng, đi qua NAT hoặc nhiều người chia sẻ một địa chỉ.

## 5. Phân biệt correlation và causation

Hai sự kiện xảy ra gần nhau hoặc có cùng user có thể được **correlate**, nhưng chưa chắc cái này **gây ra** cái kia.

- **Same subject**: cùng principal có thể đăng nhập từ ba app khác nhau trong vài phút.
- **Same trace**: các spans chia sẻ một context, thường biểu thị một execution flow nhưng vẫn phải kiểm nguồn context.
- **Same business operation**: event Mover dẫn đến nhiều revoke operations, có quan hệ rõ qua parent/business IDs.
- **Same resource**: hai người truy cập cùng payment không chứng minh một người tự phê duyệt.
- **Explicit causation link**: childEvent.parentEventId = event ID từ hệ thống nguồn đã xác minh, kết hợp workflow revision/operation state.
- **Temporal correlation**: trùng cửa sổ thời gian là manh mối, không phải bằng chứng duy nhất.

### Một mô hình quan hệ nhân quả

~~~mermaid
flowchart TD
    H["HR Mover event E1"] -->|causedByEventId| R["IGA revoke request R1"]
    R -->|approvedOperation| O1["SCIM revoke op O1"]
    R -->|approvedOperation| O2["Local ACL revoke op O2"]
    O1 --> A1["SCIM ACK O1"]
    O2 --> A2["ERP API ACK O2"]
    A1 --> V1["Effective-access probe V1"]
    A2 --> V2["Effective-access probe V2"]
    V1 --> S{"Tất cả required targets VERIFIED?"}
    V2 --> S
    S -->|Có| D["JML revoke verified"]
    S -->|Chưa| N["Partial / remediation"]
~~~

**Một parent-child chain phải có nguồn dữ liệu đáng tin**, không tự tạo causal links chỉ bằng timestamp và common substring trong log message.

## 6. Bộ schema chuẩn hóa dành cho identity events

Các nhóm dữ liệu nên có cấu trúc, phiên bản và được lưu theo **mục đích kiểm toán**, thay vì ghi những dòng text khó join.

| Nhóm trường | Trường đề xuất | Lý do |
| --- | --- | --- |
| **Event envelope** | eventId, eventType, schemaVersion, eventSource, occurredAt, observedAt. | Định danh một event và đo ingestion delay. |
| **Correlation** | correlationId, traceId, spanId, parentEventId, causationId, requestId. | Liên kết request và business flow. |
| **Principal** | actorRef, subjectRef, principalType, authority, tenantRef. | Tách người thực thi và người được thay đổi quyền. |
| **Application/workload** | clientRef, servicePrincipalRef, workloadRef, jobRunId. | Truy vết phi con người và ủy nhiệm. |
| **Authorization** | action, resourceRef, entitlementRef, policyId/version, decision, reasonCode. | Kiểm điều kiện ALLOW/DENY. |
| **Lifecycle** | lifecycleEventId, revision, effectiveAt, desiredState, appliedAt, verifiedAt. | Đo xử lý JML và thu hồi quyền thực tế. |
| **Provisioning** | operationId, targetSystem, targetAccountId, connectorResult, readbackResult. | Phân biệt command ack và actual target. |
| **Security context** | authenticationMethod, assuranceLevel, sessionRef, protectedTokenRef. | Phân tích đăng nhập/token nhưng không lộ credential. |
| **Integrity** | producerIdentity, signature/provenanceRef, retentionClass, classification. | Tin cậy nguồn và kiểm soát chứng cứ. |
| **Operational** | outcome, retryAttempt, idempotencyKeyRef, errorCategory. | Phân biệt retry, partial failure và lỗi hạ tầng. |

### Ví dụ structured JSON minh họa

~~~json
{
  "schemaVersion": "iam.identity-event.v1",
  "eventId": "evt-000748",
  "eventType": "ACCESS_REVOKE_REQUESTED",
  "eventSource": "iga-workflow",
  "occurredAt": "2026-11-23T02:00:00.100Z",
  "observedAt": "2026-11-23T02:00:00.300Z",
  "correlationId": "corr-mover-4821",
  "causationId": "jml-move-142",
  "requestId": "req-erase-714",
  "traceId": "63f8c43dabdd20c62bb75e10c134bb02",
  "actor": {
    "principalType": "WORKLOAD",
    "authority": "corporate-iam",
    "subjectRef": "iga-provisioner-prod"
  },
  "subject": {
    "principalType": "HUMAN",
    "authority": "corporate-idp",
    "subjectRef": "person-4821"
  },
  "target": {
    "systemRef": "finance-erp",
    "tenantRef": "tenant-vn",
    "accountRef": "erp-user-1057"
  },
  "entitlementRef": "payment.create",
  "lifecycle": {
    "eventRef": "jml-move-142",
    "revision": "32",
    "effectiveAt": "2026-11-23T02:00:00Z"
  },
  "decision": "REVOKE_PLANNED",
  "policyVersion": "finance-access-v6",
  "credentialValueLogged": false
}
~~~

**Schema này chỉ minh họa, không phải chuẩn bắt buộc của OpenTelemetry, SCIM hay SIEM nào.** Mọi giá trị tham chiếu cần gắn đúng trust domain, và event phải có **version** để consumer không gán sai nghĩa khi các thuộc tính thay đổi.

## 7. Event nào cần correlationId, event nào cần causal link?

Một lựa chọn thực tế là ghi **cả correlationId và causationId** khi có workflow bất đồng bộ.

- **correlationId**: gom các bước thuộc cùng yêu cầu nghiệp vụ; có thể kéo dài nhiều giờ và bao phủ nhiều traces.
- **causationId/parentEventId**: cho biết event hiện tại **được tạo do sự kiện hoặc thao tác nào**; cần được phát bởi thành phần tin cậy và bảo toàn qua outbox/queue.
- **traceId**: mô tả tương quan kỹ thuật của một execution trace; có thể được nối qua HTTP/gRPC, nhưng **không nên dùng làm business transaction ID duy nhất**.
- **operationId**: định danh một hành động logic có thể retry; hữu ích cho idempotency.
- **attemptId**: phân biệt từng lần thử, giúp chẩn đoán retries và lỗi.
- **resourceRef**: object đang được kiểm/đổi; cần khi xác định self-approval và actual side effect.

### Fan-out và fan-in

~~~text
Business correlation: corr-leaver-2026-42
  ├─ op-disable-idp-1 (attempt 1, attempt 2)
  ├─ op-revoke-scim-erp-1 (attempt 1)
  ├─ op-revoke-scim-crm-1 (attempt 1, attempt 2, attempt 3)
  ├─ op-revoke-token-grants-1
  └─ verification-batch-42
      ├─ targetId=ERP, verifiedAt=...
      ├─ targetId=CRM, status=UNVERIFIED
      └─ targetId=Finance API, verifiedAt=...
~~~

Nếu chỉ có một dòng “LEAVER COMPLETED” ở IGA nhưng CRM vẫn **UNVERIFIED**, correlation phải hiển thị rõ **các nhánh chưa hoàn thành** thay vì collapse thành một success.


## 8. Stable identity mapping: liên kết cùng một subject qua nhiều hệ thống

Đây thường là phần khó nhất của log correlation trong IAM. HRIS có workforceId, IdP có subjectId, SaaS có SCIM id, hệ thống ERP có accountId và ứng dụng legacy chỉ còn username. Nếu kết hợp sai, một báo cáo có thể **gán hành động của người A cho người B** hoặc **bỏ sót quyền tồn dư của Leaver**.

### Bảng ánh xạ danh tính có provenance

| Identity domain | Khóa cần giữ | Quan hệ với canonical subject |
| --- | --- | --- |
| **HRIS** | HR source + stable person ID + employment identity nếu cần. | Event Joiner/Mover/Leaver có authority và revision. |
| **Corporate IdP** | Issuer/directory/tenant + immutable user object ID. | Link được xác minh tới workforce/person principal. |
| **OIDC** | Issuer + sub, đúng hợp đồng client và pairwise subject nếu có. | Không tự so sub của hai issuers hoặc hai sectors. |
| **SAML** | IdP entity ID + NameID/format và mapping theo SP contract. | Persistent NameID hoặc target ID phải được xác minh; không coi transient NameID là stable. |
| **SCIM target** | Target system + tenant + SCIM id; externalId nếu được dùng. | externalId thường được client provisioning quản lý, phải kiểm nguồn/trust. |
| **Legacy** | App namespace + local account key. | Link xác minh từ provisioning hoặc evidence đủ tin cậy. |
| **Service identity** | Issuer/trust domain + service principal/workload ID. | Owner/team khác với principal; không gán owner là actor của mọi request. |
| **Device identity** | Device issuer + immutable device ID/certificate. | Chỉ là context của request, không thay human principal. |

### Một bảng link có thể chứa

~~~text
canonicalSubjectRef
sourceAuthority
sourceTenant
sourceImmutableId
targetSystem
targetTenant
targetAccountId
linkMethod         // HR feed, SCIM provisioning, verified enrollment...
linkConfidence     // VERIFIED hoặc UNVERIFIED; không chỉ numeric score
validFrom / validTo
observedAt
linkRevision
provenanceEvidenceRef
~~~

**Không ghép chỉ bằng email, displayName, employeeName, IP hoặc user agent.** Email có thể đổi/tái sử dụng; IP có NAT/VPN; một service principal có thể thay mặt nhiều người dùng hoặc không có người dùng.

### Pairwise/pseudonymous subject

Một số IdP có thể phát **pairwise subject identifiers** khác nhau giữa các clients/sectors. Nếu hai app báo sub khác nhau cho cùng user, điều đó không đồng nghĩa hai người khác nhau; cần **mapping có thẩm quyền từ IdP/IGA**, không tự suy ngược từ patterns.

### Identity linking theo thời gian

Một target account có thể được chuyển quyền sở hữu hoặc tái sử dụng nếu thiết kế legacy không bảo đảm immutable IDs. Correlation phải dùng **validFrom/validTo** của mapping; không lấy bảng mapping hiện tại để gắn ngược log năm trước cho một nhân viên mới. Khi rehire, cần tách **person identity, employment relationship và account lifecycle** theo nguồn sự thật.

## 9. Distributed tracing: W3C Trace Context và OpenTelemetry

Distributed tracing giúp liên kết các spans của **một request kỹ thuật** khi request đi từ API Gateway sang IdP adapter, IGA workflow và SCIM connector.

### Trace Context

W3C Trace Context định nghĩa cách truyền thông tin trace qua HTTP, gồm **traceparent** và **tracestate**. Traceparent thường biểu diễn các thành phần **version, trace-id, parent-id và flags** theo cú pháp chuẩn. OpenTelemetry có thể dùng chúng để truyền context và tạo spans.

~~~http
POST /internal/provision HTTP/1.1
Host: connector.example.internal
traceparent: 00-63f8c43dabdd20c62bb75e10c134bb02-a8b81fbc6e4a90c2-01
Content-Type: application/json

{"operationRef":"op-revoke-782"}
~~~

Đoạn HTTP chỉ minh họa format; **trace-id/span-id không phải bí mật đăng nhập hoặc bằng chứng quyền**. Không dùng giá trị traceparent do caller không tin cậy cung cấp để xác thực actor.

### Cách dùng an toàn

1. **Trace context từ edge công khai không đáng tin về bảo mật.** Gateway có thể tiếp nhận, phân tách hoặc tạo trace mới theo policy; không lấy traceId làm bằng chứng client đã được IdP xác thực.
2. **TraceId không phải authorization credential.** Người tấn công có thể đoán hoặc gửi một giá trị traceparent; mọi PEP vẫn phải kiểm identity/token.
3. **Span attributes** không nên chứa access token, password, secret, raw SAML assertions, session cookies hay PII không cần.
4. **Sampling** có thể bỏ traces. Audit events trọng yếu phải được phát/ghi qua một cơ chế không phụ thuộc vào việc trace được sample.
5. **Long-running workflow** có thể trải nhiều traces; correlationId và causation links giữ liên kết xuyên nhiều attempts hoặc ngày.
6. **Async queue propagation** cần chọn context fields, trace links và message metadata theo contract; không giả định context HTTP sẽ tự theo qua mọi queue.
7. **Cross-trust-boundary propagation** cần sanitize baggage/tracestate; không đưa role/PII do client tự khai thành trusted attributes.
8. **High-cardinality data** như subjectId không nên gắn vào metric labels tùy tiện gây tải và nguy cơ privacy; audit store có thể chứa protected refs theo policy.

### Trace links thay vì một cây cha–con giả

Một job tổng hợp được kích hoạt từ **nhiều events** hoặc một message retry được xử lý ở worker mới có thể dùng **span links** thay vì ép mọi spans vào một parent chain. Causal model nghiệp vụ vẫn dựa trên **eventId/operationId**, không dựa duy nhất vào trace structure.

## 10. Correlation qua message queues, retries và asynchronous jobs

IAM thường chạy bất đồng bộ: HR webhook → queue → IGA → connector → SCIM → reconciliation. Một số bước có retry, dead-letter queue, compensation hoặc manual approval. Vì vậy chỉ ghép “requestId” của HTTP call đầu **không đủ**.

### Envelope minh họa khi gửi message

~~~json
{
  "messageId": "msg-5821",
  "eventId": "evt-mover-42",
  "eventType": "JML_MOVER",
  "eventRevision": 18,
  "correlationId": "corr-mover-4821",
  "causationId": "evt-hr-1009",
  "operationId": "op-revoke-creator-7",
  "attemptId": "attempt-1",
  "targetRef": "erp-vn",
  "subjectRef": "person-4821",
  "occurredAt": "2026-11-23T02:00:00Z"
}
~~~

### Phân biệt logical operation và delivery attempt

| Thành phần | Khi retry | Tại sao |
| --- | --- | --- |
| **Business correlationId** | Thường giữ nguyên. | Tất cả attempts cùng business request. |
| **operationId/idempotency key** | Giữ nguyên với cùng thao tác logic. | Tránh ghi trùng hoặc thu hồi nhầm nhiều lần. |
| **attemptId** | Mỗi lần xử lý mới có ID mới. | Biết số lần và nguyên nhân lỗi. |
| **message delivery ID** | Có thể thay theo broker. | Broker không đảm bảo bằng business operation ID. |
| **traceId** | Có thể cùng hoặc khác tùy tracing design. | Không dùng làm idempotency key mặc định. |
| **lifecycle revision** | Không thay với retry cùng event. | Chặn event cũ làm mới lại grant. |

### Out-of-order và duplicate events

Giả sử Leaver revision 42 đã vô hiệu account, sau đó Mover revision 41 đến muộn. Log correlation cần hiển thị **event đến trễ bị bỏ qua vì stale revision**, không tạo một nhánh “ROLE_GRANTED success” trái trạng thái hiện hành. Hệ thống provisioning phải **kiểm business ordering/current state**; tương quan log chỉ phát hiện và chứng minh, không tự ngăn lỗi.

### Dead-letter queue

Một SCIM operation lỗi lặp rồi vào DLQ phải giữ **operationId, subjectRef, targetRef, correlationId, attempt history và error class**. Nếu DLQ bị xử lý thủ công, event phải liên kết với cùng business operation và ghi **operator identity**. Không phát request mới hoàn toàn tách dấu vết rồi báo thao tác gốc thành công.

## 11. Thời gian và độ tin cậy: occurredAt, observedAt, effectiveAt, verifiedAt

Một chuỗi sự kiện qua nhiều systems **không phải lúc nào cũng sắp đúng theo timestamp** nếu đồng hồ lệch, queue trễ hoặc logs được ingest thành lô.

| Mốc | Ý nghĩa | Nguồn |
| --- | --- | --- |
| **occurredAt** | Nguồn nói event xảy ra lúc nào. | Producer clock; cần ghi trust/clock health. |
| **observedAt/ingestedAt** | Collector nhận/ghi event lúc nào. | Logging pipeline. |
| **effectiveAt** | Theo policy, quyền cần có hoặc ngừng có hiệu lực lúc nào. | HRIS/IGA business source. |
| **approvedAt** | Quyết định approval được ghi lúc nào. | IGA approval service. |
| **appliedAt** | Connector/target đã thực hiện thay đổi ở thời điểm nào. | Target readback hoặc system event. |
| **verifiedAt** | Đã có evidence tại PEP chứng minh hành vi mong muốn. | Verification engine/target. |
| **expiredAt** | Token/grant/session hết hạn theo policy thực tế. | AS/PAM/target. |
| **resolvedAt** | Incident/remediation được đóng theo quy trình. | Incident system, không thay verifiedAt. |

### Ví dụ về đồng hồ và thứ tự

~~~text
10:00:00.000Z  HRIS Mover effectiveAt.
10:00:01.000Z  IGA phát revoke operation.
10:00:02.000Z  SCIM connector trả ACK.
10:00:04.000Z  ERP báo cập nhật role.
10:00:05.000Z  API PEP vẫn ALLOW (token/session cũ).
10:00:09.000Z  API PEP DENY và kiểm no side effects.
10:00:10.000Z  Collector nhận log của SCIM bị trễ.
~~~

Nếu chỉ sort theo **ingestion time**, SCIM event có thể xuất hiện sau API DENY, làm tưởng thao tác ngược thứ tự. Cần giữ **cả occurredAt và observedAt**, dùng causation ID, revision/sequence và ghi **clock uncertainty** nếu nguồn không đồng bộ.

### Khuyến nghị thời gian

- Lưu timestamps theo **ISO 8601 UTC có offset rõ**; bản hiển thị có thể chuyển timezone để người vận hành dễ đọc.
- Đồng bộ clock bằng cơ chế phù hợp nền tảng; giám sát **clock drift**.
- Không suy kết luận chính xác tới millisecond nếu dữ liệu chỉ có độ phân giải giây hoặc clock lệch.
- Cần phân biệt **SLA latency** đo bằng **verifiedAt - effectiveAt** với **ingestion delay** đo bằng observedAt - occurredAt.
- Khi một nguồn timestamp thiếu hoặc không tin cậy, báo **uncertainty** thay vì âm thầm làm tròn hoặc lấy thời điểm collector thay nguồn.

## 12. Joiner: tương quan xác minh danh tính, tạo account và activation

Một Joiner được kích hoạt chỉ sau khi nguồn sự thật xác nhận danh tính, employment/start date và các approvals cần thiết. Correlation phải đi qua cả **desired account state** và **thực tế truy cập**.

~~~mermaid
sequenceDiagram
    participant H as HRIS
    participant I as IGA
    participant D as IdP
    participant S as SCIM Connector
    participant A as SaaS Target
    participant V as Verification
    H->>I: JOINER event + effectiveAt + revision
    I->>I: Resolve baseline RBAC/ABAC + approvals
    I->>D: Create account, set activation policy
    I->>S: Provision target account / groups
    S->>A: SCIM create/update
    A-->>S: HTTP response + target account ref
    I->>V: Verify target account/entitlements & pre-start deny
    V->>A: Authorized probes before/after activation
    A-->>V: Expected DENY / ALLOW
    V-->>I: Verified evidence per target
~~~

### Các event liên quan

- **IDENTITY_PROOFED**: xác minh danh tính đủ điều kiện (không ghi full document/biometrics).
- **HR_JOINER_APPROVED**: source HRIS, employmentRef, effectiveAt.
- **ACCOUNT_PROVISIONING_REQUESTED**: canonical subject, targetSystem, targetAccountRef, role bundle.
- **ACCOUNT_CREATED/SCIM_ACKED**: target account ID, nhưng chưa chứng minh user có thể login.
- **ROLE_GRANTED**: permission scope, approvalId, policy version và actual result.
- **SSO_AUTH_SUCCEEDED/FAILED**: IdP/sessionRef, đúng user mapping.
- **API_AUTHZ_ALLOWED/DENIED**: effective action/resource/tenant, account status.
- **JOINER_VERIFIED**: aggregate target coverage, access tests trước/sau start date.

### Một trường hợp dễ bỏ sót

Tài khoản được provision trước ngày nhận việc để chuẩn bị thiết bị. Nếu API/SSO cho phép nhân viên truy cập dữ liệu nhạy cảm **trước effectiveAt**, correlation phải phát hiện chênh lệch giữa **account exists** và **authorized activation**. Việc tạo account trước không đương nhiên là sai nếu policy cho phép pre-provision; **truy cập vượt thời điểm được duyệt** mới là lỗi.

## 13. Mover: ghép role cũ, role mới, token cũ và SoD

Mover phức tạp vì cần biết **quyền nào phải thu hồi, quyền nào giữ lại, quyền nào cấp mới**, đồng thời ngăn **overlap** nếu SoD cấm.

### Chuỗi dữ liệu cần nối

1. **HR_ROLE_CHANGED**: subject, old/new job role, effectiveAt, revision.
2. **IGA_DESIRED_ENTITLEMENTS**: các quyền toRevoke/toKeep/toGrant.
3. **ACCESS_REVIEW/APPROVAL**: ai duyệt và theo policy version nào.
4. **ROLE_REVOKE_REQUESTED**: target, account, entitlement, operationId.
5. **SCIM/GROUP_UPDATED**: trạng thái connector và target readback.
6. **TOKEN_ISSUED_BEFORE_MOVER**: tokenRef được bảo vệ, audience, scope, exp nếu có.
7. **TOKEN/SESSION_BEHAVIOR**: các API calls bằng quyền cũ sau effectiveAt.
8. **ROLE_GRANT_NEW**: chỉ activate đúng sequencing/SoD rules.
9. **API_NEGATIVE_PROBE**: quyền cũ DENY, no unauthorized side effects.
10. **MOVER_VERIFIED**: tất cả required targets đạt; còn unresolved target thì PARTIAL.

~~~mermaid
flowchart TD
    E["Mover event E-42"] --> O["IGA desired delta"]
    O --> R["Revoke Creator at IdP + ERP local ACL"]
    R --> C{"Target readback & current PEP DENY?"}
    C -->|Không| B["Chặn activation Approver nếu SoD yêu cầu"]
    C -->|Có| G["Grant/activate Approver"]
    G --> T{"Transaction SoD checks?"}
    T -->|Có| V["ALLOW đúng case; DENY self-approval"]
    T -->|Không| X["Remediation / risk escalation"]
    V --> Z["Mover verified + audit"]
~~~

### Không nhầm “role revoked” với “token unusable”

IdP gỡ group lúc 09:01 nhưng JWT phát 08:55 còn hạn đến 09:25. Nếu API chỉ xem claim trong JWT, **ROLE_REVOKED ở IdP và API_AUTHZ_ALLOWED có thể cùng tồn tại**. Correlation giúp đo **cửa sổ quyền tồn dư**, nhưng phải có policy/PEP để chặn thực tế.

## 14. Leaver: correlation từ offboarding tới verified deny

Với Leaver, hệ thống cần tìm **tất cả đường truy cập** mà subject vẫn có: IdP/SSO, refresh/access tokens, app-local accounts, direct ACL, SaaS PAT, VPN, PAM, database roles, workload secrets do người đó điều khiển.

### Lifecycle evidence tree

~~~text
LEAVER event + verified subject + effectiveAt
  ├─ IdP disabled + no new sign-in / token issuance
  ├─ SSO/SP session termination checks
  ├─ Refresh grants revoked
  ├─ Access token current-state/RS checks
  ├─ SaaS SCIM disable + target readback
  ├─ Application-local ACL/role removal
  ├─ PAT/API keys and database/local credentials
  ├─ PAM sessions and privileged activations
  ├─ Repository/vault/CI-CD access to workload secrets
  └─ Verification per required target: DENY + no side effect
~~~

### Những trường hợp cần phân biệt

| Tình huống | Correlation outcome | Không kết luận |
| --- | --- | --- |
| HRIS Leaver effective, IdP disable ACK. | Lifecycle accepted / IdP applied. | Mọi SaaS/API đã từ chối quyền. |
| SCIM 204 trả về, ERP local role còn. | Connector applied but target gap. | “Revoke success 100%”. |
| Refresh token revoked, JWT cũ còn ALLOW. | Partial access containment. | Access token bị vô hiệu tức thời. |
| SaaS PAT còn gọi export. | Residual access / incident candidate. | SSO logout đã giải quyết. |
| API 503 khi verification. | UNVERIFIED (outage). | Authorization đã DENY. |
| Access test DENY đúng, app còn log 401 khác. | Evidence của đường thử cụ thể. | Toàn bộ target coverage nếu chưa kiểm các path khác. |
| Owner nhân viên Leaver nhưng workload vẫn hoạt động hợp lệ. | Transfer service ownership + revoke human access. | Phải tự động xóa ứng dụng đang phục vụ nghiệp vụ. |

### Không để báo cáo che nhánh chưa hoàn tất

Một dashboard nên hiển thị rõ **completed targets, unverified targets, residual ALLOW, policy exception và owner/SLA**, thay vì một cờ tổng hợp “Leaver done” chỉ vì workflow scheduler đã kết thúc.


## 15. SSO, OAuth/OIDC, SAML và correlation của session/token

Đối với đăng nhập và gọi API, cần tránh đồng nhất **IdP session, Service Provider session, OAuth authorization grant, refresh token, access token** và business transaction. Mỗi đối tượng có vòng đời và nguồn log khác nhau.

~~~mermaid
sequenceDiagram
    participant U as Human user
    participant APP as Client / SP
    participant IDP as IdP / Authorization Server
    participant RS as Resource Server / API
    participant AUD as Audit
    U->>APP: Mở ứng dụng
    APP->>IDP: Authorization / SSO request
    IDP->>AUD: AUTHN event + IdP session reference
    IDP-->>APP: Code/assertion theo flow
    APP->>IDP: Token request nếu OAuth/OIDC
    IDP-->>APP: Access token + optional refresh token
    APP->>RS: Resource request + access token
    RS->>AUD: TOKEN_VALIDATED / AUTHZ_DECISION
    RS-->>APP: Business outcome
~~~

### Chuỗi correlation tối thiểu

| Sự kiện | Trường nên liên kết | Tránh nhầm |
| --- | --- | --- |
| AUTH_STARTED | IdP issuer, client, auth requestRef, trace. | User đã xác thực thành công. |
| AUTH_SUCCESS | Issuer+subject, auth method, sessionRef, client, occurredAt. | Tất cả apps đã có session. |
| MFA_CHALLENGE / STEP_UP | Subject, session, challengeRef, assurance context. | MFA đủ thay SoD/authorization. |
| OIDC_CODE_EXCHANGED | Client, grantRef, token issuanceRef, audience/scopes. | Authorization code/ID token là access token của API. |
| TOKEN_ISSUED | Issuer, subject/client, protected tokenRef, audience, exp. | RS đã thực sự thấy token. |
| API_AUTHZ_ALLOW/DENY | RS, trusted subject, action, resource, tokenRef nếu có, policyVersion. | Chỉ cần token hợp lệ là action được phép. |
| LOGOUT/SESSION_TERMINATED | IdP/SP sessionRef, action scope. | Mọi access token bị revoke toàn cục. |

### Liên kết theo OIDC

Một cặp **issuer + sub** thường cần được xử lý theo đúng hợp đồng OIDC, kết hợp client/sector nếu provider dùng pairwise subjects. Không dùng email để kết luận subject trong hai clients là cùng một tài khoản nếu chưa có authoritative mapping.

### Liên kết theo SAML

SAML có **assertion/response/request IDs, IdP/SP entity IDs và NameID** theo format. Một **transient NameID** không ổn định cho toàn bộ vòng đời account; việc mapping sang target account phải có contract/provenance. Không log raw SAML assertions, vì chúng có thể chứa thuộc tính nhạy cảm và bằng chứng xác thực.

### Token ID và bảo vệ credential

Nếu token có jti và issuer cho phép correlation theo protected reference, log metadata đã được kiểm chứng. Không ghi bearer token thô để dễ join. Nếu phải trích token reference, dùng **identifier an toàn hoặc HMAC có khóa quản lý** theo policy; cần xử lý khả năng tokenRef không tồn tại và vòng đời khóa tương quan.

## 16. SCIM provisioning: correlation ACK, readback và effective access

SCIM là cơ chế quản lý Users/Groups, nhưng **một HTTP 200/204 không phải bằng chứng mọi quyền truy cập thực tế đã mất**. Ngoài SCIM, target có thể có roles, ACL, OAuth sessions hoặc API keys độc lập.

### Chuỗi thao tác nên theo dõi

~~~text
IGA event:
  accessRemovalOperationId = op-revoke-42
  targetAccountId = finance-saas-user-1057
  entitlement = FinanceCreator

Connector:
  attemptId = op-revoke-42-attempt-1
  SCIM PATCH /Users/{targetId} or group membership update
  response status = 204

Target:
  change event / target readback
  current group membership = removed

PEP:
  user tries payment.create using old session/token
  decision = DENY or ALLOW

Verification:
  verifiedAt + action + reason + no side effect
~~~

### Những trường dễ gây kết luận sai

- **operationId** phải ổn định qua retry; **attemptId** thay đổi để điều tra số lần gửi.
- **Target account ID** do target trả về phải được nối với canonical subject bằng mapping đã xác minh.
- **IdP group removed** và **app-local permission removed** là hai event khác nhau.
- **HTTP success** cho biết connector xử lý request theo hợp đồng, không tự chứng minh PEP đã chặn quyền.
- **SCIM bulk/partial failures** phải theo dõi từng item, không chỉ HTTP status của batch tổng.
- **Rate limiting và retry** có thể làm một operation hoàn tất muộn; không lấy request timestamp làm appliedAt.
- **SCIM active=false** không bảo đảm access token của mọi API và local PAT bị vô hiệu tức thì.
- **Out-of-band manual role grants** ở target có thể khiến desired state và actual state khác nhau.

### Bằng chứng ba tầng

| Tầng | Bằng chứng | Trạng thái trung thực |
| --- | --- | --- |
| Connector command | PATCH/DELETE request + target ACK. | REQUEST_ACCEPTED/APPLIED theo contract. |
| Configuration readback | Membership/role/account status được đọc lại. | TARGET_STATE_CONFIRMED. |
| Enforcement test | API/PEP DENY action đã thu hồi trong scope. | VERIFIED_DENY nếu có positive control và no side effect. |

Một hệ thống không hỗ trợ readback hoặc probe phải được ghi **UNVERIFIED** và có kế hoạch bù trừ; không tự nâng lên verified bằng cách chờ cố định vài phút.

## 17. Access request, approval và review campaign: tìm đúng trách nhiệm

Không chỉ subject cần được tương quan. Quy trình cấp quyền có **người yêu cầu, người hưởng quyền, người phê duyệt, người thực thi và người xác minh**, các vai trò này không được âm thầm gộp thành một principal.

| Vai trò | Trường event | Ví dụ |
| --- | --- | --- |
| **Requester** | requesterSubjectRef. | Nhân viên gửi yêu cầu mở quyền. |
| **Beneficiary** | beneficiarySubjectRef. | Người/tài khoản sẽ nhận quyền. |
| **Approver** | approverSubjectRef, approvalDecisionRef. | Manager hoặc data owner theo policy. |
| **Provisioner** | executorPrincipalRef, connectorRunRef. | IGA service principal áp quyền. |
| **Policy owner** | policyId/version, ownerRef. | IAM/Security chủ trì rule. |
| **Verifier** | verifierPrincipalRef, evidenceRef. | Test worker hoặc auditor độc lập. |

### Ví dụ tự phê duyệt

~~~text
accessRequestId = ar-2026-41
requester = person-19
beneficiary = person-19
approver = person-19
entitlement = finance.admin
decision = APPROVED
~~~

Trong một chính sách cấm self-approval, correlation engine cần phát hiện **requester/beneficiary và approver trùng stable subject**, bất kể request/approval có hai trace IDs khác nhau. Nếu app chỉ nối approval theo “managerEmail” có thể bị bỏ lọt khi email alias hoặc tên hiển thị khác.

### Quyền thay đổi sau approval

Một request được duyệt role READ nhưng connector thực thi role ADMIN là vấn đề **approved-vs-applied delta**. Correlation phải lưu **approved snapshot/digest, entitlement version, target readback** để phát hiện grant sai. Một log “approval success” không biện minh cho mọi quyền mà target đang thực thi.

### Access review nhiều tháng

Một campaign review có thể trải nhiều ngày, nhiều reviewer, nhiều app và nhiều operations. **campaignId** liên kết chiến dịch, **reviewItemId** liên kết entitlement của từng subject, **decisionId** liên kết lựa chọn, còn **operationId** liên kết việc revoke/provision. Đừng dùng một correlationId duy nhất làm idempotency key cho cả campaign.

## 18. RBAC/ABAC, PEP và log quyết định quyền

**RBAC** xác định quyền theo role; **ABAC** thêm điều kiện theo subject/resource/environment. Khi API trả ALLOW/DENY, cần ghi **những tham chiếu đã dùng để ra quyết định** mà không phát tán dữ liệu nhạy cảm.

### Mẫu event quyết định

~~~json
{
  "eventType": "AUTHZ_DECISION",
  "eventId": "evt-authz-991",
  "correlationId": "corr-pay-2026-155",
  "requestId": "req-api-331",
  "resourceServer": "finance-api",
  "actor": {
    "authority": "corporate-idp",
    "subjectRef": "person-4821"
  },
  "action": "payment.approve",
  "resourceRef": "payment-2026-155",
  "tenantRef": "tenant-vn",
  "evaluatedPolicy": {
    "policyId": "finance-approval",
    "version": "7"
  },
  "effectiveRoleRef": "FinanceApprover",
  "decision": "DENY",
  "reasonCode": "SOD_SELF_APPROVAL",
  "resourceStateRef": "payment-version-18",
  "sideEffectsCommitted": false,
  "occurredAt": "2026-11-23T02:03:42Z"
}
~~~

### Nên ghi gì, không nên ghi gì?

- **Nên:** policy ID/version, action/resourceRef, tenant, trusted actor, evaluated condition references/reasonCode, ALLOW/DENY/INDETERMINATE, request/transaction ID.
- **Tránh:** full payment data, patient data, secrets, raw access token, unredacted attributes, password, MFA seed.
- **Nếu ABAC phụ thuộc dynamic attributes:** log **protected value reference/attribute version** hoặc một phần metadata cần kiểm toán; không sao chép toàn bộ profile.
- **Nếu có nhiều PDP/PEP:** log **policy decision** ở PDP và **enforced outcome** ở PEP để thấy chênh lệch.
- **Nếu PEP chưa đạt transaction commit:** log thêm business outcome/side effects từ domain service; “authorization allowed” không tự là “payment approved”.
- **Nếu PEP bị bypass bởi background worker:** cần phát hiện path thiếu event và kiểm từ business transaction/audit khác.

### Quy tắc SoD theo giao dịch

Một người có thể không còn role Creator nhưng vẫn là **createdBy** của payment lịch sử. Correlation phải nối **transaction actor history** với authorization event, không chỉ lịch sử cấp role. Dùng stable principal IDs, không so email do client khai.

## 19. Service account, workload identity và delegated actions

Log correlation cho **non-human identity** khó hơn vì một service principal có thể xử lý hàng nghìn request thay các người dùng hoặc chạy độc lập không có user.

| Danh tính/ngữ cảnh | Câu hỏi cần giải | Ví dụ |
| --- | --- | --- |
| **Technical actor** | Credential/principal nào thực sự gọi API? | finance-report-worker-prod. |
| **Originating human actor** | Có người yêu cầu thao tác này không? | person-4821 khởi chạy job. |
| **Delegation context** | Workload có hành động thay user qua grant hợp lệ không? | OBO/token exchange, verified user. |
| **Runtime provenance** | Pod/VM/CI runner có nằm trong trust domain được phê duyệt? | Namespace + ServiceAccount + issuer. |
| **App owner** | Ai chịu trách nhiệm vòng đời? | finance-platform team. |
| **Affected subject** | Workload đang thay đổi account của ai? | user-target-208. |
| **Resource target** | Action nào ở API/DB/tenant? | reports.read tenant VN. |

### Minh họa event có cả người dùng và workload

~~~json
{
  "eventType": "IAM_ROLE_PROVISIONED",
  "actor": {
    "principalType": "WORKLOAD",
    "principalRef": "iga-connector-prod"
  },
  "initiator": {
    "principalType": "HUMAN",
    "principalRef": "person-4821",
    "delegationStatus": "VERIFIED"
  },
  "subject": {
    "principalType": "HUMAN",
    "principalRef": "person-7702"
  },
  "target": {
    "app": "erp",
    "role": "InvoiceReader"
  },
  "approvalRef": "ar-208",
  "operationId": "op-grant-208"
}
~~~

**Không tự điền initiator là owner của service account** nếu job chạy từ scheduler không có human initiator. Khi chỉ có business sponsor, hãy ghi **sponsor/owner** khác với **actor thực**. Nếu user context đến từ header không xác thực, phải đánh dấu UNTRUSTED, không dùng làm actor để kiểm SoD.

### Workload tokens và trust

Khi OAuth client credentials hoặc workload federation cấp token cho job, sự kiện issuance nên liên kết **issuer, client/service principal, audience, grant ref, workload subject và trust policy version**. Nếu job bị decommission nhưng old trust vẫn có thể cấp token, correlation phải phát hiện **new token issuance after decommission**, không chỉ việc principal biến mất trong directory.

## 20. Correlation qua batch jobs, cron và CI/CD

Một batch job có thể sử dụng:
- **Scheduler/control-plane identity** để thay đổi lịch hoặc tạo Job.
- **Runtime principal** (OS account/Kubernetes ServiceAccount) để chạy code.
- **Downstream client/service principal** để gọi API/DB.
- **Human owner/operator** thay đổi job hoặc xử lý incident.

Các ID này phải có quan hệ rõ; một **jobRunId** khác với một **business idempotency key**, vì cùng business operation có thể có nhiều retries.

### Ví dụ log retry

~~~text
businessOperation = settle-20261123-vn
jobRunId = batch-run-910
attemptId = try-1
result = TIMEOUT_AFTER_REQUEST

businessOperation = settle-20261123-vn
jobRunId = batch-run-911
attemptId = try-2
result = ALREADY_COMMITTED
reconciliationEvidence = settlement-ref-581
~~~

Nếu hệ thống không nối attempts bằng **businessOperation/idempotencyKey**, SIEM có thể xem là hai giao dịch độc lập. Tuy nhiên **có cùng idempotency key không tự chứng minh phía ngân hàng/DB đã bảo đảm exactly-once effect**; phải có transaction/reconciliation evidence.

### CI/CD và quyền điều khiển

Log phải liên kết **repository commit, release approval, pipeline run, workload principal, trust binding và deployment outcome**, để kiểm tra người sửa pipeline có thể tự tạo/trình token và bỏ qua SoD hay không. Không ghi GitHub/GitLab token hoặc cloud STS credential thô.

## 21. Pipeline thu thập, chuẩn hóa và lưu trữ logs

Một kiến trúc correlation điển hình gồm **producer instrumentation → secure collector/agent → normalizer/enricher → event store/SIEM → query/detection → audit evidence**.

~~~mermaid
flowchart LR
    SRC["HRIS, IGA, IdP, SCIM, App, API"] --> COL["Collector / Ingestion"]
    COL --> VAL["Schema validation + provenance"]
    VAL --> RED["Sensitive-field redaction / classification"]
    RED --> ENR["Identity link + context enrichment"]
    ENR --> STORE["Protected event store / SIEM"]
    STORE --> DET["Detections / Correlation queries"]
    DET --> CASE["Incident / Remediation case"]
    STORE --> AUD["Audit evidence / retention"]
~~~

### Các yêu cầu cần bảo đảm

1. **Data loss awareness:** producer/collector có thể mất log, nên theo dõi gaps, backlog, dropped events và coverage.
2. **At-least-once delivery:** bản ghi có thể trùng; cần **eventId deduplication** nhưng không xóa các attempts thực sự khác nhau.
3. **Provenance:** xác minh nguồn/connector (mTLS, agent identity, signature/hệ thống tin cậy khi áp dụng) trước khi dùng event quyết định incident.
4. **Schema validation:** unknown eventType/version không được im lặng gán nghĩa mới.
5. **Redaction:** hạn chế secret/PII tại điểm thu sớm; không chỉ xóa khỏi dashboard còn để raw token trong data lake.
6. **Integrity:** RBAC cho ingest/query/admin, retention/immutability/WORM hoặc tamper-evidence theo risk.
7. **Time quality:** giữ occurredAt và ingestedAt; ghi clock drift/late event.
8. **Partition/index:** query theo tenant/issuer/correlationId/resourceRef, không làm lộ dữ liệu nhiều tenant.
9. **Access reviews:** người quản trị log không mặc nhiên có quyền sửa policy hoặc xóa chứng cứ của chính họ.
10. **Resilience:** khi SIEM down, hệ thống có buffering/failure telemetry và kế hoạch replay, nhưng không bỏ qua authz nếu log lỗi.

### Không biến SIEM thành “source of truth” để cấp quyền

Event store thường là **bản sao quan sát** có độ trễ. Nó phù hợp tìm dấu hiệu, điều tra, đối soát; **authorization runtime** cần nguồn quyền hiện hành và semantics riêng. Đừng dùng “chưa thấy REVOKE event trong SIEM” để tự cấp lại quyền, hoặc “đã có REVOKE event” để suy API đang DENY.

## 22. Tính toàn vẹn, quyền riêng tư và giới hạn giữ log

Identity logs có thể chứa **personal data, device information, địa chỉ mạng, sự kiện MFA, role nhạy cảm và metadata về quan hệ lao động**. Correlation tăng giá trị phân tích nhưng cũng tăng khả năng liên kết dữ liệu cá nhân, nên cần **purpose limitation, data minimization, access control và retention** theo chính sách/pháp luật áp dụng.

### Một số biện pháp

| Biện pháp | Mục đích | Lưu ý |
| --- | --- | --- |
| **Stable internal refs** | Join events không cần lộ email đầy đủ. | Vẫn có thể là personal data nếu liên kết được. |
| **HMAC/keyed pseudonymization** | Tạo protected correlation refs giữa các nguồn được cho phép. | Cần key rotation/version; đừng dùng hash trần với dữ liệu ít entropy như email. |
| **Token/secret redaction** | Tránh logs thành kho credential. | Redaction phải có cả traces, dumps, edge logs. |
| **Field-level access/RBAC** | SOC xem signals, auditor xem evidence, support chỉ xem tối thiểu. | Không chia sẻ mọi raw logs theo convenience. |
| **Tenant isolation** | Không cho analyst tenant A query dữ liệu tenant B. | Kiểm cả index/query joins, exports, dashboards. |
| **Append-only/tamper-evidence** | Phát hiện sửa/xóa evidence trái phép. | Immutable storage cũng cần key/role governance. |
| **Retention/deletion policy** | Không giữ raw authentication data vô hạn. | Cần legal hold khi phù hợp, tách audit facts khỏi payload. |
| **Access logging cho chính log store** | Biết ai tra cứu/xuất dữ liệu identity logs. | SoD giữa production admin và audit admin. |

### Pseudonymization không tự là ẩn danh hoàn toàn

Ngay cả khi subjectRef được chuyển thành HMAC, một analyst có quyền truy cập mapping/các trường giàu ngữ cảnh vẫn có thể nhận ra người. Vì vậy không được tuyên bố dữ liệu đã “anonymous” chỉ vì không còn email. Key rotation cần cân bằng **khả năng join lịch sử** với giới hạn truy cập và mục đích sử dụng; bảo vệ khóa correlation như tài sản nhạy cảm.

### Không ghi bí mật xác thực

**Không log** password, password reset token, OTP, MFA seed, access/refresh token, raw session cookie, client secret, private key, API key hay full SAML assertion. Nếu cần liên kết token issuance và usage, hãy dùng **issuer-bound protected reference** theo thiết kế và chỉ ghi metadata được phép.


## 23. Phát hiện chuỗi hành vi đáng ngờ bằng correlation rules

Một correlation rule thường kết hợp **sự kiện JML, quyết định quyền và hành động trên tài nguyên**. Các quy tắc phải có **điều kiện thời gian, nguồn tin cậy, deduplication, suppression và triage logic** để không tạo vô số cảnh báo sai.

| Rule | Tín hiệu tương quan | Ý nghĩa |
| --- | --- | --- |
| **Leaver access after effectiveAt** | HR_LEAVER hiệu lực và API_AUTHZ_ALLOW của cùng verified subject ở required RS sau mốc đó. | Quyền tồn dư có thể đang được sử dụng. |
| **Mover old-role usage** | ROLE_REVOKE_REQUIRED và action thuộc permission cũ vẫn ALLOW. | Stale token, ACL, policy cache hoặc target drift. |
| **New token after disable** | IDP_DISABLED/CLIENT_DISABLED rồi TOKEN_ISSUED ngoài ngoại lệ đã duyệt. | Issuance policy không đồng bộ, trust khác hoặc event chronology sai. |
| **Self-approval** | Requester/beneficiary và approver trùng stable subject theo rule. | Vi phạm SoD approval. |
| **Creator approves own payment** | PAYMENT_CREATED và PAYMENT_APPROVED cùng actor/resource theo nghiệp vụ. | Transaction-level SoD violation candidate. |
| **Service principal access after decommission** | APP_DECOMMISSIONED và token issuance/API_ALLOW của workload cũ. | Orphaned credential/trust. |
| **Privileged grant without approval** | ROLE_GRANTED ở target không có approved snapshot hợp lệ cùng scope. | Out-of-band grant hoặc audit gap. |
| **SCIM ack but no target change** | PATCH_ACKED rồi readback vẫn quyền cũ quá SLA. | Connector success không phản ánh actual state. |
| **SCIM retry flood** | Một operationId có nhiều attempts/429/5xx, chưa VERIFIED. | Backlog, rate limiting hoặc mất tiến độ. |
| **Impossible-looking session sequence** | SessionId được dùng sau logout hoặc từ nhiều client contexts. | Có thể token/session tồn dư hoặc mapping sai; cần điều tra. |
| **Audit tampering** | Logging config changed/deletion attempts gần privileged actions. | Khả năng che dấu dấu vết; cần provenance và role context. |
| **Unresolved account mapping** | Active targetAccountId không gắn verified subject/owner. | Orphan identity, không được gắn nhầm người khác. |

### Thứ tự phát hiện

1. **Chọn source of truth** cho trigger: HRIS effectiveAt, IGA revision, target API outcome.
2. **Xác định stable join key**, gồm authority/tenant/time validity.
3. **Xác định cửa sổ thời gian** và thời gian chờ ingestion/propagation phù hợp.
4. **Kiểm loại event và phiên bản schema** trước khi join.
5. **Phân biệt ATTEMPT, ACK, APPLIED, VERIFIED**, không gộp.
6. **Đối chiếu exception/maintenance windows** đã được phê duyệt, không bỏ qua hard SoD.
7. **Yêu cầu chứng cứ outcome**: ALLOW ở PEP + side effect nếu kết luận vi phạm thành công.
8. **Phát cảnh báo có context tối thiểu**: subjectRef, target, action, eventRef, evidenceRef, owner.
9. **Suppress duplicates** bằng business incident key, nhưng giữ mọi attempts có ý nghĩa.
10. **Học từ false positives** và cập nhật policy/mapping, không chỉ tắt detection.

### Không suy đoán gian lận từ một deny event

Một AUTHZ_DENY cho user Leaver có thể cho thấy kiểm soát đang hoạt động, không phải user đã truy cập thành công. Một event AUTHZ_ALLOW cho resource ngoài scope phải được điều tra theo **nguồn actor/resource đáng tin**. Sự kiện “insufficient scope” có thể là client lỗi chứ chưa phải tấn công.

## 24. SQL: nối sự kiện JML với API decisions

Để minh họa thuật toán, giả định có hai bảng **normalized_identity_event** và **api_authorization_event**, mỗi bảng đã được:
- Schema-normalized và identity mapping xác minh.
- Tách theo tenant/authority; subject references không bị dùng nhầm giữa issuers.
- Giữ occurredAt, observedAt, effectiveAt, event IDs và policy version.
- Phân loại decision/authn result theo semantics của nguồn.

### Schema logic tối thiểu

~~~sql
-- Pseudocode SQL theo cú pháp gần PostgreSQL.
-- Tên bảng/kiểu dữ liệu là minh họa, không phải schema chuẩn của SIEM.

-- normalized_identity_event:
-- event_id, event_type, event_revision,
-- subject_authority, tenant_id, canonical_subject_id,
-- correlation_id, target_id, entitlement_id,
-- effective_at, occurred_at, observed_at

-- api_authorization_event:
-- event_id, request_id, resource_server, target_id,
-- subject_authority, tenant_id, canonical_subject_id,
-- action_id, resource_id,
-- decision, occurred_at, observed_at, correlation_id
~~~

### Tìm API ALLOW sau Leaver effectiveAt

~~~sql
WITH latest_leaver AS (
    SELECT
        subject_authority,
        tenant_id,
        canonical_subject_id,
        MAX(effective_at) AS leaver_effective_at
    FROM normalized_identity_event
    WHERE event_type = 'HR_LEAVER_EFFECTIVE'
    GROUP BY subject_authority, tenant_id, canonical_subject_id
)
SELECT
    l.canonical_subject_id,
    l.tenant_id,
    l.leaver_effective_at,
    a.resource_server,
    a.action_id,
    a.resource_id,
    a.event_id AS api_event_id,
    a.occurred_at AS api_occurred_at
FROM latest_leaver l
JOIN api_authorization_event a
  ON a.subject_authority = l.subject_authority
 AND a.tenant_id = l.tenant_id
 AND a.canonical_subject_id = l.canonical_subject_id
 AND a.occurred_at >= l.leaver_effective_at
WHERE a.decision = 'ALLOW';
~~~

### Những điều truy vấn này *chưa* chứng minh

- Dùng **MAX(effective_at)** không xử lý đầy đủ rehire hoặc employment relationship mới. Với production, dùng **temporal valid intervals/current lifecycle revision** và đối chiếu đúng employment/account epoch.
- Một user có thể có approved exception/legal hold hay một principal được mapping lại; cần kiểm **policy context**, không tự coi mọi dòng là breach đã xác nhận.
- API log **ALLOW** thường là quyết định authorization, không chứng minh business transaction đã commit; khi cần cần join **TRANSACTION_COMMITTED**.
- Nếu log API thiếu, truy vấn trả rỗng **không chứng minh Leaver đã bị chặn**.
- Nếu clock lệch, biên effectiveAt cần được xét theo uncertainty và sequence evidence.
- Nhiều target/local accounts có thể không cùng canonical subject khi link chưa VERIFIED; phải hiển thị coverage gap thay vì bỏ qua chúng.

### Tránh Cartesian join và sự kiện trùng

Event streams có thể có retries và duplicate delivery. Không join **chỉ theo subject** mà không có **target/tenant/time/policy filter**. Khi cần chọn một event, ưu tiên **stable eventId + source/version + business operation**, không tự DISTINCT toàn bộ bản ghi làm mất những attempts quan trọng.

## 25. SQL: so sánh yêu cầu thu hồi, target readback và verification

Giả sử có bảng **revocation_operation** và **revocation_target_evidence** lưu từng hành động thu hồi theo target:

~~~sql
-- Pseudocode PostgreSQL.
-- revocation_operation:
-- operation_id, correlation_id, canonical_subject_id,
-- target_id, entitlement_id, effective_at, sla_deadline

-- revocation_target_evidence:
-- evidence_id, operation_id, target_id, evidence_type,
-- status, observed_at, verified_at, source_event_id

SELECT
    o.operation_id,
    o.correlation_id,
    o.canonical_subject_id,
    o.target_id,
    o.entitlement_id,
    o.effective_at,
    MAX(CASE
          WHEN e.evidence_type = 'CONNECTOR_ACK'
          THEN e.observed_at
        END) AS last_connector_ack,
    MAX(CASE
          WHEN e.evidence_type = 'TARGET_READBACK'
               AND e.status = 'REMOVED'
          THEN e.observed_at
        END) AS target_removed_at,
    MIN(CASE
          WHEN e.evidence_type = 'EFFECTIVE_ACCESS_PROBE'
               AND e.status = 'VERIFIED_DENY'
          THEN e.verified_at
        END) AS first_verified_deny_at
FROM revocation_operation o
LEFT JOIN revocation_target_evidence e
  ON e.operation_id = o.operation_id
 AND e.target_id = o.target_id
GROUP BY
    o.operation_id, o.correlation_id,
    o.canonical_subject_id,
    o.target_id, o.entitlement_id,
    o.effective_at;
~~~

### Diễn giải

- **last_connector_ack** là lúc connector nhận ack; không chứng minh PEP đã từ chối.
- **target_removed_at** là mốc target configuration được đọc lại; có thể chưa chặn token/session cũ.
- **first_verified_deny_at** là bằng chứng lần đầu probe DENY trên đường đã kiểm. Để chứng minh **đúng sau toàn bộ required targets**, cần có inventory paths và coverage, không chỉ một evidence record.
- Dùng **MIN** trong ví dụ giúp tìm lần đầu, nhưng production có thể cần kiểm **sustained DENY**, target node coverage, mọi entitlements liên quan và thời gian sau rollback/regrant.
- Dòng có NULL first_verified_deny_at không phải success; cần trạng thái **UNVERIFIED**.
- Để tính SLA, phải so effectiveAt với **verification hợp lệ** theo chuẩn thời gian/clock quality, không với connector ACK.

### Phân biệt loại verification

Một HTTP 401 có thể là token expired; nếu policy cần chứng minh **revocation-before-expiry**, phải test token còn hạn và điều kiện khác hợp lệ. Một HTTP 503 không tính policy DENY. Một thử nghiệm chặn tại gateway không tự bao phủ đường API background bypass gateway.

## 26. Java: structured logging, MDC và truyền correlation context

Trong ứng dụng Java, có thể dùng **SLF4J/structured JSON logging**, MDC và OpenTelemetry để gắn các IDs cho từng request. **Không tin header correlation do client gửi như danh tính**; gateway hoặc middleware phải kiểm ngữ cảnh và phát/tách context phù hợp.

### Middleware/pseudocode cho HTTP request

~~~java
// Pseudocode minh họa; framework/filter classes phụ thuộc hệ thống.
// Trace context cần được xử lý bởi instrumentation/tracer chính thức.
void handleRequest(HttpRequest request, HttpResponse response) {
    String correlationId = trustedCorrelationResolver.resolveOrCreate(request);
    String requestId = trustedRequestIdGenerator.newId();

    try {
        MDC.put("correlationId", correlationId);
        MDC.put("requestId", requestId);

        // Verified principal do middleware xác thực token/session tạo.
        VerifiedPrincipal principal = securityContext.verifiedPrincipalOrNull();

        if (principal != null) {
            MDC.put("principalRef", principal.protectedRef());
            MDC.put("principalType", principal.type());
        }

        downstreamHandler.process(request, response);

        audit.emitStructured(
            "API_REQUEST_COMPLETED",
            correlationId,
            requestId,
            response.statusCode()
        );
    } finally {
        // Thread pools có thể tái sử dụng thread: tránh leakage giữa requests.
        MDC.remove("principalRef");
        MDC.remove("principalType");
        MDC.remove("requestId");
        MDC.remove("correlationId");
    }
}
~~~

### Những điểm phải thực hiện trong hệ thống thật

1. **Không tự tạo trusted principal từ X-User-Id/X-Role header**; chỉ dùng security context đã xác minh.
2. **MDC là thread-local context phổ biến**, không tự truyền an toàn qua reactive streams, completable futures, virtual threads hoặc queue; dùng context propagation phù hợp framework.
3. **Luôn cleanup** khi request kết thúc hoặc có exception, tránh user A bị gắn log của user B trên thread pool.
4. **CorrelationId từ client** có thể bị giả mạo hoặc đụng; đặt giới hạn độ dài/ký tự, namespace/trust và không dùng làm permission proof.
5. **Structured logs** cần loại secrets/PII, escape/encode input để chống log injection.
6. **Audit events** quan trọng phải được ghi qua cơ chế đáng tin, có delivery retry/idempotency và bảo vệ integrity; không phụ thuộc hoàn toàn vào logger debug.
7. **Metrics labels** không nên dùng full principalId/correlationId làm label do cardinality/privacy; dùng protected audit refs ở storage chuyên dụng.
8. **Đừng cho log pipeline failure bypass authorization** của các action quan trọng; xử lý theo risk, có buffering/fail behavior rõ.

### Trace context không thay audit context

OpenTelemetry span context và MDC có thể hỗ trợ diagnostic correlation; nhưng **request state** của Java app khác **business workflow state** trong IGA. Khi gửi queue message, bảo toàn **correlationId/causationId/operationId** ở envelope nghiệp vụ, không trông chờ MDC tự tồn tại trên worker khác.

## 27. Java: propagation qua message queue, idempotency và event envelope

Một listener xử lý SCIM revoke cần ghi **operation ID ổn định** và **attempt ID riêng cho lần xử lý**:

~~~java
record RevokeMessage(
    String messageId,
    String correlationId,
    String causationId,
    String operationId,
    String subjectRef,
    String targetAccountRef,
    String entitlementRef,
    long lifecycleRevision
) {}

void processRevokeMessage(RevokeMessage msg) {
    String attemptId = attemptIds.newId();

    try (CorrelationScope ignored = correlationScopes.open(
            msg.correlationId(), msg.operationId(), attemptId)) {

        if (!trustedMessageValidator.isAuthenticAndAuthorized(msg)) {
            audit.emit("REVOKE_MESSAGE_REJECTED",
                msg.operationId(), attemptId, "UNTRUSTED");
            return;
        }

        if (!currentLifecycle.isRevisionCurrent(
                msg.subjectRef(), msg.lifecycleRevision())) {
            audit.emit("REVOKE_MESSAGE_IGNORED",
                msg.operationId(), attemptId, "STALE_EVENT");
            return;
        }

        if (idempotencyStore.isAlreadyApplied(msg.operationId())) {
            audit.emit("REVOKE_DUPLICATE_ACKNOWLEDGED",
                msg.operationId(), attemptId, "NO_NEW_EFFECT");
            return;
        }

        ScimAck ack = connector.removeEntitlement(
            msg.targetAccountRef(), msg.entitlementRef());

        audit.emit("SCIM_REVOKE_ACKED",
            msg.operationId(), attemptId, ack.statusCategory());

        // Target readback và verification là bước riêng.
        reconciliation.enqueueVerification(
            msg.operationId(), msg.targetAccountRef(),
            msg.entitlementRef());
    }
}
~~~

### Giới hạn của pseudocode

- **Không được ghi idempotency COMPLETE trước khi thật sự đạt trạng thái được định nghĩa**, kể cả trường hợp target đã apply nhưng connector trả timeout.
- Cần transaction/outbox hoặc cơ chế đáng tin để **không mất event** giữa việc apply target và ghi audit/verification.
- Cần chứng minh **event ordering** bằng revision/source-of-truth và bảo vệ khỏi regrant event đến trễ.
- **Không dựa vào exact string status** mà không có target semantics; 204 không tương đương PEP DENY.
- Nếu message metadata không tin cậy, correlationId và causationId chỉ dùng chẩn đoán chứ **không được tự nâng quyền**.
- Với async executor/queue, MDC/OpenTelemetry context cần được thiết lập/cleanup **riêng cho mỗi attempt**.


## 28. SIEM correlation logic: từ rule đến incident có bằng chứng

Nền tảng SIEM có cú pháp khác nhau (KQL, SPL, SQL, EQL, OTel query và ngôn ngữ của nhà cung cấp). Thay vì đưa một truy vấn vendor-specific dễ dùng sai, có thể diễn tả **algorithm** bằng các bước:

~~~text
INPUT:
  authoritativeLifecycleEvents
  verifiedIdentityLinks
  targetApiAuthorizationEvents
  requiredTargetInventory
  approvedExceptions

FOR EACH latest valid LEAVER event with effectiveAt:
    subjectKey = authority + tenant + stableSubjectId + lifecycleEpoch

    IF identity link missing/ambiguous:
        OPEN finding "UNVERIFIED_IDENTITY_MAPPING"
        CONTINUE

    FILTER target events:
        subjectKey matches by verified temporal mapping
        event.occurredAt >= effectiveAt - boundedClockUncertainty
        event.source is trusted
        event.type is recognized

    IF event.decision == ALLOW for prohibited action:
        OPEN incident candidate "RESIDUAL_ACCESS"
        ATTACH event evidence, scope and target

    FOR EACH required target and entitlement:
        CHECK validated revoke + readback + effective DENY evidence
        IF missing:
            MARK target UNVERIFIED
        IF stale ALLOW:
            MARK target REMEDIATION_REQUIRED

    COMPUTE verified coverage and SLA with clock quality
    DO NOT set overall VERIFIED until all required targets pass
~~~

### Những điểm cần phân biệt

- **Event-time processing** có thể cần chờ late arrivals (watermark) để giảm false positives. Nhưng không nên trì hoãn **critical containment** chỉ để đợi đủ mọi log.
- **Correlations theo thời gian** phải giới hạn window, tránh gắn một API request cách event hai năm vào cùng incident khi user đã rehire.
- **Causal evidence** qua operationId/approval/resource history đáng tin hơn việc chỉ có subject và timestamp gần nhau.
- **Partial logging** cần hiển thị như coverage gap, không coi missing events là hành vi không xảy ra.
- **Approved exceptions** phải có policy, owner, scope, TTL; không tự miễn SoD non-waivable.
- **Alert aggregation** dùng incident key ổn định, nhưng vẫn giữ từng denied/allowed attempts, target node và state transitions.

### Chuẩn hóa reason code

Cần phân biệt ít nhất:
- **INVALID_TOKEN/UNAUTHENTICATED**.
- **INSUFFICIENT_SCOPE/ROLE**.
- **SUBJECT_DISABLED/LEAVER**.
- **TENANT_MISMATCH/RESOURCE_DENIED**.
- **SOD_CONFLICT**.
- **PEP_UNAVAILABLE/INDETERMINATE**.
- **SYSTEM_ERROR/TIMEOUT**.
- **POLICY_ALLOW và BUSINESS_COMMITTED** là hai loại kết quả khác nhau.

Một HTTP **503** hoặc lỗi network không được đánh đồng với **policy DENY**. Một request được ALLOW nhưng transaction rollback cũng không đồng nghĩa hành động nghiệp vụ đã thành công.

## 29. Tình huống thực hành: Mover còn quyền từ token cũ

### Bối cảnh

Nhân viên **Mai** chuyển từ Payment Operations sang Payment Control. Policy yêu cầu role Creator cũ bị thu hồi trước khi Approver mới được activate trong tenant VN. Source HRIS xác định hiệu lực Mover **09:00**.

### Chuỗi sự kiện được quan sát

| Giờ | Hệ thống | Event | Bằng chứng/câu hỏi |
| --- | --- | --- | --- |
| 08:55 | OAuth AS | TOKEN_ISSUED cho Mai với Creator scope, exp 09:25. | TokenRef, issuer, audience Finance API. |
| 09:00 | HRIS | HR_MOVER_EFFECTIVE rev 32. | Stable subject và effectiveAt. |
| 09:00:10 | IGA | ROLE_REVOKE_REQUESTED. | CausationId=HR event, operationId=op-creator-32. |
| 09:01 | IdP | GROUP_REMOVED. | Canonical subject mapping và group version. |
| 09:02 | SCIM | PATCH_ACK 204. | Chỉ là acknowledgment. |
| 09:03 | ERP | ROLE_READBACK_REMOVED. | Direct role/ACL khác còn không? |
| 09:04 | Finance API | API_AUTHZ_ALLOW payment.create bằng token cũ. | Residual access, cần no-side-effect/transaction evidence. |
| 09:05 | IGA | ACTIVATE_APPROVER_BLOCKED vì SoD. | Chặn overlap theo policy. |
| 09:07 | PEP | Current-state policy cập nhật; payment.create DENY. | Verification event + API healthy. |
| 09:08 | IGA | APPROVER_ACTIVATED theo approved scope. | Revalidation quyền hiện hành. |
| 09:09 | Finance API | Mai tự duyệt payment do Mai tạo trước Mover: DENY. | Transaction SoD kiểm resource history. |

### Cách correlation giải thích sự việc

1. **HR event** và các operations dùng cùng subject/business correlation, nhưng mỗi HTTP request có requestId/trace khác nhau.
2. **ACK lúc 09:02** không làm mất quyền ngay vì token/session và PEP policy có vòng đời riêng.
3. **ALLOW lúc 09:04** là bằng chứng quyền Creator còn sử dụng được sau effectiveAt, không phải lỗi “đăng nhập”.
4. **DENY lúc 09:07** giúp xác minh cửa sổ quyền tồn dư đã được đóng trên đường API được test.
5. **SoD transaction** lúc 09:09 vẫn cần dùng createdBy của payment, dù Mai đã đổi role.
6. **Incident/SLA** phải ghi cả thời điểm phát hiện, remediate và verifiedAt; không lấy 09:02 làm thời điểm revoke hiệu lực.

### Outcome

Với scope thử chỉ Finance API, revocation latency theo bằng chứng từ 09:00 đến 09:07 là **7 phút**; kết luận **toàn bộ hệ thống** chỉ hợp lệ khi các required target khác đã có verification phù hợp. Nếu policy cho phép tối đa 5 phút, đây là **SLA breach** mặc dù hiện trạng đã được khắc phục.

## 30. Tình huống thực hành: Leaver với SaaS PAT và account không còn mapping

### Bối cảnh

Nhân viên **An** rời công ty lúc **17:00**. IGA đã disable tài khoản IdP, kết thúc refresh grants, gửi SCIM sang CRM và Finance SaaS. Một legacy integration còn sử dụng **personal access token (PAT)**.

### Điều tra ban đầu

~~~text
17:00  HR_LEAVER_EFFECTIVE(subject=person-330)
17:01  IDP_ACCOUNT_DISABLED(subject=idp-119)
17:02  OAUTH_REFRESH_GRANT_REVOKED(subject=idp-119)
17:04  SCIM_USER_DISABLED(target=crm-user-870)
17:06  SCIM_USER_DISABLED(target=finance-user-201)
17:10  SAAS_API_AUTHZ_ALLOW(action=reports.export,
       targetAccount=legacy-saas-user-77)
~~~

Nếu chưa có **verified temporal link** giữa legacy-saas-user-77 và person-330, engine không nên tự khẳng định hành vi của An chỉ vì email/display name trùng. Nó cần mở **UNVERIFIED_IDENTITY_MAPPING** và điều tra provisioning/account records. Nếu link được xác minh và API event thực sự ALLOW, đây là **residual access**.

### Diễn biến sau khi xác minh

- So sánh **issuer + stable subject**, target account IDs, lịch sử account linking theo thời gian.
- Kiểm PAT local có bị revoke cùng SCIM disable không; nếu không, xử lý PAT ở target.
- Xem action reports.export có thực sự xuất dữ liệu hay chỉ nhận authorization ALLOW.
- Kiểm phiên/app-local ACL/token sessions đã phát còn hoạt động.
- Gỡ quyền former owner trên vault/CI/CD nếu An từng kiểm soát service credentials.
- Dùng safe negative probe sau revoke và positive control cho endpoint hoạt động.
- Giữ audit đầy đủ quyền của An và bảo vệ privacy, không trích PAT thô.

### Kết quả đáng tin

Chỉ khi xác minh mapping, target readback và **API DENY**, mới có evidence đóng đường PAT. Nếu event access lúc 17:10 đến SIEM lúc 17:30, phải dùng **occurredAt** để tính cửa sổ quyền tồn dư, không dùng thời điểm ingest.

## 31. Tình huống thực hành: service account thay mặt người dùng và SoD

### Bối cảnh

Một service principal **finance-approval-bot** gọi Payment API để thực hiện workflow đã được người kiểm soát phê duyệt. Bot có **technical identity**, còn yêu cầu xuất phát từ một human approver.

### Rủi ro log chỉ có client ID

~~~text
API_AUTHZ_ALLOW
  technicalActor = finance-approval-bot
  action = payment.approve
  resource = payment-700
~~~

Log này không đủ để xác định **ai yêu cầu phê duyệt**. Nếu người tạo payment cũng là người gửi yêu cầu cho bot, một hệ thống chỉ so technical actor với createdBy có thể bỏ lọt self-approval.

### Mô hình event tốt hơn

~~~json
{
  "eventType": "PAYMENT_APPROVAL_ATTEMPT",
  "correlationId": "corr-payment-700",
  "operationId": "approve-payment-700-v2",
  "technicalActor": {
    "principalType": "WORKLOAD",
    "principalRef": "finance-approval-bot"
  },
  "initiatingHuman": {
    "principalType": "HUMAN",
    "principalRef": "person-411",
    "contextTrust": "VERIFIED_DELEGATION"
  },
  "resourceRef": "payment-700",
  "resourceCreatedBy": "person-411",
  "ruleVersion": "SOD-SELF-APPROVAL-v3",
  "decision": "DENY",
  "reasonCode": "SAME_BUSINESS_ACTOR",
  "businessEffectsCommitted": false
}
~~~

### Những điều bắt buộc

- Human initiator phải đến từ **delegation context được xác minh**, không phải header tự khai.
- Nếu bot tự chạy theo lịch, **không được bịa human initiator**; dùng business trigger/approval reference thực tế.
- Nếu bot được cấp app-only quyền rộng, authorization layer vẫn cần kiểm **approval chain và resource history** khi nghiệp vụ yêu cầu maker–checker.
- Hai service accounts không mặc nhiên là hai người kiểm soát độc lập; cần xét **người có quyền sửa pipeline, lấy secret hoặc assume cả hai**.
- Log correlation giúp điều tra, nhưng **PEP phải chặn** trường hợp xung đột trước khi payment được duyệt.

## 32. Tình huống thực hành: mất log, replay và event đến trễ

### Bối cảnh

IGA gửi revoke event revision 56, connector gặp lỗi và retry ba lần. Trong lúc đó, nguồn HRIS gửi Leaver revision 57. Một queue replica sau sự cố phát lại Mover revision 56.

~~~text
12:00  HRIS MOVER revision=56
12:01  IGA REVOKE op=revoke-56, attempt=1 -> timeout
12:02  IGA REVOKE op=revoke-56, attempt=2 -> 429
12:03  HRIS LEAVER revision=57
12:04  IdP disabled, Finance API current-state DENY
12:05  Old MOVER revision=56 replayed
12:05  Consumer IGNORED_STALE_EVENT revision=56
12:06  Reconciliation verifies required targets
~~~

### Những câu hỏi cần giải

1. Có thể truy ngược mọi attempts về **một operationId** không?
2. Có giữ **attemptId** riêng để hiểu timeout/429 không?
3. Có xác minh thứ tự theo **source revision** thay vì chỉ timestamp không?
4. Có event **IGNORED_STALE_EVENT** thể hiện không tái cấp quyền không?
5. Có DLQ/backlog metrics và alerts khi thiếu log/ACK không?
6. Nếu revoked action vẫn ALLOW ở một target sau 12:03, có evidence riêng không?
7. Có đủ positive controls để phân biệt target outage với DENY thực?
8. Việc replay làm đổi state hay chỉ tạo duplicate log? Idempotency và reconciliation có đúng không?

Nếu chỉ thấy nhiều dòng PATCH_SENT, hệ thống có thể đếm nhầm là ba lần thu hồi khác nhau. Nếu chỉ giữ latest event và xóa retry history, người vận hành sẽ không giải thích được sự chậm trễ và lý do target từng ở trạng thái partial.


## 33. Ma trận kiểm thử log correlation trong IAM

Các test cần sử dụng **synthetic events, test principals, trusted test timestamps, approved resource probes** và một **test oracle độc lập** từ policy/schema. Không sử dụng token, session hoặc account production thật làm fixture khi chưa được phép.

| ID | Trường hợp | Kết quả mong đợi |
| --- | --- | --- |
| LC01 | HTTP request có correlationId hợp lệ do gateway tạo. | Các logs cùng request mang cùng correlation context. |
| LC02 | Request từ Internet tự gửi traceparent giống một trace quản trị. | Không được suy ra actor/quyền của trace quản trị. |
| LC03 | Correlation header chứa newline/log injection. | Bị giới hạn, sanitize hoặc regenerate; không phá structured log. |
| LC04 | Header correlationId cực dài. | Bị từ chối/chuẩn hóa theo policy, không làm tăng log size vô hạn. |
| LC05 | Hai request độc lập cùng subject trong một phút. | Không gộp thành một business operation nếu thiếu link. |
| LC06 | Một lifecycle workflow fan-out ba target khác nhau. | Cả ba operations nối đúng parent event. |
| LC07 | Một revoke operation retry ba lần. | Một logical operation, ba attempt IDs. |
| LC08 | Duplicate delivery của cùng eventId. | Dedup message, giữ audit attempts và không apply grant hai lần. |
| LC09 | SCIM connector timeout nhưng target đã apply revoke. | Reconciliation đọc lại, không tạo kết luận sai từ timeout. |
| LC10 | SCIM PATCH 204 nhưng target role vẫn còn. | Không VERIFIED; phát hiện mismatch. |
| LC11 | IdP group đã gỡ nhưng app-local ACL còn ALLOW. | Residual access finding và target remediation. |
| LC12 | HRIS Joiner được pre-provision trước effectiveAt. | Không báo vi phạm nếu policy cho phép provisioning sớm; kiểm actual access trước start. |
| LC13 | Joiner account đã active trước business effectiveAt trái policy. | Phát hiện early access theo evidence. |
| LC14 | Mover có token cũ được API ALLOW sau revoke. | Liên kết tokenRef/subject với JML và báo stale authorization window. |
| LC15 | Mover nhận role mới khi role cũ chưa revoke, SSD cấm overlap. | Phát hiện conflict bằng effective rights. |
| LC16 | Mover tự duyệt payment từng tạo trước khi đổi role. | SoD correlation dựa trên resource actor history. |
| LC17 | Leaver có API_AUTHZ_ALLOW sau effectiveAt. | Residual access candidate, đủ target/source context. |
| LC18 | Leaver chỉ có AUTHZ_DENY sau effectiveAt. | Không kết luận breach thành công chỉ từ deny. |
| LC19 | API trả 503 khi verification. | UNVERIFIED; không tính verified DENY. |
| LC20 | API trả 403 nhưng async worker đã tạo file export. | Phát hiện unauthorized side effect qua transaction/audit logs. |
| LC21 | SSO logout thành công nhưng JWT/API vẫn ALLOW. | Phân biệt session logout với token lifecycle. |
| LC22 | OAuth refresh token revoked nhưng access JWT còn hạn. | Không báo all-token revoked nếu RS còn ALLOW. |
| LC23 | SaaS PAT còn hoạt động sau SCIM disable. | Phát hiện credential ngoài OAuth/SCIM. |
| LC24 | IdP user cùng email khác immutable subject sau rehire. | Không ghép hai principal sai thời kỳ. |
| LC25 | User đổi email alias. | Stable subject mapping vẫn liên kết đúng events. |
| LC26 | Hai người dùng chung NAT IP. | Không gộp identity theo IP. |
| LC27 | OIDC pairwise sub khác giữa hai clients. | Chỉ nối khi có verified authoritative mapping. |
| LC28 | SAML transient NameID đổi theo phiên. | Không coi transient ID là stable identity. |
| LC29 | SCIM target account ID trùng số ở hai tenants. | Join có target namespace/tenant, không cross-tenant. |
| LC30 | Service principal app-only gọi API không có human initiator. | Actor là workload, không tự bịa owner làm initiator. |
| LC31 | Service hoạt động OBO có verified user context. | Ghi cả technical actor và human initiator đúng authority. |
| LC32 | Client tự gửi X-User-Id khác actor đã xác thực. | Không dùng header chưa xác minh để gán event. |
| LC33 | Hai service accounts khác tên nhưng cùng operator kiểm soát. | SoD review xét controller/trust graph thực tế. |
| LC34 | OAuth tokenRef/jti thiếu trong API log. | Correlation dùng protected refs khác hoặc đánh dấu coverage limitation. |
| LC35 | JWT token thô bị ghi trong structured logs. | Privacy/security regression FAIL, redaction và incident handling. |
| LC36 | Password reset token hoặc MFA seed xuất hiện trong trace. | FAIL, lọc dữ liệu và đánh giá exposure. |
| LC37 | Trace sampling bỏ request của giao dịch quan trọng. | Audit event vẫn đầy đủ nếu được thiết kế independent. |
| LC38 | Message queue xử lý ở worker khác và mất MDC. | Kiểm context propagation, không gán nhầm subject từ thread trước. |
| LC39 | Java thread pool tái sử dụng thread với MDC cũ. | finally/cleanup ngăn log user A bị gắn user B. |
| LC40 | Out-of-order Mover revision cũ đến sau Leaver. | Stale event bị ignore, audit có reason và không regrant. |
| LC41 | Một producer có clock lệch 4 phút. | Phát hiện uncertainty, không kết luận thứ tự bằng timestamp đơn thuần. |
| LC42 | Event ingested 30 phút sau occurredAt. | Tính timeline theo occurredAt/causation; đo ingestion lag riêng. |
| LC43 | Sự kiện cùng correlationId nhưng khác source/trust domain không hợp lệ. | Không coi là cùng trusted business chain nếu thiếu chứng cứ. |
| LC44 | Business operation kéo dài ba ngày qua 10 traces. | Nối bằng business correlation/causation, không ép cùng traceId. |
| LC45 | Một API trace có nhiều spans. | Phân biệt spanId với business operationId. |
| LC46 | Truy vấn chỉ join subject, bỏ tenant/validity. | Regression phát hiện false join và yêu cầu scoped keys. |
| LC47 | Một target account liên kết lại cho người khác vào ngày sau. | Temporal identity link áp đúng khoảng validFrom/validTo. |
| LC48 | Audit event giả được gửi từ nguồn không tin cậy. | Ingestion provenance validation loại/đánh dấu UNTRUSTED. |
| LC49 | Event schema v2 thêm trường có nghĩa khác. | Version-aware normalization, không im lặng mapping sai. |
| LC50 | Collector downtime làm thiếu logs ở một RS. | Coverage gap/backlog alert; không suy zero violations. |
| LC51 | Logger throughput cao làm drop audit events. | Phát hiện data loss, retry/buffering/incident theo risk. |
| LC52 | SIEM analyst tenant A truy vấn dữ liệu tenant B. | Tenant isolation/RBAC chặn truy cập. |
| LC53 | Người sửa audit config cố xóa logs của chính mình. | SoD/tamper-evidence controls và audit event riêng. |
| LC54 | Event cùng messageId replay do broker. | Dedup/attempt modeling đúng, không ghi hai business outcomes. |
| LC55 | Cùng payment có hai approvals đồng thời. | Correlate transaction version, actor/history và commit outcome. |
| LC56 | Một approval request chỉ có approvalId nhưng không có beneficiary. | UNVERIFIED_MAPPING, không tự gán approver cho người bất kỳ. |
| LC57 | Resource Server policy DENY nhưng gateway trả ALLOW. | Phát hiện PDP-vs-PEP inconsistency và không có side effect. |
| LC58 | Token issued sau APP_DECOMMISSIONED. | Trust/issuer residual finding, verify target authorization. |
| LC59 | Key HMAC correlation rotation làm mất join lịch sử. | Key version/rotation migration có kiểm soát, không mất evidence hợp lệ. |
| LC60 | Mức redaction khác nhau giữa raw log và SIEM dashboard. | Security review kiểm cả raw storage không còn token/secret. |
| LC61 | Verification chỉ thử API một node, node khác stale cache ALLOW. | Chưa VERIFIED toàn required RS coverage. |
| LC62 | Approved exception đã hết TTL nhưng detector tiếp tục suppress. | Exception expiry enforced, tạo finding mới. |
| LC63 | Audit event AUTHZ_ALLOW nhưng business transaction rollback. | Không báo payment thành công nếu thiếu committed event. |
| LC64 | Payment commit thành công nhưng response timeout trước client. | Business outcome dựa on ledger/transaction, không chỉ response. |
| LC65 | Access review item KEEP nhưng target role được gỡ ngoài luồng. | Phát hiện desired-vs-actual drift, tránh regrant không được duyệt. |
| LC66 | SCIM bulk batch có 1 item fail trong 100. | Tách item outcomes và mở remediation cho item fail. |
| LC67 | Legacy account không có authoritative identity mapping. | Ghi UNVERIFIED; không tự xóa từ thống kê. |
| LC68 | Resource probe trả DENY vì target account đang thiếu dữ liệu thử. | Test oracle kiểm đúng nguyên nhân và positive control. |
| LC69 | User còn được phép đọc báo cáo sau Mover, nhưng rule correlation chặn mọi action. | Phát hiện false deny, giới hạn rule theo entitlement bị thu hồi. |
| LC70 | SOAR automation dựa vào correlation candidate để disable principal khác. | Require authority, confidence/evidence và safeguards, không dùng heuristic join làm quyết định tuyệt đối. |

### Phân lớp test

| Lớp | Cần chứng minh |
| --- | --- |
| **Schema/normalization** | Event types, version, required fields, redaction và unknown handling. |
| **Identity linking** | Stable IDs, tenant/issuer namespace, temporal mappings, rehire, alias. |
| **Causality/trace** | CorrelationId/causationId, W3C trace context, queue fan-out, retries. |
| **JML end-to-end** | Joiner activation, Mover overlap, Leaver revoke, session/token residual. |
| **Authorization** | RBAC/ABAC, SoD, trusted actor, effective PEP and side effects. |
| **Fault tolerance** | Out-of-order, duplicate, dropped events, clock skew, SIEM outage. |
| **Privacy/integrity** | No secrets in logs, provenance, tenant access, tamper evidence. |
| **Operational reporting** | Coverage gaps, exact SLA timestamps, reason-coded alerts. |

### PASS cần cả positive lẫn negative

Ví dụ, sau Leaver, API trả DENY khi dùng token cũ nhưng **API đang down**: chưa thể báo SUCCESS. Cần positive control chứng minh target đang hoạt động, rồi negative probe chứng minh policy chặn đúng principal/action. Với giao dịch ghi, phải kiểm **không có unauthorized side effects**.

## 34. KPI và dashboard cho log correlation

| KPI | Định nghĩa | Cách tránh đo sai |
| --- | --- | --- |
| **Event schema coverage** | Tỷ lệ producers phát đúng eventType/version/mandatory fields. | Không lấy “có log text” làm schema coverage. |
| **Correlation link completeness** | Tỷ lệ workflow có đủ required events và valid causation references. | Một correlationId xuất hiện không có nghĩa đủ các bước. |
| **Identity link verification rate** | Tỷ lệ target accounts có verified canonical mapping. | Không chấp nhận email-only link là verified. |
| **Required-target visibility** | Số target/PEP bắt buộc có telemetry và readback/probe. | Missing target không bằng 0 incidents. |
| **Ingestion delay P95/P99** | observedAt - occurredAt trên nguồn có clock đáng tin. | Ghi clock uncertainty và heavy-tailed late events. |
| **Orphan event rate** | Event thiếu parent/business correlation khi kỳ vọng có. | Một số events độc lập không nên bị ép có parent. |
| **Duplicate/attempt ratio** | Delivery duplicates và retries theo operationId/attemptId. | Không gộp cả retry thật thành duplicate. |
| **Revocation verified latency** | verifiedAt - effectiveAt trên required targets. | Không dùng connector ACK hoặc SIEM ingestion timestamp. |
| **Residual access detections** | Verified API ALLOW sau revoke effectiveAt ngoài exception. | Một correlation candidate không luôn là confirmed violation. |
| **Policy-enforcement gap** | PDP DENY nhưng PEP/transaction vẫn thực thi. | Kiểm business side effects, không chỉ HTTP status. |
| **SLA compliance by risk tier** | Target cuối hoàn tất trước deadline theo policy. | Một target High chưa verified không được bỏ khỏi mẫu số. |
| **Log-integrity failures** | Thiếu/gãy sequence, tampering, provenance invalid. | Phân biệt drop log và malicious deletion. |
| **Secret exposure in telemetry** | Raw token/key/password phát hiện qua controls an toàn. | Không đưa secret thật vào SIEM chỉ để test detection. |
| **False positive/false negative findings** | Detection cần sửa theo audit review và missed incidents. | Đừng tối ưu giảm alert tới mức mất sensitivity. |
| **Mean time to investigate** | Từ alert đến xác định causal chain/evidence. | Chỉ tính trên cases có chất lượng dữ liệu phù hợp. |

### Các công thức dễ dùng

**Revocation latency per required target**:

\[
L_t = \operatorname{verifiedAt}_t - \operatorname{effectiveAt}
\]

**Toàn workflow** (chỉ khi mọi required target đã có verified evidence):

\[
L_{\text{workflow}} = \max_t(\operatorname{verifiedAt}_t)-\operatorname{effectiveAt}
\]

**Verified coverage**:

\[
C = \frac{\#\text{required targets verified}}{\#\text{required targets in scope}} \times 100\%
\]

Nếu 4/5 targets đã có evidence thì **coverage = 80%**, không thể báo workflow verified toàn bộ. Mẫu số phải lấy từ **approved target inventory**, không lấy từ số target có log, vì làm vậy sẽ tự động bỏ những nơi im lặng khỏi thống kê.

### Dashboard có ích

Một dashboard nên cho phép đi từ **lifecycle event** tới những node:
- Subject và verified target account mapping.
- Access request/approval và entitlement delta.
- IdP/SCIM operations + retries.
- Session/token actions khi có metadata đáng tin.
- API/PEP decisions theo tenant/resource.
- Negative probes và no-side-effect evidence.
- Exception/suppression đang còn hiệu lực.
- Target status: **VERIFIED, PARTIAL, UNVERIFIED, REMEDIATION**.
- Outstanding owner, SLA deadline và log coverage gaps.

Không cần phơi bày email, IP đầy đủ hoặc raw payload cho mọi dashboard viewer. Tách **analyst view, auditor view và privileged evidence view** theo vai trò.


## 35. Troubleshooting: khi log correlation bị đứt hoặc kết luận sai

### Trường hợp A — HRIS có event, IGA không tìm thấy correlationId

**Triệu chứng:** HRIS phát ROLE_CHANGED nhưng không có workflow tương ứng ở IGA.

**Kiểm tra:**

1. Event source có **messageId/eventId** và được collector nhận không?
2. Webhook/API gateway có tạo **correlationId/causationId** và ghi event boundary không?
3. Queue có **retry/DLQ/backlog** hoặc event bị schema validator loại không?
4. Identity mapping canonical subject có hợp lệ, chưa bị merge sai tenant không?
5. Revision của event có **cũ hơn current state** và bị bỏ qua hợp lệ không?
6. Nếu business flow chưa được tạo do policy, có reason-coded rejection không?

**Không vội kết luận:** “HR event bị mất” chỉ vì SIEM không thấy log IGA. Có thể đã bị chặn vì **stale revision**, không có quyền xử lý, telemetry drop hoặc clock/ingestion delay.

### Trường hợp B — Hai người bị ghép vào một chuỗi

**Triệu chứng:** Dashboard cho thấy user A có hành vi user B.

**Nguồn lỗi thường gặp:**
- Join theo email/username sau đổi tên hoặc tái tuyển dụng.
- Bỏ issuer/tenant khi so sub/token jti.
- Dùng request header X-User-Id không được xác thực.
- MDC trong Java thread pool không được xóa.
- Dùng IP NAT hoặc traceparent từ client làm bằng chứng identity.
- Dùng mapping hiện tại để nối log lịch sử sai khoảng hiệu lực.

**Khắc phục:** tạm đánh dấu **UNVERIFIED_IDENTITY_MAPPING**, kiểm nguồn mapping có authority và interval, sửa pipeline, đánh giá scope/ảnh hưởng tới những incident đã kết luận.

### Trường hợp C — Một connector success nhưng API vẫn ALLOW

**Triệu chứng:** SCIM 204, target readback đúng, nhưng policy API cho phép hành động cũ.

**Điều tra:**
- JWT claim/refresh token cũ, SP session hoặc local PAT.
- App-local ACL, role inheritance hoặc nested groups chưa gỡ.
- PDP/PEP cache stale, delayed policy event hoặc một RS node chưa cập nhật.
- Bulk/async endpoint bỏ qua authorization middleware.
- Target account mapping sai làm revoke nhầm account.
- Readback kiểm group nhưng quyền đến từ direct entitlement khác.
- Backend ghi ALLOW nhưng transaction có commit hay không?

**Khắc phục:** mở **residual access/remediation**, chặn action theo policy và **verify DENY** tại required PEP. Không chỉ retry SCIM PATCH đến khi trả 200 lần nữa.

### Trường hợp D — SIEM có gap dữ liệu

**Triệu chứng:** Collector drop events, thiếu traces hoặc một target không onboard logs.

**Xử lý:** kiểm logs producer health, buffer/retry, consumer lag, dropped counters và storage ACL/retention. Ghi rõ **khoảng thời gian thiếu dữ liệu**, các systems không quan sát được và phương án chứng minh bằng **target readback/probes** khác. Đừng khẳng định không có vi phạm trong khoảng gap.

### Trường hợp E — Nhiều alerts sau deploy policy mới

**Triệu chứng:** Hàng nghìn AUTHZ_DENY sau rollout.

**Phân loại:**
- Token/JWKS/issuer/audience validation drift.
- Role mapping sai hoặc policy quá rộng.
- Client refresh loop, consent sai, token cache dùng sai tenant.
- Resource Server không tải được current-state.
- Thay đổi access thực sự cần bị chặn.

**Quy trình:** Dùng **positive controls** để nhận biết false deny, so deployed policy version/target node, inspect reason codes và rollback **có kiểm soát** khi được duyệt. Không tắt mọi kiểm chứng chỉ để giảm dashboard đỏ.

## 36. Những sai lầm phổ biến khi làm log correlation IAM

| Sai lầm | Hậu quả | Sửa thế nào |
| --- | --- | --- |
| Chỉ cần một field correlationId trong mọi log. | Có ID nhưng không biết source, causal chain và outcome. | Correlation + causation + business operation + status rõ. |
| Dùng traceId làm user ID. | Ghép sai người, trust boundary bị giả mạo. | Trusted principal từ auth middleware. |
| Tin traceparent/X-User-Id do client tự gửi. | Log spoofing và đánh tráo identity. | Gateway/tracer trust context + canonical principal. |
| Join theo email hoặc IP. | Đổi alias/NAT/rehire gây false attribution. | Immutable subject + issuer/tenant và temporal links. |
| Dùng IdP subject một mình xuyên nhiều issuers. | ID collision và cross-tenant joins. | Composite scoped principal key. |
| Gộp requestId và operationId. | Retry bị đếm thành operations mới hoặc mất attempts. | Business operation stable + attempt ID riêng. |
| Dùng cùng một trace cho cả campaign dài ngày. | Trace phình và mất semantics. | Business correlation, span links và nhiều traces. |
| Sắp timeline chỉ theo ingestion time. | Queue delay làm đảo thứ tự business events. | occurredAt, observedAt, revision/causation. |
| Không theo dõi clock drift. | SLA và causal ordering sai. | Clock quality metadata/uncertainty. |
| SCIM ACK được tính là revoke VERIFIED. | Token/local grants vẫn ALLOW. | Target readback + PEP negative evidence. |
| IdP logout được tính là chặn mọi access token. | JWT/refresh/local session còn sống. | Phân biệt session/token lifecycle và RS outcomes. |
| Mọi event cùng subject được coi cùng một workflow. | Ghép sai những requests độc lập. | Thêm operation/resource/time/authority constraints. |
| Missing logs được diễn giải không có hành vi. | Che phủ visibility gap. | Required source inventory, UNVERIFIED metrics. |
| Chỉ kiểm HTTP 401/403. | Gateway chặn do lỗi khác, async side effect còn. | Reason code, positive control, transaction outcome. |
| Chỉ nhìn PDP decision, không nhìn PEP enforcement. | Policy đúng nhưng endpoint bypass. | API/worker verification, no-side-effect checks. |
| Tự nhận service owner là human initiator. | Sai trách nhiệm, SoD bị đánh lừa. | Distinct actor/initiator/owner fields. |
| Không ghi policy/role version. | Không tái dựng vì sao quyết định đã xảy ra. | Versioned policy and entitlement catalog. |
| Không kiểm nhân sự rehire. | Grant cũ bị gán nhầm nhân viên mới. | Time-valid identity links và lifecycle epoch. |
| Không có eventId/idempotency. | Broker replay tăng giả số revoke và detection. | Stable event IDs + per-attempt metadata. |
| Log raw access token để join dễ. | SIEM thành kho credential, nguy cơ credential replay. | Protected tokenRef hoặc metadata, không raw values. |
| Hash email bằng SHA thường rồi gọi anonymous. | Dễ brute-force dictionary, vẫn có personal data. | Keyed pseudonymization + access/retention. |
| Redact trên dashboard nhưng giữ raw secret trong storage. | Vẫn lộ qua SIEM raw export. | Redaction ở pipeline và bảo vệ nguồn. |
| Không bảo vệ log producer. | Attacker inject event giả, analyst ra quyết định sai. | Provenance, authenticated transport, schema validation. |
| Audit event bị sampled như trace debug. | Mất evidence chính của thay đổi quyền. | Audit pipeline riêng với reliability controls. |
| Cho developer production xóa audit mình tạo. | Có thể che giấu lạm dụng. | SoD, RBAC và tamper-evident retention. |
| KPI tính mẫu số từ target đã gửi log. | Missing target biến mất khỏi coverage. | Approved required-target inventory làm mẫu số. |
| Rút gọn “ACCESS_REVOKE_REQUESTED” thành “ACCESS_REVOKED”. | Chứng cứ bị đẩy lên một trạng thái không đúng. | State taxonomy: requested/applied/verified. |
| Correlate incident bằng timestamp cách nhau vài phút rồi tự động disable user. | Có thể vô hiệu hóa sai principal. | Authority, link confidence, safeguards và approval. |
| Tắt detection khi false positives tăng. | Mất phát hiện thực sự. | Cải thiện mapping, suppression/threshold theo policy. |

**Chất lượng correlation là tích của chất lượng nguồn identity, semantics sự kiện, provenance, thời gian và coverage.** Một dashboard đẹp không thể sửa lỗi nền tảng nếu target không log action hay không kiểm access tại API.

## 37. Checklist triển khai log correlation cho IAM

1. **Mục đích rõ:** cần phục vụ JML, access review, security detection, incident hay SLA nào.
2. **Danh mục nguồn:** HRIS, IGA, IdP, SSO, SCIM, OAuth AS, ứng dụng, API/PEP, PAM, service identities và audit.
3. **Owner mỗi nguồn:** chịu trách nhiệm schema, availability, identity mapping và retention.
4. **Event taxonomy:** AUTHN, AUTHZ, GRANT, REVOKE, APPROVAL, PROVISION, VERIFICATION, INCIDENT phân biệt rõ.
5. **Schema version:** mọi producer có version và mandatory fields, unknown events không được map bừa.
6. **Event envelope:** eventId, eventSource, occurredAt, observedAt, eventType, outcome.
7. **Business correlation:** correlationId gắn workflow; causationId/parentEventId giữ liên kết thật.
8. **Technical trace:** W3C traceparent/tracestate hoặc tracing contract phù hợp, không tin client context làm auth.
9. **Async tracing:** queue retries, fan-out, attempts, DLQ và manual interventions vẫn giữ causal links.
10. **Stable identity:** canonical subject và source authority, tenant; verified time-valid mapping tới target accounts.
11. **Rehire/alias:** không nối chỉ bằng email hoặc dùng mapping hiện tại cho toàn lịch sử.
12. **Human/workload distinction:** actor, initiator, beneficiary, approver, executor, verifier và owner tách riêng.
13. **Entitlement context:** role/permission IDs, target, scope, policy version, desired vs actual state.
14. **Token/session context:** issuer, protected token references, clientId, sessionRef, audience khi cần; không log raw values.
15. **Timestamps:** effectiveAt, appliedAt, verifiedAt khác nhau; UTC/clock quality/late events.
16. **Joiner tests:** pre-provision, start date activation và API ALLOW/DENY đúng mốc.
17. **Mover tests:** role old/new, residual JWT/session/local ACL, SoD, revoke-before-grant khi áp dụng.
18. **Leaver tests:** IdP disable, SCIM, token/RT/PAT, application-local access và verified DENY.
19. **Target readback:** connector ACK không tự thành completion evidence.
20. **PEP coverage:** API, bulk, exports, async workers, database và local SaaS không có bypass.
21. **No unauthorized effects:** kiểm business commit và hậu quả khi policy DENY.
22. **Verified evidence:** positive control, negative probe, reason code, observed outcome, target ID/verifiedAt.
23. **Provenance:** producer authentication, schema validation, trusted enrichment và injection protection.
24. **Privacy:** data minimization, no secrets, protected refs, tenant separation và retention.
25. **Integrity:** access review cho SIEM, audit log của việc đọc/xóa evidence, tamper-evident storage.
26. **Resilience:** mất mạng, retry, duplicate, DLQ, collector outage, backlog và dropped event alerts.
27. **Event ordering:** revision/idempotency, delayed events không tái grant sau Leaver.
28. **Policy governance:** correlation rule version/owner, independent review, exception TTL và rollback.
29. **Operational KPIs:** correlation completeness, mapping coverage, clock skew, lag, verified latency và UNVERIFIED targets.
30. **Alert triage:** phân biệt actual violation, attempt denied, potential conflict, missing data và system outage.
31. **Incident handoff:** incidentId/correlationId, evidence refs, target owner, severity và remediation steps.
32. **Evidence completeness:** chưa bao phủ target critical thì kết luận PARTIAL/UNVERIFIED, không phải PASS.
33. **Regression coverage:** tự động test identity/link/cause/time/privacy/authorization sau thay đổi IdP/SCIM/role schema.
34. **Periodic review:** cập nhật target inventory và detection theo ứng dụng mới, token flow mới, workload mới.
35. **Thước đo cuối:** hệ thống liên kết được từ business JML event tới **effective access outcome**, không chỉ phát hiện một chuỗi request thành công.

**Nghiệm thu nên bao gồm cả “một hành động hợp lệ vẫn ALLOW” và “một hành động bị thu hồi thực sự DENY”**, có full provenance và coverage phù hợp.


## 38. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Log correlation có ý nghĩa gì trong IAM, và vì sao chỉ có log IdP là không đủ?

**Trả lời:** Nó nối các events ở HRIS, IGA, IdP/SSO, SCIM, application và API để tái dựng **ai/yêu cầu nào đã làm thay đổi quyền gì, khi nào và kết quả hiệu lực**. IdP log có thể chứng minh đăng nhập/group update nhưng không tự xác minh API đã DENY quyền cũ.

**Câu 2.** CorrelationId khác traceId ở điểm nào?

**Trả lời:** CorrelationId theo thiết kế có thể gắn **business workflow dài ngày**; traceId thường gắn một **execution trace kỹ thuật** gồm spans. Một workflow có thể có nhiều traces, và traceId không phải stable user ID.

**Câu 3.** Khi nào cần causationId/parentEventId?

**Trả lời:** Khi phải giải thích event được **gây ra bởi** event/operation nào, đặc biệt trong queue fan-out/retry và JML. Chỉ có cùng subject/timestamp không đủ chứng minh quan hệ nhân quả.

**Câu 4.** Vì sao không dùng email làm khóa join duy nhất?

**Trả lời:** Email có thể đổi, có alias hoặc được tái dùng khi rehire. Cần **issuer/authority + immutable subject + tenant**, mapping tới target account có provenance và validFrom/validTo.

**Câu 5.** Có thể dùng traceparent do client gửi để biết user đã được xác thực không?

**Trả lời:** Không. Traceparent là context phục vụ tracing, không chứng minh principal identity hoặc quyền. Actor phải lấy từ **verified authentication context**, gateway cần xử lý trace context không tin cậy.

**Câu 6.** Vì sao SCIM PATCH trả 204 vẫn chưa chứng minh quyền đã thu hồi?

**Trả lời:** ACK chỉ cho biết xử lý request theo contract, không nói hết về target-local ACL, session, JWT hay PAT. Cần readback và **effective authorization proof** trên required PEP.

**Câu 7.** Khi connector retry một operation ba lần, nên có bao nhiêu operation IDs và attempt IDs?

**Trả lời:** Một **operationId** cho thao tác logic và ba **attemptIds** riêng (theo quy ước), giúp tránh nhân ba số lượng business operations mà vẫn giữ được lịch sử retry.

**Câu 8.** occurredAt và observedAt khác nhau ở đâu?

**Trả lời:** occurredAt là lúc producer nói sự kiện xảy ra; observedAt là lúc collector nhận được. Trễ ingest không làm thay đổi business effectiveAt; cần giữ cả hai cùng clock quality để dựng timeline.

**Câu 9.** Khi HRIS gửi Mover 09:00 và API ALLOW quyền cũ lúc 09:04 thì có thể kết luận gì?

**Trả lời:** Nếu subject mapping, trust và timestamps đáng tin, đó là **residual access event/candidate** sau quyền có hiệu lực thu hồi. Cần kiểm action/target, business outcome, exception và coverage để kết luận chính xác mức ảnh hưởng.

**Câu 10.** Vì sao user có thể không còn Creator role nhưng vẫn không được tự duyệt payment cũ?

**Trả lời:** Transaction-level SoD dựa trên **resource actor history**; createdBy của payment vẫn trỏ tới user đó. Correlation phải nối actor hiện hành với creator lịch sử, không chỉ role hiện tại.

**Câu 11.** Một batch service principal gọi API. Có nên ghi owner team là người thực hiện action không?

**Trả lời:** Không. Ghi **technical actor** là service principal, **owner/sponsor** là người chịu trách nhiệm và **human initiator** chỉ khi có ngữ cảnh được ủy nhiệm, xác minh đáng tin.

**Câu 12.** API trả 503 khi kiểm token Leaver cũ. Trạng thái verification là gì?

**Trả lời:** **UNVERIFIED** vì lỗi khả dụng, không phải authorization DENY. Cần positive control và negative probe chứng minh quyền thật sự bị từ chối tại API hoạt động bình thường.

**Câu 13.** Vì sao không thể dùng log “AUTHZ_ALLOW” một mình để khẳng định payment đã chuyển tiền?

**Trả lời:** Authorization ALLOW là quyết định cho phép request, còn business transaction có thể rollback, timeout hoặc chưa commit. Cần correlation với **transaction ledger/COMMITTED event** và side effects.

**Câu 14.** Một user có hai OIDC pairwise subjects khác nhau. Có chắc đó là hai người?

**Trả lời:** Không. Cần mapping có thẩm quyền của IdP/IGA, đúng issuer/client/sector contract; không tự ghép bằng pattern hoặc email.

**Câu 15.** Tại sao correlation logs không thể dùng thay source of truth để tự cấp/revoke quyền?

**Trả lời:** Event store có thể có **ingestion delay, event loss, stale states hoặc enrichment errors**. Authorization/provisioning cần current authoritative state và policy gates; SIEM chủ yếu giám sát, điều tra và đối soát.

**Câu 16.** Một event LEAVER được xử lý sau MOVER cũ đến trễ. Hệ thống cần gì?

**Trả lời:** **Lifecycle revision, current-state check và idempotency** để chặn event cũ tái grant quyền. Log cần ghi rõ event cũ được ignore vì stale revision.

**Câu 17.** Khi nào nên dùng HMAC đối với correlation refs thay vì hash trần?

**Trả lời:** Khi cần liên kết định danh nhạy cảm mà không lưu raw identifier trong nhiều hệ thống, HMAC có khóa được bảo vệ có thể giảm rủi ro dictionary guessing của hash đơn giản. Tuy nhiên dữ liệu vẫn có thể liên kết được và cần key/retention/access governance.

**Câu 18.** Vì sao distributed tracing không thể thay audit logging?

**Trả lời:** Traces có thể bị **sample**, thiếu các bước bất đồng bộ hoặc không được bảo vệ integrity/retention như audit. Những quyết định cấp/thu hồi quyền và business transaction cần audit events chuyên dụng có provenance.

**Câu 19.** Cần ghi những mốc thời gian nào để đo revoke SLA đúng?

**Trả lời:** Ít nhất **effectiveAt** (policy cần chặn), **appliedAt** (thay đổi đã thực hiện) và **verifiedAt** (bằng chứng PEP DENY); kèm clock quality, target coverage và SLA deadline.

**Câu 20.** Nếu bốn trong năm target đã verified deny, hệ thống có thể báo Leaver completed an toàn không?

**Trả lời:** Không. Coverage mới 80%, target thứ năm phải là **UNVERIFIED/PARTIAL** hoặc REMEDIATION theo bằng chứng. Mẫu số phải đến từ required-target inventory, không chỉ từ nguồn có log.

**Câu 21.** Làm sao phân biệt false positive khi phát hiện “API_ALLOW sau Leaver”?

**Trả lời:** Kiểm canonical subject mapping và hiệu lực theo thời gian, source provenance, event-time/clock skew, action/resource thật, exception được duyệt, policy version và transaction outcome. Không tự kết luận từ cùng email hoặc timestamp gần nhau.

**Câu 22.** Vì sao correlation rule cần version và test oracle độc lập?

**Trả lời:** Bởi mapping/schema/policy thay đổi có thể làm rule gộp nhầm hoặc bỏ sót event. Kỳ vọng test phải dựa trên **approved business/IAM rules** và dữ liệu giả có outcome đã biết, không copy logic đang kiểm.

**Câu 23.** Với một service account đã decommission nhưng vẫn có token issuance, cần điều tra gì?

**Trả lời:** Trust binding còn hoạt động, client credentials/refresh grants, role scopes, source runtime, AS issuer, token audience, API acceptance và ownership. Không chỉ xóa app registration rồi bỏ qua token cũ.

**Câu 24.** Đâu là dấu hiệu tốt nhất rằng log correlation giúp giảm quyền truy cập tồn dư?

**Trả lời:** Nó nối được **JML effective event → actual target grant/session/token state → verified API DENY**, có coverage và thời gian rõ, đồng thời phát hiện đường còn ALLOW để remediation. Đếm số log có correlationId không đủ.

## 39. Tài liệu nền và những điểm cần xác minh với hệ thống thực

| Chủ đề | Tài liệu/hệ sinh thái liên quan | Điều cần kiểm trong thực tế |
| --- | --- | --- |
| **Distributed tracing** | W3C Trace Context; OpenTelemetry specification, semantic conventions và context propagation. | Trace headers/baggage được xử lý tại trust boundary, sampling và span links. |
| **Identity provisioning** | SCIM Core Schema/Protocol: RFC 7643, RFC 7644. | User/group IDs, externalId semantics, PATCH/bulk/readback và app-local grants. |
| **OAuth/OIDC** | OAuth 2.0 và access token/introspection/revocation specs; OpenID Connect Core. | Issuer+subject, session/token/grant lifecycle, audience và provider logging. |
| **SAML federation** | SAML 2.0 Core/Profiles và identity provider contracts. | NameID format, SP mapping và attribute minimization. |
| **Security logging** | NIST SP 800-92; OWASP Logging Cheat Sheet. | Schema, clock quality, log injection, redaction, incident response. |
| **Audit controls** | NIST SP 800-53 Audit and Accountability family hoặc control framework được tổ chức áp dụng. | Evidence provenance, access controls, retention, tamper resistance, SoD. |
| **Time format** | RFC 3339 / ISO 8601 và clock synchronization practices. | occurredAt, ingestedAt, effectiveAt/verifiedAt và drift. |
| **SIEM/SOAR** | Tài liệu của nền tảng SIEM/stream processor được sử dụng. | Join semantics, event-time windows, duplicate delivery, RBAC/tenant isolation. |
| **IAM lifecycle** | Quy trình nội bộ HRIS/IGA/IdP/SCIM/PAM và policy RBAC/ABAC/SoD. | Stable principal mapping, approval states, required targets và revoke SLA. |

Những ví dụ JSON, SQL và Java trong bài là **mô hình học tập**, không phải schema hoặc code triển khai nguyên trạng. Khi áp vào doanh nghiệp cần đối chiếu **nhà cung cấp IdP, SIEM, workflow engine, database, token profiles, risk policy và cơ chế authorization của từng target**, sau đó kiểm thử trên môi trường được cho phép.

---

**Ghi nhớ:** **Log correlation trong IAM không chỉ là gắn một traceId lên mọi dòng log.** Cần liên kết **identity có thẩm quyền, business correlation, causal event references, timestamps đáng tin, approved entitlements và effective API decisions** xuyên **HRIS → IGA → IdP/SSO → SCIM → ứng dụng/PEP**. Với **Joiner–Mover–Leaver**, một sự kiện cấp/thu hồi quyền chỉ được xem là hoàn tất về mặt kiểm soát khi các **target bắt buộc có bằng chứng access hợp lệ ALLOW và access bị thu hồi DENY** theo policy, không nhầm connector ACK, SSO logout hay log ingestion với kết quả thực tế. Correlation có ích khi đi kèm **privacy, provenance, audit integrity, reconciliation, SoD, service identity context và coverage minh bạch**, để phát hiện **quyền truy cập tồn dư** và giúp tổ chức điều tra, khắc phục đúng người, đúng quyền, đúng hệ thống.
