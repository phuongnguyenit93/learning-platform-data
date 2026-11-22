# Quản lý cấu hình, phát hiện drift và tài nguyên ngoài chuẩn

## Mục tiêu học tập

Trong môi trường cloud, hạ tầng và cấu hình ứng dụng thay đổi liên tục. Một nhóm tạo resource bằng Infrastructure as Code (IaC), nhóm khác chỉnh thủ công để xử lý sự cố, pipeline cập nhật image hoặc policy, dịch vụ managed thay đổi metadata, còn tài khoản thử nghiệm tạo resource ngoài quy trình. Theo thời gian, trạng thái thực tế có thể khác với cấu hình đã được phê duyệt. Hiện tượng đó gọi là **configuration drift**.

Nếu không kiểm soát drift, môi trường production có thể khác staging, security group mở rộng ngoài ý muốn, database chạy sai backup policy, encryption hoặc logging bị tắt, và chi phí tăng vì tài nguyên không có owner. Chỉ triển khai IaC nhưng không liên tục đối chiếu trạng thái thực tế vẫn chưa đủ để duy trì kiểm soát.

Bài học này trình bày cách quản lý cấu hình, phát hiện drift và xử lý tài nguyên ngoài chuẩn trong kiến trúc cloud. Nội dung bao gồm desired state, source of truth, IaC, configuration inventory, change management, policy-as-code, drift detection, remediation, exception handling, audit evidence và trách nhiệm vận hành.

Bài học thuộc chương **Quản trị và tuân thủ**, tập trung vào **quản lý cấu hình, phát hiện drift và tài nguyên ngoài chuẩn**. Trong bối cảnh Cloud Architecture, các quyết định phải kết nối yêu cầu nghiệp vụ với network, compute, data, deployment model và controls; đồng thời cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt desired state, actual state, configuration baseline và drift.
- Xác định source of truth và ownership cho từng loại cấu hình/resource.
- Thiết kế quy trình thay đổi cấu hình qua IaC, review, approval và deployment.
- Phân loại drift do thay đổi thủ công, automation, provider, state loss hoặc lỗi pipeline.
- Phát hiện drift bằng plan, cloud inventory, config rules, audit logs và policy evaluation.
- Phân biệt resource unmanaged, orphaned, shadow IT và resource hợp lệ có ngoại lệ.
- Thiết kế remediation an toàn, có kiểm soát blast radius và rollback.
- Áp dụng policy-as-code, preventive guardrails và continuous compliance.
- Quản lý exception, risk acceptance, owner, expiry và evidence.
- Kiểm soát secret, encryption, network, identity, backup, tags và data residency.
- Xây dashboard, alert, KPI và quy trình audit có thể tái lập.
- Đánh giá chi phí và mức tự động hóa phù hợp với từng workload.

## 1. Configuration drift là gì?

Configuration drift xảy ra khi cấu hình hoặc resource đang chạy khác với trạng thái được mong đợi, phê duyệt hoặc khai báo trong hệ thống quản lý cấu hình.

Ví dụ, IaC khai báo database chỉ chấp nhận kết nối từ private application subnet. Người vận hành mở thêm dải IP công cộng để điều tra sự cố rồi quên đóng lại. Database vẫn chạy, application vẫn hoạt động, nhưng trạng thái thực tế đã lệch khỏi baseline bảo mật.

Các dạng drift thường gặp:

- **Manual drift:** thay đổi bằng console, CLI hoặc script ngoài pipeline.
- **Automation drift:** controller, autoscaler hoặc pipeline khác sửa resource.
- **Provider-managed change:** dịch vụ cloud thay đổi thuộc tính do maintenance, version hoặc feature.
- **State drift:** file state của IaC không còn khớp tài nguyên thực tế hoặc bị mất.
- **Code drift:** cấu hình trong repository khác bản đã deploy.
- **Environment drift:** dev, test, staging và production có cấu hình không tương thích ngoài chủ đích.
- **Dependency drift:** phiên bản image, package, runtime, module hoặc policy thay đổi ngoài baseline.
- **Unmanaged resource:** resource tồn tại nhưng không có owner, IaC source hoặc record quản lý rõ ràng.

Không phải mọi khác biệt đều là lỗi. Một thuộc tính có thể được provider cập nhật tự động, autoscaler thay đổi số replica theo tải hoặc một ngoại lệ được phê duyệt theo thời hạn. Cần xác định ai sở hữu trạng thái, thay đổi có được phép không và bằng chứng phê duyệt nằm ở đâu.

### 1.1. Desired state và actual state

- **Desired state:** cấu hình đích đã được phê duyệt trong IaC, config repository, policy hoặc hệ thống quản lý cấu hình.
- **Actual state:** trạng thái đang tồn tại trong cloud account, cluster, operating system hoặc application runtime.
- **Baseline:** tập quy tắc tối thiểu phải đáp ứng cho một loại workload/environment.
- **Drift:** sai khác cần được đánh giá giữa desired và actual state.
- **Reconciliation:** quá trình phát hiện và đưa actual state về trạng thái mong muốn hoặc ghi nhận ngoại lệ hợp lệ.

~~~mermaid
flowchart LR
    SRC["IaC / Config repository"] --> DES["Desired state"]
    DES --> DEPLOY["Deployment / Controller"]
    DEPLOY --> CLOUD["Cloud resources"]
    CLOUD --> ACT["Actual state"]
    ACT --> SCAN["Drift detection"]
    DES --> SCAN
    SCAN --> FIND["Classify findings"]
    FIND --> FIX["Remediate / Exception"]
    FIX --> CLOUD
    FIX --> SRC
~~~

### 1.2. Configuration drift khác vulnerability và compliance finding ra sao?

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Configuration drift | Actual khác desired/baseline | Security group có rule không nằm trong IaC |
| Vulnerability | Điểm yếu có thể bị khai thác | Runtime/package có CVE |
| Compliance finding | Không đáp ứng control/quy định | Log retention thấp hơn yêu cầu |
| Misconfiguration | Cấu hình sai hoặc không an toàn | Public bucket chứa dữ liệu restricted |
| Unmanaged resource | Resource không có lifecycle/owner quản lý rõ | VM được tạo thủ công trong account production |

Một resource có thể đồng thời drift, misconfigured và tạo compliance finding. Phân loại giúp chỉ định owner và remediation đúng.

## 2. Xây dựng source of truth cho cấu hình

Drift detection không thể đáng tin nếu không biết đâu là trạng thái chuẩn. Mỗi loại resource/configuration cần có nguồn sự thật và người chịu trách nhiệm.

### 2.1. Các nguồn chuẩn có thể dùng

| Phạm vi | Source of truth có thể dùng | Owner |
| --- | --- | --- |
| Cloud infrastructure | IaC repository và state backend | Platform/Cloud team |
| Kubernetes workload | GitOps repository/Helm/Kustomize | Application/platform team |
| OS baseline | Image pipeline/config management | Compute/platform team |
| Application configuration | Config repository hoặc config service có version | Service owner |
| Identity/access policy | IAM policy repository và approval record | Security/IAM team |
| Network policy | Network IaC và architecture baseline | Network team |
| Database parameters | Database configuration repository/change record | DBA/data platform |
| Security controls | Policy-as-code và control catalog | Security/compliance |
| Container image | Immutable artifact registry và build provenance | Engineering/Supply chain |

Không nên có nhiều nguồn chuẩn cùng ghi vào một thuộc tính mà không có thứ tự ưu tiên. Ví dụ console, Terraform và GitOps cùng quản lý replica count có thể liên tục ghi đè lẫn nhau.

### 2.2. Một owner cho mỗi thuộc tính được quản lý

Một resource có thể được quản lý bởi nhiều tool, nhưng mỗi thuộc tính quan trọng nên có owner rõ. Ví dụ:

- Terraform quản lý VPC, subnet, route và security group.
- Kubernetes controller quản lý replica count.
- HPA thay đổi replica theo metric.
- Application deployment quản lý image/version.
- Secret manager quản lý secret value; IaC chỉ tham chiếu secret.

Nếu Terraform liên tục ép replica count về 3 trong khi HPA điều chỉnh lên 8, pipeline có thể tạo drift giả hoặc phá auto-scaling. Cần xác định thuộc tính nào được controller tự do thay đổi và thuộc tính nào vẫn phải khóa theo baseline.

### 2.3. Baseline theo environment và workload

Không dùng một cấu hình chung cho mọi workload. Baseline có thể chia theo production, staging, development, sandbox; public-facing hay internal-only; data processing hay regulated workload; criticality tier; tenant isolation model; data classification; region/residency requirement và deployment model.

Production database thường có yêu cầu backup/PITR, encryption, private network và audit cao hơn môi trường ephemeral. Sandbox vẫn cần guardrail chống public exposure và kiểm soát chi phí.

## 3. Quản lý cấu hình bằng Infrastructure as Code

IaC mô tả hạ tầng bằng code có thể review, version, test và triển khai lặp lại. IaC tạo desired state rõ ràng, nhưng không bảo đảm mọi thay đổi đều đi qua pipeline.

### 3.1. Quy trình thay đổi chuẩn

~~~mermaid
flowchart TD
    CHANGE["Change request"] --> BRANCH["Version-controlled change"]
    BRANCH --> REVIEW["Peer / security review"]
    REVIEW --> VALIDATE["Lint / test / policy check"]
    VALIDATE --> PLAN["Plan and impact review"]
    PLAN --> APPROVE["Approval by authorized owner"]
    APPROVE --> APPLY["Apply through controlled pipeline"]
    APPLY --> VERIFY["Post-deploy verification"]
    VERIFY --> AUDIT["Record version, actor, evidence"]
~~~

Quy trình này tạo bằng chứng ai thay đổi gì, tại sao, review bởi ai, pipeline nào triển khai và kết quả ra sao.

### 3.2. Ví dụ Terraform minh họa

~~~hcl
resource "aws_s3_bucket_public_access_block" "data" {
  bucket = aws_s3_bucket.data.id

  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}
~~~

Ví dụ minh họa trên một provider. Cấu hình thực tế cần thêm bucket policy, key policy, lifecycle, logging và quyền truy cập phù hợp; tên resource/argument tùy provider và version. Không copy nguyên mẫu vào production nếu chưa kiểm tra yêu cầu data classification và KMS ownership.

### 3.3. State backend và locking

IaC state có thể chứa metadata nhạy cảm và mapping giữa resource với code. Cần:

- Lưu state trong backend được bảo vệ, mã hóa và backup.
- Bật locking/concurrency control theo khả năng tool.
- Giới hạn quyền đọc/ghi state.
- Không lưu state trong repository công khai.
- Tách state theo account/environment/workload hợp lý.
- Có recovery procedure khi state hỏng hoặc resource bị import sai.
- Audit thao tác state, import, move, replace hoặc force-unlock.

State mất hoặc stale có thể khiến IaC nghĩ resource chưa tồn tại và tạo trùng, hoặc không còn quản lý resource đã có. Không sửa state thủ công tùy tiện để che drift.

### 3.4. Immutable và mutable configuration

Có thể ưu tiên immutable infrastructure cho image, container và deployment artifact: thay vì sửa VM đang chạy, build image mới và rollout. Một số runtime config như feature flag, policy threshold hoặc scaling vẫn cần thay đổi động.

Phân biệt:
- Artifact immutable: image/package có version/digest.
- Desired config versioned: commit/config release có ID.
- Runtime state dynamic: autoscaler, lease, controller state.
- Secret mutable: được rotate theo policy nhưng không lộ trong diff.
- Provider-managed attribute: chỉ quan sát hoặc chấp nhận thay đổi trong phạm vi đã xác định.

## 4. Phát hiện drift: so sánh desired và actual

Drift detection cần phủ cả resource, config và runtime state. Không có một công cụ đơn lẻ nhìn thấy mọi lớp.

### 4.1. Các phương pháp

| Phương pháp | Phạm vi | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| IaC plan/refresh | Resource được IaC quản lý | Cho biết thay đổi so với state/code | Có thể bỏ sót unmanaged resource ngoài scope |
| Cloud asset/config inventory | Tài sản và cấu hình toàn account | Phát hiện resource không có trong IaC | Cần mapping ownership và baseline |
| Cloud audit logs | Actor và lịch sử API/config change | Điều tra ai làm gì, khi nào | Không phải mọi runtime state đều có event dễ đọc |
| Policy evaluation | Kiểm tra resource theo rule | Tự động phát finding | Rule có thể thiếu context |
| Kubernetes reconciliation | Cluster object so với Git/manifest | Liên tục đồng bộ desired state | Cần xử lý controller-owned fields |
| Host configuration scanning | OS/package/config | Phát hiện drift trên VM/node | Cần agent/credential và scale phù hợp |
| Runtime monitoring | Process, network, behavior | Phát hiện thay đổi đang tác động | Không nhất thiết biết desired state |
| Vulnerability/config scanning | Image, package, service settings | Phát hiện rủi ro kỹ thuật | Không thay thế ownership và approval |

### 4.2. IaC plan không phải inventory toàn cloud

Nếu một resource được tạo thủ công ngoài module/state, Terraform plan của repository hiện có có thể không biết resource đó tồn tại. Vì vậy cần kết hợp:

1. Resource inventory toàn account/subscription/project.
2. Mapping resource ID với IaC state/repository/owner.
3. Policy/baseline evaluation.
4. Audit logs để xác định nguồn thay đổi.
5. IaC plan cho các resource đã được quản lý.

### 4.3. Drift detection theo chu kỳ và event-driven

- **Scheduled scan:** chạy theo lịch, ví dụ mỗi giờ/ngày.
- **Event-driven:** đánh giá lại khi cloud audit event cho biết resource được tạo/sửa.
- **Continuous reconciliation:** controller liên tục so sánh và điều chỉnh desired state.
- **Deployment-time validation:** kiểm tra trước/sau mỗi release.

Kết hợp các cách này: event-driven giảm detection latency; scheduled scan bắt sự kiện bị bỏ lỡ hoặc resource tồn tại từ lâu; deployment-time check ngăn thay đổi sai từ đầu.

### 4.4. Detection latency

Resource public bị phát hiện sau vài giờ có thể tạo exposure lâu hơn nhiều so với một tag thiếu. Đo thời gian từ lúc drift xuất hiện đến lúc phát hiện và khắc phục:

~~~text
Mean Time To Detect (MTTD)
  = Detection timestamp - Drift introduction timestamp

Mean Time To Remediate (MTTR)
  = Remediation verified timestamp - Detection timestamp
~~~

Theo dõi percentile và severity, không chỉ average. Drift critical cần alert gần real time hoặc preventive block, trong khi tag thiếu ở sandbox có thể xử lý theo batch.

## 5. Tài nguyên ngoài chuẩn và unmanaged resources

### 5.1. Các nhóm cần phân biệt

- **Unmanaged resource:** không được đăng ký trong IaC/config inventory và không có lifecycle owner rõ.
- **Orphaned resource:** có thể từng được quản lý nhưng owner, parent hoặc workload đã mất.
- **Shadow IT:** resource được tạo ngoài governance/approval process.
- **Out-of-policy resource:** có owner nhưng vi phạm baseline/policy.
- **Exception-approved resource:** khác baseline nhưng có risk acceptance, owner, scope và expiry.
- **Ephemeral resource:** resource tạm thời được tạo bởi job/controller và có TTL/owner rõ.
- **Provider-managed resource:** resource hoặc field do dịch vụ quản lý theo semantics của nhà cung cấp.

Không đánh đồng resource không có tag với resource vô chủ. Tag có thể mất nhưng ownership vẫn có thể truy ra qua account, deployment, audit log, naming và billing metadata.

### 5.2. Inventory và ownership

Một resource inventory nên ghi resource ID, type, region, account/project, environment, workload/service, owner team/contact, cost center/product/tenant nếu phù hợp, source of truth/repository/module, creation time/creator principal, last modified time/actor, classification/compliance scope, backup/retention/criticality, lifecycle/expiry/TTL và exception ID nếu có.

Không yêu cầu tag chứa secret, token, email cá nhân hoặc dữ liệu khách hàng.

### 5.3. Phát hiện resource chưa có owner

Quy trình tìm:

1. Lấy inventory từ tất cả account/project/region được quản lý.
2. Chuẩn hóa resource ID, account, type và tag.
3. Đối chiếu với IaC state và deployment inventory.
4. Đối chiếu creator/last actor từ audit logs.
5. Tìm quan hệ với workload, network interface, DNS, storage mount và billing.
6. Gán trạng thái unknown owner/unmanaged/orphaned.
7. Tạo case có owner xử lý và deadline.
8. Không tự động xóa resource có thể đang phục vụ production.

## 6. Phân loại và ưu tiên drift

Không phải drift nào cũng có cùng mức rủi ro. Một tag thiếu có thể ảnh hưởng cost allocation; firewall mở public có thể tạo rủi ro nghiêm trọng.

### 6.1. Risk score

Có thể chấm dựa trên impact, exposure, exploitability, criticality, scope, duration và compensating controls.

~~~text
Risk score
  = Impact × Exposure × Exploitability × Scope factor
~~~

Mô hình này chỉ hỗ trợ xếp hạng, không thay thế đánh giá security. Có thể dùng thang điểm có trọng số và ngưỡng severity được tổ chức phê duyệt.

### 6.2. Severity và phản hồi

| Severity | Ví dụ | Phản hồi tham khảo |
| --- | --- | --- |
| Critical | Public access vào dữ liệu restricted; tắt encryption/control trọng yếu | Chặn hoặc cô lập ngay theo incident procedure |
| High | Security group mở cổng quản trị rộng; audit logging tắt | Alert ngay, owner xử lý khẩn |
| Medium | Backup retention thấp hơn baseline; resource thiếu owner tag | Ticket có SLA ngắn và escalation |
| Low | Tag mô tả thiếu; naming lệch convention không ảnh hưởng control | Batch remediation theo lịch |

Severity và thời hạn phải phụ thuộc policy/risk appetite. Không tự động public block hoặc xóa resource nếu có khả năng làm mất dịch vụ; critical exposure cần incident commander/security owner quyết định hành động an toàn.

### 6.3. Drift có thể là legitimate change

Autoscaler tăng replica từ 3 lên 8 là thay đổi runtime được controller sở hữu. Nếu IaC so sánh và muốn ép về 3, nó có thể phá scale-out. Desired state nên mô tả policy (min/max/metric) thay vì cố định giá trị động.

Cần rule:
- Ignore/allow attribute thuộc controller.
- Observe nhưng không auto-remediate provider-managed field.
- Require approval cho security-critical property.
- Reconcile thuộc tính cần tuân thủ liên tục.
- Tách emergency change khỏi permanent desired state.

## 7. Remediation: xử lý drift an toàn

Có ba hướng xử lý chính:

1. **Reconcile to desired:** đưa resource thực tế về cấu hình chuẩn.
2. **Adopt actual state:** nếu thay đổi thực tế hợp lệ, cập nhật IaC/config repository để phản ánh quyết định đã phê duyệt.
3. **Approved exception:** giữ khác biệt có thời hạn cùng risk acceptance và compensating control.

Không phải mọi drift đều nên chạy apply ngay. Apply có thể xóa resource, thay database, reset firewall, thay endpoint hoặc gây downtime.

### 7.1. Remediation workflow

~~~mermaid
flowchart TD
    D["Drift finding"] --> C["Classify / assess risk"]
    C --> U{"Unknown owner or impact?"}
    U -->|Yes| H["Quarantine change / investigate"]
    U -->|No| R{"Matches approved exception?"}
    R -->|Yes| E["Record exception and expiry"]
    R -->|No| A{"Actual change legitimate?"}
    A -->|Yes| I["Update source of truth after approval"]
    A -->|No| P["Plan remediation / rollback"]
    P --> AP["Review impact and approve"]
    AP --> FIX["Apply controlled fix"]
    I --> V["Verify actual state"]
    E --> V
    FIX --> V
    H --> V
    V --> CLOSE["Evidence / close finding"]
~~~

### 7.2. Prevent, detect và correct

| Control | Mục đích | Ví dụ |
| --- | --- | --- |
| Preventive | Chặn cấu hình sai trước khi tạo | Policy-as-code, org policy, admission control |
| Detective | Phát hiện sai lệch đang tồn tại | Inventory scan, config rule, audit alert |
| Corrective | Đưa về chuẩn hoặc xử lý ngoại lệ | IaC apply, rollback, quarantine, ticket |
| Compensating | Giảm rủi ro trong thời gian chưa sửa | Firewall rule tạm, extra monitoring, access revoke |

Một control chỉ có tác dụng khi scope và bypass path được quản lý. Policy block public storage nhưng role admin rộng có thể tắt policy; cần audit thay đổi policy và bảo vệ control plane.

### 7.3. Auto-remediation và manual remediation

Auto-remediation phù hợp khi rule có semantics rõ, hành động reversible hoặc blast radius thấp, owner/environment đã biết, có test, audit, idempotency và rollback, và không phá workload hợp lệ.

Manual approval phù hợp khi có khả năng downtime/data loss, resource chưa biết owner hoặc nằm ngoài IaC, thay đổi ảnh hưởng cross-account/network, cần đánh giá pháp lý/business exception hoặc provider/manager giữ quyền kiểm soát lifecycle.

Ví dụ có thể tự động bật lại required encryption khi dịch vụ hỗ trợ an toàn và dữ liệu hiện có không bị ảnh hưởng; nhưng không tự động terminate VM không tag nếu chưa xác định nó có đang chạy workload quan trọng không.

## 8. Policy-as-code và guardrails

Policy-as-code biến yêu cầu quản trị thành rule có thể kiểm tra trong pipeline hoặc trên resource thực tế.

### 8.1. Ví dụ policy

Các policy phổ biến:

- Resource production phải có owner, environment và cost center.
- Database không được public endpoint nếu không có exception.
- Storage chứa restricted data phải bật encryption và block public access.
- Compute production phải dùng image được phê duyệt.
- IAM policy không được cấp wildcard privilege ngoài role được kiểm soát.
- Audit log phải bật và ghi vào destination được bảo vệ.
- Backup/retention phải đạt baseline theo data tier.
- Region phải phù hợp residency requirement.

### 8.2. Ví dụ policy dạng pseudo-Rego

~~~rego
package cloud.baseline

deny[msg] {
  input.environment == "production"
  not input.tags.owner
  msg := "Production resource must declare an owner"
}

deny[msg] {
  input.data_classification == "restricted"
  input.public_access == true
  msg := "Restricted data must not be publicly accessible"
}

deny[msg] {
  input.environment == "production"
  input.encryption.enabled != true
  msg := "Production resource requires encryption"
}
~~~

Đây là pseudo-policy minh họa; schema input và cú pháp rule cần khớp engine/policy framework thực tế. Một rule phải có unit test cho pass/fail, negative cases và exception behavior.

### 8.3. Policy enforcement stages

- Pull request: static validation, IaC scanning, policy evaluation.
- Plan review: xem resource create/update/delete và blast radius.
- Deploy: policy gate trước apply.
- Runtime: continuous config evaluation.
- Audit: lưu result, policy version, resource snapshot và exception.
- Remediation: tạo action hoặc auto-fix theo policy.

### 8.4. Preventive guardrails và break-glass

Có thể dùng organization policy, SCP/management policy, IAM permission boundary hoặc admission controller để chặn hành động nguy hiểm. Cần thiết kế break-glass cho sự cố thật nhưng phải có identity riêng và MFA, time-bound permission, approval hoặc post-incident review, audit không thể tự xóa, automatic expiry/revoke và reconciliation sau emergency change.

Không dùng break-glass như đường triển khai thường ngày. Sau emergency change, phải đưa thay đổi vào source of truth hoặc rollback.

## 9. Quản lý cấu hình ở Kubernetes và runtime

Kubernetes có nhiều controller cùng thay đổi object. Drift detection phải hiểu owner và field management.

### 9.1. GitOps reconciliation

GitOps controller so sánh manifest trong repository với cluster state rồi reconcile theo policy. Cần kiểm tra:
- Field do HPA/controller sở hữu.
- Admission mutation/defaulting.
- Secret injection sidecar/operator.
- CRD/operator tự tạo child resource.
- Runtime-generated status fields.
- Manual kubectl edit và emergency patch.
- Resource bị prune khi xóa khỏi Git.

kubectl diff hoặc GitOps sync status giúp phát hiện khác biệt nhưng cần hiểu field ownership và defaulting để tránh false positive.

### 9.2. Drift của container và node

Có thể kiểm soát image pin theo digest thay vì tag mutable, base image/version và patch level, node OS/AMI baseline, runtime security profile, admission policy cho privilege/hostPath/capabilities, sidecar/agent version và secret/config version.

Không nên sửa container đang chạy bằng shell rồi coi đó là trạng thái chuẩn. Thay đổi cần đi qua build/deploy pipeline và artifact mới.

### 9.3. Runtime config và feature flags

Feature flag/config service có thể thay đổi ngoài deployment release. Cần lưu config key/version, actor hoặc automation principal, reason/change ticket, scope (tenant/environment/region), effective time và expiry, approval khi ảnh hưởng security/data processing, và rollback value.

Cấu hình động cần audit tương đương IaC, dù không tạo cloud resource.

## 10. Tài nguyên ngoài chuẩn: discovery và lifecycle

### 10.1. Quy trình resource discovery

~~~mermaid
flowchart TB
    INV["Cloud asset inventory"] --> NORM["Normalize resource identity"]
    NORM --> MAP["Map to IaC / owner / workload"]
    MAP --> POL["Evaluate baseline and policy"]
    POL --> FIND["Create finding"]
    FIND --> TKT["Assign owner and SLA"]
    TKT --> DEC{"Decision"}
    DEC -->|Adopt| SRC["Import into source of truth"]
    DEC -->|Delete| DEL["Approved decommission"]
    DEC -->|Exception| EX["Time-bound exception"]
    SRC --> VERIFY["Verify and audit"]
    DEL --> VERIFY
    EX --> VERIFY
~~~

### 10.2. Adopt/import resource

Khi resource ngoài chuẩn hợp lệ và cần giữ:
1. Xác định owner/business purpose.
2. Kiểm tra security/compliance/cost.
3. Chọn module và source of truth phù hợp.
4. Import resource vào state/config management an toàn.
5. So sánh plan để bảo đảm không có replace/destroy ngoài ý muốn.
6. Review và apply thay đổi nhỏ theo giai đoạn.
7. Gắn owner, lifecycle, backup và alert.
8. Đóng finding với evidence.

Import không có nghĩa resource tự động đã đạt baseline; cần kiểm tra đầy đủ actual configuration.

### 10.3. Decommission resource

Trước khi xóa, xác định owner và consumer; kiểm tra network dependency, DNS, data mount, backup và service linkage; kiểm tra retention/legal hold; xác định dữ liệu cần archive; drain traffic/job và dừng writes; backup/export nếu cần; xóa theo approval; xác nhận bill/resource inventory không còn; lưu deletion evidence.

Không tự động xóa resource chỉ vì không có tag hoặc không nằm trong IaC. Orphaned disk, snapshot hoặc IP có thể vẫn cần cho recovery.

## 11. Exception management và risk acceptance

Có những trường hợp baseline không thể áp dụng ngay hoặc cần cấu hình khác cho workload đặc biệt. Ngoại lệ cần được quản lý như một đối tượng có vòng đời, không phải comment trong ticket rồi quên.

### 11.1. Exception record

Một exception nên có:
- Exception ID.
- Resource/scope/environment.
- Policy/rule bị ngoại lệ.
- Business reason.
- Risk và impact assessment.
- Compensating controls.
- Owner và approver.
- Start/effective time.
- Expiry date.
- Review cadence.
- Remediation plan nếu ngoại lệ tạm thời.
- Evidence và audit history.

### 11.2. Expiry và revalidation

Ngoại lệ hết hạn phải tự chuyển trạng thái cần review, cảnh báo owner và theo policy:
- Tự động đóng exception và reconcile nếu hành động an toàn.
- Chặn thay đổi/deploy tiếp theo.
- Escalate tới owner/approver.
- Yêu cầu re-approval với risk mới.

Không tự động xóa resource khi exception hết hạn. Có thể policy yêu cầu cấu hình lại, nhưng phải đánh giá blast radius trước.

### 11.3. Không dùng exception để hợp thức hóa mọi drift

Nếu baseline liên tục được miễn trừ, có thể baseline sai hoặc kiến trúc chưa phù hợp. Cần phân tích pattern exception để sửa baseline, tạo workload tier khác, xây control mới, tách resource hoặc chấp nhận risk có chủ đích ở mức phù hợp.

## 12. Audit evidence và continuous compliance

Một control có thể tồn tại trong policy nhưng auditor vẫn cần bằng chứng nó hoạt động. Evidence cần chỉ ra scope, thời gian, policy version, result và người chịu trách nhiệm.

| Control | Evidence |
| --- | --- |
| Encryption at rest | Resource config snapshot, key reference, policy evaluation |
| Network exposure | Security group/firewall inventory, route, public endpoint scan |
| Access governance | IAM policy version, access review, audit logs |
| Backup | Backup status, retention, restore test evidence |
| Logging | Audit configuration, destination, retention, access policy |
| IaC change control | Commit, review, plan, approval, pipeline run |
| Drift management | Finding, owner, severity, remediation/exception, closure evidence |
| Unmanaged resources | Inventory snapshot, mapping result, owner assignment |
| Exception control | Exception record, approver, expiry, revalidation |

### 12.1. Evidence integrity

Evidence phải được bảo vệ khỏi chỉnh sửa trái phép. Có thể lưu trong audit account/bucket riêng, bật versioning/immutable retention theo yêu cầu, ghi checksum và truy cập qua role hạn chế. Không đặt evidence có secret hoặc PII vượt nhu cầu audit.

### 12.2. Continuous compliance

Compliance không chỉ là ảnh chụp một ngày. Cần đo:
- Tỷ lệ resource compliant theo baseline.
- Critical drift count và tuổi tồn tại.
- MTTD/MTTR theo severity.
- Resource không có owner.
- Exception còn hiệu lực và sắp hết hạn.
- Tỷ lệ remediation thành công.
- False positive/false negative của policy.
- Số thay đổi ngoài pipeline.
- Tỷ lệ resource có source of truth.
- Evidence freshness.

## 13. Quy trình incident khi phát hiện drift nghiêm trọng

Drift critical có thể là security incident hoặc change incident. Quy trình cần ưu tiên bảo vệ hệ thống và dữ liệu, đồng thời giữ bằng chứng.

1. Xác minh finding và resource identity.
2. Kiểm tra audit log, actor, thời điểm và change path.
3. Đánh giá public exposure, privilege, data classification và blast radius.
4. Thông báo incident commander/security owner.
5. Chọn containment: revoke access, isolate network, disable key/endpoint hoặc rollback theo policy.
6. Giữ evidence trước khi thay đổi nếu không làm tăng rủi ro.
7. Remediate qua controlled path hoặc emergency procedure.
8. Xác minh actual state và workload health.
9. Điều tra root cause, kiểm tra resource tương tự.
10. Cập nhật IaC, policy, alert và runbook.
11. Ghi incident closure và lessons learned.

Không tự động revert một thay đổi mà chưa hiểu nguyên nhân. Có thể người vận hành đã thêm rule để chặn outage; xóa ngay có thể làm hệ thống mất kết nối. Đối với critical exposure, containment phải theo incident policy và người có thẩm quyền.

## 14. Observability và KPI cho configuration governance

### 14.1. KPI vận hành

| KPI | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| Drift coverage | Tỷ lệ resource thuộc scope có cơ chế phát hiện drift | Phát hiện vùng mù |
| Compliant resource ratio | Tỷ lệ resource đáp ứng baseline | Theo dõi xu hướng compliance |
| Unmanaged resource count | Resource không mapping được owner/source | Ưu tiên discovery |
| Critical drift count | Drift severity cao chưa đóng | Escalation |
| MTTD | Thời gian từ introduction đến detection | Đánh giá detection |
| MTTR | Thời gian từ detection đến verified remediation | Đánh giá response |
| Change outside pipeline | Thay đổi ngoài quy trình chuẩn | Tìm nguồn drift |
| Exception aging | Tuổi và thời gian tới expiry | Tránh exception vĩnh viễn |
| Remediation success rate | Tỷ lệ fix được xác minh | Đánh giá automation |
| False positive rate | Finding không phải vi phạm thực | Cải thiện policy |
| Evidence freshness | Bằng chứng còn mới và đủ scope | Sẵn sàng audit |

### 14.2. Dashboard

Dashboard có thể chia:
- Executive: compliance trend, critical risk, exception exposure và chi phí ngoài chuẩn.
- Platform: drift theo account/region/resource type, IaC coverage, policy failure.
- Security: public exposure, privileged access drift, encryption/logging gaps.
- Operations: alert age, owner, remediation status, change failures.
- Cost: orphaned resource, idle capacity, untagged cost và budget variance.
- Audit: evidence completeness, exception expiry và control coverage.

Không chỉ hiển thị phần trăm compliance. Một môi trường 99,9% compliant vẫn có thể có một critical public bucket chứa dữ liệu nhạy cảm.

### 14.3. Alert design

Cảnh báo cần có resource ID, account/region, policy ID, severity, owner, first-seen, last-seen, actual/desired summary và remediation link. Không đưa secret hoặc dữ liệu nhạy cảm vào notification.

## 15. Tự động hóa remediation có guardrail

Automation giúp giảm MTTR nhưng cũng có thể nhân lỗi trên quy mô lớn. Chỉ tự động hóa sau khi đã hiểu semantics và tác động.

### 15.1. Các mức tự động hóa

- **Observe-only:** ghi finding, không thay đổi resource.
- **Ticket automation:** tạo ticket, gán owner và SLA.
- **Suggested remediation:** tạo plan/PR để review.
- **Approved execution:** người có quyền phê duyệt rồi pipeline apply.
- **Auto-remediation:** tự động sửa rule đã xác minh, có điều kiện và rollback.
- **Preventive enforcement:** chặn cấu hình sai ngay khi request tạo/change.

Bắt đầu bằng observe-only hoặc suggested remediation cho resource phức tạp; tăng dần khi precision và rollback đã được kiểm chứng.

### 15.2. Guardrail cho auto-remediation

- Scope theo resource type/environment/owner.
- Allowlist và denylist rõ.
- Idempotent action.
- Rate limit và concurrency cap.
- Dry-run/plan trước khi apply.
- Precondition và postcondition.
- Canary hoặc batch rollout.
- Circuit breaker cho remediation automation.
- Rollback procedure.
- Audit actor/service identity và version.
- Stop switch khi remediation gây incident.
- Không đụng resource không owner hoặc critical nếu chưa phê duyệt.

### 15.3. Không tạo vòng lặp controller

Nếu hai controller cùng sửa một thuộc tính, chúng có thể liên tục ghi đè nhau. Ví dụ Terraform đặt replica count 4 trong khi HPA tăng lên 10; GitOps lại sync về 4; HPA tăng trở lại. Cần field ownership rõ và ignore/managed-field configuration phù hợp.

## 16. TCO và tác động vận hành

Configuration governance có chi phí từ IaC/state backend và CI/CD; cloud inventory/config management; policy engine, scanner và log storage; agent/runtime config management; remediation workers, ticketing và approval workflow; audit evidence retention; engineering time duy trì module/baseline; false positives/manual review; training, incident response và exception governance.

Giá trị mang lại gồm giảm misconfiguration/security exposure, giảm resource không owner và chi phí lãng phí, tái tạo environment đồng nhất, tăng tốc audit/điều tra, giảm change failure rate và nâng kiểm soát multi-account/region.

~~~text
Cost of configuration governance
  = Tooling + Inventory/scan compute
    + Logs/evidence storage
    + Remediation automation
    + Engineering and audit effort

Avoided cost
  = Reduced incident impact
    + Reduced orphaned/idle resource spend
    + Reduced manual audit effort
    + Reduced change/recovery failures
~~~

Không cần triển khai policy platform phức tạp cho mọi sandbox. Mức kiểm soát nên phù hợp criticality, data classification, blast radius và tốc độ thay đổi.

## 17. Case study: phát hiện và xử lý drift trong nền tảng SaaS

### 17.1. Bối cảnh

Một SaaS chạy trên ba cloud accounts: production, staging và sandbox. Infrastructure được quản lý bằng Terraform; Kubernetes workload được deploy qua GitOps; database và object storage dùng managed service. Nhiều nhóm có quyền vận hành nhưng một số thay đổi khẩn cấp vẫn được thực hiện trực tiếp qua console.

Một cuộc audit phát hiện:
- Production storage bucket có public access block bị thay đổi.
- Security group database có thêm CIDR ngoài private subnet.
- Một VM không có owner/cost center.
- HPA replica count khác với manifest Git.
- Backup retention một database thấp hơn baseline.

### 17.2. Discovery và phân loại

Inventory tìm resource theo account/region. IaC state mapping xác định bucket và security group được quản lý; VM không có mapping; database thuộc module do data platform sở hữu; replica count do HPA điều khiển nên không phải drift nếu policy đúng.

Audit log cho thấy bucket được thay đổi bởi principal vận hành trong emergency; security group được tạo rule bởi script cũ; VM thuộc job thử nghiệm chưa dọn.

### 17.3. Remediation

- Bucket: kiểm tra access và consumer, containment public access, khôi phục baseline, review data exposure.
- Security group: xác nhận CIDR không còn cần, remove qua controlled change, kiểm tra app connectivity.
- VM: xác định job owner, export dữ liệu nếu cần, decommission sau approval; bổ sung TTL/cleanup.
- HPA: sửa rule so sánh để loại field runtime do HPA sở hữu, giữ min/max và metric baseline.
- Backup: tăng retention theo data tier, chạy restore test và cập nhật evidence.

### 17.4. Prevent recurrence

- Giảm quyền console mutate production; break-glass có thời hạn và audit.
- Bật event-driven config evaluation cho public access/security group.
- Bắt buộc owner/environment/expiry tags ở resource creation.
- IaC policy gate kiểm tra baseline trước apply.
- Scheduled inventory tìm unmanaged/orphaned resource.
- Exception record cho emergency changes và expiry.
- Dashboard hiển thị drift aging và changes outside pipeline.

~~~mermaid
flowchart TB
    INV["Account/region inventory"] --> MAP["IaC and owner mapping"]
    MAP --> DET["Policy and drift detection"]
    DET --> TRIAGE["Risk triage"]
    TRIAGE --> FIX1["Security remediation"]
    TRIAGE --> FIX2["Adopt/decommission resource"]
    TRIAGE --> FIX3["Correct controller ownership"]
    FIX1 --> VERIFY["Post-fix verification"]
    FIX2 --> VERIFY
    FIX3 --> VERIFY
    VERIFY --> PREV["Preventive guardrails + audit"]
~~~

## 18. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Coi IaC plan là inventory toàn bộ cloud | Resource tạo thủ công bị bỏ sót | Kết hợp account-wide inventory |
| Tự động revert mọi drift | Có thể gây outage hoặc xóa dữ liệu | Classify, impact review, approval |
| Không có owner cho resource | Finding tồn tại vô thời hạn | Ownership tag/registry và escalation |
| Nhiều controller ghi cùng field | Reconciliation loop, config flapping | Field ownership rõ |
| Coi provider-managed change là vi phạm | False positive liên tục | Phân loại attribute và provider semantics |
| Không audit console change | Không truy được actor/root cause | Cloud audit log và alert |
| Exception không expiry | Baseline bị vô hiệu hóa dần | Time-bound exception và revalidation |
| Policy block quá rộng | Chặn deployment hợp lệ | Test policy, exception scope, staged rollout |
| Chỉ đo compliant percentage | Critical gap bị che khuất | Severity, aging và risk-weighted metrics |
| Xóa resource không tag ngay | Mất workload/data cần thiết | Discovery, owner confirmation và decommission plan |
| Drift được sửa trực tiếp nhưng không cập nhật source | Pipeline tái tạo sai lệch | Adopt hoặc rollback vào source of truth |
| Evidence lưu trong cùng quyền admin | Có thể bị sửa/xóa | Immutable/segregated audit storage |

## 19. Bài tập thực hành

Một công ty SaaS có production, staging và sandbox trên nhiều cloud accounts. IaC quản lý network/database/compute; GitOps quản lý Kubernetes; security team có baseline encryption/logging/private access. Audit tìm thấy public object storage, một database backup retention sai, hai VM không owner và một thay đổi replica count do HPA.

Hãy thực hiện:

1. Xác định source of truth và owner cho VPC, security group, bucket, database, VM và Kubernetes deployment.
2. Phân loại từng finding là drift, unmanaged, orphaned, controller-managed hay approved exception.
3. Thiết kế inventory schema để mapping resource ID, account, region, owner, IaC state và cost center.
4. Chọn preventive, detective và corrective control cho public access, encryption, backup và mandatory tags.
5. Viết policy-as-code rule cho production owner tag, restricted data public access và encryption.
6. Xác định trường hợp HPA/provider-managed field cần loại khỏi drift comparison.
7. Thiết kế remediation plan có impact review, approval, canary, rollback và evidence.
8. Định nghĩa exception record có owner, compensating control, approver và expiry.
9. Thiết kế alert cho critical drift và dashboard cho drift aging/MTTD/MTTR.
10. Xác định cách điều tra console change từ audit log và ngăn tái diễn.
11. Xây quy trình import/adopt resource và decommission VM vô chủ an toàn.
12. Đánh giá chi phí của IaC/policy/inventory platform so với rủi ro và manual audit.
13. Viết ADR về mức auto-remediation cho từng nhóm resource.

**Gợi ý tự đánh giá:** Bài làm đạt khi có source of truth rõ, không coi mọi khác biệt là lỗi, phát hiện được resource ngoài IaC, remediation không gây outage, exception có thời hạn và evidence chứng minh trạng thái đã được xử lý.

## 20. Checklist trước production

- [ ] Mỗi loại resource/config có source of truth và owner rõ ràng.
- [ ] Baseline khác nhau theo environment, criticality và data classification.
- [ ] IaC state được bảo vệ, locking, backup và audit.
- [ ] Controller-owned fields được xác định để tránh false drift.
- [ ] Inventory bao phủ account, project, region và resource type.
- [ ] IaC mapping và unmanaged-resource discovery chạy định kỳ.
- [ ] Drift detection kết hợp plan, inventory, audit logs và policy evaluation.
- [ ] Critical policy có preventive guardrail và runtime detection.
- [ ] Findings có resource ID, actual/desired state, severity, owner và first-seen.
- [ ] Auto-remediation có dry-run, scope, rate limit, rollback và stop switch.
- [ ] Resource chưa rõ owner không bị xóa tự động.
- [ ] Exception có risk acceptance, compensating control, approver và expiry.
- [ ] Emergency change có audit, time-bound access và post-change reconciliation.
- [ ] Secret/config runtime có version, access control và change audit.
- [ ] Có evidence integrity và retention phù hợp cho audit.
- [ ] KPI gồm coverage, compliance, unmanaged count, MTTD, MTTR, exception aging.
- [ ] Remediation được verify sau apply và có re-test.
- [ ] TCO và operational ownership được đánh giá định kỳ.

## 21. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi review configuration governance |
| --- | --- |
| **Operational Excellence** | Desired state, owner, change workflow, drift detection, remediation và audit evidence có thể vận hành lặp lại không? |
| **Security** | IAM, network, encryption, logging, secret và public exposure có preventive/detective control và exception governance không? |
| **Reliability** | Remediation có kiểm soát blast radius, rollback và giữ service health; recovery environment có tái tạo từ source of truth được không? |
| **Performance Efficiency** | Inventory/scan/reconciliation có chạy hiệu quả, không tạo tải quá mức lên API/control plane không? |
| **Cost Optimization** | Resource ngoài chuẩn/orphaned có được phát hiện; tag/cost ownership và idle resource có được quản lý không? |
| **Sustainability** | Có giảm tài nguyên mồ côi, cấu hình dư, drift gây overprovision và thao tác vận hành lặp lại không? |

**Kết luận:** Quản lý cấu hình hiệu quả cần một desired state có owner, inventory bao phủ toàn môi trường và vòng lặp phát hiện–phân loại–xử lý–xác minh. IaC tạo nền tảng kiểm soát thay đổi; policy-as-code ngăn cấu hình sai; inventory và audit tìm resource ngoài chuẩn; remediation có guardrail đưa hệ thống về trạng thái được phê duyệt. Không phải mọi khác biệt đều cần tự động revert: phải hiểu controller, provider, business context và blast radius. Hãy lưu exception có thời hạn, đo MTTD/MTTR và giữ evidence có thể kiểm toán để duy trì trạng thái cloud an toàn, tin cậy và kiểm soát được chi phí theo Well-Architected.
