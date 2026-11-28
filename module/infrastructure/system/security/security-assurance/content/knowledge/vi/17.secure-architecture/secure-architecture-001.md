# Security Architecture Review (Đánh giá kiến trúc an toàn)

## 1. Vì sao phải review kiến trúc bảo mật?

Một nền tảng SaaS quản lý hóa đơn phục vụ hàng trăm doanh nghiệp có thể đã triển khai SSO, mã hóa database, API gateway, WAF và hệ thống giám sát. Tuy nhiên, một luồng export mới được thêm: API tạo job, message broker chuyển yêu cầu cho worker, worker dùng service account đọc dữ liệu và ghi file vào object storage. Thiết kế ban đầu không xác định ai có quyền tải file, tenant context được bảo vệ thế nào và ai kiểm soát link chia sẻ.

Mỗi thành phần riêng lẻ có thể được cấu hình đúng theo tài liệu của nó, nhưng **cách các thành phần kết hợp với nhau vẫn có thể tạo ra một đường truy cập trái phép**. Đây là vấn đề mà **Security Architecture Review (SAR) – đánh giá kiến trúc an toàn** cần phát hiện trước khi hệ thống hoặc thay đổi được đưa vào vận hành.

Security architecture review là hoạt động đánh giá có cấu trúc đối với **kiến trúc hệ thống, luồng dữ liệu, ranh giới tin cậy, giả định, yêu cầu bảo mật và thiết kế controls** để xác định liệu thiết kế có xử lý được các rủi ro đã biết, hỗ trợ mục tiêu bảo mật và có thể được kiểm chứng hay không.

Trong module **SECURITY_SECURITY_ASSURANCE**, review kiến trúc là một mắt xích của chương trình assurance liên tục. Nó nối:

**Business context → assets/data flows → threats and risks → security requirements → architecture controls → verification evidence → findings → remediation → residual risk.**

Mục tiêu không phải tạo một bản vẽ đẹp hay một danh sách công nghệ nổi tiếng. Mục tiêu là đưa ra **kết luận có căn cứ, có phạm vi và có thể kiểm tra lại** về việc thiết kế có đáp ứng yêu cầu bảo mật hay không.

> Một kiến trúc có thể có nhiều security products mà vẫn không an toàn nếu trust boundaries, quyền hiệu lực, luồng dữ liệu và trách nhiệm giữa các thành phần không được thiết kế rõ.

## 2. Security architecture review trả lời những câu hỏi nào?

Một review tốt phải làm rõ:

1. **Hệ thống bảo vệ tài sản nào?** Dữ liệu, danh tính, giao dịch, dịch vụ, khóa, cấu hình và khả năng vận hành.
2. **Ai hoặc điều gì có thể tương tác với hệ thống?** Người dùng, admin, workload, vendor, API client, batch và đối tác.
3. **Dữ liệu đi qua đâu?** Thành phần, network zones, queue, storage, logs, backup và các bên nhận.
4. **Trust boundaries nằm ở đâu?** Nơi danh tính, quyền, trách nhiệm, tenant hoặc mức kiểm soát thay đổi.
5. **Threat scenarios nào có thể xảy ra?** Spoofing, tampering, disclosure, privilege escalation, misuse, failure hoặc abuse.
6. **Yêu cầu bảo mật nào phải được đáp ứng?** Authentication, authorization, isolation, encryption, audit, resilience, privacy và recovery.
7. **Controls được đặt đúng nơi chưa?** Có bao phủ happy path, negative path, admin path, async path và failure mode?
8. **Có thể chứng minh thiết kế và triển khai đúng không?** Có testable requirements, owner, evidence và change traceability?
9. **Rủi ro còn lại là gì?** Phần chưa xử lý, ngoại lệ, phụ thuộc vendor và giả định chưa được xác minh.

### Kết quả review không chỉ là “Approved”

Một quyết định review nên có:

- Scope, phiên bản kiến trúc và môi trường được đánh giá.
- Danh sách assets, actors, flows và trust boundaries.
- Threat/risk register và security requirements.
- Findings có mức độ, bằng chứng, owner và deadline.
- Quyết định về controls, ngoại lệ và residual risk.
- Điều kiện cần hoàn thành trước release hoặc trước khi mở rộng scope.
- Verification plan và trigger review khi kiến trúc thay đổi.

Một trạng thái **Approved with conditions** phải nêu rõ điều kiện, thời hạn, người chịu trách nhiệm và cách kiểm chứng. Nếu chưa có bằng chứng về một giả định quan trọng, cần ghi **Open / Not verified**, không coi đó là PASS.

## 3. Phân biệt security architecture, design review, threat modeling và penetration testing

| Hoạt động | Trọng tâm | Thời điểm thường dùng | Kết quả chính |
| --- | --- | --- | --- |
| **Security architecture review** | Cấu trúc, boundaries, controls, assumptions và khả năng đáp ứng yêu cầu. | Thiết kế mới, thay đổi lớn, trước release và theo trigger. | Review record, findings, architecture decisions, verification plan. |
| **Threat modeling** | Cách attacker hoặc lỗi có thể tác động vào assets/flows. | Trong thiết kế và khi có thay đổi rủi ro. | Threat scenarios, attack paths, mitigations, residual risks. |
| **Secure design/code review** | Logic triển khai, code, configuration và cách controls được hiện thực. | Trong phát triển và pull request. | Review comments, code/config findings, tests. |
| **Penetration testing** | Khai thác có kiểm soát các điểm yếu trong hệ thống đang chạy. | Theo risk, trước release hoặc định kỳ. | Exploitation findings, proof of impact, retest. |
| **Security control assessment** | Control được thiết kế và vận hành có đáp ứng tiêu chí không? | Trong chương trình assurance/audit. | Design/operating effectiveness, evidence và conclusion. |
| **Compliance assessment** | Các yêu cầu của framework/luật/hợp đồng có được đáp ứng? | Theo phạm vi và kỳ đánh giá. | Mapping, evidence, gaps, compliance conclusion. |

Các hoạt động này bổ trợ nhau nhưng **không thay thế nhau**. Penetration test không thể chứng minh mọi giả định kiến trúc đã được xem xét; sơ đồ kiến trúc không chứng minh endpoint thực tế không có lỗ hổng; compliance checklist không tự chứng minh control hiệu quả.

## 4. Phạm vi và thời điểm cần thực hiện review

Review nên được kích hoạt theo **mức rủi ro và thay đổi kiến trúc**, không chỉ theo lịch cố định.

### Các tình huống nên review

- Hệ thống hoặc dịch vụ mới, đặc biệt xử lý dữ liệu nhạy cảm hoặc phục vụ nhiều tenant.
- Thay đổi trust boundary, network topology, identity provider hoặc authentication flow.
- Thêm API public, webhook, partner integration, event consumer hoặc data export.
- Thay đổi authorization model, role mapping, service identity hoặc quyền admin.
- Chuyển cloud account/region, thêm Kubernetes cluster, database, object storage hoặc analytics platform.
- Thêm AI/ML, data lake, third-party processor hoặc đường xử lý dữ liệu mới.
- Thay cryptographic design, KMS policy, secrets management hoặc certificate trust.
- Tăng mức độ quan trọng của dịch vụ, thay RTO/RPO hoặc kiến trúc DR.
- Có incident, penetration-test finding, control failure hoặc thay đổi nghĩa vụ.
- Deprecate thành phần, hợp nhất hệ thống hoặc thay nhà cung cấp.

### Phân loại mức review

| Loại review | Phạm vi phù hợp | Ví dụ |
| --- | --- | --- |
| **Initial architecture review** | Kiến trúc tổng thể và các trust boundaries chính. | Một SaaS mới trước khi triển khai production. |
| **Focused review** | Một thay đổi hoặc luồng rủi ro cao. | Thêm export worker và object storage. |
| **Design delta review** | Chỉ phần thay đổi cùng tác động lan truyền. | Thêm IdP hoặc thay key management. |
| **Reassessment** | Kiến trúc đã vận hành nhưng threat, dependency hoặc control thay đổi. | Incident, cloud migration hoặc vendor mới. |
| **Architecture assurance review** | Đối chiếu thiết kế với implementation và evidence. | Kiểm tra release đã triển khai có đúng ADR/control không. |

Focused review không có nghĩa bỏ qua dependency. Nếu thay một message consumer làm thay đổi quyền database hoặc đường dữ liệu, phải theo tác động tới các thành phần liên quan.

## 5. Tài liệu đầu vào và thông tin cần có

Không cần đợi một bộ tài liệu hoàn hảo mới bắt đầu. Nhưng reviewer cần biết **đâu là sự thật đã xác minh, đâu là giả định và đâu là phần chưa có**.

| Đầu vào | Nội dung cần xem | Mục đích |
| --- | --- | --- |
| **Business context** | Mục tiêu, người dùng, quy trình, impact khi sai hoặc gián đoạn. | Hiểu rủi ro nghiệp vụ. |
| **System context diagram** | External entities, services, dependencies và boundaries. | Xác định scope. |
| **Data flow/DFD** | Data sources, processing, stores, recipients, copies và protocols. | Xác định nơi dữ liệu di chuyển. |
| **Deployment/network view** | Cloud accounts, VPC/VNet, subnets, ingress/egress, regions, clusters. | Xem vị trí và ranh giới kỹ thuật. |
| **Identity/access model** | IdP, users, roles, service accounts, workload identity, PAM. | Xác định đường quyền. |
| **Data classification** | Loại dữ liệu, độ nhạy, retention, owner. | Chọn mức controls phù hợp. |
| **Threat model/risk register** | Kịch bản, likelihood, impact, existing controls. | Ưu tiên review. |
| **Security requirements** | Các điều kiện có thể kiểm tra, nguồn và owner. | Làm tiêu chí đánh giá. |
| **Architecture Decision Records (ADR)** | Lựa chọn, phương án khác, lý do và hệ quả. | Hiểu các trade-offs. |
| **Control/config evidence** | IaC, policy, API contracts, tests, monitoring. | Đối chiếu thiết kế với hiện thực. |
| **Third-party/service inventory** | Vendor, SDK, SaaS, subprocessor và shared responsibility. | Xem ranh giới bên ngoài. |
| **Operational/recovery design** | Logging, incident, backup, DR, runbooks. | Đánh giá vận hành và resilience. |

### Khi tài liệu không đầy đủ

Ghi rõ **Assumption**, **Unknown** hoặc **Evidence gap**, gắn owner và cách xác minh. Không tự suy diễn rằng “cloud provider quản lý” đồng nghĩa một control đã được triển khai; cũng không coi một thành phần không xuất hiện trên sơ đồ là không tồn tại.

## 6. Các góc nhìn kiến trúc cần review

Một hệ thống lớn không thể đánh giá đầy đủ từ một sơ đồ duy nhất. Nên dùng các views liên kết với nhau:

| Architecture view | Nội dung | Câu hỏi bảo mật |
| --- | --- | --- |
| **Context view** | Actor, hệ thống ngoài, mục tiêu và trust. | Ai tương tác và dữ liệu ra/vào đâu? |
| **Logical/component view** | Services, modules, responsibilities và APIs. | Thành phần nào thực thi control và có phụ thuộc vòng? |
| **Data flow view** | Dữ liệu, biến đổi, stores, queues và recipients. | Dữ liệu nhạy cảm đi đâu và được giảm thiểu thế nào? |
| **Deployment view** | Cloud resources, clusters, accounts, regions và runtime. | Ranh giới network/administration nằm đâu? |
| **Identity/access view** | Users, roles, groups, workload identities và trust. | Ai có quyền hiệu lực và qua đường nào? |
| **Security control view** | Prevent/detect/respond/recover controls. | Control đặt đúng điểm và có kiểm tra được không? |
| **Operations view** | Logs, alerts, incident, patching, backup, DR. | Hệ thống phát hiện và phục hồi thế nào? |
| **Supply-chain view** | Source code, CI/CD, dependencies, artifacts, signing. | Ai có thể thay đổi phần mềm và đưa nó vào production? |

Các view phải có **ID hoặc tham chiếu chung** để trace một component/flow tới threat, requirement, control và test. Nếu cùng một API được gọi bằng ba tên ở ba tài liệu, reviewer khó xác định bằng chứng có đang nói về cùng endpoint không.

## 7. Trust boundaries và kiến trúc phân vùng

**Trust boundary** là ranh giới nơi giả định về danh tính, quyền, mức tin cậy, trách nhiệm hoặc khả năng kiểm soát thay đổi. Nó có thể nằm giữa hai network zones, hai tenant, hai cloud accounts, một tổ chức với vendor, hoặc giữa process có quyền khác nhau.

Ví dụ:

- Browser/client → public API.
- Public ingress → application subnet.
- Application service → database.
- Tenant A → shared multi-tenant service → tenant B.
- CI/CD runner → artifact registry → production cluster.
- SaaS platform → third-party processor.
- Production → analytics, staging, support hoặc backup environment.

### Sơ đồ ranh giới cho SaaS

~~~mermaid
flowchart TB
    subgraph External["External trust zone"]
      U["Customer user"]
      IDP["Customer IdP"]
      V["Third-party vendor"]
    end
    subgraph Edge["Public edge boundary"]
      CDN["CDN / WAF / Gateway"]
    end
    subgraph App["Application trust zone"]
      API["API services"]
      AUTH["Authorization service"]
      WORK["Background workers"]
    end
    subgraph Data["Restricted data zone"]
      DB[("Tenant data DB")]
      OBJ[("Object storage")]
      KMS["KMS / secrets"]
    end
    U --> CDN
    IDP <--> API
    CDN --> API
    API --> AUTH
    API --> DB
    API --> WORK
    WORK --> OBJ
    API --> KMS
    WORK --> KMS
    API --> V
~~~

### Cách review một boundary

1. Xác định **nguồn và đích**, danh tính hai bên, giao thức và dữ liệu đi qua.
2. Xác định ai quản lý mỗi đầu, ai thay đổi policy và ai chịu trách nhiệm.
3. Liệt kê attacker capabilities và các giả định tin cậy.
4. Kiểm tra authentication, authorization, integrity, encryption, rate limiting và logging theo rủi ro.
5. Kiểm tra đường lỗi, retry, failover và các bypass.
6. Viết test cases và evidence cần có.

**Private network không tự đồng nghĩa trusted.** Workload trong cùng VPC có thể bị xâm nhập, service identity có thể bị đánh cắp và cấu hình peering có thể mở rộng phạm vi. Trust cần dựa trên danh tính, quyền, policy và quan sát được.

## 8. Threat modeling gắn với kiến trúc

Threat modeling giúp đặt câu hỏi có hệ thống về việc attacker có thể **tác động tới tài sản qua flow hoặc boundary nào**.

### Quy trình STRIDE minh họa

| Nhóm | Ý nghĩa | Ví dụ SaaS |
| --- | --- | --- |
| **Spoofing** | Giả mạo danh tính hoặc nguồn. | Token từ IdP không được duyệt được chấp nhận. |
| **Tampering** | Thay đổi dữ liệu/thông điệp/cấu hình. | Tenant ID trong queue message bị sửa. |
| **Repudiation** | Không thể truy nguyên hành động. | Không liên kết được export job với actor. |
| **Information Disclosure** | Tiết lộ dữ liệu trái phép. | User A đọc hóa đơn B. |
| **Denial of Service** | Làm suy giảm hoặc ngừng dịch vụ. | Queue backlog hoặc endpoint export bị lạm dụng. |
| **Elevation of Privilege** | Tăng quyền trái phép. | Claim group từ IdP thành PlatformAdmin. |

STRIDE là một **cách phân loại gợi ý**, không phải phép chấm điểm rủi ro tự động. Một threat có thể thuộc nhiều nhóm; cần xem business impact và controls thật.

### Threat modeling theo luồng

~~~mermaid
flowchart TD
    A["Identify asset and business impact"] --> B["Draw components, data flows and boundaries"]
    B --> C["List actors and attacker capabilities"]
    C --> D["Derive threat scenarios"]
    D --> E["Define security requirements"]
    E --> F["Choose controls and design alternatives"]
    F --> G["Define verification and evidence"]
    G --> H{"Risk within acceptance criteria?"}
    H -- "No" --> I["Redesign / mitigate / escalate"]
    I --> F
    H -- "Yes with evidence" --> J["Record decision and reassessment triggers"]
~~~

### Ví dụ attack path

**Mục tiêu attacker:** lấy hóa đơn tenant B.

1. Tạo tài khoản hợp lệ ở tenant A.
2. Đoán hoặc thu thập invoice ID của tenant B.
3. Gọi API export.
4. API kiểm tra role nhưng không kiểm tra tenant ownership.
5. Worker nhận job và dùng database service account có quyền đọc toàn bộ dữ liệu.
6. File được tạo và link tải không ràng buộc với principal/tenant.

Nếu review chỉ kiểm tra API authentication, đường tấn công ở bước 4–6 bị bỏ sót. Cần **authorization ở object, job và download**, cùng test đầu-cuối.

## 9. Các nguyên tắc kiến trúc an toàn

Các nguyên tắc dưới đây hỗ trợ thiết kế; mỗi nguyên tắc phải được cụ thể hóa thành yêu cầu, control và evidence phù hợp.

| Nguyên tắc | Ý nghĩa | Dấu hiệu trong kiến trúc |
| --- | --- | --- |
| **Least privilege** | Mỗi identity chỉ có quyền cần thiết cho nhiệm vụ. | Role/workload permissions nhỏ, hạn quyền và review định kỳ. |
| **Default deny / secure defaults** | Mặc định từ chối nếu không có căn cứ cho phép. | API, storage, network và policy có trạng thái mặc định an toàn. |
| **Defense in depth** | Nhiều lớp độc lập giảm phụ thuộc vào một control. | Authz tại app, DB scoping, storage policy và monitoring. |
| **Separation of duties** | Tách nhiệm vụ hoặc quyết định có nguy cơ xung đột. | Request/approval, deploy/admin, key admin/data access. |
| **Complete mediation** | Kiểm tra quyền tại mỗi điểm truy cập phù hợp. | API, worker, export, download và object-level checks. |
| **Minimize attack surface** | Giảm endpoint, port, dependencies và quyền không cần. | Service exposure hẹp, egress allowlist, dependency cleanup. |
| **Fail securely** | Lỗi không làm mở quyền hoặc bỏ qua bảo vệ. | Auth/KMS/policy outage không chuyển sang chế độ cho phép rộng. |
| **Isolation/compartmentalization** | Hạn chế blast radius khi một thành phần bị xâm nhập. | Tenant isolation, account separation, workload boundaries. |
| **Assume breach / verify explicitly** | Không tin chỉ vì request đến từ mạng nội bộ. | Workload identity, policy, telemetry và revalidation. |
| **Secure by design/default** | Bảo mật được xem từ đầu và mặc định hạn chế. | Threat modeling, approved baseline, privacy/data minimization. |
| **Observability/accountability** | Có thể phát hiện và truy nguyên hành động quan trọng. | Audit events, correlation IDs, alerting và log protection. |
| **Resilience/recoverability** | Duy trì hoặc phục hồi chức năng khi có sự cố. | Backup/DR, isolation, runbooks và restore tests. |

### Tránh áp dụng khẩu hiệu một cách máy móc

“Defense in depth” không có nghĩa thêm càng nhiều sản phẩm càng tốt. Nhiều control trùng nhau nhưng cùng phụ thuộc một identity hoặc một policy có thể tạo **common-mode failure**. Reviewer cần xác định **mỗi lớp xử lý threat nào, phụ thuộc vào đâu và bằng chứng độc lập nào**.

## 10. Kiến trúc identity và access management

Identity là ranh giới quan trọng giữa người, service và tài nguyên.

### Các yếu tố cần review

- Nguồn danh tính: IdP, local account, federation, workload identity.
- Authentication strength, MFA/step-up, session lifetime và account recovery.
- Authorization model: RBAC, ABAC, ReBAC, ACL, direct grants.
- Tenant/object-level authorization, resource ownership và context integrity.
- Service-to-service identity, token audience/scope và credential lifecycle.
- Admin/PAM/JIT/break-glass, approval và audit.
- JML, provisioning/deprovisioning, stale accounts và role review.
- Cache, session, token revocation và quyền sau khi thay đổi.

### Sơ đồ identity flow

~~~mermaid
sequenceDiagram
    participant U as User
    participant IDP as Trusted IdP
    participant API as API / Relying Party
    participant AUTH as Authorization
    participant DATA as Tenant Data
    U->>API: Start login
    API-->>U: Redirect with protected transaction
    U->>IDP: Authenticate
    IDP-->>API: Verified federation response
    API->>API: Bind issuer + subject + tenant context
    U->>API: Request object action
    API->>AUTH: Principal + action + resource + context
    AUTH-->>API: Allow / Deny
    API->>DATA: Tenant-scoped operation if allowed
    API-->>U: Minimal authorized response
~~~

**Một token hợp lệ không phải quyền truy cập vô hạn.** Review cần phân biệt authentication, identity binding và authorization theo resource.

### Service identity cần được review như user đặc quyền

Worker, CI runner, cron job, controller và integration account có thể truy cập lượng dữ liệu lớn hơn người dùng. Mỗi identity cần owner, purpose, scope, credential/key lifecycle, monitoring và tests về hành động bị cấm.

## 11. Kiến trúc dữ liệu, tenant isolation và privacy

Một kiến trúc có nhiều tenant phải mô tả rõ **cách phân tách dữ liệu và quyền**. Các lựa chọn thường gặp:

| Mô hình | Đặc điểm | Rủi ro cần review |
| --- | --- | --- |
| **Shared DB, shared schema** | Dữ liệu tenant dùng chung bảng và có tenant key. | Query thiếu tenant predicate, cache key sai, quyền service rộng. |
| **Shared DB, separate schema** | Mỗi tenant có schema riêng trong cùng DB. | Cross-schema grants, migration và connection routing. |
| **Separate database per tenant** | Mỗi tenant có DB riêng. | Quản trị nhiều DB, backup, credentials, routing và chi phí. |
| **Separate account/project/environment** | Ranh giới hạ tầng mạnh hơn theo mô hình cloud. | Cross-account trust, shared control plane, central admin và drift. |

Không có một mô hình phù hợp mọi hệ thống. Review phải căn cứ **mức độ nhạy cảm, blast radius, yêu cầu khách hàng, khả năng vận hành, chi phí và evidence thực tế**.

### Data flow cần bao gồm cả bản sao

DB chính có isolation tốt nhưng analytics warehouse, search index, cache, export, backup, logs hoặc support tooling có thể dùng policy khác. Mỗi bản sao cần **owner, purpose, classification, retention và authorization**.

### Privacy by design

Security architecture review nên hỏi:

- Có thu thập/chuyển trường dữ liệu vượt nhu cầu không?
- Data flow có người nhận/vendor mới hoặc mục đích mới không?
- Có cơ chế xóa/sửa/retention đồng bộ với downstream không?
- Analytics, logs và test environments có dữ liệu cá nhân thật không cần thiết?
- Các privacy requirements có thể kiểm thử ở API, event và storage không?

## 12. Network architecture và service-to-service communication

Network segmentation có thể giảm khả năng di chuyển ngang, nhưng không nên xem **network location là bằng chứng danh tính**.

### Các câu hỏi review

1. Ingress public nào thực sự cần mở? Endpoint admin có bị expose không?
2. Egress có bị giới hạn theo nhu cầu và theo workload không?
3. Service-to-service có authentication/authorization và bảo vệ kênh phù hợp?
4. Có trust giữa VPC/VNet, peering, private endpoints, shared services hoặc vendor connections?
5. DNS, service discovery và certificate validation có được bảo vệ?
6. Có kiểm soát east-west traffic và metadata/management plane?
7. Khi một pod/service bị compromise, attacker có thể truy cập tài nguyên nào?
8. Network policy có được kiểm tra effective state thay vì chỉ đọc IaC?

### Kiểm soát nhiều lớp

- Public ingress hẹp, WAF/rate limits khi phù hợp.
- Network segmentation và egress policy.
- TLS/mTLS theo threat model và trust boundary.
- Workload identity và authorization tại service.
- Secrets không được truyền qua environment/log không cần thiết.
- Network flow logs, alerting và runbooks.

**Private subnet không tự chứng minh dữ liệu được bảo vệ.** Một workload có thể được gọi bởi service khác trong cùng vùng nhưng vẫn cần kiểm tra identity, scope và tenant.

## 13. API, event-driven và asynchronous architecture

Các kiến trúc API/event thường mở rộng bề mặt tấn công vì dữ liệu có thể được xử lý **sau khi request ban đầu đã kết thúc**.

| Thành phần | Điểm cần review |
| --- | --- |
| **API Gateway** | Authentication, routing, rate limiting, request size, schema validation, TLS termination. |
| **Application API** | Object-level authorization, tenant binding, business rules, idempotency, data minimization. |
| **Webhook** | Sender authentication, signature/timestamp, replay protection, endpoint allowlist. |
| **Message broker** | Producer/consumer ACL, topic separation, encryption, retention, DLQ. |
| **Background worker** | Workload identity, tenant context, job integrity, least privilege, retry safety. |
| **Export/download** | Ownership check, short-lived access, file scanning nếu phù hợp, lifecycle. |
| **Internal API** | Không mặc định trusted; có authentication, authorization, versioning và audit. |

### Transaction boundary và outbox

Nếu API commit DB rồi mới gửi event, một lỗi giữa hai bước có thể làm trạng thái không đồng bộ. Kiến trúc có thể sử dụng **transactional outbox** hoặc cơ chế bền vững tương đương; reviewer cần xem idempotency, duplicate, replay, ordering và reconciliation. Đừng giả định broker cung cấp exactly-once end-to-end cho mọi side effect.

### API versioning và backward compatibility

Một field mới có thể làm thay đổi classification hoặc recipients. Schema tương thích về cú pháp không tự bảo đảm tương thích về bảo mật. Thay đổi contract phải kích hoạt review data purpose, permission và consumer inventory.

## 14. Application architecture và secure coding boundaries

Review nên xem nơi nào thực thi business authorization và dữ liệu tin cậy được tạo ở đâu.

- Không để controller chỉ kiểm tra role chung trong khi service/repository không giới hạn resource.
- Không lấy tenantId, ownerId, isAdmin từ request mà không xác minh nguồn.
- Tách DTO theo mục đích thay vì serialize toàn bộ entity.
- Kiểm tra input/output, deserialization, SSRF, injection và file upload theo threat.
- Xử lý lỗi không tiết lộ secrets, PII hoặc trạng thái nội bộ.
- Cẩn thận cache key, race conditions, concurrency và retry.
- Tách quyền admin, data access và deployment khi phù hợp.
- Dùng framework/security library được duy trì, quản lý dependency và secure defaults.

### Ví dụ Java/Spring: authorization ở tầng service

~~~java
@Service
public class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public InvoiceSummary getInvoice(
            UUID invoiceId, VerifiedPrincipal principal) {

        String tenantId = principal.tenantId();
        if (tenantId == null || !principal.mayReadInvoices()) {
            throw new AccessDeniedException("Not authorized");
        }

        Invoice invoice = repository
                .findByIdAndTenantId(invoiceId, tenantId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND));

        return new InvoiceSummary(
                invoice.getId(),
                invoice.getIssueDate(),
                invoice.getAmount(),
                invoice.getStatus());
    }
}
~~~

Đây là mẫu minh họa. VerifiedPrincipal phải đến từ security context đã xác minh, không phải request body/header do client tự đặt. Method cần được gọi qua cơ chế bảo vệ thực tế; test phải xác nhận authorization được thực thi trong cấu hình Spring Security đang dùng. Việc giới hạn truy vấn theo tenant là một lớp; worker/export/search cần kiểm tra riêng.

### Test architecture assumptions

- User A không đọc object B dù biết ID.
- Role viewer không thể export nếu policy không cho.
- Principal thiếu tenant bị từ chối.
- Internal service không được tin chỉ vì nằm trong private network.
- Error/trace không lộ entity hoặc token.
- Cache không trả response từ tenant khác.

## 15. Cloud architecture và shared responsibility

Cloud không làm mất trách nhiệm thiết kế kiến trúc. Cần xác định **provider quản lý gì, tổ chức cấu hình gì, workload vận hành gì và bằng chứng đến từ đâu**.

### Các lớp cần xem

| Lớp | Câu hỏi |
| --- | --- |
| **Organization/account hierarchy** | Có tách production/non-production, central security/logging và delegated admin không? |
| **IAM** | Root/admin access, federation, roles, permission boundaries, cross-account trust ra sao? |
| **Network** | VPC/VNet, routes, firewall/security groups, private endpoints, egress và DNS? |
| **Compute/container** | Image, runtime identity, secrets, isolation, admission policies, patching? |
| **Storage/database** | Encryption, access policies, backup, public exposure, data lifecycle? |
| **KMS/secrets** | Key ownership, grants, rotation, recovery và audit? |
| **Logging/monitoring** | Centralization, immutable/tamper-resistant storage khi cần, coverage và alerts? |
| **Control plane** | Ai có thể thay policy, disable logging, tạo credential hoặc deploy resource? |
| **IaC/CI/CD** | Change approval, policy-as-code, artifact integrity, secret handling? |

### Shared responsibility phải được lập thành ma trận

Không nên ghi chung “cloud provider bảo mật hạ tầng”. Hãy xác định control cụ thể:

- Provider vận hành lớp vật lý hoặc managed service nào?
- Khách hàng phải bật/cấu hình quyền, encryption, logging hoặc network?
- Ai chịu trách nhiệm patch OS/runtime/container image?
- Ai quản lý key, certificate và secret?
- Bằng chứng provider cung cấp có đúng dịch vụ, region, thời kỳ và control không?
- Những control do khách hàng cấu hình có được kiểm tra runtime không?

Một chứng nhận của provider không tự chứng minh account của tổ chức đã cấu hình an toàn.

## 16. Container, Kubernetes và workload isolation

Khi sử dụng Kubernetes hoặc nền tảng container, kiến trúc review nên xem cả **control plane, node, pod, network và identity**.

| Thành phần | Rủi ro kiến trúc | Câu hỏi/control |
| --- | --- | --- |
| **API server/control plane** | Quyền cluster-admin rộng hoặc endpoint mở. | Authentication, RBAC, audit, private endpoint và admin path. |
| **Namespace** | Coi namespace là ranh giới isolation tuyệt đối. | Network policies, RBAC, admission và shared resources. |
| **Service account** | Pod có token/quyền vượt nhu cầu. | Workload identity, automount/token scope, least privilege. |
| **Secrets** | Secret lưu/đọc quá rộng, xuất ra logs. | Secret manager, encryption, rotation, access audit. |
| **Container image** | Image dễ bị thay, dependency có lỗ hổng. | Trusted registry, signing/provenance, scanning, pinning. |
| **Node/runtime** | Container escape hoặc host compromise ảnh hưởng nhiều workload. | Isolation, patching, hardening, runtime detection. |
| **Network** | Pod-to-pod mặc định rộng. | NetworkPolicy, mTLS/identity-aware controls, egress limits. |
| **Persistent volumes** | Dữ liệu lưu trữ và snapshot bị truy cập sai. | Storage class, encryption, IAM, backup/restore. |

**Namespace không tự là security boundary hoàn chỉnh.** Nếu threat model yêu cầu isolation mạnh hơn, có thể cần tách cluster, account, node pool hoặc cơ chế khác; quyết định phải dựa trên blast radius, chi phí và khả năng vận hành.

## 17. Supply chain, CI/CD và software delivery architecture

Một attacker không cần khai thác API nếu có thể **thay artifact hoặc pipeline trước khi deploy**.

### Những ranh giới cần review

- Developer workstation → source repository.
- Repository → CI runner.
- CI → dependency registries và build tools.
- Build artifact → registry/signing service.
- Deployment controller → production cluster.
- Production runtime → secrets/configuration.

### Controls quan trọng

- Branch protection, review độc lập và quyền merge/deploy rõ.
- CI runner ephemeral/hardening, hạn chế secrets và network egress.
- Dependency pinning, provenance, SBOM và vulnerability management.
- Artifact signing/verification và bảo vệ signing keys.
- IaC review, policy-as-code và drift detection.
- Tách build và deploy credentials; approval phù hợp cho production.
- Audit pipeline configuration và thay đổi quyền.

### Threat scenario

Một CI runner có quyền đọc tất cả secrets production và có thể sửa deployment policy. Nếu runner bị compromise, attacker có thể phát hành mã độc hoặc truy cập dữ liệu. Review phải xem **quyền của runner, artifact trust, secret exposure, approval và khả năng phát hiện**, không chỉ kiểm tra source code có scan hay không.

## 18. Secrets, certificates và cryptographic architecture

Review cần xem:

- Secret nằm ở đâu, ai có thể đọc, thời gian sống và cách rotation?
- Key mã hóa dữ liệu có tách khỏi dữ liệu ciphertext và workload cần thiết không?
- Có phân tách key administration và data access khi phù hợp?
- TLS/mTLS có được xác minh ở từng hop và endpoint?
- Certificate lifecycle, CA trust, revocation và expiration được theo dõi?
- Có backup/DR cho key dependencies và test khôi phục?
- Có versioning và crypto agility khi cần đổi thuật toán?
- Plaintext/key material có lọt vào logs, traces, crash dumps hoặc CI output?

**Encryption không thay authorization.** Nếu service được phép decrypt nhưng trả plaintext cho user sai tenant, kiến trúc vẫn có lỗi. Key management phải gắn với workload identity, data flow và effective permissions.

## 19. Logging, monitoring, incident response và resilience

Kiến trúc an toàn phải có khả năng **phát hiện, điều tra và phục hồi**, không chỉ phòng ngừa.

### Observability cần trả lời

- Sự kiện nào cần audit: login, quyền, data export, admin action, key use, policy change?
- Có correlation giữa user, request, job, resource và service không?
- Log có bị sửa/xóa bởi cùng identity có quyền gây sự cố không?
- Có dữ liệu nhạy cảm không cần thiết trong logs/traces?
- Có alert khi collector im lặng, ingestion lag hoặc nguồn quan trọng mất?
- Ai được đọc, xuất, xóa và thay đổi retention?

### Resilience/recovery

- Backup có độc lập đủ với production để hạn chế blast radius?
- Có kiểm tra restore, integrity và khả năng truy cập khóa?
- RTO/RPO có xuất phát từ business impact và được test?
- Có circuit breaker, rate limits, queue backpressure và graceful degradation?
- Failure của IdP/KMS/DNS/vendor dẫn tới hành vi fail securely nào?
- Runbook có owner, quyền thực thi, rollback và evidence?

**Một hệ thống fail closed sai cách vẫn có thể tạo sự cố availability.** Review cần cân bằng confidentiality, integrity và availability, đồng thời ghi rõ các trade-offs và cơ chế ứng cứu.

## 20. Security requirements và control mapping

Mỗi rủi ro quan trọng phải được chuyển thành **security requirement testable**.

| Risk scenario | Security requirement | Architectural control | Verification |
| --- | --- | --- | --- |
| User A truy cập invoice B. | Mọi thao tác đọc/export phải kiểm tra quyền trên object và tenant. | Tenant-scoped service/repository, authorization policy. | Cross-tenant negative tests trên API/worker/download. |
| Worker bị compromise. | Workload chỉ có quyền cần cho nhiệm vụ và dữ liệu trong scope. | Workload identity, scoped IAM, isolated queues. | Effective permission review, denied operations. |
| Token từ IdP sai được chấp nhận. | Chỉ issuer/client/response hợp lệ được tạo session. | Federation trust registry và OIDC/SAML validation. | Wrong issuer/audience/state/replay tests. |
| File export bị chia sẻ rộng. | Download phải được authorization và giới hạn thời gian. | Private storage, scoped download mechanism, lifecycle. | Anonymous/wrong tenant/expired link tests. |
| Key admin đọc dữ liệu không cần. | Key policy và data access tách theo nhiệm vụ. | KMS IAM, SoD, approval/JIT. | Effective grants và negative decrypt tests. |
| CI bị compromise. | Build/deploy identity không có quyền vượt nhiệm vụ. | Runner isolation, artifact verification, scoped credentials. | Pipeline permission tests, provenance verification. |
| Log bị tắt khi incident. | Security event sources trọng yếu được giám sát và bảo vệ. | Central audit, immutable controls khi phù hợp, health alerts. | Disable-source simulation, alert and access review. |

### Requirement cần đo được

Tránh câu “hệ thống phải bảo mật tốt”. Viết rõ:

- **Actor:** ai thực hiện.
- **Action:** làm gì.
- **Resource/scope:** trên tài sản hoặc tenant nào.
- **Condition:** thời điểm, trạng thái hoặc ngữ cảnh.
- **Expected result:** allow/deny, audit, timeout hoặc recovery behavior.
- **Evidence:** test/config/log nào hỗ trợ kết luận.

## 21. Architecture Decision Record (ADR) và security trade-offs

ADR ghi lại **quyết định kiến trúc**, lựa chọn đã xem xét, lý do, hệ quả và trạng thái. Nó giúp người review sau hiểu tại sao một control được chọn và những rủi ro nào đã được chấp nhận.

### Cấu trúc ADR nên có

1. **Title/ID/status/date/owners.**
2. **Context:** business need, constraints, assets, trust assumptions.
3. **Decision drivers:** security objectives, scale, availability, cost, privacy, compliance.
4. **Options considered:** các lựa chọn thực tế và trade-offs.
5. **Decision:** chọn gì, phạm vi áp dụng và điều kiện.
6. **Security implications:** threats mitigated, residual risks, dependencies.
7. **Controls/verification:** yêu cầu, tests, evidence, owner.
8. **Reassessment triggers:** thay đổi nào khiến quyết định phải xem lại.

### Ví dụ: tenant isolation model

| Option | Ưu điểm | Trade-offs/rủi ro |
| --- | --- | --- |
| Shared DB/shared schema | Vận hành đơn giản, chi phí thấp. | Phụ thuộc query scoping, cache, service identities; blast radius rộng. |
| Separate schema | Phân tách logic tốt hơn trong một DB. | Quản lý migration, grants, schema routing phức tạp. |
| Database per tenant | Ranh giới dữ liệu rõ hơn. | Quản trị/backup/monitoring nhiều tài nguyên, cross-tenant operations phức tạp. |
| Account/project per tenant | Có thể tăng isolation ở control plane. | Cost, scale, central administration và cross-account trust. |

**Không chọn một phương án chỉ vì tên gọi secure.** ADR cần ghi requirement và phép kiểm tra tương ứng; nếu shared DB được chọn, phải có evidence về query scoping, policy, tests và monitoring.

## 22. Review workflow end-to-end

~~~mermaid
flowchart TD
    A["Request + business context + change scope"] --> B["Collect architecture views and assets"]
    B --> C["Validate data flows and trust boundaries"]
    C --> D["Threat model and risk assessment"]
    D --> E["Map security requirements and controls"]
    E --> F["Review design alternatives and ADRs"]
    F --> G["Define tests, evidence and owners"]
    G --> H{"Critical risks resolved or accepted?"}
    H -- "No" --> I["Redesign / mitigation / escalation"]
    I --> D
    H -- "Yes with evidence" --> J["Record decision, scope and expiry"]
    J --> K["Implementation verification / release gate"]
    K --> L["Monitor drift, incidents and reassessment triggers"]
~~~

### Bước 1 — Xác định mục tiêu, scope và reviewer

Nêu hệ thống, phiên bản, environment, data classification, thay đổi và những thành phần ngoài scope. Chỉ định **architect, service owner, data owner, security/control owner, assurance reviewer và risk owner** theo nhu cầu. Reviewer phải có đủ độc lập tương xứng với rủi ro.

### Bước 2 — Thu thập và kiểm tra views

Đối chiếu context, component, deployment, data flow, identity, cloud, supply chain và operations. Ghi ngày/version và nguồn; phát hiện mâu thuẫn giữa sơ đồ, IaC và hiện trạng.

### Bước 3 — Threat model và risk assessment

Xác định assets, actors, attack paths, abuse cases, impact, likelihood, existing controls và assumptions. Ưu tiên rủi ro liên quan dữ liệu nhạy cảm, quyền cao, tenant boundary, internet exposure và recovery.

### Bước 4 — Đánh giá controls và lựa chọn thiết kế

Kiểm tra controls có **prevent, detect, respond, recover** theo yêu cầu. So sánh phương án và ghi trade-offs trong ADR. Không yêu cầu mọi hệ thống dùng một mẫu kiến trúc duy nhất.

### Bước 5 — Định nghĩa verification plan

Với từng requirement ghi test method, expected/observed, environment, data set, owner, thời điểm và evidence repository. Có cả positive, negative và failure-mode tests.

### Bước 6 — Ghi findings và quyết định

Finding phải có mô tả, evidence, risk, affected scope, recommendation, owner, due date và retest. Nếu chấp nhận ngoại lệ, phải có thẩm quyền, scope, expiry, compensating controls và trigger.

### Bước 7 — Kiểm tra implementation trước/sau release

Đối chiếu architecture/ADR với code, IaC, cloud config, runtime identity, test và monitoring. Thay đổi lớn sau review có thể làm conclusion hết hiệu lực.

### Bước 8 — Theo dõi liên tục

Theo dõi drift, dependency, incident, key/identity changes và findings; kích hoạt review lại khi điều kiện thay đổi.

## 23. Phân tích và ưu tiên rủi ro

Không nên chấm risk chỉ theo số lượng findings. Cần xác định **impact, likelihood, exploitability, exposure, data sensitivity, blast radius và control strength** theo phương pháp của tổ chức.

### Một rubric minh họa

| Yếu tố | Mức thấp | Mức cao |
| --- | --- | --- |
| **Data sensitivity** | Dữ liệu công khai, ít hậu quả nếu lộ. | Dữ liệu cá nhân nhạy cảm, bí mật kinh doanh, khóa. |
| **Exposure** | Internal path hạn chế, identity rõ. | Public endpoint, partner hoặc nhiều trust boundaries. |
| **Privilege/blast radius** | Quyền hẹp, một tài nguyên. | Admin, cross-tenant, shared service hoặc control plane. |
| **Exploitability** | Cần nhiều điều kiện khó đạt. | Đường đơn giản, dễ lặp lại hoặc có thể tự động hóa. |
| **Impact** | Tác động nhỏ và dễ phục hồi. | Disclosure lớn, gian lận, gián đoạn nghiêm trọng hoặc ảnh hưởng nhiều người. |
| **Existing controls** | Independent controls có test/evidence. | Control thiếu, dễ bypass hoặc chưa kiểm chứng. |

Có thể dùng ma trận likelihood × impact, nhưng phải ghi **định nghĩa mức, nguồn dữ liệu và người quyết định**. Không đưa ra một điểm số giả chính xác nếu không có phương pháp hoặc evidence.

### Current risk và target risk

- **Current/inherent risk:** rủi ro trước controls hoặc theo trạng thái baseline được định nghĩa.
- **Current residual risk:** rủi ro còn lại với controls thực sự đang vận hành.
- **Target residual risk:** mức dự kiến sau mitigation và verification.

Không được tính một control chưa triển khai như thể đã giảm current residual risk. Một kế hoạch remediation có thể giảm **target risk**, không thay đổi hiện trạng ngay lúc review.

## 24. Design effectiveness và operating effectiveness

### Design effectiveness

Review kiến trúc chủ yếu đánh giá:

- Requirements có bao phủ threats và obligations trong scope không?
- Control đặt đúng ranh giới và đúng điểm ra quyết định?
- Có giảm quyền, cô lập blast radius và tránh single point of failure?
- Failure mode có fail securely và có recovery path?
- Control có thể được test, monitor và audit?
- Assumptions/dependencies có owner và được xác minh?

### Operating effectiveness

Để kết luận controls thực sự hoạt động, cần evidence từ implementation/vận hành:

- Effective IAM/network/storage policies ở release và environment được đánh giá.
- Negative/positive tests trên API, worker, export và admin path.
- Log/alert health và hành động response.
- Change records, drift history, key rotation, access review.
- Backup/restore drills, incident exercises và retests.
- Ngoại lệ, findings và remediation trong thời kỳ.

**Một kiến trúc review PASS không chứng minh production đã triển khai đúng.** Ngược lại, một test PASS đơn lẻ không chứng minh thiết kế tổng thể không có attack path khác.

## 25. Evidence strategy: Claim – Argument – Evidence

### Claim minh họa

“Kiến trúc Invoice SaaS release 3.2 trong production hỗ trợ cô lập dữ liệu giữa tenants, giới hạn quyền service/workload và bảo vệ các luồng export thuộc scope theo security requirements được duyệt.”

### Argument

1. Context/data flow và deployment views xác định toàn bộ đường đọc/ghi/export quan trọng.
2. Threat model nêu các cross-tenant, privilege escalation và data disclosure scenarios.
3. Architecture requirements được ánh xạ vào API, worker, DB, broker và storage controls.
4. IaC/config/code review chứng minh controls được hiện thực theo thiết kế.
5. Positive/negative tests, runtime policies và logs chứng minh controls hoạt động trong scope.
6. Findings/assumptions/limitations được xử lý hoặc chấp nhận theo thẩm quyền.

### Evidence

- Versioned diagrams, data flow register và architecture inventory.
- Threat model, risk register, security requirements và ADR.
- IAM/KMS/network/storage policy snapshots có nguồn và timestamp.
- Code/config reviews, CI results, integration/security tests.
- Production verification, logs/alerts và recovery drills.
- Findings, tickets, retest reports và risk acceptance records.

### Ma trận requirement → control → test → evidence

| Requirement | Architectural control | Verification | Evidence |
| --- | --- | --- | --- |
| **SAR-01 Tenant isolation** | Tenant-scoped data access, object authorization. | Cross-tenant API/worker/export negative tests. | Test reports, effective policies, query/config review. |
| **SAR-02 Identity trust** | Trusted IdP registry, service identity and token validation. | Wrong issuer/audience, forged principal, revoked identity. | Auth config, test output, identity logs. |
| **SAR-03 Least privilege** | Scoped workload roles, SoD, JIT/PAM. | Effective permission and denied-action tests. | IAM policy, role review, KMS audit. |
| **SAR-04 Data protection** | TLS, storage encryption, key lifecycle, minimization. | TLS/config scan, decrypt/authorization, field tests. | KMS/storage config, data samples, test artifacts. |
| **SAR-05 Secure operations** | Central audit, alerts, incident runbooks. | Disable-source/alert simulation and incident exercise. | Alert records, log health, runbook execution. |
| **SAR-06 Recovery** | Backup isolation, key dependencies, DR design. | Restore drill and RTO/RPO measurement. | Restore logs, data reconciliation, exercise report. |
| **SAR-07 Supply chain** | Signed artifacts, protected CI/CD and dependency governance. | Pipeline permissions, artifact verification, provenance. | SBOM, signatures, CI policy, deployment records. |
| **SAR-08 Change assurance** | Architecture gates and drift detection. | Add consumer/permission test, config drift simulation. | ADR, review approvals, CI gates, drift alerts. |

### Evidence có thể bác bỏ thiết kế

Nếu sơ đồ nói storage private nhưng runtime policy cho phép public access, đó là evidence mâu thuẫn. Nếu ADR yêu cầu mTLS nhưng một internal hop dùng plaintext, cần ghi finding. **Không được bỏ qua evidence trái chiều** hoặc coi tài liệu thiết kế là sự thật cuối cùng.

## 26. Review findings và xử lý remediation

Một finding phải đủ rõ để owner có thể tái tạo và assessor có thể retest.

### Cấu trúc finding

| Trường | Nội dung |
| --- | --- |
| **Finding ID/title** | Định danh duy nhất và mô tả cụ thể. |
| **Affected scope** | Service, version, tenant, environment, component/flow. |
| **Observed evidence** | Config/test/log/diagram thực tế, nguồn và thời điểm. |
| **Expected requirement** | Control/requirement/ADR mà thiết kế chưa đáp ứng. |
| **Threat and impact** | Attack path và hậu quả có thể xảy ra. |
| **Severity/risk rationale** | Phương pháp đánh giá, giả định và owner. |
| **Recommendation** | Thay đổi thiết kế/control cụ thể, có thể kiểm chứng. |
| **Owner/due date** | Người chịu trách nhiệm và thời hạn. |
| **Compensating control/exception** | Biện pháp tạm, approval, scope và expiry nếu có. |
| **Retest criteria/evidence** | Expected result, phương pháp và bằng chứng đóng. |

### Ví dụ finding

**SAR-F-07 — Export Worker thiếu ràng buộc tenant khi truy vấn dữ liệu**

- **Observed:** job message có tenant ID từ payload; worker dùng service identity có quyền đọc mọi tenant; không thấy kiểm tra job ownership trước truy vấn.
- **Threat:** attacker có thể tạo/thay tenant context và làm worker xuất dữ liệu của tenant khác.
- **Requirement:** worker chỉ xử lý job gắn với principal/tenant đã xác minh và resource scope được duyệt.
- **Recommendation:** tạo job record server-side, bind actor/tenant, giới hạn worker permissions và kiểm tra quyền tại download.
- **Retest:** forged tenant/job, cross-tenant data, retry và download tests phải bị từ chối; policy effective access phải phù hợp.

### Đóng finding

Ticket được đánh dấu Done chưa đủ. Assessor cần xem **thay đổi thực tế, release, test expected/observed, population và phạm vi**. Nếu mitigation chỉ giảm một phần risk, finding có thể chuyển Partial hoặc residual risk acceptance theo thẩm quyền thay vì đóng PASS.

## 27. Review architecture trong môi trường multi-tenant SaaS: ví dụ đầy đủ

### Bối cảnh

Invoice SaaS có:

- Browser/mobile clients và customer IdPs.
- Public API gateway và các microservices.
- Shared relational database có tenant_id.
- Message broker, background workers và export object storage.
- Analytics warehouse, email vendor, centralized logs.
- KMS, CI/CD và cloud control plane.

**Security objectives:**

1. Tenant A không đọc/sửa/xuất dữ liệu tenant B.
2. User và service chỉ có quyền cần thiết.
3. Data flow tới analytics/vendor có mục đích, trường và người nhận được kiểm soát.
4. Secrets, keys, network và artifacts được bảo vệ.
5. Sự kiện quan trọng có thể phát hiện/điều tra; dữ liệu có thể phục hồi.

### Architecture review phát hiện

| ID | Quan sát | Rủi ro | Yêu cầu/control cần bổ sung |
| --- | --- | --- | --- |
| **F-01** | API kiểm tra role nhưng query không gắn tenant. | Cross-tenant access. | Object-level authz và tenant-scoped query/tests. |
| **F-02** | Worker service account đọc mọi tenant. | Blast radius khi worker bị compromise. | Scope IAM, trusted job context và isolation. |
| **F-03** | Download URL sống lâu và không ràng buộc principal. | File disclosure khi link bị chia sẻ. | Scoped/short-lived access và reauthorization. |
| **F-04** | Event analytics serialize nguyên entity. | Personal data vượt mục đích. | DTO allowlist, schema contract và data owner review. |
| **F-05** | CI runner giữ credentials production rộng. | Supply-chain compromise. | Runner isolation, short-lived credentials và deploy approval. |
| **F-06** | KMS key policy dùng chung với role support. | Key misuse và dữ liệu bị giải mã sai nhiệm vụ. | Least privilege, SoD, negative decrypt tests. |
| **F-07** | Log collector không có health alert. | Mất khả năng phát hiện và evidence. | Source health, ingestion lag và tamper controls. |
| **F-08** | Backup chưa restore bằng key version cũ. | Không phục hồi được sau incident. | Key dependency inventory và DR restore test. |

### Đánh giá sau thiết kế lại

- API và worker dùng trusted tenant context; truy vấn và quyền storage được test độc lập.
- Worker identity chỉ có quyền trên job/data scope cần thiết.
- File download có authorization, expiration và audit.
- Analytics event dùng allowlisted fields và consumer inventory.
- CI/CD credentials ngắn hạn, scope hẹp và artifact verification.
- KMS roles tách theo purpose, support không có Decrypt ngoài nhiệm vụ.
- Logging có health monitoring và quyền đọc hạn chế.
- DR restore drill chứng minh key dependency và data integrity.

**Kết luận review** chỉ được nâng trạng thái sau khi các controls đã triển khai và evidence đáp ứng tiêu chí. Nếu sơ đồ mới được duyệt nhưng chưa có runtime tests, trạng thái phải nêu rõ **Design reviewed / Implementation verification pending**.

## 28. Kiểm thử kiến trúc và verification matrix

| Test ID | Kịch bản | Kết quả cần chứng minh |
| --- | --- | --- |
| **SAR-T01** | User tenant A đọc object tenant B qua API. | Deny; không có data leakage qua body/error/log. |
| **SAR-T02** | User A gửi tenant B trong header/body. | Server giữ tenant context từ principal đã xác minh. |
| **SAR-T03** | Worker nhận job payload bị sửa hoặc replay. | Không xử lý sai tenant; idempotency và audit phù hợp. |
| **SAR-T04** | Download link của A được user B sử dụng. | Bị từ chối hoặc theo policy xác minh lại. |
| **SAR-T05** | Service identity gọi KMS/database ngoài scope. | Deny và có audit/alert theo control. |
| **SAR-T06** | Token sai issuer/audience hoặc revoked. | Không tạo session/không thực hiện action. |
| **SAR-T07** | API rate/size abuse làm cạn tài nguyên. | Rate limits/backpressure hoạt động theo yêu cầu. |
| **SAR-T08** | Internal service gọi endpoint không có authorization. | Bị từ chối; private network không tự bypass identity. |
| **SAR-T09** | Egress tới vendor/host không được phép. | Network/policy chặn hoặc alert theo design. |
| **SAR-T10** | Pod có quyền đọc secret của namespace khác. | RBAC/workload boundary từ chối. |
| **SAR-T11** | CI runner thử lấy secret production ngoài pipeline. | Không có quyền hoặc phải qua control được duyệt. |
| **SAR-T12** | Artifact không đúng signature/provenance. | Deployment gate từ chối. |
| **SAR-T13** | Public storage policy bị thay đổi ngoài IaC. | Drift detection phát hiện và xử lý. |
| **SAR-T14** | Audit collector bị tắt. | Health alert phát hiện mất nguồn. |
| **SAR-T15** | KMS/IdP/DNS timeout. | Failure behavior không mở quyền hoặc bỏ validation. |
| **SAR-T16** | Backup restore ở DR environment. | Dữ liệu và khóa phục hồi trong RTO/RPO. |
| **SAR-T17** | Schema thêm field nhạy cảm. | Privacy/security review và contract tests được kích hoạt. |
| **SAR-T18** | Admin tự thay role và tự phê duyệt. | SoD/approval policy chặn hoặc escalation. |
| **SAR-T19** | Một dependency có CVE nghiêm trọng được đưa vào build. | Dependency gate/triage theo policy. |
| **SAR-T20** | Một threat assumption thay đổi sau vendor/region migration. | Review trigger tạo reassessment và evidence mới. |

Tests phải chạy trong môi trường và phạm vi được phép, dùng synthetic data khi có thể. Không thực hiện destructive test, cross-tenant access vào dữ liệu thật hoặc disable control production nếu không có authorization và kế hoạch kiểm soát tác động.

## 29. Architecture review scorecard và kết luận

Scorecard hỗ trợ tổng hợp nhưng không thay thế phân tích. Có thể đánh giá theo các chiều:

| Dimension | Câu hỏi | Kết quả cần ghi |
| --- | --- | --- |
| **Scope/completeness** | Inventory, views, actors và flows có đầy đủ? | Covered / Partial / Gap + evidence. |
| **Threat coverage** | Rủi ro trọng yếu có được nhận diện? | Threat IDs, assumptions, omitted threats. |
| **Requirements** | Requirements có rõ, testable và traceable? | Requirement IDs và gaps. |
| **Control design** | Controls xử lý threat đúng boundary? | Design result và dependencies. |
| **Implementation alignment** | Code/IaC/runtime có khớp ADR/design? | Config/test evidence, drift. |
| **Operational readiness** | Logging, incident, backup/DR và ownership sẵn sàng? | Runbooks, exercises, owners. |
| **Third-party/supply chain** | External dependencies và shared responsibility được quản lý? | Inventory, contract, attestations và customer config. |
| **Residual risk** | Rủi ro còn lại có owner và quyết định đúng thẩm quyền? | Risk records, expiry, treatments. |

### Kết quả review có thể dùng

- **Approved:** các tiêu chí bắt buộc trong scope có evidence phù hợp và không còn blocker theo chính sách.
- **Approved with conditions:** có điều kiện cụ thể, owner, deadline, cách kiểm tra và risk authority.
- **Needs redesign:** kiến trúc hiện tại không xử lý được một threat/requirement trọng yếu.
- **Pending evidence:** thiết kế có vẻ phù hợp nhưng chưa đủ bằng chứng triển khai/kiểm chứng.
- **Rejected:** không thể chấp nhận theo tiêu chí hoặc nghĩa vụ áp dụng.
- **Not assessed:** scope hoặc đầu vào không đủ để đưa ra kết luận.

Không cộng trung bình điểm để che một **critical failure**. Ví dụ mọi chiều khác tốt nhưng cross-tenant authorization thất bại thì kết luận phải phản ánh blocker đó.

## 30. Architecture governance, ownership và RACI

| Vai trò | Trách nhiệm |
| --- | --- |
| **Solution/system architect** | Duy trì views, boundaries, design options và ADR. |
| **Security architect** | Xác định security requirements, threat model, control patterns và design review. |
| **Application/service owner** | Giải trình implementation, code/config, tests và vận hành. |
| **Data owner** | Classification, data flow, purpose, access và retention. |
| **Platform/cloud/network owner** | Hạ tầng, IAM, network, KMS, logging, container và recovery controls. |
| **Product/business owner** | Mục tiêu, trade-offs, người dùng, impact và chấp thuận thay đổi nghiệp vụ. |
| **Security assurance/independent assessor** | Kiểm tra evidence, design/operating effectiveness và findings. |
| **Risk owner** | Quyết định residual risk/exception trong thẩm quyền. |
| **Privacy/legal/compliance** | Xác định nghĩa vụ và ranh giới yêu cầu áp dụng. |
| **Change/release owner** | Bảo đảm điều kiện review, approval, deployment và retest. |

### RACI minh họa

**R** = thực hiện; **A** = chịu trách nhiệm cuối cùng; **C** = tham vấn; **I** = thông báo.

| Hoạt động | Solution architect | Security architect | Service owner | Assurance | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Xây architecture views/ADR | **A/R** | C | R | I | I |
| Threat model/security requirements | C | **A/R** | R | C | I |
| Triển khai controls và tests | C | C | **A/R** | C | I |
| Đánh giá độc lập/evidence | C | C | C | **A/R** | I |
| Chấp nhận residual risk | C | C | C | C | **A/R** |

Một người có thể đảm nhiệm nhiều vai trò ở tổ chức nhỏ, nhưng cần xem **xung đột lợi ích và mức độc lập**. Người tự thiết kế/triển khai không nhất thiết là reviewer độc lập cho mọi claim rủi ro cao.

## 31. Continuous Security Architecture Assurance

Kiến trúc thay đổi qua code, IaC, cloud configuration, vendors, identities và data flows. Review một lần ở đầu dự án không đủ cho hệ thống đang phát triển.

### Các trigger cần theo dõi

- New service/API/topic/consumer/storage hoặc trust boundary.
- Permission/role/service account, IdP, token flow hoặc admin path thay đổi.
- New data type, tenant, vendor, region, AI/analytics use.
- KMS/key/certificate/TLS policy hoặc cryptographic library thay đổi.
- Cloud account, VPC, cluster, deployment pipeline và runtime thay đổi.
- Critical dependency, vulnerability hoặc supply-chain incident.
- Thay RTO/RPO, backup/DR topology, logging/monitoring.
- Incident, audit finding, pen-test finding hoặc control failure.

### Architecture fitness functions

Có thể tự động kiểm tra một số thuộc tính kiến trúc:

- Không có public storage ngoài danh sách được duyệt.
- Workload identities không được dùng wildcard admin policies.
- Public endpoints có authentication và rate limit theo baseline.
- Service-to-service flows dùng identity và transport controls cần thiết.
- Database/backup/storage có encryption settings đúng baseline.
- Container images có provenance/signature theo policy.
- New data flows có owner, classification và purpose metadata.
- Production deploy phải tham chiếu ADR/review approval khi thay đổi thuộc scope.

**Fitness function không thay thế threat review.** Máy có thể phát hiện wildcard trong policy nhưng không biết một quyền hẹp hơn vẫn tạo attack path do business logic. Cần kết hợp static checks, human review và runtime evidence.

### Chu kỳ assurance

~~~mermaid
flowchart TD
    A["Architecture baseline + ADR + risk register"] --> B["Code/IaC/dependency changes"]
    B --> C["Automated fitness checks + human review"]
    C --> D["Deploy and runtime drift detection"]
    D --> E["Tests, telemetry, incidents, restore evidence"]
    E --> F{"Requirements still supported?"}
    F -- "No" --> G["Finding / redesign / remediation"]
    G --> H["Retest and risk decision"]
    H --> A
    F -- "Yes" --> I["Time-scoped assurance record"]
    I --> J["New threat / business / vendor / platform change"]
    J --> A
~~~

## 32. Chỉ số theo dõi chương trình review

| Metric | Mục đích | Giới hạn cần lưu ý |
| --- | --- | --- |
| **Architecture review coverage** | Tỷ lệ hệ thống/thay đổi trọng yếu được review theo tiêu chí. | Population và ngưỡng trọng yếu phải rõ. |
| **Threat model freshness** | Threat model được cập nhật theo kiến trúc hiện tại. | Ngày sửa file không chứng minh nội dung đúng. |
| **Requirement traceability** | Rủi ro → requirement → control → test → evidence. | Mapping đầy đủ trên giấy không chứng minh implementation. |
| **Critical findings aging** | Thời gian tồn tại của rủi ro nghiêm trọng. | Ticket age cần kết hợp impact và owner. |
| **Remediation/retest rate** | Findings đã sửa và kiểm tra lại. | Không tính closed by owner là retested. |
| **Architecture drift** | Thay đổi production ngoài baseline/ADR. | Collector thiếu coverage có thể bỏ sót drift. |
| **Third-party review coverage** | Dependency/vendor quan trọng được đánh giá. | Chứng nhận nhà cung cấp có scope/thời hạn riêng. |
| **Security test coverage** | Threat scenarios có tests phù hợp. | Số test lớn không bảo đảm threat quan trọng được bao phủ. |
| **Exception age/expiry** | Rủi ro được chấp nhận tạm có còn trong hạn? | Risk acceptance không phải control pass. |
| **Recovery readiness** | Restore/incident exercises đáp ứng mục tiêu. | Một lần diễn tập không đại diện mọi failure. |

Không tối ưu số lượng review hoặc tỷ lệ PASS bằng cách thu hẹp scope tùy tiện. **Chất lượng conclusion và mức giảm rủi ro** quan trọng hơn số lượng biểu mẫu đã ký.

## 33. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Có WAF, SIEM và EDR là kiến trúc an toàn.” | Cần xem trust boundaries, identity, data flow, quyền và khả năng bypass. |
| “Sơ đồ đã được duyệt nghĩa là production đúng.” | Cần đối chiếu code, IaC, runtime config và test evidence. |
| “Private subnet là trusted zone.” | Workload có thể bị compromise; cần identity, authorization và monitoring. |
| “JWT hợp lệ là user được truy cập mọi object.” | Authentication và authorization theo resource/tenant là hai quyết định khác nhau. |
| “API đã kiểm tra quyền thì worker không cần kiểm tra.” | Async worker là một principal và trust boundary riêng. |
| “Mọi tenant phải có database riêng mới an toàn.” | Isolation model phải theo threat, requirements, blast radius và evidence. |
| “Cloud provider chịu toàn bộ security.” | Shared responsibility: cấu hình IAM, data, workload và nhiều controls thuộc khách hàng. |
| “Namespace là ranh giới bảo mật hoàn chỉnh.” | Cần xem cluster/control plane, RBAC, network, node và workload identities. |
| “Mã hóa giải quyết mọi vấn đề dữ liệu.” | Encryption không thay object authz, purpose, logging, key lifecycle và recovery. |
| “Pen test PASS nghĩa là architecture review PASS.” | Pen test có scope/time và không chứng minh mọi requirements/assumptions. |
| “Threat model là sơ đồ STRIDE đã điền đủ.” | Cần attack paths, impact, controls, owners và verification. |
| “Một risk score thấp cho phép bỏ qua critical finding.” | Severity/acceptance criteria và nghĩa vụ bắt buộc vẫn phải được tôn trọng. |
| “ADR được ký là risk đã được xử lý.” | ADR ghi quyết định; controls và evidence vẫn cần triển khai/test. |
| “Một security product có thể thay thế nhiều lớp.” | Phải xác định control objective và common-mode dependencies. |
| “Không có alert nghĩa là không có incident.” | Có thể thiếu log source, detector, retention hoặc health monitoring. |
| “Backup job xanh chứng minh DR sẵn sàng.” | Cần restore test, key dependencies, integrity và RTO/RPO. |
| “Chấp nhận ngoại lệ nghĩa là control đạt.” | Exception là quyết định residual risk có scope, owner và expiry. |

## 34. Checklist cho Security Architecture Review

1. **Scope/context:** hệ thống, release, environment, business purpose và exclusions có rõ?
2. **Assets/data:** data classification, owner, crown jewels, secrets, keys và dependencies được kiểm kê?
3. **Architecture views:** context, components, deployment, network, identity, data flow, operations và supply chain?
4. **Trust boundaries:** public/internal, tenant, cloud account, vendor, CI/CD và admin boundaries được xác định?
5. **Threat model:** actors, attacker capabilities, attack paths, STRIDE/abuse cases và impact?
6. **Requirements:** cụ thể, testable, có owner và trace tới risk/standard?
7. **Identity:** IdP/federation, MFA, service identities, least privilege, PAM/JIT và lifecycle?
8. **Authorization:** object/tenant scope, async jobs, exports, admin, direct grants và cache?
9. **Data/privacy:** purpose, minimization, encryption, retention, deletion, recipients và backups?
10. **Network/API:** ingress/egress, TLS/mTLS, internal calls, webhook, rate limits và failure?
11. **Cloud/container:** account hierarchy, IAM, KMS, Kubernetes RBAC/network, images và runtime?
12. **Supply chain:** source, CI runner, dependencies, artifact provenance/signing và deploy permissions?
13. **Operations:** logs, alerts, incident response, patching, backup/DR, RTO/RPO?
14. **Third parties:** scope, contracts, shared responsibility, downstream processors và evidence?
15. **Verification:** positive/negative/failure tests, environment, data, expected/observed và retest?
16. **Governance:** ADR, owners, findings, exceptions, residual risk và expiry?
17. **Continuous assurance:** drift/change triggers, fitness functions, monitoring và reassessment?

## 35. Bài tập tình huống và gợi ý giải

### Bài tập A — API bảo vệ tốt, worker quyền quá rộng

API kiểm tra user có quyền export hóa đơn trong tenant. Worker dùng service account đọc tất cả tenant và tin tenant_id trong queue payload.

**Gợi ý:** Vẽ data flow và trust boundary API→queue→worker. Threat scenario là tampering/replay và confused deputy. Tạo job record server-side gắn actor/tenant, giới hạn IAM, kiểm tra job scope ở worker và authorization khi download; test forged tenant, retry, cross-tenant và effective permissions.

### Bài tập B — Mọi service trong VPC đều được tin

Một internal service không xác thực caller vì chỉ có thể truy cập từ private subnet. Một workload test bị compromise có thể gọi endpoint admin.

**Gợi ý:** Private network không thay danh tính và quyền. Thêm workload identity, authorization theo action/resource, egress/network restrictions, audit và test caller không được phép; đánh giá blast radius của compromised workload.

### Bài tập C — Cloud scanner báo mọi bucket encrypted

Có 100 bucket đã mã hóa, nhưng export URL có thể truy cập công khai và bucket của vendor chưa được inventory.

**Gợi ý:** Claim at-rest encryption có thể đúng cho population 100 bucket, nhưng claim bảo vệ data flow không đúng. Cần mở scope tới export/download/vendor, test effective access, retention, transport và shared responsibility.

### Bài tập D — Sơ đồ cũ sau khi thêm analytics

Threat model không đề cập warehouse mới nhận event có email và địa chỉ. Đội phát triển cho rằng thay đổi chỉ ảnh hưởng báo cáo.

**Gợi ý:** Đây là data flow/recipient mới, có thể thay đổi classification, purpose, privacy risk và access. Trigger reassessment, field allowlist, consumer IAM, retention, deletion và evidence ở đích.

### Bài tập E — CI runner có quyền production admin

Pipeline build/test dùng cùng credential để deploy và đọc secrets production. Một dependency độc hại có thể chạy script trong build.

**Gợi ý:** Review supply-chain trust boundary và attacker path. Tách build/deploy identities, runner ephemeral, hạn egress, short-lived credentials, artifact signing/provenance và approval; test quyền effective và pipeline compromise scenarios.

### Bài tập F — Namespace được coi là isolation tuyệt đối

Các tenant workloads chạy ở namespace riêng, nhưng dùng chung node, cluster-admin, storage class và network không hạn chế.

**Gợi ý:** Namespace chỉ là một lớp logical boundary. Đánh giá node/cluster/control plane, RBAC, NetworkPolicy, service account, volume access và blast radius; chọn isolation mạnh hơn nếu threat/contract yêu cầu và kiểm chứng.

### Bài tập G — ADR được phê duyệt nhưng chưa test

ADR nói mọi download phải được authorization và link hết hạn sau thời gian ngắn. Release mới triển khai nhưng chưa có test link cũ hoặc link chia sẻ sang tenant khác.

**Gợi ý:** Trạng thái là design reviewed/implementation verification pending. Cần test expired, wrong principal, wrong tenant, CDN/cache và audit trước khi kết luận operating effectiveness.

### Bài tập H — SIEM không có sự kiện nhưng collector đã dừng

Dashboard báo không có failed admin action trong tuần, nhưng log source của Kubernetes audit bị ngừng ingest ba ngày.

**Gợi ý:** Không có sự kiện quan sát không có nghĩa không có hành động. Cần health monitoring, ingestion lag alert, ghi evidence gap và đánh giá lại claim trong thời gian thiếu logs.

### Bài tập I — Backup mã hóa nhưng không phục hồi

Snapshot đã mã hóa, nhưng key version cũ bị retire và DR account không có quyền truy cập theo runbook.

**Gợi ý:** Kiến trúc bảo vệ confidentiality có thể làm thất bại availability/recovery. Cần key dependency inventory, quyền recovery, restore drills và kiểm tra RTO/RPO; quản lý rotation/retention có xét backup.

### Bài tập J — Security score trung bình cao

Scorecard có 9/10 dimensions đạt, nhưng dimension tenant isolation thất bại nghiêm trọng. Nhóm đề xuất trung bình 90% để approve.

**Gợi ý:** Không dùng trung bình che critical failure. Nếu requirement tenant isolation là bắt buộc, review cần Needs redesign/Not approved theo policy cho đến khi remediation và retest đạt hoặc có quyết định hợp lệ theo thẩm quyền.

## Kết luận

**Security Architecture Review** là hoạt động đánh giá có hệ thống xem kiến trúc có bảo vệ đúng tài sản, ranh giới, luồng dữ liệu và mục tiêu bảo mật trước các threat scenarios đã xác định hay không. Review cần kết hợp **context, component, deployment, identity, data flow, cloud, supply chain và operations views**; biến rủi ro thành requirements có thể kiểm tra; đánh giá controls, trade-offs, ADR và failure modes; rồi liên kết với test, evidence, findings, remediation và residual risk. Trong **SECURITY_SECURITY_ASSURANCE**, một kết luận đáng tin phải có **scope, phiên bản, thời kỳ, population và giới hạn rõ**, đồng thời đối chiếu thiết kế với implementation/runtime. Kiến trúc được review không đồng nghĩa production tự động an toàn: controls phải được kiểm chứng và đánh giá lại khi dịch vụ, dữ liệu, identity, vendor hoặc môi trường thay đổi.
