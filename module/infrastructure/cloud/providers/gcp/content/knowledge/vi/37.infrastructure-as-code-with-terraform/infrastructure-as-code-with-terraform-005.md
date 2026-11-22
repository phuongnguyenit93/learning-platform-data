# Thiết kế modules Terraform tái sử dụng cho GCP

Terraform module là một tập hợp các tệp cấu hình được đóng gói để tạo và quản lý một nhóm tài nguyên hạ tầng. Trên Google Cloud, module giúp chuẩn hóa cách tạo VPC, subnet, service account, bucket, Cloud Run service hoặc các thành phần nền tảng khác. Thay vì sao chép nhiều khối resource giữa các project, nhóm có thể xây dựng module có đầu vào và đầu ra rõ ràng, sau đó gọi module đó từ các cấu hình môi trường khác nhau.

Một module tái sử dụng tốt không chỉ gom nhiều resource vào một thư mục. Nó cần có ranh giới trách nhiệm hợp lý, giao diện ổn định, giá trị mặc định an toàn, khả năng kiểm tra đầu vào và cách phát hành phiên bản có kiểm soát. Thiết kế như vậy giúp các nhóm dùng chung tiêu chuẩn hạ tầng mà vẫn điều chỉnh được theo nhu cầu của từng workload.

## 1. Phân biệt root module và child module

Trong Terraform, mọi thư mục chứa một tập hợp tệp cấu hình được nạp cùng nhau là một module. Khi chạy lệnh Terraform trong một thư mục, cấu hình tại đó là root module. Một root module có thể gọi các module khác bằng khối module; các module được gọi được gọi là child module.

| Thành phần | Trách nhiệm | Ví dụ trên GCP |
| --- | --- | --- |
| Root module | Kết hợp các thành phần, chọn môi trường, cấu hình provider, backend và state | Cấu hình hạ tầng production của một ứng dụng |
| Child module | Đóng gói một năng lực hạ tầng có thể dùng lại, nhận inputs và trả outputs | Module VPC, Cloud Run service, GCS bucket hoặc service account |
| Provider configuration | Cung cấp thông tin kết nối và xác thực với Google Cloud | Project, region và credentials hoặc cơ chế xác thực của Google |
| State | Ghi nhận quan hệ giữa cấu hình Terraform và tài nguyên thực tế | State riêng cho network production hoặc workload staging |

Root module thường là nơi nhóm chọn project, region, môi trường và kết nối các module. Child module nên tập trung vào việc tạo một thành phần có trách nhiệm rõ ràng. Backend và state thuộc về root module; child module không nên tự khai báo backend riêng.

## 2. Xác định ranh giới module

Ranh giới tốt bắt đầu từ một năng lực hạ tầng có thể mô tả bằng một câu. Ví dụ: module VPC tạo một mạng tùy chỉnh và các subnet; module Cloud Run triển khai một dịch vụ với cấu hình runtime, ingress và service account; module bucket tạo bucket với chính sách truy cập và lifecycle được chuẩn hóa.

Khi quyết định tách module, hãy cân nhắc:

- **Một trách nhiệm rõ ràng:** module nên giải quyết một vấn đề hạ tầng liên quan chặt chẽ. Không nên tạo module tổng hợp có quá nhiều tùy chọn để quản lý toàn bộ project.
- **Giao diện theo nhu cầu người gọi:** chỉ đưa vào inputs mà người dùng module cần quyết định. Các chi tiết triển khai có thể giữ bên trong.
- **Mức tái sử dụng thực tế:** chỉ trừu tượng hóa những mẫu đã lặp lại hoặc có khả năng được dùng ở nhiều workload. Tránh tạo module chỉ để bọc một resource mà không thêm tiêu chuẩn hay giá trị.
- **Quyền sở hữu rõ ràng:** xác định nhóm duy trì module, người phê duyệt thay đổi và cách thông báo khi có phiên bản mới.
- **Mức độ kết hợp vừa phải:** module có thể tạo các tài nguyên cùng vòng đời, nhưng nên hạn chế phụ thuộc vào những module không liên quan.

Ví dụ, module VPC có thể quản lý network và subnet. Firewall policy, Cloud NAT, VPN hoặc Shared VPC có thể là module riêng nếu chúng có vòng đời, quyền quản trị hoặc cách sử dụng độc lập. Root module sẽ kết hợp chúng bằng outputs và inputs.

Không nên tạo một module riêng cho mọi resource theo cách máy móc. Nếu module chỉ chuyển tiếp toàn bộ thuộc tính của một resource mà không cung cấp chuẩn đặt tên, validation, bảo mật hoặc cấu trúc có giá trị, người gọi có thể sử dụng resource trực tiếp dễ hiểu hơn.

## 3. Tổ chức cấu trúc thư mục

Một repository có thể tổ chức các module dùng chung và các cấu hình triển khai như sau:

~~~text
terraform-gcp/
├── modules/
│   ├── vpc/
│   │   ├── versions.tf
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   ├── README.md
│   │   └── examples/
│   │       └── basic/
│   ├── cloud-run-service/
│   └── gcs-bucket/
├── environments/
│   ├── dev/
│   ├── staging/
│   └── prod/
└── README.md
~~~

Trong module VPC, có thể chia nội dung theo vai trò:

| Tệp | Nội dung |
| --- | --- |
| versions.tf | Phiên bản Terraform tối thiểu và yêu cầu provider |
| main.tf | Các resource chính |
| variables.tf | Inputs, kiểu dữ liệu, mô tả, validation và giá trị mặc định |
| outputs.tf | Những giá trị mà module công khai cho module gọi |
| README.md | Mục đích, cách gọi, inputs, outputs, ví dụ và lưu ý vận hành |
| examples/ | Các root module nhỏ minh họa cách sử dụng module |

Terraform nạp tất cả các tệp .tf trong cùng thư mục như một cấu hình duy nhất; việc tách thành nhiều tệp nhằm giúp con người đọc và duy trì dễ hơn. Không cần tạo một tệp riêng cho mỗi resource nếu số lượng nhỏ hoặc cách chia làm cấu hình khó theo dõi.

## 4. Thiết kế giao diện inputs và outputs

Inputs là hợp đồng giữa module và người gọi. Một input tốt có tên thể hiện ý nghĩa, kiểu dữ liệu rõ ràng, description dễ hiểu và validation cho những ràng buộc quan trọng. Hạn chế dùng nhiều biến string tự do khi có thể mô tả bằng object hoặc map có cấu trúc.

Với module VPC, các inputs thường gồm:

| Input | Kiểu dữ liệu gợi ý | Mục đích |
| --- | --- | --- |
| project_id | string | Project sở hữu network |
| network_name | string | Tên VPC |
| routing_mode | string | GLOBAL hoặc REGIONAL |
| subnets | map(object(...)) | Danh sách subnet, region và CIDR |

Outputs nên công bố thông tin mà module khác thực sự cần, ví dụ network ID, self link hoặc map subnet theo tên. Không nên xuất toàn bộ thuộc tính nội bộ chỉ vì chúng đang có sẵn; outputs là một phần API công khai và thay đổi chúng có thể ảnh hưởng người gọi.

Khi một module Cloud Run cần network do module VPC tạo, root module có thể truyền output network vào input của module Cloud Run. Cách nối này tạo dependency rõ ràng trong đồ thị Terraform và giúp Terraform xác định thứ tự thực hiện.

### Validation và giá trị mặc định

Dùng kiểu dữ liệu cụ thể và validation để phát hiện lỗi cấu hình sớm. Ví dụ, project ID và tên network không được để trống, routing mode chỉ nhận giá trị hợp lệ, còn CIDR cần có định dạng mạng hợp lệ.

Giá trị mặc định chỉ nên áp dụng cho tùy chọn có hành vi an toàn và phổ biến. Không nên tự đặt project, region, IAM principal hoặc CIDR quan trọng bằng một giá trị giả định vì có thể tạo tài nguyên sai phạm vi.

Với Terraform từ 1.3 trở lên, object type có thể dùng thuộc tính optional để định nghĩa trường tùy chọn có default. Cần công bố rõ giá trị mặc định trong README để người gọi hiểu module sẽ tạo ra cấu hình gì.

## 5. Ví dụ xây dựng module VPC cho Google Cloud

Ví dụ sau tạo một VPC custom-mode và nhiều subnet. Mục tiêu là minh họa cấu trúc module, cách truyền dữ liệu và cách công bố outputs. Tên project, region và dải CIDR là giá trị mẫu; cần thay bằng thông tin phù hợp với kiến trúc thực tế.

**Tệp versions.tf**

~~~hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0.0"
    }
  }
}
~~~

Module công bố provider mà nó cần và phiên bản Terraform tối thiểu. Module không nên tự cấu hình credentials hoặc project mặc định. Root module sẽ cấu hình provider và truyền cấu hình phù hợp xuống child module.

**Tệp variables.tf**

~~~hcl
variable "project_id" {
  description = "Project ID sở hữu VPC và các subnet."
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.project_id)) > 0
    error_message = "project_id không được để trống."
  }
}

variable "network_name" {
  description = "Tên VPC cần tạo."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$", var.network_name))
    error_message = "network_name phải bắt đầu bằng chữ thường, chỉ chứa chữ thường, số hoặc dấu gạch ngang và dài tối đa 63 ký tự."
  }
}

variable "routing_mode" {
  description = "Chế độ định tuyến của VPC."
  type        = string
  default     = "GLOBAL"

  validation {
    condition     = contains(["GLOBAL", "REGIONAL"], var.routing_mode)
    error_message = "routing_mode chỉ nhận GLOBAL hoặc REGIONAL."
  }
}

variable "subnets" {
  description = "Subnet theo tên, mỗi subnet có region và CIDR."
  type = map(object({
    region                   = string
    ip_cidr_range            = string
    private_ip_google_access = optional(bool, true)
  }))
  nullable = false

  validation {
    condition = alltrue([
      for subnet in values(var.subnets) :
      length(trimspace(subnet.region)) > 0 &&
      can(cidrhost(subnet.ip_cidr_range, 0))
    ])
    error_message = "Mỗi subnet phải có region không rỗng và ip_cidr_range hợp lệ."
  }
}
~~~

**Tệp main.tf**

~~~hcl
resource "google_compute_network" "this" {
  project                 = var.project_id
  name                    = var.network_name
  auto_create_subnetworks = false
  routing_mode            = var.routing_mode
}

resource "google_compute_subnetwork" "this" {
  for_each = var.subnets

  project                  = var.project_id
  name                     = each.key
  region                   = each.value.region
  network                  = google_compute_network.this.id
  ip_cidr_range            = each.value.ip_cidr_range
  private_ip_google_access = each.value.private_ip_google_access
}
~~~

**Tệp outputs.tf**

~~~hcl
output "network_id" {
  description = "ID của VPC được tạo."
  value       = google_compute_network.this.id
}

output "network_self_link" {
  description = "Self link của VPC."
  value       = google_compute_network.this.self_link
}

output "subnetwork_self_links" {
  description = "Map self link của subnet theo tên."
  value = {
    for name, subnet in google_compute_subnetwork.this :
    name => subnet.self_link
  }
}
~~~

Ở đây, for_each tạo một subnet cho mỗi phần tử trong map. Tên subnet trở thành key ổn định, giúp người gọi tham chiếu subnet theo tên thay vì theo vị trí trong danh sách. Việc dùng map cũng giúp thêm một subnet mà không làm thay đổi cách tham chiếu các subnet khác.

VPC được tạo ở chế độ custom-mode vì auto_create_subnetworks được đặt false. Mỗi subnet khai báo region riêng. Module có thể được mở rộng để hỗ trợ secondary IP ranges hoặc flow logs khi nhu cầu thực tế xuất hiện; không nên thêm mọi tính năng mạng vào module cơ sở ngay từ đầu.

## 6. Gọi module từ root module

Root module chịu trách nhiệm cấu hình Google provider, chọn project và truyền các giá trị theo môi trường. Ví dụ sau gọi module VPC từ thư mục modules/vpc:

~~~hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0.0"
    }
  }
}

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "environment" {
  type = string
}

provider "google" {
  project = var.project_id
  region  = var.region
}

module "network" {
  source = "../../modules/vpc"

  project_id   = var.project_id
  network_name = format("%s-network", var.environment)
  routing_mode = "GLOBAL"

  subnets = {
    app = {
      region        = var.region
      ip_cidr_range = "10.20.0.0/20"
    }
    data = {
      region        = var.region
      ip_cidr_range = "10.20.16.0/20"
    }
  }
}

output "network_id" {
  value = module.network.network_id
}
~~~

Với cấu trúc thư mục đã nêu, source tương đối từ environments/prod đến modules/vpc là ../../modules/vpc. Trong môi trường thực tế, có thể đặt các biến khác nhau trong tệp tfvars riêng, chẳng hạn project ID, region, environment và CIDR. Không đưa thông tin xác thực hoặc secret vào tệp tfvars được commit lên repository.

Nếu nhiều môi trường dùng cùng module, mỗi root module dev, staging và prod truyền bộ input riêng. Module giữ nguyên logic; root module quyết định giá trị môi trường và backend state. Cách này giúp thay đổi logic dùng chung được kiểm soát tập trung, trong khi quyền truy cập và vòng đời state vẫn tách biệt.

## 7. Provider configuration và nhiều project

Provider configuration nên nằm ở root module để nhóm triển khai quyết định project, region và cơ chế xác thực. Child module khai báo required_providers để Terraform biết provider source và version, nhưng thường không chứa khối provider riêng.

Provider mặc định từ root module được truyền xuống child module theo cơ chế kế thừa. Nếu cần dùng provider alias, root module có thể truyền alias tường minh:

~~~hcl
provider "google" {
  alias   = "shared"
  project = var.network_project_id
  region  = var.region
}

module "shared_network" {
  source = "../../modules/vpc"

  providers = {
    google = google.shared
  }

  project_id   = var.network_project_id
  network_name = "shared-network"
  subnets      = var.subnets
}
~~~

Ví dụ này dùng provider alias để tạo network trong project dùng chung. Nếu child module cần nhiều provider configuration khác nhau, module phải khai báo configuration alias tương ứng trong required_providers và root module phải truyền đủ mapping. Hãy chỉ dùng alias khi kiến trúc thực sự cần nhiều project hoặc cấu hình provider khác nhau.

Không đặt credentials trực tiếp trong mã nguồn module. Trên môi trường phát triển có thể dùng Application Default Credentials; trong CI/CD nên dùng cơ chế xác thực workload phù hợp, chẳng hạn Workload Identity Federation khi nền tảng chạy hỗ trợ. Service account hoặc principal triển khai chỉ nên có quyền cần thiết trên project và tài nguyên mục tiêu.

## 8. Kết hợp nhiều module thành kiến trúc

Module được tái sử dụng hiệu quả khi root module kết hợp các thành phần bằng outputs và inputs. Ví dụ một workload có thể gồm:

- Module VPC tạo network và subnet.
- Module service account tạo danh tính runtime cho ứng dụng.
- Module Cloud Run triển khai container và nhận service account, cấu hình ingress.
- Module IAM cấp các quyền cần thiết cho workload.
- Module GCS bucket tạo nơi lưu trữ dữ liệu với policy và lifecycle phù hợp.

Root module nối các thành phần:

~~~hcl
module "runtime_identity" {
  source       = "../../modules/service-account"
  project_id   = var.project_id
  account_id   = "orders-api"
  display_name = "Orders API runtime"
}

module "orders_service" {
  source = "../../modules/cloud-run-service"

  project_id         = var.project_id
  region             = var.region
  service_name       = "orders-api"
  image              = var.orders_image
  service_account_id = module.runtime_identity.email
}
~~~

Đoạn gọi module minh họa cách truyền output email của service account sang input của module Cloud Run. Các input và output phải khớp với giao diện thực tế của những module tương ứng. Không nên copy ví dụ này vào root module nếu repository chưa có các module được nêu.

Nếu module IAM cấp quyền cho service account, hãy chọn loại IAM resource có semantics phù hợp. Resource dạng member thường quản lý một binding thành viên; resource dạng binding có thể quản lý toàn bộ thành viên cho một role ở phạm vi đó. Trộn các resource quản lý cùng một role và cùng phạm vi có thể gây ghi đè policy ngoài dự kiến. Tài liệu module cần nói rõ quyền nào được tạo và phạm vi nào bị quản lý.

## 9. Versioning và phát hành module

Module dùng chung là một API hạ tầng. Khi thay đổi input, output hoặc hành vi resource, cần xem xét ảnh hưởng đến mọi root module đang sử dụng. Nên áp dụng versioning có quy tắc và phát hành thay đổi qua pull request, review, kiểm thử và release note.

Với module lưu trong Terraform Registry hoặc private registry, người gọi có thể chỉ định version:

~~~hcl
module "network" {
  source  = "app.terraform.io/example-org/gcp-vpc/google"
  version = "~> 1.2"

  project_id   = var.project_id
  network_name = "prod-network"
  subnets      = var.subnets
}
~~~

Địa chỉ registry ở trên là ví dụ minh họa. Trong tổ chức, thay bằng hostname và namespace thực tế. Với module lấy từ Git, có thể pin tag hoặc commit:

~~~hcl
module "network" {
  source = "git::https://example.com/platform/terraform-gcp.git//modules/vpc?ref=v1.2.0"

  project_id   = var.project_id
  network_name = "prod-network"
  subnets      = var.subnets
}
~~~

Source Git là ví dụ cấu trúc; thay URL bằng repository thực tế. Với Git source, ref xác định tag hoặc commit cần sử dụng. Tránh tham chiếu nhánh thay đổi liên tục trong môi trường production vì cùng một cấu hình có thể tải nội dung khác nhau ở những lần init sau.

Một quy trình phát hành module có thể gồm:

1. Tạo branch và pull request cho thay đổi.
2. Chạy format, validate, kiểm tra static và kiểm thử module.
3. Dùng example root module để xác minh giao diện công khai.
4. Review ảnh hưởng đến resource, state và người gọi hiện có.
5. Tăng version theo mức độ thay đổi, tạo tag hoặc phát hành lên registry.
6. Cập nhật người gọi theo kế hoạch, chạy plan và review trước khi apply.

Thay đổi phá vỡ tương thích như xóa input, đổi kiểu dữ liệu, đổi tên output hoặc thay resource address cần được xem là thay đổi lớn. Nếu phải đổi địa chỉ resource, hãy đánh giá việc dùng moved block hoặc quy trình state migration phù hợp để tránh Terraform hiểu nhầm tài nguyên cũ cần bị hủy và tạo lại.

## 10. State, môi trường và bảo vệ dữ liệu nhạy cảm

Child module không có state độc lập. State thuộc về root module đang chạy và lưu thông tin liên kết giữa resource address với tài nguyên thực tế. Vì vậy, cùng một module có thể được gọi trong nhiều root module với state tách biệt.

Với GCP production, nhóm thường dùng GCS backend để lưu state từ xa. Bucket state cần được tạo và bảo vệ theo chính sách riêng, bật versioning nếu phù hợp, giới hạn IAM và kiểm soát quyền đọc/xóa. Backend được cấu hình tại root module, không khai báo trong child module. Nên tách state theo môi trường hoặc ranh giới quản trị để giảm phạm vi ảnh hưởng khi có lỗi hoặc thao tác nhầm.

Ví dụ backend tại root module:

~~~hcl
terraform {
  backend "gcs" {
    bucket = "org-terraform-state-prod"
    prefix = "gcp/network/prod"
  }
}
~~~

Bucket và prefix là giá trị mẫu. Backend bucket phải tồn tại trước khi khởi tạo backend. Không dùng cùng prefix state cho nhiều root module độc lập. Việc chia sẻ state giữa dev và prod làm tăng nguy cơ apply nhầm tài nguyên và khó kiểm soát quyền.

Biến đánh dấu sensitive giúp hạn chế hiển thị giá trị trong một số đầu ra của Terraform, nhưng không bảo đảm secret không được lưu trong state. Không hardcode mật khẩu, private key hoặc token trong module, output, tfvars commit lên Git hay log pipeline. Dùng Secret Manager hoặc cơ chế secret injection phù hợp, giới hạn quyền đọc state và tránh xuất giá trị nhạy cảm qua outputs.

## 11. Kiểm thử và kiểm tra chất lượng module

Module nên có example chạy được để người dùng hiểu cách gọi và reviewer có thể xác minh giao diện. Các bước kiểm tra cơ bản:

~~~bash
terraform fmt -check -recursive
terraform -chdir=modules/vpc/examples/basic init -backend=false
terraform -chdir=modules/vpc/examples/basic validate
terraform -chdir=modules/vpc/examples/basic plan
~~~

Lệnh plan cần có biến mẫu hợp lệ và quyền đọc cấu hình provider tương ứng. Có thể dùng tệp tfvars không chứa secret để cung cấp project, region và CIDR trong môi trường kiểm thử.

Với Terraform 1.6 trở lên, terraform test cho phép viết kiểm thử trong các tệp .tftest.hcl. Test có thể kiểm tra điều kiện, output và hành vi cấu hình; một số test có thể tạo tài nguyên thật tùy cách khai báo run. Chỉ chạy integration test trong project thử nghiệm được cô lập, với quyền và ngân sách phù hợp, đồng thời kiểm tra quá trình cleanup.

Ngoài kiểm thử Terraform, nên rà soát:

- Tên resource ổn định và tránh thay đổi địa chỉ ngoài ý muốn.
- Inputs có validation và mô tả rõ ràng.
- Outputs chỉ công khai thông tin cần thiết.
- IAM theo nguyên tắc đặc quyền tối thiểu.
- Không có secret trong mã nguồn, state mẫu hoặc log.
- API được bật và prerequisite của tài nguyên được mô tả.
- README có ví dụ, yêu cầu provider, inputs, outputs và ghi chú nâng cấp.
- Thay đổi module có release note và hướng dẫn migration khi cần.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Tác động | Cách cải thiện |
| --- | --- | --- |
| Module quá lớn, quản lý nhiều miền tài nguyên không liên quan | Khó tái sử dụng và thay đổi một phần có thể ảnh hưởng toàn bộ | Tách theo năng lực và vòng đời tài nguyên |
| Expose mọi thuộc tính resource thành input | Giao diện phức tạp, khó duy trì và khó giữ chuẩn | Chỉ công khai tùy chọn có ý nghĩa với người gọi |
| Khai báo provider hoặc credentials bên trong child module | Khó dùng module ở nhiều project và nhiều môi trường | Cấu hình provider ở root và truyền alias khi cần |
| Dùng tên resource hoặc for_each key không ổn định | Thay đổi input có thể dẫn đến destroy/create ngoài ý muốn | Dùng key có ý nghĩa, ổn định và tài liệu hóa |
| Dùng wildcard IAM hoặc quyền rộng để module dễ chạy | Tăng phạm vi ảnh hưởng khi workload bị xâm phạm | Thiết kế role và principal theo nhu cầu cụ thể |
| Thay đổi output hoặc input mà không versioning | Root module hiện có có thể lỗi hoặc thay đổi hạ tầng ngoài ý muốn | Phát hành phiên bản, migration và release note |
| Dùng chung state giữa nhiều môi trường | Có thể apply nhầm tài nguyên và mở rộng quyền không cần thiết | Tách root module, backend prefix và quyền theo môi trường |
| Cho rằng sensitive ngăn secret vào state | Secret vẫn có thể được lưu trong state hoặc backend | Bảo vệ state và dùng Secret Manager hoặc secret injection |

## 13. Checklist thiết kế module GCP có thể tái sử dụng

Trước khi phát hành module dùng chung, hãy xác nhận:

- Module có một mục đích và ranh giới trách nhiệm rõ ràng.
- Inputs có kiểu dữ liệu, mô tả, validation và default an toàn.
- Outputs là giao diện công khai nhỏ, ổn định và có tài liệu.
- Module khai báo required_providers và phiên bản Terraform tối thiểu.
- Provider configuration, backend và state do root module quản lý.
- Module có example root module và kiểm thử phù hợp.
- Quyền IAM, API prerequisite, region và project scope được mô tả.
- Resource address và for_each key được thiết kế ổn định.
- Phiên bản module được pin trong môi trường production và có quy trình nâng cấp.
- State, credentials và secret được bảo vệ theo chính sách tổ chức.
- Thay đổi phá vỡ tương thích có migration plan và review trước khi apply.

Thiết kế module Terraform tái sử dụng cho GCP là việc xác định đúng phần hạ tầng cần chuẩn hóa, công bố một giao diện dễ hiểu và giữ quyền kiểm soát ở root module. Khi module có trách nhiệm rõ ràng, provider và state được quản lý đúng tầng, inputs được kiểm tra và phiên bản được phát hành có kỷ luật, nhiều nhóm có thể triển khai hạ tầng nhất quán mà vẫn đáp ứng nhu cầu riêng của từng project và workload.
