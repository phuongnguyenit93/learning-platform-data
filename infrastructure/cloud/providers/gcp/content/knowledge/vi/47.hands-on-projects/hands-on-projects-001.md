# Dự án landing zone với IAM, VPC và ngân sách

Trong module `CLOUD_PROVIDERS_GCP`, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua những tình huống triển khai, người học thực hành lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Ở chương **Dự án thực hành GCP**, bài này kết hợp các kiến thức nền tảng thành một **landing zone tối giản** có thể kiểm tra và mở rộng.

Bạn đóng vai nhóm nền tảng đang chuẩn bị môi trường `sandbox` cho một ứng dụng Java/Spring Boot. Trước khi triển khai ứng dụng, nhóm phải tạo **ranh giới quản trị**, **danh tính và quyền tối thiểu**, **mạng riêng có kiểm soát**, cùng **ngân sách và cảnh báo chi phí**. Hạ tầng được mô tả bằng **Terraform**; các bước kiểm tra phân biệt rõ cấu hình tồn tại với khả năng sử dụng tài nguyên thực tế.

> **Quan trọng:** Đây là lab hạ tầng có thể phát sinh chi phí và đòi hỏi quyền cấp organization/folder/billing account. Chỉ triển khai vào môi trường được phép, có billing owner và giới hạn tài nguyên. Ví dụ sử dụng project mới, không thay đổi IAM hoặc firewall của production. **Billing Budget dạng cảnh báo không phải hard spending cap**: khi vượt ngưỡng, dịch vụ có thể tiếp tục hoạt động và tiếp tục phát sinh phí.

## 1. Yêu cầu đầu bài và tiêu chí hoàn thành

Một nhóm sản phẩm cần một project `orders-sandbox` để sau này triển khai Java API. Nhóm nền tảng có trách nhiệm chuẩn bị những thành phần sau:

| Hạng mục | Yêu cầu kỹ thuật | Bằng chứng nghiệm thu |
| --- | --- | --- |
| Resource hierarchy | Project lab nằm dưới folder do đội nền tảng quản lý, gắn billing account hợp lệ | Project/folder ID, parent, billing association |
| IAM | Có service account runtime riêng; nhóm quan sát chỉ được xem logs; nhóm mạng chỉ có quyền xem network | IAM policy không có quyền Owner/Editor cấp bừa |
| Default network | Ngăn tạo default VPC cho project mới khi organization policy cho phép | Effective policy và danh sách VPC không có `default` |
| VPC | Tạo custom-mode VPC, subnet ở region đã chọn, CIDR không chồng lấn | Network/subnetwork description |
| Firewall | Không mở SSH/RDP ra toàn Internet; chỉ rule lab có nguồn/đích hạn chế | Danh sách firewall rules và kết quả review |
| Private access | Bật Private Google Access trên subnet để chuẩn bị cho VM không có external IP | Subnet setting; không nhầm với IAM |
| Budget | Budget theo **một project**, kỳ tháng, có ngưỡng chi tiêu và dự báo | Budget hiển thị đúng scope, amount và notifications |
| Automation | Terraform plan có review, state lưu riêng, apply bởi danh tính được cấp phép | Plan, `terraform output`, lần plan tiếp theo không thay đổi ngoài dự kiến |
| Recovery | Có runbook dọn tài nguyên đúng scope, bảo vệ project khỏi xóa ngoài ý muốn | Danh sách resource, kế hoạch hủy theo phê duyệt |

**Phạm vi MVP:** không tạo VM, database, cluster hay public load balancer; chỉ dựng các ranh giới để workload có thể đi vào sau. Điều này giúp giảm chi phí trong lab và tránh nhầm việc một subnet đã tồn tại đồng nghĩa mạng đã được kiểm chứng bằng traffic.

## 2. Kiến trúc mục tiêu

~~~mermaid
flowchart TB
    ORG[Google Cloud organization]
    FOLDER[Folder: Hands-on Sandbox]
    PROJ[Project: orders-sandbox]
    SA[Service account: orders-runtime]
    GROUPS[IAM: observer + network groups]
    API[Enabled APIs]
    VPC[Custom VPC: orders-vpc]
    SUBNET[Subnet: orders-app, 10.42.0.0/24]
    FW[Ingress firewall: TCP 8080 limited to subnet]
    BUDGET[Monthly Billing Budget: project-scoped]
    BILL[Cloud Billing account]
    STATE[Bootstrap project + protected GCS state]

    ORG --> FOLDER
    FOLDER --> PROJ
    PROJ --> SA
    PROJ --> GROUPS
    PROJ --> API
    PROJ --> VPC
    VPC --> SUBNET
    VPC --> FW
    BILL --> PROJ
    BILL --> BUDGET
    BUDGET -.->|filters numeric project ID| PROJ
    STATE -.->|Terraform manages| FOLDER
    STATE -.->|Terraform manages| PROJ
~~~

### 2.1. Phân biệt các ranh giới

- **Organization và folder:** ranh giới kế thừa IAM và Organization Policy, thích hợp để đặt baseline bảo mật cho nhiều project.
- **Project:** nơi gắn billing, quota, API enablement, service accounts và đa số resource.
- **Service account:** danh tính mà workload dùng để gọi Google APIs; không phải tài khoản cá nhân của deployer.
- **VPC/subnet:** đường mạng và phạm vi IP nội bộ; không tự xác thực người dùng hoặc cấp quyền truy cập Google API.
- **Billing account/budget:** theo dõi chi phí của các project, có thể thiết lập cảnh báo khi đạt ngưỡng; không phải chính sách firewall hoặc quota.
- **Terraform state:** chứa thông tin hạ tầng và có thể chứa dữ liệu nhạy cảm; phải dùng backend được bảo vệ và phân quyền riêng.

Landing zone ở cấp doanh nghiệp có thể bổ sung Shared VPC, organization-wide audit logs, DNS, Cloud NAT, SCC, KMS, VPC Service Controls và cấu trúc nhiều môi trường. Bài này cố ý giới hạn vào **IAM, VPC và ngân sách** để người học hiểu từng ranh giới trước khi mở rộng.

## 3. Chuẩn bị trước khi thực hành

### 3.1. Tiền điều kiện

Cần có:

1. Một **Google Cloud organization** và quyền tạo folder/project trong vùng được cấp phép. Một tài khoản cá nhân không có organization không thể thực hiện nguyên mẫu folder-level giống hệt bài lab.
2. Cloud Billing account đang hoạt động, mã billing account và quyền liên kết project vào account.
3. **Bootstrap project tồn tại sẵn**, dùng làm project mặc định của Terraform provider và chứa Cloud Storage bucket cho remote state.
4. Cloud Storage bucket lưu Terraform state **được tạo trước**, bật Object Versioning, Uniform Bucket-Level Access và Public Access Prevention.
5. Terraform CLI và Google Cloud CLI; một danh tính thực thi có thể dùng Application Default Credentials (ADC), ưu tiên service account impersonation hoặc Workload Identity Federation cho CI/CD.
6. Một project ID và bucket name chưa được sử dụng, region phù hợp và dải CIDR không trùng với mạng đang có.
7. Địa chỉ Google Groups `lab-observers@example.com` và `lab-network@example.com` **đã tồn tại** hoặc được thay bằng những nhóm thực tế của tổ chức.

Không để Terraform **tự tạo bucket của backend trong chính state đang cần backend đó**. Hãy tạo bootstrap layer riêng rồi mới khởi tạo foundation layer.

### 3.2. Ma trận quyền của danh tính triển khai

| Công việc | Role thường cần | Scope |
| --- | --- | --- |
| Tạo folder | `roles/resourcemanager.folderCreator` | Organization hoặc folder cha |
| Quản lý organization policy cho folder | `roles/orgpolicy.policyAdmin` | Folder được phép quản lý |
| Tạo project | `roles/resourcemanager.projectCreator` | Organization hoặc folder cha |
| Liên kết billing | `roles/billing.user` và quyền quản lý billing của project thích hợp | Billing account + project |
| Bật API | `roles/serviceusage.serviceUsageAdmin` | Project được tạo |
| Tạo VPC/subnet/firewall | `roles/compute.networkAdmin` và quyền API thích hợp | Project mạng |
| Tạo service account | `roles/iam.serviceAccountAdmin` hoặc custom role tương đương | Project |
| Gán IAM member vào project | Quyền `resourcemanager.projects.setIamPolicy` từ role quản lý IAM phù hợp | Project |
| Tạo budget cấp billing account | `roles/billing.costsManager` hoặc `roles/billing.admin` | Billing account |
| Đọc/ghi remote state | Quyền Cloud Storage tối thiểu phục vụ state operations | Bootstrap state bucket |

Đây là **tổng hợp các quyền cho lab**; không nên cấp toàn bộ cho một identity lâu dài trong production. Đội nền tảng có thể chia thành *organization bootstrap*, *network foundation* và *billing FinOps* để giảm blast radius. Những quyền rộng chỉ dùng tại đúng bước tạo foundation; CI triển khai ứng dụng sau này không cần Project Creator hay Billing Admin.

Với user ADC dùng resource `google_billing_budget` qua Terraform Google provider, tài liệu provider yêu cầu cấu hình `billing_project` và `user_project_override = true` để dùng project tính quota phù hợp. Danh tính đó cần `serviceusage.services.use` trên bootstrap billing project.

### 3.3. Bootstrap APIs

Chạy dưới danh tính được phép trên **bootstrap project** (không phải project lab chưa được tạo):

~~~bash
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  serviceusage.googleapis.com \
  cloudbilling.googleapis.com \
  billingbudgets.googleapis.com \
  orgpolicy.googleapis.com \
  iam.googleapis.com \
  compute.googleapis.com \
  --project=BOOTSTRAP_PROJECT_ID
~~~

Một số API cũng cần có hiệu lực trên project nguồn/đích theo service cụ thể. Resource `google_project_service` sau này bật API trong project mới, nhưng Terraform phải có quyền quản lý Service Usage ở đó. Không dùng quyền Owner trên toàn organization để khắc phục lỗi `403` trong lab.

## 4. Bố cục repository và state

Ví dụ cấu trúc:

~~~text
gcp-landing-lab/
├── bootstrap/               # tạo từ trước: GCS state bucket + CI identity
├── foundation/
│   ├── versions.tf
│   ├── providers.tf
│   ├── variables.tf
│   ├── hierarchy.tf
│   ├── iam.tf
│   ├── network.tf
│   ├── budget.tf
│   └── outputs.tf
└── environments/
    └── sandbox.tfvars
~~~

**Không cần tạo các file trên vào module Java Learning:** đây là các file Terraform mà **người học sẽ tạo trong workspace lab của họ**, không phải file nguồn của bài học này.

### 4.1. Phiên bản Terraform và provider

`foundation/versions.tf`:

~~~hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }

  backend "gcs" {
    bucket = "REPLACE_WITH_EXISTING_TFSTATE_BUCKET"
    prefix = "hands-on/landing-zone"
  }
}
~~~

Dải `~> 7.0` là **ví dụ nhánh provider** để minh họa, không phải cam kết đây luôn là phiên bản mới nhất. Chọn phiên bản tương thích với môi trường đã kiểm thử và commit `terraform.lock.hcl`. Thay placeholder bucket bằng bucket đã có trước khi `terraform init`.

`foundation/providers.tf`:

~~~hcl
provider "google" {
  project               = var.bootstrap_project_id
  region                = var.region
  billing_project       = var.bootstrap_project_id
  user_project_override = true
}
~~~

Provider dùng ADC. Phần `billing_project` ở đây nhằm cấp quota/billing context cho các API, **không gắn billing account tự động cho project mới**. Backend GCS và provider cũng có thể dùng **hai cơ chế xác thực khác nhau**; xác minh quyền đọc/ghi state riêng trước khi plan.

### 4.2. Biến đầu vào

`foundation/variables.tf`:

~~~hcl
variable "organization_id" {
  description = "Numeric organization ID."
  type        = string
}

variable "bootstrap_project_id" {
  description = "Existing project used for Terraform quota and state."
  type        = string
}

variable "billing_account_id" {
  description = "Cloud Billing account identifier."
  type        = string
}

variable "lab_project_id" {
  description = "Globally unique new project ID."
  type        = string
}

variable "region" {
  type    = string
  default = "asia-southeast1"
}

variable "subnet_cidr" {
  type    = string
  default = "10.42.0.0/24"
}

variable "observer_group_email" {
  type = string
}

variable "network_group_email" {
  type = string
}

variable "budget_currency" {
  description = "Currency code of the billing account."
  type        = string
  default     = "USD"
}

variable "monthly_budget_units" {
  description = "Whole currency units for monthly alerts-only budget."
  type        = string
  default     = "50"
}
~~~

**Chú ý về tiền tệ:** giá trị `USD` và 50 chỉ là ví dụ nếu billing account thực sự sử dụng USD. Với tài khoản có đơn vị tiền khác, lấy currency code thực tế và điều chỉnh amount phù hợp; không tự suy rằng mọi Cloud Billing account ở Việt Nam dùng cùng đơn vị tiền.

## 5. Resource hierarchy: folder, organization policy và project

### 5.1. Folder cô lập lab

`foundation/hierarchy.tf`:

~~~hcl
resource "google_folder" "sandbox" {
  display_name = "Hands-on Sandbox"
  parent       = format("organizations/%s", var.organization_id)
}
~~~

Folder không phải billing account. Giá trị `google_folder.sandbox.name` có định dạng `folders/NUMERIC_ID` và có thể truyền làm `folder_id` cho project. Project ID và numeric project number khác nhau, đều cần trong các API khác nhau.

### 5.2. Guardrail chống default network

Tạo policy tại **folder sandbox** để project mới không sinh default VPC khi bật Compute Engine API:

~~~hcl
resource "google_org_policy_policy" "skip_default_network" {
  name   = format(
    "%s/policies/compute.skipDefaultNetworkCreation",
    google_folder.sandbox.name
  )
  parent = google_folder.sandbox.name

  spec {
    rules {
      enforce = "TRUE"
    }
  }
}
~~~

Policy này cần Organization Policy API và quyền quản trị tương ứng. **Đây là constraint boolean, không phải firewall rule**. Nó ngăn default network được tạo tự động trong các project con khi policy có hiệu lực.

**Thứ tự quan trọng:** organization policy có thể mất thời gian lan truyền. Với môi trường yêu cầu chặt, hãy tạo folder và policy ở **bootstrap/foundation stage riêng**, xác minh **effective policy** trên folder rồi mới tạo project. Một dependency trong Terraform chỉ đảm bảo lời gọi tạo policy hoàn tất, **không đảm bảo mọi quyền/policy đã lan truyền đến mọi backend** ngay lập tức.

Nếu bạn **không có quyền Organization Policy**, không bỏ qua kiểm soát rồi mặc nhiên coi không có default network. Nhờ quản trị viên cấu hình policy ở folder cha, hoặc tách phần quản trị ra khỏi project lab và xác minh trước khi triển khai.

### 5.3. Tạo project có billing, labels và deletion protection

Cũng trong `foundation/hierarchy.tf`:

~~~hcl
resource "google_project" "sandbox" {
  name            = "Orders Landing Sandbox"
  project_id      = var.lab_project_id
  folder_id       = google_folder.sandbox.name
  billing_account = var.billing_account_id

  labels = {
    env        = "sandbox"
    owner_team = "platform"
    cost_area  = "training"
  }

  deletion_policy = "PREVENT"

  depends_on = [google_org_policy_policy.skip_default_network]
}
~~~

Trong Google provider nhánh hiện hành, `deletion_policy = "PREVENT"` khiến Terraform từ chối thao tác destroy/recreate project ngoài ý muốn. Đây không phải khóa Resource Manager tuyệt đối đối với mọi administrator Google Cloud, nhưng là một guardrail hữu ích trong vòng đời Terraform. Thay project ID gây replacement; không đổi project ID sau khi chạy chỉ vì muốn tên đẹp hơn.

Các project hiện hữu phải được đánh giá và **import vào state**, không tạo bản sao để tránh xung đột ID. Một project đã bật billing và có dữ liệu sản xuất không nên được Terraform lab vô tình quản lý hoặc xóa.

### 5.4. Bật các API cần dùng

~~~hcl
resource "google_project_service" "enabled" {
  for_each = toset([
    "compute.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com"
  ])

  project            = google_project.sandbox.project_id
  service            = each.value
  disable_on_destroy = false
}
~~~

`disable_on_destroy = false` tránh tự tắt API khi resource service bị bỏ khỏi Terraform state/config; điều này không có nghĩa an toàn để xóa mọi tài nguyên đang dùng API. Xem lại nhu cầu API và quyền trước khi apply.

**Lab theo giai đoạn:** lần đầu có thể provision folder/policy, kiểm tra effective constraint rồi mới provision project, APIs và network. Với môi trường chuẩn hóa, nên tách các stack thành các state có quyền riêng thay vì dựa vào `terraform -target` như quy trình lâu dài.

## 6. IAM baseline: nguyên tắc ít quyền nhất

### 6.1. Tạo runtime service account

`foundation/iam.tf`:

~~~hcl
resource "google_service_account" "orders_runtime" {
  project      = google_project.sandbox.project_id
  account_id   = "orders-runtime"
  display_name = "Orders sandbox runtime"

  depends_on = [
    google_project_service.enabled["iam.googleapis.com"]
  ]
}
~~~

Đây là danh tính cho **ứng dụng sẽ chạy sau này**, không phải danh tính chạy Terraform. Nó chưa tự có quyền gọi Storage, Cloud SQL hoặc Pub/Sub. Khi thêm workload, cấp role chuyên biệt trên **tài nguyên đích** thay vì `Editor` toàn project.

### 6.2. Quyền quan sát và quyền mạng tách biệt

~~~hcl
resource "google_project_iam_member" "observers_logs" {
  project = google_project.sandbox.project_id
  role    = "roles/logging.viewer"
  member  = format("group:%s", var.observer_group_email)
}

resource "google_project_iam_member" "network_readers" {
  project = google_project.sandbox.project_id
  role    = "roles/compute.networkViewer"
  member  = format("group:%s", var.network_group_email)
}

resource "google_project_iam_member" "runtime_logs" {
  project = google_project.sandbox.project_id
  role    = "roles/logging.logWriter"
  member  = format(
    "serviceAccount:%s",
    google_service_account.orders_runtime.email
  )
}
~~~

Mục tiêu của ba binding:

- Nhóm **observers** xem log theo phạm vi role được cấp, không sửa VPC hoặc project IAM.
- Nhóm **network readers** xem cấu hình mạng, không mặc nhiên sửa firewall.
- Runtime SA có thể ghi log ứng dụng theo quyền `logging.logWriter`; không được tự mở rộng quyền quản trị.

Nếu tổ chức có dữ liệu nhạy cảm trong Data Access logs hoặc private log buckets, `roles/logging.viewer` không đồng nghĩa được xem mọi nội dung. Phân quyền theo data sensitivity và log view; không đưa secret/password/token vào log.

**Ưu tiên `google_project_iam_member`** khi nhiều nhóm/hệ thống cùng quản lý bindings. Resource `google_project_iam_policy` có tính **authoritative** và có thể thay toàn bộ policy; chỉ dùng nếu đã kiểm soát toàn bộ quyền sở hữu IAM của project. IAM Conditions và custom roles có thể được bổ sung sau khi hợp đồng quyền rõ ràng.

### 6.3. Những quyền không nên cấp

Không cấp cho runtime:

- `roles/owner`, `roles/editor` hoặc `roles/resourcemanager.projectIamAdmin`.
- `roles/billing.admin`, `roles/resourcemanager.projectCreator`.
- Quyền tạo service account keys nếu tổ chức đã chặn bằng Organization Policy.
- `roles/iam.serviceAccountTokenCreator` trên các service accounts khác nếu không có luồng impersonation được duyệt.

Triển khai CI/CD nên dùng Workload Identity Federation hoặc service account impersonation ngắn hạn; tách quyền **deployer** khỏi quyền **runtime**. Khi một người rời nhóm hoặc workload bị xâm nhập, phạm vi ảnh hưởng phải đủ nhỏ để thu hồi.

## 7. VPC: custom mode, subnet và firewall tối thiểu

### 7.1. Tạo VPC chỉ có subnet do người học định nghĩa

`foundation/network.tf`:

~~~hcl
resource "google_compute_network" "orders" {
  project                 = google_project.sandbox.project_id
  name                    = "orders-vpc"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  depends_on = [
    google_project_service.enabled["compute.googleapis.com"]
  ]
}
~~~

**Custom-mode VPC** không tự sinh subnet ở tất cả các region. Đây là lựa chọn phù hợp khi đội mạng muốn kiểm soát từng CIDR. Tuy nhiên, tự tạo một custom VPC **không xóa default VPC**; đó là nhiệm vụ của guardrail ở mục 5 và xác minh thực tế.

### 7.2. Tạo subnet theo địa chỉ đã quy hoạch

~~~hcl
resource "google_compute_subnetwork" "orders_app" {
  project                  = google_project.sandbox.project_id
  name                     = "orders-app"
  region                   = var.region
  network                  = google_compute_network.orders.id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true
}
~~~

Ví dụ `10.42.0.0/24` dành cho sandbox. Trước khi áp dụng trong hệ thống lớn, đối chiếu với dải on-premises, VPN, VPC peering, Shared VPC, Private Service Access và dự phòng không gian địa chỉ trong tương lai.

`private_ip_google_access = true` giúp **VM không có external IP** trên subnet có khả năng truy cập các API Google được hỗ trợ theo đường đi phù hợp. Nó **không cấp IAM**, không bảo đảm mọi Google API được truy cập qua private endpoint, không cấp Internet egress và không tự tạo Cloud NAT. Để kiểm chứng, phải triển khai một workload test và xem cả routing/DNS và IAM; MVP hiện tại chỉ kiểm chứng cấu hình.

### 7.3. Firewall minh họa có phạm vi hẹp

~~~hcl
resource "google_compute_firewall" "lab_app_internal" {
  project   = google_project.sandbox.project_id
  name      = "allow-lab-app-internal-8080"
  network   = google_compute_network.orders.name
  direction = "INGRESS"
  priority  = 1000

  source_ranges = [var.subnet_cidr]
  target_tags   = ["lab-app"]

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }
}
~~~

Rule này chỉ cho phép TCP `8080` từ dải subnet đã chọn **đến các Compute Engine VMs có network tag `lab-app`**. Trong MVP chưa tạo VM, nên rule **không cho phép một ứng dụng nào kết nối ngay**. Nó cũng không phải IAM permission, không áp dụng cho Cloud Run theo semantics network tags của VM, và không tự động tạo route/hệ thống lắng nghe cổng.

Google Cloud có **implied deny ingress** và **implied allow egress** ở VPC firewall (trừ khi bị policy/rule khác thay đổi). Vì vậy, không tạo rule inbound `0.0.0.0/0` cho SSH `22` hoặc RDP `3389`. Nếu cần SSH quản trị VM sau này, đánh giá IAP TCP forwarding, OS Login, firewall chỉ cho dải IAP phù hợp và IAM riêng. Tránh coi network tag là boundary chống kẻ đã có quyền quản lý VM/tag; có thể tăng cường bằng hierarchical firewall policies hoặc service-account-based rules.

### 7.4. Nếu sau này triển khai Cloud Run hoặc GKE

- **Cloud Run:** Direct VPC egress yêu cầu subnet đủ IP và cấu hình egress; không mặc nhiên thuộc subnet như một VM. Ingress HTTP của Cloud Run được kiểm soát riêng.
- **GKE:** cần quy hoạch secondary IP ranges cho Pods/Services nếu dùng VPC-native cluster, tránh trùng CIDR; thêm firewall và IAM Workload Identity Federation riêng.
- **Compute Engine:** VM nên không có external IP khi không cần, gắn runtime service account với quyền tối thiểu, kiểm tra shielded settings và route/egress.
- **Cloud SQL private IP:** cần thêm Private Service Access/Private Service Connect hoặc kết nối được hỗ trợ; custom VPC một mình chưa đủ để kết nối Cloud SQL.

Landing zone MVP chỉ là **điểm xuất phát**, không phải chứng nhận rằng mọi ứng dụng có thể triển khai an toàn mà không cần thiết kế bổ sung.

## 8. Billing Budget theo project và cảnh báo chi phí

### 8.1. Phân biệt budget và spending cap

**Alerts-only budget** dùng để quan sát và gửi thông báo khi đạt ngưỡng `CURRENT_SPEND` hoặc `FORECASTED_SPEND`. Nó **không tự động tắt VM, chặn API, đóng billing hoặc đảm bảo chi phí không vượt hạn mức**. Dữ liệu sử dụng và thông báo có độ trễ.

Google Cloud có thêm những loại **spend cap budget** cho một số dịch vụ/điều kiện được hỗ trợ. Đây là cơ chế **khác** và không được suy rằng cấu hình `google_billing_budget` alerts-only dưới đây sẽ tạo hard cap. Nếu dịch vụ hỗ trợ, đọc điều kiện spend cap riêng trước khi sử dụng.

### 8.2. Xác định billing account và project number

`foundation/budget.tf`:

~~~hcl
data "google_billing_account" "selected" {
  billing_account = var.billing_account_id
  lookup_projects = false
}
~~~

`google_project.sandbox.project_id` là ID dạng chuỗi; **budget_filter.projects** cần resource name theo **numeric project number**. Terraform xuất `google_project.sandbox.number`.

### 8.3. Budget tháng với cảnh báo 50%, 90%, 100% và dự báo

~~~hcl
resource "google_billing_budget" "sandbox" {
  billing_account = data.google_billing_account.selected.id
  display_name    = "orders-sandbox-monthly-budget"

  budget_filter {
    projects        = [format("projects/%s", google_project.sandbox.number)]
    calendar_period = "MONTH"
  }

  amount {
    specified_amount {
      currency_code = var.budget_currency
      units         = var.monthly_budget_units
    }
  }

  threshold_rules {
    threshold_percent = 0.50
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 0.90
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 1.00
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 1.00
    spend_basis       = "FORECASTED_SPEND"
  }
}
~~~

Giả sử tài khoản dùng USD và đặt `monthly_budget_units = "50"`, các ngưỡng có ý nghĩa:

| Rule | Mức tương đương | Ý nghĩa |
| --- | --- | --- |
| `CURRENT_SPEND = 0.50` | 25 USD | Chi tiêu thực tế đã đến khoảng 50% budget |
| `CURRENT_SPEND = 0.90` | 45 USD | Cần rà soát các resource đang chạy |
| `CURRENT_SPEND = 1.00` | 50 USD | Đã đến/ngang ngưỡng budget, **không tự chặn** việc sử dụng |
| `FORECASTED_SPEND = 1.00` | Dự báo đạt 50 USD trong kỳ | Cảnh báo sớm dựa trên forecast; không phải hóa đơn cuối kỳ |

Kỳ `MONTH` là một tháng lịch **theo ranh giới thời gian của Cloud Billing**, không tự tùy chỉnh theo múi giờ từng người dùng. Độ trễ báo cáo nghĩa là khi nhận alert, chi phí thực tế có thể đã cao hơn.

### 8.4. Ai nhận thông báo?

Khi không tùy chỉnh `all_updates_rule`, alerts-only budget có hành vi gửi email theo IAM recipients mặc định của Billing account. Để gửi cho **chủ sản phẩm hoặc FinOps** không có quyền Billing Admin, hãy cấu hình Cloud Monitoring notification channel được ủy quyền, hoặc Pub/Sub programmatic notifications. Các thông báo qua Pub/Sub có lịch cập nhật, không phải webhook thời gian thực tức thì.

Nếu chỉ cần monitor một project, có lựa chọn project-level recipients tùy quyền và cấu hình; không mặc định mọi người có role Viewer trong project đều được nhận thông báo.

**Không tự động tắt Billing khi đến 100%** trong lab này. Tắt Billing có thể làm gián đoạn ứng dụng và có hệ quả dữ liệu/dịch vụ, trong khi thông báo có thể trễ. Automation cost control phải có lựa chọn hành động an toàn, quyền hạn, idempotency, kiểm thử và runbook riêng.

### 8.5. Xử lý chi phí ngoài dự kiến

Khi dự báo vượt ngân sách:

1. Kiểm tra **Billing Reports**, chọn đúng billing account và project.
2. Nhóm theo service/SKU/region để tìm nguồn tăng.
3. Xác minh các resource vừa triển khai, load test, lưu lượng egress, logs và storage.
4. Có thể giảm min instances, dừng môi trường test hoặc xóa tài nguyên phát sinh ngoài dự kiến **theo thay đổi được phê duyệt**.
5. Chốt owner và kết quả điều tra; không thay ngân sách lên cao hơn để che cảnh báo.

Budget không thay thế **quotas**, **org policies**, giới hạn autoscaling hay cảnh báo tài nguyên. Các lớp đó phải được thiết kế cùng nhau.

## 9. Outputs để bàn giao landing zone

`foundation/outputs.tf`:

~~~hcl
output "folder_name" {
  value = google_folder.sandbox.name
}

output "project_id" {
  value = google_project.sandbox.project_id
}

output "project_number" {
  value = google_project.sandbox.number
}

output "vpc_self_link" {
  value = google_compute_network.orders.self_link
}

output "subnet_self_link" {
  value = google_compute_subnetwork.orders_app.self_link
}

output "runtime_service_account" {
  value = google_service_account.orders_runtime.email
}

output "budget_resource_name" {
  value = google_billing_budget.sandbox.name
}
~~~

Outputs cho biết chính xác tài nguyên đã provision để các nhóm ứng dụng lấy project, subnet và service account. Không đưa access token, private key, database password hoặc nhạy cảm tài chính vào outputs.

## 10. Khai báo giá trị cho sandbox

`environments/sandbox.tfvars`:

~~~hcl
organization_id        = "123456789012"
bootstrap_project_id   = "org-bootstrap-123"
billing_account_id     = "000000-000000-000000"
lab_project_id         = "orders-sandbox-12345"

region                 = "asia-southeast1"
subnet_cidr            = "10.42.0.0/24"

observer_group_email   = "lab-observers@example.com"
network_group_email    = "lab-network@example.com"

budget_currency        = "USD"
monthly_budget_units   = "50"
~~~

Các ID, email và số tiền trong ví dụ đều là **placeholders**. Trong dự án thực tế, phải xác nhận organization ID, billing account, CIDR, nhóm IAM và project ID duy nhất. Không commit thông tin xác thực vào `tfvars`. Nếu tổ chức coi billing account ID là thông tin nhạy cảm, lưu biến trong hệ thống quản lý cấu hình có kiểm soát.

## 11. Thực hiện theo các giai đoạn

### Giai đoạn A — chuẩn bị quyền và backend

1. Xác nhận người thực thi có quyền trên **organization**, **folder**, **billing account** và **state bucket**.
2. Bật API cần thiết ở bootstrap project.
3. Đọc effective Organization Policy của parent folder; chuẩn bị để hạn chế default network.
4. Kiểm tra Terraform provider version và backend GCS; không tạo local state thay thế backend production tùy tiện.
5. Đảm bảo quyền được cấp cho từng thao tác, không gộp mọi quyền vào service account runtime.

### Giai đoạn B — khởi tạo và kiểm tra mã

Từ thư mục `foundation/`:

~~~bash
terraform init
terraform fmt -recursive
terraform validate
terraform plan -var-file="../environments/sandbox.tfvars" -out="sandbox.tfplan"
terraform show "sandbox.tfplan"
~~~

Tại bước review plan, phải xác nhận:

- Folder được tạo dưới đúng organization.
- Policy có hiệu lực ở đúng folder trước khi project/Compute Engine API tạo default network.
- Project có billing account, labels và `deletion_policy=PREVENT`.
- IAM members là **Google Groups thật** và đúng roles; runtime SA không có Owner.
- VPC dùng custom mode, subnet CIDR không trùng và firewall không mở Internet rộng.
- Budget filter chỉ chứa **numeric number** của project sandbox; currency đúng với billing account.
- Không có hành động destroy hoặc replace không dự kiến.

**Triển khai theo lớp:** để policy có thời gian lan truyền, tổ chức nên áp dụng folder/policy ở một giai đoạn bootstrap riêng, xác minh effective policy, rồi mới tạo project và phần còn lại. Đừng dùng `-target` như cách tổ chức thường xuyên thay cho cấu trúc state/module rõ ràng.

### Giai đoạn C — apply được phê duyệt

Sau khi reviewer đã kiểm tra cùng plan file:

~~~bash
terraform apply "sandbox.tfplan"
~~~

**Chỉ chạy khi đã có quyền và phê duyệt chi phí.** Sau apply, nên chạy:

~~~bash
terraform output
terraform state list
terraform plan -var-file="../environments/sandbox.tfvars"
~~~

Nếu lần plan tiếp theo báo thay đổi không dự kiến, tìm nguyên nhân provider defaults, policy propagation, thao tác thủ công hoặc resource drift. Không tự động apply lần hai nếu có IAM/billing/destroy changes chưa được review.

## 12. Kiểm tra kết quả bằng Cloud Console và gcloud

### 12.1. Resource hierarchy và project

~~~bash
gcloud projects describe orders-sandbox-12345 \
  --format="json(projectId,projectNumber,name,parent,labels)"
~~~

Xác minh project nằm đúng folder và có labels phù hợp. Liên kết Billing nên được kiểm tra thêm trong **Cloud Billing → My projects** hoặc bằng API Billing với principal có quyền; lệnh mô tả project không chứng minh chính sách ngân sách.

### 12.2. API, network và subnet

~~~bash
gcloud services list \
  --enabled \
  --project=orders-sandbox-12345

gcloud compute networks describe orders-vpc \
  --project=orders-sandbox-12345

gcloud compute networks subnets describe orders-app \
  --project=orders-sandbox-12345 \
  --region=asia-southeast1

gcloud compute firewall-rules list \
  --project=orders-sandbox-12345
~~~

Kiểm tra network ở custom mode, subnet dùng `10.42.0.0/24`, `privateIpGoogleAccess` đang bật, và chỉ có firewall rules trong phạm vi đã thiết kế. Nếu default VPC xuất hiện, **không chỉ xóa nó rồi tuyên bố guardrail đạt**: xác minh effective `compute.skipDefaultNetworkCreation` và vòng đời API/project trước khi xử lý drift.

### 12.3. IAM

~~~bash
gcloud projects get-iam-policy orders-sandbox-12345 \
  --format=json
~~~

Đối chiếu bindings mong đợi. Kiểm tra `lab-observers` chỉ có `roles/logging.viewer`, `lab-network` chỉ có `roles/compute.networkViewer` từ module lab (các binding khác do organization hoặc quản trị viên có thể tồn tại), và `orders-runtime` không được cấp Editor/Owner.

Dùng **IAM Policy Troubleshooter** nếu cần đánh giá quyền hiệu lực với inherited policies, deny policies, IAM Conditions và các lớp khác. Một binding tồn tại trong project policy không chứng minh một principal có mọi quyền dưới organization.

### 12.4. Billing Budget

Mở **Billing → Budgets & alerts**, chọn đúng billing account và budget `orders-sandbox-monthly-budget`. Xác minh:

- Phạm vi là **duy nhất** project numeric ID được tạo.
- Kỳ tháng, currency và amount đúng.
- Có các mức 50%, 90%, 100% actual và 100% forecast.
- Người nhận cảnh báo hoặc Monitoring/Pub/Sub channel đúng.
- Không có yêu cầu tự ngắt dịch vụ nếu bài chỉ dùng alerts-only budget.

Không cần cố tạo chi phí thật đến 100% chỉ để thử alert. Kiểm thử cách hiển thị cấu hình và hướng dẫn chủ sản phẩm nhận thông báo; muốn diễn tập automation hãy dùng sự kiện giả hoặc kênh test riêng, không phá workload sản xuất.

## 13. Ma trận kiểm thử tích cực và tiêu cực

| Test | Điều kiện | Hành động | Kết quả mong đợi |
| --- | --- | --- | --- |
| HIER-01 | Đúng organization | Describe project/folder | Project thuộc folder sandbox |
| POLICY-01 | Policy đã lan truyền | Kiểm tra effective constraint | `skipDefaultNetworkCreation` được enforce |
| VPC-01 | API Compute đã bật | Describe `orders-vpc` | Custom mode, không auto subnets |
| VPC-02 | Subnet đã tạo | Describe subnet | Region, CIDR, Private Google Access đúng |
| FW-01 | Chưa có workload | Review firewall rules | Không có broad public SSH/RDP |
| FW-02 | Nếu thêm VM test tag `lab-app` | TCP `8080` từ subnet được phép | Được phép **nếu app lắng nghe** và route/other policies cho phép |
| FW-03 | VM test tương đương ngoài dải được phép | TCP `8080` | Bị chặn nếu không có rule khác nới quyền |
| IAM-01 | Runtime SA | Review project IAM | Không có Owner/Editor |
| IAM-02 | Group observer | Kiểm tra logging viewer role | Chỉ đọc logs phù hợp, không sửa network |
| IAM-03 | Group network | Kiểm tra network viewer role | Xem VPC nhưng không sửa firewall |
| BUDGET-01 | Billing account đúng | Xem budget filter | Một project và amount/currency đúng |
| BUDGET-02 | Có ngưỡng forecast | Xem threshold rules | Có 100% forecast và 50/90/100% actual |
| STATE-01 | Remote backend đã cấu hình | Terraform plan/re-init | Không tạo state phân tán/local ngoài ý muốn |
| DRIFT-01 | Sau apply | Chạy plan | Không có thay đổi ngoài dự kiến |

**Giới hạn kết quả:** vì MVP chưa có VM, `FW-02` và `FW-03` là bài mở rộng chứ không phải đã PASS. Việc rule hiện diện chưa chứng minh traffic đi đúng đường. Nếu chạy test thực tế, dùng VM nhỏ/không public IP trong project staging, thiết lập cleanup và đo thêm chi phí; không mở SSH từ `0.0.0.0/0`.

## 14. Giám sát và FinOps sau khi bàn giao

### 14.1. Bằng chứng nên lưu

Một báo cáo nghiệm thu có thể chứa:

~~~json
{
  "environment": "sandbox",
  "projectId": "orders-sandbox-12345",
  "network": "orders-vpc",
  "subnet": "orders-app",
  "subnetCidr": "10.42.0.0/24",
  "defaultNetworkPolicy": "enforced",
  "runtimeServiceAccount": "orders-runtime@orders-sandbox-12345.iam.gserviceaccount.com",
  "monthlyBudget": {
    "currency": "USD",
    "units": 50,
    "actualThresholds": [0.50, 0.90, 1.00],
    "forecastThreshold": 1.00
  },
  "deployment": "terraform",
  "status": "reviewed"
}
~~~

Đây là **định dạng báo cáo minh họa**, không phải kết quả thực tế của môi trường người học. Chỉ điền `enforced` và `reviewed` sau khi đã xác minh. Không đưa service account key, access token, password hoặc state file vào báo cáo nghiệm thu.

### 14.2. Quy trình xử lý khi chi phí tăng

- Chủ sản phẩm/FinOps nhận cảnh báo và đối chiếu Billing Reports theo service, SKU, region.
- Đội hạ tầng kiểm tra resource vừa tạo, log volume, egress và mức sử dụng.
- Đội bảo mật kiểm tra principal tạo resource và Cloud Audit Logs.
- Nếu cần tạm dừng lab, quyết định dừng resource **theo loại workload**, không tự tắt Billing account trên diện rộng.
- Sau xử lý, cập nhật ngân sách/alert threshold dựa trên thực tế và người chịu trách nhiệm.

Có thể mở rộng thêm **Cloud Billing export sang BigQuery**, báo cáo ngày/tuần, labels theo owner/cost center và alerting về unusual spend. Không nên tính chi phí riêng của project bằng cách cộng mọi khoản toàn billing account mà không lọc đúng project/credits.

### 14.3. SLI/SLO vận hành

Khi chưa có workload, chưa có SLO application latency. Thay vào đó, theo dõi các chỉ báo nền tảng:

- **Compliance:** % project có labels, budget, service identity và đúng folder.
- **Security:** số IAM bindings vượt quyền được duyệt; số default VPC trái policy.
- **Network hygiene:** số firewall ingress rules mở rộng không cần thiết.
- **Cost governance:** % project có budget và owner nhận alert; thời gian xử lý cảnh báo.
- **Automation quality:** tỷ lệ Terraform plan có drift hoặc thay đổi phá hủy không phê duyệt.

Khi có ứng dụng Java được triển khai, bổ sung logs/metrics/traces, availability, p95 latency và error budget theo nghiệp vụ.

## 15. Dọn dẹp và bảo vệ dữ liệu khi kết thúc lab

**Không chạy `terraform destroy` ngay trên project không chắc chắn là sandbox.** Trước khi hủy:

1. Xác nhận chính xác `lab_project_id`, folder, billing account và state backend; kiểm tra state file chỉ chứa resource của lab.
2. Đảm bảo không có dữ liệu, secret, VM, disk, IP, database, backup hoặc workload vẫn cần giữ.
3. Chạy `terraform plan -destroy -var-file="../environments/sandbox.tfvars"`; xem đầy đủ danh sách tác động.
4. Do `google_project.sandbox.deletion_policy = "PREVENT"`, Terraform sẽ chặn xóa project. Muốn xóa **project lab**, phải có change approval riêng để đổi policy sang `DELETE` (hoặc xử lý project theo chính sách organization), sau đó review lại kế hoạch destroy.
5. Nếu chỉ muốn ngừng Terraform quản lý project mà **không xóa project**, cần cân nhắc cơ chế `ABANDON` với phê duyệt, không đánh đồng với xóa resource.
6. Đợi resource hoàn tất xóa/khôi phục và kiểm tra chi phí còn lại; backup retention, logging và billing export có thể tiếp tục phát sinh phí hoặc duy trì dữ liệu.
7. Giữ audit evidence và đóng budget nếu không còn project được theo dõi. Không xóa bootstrap state bucket dùng chung cho môi trường khác.

Thứ tự destroy có thể bị ràng buộc bởi IAM/policy, project liens và deletion protection. Nếu lệnh trả lỗi, đừng gỡ những cơ chế bảo vệ của organization chỉ để xóa nhanh; chuyển cho owner có thẩm quyền xử lý.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Tạo folder `403` | Thiếu Folder Creator trên parent | Cấp quyền ở đúng scope hoặc dùng folder được admin cấp sẵn |
| Không tạo được project | Thiếu Project Creator, ID trùng hoặc policy chặn | Kiểm tra organization/folder, project ID và effective policy |
| Gắn billing thất bại | Thiếu Billing User hoặc quyền quản lý billing của project | Xem Billing IAM và trạng thái billing account |
| `google_org_policy_policy` bị từ chối | Thiếu Org Policy Admin hoặc API chưa được bật | Quản trị viên áp policy trước, xác minh inheritance |
| Project vẫn có `default` VPC | Constraint chưa có hiệu lực khi project/API tạo mạng | Đánh giá policy propagation và lịch sử tạo project, sửa drift có kế hoạch |
| VPC/subnet báo lỗi | Compute API chưa bật, CIDR đè lên dải khác hoặc quota | Kiểm tra service enablement, region và quy hoạch IP |
| Runtime SA được xem là có quyền quá rộng | Có IAM role kế thừa ở folder/organization | Dùng Policy Troubleshooter, rà soát inherited bindings |
| Firewall `allow` có nhưng TCP không thông | Chưa có VM/tag/app listener, route hoặc rule khác chặn | Không coi policy config test là integration test |
| `google_billing_budget` trả `403` với user ADC | Thiếu `billing_project`, quota override hoặc quyền Billing Costs Manager | Kiểm tra provider config, `serviceusage.services.use` và billing IAM |
| Budget tạo nhưng không gửi email mong đợi | Recipient không thuộc nhóm mặc định/chưa có Monitoring channel | Xem notification rules, billing account recipients |
| Chi phí vẫn tăng sau 100% | Alerts-only budget không dừng dịch vụ, reporting delay | Theo dõi Billing Reports; dùng controls khác phù hợp |
| `terraform init` lỗi | Bucket backend chưa tồn tại hoặc thiếu IAM | Sửa bootstrap state bucket/credentials, không để state phân tán |
| `terraform destroy` bị chặn | Project deletion policy `PREVENT` | Đây là guardrail mong đợi; xin phê duyệt rồi xử lý lab |
| Plan có unexpected IAM changes | Một state khác đang quản lý IAM policy hoặc có drift | Review resource authoritative/member, không apply thiếu kiểm tra |

## 17. Checklist nghiệm thu dự án

- [ ] Organization, folder, billing account, bootstrap project và GCS state bucket đã có.
- [ ] Terraform execution identity chỉ có quyền cần thiết cho bootstrap/foundation; không dùng key JSON lâu dài.
- [ ] Folder sandbox tạo đúng parent; project ID duy nhất và có labels owner/cost area.
- [ ] Organization Policy chặn tạo default network đã được xác minh có hiệu lực trước project provisioning.
- [ ] Project liên kết đúng billing account và không bị Terraform xóa nhầm nhờ `deletion_policy=PREVENT`.
- [ ] Service APIs đã bật; không bật dịch vụ không cần thiết.
- [ ] Tạo service account `orders-runtime` riêng, không có Owner/Editor.
- [ ] Nhóm observer và network nhận role tối thiểu, không có quyền IAM hoặc Billing ngoài yêu cầu.
- [ ] Custom-mode VPC và subnet đúng region/CIDR, không chồng lấn.
- [ ] Bật Private Google Access trên subnet và hiểu đây không phải IAM.
- [ ] Không có firewall ingress public SSH/RDP; rule `8080` chỉ áp dụng cho tagged VM lab.
- [ ] Budget có scope **numeric project number**, đúng tiền tệ, kỳ tháng.
- [ ] Các thresholds actual 50/90/100% và forecast 100% được xác minh.
- [ ] Người sở hữu ngân sách biết **alert budget không phải spending cap**.
- [ ] Terraform plan đã được review; lần plan sau apply không có drift ngoài dự kiến.
- [ ] Đã lưu thông tin bàn giao, owner, alert recipients và hướng dẫn xử lý sự cố.
- [ ] Có quy trình decommission với phê duyệt và bảo vệ bootstrap state.

## Tài liệu tham khảo

- [Google Cloud landing zones](https://docs.cloud.google.com/architecture/landing-zones) — thành phần nền tảng và các lựa chọn kiến trúc.
- [Google Cloud resource hierarchy](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy) — organization, folders, projects và chính sách kế thừa.
- [Organization Policy: Restrict resource configurations](https://docs.cloud.google.com/resource-manager/docs/organization-policy/overview) — constraints và effective policies.
- [Compute Engine VPC networks](https://docs.cloud.google.com/vpc/docs/vpc) — custom/auto-mode VPC, routes, firewall behavior.
- [Private Google Access](https://docs.cloud.google.com/vpc/docs/private-google-access) — điều kiện truy cập Google APIs từ VM không có external IP.
- [Cloud Billing: Create budgets and alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets) — alerts-only budget, scope, notification delays và spend caps riêng.
- [Cloud Billing: Programmatic budget notifications](https://docs.cloud.google.com/billing/docs/how-to/notify) — Pub/Sub notifications và tích hợp cost automation.
- [Terraform google_project](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project) — project, folder, billing, labels và deletion policy.
- [Terraform google_org_policy_policy](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/org_policy_policy) — policy boolean cho folder/project.
- [Terraform google_project_iam_member](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project_iam) — non-authoritative IAM bindings.
- [Terraform google_compute_network](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_network) — custom VPC.
- [Terraform google_compute_subnetwork](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_subnetwork) — CIDR và Private Google Access.
- [Terraform google_compute_firewall](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_firewall) — source ranges, target tags và ingress/egress.
- [Terraform google_billing_budget](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/billing_budget) — monthly budget filter, numeric project number và alert thresholds.
- [Terraform GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs) — remote state, locking và backend authentication.

