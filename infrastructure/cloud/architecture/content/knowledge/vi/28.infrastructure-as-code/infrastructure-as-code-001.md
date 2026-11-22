# Khai báo hạ tầng và thiết kế cấu trúc mã nguồn

## 1. Hạ tầng dưới dạng mã giải quyết vấn đề gì?

Một hệ thống cloud được tạo từ nhiều thành phần: network, subnet, firewall, identity, compute, load balancer, database, storage, queue, monitoring và policy. Nếu mỗi thành phần được tạo thủ công qua console, cấu hình thường khó lặp lại, khó review, khó truy vết và dễ khác nhau giữa development, staging và production.

**Infrastructure as Code (IaC)** là cách mô tả hạ tầng bằng các tệp có thể đọc, review, kiểm tra và thực thi bằng công cụ. Thay đổi hạ tầng đi qua quy trình tương tự thay đổi phần mềm: lưu trong version control, review, kiểm thử, lập kế hoạch, triển khai và theo dõi drift.

IaC giúp:

- Tạo môi trường nhất quán và có thể tái lập.
- Review thay đổi trước khi chúng tác động lên tài nguyên thật.
- Tái sử dụng cấu hình qua module và quy ước chung.
- Ghi lại lịch sử thay đổi và người phê duyệt.
- Tự động hóa provisioning, update và teardown.
- Hỗ trợ audit, disaster recovery và capacity planning.
- Giảm phụ thuộc vào kiến thức chỉ một cá nhân nắm giữ.

IaC không tự bảo đảm kiến trúc đúng hoặc an toàn. Một cấu hình sai được tự động triển khai nhanh có thể mở rộng phạm vi ảnh hưởng nhanh hơn thao tác thủ công. Vì vậy cần kết hợp thiết kế, policy as code, kiểm thử, quyền triển khai tối thiểu và quy trình vận hành.

Trong module **CLOUD_ARCHITECTURE**, IaC là cầu nối từ quyết định kiến trúc sang network, compute, data, security và deployment. Thiết kế cần cân bằng **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành** theo tư duy Well-Architected.

Ví dụ xuyên suốt: nền tảng đặt chỗ có một network boundary, cụm ứng dụng, database riêng tư, object storage, queue, IAM role và observability stack. Các môi trường dev, staging và prod có cùng cấu trúc logic nhưng khác kích thước, dữ liệu và chính sách.

## 2. Khai báo (declarative) và mệnh lệnh (imperative)

| Cách tiếp cận | Mô tả | Ví dụ |
| --- | --- | --- |
| Declarative | Khai báo trạng thái mong muốn; công cụ so sánh trạng thái hiện tại và tìm cách đưa về trạng thái đó | Network cần có 3 subnet, database private và bật encryption |
| Imperative | Mô tả từng bước hoặc lệnh cần chạy để tạo/thay đổi trạng thái | Chạy lệnh tạo VPC, rồi tạo subnet, rồi gắn route |

Với declarative IaC, người thiết kế tập trung vào trạng thái cuối và dependency graph. Công cụ lập kế hoạch những thao tác cần thực hiện. Với imperative automation, tác giả kiểm soát thứ tự thao tác và thường phải tự quản lý trạng thái, idempotency và rollback.

Không có lựa chọn tuyệt đối. Declarative phù hợp với resource lifecycle có provider hỗ trợ; imperative hữu ích cho bootstrap, migration hoặc tác vụ mà provider chưa mô tả được. Có thể kết hợp, nhưng cần ranh giới rõ để hai công cụ không cùng quản lý một resource.

### 2.1. Idempotency và convergence

Một thao tác idempotent có thể chạy lại mà không tạo thêm tác động ngoài ý muốn sau khi trạng thái mong muốn đã đạt. Với IaC, mục tiêu là lần apply thứ hai không tiếp tục tạo thay đổi không cần thiết nếu cấu hình và môi trường không đổi.

Convergence là khả năng đưa hệ thống dần về trạng thái khai báo. Điều này phụ thuộc provider, API và resource. Một số thuộc tính chỉ cập nhật tại chỗ; số khác buộc replace resource; một số dịch vụ bất đồng bộ và cần thời gian ổn định.

Không giả định mọi resource đều có thể update an toàn. Phải đọc plan để nhận biết create, update, replace và destroy trước khi triển khai.

## 3. Tách kiến trúc thành các lớp mã nguồn

Một repository IaC tốt giúp người đọc trả lời nhanh: môi trường nào đang được quản lý; thành phần hạ tầng nằm ở đâu; giá trị nào là cấu hình theo môi trường; module nào được dùng chung; state nằm ở đâu; pipeline nào triển khai và cách kiểm tra/phục hồi ra sao.

Một cấu trúc tham khảo:

~~~text
cloud-platform/
  README.md
  docs/
    architecture.md
    decisions/
  modules/
    network/
    identity/
    compute-service/
    database/
    object-storage/
    observability/
  environments/
    dev/
      main.tf
      variables.tf
      outputs.tf
      backend.hcl
      dev.tfvars
    staging/
      main.tf
      variables.tf
      outputs.tf
      backend.hcl
      staging.tfvars
    prod/
      main.tf
      variables.tf
      outputs.tf
      backend.hcl
      prod.tfvars
  policies/
  tests/
  scripts/
~~~

Đây là cấu trúc minh họa theo phong cách Terraform. Pulumi, CloudFormation, Bicep, CDK hoặc công cụ khác có thể có cách bố trí tệp và lifecycle khác. Mục tiêu là giữ rõ ranh giới giữa module tái sử dụng, composition của môi trường, policy, test và tài liệu.

### 3.1. Modules và environment composition

- **Module:** đóng gói một phần hạ tầng có giao diện đầu vào/đầu ra ổn định, ví dụ database private hoặc service compute.
- **Environment composition/root stack:** kết nối các module để tạo một môi trường cụ thể.
- **Policy:** kiểm tra hoặc giới hạn những gì module/environment được phép tạo.
- **Test:** kiểm tra contract và hành vi dự kiến.
- **Documentation:** giải thích mục đích, giả định và cách vận hành.

Module không nên tự quyết định mọi thứ của tổ chức. Network module có thể nhận danh sách CIDR, nhưng organization policy mới là nơi định nghĩa region được phép hoặc quy tắc bắt buộc chung.

## 4. Thiết kế module theo ranh giới kiến trúc

Module tốt đóng gói một capability có cohesion cao và coupling thấp. Không nên tạo một module duy nhất chứa toàn bộ hệ thống, cũng không cần biến mọi resource nhỏ thành module riêng.

Một module database có thể quản lý database instance/cluster, subnet group, encryption setting, backup/retention, parameter group, security rule cần thiết và monitoring output. Module database không nên âm thầm tạo các user nghiệp vụ, cấp quyền admin cho ứng dụng hoặc tạo resource ở nhiều environment ngoài phạm vi của nó.

### 4.1. Interface của module

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Inputs | Giá trị caller cung cấp hoặc được phép tùy chỉnh | name, subnet IDs, engine version, size |
| Defaults | Giá trị an toàn, phổ biến và có chủ đích | encryption enabled, deletion protection |
| Validation | Kiểm tra đầu vào trước khi tạo resource | CIDR hợp lệ, retention trong khoảng cho phép |
| Outputs | Thông tin cần cho module/caller khác | endpoint, resource ID, security group ID |
| Dependencies | Quan hệ tới capability khác | private subnets, KMS key, security boundary |
| Version | Contract và hành vi của module | semantic version hoặc source revision |
| Documentation | Cách dùng, giới hạn, ví dụ và migration | README/module docs |

Inputs ít nhưng có ý nghĩa giúp module dễ dùng. Một module với hàng trăm biến tùy chỉnh thường khó kiểm soát. Ngược lại, module quá cứng khiến team fork hoặc bypass. Hãy mở đúng các lựa chọn có lý do kiến trúc.

### 4.2. Encapsulation và abstraction

Module che giấu chi tiết triển khai nhưng không nên che giấu tác động quan trọng. Nếu một biến đổi cấu hình có thể gây replace database hoặc xóa storage, module phải thể hiện rõ và tài liệu phải cảnh báo. Không tạo abstraction khiến người dùng không thể nhận biết network exposure, encryption, backup hoặc cost tier.

### 4.3. Versioning module

Thay đổi input/output hoặc semantics có thể phá các environment đang sử dụng. Cần version module, ghi breaking changes, duy trì compatibility khi có thể, cung cấp migration guide, test consumer đại diện và nâng version theo pull request, plan và rollout có kiểm soát.

Không dùng tham chiếu branch chính thay đổi liên tục cho production nếu không có quy trình pinning và kiểm chứng rõ.

## 5. Đặt tên và tổ chức resource nhất quán

Tên resource hỗ trợ tìm kiếm, audit, phân bổ chi phí và vận hành. Một naming convention có thể gồm:

~~~text
<organization>-<environment>-<region>-<domain>-<resource>
~~~

Ví dụ:

~~~text
acme-prod-sea1-booking-db
acme-stg-sea1-platform-private-subnet-a
acme-dev-sea1-booking-api
~~~

Tên thật cần tuân theo giới hạn và charset của từng dịch vụ. Không nhét secret, email, tên người dùng hoặc dữ liệu nhạy cảm vào resource name.

### 5.1. Tags/labels tối thiểu

| Tag | Mục đích |
| --- | --- |
| application | Hệ thống sở hữu resource |
| environment | dev/staging/prod |
| owner | Team chịu trách nhiệm |
| cost-center | Phân bổ chi phí |
| data-classification | Phân loại dữ liệu |
| managed-by | IaC/pipeline chịu trách nhiệm |
| lifecycle | persistent/temporary/expiry |

Tag không thay thế IAM hoặc network policy. Không được cho rằng resource có tag production thì tự động an toàn; policy phải kiểm tra cấu hình và ranh giới thật.

## 6. Quản lý cấu hình theo môi trường

Dev, staging và prod thường chia sẻ cấu trúc nhưng khác cấu hình:

| Thuộc tính | Dev | Staging | Prod |
| --- | --- | --- | --- |
| Compute size | Nhỏ | Gần prod hoặc đại diện tải test | Theo capacity plan |
| Data | Synthetic | Masked/synthetic | Dữ liệu thật theo kiểm soát |
| Availability | Có thể đơn giản hơn | Mô phỏng HA khi cần | Theo SLO |
| Backup | Phục vụ thử nghiệm | Kiểm thử restore | Theo RPO/retention |
| Network | Tách môi trường | Tương đồng prod | Boundary chặt |
| Access | Developer scope | Test/release scope | Workload/admin scope riêng |

Không nên sao chép nguyên cấu hình dev sang production mà không xét sizing, resilience, privacy và access boundary. Cũng không nên để staging khác production hoàn toàn nếu mục tiêu là phát hiện lỗi trước release.

### 6.1. Tách code và data

Giữ cùng module nhưng truyền giá trị khác nhau theo environment. Không tạo ba bản module copy-paste nếu khác biệt chỉ là sizing hoặc subnet ID.

Các giá trị nhạy cảm như database password, signing key hoặc token không nên commit trong tfvars/parameter file. Hãy tham chiếu secret manager và cấp quyền đọc cho đúng workload/deployment identity.

## 7. State: dữ liệu quan trọng của IaC

Với nhiều công cụ declarative, state lưu mapping giữa resource được khai báo và resource thật, cùng metadata cần cho plan/update. State có thể chứa thông tin nhạy cảm tùy resource/provider và không nên xem là file cấu hình thông thường.

### 7.1. Local state và remote state

| Loại | Ưu điểm | Rủi ro/đánh đổi |
| --- | --- | --- |
| Local state | Dễ học và thử nghiệm nhỏ | Khó cộng tác, dễ mất hoặc ghi đè, backup thủ công |
| Remote state | Cộng tác và automation tốt hơn, có thể kết hợp locking/versioning | Cần quản trị backend, quyền, encryption, availability và chi phí |

Production thường cần remote backend có access control, encryption, versioning/backup và locking phù hợp. Không commit state vào repository công khai hoặc chia sẻ rộng.

### 7.2. State locking

Locking ngăn hai tiến trình cùng sửa một state đồng thời. Không phải backend nào cũng hỗ trợ locking giống nhau; cần kiểm tra semantics của công cụ và backend. Khi pipeline bị ngắt, lock có thể cần xử lý có kiểm soát. Không xóa lock thủ công khi chưa xác định process sở hữu và khả năng ghi đang diễn ra.

### 7.3. State separation

Có thể tách state theo environment, account/project, domain hoặc blast radius. Tách quá lớn làm dependency và output phức tạp; gộp quá nhiều khiến một thay đổi có thể ảnh hưởng phạm vi rộng và tăng nguy cơ lock contention.

Một nguyên tắc thực tế là phân chia theo lifecycle và owner: network foundation, shared platform services, workload stack và từng môi trường có thể có state riêng. Mọi tham chiếu state từ stack khác cần quyền đọc tối thiểu.

### 7.4. State backup và recovery

- Bật versioning hoặc snapshot backend theo khả năng.
- Hạn chế quyền đọc/ghi state.
- Mã hóa khi lưu và truyền.
- Không log full state trong CI.
- Kiểm tra quy trình restore state và mapping resource.
- Quy định xử lý state lock và state corruption.
- Audit thao tác import, move, remove và recovery.

Nếu mất state nhưng resource vẫn tồn tại, không tạo lại mù quáng. Cần import hoặc khôi phục mapping theo quy trình được kiểm thử.

## 8. Dependency graph và thứ tự triển khai

Một kiến trúc cloud có dependency: network trước compute, identity trước service access, database trước application endpoint, monitoring và logging cần sẵn sàng khi workload chạy.

~~~mermaid
flowchart TD
    ORG["Organization / IAM baseline"]
    NET["Network foundation"]
    SEC["Secrets / KMS / security policy"]
    DATA["Database / Object Storage"]
    COMPUTE["Compute / Container platform"]
    APP["Application services"]
    OBS["Monitoring / Logging / Alerts"]
    ORG --> NET
    ORG --> SEC
    NET --> DATA
    NET --> COMPUTE
    SEC --> DATA
    SEC --> COMPUTE
    DATA --> APP
    COMPUTE --> APP
    APP --> OBS
    DATA --> OBS
~~~

IaC engine có thể suy ra dependency từ reference giữa resource. Nếu dependency không thể biểu diễn qua reference, một số công cụ hỗ trợ khai báo phụ thuộc tường minh. Chỉ thêm explicit dependency khi thật sự cần; dependency thừa có thể làm giảm song song và tạo thứ tự giả.

### 8.1. Dependency giữa stack/repository

Khi network và workload ở hai state khác nhau, cần contract rõ: network cung cấp subnet ID, route table, security boundary; workload stack tiêu thụ outputs đó. Tránh truy vấn resource theo tên mơ hồ hoặc hard-code ID dễ thay đổi.

Có thể công bố output qua remote state, parameter store, service catalog hoặc artifact cấu hình có version. Mỗi cách phải xác định quyền truy cập, consistency và cách xử lý breaking change.

## 9. Ví dụ Terraform-style khai báo hạ tầng

Ví dụ sau minh họa ý tưởng, không phải cấu hình production hoàn chỉnh và không gắn với một cloud provider cụ thể:

~~~hcl
variable "environment" {
  type = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "private_subnet_ids" {
  type = list(string)
}

module "booking_database" {
  source = "../../modules/database"

  name                 = "booking-" + var.environment
  environment          = var.environment
  subnet_ids           = var.private_subnet_ids
  encryption_enabled   = true
  public_access        = false
  backup_retention_days = var.environment == "prod" ? 14 : 2
}

output "database_endpoint" {
  value = module.booking_database.endpoint
}
~~~

Ví dụ thể hiện environment là input có validation, subnet IDs được truyền từ foundation và database module được gọi với security intent rõ. Module thật còn cần version pinning, provider configuration, password/secret handling, monitoring, parameter compatibility, deletion protection và policy validation.

## 10. Cấu hình provider, version và dependency

IaC repository có dependency ngoài như provider plugin, module registry, package library hoặc CLI. Version trôi nổi có thể làm plan thay đổi dù source không đổi.

Nên pin version tool/provider/module theo chính sách; commit lock file nếu hệ sinh thái hỗ trợ; review thay đổi dependency như thay đổi mã nguồn; kiểm tra checksum/signature hoặc nguồn artifact khi công cụ hỗ trợ; dùng registry/repository đáng tin cậy; và có quy trình cập nhật phiên bản, kiểm tra compatibility.

Không khóa mọi dependency vĩnh viễn. Cần lịch nâng cấp để nhận security fix, bug fix và API mới, nhưng phải kiểm thử có kiểm soát.

## 11. Secret, identity và quyền triển khai

IaC có quyền lớn vì có thể tạo database, network, IAM và xóa tài nguyên. Vì vậy pipeline triển khai là một security boundary.

### 11.1. Không lưu secret trong source

Không commit password, private key, access token hoặc provider credential trong tfvars/config file, variable default, output, plan artifact không được bảo vệ, CI log hoặc container image.

Dùng workload identity/federation hoặc credential ngắn hạn cho pipeline khi có thể. Secret runtime được workload đọc từ secret manager theo least privilege. Lưu ý state và plan vẫn có thể chứa secret nếu provider/resource ghi giá trị nhạy cảm vào metadata.

### 11.2. Tách quyền plan và apply

- Pull request có thể chạy validate/plan với quyền đọc cần thiết.
- Apply production chỉ chạy từ protected branch/environment.
- Deployment identity chỉ có quyền thay đổi resource trong scope được giao.
- IAM/policy thay đổi nhạy cảm có review độc lập.
- Không cho fork/untrusted PR nhận credential ghi production.
- Log/audit lưu principal, commit, plan và deployment result.

Không mặc định một người viết module cũng nên có quyền admin organization.

## 12. Kiểm thử IaC trước và sau triển khai

| Lớp | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Format/lint | Phong cách và lỗi cấu trúc | Formatter, linter |
| Validate | Schema, type, required argument | Validate command |
| Unit/policy test | Contract và guardrail | Test input/output, policy rule |
| Static security scan | Phát hiện cấu hình nguy hiểm | Public storage, open firewall, unencrypted DB |
| Plan review | Xem thay đổi dự kiến | Create/update/replace/destroy |
| Integration test | Resource hoạt động cùng nhau | Service truy cập private DB |
| Smoke test | Kiểm tra sau apply | Health check, DNS, auth, data access |
| Drift scan | So sánh actual với desired state | Scheduled plan/config assessment |

### 12.1. Kiểm thử module

Module nên có test cho giá trị mặc định an toàn; input hợp lệ và không hợp lệ; output contract; security invariants như database không public; các environment/plan quan trọng; thay đổi version và backward compatibility.

Test không thay thế review plan. Một module có test pass vẫn có thể tạo thay đổi phá hủy khi input production đổi.

## 13. Plan, apply và review thay đổi

Với công cụ dạng plan/apply, plan là artifact quan trọng để review. Người phê duyệt cần xem resource nào được tạo, cập nhật, thay thế hoặc xóa; resource nhạy cảm; network impact; database replacement/downtime; IAM quyền mới; cost estimate; và tác động cross-module/environment.

Plan nên được tạo từ cùng source commit, tool/provider version và input mà pipeline sẽ apply. Nếu code hoặc variables đổi sau approval, phải tạo plan mới và review lại.

### 13.1. Destructive changes

Xóa database, bucket, key, network hoặc stateful resource cần quy trình bảo vệ: deletion protection, backup verified, explicit approval, maintenance window và recovery plan. Không dựa vào một dấu xác nhận tự động trong pipeline để xóa tài nguyên quan trọng.

## 14. CI/CD pipeline cho IaC

~~~mermaid
flowchart TD
    PR["Pull request"]
    FMT["Format / lint / validate"]
    SEC["Policy and security scan"]
    PLAN["Generate plan"]
    REVIEW["Code review / approval"]
    APPLY["Apply with scoped identity"]
    POST["Smoke test / health checks"]
    DRIFT["Scheduled drift detection"]
    PR --> FMT --> SEC --> PLAN --> REVIEW --> APPLY --> POST
    POST --> DRIFT
    DRIFT -->|"Finding"| PR
~~~

Một pipeline thực tế có thể checkout đúng commit; cài tool/provider theo version đã pin; format/lint/validate; chạy policy/security test; khởi tạo backend và tải state theo quyền giới hạn; sinh plan và lưu artifact có kiểm soát; review/approval; apply đúng plan đã phê duyệt nếu công cụ hỗ trợ; chạy smoke test; lưu deployment evidence; và quét drift định kỳ.

Pipeline phải có timeout, retry phù hợp, concurrency control theo state và xử lý khi job bị hủy giữa chừng. Không chạy hai apply đồng thời trên cùng state nếu backend/locking không bảo đảm an toàn.

## 15. Drift detection và quản lý thay đổi ngoài IaC

Drift xảy ra khi actual infrastructure khác desired configuration. Nguyên nhân có thể là thao tác console, automation khác, thay đổi do cloud service hoặc state không đồng bộ.

Các lựa chọn xử lý:

- **Reconcile:** cập nhật actual resource về desired state bằng apply.
- **Import/adopt:** đưa resource được tạo ngoài IaC vào quản lý.
- **Update code:** chấp nhận thay đổi hợp lệ và cập nhật source.
- **Revert:** đưa cấu hình về trạng thái trước nếu thay đổi không được phép.
- **Exception:** cho phép tạm thời với owner, lý do và expiry.

Không tự động revert mọi drift. Ví dụ thay đổi khẩn cấp để ngăn sự cố có thể là hợp lệ; cần xác minh, cập nhật IaC và lưu audit. Auto-remediation cũng có thể gây downtime nếu thay thế resource ngoài ý muốn.

### 15.1. Drift review

Phát hiện drift và xác định resource/field; so sánh actor/change log; phân loại hợp lệ hay vi phạm; đánh giá impact/severity; chọn reconcile, import, sửa code hoặc exception; review và triển khai; chạy lại scan và lưu bằng chứng.

## 16. State migration, refactor và lifecycle

Khi đổi cấu trúc repository hoặc tên module/resource, IaC có thể hiểu resource cũ bị xóa và resource mới được tạo. Với database, storage hoặc network, việc replace có thể gây mất dữ liệu hoặc downtime.

Các thao tác state move/import/remove cần backup state; hiểu mapping address cũ/mới; dùng tính năng move/rename chính thức khi phù hợp; sinh plan để xác nhận không có destroy/create ngoài dự kiến; thực hiện từng scope nhỏ và có rollback; giữ lịch sử commit và evidence.

Lifecycle policy có thể ngăn destroy hoặc bảo vệ resource quan trọng. Đây là lớp guardrail bổ sung, không thay thế backup và review. Có thể thiết lập retention cho temporary environment, nhưng phải đảm bảo cleanup không xóa dữ liệu cần giữ.

## 17. Cost, tagging và vận hành lâu dài

IaC quyết định quy mô, số lượng và topology resource nên ảnh hưởng trực tiếp tới chi phí. Code có thể hợp lệ về cú pháp nhưng quá đắt hoặc không có owner.

Nên đưa vào review instance size, autoscaling bounds và idle capacity; database tier/storage/IOPS/backup/replica; network egress và cross-zone/region transfer; log/metric retention và ingestion; queue/cache/search capacity; resource tags/owner/cost center/expiry; và budget/limit theo project/account.

Không tối ưu chỉ theo chi phí thấp nhất. Tier rẻ có thể không đạt availability, latency hoặc RPO/RTO. Quyết định nên thể hiện rõ trade-off giữa cost và SLO.

## 18. Bài thực hành: xây dựng cấu trúc IaC cho nền tảng đặt chỗ

**Bối cảnh giả định:** team cần tạo ba môi trường dev, staging và prod cho Booking Platform. Mỗi môi trường có network, compute, database, object storage, queue và monitoring. Prod yêu cầu private database, encryption, backup, central logging và workload identity.

### Nhiệm vụ

1. Đề xuất cấu trúc repository gồm modules, environments, policies, tests, scripts và docs.
2. Xác định ranh giới module network, identity, database, compute, storage và observability.
3. Thiết kế input/output contract, defaults và validation của module database.
4. Tách environment configuration khỏi reusable module; xác định giá trị khác nhau và giá trị dùng chung.
5. Chọn state boundary, remote backend, locking, versioning, backup và quyền truy cập.
6. Vẽ dependency graph và xác định thứ tự bootstrap.
7. Thiết kế IAM/workload identity cho CI plan/apply và runtime services.
8. Viết policy kiểm tra encryption, private networking, region, tagging và public exposure.
9. Xây pipeline format, validate, test, scan, plan, review, apply và smoke test.
10. Mô phỏng drift do console change và lựa chọn reconcile/import/exception.
11. Kiểm tra plan có replace database hoặc destroy storage ngoài dự kiến; thiết kế approval.
12. Viết ADR cho repository layout, state split, module versioning và cost guardrail.

### Mẫu cấu trúc đề xuất

| Thư mục | Nội dung | Owner |
| --- | --- | --- |
| modules/network | VPC/VNet, subnet, route, security boundary | Cloud platform |
| modules/database | Database, backup, encryption, monitoring | Data platform |
| modules/compute-service | Runtime, autoscaling, health check | Application platform |
| modules/identity | Workload roles, trust, scoped permission | IAM platform |
| environments/dev | Composition và dev inputs | Development team |
| environments/staging | Composition và staging inputs | Release/platform |
| environments/prod | Composition và production inputs | Production owner |
| policies | Guardrail và compliance rules | Security/platform |
| tests | Module, policy, integration test | Module owner |
| docs/decisions | Architecture decision records | Architecture owner |

### Tiêu chí hoàn thành

- Repository có ranh giới module/environment/policy/test rõ.
- Module có interface nhỏ, validation và output contract.
- Environment dùng chung module nhưng có config và state boundary phù hợp.
- State được bảo vệ, backup và locking theo khả năng backend.
- Dependency graph phản ánh đúng thứ tự và contract giữa stack.
- Secret không được commit; pipeline dùng identity có scope.
- Có format/validate/test/security scan/plan review/smoke test.
- Destructive changes có approval và recovery plan.
- Drift có owner và quy trình reconcile.
- Cost tag, owner và lifecycle được kiểm tra.

## 19. Checklist Well-Architected trước khi đưa IaC vào production

- [ ] Mỗi resource thuộc đúng module và có owner/lifecycle rõ ràng.
- [ ] Cấu trúc repository phân biệt reusable module, environment composition, policy, test và documentation.
- [ ] Module có interface rõ, input validation, defaults an toàn và output contract.
- [ ] Module/provider/tool version được pin và cập nhật có kiểm soát.
- [ ] Environment dùng cùng module nhưng có cấu hình, quyền và dữ liệu phù hợp.
- [ ] Không commit secret; state/plan được bảo vệ như dữ liệu nhạy cảm.
- [ ] Remote state có access control, encryption, versioning/backup và locking phù hợp.
- [ ] State boundary theo lifecycle/owner và giảm blast radius.
- [ ] Dependency graph và outputs giữa stack có contract rõ.
- [ ] IAM pipeline/runtime tuân theo least privilege và workload identity.
- [ ] Policy kiểm tra network exposure, encryption, region, backup và tagging.
- [ ] CI kiểm tra format, validate, policy, security, plan và integration phù hợp.
- [ ] Plan được review từ cùng commit/version/input sẽ apply.
- [ ] Destructive replace/destroy có approval, backup và rollback/recovery plan.
- [ ] Drift được phát hiện liên tục và phân loại trước remediation.
- [ ] State move/import/refactor được backup và xác minh plan.
- [ ] Cost, quota, egress, retention và resource lifecycle được đánh giá.
- [ ] Có audit evidence, runbook, smoke test và owner vận hành.
- [ ] ADR ghi rõ đánh đổi reliability, security, performance, cost và operations.

**Điểm cốt lõi:** IaC chuyển kiến trúc thành mã nguồn có thể review, kiểm tra và tái lập. Cấu trúc tốt tách module theo capability, composition theo môi trường, state theo lifecycle/owner và policy/test theo guardrail. Khi kết hợp version control, plan review, quyền triển khai tối thiểu, state protection, drift detection và quy trình phục hồi, IaC trở thành nền tảng vận hành cloud nhất quán thay vì chỉ là tập hợp các tệp cấu hình.
