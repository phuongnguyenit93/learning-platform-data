# Quản lý VPC, Compute Engine và Cloud Run bằng Terraform

Terraform là công cụ Infrastructure as Code (IaC) cho phép mô tả hạ tầng bằng tệp cấu hình, xem trước thay đổi và áp dụng chúng một cách có thể lặp lại. Với Google Cloud, provider Google ánh xạ các resource trong HCL sang tài nguyên thực như VPC network, subnet, firewall rule, Compute Engine VM và Cloud Run service.

Trong module CLOUD_PROVIDERS_GCP, Terraform giúp kết nối các phần hạ tầng thành một cấu hình thống nhất. Một VPC có thể chứa subnet cho VM và subnet dành cho Cloud Run Direct VPC egress; firewall giới hạn luồng kết nối; VM chạy workload cần xử lý liên tục; Cloud Run triển khai container và mở rộng theo request. Terraform theo dõi quan hệ giữa các tài nguyên qua state và dependency graph để biết thứ tự tạo, cập nhật hoặc xóa.

Sau bài học, bạn có thể:

- Khởi tạo Terraform project dùng Google provider và xác thực bằng Application Default Credentials.
- Phân biệt provider, resource, data source, variable, output, module và state.
- Tạo VPC custom mode, subnet theo region và firewall rule.
- Tạo Compute Engine VM trong subnet riêng, không gán external IP và cho phép SSH qua IAP.
- Triển khai Cloud Run service bằng Terraform và kết nối egress đến VPC bằng Direct VPC.
- Lưu state từ xa trên Cloud Storage, review plan, quản lý drift và tổ chức môi trường dev/staging/prod.

## 1. Mô hình Terraform trên Google Cloud

Terraform đọc các tệp cấu hình HCL trong một working directory. Provider Google chịu trách nhiệm gọi Google Cloud APIs; mỗi resource block mô tả một tài nguyên cần quản lý.

Các khái niệm chính:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Provider | Kết nối Terraform với API của nền tảng | hashicorp/google |
| Resource | Tạo và quản lý một tài nguyên | google_compute_network |
| Data source | Đọc thông tin của tài nguyên có sẵn | google_project |
| Variable | Nhận giá trị đầu vào có thể thay đổi | project_id, region |
| Local | Đặt tên cho biểu thức dùng lại | danh sách API cần bật |
| Output | Xuất thông tin sau khi áp dụng | IP nội bộ của VM, URL Cloud Run |
| Module | Đóng gói cấu hình để tái sử dụng | network, compute, cloud-run |
| State | Lưu ánh xạ giữa resource trong HCL và tài nguyên thực | terraform.tfstate |

Terraform so sánh cấu hình hiện tại với state và trạng thái thực tế từ Google Cloud APIs để xây dựng execution plan. Plan cho biết tài nguyên nào được tạo, cập nhật tại chỗ, thay thế hoặc xóa.

~~~mermaid
flowchart TD
    HCL["HCL configuration"] --> TF["Terraform CLI"]
    TF --> P["Google provider"]
    TF <--> ST["Terraform state"]
    P --> API["Google Cloud APIs"]
    API --> RES["VPC / Subnet / Firewall"]
    API --> VM["Compute Engine"]
    API --> CR["Cloud Run"]
    TF --> PLAN["Plan: add / change / destroy"]
    PLAN --> REVIEW["Review và phê duyệt"]
    REVIEW --> APPLY["Apply"]
~~~

Terraform cần state để biết một resource trong cấu hình tương ứng với tài nguyên nào trên Google Cloud. Nếu state bị mất hoặc nhiều người cùng ghi state mà không khóa, Terraform có thể hiểu sai tài nguyên cần tạo hoặc thay đổi. Vì vậy, quản lý state là một phần thiết yếu của IaC.

## 2. Chuẩn bị project, công cụ và danh tính

### 2.1. Điều kiện Google Cloud

Trước khi chạy Terraform, cần có:

- Google Cloud project đã tồn tại.
- Billing được bật cho project.
- Quyền tạo network, subnet, firewall rule, VM, service account và Cloud Run service.
- Quyền bật các API cần thiết.
- Terraform CLI và Google Cloud CLI đã cài đặt.

Project ID là định danh của project, không phải display name. Region và zone cần phù hợp với vị trí triển khai. Ví dụ trong bài sử dụng asia-southeast1 và asia-southeast1-b; hãy kiểm tra machine type, image và quota ở location bạn chọn.

### 2.2. Bật Service Usage API

Terraform có thể quản lý API bằng resource google_project_service, nhưng chính Service Usage API phải được bật trước khi Terraform tạo resource đó:

~~~bash
gcloud services enable serviceusage.googleapis.com --project=PROJECT_ID
~~~

Sau đó, cấu hình Terraform có thể bật các API như Compute Engine, Cloud Run, IAM và Artifact Registry.

### 2.3. Xác thực bằng ADC

Khi chạy Terraform trên máy phát triển, đăng nhập bằng Application Default Credentials:

~~~bash
gcloud auth application-default login
gcloud config set project PROJECT_ID
~~~

Google provider tự tìm ADC. Với CI/CD, ưu tiên Workload Identity Federation hoặc service account impersonation. Tránh tạo service account key JSON dài hạn rồi commit vào repository hoặc lưu trong pipeline logs.

Danh tính chạy Terraform cần quyền quản trị phù hợp với tài nguyên mà cấu hình quản lý. Nên phân tách quyền của người tạo hạ tầng, người review plan và workload runtime. Service account của VM hoặc Cloud Run không nên nhận quyền rộng chỉ vì Terraform có quyền triển khai.

### 2.4. Khởi tạo cấu trúc thư mục

Một cấu trúc nhỏ có thể bắt đầu như sau:

~~~text
terraform/
  environments/
    dev/
      main.tf
      variables.tf
      outputs.tf
      terraform.tfvars
    prod/
      main.tf
      variables.tf
      outputs.tf
      terraform.tfvars
  modules/
    network/
    compute/
    cloud-run/
~~~

Mỗi thư mục environment là một root module có state riêng. Các module dùng chung chứa resource và output được tái sử dụng. Với bài thực hành, bạn có thể bắt đầu bằng một root module đơn giản rồi tách module khi cấu hình đã ổn định.

Không đưa credential, state file, plan file hoặc thư mục .terraform vào Git. Một .gitignore cơ bản:

~~~gitignore
.terraform/
*.tfstate
*.tfstate.*
*.tfplan
crash.log
terraform.tfvars
~~~

Nếu terraform.tfvars chỉ chứa giá trị không nhạy cảm, tổ chức có thể quyết định lưu mẫu hoặc lưu file theo quy trình review riêng. Không lưu mật khẩu, token hoặc key trong file này.

## 3. Khai báo Google provider và API

Tạo file versions.tf:

~~~hcl
terraform {
  required_version = ">= 1.5.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.31"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}
~~~

Provider version constraint giúp nhóm phát triển sử dụng một dải phiên bản đã được kiểm thử. Terraform lưu phiên bản provider đã chọn trong .terraform.lock.hcl; hãy commit file lock này để các môi trường cài cùng provider build.

Tạo file variables.tf:

~~~hcl
variable "project_id" {
  description = "Google Cloud project ID"
  type        = string
}

variable "region" {
  description = "Region triển khai subnet và Cloud Run"
  type        = string
  default     = "asia-southeast1"
}

variable "zone" {
  description = "Zone triển khai Compute Engine VM"
  type        = string
  default     = "asia-southeast1-b"
}

variable "container_image" {
  description = "Container image đã được build và có thể truy cập"
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}
~~~

Bật các API cần thiết bằng file apis.tf:

~~~hcl
locals {
  required_apis = toset([
    "compute.googleapis.com",
    "run.googleapis.com",
    "iam.googleapis.com",
    "artifactregistry.googleapis.com"
  ])
}

resource "google_project_service" "required" {
  for_each = local.required_apis

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
~~~

Thuộc tính disable_on_destroy = false giúp Terraform xóa resource quản lý API mà không tự động tắt API của project. Đây là lựa chọn phù hợp cho project dùng chung lâu dài, nơi các hệ thống khác có thể vẫn cần API đó.

Các resource hạ tầng cần phụ thuộc vào việc bật API. Có thể khai báo depends_on trên resource gốc. Terraform cũng tự tạo dependency khi một resource tham chiếu output của resource khác.

## 4. Quản lý Terraform state bằng Cloud Storage

### 4.1. Vì sao cần remote state?

Mặc định, Terraform lưu state trong file terraform.tfstate ở working directory. Cách này phù hợp cho thử nghiệm cá nhân nhưng không phù hợp khi nhiều người hoặc pipeline cùng quản lý một hạ tầng.

Remote backend lưu state ở nơi dùng chung. GCS backend có các đặc điểm:

- Lưu state thành object trong bucket và prefix được cấu hình.
- Hỗ trợ state locking để ngăn các thao tác ghi state chạy đồng thời.
- Có thể bật Object Versioning để khôi phục phiên bản state trước đó khi xảy ra lỗi hoặc xóa nhầm.
- Dùng ADC hoặc service account impersonation để xác thực.

### 4.2. Tạo bucket state riêng

Bucket dùng làm backend phải tồn tại trước khi Terraform khởi tạo GCS backend. Có thể tạo bucket bằng một cấu hình bootstrap độc lập hoặc do nhóm nền tảng quản lý:

~~~hcl
resource "google_storage_bucket" "terraform_state" {
  name                        = "company-terraform-state-unique"
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

Tên bucket phải duy nhất trên toàn Google Cloud. Giới hạn quyền đọc/ghi bucket cho các danh tính cần chạy Terraform. State có thể chứa thông tin nhạy cảm, vì vậy bucket không được public và cần được bảo vệ như một kho dữ liệu quan trọng.

Không đặt resource tạo chính bucket state trong cùng root module đang dùng bucket đó làm backend. Hãy tạo bucket trong một bootstrap stack riêng hoặc dùng bucket đã được nhóm nền tảng chuẩn bị.

### 4.3. Khai báo GCS backend

Sau khi bucket tồn tại, khai báo backend trong file backend.tf:

~~~hcl
terraform {
  backend "gcs" {
    bucket = "company-terraform-state-unique"
    prefix = "gcp/network-app/prod"
  }
}
~~~

Backend block không thể tham chiếu Terraform variables, locals hoặc data sources. Vì vậy, bucket và prefix phải được khai báo trực tiếp hoặc truyền qua backend configuration khi khởi tạo.

Khởi tạo backend:

~~~bash
terraform init
~~~

Nếu trước đó state đang ở local và cần chuyển sang GCS:

~~~bash
terraform init -migrate-state
~~~

Trước khi migrate, sao lưu state và kiểm tra bucket đích, prefix cùng quyền truy cập. Không sửa file state bằng tay; khi cần thao tác, dùng các lệnh terraform state có kiểm soát.

### 4.4. Bảo vệ state và quyền truy cập

State không phải file cấu hình công khai. Một số giá trị đánh dấu sensitive trong Terraform chỉ được ẩn khỏi output thông thường; giá trị vẫn có thể nằm trong state và plan file.

Nên thực hiện:

- Dùng bucket riêng cho state, bật Object Versioning và public access prevention.
- Giới hạn IAM trên bucket theo từng nhóm environment.
- Cấp cho danh tính chạy Terraform quyền đọc/ghi object trên bucket, thường dùng roles/storage.objectAdmin ở phạm vi bucket.
- Dùng service account hoặc impersonation cho pipeline.
- Không commit state, plan file hoặc credential.
- Không chia sẻ plan file qua kênh không được bảo vệ.
- Chỉ dùng terraform force-unlock khi đã xác nhận lock bị bỏ lại và đúng lock ID của thao tác cần giải phóng.

## 5. Tạo VPC và subnet bằng Terraform

### 5.1. VPC custom mode

VPC network là tài nguyên global; subnet nằm trong một region. Một VPC có thể chứa nhiều subnet ở các region khác nhau. Khi cần kiểm soát CIDR và vị trí subnet, custom mode với auto_create_subnetworks = false là lựa chọn rõ ràng.

Tạo file network.tf:

~~~hcl
resource "google_compute_network" "app" {
  name                    = "tf-demo-vpc"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  depends_on = [google_project_service.required]
}
~~~

Nếu bật auto_create_subnetworks, Google Cloud tự tạo subnet ở các region. Với hạ tầng cần kiểm soát dải IP, nên tắt tùy chọn này và tự khai báo subnet.

### 5.2. Subnet cho Compute Engine và Cloud Run

Tạo subnet riêng cho VM và Cloud Run Direct VPC egress:

~~~hcl
resource "google_compute_subnetwork" "vm" {
  name                     = "tf-demo-vm-subnet"
  region                   = var.region
  network                  = google_compute_network.app.id
  ip_cidr_range            = "10.40.0.0/24"
  private_ip_google_access = true
}

resource "google_compute_subnetwork" "run" {
  name                     = "tf-demo-run-subnet"
  region                   = var.region
  network                  = google_compute_network.app.id
  ip_cidr_range            = "10.40.1.0/24"
  private_ip_google_access = true
}
~~~

Hai subnet nằm trong cùng VPC nhưng có dải IP không trùng nhau. Việc tách subnet giúp quản lý địa chỉ, firewall và luồng truy cập của từng nhóm workload.

Cloud Run Direct VPC egress cần subnet IPv4 có kích thước tối thiểu /26. Cloud Run cấp phát IP theo block và có thể giữ lại địa chỉ sau khi revision scale down hoặc cập nhật. Vì vậy, subnet thực tế nên có dư địa theo số instance tối đa và các đợt rollout; ví dụ /24 ở trên có nhiều địa chỉ hơn mức tối thiểu.

Private Google Access cho phép tài nguyên chỉ có IP nội bộ truy cập các dịch vụ Google APIs và services được hỗ trợ qua đường mạng riêng. Cấu hình này không tự cung cấp đường ra Internet công cộng. Nếu VM cần tải package hoặc gọi endpoint Internet, cân nhắc Cloud NAT hoặc proxy egress.

## 6. Tạo firewall rule và bảo vệ đường truy cập

VPC custom network không tự có các rule ingress cho ứng dụng. Mặc định, ingress bị chặn cho đến khi có firewall rule cho phép.

### 6.1. SSH qua Identity-Aware Proxy

Ví dụ dưới đây chỉ cho phép SSH từ dải địa chỉ IAP TCP forwarding:

~~~hcl
resource "google_compute_firewall" "allow_iap_ssh" {
  name      = "tf-demo-allow-iap-ssh"
  network   = google_compute_network.app.name
  direction = "INGRESS"
  priority  = 1000

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["iap-ssh"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}
~~~

Người vận hành còn cần quyền IAM để mở tunnel qua IAP, thường là roles/iap.tunnelResourceAccessor, và quyền OS Login phù hợp nếu VM bật OS Login. Rule này không mở SSH từ toàn Internet.

### 6.2. Cho phép Cloud Run gọi backend VM

Giả sử backend trên VM lắng nghe TCP port 8080. Cloud Run Direct VPC egress sẽ lấy IP từ subnet của Cloud Run; địa chỉ nguồn thay đổi theo vòng đời revision. Vì vậy, firewall nên dùng toàn bộ CIDR của subnet:

~~~hcl
resource "google_compute_firewall" "allow_run_to_backend" {
  name      = "tf-demo-allow-run-to-backend"
  network   = google_compute_network.app.name
  direction = "INGRESS"
  priority  = 1000

  source_ranges = [google_compute_subnetwork.run.ip_cidr_range]
  target_tags   = ["orders-backend"]

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }
}
~~~

Rule này cho phép nguồn trong subnet Cloud Run truy cập VM có network tag orders-backend ở port 8080. Hãy thu hẹp CIDR và port theo thiết kế thực tế, đồng thời xác nhận ứng dụng trên VM thực sự lắng nghe địa chỉ nội bộ.

Không gán external IP cho VM nếu workload chỉ cần truy cập nội bộ. Kết nối quản trị có thể đi qua IAP; kết nối ứng dụng đi qua private IP trong VPC.

## 7. Tạo Compute Engine VM bằng Terraform

### 7.1. Service account cho VM

Mỗi workload nên có service account riêng. Ví dụ:

~~~hcl
resource "google_service_account" "vm" {
  account_id   = "tf-demo-vm"
  display_name = "Terraform demo VM runtime"

  depends_on = [google_project_service.required]
}
~~~

Service account runtime chỉ cần các quyền API mà phần mềm trên VM thực sự sử dụng. Trong bài này, VM minh họa kết nối mạng nội bộ; không cấp Owner hoặc Editor cho service account.

### 7.2. Khai báo VM

~~~hcl
resource "google_compute_instance" "backend" {
  name         = "tf-demo-backend"
  machine_type = "e2-small"
  zone         = var.zone
  tags         = ["iap-ssh", "orders-backend"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.vm.id
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  service_account {
    email  = google_service_account.vm.email
    scopes = ["cloud-platform"]
  }

  depends_on = [google_project_service.required]
}
~~~

Các điểm đáng chú ý:

- zone quyết định vị trí zonal của VM; region của subnet phải tương ứng với zone đó.
- boot_disk xác định image, dung lượng và loại persistent disk.
- network_interface tham chiếu subnet đã tạo, vì vậy Terraform tự biết phải tạo subnet trước VM.
- Không có access_config trong network_interface nên VM không được cấp external IPv4 address.
- enable-oslogin bật cơ chế đăng nhập OS Login. Người dùng cần roles/compute.osLogin để đăng nhập; roles/compute.osAdminLogin cho quyền quản trị hệ điều hành khi cần sudo.
- cloud-platform là OAuth scope rộng cho API, còn IAM role trên service account mới quyết định API nào được phép sử dụng.

VM trên chưa tự cài backend application. Trong môi trường thật, bạn có thể dùng startup script, image đã chuẩn hóa hoặc hệ thống quản lý cấu hình để cài ứng dụng và mở port 8080. Sau đó kiểm tra kết nối từ Cloud Run tới private IP của VM.

## 8. Triển khai Cloud Run service và kết nối VPC

### 8.1. Cloud Run dùng container image

Cloud Run triển khai container image từ Artifact Registry hoặc registry được hỗ trợ. Image phải tồn tại và danh tính triển khai/runtime phải có quyền truy cập phù hợp.

Tạo service account cho Cloud Run:

~~~hcl
resource "google_service_account" "run" {
  account_id   = "tf-demo-run"
  display_name = "Terraform demo Cloud Run runtime"

  depends_on = [google_project_service.required]
}
~~~

Service account này là danh tính runtime của revision. Nếu ứng dụng cần đọc Secret Manager, truy cập database hoặc gọi API khác, cấp role tương ứng cho riêng service account này.

### 8.2. Cloud Run Direct VPC egress

Direct VPC egress cho phép Cloud Run gửi traffic đến tài nguyên có private IP trong VPC mà không cần Serverless VPC Access connector. Với Terraform Google provider, dùng resource google_cloud_run_v2_service và block vpc_access.network_interfaces.

~~~hcl
resource "google_cloud_run_v2_service" "orders" {
  name                = "tf-demo-orders"
  location            = var.region
  deletion_protection = true
  ingress             = "INGRESS_TRAFFIC_ALL"

  scaling {
    max_instance_count = 5
  }

  template {
    service_account = google_service_account.run.email

    containers {
      image = var.container_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }

    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"

      network_interfaces {
        network    = google_compute_network.app.id
        subnetwork = google_compute_subnetwork.run.id
      }
    }
  }

  depends_on = [google_project_service.required]
}
~~~

Trong cấu hình này:

- Cloud Run service chạy ở region giống subnet Direct VPC.
- service_account xác định danh tính runtime.
- container image là image đã build và push.
- scaling giới hạn số instance tối đa của service để kiểm soát capacity và chi phí.
- PRIVATE_RANGES_ONLY gửi traffic đến địa chỉ private qua VPC; traffic Internet công cộng không tự động đi qua VPC.
- network_interfaces liên kết revision với VPC và subnet đã khai báo.

Cloud Run service chỉ dùng Direct VPC egress cho traffic đi ra. Điều này cho phép service gọi backend VM hoặc dịch vụ nội bộ; không có nghĩa VM có thể chủ động mở kết nối vào instance Cloud Run qua private IP như một VM thông thường.

Subnet Direct VPC phải cùng region với Cloud Run service và có kích thước ít nhất /26. IP của Cloud Run là ephemeral; khi tạo firewall rule, dùng CIDR của subnet thay vì cố định một địa chỉ IP. Theo dõi mức tiêu thụ IP khi tăng max_instance_count hoặc triển khai revision mới.

Cloud Run service agent cần quyền mặc định roles/run.serviceAgent để cấu hình kết nối VPC. Không xóa role này khỏi service agent. Người triển khai cũng cần quyền Cloud Run và Service Account User phù hợp trên service identity.

### 8.3. Ingress và quyền gọi Cloud Run

Ingress = INGRESS_TRAFFIC_ALL cho phép request đi vào service theo các đường mạng được Cloud Run hỗ trợ. Nó không tự làm service trở thành public. Cloud Run vẫn kiểm tra IAM invoker theo cấu hình mặc định.

Nếu chủ đích mở service cho mọi người dùng Internet, có thể cấp roles/run.invoker cho allUsers bằng resource google_cloud_run_v2_service_iam_member. Chỉ thêm binding này sau khi đã quyết định service thực sự là public:

~~~hcl
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = var.project_id
  location = google_cloud_run_v2_service.orders.location
  name     = google_cloud_run_v2_service.orders.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
~~~

Nếu ứng dụng cần xác thực, không tạo binding allUsers. Dùng IAM principal, API Gateway, load balancer hoặc cơ chế xác thực phù hợp với kiến trúc.

## 9. Kết nối các tài nguyên thành một dependency graph

Terraform tự xây dựng thứ tự triển khai dựa trên tham chiếu giữa các resource:

~~~mermaid
flowchart TD
    API["Project APIs"] --> VPC["VPC network"]
    VPC --> VMNET["VM subnet"]
    VPC --> RUNNET["Cloud Run subnet"]
    VPC --> FW1["IAP firewall"]
    VPC --> FW2["Cloud Run to VM firewall"]
    VMNET --> VM["Compute Engine VM"]
    SA1["VM service account"] --> VM
    RUNNET --> CR["Cloud Run service"]
    SA2["Cloud Run service account"] --> CR
    FW1 -.-> VM
    FW2 -.-> VM
~~~

Ví dụ, network của subnet được tham chiếu bằng google_compute_network.app.id. Đây là implicit dependency: Terraform biết VPC phải tồn tại trước subnet. Tương tự, VM tham chiếu subnet nên Terraform tạo subnet trước VM.

Chỉ dùng depends_on khi có dependency mà biểu thức không thể thể hiện, ví dụ resource cần chờ API bật nhưng không tham chiếu trực tiếp đến API resource. Dùng depends_on quá rộng làm graph khó hiểu và có thể giảm khả năng thực thi song song.

## 10. Biến, output và cấu hình theo môi trường

### 10.1. Gán giá trị đầu vào

File terraform.tfvars có thể chứa:

~~~hcl
project_id      = "my-gcp-project"
region          = "asia-southeast1"
zone            = "asia-southeast1-b"
container_image = "asia-southeast1-docker.pkg.dev/my-gcp-project/apps/orders-api:v1.4.0"
~~~

Không nên để project ID, region hoặc container image rải rác trong nhiều resource. Dùng variable giúp thay đổi môi trường mà không phải sửa logic resource.

### 10.2. Xuất thông tin sau triển khai

File outputs.tf:

~~~hcl
output "backend_internal_ip" {
  description = "Private IP của Compute Engine backend"
  value       = google_compute_instance.backend.network_interface[0].network_ip
}

output "cloud_run_uri" {
  description = "URL của Cloud Run service"
  value       = google_cloud_run_v2_service.orders.uri
}

output "vpc_name" {
  description = "Tên VPC network"
  value       = google_compute_network.app.name
}
~~~

Sau khi apply, xem output:

~~~bash
terraform output
~~~

Output giúp pipeline hoặc người vận hành nhận được địa chỉ tài nguyên. Không xuất password, token hoặc private key; đánh dấu output sensitive chỉ che output trên terminal chứ không loại giá trị khỏi state.

### 10.3. Tách dev và prod

Dev và prod có thể dùng chung module nhưng nên có state riêng, CIDR riêng, service account riêng và quyền triển khai riêng. Ví dụ:

| Thành phần | Dev | Prod |
|---|---|---|
| Root module | environments/dev | environments/prod |
| State prefix | gcp/network-app/dev | gcp/network-app/prod |
| VPC | tf-dev-vpc | tf-prod-vpc |
| CIDR | 10.50.0.0/16 | 10.60.0.0/16 |
| Cloud Run max instances | 2 | Theo capacity production |
| Quyền apply | Nhóm phát triển | Pipeline/nhóm vận hành được phê duyệt |

Không dùng Terraform workspace như ranh giới bảo mật duy nhất giữa production và non-production. Tách root directory, backend prefix và quyền IAM giúp giảm nguy cơ áp nhầm cấu hình vào project hoặc state khác.

## 11. Quy trình plan, review và apply

### 11.1. Format và validate

Sau khi tạo các file HCL:

~~~bash
terraform fmt -recursive
terraform init
terraform validate
~~~

- fmt chuẩn hóa định dạng HCL.
- init tải provider, module và khởi tạo backend.
- validate kiểm tra cú pháp và tính hợp lệ nội bộ của cấu hình.

Validate không xác nhận rằng mọi API, IAM permission, quota hoặc tên tài nguyên trên Google Cloud đều hợp lệ. Những vấn đề đó thường xuất hiện khi plan hoặc apply gọi provider.

### 11.2. Tạo và lưu plan

Tạo plan file:

~~~bash
terraform plan -out=tfplan
~~~

Đọc chi tiết plan:

~~~bash
terraform show tfplan
~~~

Review các resource sẽ được tạo, thay đổi hoặc phá hủy. Đặc biệt chú ý:

- VPC hoặc subnet có bị thay thế không.
- CIDR có bị đổi làm ảnh hưởng địa chỉ nội bộ không.
- Firewall rule có mở rộng source range hoặc port không.
- VM có bị thay đổi disk, machine type hoặc network interface không.
- Cloud Run có đổi image, service account, ingress hoặc VPC egress không.
- Tài nguyên có deletion protection hoặc lifecycle prevent_destroy không.

Sau khi plan được review và phê duyệt, apply đúng plan đã lưu:

~~~bash
terraform apply tfplan
~~~

Khi apply từ saved plan, Terraform thực thi các hành động trong plan đó. Nếu cấu hình hoặc state thay đổi sau khi plan được tạo, hãy tạo plan mới và review lại.

Không dùng terraform apply -auto-approve trong production nếu quy trình chưa có bước review tương đương.

### 11.3. Kiểm tra sau apply

Sau khi Terraform báo Apply complete, xác nhận trên Google Cloud:

- VPC và subnet có đúng CIDR, region và trạng thái.
- Firewall rule có đúng network, direction, target tags, source ranges và ports.
- VM nằm trong subnet dự kiến, không có external IP nếu thiết kế là private.
- Cloud Run service có revision Ready, image đúng và VPC egress đúng.
- Cloud Run có thể kết nối tới private backend khi ứng dụng backend đã chạy.
- IAM principal của workload có đúng quyền cần thiết.

Terraform state xác nhận quan hệ quản lý tài nguyên, còn kiểm tra runtime xác nhận ứng dụng và mạng hoạt động thực tế.

## 12. Drift, import và thay đổi tài nguyên đang tồn tại

### 12.1. Phát hiện drift

Drift xảy ra khi tài nguyên thực tế bị thay đổi ngoài Terraform, ví dụ một người sửa firewall rule trong Console. Terraform có thể phát hiện khác biệt khi refresh trạng thái trong plan.

~~~bash
terraform plan
~~~

Nếu cần cập nhật state theo trạng thái thực tế mà không thay đổi hạ tầng, xem plan refresh-only:

~~~bash
terraform plan -refresh-only
~~~

Review trước khi áp dụng refresh-only. Nếu thay đổi ngoài Terraform là chủ ý, cập nhật HCL để phản ánh trạng thái mong muốn. Nếu thay đổi ngoài Terraform là không được phép, plan thông thường có thể đưa tài nguyên về cấu hình đã khai báo.

### 12.2. Import tài nguyên đã tồn tại

Nếu VPC hoặc VM đã được tạo thủ công và cần đưa vào Terraform, khai báo resource block mô tả tài nguyên đó rồi import vào state.

Với Terraform 1.5 trở lên, có thể dùng import block:

~~~hcl
import {
  id = "projects/PROJECT_ID/global/networks/existing-vpc"
  to = google_compute_network.app
}
~~~

Chạy plan để xem import operation và các khác biệt cấu hình. Sau khi import, điều chỉnh HCL để phản ánh đúng resource thực tế rồi tiếp tục quản lý tài nguyên bằng Terraform.

Import chỉ liên kết tài nguyên đang tồn tại với resource address trong state; nó không tự động bảo đảm cấu hình HCL đã đầy đủ. Nếu bỏ qua review, lần apply sau có thể thay đổi tài nguyên ngoài dự kiến.

### 12.3. Đổi tên resource address

Khi đổi tên resource trong HCL, Terraform có thể hiểu resource cũ bị xóa và resource mới cần tạo. Nếu chỉ đổi địa chỉ quản lý, dùng moved block để thông báo sự thay đổi địa chỉ:

~~~hcl
moved {
  from = google_compute_instance.backend
  to   = google_compute_instance.orders_backend
}
~~~

Sau khi thêm moved block, chạy plan và xác nhận Terraform nhận ra đây là chuyển địa chỉ trong state thay vì tạo VM mới.

## 13. Xóa tài nguyên và bảo vệ hạ tầng

Lệnh destroy xóa tất cả resource được quản lý trong root module hiện tại:

~~~bash
terraform plan -destroy
terraform destroy
~~~

Chỉ chạy destroy khi chắc chắn đúng project, đúng backend và đúng workspace. Hủy nhầm VPC hoặc subnet production có thể làm gián đoạn nhiều workload.

Trong ví dụ Cloud Run, deletion_protection = true ngăn Terraform xóa service khi protection còn bật. Khi cần xóa service trong môi trường thử nghiệm, thay giá trị thành false, review plan, apply thay đổi protection rồi mới thực hiện destroy. Với tài nguyên quan trọng như state bucket hoặc network dùng chung, cân nhắc lifecycle prevent_destroy và quy trình phê duyệt riêng.

Khi xóa theo dependency graph, Terraform thường xóa tài nguyên phụ thuộc trước rồi mới xóa tài nguyên nền tảng. Ví dụ, phải xóa Cloud Run service sử dụng subnet trước khi xóa subnet đó. Với Direct VPC egress, Google Cloud có thể giữ lại địa chỉ IP đã cấp một khoảng thời gian sau khi service/revision ngừng dùng subnet; chờ tài nguyên được giải phóng trước khi xóa subnet.

## 14. Tổ chức module và CI/CD

### 14.1. Khi nào nên tách module?

Có thể tách module khi một nhóm tài nguyên có trách nhiệm và giao diện rõ ràng:

- Module network nhận project, region và CIDR; xuất VPC ID và subnet ID.
- Module compute nhận subnet, machine type, image và service account; xuất instance name và private IP.
- Module cloud-run nhận region, image, service account và VPC subnet; xuất service URI.

Module nên có input/output rõ ràng, tránh phụ thuộc vào tên resource nội bộ của module khác. Không cần tạo module cho từng resource nhỏ nếu việc đó làm cấu hình khó theo dõi.

### 14.2. CI/CD cho Terraform

Một pipeline triển khai an toàn thường có các bước:

1. Kiểm tra định dạng bằng terraform fmt -check.
2. Khởi tạo provider và backend bằng terraform init.
3. Kiểm tra cấu hình bằng terraform validate.
4. Chạy policy checks, security scans hoặc module tests theo quy chuẩn của tổ chức.
5. Tạo plan file và lưu artifact có kiểm soát quyền truy cập.
6. Review plan; production cần phê duyệt theo quy trình của nhóm vận hành.
7. Apply đúng plan đã phê duyệt.
8. Kiểm tra resource và workload sau triển khai.
9. Lưu kết quả và thông tin phiên bản provider/module để truy vết.

CI identity nên dùng Workload Identity Federation hoặc impersonation. Không để pipeline tải key JSON cố định rồi dùng lại lâu dài.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Error 403 khi chạy plan/apply | ADC hoặc service account thiếu IAM permission | Kiểm tra principal thực tế, role cần thiết và project được chọn |
| API not enabled | API chưa bật hoặc Service Usage API chưa bật trước | Bật serviceusage.googleapis.com, sau đó quản lý các API bằng google_project_service |
| Bucket backend không tồn tại | GCS bucket chưa được bootstrap | Tạo bucket trước rồi chạy terraform init |
| State lock đang được giữ | Một thao tác Terraform khác đang chạy hoặc lock cũ chưa được giải phóng | Kiểm tra pipeline/session đang chạy; chỉ force-unlock khi đã xác nhận lock stale |
| Resource already exists | Tài nguyên đã được tạo thủ công hoặc bởi stack khác | Kiểm tra quyền sở hữu; import đúng resource hoặc chọn tên mới |
| VM không có kết nối Internet | VM không có external IP và chưa có Cloud NAT/proxy | Cấu hình Cloud NAT hoặc đường egress phù hợp; Private Google Access chỉ phục vụ Google APIs được hỗ trợ |
| SSH tới VM thất bại | Thiếu IAP firewall rule, IAP IAM role hoặc OS Login permission | Kiểm tra dải IAP 35.235.240.0/20, roles/iap.tunnelResourceAccessor và OS Login |
| Cloud Run không gọi được VM | Sai region/subnet, firewall thiếu CIDR nguồn hoặc backend không lắng nghe port | Kiểm tra Direct VPC egress, source subnet CIDR, target tag và service port |
| Cloud Run deploy không lấy được image | Image sai hoặc thiếu quyền Artifact Registry | Kiểm tra image URI, repository location và quyền truy cập image |
| Plan muốn thay thế subnet hoặc VM | Thay đổi thuộc tính buộc resource recreate hoặc cấu hình khác thực tế | Đọc phần forces replacement, đánh giá downtime và migration trước khi apply |
| Cloud Run Direct VPC thiếu IP | Subnet quá nhỏ hoặc revision scale lớn | Mở rộng kế hoạch CIDR, giám sát IP allocation và đặt max instances phù hợp |

## 16. Checklist triển khai production

- [ ] Project, billing, quota và APIs đã sẵn sàng.
- [ ] Terraform CLI và Google provider được pin theo phiên bản đã kiểm thử.
- [ ] Xác thực qua ADC, Workload Identity Federation hoặc service account impersonation.
- [ ] State được lưu trong GCS bucket riêng, bật Object Versioning và state locking.
- [ ] Bucket state có uniform bucket-level access, public access prevention và IAM giới hạn.
- [ ] Mỗi environment có root module và state prefix riêng.
- [ ] VPC dùng custom subnet, CIDR không chồng lấn và region được chọn rõ ràng.
- [ ] Firewall chỉ mở source range, target và port cần thiết.
- [ ] VM private không có external IP nếu không cần public ingress.
- [ ] Cloud Run dùng runtime service account riêng và ingress/auth được thiết kế rõ ràng.
- [ ] Direct VPC subnet có đủ IP cho scale và revision rollout.
- [ ] Resource dependencies dựa vào tham chiếu; depends_on chỉ dùng cho dependency ẩn.
- [ ] Plan được lưu, review và apply đúng artifact đã phê duyệt.
- [ ] State, plan và credential không bị commit hoặc chia sẻ công khai.
- [ ] Có quy trình import, drift review, rollback và xóa tài nguyên.
- [ ] Kiểm tra runtime sau apply, không chỉ dựa vào thông báo Terraform thành công.

## 17. Câu hỏi tự kiểm tra

**1. Vì sao cần Terraform state?**

State ánh xạ resource address trong HCL với tài nguyên thực trên Google Cloud. Terraform dùng state để tính toán thay đổi, tránh tạo trùng tài nguyên và xác định resource cần cập nhật hoặc xóa.

**2. VPC và subnet có phạm vi khác nhau thế nào trên Google Cloud?**

VPC network là tài nguyên global, còn subnet là tài nguyên regional. Một VPC có thể chứa nhiều subnet ở các region khác nhau.

**3. Vì sao nên dùng custom mode VPC với auto_create_subnetworks = false?**

Custom mode cho phép chủ động đặt CIDR, region và tách subnet cho từng nhóm workload. Điều này giúp quản lý IP và firewall rõ ràng hơn.

**4. Cloud Run Direct VPC egress dùng subnet để làm gì?**

Cloud Run cấp phát địa chỉ IP từ subnet để gửi traffic ra tài nguyên nội bộ trong VPC. Subnet cần cùng region với service và tối thiểu /26; nên dự trù thêm địa chỉ theo quy mô instance và rollout.

**5. Vì sao nên dùng GCS backend thay vì giữ state trên máy cá nhân?**

GCS backend cho phép nhóm và pipeline dùng chung state, hỗ trợ state locking và Object Versioning để phục hồi phiên bản trước.

**6. terraform plan khác terraform apply ở điểm nào?**

Plan tính toán và hiển thị thay đổi dự kiến. Apply thực thi thay đổi đó trên hạ tầng sau khi đã review và phê duyệt.

**7. Khi nào cần dùng terraform import?**

Khi tài nguyên đã tồn tại trên Google Cloud nhưng chưa được Terraform quản lý. Import liên kết tài nguyên với resource address trong state; cấu hình HCL vẫn cần được kiểm tra và hoàn thiện.

## 18. Tài liệu tham khảo

- [Terraform on Google Cloud](https://cloud.google.com/docs/terraform)
- [Getting started with the Google Cloud provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs/guides/getting_started)
- [Google provider: google_compute_network](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_network)
- [Google provider: google_compute_subnetwork](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_subnetwork)
- [Google provider: google_compute_firewall](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_firewall)
- [Google provider: google_compute_instance](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_instance)
- [Google provider: google_cloud_run_v2_service](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_v2_service)
- [Google provider: google_project_service](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project_service)
- [Store Terraform state in Cloud Storage](https://cloud.google.com/docs/terraform/resource-management/store-state)
- [Terraform GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs)
- [Terraform operations best practices](https://cloud.google.com/docs/terraform/best-practices/operations)
- [Cloud Run Direct VPC egress](https://cloud.google.com/run/docs/configuring/vpc-direct-vpc)
- [Connect Cloud Run to a VPC network](https://cloud.google.com/vpc/docs/configure-serverless-vpc-access)

