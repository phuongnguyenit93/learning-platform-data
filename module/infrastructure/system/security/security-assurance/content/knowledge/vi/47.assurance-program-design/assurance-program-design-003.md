# Xác định control: Thiết kế danh mục kiểm soát cho chương trình security assurance

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **security control** là gì, vì sao **xác định control** là một bước thiết kế nền tảng của chương trình **security assurance**, và phân biệt nó với việc cài đặt công cụ hoặc chạy audit.
2. Xuất phát từ **security objectives, tài sản, threat scenarios, đánh giá rủi ro và nghĩa vụ áp dụng** để chọn controls có mục đích, tránh sao chép checklist không phù hợp.
3. Phân biệt các control **preventive, detective, corrective/recovery**, control **technical, administrative, physical**, và control **key, supporting, inherited, shared, alternative/compensating**.
4. Xây dựng **control register** có ID, mục tiêu, nguồn yêu cầu, rủi ro, population/applicability, owner, tiêu chí đạt, cách vận hành, evidence, tần suất kiểm tra và trạng thái.
5. Đánh giá tính phù hợp và độ đầy đủ của control design: **coverage**, khả năng bị bypass, phụ thuộc, thứ tự thực thi, nguồn dữ liệu, **fail-safe/fail-closed**, độ độc lập và tính khả thi.
6. Thiết kế **traceability risk → requirement → control → asset/identity/data flow → test → evidence → finding → remediation**.
7. Xây dựng **assurance criteria và test plan** để phân biệt một control **có tài liệu**, **đã triển khai** và **vận hành hiệu lực** trong khoảng thời gian được kiểm tra.
8. Áp dụng cách xác định controls cho dịch vụ SaaS production với IAM, API authorization, data protection, cloud/Kubernetes, logging, detection và disaster recovery.
9. Ưu tiên controls theo mức rủi ro, thiết kế coverage metrics và quản lý control changes, exceptions, residual risk trong một chương trình assurance liên tục.

> **Bối cảnh:** Đây là bài học trong chương **Thiết kế chương trình assurance** của mô-đun **SECURITY_SECURITY_ASSURANCE**. Mục tiêu của mô-đun là xây dựng cách đánh giá **có bằng chứng** rằng hệ thống đáp ứng các mục tiêu bảo mật, từ rủi ro và requirements qua security controls tới kiểm thử, audit và khắc phục. Các mã control, chính sách, ngưỡng, hệ thống và dữ liệu ví dụ dưới đây là **giả định đào tạo**, không phải yêu cầu chung của một khuôn khổ hoặc tổ chức cụ thể.

## 1. Xác định control thực sự là làm gì?

**Security control** là một biện pháp kỹ thuật, quy trình, tổ chức hoặc vật lý được thiết kế để **thay đổi rủi ro bảo mật**: phòng ngừa, ngăn chặn, phát hiện, hạn chế tác động, đáp ứng hoặc hỗ trợ phục hồi khi tình huống không mong muốn xảy ra.

**Xác định control** trong thiết kế chương trình assurance gồm nhiều quyết định:

- **Cái gì cần bảo vệ?** Hệ thống, dữ liệu, khả năng nghiệp vụ, users và môi trường nào nằm trong scope?
- **Cần đạt điều gì?** Confidentiality, integrity, availability, privacy, accountability, recoverability và những nghĩa vụ cụ thể nào?
- **Rủi ro xuất phát từ đâu?** Threat actors, trust boundaries, failure modes và attack paths nào phù hợp?
- **Control nào giải quyết được rủi ro?** Nó tác động lên bước nào của kịch bản và bằng cơ chế gì?
- **Áp dụng ở đâu, cho ai và khi nào?** Population và điều kiện applicability là gì?
- **Ai thiết kế, vận hành, kiểm chứng và chịu rủi ro?** Các trách nhiệm có đủ rõ?
- **Làm sao nhận biết control hoạt động?** Tiêu chí kiểm tra, evidence và các failure/unknown conditions là gì?
- **Khi control không đạt thì sao?** Phát hiện drift, finding, exception, remediation, retest và risk decision nào sẽ diễn ra?

Kết quả **không chỉ là một danh sách tên controls**. Đó là một tập hợp **control definitions có thể triển khai, có thể kiểm tra và có thể truy vết tới mục tiêu bảo mật**.

### 1.1. Ví dụ đầu tiên: “Bật MFA”

Một chương trình ghi:

> Control C-01: Bật MFA.

Câu trên chưa đủ để thiết kế assurance. Các câu hỏi chưa trả lời:

1. MFA áp dụng cho **human users**, privileged identities, contractors hay service principals?
2. MFA bắt buộc trên **đường đăng nhập nào**: IdP, VPN, PAM, cloud console, local admin, break-glass?
3. Có login path bypass MFA qua API, legacy authentication hoặc federated trust không?
4. Đơn vị đo là **identity**, **interactive sign-in**, **session** hay **resource access**?
5. Điều kiện PASS: policy đã bật, effective policy có áp dụng, hay negative login tests thực sự chặn?
6. Nếu IdP mất kết nối thì hệ thống fail-open hay fail-closed?
7. Ai nhận biết MFA policy bị disable sau release và trong bao lâu?
8. Exception nào có thẩm quyền, expiry và compensating control?

Một phiên bản control có thể kiểm tra hơn:

> Các phiên đăng nhập tương tác có đặc quyền vào production trong tập danh tính và đường truy cập đã xác định phải được thực thi MFA theo chính sách IAM-P-03 có hiệu lực. Các đường không áp dụng hoặc ngoại lệ được ghi và phê duyệt riêng; độ bao phủ được xác minh bằng effective privilege inventory, identity policy assignment, sign-in history và negative tests trên những đường trọng yếu.

Định nghĩa này tạo được **population, criteria, evidence và người chịu trách nhiệm**.

### 1.2. Một control không đồng nghĩa một sản phẩm

| Sản phẩm/công cụ | Control objective thực tế | Điều cần kiểm tra |
|---|---|---|
| SIEM | Nhận diện và chuyển sự kiện an ninh trọng yếu tới người xử lý. | Source completeness, detection tests, event-to-case, on-call. |
| EDR | Hạn chế, phát hiện hoặc phản ứng hoạt động host nguy hiểm. | Agent coverage, effective policy, health, behavior tests. |
| IAM platform | Quản lý identity, authentication và authorization theo policy. | Effective permissions, MFA, access lifecycle, bypass paths. |
| Backup software | Duy trì recovery points có thể sử dụng cho mục tiêu phục hồi. | Integrity, decryption, restore, RPO/RTO, dependencies. |
| WAF | Chặn/giảm thiểu một tập kỹ thuật tấn công ở đường HTTP được định nghĩa. | Route coverage, rules, authorized negative tests, bypass, false positives. |
| Kubernetes admission | Chặn cấu hình workload trái yêu cầu khi được tạo/cập nhật. | Policy scope, bypass RBAC, existing resources, runtime drift. |

**Mua hoặc cài công cụ là hoạt động triển khai**, không tự xác định control objective đúng và cũng không tự chứng minh control effective.

## 2. Phân biệt mục tiêu, yêu cầu, control và evidence

Chương trình assurance thường thất bại khi mọi thứ được gọi chung là “control”, khiến không biết phải đo gì.

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Business/security objective** | Điều quan trọng phải duy trì? | Không cho người dùng đọc dữ liệu đơn hàng thuộc tenant khác. |
| **Risk/threat scenario** | Điều gì có thể khiến mục tiêu thất bại? | IDOR/BOLA qua Order API làm lộ thông tin khách hàng. |
| **Security requirement** | Điều kiện có thể đánh giá phải được đáp ứng? | Mỗi request đọc order phải có object-level authorization ở server. |
| **Control definition** | Cơ chế/quy trình nào thực hiện requirement? | API authorization middleware với deny-by-default và tenant-aware policy. |
| **Control implementation** | Đã áp control vào đâu và trạng thái ra sao? | Middleware ở routes X/Y/Z, config version 7. |
| **Assurance criterion** | Theo điều kiện nào kết luận đạt/chưa đạt? | Principal A không được đọc object tenant B qua các endpoints thuộc scope. |
| **Test/assessment** | Kiểm tra điều kiện bằng cách nào? | Authorized cross-tenant negative tests và code/config review. |
| **Evidence** | Điều gì đã được quan sát, từ nguồn nào? | Test IDs, request/response redacted, audit, backend integrity. |
| **Finding** | Điều gì sai khác hoặc chưa được chứng minh? | Route export thiếu object-level check. |
| **Remediation/retest** | Khôi phục yêu cầu và xác minh lại ra sao? | Sửa route, test cả direct API và batch export, reviewer signoff. |

**Control là biện pháp được dự định để đáp ứng yêu cầu; evidence là dữ liệu cho thấy biện pháp ấy thực sự đạt điều kiện được kiểm tra.** Một mục tiêu thường cần nhiều controls; một control có thể giảm nhiều risk scenarios.

## 3. Bắt đầu từ phạm vi và những tài sản cần bảo vệ

Không thể xác định control đúng khi chưa biết **nó phải áp dụng cho những đối tượng nào**.

### 3.1. Lập assurance scope

Một scope có thể bao gồm:

- Business capabilities và **critical services**.
- Applications, APIs, workloads, databases, queues, SaaS integrations.
- Production, staging, disaster recovery, development; khi nào mỗi môi trường thuộc yêu cầu?
- Cloud accounts/subscriptions, Kubernetes clusters, regions, VPCs.
- Human identities, privileged sessions, service accounts, machine/workload identities.
- Data classes, storage, backups, data exports, retention và data flows.
- Third-party services, trust boundaries và customer responsibilities.
- Release versions và kỳ quan sát cần chứng minh.

**Không dùng riêng danh sách của một công cụ control** làm authoritative population. Ví dụ EDR chỉ thấy endpoints đã cài agent, không tự thấy máy chưa cài.

### 3.2. Tối thiểu ba loại inventory

| Inventory | Nội dung cần có | Nguồn cần đối chiếu |
|---|---|---|
| **Assets/services** | Asset ID, owner, criticality, environment, account/region, dependencies. | CMDB + cloud APIs + cluster/service discovery. |
| **Identities/privileges** | Human/service principal IDs, effective permissions, roles, trust paths, lifecycle. | IAM/IdP + application permissions + audit history. |
| **Data flows/obligations** | Data category, source, destination, purpose, region, storage/processor và retention. | Data catalog + architecture + vendor inventory + configuration. |

Những inventory này có thể không hoàn hảo. Đặt **owner, reconcile cadence và unknown status**, không âm thầm loại bỏ đối tượng chưa rõ.

### 3.3. Đánh dấu ranh giới hệ thống

Ví dụ một nền tảng Order Platform:

~~~mermaid
flowchart LR
    U["Customer / admin"] --> IDP["Identity provider"]
    U --> GW["API gateway"]
    IDP --> GW
    GW --> API["Order API / Kubernetes"]
    API --> DB["Order database"]
    API --> BUS["Event queue"]
    BUS --> SAAS["Analytics vendor"]
    API --> LOG["Audit & detection pipeline"]
    DB --> BAK["Backup / recovery"]
    CI["CI/CD + IaC"] --> API
    CI --> GW
~~~

Các ranh giới đáng chú ý:

- Internet → API gateway.
- IdP → application authorization.
- Workload → database và secret manager.
- Organization → analytics vendor.
- CI/CD → production control plane.
- Production → recovery site.
- Audit sources → centralized monitoring.

Control cần được lựa chọn để **bảo vệ từng mục tiêu và đường rủi ro xuyên ranh giới**, không chỉ từng thành phần riêng lẻ.

## 4. Xác định nguồn yêu cầu trước khi chọn control

Một chương trình phải biết **vì sao control tồn tại** và nguồn nào có quyền thay đổi yêu cầu.

### 4.1. Những nguồn phổ biến

| Nguồn | Nội dung | Cách sử dụng |
|---|---|---|
| **Risk assessment / threat model** | Kịch bản, attack path, likelihood, impact, mitigations. | Định hình controls theo rủi ro thực tế. |
| **Security objectives** | Confidentiality, integrity, availability, privacy, resilience. | Xác định điều kiện thành công của kiểm soát. |
| **Law/regulation** | Nghĩa vụ bắt buộc trong jurisdiction/phạm vi áp dụng. | Legal/compliance xác định applicability, phiên bản, cách đáp ứng. |
| **Customer/third-party contracts** | Security commitments, audit, notification, data processing, SLAs. | Map tới requirements có owner và thời hạn. |
| **Internal policy/standards** | Control baseline, secure configuration, access review, retention. | Xác định mandatory controls và ngoại lệ có thể cho phép. |
| **Control frameworks** | Danh mục/control objectives gợi ý, phương pháp tổ chức. | Làm taxonomy, gap review; không copy mà không đánh giá phạm vi. |
| **Architecture/release design** | Các đường truy cập, dependencies, state và failure modes. | Thiết kế controls tương thích hệ thống. |
| **Findings/incidents** | Control failures, bypass, exposure thực tế, lessons learned. | Bổ sung hoặc sửa controls và tests. |

Có thể tham khảo các bộ khung như **ISO/IEC 27001/27002, NIST SP 800-53, CIS Controls** tùy mục đích và phiên bản được tổ chức sử dụng. **Không suy rằng một control được đặt tên giống framework là đủ đạt chứng nhận hoặc luật áp dụng.** Việc diễn giải nghĩa vụ và xác nhận applicability phải do người có thẩm quyền thực hiện.

### 4.2. Tạo requirement register có thể truy vết

Một requirement tốt có:

- Requirement ID, source và phiên bản hiệu lực.
- Chủ thể và điều kiện áp dụng.
- Expected behavior/control objective.
- Scope, environment, business service và kỳ.
- Các trường hợp ngoại lệ hợp lệ.
- Risk scenario/attack path liên quan.
- Owner, reviewer và method kiểm tra.
- Trạng thái áp dụng và ngày cần review lại.

Ví dụ:

> REQ-AUTH-01 — Tất cả routes đọc dữ liệu đơn hàng của tenant được đánh dấu Confidential trong production phải kiểm tra cả user permission và ownership ở server trước khi trả dữ liệu; yêu cầu áp dụng cho API, batch export và luồng ủy quyền từ service accounts theo phạm vi đã ghi.

Đây là nguồn đầu vào để xác định **authorization controls**; chưa phải bằng chứng rằng routes đã thực hiện đúng.

### 4.3. Xử lý yêu cầu chồng chéo

Một control như logging có thể phục vụ đồng thời:

- Điều tra security incidents.
- Phát hiện hành vi cấp quyền admin.
- Truy xuất evidence cho audit.
- Đáp ứng yêu cầu hợp đồng.
- Đảm bảo accountabilities giữa teams.

Không cần tạo năm hệ thống log giống nhau. Có thể dùng **một implementation chung** hỗ trợ nhiều requirements, nhưng **mỗi requirement vẫn cần mapping, acceptance criteria và evidence phù hợp**.

Ngược lại, một requirement “bảo vệ privileged access” có thể đòi **MFA + least privilege + approval + audit/detection**. Chỉ có một control bất kỳ không đủ nếu requirement cần nhiều điều kiện đồng thời.

## 5. Phân loại control theo vai trò trong xử lý rủi ro

Phân loại giúp nhìn ra gap, nhưng **nhãn không thay thế phân tích mechanism**.

### 5.1. Theo thời điểm tác động

| Loại | Mục đích | Ví dụ | Giới hạn |
|---|---|---|---|
| **Preventive** | Ngăn hoặc giảm khả năng hành vi xảy ra. | Server-side authorization, network deny, MFA, admission enforcement. | Có thể bị bypass, áp sai scope hoặc không bao phủ mọi path. |
| **Detective** | Phát hiện sự kiện/control failure và cung cấp tín hiệu. | Audit logging, SIEM detection, integrity alert, source-health. | Không tự ngăn tổn thất; cần response và telemetry đáng tin. |
| **Corrective** | Sửa hậu quả hoặc trạng thái lỗi. | Remediation workflow, credential revoke, reconfiguration. | Có thể chậm; cần kiểm chứng sau xử lý. |
| **Recovery/resilience** | Khôi phục chức năng/dữ liệu sau sự cố. | Immutable backup, restore, failover, DR runbook. | Backup thành công không chứng minh restore được. |
| **Deterrent/directive** | Tạo động lực, chuẩn hành vi, giới hạn sử dụng. | Policy, training, acceptable-use notice. | Không thay enforcement cho attack path cần technical controls. |
| **Compensating/alternative** | Giảm cùng một rủi ro khi control chuẩn chưa thể thực hiện. | PAM proxy MFA khi app legacy chưa hỗ trợ MFA gốc. | Cần chứng minh tương đương mục tiêu và đúng scope. |

Một control có thể có nhiều chức năng. Ví dụ EDR kết hợp prevention, detection và response; phải chia nhỏ claim/test theo **từng chức năng** khi cần.

### 5.2. Theo phương thức thực hiện

- **Technical:** IAM policies, encryption, network controls, logging, endpoint protection.
- **Administrative/organizational:** approval, review, risk governance, training, supplier oversight.
- **Physical/environmental:** facility access, secure hardware disposal, power/cooling redundancy.
- **Human-in-the-loop:** privileged change review, manual incident triage, exception decision.

Không giả định technical control luôn mạnh hơn administrative control. Chúng thường phụ thuộc nhau: technical enforcement cần policy đúng; manual review cần source dữ liệu đầy đủ.

### 5.3. Key control và supporting control

**Key control** là control có vai trò đặc biệt quan trọng trong giảm thiểu risk scenario hoặc đáp ứng requirement theo phương pháp phân loại được tổ chức phê duyệt.

**Supporting control** giúp key control hoạt động đáng tin.

Ví dụ:

- Key control: server-side authorization chặn truy cập order ngoài tenant.
- Supporting controls: authoritative identity data, role mapping, code review, audit trail, automated regression tests, CI/CD enforcement.

Nếu identity service cấp sai tenant claims, key control có thể fail dù code middleware không đổi. Vì vậy một chương trình không nên chỉ test control chính mà bỏ **critical dependencies**.

### 5.4. Common controls, inherited controls và shared responsibility

Một số controls được cung cấp tập trung:

- Enterprise IdP/MFA.
- Centralized logging/SIEM.
- Cloud organization guardrails.
- Enterprise KMS và backup vault.
- Managed service provider controls.

Team application có thể **kế thừa** một phần assurance từ common control; nhưng vẫn phải xác định:

1. Control trung tâm **bao phủ tài nguyên nào**?
2. Team ứng dụng phải cấu hình gì để sử dụng đúng?
3. Evidence trung tâm có scope, version và kỳ phù hợp?
4. Customer-side controls và các exclusions là gì?
5. Khi common control lỗi, ai phát hiện và thông báo cho consumers?

**Có control tập trung không đồng nghĩa mọi ứng dụng tự động được bảo vệ.** Ví dụ enterprise IdP có MFA nhưng một legacy endpoint vẫn cho local admin login trực tiếp.

## 6. Quy trình xác định control từ rủi ro đến khả năng kiểm chứng

Một quy trình thực hành gồm mười bước, có thể lặp lại sau release hoặc khi risk thay đổi:

1. **Chọn security objective và business scope.**
2. **Chốt assets, identities, data flows và trust boundaries** liên quan.
3. **Phân tích threat scenarios, attack paths và failure modes**.
4. **Xác định requirements và nghĩa vụ áp dụng**, gồm nguồn/phiên bản.
5. **Đánh giá các controls hiện có**, mức triển khai và các control gaps.
6. **Lựa chọn hoặc thiết kế controls** gắn với từng bước rủi ro quan trọng.
7. **Định nghĩa control objective, mechanism, owner, population và acceptance criteria**.
8. **Thiết kế test/evidence và monitoring**, bao gồm negative tests và những trường hợp không quan sát được.
9. **Phân loại criticality/priority và risk treatment**, lập kế hoạch triển khai.
10. **Review, phê duyệt, version và duy trì** khi có thay đổi, incident hoặc findings.

~~~mermaid
flowchart TD
    OBJ["Security objective & business scope"] --> INV["Assets / identities / data flows"]
    INV --> TH["Threat scenarios / risk analysis"]
    TH --> REQ["Requirements & obligations"]
    REQ --> MAP["Existing control mapping & gap review"]
    MAP --> DESIGN["Control selection / design"]
    DESIGN --> OWN["Owner + applicability + criteria"]
    OWN --> TEST["Tests + telemetry + evidence contract"]
    TEST --> DEC{"Design assurance review"}
    DEC -->|Phù hợp| REG["Versioned control register"]
    DEC -->|Thiếu coverage| DESIGN
    REG --> IMPL["Implement / operate / monitor"]
    IMPL --> FIND["Assess / findings / exceptions / retest"]
    FIND --> TH
~~~

Quy trình không yêu cầu viết lại toàn bộ controls từ đầu mỗi lần. Nó tạo một **control lifecycle** để những điều đã được quyết định vẫn có ý nghĩa khi scope và threat model thay đổi.

## 7. Xác định một control đầy đủ: control definition contract

Một control tốt nên đủ cụ thể để một người khác có thể trả lời:

> Điều gì phải xảy ra, ở đâu, cho ai, vào lúc nào, do ai chịu trách nhiệm, và bằng chứng nào chứng minh control đạt?

### 7.1. Các trường tối thiểu

| Thuộc tính | Câu hỏi thiết kế | Ví dụ |
|---|---|---|
| **Control ID / version** | Control có danh tính ổn định và lịch sử thay đổi? | CTRL-IAM-007 v2.1. |
| **Control name** | Tên mô tả hành vi cần đảm bảo? | Privileged authentication enforcement. |
| **Control objective** | Nó giảm rủi ro/mục tiêu nào? | Giảm nguy cơ lạm dụng thông tin đăng nhập admin. |
| **Requirement sources** | Dựa trên policy/obligation nào? | IAM-P-03 v4, RISK-IAM-12. |
| **Mechanism / activity** | Cách ngăn/detect/respond? | Enforce MFA qua IdP/PAM, deny direct legacy path. |
| **Applicability** | Loại assets/identities nào bắt buộc? | Human privileged interactive access tới production. |
| **Population source** | Lấy mẫu số từ đâu? | IAM effective privilege inventory đối chiếu IdP. |
| **Owner / operator** | Ai chịu trách nhiệm thực thi và duy trì? | Identity platform team. |
| **Risk owner** | Ai chịu rủi ro tồn dư nếu control fail? | Business service risk owner. |
| **Dependencies** | Control dựa vào gì? | IdP availability, MFA policy, accurate roles, audit. |
| **Frequency / trigger** | Khi nào chạy/kiểm chứng? | Mỗi sign-in, privilege grant, scheduled review. |
| **Criterion** | Điều kiện rõ để PASS/FAIL? | Unauthorized privileged sign-in không thể hoàn tất. |
| **Test method** | Examine, interview, test thế nào? | Effective assignment, negative test, log history. |
| **Evidence contract** | Source, timestamp, scope và freshness? | Policy history, sign-in audit, canary ID, source health. |
| **Exception / fallback** | Khi control không hỗ trợ, xử lý sao? | Time-bound exception đúng thẩm quyền và controls bù trừ. |
| **Monitoring / failure** | Ai biết khi control mất hiệu lực? | IdP policy drift alert, health, IAM grant reconciliation. |
| **Assessment status** | Đạt/chưa đạt/chưa đủ evidence ở phạm vi nào? | VERIFIED, PARTIAL, FAIL, INCONCLUSIVE. |
| **Review trigger** | Khi nào phải đánh giá lại? | New cloud account, IdP change, new admin path, incident. |

### 7.2. Mẫu YAML cho control register

~~~yaml
control:
  id: CTRL-IAM-007
  version: "2.1"
  name: "Privileged interactive authentication enforcement"
  family: "identity-and-access"
  type: ["preventive", "detective-supporting"]
  objective: >
    Reduce unauthorized privileged interactive access
    in the defined production population.
  sources:
    requirements:
      - "REQ-IAM-003 v4"
    risks:
      - "RISK-PRIV-012"
    threat_scenarios:
      - "ST-CREDENTIAL-ABUSE"
  applicability:
    scope: "production"
    unit_type: "human-privileged-identity-path"
    population_source: "effective-iam-and-IdP-inventory-v3"
    exclusions: "only approved and documented non-applicability"
  mechanism:
    enforcement: "IdP/PAM MFA and no unmanaged direct admin login"
    monitoring: "privileged sign-in and policy-drift alerts"
  owner:
    control_owner: "identity-platform"
    risk_owner: "business-service-risk-owner"
    assurance_reviewer: "security-assurance"
  dependencies:
    - "IdP policy integrity and availability"
    - "accurate effective privilege inventory"
    - "sign-in audit source health"
  test_contract:
    - id: "IAM-T01"
      method: "examine"
      objective: "Reconcile privileged population and policy assignments"
    - id: "IAM-T02"
      method: "test"
      objective: "Unauthorized path cannot complete privileged login"
    - id: "IAM-T03"
      method: "test"
      objective: "Policy drift and bypass attempts produce audit/alerts"
  evidence:
    required_sources:
      - "IAM effective privilege data"
      - "IdP policy and version history"
      - "sign-in audit and test results"
      - "source-health and exception register"
    freshness_rule: "defined-by-assurance-policy"
  assessment:
    period: "2026-11"
    status: "NOT_ASSESSED"
    known_limitations: []
  lifecycle:
    triggers:
      - "privilege grant or new account"
      - "IdP/PAM policy change"
      - "application admin path change"
      - "control failure or incident"
~~~

Đây là **schema học tập**, không phải định dạng chuẩn của một framework. Ngày/period và criteria thực tế cần được xác nhận trước khi dùng. Không lưu passwords, tokens hoặc thông tin nhạy cảm vào control register.

### 7.3. Tiêu chí để một control “được xác định” có chất lượng

- **Specific:** hành vi và đối tượng rõ.
- **Risk-relevant:** giải quyết đúng scenario, không chỉ có tên đẹp.
- **Applicable:** population và điều kiện rõ.
- **Implementable:** có cơ chế triển khai và operator.
- **Testable:** có phương pháp để chứng minh hoặc phản bác.
- **Observable:** biết khi control hỏng hoặc mất evidence.
- **Owned:** có accountability và decision authority.
- **Maintainable:** có versioning, change triggers, monitoring.
- **Bounded:** công bố assumptions và limitations.
- **Consistent:** không mâu thuẫn với nghĩa vụ, design khác hoặc control dependencies.

Một control quá mơ hồ nên được **làm rõ hoặc chia thành các subcontrols** thay vì chỉ thêm nhiều dòng evidence vào trường “description”.

## 8. Tính đầy đủ của control design: không bỏ sót đường rủi ro

Chọn control bằng checklist có thể để lại một **attack path không được kiểm soát** dù tổng số controls rất nhiều.

### 8.1. Chuyển attack path thành các điều kiện

Ví dụ rủi ro **truy cập trái phép dữ liệu khách hàng** qua Order API:

1. Attacker chiếm tài khoản hoặc lấy token.
2. API chấp nhận token có scope không phù hợp.
3. Route truy cập order không kiểm tra ownership.
4. Service principal đọc trực tiếp database nhờ quyền quá rộng.
5. Data export gửi thông tin tới SaaS ngoài mục đích.
6. Logging/detection không quan sát được hành vi.
7. Khả năng thu hồi quyền chậm làm kéo dài tác động.

Control set cần xem:

- Identity verification và authentication.
- Effective authorization và tenant isolation.
- Least privilege cho service principals/database.
- Data minimization, egress và third-party integration controls.
- Audit logging, detection, alert routing.
- Credential revoke, incident response, containment.
- Regression tests và kiểm tra drift.

**MFA không tự ngăn BOLA**, và encryption at rest không ngăn người có API quyền đọc vượt scope.

### 8.2. Coverage matrix

| Attack step / failure mode | Prevention | Detection | Response/recovery | Evidence/limitation |
|---|---|---|---|---|
| Credential abuse. | MFA, session hardening, conditional access. | Risk sign-in signals, privileged sign-in review. | Revoke tokens, isolate principal. | Effective policy + negative tests; service principal khác human. |
| JWT audience bypass. | Strict signature/issuer/audience checks. | Auth anomaly/audit. | Disable route, rotate keys when needed. | Invalid-token tests trên gateway và endpoints. |
| Cross-tenant read. | Object-level server-side authorization. | Cross-tenant test/detection use case. | Block, investigate access. | Positive/negative tests; route inventory completeness. |
| DB privilege escalation. | Least privilege, isolated service identities. | DB/IAM audit, privilege-change alert. | Revoke/rotate, incident triage. | Effective grants; check inherited roles. |
| Excess data export. | Schema allowlist, egress restrictions. | Data-flow audit, unusual export signals. | Stop integration, assess exposed data. | Synthetic payload, DLP if applicable. |
| Telemetry blind spot. | Source onboarding and protected logging config. | Health canary, dropped event alerts. | Fix collector, assess historical gap. | Source register + event-to-case tests. |

Bảng không tự chứng minh coverage đầy đủ. Phải có subclaim rằng **threat model và population đủ phù hợp** với quyết định assurance đang đưa ra.

### 8.3. Định nghĩa key control theo điều kiện cần

Nếu mục tiêu là “mọi hành vi truy cập trái phép bị từ chối”, control authorization là điều kiện **bắt buộc**. Dù logging hoạt động tốt, nó không thay thế prevention nếu requirement quy định phải chặn.

Ngược lại, một mục tiêu detection cần **source logging + parser + rule + case routing**. Chỉ có rule không chứng minh capability detect end-to-end.

**Cần xác định quan hệ AND/OR giữa các controls theo mục tiêu**, không cộng số lượng và tuyên bố đạt khi có nhiều cái tên.

## 9. Chất lượng control mechanism: từ thiết kế đến hoạt động thực

### 9.1. Các câu hỏi về security engineering

- **Bypass resistance:** có đường vào không đi qua control không?
- **Fail behavior:** khi IdP, KMS, database, network hoặc policy engine lỗi thì fail-open hay fail-closed? Hậu quả kinh doanh ra sao?
- **Scope fidelity:** selector, role, route, resource và tenant có bao đúng population?
- **Trust boundary:** enforcement ở server/authorization layer hay chỉ UI?
- **Least privilege:** control cần quyền gì, có tạo privileged blast radius mới?
- **Independent verification:** có nguồn khác xác nhận effective state và behavior?
- **Alert reliability:** khi control hỏng, ai nhận tín hiệu và trong bao lâu?
- **Recovery:** có fallback, rollback, restore và incident coordination?
- **Performance/availability:** control có gây outage, latency, queue backlog hoặc sự cố cascading?
- **Change resistance:** IaC/GitOps/admission và drift monitoring có phát hiện sửa ngoài luồng?

Đánh giá control phải cân nhắc **khả năng vận hành**, không chỉ khả năng ngăn một test case.

### 9.2. Control dependencies và common-mode failure

Một số controls được thiết kế tưởng độc lập nhưng thực tế cùng phụ thuộc:

- IAM access policy và audit dùng chung một IdP.
- Detection và source-health alert đều dựa vào cùng một SIEM ingestion path.
- Production backup và DR site dùng chung KMS key/region.
- Firewall enforcement và monitoring cùng cấp quyền bởi một admin role.
- Runtime policy và CI/CD admission cùng dùng một registry metadata không có integrity validation.

Nếu một dependency thất bại có thể làm **cả control và cơ chế chứng minh control** cùng mất tác dụng, đó là **common-mode failure** đáng ghi thành risk scenario.

### 9.3. Nguyên tắc defense in depth có điều kiện

Nhiều lớp control là hữu ích khi chúng tạo **những cơ chế giảm rủi ro khác nhau hoặc giảm phụ thuộc**. Ví dụ:

- Authorization ở API.
- Least privilege ở data store.
- Egress/data minimization.
- Audit/detection và response.

Nhưng ba dashboards cùng đọc một index lỗi **không tạo ba lớp assurance độc lập**. Phải xác định **common dependencies và kiểu thất bại**.

## 10. Quyền sở hữu: design owner, operator, risk owner, assessor

Một control không có owner sẽ dễ thành một checkbox tồn tại trên giấy.

| Vai trò | Trách nhiệm trong control lifecycle | Giới hạn |
|---|---|---|
| **Control design owner** | Định nghĩa mechanism, criteria, risk mapping và assumptions. | Không tự tuyên bố effectiveness khi chưa test. |
| **Control operator** | Triển khai, vận hành, monitoring, xử lý drift và evidence source. | Không tự bỏ criterion vì triển khai khó. |
| **Asset/service owner** | Xác định population, dependencies, change plan và business impact. | Không tự miễn ràng buộc bên ngoài. |
| **Risk owner** | Quyết định cách xử lý residual risk trong thẩm quyền. | Risk acceptance không biến control FAIL thành PASS. |
| **Security assurance assessor** | Xem criteria, kiểm tra evidence, nhận định coverage/effectiveness. | Không suy từ một snapshot sang toàn kỳ khi không đủ history. |
| **Compliance/legal specialist** | Xác định applicability của nghĩa vụ ngoài nội bộ khi cần. | Không thay thế test kỹ thuật cho mechanism. |
| **Independent auditor/reviewer** | Chất vấn độ đầy đủ của scope, lập luận và evidence. | Không phê duyệt rủi ro ngoài vai trò đã phân công. |

Có thể một người kiêm nhiều vai ở tổ chức nhỏ, nhưng cần **separation of duties** hoặc peer/independent review phù hợp rủi ro, nhất là với privileged controls và critical evidence.

### 10.1. RACI cần đủ cụ thể

Ví dụ CTRL-LOG-002:

- **Accountable:** service risk owner hoặc chức danh được chương trình xác định.
- **Responsible:** platform logging team.
- **Consulted:** SOC/detection, cloud/IAM, compliance khi có nghĩa vụ.
- **Informed:** application owners, audit/GRC và on-call.
- **Assessor:** security assurance hoặc reviewer theo quy trình.

RACI phải quy định **ai sửa lỗi và ai xác nhận sửa thành công**, không chỉ ai nhận email khi audit đến.

## 11. Xác định applicability và population cho từng control

Control chỉ có ý nghĩa khi biết nó phải được áp dụng **ở đâu**.

### 11.1. Ma trận loại đối tượng – control

| Đối tượng | Controls thường cần xem | Sai lầm dễ gặp |
|---|---|---|
| Human privileged login. | MFA, access approval, session audit, lifecycle. | Xem MFA ở IdP nhưng bỏ local/direct login. |
| Non-interactive workload identity. | Short-lived identity, least privilege, token/secret lifecycle, audit. | Ép cùng MFA flow với human rồi tự gắn N/A toàn bộ identity security. |
| API xử lý dữ liệu Confidential. | Authn/authz, input validation, encryption, data minimization, audit. | Chỉ có TLS rồi coi data access an toàn. |
| Cloud control plane. | Organization guardrails, privileged access, config audit, detection. | Chỉ xem một account/region. |
| Kubernetes workloads. | Admission, RBAC, network segmentation, image provenance, runtime. | Admission PASS nhưng existing pods/drift chưa được kiểm tra. |
| Database và backup. | Encryption/key permissions, access, integrity, restore, retention. | Backup job SUCCESS được tính DR PASS. |
| Third-party data flows. | Vendor scope, data transfer conditions, token scopes, monitoring/offboarding. | Vendor certificate được dùng thay customer-side tests. |

### 11.2. Trạng thái applicability

- **APPLICABLE:** control yêu cầu cho đối tượng theo source có hiệu lực.
- **NOT_APPLICABLE:** điều kiện chứng minh yêu cầu không áp dụng đã được rà soát/phê duyệt theo policy.
- **UNKNOWN_APPLICABILITY:** thiếu inventory, data classification hoặc nghĩa vụ, cần review.
- **ALTERNATIVE_CONTROL_PATH:** requirement áp dụng nhưng có phương án tương đương đã được phê duyệt và phải được chứng minh.
- **EXCEPTION:** requirement áp dụng nhưng chưa đáp ứng, tồn tại quyết định risk/time-bound riêng.

**Không hỗ trợ về công nghệ không tự biến một yêu cầu applicable thành N/A.** Trạng thái unknown không được xóa khỏi denominator chỉ vì thiếu dữ liệu.

### 11.3. Đơn vị đánh giá

Tùy control:

- Asset.
- Identity.
- Identity–access path.
- Asset–control pair.
- Data flow/trust boundary.
- Security requirement.
- Threat scenario.
- Source event stream.
- Business service/recovery scenario.
- Time interval.

Một chương trình cần xác định đúng **unit of analysis**, nếu không sẽ xuất hiện những tỷ lệ khó hiểu như “đã triển khai 100 controls” mà không biết 100 controls bao phủ những hệ thống nào.

## 12. Control register và traceability graph

### 12.1. Các quan hệ cần lưu

~~~mermaid
flowchart LR
    O["Security objective"] --> R["Risk / threat scenario"]
    R --> REQ["Requirement / policy / obligation"]
    REQ --> C["Control definition"]
    C --> APP["Applicable units / assets"]
    C --> OWN["Control owner & dependencies"]
    APP --> TEST["Assessment/test"]
    TEST --> EV["Evidence & provenance"]
    EV --> VERDICT["Assessment verdict"]
    VERDICT --> FIND["Finding / exception"]
    FIND --> REM["Remediation & retest"]
    REM --> TEST
~~~

Một control có thể được dùng cho nhiều requirements; nhiều controls có thể cùng giải quyết một requirement. Vì vậy **traceability là đồ thị nhiều-nhiều**, không nên ép mọi thứ thành một cột duy nhất.

### 12.2. Control register dạng bảng

| ID | Control objective | Applicable population | Owner | Criterion | Evidence |
|---|---|---|---|---|---|
| CTRL-IAM-01 | Giới hạn access đặc quyền. | Human privileged access paths ở production. | Identity team. | Login ngoài policy bị từ chối, mọi exception có thẩm quyền. | IAM effective grants, MFA tests, sign-in audit. |
| CTRL-API-02 | Ngăn truy cập cross-tenant. | Order API routes và batch exports xử lý tenant objects. | API team. | Unauthorized principal không thể đọc/sửa object ngoài tenant. | Test matrix, runtime audit, data-state checks. |
| CTRL-DATA-03 | Hạn chế dữ liệu gửi vendor. | Purchase event flows tới analytics. | Data/integration owner. | Only allowlisted fields và destinations. | Schema tests, egress config, vendor scope. |
| CTRL-LOG-04 | Quan sát security events quan trọng. | Critical log sources theo inventory. | Logging + SOC. | Raw event đến parser/rule/case theo defined window. | Canaries, health history, rule tests. |
| CTRL-DR-05 | Khôi phục dịch vụ Critical. | Order service dependencies và recovery site. | DR owner. | Restore scenario đạt RTO/RPO/integrity criteria. | DR exercise, recovery timeline và data validation. |

Bảng trên mới là **control design register**. Status effectiveness phải được lấy từ assessments/evidence **không điền mặc định PASS**.

### 12.3. Kiểm tra tính đầy đủ

Một control register nên kiểm tra:

1. Mọi high-priority risk scenario có control mapping hoặc documented treatment.
2. Mọi mandatory requirement có chủ sở hữu, applicability và controls đủ.
3. Mỗi key control có criterion và evidence method.
4. Các control dependencies trọng yếu có người quản lý và test.
5. Có control nào không liên kết risk/requirement rõ ràng? Kiểm tra để tránh kiểm soát vô mục đích.
6. Có requirement nào chỉ mapping control detective khi bắt buộc prevention?
7. Có tài sản Critical nào chưa có owner hoặc chưa được phân loại?
8. Có control nào có nguồn evidence hỏng khiến assessment không thể thực hiện?
9. Có conflicts giữa controls như logging retention và data minimization?
10. Có claims “mọi assets” khi inventory completeness chưa được chứng minh?

**Completeness không chỉ đếm số hàng**. Nó đánh giá mức bao phủ **đúng rủi ro, đúng điều kiện và đúng population**.

## 13. Xây dựng assurance criteria trước khi triển khai

Một control có thể được xác định chính xác hơn khi người thiết kế thử viết **cách có thể bác bỏ claim**.

### 13.1. Từ câu mơ hồ tới tiêu chí có thể test

| Phát biểu mơ hồ | Tiêu chí cụ thể hơn | Evidence phù hợp |
|---|---|---|
| “Có bảo vệ API.” | Mọi route thuộc inventory Confidential áp object-level authorization; unauthorized cross-tenant tests bị deny. | Route inventory, identity claims, negative test, backend outcome. |
| “Bật logging.” | Source Critical sinh/đưa event types yêu cầu tới nơi xử lý đúng schema; mất source có health alert. | Raw/normalized event, canary, source health, parser version. |
| “Có backup.” | Recovery point trong scope có thể restore, đạt consistency và các objectives theo scenario. | Restore exercise, RPO/RTO, KMS/network dependencies. |
| “Có mã hóa dữ liệu.” | Dữ liệu được chỉ định được bảo vệ trong trạng thái yêu cầu với keys, identities và cấu hình đúng policy. | Key policy, storage/service configs, effective access test. |
| “Đánh giá vendor.” | Rủi ro/integration và scope báo cáo vendor được review khi service/data flow thay đổi; customer controls được test. | Contract register, vendor report scope, integration tests. |
| “Đã kiểm soát privileged access.” | Effective grants trong kỳ được đối chiếu approvals, direct bypass paths được đánh giá, exceptions còn hiệu lực. | IAM audit, approvals, negative test, exception records. |

Cần cụ thể hóa những từ như **“mọi”, “đủ”, “kịp thời”, “tối thiểu”, “được phép”** bằng source, unit, scope và điều kiện rõ.

### 13.2. Three-way test design

Một control tốt cần test không chỉ khi nó hoạt động:

1. **Positive behavior:** hành vi hợp lệ hoạt động như được phép.
2. **Negative behavior:** hành vi bị cấm được từ chối/phát hiện.
3. **Failure behavior:** khi dependency/control hỏng, hệ thống xử lý theo chính sách và có alert/fallback.

Ví dụ một authentication control:

- Token đúng issuer/audience/expiry và role được chấp thuận → pass.
- Token sai issuer/audience/expiry hoặc thiếu quyền → deny, không side effect.
- Kết nối tới IdP/JWKS bị lỗi → behavior theo policy đã phê duyệt (thường cần tránh fail-open cho hành vi nhạy cảm), có telemetry và runbook.

Không tồn tại một **fail-closed rule phổ quát** cho mọi chức năng: phải xem an toàn, availability và khả năng khôi phục. Nhưng nếu control cho phép bypass khi dependency hỏng, đây là risk assumption cần đánh giá, không được che.

## 14. Evidence contract cho control

**Evidence contract** mô tả chính xác dữ liệu nào được dùng để kết luận control đáp ứng criterion.

### 14.1. Các thuộc tính cần xác định

| Thuộc tính | Câu hỏi |
|---|---|
| **Claim/criterion ID** | Evidence chứng minh điều gì và không chứng minh điều gì? |
| **Source/provenance** | Nguồn nào, query/tool/version, thu bởi ai? |
| **Population** | Nguồn có bao phủ toàn bộ applicable units hay một sample? |
| **Time window** | Point-in-time hay operating effectiveness trong kỳ? |
| **Quality** | Completeness, integrity, timestamp accuracy, errors, duplicates? |
| **Behavior** | Positive, negative, boundary, failure tests nào được chạy? |
| **Independence** | Nguồn khác hoặc reviewer có thể xác minh không? |
| **Retention/access** | Evidence có đủ lâu, đúng phân quyền, không rò secrets/PII? |
| **Reproducibility** | Người khác có thể kiểm tra lại expected và actual? |
| **Limitation** | Những đối tượng, scenarios hoặc thời gian nào chưa được test? |

### 14.2. Ba mức hiệu lực cần tách

- **Design effectiveness:** control được thiết kế hợp lý cho risk/requirement trong scope.
- **Implementation effectiveness:** control được đưa vào những đối tượng áp dụng và cấu hình đúng.
- **Operating effectiveness:** control thực thi đúng trong những điều kiện và khoảng thời gian được đánh giá.

Ví dụ **PAM approval policy** được viết tốt chứng minh design, effective assignment xác minh implementation, còn raw privilege-change events được nối với approval và tests trong kỳ hỗ trợ operating effectiveness.

### 14.3. Khung assessment Examine–Interview–Test

Một bộ phương pháp hữu ích:

- **Examine:** xem policy, architecture, config, population, logs và evidence metadata.
- **Interview:** hỏi control operator, risk owner, on-call về cách xử lý exceptions, failure và changes.
- **Test:** thực thi kiểm tra được ủy quyền, positive/negative/failure và xác minh kết quả.

Không cần dùng cả ba phương pháp cho mọi criterion. Nhưng phải chọn phương pháp **đủ mạnh so với claim**, nhất là control tự động xử lý threat kỹ thuật: chỉ phỏng vấn “đã bật rule” hiếm khi đủ.

### 14.4. Chất lượng chứng cứ không được suy từ số lượng file

- Năm ảnh chụp cùng một dashboard không có nghĩa năm nguồn độc lập.
- Hash đúng không chứng minh log population đầy đủ.
- Report nhà cung cấp độc lập đáng tin về **scope đã kiểm tra**, không tự mở rộng cho feature mới.
- Test pass trong staging không tự chứng minh runtime production.
- Một snapshot ngày audit không chứng minh control hoạt động trong cả quý.
- Không thấy alert không chứng minh không có attack nếu source health thiếu.

## 15. Các trạng thái và cách kết luận control

Chương trình nên công khai cả **control lifecycle** và **assessment verdict**.

### 15.1. Lifecycle status

- **PROPOSED:** mới xác định, chưa thiết kế đầy đủ/phê duyệt.
- **DESIGNED:** objective, mechanism, owner, scope, criteria đã thống nhất.
- **IMPLEMENTING:** đang triển khai; có thể chưa bao phủ population.
- **OPERATING:** control đang chạy theo owner nhưng phải đánh giá effectiveness.
- **DEPRECATED/REPLACED:** có phương án thay thế và kế hoạch chuyển giao.
- **RETIRED:** không còn áp dụng theo quyết định đã được chứng minh.

### 15.2. Assessment verdict

| Verdict | Ý nghĩa | Có thể đưa vào numerator “verified coverage”? |
|---|---|---|
| **SUPPORTED / VERIFIED** | Criterion có evidence đủ, đúng phạm vi/kỳ, không có blocker trọng yếu chưa xử lý. | Có, theo measurement contract. |
| **PARTIALLY_SUPPORTED** | Chỉ một phần scope/điều kiện được xác minh. | Không nếu metric đòi full verified. |
| **FAILED / CONTRADICTED** | Có evidence cho thấy criterion không đạt. | Không. |
| **INCONCLUSIVE** | Không đủ evidence, nguồn hoặc population để kết luận. | Không. |
| **NOT_ASSESSED** | Control applicable nhưng chưa được đánh giá. | Không. |
| **NOT_APPLICABLE** | Có căn cứ rằng requirement không áp dụng. | Không nằm trong applicable denominator khi hợp lệ. |

**ACTIVE_APPROVED_EXCEPTION** nên là thuộc tính quản trị riêng về một gap **đang được chấp nhận có điều kiện**, không phải tình trạng control đã chứng minh đạt.

### 15.3. Ví dụ không nên gộp status

Một admission policy của Kubernetes đã triển khai trên mọi namespace mới; tuy nhiên một số workloads cũ có privileged settings từ trước và chưa được xử lý.

- Control deployment có thể đạt cho **creation/admission paths mới**.
- Control security objective “không có workloads privileged ngoài scope” chưa đạt cho **runtime population**.
- Nếu chưa có inventory đầy đủ, phần operating coverage có thể **INCONCLUSIVE**.

Phải báo các claims khác nhau thay vì một ô “Kubernetes security = green”.

## 16. Prioritization: không thể kiểm tra mọi control với cùng độ sâu

Xác định control cũng là quyết định **đầu tư assurance** vào những nơi rủi ro đáng kể.

### 16.1. Yếu tố ưu tiên

- Mức độ trọng yếu và dữ liệu nhạy cảm.
- Threat scenario, khả năng bị exploit, hậu quả kinh doanh.
- Exposure trực tiếp/gián tiếp, quyền đặc biệt.
- Obligation bắt buộc và độ khó khắc phục khi vi phạm.
- Tốc độ thay đổi/release và nguy cơ drift.
- Phụ thuộc chung hoặc single point of failure.
- Khả năng phát hiện failure và thời gian phản ứng.
- Phạm vi bao phủ của control (blast radius).
- Chất lượng evidence hiện tại và trạng thái unknown.
- Lịch sử incidents, findings và overdue remediation.

Một chương trình có thể gắn **Critical/High/Medium/Low** theo policy. **Không có scoring universal** phù hợp mọi hệ thống; ghi phương pháp và thẩm quyền.

### 16.2. Key controls thường cần assurance sâu hơn

Ví dụ một API quan trọng xử lý PII:

| Control | Ưu tiên giả định | Lý do | Kiểm chứng |
|---|---|---|---|
| Server-side object authorization. | Critical. | Ngăn BOLA/cross-tenant data exposure. | Negative tests trên route/role/tenant matrix. |
| IAM least privilege. | High. | Hạn chế blast radius của service principal. | Effective grants, out-of-scope deny tests. |
| Audit source + detection. | High. | Quan sát misuse và incidents. | Source health, event-to-alert/case. |
| Encryption at rest/key protection. | High. | Bảo vệ dữ liệu và key misuse. | Effective policies, decrypt/deny tests. |
| Restore/recovery. | High. | Giữ availability/integrity sau sự cố. | End-to-end restore exercise. |
| Security awareness cho nhóm vận hành. | Supporting theo scenario. | Giảm lỗi thao tác xã hội/quy trình. | Training evidence + behavior/process review. |

Nếu legal/contract yêu cầu một control cụ thể, **mức ưu tiên nội bộ không tự cho phép bỏ yêu cầu**.

### 16.3. Không lấy cost/coverage thay thế risk analysis

Một control rẻ và dễ triển khai trên hàng nghìn endpoints có thể tăng coverage percentage nhanh, nhưng một control Critical chưa đạt ở payment gateway có thể quan trọng hơn.

Phải báo **critical uncovered items** và risk consequences riêng; không cho tổng số control pass bù điều kiện bắt buộc fail.

## 17. Risk treatment, alternative controls và exception

Có nhiều cách xử lý rủi ro: giảm rủi ro bằng controls, tránh hoạt động, chuyển/giao một phần theo cơ chế phù hợp hoặc chấp nhận residual risk trong quyền hạn.

### 17.1. Khi control chuẩn không khả thi

Ví dụ server legacy không hỗ trợ EDR. Câu hỏi cần hỏi:

1. Requirement thực sự áp dụng cho server này không?
2. Threat scenario EDR cần giảm là gì?
3. Có giải pháp khác như network isolation, allowlisting, host audit, runtime monitoring hoặc nâng cấp OS không?
4. Controls thay thế có đạt **cùng mục tiêu** và coverage phù hợp không?
5. Effective configuration và tests đã chứng minh tác dụng chưa?
6. Residual risk, assumptions, monitoring và deadline là gì?
7. Risk owner có thẩm quyền ký exception không?
8. Có nghĩa vụ ngoài nội bộ không thể miễn bằng approval nội bộ?

**Compensating control được đề xuất chưa phải verified.** Cần tiêu chí và evidence riêng.

### 17.2. Ví dụ alternative control path

| Standard control | Gap | Alternative mechanism | Test cần có | Giới hạn |
|---|---|---|---|---|
| MFA trên portal legacy. | App không hỗ trợ MFA. | Access proxy/SSO/PAM có MFA, chặn direct access. | Positive/negative login và bypass tests. | Local admin routes hoặc break-glass còn cần kiểm chứng. |
| EDR trên OS cũ. | Agent không tương thích. | Isolation, allowlisting, host audit và SOC detection. | Effective network deny, canary/detection health. | Thiếu một số prevention trên host. |
| Cloud-native log source. | Một API audit không có sẵn. | Alternative event source + correlation và coverage. | Compare event types, source health, detection tests. | Có thể không đáp ứng yêu cầu audit đủ chi tiết. |

Không tự tính alternative path là PASS khi **rủi ro quan trọng vẫn chưa được giải quyết**. Nếu control phải có vì luật/hợp đồng, cần review đúng authority và nguồn áp dụng.

### 17.3. Bất biến governance

- Control criterion không tự thay đổi để làm báo cáo xanh.
- Exception có scope, owner, risk assessment, expiry và conditions.
- Renewal đòi reassessment và approval mới theo policy.
- Control failure vẫn được ghi dù residual risk được chấp nhận.
- Khắc phục xong phải retest trước khi đóng finding.
- Third-party report không miễn customer-side configuration checks.

## 18. Case study: xác định controls cho nền tảng SaaS xử lý đơn hàng

### 18.1. Bối cảnh

Một doanh nghiệp vận hành **Order Platform** trên cloud, gồm:

- Web/mobile clients và API gateway.
- Order API trong hai Kubernetes clusters production.
- Database chứa order/customer data phân loại Confidential.
- Worker jobs gửi purchase events tới analytics SaaS.
- Enterprise IdP và service/workload identities.
- Centralized security logging/SIEM, backup vault và recovery site.
- CI/CD có khả năng triển khai code, config và IAM changes.

Security objectives giả định:

1. **O1 — Confidentiality:** người dùng không đọc dữ liệu tenant khác.
2. **O2 — Integrity:** giao dịch không bị sửa trái quyền hoặc mất/duplicate ngoài contract.
3. **O3 — Accountability:** privileged changes quan trọng có thể audit/detect và điều tra.
4. **O4 — Availability/recovery:** dịch vụ Critical có thể khôi phục trong RTO/RPO đã được doanh nghiệp duyệt.
5. **O5 — Controlled third-party sharing:** chỉ gửi dữ liệu đã duyệt tới analytics vendor.

### 18.2. Xác định risk scenarios

| ID | Scenario | Tài sản/impact | Security objective |
|---|---|---|---|
| R-01 | User A truy cập order thuộc tenant B qua API. | Customer data leak, contractual/privacy exposure. | O1 |
| R-02 | Service principal bị lạm dụng để đọc toàn DB. | Mass data access, increased blast radius. | O1, O3 |
| R-03 | Privileged IAM grant ngoài approval. | Takeover, config changes, audit disable. | O3 |
| R-04 | Parser log mất actor/target sau release. | Blind detection, khó điều tra. | O3 |
| R-05 | Retry/batch ghi trùng purchase order. | Data integrity, financial/business impact. | O2 |
| R-06 | Region outage hoặc ransomware ảnh hưởng primary. | Service downtime, data loss, unsafe restore. | O4 |
| R-07 | Analytics event có trường PII không cần thiết. | Third-party sharing vượt purpose. | O5 |

### 18.3. Chọn controls tương ứng

| Control ID | Objective/biện pháp | Rủi ro | Population/applicability | Evidence cốt lõi |
|---|---|---|---|---|
| **C-AUTH-01** | Server-side object authorization, deny by default. | R-01 | Mọi routes/order operations theo inventory. | Negative tenant/role tests và backend audit. |
| **C-IAM-02** | Least privilege, workload identity, credential lifecycle. | R-02, R-03 | Service/human privileged paths. | Effective IAM, denied grants, change audit. |
| **C-APPROVE-03** | Privilege changes có approval trong policy. | R-03 | Privileged change events trong production. | Raw events joined to approvals và exception status. |
| **C-LOG-04** | Critical admin/API audit events được sinh và thu. | R-03, R-04 | Source register trên accounts/clusters. | Source health, raw/normalized mapping. |
| **C-DET-05** | Priority threat detections tạo alert/case. | R-03, R-04 | Use cases và sources theo threat model. | Positive/negative tests và event-to-case. |
| **C-DATA-06** | Event payload allowlist và egress enforcement. | R-07 | Analytics integrations/data flows. | Synthetic schema, network, audit và vendor scope. |
| **C-INTEGRITY-07** | Idempotency, transactional invariants, reconciliation. | R-05 | Order write/worker pipelines. | Duplicate/retry tests, reconciliation. |
| **C-DR-08** | Protected recovery points và end-to-end restore. | R-06 | Critical service, DB, dependencies. | Restore exercise, consistency, RTO/RPO. |
| **C-CHANGE-09** | Approved change, artifact integrity, runtime drift. | R-02–R-07 | CI/CD, IaC, production controls. | Diff/review, digest, effective-state tests. |
| **C-INCIDENT-10** | Triage, containment, communication và recovery. | R-01–R-07 | Applicable incidents, response teams. | Runbook exercise, case timeline, actions. |

**Không nên tự kết luận R-01 đã được giảm tới mức chấp nhận chỉ vì C-AUTH-01 có tên trong bảng.** Phải xác minh scope routes, policy semantics, tests và residual risk.

### 18.4. Chọn thứ tự triển khai

Giả sử C-AUTH-01 đang thiếu tại endpoint export, C-LOG-04 có source gap ở cluster B, C-DR-08 có backup nhưng chưa restore test. Một lịch ưu tiên có thể là:

1. Điều tra và chặn **cross-tenant export** nếu có đường truy cập trái phép thực sự.
2. Sửa **critical logging gap** và đánh giá impact của kỳ mất visibility.
3. Kiểm tra backup/recovery thực, nhất là với dịch vụ Critical và keys đang thay đổi.
4. Hoàn thiện CI tests/gates để gap không tái xuất hiện.
5. Cập nhật control register, owners, findings, residual risk và evidence.

Thứ tự phải dựa trên **risk severity, exposure, exploitation, business impact và nghĩa vụ**, không chỉ theo chi phí thấp hoặc số ticket dễ đóng.

## 19. Case study chi tiết: từ requirement đến negative test

Lấy requirement R-AUTH:

> Người dùng chỉ có thể đọc/sửa order thuộc tenant được ủy quyền trong production.

### 19.1. Xác định tất cả đường tương tác

- GET /orders/{id}.
- GET /orders?filter=...
- POST/PUT/PATCH cho thuộc tính order.
- Batch export/download.
- Async worker/API internal.
- Support/admin override và delegated access.
- Caches, search index và read replicas.
- Webhooks hoặc SaaS integration nếu dữ liệu có thể đi tiếp.

Nếu chỉ test giao diện web, có thể bỏ các route API hoặc worker trực tiếp.

### 19.2. Phân rã control objective

**G0:** không có read/write ngoài quyền đối với tenant order data trong scope đã xác định.

- G1: Inventory của data access paths đầy đủ theo architecture/threat model.
- G2: Mỗi path áp server-side authorization đúng actor/resource.
- G3: Service principals/DB permissions không tạo đường bypass ngoài kiểm soát.
- G4: Admin override và exception được phê duyệt, audit và giới hạn.
- G5: Test, monitoring và release gates phát hiện regression.

~~~mermaid
flowchart TD
    TOP["G0: Tenant order data access is controlled"]
    S["Strategy: paths + enforcement + bypass + monitoring"]
    G1["G1: All material access paths inventoried"]
    G2["G2: Object-level authorization enforced"]
    G3["G3: Service/DB bypass paths constrained"]
    G4["G4: Exceptional admin access governed"]
    G5["G5: Tests/monitoring detect regression"]
    E1["API/data-flow inventory & threat review"]
    E2["Positive/negative auth tests"]
    E3["Effective service grants & deny tests"]
    E4["Approval + admin audit"]
    E5["CI/runtime tests + source-health"]
    TOP --> S
    S --> G1
    S --> G2
    S --> G3
    S --> G4
    S --> G5
    G1 --> E1
    G2 --> E2
    G3 --> E3
    G4 --> E4
    G5 --> E5
~~~

### 19.3. Test matrix

| Test ID | Tình huống | Expected behavior | Evidence |
|---|---|---|---|
| AUTH-T01 | User tenant A đọc order A được phép. | Success, đúng object, có audit phù hợp. | Redacted response, identity, record ID. |
| AUTH-T02 | User A đọc order B thuộc tenant B. | Deny, không leak data, không side effect. | 403/appropriate denial, backend state, audit. |
| AUTH-T03 | User A dùng filter/export để lấy order B. | Deny hoặc filter đúng quyền theo policy. | Query/export test, result verification. |
| AUTH-T04 | Service principal ít quyền thử truy cập toàn DB. | Deny ngoài scope, log. | Effective grants, negative DB/API test. |
| AUTH-T05 | Support admin sử dụng override được cấp phép. | Scope, expiry, approval và audit đúng. | Approval ID, sign-in, privileged action audit. |
| AUTH-T06 | Token test sai issuer/audience hoặc hết hạn. | Deny và không thay state. | Token metadata, result và correlation. |
| AUTH-T07 | API authorization dependency lỗi trong môi trường test. | Hành vi fail-safe theo policy, alert phù hợp. | Failure simulation, result, source health. |
| AUTH-T08 | Sau release, test mọi route/region được thêm mới. | Không mở rộng attack path chưa kiểm tra. | Route diff, test coverage, CI gate. |

Test cần dùng **synthetic identities và dữ liệu được ủy quyền**. Không thử truy cập dữ liệu người dùng thật trái phép hoặc làm hỏng production để tạo evidence.

### 19.4. Kết luận không vượt quá evidence

Một bộ 8 test pass chỉ chứng minh những **trường hợp được thử**. Muốn hỗ trợ G0 cho population rộng, cần thêm route inventory completeness, code/config review, effective permission mapping, test coverage và assumptions hợp lý.

**Chọn control và thiết kế assurance argument xảy ra cùng nhau:** lập luận phơi bày những control/path còn thiếu mà checklist thuần túy khó nhìn thấy.

## 20. Monitoring khi control đang hoạt động

Một control được xác định và triển khai cần có **failure signals**.

### 20.1. Một số tín hiệu vận hành

| Control | Runtime signal | Drift/failure signal |
|---|---|---|
| Privileged MFA. | Sign-in/policy events, enforcement outcomes. | New bypass route, disabled policy, invalid exception. |
| API authorization. | Deny/allow with actor and resource, business transactions. | Cross-tenant negative test fail, route không có middleware. |
| Least privilege. | Effective permission changes, activity outside expected. | Wildcard grant, trust change, unauthorized access. |
| Centralized logging. | Expected event types, ingestion, retention and health. | Missing source, parser error, delayed event, clock skew. |
| Detection rule. | Alert/case from authorized fixtures, false-positive trends. | Positive test no alert, routing broken, stale rule. |
| Data minimization. | Schema/egress metadata, approved destinations. | Unapproved field, endpoint hoặc region. |
| Backup/recovery. | Backup catalog, integrity, restore test result. | Job failure, key unavailable, restore/RTO fail. |
| Change approval. | Change events matched to approvals. | Out-of-band change, missing actor/approval. |

Không nên ghi raw secrets hoặc không cần thiết thu PII chỉ để có telemetry. **Evidence design cũng phải tuân thủ data minimization.**

### 20.2. Event-driven reassessment

Một control cần đánh giá lại khi:

- New application/asset/region/tenant đi vào scope.
- Privileged role, trust boundary, API route hoặc token scope đổi.
- IaC, Kubernetes admission, network policy hoặc KMS đổi.
- Logging source/parser/detection rule đổi.
- Third-party integration/data flow/contract đổi.
- Có vulnerability mới liên quan hoặc incident/near miss.
- Backup/DR topology, key hoặc dependency thay.
- Một exception hết hạn hoặc control monitoring mất tín hiệu.
- Evidence đã quá thời gian phù hợp theo control risk.

**Audit date chỉ là một trigger bổ sung**, không phải điều kiện duy nhất để control được kiểm tra.

## 21. Control coverage và chương trình đo lường

### 21.1. Ba chỉ số không được đánh đồng

1. **Control mapping coverage:** số yêu cầu/rủi ro đã có design mapping phù hợp.
2. **Deployment/implementation coverage:** số đối tượng đã được triển khai control theo định nghĩa.
3. **Verified coverage/effectiveness:** số đối tượng hoặc scenarios có evidence đủ cho claim.

Một requirement có control mapping chưa chắc đã triển khai. Một control đã triển khai chưa chắc có effectiveness.

### 21.2. Công thức verified coverage

Đặt:

- A: tất cả **applicable units** theo inventory và applicability rule.
- V: những units có evidence đủ, đáp ứng **full verified coverage criterion**.
- Q: những units **UNKNOWN/INCONCLUSIVE**.

\[
\text{Verified coverage}=\frac{|V|}{|A|}\times 100\%
\]

\[
\text{Unknown rate}=\frac{|Q|}{|A|}\times 100\%
\]

Nếu |A| = 0 và đã xác minh không có applicable units, báo **N/A**, không tự đặt 100%. Nếu không rõ population, phải báo **inconclusive** chứ không tự loại unknown.

### 21.3. Ví dụ định lượng

Một tổ chức có **60 production service–control pairs** đã được xác định applicable:

- 42 VERIFIED.
- 8 IMPLEMENTED_UNVERIFIED.
- 5 PARTIAL.
- 3 FAILED.
- 2 UNKNOWN.

Verified coverage = 42/60 = **70%**.

Implemented-or-verified theo định nghĩa riêng = (42+8)/60 ≈ **83,33%**.

Unknown rate = 2/60 ≈ **3,33%**.

Không nói “83,33% controls effective” hoặc “70% systems secure”, vì unit đang là **service–control pair**, không phải system hoặc attack probability.

### 21.4. Risk-weighted coverage

Khi các units có criticality khác nhau, có thể đặt trọng số **được phê duyệt trước**:

\[
\text{Risk-weighted verified coverage}
=\frac{\sum_{i \in A} w_i\,v_i}{\sum_{i \in A} w_i}\times100\%
\]

Trong đó v_i = 1 nếu unit verified, ngược lại 0, w_i là trọng số priority không âm. Nếu tổng w_i = 0 thì không tính tỷ lệ.

Ví dụ:

| Service–control unit | Risk weight | Verified |
|---|---:|---|
| Payment API authorization. | 5 | Không. |
| Order database encryption. | 5 | Có. |
| Internal wiki MFA. | 1 | Có. |
| Static website logging. | 1 | Có. |

Unweighted = 3/4 = **75%**, nhưng weighted = (5+1+1)/(5+5+1+1) = 7/12 ≈ **58,33%**.

Trọng số này **không phải xác suất breach hoặc mức mất mát tiền tệ**, chỉ giúp nêu ưu tiên; không dùng để che một mandatory Critical control FAIL.

### 21.5. Metrics bổ trợ

- Authoritative population completeness.
- Key control test coverage theo threat scenario.
- Source-health, missing telemetry và evidence freshness.
- Số Critical gaps, age và time-to-detect control drift.
- Exceptions hết hạn hoặc kéo dài, risk acceptance không hợp lệ.
- Remediation retest success, không chỉ ticket Done.
- Control owners không xác định hoặc mất contact.
- Changes không được mapping tới control reviews.
- Residual risk và negative test failures.
- Third-party controls/customer-side responsibility coverage.

**Metric phải hỗ trợ quyết định**. Không tối ưu chỉ một phần trăm tổng để làm dashboard đẹp.

## 22. Change management và lifecycle của control catalog

Control register không phải tài liệu viết một lần cho audit. Nó thay đổi khi **hệ thống và risks đổi**.

### 22.1. Khi tạo mới control

1. Có requirement/risk và security objective rõ.
2. Có owner và technical/operational mechanism.
3. Có applicability/population và dependencies.
4. Có criteria, evidence, test method và review cadence.
5. Có implementation plan và residual risk assessment.
6. Có approval theo governance và version control.

### 22.2. Khi sửa control

- Ghi lý do và control version.
- Phân tích thay đổi nghĩa của PASS/FAIL.
- Đánh giá assets, tenants, reports và test fixtures chịu ảnh hưởng.
- Review contracts/obligations/threats nếu control behavior đổi.
- Revalidate evidence đã dùng trước đó có còn phù hợp không.
- Sửa dashboards và metric denominators có giải thích.
- Không hồi tố thay đổi criterion để biến một thời kỳ fail thành pass.

### 22.3. Khi retire/replace control

Ví dụ thay source logging hoặc IdP:

- Xác định mọi consumer đang **kế thừa** control cũ.
- Có kế hoạch migrate, fallback và lịch overlap.
- Test end-to-end control mới trên từng applicable environment.
- Bảo toàn audit/recovery evidence của thời kỳ trước.
- Đóng gaps của control cũ hoặc nêu limitations.
- Cập nhật risk register, register mapping, owner và exception.
- Chỉ retire sau khi reviewer xác nhận **không còn consumer phụ thuộc chưa xử lý**.

### 22.4. Vì sao phải giữ lịch sử control version?

Nếu quý 1 criterion là “có audit log”, quý 2 được nâng thành “event-to-case trong SLA” thì sự khác biệt giữa hai kỳ **không nhất thiết là control suy giảm**; tiêu chí đã thay.

Reports cần ghi **control definition version, assessment criteria và period** để không so sánh tỷ lệ không tương thích.

## 23. Anti-patterns khi xác định security controls

### 23.1. Copy framework rồi coi là đã thiết kế

> “Chúng ta triển khai 100 controls từ một spreadsheet mẫu.”

Không có threat mapping, applicability, owner hoặc evidence: có thể tạo 100 hàng nhưng chưa có một chương trình kiểm chứng hữu ích.

**Cách sửa:** map từng control vào requirement/risk, chọn population, mechanism và test. Gộp trùng lặp có rationale; chỉ giữ control phù hợp.

### 23.2. Chọn controls vì có sẵn tool

> “Đã mua SIEM nên mọi rủi ro đều có detection.”

SIEM chỉ hoạt động trong nguồn/event và rule scope hiện có. **Không có source health hay end-to-end tests**, detection claim yếu.

**Cách sửa:** xác định threat use cases trước, rồi chọn event sources, parsing, rules, case routing và owner.

### 23.3. Đếm controls thay vì đo attack-path coverage

> “Chúng ta có 20 IAM controls nên quyền admin đã an toàn.”

Nếu còn một đường legacy direct-admin bypass, nhiều controls khác không bù được.

**Cách sửa:** threat/attack-path matrix và negative tests cho bypass.

### 23.4. Viết control quá mơ hồ

> “Đảm bảo dữ liệu an toàn.”

Không có behavior, scope, unit hoặc test.

**Cách sửa:** tách thành confidentiality, integrity, data flows, key access, authorization, retention và recovery criteria theo yêu cầu thực.

### 23.5. Dùng policy làm evidence effectiveness

> “Có policy access review nên mọi quyền đã được duyệt.”

Policy chỉ là một phần design.

**Cách sửa:** event population, approval joins, exception review và test effective permission.

### 23.6. Gộp N/A, exception và unknown

> “Không cài được EDR nên không áp dụng.”

Khả năng công nghệ không xác định tính applicability. Exception cần thẩm quyền/time-bound; unknown cần điều tra.

**Cách sửa:** định nghĩa status và approval path riêng.

### 23.7. Quên dependency và shared controls

> “Cloud provider quản lý phần bảo mật nên team app không cần test.”

Mô hình trách nhiệm chung có các customer-side configs. Một bản vendor report có scope cụ thể, không xác minh app controls.

**Cách sửa:** mô hình responsibility/consumer mapping và test configuration phía mình.

### 23.8. Chỉ xem control lúc audit

> “Ngày audit rule đã bật nên control hoạt động cả năm.”

Config snapshot không chứng minh operating effectiveness.

**Cách sửa:** history, change triggers, recurring tests, source-health và evidence time validity.

### 23.9. Quá lệ thuộc control automation score

> “Dashboard 95% xanh nên không còn critical risk.”

Một control Critical fail và các unknowns có thể bị trung bình che lấp.

**Cách sửa:** report Critical gaps, threat coverage, risk/exception và limitations bên cạnh overall score.

### 23.10. Remediation khép kín trên ticket

> “Ticket Done nên control restored.”

Không có effective-state verification hoặc retest.

**Cách sửa:** close only when acceptance criteria và reviewer evidence đạt.

## 24. Bài thực hành 1: chọn control cho tình huống API

### 24.1. Đề bài

Một hệ thống thanh toán giả định có:

- Payment API public phía sau gateway.
- Order và customer databases phân loại Confidential.
- Admin portal dùng SSO.
- Service principals cho analytics integration.
- Một database snapshot được gửi tới DR site.
- SOC nhận một phần cloud logs.

Threat model ưu tiên:

1. Truy cập tài khoản khách hàng khác qua API object ID.
2. Service token bị lộ và đọc dữ liệu ngoài mục đích.
3. Đặc quyền cloud bị cấp ngoài approval.
4. Parser bỏ event quan trọng khiến SOC không thấy misuse.
5. Snapshot không giải mã được sau key rotation.

### 24.2. Nhiệm vụ

1. Xác định security objectives cho từng threat scenario.
2. Viết ít nhất năm requirements có chủ thể, scope và behavior.
3. Chọn tối thiểu tám controls gồm preventive, detective, response và recovery.
4. Xác định owner, inherited/shared controls và dependencies.
5. Tạo risk-to-control matrix với ít nhất một **bypass/failure mode** cho mỗi control.
6. Viết ba negative tests cho API authorization và một test effective IAM privilege.
7. Thiết kế log source inventory và event-to-case test sau parser change.
8. Viết acceptance criteria cho restore sau KMS rotation.
9. Xác định hai control gaps cần escalation theo risk và lý do.
10. Tạo một control register với scope, test method, evidence và review trigger.

### 24.3. Gợi ý đáp án

Một tập controls khả thi:

| Threat | Controls chủ đạo | Supporting controls / evidence |
|---|---|---|
| BOLA/cross-tenant. | Server-side object-level authorization, deny-by-default. | Route/data-flow inventory, negative cross-tenant tests, audit. |
| Leaked service token. | Narrow token scopes, short-lived credentials, least privilege. | Secret manager, rotate/revoke, effective permissions, egress data minimization. |
| Unauthorized privileged grant. | IAM approval/workflow enforcement, effective boundary. | Cloud IAM audit, alert, break-glass review, change records. |
| Detection blind spot. | Logging source coverage, parser validation, rule-to-case pipeline. | Canary, source health, positive/negative detection tests. |
| DR decryption failure. | Recovery key policy/availability, tested restore. | Key lifecycle, isolated restore exercise, RTO/RPO and data consistency. |

Không có “một công cụ duy nhất” chứng minh cả năm threat scenarios đều được kiểm soát.

## 25. Bài thực hành 2: audit một danh mục control yếu

Một chương trình hiện có 12 control statements:

- “Có firewall.”
- “Có MFA.”
- “Có SOC.”
- “Có backup.”
- “Có mã hóa.”
- “Có policy vulnerability.”
- “Quản lý nhà cung cấp tốt.”
- “Ứng dụng kiểm tra quyền.”
- “Đã phê duyệt change.”
- “Có kiểm soát container.”
- “Có logging.”
- “Hệ thống tuân thủ quy định.”

Nhóm báo **12/12 implemented**, vì mỗi dòng đều có screenshot hoặc policy PDF. Auditor hỏi về API BOLA, log source missing, restore failure và quyền third-party.

### 25.1. Nhiệm vụ

1. Chỉ ra vì sao **12/12 implemented** không phải operating effectiveness.
2. Chọn bốn statements yếu nhất và viết lại thành control definitions có scope, mechanism, owner, evidence, test.
3. Phân biệt control nào là **policy**, control nào là **mechanism**, control nào chỉ là một **mục tiêu tổng quát**.
4. Lập danh sách authoritative inventories cần trước khi tính coverage.
5. Tạo trạng thái VERIFIED/PARTIAL/FAIL/UNKNOWN/N/A cho từng applicable asset-control pair.
6. Chọn hai critical threats mà control catalog hiện tại có thể chưa bao phủ.
7. Viết báo cáo 6–8 câu cho lãnh đạo, tránh tuyên bố “mọi system compliant”.
8. Đề xuất một vòng reassessment khi release/config/vulnerability/vendor mới xuất hiện.

### 25.2. Một ví dụ viết lại

**Trước:** “Có logging.”

**Sau:** 

> CTRL-LOG-04 — Mọi nguồn audit được phân loại Critical trong production inventory phải tạo và đưa các event thuộc catalog đã phê duyệt tới nơi xử lý với các trường actor, action, target, outcome và timestamp có ý nghĩa. Hệ thống phải phát hiện sự im lặng bất thường/mất nguồn và có test end-to-end cho các detection use cases ưu tiên trong kỳ kiểm chứng. Platform logging chịu trách nhiệm source/pipeline; SOC chịu trách nhiệm detection/case; security assurance xác minh coverage, quality và gaps.

Với control này, **PASS** đòi evidence về population, behavior và kỳ quan sát, không phải screenshot của một dashboard.

## 26. Checklist xác định control trước khi đưa vào chương trình assurance

### 26.1. Risk và requirement

- [ ] Có security objective và risk/threat scenario rõ.
- [ ] Requirement có ID, source, version, applicability và owner.
- [ ] Có architecture/data-flow/trust-boundary map phù hợp.
- [ ] Đã đối chiếu asset/identity/data inventories để biết population.
- [ ] Control phù hợp với threat mechanism, không chỉ có tên trong framework.
- [ ] Có đánh giá các đường bypass và những attack paths chưa được bao phủ.
- [ ] Đã xác định mandatory requirements, dependencies và nghĩa vụ bên ngoài.

### 26.2. Control definition

- [ ] Control có ID và version ổn định.
- [ ] Objective, mechanism và điều kiện áp dụng cụ thể.
- [ ] Rõ preventive/detective/corrective/recovery role nếu có.
- [ ] Rõ key/supporting/inherited/alternative control.
- [ ] Có control owner, operator, risk owner và assessor.
- [ ] Có dependency/fault-domain và failure-mode analysis.
- [ ] Có kỹ thuật vận hành, change trigger và monitoring.
- [ ] Có phương án exception/risk decision đúng thẩm quyền.

### 26.3. Assurance design

- [ ] Mỗi control có criterion có thể kiểm chứng hoặc phản bác.
- [ ] Tách design, implementation và operating effectiveness.
- [ ] Positive/negative/failure tests phù hợp với claim.
- [ ] Evidence contract có source, scope, time, tool/version và provenance.
- [ ] Có population completeness và data-quality checks.
- [ ] UNKNOWN/NOT_ASSESSED/FAIL không bị tính như VERIFIED.
- [ ] Có traceability tới requirements, assets, tests, evidence và findings.
- [ ] Có review hoặc sample method thích hợp và independent challenge.
- [ ] Có remediation acceptance và retest, không đóng chỉ bằng ticket Done.
- [ ] Có metrics theo criticality và risk, không chỉ tổng control count.
- [ ] Có review lịch định kỳ và theo thay đổi/incident/vendor events.
- [ ] Kết luận chỉ mạnh tới mức evidence thực sự hỗ trợ.

## 27. Câu hỏi tự đánh giá

1. “Xác định control” khác gì việc mua một security product hoặc viết policy?
2. Vì sao phải có security objective và risk scenario trước khi chọn control?
3. Requirement, control, criterion, test và evidence khác nhau thế nào?
4. Một security requirement có thể cần nhiều controls không? Cho ví dụ với privileged access.
5. Control preventive khác detective ở đâu? Vì sao detection không thay prevention trong mọi mục tiêu?
6. Key control và supporting control có thể phụ thuộc nhau như thế nào?
7. Khi nào một control được gọi là inherited hoặc shared? Customer-side responsibilities là gì?
8. Tại sao cần authoritative population độc lập với console công cụ control?
9. “MFA installed” có đủ chứng minh privileged access protected không? Vì sao?
10. Một control definition tốt tối thiểu cần những trường nào?
11. Vì sao phải ghi assumptions, dependencies và bypass paths?
12. Hãy nêu một common-mode failure giữa control và hệ đo của chính nó.
13. Positive/negative/failure tests khác nhau thế nào khi kiểm tra authorization?
14. Design, implementation và operating effectiveness khác nhau ở đâu?
15. Một screenshot được chụp hôm nay có chứng minh control hoạt động cả quý không?
16. Làm thế nào phân biệt NOT_APPLICABLE, UNKNOWN và APPROVED_EXCEPTION?
17. Compensating control cần evidence nào trước khi được xem là đủ giảm rủi ro?
18. Khi requirements thay phiên bản, control register và test contract phải cập nhật điều gì?
19. Nếu một API có 10 routes và chỉ 8 routes được test, có thể kết luận “toàn bộ authorization đáp ứng” không?
20. Verified coverage 42/60 khác implemented-or-verified 50/60 thế nào?
21. Risk-weighted coverage thấp hơn unweighted coverage cho thấy điều gì, và không cho thấy điều gì?
22. Một release mới thêm cloud account khiến control coverage metrics thay đổi. Phải xử lý mẫu số thế nào?
23. Hãy mô hình hóa một graph **risk → requirement → control → asset → test → evidence → finding**.
24. Hãy tự viết ba controls cho hệ thống quen thuộc, mỗi control có owner, scope, criterion, source evidence, failure signal và reassessment trigger.

## 28. Tổng kết: xác định control là thiết kế một khả năng có thể bảo đảm

Một chương trình assurance chỉ có chất lượng khi controls được xác định theo **rủi ro và requirements có hiệu lực**, áp dụng tới **đúng tài sản và đường truy cập**, có owner, cơ chế, dependencies và criteria có thể test.

Một danh mục control đáng tin phải giúp trả lời:

- Tại sao control cần tồn tại và giảm rủi ro nào?
- Nó được áp ở đâu, cho ai, trong điều kiện nào?
- Làm sao biết control đang hoạt động và phát hiện khi nó thất bại?
- Những trường hợp nào vẫn nằm ngoài phạm vi hoặc chưa có evidence?
- Ai quyết định residual risk, khắc phục và đánh giá lại?
- Reviewer có thể truy từ claim về source, test và timestamp không?

**Điểm cốt lõi:** **Xác định control không phải là điền tên các công cụ bảo mật vào checklist.** Đây là bước thiết kế **các cơ chế giảm rủi ro có mục tiêu, phạm vi, người chịu trách nhiệm và cách chứng minh hiệu lực**. Khi control được nối với threat scenarios, obligations, authoritative population, negative tests, telemetry, evidence và remediation, chương trình **SECURITY_SECURITY_ASSURANCE** mới có thể đánh giá và cải thiện bảo mật **liên tục**, thay vì chỉ thu thập tài liệu tại thời điểm audit.
