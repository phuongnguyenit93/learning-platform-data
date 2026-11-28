# Review Threat Model: Đánh giá mô hình đe dọa trong Security Design Review

## 1. Vì sao phải review threat model?

Một nền tảng SaaS quản lý hóa đơn cho phép người dùng đăng nhập, xem hóa đơn và yêu cầu xuất dữ liệu. Đội phát triển đã vẽ Data Flow Diagram (DFD), chạy STRIDE và liệt kê mười đe dọa. Bản báo cáo được đánh dấu *Done*. Sau đó, ứng dụng bổ sung một background worker có quyền đọc dữ liệu của mọi tenant, một link tải file được tạo trong object storage, và một hệ thống analytics nhận bản sao các bản ghi nhạy cảm. Threat model không được cập nhật.

Số lượng đe dọa trên giấy vẫn là mười; hệ thống thực tế đã có thêm nhiều đường tấn công. Một người kiểm tra chỉ đếm số hàng trong threat register có thể kết luận sai rằng hoạt động threat modeling đã hoàn thành.

**Review threat model** là hoạt động đánh giá có cấu trúc về **độ đúng, độ đầy đủ tương xứng rủi ro, tính cập nhật và khả năng kiểm chứng** của mô hình đe dọa đối với hệ thống hoặc một thay đổi kiến trúc cụ thể. Review không chỉ sửa câu chữ, mà kiểm tra liệu mô hình có biểu diễn đúng tài sản, actors, trust boundaries, luồng dữ liệu, năng lực attacker, kịch bản gây hại và controls thực tế hay không.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là **đánh giá có bằng chứng** rằng thiết kế và hệ thống đáp ứng các mục tiêu bảo mật. Vì vậy, review threat model nối:

**Business objectives → assets → architecture & flows → attacker capabilities → threat scenarios → security requirements → controls → tests & evidence → findings → residual risk → reassessment.**

> Một threat model tốt không phải bản đồ của tất cả tấn công có thể tưởng tượng; nó là mô hình có phạm vi, giả định và giới hạn rõ ràng, đủ hỗ trợ các quyết định bảo mật quan trọng trong bối cảnh cụ thể.

### Câu hỏi mở đầu

Nếu một reviewer hỏi: “Worker xuất hóa đơn của tenant A có thể bị lạm dụng để lấy dữ liệu tenant B qua job replay hoặc tenant ID giả không?”, threat model cần chỉ ra **đường tương tác, nguồn tin cậy của tenant context, quyền của worker, threat scenario, control xử lý và bằng chứng kiểm tra**. Câu trả lời “API đã có MFA” không trực tiếp giải quyết nguy cơ đó.

## 2. Threat modeling và review threat model khác nhau thế nào?

| Hoạt động | Câu hỏi | Tác phẩm và đầu ra |
| --- | --- | --- |
| **Threat modeling** | Điều gì cần bảo vệ, attacker có thể làm gì, bằng đường nào, và nên xử lý ra sao? | Diagrams, asset register, threat scenarios, mitigations, risks. |
| **Review threat model** | Mô hình có phản ánh hệ thống thật, có bỏ sót điều trọng yếu, lý luận và controls có đủ căn cứ không? | Review findings, coverage assessment, required changes, verification plan. |
| **Security design review** | Thiết kế nói chung có đáp ứng yêu cầu bảo mật và rủi ro trong scope không? | Decision, architecture/control findings, approval conditions. |
| **Secure code/config review** | Các controls dự kiến được hiện thực đúng ở code/IaC/config chưa? | Implementation defects và evidence. |
| **Penetration testing** | Những attack paths thuộc test scope có thể bị khai thác thực tế không? | Test observations, impact, remediation/retest. |
| **Risk assessment** | Likelihood, impact, existing controls và residual risk theo phương pháp nào? | Risk rating, owner, treatment/acceptance. |
| **Control assessment/audit** | Một control được thiết kế và vận hành có hiệu quả trong scope/thời kỳ không? | Design/operating effectiveness và evidence. |

Các hoạt động bổ trợ nhau. Threat model không phải vulnerability scan; một scan PASS không tự chứng minh thiếu threat scenarios. Reviewer cũng không nên yêu cầu mọi threat model có PoC khai thác: với những giả định thiết kế, evidence có thể là diagram, data contract, policy và plan kiểm chứng.

### Review theo hướng kiểm tra giả thuyết

Một threat model thường chứa nhiều giả thuyết: “service A không thể gọi service B”, “tenant ID chỉ đến từ verified principal”, “signed URL không dùng được sau revoke”. Người review cần phân biệt giả thuyết đã kiểm tra, giả thuyết đang chờ xác minh và mệnh đề đã bị bằng chứng bác bỏ.

## 3. Mục tiêu và đầu ra của một vòng review

Một vòng review cần làm rõ bảy nhóm câu hỏi:

1. **Scope:** hệ thống, release, environments, users, workloads và dependencies đã được mô tả đúng?
2. **Assets:** tài sản/dữ liệu và hậu quả khi bị lộ, sửa, mất hoặc gián đoạn đã được nhận diện?
3. **Flows/boundaries:** các luồng chính, đặc biệt async/admin/export/backup/vender, đi qua những ranh giới nào?
4. **Threats:** attacker goals/capabilities và abuse cases có thực tế, trace được tới component/flow?
5. **Risk:** mức ưu tiên dựa trên impact, exposure và controls hiện hữu hay suy đoán?
6. **Controls/verification:** mitigation đặt đúng điểm, có owner và tiêu chí kiểm chứng?
7. **Lifecycle:** findings, exceptions, assumptions và triggers cập nhật model đã rõ?

### Bộ đầu ra tối thiểu

- **Review scope/version:** hệ thống, component, phiên bản thiết kế, build/release, environment và ngày review.
- **Coverage map:** assets, actors, trust boundaries, flows, external dependencies và omissions.
- **Threat/risk register đã hiệu chỉnh:** scenarios, attack paths, preconditions, impacted objectives, priority.
- **Controls/requirements mapping:** preventive, detective, responsive và recovery controls khi phù hợp.
- **Findings:** thiếu threat, giả định chưa xác minh, control không phù hợp, evidence gaps.
- **Verification plan:** test case, expected results, method, evidence source và owner.
- **Decision:** reviewed/conditional/rework/pending evidence, risk owner và conditions.
- **Reassessment triggers:** thay đổi dữ liệu, trust, identities, flows, code, incident hoặc công nghệ.

**Kết luận “Reviewed” không đồng nghĩa “No risk”.** Reviewer phải nêu mức tin cậy, phạm vi và những phần chưa đánh giá.

## 4. Khi nào phải review threat model?

Threat model cần được review theo **thay đổi rủi ro** và những mốc delivery quan trọng; một lịch cố định có thể bổ sung nhưng không thay các trigger.

### Các trigger thường gặp

| Trigger | Vì sao cần xem lại |
| --- | --- |
| Thiết kế một hệ thống, tính năng hoặc API mới. | Có assets, flows, actors và attack surface mới. |
| Thêm async worker, queue, event bus, scheduler hoặc data export. | Tăng trust boundaries, replay, quyền service và persistence của dữ liệu. |
| Đổi authentication, federation, authorization, tenant model. | Thay identity trust và khả năng vượt quyền. |
| Thêm vendor, SDK, webhook, AI/analytics hoặc data recipient. | Có thêm bên nhận dữ liệu hoặc mục đích xử lý. |
| Chuyển cloud account/region, Kubernetes, storage hoặc network topology. | Thay blast radius, control plane và shared responsibility. |
| Thay encryption/key management, secrets hoặc CI/CD trust chain. | Thay key trust, deployment authority và điểm thất bại chung. |
| Phát hiện incident, pentest finding, audit failure hoặc anomaly. | Giả định cũ có thể đã sai hoặc attack path mới được quan sát. |
| Thay data classification, khách hàng, traffic hoặc RTO/RPO. | Thay impact và tiêu chí ưu tiên. |
| Dependency/third-party end of life hoặc thay policy/standard. | Thay vulnerability exposure và khả năng vận hành control. |

### Phạm vi review theo mức thay đổi

- **Initial review:** rà toàn bộ system context, các boundaries và flows chính.
- **Focused change review:** xem phần thay đổi, nhưng phải theo **impact propagation** tới downstream và controls.
- **Periodic reassessment:** kiểm tra freshness, drift, open risks, incidents và assumptions.
- **Post-incident review:** xem attacker path thực tế, detective/control failures và khả năng ngăn tái diễn.

Focused review không có nghĩa chỉ nhìn component vừa sửa. Thêm một queue message có thể thay đổi logic authorization ở worker, object storage, audit và downstream consumers.

## 5. Input cần có trước khi review

Reviewer không phải đợi mọi tài liệu hoàn hảo, nhưng phải **biết bằng chứng nào có và đâu là unknown**.

| Input | Nội dung nên có | Review sử dụng để |
| --- | --- | --- |
| **Business context/impact** | Quy trình, người dùng, service criticality, hậu quả sự cố. | Ưu tiên assets và threats theo tác động thật. |
| **System context** | External actors, vendors, entry points, environments. | Xác định scope và trust với tổ chức khác. |
| **DFD/data lineage** | Processes, data stores, data flows, recipients và annotations. | Tìm nơi dữ liệu được xử lý và boundaries. |
| **Deployment/network view** | Cloud accounts, clusters, regions, ingress/egress. | Kiểm tra exposure và đường lateral movement. |
| **Identity/access model** | IdP, roles, policies, service accounts, admin paths. | Phân tích spoofing, privilege escalation, confused deputy. |
| **Data classification/privacy** | Loại dữ liệu, purpose, retention, owner, data transfers. | Tính impact và data disclosure threats. |
| **Architecture decisions** | ADR, phương án, assumptions và trade-offs. | Xác minh quyết định dựa trên threat đúng. |
| **Threat register cũ** | Scenarios, severity, controls, status, owner. | Review completeness và technical accuracy. |
| **Controls/test evidence** | Code, IaC, configuration, previous tests, runtime observations. | Không nhầm “planned mitigation” với implemented control. |
| **Incident/pentest/audit findings** | Các lỗi đã xảy ra, roots, remediation và open exceptions. | Thử bác bỏ assumptions và mở threat coverage. |
| **Operational design** | Logging, incident, backups, DR, rollout, rollback. | Xem detect/respond/recover và failure modes. |

### Preflight: kiểm tra tính nhất quán

Một DFD nói “worker chỉ gọi invoice API” nhưng IaC cho phép worker trực tiếp kết nối database thì phải ghi mâu thuẫn và làm rõ. Không tự tin một sơ đồ hơn runtime chỉ vì sơ đồ đã được ký duyệt.

## 6. Xác định scope, assumptions và exclusions

Scope phải cụ thể về:

1. Business capability và protected resources.
2. System components và runtime/service versions.
3. Users, administrators, external systems và workload principals.
4. Environments/regions/tenants, đặc biệt production và support.
5. Data classes, stores, event streams và bản sao.
6. Trust boundaries và internet/internal/vendor paths.
7. Threat actors và attacker capabilities giả định.
8. Thời điểm/thời kỳ review và điều kiện thay đổi.
9. Exclusions, lý do, người chấp thuận, expiry hoặc owner nếu là risk.

### Phân loại statement

- **Fact verified:** ví dụ runtime policy được đọc lại lúc T và cho thấy bucket private.
- **Design intent:** tài liệu yêu cầu bucket private, nhưng chưa có kiểm tra runtime.
- **Assumption:** ví dụ vendor gửi webhook signed; chưa kiểm tra toàn bộ clients.
- **Unknown/evidence gap:** chưa biết source nào có thể gọi worker trực tiếp.
- **Excluded:** nằm ngoài scope đã nêu; không có nghĩa rủi ro biến mất.

### Một scope hẹp vẫn phải trung thực

Review API authentication chỉ hỗ trợ kết luận về API và identity paths đã xét. Nó không tự chứng minh backup encryption, cloud admin hoặc cross-tenant data flow đã an toàn. Dùng tên scope trong conclusion để không phóng đại.

## 7. Assets và security objectives có được nhận diện đủ?

Threat model review không chỉ hỏi “attacker có lấy được password?” mà còn hỏi **tài sản gì quan trọng, bị hại bằng cách nào**.

### Asset categories

| Asset | Thuộc tính cần bảo vệ | Ví dụ thất bại |
| --- | --- | --- |
| **Business data** | Confidentiality, integrity, availability. | Invoice tenant B được đọc bởi tenant A. |
| **Identity/credentials** | Authenticity, confidentiality, lifecycle. | Stolen session, workload key hoặc recovery token. |
| **Transactions** | Integrity, non-repudiation/accountability khi cần. | Payment trạng thái sai do replay. |
| **Availability** | Capacity, continuity, recoverability. | Queue backlog làm invoice export không hoạt động. |
| **Security policy/config** | Integrity, authorized change, audit. | IAM policy bị mở rộng hoặc logging bị tắt. |
| **Cryptographic keys** | Confidentiality, authorized use, recovery. | KMS grant bị lạm dụng hoặc key mất khiến backup không thể restore. |
| **Build artifacts/pipeline** | Integrity, provenance, trusted deployment. | Runner bị compromise đẩy image độc hại. |
| **Personal data/metadata** | Privacy, confidentiality, purpose limitation. | Analytics event thu dữ liệu ngoài mục đích. |
| **Evidence/logs** | Integrity, completeness, confidentiality. | Attacker xóa audit để che hành động. |

### Review business impact

Hãy hỏi ai bị ảnh hưởng, mức dữ liệu/phạm vi tenant, khả năng khôi phục, tác động fraud, disruption, compliance hoặc uy tín. Không chấm tất cả data stores mức cao chỉ vì có database; nhưng cũng không xem metadata công khai mặc nhiên vô hại nếu có thể dùng để liên kết danh tính/hoạt động.

## 8. Actors và attacker capabilities: threat model có thực tế?

Một bản threat model chỉ có “external hacker” thường bỏ nhiều đường quan trọng.

### Các vai trò cần phân biệt

- **Legitimate external user:** có account hợp lệ nhưng cố truy cập tài nguyên ngoài quyền.
- **Malicious tenant admin:** có quyền trong tenant nhưng không có quyền platform-wide.
- **Compromised user/device:** attacker nắm session, token hoặc endpoint.
- **Compromised workload:** worker/pod/service principal có quyền nội bộ.
- **Insider/support/admin misuse:** người có quyền cao hoặc nhầm lẫn vận hành.
- **Supply-chain attacker:** ảnh hưởng dependency, build script, CI runner hoặc artifact.
- **Malicious/compromised vendor:** partner API hoặc third-party service có kết nối.
- **Unauthenticated external attacker:** không có credential nhưng có thể gửi request tới public ingress.

### Capabilities phải đủ cụ thể

Ví dụ, attacker tenant A biết invoice ID của B, có bearer token hợp lệ của A, có thể thay HTTP parameters và gửi job request, nhưng **không được giả định có quyền root database** trừ khi scenario xem xét compromised DB principal. Khi kết luận về workload compromise, giả định khác: attacker điều khiển một pod và sử dụng được workload identity được gán.

### Reviewer cần phát hiện hai cực đoan

1. **Attacker quá yếu:** “không thể gửi request sai” dù API public; threat bị loại sai.
2. **Attacker toàn năng:** “đã root mọi hệ thống” làm mọi rủi ro đều critical và không giúp chọn controls.

Năng lực attacker phải liên kết **entry point, prerequisites, exploitation effort, trust boundary, mục tiêu và security impact**.

## 9. DFD và data flow: kiểm tra độ đúng của bản đồ

DFD thường gồm **external entities, processes, data stores và data flows**. Reviewer kiểm tra các luồng từ source tới sink, chứ không chỉ số ô trong hình.

### Ví dụ SaaS nhiều tenant

~~~mermaid
flowchart LR
    U["Customer browser / mobile"] -->|"TLS: auth and actions"| G["Public API gateway"]
    IDP["Customer IdP"] -->|"Federation assertions"| G
    subgraph App["Application trust zone"]
      G --> API["Invoice API"]
      API --> AUTH["Authorization policy"]
      API -->|"Create job"| Q[("Message broker")]
      Q --> W["Export worker"]
    end
    subgraph Data["Restricted data zone"]
      API --> DB[("Shared tenant database")]
      W --> DB
      W --> OBJ[("Private object storage")]
    end
    U -->|"Download request"| DL["Download service"]
    DL --> OBJ
    API --> ANALYTICS["Analytics pipeline"]
    W --> LOG[("Audit and operational logs")]
    API --> LOG
    V["Email / delivery vendor"] <-->|"Limited data"| API
~~~

### Những luồng thường bị bỏ quên

- Background jobs, retry, queue replay và dead-letter queues.
- Export/download, signed URL/CDN, cache, search indexes, analytics và logs.
- Database replicas, backups, snapshots và disaster recovery.
- Control-plane/admin APIs, support tools, audit collectors.
- CI/CD pipeline, artifact registry, secrets retrieval và deployment.
- Partner APIs, webhooks, payment providers và third-party storage.
- Error paths, timeout/fallback, import/migration và bulk operations.
- Service-to-service traffic, cross-region replication và egress.

### Review flow contract

Mỗi luồng quan trọng nên có:

**Flow ID, producer, consumer, data class, purpose, principal/identity, authentication mechanism, authorization point, transport/storage, integrity/replay handling, retention, owner, monitoring và policy/evidence refs.**

Không phải mọi DFD đều chứa toàn bộ chi tiết này; có thể dùng **flow register** liên kết sơ đồ để tránh sơ đồ rối.

## 10. Trust boundaries: xem đúng nơi sự tin cậy đổi

**Trust boundary** không nhất thiết trùng với VPC, subnet hoặc firewall. Đó là chỗ giả định về **nguồn dữ liệu, quyền, danh tính, ownership, tenant hoặc control authority** thay đổi.

| Boundary | Reviewer cần hỏi |
| --- | --- |
| **Browser → API** | Input có bị tin là verified identity/tenant không? AuthN/AuthZ diễn ra ở đâu? |
| **Customer IdP → SaaS RP** | Issuer/subject/tenant mapping, audience, state/nonce/PKCE đúng không? |
| **API → queue** | Ai được produce, message có chống giả mạo/replay? |
| **Queue → worker** | Worker có xác minh job và tenant context hay tin payload nguyên vẹn? |
| **Worker → DB** | Workload identity có quyền quá rộng, có data scoping? |
| **Download → storage/CDN** | Có anonymous/public/capability access ngoài quyền? |
| **Production → analytics** | Có chuyển PII ngoài purpose hoặc retention không? |
| **Cloud account → account khác** | Trust policies, cross-account roles, key grants và audit? |
| **CI/CD → production** | Ai có thể ký artifact, deploy, thay policy/secret? |
| **Vendor → internal system** | Chữ ký, retry/replay, data transfer, downstream responsibility? |

**“Internal = trusted”** là giả định phải được biện minh, không phải câu trả lời. Nếu attacker nắm service identity hoặc một pod bị xâm nhập, khả năng lateral movement và confused deputy cần được xét.

### Dấu hiệu trust boundary bị thiếu

Một mũi tên trực tiếp từ browser tới database nhưng không nêu cách kiểm soát; nhiều tenants dùng chung cache key; một internal API không xác minh caller; queue message có field tenantId do client tự đặt; một third-party data processor được vẽ như module nội bộ.

## 11. STRIDE: kiểm tra có dùng đúng mục đích không

**STRIDE** là cách gợi ý các loại threat: Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service và Elevation of Privilege. Nó giúp đặt câu hỏi theo component/flow/trust boundary. Không nên biến STRIDE thành bài tập “điền đủ sáu chữ vào mọi ô”.

| Category | Câu hỏi review | Ví dụ cho SaaS |
| --- | --- | --- |
| **Spoofing** | Actor/workload/issuer có thể bị giả mạo? | Token sai issuer được chấp nhận. |
| **Tampering** | Message/config/data có thể bị sửa trái phép? | Queue job đổi tenant context. |
| **Repudiation** | Có khó chứng minh ai đã làm gì trong scope? | Không liên kết được export với user/job. |
| **Information Disclosure** | Data có thể ra khỏi quyền/purpose? | Signed URL cho phép đọc file B. |
| **Denial of Service** | Tài nguyên critical bị làm cạn/ngừng? | Export queue bị spam, worker starvation. |
| **Elevation of Privilege** | Có thể tăng quyền hoặc bypass enforcement? | Service account wildcard được dùng làm confused deputy. |

### Cách review STRIDE

1. Đọc từng flow và boundary, xét category **có ý nghĩa** với loại thành phần đó.
2. Viết scenario cụ thể: ai, làm gì, qua đâu, asset nào và hậu quả gì.
3. Ghi prerequisites và existing controls; đừng chỉ chép “Spoofing” thành một finding.
4. Tìm attack paths kết hợp nhiều categories.
5. Ghi threat không áp dụng với lý do, tránh vừa “n/a” vô căn cứ vừa “phải có đủ 6”.

### Công cụ khác có thể bổ trợ

- **Abuse/misuse cases:** lạm dụng business workflows và quyền hợp lệ.
- **Attack trees/path analysis:** nhiều bước để đạt attacker objective.
- **LINDDUN:** khơi gợi privacy threats nếu data/purpose/identity cần đánh giá.
- **Kill-chain/ATT&CK-inspired thinking:** xem post-compromise, lateral movement, detection.
- **Risk workshops:** người vận hành/khách hàng hỗ trợ impact và điều kiện khai thác.

Các phương pháp giúp đặt câu hỏi, **không tự là bằng chứng controls đã được kiểm chứng**.

## 12. Threat scenario đủ tốt trông như thế nào?

Một scenario kiểm chứng được nên bao gồm:

1. **Threat ID và asset/flow ID.**
2. **Attacker goal:** mục tiêu gây hại.
3. **Attacker capabilities/starting position.**
4. **Preconditions:** điều kiện trước khi exploit.
5. **Entry point/trust boundary.**
6. **Attack steps:** chuỗi thao tác hợp lý.
7. **Security property violated:** confidentiality/integrity/availability/authenticity/accountability/privacy.
8. **Affected scope/impact:** resource, tenant, data, business harm.
9. **Existing/proposed controls và evidence state.**
10. **Residual risk, owner, treatment và tests.**

### Ví dụ chưa đủ

“Attacker có thể lấy hóa đơn.” — Không rõ actor, flow, điều kiện, tác động, mitigation hoặc test.

### Ví dụ tốt hơn

**TH-EXP-03: Cross-tenant export via worker confused deputy.** Attacker có account viewer trong tenant A, biết invoice ID thuộc tenant B, có thể gửi export request chứa object ID tùy ý. API chỉ kiểm tra quyền tạo job trong tenant A rồi đưa message có tenantId từ client. Worker dùng database role đọc mọi tenant và tin context từ message, tạo file export. Attacker lấy link của job và tải invoice B.

**Impact:** lộ Confidential data giữa tenants. **Boundary:** browser→API→queue→worker→DB→storage. **Control cần kiểm:** server-owned job, principal/resource authorization, worker least privilege, download authorization. **Tests:** forged tenant/object ID, queue replay, wrong principal download, effective DB grants. **Evidence:** observed outcomes và policies đúng release.

## 13. Attack paths và cách liên kết các threats

Một threat thường cần nhiều điều kiện nối nhau. Review chỉ xem từng ô STRIDE độc lập có thể bỏ qua tổ hợp tấn công.

~~~mermaid
flowchart TD
    GOAL["Goal: obtain another tenant's invoice"] --> A["Acquire legitimate tenant A account"]
    A --> B["Discover/guess tenant B object ID"]
    B --> C["Invoke export API with foreign object"]
    C --> D{"Object-level authorization enforced?"}
    D -- "Yes" --> BLOCK["Attack path blocked at API"]
    D -- "No" --> E["Queue job with untrusted tenant context"]
    E --> F{"Worker verifies job owner and scope?"}
    F -- "Yes" --> BLOCK2["Attack path blocked at worker"]
    F -- "No" --> G["Worker reads cross-tenant DB rows"]
    G --> H{"Download authorized for same actor/resource?"}
    H -- "Yes" --> BLOCK3["Attack path blocked at download"]
    H -- "No" --> IMPACT["Confidential data disclosure"]
~~~

### Reviewer cần xem các đường phụ

- Có thể gọi worker callback trực tiếp mà không qua API?
- Có thể giả producer quyền cao trong message broker?
- Có thể đọc output file bằng cloud storage permissions ngoài download service?
- Queue DLQ có chứa payload nhạy cảm và cho team khác đọc?
- Nếu một control fail nhưng control khác vẫn hoạt động, outcome là gì?
- Các controls có thật sự độc lập hay cùng phụ thuộc vào một principal/policy?

### Điều không được suy từ attack tree

Sơ đồ có ba điểm “block” không chứng minh cả ba đã triển khai hiệu lực. Một **planned control** không được coi là giảm current residual risk trước khi có bằng chứng.

## 14. Kiểm tra logic của risk scoring

Một threat scenario có thể khả thi nhưng impact rất khác nhau theo dữ liệu, loại khách hàng và blast radius. Reviewer cần kiểm tra **định nghĩa likelihood/impact, phương pháp chấm, assumption và chất lượng evidence**.

| Dimension | Câu hỏi |
| --- | --- |
| **Exposure/reachability** | Entry point có public? Cần account hay network position? |
| **Exploitability** | Cần những preconditions, kỹ năng, tài nguyên nào? |
| **Privileges required** | Attacker có quyền gì và có thể tăng quyền? |
| **Asset sensitivity** | Loại dữ liệu/tài sản nào, mất gì? |
| **Blast radius** | Một tenant, toàn hệ thống, một region hay control plane? |
| **Detectability/response** | Có event, alert, containment và rollback? |
| **Control effectiveness** | Controls có được triển khai, test, duy trì không? |
| **Uncertainty** | Điều gì chưa biết hoặc chưa quan sát? |

### Inherent, current residual và target residual

- **Inherent risk:** rủi ro trước controls theo cách tổ chức định nghĩa.
- **Current residual risk:** rủi ro với controls đang **thực sự vận hành**.
- **Target residual risk:** mức dự kiến sau remediation và verification.

### Không dùng điểm số để che critical failure

Một risk matrix “3 × 4 = 12” chỉ có ý nghĩa nếu likelihood/impact có rubric và evidence. Nếu cross-tenant access đã được xác minh, việc có nhiều controls khác hoặc giảm điểm theo cảm tính không thay đổi finding. Risk acceptance phải theo thẩm quyền, không phải reviewer tự “approve” một lỗi bắt buộc.

## 15. Kiểm tra assumptions và bằng chứng trái chiều

Mô hình đáng tin phải thể hiện **đâu là điều đã biết, đâu là điều cho rằng đúng**.

### Assumption register minh họa

| ID | Assumption | Cách xác minh | Trạng thái nếu chưa có evidence |
| --- | --- | --- | --- |
| A-01 | Worker không thể kết nối trực tiếp public ingress. | Effective routes/firewall và direct-path test. | UNKNOWN |
| A-02 | Tenant context được tạo từ verified principal. | Code review, negative spoof tests, trace. | UNKNOWN |
| A-03 | Queue chỉ chấp nhận approved producers. | Broker ACL, IAM effective permissions, denied publish test. | UNKNOWN |
| A-04 | Download link hết hạn và không bypass owner. | Real storage policy, wrong-principal/expired tests. | UNKNOWN |
| A-05 | Analytics event không chứa PII ngoài allowlist. | Schema/data sample test, consumer review. | UNKNOWN |
| A-06 | Audit collector luôn nhận privileged actions. | Source inventory, ingestion health, controlled event test. | UNKNOWN |

### Reviewer phải tìm contradiction

Nếu architecture design nói database role scoped nhưng live grants có quyền đọc mọi schema, phải ghi evidence mâu thuẫn. Nếu threat model nói link download không thể chia sẻ nhưng file dùng bearer pre-signed URL không ràng buộc recipient, cần xem lại claim theo **semantics thực tế của capability URL**.

### Khả năng truy vết

Mỗi assumption quan trọng cần owner, thời hạn xác minh, evidence reference và trigger đánh giá lại. “Unknown” không tự có nghĩa vulnerability đã được chứng minh; nó là **lỗ hổng trong assurance argument** cần xử lý.

## 16. Từ threat tới security requirement có thể kiểm chứng

Một threat model có thể nêu đúng rủi ro nhưng thiếu **security requirements**; khi đó thiết kế không có tiêu chí nghiệm thu.

| Threat | Requirement cụ thể | Controls có thể dùng | Cách chứng minh |
| --- | --- | --- | --- |
| Token từ IdP sai được nhận. | Chỉ issuer/audience/transaction hợp lệ tạo principal. | OIDC/SAML validation, trust registry. | Wrong issuer/audience/state negative tests. |
| User A xem invoice B. | Mọi READ/EXPORT phải có object/tenant authorization. | Policy at service/resource, scoped queries. | Cross-tenant negative tests trên mọi data path. |
| Worker lấy dữ liệu ngoài job. | Worker chỉ xử lý server-owned jobs và effective grants phù hợp. | Job integrity, scoped workload IAM. | Forged/replayed job và denied DB access tests. |
| Storage lộ file. | Export files private và download đúng quyền/thời hạn. | Storage IAM, authorized download, expiration. | Anonymous/wrong principal/expired tests. |
| CI runner bị chiếm. | Build principal không có quyền production ngoài job. | Ephemeral identity, separated deploy credentials. | Effective permission, artifact provenance tests. |
| Log bị xóa. | Critical audit events được thu và bảo vệ theo policy. | Central logging, source health, limited delete privileges. | Disable-source simulation, access/retention review. |
| Không restore được backup. | Backup, keys và DR runbook phải hỗ trợ mục tiêu recovery. | Isolated backup, KMS recovery, restore exercises. | Integrity reconciliation, measured RTO/RPO. |

### Công thức viết requirement

**[Principal] + [action] + [resource/scope] + [context/condition] + [expected allow/deny/response] + [verification]**.

Ví dụ **REQ-AUTHZ-07:** Đối với request READ/EXPORT invoice qua API, worker và download service trong production, chỉ principal có quyền trên **object và tenant đã được server xác minh** mới được truy xuất. Trường tenantId từ browser/queue payload không tự cấp quyền. Cross-tenant attempts phải bị từ chối và không tiết lộ dữ liệu.

Reviewer cần kiểm tra requirement có **testable outcome**, không chỉ “ứng dụng phải dùng authorization tốt”.

## 17. Review control placement và complete mediation

Control hiệu quả cần nằm ở điểm có thể ngăn hoặc phát hiện hành động trong mô hình đe dọa. Một API gateway bảo vệ public ingress không đủ nếu internal service hoặc background worker đi thẳng tới database.

### Câu hỏi về placement

1. Attacker có thể đến tài sản bằng một đường không qua control không?
2. Control quyết định dựa trên dữ liệu đáng tin hay user-controlled claims?
3. Kiểm tra quyền có ở **mọi resource/action path quan trọng** không?
4. Khi request chuyển từ synchronous sang asynchronous, context và quyết định có còn hợp lệ?
5. Control có đảm bảo minimum scope hay dùng một tài khoản toàn quyền?
6. Failure của control có cho phép truy cập theo mặc định không?
7. Có phát hiện bypass, drift hoặc silent failure?

### Phân lớp defense-in-depth

| Layer | Ví dụ control | Giới hạn |
| --- | --- | --- |
| Gateway | AuthN, generic routing, rate control. | Không biết object ownership trong nhiều ứng dụng. |
| Application | Role/resource/tenant authorization. | Có thể bị bypass qua worker, query hoặc đường direct. |
| Data access | Tenant-scoped repository, RLS nếu phù hợp. | Shared privileged accounts có thể bypass policy. |
| Workload/platform | Least privilege IAM, network boundaries. | Không thay business authorization. |
| Download/storage | Private buckets, scoped download access. | Bearer link có thể tiếp tục sống khi user revoke. |
| Detection | Audit, anomaly alerts, collector health. | Không tự ngăn lộ dữ liệu đã xảy ra. |

Reviewer phải xem lớp có **độc lập** hay cùng dùng một policy/identity có thể fail chung. Đếm ba công cụ không chứng minh ba lớp phòng vệ độc lập.

## 18. Review authentication, identity và authorization threats

Những câu hỏi cốt lõi:

- Có tất cả login paths, recovery, support, admin, API, service và machine identities không?
- IdP trust registry, issuer, subject, audience, role mapping có sai boundary?
- Một token hợp lệ có bị dùng sai API, tenant hoặc purpose?
- Authenticator enrollment/recovery có yếu hơn main login?
- Session/token/cache có còn quyền sau khi role/account bị revoke?
- Workload credentials sống lâu, dùng chung, ghi log hoặc có wildcard grants?
- Có phân biệt authentication với authorization theo **resource/action**?
- Có cơ chế positive, negative và failure-mode tests?

### Ví dụ review identity boundary

Hai tenants dùng IdP khác nhau nhưng cùng email user@example.invalid. Application dùng email làm key global và ghép accounts. Threat là **account confusion/cross-tenant session binding**. Test cần cùng email với **issuer và subject khác nhau**, không chỉ dùng login success với mỗi tenant.

### Root cause thường nằm ngoài lớp authN

Một backend service có mTLS certificate hợp lệ nhưng được dùng như **confused deputy** để đọc dữ liệu tenant khác. Reviewer phải phân biệt **peer authentication** có thể PASS và **business authorization** có thể FAIL.

## 19. Review data threats, privacy và vòng đời dữ liệu

Data threat review phải theo **bản sao, chuyển đổi và người nhận**, không chỉ database chính.

### Câu hỏi theo data lifecycle

1. Dữ liệu vào từ đâu, có phân loại và validation không?
2. Data store chính, cache, search index, queue, analytics, logs và backup có gì?
3. Dữ liệu ra ngoài qua export, CDN, email, vendor, API, metrics hoặc debug dumps?
4. Ai có quyền đọc/sửa/xóa mỗi bản sao? Có policy riêng cho support/admin?
5. Encryption at rest/in transit/key usage có phù hợp với threats?
6. Retention, deletion, data subject requests và recovery copies xử lý ra sao?
7. Dữ liệu có chuyển qua region hoặc third-party khác với requirement không?
8. Có đường dữ liệu phụ chưa được biết như DLQ, debug trace hoặc ETL job?

### Phân biệt bảo mật và riêng tư

Confidentiality controls bảo vệ trước truy cập trái phép; privacy review còn hỏi **purpose, minimization, data linkage, consent/authority nơi áp dụng, retention và khả năng thực hiện quyền**. Một data pipeline được mã hóa và có IAM vẫn có thể xử lý dữ liệu vượt mục đích.

### Một kịch bản LINDDUN-oriented

Analytics pipeline nhận email, invoice history và device identifiers để tính báo cáo tổng hợp. Dù public API không bị hack, dữ liệu có thể cho phép **linkability** giữa các danh tính hoặc vượt purpose. Reviewer nên yêu cầu data field allowlist, recipient/retention map, access policy và kiểm thử event schemas. Không tự suy áp dụng một luật cụ thể nếu chưa xác định jurisdiction/obligation.

## 20. Review cloud, network và container threats

Cloud architecture thêm **control-plane identities, regions, managed service boundaries, IAM policies, storage permissions và ephemeral workloads**.

| Component | Threat reviewer cần xét | Evidence/test |
| --- | --- | --- |
| Cloud account/project | Shared admin or cross-account trust tạo blast radius rộng. | IAM trust graph, effective privileges và denied-use tests. |
| Public ingress | Admin path hoặc alternate origin bypass WAF/gateway. | Route inventory, direct-path negative test. |
| VPC/VNet/egress | Lateral movement, metadata endpoint misuse, unrestricted egress. | Flow graph, effective network policy, canary tests. |
| Kubernetes API | Cluster-admin broad access, unaudited changes. | RBAC, auth audit, restricted admin paths. |
| Pods/service accounts | Stolen workload identity, namespace assumptions. | Service account grants, network policies và token handling. |
| Container images | Dependency compromise hoặc tampered artifact. | Provenance, signing/verification, scan and deployment gate. |
| Storage/bucket | Public access, backup/snapshot leaks. | Effective policy, anonymous/wrong-principal tests. |
| KMS/secrets | Key admin và data access trùng, secret lộ qua CI/log. | Key grants, denied decrypt tests, rotation evidence. |
| Observability | Logs có secrets hoặc attacker disable collector. | Source inventory, health checks, log access review. |

### Namespace không phải isolation tuyệt đối

Nếu threat model coi mỗi Kubernetes namespace là ranh giới cứng giữa các tenants, reviewer phải kiểm tra **node, cluster admin, network policy, service account, volumes và shared control plane**. Tùy threat và contract, cần isolation mạnh hơn như tách cluster/account hoặc tăng controls.

### Shared responsibility

Không dùng tuyên bố “provider chịu trách nhiệm bảo mật” thay cho mapping control cụ thể. Provider có thể quản lý phần hạ tầng vật lý hoặc managed-service layer; khách hàng vẫn phải cấu hình identity, networking, data, workload và phần quan sát. Evidence provider phải đúng **service, scope, region và time period**, còn customer configuration phải được kiểm tra riêng.

## 21. Review supply-chain và deployment trust model

Một attacker không cần đi qua public API nếu có thể sửa artifact được triển khai hoặc lấy deployment credentials.

### Attack path điển hình

1. Một dependency độc hại chạy code trong CI build.
2. CI runner có environment credential với quyền deployment và đọc production secrets.
3. Attacker lấy credential hoặc sửa build artifact.
4. Artifact được đẩy vào registry và production không xác minh provenance/signature.
5. Workload độc hại có quyền truy cập dữ liệu khách hàng.

### Checklist review

- Repository branches/tags, protected changes, code review và ownership.
- CI runner isolation/ephemeral status và quyền truy cập secrets/network.
- Dependency provenance, pinning, SBOM và vulnerability management.
- Artifact signing, provenance verification và signing-key custody.
- Tách build và deploy authorities; production change approval.
- IaC/policy-as-code, drift detection, rollback.
- External registries, packages, build plugins và vendor integration.
- Trace từ source commit → build → image digest → deployment → runtime.

**“Pipeline có SAST”** chỉ cho thấy một lớp kiểm soát; không chứng minh workflow không có đường publish artifact giả hoặc runner không có excessive privileges.

## 22. Review encryption, secrets và key dependency threats

Khi có data protection controls, threat model review phải hỏi **ai được giải mã, ký, xoay, vô hiệu và khôi phục khóa**.

| Threat | Câu hỏi review |
| --- | --- |
| Secret leaked | Secret ở CI, image, env, logs, backups và support tooling? |
| Key misuse | Identity nào có Decrypt/Sign/GenerateDataKey, có tách admin/data? |
| Ciphertext disclosure | Encryption scope bao phủ database, snapshots, exports, analytics và transit? |
| Token/signature compromise | Signing key có bảo vệ, audit, version/rotation và incident response? |
| Destructive key loss | Old backup có restore bằng key version cần thiết? |
| Insecure fallback | KMS timeout có dẫn tới plaintext storage hoặc bypass không? |
| Misplaced trust | mTLS key/certificate có phù hợp identity/authorization boundary? |

### Security vs availability

Một key được bảo vệ rất chặt nhưng không thể dùng để restore backup có thể phá mục tiêu availability. Reviewer nên đánh giá **cryptographic dependency trong recovery path**, không chỉ encryption flag hoặc cipher name.

## 23. Review event-driven/async threats và trạng thái giao dịch

Async architecture thường có những threat scenarios khác synchronous request.

### Cần review producer–broker–consumer

- Producer identity và topic/queue write permissions.
- Message authenticity/integrity và trusted server-owned context.
- Tenant/actor/resource fields được tạo ở đâu, có bị spoofed không?
- Consumer authorization có được kiểm tra độc lập khi thực hiện side effect?
- Retry, duplicate, replay, ordering và idempotency.
- Dead-letter queue có dữ liệu nhạy cảm, retention và read permissions nào?
- Backpressure, overload và worker starvation có gây DoS không?
- Consumer schema evolution và field allowlist có tăng exposure?
- Audit/correlation từ user request qua job tới kết quả cuối.

### Ví dụ threat về giao dịch

API commit DB rồi phát event; broker lỗi khiến event không được gửi. Payment reconciliation có thể mất tính toàn vẹn nếu downstream dựa hoàn toàn vào event. Reviewer cần hỏi có **transactional outbox**, durable handoff hoặc reconciliation mechanism phù hợp không, và đã test crash window chưa. Không nên coi exactly-once end-to-end là điều tự động có từ tên broker.

### Authorization continuity

Một user có quyền tạo job tại thời điểm T0 nhưng mất quyền lúc T1 trước khi worker chạy. Requirement phải quy định semantics: job có được tiếp tục không, quyền có cần kiểm tra lại không, file download bị xử lý thế nào. Reviewer không thể kết luận khi chưa biết **business policy và threat model**.

## 24. Review failure modes, abuse cases và resilience

Nhiều threat models chỉ vẽ happy path. Một review nghiêm túc còn hỏi hệ thống làm gì khi các dependency thất bại.

| Failure | Rủi ro bảo mật/vận hành | Điều cần chứng minh |
| --- | --- | --- |
| IdP không khả dụng | Mở login bypass hoặc không thể xử lý emergency access. | Đúng fail-secure policy, controlled recovery. |
| PDP/auth service timeout | Cho phép request không được đánh giá. | Unknown/deny/restrict behavior theo requirement. |
| Queue backlog | DoS, mất event, duplicate side effects. | Backpressure, DLQ, idempotency và monitoring. |
| KMS unavailable | Data không giải mã được hoặc lưu plaintext fallback. | No unauthorized fallback, recovery design. |
| Network partition | Split-brain, stale authz cache, partial writes. | Consistency/reconciliation và timeouts. |
| Audit collector im lặng | Không phát hiện tấn công và mất evidence. | Health alert, unknown status, incident handling. |
| Storage/CDN misconfig | File công khai hoặc link không hết hạn. | Effective policy và anonymous/capability tests. |
| Backup key mất | DR không thể khôi phục. | Restore drill với key dependencies. |
| Vendor outage/compromise | Data transfer thất bại, callback giả. | Signed/replay-safe webhooks, fallback, data limits. |

### “Fail closed” không phải câu trả lời đủ

Một hệ thống fail closed đúng điểm có thể bảo vệ confidentiality nhưng cũng có thể làm gián đoạn dịch vụ thiết yếu. Reviewer cần kiểm tra **approved failure behavior cho từng asset/action**, cách thông báo/rollback/recovery và risk trade-offs. Không biến khẩu hiệu thành yêu cầu không khả thi.

## 25. Review controls: Prevent, Detect, Respond, Recover

Mỗi threat nên có treatment rõ; không phải mọi threat đều cần đủ bốn lớp, nhưng reviewer phải kiểm tra **rủi ro còn lại khi lớp phòng ngừa thất bại**.

| Loại control | Ví dụ cho cross-tenant export | Evidence |
| --- | --- | --- |
| **Preventive** | Object/tenant authz, server-owned job, scoped worker permissions. | Code/config, policy, negative tests. |
| **Detective** | Audit correlation actor→job→file, anomaly on bulk export. | Event schema, alert tests, source health. |
| **Responsive** | Revoke tokens/jobs, quarantine worker, disable export route. | Controlled incident drill và time-to-effect. |
| **Corrective/recovery** | Fix permissions, regenerate affected files, retest/restore. | Change record, deployment, retest và data reconciliation. |

### Planned, implemented và verified

- **Proposed:** control được đề xuất hoặc đang nằm trên diagram.
- **Implemented:** code/config được triển khai trong scope.
- **Design assessed:** assessor đánh giá control có hợp lý về kiến trúc.
- **Operating tested:** có evidence control thực thi đúng trong một kỳ/test set.
- **Exception/partial:** có khoảng trống được quản trị hoặc chưa xử lý.

Không đánh đồng *proposed mitigation* với *current control*. Nếu threat hiện chưa có prevention nhưng có detective alert, phải đánh giá liệu alert có đủ thời gian/ngưỡng để giảm impact thật hay không.

## 26. Từ threat model review tới verification plan

Review không kết thúc khi gắn nhãn high/medium/low. Phải chuyển threat quan trọng thành **verification scenarios** và evidence cụ thể.

### Test case đủ chặt

1. Threat ID, requirement ID và related control.
2. Scope: component, release, environment, tenant/resource population.
3. Preconditions và attacker capabilities.
4. Input/attack attempt, dùng canary/synthetic dữ liệu khi có thể.
5. Expected outcome do owner xác nhận.
6. Observed outcome tại API, worker, data, storage và logs.
7. Evidence artifact, source, time, policy/config version.
8. PASS/FAIL/INCONCLUSIVE, finding và retest.

### Test matrix minh họa

| Test ID | Threat scenario | Expected |
| --- | --- | --- |
| **TM-T01** | User A đọc invoice của tenant B bằng ID trực tiếp. | DENY, không lộ data qua body/error/cache. |
| **TM-T02** | User đổi tenantId trong export request. | Tenant context lấy từ principal, không từ client claim. |
| **TM-T03** | Forge/replay queue job cho tenant B. | Worker kiểm tra server-owned job và idempotency. |
| **TM-T04** | Worker principal truy vấn dữ liệu ngoài scope. | Effective grants/data policy deny. |
| **TM-T05** | Anonymous user tải file trong object storage. | DENY theo storage/download design. |
| **TM-T06** | User B dùng link của A hoặc link đã hết hạn. | Resource access đúng recipient/expiration semantics. |
| **TM-T07** | Token sai issuer/audience gọi API. | Không tạo principal hoặc authorize action. |
| **TM-T08** | Compromised service gọi KMS ngoài nhiệm vụ. | Cryptographic operation deny và audit. |
| **TM-T09** | Vendor webhook sai chữ ký hoặc replay. | Reject và không tạo side effect không hợp lệ. |
| **TM-T10** | Pod gọi internal admin port trái scope. | Segmentation/identity enforcement deny. |
| **TM-T11** | CI artifact không có provenance theo policy. | Deployment gate từ chối. |
| **TM-T12** | Producer/consumer xử lý duplicate event. | Idempotent hoặc reconcile theo contract. |
| **TM-T13** | Security log collector bị tắt trong drill. | Source health alert và evidence-gap status. |
| **TM-T14** | KMS hoặc IdP timeout. | Failure behavior theo approved requirement. |
| **TM-T15** | Restore backup cùng key dependencies. | Dữ liệu nguyên vẹn, RTO/RPO đạt mục tiêu đã duyệt. |
| **TM-T16** | Analytics event thêm PII ngoài schema allowlist. | Bị ngăn hoặc được phát hiện theo data contract. |
| **TM-T17** | Cached authorization sau role revocation. | Effective deny trong cửa sổ được phê duyệt. |
| **TM-T18** | Signed URL dùng qua CDN alternate path. | Không bypass policy/capability constraints. |
| **TM-T19** | Admin thay federation trust configuration không đủ quyền. | DENY, audit và approval controls. |
| **TM-T20** | App bypass gateway qua direct service route. | Từ chối trái authorization requirement. |

### Không làm tổn hại hệ thống khi kiểm thử

Tất cả tests phải nằm trong authorization và môi trường được kiểm soát. Không thực hiện truy cập chéo dữ liệu khách hàng thật, vô hiệu logging production, đoạt secret hoặc tạo workload overload nếu không có phạm vi và kế hoạch kiểm soát rõ. Dùng **synthetic tenants, dummy resources, canary identities và failure injection có guardrails**.

## 27. Đánh giá coverage của threat model: không đếm hàng

**Coverage** nên mô tả phạm vi tài sản, flows, boundaries và threat objectives đã được đánh giá, không đơn giản là số STRIDE rows.

| Dimension | Cách đo có ích | Caveat |
| --- | --- | --- |
| **Assets** | High-impact assets có owner/classification và threat consideration / assets trong inventory được kiểm tra độc lập. | Asset inventory có thể thiếu. |
| **Flows** | Critical flows có threat analysis và trust validation / flows trong scope. | Phải phát hiện hidden async/vendor flows. |
| **Boundaries** | Trust boundaries có authentication/authorization/data controls review / boundaries đã map. | Không có guarantee tìm hết unknown boundaries. |
| **Actor capabilities** | Principal/attacker categories được xét trên entry points phù hợp. | Có category không có nghĩa scenario quality tốt. |
| **Attack paths** | Các high-risk attack paths từ scope có tests và outcomes. | Suite có thể không đại diện toàn threat space. |
| **Threat-to-control trace** | Material threats có requirement/control owner/status. | Control mapped có thể chưa vận hành. |
| **Threat-to-test trace** | Material threats có test/assessment evidence còn mới. | Test có thể không đo đúng threat. |
| **Freshness** | Model đã reassess khi flows/identities/risks thay đổi. | Ngày edit gần không tự bảo đảm coverage. |

### Sample denominator

Ví dụ hệ thống có **50 critical flows theo inventory đối chiếu**, trong đó 43 flow có threat analysis hoàn tất. Có thể ghi **43/50 coverage trên population đó = 86%**, nhưng không được kết luận “86% hệ thống an toàn”. Reviewer cần xem **7 flows thiếu thuộc loại nào**, có critical bypass không và inventory có đáng tin không.

### Unknown không được tự biến thành N/A

Nếu chưa biết downstream của event hoặc ai đọc một DLQ, trạng thái là **UNKNOWN/needs investigation**. *Not Applicable* đòi hỏi rationale có thể kiểm tra. Tách hai trạng thái để dashboard không trở nên xanh giả.

## 28. Finding của threat model review: yêu cầu đủ để sửa

Một review finding cần mô tả **sự sai lệch giữa kỳ vọng và thực tế trong scope**, không chỉ lời phê bình chung chung.

| Trường | Ý nghĩa |
| --- | --- |
| **ID/title** | Mã duy nhất và phát biểu vấn đề. |
| **Scope/version** | Service, component/flow, release, environment, date. |
| **Expected requirement** | Điều kiện hoặc policy/ADR cần đáp ứng. |
| **Observed evidence** | Diagram, config, tests, code hoặc logs có nguồn và thời gian. |
| **Threat/attack path** | Ai có thể làm gì, đi qua boundary nào. |
| **Impact/risk rationale** | Business assets, blast radius, uncertainty và severity basis. |
| **Root-cause hypothesis** | Thiếu context, incorrect trust, misplaced control, stale model? |
| **Owner/due date** | Người xử lý và mốc cần xác nhận. |
| **Remediation** | Cập nhật model, sửa control, thêm test/telemetry hoặc risk handling. |
| **Retest acceptance** | Expected outcome và evidence cần để đóng. |
| **Exception** | Risk owner, scope, expiry, compensating controls nếu có. |

### Phân biệt ba dạng finding

- **Model defect:** DFD thiếu export/download flow; chưa nhất thiết chứng minh product có lỗ hổng.
- **Design weakness:** Control dự kiến đặt sai boundary, ví dụ chỉ authz tại UI.
- **Implementation/control failure:** Runtime thực tế trả dữ liệu B cho A; có evidence FAIL.

Không gộp ba loại vào cùng một nhãn “vulnerability confirmed” nếu chưa có bằng chứng khai thác; nhưng cũng không hạ thấp một control failure đã được xác minh thành “documentation issue”.

## 29. Review decision và trạng thái: không “approve” quá mức

Một cuộc review có thể kết thúc bằng các trạng thái:

- **Reviewed – sufficient for current design phase:** mô hình đủ để hỗ trợ quyết định trong scope nhưng implementation tests còn ở phase sau.
- **Approved with conditions:** thiếu phần có thể hoàn thành theo điều kiện, owner, deadline và release gate rõ.
- **Needs rework:** thiếu/sai trust boundaries hoặc bỏ attack paths trọng yếu khiến quyết định thiếu cơ sở.
- **Pending evidence:** design có vẻ phù hợp nhưng assumptions/controls chưa được kiểm chứng.
- **Not assessed:** input hoặc scope không đủ, không có kết luận về hiệu quả.
- **Failed/critical finding:** có evidence trực tiếp cho thấy requirement trọng yếu không được đáp ứng.

### Vấn đề độc lập đánh giá

Người tạo threat model có thể giải thích và sửa sai, nhưng người đánh giá cần đủ độc lập tương xứng với rủi ro. Với hệ thống rất quan trọng, review bởi người không phải tác giả hoặc reviewer có quyền thách thức giả định là hữu ích; không cần biến mọi thay đổi nhỏ thành hội đồng nhiều cấp.

### Không thay quyền của risk owner

Reviewer có thể nhận định “không đủ evidence” hoặc “cần redesign”, nhưng việc chấp nhận residual risk và ngoại lệ phải được quyết định theo thẩm quyền của tổ chức và nghĩa vụ thực tế.

## 30. Quy trình workshop review threat model từng bước

Review có thể thực hiện bất đồng bộ qua document/PR hoặc trong workshop có đại diện các nhóm. Với kiến trúc phức tạp, workshop thường giúp phát hiện nhanh assumptions sai vì những người hiểu code, dữ liệu và vận hành **nhìn các ranh giới khác nhau**.

### Trước workshop

1. Chỉ định facilitator, model owner, decision owner, reviewer và note-taker.
2. Gửi scope/architecture version, risk context, DFD, inventory, current threat register và open questions.
3. Thống nhất expected outcomes: tìm gaps, chọn treatment, phân công evidence — **không phải ký duyệt mặc định**.
4. Đánh dấu data/flows trọng yếu, thay đổi mới và findings từ incident/pentest.
5. Chuẩn bị sandbox/canary để minh họa khi cần, nhưng không biến workshop thành destructive testing.

### Trong workshop: một trình tự hiệu quả

| Giai đoạn | Điều phối viên hỏi | Đầu ra |
| --- | --- | --- |
| **Scope sanity check** | Có asset, route, actor hoặc region nào ngoài sơ đồ? | Scope corrections, open unknowns. |
| **Walk a real request** | Từ browser/client tới data/worker/export, quyền đổi ở đâu? | Verified flows/trust boundaries. |
| **Attacker perspective** | Nếu nắm một account/session/pod, có thể làm gì? | Attack paths, prerequisites. |
| **Framework prompts** | STRIDE/abuse/privacy/supply-chain câu nào chưa được xét? | Candidate threats. |
| **Prioritization** | Rủi ro nào ảnh hưởng nhiều tenants/critical data? | Risk rationale và ưu tiên. |
| **Control reasoning** | Mỗi mitigation thực thi ở đâu, có bypass/dependency nào? | Requirement/control links. |
| **Evidence challenge** | Cái nào là design intent, cái nào có effective config/test? | Evidence gaps và verification tasks. |
| **Decision** | Gaps nào phải sửa trước release, ai chấp nhận phần còn lại? | Findings, owners, conditions. |

### Sau workshop

Không chỉ lưu meeting minutes. Cập nhật **DFD, threat register, requirement/control/test mapping, findings, ADR links và review outcome**. Những item chưa được xác minh phải có owner và deadline; những phát hiện cần test phải vào backlog có acceptance criteria.

### Facilitation tránh groupthink

Cho reviewer không trực tiếp xây tính năng đặt câu hỏi “Nếu control này không tồn tại thì sao?”, “Có đường thứ hai không?”, “Ai quản lý service identity?” và “Bằng chứng nào có thể bác bỏ giả định?”. Cần tạo không gian để engineers báo thiếu sót mà không bị coi là thất bại cá nhân.

## 31. Một playbook review dựa trên đường truy cập

Để tránh thảo luận lan man, bắt đầu từ **một protected business action** có giá trị cao, ví dụ xuất toàn bộ hóa đơn.

### Bước 1: Xác định legitimate flow

User thuộc tenant A → login/federation → API tạo job → queue → worker → database → object storage → download. Với từng bước, ghi **principal, action, resource, data sensitivity và authorization point**.

### Bước 2: Thử thay một giả định

- Token được xác minh nhưng resource ID thuộc tenant B.
- Tenant ID ở job message bị attacker thay.
- Worker chạy với privileged database account.
- CDN có link không ràng buộc người dùng.
- User mất quyền sau khi job được tạo.
- Queue replay khi worker retry.
- Thời gian log source mất kết nối.

### Bước 3: Theo hệ quả lan truyền

Nếu user gửi object ID ngoài quyền, ai sẽ phát hiện trước? Nếu API không ngăn nhưng worker có scoping thì outcome thế nào? Nếu cả API và worker đúng nhưng CDN vẫn public thì có đường bypass nào khác?

### Bước 4: Định nghĩa expected outcome

Viết rõ các trường hợp **DENY**, **ALLOW có điều kiện**, **STEP-UP**, **FAIL SECURE**, **AUDIT**, **REVOKE** hoặc **RECONCILE**. Không tự dùng response code 403 như bằng chứng nếu dữ liệu đã trả qua đường khác.

### Bước 5: Gán verification

Kết nối mỗi bước với code/config review, effective policies, negative tests, telemetry, incident/restore drill. Đây là chuyển đổi từ **threat modeling workshop sang assurance engineering**.

## 32. Case study đầy đủ: review mô hình đe dọa tính năng Export trong Invoice SaaS

### 32.1. Bối cảnh nghiệp vụ

Invoice SaaS phục vụ nhiều doanh nghiệp trên cùng nền tảng. Mỗi tenant có dữ liệu hóa đơn và hồ sơ khách hàng. Người dùng được phân vai trò Viewer, Accountant và TenantAdmin; nhân viên support có giới hạn truy cập riêng. Tính năng mới cho phép export CSV/PDF theo bộ lọc và tải file sau khi background job hoàn tất.

Kiến trúc dùng:

- Public gateway và invoice API.
- Customer SSO/IdP.
- Shared relational database có tenant identifier.
- Job queue và export worker.
- Object storage và download endpoint.
- Centralized security logs và analytics.
- Cloud IAM/KMS cùng pipeline CI/CD.

**Security objectives:** ngăn cross-tenant disclosure; hạn quyền service; bảo vệ file và thông tin nhạy cảm trong queue, logs, analytics; có thể phát hiện abuse và thu hồi quyền; duy trì availability khi spike export.

### 32.2. Threat model ban đầu

Nhóm phát triển liệt kê:

1. SQL injection ở API.
2. Credential stuffing.
3. DoS tới gateway.
4. Man-in-the-middle trên Internet.

Các mitigations tương ứng là parameterized queries, MFA, rate limiting và TLS. Đây đều là những controls hữu ích nhưng **chưa chứng minh được feature export an toàn**.

### 32.3. Review phát hiện thiếu coverage

| ID | Thiếu sót | Vì sao có ý nghĩa |
| --- | --- | --- |
| **RV-01** | DFD không có worker, queue và object storage. | Thiếu nhiều trust boundaries và data copies. |
| **RV-02** | Không mô hình hóa authenticated malicious tenant user. | Bỏ qua BOLA và abuse bằng account hợp lệ. |
| **RV-03** | Tenant ID từ request được đưa thẳng vào job. | Attacker có thể kiểm soát authorization context. |
| **RV-04** | Worker dùng service identity đọc mọi tenants. | Blast radius lớn nếu job hoặc workload bị lạm dụng. |
| **RV-05** | Download URL được coi là “private” vì khó đoán. | Capability URL có thể bị chia sẻ; semantics revoke chưa rõ. |
| **RV-06** | Không ghi retention của queue, DLQ và export files. | Confidential data có thể tồn tại lâu ngoài dữ liệu chính. |
| **RV-07** | Không xét retry/replay hoặc idempotency. | Tạo nhiều exports, chi phí hoặc dữ liệu ngoài policy. |
| **RV-08** | Không nối actor→job→file trong audit. | Khó xác minh truy cập và điều tra abuse. |
| **RV-09** | Không có model cho failure của KMS/broker/IdP. | Khả năng có fallback không an toàn hoặc outage kéo dài. |
| **RV-10** | Không xét data recipient qua analytics/vendor email. | Data sharing/purpose/retention gaps. |

### 32.4. Hai attacker stories

**Story A – malicious tenant user:** User ở tenant A có quyền export một số invoices. Họ thử gửi ID của invoice B. API xác thực đúng user A, nhưng không kiểm tra object ownership; worker dùng role đọc mọi tenant; file được tạo và link tải được trả về. Đây là **cross-tenant confidentiality violation**, không được giải quyết bằng MFA.

**Story B – compromised export worker:** Attacker chiếm process worker qua dependency vulnerability. Workload identity có quyền DB read rộng, storage write rộng và KMS Decrypt. Attacker có thể truy xuất nhiều tenants mà không cần lấy user session. Đây là rủi ro **workload privilege/blast radius**, có mitigation khác Story A.

### 32.5. Threat-to-control mapping sau review

| Threat ID | Requirement | Controls cần có | Verification |
| --- | --- | --- | --- |
| TH-EXP-01: BOLA | Object/tenant authorization tại protected action. | Verified principal, server-side tenant lookup, scoped data access. | TM-T01, TM-T02. |
| TH-EXP-02: forged job | Không tin tenant/resource context do producer bất hợp lệ. | Server-owned job, broker ACL, worker validation. | TM-T03, TM-T04. |
| TH-EXP-03: overprivileged worker | Compromise không cho đọc ngoài nhiệm vụ. | Least privilege IAM, workload identity, DB scope. | Effective grants, denied-use tests. |
| TH-EXP-04: file disclosure | Download tuân thủ authorization/capability semantics đã duyệt. | Private storage, download PEP, lifecycle/expiry. | TM-T05, TM-T06, TM-T18. |
| TH-EXP-05: replay/DoS | Job idempotency và resource controls. | Durable job state, retry limits, quota, backpressure. | TM-T12, load/failure tests. |
| TH-EXP-06: missing audit | Export có thể truy vết actor/job/file và source health. | Correlation IDs, protected audit, health alert. | TM-T13 và correlation test. |
| TH-EXP-07: data lifecycle | Bản sao có purpose/retention/recipient phù hợp. | Queue/DLQ/file lifecycle, analytics allowlist. | TM-T16, deletion/retention verification. |
| TH-EXP-08: outage/fallback | Failure không mở quyền hoặc mất dữ liệu trái policy. | Fail-secure handling, recovery and reconciliation. | TM-T14, TM-T15. |

### 32.6. Quyết định review tại design stage

**Needs rework / Approved only with explicit conditions** tùy governance: bổ sung DFD và threat register, định nghĩa object/job/download authorization, thu hẹp workload identity, kiểm tra copy lifecycle, thêm test suite và audit design. Nếu các controls mới chỉ là đề xuất, không gán current residual risk thấp hơn như thể đã triển khai.

### 32.7. Kiểm chứng implementation và đóng finding

Sau khi code/IaC được thay, reviewer cần nhận:

- Exact release/commit/policy version đã deploy.
- Positive/negative tests với synthetic tenant A và B.
- Effective IAM/DB/storage access và revoked credential tests.
- Queue producer/consumer auth và idempotency outcome.
- Download link semantics và unauthorized/expired URL tests.
- Audit correlation end-to-end, collector health và data retention.
- Remediation owner sign-off và **independent retest** theo mức rủi ro.

**Không được báo PASS trước khi có observed results.** Trong học tập, mọi findings, owners và controls ở đây là kịch bản giả định.

## 33. Ví dụ Java/Spring: một threat model có thể dẫn đến code review gì?

Threat scenario là **BOLA**: user đã đăng nhập nhưng gửi invoice ID không thuộc tenant hiện hành. Reviewer cần nhìn **nguồn principal, điều kiện authorization, query scope và các internal call paths**.

### Minh họa authorization ở service/repository boundary

~~~java
@Service
public class InvoiceExportAuthorization {
    private final InvoiceRepository invoices;

    public InvoiceExportAuthorization(InvoiceRepository invoices) {
        this.invoices = invoices;
    }

    @Transactional(readOnly = true)
    public InvoiceExportScope verify(
            UUID invoiceId,
            VerifiedPrincipal principal) {

        if (principal == null
                || principal.tenantId() == null
                || !principal.canExportInvoices()) {
            throw new AccessDeniedException("Export not permitted");
        }

        Invoice invoice = invoices
            .findByIdAndTenantId(invoiceId, principal.tenantId())
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND));

        return new InvoiceExportScope(
            invoice.getId(),
            invoice.getTenantId(),
            principal.subjectId());
    }
}
~~~

### Những giả định phải review tiếp

1. **VerifiedPrincipal** được tạo từ verified identity context, không từ header/body do client đặt.
2. **canExportInvoices()** được tính từ policy phù hợp resource/action và được update sau role changes.
3. **Repository** triển khai tenant-scoped query đúng, không có bypass ở native SQL hoặc admin path.
4. **InvoiceExportScope** là dữ liệu đã kiểm chứng, nhưng khi tạo job cần giữ integrity/binding với actor và tenant; không được biến thành payload ai cũng sửa được.
5. **Worker** không tự suy “job hợp lệ = tôi có thể đọc mọi tenant”; phải có authorization/least privilege riêng.
6. **Download** cần controls riêng, nhất là signed URL hoặc CDN.
7. **Audit** ghi được actor→job→file→download mà không log nội dung hóa đơn.
8. **Test** phải kiểm tra wrong tenant, wrong principal, deleted invoice, revoked role, replay job, direct worker call.

Đoạn code chỉ minh họa cách một threat scenario dẫn tới **review checklist cụ thể**. Nó không chứng minh Spring Security filters đã bao phủ mọi route, không tự thiết lập object permissions cho worker, và không thay full integration tests.

### Test matrix nhỏ

| Principal | Resource | Action | Expected |
| --- | --- | --- | --- |
| Tenant A, permitted accountant | Invoice A, owned/scope đúng | EXPORT | ALLOW theo policy. |
| Tenant A, viewer không có export permission | Invoice A | EXPORT | DENY. |
| Tenant A, permitted accountant | Invoice B | EXPORT | DENY; không có data leakage. |
| Principal thiếu tenant binding | Invoice A | EXPORT | DENY. |
| Worker principal ngoài job/resource scope | Invoice B | READ/EXPORT | DENY. |

Một positive test thành công không thay negative tests. Nếu review chỉ thấy controller check authenticated, đây vẫn có thể là **finding về object-level authorization**.

## 34. Evidence-based review: Claim–Argument–Evidence (CAE)

### Claim minh họa

> Trong release R của tính năng Invoice Export trên production, các threat scenarios trọng yếu liên quan cross-tenant access, forged jobs, excessive workload privilege, file disclosure và loss of auditability đã được nhận diện, có security requirements phù hợp và controls đã được kiểm chứng trong phạm vi đã định nghĩa.

### Argument

1. Asset inventory và business impact xác định Confidential invoice data là tài sản quan trọng.
2. DFD/flow register mô tả request, queue, worker, database, storage và download cùng trust boundaries.
3. Threat scenarios có attacker goals/capabilities, preconditions, paths và impact.
4. Requirements/controls xử lý các đường tấn công và không phụ thuộc hoàn toàn vào một lớp.
5. Code/IaC/runtime policies khớp kiến trúc được review.
6. Negative/positive/failure-mode tests và audit chứng minh outcome theo design.
7. Unknowns, exceptions và residual risks được ghi đúng thẩm quyền.

### Evidence matrix

| Claim component | Evidence nên có | Điều không tự chứng minh |
| --- | --- | --- |
| Scope/flows hoàn chỉnh tương xứng mục tiêu. | Versioned DFD, API/service/storage inventory, owner walkthrough. | Không thể khẳng định toàn bộ unknown routes đã được phát hiện. |
| Threat scenarios được đánh giá. | Threat register, attack paths, STRIDE/abuse workshop outcomes. | Không chứng minh runtime controls hoạt động. |
| Controls có thiết kế hợp lý. | Requirement-control mapping, ADR, security design review. | Code/config đã được deploy đúng. |
| Tenant authorization thực thi. | Cross-tenant negative tests, verified query, effective grants. | Mọi business flows ngoài suite đều được bao phủ. |
| Export file được bảo vệ. | Storage effective policy, signed URL/PEP tests. | Không có link bị chia sẻ trước review. |
| Audit/response hoạt động. | End-to-end correlation traces, source-health tests, drill records. | Không có bất kỳ incident nào nếu logs không đầy đủ. |
| Risk được quản trị. | Finding register, risk acceptance, retest, status history. | Rủi ro đã được loại bỏ chỉ vì ticket đóng. |

### Bằng chứng có thể phản bác

Nếu DFD nói data path luôn đi qua download service nhưng effective storage policy cho anonymous read, một phần claim bị bác bỏ. Reviewer phải ghi finding, sửa scope/threat model và đánh giá lại — không chỉ thay wording thành “private by design”.

## 35. Mẫu threat scenario YAML để review và truy vết

Mẫu sau là **minh họa học tập**, không phải schema của hệ thống hoặc evidence đã thu thập.

~~~yaml
threat:
  id: TH-EXP-03
  title: "Cross-tenant export through background worker"
  model_version: "review-example-v1"
  status: under_review
  scope:
    system: invoice-saas
    feature: async-export
    environment: production
    assets:
      - confidential-invoice-data
    flows:
      - API-TO-JOB
      - QUEUE-TO-WORKER
      - WORKER-TO-DB
      - FILE-DOWNLOAD
    trust_boundaries:
      - client-to-api
      - api-to-worker
      - worker-to-data
      - download-to-storage
  attacker:
    type: legitimate-tenant-user
    initial_access: "tenant A viewer account"
    capabilities:
      - "Send crafted export requests"
      - "Specify resource IDs not owned by tenant A"
  objective: "Read invoice belonging to tenant B"
  prerequisites:
    - "Object-level authorization missing or bypassable"
    - "Worker trusts unverified job context"
  impact:
    property: confidentiality
    scope: cross-tenant
    rating: "TO_BE_ASSESSED_WITH_RUBRIC"
  requirements:
    - REQ-AUTHZ-07
    - REQ-JOB-INTEGRITY-03
  controls:
    proposed:
      - "Server-owned job record"
      - "Resource-level authorization"
      - "Tenant-scoped worker/database permissions"
      - "Authorized download"
    implemented: []
    verification_state: pending
  tests:
    - TM-T01
    - TM-T02
    - TM-T03
    - TM-T04
    - TM-T06
  evidence:
    state: NOT_COLLECTED
    release: "TO_BE_FILLED"
    policy_version: "TO_BE_FILLED"
    references: []
  assumptions:
    - "No alternate direct object storage read path"
  review:
    reviewer_role: security-design-reviewer
    result: PENDING_EVIDENCE
    finding_ids:
      - RV-03
      - RV-04
    owner_role: export-service-owner
    reassessment_triggers:
      - "new-export-consumer"
      - "authorization-model-change"
      - "confirmed-cross-tenant-incident"
~~~

### Reviewer nên nhận xét gì về mẫu?

Vì trường controls.implemented rỗng và evidence.state = NOT_COLLECTED, mô hình **không có quyền hạ current residual risk dựa trên proposed controls**. Đó là một record tốt về ý định xử lý và kế hoạch test, chưa phải một kết luận operating effectiveness.

### Đừng đưa bí mật vào threat register

Không lưu real API tokens, private keys, exploit payload có chứa customer data, production passwords hoặc toàn bộ flow nhạy cảm ở nơi công khai. Định danh và links tới evidence repositories nên được kiểm soát theo phân quyền và retention.

## 36. Mẫu báo cáo Security Design Review cho threat model

Một review report có thể dùng cấu trúc:

1. **Header:** review ID, system, feature, version, date, reviewers, authors.
2. **Context:** business purpose, assets, threat assumptions và exclusions.
3. **Architecture view refs:** context, DFD, deployment, identity/access, data lineage.
4. **Review methods:** walkthrough, STRIDE, attack trees, privacy review, code/IaC sampling.
5. **Coverage:** quan trọng gì đã review và nguồn population.
6. **Threat register summary:** material threats, status, risks, controls.
7. **Findings:** model defects, design weaknesses, implementation failures phân biệt.
8. **Verification plan:** tests/evidence trước release và trong operation.
9. **Limitations:** unresolved unknowns, absent teams, stale diagrams, missing evidence.
10. **Decision:** review outcome, release gate/conditions và risk acceptance.
11. **Sign-off/owners:** thẩm quyền đúng scope; revision history.
12. **Reassessment triggers:** new trust boundary, data flow, incident, vendor, workload.

### Sample conclusion có căn cứ

> “Threat model bản v1.4 đã được review cho thay đổi async export trong release R, gồm API, queue, worker, database và download path. Các threat scenarios TH-EXP-01 đến TH-EXP-08 được phân tích; còn findings RV-03 và RV-04 cần mitigation và negative retest trước khi cấp kết luận operating effectiveness. Vùng analytics và vendor email chưa được đánh giá đầy đủ, do đó không nằm trong assurance claim.”

Kết luận mẫu này có ích vì **scope, status và điều kiện** được diễn đạt cụ thể, không dùng “Secure/Approved” thiếu căn cứ.

## 37. Tính đầy đủ và chất lượng của bằng chứng review

Một threat model review có thể rất sâu về lập luận nhưng vẫn không đủ điều kiện đưa ra **assurance conclusion** nếu chỉ có hình vẽ cũ và một buổi họp.

### Bằng chứng theo từng loại claim

| Claim | Bằng chứng phù hợp | Giới hạn |
| --- | --- | --- |
| Architecture model phản ánh hệ thống đang vận hành. | Versioned diagrams, asset/route inventory, code/IaC/deployment comparison. | Diagram đúng tại một thời điểm chưa bảo đảm sau release. |
| Trust boundaries đã được phân tích. | Flow/identity mapping, policy owners, reviewer notes. | Boundary chưa được khám phá vẫn có thể tồn tại. |
| Attack paths quan trọng được xét. | Scenario register, assumptions, attacker capabilities, workshop records. | Không thể chứng minh mọi attacker strategy đã được nghĩ tới. |
| Mitigation có thiết kế hợp lý. | Requirement/control trace, ADR, architecture review. | Chưa chứng minh code/config được triển khai. |
| Mitigation được thực thi. | Effective runtime policy, integration tests, direct-path probes trong scope. | Test suite có thể thiếu một environment/tenant tier. |
| Detection/response hoạt động. | Alert simulation, health checks, incident drills, time-to-effect records. | Có thể có incident ngoài detector coverage. |
| Residual risk được quản trị. | Risk register, exceptions, decisions, expiry và retests. | Chữ ký không biến rủi ro thành zero. |

### Phẩm chất của evidence

- **Relevance:** có chứng minh đúng threat/requirement và phiên bản không?
- **Completeness:** có đủ flows, users, resources, environments và thời kỳ?
- **Accuracy:** expected/observed có nguồn đáng tin, không sai join?
- **Freshness:** evidence còn đúng sau thay identity/policy/service?
- **Integrity/provenance:** ai/công cụ nào tạo, có thể kiểm tra nguồn và thay đổi?
- **Independence:** người review/test có đủ độc lập tương xứng risk?
- **Repeatability:** có thể tái tạo phương pháp và điều kiện test?
- **Limitations:** unknown/exclusions có được công bố và xử lý?

### Bảo vệ evidence

Threat models có thể tiết lộ routes, trust relationships, key ownership, attacker paths và cấu trúc sản phẩm. Phân quyền repository, logging và retention cần phù hợp. Không dán real secrets, customer PII, access tokens hoặc exploitable live endpoints vào báo cáo nếu không có căn cứ/quyền và môi trường được bảo vệ.

### Scope & time-bound conclusion

Một kết luận cho release R1 và ngày đánh giá T không tự áp dụng cho R2 sau khi thay queue/auth policy. Khi dùng evidence từ staging, phải xác định các controls có tương đương production không và phần nào cần production readback/monitoring.

## 38. Vai trò, ownership và RACI

Review threat model đòi hỏi phối hợp vì không ai nắm trọn mọi layer: product biết impact, architect biết boundaries, developers biết code, platform biết IAM/runtime, data owner biết sensitivity, security reviewer biết attack patterns và assurance biết evidence.

| Vai trò | Trách nhiệm |
| --- | --- |
| **Threat model author / feature engineer** | Duy trì DFD, flows, threat scenarios, assumptions và changes. |
| **Solution/security architect** | Đánh giá boundaries, controls, design trade-offs và cross-service dependencies. |
| **Application/service owner** | Xác minh actual routes, authorization logic, jobs, tests và fix. |
| **Data owner/privacy owner** | Classification, data lineage, purposes, recipients và impact. |
| **Platform/cloud/IAM owner** | Effective IAM, network, secrets, KMS, CI/CD, runtime và evidence. |
| **Detection/response owner** | Logging, alerts, incident containment và recovery drills. |
| **Independent security assurance reviewer** | Thách thức assumptions, kiểm tra coverage/evidence, ghi findings và retest. |
| **Business/risk owner** | Quyết định residual risk và treatment trong thẩm quyền. |
| **Release/change owner** | Gắn review conditions với release gate, deployment và reassessment. |

### RACI minh họa

**R** = thực hiện; **A** = chịu trách nhiệm cuối cùng; **C** = tham vấn; **I** = được thông báo.

| Hoạt động | Feature/architect | Security reviewer | Platform/Data owners | Assurance | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Tạo/cập nhật DFD và flows | **A/R** | C | C | I | I |
| Phân tích threats và attacker paths | R | **A/R** | C | C | I |
| Xác định controls và implementation | **A/R** | C | R | C | I |
| Đánh giá quality/evidence | C | R | C | **A/R** | I |
| Chấp nhận residual risk | C | C | C | C | **A/R** |
| Remediation/retest | **A/R** | C | R | R | I |
| Release gate theo policy | R | C | C | C | **A** hoặc release authority phù hợp |

Không phải tổ chức nào cũng có đủ từng vai trò độc lập; có thể gộp theo nguồn lực. Nhưng **người viết threat model không nên tự coi self-review là bằng chứng đánh giá độc lập** khi rủi ro đòi hỏi assurance bên thứ hai.

## 39. Chỉ số chất lượng review threat model

Các chỉ số giúp phát hiện vùng chưa được xử lý, không phải một công thức tạo “security score” duy nhất.

| Metric | Định nghĩa gợi ý | Cảnh báo khi diễn giải |
| --- | --- | --- |
| **TM-M01 Asset coverage** | High-impact assets có threat consideration / population đã đối chiếu. | Inventory thiếu sẽ cho tỷ lệ đẹp giả. |
| **TM-M02 Flow/boundary coverage** | Critical flows/boundaries đã review / tổng critical flows/boundaries trong scope. | Không nói controls vận hành tốt. |
| **TM-M03 Threat quality** | Material threats có actor, goal, entry, impact, control owner và test / threats được đánh giá. | Tăng trường metadata không tự tạo insight. |
| **TM-M04 Requirement traceability** | Material threats có requirement/control/test links / material threats. | Mapped test có thể chưa chạy. |
| **TM-M05 Verified mitigation coverage** | Material threats có controls với evidence còn mới / material threats cần mitigations. | Một control có thể chỉ giảm một phần risk. |
| **TM-M06 Open critical gaps** | Số critical findings và tuổi theo risk policy. | Số ít có thể do review chưa đủ sâu. |
| **TM-M07 Model freshness** | Systems/changes có review sau trigger trong SLA được duyệt. | Ngày sửa file không chứng minh chất lượng. |
| **TM-M08 Assumption verification** | Material assumptions đã xác minh / assumptions trong phạm vi. | Unknown phải ghi riêng, không là N/A. |
| **TM-M09 Retest closure** | Findings đã remediation và retest đạt / findings đến hạn. | Closed ticket không đồng nghĩa test PASS. |
| **TM-M10 Release gate compliance** | Risk-significant changes có review condition/decision / changes cần review. | Phụ thuộc phân loại changes đáng review. |
| **TM-M11 Evidence source health** | Critical telemetry sources đủ nguồn/tuổi/quality / critical sources. | Heartbeat không chứng minh tất cả events đã đến. |
| **TM-M12 Detection-to-model feedback** | Relevant incidents/findings có cập nhật model hoặc explicit no-change rationale. | Không nên tự sinh threats để đạt KPI. |

### Ví dụ tính coverage có giới hạn

Hệ thống có 60 critical data flows trong inventory được xác minh. Review hoàn tất 54 flows:

\[
\text{Flow review coverage}=\frac{54}{60}\times100\%=90\%.
\]

Kết quả chỉ nói **90% flows trong population đã được review theo tiêu chí đề ra**. Nếu 6 flows chưa review gồm một luồng public export có data Confidential, quyết định release phải xem trọng yếu của gap đó; không được dùng 90% để che blocker.

### Target do ai quyết định?

Ngưỡng, SLA, risk tiers và critical gates phải do chương trình/governance xác định dựa trên business impact và nghĩa vụ. Nếu mẫu số không đủ, kết quả phải là **UNKNOWN/PARTIAL** kèm nguồn và exclusions, không tự đặt 100%.

## 40. Continuous review: giữ threat model gắn với hệ thống thực

Một threat model có thể nhanh chóng lỗi thời khi team đổi code, cloud, identities, integrations hoặc nghiệp vụ. Cần thiết kế **trigger-driven maintenance**.

~~~mermaid
flowchart TD
    A["Approved architecture baseline + threat model"] --> B["Code / IaC / data flow / identity changes"]
    B --> C["Detect material changes and review trigger"]
    C --> D["Revalidate inventory and trust boundaries"]
    D --> E["Update attack paths, threats and risk"]
    E --> F["Adjust requirements, controls and test plans"]
    F --> G["Implement changes and collect evidence"]
    G --> H{"Expected result demonstrated?"}
    H -- "No or unknown" --> I["Finding / rework / risk escalation"]
    I --> F
    H -- "Yes" --> J["Time-scoped review outcome"]
    J --> K["Monitor incidents, drift and assumptions"]
    K --> C
~~~

### Trigger quan trọng

- New public API, GraphQL field, gRPC method, websocket hoặc admin route.
- New topic/queue/worker, retry flow, scheduled job hoặc file export.
- New data recipient, vendor, region, analytics/AI pipeline hoặc backup copy.
- IdP federation, token, authorization policy, workload principal hoặc key changes.
- Cloud account/trust, network zone, Kubernetes service account hoặc deployment pipeline.
- Vulnerability/incident/pentest finding khiến assumption sai.
- Customer/tenant tier, data classification, privacy purpose hoặc RTO/RPO thay đổi.
- Control drift, logging coverage loss hoặc failed negative tests.

### Automation giúp gì?

Có thể đối chiếu changed IaC resources, new routes, IAM grants, data schemas, dependencies và ownership registry để gợi ý review. Policy-as-code và tests có thể trở thành **architecture fitness functions** cho các giả định có thể đo:

- Critical API route có policy owner và test ID.
- Public storage ngoài baseline bị chặn.
- New service principal không có wildcard admin khi policy cấm.
- Event schema không xuất fields nhạy cảm ngoài allowlist.
- CI deploy đòi provenance/signature theo baseline.
- Thay trust relationship tạo review request.

Automation không tự biết một business rule bị hiểu sai hoặc một attack path kết hợp nhiều services; human threat review và thực nghiệm vẫn quan trọng.

## 41. Anti-patterns thường gặp khi review threat model

| Anti-pattern | Dấu hiệu | Cách cải thiện |
| --- | --- | --- |
| **Checkbox STRIDE** | Điền đủ sáu chữ nhưng không có kịch bản cụ thể. | Viết actor/goal/precondition/flow/impact/control. |
| **Diagram-only review** | Chỉ xem hình mà không đối chiếu code/IaC/runtime. | Compare design với effective config và deployment. |
| **MFA solves everything** | Dùng login strength để đóng lỗi object authz. | Tách AuthN và business authorization. |
| **Internal trusted by default** | Bỏ internal API, worker, queue và service identity. | Xem compromised workload và trust boundary. |
| **No negative tests** | Chỉ happy-path login/export success. | BOLA, replay, wrong principal, expired link, failure tests. |
| **Rely on proposed controls** | Ghi “mitigated” dù chưa triển khai. | Tách Proposed/Implemented/Verified và current/target risk. |
| **Single threat score** | Trộn mọi risks thành điểm trung bình để approve. | Critical gates, rationale và unresolved unknowns. |
| **Ignore copies/downstream** | Quên cache, DLQ, analytics, logs, backup, vendor. | Data lineage và recipient inventory. |
| **No attacker model** | Giả attacker vô năng hoặc toàn năng. | Capabilities/prerequisites cụ thể theo scenario. |
| **One reviewer knows all** | Security reviewer tự xác nhận dữ liệu/ops không hỏi owner. | Cross-functional review và assumption register. |
| **Static annual document** | Release thay lớn nhưng model không đổi. | Trigger-driven reassessment, evidence freshness. |
| **Risk acceptance as control** | Có chữ ký thì chuyển FAIL thành PASS. | Acceptance riêng với hiệu quả control, có scope/expiry. |
| **No evidence provenance** | Screenshot không biết region/version/time. | Evidence register và test metadata. |
| **Quietly discard unknowns** | Không đủ dữ liệu nhưng báo N/A. | UNKNOWN có owner/deadline và risk treatment. |
| **Closed ticket = fixed risk** | Không có retest sau sửa. | Verified implementation và regression checks. |
| **No operational threats** | Chỉ threat disclosure, bỏ incident/recovery/DoS. | Xem availability, detection, recovery và key dependencies. |

### Red flags cần ưu tiên ngay

Trong buổi review, nếu một trong những câu sau xuất hiện thì nên kiểm tra sâu:

- “Service này ở private network nên không cần auth.”
- “Queue message do hệ thống gửi nên tenantId chắc chắn đúng.”
- “Chỉ có user hợp lệ mới biết ID nên không cần kiểm tra object.”
- “Chúng ta đã bật encryption nên không có data disclosure.”
- “Cloud provider chịu toàn bộ trách nhiệm.”
- “Test không phát hiện gì nghĩa là không có threat.”
- “Policy đã được duyệt nên mọi release sau cũng an toàn.”

Các câu trên không tự chứng minh lỗ hổng; chúng là **assumptions cần evidence và threat-driven tests**.

## 42. Checklist chất lượng review threat model

Một reviewer có thể sử dụng checklist 24 câu hỏi dưới đây như **prompt**, không phải chứng chỉ đạt.

1. **Scope:** system/release/environment/feature và exclusions có rõ?
2. **Business impact:** assets, users và hậu quả kinh doanh được xác định?
3. **Inventory:** API, services, workloads, data stores, vendors, backups đầy đủ tương xứng scope?
4. **DFD:** flows có direction, source, recipient, data class và purpose?
5. **Trust boundaries:** nơi đổi identity/tenant/authority/ownership được chỉ rõ?
6. **Admin/control plane:** có privileged access, support tools, CI/CD và emergency paths?
7. **Non-human identities:** worker/runner/service principals có owner, scope và credentials?
8. **Attacker model:** goals, capabilities, entry points và prerequisites hợp lý?
9. **STRIDE/abuse/privacy:** taxonomy dùng để tìm scenarios chứ không làm checklist hình thức?
10. **Attack paths:** có xem multi-step, confused deputy, replay và bypass?
11. **Cross-tenant:** object, job, cache, export, storage và analytics isolation được xét?
12. **Data lifecycle:** copies, logs, DLQ, vendor, backup, retention và deletion?
13. **Supply chain:** dependencies, pipeline, artifacts, signing và deployment authority?
14. **Cryptography:** keys, key grants, rotation, loss và recovery?
15. **Availability:** DoS, overload, backpressure, fallback và DR?
16. **Detect/respond:** audit source health, containment và incident evidence?
17. **Risk quality:** impact, likelihood, blast radius, existing controls và uncertainty rõ?
18. **Requirement mapping:** threats có security requirements testable?
19. **Control placement:** controls nằm đúng boundary, có alternate paths và common-mode failure?
20. **Verification:** positive/negative/failure tests có expected/observed và evidence plan?
21. **Assumptions:** có owner, cách xác minh, unknown và contradicted evidence?
22. **Findings:** phân biệt model defect, design weakness và runtime failure?
23. **Governance:** review decision, release conditions, risk owner và exceptions/expiry?
24. **Freshness:** change/incident/dependency triggers tạo reassessment?

### Kết quả checklist

Không chỉ đánh dấu Yes/No. Mỗi mục quan trọng cần **evidence link, scope, version, status (PASS/PARTIAL/FAIL/UNKNOWN/N/A có lý do), owner và next action**. Một checklist hoàn chỉnh trên giấy không chứng minh coverage nếu asset/flow inventory sai.

## 43. Bài tập tình huống và gợi ý giải

### Bài tập A — STRIDE đủ sáu chữ nhưng vẫn thiếu đường dữ liệu

Threat model của tính năng export có bảng STRIDE đầy đủ, nhưng DFD không vẽ queue và object storage.

**Gợi ý:** Đây là model completeness defect. Cập nhật flows, producer/consumer, worker identity, storage/download paths, replay và authorization; tạo requirements/tests trước khi coi review đủ.

### Bài tập B — API có MFA nhưng cross-tenant BOLA

Một user của tenant A có MFA thành công và gọi invoice ID thuộc B; endpoint trả dữ liệu.

**Gợi ý:** AuthN PASS không bù AuthZ FAIL. Tạo threat scenario authenticated attacker, đánh giá blast radius, service/repository scope, worker/export/download và retest synthetic tenants.

### Bài tập C — “Internal” worker có quyền database admin

Worker nằm trong private subnet nhưng có quyền read/write mọi schema; threat model đánh giá “low risk” vì không public.

**Gợi ý:** Giả định network trust yếu. Xem compromised workload, effective IAM, tenant data scope, key usage, lateral movement và segmentation. Risk score phải xét blast radius.

### Bài tập D — Signed URL được coi là private

File export có URL ngẫu nhiên hết hạn sau 24 giờ, nhưng có thể chia sẻ cho người khác và không kiểm tra session tại tải.

**Gợi ý:** Capability URL sở hữu là điều kiện truy cập theo design; cần xét threat link disclosure, recipient binding hoặc lifetime, revoke semantics, logging và controls tương ứng, không mặc định “khó đoán” bằng authenticated access.

### Bài tập E — Bản sao analytics bị bỏ quên

Main DB có row-level isolation. Analytics warehouse lưu bản ghi nhiều tenants, analysts có quyền đọc dataset tập trung.

**Gợi ý:** Data lineage mở thêm trust boundary, có threat insider/cross-tenant disclosure, purpose/retention, field allowlist, workload IAM và query authorization; không suy DB chính an toàn thì mọi bản sao an toàn.

### Bài tập F — “Mitigated” dù remediation chưa deploy

Threat register ghi BOLA đã mitigated bởi service authorization, nhưng PR mới đang review và production vẫn chạy code cũ.

**Gợi ý:** Phân biệt proposed control, design reviewed, implemented và operating verified; current residual risk phản ánh trạng thái đang chạy. Gắn finding/release gate và test sau deployment.

### Bài tập G — Phát hiện log source im lặng

Nhóm bảo mật nói không có privileged abuse vì tuần này SIEM báo zero events, nhưng cloud control plane log collector đã dừng.

**Gợi ý:** Evidence gap, không phải PASS. Kiểm tra source inventory, lag/health, restore/reconcile và xem lại assumptions về detectability; xác định rủi ro trong kỳ mất log.

### Bài tập H — Backup mã hóa không khôi phục được

KMS key phiên bản cũ bị hủy sau rotation; backup vẫn mã hóa bằng key đó.

**Gợi ý:** Threat model thiếu availability/recovery dependency. Ghi key lifecycle, retention, restore flow, risk/owner và thử restore trong DR environment theo mục tiêu RTO/RPO.

### Bài tập I — CI runner có thể ký artifact production

Threat model chỉ xem public API, không có software supply chain. CI runner có quyền đọc signing key và deploy production.

**Gợi ý:** Mở DFD/context tới source→build→registry→deploy. Xem compromised dependency/runner, key custody, least privilege, signature/provenance, independent deployment gate và incident response.

### Bài tập J — “Threats reviewed 100%”

Đội báo 100% vì mọi dòng STRIDE đều có status, nhưng một API mới và một webhook mới chưa được đưa vào asset/flow inventory.

**Gợi ý:** Tỷ lệ này chỉ về các dòng hiện có, không phản ánh population. Đối chiếu route/flow discovery, cập nhật denominator, ghi unknown paths và trigger reassessment.

### Bài tập K — Risk score bị hạ nhờ control chưa kiểm chứng

Một attack path có khả năng gây lộ nhiều tenants. Nhóm giảm risk từ High xuống Low vì “sẽ thêm IAM rule” nhưng không có test.

**Gợi ý:** Current residual risk không giảm bởi kế hoạch. Target residual risk có thể ghi dự kiến; chỉ cập nhật sau effective policy/test evidence và đúng risk assessment.

### Bài tập L — Thay đổi message schema gây leak

Event mới chứa email và địa chỉ khách hàng để hỗ trợ dashboard; threat model trước chỉ có invoice ID.

**Gợi ý:** Thay data classification, recipients và purpose, review lại vendor/analytics, DLQ, logs, data minimization và retention; tạo schema allowlist/contract tests, update model/ADR.

## 44. Mẫu quyết định review và tiêu chí đóng

Một review có thể đưa ra quyết định với cấu trúc:

| Trường | Ví dụ giá trị cần ghi |
| --- | --- |
| **Decision scope** | Invoice Export, release R, production topology, tenant tiers và components. |
| **Material threats** | TH-EXP-01 đến TH-EXP-08 với priorities và trạng thái. |
| **Model completeness** | DFD/flows/assets được đối chiếu; known unknowns cụ thể. |
| **Design quality** | Controls, assumptions, requirement mapping và bypass paths. |
| **Implementation evidence** | Code/IaC/config/test results theo release. |
| **Unresolved findings** | IDs, risk, blockers/conditions, owner và deadline. |
| **Risk authority** | Người có quyền chấp nhận residual risk trong scope. |
| **Review outcome** | Reviewed / conditions / needs rework / pending evidence / failed. |
| **Retest acceptance** | Những tests/evidence bắt buộc trước khi đóng finding. |
| **Reassessment trigger** | New job, tenant, data recipient, IdP, IAM, cloud change, incident. |

### Tiêu chí đóng một finding

1. Mô hình và requirement được cập nhật theo kiến trúc đã chọn.
2. Thay đổi thực tế đã được triển khai đúng release/environment.
3. Có **observed** negative/positive/failure results trên threat scenarios thuộc scope.
4. Evidence đúng source/version/time, nguồn giám sát hoạt động.
5. Regression/bypass paths được kiểm tra; limitations công bố.
6. Residual risk hoặc exceptions (nếu còn) được xử lý đúng thẩm quyền.

Nếu một phần không chứng minh được, ghi **PARTIAL/UNKNOWN hoặc conditional close** theo policy và giải thích; đừng viết “threat eliminated” chỉ vì có tài liệu mới.

## 45. Kết luận

**Review threat model** trong **Security Design Review** là hoạt động kiểm tra độc lập hoặc có sự thách thức chuyên môn đối với **phạm vi, kiến trúc, assets, attacker capabilities, trust boundaries, threat scenarios, risk assumptions và controls**. Một mô hình chỉ hữu ích cho **SECURITY_SECURITY_ASSURANCE** khi threat scenarios được nối với **security requirements có thể kiểm chứng, implementation, positive/negative/failure tests, bằng chứng và kết luận có giới hạn**.

Review không được dừng ở việc đếm số dòng STRIDE, chấm điểm trung bình hay ký duyệt sơ đồ. Cần đặc biệt kiểm tra những đường thường bị bỏ quên như **background workers, queue/DLQ, signed export links, analytics, backups, privileged access, supply chain và cloud control plane**, đồng thời phân biệt **thiếu mô hình, yếu thiết kế và lỗi control đã xác minh**.

Kết luận có giá trị phải ghi rõ **system/release, environment, assets/flows được xét, thời kỳ, phương pháp, evidence, known unknowns, open findings, residual risk và conditions**. Khi ứng dụng, dữ liệu, identities, threats hoặc chính controls thay đổi, threat model và luận cứ assurance cũng cần được đánh giá lại. **Mục tiêu không phải chứng minh “không thể bị tấn công”, mà là có cơ sở đáng tin để hiểu và xử lý những rủi ro quan trọng nhất trước, trong và sau quá trình vận hành.**
