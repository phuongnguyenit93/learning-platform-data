# Khai báo project, API và IAM bằng Terraform

Khi một tổ chức tạo nhiều môi trường Google Cloud, việc tạo project, bật API và cấp quyền thủ công dễ dẫn đến cấu hình không đồng nhất. Một project có thể thiếu API cần thiết, project khác có quá nhiều quyền, hoặc nhóm vận hành không nhớ ai đã thay đổi IAM. Infrastructure as Code (IaC) giải quyết vấn đề này bằng cách mô tả hạ tầng trong tệp cấu hình có thể quản lý bằng Git, xem trước thay đổi và triển khai lặp lại.

Terraform là công cụ IaC khai báo. Với Google Cloud, provider hashicorp/google ánh xạ tài nguyên HCL thành thao tác với Google Cloud APIs. Bạn có thể mô tả project, bật dịch vụ bằng Service Usage API, tạo service account và cấp vai trò IAM. Terraform theo dõi tài nguyên đã quản lý trong state để biết cấu hình thực tế cần thay đổi thế nào khi mã nguồn cập nhật.

Trong module CLOUD_PROVIDERS_GCP, project là ranh giới quản trị, billing và IAM; API xác định những dịch vụ được phép sử dụng; IAM xác định principal nào được làm gì trên tài nguyên. Quản lý cả ba bằng Terraform giúp chuẩn hóa nền tảng cho Compute Engine, GKE, Cloud Run, Cloud Storage, BigQuery và Cloud Monitoring.

Sau bài học này, bạn có thể:

- Giải thích provider, resource, variable, dependency graph và state của Terraform.
- Chuẩn bị quyền bootstrap để tạo project trong organization hoặc folder.
- Khai báo project Google Cloud và liên kết billing account.
- Bật API bằng google_project_service và quản lý vòng đời API.
- Tạo service account và cấp quyền IAM theo nguyên tắc least privilege.
- Phân biệt các resource IAM dạng member, binding và policy.
- Quản lý state từ xa, xem plan, áp dụng thay đổi và nhập tài nguyên đã tồn tại.

## 1. Terraform quản lý Google Cloud như thế nào?

### Cấu trúc khai báo

Terraform sử dụng ngôn ngữ HCL (HashiCorp Configuration Language). Một cấu hình thường có:

- **Provider:** plugin kết nối Terraform với nền tảng, ví dụ hashicorp/google.
- **Resource:** tài nguyên cần tạo hoặc quản lý, ví dụ google_project và google_project_service.
- **Data source:** đọc thông tin của tài nguyên đã tồn tại mà không tạo tài nguyên đó.
- **Variable và local:** tham số đầu vào và giá trị dùng chung trong cấu hình.
- **Output:** giá trị cần hiển thị hoặc chuyển cho module khác.
- **State:** ánh xạ giữa địa chỉ resource trong cấu hình và tài nguyên thực tế trên Google Cloud.

Terraform đọc các tệp .tf, xây dựng dependency graph và so sánh cấu hình mong muốn với state cùng dữ liệu đọc từ provider. Từ đó, terraform plan hiển thị các hành động dự kiến trước khi terraform apply thực hiện.

~~~mermaid
flowchart TD
    A[HCL trong Git] --> B[Terraform init]
    B --> C[Provider Google]
    C --> D[Terraform plan]
    E[Terraform state] --> D
    F[Google Cloud hiện tại] --> D
    D --> G[Review plan]
    G --> H[Terraform apply]
    H --> I[Google Cloud APIs]
    H --> E
~~~

### Provider và resource

Provider cấu hình cách Terraform xác thực và gọi API. Resource mô tả vòng đời của một loại tài nguyên. Ví dụ:

| Terraform resource | Tài nguyên Google Cloud |
|---|---|
| google_project | Google Cloud project |
| google_project_service | Một API/service được bật trong project |
| google_service_account | Service account |
| google_project_iam_member | Một principal được thêm vào một role ở cấp project |
| google_project_iam_binding | Danh sách thành viên có thẩm quyền cho một role ở cấp project |
| google_project_iam_policy | IAM policy đầy đủ của project |

Địa chỉ Terraform như google_project.application là định danh trong cấu hình và state. Nó không phải project ID trên Google Cloud. Project ID là giá trị bất biến và phải duy nhất toàn cầu; project display name có thể thay đổi.

### Dependency graph

Terraform tự nhận biết phụ thuộc khi một resource tham chiếu thuộc tính của resource khác. Ví dụ, nếu google_project_service lấy project từ google_project.application.project_id, Terraform sẽ tạo project trước rồi mới bật API.

Khi phụ thuộc không thể hiện qua tham chiếu, có thể dùng depends_on. Hạn chế dùng depends_on rộng nếu một tham chiếu trực tiếp đã thể hiện được quan hệ, vì phụ thuộc tường minh quá nhiều làm graph khó hiểu và có thể trì hoãn các thao tác không cần thiết.

## 2. Chuẩn bị quyền và project bootstrap

Tạo project mới là thao tác cấp tổ chức. Principal chạy Terraform cần quyền ở đúng phạm vi trước khi cấu hình có thể tạo tài nguyên.

### Các quyền thường cần

| Công việc | Quyền hoặc vai trò thường dùng | Phạm vi |
|---|---|---|
| Tạo project trong organization hoặc folder | roles/resourcemanager.projectCreator | Organization hoặc folder nơi tạo project |
| Liên kết project với billing account | roles/billing.user và quyền liên kết billing tương ứng | Billing account và project |
| Bật API | roles/serviceusage.serviceUsageAdmin | Project đích |
| Tạo service account | roles/iam.serviceAccountAdmin | Project đích |
| Thay đổi IAM policy của project | roles/resourcemanager.projectIamAdmin | Project đích |
| Impersonate Terraform runner service account | roles/iam.serviceAccountTokenCreator | Service account được impersonate |

Vai trò thực tế còn phụ thuộc organization policy, cách tạo project, billing và resource được quản lý. Hãy yêu cầu quản trị viên cấp đúng quyền cần thiết theo quy trình của tổ chức. Không dùng Owner ở cấp organization chỉ để làm cho Terraform chạy được.

### Bootstrap project là gì?

Terraform cần một danh tính có thể gọi Google Cloud APIs trước khi project đích được tạo. Project đang lưu trữ các API và tài nguyên phục vụ quá trình triển khai thường được gọi là bootstrap hoặc administration project. Project này có thể chứa:

- Các API cần để quản lý organization, project, billing và IAM.
- Service account chuyên chạy Terraform.
- Cấu hình Workload Identity Federation hoặc cơ chế impersonation.
- State bucket và các tài nguyên dùng chung cho quy trình IaC.

Không nên để state bucket phụ thuộc vào chính state đang lưu trong bucket đó. Hãy tạo và quản lý backend bucket qua một cấu hình bootstrap riêng hoặc quy trình nền tảng đã được tổ chức phê duyệt.

### Xác thực an toàn

Trên máy phát triển, có thể dùng Application Default Credentials (ADC) sau khi đăng nhập bằng tài khoản được cấp quyền. Trong CI/CD, ưu tiên Workload Identity Federation hoặc impersonation service account. Tránh tạo và lưu service account key JSON lâu dài trong repository, biến môi trường không được bảo vệ hoặc pipeline log.

## 3. Khởi tạo cấu hình Terraform

Tạo một thư mục làm việc cho project, ví dụ:

~~~text
gcp-project/
├── versions.tf
├── provider.tf
├── variables.tf
├── main.tf
├── outputs.tf
└── terraform.tfvars
~~~

### Khai báo Terraform và provider

Trong versions.tf:

~~~hcl
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }
}
~~~

Terraform sẽ chọn phiên bản provider phù hợp khi khởi tạo. Hãy kiểm tra và commit tệp .terraform.lock.hcl để các lần chạy sau dùng cùng phiên bản provider đã được xác minh. Khi nâng phiên bản, thực hiện trong một thay đổi có review và kiểm tra plan.

Trong provider.tf:

~~~hcl
provider "google" {
  project = var.bootstrap_project_id
  region  = var.region

  # Tùy chọn: chạy Terraform bằng service account chuyên dụng.
  impersonate_service_account = var.terraform_runner_service_account
}
~~~

project ở provider là project mặc định cho các resource không chỉ định project riêng. Trong ví dụ tiếp theo, resource project và API sẽ chỉ rõ project đích. Service account dùng để impersonate cần được cấp quyền phù hợp cho principal đang chạy Terraform.

### Khai báo biến đầu vào

Trong variables.tf:

~~~hcl
variable "bootstrap_project_id" {
  description = "Project dùng để khởi tạo và gọi Google Cloud APIs."
  type        = string
}

variable "terraform_runner_service_account" {
  description = "Email service account Terraform sẽ impersonate."
  type        = string
}

variable "project_id" {
  description = "Project ID duy nhất toàn cầu cho workload."
  type        = string
}

variable "project_name" {
  description = "Tên hiển thị của project."
  type        = string
}

variable "folder_id" {
  description = "ID số của folder chứa project."
  type        = string
}

variable "billing_account" {
  description = "Billing account ID được liên kết với project."
  type        = string
}

variable "region" {
  description = "Region mặc định cho tài nguyên regional."
  type        = string
  default     = "asia-southeast1"
}

variable "operations_group" {
  description = "Email Google Group của nhóm vận hành."
  type        = string
}
~~~

Trong terraform.tfvars, cung cấp giá trị theo môi trường. Ví dụ dưới đây là dữ liệu mẫu, cần thay bằng ID thật trong organization:

~~~hcl
bootstrap_project_id             = "platform-bootstrap-prod"
terraform_runner_service_account = "terraform-runner@platform-bootstrap-prod.iam.gserviceaccount.com"
project_id                        = "customer-api-prod-123"
project_name                      = "Customer API Production"
folder_id                         = "123456789012"
billing_account                   = "000000-111111-222222"
region                            = "asia-southeast1"
operations_group                  = "gcp-operations@example.com"
~~~

Không commit tệp chứa bí mật hoặc dữ liệu nhạy cảm. Các giá trị project ID, folder ID và billing account ID không phải mật khẩu, nhưng vẫn nên tuân theo quy tắc quản lý cấu hình nội bộ. Có thể cung cấp biến qua pipeline hoặc tệp .tfvars được quản lý riêng.

## 4. Khai báo Google Cloud project

Resource google_project tạo project và gắn project vào organization hoặc folder. Ví dụ sau đặt project trong folder và liên kết billing account.

Trong main.tf:

~~~hcl
resource "google_project" "application" {
  project_id      = var.project_id
  name            = var.project_name
  folder_id       = var.folder_id
  billing_account = var.billing_account

  # Không tự tạo default VPC network trong project.
  auto_create_network = false

  lifecycle {
    prevent_destroy = true
  }
}
~~~

folder_id là ID của folder chứa project. Nếu tạo project trực tiếp dưới organization, dùng org_id thay cho folder_id; không khai báo đồng thời cả hai. Nếu không có quyền hoặc không có billing account phù hợp, thao tác tạo hoặc liên kết billing sẽ thất bại.

### Vì sao cần tắt default network?

Khi tạo project, việc tự tạo default VPC network có thể tạo các subnet và firewall rule mặc định ở nhiều region. Trong môi trường production, nhóm thường muốn thiết kế mạng rõ ràng theo kiến trúc và chính sách bảo mật. auto_create_network = false tránh tạo default network; sau đó có thể khai báo VPC và subnet bằng các resource riêng trong bài học về networking.

### Bảo vệ project khỏi xóa nhầm

lifecycle { prevent_destroy = true } khiến Terraform từ chối plan có hành động destroy resource khi block này còn trong cấu hình. Đây là lớp bảo vệ hữu ích cho project production, nhưng không thay thế quy trình review, quyền IAM và chính sách organization. Nếu xóa hẳn resource block khỏi cấu hình, Terraform không còn nhìn thấy lifecycle rule đó; vì vậy phải review kỹ mọi thay đổi liên quan tới project và state.

Project ID không thể đổi sau khi tạo. Nếu cần đổi tên hiển thị, có thể cập nhật name; nếu cần project ID khác, đó là project mới và cần kế hoạch di chuyển tài nguyên.

## 5. Bật Google Cloud APIs bằng Terraform

Google Cloud API phải được bật trong project trước khi workload có thể sử dụng dịch vụ tương ứng. Terraform dùng resource google_project_service để quản lý trạng thái này thông qua Service Usage API.

Thêm vào main.tf:

~~~hcl
locals {
  project_services = toset([
    "serviceusage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "compute.googleapis.com",
    "run.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
  ])
}

resource "google_project_service" "apis" {
  for_each = local.project_services

  project = google_project.application.project_id
  service = each.value

  # Khi bỏ resource khỏi cấu hình, không tự động disable API.
  disable_on_destroy = false
}
~~~

Terraform tạo một instance google_project_service.apis cho mỗi API trong set. project tham chiếu google_project.application.project_id, vì vậy Terraform biết phải tạo project trước khi bật API.

disable_on_destroy = false giữ API đang bật nếu resource bị xóa khỏi cấu hình hoặc state. Điều này giảm nguy cơ vô tình tắt API đang được workload sử dụng. Nếu tổ chức muốn quản lý cả việc disable API, hãy có quy trình riêng, kiểm kê dependency và review tác động trước khi thay đổi thuộc tính này.

### Chọn API theo workload

Không nên bật tất cả API có thể có. Chỉ khai báo những dịch vụ mà workload cần:

| API | Khi cần |
|---|---|
| compute.googleapis.com | VM, disk, VPC, firewall và tài nguyên Compute Engine |
| container.googleapis.com | Google Kubernetes Engine |
| run.googleapis.com | Cloud Run |
| storage.googleapis.com | Cloud Storage |
| bigquery.googleapis.com | BigQuery |
| logging.googleapis.com | Cloud Logging và log ingestion |
| monitoring.googleapis.com | Cloud Monitoring và metric |
| iam.googleapis.com | Quản lý service account và IAM liên quan |
| cloudresourcemanager.googleapis.com | Quản lý project và resource hierarchy |
| serviceusage.googleapis.com | Bật, tắt và kiểm tra trạng thái API |

Việc bật API có thể mất một khoảng thời gian để hoàn tất và lan truyền. Terraform provider thường xử lý việc chờ operation, nhưng pipeline vẫn cần xử lý retry hợp lý cho những thao tác phụ thuộc dịch vụ mới được bật.

### API cần có trong bootstrap project

Resource tạo project gọi Cloud Resource Manager API; resource bật API gọi Service Usage API. Vì thế, project đang được dùng để chạy Terraform phải có những API cần thiết đã được bật và principal phải có quyền tương ứng. Bật API trong project đích không tự bật API trong bootstrap project.

## 6. Tạo service account và cấp IAM

### Tạo service account cho workload

Service account đại diện cho workload hoặc thành phần tự động cần gọi Google Cloud APIs. Không dùng tài khoản người dùng cá nhân làm danh tính chạy ứng dụng.

~~~hcl
resource "google_service_account" "runtime" {
  project      = google_project.application.project_id
  account_id   = "customer-api-runtime"
  display_name = "Customer API runtime"

  depends_on = [
    google_project_service.apis,
  ]
}
~~~

depends_on bảo đảm các API trong danh sách đã được quản lý trước khi tạo service account. Do service account resource tham chiếu project ID, project cũng được tạo trước.

### Cấp quyền bằng google_project_iam_member

Ví dụ, workload cần ghi log vào Cloud Logging:

~~~hcl
resource "google_project_iam_member" "runtime_log_writer" {
  project = google_project.application.project_id
  role    = "roles/logging.logWriter"
  member  = format("serviceAccount:%s", google_service_account.runtime.email)
}
~~~

google_project_iam_member thêm một principal vào một role. Nó không quản lý toàn bộ danh sách thành viên của role đó. Đây thường là lựa chọn phù hợp khi nhiều nhóm hoặc module độc lập cùng quản lý các quyền khác nhau trên một project.

Nếu nhóm vận hành cần xem metric và log, có thể cấp quyền đọc theo nhu cầu:

~~~hcl
resource "google_project_iam_member" "operations_monitoring_viewer" {
  project = google_project.application.project_id
  role    = "roles/monitoring.viewer"
  member  = format("group:%s", var.operations_group)
}

resource "google_project_iam_member" "operations_logging_viewer" {
  project = google_project.application.project_id
  role    = "roles/logging.viewer"
  member  = format("group:%s", var.operations_group)
}
~~~

Chỉ cấp các vai trò thật sự cần cho nhiệm vụ. Không cấp roles/owner, roles/editor hoặc quyền rộng ở organization chỉ để tránh lỗi permission trong quá trình triển khai.

### Phân biệt member, binding và policy

Ba resource IAM ở cấp project có mức độ authoritative khác nhau:

| Resource | Phạm vi quản lý | Tác động |
|---|---|---|
| google_project_iam_member | Một cặp role–member | Thêm hoặc xóa thành viên cụ thể; các thành viên khác của role được quản lý độc lập |
| google_project_iam_binding | Toàn bộ danh sách member cho một role | Khi áp dụng, danh sách member của role được đặt theo cấu hình |
| google_project_iam_policy | Toàn bộ IAM policy của project | Thay thế policy đầy đủ; có thể xóa các quyền không được khai báo |

Không khai báo google_project_iam_binding và google_project_iam_member cùng quản lý một role trên cùng project vì hai resource có thể ghi đè thay đổi của nhau. google_project_iam_policy có phạm vi tác động lớn nhất; chỉ dùng khi một cấu hình chuyên trách thực sự sở hữu toàn bộ IAM policy.

### Least privilege và quyền kế thừa

IAM trên Google Cloud được kế thừa theo resource hierarchy: organization, folder, project và tài nguyên con. Khi điều tra một quyền, cần xem cả policy được gán trực tiếp và policy kế thừa. Một principal có thể có quyền thông qua group hoặc folder dù không xuất hiện trực tiếp trong resource IAM mà Terraform đang quản lý.

Trước khi thay đổi IAM:

- Xác định principal là user, group, service account hay workload identity.
- Chọn role có ít quyền nhất đáp ứng nhiệm vụ.
- Chọn phạm vi project hoặc resource phù hợp.
- Kiểm tra quyền kế thừa và các binding hiện có.
- Tránh xóa thành viên do hệ thống hoặc nhóm khác quản lý.
- Xác minh ứng dụng hoạt động bằng danh tính thực tế sau khi cấp quyền.

## 7. Ghép project, API và IAM thành một cấu hình

Các resource ở trên có thể nằm trong cùng một root module. Terraform tự sắp xếp thứ tự dựa trên tham chiếu và depends_on:

~~~mermaid
flowchart TD
    A[google_project.application] --> B[google_project_service.apis]
    B --> C[google_service_account.runtime]
    C --> D[google_project_iam_member.runtime_log_writer]
    A --> D
~~~

Thứ tự logic:

1. Tạo project trong folder và liên kết billing account.
2. Bật API cần cho workload.
3. Tạo service account sau khi IAM API đã sẵn sàng.
4. Cấp role cho service account trên project.
5. Xuất project ID và service account email để các module khác sử dụng.

Trong outputs.tf:

~~~hcl
output "project_id" {
  description = "Project ID của workload."
  value       = google_project.application.project_id
}

output "runtime_service_account_email" {
  description = "Danh tính runtime của ứng dụng."
  value       = google_service_account.runtime.email
}
~~~

Output không phải nơi lưu bí mật. Nếu output chứa giá trị nhạy cảm, đánh dấu sensitive = true, nhưng hãy nhớ state vẫn có thể lưu giá trị đó và cần được bảo vệ.

## 8. Quản lý Terraform state an toàn

### Vì sao state quan trọng?

Terraform state lưu ánh xạ resource, ID tài nguyên, metadata và đôi khi cả giá trị thuộc tính nhạy cảm. Nếu mất state, Terraform có thể không nhận biết tài nguyên đã tạo; nếu state bị sửa hoặc lộ, người khác có thể gây thay đổi hạ tầng hoặc đọc thông tin nhạy cảm.

Không commit terraform.tfstate, state backup hoặc plan file có thể chứa dữ liệu nhạy cảm vào Git. Không coi sensitive = true là mã hóa state; thuộc tính này chủ yếu hạn chế hiển thị trong một số đầu ra CLI.

### Dùng Google Cloud Storage backend

Ví dụ cấu hình backend:

~~~hcl
terraform {
  backend "gcs" {
    bucket = "company-terraform-state"
    prefix = "gcp/production/customer-api"
  }
}
~~~

Bucket phải được tạo trước khi terraform init khởi tạo backend. Dùng IAM để giới hạn ai được đọc/ghi state, bật object versioning để có thể khôi phục phiên bản trước và theo dõi audit log. GCS backend hỗ trợ state locking để tránh nhiều lần chạy cùng ghi state đồng thời.

State bucket nên nằm trong project nền tảng được quản trị riêng. Tách quyền đọc state khỏi quyền triển khai workload nếu quy trình cho phép. Người có quyền đọc state có thể xem các giá trị nhạy cảm được provider ghi vào state.

### Các lệnh trong vòng đời Terraform

~~~bash
# Tải provider và khởi tạo backend
terraform init

# Chuẩn hóa HCL
terraform fmt -recursive

# Kiểm tra cú pháp và cấu trúc cấu hình
terraform validate

# Tạo plan để review trước khi thay đổi
terraform plan -out=tfplan

# Đọc lại plan đã lưu
terraform show tfplan

# Chỉ áp dụng plan đã được review
terraform apply tfplan

# Kiểm tra drift sau triển khai
terraform plan
~~~

Trong pipeline production, tách bước plan và apply để có người review. Plan file cần được lưu trong nơi có kiểm soát truy cập và thời hạn ngắn vì nó có thể chứa dữ liệu nhạy cảm. Khi cấu hình thay đổi sau khi tạo plan, hãy tạo plan mới thay vì áp dụng plan cũ.

## 9. Import và quản lý tài nguyên đã tồn tại

Nhiều organization đã có project, API hoặc IAM được tạo thủ công. Không nên tạo resource Terraform trùng với tài nguyên đang tồn tại. Có thể import tài nguyên vào state rồi điều chỉnh HCL để phản ánh trạng thái mong muốn.

Ví dụ import project hiện có:

~~~bash
terraform import google_project.application existing-project-id
~~~

Sau khi import:

1. Viết cấu hình HCL tương ứng với project thực tế.
2. Chạy terraform plan để xem khác biệt giữa HCL, state và remote object.
3. Chỉnh cấu hình hoặc quy trình import cho đến khi plan không còn đề xuất thay đổi ngoài ý muốn.
4. Chỉ apply khi đã hiểu rõ tác động của từng thay đổi.

Import chỉ đưa tài nguyên vào state; nó không tự tạo ra đầy đủ cấu hình HCL. Với IAM, cần kiểm kê policy hiện tại và chọn member/binding/policy resource phù hợp. Việc chuyển từ quản lý thủ công sang Terraform nên làm theo từng nhóm quyền nhỏ để giảm nguy cơ xóa nhầm quyền đang được sử dụng.

## 10. Drift, thay đổi và xử lý sự cố

### Configuration drift

Drift xảy ra khi trạng thái thực tế khác cấu hình Terraform, chẳng hạn quản trị viên bật thêm API hoặc cấp role thủ công ngoài Terraform. terraform plan có thể phát hiện một số khác biệt khi provider đọc lại remote state.

Khi phát hiện drift, cần xác định thay đổi có chủ đích hay không:

- Nếu thay đổi hợp lệ, cập nhật HCL để cấu hình phản ánh quyết định mới.
- Nếu thay đổi trái quy trình, xem xét để Terraform đưa tài nguyên về trạng thái mong muốn sau khi đánh giá tác động.
- Nếu tài nguyên chưa được Terraform quản lý, cân nhắc import trước khi chỉnh sửa.

Không chạy apply chỉ để làm sạch plan mà chưa hiểu vì sao drift xuất hiện.

### Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Không tạo được project | Thiếu quyền projectCreator, folder ID sai hoặc organization policy chặn | Kiểm tra principal, folder/organization và chính sách tạo project |
| Không liên kết được billing | Thiếu quyền trên billing account hoặc billing account không hoạt động | Kiểm tra billing account và quyền liên kết project |
| Bật API bị từ chối | Thiếu Service Usage Admin hoặc API cần thiết chưa bật trong bootstrap project | Kiểm tra quyền serviceusage.services.enable và API của bootstrap project |
| Tạo service account thất bại | IAM API chưa bật hoặc principal thiếu quyền | Kiểm tra iam.googleapis.com và quyền Service Account Admin |
| IAM member bị xung đột | Nhiều resource Terraform cùng quản lý một role hoặc binding | Chuẩn hóa ownership và dùng đúng một mô hình IAM cho mỗi role |
| Apply báo project đang được sử dụng | Tài nguyên phụ thuộc hoặc project có protection rule | Kiểm tra dependency và không xóa project khi chưa có kế hoạch di chuyển |
| Terraform liên tục đề xuất thay đổi | Drift, default do provider/API hoặc cấu hình không nhất quán | Đọc diff, chuẩn hóa thuộc tính và import tài nguyên nếu cần |
| State lock bị giữ | Một lần chạy trước bị dừng bất thường | Xác nhận không còn Terraform process đang chạy trước khi unlock theo quy trình |

### Xử lý state lock

Không dùng terraform force-unlock ngay khi thấy lỗi lock. Trước hết kiểm tra pipeline, terminal hoặc người đang chạy Terraform có còn hoạt động không. Chỉ unlock khi xác nhận lock thuộc một lần chạy đã dừng và có quyền xử lý state. Unlock sai có thể làm hai tiến trình cùng sửa state và gây hỏng dữ liệu quản lý.

## 11. Quy trình làm việc an toàn trong nhóm

Một workflow IaC có review thường gồm:

1. Kỹ sư tạo branch và thay đổi HCL.
2. CI chạy terraform fmt -check và terraform validate.
3. Pipeline tạo plan bằng identity được cấp quyền có kiểm soát.
4. Reviewer kiểm tra project, API, IAM diff, tác động billing và thay đổi có thể phá hủy.
5. Người được ủy quyền phê duyệt plan.
6. Pipeline áp dụng đúng plan đã duyệt.
7. Hệ thống ghi lại log, state version và kết quả triển khai.
8. Nhóm theo dõi drift và rà soát quyền định kỳ.

Nên tách root module hoặc state theo môi trường và phạm vi ownership. Ví dụ, bootstrap project, project nền tảng mạng và project workload có thể có state riêng. Cách tách này giảm phạm vi ảnh hưởng khi một lần apply gặp lỗi và giúp phân quyền nhóm vận hành rõ hơn.

### Những thực hành nên duy trì

- Commit .terraform.lock.hcl để cố định provider đã kiểm thử.
- Dùng module dùng chung cho naming, labels, API và IAM khi có nhiều project tương tự.
- Dùng biến cho project ID, folder, billing và region; không hard-code khác biệt môi trường trong resource.
- Dùng service account hoặc workload identity riêng cho từng pipeline.
- Bảo vệ state backend, plan artifact và quyền impersonation.
- Không cấp quyền rộng chỉ để làm cho một lần apply thành công.
- Review mọi thay đổi có thể xóa project, disable API hoặc thay thế IAM policy.
- Lưu output cần thiết và không xuất bí mật ra log.

## 12. Checklist trước khi triển khai production

- [ ] Principal chạy Terraform có quyền bootstrap đúng phạm vi.
- [ ] API cần cho bootstrap project đã được bật.
- [ ] Project ID, folder ID và billing account đã được xác nhận.
- [ ] Project được tạo với cấu hình network phù hợp.
- [ ] Chỉ bật những API workload cần.
- [ ] disable_on_destroy được đặt theo chính sách vòng đời API.
- [ ] Service account riêng được tạo cho workload và pipeline.
- [ ] IAM dùng role tối thiểu và principal đúng.
- [ ] Không có xung đột giữa google_project_iam_member, binding và policy.
- [ ] State dùng remote backend, locking và versioning.
- [ ] .terraform.lock.hcl được commit; state và plan không bị đưa vào Git.
- [ ] Plan đã được review trước khi apply.
- [ ] Có quy trình import và xử lý drift.
- [ ] Có biện pháp ngăn xóa project production ngoài ý muốn.

## 13. Kết luận

Terraform biến project, API và IAM thành cấu hình có thể review, tái lập và quản lý theo vòng đời. google_project tạo ranh giới quản trị; google_project_service bật dịch vụ cần thiết; google_service_account và các resource IAM xác định workload hoặc nhóm người dùng được phép thực hiện hành động nào.

Để vận hành an toàn, hãy chuẩn bị bootstrap identity có quyền tối thiểu, quản lý state từ xa, chọn đúng mô hình IAM và luôn review plan trước khi apply. Khi cấu hình Terraform trở thành nguồn sự thật cho project, API và IAM, tổ chức có thể mở rộng môi trường GCP nhất quán và kiểm soát thay đổi tốt hơn.

## Tài liệu tham khảo

- [Terraform Google Cloud provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [Google Cloud projects with Terraform](https://cloud.google.com/docs/terraform/resource-management/managing-projects)
- [google_project resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project)
- [google_project_service resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project_service)
- [google_project_iam resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project_iam)
- [Google Cloud Storage backend](https://developer.hashicorp.com/terraform/language/backend/gcs)
- [Google Cloud authentication for Terraform](https://cloud.google.com/docs/terraform/authentication)
