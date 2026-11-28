# Post-release monitoring: Giám sát sau phát hành để bảo đảm an toàn bằng bằng chứng

## Mục tiêu học tập

Sau khi hoàn thành bài học này, người học có thể:

1. Giải thích **post-release monitoring** trong **release assurance**, phân biệt nó với kiểm thử trước phát hành, xác minh triển khai, giám sát vận hành thường ngày và xử lý sự cố.
2. Thiết kế kế hoạch giám sát dựa trên **rủi ro của bản phát hành**, phạm vi thực tế, đối tượng người dùng, dữ liệu, trust boundaries, security objectives và mức độ quan trọng của dịch vụ.
3. Xác định baseline, observation windows, **security/service indicators**, điều kiện đủ bằng chứng, ngưỡng cảnh báo, ngưỡng dừng rollout và điều kiện tiếp tục.
4. Theo dõi những thay đổi về **IAM/authorization, API, network, logging/detection, data protection, supply chain, third parties, reliability và recoverability** sau phát hành.
5. Phân biệt kết quả đo **tình trạng hệ thống** với kết quả **assurance test**, nhận diện missing telemetry, sampling bias, denominator drift và failure không thể quan sát.
6. Thiết kế quy trình **canary → mở rộng theo giai đoạn → stabilization → handover**, xác định trách nhiệm đánh giá, phản ứng, rollback và forward-fix.
7. Xây dựng báo cáo kết luận có thể kiểm toán với **release ID → risk/requirement → control → monitoring/test → evidence → decision → finding → remediation/retest**.
8. Áp dụng phương pháp trên vào tình huống triển khai Order API nhiều region và nhận biết khi nào phải dừng phát hành dù CI/CD hiển thị xanh.

> **Bối cảnh:** Bài học thuộc mô-đun **SECURITY_SECURITY_ASSURANCE**: đánh giá có bằng chứng rằng hệ thống đáp ứng mục tiêu bảo mật từ phân tích rủi ro, yêu cầu và security controls tới kiểm thử, audit, khắc phục và assurance liên tục. Những hệ thống, mức ngưỡng, số liệu và SLA trong ví dụ là **giả định đào tạo**, không phải ngưỡng chung bắt buộc cho mọi tổ chức.

## 1. Post-release monitoring là gì?

**Post-release monitoring** là quá trình **quan sát, kiểm tra và ra quyết định có cấu trúc sau khi một phiên bản được triển khai hoặc đưa vào phục vụ**, nhằm phát hiện regression, sai lệch security controls, rủi ro mới, sự cố phát sinh và đánh giá liệu release có tiếp tục đáp ứng **tiêu chí chấp nhận** trong môi trường thực tế.

Nó cần trả lời đồng thời bốn câu hỏi:

1. **Đúng phiên bản, đúng phạm vi?** Release nào đang chạy ở account, region, cluster, tenant, host, service và data plane nào?
2. **Vận hành có ổn định?** Chức năng, latency, error rate, saturation, data integrity, dependencies và khả năng phục hồi còn trong điều kiện đã chấp thuận?
3. **Bảo mật có đúng?** Identity, authorization, secret, encryption, audit, detection, data flows và policy vẫn được thực thi như mục tiêu?
4. **Bằng chứng đủ tin cậy?** Telemetry có bao phủ đối tượng cần quan sát, đúng thời gian, không bị rơi event, đủ để đưa ra verdict?

**Triển khai thành công không tương đương release assurance đạt.** Một pipeline có thể báo SUCCESS vì Deployment đã được Kubernetes API chấp nhận, trong khi:

- Một replica cũ vẫn giữ authorization policy lỏng hơn.
- API ghi log thành công nhưng parser mới làm mất actor ID.
- Feature flag mở cho tenant ngoài danh sách được duyệt.
- Một region không nhận alert khi phát sinh hành vi đặc quyền.
- Error rate chưa tăng vì canary ít request và chưa đi qua chức năng rủi ro.
- Rollback artifact không tương thích dữ liệu đã migrate.

### 1.1. Phân biệt các hoạt động trong vòng đời

| Hoạt động | Thời điểm | Câu hỏi chính | Giới hạn |
|---|---|---|---|
| **Pre-release assurance** | Trước phát hành. | Artifact, code, dependency, cấu hình, threat model và test đã đáp ứng điều kiện để triển khai? | Test môi trường trước production có thể không phản ánh traffic, data và dependencies thực. |
| **Deployment verification** | Trong/sau thao tác rollout. | Đúng artifact/digest và cấu hình đã áp vào đúng targets? | Deployed state không tự chứng minh runtime behavior, security effectiveness. |
| **Post-release monitoring** | Khi phiên bản bắt đầu chạy, qua giai đoạn quan sát được định nghĩa. | Phiên bản mới có duy trì security controls và mục tiêu vận hành với traffic/state thực không? | Quan sát tốt vẫn bị giới hạn bởi coverage, mẫu và thời gian. |
| **Continuous monitoring** | Trong vận hành lâu dài. | Có drift, attack, control failure, incident hoặc thay đổi risk đáng chú ý? | Không thay thế việc chốt bằng chứng theo release và quyết định release gate. |
| **Incident response** | Khi sự cố đã hoặc nghi đang xảy ra. | Có cần containment, investigation, escalation, recovery, notification? | Có mục tiêu xử lý sự cố, không đơn thuần đánh giá bản phát hành. |
| **Post-release review** | Sau thời gian theo dõi hoặc sau incident. | Có thể chấp thuận/handover release? Học được gì và còn finding nào? | Review chỉ có giá trị nếu bằng chứng/giới hạn được lưu đầy đủ. |

Các hoạt động gắn với nhau nhưng không hoán đổi. Đặc biệt, **post-release monitoring không nên chờ tới khi người dùng báo lỗi** mới bắt đầu.

### 1.2. Tại sao cần gắn monitoring với release?

Nếu dashboard chỉ hiển thị trạng thái dịch vụ hiện tại, rất khó xác định:

- Lỗi nào thực sự xuất hiện **sau** bản phát hành.
- Những pods đang chạy phiên bản mới hay cũ.
- Các route, nhóm người dùng, feature flags nào đã nhận release.
- Phạm vi bị ảnh hưởng là canary, một tenant hay toàn region.
- Metrics đang gộp dữ liệu từ release khác nhau.
- Khi nào phải revert và revert những thành phần nào.

Vì vậy post-release monitoring cần **release identity và change context** nhất quán: release ID, artifact digest, configuration version, deployment ID, feature flag version, environment, region/cluster và mốc rollout.

## 2. Đầu ra của một chương trình post-release assurance

Một kế hoạch giám sát tốt không chỉ là dashboard mà là **hồ sơ cho phép ra quyết định**.

### 2.1. Năm sản phẩm đầu ra

| Đầu ra | Nội dung bắt buộc | Người sử dụng |
|---|---|---|
| **Release monitoring plan** | Risk scenarios, targets, baseline, observation windows, indicators, gates, owners, fallback. | Release manager, SRE, security, service owner. |
| **Telemetry & test coverage record** | Nguồn dữ liệu, population, health, security canaries, negative tests, gaps. | Control owner, security assurance, SOC. |
| **Decision timeline** | Khi nào mở rộng, hold, rollback, forward-fix, escalate; dựa trên evidence nào. | Change/release authority, on-call, risk owner. |
| **Findings/remediation log** | Security regression, incident, data-quality gap, owners, deadlines và retest. | Engineering, SOC, GRC, audit. |
| **Release assurance conclusion** | Pass/partial/fail/inconclusive theo mục tiêu, phạm vi, kỳ và evidence. | Management, audit, service handover. |

Một kết luận tốt mô tả **điều gì đã được đánh giá và điều gì chưa được chứng minh**. Đạt canary không đồng nghĩa “an toàn trong mọi trường hợp”; chưa có incident trong hai giờ cũng không chứng minh không có đường tấn công khác.

### 2.2. Release scope phải xác định được

Ví dụ phạm vi:

> Release ORD-2026.11.28-R3, artifact digest D, API gateway configuration G7, Order API version V2.7, được triển khai cho 10% traffic ở production region A và 0% ở region B/C lúc 09:00 UTC.

Đối chiếu thêm:

- Accounts, clusters, namespaces, workloads, node pools.
- Tenants/customer segments và phân loại dữ liệu.
- Identity provider và các loại principal.
- Endpoints, auth scopes, data flows, dependencies.
- Cấu hình runtime/feature flags không được đóng gói trong artifact.
- Lịch sử batch rollout và phần đang rollback/forward-fix.

**Không có release scope đáng tin thì không có mẫu số chính xác cho monitoring coverage.**

## 3. Phương pháp risk-based: phải giám sát điều gì?

Không nên bắt đầu với “dashboard đang có chỉ số nào?”, mà phải bắt đầu với **thay đổi nào có thể gây mất an toàn hoặc làm hỏng mục tiêu kinh doanh**.

### 3.1. Chuyển change impact thành monitoring requirements

1. **Mô tả thay đổi:** code, config, IAM, DB schema, dependency, artifact, vendor hay data flow.
2. **Lập bản đồ tác động:** business service, users, tenants, assets, quyền, data class, region.
3. **Xác định security objectives:** confidentiality, integrity, availability, authorization, auditability, recoverability.
4. **Viết risk scenarios:** bypass, data export, telemetry failure, secret compromise, corruption, replay, outage.
5. **Mapping controls và expected behavior:** control nào phải giữ nguyên/được cải thiện?
6. **Chọn indicators và probes:** metric, log, trace, event, tests, synthetic transaction, source-health.
7. **Định nghĩa decision rules:** mức nào cần investigate, hold, rollback, trigger incident?
8. **Định nghĩa evidence và owner:** nguồn, khoảng thời gian, reviewer, retention và limitations.

~~~mermaid
flowchart TD
    A["Release diff + threat model + change request"] --> B["Tài sản, dữ liệu, trust boundaries và risk scenarios"]
    B --> C["Security requirements & controls"]
    C --> D["Indicators + behavioral tests + telemetry health"]
    D --> E["Baseline + canary/rollout/stabilization windows"]
    E --> F["Evidence-based gate"]
    F -->|Accept| G["Expand / handover"]
    F -->|Hold| H["Investigate / collect evidence"]
    F -->|Fail| I["Contain / rollback / forward-fix"]
    H --> F
    I --> J["Findings, retest & updated assurance"]
    G --> K["Continuous monitoring"]
    K --> J
~~~

### 3.2. Ví dụ risk-to-monitoring matrix

| Release change | Kịch bản rủi ro | Signal / test | Gate/response |
|---|---|---|---|
| Đổi JWT issuer/audience. | Token sai audience vẫn được chấp nhận hoặc user bị từ chối sai. | Negative authentication/authorization tests, auth failure mix, audit actor. | Dừng rollout nếu bypass được chứng minh; điều tra nếu auth failure tăng. |
| Thêm OAuth scope cho integration. | Service principal đọc dữ liệu ngoài mục đích. | Effective permission diff, out-of-scope access deny test, egress audit. | Block khi scope rộng trái policy; kiểm tra dữ liệu đã truy cập. |
| Đổi parser audit logs. | Mất actor/target hoặc event loại Critical. | Raw vs normalized field completeness, canary event-to-alert. | Hold/fail khi không còn nhận diện hoặc phát hiện hành vi ưu tiên. |
| DB migration. | Dữ liệu bị mất, duplicate, không nhất quán. | Reconciliation count, checksums phù hợp, synthetic transaction, backup markers. | Dừng nếu integrity criterion fail; chọn phương án recovery phù hợp. |
| Đổi network egress. | Workload có thể gửi dữ liệu tới endpoint chưa duyệt. | Effective route/policy, synthetic allow/deny connectivity, flow logs. | Rollback/contain khi egress vượt scope. |
| Đổi feature flag. | Tính năng mở cho sai tenant/data class. | Flag evaluation, tenant-segment test, access logs, exposure count. | Tắt flag và điều tra nếu exposure sai. |
| Đổi cloud/KMS key policy. | Service mất decrypt hoặc principal lạ có quyền. | Effective KMS access, decrypt canary được phép, deny test, key audit. | Dừng nếu key access không hợp lệ hoặc khả năng restore bị ảnh hưởng. |
| Đổi DR routing. | Failover không khôi phục chức năng đúng RTO/RPO. | Dependency health, authorized failover exercise, recovery-point checks. | Giữ release chưa accepted nếu recovery objective chưa có evidence. |

**Số monitor không quan trọng bằng mức bao phủ những risk scenarios trọng yếu.** Một service có 200 metrics nhưng không kiểm tra authorization bypass vẫn có gap lớn.

## 4. Các giai đoạn giám sát và thời gian quan sát

Thời lượng monitoring phụ thuộc **rủi ro, mức traffic, tần suất hành vi, chu kỳ nghiệp vụ và độ trễ failure mode**. Không nên coi một khoảng “30 phút sau deploy” là quy tắc phổ quát.

### 4.1. Release timeline

| Giai đoạn | Khi nào | Việc cần làm |
|---|---|---|
| **T-Preflight** | Trước rollout. | Chốt scope, baseline, telemetry readiness, owner, gates, rollback và test fixtures. |
| **T0 Deployment** | Bắt đầu áp version/config. | Log release markers, digest, targets, actor, start/end times và trạng thái từng batch. |
| **T1 Canary observation** | Traffic/targets giới hạn. | Positive/negative probes, security signals, service SLIs, telemetry health và risk review. |
| **T2 Progressive rollout** | Mở rộng theo batch/region/tenant. | Lặp gates cho từng cohort, kiểm tra cross-version compatibility, dependencies. |
| **T3 Stabilization** | Đã mở rộng xong, qua cửa sổ theo dõi phù hợp. | Xem trend, backlog, latent errors, auth/data/alert patterns, control drift. |
| **T4 Handover** | Chuyển sang steady-state support. | Kết luận, findings còn mở, owner on-call, evidence index và next review triggers. |
| **T5 Continuous assurance** | Sau handover. | Drift, threats mới, traffic mix, vendor changes, expired evidence và regression tests định kỳ. |

Không nhất thiết mọi release đi đủ các giai đoạn theo tên trên, nhưng với thay đổi high-risk phải có **điểm chặn quyết định** và bằng chứng trước khi mở rộng ảnh hưởng.

### 4.2. Observation windows và latency

Một security control có thể lỗi theo nhiều nhịp:

- Bypass authorization: có thể phát hiện ngay bằng negative test.
- Rate limiting: cần đủ traffic để đánh giá fairness và burst.
- Memory leak: có thể cần thời gian dài hoặc soak test.
- DB reconciliation: có thể cần full processing cycle.
- Backup: lỗi chỉ xuất hiện khi đến kỳ backup hoặc restore test.
- Token rotation: lỗi có thể xuất hiện khi credential cũ hết hiệu lực.
- Billing/export hoặc vendor batch: lỗi có thể xuất hiện hàng giờ/ngày sau release.
- Detection: cần chủ động tạo test signal phù hợp nếu threat hiếm gặp.

**Observation window phải gắn với failure mode.** Nếu chu kỳ nghiệp vụ dài hơn thời gian canary, cần thêm synthetic tests, delayed acceptance hoặc monitoring kéo dài với giới hạn minh bạch.

### 4.3. Tại sao cần baseline?

Baseline giúp phân biệt lỗi mới sau release với điều đã xảy ra trước đó. Có thể dùng:

- Số liệu của **cùng service/route/segment** trước release.
- Canary so với **control group** đang chạy version cũ khi hợp lệ.
- Khung giờ/ngày có traffic pattern tương đương.
- SLO, policy thresholds và lịch sử threat alerts.
- Test fixture giống nhau chạy trước/sau.
- Baseline có phiên bản và thời gian thu rõ ràng.

Không so sánh máy móc giờ cao điểm với giờ thấp điểm, hoặc request mix của khách hàng lớn với internal test traffic. Baseline sai có thể tạo **false regression** hoặc bỏ qua regression thật.

## 5. Metric contract: đo đúng mẫu số và phạm vi

### 5.1. Những trường phải ghi

Mỗi chỉ số dùng cho release gate cần có:

- **Metric ID, objective, owner, expected direction.**
- **Population/unit:** request, unique user, privileged action, event source, region, asset hoặc time interval.
- **Numerator/denominator**, query và source của cả hai.
- **Scope filters:** release version, route, tenant, region, cohort.
- **Window:** event time, ingestion time và thời điểm xử lý late events.
- **Threshold hoặc expected pattern:** do policy/service SLO/risk owner phê duyệt.
- **Alert/gate semantics:** cảnh báo tham khảo hay điều kiện hard stop.
- **Source health:** mất dữ liệu hoặc sample nhỏ xử lý như thế nào.
- **Baseline:** reference release, period, traffic segmentation.
- **Evidence retention và reviewer:** ai có thể tái hiện calculation.

### 5.2. Phép tính thường gặp

**Error rate theo request:**

\[
\text{Error rate} = \frac{\text{số request lỗi thuộc định nghĩa}}{\text{tổng request hợp lệ trong scope}}\times 100\%
\]

**Verified security-source coverage:**

\[
\text{Coverage} = \frac{\text{số source bắt buộc có event và health đã xác minh}}{\text{tổng source bắt buộc trong inventory}}\times 100\%
\]

**Detection delivery latency:**

\[
L_{\text{delivery}} = t_{\text{case delivered}}-t_{\text{source event}}
\]

Chỉ tính độ trễ khi clock sync và timestamp semantics đủ tin cậy; cần phân biệt thời điểm **event**, **collector ingest**, **rule alert** và **case delivered**.

**Số security regressions được xác minh:**

\[
N_{\text{regression}}=\text{số criterion trước release đạt nhưng sau release FAIL trong scope}
\]

Phải xem phiên bản criterion, test và population. Nếu trước release chưa test, không tự gắn nhãn “regression đã chứng minh” chỉ vì mới phát hiện lỗi sau release.

### 5.3. Ví dụ sai lầm khi gộp tỷ lệ

Canary có 20 lỗi trên 1.000 request (2%), baseline có 100 lỗi trên 20.000 request (0,5%). Chênh lệch đáng chú ý nhưng phải xem:

- Request mix, status code và expected failures.
- Các endpoints hoặc tenants có traffic khác nhau.
- Sample size và độ biến thiên; có thể cần thêm data.
- Release version gắn đúng mọi request?
- Monitoring/collection có bỏ request ở service lỗi không?
- Có security negative tests bị chặn đúng tạo response 4xx “lỗi” về mặt tính toán nhưng là hành vi mong muốn không?

Không nên đánh đồng tất cả 4xx với availability errors hoặc xác định cause của lỗi chỉ từ tương quan thời gian.

### 5.4. Cẩn trọng với low volume

Nếu canary chỉ có 10 request và không xảy ra lỗi, **0/10 = 0%** về số liệu quan sát, nhưng chưa đủ cơ sở để tuyên bố phiên bản không có lỗi. Cần ghi **sample size và observation confidence**, tăng synthetic transactions hoặc chờ đủ traffic theo risk.

Khi mẫu số bằng 0, kết quả metric là **N/A hoặc không đủ mẫu** theo contract, không mặc định 100% đạt.

## 6. Các tầng quan sát cần có sau phát hành

### 6.1. Release identity và deployment telemetry

Theo dõi:

- Commit, build/artifact digest, image digest hoặc config version.
- Pipeline/deployment IDs, signer/provenance khi áp dụng.
- Deploy events và thời điểm mỗi target nhận version.
- Pods/instances sẵn sàng, lỗi restart, stale replicas.
- Feature flags và config dynamic trên từng cohort.
- Các thay đổi ngoài luồng release như console hotfix/IAM update.

**Một deployment controller báo “desired replicas available” không chứng minh mọi request đang được xử lý với đúng auth policy.** Cần runtime version và test behavior.

### 6.2. Application/service health

- Request volume, errors, latency p95/p99 theo route và version.
- Saturation: CPU/memory, queue depth, connection pool, thread pool.
- Dependencies: DB, cache, IdP, DNS, KMS, vendor API.
- Business transactions: checkout completion, order creation, event processing, reconciliation.
- Background jobs, retry/backoff, dead-letter queues, timeout.
- Data integrity: missing/duplicate records, mismatch, idempotency.
- Availability của đường quản trị, không chỉ public endpoint.

Các tín hiệu này phát hiện regression nghiệp vụ, nhưng **không tự chứng minh confidentiality và authorization**.

### 6.3. IAM, authentication và authorization

- Tỷ lệ sign-in failures theo loại và expected reason.
- Privileged grants, role changes, policy edits và effective permissions.
- MFA enforcement, token validation failures, issuer/audience/scope discrepancies.
- API 401/403 trên endpoints nhạy cảm, tách deny đúng khỏi lỗi ngoài dự kiến.
- Break-glass usage và session bất thường.
- Secret/key access, token issuance, credential rotation.
- Negative test cho tenant isolation và object-level authorization.

**Một sự tăng 403 có thể là control chặn tốt hơn**, hoặc là regression từ chối người hợp lệ. Cần đối chiếu test fixtures, role/tenant và business behavior trước khi kết luận.

### 6.4. Data protection và integrity

- Truy cập dữ liệu nhạy cảm qua API và service-to-service.
- Payload/data schema gửi cho bên thứ ba, số trường và data classification.
- Data export volume, storage ACL và public exposure.
- Database migrations, reconciliation, constraints, duplicate writes.
- Encryption/KMS usage, failed decrypt, rotation, key permissions.
- Backup events và khả năng restore đối với thay đổi rủi ro cao.
- Data residency/retention/deletion controls khi phạm vi xử lý đổi.

Không dùng monitoring chứa raw PII hoặc secrets không cần thiết. **Data minimization áp dụng cả cho telemetry và evidence**.

### 6.5. Network và runtime/workload security

- Ingress/egress routes thực, network policies, firewall effective rules.
- Unexpected external destinations, DNS changes, proxy bypass.
- Kubernetes admission denials, privileged workloads, RBAC, runtime drift.
- Image digest mismatch, binary/process anomalies nếu có telemetry đáng tin.
- Node/host exposure và các control runtime không được disable khi rollout.
- Container restarts không chỉ phản ánh reliability mà có thể chỉ ra securityContext/config incompatibility.

### 6.6. Logging, detection và response readiness

- Mọi source bắt buộc có audit events theo inventory.
- Parser bảo toàn actor, target, outcome, resource, correlation ID.
- Log pipeline ingest lag, dropped/duplicated events, retention, access.
- Detection rules đã deploy đúng version và sử dụng field mới.
- Positive/negative detection regression tests.
- Alert routing, escalation, on-call acknowledgment theo policy.
- Source-health alert khi collector biến mất.

Đây là **tầng quan sát điều kiện để các tầng khác đáng tin**. Nếu một source critical mất log, không được suy “không thấy tấn công sau release” là an toàn.

### 6.7. Business continuity và dependency health

- KMS/IdP/DNS control plane availability.
- Restore/rollback path và backup catalog.
- Vendor latency, failure and retry behavior, dữ liệu ra/vào vendor.
- Hệ thống chống cascading failure như circuit breaker và backpressure.
- DR mode, degraded mode và hoạt động failover khi release đụng cấu hình khôi phục.

Phân biệt **service healthy trong điều kiện bình thường** với **có thể phục hồi sau failure mode trọng yếu**. Không đánh dấu mục tiêu DR đạt chỉ vì backup job chạy thành công.

## 7. Telemetry quality: phải chứng minh mình nhìn thấy hệ thống

### 7.1. Nguồn dữ liệu cần đối chiếu

| Nguồn | Giá trị | Giới hạn |
|---|---|---|
| **Deployment audit/CI/CD** | Artifact, approval, thời gian và targets triển khai. | Không cho biết tất cả data-plane paths hoạt động đúng. |
| **Application logs** | Event nghiệp vụ, request/actor/outcome. | Sampling, parser và logging gaps có thể bỏ sự kiện. |
| **Metrics** | Tỷ lệ, latency, saturation và health trends. | Aggregate có thể che tenant/version/attack-path. |
| **Distributed traces** | Dependency calls và request path. | Sampling có thể bỏ sự kiện hiếm, dữ liệu nhạy cảm. |
| **Cloud/K8s audit** | IAM, control plane, policy/resource changes. | Thiếu region/cluster/action types sẽ tạo blind spots. |
| **SIEM/detection/case** | Use case, alert, triage và response. | Không thấy event không có nghĩa không có hành vi. |
| **Business data/reconciliation** | Trạng thái giao dịch, tính nhất quán và tác động. | Có thể phát hiện muộn, cần giới hạn truy cập. |
| **Synthetic security probes** | Kiểm chứng có chủ đích cho path hiếm gặp. | Phạm vi fixture hẹp, không đại diện mọi loại tấn công. |

### 7.2. Telemetry coverage là một claim riêng

Một claim ví dụ:

> Những source audit Critical thuộc release cohort R, từ mốc T0 đến T1, đã được xác định từ inventory và được chứng minh tạo, truyền, lưu các event bắt buộc theo test contract.

Để hỗ trợ cần:

1. Inventory độc lập, đủ accounts, clusters, services, regions.
2. Source configuration và effective state.
3. Source-health heartbeat và test canary có kiểm soát.
4. Raw event → normalized event → alert/case nếu cần.
5. Monitoring của dropped records, lag, parser errors.
6. Sampling, filter, retention và backfill limitations.
7. Quy tắc xử lý UNKNOWN/INCONCLUSIVE.

Nếu canary chạy chỉ ở region A, **không thể lấy kết quả đó để xác minh B/C**.

### 7.3. Các kiểu telemetry failure

- Collector không chạy hoặc IAM quyền đọc bị thu hồi.
- API paginated nhưng job chỉ lấy trang đầu.
- Parser không hiểu schema field mới.
- Timestamp lệch làm correlation sai cửa sổ.
- Log được sampling khiến event đặc quyền biến mất.
- Ingestion backlog che regression ở phút đầu.
- Traces chỉ có parent span, bỏ auth service.
- Dashboard filter phiên bản mới mà không có tag version trên request.
- Source phát hiện không thuộc cùng production route mà chỉ ở test pipeline.
- Một alert được nhận trong SIEM nhưng không đến hệ thống case/on-call.

**Bằng chứng về trạng thái pipeline còn sống** không thay thế bằng chứng rằng **đúng loại event** đang được quan sát.

### 7.4. Telemetry confidence labels

Một release review có thể ghi:

| Nhãn | Ý nghĩa |
|---|---|
| **VERIFIED_COVERAGE** | Population nguồn đã đối chiếu, event/health và processing đúng criterion trong scope. |
| **PARTIAL_COVERAGE** | Một số source/field/event có evidence, phần khác thiếu. |
| **UNKNOWN_COVERAGE** | Không biết tình trạng do inventory/source health/permission lỗi. |
| **CONFIRMED_GAP** | Có bằng chứng một source/critical event không được thu hoặc xử lý. |
| **NOT_APPLICABLE** | Có căn cứ duyệt rằng yêu cầu không áp dụng cho đối tượng. |

Không chuyển UNKNOWN thành healthy chỉ vì dashboard không báo lỗi. Với release high-risk, một telemetry gap trọng yếu có thể là **hard stop** ngay cả khi các SLI vận hành đang tốt.

## 8. Security regression tests sau phát hành

### 8.1. Vì sao phải chạy test sau deploy?

Pre-release tests hữu ích nhưng có khác biệt giữa staging và production:

- Identity policies và trust relationships khác.
- Real routes qua gateway, service mesh và WAF khác.
- Network egress, DNS và cloud account khác.
- Feature flags chọn tenant/region khác.
- Real secrets/KMS access policy khác.
- Logs/detection rules ở production khác hoặc có suppression.
- Application rollout đang có nhiều versions đồng thời.

Phải chọn **authorized production-safe tests** hoặc canary fixtures tạo tín hiệu mà không làm hỏng dữ liệu thật.

### 8.2. Positive, negative và boundary tests

| Test type | Ví dụ | Hỏi điều gì? |
|---|---|---|
| **Positive behavior** | Người dùng có quyền đọc order của mình. | Luồng hợp lệ còn hoạt động? |
| **Negative authorization** | Người dùng A cố đọc order synthetic của tenant B. | Server chặn ở đúng boundary, không chỉ UI che? |
| **Token validation negative** | Token test sai audience, issuer, expiry hoặc signature. | API thật sự từ chối với reason phù hợp? |
| **Data minimization** | Synthetic payload chứa field không được phép gửi vendor. | Proxy loại field và không leak qua logging? |
| **Network deny** | Test workload thử kết nối endpoint ngoài allowlist. | Effective egress rule chặn? |
| **Privileged change detection** | Authorized simulation một thao tác quản trị đã chọn. | Có audit, rule, alert và case đúng context? |
| **Collector health** | Canary mất heartbeat trong sandbox phù hợp. | Monitoring nhận biết mất visibility? |
| **Failure/degraded mode** | Synthetic dependency timeout/circuit-breaker scenario. | Hệ thống fail-closed/fail-safe theo criterion? |
| **Recovery** | Thực hiện rollback rehearsal hoặc restore test được phép. | Có thể phục hồi service/data đúng cách? |

Không tự thực hiện hành vi có thể gây phá hoại production chỉ để “chứng minh” control. Các test cần phạm vi, quyền, dữ liệu và cleanup được phê duyệt.

### 8.3. Một test contract

~~~yaml
test_id: "REL-SEC-AUTH-003"
release_id: "ORD-2026-11-R3"
control_id: "CTRL-API-AUTHZ-004"
objective: "Ngăn truy cập order cross-tenant"
scope:
  environment: "production"
  region: "region-a"
  canary_cohort: "synthetic-tenant-qa"
  release_digest: "sha256:EXAMPLE_DIGEST"
preconditions:
  - "Synthetic identities và records đã được duyệt"
  - "Release marker và audit source healthy"
action:
  description: "Tenant A test principal requests Tenant B synthetic order"
expected:
  decision: "DENY"
  data_exposure: "NONE"
  audit_event: "PRESENT_WITH_ACTOR_TARGET"
  no_unexpected_side_effect: true
evidence:
  - "test-run-id-and-timestamp"
  - "request-response-redacted"
  - "effective-identity-claims"
  - "server-side-audit-correlation"
  - "backend-state-check"
result: "NOT_RUN"
~~~

Đây là **mẫu cấu trúc minh họa**, không phải test runner thực. Không dùng ID hoặc trường dữ liệu giả làm bằng chứng hệ thống thật đã đạt.

### 8.4. Test result có phạm vi, không phải sự thật tuyệt đối

Một test cross-tenant PASS cho endpoint X, release digest D và role R hỗ trợ kết luận **đường đã thử** từ chối truy cập. Nó không chứng minh mọi endpoint/role/session/tenant được bảo vệ. Nên đánh dấu coverage matrix cho:

- Endpoints/resource types.
- Roles/scopes và human/service principals.
- Tenant boundaries.
- API methods.
- Regions/clusters.
- Feature flags và old/new version.
- Time period và detection routing.

## 9. Detection monitoring sau release: từ event đến case

Post-release monitoring cần xác minh các security events vẫn đi qua **đường production thực sự**:

~~~mermaid
flowchart LR
    ACT["Authorized test / actual event"] --> SRC["Source audit"]
    SRC --> PIPE["Collector + parser"]
    PIPE --> STORE["Indexed/retained event"]
    STORE --> RULE["Detection rule"]
    RULE --> ALERT["Alert"]
    ALERT --> CASE["Case / on-call delivery"]
    CASE --> RESP["Triage / response"]
~~~

### 9.1. Những độ trễ khác nhau

- **Source delay:** từ hành vi đến lúc event được tạo.
- **Transport/ingest delay:** từ nguồn tới nơi nhận.
- **Rule detection delay:** từ event sẵn có tới alert.
- **Delivery delay:** từ alert tới case hoặc người trực.
- **Acknowledgment delay:** từ delivered tới người trực xác nhận.
- **Response delay:** từ case tới hành động containment hoặc triage.

Một SLO “alert trong 2 phút” cần nói rõ **từ mốc nào đến mốc nào**. Không thể tự chuyển từ “event-to-delivered” thành “ingest-to-alert” vì kết quả dễ đạt hơn.

### 9.2. Ví dụ timeline minh họa

Một security canary được ủy quyền:

| Mốc | Thời điểm UTC |
|---|---|
| Action thực hiện | 10:00:00 |
| Source event | 10:00:04 |
| Collector ingest | 10:00:18 |
| Rule alert | 10:00:51 |
| Case delivered | 10:01:36 |
| On-call acknowledged | 10:02:20 |

Nếu acceptance criterion là **event-to-delivered ≤ 120 giây**, kết quả **92 giây, PASS** cho fixture này. Nếu criterion là **event-to-acknowledged ≤ 120 giây**, kết quả **136 giây, FAIL**. Cần dùng đúng loại timestamp và clock synchronization.

Một fixture thành công không chứng minh **phần lớn kỹ thuật tấn công không được thử** sẽ tạo alert, hoặc hệ thống luôn đáp ứng SLA khi queue đầy.

### 9.3. Positive và negative detection tests

**Positive test:** một hành vi được chọn theo threat model phải tạo signal và alert/case đúng.

**Negative test:** một hành vi hợp lệ rất gần pattern tấn công không nên tạo cảnh báo sai theo detection contract, hoặc phải được phân loại/suppress đúng logic được phê duyệt.

Nếu chỉ chạy positive tests, một rule match tất cả event có thể được coi “đạt” dù gây hàng nghìn false positives. Nếu chỉ đo alert volume, giảm volume có thể là cải tiến noise hoặc **mất detection coverage**. Phải kết hợp rule behavior, source health và case outcomes.

## 10. Monitoring theo release version và cohort

### 10.1. Tránh dữ liệu gộp che vấn đề

Ví dụ một release mới được áp cho **5% request**; tổng error rate toàn hệ thống gần như không đổi. Nhưng riêng canary cohort, error rate tăng mạnh và các auth failures tập trung ở API endpoint mới.

Báo cáo nên phân đoạn ít nhất theo:

- Release version hoặc artifact digest.
- Region/cluster/availability zone.
- Route/API method, service và dependency.
- Tenant/business segment hoặc test cohort.
- Identity type và privilege class.
- Feature flag version, deployment batch.
- Error/security event category.
- Pre/post-change interval.

### 10.2. Không lạm dụng customer/PII trong telemetry

Để phân đoạn có thể dùng **tenant IDs dạng nội bộ, pseudonymous identifiers hoặc aggregate labels** phù hợp chính sách. Tránh dùng email, token, raw session, payment data hoặc thông tin nhạy cảm làm metric labels dễ rò rỉ và tăng cardinality không kiểm soát.

### 10.3. Canary representativeness

Kiểm tra:

- Canary có đi qua **đúng network/IdP/KMS/logging paths** không?
- Có gồm những API routes, transaction types, roles hoặc tenants quan trọng?
- Các miền lỗi khác nhau có được đánh giá độc lập?
- Traffic đủ để phát hiện loại lỗi cần quan sát?
- Synthetic tests có bao phủ hành vi hiếm khi traffic thực chưa xuất hiện?
- Có cross-version compatibility trong rolling rollout?
- Có đối tượng rất quan trọng bị cố tình loại khỏi canary không? Nếu có, cách kiểm chứng riêng là gì?

**Canary pass là một quyết định có điều kiện để mở rộng phạm vi**, không phải kết luận toàn hệ thống đã được chứng minh.

## 11. Release gates: ai quyết định mở rộng, dừng hoặc đảo thay đổi?

### 11.1. Bốn loại cổng đánh giá

| Gate | Mục tiêu | Ví dụ |
|---|---|---|
| **Technical deployment gate** | Artifact và targets đã triển khai đúng. | Digest match, workload ready, config version đúng. |
| **Service health gate** | Tính sẵn sàng và business transactions đạt điều kiện. | Error/latency/queue trong ngưỡng đã phê duyệt. |
| **Security control gate** | Các control trọng yếu và detection vẫn có evidence. | Auth negative test, audit source health, data-flow deny. |
| **Assurance/evidence gate** | Coverage và chất lượng chứng cứ đủ cho quyết định. | Đúng inventory, source đầy đủ, không có unreviewed high-risk gaps. |

**Một gate thất bại** không được tự bù bằng các gate khác đang xanh nếu đó là điều kiện bắt buộc. Ví dụ 100% uptime không bù được việc token sai audience được chấp nhận.

### 11.2. Quyết định và trạng thái

| Quyết định | Khi nào phù hợp | Hành động tiếp theo |
|---|---|---|
| **PROCEED** | Các criteria bắt buộc đạt trong cohort và evidence đủ, risk còn trong phạm vi đã duyệt. | Mở batch theo rollout plan. |
| **HOLD** | Chưa đủ mẫu, có cảnh báo cần điều tra hoặc telemetry không chắc chắn. | Dừng mở rộng, thu thêm evidence. |
| **ROLLBACK** | Có failure/vi phạm nghiêm trọng và đường quay về an toàn được xác minh. | Kích hoạt runbook, kiểm tra dữ liệu và security sau rollback. |
| **FORWARD_FIX** | Rollback gây rủi ro lớn hơn hoặc không khả thi, có phương án sửa được phê duyệt. | Sửa với blast radius kiểm soát và giám sát tăng cường. |
| **CONTAIN / INCIDENT** | Có dấu hiệu compromise/data leak/control failure cần ứng phó khẩn cấp. | Kích hoạt IR, preserve evidence, cô lập và phối hợp legal khi cần. |
| **LIMITED_ACCEPTANCE** | Một số điều kiện không trọng yếu có findings và quyết định đúng thẩm quyền. | Công bố limitations, owner, deadline và monitoring. |
| **INCONCLUSIVE** | Thiếu evidence/population/source health để ra kết luận. | Không coi là PASS; sửa nguồn kiểm chứng và retest. |

**Risk acceptance hoặc approved exception không biến một control không đạt thành PASS**. Đối với nghĩa vụ pháp luật/hợp đồng bắt buộc, không tự bỏ điều kiện chỉ bằng chữ ký của quản lý nội bộ.

### 11.3. Stop conditions

Một kế hoạch high-risk nên xác định trước:

- Confirmed authn/authz bypass hoặc unauthorized data access.
- Confirmed leak secret/PII hoặc data flow ngoài phạm vi phê duyệt.
- Mất audit/detection source Critical hoặc alert routing không hoạt động.
- Data integrity invariant bị vi phạm.
- Lỗi vận hành vượt ngưỡng service đã phê duyệt.
- Không còn đường rollback/forward-fix an toàn.
- Release artifact/target thực lệch approved scope.
- Không đủ telemetry trong một phần trọng yếu của rollout.
- Threat/incident mới làm thay đổi risk assessment hoặc khiến exception mất hiệu lực.

Một stop condition có thể kích hoạt **ngay lập tức** không cần chờ tính đủ trung bình cửa sổ nếu đã có bằng chứng critical failure.

### 11.4. Quy trình ra quyết định cần phân vai

- **Release manager/change authority:** điều phối rollout và quyết định thay đổi theo quy trình.
- **Service owner/SRE:** bảo vệ availability, SLO và phục hồi.
- **Security/control owner:** xác định security criterion, điều tra regression và evidence.
- **SOC/incident commander:** ứng phó khi có alert hoặc dấu hiệu compromise.
- **Risk owner:** quyết định residual risk trong giới hạn thẩm quyền.
- **Legal/privacy/compliance:** điều kiện thông báo, dữ liệu và nghĩa vụ khi liên quan.
- **Independent assurance reviewer:** đánh giá sự tương ứng giữa claim, evidence và verdict.

Không nên để người vừa tạo thay đổi vừa đơn phương ghi “security accepted” khi policy đòi review độc lập.

## 12. Rollback, forward-fix và khả năng phục hồi

### 12.1. Rollback cần cân nhắc cả state

Revert ứng dụng không tự phục hồi:

- Database schema hoặc dữ liệu đã migrate không tương thích version cũ.
- KMS key đã rotate/revoke khiến bản cũ không giải mã được.
- JWT issuer/token clients đã đổi.
- Secrets bị thu hồi hoặc external vendor đã nhận dữ liệu.
- Retention đã xóa dữ liệu.
- CDN/cache vẫn phục vụ version cũ hoặc mới.
- Kubernetes controller thực hiện thay đổi ngoài Git.
- Các replica và clients còn active sessions từ release lỗi.

Phải có **rollback compatibility assessment** trước release high-risk.

### 12.2. Decision flow khi gate fail

~~~mermaid
flowchart TD
    FAIL["Security/service gate FAIL"] --> PAUSE["Stop rollout and preserve evidence"]
    PAUSE --> IMPACT["Classify impact, scope, active incident?"]
    IMPACT -->|Incident| IR["Activate IR/containment"]
    IMPACT -->|No incident or contained| ROL{"Rollback safe & effective?"}
    ROL -->|Yes| BACK["Apply approved rollback"]
    ROL -->|No| FIX["Forward-fix / degrade / isolate"]
    BACK --> VERIFY["Verify version, controls, data, telemetry"]
    FIX --> VERIFY
    IR --> VERIFY
    VERIFY --> REPORT["Finding + decision + retest + risk review"]
~~~

Cần xem **rủi ro của rollback**. Nếu release cũ chứa vulnerability Critical đã bị khai thác, quay lại version cũ có thể không an toàn. Có thể cần isolation, giảm chức năng hoặc forward-fix theo thẩm quyền.

### 12.3. Post-rollback monitoring

Sau rollback phải kiểm tra:

1. Artifact/config thực đã quay đúng version trên mọi target.
2. Những thay đổi dữ liệu/keys/session còn tương thích.
3. API auth, network, secret và IAM không bị bỏ qua.
4. Audit/log/detection vẫn có coverage.
5. Dữ liệu đang xử lý và queue/retry không tạo duplicate/loss.
6. Kỳ mất visibility hoặc outage được ghi vào incident/finding.
7. Có owner xử lý root cause và retest bản sửa.
8. Người chịu trách nhiệm ra quyết định đã được thông báo và lưu dấu.

**Rollback thành công của controller không tự chứng minh sự cố đã được giải quyết.**

## 13. Case study: Order API phiên bản 2.7 trên ba region

### 13.1. Bối cảnh

Doanh nghiệp vận hành Order API hỗ trợ checkout, tạo đơn và gửi purchase events tới SaaS analytics. Phiên bản **v2.7** thay đổi:

- Cơ chế kiểm tra JWT audience.
- Object-level authorization đối với order queries.
- Log schema ở API gateway và collector.
- Rate limit cho endpoint tạo đơn.
- Event payload gửi nhà cung cấp analytics.
- DB index và một phần read-model xử lý asynchronous.

Tổ chức muốn rollout từng region và đánh giá security/availability theo risk. Phạm vi ví dụ:

| Region | Release trạng thái ban đầu | Chức năng đặc biệt | Rủi ro |
|---|---|---|---|
| **A** | Canary 10% traffic. | Gateway JWT và logging mới. | Token bypass, parser mất actor, alert delay. |
| **B** | Chưa triển khai. | Batch reconciliation. | Data inconsistency, batch lag. |
| **C** | Chưa triển khai. | Analytics egress. | Data minimization và vendor dependency. |

Những con số/tên chỉ minh họa. Chúng không tương ứng với một dịch vụ thực.

### 13.2. Top-level assurance claims

- **G0:** Release v2.7 đáp ứng các security objectives đã phê duyệt trong phạm vi cohort, region và cửa sổ quan sát đã được đánh giá.
- **G1:** Release identity, config và deployment targets đúng approved artifact.
- **G2:** Authentication/authorization không cho phép truy cập ngoài policy.
- **G3:** Purchase events chỉ chứa dữ liệu được cho phép và không làm mất integrity.
- **G4:** Source audit Critical và detection/response path hoạt động.
- **G5:** Service reliability và recovery/fallback thỏa acceptance criteria.
- **G6:** Evidence đầy đủ và findings/uncertainty được trình bày trung thực.

### 13.3. Test & monitoring matrix

| Test/metric | Đối tượng | Expected theo kế hoạch giả định | Bằng chứng |
|---|---|---|---|
| **REL-01 Version** | API gateway, API pods, config service. | Digest/config đúng cohort, không nhầm giữa vùng. | Deployment events, effective version labels. |
| **REL-02 JWT deny** | Token test sai audience/issuer. | Từ chối, không side effect, có audit. | Signed test fixture metadata, HTTP result, server audit. |
| **REL-03 Tenant isolation** | User A gọi order synthetic của tenant B. | Deny theo policy, không leak data. | Request/response redacted, backend check. |
| **REL-04 Allowed access** | User hợp lệ và order thuộc tenant. | Thành công; không bị regression auth. | Synthetic business transaction, trace. |
| **REL-05 Data egress** | Purchase event tới SaaS. | Chỉ fields allowlist; đúng tenant/region. | Event schema, proxy config, sanitized payload sample. |
| **REL-06 Data integrity** | DB writes, read model và event queue. | Không loss/duplicate trái contract, reconcile. | Transaction IDs, counts, data validation. |
| **REL-07 Log source** | Gateway/API/K8s audit các regions. | Critical fields có source/ingest và health. | Raw event, parser/version, heartbeat. |
| **REL-08 Detection** | Privileged policy edit fixture. | Alert/case đến đúng người trong mục tiêu. | Event-to-case timeline, rule version. |
| **REL-09 Service SLIs** | Error, latency, queue theo cohort/route. | Trong ngưỡng đã duyệt, đủ mẫu. | Metrics query/version, traffic counts. |
| **REL-10 Recovery** | Failover/rollback scenario được duyệt. | Khôi phục đúng behavior, data không hỏng. | Runbook test, deployed version, integrity evidence. |
| **REL-11 Source health** | Mất collector synthetic / ingest lag. | Nhận biết gap và escalation đúng rule. | Health alerts, case log. |
| **REL-12 Third-party** | SaaS analytics timeout và permission scopes. | Không mở dữ liệu ngoài allowlist; checkout degrade an toàn. | Outbound tests, token scope, queue behavior. |

Không phải mọi test đều cần thao tác trực tiếp trên production. Có thể kết hợp test ở environment tương đương, canary synthetic và runtime evidence; **phải ghi giới hạn của phương pháp**.

### 13.4. Baseline và gates

Giả sử release plan định nghĩa các ngưỡng **minh họa**:

- Không có confirmed cross-tenant data access hay JWT audience bypass.
- Không có mất logging/detection Critical ở cohort được đánh giá.
- Error rate của checkout trong cửa sổ so sánh không vượt ngưỡng đã thống nhất.
- Alert delivery của use case privileged change trong vòng **120 giây** từ event.
- Không ghi raw tokens/PII ngoài data-flow policy.
- Canary phải đủ traffic/test coverage; nếu thiếu phải giữ HOLD.
- Chỉ triển khai region tiếp theo sau khi region hiện tại đạt các gate bắt buộc.

Ngưỡng phải được phê duyệt theo risk appetite, service objectives và khả năng quan sát. Không lấy **120 giây** hoặc **10% canary** làm tiêu chuẩn chung.

### 13.5. Tình huống thực tế giả định trong canary

Sau khi region A nhận v2.7:

- Digest và version đúng.
- Checkout latency không thay đổi đáng kể trong sample.
- Negative test JWT sai audience **bị từ chối** và audit đầy đủ.
- Object-level authorization test **PASS**.
- Gateway access logs xuất hiện, nhưng parser mới bỏ trường **tenant_id** cho một loại event.
- Detection use case nhắm dữ liệu **cross-tenant access** không hoạt động khi thiếu tenant_id.
- Một số event bị trễ do collector backlog; không có bằng chứng về khoảng mất hoàn toàn nhưng completeness chưa được xác minh.
- Synthetic purchase event tới SaaS có thêm trường internal_debug_metadata không thuộc allowlist.

**Kết luận không phải “release healthy”.** Có ít nhất một vi phạm data minimization và một regression về detection context; phần log completeness còn **INCONCLUSIVE**.

### 13.6. Quyết định theo từng claim

| Claim | Kết quả | Lý do | Hành động |
|---|---|---|---|
| **G1 Version/scope** | Supported cho region A canary. | Digest và effective state khớp cohort. | Duy trì evidence, không suy cho B/C. |
| **G2 Authn/authz** | Supported trong các tests đã chạy. | Negative JWT/object tests đạt; coverage của các role khác còn giới hạn. | Duy trì tests khi mở rộng. |
| **G3 Data minimization** | **FAIL.** | Có trường ngoài allowlist trong outbound event. | Hold, chặn field/egress, điều tra dữ liệu đã gửi. |
| **G4 Detection** | **FAIL/PARTIAL.** | Parser mất tenant_id; source completeness còn chưa đủ evidence. | Hold, sửa parser, kiểm tra raw-to-alert. |
| **G5 Reliability** | Partial/inconclusive cho toàn release. | Sample canary tốt nhưng chưa đánh giá background cycle và B/C. | Tiếp tục quan sát sau khi sửa. |
| **G6 Evidence quality** | Inconclusive cho một phần. | Chưa reconcile backlog và event counts. | Sửa telemetry/đối chiếu nguồn. |

**Không mở rollout sang B/C** vì những hard security gates trong ví dụ chưa đạt, dù CI/CD và latency đang xanh.

### 13.7. Timeline quyết định

~~~text
09:00 UTC  Deploy canary v2.7 to region A, 10% traffic
09:04 UTC  Artifact/target check PASS
09:08 UTC  JWT and object authz synthetic tests PASS
09:12 UTC  Parser validation: tenant_id missing on event type X
09:14 UTC  Detection test for X fails to create expected case
09:16 UTC  Outbound event review finds internal_debug_metadata
09:17 UTC  Release gate: HOLD further rollout
09:19 UTC  Security + service owners assess impact and evidence
09:23 UTC  Data egress temporarily restricted / fixed as approved
09:28 UTC  Finding opened for parser, data-flow and telemetry gap
09:35 UTC  Decision: no expansion; prepare controlled forward-fix
...        Repeat tests and review after actual correction
~~~

Đây là lịch giả định để học cơ chế quyết định. Khi có dấu hiệu rò dữ liệu thật, phải xem xét **incident response và nghĩa vụ thông báo** theo phạm vi được legal/compliance xác nhận, không tự coi chỉ là lỗi phát hành bình thường.

### 13.8. Retest sau forward-fix

Yêu cầu tối thiểu:

1. Artifact/config mới có digest/version và approval tương ứng.
2. Không còn internal_debug_metadata trong outbound fixture; schema allowlist được áp trên actual path.
3. Nếu đã có dữ liệu ra ngoài, có điều tra phạm vi, chủ sở hữu và xử lý theo quy trình.
4. Parser giữ tenant_id/actor/target đúng trên raw và normalized events.
5. Detection positive/negative tests tạo kết quả đúng tới case/on-call.
6. Reconcile backlog và source health; gap lịch sử vẫn được ghi.
7. Chạy lại authn/authz tests phòng regression do fix.
8. Kiểm tra health/traffic canary đủ theo plan, sau đó mới xét mở rộng region.
9. Ghi findings, approvals, release gate decision và evidence references.

**Retest PASS sau fix không xóa sự thật rằng phiên bản trước từng fail hoặc có thời gian telemetry không đủ.**

## 14. Post-release monitoring và incident response

### 14.1. Khi nào nên tạo incident?

Không phải mọi alert sau release đều là incident. Tuy nhiên, nên có **triggers và phân loại theo chính sách** cho:

- Confirmed hoặc suspected unauthorized access/data exposure.
- Confidential information hoặc credential xuất hiện ở log/data flow.
- Integrity bị thay đổi ngoài mong muốn.
- Mất detection/audit có ảnh hưởng đáng kể hoặc liên quan hành vi nghi vấn.
- Outage/degradation vượt tiêu chí và ảnh hưởng dịch vụ Critical.
- Dấu hiệu malicious activity, exploitation hoặc secret compromise.
- Sự cố vendor ảnh hưởng tới dữ liệu, nghĩa vụ hoặc hệ thống phụ thuộc.

Nếu trigger đạt, chuyển sang **incident command, preservation, containment, communication và recovery**; tiếp tục giữ liên kết tới release/change ID.

### 14.2. Phân biệt causal hypothesis và bằng chứng nguyên nhân

Có sự cố xuất hiện **sau** release không đủ chứng minh release **gây ra** sự cố. Cần:

1. Đối chiếu thời gian và release exposure.
2. So sánh impacted/unimpacted cohorts khi có thể.
3. Kiểm tra diff/code/config/dependencies.
4. Tìm reproduction hoặc counterexample an toàn.
5. Kiểm tra dữ liệu trước release và các thay đổi song song.
6. Ghi nguyên nhân **đã xác minh**, **khả năng** hoặc **chưa xác định**.

Không dùng nhãn “release-induced” để thay thế điều tra. Nhưng khi có security risk hiện hữu, có thể **contain/hold trước khi root cause xác minh xong** theo thẩm quyền.

### 14.3. Bảo toàn evidence khi rollback

Trước khi xóa pods hoặc thay cấu hình nếu không gây nguy hiểm, cần lưu dữ liệu phù hợp:

- Release digest, config before/after, deployment timeline.
- Raw security events, alerts, case IDs và source-health gaps.
- Effective permissions, network routes và data-flow state.
- Trace/correlation IDs có redaction đúng.
- Errors, queue backlog, DB consistency markers.
- Quyết định on-call, thời điểm và người thực hiện.
- Thao tác containment/rollback và kết quả validation.

Tính toàn vẹn có thể dùng cơ chế audit trail, versioning và hashes khi cần; hash không tự chứng minh **nguồn dữ liệu đầy đủ và chính xác**.

## 15. Findings và remediation từ post-release evidence

### 15.1. Mỗi phát hiện cần phân biệt

| Kết quả | Ý nghĩa | Hành động |
|---|---|---|
| **PASS trong scope** | Các criteria đã test và telemetry phù hợp trong cửa sổ xác định. | Lưu evidence, tiếp tục monitoring. |
| **FAIL** | Có evidence đáng tin control/acceptance criterion không đáp ứng. | Hold/contain hoặc rollback, finding, fix và retest. |
| **PARTIAL** | Một phần cohort/path đạt, phần khác chưa đạt hoặc chưa test. | Chỉ kết luận phần đã chứng minh, không mở rộng tùy tiện. |
| **INCONCLUSIVE** | Evidence hoặc telemetry/source inventory không đủ. | Sửa quan sát, lấy thêm evidence, đánh giá lại. |
| **NOT_ASSESSED** | Điều kiện áp dụng nhưng chưa kiểm tra. | Giữ kế hoạch test/owner và rủi ro. |
| **NOT_APPLICABLE** | Có căn cứ đã duyệt rằng criterion không áp dụng. | Lưu rationale, trigger review. |
| **APPROVED_EXCEPTION** | Có gap và quyết định time-bound theo thẩm quyền. | Báo riêng residual risk; không đổi FAIL thành PASS. |

### 15.2. Finding mẫu

~~~yaml
finding_id: "REL-FIND-2026-017"
release_id: "ORD-2026-11-R3"
criterion_id: "REL-07"
control_id: "CTRL-LOG-ACTOR-CONTEXT"
scope:
  environment: "production"
  region: "region-a"
  cohort: "canary"
  artifact_digest: "sha256:EXAMPLE_DIGEST"
condition:
  observed: "Parser new version drops tenant_id for event type X"
  first_seen_utc: "2026-11-28T09:12:00Z"
  evidence_scope: "Synthetic fixture and raw-to-normalized comparison"
risk:
  scenario: "Cross-tenant security alert may lack tenant context"
  severity: "high-under-example-policy"
root_cause:
  status: "under-investigation"
evidence_refs:
  - "EV-RAW-109"
  - "EV-PARSER-208"
  - "EV-DET-309"
owner: "logging-platform"
remediation:
  action: "Correct field mapping, investigate ingest gap and retest detection"
  due_at: "2026-11-30T00:00:00Z"
retest:
  criteria:
    - "Raw and normalized fields match required schema"
    - "Positive and negative detection tests pass"
    - "Event reaches correct alert/case route"
  result: "pending"
release_gate:
  decision: "HOLD"
  decision_ref: "DEC-2026-044"
~~~

Ví dụ trên không khẳng định có sự cố rò dữ liệu thật. **Finding condition** mô tả điều quan sát được, **risk** mô tả hậu quả khả dĩ, **root cause** có thể đang điều tra. Điều này tránh viết kết luận mạnh hơn bằng chứng.

### 15.3. Đóng finding thế nào?

Không đóng khi chỉ có “PR merged” hoặc “alert đã im lặng”. Chỉ đóng sau:

- Effective state đã thay đúng trên population.
- Test acceptance có expected/actual và evidence.
- Source-health đủ để tin kết quả.
- Không còn bypass/regrression liên quan trong scope.
- Impact tồn đọng hoặc dữ liệu bị sai có phương án xử lý.
- Reviewer xác nhận và có lịch monitoring tiếp theo.

Một fix có thể khiến lỗi cũ hết nhưng tạo lỗi khác; vì vậy cần **regression test theo các đường liên quan**, không chỉ test lại một fixture đã fail.

## 16. Evidence package cho từng release

### 16.1. Cấu trúc minh họa

~~~text
security-assurance/releases/ORD-2026-11-R3/
  release-context/
    approved-change-request.md
    scope-versions-and-artifacts.md
    threat-model-and-control-map.md
    authority-and-risk-decisions.md
  pre-release/
    security-test-summary.md
    baseline-metrics-and-population.csv
    telemetry-readiness.md
    rollback-and-forward-fix-plan.md
  rollout/
    deployment-and-feature-flag-timeline.csv
    version-per-region-and-cohort.csv
    canary-gate-decisions.md
  monitoring/
    metric-contracts.md
    service-sli-results.csv
    security-test-results.json
    source-health-and-completeness.csv
    event-to-alert-case-timeline.csv
    backend-reconciliation-results.csv
    third-party-dependency-results.md
  findings/
    failed-criteria-and-gaps.csv
    containment-and-remediation.md
    retest-evidence.json
  assurance/
    claim-argument-evidence.md
    evidence-index-and-provenance.csv
    limitations-and-reviewer-verdict.md
    handover-and-next-triggers.md
~~~

Đây là **cấu trúc tham khảo**. Hệ thống thật có thể lưu evidence trong CI/CD, GRC, SIEM và ticketing; không nên tạo bản sao dữ liệu nhạy cảm không cần thiết.

### 16.2. Metadata tối thiểu

Mỗi evidence record nên có:

- Evidence ID, release/change ID, control/criterion/test ID.
- Artifact digest/config version và runtime target.
- Region, cluster, cohort, tenant/classification khi phù hợp.
- Collection window, timestamp semantics và timezone.
- Expected/actual, sample size, numerator/denominator.
- Source, query, tool/parser/rule version, transformations.
- Provenance, integrity controls và limitation.
- Reviewer, decision, linked finding/exception và retest.
- Retention và quyền xem evidence theo mức nhạy cảm.

### 16.3. Evidence quality review

| Thuộc tính | Câu hỏi |
|---|---|
| **Relevance** | Evidence hỗ trợ đúng claim/criterion nào? |
| **Completeness** | Đúng population, tất cả regions/sources và cả cửa sổ quan sát? |
| **Freshness** | Thu sau đúng release/config và còn phù hợp thời điểm ra quyết định? |
| **Reliability** | Nguồn, query, parser, timestamps và integrity có đáng tin? |
| **Corroboration** | Có test hoặc nguồn độc lập xác minh behavior quan trọng? |
| **Reproducibility** | Reviewer có thể truy lại raw/source và tính toán cùng kết quả? |
| **Safety/privacy** | Có lọc secrets/PII và quản lý quyền truy cập evidence? |

Một dashboard có rất nhiều dữ liệu nhưng không ghi version/scope có thể **không đủ** để hỗ trợ kết luận riêng cho release.

## 17. Assurance argument cho kết luận sau release

### 17.1. Claim–Argument–Evidence (CAE)

~~~mermaid
flowchart TD
    G0["G0: Release đáp ứng security objectives trong scope"]
    S0["Strategy: identity, correctness, controls, telemetry, recovery"]
    G1["G1: Approved artifact đang chạy đúng targets"]
    G2["G2: Security behaviors đáp ứng criteria"]
    G3["G3: Data/service integrity & availability được giữ"]
    G4["G4: Detection/logging còn coverage đủ"]
    G5["G5: Failure handling và release decision hợp lệ"]
    G6["G6: Evidence đủ và không che gaps trọng yếu"]
    E1["Digest + deployment + effective state"]
    E2["Auth, IAM, egress negative tests"]
    E3["Service SLI + data reconciliation"]
    E4["Source health + event-to-case tests"]
    E5["Rollback readiness + decision trail"]
    E6["Inventory + provenance + reviewer findings"]
    G0 --> S0
    S0 --> G1
    S0 --> G2
    S0 --> G3
    S0 --> G4
    S0 --> G5
    S0 --> G6
    G1 --> E1
    G2 --> E2
    G3 --> E3
    G4 --> E4
    G5 --> E5
    G6 --> E6
~~~

**Warrant:** Nếu release đúng artifact/scope, kiểm thử những security behaviors trọng yếu đạt, dịch vụ và dữ liệu còn trong điều kiện chấp nhận, monitoring/detection đủ coverage, có khả năng xử lý thất bại và evidence đáng tin, thì có cơ sở đưa ra **kết luận giới hạn theo phạm vi và thời kỳ**.

Không được suy rộng thành “an toàn trước mọi tấn công” hoặc “không còn residual risk”. Lập luận phải nhắc các phần chưa thử, assumptions và defeaters.

### 17.2. Defeaters cần đánh giá

- Traffic từ các routes mới không có release tag.
- Một region chưa triển khai nhưng bị tính chung với cohort mới.
- Security probe đi qua test proxy khác đường production.
- Parser bỏ trường actor/tenant nên detection không có context.
- Source telemetry bị sampling hoặc bỏ event khi queue đầy.
- Feature flag thay sau thời điểm test.
- Vendor thay data processing scope ngoài thời điểm release.
- KMS key rotation làm rollback artifact không giải mã được.
- Dashboard tính error rate bằng mẫu số sai.
- Issue được đóng nhưng negative test chưa chạy lại.
- Thời gian monitoring ngắn hơn failure mode quan trọng.
- Một exception/risk decision đã hết hạn nhưng vẫn tính hợp lệ.

Một defeater trọng yếu chưa được giải quyết có thể làm top claim chuyển sang **partial/inconclusive**, ngay cả khi phần lớn tests đã PASS.

## 18. Mẫu release monitoring plan

~~~yaml
monitoring_plan:
  id: "RMP-ORD-2026-11-R3"
  release_id: "ORD-2026-11-R3"
  business_service: "order-platform"
  risk_tier: "high"
  scope:
    environment: "production"
    regions: ["region-a", "region-b", "region-c"]
    release_identity:
      application_version: "2.7"
      gateway_policy_version: "g7"
      artifact_digest: "sha256:EXAMPLE_DIGEST"
  stages:
    - id: "canary-a"
      exposure: "10% of region-a eligible traffic"
      required_checks: ["REL-01", "REL-02", "REL-03", "REL-05", "REL-07", "REL-08"]
    - id: "expand-a"
      condition: "All mandatory canary gates supported by evidence"
    - id: "region-b-c"
      condition: "Independent per-region verification"
    - id: "stabilization"
      condition: "Time and workload coverage defined by risk review"
  baseline:
    reference_release: "2.6"
    segmentation: ["route", "region", "tenant-class", "identity-type"]
    source_refs: ["EV-BASE-01", "EV-BASE-02"]
  mandatory_security_gates:
    - "No confirmed unauthorized cross-tenant read"
    - "No unapproved data fields delivered to analytics"
    - "Critical audit source coverage verified"
    - "Prioritized detection canaries reach expected case route"
  telemetry_quality:
    inventory_source: "asset-and-log-source-register"
    unknown_status: "INCONCLUSIVE"
    failure_policy: "HOLD for critical blind spots"
  rollback:
    artifact_ref: "approved-previous-release"
    runbook_ref: "RB-ORD-001"
    data_compatibility: "requires explicit review"
  accountability:
    release_manager: "release-lead"
    service_owner: "order-sre"
    security_reviewer: "appsec-assurance"
    detection_owner: "security-monitoring"
    risk_owner: "order-business-owner"
  decisions:
    current_state: "PREDEPLOY"
    evidence_index: "EVI-ORD-2026-11-R3"
~~~

Mẫu là minh họa; trường conditions cần được thay bằng **ngưỡng, thẩm quyền, mốc thời gian và acceptance criteria có hiệu lực** trước khi dùng thật.

### 18.1. Mẫu trạng thái phê duyệt

Một release có thể dùng trạng thái:

- **PREDEPLOY**: đã lập kế hoạch nhưng chưa triển khai.
- **DEPLOYING**: đang áp thay đổi.
- **CANARY_MONITORING**: chỉ cohort giới hạn được quan sát.
- **HOLD**: không mở rộng do warning, gap hoặc chờ evidence.
- **EXPANDING**: đang tăng exposure từng bước.
- **STABILIZING**: đã triển khai đủ scope, đang quan sát delayed effects.
- **ACCEPTED_WITH_SCOPE**: evidence đủ cho kết luận trong scope.
- **ROLLED_BACK**: đã quay về trạng thái được xác minh; vẫn cần investigation.
- **FORWARD_FIXED**: đã sửa trong release mới; phải retest.
- **INCIDENT_ESCALATED**: chuyển xử lý theo IR.
- **REVIEW_REQUIRED**: phát sinh thay đổi ngoài assumptions/monitoring plan.

Đừng tự động đánh dấu **ACCEPTED_WITH_SCOPE** khi clock chạy hết một cửa sổ cố định; criteria và evidence vẫn phải đạt.

## 19. KPI và báo cáo post-release monitoring

### 19.1. Metric families

| Metric | Đo gì? | Điều kiện đọc đúng |
|---|---|---|
| **Release health gate pass rate** | Tỷ lệ gate có đủ evidence và đạt điều kiện. | Gate trọng yếu FAIL không bị “bù điểm” bởi gate khác. |
| **Security regression count** | Số control criteria có regression đã xác minh sau release. | Báo severity và impact, không gộp việc mới phát hiện issue cũ. |
| **Monitoring/source coverage** | Nguồn Critical đã verified / toàn bộ nguồn áp dụng. | Phải có authoritative inventory và unknown riêng. |
| **Detection scenario test coverage** | Threat scenarios ưu tiên có test đủ / tất cả scenarios trong scope. | Một fixture không đại diện toàn technique. |
| **Event-to-case latency** | Độ trễ sự kiện đến case. | Cùng mốc timestamp, đủ clock quality và source coverage. |
| **Release-induced incidents** | Incident có causal link hợp lý tới release. | Không quy nguyên nhân chỉ theo thời điểm. |
| **Change rollback/forward-fix rate** | Release phải khắc phục hoặc quay lại. | Không tự coi rollback là thất bại đo lường; nhiều khi là phản ứng đúng. |
| **Mean time to identify regression** | Thời gian từ regression onset được xác minh tới detection. | Onset có thể ước lượng; ghi uncertainty. |
| **Evidence sufficiency** | Các gate được đánh giá với evidence thích hợp / tổng gate đến hạn. | INCONCLUSIVE không tính PASS. |
| **Critical unknowns** | Số rủi ro/nguồn quan trọng chưa thể kết luận. | Không xóa khỏi scope để làm dashboard xanh. |
| **Remediation retest closure** | Findings đã được xác minh đóng / findings đã báo sửa xong. | Ticket Done không đồng nghĩa verified. |
| **Handover readiness** | On-call, runbook, release scope, dashboards, findings và owner đủ. | Giao việc miệng không thay record. |

### 19.2. Ví dụ executive report

> **Order API v2.7 — release monitoring status: HOLD.** Canary region A đã triển khai đúng artifact và hai kiểm thử authorization ưu tiên đạt. Tuy nhiên, một dữ liệu ngoài allowlist xuất hiện trong event gửi SaaS; parser mới thiếu tenant_id, khiến một detection use case không tạo case đúng điều kiện. Mức đầy đủ dữ liệu collector trong một cửa sổ còn chưa được xác minh. Không mở triển khai sang regions B/C. Đã giao owners xử lý data-flow và parser, kiểm tra tác động, thực hiện retest; quyết định triển khai lại phụ thuộc security gates có bằng chứng. Kết luận không xác nhận các phần ngoài canary.

Báo cáo nên kèm:

- Business impact và quyết định cần cấp có thẩm quyền.
- Version/scope/exposure tại mốc báo cáo.
- Gaps theo severity và owner.
- Confidence/unknowns và source-health.
- Kế hoạch containment, rollback/forward-fix và retest.
- Đường dẫn evidence, approval và lịch review tiếp theo.

### 19.3. Chỉ số không nên được dùng làm mục tiêu duy nhất

Một dashboard chỉ đo “release success rate” khuyến khích:

- Bỏ security tests để rollout nhanh.
- Đóng gate khi telemetry thiếu.
- Tránh báo rollback vì sợ bị tính thất bại.
- Loại cohort rủi ro cao khỏi phạm vi.
- Gộp dữ liệu canary với stable version để che regression.
- Chỉ nhìn error rate và bỏ qua data leak hoặc auth bypass.
- Tạo nhiều alerts thấp giá trị thay vì test detection thực sự.

Đo lường tốt phải giúp **ra quyết định đúng**, không làm cho mọi bản phát hành đều có màu xanh.

## 20. Third-party, compliance và điều kiện ngoài hệ thống

### 20.1. Shared responsibility sau release

Một bản phát hành có thể đổi integration với SaaS, CDN, IdP, cloud hoặc payment provider. Monitoring phải xác định:

- Customer-side tokens, scopes, egress, payload fields và audit.
- Vendor-side data processing, availability, API behavior và reporting contract.
- Bên xử lý phụ trợ và phạm vi thay đổi của vendor nếu liên quan.
- Dữ liệu có đi tới endpoint/region mới hay không.
- Callback/webhook trust, signatures, replay protection.
- Vendor incident/status communication và khả năng offboarding/disable integration.

Một báo cáo SOC 2 hoặc chứng nhận của vendor **không tự chứng minh release integration bên khách hàng đã cấu hình đúng**.

### 20.2. Nghĩa vụ pháp lý và hợp đồng

Khi một release làm thay đổi mục đích xử lý dữ liệu, data location, privacy, retention hoặc điều kiện thông báo sự cố, cần có **legal/privacy/compliance applicability review** theo đúng hợp đồng và khu vực liên quan.

Không được tự suy rằng **risk owner chấp nhận rủi ro** thì một yêu cầu pháp lý/hợp đồng không còn áp dụng. Với dấu hiệu data exposure, cần ghi nhận sự kiện, điều tra và escalations trước khi quyết định hành động thông báo theo nghĩa vụ thực tế.

### 20.3. Đừng giữ raw dữ liệu nhạy cảm để “làm evidence”

Evidence chỉ cần đủ để kiểm chứng. Ưu tiên:

- Synthetic data hoặc thông tin đã redacted.
- ID nội bộ, request correlation và metadata không chứa secret.
- Tách raw evidence nhạy cảm vào kho kiểm soát quyền.
- Giới hạn mục đích, retention và quyền chia sẻ.
- Giữ link tới raw trong phạm vi được phép thay vì copy vào mọi ticket.
- Bảo vệ chain-of-custody khi phục vụ điều tra.

## 21. Continuous assurance sau giai đoạn stabilization

Release monitoring kết thúc giai đoạn tăng cường, nhưng các claim phải được theo dõi khi bối cảnh thay đổi:

- Feature flag mở thêm cohorts.
- Tenant/user/route mới nhận traffic.
- Cloud/Kubernetes autoscaling tạo assets mới.
- Key/cert/token rotation.
- Detection rule hoặc parser đổi.
- Vendor sửa API, callback hoặc subprocessor.
- Attack scenario mới và vulnerability được công bố.
- Data pipeline thêm trường dữ liệu mới.
- Backup/DR exercise hoặc change management cho release tiếp theo.
- Một nguồn health biến mất, finding hoặc exception hết hạn.

### 21.1. Change-triggered reassessment

Khi trigger xuất hiện:

1. Xác định claim/control/asset nào bị ảnh hưởng.
2. Gắn release/config version mới hoặc change ID.
3. Kiểm tra evidence trước còn hiệu lực không.
4. Chạy lại test/monitoring phù hợp, ưu tiên risk scenario quan trọng.
5. Sửa risk/threat model và exceptions nếu cần.
6. Báo tình trạng mới, findings và owner.
7. Giữ lịch sử kết luận cũ; không ghi đè để xóa failure.

### 21.2. Handover checklist

Sau khi một release được chấp nhận, chuyển cho operations:

- Runtime inventory và artifact/config version.
- Monitors, source-health checks, alert destinations và owner.
- Security tests phải duy trì hoặc định kỳ chạy lại.
- Các limitations/unknowns chưa xử lý.
- Open findings/approved exceptions với deadline và expiry.
- Rollback/forward-fix runbooks đã đánh giá và khả năng recovery.
- Các metrics/report queries và quyền truy cập evidence.
- Escalation/incident path, on-call/backup owners.
- Triggers khiến release assurance conclusion mất hiệu lực.

**Handover không phải chuyển hết trách nhiệm rủi ro sang SRE/SOC**. Risk, control và service owners tiếp tục chịu trách nhiệm theo governance.

## 22. Các lỗi thường gặp

1. **Xem deployment success là security acceptance.** Runtime và control behavior chưa được kiểm chứng.
2. **Chỉ đo uptime, latency, error rate.** Không phát hiện data exposure, auth bypass, mất detection.
3. **Không gắn metric với release version.** Lỗi cohort mới bị che trong tổng traffic.
4. **Lấy dashboard làm inventory.** Nguồn chưa có telemetry không xuất hiện, mẫu số bị thiếu.
5. **Coi không có alert là không có tấn công.** Collector/parser/rule/case delivery có thể lỗi.
6. **Chỉ nhìn một region.** Vùng khác có config, secrets, IAM hoặc routes khác.
7. **Chỉ chạy positive functional tests.** Authorization bypass, data over-sharing và policy fail-open không được thử.
8. **Canary quá ít traffic nhưng kết luận chắc chắn.** Không đủ mẫu và chưa gặp business cycle.
9. **So sánh không tương đương.** Time-of-day/tenant/route mix khác gây kết luận sai.
10. **Dùng tỷ lệ trung bình che outage ở nhóm Critical.** Cần phân đoạn và hard security gates.
11. **Không định nghĩa rollback trước deploy.** Khi lỗi mới phát hiện mới biết old version không đọc được data.
12. **Revert commit và tuyên bố sự cố đóng.** DB/KMS/telemetry và sessions vẫn sai.
13. **Chuyển UNKNOWN thành PASS.** Missing evidence là gap, không phải control effectiveness.
14. **Bỏ các alert false positives khỏi report.** Rule có thể vô dụng dù có positive test.
15. **Gộp incident và release regression làm một.** Cần causal analysis và IR riêng khi trigger.
16. **Không lưu decision timeline.** Auditor không biết ai mở rộng rollout dựa vào dữ liệu nào.
17. **Risk acceptance xóa finding.** Ngoại lệ chỉ quản trị residual risk trong thẩm quyền.
18. **Không retest sau fix.** Code merge không chứng minh effective-state đã đạt.
19. **Telemetry chứa secrets/PII.** Monitoring có thể tự tạo lỗ hổng bảo mật và privacy.
20. **Handover không rõ owner.** Monitoring hết người trực sau khi release manager đóng CR.
21. **Không monitor độ trễ của dữ liệu bảo mật.** Alert có thể tới quá muộn để có tác dụng.
22. **Không tính những trạng thái ngoài bình thường.** DR/degraded mode có thể thiếu IAM/logging.
23. **Không ghi limitation.** Kết luận khái quát hóa sang các path chưa thử.
24. **Thay ngưỡng khi có lỗi để đạt gate.** Mọi thay đổi criteria cần rationale, approval và version.

## 23. Bài tập tình huống: giám sát một release API ngân hàng giả định

Một ngân hàng **giả định** triển khai Payment API phiên bản R12 trên hai cloud regions A/B. Release thay JWT token validation, authorization với tài khoản thanh toán, rotation key và cấu hình security event routing. Canary region A chỉ có 500 giao dịch synthetic/limited real traffic; region B chưa triển khai.

Sau release:

- Service uptime 100% và p95 latency vẫn trong giới hạn.
- Một token test sai audience được chấp nhận ở một endpoint mới, nhưng bị từ chối ở endpoint cũ.
- Auth audit logs hiển thị ở A, nhưng sự kiện của API mới thiếu field resource_owner.
- Một detection rule không tạo alert khi fixture sử dụng endpoint mới.
- Key rotation khiến một background reconciliation job không giải mã được bản ghi được tạo trước release.
- Chỉ có 10 giao dịch đi qua background job trong canary window.
- Feature flag mới cho phép một tenant không thuộc danh sách rollout.

### 23.1. Nhiệm vụ

1. Xác định những security objectives bị ảnh hưởng và viết threat/risk scenarios tương ứng.
2. Vì sao uptime 100% không đủ để mở rộng triển khai?
3. Đặt release scope, mốc version và population cho monitoring.
4. Thiết kế ít nhất 8 test/monitoring controls, gồm positive và negative.
5. Phân loại các vấn đề thành FAIL, INCONCLUSIVE hoặc NOT_ASSESSED theo từng criterion.
6. Xác định những hard stop conditions và thứ tự hành động containment/rollback/forward-fix.
7. Viết metric contract cho JWT audience denial test và detection end-to-end.
8. Nêu vì sao region B không thể được tính là verified post-release.
9. Đề xuất cách kiểm tra background job và key rotation khi sample size quá thấp.
10. Đề xuất evidence cần preserve trước khi thay phiên bản hoặc sửa token validator.
11. Viết finding cho endpoint mới chấp nhận token sai audience và ghi rõ impact đã biết/chưa biết.
12. Đề xuất một assurance conclusion có giới hạn, không che thiếu telemetry.
13. Xác định người chịu trách nhiệm release decision, security risk, IR, operations và legal review.
14. Sau fix, thiết kế retest matrix và phương pháp xác nhận source health.
15. Đề xuất cách handover những findings và unknowns nếu release không được rollback hoàn toàn.

### 23.2. Gợi ý kết luận

- **JWT audience bypass:** nếu policy yêu cầu từ chối, đây là **confirmed security criterion FAIL** và hard stop trong ví dụ.
- **Missing resource_owner:** có thể là **FAIL cho logging schema requirement** và làm yếu detection; không coi alert absence là không có hành vi.
- **Detection rule failure:** test cho thấy một use case ưu tiên không hoạt động như kỳ vọng; cần sửa và retest.
- **Background decrypt error:** ảnh hưởng dữ liệu và recoverability; đòi xác minh key lifecycle, không tự revert key khi chưa hiểu dữ liệu cũ.
- **Tenant exposure:** cần đối chiếu approved rollout scope và data impact; nếu không được phê duyệt, là security/operational deviation.
- **Region B:** NOT_DEPLOYED, không thể là post-release PASS.
- **Top claim “R12 an toàn trên cả hai region”:** **không được hỗ trợ**; cần HOLD/containment, xử lý các failures và thu đủ evidence trước khi triển khai tiếp.

## 24. Checklist trước, trong và sau giám sát release

### 24.1. Trước phát hành

- [ ] Có release/change ID, artifact digest, config version và approved scope.
- [ ] Rủi ro và security requirements của thay đổi được xác định từ threat model.
- [ ] Các controls Critical được mapping với monitoring/test cases.
- [ ] Authoritative asset, identity, service, tenant và source inventories đã đối chiếu.
- [ ] Có baseline tương đương, observation windows và sample/traffic assumptions.
- [ ] Metric contract định nghĩa numerator/denominator, version, source, threshold và gate.
- [ ] Có positive, negative, boundary và failure tests phù hợp.
- [ ] Source-health, detection và case-delivery telemetry đã sẵn sàng.
- [ ] Canary/progressive rollout có hard stop và phân quyền quyết định.
- [ ] Rollback/forward-fix plan xét stateful data, keys, tokens và vendor dependencies.
- [ ] Legal/privacy/compliance review được thực hiện khi data processing hoặc nghĩa vụ đổi.
- [ ] Runbooks, on-call, release owners và incident escalation sẵn sàng.

### 24.2. Trong rollout và stabilization

- [ ] Version và effective state được gắn theo từng region/tenant/cohort.
- [ ] Deployment targets và traffic exposure khớp kế hoạch.
- [ ] Health SLIs được phân đoạn theo version/route, không chỉ nhìn tổng.
- [ ] Test xác thực/ủy quyền và data flow sau release có bằng chứng.
- [ ] Audit/log/detection pipeline có source coverage, field correctness và case delivery.
- [ ] Missing sources, lag, sampling và errors được ghi riêng.
- [ ] Có đủ traffic/test coverage cho những failure modes cần đánh giá.
- [ ] Decision PROCEED/HOLD/ROLLBACK/FORWARD_FIX được ghi thời điểm, owner và evidence.
- [ ] Phát hiện nghi incident được chuyển IR thay vì chờ end-of-window.
- [ ] Mọi out-of-band config/feature flag change đều có trace và risk review.
- [ ] Rollback/forward-fix được xác minh cả security, data integrity và observability.
- [ ] Findings/unknowns không bị chuyển thành PASS do dashboard thiếu tín hiệu.

### 24.3. Khi bàn giao và kiểm toán

- [ ] Assurance conclusion mô tả đúng scope, kỳ, release/version và những giới hạn.
- [ ] Có traceability từ risk/requirement tới controls, tests, evidence và decision.
- [ ] Critical gaps và exceptions có owner, deadline và thẩm quyền.
- [ ] Findings chỉ đóng khi remediation đã được retest đạt.
- [ ] Evidence có provenance, timestamp, population, tool/parser version và quyền truy cập.
- [ ] Đã phân biệt observed service health với security effectiveness.
- [ ] Handover có on-call, dashboards, runbooks, open issues và triggers cần reassess.
- [ ] Monitoring lâu dài được duy trì khi traffic/feature flags mở rộng.
- [ ] Bài học được cập nhật vào threat model, release gates và regression tests.
- [ ] Không tuyên bố loại bỏ hoàn toàn rủi ro chỉ vì một release đã qua stabilization.

## 25. Câu hỏi tự đánh giá

1. Post-release monitoring khác pre-release testing và continuous monitoring ở những điểm nào?
2. Vì sao deployment success và service uptime không đủ để khẳng định security assurance đạt?
3. Nêu các trường cần thiết để gắn security telemetry với đúng release version và cohort.
4. Khi canary chỉ có ít traffic, làm sao kiểm tra security behaviors hiếm gặp?
5. Vì sao error rate phải có numerator, denominator và request mix rõ ràng?
6. Điều gì làm baseline trước/sau release không còn so sánh hợp lệ?
7. Vì sao log source healthy không đồng nghĩa detection rule vẫn tạo alert/case?
8. Event-to-alert và event-to-delivered khác nhau thế nào khi kiểm tra SLO?
9. Hãy viết hai negative tests sau khi đổi JWT issuer/audience.
10. Khi dữ liệu chỉ có ở một region, có thể kết luận các region khác đạt không? Vì sao?
11. Vì sao một release có 0 alerts vẫn có thể thiếu assurance?
12. Khi nào cần HOLD, khi nào cần rollback và khi nào cần forward-fix?
13. Tại sao Git revert không đảm bảo hoàn tác DB migration, rotation key hoặc xóa dữ liệu?
14. Một approved risk exception có biến control đang FAIL thành PASS không?
15. Chỉ ra các điểm phân biệt incident cần ứng phó và regression cần retest.
16. Nếu source telemetry mất đúng lúc canary, cần ghi verdict nào và hành động gì?
17. Vì sao việc dữ liệu gửi vendor có thêm một field không mong muốn là vấn đề security/privacy dù error rate không tăng?
18. Thiết kế một assurance case gồm G0 và ít nhất năm subclaims cho một release nhiều region.
19. Những evidence fields nào giúp auditor kiểm tra lại một quyết định mở rộng rollout?
20. Hãy soạn dashboard và báo cáo release 1 trang gồm scope, gates, reliability, security, telemetry quality, findings, owner và quyết định.
21. Một test PASS tại thời điểm 09:00 có còn đủ giá trị nếu feature flag đổi lúc 10:00 không? Khi nào phải revalidate?
22. Thế nào là một handover đủ trách nhiệm giữa release manager, SRE, SOC, control owner và risk owner?

**Điểm cốt lõi:** **Post-release monitoring biến việc “đã phát hành” thành một quyết định assurance dựa trên trạng thái thực và bằng chứng có thể kiểm toán.** Một release chỉ nên được mở rộng và chấp thuận trong phạm vi khi **artifact/targets đúng, security behaviors đã kiểm thử, reliability/data integrity đạt điều kiện, telemetry/detection đủ bao phủ, và có khả năng dừng, khôi phục hoặc sửa an toàn**. Những nơi thiếu chứng cứ phải được ghi **INCONCLUSIVE**, những control đã fail vẫn là **FAIL** dù có ngoại lệ quản trị, và mọi finding cần owner, remediation, retest cùng monitoring liên tục sau handover.
