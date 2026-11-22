# Tách môi trường, tham số hóa và quản lý phụ thuộc

Một cấu hình Terraform thường bắt đầu từ một môi trường thử nghiệm. Khi ứng dụng phát triển, cùng một hạ tầng cần được triển khai ở dev, staging và production. Nếu sao chép toàn bộ file cấu hình cho từng môi trường, các bản sao dễ lệch nhau; nếu dùng chung một state và một bộ quyền, một thao tác nhầm có thể tác động đến production.

Thiết kế tốt cần giải quyết ba việc cùng lúc: **tách ranh giới môi trường**, **tái sử dụng cấu hình bằng module và biến**, và **khai báo đúng quan hệ phụ thuộc** để Terraform lập kế hoạch theo thứ tự an toàn. Trên Google Cloud, mô hình thường dùng là một thư mục root module cho mỗi môi trường, module dùng chung nằm ở thư mục riêng, và mỗi môi trường có backend/state cùng quyền truy cập phù hợp.

Trong module **CLOUD_PROVIDERS_GCP**, cách tổ chức này giúp triển khai nhất quán từ project, IAM, VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Đội vận hành có thể thử thay đổi ở dev, xác minh ở staging rồi đưa cùng phiên bản module lên production với tham số và quyền riêng.

Sau bài học, bạn có thể:

- Chọn ranh giới môi trường phù hợp với project và quyền IAM trên Google Cloud.
- Tổ chức root module theo môi trường và module tái sử dụng.
- Tham số hóa project, region, tên tài nguyên và cấu hình theo môi trường.
- Quản lý biến, giá trị mặc định, validation và dữ liệu nhạy cảm.
- Thiết kế backend/state độc lập cho từng môi trường.
- Phân biệt dependency ngầm, dependency tường minh và phụ thuộc giữa các root module.
- Xây dựng quy trình plan, review, apply và nâng cấp module có kiểm soát.

## 1. Vì sao phải tách môi trường?

Các môi trường có mục tiêu và mức độ rủi ro khác nhau:

| Môi trường | Mục tiêu | Đặc điểm cấu hình thường gặp |
|---|---|---|
| Dev | Phát triển nhanh, thử tính năng | Tài nguyên nhỏ, dữ liệu thử nghiệm, có thể tạo/xóa thường xuyên |
| Staging / QA | Kiểm thử tích hợp và kiểm tra trước phát hành | Gần production về cấu trúc, dữ liệu đã được làm sạch |
| Production | Phục vụ người dùng thật | Tính sẵn sàng cao, kiểm soát thay đổi, backup, logging và IAM chặt chẽ |

Tách môi trường không chỉ là đổi hậu tố tên tài nguyên. Ranh giới nên thể hiện trong:

- **Google Cloud project**: mỗi môi trường có project riêng, hoặc ít nhất có ranh giới project rõ ràng theo ứng dụng và miền trách nhiệm.
- **IAM và danh tính triển khai**: service account hoặc workload identity riêng cho từng môi trường; pipeline dev không có quyền apply production.
- **Terraform state**: mỗi môi trường có state riêng để plan và apply chỉ tác động đến tập tài nguyên được giao.
- **Backend và quyền truy cập**: state production có quyền đọc/ghi giới hạn hơn state dev.
- **Cấu hình và dữ liệu**: project ID, region, sizing, domain, retention, số replica và chính sách backup được đặt theo môi trường.

Ví dụ, tổ chức có thể dùng project ID là app-dev, app-staging và app-prod. Cách đặt tên này giúp nhận diện mục tiêu triển khai ngay từ lệnh CLI, log và IAM policy. Trong hệ thống lớn, Shared VPC hoặc project mạng dùng chung có thể được quản lý riêng; quyền kết nối vào tài nguyên dùng chung cần được thiết kế rõ ràng.

## 2. Chọn cấu trúc Terraform cho nhiều môi trường

### 2.1. Mô hình modules và environments

Google Cloud khuyến nghị tách phần cấu hình dùng chung vào thư mục modules/ và tạo root configuration riêng cho từng môi trường trong environments/.

Ví dụ cấu trúc cho một dịch vụ mạng:

~~~text
network-service/
├── modules/
│   └── vpc/
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
└── environments/
    ├── dev/
    │   ├── backend.tf
    │   ├── main.tf
    │   ├── variables.tf
    │   └── dev.tfvars
    ├── staging/
    │   ├── backend.tf
    │   ├── main.tf
    │   ├── variables.tf
    │   └── staging.tfvars
    └── prod/
        ├── backend.tf
        ├── main.tf
        ├── variables.tf
        └── prod.tfvars
~~~

Mỗi thư mục environments/<env> là một **root module**: nơi chạy terraform init, plan và apply. Root module gọi module dùng chung bằng đường dẫn tương đối. File .tfvars cung cấp các giá trị riêng của môi trường.

Module vpc chỉ mô tả cách tạo VPC và nhận các tham số như project ID, tên mạng, chế độ subnet. Root module quyết định dùng module đó ở project nào, region nào và với giá trị nào. Nhờ vậy, logic tạo VPC được viết một lần nhưng có thể triển khai ở nhiều project.

Không nên gom mọi ứng dụng và mọi lớp hạ tầng vào một root module lớn. Google Cloud đưa ra quy tắc thực hành là giữ mỗi state dưới 100 resource, lý tưởng chỉ vài chục resource. Tách theo ranh giới ứng dụng hoặc thành phần giúp plan nhanh hơn, giảm blast radius và giao quyền sở hữu cho từng nhóm.

### 2.2. Vì sao không dùng CLI workspace làm ranh giới bảo mật?

Terraform CLI workspace là nhiều state riêng bên trong cùng một working directory và backend. Khi đổi workspace, Terraform dùng state khác, nhưng cấu hình, backend và cơ chế xác thực vẫn thuộc cùng working directory.

Workspace hữu ích khi cần nhiều bản triển khai tương tự, dùng cùng cấu hình và cùng quyền truy cập. Tuy nhiên, workspace không phù hợp khi môi trường cần credentials hoặc access control riêng. Một người có quyền truy cập backend chung có thể chuyển workspace và thao tác trên state khác.

Với Google Cloud, hãy ưu tiên thư mục root module riêng cho dev, staging và prod, mỗi thư mục dùng backend/state độc lập và chỉ định danh tính triển khai có quyền trên project tương ứng. Mỗi thư mục thường dùng workspace mặc định default.

| Tiêu chí | Thư mục môi trường riêng | CLI workspace |
|---|---|---|
| Root configuration | Mỗi môi trường có thư mục riêng | Dùng chung working directory |
| Backend | Có thể cấu hình riêng | Dùng chung backend trong working directory |
| Quyền truy cập state | Có thể tách theo bucket hoặc backend | Khó tách quyền theo workspace nếu cùng backend |
| Cấu hình môi trường | File và biến riêng | Thường dựa vào biến và terraform.workspace |
| Phù hợp | Môi trường cần ranh giới IAM, project và blast radius rõ | Nhiều bản triển khai tương tự, cùng quyền và cùng vòng đời |

Đừng dùng điều kiện terraform.workspace == "prod" làm lớp bảo vệ duy nhất cho production. Quyền IAM ở Google Cloud và quyền ghi state mới là ranh giới thực tế.

## 3. Tạo module dùng chung

Một module nên có trách nhiệm rõ ràng, giao diện đầu vào nhỏ và output có ý nghĩa. Ví dụ module VPC:

**modules/vpc/main.tf**

~~~hcl
resource "google_compute_network" "this" {
  project                 = var.project_id
  name                    = var.network_name
  auto_create_subnetworks = var.auto_create_subnetworks
  routing_mode            = "REGIONAL"
}
~~~

**modules/vpc/variables.tf**

~~~hcl
variable "project_id" {
  description = "Google Cloud project chứa VPC."
  type        = string
  nullable    = false
}

variable "network_name" {
  description = "Tên VPC trong project."
  type        = string
  nullable    = false
}

variable "auto_create_subnetworks" {
  description = "Có tự tạo subnet theo region hay không."
  type        = bool
  default     = false
}
~~~

**modules/vpc/outputs.tf**

~~~hcl
output "network_self_link" {
  description = "Self link của VPC được tạo."
  value       = google_compute_network.this.self_link
}

output "network_name" {
  description = "Tên VPC."
  value       = google_compute_network.this.name
}
~~~

Module không nên cố đoán môi trường bằng tên thư mục, tên branch hoặc biến toàn cục. Hãy nhận giá trị cần thiết qua input variable. Các giá trị chung và ổn định có thể đặt mặc định trong module; giá trị thay đổi theo project hoặc môi trường nên là tham số bắt buộc.

Nếu một module cần nhiều tài nguyên cùng loại, dùng for_each với key ổn định để Terraform theo dõi từng instance. Key nên mang ý nghĩa nghiệp vụ như web, private hoặc database; tránh tạo key ngẫu nhiên. Với danh sách có thể thay đổi thứ tự, for_each thường dễ duy trì danh tính resource hơn count dựa trên index.

## 4. Khai báo provider và root module cho từng môi trường

Mỗi root module khai báo phiên bản Terraform và provider cần thiết. Ví dụ dưới đây dùng Google provider nhánh 8.12; trong dự án thật, chọn phiên bản tương thích với resource đang dùng, khóa phiên bản trong .terraform.lock.hcl và nâng cấp có kiểm soát.

**environments/dev/main.tf**

~~~hcl
terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.12"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "compute" {
  project            = var.project_id
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

module "vpc" {
  source = "../../modules/vpc"

  project_id              = var.project_id
  network_name            = var.network_name
  auto_create_subnetworks = false

  # API phải được bật trước khi module tạo VPC.
  # Module không tham chiếu trực tiếp thuộc tính của resource API này.
  depends_on = [google_project_service.compute]
}
~~~

**environments/dev/variables.tf**

~~~hcl
variable "project_id" {
  description = "Project ID dành cho môi trường dev."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id phải có 6-30 ký tự, bắt đầu bằng chữ thường và chỉ chứa chữ thường, số hoặc dấu gạch ngang."
  }
}

variable "environment" {
  description = "Tên môi trường triển khai."
  type        = string
  nullable    = false

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment phải là dev, staging hoặc prod."
  }
}

variable "region" {
  description = "Region triển khai tài nguyên."
  type        = string
  default     = "asia-southeast1"
}

variable "network_name" {
  description = "Tên VPC của môi trường."
  type        = string
  nullable    = false
}
~~~

**environments/dev/dev.tfvars**

~~~hcl
project_id   = "company-app-dev"
environment  = "dev"
region       = "asia-southeast1"
network_name = "app-dev-vpc"
~~~

Ở staging và production, root module gọi cùng module ../../modules/vpc nhưng sử dụng project_id, network_name, backend và danh tính triển khai riêng. Các thư mục có thể dùng cùng nội dung variables.tf; mỗi môi trường có file .tfvars riêng. Nếu cần khác biệt lớn về kiến trúc, hãy tạo module hoặc root module chuyên biệt thay vì rải nhiều điều kiện theo environment trong một cấu hình.

Lưu ý: ví dụ bật Compute Engine API minh họa một dependency ở cấp module. Trong môi trường thật, API cần bật có thể gồm compute.googleapis.com, container.googleapis.com, run.googleapis.com hoặc các API khác tùy dịch vụ. Tổ chức danh sách API trong module nền tảng phù hợp với quyền và vòng đời của project.

## 5. Tham số hóa bằng variables, locals và tfvars

### 5.1. Input variables

Input variable là giao diện để root module hoặc module cha truyền giá trị cho module con. Một biến nên khai báo:

- type: kiểu dữ liệu như string, number, bool, list(string), set(string), map(string) hoặc object({...}).
- description: mục đích và định dạng giá trị.
- default: giá trị mặc định nếu thực sự an toàn và phù hợp cho mọi caller.
- validation: điều kiện hợp lệ để chặn cấu hình sai trước khi apply.
- sensitive: che giá trị trong output CLI và một số log.
- nullable: quyết định có cho phép giá trị null hay không.

Ví dụ kiểm tra region và environment:

~~~hcl
variable "region" {
  description = "Region triển khai workload."
  type        = string
  default     = "asia-southeast1"

  validation {
    condition = contains(
      ["asia-southeast1", "asia-east1", "us-central1"],
      var.region
    )
    error_message = "Region chưa nằm trong danh sách được phép."
  }
}
~~~

Validation nên kiểm tra quy tắc thuộc phạm vi module, chẳng hạn danh sách region được tổ chức phê duyệt, số replica nằm trong giới hạn hoặc tên tài nguyên có định dạng hợp lệ. Không lặp lại quá nhiều validation cho các điều kiện đã được provider hoặc Google Cloud kiểm tra.

Biểu thức project ID ở trên kiểm tra định dạng cơ bản. Google Cloud còn áp dụng các quy tắc đặt tên và từ bị dành riêng; việc vượt qua validation trong Terraform không thay thế bước kiểm tra khi tạo project.

### 5.2. Locals cho giá trị dẫn xuất

locals dùng để đặt tên cho biểu thức được tính từ input. Nó không phải biến đầu vào và không có cơ chế override từ CLI:

~~~hcl
locals {
  common_labels = {
    environment = var.environment
    managed_by  = "terraform"
    service     = "checkout"
  }
}
~~~

Dùng locals để chuẩn hóa labels, tên tài nguyên hoặc giá trị tính toán dùng nhiều lần. Đặt các khác biệt theo môi trường ở input variables và file .tfvars; tránh sao chép cùng một hằng số ở nhiều resource.

### 5.3. File tfvars và độ ưu tiên

File .tfvars giúp lưu các giá trị cấu hình theo môi trường. Terraform CLI tự động nạp terraform.tfvars, terraform.tfvars.json và các file *.auto.tfvars hoặc *.auto.tfvars.json. Có thể truyền file cụ thể bằng -var-file.

Khi cùng một biến nhận nhiều giá trị, thứ tự ưu tiên thông thường từ cao xuống thấp là:

1. Các tùy chọn -var và -var-file trên dòng lệnh, theo thứ tự được truyền.
2. Các file *.auto.tfvars và *.auto.tfvars.json, theo thứ tự tên từ điển.
3. terraform.tfvars.json.
4. terraform.tfvars.
5. Biến môi trường có tiền tố TF_VAR_.
6. Giá trị default trong khai báo variable.

Ví dụ chạy plan cho dev:

~~~bash
terraform plan -var-file="dev.tfvars"
~~~

Pipeline có thể truyền file biến rõ ràng để tránh vô tình dùng nhầm cấu hình của môi trường khác. Khi dùng CI/CD, biến có thể được inject qua TF_VAR_project_id, TF_VAR_region hoặc hệ thống quản lý biến của pipeline. Không truyền secret bằng command line nếu lệnh có thể bị ghi vào shell history hoặc log.

## 6. Quản lý dữ liệu nhạy cảm và xác thực

Đánh dấu sensitive = true giúp Terraform che giá trị khi hiển thị, nhưng **không tự loại bỏ giá trị khỏi state hoặc plan file**. Nếu resource nhận password hoặc secret qua một argument được lưu, giá trị đó có thể vẫn nằm trong state.

Ví dụ khai báo một biến nhạy cảm:

~~~hcl
variable "database_password" {
  description = "Mật khẩu database được cấp từ secret manager."
  type        = string
  sensitive   = true
}
~~~

Quy tắc vận hành:

- Không commit file chứa password, API token hoặc private key vào Git.
- Không lưu service account key JSON trong terraform.tfvars.
- Ưu tiên Application Default Credentials khi chạy local; nhà phát triển có thể xác thực bằng gcloud auth application-default login.
- Trong CI/CD, dùng Workload Identity Federation hoặc cơ chế impersonate service account thay vì key dài hạn.
- Dùng Secret Manager để quản lý secret ứng dụng. Chỉ đưa secret vào Terraform khi thật sự cần thiết và hiểu rõ việc lưu secret trong state.
- Bảo vệ quyền đọc state như quyền đọc dữ liệu nhạy cảm; hạn chế người và pipeline có thể truy cập bucket state.

Terraform từ phiên bản 1.10 hỗ trợ ephemeral = true cho một số input/output và ngữ cảnh hợp lệ. Giá trị ephemeral không được ghi vào state hoặc plan file, phù hợp với token ngắn hạn. Tuy nhiên, nó có giới hạn nơi được tham chiếu và không thể dùng tùy ý cho mọi argument của provider. Hãy kiểm tra tài liệu resource/provider trước khi áp dụng. sensitive và ephemeral giải quyết hai vấn đề khác nhau: che khi hiển thị và không lưu vào state/plan.

## 7. Tách backend và state trên Google Cloud

Terraform state lưu mapping giữa resource trong cấu hình và đối tượng thật trên Google Cloud. Nếu dev và prod dùng chung state, một plan có thể thay đổi hoặc xóa nhầm tài nguyên của môi trường khác. Vì vậy, mỗi root module môi trường cần một state độc lập.

### 7.1. Dùng Cloud Storage backend

GCS backend lưu state thành object trong bucket Cloud Storage. Bucket phải được tạo trước khi Terraform khởi tạo backend. Backend GCS hỗ trợ state locking để ngăn nhiều tiến trình ghi state đồng thời; Google/HashiCorp khuyến nghị bật Object Versioning để phục hồi state khi có xóa nhầm hoặc lỗi thao tác.

**environments/dev/backend.tf**

~~~hcl
terraform {
  backend "gcs" {
    bucket = "company-terraform-state-dev"
    prefix = "network-service"
  }
}
~~~

**environments/prod/backend.tf**

~~~hcl
terraform {
  backend "gcs" {
    bucket = "company-terraform-state-prod"
    prefix = "network-service"
  }
}
~~~

Staging có backend riêng theo cùng mẫu. Dùng bucket riêng cho production khi cần IAM, retention, encryption hoặc quản trị truy cập độc lập. Nếu dùng chung bucket, mỗi môi trường vẫn cần prefix riêng; tuy nhiên quyền IAM ở cấp bucket có thể không đủ chi tiết để tạo ranh giới như mong muốn.

Backend config được xử lý trong giai đoạn terraform init; không thể tham chiếu input variable như var.environment trong block backend. Vì thế, hãy khai báo backend riêng cho từng root module hoặc truyền cấu hình backend tĩnh qua -backend-config.

Tạo bucket state bằng một quy trình bootstrap độc lập. Không nên để một cấu hình dùng chính bucket state của nó làm tài nguyên cần tạo, vì backend phải tồn tại trước khi terraform init có thể lưu state.

### 7.2. Bảo vệ state

- Bật Object Versioning trên bucket để có thể phục hồi phiên bản state trước.
- Bật uniform bucket-level access và chỉ cấp IAM cần thiết cho pipeline/nhóm vận hành.
- Không công khai bucket và không commit terraform.tfstate, backup state hoặc plan artifact vào Git.
- Sử dụng state locking; không dùng -lock=false để né lock đang được tiến trình khác giữ.
- Không chỉnh sửa JSON state trực tiếp. Khi cần thay đổi binding, dùng các lệnh terraform state phù hợp và review trước.
- Xem state như dữ liệu nhạy cảm vì nó có thể chứa giá trị thuộc tính và secret.

Khởi tạo backend:

~~~bash
cd environments/dev
terraform init
~~~

Nếu chuyển backend của một cấu hình đang quản lý tài nguyên, cần xem xét migration state bằng terraform init -migrate-state. Không đổi bucket hoặc prefix một cách tùy tiện rồi chạy apply, vì Terraform có thể khởi tạo một state rỗng và đề xuất tạo lại các tài nguyên đã tồn tại.

## 8. Quản lý dependency trong Terraform

Terraform xây dựng dependency graph từ các tham chiếu trong cấu hình. Các resource không phụ thuộc nhau có thể được xử lý song song; các resource có quan hệ phụ thuộc sẽ được thực hiện theo thứ tự phù hợp.

### 8.1. Dependency ngầm qua reference

Khi một resource dùng thuộc tính của resource khác, Terraform tự suy ra dependency:

~~~hcl
resource "google_compute_network" "app" {
  project                 = var.project_id
  name                    = "app-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "private" {
  project       = var.project_id
  name          = "app-private"
  region        = var.region
  network       = google_compute_network.app.id
  ip_cidr_range = "10.20.0.0/20"
}
~~~

google_compute_subnetwork.private tham chiếu google_compute_network.app.id, do đó Terraform biết VPC phải tồn tại trước subnet. Đây là cách ưu tiên vì dependency thể hiện trực tiếp qua dữ liệu mà resource cần.

### 8.2. Dependency tường minh bằng depends_on

Đôi khi có quan hệ vận hành nhưng không có thuộc tính nào được tham chiếu. Ví dụ, module VPC cần Compute Engine API được bật trước, nhưng module chỉ nhận project_id và network_name, không đọc output từ resource google_project_service.

Trong trường hợp đó có thể khai báo:

~~~hcl
resource "google_project_service" "compute" {
  project            = var.project_id
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

module "vpc" {
  source       = "../../modules/vpc"
  project_id   = var.project_id
  network_name = var.network_name

  depends_on = [google_project_service.compute]
}
~~~

depends_on hỗ trợ trong resource và module block, nhận danh sách tham chiếu resource hoặc module trong cùng calling module. Dùng nó khi có dependency ẩn mà Terraform không thể suy ra. Tránh thêm depends_on cho mọi resource chỉ để ép chạy tuần tự: điều này làm dependency graph rộng, plan khó đọc và có thể khiến Terraform phải chờ các giá trị chưa xác định.

### 8.3. Dependency giữa các module

Khi module con sử dụng output của module khác, Terraform tự suy ra thứ tự:

~~~hcl
module "vpc" {
  source       = "../../modules/vpc"
  project_id   = var.project_id
  network_name = var.network_name
}

module "private_service" {
  source     = "../../modules/private-service"
  project_id = var.project_id
  network_id = module.vpc.network_self_link
}
~~~

module.private_service nhận output từ module.vpc, nên module VPC được xử lý trước khi thành phần phụ thuộc cần output đó. Thiết kế module bằng input/output rõ ràng giúp dependency graph tự nhiên và dễ kiểm tra.

## 9. Phụ thuộc giữa các root module và chia sẻ output

Hai root module là hai cấu hình độc lập. Terraform không tạo một dependency graph chung giữa chúng. Ví dụ, network có state riêng và application có state riêng. Nếu ứng dụng cần network ID, có thể dùng remote state để đọc output đã công bố:

~~~hcl
data "terraform_remote_state" "network" {
  backend = "gcs"

  config = {
    bucket = "company-terraform-state-dev"
    prefix = "network-service"
  }
}

module "application" {
  source = "../../modules/application"

  project_id = var.project_id
  network_id = data.terraform_remote_state.network.outputs.network_self_link
}
~~~

Google Cloud khuyến nghị Cloud Storage hoặc Terraform Enterprise làm backend khi cần chia sẻ thông tin giữa các root module. Dùng remote state cho các output có hợp đồng rõ ràng, chẳng hạn network self link, subnet ID hoặc service account email.

Consumer phải đọc state của đúng môi trường. Root module production cần tham chiếu backend/state production; không dùng output từ state dev để cấu hình tài nguyên production.

Có hai điều cần chú ý:

1. Remote state chỉ cung cấp dữ liệu; nó không tự điều phối thứ tự apply giữa hai root module. Pipeline phải triển khai network trước, sau đó mới chạy application.
2. Người đọc remote state cần quyền đọc state snapshot. Vì state có thể chứa nhiều dữ liệu hơn các output được tham chiếu, không đưa secret vào output và cấp quyền truy cập state theo nguyên tắc tối thiểu.

Nếu cần truy vấn một tài nguyên được tạo thủ công hoặc do hệ thống khác quản lý, hãy dùng data source của Google provider. Tránh dùng data source để tra cứu tài nguyên vốn do một Terraform root module khác quản lý, vì việc phụ thuộc vào tên và cấu trúc resource có thể bị phá vỡ khi cấu hình nguồn thay đổi. Với tài nguyên Terraform ở cấu hình khác, ưu tiên một output contract qua remote state hoặc một cơ chế chia sẻ cấu hình có quản trị.

## 10. Quản lý phiên bản provider và module

Terraform cần provider plugin để giao tiếp với Google Cloud. Khai báo provider trong required_providers:

~~~hcl
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.12"
    }
  }
}
~~~

Version constraint xác định phạm vi phiên bản có thể cài đặt. Sau terraform init, Terraform ghi lại phiên bản provider đã chọn cùng checksum vào .terraform.lock.hcl. Commit lock file này vào Git để máy của nhà phát triển và pipeline cài cùng phiên bản provider. Chỉ cập nhật lock file có chủ đích, ví dụ sau khi xem xét thay đổi và chạy kiểm thử với terraform init -upgrade.

Với module từ Terraform Registry, khai báo version để khóa module ở một bản tương thích. Với module lấy từ Git, dùng tag hoặc commit ref ổn định. Với module local, Terraform đọc trực tiếp source tại đường dẫn đó; tham số version không áp dụng cho local module. Lock file hiện theo dõi provider dependency, không khóa phiên bản module remote; vì vậy cần pin version của module remote trong module block.

Ví dụ module Registry:

~~~hcl
module "network" {
  source  = "terraform-google-modules/network/google"
  version = "18.3.1"

  project_id   = var.project_id
  network_name = "app-network"
  routing_mode = "REGIONAL"

  subnets = [
    {
      subnet_name           = "app-private"
      subnet_ip             = "10.20.0.0/20"
      subnet_region         = var.region
      subnet_private_access = "true"
    }
  ]
}
~~~

Chọn phiên bản module có hỗ trợ provider và Terraform version mà tổ chức đang dùng. Khi nâng cấp, đọc changelog, chạy plan trong dev, kiểm thử ở staging và chỉ sau đó cập nhật version production.

## 11. Quy trình triển khai qua dev, staging và production

Một pipeline có kiểm soát có thể triển khai theo trình tự:

~~~mermaid
flowchart TD
    A["Thay đổi module / biến trong Git"] --> B["Format và validate"]
    B --> C["Plan với backend + tfvars dev"]
    C --> D["Review diff và apply dev"]
    D --> E["Kiểm thử tích hợp ở staging"]
    E --> F["Plan với state và quyền staging"]
    F --> G["Review và apply staging"]
    G --> H["Plan production"]
    H --> I["Infrastructure owner phê duyệt"]
    I --> J["Apply saved plan bằng danh tính prod"]
    J --> K["Theo dõi và lưu kết quả triển khai"]
~~~

Lệnh tham khảo khi chạy trong từng thư mục môi trường:

~~~bash
terraform fmt -check
terraform init
terraform validate
terraform plan -var-file="dev.tfvars" -out="dev.tfplan"
terraform apply "dev.tfplan"
~~~

Ở staging và production, thay file biến tương ứng và dùng backend của môi trường đó. terraform plan cần được review để nhận diện resource sẽ tạo, cập nhật hoặc destroy. Saved plan phải được bảo vệ vì có thể chứa dữ liệu nhạy cảm. Không dùng -auto-approve cho production nếu quy trình yêu cầu người sở hữu hạ tầng phê duyệt.

Pipeline nên:

- Chạy từ đúng root module và chọn đúng project.
- Xác thực bằng service account hoặc Workload Identity Federation riêng cho môi trường.
- Không dùng credentials production trong job dev.
- Lưu log plan/apply, commit ID, module version và người phê duyệt.
- Dừng nếu validation, policy check hoặc review plan không đạt.
- Chạy các root module theo dependency order đã định nghĩa trong pipeline.

## 12. Những lỗi thường gặp khi tách môi trường

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dev và prod dùng chung state | Plan ở môi trường này có thể tác động tài nguyên môi trường kia | Tách root module và backend/state |
| Chỉ đổi tên resource theo terraform.workspace | Quyền backend và credentials vẫn dùng chung | Dùng thư mục, project, IAM identity và state riêng |
| Copy toàn bộ cấu hình thành nhiều bản | Các môi trường lệch logic sau một thời gian | Đưa phần chung vào module và truyền tham số |
| Module có quá nhiều biến đặc thù | Giao diện khó hiểu, nhiều nhánh điều kiện | Giữ input nhỏ, có kiểu dữ liệu và validation |
| Ghi secret trong tfvars và commit Git | Lộ thông tin xác thực | Secret Manager, ADC, WIF và secret store của CI/CD |
| Cho rằng sensitive không lưu state | Secret vẫn có thể nằm trong state | Bảo vệ state; dùng ephemeral khi ngữ cảnh cho phép |
| Dùng depends_on tràn lan | Graph quá chặt, plan khó hiểu và chậm | Ưu tiên tham chiếu output/attribute; chỉ khai báo dependency ẩn |
| Dùng data source tìm resource do root module khác quản lý | Phụ thuộc vào tên/thuộc tính dễ vỡ | Dùng output contract qua remote state |
| Không pin provider/module | Máy local và pipeline có thể dùng phiên bản khác nhau | Constraint, lock file và version module |
| Copy thư mục môi trường từ state cũ rồi apply | Terraform có thể đề xuất tạo lại resource | Lập kế hoạch migration state và review plan trước apply |

## 13. Checklist trước khi áp dụng production

- [ ] Production có Google Cloud project riêng hoặc ranh giới project được phê duyệt.
- [ ] Service account/workload identity của production được tách khỏi dev và staging.
- [ ] Root module production có backend và state riêng.
- [ ] Bucket state đã bật Object Versioning, state locking và IAM tối thiểu.
- [ ] Module dùng chung có input/output rõ ràng, không phụ thuộc vào tên môi trường ngầm định.
- [ ] variables.tf có type, description và validation cho các giá trị quan trọng.
- [ ] File tfvars không chứa secret được commit vào Git.
- [ ] Provider constraint và .terraform.lock.hcl đã được review.
- [ ] Dependency ngầm được thể hiện bằng reference; depends_on chỉ dùng cho dependency ẩn.
- [ ] Phụ thuộc giữa root module có output contract và pipeline order.
- [ ] Plan production đã được review, saved plan được bảo vệ và có phê duyệt.
- [ ] Có phương án phục hồi state và xử lý migration trước khi thay backend hoặc chia state.

## 14. Tự kiểm tra

1. Vì sao mỗi môi trường cần root module và state riêng khi dev và production có IAM khác nhau?
2. Module reusable nên nhận những giá trị nào qua input variables?
3. sensitive = true có bảo đảm secret không xuất hiện trong state không?
4. Khi nào Terraform tự suy ra dependency và khi nào cần depends_on?
5. Vì sao CLI workspace không phù hợp để tách môi trường cần credentials riêng?
6. Làm thế nào để một root module application đọc network ID do root module network quản lý?
7. .terraform.lock.hcl quản lý provider và module remote giống nhau không?

**Gợi ý đáp án**

1. State độc lập giới hạn phạm vi plan/apply; root module và backend riêng giúp tách quyền, credentials và blast radius.
2. Các giá trị thay đổi theo caller như project ID, region, tên tài nguyên, sizing, CIDR và chính sách môi trường. Module giữ mặc định cho những thuộc tính thực sự chung.
3. Không. sensitive che giá trị khi hiển thị; state vẫn có thể lưu giá trị. Cần bảo vệ backend và dùng ephemeral khi ngữ cảnh hỗ trợ.
4. Terraform tự suy ra khi resource/module tham chiếu attribute hoặc output của thành phần khác. Dùng depends_on cho quan hệ ẩn không thể biểu diễn bằng data reference.
5. CLI workspace dùng chung working directory và backend, nên khó tách credentials và access control theo môi trường.
6. Công bố output từ network root module, đọc bằng terraform_remote_state và điều phối pipeline để network apply trước application.
7. Không. Lock file theo dõi provider dependency; module remote cần pin version hoặc source ref trong module block.

## Tài liệu tham khảo

- [Google Cloud: Best practices for root modules](https://docs.cloud.google.com/docs/terraform/best-practices/root-modules)
- [Google Cloud: Best practices for cross-configuration communication](https://docs.cloud.google.com/docs/terraform/best-practices/cross-config-communication)
- [Google Cloud: Best practices for Terraform operations](https://docs.cloud.google.com/docs/terraform/best-practices/operations)
- [HashiCorp: Terraform CLI workspaces](https://developer.hashicorp.com/terraform/cli/workspaces)
- [HashiCorp: GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs)
- [HashiCorp: Input variables](https://developer.hashicorp.com/terraform/language/values/variables)
- [HashiCorp: Dependency lock file](https://developer.hashicorp.com/terraform/language/files/dependency-lock)
- [HashiCorp: depends_on meta-argument](https://developer.hashicorp.com/terraform/language/meta-arguments/depends_on)
- [Terraform Registry: Google provider](https://registry.terraform.io/providers/hashicorp/google)
- [Terraform Registry: Google Cloud Network module](https://registry.terraform.io/modules/terraform-google-modules/network/google/latest)

