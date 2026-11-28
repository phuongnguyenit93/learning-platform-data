# Rollback readiness: chứng minh khả năng khôi phục bản phát hành về trạng thái an toàn

**Rollback readiness (mức sẵn sàng quay lui bản phát hành)** là khả năng đã được chuẩn bị, kiểm thử và ghi nhận bằng chứng để đưa một dịch vụ hoặc hệ thống **từ trạng thái sau phát hành gặp lỗi về một trạng thái chấp nhận được về chức năng, dữ liệu, an toàn thông tin và khả năng vận hành**, trong phạm vi và khoảng thời gian được phê duyệt. Đây không chỉ là có lệnh deploy phiên bản cũ. Một release có thể đổi code, IAM, database schema, keys, event format, DNS, third-party integration và trạng thái dữ liệu; việc đảo ngược một thành phần có thể làm các thành phần khác mất tính tương thích hoặc tái tạo lỗ hổng bảo mật cũ.

Trong chương **Release assurance** của module **SECURITY_SECURITY_ASSURANCE**, chủ đề này gắn với mục tiêu học cách **đánh giá có bằng chứng** hệ thống đáp ứng các mục tiêu bảo mật: từ risk analysis, security requirements và controls đến kiểm thử, audit, phát hiện, remediation và cải tiến liên tục trong phát triển/vận hành. Do đó, một tuyên bố “rollback ready” cần có **phạm vi, điều kiện kích hoạt, artifact tin cậy, runbook, dependency, thời hạn, chủ sở hữu, kiểm thử, bằng chứng và giới hạn** có thể được người khác xác minh.

> **Nguyên tắc cốt lõi:** rollback thành công không có nghĩa là khôi phục chính xác mọi byte của trạng thái trước đó; thành công nghĩa là đạt **trạng thái phục hồi đã được chấp thuận** với các bất biến dữ liệu, security controls và business acceptance criteria đã xác định. Nếu đảo ngược không an toàn hoặc không khả thi, cần **fail-forward, containment hoặc disaster recovery** có kiểm soát thay vì cố revert.

Các tình huống, số liệu và ID trong bài là ví dụ giáo dục, không phải yêu cầu SLA chung hoặc bằng chứng của một hệ thống thật.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **rollback**, **roll-forward/fail-forward**, **feature disable**, **traffic failback**, **backup restore**, **disaster recovery**, **containment** và **re-deployment**.
2. Phân tích thay đổi dựa trên **before/after state**, trust boundaries và những thành phần có thể hoặc không thể đảo ngược.
3. Định nghĩa mục tiêu rollback theo **service recovery, data integrity, security invariants, RTO/RPO và business impact**, tránh chỉ đo thời gian chạy command.
4. Liệt kê các phụ thuộc bắt buộc của rollback: artifact, container image, IAM, DNS, KMS, secrets, schema, queue, storage, third-party API, observability và capacity.
5. Thiết kế rollback strategy cho release stateless, stateful, database migration, identity changes và key rotation.
6. Xây **release/rollback gates** với điều kiện kích hoạt, stop conditions, go/no-go, thẩm quyền và runbook có thể vận hành khi sự cố xảy ra.
7. Kiểm tra provenance và tính tin cậy của **artifact cũ**, bảo đảm rollback không vô tình tái đưa một vulnerability nghiêm trọng vào production.
8. Thực hành canary, progressive delivery, blue-green, feature flags và cách đo trạng thái thực tế trên toàn bộ affected population.
9. Phân tích rủi ro **backward compatibility, dual-write, queue replay, data deletion, session/token validity, rollback drift và partial failure**.
10. Xây bài **rollback rehearsal** có positive/negative tests, dữ liệu đại diện, fault scenarios, security assertions và evidence.
11. Tổ chức phối hợp release manager, SRE, security, database, identity, data owner, SOC, IR và risk owner.
12. Theo dõi rollback readiness theo thời gian qua KPI, retest, decision records và continuous release assurance.

## 2. Rollback readiness khác “có thể redeploy phiên bản cũ”

### 2.1. Định nghĩa thuật ngữ

| Khái niệm | Ý nghĩa | Ví dụ | Giới hạn |
|---|---|---|---|
| **Application rollback** | Đưa code/config application về bản đã chọn | Deploy lại image digest trước release | Không tự đảo database, IAM, keys hay external state |
| **Infrastructure rollback** | Khôi phục trạng thái hạ tầng hoặc chính sách trước thay đổi | Phục hồi network rule được duyệt | Có thể xóa các tài nguyên mới đã chứa dữ liệu |
| **Feature flag disable** | Ngừng một tính năng hoặc route có nguy cơ | Tắt tính năng export dữ liệu | Code và schema mới có thể vẫn hiện diện |
| **Traffic switch/failback** | Chuyển lưu lượng sang phiên bản/region hoạt động | Blue-green switch về blue | Dữ liệu/queue có thể đã cập nhật ở green |
| **Roll-forward / fail-forward** | Sửa bản đang chạy bằng hotfix tương thích | Deploy schema-compatible correction | Cần kiểm patch, provenance và release gates |
| **Data restore** | Khôi phục dữ liệu từ checkpoint/snapshot/backup | Restore DB đến recovery point phù hợp | Có thể mất dữ liệu được ghi sau checkpoint |
| **Disaster recovery** | Khôi phục dịch vụ sau thảm họa/failure domain lớn | Phục hồi ở region/account khác | Bao gồm nhiều dependency và BIA objectives |
| **Containment** | Hạn chế nguy cơ trước hoặc thay vì revert | Chặn route nhạy cảm, revoke credential | Chưa chắc loại bỏ nguyên nhân |
| **Compensating control** | Kiểm soát khác làm giảm rủi ro theo objective đã xét | Hạn chế access và giám sát khi patch bị hoãn | Cần kiểm hiệu lực, scope và expiry |
| **Safe degraded mode** | Dịch vụ hoạt động giới hạn trong điều kiện chấp thuận | Chỉ đọc, ngừng giao dịch mới | Có thể ảnh hưởng mục tiêu nghiệp vụ, hợp đồng |

**Rollback readiness** là **mức sẵn sàng và độ tin cậy của toàn bộ đường khôi phục**: liệu có thực hiện an toàn được khi cần, dựa trên bằng chứng hiện hành hay không. Việc đã từng rollback một service stateless không chứng minh đường rollback của một release có destructive migration cũng sẵn sàng.

### 2.2. Hai chiều phải bảo toàn

**Business correctness:** dịch vụ tiếp tục đáp ứng chức năng quan trọng, không làm mất/nhân đôi giao dịch, không phá dữ liệu hoặc phạm vi phục vụ mà nghiệp vụ không chấp thuận.

**Security correctness:** xác thực/ủy quyền, encryption/decryption, audit logging, secrets, data isolation, image provenance, detection và recovery permissions vẫn đáp ứng các security assertions bắt buộc.

Nếu khôi phục 200 HTTP responses nhưng quyền tenant bị mở rộng, không thể coi rollback đạt security acceptance. Nếu bảo vệ được IAM nhưng các giao dịch bị phát sinh đôi không có đối soát, cũng chưa đạt yêu cầu nghiệp vụ.

### 2.3. Rollback không phải khả năng quay ngược thời gian

Từ lúc release bắt đầu đến lúc rollback, hệ thống có thể tạo:

- Thanh toán, đơn hàng hoặc ledger entries.
- Token/session/credential đã cấp cho người dùng và dịch vụ.
- Message events đã phát sang queue hoặc third party.
- Bản ghi thuộc schema mới; một số không còn biểu diễn được bằng schema cũ.
- Dữ liệu đã gửi tới analytics, webhook, vendor hoặc email.
- Backup mới, key mới, storage lifecycle và encryption metadata.
- Network allowlists, DNS cache, signed URLs hoặc external approvals.

Lùi code về phiên bản cũ **không thu hồi các tác động đã rời hệ thống**. Cần có chiến lược **reconciliation, idempotency, compensation business, key compatibility, message handling và xử lý residual risk**, không đơn thuần “git revert”.

## 3. Security assurance objectives của rollback

### 3.1. Tại sao rollback là security control?

Một rollback không an toàn có thể:

- Tái đưa vulnerability đã sửa vào public API.
- Làm mất enforced MFA/least privilege sau khi quay về policy cũ.
- Cắt audit log/telemetry để tăng tốc restore.
- Khôi phục một backup không sạch hoặc có persistence sau incident.
- Phá authorization isolation giữa các tenant do schema/application mismatch.
- Mở rộng quyền KMS để giải mã tạm nhưng quên thu hồi.
- Làm mất/nhân đôi giao dịch và ảnh hưởng **integrity**.
- Làm quá RTO/RPO, ảnh hưởng **availability**.
- Hủy bằng chứng điều tra do ghi đè log hoặc làm mất event IDs.
- Đưa lại artifact không được kiểm nguồn gốc hoặc không còn được ký tin cậy.

Do đó rollback readiness cần được coi là một **security control objective có thể kiểm chứng**, không chỉ mục trong checklist release.

### 3.2. Những security invariants cần giữ

**Security invariant** là điều kiện phải luôn đúng hoặc phải được phục hồi theo yêu cầu trước khi dịch vụ được coi là an toàn. Ví dụ:

| Invariant | Assertion cần chứng minh | Cách kiểm |
|---|---|---|
| **Authorization** | Principal không được phép không đọc/sửa được resource ngoài scope | Negative/positive authorization tests |
| **Authentication** | Admin paths bắt buộc được enforce MFA; break-glass có kiểm soát | Effective policy + controlled login tests |
| **Encryption** | Dữ liệu trước/sau rollback còn giải mã được đúng quyền | KMS/key access + restore/data reads |
| **Secret lifecycle** | Credential bị revoke không có hiệu lực trở lại | Revoke deny test, token/session checks |
| **Audit trail** | Security events tiếp tục tới kho tập trung với field cần thiết | Synthetic event source→SIEM→alert |
| **Data integrity** | Không mất/nhân đôi giao dịch ngoài recovery objective | Reconciliation, idempotency, constraints |
| **Supply chain** | Artifact rollback có provenance/trust và đáp ứng baseline tối thiểu | Digest, signing/attestation, scan/exception |
| **Tenant/data boundaries** | Không xuất dữ liệu cross-tenant do code/schema mismatch | Multi-tenant regression tests |
| **Recovery access** | DR/recovery identity chỉ có quyền cần thiết | Effective permission/deny tests |
| **Observability** | Phát hiện lỗi, mất nguồn và hành động đặc quyền | Health, controlled fault/canary event |
| **Retention & privacy** | Rollback không làm mất hoặc tiết lộ dữ liệu trái yêu cầu áp dụng | Retention/deletion/access checks |

Một release có thể bổ sung invariants mới. Khi rollback về phiên bản cũ, cần xác định bản cũ có thể đáp ứng yêu cầu **đang có hiệu lực** không; không mặc định trạng thái “trước release” luôn là trạng thái chấp nhận được.

### 3.3. Bốn tầng kết luận

1. **Designed:** có tài liệu rollback strategy hợp lý với phạm vi và dependencies.
2. **Prepared:** artifacts, quyền, capacity, tools, communication, checkpoints và runbook sẵn sàng.
3. **Rehearsed:** đã thử các bước trên môi trường/kịch bản đủ đại diện, có kết quả và failure handling.
4. **Validated in context:** khi release thực diễn ra, đã xác minh assumptions còn đúng và điều kiện rollback/restore tương thích với trạng thái runtime hiện tại.

Một runbook đầy đủ chưa chứng minh đã diễn tập. Một rehearsal tháng trước chưa chắc còn hợp lệ khi schema, IAM hoặc vendor API đã thay.

## 4. Định nghĩa mục tiêu rollback và phạm vi

### 4.1. Xác định câu hỏi về nghiệp vụ trước khi chọn công cụ

- Release phục vụ **dịch vụ và chức năng** nào, mức criticality theo BIA ra sao?
- Sự cố nào buộc phải rollback: outage, authz breach, dữ liệu sai, mất log, security vulnerability, regression?
- Mục tiêu là **khôi phục version cũ**, **giữ continuity**, **loại bỏ risk** hay **cách ly incident**?
- Có được chấp nhận **read-only/degraded mode** tạm thời không?
- Dữ liệu mất hoặc phải bù trừ tối đa bao nhiêu, ai phê duyệt?
- Những hoạt động ngoại hệ thống nào không thể đảo ngược?
- Bản cũ có đáp ứng các security policies hiện hành không?
- Có đủ con người, quyền, mạng, quota, artifact và khóa để thi hành trong sự cố không?

### 4.2. RTO/RPO và chỉ số rollback

**Recovery Time Objective (RTO)** và **Recovery Point Objective (RPO)** là các mục tiêu nghiệp vụ/phục hồi được xác định theo BIA và kịch bản; không phải số đo tự động do deploy tool tạo.

- **RTO:** khoảng thời gian mục tiêu từ mốc disruption được định nghĩa đến khi **dịch vụ đạt acceptance criteria**.
- **RPO:** mức lùi dữ liệu tối đa được chấp nhận giữa mốc disruption và điểm dữ liệu cuối cùng có thể khôi phục nhất quán.

Với rollback release không làm mất dữ liệu, RPO có thể được đặt theo yêu cầu khác với DR backup restore. Nếu phải restore snapshot cũ, cần đánh giá mất dữ liệu, khả năng replay và business compensations; **không mặc định RPO bằng 0**.

Ví dụ giả định:

| Mốc | UTC | Ý nghĩa |
|---|---|---|
| T0 | 09:00 | Disruption được xác nhận theo quy tắc tổ chức |
| Tdecision | 09:12 | Người có thẩm quyền quyết định rollback |
| Ttraffic | 09:25 | Lưu lượng chuyển sang môi trường rollback |
| Tdatabase | 09:31 | Đối soát dữ liệu và schema phù hợp hoàn tất |
| Tsecurity | 09:37 | Auth, audit, secrets và required control tests PASS |
| Tservice | 09:41 | Functional + security acceptance hoàn tất |

Nếu định nghĩa **service recovered** là 09:41, thời gian phục hồi thực tế từ T0 là **41 phút**. Không dùng mốc 09:25 để kết luận RTO nếu ứng dụng ở thời điểm đó chưa phục vụ dữ liệu nhất quán hoặc security gates chưa đạt.

### 4.3. Khoảng thời gian quyết định và thi hành

Có thể phân tích:

\[
T_{\text{total recovery}}
= T_{\text{detect}}
+ T_{\text{decide}}
+ T_{\text{execute}}
+ T_{\text{validate}}
\]

Với điều kiện các mốc được định nghĩa nối tiếp, không chồng lấp và cùng time base. Trong thực tế nhiều thao tác song song; nên lưu timestamp thô thay vì gán các nhãn mơ hồ.

Nếu mất 30 phút vì không có quyền truy cập artifact hoặc approver không thể liên hệ, việc tối ưu tốc độ chạy command thêm 20 giây không giải quyết được bottleneck.

### 4.4. Phạm vi kịch bản

Các kịch bản cần chọn phù hợp rủi ro:

- Code regression khi deploy mới.
- Bad IAM/security policy.
- Database migration không tương thích.
- Loss of telemetry/detection sau update.
- KMS key rotation khiến đọc backup thất bại.
- Partial rollout giữa regions/clusters.
- Load balancer/DNS route sai.
- Vendor API change không backward-compatible.
- Known-vulnerable rollback image.
- Security incident đòi hỏi containment và trusted recovery.
- Recovery team thiếu privileged access khi IdP outage.

Không cần giả định một bài diễn tập bao phủ tất cả. Mỗi kịch bản phải có **scope, prerequisites, fault trigger, acceptance criteria, limitations và bằng chứng**.

## 5. Reversibility assessment: điều gì có thể đảo ngược?

### 5.1. Bảng phân loại

| Loại thay đổi | Đảo ngược thuận lợi hơn khi | Rủi ro khi rollback |
|---|---|---|
| Stateless application code | API contracts backward-compatible, artifact sẵn, config không phụ thuộc bản mới | Bản cũ có vulnerability hoặc không hiểu token/schema mới |
| Container image | Pinned digest, rollout history, image trusted, admission cho phép | Registry xóa image, signature expired/revoked, policy mới chặn |
| IaC config | State/plan được bảo vệ, resource có thể restore | IaC destroy/xóa resource có dữ liệu hoặc khiến keys biến mất |
| IAM policy | Phiên bản trước được lưu, emergency access sẵn | Quay về policy cũ mở lại quyền nguy hiểm |
| Feature flag | Flag thực sự tách tính năng khỏi data effects | Async job đã gửi thông tin hoặc ghi dữ liệu |
| Database additive schema | Các bản app đều đọc/ghi tương thích | Dữ liệu mới không được client cũ hiểu |
| Database destructive schema | Snapshot hợp lệ, replay/reconciliation có kế hoạch | Restore cũ làm mất giao dịch hoặc phá constraints |
| KMS/key rotation | Old key được giữ hợp lệ, key access/metadata đúng | Restore không decrypt, thu hồi key phá dữ liệu |
| Network/DNS | Route cũ sẵn, TTL và dependencies được hiểu | DNS/cache chậm, session cũ vẫn tới phiên bản lỗi |
| Event schema | Producer/consumer hỗ trợ nhiều version | Message cũ/mới không tương thích, replay sai |
| Third-party integration | Vendor hỗ trợ rollback/old API và token scopes cũ | Hành động external đã thực hiện không thể đảo |
| Data deletion/retention | Có snapshot được phép giữ và lý do khôi phục hợp lệ | Phục hồi dữ liệu đáng lẽ phải xóa, vi phạm nghĩa vụ |

### 5.2. Hệ số “có thể đảo ngược” không phải một điểm số đủ dùng

Có thể gắn trạng thái:

- **REVERSIBLE_WITH_VERIFIED_RUNBOOK:** đã thử và có evidence trong scope.
- **REVERSIBLE_WITH_CONDITIONS:** chỉ đảo được nếu key/schema/data volume thỏa điều kiện.
- **PARTIALLY_REVERSIBLE:** khôi phục dịch vụ được nhưng cần reconcile/replay dữ liệu.
- **FAIL_FORWARD_REQUIRED:** không thể trở về thiết kế cũ mà vẫn giữ bất biến.
- **IR_RECOVERY_REQUIRED:** nếu nghi compromise, phải dựng từ nguồn tin cậy chứ không chỉ rollback.
- **UNKNOWN:** chưa có evidence hoặc assumptions chưa được xác minh.

**UNKNOWN không được báo là READY.** Ngược lại, không nên mặc định toàn bộ release nguy hiểm chỉ vì chưa có test scenario không liên quan; cần triage theo impact và remediation plan.

### 5.3. State map trước/sau thay đổi

Một rollback assessment nên liệt kê:

1. **Application:** commit, image digest, runtime configuration, feature flags.
2. **Infrastructure:** networks, ingress, egress, DNS, LB, autoscaling, region/quota.
3. **Identity:** human/workload roles, tokens, sessions, break-glass.
4. **Crypto:** KMS keys, encryption metadata, certificate trust, secrets.
5. **Data:** schema version, new fields, migration checkpoint, backup and transaction log.
6. **Messaging:** topics, consumers, schema registry, offsets, pending jobs, deduplication.
7. **Observability:** log sources, parser versions, alert routes, event retention.
8. **External systems:** webhook, vendor APIs, payment processors, export jobs.
9. **Business:** orders/payments already completed, invoices, notifications and customer-visible state.
10. **Assurance:** control requirements hiện hành, exceptions, finding/incident và evidence.

Mỗi hạng mục cần chỉ ra **tác động của rollback**, **test xác minh** và **owner**.

## 6. Rollback readiness gates trong release assurance

### 6.1. Bốn câu hỏi trước phê duyệt

1. **Có đường quay lui/đi tiếp tin cậy?** Đã chọn strategy phù hợp từng stateful dependency?
2. **Có đủ điều kiện thi hành?** Artifact, quyền, capacity, checkpoint, key, runbook, người trực?
3. **Có cơ chế biết khi nào phải kích hoạt?** Monitoring, threshold, decision maker, stop condition?
4. **Có thể xác nhận trạng thái sau phục hồi?** Functional, integrity, security, data loss, observability và business acceptance?

Không nên ghi gate **PASS** chỉ vì trong ticket có URL đến runbook không được diễn tập.

### 6.2. Ma trận gates tham khảo

| Gate | Assertion | Evidence cần có | Kết quả không đạt |
|---|---|---|---|
| **G1 — Scope** | Affected services/assets và dependency đã được xác định | Release diff, service map, inventory | INCONCLUSIVE/REVIEW_REQUIRED |
| **G2 — Artifact trust** | Rollback image/config có nguồn gốc tin cậy, đúng policy hiện hành | Digest, provenance, scan, signing controls | BLOCK/ESCALATE theo risk |
| **G3 — Compatibility** | Old/new code, schema, queues và API version phối hợp an toàn | Contract tests, migration matrix | FAIL nếu backward compatibility cần nhưng không đạt |
| **G4 — Data recovery** | Checkpoint, backup, key và reconciliation phù hợp mục tiêu | Restore exercise, data tests, RPO plan | Không cho destructive cutover nếu thiếu |
| **G5 — Security invariants** | IAM, authz, crypto, audit và control boundaries không suy giảm ngoài phép | Effective config/negative tests | Critical control gate fail |
| **G6 — Observability** | Có thể phát hiện và xác minh lỗi, logging path hoạt động | Synthetic event, alert routing/latency | Không thể coi canary đủ quan sát |
| **G7 — Operational readiness** | Người, quyền, công cụ, quota, contact, communication sẵn sàng | Rehearsal, permission/capacity checks | Không đủ điều kiện kích hoạt |
| **G8 — Decision & timing** | Threshold, owner, go/no-go, time budget và escalation rõ | Runbook, approval, BIA link | INCOMPLETE_DECISION |
| **G9 — Post-rollback validation** | Test xác nhận service/security/data trong scope | Test plan, pass/fail criteria | Không thể xác nhận verified rollback |
| **G10 — Residual risk** | Rủi ro và ngoại lệ được quản lý đúng thẩm quyền | Risk register, expiry, compensating controls | Escalate; không tự hợp thức hóa |

Một high-risk release có thể có **critical gates bắt buộc**, còn release stateless với các guardrails đã kiểm chứng có thể đi qua quy trình tự động giản lược. Độ sâu phải theo **risk, BIA và nghĩa vụ áp dụng**, không theo số trang tài liệu.

### 6.3. Mô hình quyết định release

~~~mermaid
flowchart TD
    CHANGE["Release proposal + scope"] --> CLASS["Classify reversibility and risk"]
    CLASS --> STRAT["Rollback / fail-forward / containment strategy"]
    STRAT --> GATES{"Pre-release readiness gates?"}
    GATES -- "Fail/unknown critical" --> HOLD["Fix / rehearse / authorized risk decision"]
    HOLD --> GATES
    GATES -- "Pass within scope" --> CAN["Progressive rollout + monitoring"]
    CAN --> TRIGGER{"Safety trigger crossed?"}
    TRIGGER -- "No" --> CONT["Continue / verify full rollout"]
    TRIGGER -- "Yes" --> DEC["Incident/change owner decision"]
    DEC --> SAFE{"Is backward rollback safe?"}
    SAFE -- "Yes" --> RB["Execute verified rollback path"]
    SAFE -- "No" --> FF["Contain / fail-forward / recover"]
    RB --> VERIFY["Data + business + security verification"]
    FF --> VERIFY
    VERIFY --> CLOSED{"Acceptance achieved?"}
    CLOSED -- "No" --> DEC
    CLOSED -- "Yes" --> CLOSE["Evidence, closure and prevention"]
    CONT --> CLOSE
~~~

### 6.4. Stop conditions và time budget

Runbook cần xác định các điều kiện **không được tự tiếp tục**:

- Backup/recovery point thiếu hoặc integrity không xác minh được.
- Artifact rollback bị nghi compromise hoặc có known severe vulnerability bị khai thác.
- Sơ đồ migration không còn phản ánh state dữ liệu hiện tại.
- Key hoặc quyền decryption không đủ và không có fallback.
- Concurrency/transaction state khiến đảo chiều có nguy cơ mất/nhân đôi giao dịch.
- Logging/evidence path bị mất trong một sự cố cần điều tra.
- Affected services vượt scope runbook đã được thử.
- Thao tác có thể làm biến mất forensic evidence quan trọng.
- Người có thẩm quyền hoặc owner bắt buộc không sẵn sàng.
- Deadline dự kiến không còn có thể đạt, cần chuyển sang alternate strategy.

**Time budget** cần tính cả detection, decision, execution và validation, không chỉ thời gian chạy rollback tool. Khi vượt ngân sách thời gian, cần có **escalation và alternate recovery plan**, không tự phá thêm control để đạt mục tiêu thời gian.

## 7. Kế hoạch rollback cho ứng dụng stateless

### 7.1. Điều kiện thuận lợi

Ứng dụng stateless dễ rollback hơn khi:

- Có image/artifact digest trước release được quản lý theo retention.
- Build và deploy có provenance, kiểm integrity và phiên bản.
- Config/secrets tương thích với cả phiên bản cũ và mới.
- API contract backward-compatible đối với upstream/downstream.
- Session/token semantics không phá authentication/authorization.
- New state chỉ nằm trong external services có xử lý tương thích.
- Load balancer/DNS/mesh có cách chuyển traffic nhanh và kiểm chứng được.
- Có capacity để chạy phiên bản cũ trong thời gian failback.
- Observability cho phép so sánh trước/sau và phát hiện lỗi.

Ngay cả service “stateless” có thể phụ thuộc database, cache, queue và IdP stateful; vì vậy chỉ được kết luận **ứng dụng stateless**, không suy ra **toàn bộ release stateless**.

### 7.2. Progressive delivery và rollback

| Chiến lược | Thuận lợi | Điểm cần review |
|---|---|---|
| **Rolling update** | Không cần môi trường song song đầy đủ | Pod cũ/mới cùng chạy, schema compatibility, max unavailable |
| **Canary** | Giới hạn blast radius và quan sát trước mở rộng | Sample tenant/traffic đại diện, guardrails và promotion criteria |
| **Blue-green** | Có môi trường trước đó để chuyển traffic | Shared DB, writable state, DNS caches, capacity, security policies |
| **Feature flags** | Vô hiệu logic mới nhanh | Async side effects/data migrations vẫn còn |
| **Immutable deployments** | Giảm khác biệt runtime và hỗ trợ provenance | Artifact cũ vẫn trusted, keys/config còn hợp lệ |
| **Shadow traffic** | Quan sát đường tính toán mới ít ảnh hưởng | Không tạo side effects, tránh rò dữ liệu nhạy cảm qua shadow |

**Rollback command thành công** chỉ nói controller chấp nhận thay đổi. Cần xác minh **mọi pod/instance/region** liên quan đã nhận đúng version và traffic không còn đi vào phiên bản lỗi.

### 7.3. Kubernetes example: evidence cần thu

Một runbook không nên chỉ ghi “kubectl rollout undo”; cần chỉ ra namespace/workload, context, target revision, image digest và các control gates.

~~~yaml
rollback_plan:
  strategy: "kubernetes-progressive-rollback"
  scope:
    environment: "production"
    cluster: "cluster-example"
    namespace: "payments"
    workload: "payments-api"
  known_good:
    application_revision: "rev-41"
    image_digest: "EXAMPLE_TRUSTED_DIGEST"
    configuration_revision: "config-12"
  prerequisites:
    - "Verified artifact provenance and current security policy"
    - "Database schema compatible with rev-41"
    - "IAM and KMS configuration remain compatible"
    - "On-call roles and cluster authorization tested"
  trigger:
    - "Confirmed cross-tenant authorization regression"
    - "Critical payment integrity check fails"
    - "Loss of required audit event path"
  steps:
    - "Freeze promotion and preserve current evidence"
    - "Confirm target revision and scope"
    - "Apply approved rollback through controlled CD mechanism"
    - "Verify all affected workloads are at the intended digest"
    - "Run transaction, authz and logging acceptance tests"
  stop_conditions:
    - "Schema or key compatibility unknown"
    - "Rollback artifact fails trust/security gate"
  closure:
    - "Business and security approvals documented"
    - "Evidence recorded and findings assigned"
~~~

YAML là **mẫu hướng dẫn**, không phải file manifest Kubernetes hoặc pipeline chạy được ngay. Một triển khai thật phải xác minh authorization, cluster context, rollout history và deployment system thực tế.

### 7.4. Kiểm tra rollback version trước deploy

Phiên bản cũ có thể:

- Chứa lỗ hổng bảo mật mới được biết đến.
- Không hỗ trợ certificate/trust chain vừa rotate.
- Không biết cách validate token/claim mới.
- Không parse schema/event mới.
- Có cơ chế logging không đáp ứng requirement hiện tại.
- Đã bị thu hồi chữ ký hoặc artifact không còn trusted.
- Không tương thích queue messages vừa phát.

Vì vậy **known-good không đồng nghĩa known-safe forever**. Danh sách rollback candidates phải được review khi security baseline/threat/certificate thay đổi.

## 8. Dữ liệu và schema: nơi rollback thường khó nhất

### 8.1. Vì sao schema/data migration làm mất reversibility?

Ví dụ release V2 thêm trạng thái **PENDING_REVIEW** cho giao dịch. V1 chỉ hiểu APPROVED và REJECTED. Nếu V2 đã ghi nhiều giao dịch PENDING_REVIEW rồi rollback code về V1, ứng dụng có thể:

- Không đọc được trạng thái mới.
- Đọc sai và xác nhận giao dịch chưa hoàn tất.
- Rơi vào error retry vô hạn.
- Ghi đè trạng thái với default không hợp lệ.
- Xử lý lặp vì consumer semantics đổi.

**Lùi schema để V1 chạy** có thể yêu cầu xóa/chuyển dữ liệu đã tạo, gây vi phạm tính toàn vẹn. Không thể coi schema rollback là an toàn nếu chưa kiểm các trạng thái đã phát sinh.

### 8.2. Expand–migrate–contract

Một chiến lược khả dụng với nhiều thay đổi database:

1. **Expand:** thêm schema/field/index mới tương thích V1 trong khi triển khai V2.
2. **Adapt:** các phiên bản cũ/mới cùng có thể đọc/ghi trong cửa sổ được định nghĩa.
3. **Migrate:** chuyển dữ liệu theo batch, checkpoint và idempotency, theo dõi lag.
4. **Validate:** đối soát integrity, authorization, data classification và backup.
5. **Cut over:** chuyển traffic/consumers khi hệ thống sẵn sàng.
6. **Contract:** chỉ xóa đường cũ sau khi rollback window kết thúc và risk/approval cho phép.

Ưu điểm là **giữ cửa sổ tương thích** để có thể lùi application trong khi schema còn mở rộng. Không phải mọi hệ thống đều áp dụng được; destructive changes, data law, key rotation và vendor APIs cần strategy riêng.

### 8.3. Backward/forward compatibility matrix

| Ứng dụng | Database/schema v1 | Schema mở rộng v1+v2 | Schema chỉ còn v2 |
|---|---|---|---|
| **Application v1** | Đạt theo test cũ | Chỉ PASS nếu kiểm backward compatibility | Có thể FAIL, không cho rollback mù |
| **Application v2** | Có thể FAIL nếu thiếu field | PASS nếu test đầy đủ | PASS nếu dữ liệu được migrate đúng |
| **Rollback về v1 sau V2 ghi dữ liệu** | Chỉ được xem xét khi có conversion/replay | Có thể an toàn với dual-read và invariants | Thường cần fail-forward hoặc restore phù hợp |

Bảng là mô hình định tính; verdict thực tế phải dựa **contract tests trên version thật**.

### 8.4. Checkpoint, reconciliation và transactional integrity

Cần định nghĩa:

- Timestamp và transaction sequence cuối cùng được công nhận.
- Snapshot/backup, WAL hoặc event log dùng để replay.
- Khả năng đối chiếu số giao dịch, balance/ledger, foreign keys và states.
- Cách dừng writers/consumers để tránh ghi song song không kiểm soát.
- Idempotency keys, duplicate detection và exactly-once claims nếu có.
- Dead-letter queues, retry offsets, ordering và poison messages.
- Tình huống backfill vào external systems và dữ liệu đã thông báo khách hàng.
- Audit trail cho migration/replay actions và quyền operator.
- RPO và tập transaction cần manual reconciliation khi không thể replay.

**Checksum của file backup** không thay cho kiểm integrity ở mức business transaction. Bản sao byte hợp lệ vẫn có thể chứa trạng thái dữ liệu không nhất quán tại application.

### 8.5. Rollback data và nghĩa vụ bảo vệ thông tin

Một bản restore từ thời điểm cũ có thể:

- Khôi phục dữ liệu đã được xóa theo yêu cầu hợp lệ.
- Phục hồi quyền/quy trình consent cũ.
- Làm bản sao chứa dữ liệu nhạy cảm vào region không được phê duyệt.
- Phát tán token/secret cũ đã phải hủy.
- Giữ sai retention hoặc làm mất audit records mới.

Security reviewer cần có **data protection/privacy check** tương ứng với nghĩa vụ áp dụng trước khi restore hoặc replay lớn. “Có backup” không đồng nghĩa được phép khôi phục mọi dữ liệu vào bất kỳ nơi nào.

### 8.6. Chọn fail-forward khi rollback làm sai dữ liệu

Fail-forward có thể là lựa chọn đúng khi:

- Schema v2 đã xử lý nhiều data states không biểu diễn trong v1.
- Vendor chỉ hỗ trợ API v2.
- Old key đã bị thu hồi hợp lệ và không thể/không nên khôi phục.
- Rollback image cũ chứa một vulnerability critical.
- V1 không có tenant isolation mà requirement mới bắt buộc.
- External side effects không thể hoàn tác.
- Data restore khiến RPO vượt giới hạn business.

Khi đó, **giữ/đưa dịch vụ về safe degraded mode** trong lúc phát hành hotfix tương thích có thể giảm rủi ro hơn cố gắng đảo cả hệ thống.

## 9. IAM, secrets, encryption keys và phiên làm việc

### 9.1. Đảo IAM policy không đồng nghĩa thu hồi quyền thật

Khi release tạo role/service account hoặc đổi federation:

- Policies cũ/mới có thể cùng có hiệu lực trong transitional window.
- Existing sessions và tokens có thể chưa hết hạn dù policy đổi.
- Resource-based policy, trust policy, inherited grants có thể khác expectation.
- Một rollback có thể vô tình cấp lại quyền đã được thu hồi vì incident.
- Break-glass có thể bị loại bỏ khiến đội recovery tự khóa quyền.
- Secrets đã cấp cho external vendors không tự biến mất khi xóa application config.

**Assertion cần test:** principal thuộc scope chỉ có quyền cần thiết, token cũ cần revoke đã bị từ chối, required MFA vẫn enforce, emergency access được bảo vệ và audit hoạt động.

### 9.2. Key rotation và tính tương thích dữ liệu

Một đường rollback liên quan encryption cần xét:

| Tình huống | Cần kiểm |
|---|---|
| V2 mã hóa dữ liệu bằng key K2 | V1 có thể dùng/được phép dùng K2 nếu cần đọc dữ liệu mới? |
| K1 cần giữ để decrypt backup cũ | Lifecycle/retention/rotation có đảm bảo K1 không bị hủy quá sớm? |
| Recovery account cần decrypt bằng K2 | IAM/KMS policy đúng scope, controlled restore đã PASS? |
| K2 bị nghi compromise | Có được phép quay về K1, hay phải dùng trusted new key/IR recovery? |
| Secrets được rotate khi deploy | Rollback version cũ có dùng được secrets mới mà không tái kích hoạt secrets cũ? |
| Certificate chain đổi | Client/old service có trust đúng chain, expiration và revocation semantics? |

Không bao giờ đề nghị mở wildcard KMS key policy để rollback “cho nhanh” khi có cách cấp quyền tối thiểu phù hợp. Nếu security policy bắt buộc thu hồi key cũ, phải chọn strategy không phụ thuộc key đó.

### 9.3. Test keys/privileges trong môi trường recovery

- Test decrypt/restore bằng **recovery identity thật trong scope được phép**, không chỉ root/admin.
- Dùng test dataset đại diện, không để secrets/PII lộ trong logs.
- Kiểm access-denied paths cho principal không được phép.
- Xác nhận audit logs của KMS/key accesses.
- Kiểm key grants, region, quota và dependencies.
- Kiểm expired token/certificate và khả năng rotate khi IdP outage.
- Sau khôi phục, thu hồi quyền tạm được cấp thêm cho recovery.
- Ghi kết quả PASS/FAIL/UNKNOWN theo scope, timestamp và test ID.

Một database restore job thành công với tài khoản superadmin không chứng minh **runbook production** với recovery service identity có thể chạy an toàn.

## 10. Logging, detection và forensic evidence khi rollback

### 10.1. Không hy sinh auditability để phục hồi nhanh

Rollback thường xảy ra trong khoảng nhiễu loạn, khi telemetry bị giảm, nhiều operator truy cập và thay đổi IAM/config dồn dập. Đó chính là thời điểm log và bằng chứng quan trọng nhất.

Cần giữ:

- Change/deploy/rollback ID, actor, approver và event timestamps.
- Old/new image digest, config revision, migration checkpoint.
- Before/after IAM/network/KMS state trong mức phân quyền hợp lý.
- Failed alert hoặc control assertions làm kích hoạt rollback.
- Trạng thái source→collector→SIEM, parser và detection rule versions.
- Monitoring gap intervals và phương án forensic evidence thay thế.
- Incident references nếu rollback liên quan active compromise.
- Decision log và thông tin liên lạc với affected service owners.

### 10.2. Logging test end-to-end

1. Chọn một **security event** an toàn đại diện sau rollback, ví dụ controlled admin change được phê duyệt.
2. Ghi event ID, actor test, timestamp UTC và resource giả định.
3. Kiểm tại nguồn và routing/collector.
4. Kiểm event xuất hiện trong central index với required fields.
5. Kiểm detection rule/alert routing nếu thuộc security objective.
6. Kiểm pipeline freshness, drop, retry, parser errors và last-seen.
7. Lưu evidence, limitations và retest owner.

**Agent healthy** không chứng minh event quan trọng đã được giữ. Một event có mặt cũng không chứng minh mọi event trong kỳ rollback đều đầy đủ; cần xem source coverage, ingestion gaps và retention.

### 10.3. Phân biệt rollback incident response với rollback release

Nếu phát hiện **artifact có dấu hiệu bị compromise**, quay về version trước không đủ:

- Có thể attacker vẫn giữ credential/session hoặc persistence ở nơi khác.
- Backup/image “known-good” có thể đã bị nhiễm trước mốc đã chọn.
- Forensic evidence có thể bị ghi đè khi redeploy.
- Active threat yêu cầu containment, eradication, trusted recovery và credential hygiene.
- Incident commander có thể cần approval riêng cho imaging, isolation hoặc phục hồi hệ thống.

**IR recovery** cần đánh giá **trustworthiness của recovery point**, không chỉ tính tương thích code. Mốc rollback “bản trước phát hành” không tự là mốc sạch.

## 11. Runbook rollback khả thi trong áp lực sự cố

### 11.1. Runbook phải hướng dẫn một người không phải tác giả

Một runbook tốt không phụ thuộc vào kiến thức chưa viết ra hoặc máy tính cá nhân của một kỹ sư. Nó phải có:

- Mục tiêu dịch vụ và recovery criteria.
- Trigger và người có quyền quyết định.
- Preflight prerequisites và quyền thực thi.
- Tên environments/accounts/regions và cách xác minh đúng scope.
- Artifacts/revisions được phép và nguồn trust.
- Backup/restore points, schema compatibility và keys.
- Trình tự thao tác **có checkpoints và stop conditions**.
- Data consistency và security acceptance tests.
- Tiêu chí rollback tiếp/stop/escalate/fail-forward.
- Kênh thông báo, incident/change record và owner.
- Evidence collection/checkpoints, logging và audit.
- Các tình huống fail partial và lối thoát.
- Kế hoạch revocation cleanup sau khi recovery hoàn tất.
- Liên kết test rehearsal gần nhất và limitations.

### 11.2. Runbook mẫu

~~~yaml
runbook:
  id: "REL-RB-2026-008"
  version: "1.3"
  service: "payments-api"
  environment: "production"
  purpose: "Return to a security-acceptable release state"
  owners:
    release: "release-lead"
    runtime: "platform-on-call"
    data: "database-owner"
    security: "security-assurance-reviewer"
    decision: "authorized-incident-or-service-owner"
  trigger_examples:
    - "Confirmed tenant authorization violation"
    - "Transaction integrity gate failure"
    - "Required audit source becomes unavailable after release"
  approved_scope:
    clusters: ["prod-cluster-example"]
    application: "payments-api"
    database: "payments-db"
  required_prerequisites:
    - "Verify old artifact digest/provenance and security baseline"
    - "Verify schema forward/backward compatibility"
    - "Verify last consistent checkpoint and reconciliation plan"
    - "Verify IAM/KMS/logging and change approval"
    - "Verify communication and recovery personnel readiness"
  execution:
    - step: "Freeze promotion and preserve evidence"
      owner: "release-lead"
    - step: "Capture production state and checkpoint"
      owner: "platform-on-call"
    - step: "Quiesce or route affected traffic as approved"
      owner: "platform-on-call"
    - step: "Apply version-specific rollback or fail-forward strategy"
      owner: "release-lead"
    - step: "Reconcile data and pending messages"
      owner: "database-owner"
    - step: "Verify authz, keys, logging and business functionality"
      owner: "security-assurance-reviewer"
    - step: "Approve resumed normal operation and clean up privileges"
      owner: "authorized-incident-or-service-owner"
  stop_conditions:
    - "Artifact is no longer trusted"
    - "Old schema cannot interpret new data"
    - "Snapshot or recovery key unavailable"
    - "Transaction duplication/loss cannot be bounded"
  expected_evidence:
    - "Before/after inventory and deployment revision"
    - "Execution log and decision timestamps"
    - "Business reconciliation and security test results"
    - "Risk exceptions and monitoring gaps"
  closure_verdict: "NOT_YET_EXECUTED"
~~~

Đây là runbook **minh họa**, không phải lệnh đủ để vận hành production. Hệ thống thật phải có thao tác/chế độ dry-run, quyền, đường dẫn cụ thể, process control và biện pháp chống thi hành nhầm account.

### 11.3. Những tiền điều kiện thường bị quên

- Registry đã garbage-collect image cũ.
- Artifact signature/key trust bị rotate và policy không còn chấp nhận.
- Snapshot bị xóa hoặc retention không đủ.
- KMS key bị disabled, pending deletion hoặc region khác.
- Cluster hết quota, không thể chạy blue và green song song.
- DB schema đã contract, không còn backward-compatible.
- Message consumer đã đọc/sinh event mới không lùi version được.
- Incident xảy ra lúc IdP không sẵn, runbook giả định SSO.
- Certificate/secret mới không tương thích client cũ.
- Vendor deprecate API/version cũ.
- Runbook chỉ có quyền trên staging, production khác.
- Người duy nhất có quyền thực thi không trực hoặc đã nghỉ.
- Alert parser bị đổi, dashboard “xanh” do missing telemetry.
- Rollback về image cũ vi phạm policy bảo mật mới.

Nên chạy **preflight kiểm thật** cho các giả định quan trọng ngay trước release, không chỉ ký xác nhận.

### 11.4. Quyền rollback và least privilege

Quyền rollback phải đủ để ứng cứu nhưng không nên là tài khoản admin vô hạn:

- Có role định danh cho release/rollback.
- Quyền deploy, traffic switch, backup restore, KMS và IAM được tách theo chức năng.
- Chỉ mở permission đặc biệt theo just-in-time và thời hạn.
- Có emergency access khi IdP không sẵn, audit độc lập nếu có thể.
- Không cất secrets dạng plain text trong runbook hoặc artifact.
- Có approval và audit trail cho những thao tác xóa/khôi phục dữ liệu.
- Sau phục hồi, thu hồi đặc quyền tạm và kiểm session/token.
- Test thường kỳ hiệu lực quyền để không phát hiện thiếu access lúc sự cố xảy ra.

Một runbook bị bỏ qua quyền truy cập có thể trông hoàn chỉnh nhưng **không executable khi cần**.

## 12. Canary, blue-green và feature flags trong kế hoạch quay lui

### 12.1. Canary giảm blast radius nhưng không tạo reversibility tự động

**Canary** cho phép chuyển một phần traffic/tenants sang version mới, đo health/security trước khi promotion. Cần xác định:

1. **Phạm vi mẫu:** tenants, regions, traffic types, dữ liệu và quyền có đại diện cho rủi ro quan trọng?
2. **Thời gian quan sát:** có bao phủ batch processing, cache TTL, token lifetime và peak traffic?
3. **Security signals:** bất thường authorization, token errors, audit gaps, secret access, tenant leakage.
4. **Business invariants:** transaction balances, order duplication, latency, state consistency.
5. **Stop conditions:** indicator nào vượt ngưỡng bắt buộc thì dừng promotion?
6. **Rollback target:** bản nào được chọn và phiên bản ấy có còn trusted không?
7. **Data compatibility:** canary đã ghi record version mới vào database chung hay chưa?
8. **Parallel versions:** client/consumers cũ và mới có xử lý được message chung?
9. **Capacity:** nhóm stable còn đủ tài nguyên nhận lại toàn traffic?
10. **Evidence:** record theo release/digest/tenant để truy nguyên kết quả.

**Không nên canary chỉ trên tenant dễ kiểm** rồi kết luận mọi user/region đã được bảo vệ. Nếu nhóm có dữ liệu nhạy cảm hoặc privileged paths cần test riêng, phải bổ sung đúng scope.

### 12.2. Blue-green dễ chuyển traffic nhưng có shared-state risk

Blue-green có thể chuyển route về cụm trước release rất nhanh. Tuy nhiên:

- Cả hai cụm có thể ghi vào chung database/schema v2.
- Session cookies, auth claims hoặc API protocols có thể khác.
- Public DNS caching khiến traffic còn vào cụm green sau switch.
- Queue consumers có thể cùng xử lý message gây duplication.
- Encryption keys/secret versions có thể khác giữa cụm.
- Logging/detection rules có thể chỉ onboard green.
- Artifact blue có thể quá cũ so với security policy hiện hành.

Cần test **end-to-end traffic draining, read/write compatibility, credential scope và log source coverage**, không chỉ đổi màu deployment dashboard.

### 12.3. Feature flag không hoàn tác side effects

Một feature flag là cơ chế containment tốt nếu thiết kế từ trước, nhưng:

- Job background đã chạy có thể tiếp tục gửi webhook.
- Export file đã tạo vẫn tồn tại và phải quản lý quyền/retention.
- Data migration có thể đã biến đổi dữ liệu.
- Một API client có thể đã cache schema/response mới.
- Đã phát token với scope mới, flag tắt không revoke tự động.
- Đã gửi email/notification hoặc thanh toán ngoài hệ thống.

Một **kill switch** cần được review như một security control: ai được dùng, có audit, ưu tiên fail-safe, thời gian có hiệu lực và test xác nhận điều bị vô hiệu thực sự không còn reachable.

### 12.4. Promotion và rollback nên cùng dùng immutable evidence

Một release controller nên liên kết:

- Release ID và change approval.
- Source revision, pipeline run, build provenance.
- Image/artifact digest, config/secret version references.
- Traffic weights per region/tenant và timestamps.
- Các control assertions và smoke/security test results.
- Trigger thresholds và người phê duyệt rollback.
- Bằng chứng sau chuyển traffic.
- Danh sách mọi workload vẫn chạy phiên bản cũ/mới.
- Kết quả reconciliation cho stateful dependencies.

Nếu “production version” chỉ được lưu dưới một mutable tag, review khó xác nhận version thực sự được rollback.

## 13. Điều kiện kích hoạt rollback và quyết định go/no-go

### 13.1. Kích hoạt dựa trên mục tiêu bảo mật và nghiệp vụ

Các trigger có thể gồm:

| Trigger | Tín hiệu/bằng chứng cần xác minh | Hành động xem xét |
|---|---|---|
| **Authorization regression** | Controlled test hoặc cảnh báo có bằng chứng cross-tenant/privilege | Dừng promotion, isolate, rollback hoặc hotfix |
| **Critical secrets/identity gap** | Key/token có quyền sai, MFA bypass, revoke thất bại | Thu hồi/giảm quyền, đánh giá incident |
| **Transaction integrity failure** | Reconciliation mismatch, duplicates, invalid state | Stop writes khi phù hợp, preserve checkpoint, xử lý data |
| **Loss of required audit logs** | Synthetic event missing với xác minh pipeline, source silence | Dừng change/khôi phục telemetry và đánh giá blind spot |
| **Availability breach** | Error budget, latency, critical workflow failures | Switch traffic/rollback theo SLO và risk |
| **Data leakage indicator** | Incident/security alert có căn cứ | IR triage; rollback không thay incident containment |
| **KMS/backup failure** | Test decrypt/restore FAIL hoặc key access incorrect | Hold stateful cutover, correct key plan, retest |
| **Untrusted artifact** | Provenance/signature mismatch hoặc suspected compromise | Freeze rollout, isolate, trusted recovery |
| **Region/tenant asymmetry** | Một nhóm không nhận config hoặc chạy artifact cũ | Kiểm population, partial rollback nếu an toàn |
| **Third-party incompatibility** | Contract/API response khác, webhook retry/dupe | Disable integration, fail-forward/compensation |

Không nên kích hoạt rollback tự động chỉ vì một spike số liệu chưa xác nhận nguyên nhân nếu chính rollback có thể phá dữ liệu. Nhưng với **hard security gates** đã định nghĩa và có signal đáng tin, việc chờ phê duyệt quá lâu cũng có thể làm tăng tác động. Cần có policy rõ cho auto-pause, auto-rollback và human decision.

### 13.2. Decision tree an toàn

~~~mermaid
flowchart TD
    S["Security/business trigger"] --> V["Validate scope and signal quickly"]
    V --> IR{"Active compromise or sensitive data impact?"}
    IR -- "Yes" --> INCIDENT["Incident commander + containment + evidence"]
    IR -- "No" --> H["Release/operations owner assessment"]
    INCIDENT --> H
    H --> COMP{"Old artifact and data backward-compatible?"}
    COMP -- "Yes" --> OLD{"Old release still meets security baseline?"}
    OLD -- "Yes" --> RB["Rollback via approved runbook"]
    OLD -- "No" --> ALT["Fail-forward, isolation or trusted recovery"]
    COMP -- "No/Unknown" --> ALT
    RB --> TEST["Functional + data + security verification"]
    ALT --> TEST
    TEST --> PASS{"Required invariants PASS?"}
    PASS -- "No" --> ESC["Escalate, keep containment, alternate recovery"]
    ESC --> H
    PASS -- "Yes" --> REVIEW["Closure, residual risk and follow-up"]
~~~

### 13.3. Khi nào auto-rollback có thể phù hợp?

Auto-rollback hữu ích cho các thay đổi **stateless, không phá dữ liệu, có compatibility được kiểm thử** và các metric tương đối đáng tin. Để cho phép auto-rollback cần:

- Trigger có ít false positives và data-quality checks.
- Version cũ được xác minh trusted và tương thích.
- Traffic routing có khả năng drain/restore.
- Không cần quyết định dữ liệu irreversible.
- Có giới hạn vòng lặp auto-retry/rollback liên tục.
- Sự kiện được ghi log, thông báo đúng owner.
- Monitoring hậu rollback và fallback nếu rollback không đạt.
- Control không thể bị attacker lợi dụng để ép hệ thống quay về vulnerable release.

**Không bật auto-rollback** cho schema destructive/key lifecycle hoặc incident forensic-sensitive scenarios chỉ vì deployment tool hỗ trợ một cờ tự động.

### 13.4. Không đánh đồng cảnh báo và kết luận nhân quả

Một authorization alert sau deploy có thể là test thật, parser bug hoặc hoạt động tấn công. Cần điều tra nhanh nguồn, phiên bản, data quality và context để đưa quyết định. Dù chưa xác định root cause, **một nguy cơ tác động lớn có thể cần containment ngay**. Ghi rõ “signal confirmed, root cause pending”, không tự tuyên bố release là nguyên nhân chắc chắn khi chưa có chứng cứ.

## 14. Kiểm chứng trạng thái sau rollback

### 14.1. Ba lớp validation

**Lớp 1 — Deployment/runtime state:**

- Target image digest/config revision đúng scope.
- Không còn pod/instance cũ ngoài ý muốn đang nhận traffic.
- Required IAM, network, KMS, secrets, feature flags hiệu lực.
- DNS/load balancer/mesh routing khớp trạng thái mong đợi.

**Lớp 2 — Business/data state:**

- Core APIs và background workers hoạt động.
- Transactions/ledger/data records được reconciliation.
- Không có duplicate/missing messages vượt quy định.
- Third-party side effects/notifications được xử lý.
- Tồn đọng, retries, DLQ và consumer offsets an toàn.

**Lớp 3 — Security assurance:**

- Positive/negative authn/authz tests PASS.
- Privileged paths enforce control đang áp dụng.
- Old artifact đáp ứng supply-chain trust và không có risk blocker mới.
- Cryptographic keys/decrypt/restore hoạt động với least privilege.
- Audit events và detections trong scope vẫn có bằng chứng.
- No unapproved data boundary/region/retention changes.
- Temporary emergency privileges được thu hồi khi thích hợp.

### 14.2. Ví dụ validation matrix

| Assertion | Test phù hợp | PASS khi | Evidence |
|---|---|---|---|
| **REL-RB-A01: Deploy scope** | Đối chiếu cluster inventory và digest | Mọi workload cần rollback đúng target artifact | Runtime export, release diff |
| **REL-RB-A02: Access control** | Negative cross-tenant requests | Không đọc/sửa được tenant khác | Authz test results, audit events |
| **REL-RB-A03: MFA/privilege** | Effective permissions, controlled login | Không có unapproved privileged bypass | IAM snapshot, deny tests |
| **REL-RB-A04: Data integrity** | Transaction-level reconciliation | Các invariants đã chốt đạt, gap có quyết định | DB checks, reconciliation |
| **REL-RB-A05: Token lifecycle** | Test revoke/expiration | Old prohibited tokens bị từ chối | Auth test, revocation logs |
| **REL-RB-A06: Crypto/recovery** | Decrypt/restore representative data | KMS/backup hoạt động theo approved scope | Restore record, key access |
| **REL-RB-A07: Telemetry** | Synthetic security event | Event tới SIEM đúng fields/time | Source/ingest/alert IDs |
| **REL-RB-A08: Business service** | Core workflow + latency/error | Service acceptance đạt | Functional health test |
| **REL-RB-A09: Incident evidence** | Kiểm forensic/evidence references | Dữ liệu điều tra không bị xóa sai | Evidence manifest, custody |
| **REL-RB-A10: Monitoring** | Source silence/drift check | Alert khi source/critical control fail | Controlled fault test |
| **REL-RB-A11: Third party** | Idempotency và webhook replay test | Không trùng side effects ngoài tolerance | Partner test, dedupe record |
| **REL-RB-A12: Cleanup** | So quyền/session/flags tạm | Không còn đặc quyền tạm trái yêu cầu | IAM/change history |

Nên định nghĩa **PASS/FAIL/INCONCLUSIVE/NOT_TESTED** theo assertion. Một test chưa thực hiện không được coi PASS. Nếu chỉ 8/12 assertions đạt mà 4 assertions critical chưa có evidence, không nên báo “rollback successful” không kèm giới hạn.

### 14.3. Retest trên actual population

Giả sử rollout ảnh hưởng 30 deployments ở ba regions. Có 20 deployment đã về bản cũ và test PASS, 5 đang chạy bản mới nhưng được cô lập, 3 chưa kiểm và 2 bị mất telemetry.

Nếu yêu cầu mọi deployment phải ở trạng thái phục hồi đã phê duyệt, **verified recovery coverage = 20/30 = 66,7%** tại thời điểm đó. Không dùng 20/20 = 100% để tuyên bố toàn bộ phạm vi đã phục hồi; những deployment chưa xác minh vẫn nằm trong mẫu số.

Nếu có **partial rollback plan được phê duyệt**, phải xác định riêng những deployment được phép giữ phiên bản mới và test các controls của chúng; không cộng bừa vào “rollback version coverage”.

### 14.4. Evidence của rollback thực tế khác evidence rehearsal

- **Rehearsal evidence:** chứng minh quy trình có thể hoạt động trong kịch bản/điều kiện đã mô phỏng.
- **Actual execution evidence:** xác nhận trong incident/release thật đã thi hành trên đúng versions, data, scope và acceptance.
- **Ongoing evidence:** giám sát drift, delayed failures, long-running jobs và ngoại lệ sau phục hồi.

Cả ba loại hỗ trợ assurance, nhưng một loại không tự thay thế loại còn lại.

## 15. Rehearsal, tabletop và fault simulation

### 15.1. Những loại thực hành

| Bài thực hành | Mục tiêu | Giới hạn |
|---|---|---|
| **Tabletop** | Xác minh vai trò, quyết định, liên lạc, trigger, stop conditions | Không chứng minh code/data rollback chạy được |
| **Runbook walkthrough** | Tìm bước thiếu, permissions, dependencies, ambiguity | Không xác minh thời gian hoặc hiệu lực runtime |
| **Staging technical rehearsal** | Chạy rollback với artifact/schema đại diện | Có thể thiếu data volume, IAM/region khác production |
| **Pre-production controlled drill** | Test gần giống đường thật, đo gates và capacity | Cần ngăn ảnh hưởng dữ liệu/traffic thật |
| **Canary rollback test** | Xác minh trong phạm vi hạn chế với rollout thật | Không chứng minh mọi region và background workloads |
| **DR/recovery exercise** | Kiểm khôi phục failure domain lớn | Chi phí/rủi ro cao, cần approval riêng |
| **Authorized fault injection** | Thử monitoring, failure detection, rollback/stop behavior | Phải có blast-radius guardrails và khả năng dừng |

**Không thực hành fault injection trên production nếu chưa có thẩm quyền, kế hoạch an toàn và khả năng thu hồi**. Dùng môi trường và dữ liệu thử phù hợp.

### 15.2. Thiết kế rehearsal theo giả thuyết

Một rehearsal tốt có cấu trúc:

1. **Hypothesis:** “Khi deploy V2 fail, có thể chuyển về V1 mà dữ liệu/keys vẫn tương thích.”
2. **Initial state:** đúng artifact/config/schema/privilege của before/after scenario.
3. **Fault injection:** gây fail có kiểm soát, ví dụ readiness/authorization test fail trong canary.
4. **Detection:** đo thời gian từ failure đến alert phù hợp.
5. **Decision:** người có thẩm quyền chọn rollback/fail-forward theo cây quyết định.
6. **Execution:** chạy runbook, ghi commands qua logging được phép và checkpoints.
7. **Verification:** application/data/security assertions.
8. **Recovery outcome:** đo thời gian và độ lùi dữ liệu theo mốc.
9. **Evidence & debrief:** failed steps, assumptions sai, findings và corrective actions.
10. **Retest:** sửa runbook/control rồi chạy lại trường hợp lỗi quan trọng.

### 15.3. Mẫu rehearsal result

~~~yaml
exercise_id: "REL-RB-EX-2026-008"
runbook_id: "REL-RB-2026-008"
service: "payments-api"
scenario: "rollback-after-canary-authorization-regression"
environment: "pre-production-representative"
started_at: "2026-11-28T06:00:00Z"
ended_at: "2026-11-28T06:52:00Z"
scope:
  deployments_required: 8
  deployments_verified: 8
  database_schema: "expanded-v2-compatible"
  representative_data_set: "synthetic-orders-with-v1-v2-states"
fault:
  type: "controlled-authorization-negative-test-failure"
  approved_by_role: "resilience-test-owner"
timeline:
  signal_detected_at: "2026-11-28T06:06:00Z"
  rollback_decided_at: "2026-11-28T06:11:00Z"
  traffic_restored_at: "2026-11-28T06:32:00Z"
  data_verified_at: "2026-11-28T06:40:00Z"
  security_verified_at: "2026-11-28T06:47:00Z"
  business_accepted_at: "2026-11-28T06:52:00Z"
security_assertions:
  authorization: "PASS"
  iam: "PASS"
  data_integrity: "PASS"
  audit_event_delivery: "PASS"
  artifact_provenance: "PASS"
  temporary_privileges_revoked: "PASS"
result: "PASS_WITH_SCOPE"
evidence_refs:
  - "REL-EV-2026-021"
  - "REL-EV-2026-022"
  - "REL-EV-2026-023"
limitations:
  - "Preproduction data volume is smaller than production"
  - "No public DNS propagation path tested"
reviewer_role: "security-assurance"
~~~

Toàn bộ dữ liệu là **mẫu**, không phải kết quả một exercise có thật. Không suy ra production RTO sẽ đạt chỉ từ kết quả pre-production 52 phút nếu traffic, volume và dependencies khác.

### 15.4. Kiểm điều kiện bất lợi, không chỉ happy-path

- Người chạy runbook vắng mặt.
- IdP không hoạt động và cần break-glass.
- Container registry không truy cập được hoặc image đã GC.
- KMS key bị disabled hoặc region hạn chế quyền.
- Queue còn message v2 không thể đọc bởi consumer v1.
- Chỉ một region rollback thành công, một region fail.
- Data backup hợp lệ nhưng restore bị timeout vì capacity.
- Logging collector bị lỗi trong lúc rollback.
- Vendor API cũ không còn được hỗ trợ.
- Rollback image có known critical vulnerability.
- Emergency approval channel không thể liên hệ.

Bài diễn tập cần **ưu tiên các failure modes có rủi ro cao**, không phải cố gây mọi lỗi trong production.

### 15.5. Tiêu chí độ đại diện

Rehearsal test có giá trị khi các điều kiện quan trọng khớp thực tế:

- Versions và image digests.
- IAM/KMS policies và identity paths.
- Network segmentation/latency/regions.
- Data schema/content/volume và traffic shape.
- CI/CD/change workflow, secret storage và trust chain.
- Quota, capacity, DNS và load balancer semantics.
- Logging/detection/alert routing.
- Khả năng thao tác của on-call staff theo runbook.
- Mục tiêu nghiệp vụ và security assertions áp dụng.

Không nhất thiết giống production từng byte, nhưng **những khác biệt có thể làm thay đổi kết luận phải được ghi và có kế hoạch bù**.

## 16. Tính sẵn sàng về con người và quyền quyết định

### 16.1. Vai trò trong một rollback đáng tin

| Vai trò | Trách nhiệm |
|---|---|
| **Release manager** | Điều phối change, pause promotion, artifact/rollout scope, decision record |
| **Service/business owner** | Xác nhận mục tiêu nghiệp vụ, outage tolerance, degraded mode và customer impact |
| **SRE/platform/on-call** | Thực hiện routing, deployment, infrastructure rollback, theo dõi health |
| **Database/data owner** | Checkpoint, quiesce writes, restore, reconciliation, replay |
| **Identity/KMS owner** | Quyền recovery, key compatibility, revoke access, secret lifecycle |
| **Security assurance** | Kiểm control assertions, evidence quality, scope và verified outcome |
| **SOC/IR** | Triage dấu hiệu security incident, bảo toàn bằng chứng, detection continuity |
| **Privacy/legal/compliance** | Tham vấn về nghĩa vụ dữ liệu, hợp đồng, thông báo khi áp dụng |
| **Risk owner** | Phê duyệt residual risk hoặc ngoại lệ trong thẩm quyền |
| **Communications lead** | Điều phối thông báo kỹ thuật/nghiệp vụ theo policy |
| **Third-party contact** | Phối hợp vendor khi API/support/DR phụ thuộc dịch vụ bên ngoài |

Một cá nhân có thể đảm nhiệm nhiều vai trò trong hệ thống nhỏ, nhưng trách nhiệm và phê duyệt đối với **critical data/security decisions** cần rõ, có cách liên lạc dự phòng.

### 16.2. RACI minh họa

R = Responsible, A = Accountable, C = Consulted, I = Informed.

| Hoạt động | Release | Service owner | Platform/DB | Security/IR | Risk owner |
|---|---|---|---|---|---|
| Định nghĩa rollback strategy | **A** | C | **R** | C | I |
| Phê duyệt business/security gates | R | **A** cho business | C | **R** security | C |
| Kích hoạt rollback thường | **A** theo policy | C | R | C | I |
| Containment khi incident | C | C | R | **A/R** theo IR plan | I |
| Data restore/destructive action | C | **A** theo governance | **R** | C | C |
| Security validation | I | C | R | **A/R** assurance | I |
| Chấp nhận residual risk | C | C | C | C | **A/R** |
| Record/closure | **A/R** | C | R | C | I |

RACI là ví dụ; các quyền phải được xây theo hệ thống và chính sách thật. Không để một operator tự thực hiện destructive restore và tự phê duyệt kết quả trong tình huống policy yêu cầu độc lập.

### 16.3. Các điều kiện về người vận hành

- On-call rotation và backup owner có thể liên hệ.
- Runbook đã được người không phải tác giả thực hiện thử.
- Privileged access được kiểm trước release, không tự giả định.
- Có đường fallback khi IdP/SSO hoặc chat tool không hoạt động.
- Có danh sách người duyệt thay thế phù hợp thẩm quyền.
- Các thao tác nguy hiểm có two-person check theo chính sách.
- Có kênh thông báo incident/change độc lập.
- Có training sau khi runbook thay đổi.
- Không phụ thuộc secrets trên laptop cá nhân.
- Có quy trình chuyển giao khi owner/vender thay đổi.

### 16.4. Communication trong và sau rollback

Một communication plan cần phân biệt:

**Trong sự cố:** ai ra quyết định, ai điều phối, ai thay đổi traffic/data, update cadence, kênh liên lạc nếu hệ thống nội bộ lỗi.

**Sau khôi phục:** tình trạng dịch vụ, residual data uncertainty, ảnh hưởng privacy/security, việc cần điều tra, khách hàng/đối tác cần thông báo theo nghĩa vụ nào.

Không công bố “không mất dữ liệu” khi chưa reconciliation. Không tự kết luận có breach chỉ vì cần rollback; nếu có bằng chứng security incident phải xử lý theo IR.

## 17. Bản cũ có thể không còn an toàn: security regression risk

### 17.1. Tái phát hành vulnerability qua rollback

Giả sử release V2 vá một CVE exploitable trên API production, nhưng đồng thời làm lỗi thanh toán. Rollback về V1 giúp thanh toán hoạt động lại nhưng tái mở lỗ hổng.

Quyết định cần so sánh:

- **Availability/integrity impact nếu giữ V2.**
- **Exposure và exploitation risk nếu về V1.**
- **Khả năng hotfix V2** để sửa lỗi chức năng.
- **Mitigation tạm** (giảm route/privilege/exposure) có test hay không.
- **Safe degraded mode** như chỉ đọc hoặc tạm dừng endpoint bị ảnh hưởng.
- **Thời gian, owner và điều kiện phê duyệt residual risk.**

Không dùng chữ “known-good” cho bản cũ nếu đã biết có vulnerability chưa mitigated. Một bản từng được approve có thể không còn đủ điều kiện security policy ở thời điểm rollback.

### 17.2. Risk decision record

Một decision khi bản cũ không an toàn cần:

1. Version mới, version rollback và known vulnerabilities.
2. BIA/security impact và kịch bản threat.
3. Sự cố hiện tại và mức độ xác nhận.
4. Alternatives: roll-forward, traffic isolation, rollback có mitigation, safe degraded mode.
5. Control bù trừ cùng test/evidence và scope.
6. Owner/approver đúng authority.
7. Thời điểm bắt đầu/kết thúc risk decision, expiry.
8. Điều kiện rút quyết định (active exploitation, mitigation failure, impact tăng).
9. Next patch/retest milestone.
10. Evidence và audit history.

Nếu một nghĩa vụ pháp lý/hợp đồng không cho phép ngoại lệ, internal risk acceptance không tự biến vi phạm thành tuân thủ.

### 17.3. Tính sạch của điểm recovery

Trong một incident supply-chain, artifact V1/V2 đều có thể được build bằng pipeline đã compromise. Một image digest cũ không tự chứng minh nguồn tin cậy. Cần kiểm:

- Trust root và signing key có bị lộ?
- Pipeline run có được bảo vệ ở thời điểm build?
- Artifact provenance còn đáng tin và được kiểm theo policy?
- Image/package có malware/persistence, secret leak hoặc vulnerable dependency?
- Thời điểm compromise đã được khoanh vùng?
- Backup/data snapshot có sạch theo threat scenario được điều tra?
- Credential/session đã được revoke và rotation chưa?

**Trusted recovery** thường cần cơ chế IR và forensics bổ sung; rollback thông thường không đủ chứng minh đã loại bỏ attacker.

## 18. Change/release assurance liên kết với rollback

### 18.1. Những yêu cầu phải đặt từ khi thiết kế release

Rollback readiness không nên được viết vào cuối sprint. Ngay khi một thay đổi đề xuất:

- Xác định rollback horizon (cửa sổ có thể đảo).
- Xác định schema/API/queue contract versions phải tương thích.
- Chọn migration/feature flag/traffic strategy.
- Xác định data checkpoint và replay/compensation.
- Chọn artifact retention và integrity controls.
- Lập permissions và key lifecycle.
- Chọn monitoring/decision triggers.
- Định nghĩa functional/security recovery acceptance.
- Dự trù pre-release rehearsal tương xứng risk.
- Đặt owner và budget thời gian phù hợp BIA.

Một release có thiết kế **không thể rollback an toàn** vẫn có thể triển khai nếu fail-forward/recovery có đủ evidence và authority, nhưng không được gọi là “rollback-ready” theo nghĩa đảo ngược đầy đủ.

### 18.2. Release gates trước, trong và sau

| Pha | Câu hỏi | Evidence |
|---|---|---|
| **Design** | Ranh giới dữ liệu/quyền nào đổi và strategy reversal nào phù hợp? | Change impact, threat model, dependency map |
| **Build** | Artifact rollback và release artifact có trusted provenance? | Digests, build records, security scans |
| **Pre-deploy** | Schema/keys/migrations tương thích, backup và permissions sẵn? | Compatibility/restore tests, preflight |
| **Canary** | Có tín hiệu phát hiện security/business regression đủ nhanh? | Synthetic events, health/SLO/security tests |
| **Go/no-go** | Có approver và alternate strategy khi rollback không an toàn? | Decision record, runbook, risk acceptance |
| **Post-deploy** | Đã xác minh runtime/security và rollback horizon? | Population checks, actual digests, monitoring |
| **Closure** | Có evidence verified, exceptions/remediation tracking? | Release assurance report, retest results |
| **Continuous** | Artifact/keys/runbook còn tương thích khi môi trường thay đổi? | Periodic rehearsal, drift trigger, audit |

### 18.3. Change assurance khác release assurance

**Change assurance** quan tâm tác động của một thay đổi và những controls bị ảnh hưởng. **Release assurance** kiểm chứng rằng một gói/version phối hợp nhiều changes có thể được triển khai và vận hành trong các điều kiện an toàn, kể cả đường xử lý khi release thất bại.

Một release gồm 10 changes nhỏ có thể tạo **rủi ro tổng hợp** (ví dụ code V2 + schema V2 + KMS policy V2 + parser V2); dù từng ticket có approve, đường rollback của gói release vẫn có thể FAIL.

### 18.4. Thay đổi ngoài pipeline

Những thay đổi manual console, vendor, emergency hoặc autoscaling có thể khiến giả định runbook bị sai:

- IAM role bị sửa ngoài IaC.
- Key bị disable/delete schedule.
- Vendor API cũ bị deprecate.
- Cloud resource/region thay thế tự động.
- Runtime image không khớp deployment manifest.
- Log pipeline đổi parser.

Cần **drift detection và revalidation triggers** để rollback readiness không chỉ đúng tại lúc viết runbook.

## 19. Evidence contract cho rollback readiness

### 19.1. Đặc tính của bằng chứng tốt

Một evidence artifact nên trả lời:

- **Assertion:** điều kiện nào đang được chứng minh?
- **Scope:** service, env, cluster, region, data class, release version?
- **Time:** artifact được thu khi nào, kỳ test nào, còn hiệu lực không?
- **Source:** hệ thống gốc, người thực hiện, phương pháp?
- **Relevance:** có trực tiếp hỗ trợ điều kiện rollback/security không?
- **Sufficiency:** có đủ kịch bản, assets và data state?
- **Reliability:** source/method có đáng tin, role collector có quyền đúng?
- **Integrity:** artifact được bảo vệ và có thể đối chiếu?
- **Result:** PASS/FAIL/INCONCLUSIVE/NOT_TESTED và lý do?
- **Limitations:** trường hợp chưa kiểm, assumptions khác production?
- **Ownership:** ai chịu trách nhiệm và ai review?
- **Freshness:** khi version/keys/schema đổi cần test lại không?

### 19.2. Evidence register ví dụ

| Evidence ID | Artifact | Assertion | Giới hạn |
|---|---|---|---|
| **REL-EV-001** | Artifact manifest, image digest, signature/provenance | Rollback image trusted theo policy | Không chứng minh business behavior |
| **REL-EV-002** | Schema compatibility test V1↔V2 | Old app đọc được data types cần thiết | Dataset test có thể nhỏ hơn production |
| **REL-EV-003** | DB backup/restore rehearsal | Data restore và integrity gates | Không đại diện failure region khác nếu chưa test |
| **REL-EV-004** | Effective IAM/KMS permissions và deny test | Recovery identities đúng quyền | Snapshot chưa chứng minh không có drift sau đó |
| **REL-EV-005** | Synthetic audit event trace | Logging/detection hoạt động sau rollback | Một event không bao phủ mọi event class |
| **REL-EV-006** | Traffic switch exercise | Routing/proxy/DNS xử lý chuyển về bản cũ | Cache/TTL ngoài môi trường có thể khác |
| **REL-EV-007** | Transaction reconciliation report | Không có sai lệch vượt tolerance trong scope | Không bao phủ external side effects ngoài nguồn |
| **REL-EV-008** | Approved runbook và diễn tập | Con người, tools, authority có thể thực thi | Owner/permissions có thể đổi |
| **REL-EV-009** | Canary rollout/rollback record | Blast radius giới hạn, trigger hoạt động | Không chứng minh full rollout đã được kiểm |
| **REL-EV-010** | Security vulnerability review của old artifact | Không rollback vào blocker chưa xử lý | Advisories và threat exposure thay đổi theo thời gian |

### 19.3. Digest có ý nghĩa nhưng không phải bằng chứng đầy đủ

Hash/digest giúp đối chiếu một artifact với mốc tham chiếu đáng tin. Nhưng nếu attacker kiểm soát **cả artifact và digest record**, việc khớp giá trị không chứng minh an toàn. Signed provenance tăng giá trị nếu trust root được bảo vệ, nhưng không chứng minh code không có lỗ hổng. Một evidence store cần **ACL, retention, audit access, immutable/append-only safeguards khi phù hợp và review độc lập**.

### 19.4. Versioning và historical truth

Khi một rollback test FAIL rồi sau đó fix/retest PASS:

- Giữ cả lần FAIL và mốc nhận biết.
- Lưu issue, root cause, remediation và tester.
- Tạo evidence mới cho PASS, không ghi đè bản FAIL.
- Ghi version của runbook, tools, artifact, keys và schema.
- Nếu một rủi ro được accepted, lưu scope/approver/expiry riêng.
- Không chỉnh số liệu kỳ cũ thành PASS chỉ vì kỳ này đã sửa.

**Lịch sử trung thực** cho phép đánh giá khả năng phục hồi đã cải thiện thật hay chỉ do thay đổi cách đo.

## 20. Risk exceptions và quyết định khi rollback không sẵn sàng

### 20.1. Khi nào cần đánh giá ngoại lệ?

Ví dụ release cần xử lý một advisory nghiêm trọng nhưng chưa thể chứng minh rollback toàn database. Tổ chức có thể cân nhắc:

- Dừng release và áp mitigation ở version cũ.
- Chia release thành các bước tương thích.
- Lập fail-forward path thay vì cố rollback destructive change.
- Dùng read-only/degraded mode với giới hạn được phê duyệt.
- Triển khai sau khi có backup/rehearsal và đủ on-call capacity.
- Chấp thuận residual risk tạm thời nếu policy/obligations cho phép.

Không được tự chọn “deploy dù chưa sẵn sàng” chỉ vì deadline kinh doanh, cũng không được dùng “chưa có rollback” để trì hoãn vô hạn một bản vá đang cần xử lý gấp. Cần **đánh giá rủi ro hai chiều**.

### 20.2. Mẫu decision record cho ngoại lệ

~~~yaml
decision_id: "REL-RISK-2026-008"
release_id: "REL-2026-042"
service: "payments"
issue: "Data migration has no verified backward rollback"
security_objective: "Maintain transaction integrity and recoverability"
assessment:
  state: "NOT_ROLLBACK_READY_FOR_SCHEMA"
  risk_if_deploy: "Data incompatibility during failure"
  risk_if_delay: "Exposure remains on previous release"
  context_confidence: "HIGH_FOR_SCHEMA_CONDITION"
alternatives:
  - "Split expand/migrate/contract"
  - "Fail-forward correction with verified recovery checkpoint"
  - "Delay destructive contract step"
proposed_controls:
  - "Representative backup/restore rehearsal"
  - "Write quiescence and replay/reconciliation procedure"
  - "Canary with security and business acceptance"
approval:
  state: "PENDING"
  risk_owner_role: "payments-risk-owner"
  valid_from: null
  valid_until: null
conditions_to_release:
  - "Independent approval within permitted policy"
  - "No critical data-integrity or security gate failed"
  - "Fail-forward and recovery test evidence available"
next_review_at: "2026-11-29T00:00:00Z"
status: "NOT_APPROVED"
~~~

Đây là **hồ sơ giả định đang chờ phê duyệt**, không phải một exception đã có hiệu lực. Một exception hợp lệ phải có phê duyệt, phạm vi, ngày hết hạn, controls bù trừ và điều kiện review theo chính sách.

### 20.3. Ranh giới authority

Một release manager có thể quyết định rollback application theo playbook thường nhưng **không nhất thiết có quyền chấp thuận mất dữ liệu ngoài RPO, bỏ logging, mở KMS wildcard hoặc không tuân thủ nghĩa vụ bảo vệ thông tin**. Những quyết định đó phải theo thẩm quyền của service/risk/data/security owner và quy định liên quan.

**Risk acceptance không tự biến FAILED control thành PASS** và không tự miễn trừ hợp đồng/pháp lý.

## 21. Security incident, ransomware và trusted recovery

### 21.1. Khi rollback bình thường không đủ

Một deployment lỗi chức năng thường có thể xử lý bằng code rollback nếu data compatible. Nhưng với dấu hiệu **compromise**, còn phải xem:

- Điểm xâm nhập, persistence và khả năng attacker đang có quyền.
- Secrets/certificates/tokens đã bị lộ hay chưa được rotate.
- Backups/artifacts có bị attacker tác động không?
- Recovery point có trước thời điểm attacker có khả năng sửa dữ liệu?
- Control-plane identities và source-of-truth IaC có còn tin cậy?
- Forensic evidence có bị hủy nếu restore/rollback ngay?
- Có thể dựng môi trường recovery cô lập để kiểm tra trước khi mở traffic?
- Logging/detection có thể nhận biết re-compromise không?

Nếu cần, kích hoạt **incident response và cyber recovery** theo thẩm quyền, không cố gọi rollback version cũ là “đã xử lý incident”.

### 21.2. Clean recovery assertions

| Assertion | Cách kiểm có thể phù hợp |
|---|---|
| Recovery artifact được tin cậy | Provenance, known compromise window, independent verification |
| Runtime không còn persistence đã biết | Forensic triage/hunting theo scope được phép |
| Identity boundary được khôi phục | Credential rotation/revoke tests, effective permissions |
| Data integrity chấp nhận được | Transaction reconciliation, trusted checkpoints |
| Recovery keys an toàn | KMS access isolation, key lifecycle checks |
| Network isolation trước mở traffic | Egress/ingress tests, segmentation |
| Telemetry/detection hoạt động | Synthetic events, alert routing |
| Business functionality đạt | Core workflow acceptance |
| Residual uncertainties được quản trị | Incident/risk owner decision và follow-up |

Không có phương pháp đơn lẻ có thể chứng minh tuyệt đối “hệ thống sạch”. Cần nêu threat scope, evidence, methods và limitations.

### 21.3. Bảo toàn chứng cứ khi phục hồi

- Đánh dấu mốc, actor, system, volume/resource IDs theo chính sách.
- Tạo immutable/controlled copies khi được phép và phù hợp.
- Ghi source of evidence, digest/reference, cách thu và custody.
- Không đưa secrets hoặc raw customer PII vào báo cáo rộng rãi.
- Tránh ghi đè instance/log quan trọng nếu không cần thiết cho containment.
- Khi phải phục hồi khẩn, ghi rõ dữ liệu nào có thể mất/không còn quan sát.
- Liên kết incident case, change/release record và forensic evidence.

Một hành động khẩn để cứu availability có thể là lựa chọn đúng nhưng vẫn cần đánh giá hệ quả với evidence và legal/privacy obligations.
## 22. Phụ thuộc bên thứ ba và tác động không thể hoàn tác

### 22.1. Những gì release có thể đã gửi ra ngoài

Rollback không đảo ngược một tác động đã diễn ra ở hệ thống khác. Ví dụ:

- Một khoản thanh toán/hoàn tiền đã được xử lý bởi payment processor.
- Email, SMS hoặc push notification đã gửi đến khách hàng.
- Webhook đã gửi tới vendor và được đối tác xử lý.
- Dữ liệu xuất tới analytics hoặc subprocessor đã được lưu.
- Identity federation đã tạo token hoặc session trên hệ thống ngoài.
- Thay đổi DNS/certificate đã được cache tại clients.
- Khóa/dữ liệu đã được replicate sang recovery region.
- Một thông báo pháp lý/hợp đồng đã được gửi và có hiệu lực.

Một runbook chỉ restore local database có thể làm **hệ thống nội bộ không còn khớp với external effects**.

### 22.2. Compensation thay vì “đảo ngược” business event

Nếu thanh toán đã xảy ra, không được tạo một lệnh “reverse payment” tùy tiện như thể giao dịch chưa từng tồn tại. Cần:

1. Biết giao dịch gốc và trạng thái được đối tác xác nhận.
2. Xác định nghiệp vụ cho phép refund/void/compensation hay không.
3. Đánh giá idempotency, retry, settlement và audit trail.
4. Có owner và approval cho nghiệp vụ có tiền/dữ liệu nhạy cảm.
5. Thực hiện compensation qua API/process được hỗ trợ.
6. Đối soát hệ thống nội bộ với đối tác sau compensation.
7. Giữ dấu vết lịch sử, không xóa transaction để “làm đẹp” dữ liệu.
8. Đánh giá customer notification và nghĩa vụ liên quan nếu cần.

Đây là nguyên lý của **compensating business transaction**; không bảo đảm luôn có một hành động hủy hợp lệ cho mọi external effect.

### 22.3. Replay và idempotency

| Tình huống | Rủi ro | Guardrail |
|---|---|---|
| Event v2 đã được consumer xử lý, rollback producer sang v1 | Consumer hiểu khác schema | Contract/schema compatibility test |
| Replay message sau restore | Tạo đơn hàng/hoàn tiền trùng | Idempotency key và dedupe store có độ tin cậy |
| Chuyển queue offset về trước | Consumer chạy lại công việc đã gây side effect | Checkpoint, dedupe, reconciliation |
| Job đang chạy giữa chừng | Một phần dữ liệu đã xuất sang vendor | Quiesce, cancellation/compensation, audit |
| Retry do timeout với provider | Provider đã xử lý nhưng client không biết | Status lookup, idempotent retry semantics |
| DLQ có messages từ schema mới | Bản app cũ không parse được | Compatible reader, quarantine và fail-forward |

Không tự gán **exactly-once** chỉ vì message broker hoặc code có cờ idempotent. End-to-end effects cần kiểm với database, downstream API và failure scenarios thực.

### 22.4. Shared responsibility cho rollback

Vendor có thể kiểm soát API availability hoặc retention, nhưng khách hàng có trách nhiệm version pinning, token scope, data export và reconciliations. Một rollback readiness review với third-party cần:

- SLA/response contact, business hours và emergency support.
- API deprecation, backward compatibility, vendor-side flags.
- Data retention/deletion và backup export constraints.
- Client-side retry/idempotency và webhook replay semantics.
- Credential revocation và access logs cho integration.
- Testing rights và sandbox fidelity.
- Data processing/region/subprocessor change approvals.
- Khả năng exit/switch provider nếu vendor không còn rollback path.

Báo cáo chứng nhận chung của vendor không chứng minh **cụ thể API v1 còn hoạt động** tại thời điểm cần rollback.

## 23. KPI và leading indicators cho Rollback readiness

### 23.1. Chọn metric trả lời câu hỏi thực

Một KPI tốt phải có **unit, population, kỳ, nguồn, condition PASS và owner**. Không nên thưởng cho “100% runbooks đã được tạo” nếu runbook chưa được kiểm thử hoặc không có recovery access.

| KPI/KCI | Công thức hoặc đơn vị | Cần chú ý |
|---|---|---|
| **Rollback strategy coverage** | Required releases có strategy được phê duyệt / tất cả required releases | Strategy tồn tại chưa chứng minh executable |
| **Rehearsed rollback coverage** | Required release-scenario units có test PASS còn hiệu lực / tổng required units | Mẫu số lấy từ release/risk inventory, không từ tests đã chạy |
| **Validated recovery-path coverage** | Critical recovery assertions PASS / tổng mandatory assertions | Unknown và NOT_TESTED ở mẫu số |
| **Artifact retention readiness** | Approved rollback candidates còn sẵn, trusted và deployable / required candidates | Provenance và vulnerability state có thể đổi |
| **Schema compatibility coverage** | Pairs of app/schema versions required đã test PASS / required pairs | Chỉ happy-path test không đủ |
| **Recovery permission readiness** | Required IAM/KMS paths đã verified / required paths | Access có thể bị revoke/drift sau rehearsal |
| **Time to rollback decision** | Tdecision – Ttrigger, theo scenario/cohort | Không phản ánh thời gian phục hồi dịch vụ |
| **Time to business/security acceptance** | Taccepted – Tdisruption theo định nghĩa | Cần ghi RTO, data/security gates và open incidents |
| **Rollback rehearsal success** | Exercises đạt acceptance / exercises đã thử hoặc required exercises theo metric | Phải phân biệt test completion và test effectiveness |
| **Data reconciliation exceptions** | Số sai lệch giao dịch chưa giải quyết sau rollback | Count thấp không chứng minh population đầy đủ |
| **Post-rollback control regressions** | Confirmed security failures sau rollback | Cần monitoring/telemetry đủ để phát hiện |
| **Runbook freshness** | Required runbooks được xem/test lại sau material changes | Review văn bản không thay execution test |
| **Emergency access readiness** | Required recovery roles/paths được test trong scope | Không cho là có quyền chỉ vì account tồn tại |
| **Rollback-trigger detection latency** | Tsignal – Tfailure, theo khả năng xác minh | Mốc failure có thể không biết |
| **Evidence quality gap** | Assertions thiếu evidence hợp lệ / mandatory assertions | Không tự coi missing evidence là technical FAIL |
| **Rollback re-introduced vulnerabilities** | Số lần rollback làm tái xuất hiện unapproved critical exposures | Phải xét thực tế deployed scope và time window |

### 23.2. Công thức coverage

Chọn **unit = release × required rollback scenario** cho một quý:

\[
\text{Verified Rollback Readiness Coverage}
=\frac{\text{Required scenario units có rehearsal PASS còn hiệu lực}}
{\text{Tổng required scenario units}}\times 100\%
\]

Giả sử có 40 scenario units cần kiểm trong kỳ:

- 26 PASS.
- 5 FAIL.
- 6 NOT_TESTED.
- 3 INCONCLUSIVE (quyền/telemetry thiếu).

**Verified coverage = 26/40 = 65%.** Không báo 26/31 = 83,9% là toàn coverage khi đã loại 9 đơn vị chưa xác minh; tỷ lệ đó, nếu dùng, chỉ phản ánh pass rate trong một tập xác định khác.

### 23.3. Không dùng metric để khuyến khích che rủi ro

Các anti-pattern:

- Loại release khó khỏi risk inventory để KPI đẹp.
- Đổi scope rehearsal sang schema đơn giản không đại diện.
- Đánh test PASS vì runbook đã được đọc chứ chưa chạy.
- Xóa failed rehearsal sau khi retest PASS.
- Tính thời gian rollback đến lúc đổi traffic, không đến security acceptance.
- Đưa accepted risk/exception vào numerator PASS.
- Không ghi những recovery exercises đã thất bại vì “không liên quan production”.
- Giảm số lượng required scenarios bằng cách gọi tất cả changes là stateless.
- Bỏ qua security regression của old artifact để đạt recovery time.
- Chỉ test khi người viết runbook có mặt.

Nên báo đồng thời **coverage, quality, failures, unknowns, critical blockers và verified improvement**, không chỉ một overall readiness score.

### 23.4. Theo dõi tail risk và sample size

Một vài rollback exercises trong năm có thể có thời gian rất khác nhau. Ví dụ: **8, 10, 12, 15 và 135 phút**:

- Mean = **36 phút**.
- Median = **12 phút**.

Median phản ánh ca điển hình hơn, nhưng trường hợp **135 phút** có thể vi phạm RTO của một service critical. Cần ghi **count, scope, outliers, maximum, failed cases và data loss/impact**, không dùng một trung bình chung che tail failure.

Với tập rất nhỏ, p95/p99 dễ gây ấn tượng thống kê không đúng; khi báo cần kèm sample size và giới hạn diễn giải.

## 24. Mẫu hồ sơ Rollback readiness dùng cho release gate

### 24.1. Readiness record tổng hợp

~~~yaml
release_id: "REL-2026-01128-PAY"
security_assurance_id: "REL-ASSURANCE-2026-044"
service: "payments-api"
environment: "production"
created_at: "2026-11-28T07:00:00Z"
scope:
  regions: ["region-example-a"]
  clusters: ["cluster-a"]
  affected_services:
    - "payments-api"
    - "payments-worker"
    - "payments-db"
  data_classes:
    - "payment-records"
    - "customer-identifiers"
risk_context:
  service_criticality: "HIGH"
  release_risk: "HIGH"
  key_threats:
    - "Cross-tenant data disclosure"
    - "Transaction integrity failure"
    - "Loss of mandatory audit events"
before_after:
  current_release: "v2"
  rollback_candidate: "v1"
  rollback_artifact_digest: "EXAMPLE_DIGEST_NOT_REAL"
  config_revision: "cfg-17"
  database_schema: "expanded-compatible-v2"
strategy:
  application: "controlled-progressive-rollback"
  database: "retain-compatible-expanded-schema"
  messaging: "quiesce-and-reconcile-before-resume"
  secrets: "new-secret-remains-valid-with-v1"
  alternative: "fail-forward-or-safe-read-only-mode"
prerequisites:
  artifact_trust: "VERIFIED_WITH_SCOPE"
  schema_compatibility: "PASS_WITH_SCOPE"
  backup_restore: "PASS_WITH_SCOPE"
  kms_permissions: "PASS_WITH_SCOPE"
  recovery_capacity: "VERIFIED_WITH_SCOPE"
  runbook_access: "PASS_WITH_SCOPE"
  logging_detection: "PASS_WITH_SCOPE"
exercise:
  rehearsal_id: "REL-RB-EX-2026-008"
  date: "2026-11-28"
  scenario: "authorization-regression-during-canary"
  verdict: "PASS_WITH_SCOPE"
  limitations:
    - "No production-scale queue backlog included"
    - "Public DNS caches not exercised"
acceptance:
  data_integrity: "mandatory"
  effective_authorization: "mandatory"
  audit_event_flow: "mandatory"
  trusted_artifact: "mandatory"
  business_workflow: "mandatory"
decision:
  readiness_state: "READY_WITH_LIMITATIONS"
  allowed_release_scope: "canary-first"
  owner_role: "release-risk-owner"
  reviewer_role: "security-assurance"
  approval_state: "PENDING_REAL_APPROVAL"
  next_review_trigger:
    - "database-schema-contract"
    - "key-rotation"
    - "third-party-api-change"
evidence_refs:
  - "REL-EV-001"
  - "REL-EV-002"
  - "REL-EV-003"
  - "REL-EV-004"
~~~

Bản trên là **dữ liệu mẫu**. Vì approval chưa có, trạng thái **READY_WITH_LIMITATIONS không phải quyền triển khai production**. Hệ thống thật phải xét chính sách go/no-go và bổ sung bằng chứng cho những assumptions rủi ro cao.

### 24.2. Phân biệt readiness state với release approval

| State | Ý nghĩa |
|---|---|
| **NOT_ASSESSED** | Chưa đánh giá rollback/recovery strategy |
| **DESIGNED_NOT_TESTED** | Có strategy/runbook nhưng chưa kiểm chứng |
| **PREPARED_PENDING_REHEARSAL** | Prerequisites có, cần thử scenario bắt buộc |
| **READY_WITH_SCOPE** | Các required gates đã được chứng minh trong scope |
| **READY_WITH_LIMITATIONS** | Có evidence cho phần scope nhưng còn giới hạn đáng kể cần quyết định |
| **NOT_READY** | Một hoặc nhiều critical assertions FAIL hoặc strategy không executable |
| **UNKNOWN_DATA_QUALITY** | Evidence thiếu/stale hoặc không đủ coverage để kết luận |
| **APPROVED_FOR_RELEASE** | Quyết định go-live theo thẩm quyền, có thể có điều kiện |
| **ROLLBACK_EXECUTED_UNVERIFIED** | Đã chạy rollback nhưng chưa chứng minh acceptance |
| **ROLLBACK_VERIFIED** | Kết quả phục hồi đạt assertions theo scope, có evidence |
| **FAIL_FORWARD_ACTIVE** | Đang phục hồi bằng strategy khác, không ghi như rollback PASS |

Nếu tổ chức dùng taxonomy khác, cần giữ **ý nghĩa của design, tested, approved, executed và verified** tách biệt.

### 24.3. Decision log khi đổi strategy

Khi plan từ rollback chuyển sang fail-forward, ghi:

- Tại sao rollback không an toàn (schema, keys, vulnerability, data).
- Trigger/evidence mới và thời điểm nhận biết.
- Alternatives và risk tradeoffs.
- Authority phê duyệt strategy.
- Service/data exposure hiện tại và controls tạm.
- Deadline, owner, test plan mới.
- Ghi nhận changes/versions thực tế.
- Retest và quyết định khôi phục hoạt động bình thường.

Không chỉnh lại runbook lịch sử để giả như ban đầu mọi thứ đã được dự liệu và PASS.

## 25. Case study 1: release API mới tạo lỗi authorization giữa các tenant

### 25.1. Bối cảnh

Dịch vụ quản lý đơn hàng triển khai **API V2** để tăng tốc tìm kiếm. Ở canary, controlled test phát hiện support role của tenant A có thể đọc metadata đơn hàng thuộc tenant B. Đây là **confirmed authorization regression trong phạm vi test**, chưa phải bằng chứng đã có khách hàng bị truy cập trái phép ngoài test.

Release có:

- V1 được giữ ở blue environment, image digest đã có.
- Database schema được mở rộng để support V2 và còn backward-compatible theo test trước.
- V2 có background worker xử lý các request export mới.
- Audit event cho tính năng mới được sinh theo schema V2.
- V1 đã từng có một finding về rate limiting được sửa bằng mitigation tại edge.

### 25.2. Trigger và quyết định

**Trigger:** negative tenant isolation test FAIL. Theo giả định policy, đây là hard security gate, không tiếp tục promotion.

Triage cần:

1. Dừng rollout V2, bảo toàn evidence và trace IDs.
2. Xác minh scope: tenant/resource/endpoint, có traffic thật nào bị ảnh hưởng?
3. Xem V1 có còn đáp ứng authz/rate-limit baseline và artifact trust không.
4. Kiểm worker/batch jobs đã tạo side effects/data ở schema mới chưa.
5. Chọn rollback API/worker sang V1 hoặc disable export flag theo strategy.
6. Đối soát authz của V1 với schema V2 trên synthetic tenants.
7. Kiểm log/detection sau traffic switch.
8. Cập nhật finding, remediation, test regression và decision record.

### 25.3. Những phép kiểm bắt buộc

| Test | Câu hỏi | Kết quả chấp nhận |
|---|---|---|
| Artifact verification | V1 image/trust còn đáp ứng policy? | Đúng digest/provenance, không critical blocker chưa xử lý |
| Schema compatibility | V1 đọc được records V2 đã ghi? | Không mất/invalidate trạng thái cần giữ |
| Authz negative | Role A đọc resource B được không? | **DENY** |
| Authz positive | Role A truy cập resource A được không? | **ALLOW** |
| Export side effects | Jobs V2 đã gửi dữ liệu/links ra ngoài? | Inventory, revoke/expire/cleanup theo procedure |
| Audit | Event post-rollback có actor/resource/outcome? | Event được ghi và truy ở central store |
| Runtime coverage | Có pod/workers V2 còn chạy không? | Các workload affected đúng approved state |
| Business | Order search và hỗ trợ còn hoạt động? | Accepted functional checks đạt |
| Monitoring | Có alert khi authz bypass tái xuất hiện? | Controlled test/rule result được xác minh |

### 25.4. Kết luận assurance

Nếu toàn bộ critical tests đạt và affected deployment population được đối soát, có thể ghi **ROLLBACK_VERIFIED_WITH_SCOPE**. Cần giữ finding về authz V2, root cause và regression tests trước lần rollout tiếp theo.

Nếu V1 chỉ chạy được bằng cách mở quyền service account ngoài baseline, rollback **không đạt security acceptance** và cần thay bằng mitigation/fail-forward được phê duyệt. Không dùng availability PASS để che authz FAIL.

## 26. Case study 2: database migration và KMS rotation khiến rollback không an toàn

### 26.1. Bối cảnh

Một hệ thống giao dịch có release V3 thay:

- Database schema thành **v3-only**, xóa cột cũ.
- Encryption key từ K1 sang K2.
- Message format từ format A sang B.
- Service worker mới hỗ trợ sự kiện có trạng thái bổ sung.
- Tạo transactions và gửi một số thông báo tới đối tác trước khi phát hiện lỗi.

Một giờ sau rollout, application phát sinh lỗi với một nhóm giao dịch. Team định **re-deploy V2** ngay để khôi phục availability.

### 26.2. Reversibility assessment

| Thành phần | Câu hỏi | Kết luận sơ bộ |
|---|---|---|
| App V2 | Có hiểu trạng thái/field mới không? | Chưa kiểm, không được giả định |
| DB v3-only | Có thể revert schema mà không mất transactions mới không? | Có nguy cơ mất dữ liệu hoặc invalid state |
| K2 | V2 có thể đọc dữ liệu đã encrypt bằng K2 không? | Cần test với permission đúng |
| Queue format B | Consumer V2 parse được không? | Cần contract test/replay plan |
| External notifications | Có thể thu hồi hoặc bù trừ không? | Có thể không đảo trực tiếp |
| Artifact V2 | Có còn trusted và security-valid không? | Cần provenance/known vulnerabilities |
| Backup | Recovery point/transaction replay có đáp ứng RPO? | Phải kiểm tính nhất quán |

### 26.3. Quyết định đúng không phải “rollback càng nhanh càng tốt”

Khi chưa chứng minh compatibility, việc đưa V2 lên production có thể phá dữ liệu. Một chiến lược có căn cứ hơn:

1. Dừng hoặc giới hạn writer path rủi ro theo quy trình.
2. Bảo toàn backups, transaction logs, queue checkpoints và evidence.
3. Tách business impact: giao dịch nào đã xác nhận, đang pending hoặc cần replay?
4. Xem có **fail-forward hotfix V3** sửa lỗi mà giữ schema/keys không.
5. Nếu dùng restore, kiểm RPO và khả năng replay/compensation với đối tác.
6. Test V2→v3-only schema và K2 decrypt trong môi trường an toàn trước mọi rollback.
7. Tham vấn service/data/security/risk owners về data loss và downtime.
8. Thực hiện strategy đã phê duyệt, có stop conditions.
9. Reconcile transactions và external effects theo ID/timestamp.
10. Xác minh authorization, crypto, audit, business và backup recovery.
11. Giữ nguyên lịch sử test FAIL và quyết định không rollback.

### 26.4. Bài học

**“Restore image cũ” không phải rollback readiness** khi trạng thái dữ liệu, khóa và external effects đã đổi. Một release có destructive migration cần strategy tích hợp ngay từ thiết kế, và có trường hợp **fail-forward là lựa chọn an toàn duy nhất** trong phạm vi rủi ro được chấp thuận.

## 27. Case study 3: rollback khôi phục availability nhưng tái đưa vulnerability

### 27.1. Bối cảnh

Dịch vụ API public deploy V2 chứa security fix cho một vulnerability đã có bằng chứng khai thác ngoài thực tế, nhưng gây regression làm hỏng một luồng nghiệp vụ quan trọng. V1 trước đó hoạt động ổn định; release controller đề xuất tự động rollback về V1.

Mục tiêu security assurance là **không để một đường exploitable critical mở trở lại** đồng thời vẫn khôi phục dịch vụ ở mức nghiệp vụ chấp nhận được.

### 27.2. Lựa chọn cần so sánh

| Phương án | Lợi ích | Rủi ro cần quản lý |
|---|---|---|
| **Rollback V1 không mitigation** | Khôi phục behavior cũ nhanh | Có thể tái đưa exploitable vulnerability vào Internet |
| **Rollback V1 với verified isolation** | Giữ một phần chức năng, giảm exposure | Bypass paths và phạm vi phải kiểm chứng |
| **Disable broken feature trong V2** | Giữ security fix, giảm business regression | Side effects và feature flag coverage |
| **Fail-forward V2.1** | Sửa regression, giữ security improvements | Build/test nhanh có thể tạo lỗi mới |
| **Read-only/degraded mode** | Giữ data integrity và giảm attack surface | Availability/functionality bị giới hạn |
| **Traffic shift sang phiên bản sạch khác** | Có thể vừa giữ security vừa đảm bảo phục vụ | Capacity, data compatibility, trust và recovery controls |

### 27.3. Guardrails và quyết định

- Kiểm version/security fix và vulnerability applicability cho V1.
- Đánh giá active exploitation signals và Internet exposure.
- Nếu chọn mitigation, test mạng/WAF/route **đúng đường khai thác**, cả đường bypass.
- Giữ audit logs, detection, incident response và decision record.
- Không tự trừ rủi ro chỉ vì có config mitigation chưa test.
- Xem V2 có thể disable tính năng lỗi bằng safe flag không.
- Chọn owner có thẩm quyền xử lý security và business tradeoff.
- Timebox residual risk theo policy nếu cho phép; không gọi V1 “secure” khi vẫn có gap.
- Retest patch path, authz, functionality, recovery after deployment.
- Lưu follow-up cho root cause và kiểm không quay lại V1 sau khi security fix được triển khai.

### 27.4. Kết luận

Một **auto-rollback mặc định** có thể xung đột với mục tiêu security nếu quay về bản không còn trusted. Release controller cần guardrail cho **security minimum version / prohibited artifacts / trusted candidate list** và đường alternate recovery. Availability là mục tiêu cần bảo vệ, nhưng không thể đánh đổi bằng một quyết định mù quáng tái tạo lỗ hổng đã xác nhận.

## 28. Những sai lầm thường gặp khi đánh giá Rollback readiness

| Nhầm lẫn | Vì sao nguy hiểm | Cách làm phù hợp |
|---|---|---|
| “Có lệnh rollback là sẵn sàng.” | Command chưa chứng minh dữ liệu, keys, quyền và business state tương thích | Preflight, runbook rehearsal và post-rollback assertions |
| “Revert commit sẽ đảo tất cả.” | External side effects, schema/data migration, tokens không tự đảo | Before/after state map và compensation/recovery plan |
| “V1 từng an toàn nên luôn an toàn.” | Threat/vulnerability/key/security requirements đã đổi | Re-evaluate trusted artifact/security baseline trước rollback |
| “Backup job PASS nghĩa restore được.” | KMS, corruption, volume, schema hoặc account permissions có thể chặn | Representative restore/decrypt/data validation |
| “DR RTO bằng thời gian boot server.” | Service/business/security gates chưa đạt | Đo từ disruption đến accepted recovery |
| “Canary PASS nghĩa toàn production PASS.” | Tenant/region/batch/privileged paths có thể khác | Population reconciliation và targeted risk tests |
| “Blue-green rollback không động tới data.” | Cả hai environments có thể dùng chung DB/queue | Shared-state compatibility và traffic draining |
| “Feature flag tắt là hoàn tác mọi thứ.” | Job, export, webhook và token có thể đã tác động | Cancel/revoke/cleanup/compensation và verification |
| “Schema cũ đọc được dữ liệu mới.” | New enum/field/constraints có thể không tương thích | Cross-version matrix, data/state tests |
| “Đã đổi app về version cũ nghĩa mọi pod cũ.” | Partial rollout, stale instances và traffic routing | Effective digest/version/traffic checks trên toàn scope |
| “Một checksum khớp là artifact sạch.” | Không chứng minh nguồn dữ liệu trung thực hoặc không có malicious code | Trusted provenance, policy checks và incident context |
| “Đã có KMS key nên decrypt ở DR được.” | Recovery identity/grants/region khác | Authorized key/restore rehearsal |
| “Session cũ tự biến mất sau IAM rollback.” | Tokens/session grants có thể sống đến hết hạn | Revoke/expiry và negative access tests |
| “Logging agent healthy là audit liên tục.” | Event class bị drop hoặc parser mất field | Synthetic source→SIEM→alert test |
| “Không có alert nghĩa rollback an toàn.” | Có thể sensor bị mù hoặc business workflow chưa chạy | Test assertions, telemetry quality và monitoring window |
| “Dùng bản cũ có CVE là chấp nhận được vì nhanh.” | Tái đưa attack surface critical | Security candidate gate, mitigation verified hoặc fail-forward |
| “Rollback từ snapshot cũ không mất gì.” | Giao dịch mới/partner effects có thể đã xảy ra | RPO, WAL/replay, reconciliation và compensation |
| “Rehearsal staging đại diện tất cả.” | Volume, IAM, KMS, DNS, traffic khác production | Fidelity assessment và test bổ sung theo rủi ro |
| “Emergency bỏ qua review và record.” | Không kiểm soát quyền/dữ liệu và không audit được | Minimum guardrails, authority và hậu kiểm time-boxed |
| “Có risk acceptance nghĩa control đạt.” | Governance decision khác technical assurance | Giữ FAIL/unknown, scope, expiry và retest |
| “Runbook có một owner là đủ.” | Owner có thể không trực hoặc không đủ quyền | Backup owner, on-call, emergency access và rehearsal |
| “Rollback thành công khi traffic đã chuyển.” | Dữ liệu và security tests chưa đạt | Separate traffic-recovered vs accepted-recovery time |
| “Metric chỉ tính các exercises đã PASS.” | Bỏ FAIL/NOT_TESTED khỏi denominator | Required scenario inventory độc lập |
| “Đổi version rồi xóa kết quả test FAIL cũ.” | Mất audit trail, không thể học root cause | Versioned evidence và lịch sử decision |
| “Incident recovery = deploy artifact cũ.” | Attacker persistence, stolen tokens, untrusted backups | IR/cyber recovery, trusted artifacts và forensic checks |
| “Khôi phục bản sao dữ liệu nào cũng được.” | Privacy/deletion/retention/region restrictions | Data compliance/authorization review |
| “Một phiên bản rollback phù hợp mọi thay đổi.” | Schema, key, vendor API tiến hóa theo thời gian | Revalidate candidates sau material change |
| “Không cần test fail-forward nếu có rollback.” | Rollback có thể không còn khả thi sau cutover | Alternate strategy và rehearsal theo risk |

## 29. Câu hỏi tự kiểm tra và đáp án gợi ý

**Câu 1.** Một deployment Kubernetes có rollout history và lệnh undo. Có thể kết luận Rollback readiness PASS chưa?

**Gợi ý:** Chưa. Cần kiểm image trust/availability, affected deployment scope, data/schema compatibility, IAM/KMS, business và security assertions, decision/permission, rehearsal và runtime verification plan.

**Câu 2.** Release V2 thêm trường database, V1 còn đọc được dữ liệu V2 trong rehearsal. Có nghĩa rollback luôn an toàn?

**Gợi ý:** Không. Kiểm những data states/enum, async jobs, migrations, rollback window, traffic và keys thực tế; rehearsal có limitations và có thể hết hiệu lực khi V2 tiếp tục ghi dữ liệu.

**Câu 3.** Feature flag của dịch vụ export bị tắt ngay sau phát hiện lỗi. Các file export đã được tạo có tự biến mất không?

**Gợi ý:** Không. Cần inventory output, revoke/expiry/cleanup theo retention, kiểm external transfer và audit history.

**Câu 4.** Một rollback image V1 chứa CVE đang bị khai thác, còn V2 gây 5xx trên tính năng ít thiết yếu. Nên làm gì?

**Gợi ý:** Không auto-rollback mù. Cân nhắc disable tính năng lỗi trên V2, hotfix/fail-forward, safe degraded mode, hoặc isolation đã kiểm với owner/risk decision; không đưa exploit trở lại chỉ vì nhanh.

**Câu 5.** Sau rollback, HTTP 200 và CPU bình thường nhưng synthetic audit event không tới SIEM. Có được VERIFIED_CLOSED không?

**Gợi ý:** Nếu logging là critical security gate thì không. Cần kiểm source/collector/parser/route, remediation và retest; functional health khác security acceptance.

**Câu 6.** Restore database bằng admin superuser thành công, nhưng recovery service identity không có quyền KMS. Có đủ bằng chứng production restore sẵn sàng?

**Gợi ý:** Chưa. Phải thử đúng identity/quyền quy định và dữ liệu đại diện, không mở quyền wildcard chỉ để qua test.

**Câu 7.** Một vùng đã rollback 8/10 pods, hai pods còn ở version mới do thiếu capacity. Verified rollback coverage là bao nhiêu nếu cả 10 phải về V1?

**Gợi ý:** Tối đa 8/10 = 80%, nếu cả tám đã có acceptance tests đạt. Không thể coi region hoàn tất khi hai pods còn nhận traffic và vi phạm scope.

**Câu 8.** Một dịch vụ thanh toán đã gửi yêu cầu hoàn tiền tới vendor trước rollback, sau đó restore local DB về snapshot. Điều gì phải kiểm?

**Gợi ý:** External transaction outcome, idempotency/retry, reconciliation với vendor và compensation hợp lệ; không xóa lịch sử như giao dịch chưa diễn ra.

**Câu 9.** Một bài tabletop được đánh PASS, liệu nó chứng minh RTO của ứng dụng sẽ đạt trong production?

**Gợi ý:** Không. Tabletop hỗ trợ kiểm quy trình/communication, nhưng không đo được actual restore/capacity/data path. Cần technical rehearsal hoặc bằng chứng khác phù hợp.

**Câu 10.** Key K1 được thay bằng K2; ứng dụng hiện tại giải mã tốt. V1 rollback có dùng được dữ liệu mới không?

**Gợi ý:** Phải kiểm V1 hỗ trợ crypto metadata/K2, effective key policy, recovery permissions và backup keys; không suy ra từ việc V2 đọc được.

**Câu 11.** Sau rollback, data reconciliation cho thấy 12 giao dịch bị nhân đôi. SLA thời gian đã đạt. Có thể coi rollback success?

**Gợi ý:** Không nếu data integrity là mandatory acceptance. Cần containment, correction/compensation, root cause và approval theo rủi ro; timeline tốt không che integrity failure.

**Câu 12.** Một incident nghi compromise artifact từ build pipeline. Có thể chọn image build trước release làm recovery point tin cậy?

**Gợi ý:** Chưa có căn cứ. Cần xác định compromise window, pipeline trust, signing keys, persistence, credentials và forensic validation; có thể phải dùng trusted cyber recovery path.

**Câu 13.** Có 40 rollback scenario units bắt buộc; 26 PASS, 5 FAIL, 6 NOT_TESTED, 3 INCONCLUSIVE. Coverage là bao nhiêu?

**Gợi ý:** 26/40 = 65%; không được loại những scenario chưa kiểm khỏi mẫu số nếu thuộc phạm vi bắt buộc.

**Câu 14.** Một runbook đã diễn tập 6 tháng trước. Release mới đổi schema, KMS và third-party API. Có thể giữ kết luận readiness cũ?

**Gợi ý:** Phải đánh giá lại các material changes; phần test cũ chỉ còn giá trị với assumptions chưa thay. Cần retest schema/key/vendor paths.

**Câu 15.** Rollback giúp service phục vụ request sau 20 phút, nhưng security tests hoàn tất sau 35 phút. Mốc nào dùng làm accepted recovery nếu security gates bắt buộc?

**Gợi ý:** 35 phút kể từ disruption theo mốc định nghĩa, giả sử business/data gates cũng đã đạt trước đó; mốc traffic 20 phút là interim operational signal.

**Câu 16.** Một risk owner chấp thuận dùng bản cũ thiếu một control trong 48 giờ, nhưng nghĩa vụ hợp đồng yêu cầu control luôn có. Đã đáp ứng compliance chưa?

**Gợi ý:** Internal acceptance không tự miễn trừ nghĩa vụ hợp đồng. Cần review thẩm quyền/điều khoản và phương án phù hợp; tiếp tục ghi control gap và risk decision.

## 30. Bài thực hành: đánh giá rollback readiness cho release nhiều thành phần

### 30.1. Hệ thống giả định

Bạn là security assurance engineer cho một nền tảng xử lý giao dịch và hỗ trợ khách hàng. Release **R42** chuẩn bị đưa vào production có các thay đổi:

- Application API từ V1 lên V2, hỗ trợ field trạng thái giao dịch mới.
- Database schema được mở rộng, nhưng kế hoạch xóa field cũ sau 24 giờ.
- Encryption key K1 được rotate sang K2.
- Queue consumer V2 phát event format mới cho downstream.
- Một job batch export gửi dữ liệu khách hàng đã ẩn danh theo policy tới vendor.
- Role mới cho service account có quyền đọc một nhóm dữ liệu nhạy cảm.
- SIEM parser được đổi để ghi nhận event V2.
- V1 được lưu trong container registry với mutable tag; chưa có record digest được chốt.
- BIA đặt mục tiêu RTO **60 phút**, RPO **10 phút** trong kịch bản đang xét.
- Có backup job PASS nhưng chưa có restore rehearsal với K2.
- Canaries chạy ở 1/3 regions, chưa test batch jobs và vendor callback.
- Incident playbook yêu cầu evidence về actor/change/decision khi phát hành khẩn.

**Tình huống phát sinh:** Sau khi R42 nhận 15% production traffic, negative authorization test phát hiện cross-tenant data access. Cùng lúc, alert về audit log không còn hiển thị actor field. Một số giao dịch/event format V2 đã được ghi và gửi sang vendor; chưa có bằng chứng mất dữ liệu thực tế.

### 30.2. Nhiệm vụ

1. Xác định **release boundary** và liệt kê ít nhất 10 stateful/security dependencies.
2. Phân loại các thay đổi: reversible, conditional, partially reversible, fail-forward required hoặc unknown, kèm lý do.
3. Xác định **critical security invariants** cho tenant isolation, transaction integrity, IAM/KMS, logging và artifacts.
4. Viết **risk-based go/no-go** và các stop conditions trước khi mở thêm traffic.
5. Đề xuất **ba lựa chọn recovery**: rollback application, feature disable/containment, fail-forward; so sánh security và business risks.
6. Xác định liệu V1 còn có thể đọc dữ liệu trạng thái mới, event format V2 và K2 hay không; nêu test cần thiết.
7. Lập kế hoạch quiesce/write replay và reconciliation với vendor để tránh duplicate transactions.
8. Thiết kế một **rollback runbook** có owner, identity/permissions, bước thực hiện, checkpoints, rollback/fail-forward switch và monitoring.
9. Lập bảng ít nhất **12 assertions** với positive/negative tests và evidence.
10. Xác định trước khi rollback cần giữ những forensic/incident evidence gì, và cách giới hạn truy cập.
11. Dùng giả định của BIA để xác định mốc đo RTO/RPO, không coi thời gian đổi traffic là accepted recovery.
12. Thiết kế rehearsal cho schema/K2/queue với test data representative và failure injection an toàn.
13. Đề xuất cách kiểm full population (regions, pods, consumers, queues) sau rollout/rollback.
14. Đề xuất KPI readiness với required scenario denominator độc lập.
15. Viết decision record ngắn phân biệt **confirmed gap**, **unknown**, **risk acceptance** và **not applicable**.
16. Đề xuất hai preventive actions giúp release tương lai không tái phạm, một về artifact/version và một về cross-component compatibility.

### 30.3. Gợi ý hướng xử lý

**Điều chắc chắn:** trong phạm vi controlled test, authorization assertion FAIL; trong event test đã kiểm, actor field không xuất hiện như dự kiến. Đây là hai vấn đề security cần xử lý ngay; không tự suy ra đã có data breach.

**Điều chưa rõ:** V1 có tương thích K2/schema/event format V2 không, vendor đã nhận/xử lý event nào, có thể restore trong RPO/RTO không. Do đó, **không thể tuyên bố rollback V1 an toàn khi chưa kiểm**.

**Phương án giảm rủi ro ngay:** dừng promotion và giới hạn chức năng gây lỗi; bảo vệ logging/evidence; cô lập export hoặc giới hạn quyền nếu phù hợp business/security approval; tiến hành incident triage khi evidence đủ.

**Nhánh recovery:**

- Nếu V1 vẫn compatible và security-valid, dùng rollback có kiểm soát, rồi test đủ data/security assertions.
- Nếu V1 không compatible, ưu tiên fix authorization/parser ở V2 hoặc fail-forward trong safe degraded mode.
- Nếu phải restore data, đánh giá recovery point, RPO, replay, external effects và thẩm quyền; không restore tùy tiện.
- Nếu nghi compromise, kích hoạt trusted recovery/IR path thay vì chỉ quay version.

### 30.4. Ví dụ tính kết quả phục hồi

Giả sử trong rehearsal có mốc:

| Mốc | UTC |
|---|---|
| Disruption được xác nhận | 09:00 |
| Quyết định recovery | 09:09 |
| Route chuyển về stable | 09:18 |
| Data reconciliation đạt | 09:30 |
| Key + IAM + logging tests đạt | 09:42 |
| Full business acceptance đạt | 09:49 |

Nếu các security assertions và data tests bắt buộc đều PASS, **accepted recovery duration = 49 phút**, đạt mục tiêu **RTO 60 phút** của kịch bản giả định. Việc RPO **10 phút** có đạt hay không chỉ xác định được khi biết mốc **last consistent recovery point**, không suy từ RTO 49 phút.

### 30.5. Thang đánh giá

| Tiêu chí | Đạt khi |
|---|---|
| **System scope** | Xác định runtime, data, keys, identities, queue, vendor và regions |
| **Reversibility** | Không giả định backward compatibility khi chưa có test |
| **Security** | Authz, least privilege, crypto, logs và artifact trust có assertions |
| **Data integrity** | Có checkpoint, replay, dedupe, reconciliation và RPO |
| **Decision** | Stop conditions, owner, authority, risk alternatives rõ |
| **Recovery** | Có runbook thực thi được và fail-forward path nếu rollback không an toàn |
| **Evidence** | Test IDs, source, timestamps, digests, limitations và custody |
| **Verification** | Không kết luận rollback thành công trước business/security acceptance |
| **Governance** | Exception đúng quyền, scope, expiry và history |
| **Continuous** | Có trigger re-review khi schema/keys/vendor/security baseline đổi |

## 31. Checklist Rollback readiness trước, trong và sau release

### 31.1. Trước release

- [ ] Release ID, scope, service owner, business criticality và impacted populations rõ.
- [ ] Change impact bao gồm code/config, schema/data, IAM, keys, logging, network, queue và vendors.
- [ ] RTO/RPO và business/security recovery criteria được định nghĩa từ bối cảnh BIA.
- [ ] Đã phân loại fully/partially/non-reversible components bằng evidence.
- [ ] Có rollback, containment hoặc fail-forward strategy cho từng risky dependency.
- [ ] Old artifact/release candidate có digest/provenance, sẵn và trusted theo policy hiện hành.
- [ ] Bản rollback không tái mở known critical vulnerability hoặc có decision phù hợp khi không thể tránh.
- [ ] Application và database schema compatibility đã được test với dữ liệu đại diện.
- [ ] Data checkpoints/backup/restore và replay/compensation được chuẩn bị.
- [ ] KMS keys, certs, secrets, token/session semantics được kiểm với runtime cũ và mới.
- [ ] IAM/DR/recovery permissions đủ thực thi nhưng least privilege, có emergency access.
- [ ] Queues, batch jobs, third-party external effects có phương án pause/drain/reconcile.
- [ ] Feature flags/kill switch đã được kiểm quyền, audit và side effects.
- [ ] DNS/LB/mesh traffic switch có capacity và test draining/TTL phù hợp.
- [ ] Canary sample, promotion criteria, security/business monitoring và rollback triggers rõ.
- [ ] Có stop conditions, time budget, alternate strategy và escalation authority.
- [ ] Runbook có người duyệt, version, exact scope và owner/backup owner.
- [ ] Rehearsal đủ đại diện, có pass/fail evidence và limitations.
- [ ] Evidence collector, SIEM/alert routes và log integrity hoạt động.
- [ ] Data privacy/retention và regional processing conditions được review nếu ảnh hưởng.
- [ ] Release gates có decision record, không biến UNKNOWN thành PASS.
- [ ] Các ngoại lệ được approval, scope, expiry và remediation plan đúng governance.

### 31.2. Khi kích hoạt rollback hoặc fail-forward

- [ ] Xác minh trigger, severity, scope, data quality và risk; gọi IR nếu cần.
- [ ] Dừng promotion/freeze change phù hợp để giảm blast radius.
- [ ] Bảo toàn logs, deployed state, data checkpoints, decision timestamps và evidence.
- [ ] Xác nhận target artifact/config/version và security baseline hiện hành.
- [ ] Kiểm khả năng lùi database/keys/queues mà không phá dữ liệu.
- [ ] Kiểm operator context/permissions/region/service để tránh thao tác sai.
- [ ] Ghi go/no-go decision, alternate plan và người phê duyệt.
- [ ] Thực hiện traffic draining/quiesce jobs/writers theo runbook nếu cần.
- [ ] Đo thời gian và ghi execution checkpoints có source.
- [ ] Dừng khi stop condition xuất hiện, không cố ép rollback gây tổn thất lớn hơn.
- [ ] Nếu backward rollback không an toàn, chuyển containment/fail-forward/recovery đã được duyệt.
- [ ] Giữ communication/update cadence và đánh giá business/customer impact.

### 31.3. Sau rollback hoặc alternate recovery

- [ ] Tất cả affected assets/regions/pods/tenants có trạng thái runtime được xác minh.
- [ ] Artifacts đang chạy đáp ứng trust, vulnerability và signing/provenance controls.
- [ ] Positive/negative authentication và authorization tests đạt.
- [ ] IAM/service roles, break-glass và temporary privileges có hiệu lực đúng scope.
- [ ] Keys/secrets/certificates hợp lệ, không tái mở credential đã revoke.
- [ ] Transaction/data reconciliation và RPO/data-loss assessment được hoàn tất.
- [ ] Queue offsets, retry, idempotency, DLQ và external side effects được đối soát.
- [ ] Audit events source→SIEM và alert routing được thử theo required classes.
- [ ] Data encryption, retention, privacy và tenant boundaries vẫn phù hợp.
- [ ] Business workflows, latency và critical functionality đã đạt acceptance.
- [ ] Time-to-accepted-recovery được tính với mốc chính xác và công bố limitations.
- [ ] Những test FAIL/INCONCLUSIVE vẫn được giữ riêng, không gộp vào PASS.
- [ ] Residual risk, exception, owner và deadline được ghi nếu còn gap.
- [ ] Logs/forensic evidence và decision history được lưu đúng quyền.
- [ ] Điều kiện hoạt động của vendor/subprocessor đã được xác minh khi có liên quan.
- [ ] Recovery/emergency access được thu hồi hoặc review lại.
- [ ] Incident/finding được liên kết với remediation, root cause và preventive controls.
- [ ] Runbook, compatibility matrix, rollback candidate và artifact retention được cập nhật.
- [ ] Monitoring window theo business/security cycles được hoàn tất hoặc có owner theo dõi tiếp.
- [ ] Khả năng rollback ở release sau được kiểm lại khi schema/key/vendor thay đổi.
- [ ] Closure chỉ được duyệt khi có evidence đúng phạm vi và thẩm quyền.

## Kết luận

**Rollback readiness là một năng lực phục hồi có thể chứng minh, không phải nút hoàn tác.** Release có thể thay code, dữ liệu, privileges, keys, audit pipeline, queue, vendors và các ranh giới tin cậy. Muốn khôi phục an toàn phải biết thành phần nào có thể đảo, những tác động nào không thể đảo, và trường hợp nào cần fail-forward, containment hay trusted recovery. Một bản cũ từng chạy ổn định cũng có thể không còn phù hợp với security baseline hoặc dữ liệu hiện hành.

Trong **SECURITY_SECURITY_ASSURANCE**, rollback readiness được chứng minh bằng chuỗi **release scope → reversibility/security impact → rollback/fail-forward strategy → readiness gates → trusted artifacts và dependencies → rehearsal → authorized decision → controlled execution → business/data/security verification → evidence/verified closure → monitoring và cải tiến**. Khi mỗi khâu có owner, acceptance criteria, bằng chứng đáng tin, kiểm thử thực tế và giới hạn được công bố, rollback trở thành một phần hiệu quả của **release assurance liên tục**, giúp giảm tác động khi thay đổi thất bại mà không phải hy sinh tính toàn vẹn dữ liệu và các kiểm soát bảo mật quan trọng.





