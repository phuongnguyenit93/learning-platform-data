# Configuration update: Bảo đảm an toàn cho thay đổi cấu hình bằng kiểm chứng và bằng chứng

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Giải thích **configuration update** trong **change assurance**, phân biệt thay đổi cấu hình với thay đổi mã nguồn, cấu hình chuẩn, thay đổi khẩn cấp, drift và remediation.
2. Xác định **security impact** của một thay đổi cấu hình trên cloud, Kubernetes, IAM, mạng, ứng dụng, logging, secret, encryption, backup và các hệ thống phụ thuộc.
3. Thiết kế luồng **request → impact assessment → approval → pre-change validation → rollout → runtime verification → monitoring → rollback/fix → evidence** có kiểm soát.
4. Xây dựng security acceptance criteria và test cases cho cả tính đúng chức năng, **least privilege**, segmentation, telemetry, tính sẵn sàng và khả năng khôi phục.
5. Sử dụng **Infrastructure as Code (IaC), GitOps, policy as code, signed artifacts, immutable versioning, progressive delivery và drift detection** đúng vai trò.
6. Phân biệt **desired state, deployed state, effective/runtime state**; chọn evidence để chứng minh cấu hình đã thay đổi như mong muốn trên **đúng population**.
7. Tổ chức rollback hoặc forward-fix có tính đến **stateful changes, dữ liệu, keys, certificates và dependency ordering**, thay vì giả định revert commit là đủ.
8. Xây dựng assurance case và báo cáo findings/remediation có thể audit cho một đợt cập nhật cấu hình production.

> **Bối cảnh:** Đây là bài học thuộc mô-đun **SECURITY_SECURITY_ASSURANCE**, hướng tới cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật từ phân tích rủi ro, security controls, kiểm thử, audit đến khắc phục và assurance liên tục. Các chính sách, thời gian, ngưỡng và hệ thống đặt tên trong ví dụ đều là **giả định đào tạo**, không tự động là tiêu chuẩn bắt buộc của một tổ chức.

## 1. Configuration update là gì?

**Configuration update** là việc thay đổi một hoặc nhiều tham số, quy tắc, mối liên kết hoặc trạng thái mong muốn quyết định **hệ thống hoạt động và thực thi controls như thế nào**. Thay đổi có thể được đưa qua file cấu hình, API, cloud console, IAM, Kubernetes manifest, secret manager, CI/CD pipeline hoặc các cơ chế điều khiển khác.

Ví dụ:

- Thêm hoặc loại bỏ một quyền trong IAM policy.
- Đổi firewall/network security group, API gateway policy hoặc Kubernetes NetworkPolicy.
- Bật/tắt audit source, sửa detection rule hoặc thay đường chuyển log.
- Điều chỉnh TLS version, certificate chain, trusted issuer/audience hoặc cơ chế verify token.
- Sửa retention của bucket hoặc backup vault; thay KMS key alias.
- Thay admission policy, Pod Security settings hoặc securityContext.
- Bật tính năng remote management, debug endpoint hoặc tracing có thể chứa dữ liệu nhạy cảm.
- Thay cloud account/region được phép, endpoint SaaS hoặc egress route.
- Cập nhật config application: rate limit, feature flag, retry, timeout, fail-open/fail-closed behavior.
- Điều chỉnh recovery runbook, replication hoặc failover settings.

**Configuration update có thể tạo thay đổi bảo mật mà không thay một dòng application source code.** Một quy tắc IAM mới hoặc cấu hình logging bị tắt có thể làm tăng attack surface ngay cả khi bản build ứng dụng không đổi.

### 1.1. Phân biệt những khái niệm liên quan

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| **Configuration baseline** | Trạng thái hoặc tập yêu cầu cấu hình đã được duyệt làm mốc đánh giá. | Cloud admin phải chịu MFA; audit trọng yếu phải bật. |
| **Configuration update** | Thực hiện một thay đổi cấu hình có ý định và phiên bản. | Thay đường forward cloud audit sang SIEM mới. |
| **Configuration drift** | Trạng thái thực lệch khỏi baseline hoặc desired state ngoài thay đổi được quản lý. | Người quản trị sửa firewall qua console sau khi pipeline đã deploy. |
| **Change request (CR)** | Hồ sơ lý do, phạm vi, rủi ro và quyết định cho thay đổi. | CR-2026-081 về chuyển log collector. |
| **Change assurance** | Xác nhận thay đổi hợp lệ, có controls, được triển khai và hoạt động như đã phê duyệt. | Kết quả kiểm thử, evidence và reviewer signoff. |
| **Incident response change** | Điều chỉnh khẩn cấp phục vụ cô lập/khôi phục sự cố, có governance riêng. | Chặn tạm một route trong containment. |
| **Remediation** | Khắc phục một finding/vulnerability hoặc control gap. | Bổ sung logging sau audit phát hiện thiếu source. |
| **Exception** | Quyết định có giới hạn cho trường hợp chưa đáp ứng baseline. | Legacy app tạm chưa hỗ trợ một chính sách TLS trong khi được giám sát. |

Một **change ticket đã được duyệt** không tự chứng minh **runtime state an toàn**. Một **Git commit đã merge** cũng không chứng minh mọi workload đang dùng config mới.

### 1.2. Vì sao thay đổi cấu hình dễ gây sự cố?

Cấu hình thường đi xuyên nhiều lớp, mỗi lớp có nguồn sự thật khác nhau:

- IaC mô tả tài nguyên dự định.
- Control plane nhận yêu cầu và ghi trạng thái.
- Controller/reconciler cố đưa tài nguyên về desired state.
- Data plane, process hoặc sidecar có thể chưa nạp lại config.
- IAM evaluation và network route phụ thuộc policies kết hợp và thứ tự ưu tiên.
- Audit/monitoring có thể chưa nhận sự kiện hoặc không nhìn thấy một region.

Vì vậy có ít nhất ba câu hỏi phải trả lời:

1. **Intent:** ta định thay đổi điều gì, và ai cho phép?
2. **Effective state:** điều gì đang thật sự được thực thi?
3. **Outcome:** thay đổi có tạo kết quả bảo mật và nghiệp vụ đúng như dự kiến, trong phạm vi thử hay không?

## 2. Các mục tiêu của configuration change assurance

Một đợt cập nhật đáng tin không chỉ “thành công” theo trạng thái deployment job. Nó cần bảo vệ các mục tiêu sau:

| Mục tiêu | Security question | Evidence có thể cần |
|---|---|---|
| **Authorization** | Thay đổi được thực hiện bởi actor có quyền và được phê duyệt đúng cấp? | CR, approval, actor identity, deployment audit. |
| **Integrity** | Nội dung áp dụng đúng artifact đã review, không bị sửa trái phép trên đường đi? | Commit/digest, pipeline provenance, signed artifact khi áp dụng, effective-state diff. |
| **Least privilege** | Không cấp quyền IAM, network hoặc workload vượt mục đích? | Effective permissions, policy analysis, negative access tests. |
| **Confidentiality/privacy** | Không mở đường truy cập/dump secret hoặc gửi dữ liệu ngoài phạm vi? | Data-flow diff, egress test, redaction, secret scan. |
| **Availability** | Thay đổi không làm ngừng dịch vụ ngoài ngưỡng được duyệt? | Canary, SLI, error rate, rollback drill. |
| **Observability** | Log/detection/alert vẫn hoạt động trong và sau rollout? | Canary events, collector health, event-to-alert trace. |
| **Recoverability** | Có rollback/forward-fix khi thất bại và đủ dependencies để phục hồi? | Runbook, backup/config snapshot, restore test, readiness check. |
| **Compliance** | Các control requirements và nghĩa vụ áp dụng vẫn được đáp ứng? | Criteria mapping, policy-as-code results, legal/compliance review khi cần. |
| **Traceability** | Reviewer có thể nối requirement, change, artifact và kết quả? | Change ID, test IDs, evidence index, reviewer decision. |

Security assurance phải kết nối **rủi ro, yêu cầu, control, test, evidence và remediation**, không xem deployment success là điểm kết thúc.

## 3. Threat model cho thay đổi cấu hình

### 3.1. Các kịch bản rủi ro thường gặp

| Scenario | Ví dụ cụ thể | Hậu quả |
|---|---|---|
| **Unauthorized change** | Một principal sửa IAM trust policy ngoài luồng approval. | Privilege escalation, mất kiểm soát. |
| **Over-broad scope** | Network rule dự định cho một subnet nhưng áp dụng cho toàn VPC. | Exposed services, lateral movement. |
| **Fail-open behavior** | Gateway lỗi khi kiểm tra token và cho request đi tiếp. | Bỏ qua authentication/authorization. |
| **Telemetry loss** | Đổi log collector nhưng quên cấu hình audit ở một cluster. | Blind spot khi xảy ra sự cố. |
| **Secrets exposure** | Đưa API key vào ConfigMap hoặc log debug. | Lộ credential, tăng khả năng truy cập trái phép. |
| **Rollback mismatch** | Revert app config nhưng DB schema/keys đã đổi không tương thích. | Dữ liệu lỗi hoặc mất khả năng phục hồi. |
| **Supply-chain compromise** | Pipeline áp một manifest khác với bản được review. | Backdoor hoặc disable security control. |
| **Race/ordering** | Thu hồi credential cũ trước khi service được cấp credential mới. | Mất dịch vụ, lỗi authentication. |
| **Partial rollout** | Chỉ 70% pods đã nạp config, policies không đồng nhất. | Kết quả bất định, bypass hoặc outage. |
| **Unmanaged drift** | Admin hotfix trên console, Git không phản ánh state. | Tái triển khai xóa hotfix hoặc duy trì lỗ hổng. |
| **Third-party dependency** | Vendor thay endpoint hoặc token scopes kéo theo config local. | Mất chức năng, lộ dữ liệu, thay đổi nghĩa vụ. |

Từng scenario phải nối tới một **control objective** và **acceptance criteria**. Với thay đổi high-risk, không đủ chỉ ghi “risk: low” mà không chỉ ra đường tấn công và kiểm thử tương ứng.

### 3.2. Phân loại thay đổi theo rủi ro

Một mô hình minh họa:

| Loại | Điều kiện thường gặp | Assurance tối thiểu |
|---|---|---|
| **Standard / low-risk** | Lặp lại, có thủ tục đã duyệt, tác động hạn chế, có tự động kiểm tra. | Change trace, policy check, rollout health, sample audit. |
| **Normal / medium-risk** | Thay config có tác động hạn chế đến dịch vụ/controls. | Risk assessment, approval phù hợp, test và rollback plan. |
| **High-risk / sensitive** | Động đến IAM admin, encryption keys, network trust, log pipeline, production data hoặc Critical service. | SoD, threat/data-flow review, negative tests, staged rollout, independent verification. |
| **Emergency** | Phải thay đổi ngay để containment hoặc phục hồi dịch vụ thiết yếu theo quy trình được phép. | Scope tối thiểu, logging, người có thẩm quyền, hậu kiểm và rollback/review. |

Đây là **cách phân tầng chính sách ví dụ**. Rủi ro không được phân loại chỉ dựa vào “thay một dòng YAML” hoặc “không có code change”.

## 4. Thiết lập change record có thể kiểm toán

### 4.1. Các trường thông tin cần có

| Trường | Ý nghĩa | Câu hỏi |
|---|---|---|
| **Change ID** | Liên kết mọi artifact và approval. | CR-2026-081 có duy nhất? |
| **Business/security reason** | Tại sao thay, giảm risk nào? | Có finding hoặc mục tiêu rõ? |
| **System inventory & scope** | Accounts, clusters, tenants, workload, region, version. | Những gì phải thay và những gì không được thay? |
| **Before/after state** | Khác biệt cấu hình dự kiến. | Có thay ngầm qua defaults, inheritance hoặc template không? |
| **Source requirement/control** | Policy hoặc baseline nào liên quan? | Control ID, phiên bản, applicability? |
| **Risk scenarios** | Threats, availability, privacy và dependencies. | Đường fail/bypass là gì? |
| **Owner/approver** | Ai triển khai, ai review và ai phê duyệt? | Thẩm quyền và SoD đã kiểm tra? |
| **Test plan** | Static, integration, negative, canary, runtime checks. | Expected vs actual, tiêu chí pass/fail? |
| **Rollout strategy** | Batch, canary, maintenance, dependencies. | Tiêu chí dừng và thời gian quan sát? |
| **Rollback/forward-fix** | Cách phục hồi với hệ thống có state. | Có đủ keys, version và permission? |
| **Monitoring** | Chỉ số, rule, alert và owner trong kỳ rollout. | Khi log pipeline bị lỗi có phát hiện? |
| **Evidence & findings** | Nguồn kiểm chứng, gap và retest. | Người khác tái hiện được kết luận? |
| **Closure** | Quyết định post-change và risk còn lại. | Đã xác minh runtime, không chỉ ticket Done? |

### 4.2. Ví dụ manifest quản trị

~~~yaml
change:
  id: "CR-2026-081"
  title: "Chuyển đường gửi Kubernetes audit events tới collector mới"
  type: normal-high-impact
  service: order-platform
  environment: production
  owner: platform-observability
  risk_owner: order-service-risk-owner
  target:
    clusters: ["order-prod-a", "order-prod-b"]
    audit_sources: ["kube-apiserver", "cloud-control-plane"]
  reason:
    finding_id: FIND-LOG-022
    objective: "Đảm bảo audit events trọng yếu được thu và phát hiện"
  before:
    collector_version: "collector-old"
    pipeline_ref: "pipeline-legacy"
  after:
    collector_version: "collector-new"
    pipeline_ref: "pipeline-v2"
  controls:
    - CTRL-LOG-001
    - CTRL-DET-003
  risk:
    classification: high
    key_scenarios:
      - "Mất audit event khi chuyển nguồn"
      - "Parser đổi schema và bỏ mất actor identity"
      - "Collector mới không có network permission"
  rollout:
    strategy: canary-then-batch
    abort_on: ["critical-log-gap", "collector-unhealthy"]
  validation:
    required_tests: ["LOG-001", "LOG-002", "DET-003", "LOG-004"]
  fallback:
    preferred: "Chuyển về pipeline legacy trong khi giữ event buffer"
    constraints: "Bảo đảm không mất dữ liệu và xử lý sự kiện trùng"
  governance:
    approval_required: true
    security_review_required: true
    independent_post_change_review: true
    status: proposed
~~~

Manifest là **ví dụ về cấu trúc thông tin**. Nó không tự bật log, không phải chuẩn công cụ, và các trường như fallback phải được gắn với runbook/test thực tế.

## 5. Phân biệt desired, deployed và effective state

### 5.1. Ba lớp trạng thái

~~~mermaid
flowchart LR
    P["Policy & approved baseline"] --> D["Desired configuration"]
    D --> C["Build/CI checks"]
    C --> ART["Versioned artifact/digest"]
    ART --> DEP["Deployment controller"]
    DEP --> RUN["Effective/runtime state"]
    RUN --> VAL["Behavioral tests & monitoring"]
    RUN --> DRIFT["Drift detection"]
    DRIFT --> FIX["Reconcile / investigate exception"]
    FIX --> D
    VAL --> E["Evidence & assurance decision"]
~~~

**Desired state:** mô tả mong muốn trong IaC/GitOps/config repository.

**Deployed state:** control plane, release manager hoặc orchestration báo đã áp dụng một version/artifact.

**Effective state:** quyền, routing, process, pods, network/data-plane và ứng dụng **thực sự đang dùng** các điều kiện đó.

Ví dụ:

- Git khai báo NetworkPolicy chặn egress.
- Pipeline đã apply thành công.
- Một namespace/label selector sai khiến workload cần bảo vệ không được chọn; traffic vẫn ra ngoài.
- Do đó **Git merged và kubectl apply success không chứng minh network segmentation đạt**.

### 5.2. Runtime verification phải kiểm tra điều gì?

- Resource IDs/namespace/accounts/regions đúng danh sách.
- Actual config/effective policy bằng expected sau giải quyết inheritance và priority.
- Mọi replica/node liên quan đã nạp version mới.
- Không còn đường bypass, endpoint cũ, webhook cũ hoặc service account quyền rộng.
- Control đang hoạt động qua positive/negative tests phù hợp.
- Log/alert đủ context và dẫn tới đúng đội xử lý.
- Các điều kiện availability, latency, error budget và data integrity đáp ứng tiêu chí triển khai.
- Những trường hợp không đủ visibility được ghi riêng **INCONCLUSIVE**, không tính PASS.

### 5.3. Application configuration có nhiều nguồn

Ứng dụng có thể đọc giá trị từ:

1. Defaults trong source.
2. File config hoặc chart values.
3. Environment variables.
4. Secret manager/config service.
5. Command-line flags.
6. Runtime feature flags.
7. Dynamic configuration API.

**Thứ tự ưu tiên phụ thuộc ứng dụng và framework**, không nên giả định chung. Test phải xác định nguồn thực sự có hiệu lực, tránh chỉ đọc một file nhưng process lại nhận giá trị từ environment.

## 6. Pre-change assurance: kiểm chứng trước khi triển khai

### 6.1. Baseline và inventory

Trước update:

1. Chốt **baseline** có hiệu lực và version.
2. Chốt authoritative inventory của assets, identities và config endpoints.
3. Lấy snapshot/evidence của trạng thái hiện tại khi cần và được phép.
4. Gắn control owners, risk owner và dependencies vào CR.
5. Xác định **population** phải thay và population không được tác động.
6. Liệt kê các exceptions hiện có và ngày hết hạn.
7. Xác định telemetry tối thiểu để phân biệt success với blind spot.

Nếu inventory không đầy đủ, một rollout “100%” có thể chỉ là 100% trong số tài nguyên công cụ nhìn thấy.

### 6.2. Impact analysis theo bảo mật

| Miền | Câu hỏi cần xem trước khi đổi |
|---|---|
| **IAM / authentication** | Có tăng privileges, sửa trust, bỏ MFA, đổi issuer/audience, mở đường break-glass không? |
| **Data flow / privacy** | Có chuyển dữ liệu nhạy cảm sang region/vendor/endpoint mới? Mục đích và retention còn hợp lệ? |
| **Network** | CIDR, pod selector, service mesh policy, DNS, proxy và egress có mở rộng? |
| **Cryptography** | Key/cert rotation có ảnh hưởng decrypt, recovery, pinned clients và backup? |
| **Logging / detection** | Schema, parser, collector hoặc retention thay làm mất event/alert? |
| **Availability** | Có thể gây thắt cổ chai, lỗi authentication, downtime, retry storm hoặc cascading failure? |
| **Recovery** | Rollback có thật sự đảo được thay đổi? Có data migration hoặc key revocation không thể đảo ngược? |
| **Third party** | Contract, subprocessor, new scopes, service status và migration phụ thuộc vendor? |
| **Governance** | Có xung đột policy, exception đã hết hiệu lực, thẩm quyền approval hoặc yêu cầu thông báo? |

### 6.3. Risk analysis và lựa chọn đường triển khai

Không có một nhãn rủi ro chung cho mọi thay đổi kiểu “config-only”. Đánh giá theo:

- **Severity nếu cấu hình sai** và phạm vi tác động.
- **Likelihood** do độ phức tạp, thao tác thủ công, quyền và bề mặt tấn công.
- **Reversibility** và thời gian phục hồi.
- **Blast radius** của batch, region, account, tenant.
- **Observability** và thời gian phát hiện.
- **Change dependency** giữa IAM/KMS, network, app, data và log.
- **Data migration/compatibility**.
- **Khả năng triển khai an toàn theo canary hoặc staged rollout**.
- **Chất lượng test** ở các môi trường trước production.

Với một thay đổi không thể rollback an toàn, phải có **forward-fix, fallback service mode và kế hoạch xử lý dữ liệu** được xem trước khi bấm deploy.

## 7. Phê duyệt và separation of duties

### 7.1. Mô hình trách nhiệm

| Vai trò | Trách nhiệm |
|---|---|
| **Requestor** | Đề nghị update và nêu business/security rationale. |
| **Configuration/control owner** | Thiết kế desired state, thực hiện thay đổi và duy trì control. |
| **Security reviewer** | Đánh giá threat/permission/data impact, test contract, evidence và các rủi ro chưa được che phủ. |
| **Business/risk owner** | Xác định ưu tiên và chấp nhận residual risk **trong thẩm quyền**. |
| **Change authority** | Phê duyệt triển khai theo phân quyền change management. |
| **Legal/compliance** | Xử lý nghĩa vụ bên ngoài nếu config thay đổi dữ liệu, xử lý, thông báo hay SLA. |
| **Incident/operations** | Thực hiện rollout, giám sát, containment hoặc rollback khi cần. |
| **Independent assurance/audit** | Kiểm chứng quy trình và evidence, đánh giá findings không phụ thuộc người tạo config. |

Một người có thể đảm nhiệm nhiều vai trong tổ chức nhỏ, nhưng phải kiểm soát **xung đột lợi ích** bằng peer review, bảo vệ audit trail và phân quyền phù hợp.

### 7.2. Các quyết định khác nhau

- **Approval thay đổi:** cho phép triển khai một kế hoạch trong phạm vi và điều kiện đã xác định.
- **Approval ngoại lệ:** có thể cho phép lệch baseline tạm thời trong thẩm quyền, có expiry và controls bù trừ.
- **Risk acceptance:** quyết định quản lý residual risk, không làm thay đổi thực trạng control.
- **Post-change acceptance:** xác nhận evidence cho thấy rollout đạt acceptance criteria, không chỉ được phép triển khai.

Không dùng một chữ ký “Approved” để mặc định đã bao gồm bốn quyết định trên.

## 8. IaC, GitOps và configuration integrity

### 8.1. Ưu điểm của khai báo cấu hình

Infrastructure as Code hoặc GitOps có thể giúp:

- Quản lý desired state theo version.
- Review diff qua pull request.
- Kết nối commit với change ID, reviewer và build artifact.
- Chạy automated policy/security tests trước triển khai.
- Thực hiện deployment nhất quán.
- Phát hiện runtime drift với desired state.
- Tạo audit trail và rollback/forward-fix có kiểm soát.

Nhưng **GitOps không thay thế security review và runtime verification**. Controller có thể áp nhầm account, manifest sai selector hoặc policy đúng cú pháp nhưng sai mục đích.

### 8.2. Review một cấu hình thay đổi

Đừng chỉ đọc các dòng thêm/xóa. Cần xem:

- Tác động semantic của thay đổi; inheritance/default có đổi?
- Resource dependency và resource nào bị destroy/recreate?
- Scope bị mở rộng do wildcard hoặc label selector?
- Secret được tham chiếu hay bị nhúng trực tiếp?
- ServiceAccount và IAM permissions có tăng?
- Network egress/ingress policy có cho phép thêm endpoint?
- Audit/retention có bị tắt hoặc giảm?
- Có trường hợp drift đang tồn tại khiến apply kết quả khác dự kiến?
- Có temporary exception hoặc resource được bảo vệ khỏi rollout không?
- Thay đổi có phụ thuộc bản rollout trước chưa hoàn thành?

Một diff nhỏ có thể có blast radius lớn khi sửa **policy shared** hoặc một default được kế thừa bởi nhiều workload.

### 8.3. Policy as Code: kiểm tra trước deploy

Những quy tắc thường được tự động hóa:

- Từ chối IAM wildcard grants ngoài ngoại lệ hợp lệ.
- Không tạo storage public cho dữ liệu nhạy cảm.
- Không cho privileged container/hostPath ngoài trường hợp được phê duyệt.
- Yêu cầu encryption/key policy và logging phù hợp baseline.
- Chặn insecure TLS options và không cho debug endpoint trên production.
- Kiểm tra tag/owner/region cho các resource bắt buộc.
- Chặn artifact không có nguồn gốc hoặc digest được phê duyệt.

**Policy test là một tầng kiểm soát**, không đảm bảo không có resource được tạo qua đường ngoài pipeline.

### 8.4. Supply-chain assurance cho config artifact

Một workflow mẫu:

~~~text
Change request CR-2026-081
  -> Pull request references CR + security requirements
  -> Review diff by authorized peers
  -> Static syntax/schema validation
  -> Policy-as-code checks
  -> Test plan and acceptance criteria approved
  -> Build immutable config artifact with digest
  -> Deployment identity constrained to target scope
  -> Record deployed digest and effective state
  -> Runtime behavior and source-health tests
  -> Reviewer signoff or finding/remediation
~~~

Nếu cần mức tin cậy cao, artifact có thể được ký, lưu provenance và áp dụng cơ chế verify trước deploy theo công nghệ phù hợp. Tuy nhiên, **hash/signature chỉ hỗ trợ integrity và nguồn gốc đã xác định**, không chứng minh nội dung config là an toàn hoặc có hiệu lực đúng.

## 9. Những phép kiểm tra trước triển khai

### 9.1. Validation tầng tĩnh

| Loại | Tình huống | Điều nó chứng minh và giới hạn |
|---|---|---|
| **Syntax/schema** | YAML/JSON parse, required fields, API version. | Artifact hợp lệ cấu trúc; chưa chứng minh policy đúng. |
| **Policy as Code** | Không có public bucket/wildcard privilege ngoài exception. | Chặn một số trạng thái không cho phép trong input được test. |
| **Secret scanning** | Không hard-code tokens, passwords hoặc private keys. | Phát hiện pattern trong files; không thấy gì không bảo đảm hết secret. |
| **Dependency/plan diff** | IaC plan phát hiện resource destroy/replace. | Thấy thay đổi dự kiến theo state hiện tại; plan có thể stale. |
| **Config unit tests** | Parser, schema mapping, default, precedence. | Logic config ở test fixture; chưa chứng minh runtime production. |
| **Static cross-resource check** | Network rule, service selectors, IAM references. | Giảm lỗi tham chiếu; còn phụ thuộc thực tế controller/runtime. |

### 9.2. Validation hành vi và negative tests

Các phép kiểm chứng hành vi nên gồm:

- **Positive:** luồng hợp lệ vẫn chạy.
- **Negative:** luồng trái quyền, sai token hoặc network bị cấm thực sự bị từ chối.
- **Boundary:** gần ngưỡng rate limit, timeout, retention hoặc credential expiry.
- **Failure injection có kiểm soát:** collector fail, dependency timeout, feature flag lỗi, worker restart.
- **Recovery:** rollback/forward-fix và kiểm tra dữ liệu không bị hỏng.
- **Observability:** event sinh ra có thể truy tới alert/case và on-call.
- **Compatibility:** clients cũ/mới, các replicas và version của dependencies.

Chỉ test positive path có thể bỏ qua **security bypass**.

### 9.3. Tiêu chí PASS rõ ràng

Không dùng một câu “test pass” nếu chưa định nghĩa kiểm tra nào.

Một test case nên có:

~~~yaml
test_id: "SEC-IAM-NEG-001"
change_id: "CR-2026-081"
scope: "order-api production-like integration environment"
objective: "Không cho non-admin gọi privileged endpoint"
preconditions:
  - "Auth policy v3 deployed"
  - "Test identity cannot hold admin permission"
action: "Invoke test-only privileged operation"
expected:
  http_status: 403
  audit_event_present: true
  no_state_change: true
evidence:
  - "Identity and effective claims snapshot"
  - "Request/response and backend state verification"
  - "Raw audit event with correlation ID"
result: "NOT_RUN"
~~~

Đây là **test fixture minh họa**, không phải phương thức xâm nhập hệ thống thật. Test chỉ được thực hiện trên tài khoản, endpoint và dữ liệu được ủy quyền.

## 10. Progressive rollout, canary và blast radius

### 10.1. Tại sao cần chia lô?

Một cấu hình sai có thể ảnh hưởng mọi request trong vài giây. Rollout từng bước giúp phát hiện lỗi với phạm vi nhỏ, miễn là:

- Canary thực sự đại diện cho các đường nghiệp vụ và security controls cần kiểm tra.
- Được giám sát đủ lâu, kể cả những hành vi không xuất hiện ngay.
- Tách biệt tài nguyên và phụ thuộc để lỗi không lan ra toàn bộ hệ thống.
- Có điều kiện dừng và kênh rollback còn hoạt động.

### 10.2. Chiến lược phổ biến

| Chiến lược | Mô tả | Rủi ro đặc biệt |
|---|---|---|
| **All-at-once** | Đổi tất cả trong một đợt. | Blast radius lớn; phù hợp khi thay đổi đơn giản, có kiểm chứng và nguy cơ giới hạn. |
| **Rolling update** | Thay dần từng replica/node. | Các version có thể đồng thời tồn tại, gây mismatch policy/schema. |
| **Canary** | Áp trước một tập nhỏ, kiểm thử rồi mở rộng. | Canary không đại diện traffic/tenant/region nhạy cảm. |
| **Blue/green** | Hai môi trường hoặc config sets, chuyển traffic khi đạt. | State/data hoặc shared IAM/KMS có thể không tách biệt. |
| **Feature-flag rollout** | Bật điều kiện logic theo nhóm người dùng. | Flag service availability, authz precedence và user targeting có thể bị lỗi. |
| **Region/account sequencing** | Thay từng fault domain. | Dependencies chung gây ảnh hưởng vượt region. |
| **Shadow/dual-write (khi thích hợp)** | Gửi kết quả sang đường mới để kiểm chứng trước chuyển thật. | Có nguy cơ tạo dữ liệu trùng hoặc vi phạm purpose/retention; phải kiểm soát. |

Không có chiến lược rollout nào bảo đảm an toàn nếu **validation và fallback không phù hợp kịch bản**.

### 10.3. Gating và tiêu chí dừng

Ví dụ một rollout high-risk chỉ tiến sang batch tiếp theo nếu:

1. Desired digest xuất hiện trên đúng đối tượng, không có cấu hình bất ngờ.
2. Functional SLIs nằm trong giới hạn được phê duyệt.
3. Authentication và authorization negative tests đạt.
4. Logging source health và critical detection use cases vẫn có evidence.
5. Không có tăng bất thường về traffic outbound hoặc dữ liệu nhạy cảm.
6. Không có finding Severity High chưa xử lý do thay đổi.
7. On-call và rollback owner xác nhận sẵn sàng.

**Chỉ số không xấu đi trong vài phút không đủ chứng minh** hệ thống an toàn cho một mối đe dọa hiếm gặp hoặc cho tác động trễ. Cần thêm test cụ thể và thời gian quan sát phù hợp.

## 11. Rollback không phải lúc nào cũng là revert commit

### 11.1. Reversible và non-reversible changes

Một số config update dễ đảo:

- Thay feature flag không ảnh hưởng dữ liệu.
- Chuyển đường traffic giữa hai backend cùng giao thức và state tương thích.
- Thay rate-limit threshold có kiểm tra rõ.

Một số thay đổi **không thể đảo bằng Git revert đơn thuần**:

- Revoke hoặc rotate encryption key làm dữ liệu cũ không đọc được nếu không giữ cơ chế decrypt phù hợp.
- Thay database schema hoặc dữ liệu đã migrate theo định dạng mới.
- Chuyển DNS/issuer/audience khiến token clients cũ hết giá trị và cần truyền thông.
- Xóa hoặc ghi đè log, object versions, snapshots, backups.
- Thay retention khiến dữ liệu đã bị xóa không thể khôi phục.
- Thay data residency/third-party endpoint đã chuyển dữ liệu ra ngoài.

### 11.2. Runbook rollback tối thiểu

- **Trigger:** ngưỡng nào bắt buộc dừng/cancel/revert?
- **Decision owner:** ai có quyền quyết định và ai triển khai?
- **Previous artifact:** digest/version của config và các dependencies trước đổi.
- **Data compatibility:** app version cũ có đọc data/state hiện tại không?
- **Credentials/keys:** còn khóa, certificates và quyền để quay lại không?
- **Rollback ordering:** phải sửa network, IAM, service, schema, DNS theo thứ tự nào?
- **Rollback time objective:** thời gian chấp nhận được theo business impact.
- **Validation:** functional, security, data integrity, logging và traffic sau rollback.
- **Evidence:** timestamps, commands/runbook steps, decisions, outcome và impact.
- **Follow-up:** root cause, new change ID nếu cần và kiểm tra lại controls.

**Rollback thử ở staging** hữu ích nhưng cần ghi khác biệt với production. Với thay đổi High/Critical, nếu không thể rollback an toàn thì cần **forward-fix plan và điều kiện dừng** trước khi bắt đầu.

### 11.3. Rollback bảo mật không đồng nghĩa quay lại cấu hình lỗi

Nếu config cũ có lỗ hổng nghiêm trọng, rollback hoàn toàn có thể khôi phục vulnerability. Cần quyết định dựa trên **hai rủi ro đồng thời**:

1. Rủi ro outage/data corruption do thay đổi mới.
2. Rủi ro exploitation khi quay lại phiên bản cũ.

Có thể chọn degraded mode, isolation, emergency rule hoặc forward-fix được phê duyệt thay vì mặc định revert. Điều này phải được ghi trong change decision và post-change risk record.

## 12. Change assurance với IAM và permissions

### 12.1. IAM có tính kế thừa và hiệu lực thực

Một thay đổi IAM có thể biểu hiện rất khác file policy:

- Quyền thông qua group và nested role.
- Trust policies và delegated administration.
- Service principals có khả năng assume role.
- Organization policy/SCP hoặc permissions boundary.
- Resource policy cộng với identity policy.
- Session policies và token claims.
- Kubernetes RBAC/cluster roles, admission and workload identity.
- Caches hoặc sessions đã cấp trước thay đổi.

Để kết luận least privilege vẫn đạt, cần đánh giá **effective permissions**, không chỉ một JSON policy.

### 12.2. Các test quan trọng

| Test | Expected |
|---|---|
| Identity cần quyền mới có thể thực hiện đúng operation được cho phép. | Có thể làm trong đúng scope. |
| Identity ngoài scope gọi cùng operation. | Bị từ chối, có audit phù hợp. |
| Identity được phép nhưng nhắm resource ngoài scope. | Bị từ chối. |
| Service principal cũ/role cũ sau thu hồi. | Không tiếp tục có quyền ngoài policy; lưu ý session/token hiệu lực còn lại. |
| Người không được ủy quyền cố thay IAM policy. | Bị từ chối hoặc phát hiện và điều phối theo control objective. |
| Đổi key/credential. | Quyền cũ được thu hồi theo lifecycle, app hợp lệ không ngừng do thứ tự sai. |

Không tự cho test thành công chỉ vì API trả mã lỗi; cần xác nhận lỗi đúng do **authorization** và backend không có tác động ngoài mong muốn.

## 13. Change assurance với Kubernetes

### 13.1. Những cấu hình có tác động lớn

- Pod Security admission/namespace labels.
- Security context: privileged, root user, Linux capabilities, seccomp, read-only filesystem.
- ServiceAccount, RBAC, workload identity và token automount.
- Admission webhooks và policies, bao gồm khả năng fail-open/fail-closed.
- NetworkPolicy, service mesh policies, ingress, egress, DNS.
- ConfigMaps/Secrets, image pull, digest và registry trust.
- Resource limits, probe/readiness, rollout strategy.
- Kubernetes API audit, node/container logging và telemetry.
- Storage classes, backup và persistent volume snapshots.

### 13.2. Ví dụ một Kubernetes Deployment đổi securityContext

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: orders
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      automountServiceAccountToken: false
      containers:
        - name: order-api
          image: registry.example.invalid/order-api@sha256:REPLACE_WITH_VALID_DIGEST
          securityContext:
            allowPrivilegeEscalation: false
            runAsNonRoot: true
            capabilities:
              drop: ["ALL"]
            seccompProfile:
              type: RuntimeDefault
          ports:
            - containerPort: 8080
~~~

Đây là **bản minh họa, không phải manifest sẵn deploy**: cần image digest hợp lệ, xác nhận container image có thể chạy non-root, cấu hình ứng dụng/probes, tài nguyên, traffic, policies và secret theo môi trường. Cài đặt token automount=false có thể làm hỏng ứng dụng nếu nó cần Kubernetes API. Một update bảo mật đúng phải **đánh giá dependency này trước**, không bật tham số rồi xem pod chạy lỗi là thành công.

### 13.3. Test sau thay đổi

1. PodSpec thực ở **mọi replica** thuộc Deployment mang các giá trị kỳ vọng.
2. Workload hoạt động với user và quyền filesystem thực tế.
3. Không còn privilege escalation hoặc Linux capabilities ngoài nhu cầu.
4. Không có ServiceAccount token mounted ngoài điều kiện đã phê duyệt.
5. Container mới/old replicas trong rolling update không tạo lỗ hổng tạm thời vượt ngưỡng.
6. Readiness, latency, lỗi ứng dụng và error budget đạt tiêu chí.
7. Audit/monitoring vẫn nhận security events.
8. Có cách chuyển về phiên bản phù hợp nếu image cần quyền mới và không thể chạy.

**Một manifest có field securityContext không chứng minh runtime được enforcement đầy đủ**, đặc biệt nếu workload có đường phụ thuộc đặc quyền ở nơi khác.

## 14. Change assurance với logging và detection

### 14.1. Những thay đổi cần chú ý

- Thay source audit hoặc destination log.
- Chỉnh parser, field schema và mapping actor/target.
- Thay filter/sampling có nguy cơ bỏ event quan trọng.
- Đổi retention, access control, encryption và log integrity.
- Chỉnh detection rule, threshold, suppressions hoặc allowlists.
- Thay alert routing/on-call schedules.
- Di chuyển SIEM, region hoặc nhà cung cấp xử lý log.

### 14.2. Mẫu coverage argument

**Claim:** “Sau update, các audit sources Critical trong scope tiếp tục gửi những event bắt buộc và use case phát hiện tăng quyền còn hoạt động.”

Cần có:

- Inventory nguồn Critical độc lập với connector đang báo healthy.
- Diff before/after config và collector/parser version.
- Evidence raw event nguồn, ingest, indexing và search khả dụng.
- Test tạo sự kiện tăng quyền được ủy quyền hoặc synthetic fixture có fidelity phù hợp.
- Event-to-alert-to-case timeline và đúng actor/target.
- Negative tests chống báo sai cho hoạt động hợp lệ.
- Source-health alert cho collector bị ngừng.
- Đối chiếu missing event, duplicate, clock skew và backlog trong rollout.
- Giới hạn: event types hoặc clusters chưa test.

### 14.3. Ví dụ mốc thời gian

Một test gửi event lúc **10:00:00 UTC**, collector nhận lúc **10:00:12**, rule phát alert **10:00:25**, case tới on-call **10:00:40**. Nếu mục tiêu nội bộ là **60 giây từ event đến delivered**, test này đạt trong phạm vi fixture và đường pipeline đã kiểm chứng.

Nhưng nếu chỉ kiểm tra một cluster, không được suy ra **tất cả các cluster đều đạt**. Cần ghi **denominator**, source coverage và health monitoring trong suốt giai đoạn chuyển.

## 15. Change assurance với cryptography, secrets và dữ liệu

### 15.1. Cập nhật TLS/certificate

Kiểm tra:

- Server-side protocol và cipher suites theo policy.
- Certificate chain, SAN, expiry, revocation handling và trust anchors.
- Clients cũ/mới có khả năng tương thích.
- Không còn cổng/endpoint yếu được truy cập qua đường phụ.
- Runtime handshake thực từ những đường client được phép.
- Log lỗi TLS và khả năng khôi phục khi certificate mới lỗi.

**Chứng chỉ mới đã được upload không có nghĩa mọi replica/proxy đang phục vụ chứng chỉ mới**.

### 15.2. Key và secret rotation

Một rotation có thể gồm:

1. Tạo hoặc chuẩn bị key/secret mới trong hệ quản lý đúng quyền.
2. Cấp quyền decrypt/verify hoặc nhận token theo thứ tự bảo đảm hoạt động.
3. Chuyển service sang credential mới, xác minh sử dụng thực.
4. Giới hạn và thu hồi credential cũ có cân nhắc sessions, retries và offline jobs.
5. Xác minh audit, secrets không xuất hiện trong logs/config artifacts.
6. Bảo đảm backups, DR và dữ liệu cũ vẫn có thể truy xuất theo chính sách.
7. Ghi evidence của rotation, revocation và những nơi chưa cập nhật.

Không nên “rotate” bằng cách **in secret mới vào CI log** hoặc xóa khóa cũ trước khi kiểm tra khả năng giải mã dữ liệu cần giữ.

### 15.3. Cấu hình retention/data residency

Thay retention từ 180 ngày xuống 30 ngày có thể hợp lý hoặc không tùy nguồn yêu cầu. Trước khi áp:

- Legal/compliance xác định hợp đồng/quy định và legal hold.
- Data owner xác định tập dữ liệu, bản sao, backup và subprocessors.
- Security đánh giá audit/incident evidence cần bảo toàn.
- Platform kiểm tra lifecycle policy và đối tượng được chọn.
- Chạy simulation/dry-run nếu nền tảng hỗ trợ.
- Xác nhận tác động **không thể đảo** khi dữ liệu bị xóa.
- Đo/test trạng thái sau update và xử lý exceptions có căn cứ.

Đây là ví dụ tại sao **configuration update có thể là một thay đổi nghiệp vụ và pháp lý quan trọng**, không chỉ thao tác hạ tầng.

## 16. Assurance case: tại sao thay đổi này an toàn?

### 16.1. Claim–Argument–Evidence

~~~mermaid
flowchart TD
    TOP["G0: Update C đáp ứng security objectives trong scope"]
    S["S0: Lập luận theo authorization, correctness, operation, recovery"]
    G1["G1: Thay đổi có phê duyệt đúng quyền và risk review"]
    G2["G2: Artifact được review, kiểm tra và áp đúng targets"]
    G3["G3: Effective configuration đáp ứng baseline và security tests"]
    G4["G4: Monitoring và logging còn đủ coverage"]
    G5["G5: Recovery/rollback hoặc forward-fix được chuẩn bị và kiểm chứng"]
    E1["CR + DoA + review + policy mapping"]
    E2["Diff + digest + deployed/effective state"]
    E3["Negative tests + functional canary"]
    E4["Source health + event/alert/case trace"]
    E5["Recovery plan + test + decision log"]
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

**Warrant:** nếu các đối tượng đã được xác định đầy đủ, update được cho phép, artifact và effective state đúng, security behavior đạt trong phạm vi test, observability và khả năng xử lý thất bại đủ, thì có cơ sở kết luận update đáp ứng các mục tiêu được đánh giá trong phạm vi. Không thể suy rằng toàn bộ hệ thống an toàn trước mọi threat scenario.

### 16.2. Những defeaters quan trọng

- Một account/cluster không có trong deployment target inventory.
- Một operator có quyền sửa trực tiếp config ngoài GitOps.
- Policy có thứ tự ưu tiên khiến rule cũ ghi đè rule mới.
- Một pod/node không load config mới dù controller báo success.
- Negative access test chỉ dùng một role nhưng quyền admin khác bypass.
- Monitoring dùng cùng pipeline với control được thay, nên khi hỏng không tự phát hiện.
- Rollback artifact cần một KMS key đã bị xóa.
- Contract/vendor change làm data flow ngoài scope đã phê duyệt.
- Một exception hết hạn vẫn được áp vào release.
- Unit tests chạy trên defaults khác production.

Khi một defeater trọng yếu chưa xử lý, kết luận có thể là **PARTIAL hoặc INCONCLUSIVE** thay vì PASS.

## 17. Case study: chuyển Kubernetes audit collector cho Order Platform

### 17.1. Bối cảnh và mục tiêu

Order Platform có hai production clusters:

- **order-prod-a**: vận hành checkout và order workers.
- **order-prod-b**: vận hành batch, admin jobs và reporting.

Tổ chức muốn chuyển từ collector cũ sang collector mới để cải thiện độ ổn định. Security requirement giả định: **mọi Kubernetes API audit event thuộc nhóm privileged changes phải được ghi và có detection/alert trong phạm vi các clusters production**.

Một đợt update có thể gây lỗi: audit chỉ hoạt động ở cluster A, parser mới bỏ trường username, backlog khiến rule đến trễ, hoặc quyền network không cho collector gửi event.

### 17.2. Phân tích rủi ro

| Risk ID | Kịch bản | Control/giải pháp | Test |
|---|---|---|---|
| R-LOG-01 | Mất source audit ở một cluster. | Source inventory, coverage health, canary. | T01 inventory reconcile, T02 canary mỗi cluster. |
| R-LOG-02 | Parser mới bỏ actor/target. | Schema contract, parser regression. | T03 field mapping và unknown-field tests. |
| R-LOG-03 | Collector gửi được nhưng không tới detection. | Pipeline/lookup, correlation test. | T04 raw-to-alert-to-case. |
| R-LOG-04 | Rollout gây duplicate hoặc mất event. | Bounded buffer, dedup, reconciliation. | T05 consistency và backlog test. |
| R-LOG-05 | SIEM creds cấp rộng hoặc secret lộ. | Scoped identity, vault, rotation, log redaction. | T06 negative permissions/secret exposure. |
| R-LOG-06 | Rollback mất quyền vào pipeline cũ. | Keep controlled fallback until validated. | T07 rollback drill. |

### 17.3. Phân rã rollout

**Giai đoạn 0 — trước deploy**

- Chốt inventory hai clusters và audit source IDs, account và timezone.
- Lưu baseline configs, parser, rules, source/target permissions và evidence source health.
- Rà soát CR, approvals, threat scenarios, rollback/runbook.
- Test với synthetic audit events ở lab hoặc môi trường tích hợp đại diện.
- Xác định điều kiện abort trước khi canary.

**Giai đoạn 1 — canary**

- Áp collector mới cho một source được chọn có kiểm soát.
- Giữ đường quan sát độc lập phù hợp để phát hiện collector mới bị lỗi.
- Phát fixtures event privileged change được ủy quyền.
- Kiểm tra actor/target, event time, ingest, alert và case.
- Đánh giá backlog, error rate, CPU/memory và quyền dữ liệu.
- Nếu bất kỳ test trọng yếu fail, **không mở rộng rollout**.

**Giai đoạn 2 — mở rộng theo cluster**

- Triển khai order-prod-a, sau đó order-prod-b theo trình tự đã duyệt.
- Mỗi cluster có evidence riêng, không dùng test cluster A làm kết luận cho B.
- Xác minh 100% audit sources thuộc population Critical và event types bắt buộc.
- Theo dõi ingress/egress, token scope, collector drift và lag.
- Ghi lại thay đổi runtime và mọi deviations.

**Giai đoạn 3 — sau deploy**

- Đối chiếu event counts và source coverage trong kỳ chuyển.
- Thực hiện detection regression và alert delivery tests.
- Xác minh không còn unauthorized permissions hoặc secrets ở đường cũ/mới.
- Thực hiện fallback test nếu chưa có evidence thực tế đủ.
- Review incident/ticket và quyết định đóng CR hoặc mở remediation.

### 17.4. Ma trận test và bằng chứng

| Test ID | Điều cần đạt | Phương pháp | Evidence |
|---|---|---|---|
| **T01 Population** | Cả hai clusters và mọi Critical audit sources đã được inventory/reconcile. | So API resources, logging baseline, source register. | Inventory snapshot, query/version, scope approval. |
| **T02 Event generation** | Event mẫu từ mỗi cluster xuất hiện ở nguồn và pipeline. | Authorized canary hoặc audit test được phép. | Raw event ID, source timestamps, ingest refs. |
| **T03 Schema** | Actor, verb, target, outcome không bị mất/đổi sai. | Parser regression fixtures và xem raw/normalized. | Before/after schema, fixture results. |
| **T04 Detection** | Một security use case ưu tiên tạo alert đúng route. | Positive/negative rule tests, kiểm tra case. | Rule version, event-to-alert-to-case timeline. |
| **T05 Consistency** | Không có missing critical event do rollout hoặc xử lý theo quy tắc đã duyệt. | Reconcile counts, duplicate, lag và buffer health. | Metrics, error log, reconciliation record. |
| **T06 Least privilege** | Collector chỉ truy cập nguồn/destination cần thiết. | IAM effective permission review, denied access test. | IAM config, negative test, audit. |
| **T07 Fallback** | Có thể quay lại đường cũ trong giới hạn và không mất dữ liệu vượt ngưỡng. | Authorized rollback rehearsal, queue consistency check. | Runbook, timestamps, event reconciliation. |
| **T08 Post-change health** | Source coverage và collector health vẫn ổn định theo window. | Continuous monitoring và alert fail-source. | Health trends, alerts, owner acknowledgement. |

### 17.5. Ví dụ kết quả

Giả sử:

- order-prod-a: T01–T08 đạt trong scope.
- order-prod-b: collector đã triển khai nhưng parser bỏ mất trường **actor.id** của một loại audit event.
- T04 cho một technique tại cluster B không tạo alert vì rule cần actor.id.
- T05 phát hiện khoảng 12 phút ingestion không rõ độ đầy đủ.

**Không được đóng CR là PASS chỉ vì cả hai deployment jobs succeeded.**

Cách xử lý:

1. **Block rollout/closure**; cân nhắc quay về parser/collector đã biết tốt hoặc forward-fix có kiểm soát.
2. Lưu raw evidence về actor.id missing, rule miss và 12 phút gap.
3. Đánh giá ảnh hưởng tới phát hiện các hành vi xảy ra trong khoảng đó.
4. Mở findings cho schema/detection, source completeness; xác định owner và severity.
5. Sửa parser, chạy negative/positive tests, đối chiếu source/alert end-to-end.
6. Quyết định cập nhật conclusion theo phạm vi và kỳ mới, không “tẩy” gap lịch sử.

### 17.6. Claim sau khi retest

> Trong phạm vi hai production clusters được ghi trong inventory và sau khi sửa parser, các event privileged audit được thử đã được sinh, ingest và tạo alert/case theo tiêu chí đã duyệt. Đánh giá tháng 11 có một khoảng mất visibility 12 phút cần ghi rõ, và kết luận không áp dụng cho các event types chưa được test.

Câu này **thận trọng và audit được**, khác với “hệ thống logging đã an toàn 100%”.

## 18. Ví dụ thứ hai: cập nhật IAM permissions phục vụ integration

### 18.1. Bối cảnh

Một SaaS analytics cần nhận purchase events. Một requestor đề nghị mở IAM permissions từ chỉ gửi events sang **đọc tất cả customer records** để “đơn giản hóa tích hợp”. Điều này có thể vượt mục đích xử lý dữ liệu và tăng blast radius khi token lộ.

**Risk:** excessive permissions, unauthorized data access, data leakage qua vendor, khó thu hồi khi offboarding.

### 18.2. Cách đánh giá và thiết kế lại

- Xác định dữ liệu thực sự cần: event ID, timestamp, order status, data classification.
- Phân biệt **send-only event** với **read-all customer data**.
- Thiết kế proxy/schema allowlist để giảm dữ liệu, thay vì cấp quyền rộng.
- Xác định principal, token lifetime, secret storage và region/tenant.
- Xem contract/subprocessor và privacy implications.
- Kiểm tra API requests ngoài scope bị từ chối và có audit.
- Kiểm tra rotation/revocation và compatibility với event pipeline.
- Có rollback/disable egress và alert bất thường.

### 18.3. Acceptance criteria

| Claim | Expected | Evidence |
|---|---|---|
| API principal chỉ có scopes đúng mục đích. | Effective permissions không cho read-all customers. | IAM snapshot, policy evaluator và denied call. |
| Payload chỉ gồm fields được phê duyệt. | Extra PII không ra khỏi proxy. | Schema allowlist, synthetic output, DLP review. |
| Token không được log hoặc commit. | Không xuất hiện trong build/log artifacts. | Secret scan, config/review, access-limited evidence. |
| Khi vendor lỗi, checkout không ngừng. | Queue/circuit breaker và test degrade hoạt động. | Functional failure injection, retry/backlog metrics. |
| Offboarding có thể thực hiện. | Revocation và data-flow stop đã thử. | Revoke test, blocked requests, inventory. |

**Risk owner** không nên phê duyệt tăng quyền vượt scope chỉ vì integration cần tiến độ nhanh, đặc biệt nếu nghĩa vụ hợp đồng hoặc privacy không cho phép.

## 19. Emergency configuration updates

Trong incident response, đôi khi không thể chờ quy trình normal change đầy đủ. Tuy nhiên cần **emergency governance được định nghĩa trước**.

### 19.1. Những yêu cầu tối thiểu

1. Trigger thực sự khẩn cấp và có người quyết định theo thẩm quyền.
2. Phạm vi hẹp nhất, thời hạn ngắn nhất, ghi rõ lệnh/config được áp.
3. Nếu có thể, giữ reviewer thứ hai hoặc approval đồng thời có audit.
4. Bảo vệ logs và evidence, đặc biệt khi thay đổi nguồn telemetry.
5. Có plan revert/containment để không tạo backdoor lâu dài.
6. Theo dõi security/availability trong lúc thay đổi.
7. Hậu kiểm trong thời hạn policy với root cause, residual risk và findings.
8. Chuyển về normal baseline hoặc tạo exception time-bound đúng quy trình.
9. Không dùng nhãn “emergency” để hợp thức hóa việc bỏ nghĩa vụ pháp lý/hợp đồng.

### 19.2. Ví dụ

Incident nghi lộ service credential. Đội vận hành phải thu hồi token và tạo credential mới:

- Ghi credential ID, actor, thời điểm và phương thức thu hồi.
- Kiểm tra mọi consumer nhận credential mới trước/sau theo thứ tự phù hợp.
- Chặn quyền cũ ở những đường cần được chặn ngay.
- Đánh giá delayed jobs, active sessions và traffic dùng credential cũ.
- Bảo vệ audit trail và truy vết những request trước/sau.
- Hậu kiểm secret lifecycle và kiểm tra thêm xem pipeline có nguồn lộ hay không.

**Không đưa giá trị secret vào evidence package hoặc ticket**. Chỉ dùng ID, metadata và proof of revocation dưới quyền truy cập phù hợp.

## 20. Findings, exceptions và remediation sau thay đổi

### 20.1. Các loại kết luận

| Kết quả | Ý nghĩa | Việc cần làm |
|---|---|---|
| **PASS trong scope** | Control có evidence đủ theo acceptance criteria, đúng targets, đúng kỳ. | Lưu hồ sơ và monitoring. |
| **FAIL** | Có bằng chứng hợp lệ về criterion không đạt. | Stop/escalate, finding, rollback/fix, retest. |
| **PARTIAL** | Một số targets/case đạt, phần khác chưa đáp ứng. | Ghi phạm vi rõ, xử lý những phần còn lại. |
| **INCONCLUSIVE** | Không đủ evidence về population, hiệu lực, nguồn hoặc test. | Thu thêm dữ liệu, không coi là PASS. |
| **NOT_APPLICABLE** | Criterion không áp dụng có căn cứ và phê duyệt phù hợp. | Ghi rationale và trigger review. |
| **APPROVED_EXCEPTION** | Gap được quản lý qua quyết định có hạn trong thẩm quyền. | Theo dõi conditions/expiry; **không tự đổi control FAIL thành PASS**. |

Một thay đổi có thể **triển khai được nhưng assurance fail**. Hệ thống cần phản ánh cả technical deployment status và security verdict riêng.

### 20.2. Finding record mẫu

~~~yaml
finding_id: CHG-2026-047
change_id: CR-2026-081
control_id: CTRL-DET-003
asset: "order-prod-b"
criterion: "Privileged API audit events must retain actor identity"
condition:
  observed: "Parser mapping drops actor.id for event type X"
  first_seen_utc: "2026-11-28T10:00:00Z"
  assessment_period: "2026-11-28 rollout window"
evidence:
  - EV-RAW-AUDIT-018
  - EV-PARSER-DIFF-004
  - EV-ALERT-NEGATIVE-007
status: OPEN
risk:
  scenario: "Privilege changes may not be detected/attributed"
  severity: high
root_cause:
  status: investigating
owner: detection-platform
remediation:
  action: "Correct parser and validate raw-to-alert mapping"
  acceptance: "Actor field retained; positive/negative tests pass"
  due_at: "2026-12-02T00:00:00Z"
retest:
  result: pending
  reviewer: security-assurance
~~~

Đây là **dữ liệu giả định**. Không đóng finding chỉ vì parser code đã merge; phải xác minh effective state, alert behavior và kiểm tra dữ liệu gap trong phạm vi có thể.

## 21. Evidence package của configuration update

### 21.1. Cấu trúc gợi ý

~~~text
security-assurance/change/CR-2026-081/
  request-and-impact.md
  control-requirements-and-policy-versions.md
  architecture-and-dependency-map.md
  authority-approvals.md
  change-diff-and-artifact-digest.txt
  rollout-plan-and-abort-criteria.md
  baseline/
    effective-state-before.json
    source-health-before.json
  validation/
    static-and-policy-as-code-results.json
    positive-negative-test-results.json
    canary-and-rollout-timeline.csv
    effective-state-after.json
    source-health-and-alert-test.json
  recovery/
    rollback-or-forward-fix-runbook.md
    authorized-rollback-test.json
  risk-and-findings/
    issues-and-exceptions.csv
    remediation-and-retest.json
  assurance/
    claim-argument-evidence.md
    evidence-index.csv
    reviewer-verdict-and-limitations.md
~~~

Bố cục minh họa; không bắt buộc tạo đúng các file này. Evidence có thể lưu trong GRC, CI/CD, SIEM và ticket system; cần **quyền truy cập và retention** phù hợp.

### 21.2. Metadata quan trọng

Một evidence record nên có:

- Change ID, asset/control/test IDs và assessment run.
- Source, collector, query/tool/parser và version.
- Commit SHA/config digest hoặc artifact identity.
- Mốc thời gian UTC, phạm vi, tenant/account/cluster/region.
- Expected, actual, pass/fail/inconclusive và người đánh giá.
- Raw-to-derived transformation, completeness, sampling và timezone.
- Evidence classification, access control và provenance/integrity.
- Link tới finding, exception, reviewer decision và retest.

Một log có hash đúng **không chứng minh log source đã đầy đủ**. Một screenshot được lấy sau rollout **không chứng minh trạng thái liên tục trong toàn kỳ**. Bằng chứng phải khớp loại claim.

## 22. Metrics cho chương trình change assurance

| KPI | Định nghĩa minh họa | Điều cần tránh |
|---|---|---|
| **Changes with approved risk review** | Số thay đổi thuộc scope đã có risk review và approval hợp lệ / tổng thay đổi yêu cầu. | Đếm approval sai cấp là đạt. |
| **Pre-change validation coverage** | Số changes có đủ test/policy results theo risk tier / tổng cần kiểm tra. | Tính pipeline success dù test bị skip. |
| **Effective-state verification rate** | Số targets được xác minh đúng effective config / tổng targets áp dụng. | Dùng deployment success làm numerator. |
| **Security regression rate** | Số changes gây security criterion failure / tổng changes có evaluation đủ. | Bỏ unknown khỏi mẫu số khiến rate thấp giả. |
| **Drift detection latency** | Thời gian từ drift phát sinh tới khi được nhận diện. | Không xét source health và missing telemetry. |
| **Rollback/forward-fix success** | Những change failures có phục hồi được kiểm chứng trong objective. | Chỉ đo revert commit, bỏ data integrity. |
| **Critical change evidence completeness** | Tỷ lệ high-risk changes có approved diff, test, runtime evidence, verdict. | Nhiều file nhưng không phù hợp scope. |
| **Change-induced incidents** | Incident liên quan change theo root cause/impact khi có thể xác minh. | Kết luận nhân quả chỉ dựa vào thời gian gần nhau. |
| **Exception aging** | Ngoại lệ config lệch baseline quá hạn hoặc gia hạn nhiều lần. | Phê duyệt ngoại lệ được coi là control pass. |
| **Mean time to remediate failed changes** | Thời gian từ confirmed failure đến retest closed. | Đóng ticket mà chưa test. |
| **Out-of-band changes** | Changes ngoài đường approved workflow phát hiện trong kỳ. | Không thấy event do logging bị lỗi rồi ghi 0. |
| **Source-health coverage** | Tỷ lệ nguồn monitoring đủ khả năng quan sát change/detection. | Coi “không có cảnh báo” là health pass. |

### 22.1. Không biến metric thành mục đích

Nếu nhóm bị đánh giá chỉ theo “change success 100%”, họ có thể:

- Đánh dấu success dù post-change tests chưa chạy.
- Không khai báo changes nguy hiểm để tránh phê duyệt.
- Đưa assets khó sang “out of scope”.
- Dùng exception không hết hạn.
- Che rollback và deployment failures.
- Giảm negative tests để tỷ lệ PASS cao.

Một chương trình trưởng thành công bố **gaps, unknowns, rollback, findings và residual risk** cùng success rate.

## 23. Bài tập thực hành

Một đội vận hành chuẩn bị thay API gateway configuration cho dịch vụ thanh toán Critical. Thay đổi gồm:

- Chuyển JWT issuer sang IdP mới.
- Bật cache public key/JWKS theo cách mới.
- Thay accepted audiences của token.
- Giới hạn quyền truy cập admin APIs.
- Tăng rate limit trong giai đoạn cao điểm.
- Đổi log field mapping và alert rule.
- Deployment rollout theo 3 regions.

Trong staging, functional tests đều pass. Trong canary region A, một service account cũ vẫn gọi được admin endpoint nhờ audience cũ; region B không nhận log của một loại token rejection; region C chưa deploy.

**Yêu cầu:**

1. Viết change request với mục tiêu, phạm vi, dependencies, approval và risk classification.
2. Xác định ít nhất năm threat scenarios, gồm auth bypass, excessive privileges, token validation failure, log gap và rate-limit impact.
3. Phân biệt desired, deployed và effective state cho ba regions.
4. Đề xuất negative tests cho issuer, audience, expired token, signature/key rotation, admin authorization và direct bypass.
5. Vì sao functional tests pass không cho phép kết luận security acceptance?
6. Xây dựng bảng population gồm 3 regions và trạng thái PASS/FAIL/NOT_DEPLOYED theo từng criterion.
7. Nêu vì sao log source missing ở B là INCONCLUSIVE hoặc FAIL tùy tiêu chí, không được coi là “không có token rejection”.
8. Đề xuất abort criteria và phương án rollback/forward-fix khi IdP mới không tương thích.
9. Liệt kê evidence cần lưu từ CI, deployment, runtime, IdP, API gateway và alert/case.
10. Xác định ai có thẩm quyền phê duyệt thay đổi và chấp nhận residual risk đối với một dịch vụ Critical.
11. Viết một finding cho audience cũ còn được chấp nhận, kèm root cause chưa xác minh, owner, deadline và retest.
12. Sau khi sửa, thiết kế post-change assurance argument chứng minh các đường token validation đang được enforce trong scope.

### 23.1. Gợi ý cách đánh giá

- **Region A:** có bằng chứng một đường admin endpoint chấp nhận audience không còn được phép; đây là **FAIL** cho criterion tương ứng nếu policy thực sự cấm.
- **Region B:** thiếu audit event bắt buộc; nếu đã chứng minh source mapping sai thì **FAIL**, còn nếu chưa đủ evidence để biết event được sinh/ingest thì **INCONCLUSIVE** cùng gap.
- **Region C:** chưa deploy; không thể tính là post-change PASS.
- **Top claim:** “Cấu hình mới đã được triển khai an toàn trên cả ba regions” **chưa được hỗ trợ**.
- **Action:** dừng mở rộng, điều tra audience validation và logging pipeline, sửa và retest, rồi đánh giá lại decision theo scope.

## 24. Checklist Configuration update assurance

- [ ] Change có ID, owner, business/security rationale và nguồn requirements.
- [ ] Đã chốt system boundary, asset inventory, population, environments, regions và kỳ.
- [ ] Before/after config và dependencies được version, có digest/reference phù hợp.
- [ ] Đánh giá threat/data-flow/IAM/network/crypto/logging/DR impact.
- [ ] Risk tier, risk owner, approval authority và SoD được xác minh.
- [ ] Legal/compliance/vendor obligations được xem khi phạm vi thay đổi liên quan.
- [ ] Có acceptance criteria rõ cho security, functionality, availability, data integrity và observability.
- [ ] Pre-change syntax/schema, static checks, secret scan, IaC plan và policy tests được dùng theo risk.
- [ ] Test plan bao gồm positive, negative, boundary, failure và recovery scenarios thích hợp.
- [ ] IaC/GitOps diff được review với chú ý semantic, defaults, selectors và inheritance.
- [ ] Artifact provenance và deployment identity có thể truy vết về approval.
- [ ] Rollout theo blast radius phù hợp; canary/stage có stop criteria.
- [ ] Đã phân biệt desired, deployed và effective state trên mọi target.
- [ ] Runtime verification kiểm tra effective permissions, routes, security controls và app behavior.
- [ ] Monitoring/alert/source health có đủ coverage trước, trong và sau rollout.
- [ ] Rollback/forward-fix plan xử lý keys, secrets, schema, dữ liệu và dependencies.
- [ ] Không dùng Git revert như bảo đảm phục hồi cho change không thể đảo.
- [ ] Không dùng approved exception làm bằng chứng control đã đạt.
- [ ] Evidence có source, timestamp, version, target, result, provenance và limitations.
- [ ] FAIL/PARTIAL/INCONCLUSIVE được giữ riêng, không gộp thành success.
- [ ] Có finding/remediation owner và retest khi phát hiện lệch yêu cầu.
- [ ] Change close chỉ sau post-change verification và reviewer decision.
- [ ] Continuous drift detection và trigger đánh giá lại đã được thiết lập.
- [ ] Metric/reporting công bố cả security coverage, data quality và remaining risk.

## 25. Câu hỏi tự đánh giá

1. Vì sao một thay đổi chỉ có một dòng YAML vẫn có thể được phân loại high-risk?
2. Desired state, deployed state và effective state khác nhau ở đâu?
3. Một CI job PASS có thể bỏ sót loại rủi ro configuration nào?
4. Vì sao cần đối chiếu asset/cluster/account inventory độc lập với deployment targets?
5. Khi nào negative authorization test có giá trị hơn một ảnh IAM policy?
6. Một Kubernetes manifest đã cài securityContext có tự chứng minh workload đang chạy với privilege mong muốn không?
7. Những giả định nào khiến revert Git không đủ để rollback key rotation hoặc database migration?
8. Khi thay log collector, test nào chứng minh actor/target không bị mất qua parser?
9. Vì sao rollout canary ở một tenant không chứng minh tất cả tenant có cùng config và data flow?
10. Một exception đã phê duyệt có thể biến một control không đạt thành control PASS không?
11. Khi external vendor đổi data processing region, change assurance cần review thêm những gì?
12. Một thay đổi network rule có thể tăng blast radius qua label selector hoặc policy priority thế nào?
13. Cần bằng chứng nào để chứng minh log pipeline healthy trong kỳ rollout, không chỉ sau rollout?
14. Khi nào phải chọn forward-fix thay vì rollback?
15. Risk owner, change authority, security reviewer và control owner có vai trò khác nhau như thế nào?
16. Hãy thiết kế test để phát hiện IAM permissions tăng ngoài scope sau một update.
17. Nếu ba cloud regions deploy không đồng đều, report nào là trung thực nhất?
18. Hãy tạo một finding cho config drift ngoài GitOps và định nghĩa acceptance criteria để đóng.
19. Viết một assurance claim có scope, 4–5 subclaims và evidence tương ứng cho một config change thực tế.
20. Đề xuất dashboard gồm effective-state verification, security regression, unknowns, remediation và source health.

**Điểm cốt lõi:** **Configuration update không an toàn chỉ vì đã được phê duyệt, merge hoặc deploy thành công.** Trong security assurance, phải chứng minh rằng cấu hình thay đổi **đúng nguồn yêu cầu, đúng đối tượng, đúng quyền, được kiểm thử trong các kịch bản rủi ro, có evidence về trạng thái thực, vẫn duy trì telemetry và có đường xử lý thất bại**. Việc ghi nhận mọi thay đổi, gap, exception, findings và retest tạo nên vòng **change assurance liên tục** giữa phát triển và vận hành.
