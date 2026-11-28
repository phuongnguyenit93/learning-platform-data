# Cloud security assurance – Đánh giá có bằng chứng mức bảo đảm an ninh trên môi trường đám mây

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **cloud security assurance** và phân biệt với cloud security, cloud compliance, cloud posture monitoring, penetration testing và kiểm toán một lần.
- Phân định **shared responsibility**, control ownership và các controls được kế thừa/đồng quản lý trên IaaS, PaaS, container platform, serverless và SaaS, tránh hiểu nhầm “nhà cung cấp chịu hết”.
- Xây dựng **assurance claim** có scope, risk, security objective, requirement, control, test, evidence, limitation và confidence.
- Xác định assets trên nhiều cloud accounts/projects/subscriptions, regions, workloads và identities; nhận biết **ephemeral resources, shadow cloud, asset drift** và missing telemetry.
- Mô hình hóa trust boundaries giữa user, identity provider, API, cloud control plane, data plane, network, storage, KMS, CI/CD và service-to-service.
- Đánh giá các nhóm controls về IAM, workload federation, least privilege, networking, encryption/key management, backup, logging, configuration, supply chain và incident response.
- Tổ chức **policy-as-code, configuration assessment, runtime verification, drift detection và continuous control monitoring** để tránh “đạt một lần rồi quên”.
- Phân biệt evidence về **thiết kế, triển khai và operating effectiveness**; biết xử lý stale, incomplete, contradictory và provider-derived evidence.
- Thiết kế risk-based coverage metrics, requirement/test catalog, report và finding remediation; không coi “CSPM xanh” hoặc “SOC 2 report có sẵn” là bằng chứng mọi objective đã đạt.
- Thực hành với ví dụ Rego/policy-as-code, Java 17/JUnit, YAML evidence register và các case study của hệ thống Java/Spring Boot trên cloud.

## 1. Cloud security assurance là gì?

**Cloud security assurance** là chương trình **đánh giá và duy trì bằng chứng** cho thấy môi trường, workload và cách vận hành đám mây đáp ứng **các mục tiêu bảo mật đã xác định**, ở một thời điểm/phạm vi cụ thể và trong quá trình thay đổi liên tục.

Cloud security bao gồm việc **thiết kế và vận hành** các controls như IAM, encryption, network segmentation, monitoring, backup. Cloud security assurance đặt câu hỏi khác:

> “Bằng chứng nào đủ tin cậy để kết luận đúng controls đã được triển khai, có hiệu lực trên tài sản và dữ liệu thực tế, đang tiếp tục hoạt động, và phần nào chưa thể xác nhận?”

Ví dụ, kiến trúc ghi “S3 bucket private” hoặc “object storage không được public”. Để có assurance, cần hơn một diagram:

1. Xác định **bucket/account/project/region** và data classification.
2. Xem effective public access policy ở cấp resource, account/organization, ACL hoặc các lớp tương đương mà cloud đó có.
3. Kiểm tra access paths qua application, signed URL, identity và network theo policy.
4. Đối chiếu runtime configuration và thay đổi gần đây với baseline.
5. Thực hiện **negative access tests an toàn** bằng các test principals và synthetic objects được cho phép.
6. Xác định logging và alert khi cấu hình bị thay đổi ngoài chính sách.
7. Ghi evidence timestamp, nguồn, revision, assessor, gap/limitation và owner.

Tuyên bố “bucket private” chỉ **đạt trong scope** khi bằng chứng phù hợp với các đường truy cập và yêu cầu cần chứng minh. Một rule CSPM báo PASS không tự chứng minh ứng dụng không thể tạo **signed download URL quá rộng** hoặc data bị lộ qua API.

### Trong module SECURITY_SECURITY_ASSURANCE

Module này học cách thiết lập **security objectives, risk assessment, controls, tests, audit và khắc phục findings** trên toàn bộ vòng đời phát triển/vận hành. Cloud security assurance đưa tư duy đó vào môi trường có API quản trị tập trung, tài sản thay đổi nhanh, dịch vụ managed và trách nhiệm chia sẻ giữa nhiều bên.

**Công thức tư duy:**

~~~text
Cloud assurance =
  scoped risk/objective/requirement
  + control ownership and effective design
  + implementation/operation verification
  + trusted evidence with freshness and coverage
  + finding, exception, remediation and retest
  + reassessment when cloud conditions change
~~~

Không có một tỷ lệ hoặc sản phẩm nào tự động chứng minh được toàn bộ hệ thống “an toàn”.

## 2. Phân biệt những thuật ngữ dễ nhầm

| Thuật ngữ | Trả lời câu hỏi | Không tự chứng minh |
| --- | --- | --- |
| **Cloud security architecture** | Controls và trust boundaries được thiết kế thế nào? | Controls đã chạy đúng trên runtime |
| **Cloud security engineering** | Cấu hình, triển khai và vận hành bảo vệ ra sao? | Bằng chứng hiệu lực và coverage đã đầy đủ |
| **Cloud security assurance** | Có chứng cứ phù hợp rằng objectives được đáp ứng trong scope? | Không còn bất kỳ rủi ro nào |
| **Cloud compliance** | Có đáp ứng các yêu cầu chuẩn/quy định/hợp đồng áp dụng? | Một system không thể bị khai thác |
| **CSPM** (cloud security posture management) | Tài nguyên cloud có sai lệch cấu hình/rule không? | Business authZ hay data exposure qua app |
| **CWPP** (cloud workload protection) | Workload/host/container có tín hiệu rủi ro runtime? | Mọi cloud controls và business requirements |
| **CIEM** (cloud infrastructure entitlement management) | Effective cloud permissions quá rộng/unused? | Quyền được enforce đúng cho từng business object |
| **CNAPP** (cloud-native application protection platform) | Tập hợp posture/workload/identity/code signals | Tự động hoàn thành assessment có thẩm quyền |
| **Cloud pentest/DAST** | Một số attack paths có thể vượt boundary không? | Toàn bộ cloud population đã kiểm |
| **Cloud provider audit report** | Nhà cung cấp có control assertions cho scope/thời kỳ báo cáo? | Tenant/customer configuration của bạn đúng |
| **Control monitoring** | Control/state có thay đổi hoặc thất bại không? | Control phù hợp với mọi risk scenario |

Tên sản phẩm và khả năng cung cấp có thể thay đổi theo nhà cung cấp; bài học chỉ sử dụng khái niệm phổ quát. Khi áp dụng, kiểm tra tài liệu dịch vụ và evidence policy thực tế.

## 3. Shared responsibility: phân định trách nhiệm đúng

### 3.1. Trách nhiệm thay đổi theo service model

Mô hình chia sẻ trách nhiệm thường phân biệt:
- **Cloud provider:** các thành phần provider thực sự vận hành, ví dụ một phần datacenter, cơ sở hạ tầng vật lý và service platform.
- **Cloud customer:** dữ liệu, identities, application code, cấu hình được phép thay đổi, access, service usage, monitoring và các controls thuộc quyền mình.
- **Shared/co-managed:** một số hoạt động phụ thuộc model/service/config, ví dụ patching, encryption, recovery, logging, networking.
- **External partners/vendors:** IdP, SaaS, CDN, third-party CI, support channel và subprocessors với hợp đồng/quyền riêng.

**Không có một ma trận bất biến cho mọi IaaS/PaaS/SaaS.** Cần đọc **shared-responsibility documentation của dịch vụ cụ thể** và xác định từng control activity, không suy từ nhãn “managed”.

### 3.2. Ma trận khái niệm

| Control domain | IaaS VM | Managed PaaS/database | SaaS |
| --- | --- | --- | --- |
| Datacenter vật lý | Chủ yếu provider | Chủ yếu provider | Chủ yếu provider |
| Guest OS/package patch | Thường customer | Tùy dịch vụ/provider và version choices | Thường provider |
| Application code | Customer | Customer với app do họ triển khai | Chủ yếu vendor; customer vẫn cấu hình tích hợp |
| Identity, roles và access | Customer | Customer cho các roles/permissions được cấu hình | Customer cho tenant accounts/SSO/sharing |
| Dữ liệu và classification | Customer | Customer | Customer vẫn sở hữu nghĩa vụ dùng/chia sẻ dữ liệu |
| Storage encryption | Provider platform + customer choices | Service-specific shared | Contract/service-specific; customer có settings |
| KMS/key lifecycle | Tùy khóa do provider/customer quản lý | Service-specific | Phụ thuộc tích hợp và hợp đồng |
| Network policies | Customer VPC/security group/host | Service networking/customer connectors | Customer access/network configuration khi có |
| Backup/restore | Customer design/operation | Managed capabilities + customer policy | Contract/vendor capability + customer contingency |
| Audit logging | Provider events + customer log enable/retention | Service-specific | Customer tenant audit logs + vendor evidence |
| Incident response | Provider xử lý platform scope | Chia sẻ/handoff | Vendor + customer theo dữ liệu/tài khoản |
| Security assurance | Customer kiểm phần mình và đánh giá evidence provider | Customer xác minh phần control áp dụng | Customer làm vendor/tenant/control assurance |

Đây là mô hình học tập; việc gán cụ thể phải dựa trên **dịch vụ và contract**.

### 3.3. Control inheritance không phải bằng chứng vô điều kiện

Một tổ chức có thể **kế thừa assurance** từ provider cho control thực sự do provider quản lý. Nhưng phải xác định:
- Provider report/service scope có bao phủ đúng service/region của workload?
- Reporting period có phù hợp thời điểm đánh giá?
- Report có ngoại lệ, qualifications hoặc carve-outs nào?
- Provider control có phụ thuộc **Complementary User Entity Controls (CUECs)** hay customer controls khác?
- Khóa, logs, network hoặc identity options mà khách hàng phải cấu hình đã được kiểm chưa?
- Có subservice organizations hay third-party dependencies bên ngoài report?
- Những nội dung nào provider không cung cấp observability trực tiếp?
- Rủi ro và obligations nào vẫn thuộc khách hàng?

**Provider có chứng nhận không đồng nghĩa tenant của bạn đạt yêu cầu.** Một provider có thể triển khai encryption at rest cho managed storage nhưng người dùng vẫn cấp public access hoặc ứng dụng gửi dữ liệu ra ngoài thông qua endpoint khác.

### 3.4. RACI control ownership mẫu

| Hoạt động | Cloud/platform team | App team | Security/AppSec | Risk/GRC | Provider |
| --- | --- | --- | --- | --- | --- |
| Account/project baseline | Responsible | Consulted | Reviewer | Accountable theo policy | Cung cấp platform |
| App authorization | Support | Responsible | Assessor | Risk owner khi sai lệch | Không quyết business authZ |
| Key usage/policies | Platform + service owner | Implementer | Reviewer | Governance | Quản lý hạ tầng KMS theo service |
| Cloud audit logs | Platform/SRE | Consume | Detection owner | Assurance | Phát sinh service events theo khả năng |
| Provider controls | Tiếp nhận evidence | Đánh giá dependencies | Assessor | Vendor/compliance owner | Control operator |
| Exception approval | Recommend/operate | Remediation owner | Risk assessor | Authorized risk owner | Không tự approve customer risk |
| Retest/finding closure | Runtime evidence | Fix + tests | Independent review | Record oversight | Cung cấp evidence trong scope |

**RACI phải chi tiết theo từng requirement**, không chỉ nói chung “cloud team chịu trách nhiệm”.

## 4. Assurance claim và evidence chain

### 4.1. Claim – Argument – Evidence

Một cách tổ chức assessment là:

- **Claim:** điều muốn khẳng định, có scope và thời điểm.
- **Argument:** vì sao controls và verification methods đủ để hỗ trợ claim.
- **Evidence:** artefacts/observations có nguồn, thời gian, identity và trust.
- **Limitations:** phần chưa chứng minh, assumptions, data gaps và residual risk.
- **Decision:** PASS/FAIL/INCONCLUSIVE theo acceptance criteria đã duyệt.

Ví dụ:

> “Các production object storage buckets chứa báo cáo khách hàng, trong accounts và regions X tại thời điểm T, không cho principal ngoài approved policy đọc đối tượng; các thay đổi public access bị phát hiện trong thời gian đã quy định.”

Để hỗ trợ claim, có thể cần:
- Asset inventory và data classification.
- Effective resource/account/org access policies.
- IAM role/identity inventory và actual principal paths.
- Negative tests với **test object/principal** trong môi trường cho phép.
- Configuration/drift detection coverage.
- Log source-health và alert-test evidence.
- Exclusions, inherited controls và reviewer sign-off.

**Claim scope phải đúng với evidence scope.** Kiểm một bucket test trong account A không đủ nói tất cả buckets production ở accounts B/C đều đạt.

### 4.2. Mối liên hệ risk → control → test

~~~text
RISK CLOUD-R01:
  Sensitive report object may be accessed without authorization
  -> OBJECTIVE: Confidentiality and tenant isolation
  -> REQUIREMENT: Object access only through approved identities/routes
  -> CONTROLS: Private policy, role scoping, encryption, signed-URL policy
  -> TESTS: Effective-policy check, negative access test, API authZ test
  -> EVIDENCE: Bucket/account/resource identity + policy revision
               + test object/principal + runtime test + log IDs
  -> FINDING: Unexpected external read / access path if observed
  -> REMEDIATION: Tighten policy, remove bypass, rotate affected access
  -> RETEST: Repeat same deny scenario on deployed state
  -> MONITOR: Public policy changes, role changes, new buckets
  -> ASSURANCE: Scoped PASS / FAIL / INCONCLUSIVE
~~~

### 4.3. Ba mức bằng chứng không được trộn

| Mức | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Design effectiveness** | Control có thiết kế đúng risk/requirement? | Architecture, threat model, policy definition |
| **Implementation effectiveness** | Đã triển khai control tại đúng tài sản? | Effective policy, enabled logs, key settings |
| **Operating effectiveness** | Control còn chạy và thực sự tạo behavior yêu cầu? | Deny test, alert exercise, restore test, evidence history |

Một IaC template có `block_public_access=true` chỉ là **ý định thiết kế/triển khai**, không đủ chứng minh resource production đã được cập nhật hoặc không có alternate access path.

## 5. Cloud architecture và trust boundaries

### 5.1. Kiến trúc tham chiếu

~~~mermaid
flowchart LR
    USER["Customer / partner"] --> EDGE["CDN / WAF / API gateway"]
    EDGE --> API["report-api / Spring Boot"]
    API --> DB["Managed database"]
    API --> OBJ["Object storage"]
    API --> Q["Message queue"]
    Q --> WORKER["Export worker"]
    WORKER --> OBJ
    IDP["Identity provider / Federation"] --> API
    STS["Cloud identity / STS"] --> API
    STS --> WORKER
    KMS["KMS / keys"] --> DB
    KMS --> OBJ
    CI["Git / CI / Artifact registry"] --> CD["Deploy automation"]
    CD --> API
    CD --> WORKER
    ORG["Cloud organization / accounts / policies"] -. "control plane" .-> API
    ORG -. "control plane" .-> OBJ
    LOG["Central audit / detection"] -. "events" .-> ORG
    LOG -. "events" .-> API
    LOG -. "events" .-> WORKER
~~~

Các trust boundaries có thể gồm:
1. Internet/partner → edge.
2. Gateway → application/data plane.
3. User identity → application authorization.
4. Workload identity → cloud API/STS.
5. App/worker → database, queue và object storage.
6. CI/CD → cloud deployment/control plane.
7. Root/org admin → accounts/projects/subscriptions.
8. Service/data plane → central audit/monitoring.
9. Customer configuration → provider-operated platform.
10. Region/account → region/account khác qua peering, replication và shared resources.

### 5.2. Cloud control plane và data plane

**Control plane:** APIs và identities tạo/xóa/sửa resources, IAM policy, network, encryption, logging, role binding, deployment. Một compromise ở đây có thể thay đổi toàn bộ posture.

**Data plane:** nơi requests thực sự xử lý, dữ liệu đọc/ghi, workloads thực thi, queues và storage vận hành.

Một IAM policy hoặc WAF rule nhìn “đúng” trên control plane **chưa đủ** chứng minh mọi data plane path đều được bảo vệ; ngược lại một endpoint API deny không chứng minh không thể thay policy qua privileged control plane identity.

### 5.3. Cloud-native threats cần đưa vào assurance

| Risk scenario | Trust boundary | Câu hỏi assurance |
| --- | --- | --- |
| Public object exposure | External principal → storage | Effective policy và signed URL có đúng scope? |
| Excessive workload permissions | Pod/function/VM → cloud API | Có least privilege, temporary credentials, condition? |
| Misconfigured federation | CI/OIDC principal → STS/role | Trust condition có bind issuer/audience/subject? |
| Account takeover | Human identity → control plane | MFA, conditional access, admin break-glass tests? |
| Data exfiltration path | App/worker → egress/storage | Egress controls và monitoring có bao phủ? |
| Unpatched image | Registry/CI → runtime | Signed/approved digest có đúng deployed workload? |
| Logging disabled | Admin/control plane → audit pipeline | Detection/alert trên config change có hiệu lực? |
| KMS misuse | Workload → key decrypt | Key policy, usage logs và rotation/revocation phù hợp? |
| Backup tampering | Production identity → backup vault | Immutable/separated recovery access có hiệu lực? |
| Cross-account trust | Principal account A → resource B | Resource/identity conditions có giới hạn? |
| Secret exposure | CI/config/app → logs/repository | Secrets có được ngăn, scan, rotate? |
| Region outage | Dependencies giữa regions | Recovery procedure được test theo RTO/RPO? |
| Metadata service misuse | Untrusted input → workload identity | SSRF boundary/metadata protections và IAM scope? |
| Tenant isolation error | User A → report B | Business authorization tests trên synthetic data? |

Threat models phải xét **bối cảnh của service**: dữ liệu nhạy cảm, actors, exposure, privileges và business impact. Không tất cả risks đều được một CSPM rule phát hiện.

## 6. Cloud inventory: lấy mẫu số đúng

### 6.1. Resource universe

Cloud resources có thể sinh/xóa trong vài phút:
- Accounts, management groups, organizations, folders, projects.
- Regions, availability zones, VPC/VNet, subnets, gateways.
- VMs, autoscaling groups, container clusters, nodes, pods, images.
- Functions, API gateways, load balancers, DNS records.
- Buckets, object versions, databases, caches, queues và event buses.
- IAM users, roles, groups, policies, service accounts, workload identities.
- KMS keys, secrets, certificates.
- CI/CD roles, registries, deployment pipelines.
- Backups, snapshots, logs, monitoring sinks và recovery environments.
- SaaS tenants/connected apps ngoài cloud account chính.

Nếu định nghĩa population bằng “assets đã được CSPM scan”, unmanaged accounts và disconnected regions bị bỏ khỏi mẫu số — chỉ số có thể **xanh giả**.

### 6.2. Nguồn inventory nên reconcile

| Nguồn | Thông tin mạnh | Giới hạn |
| --- | --- | --- |
| Organization/account APIs | Accounts, regions, hierarchy, ownership | Không tự thấy mọi app-level asset |
| Cloud resource inventory | Current resource IDs, tags, states | Có delay và service blind spots |
| Cloud billing/cost inventory | Shadow assets, subscription usage | Không đủ security metadata |
| IaC state/Git | Intended resources và policy | Drift hoặc manually created resources |
| Kubernetes API | Deployed workloads/pods/service accounts | Không bao phủ clusters chưa đăng ký |
| Registry/SBOM | Images/packages/artifacts | Registry image có thể chưa deploy |
| IdP/IAM audit | Principals, access/role changes | Không đủ effective permissions nếu thiếu trust/path |
| Network discovery/flow logs | Exposed services/traffic | Có sample/retention gaps |
| CMDB/service catalog | Owner, business criticality, data class | Thường lag so với actual cloud |
| Provider reports | Provider-controlled scope | Không thay customer tenant inventory |

### 6.3. Stable resource identity

Nên gắn:
`(provider, organization/account/project/subscription, region, resource type, resource ID, deployment/generation)`.

Không dùng mỗi hostname, IP, tag hoặc image tag làm khóa duy nhất:
- IP tái sử dụng; hostname có thể đổi.
- Resource name có thể được tạo lại với ID mới.
- Container image tag có thể trỏ tới digest khác.
- Một image digest có thể chạy trong nhiều clusters.
- Serverless có function version/alias, concurrency và execution role khác nhau.
- Kubernetes pod UID và controller template có ý nghĩa riêng.

### 6.4. Discovery gaps và ephemeral workload

- Resource xuất hiện nhưng chưa có owner → **unowned asset finding**.
- Resource biến mất trước lần scan → cần event/inventory history để biết đã tồn tại trong window.
- Account mới chưa onboard logging → **assurance coverage gap**, không phải “0 findings”.
- Region disabled trong dashboard nhưng có workloads → scope mismatch.
- Resource terminated có evidence có thể rời current snapshot, nhưng **historical incidents/evidence vẫn cần giữ**.
- Serverless function dùng alias trỏ tới version khác → kiểm actual invocation mapping, không chỉ source repository.

### 6.5. Data classification là một phần asset identity

Không thể ưu tiên cloud controls chỉ bằng resource type. Một storage bucket chứa ảnh công khai và một bucket chứa hồ sơ sức khỏe có risk khác nhau. Cần:
- Owner, data class, environment, exposure.
- Business function và downstream consumers.
- Security objective tương ứng.
- Applicable policy và regulatory/contract obligations.
- Retention, backup, replication và data residency.
- Các tenants và data access pathways.

**Unknown owner/classification** phải được đánh dấu để triage, không tự mặc định low risk.

## 7. Governance: cloud landing zone và security baseline

### 7.1. Tổ chức cloud hierarchy

Một landing zone thường hướng tới:
- Account/project/subscription separation theo environment, workload và ownership.
- Central identity/federation và privileged-access procedure.
- Organization-level guardrails/policy constraints nơi dịch vụ hỗ trợ.
- Network architecture và approved connectivity.
- Centralized audit logs/monitoring, encryption và retention.
- Baseline resource tags, ownership và data classification.
- Secure account vending/onboarding, IaC/policy checks.
- Resource lifecycle, budget, exception và decommission.
- Incident and recovery capabilities.

Nhưng **một “landing zone approved” không tự bảo đảm workload mới** nếu automation không áp đúng policy hoặc người dùng có quyền bypass.

### 7.2. Guardrail vs detective control

| Control | Loại | Assurance cần có |
| --- | --- | --- |
| Deny public storage policy via organization rules | Preventive | Effective scope, exception paths, negative create tests |
| Required encryption policy | Preventive/configuration | Deployment/effective key settings và restore semantics |
| CSPM rule phát hiện public resources | Detective | All accounts/regions covered, freshness và alert delivery |
| IaC PR policy gate | Preventive pre-deploy | Có ngăn bypass/direct cloud API? |
| Central audit logging | Detective/evidence | Events delivered, durable, protected, source-health |
| Auto-remediation | Corrective | Quyền hạn, safety, rollback, conflict với business |
| Privileged role review | Governance/preventive | Effective entitlements và approval history |
| Break-glass account | Resilience/control | Access limited, monitored, tested và recovered |
| Backup isolation | Recovery | Restore drill, permissions, integrity, recovery time |

Dùng **defense in depth**: preventive policies + detective posture + runtime behavior tests + incident response. Một control có thể giảm một phần risk nhưng không tự thay các controls khác.

### 7.3. Hạn chế của “default secure”

Cloud vendor có thể cung cấp default configuration theo phiên bản/tài khoản, nhưng:
- Defaults có thể khác theo ngày tạo resource và service generation.
- Config migration có thể giữ legacy settings.
- API/IaC overrides vẫn có thể đổi trạng thái.
- Control mới không tự bảo vệ resource cũ.
- Service edge cases, delegated admins hoặc service-linked roles có semantics riêng.

Do đó phải kiểm **effective configuration của resource và policy hierarchy**, không chỉ suy từ default docs.

## 8. IAM và cloud identity assurance

### 8.1. Human identities

Một control objective quan trọng: **chỉ những con người có thẩm quyền mới thực hiện được thao tác cloud tương ứng**, trong thời gian và context phù hợp.

Kiểm chứng cần xét:
- Central IdP, federation/SSO, provisioning/deprovisioning.
- Strong authentication/MFA với privileged và high-risk actions theo policy.
- Human roles/groups và permission sets thực sự gán.
- Least privilege, separation of duties, just-in-time access khi phù hợp.
- Administrator/root/break-glass identities, recovery và usage alerts.
- Long-lived API keys, dormant users và unowned roles.
- Conditional access, session length và step-up policy.
- External guests, contractors, support roles và expiration.
- Access reviews, ownership và audit evidence.

**“MFA enabled” là một thuộc tính, không đủ chứng minh quyền admin chỉ được dùng đúng lúc.** Cần kiểm permission assignments, bypass routes, break-glass lifecycle và actual events.

### 8.2. Workload identities

Application thường dùng cloud IAM để truy cập queues, storage, KMS, databases hoặc service APIs. Mục tiêu:
- Không hardcode cloud keys dài hạn trong image, Git, CI hoặc container environment.
- Ưu tiên workload identity, short-lived credentials và federation khi service hỗ trợ.
- Bind trust vào **issuer, audience, subject/namespace/service account/workflow** theo môi trường.
- Phân biệt **authentication** của workload với **authorization** tới resource và data scope.
- IAM role/session credentials có permissions tối thiểu, giới hạn resource/conditions.
- Lưu trust policy và effective permissions; test deny với identity ngoài scope.
- Rotation, revocation, incident response và audit identity issuance/use.

### 8.3. Ví dụ federation qua CI

Một CI pipeline nhận OIDC assertion để yêu cầu temporary credentials. Risk thường xuất hiện nếu trust chỉ kiểm issuer mà không giới hạn:
- Repository/workflow/ref/environment được duyệt.
- Audience và token type.
- Credential scope, expiry và role permissions.
- Artifact registry/environment mà pipeline được deploy.
- Security review cho reusable workflows và third-party actions.

**Đánh giá assurance:** mã IaC trust policy là design evidence, effective provider IAM policy là implementation evidence, test với untrusted PR identity bị **DENY** và logs/audit là operating evidence.

Không nên kết luận “không có static secret” đồng nghĩa federation hoàn toàn an toàn: trust conditions sai có thể cho phép untrusted workload nhận token quyền rộng.

### 8.4. Resource-based vs identity-based policy

Quyền effective có thể phụ thuộc **nhiều lớp**:
- Identity policy và group/role assignments.
- Resource-based access policy.
- Organization-level permission boundaries, constraints/deny rules.
- Session policy, conditions, service resource scope.
- Trust relationship giữa accounts/projects.
- Network controls (nếu có) và application-level authorization.

Vì vậy không kết luận quyền chỉ qua một JSON policy. Dùng effective-permission analysis, explicit deny tests với test principals và review **all reachable paths** theo platform semantics.

### 8.5. IAM evidence checklist

| Claim | Evidence cần có | Negative test mẫu |
| --- | --- | --- |
| Không có unowned privileged account | IAM inventory, owner records, access reviews | Account không owner không tự PASS |
| CI PR không thể deploy prod | Trust policy, workflow identity, deploy role | Untrusted PR principal bị deny |
| Worker chỉ đọc report objects | Workload role, bucket policy, key scope | Write ngoài prefix bị deny |
| Temporary credentials có expiry | Issuer/session settings, logs | Expired credentials không dùng được |
| Break-glass được kiểm soát | Account/role config, alert, drill | Unauthorized use bị phát hiện |
| Human access bị revoke khi nghỉ việc | IdP lifecycle, cloud session policy | Revoked user không còn effective access |

## 9. Network và cloud exposure assurance

### 9.1. Network boundaries

Cloud network posture không chỉ là một firewall rule:
- Public/private addresses và routes.
- VPC/VNet/subnets, gateways, NAT, peering/transit.
- Security groups/firewall policies, NACL và host firewall (tùy platform).
- Public-facing load balancer/API gateway, CDN/WAF.
- Private service endpoints và managed service network access.
- Kubernetes ingress/network policies và service mesh.
- Workload outbound egress, DNS và proxies.
- Hybrid VPN/direct connectivity và corporate network.
- Cross-region/account network paths.

Một instance không có public IP **vẫn có thể reachable từ Internet** qua public gateway/proxy. Ngược lại một cloud security group private có thể không che application authorization defect.

### 9.2. Đánh giá effective ingress và egress

| Claim | Test/evidence | Những điều dễ bỏ sót |
| --- | --- | --- |
| Admin port không public | Cloud network configs + safe connectivity deny test | LB, jump host, public proxy, rule inheritance |
| Database chỉ cho app workloads | Effective source/destination policy | Shared network/sidecar/route bypass |
| Export worker không gọi external APIs bất kỳ | Egress policy + mock-destination deny test | NAT, DNS, service mesh bypass |
| Private endpoint thực sự được dùng | DNS/route/runtime connection evidence | SDK vẫn đi tới public endpoint |
| WAF rule bảo vệ exposed API | Gateway config + behavior tests | Direct-to-origin, internal/async paths |
| K8s tenants/workloads cách ly | Network policy + namespace/service account tests | Node/host network bypass, CNI semantics |

**Proof boundary:** dùng controlled connectivity tests tới resources **sở hữu và được cấp quyền**, không thử probe cloud metadata endpoints hay mạng bên thứ ba để chứng minh egress policy.

### 9.3. Zero trust trong cloud

Zero trust là tư duy xác minh theo **identity, device/workload, resource, request context và policy**, không phải một sản phẩm. Assurance cần chứng minh:
- Requests đến resource nhạy cảm yêu cầu đúng principal.
- Identity/permission không được tin chỉ vì source IP/subnet.
- Controls còn hiệu lực khi workload di chuyển vùng mạng.
- Segmentation đi đôi server-side authorization.
- Cross-tenant/data access được kiểm tra ở tầng nghiệp vụ.
- Mọi quyền/delegation có review/revocation khi cần.

Một security group “restrictive” không thay object-level authorization; business data có thể bị lộ qua một API đã được phép đi qua network.

### 9.4. Monitoring exposure drift

Khi thêm ingress listener, DNS, peering, public LB, security group rule hoặc route mới:
- Refresh attack-surface inventory.
- Chạy policy-as-code và effective config verification.
- Xác định risk owner và data classification của target.
- Kiểm service/API authentication và authorization.
- Tạo finding nếu control không đạt.
- Đưa trigger vào continuous assurance, không chờ audit hằng năm.

## 10. Data protection, encryption và key assurance

### 10.1. Bảo vệ dữ liệu theo vòng đời

Các nhóm yêu cầu:
1. Phân loại dữ liệu và biết data owner.
2. Hạn chế ingest và location/data residency theo policy.
3. Authentication/authorization và least-privilege access.
4. Bảo mật dữ liệu **in transit** và **at rest** khi áp dụng.
5. Encryption keys, rotation/usage/revocation.
6. Backup, replication, snapshot và secure deletion.
7. Retention/lifecycle và access logging.
8. Privacy/PII redaction trong metrics, traces và audit logs.
9. Data export/download/signed URL policy.
10. Incident detection và response cho unauthorized access.

### 10.2. Encryption at rest không đủ để tuyên bố data secure

Encryption at rest bảo vệ một số loại rủi ro, nhưng nếu application role có quyền decrypt rồi gửi data ra public API, encryption không ngăn business-level leak.

Assurance cần phân biệt:
- Service-managed encryption vs customer-managed key options.
- Key policy và principals có quyền use/decrypt/rotate/disable.
- KMS grant/session behavior và audit logs.
- Key lifecycle, recovery và outage consequences.
- Key region/replication và cross-account access.
- Data classification có yêu cầu key separation không.
- Backup/snapshot/replica và logs có cùng protection objectives?
- Effective encryption state của resource hiện tại, không chỉ IaC flag.

### 10.3. Key-management evidence

| Claim | Evidence | Negative/failure test trong phạm vi |
| --- | --- | --- |
| Dữ liệu nhạy cảm mã hóa bằng approved key | Resource encryption config + key identity | Unapproved key/config bị policy deny |
| Chỉ workload được duyệt decrypt | Effective key policy, role binding, grants | Untrusted test principal bị deny |
| Key usage có audit | KMS logs, event delivery health | Synthetic key use sinh event |
| Rotation đáp ứng policy | Rotation config + key history | Evidence freshness và dependency compatibility |
| Key bị disable thì recovery an toàn | Tested recovery procedure | Restore lab khi key unavailable |
| Secret không tồn tại trong artifacts/logs | Secret scan, CI log review | Synthetic canary không bị lộ |

**Không thử vô hiệu hóa production key hoặc xóa data để tạo bằng chứng.** Dùng isolated test keys/resources và tabletop/integration exercises.

### 10.4. Data access khác resource access

IAM cho phép một service đọc bucket chưa đủ bảo đảm service chỉ đọc đối tượng đúng tenant. Cần:
- Server-side resource ownership và field-level authorization.
- Resource prefixes hoặc tenant-specific access controls nếu phù hợp.
- Signed URLs scope, expiration, method và revocation semantics.
- Copy/replication destinations và external principals.
- Secret/PII leakage qua logs, dead-letter queues và object metadata.
- CORS/CDN/cache behavior cho nội dung nhạy cảm.
- Negative authorization tests bằng synthetic tenant A/B.

## 11. Workload, containers, Kubernetes và serverless assurance

### 11.1. Compute và runtime controls

| Workload | Controls cần đánh giá | Evidence thực tế |
| --- | --- | --- |
| VM | OS patch, access, disk encryption, endpoint agent, egress, backup | Running kernel/packages, IAM, monitoring |
| Container image | Provenance, dependencies, secrets, fixed versions | Immutable digest, SBOM/SCA, signing/attestation |
| Kubernetes cluster | RBAC, admission, secrets, API exposure, network policy, nodes | Effective objects, authZ deny tests, node status |
| Serverless function | Execution role, event sources, versions/layers, concurrency | Actual alias/version, IAM, invocations, config |
| Managed container service | Image identity, deployment identity, task role, traffic | Task/pod current digest and policy |
| Managed database | Access, engine/version, encryption, backups, connectivity | Effective engine/roles, restore and policy tests |
| SaaS | Tenant identities, sharing, audit, vendor controls | Settings, IdP, vendor report/assurance limitations |

### 11.2. Container/image provenance

Một registry có image đã vá/được ký không chứng minh production chạy đúng image đó. Cần nối:
- Source commit và reviewed change.
- Build environment, provenance, dependency graph/SBOM.
- Image digest và approved policy.
- Deployment manifest/desired state.
- Runtime pods/tasks/functions đang chạy digest/version đúng.
- Old replicas/CronJobs/regions/rollback paths.
- Admission policy và enforcement evidence.

**Tag mutable ≠ immutable digest**. Nếu gate scan image A nhưng runtime dùng image B, evidence A không chứng minh B patched.

### 11.3. Kubernetes security

Assurance domains gồm:
- Control-plane access và RBAC.
- Service accounts/workload identity.
- Pod security restrictions: privileged, hostPath, hostNetwork, capabilities, runtime user.
- Secrets management và encryption.
- Cluster/node patching, supported versions.
- Network policies, ingress, API server exposure.
- Admission/policy rules và bypass routes.
- Supply-chain controls cho images/deployments.
- Multi-tenant namespace isolation và external secrets.
- Audit logs, workload monitoring và incident response.

Không coi `namespace` là ranh giới bảo mật đầy đủ trong mọi mô hình. Policy còn phụ thuộc IAM, workload runtime, cluster role, network CNI, nodes và service identity.

### 11.4. Serverless

Một function có thể được cập nhật source nhưng alias production vẫn trỏ version cũ. Ngoài ra phải xét:
- Event triggers, allowed invoke principals, function URLs.
- Execution role và accessible data sources.
- Environment variables/secrets.
- Runtime/layer/extension versions và patch responsibilities.
- Network egress, timeouts, concurrency và abuse limits.
- Logs, DLQ và event payload PII.
- Version/alias routing, deployment rollback và actual execution identity.

Assurance bắt buộc **gắn current deployed/executed version** với control evidence.

### 11.5. Shared platform vs customer controls

Một managed Kubernetes provider vận hành control plane không có nghĩa khách hàng miễn:
- Workload RBAC và image provenance.
- Node pools do khách hàng quản lý, nếu có.
- App authentication/authorization.
- Database/queue IAM.
- Runtime network policy và egress.
- Data confidentiality và retention.

Chỉ “đã dùng managed service” chưa phải risk treatment có bằng chứng.

## 12. Logging, detection, forensics và incident response

### 12.1. Những log sources quan trọng

- Organization/account/control-plane events.
- IAM login/role-assume/policy-change events.
- Network connection/flow/WAF/load-balancer events.
- Object-storage/data access events nếu dịch vụ bật/cho phép.
- KMS key use/admin events.
- Application/worker audit logs cho business actions.
- Kubernetes cluster/workload logs.
- Container/process runtime alerts.
- CI/CD deployment, artifact signing và approval events.
- Security scanner/CSPM findings và exceptions.
- Backup/restore, configuration và data deletion events.

Không phải mọi cloud service mặc định cung cấp đủ events, có thể có **cost, latency, coverage và service limitations**. Bật logging là một bước implementation; assurance phải kiểm **events có đến đúng sink, đầy đủ, an toàn và được sử dụng**.

### 12.2. Audit pipeline trust boundary

~~~mermaid
flowchart LR
    CP["Cloud control plane events"] --> PIPE["Collector / event routing"]
    APP["Application & worker logs"] --> PIPE
    KMS["Key usage events"] --> PIPE
    PIPE --> STORE["Protected centralized log store"]
    STORE --> DET["Detection / SIEM / analytics"]
    DET --> IR["Incident triage / response"]
    HEALTH["Source health and synthetic events"] -. "Verify pipeline" .-> PIPE
    IR --> CASE["Case, evidence, follow-up actions"]
~~~

Cloud audit assurance phải kiểm:
- Log source enabled trên **mọi expected accounts/regions/services**.
- Delivery delay, failures, source health và last event time.
- Identity/region/timestamp correlation.
- Integrity và quyền sửa/xóa logs.
- Retention đúng policy, dữ liệu nhạy cảm không bị lộ.
- Alerts đúng priority, owner, notification và runbook.
- Synthetic event được phép có thể **đi tới analyst/alert**.
- Monitoring khi một user/role **disable logging**.

**Zero alerts** không chứng minh “zero attacks” nếu collector bị tắt.

### 12.3. Incident response và cloud forensics

Một runbook cho cloud compromise nên xác định:
- Ai có quyền revoke sessions/roles/keys, isolate workloads, disable public access.
- Tài sản nào được snapshot/log preserve trong phạm vi legal/privacy.
- Cách ghi chain-of-custody, timestamps, affected accounts/regions.
- Cách ngăn attacker dùng control-plane access để xóa evidence.
- Cách rotate workload credentials và kiểm downstream dependencies.
- Cách restore from known-good infrastructure/images/backups.
- Cách điều phối provider support, third parties và business owner.
- Cách retest controls trước khi khôi phục dịch vụ.

Không tự chạy destructive containment trên production khi đang học; dùng tabletop, lab drills và phê duyệt theo incident policy.

## 13. Backup, resilience và recovery assurance

### 13.1. Backup configured ≠ recoverable

Một dashboard báo `backup job SUCCESS` chưa chứng minh:
- Có thể restore dữ liệu/application state đúng version.
- Backups không bị cùng compromised role xóa/sửa.
- Encryption keys cần phục hồi vẫn sẵn có.
- DB snapshot consistent với queue/object storage state.
- Regional outage không làm mất tất cả copies.
- RTO/RPO đạt theo business requirement.
- Recovery account/permissions/network có sẵn khi primary unavailable.
- Restore procedure được thực hành và ứng dụng khởi động đúng.

### 13.2. Evidence cho recovery

| Objective | Design evidence | Operating evidence |
| --- | --- | --- |
| Data recovery point | Backup/replication policy | Restore test và measured data loss |
| Recovery time | DR plan và dependencies | Timed failover/restore exercise |
| Backup integrity | Immutable/isolated storage design | Access-deny tests, restore checksum |
| Recovery identity | Break-glass/DR role design | Access drill với proper controls |
| Cross-region availability | Architecture dependency map | Controlled failover/tabletop test |
| Key availability | KMS/secret recovery plan | Lab restore với key states |
| Incident containment | Isolation/recovery runbook | Incident exercise audit |

**Đặt RTO/RPO theo business risk và được phê duyệt**, không lấy thời gian quảng cáo của provider như cam kết đã đạt khi chưa test.

### 13.3. Hai bản sao không luôn là hai failure domains

Hai snapshots trong cùng account và cùng permission domain có thể cùng bị xóa bởi một compromised admin. Assurance cần xem **independent access boundaries, recovery credentials, retention/immutability controls và replication/dependency graph**.

## 14. IaC, CI/CD và policy-as-code

### 14.1. “Shift left” nhưng không dừng ở pre-deploy

Infrastructure as Code (IaC) giúp kiểm configuration trước merge:
- Review pull request và branch/environment protections.
- Static IaC checks và policy-as-code rules.
- Sensitive variable/secret checks.
- Resource naming, owner/tagging và data classification.
- IAM/network/storage constraints.
- Supply-chain provenance, module/provider pinning và approval.
- Plan/diff review, drift detection và change authorization.
- CI identity least privilege, short-lived credentials và release provenance.

Nhưng **PASS ở CI** không tự chứng minh effective cloud state:
- User có thể tạo resource bằng console/API khác pipeline.
- Một update thất bại/rollback nhưng pipeline summary vẫn xanh.
- Provider defaults/permissions có thể khác expectation.
- Manual hotfix gây drift.
- Runtime workload chạy build/image cũ.
- Tài khoản/region mới chưa onboard scanner/logging.

Cần kết hợp **pre-deploy guardrail + post-deploy actual-state verification + continuous monitoring**.

### 14.2. Policy-as-code có ý nghĩa khi policy được gắn đúng scope

Một rule đơn giản phát hiện bucket không bật chế độ chặn public access **không đủ** chứng minh mọi data path an toàn. Nó kiểm một điều kiện hẹp.

Ví dụ **Rego dạng minh họa** dưới đây sử dụng cú pháp `rego.v1`. Giả định input đã được collector chuẩn hóa; không phải bộ kiểm chứng đầy đủ cho AWS/Azure/GCP và không kết luận bucket private chỉ từ một flag.

~~~rego
package assurance.storage

import rego.v1

deny contains msg if {
    input.resource.type == "object_storage_bucket"
    input.resource.classification == "confidential"
    not input.resource.public_access_guardrail_enabled

    msg := sprintf(
        "Confidential bucket %s lacks approved public-access guardrail",
        [input.resource.canonical_id],
    )
}

deny contains msg if {
    input.resource.type == "object_storage_bucket"
    input.resource.classification == "confidential"
    not input.resource.owner_known

    msg := sprintf(
        "Confidential bucket %s has no accountable owner",
        [input.resource.canonical_id],
    )
}
~~~

Mẫu normalized input:

~~~json
{
  "resource": {
    "canonical_id": "cloud:account-01:region-a:bucket-report-test",
    "type": "object_storage_bucket",
    "classification": "confidential",
    "owner_known": true,
    "public_access_guardrail_enabled": true
  }
}
~~~

Với input này hai rules trên không phát sinh `deny`, nhưng **đó không phải PASS toàn bộ security**. Cần:
- Validate nguồn input và identity của resource.
- Kiểm effective bucket/access policy, identity paths, signed URL và application authZ.
- Xem account/org-level guardrails và platform semantics.
- Kiểm monitoring/drift và dữ liệu thực tế.
- Kết hợp negative tests với test principal/object.
- Bổ sung policy cho encryption, key scope, logging, egress, retention.
- Thử trên lab/CI và kiểm công cụ/rule version trước áp production.

### 14.3. Policy enforcement và exceptions

Một pipeline có thể:
1. Lint/validate IaC.
2. Chạy policy rules theo approved baseline.
3. Phân loại policy violations theo risk/owner.
4. Kiểm exception authority, scope, expiry và compensating controls.
5. Block hoặc escalate theo release policy.
6. Deploy với workload identity hạn chế.
7. Verify actual resources sau deploy.
8. Record evidence và alerts nếu có drift.

**Exception không tự biến control thành compliant/fixed**. Báo riêng technical deviation, risk decision và remediation milestones. Không dùng suppression wildcard cho toàn account/region.

## 15. Continuous control monitoring

### 15.1. Snapshot assessment là cần nhưng chưa đủ

Cloud changes phát sinh từ:
- Autoscaling, ephemeral workloads, scheduled jobs.
- New accounts/projects/subscriptions.
- IAM roles/policies và CI trust changes.
- Public endpoint/storage policy updates.
- New regions, peering, gateway/WAF.
- Key rotation/disable, secrets updates.
- Images, dependencies, runtime versions và service upgrades.
- Provider configuration/evidence changes.
- Backup/retention policy và restore conditions.
- Incident/active exploitation intelligence.

Vì vậy **continuous assurance** cần event-driven reassessment bên cạnh periodic reviews.

### 15.2. Signals và trigger

| Trigger | Controls cần đánh giá lại | Expected response |
| --- | --- | --- |
| New cloud account/region | Inventory, logging, guardrails, ownership | Onboarding gate trước production |
| Role policy/trust changed | IAM least privilege, federation conditions | Diff + effective permission tests |
| New public route/IP/bucket | Exposure, authN/authZ, WAF/data control | Risk review, negative checks |
| Storage ACL/policy changed | Object confidentiality, data classification | Alert, policy enforcement/retest |
| Key/grant changed | KMS authorization, backup recovery | Key tests và audit review |
| New image/function version | SCA, provenance, runtime permissions | Digest-bound verification |
| Worker/queue topology changed | Data-flow/tenant isolation | Threat model và authZ tests |
| Logging disabled/source delay | Evidence/control monitoring | Inconclusive/alert/escalation |
| Backup/retention changed | Recovery claim, immutability | Restore/validation plan |
| Provider advisory/incident | Inherited controls và exposure | Risk assessment, vendor coordination |
| Exception expired/revoked | Technical deviation vẫn tồn tại | Enforcement/escalation |
| New exploitation intelligence | Prioritization and containment | Review emergency treatment |

### 15.3. Data pipeline để không báo xanh giả

~~~mermaid
flowchart TD
    INV["Accounts/projects/resource inventory"] --> EVAL["Control applicability and effective-state engine"]
    POL["Approved security requirements / policies"] --> EVAL
    OBS["Runtime config, logs, tests, provider evidence"] --> EVAL
    EVAL --> Q{"Evidence fresh, trusted and scope-complete?"}
    Q -- "Không" --> INC["INCONCLUSIVE / inventory or source gap"]
    Q -- "Có" --> R{"Requirement meets acceptance?"}
    R -- "Có" --> PASS["Scoped VERIFIED_PASS"]
    R -- "Không" --> FAIL["FAIL + risk finding"]
    FAIL --> FIX["Owner, remediation, controlled exception"]
    FIX --> RETEST["Retest actual deployed state"]
    RETEST --> EVAL
    PASS --> WATCH["Drift / change / incident triggers"]
    INC --> WATCH
    WATCH --> INV
~~~

### 15.4. “Continuous” không nhất thiết là real-time tuyệt đối

Controls có khác nhau về:
- Khả năng query và event latency của provider.
- Criticality và acceptable detection delay.
- Cost/quota/API throttling.
- Batch vs event-based evidence.
- Provider-managed evidence availability.
- Số lượng accounts/regions và required coverage.

Chọn monitoring cadence **theo risk** và đo độ trễ thực tế, không tuyên bố zero-latency nếu hệ thống không thể đáp ứng.

## 16. Công cụ cloud posture và phạm vi assurance

### 16.1. CSPM/CNAPP cung cấp dữ liệu, không cung cấp mọi kết luận

Các platform có thể hỗ trợ:
- Cloud asset discovery và configuration snapshots.
- IaC policy checks, misconfiguration detection và security benchmarks.
- Identity/permission risk analysis.
- Workload/container vulnerability findings.
- Network exposure/path graphs.
- Compliance reporting, exceptions và drift alerts.
- Risk prioritization bằng kết hợp assets, exposure và attack paths.
- Incident/detection correlations.

Nhưng mỗi công cụ có **connector scopes, supported service APIs, update latency, resource coverage và rule semantics riêng**. Cần kiểm chứng tool:
- Đã onboard mọi accounts/projects/subscriptions?
- Có quyền đọc resources và IAM policy cần thiết?
- Có quét mọi regions/managed services liên quan?
- Có xử lý resources ephemeral và terminated history?
- Rule version/benchmarks nào đang áp?
- Có blind spots về application/business authorization?
- Có self-test khi collector/API fails?
- Có giữ raw findings khi exception/suppression được áp?
- Có replay/reconcile actual state và scanner snapshot không?
- Alert tới đúng owner và thực sự được xử lý không?

Một dashboard hiển thị “0 critical” có thể do **rule bị tắt, connector thiếu account, source mất quyền hoặc chưa chạy scan**, chứ không phải môi trường đạt mục tiêu.

### 16.2. Các loại đánh giá

| Approach | Giá trị | Giới hạn |
| --- | --- | --- |
| CSPM posture rule | Phát hiện cấu hình lệch baseline | Không đo business behavior |
| CIEM/effective permissions | Quyền cloud có thể truy cập resource nào | Không hiểu đủ application authorization |
| Container/image scanning | Known vulnerable packages và provenance signals | Chưa chứng minh actual deployed/running state |
| IaC scan | Sai lệch trước deploy | Không chứng minh production không drift |
| K8s admission/policy | Ngăn deployment vi phạm rule ở boundary | Bypass routes và running objects cần kiểm |
| Cloud threat detection | Suspicious events | Không có alert không phải không có abuse |
| Manual architecture review | Control design phù hợp threat model | Không thay runtime tests |
| Penetration/security tests | Xác minh attack-path behavior | Chỉ đúng approved scenarios |
| Provider assurance | Chứng cứ cho provider-operated controls | Không bao phủ customer-controlled settings |

### 16.3. Không đồng nhất finding severity với business risk

Một public bucket chứa static marketing assets có mức impact khác public bucket chứa customer reports. Ngược lại một service role wildcard không public có thể gây rủi ro cao khi CI trust bị compromise.

Khi triage:
1. Confirm asset/resource identity và data/business criticality.
2. Determine actual exposure/reachability và attacker prerequisites.
3. Verify control effectiveness, không chỉ một boolean.
4. Assess likelihood, potential impact, uncertainty và regulatory obligations.
5. Set remediation priority/owner theo policy.
6. Link findings, exceptions và retest evidence vào source of truth.

### 16.4. Rule coverage và customization

Một rule vendor baseline có thể:
- Không áp dụng cho một service mới.
- Dùng option/version semantics khác ở cloud provider.
- Bị vô hiệu hoặc lọc trong dashboard.
- Tạo false positive do backport/equivalent controls.
- Tạo false negative vì application path không quan sát.
- Không biết những nghĩa vụ riêng của doanh nghiệp.

Vì vậy **policy catalog** phải do tổ chức kiểm soát: mỗi rule có owner, version, security objective, applicable asset classes, acceptance criteria và test plan; thay rule phải có review và migration để so sánh lịch sử đúng.

## 17. Mapping với standards và governance frameworks

Cloud assurance có thể lấy cấu trúc từ:
- **NIST Cybersecurity Framework (CSF)**: quản trị, nhận diện, bảo vệ, phát hiện, ứng phó và phục hồi ở mức kết quả/quản trị risk.
- **ISO/IEC 27001** và các chuẩn/quy định liên quan khi thuộc phạm vi áp dụng: quản lý hệ thống kiểm soát an toàn thông tin, kiểm soát và bằng chứng.
- **Cloud Security Alliance Cloud Controls Matrix (CSA CCM)**: tham chiếu nhóm kiểm soát đặc thù cloud.
- **CIS Benchmarks**: cấu hình hardening cho từng platform/service/version.
- **SOC 2 reports**: chứng cứ về controls trong phạm vi/type/period được kiểm tra, khi hữu ích cho provider/vendor assurance.
- **Industry/regulatory requirements** như PCI DSS, data protection/privacy obligations, hợp đồng và residency khi thật sự áp dụng.

Những framework này **khác nhau về mục tiêu, ngôn ngữ và phạm vi**. Không tự gán một control ID hoặc claim “tuân thủ chuẩn” khi chưa có mapping được review theo phiên bản áp dụng.

### 17.1. Mapping khái niệm

| Cloud risk/control | Security objective | Control evidence | Kết quả governance |
| --- | --- | --- | --- |
| Public storage exposure | Data confidentiality | Effective access policies + deny test | Risk/finding & cloud control mapping |
| Excessive privileged access | Least privilege | IAM entitlement graph + reviews + deny test | Access governance |
| Missing audit trails | Accountability/detection | Log source health + synthetic event | Operating effectiveness |
| Untrusted CI deployment | Software integrity | Build provenance + federation trust + runtime digest | Supply-chain assurance |
| Unsupported image/OS | Vulnerability management | Baseline, patch inventory, runtime verification | Remediation/backlog/exception |
| KMS permissions too broad | Key/data protection | Key policy and usage audit | Cryptographic control assurance |
| Unverified recovery | Availability/resilience | Restore drill and measured outcome | Business continuity/recovery |
| Weak vendor evidence | Shared responsibility | Scope/period/vendor report/CUEC review | Third-party risk management |

### 17.2. Evidence reuse phải có điều kiện

Một audit report hoặc control test có thể phục vụ nhiều requirements nếu:
- Asset, service, environment và control identity trùng scope.
- Thời kỳ quan sát phù hợp.
- Acceptance criteria tương thích.
- Bằng chứng có provenance/integrity.
- Assumptions và exclusions được công bố.
- Chưa có change trigger khiến kết quả cũ invalid.

Không tạo “evidence reuse” bằng cách copy một screenshot qua nhiều services/regions mà không kiểm effective state.

## 18. Evidence quality và đánh giá assurance có giới hạn

### 18.1. Một evidence record đáng tin cần gì?

| Dimension | Câu hỏi | Ví dụ gap |
| --- | --- | --- |
| **Provenance** | Lấy từ API/log/test nào, bằng identity nào? | Screenshot không có source |
| **Resource identity** | Đúng account/region/resource/deploy/digest? | Nhầm resource trùng tên |
| **Completeness** | Có đủ assets/controls trong scope? | 3 accounts chưa onboard |
| **Freshness** | Observation còn hiện hành? | Last scan 40 ngày |
| **Integrity** | Report/config có bị sửa trái phép? | CSV thủ công chưa kiểm |
| **Authenticity** | Source/assessor có đáng tin, authorization phù hợp? | Self-declared PASS |
| **Consistency** | Các nguồn có mâu thuẫn? | IaC deny, runtime public |
| **Test relevance** | Test thực sự chứng minh requirement? | Có log enabled nhưng không có events |
| **Operating behavior** | Control có hiệu lực trong thực tế? | WAF detect-only, không block |
| **Coverage boundaries** | Đã ghi exclusions, untested paths? | SaaS provider report không bao phủ tenant config |
| **Reviewability** | Reviewer có tái kiểm/đối chiếu được? | Không có time/deployment ID |
| **Data minimization** | Evidence có lộ secret/PII không? | Raw access tokens trong báo cáo |

### 18.2. Evidence freshness

Một snapshot là đúng ở thời điểm chụp nhưng có thể stale khi:
- Resource được tạo lại hoặc chuyển account/region.
- IAM trust/policy đổi.
- Image/digest/function alias đổi.
- Storage bucket policy/ACL thay.
- Key grant hoặc encryption config thay.
- Logs bị disable/mất source.
- Provider nâng service generation.
- Exception hết hạn.
- Phát hiện threat/incident mới làm risk assessment thay đổi.

Chính sách freshness nên nêu:
- **Maximum observation age** theo control criticality.
- **Immediate invalidation events** độc lập TTL.
- Sensor/source health.
- Assessment clock/timezone và clock skew tolerance.
- Cách xử lý data missing/partial/historical.
- Owner và remediation workflow cho evidence gaps.

Một report có timestamp mới nhưng lấy từ **resource version cũ** vẫn không phải evidence hiện hành.

### 18.3. Các trạng thái kết luận

| Trạng thái | Điều kiện | Có tính verified assurance PASS? |
| --- | --- | --- |
| **VERIFIED_PASS** | Requirement đạt, effective evidence đúng scope/fresh và đủ | Có |
| **CONFIRMED_FAIL** | Requirement không đạt, có evidence đáng tin | Không |
| **INCONCLUSIVE** | Evidence, source, applicability hoặc coverage không đủ | Không |
| **NOT_RUN** | Chưa đánh giá, kể cả tool unavailable | Không |
| **STALE_EVIDENCE** | Evidence hết hạn hoặc đã bị invalidated | Không |
| **CONTROL_NOT_APPLICABLE_VERIFIED** | Requirement thật sự không áp dụng có rationale | Exclude có kiểm soát, báo riêng |
| **EXCEPTION_ACTIVE** | Sai lệch có risk approval hợp lệ | Không biến technical result thành PASS |
| **MITIGATED_NOT_FIXED** | Giảm risk nhưng requirement gốc chưa đáp ứng | Không tự là PASS |
| **INHERITED_VERIFIED** | Control provider-operated được kế thừa trong scope/time phù hợp | Có thể hỗ trợ claim đó, không phải toàn tenant |

### 18.4. Không tự “PASS” khi thiếu nguồn

- Source connector mất quyền → **INCONCLUSIVE**, không “no findings”.
- Cloud service không hỗ trợ một rule → **NOT_RUN hoặc NOT_APPLICABLE có chứng cứ**, không mặc định PASS.
- Provider report không có scope/current period → **inherited-control evidence gap**.
- Service owner chưa khai data classification → **unknown applicability/risk**, không tự low.
- Một control trong IaC PASS nhưng runtime drift → report current effective state là FAIL/needs reconciliation.
- Risk exception active → decision riêng, không biến original technical control into PASS.

## 19. Coverage metrics và denominator integrity

### 19.1. Định nghĩa một control obligation

Một cloud assurance obligation có thể là:

`(account/project, region, resource ID, requirement ID, policy version, assessment scope)`.

Ví dụ:
- `storage:account-A:region-1:bucket-X` + `CONFIDENTIAL_NO_PUBLIC_ACCESS`.
- `iam:account-B:role-Y` + `NO_UNRESTRICTED_TRUST`.
- `logs:account-A:region-2:control-plane-log-source` + `EVENT_DELIVERY_ACTIVE`.

Có thể chọn đơn vị **resource-control pair** hoặc **risk scenario-control-test** tùy mục tiêu; nhưng phải ghi rõ. Đừng đếm một resource với 20 rules bằng cùng trọng số rồi so với một resource có một critical control như thể risk tương đương.

### 19.2. Tập eligible và tử số

Cho snapshot `t`:
- `U(t)` = các candidate obligations từ **đầy đủ cloud inventory + approved policy catalog**.
- `N(t)` = obligations verified not applicable, có reason/evidence.
- `D(t) = U(t) \ N(t)` = eligible obligations, gồm requirements chưa rõ applicability cần triage.
- `P(t)` = obligations VERIFIED_PASS hoặc inherited control đã được **chứng minh đúng phạm vi/criteria** trong `D(t)`.

~~~text
Cloud control assurance coverage (%) =
  100 × |verified PASS obligations| / |eligible obligations|

Eligible = candidate in-scope obligations
           − verified-not-applicable obligations

CONFIRMED_FAIL, INCONCLUSIVE, NOT_RUN, STALE_EVIDENCE
and EXCEPTION_ACTIVE remain unresolved in denominator.
~~~

Nếu `D=0` vì scope thực sự không có eligible obligations, báo **N/A với giải thích**. Nếu inventory thiếu và **không biết population**, báo **INCONCLUSIVE**; không tự đổi thành 100%.

### 19.3. Ví dụ số liệu

Giả sử một assessment có:
- 120 candidate resource–control pairs.
- 12 verified not applicable.
- 75 verified PASS.
- 10 confirmed FAIL.
- 7 có exception được duyệt nhưng technical control chưa đạt.
- 10 INCONCLUSIVE (missing/conflicting evidence).
- 6 NOT_RUN.

~~~text
Candidate:         120
Not applicable:     12
Eligible:          108 = 120 - 12

Verified PASS:      75
Confirmed FAIL:     10
Exception (not PASS): 7
Inconclusive:       10
Not run:             6

Coverage = 75 / 108 × 100 ≈ 69.44%
Valid evaluated outcomes = 75 + 10 = 85
Evidence-backed outcome coverage = 85 / 108 × 100 ≈ 78.70%
~~~

Một exception approved có thể đáp ứng quy trình risk governance trong scope nhưng **không được cộng vào tử số technical assurance**. Nếu dùng một metric `policy-compliant-or-excepted`, phải đổi tên, công bố cách tính và không trình bày là controls thực sự được verify.

### 19.4. Risk-segmented metrics

| Segment | Metric nên có | Phải kèm |
| --- | --- | --- |
| Critical production IAM | Verified restrictive trust/permissions | Open excessive roles, active incidents |
| Public-facing applications | AuthN/authZ, TLS, WAF và egress checks | Critical routes untested, exploitable findings |
| Confidential data storage | Encryption, private access, audit | Public/external access count |
| Central logging | Source delivery coverage and freshness | Missing accounts/regions, collector outages |
| KMS/secret management | Key policy tests/usage audit | Unowned keys, expiring credentials |
| Production workloads | Approved image/digest, runtime controls | Unscanned/old replicas, exceptions |
| Recovery | Restore tests vs RTO/RPO | Untested recovery domains |
| SaaS/provider controls | Inherited control evidence coverage | Report scope/period/CUECs/customer settings |

**Một tỷ lệ 99% có thể che một production admin role quyền quá rộng hoặc một public bucket chứa data nhạy cảm.** Báo song song count tuyệt đối, critical risk gaps và detection times.

### 19.5. Historical comparison

Mỗi time series cần lưu:
- Scope và cloud population snapshot.
- Requirement catalog/policy version.
- Tool/query/evidence semantics.
- Freshness và exclusion policy.
- Assessment cutoff.
- Criticality mapping/risk weights nếu dùng.
- Provider report/control inheritance source.

Nếu thêm 10 accounts trước đây chưa inventory, coverage có thể giảm do visibility tăng — **đây không nhất thiết là security posture xấu đi**, mà là việc loại bỏ blind spot. Không tự so sánh % trước/sau khi denominator khác mà không nêu điều chỉnh.

## 20. Java 17: bộ tổng hợp cloud control assurance coverage

### 20.1. Bài toán

Giả sử cloud inventory và policy catalog đã tạo ra các **expected control obligations**. Collector cung cấp observations cho từng cặp resource–requirement.

Bộ tổng hợp cần ngăn ba lỗi phổ biến:
1. Một resource thiếu telemetry bị **loại khỏi denominator**.
2. Một test có trạng thái PASS nhưng bằng chứng **quá cũ/sai scope** vẫn được tính.
3. Một approved exception hoặc “not applicable” không có evidence bị **đếm là technical PASS**.

Mã dưới đây minh họa **aggregation invariants**, không gọi cloud API và không khẳng định tính xác thực của raw evidence. `trustedEvidenceValidated` phải đến từ hệ thống kiểm provenance/authorization/integrity đáng tin cậy, **không phải flag do client tự khai**.

### 20.2. Model và calculator

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class CloudAssuranceCalculator {

    public enum Applicability {
        APPLICABLE,
        NOT_APPLICABLE_VERIFIED,
        UNKNOWN
    }

    public enum ResultState {
        VERIFIED_PASS,
        CONFIRMED_FAIL,
        EXCEPTION_ACTIVE,
        INCONCLUSIVE,
        NOT_RUN
    }

    public record Obligation(
            String canonicalResourceId,
            String requirementId) {}

    public record Observation(
            String canonicalResourceId,
            String requirementId,
            Applicability applicability,
            ResultState state,
            Instant observedAt,
            String evidenceRef,
            boolean sourceHealthy,
            boolean trustedEvidenceValidated) {}

    private record Key(String resourceId, String requirementId) {}

    public record Report(
            int candidate,
            int notApplicableExcluded,
            int eligible,
            int verifiedPass,
            int confirmedFail,
            int unresolved,
            Double coveragePercent) {}

    public Report calculate(
            List<Obligation> expected,
            List<Observation> observations,
            Clock clock,
            Duration maxAge) {

        Objects.requireNonNull(expected);
        Objects.requireNonNull(observations);
        Objects.requireNonNull(clock);
        Objects.requireNonNull(maxAge);

        if (maxAge.isZero() || maxAge.isNegative()) {
            throw new IllegalArgumentException(
                    "maxAge must be positive");
        }

        Set<Key> obligations = new HashSet<>();
        for (Obligation item : expected) {
            if (item == null || blank(item.canonicalResourceId())
                    || blank(item.requirementId())) {
                throw new IllegalArgumentException(
                        "Invalid obligation");
            }

            Key key = new Key(
                    item.canonicalResourceId(),
                    item.requirementId());
            if (!obligations.add(key)) {
                throw new IllegalArgumentException(
                        "Duplicate resource-control obligation");
            }
        }

        Map<Key, Observation> observedByKey = new HashMap<>();
        for (Observation item : observations) {
            if (item == null || blank(item.canonicalResourceId())
                    || blank(item.requirementId())
                    || item.applicability() == null
                    || item.state() == null) {
                throw new IllegalArgumentException(
                        "Invalid observation");
            }

            Key key = new Key(
                    item.canonicalResourceId(),
                    item.requirementId());

            if (!obligations.contains(key)) {
                throw new IllegalArgumentException(
                        "Observation outside expected population");
            }
            if (observedByKey.putIfAbsent(key, item) != null) {
                throw new IllegalArgumentException(
                        "Multiple observations need reconciliation");
            }
        }

        Instant now = clock.instant();
        Instant earliest = now.minus(maxAge);

        int excluded = 0;
        int eligible = 0;
        int passed = 0;
        int failed = 0;

        for (Key key : obligations) {
            Observation row = observedByKey.get(key);

            // Không có observation -> eligible chưa được đánh giá.
            if (row == null) {
                eligible++;
                continue;
            }

            boolean fresh = row.observedAt() != null
                    && !row.observedAt().isAfter(now)
                    && !row.observedAt().isBefore(earliest);

            boolean evidenceReady = fresh
                    && !blank(row.evidenceRef())
                    && row.sourceHealthy()
                    && row.trustedEvidenceValidated();

            // NOT_APPLICABLE chỉ có hiệu lực khi evidence đạt.
            if (row.applicability()
                    == Applicability.NOT_APPLICABLE_VERIFIED
                    && evidenceReady) {
                excluded++;
                continue;
            }

            eligible++;

            if (!evidenceReady
                    || row.applicability()
                    != Applicability.APPLICABLE) {
                continue;
            }

            if (row.state() == ResultState.VERIFIED_PASS) {
                passed++;
            } else if (row.state()
                    == ResultState.CONFIRMED_FAIL) {
                failed++;
            }

            // Exceptions / unknown / not-run:
            // giữ nguyên trong eligible, không tính PASS.
        }

        int unresolved = eligible - passed - failed;
        Double coverage = eligible == 0
                ? null : (100.0 * passed / eligible);

        return new Report(obligations.size(), excluded,
                eligible, passed, failed, unresolved, coverage);
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
~~~

### 20.3. Giải thích ràng buộc

- **Expected population** phải do cloud inventory + approved control catalog xây; thiếu account/region vẫn là **source completeness gap** bên ngoài calculator.
- Một resource–requirement là một đơn vị; có nhiều snapshots cần upstream chọn **current view** có lịch sử, không pick observation “xanh nhất”.
- `maxAge` là rule ví dụ. Thay đổi IAM/bucket/image có thể làm evidence invalid **ngay lập tức**, dù chưa hết TTL.
- `trustedEvidenceValidated` chỉ đại diện kết quả validation từ trusted system, không phải proof tự thân. Real implementation cần xác minh source identity, policy version, cloud resource ID, deployment, signature/authorization và applicable test semantics.
- `NOT_APPLICABLE_VERIFIED` có thể bị loại khỏi eligible nhưng phải có rationale và approval phù hợp; ở đây nó **không được cộng vào PASS**.
- Approved exceptions không tự đưa weakness đã biết thành compliant technical result.
- `INCONCLUSIVE`, `NOT_RUN`, missing observation và unhealthy source luôn giữ trong denominator.
- `eligible=0` cho `coveragePercent=null` (N/A). Nếu inventory completeness không chứng minh, assessment ở level cao hơn phải là INCONCLUSIVE, không tự chấp nhận N/A.
- Risk-based priority và inherited controls cần mô hình policy/evidence bổ sung, không nên ép tất cả vào một Boolean.

### 20.4. JUnit 5: negative tests cho dữ liệu assurance

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;

class CloudAssuranceCalculatorTest {

    private static final Instant NOW =
            Instant.parse("2026-11-28T03:00:00Z");
    private static final Clock CLOCK =
            Clock.fixed(NOW, ZoneOffset.UTC);
    private static final Duration MAX_AGE =
            Duration.ofHours(24);

    private final CloudAssuranceCalculator calculator =
            new CloudAssuranceCalculator();

    private CloudAssuranceCalculator.Obligation expected(String id) {
        return new CloudAssuranceCalculator.Obligation(
                "cloud:account-a:region-1:" + id,
                "CONFIDENTIAL_PRIVATE_ACCESS");
    }

    private CloudAssuranceCalculator.Observation observation(
            String id,
            CloudAssuranceCalculator.Applicability applicability,
            CloudAssuranceCalculator.ResultState state,
            Instant when,
            String evidence,
            boolean healthy) {

        return new CloudAssuranceCalculator.Observation(
                "cloud:account-a:region-1:" + id,
                "CONFIDENTIAL_PRIVATE_ACCESS",
                applicability, state, when, evidence, healthy, true);
    }

    @Test
    void onlyCurrentTrustedPassesIncreaseNumerator() {
        var pass = observation(
                "bucket-a",
                CloudAssuranceCalculator.Applicability.APPLICABLE,
                CloudAssuranceCalculator.ResultState.VERIFIED_PASS,
                NOW, "EVIDENCE-01", true);
        var fail = observation(
                "bucket-b",
                CloudAssuranceCalculator.Applicability.APPLICABLE,
                CloudAssuranceCalculator.ResultState.CONFIRMED_FAIL,
                NOW, "EVIDENCE-02", true);
        var exception = observation(
                "bucket-c",
                CloudAssuranceCalculator.Applicability.APPLICABLE,
                CloudAssuranceCalculator.ResultState.EXCEPTION_ACTIVE,
                NOW, "EXCEPTION-01", true);

        var result = calculator.calculate(
                List.of(expected("bucket-a"), expected("bucket-b"),
                        expected("bucket-c"), expected("bucket-d")),
                List.of(pass, fail, exception),
                CLOCK, MAX_AGE);

        assertEquals(4, result.candidate());
        assertEquals(4, result.eligible());
        assertEquals(1, result.verifiedPass());
        assertEquals(1, result.confirmedFail());
        assertEquals(2, result.unresolved());
        assertEquals(25.0, result.coveragePercent(), 0.001);
    }

    @Test
    void verifiedNotApplicableIsExcluded() {
        var na = observation(
                "bucket-a",
                CloudAssuranceCalculator.Applicability.NOT_APPLICABLE_VERIFIED,
                CloudAssuranceCalculator.ResultState.NOT_RUN,
                NOW, "N_A_EVIDENCE", true);

        var result = calculator.calculate(
                List.of(expected("bucket-a")),
                List.of(na), CLOCK, MAX_AGE);

        assertEquals(1, result.notApplicableExcluded());
        assertEquals(0, result.eligible());
        assertNull(result.coveragePercent());
    }

    @Test
    void notApplicableWithoutEvidenceStaysEligible() {
        var na = observation(
                "bucket-a",
                CloudAssuranceCalculator.Applicability.NOT_APPLICABLE_VERIFIED,
                CloudAssuranceCalculator.ResultState.NOT_RUN,
                NOW, null, true);

        var result = calculator.calculate(
                List.of(expected("bucket-a")),
                List.of(na), CLOCK, MAX_AGE);

        assertEquals(0, result.notApplicableExcluded());
        assertEquals(1, result.eligible());
    }

    @Test
    void stalePassIsNotTrusted() {
        var old = observation(
                "bucket-a",
                CloudAssuranceCalculator.Applicability.APPLICABLE,
                CloudAssuranceCalculator.ResultState.VERIFIED_PASS,
                NOW.minus(Duration.ofDays(3)), "OLD-EVIDENCE", true);

        var result = calculator.calculate(
                List.of(expected("bucket-a")),
                List.of(old), CLOCK, MAX_AGE);

        assertEquals(0, result.verifiedPass());
        assertEquals(1, result.unresolved());
    }

    @Test
    void sourceOutageNeverBecomesVerifiedPass() {
        var outage = observation(
                "bucket-a",
                CloudAssuranceCalculator.Applicability.APPLICABLE,
                CloudAssuranceCalculator.ResultState.VERIFIED_PASS,
                NOW, "EVIDENCE-01", false);

        var result = calculator.calculate(
                List.of(expected("bucket-a")),
                List.of(outage), CLOCK, MAX_AGE);

        assertEquals(0, result.verifiedPass());
    }

    @Test
    void unknownApplicabilityNeverBecomesPass() {
        var unknown = observation(
                "bucket-a",
                CloudAssuranceCalculator.Applicability.UNKNOWN,
                CloudAssuranceCalculator.ResultState.VERIFIED_PASS,
                NOW, "EVIDENCE-01", true);

        var result = calculator.calculate(
                List.of(expected("bucket-a")),
                List.of(unknown), CLOCK, MAX_AGE);

        assertEquals(0, result.verifiedPass());
        assertEquals(1, result.eligible());
    }

    @Test
    void futureObservationCannotCount() {
        var future = observation(
                "bucket-a",
                CloudAssuranceCalculator.Applicability.APPLICABLE,
                CloudAssuranceCalculator.ResultState.VERIFIED_PASS,
                NOW.plusSeconds(3600), "FUTURE-EVIDENCE", true);

        var result = calculator.calculate(
                List.of(expected("bucket-a")),
                List.of(future), CLOCK, MAX_AGE);

        assertEquals(0, result.verifiedPass());
    }

    @Test
    void duplicateExpectedObligationIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                calculator.calculate(
                        List.of(expected("bucket-a"),
                                expected("bucket-a")),
                        List.of(), CLOCK, MAX_AGE));
    }

    @Test
    void wrongResourceObservationIsRejected() {
        var wrong = observation(
                "bucket-b",
                CloudAssuranceCalculator.Applicability.APPLICABLE,
                CloudAssuranceCalculator.ResultState.VERIFIED_PASS,
                NOW, "EVIDENCE-02", true);

        assertThrows(IllegalArgumentException.class, () ->
                calculator.calculate(
                        List.of(expected("bucket-a")),
                        List.of(wrong), CLOCK, MAX_AGE));
    }

    @Test
    void emptyPopulationIsNotHundredPercent() {
        var result = calculator.calculate(
                List.of(), List.of(), CLOCK, MAX_AGE);

        assertEquals(0, result.eligible());
        assertNull(result.coveragePercent());
    }
}
~~~

**Các tests này chưa chạy trong STEP 4**, là code minh họa để người học thực hành. Chúng kiểm aggregation logic; không xác minh cloud provider APIs hay physical/managed platform controls. Khi áp dụng, cần thêm unit/integration tests cho resource inventory, IAM effective policies, provider evidence, control inheritance và mismatch giữa actual state với IaC.

## 21. Security requirements cho cloud assurance

Các mã `CA-REQ-*` là **mẫu giáo dục**, không phải ID của một tiêu chuẩn chính thức. Một tổ chức cần chỉnh theo service, risk, policy, obligations và cloud provider/service model đang dùng.

| ID | Requirement kiểm chứng được | Acceptance/evidence |
| --- | --- | --- |
| **CA-REQ-01** | Mọi cloud account/project/subscription thuộc scope phải có owner và được inventory | Org + resource discovery reconciliation |
| **CA-REQ-02** | Những resources mới phải được phân loại dữ liệu/risk và gắn owner trước production use | Onboarding metadata/policy tests |
| **CA-REQ-03** | Shared responsibility phải có control owner và inheritance/evidence mapping | Service-specific responsibility register |
| **CA-REQ-04** | Privileged human cloud access phải tuân approved identity/authentication/access policy | Effective roles, IdP, MFA/conditional control tests |
| **CA-REQ-05** | Workload identity phải dùng trusted federation/credentials và permission theo least privilege | Effective trust + deny tests |
| **CA-REQ-06** | Cross-account/resource access phải giới hạn principals, conditions, resources | Resource policy + effective permission test |
| **CA-REQ-07** | Confidential object storage không được public ngoài approved business requirement | Effective access policy + synthetic deny test |
| **CA-REQ-08** | Sensitive data encrypted at rest/in transit theo approved classification policy | Runtime configs + key/TLS checks |
| **CA-REQ-09** | KMS keys/grants chỉ cho approved identities sử dụng | Key policy + denied principal test + audit |
| **CA-REQ-10** | Public exposure/network ingress/egress phải theo approved architecture | Route/firewall graphs + safe connectivity tests |
| **CA-REQ-11** | Production container/functions phải chạy approved artifact/version/digest | Runtime identity + provenance/signed build |
| **CA-REQ-12** | OS/runtime/dependency patch obligations phải được đo trên actual workloads | Patch baselines + image/host/runtime verification |
| **CA-REQ-13** | IaC/policy violations phải được ngăn hoặc escalated theo release policy | CI gate + effective deployed state |
| **CA-REQ-14** | Mọi account/region service logs cần thiết phải gửi tới protected detection pipeline | Source health, delivery synthetic event |
| **CA-REQ-15** | Thay đổi cấu hình làm giảm bảo vệ phải tạo drift/risk event | Controlled change detection test |
| **CA-REQ-16** | Backup/recovery controls phải được kiểm chứng với RTO/RPO/permissions tương ứng | Approved restore drill và measured results |
| **CA-REQ-17** | Service-managed/inherited controls phải có provider evidence đúng scope/period | Provider report/CUEC/service applicability review |
| **CA-REQ-18** | SaaS tenant sharing/SSO/access phải được kiểm bởi customer owner | Tenant settings + negative access review |
| **CA-REQ-19** | Cloud findings phải có risk owner, severity context, treatment và retest plan | Finding/remediation register |
| **CA-REQ-20** | Exceptions phải time-bound, authorized và không được tính technical PASS | Exception verification + coverage test |
| **CA-REQ-21** | Evidence phải có provenance, asset/deployment identity, timestamp, integrity và reviewer | Evidence register + sampled audit |
| **CA-REQ-22** | Unknown applicability, stale/missing telemetry không được tự PASS | Coverage unit/failure tests |
| **CA-REQ-23** | New account/route/region/key/role/image change phải trigger reassessment theo risk | Change event + monitoring evidence |
| **CA-REQ-24** | Incident/privilege compromise phải có containment, recovery và audit preservation procedure | Tabletop/authorized exercise |
| **CA-REQ-25** | Cloud data access phải có server-side object/tenant authorization ở tầng ứng dụng | Synthetic cross-tenant integration tests |
| **CA-REQ-26** | API/CI/automation được cấp production deploy rights phải tuân separation of duties | Workflow approval + untrusted identity deny test |
| **CA-REQ-27** | Cloud resource/control inventory phải đối chiếu scanner coverage và phát hiện shadow accounts | Reconciliation report + negative tests |
| **CA-REQ-28** | Evidence của fixed control phải gắn actual post-change deployment và retest | Runtime verification + reviewer sign-off |

### Từ requirement tới test

Một requirement tốt cần:
- **Owner** accountable và source of authority.
- **Asset scope**: resource types, environments, accounts/regions.
- **Risk statement** và security objective.
- **Control behavior**, không chỉ tool configuration.
- **Applicability** và verified exclusion rules.
- **Evidence source, freshness và validation**.
- **Acceptance criteria**: PASS/FAIL/INCONCLUSIVE rõ.
- **Monitoring/reassessment triggers**.
- **Remediation/exception path**.
- **Audit/retention** cho bằng chứng.

Ví dụ `CA-REQ-07` không thể được đánh giá chỉ bằng “CSPM rule 12 = true”. Cần xác định confidential buckets từ inventory, effective access paths, storage policies và negative behavior tests phù hợp.

## 22. Cloud assurance verification test plan

Các tests dưới đây là **kế hoạch**, không tự khẳng định đã chạy. Chỉ thực hiện trên cloud accounts/resources được cấp quyền; negative tests nên dùng principals và resources synthetic, không truy cập dữ liệu người dùng thật hoặc làm gián đoạn production.

| Test ID | Scenario | Expected result |
| --- | --- | --- |
| **CA-T01** | Account mới chưa được onboarding CSPM/logging | Coverage gap, không PASS |
| **CA-T02** | Resource chưa có owner | Finding, không auto low-risk |
| **CA-T03** | CMDB nói resource retired nhưng cloud API thấy running | Reconcile, giữ active trong scope |
| **CA-T04** | Resource name được tái sử dụng với ID mới | Không kế thừa evidence cũ |
| **CA-T05** | Region chưa scan | INCONCLUSIVE/NOT_RUN cho obligations |
| **CA-T06** | IAM human admin thiếu required factor | FAIL theo policy |
| **CA-T07** | Break-glass test account dùng theo approval | Audit và alert đúng |
| **CA-T08** | Untrusted CI PR identity assume production role | DENY |
| **CA-T09** | Workload ngoài namespace/subject được duyệt xin role | DENY |
| **CA-T10** | Workload có quyền đọc object đúng prefix | ALLOW theo authorized policy |
| **CA-T11** | Workload ghi ngoài prefix hoặc đọc tenant khác | DENY, không side effect |
| **CA-T12** | Resource policy cho external principal ngoài scope | Finding/risk review |
| **CA-T13** | Confidential bucket thiếu public guardrail | Policy FAIL và alert |
| **CA-T14** | Public guardrail bật nhưng signed URL quá rộng | App/data access finding riêng |
| **CA-T15** | Encrypted resource dùng unapproved key | FAIL theo classification |
| **CA-T16** | Unauthorized test principal gọi decrypt | DENY, usage event |
| **CA-T17** | Key rotation config có nhưng key usage audit tắt | Operating evidence gap |
| **CA-T18** | Database public route do network misconfiguration | Exposure finding |
| **CA-T19** | Database private nhưng gateway app authZ lỏng | Separate application finding |
| **CA-T20** | WAF rule chỉ detect, requirement cần block | FAIL enforcement |
| **CA-T21** | Source IP private nhưng request thiếu authorization | Server-side deny vẫn bắt buộc |
| **CA-T22** | CI scan fixed image A; runtime chạy digest B | Không chuyển PASS của A sang B |
| **CA-T23** | Container node patched, app library vulnerable | App obligation vẫn open |
| **CA-T24** | New K8s namespace có privileged workload | Policy gate/alert tùy requirement |
| **CA-T25** | Serverless alias trỏ old vulnerable version | Reassess actual version |
| **CA-T26** | IaC PASS nhưng console drift thành public | Actual state FAIL và drift alert |
| **CA-T27** | Config scanner timeout/mất quyền | INCONCLUSIVE, không no-findings PASS |
| **CA-T28** | Cloud audit logging disabled | Detection và control finding |
| **CA-T29** | Synthetic control-plane change không tới central sink | Source-health FAIL |
| **CA-T30** | Log sink vẫn ghi nhưng retention không đáp ứng | Policy FAIL |
| **CA-T31** | Backup job succeeded nhưng restore test thất bại | Recovery claim FAIL |
| **CA-T32** | Backup có thể bị primary compromised role xóa | Isolation/control gap |
| **CA-T33** | SaaS vendor report không cover region/service | Inherited evidence INCONCLUSIVE |
| **CA-T34** | Provider evidence có CUEC khách hàng chưa triển khai | Customer control gap |
| **CA-T35** | Exception ACTIVE cho một unpatched image | Technical numerator không tăng |
| **CA-T36** | Exception expired/revoked | Gate/escalate theo policy |
| **CA-T37** | NOT_APPLICABLE thiếu evidence | Giữ eligible denominator |
| **CA-T38** | Evidence timestamp cũ hoặc future | Không VERIFIED_PASS |
| **CA-T39** | Duplicate/conflicting resource observations | Reconcile, không chọn “xanh nhất” |
| **CA-T40** | New public endpoint sau assessment | Trigger new scenario/control evaluation |
| **CA-T41** | Data class tăng từ internal lên confidential | Recalculate applicable requirements |
| **CA-T42** | Role chính thức bị revoke nhưng session còn | Kiểm lifecycle theo expiry/revocation policy |
| **CA-T43** | KMS/service outage gây fail-open behavior | Không mở rộng quyền; record test outcome |
| **CA-T44** | Cloud asset không có agent nhưng vẫn running | Inventory gap; không exclude |
| **CA-T45** | Staging test PASS, production dùng gateway config khác | Không suy production PASS |
| **CA-T46** | Remediation PR merged nhưng cloud resource chưa cập nhật | Finding vẫn open |
| **CA-T47** | Fixed policy deployed, retest same deny case đạt | Có thể VERIFIED_CLOSED theo scope |
| **CA-T48** | Rollback trở về overly permissive policy | Reopen/reassess finding |
| **CA-T49** | One critical account-risk FAIL nhưng 99% overall PASS | Priority/escalation theo risk, không theo average |
| **CA-T50** | Incident/active exploitation intelligence mới | Trigger contingency/risk reassessment |

### Chạy test ở nhiều tầng

- **Design review:** threat modeling, shared responsibility, control architecture.
- **IaC/policy unit:** parse/lint, rule logic, applicability, deny test fixtures.
- **Integration:** IAM, storage policy, gateway/API and identities với synthetic resources.
- **Runtime:** actual VM/pod/function versions, network endpoints, key usage, logs.
- **Negative security:** wrong principal/role/account/tenant, stale evidence, direct paths.
- **Failure injection:** collector disabled, permission revoked, backup restore fails trong lab.
- **Operational:** incident/tabletop, log alert exercise, recovery and stop procedures.
- **Governance:** exception approvals, risk ownership, vendor reports và audit retention.

Đặc biệt, đừng gây sự cố bằng cách **tắt production KMS, xóa backup hoặc thử lộ dữ liệu thật** chỉ để đánh giá. Mọi failure injection cần isolated environment hoặc phương pháp an toàn đã được phê duyệt.

## 23. Cloud security assurance evidence register

### 23.1. Hồ sơ đánh giá YAML mẫu

Các mục `<...>` là placeholders cần thay bằng values từ hệ thống thực. Các con số minh họa dùng chính ví dụ ở mục 19; **chưa có assessment thực tế**.

~~~yaml
assessment_id: CLOUD-ASSURANCE-001
module: SECURITY_SECURITY_ASSURANCE
topic: Cloud security assurance
assessment:
  state: PLANNED
  cutoff_at: "<ISO_8601_UTC>"
  assessor: "<AUTHORIZED_SECURITY_ASSESSOR>"
  reviewer: "<INDEPENDENT_REVIEWER>"
  approved_policy_catalog_ref: "<VERSIONED_POLICY_BASELINE>"
  scope_version: "<VERSION>"
  security_objectives:
    - cloud-identity-and-least-privilege
    - cloud-data-confidentiality
    - runtime-and-supply-chain-integrity
    - monitoring-and-resilience
scope:
  provider_services: ["<CLOUD_PROVIDER_AND_SERVICE_TYPES>"]
  organization_id: "<CLOUD_ORGANIZATION_ID>"
  accounts_or_projects: ["<APPROVED_ACCOUNT_IDS>"]
  environments: ["production"]
  regions: ["<REGION_IDS>"]
  asset_classes: ["iam", "storage", "network", "compute", "keys", "logs"]
  service_owner: "<SERVICE_OWNER>"
  inventory_snapshot_ref: "<ACCOUNT_AND_RESOURCE_INVENTORY>"
  account_discovery_coverage_ref: "<SHADOW_ACCOUNT_RECONCILIATION>"
  classification_ref: "<DATA_OWNER_AND_CLASSIFICATION>"
responsibility:
  service_model_map_ref: "<IAAS_PAAS_SAAS_RESPONSIBILITY_MATRIX>"
  inherited_controls_ref: "<PROVIDER_ASSURANCE_SCOPE_AND_PERIOD>"
  customer_controls_ref: "<CUES_AND_TENANT_CONTROL_REGISTER>"
  shared_controls_ref: "<SHARED_OPERATION_AND_EVIDENCE_OWNER>"
evidence_policy:
  provenance_verification_ref: "<TRUSTED_COLLECTORS_AND_ATTESTATIONS>"
  max_age_policy_ref: "<RISK_BASED_FRESHNESS_POLICY>"
  invalidation_triggers_ref: "<CLOUD_CHANGE_EVENT_CATALOG>"
  source_health_ref: "<API_LOG_SCAN_CONNECTOR_HEALTH>"
  protected_store_ref: "<EVIDENCE_STORE_AND_RETENTION>"
metric:
  name: cloud-control-assurance-coverage
  unit: resource-control-obligation
  definition_version: "1.0"
  candidate_obligations: 120
  not_applicable_verified: 12
  eligible_obligations: 108
  verified_pass: 75
  confirmed_fail: 10
  exception_not_pass: 7
  inconclusive: 10
  not_run: 6
  coverage_percent: 69.44
  outcome_observed_percent: 78.70
  denominator_rule: >
    Reconciled in-scope resource-control obligations,
    excluding only independently verified not-applicable items.
  numerator_rule: >
    Requirements with current, trusted, scope-matching
    verified implementation and effectiveness evidence.
  zero_denominator_rule: "N/A; never automatically 100%"
critical_risk:
  public_confidential_storage_findings: ["<FINDING_IDS>"]
  excessive_production_admin_roles: ["<ROLE_FINDING_IDS>"]
  known_exploited_runtime_exposure: ["<VULN_FINDING_IDS>"]
  high_risk_inconclusive: ["<SCENARIO_IDS>"]
control_evidence:
  - requirement_id: CA-REQ-07
    resource_id: "<CANONICAL_STORAGE_RESOURCE_ID>"
    result: "<VERIFIED_PASS_FAIL_INCONCLUSIVE>"
    configuration_ref: "<EFFECTIVE_ACCESS_POLICY>"
    negative_test_ref: "<SYNTHETIC_ACCESS_TEST_ID>"
    observed_at: "<ISO_8601_UTC>"
    collector_id: "<TRUSTED_SOURCE>"
    reviewer: "<REVIEWER>"
  - requirement_id: CA-REQ-14
    resource_id: "<CANONICAL_LOGGING_SOURCE_ID>"
    result: "<VERIFIED_PASS_FAIL_INCONCLUSIVE>"
    source_health_ref: "<LOG_DELIVERY_TEST>"
    observed_at: "<ISO_8601_UTC>"
findings:
  open_ids: ["<OPEN_FINDING_IDS>"]
  remediations: ["<OWNER_ACTION_DUE_DATE_AND_RETEST>"]
  exception_refs: ["<AUTHORIZED_SCOPED_EXPIRING_EXCEPTIONS>"]
recovery:
  last_restore_exercise_ref: "<RESTORE_DRILL>"
  result: "<PASS_FAIL_INCONCLUSIVE>"
limitations:
  - "<MISSING_PROVIDER_SCOPE_OR_REGIONS>"
  - "<UNVERIFIED_SERVICE_CONTROL_INHERITANCE>"
  - "<EPHEMERAL_RESOURCE_INVENTORY_LAG>"
assessment_decision:
  result: "<PASS_FAIL_INCONCLUSIVE>"
  basis_ref: "<ACCEPTANCE_AND_RISK_POLICY>"
  approved_by: "<AUTHORIZED_DECISION_OWNER>"
  decision_at: "<ISO_8601_UTC>"
reassessment_triggers:
  - "New accounts, projects, regions or exposed routes"
  - "IAM/trust, storage policy or KMS grant change"
  - "New deployment digest, vulnerability or provider advisory"
  - "Logging/collector outage or backup restore failure"
  - "Expired exception, incident or change in risk appetite"
~~~

### 23.2. Evidence bảo vệ thế nào?

Đối với IAM, KMS, logs và configs:
- Không lưu private keys, token, client secrets hoặc customer records trong report.
- Dùng principal/resource IDs, sanitized config diffs, immutable digests và evidence references.
- Giới hạn quyền đọc evidence, có auditing và retention/deletion policy.
- Có record kiểm provenance và integrity.
- Không đưa raw cloud configuration có nội dung nhạy cảm vào public CI artifacts.
- Nếu cần provider report có confidentiality restrictions, lưu ở repository được cấp quyền; chỉ trích metadata/scope vào risk register.

### 23.3. Kết quả test và kết quả tổng thể

Một `control_evidence.result=VERIFIED_PASS` chỉ áp dụng cho requirement/resource cụ thể. `assessment_decision.result` phụ thuộc:
- Acceptance criteria của tổ chức.
- Critical failure/risk hard stops.
- Coverage and uncertainty.
- Applicability và inherited controls.
- Approved exceptions và obligations.
- Reviewer/authority.

Không để một tỷ lệ coverage hoặc tự điền YAML `result: PASS` thay thế **assessment có chứng cứ**.

## 24. Workflow vận hành cloud assurance

~~~mermaid
flowchart TD
    GOV["Define objectives, risk appetite and policy"] --> SCOPE["Reconcile cloud accounts/resources/owners"]
    SCOPE --> MAP["Shared responsibility, applicability and control owners"]
    MAP --> DES["Design / threat-model assessment"]
    DES --> COL["Collect config, runtime, provider and test evidence"]
    COL --> HEALTH{"Evidence trusted, fresh and complete?"}
    HEALTH -- "Không" --> UNC["INCONCLUSIVE + discovery/collector gap"]
    HEALTH -- "Có" --> EVAL{"Requirement acceptance achieved?"}
    EVAL -- "Có" --> PASS["Scoped VERIFIED_PASS"]
    EVAL -- "Không" --> FAIL["Finding + risk/impact assessment"]
    FAIL --> FIX["Owner, containment, remediation or exception"]
    FIX --> RETEST["Verify actual state and original behavior"]
    RETEST --> COL
    PASS --> MON["Change, exploit, drift and provider-event monitoring"]
    UNC --> MON
    MON --> SCOPE
~~~

### Bước 1 – Xác nhận mục tiêu/phạm vi

- Service/business owner, security objectives, data classification, criticality.
- Cloud provider/services, organizations/accounts, environments, regions và asset classes.
- Policy/standard version, obligations và risk tolerance.
- Provider vs customer/shared control ownership.

### Bước 2 – Inventory và applicability

- Reconcile cloud inventory, CMDB, IaC, runtime và SaaS/vendor scope.
- Xác định resource–control obligations và verified exclusions.
- Nhận biết shadow accounts, ephemeral workloads, missing data owners.
- Ghi timestamp/scope version để tái hiện denominator.

### Bước 3 – Đánh giá design/implementation/operation

- Threat model/architecture review.
- IaC và effective cloud policies.
- Runtime identities, network, data, image, logs/backup.
- Safe negative tests và restore/drift exercises.
- Provider report inheritance, scope, periods và customer dependencies.

### Bước 4 – Phân loại outcomes

- VERIFIED_PASS khi có evidence đủ, fresh, đúng scope.
- CONFIRMED_FAIL khi control không đáp ứng acceptance.
- INCONCLUSIVE/NOT_RUN khi thiếu source, asset hoặc test.
- NOT_APPLICABLE chỉ sau khi có rationale/evidence.
- Exception/risk acceptance tách khỏi technical state.

### Bước 5 – Remediation và retest

- Risk-based priority, system/service owner.
- IaC fix, access tightening, key/data controls, network isolation, logging/restore.
- Deploy với change approval.
- Verify actual cloud state và run negative tests.
- Đóng finding với reviewer và evidence.

### Bước 6 – Continuous assurance

- Monitor changes, new accounts/regions, cloud service updates và incidents.
- Trigger re-evaluation trên changed resources và các dependent controls.
- Refresh inherited/vendor evidence khi scope/report period đổi.
- Báo metrics, gaps, exceptions và trend có denominator consistency.
- Họp governance để xử lý systemic issues như missing ownership và unmanaged assets.

## 25. Findings, risk acceptance và escalation

### 25.1. Finding lifecycle

Các trạng thái gợi ý:
- `NEW/UNDER_REVIEW`: signal chưa xác minh đầy đủ.
- `CONFIRMED_OPEN`: behavior/config không đáp ứng requirement.
- `MITIGATED_NOT_FIXED`: risk giảm nhưng weakness còn.
- `EXCEPTION_ACTIVE`: có quyết định sai lệch hợp lệ, **không là technical PASS**.
- `FIXED_AWAITING_RETEST`: change đã deploy nhưng chưa có effectiveness evidence.
- `VERIFIED_CLOSED`: tested actual state đạt acceptance.
- `INCONCLUSIVE`: thiếu source/scope/test.

Technical finding state và exception decision state nên là hai trường/đối tượng độc lập; một approved exception không được tự xóa scanner finding.

### 25.2. Khi nào risk owner phải tham gia?

- Một confidential bucket có đường public read/third-party access.
- Production admin role có trust/permissions vượt risk appetite.
- Cloud logging không thu events trong một region quan trọng.
- KMS/secret hoặc backup isolation không còn phù hợp.
- Provider service incident có thể tác động dữ liệu.
- Patch/fix không thể triển khai trước deadline.
- Managed service không đủ evidence để hỗ trợ nghĩa vụ trọng yếu.
- Control failure có khả năng tạo privacy/operational incidents.

**Approval phải đúng thẩm quyền và không trái obligations bắt buộc.** Active exploitation hoặc confirmed incident thường cần incident response/emergency escalation thay vì chờ quarterly exception review.

### 25.3. Điều kiện của một exception có thời hạn

- Finding/requirement và exact cloud resources/account/region.
- Technical reason chưa remediate được.
- Risk scenario/current/residual risk và uncertainty.
- Compensating controls **đã verified** cùng limitations.
- Risk owner approval và authority record.
- Starts/expires, review cadence, immediate invalidation triggers.
- Monitoring/alert owner.
- Remediation milestones và exit plan.
- CI/CSPM exception policy không xóa raw findings.
- Reassess khi exposure/trust/provider advisory/known exploit đổi.

### 25.4. Escalation theo risk, không theo tỷ lệ trung bình

Một enterprise có 20.000 resource-control pairs, coverage rất cao, nhưng có thể tồn tại **một root/organization role quá rộng** hoặc một object store chứa records quan trọng được public. Phải có hard stops/escalation theo approved risk policy. Không dùng trung bình tổng để che single-point-of-failure.

## 26. Case study 1 – Object storage “đã mã hóa” nhưng vẫn lộ dữ liệu

### 26.1. Bối cảnh

Một nền tảng Java/Spring Boot chạy trên cloud:
- `report-api` phục vụ khách hàng từ nhiều tenants.
- Object storage lưu PDF/CSV reports có dữ liệu confidential.
- Gateway/API thực hiện OIDC authentication.
- Worker có workload identity để tạo file export.
- Object storage bật **encryption at rest** với KMS.
- CSPM báo rule mã hóa **PASS**.
- API trả signed download URLs cho người dùng khi export xong.

Nhóm product nói: “Bucket đã mã hóa nên confidentiality được bảo đảm.”

### 26.2. Threat scenario

Một object có thể bị đọc trái phép qua:
1. Direct resource access policy quá rộng.
2. Cross-account principal không còn thuộc allowlist.
3. Signed URL thời hạn quá dài hoặc không bind scope.
4. API authorization lỗi: tenant A được URL của report B.
5. Worker lưu file dưới prefix không đúng tenant.
6. Logs/backup/replica copy khác bị public hoặc accessible rộng.
7. Cache/CDN trả file thuộc tenant khác.
8. KMS principal có quyền decrypt rộng khi application route không kiểm ownership.

Encryption at rest chỉ hỗ trợ bảo vệ một phần dữ liệu; nếu một API hợp lệ decrypt rồi phục vụ report sai tenant, **mã hóa không ngăn disclosure**.

### 26.3. Assurance claim phải sửa lại

**Claim quá rộng:** “Mọi báo cáo an toàn vì storage encrypted”.

**Claim đánh giá được:**
> Trong phạm vi production bucket X tại account A/region R và deployments của report-api trong release D, confidential report objects phải chỉ được đọc bởi các workload principals đã được cấp quyền; API download URLs chỉ được phát hành cho actor có quyền trên resource/tenant, trong effective time window của policy. Evidence phải bao phủ effective policies, data paths và negative tests phù hợp.

### 26.4. Bộ controls và evidence

| Security requirement | Control | Bằng chứng cần |
| --- | --- | --- |
| Storage không public | Resource/org access policy | Effective config, deny test với test principal |
| Workload chỉ đọc/ghi prefix đúng | Least-privilege role + resource policy | IAM effective permissions, deny outside prefix |
| Data encrypted | Approved encryption/key settings | Actual resource/key ID và KMS policy |
| Tenant isolation | Server-side report ownership check | Synthetic tenant A/B negative test |
| Signed URLs có hạn | URL policy/expiry, authZ at issuance | Expired/wrong-tenant test |
| Audit trail | Object access + API audit events | Source health và synthetic access record |
| Backup/replica protected | Replica encryption/access control | Separate resource inventory/policy test |
| Scope liên tục | Drift alert và onboarding | New bucket/policy-change test |

### 26.5. Các quan sát giả định

- Bucket encrypted bằng approved key → `CA-REQ-08` có thể PASS trong scope sau verification.
- Resource policy không public → một control `CA-REQ-07` có thể PASS.
- Nhưng API với tenant A lấy được signed URL cho synthetic report B → **FAIL `CA-REQ-25`** về tenant/object-level authorization.
- Một replication bucket ở region khác chưa onboard inventory → **INCONCLUSIVE** đối với coverage toàn bộ copies.
- Log delivery từ một source bị tắt → **FAIL/INCONCLUSIVE** cho detection requirement tùy bằng chứng.

**Kết luận:** không thể tuyên bố confidentiality assurance PASS tổng thể, dù encryption rule green. Cloud và application controls phải đánh giá cùng trust path.

### 26.6. Remediation và retest

1. Sửa server-side ownership và field-level policy tại API.
2. Giới hạn export worker role/prefix và signed-URL issuance.
3. Kiểm effective key/storage policies, backup/replicas.
4. Onboard missing region/account inventory/logs.
5. Retest synthetic tenant A→report B: deny và không URL/file.
6. Retest expired URL và role ngoài scope.
7. Đối chiếu deployed artifact, KMS/logging status, reviewers.
8. Theo dõi regression khi đổi API/tenant/workload policy.

**Không truy xuất dữ liệu khách hàng thật** chỉ để chứng minh sai lệch; synthetic object và negative authorization test được phép thường đủ.

## 27. Case study 2 – CI federation có quá nhiều quyền

### 27.1. Bối cảnh

Tổ chức triển khai Spring Boot applications bằng CI/CD:
- Pull request chạy tests.
- Trusted release workflow ký và publish container images.
- OIDC federation cho CI nhận short-lived cloud credentials.
- Production deployment role được phép thay compute/configuration.
- Risk review phát hiện trust policy chỉ giới hạn issuer nhưng không kiểm đầy đủ repository/ref/workflow context.
- Cloud posture tool báo “không có long-lived access keys” và dashboard identity xanh.

### 27.2. Threat model

Nếu trust policy không phân biệt untrusted PR context với approved release, một workflow không được duyệt có thể được cấp production role dù không có static secret. Rủi ro không phụ thuộc việc người tấn công đã dùng quyền thật trong assessment; **design/implementation conditions sai đã là gap cần xử lý**.

### 27.3. Safe assurance plan

| Bước | Phép kiểm | Evidence |
| --- | --- | --- |
| Inventory | CI workflows, trust policies, production roles | Approved workflow and identity list |
| Design review | Issuer/audience/subject/context binding | Threat model và trust requirement |
| Effective state | Trust policy/deploy role permissions đang áp | Current provider IAM config |
| Negative test | Untrusted **test** workflow principal trong sandbox xin role được bảo vệ | DENY audit event |
| Positive test | Approved release identity trong test environment | Conditional ALLOW theo policy |
| Pipeline review | PR không được chỉnh production policy/secret scope | Change/approval evidence |
| Runtime bind | Image digest từ trusted release tới actual production | Artifact/deployment provenance |
| Alerting | Unexpected role assume attempts bị phát hiện | Log/alert source-health |

**Không cần lấy production credential hoặc thực hiện mutation** để chứng minh một trust condition quá rộng. Có thể dùng policy simulation và sandbox principal; mọi active IAM tests phải ở environment/role đã được cấp quyền.

### 27.4. Remediation

- Thu hẹp federation trust theo approved CI provider/repository/workflow/ref/environment/audience semantics.
- Đặt least-privilege deployment permissions cho từng service/environment.
- Tách untrusted PR jobs khỏi release credentials/cache/runners.
- Bảo vệ branch/environment approvals và workflow changes.
- Sử dụng short-lived sessions với audit/alerts.
- Review roles/resource policies mà CI identity có thể assume.
- Pin/verify artifact provenance và image digest khi deploy.
- Thêm negative tests vào CI trust policy review.

### 27.5. Assurance claim và limitation

> Trong phạm vi release workflow đã được kiểm, untrusted test principal không thể nhận role dành riêng cho production và approved release identity có quyền đúng scope theo effective trust/resource policies. Phép đo có evidence từ policy và synthetic denial; không tuyên bố mọi provider workflow hay mọi historical deployment đã được kiểm.

Một tool signal “no static keys” là **một dấu hiệu tốt**, không tự chứng minh entitlement và workload federation an toàn.

## 28. Case study 3 – Centralized logging và regional recovery

### 28.1. Bối cảnh

Cloud organization có các accounts:
- `security-logging` dành cho audit/detection.
- `production-a` và `production-b` triển khai API cùng dữ liệu.
- `backup-recovery` giữ backups được phân quyền riêng.
- Một region có log source hoạt động, region còn lại không gửi data access events.
- Backups báo success, nhưng chưa có restore drill đầy đủ.

Dashboard tổng hợp:
> “Logging enabled everywhere, backup 100% successful.”

### 28.2. Những câu hỏi cần điều tra

1. Có inventory **tất cả** accounts/regions và event sources expected chưa?
2. Cloud provider có mặc định cung cấp những event classes nào; có cần bật data access logs riêng không?
3. Collector nhận events thực tế, có delay/drop không?
4. Tài khoản production admin có quyền tắt/xóa cả log sink không?
5. Detection rule có synthetic test event và on-call response?
6. Recovery backups nằm trong trust domain nào; compromised primary role có thể xóa?
7. RTO/RPO đã định nghĩa theo business objective?
8. Restore có cần KMS keys, application image, secrets và DNS/failover?
9. Recovery procedure có chạy trong lab/controlled environment?
10. Provider shared-responsibility report bao phủ dịch vụ/thời kỳ nào?

### 28.3. Assurance matrix

| Control | Evidence có | Chưa có | Đánh giá |
| --- | --- | --- | --- |
| Audit source configuration | Log configuration trong 2 regions | Data event source region B | Gap; không PASS toàn scope |
| Central log delivery | Một số control-plane events đến sink | Region B delivery test | INCONCLUSIVE cho source B |
| Detection | Rule config tồn tại | Synthetic end-to-end alert exercise | Chưa xác minh operating effectiveness |
| Backup configured | Scheduled jobs SUCCESS | Restore test và integrity check | Không kết luận recoverable |
| Backup isolation | Separate account | Effective denial của primary compromised role | Cần test/review |
| Recovery RTO/RPO | DR plan | Measured exercise | INCONCLUSIVE |
| Provider controls | Report có service scope | User controls/CUECs chưa map | Partial inheritance |

### 28.4. Kế hoạch khắc phục

- Hoàn thiện expected event inventory theo accounts/regions/services.
- Bật đúng events cần thiết, bảo vệ central sink và kiểm delivery end-to-end.
- Tạo synthetic audit event trong sandbox/approved scope.
- Test alerts và incident runbook theo schedule.
- Kiểm effective deny quyền xóa backups/logs của roles không được duyệt.
- Thực hiện restore drill với synthetic data và đo outcomes theo approved RTO/RPO.
- Reconcile provider evidence và customer responsibilities.
- Lưu findings/limitations theo từng account/region, không làm green tổng thể.

**Bài học:** hoạt động “configured” không đủ chứng minh “operating”; mục tiêu bảo mật availability và incident detection cần được đo bằng tests thực tế, phù hợp safety.

## 29. Bài tập thực hành

### Bối cảnh

Bạn là assessor cho nền tảng `security-assurance-learning` triển khai đa tài khoản trên cloud:
- Hai production accounts và một security account.
- Một staging account mới nhưng chưa nối CSPM.
- Một region chạy Java/Spring Boot API và Kafka worker.
- Một region dùng managed database và object storage replicas.
- CI OIDC federation cấp role deploy.
- Kubernetes production có container image digests và một CronJob dùng image cũ.
- Một confidential bucket đã mã hóa nhưng có policy allow external principal.
- Central audit logs có missing source ở một region.
- Vendor cung cấp report về managed database platform nhưng không bao phủ tenant DB roles.
- Một backup job SUCCESS nhưng chưa restore.
- Một exception đã duyệt cho legacy runtime và sắp hết hạn.

### Yêu cầu

1. Viết **ba scoped assurance claims** cho identity, confidentiality và resilience.
2. Vẽ DFD/control-plane và data-plane trust boundaries.
3. Tạo shared-responsibility matrix cho VM, Kubernetes, managed DB và SaaS phụ trợ.
4. Liệt kê accounts/regions/resources cần inventory, phân biệt source của resource vs owner/classification.
5. Định nghĩa control obligation theo `(account, region, resource, requirement, policy version)`.
6. Phân loại bucket external policy, image cũ, logging missing, unknown vendor evidence, exception và backup success vào PASS/FAIL/INCONCLUSIVE.
7. Đề xuất **ít nhất 12 negative/failure tests** trên resources được phép để chứng minh controls.
8. Mô tả một IAM federation deny test cho untrusted test workflow.
9. Đánh giá KMS key use policy và backup key recovery dependencies.
10. Định nghĩa evidence freshness và change-trigger invalidation cho IAM, bucket, image và provider reports.
11. Viết ít nhất **10 CA-REQ IDs**, kèm owner, risk, test và acceptance.
12. Viết YAML evidence register theo mục 23 cho assessment **chưa thực hiện**, để `state: PLANNED` và result placeholders.
13. Tính technical coverage nếu có 120 candidates, 12 NA verified, 75 PASS, 10 FAIL, 7 exceptions, 10 INCONCLUSIVE, 6 NOT_RUN.
14. Thiết kế dashboard có absolute critical findings, unknown sources, expired exceptions, recent drift và measured coverage.
15. Lập remediation plan cho external bucket policy và old CronJob image.
16. Thiết kế restore drill với synthetic data, RTO/RPO đã phê duyệt và evidence hạn chế.
17. Ghi một vendor/CUEC mapping cho managed DB và tenant customer controls.
18. Giải thích tại sao CSPM dashboard green không bảo đảm business tenant authZ.
19. Viết một finding report với observed behavior, risk, scope, mitigation và retest plan.
20. Viết concluding assurance claim ghi PASS/FAIL/INCONCLUSIVE, reviewer và những limitations không thể bỏ qua.

### Hướng giải: dữ liệu ví dụ câu 13

~~~text
Eligible = 120 - 12 = 108
Verified PASS = 75
Technical assurance coverage = 75 / 108 × 100 ≈ 69.44%

Confirmed FAIL = 10
Exception (not technical PASS) = 7
INCONCLUSIVE = 10
NOT_RUN = 6
Unresolved / not verified PASS = 33
~~~

**Không cộng exception vào PASS**, không loại NOT_RUN/INCONCLUSIVE khỏi denominator và không báo 100% nếu missing cloud accounts/regions làm population không đầy đủ.

### Câu hỏi nâng cao

CSPM báo **100% encrypted object storage** cho 30 buckets đã kết nối. Organization API cho biết có 8 buckets ở account chưa onboard. Một trong 30 buckets có signed URL cho report của tenant B được API phát hành sai cho user A.

**Có thể tuyên bố confidentiality PASS không?**

**Gợi ý:** không. Tỷ lệ 100% chỉ cho **encryption configuration của 30 buckets được scan**, không bao phủ 8 buckets thiếu visibility và không chứng minh authorization/signed URL của application. Cần sửa inventory, đánh giá access paths và test cross-tenant với synthetic data; kết luận global confidentiality **FAIL/INCONCLUSIVE theo các requirements**, không đồng nhất với encryption check PASS cục bộ.

## 30. Các ngộ nhận và anti-patterns

| Ngộ nhận | Vì sao sai? | Thực hành đúng |
| --- | --- | --- |
| “Cloud provider bảo mật hết.” | Customer controls vẫn có trách nhiệm | Service-specific responsibility map |
| “Provider có certification nên app compliant.” | Provider scope khác tenant/application | Inheritance + customer testing |
| “CSPM 100% nghĩa là an toàn.” | Blind spots, rule limits và business risk | Scoped requirements/evidence |
| “Số accounts đã nối scanner là toàn bộ.” | Shadow accounts/regions bị bỏ | Org-level reconciliation |
| “Một screenshot policy là evidence đủ.” | Có thể sai resource/time hoặc drift | Effective-state and runtime tests |
| “Mọi account có cùng controls.” | Services/regions/provider semantics khác | Applicability mapping |
| “MFA enabled là admin access an toàn.” | Permission/session/break-glass còn risk | IAM effectiveness |
| “Không có long-lived keys là federation an toàn.” | CI trust/subject condition có thể sai | Trusted federation negative tests |
| “Private IP nghĩa là không Internet-reachable.” | Gateway/proxy/peering có thể mở path | Effective network route analysis |
| “Có WAF nghĩa backend authZ đúng.” | WAF chỉ kiểm một đường | Server-side resource authorization |
| “Encrypt at rest nghĩa data không lộ.” | Authorized route có thể trả sai data | Access/tenant tests |
| “KMS rotation tự ngăn credential misuse.” | Permissions/usage vẫn cần kiểm | Key policy và log evidence |
| “Bucket private nghĩa report download secure.” | Signed URL và API authZ có thể lỗi | End-to-end data paths |
| “Image đã ký nghĩa không có lỗ hổng.” | Integrity khác vulnerability | SCA + runtime verification |
| “CI deploy PASS nghĩa prod đã fixed.” | Runtime có thể chạy digest cũ | Actual deployment binding |
| “Managed Kubernetes nghĩa không cần RBAC/network.” | Workload/tenant controls vẫn thuộc customer | Shared responsibility verification |
| “Backup SUCCESS nghĩa có thể restore.” | Chưa test integrity/keys/recovery | Restore drill/RTO/RPO |
| “Logs enabled nghĩa incident detectable.” | Source delivery/alert có thể fail | Synthetic detection exercise |
| “Zero alerts là zero threats.” | Monitoring source có thể down | Source health/coverage |
| “NOT_APPLICABLE không cần evidence.” | Có thể loại sai denominator | Verified applicability |
| “Missing resources khỏi tính để % đẹp.” | Tạo false green | Unknown/visibility gap |
| “Có approved exception là technical PASS.” | Risk acceptance không sửa control | Tách decision và technical status |
| “Provider report luôn mới và áp dụng mọi region.” | Scope/period/carve-outs | Evidence limitation review |
| “Hạ severity vì asset internal.” | Privileged/insider paths vẫn tồn tại | Reachability và impact assessment |
| “Dùng một metric để quyết định release.” | Single critical risk có thể bị che | Risk-based hard stops |
| “Audit một lần đủ.” | Cloud drift và ephemeral workloads | Event-driven continuous assurance |
| “Sửa IaC đủ, khỏi retest.” | Deployed state có thể khác | Post-deploy effective tests |
| “Staging PASS nghĩa production PASS.” | Config/roles/regions khác | Scoped transfer of evidence |
| “Old screenshot vẫn hợp lệ nếu mới 24h.” | Change event có thể invalid ngay | Event-triggered invalidation |
| “Không biết source thì để PASS tạm.” | Không có bằng chứng | INCONCLUSIVE và finding |

## 31. Checklist triển khai cloud security assurance

### 31.1. Governance và scope

- [ ] Security objectives, business risks và applicable obligations rõ.
- [ ] Cloud provider/service models và shared responsibility được lập.
- [ ] Resource/control owner và assessor/reviewer xác định.
- [ ] Organization, accounts, projects, subscriptions, regions thuộc scope đầy đủ.
- [ ] Asset inventory, CMDB, IaC, deployed workloads và source health reconcile.
- [ ] Data classification, service criticality, exposure, tenant boundaries rõ.
- [ ] Policy/control catalog có version, requirements và applicability.
- [ ] Provider/inherited evidence đúng service, region, period và CUECs.
- [ ] Shadow accounts/unknown resources được quản lý như coverage gaps.

### 31.2. Kỹ thuật và kiểm chứng

- [ ] IAM, federation, privileged access và service roles có effective evidence.
- [ ] Public routes, network ingress/egress và resource policies được kiểm.
- [ ] Storage/data encryption và KMS policy/key usage có evidence.
- [ ] Kubernetes/VM/serverless/managed services kiểm đúng responsibility.
- [ ] IaC policy-as-code có test và không bị bypass sau deploy.
- [ ] Artifact/image digest gắn actual runtime, không chỉ CI.
- [ ] Logs/alert/source-health hoạt động end-to-end.
- [ ] Backup/restore/DR có exercises với outcomes đo được.
- [ ] Business object/tenant authorization được test riêng với synthetic fixtures.
- [ ] Negative/failure tests có approval/safety boundaries.

### 31.3. Evidence và decision

- [ ] Control evidence có asset ID, requirement ID, time, source, policy version.
- [ ] Effective config và operating evidence được phân biệt.
- [ ] No-secret/no-PII evidence handling và retention đúng policy.
- [ ] Missing/stale/conflicting evidence không tự thành PASS.
- [ ] Exclusions và inherited controls có rationale và reviewer.
- [ ] Coverage có numerator/denominator và metric definition minh bạch.
- [ ] Absolute critical risk gaps và unscanned assets được báo riêng.
- [ ] Exceptions có risk owner, scope, expiry và không tăng technical PASS.
- [ ] Assessment có PASS/FAIL/INCONCLUSIVE và limitations rõ.
- [ ] Reviewer/case history/evidence refs cho phép audit lại.

### 31.4. Vận hành liên tục

- [ ] New accounts/regions/resources trigger onboarding và reassessment.
- [ ] IAM trust, policy, key, network, storage public access changes trigger checks.
- [ ] Runtime image/function/worker changes trigger tests phù hợp.
- [ ] Logging outages, drift, provider advisories và incidents được phát hiện.
- [ ] Findings có owner, risk priority, remediation và retest deadlines.
- [ ] Patch/permission/data misconfiguration fix được verify trên actual state.
- [ ] Rollback/regression có thể reopen finding và invalidate evidence.
- [ ] Restore/security exercises chạy theo risk và có kết quả cụ thể.
- [ ] Metrics không bỏ qua UNKNOWN, incomplete inventory hoặc high-impact exceptions.
- [ ] Service/security/risk owners review những critical gaps định kỳ và khi có trigger.

## Ghi nhớ

- **Cloud security assurance là chương trình xác minh bằng chứng rằng cloud controls đáp ứng security objectives trong phạm vi và thời điểm được xác định**, không chỉ bật công cụ posture.
- **Shared responsibility phải map theo từng service/control:** provider-operated evidence có thể được kế thừa có điều kiện; tenant configuration, identities, data và application vẫn cần customer assurance.
- **Control plane và data plane đều quan trọng:** IaC/config PASS không tự chứng minh behavior runtime, còn API deny không tự bảo đảm privileged cloud role không thể bypass.
- **Inventory đủ accounts/projects/regions/ephemeral resources** là điều kiện để denominator đáng tin; missing telemetry, UNKNOWN và stale observations không tự biến thành PASS.
- Kiểm IAM, federation, network, storage, KMS, workloads, supply chain, logging, backup/restore, business authorization theo **risk và trust boundaries**.
- **CSPM/CNAPP, provider audit reports, standards và policy-as-code là nguồn evidence/tham chiếu**, không tự thay actual-state verification và reviewer quyết định.
- Evidence phải gắn **resource identity, requirement, policy, source, timestamp, effectiveness test, tool/version, reviewer, limitations** và được bảo vệ khỏi secret/PII leak.
- Approved exception là quyết định quản trị risk trong phạm vi/thời hạn, **không tự sửa technical control**; remediation cần actual-state retest.
- Cloud thay đổi nhanh, nên assurance cần **continuous monitoring, change-triggered reassessment, drift detection, incident handoff và recovery verification**.
- Trong **SECURITY_SECURITY_ASSURANCE**, duy trì chuỗi **risk → objective → requirement → ownership → control → test → evidence → finding → remediation/retest → reassessment** để bảo vệ cloud một cách có thể giải trình và kiểm toán.





