# Checklist vận hành: duy trì security assurance liên tục dựa trên bằng chứng

**Checklist vận hành security assurance** là bộ câu hỏi, bước kiểm tra và tiêu chí xử lý có chủ sở hữu để xác minh rằng các **security objectives** và **security controls** vẫn được đáp ứng trong vận hành thực tế — không chỉ ở lần triển khai đầu hoặc tại một kỳ audit. Checklist tốt kết nối **rủi ro → yêu cầu → control → assertion → test → bằng chứng → quyết định → remediation/retest** thành hoạt động định kỳ và theo sự kiện, với điều kiện PASS/FAIL/INCONCLUSIVE/NOT_TESTED rõ ràng.

Bài học nằm trong chương **Tổng kết security assurance** của module **SECURITY_SECURITY_ASSURANCE**. Mục tiêu xuyên suốt là **đánh giá có bằng chứng** hệ thống đáp ứng những mục tiêu bảo mật, từ phân tích rủi ro, requirements và security controls tới testing, audit, remediation và vận hành liên tục. Vì vậy, checklist dưới đây không chỉ liệt kê những việc “nên làm” mà cho biết **ai làm, kiểm cái gì, nguồn chứng cứ, khi nào escalated, cách khép kín finding và giới hạn kết luận**.

> **Nguyên tắc cốt lõi:** Một ô đã tick không phải bằng chứng control đạt. Mỗi kết luận quan trọng cần đúng asset/identity/data population, đúng thời điểm, đúng phiên bản control, có test/evidence phù hợp và người chịu trách nhiệm. **Thiếu dữ liệu không đồng nghĩa PASS; risk acceptance không biến FAIL thành PASS.**

Các tình huống, SLA, thời gian, chỉ số và ID trong bài đều là ví dụ học tập. Tổ chức cần chọn lịch kiểm, ngưỡng cảnh báo, thẩm quyền và retention dựa trên **BIA, threat model, risk appetite, requirements/obligations áp dụng**, không dùng các ví dụ như chuẩn bắt buộc toàn ngành.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vì sao security assurance phải **liên tục theo vòng đời hệ thống**, không chỉ kiểm trước phát hành hoặc khi audit.
2. Thiết kế checklist cho **ca trực/hằng ngày, hằng tuần, hằng tháng, hằng quý và event-driven**, biết phân biệt việc cần phản ứng ngay.
3. Ánh xạ từng checkbox sang **control assertion, phạm vi, nguồn dữ liệu, owner, bằng chứng và hành động khi không đạt**.
4. Đánh giá coverage và chất lượng dữ liệu của scanner, log pipeline, asset inventory, IAM, CI/CD và recovery evidence.
5. Xác minh các control cốt lõi về IAM, privileged access, data protection, cloud/runtime, vulnerability, logging/detection, incident/DR, third-party và change/release.
6. Phân biệt **control PASS/FAIL/INCONCLUSIVE/NOT_TESTED/NOT_APPLICABLE**, remediation status, risk acceptance và exception expiry.
7. Thiết lập **decision gates và escalation paths** cho critical security boundary failure, missing evidence và detection blind spots.
8. Quản lý lịch kiểm và vòng đời bằng chứng mà không phụ thuộc một cá nhân hoặc hình ảnh dashboard.
9. Tạo mẫu **operational assurance record, finding record, review board pack và KPI** với mẫu số có căn cứ.
10. Thực hành incident/change/DR scenarios, xác định việc cần làm trước, trong và sau khi xử lý.
11. Đánh giá cách checklist bị gaming và các sai lầm tạo **false assurance**.
12. Viết báo cáo vận hành ngắn nhưng trung thực về risk, evidence, unknowns, decisions và remediation.

## 2. Checklist vận hành khác gì checklist tuân thủ trên giấy?

### 2.1. Ba câu hỏi phải trả lời

Một mục như “Đã bật logging?” quá chung. Nó chưa nói:

- Log của **asset nào**, event class gì và trong kỳ nào?
- Đã test **source → collector → index → alert** hay chỉ thấy agent healthy?
- Trường **actor/action/resource/outcome** có đúng, cần giữ bao lâu?
- Ai sở hữu source và parser?
- Nếu event mất, ai chịu trách nhiệm điều tra và có cần xử lý incident?
- Kết quả có đủ đại diện cho all critical assets, hay chỉ một sample?

Một mục tốt có dạng:

**LOG-01 / assertion:** “Mọi required privileged-change events từ Admin Portal trong production phải có actor, action, resource và outcome, đến kho log trong thời gian chấp nhận được theo policy; detection rule trọng yếu phải bắt được synthetic scenario.”

**Test:** phát sinh event kiểm soát được trên test principal, truy event ID tại source/transport/SIEM và kiểm route alert.

**Evidence:** test ID, source ID, timestamps UTC, log record đã che dữ liệu, rule version, monitor/source health, reviewer.

**Verdict:** PASS_WITH_SCOPE, FAIL, INCONCLUSIVE hoặc NOT_TESTED, kèm population và giới hạn.

### 2.2. Bốn lớp cần phân biệt

| Lớp | Claim | Ví dụ chứng cứ | Giới hạn |
|---|---|---|---|
| **Control design** | Có biện pháp được thiết kế để xử lý rủi ro | Policy, architecture, control card | Không chứng minh đã triển khai |
| **Implementation** | Config/process hiện tồn tại trong scope | IAM policy, IaC, deployment export | Có thể không hiệu lực như kỳ vọng |
| **Operating effectiveness** | Control hoạt động đúng khi thực sự dùng | Negative access tests, audit trace, restore rehearsal | Chỉ chứng minh scope/time đã test |
| **Ongoing assurance** | Sai lệch được phát hiện và xử lý khi thay đổi | Source health, drift alerts, periodic retest, findings | Cần nguồn monitoring đầy đủ và có owner |

Một screenshot “MFA: enabled” chỉ chứng minh một config đã được nhìn thấy. Nó không tự chứng minh tất cả required admin paths, local accounts, vendor access và break-glass đều được bảo vệ.

### 2.3. Checklist không thay risk analysis

Không nên có 500 mục cố định và kiểm mọi mục như nhau. Cần ưu tiên theo:

- Service/data criticality và business impact.
- Attack surface, exposure, privileged boundary và multi-tenant risks.
- Threat intelligence, actual incidents và active exploitation.
- Control failures, evidence gaps và long-running exceptions.
- BIA/RTO/RPO, vendor dependencies và operational changes.
- Applicable legal/contractual/security requirements.

Những yêu cầu bắt buộc hoặc critical gates phải được kiểm theo cách phù hợp, kể cả khi một overall score vẫn cao.

## 3. Kiến trúc vận hành: từ control library đến hành động

### 3.1. Các đối tượng cần quản trị

1. **Asset/service register:** inventory nguồn độc lập, data classification, criticality, owner.
2. **Risk register:** threat scenario, impact, treatment và residual risk.
3. **Requirement/control catalog:** objectives, requirements, control IDs, version, applicability.
4. **Control unit population:** từng asset × environment × control/assertion thuộc diện kiểm.
5. **Assurance test catalog:** test method, positive/negative cases, expected results, cadence.
6. **Evidence manifest:** source, timestamp, collection method, artifact, integrity, scope, confidence.
7. **Assessment/decision record:** verdict, assessor, limitations và escalation.
8. **Findings/remediation:** root cause, owner, deadline, fix, retest và closure.
9. **Exception/risk decision:** đúng authority, scope, finite expiry, compensating controls.
10. **Operational calendar:** ca/ngày/tuần/tháng/quý và event-driven triggers.
11. **KPI/reporting:** population, coverage, FAIL/unknown, trends, critical risk.
12. **Change/incident/DR history:** những thay đổi có thể làm evidence cũ hết hiệu lực.

### 3.2. Vòng phản hồi

~~~mermaid
flowchart LR
    CONTEXT["Assets + risks + requirements"] --> CONTROL["Versioned control library"]
    CONTROL --> TEST["Scheduled + event-driven tests"]
    TEST --> EVIDENCE["Evidence + source quality checks"]
    EVIDENCE --> VERDICT["PASS / FAIL / INCONCLUSIVE / NOT_TESTED"]
    VERDICT --> RESP["Triage + containment + remediation"]
    RESP --> RETEST["Retest + verified closure"]
    RETEST --> CONTROL
    VERDICT --> REPORT["Assurance reporting"]
    REPORT --> PRIORITY["Owner / risk decisions / priorities"]
    PRIORITY --> CONTEXT
    CHANGE["Changes / incidents / threats"] --> TEST
    CHANGE --> CONTEXT
~~~

### 3.3. Không trộn các trạng thái

| Trạng thái | Ý nghĩa thực tế | Điều không thể suy ra |
|---|---|---|
| **PASS_WITH_SCOPE** | Assertion được kiểm đạt trong asset/kỳ/test đã ghi | Không phải “toàn tổ chức luôn an toàn” |
| **FAIL** | Có bằng chứng assertion không đáp ứng | Không tự chứng minh đã có incident/breach |
| **INCONCLUSIVE** | Evidence thiếu, stale, sai source/scope hoặc xung đột | Không phải PASS và cũng chưa chắc FAIL |
| **NOT_TESTED** | Control thuộc scope nhưng chưa chạy test | Không tự N/A |
| **NOT_APPLICABLE** | Không áp dụng theo căn cứ được review | Không phải verdict PASS |
| **FIX_IMPLEMENTED** | Code/config đã sửa nhưng chưa retest effective state | Không phải verified closed |
| **RISK_ACCEPTED** | Residual risk được chấp nhận có điều kiện theo authority | Không biến primary FAIL thành PASS |
| **CLOSED_VERIFIED** | Retest đạt và điều kiện đóng được thỏa | Không xóa lịch sử thất bại hoặc rủi ro khác |

### 3.4. Vòng đời một item checklist

Mỗi mục nên có:

- Stable ID và control/assertion link.
- Scope predicate hoặc affected unit IDs.
- Evidence source và collector/assessor.
- Cadence/timezone, kỳ kiểm, freshness/validity.
- Rule xác định PASS/FAIL/UNKNOWN.
- Severity/criticality và escalation.
- Runbook hoặc remediation entry point.
- Output format, retention/access policy.
- Material-change trigger.
- Reviewer/owner và backup.
- Evidence của lần kiểm trước và next_due_at.

Nếu một item không có owner hoặc nguồn dữ liệu mất, hãy coi đó là **governance/evidence gap**, không âm thầm bỏ khỏi checklist.

## 4. Lịch vận hành theo mức độ rủi ro

### 4.1. Mẫu cadence

| Nhịp | Nội dung tập trung | Kết quả cần ghi |
|---|---|---|
| **Liên tục / near-real-time** | Critical security events, high-impact drift, source silence, access anomalies, exploited vulnerabilities | Alerts, incident/change linkage, timestamp và action |
| **Đầu ca / hằng ngày** | Tình trạng visibility, findings critical, exception expiry, pending security changes, unknowns | Daily assurance pulse và owner actions |
| **Hằng tuần** | Reconcile controls/asset population, IAM/vendor changes, vulnerability queues, detection test, remediation | Control coverage delta và action backlog |
| **Hằng tháng** | Deeper control effectiveness sampling, evidence freshness, role/access reviews, backup restore readiness, vendor exposure | Assurance review pack, gaps/decisions |
| **Hằng quý / theo policy** | Independent sampling, risk/requirement/exception governance, DR/IR exercises, framework review | Periodic assurance statement + improvement plan |
| **Theo sự kiện** | Release, IAM/key changes, incident, new cloud account, third-party/data change, recovery event | Targeted re-assessment và new evidence |

Đây là **lịch tham khảo**. Nếu một control critical chỉ được kiểm hàng quý trong khi threat có thể phát triển trong vài giờ, cần bổ sung telemetry/guardrails liên tục. Ngược lại, không cần chạy destructive DR exercise mỗi ngày để “đủ checklist”.

### 4.2. Vì sao không tất cả controls cùng tần suất?

- **MFA enforcement/privileged changes:** cần giám sát gần thời gian thực và periodic effective-state test.
- **Asset population:** cần event-driven onboarding và đối soát định kỳ.
- **IAM access review:** kiểm theo risk/role; continuous JIT expiry cho quyền tạm.
- **Application authorization:** kiểm trong CI/CD và sau material changes, cùng runtime sampling.
- **Logging/detection:** source health và alert routing có thể theo dõi liên tục; kiểm end-to-end ở cadence được phê duyệt.
- **Backup/DR:** kiểm backup freshness thường xuyên, nhưng restore rehearsal theo criticality và plan được duyệt.
- **Third-party:** đánh giá trước onboarding, khi contract/data flow đổi và theo chu kỳ risk.
- **GRC exception:** nhắc expiry/owner liên tục; risk review đúng mốc và sau material events.

### 4.3. Lập lịch từ kỳ kiểm và trigger

Một control check có thể được khởi động bởi cả **time** và **event**. Ví dụ IAM-PRIV-01 có next review vào cuối tháng, nhưng một change thêm role wildcard hôm nay phải kích hoạt review ngay. Không chờ đủ tháng để đánh giá một đường quyền mới tạo.

## 5. Định dạng checklist chuẩn cho mỗi ca vận hành

### 5.1. Một dòng checklist tốt có gì?

| Trường | Ví dụ |
|---|---|
| **Check ID** | OPS-LOG-01 |
| **Control unit** | CU-LOG01-ADMIN-PROD |
| **Criterion** | Required admin events có actor/action/resource/outcome |
| **Population** | Production admin portals và privileged paths |
| **Cadence** | Daily health + event-driven retest |
| **Source** | Source event, collector, SIEM, alert test |
| **Procedure** | Đối soát required event classes/source last-seen; synthetic test theo policy |
| **Expected** | Không source silence, schema đúng, critical detections reachable |
| **Output** | Evidence IDs, PASS/FAIL/INCONCLUSIVE |
| **Owner** | SOC engineering; Platform hỗ trợ parser |
| **If failed** | Escalate visibility gap, triage source→SIEM, recovery |
| **Review trigger** | Parser/rule/source routing change |
| **Evidence retention** | Theo audit/log retention policy và sensitivity |

Một mục quá chung nên được tách thành các **atomic checks** có acceptance riêng. Ví dụ “logging hoạt động” có thể chia **source availability**, **event fidelity**, **retention/integrity** và **detection effectiveness**.

### 5.2. Quy tắc đánh giá theo kỳ

- Đánh **PASS** chỉ khi tất cả assertions bắt buộc đã đạt theo scope, test method và data quality.
- Đánh **FAIL** khi có bằng chứng condition không đạt.
- Đánh **INCONCLUSIVE** khi nguồn mất, không đủ sample hoặc test conflict.
- Đánh **NOT_TESTED** khi thuộc scope nhưng chưa kiểm.
- Đánh **N/A** chỉ khi có applicability evidence và review hợp lệ.
- Mỗi đánh giá có **as_of_at** và **period_start/period_end** khi đo effectiveness theo kỳ.
- Kết quả hôm nay không tự thay kết quả tuần trước; giữ lịch sử và new evidence sau remediation.

### 5.3. Chọn tối thiểu cần kiểm mỗi đầu ca

Đối với ca vận hành có scope critical service:

1. **Visibility còn không?** Log source/collector/alert routing và scanner health.
2. **Có critical control failure?** Privileged access, data boundary, public ingress, crypto, payment integrity.
3. **Có high-impact change mới?** IAM, network, vendor, CI/CD, keys, release.
4. **Có active incident/vulnerability threat?** Cập nhật triage, exposure và owner.
5. **Có exception hết hạn hoặc bypass ngoài approval?** Ưu tiên critical.
6. **Có data/backup/recovery signal bất thường?** Snapshot freshness, replication lag, KMS denial.
7. **Có unknowns?** Asset mới, missing scanners, stale evidence và unverified deployments.
8. **Có hành động cần giao ca?** Owner, deadline, status, escalation và evidence references.

Không biến việc đầu ca thành ngồi xem dashboard cả giờ; nên tự động hóa nguồn tín hiệu và tập trung những **exceptions, deviations và decisions cần con người**.

## 6. Checklist ca trực và hằng ngày

### 6.1. Telemetry và khả năng quan sát

- [ ] Required production log sources trong inventory đều có last-seen/health theo kỳ vọng.
- [ ] SIEM/collector ingestion lag, drop, parser errors và storage/retention warnings được theo dõi.
- [ ] Có alert cho **source silence** của nguồn critical, không chỉ tình trạng agent/process.
- [ ] Các security detections critical không bị disable hoặc suppress ngoài approved, time-bound scope.
- [ ] Detection/alert queue và on-call routing không có lỗi không được xử lý.
- [ ] Các fields cần thiết như actor, action, resource, outcome còn nguyên với event classes đại diện theo policy.
- [ ] Những data-quality gaps có người xử lý và được ghi INCONCLUSIVE thay vì PASS.

**Evidence:** source inventory diff, ingestion health, alert IDs, controlled test results và timestamps. **Trigger:** mất critical source hoặc alert path → triage nhanh theo visibility incident/change playbook.

### 6.2. Identities và đặc quyền

- [ ] Privileged sign-ins, role changes, break-glass uses và abnormal access được xem theo detection rules.
- [ ] High-risk new grants hoặc wildcard/trust-policy changes đã qua review đúng authority.
- [ ] Temporary vendor/admin privileges đã đến hạn được revoke hoặc có decision mới hợp lệ.
- [ ] Các local/bypass paths ngoài IdP được inventoried/monitored và test theo scope.
- [ ] Secrets/KMS grants hoặc token refresh anomalies quan trọng có owner xử lý.
- [ ] Không có exception expired nhưng quyền effective vẫn mở ngoài approved response.
- [ ] Identity log sources còn ghi được events cần điều tra.

**Evidence:** IdP/IAM audit events, grant diffs, JIT lease expiry, exceptions register và selected deny tests. Không kết luận “toàn bộ quyền least privilege” chỉ từ một báo cáo role changes.

### 6.3. Cloud, runtime và release signals

- [ ] Thay đổi public ingress/egress, security groups, firewall, K8s RBAC và IAM policies được nhận diện.
- [ ] Console/out-of-band changes được đối soát với IaC/source of truth theo risk.
- [ ] Deployment critical dùng artifact/config đúng approved versions; new drift/deviation có ticket.
- [ ] Pipeline security gates không bị bypass không có decision.
- [ ] Kubernetes/container runtime alerts và admission-policy deviations có owner.
- [ ] Registry/provenance hoặc package supply-chain advisories critical được triage.
- [ ] Cloud account/project/resource mới được enroll vào baseline/monitoring.
- [ ] Không coi tool scan PASS nếu actual deployed artifact khác artifact đã quét.

**Evidence:** cloud audit events, IaC plan/state diff, deployment digest, admission/policy logs, owner reviews.

### 6.4. Vulnerability và remediation

- [ ] Advisories/active exploitation signals liên quan in-scope assets được triage.
- [ ] Findings critical/high quá hạn hoặc đang tăng exposure được escalated.
- [ ] Planned fixes có owner, change window và retest plan; không chỉ ticket deadline.
- [ ] Exception/deferral còn trong kỳ, có mitigation hiệu lực và review trigger.
- [ ] Scanner/source coverage còn đủ cho asset population critical.
- [ ] Fix deployed được phân biệt với verified closed; urgent regressions tạo finding.
- [ ] Không suy ra “zero vulnerabilities” khi nguồn quét bị lỗi hoặc asset chưa onboard.

**Evidence:** affected asset map, advisories scoped, scanner heartbeat, runtime versions, retest results.

### 6.5. Data integrity và resilience

- [ ] Backup execution/freshness failures và replication lag critical được phát hiện.
- [ ] KMS key status/policy changes có tác động decrypt/restore được triage.
- [ ] Payment/order reconciliation, duplicate transactions, queue backlog hoặc DLQ alerts critical được xem.
- [ ] Restore readiness không được tuyên bố từ backup SUCCESS đơn lẻ.
- [ ] Data export/retention exceptions hoặc new third-party destinations có owner.
- [ ] Critical data handling/tenant isolation violations được xem theo incident triggers.
- [ ] Những thay đổi schema/data lifecycle làm evidence cũ hết hiệu lực đã được chuyển review.

**Evidence:** backup catalogs, replication metrics, transaction reconciliation alerts, key IAM/KMS events, scope notes.

### 6.6. Chốt ca

Một kết quả chốt ca phải ghi:

- Tình trạng **critical controls/visibility**, không chỉ số alert.
- Các **FAIL/INCONCLUSIVE** mới, impacted assets và owner.
- Active incidents, changes, exceptions gần hết hạn.
- Quyết định cần người có thẩm quyền.
- Hành động/ETA theo lịch thật và next review.
- Evidence links và nơi lưu đúng quyền.
- Người nhận bàn giao xác nhận critical open actions.

Một ca có nhiều UNKNOWN không thể ghi “ALL GREEN” chỉ vì monitoring dashboard không đỏ.

## 7. Checklist hằng tuần: đối soát phạm vi và tiến độ khắc phục

### 7.1. Asset và coverage

- [ ] Đối soát cloud accounts/projects, workloads, service catalogs với inventory và control units.
- [ ] Xác minh assets mới/retired, owners, criticality và data classes.
- [ ] Phát hiện assets missing scanner, IdP coverage, logging, backup hoặc DR inventory.
- [ ] Rà soát controls có scope wildcard hoặc N/A thiếu căn cứ.
- [ ] Cập nhật risk/requirement/control mapping theo material changes.
- [ ] Kiểm những nguồn evidence có last-seen/health bị mất trong tuần.
- [ ] Xác nhận các exceptions không bao phủ tài sản mới ngoài approval.

### 7.2. Access, cloud và pipeline

- [ ] So effective privileged permissions với approved role/access baseline.
- [ ] Đối soát new vendor/support accounts, expiry và offboarding.
- [ ] Rà soát IAM/KMS/network changes đã qua change assurance phù hợp.
- [ ] Sample CI/CD promotions: commit, build, artifact digest, deployment có khớp?
- [ ] Review unapproved console/IaC drift; lập action và retest.
- [ ] Kiểm admission policy exceptions và current enforcement trên runtime.
- [ ] Xác minh IaC/security scan coverage trên resources required, không chỉ repos đã onboard.

### 7.3. Testing, findings và risk

- [ ] Chạy/test một tập **positive/negative security scenarios** theo risk priority.
- [ ] Đối chiếu các detection rule adjustments với event/alert regression tests.
- [ ] Review findings quá hạn, repeated root causes và blockers.
- [ ] Chốt những fixes đã triển khai cần retest, không cho “Done” khi chưa verified.
- [ ] Rà soát exceptions sắp expiry, owner và compensating test freshness.
- [ ] Tách accepted risk khỏi FAIL/INCONCLUSIVE trong reports.
- [ ] Kiểm data quality problems đang ngăn kết luận đúng.

**Output tuần:** changes trong control population, new/closed findings theo verified state, risk decisions cần làm, evidence gaps và action owner.

## 8. Checklist hằng tháng: kiểm soát hiệu lực và chương trình assurance

### 8.1. Tác vụ trọng tâm

- [ ] Review control-unit applicability cho critical services và data flows.
- [ ] Kiểm evidence freshness so với release/IAM/key/architecture changes.
- [ ] Chạy targeted negative authz/privileged access tests theo approved environments.
- [ ] Kiểm detection coverage theo scenario và end-to-end synthetic event.
- [ ] Review vulnerability findings root causes, retest và recurring exposures.
- [ ] Thử sample log retention/integrity và quyền access evidence store.
- [ ] Rà soát KMS/backup/DR dependencies và rehearsal readiness theo BIA.
- [ ] Đối soát third-party access, API scopes, subprocessors và contract changes.
- [ ] Review risk acceptance decisions: finite expiry, approver, owner, mitigation, progress.
- [ ] Cập nhật risk appetite/applicability khi business hoặc environment đổi.
- [ ] Chạy sample independent assurance reviews đối với critical changes/controls.
- [ ] Kiểm dashboard denominators, metric versions và anti-gaming indicators.
- [ ] Phê duyệt remediation funding/priorities theo risk.
- [ ] Lập monthly assurance report có PASS, FAIL, unknown, N/A, critical cases và limits.

### 8.2. Chứng minh operating effectiveness theo kỳ

Một config export lúc cuối tháng có thể chứng minh **trạng thái tại mốc đó**, không tự chứng minh control hiệu quả suốt 30 ngày. Với control cần đo operating effectiveness, cân nhắc:

- Event/decision history suốt kỳ.
- Sample theo nhiều thời điểm, không chỉ ngày audit.
- Critical event classes và affected population.
- Alert/incident response outcomes.
- Unauthorized changes và gap intervals.
- Data source quality và source silence.
- Reviewer độc lập hoặc test method có thể tái lập.

Nếu không có dữ liệu đầy đủ cả kỳ, nêu **limitation/INCONCLUSIVE** cho claim về operating effectiveness.

## 9. Checklist hằng quý và theo chu kỳ quản trị

### 9.1. Control framework và risk governance

- [ ] Đánh giá lại security objectives theo BIA, threat landscape, business/data changes.
- [ ] Review baseline/control versioning, applicable standards và contractual obligations.
- [ ] Kiểm mẫu số required assets/units từ nguồn độc lập, không chỉ GRC.
- [ ] Lấy mẫu controls ở các đội khác nhau để kiểm evidence lineage và reviewer independence.
- [ ] Rà soát control owners/backup owners, separation of duties và authority matrix.
- [ ] Audit exception lifecycle, repeated renewals, expired/unapproved bypasses.
- [ ] Xem findings đã verified closed có tái phát cùng root cause không.
- [ ] Review threat-model deltas, attack paths và những preventive controls còn thiếu.

### 9.2. Incident/DR và third-party

- [ ] Chạy tabletop/technical exercises theo plan được phê duyệt, ưu tiên critical scenarios.
- [ ] Kiểm IR contacts/on-call escalation, access to evidence và response playbooks.
- [ ] Diễn tập restore/DR/rollback cho selected scenarios với BIA acceptance.
- [ ] Kiểm backup encryption/key lifecycle, least privilege và recovery domain independence.
- [ ] Review vendor assurance evidence theo service/period/scope và complementary controls.
- [ ] Đánh giá khả năng xử lý incident từ logging/detection và forensic readiness.
- [ ] Tổng kết incident postmortems thành preventive actions và retest gates.

### 9.3. Board/leadership reporting

Báo cáo theo kỳ nên trình bày **có bằng chứng, không chỉ nỗ lực**:

- Verified coverage và giới hạn của coverage.
- Top critical control failures và operational impact.
- Evidence gaps/unknowns đáng kể.
- Residual accepted risks, expired exceptions và approvals required.
- Incident/recovery exercise outcomes và unmet BIA goals.
- Remediation progress tính theo **verified closure**.
- Material changes làm thay scope.
- Nhu cầu ngân sách hoặc quyền quyết định.

Không cần mọi control test quarterly; đây là kỳ tổng kết governance, còn cadence từng control vẫn theo risk và quy định của chính tổ chức.

## 10. Checklist theo sự kiện: không chờ đến kỳ định kỳ

**Event-driven assurance** xử lý những thay đổi có thể khiến kết quả PASS trước đó mất tính đại diện. Một sự kiện không nhất thiết buộc kiểm lại toàn bộ controls; cần **impact analysis → affected control units → targeted tests → evidence mới → verdict và risk decision**.

### 10.1. Khi có deployment/release

- [ ] Release ID, environment, owner và approved scope đã xác định.
- [ ] Source commit/build run/artifact digest/config version khớp evidence trước deploy.
- [ ] Security test gates phù hợp trust boundaries đã thay, không chỉ unit tests.
- [ ] IAM/network/data/supply-chain changes được diff và review theo risk.
- [ ] Rollback/fail-forward/containment plan tương thích schema/keys và business state.
- [ ] Canary/blue-green có security signals, stop conditions và promotion criteria.
- [ ] Runtime units được đối chiếu với artifact và target population.
- [ ] Positive/negative authz, integrity, logging/detection tests sau deploy khi cần.
- [ ] Missing critical evidence/FAIL gate phải dừng/escalate theo policy.
- [ ] **APPROVED_FOR_DEPLOY** không bị đánh đồng **POST_DEPLOY_VERIFIED**.

**Ví dụ:** image scan PASS cho digest A không chứng minh production chạy mutable tag trỏ digest B. Cần runtime image identity.

### 10.2. Khi IAM/role/trust policy thay đổi

- [ ] Xác định human/workload/vendor principal, resource scope và inherited grants.
- [ ] Business justification và approval có owner.
- [ ] Kiểm effective permission diff, MFA, JIT, PAM, break-glass, session expiry.
- [ ] Chạy negative action/resource/cross-account access tests.
- [ ] Audit event cho grant/assume/revoke tới central store.
- [ ] Token/session cũ cần revoke được từ chối theo semantics hệ thống.
- [ ] Inventory và monitoring được cập nhật khi role mới tạo.
- [ ] Exception có finite expiry, owner, mitigation tests và trigger.

Một role tên ReadOnly không nhất thiết là read-only theo quyền hiệu lực; còn trust, resource policy, inheritance và condition.

### 10.3. Khi dữ liệu, region, privacy hoặc subprocessor thay đổi

- [ ] Data classification và loại dữ liệu mới đã xác định.
- [ ] Data-flow trước/sau có nguồn, đích, region, retention, encryption, vendor.
- [ ] Tenant authorization, export/caching/logging được test trên changed paths.
- [ ] Có review contract/privacy obligations khi áp dụng, không suy luật từ công nghệ.
- [ ] Backup/restore và deletion/retention semantics được đánh giá.
- [ ] Destructive migration có recovery/fail-forward/reconciliation plan.
- [ ] Service, data, vendor owner được tham vấn khi responsibility thay đổi.
- [ ] Evidence collection hạn chế dữ liệu nhạy cảm.
- [ ] Controls/exception liên quan được re-assessed.

### 10.4. Khi rotate KMS key, secret hoặc certificate

- [ ] Inventory key usage: apps, backups, recovery account, queues, vendors, historic ciphertext.
- [ ] Effective IAM/KMS permissions đúng scope, không mở wildcard không cần.
- [ ] Giải mã dữ liệu cũ/mới bằng identity được phép.
- [ ] Backup/DR decrypt path và key lifecycle được kiểm khi affected.
- [ ] Certificate chain, expiry/revocation semantics phù hợp clients và bản rollback.
- [ ] Secrets/tokens cũ cần revoke không còn hiệu lực.
- [ ] Key usage/change events được audit và monitoring.
- [ ] Rollback strategy không phụ thuộc key đã bị thu hồi hoặc nghi compromise.

### 10.5. Khi đổi logging/parser/SIEM/detection

- [ ] Source/event classes/rule IDs bị ảnh hưởng được mapping đến control objectives.
- [ ] So source schema và parser trước/sau, nhất là actor/action/resource/outcome.
- [ ] Chạy controlled positive/negative detection scenarios, kiểm suppression scope.
- [ ] Kiểm source silence, lag, lost events, duplicates và last-seen.
- [ ] Kiểm alert route, on-call owner và case creation nếu required.
- [ ] Không tuyên bố false-positive rate giảm chỉ vì volume alert giảm.
- [ ] Giữ evidence của blind-spot interval và retrospective review khi cần.
- [ ] Cập nhật runbook và regression tests.

### 10.6. Khi có critical vulnerability hoặc exploit intelligence

- [ ] Xác định actual affected product/version/asset population; không suy toàn bộ từ CVE title.
- [ ] Tách vulnerability present, exploitable configuration và evidence of exploitation.
- [ ] Kiểm Internet exposure, privilege/data impact và mitigation effectiveness.
- [ ] Chọn patch, feature disable, isolation hoặc alternate recovery theo risk.
- [ ] Security change/release gates và provenance không bị bỏ qua tùy tiện.
- [ ] Emergency hotfix có decision, minimum safeguards và hậu kiểm.
- [ ] Sau fix, xác minh deployed version và regression, không chỉ ticket Done.
- [ ] Accepted risk/deferral có authority, expiry và threat-based review trigger.

### 10.7. Khi tạo account/cluster/workload mới

- [ ] Asset discovery đưa nguồn mới vào inventory độc lập.
- [ ] Owner, criticality, environment, regions và data classes rõ.
- [ ] IAM, logging, network, encryption, secrets, backup baseline được áp.
- [ ] Control units/applicability và test schedules được tạo.
- [ ] Scanner, SIEM, asset management, drift monitoring được onboard.
- [ ] New vendor/privileged access có bounded scope/expiry.
- [ ] Missing source không bị coi N/A.
- [ ] First effective-state validation có evidence, defects được giao owner.

### 10.8. Khi có incident/anomaly ảnh hưởng boundary

- [ ] Xác minh alert, scope, confidence và impact theo IR triage.
- [ ] Kích hoạt đúng SOC, Incident Commander và service/risk owner.
- [ ] Preserve logs, configs, artifacts và forensic evidence trước thao tác phá hủy.
- [ ] Xác định control nào bị phá hoặc không còn đáng tin.
- [ ] Phân biệt containment, eradication, trusted recovery và remediation.
- [ ] Nếu restore, xét trustworthiness của recovery point theo threat scenario.
- [ ] Kiểm business/data/security invariants trước khi hoạt động bình thường.
- [ ] Link findings, root cause tới control library và tests.
- [ ] Không suy từ control gap rằng breach chắc chắn đã xảy ra.
- [ ] Nghĩa vụ thông báo/privacy được đánh giá bởi bộ phận có thẩm quyền khi cần.

### 10.9. Khi backup/DR/rollback exercise thất bại

- [ ] Xác định FAIL ở backup freshness, KMS, restore, data integrity, RTO/RPO hay logging.
- [ ] Không tuyên bố mất dữ liệu production chỉ vì một rehearsal thất bại.
- [ ] Xem immediate business exposure và alternate recovery strategy.
- [ ] Kiểm IdP, DNS, keys, secrets, registry, DB schema, network, vendors.
- [ ] Lập finding có owner, deadline, corrective action và retest.
- [ ] Rehearse representative scenario sau fix và đo actual outcomes.
- [ ] Nếu critical recovery assertion FAIL, escalation theo BIA/risk authority.
- [ ] Cập nhật runbooks, monitoring và preventive gates.

### 10.10. Khi thay đổi owner, baseline hoặc nghĩa vụ

- [ ] Control/risk owner mới có authority và contact.
- [ ] Required controls/applicability cập nhật theo requirement version.
- [ ] Exceptions/decisions cũ có cần reassessment với authority mới?
- [ ] Test methods và evidence period có bị đổi semantics?
- [ ] RACI, approval, escalation, data retention/reporting đồng bộ.
- [ ] Không đổi lịch sử FAIL thành PASS khi baseline thay đổi.

## 11. Checklist theo domain: security invariants cần kiểm

Checklist dưới đây là **mẫu control assertions**, phải cụ thể hóa theo policy và applicable population. Không phải tổ chức nào cũng phải tick mọi dòng cho mọi asset.

### 11.1. Governance, risk và ownership

- [ ] Security objectives, risk appetite và baseline có owner/version.
- [ ] Asset/service/data inventory đủ nguồn độc lập và reconciliation.
- [ ] High/critical risks có treatment và traceability đến controls.
- [ ] Control statements có scope, assertion, tests và evidence contracts.
- [ ] Control implementer, assessor và risk approver được phân biệt.
- [ ] Missing assets/unknown applicability không bị loại khỏi báo cáo.
- [ ] Risk acceptance có scope, authority, expiry và mitigation.
- [ ] Audit history và closure evidence được bảo vệ.

### 11.2. Identity & Access

- [ ] Human privileged paths và emergency accounts được kiểm kê.
- [ ] Required MFA/SSO/JIT/PAM thực sự enforce.
- [ ] Workload identities không có unnecessary inherited grants.
- [ ] Cross-account trust và vendor access least privilege.
- [ ] Secrets/tokens có rotation, revoke, expiry và monitoring.
- [ ] Disallowed resources/actions được thử negative tests.
- [ ] Expired temporary privileges bị thu hồi effective.
- [ ] Privileged grants và usage có audit/detection.

### 11.3. Application/API và secure SDLC

- [ ] Object/field/tenant authorization ở server-side.
- [ ] Positive/negative authz và abuse-case tests đầy đủ các paths required.
- [ ] Input validation/error handling tránh lộ secrets/PII.
- [ ] Authentication/session/token lifecycle có test.
- [ ] Secure review, SAST, SCA có scope phù hợp changes.
- [ ] Vulnerabilities map tới actual deployed versions.
- [ ] Security regression tests chạy đúng artifact promoted.
- [ ] Release approval/rollback readiness, post-deploy validation phù hợp.

### 11.4. Data protection và privacy

- [ ] Data classification và owner cho storage/flows.
- [ ] Encryption in-transit/at-rest và key access effective.
- [ ] Tenant/resource data access boundaries được test.
- [ ] Integrity, idempotency, reconciliation được kiểm theo business rules.
- [ ] Retention/deletion/cache/log/backup lifecycle được xem xét.
- [ ] Data transfer/export đến vendors/regions có approved scope.
- [ ] Evidence không chứa secrets/customer content ngoài phạm vi cho phép.
- [ ] Legal/privacy obligations được xác minh theo applicability.

### 11.5. Cloud, infrastructure và platform

- [ ] Cloud accounts, clusters, workloads và principals được kiểm kê đủ.
- [ ] IaC/policy-as-code kiểm network, IAM, KMS và runtime baseline.
- [ ] Public ingress/egress và privileged trust không vượt scope.
- [ ] Workload isolation và service accounts được kiểm runtime.
- [ ] Console changes và source-of-truth drift có alert/triage.
- [ ] Deployed digest/provenance khớp approved artifact.
- [ ] Customer-side controls trong shared responsibility được biết rõ.
- [ ] Operational exceptions có bounded scope/time.

### 11.6. Logging, detection và incident readiness

- [ ] Required event classes được gắn với threat scenarios.
- [ ] Source coverage, parser fields, SIEM routing/retention được kiểm.
- [ ] Detection rules có controlled scenarios và owner.
- [ ] Suppressions có scope, reason, expiry và retest.
- [ ] Source silence/field loss/alert-route failure được phát hiện.
- [ ] IR contacts, runbooks, evidence preservation và on-call sẵn.
- [ ] Incident lessons learned chuyển thành preventive action.
- [ ] Threat changes kích hoạt relevant detection regression.

### 11.7. Resilience, recovery và third party

- [ ] BIA xác định service/security recovery acceptance và RTO/RPO.
- [ ] Backup freshness và actual restore/decrypt được kiểm riêng.
- [ ] Recovery keys/IAM/network/secret dependencies đúng.
- [ ] Replay/compensation/rollback giữ business integrity.
- [ ] DR/IR/release runbooks có rehearsals, owners và stop conditions.
- [ ] Vendor data/access flows có inventory/contract/monitoring.
- [ ] Third-party evidence đúng service, period, scope, customer responsibilities.
- [ ] Offboarding/revoke/exit path được thử khi cần.

## 12. Decision gates và ưu tiên phản ứng

### 12.1. Phân loại response theo rủi ro

| Gate class | Tình huống ví dụ | Response tham khảo |
|---|---|---|
| **Critical boundary failure** | Confirmed cross-tenant access, unapproved privileged grant | Stop affected promotion, containment/IR review |
| **Critical visibility loss** | Audit/detection source mất cho critical service | Visibility triage, mitigation, risk decision |
| **Integrity/recovery gap** | Payment reconciliation FAIL, required restore/decrypt FAIL | Hold stateful change, alternate recovery |
| **High-risk drift** | New public ingress, KMS trust hoặc privileged K8s drift | Verify effective state, restrict/rollback theo policy |
| **Evidence quality gap** | Scanner/log source stale, wrong scope | INCONCLUSIVE và phục hồi source/test |
| **Standard deviation** | Noncritical issue có mitigation | Timebound remediation và monitoring |
| **Unapproved exception** | MFA/detection bypass thiếu approval | Escalate, safe enforcement, runtime verification |

Danh sách chỉ minh họa **hard gates có thể có**; tổ chức phải định nghĩa trong policy, tránh tự động ngắt production khi không có safety analysis.

### 12.2. Hai trục: impact và confidence

- **Impact/urgency:** tác động có thể lớn đến mức nào, nhanh đến đâu?
- **Confidence:** bằng chứng xác nhận condition, scope và thời điểm đến đâu?

Một risk tiềm tàng high-impact nhưng evidence chưa đủ vẫn có thể cần containment thận trọng và xác minh ngay; không tự gán confirmed FAIL nếu chỉ là giả thuyết. Với confirmed critical failure, không nên chờ dashboard overall xuống ngưỡng mới xử lý.

### 12.3. Decision pseudocode

~~~text
IF evidence confirms a critical security-control failure:
    record FAIL with verified scope
    preserve evidence and invoke authorized containment/incident path
    assign owner, escalation and retest
ELSE IF required source is unavailable or test conflicts:
    record INCONCLUSIVE / NOT_TESTED according to facts
    assess visibility risk and restore source or alternate evidence
ELSE IF required assertion has suitable evidence in scope:
    record PASS_WITH_SCOPE and explicit limitations
ELSE IF applicability is proven absent:
    record NOT_APPLICABLE with rationale and approval
ELSE:
    do not infer PASS
    request further assessor review
~~~

Đây là **mã giả**, không được dùng trực tiếp làm tự động tắt workload. Các thao tác production cần approval, safety, rollback và incident/change governance.

### 12.4. Không có alert không có nghĩa không có attacker

Zero alerts có thể do collector dừng, parser bỏ fields, routing sai, suppression, time skew, asset không onboard hoặc detector không bao phủ attack path. Do đó báo cáo phải chỉ rõ **visibility coverage** và giới hạn thay vì kết luận “không có incident” dựa vào im lặng của dashboard.

## 13. Evidence contract: chứng cứ nào đủ cho một checkbox?

### 13.1. Các trường tối thiểu

- **Evidence ID, check ID, control ID, assertion ID, control unit ID**.
- **Asset/environment/population**, sampled và unsampled.
- **Time period/as-of timestamp** và timezone/clock confidence.
- **Source/collection method**, collector identity và quyền.
- **Test method/version**, expected và observed outcomes.
- **Artifact/config/identity versions** thực sự được kiểm.
- **Coverage/freshness/quality**, data gaps và last-seen.
- **Integrity/reference**, quyền truy cập và retention.
- **Verdict, confidence, limitations**.
- **Operator, reviewer, decision, finding/retest links**.

### 13.2. Mẫu evidence record cho kiểm tra vận hành

~~~yaml
check_id: "OPS-LOG-2026-051"
control_id: "LOG-01"
assertion_id: "LOG-01-A1"
control_unit_id: "CU-LOG01-ADMIN-PROD"
scope:
  environment: "training-simulation"
  asset: "admin-portal-example"
  event_class: "ADMIN_PRIVILEGE_CHANGE"
period:
  start: "2026-11-28T01:00:00Z"
  end: "2026-11-28T02:00:00Z"
test:
  method: "synthetic-source-to-siem-and-alert"
  version: "v3"
  test_identity: "approved-synthetic-admin"
  expected:
    - "actor"
    - "action"
    - "resource"
    - "outcome"
  observed:
    source_event: true
    collector_event: true
    siem_event: true
    actor_present: false
    alert_observed: false
evidence:
  refs:
    - "EV-LOG-SOURCE-101"
    - "EV-LOG-SIEM-101"
  storage: "restricted-training-evidence"
  source_health: "OK_FOR_TEST_SOURCE"
result:
  verdict: "FAIL"
  confidence: "HIGH_WITHIN_TEST_SCOPE"
  limitation: "One synthetic event and event class"
ownership:
  operator_role: "SOC-analyst"
  reviewer_role: "security-assurance"
followup:
  finding_id: "F-LOG-101"
  priority: "ASSESS_BY_REQUIRED_LOGGING_CRITICALITY"
  next_action: "Investigate parser mapping and detection rule"
~~~

Đây là **dữ liệu mô phỏng**, không phải kiểm thử production thật. Field source_health = OK không khiến logging control PASS khi actor/alert vẫn không đạt.

### 13.3. Quality gate của evidence

| Kiểm tra | Câu hỏi | Khi thiếu |
|---|---|---|
| **Source identity** | Có đúng system/asset cần kiểm? | Recollect/INCONCLUSIVE |
| **Version binding** | Test đúng deployed artifact/policy? | Bind lại test tới actual runtime |
| **Time binding** | Đúng kỳ và sau material change? | Evidence stale |
| **Population** | Bỏ sót pods, accounts, identities, tenants? | Bổ sung units/coverage |
| **Method suitability** | Test đúng assertion hay chỉ proxy metric? | Đổi phương pháp |
| **Reliability** | Requester có thể sửa kết quả/approval không? | Bảo vệ collector/independence |
| **Integrity** | Có original/source và version history? | Reconstruct lineage |
| **Privacy** | Có secrets/customer content dư thừa? | Redaction, ACL và retention |
| **Contradictions** | Có evidence trái nhau mà chưa giải thích? | Điều tra, không tự PASS |

Một checksum khớp chỉ chứng minh file không đổi so với mốc tham chiếu tin cậy; **không chứng minh log ở nguồn đầy đủ**. Một snapshot config cũng không chứng minh control hoạt động suốt một kỳ dài nếu không có event/history.

### 13.4. Synthetic evidence và production claims

Dữ liệu mô phỏng hữu ích để diễn tập, nhưng phải ghi **TRAINING_ONLY/SYNTHETIC**. Không suy kết quả giả định thành production assurance. Trong lab, có thể dùng test identity và resource giả, event IDs, role matrix, backup simulation; tuyệt đối không lấy dữ liệu người dùng thật hoặc thử các endpoint không được cấp quyền.

## 14. Vận hành finding, remediation và verified closure

### 14.1. Từ FAIL đến hành động kiểm được

1. Xác nhận criterion và affected population.
2. Thu source evidence, ghi condition và confidence.
3. Xem có cần incident/containment hoặc emergency change ngay.
4. Đánh impact, exposure, exploitability và compensating controls.
5. Tạo finding với owner, risk, deadline, required approvals.
6. Viết corrective action và retest plan trước khi triển khai.
7. Ghi change/deployed artifact, time, affected units.
8. Kiểm effective state sau fix, không chỉ merge PR/ticket Done.
9. Thu mới test evidence PASS/FAIL và ghi limitations.
10. Dọn temporary bypass/privileges nếu không còn cần.
11. Đóng **CLOSED_VERIFIED** chỉ khi assertions và điều kiện closure đạt.
12. Giữ failed evidence cũ cùng CAPA/root-cause prevention.

### 14.2. Finding record minh họa

~~~yaml
finding_id: "F-2026-OPS-019"
criterion:
  control_id: "IAM-02"
  assertion_id: "IAM-02-A1"
  requirement_ref: "LEAST-PRIVILEGE-POLICY"
condition:
  observed: "Payment worker can read secrets outside required scope"
  environment: "training-simulation"
  evidence_refs: ["EV-IAM-041", "EV-IAM-042"]
  confidence: "HIGH_WITHIN_TEST_SCOPE"
risk:
  scenario: "Compromised workload accesses unrelated service secrets"
  severity: "HIGH_FOR_WORKSHOP"
ownership:
  control_owner_role: "identity-platform"
  remediation_owner_role: "payment-platform"
  reviewer_role: "security-assurance"
plan:
  immediate: "Restrict grants via approved change"
  permanent: "Scoped policy and permission regression tests"
  due_at: "2026-12-07T00:00:00Z"
retest:
  method: "effective-permission-and-negative-access-test"
  affected_population: ["payment-worker-principals"]
  expected: "deny-nonrequired-secrets"
state: "OPEN"
~~~

Condition trên **không chứng minh secrets đã bị đánh cắp**. Phải tách security weakness khỏi incident/breach evidence.

### 14.3. CAPA (corrective and preventive action)

| Root cause | Correction | Preventive control |
|---|---|---|
| IAM wildcard default template | Thu hẹp policy, retest | Policy-as-code + negative access tests |
| Parser làm mất actor | Sửa source/field mapping | Event schema contract + source silence alerts |
| Cloud account thiếu onboarding | Enroll account | Organization-wide discovery + mandatory baseline |
| Backup restore lỗi KMS | Cấp quyền đúng scope, retest | Key rotation change gate với DR |
| CI override không được duyệt | Thu hồi bypass, kiểm artifact | Protected workflow + emergency approvals |
| Detection suppression quá rộng | Tune scope, expiry | Suppression lifecycle tests |
| Vendor token không hết hạn | Revoke/rotate | JIT/lease + offboarding controls |
| Vulnerability tồn đọng | Patch/mitigate | Risk-based SLA, runtime version tracking |

Correction sửa condition hiện tại; prevention giảm khả năng lặp lại. Cả hai cần owner, evidence và hiệu lực được review.

## 15. Ngoại lệ và risk acceptance trong vận hành

### 15.1. Checklist exception request

- [ ] Requirement/control nào chưa đạt, evidence gì?
- [ ] Scope asset/principal/environment/data có chính xác?
- [ ] Có nghĩa vụ không cho phép miễn trừ hoặc giới hạn authority?
- [ ] Residual risk, business impact và threat assumptions có căn cứ?
- [ ] Compensating controls thực sự test đúng attack paths?
- [ ] Approver có thẩm quyền với risk level đó?
- [ ] Có finite effective_from, expires_at, next_review_at?
- [ ] Có remediation owner, milestone, deadline và retest plan?
- [ ] Có runtime rule/bypass ID để xác minh khi hết hạn?
- [ ] Trigger review khi threat, exposure, data, owners đổi?
- [ ] Governance decision tách khỏi primary control FAIL?
- [ ] Renewal có assessment mới và explicit approval?
- [ ] Expiry/withdrawal có safe enforcement và escalation path?

### 15.2. Expired trên giấy, runtime còn mở

Một ngoại lệ MFA hết hạn nhưng local admin path vẫn bypass:

- **Governance decision:** EXPIRED/NOT_AUTHORIZED.
- **Primary control:** FAIL nếu kiểm chứng được bypass.
- **Runtime exposure:** cần xác nhận actual permission/session.
- **Response:** containment, safe restriction, escalate theo policy.
- **Evidence:** rule state, approved scope, time, principal, owner.
- **Closure:** sửa MFA, thu hồi bypass, negative test và reviewer.

Không tự cho rằng expiry đã revoke quyền. Cũng không tự khóa một đường khôi phục DR critical khi chưa có alternative path và operational safety. **Validity của decision** khác với **thực thi runtime**.

### 15.3. Risk acceptance không thay requirement

Internal approval chỉ có hiệu lực trong thẩm quyền. Với contractual/legal/regulatory obligations cần bộ phận chuyên môn xác minh applicability và giới hạn miễn. Không dùng “risk accepted” để chuyển FAIL sang compliance PASS.

## 16. Giao ca và escalation: không để kết quả nằm trong một dashboard

### 16.1. Operational handoff record

~~~yaml
handoff_id: "SHIFT-2026-11-28-AM"
service_scope: ["order-api", "payment-worker", "siem"]
period:
  start: "2026-11-28T00:00:00Z"
  end: "2026-11-28T08:00:00Z"
headline:
  posture: "CONDITIONAL_WITH_OPEN_GAPS"
  source_coverage: "PARTIAL"
  critical_failures: 1
  critical_unknowns: 1
open_items:
  - id: "F-2026-OPS-019"
    issue: "Payment worker IAM outside approved scope in simulation"
    owner_role: "identity-platform"
    next_action: "Review effective permissions and fix"
  - id: "DQ-2026-004"
    issue: "Admin SIEM actor field missing"
    owner_role: "SOC-engineering"
    next_action: "Parser investigation and retest"
decisions_needed:
  - "Risk owner to review expiring privileged mitigation"
evidence_refs: ["EV-IAM-041", "EV-LOG-SIEM-101"]
next_shift_owner_role: "security-operations"
~~~

YAML là **mẫu**, không phải handoff đang chạy. Với incident nghiêm trọng, không chỉ chờ một file bàn giao; phải theo on-call/escalation policy và xác nhận người nhận đã nắm hành động.

### 16.2. RACI vận hành tham khảo

| Vai trò | Trách nhiệm |
|---|---|
| **SOC/on-call** | Nhận tín hiệu, triage, incident/detection handoff |
| **Service owner** | Business impact, degraded mode, thẩm quyền vận hành |
| **Control owner** | Assertion, effective-state behavior, baseline |
| **Engineering/Platform** | Implement/fix/rollback, technical evidence |
| **Security Assurance** | Quality/verdict, retest, evidence traceability |
| **Risk owner** | Residual risk decision, limits và expiry |
| **Incident Commander** | Điều phối IR theo chính sách |
| **GRC/Audit** | Evidence/exception governance và reporting |
| **Privacy/Legal/Vendor owner** | Nghĩa vụ và bên ngoài khi áp dụng |

Một người có thể đảm nhiệm nhiều vai trò trong nhóm nhỏ; với critical decision cần separation of duties hoặc cơ chế giám sát độc lập theo policy.

### 16.3. Runbook hữu ích phải ghi

- Conditions, scope, service/asset owner.
- Preflight và cách xác minh đúng environment.
- Thẩm quyền quyết định, contact và backup role.
- Stop conditions, rollback/fail-forward, safe degraded mode.
- Evidence preservation và bảo vệ dữ liệu nhạy cảm.
- Positive/negative acceptance tests.
- Unknown-handling và escalation.
- Cleanup, post-change verification.
- Review cadence và triggers.

Nếu runbook giả định IdP/CI/registry luôn sẵn trong khi failure scenario khiến hệ thống đó lỗi, cần alternate emergency/recovery path.

## 17. Automation: kiểm soát checklist và kiểm lỗi của chính công cụ

### 17.1. Những việc nên tự động hóa

- Asset/workload/account discovery, owner mapping và new-unit creation.
- Source/collector/scanner health, stale data alerts.
- Control check scheduling theo cadence và change triggers.
- Evidence schema/provenance/freshness validation.
- Risk-based CI/CD gates gắn actual artifact.
- IAM temporary grant expiry và revalidation.
- Cloud/IaC policy drift detection.
- Exception time-bound approval/renewal alerts.
- Findings overdue/verified closure tracking.
- KPI aggregation theo independent denominators.

### 17.2. Không tự động hóa quyết định vượt thẩm quyền

Tự động có thể chặn deploy không có signed artifact hoặc tạm dừng promotion theo policy đã phê duyệt. Nhưng không được mặc định:

- Xóa dữ liệu production khi exception hết hạn.
- Rotate/revoke KMS key critical gây mất decrypt/DR.
- Disable toàn bộ network khi alert không chắc chắn.
- Tự chấp nhận risk khi không ai phản hồi.
- Ghi PASS khi scanner lỗi hoặc API query trả tập rỗng.
- Đổi audit history để báo cáo trông tốt hơn.

Cần **dry-run, idempotency, authorization, rate limits, audit logs, safe fallback, stop conditions và human escalation** cho những thao tác có ảnh hưởng lớn.

### 17.3. Giám sát chính hệ thống assurance

Một pipeline đánh giá có thể thất bại mà dashboard vẫn xanh nếu:

- Collector chỉ lấy các source đang hoạt động và không biết những source missing.
- IAM client/API pagination dừng sớm, bỏ một phần principals.
- Clock skew khiến evidence stale vẫn “fresh”.
- Mapping control units bị đổi nhưng denominator chưa cập nhật.
- Truy vấn chỉ lọc verdict PASS, không tải FAIL/unknown.
- Test harness chỉ dùng admin account và bỏ negative paths.
- CI chạy scan image A, deployment dùng image B.
- Suppression trong SIEM che alerts của chính test.
- Reviewer có quyền sửa cùng lúc evidence và approval.

Do đó, assurance program cũng cần **control cho evidence pipeline**: expected-source registry, collection coverage, last-seen, schema validation, reconciliation, access audit và independent sampling.

### 17.4. Control monitoring cho checklist

| Meta-control | Assertion | Test |
|---|---|---|
| **META-01 Source completeness** | Required sources đều được nhận biết, kể cả khi im lặng | So expected inventory với collected sources |
| **META-02 Evidence freshness** | Không dùng stale evidence cho current claim | Change timestamp vs evidence timestamp |
| **META-03 Verdict integrity** | Không đổi FAIL thành PASS khi thiếu test | Version/audit trail review |
| **META-04 Approval integrity** | Exceptions/risk decisions đúng quyền và hạn | RBAC/SoD và renewal sampling |
| **META-05 Population consistency** | Denominator không loại unknown không căn cứ | Asset/control-unit reconciliation |
| **META-06 Test coverage** | Negative/positive cases đủ cho assertion critical | Test catalog vs route/role matrix |
| **META-07 Closing integrity** | Verified closure phải có retest evidence | Finding → fix → runtime evidence links |

## 18. Lược đồ operational assurance record tổng hợp

### 18.1. Mẫu JSON/YAML tổng thể

~~~yaml
record_id: "OPS-2026-11-28-001"
module: "SECURITY_SECURITY_ASSURANCE"
record_type: "daily-assurance-pulse"
service_scope:
  - "order-api"
  - "payment-worker"
  - "admin-portal"
environment: "training-simulation"
period:
  start: "2026-11-28T00:00:00Z"
  end: "2026-11-28T08:00:00Z"
source_population:
  required_sources: 8
  sources_verified: 7
  sources_missing: 1
control_population:
  required_units: 40
  pass: 25
  fail: 4
  inconclusive: 7
  not_tested: 4
findings:
  critical_open: ["F-LOG-101"]
  high_open: ["F-2026-OPS-019"]
exceptions:
  expiring_soon: ["EX-IAM-2026-003"]
  expired_enabled_candidates: []
decisions:
  - "Restore missing audit source"
  - "Review privileged access risk and remediation"
evidence_refs:
  - "EV-LOG-SIEM-101"
  - "EV-IAM-041"
owner_roles:
  operations: "SOC"
  security_assurance: "assurance-team"
  risk: "authorized-service-risk-owner"
limitations:
  - "One required log source unavailable in assessment window"
  - "Only synthetic environment tested"
headline: "SECURITY_GAPS_AND_UNCERTAINTY_REQUIRING_ACTION"
~~~

Các số liệu là **giả định** và bốn nhóm pass/fail/inconclusive/not_tested **cộng đúng 40 applicable units**. Nếu required source thiếu, không được tuyên bố kiểm soát phụ thuộc nguồn đó đã PASS suốt kỳ.

### 18.2. Quy trình thu, phê duyệt và sử dụng record

1. Collector thu observations và kiểm expected source population.
2. Normalizer gắn asset/control/unit, timestamp và artifact version.
3. Quality checks phát hiện missing/stale/conflicting evidence.
4. Evaluator đưa verdict theo assertions có version.
5. Owner/reviewer xác nhận critical observations và scope.
6. Findings/IR/change actions được lập khi có failure.
7. Risk approver ra quyết định riêng khi cần, không viết đè control verdict.
8. Daily/weekly/monthly report tổng hợp có denominator.
9. Evidence được lưu đúng ACL/retention, redaction và audit history.
10. Periodic independent sampling kiểm pipeline có phản ánh runtime thật.

### 18.3. Đối soát KPI của mẫu

Với 40 applicable control units, 25 PASS, 4 FAIL, 7 INCONCLUSIVE và 4 NOT_TESTED:

\[
\text{Verified coverage} = 25/40 \times 100\% = 62.5\%
\]

Không dùng **25/(25+4) = 86,2%** để báo verified coverage toàn scope vì công thức đó loại 11 units chưa có verdict đủ. Có thể công bố chỉ số khác như pass rate among conclusive tests, **nhưng phải ghi rõ mẫu số và tên metric**.

## 19. KPI/KCI: đo tình trạng assurance, không đo số ô đã tick

### 19.1. Những chỉ số cần phân biệt

| KPI/KCI | Cách định nghĩa hữu ích | Bẫy thường gặp |
|---|---|---|
| **Required asset coverage** | Required assets có inventory/owner và baseline enrollment / toàn required assets | Chỉ tính assets đã onboard scanner |
| **Control applicability completeness** | Candidate units đã xác minh applicable/N/A / toàn candidate units | Tự coi unknown=N/A |
| **Verified control coverage** | Applicable control units có evidence PASS / all applicable units | Cộng accepted risks hoặc bỏ unknown |
| **Test execution coverage** | Applicable units được test theo kế hoạch / all units required testing | Chạy test nhưng không đúng artifact |
| **Evidence freshness** | Units có evidence còn hiệu lực / required evidence units | Snapshot cũ được kéo dài vô hạn |
| **Source health completeness** | Required telemetry sources có chứng cứ last-seen/data quality / all required sources | Chỉ nhìn các sources vẫn gửi dữ liệu |
| **Critical gate failures** | Số critical assertions FAIL trong required scope | Zero FAIL do test không chạy |
| **Unverified critical units** | Critical units INCONCLUSIVE/NOT_TESTED | Loại khỏi báo cáo vì chưa có kết quả |
| **Detection scenario effectiveness** | Required scenarios có test alert PASS / all required scenarios | Lấy alert volume làm recall |
| **Exception validity** | Exceptions đúng authority/scope/expiry/controls / all active or candidate bypasses | Chỉ đọc GRC, bỏ bypass ngoài hệ thống |
| **Verified remediation closure** | Findings retest PASS / findings cần khắc phục trong cohort | Đếm tickets Done |
| **Repeated control failures** | Gaps lặp lại theo root cause sau closure | Đổi finding ID để reset |
| **Time to detect/respond** | Mốc signal→triage→action theo incident/change | Không xác định cohort hoặc clock |
| **Recovery exercise success** | Required scenarios đạt business/security acceptance / all required exercises | Backup SUCCESS được tính restore PASS |
| **Vendor access hygiene** | Temporary vendor grants đúng scope và expiry / active vendor grants | Bỏ account không được inventory |
| **Control assurance latency** | Từ material change đến control retest/decision | Chỉ đo thời gian chạy scanner |

### 19.2. Giữ định nghĩa numerator và denominator

Giả sử có 80 applicable control units của critical services:

- 52 PASS.
- 10 FAIL.
- 12 INCONCLUSIVE.
- 6 NOT_TESTED.

Khi đó:

\[
\text{Verified control coverage} = \frac{52}{80}\times100\% =65\%
\]

Nếu 4 trong 10 FAIL được risk owner chấp nhận trong thời gian hữu hạn, coverage **vẫn 65%**. Một báo cáo có thể nêu riêng **4 FAIL có valid risk disposition**, nhưng không sửa control verdict.

Nếu có thêm 6 candidate units **chưa biết applicability**, nên báo cả **applicability completeness** và unknown candidate count. Không tự loại chúng để mẫu số “đẹp”.

### 19.3. Metric không tạo động cơ gian lận

Hệ thống đo lường phải chống:

- Gán low risk để bỏ critical test.
- Tách một finding thành nhiều ticket “Done” nhưng chưa sửa.
- Đổi expiry exception tự động.
- Chỉ test “easy assets”.
- Xóa failed history sau retest.
- Loại missing-source units ra khỏi denominator.
- Dùng source health thay assertion testing.
- Sửa threshold/chỉ số mà không version.
- Đếm scans nhiều lần như nhiều controls.
- Xem incident không được phát hiện là không tồn tại.

Tốt hơn nên hiển thị **verified PASS, confirmed FAIL, unknown, critical scope, evidence gaps, risk decisions và trend**, kèm số lần test/coverage.

### 19.4. Chỉ số cần context và confidence

Một tháng có số FAIL tăng có thể do:

1. Control thực sự xuống cấp.
2. Program kiểm được nhiều assets hơn.
3. Test case/requirements mới nghiêm ngặt hơn.
4. Scanner/rules đổi và phát sinh false positives.
5. Một event source mất và tăng INCONCLUSIVE.
6. Material changes tạo risk surface mới.

Do vậy không diễn giải trend mà không ghi **population drift, metric version, confidence và nguồn dữ liệu**. Nếu có một incident critical, cần phân tích cụ thể thay vì chỉ nhìn pass-rate.

## 20. Báo cáo vận hành cho các cấp trách nhiệm

### 20.1. Executive summary 1 trang cần có gì?

Một bản ngắn dành cho service/risk owner:

- **Scope/kỳ:** dịch vụ, environments, data classes và exclusions.
- **Tình trạng:** controls verified PASS/FAIL/unknown theo population.
- **Top 3–5 risks:** criterion, affected assets, business impact, evidence confidence.
- **Current mitigations:** controls bù trừ nào đã test, chưa test.
- **Decisions required:** release hold, remediation budget, vendor escalation, accepted risk đúng thẩm quyền.
- **Remediation owners/time:** deadlines, status, next checkpoint.
- **Material changes:** release, cloud IAM, data flow hoặc vendor changes trong kỳ.
- **Evidence limitations:** scanner gaps, synthetic tests, stale sources.
- **Historical trend:** so sánh cohort nhất quán và giải thích restatements.

### 20.2. Báo cáo minh họa, không phải kết quả sản xuất

> **Scope:** mô phỏng 40 applicable control units cho Order API, Payment Worker và Admin Portal trong một kỳ kiểm.
>
> **Kết quả:** 25 PASS (62,5%), 4 FAIL, 7 INCONCLUSIVE, 4 NOT_TESTED. Một required log source không sẵn trong kỳ, làm giảm confidence của những claims phụ thuộc nguồn đó.
>
> **Rủi ro ưu tiên:** một đường IAM quyền quá rộng trong test scope và việc thiếu actor field của event quản trị trong synthetic logging check.
>
> **Action:** Identity team phải xác minh effective grants và thu hẹp quyền; SOC engineering sửa parser, test source→SIEM→alert. Security Assurance xác minh retest và update verdict.
>
> **Cần quyết định:** Service/risk owner xem hạn ngoại lệ privileged access; chưa có cơ sở để tuyên bố toàn bộ required controls đã đạt.
>
> **Giới hạn:** dữ liệu tổng hợp, không phải production assessment hoặc chứng nhận.

### 20.3. Báo cáo cho từng đối tượng

**Engineering/Platform:** failing assertion, actual artifact, deployment/unit ID, test method, remediation/rollback.

**SOC/IR:** event source coverage, detection blind spots, suppression, incident triage, evidence preservation.

**GRC/Audit:** applicable controls, test histories, evidence quality, exceptions, reviewer authority, closure.

**Service/Risk owner:** impact/alternatives, residual risk, deadlines, funding/approval required.

**Leadership:** critical risks, trend, control coverage có mẫu số, confidence và risk decision bottlenecks.

### 20.4. Kết luận không vượt phạm vi

Tránh các tuyên bố như “không có breach vì không có alert” hoặc “hệ thống luôn an toàn vì tuần này PASS”. Nên dùng **“các assertions đã đạt trong phạm vi và kỳ được kiểm, với limitations sau…”**. Đối với claim đang dùng dữ liệu synthetic, phải ghi rõ không áp dụng production.

## 21. Case study 1: dashboard xanh nhưng mất khả năng phát hiện

### 21.1. Bối cảnh

Một SOC giả định giám sát thay đổi quyền quản trị trên nhiều cloud accounts. Dashboard hiển thị **collector healthy 100%** và không có alert IAM bất thường trong hai ngày. Trong một controlled test, Security Assurance tạo privileged-change event trên một cloud account mới. Event xuất hiện tại source nhưng không có ở SIEM; account mới chưa nằm trong source enrollment list.

### 21.2. Các claim cần tách

| Claim | Evidence | Verdict phù hợp |
|---|---|---|
| Các collectors đã onboard còn chạy | Heartbeat từ known collectors | PASS_WITH_SCOPE cho registered collectors |
| Mọi critical cloud accounts được giám sát | Account inventory có account mới chưa onboard | FAIL cho enrollment/coverage criterion |
| Event đi end-to-end | Source event không tới SIEM trong test | FAIL cho tested event path |
| Detection rule hoạt động trên account mới | Không có event ở SIEM | INCONCLUSIVE hoặc FAIL nếu rule kiểm nhận/sourcing là criterion |
| Không có attacker hoạt động | Chưa có điều tra đủ | Không có căn cứ kết luận |

### 21.3. Hành động theo checklist

1. Ghi nguồn, mốc thời gian, account, test principal và event ID.
2. Xác minh account thực sự required và data/role criticality.
3. Tạo finding **source enrollment gap**, không tự đánh toàn SIEM PASS.
4. Contain high-risk operations nếu threat/exposure và policy yêu cầu.
5. Onboard log source và các required event classes.
6. Sửa mapping source→collector/index.
7. Chạy lại event delivery và detector scenario, kiểm actor/action/resource/outcome.
8. Kiểm các cloud accounts khác cùng onboarding path.
9. Bổ sung **organization-level account discovery** và source silence meta-control.
10. Cập nhật denominator báo cáo, giữ lịch sử dashboard cũ và explanation.
11. Review interval thiếu visibility và retrospective hunting nếu risk warrant.
12. Verified closure chỉ sau runtime test với affected population.

### 21.4. Bài học

Một **source health percentage** có mẫu số chỉ gồm các source đã biết có thể báo 100% dù thiếu cả một cloud account. **Independent asset discovery và reconciliation** quan trọng ngang kiểm collector heartbeat.

## 22. Case study 2: change IAM và ngoại lệ sắp hết hạn

### 22.1. Bối cảnh

Nhóm vận hành muốn mở rộng một role support để hỗ trợ khách hàng. PR thay IAM policy từ một resource cụ thể thành wildcard. Cùng lúc có local admin exception không MFA hết hạn vào cuối ngày. CI/CD kiểm code thành công; bảng IAM vẫn hiện “approved” theo một decision cũ.

### 22.2. Những rủi ro khác nhau

- **Privilege escalation/exposure:** wildcard có thể mở nhiều data/resource ngoài business need.
- **Governance:** approval cũ không bao phủ diff mới.
- **Identity assurance:** local admin MFA gap chưa hết hiệu lực về mặt kỹ thuật.
- **Expiry:** nếu hết hạn mà không có reapproval, governance status phải EXPIRED.
- **Audit:** role change và exception usage cần được log.
- **Operational safety:** thu hồi break-glass mà không có recovery alternative có thể gây outage.

### 22.3. Checklist xử lý

- [ ] Đối chiếu effective IAM policy/trust/resource scope trước và sau, không dựa tên role.
- [ ] Chạy negative action/resource/tenant tests trên scope được phép.
- [ ] Kiểm service/data owner approval cho tăng quyền ngoài scope.
- [ ] Dừng hoặc hạn chế deployment theo critical gate nếu quyền quá mức được xác nhận.
- [ ] Xác minh decision mới đúng affected policy và artifact version.
- [ ] Rà soát local admin path, actual grants, next_review/expires_at.
- [ ] Kiểm compensating network/JIT/session auditing có hiệu lực.
- [ ] Nếu renewal được đề xuất, cần new risk assessment và explicit authority.
- [ ] Nếu phải thu hồi, thực thi safe recovery access plan, không tự phá DR.
- [ ] Ghi cả IAM finding và exception governance status, không gộp thành một checkbox.
- [ ] Retest actual runtime policies sau fix/revoke.
- [ ] Giữ evidence lịch sử của quyết định cũ.

### 22.4. Kết luận ví dụ

Nếu wildcard read đã được chứng minh cho phép đọc resources ngoài business need, đó là **confirmed IAM control failure trong test scope**. Không được tự khẳng định dữ liệu đã bị truy cập trái phép ngoài test. Nếu exception hết hạn nhưng vẫn có bypass, đó là một **approval/runtime gap** khác cần xử lý. Hai vấn đề có owner và closure tests riêng.

## 23. Case study 3: backup thành công nhưng DR không đạt

### 23.1. Bối cảnh

Một dịch vụ thanh toán có backup job SUCCESS mỗi ngày. Sau khi rotate data encryption key từ K1 sang K2, recovery account vẫn chỉ có quyền decrypt bằng K1. Trong buổi DR exercise, restore object hoàn tất nhưng application không đọc được một nhóm bản ghi đã mã hóa với K2.

### 23.2. Từng assertion và kết luận

| Assertion | Observed evidence | Verdict |
|---|---|---|
| Backup file được tạo | Backup job SUCCESS | PASS chỉ cho backup creation |
| Recovery identity decrypt với key mới | KMS access denied | FAIL trong exercise |
| Service đạt recovery acceptance | Application chưa đọc được dữ liệu | FAIL trong tested scenario |
| RTO/RPO có đạt không | Không có full business recovery | Không tuyên bố đạt |
| Data loss production có xảy ra không | Exercise failure, không có production incident evidence | Chưa có căn cứ |
| Unauthorized principal bị deny KMS | Cần test riêng | NOT_TESTED hoặc theo evidence |

### 23.3. Hành động

1. Ghi backup ID, key version, recovery identity, time và failure logs đã che nhạy cảm.
2. Kiểm BIA và affected business criticality.
3. Tạo finding cho key/recovery dependency.
4. Không mở KMS wildcard; thiết kế least-privilege grants trên đúng keys/contexts.
5. Rehearse decrypt/restore trên representative synthetic dataset.
6. Kiểm ứng dụng hoạt động, data integrity và transaction reconciliation.
7. Đo RTO từ disruption tới business/security acceptance, RPO từ last consistent recovery point.
8. Kiểm IAM deny tests và KMS audit events.
9. Cập nhật change gate cho key rotation: **DR path verification required**.
10. Giữ original FAIL history, retest mới và preventive actions.

### 23.4. Bài học

**Backup availability, restore feasibility và business/security recovery** là những assertions khác nhau. Nếu chỉ có daily backup job SUCCESS mà không có restore evidence, không thể tuyên bố DR readiness hoàn chỉnh.

## 24. Audit readiness: biến hoạt động thường ngày thành bằng chứng kiểm toán

### 24.1. Chuẩn bị theo từng claim

Khi auditor hỏi “Làm sao biết privileged access đã được kiểm soát trong kỳ?”, không chỉ gửi policy MFA. Gói chứng cứ có thể gồm:

- Inventory của required privileged identities/paths.
- Control description và version được áp dụng trong kỳ.
- Effective MFA/JIT/IAM policy exports hoặc test records.
- Authentication/privilege events và access review decisions.
- Exceptions còn hạn, compensating controls và scope.
- Findings/changes và retest sau remediation.
- Source health/known gaps, sample design và limitations.
- Assessor/reviewer role và decision history.

### 24.2. Evidence packet có thể xem xét

~~~yaml
assurance_packet_id: "AUD-SEC-2026-Q4-07"
purpose: "Privileged access assurance - synthetic example"
period:
  start: "2026-10-01T00:00:00Z"
  end: "2026-12-31T23:59:59Z"
scope:
  services: ["critical-service-example"]
  environments: ["production"]
  required_units: ["CU-IAM-PRIV-01", "CU-IAM-PRIV-02"]
control:
  id: "IAM-PRIV-01"
  version: "v4"
  requirement_ref: "PRIVILEGED-AUTH-POLICY"
assessment:
  verdict: "INCONCLUSIVE"
  reason: "One privileged login source lacks full-period evidence"
evidence:
  refs: ["EV-IAM-050", "EV-IAM-051"]
  known_gaps: ["SRC-IAM-LOCAL-02"]
risk:
  exception_refs: ["EX-IAM-2026-003"]
  decision_validity_requires_review: true
owner_role: "identity-assurance"
reviewer_role: "security-assurance"
classification: "TRAINING_ONLY"
~~~

Packet này cố ý **INCONCLUSIVE** vì thiếu full-period source; không được gắn mác “audited PASS” vì có policy và một số log.

### 24.3. Chống audit-by-screenshot

Một screenshot thiếu timestamp, system identity, policy version hoặc original source không đủ hỗ trợ critical assertion nếu không thể xác minh. Với automated evidence nên giữ **source references, run IDs, timestamps, retrieval method, integrity và access audit**. Không đưa PII/secrets nguyên văn vào tài liệu chia sẻ rộng.

### 24.4. Operating evidence và audit period

Nếu control được sửa giữa kỳ, phải ghi:

- Thời điểm failure được phát hiện.
- Khoảng thời gian gap hoặc chưa quan sát được.
- Date fix deployed.
- Date retest PASS.
- Scope và remaining uncertainty.

Không được **dùng current PASS để xóa lịch sử failure** trong audit period. Chất lượng assurance cao thể hiện cả các giới hạn mà chương trình phát hiện.

## 25. Những anti-pattern cần phát hiện khi dùng checklist

| Anti-pattern | Tín hiệu | Biện pháp |
|---|---|---|
| **Checkbox theater** | Tick đủ 100% nhưng không có test/evidence | Assertion + evidence contract bắt buộc |
| **No alert = no threat** | Dashboard im lặng không có source health | Expected source inventory và synthetic tests |
| **Scanning-only assurance** | Chỉ dựa vào SAST/SCA/image scans | Runtime IAM/data/detection/recovery tests |
| **Self-approval** | Người triển khai tự sửa PASS/exception | SoD, immutable evidence, independent review |
| **Green by denominator** | Bỏ missing/unknown units khỏi scope | Independent population reconciliation |
| **Risk accepted = PASS** | Exception được cộng vào numerator | Tách technical verdict và risk decision |
| **Stale evidence** | PASS cũ sau IAM/key/data/release change | Event-driven reassessment |
| **Ownerless control** | Không ai phản hồi khi check FAIL | Owner/backup/escalation |
| **Permanent suppression** | Detection disable vô hạn | Timebound rule + regression test |
| **Backup = DR** | Không có restore test mà báo RTO đạt | Representative restore/decrypt |
| **No negative tests** | API 200 nên authz PASS | Role/object/path deny matrix |
| **Release approved = verified** | Chưa kiểm post-deploy state | Separate approval/deploy/validation states |
| **Ticket closed = remediated** | Không có retest actual runtime | CLOSED_VERIFIED với evidence |
| **Hash = trustworthy** | Hash của source tự khai không kiểm trust | Provenance và source controls |
| **High-level control only** | LOG-01 PASS dựa một nguồn | Control units per required source |
| **Vendor report covers all** | Bỏ customer responsibility và new services | Scope/period/shared-responsibility review |
| **Unsafe automation** | Auto-disable key/firewall gây outage | Risk-based playbooks, dry run, safety |
| **Unbounded exception** | “Until migration” không có end date | Finite expiry, owner, milestone |
| **No historical truth** | Rewriting FAIL thành PASS sau fix | Versioned evidence/decision trails |
| **Zero findings = maturity** | Coverage thiếu, scanner không chạy | Completeness và detection capability metrics |

### 25.1. Triệu chứng dashboard đánh lừa

- Số alert giảm nhưng active suppressions tăng.
- % compliance tăng vì số assets được quét giảm.
- Số vulnerabilities giảm vì runtime inventory biến mất.
- Tốc độ closure nhanh nhưng repeat findings cao.
- 100% IAM roles “reviewed” bằng auto-approve.
- Backup jobs PASS trong khi restore rehearsal chưa chạy.
- Exceptions giảm vì chuyển thành acceptance không expiry.

Nếu metric thay đổi không có lời giải thích dựa trên **cohort, scope, policy version và evidence quality**, không nên tự tuyên bố cải thiện bảo mật.

## 26. Câu hỏi tự kiểm tra và hướng trả lời

**Câu 1.** Một dashboard hiển thị 100% log collectors healthy. Có thể kết luận required security events đã được ghi đầy đủ không?

**Gợi ý:** Không. Cần independent source inventory, event class coverage, parser fields, source→SIEM/alert test và source-silence monitoring. Dashboard có thể bỏ các sources chưa onboard.

**Câu 2.** Trong tháng có 80 applicable control units, 52 PASS, 10 FAIL, 12 INCONCLUSIVE và 6 NOT_TESTED. Verified coverage là bao nhiêu?

**Gợi ý:** 52/80 = 65%. Không loại 18 units chưa có kết luận, không cộng accepted risk vào PASS.

**Câu 3.** Một critical authorization test bị FAIL trên staging. Có thể khẳng định production đã rò dữ liệu không?

**Gợi ý:** Không tự suy ra. Đây là finding trong tested scope; cần xem actual deployment và incident evidence. Với critical trust boundary, vẫn có thể cần hold release và risk-based containment ngay.

**Câu 4.** Control owner nói “CI xanh”, nhưng image digest production không phải artifact vừa quét. Có thể đánh supply-chain control PASS không?

**Gợi ý:** Chưa. Cần đối chiếu actual deployed artifact, build provenance, admission/trust policies và test tương ứng.

**Câu 5.** Một risk exception MFA có approval hợp lệ trong 14 ngày. Primary control có PASS chưa?

**Gợi ý:** Không. Control vẫn FAIL ở đường bypass, còn risk disposition là accepted trong scope/kỳ, đi kèm mitigation và remediation.

**Câu 6.** Backup job SUCCESS hằng ngày nhưng chưa có restore test bằng recovery role. Có thể nói DR sẵn sàng?

**Gợi ý:** Chưa. Job success không chứng minh decrypt, data integrity, app startup, RTO/RPO và security recovery.

**Câu 7.** Sau khi sửa parser, một synthetic event có đầy đủ actor field. Có thể tuyên bố logging hoạt động cả quý?

**Gợi ý:** Chỉ trong test scope/time và event class. Operating effectiveness cả kỳ cần event/history hoặc sampling đủ và source coverage.

**Câu 8.** Một cloud account mới chỉ xuất hiện trong organization inventory, chưa có ở scanner. Nên loại account khỏi denominator vì “chưa onboard” không?

**Gợi ý:** Không. Đây là coverage gap; tạo required units, ghi NOT_TESTED/INCONCLUSIVE phù hợp và onboard sources.

**Câu 9.** Detection alert volume giảm 80% sau rule tuning. Có chắc detection tốt hơn?

**Gợi ý:** Không. Phải kiểm positive/negative scenarios, false negatives, suppression, source data quality và analyst outcomes.

**Câu 10.** Một service owner chấp nhận rủi ro nhưng contractual requirement không cho phép miễn. Đã đủ authority chưa?

**Gợi ý:** Không. Cần applicability và decision theo nghĩa vụ/bộ phận có thẩm quyền; internal risk acceptance không tự miễn hợp đồng.

**Câu 11.** Đội engineering đã merge một fix, ticket trạng thái Done. Finding được VERIFIED_CLOSED chưa?

**Gợi ý:** Chưa cho tới khi actual deployed state được retest đạt assertion, affected units đủ và bypass tạm được cleanup.

**Câu 12.** Vì sao cần kiểm thông tin owner/backup owner ngay cả khi mọi technical tests PASS?

**Gợi ý:** Nếu không có người accountable, alerts, exceptions, remediation và incident handling có thể không được thực hiện đúng lúc. Owner lifecycle là một phần của governance effectiveness.

**Câu 13.** Khi một KMS key rotation làm DR restore fail, nên chỉ thêm quyền wildcard cho recovery account để sửa nhanh?

**Gợi ý:** Không. Cần xét least privilege, approved key/data scope, test restore/decrypt/deny, audit và risk/availability tradeoff.

**Câu 14.** Nếu 25 PASS, 4 FAIL, 7 INCONCLUSIVE và 4 NOT_TESTED trong 40 applicable units, vì sao không được chỉ báo pass rate 25/29?

**Gợi ý:** 25/29 là một metric của conclusive subset; không phải verified coverage trên required population. Cần báo 25/40 = 62,5% cùng unknowns.

**Câu 15.** Một IAM role cũ tên ReadOnly nhưng có thể assume role với quyền administrator. Checklist nào phải bắt được?

**Gợi ý:** Effective permissions/trust graph, negative access tests, role assumption logs, approval và blast-radius review; tên role không phải chứng cứ.

**Câu 16.** Khi incident nghi compromise, rollback image về phiên bản trước có chứng minh đã loại attacker?

**Gợi ý:** Không. Cần IR/trusted recovery, đánh giá compromise window, credentials/persistence, source trust, backup, forensic evidence và security acceptance.

**Câu 17.** Mỗi tuần mọi team tick 100% checklist nhưng không có finding nào dù asset inventory tăng nhanh. Điều gì đáng kiểm?

**Gợi ý:** Missing assets, denominator, stale evidence, source coverage, false assurance/auto-approve và sampling quality, không tự coi zero finding là posture tốt.

**Câu 18.** Khi một ngoại lệ đến hạn và local admin path còn dùng cho DR, có nên tự động disable ngay không?

**Gợi ý:** Expire approval và escalate, nhưng runtime enforcement cần safe playbook, alternative access, authority, tests và containment; không auto-renew hoặc disable mù.

**Câu 19.** Vì sao phải giữ các failed test results sau khi remediation PASS?

**Gợi ý:** Để chứng minh timeline của gap, nguyên nhân, impact, thời điểm khắc phục, hiệu lực control theo audit period và preventive progress.

**Câu 20.** Tần suất hằng tuần có đủ cho mọi critical security controls không?

**Gợi ý:** Không. Những control nhạy cảm có thể cần continuous monitoring/event-driven tests; lịch theo risk, BIA, threat và khả năng phát hiện/khắc phục.

## 27. Bài thực hành cuối chương: vận hành một ca security assurance

### 27.1. Bối cảnh giả định

Bạn là **Security Assurance On-call Lead** phụ trách ba dịch vụ: Order API, Payment Worker và Admin Portal trong một cloud platform. Vào đầu ca, các sự kiện sau được ghi nhận:

| ID | Quan sát ban đầu | Điều đã biết | Điều chưa biết |
|---|---|---|---|
| **S-01** | Cloud account mới xuất hiện | Organization inventory có account | IAM/logging/backup baseline đạt chưa |
| **S-02** | Admin SIEM source im lặng | Last-seen đã quá ngưỡng nội bộ | Collector lỗi hay source không phát event |
| **S-03** | Role payment worker được mở wildcard | IaC/policy diff có wildcard | Effective grant và business need |
| **S-04** | Pipeline triển khai image với mutable tag | Manifest dùng tag | Runtime digest có khớp approved artifact không |
| **S-05** | Backup job SUCCESS | Backup catalog có snapshot | Restore/decrypt đạt RTO/RPO không |
| **S-06** | Local admin MFA exception hết hạn | Decision expiry ở quá khứ | Runtime bypass còn hoạt động không |
| **S-07** | Vendor API token không có expiry | Access record | Token đang dùng, data scope và revoke path |
| **S-08** | Detection rule được suppress | Suppression config | Negative scenario có bị bỏ sót không |
| **S-09** | Order API release thêm export endpoint | Change record | Object/tenant authorization tests có đủ không |
| **S-10** | KMS key policy mới | Policy diff | Recovery account decrypt được backup mới? |
| **S-11** | Payment event backlog tăng | Queue metric | Có duplicate/transaction divergence không |
| **S-12** | Remediation ticket đóng | Ticket Done | Fix đã deploy và retest actual unit chưa |

Tất cả là **dữ liệu tổng hợp**; không có bằng chứng về incident/breach ngoài những điều đã nêu.

### 27.2. Nhiệm vụ người học

1. Xác định **critical security objectives** của ba dịch vụ.
2. Tạo bảng asset/control unit cho ít nhất **10 required assertions**.
3. Chọn nhịp xử lý cho mỗi item: immediate, shift, weekly hay scheduled review và giải thích.
4. Phân loại S-01..S-12 thành **confirmed control failure, evidence gap, material change, governance gap hoặc signal cần triage**.
5. Không tự gắn FAIL nơi evidence chưa đủ; phân biệt **planned-state** với **effective runtime**.
6. Đề xuất test negative/positive cho S-03 và S-09, bao gồm actor, resource, tenant, scope.
7. Viết procedure nguồn→collector→SIEM→alert để kiểm S-02/S-08.
8. Thiết kế kiểm actual deployed digest/provenance cho S-04.
9. Giải thích vì sao S-05 không đủ cho RES-01 và thiết kế representative restore test.
10. Tách decision expiry và runtime access đối với S-06, chọn safe enforcement path.
11. Tạo vendor token offboarding/expiry test cho S-07.
12. Phân tích key rotation/recovery dependency của S-10, không dùng wildcard KMS.
13. Thiết kế reconciliation/idempotency tests cho S-11, tránh suy duplication từ backlog một mình.
14. Xác định điều kiện CLOSED_VERIFIED cho S-12.
15. Viết **3 finding records** có criterion, condition, evidence, owner, plan và retest.
16. Viết **1 exception request** nhưng để PENDING nếu thiếu approval và expiry.
17. Chuẩn bị shift handoff với owner, next action và evidence IDs.
18. Viết executive summary 200–350 từ nêu risk/unknown/decision requirements.
19. Tính verified coverage trên dataset 40 units ở mục 18.3.
20. Đề xuất **5 preventive meta-controls** để ngăn các tình huống lặp lại.
21. Chỉ ra ít nhất **3 mục trong checklist cũ** có thể gây false assurance.
22. Phác một review plan cho tuần và tháng sau, gắn material triggers.

### 27.3. Gợi ý triage không phải verdict áp đặt

| Tình huống | Triage hợp lý |
|---|---|
| **S-01** | Population/source enrollment gap, tạo required units và baseline tests |
| **S-02** | Visibility loss cần source/collector/parser investigation, không tự kết luận attack |
| **S-03** | High-impact IAM scope diff, cần effective permission test trước verdict |
| **S-04** | Artifact identity/evidence gap, kiểm deployed digest trước khi nói PASS |
| **S-05** | Backup success verified, restore readiness chưa có evidence |
| **S-06** | Expired decision; runtime bypass phải kiểm, safe response có owner |
| **S-07** | Third-party credential lifecycle issue, quyền/expiry và revoke tests |
| **S-08** | Potential detection blind spot; positive/negative scenario tests |
| **S-09** | New API trust boundary; negative tenant/export tests cần thiết |
| **S-10** | Potential DR/key access regression; controlled decrypt/restore test |
| **S-11** | Payment integrity signal; reconciliation và business owner escalation |
| **S-12** | Implementation/closure uncertainty; retest actual deployed population |

Một high-impact event có thể cần **immediate containment/escalation** trước khi root cause hoàn tất, nhưng báo cáo phải ghi mức confidence. Không tuyên bố “có data breach” chỉ vì wildcard role hoặc log gap.

### 27.4. Ví dụ kết quả tổng hợp của học viên

~~~yaml
training_only: true
assessment_id: "SHIFT-ASSURANCE-EXERCISE-01"
services: ["order-api", "payment-worker", "admin-portal"]
required_control_units: 40
results:
  pass: 25
  fail: 4
  inconclusive: 7
  not_tested: 4
verified_coverage: "62.5%"
confirmed_risk:
  - "one critical logging assertion failed in synthetic test scope"
uncertainties:
  - "new cloud account has missing evidence"
  - "rollback key compatibility not tested"
  - "effective wildcard IAM permission requires validation"
operational_decisions:
  - "review response to expired privileged exception"
  - "determine scope of affected services for log-source issue"
closure_conditions:
  - "runtime effective-state tests"
  - "required security and business assertions pass"
  - "new evidence stored with traceable scope"
next_review:
  - "follow up IAM tests"
  - "source reconciliation and parser retest"
  - "key rotation impact assessment"
~~~

**Mục tiêu chấm:** trình bày điều **biết, chưa biết và phải làm**, không ép tất cả 12 quan sát thành FAIL hoặc PASS.

## 28. Checklist cho người kiểm tra độc lập (assurance reviewer)

### 28.1. Review tính đúng của checklist

- [ ] Có source of truth cho required control population.
- [ ] Mỗi check map security objective/requirement/control unit.
- [ ] Acceptance criteria có thể kiểm, không mơ hồ như “đủ an toàn”.
- [ ] Positive/negative tests phù hợp threat và use case.
- [ ] Owner/reviewer/approver không nhầm quyền.
- [ ] Checklist có risk-based cadence và event triggers.
- [ ] Có decision tree khi FAIL, unknown, expired, N/A.
- [ ] Không có auto-PASS khi collector mất/exception accepted.
- [ ] Mỗi item có evidence contract và retention/data protection.
- [ ] Review các metadata giả định: period, timezone, versions, environment.

### 28.2. Review evidence và conclusions

- [ ] Source, timestamp, system identity và collection method rõ.
- [ ] Tested artifact/runtime configuration khớp claimed target.
- [ ] Sample population và exclusions được ghi.
- [ ] Evidence đủ về correctness/effectiveness, không chỉ config enabled.
- [ ] Evidence conflicts được điều tra và documented.
- [ ] Controls bù trừ/DR/vendor assumptions được test theo scope.
- [ ] PASS/FAIL/INCONCLUSIVE/NOT_TESTED/N/A được dùng đúng.
- [ ] Risk acceptance không tăng số PASS.
- [ ] Critical findings có owner/action/decision đúng authority.
- [ ] Retest results giữ lịch sử và linked findings.
- [ ] Báo cáo không overclaim compliance/chứng nhận/absence of breach.

### 28.3. Review vận hành liên tục

- [ ] New assets/revisions làm cập nhật control population.
- [ ] Source health/coverage đang được đo và cảnh báo.
- [ ] Expired exceptions/runtime bypasses được reconciliation.
- [ ] Material changes tạo targeted reassessment đúng lúc.
- [ ] Incidents/DR drills tạo lessons learned/controls mới.
- [ ] Vulnerability/patch remediation được verified trên runtime.
- [ ] KPI có độc lập denominator, period và metric version.
- [ ] Owner changes, role expiry và on-call handoff được xử lý.
- [ ] Independent sampling có thể tìm lỗi dashboard hoặc evidence pipeline.
- [ ] Những control FAIL/unknown không bị dồn qua kỳ sau vô thời hạn.

## 29. Master checklist áp dụng khi vận hành Security Assurance

Phần này là **bản tóm tắt triển khai** để dùng ở cuộc họp giao ca hoặc review chương trình; các câu trả lời phải đi kèm evidence/owner ở các mục chi tiết phía trên.

### 29.1. Trước khi bắt đầu một kỳ kiểm

- [ ] Có current asset/service/data inventory và criticality.
- [ ] Có current requirement/control library, owner và version.
- [ ] Required control units được sinh từ applicability có căn cứ.
- [ ] Có test plan, evidence source và quality checks.
- [ ] Time window, timezone, deadlines, review authority rõ.
- [ ] Các material changes sau kỳ kiểm trước đã được nhận diện.

### 29.2. Trong mỗi ca và chu kỳ

- [ ] Critical telemetry/source/detection health được xác minh.
- [ ] IAM/admin privileges, vendor tokens và key access changes được kiểm.
- [ ] New cloud/network/runtime/pipeline deviations có owner.
- [ ] Critical vulnerabilities và active threats được triage.
- [ ] Data integrity/backup/DR signals được xem đúng risk.
- [ ] Required control tests/positive-negative scenarios được thực hiện.
- [ ] Findings, exceptions, remediation và deadlines được theo dõi.
- [ ] Unknowns/coverage gaps không bị loại khỏi report.

### 29.3. Khi có sự kiện bất thường

- [ ] Trigger, scope và confidence được xác minh.
- [ ] Evidence được bảo toàn; không xóa logs để làm dashboard đẹp.
- [ ] Critical risk có containment/IR/escalation theo quyền.
- [ ] Actual effective state được kiểm, không chỉ intended state.
- [ ] Safe rollback/fail-forward và business impact được cân nhắc.
- [ ] Data/identity/vendor/crypto dependencies được review khi affected.
- [ ] Fix được retest; temporary bypass không bị bỏ quên.
- [ ] Risk decision còn hạn và đúng thẩm quyền.

### 29.4. Trước khi công bố kết luận

- [ ] PASS có scope, time, method, source và limitation.
- [ ] FAIL có finding và next action.
- [ ] INCONCLUSIVE/NOT_TESTED được hiển thị và có owner.
- [ ] N/A có applicability evidence, không phải thiếu scan.
- [ ] Accepted risk hiển thị riêng primary control.
- [ ] Mẫu số coverage từ independent population, không từ PASS-only query.
- [ ] Critical boundaries được nêu riêng thay vì bị che bằng trung bình.
- [ ] Evidence được bảo vệ và có thể truy source/lineage.
- [ ] Báo cáo cho người có thẩm quyền xác định decision required.
- [ ] Next review và event-driven retest đã được lập lịch.

### 29.5. Dấu hiệu một chương trình thực sự vận hành tốt

Chương trình security assurance vận hành tốt **không nhất thiết có zero FAIL**. Trái lại, dấu hiệu tốt là:

- Phát hiện control gaps sớm trước khi rủi ro tích lũy.
- Asset mới không bị mất khỏi inventory.
- Failed source hoặc missing data được báo rõ.
- Đội ngũ biết ai chịu trách nhiệm và hành động nào cần approval.
- Khi fix, có verified retest và preventive action.
- Critical events có response và forensic evidence phù hợp.
- Risk acceptance có hạn và không biến thành camouflage.
- KPI có nghĩa và đối soát được với runtime.
- Các bài học từ incident/change/DR làm framework tốt hơn theo thời gian.

## Kết luận

**Checklist vận hành Security Assurance là cơ chế thực thi liên tục của việc kiểm chứng bảo mật dựa trên bằng chứng.** Giá trị không nằm ở số ô được tick mà ở sự liên kết giữa **security objective, risk, applicable control, affected population, test, reliable evidence, verdict, action và verified closure**. Checklist cần được thiết kế theo nhịp ca/ngày/tuần/tháng/quý, đồng thời thay đổi theo release, IAM/key/data changes, incidents, vendor exposure và recovery events.

Trong **SECURITY_SECURITY_ASSURANCE**, cách làm bền vững là **kiểm kê đúng → chọn control đúng → thu và kiểm bằng chứng đúng → báo kết luận trung thực → xử lý critical gaps/unknowns → kiểm chứng remediation → giám sát tái phát và cập nhật framework**. Khi có owner, expiry, decision gates, evidence quality và KPI với mẫu số độc lập, chương trình sẽ biến security assurance từ hoạt động kiểm toán thời điểm thành **năng lực vận hành có thể đo, giải trình và cải tiến liên tục**.





