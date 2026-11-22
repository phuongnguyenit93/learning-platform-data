# Plan review, policy checks và bảo vệ thao tác hủy

Terraform giúp mô tả hạ tầng Google Cloud bằng mã và tạo ra một kế hoạch thay đổi trước khi áp dụng. Tuy nhiên, một lệnh `terraform apply` có thể tạo mới, cập nhật, thay thế hoặc xóa tài nguyên đang phục vụ production. Vì vậy, đọc và phê duyệt plan là một bước kiểm soát quan trọng trong quy trình Infrastructure as Code (IaC).

Một quy trình tốt kết hợp ba lớp: **review plan để hiểu tác động**, **policy checks để tự động chặn cấu hình không đạt yêu cầu**, và **cơ chế bảo vệ thao tác hủy để giảm nguy cơ xóa nhầm tài nguyên hoặc dữ liệu**. Trên GCP, các kiểm soát này cần phối hợp với IAM, Organization Policy, cấu hình bảo vệ riêng của dịch vụ, backend lưu Terraform state và quy trình CI/CD.

Bài học này trình bày cách phân tích Terraform plan, xuất và kiểm tra JSON plan, xây dựng policy gate, quản lý state và phê duyệt thay đổi, rồi thiết kế quy trình destroy an toàn cho các tài nguyên như Compute Engine, Cloud SQL và Cloud Storage.

## 1. Vòng đời thay đổi Terraform

Một quy trình IaC thường gồm các bước:

1. Viết hoặc chỉnh sửa cấu hình Terraform.
2. Format và kiểm tra cú pháp, module, provider.
3. Khởi tạo thư mục làm việc và tải provider/module cần thiết.
4. Tạo plan để so sánh cấu hình mong muốn với state và hạ tầng hiện tại.
5. Review plan và chạy policy checks.
6. Phê duyệt thay đổi theo môi trường và mức độ rủi ro.
7. Áp dụng chính plan đã được phê duyệt.
8. Kiểm tra kết quả, cập nhật state và lưu bằng chứng triển khai.

Sơ đồ tổng quát:

~~~mermaid
flowchart TD
    A[Terraform configuration change] --> B[fmt and validate]
    B --> C[terraform plan -out]
    C --> D[Review human-readable plan]
    D --> E[Policy checks on plan JSON]
    E --> F{Checks passed?}
    F -->|No| G[Fix configuration or request exception]
    G --> B
    F -->|Yes| H[Approval gate]
    H --> I[Apply the reviewed saved plan]
    I --> J[Verify GCP resources and outputs]
    J --> K[Record deployment evidence]
~~~

Không nên xem plan là một bản tóm tắt đơn giản. Plan là kết quả tính toán của Terraform tại một thời điểm, dựa trên cấu hình, state, provider và thông tin đọc được từ API. Nó có thể chứa giá trị chưa biết cho đến lúc apply, và có thể trở nên lỗi thời khi state hoặc hạ tầng thay đổi.

### Ba nhóm kiểm soát

| Nhóm | Câu hỏi cần trả lời | Cơ chế |
|---|---|---|
| Plan review | Thay đổi nào sẽ xảy ra và ảnh hưởng ra sao? | Review thủ công, diff, saved plan, plan JSON |
| Policy checks | Thay đổi có vi phạm tiêu chuẩn tổ chức không? | OPA/Conftest, Sentinel, rule tùy chỉnh, policy trong CI |
| Destroy protection | Có thể ngăn hoặc yêu cầu phê duyệt trước khi xóa tài nguyên quan trọng không? | lifecycle, deletion protection, IAM, approval, backup và retention |

Mỗi lớp giải quyết một loại rủi ro. Policy có thể chặn một cấu hình public, nhưng không thay thế việc xác nhận rằng người phê duyệt hiểu một database sắp bị thay thế.

## 2. Đọc Terraform plan đúng cách

Tạo saved plan:

~~~bash
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan -out=tfplan
~~~

Đọc plan đã lưu:

~~~bash
terraform show -no-color tfplan
~~~

Một plan thường thể hiện các hành động:

| Ký hiệu | Ý nghĩa | Cần chú ý |
|---|---|---|
| `+` | Tạo tài nguyên | Chi phí mới, IAM mới, endpoint mới, quota |
| `~` | Cập nhật tại chỗ | Có thể gây gián đoạn, thay đổi bảo mật hoặc dữ liệu |
| `-` | Xóa tài nguyên | Ảnh hưởng dịch vụ, dữ liệu, phụ thuộc |
| `-/+` | Xóa rồi tạo lại (replace) | Có thể gây downtime hoặc mất dữ liệu |
| `+/-` | Tạo mới trước rồi xóa cũ | Cần capacity, tên tài nguyên và khả năng chuyển traffic |
| `<=` | Đọc data source | Giá trị đọc từ hạ tầng hoặc nguồn bên ngoài |

Một số thay đổi trông nhỏ trong HCL nhưng có thể dẫn đến replace. Ví dụ, thay đổi thuộc tính bất biến của một VM hoặc Cloud SQL instance có thể buộc provider xóa tài nguyên cũ và tạo tài nguyên mới. Reviewer cần tìm phần ghi rõ thuộc tính nào buộc replace, thay vì chỉ nhìn tên resource.

### Các câu hỏi khi review

Với mỗi resource trong plan, hãy kiểm tra:

- Địa chỉ Terraform và module chứa resource có đúng không?
- Project, region, zone, network, subnet và environment có đúng không?
- Resource sẽ được tạo, cập nhật, thay thế hay xóa?
- Có thuộc tính nào đổi ngoài dự kiến không?
- Có IAM binding mới hoặc quyền rộng hơn không?
- Có mở public IP, public bucket, firewall ingress hoặc endpoint ngoài ý muốn không?
- Có thay đổi encryption, CMEK, retention, backup hoặc logging không?
- Có thay đổi ảnh hưởng quota, chi phí, autoscaling hoặc SLA không?
- Có tài nguyên phụ thuộc nào bị xóa theo dây chuyền không?
- Giá trị nào vẫn là unknown và cần kiểm chứng sau apply?

### Phân biệt update và replace

Một thay đổi update tại chỗ vẫn có thể gây gián đoạn. Ví dụ, thay đổi cấu hình database, firewall hoặc load balancer có thể làm mất kết nối tạm thời. Replace thường có rủi ro lớn hơn vì Terraform cần tạo một vòng đời resource mới.

Với các resource stateful, cần xác định dữ liệu nằm ở đâu. Thay thế VM không nhất thiết làm mất dữ liệu nếu persistent disk được quản lý riêng và giữ nguyên, nhưng xóa Cloud SQL instance hoặc bucket có thể làm mất dữ liệu nếu không có backup, versioning hoặc retention phù hợp.

## 3. Tạo plan có thể review và apply nhất quán

Trong CI/CD, nên tạo saved plan và giữ đúng artifact đó qua các bước review và apply:

~~~bash
terraform plan -out=tfplan
terraform show -no-color tfplan
terraform show -json tfplan > tfplan.json
~~~

Sau khi policy và approval thành công, apply saved plan:

~~~bash
terraform apply tfplan
~~~

Cách này giúp apply đúng kế hoạch đã review. Nếu chạy `terraform apply` không kèm plan file, Terraform sẽ tạo một plan mới và các thay đổi có thể khác với những gì reviewer đã phê duyệt.

Saved plan gắn với state và điều kiện tại thời điểm tạo. Nếu state bị thay đổi, lock không còn phù hợp hoặc hạ tầng drift khiến plan không còn áp dụng được, Terraform có thể từ chối apply. Khi đó, hãy tạo plan mới và review lại; không tìm cách ép áp dụng một plan đã lỗi thời.

### Exit code của plan trong CI

Có thể dùng `-detailed-exitcode` để phân biệt ba trạng thái:

~~~bash
terraform plan -detailed-exitcode -out=tfplan
~~~

- Exit code `0`: không có thay đổi.
- Exit code `1`: lỗi khi tạo plan.
- Exit code `2`: plan có thay đổi.

Pipeline phải xử lý exit code 2 như một trạng thái cần review, không coi đó là lỗi chạy lệnh. Exit code 1 mới là lỗi tạo plan.

### Không áp dụng plan chưa được kiểm tra

Không dùng `-auto-approve` như cách bỏ qua review trong production. Với môi trường thử nghiệm có thể tự động hóa, policy và guardrail vẫn cần chạy trước apply. Approval phải gắn với commit, workspace, project, artifact plan và người phê duyệt để có thể truy vết.

## 4. Xuất JSON plan và xử lý dữ liệu nhạy cảm

Terraform có thể chuyển saved plan sang JSON:

~~~bash
terraform show -json tfplan > tfplan.json
~~~

JSON plan phù hợp cho công cụ policy as code vì nó chứa cấu trúc machine-readable về resource changes, actions, values, dependencies và metadata.

Một số trường thường được dùng:

| Trường | Nội dung |
|---|---|
| `resource_changes` | Các thay đổi dự kiến của resource |
| `address` | Địa chỉ resource trong cấu hình Terraform |
| `type` | Loại resource, ví dụ `google_compute_instance` |
| `change.actions` | Danh sách hành động như create, update, delete |
| `change.before` | Giá trị trước thay đổi |
| `change.after` | Giá trị dự kiến sau thay đổi |
| `change.after_unknown` | Thuộc tính chưa biết tại thời điểm plan |
| `change.before_sensitive` và `after_sensitive` | Metadata đánh dấu giá trị nhạy cảm |

### Bảo vệ plan artifact

Plan JSON và saved plan có thể chứa dữ liệu nhạy cảm. Giao diện terminal thường che một số giá trị được đánh dấu sensitive, nhưng JSON hoặc binary plan có thể vẫn chứa giá trị thực. Do đó:

- Không upload plan artifact lên kho công khai hoặc issue tracker không được bảo vệ.
- Hạn chế quyền đọc artifact cho người và service account cần review.
- Đặt thời hạn lưu giữ phù hợp với chính sách tổ chức.
- Không in toàn bộ JSON vào log CI.
- Không đính kèm plan chứa secret vào email hoặc chat thông thường.
- Xóa artifact tạm sau thời hạn cần thiết theo chính sách lưu trữ.
- Dùng dữ liệu giả lập trong môi trường lab để minh họa policy.

Không coi thuộc tính `sensitive = true` là mã hóa dữ liệu. Nó chủ yếu ảnh hưởng cách Terraform hiển thị giá trị; việc bảo vệ state, plan và artifact vẫn là trách nhiệm của pipeline.

### Đọc JSON có chọn lọc

Có thể dùng `jq` để xem các thay đổi theo loại resource và hành động:

~~~bash
jq -r '
  .resource_changes[]
  | [.address, .type, (.change.actions | join(","))]
  | @tsv
' tfplan.json
~~~

Lệnh trên chỉ in địa chỉ, loại resource và action. Khi cần xem chi tiết thuộc tính, hãy tạo báo cáo đã lọc và làm sạch dữ liệu nhạy cảm trước khi chia sẻ.

## 5. Review rủi ro theo tài nguyên GCP

Reviewer nên tập trung vào tác động của thay đổi đối với dịch vụ, bảo mật, dữ liệu và chi phí.

| Resource GCP | Nội dung cần kiểm tra trong plan |
|---|---|
| Compute Engine | Machine type, boot disk, attached disk, service account, network interface, external IP, deletion protection |
| GKE | Cluster location, node pool, version, release channel, workload identity, private cluster, node upgrade |
| Cloud SQL | Database version, HA, backup, PITR, authorized networks, private IP, deletion protection |
| Cloud Storage | Public access prevention, uniform bucket-level access, versioning, retention, force_destroy, encryption |
| IAM | Principal, role, project/folder scope, custom role, service account key, quyền impersonation |
| VPC/Firewall | CIDR, ingress/egress, source ranges, target tags/service accounts, route |
| KMS | Key ring, key version, rotation, protection level, quyền encrypt/decrypt |
| Cloud Run | Revision, traffic split, ingress, service identity, secret reference, min/max instances |

### Thay đổi IAM

Một role được thêm có thể mở quyền trên toàn project thay vì một resource cụ thể. Kiểm tra principal là user, group hay service account; role là predefined hay custom; binding ở cấp organization, folder hay project. Đặc biệt xem các role rộng như Owner, Editor hoặc quyền quản trị IAM.

### Thay đổi mạng

Firewall ingress từ `0.0.0.0/0`, mở SSH/RDP, thay đổi route hoặc tạo external IP cần có lý do rõ ràng. Đối chiếu source range, target và môi trường. Một rule có vẻ chỉ thêm cho một workload nhưng selector hoặc target tag quá rộng có thể ảnh hưởng nhiều VM.

### Thay đổi lưu trữ và dữ liệu

Khi plan thay đổi bucket, database, disk hoặc key, reviewer cần xác minh:

- Có resource bị replace hoặc destroy không?
- Backup/PITR hoặc snapshot mới nhất có tồn tại và đã thử restore chưa?
- Có object versioning hoặc retention cần thiết không?
- Encryption key còn khả năng giải mã dữ liệu cũ không?
- Có consumer, service hoặc pipeline phụ thuộc vào tên và endpoint cũ không?
- Có cần migration hoặc chuyển traffic theo từng giai đoạn không?

## 6. Policy as code cho Terraform plan

Policy as code chuyển các quy tắc quản trị thành kiểm tra tự động. Thay vì phụ thuộc hoàn toàn vào reviewer, pipeline có thể chặn plan vi phạm tiêu chuẩn trước khi đến bước apply.

Có thể dùng:

- **Open Policy Agent (OPA) và Conftest:** kiểm tra JSON plan bằng các policy viết bằng Rego.
- **Terraform Sentinel:** áp dụng policy trong các workflow Terraform Cloud/Enterprise hỗ trợ Sentinel.
- **Checkov hoặc công cụ phân tích IaC:** phát hiện cấu hình rủi ro trong HCL hoặc plan theo framework hỗ trợ.
- **Custom CI checks:** kiểm tra project, region, action, IAM, public access và resource quan trọng theo tiêu chuẩn nội bộ.

Không phải công cụ nào cũng đánh giá cùng một đầu vào. Hãy xác định rõ công cụ đang kiểm tra HCL, JSON plan hay trạng thái runtime. Ví dụ, Google Cloud Organization Policy áp dụng ràng buộc ở cấp tổ chức/folder/project đối với các tài nguyên được hỗ trợ; nó không phải một trình review Terraform plan tổng quát.

### Các nhóm policy thường cần

| Nhóm policy | Ví dụ |
|---|---|
| Location | Chỉ cho phép region được tổ chức phê duyệt |
| Network | Không tạo firewall ingress mở rộng ngoài ngoại lệ |
| Storage | Bucket phải bật public access prevention và uniform bucket-level access |
| Encryption | Resource dữ liệu nhạy cảm phải dùng CMEK theo yêu cầu |
| IAM | Không cấp role quá rộng hoặc binding ngoài phạm vi |
| Identity | Không tạo service account key dài hạn nếu không có ngoại lệ |
| Reliability | Cloud SQL quan trọng phải có backup/HA theo tier |
| Cost | Chặn machine type hoặc số lượng resource vượt giới hạn |
| Destruction | Cảnh báo hoặc chặn delete/replace đối với resource được bảo vệ |

Policy cần phân biệt giữa tạo mới, update và destroy. Ví dụ, một bucket đã có public access prevention có thể bị policy chặn nếu plan tắt thuộc tính này. Một resource bị xóa sẽ có `change.after = null`; policy cần xử lý trường hợp này thay vì cố đọc thuộc tính sau thay đổi.

### Ví dụ policy cho Cloud Storage

Ví dụ Rego minh họa kiểm tra bucket được tạo hoặc cập nhật phải bật public access prevention. Policy chỉ kiểm tra các resource có trạng thái sau thay đổi:

~~~rego
package terraform.plan

deny contains msg if {
  some rc in input.resource_changes
  rc.type == "google_storage_bucket"
  rc.change.after != null
  rc.change.after.public_access_prevention != "enforced"

  msg := sprintf(
    "%s must enforce public access prevention",
    [rc.address]
  )
}
~~~

Chạy Conftest trên plan JSON:

~~~bash
conftest test tfplan.json --policy policy/
~~~

Nếu policy phát hiện vi phạm, pipeline phải dừng trước approval/apply. Trong thực tế, cần kiểm tra schema JSON của phiên bản Terraform và provider đang sử dụng, viết test cho cả trường hợp create/update/destroy và xác nhận policy không bỏ sót giá trị unknown.

### Ví dụ policy chặn xóa resource quan trọng

Có thể duy trì danh sách resource address được bảo vệ trong policy data hoặc file cấu hình được review. Quy tắc minh họa:

~~~rego
package terraform.plan

protected_addresses := {
  "google_sql_database_instance.orders",
  "google_storage_bucket.audit_archive",
}

deny contains msg if {
  some rc in input.resource_changes
  rc.address in protected_addresses
  rc.change.actions[_] == "delete"

  msg := sprintf(
    "destruction of protected resource %s requires an approved exception",
    [rc.address]
  )
}
~~~

Đây là ví dụ tối giản. Trong pipeline thực tế, exception cần có người phê duyệt, mã change request, lý do, thời hạn và phạm vi chính xác. Không nên cho phép exception dạng wildcard rộng như toàn bộ module hoặc project.

### Xử lý giá trị unknown

Một số thuộc tính chỉ có giá trị sau khi apply, ví dụ IP được cấp động hoặc ID do API tạo. Policy không được mặc định coi unknown là an toàn. Với thuộc tính bảo mật quan trọng, có thể yêu cầu khai báo tường minh trong cấu hình hoặc chặn plan cho đến khi giá trị được xác định. Ghi rõ cách xử lý unknown để tránh policy false positive hoặc false negative.

## 7. Tích hợp policy checks vào CI/CD

Một pipeline có thể thực hiện các bước:

~~~bash
terraform init -input=false
terraform fmt -check -recursive
terraform validate
terraform plan -input=false -out=tfplan
terraform show -json tfplan > tfplan.json
conftest test tfplan.json --policy policy/
terraform show -no-color tfplan
~~~

Sau đó, hệ thống tạo approval gate. Khi reviewer chấp thuận, pipeline apply đúng saved plan:

~~~bash
terraform apply -input=false tfplan
~~~

Cần bảo đảm các bước dùng cùng commit, cùng workspace và cùng artifact. Không cho pipeline tạo lại plan sau khi approval nhưng vẫn giữ trạng thái approved cũ.

### Tách quyền giữa các giai đoạn

| Danh tính | Quyền phù hợp |
|---|---|
| Pull request validation | Đọc module/provider và tạo plan theo quyền giới hạn |
| Plan reviewer | Đọc plan đã làm sạch và policy result |
| Apply service account | Quyền thay đổi đúng project/resource cần triển khai |
| Destroy approver | Quyền phê duyệt thao tác hủy theo quy trình riêng |
| Break-glass operator | Quyền khẩn cấp được kiểm soát, ghi log và rà soát sau sử dụng |

Không dùng một service account có Owner trên toàn organization cho mọi pipeline. Tách danh tính theo môi trường và module, cấp quyền tối thiểu, ưu tiên Workload Identity Federation cho CI/CD thay cho khóa service account dài hạn.

### Approval phải gắn với artifact

Approval record nên lưu:

- Commit SHA và pull request.
- Terraform workspace hoặc stack.
- Project, folder và region bị tác động.
- Hash hoặc định danh của saved plan.
- Kết quả policy checks.
- Danh sách resource create/update/delete/replace.
- Người review, người phê duyệt và thời điểm.
- Exception ID nếu có.
- Thời điểm apply và kết quả.

Khi plan thay đổi, approval cũ không còn áp dụng. Cần tạo plan mới và review lại.

## 8. Bảo vệ Terraform state và backend GCS

Terraform state ánh xạ resource trong cấu hình với tài nguyên thật. State có thể chứa thuộc tính nhạy cảm, ID, endpoint và giá trị bí mật. Nếu state bị sửa hoặc mất, Terraform có thể tính toán sai thay đổi và tạo ra hành động không mong muốn.

Với GCP, backend GCS là lựa chọn phổ biến:

~~~hcl
terraform {
  backend "gcs" {
    bucket = "ORG_TERRAFORM_STATE"
    prefix = "gcp/production/network"
  }
}
~~~

Bucket backend nên có:

- IAM giới hạn người và service account đọc/ghi state.
- Uniform bucket-level access và public access prevention.
- Versioning để hỗ trợ khôi phục object state khi có sự cố.
- Retention và backup phù hợp với chính sách tổ chức.
- Logging và giám sát hoạt động truy cập.
- Mã hóa theo yêu cầu, có thể dùng CMEK khi cần kiểm soát khóa.

GCS backend hỗ trợ state locking để hạn chế nhiều tiến trình cùng sửa state. Không tắt locking để xử lý xung đột một cách vội vàng. Nếu pipeline bị dừng và lock còn tồn tại, xác minh không có process apply đang chạy trước khi dùng thao tác force-unlock; ghi lại lock ID và lý do.

### Không chỉnh state bằng tay để “sửa plan”

Khi phát hiện state drift hoặc mapping sai, dùng quy trình Terraform phù hợp như import, moved block, state mv hoặc state rm theo hướng dẫn và review kỹ. Các lệnh state có thể thay đổi cách Terraform quản lý resource mà không thay đổi trực tiếp tài nguyên GCP; sai thao tác vẫn có thể dẫn đến destroy/create ở lần plan tiếp theo.

Không đưa state file, backup state hoặc plan JSON lên repository. Thêm chúng vào quy tắc loại trừ phù hợp và bảo vệ artifact trong CI.

## 9. Cơ chế ngăn xóa trong Terraform và GCP

Không có một nút bảo vệ duy nhất cho mọi loại tài nguyên. Cần kết hợp lifecycle của Terraform với thuộc tính bảo vệ ở phía GCP và chính sách vận hành.

### Terraform lifecycle prevent_destroy

Ví dụ giữ Cloud SQL instance quan trọng:

~~~hcl
resource "google_sql_database_instance" "orders" {
  name             = "orders-prod"
  region           = "asia-southeast1"
  database_version = "POSTGRES_15"

  deletion_protection = true

  settings {
    tier = "db-custom-2-7680"
  }

  lifecycle {
    prevent_destroy = true
  }
}
~~~

`prevent_destroy = true` yêu cầu Terraform từ chối plan có thao tác destroy resource trong khi resource block vẫn còn trong cấu hình. Đây là guardrail hữu ích cho resource stateful hoặc trọng yếu.

Giới hạn cần hiểu:

- Nó không ngăn người có quyền gọi API xóa trực tiếp ngoài Terraform.
- Nó không phải backup và không bảo vệ dữ liệu đã bị xóa ngoài quy trình.
- Nếu xóa hẳn resource block khỏi cấu hình, lifecycle rule cũng biến mất; Terraform có thể đề xuất xóa resource.
- Nó không thay thế quyền IAM và cơ chế deletion protection của dịch vụ.

Vì vậy, policy gate cần phát hiện việc resource quan trọng biến mất khỏi cấu hình hoặc bị đánh dấu destroy, kể cả khi lifecycle block không còn xuất hiện.

### Deletion protection của tài nguyên GCP

Một số resource có thuộc tính bảo vệ xóa riêng ở cấp API/provider. Ví dụ:

~~~hcl
resource "google_compute_instance" "bastion" {
  name         = "admin-bastion"
  machine_type = "e2-small"
  zone         = "asia-southeast1-a"

  deletion_protection = true

  boot_disk {
    initialize_params {
      image = "projects/debian-cloud/global/images/family/debian-12"
    }
  }

  network_interface {
    network = "default"
  }
}
~~~

Với Cloud SQL, thuộc tính `deletion_protection` có thể ngăn xóa instance qua API khi được bật và được provider version hỗ trợ. Với Compute Engine, `deletion_protection` bảo vệ instance khỏi thao tác delete. Hãy kiểm tra schema của provider version đang khóa trong dự án trước khi dùng thuộc tính, vì tên và hành vi có thể khác giữa resource/provider version.

Terraform `prevent_destroy` và GCP deletion protection bổ sung cho nhau: một lớp bảo vệ trong plan, một lớp bảo vệ tại resource API. Cả hai cần được kiểm tra trong plan và sau apply.

### Cloud Storage và force_destroy

Với bucket chứa log hoặc dữ liệu nghiệp vụ, không bật `force_destroy` một cách mặc định:

~~~hcl
resource "google_storage_bucket" "audit_archive" {
  name                        = "org-audit-archive"
  location                    = "ASIA"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }
}
~~~

`force_destroy = false` khiến việc xóa bucket không tự động xóa toàn bộ object bên trong. Nó không phải là cơ chế chống xóa bucket tuyệt đối. `prevent_destroy` bảo vệ plan khi resource block còn tồn tại; retention policy và Bucket Lock bảo vệ object theo thời hạn lưu giữ đã cấu hình.

Bucket Lock có thể làm retention policy không thể đảo ngược sau khi khóa. Chỉ khóa khi thời hạn, yêu cầu tuân thủ và quy trình xóa đã được phê duyệt. Không dùng Bucket Lock như một thao tác thử nghiệm trên bucket production.

## 10. Quy trình destroy an toàn

Destroy có thể cần thiết khi kết thúc môi trường thử nghiệm, thay thế một stack hoặc loại bỏ tài nguyên đã ngừng sử dụng. Với resource quan trọng, destroy cần một quy trình riêng thay vì chạy như một bước cleanup tự động.

### Trước khi tạo destroy plan

1. Xác nhận đúng project, workspace, backend và environment.
2. Kiểm tra danh sách resource nằm trong state.
3. Xác định dữ liệu, dependency và owner nghiệp vụ.
4. Kiểm tra backup, snapshot, PITR, export và retention.
5. Kiểm tra resource protection, policy exception và quyền IAM.
6. Xác định downtime, ảnh hưởng người dùng và thứ tự tháo gỡ dependency.
7. Ghi change request và người phê duyệt.

### Tạo destroy plan riêng

~~~bash
terraform plan -destroy -out=destroy.tfplan
terraform show -no-color destroy.tfplan
terraform show -json destroy.tfplan > destroy-plan.json
~~~

Review tất cả resource có action delete hoặc replace. Dùng policy gate riêng để chặn các địa chỉ resource được bảo vệ hoặc yêu cầu exception có thời hạn. Đặc biệt kiểm tra database, bucket, KMS key, disk, backup, network và IAM.

Chỉ sau khi được phê duyệt mới áp dụng đúng plan:

~~~bash
terraform apply destroy.tfplan
~~~

Không dùng `terraform destroy -auto-approve` trong pipeline production. Không coi việc nhập `yes` là một quy trình approval đầy đủ nếu không có record, reviewer và scope rõ ràng.

### Bảo vệ khỏi thao tác xóa nhầm

Các guardrail nên phối hợp:

- `prevent_destroy` trên resource trọng yếu.
- Deletion protection của GCP resource nếu có.
- Policy kiểm tra resource action delete/replace.
- IAM hạn chế quyền xóa cho apply identity.
- Approval độc lập cho destroy.
- Backup/restore được thử nghiệm.
- Retention và Bucket Lock theo yêu cầu dữ liệu.
- Audit log cho thay đổi và hành động xóa.
- Kiểm tra project/workspace trước khi chạy.

Một số dịch vụ có cơ chế xóa chậm hoặc lịch chờ, ví dụ key version của Cloud KMS có thể có thời gian chờ trước khi bị hủy. Cần hiểu rõ trạng thái disable/destroy và khả năng phục hồi của từng dịch vụ trước khi đưa vào quy trình teardown.

## 11. Xử lý drift, import và ngoại lệ policy

Plan có thể phát hiện khác biệt giữa state/configuration và hạ tầng thật. Terraform thường refresh trạng thái từ provider trước khi lập plan. Nếu ai đó thay đổi IAM, firewall hoặc instance trực tiếp trên GCP, plan có thể đề xuất sửa lại để khớp cấu hình.

### Khi plan phát hiện drift

- Xác minh thay đổi ngoài Terraform có hợp lệ hay là sự cố.
- Xác định owner và thời điểm thay đổi từ Cloud Audit Logs.
- Cập nhật mã Terraform nếu thay đổi là chủ đích.
- Nếu tài nguyên chưa được quản lý, đánh giá import thay vì tạo resource trùng.
- Tạo plan mới và review tác động sau khi điều chỉnh.

Không dùng `-refresh=false` để che drift trong một lần triển khai thông thường. Tùy chọn này bỏ qua refresh và có thể làm plan không phản ánh trạng thái thật. Chỉ dùng trong trường hợp chẩn đoán đặc biệt đã hiểu rõ giới hạn.

### Quản lý ngoại lệ policy

Một số hệ thống cũ có thể cần ngoại lệ tạm thời. Mỗi exception nên chứa:

- Policy ID và rule bị vi phạm.
- Resource address và project bị ảnh hưởng.
- Lý do nghiệp vụ và rủi ro chấp nhận.
- Biện pháp bù trừ.
- Người yêu cầu và người phê duyệt.
- Thời hạn hết hiệu lực.
- Link đến ticket hoặc change request.

Exception phải hẹp theo resource và thời gian. Không sửa policy chung để một workload duy nhất có thể triển khai cấu hình rủi ro.

## 12. Tình huống thực hành: review thay đổi Cloud SQL và bucket production

Một nhóm cần cập nhật hạ tầng cho hệ thống orders. Plan dự kiến:

- Tạo một service account mới cho ứng dụng.
- Cập nhật IAM binding cho Cloud SQL client.
- Thay đổi tier Cloud SQL.
- Cập nhật bucket log.
- Có một thay đổi bất ngờ đề xuất xóa bucket archive cũ.

### Bước 1 — Tạo và lưu plan

~~~bash
terraform plan -out=tfplan
terraform show -no-color tfplan
terraform show -json tfplan > tfplan.json
~~~

### Bước 2 — Review theo resource

| Resource | Hành động dự kiến | Câu hỏi review |
|---|---|---|
| Service account | Create | Có đúng project và mục đích? |
| IAM binding | Update | Có cấp quyền đúng principal và scope? |
| Cloud SQL | Update hoặc replace | Tier đổi tại chỗ hay buộc replace? Có downtime? |
| Log bucket | Update | Có giữ retention, versioning và public access prevention? |
| Archive bucket | Delete | Ai yêu cầu? Dữ liệu đã được di chuyển và xác minh chưa? |

### Bước 3 — Chạy policy checks

Chạy Conftest trên JSON plan. Policy cần:

- Chặn bucket không bật public access prevention.
- Chặn IAM role quá rộng nếu không có exception.
- Chặn destroy bucket archive được bảo vệ.
- Yêu cầu Cloud SQL production có deletion protection và backup theo chuẩn.

Nếu policy chặn archive bucket, pipeline dừng. Reviewer kiểm tra plan, ticket và dữ liệu trước khi quyết định exception hoặc sửa cấu hình.

### Bước 4 — Phê duyệt và apply

Sau khi loại bỏ thay đổi xóa bucket ngoài dự kiến hoặc hoàn thành exception hợp lệ, tạo plan mới. Không sử dụng lại approval cũ. Reviewer xác nhận commit, project, saved plan và policy result rồi mới cho phép apply đúng file plan đã kiểm tra.

### Bước 5 — Kiểm chứng sau apply

- Xác nhận service account và IAM binding đúng scope.
- Kiểm tra Cloud SQL hoạt động, kết nối ứng dụng và backup.
- Xác nhận bucket giữ retention, versioning và public access prevention.
- Kiểm tra Cloud Audit Logs và deployment record.
- Lưu plan, policy report, approval và kết quả apply theo chính sách.

## 13. Checklist review và bảo vệ thao tác hủy

### Trước khi review plan

- [ ] Đúng commit, workspace, backend, project và environment.
- [ ] `terraform fmt` và `terraform validate` thành công.
- [ ] Saved plan được tạo từ state hiện tại.
- [ ] Plan artifact được lưu ở nơi có kiểm soát truy cập.
- [ ] Reviewer có thể đọc diff và policy report.

### Trong khi review

- [ ] Đã phân loại create, update, delete và replace.
- [ ] Đã kiểm tra IAM, firewall, public access và encryption.
- [ ] Đã xem resource stateful, backup, retention và dependency.
- [ ] Đã xử lý thuộc tính unknown.
- [ ] Đã xác minh các thay đổi ngoài dự kiến và drift.
- [ ] Policy checks đã chạy trên đúng plan JSON.
- [ ] Exception có owner, lý do, scope và thời hạn.

### Trước apply

- [ ] Approval gắn với đúng commit và saved plan.
- [ ] Apply identity có quyền tối thiểu.
- [ ] Plan chưa bị thay đổi hoặc lỗi thời.
- [ ] Có kế hoạch rollback hoặc phục hồi phù hợp.
- [ ] Người vận hành biết cách dừng khi có tác động bất thường.

### Trước destroy

- [ ] Xác nhận project, workspace và resource address.
- [ ] Đã kiểm tra mọi action delete/replace.
- [ ] Đã xác minh backup và khả năng restore.
- [ ] Đã kiểm tra `prevent_destroy`, deletion protection và retention.
- [ ] Đã chạy policy gate riêng cho destroy.
- [ ] Có approval độc lập và change request.
- [ ] Đã tạo destroy plan và review saved plan.
- [ ] Đã xác định người giám sát và cách phục hồi.

Plan review, policy checks và destroy protection tạo thành một quy trình kiểm soát thống nhất cho Terraform trên GCP. Khi nhóm hiểu rõ từng action, kiểm tra chính sách trên saved plan, bảo vệ state và yêu cầu phê duyệt riêng cho thao tác hủy, thay đổi hạ tầng trở nên dễ truy vết hơn và nguy cơ xóa nhầm tài nguyên hoặc dữ liệu giảm đáng kể.

