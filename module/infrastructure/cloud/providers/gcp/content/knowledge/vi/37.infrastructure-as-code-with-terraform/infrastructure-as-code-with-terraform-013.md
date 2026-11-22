# Thực hành triển khai landing zone tối giản bằng mã

Trong module `CLOUD_PROVIDERS_GCP`, bạn khám phá Google Cloud từ tổ chức, project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Trước khi đưa workload lên các dịch vụ đó, tổ chức cần một nền tảng dùng chung để quản lý danh tính, phân tách môi trường, kiểm soát mạng, lưu dấu vết hoạt động và quản lý chi phí.

Landing zone là nền tảng cloud được thiết kế để workload có thể triển khai và vận hành theo những quy tắc thống nhất. Bài thực hành này xây một landing zone GCP tối giản bằng Terraform: tổ chức và folder, các project nền tảng, Shared VPC, API cần thiết, một số organization policy guardrails và nơi tập trung audit logs. Bạn sẽ triển khai theo từng lớp để hiểu thứ tự phụ thuộc và cách kiểm soát thay đổi.

## 1. Mục tiêu và phạm vi landing zone

Một landing zone không chỉ là một VPC hoặc một project mẫu. Nó kết hợp danh tính, resource hierarchy, mạng và security controls; monitoring/logging, backup, cost management và kết nối hybrid có thể được bổ sung theo nhu cầu. Thiết kế nên bắt đầu từ workload đầu tiên nhưng đủ mô-đun để mở rộng.

Bài lab tạo một nền tảng minh họa gồm:

- Một organization resource đã được thiết lập thông qua Google Workspace hoặc Cloud Identity.
- Các folder để tách bootstrap, shared infrastructure, production và non-production.
- Project riêng cho mạng dùng chung, lưu trữ audit logs và workload của từng môi trường.
- Shared VPC host project cung cấp subnet cho các service project.
- Organization policies ngăn tạo default network và service account key mới.
- Organization-level log sink chuyển audit logs đến kho lưu trữ tập trung.
- Terraform state được lưu trong Cloud Storage với versioning và quyền truy cập riêng.

Sơ đồ mục tiêu:

~~~mermaid
flowchart TB
  ORG[Google Cloud Organization]
  ORG --> BOOT[bootstrap folder]
  ORG --> SHARED[shared infrastructure folder]
  ORG --> NONPROD[non-production folder]
  ORG --> PROD[production folder]
  BOOT --> STATE[Terraform state / CI identity]
  SHARED --> NET[network-host project]
  SHARED --> LOG[central-logs project]
  NONPROD --> DEV[app-dev project]
  PROD --> APP[app-prod project]
  NET --> VPC[Shared VPC + subnets]
  VPC --> DEV
  VPC --> APP
  ORG --> POLICY[Organization policies]
  ORG --> SINK[Organization audit-log sink]
  SINK --> LOG
~~~

Đây là một thiết kế học tập nhỏ. Trong tổ chức lớn, bạn có thể cần Shared VPC riêng cho production và non-production, nhiều project mạng, thư mục security riêng, VPC Service Controls, Cloud NAT, Cloud DNS, hybrid connectivity và các policy bổ sung. Không có một cấu trúc folder hoặc network duy nhất phù hợp cho mọi doanh nghiệp.

## 2. Chuẩn bị trước khi chạy Terraform

### 2.1. Các tài nguyên phải có trước

Terraform không thể tự tạo organization resource hoặc billing account từ một project thông thường. Trước khi chạy foundation stack, cần có:

1. Google Cloud organization được liên kết với Google Workspace hoặc Cloud Identity.
2. Billing account đang hoạt động.
3. Organization ID và billing account ID.
4. Một project bootstrap để bật API, cấp quyền cho Terraform và lưu Terraform state.
5. Một danh tính thực thi Terraform có quyền tạo folder/project, cấu hình IAM, organization policies, Shared VPC và log sink.

Project bootstrap và state bucket cần tồn tại trước khi backend GCS có thể được khởi tạo. Bạn có thể tạo chúng trong một bước bootstrap riêng bằng quy trình quản trị ban đầu, sau đó chuyển foundation stack sang backend từ xa. Không nên để một state backend phụ thuộc vào chính bucket mà state đó phải tạo ra.

### 2.2. Quyền của danh tính thực thi

Hãy cấp quyền theo từng lớp tài nguyên. Các role dưới đây là những role thường gặp; quyền chính xác phụ thuộc vào tài nguyên và cách bạn chia stack:

| Công việc | Quyền thường cần | Phạm vi |
| --- | --- | --- |
| Tạo folder | `roles/resourcemanager.folderCreator` | Organization hoặc folder cha |
| Tạo project | `roles/resourcemanager.projectCreator` | Organization hoặc folder cha |
| Gắn project vào billing account | `roles/billing.user` trên billing account và quyền quản lý billing của project | Billing account/project |
| Quản lý organization policies | `roles/orgpolicy.policyAdmin` | Organization hoặc folder được quản lý |
| Bật API trong project | `roles/serviceusage.serviceUsageAdmin` | Project |
| Quản lý Shared VPC | `roles/compute.xpnAdmin` và các quyền quản trị network cần thiết | Organization/host project |
| Quản lý VPC/subnet/firewall | `roles/compute.networkAdmin` | Network host project |
| Tạo organization log sink | `roles/logging.configWriter` hoặc quyền tương đương | Organization |
| Cấp IAM trên tài nguyên | Quyền IAM phù hợp với resource, ví dụ role quản trị IAM ở đúng phạm vi | Organization/folder/project |

Tách quyền bootstrap có phạm vi rộng khỏi quyền vận hành hằng ngày. Trong production, không dùng các role cơ bản Owner, Editor hoặc Viewer làm quyền triển khai tổng quát. Thay vào đó, cấp role chuyên biệt hoặc custom role chỉ chứa các permission mà stack cần.

Nếu dùng danh tính ngắn hạn từ Workload Identity Federation hoặc service account impersonation, hãy áp dụng bài học xác thực Terraform trước đó: danh tính CI chỉ được phép impersonate service account triển khai đã định danh; service account đó nhận quyền quản lý foundation theo phạm vi được phê duyệt.

### 2.3. Bật API cần cho bootstrap

Trong project bootstrap, bật các API mà quy trình quản trị cần sử dụng. Ví dụ:

~~~bash
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  orgpolicy.googleapis.com \
  serviceusage.googleapis.com \
  logging.googleapis.com \
  --project=BOOTSTRAP_PROJECT_ID
~~~

Một số API được bật trong project đích khi Terraform tạo project và kích hoạt dịch vụ. Service Usage API phải khả dụng để Terraform quản lý `google_project_service`.

## 3. Thiết lập Terraform root và remote state

### 3.1. Bố cục thư mục

Tổ chức mã theo các lớp để thay đổi hierarchy không buộc bạn phải chỉnh sửa network hoặc workload cùng lúc:

~~~text
landing-zone/
├── bootstrap/
│   └── state-bucket/          # tạo một lần trước foundation stack
├── foundation/
│   ├── versions.tf
│   ├── providers.tf
│   ├── backend.tf
│   ├── variables.tf
│   ├── folders-projects.tf
│   ├── policies.tf
│   ├── networking.tf
│   ├── logging.tf
│   └── outputs.tf
└── environments/
    ├── dev.tfvars
    └── prod.tfvars
~~~

Ví dụ bên dưới gom các phần chính để dễ học. Khi dùng thật, tách thành module theo trách nhiệm và giữ interface đầu vào/đầu ra rõ ràng.

### 3.2. Khai báo phiên bản provider

`versions.tf`:

~~~hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.0"
    }
  }
}
~~~

Dải `~> 8.0` là ví dụ cho Google provider major version 8. Hãy chọn dải tương thích với phiên bản provider đã được tổ chức kiểm thử, chạy `terraform init` để tạo/cập nhật `terraform.lock.hcl`, rồi commit lock file vào Git. Không tự động nâng major version trong pipeline production.

### 3.3. Khai báo provider và backend

`providers.tf`:

~~~hcl
provider "google" {
  project = var.bootstrap_project_id
  region  = var.region
}
~~~

Provider sử dụng Application Default Credentials (ADC). Trên máy phát triển, bạn có thể đăng nhập bằng user ADC; trong CI/CD, ưu tiên Workload Identity Federation hoặc danh tính service account được gắn vào runner trên Google Cloud. Tránh đưa service account key JSON vào mã Terraform hoặc biến môi trường lâu dài.

`backend.tf`:

~~~hcl
terraform {
  backend "gcs" {
    bucket = "REPLACE_WITH_PRECREATED_TFSTATE_BUCKET"
    prefix = "landing-zone/foundation"
  }
}
~~~

Thay bucket bằng tên bucket bootstrap đã tạo. Backend GCS lưu state tập trung và hỗ trợ state locking. Bật Object Versioning cho bucket để có thể khôi phục phiên bản state trước đó khi xảy ra thao tác nhầm. Dùng Uniform Bucket-Level Access, Public Access Prevention và IAM tối thiểu; chỉ danh tính triển khai và người vận hành được phép mới có quyền đọc/ghi state.

Backend khởi tạo ở bước `terraform init`, trước khi Terraform thực thi các resource của provider. Vì vậy, quyền truy cập state bucket phải được cấu hình riêng và kiểm tra trước khi chạy plan. Nếu backend cần impersonate service account khác, cấu hình `impersonate_service_account` cho backend GCS hoặc biến môi trường tương ứng; quyền truy cập backend không tự động được cấp chỉ vì provider có quyền tạo tài nguyên.

### 3.4. Khai báo biến

`variables.tf`:

~~~hcl
variable "organization_id" {
  description = "Numeric ID of the Google Cloud organization."
  type        = string
}

variable "billing_account_id" {
  description = "Billing account ID used for new projects."
  type        = string
}

variable "bootstrap_project_id" {
  description = "Existing project used as the provider's default project."
  type        = string
}

variable "network_project_id" {
  description = "Globally unique project ID for the Shared VPC host."
  type        = string
}

variable "logs_project_id" {
  description = "Globally unique project ID for centralized logs."
  type        = string
}

variable "dev_project_id" {
  description = "Globally unique project ID for the development workload."
  type        = string
}

variable "prod_project_id" {
  description = "Globally unique project ID for the production workload."
  type        = string
}

variable "region" {
  description = "Primary region for the sample network."
  type        = string
  default     = "asia-southeast1"
}

variable "dev_subnet_cidr" {
  type    = string
  default = "10.40.0.0/20"
}

variable "prod_subnet_cidr" {
  type    = string
  default = "10.50.0.0/20"
}

variable "developer_group_email" {
  description = "Google Group for application developers."
  type        = string
}

variable "prod_operator_group_email" {
  description = "Google Group allowed to use production subnets."
  type        = string
}

variable "log_archive_bucket_name" {
  description = "Globally unique name for the audit-log archive bucket."
  type        = string
}
~~~

Các project ID và bucket name phải duy nhất theo quy tắc đặt tên của Google Cloud. Không dùng giá trị ví dụ trong môi trường thật nếu chúng đã được một tổ chức khác sử dụng. Hãy quản lý các giá trị môi trường trong tfvars hoặc pipeline variables; không đưa thông tin xác thực vào tfvars.

## 4. Tạo resource hierarchy và project

### 4.1. Tạo folder theo môi trường và chức năng

`folders-projects.tf`:

~~~hcl
resource "google_folder" "bootstrap" {
  display_name = "Bootstrap"
  parent       = format("organizations/%s", var.organization_id)
}

resource "google_folder" "shared" {
  display_name = "Shared Infrastructure"
  parent       = format("organizations/%s", var.organization_id)
}

resource "google_folder" "nonprod" {
  display_name = "Non-Production"
  parent       = format("organizations/%s", var.organization_id)
}

resource "google_folder" "prod" {
  display_name = "Production"
  parent       = format("organizations/%s", var.organization_id)
}
~~~

Project bootstrap đã tồn tại trước foundation stack và được dùng làm project mặc định của provider. Folder Bootstrap trong ví dụ là điểm đặt các tài nguyên nền tảng về sau; nếu project bootstrap hiện ở vị trí khác trong hierarchy, hãy lập kế hoạch di chuyển riêng hoặc import folder/project hiện có. Không tự di chuyển project đang vận hành chỉ để làm cho sơ đồ trông giống ví dụ.

Folder là điểm kế thừa IAM và organization policy. Ví dụ, nhóm vận hành mạng có thể quản lý tài nguyên trong Shared Infrastructure; nhóm ứng dụng được cấp quyền trên folder của môi trường tương ứng. Cách chia theo môi trường giúp áp dụng policy và quyền khác nhau cho production và non-production.

Không cần tạo nhiều tầng folder ngay từ đầu. Chỉ thêm folder khi có ranh giới quản trị, bảo mật, chi phí hoặc vòng đời cần thể hiện. Dùng tên nhất quán và tránh gắn chặt folder với tên cá nhân hoặc vị trí của một nhân viên.

### 4.2. Tạo project nền tảng và workload

~~~hcl
resource "google_project" "network_host" {
  name            = "Shared Network Host"
  project_id      = var.network_project_id
  folder_id       = google_folder.shared.name
  billing_account = var.billing_account_id
}

resource "google_project" "central_logs" {
  name            = "Central Logs"
  project_id      = var.logs_project_id
  folder_id       = google_folder.shared.name
  billing_account = var.billing_account_id
}

resource "google_project" "app_dev" {
  name            = "Application Development"
  project_id      = var.dev_project_id
  folder_id       = google_folder.nonprod.name
  billing_account = var.billing_account_id
}

resource "google_project" "app_prod" {
  name            = "Application Production"
  project_id      = var.prod_project_id
  folder_id       = google_folder.prod.name
  billing_account = var.billing_account_id
}
~~~

Mỗi project là đơn vị quản lý API, IAM, billing và tài nguyên dịch vụ. Tách network host, central logs và workload projects giúp giới hạn quyền và quản lý chi phí theo mục đích. Billing account được gắn ở cấp project; folder không tự trở thành một billing account.

Nếu project đã tồn tại, không tạo lại với một ID khác chỉ để đưa nó vào Terraform. Hãy đánh giá trạng thái hiện tại và dùng `terraform import` hoặc import block để đưa tài nguyên hiện có vào state. Việc import cần xác nhận đúng resource address, project ID và cấu hình trước khi apply.

### 4.3. Bật API theo từng project

~~~hcl
resource "google_project_service" "network_host" {
  for_each = toset([
    "compute.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com"
  ])

  project            = google_project.network_host.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_project_service" "central_logs" {
  for_each = toset([
    "storage.googleapis.com",
    "logging.googleapis.com"
  ])

  project            = google_project.central_logs.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_project_service" "app_dev" {
  for_each = toset([
    "compute.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com"
  ])

  project            = google_project.app_dev.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_project_service" "app_prod" {
  for_each = toset([
    "compute.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com"
  ])

  project            = google_project.app_prod.project_id
  service            = each.value
  disable_on_destroy = false
}
~~~

Chỉ bật API mà project cần. `disable_on_destroy = false` giúp Terraform không tự tắt API khi resource service bị xóa khỏi cấu hình. Điều này hữu ích vì API có thể đang được dùng bởi tài nguyên ngoài phạm vi state hiện tại. Quản lý API như một phần của project baseline và review các thay đổi trước khi apply.

### 4.4. Cấp quyền nhóm theo folder

Ví dụ chỉ cấp quyền xem cho nhóm phát triển trong folder non-production:

~~~hcl
resource "google_folder_iam_member" "nonprod_developers_viewer" {
  folder = google_folder.nonprod.name
  role   = "roles/viewer"
  member = format("group:%s", var.developer_group_email)
}
~~~

`google_folder_iam_member` thêm một thành viên vào một role mà không thay toàn bộ policy. Ưu tiên IAM member hoặc binding có phạm vi rõ ràng. Hạn chế dùng resource IAM policy authoritative vì nó có thể thay thế toàn bộ policy hiện tại và vô tình loại bỏ các binding khác.

Role Viewer trong ví dụ chỉ cho phép đọc. Khi nhóm cần triển khai workload, hãy cấp thêm các role cụ thể ở project hoặc resource cần quản lý, kèm điều kiện IAM khi phù hợp. Không cấp Editor toàn folder chỉ để làm cho pipeline chạy được.

## 5. Áp dụng organization policy guardrails

Organization policy giúp đặt giới hạn cấu hình nhất quán cho toàn bộ descendants của organization hoặc một folder. Bài lab áp dụng hai guardrail cơ bản:

1. Không tạo default VPC network khi project mới được tạo.
2. Không tạo service account key do người dùng quản lý.

`policies.tf`:

~~~hcl
resource "google_org_policy_policy" "skip_default_network" {
  name   = format("organizations/%s/policies/compute.skipDefaultNetworkCreation", var.organization_id)
  parent = format("organizations/%s", var.organization_id)

  spec {
    rules {
      enforce = "TRUE"
    }
  }
}

resource "google_org_policy_policy" "disable_service_account_keys" {
  name   = format("organizations/%s/policies/iam.managed.disableServiceAccountKeyCreation", var.organization_id)
  parent = format("organizations/%s", var.organization_id)

  spec {
    rules {
      enforce = "TRUE"
    }
  }
}
~~~

`google_org_policy_policy` dùng Organization Policy API v2. Tên policy bao gồm resource cha và constraint. Policy được kế thừa xuống folder và project; một policy ở cấp thấp hơn có thể thay đổi kết quả theo quy tắc kế thừa của Organization Policy.

Guardrail về service account key phù hợp khi tổ chức đã dùng Workload Identity Federation, service account impersonation hoặc service account gắn vào compute resource. Trước khi enforce trên phạm vi lớn, kiểm tra các pipeline và workload hiện có có còn phụ thuộc vào key JSON hay không. Việc chặn tạo key không tự động chuyển đổi hệ thống cũ đang dùng key.

Organization policy có thể làm một số thao tác tạo tài nguyên thất bại. Ví dụ, constraint chặn tạo service account có thể ngăn một số dịch vụ tự tạo default service account khi bật API. Vì vậy, không bật constraint chặn service account creation trong bài lab này; hãy đánh giá tác động và thứ tự triển khai riêng trước khi áp dụng constraint đó.

Với production, cần review từng guardrail với đội bảo mật, kiểm tra inheritance và lập quy trình exception có thời hạn. Không dùng policy để thay thế IAM; policy giới hạn cấu hình tài nguyên, còn IAM xác định ai được phép thực hiện thao tác.

## 6. Tạo Shared VPC cho workload projects

Shared VPC cho phép network team quản lý network trong một host project, trong khi workload được đặt trong các service project. Cách này giúp tách quyền quản trị mạng khỏi quyền triển khai ứng dụng.

### 6.1. Bật Shared VPC host project

`networking.tf`:

~~~hcl
resource "google_compute_shared_vpc_host_project" "host" {
  project = google_project.network_host.project_id

  depends_on = [
    google_project_service.network_host["compute.googleapis.com"]
  ]
}

resource "google_compute_network" "shared" {
  project                 = google_project.network_host.project_id
  name                    = "shared-vpc"
  auto_create_subnetworks = false
  routing_mode            = "GLOBAL"

  depends_on = [
    google_compute_shared_vpc_host_project.host
  ]
}
~~~

`auto_create_subnetworks = false` tạo custom-mode VPC, cho phép bạn kiểm soát CIDR theo region. Host project cần Compute Engine API và quyền Shared VPC administration phù hợp.

### 6.2. Tạo subnet theo môi trường

~~~hcl
resource "google_compute_subnetwork" "dev" {
  project                  = google_project.network_host.project_id
  name                     = format("dev-%s", var.region)
  region                   = var.region
  network                  = google_compute_network.shared.id
  ip_cidr_range            = var.dev_subnet_cidr
  private_ip_google_access = true
}

resource "google_compute_subnetwork" "prod" {
  project                  = google_project.network_host.project_id
  name                     = format("prod-%s", var.region)
  region                   = var.region
  network                  = google_compute_network.shared.id
  ip_cidr_range            = var.prod_subnet_cidr
  private_ip_google_access = true
}
~~~

Các CIDR phải không chồng lấn với mạng on-premises, VPN, VPC peering hoặc các VPC khác có thể kết nối sau này. `private_ip_google_access` cho phép VM không có external IP truy cập các API và dịch vụ Google thông qua đường đi riêng phù hợp. Tùy yêu cầu, bạn có thể bổ sung Cloud NAT, Private Service Access, firewall rules, Cloud DNS và hybrid connectivity ở các bước sau.

### 6.3. Gắn service projects vào host project

~~~hcl
resource "google_compute_shared_vpc_service_project" "dev" {
  host_project    = google_compute_shared_vpc_host_project.host.project
  service_project = google_project.app_dev.project_id

  depends_on = [
    google_project_service.app_dev["compute.googleapis.com"],
    google_compute_subnetwork.dev
  ]
}

resource "google_compute_shared_vpc_service_project" "prod" {
  host_project    = google_compute_shared_vpc_host_project.host.project
  service_project = google_project.app_prod.project_id

  depends_on = [
    google_project_service.app_prod["compute.googleapis.com"],
    google_compute_subnetwork.prod
  ]
}
~~~

Việc liên kết service project với host project chưa tự động cấp mọi quyền sử dụng subnet cho mọi danh tính. Hãy cấp `roles/compute.networkUser` trên subnet hoặc phạm vi mạng phù hợp cho các service account và nhóm triển khai cần tạo tài nguyên trong Shared VPC. Giữ quyền này ở đúng subnet để tránh cho một workload non-production sử dụng mạng production ngoài ý muốn.

Ví dụ cấp quyền Network User riêng trên từng subnet cho nhóm triển khai tương ứng:

~~~hcl
resource "google_compute_subnetwork_iam_member" "dev_network_users" {
  project    = google_compute_subnetwork.dev.project
  region     = google_compute_subnetwork.dev.region
  subnetwork = google_compute_subnetwork.dev.name
  role       = "roles/compute.networkUser"
  member     = format("group:%s", var.developer_group_email)
}

resource "google_compute_subnetwork_iam_member" "prod_network_users" {
  project    = google_compute_subnetwork.prod.project
  region     = google_compute_subnetwork.prod.region
  subnetwork = google_compute_subnetwork.prod.name
  role       = "roles/compute.networkUser"
  member     = format("group:%s", var.prod_operator_group_email)
}
~~~

Một Shared VPC với hai subnet là ví dụ đơn giản để học. Trong môi trường có yêu cầu cô lập cao, nên dùng Shared VPC riêng cho production và non-production, sau đó thiết kế firewall policy, route và quyền network user riêng cho từng host project. Không dùng chung một subnet cho tất cả workload chỉ vì chúng cùng region.

## 7. Tập trung audit logs về project quản trị

Audit logs giúp đội bảo mật và vận hành điều tra thay đổi tài nguyên, thay đổi IAM và hoạt động API. Organization-level aggregated sink có thể thu thập log từ organization và các project con, sau đó định tuyến đến nơi lưu trữ tập trung.

### 7.1. Tạo bucket lưu trữ log

`logging.tf`:

~~~hcl
resource "google_storage_bucket" "audit_archive" {
  project                     = google_project.central_logs.project_id
  name                        = var.log_archive_bucket_name
  location                    = "ASIA"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  depends_on = [
    google_project_service.central_logs["storage.googleapis.com"]
  ]
}
~~~

Bucket này là đích lưu trữ archive. Trong môi trường thật, xác định location theo yêu cầu residency, retention và truy vấn. Có thể cấu hình retention policy, object lifecycle, logging access và quy trình xóa dữ liệu phù hợp với chính sách tổ chức. Không cấp quyền đọc rộng cho người dùng ứng dụng.

### 7.2. Tạo organization log sink

~~~hcl
resource "google_logging_organization_sink" "audit_archive" {
  name             = "organization-audit-archive"
  org_id           = var.organization_id
  destination      = format("storage.googleapis.com/%s", google_storage_bucket.audit_archive.name)
  include_children = true

  filter = "logName:\"cloudaudit.googleapis.com\""
}
~~~

Sink có `include_children = true` để lấy log từ project con. Filter giới hạn vào Cloud Audit Logs. Tùy nhu cầu, có thể mở rộng filter để thu thập thêm log ứng dụng, VPC Flow Logs hoặc firewall logs; hãy cân nhắc dung lượng và chi phí trước khi thu thập tất cả.

### 7.3. Cấp quyền ghi cho sink writer identity

~~~hcl
resource "google_storage_bucket_iam_member" "audit_sink_writer" {
  bucket = google_storage_bucket.audit_archive.name
  role   = "roles/storage.objectCreator"
  member = google_logging_organization_sink.audit_archive.writer_identity
}
~~~

Khi tạo sink, Cloud Logging cấp một writer identity riêng. Bạn phải cấp quyền ghi object cho identity đó trên bucket đích; nếu thiếu binding này, sink có thể tồn tại nhưng log không được ghi vào đích. Terraform tạo bucket trước, tạo sink để lấy writer identity, rồi cấp quyền IAM tương ứng.

Để phục vụ điều tra, hãy định nghĩa rõ ai được xem archive, ai được thay đổi sink và ai được xóa bucket/object. Quyền cấu hình sink ở organization scope có tác động đến nhiều project nên cần được review như thay đổi bảo mật.

## 8. Khai báo outputs để kiểm tra kết quả

`outputs.tf`:

~~~hcl
output "folder_ids" {
  value = {
    bootstrap = google_folder.bootstrap.name
    shared    = google_folder.shared.name
    nonprod   = google_folder.nonprod.name
    prod      = google_folder.prod.name
  }
}

output "project_ids" {
  value = {
    network_host = google_project.network_host.project_id
    central_logs = google_project.central_logs.project_id
    app_dev      = google_project.app_dev.project_id
    app_prod     = google_project.app_prod.project_id
  }
}

output "shared_vpc_network" {
  value = google_compute_network.shared.self_link
}

output "audit_sink_writer_identity" {
  value = google_logging_organization_sink.audit_archive.writer_identity
}
~~~

Outputs giúp pipeline hoặc người vận hành kiểm tra các resource đã được tạo và lấy tên định danh cho bước cấu hình tiếp theo. Không đưa secret hoặc access token vào output. Project ID, folder name và network self link không phải credential nhưng vẫn nên được xử lý theo quy định thông tin hạ tầng của tổ chức.

## 9. Triển khai theo từng giai đoạn

Không nên chạy một lệnh apply khổng lồ ngay lần đầu. Triển khai từng lớp giúp kiểm tra quyền, billing và policy trước khi tạo network hoặc sink.

### Bước 1: Khởi tạo backend

~~~bash
terraform init
~~~

Nếu backend GCS chưa có hoặc danh tính thực thi không đọc/ghi được bucket, dừng ở bước này và xử lý quyền. Không chuyển sang local state tạm thời trong pipeline production mà không có kế hoạch migration và kiểm soát state.

### Bước 2: Kiểm tra biến môi trường

Tạo file `environments/dev.tfvars`:

~~~hcl
organization_id          = "123456789012"
billing_account_id       = "000000-000000-000000"
bootstrap_project_id     = "org-bootstrap-123"
network_project_id       = "org-network-host-123"
logs_project_id          = "org-central-logs-123"
dev_project_id           = "org-app-dev-123"
prod_project_id          = "org-app-prod-123"
region                   = "asia-southeast1"
dev_subnet_cidr          = "10.40.0.0/20"
prod_subnet_cidr         = "10.50.0.0/20"
developer_group_email    = "cloud-developers@example.com"
prod_operator_group_email = "cloud-operations@example.com"
log_archive_bucket_name  = "org-audit-archive-123456789012"
~~~

Thay tất cả giá trị minh họa bằng ID thật và CIDR đã được nhóm mạng phê duyệt. File tfvars chỉ chứa cấu hình, không chứa key JSON, mật khẩu hoặc access token. Nếu ID môi trường là dữ liệu nhạy cảm theo chính sách nội bộ, hãy lưu trong kho cấu hình được kiểm soát.

### Bước 3: Format và validate

~~~bash
terraform fmt -recursive
terraform validate
~~~

`terraform fmt` chuẩn hóa định dạng HCL; `terraform validate` kiểm tra cấu trúc và kiểu cấu hình sau khi provider đã được khởi tạo. Hai lệnh này không xác nhận rằng danh tính có đủ IAM permission hoặc organization policy cho phép tạo tài nguyên.

### Bước 4: Review plan

~~~bash
terraform plan \
  -var-file="environments/dev.tfvars" \
  -out="foundation-dev.tfplan"
~~~

Đọc kỹ plan trước khi apply. Xác nhận đúng organization, folder cha, project ID, billing account, CIDR, destination log sink và các policy đang được enforce. Đặc biệt xem kỹ các thay đổi IAM và organization policy vì chúng có thể ảnh hưởng đến workload hiện hữu ngoài stack.

Plan file có thể chứa giá trị nhạy cảm từ state hoặc cấu hình. Bảo vệ file plan như dữ liệu hạ tầng nội bộ; không commit vào Git hoặc upload lên nơi công khai.

### Bước 5: Apply có kiểm soát

~~~bash
terraform apply "foundation-dev.tfplan"
~~~

Chỉ apply plan đã được review và phê duyệt theo quy trình thay đổi của tổ chức. Với production, dùng pipeline có kiểm soát quyền, môi trường approval và cùng một danh tính thực thi đã được xác minh. Không dùng `-auto-approve` cho lần triển khai foundation đầu tiên.

### Bước 6: Xác minh outputs và state

~~~bash
terraform output folder_ids
terraform output project_ids
terraform output shared_vpc_network
terraform state list
~~~

Đối chiếu outputs với Resource Manager, IAM, VPC và Logging trong Console. Terraform state phải được lưu trong remote backend, khóa state hoạt động và chỉ nhóm cần thiết mới có quyền truy cập.

## 10. Kiểm tra landing zone sau khi triển khai

Dùng checklist sau để xác minh từng lớp:

| Lớp | Kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Hierarchy | Xem organization và các folder | Bootstrap, Shared Infrastructure, Non-Production và Production xuất hiện đúng cha. |
| Projects | Xem project list và billing | Network host, central logs, app dev và app prod ở đúng folder và gắn billing account. |
| API | Kiểm tra API đã bật trong từng project | Chỉ API cần thiết được bật; Compute Engine API sẵn sàng cho Shared VPC. |
| Organization policies | Xem policy inheritance | Default network creation và service account key creation bị giới hạn theo policy đã cấu hình. |
| Shared VPC | Xem host/service project associations | App dev và app prod được gắn vào đúng host project. |
| Subnets | Kiểm tra region và CIDR | Subnet không chồng lấn và thuộc đúng VPC. |
| Network IAM | Kiểm tra `roles/compute.networkUser` | Chỉ danh tính triển khai/workload được phép mới dùng subnet. |
| Logging | Kiểm tra organization sink và destination | Sink include children, writer identity có quyền ghi bucket. |
| Terraform state | Chạy `terraform plan` lần nữa | Không có thay đổi ngoài dự kiến sau khi triển khai thành công. |

Một lần `terraform plan` thứ hai không có thay đổi ngoài dự kiến là tín hiệu tốt cho thấy cấu hình và state đang đồng bộ. Tuy nhiên, vẫn cần kiểm tra cấu hình ngoài Terraform, audit logs và quyền IAM để phát hiện thay đổi thủ công hoặc drift.

## 11. Vận hành và mở rộng landing zone

Landing zone là nền tảng sống cùng workload. Sau khi tạo thành công, tiếp tục duy trì các quy tắc sau:

- **Giữ bootstrap riêng:** quản lý state bucket, danh tính CI và pipeline trong một stack bootstrap có vòng đời được kiểm soát.
- **Tách state theo lớp:** hierarchy/policies, network, logging và workload có thể có state riêng để giảm blast radius và quyền cần thiết.
- **Bảo vệ production:** dùng approval cho apply, review plan và hạn chế ai có thể thay đổi folder, IAM, org policy hoặc network.
- **Quản lý drift:** chạy plan định kỳ, điều tra thay đổi ngoài Terraform và import tài nguyên được chấp nhận quản lý bằng IaC.
- **Mở rộng logging:** bổ sung retention, Log Analytics/BigQuery, alert và quy trình xử lý sự kiện; xác minh log sink không bị thay đổi trái phép.
- **Quản lý chi phí:** gắn nhãn và budget theo project, environment và owner; xem billing export để phân tích chi phí theo workload.
- **Mở rộng mạng:** thêm Cloud NAT, Cloud DNS, firewall policies, Private Service Connect hoặc hybrid connectivity khi có yêu cầu thực tế.
- **Tách môi trường:** nếu production và non-production có yêu cầu bảo mật khác nhau, cân nhắc host project và Shared VPC riêng thay vì chỉ dùng subnet khác nhau.
- **Review guardrails:** thử nghiệm organization policy trong sandbox hoặc folder thử nghiệm trước khi enforce rộng trên organization.

Nếu landing zone có nhiều project và nhiều nhóm, hãy cân nhắc Google Cloud Foundation Fabric hoặc Enterprise Foundations Blueprint. Các giải pháp này cung cấp module và kiến trúc tham chiếu rộng hơn cho enterprise; bài lab hiện tại là điểm khởi đầu để hiểu các thành phần cốt lõi.

## 12. Sự cố thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Tạo folder bị 403 | Terraform identity thiếu Folder Creator trên organization hoặc folder cha. | Cấp quyền đúng scope, xác minh lại principal đang chạy Terraform. |
| Tạo project bị từ chối | Thiếu Project Creator hoặc project ID đã tồn tại. | Kiểm tra IAM, ID duy nhất và trạng thái project hiện hữu. |
| Không gắn được billing | Thiếu quyền trên billing account hoặc project. | Kiểm tra Billing User và quyền Project Billing Manager. |
| Không bật được API | Service Usage API chưa bật hoặc identity thiếu Service Usage Admin. | Bật API cần thiết ở bootstrap và cấp role trên project đích. |
| Organization policy bị từ chối | Policy đã được kế thừa hoặc có constraint khác chặn thao tác. | Xem policy ở organization/folder/project và đánh giá tác động trước khi override. |
| Shared VPC association lỗi | Compute API chưa bật hoặc thiếu quyền Shared VPC Admin. | Bật API ở cả host/service project và cấp quyền ở đúng scope. |
| Workload không dùng được subnet | Service project đã attach nhưng principal thiếu Network User. | Cấp `roles/compute.networkUser` ở subnet/host project theo phạm vi tối thiểu. |
| Log sink không ghi vào bucket | Writer identity chưa được cấp quyền object creation. | Cấp `roles/storage.objectCreator` cho writer identity trên bucket đích. |
| `terraform init` lỗi 403 | Backend identity không có quyền truy cập GCS state bucket. | Kiểm tra ADC/impersonation và IAM trên bucket; backend quyền độc lập với resource provider. |
| Terraform muốn thay thế project hoặc folder | Thay đổi thuộc tính bất biến hoặc cấu hình không khớp resource hiện hữu. | Review plan, import hoặc migration có kiểm soát; không apply khi chưa hiểu tác động. |

Không giải quyết lỗi quyền bằng cách cấp Owner hoặc Editor tạm thời rồi quên thu hồi. Xác định permission còn thiếu, cấp role hẹp nhất trong thời gian cần thiết và ghi nhận thay đổi IAM.

## 13. Checklist hoàn thành landing zone tối giản

- [ ] Organization resource và billing account đã tồn tại.
- [ ] Bootstrap project, remote state bucket và Terraform execution identity đã sẵn sàng.
- [ ] Terraform dùng provider version được pin và ADC/WIF thay cho service account key lâu dài.
- [ ] Folder hierarchy tách bootstrap, shared infrastructure, production và non-production.
- [ ] Project network host, central logs, app dev và app prod được tạo dưới đúng folder.
- [ ] Billing account được gắn cho từng project.
- [ ] API cần thiết được bật ở đúng project.
- [ ] Organization policy guardrails đã được review và áp dụng theo inheritance.
- [ ] Shared VPC host project và service project association hoạt động.
- [ ] Subnet CIDR không chồng lấn và network access được cấp theo nguyên tắc tối thiểu.
- [ ] Organization audit-log sink có writer identity và destination hoạt động.
- [ ] Terraform state được lưu an toàn, có versioning và quyền IAM riêng.
- [ ] Plan đã được review; apply có approval; lần plan tiếp theo không có drift ngoài dự kiến.

## Tài liệu tham khảo

- [Landing zone design in Google Cloud](https://docs.cloud.google.com/architecture/landing-zones) — các thành phần nền tảng, lựa chọn kiến trúc và lộ trình triển khai landing zone.
- [Decide a resource hierarchy for your Google Cloud landing zone](https://docs.cloud.google.com/architecture/landing-zones/decide-resource-hierarchy) — cách tổ chức organization, folders, projects, bootstrap và shared infrastructure.
- [Google Cloud resource hierarchy](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy) — quan hệ cha/con và kế thừa IAM, organization policies.
- [Terraform Google provider: google_folder](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_folder) — tạo folder bằng Terraform.
- [Terraform Google provider: google_project](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project) — tạo project, folder parent và billing account.
- [Terraform Google provider: google_project_service](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project_service) — bật API cho project.
- [Terraform Google provider: google_org_policy_policy](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/org_policy_policy) — quản lý organization policies bằng API v2.
- [Terraform Google provider: Shared VPC host project](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_shared_vpc_host_project) — bật Shared VPC host project.
- [Terraform Google provider: Shared VPC service project](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_shared_vpc_service_project) — gắn service project vào host project.
- [Terraform Google provider: organization logging sink](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/logging_organization_sink) — định tuyến log từ organization và project con.
- [Terraform GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs) — remote state, xác thực, locking và cấu hình backend.
- [Manage baseline organization policy constraints](https://docs.cloud.google.com/organization-policy/manage-baseline-constraints) — các guardrail mặc định và tác động đến service account keys.
- [Enterprise foundations blueprint](https://docs.cloud.google.com/architecture/blueprints/security-foundations) — kiến trúc tham chiếu cho nền tảng enterprise trên Google Cloud.

