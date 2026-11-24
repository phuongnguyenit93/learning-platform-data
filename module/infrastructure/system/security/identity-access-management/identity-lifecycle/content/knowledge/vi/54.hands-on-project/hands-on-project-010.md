# Dự án thực hành: Thêm audit và monitoring cho Identity Lifecycle IAM

## 1. Mục tiêu dự án

Một luồng **Joiner–Mover–Leaver (JML)** có thể đã tạo, cập nhật hoặc vô hiệu hóa tài khoản mà nhóm vận hành vẫn không biết **ai yêu cầu**, **chính sách nào được áp dụng**, **ứng dụng nào chưa đồng bộ** và **liệu quyền cũ còn dùng được hay không**. Bài thực hành này hướng dẫn bổ sung **audit trail** (dấu vết kiểm toán) và **monitoring** (giám sát vận hành, bảo mật) để các sai lệch không bị che khuất trong nhiều hệ thống.

Phạm vi thuộc module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, tập trung xác minh–tạo tài khoản–cấp quyền–rà soát–thu hồi khi đổi vai trò, liên kết HRIS, IAM orchestrator, Identity Provider (IdP), SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và ứng dụng đích. Kết quả phải giúp giảm **quyền truy cập tồn dư** và hỗ trợ kiểm toán được toàn bộ vòng đời.

Học viên cần bàn giao:

1. Thiết kế sự kiện audit thống nhất cho Joiner, Mover, Leaver, approval, policy decision và provisioning.
2. Cách liên kết event qua correlation ID, event ID, actor, subject và target.
3. Dashboard về độ trễ cấp/thu hồi quyền, sai lệch trạng thái, lỗi connector và sự kiện an ninh.
4. Cảnh báo có ngưỡng, mức độ ưu tiên, owner, hướng xử lý và chống nhiễu.
5. Quy trình reconciliation, kiểm thử audit, mô phỏng lỗi và báo cáo diễn tập.

**Giới hạn an toàn:** chỉ dùng tài khoản, hệ thống và dữ liệu giả trong sandbox. Không ghi password, OTP, access/refresh token, API key, private key hay nội dung nhạy cảm vào log; audit cần đủ thông tin để điều tra nhưng không trở thành kho bí mật.

## 2. Bối cảnh và các giả định

Tổ chức giả lập có một HRIS làm nguồn trạng thái nhân sự, IAM điều phối sự kiện, IdP/SSO cung cấp xác thực, CRM hỗ trợ SCIM, ứng dụng Finance dùng API riêng và bot CI/CD có service principal. Chính sách giả định: Sales VN được đọc CRM VN, Finance được đọc báo cáo Finance, Leaver không còn quyền tương tác; quản trị viên phải được phê duyệt riêng.

Ba sự kiện thử:

~~~yaml
events:
  - eventId: "join-201-v1"
    version: 1
    personId: "test-person-201"
    type: JOINER
    department: SALES
    region: VN
    effectiveAt: "2026-12-02T09:00:00+07:00"
  - eventId: "move-202-v4"
    version: 4
    personId: "test-person-202"
    type: MOVER
    fromDepartment: SALES
    toDepartment: FINANCE
    effectiveAt: "2026-12-03T09:00:00+07:00"
  - eventId: "leave-203-v9"
    version: 9
    personId: "test-person-203"
    type: LEAVER
    effectiveAt: "2026-12-04T18:00:00+07:00"
~~~

Đây là dữ liệu minh họa, không phải schema HRIS thực tế. Mọi ngưỡng trong bài phải được xác định từ chính sách và SLA của môi trường thử; không sử dụng số liệu mẫu để tuyên bố mức tuân thủ thực tế.

## 3. Phân biệt audit, log, metric, trace và alert

| Thành phần | Trả lời | Ví dụ |
|---|---|---|
| **Audit event** | Ai/điều gì thực hiện thay đổi có ý nghĩa, theo căn cứ nào? | Approver phê duyệt role Finance cho person-202 |
| **Operational log** | Thành phần đang xử lý gì, lỗi gì xảy ra? | SCIM connector trả HTTP 429 |
| **Metric** | Hệ thống hoạt động tốt đến đâu theo thời gian? | 95th percentile của độ trễ revoke |
| **Trace** | Một workflow đi qua dịch vụ và connector nào? | HRIS → IAM → IdP → CRM |
| **Alert** | Ai cần hành động ngay khi điều kiện rủi ro xảy ra? | Leaver vẫn truy cập CRM sau SLA |

Audit phải đáng tin cậy, chống sửa đổi trái phép, có quy định lưu giữ và quyền đọc. Log vận hành có thể chứa thông tin chẩn đoán ngắn hạn nhưng không tự động đủ làm bằng chứng về quyết định quyền. Metric tổng hợp giúp theo dõi xu hướng nhưng không thay thế bản ghi chi tiết để điều tra từng người.

## 4. Thiết kế event audit chuẩn hóa

Mỗi sự kiện audit nên gồm các trường:

| Nhóm | Trường minh họa | Ý nghĩa |
|---|---|---|
| Định danh | eventId, correlationId, causationId | Phân biệt một hành động và chuỗi workflow |
| Thời gian | occurredAt, observedAt, effectiveAt | Phân biệt lúc nghiệp vụ phát sinh và lúc hệ thống thấy |
| Chủ thể | actorId, actorType, subjectId | Người/hệ thống thực hiện và danh tính bị tác động |
| Nguồn/đích | sourceSystem, targetSystem, tenantId | Xác định ranh giới tích hợp |
| Hành động | action, lifecycleType, operation | Ví dụ GRANT, REVOKE, ACCOUNT_DISABLE |
| Căn cứ | policyId, policyVersion, approvalId | Giải thích quyết định |
| Kết quả | status, reasonCode, retryCount | SUCCESS, FAILED, PENDING và nguyên nhân |
| Đối soát | desiredStateHash, observedStateHash | Phát hiện trạng thái khác nhau mà không log dữ liệu nhạy cảm |

Ví dụ audit JSON:

~~~json
{
  "eventId": "audit-000045",
  "correlationId": "corr-move-202-v4",
  "causationId": "move-202-v4",
  "occurredAt": "2026-12-03T02:00:04Z",
  "actorId": "iam-orchestrator",
  "actorType": "SERVICE",
  "subjectId": "test-person-202",
  "sourceSystem": "IAM",
  "targetSystem": "CRM",
  "lifecycleType": "MOVER",
  "action": "ENTITLEMENT_REVOKE",
  "entitlement": "crm.customer.read.vn",
  "policyId": "jml-access-policy",
  "policyVersion": "12",
  "approvalId": "approved-move-202",
  "status": "SUCCEEDED",
  "reasonCode": "ROLE_CHANGED",
  "retryCount": 0
}
~~~

Không ghi hồ sơ HR đầy đủ, email không cần thiết, dữ liệu khách hàng hoặc giá trị token. Nếu cần truy vấn một danh tính, dùng ID giả hoặc tham chiếu đã bảo vệ; khi dùng hash, cần bảo đảm không vô tình tiết lộ thông tin có entropy thấp.

**Event ID** định danh bản ghi audit, **causation ID** liên kết sự kiện đầu vào dẫn đến thao tác, **correlation ID** liên kết toàn bộ chuỗi. Nếu consumer nhận event trùng, có thể có nhiều log thử lại nhưng không được ghi nhận sai rằng nhiều entitlement mới đã được cấp.

## 5. Bản đồ điểm phát audit trong luồng JML

~~~mermaid
flowchart TD
    H[HRIS event] --> I[IAM workflow]
    I --> P[Policy RBAC / ABAC]
    P --> A[Approval / SoD]
    A --> D[IdP / SSO]
    D --> S[SCIM / Application]
    S --> R[Readback / Reconciliation]
    H --> L[Audit collector]
    I --> L
    P --> L
    A --> L
    D --> L
    S --> L
    R --> L
    L --> M[Metrics / Traces]
    M --> N[Dashboard / Alerts]
~~~

Định nghĩa các checkpoint tối thiểu:

1. **Event received/validated:** nguồn, định danh, phiên bản, effectiveAt, hợp lệ hay bị từ chối.
2. **Policy evaluated:** policy version, role/ABAC attributes đã được chuẩn hóa, kết quả cho phép/từ chối.
3. **Approval recorded:** ai duyệt, phạm vi, expiry và quyết định SoD.
4. **Provisioning attempted:** target, operation, correlation ID, trạng thái yêu cầu; không ghi token connector.
5. **Provisioning observed:** readback account, nhóm, quyền tại đích và thời điểm xác minh.
6. **Authorization enforced:** kết quả ALLOW/DENY của ca kiểm thử truy cập hoặc sự kiện truy cập quan trọng.
7. **Reconciliation completed:** sai lệch quyền, remediation, người chịu trách nhiệm và trạng thái đóng.

Audit tại bước “gửi lệnh SCIM thành công” không thay cho audit “quyền tại đích đã đúng”. Với Leaver, cần phân biệt disable account tại IdP với việc session SSO hay API key cũ hết hiệu lực.

## 6. Các bất biến cần giám sát

**Bất biến** (invariant) là điều kiện hệ thống phải giữ đúng, bất kể thứ tự sự kiện hay lỗi mạng. Đề xuất:

~~~text
INV-01: TERMINATED identity không có quyền tương tác vượt SLA.
INV-02: MOVER mới không giữ quyền của role cũ ngoài chính sách/ngoại lệ.
INV-03: JOINER chưa verified/approved không được cấp quyền nhạy cảm.
INV-04: Mọi grant đặc quyền có approval và expiry hợp lệ.
INV-05: Sự kiện cũ không phục hồi quyền đã thu hồi ở version mới.
INV-06: Mỗi service principal có owner được xác minh và review deadline.
INV-07: Quyết định REVOKE được xác minh tại ứng dụng, không chỉ ở IAM.
~~~

Giám sát nên đối chiếu **desired state** từ HRIS/policy với **observed effective access** từ IdP và ứng dụng. Một user có thể bị gỡ khỏi IdP group nhưng còn quyền direct ACL ở CRM; nếu chỉ đo số ticket đóng thì không phát hiện INV-02/INV-07 bị vi phạm.

## 7. Xây dựng metrics và dashboard

| Metric | Định nghĩa | Ý nghĩa |
|---|---|---|
| provisioning_success_ratio | Số target đã xác minh đúng / tổng target đến hạn | Phân biệt giao lệnh và hội tụ |
| deprovisioning_latency | Thời gian từ effectiveAt đến lúc quyền bị chặn | Phát hiện Leaver quá hạn |
| access_reconciliation_gap | Số quyền thực tế không được phê duyệt | Đo quyền tồn dư |
| pending_connector_operations | Số thao tác đang PENDING theo target | Tắc nghẽn hoặc thiếu kết nối |
| connector_error_ratio | Lỗi connector / tổng lần gọi theo loại | Phát hiện sự cố SCIM/API |
| stale_event_rejected_count | Số event cũ bị từ chối hợp lệ | Quan sát xử lý thứ tự sự kiện |
| orphan_service_principals | Số danh tính máy thiếu owner | Nguy cơ secret tồn dư |
| audit_event_gap_count | Số checkpoint bắt buộc thiếu audit | Kiểm soát độ đầy đủ chứng cứ |

Chọn dashboard theo ba lớp: **tình trạng toàn hệ thống** (SLA, lỗi, backlog), **rủi ro bảo mật** (Leaver còn active, privileged grants quá hạn, quyền chồng lấn) và **chi tiết điều tra** (tìm theo correlation ID, event ID, target). Không đặt person ID hoặc email làm nhãn metric có độ phân biệt cao; metric có cardinality lớn gây chi phí và lộ dữ liệu.

Ví dụ công thức:

~~~text
revokeLatency = firstObservedDeniedAt - effectiveAt
overdueRevocations = count(revokeLatency > approvedRevocationSLA)
unexpectedGrants = actualEffectiveGrants - approvedDesiredGrants
auditCompleteness = checkpointsWithAudit / expectedCheckpoints
~~~

Các phép đo cần tránh đếm sai khi chưa tới effectiveAt hoặc khi chỉ một ứng dụng hoàn tất. Dùng timestamp thống nhất (ưu tiên UTC trong log), đo độ trễ theo từng target và ghi trạng thái chưa biết khi telemetry thiếu.

## 8. Thiết kế alert và quy trình phản ứng

| Alert | Điều kiện kích hoạt | Mức ưu tiên gợi ý | Người xử lý |
|---|---|---|---|
| Leaver still active | Có quyền tương tác sau deadline đã duyệt | Critical | Security + IAM On-call |
| Privileged grant expired | Entitlement nhạy cảm còn hiệu lực sau expiry | High | IAM + App Owner |
| SCIM sync failure | Target lỗi liên tục hoặc backlog quá SLA | High | IAM Operations |
| Missing audit trail | Thiếu checkpoint quan trọng trong workflow | High | Security Engineering |
| Orphaned service identity | Service principal thiếu owner quá thời hạn xử lý | Medium/High tùy quyền | App Owner |
| Unexpected access grant | Grant thực tế không có trong policy/approval | High/Critical tùy tài nguyên | Security |
| Out-of-order event regression | Sự kiện cũ phục hồi quyền đã thu hồi | Critical | IAM + Incident Team |

Đây là mức ưu tiên minh họa; môi trường thật cần phân loại theo hệ thống, dữ liệu và SLA. Mỗi alert phải có **owner**, playbook, link tới evidence, thời điểm mở, trạng thái xử lý và điều kiện đóng. Giảm nhiễu bằng dedup theo correlation/target, grouping theo incident, ngưỡng kéo dài hợp lý và chế độ bảo trì được phê duyệt. Không để giảm nhiễu che khuất một Leaver thực sự còn truy cập.

Khi thấy bất biến bảo mật bị vi phạm, chỉ rõ bước containment nếu chính sách cho phép, ví dụ chặn session rủi ro hoặc khóa tài khoản tại IdP; các thay đổi ngoài sandbox phải do người có thẩm quyền thực hiện.

## 9. Mẫu thu thập audit event bằng Java

Đây là ví dụ minh họa về cấu trúc phát sự kiện từ một ứng dụng Java. Hàm ghi ra hệ thống audit riêng nên hỗ trợ độ bền, retry và cơ chế bảo đảm delivery được thiết kế; đoạn mã không thay thế hạ tầng audit production.

~~~java
import java.time.Instant;
import java.util.Map;

record AuditEvent(
    String eventId,
    String correlationId,
    String actorId,
    String subjectId,
    String action,
    String targetSystem,
    String result,
    Instant occurredAt
) {}

interface AuditPublisher {
    void publish(AuditEvent event);
}

class LifecycleService {
    private final AuditPublisher audit;

    LifecycleService(AuditPublisher audit) {
        this.audit = audit;
    }

    void recordRevocation(
        String eventId,
        String correlationId,
        String personId,
        String target,
        boolean verified
    ) {
        audit.publish(new AuditEvent(
            eventId,
            correlationId,
            "iam-orchestrator",
            personId,
            "ENTITLEMENT_REVOKE_VERIFIED",
            target,
            verified ? "SUCCEEDED" : "FAILED",
            Instant.now()
        ));
    }
}
~~~

Để tránh mất audit khi nghiệp vụ commit nhưng publisher gặp lỗi, xem xét **transactional outbox** hoặc cơ chế ghi bền tương đương. Khi audit pipeline không sẵn sàng, hành vi tiếp tục/chặn nghiệp vụ cần được xác định theo rủi ro và chính sách. Không tự đánh dấu đã phát audit nếu mới đưa sự kiện vào bộ nhớ.

## 10. Kiểm thử dữ liệu audit và monitoring

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| AM01 | Joiner thành công | Có event nguồn, policy, approval, provisioning, readback |
| AM02 | Joiner bị từ chối do thiếu phê duyệt | Có DENY và reason, không có grant ngoài ý muốn |
| AM03 | Mover cấp quyền mới và gỡ quyền cũ | Truy vết được trước/sau và target |
| AM04 | Leaver hợp lệ | Có bằng chứng chặn đăng nhập và quyền đích |
| AM05 | SCIM timeout sau khi server đã xử lý | Retry không nhân đôi grant; audit nhất quán |
| AM06 | Event bị replay | Không đếm thành nhiều thay đổi quyền |
| AM07 | Mover cũ đến sau Leaver | Bị chặn và ghi reason STALE_EVENT |
| AM08 | Ứng dụng còn direct grant | Reconciliation tìm thấy sai lệch |
| AM09 | Audit collector bị lỗi | Không báo coverage hoàn chỉnh giả |
| AM10 | Alert Leaver quá SLA | Alert tới đúng owner, có evidence |
| AM11 | Quyền đặc quyền hết hạn | Alert và remediation theo policy |
| AM12 | Service account thiếu owner | Phát hiện và tạo finding |
| AM13 | Log có token/secret | Test fail và yêu cầu redaction |
| AM14 | Đồng hồ dịch vụ lệch | Phát hiện timestamp bất thường, không đo SLA sai |
| AM15 | Bulk event quá tải | Có backpressure và kiểm soát mất log |

Chú ý phân biệt **audit event được gửi** và **được lưu, tìm kiếm, bảo toàn**. Tạo ca thử mất kết nối collector, retry gửi trùng, sự kiện tới ngoài thứ tự, kiểm soát access vào audit storage và thay đổi trái phép nội dung log.

## 11. Reconciliation tự động và bằng chứng xử lý quyền tồn dư

Một job reconciliation nên được thiết kế chạy theo lịch hoặc sau sự kiện lỗi:

1. Lấy danh tính và trạng thái JML có thẩm quyền; ghi snapshot ID, version, timestamp.
2. Tính entitlement được duyệt dựa trên RBAC/ABAC, SoD và ngoại lệ còn hiệu lực.
3. Liệt kê account và effective grants từ IdP, CRM, Finance, local ACL và service principals.
4. Kiểm tra pagination và freshness của inventory; thiếu nguồn dữ liệu phải hiện là UNKNOWN, không được suy bằng rỗng.
5. So sánh actual–desired để tìm quyền thừa, quyền thiếu, account mồ côi và owner thiếu.
6. Tạo finding có độ nghiêm trọng, owner, SLA, link audit và hành động khắc phục.
7. Thực hiện remediation được phê duyệt; readback và thử API DENY/ALLOW sau sửa.
8. Chỉ đóng finding khi trạng thái cuối đã được xác minh.

Ví dụ một Mover rời Sales nhưng role cục bộ ở CRM còn cho phép export. IAM báo đã gỡ IdP group nhưng reconciliation phải tìm ra grant thừa; sau gỡ quyền, thử lại API export bằng session cũ để xác minh không còn đường truy cập sau deadline.

## 12. Thiết kế bảo vệ audit và tính riêng tư

Audit trail có thể chứa ID định danh, hành động nhạy cảm và dữ liệu truy vết. Kiểm soát:

- **Least privilege:** chỉ bộ phận audit, bảo mật và vận hành được ủy quyền mới có quyền đọc tương ứng.
- **Integrity:** chống sửa/xóa trái phép bằng append-only/immutability và kiểm tra toàn vẹn phù hợp.
- **Retention:** thời hạn lưu theo yêu cầu pháp lý, hợp đồng, kiểm toán và chính sách riêng.
- **Data minimization:** chỉ ghi trường cần thiết, không ghi bí mật hoặc payload HR/customer đầy đủ.
- **Time synchronization:** hệ thống dùng UTC và đồng bộ thời gian để đối chiếu thứ tự sự kiện.
- **Audit of audit access:** truy cập, xuất hoặc thay đổi cấu hình lưu trữ audit cũng cần được ghi nhận.
- **Incident handling:** cảnh báo khi mất log, thiếu checkpoint, thay đổi policy thu thập hoặc phát hiện truy cập bất thường vào kho audit.

Không dùng lời hứa “log bất biến” nếu storage vẫn cho quản trị viên tùy ý sửa; trong bài nộp cần mô tả cụ thể biện pháp bảo vệ và hạn chế của hệ thống giả lập.

## 13. Quy trình triển khai dự án theo bước

### Bước 1 — Vẽ luồng JML và chọn checkpoint

Tạo sơ đồ nguồn HRIS → IAM → IdP/SCIM → ứng dụng, liệt kê các sự kiện cần audit. Với từng checkpoint, chọn producer, consumer, dữ liệu bắt buộc và trạng thái khi gửi thất bại.

### Bước 2 — Định nghĩa schema và correlation

Chuẩn hóa eventId, causationId, correlationId, subjectId, actorId, target, action, status, timestamp, policyVersion. Viết schema version và quy tắc tương thích khi thêm trường.

### Bước 3 — Phát audit, metric, trace

Thêm instrumentation tại các vị trí đã chọn; bảo đảm không ghi secret. Ghi metric ở dạng tổng hợp theo loại event, connector, target, status mà không đưa ID cá nhân thành label.

### Bước 4 — Xây dashboard và alert

Tạo ba góc nhìn: vận hành, bảo mật, điều tra; cấu hình alert theo SLA được phê duyệt, owner, runbook và điều kiện đóng.

### Bước 5 — Chạy tình huống kiểm thử

Thực hiện Joiner, Mover, Leaver, SCIM lỗi, event trùng, event cũ, quyền cục bộ còn tồn dư và log collector mất kết nối. Xác nhận event/metric/trace/alert có đủ bằng chứng.

### Bước 6 — Đối soát và nghiệm thu

So sánh desired state với effective access tại ứng dụng; ghi findings, remediation và kết quả readback. Kết luận dựa trên hệ thống đích, không chỉ trạng thái workflow IAM.

## 14. Rubric đánh giá bài thực hành

| Hạng mục | Điểm tối đa | Minh chứng cần nộp |
|---|---:|---|
| Sơ đồ luồng và checkpoint JML | 15 | Sơ đồ và danh sách producer/consumer |
| Audit schema, version, correlation | 20 | Ví dụ JSON, mô tả thời gian và actor |
| Metrics, dashboard, alert | 20 | Chỉ số có định nghĩa, ngưỡng, owner |
| Kiểm thử lỗi, replay và an toàn sự kiện | 15 | Bảng testcase và kết quả quan sát |
| Reconciliation, phát hiện quyền tồn dư | 15 | Finding và chứng cứ readback |
| Bảo vệ audit và dữ liệu cá nhân | 10 | Retention, RBAC, redaction, integrity |
| Báo cáo diễn tập | 5 | PASS/FAIL, remediation, owner |
| **Tổng** | **100** | **Mức đạt bài học: 80 điểm, không có lỗi quyền tồn dư nghiêm trọng bị bỏ qua** |

Điểm số dùng cho môi trường học tập. Chính sách vận hành thật phải do tổ chức phê duyệt, không suy từ rubric.

## 15. Mẫu báo cáo kết quả

~~~markdown
# JML Audit and Monitoring Drill

Environment:
Policy version:
Audit schema version:
Participants and approvers:
Event IDs and correlation IDs:

| Case ID | Expected event/metric/alert | Observed | Evidence | Status |
|---|---|---|---|---|
| AM01 | Joiner checkpoints complete | ... | ... | ... |
| AM04 | Leaver revoke observed | ... | ... | ... |
| AM08 | Residual CRM grant detected | ... | ... | ... |
| AM09 | Collector gap surfaced | ... | ... | ... |

Findings:
- Severity:
- Affected target:
- Root cause:
- Owner and due date:
- Remediation:
- Verification evidence:

Final review:
~~~

Chỉ kết luận hoàn tất khi có bằng chứng kết nối được **sự kiện nguồn → quyết định chính sách → thao tác provisioning/deprovisioning → quyền thực tế → audit/alert**. Monitoring phải giúp nhóm vận hành phát hiện và xử lý sai lệch, không chỉ tạo thêm biểu đồ đẹp.

## 16. Câu hỏi tự đánh giá

1. Vì sao một log “SCIM update succeeded” chưa đủ chứng minh Leaver không còn truy cập?
2. Event ID, causation ID và correlation ID có nhiệm vụ khác nhau thế nào?
3. Khi audit collector ngắt kết nối, nên biểu diễn độ đầy đủ bằng trạng thái gì?
4. Vì sao không nên dùng person ID làm label metric?
5. Cách kiểm chứng một quyền được gỡ khỏi IdP group nhưng vẫn còn qua role cục bộ?
6. Khi Mover cũ đến sau Leaver, audit và alert phải cho thấy những thông tin nào?
7. Làm thế nào giữ đủ chứng cứ điều tra mà không ghi token hay dữ liệu cá nhân không cần thiết?

**Kết luận:** Một hệ thống IAM quản lý vòng đời tốt phải vừa thực hiện thay đổi quyền chính xác vừa **chứng minh được kết quả và phát hiện sai lệch kịp thời**. Audit cung cấp sự giải trình, monitoring phát hiện vấn đề, reconciliation xác nhận quyền thực tế; phối hợp ba yếu tố giúp giảm quyền truy cập tồn dư sau Joiner–Mover–Leaver.
