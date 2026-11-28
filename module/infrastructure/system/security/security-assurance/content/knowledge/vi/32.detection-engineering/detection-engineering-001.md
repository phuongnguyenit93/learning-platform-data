# Detection là gì? Nền tảng Detection Engineering và Security Assurance

## 1. Bài toán: “Không có cảnh báo” có nghĩa hệ thống an toàn?

Giả sử một nền tảng Invoice SaaS đã triển khai MFA, phân quyền theo tenant, mã hóa dữ liệu và kiểm thử bảo mật. Trong một ca trực, dashboard SOC không phát sinh cảnh báo nào. Ban quản lý hỏi: “Có thể kết luận không có hoạt động tấn công trong 24 giờ vừa qua không?”

**Không thể kết luận như vậy chỉ từ số cảnh báo bằng 0.** Có ít nhất ba khả năng: (1) không có hành vi nguy hiểm trong phạm vi theo dõi; (2) có hành vi nhưng không nằm trong các giả thuyết detection đã triển khai; (3) hành vi xảy ra nhưng telemetry không được tạo, thu thập, xử lý hoặc khớp logic detection. Một nguồn log chết hoặc một rule bị tắt cũng có thể tạo dashboard “xanh” giả.

**Detection trong an ninh mạng** là hoạt động sử dụng tín hiệu và bằng chứng từ hệ thống để **nhận diện những hành vi, trạng thái hoặc chuỗi sự kiện có khả năng liên quan một mối đe dọa hoặc vi phạm security requirement**, từ đó tạo ra một kết quả đánh giá có thể được kiểm tra, ưu tiên và chuyển tới quy trình điều tra/ứng phó thích hợp.

**Detection engineering** là quá trình kỹ thuật hóa điều đó: thiết kế giả thuyết, xác định dữ liệu cần thu, xây dựng logic, kiểm thử, triển khai, theo dõi chất lượng, cải tiến và ngừng sử dụng các detections không còn phù hợp. Đối tượng cần bảo đảm không chỉ là **rule có tồn tại** mà là **khả năng phát hiện có hiệu lực trong phạm vi được công bố**.

Trong module `SECURITY_SECURITY_ASSURANCE`, mục tiêu là đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật, từ rủi ro, yêu cầu và controls tới kiểm thử, audit, khắc phục phát hiện và security assurance liên tục. Detection đóng vai trò **detective control**, đồng thời cung cấp bằng chứng vận hành để nhận biết prevention controls có thể đã bị vượt qua, cấu hình bị thay đổi hoặc giả định threat model không còn đúng.

> Detection tốt không đồng nghĩa “càng nhiều alert càng tốt”; nó giúp người có trách nhiệm nhận đúng tín hiệu quan trọng, đủ nhanh, đủ bối cảnh và đủ bằng chứng để quyết định.

### Ví dụ xuyên suốt

Bài dùng Invoice SaaS giả định với Java/Spring Boot API, PostgreSQL, cloud IAM, Kubernetes, export workers, object storage và SIEM/SOC. Các events, rules, paths, IDs và kết quả kiểm thử trong ví dụ là **dữ liệu minh họa hoặc synthetic**, không phải kết quả thực từ production.

## 2. Bản chất của detection: giả thuyết, quan sát và quyết định

Detection có thể mô hình hóa khái niệm:

\[
\text{Detection result}
= f(\text{observations},\ \text{context},\ \text{logic},\ \text{time window},\ \text{data quality})
\]

Trong đó:

- **Observations:** events, metrics, state changes, network flows và các dữ liệu khác.
- **Context:** asset, role, user, tenant, environment, business operation và authorized behavior.
- **Logic:** điều kiện, phép tương quan, ngưỡng, state machine hoặc mô hình thống kê.
- **Time window:** khoảng thời gian event xảy ra, được nhận hoặc được đánh giá.
- **Data quality:** completeness, provenance, freshness, identity mapping và sensor health.

### Một detection không trực tiếp nhìn thấy “ý định”

Hệ thống thấy “user A bị từ chối truy cập invoice B” hoặc “một service role mới được grant quyền đọc storage”. Nó **không trực tiếp thấy** người đó là attacker hay chỉ là automation/operations hợp lệ. Detection logic đưa ra một **phán đoán có điều kiện**: hành vi này đủ khác thường hoặc đủ vi phạm policy để cần xử lý.

### Detection có thể sai theo hai hướng

**False positive:** cảnh báo về hoạt động không thực sự đáp ứng định nghĩa rủi ro đã đặt.

**False negative:** hoạt động đáp ứng định nghĩa cần phát hiện nhưng không tạo tín hiệu/cảnh báo như mong đợi.

Một finding cũng có thể là **inconclusive** nếu dữ liệu thiếu hoặc ngữ cảnh chưa đủ. Đừng ép mọi trường hợp về hai nhãn “attack” và “benign”.

### Kết quả là đầu vào cho hành động, không tự là kết luận cuối

Một alert có thể dẫn đến triage, case, incident hoặc no-action có lý do. Detection không thay người điều tra, hành động của SOC hoặc thẩm quyền chấp nhận residual risk.

## 3. Từ raw data tới security incident: phân biệt các thuật ngữ

| Thuật ngữ | Định nghĩa vận dụng | Ví dụ Invoice SaaS |
| --- | --- | --- |
| **Telemetry** | Dòng dữ liệu hệ thống tạo/thu để quan sát hoạt động. | HTTP logs, audit events, auth decisions, cloud trail. |
| **Event** | Một sự kiện có thời gian/nguồn/đối tượng và thuộc tính. | `invoice.read.denied` lúc T bởi principal A. |
| **Signal** | Dấu hiệu có ý nghĩa cho một giả thuyết rủi ro. | A có nhiều denied cross-tenant reads trong một cửa sổ. |
| **Indicator** | Dấu vết/đặc trưng cụ thể, có thể kèm ngữ cảnh. | Repeated new admin grants ngoài change window. |
| **Detection analytic/rule** | Logic ánh xạ dữ liệu và điều kiện thành outcome. | Join role-grant audit và approved changes trong 10 phút. |
| **Detection hit/match** | Event/nhóm events thỏa rule. | Một match threshold hoặc policy violation. |
| **Alert** | Thông báo/đối tượng xử lý được sinh từ match theo routing policy. | High-priority access anomaly tới SOC queue. |
| **Finding** | Đánh giá có evidence về một vấn đề/đặc tính bảo mật. | Control telemetry không hoạt động trên một worker. |
| **Case** | Hồ sơ điều tra tập hợp alerts, evidence, hành động. | Case về credential misuse có nhiều observations. |
| **Security incident** | Sự kiện/tình huống được phân loại theo incident process. | Đã xác minh tài khoản bị lạm dụng và data exposure. |
| **Response** | Containment, investigation, remediation, recovery theo thẩm quyền. | Thu hồi token, khóa phiên và kiểm tra exposure. |

### Không đánh đồng event và alert

Một service có thể tạo hàng triệu events/ngày nhưng chỉ một phần phù hợp một detection. Một alert có thể tổng hợp nhiều events hoặc nhiều signals. Ngược lại, một event bị thiếu có thể làm cả một correlation rule không bao giờ match.

### Incident không tự được tạo vì severity “Critical”

Severity của một rule có thể phản ánh rủi ro giả định; incident classification cần **evidence, scope, impact và quy trình**. Một benign canary đúng rule có thể sinh alert Critical nhưng không phải một cuộc tấn công thật.

## 4. Detection, prevention, monitoring và response khác nhau thế nào?

| Nhóm | Câu hỏi | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| **Preventive control** | Ngăn hành vi trái phép trước khi gây tác động? | Server-side tenant authorization, IAM deny. | Có thể bị bypass hoặc sai cấu hình. |
| **Detective control** | Nhận diện điều đáng ngờ/vi phạm cần điều tra? | Alert quyền IAM thay đổi ngoài change. | Có thể đến sau tác động hoặc bỏ sót. |
| **Monitoring/observability** | Hệ thống đang vận hành ra sao? | API latency, logs, metrics, traces. | Không mặc nhiên có security hypothesis. |
| **Responsive control** | Giới hạn, điều tra, xử lý sự kiện? | Revoke credential, isolate workload. | Phải được quyền/điều kiện an toàn cho phép. |
| **Corrective/recovery control** | Sửa nguyên nhân, khôi phục trạng thái tin cậy? | Fix authz, rebuild host, restore backup. | Không thay chứng minh sự cố đã được phát hiện. |

### Security logging không đồng nghĩa detection

“Chúng ta đã bật audit logs” là một bước thu thập, không tự tạo logic đánh giá. Cần **source health, parser, correlation, detection rule, alert routing và hành động**.

### SIEM không tự bảo đảm detection

Một hệ thống quản lý logs và analytics có thể hỗ trợ detection, nhưng cài SIEM mà không có data mapping/rules/tests không chứng minh đạt security objective. Cũng có detections ngay tại EDR, gateway, application hoặc cloud control plane chứ không nhất thiết đi qua một SIEM trung tâm.

### Không dùng detection để bù mọi prevention gap

Một API cho phép user A đọc Confidential invoice của tenant B là **vi phạm authorization** cần sửa. Alert cho các reads này là defense-in-depth và điều tra, **không thay yêu cầu chặn truy cập**.

## 5. Detection engineering giải quyết vấn đề kinh doanh nào?

Detection nên bảo vệ **asset và business capability quan trọng**, không chạy theo tên rule hấp dẫn.

| Business asset | Threat/action cần phát hiện | Lý do ưu tiên |
| --- | --- | --- |
| **Invoice records** | Cross-tenant denied access bursts, unusual bulk reads/exports. | Confidentiality và tenant isolation. |
| **Payment approval** | State transition/admin override ngoài policy. | Transaction integrity và fraud risk. |
| **Identity/session** | Suspicious privilege grant, revoked token use, session anomalies. | Account takeover và authorization. |
| **Storage exports** | Unexpected public policy, high-volume retrieval, expired link misuse. | Data disclosure. |
| **Cloud/Kubernetes** | Privileged role grant, new exposed route, policy disable. | Control-plane compromise, blast radius. |
| **Build pipeline** | Unauthorized signing/deploy identity use, unapproved artifact. | Supply-chain integrity. |
| **Security telemetry** | Audit collector stopped, source silent, parser failures. | Mất khả năng chứng minh detection hoạt động. |
| **Recovery** | Backup policy changed, key access modified, restore failure. | Availability và resilience. |

### Không phải mọi dấu hiệu phải alert ngay

Một thay đổi được phê duyệt có thể chỉ cần audit; một thay đổi IAM cực kỳ nhạy cảm ngoài maintenance window có thể cần high-priority alert; một anomaly thống kê yếu có thể chỉ đưa vào hunting. **Priority và action** phải theo attacker capability, exposure, impact và confidence.

## 6. Scope của detection: “phát hiện điều gì, ở đâu, khi nào?”

Mọi claim detection nên mô tả ít nhất:

- **Threat/behavior:** đối thủ hoặc hành vi vi phạm nào được xét?
- **Asset/data:** dịch vụ, endpoint, tenant, identity, resource hoặc host nào được bảo vệ?
- **Viewpoint:** external, authenticated low-privilege, privileged insider, compromised workload?
- **Environment:** production, staging, DR, cloud account, cluster, region, API version.
- **Observation path:** application events, identity logs, cloud audit, EDR, network telemetry.
- **Time:** window, source delay, ingestion lag, data retention và as-of period.
- **Decision:** alert/not-alert, severity, dedup, routing, thresholds và exceptions.
- **Evidence:** nguồn, identity, version, test result, limitations.

### Một câu claim quá rộng

“SOC phát hiện mọi hành vi truy cập trái phép.” Đây là claim gần như không thể chứng minh bằng một rule hoặc tập tests có giới hạn.

### Một claim kiểm chứng được

“Đối với các Invoice API endpoints thuộc release R và tenants A/B trong môi trường test có cấu hình tương đương, khi một user phát sinh nhiều lần truy cập bị từ chối tới synthetic invoice khác tenant trong cửa sổ W, pipeline thu đủ events và sinh alert có actor/tenant/resource category trong độ trễ tối đa đã duyệt.”

Claim thứ hai có **data, logic, actor, expected behavior, time window và scope** để thử nghiệm.

## 7. Phân biệt detection coverage với attack coverage

Một detection có thể quan sát event `authorization.denied`; nhưng nếu một endpoint bỏ hoàn toàn authorization và **cho phép** đọc dữ liệu trái tenant, có thể không có denied event nào. Rule hoạt động đúng nhưng threat bị bỏ sót vì **khác loại behavior**.

### Các mức coverage

| Level | Câu hỏi |
| --- | --- |
| **Asset coverage** | Host/services/tenants nào sinh telemetry? |
| **Data coverage** | Field/event types nào được tạo/thu/parse đầy đủ? |
| **Technique coverage** | Những behavior/threat hypotheses nào có analytics liên quan? |
| **Path coverage** | Các API versions, alternative routes, async workers và control-plane actions có được nhìn? |
| **Test coverage** | Những scenarios nào được verify với fixtures và expected outcomes? |
| **Response coverage** | Alerts có owner, runbook và kết quả triage không? |
| **Time coverage** | Trạng thái hoạt động trong ca trực, sau deploy, khi source down hoặc maintenance? |

### Không lấy số rules làm mẫu số

“Có 500 rules” không cho biết chúng có bao phủ payment fraud, BOLA hay cloud admin grant trên assets quan trọng không. Một analytic có chất lượng và đúng telemetry path có thể đóng góp nhiều hơn 50 rules trùng nhau.

## 8. Threat-informed detection: bắt đầu từ giả thuyết

Detection use case cần một mối nối từ **threat model/security requirement** tới điều kiện quan sát.

### Cấu trúc một hypothesis

1. **Threat actor capability:** user hợp lệ hoặc attacker có token bị lộ?
2. **Objective:** đọc invoice ngoài tenant hoặc tạo export trái phép?
3. **Behavior sequence:** loại API actions hay policy changes nào có thể xảy ra?
4. **Observable consequence:** event/status nào phản ánh hành vi, ở lớp nào?
5. **Required telemetry:** fields, tenant/actor mapping, source và parser.
6. **Detection logic:** ngưỡng, correlation, context, exclusions hợp lệ.
7. **Expected alert:** entity, severity, evidence và routing.
8. **Known blind spots:** authorization bypass không log deny, async paths, data loss.

### Hai giả thuyết dễ bị nhầm

**H-01:** “Một actor cố đọc nhiều invoice của tenant khác nhưng bị server từ chối.” Có thể cần detection trên access-denied bursts.

**H-02:** “Một lỗi BOLA làm actor đọc được invoice của tenant khác.” Đây có thể cần **cross-tenant access invariant check**, query/audit correlation hoặc runtime security tests; chỉ quan sát deny không đủ.

### Dùng các framework như ATT&CK đúng vai trò

Một bộ phân loại behavior/technique có thể giúp đội chọn hypothesis và trao đổi coverage. Nhưng **gắn nhãn tactic/technique vào rule không chứng minh rule phát hiện được technique đó**. Cần data sources, valid tests và version/scope rõ.

## 9. Từ hypothesis tới data contract

Một detection không thể hoạt động đáng tin nếu dữ liệu tối thiểu không tồn tại hoặc được diễn giải không thống nhất.

### Các trường thường cần

| Trường | Vai trò | Lỗi thường gặp |
| --- | --- | --- |
| **event_type** | Định danh hành động/security decision. | Tên event thay mà parser/rule không đổi. |
| **event_time** | Thời điểm xảy ra tại nguồn. | Host clock sai, timezone/precision khác. |
| **ingest_time** | Thời điểm collector nhận. | Nhầm ingest lag với attacker timeline. |
| **source/service** | Sự kiện xuất phát từ đâu. | Thiếu region/instance/route attribution. |
| **actor_id** | Principal thực hành action. | Dùng email dễ thay đổi hoặc untrusted user field. |
| **actor_type/role** | Người dùng/service/admin và quyền. | Role lấy từ client-supplied request. |
| **tenant_id** | Ranh giới tenancy. | Mapping khác qua API/worker/DB hoặc thiếu. |
| **resource_type/id** | Protected object được tác động. | Dump ID/data nhạy cảm không cần thiết. |
| **action** | Read/update/export/grant/delete. | Trùng event names nhưng semantics khác. |
| **decision/outcome** | Allow/deny/failure và lý do cấp cao. | HTTP 200 bị hiểu là authorization ALLOW. |
| **correlation_id** | Liên kết API→queue→worker→storage. | Mỗi hop tạo ID không thể join. |
| **auth_context** | Session assurance, token/client class. | Ghi raw tokens thay vì metadata. |
| **deployment_id** | Version/region/ring của code và policy. | Alert không biết route cũ. |
| **schema_version** | Kiểm soát compatibility với parser/rules. | Silent field rename. |

### Không đưa raw secrets/PII vào event chỉ để đủ context

Detection thường cần **actor reference, data class, outcome, correlation** hơn là nội dung hóa đơn, passwords, tokens hoặc raw request bodies. Sử dụng pseudonymous IDs/approved references với access controls phù hợp.

### Schema evolution là một security event

Nếu team đổi `principal_id` thành `actor_id` mà parser vẫn đọc field cũ, analytic có thể tiếp tục chạy “thành công” nhưng không phát hiện được gì. Cần **contract tests, version migration, missing-field metrics và canary detection**.

## 10. Detection pipeline: từ hệ thống nguồn đến người ứng phó

~~~mermaid
flowchart LR
    A["Applications / IAM / hosts / cloud audit"] --> B["Event generation"]
    B --> C["Collection / transport"]
    C --> D["Parsing, normalization, enrichment"]
    D --> E["Time-window correlation / detection analytics"]
    E --> F["Dedup, risk scoring and alert routing"]
    F --> G["SOC triage / case management"]
    G --> H["Containment / remediation / recovery"]
    I["Asset inventory, threat model and policy"] --> D
    I --> E
    J["Source health and synthetic canaries"] --> C
    J --> E
    H --> K["Lessons learned and tuning"]
    K --> E
~~~

### Điểm có thể mất dữ liệu

- Source không ghi event hoặc ghi sai security decision.
- Agent/collector bị disable, thiếu quyền hoặc không nhận version mới.
- Queue/transport drop, duplicate, out-of-order hoặc trễ.
- Parser làm mất fields, mapping user/tenant sai.
- Enrichment source stale, identity resolution mismatch.
- Detection rule bị disable, filter/suppression quá rộng.
- Alert routing lỗi hoặc queue quá tải, không có owner.
- Case/response không liên kết evidence và không biết action.

### Vì sao đây là assurance problem?

Một ảnh chụp “rule enabled” chỉ kiểm một điểm trong pipeline. Để kết luận khả năng detection hoạt động, cần **end-to-end evidence**: tạo canary hợp lệ tại nguồn → collector/normalization → rule match → alert → SOC nhận trong expected window.

## 11. Dữ liệu nguồn có thể phục vụ detection

| Data source | Behavior quan sát | Giới hạn điển hình |
| --- | --- | --- |
| **Application security audit** | Authorization decisions, sensitive business transitions. | Thiếu events ở code paths cũ/async, không chuẩn hóa. |
| **Identity/IdP** | Login, MFA, account recovery, token/session events. | Không thấy resource-level authorization trong app. |
| **Cloud control-plane audit** | IAM grants, instance/storage/network policy changes. | Không thấy full in-guest process behavior. |
| **Host/EDR** | Process, local privilege, binary/service changes. | Agent coverage, tamper/compatibility, sparse metadata. |
| **Network flow/DNS** | Destinations, connection patterns, egress changes. | Encrypted payload/identity semantics có thể thiếu. |
| **API gateway/WAF** | HTTP routes, ingress auth, denial, request metadata. | Direct origin/backend routes không qua gateway. |
| **Database audit** | DB principal/query category/privilege activity. | App-level actor/tenant mapping có thể thiếu. |
| **Storage audit** | Object reads/writes, policy changes, link access. | Có thể chậm hoặc không gắn principal business. |
| **Container/Kubernetes audit** | Pod/security policy changes, exec/role actions. | Managed control-plane logging phạm vi tùy provider. |
| **CI/CD/Supply chain** | Runner/signing/deploy identity and artifact changes. | Không bao phủ runtime misuse sau deploy. |
| **Business transaction logs** | Approval workflow, export volume, refund anomaly. | Không được chứa PII quá mức, cần semantics. |

### Không có một nguồn log “tốt nhất” cho mọi threat

Một cloud IAM role grant thường thấy trong cloud audit; một invoice bị đọc sai tenant cần application authorization/data access evidence; một suspicious process cần endpoint telemetry. **Source selection phải theo observable behavior**, không phải chọn SIEM table nào nhiều records nhất.

## 12. Data quality và “health của detector”

Detection có thể coi là một control có nhiều phụ thuộc: sensors, collection, parsing, analytics, routing, analyst workflows. Cần kiểm **sức khỏe từng mắt xích**.

### Những chỉ số cần theo dõi

1. **Expected source coverage:** bao nhiêu eligible hosts/services/tenants có source.
2. **Event generation rate:** theo asset class, business volume, giờ trong ngày.
3. **Field presence:** event_type, actor, decision, tenant và correlation đúng schema.
4. **Timestamp quality:** offset, event-time vs ingest-time, late-arrival.
5. **Transport reliability:** drop/retry/backpressure/dead-letter events.
6. **Parser health:** parse failures, unknown schema versions, mapping errors.
7. **Enrichment freshness:** asset/identity/tenant registry có mới và consistent.
8. **Rule execution:** enabled, version, schedule, latency, failed queries.
9. **Match/alert generation:** canary hits và routing path.
10. **SOC delivery:** ticket/queue nhận đúng priority, owner và acknowledgement.

### “0 events” có nhiều ý nghĩa

Có thể dịch vụ không hoạt động, không có traffic, collector mất quyền, filter chặn hết, parser drop hoặc retention/query sai. **Data absence không mặc nhiên là absence of threat**.

### Canary source health

Một benign test action có unique synthetic marker/correlation ID, sinh theo lịch hoặc sau deployment, giúp xác minh event đến analytics và alert đúng điều kiện. Nếu canary không đến, đánh dấu **INCONCLUSIVE/UNKNOWN**, không tự đưa rule vào danh sách PASS.

## 13. Các kiểu detection và trường hợp phù hợp

Không có một kỹ thuật detection duy nhất áp dụng cho mọi loại hành vi.

| Kiểu | Nguyên lý | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| **Signature/indicator matching** | So event với một đặc trưng đã biết. | Credential identifier đã bị revoke vẫn xuất hiện trong allowed use. | Dễ bỏ behavior không khớp signature; indicator có thể lỗi thời. |
| **Policy/invariant detection** | Quan sát violation của security/business requirement. | Một non-admin được cấp platform-admin role. | Phải xác định trusted policy và exception semantics. |
| **Threshold** | Đếm/tính tổng số events trong window. | N denied cross-tenant reads/10 phút. | Legitimate bulk workflow có thể gây noise; slow behaviors có thể bỏ sót. |
| **Correlation** | Ghép nhiều nguồn/steps bằng entity/time. | New IAM grant gần thời điểm object store policy được mở. | Chất lượng join, timestamps và late events ảnh hưởng mạnh. |
| **Sequence/state-machine** | Phát hiện chuỗi hay transition bất hợp lệ. | Refund `PAID` không qua approval được phép. | Thiếu event bước giữa tạo false conclusion. |
| **Anomaly/outlier** | So với baseline thống kê/hành vi thường thấy. | Export volume tăng bất thường theo tenant tier. | “Bất thường” không tự là “xấu”; baseline drift, seasonality. |
| **Behavioral/graph** | Quan hệ actor–host–resource–action theo mẫu. | Một identity mới tạo role và đọc secrets trên nhiều assets. | Complexity, entity resolution và explainability. |
| **Risk-based correlation** | Kết hợp asset criticality, behavior, context và confidence. | Same action ưu tiên khác trên signing host so với test pod. | Risk weights cần calibration và governance. |
| **Hunting hypothesis** | Analyst chủ động tìm evidence chưa có production alert ổn định. | Review unusual support access trong kỳ. | Coverage/latency có thể không đáp ứng realtime detection. |

### Detection theo policy đôi khi đáng tin hơn anomaly

Ví dụ “mọi grant platform administrator phải đi qua approved change” có thể được kiểm soát bằng **đối chiếu audit event với approval register**, không cần mô hình machine learning. Nếu policy rõ, dữ liệu đầy đủ và mapping tốt, detection này dễ giải thích và retest.

### Anomaly không tự là incident

Một tenant export nhiều invoices cuối tháng có thể hoàn toàn hợp lệ. Thay vì alert dựa vào con số thô, cần **business calendar, tenant size, actor role, operation class và approved bulk jobs**; đồng thời tránh suppress toàn bộ hành vi xấu chỉ vì activity lặp lại.

## 14. Ngưỡng, cửa sổ thời gian và tính đúng của detector

Một analytic dạng threshold cần có **đơn vị đếm, khóa nhóm, cửa sổ, cập nhật thời gian và dữ liệu đến muộn**.

### Những lựa chọn làm thay đổi ý nghĩa

- **Group by actor:** một account gửi request bất thường.
- **Group by tenant:** nhiều accounts cùng một tenant phối hợp.
- **Group by source IP/device:** nhiều accounts dùng cùng nguồn, nhưng NAT/proxy có thể gây nhầm.
- **Group by resource:** một invoice bị nhiều actors truy cập.
- **Event-time window:** dựa vào thời điểm hành vi thực sự xảy ra.
- **Processing-time window:** dựa vào lúc analytic nhìn thấy event.
- **Tumbling/sliding/session windows:** có thể tạo số hits và latency khác nhau.
- **Threshold + minimum diversity:** số lần deny cao và số distinct resources cao.
- **Dedup/suppression:** tránh hàng trăm alerts cho cùng một campaign.

### Ví dụ minh họa

Rule: “Cảnh báo khi cùng một actor có ít nhất 8 lần bị từ chối đọc từ ít nhất 5 invoice IDs trong 10 phút.” Đây chỉ là **ngưỡng giáo dục**; phải hiệu chỉnh bằng dữ liệu hợp lệ, expected workload và risk tier, không xem là industry default.

### Event-time vs ingest-time

Giả sử collector mất mạng 15 phút rồi gửi lại 20 events một lượt. Nếu rule xử lý theo ingest-time và coi tất cả trong một phút, có thể gây burst alert giả hoặc làm mất sequence. Cần định nghĩa **allowed lateness, backfill/replay handling, ordering, event dedup** và cách gắn watermark theo nền tảng.

### False negative từ lỗi join key

Nếu `actor_id` thay đổi giữa API gateway và app (email ở edge, subject ID ở app), correlation có thể chia một actor thành nhiều entities. Trường **normalized_actor_id** phải được tạo bằng mapping được quản trị và giữ source provenance để có thể kiểm lại.

## 15. Entity resolution: identity, tenant, host và resource

Một rule ghép events từ nhiều nơi phải biết “cùng một entity” là gì.

| Entity | Stable reference mong muốn | Nguy cơ mapping sai |
| --- | --- | --- |
| **Human principal** | Verified subject/issuer + tenant binding. | Hai IdPs có cùng email bị gộp sai. |
| **Service identity** | Workload principal, trust domain, role/session. | Role name giống nhau ở hai cloud accounts. |
| **Host** | Instance/node/resource ID + validity interval. | IP/hostname được reuse sau rebuild. |
| **Pod/container** | Pod UID/container ID + cluster/namespace. | Pod name được tái sử dụng khi restart. |
| **Business resource** | Object type, stable ID, tenant/owner mapping. | Client-supplied tenant ID không tin cậy. |
| **Session** | Session reference/fingerprint không phải token thô. | Không phân biệt reused/rotated session. |
| **Cloud action** | Account, region, principal, API action, resource. | Dùng display name thay immutable role/resource ID. |

### Privacy và correlation có thể đồng thời đạt

Không cần ghi nguyên email, IP đầy đủ hoặc nội dung invoice ở mọi event. Có thể dùng **pseudonymous stable references** trong scope đã quản trị, giới hạn khả năng re-identification và quyền truy cập theo data classification.

### Không gán nhãn độc hại từ enrichment lỗi thời

User đã chuyển role nhưng enrichment cache còn gọi người đó là Admin. Rule dựa vào role có thể định tuyến severity sai. Cần **event-time authorization context** khi có, temporal validity của enrichment và các flags “context missing/stale”.

## 16. Vòng đời Detection Engineering

~~~mermaid
flowchart TD
    A["Threat/security requirement + risk context"] --> B["Detection hypothesis and use-case design"]
    B --> C["Data source and field-contract assessment"]
    C --> D["Rule / analytic implementation"]
    D --> E["Benign fixtures, negative and regression tests"]
    E --> F["Review, approve and version detection"]
    F --> G["Deploy to selected environment / tenants"]
    G --> H["Observe canary, health, alert and triage outcomes"]
    H --> I{"Effective and useful?"}
    I -- "Yes" --> J["Operate and continuously reassess"]
    I -- "False alerts / blind spots" --> K["Tune logic, data, enrichment or routing"]
    I -- "No longer relevant" --> L["Retire with documented decision"]
    K --> D
    J --> B
    L --> M["Archive provenance and historical evidence"]
~~~

### Mỗi pha cần deliverable

| Pha | Đầu ra |
| --- | --- |
| **Threat selection** | Protected asset, risk, attacker viewpoint, hypothesis. |
| **Data readiness** | Source owner, schema contract, expected completeness/freshness. |
| **Design** | Logic, time-window, entity key, severity/routing, limitations. |
| **Implementation** | Versioned query/rule, parser/enrichment dependencies. |
| **Validation** | Positive/negative fixtures, test IDs, expected and observed alerts. |
| **Deployment** | Approved change, environment/tenant scope, rule version and enabled state. |
| **Operation** | Source health, alert quality, triage feedback, missed-event analysis. |
| **Improvement** | Retuning, additional data, rule split/merge, updated runbook. |
| **Retirement** | Justification, owner, replacement/coverage mapping and rollback plan. |

### “Done” không phải “rule đã merge”

Một rule trong Git chưa được enable trong production, hoặc enable nhưng parser thiếu data, **chưa đạt operating effectiveness**. Vòng đời phải đi tới **observed canary/alert delivery và SOC acknowledgement** với đúng release/scope.

## 17. Detection use case specification: phải mô tả điều gì?

Một use case có thể được ghi trong Detection Catalog:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **Use-case ID/name** | Định danh duy nhất, purpose không mơ hồ. |
| **Security objective/threat** | Rủi ro cần nhìn thấy, requirement và business impact. |
| **Assumptions** | Authz enforced? Log source đủ? Actor ID trusted? |
| **Scope** | Environment, cluster, tenants, APIs, versions, population. |
| **Data contract** | Event types/required fields/schema versions/retention. |
| **Analytic logic** | Predicate, correlation keys, windows, thresholds. |
| **Expected outcome** | Khi nào alert; khi nào không alert. |
| **Priority/risk semantics** | Asset criticality, actor capability, impact, confidence. |
| **Known blind spots** | Missing API paths, late events, lack of DB/worker logs. |
| **False-positive sources** | Approved bulk jobs, maintenance, synthetic load tests. |
| **Owner/reviewer** | Engineer, data owner, SOC, service owner, risk authority. |
| **Test plan** | Synthetic fixtures, negative tests, canary, source failure tests. |
| **Runbook** | Triage questions, initial containment authorization, escalation. |
| **Evidence** | Code/version, source health, rule matches, alert/case trace. |
| **Change/expiry** | Ruleset version, exceptions, review cadence, reassessment triggers. |

### Use case tốt phải có điều kiện **không cảnh báo**

Nếu chỉ có positive condition, rule rất dễ gây false positives. Ví dụ: một authorized test account tạo ba denied events **dưới threshold** nên không tạo High alert; một approved migration job có đủ context có thể được ghi audit nhưng không tạo incident alert; một unknown source không được **silent PASS**.

## 18. Mô hình các lớp detector trên cùng một sự kiện

Giả sử một user thuộc tenant A liên tục cố đọc invoice B:

1. **Preventive:** server-side object authorization từ chối yêu cầu.
2. **Source event:** app ghi `invoice.read.authorization_denied` với actor/tenant/object type và correlation ID.
3. **Threshold detector:** nhiều denies trong W phút tạo signal.
4. **Context enrichment:** actor role, asset sensitivity, whether legitimate workflow retry.
5. **Routing:** alert tới queue có owner, kèm minimal evidence refs.
6. **Triage:** kiểm account activity, sessions, API version và potential misconfiguration.
7. **Response:** có thể khóa session hoặc yêu cầu owner review khi evidence/thẩm quyền đủ.
8. **Security assurance:** chứng minh từ test canary tới alert, đồng thời đánh giá false negatives.

### Một detection nên được thử ở ít nhất hai mức

**Logic test:** với event fixtures, rule có match đúng khi điều kiện thỏa và không match khi điều kiện chưa thỏa?

**End-to-end test:** ứng dụng có sinh đúng event trên endpoint thực, collector có nhận, parser có chuẩn hóa, rule có chạy và alert có đến nơi đúng trong SLA?

Nếu chỉ test logic trên CSV tự tạo, chưa có bằng chứng rằng **production sources** đang sinh events giống CSV.

## 19. Ví dụ Java/Spring Boot: tạo security event có cấu trúc

Event tốt cần xuất phát từ **server-trusted security decision**, không lấy `tenantId` trong HTTP header rồi xem như danh tính đã xác minh.

### DTO và interface phát sự kiện

~~~java
package example.invoice.assurance;

import java.time.Instant;
import java.util.UUID;

public record AuthorizationAuditEvent(
    String schemaVersion,
    String eventType,
    Instant eventTime,
    String service,
    String verifiedActorId,
    String verifiedTenantId,
    String resourceType,
    String resourceReference,
    String action,
    String decision,
    String reasonCategory,
    UUID correlationId,
    String deploymentId
) {}

public interface SecurityAuditPublisher {
    void publish(AuthorizationAuditEvent event);
}
~~~

### Nơi sinh event trong service

~~~java
package example.invoice.assurance;

import java.time.Clock;
import java.util.UUID;

public final class InvoiceAuthorizationService {
    private final InvoiceRepository invoices;
    private final SecurityAuditPublisher events;
    private final Clock clock;
    private final String deploymentId;

    public InvoiceAuthorizationService(
            InvoiceRepository invoices,
            SecurityAuditPublisher events,
            Clock clock,
            String deploymentId) {
        this.invoices = invoices;
        this.events = events;
        this.clock = clock;
        this.deploymentId = deploymentId;
    }

    public boolean canRead(
            VerifiedPrincipal principal,
            UUID invoiceId,
            UUID correlationId) {
        boolean permitted = principal != null
            && principal.mayReadInvoices()
            && invoices.belongsToTenant(
                invoiceId, principal.verifiedTenantId());

        // References are approved synthetic/opaque IDs, not raw PII.
        events.publish(new AuthorizationAuditEvent(
            "1.0",
            "invoice.read.authorization_decision",
            clock.instant(),
            "invoice-api",
            principal == null ? "anonymous" : principal.auditSubject(),
            principal == null ? "none" : principal.verifiedTenantId(),
            "invoice",
            invoiceId.toString(),
            "READ",
            permitted ? "ALLOW" : "DENY",
            permitted ? "POLICY_ALLOWED" : "NOT_AUTHORIZED",
            correlationId,
            deploymentId
        ));
        return permitted;
    }
}
~~~

`InvoiceRepository`, `VerifiedPrincipal` và `SecurityAuditPublisher` là các **interfaces/types khái niệm phải được hiện thực, xác thực và kiểm thử** trong ứng dụng thật. Đoạn mã minh họa event contract, không tự cung cấp authorization framework hoàn chỉnh; entrypoint phải từ chối request khi `canRead` trả false. Trong thực tế phải xử lý errors/timeouts của event publishing theo **safe failure policy**, tránh để lỗi logging tạo đường fail-open hoặc mất giao dịch không được quản trị.

### Các giới hạn cần xem

- `belongsToTenant` phải an toàn với thiếu object, tenant spoofing và DB errors; ví dụ đơn giản không xử lý mọi error paths.
- Không dùng raw request body/Authorization header làm actor; principal phải verified.
- Khi logging thất bại, cần định nghĩa **audit-loss handling và compensating queue/retry**, không im lặng cho rằng có event.
- Trên high-volume path, synchronous logging có thể làm tăng latency; chọn delivery design theo threat/SLO và durability.
- Authorization tại API không thay kiểm ở worker/cache/download nếu các đường đó có access riêng.
- Không log toàn bộ invoice content hoặc credentials.

## 20. JSON event minh họa và data-quality contract

~~~json
{
  "schema_version": "1.0",
  "event_type": "invoice.read.authorization_decision",
  "event_time": "2026-11-28T03:00:00Z",
  "source": {
    "service": "invoice-api",
    "environment": "sandbox",
    "region": "region-example",
    "deployment_id": "invoice-api-R-example",
    "instance_id": "api-pod-example"
  },
  "actor": {
    "subject_ref": "synthetic-user-a",
    "identity_class": "tenant_user",
    "tenant_ref": "synthetic-tenant-a",
    "role": "Viewer"
  },
  "resource": {
    "type": "invoice",
    "reference": "synthetic-invoice-b",
    "tenant_ref": "synthetic-tenant-b",
    "classification": "CONFIDENTIAL"
  },
  "action": "READ",
  "decision": "DENY",
  "reason_category": "CROSS_TENANT_POLICY",
  "correlation_id": "example-correlation-001",
  "request_path_class": "invoice-detail",
  "contains_secret_values": false
}
~~~

### Không để event trở thành lời khẳng định không có nguồn

Trong mã thực, thông tin `resource.tenant_ref` phải đến từ authoritative lookup/security decision, không phải từ untrusted request payload. Nếu app **không biết resource tenant** khi từ chối vì object không tồn tại, nên ghi unknown/none thay vì đoán là cross-tenant. Event mẫu trên giả định có dữ liệu synthetic authoritative tương ứng.

### Schema tests cần kiểm

**Required fields, enum semantics, source identity, timestamp precision, cardinality, version changes, masking và correlation**. Nếu event thiếu actor, detector theo actor phải báo data-quality gap, không tự nhóm mọi requests vào `unknown` rồi tạo một alert chung gây nhiễu.

## 21. Ví dụ detection logic với SQL-style analytics

Mẫu dưới đây mô tả một **windowed query cho dữ liệu đã chuẩn hóa**, không phải query production tùy ý. Giả định bảng `security_events` có các field từ schema, `:window_end` và ngưỡng do policy cung cấp.

~~~sql
-- Illustrative PostgreSQL-style logic over synthetic events.
-- A scheduled runner must manage windows, late events, dedup,
-- tenant/actor identity validity and alert delivery separately.
SELECT
    actor_id,
    actor_tenant_id,
    COUNT(*) AS denied_count,
    COUNT(DISTINCT resource_ref) AS distinct_invoices,
    MIN(event_time) AS first_seen,
    MAX(event_time) AS last_seen
FROM security_events
WHERE event_type = 'invoice.read.authorization_decision'
  AND decision = 'DENY'
  AND resource_type = 'invoice'
  AND environment = 'production'
  AND data_quality = 'VALID'
  AND event_time > (:window_end - INTERVAL '10 minutes')
  AND event_time <= :window_end
GROUP BY actor_id, actor_tenant_id
HAVING COUNT(*) >= 8
   AND COUNT(DISTINCT resource_ref) >= 5;
~~~

### Điều query **không** làm

- Không chứng minh các events đã đến đầy đủ hoặc `actor_id` không bị sai.
- Không phát hiện BOLA khi truy cập bị **allow trái policy**, vì chỉ lọc DENY.
- Không làm **dedup/late-event handling**, enrichment, alert routing hoặc exception management.
- Không phân biệt tester đang kiểm authorized sandbox với attacker thực nếu không có context.
- Không chứng minh 8/5/10 phút là ngưỡng phù hợp; cần baseline, cost và retest.

### Nâng cấp cần thiết

Có thể thêm verified actor role, tenant/resource classification, trusted maintenance context và correlation với authentication changes. Nhưng thêm càng nhiều joins thì **data completeness và semantics** càng quan trọng; phải ghi các assumptions vào use-case spec.

## 22. Ví dụ detection-as-code: một rule specification

Detection-as-code có nghĩa version hóa logic, metadata, tests và quy trình triển khai như một thành phần được review. Ví dụ YAML dưới là **định dạng minh họa của tổ chức**, **không phải cú pháp chính thức của một SIEM hoặc Sigma có thể chạy ngay**.

~~~yaml
schema_version: "1.0"
kind: "detection_analytic_example"
detection_id: "DET-INVOICE-DENIED-BURST-001"
title: "Repeated denied invoice reads by an actor"
status: "ILLUSTRATIVE_NOT_DEPLOYED"
scope:
  service: "invoice-api"
  environment: "production"
  data_sources:
    - "application-security-audit"
  schema_versions:
    - "1.0"
security_context:
  objective: "Detect suspicious resource access attempts"
  threat_hypothesis: >
    A principal may repeatedly attempt to access invoice
    resources outside its approved scope.
  related_requirement: "REQ-TENANT-OBJECT-AUTHZ"
required_fields:
  - "event_type"
  - "event_time"
  - "actor_id"
  - "actor_tenant_id"
  - "resource_ref"
  - "decision"
logic:
  filter:
    event_type: "invoice.read.authorization_decision"
    decision: "DENY"
  group_by:
    - "actor_id"
    - "actor_tenant_id"
  window: "10m"
  minimum_events: 8
  minimum_distinct_resource_refs: 5
  note: "Thresholds are examples, not production defaults"
outputs:
  severity: "CONTEXT_DEPENDENT"
  route_to: "SOC-application-queue"
  include_raw_credentials: false
validation:
  required_tests:
    - "DE-T01"
    - "DE-T02"
    - "DE-T06"
    - "DE-T16"
  require_end_to_end_canary: true
  on_missing_source: "UNKNOWN_NOT_PASS"
owners:
  engineer: "Detection Engineering"
  data: "Invoice Application Team"
  triage: "SOC"
reassessment_triggers:
  - "new-api-version"
  - "audit-schema-change"
  - "tenant-identity-mapping-change"
  - "parser-change"
  - "high-noise-or-missed-detection"
~~~

### Logic đúng chưa đủ nếu thiếu deployment evidence

Rule trong Git có thể PASS tests offline nhưng chưa được enable ở đúng tenant/region, hoặc rule production đang ở version cũ. Cần **commit/rule digest, deployment scope, enabled state, observed run, source health và canary-to-alert evidence**.

## 23. Precision, recall, specificity và false-alarm economics

Để định lượng detector, trước hết cần **tập ground truth** gồm scenarios được xác minh. Định nghĩa:

| | Hành vi thực sự đáp ứng positive class | Hành vi thực sự thuộc negative class |
| --- | --- | --- |
| **Detector báo positive** | True Positive (TP) | False Positive (FP) |
| **Detector báo negative** | False Negative (FN) | True Negative (TN) |

Các công thức thường dùng:

\[
\operatorname{Precision}=\frac{TP}{TP+FP},\qquad
\operatorname{Recall}=\frac{TP}{TP+FN}
\]

\[
\operatorname{FPR}=\frac{FP}{FP+TN},\qquad
\operatorname{Specificity}=\frac{TN}{TN+FP}
\]

Ví dụ trong **tập kiểm thử gán nhãn đã định nghĩa**, giả định TP = 60, FP = 20, FN = 10, TN = 910:

- Precision = 60/80 = **75%**.
- Recall = 60/70 ≈ **85,7%**.
- False Positive Rate = 20/930 ≈ **2,15%**.

Đây **không phải** chỉ số của hệ thống thật và không suy ra trực tiếp từ số alerts production. Ground truth trong thực tế khó xác định: missed cases không tự xuất hiện trong backlog.

### Base-rate problem

Khi malicious behaviors hiếm, ngay cả detector có low FPR vẫn có thể sinh nhiều false alerts so với true alerts. Nếu SOC chỉ tối ưu “nhạy nhất”, analyst bị ngập và thời gian xử lý các alert quan trọng tăng.

### Không dùng một metric duy nhất

Precision cao nhờ chỉ alert một hành vi cực hiếm có thể bỏ phần lớn threat population (recall thấp). Recall cao nhờ alert mọi request làm precision giảm mạnh. Phải xét **criticality, miss cost, analyst capacity, response action** và confidence của ground truth.

### Tránh suy Recall = 100% vì không có incident

Không có confirmed misses không chứng minh FN = 0. Muốn đánh giá recall tương đối cần **controlled test cases, adversarial simulation được ủy quyền, historical labeled datasets hoặc independent review** và ghi sampling bias.

## 24. Tuning, exclusions và suppression có ranh giới

Tuning giúp giảm noise, nhưng mỗi lần thay threshold, filter hay suppression có thể làm tăng false negatives.

### Ba trường hợp phải tách

1. **False-positive disposition:** evidence chứng minh observation là benign theo định nghĩa rule.
2. **Approved exception:** behavior đáng cảnh báo nhưng risk được chấp nhận trong time/scope có thẩm quyền.
3. **Suppression/tuning:** đổi analytic hoặc routing để giảm hits, cần chứng minh không che critical threat.

### Ví dụ hợp lệ

Một migration batch account được phép đọc nhiều invoices trong khoảng maintenance window. Có thể phân loại bằng **trusted change ID, owner, exact service identity, window và expected resource class**, không suppress toàn bộ `invoice.export` từ mọi user.

### Những suppression nguy hiểm

- Bỏ qua mọi alerts từ “internal IP range” dù attacker có thể ở mạng nội bộ.
- Whitelist nguyên cloud account hoặc role quá rộng vì một maintenance job.
- Suppress theo username dễ thay/reuse.
- Tắt rule vô thời hạn sau vài false positives mà không có owner/expiry.
- Đổi threshold cho pipeline pass mà không đánh giá missed attacks.

### Quy trình tuning tốt

**Collect labeled feedback → identify root cause (bad event/data, rule semantics, legitimate workflow) → propose narrow change → regression test positive/negative sets → review/approve → deploy version → monitor canary/noise/misses → rollback if needed.**

Ghi rationale và **rule diff**, không chỉ “giảm 90% alerts” vì con số đó cũng có thể do source bị tắt.

## 25. Kiểm thử detection: unit, integration và end-to-end

Một rule cần có các lớp kiểm thử khác nhau để tránh kết luận sai:

| Test level | Input | Điều chứng minh | Không chứng minh |
| --- | --- | --- | --- |
| **Schema/contract** | Synthetic structured events. | Fields, enum, parsing và validation contract. | Source production thực sự tạo đủ events. |
| **Unit analytic** | Labeled event fixtures. | Logic threshold/filter/correlation theo giả định. | Collector/transport/SIEM delivery. |
| **Regression** | Bộ positive/negative fixtures trước đây. | Rule change không làm lỗi những cases đã biết. | Không có blind spots ngoài fixtures. |
| **Integration** | Source→parser→analytic trong test pipeline. | Một số thành phần tích hợp đúng. | Production routes/identities/regions giống test. |
| **End-to-end canary** | Authorized synthetic action tại business source. | Event được sinh, nhận, match, alert routed trong scope. | Mọi attack variants đều phát hiện. |
| **Adversarial validation** | Controlled threat emulation trong sandbox, có RoE. | Behavior/hypothesis chọn có được nhìn thấy trong điều kiện thực. | Detection tất cả kỹ thuật hoặc environment khác. |
| **Failure-mode** | Collector loss, delay, malformed event, parser change. | Alert/evidence-health behavior khi phụ thuộc hỏng. | System sẽ tự hồi phục trong mọi sự cố. |
| **Operational drill** | SOC nhận một alert test đã được xác định. | Triage/runbook/ownership/SLA quan sát được. | Containment production luôn thành công. |

### Positive và negative cùng quan trọng

Nếu chỉ tạo fixture đủ 8 denied events thì rule match là expected, nhưng còn phải thử 7 events, 8 events chỉ trên 2 objects, actor khác, tenant khác, ngoài window, duplicates và events thiếu trường để chứng minh rule không quá rộng.

### Canary không được gây hại

Dùng **synthetic principal/resource, sandbox hoặc môi trường production được phê duyệt có giới hạn**, canary marker riêng và quan sát downstream. Không tạo credential misuse thật, bulk exfiltration hoặc phá availability để “kiểm detection”. Các bài test nguy hiểm cần separate authorization, safe method và incident contact theo RoE.

## 26. Detection test fixtures phải có ground truth

Một bộ fixtures nên lưu **security hypothesis, expected output, reason**, thay vì chỉ vài events không có nhãn.

| Fixture | Nội dung | Expected |
| --- | --- | --- |
| **F-01** | Một actor có 8 denied reads, 5 resources, trong 10 phút. | MATCH với rule minh họa. |
| **F-02** | Cùng actor chỉ 7 denied reads, 5 resources. | Không match threshold. |
| **F-03** | 8 denies nhưng chỉ 2 distinct resources. | Không match diversity condition. |
| **F-04** | 8 denies được chia cho hai actors, 4 mỗi actor. | Không match per-actor rule. |
| **F-05** | Events từ hai tenants không được gộp sai actor/tenant key. | Independent grouping. |
| **F-06** | Events giống nhau được replay với event IDs giữ nguyên. | Không tạo count giả nếu dedup contract quy định. |
| **F-07** | Một số events đến muộn nhưng event_time vẫn trong window. | Xử lý theo documented lateness policy. |
| **F-08** | Missing actor_id trong một event. | Quarantine/data-quality signal, không silently counted. |
| **F-09** | Source dừng gửi events. | Source-health UNKNOWN/FAIL, không “detector PASS”. |
| **F-10** | Benign approved migration tạo pattern giống rule. | Alert/classification phù hợp exception chính xác và time bound. |
| **F-11** | One allowed cross-tenant read trái policy trong synthetic data. | Phải có complementary detection/test, denied-only rule không đủ. |
| **F-12** | Parser/schema version mới đổi field. | Contract validation phát hiện drift trước production silent failure. |

### Cẩn thận khi định nghĩa duplicate

Hai HTTP requests hợp lệ có thể có cùng actor/resource/action/time gần nhau nhưng **không phải duplicates**. Idempotency/dedup phải dựa vào **trusted event identifier/source semantics**, không dùng fuzzy key quá rộng làm mất tín hiệu.

### Test corpus cần được version hóa

Gắn fixtures và expected results với rule version, schema version và evaluation engine. Khi một rule được tuning, kiểm lại những cases trước đây để biết **trường hợp nào đổi outcome và vì sao**.

## 27. Phân tích false negative: thiếu rule hay thiếu tín hiệu?

False negative không phải lúc nào cũng do rule viết sai:

1. **Source absence:** endpoint cũ không sinh event.
2. **Collection gap:** collector không có quyền đọc một cloud account.
3. **Transport loss:** queue drop khi backpressure, retries hết hạn.
4. **Parsing mismatch:** event đổi schema, field mới bị bỏ.
5. **Wrong identity join:** actor IDs giữa API/IdP/worker không thống nhất.
6. **Late arrival:** event đến ngoài evaluation window.
7. **Threshold issue:** behavior dưới ngưỡng hoặc phân tán qua entities.
8. **Suppression bug:** exception/suppress quá rộng.
9. **Rule disable/version drift:** production không chạy cùng rule đã test.
10. **Alert routing failure:** analytic match nhưng alert không tới SOC.
11. **Unmodeled threat behavior:** attacker đi qua success path không sinh deny.
12. **Tampering:** compromised actor sửa/disable sensors hoặc xóa logs trước ship.

### Phân lớp nguyên nhân

| Layer | Test bổ sung |
| --- | --- |
| Source | App/business behavior test + event generation assertion. |
| Collection | Expected source inventory, canary, agent permissions. |
| Parser | Schema conformance tests, invalid-field alerts. |
| Analytic | Labeled fixtures, positive/negative threshold tests. |
| Context | Identity/asset enrichment validity, temporal mappings. |
| Routing | Test alert delivery, queue/ticket health. |
| Response | SOC drill, owner acknowledgement, escalation. |

### Đừng “fix rule” khi nguyên nhân ở data

Tăng độ nhạy của threshold không giúp nếu service không tạo log. Ngược lại, thêm mọi field vào log không giải quyết analytic sai semantics và có thể làm lộ dữ liệu nhạy cảm. Tìm **failing layer** trước.

## 28. Source health và trường hợp pipeline mất khả năng quan sát

Một chương trình detection trưởng thành cần detect **mất khả năng detection** như một security control failure.

### Các tín hiệu sức khỏe cần có

- Expected heartbeat và valid event volume theo active source population.
- Parser error rate và missing required fields.
- Ingestion lag, queue backlog, dropped/duplicate data.
- Rule execution schedule/last success và query errors.
- Deployed rule version, enabled status và last known canary pass.
- Destination queue/ticket/notification health.
- Time synchronization và identity mapping freshness.
- Telemetry retention/access constraints.

### Khi không có events, hỏi hai câu

**Nguồn có được kỳ vọng sinh events trong thời gian đó không?** Nếu có, xem source generation/transport. **Nếu không có activity**, source-health canary/heartbeat độc lập có thể xác minh connection nhưng không tự chứng minh mọi event type hoạt động.

### Fail-open/closed trong detection operations

Pipeline detection thường không nên chặn mọi business transaction chỉ vì SIEM tạm lỗi — trừ các security-critical audit semantics được thiết kế có chủ đích. Tuy nhiên việc mất audit trên một privileged operation có thể đòi **reject, queue durably, degrade, manual approval hoặc escalation** theo threat/risk/SLO.

Không dùng “log failure never blocks anything” như mặc định vĩnh viễn; cũng không tự kill production khi collector lỗi. Xác định **safe failure contract** cho từng control.

### Source health cũng cần độc lập

Một agent trên host bị compromise có thể giả healthy. Với critical assets, dùng các nguồn tương đối độc lập như cloud audit, gateway logging, app events và receiver-side liveness/canaries; nêu rõ assumptions về tính đáng tin.

## 29. Detection latency và giới hạn thời gian

Người dùng có thể kỳ vọng detection “gần thời gian thực”, nhưng độ trễ thực tế có nhiều phần:

\[
L_{\text{end-to-end}} =
L_{\text{generate}}+
L_{\text{collect}}+
L_{\text{transport}}+
L_{\text{parse}}+
L_{\text{evaluate}}+
L_{\text{route}}
\]

Đây là mô hình cộng đơn giản; trong kiến trúc song song và batch, cần đo observed end-to-end thay vì chỉ cộng số cấu hình.

### Những mốc thời gian phải phân biệt

- **Event time:** action xảy ra tại source.
- **Collection time:** agent nhận event.
- **Ingestion time:** pipeline nhận.
- **Rule evaluation time:** analytic chạy/match.
- **Alert delivery time:** SOC queue nhận.
- **Acknowledgement/triage time:** analyst mở và đánh giá.
- **Containment time:** action giảm exposure có hiệu lực.

### MTTD nghĩa là gì?

Các tổ chức dùng *Mean Time to Detect* theo định nghĩa khác nhau (từ initial compromise, first observable behavior hay first event). Mọi metric phải ghi **start/end event definitions, cohort, timestamp confidence, sample và censored/unknown cases**. Không so MTTD của hai hệ thống nếu chúng đo hai thời điểm bắt đầu khác nhau.

### Lateness và clock drift

Một host lệch giờ có thể làm latency tính âm hoặc một chuỗi events bị sắp sai. Cần NTP/time source health, event-time/receive-time provenance và chính sách xử lý events đến muộn.

## 30. Alert enrichment và triage: detection cần dẫn tới quyết định

Một alert có thể đúng logic nhưng không hữu ích nếu SOC không biết tài sản hay hành vi nào quan trọng.

### Minimum context cho alert

| Field | Giá trị |
| --- | --- |
| **Detection ID/version** | Biết rule nào match, test/routing version nào. |
| **Security hypothesis** | Vì sao cần điều tra, requirement liên quan. |
| **Time interval** | First/last seen, event vs ingest timestamps. |
| **Actor/asset references** | Trusted principal, host, tenant/resource category. |
| **Observed behavior** | Event count, distinct objects, sequence, decision. |
| **Risk signals** | Business asset criticality, privileged actor, data class. |
| **Confidence/quality** | Missing fields, stale enrichment, source-health status. |
| **Evidence references** | Truy được raw redacted events và provenance. |
| **Suggested triage** | Xác minh identity, approved change, asset state, customer impact. |
| **Owner/escalation** | SOC queue, service contact, incident criteria. |

### Hai câu hỏi của triage

**Detection match có đúng theo dữ liệu và logic không?** Sau đó: **behavior có thực sự đáng ngờ/vi phạm policy trong business context không?** Một rule match đúng có thể dẫn tới benign disposition; một alert không match expected có thể là detection defect.

### Không tự động xử lý quá mức

Tự động khóa account, cô lập host hoặc revoke IAM role có thể gây outage hay làm mất forensic evidence. Cần **authorization, confidence threshold, false-positive cost, rollback, safe stop và SOC ownership** trước khi tự động hóa containment.

## 31. Detection và incident response kết nối ra sao?

Detection nên có **runbook** chứ không chỉ tên rule và mức severity.

### Runbook cho denied cross-tenant burst

1. **Verify alert:** rule/version, event quality, unique actor/tenant và test marker.
2. **Assess legitimacy:** approved test/migration, unusual client retry, support case.
3. **Scope behavior:** API routes/versions, number of distinct resources, session and identity changes.
4. **Check preventive effectiveness:** tất cả requests bị DENY hay có ALLOW sai policy?
5. **Check data exposure:** synthetic examples, authorized query/audit with data minimization; tránh bulk customer data.
6. **Review associated signals:** auth anomalies, role grants, export jobs, storage access, cloud changes.
7. **Classify:** benign, false positive, suspicious, confirmed incident hoặc insufficient evidence.
8. **Escalate:** account/service owner, SOC lead, privacy/incident team nếu cần.
9. **Contain and recover:** theo thẩm quyền; rotate/revoke, patch policy, preserve evidence.
10. **Feed back:** update detection logic, security requirement, source coverage, test corpus.

### Detection quality phụ thuộc response outcome

Một detector có precision tốt nhưng alert được gửi tới một queue không ai theo dõi có **operating effectiveness thấp đối với mục tiêu response**. Do đó đánh giá cần cả **delivery, owner, acknowledgement, triage correctness, escalation**.

### Detection không tạo quyền điều tra vô hạn

SOC cần tuân data minimization, role-based access và incident legal/privacy requirements. Một alert không tự cho phép truy cập mọi mailbox, tenant hoặc dữ liệu khách hàng.

## 32. Detection-as-code và change governance

Một detection nên được quản lý như software có ảnh hưởng bảo mật:

- Rule source/version, reviewers, change approval.
- Dependency schema/parser/source contracts và data owners.
- Test fixtures positive/negative, canary results, regression history.
- Deployment target và feature rollout scope.
- Suppression/exception/threshold metadata.
- Alert route/runbook và responsible SOC team.
- Kill-switch/rollback và incident handling khi detector gây overload.
- Audit trail về enable/disable, query/logic edits và privileged users.
- Reassessment triggers khi threat, API, platform hoặc business model đổi.

### Các loại thay đổi khác nhau

**Rule logic update** cần test analytic. **Event schema change** cần producer/consumer contract tests. **Routing change** cần alert-delivery test. **New environment/tenant enablement** cần source inventory và canary. **Suppression change** cần test false-negative side effects.

### CI green không là production detection PASS

Rule YAML đã qua lint và offline fixtures nhưng runtime engine có syntax/runtime difference hoặc query bị disabled. Kết luận operating phải dựa **deployed rule identity + successful execution + end-to-end canary + SOC delivery**.

## 33. Detection review: design effectiveness và operating effectiveness

Security assurance thường phân biệt hai tầng:

**Design effectiveness:** giả thuyết có phù hợp threat? Rule đặt đúng observation point? Data sources có khả năng tạo evidence cần? Threshold và exceptions hợp lý? Đã cân nhắc false negatives?

**Operating effectiveness:** events có thực sự sinh/thu đúng? Rules có chạy trên expected population? Canary có match và alert đến SOC đúng window? Analyst có nhận/điều tra? Mất nguồn có bị phát hiện?

| Evidence | Hỗ trợ điều gì? | Không hỗ trợ điều gì? |
| --- | --- | --- |
| Threat/use-case document | Lý do và design scope. | Production đang chạy. |
| Rule source trong Git | Intended logic/version. | Rule enabled/effective. |
| Offline unit tests | Logic trên fixtures. | Production event generation. |
| Collection coverage report | Sources registered/reported. | All required events delivered. |
| Runtime rule execution status | Analytic chạy không lỗi. | Correct output trên threats chưa có data. |
| End-to-end benign canary | Một test path được phát hiện và routed. | Mọi variants/regions đều đạt. |
| Incident case | Ability to investigate một scenario. | Zero missed incidents. |
| Independent evidence challenge | Confidence/contradictions có thể kiểm. | Bảo đảm tuyệt đối mọi future events. |

### Khả năng detection có phạm vi và kỳ

“Use case DET-X effective trong release R, telemetry population P, evaluation window T” là dạng claim có thể kiểm. Không viết “detector will always detect every attacker” hoặc “SOC hoàn toàn an toàn” từ một test.

## 34. Claim–Argument–Evidence (CAE) cho detection

### Claim mẫu

> “Đối với các Invoice API services, API versions và tenant cohorts trong population P của release R, use case DET-INVOICE-DENIED-BURST-001 có nguồn telemetry hợp lệ, analytics đang chạy đúng policy, phát hiện các synthetic denied-access sequences đạt ngưỡng và chuyển alert tới SOC trong cửa sổ SLA đã phê duyệt; exceptions và blind spots được ghi riêng.”

### Argument cần chứng minh

1. **Risk relevance:** threat hypothesis có business/security objective và attacker capability rõ.
2. **Complete applicable scope:** đúng sources, API versions, environments, asset population.
3. **Data quality:** field contract, timestamps, actor/tenant mapping và collectors đáp ứng.
4. **Logic correctness:** unit positive/negative fixtures và threshold behavior đúng.
5. **Runtime deployment:** rule version, enabled state, schedule, parser/mapping đồng nhất.
6. **End-to-end effectiveness:** canary action tạo event, match, alert, SOC receive.
7. **Operations:** runbook, on-call ownership, triage và escalation hoạt động.
8. **Risk transparency:** false negatives, untested paths, exceptions, data gaps được công bố.
9. **Reassessment:** change/incident/schema/source health triggers dẫn tới retest.

### CAE evidence matrix

| Assertion | Evidence phù hợp | Phản chứng/giới hạn |
| --- | --- | --- |
| Use case phù hợp threat. | Approved threat model, requirement và asset risk. | Attack path khác ngoài chosen observable. |
| Source đầy đủ. | Independent service inventory, source health, valid event volume. | Unregistered API v1 có thể bị bỏ. |
| Schema chính xác. | Contract tests, parser output, missing-field metrics. | Event semantic sai dù field hợp lệ. |
| Logic correct. | Positive/negative fixtures, replay, reviewed rule diff. | Fixtures không đại diện real traffic. |
| Deployed đúng scope. | Runtime version/tenant/region mapping và execution status. | Một rule enabled ở staging không áp production. |
| Canary được phát hiện. | Source event ID → normalized event → match → alert/ticket ID. | Chỉ một behavior/window đã thử. |
| SOC có hành động. | Receipt/acknowledgement, runbook exercise, case decision. | Real incident complexity có thể khác test. |
| Source outage bị phát hiện. | Collector failure canary, health alert, unknown status. | Sensor compromise có thể giả mạo healthy. |
| Risk được quản trị. | Finding/exception owners, expiry, remediation retest. | Accepted risk không phải control PASS. |

### Evidence phản bác

Nếu CI cho thấy rule enabled nhưng production collector không nhận events của API v1, claim “đã bao phủ mọi Invoice APIs” bị bác bỏ hoặc chỉ đạt PARTIAL. Nếu canary sinh event nhưng alert queue không nhận, **logic match PASS nhưng end-to-end detection FAIL**; không cộng hai trạng thái thành PASS chung.

## 35. Bảo mật, quyền riêng tư và độ tin cậy của detection data

Detection system thường là kho dữ liệu nhạy cảm: user IDs, hostnames, access paths, account roles, customer metadata, internal architecture và findings chưa khắc phục.

### Bảo vệ event/data pipeline

1. **Data minimization:** chỉ ghi fields hỗ trợ hypothesis, investigation và policy.
2. **Sensitive fields:** che/mã hóa/hạn quyền đối với PII, credentials, secrets và invoice data.
3. **Least-privilege ingestion:** agents có quyền chỉ gửi đúng data, không tự đọc mọi tenant table.
4. **Collection integrity:** trusted source identities, transport protection, audit trail.
5. **Storage access:** SOC analysts được quyền theo role/purpose, không public dashboards chứa raw telemetry.
6. **Retention:** đủ incident/regulatory purposes, có deletion/hold policy.
7. **Cross-border/vendor:** đánh giá nơi provider/SIEM lưu hoặc xử lý event data.
8. **Tamper resistance:** host/app compromise có thể xóa/chỉnh logs; cần remote/immutable evidence khi phù hợp.
9. **Availability:** pipeline lỗi có backlog/retry và source health signal.
10. **Audit-of-audit:** ai đã thay rule, đọc dữ liệu hoặc disable alert?

### Nhiều log hơn không luôn tốt hơn

Logging raw Authorization header, tokens, passwords, payment details hoặc toàn bộ invoice contents chỉ để “có bằng chứng” có thể tạo secondary data breach. **Có đủ context không đồng nghĩa thu tất cả dữ liệu**.

### Integrity hash không đủ

Hash của log chứng minh bytes sau thu không đổi so với reference được giữ, nhưng không chứng minh nguồn thu không bị compromise hoặc event không bị bỏ trước khi gửi. Critical claims có thể cần **independent controls, event canaries, remote append-only logging và provenance**.

## 36. Monitoring source health là một detection use case riêng

Ví dụ use case `DET-TELEMETRY-GAP-001` được thiết kế để phát hiện khi critical source không còn tạo valid events.

### Giả thuyết

“Trong production active hosts/services, việc mất security audit source vượt quá SLA làm tổ chức không thể phát hiện/điều tra một số threats, ngay cả khi không có attacker behavior trực tiếp.”

### Điều kiện cần

- Independent list of expected active assets.
- Source-to-asset mapping và event class required.
- Expected heartbeat/canary hoặc traffic-aware minimum volume.
- Ingestion health và last-seen time.
- Maintenance/approved shutdown/decommission info.
- Account/collector permissions, parser errors, clock quality.

### Outcome

**HEALTHY:** required canary và source metadata đạt trong valid window.

**DEGRADED:** source còn nhưng event classes thiếu, lag cao hoặc parser errors tăng.

**UNKNOWN:** chưa biết asset population hoặc thiếu health evidence.

**FAILED:** control không đáp ứng defined freshness/completeness threshold trong scope.

### Đừng cảnh báo vì nguồn đã nghỉ hợp lệ

Host bị decommission đúng thủ tục không còn phải gửi heartbeats; dịch vụ có traffic bằng không có thể vẫn healthy nếu canary/telemetry contract phù hợp. Cần **asset lifecycle và maintenance context** để giảm noise mà không giấu source outage thực.

## 37. Java/JUnit: kiểm tra logic detection mà không kích hoạt tấn công thật

Ví dụ sau chỉ dùng **synthetic authorization events**. Mục tiêu kiểm đúng điều kiện actor+tenant, number of denies, distinct resources và time window. Nó là **unit-level detector**, chưa bao gồm event dedup transport, late arrivals, source integrity hay SOC routing.

~~~java
package example.assurance.detection;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

public final class DeniedReadDetector {
    public record AuditEvent(
        String eventId,
        String actorId,
        String tenantId,
        String resourceRef,
        String decision,
        Instant occurredAt) {}

    public boolean matches(
            List<AuditEvent> events,
            String verifiedActor,
            String verifiedTenant,
            Instant endTime) {
        Instant start = endTime.minus(Duration.ofMinutes(10));

        // Illustrative dedup by a trusted unique event ID.
        Set<String> seenIds = new java.util.HashSet<>();
        List<AuditEvent> valid = events.stream()
            .filter(e -> e != null)
            .filter(e -> e.eventId() != null && !e.eventId().isBlank())
            .filter(e -> e.resourceRef() != null
                && !e.resourceRef().isBlank())
            .filter(e -> e.occurredAt() != null)
            .filter(e -> verifiedActor.equals(e.actorId()))
            .filter(e -> verifiedTenant.equals(e.tenantId()))
            .filter(e -> "DENY".equals(e.decision()))
            .filter(e -> e.occurredAt().isAfter(start))
            .filter(e -> !e.occurredAt().isAfter(endTime))
            .filter(e -> seenIds.add(e.eventId()))
            .toList();

        long uniqueResources = valid.stream()
            .map(AuditEvent::resourceRef)
            .filter(ref -> ref != null && !ref.isBlank())
            .collect(Collectors.toSet())
            .size();

        return valid.size() >= 8 && uniqueResources >= 5;
    }
}
~~~

Ví dụ dùng Java **16+ record và Java 16+ `Stream.toList()`** (khả năng hỗ trợ theo phiên bản cụ thể), không tự thích hợp cho Java 8/11. Đoạn `seenIds.add` có side effect trong stream: ở ví dụ tuần tự này có thể chạy, nhưng nên **thiết kế bước dedup rõ ràng và deterministic** ở implementation production, tránh dùng stateful stream predicates trong parallel pipeline. `eventId` được giả định trusted/unique theo source contract; kiểm null/schema integrity phải có trước analytic.

### Test cases JUnit minh họa

~~~java
package example.assurance.detection;

import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class DeniedReadDetectorTest {
    private final DeniedReadDetector detector = new DeniedReadDetector();
    private final Instant now = Instant.parse("2026-11-28T03:00:00Z");

    private List<DeniedReadDetector.AuditEvent> fixture(int count) {
        var events = new ArrayList<DeniedReadDetector.AuditEvent>();
        for (int i = 0; i < count; i++) {
            events.add(new DeniedReadDetector.AuditEvent(
                "synthetic-event-" + i, "actor-a", "tenant-a",
                "invoice-" + (i % 5), "DENY", now.minusSeconds(60)));
        }
        return events;
    }

    @Test
    void alertsOnEightDeniesAcrossFiveResources() {
        assertTrue(detector.matches(fixture(8), "actor-a", "tenant-a", now));
    }

    @Test
    void doesNotAlertOnOnlySevenDenies() {
        assertFalse(detector.matches(fixture(7), "actor-a", "tenant-a", now));
    }

    @Test
    void doesNotMixActorOrTenant() {
        var events = fixture(8);
        assertFalse(detector.matches(events, "actor-b", "tenant-a", now));
        assertFalse(detector.matches(events, "actor-a", "tenant-b", now));
    }

    @Test
    void duplicateEventIdsDoNotRaiseCount() {
        var events = fixture(7);
        events.add(events.get(0));
        assertFalse(detector.matches(events, "actor-a", "tenant-a", now));
    }
}
~~~

### Giới hạn phải ghi

Một unit test PASS cho logic không đảm bảo **app sinh event, parser giữ đúng eventId, source clock đúng, deployment enabled hoặc SOC nhận alert**. Nó là lớp evidence thiết yếu nhưng chưa đủ. Đặc biệt đoạn detector không phân biệt `event_type` vì ví dụ đã giả định input chỉ gồm authorization-decision events; nếu dùng stream đa loại phải thêm filter dựa schema tin cậy.

## 38. Ma trận 40 tình huống kiểm thử Detection Engineering

Ma trận giúp reviewer thiết kế **positive, negative, failure-mode, source-health và operational tests**; tất cả phải thực hiện bằng dữ liệu thử/benign canaries theo ủy quyền, không tạo tấn công hoặc phá hủy hệ thống thật.

| Test ID | Kịch bản | Expected outcome/evidence |
| --- | --- | --- |
| **DE-T01** | Synthetic 8 denied reads tới 5 resource IDs trong 10 phút, một actor. | Analytic MATCH đúng. |
| **DE-T02** | Cùng actor chỉ 7 denied reads. | Không tạo threshold alert. |
| **DE-T03** | 8 denies nhưng chỉ 2 distinct resources. | Không MATCH diversity requirement. |
| **DE-T04** | Denies chia đều hai actors, mỗi người dưới ngưỡng. | Không gộp sai actor identity. |
| **DE-T05** | Events từ hai tenants, cùng display name. | Trusted actor+tenant mapping không bị gộp. |
| **DE-T06** | Duplicated transport event với cùng trusted eventId. | Không double-count theo dedup contract. |
| **DE-T07** | Events đến muộn nhưng event_time thuộc window. | Late-data policy được thực thi, không silent loss. |
| **DE-T08** | Host clock lệch, ingest_time khác event_time. | Clock/source quality warning và documented handling. |
| **DE-T09** | Missing actor_id trong input. | Quarantine/data-quality gap, không gộp tất cả vào unknown. |
| **DE-T10** | Parser đổi enum `DENIED` thành `DENY` ngoài contract. | Schema/normalization test FAIL trước silently missing events. |
| **DE-T11** | App route v1 không sinh auth decision event. | End-to-end canary/source completeness FAIL. |
| **DE-T12** | App route v2 sinh event, v1 thiếu. | Báo PARTIAL theo route/version, không global PASS. |
| **DE-T13** | Synthetic invalid invoice ID gây 404 nhưng không authz decision. | Không tự suy BOLA test PASS từ 404. |
| **DE-T14** | Authorized cross-tenant test kiểm trường hợp wrong-tenant resource tồn tại. | Prevention negative test và auth event correlates đúng. |
| **DE-T15** | Một BOLA path trả ALLOW trái tenant policy. | Complementary invariant monitoring/test phát hiện; denied-only rule blind spot. |
| **DE-T16** | Approved source canary đi xuyên collection→SIEM→alert queue. | End-to-end MATCH/receipt trong SLA. |
| **DE-T17** | Collector ngừng nhận source trong sandbox. | Telemetry-gap detector báo UNKNOWN/FAIL. |
| **DE-T18** | Collector có heartbeat nhưng event-type canary không đến. | Phát hiện semantic coverage gap. |
| **DE-T19** | Event schema version mới parser không hiểu. | Parser failure metric/alert và no false PASS. |
| **DE-T20** | Identity enrichment stale sau role revoke. | Context freshness flagged, risk scoring không vô căn cứ. |
| **DE-T21** | Cloud role grant đúng approved change window. | Audit event và routing phù hợp context, không incident giả. |
| **DE-T22** | Privileged role grant ngoài approved window trên synthetic test account. | High-priority signal theo policy và owner. |
| **DE-T23** | Export spike cuối tháng theo approved tenant workflow. | Tuning/triage giảm false positives có rationale. |
| **DE-T24** | Suspicious export volume qua API version khác không thuộc initial rule. | Coverage gap và targeted detector tests. |
| **DE-T25** | Storage public policy drift có cloud event nhưng không có alert. | Cloud-policy use case FAIL/INCONCLUSIVE theo source evidence. |
| **DE-T26** | Audit suppression quá rộng cho internal source IP. | Regression test phát hiện missed expected alert. |
| **DE-T27** | Rule updated trong Git nhưng production vẫn chạy old version. | Deployment provenance/version drift detected. |
| **DE-T28** | Rule engine báo success nhưng không thấy matched fixture. | Logic/data integration FAIL, not blindly healthy. |
| **DE-T29** | Alert match nhưng notification queue không nhận. | Delivery/operational end-to-end FAIL. |
| **DE-T30** | Alert tới queue không có assigned owner. | Case routing/ownership control FAIL. |
| **DE-T31** | SOC nhận benign canary và thực hiện triage runbook. | Acknowledgement, classification, timeline evidence. |
| **DE-T32** | Synthetic alert bị phân loại incident thật do thiếu test marker. | Test governance/labeling defect được xử lý. |
| **DE-T33** | Detection rule bị disable bởi account không được phép. | Change audit và control-tamper detection. |
| **DE-T34** | Out-of-band threshold change giảm alerts đột ngột. | Detection-as-code drift/source-health investigation. |
| **DE-T35** | Raw security event chứa bearer token. | Privacy/redaction control FAIL, incident escalation theo policy. |
| **DE-T36** | EDR reports healthy nhưng cloud/app independent event mâu thuẫn. | Evidence conflict được challenge và điều tra. |
| **DE-T37** | Incident response revoke credential nhưng old token còn accepted. | Response effectiveness retest FAIL dù alert đã đúng. |
| **DE-T38** | Một source bị decommission hợp lệ. | Expected population/canary được cập nhật có audit, không noise vô ích. |
| **DE-T39** | Backfill/replay historical events tạo duplicate alerts. | Dedup/time-window/reprocessing policy verified. |
| **DE-T40** | Security requirement đổi vì new API/export functionality. | Trigger review/threat mapping/test corpus và redeploy detector. |

### Cách ghi kết quả

Mỗi case cần `test_id`, linked requirement/threat, source/actor/test fixture, event time, input schema, rule version, expected analytic outcome, observed match/alert/case outcome, collector health, environment/region/tenant scope, evidence refs, limitations và status.

### Không tự cộng “40 tests PASS = hệ thống secure”

Một critical data leakage có thể chưa được model trong tests; một route v1 thiếu logs có thể làm toàn bộ denied-burst detection mất tác dụng ở đó. Báo cáo cần **critical threat hypotheses, untested paths, source coverage và risk**, không chỉ số tests đã chạy.

## 39. Case study: Detection cho Invoice SaaS đa tenant

### 39.1. Bối cảnh

Invoice SaaS dùng Java/Spring APIs (v1/v2), async export workers, managed database, object storage, IdP, cloud IAM, Kubernetes và centralized security monitoring. Tổ chức muốn phát hiện sớm những hành vi có khả năng dẫn tới **cross-tenant data exposure, unauthorized privilege grants và loss of security telemetry**.

### 39.2. Security requirements

| ID | Security invariant | Detection hypothesis |
| --- | --- | --- |
| **INV-AUTHZ-01** | User không đọc được invoice của tenant khác. | Repeated denied reads; complementary check cho abnormal allowed cross-tenant reads. |
| **INV-ROLE-02** | Privileged role grants phải có approved authority. | New admin grants ngoài approved change. |
| **INV-EXPORT-03** | Bulk export chỉ trong authorized scope. | Unusual export patterns và mismatched actor/job/tenant context. |
| **INV-STORAGE-04** | Storage không trở thành public ngoài policy. | Resource-policy change trái approved baseline. |
| **INV-AUDIT-05** | Events security-critical được gửi đúng schema và SLA. | Source silent/lag/parse failures. |
| **INV-RESPONSE-06** | Alerts material có owner và response trong SLA. | Alert delivery/triage control health. |

### 39.3. Sources và trust boundaries

~~~mermaid
flowchart LR
    U["Synthetic tenant users A/B"] --> API["Invoice API v1 / v2"]
    API --> DB[("Invoice DB")]
    API --> Q[("Export queue")]
    Q --> W["Export worker"]
    W --> S[("Object storage")]
    IDP["IdP audit"] --> C["Security data pipeline"]
    CLOUD["Cloud IAM/storage audit"] --> C
    API --> C
    W --> C
    S --> C
    C --> N["Normalized events + source health"]
    N --> R["Detection analytics"]
    R --> SOC["SOC queue and case management"]
    SOC --> FIX["Response / remediation"]
~~~

Không phải mọi mũi tên đều có cùng guarantees: events có thể đến trễ, thiếu tenant context hoặc bị phân mảnh giữa services. Chất lượng correlation cần được đo.

### 39.4. Mười observations giả định

| Observation | Kết quả test minh họa | Diễn giải đúng |
| --- | --- | --- |
| **OBS-01** | API v2 tạo event deny đầy đủ khi A thử synthetic B object. | Source v2 hoạt động trong tested path. |
| **OBS-02** | Rule tạo alert với 8 denies tới 5 invoices trong window. | Threshold analytic PASS cho fixture. |
| **OBS-03** | API v1 có cùng deny behavior nhưng không tạo audit event. | Source/route coverage gap. |
| **OBS-04** | Worker export tạo job nhưng thiếu verified actor ID. | Async correlation context incomplete. |
| **OBS-05** | IAM admin grant event có nhưng enrichment map nhầm cloud account. | Identity/context correctness gap. |
| **OBS-06** | Storage public policy drift event đến pipeline sau 25 phút. | Latency gap nếu SLA nhỏ hơn 25 phút. |
| **OBS-07** | App log schema đổi, parser drop `decision` field. | Silent false-negative potential. |
| **OBS-08** | Analyst queue nhận alert nhưng owner không rõ. | Operational response gap. |
| **OBS-09** | Approved bulk migration sinh nhiều alerts thiếu context. | False-positive/tuning need, không tự suppress diện rộng. |
| **OBS-10** | Synthetic source outage làm canary mất nhưng dashboard vẫn báo healthy. | Source health/evidence assurance failure. |

### 39.5. Triaging OBS-03: rule đúng nhưng threat coverage sai

Rule `DET-INVOICE-DENIED-BURST-001` có thể chạy hoàn hảo trên events từ API v2. Tuy nhiên **API v1 không tạo event**, nên không thể nói rule bao phủ toàn bộ Invoice API. Remediation cần sửa **event generation/route inventory**, triển khai logging contract cho v1 hoặc chứng minh route v1 đã decommission, rồi chạy canary end-to-end.

### 39.6. Triaging OBS-07: dữ liệu vẫn chảy nhưng detector mù

Collector vẫn nhận logs, event volume trông bình thường. Nhưng parser sau schema change không còn map `decision`; query lọc `decision='DENY'` không match. Một metric “ingestion healthy” có thể tiếp tục xanh trong khi rule không còn useful. Cần **contract tests, missing-field alert, replay validated fixtures và deployment/version readback**.

### 39.7. Triaging OBS-09: noise có thể là tuning vấn đề data

Một approved migration job dùng service identity để export synthetic data hàng loạt. Rule không biết approved change context nên tăng false positives. Cách sửa có thể là **correlate signed/approved change metadata, role/workload identity và time window**, không whitelist mọi internal exports. Sau tuning phải retest các cases unauthorized bên ngoài approved window.

### 39.8. Tách technical và operational outcomes

| Domain | Outcome minh họa | Required next step |
| --- | --- | --- |
| Analytic correctness | PASS trên positive/negative fixtures. | Giữ regression tests. |
| API source coverage | PARTIAL vì v1 thiếu events. | Implement/verify source hoặc retire v1. |
| Worker correlation | PARTIAL do actor missing. | End-to-end identity contract. |
| Cloud enrichment | FAIL theo observation giả định. | Fix mapping và replay tests. |
| Ingestion latency | Vi phạm nếu SLA dưới 25 phút. | Diagnose queue/collection timing. |
| Parser correctness | FAIL sau schema change. | Contract validation và rule retest. |
| SOC routing | FAIL owner requirement. | Update routing/on-call and drill. |
| Noise control | NEEDS_TUNING. | Narrow approved-context enrichment. |
| Source health | FAIL for outage canary. | Independent heartbeat/health alert. |

### 39.9. Remediation plan

1. Reconcile API v1/v2/worker/storage identities và event-producing paths.
2. Định nghĩa và version data contract cho authorization decisions.
3. Fix event fields/trusted actor mapping; kiểm event output không chứa PII/secrets.
4. Add parser compatibility tests và missing-field health monitors.
5. Deploy analytics/routing theo approved rule versions.
6. Run synthetic positive, negative, late-data, dedup, wrong-tenant tests.
7. Run source-to-SOC benign canary với observed latency và evidence refs.
8. Triage false positives qua approved migration metadata với scoped exception.
9. Ensure SOC queue ownership/runbook và emergency escalation.
10. Record residual blind spots, change triggers, review lại claim phạm vi.

### 39.10. Kết luận case study có giới hạn

“Rule threshold được xác minh trên dữ liệu synthetic của API v2 nhưng chương trình detection **chưa có đủ operating evidence cho toàn bộ Invoice SaaS** vì API v1/worker data gaps, parser drift, routing và source-health failures. Cần remediation/retest theo các requirement và population đã nêu; chưa thể kết luận mọi hành vi cross-tenant bị phát hiện.”

Đây chỉ là **case study học tập**, không phải một incident hay kiểm thử sản phẩm thật.

## 40. Mẫu Detection Assurance Record: theo dõi từ claim tới retest

Một rule source file không đủ làm hồ sơ assurance. Cần record liên kết requirement, source, runtime version, coverage, verification và ownership. Ví dụ YAML sau **không phải cấu hình chạy trực tiếp trên SIEM**, chỉ mô tả kết quả đánh giá giả định chưa thực thi.

~~~yaml
schema_version: "1.0"
record_type: "security_detection_assurance"
record_id: "ASSUR-DET-INVOICE-001"
service_name: "SECURITY_SECURITY_ASSURANCE"
chapter: "Detection engineering"
topic: "Detection là gì"
assurance_status: "ILLUSTRATIVE_NOT_EVALUATED"
security_claim: >
  For approved Invoice API services in population P,
  an authorized synthetic denied-access burst triggers a
  correctly routed alert within the agreed latency window.
requirements:
  - "INV-AUTHZ-01"
  - "INV-AUDIT-05"
  - "INV-RESPONSE-06"
threat_hypotheses:
  - "H-DENIED-CROSS-TENANT-READS"
scope:
  application: "invoice-saas"
  environments:
    - "production"
  api_versions:
    - "v1"
    - "v2"
  workload_types:
    - "invoice-api"
  expected_population_source: "approved-service-inventory"
data_contract:
  event_type: "invoice.read.authorization_decision"
  version: "1.0"
  required_fields:
    - "event_time"
    - "actor_id"
    - "actor_tenant_id"
    - "resource_ref"
    - "decision"
    - "event_id"
  raw_secrets_allowed: false
detection:
  id: "DET-INVOICE-DENIED-BURST-001"
  version: "PENDING_DEPLOYED_RULE_READBACK"
  threshold_policy: "EXAMPLE_THRESHOLD_NOT_APPROVED"
  routing: "SOC-application-queue"
  runbook_ref: "PENDING"
verification:
  offline_tests:
    - "DE-T01"
    - "DE-T02"
    - "DE-T03"
    - "DE-T06"
  end_to_end_tests:
    - "DE-T11"
    - "DE-T16"
    - "DE-T29"
  source_health_test:
    - "DE-T17"
  tested_at: "NOT_TESTED"
  detection_latency: "NOT_MEASURED"
  observed_alert_id: "NONE"
  evidence_refs: []
  status: "UNKNOWN"
limitations:
  - "No valid production source population evidence"
  - "No end-to-end canary completed"
owners:
  use_case: "Detection Engineering"
  data: "Invoice Application Team"
  response: "SOC"
  risk: "Invoice Business Risk Owner"
exceptions: []
reassessment_triggers:
  - "new-api-version-or-tenant-tier"
  - "security-audit-schema-update"
  - "collector-or-parser-change"
  - "deployed-rule-version-change"
  - "material-incident-or-missed-detection"
~~~

### Trạng thái `UNKNOWN` có chủ đích

Record mô tả **phương pháp**, không khẳng định đã chạy test. `observed_alert_id: NONE` không nói rule fail hay threat không tồn tại — chỉ nói ví dụ chưa có observed alert evidence. Muốn chuyển PASS phải điền evidence có provenance, asset population, version, source health và kết quả end-to-end.

### Một record tốt cần nêu contradictions

Nếu rule test PASS nhưng alert queue thiếu owner, không xóa kết quả PASS của unit test; đồng thời không cấp global PASS. Có thể ghi **analytic PASS / operational routing FAIL / overall PARTIAL** để giữ nguyên sự thật ở từng lớp.

## 41. KPI/KRI/KCI cho Detection Engineering

Một chương trình trưởng thành đo **độ phủ, chất lượng dữ liệu, khả năng bắt threat, chi phí noise và hiệu quả response**. Không dùng “số rules nhiều” hay “số alerts ít” như KPI duy nhất.

| Metric ID | Định nghĩa hoặc phương pháp | Giới hạn |
| --- | --- | --- |
| **DE-M01 Critical hypothesis coverage** | Required high-risk behaviors có detection/tests phù hợp / independently identified hypotheses. | Rule mapping trên giấy chưa đủ operating. |
| **DE-M02 Required telemetry source coverage** | Eligible assets tạo required source/contract / independent eligible population. | Scanner-known assets không đủ denominator. |
| **DE-M03 Valid event schema rate** | Events thuộc scope có required fields/enum đúng / valid received scope population. | Chỉ nhận được events không nói events đã mất. |
| **DE-M04 Source-health conformance** | Required sources có heartbeat/benign canary đúng SLA / required sources. | Heartbeat không chứng minh mọi event types. |
| **DE-M05 Detection deployment alignment** | Deployed analytics đúng approved rule version/scope / required targets. | Có thể disabled dù version đúng. |
| **DE-M06 Unit test pass rate** | Positive/negative fixture cases đạt / eligible fixtures của rule. | Không thay end-to-end tests. |
| **DE-M07 End-to-end detection coverage** | Approved canary paths tạo alert/routing đúng / required material paths. | Canaries không chứng minh các attack variants khác. |
| **DE-M08 Time to detection** | Observed event-to-alert latency theo use case/cohort/percentile. | Event time/clock/delayed arrival phải đáng tin. |
| **DE-M09 Alert precision estimate** | TP/(TP+FP) trong labeled representative reviewed sample. | Sampling bias và unknown dispositions. |
| **DE-M10 Recall estimate** | TP/(TP+FN) trong ground-truth test population. | Không suy từ production alerts alone. |
| **DE-M11 False positive burden** | False alerts / analyst-shift hoặc per 1k meaningful events, theo cohort. | Business activity volume khác nhau. |
| **DE-M12 Analyst triage time** | Alert received→reviewed disposition theo priority. | Tách automated benign close và human investigation. |
| **DE-M13 High-impact missed detections** | Verified material scenarios không được alert theo SLA. | Unknown population chưa thấy không là 0. |
| **DE-M14 Data ingestion freshness** | Events trong allowed event→ingest delay / required expected observations. | Source silent có thể làm ratio bị đánh lừa. |
| **DE-M15 Alert delivery reliability** | Analytic matches tạo tickets/notifications nhận được / matches cần route. | SOC acknowledgement là metric khác. |
| **DE-M16 Rule tuning regression rate** | Approved changes gây unexpected missed/noisy cases theo test corpus. | Corpus phải đủ đa dạng và versioned. |
| **DE-M17 Suppression governance** | Active suppressions có rationale/owner/scope/expiry / all active suppressions. | Suppression không đồng nghĩa control PASS. |
| **DE-M18 Source outage detection latency** | Time source health vượt ngưỡng→health alert/triage. | Missing events có thể do approved idle. |
| **DE-M19 Response runbook coverage** | Material detections có tested runbook/owner / detections yêu cầu response. | Runbook tồn tại chưa chắc analyst làm được. |
| **DE-M20 Evidence traceability** | Material claims có requirement→rule→test→alert→decision/provenance / claims cần chứng minh. | Links có thể stale sau deploy. |

### Ví dụ định lượng giả định

Trong 80 endpoints quan trọng đã được inventory độc lập, chỉ 70 sinh valid security audit events theo contract và 60 đã có canary-to-alert test đạt. Có thể mô tả **source coverage = 70/80 = 87,5%** và **end-to-end tested coverage = 60/80 = 75%**, nếu các denominators/conditions được định nghĩa như vậy. **Không** thể viết “75% hệ thống an toàn”.

### Cần phân tầng theo criticality

Một detection gap ở signing server hoặc cross-tenant export có thể nghiêm trọng hơn mười detections ít quan trọng PASS. Thống kê phải tách **tier, threat, data classification, user impact và source confidence**.

### Không che unknown dưới denominator

Nếu một cloud account không có collector permissions, không thể loại nó khỏi denominator để tăng compliance. Có thể báo **known eligible scope, unknown assets và completeness limitation** riêng; đối soát độc lập trước khi chốt coverage.

## 42. Ownership và RACI: ai chịu trách nhiệm phát hiện?

Detection engineering không thể chỉ giao cho một SOC analyst hoặc một SIEM admin. Use case thường phụ thuộc product, identity, platform, data và incident response.

| Vai trò | Trách nhiệm |
| --- | --- |
| **Business/service owner** | Protected assets, business workflows, data classification và acceptable risk. |
| **Threat/security architect** | Threat model, security objectives, hypothesis, coverage prioritization. |
| **Application/data owner** | Trusted event generation, semantics, privacy và schema versioning. |
| **Telemetry/platform owner** | Collection, transport, normalization, retention, source/collector health. |
| **Detection engineer** | Analytic logic, tests, tuning, deployment, change control. |
| **SIEM/EDR administrator** | Runtime rule execution, access, integrations, scheduling, resource limits. |
| **SOC analyst/lead** | Triage, case ownership, escalation, feedback về alert quality. |
| **Incident responder** | Investigation, containment/recovery, preservation và post-incident feedback. |
| **Security assurance assessor** | Challenge scope/evidence, verify control effectiveness, qualified conclusions. |
| **Risk owner** | Accept residual risk/exceptions đúng thẩm quyền và thời hạn. |
| **Privacy/legal owner** | Review sensitive telemetry, retention/disclosure khi applicable. |

### RACI minh họa

**R** thực hiện; **A** chịu trách nhiệm cuối cùng; **C** tham vấn; **I** được thông báo.

| Hoạt động | App/Data | Detection Eng | SOC | Assurance | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Thiết kế event schema và nguồn | **A/R** | C | C | I | I |
| Detection hypothesis và analytic | C | **A/R** | C | C | I |
| Duy trì collectors/parser/source health | R | **A/R** | C | C | I |
| Canary/positive/negative test | R | **A/R** | R | C | I |
| Alert triage/runbook và escalation | C | C | **A/R** | I | I |
| Independent CAE/evidence review | C | C | C | **A/R** | I |
| Risk acceptance/exception | C | C | C | C | **A/R** |

RACI này cần điều chỉnh theo cách tổ chức giao platform responsibilities; với high-impact control nên có **independent review** khi evidence có rủi ro bị self-report bias.

### Mỗi alert phải có owner

Nếu detection mới không có người nhận trong giờ ngoài hành chính, công bố “alerting effective 24/7” là thiếu cơ sở. Cần on-call roster, routing failover, queues và tests trong time windows quan trọng.

## 43. Risk exceptions, known blind spots và quyết định chấp nhận rủi ro

Một organization có thể chưa đủ telemetry để phát hiện một threat trên legacy API hoặc một managed provider không cấp logs cần thiết. Đó là **assurance gap** phải được quản trị minh bạch.

### Exception record cần ghi

1. Detection use case/requirement/threat và affected assets/environments.
2. **Missing capability:** event không có, analytics không có, rule disabled hay alert routing lỗi?
3. Evidence về trạng thái hiện tại, data/source health và thời kỳ áp dụng.
4. Attacker capability, exposure, data criticality và potential impact.
5. Existing prevention/other detection/response controls và **evidence hiệu lực**.
6. Interim mitigation: limit access, extra audit, manual review, temporary monitoring.
7. Owner sửa, deadline, milestones và **risk authority** phê duyệt.
8. Expiry, reassessment triggers, incident/new route/schema change.
9. Required test/response evidence để đóng exception.
10. Regulatory/contractual obligations đã được review khi cần.

### Không dùng “accepted” như “detected”

Một blind spot được risk owner chấp nhận không làm detector thành PASS. Báo **technical coverage gap** và **accepted residual risk** thành hai thông tin riêng.

### Ví dụ

Legacy export worker không có actor ID trong log và chưa thể nâng cấp trong kỳ. Có thể dùng restricted API access, lower export volume threshold, storage audit correlation và manual oversight như interim controls. Nhưng phải ghi **blind spot còn lại** và test những controls thay thế — không nói detection đầy đủ.

### Khi nào exception cần mở lại ngay?

Xuất hiện incident, threat intelligence cho thấy cách lạm dụng mới, API version được mở public, source health giảm, tenant model thay hoặc interim controls không còn enforce. Không chờ tới ngày hết hạn nếu threat/exposure thay.

## 44. Continuous Detection Engineering và điều kiện đánh giá lại

Detection logic được xây dựng trên **giả định về hệ thống**. Khi ứng dụng hoặc attacker behavior thay đổi, giả định ấy có thể lỗi thời dù rule code không đổi.

### Các trigger quan trọng

- API endpoint/version, mobile/partner flow, async worker hoặc export functionality mới.
- Identity provider, roles, tenant mapping, session lifecycle và privileged grant policy thay.
- Security event schema/parser normalization hoặc ingestion field mapping đổi.
- Cloud account/cluster/region/tenant tiers mới, autoscaling hoặc decommission.
- EDR sensor/agent, cloud audit policy, SIEM backend hoặc network collector upgrade.
- Feature flag bật/tắt legacy route và approved maintenance exceptions.
- Rule threshold, time window, suppression, severity hoặc SOC routing đổi.
- Detection miss, confirmed incident, red-team exercise hoặc new threat knowledge.
- Alert overload, false-positive drift, analyst response SLA bị vi phạm.
- Source outage, clock drift, latency tăng hoặc enrichment mapping stale.
- Artifact/pipeline version khác với approved detection-as-code release.
- Privacy/data retention constraints thay, làm một số fields không còn được thu.

### Chu trình liên tục

~~~mermaid
flowchart TD
    A["Approved threats, requirements and detection catalog"] --> B["Material system / threat / data change"]
    B --> C["Review hypothesis, coverage and data contract"]
    C --> D["Update sources, rules, enrichment and runbook"]
    D --> E["Execute labeled positive, negative, failure tests"]
    E --> F["Approved deployment and runtime version check"]
    F --> G["Benign source-to-SOC canary"]
    G --> H{"Detection objective met?"}
    H -- "Yes, within scope" --> I["Versioned assurance evidence"]
    H -- "No / inconclusive" --> J["Finding, owner, risk decision and remediation"]
    J --> C
    I --> K["Monitor alert quality, source health, incidents"]
    K --> B
~~~

### Tái kiểm chứng theo risk

Không phải mọi rule cần full-scale exercise mỗi ngày. Critical identity/cloud control detections có thể cần **canary thường xuyên và thay đổi thì retest ngay**, trong khi analytics cho hành vi ít quan trọng có cadence khác. Xác định freshness từ **threat criticality, rate of change, source stability và incident tolerance**.

### Một detection retirement phải có bằng chứng

Khi decommission API v1, có thể retire rule riêng cho v1 **nếu** có route inventory, runtime reachability proof, data source lifecycle, replacement coverage và approval. Xóa rule vì “không còn alert” không đủ, vì chính source outage có thể làm nó im lặng.

## 45. Anti-patterns khi thiết kế và đánh giá detection

| Anti-pattern | Hậu quả | Hướng cải thiện |
| --- | --- | --- |
| **0 alert = không có tấn công** | Bỏ blind spots, source outage, false negatives. | Coverage, canary và unknown reporting. |
| **Có SIEM = đã có detection** | Log storage không thành analytic/response. | End-to-end use case và test. |
| **Rule enabled = effective** | Parser/data/routing có thể hỏng. | Source-to-SOC canary và rule readback. |
| **Rule match = incident** | Noise và escalation sai. | Triage evidence, context, classification. |
| **Anomaly = malicious** | Chặn workflow hợp lệ. | Business context và confidence. |
| **Severity cao = impact chắc chắn** | Overclaim. | Exposure, assets, actor, observed behavior. |
| **Giảm alerts nghĩa là tuning thành công** | Tắt source/suppress rộng cũng làm số alert giảm. | Unit/regression/canary/source health. |
| **Nhiều rules = bao phủ tốt** | Rules trùng, critical behavior bỏ sót. | Threat/requirement-to-use-case coverage. |
| **Mọi logs đều hữu ích** | Data cost và privacy risk tăng. | Event contract/data minimization. |
| **Raw token cần thiết cho correlation** | Secrets leakage. | Verified pseudonymous references. |
| **Một field tên user là trusted actor** | Spoofing hoặc mapping sai. | Server-verified identity/event provenance. |
| **Event-time = ingest-time** | Sai windows/latency. | Distinct timestamps và late-data handling. |
| **Dedup bằng actor/resource/time** | Bỏ requests thật. | Trusted event IDs và semantics. |
| **Một test fixture đủ** | Boundary và negative cases bị bỏ. | Versioned positive/negative corpora. |
| **Unit PASS = end-to-end PASS** | Pipeline failure không phát hiện. | Canary tới SOC và receiver readback. |
| **Source heartbeat = dữ liệu đầy đủ** | Event class missing/parser drop. | Semantic canaries và field health. |
| **No alerts vì parser lỗi là benign** | Không thấy attack dù dữ liệu tới. | Missing-field/parse error monitoring. |
| **One API version test covers all** | Legacy/worker route không có events. | Independent route/population mapping. |
| **Identity joins theo email/IP thô** | Gộp nhầm users, NAT false alerts. | Trusted IDs + temporal context. |
| **Suppress internal traffic toàn bộ** | Insider/compromised workload blind spot. | Narrow, reviewed, expiring exceptions. |
| **Chỉ sửa rule khi detection miss** | Lỗi có thể nằm ở source/transport. | Root-cause by pipeline layer. |
| **Đếm raw alerts là workload** | Dedup/aggregation làm méo analyst load. | Cases and analyst-time metrics. |
| **Auto-isolate dựa score yếu** | Outages hoặc sai incident classification. | Confidence, approval, safety rollback. |
| **Không phân biệt FP và unknown** | Data gaps được gắn benign. | Evidence-backed dispositions. |
| **Gọi accepted exception là PASS** | Risk bị ẩn. | Technical status/risk decision riêng. |
| **Tất cả consumers dùng schema vĩnh viễn** | Event rename silently breaks rules. | Versioned producer/consumer tests. |
| **Dashboard compliant trên registered agents** | Denominator bỏ missing assets. | Independent inventory và source reconciliation. |
| **Không có owner vào ca đêm** | Alert tới queue không ai xử lý. | On-call/routing fallback exercise. |
| **Chỉ đo mean latency** | P95/P99 và source stalls bị che. | Distributions, percentiles, overdue cohorts. |
| **Một bài diễn tập benign chứng minh mọi threats** | Unsupported generalization. | Claim chỉ trong tested conditions. |

### Bảy phát biểu nên khiến assessor hỏi lại

1. “Rule đã được enable nên không cần test.”
2. “Không có alert từ host này, hẳn không có hành vi xấu.”
3. “Đã giảm 80% alerts sau tuning, nghĩa là đã cải thiện detection.”
4. “Cảnh báo có mức Critical thì nhất định đã có sự cố Critical.”
5. “Chỉ cần log all requests, thiếu field nào sẽ tìm trong raw body.”
6. “Parser lỗi vài ngày không sao, vì data lake vẫn nhận events.”
7. “Một canary API v2 PASS chứng minh API v1 cũng an toàn.”

Các câu này thiếu **source health, scope, logic, business context hoặc operating evidence**. Reviewer cần đặt câu hỏi **điều gì thực sự được quan sát, trong những điều kiện nào, và còn điều gì chưa thể kết luận**.

## 46. Checklist đánh giá “Detection là gì?” trong thực hành

Checklist này giúp kiểm thử/kiểm toán một detection use case, không thay professional review. Mỗi mục material nên có **PASS, FAIL, PARTIAL, UNKNOWN hoặc N/A với rationale, evidence ref, owner và retest trigger**.

1. **Objective:** xác định bảo vệ dữ liệu/chức năng nào và security requirement nào?
2. **Threat:** nêu actor capability, objective, behavior và assumptions?
3. **Scope:** app/API versions, tenants, roles, environments, cloud accounts/regions rõ?
4. **Population:** có independent source inventory, không chỉ scanner known assets?
5. **Detection purpose:** preventive/monitoring/detective/response roles được phân biệt?
6. **Hypothesis:** hành vi nào phải MATCH, hành vi nào không?
7. **Data source:** mỗi required event type có producer và owner?
8. **Trust of source:** data fields đến từ server-verified identities, không từ client spoofing?
9. **Schema:** required fields, types, enum, normalization và version contract đầy đủ?
10. **Sensitive data:** không collect raw credentials, invoices hoặc PII ngoài purpose?
11. **Event semantics:** decision `DENY` và `ALLOW` được định nghĩa đúng?
12. **Timestamps:** event/ingest/evaluation times và clock quality có được ghi?
13. **Actor/entity mapping:** issuer, tenant, host, resource and temporal validity đúng?
14. **Correlation:** keys/windows/thresholds có logic, business context và limitations?
15. **Duplicates:** policy dựa trusted event IDs, không che requests hợp lệ?
16. **Late events:** reprocessing/allowed lateness được thiết kế/test?
17. **Source coverage:** routes, legacy APIs, workers, mobile/partner paths thuộc scope được nhìn?
18. **Source health:** expected heartbeat/semantic canaries và collector permissions?
19. **Parser health:** field presence/parse errors được giám sát và alert?
20. **Rule version:** deployed analytic identity/digest/enablement/schedule đúng?
21. **Review:** rule logic và critical changes được review độc lập khi cần?
22. **Unit tests:** positive/negative threshold and grouping cases đạt?
23. **Contract tests:** producer/consumer/schema changes không silent break?
24. **End-to-end tests:** synthetic action→normalized event→match→alert?
25. **Delivery:** SOC queue/ticket nhận đúng severity, owner và thời gian?
26. **Canary governance:** test marker và synthetic data không kích hoạt response nhầm?
27. **Response:** runbook/triage/escalation có owner và drill evidence?
28. **Data quality limits:** missing/late/stale/invalid inputs được báo UNKNOWN?
29. **False positives:** benign patterns được phân loại có evidence, không suppress quá rộng?
30. **False negatives:** known blind spots, unmodeled behaviors và coverage gaps rõ?
31. **Ground truth:** precision/recall tests dùng labeled sample và nêu bias?
32. **Latency:** event-to-alert SLA/percentiles được đo đúng timestamps?
33. **Costs:** analytic query capacity, storage/retention và SOC workload phù hợp?
34. **Risk:** severity/priority dựa asset impact, exposure, confidence, không chỉ raw rule label?
35. **Evidence:** source/asset/version/time/provenance, integrity và privacy protection?
36. **Exceptions:** owner/authority/scope/expiry/interim controls có?
37. **Missing sensor:** source outage có phát hiện, không silently mark PASS?
38. **Changes:** API/schema/IAM/flags/ruleset/detector deployment trigger retest?
39. **Retirement:** rule không còn phù hợp được decommission có coverage mapping?
40. **Conclusion:** CAE có được hỗ trợ theo **scope/time** và limitations hay không?

### Kết quả checklist phải có ý nghĩa

Chấm 35/40 điểm không tự nói detector “87,5% hiệu quả”. Một điểm FAIL ở **critical source coverage** có thể làm cả use case không đạt mục tiêu, dù những mục documentation khác PASS. Các **critical gates** và evidence confidence nên được trình bày riêng.

## 47. Bài tập tình huống và gợi ý giải

### Bài tập A — Không có alert suốt một tuần

SOC báo 0 alerts về invoice authorization trong 7 ngày. Không có ai xem pipeline health.

**Gợi ý:** Không suy không có tấn công. Kiểm eligible API/tenant population, event volume, schema contract, parser, rule version, canary and alert routing. Ghi trạng thái UNKNOWN cho claim thiếu chứng cứ.

### Bài tập B — Có logs nhưng không có detection

App ghi hàng triệu HTTP requests, song không có actor/tenant/security decision và chưa có analytics.

**Gợi ý:** Logging là telemetry, chưa là detective control. Cần approved event contract, threat hypothesis, source field enrichment, analytic, tests và runbook; hạn thu raw request body.

### Bài tập C — Rule threshold gây quá nhiều alerts

Cuối tháng, tenant hợp lệ export nhiều hóa đơn; rule số lượng requests tạo 500 alerts.

**Gợi ý:** Tuning dựa business calendar/approved jobs, tenant tier, role và resource. Regression test malicious/unapproved fixtures; không whitelist mọi exports hoặc tắt pipeline.

### Bài tập D — Actor join bằng email

Hai identities từ hai IdPs có cùng email bị rule gộp vào một principal, làm tăng số failed accesses giả.

**Gợi ý:** Dùng verified subject+issuer+tenant binding và temporal mapping, contract test, phân loại false positive từ join chứ không tăng threshold tùy tiện.

### Bài tập E — Duplicate events vì queue retry

Collector retry event, rule count mỗi bản sao như một denied request.

**Gợi ý:** Trusted unique event ID, replay/dedup semantics, correlation across source; giữ chính xác distinct real events, không dedup quá rộng.

### Bài tập F — Incident không được phát hiện ở API v1

API v2 sinh `authorization.denied`, API v1 không ghi audit. Detector chỉ nhìn denied events.

**Gợi ý:** Đây là **source/path coverage failure**. Thêm instrumentation hoặc decommission v1 có evidence, retest end-to-end; rule unit PASS không khắc phục gap.

### Bài tập G — API trả ALLOW trái policy

Một lỗi object authorization cho phép A đọc synthetic B invoice. Detector chỉ lọc DENY.

**Gợi ý:** Rule không được thiết kế cho sự kiện này. Cần prevention fix, complementary invariant/allowed-access anomaly detection và cross-tenant tests; không tuyên bố detector cũ đã bắt BOLA.

### Bài tập H — Parser thay enum không thông báo

Producer đổi `DENY` thành `DENIED`. SIEM vẫn ingest events, rule trả 0 matches.

**Gợi ý:** Data contract drift; producer/consumer versioned tests, missing-field/invalid enum alerts, replay verification và rule deployment check.

### Bài tập I — Events đến trễ

Một network outage khiến events được gửi dồn sau 20 phút. Detector dùng processing-time 10 phút nên gây burst alert.

**Gợi ý:** Phân biệt event-time/ingest-time, late arrival, window semantics và replay/dedup. Thiết kế watermark/lateness theo platform và test scenario.

### Bài tập J — Precision cao nhưng vẫn bị bypass

Rule báo chính xác khi có 20 denied requests, nhưng attacker có thể gây ảnh hưởng bằng một allowed privileged action sai policy.

**Gợi ý:** Precision trên một detection không đo coverage của các threats khác. Threat modeling chọn thêm invariant/privileged action use case và kiểm assumptions.

### Bài tập K — False positive được suppress toàn bộ source IP nội bộ

SOC suppress mọi alerts từ private subnet vì số cảnh báo rất lớn.

**Gợi ý:** Tạo blind spot với compromised internal workloads. Thay bằng scoped approved identity/job/time exceptions, nâng data quality và regression test malicious internal synthetic cases.

### Bài tập L — SOC queue nhận alert nhưng không ai xem

Analytic tạo alert đúng, nhưng on-call roster không có người nhận ban đêm.

**Gợi ý:** Analytic PASS nhưng operating response FAIL. Sửa routing/owner, failover/escalation, drill trong relevant shifts và đo acknowledgement.

### Bài tập M — Source health xanh giả

Host EDR heartbeat healthy nhưng event loại privilege change không đến SIEM.

**Gợi ý:** Heartbeat chỉ hỗ trợ connection. Dùng benign semantic canary và source-to-SOC evidence; kiểm agent policy, parser/transport/source permissions.

### Bài tập N — User log chứa bearer token

Để giúp điều tra, developer thêm raw Authorization header vào log event.

**Gợi ý:** Đây có thể là security/privacy incident thứ cấp. Redact/minimize, đánh giá token exposure, rotate/revoke nếu thực, sửa schema và retention/access, không tiếp tục sao chép token vào tickets.

### Bài tập O — Một SIEM query PASS nhưng runtime version cũ

CI test rule version 3 PASS; production đang chạy version 2 và chưa enable cho cloud account mới.

**Gợi ý:** Deployment drift; require runtime version/enablement/target population readback, canary theo account và source-health evidence.

### Bài tập P — Không biết ground truth để tính recall

Team lấy tổng alerts đã review và cho rằng phần trăm true positives chính là recall.

**Gợi ý:** Đó có thể gần precision estimate, không là recall. Recall cần positive cases thật gồm những cases detector bỏ sót trong defined population, dùng labeled tests/independent review và công bố bias.

### Bài tập Q — Suppression hợp lệ đã hết hạn

Một maintenance window exception vẫn được giữ ba tháng sau khi migration hoàn tất.

**Gợi ý:** Expiry/reopen, review change owner, remove/narrow suppression, retest threats tương tự và rà old missed detections nếu cần.

### Bài tập R — Alert có dữ liệu đúng nhưng severity sai

Một privileged signing host có event đáng ngờ nhưng severity giống test worker; enrichment không biết asset criticality.

**Gợi ý:** Bổ sung trusted asset inventory/risk context và governance về severity. Không tăng severity toàn bộ events, tránh false alarm cost.

### Bài tập S — User được revoke nhưng old session vẫn gọi API được

Detection thấy anomaly và SOC revoke credential, nhưng API cache vẫn chấp nhận old token trong khoảng không được policy cho phép.

**Gợi ý:** Detection và response đã bắt đầu nhưng **containment effectiveness chưa đạt**. Kiểm token/session revocation semantics, timed negative tests, identity caches và residual risk.

### Bài tập T — Rule cần được retire?

Legacy endpoint được tuyên bố đã gỡ, không còn alerts, engineer muốn xóa toàn bộ use-case cũ.

**Gợi ý:** Xác minh deployed route reachability, clients, async paths, source lifecycle, replacement coverage và risk-owner approval; no-alert không chứng minh endpoint đã biến mất.

## 48. Kết luận

**Detection** là khả năng nhận diện những **hành vi, trạng thái hoặc chuỗi sự kiện có ý nghĩa bảo mật** dựa trên telemetry, ngữ cảnh và logic phân tích. **Detection engineering** biến khả năng đó thành một detective control có thể thiết kế, version hóa, kiểm thử, triển khai, đo lường, vận hành và cải tiến.

Trong **SECURITY_SECURITY_ASSURANCE**, trọng tâm không chỉ là “đã có rule” hoặc “dashboard có alerts”. Kết luận có bằng chứng phải nối được:

**Security objective/threat → detection hypothesis → telemetry contract/source population → analytic logic → deployed rule → positive/negative tests → end-to-end canary → alert/triage/response outcome → versioned evidence → reassessment.**

Detection khác prevention, monitoring và incident response; một rule match không tự chứng minh có incident, và không có alert không tự chứng minh không có tấn công. Cần phân biệt **TP/FP/FN/TN**, đánh giá precision/recall trong population có ground truth, nhận diện **late events, parser drift, entity mapping errors, suppression gaps, nguồn đo ngừng hoạt động và những behavior chưa được mô hình hóa**.

Một chương trình detection trưởng thành phải có **asset/threat coverage, data-quality/source-health monitoring, canary và failure-mode tests, người nhận cảnh báo, runbooks, privacy protection, evidence provenance, ownership, exceptions có thời hạn và trigger retest khi ứng dụng/threat thay đổi**. Nếu rule unit PASS nhưng một API version thiếu log hoặc SOC không nhận được alert, assurance claim phải là **PARTIAL/FAIL/UNKNOWN theo từng lớp**, không tự chuyển toàn hệ thống sang PASS.

**Mục tiêu cuối cùng là xây dựng năng lực phát hiện có thể giải thích và chứng minh được — phát hiện đúng điều quan trọng, trong đúng phạm vi, đủ kịp thời để hỗ trợ quyết định và khắc phục — đồng thời trung thực về những gì chưa quan sát được.**
