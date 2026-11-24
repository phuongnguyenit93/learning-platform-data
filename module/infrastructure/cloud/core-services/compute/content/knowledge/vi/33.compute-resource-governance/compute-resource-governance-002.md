# Tổ chức tài nguyên theo tài khoản, subscription, project và môi trường

Một nền tảng cloud có thể chứa hàng trăm ứng dụng, nhiều nhóm kỹ thuật, nhiều môi trường triển khai và hàng nghìn tài nguyên compute. Nếu tất cả cùng nằm trong một phạm vi quản trị, đội vận hành sẽ khó giới hạn quyền, phân bổ chi phí, đặt quota, kiểm soát network và xử lý sự cố mà không ảnh hưởng workload khác. Ngược lại, chia quá nhiều phạm vi nhỏ mà không có quy tắc chung sẽ tạo ra nhiều cấu hình trùng lặp, khó quản lý và làm tăng chi phí vận hành.

Cách tổ chức tài nguyên cần tạo ra các ranh giới rõ ràng ở nhiều cấp:

- **Account hoặc cloud account:** ranh giới quản trị cấp cao, thường gắn với danh tính, billing, quota và phạm vi tài nguyên.
- **Subscription:** phạm vi quản lý tài nguyên, quyền, quota và billing trong một số nền tảng cloud.
- **Project:** nhóm tài nguyên phục vụ một ứng dụng, workload hoặc đơn vị kinh doanh; trong một số cloud đây là ranh giới API, IAM, quota và billing trực tiếp.
- **Environment:** phân biệt development, test, staging và production theo mức độ tin cậy, dữ liệu, quyền truy cập và vòng đời triển khai.

Tên gọi và thứ tự phân cấp khác nhau giữa nhà cung cấp. Không nên giả định account, subscription và project có cùng ý nghĩa trên mọi cloud. Cần hiểu ranh giới thực tế của nền tảng, sau đó thiết kế mô hình phù hợp với tổ chức.

Bài học này trình bày cách thiết kế hierarchy tài nguyên, lựa chọn ranh giới account/subscription/project/environment, phân tách production và non-production, quản lý identity và policy, tổ chức network/shared services, phân bổ chi phí, đặt quota/budget và vận hành vòng đời tài nguyên compute.

## 1. Vì sao cần tổ chức tài nguyên theo nhiều cấp?

Một tổ chức thường có nhiều chiều quản trị đồng thời:

- Ai sở hữu workload?
- Ai được phép tạo, sửa hoặc xóa tài nguyên?
- Chi phí thuộc team hoặc sản phẩm nào?
- Workload nào cần cô lập về bảo mật?
- Dữ liệu nào được phép đặt ở region nào?
- Môi trường nào được phép truy cập dữ liệu production?
- Quota nào cần dành cho workload quan trọng?
- Sự cố hoặc thay đổi nào có thể ảnh hưởng tới phạm vi nào?

Một cấu trúc tốt giúp trả lời các câu hỏi đó bằng ranh giới có thể kiểm soát. Tổ chức tài nguyên không chỉ là đặt tên thư mục hay nhóm resource; nó ảnh hưởng đến identity, network, billing, quota, policy, automation và incident response.

### Các mục tiêu chính

1. **Isolation:** giới hạn blast radius khi có lỗi cấu hình, credential bị lộ hoặc workload tiêu thụ quá nhiều tài nguyên.
2. **Least privilege:** cấp quyền theo team, workload và môi trường.
3. **Cost ownership:** xác định ai chịu trách nhiệm cho chi phí và ngân sách.
4. **Policy enforcement:** áp dụng guardrail thống nhất cho region, network, encryption, image và resource type.
5. **Quota management:** tránh một workload chiếm hết capacity hoặc quota của account.
6. **Lifecycle management:** tạo, nâng cấp, archive và xóa tài nguyên theo quy trình.
7. **Scalability of governance:** thêm team, ứng dụng và môi trường mà không phải thiết kế lại toàn bộ cấu trúc.

### Tổ chức quá ít hoặc quá nhiều

| Cách tổ chức | Lợi ích | Rủi ro |
|---|---|---|
| Một account/project cho tất cả | Dễ bắt đầu, ít cấu hình | Quyền rộng, khó chargeback, blast radius lớn |
| Một phạm vi cho mỗi workload | Cô lập tốt hơn, dễ phân quyền | Nhiều cấu hình và quota cần quản lý |
| Một phạm vi cho mỗi environment | Tách production/non-production rõ | Có thể khó quản lý khi có nhiều ứng dụng |
| Phân cấp theo tổ chức, sản phẩm và environment | Dễ áp dụng policy ở nhiều cấp | Cần quy ước ownership và automation |
| Quá nhiều phạm vi nhỏ không có chuẩn | Cô lập bề ngoài | Drift, policy không đồng nhất, vận hành phức tạp |

Mục tiêu là chọn số cấp và ranh giới vừa đủ để phản ánh yêu cầu bảo mật, chi phí, vận hành và quyền sở hữu.

## 2. Phân biệt account, subscription, project và environment

Các khái niệm có thể tương tự về mục đích nhưng khác nhau về implementation.

| Khái niệm | Vai trò thường gặp | Phạm vi kiểm soát |
|---|---|---|
| Organization / tenant | Gốc quản trị của tổ chức | Identity, billing agreement, policy hierarchy |
| Account | Đơn vị cloud account hoặc billing/administrative boundary | IAM, quota, resource visibility, billing tùy provider |
| Subscription | Container quản lý resource và billing trong một số nền tảng | RBAC, quota, policy assignment, billing scope |
| Folder / management group | Nhóm account hoặc subscription | Kế thừa policy, IAM và governance |
| Project | Phạm vi một workload hoặc nhóm dịch vụ | API enablement, IAM, quota, billing và resource grouping tùy provider |
| Resource group | Nhóm resource có lifecycle hoặc ownership chung | Quản lý, triển khai và xóa resource trong subscription |
| Environment | Development, test, staging, production | Trust level, data class, release lifecycle, access policy |
| Resource | VM, disk, network, cluster, function | Cấu hình và quyền ở cấp tài nguyên |

### Account không đồng nghĩa environment

Một account có thể chứa nhiều environment nếu nền tảng và risk model cho phép, nhưng production và non-production thường nên có ranh giới mạnh hơn khi:
- Dữ liệu production nhạy cảm.
- Quyền quản trị khác nhau.
- Có yêu cầu compliance hoặc audit.
- Cần quota và billing độc lập.
- Non-production có nhiều người dùng hoặc automation rộng hơn.

### Project không phải lúc nào cũng là ranh giới bảo mật tuyệt đối

Một project có thể cung cấp IAM và quota riêng, nhưng vẫn dùng chung organization, network, logging, billing hoặc policy ở cấp cao. Cần xác định điều gì được cô lập thật sự và điều gì vẫn được chia sẻ.

### Environment là thuộc tính vận hành

Environment có thể được biểu diễn bằng:
- Account hoặc subscription riêng.
- Project riêng.
- Namespace hoặc resource group riêng.
- Label/tag trên resource.
- Workspace hoặc deployment stage.

Dùng tag environment để báo cáo là hữu ích, nhưng tag không tự tạo ra isolation. Production và development có thể mang hai tag khác nhau nhưng vẫn chia sẻ cùng IAM role, network và quota.

## 3. Cách các cloud provider tổ chức hierarchy

Tên gọi và semantics thay đổi theo dịch vụ. Những ví dụ dưới đây giúp nhận diện mô hình, không phải một cây phân cấp bắt buộc dùng cho mọi tổ chức.

### AWS

Một mô hình phổ biến:
- AWS Organization là gốc quản trị nhiều account.
- Organizational Unit (OU) nhóm account theo chức năng hoặc môi trường.
- AWS account là ranh giới quan trọng cho IAM, quota, billing visibility và resource isolation.
- Region và VPC tổ chức network trong account.
- Resource group/tag hỗ trợ nhóm tài nguyên và báo cáo.

Ví dụ:

~~~text
Organization
├── OU: Production
│   ├── Account: prod-payments
│   └── Account: prod-commerce
├── OU: NonProduction
│   ├── Account: dev-shared
│   └── Account: test-commerce
└── OU: Security
    ├── Account: audit-logging
    └── Account: security-tools
~~~

Service Control Policies có thể tạo guardrail ở cấp organization/OU/account. IAM role và resource policy tiếp tục kiểm soát quyền bên trong account.

### Microsoft Azure

Một mô hình thường gặp:
- Microsoft Entra tenant chứa identity.
- Management group tổ chức subscription.
- Subscription là phạm vi quản trị, quota và billing.
- Resource group gom resource có lifecycle/ownership liên quan.
- Resource là VM, VNet, disk, AKS cluster hoặc dịch vụ khác.

Ví dụ:

~~~text
Entra tenant
└── Management group: Company
    ├── Management group: Production
    │   ├── Subscription: prod-core
    │   └── Subscription: prod-data
    └── Management group: NonProduction
        ├── Subscription: dev
        └── Subscription: test
~~~

Azure Policy và RBAC có thể được gán ở nhiều scope và kế thừa xuống cấp dưới theo semantics của nền tảng.

### Google Cloud

Một mô hình phổ biến:
- Organization là gốc.
- Folder nhóm project theo team, environment hoặc business unit.
- Project là phạm vi quan trọng cho resource, IAM, API, quota và billing.
- Resource nằm trong project và region/zone tương ứng.

Ví dụ:

~~~text
Organization
├── Folder: Production
│   ├── Project: prod-payments
│   └── Project: prod-analytics
└── Folder: NonProduction
    ├── Project: dev-platform
    └── Project: test-payments
~~~

Organization Policy, IAM và billing account hỗ trợ quản trị xuyên project. Shared VPC có thể cho phép project workload sử dụng network được quản lý tập trung.

### So sánh ở mức khái niệm

| Nhu cầu | AWS | Azure | Google Cloud |
|---|---|---|---|
| Gốc tổ chức | Organization | Entra tenant / management hierarchy | Organization |
| Nhóm phạm vi | OU | Management group | Folder |
| Ranh giới workload phổ biến | Account | Subscription | Project |
| Nhóm resource trong phạm vi | Tags/resource groups theo nhu cầu | Resource group | Labels/folders không thay project |
| Guardrail cấp cao | SCP | Azure Policy | Organization Policy |
| Identity | IAM và federation | Entra ID/RBAC | Cloud IAM |

Không chuyển nguyên xi hierarchy của một cloud sang cloud khác. Hãy ánh xạ yêu cầu quản trị vào semantics thực tế của từng nền tảng.

## 4. Chọn ranh giới account hoặc subscription

Account/subscription riêng thường phù hợp khi cần một hoặc nhiều điều kiện sau:

- Ranh giới bảo mật hoặc compliance rõ.
- Team cần quyền quản trị độc lập.
- Workload có quota lớn hoặc quota riêng.
- Chi phí cần được theo dõi và chargeback riêng.
- Có vòng đời độc lập.
- Có network boundary riêng.
- Workload có mức độ tin cậy khác biệt.
- Cần giới hạn blast radius.
- Cần tách production khỏi sandbox.

### Khi nào có thể dùng chung?

Có thể dùng chung account/subscription cho các workload có:
- Cùng owner và mức tin cậy.
- Cùng policy và network boundary.
- Cùng billing owner.
- Cùng quota profile hoặc đã có quota đủ.
- Cùng vòng đời và quy trình vận hành.
- Không cần cô lập quyền ở cấp account.

Ví dụ, nhiều microservice thuộc một sản phẩm có thể ở chung subscription production nhưng được tách project/resource group, network segment và identity theo workload nếu risk model cho phép.

### Khi nào cần tách riêng?

Nên cân nhắc phạm vi riêng cho:
- Production và non-production.
- Security/audit tooling.
- Shared networking.
- Workload regulated hoặc xử lý dữ liệu nhạy cảm.
- Sandbox có quyền tạo tài nguyên rộng.
- Workload GPU có quota và billing lớn.
- Team độc lập cần quyền quản trị riêng.

### Không tách chỉ vì tên ứng dụng khác nhau

Hai service có thể cùng thuộc một trust boundary và cùng owner. Tách mỗi service thành account/subscription sẽ tạo overhead về network, IAM, quota và logging. Hãy dựa trên yêu cầu kiểm soát thực tế.

## 5. Chọn project và resource group

Project thường phù hợp để gom tài nguyên theo:
- Một ứng dụng hoặc sản phẩm.
- Một workload có owner và budget riêng.
- Một môi trường.
- Một domain dữ liệu.
- Một pipeline compute.
- Một nhóm API hoặc dịch vụ có cùng vòng đời.

Resource group thường phù hợp để gom resource có cùng lifecycle, ví dụ VM, disk, NIC, public IP và load balancer của một deployment. Không nên coi resource group là ranh giới security duy nhất nếu IAM và network policy chưa được thiết kế tương ứng.

### Một project cho một workload

Ưu điểm:
- IAM và quota dễ giới hạn.
- Billing dễ phân bổ.
- API/service enablement có phạm vi rõ.
- Resource inventory dễ truy vấn.
- Có thể xóa hoặc archive theo lifecycle.

Nhược điểm:
- Nhiều project tạo thêm overhead.
- Shared resources cần thiết kế cross-project.
- Pipeline deployment phải quản lý nhiều target.
- Có thể chạm quota project count hoặc service quota.

### Một project cho nhiều workload

Ưu điểm:
- Ít phạm vi quản lý.
- Dễ chia sẻ network và platform services.
- Ít cấu hình bootstrap.

Nhược điểm:
- Khó phân bổ chi phí nếu tagging yếu.
- IAM và quota có thể quá rộng.
- Một workload noisy-neighbor ảnh hưởng workload khác.
- Lifecycle và owner không rõ nếu resource không được gắn nhãn.

## 6. Tổ chức theo environment

Các environment thường gặp:

| Environment | Mục đích | Đặc điểm quản trị |
|---|---|---|
| Development | Phát triển tính năng | Linh hoạt, dữ liệu giả lập, chi phí thấp |
| Test / QA | Kiểm thử chức năng và tích hợp | Dữ liệu kiểm thử, cấu hình gần production khi cần |
| Staging / Preproduction | Diễn tập release và kiểm tra tương đồng production | Kiểm soát truy cập và capacity chặt hơn |
| Production | Phục vụ người dùng thật | Availability, security, audit và change control cao |
| Sandbox | Thử nghiệm công nghệ | Quota/TTL chặt, không chứa dữ liệu production |
| Performance test | Load/stress test | Có giới hạn tải, thời gian và budget rõ |

### Production và non-production

Production thường cần:
- Quyền truy cập tối thiểu và phê duyệt thay đổi.
- Dữ liệu được phân loại và bảo vệ.
- Backup, recovery và monitoring.
- Network ingress/egress có kiểm soát.
- Quota/capacity dành riêng.
- Deployment có canary/rollback.
- Audit log bền vững.

Non-production có thể linh hoạt hơn nhưng vẫn cần:
- Không dùng secret production.
- Không sao chép dữ liệu nhạy cảm nếu chưa mask/tokenize.
- Tự động dừng resource ngoài giờ nếu phù hợp.
- Budget và quota.
- TTL cho sandbox.
- Network hạn chế tới production.
- Image và patch baseline.

### Staging không cần giống production tuyệt đối

Staging nên đủ giống production ở những yếu tố cần kiểm thử như runtime, network path, identity pattern, storage class, autoscaling và deployment process. Nhưng có thể dùng capacity nhỏ hơn, dữ liệu đã mask và một số dependency giả lập. Ghi rõ khác biệt để tránh kết quả kiểm thử gây hiểu nhầm.

## 7. Các mẫu hierarchy thường dùng

### Mẫu A: Tách theo environment trước

Phù hợp tổ chức có nhiều ứng dụng nhưng yêu cầu production isolation cao.

~~~text
Organization
├── Production
│   ├── Account/Subscription: prod-platform
│   ├── Account/Subscription: prod-payments
│   └── Account/Subscription: prod-data
└── NonProduction
    ├── Account/Subscription: dev
    ├── Account/Subscription: test
    └── Account/Subscription: staging
~~~

Ưu điểm là policy và access theo environment dễ áp dụng. Nhược điểm là cùng một ứng dụng có resource nằm ở nhiều account/subscription; cần pipeline và shared services hỗ trợ.

### Mẫu B: Tách theo workload, mỗi workload có environment riêng

~~~text
Organization
├── Workload: payments
│   ├── prod account/project
│   ├── staging account/project
│   └── dev account/project
└── Workload: analytics
    ├── prod account/project
    ├── staging account/project
    └── dev account/project
~~~

Phù hợp khi team sở hữu sản phẩm end-to-end và cần budget/quota theo workload. Policy production có thể được kế thừa từ parent group.

### Mẫu C: Kết hợp environment và business unit

~~~text
Organization
├── Business Unit: Commerce
│   ├── Production
│   └── NonProduction
├── Business Unit: Data
│   ├── Production
│   └── NonProduction
└── Platform
    ├── Shared Services
    ├── Security
    └── Network
~~~

Phù hợp tổ chức lớn có nhiều business unit và platform team. Cần tránh hierarchy quá sâu và khó hiểu.

### Tiêu chí chọn mẫu

- Số lượng team và workload.
- Mức độ độc lập của owner.
- Quy định bảo mật và dữ liệu.
- Cách tính billing và chargeback.
- Quota và region.
- Số lượng shared services.
- Khả năng automation.
- Năng lực vận hành account/subscription.

Không có mẫu duy nhất đúng cho mọi công ty. Bắt đầu từ ranh giới bảo mật và ownership, sau đó tối ưu cấu trúc để giảm overhead.

## 8. Thiết kế landing zone và baseline

Landing zone là nền tảng cloud được chuẩn bị sẵn để workload mới triển khai theo guardrail chung. Nó thường bao gồm:
- Hierarchy account/subscription/project.
- Identity federation và nhóm quyền.
- Network hub/spoke hoặc shared network.
- Logging/audit centralization.
- Security baseline.
- Policy và compliance controls.
- Billing, budget và cost allocation.
- Image/registry và CI/CD.
- Backup và disaster recovery.
- Automation để tạo phạm vi mới.

### Account factory hoặc project factory

Quy trình factory tạo phạm vi mới từ template:
1. Nhận yêu cầu workload.
2. Xác định owner, environment, data classification và region.
3. Chọn OU/folder/management group.
4. Tạo account/subscription/project.
5. Gán baseline policy và IAM.
6. Kết nối network/shared services.
7. Bật logging, monitoring và security.
8. Tạo budget, quota và tags.
9. Cấp quyền deployment role.
10. Ghi inventory và owner.
11. Chạy kiểm tra compliance.
12. Cho phép deploy workload.

Không tạo account thủ công không có owner hoặc không nằm trong hierarchy quản trị. Factory giúp tránh mỗi team tự tạo một cách khác nhau.

## 9. Identity và quyền truy cập theo hierarchy

Quyền truy cập nên được cấp theo vai trò và phạm vi cần thiết.

### Nhóm quyền thường gặp

- Organization/platform administrator.
- Account/subscription owner.
- Security auditor.
- Network administrator.
- Billing/cost analyst.
- Workload owner.
- Developer.
- CI/CD deployment identity.
- Read-only observer.
- Incident responder.

### Kế thừa quyền

Một số nền tảng cho phép gán quyền ở organization/folder/management group rồi kế thừa xuống dưới. Điều này tiện cho baseline nhưng có thể tạo quyền quá rộng nếu gán nhóm lớn ở scope cao.

Nguyên tắc:
- Gán quyền cấp cao cho nhóm quản trị nhỏ.
- Gán quyền workload ở account/subscription/project phù hợp.
- Tách quyền read, deploy, operate và administer.
- Dùng workload identity/role ngắn hạn cho automation.
- Tránh credential dài hạn dùng chung.
- Review quyền theo chu kỳ và khi owner thay đổi.

### Production access

Production nên có access path riêng:
- Developer không mặc định là owner.
- CI/CD dùng identity riêng, chỉ deploy đúng workload.
- Emergency access có thời hạn, audit và phê duyệt.
- Read-only production access có thể tách khỏi write access.
- Không dùng tài khoản cá nhân làm identity duy nhất cho automation.

### Service identity

Mỗi workload nên có service identity riêng theo nhiệm vụ. Ví dụ worker xử lý ảnh chỉ cần đọc object input và ghi output prefix; không cần quyền quản trị project hoặc truy cập database thanh toán.

## 10. Policy và guardrail theo cấp

Policy giúp áp dụng quy tắc thống nhất cho phạm vi lớn. Có thể kiểm soát:
- Allowed regions.
- Allowed machine families/SKUs.
- Public IP và public endpoint.
- Encryption requirement.
- Disk type và snapshot policy.
- Approved OS image.
- Mandatory tags.
- Network exposure.
- Logging và monitoring.
- Backup requirement.
- GPU quota hoặc accelerator type.
- Resource naming và location.

### Policy inheritance

Policy ở cấp organization/folder/subscription/project có thể kế thừa xuống resource. Cần hiểu:
- Policy nào là deny/explicit restriction.
- Policy nào chỉ audit hoặc cảnh báo.
- Exception được cấp ở scope nào.
- Ai có quyền tạo exception.
- Exception có expiry hay không.
- Policy conflict được giải quyết ra sao.

Không tạo exception không thời hạn. Ghi owner, lý do, risk, thời điểm hết hạn và bằng chứng review.

### Preventive và detective controls

- **Preventive:** chặn resource không tuân thủ trước khi tạo hoặc cập nhật.
- **Detective:** phát hiện sau khi resource đã tồn tại, tạo alert hoặc ticket.
- **Corrective:** tự sửa cấu hình hoặc yêu cầu owner remediation.

Ví dụ: policy có thể chặn tạo VM với public IP trong production; scanner có thể phát hiện disk không bật encryption; remediation workflow có thể gắn tag owner bị thiếu hoặc mở ticket cho team.

### Policy as code

Đưa policy vào version control, review qua pull request và triển khai bằng pipeline. Kiểm thử policy với:
- Resource hợp lệ.
- Resource vi phạm.
- Exception được phép.
- Resource đã tồn tại.
- Thay đổi có thể gây downtime.

Policy thay đổi ở cấp cao có thể ảnh hưởng hàng trăm workload. Rollout nên theo canary scope hoặc audit mode trước khi enforce khi nền tảng hỗ trợ.

## 11. Network boundary và shared connectivity

Hierarchy tài nguyên cần phối hợp với network architecture.

Các thành phần có thể được quản lý tập trung:
- Hub VPC/VNet.
- Transit gateway hoặc peering.
- VPN/private connectivity.
- DNS resolver.
- NAT/egress gateway.
- Firewall.
- Private endpoint.
- Load balancer.
- Network flow logs.

### Hub-and-spoke

Một mô hình phổ biến:
- Hub chứa shared network services và connectivity.
- Spoke chứa workload theo account/subscription/project.
- Route, firewall và DNS kiểm soát kết nối giữa spoke.
- Production và non-production có thể dùng hub riêng hoặc policy khác nhau.

~~~mermaid
flowchart TB
    HUB["Network hub: firewall, DNS, VPN, egress"] --> PROD["Production spokes"]
    HUB --> NONPROD["Non-production spokes"]
    HUB --> SHARED["Shared services"]
    PROD --> P1["Payments workload"]
    PROD --> P2["Compute platform"]
    NONPROD --> D1["Development"]
    NONPROD --> T1["Test / staging"]
~~~

Hub không nên trở thành điểm nghẽn hoặc single point of failure. Cần HA, capacity, route segmentation và quy trình change control.

### Không chia sẻ network một cách mặc định

Shared network giúp giảm trùng lặp nhưng có thể tạo:
- Lateral movement.
- Route conflict.
- DNS coupling.
- Egress cost khó phân bổ.
- Blast radius khi firewall thay đổi.
- Khó cô lập workload regulated.

Phân tách subnet, route table, firewall policy, security group và private endpoint theo trust boundary. VNet/VPC riêng không thay thế identity control.

## 12. Shared services và trách nhiệm ownership

Một số dịch vụ được nhiều workload sử dụng:
- Central logging và audit.
- Metrics/tracing.
- Container registry.
- Artifact repository.
- DNS.
- CI/CD runners.
- Secrets management.
- Security scanning.
- Backup vault.
- Network hub.
- Shared Kubernetes platform.

Cần xác định:
- Team sở hữu service.
- Consumer được phép sử dụng.
- Data classification.
- SLA và quota.
- Cost allocation.
- Incident escalation.
- Change/upgrade window.
- DR strategy.

### Shared services account/project

Có thể tạo phạm vi riêng cho platform services và cấp quyền sử dụng có kiểm soát. Tránh để shared service dùng một identity quản trị rộng trên mọi workload. Dùng cross-account role hoặc service identity có scope cụ thể.

### Chi phí shared services

Phân bổ theo driver phù hợp:
- Log ingest theo bytes/team.
- Registry storage theo image/project.
- Network egress theo flow hoặc bytes.
- Backup theo dung lượng/retention.
- CI/CD theo build minutes hoặc runner time.
- Kubernetes control/worker overhead theo request hoặc usage.

Nếu không thể phân bổ chính xác, ghi rõ đây là platform overhead chung và công bố policy.

## 13. Naming, tagging và metadata chuẩn

Naming và tagging giúp tìm kiếm, tự động hóa và phân bổ chi phí. Chúng không thay thế IAM hoặc resource hierarchy.

### Naming convention

Tên có thể bao gồm:
- Organization hoặc business unit.
- Workload/service.
- Environment.
- Region.
- Resource type.
- Instance ordinal nếu cần.

Ví dụ tên dễ đọc: `commerce-payments-prod-vm-01`. Tránh nhồi quá nhiều thông tin dễ thay đổi vào tên resource; metadata nên nằm trong tag/label.

### Tag/label bắt buộc

| Key | Mục đích | Ví dụ |
|---|---|---|
| owner | Người/team chịu trách nhiệm | platform-team |
| service | Tên workload | payments-api |
| environment | Môi trường | production |
| cost_center | Trung tâm chi phí | CC-410 |
| business_unit | Đơn vị kinh doanh | commerce |
| data_classification | Phân loại dữ liệu | confidential |
| managed_by | Công cụ quản lý | terraform |
| lifecycle | Loại vòng đời | long-lived |
| expiry_date | Hạn dọn tài nguyên tạm | 2026-12-15 |
| repository | Nguồn code/IaC | payments-infra |

Dùng từ điển giá trị hợp lệ và quy tắc viết thường/thống nhất. Không dùng email cá nhân hoặc secret làm tag.

### Tag coverage

Theo dõi:
- Tỷ lệ resource có owner.
- Tỷ lệ cost được gắn cost_center.
- Resource không có environment.
- Tag sai giá trị.
- Tag cũ sau khi workload đổi owner.
- Resource orphan không còn liên kết project/repository.

Policy có thể chặn hoặc audit resource thiếu tag. Với service không hỗ trợ tag, dùng inventory mapping hoặc parent scope.

## 14. Billing, budget và cost allocation

Resource hierarchy thường ảnh hưởng trực tiếp tới billing visibility. Account/subscription/project có thể là scope xuất hiện trong billing export hoặc cost management report.

### Cost allocation dimensions

Có thể tổng hợp cost theo:
- Organization.
- Account/subscription/project.
- Business unit.
- Team/owner.
- Service/workload.
- Environment.
- Region.
- SKU/machine family.
- Cost center.
- Shared platform.

### Direct và shared cost

- Direct cost có thể gắn trực tiếp với resource/workload.
- Shared cost cần driver allocation.
- Unallocated cost cần được báo cáo và có owner điều tra.

Không dùng tag environment làm bằng chứng cost đã được phân bổ chính xác nếu resource dùng chung nhiều environment.

### Budget theo scope

Có thể đặt budget:
- Account/subscription/project.
- Team hoặc cost center.
- Environment.
- Workload.
- Shared services.
- Migration hoặc performance test.

Budget alert có thể ở 50%, 75%, 90% và dự báo vượt ngưỡng. Ngưỡng cần theo mức độ quan trọng và chu kỳ billing.

### Budget không phải cơ chế dừng production

Khi đạt budget, production không nên tự động bị tắt nếu điều đó gây outage hoặc mất dữ liệu. Hành động nên theo policy:
- Thông báo owner.
- Điều tra anomaly.
- Dọn tài nguyên dev/test.
- Hạn chế tạo sandbox mới.
- Giảm workload không thiết yếu.
- Xin điều chỉnh ngân sách nếu demand hợp lệ.
- Giữ SLO và availability của dịch vụ trọng yếu.

## 15. Quota và capacity management

Quota giới hạn số lượng hoặc mức sử dụng tài nguyên trong một phạm vi. Ví dụ:
- vCPU theo region.
- Số VM theo family.
- GPU quota.
- Public IP.
- Disk/volume.
- Network address.
- Managed Kubernetes cluster.
- API request rate.

Quota có thể được đặt ở account, subscription, project, region hoặc service scope. Không giả định quota giống nhau giữa các scope.

### Phân bổ quota

Một quy trình:
1. Ước lượng baseline và peak demand.
2. Xác định quota theo region/SKU.
3. Dành headroom cho failover và upgrade.
4. Phân bổ quota giữa production và non-production.
5. Đặt owner và cảnh báo quota usage.
6. Yêu cầu tăng quota trước sự kiện tải lớn.
7. Rà soát quota không sử dụng.

### Tránh quota starvation

Một project development có thể vô tình chiếm hết quota GPU hoặc vCPU của subscription. Có thể:
- Tách production quota.
- Dùng subscription/project riêng.
- Đặt policy hạn chế machine family.
- Áp quota nội bộ theo team.
- Giữ quota reserve cho incident/failover.

Quota provider và quota nội bộ là hai lớp khác nhau. ResourceQuota của Kubernetes không tự tăng cloud quota; cloud quota không tự giới hạn requests trong namespace.

## 16. Quản lý compute theo hierarchy

Một workload compute thường gồm nhiều resource:
- VM hoặc node pool.
- Boot/data disk.
- NIC, subnet và public/private IP.
- Load balancer.
- Autoscaling group.
- Container registry/image.
- Monitoring/logging.
- Backup/snapshot.
- IAM role/service identity.
- Key management.
- DNS và network gateway.

Khi chọn account/project boundary, cần tính cả dependency. Nếu VM ở project A nhưng disk backup, key và logging ở project B, quyền và lifecycle cần được thiết kế rõ.

### Resource dependency map

Mỗi workload nên có inventory:
- Resource ID.
- Parent scope.
- Owner.
- Environment.
- Region/zone.
- Dependency.
- Data classification.
- Managed-by.
- Lifecycle/expiry.
- Backup/DR classification.

### Compute pool và environment

Production node pool có thể dùng machine family ổn định, image được harden và autoscaling min phù hợp. Development có thể dùng loại máy nhỏ, schedule stop và TTL. Performance test có thể tạm tăng quota trong một cửa sổ đã phê duyệt rồi tự động dọn dẹp.

Không nên để resource tạm tồn tại vô thời hạn chỉ vì nằm trong project test.

## 17. Tổ chức production và non-production an toàn

Một cấu trúc an toàn thường có:
- Identity tách biệt hoặc role riêng theo environment.
- Network boundary và egress policy khác nhau.
- Secret riêng.
- Data set riêng hoặc dữ liệu đã mask.
- Logging/audit central nhưng access có kiểm soát.
- Budget và quota riêng.
- Deployment pipeline có promotion gate.
- Backup/retention theo criticality.

### Không dùng secret production trong dev

Development/test nên dùng credential và key riêng. Nếu cần dữ liệu gần production, dùng dataset đã mask hoặc synthetic data. Không cấp quyền production chỉ để làm test tiện hơn.

### Promotion giữa environment

Một artifact được build một lần, sau đó promote qua dev → test → staging → production. Không build binary khác nhau tùy environment nếu không có lý do. Config và secret được inject theo môi trường.

### Drift giữa môi trường

Theo dõi khác biệt:
- IaC module/version.
- OS image.
- Runtime/container image.
- Network route/firewall.
- IAM role/policy.
- Quota.
- Observability agent.
- Autoscaling.
- Encryption/backup.

Staging không nhất thiết có capacity production, nhưng phải phản ánh những đặc tính quan trọng cần kiểm thử. Drift không được kiểm soát có thể khiến staging pass nhưng production fail.

## 18. Lifecycle của account, subscription và project

Phạm vi quản trị cũng có vòng đời.

### Tạo mới

- Có business owner.
- Có technical owner.
- Chọn parent scope.
- Gán policy baseline.
- Thiết lập identity và network.
- Bật audit/logging.
- Tạo budget/quota.
- Bắt buộc tags.
- Đăng ký inventory.
- Kiểm tra compliance trước khi deploy.

### Vận hành

- Review access định kỳ.
- Theo dõi budget và quota.
- Patch image/runtime.
- Rà soát resource orphan.
- Kiểm tra policy drift.
- Kiểm thử backup/restore.
- Quản lý exception và expiry.
- Xem xét owner khi team thay đổi.

### Decommission

Trước khi đóng account/project:
1. Xác nhận owner và phê duyệt.
2. Kiểm kê resource và dependency.
3. Xác nhận retention/legal hold.
4. Backup hoặc archive dữ liệu cần giữ.
5. Di chuyển DNS, traffic và workload.
6. Thu hồi identity và secret.
7. Xóa resource theo thứ tự dependency.
8. Xác nhận billing dừng hoặc residual charge.
9. Lưu audit evidence.
10. Đóng scope và cập nhật inventory.

Không xóa project/account chỉ vì không thấy VM. Disk, snapshot, IP, log, key, reservation hoặc managed service có thể vẫn tồn tại và phát sinh chi phí.

## 19. Infrastructure as Code và account vending

Tạo resource scope bằng IaC giúp lặp lại baseline và review được thay đổi.

Một pipeline có thể gồm:
- Request form hoặc service catalog.
- Policy validation.
- Provision account/subscription/project.
- Apply IAM, network và logging baseline.
- Create budget/quota/tags.
- Register inventory.
- Run compliance scan.
- Publish deployment target.

### Cấu trúc repository

Có thể chia:
- Organization baseline.
- Account/subscription/project factory.
- Network/shared services.
- Workload infrastructure.
- Environment overlays.
- Policy as code.
- CI/CD pipelines.

Không copy-paste cấu hình giữa hàng chục project. Dùng module có version, input rõ và kiểm thử.

### Ví dụ cấu hình khai báo

~~~yaml
workload:
  name: payments
  owner: commerce-platform
  business_unit: commerce
  data_classification: confidential
  environments:
    - name: development
      scope: nonprod-payments-dev
      region: region-a
      budget: dev-budget
    - name: production
      scope: prod-payments
      region: region-a
      budget: prod-budget
  guardrails:
    public_ip: false
    encryption_required: true
    approved_images_only: true
    owner_tag_required: true
~~~

Đây là ví dụ cấu hình nội bộ minh họa, không phải schema chuẩn của một cloud provider. Pipeline cần map các trường sang API và policy thực tế của nền tảng.

### Không để IaC trở thành đường vòng

Nếu pipeline có quyền quản trị quá rộng, người dùng có thể triển khai resource vi phạm policy qua IaC. Kiểm soát bằng:
- Review thay đổi.
- Policy validation.
- Identity theo workload.
- Protected branch/environment.
- Drift detection.
- Audit pipeline.
- Approval cho production.
- Secret ngắn hạn/federated identity.

## 20. Governance cho nhiều team và nhiều tenant

Khi tổ chức mở rộng, cần mô hình ownership rõ.

### RACI tham khảo

| Hoạt động | Platform | Security | Finance/FinOps | Workload team |
|---|---|---|---|---|
| Hierarchy và landing zone | Responsible | Consulted | Consulted | Informed |
| IAM baseline | Responsible | Accountable | Informed | Consulted |
| Policy compliance | Consulted | Accountable | Informed | Responsible remediation |
| Network hub | Responsible | Consulted | Informed | Consumer |
| Budget | Consulted | Informed | Accountable | Responsible forecast |
| Workload deployment | Platform support | Guardrail | Cost visibility | Accountable |
| Resource cleanup | Automation | Audit | Cost review | Owner |
| Incident response | Shared | Shared | Informed | Responsible for app |

RACI cần được điều chỉnh theo tổ chức. Mỗi resource scope phải có owner có thể liên hệ.

### Multi-tenant platform

Nếu một platform phục vụ nhiều team/tenant:
- Không coi project name là identity boundary.
- Dùng service identity riêng.
- Áp quota theo namespace/project.
- Tách network và secret.
- Ghi tenant attribution vào job/resource metadata.
- Không để tenant truy cập billing hoặc logs của tenant khác.
- Có policy cho noisy neighbor và fair share.

## 21. Theo dõi governance bằng metric

Một dashboard governance nên có:

| Metric | Ý nghĩa |
|---|---|
| Scope count by environment | Số account/subscription/project theo môi trường |
| Owner coverage | Tỷ lệ scope/resource có owner |
| Tag compliance | Tỷ lệ resource có tag bắt buộc |
| Policy compliance | Tỷ lệ resource đạt guardrail |
| Exception age | Tuổi của policy exception |
| Budget utilization | Mức sử dụng ngân sách |
| Forecast overrun | Dự báo vượt ngân sách |
| Quota utilization | Tỷ lệ quota đã dùng |
| Orphan resource cost | Chi phí resource không còn owner/dependency |
| Unallocated cost | Chi phí chưa gán được |
| Access review coverage | Tỷ lệ quyền đã review |
| Drift count | Số khác biệt so với baseline |
| Decommission backlog | Scope/workload chờ đóng |

### Cảnh báo

- Scope mới chưa có owner.
- Production scope thiếu audit/logging.
- Resource public exposure trái policy.
- Budget forecast vượt ngưỡng.
- Quota gần cạn.
- Exception quá hạn.
- Tag coverage giảm.
- Resource không được quản lý bởi IaC.
- Project không có hoạt động nhưng còn chi phí.
- Access key/role không được dùng hoặc quá rộng.

Cảnh báo nên gắn owner và hành động cụ thể. Không chỉ gửi một báo cáo tổng hợp mà không có người xử lý.

## 22. Ví dụ thiết kế cho một tổ chức compute

Một công ty có ba nhóm:
- Commerce chạy API thanh toán và đơn hàng.
- Data chạy batch analytics.
- Platform quản lý Kubernetes, network và logging.

Một cấu trúc có thể là:

~~~text
Organization
├── Production
│   ├── prod-commerce
│   │   ├── payments project
│   │   └── orders project
│   ├── prod-data
│   │   └── analytics project
│   └── prod-platform
│       ├── kubernetes platform
│       └── observability
├── NonProduction
│   ├── dev-commerce
│   ├── test-commerce
│   ├── dev-data
│   └── staging-platform
└── Governance
    ├── security-audit
    ├── central-logging
    └── network-hub
~~~

### Lý do phân tách

- Production và non-production có trust level khác nhau.
- Commerce và Data có owner, quota và cost center khác nhau.
- Platform shared services có lifecycle và quyền quản trị riêng.
- Security/audit cần lưu log tập trung với quyền truy cập hạn chế.
- Network hub được quản lý bởi platform/network team.

### Cách triển khai

1. Tạo organization hierarchy và parent policy.
2. Tạo production/non-production scopes.
3. Tạo workload scopes theo owner và billing.
4. Tạo shared network/logging/security scopes.
5. Gán role theo team và environment.
6. Áp policy allowed regions, encryption và public access.
7. Gán quota production và non-production.
8. Tạo budget và cost tags.
9. Bootstrap IaC pipeline.
10. Deploy workload theo promotion flow.
11. Kiểm tra policy, access, billing và inventory.

Không nhất thiết dùng đúng số project trong ví dụ. Khi workload tăng, có thể tách thêm nếu xuất hiện yêu cầu mới về quyền, quota, billing hoặc isolation.

## 23. Cách quyết định một workload cần scope riêng hay không

Dùng ma trận câu hỏi:

| Câu hỏi | Nếu câu trả lời là Có |
|---|---|
| Owner hoặc billing owner khác? | Cân nhắc project/account/subscription riêng |
| Trust level hoặc data classification khác? | Cân nhắc ranh giới mạnh hơn và policy riêng |
| Cần quota hoặc region riêng? | Tách scope nếu quota cấp hiện tại không đủ kiểm soát |
| Cần network isolation? | Thiết kế VPC/VNet/subnet/firewall; có thể cần account riêng |
| Lifecycle khác? | Tách project/resource group theo vòng đời |
| Cần audit/compliance độc lập? | Cân nhắc account/subscription boundary |
| Có noisy-neighbor hoặc blast-radius risk? | Tách capacity và quota |
| Chỉ khác tên ứng dụng? | Chưa đủ lý do để tạo scope mới |

### Quy trình quyết định

1. Xác định owner.
2. Xác định data classification và trust boundary.
3. Xác định quyền quản trị cần thiết.
4. Xác định billing và budget.
5. Xác định quota và region.
6. Xác định network dependency.
7. Xác định lifecycle.
8. Chọn cấp scope nhỏ nhất đáp ứng yêu cầu.
9. Áp baseline policy và tags.
10. Review sau khi workload vận hành.

## 24. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng tag environment để thay isolation | Dev có thể truy cập resource production | Tách identity, network và scope phù hợp |
| Một account cho toàn tổ chức | Blast radius và quyền quá rộng | Chia theo trust boundary và owner |
| Mỗi service một account dù không cần | Overhead network/IAM và quản trị | Gom workload cùng trust/owner |
| Project không có owner | Không ai xử lý cost hoặc incident | Bắt buộc owner metadata và review |
| Chỉ phân bổ cost theo tag | Shared resource bị tính sai hoặc bỏ sót | Kết hợp billing scope và allocation driver |
| Policy chỉ audit, không có remediation | Vi phạm kéo dài | Thêm owner, SLA và corrective workflow |
| Exception không hết hạn | Guardrail bị vô hiệu lâu dài | Có expiry và review |
| Shared network không phân đoạn | Lateral movement và blast radius | Route/firewall segmentation |
| Non-production dùng secret production | Credential leak và data exposure | Identity/secret riêng |
| Quota chỉ xem ở account tổng | Một team chiếm capacity | Quota nội bộ theo team/workload |
| Tạo scope thủ công | Drift và thiếu baseline | Account/project factory |
| Xóa project mà không inventory | Mất dữ liệu hoặc residual charge | Dependency scan và decommission workflow |
| IaC dùng quyền admin chung | Pipeline trở thành đường bypass policy | Federated identity và least privilege |
| Staging khác production không được ghi nhận | Test không phản ánh release risk | Drift report và documented differences |

## 25. Checklist triển khai governance

### Hierarchy và ownership
- [ ] Đã xác định organization/tenant và parent hierarchy.
- [ ] Đã định nghĩa semantics account, subscription và project theo provider.
- [ ] Mỗi scope có business owner và technical owner.
- [ ] Có quy tắc chọn cấp scope cho workload mới.
- [ ] Production và non-production được phân tách theo risk.
- [ ] Shared services có owner và consumer model.

### Identity và policy
- [ ] Có nhóm quyền theo platform, security, finance và workload.
- [ ] Production access được kiểm soát riêng.
- [ ] Automation dùng workload identity/federation.
- [ ] Có least privilege và access review.
- [ ] Policy allowed region, encryption, public access và image được áp dụng.
- [ ] Exception có owner, lý do và expiry.
- [ ] Audit log được lưu tập trung và bảo vệ.

### Network và data
- [ ] Network hub/spoke hoặc mô hình tương đương có owner.
- [ ] Route, DNS, firewall và egress được kiểm soát.
- [ ] Shared network không tạo lateral access ngoài ý muốn.
- [ ] Secret tách theo environment.
- [ ] Data production không bị sao chép tùy tiện sang non-production.
- [ ] Backup, retention và decommission được định nghĩa.

### Cost và quota
- [ ] Billing scope map được tới workload/team.
- [ ] Có mandatory owner/service/environment/cost_center tags.
- [ ] Shared cost có allocation policy.
- [ ] Budget theo scope và workload có owner.
- [ ] Quota theo region/SKU được theo dõi.
- [ ] Có headroom cho production failover và upgrade.
- [ ] Có alert budget/forecast/quota.

### Automation và lifecycle
- [ ] Có account/subscription/project factory.
- [ ] IaC module có version và review.
- [ ] Pipeline dùng identity riêng và quyền tối thiểu.
- [ ] Có compliance scan và drift detection.
- [ ] Sandbox có TTL hoặc expiry.
- [ ] Decommission có inventory, backup và residual-cost check.
- [ ] Governance dashboard có owner và remediation workflow.

## Kết luận

Tổ chức tài nguyên compute theo account, subscription, project và environment là cách thiết lập ranh giới quản trị cho identity, policy, network, quota, billing và vòng đời. Account/subscription thường phù hợp với ranh giới quản trị hoặc cô lập lớn; project gom workload theo owner, API, quota và chi phí tùy provider; environment thể hiện trust level và release lifecycle. Tag giúp phân loại và phân bổ nhưng không thay thế IAM hay network isolation. Landing zone và account/project factory giúp mọi phạm vi mới nhận baseline nhất quán. Một hierarchy hiệu quả phải cân bằng isolation với overhead, có owner rõ, policy được tự động hóa, quota/budget được theo dõi và quy trình decommission kiểm tra cả dependency lẫn residual charge.
