# Rà soát theo sự kiện trong Continuous Assurance: Đánh giá lại bảo mật đúng lúc hệ thống thay đổi

Ngày đầu tháng, tổ chức kiểm tra quyền IAM của toàn bộ cloud production và kết luận chính sách đặc quyền đạt yêu cầu. Đến ngày thứ mười, một thay đổi vận hành cấp cho service account quyền ghi trên nhiều tài nguyên hơn mức cần thiết. Cuộc rà soát tiếp theo được lên lịch vào cuối quý, tức khoảng lệch có thể tồn tại nhiều tuần mà báo cáo vẫn hiển thị “PASS” từ lần đánh giá trước.

**Rà soát theo sự kiện (event-driven review)** là cơ chế **kích hoạt đánh giá lại một hoặc nhiều security claims, controls, rủi ro và bằng chứng khi xảy ra sự kiện có khả năng làm thay đổi kết luận bảo đảm trước đó**. Sự kiện có thể là deployment, thay đổi đặc quyền, phát hiện lỗ hổng, mất luồng log, đổi mức độ nhạy cảm dữ liệu, hết hạn ngoại lệ, sự cố bảo mật hoặc thay đổi nhà cung cấp. Rà soát có thể được tự động hỗ trợ nhưng không mặc định mọi sự kiện cần một cuộc audit thủ công toàn diện.

Trong chương **Continuous assurance** của module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là **đánh giá liên tục, có bằng chứng, rằng hệ thống đáp ứng mục tiêu bảo mật** từ phân tích rủi ro, yêu cầu, security controls đến kiểm thử, audit, finding và khắc phục. Rà soát theo sự kiện bổ sung cho đánh giá định kỳ bằng cách hỏi: **“Có điều gì vừa thay đổi khiến bằng chứng hoặc kết luận assurance hiện hành không còn đủ tin cậy?”**

Sau bài học, người học có thể xác định các sự kiện kích hoạt, thiết kế event contract và luồng xử lý, liên kết trigger với claim/control, ưu tiên đánh giá theo rủi ro, thu bằng chứng tại thời điểm phù hợp, ra kết luận PASS/FAIL/INCONCLUSIVE, quản lý ngoại lệ và remediation, đo hiệu quả quy trình và duy trì audit trail có thể tái lập.

## 1. Rà soát theo sự kiện là gì và không phải là gì?

Một **sự kiện (event)** là dữ kiện cho biết một trạng thái hoặc hành động đã xảy ra: IAM role được chỉnh sửa, container image mới được triển khai, certificate hết hạn, data store chuyển region hoặc một control telemetry ngừng gửi log. Không phải sự kiện nào cũng là lỗi bảo mật.

Một **trigger** là điều kiện đã được chính sách assurance xác định khiến sự kiện phải dẫn tới hành động đánh giá, thông báo, kiểm thử lại hoặc tạm dừng một quyết định. Một **review** là quá trình đánh giá evidence, áp dụng tiêu chí và lập kết luận có owner, scope, thời gian và hành động tiếp theo.

Ví dụ:

- **Event:** Service account được thêm quyền ghi object storage lúc 14:05.
- **Trigger:** Tài khoản production nhạy cảm tăng quyền nằm ngoài allowlist đã được duyệt.
- **Review:** Đối chiếu thay đổi với change request, effective permissions, data sensitivity và đường truy cập; kiểm tra least privilege.
- **Verdict:** FAIL nếu chứng minh quyền vượt policy, INCONCLUSIVE nếu chưa đọc được runtime; không tự coi cả hai là “incident”.
- **Action:** Thu hồi/sửa quyền theo thẩm quyền, điều tra, ghi finding và retest; nếu đang bị khai thác thì kích hoạt incident response.

**Event-driven review không đồng nghĩa alerting, incident response, vulnerability scanning hoặc tự động sửa mọi thứ.** Đây là lớp **đánh giá bảo đảm** có thể dùng kết quả của các năng lực ấy, nhưng phải liên kết bằng chứng tới tiêu chí bảo mật và kết luận được giới hạn đúng mức.

### 1.1. Lợi ích chính

- Rút ngắn khoảng thời gian dùng một kết luận đã lỗi thời sau khi risk exposure thay đổi.
- Đánh giá đúng phần hệ thống bị tác động thay vì chạy lại toàn bộ audit không cần thiết.
- Đưa security assurance vào dòng công việc phát triển và vận hành thay vì chỉ đợi kỳ kiểm toán.
- Phát hiện control drift, ngoại lệ hết hạn hoặc evidence không còn đại diện.
- Tạo dấu vết quyết định: sự kiện nào làm kết luận thay đổi, ai kiểm tra, rủi ro được xử lý thế nào.

Lợi ích này chỉ có khi **trigger coverage đủ tin cậy, review được thực hiện và evidence kiểm chứng được**. Một hệ thống gửi hàng nghìn thông báo nhưng không có owner xử lý không phải chương trình continuous assurance hiệu quả.

## 2. Định kỳ, giám sát liên tục và rà soát theo sự kiện khác nhau như thế nào?

| Cách tiếp cận | Khi nào hoạt động? | Ví dụ | Giới hạn quan trọng |
|---|---|---|---|
| **Periodic assessment** | Theo lịch tuần/tháng/quý hoặc yêu cầu audit. | Access review hàng quý, pentest hằng năm. | Có thể bỏ lỡ khoảng lệch xuất hiện giữa hai lần. |
| **Continuous monitoring** | Thu tín hiệu/đánh giá tự động gần liên tục theo khả năng hệ thống. | Cloud posture scan, SIEM, EDR, kiểm tra certificate. | Telemetry không tự tạo kết luận assurance đầy đủ. |
| **Event-driven review** | Khi trigger đáng quan tâm xuất hiện và được xác thực. | Quyền IAM tăng, thay đổi encryption key, log pipeline lỗi. | Phụ thuộc độ phủ, độ tin cậy trigger và quy tắc ưu tiên. |
| **Change/release assurance** | Theo các mốc trước, trong và sau triển khai. | Pre-change gate, post-release verification. | Một số drift xảy ra ngoài pipeline hoặc sau cửa sổ release. |
| **Incident assessment** | Khi sự cố hoặc nghi vấn theo playbook được kích hoạt. | Tài khoản bị chiếm, data breach nghi ngờ. | Không nên chờ điều tra sự cố mới rà soát một control drift thông thường. |

Một chương trình trưởng thành **kết hợp** chúng: baseline định kỳ để phát hiện khoảng trống giữa các tín hiệu; telemetry để biết sự kiện; event-driven review để đánh giá claim bị ảnh hưởng; incident response cho trường hợp cần containment; remediation để xử lý nguyên nhân gốc.

### 2.1. Không phải “thời gian thực tuyệt đối”

Đường thu thập event có độ trễ: cloud audit API, webhook, polling, message queue, SIEM ingestion và người review. “Continuous” không có nghĩa zero-latency hoặc 100% sự kiện được biết ngay lập tức. Báo cáo phải nói rõ **detection coverage, event-to-review latency và những nguồn không quan sát được**.

## 3. Chọn những assurance claims cần được đánh giá lại

Để chọn trigger hiệu quả, trước tiên xác định **mệnh đề bảo đảm (claim)** và điều kiện làm claim hợp lệ.

| Claim minh họa | Bằng chứng đang dùng | Những thay đổi có thể làm kết luận cũ mất hiệu lực |
|---|---|---|
| **Privileged access chỉ cấp theo least privilege.** | IAM effective policy, role mapping, access tests. | Thêm principal, grant wildcard, thay federation hoặc exception. |
| **Audit logs bao phủ production.** | Source inventory, synthetic events, SIEM ingest test. | Thêm account/region, collector mất quyền, thay schema hoặc route. |
| **Dữ liệu nhạy cảm được mã hóa phù hợp.** | Data inventory, KMS/key mapping, encryption checks. | Tạo dataset mới, thay storage class, rotation lỗi, đổi vendor/region. |
| **Release đã được kiểm chứng.** | Artifact digest, test runs, approval record. | Deploy revision khác, config drift, mở feature flag, rollout tới tenant mới. |
| **Critical findings được kiểm soát.** | Scan/retest, exposure analysis, mitigation evidence. | CVE mới, exploit in-the-wild, mitigation lỗi, asset mới. |
| **Khôi phục đáp ứng mục tiêu.** | Restore/failover rehearsal, backup integrity, RTO/RPO review. | Thay replication, schema, KMS key, network hoặc dependency. |
| **Third-party assurance phù hợp scope.** | Hợp đồng, SOC report, data flow, tenant configuration. | Thay subprocessor, dịch vụ, dữ liệu xử lý hoặc trách nhiệm chia sẻ. |

**Không chỉ map event tới một dashboard.** Map event tới **claim ID, control ID, security objective, scope và evidence cần kiểm chứng lại**. Nếu không, người review khó giải thích vì sao một sự kiện là quan trọng.

### 3.1. Assumption và warrant cũng có thể hết hiệu lực

Một claim “MFA bảo vệ toàn bộ đường quản trị” có thể dựa trên giả định mọi đường đều qua IdP. Khi nhà cung cấp bổ sung cổng support trực tiếp, ngay cả khi policy MFA không đổi, **giả định bao phủ đã bị thách thức**. Trigger không chỉ dựa vào thay đổi của control, mà cả **thay đổi kiến trúc và những tiền đề hỗ trợ phép suy luận**.

## 4. Danh mục sự kiện kích hoạt (trigger taxonomy)

Tổ chức cần **trigger catalog** có owner, risk tier, source, điều kiện và phép review tương ứng. Bảng dưới đây là gợi ý, không phải danh sách bắt buộc chung.

| Nhóm sự kiện | Ví dụ trigger | Control/claim cần xem | Hành động khởi đầu |
|---|---|---|---|
| **IAM / privilege** | Gán role admin, tạo break-glass account, thay policy MFA. | Least privilege, MFA, approval và auditability. | Reconcile principal + test effective access. |
| **Asset / service inventory** | Thêm cloud account, cluster, host hoặc database production. | Coverage của logging, patching, backups, hardening. | Xác nhận owner, data class, baseline enrollment. |
| **Network / exposure** | Mở ingress public, thay route, tắt segmentation. | Attack surface, trust boundary, allowed/denied paths. | Review network diff và reachability tests. |
| **Application release** | Deploy image/config khác digest đã duyệt. | Approval record, secure release gates, runtime controls. | Verify provenance, scope và post-release tests. |
| **Data / privacy** | Dataset nhạy cảm mới, region mới, retention rule thay đổi. | Encryption, access, data flow, obligations. | Reclassify, privacy/legal assessment khi cần. |
| **Keys / secrets** | Key rotation, revoke, secret leak hoặc cert gần hết hạn. | Confidentiality, recovery và machine authentication. | Test key access, revoke path, restore dependencies. |
| **Vulnerability / threat intel** | CVE mới liên quan asset hoặc khai thác thực tế. | Patch SLA, exposure, compensating controls. | Reassess exploit path và remediation priority. |
| **Security telemetry** | Collector offline, parser drop event, nguồn audit bị tắt. | Detection coverage, evidence completeness. | Synthetic check, source-to-SIEM trace, gap analysis. |
| **Incident / suspicious activity** | Credential misuse, anomalous privileged session. | IAM, containment, detection, evidence assumptions. | IR triage và assurance reassessment liên kết. |
| **Exceptions** | Hết hạn, scope tăng, bù trừ lỗi hoặc renewal request. | Exception governance và control gốc. | Review authorization/risk/mitigation. |
| **Remediation** | Fix deployed, retest failed, finding reopened. | Control effectiveness và closure. | Independent retest, update finding verdict. |
| **Supplier** | Vendor đổi data location, mất support, thêm subprocessor. | Shared responsibility, vendor controls, hợp đồng. | Review applicability và tenant evidence. |
| **Resilience / DR** | Replica đổi, backup failure, failover architecture mới. | Recoverability, integrity và security controls sau DR. | Restore/consistency impact review. |
| **Policy / requirement** | Standard mới có hiệu lực, risk appetite hoặc luật áp dụng đổi. | Requirement applicability và mapping tới controls. | Impact assessment theo population và deadlines. |
| **Evidence pipeline** | API credentials hết hạn, missing event, schema đổi. | Tin cậy của toàn bộ assurance reporting. | Mark evidence gap, repair collector, rescan. |

### 4.1. Chọn trigger có mục tiêu

Không cần tạo review thủ công cho mọi cấu hình mạng nhỏ. Thiết kế điều kiện cụ thể: “mọi firewall rule public mở cổng quản trị vào production” có thể cần review ngay; “thêm mô tả cho một rule không đổi behavior” có thể chỉ cần lưu event. Cần nêu **lý do rủi ro**, không chỉ tên sự kiện.

### 4.2. Trigger từ “không có sự kiện”

Sự vắng mặt của telemetry cũng là tín hiệu nếu hệ thống **đáng lẽ phải sinh heartbeat/event**. Ví dụ không nhận audit events từ một account suốt cửa sổ kiểm tra không chứng minh chắc chắn logging bị tắt; nó có thể do lỗi mạng, quyền collector hoặc không phát sinh sự kiện. Review phải **tạo synthetic event an toàn, kiểm tra nguồn và đường ingest** để phân biệt control failure với evidence gap.

## 5. Thiết kế Event contract đủ tin cậy

**Event contract** mô tả cấu trúc, nguồn, semantics và điều kiện xử lý của sự kiện. Không có contract, một chuỗi log tự do có thể gây false positives, duplicate hoặc bỏ lọt các thay đổi quan trọng.

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| **event_id** | Định danh ổn định từ nguồn hoặc do collector suy ra có phương pháp. | cloudtrail-event-id / audit-run-123. |
| **event_type và schema_version** | Loại sự kiện, ý nghĩa và phiên bản cách mã hóa. | iam.role.granted / v2. |
| **source_system / tenant** | Nguồn và miền tin cậy sinh event. | cloud account A, IdP tenant T. |
| **occurred_at_utc** | Khi thay đổi/sự kiện thực sự xảy ra theo nguồn. | 2026-11-28T02:14:00Z. |
| **observed_at_utc** | Khi pipeline bảo đảm quan sát được event. | 2026-11-28T02:14:07Z. |
| **actor / principal** | Ai/identity nào thực hiện thay đổi khi được phép thu. | deployment-role-7. |
| **resource_id và scope** | Asset, region, environment, service, data classification. | prod-account-a/role-payment. |
| **before / after hoặc diff reference** | Trạng thái bị thay đổi và địa chỉ bản gốc. | effective policy snapshot IDs. |
| **correlation_id / change_id** | Liên kết yêu cầu thay đổi, release, incident và finding. | CHG-1234. |
| **signature/integrity metadata** | Cơ chế kiểm tra xác thực/tính toàn vẹn theo source trust. | signed event hoặc object version. |
| **confidence / data-quality flags** | Mức đáng tin và lỗi parser/inventory. | source-time-unverified. |
| **sensitivity / retention** | Quyền xem và thời gian lưu. | confidential, restricted-vault. |

Một trường `severity: high` do chính nguồn event gửi có thể là **gợi ý**, không tự thay thế risk assessment của tổ chức. Một event “role changed” cũng không chứng minh effective permissions sau thay đổi nếu policy inheritance hoặc caching chưa được xác minh.

### 5.1. Chuẩn hóa không làm mất bản gốc

Pipeline có thể chuyển nhiều loại event sang canonical schema, nhưng phải giữ liên kết tới **raw event** hoặc bản snapshot có thể kiểm tra, mapping version, errors và fields bị bỏ. Nếu parser lỗi làm bỏ field `resource_id`, sự kiện chưa đủ điều kiện ra quyết định tự động về scope.

## 6. Nguồn tín hiệu và độ tin cậy của pipeline

Một chương trình event-driven review thường có nhiều nguồn:

- Cloud audit/management events và cloud configuration inventory.
- IdP/IAM logs, privileged access management, directory changes.
- Kubernetes audit, admission controller, container runtime, orchestration events.
- Git/CI/CD, artifact registry, deployment controller, IaC drift detector.
- Vulnerability scanners, SBOM/dependency alerts, threat intelligence.
- EDR/NDR/SIEM/SOAR, ticketing, incident management.
- Data catalog, KMS/secrets manager, database audit và backup control plane.
- GRC, exception register, risk register, policy/standard versioning.
- Vendor advisories, contract and data-processing change notices.

### 6.1. Những failure modes phải thiết kế trước

| Failure mode | Tác động tới assurance | Cách ứng phó |
|---|---|---|
| **Event loss** | Không biết thay đổi đã diễn ra, claim cũ tiếp tục sai. | Source reconciliation, heartbeat, polling bổ sung, health metrics. |
| **Duplicate delivery** | Một thay đổi sinh nhiều review/finding, quá tải người trực. | Idempotent processing theo event ID/fingerprint. |
| **Out-of-order events** | Đánh giá state cũ thành state mới; kết luận ngược. | Dùng version/sequence và query effective state, không suy chỉ từ thứ tự nhận. |
| **Clock skew** | Sai mốc rủi ro, hạn SLO và thứ tự hành động. | UTC/offset, clock health, event/ingest times tách biệt. |
| **API pagination/truncation** | Bỏ tài sản/permission, kết luận coverage quá rộng. | Check page tokens, permissions, counts và source reconciliation. |
| **Schema changes** | Parser bỏ field hoặc hiểu sai action. | Versioned contract, schema tests, quarantine unknown events. |
| **Backpressure/outage** | Review đến muộn, backlog cao, mất cơ hội containment. | Queue monitoring, retry, dead-letter queue, degraded-mode procedure. |
| **Race / TOCTOU** | State đổi giữa collect và review/act. | Snapshot/version pinning, revalidation trước decision/action. |
| **Spoofed/forged event** | Trigger giả gây sửa quyền hoặc thông báo sai. | Source authentication, least privilege, anomaly checking. |
| **Shared dependency failure** | Nguồn và assurance engine cùng lỗi, trông “không có vấn đề”. | Health checks độc lập, đường quan sát bổ sung khi quan trọng. |

**Không thể lấy “0 trigger” làm bằng chứng hệ thống không thay đổi** nếu chưa chứng minh sensor/collector đang hoạt động và coverage đủ. Review theo sự kiện cần một lớp tự giám sát chính pipeline của nó.

## 7. Phân loại và ưu tiên review dựa theo rủi ro

Không phải mọi event có cùng mức khẩn. Việc ưu tiên phải xem cả **tác động bảo mật** và **độ tin cậy của dữ liệu**, tránh tình trạng một nguồn false-positive gây tê liệt quy trình.

### 7.1. Các yếu tố ưu tiên

1. **Criticality của tài sản/dịch vụ:** thanh toán, identity plane, dữ liệu khách hàng, hệ thống khôi phục.
2. **Tác động lên control:** phòng ngừa thất bại, mất audit, dữ liệu lộ, mất khả năng phục hồi.
3. **Exposure và khả năng bị khai thác:** public path, attacker reachability, quyền đặc quyền.
4. **Threat context:** có active exploitation, incident/attack path đã biết không?
5. **Độ rộng:** bao nhiêu account, region, tenant, identity hoặc dữ liệu bị ảnh hưởng?
6. **Tính đảo ngược:** có thể rollback an toàn, thời gian để tạo sự cố không thể khôi phục.
7. **Obligations:** có mốc hợp đồng/pháp luật/chứng nhận bắt buộc không?
8. **Confidence:** nguồn đáng tin và effective state đã kiểm chứng hay mới chỉ là tín hiệu nghi vấn?
9. **Thời gian tồn tại:** bao lâu kể từ event, có đang vượt ngưỡng xử lý không?

### 7.2. Làn xử lý minh họa

| Làn | Ví dụ | Hành động |
|---|---|---|
| **Khẩn/critical** | Public data exposure, key compromise, audit mất trong incident, quyền admin bất thường. | Kích hoạt IR/containment khi có căn cứ và đúng thẩm quyền; assessment ưu tiên. |
| **Cao/high** | Privilege escalation mới ở production, segmentation drift cho asset nhạy cảm. | Review sớm theo mục tiêu nội bộ, xem release/change gate và mitigation. |
| **Trung bình/medium** | New production asset chưa có đầy đủ baseline nhưng không public. | Review theo queue có chủ sở hữu, kiểm chứng onboarding/monitoring. |
| **Thấp/low** | Metadata thay đổi không tác động behavior theo quy tắc đã xác minh. | Record, sampling/periodic validation hoặc automated no-change assessment. |
| **Unknown/evidence gap** | Event thiếu resource ID, API không đọc được target. | Quarantine, sửa telemetry, không ép thành LOW hoặc PASS. |

Các mức trên là **đề xuất**, không phải SLA hay severity framework phổ quát. Thời hạn và quyền quyết định do risk policy của tổ chức xác định; nếu có nghĩa vụ bắt buộc thì không chỉ chọn theo điểm rủi ro.

### 7.3. Chống ưu tiên dựa vào nhãn sự kiện

Một alert mang tên “low” nhưng liên quan production root account và đường network public có thể cần review cao. Ngược lại, một deployment đã được duyệt có thể tạo nhiều sự kiện nhưng chỉ cần một bộ review theo release manifest nếu không có drift và các điều kiện chuyển stage đã định.

## 8. Workflow Rà soát theo sự kiện từ tín hiệu đến quyết định

~~~mermaid
flowchart TD
    A["Event từ nguồn: IAM, cloud, CI/CD, scanner, GRC"] --> B["Xác thực nguồn, schema, thời gian, dedup"]
    B --> C["Correlate asset/change/incident + xác định scope"]
    C --> D{"Match trigger catalog?"}
    D -->|Không| E["Lưu sự kiện và kiểm tra coverage/sampling theo chính sách"]
    D -->|Có| F["Risk triage + mapping claim/control"]
    F --> G["Lấy effective baseline và evidence mới"]
    G --> H["Áp test/assurance criteria, xét assumptions"]
    H --> I{"Kết quả có đủ bằng chứng?"}
    I -->|Không| J["INCONCLUSIVE: evidence gap, retry, owner"]
    I -->|Có| K{"Control/claim được hỗ trợ?"}
    K -->|Có| L["PASS theo scope/time; ghi review & triggers"]
    K -->|Không| M["FAIL: finding, risk treatment, gate/IR nếu cần"]
    J --> N["Thu thập lại/điều tra, escalation khi quá hạn"]
    M --> O["Mitigation / remediation / exception hợp lệ"]
    O --> P["Retest + reviewer decision"]
    P --> G
    L --> Q["Lưu audit trail, giám sát sự kiện tiếp theo"]
    N --> Q
~~~

### 8.1. Các pha chính

**Discover → Validate → Correlate → Triage → Assess → Decide → Act → Verify → Record.** Nên định nghĩa rõ mỗi pha có owner, input, output, SLA/SLO nội bộ, evidence và điều kiện chuyển trạng thái.

Không cho phép một review chuyển từ “trigger observed” sang “PASS” chỉ nhờ việc tạo ticket. Kết quả PASS phải gắn đúng **control objective, dữ liệu nguồn và phép kiểm tra**.

### 8.2. Không đánh giá lại quá rộng

Nếu event chỉ ảnh hưởng một IAM role ở account A, có thể đánh giá role A cùng các đường trust liên quan, thay vì chạy một audit toàn công ty. Nhưng cần xét **blast radius và shared dependencies**; thay đổi identity provider dùng chung có thể làm nhiều account chịu tác động. Quy tắc scoping phải lưu assumptions và giới hạn.

## 9. Trạng thái review và ý nghĩa vận hành

Một state machine giúp tránh nhầm giữa “đã nhận event”, “đã đánh giá” và “đã khắc phục”.

| State minh họa | Ý nghĩa | Điều kiện chuyển |
|---|---|---|
| **OBSERVED** | Sự kiện đã được ghi nhưng chưa phân loại. | Validate source/schema/time. |
| **QUEUED** | Khớp trigger, đã xác định owner/priority. | Đủ dữ liệu để bắt đầu assessment. |
| **ASSESSING** | Đang thu evidence, test và review claims. | Có verdict hoặc xác định gap. |
| **NEEDS_EVIDENCE** | Dữ liệu thiếu/không đáng tin, chưa kết luận được. | Collector sửa, evidence mới hoặc escalation. |
| **PASS_VERIFIED** | Claim/control được hỗ trợ trong scope và thời điểm được đánh giá. | Lưu validity/triggers; mở lại khi state đổi. |
| **FAIL_CONFIRMED** | Control gap được chứng minh. | Finding/incident/risk treatment. |
| **MITIGATING** | Đang giảm phơi nhiễm hoặc xử lý nguyên nhân. | Retest hoặc đổi risk decision. |
| **RETESTING** | Kiểm chứng action đã triển khai. | PASS, FAIL hoặc INCONCLUSIVE mới. |
| **CLOSED_WITH_EVIDENCE** | Kết luận, action và approval đã đầy đủ. | Giữ lịch sử; sự kiện mới tạo review version mới. |
| **SUPERSEDED** | Review được thay bằng phiên bản dựa trên sự kiện/bằng chứng mới. | Không ghi đè kết luận lịch sử. |

Có thể dùng trạng thái **REJECTED_TRIGGER** cho sự kiện sai/ngoài phạm vi, nhưng phải ghi lý do, quy tắc và mẫu kiểm tra. Không lạm dụng nó để bỏ những cảnh báo khó xử lý.

### 9.1. Tách workflow result và control verdict

Một workflow có thể **được xử lý đúng hạn** nhưng control bị **FAIL**. Ngược lại, control có thể đang PASS theo dữ liệu hiện có nhưng review **quá hạn** so với mục tiêu assurance. Giữ hai trục riêng:

- **process_status:** có thực hiện đúng bước/scope/giờ hay không.
- **control_verdict:** PASS/FAIL/INCONCLUSIVE/NOT_APPLICABLE theo tiêu chí.
- **risk_decision:** rủi ro còn lại chấp nhận hay cần xử lý trong giới hạn quyền.
- **remediation_status:** nguyên nhân đã sửa/retest hay chưa.

## 10. Evidence chain cho một cuộc rà soát do sự kiện kích hoạt

Một review có thể chỉ vài phút hoặc kéo dài nhiều ngày, nhưng mọi kết luận quan trọng phải truy về dữ kiện nguồn.

~~~mermaid
flowchart LR
    EVT["Raw event + provenance"] --> TRG["Trigger rule/version + match"]
    TRG --> SCOPE["Resource/claim/control mapping"]
    SCOPE --> BASE["Trạng thái trước và sau / baseline"]
    BASE --> TEST["Test run / effective state checks"]
    TEST --> VER["Reviewer + verdict + limitations"]
    VER --> DEC["Action / exception / incident / closure"]
    DEC --> RST["Retest / review version mới"]
~~~

### 10.1. Những artifact nên được liên kết

| Evidence | Mục đích | Điều chưa thể suy ra chỉ từ artifact đó |
|---|---|---|
| **Raw event và event ID** | Chứng minh một tín hiệu đã xuất hiện ở nguồn. | Tín hiệu thật sự làm control không đạt. |
| **Source/collector health** | Đánh giá khả năng thu dữ liệu. | Mọi event trong toàn population đã được nhận. |
| **Before/after snapshot** | So cấu hình/đối tượng và phạm vi thay đổi. | Hành vi runtime thực tế hoàn toàn giống cấu hình. |
| **Effective policy export** | Hiểu quyền/cấu hình áp dụng ở runtime. | Mọi đường bypass, session/token cũ đã bị thu hồi. |
| **Test run với expected/actual** | Kiểm chứng control trong tình huống được thử. | Các tài sản chưa thử cũng PASS. |
| **Threat/risk assessment** | Lý giải impact, scope, exposure và xử lý rủi ro. | Lỗi đã khắc phục chỉ vì được đánh giá. |
| **Approval/decision record** | Ai quyết định gì, đúng thẩm quyền, trong thời hạn nào. | Control gốc tự chuyển FAIL thành PASS. |
| **Remediation/retest** | Chứng minh thay đổi đã triển khai và xác minh. | Kỳ trước khi sửa chưa từng có rủi ro. |

### 10.2. Metadata tối thiểu

Một review record nên chứa **event_id, trigger_id/version, review_id, parent/related IDs, control IDs, asset scope, event_time, ingestion_time, assessment_time, test IDs, evidence references, collector/reviewer, verdict, limitation, action, deadline, expiry và history**. Với artifact nhạy cảm, lưu link tới evidence vault hạn quyền thay vì nhúng token/PII vào ticket.

### 10.3. Hash, chữ ký và tính đầy đủ

Digest giúp phát hiện thay đổi nội dung sau mốc đáng tin, chữ ký có thể hỗ trợ authenticity theo trust model. Nhưng một CSV thiếu 10 account cũng có hash hợp lệ. Cần **population reconciliation**, kiểm tra API pagination/permissions, kiểm tra dữ liệu bị bỏ và đối chiếu nguồn thích hợp để bảo đảm completeness.

## 11. Kiểm chứng claim đúng phạm vi và thời gian

Một vấn đề lớn trong continuous assurance là **sử dụng kết quả point-in-time như thể bảo đảm liên tục**.

### 11.1. Bốn mốc cần phân biệt

~~~text
T0  Sự kiện thực sự xảy ra theo nguồn
T1  Sự kiện được collector/assurance engine nhận
T2  Review bắt đầu hoặc kiểm thử evidence
T3  Reviewer ra verdict/action decision
T4  Remediation được triển khai và retest, nếu cần
~~~

Nếu privileged role được mở lúc 09:00 nhưng collector chỉ nhận lúc 09:10, một review lúc 09:12 chỉ nói trạng thái ở thời điểm đó. Nếu quyền tồn tại và bị sử dụng từ 09:00 đến 09:12, cần xem log/impact khoảng đó; việc sửa quyền lúc 09:15 **không làm khoảng trước thành PASS**.

### 11.2. Test về thời điểm và kỳ

| Claim | Bằng chứng phù hợp | Kết luận không được vượt |
|---|---|---|
| “Role A hiện không có wildcard.” | Effective policy/export và test runtime tại T. | Không suy ra role A chưa từng có wildcard trong tháng. |
| “Audit log bao phủ cả kỳ.” | Account inventory, log config history, collector health, synthetic tests và gap analysis. | Một event đến SIEM lúc T không chứng minh toàn bộ kỳ. |
| “Release R đạt security gate.” | Test trên digest R, approval đúng scope và post-release verification. | Không áp dụng cho artifact R+1 hoặc region chưa được duyệt. |
| “Mitigation hoạt động liên tục.” | Evidence vận hành và giám sát theo định nghĩa coverage. | Không tự bảo đảm khi collector gián đoạn hoặc source mới chưa onboard. |

### 11.3. Refresh sau sự kiện mới

Nếu review đang chạy thì có thêm thay đổi tiếp theo, cần quyết định **merge/restart/version** theo chính sách. Không ghi verdict từ snapshot cũ cho state mới mà không kiểm tra. Có thể pin snapshot và source version, phát hiện event đến sau, rồi mở review tiếp theo; giữ quan hệ giữa hai review.

## 12. Điểm quyết định: PASS, FAIL, INCONCLUSIVE, NOT_APPLICABLE

Rà soát theo sự kiện nên dùng outcome chuẩn hóa, nhưng nêu cụ thể **tiêu chí nào** được đánh giá.

| Verdict | Điều kiện | Ví dụ |
|---|---|---|
| **PASS** | Evidence có độ tin cậy và coverage phù hợp chứng minh control/claim đạt tại scope/kỳ. | Quyền mới thuộc role đã duyệt, effective IAM và negative test đạt. |
| **FAIL** | Bằng chứng đáng tin chỉ ra tiêu chí không đạt. | Public admin port được phép truy cập trái network policy. |
| **INCONCLUSIVE** | Không đủ chứng cứ, phạm vi chưa rõ, nguồn lỗi hoặc phép thử chưa thể suy ra kết quả. | API collector mất quyền nên không thể đọc account mới. |
| **NOT_APPLICABLE** | Tiêu chí thật sự không áp dụng và có căn cứ theo requirement/version. | Một rule cho personal data không áp dụng với dataset được xác minh không chứa dữ liệu đó. |

**Event severity ≠ control verdict.** Một event được xếp high risk vẫn có thể dẫn tới PASS nếu thay đổi đúng authorization và test đạt. Một event được xếp low risk có thể phát hiện FAIL trên asset quan trọng khi evidence mới chỉ ra bypass.

### 12.1. INCONCLUSIVE không phải PASS và cũng không mặc định FAIL

Nếu không nhận log từ server, có thể logging bị tắt **hoặc** collector mất quyền. Review cần phân biệt:

- **Control failure confirmed:** synthetic event có tại nguồn nhưng không tới đích trong SLA/cửa sổ cho phép, với pipeline được kiểm tra.
- **Evidence gap:** chưa thể xác minh nguồn hoặc collector không truy cập được.
- **Scope defect:** asset mới chưa có trong inventory, không thể suy coverage.
- **No event expected:** không sinh log vì chưa có hoạt động được định nghĩa; cần test chủ động phù hợp.

Không được tự quyết định “safe” từ sự im lặng của telemetry.

## 13. Rà soát theo sự kiện trong IAM và Access Control

IAM là lĩnh vực có **bề mặt thay đổi thường xuyên** và rủi ro cao: tạo người dùng, thay role, thêm federation, rotate service credentials, tạo break-glass hoặc revoke privileged session.

### 13.1. Trigger hữu ích

- Human admin được cấp quyền mới hoặc thay đổi nhóm đặc quyền.
- Service identity được cấp wildcard action hoặc quyền truy cập dữ liệu nhạy cảm.
- MFA policy chuyển sang chế độ cho phép bypass hoặc exception group.
- Federation trust hoặc session lifetime thay đổi.
- Break-glass được sử dụng ngoài playbook.
- Offboarding chưa revoke token/role theo tiêu chí.
- Một resource policy cho phép principal bên ngoài tổ chức.

### 13.2. Review cần kiểm tra gì?

1. **Nguồn thay đổi:** identity, actor, request/change approval và event ID.
2. **Population:** danh sách account/role, kể cả non-human identities và external principals.
3. **Effective permissions:** không chỉ policy trong Git mà quyền runtime, inheritance, resource policies.
4. **Allowed/denied behavior:** thử đúng các quyền nghiệp vụ được phép và thao tác ngoài quyền.
5. **Scope/time:** tài khoản mới có ảnh hưởng region/tenant nào, từ khi nào quyền có hiệu lực.
6. **Auditability:** event và session/role changes có được log đủ cho điều tra.
7. **Action:** thu hồi khi cần, risk review, exception hoặc remediation và retest.

**Ví dụ:** một IAM policy được mở thêm `s3:*` trong production. Chỉ có diff là chưa đủ để kết luận mức phơi nhiễm; cần biết principal có thể assume role nào, bucket nào, quyền ở resource policies và guardrails ở organization level. Nếu effective access vượt least privilege, mở finding; nếu event thuộc change có approval nhưng scope khác, phải đánh giá cả **authorization gate**.

## 14. Cloud configuration và Runtime drift

IaC và GitOps hỗ trợ kiểm soát thay đổi có kế hoạch, nhưng runtime vẫn có thể drift do thao tác console, incident emergency, automation khác hoặc tài nguyên unmanaged.

### 14.1. So ba trạng thái

~~~text
Desired state (Git/IaC)
    vs
Approved target state (release/change record)
    vs
Observed effective state (cloud/runtime APIs)
~~~

Một trigger “resource drift” phải chỉ ra **cái gì khác**, **bản nào được duyệt**, **tài sản nào**, **thời điểm nào** và **security objective nào bị ảnh hưởng**.

### 14.2. Tránh tự sửa thay đổi hợp lệ nhưng chưa đồng bộ

Nếu một emergency change đã được Incident Commander phê duyệt đúng cơ chế nhưng chưa kịp đồng bộ IaC, auto-remediation có thể hoàn tác containment của sự cố. Vì vậy quy tắc review và tự sửa phải hiểu **emergency override, expiry, change references và protected actions**. Không mặc định mọi drift đều ác ý hoặc phải revert tức thì.

### 14.3. Test drift detector

Một detector đáng tin cần kiểm thử được ít nhất:

- Một thay đổi trái policy được phát hiện và tạo event đúng resource.
- Thay đổi hợp lệ theo whitelist/exception đúng hạn không bị xử lý nhầm.
- Resource mới xuất hiện được đưa vào population.
- Collector mất quyền hoặc event queue lỗi được đánh dấu health failure, không im lặng.
- Khi event lặp, chỉ một finding/review canonical được mở hoặc có cơ chế liên kết.
- Sau correction, effective state được retest; không chỉ ghi “remediation job completed”.

## 15. Event-driven review cho Vulnerability và Threat Intelligence

Một CVE mới hoặc advisory của vendor không có nghĩa mọi asset đều bị ảnh hưởng. Nhưng nếu asset inventory và dependency mapping cho thấy một component đang dùng phiên bản có vấn đề, kết luận patch/risk trước đó có thể cần được đánh giá lại.

### 15.1. Quy trình phân tích tối thiểu

1. Nhận advisory có **source, version, thời gian và chất lượng dữ liệu**.
2. Map affected component/version/config đến **SBOM, package inventory và deployed artifact**.
3. Kiểm tra exposure, attack path, privilege, required preconditions và tình trạng exploit.
4. Xác định controls hiện có hoặc mitigations, có bằng chứng hiệu lực không.
5. Đặt priority/deadline theo risk policy và nghĩa vụ áp dụng.
6. Mở finding/remediation hoặc điều chỉnh risk decision.
7. Retest sau fix, đối chiếu asset coverage và lưu history.

Không dùng CVSS đơn lẻ làm kết luận “có thể khai thác ngay” hoặc “không nguy hiểm” mà không xem ngữ cảnh. Ngược lại, nếu incident cho thấy một đường khai thác mới, **trigger cần reassessment ngay**, không đợi chu kỳ vulnerability scan.

### 15.2. Advisory hay scanner scan lại?

Có thể dùng một review event-driven để quyết định **những asset nào cần scan bổ sung hoặc kiểm tra theo kỹ thuật khác**, thay vì scan toàn fleet khi có mọi advisory. Tuy nhiên, mapping chỉ chính xác nếu component inventory đủ; thiếu SBOM/coverage phải được báo là **evidence gap**, không coi asset chắc chắn không ảnh hưởng.

## 16. Thay đổi dữ liệu, privacy, nhà cung cấp và nghĩa vụ tuân thủ

Continuous assurance không dừng ở cloud/IAM. Những thay đổi phạm vi dữ liệu và quan hệ bên thứ ba có thể làm các claim bảo mật cũ không còn áp dụng.

| Event | Cần xem xét lại | Lưu ý thẩm quyền |
|---|---|---|
| Dataset chuyển sang mức nhạy cảm cao hơn | Encryption, access, retention, logging, backup, data flow. | Data owner và privacy/legal khi nghĩa vụ áp dụng. |
| Dữ liệu chuyển vùng lưu/xử lý | KMS, residency, subprocessor, hợp đồng và data flow. | Không tự coi approval kỹ thuật tương đương sự chấp thuận pháp lý. |
| Nhà cung cấp thêm subprocessor | Chain of responsibility, data access, audit scope. | Theo cơ chế hợp đồng/thông báo/chấp thuận phù hợp. |
| SaaS đổi audit API/schema | Evidence pipeline, log completeness và detection. | Vendor owner, security monitoring và contract owner. |
| Policy/standard mới có hiệu lực | Applicability mapping, controls, exceptions, deadlines. | Control owner và compliance đánh giá cùng bên chịu nghĩa vụ. |
| Một ngoại lệ security hết hạn | Quyền vận hành lệch baseline, residual risk, mitigation. | Phải renew đúng quyền; không auto-extend. |
| Phát hiện hợp đồng mới có control bổ sung | Release gates, data handling, third-party evidence. | Legal/compliance kiểm tra effective date và phạm vi. |

**Risk acceptance nội bộ không tự cho phép lệch khỏi yêu cầu pháp luật/hợp đồng bắt buộc.** Review có thể tạo **decision needed** cho chủ thể có quyền, nhưng không được biến ngẫu nhiên một contract breach thành “PASS vì đã có exception”.

## 17. Liên kết rà soát với Release, Change và Remediation

Review theo sự kiện có giá trị khi kết quả đi được vào **luồng công việc có quyền thực thi**.

~~~mermaid
flowchart TD
    E["Trigger: release / config / finding / vendor event"] --> R["Event-driven assurance review"]
    R --> C{"Tác động tới claim/control?"}
    C -->|Không, evidence đầy đủ| P["Ghi review và validity"]
    C -->|Có| D["Evaluate scope, risk và test"]
    D --> G{"Kết quả"}
    G -->|PASS| P
    G -->|FAIL| F["Finding / IR / change block theo policy"]
    G -->|INCONCLUSIVE| M["Evidence gap / collector fix / escalation"]
    F --> A["Action plan / mitigation / exception hợp lệ"]
    A --> T["Deployment/rollback/compensating tests"]
    T --> V["Independent retest + closure"]
    V --> R
~~~

### 17.1. Với release/change event

- Đối chiếu **approved source revision, artifact digest, manifest và rollout scope** với observed runtime.
- Đánh giá các security gates bị ảnh hưởng, nhất là IAM, network, secrets, audit, backup.
- Nếu artifact khác bản approved hoặc gate bắt buộc mất hiệu lực, kích hoạt reapproval/NO-GO theo chính sách.
- Sau deploy, tạo review cho post-change runtime state, không dùng phê duyệt trước change làm bằng chứng cuối cùng.

### 17.2. Với finding/remediation event

- Khi fix được deploy, kích hoạt retest cho **control gốc trên scope đúng**.
- Nếu retest PASS, cập nhật claim theo thời điểm mới và đóng finding theo quyền.
- Nếu retest FAIL, giữ finding mở và xác minh root cause/rollback.
- Nếu thiếu quyền collector, ghi INCONCLUSIVE, sửa evidence gap; không đánh dấu fixed chỉ vì PR merge.

### 17.3. Với exception event

Khi ngoại lệ gần hết hạn, scope tăng hoặc control bù trừ thất bại, kích hoạt risk reassessment. Quy trình renewal phải có **evidence hiện hành, thẩm quyền và hạn mới**; một event “reminder sent” không tương đương quyết định đã được duyệt.

## 18. Automation: Engine kích hoạt và thiết kế an toàn

Một kiến trúc tối thiểu có thể gồm **event adapters → canonical queue → correlation/rules → evidence collectors → control evaluators → decision workflow → evidence vault và reporting**.

~~~mermaid
flowchart LR
    S["Cloud / IdP / CI-CD / SIEM / GRC sources"] --> A["Adapters: authentication + schema"]
    A --> Q["Durable event queue + dead-letter"]
    Q --> N["Normalize / dedup / correlate"]
    N --> R["Trigger catalog + risk routing"]
    R --> E["Evidence collectors & effective-state tests"]
    E --> V["Control verdict + reviewer gates"]
    V --> W["Ticket/IR/exception/remediation workflow"]
    W --> H["Versioned evidence & audit history"]
    H --> D["Assurance dashboard + metrics"]
    Z["Health monitoring / reconciliation"] --> A
    Z --> Q
    Z --> E
~~~

### 18.1. Các nguyên tắc thiết kế

- **Idempotency:** cùng event ID không tạo hành động phá hoại lặp lại; xử lý retry an toàn.
- **Versioned rules:** trigger và control criteria có version, tạo được kết luận tại thời điểm trước.
- **State-aware:** query effective state trước verdict; không suy mặc định từ một delta event.
- **Scope-aware:** chỉ hành động với những asset và quyền được xác định.
- **Least privilege:** collector đọc đủ và action bot chỉ có quyền đã được ủy quyền.
- **Separate assessment/action:** review tự động có thể mở ticket; những thay đổi rủi ro cao cần gate/human approval khi policy yêu cầu.
- **Safety checks:** action nào gây gián đoạn/irreversibility phải có stop/rollback và incident override phù hợp.
- **Fail visibility:** lỗi sensor, queue, schema hoặc evaluator phải tạo health alert, không im lặng coi mọi control PASS.
- **Auditability:** giữ inputs, rule version, decision, actuation outcomes, reviewer và những lần override.
- **Continuous validation:** replay/test events giả lập an toàn để kiểm tra detector và phản ứng.

### 18.2. Pseudocode minh họa

~~~text
on_event(event):
    validate_source_and_schema(event)
    if invalid(event):
        quarantine_and_alert(event)
        return

    canonical = correlate_and_deduplicate(event)
    triggers = match_review_rules(canonical)
    for trigger in triggers:
        review = open_or_update_review(trigger, canonical)

        scope = reconcile_inventory_and_effective_state(review)
        if scope.unverified:
            mark_inconclusive_and_escalate(review)
            continue

        evidence = collect_required_evidence(review, scope)
        verdict = evaluate_control_with_versioned_policy(evidence)
        record_verdict_and_limitations(review, verdict)

        if verdict == "FAIL":
            initiate_approved_risk_or_remediation_workflow(review)
        elif verdict == "INCONCLUSIVE":
            open_evidence_gap_and_retry_or_escalate(review)
        else:
            record_assurance_validity_and_future_triggers(review)
~~~

Pseudocode không được chạy nguyên văn. Trong thực tế phải xử lý transaction boundaries, retries, event ordering, permissions, race conditions và quyền phê duyệt. **Không tự động thu hồi hàng loạt privileged accounts** chỉ vì một event chưa xác thực; nên dựa trên runbook đã được phê duyệt và trạng thái thực tế đã kiểm tra.

## 19. Ownership, RACI và trách nhiệm của các nhóm

| Hoạt động | Responsible | Accountable | Consulted/Informed |
|---|---|---|---|
| Duy trì trigger catalog và mapping controls | Security Assurance / Control Owners | Security Governance Lead | Engineering, Risk, Audit |
| Phát tín hiệu và giữ source logs | Cloud/IAM/CI-CD/SOC owner | Source System Owner | Assurance, Operations |
| Vận hành ingestion, queue, schema | Platform/Observability Engineering | Assurance Platform Owner | Security Operations |
| Xác định scope, kiểm tra effective state | Engineering/Security Assessor | Control Owner | Service/Data Owner |
| Đánh giá risk tier và escalation | Security/Risk Analyst | Business/Information Risk Owner theo thẩm quyền | Legal/Compliance khi cần |
| Tạm dừng release hoặc containment | Release/Incident Authority theo policy | Change/Incident Owner | SRE, Security, Business |
| Remediation và kiểm thử | Engineering/Platform Owner | Service Owner | Security Verification |
| Review độc lập và đóng findings | Security Assurance Reviewer | Control/Issue Owner theo quy trình | Risk, Audit |
| Xem nghĩa vụ pháp lý/hợp đồng | Legal/Compliance/Privacy | Chủ thể quyền nghĩa vụ tương ứng | Procurement/Vendor Owner |

Đây là **RACI minh họa**; trong tổ chức nhỏ có thể gộp một số vai trò nhưng cần tách review/phê duyệt rủi ro đáng kể phù hợp chính sách.

### 19.1. Ai có quyền dừng một deployment?

Với trigger về release, quyền **block**, **pause stage**, **rollback**, **disable feature** hoặc **escalate** phải được định nghĩa trước. Một automation có thể đánh dấu NO-GO theo gate chính thức nhưng không nên tự phá hủy trạng thái production nếu chưa có quyền và runbook an toàn.

### 19.2. Incident và assurance phải phối hợp nhưng không lẫn vai trò

Nếu trigger cho thấy nghi vấn tấn công, SOC/IR có thể cần containment ngay, còn assurance ghi rằng control claim trước đó bị thách thức. Không trì hoãn IR để làm đầy đủ biểu mẫu audit; cũng không để các bước khẩn cấp trở thành waiver vô hạn không hậu kiểm.

## 20. SLO và chỉ số đo chương trình event-driven review

Không chỉ đo số event đã nhận. Điều cần biết là **một thay đổi quan trọng có được phát hiện, đánh giá đúng và dẫn đến hành động kịp thời không**.

| Metric | Định nghĩa hữu ích | Cạm bẫy |
|---|---|---|
| **Trigger coverage** | Tỷ lệ các loại thay đổi/rủi ro đã được map nguồn/điều kiện và kiểm thử. | Catalog nhiều rule không chứng minh event source thực sự hoạt động. |
| **Source health / ingestion gaps** | Số nguồn mất heartbeat, API lỗi, schema/quyền thiếu trong kỳ. | “0 alerts” khi collector tắt dễ làm số đẹp giả. |
| **Event-to-observe latency** | Từ occurred_at đến observed_at với timestamp hợp lệ. | Clock skew, buffer, batch và thiếu source timestamps. |
| **Event-to-review latency** | Từ trigger đủ điều kiện đến khi review bắt đầu hoặc có verdict (phải chọn rõ). | Nhầm ACK với đánh giá hoàn tất. |
| **Review SLO attainment** | Tỷ lệ review đủ điều kiện hoàn tất đúng hạn theo risk tier. | Loại pending/overdue hoặc invalid records khỏi mẫu số. |
| **Evidence completeness** | Tỷ lệ review có đủ scope, required tests, provenance và verdict. | Điền đủ ô nhưng evidence sai thời điểm/scope. |
| **Control drift dwell time** | Thời gian từ khi drift có hiệu lực đến khi mitigation/correction đạt. | Phải phân biệt thời điểm phát hiện với thời điểm thực sự xảy ra. |
| **False trigger/review rate** | Tỷ lệ trigger dẫn tới review không tác động theo tiêu chí. | Tự xóa event hợp lệ chỉ để giảm noise. |
| **Missed trigger rate** | Tỷ lệ thay đổi đáng lẽ kích hoạt review nhưng không được tạo từ tập kiểm chứng. | Cần nguồn độc lập/replay/sampling để ước lượng. |
| **Reopen/recurrence** | Control gap tái diễn sau verified closure. | Không đồng nhất recurrence với finding do cause khác. |
| **Time to verified remediation** | Từ thời điểm được định nghĩa đến retest control đạt. | Deployment date không phải ngày retest. |
| **Manual override quality** | Overrides có lý do, thẩm quyền, expiry và evidence. | Override nhanh không đồng nghĩa an toàn. |

### 20.1. Ví dụ phép đo

Giả sử một tuần có **40 trigger high-risk** đủ điều kiện theo rule catalog và đã được đối chiếu với nguồn. Trong đó 33 review có verdict trong mục tiêu thời gian, 4 review hoàn thành muộn, 2 còn pending và đã quá hạn, 1 gặp lỗi timestamp chưa xác minh.

- **Tỷ lệ đạt SLO với mẫu số toàn bộ trigger đủ điều kiện:** 33/40 = **82,5%** theo quy tắc xem pending/unknown là chưa chứng minh đạt.
- **Completed verdict:** 37/40 = **92,5%**; không nói 37 đều đúng hạn.
- **Overdue pending:** 2/40 = **5%**; cần escalation theo risk tier.
- **Data-quality unresolved:** 1/40 = **2,5%**, phải báo riêng.

Những số liệu giả định chỉ thể hiện **hiệu năng quy trình**; không chứng minh 82,5% controls an toàn. Nếu nguồn event đã bỏ sót 10 thay đổi quan trọng, chính mẫu số 40 cũng không đầy đủ, nên cần source reconciliation/negative tests.

### 20.2. Dùng mean/median cẩn trọng

Review latency có thể lệch mạnh vì một case cần vendor investigation kéo dài. Nên báo **median, P90/P95 khi mẫu đủ lớn, số pending/overdue, phân nhóm theo severity và source**. Một mean thấp có thể do nhiều event low-risk dễ xử lý; không được kết luận capability high-risk cải thiện nếu nhóm high-risk chậm hơn.

## 21. Mẫu Event-driven review record và Trigger catalog dạng YAML

Đây là **mẫu minh họa dùng cho học tập**, không phải schema chính thức của một công cụ SIEM/GRC hoặc configuration thực thi. Các asset IDs, timestamps và kết quả đều giả định. Ví dụ cố ý có **review xác nhận FAIL** dù workflow được kích hoạt và thu evidence đúng quy trình.

~~~yaml
continuous_assurance:
  id: "CA-EVENT-REVIEW-EXAMPLE-008"
  module: "SECURITY_SECURITY_ASSURANCE"
  version: "1.0"
  service: "payment-platform"
  environment: "production"
  assurance_owner: "Security Assurance Lead"
  data_classification: "CONFIDENTIAL"

trigger_catalog_entry:
  trigger_id: "TRG-PRIVILEGE-EXPANSION-01"
  version: "3.2"
  event_types:
    - "iam.role.policy.updated"
    - "iam.principal.role.granted"
  predicate: "effective privilege increased on production critical asset"
  linked_control_ids:
    - "IAM-LEAST-PRIV-01"
    - "IAM-CHANGE-APPROVAL-02"
  related_claims:
    - "C-PRIVILEGED-ACCESS-SCOPED"
    - "C-CHANGES-AUTHORIZED"
  required_evidence:
    - "raw-event"
    - "approved-change"
    - "effective-policy-before-and-after"
    - "inventory-reconciliation"
    - "positive-negative-access-test"
  expected_response_lane: "HIGH"
  required_review: "SECURITY_REVIEW"
  owner: "Identity Security Owner"

source_event:
  event_id: "cloud-audit-event-example-20261128-012"
  source: "cloud-management-audit"
  source_tenant: "prod-account-a"
  schema_version: "v2"
  occurred_at_utc: "2026-11-28T02:14:00Z"
  observed_at_utc: "2026-11-28T02:14:08Z"
  actor: "deployment-role-example"
  resource_id: "role-payment-worker"
  correlation_change_id: "CHG-EXAMPLE-501"
  raw_evidence_ref: "restricted/continuous-008/events/raw-012"
  source_health: "PASS"
  source_integrity: "VERIFIED_FOR_COLLECTED_EVENT"

review:
  review_id: "REV-EVENT-EXAMPLE-008-001"
  opened_at_utc: "2026-11-28T02:14:12Z"
  evaluated_at_utc: "2026-11-28T02:20:00Z"
  review_policy_version: "continuous-assurance-policy-v6"
  owner: "Security Assurance Reviewer"
  state: "FAIL_CONFIRMED"
  scope:
    assets: ["role-payment-worker"]
    cloud_accounts: ["prod-account-a"]
    regions: ["region-example-1"]
    identities: ["svc-payment-worker"]
    inventory_reconciled: true

evidence:
  before_policy:
    ref: "restricted/continuous-008/baseline/role-policy-v4"
    observed_at_utc: "2026-11-28T02:10:00Z"
  after_effective_policy:
    ref: "restricted/continuous-008/reviews/role-policy-v5"
    observed_at_utc: "2026-11-28T02:17:00Z"
  change_authorization:
    ref: "restricted/continuous-008/change/approved-scope"
    permitted_privileges: "read-only"
  access_test:
    run_id: "iam-deny-test-example-050"
    result: "FAIL"
    reason: "Service identity can write to unrelated buckets"
  collection_completeness: "PASS_ON_LISTED_SCOPE"
  historical_coverage: "NOT_ASSESSED_IN_THIS_REVIEW"

assessment:
  original_claim: "Privileged actions limited to approved read-only scope"
  current_control_verdict: "FAIL"
  trigger_processing: "PASS"
  authorization_verdict: "FAIL"
  residual_risk: "HIGH_PENDING_REASSESSMENT"
  reason: >
    Thay đổi cho phép write trên tài nguyên ngoài phạm vi
    được phê duyệt; effective state và negative test xác nhận.
  limitations:
    - "No claim made about other accounts outside the reviewed scope"

action:
  response_type: "CONTAINMENT_AND_REMEDIATION"
  incident_triage_required: true
  finding_id: "FINDING-PRIVILEGE-EXAMPLE-008"
  action_plan_id: "ACTION-PLAN-EXAMPLE-008"
  planned_mitigation: "Remove unauthorized write privilege safely"
  required_retest:
    - "Effective permission export"
    - "Denied unauthorized write test"
    - "Allowed legitimate queue operation test"
  accountable_owner: "Payment Platform Owner"
  due_date_source: "APPROVED_RISK_TREATMENT_POLICY"

governance:
  exception_status: "NONE_APPROVED"
  review_history_versioned: true
  evidence_vault: "restricted-security-assurance"
  evidence_retention_policy: "INTERNAL_POLICY"
  re_evaluate_on:
    - "new-role-grant"
    - "further-policy-change"
    - "credential-compromise"
    - "mitigation-failure"
  reviewer_signoff: "REQUIRED_AFTER_RETEST"
~~~

### 21.1. Vì sao verdict FAIL?

Change record chỉ cho phép read-only, nhưng effective policy và negative test cho thấy service identity thực hiện được hành động ghi ngoài phạm vi. Đây là **control failure có bằng chứng**, không phải chỉ thay đổi metadata và cũng không phải false positive vì policy đã khai báo thay đổi.

### 21.2. Vì sao chưa thể tuyên bố toàn bộ chương trình tốt?

Review này có source health PASS và đủ chứng cứ cho **một role ở một account**, không chứng minh mọi account/role được theo dõi hoặc không có event bị mất trong kỳ. `historical_coverage: NOT_ASSESSED_IN_THIS_REVIEW` ngăn kết luận quá mức. Phải bổ sung test coverage/reconciliation ở cấp chương trình.

### 21.3. Closure sau remediation

Khi nhóm platform sửa quyền, có thể giữ review cũ với trạng thái FAIL lịch sử và mở **retest record mới**. Reviewer kiểm tra denied write trên đường không được phép, allowed business operation, effective permission, audit trail và scope; chỉ sau đó cập nhật trạng thái finding theo quy trình. Không sửa event ban đầu thành “chưa từng có privilege expansion”.

## 22. Tình huống thực hành: Cloud privilege drift đi kèm sự cố logging

Một công ty vận hành dịch vụ đặt hàng qua nhiều cloud accounts. Chương trình assurance có policy “không một human hoặc service identity nào được quyền write ngoài nhiệm vụ; mọi hành động quản trị production phải có audit events tới SIEM”.

Ngày 28/11, hệ thống nhận:

- **09:00:** Một IaC deployment được phê duyệt cho service account ở account A với quyền đọc queue và ghi vào bucket dữ liệu xuất hóa đơn.
- **09:07:** Audit event cho thấy cùng account A có policy update tạo wildcard write lên **tất cả buckets**, do một automation role ngoài workflow triển khai thông thường thực hiện.
- **09:10:** Drift detector gửi cảnh báo “IAM permission changed”, nhưng chỉ có ticket với nhãn INFO, chưa có test effective permissions.
- **09:12:** SIEM không nhận synthetic audit event của account A; một connector vừa bị đổi quyền đọc.
- **09:15:** Nhóm vận hành nói “review tháng trước PASS, release đã approve” và muốn đóng ticket để tránh tăng alert count.
- **09:20:** Nhóm security biết thêm account B mới tạo trong production hôm trước chưa nằm trong danh sách collector.
- **09:25:** Một người dùng nội bộ phát hiện job export báo lỗi; có thể liên quan thay đổi nhưng chưa xác định nguyên nhân.

### 22.1. Câu hỏi

1. Những sự kiện nào là trigger hợp lệ và ảnh hưởng claim nào?
2. Có thể coi release approval lúc 09:00 là chứng minh policy wildcard write hợp lệ không?
3. Thiếu SIEM event là control FAIL hay evidence gap?
4. Account B không có trong collector ảnh hưởng kết luận assurance ra sao?
5. Đường hành động nào hợp lý nếu có dấu hiệu lạm dụng quyền hoặc sự cố production?
6. Cần những evidence nào trước khi kết luận và đóng review?

### 22.2. Hướng giải từng bước

**Bước 1 — Định nghĩa trigger và scope.** Policy update quyền wildcard ở account A là trigger quan trọng cho **IAM least privilege**, **change authorization** và có thể **incident triage** khi actor không nằm trong workflow dự kiến. Lỗi synthetic log là trigger cho **logging/detection assurance**. Account B mới là trigger **onboarding/inventory coverage**; không gộp thành “một cảnh báo IAM duy nhất”.

**Bước 2 — Kiểm tra authorization.** Release approval chỉ có hiệu lực cho source revision, role, permissions và môi trường được duyệt. Nếu wildcard write không nằm trong change scope, không được suy nó hợp lệ chỉ vì một deployment trước đó đã được phê duyệt. Cần lấy effective policy, actor, audit event ID và bản kế hoạch đã ký.

**Bước 3 — Tái kiểm tra control IAM.** Reconcile service identity với access paths; chạy test an toàn theo quyền để kiểm tra hành động ghi ngoài phạm vi. Nếu thực sự ghi được ở buckets không được phép, claim least privilege **FAIL**. Nếu chỉ có event mà policy engine không áp quyền như mô tả, cần phân biệt signal với effective behavior; không kết luận chỉ dựa trên tên sự kiện.

**Bước 4 — Kiểm tra logging.** Tạo hoặc truy xuất synthetic event từ nguồn account A, kiểm tra source audit, quyền collector, queue, parser và SIEM. Nếu có event tại nguồn nhưng collector không đọc/không chuyển tới đích theo tiêu chí, end-to-end logging **FAIL**; nếu thiếu quyền quan sát nguồn và chưa xác định có event được tạo hay không, có **evidence gap/INCONCLUSIVE** cho trạng thái logging. Trong cả hai trường hợp, khả năng assurance hiện tại suy giảm và cần xử lý khẩn theo rủi ro.

**Bước 5 — Xử lý inventory account B.** Không được tuyên bố “100% cloud accounts được monitor” khi account B production chưa nằm trong population. Cần reconcile cloud organization, asset registry và collector enrollment; đánh giá controls logging, IAM, encryption và baseline tại B. Đây là **scope/coverage gap**, không tự động suy mọi control ở B đều FAIL nếu chưa thử.

**Bước 6 — Phân biệt failure nghiệp vụ.** Job export lỗi có thể do policy drift hoặc nguyên nhân khác. Truy dữ liệu pipeline, effective IAM, change correlation, application logs và test nghiệp vụ. Không mặc định một biến cố có quan hệ nhân quả chỉ vì gần thời gian.

**Bước 7 — Ưu tiên containment và review có quyền.** Nếu quyền write trái phép tạo exposure lớn hoặc có dấu hiệu lạm dụng, kích hoạt incident response và áp dụng containment an toàn theo runbook; không chờ đủ biểu mẫu. Đồng thời ghi review evidence, finding và action plan, xét rollback/revoke quyền có kiểm tra luồng nghiệp vụ và log.

**Bước 8 — Retest và đóng.** Sau khi thu hồi wildcard permissions, sửa connector và onboard B, kiểm tra effective deny/allow, synthetic audit end-to-end ở cả accounts, inventory reconciliation, alert routing và lịch sử sự kiện. Giữ kết luận cũ cùng gap thời gian, review mới được sign-off đúng người.

### 22.3. Kết luận mẫu tại lúc phát hiện

| Hạng mục | Bằng chứng hiện có | Verdict phù hợp |
|---|---|---|
| **Change authorization** | Approval chỉ cho quyền hẹp, update do role khác | **FAIL** nếu chứng minh không có authorization tương ứng. |
| **Least privilege ở account A** | Delta event wildcard, chưa có effective behavior test | **INCONCLUSIVE ban đầu**; thành FAIL nếu test xác nhận truy cập vượt quyền. |
| **Logging end-to-end A** | Synthetic event không tới SIEM, connector đổi quyền | **Cần xác minh nguồn**; có thể FAIL hoặc evidence gap. |
| **Account population coverage** | B production chưa vào collector | **FAIL về coverage** nếu yêu cầu là toàn bộ production accounts. |
| **Business job failure** | Có lỗi, chưa xác định nguyên nhân | **INCONCLUSIVE về quan hệ nhân quả**; cần chẩn đoán. |
| **“Assurance tháng trước còn PASS toàn diện”** | Nhiều trigger phá phạm vi/giả định | **Không thể giữ kết luận bao trùm hiện tại** mà không reassess. |
| **Review process** | Ticket được gắn INFO chưa test/owner | **Chưa hoàn tất review** và cần xử lý theo priority. |

Bài tập cho thấy **một thay đổi có thể ảnh hưởng đồng thời nhiều assurance claims** và một missing sensor có thể che cả failure kỹ thuật lẫn lỗi báo cáo. Phải giữ tách biệt event, evidence, rủi ro, verdict và action.

## 23. Sai lầm phổ biến khi thiết kế Rà soát theo sự kiện

| Sai lầm | Hậu quả | Khắc phục |
|---|---|---|
| Coi mọi log event là một review bắt buộc. | Alert fatigue, queue quá tải, bỏ mất rủi ro thật. | Trigger catalog có risk semantics, correlation và sampling phù hợp. |
| Coi mọi trigger là control FAIL. | Báo sai, phá niềm tin vào assurance. | Đánh giá effective state và tiêu chí trước verdict. |
| Chỉ theo dõi event CI/CD. | Manual drift, vendor changes và IAM console thay đổi bị bỏ sót. | Kết hợp runtime audit, inventory và reconciliation. |
| Báo không có event là an toàn. | Collector mất quyền hoặc telemetry im lặng không bị nhận ra. | Heartbeat, source health, synthetic tests, negative cases. |
| Dùng ảnh trạng thái từ tháng trước làm evidence cho hôm nay. | Snapshot không còn đại diện sau thay đổi. | Freshness/version, kiểm chứng lại khi trigger tới. |
| Không có asset inventory độc lập. | Không biết population; phạm vi thiếu account/region. | Reconcile source inventories và ghi coverage. |
| Dedup theo tên alert nhưng bỏ mất scope. | Hai resource khác nhau bị gộp, finding bị che. | Fingerprint có source, resource, event semantics và version. |
| Giả định event delivery đúng thứ tự. | Review state cũ như state mới, quyết định sai. | Query effective state, sequence/version, event-time handling. |
| Đếm ticket mở là bằng chứng đã review. | Không có test, verdict hoặc reviewer. | State machine với evidence gate. |
| Không tách FAIL và INCONCLUSIVE. | Data gap bị xem là control failure hoặc PASS. | Tiêu chí rõ, source validation và remediate evidence pipeline. |
| Auto-remediate mọi drift. | Hoàn tác emergency containment hoặc gây outage. | Policy/authority checks, action risk, runbook, rollback. |
| Không xét điều kiện kiến trúc/assumptions. | Claim cũ vẫn hiển thị PASS dù trust boundary đổi. | Map triggers tới claim assumptions và backing. |
| Dùng risk acceptance để biến FAIL thành PASS. | Mất tính trung thực và có thể bỏ nghĩa vụ bên ngoài. | Tách control verdict, decision, exception, legal applicability. |
| Chỉ đo tốc độ xử lý event nhận được. | Không biết event bị mất hoặc trigger không bao phủ. | Missed-trigger tests, reconciliation và source health. |
| Xóa lịch sử sau fix. | Không biết control thiếu trong khoảng nào, khó audit. | Versioned review, incident/finding links và timeline. |
| Giữ mọi event chứa PII và secrets vô hạn. | Tăng rủi ro lộ dữ liệu. | Data minimization, RBAC, redaction và retention policy. |
| Không có owner cho review. | Queue stale, SLO không ai chịu trách nhiệm. | RACI, escalation, backlog monitoring. |
| Không tái kiểm tra sau mitigation. | Ticket đóng nhưng control vẫn không hiệu lực. | Independent retest và effective-state evidence. |

## 24. Checklist thiết kế và kiểm toán Event-driven review

Trước khi coi cơ chế rà soát theo sự kiện đủ bảo đảm, hãy kiểm tra:

1. **Mục tiêu:** Có security objectives/claims nào cần duy trì sau mỗi thay đổi quan trọng?
2. **Mapping:** Trigger có liên kết control ID, risk scenario, scope và evidence expected?
3. **Catalog:** Có loại event, nguồn, predicate, version, owner, priority và action?
4. **Coverage:** Mọi cloud accounts, identities, services, regions và vendor dependencies trong phạm vi có nguồn tín hiệu?
5. **Source trust:** Event có xác thực nguồn, event ID, schema và timestamps đáng tin?
6. **Pipeline resilience:** Có xử lý mất event, duplicate, out-of-order, retries, backpressure và schema drift?
7. **Health evidence:** Heartbeat, synthetic tests và reconciliation có phát hiện được collector tắt?
8. **Scoping:** Inventory, effective state và blast radius đã được đối chiếu tại lúc review?
9. **Risk triage:** Priority phản ánh data/asset criticality, exposure, threat và obligations?
10. **Evidence collection:** Raw/derived artifacts có provenance, completeness, integrity, access control và retention?
11. **Evaluation:** Test/criteria có đúng claim, risk objective và kỳ, không chỉ là alert label?
12. **Verdict:** PASS/FAIL/INCONCLUSIVE/NOT_APPLICABLE có được dùng đúng và giới hạn scope?
13. **Authority:** Có người chịu trách nhiệm review, ra quyết định và thực thi action?
14. **Safe automation:** Auto-actions có least privilege, allowlist, stop/rollback và emergency-aware logic?
15. **Incident integration:** Khi trigger nghi vấn tấn công, có đường IR nhanh mà không bỏ audit evidence?
16. **Change/release integration:** Artifact/scope drift có kích hoạt reapproval hoặc post-change verification?
17. **Exceptions:** Hết hạn, scope drift và mitigations lỗi có buộc reassessment đúng quyền?
18. **Remediation:** Finding có owner, deadline, root cause, control retest và sign-off?
19. **Time semantics:** Có event_time, observed_time, review_time, decision_time và gap history?
20. **Historical integrity:** Kết luận cũ, rule version, evidence và quyết định có được giữ khi sửa?
21. **Metrics:** Có review SLO, pending/overdue, source health, missed triggers và data-quality gaps?
22. **Continuous improvement:** Có replay/negative tests, root-cause analysis và điều chỉnh trigger catalog có kiểm soát?

### Câu hỏi tự đánh giá

Một tổ chức có posture scanner quét hạ tầng mỗi 10 phút. Trong tuần không có cảnh báo critical, nên dashboard kết luận “toàn bộ production security controls bảo đảm liên tục”. Tuy nhiên, một cloud account mới đã được tạo nhưng chưa vào inventory, quyền collector chỉ đọc được hai trong ba regions, và chưa kiểm thử synthetic audit event trong tháng.

**Nhận định “được bảo đảm liên tục” có đủ bằng chứng không?**

**Gợi ý:** Không. Tần suất scanner 10 phút chỉ là **cadence của nguồn quan sát**; chưa chứng minh population coverage, collector permissions hoặc logging pipeline. Cần reconcile account/regions với nguồn độc lập, kiểm tra API pagination và quyền đọc, thực hiện test event an toàn từ nguồn tới SIEM, xác định các claims chưa đánh giá và ghi **INCONCLUSIVE/coverage gap**. Sau khi sửa nguồn, mới review theo scope/kỳ thực sự quan sát; kết luận quá khứ không được biến thành PASS hồi tố.

**Rà soát theo sự kiện có giá trị trong continuous security assurance khi mỗi thay đổi quan trọng được liên kết tới đúng claim và rủi ro, tín hiệu được kiểm tra nguồn và phạm vi, bằng chứng mới được thu và đánh giá theo tiêu chí, quyết định có người chịu trách nhiệm và finding được retest trước khi đóng. Continuous assurance không có nghĩa tuyên bố “luôn an toàn”, mà là duy trì khả năng nhận ra nhanh khi một kết luận cũ cần được kiểm chứng lại — với lịch sử, giới hạn và bằng chứng minh bạch.**
