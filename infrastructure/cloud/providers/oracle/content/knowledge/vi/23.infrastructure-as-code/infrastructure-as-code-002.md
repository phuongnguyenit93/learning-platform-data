# Provider authentication, variables, outputs và data sources

Trong chương **Hạ tầng dưới dạng mã** của module **CLOUD_PROVIDERS_ORACLE**, bốn thành phần này quyết định Terraform kết nối đến OCI bằng danh tính nào, nhận cấu hình từ đâu, đọc được dữ liệu gì và cung cấp kết quả nào cho phần triển khai tiếp theo.

Tình huống xuyên suốt là chuẩn bị thông tin mạng cho một ứng dụng Java: đội hạ tầng đã có một VCN trong compartment được giao; cấu hình Terraform cần đọc đúng VCN và các Availability Domain của region, kiểm tra phạm vi, rồi xuất một đối tượng kết quả cho pipeline hoặc module triển khai Compute sau này. Qua đó, người học thực hành các nền tảng tenancy, compartment, IAM và VCN trước khi tự động hóa các dịch vụ OCI khác.

Bài thực hành chính chỉ khai báo provider, biến, locals, data sources và outputs. Nó không tạo Compute, cơ sở dữ liệu hoặc tài nguyên mạng mới. Phần mở rộng cuối bài chỉ minh họa cách sử dụng kết quả trong một resource hoặc child module.

## 1. Phân biệt vai trò của từng thành phần

| Thành phần | Câu hỏi trả lời | Ví dụ OCI |
| --- | --- | --- |
| Provider requirement | Cần plugin nào và giới hạn phiên bản nào? | `source = "oracle/oci"` |
| Provider configuration | Gọi OCI bằng danh tính và region nào? | `auth`, profile, region |
| Input variable | Người gọi cấu hình được phép thay đổi gì? | Compartment OCID, VCN OCID, environment |
| Local value | Biểu thức nội bộ nào cần tính và dùng lại? | Bộ tag chung, tên chuẩn hóa |
| Data source | Cần đọc thông tin hiện có từ đâu? | Thông tin VCN, danh sách Availability Domain |
| Managed resource | Terraform chịu trách nhiệm quản lý vòng đời đối tượng nào? | Một subnet được khai báo bằng `resource` |
| Output | Module công bố kết quả nào cho bên sử dụng? | VCN OCID và ngữ cảnh triển khai |

Đừng nhầm `provider "oci"` với một user OCI. Provider là plugin giao tiếp với dịch vụ; principal được cơ chế xác thực của provider sử dụng mới là danh tính mà IAM đánh giá.

Đừng nhầm một `variable` có tên `compartment_ocid` với việc “đăng nhập vào compartment”. Compartment xác định phạm vi tài nguyên; nó không cấp quyền. Hai người chạy cùng một file biến có thể nhận kết quả khác nhau nếu IAM cho phép khác nhau.

~~~mermaid
flowchart LR
    A["Profile hoặc danh tính của runner"] --> P["Provider OCI"]
    V["Variables: region và OCID đích"] --> P
    V --> D["Data sources"]
    P --> D
    D --> L["Locals và biểu thức"]
    L --> O["Outputs"]
    D --> R["Resource hoặc module sử dụng dữ liệu"]
    V --> R
    R --> O
~~~

Terraform dựng quan hệ phụ thuộc từ các tham chiếu, không chạy các tệp `.tf` lần lượt theo tên. Việc chia `providers.tf`, `variables.tf` hay `outputs.tf` chủ yếu giúp tổ chức mã trong cùng một module.

## 2. Provider requirement khác provider configuration

### 2.1. Khai báo plugin và phiên bản

Ví dụ `versions.tf`:

~~~hcl
terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 9.14.0"
    }
  }
}
~~~

Trong ví dụ:

- `required_version` áp dụng cho Terraform CLI.
- `source` định danh provider trong registry, không phải credential.
- `version` giới hạn phiên bản plugin. `~> 9.14.0` cho phép từ `9.14.0` đến trước `9.15.0`.
- `.terraform.lock.hcl` ghi lại phiên bản provider đã chọn và checksum phục vụ việc cài đặt nhất quán.

Mẫu chọn nhánh provider 9.14 để minh họa một giới hạn phiên bản cụ thể; không yêu cầu mọi dự án phải nâng theo nhánh này. Khi áp dụng vào repository có sẵn, dùng phiên bản được dự án chấp nhận và đánh giá thay đổi khi nâng cấp. Tham chiếu: [OCI provider release v9.14.0](https://github.com/oracle/terraform-provider-oci/releases/tag/v9.14.0), [Provider requirements](https://developer.hashicorp.com/terraform/language/providers/requirements) và [Dependency lock file](https://developer.hashicorp.com/terraform/language/files/dependency-lock).

`terraform init` tải và cài plugin theo cấu hình. Với lab dùng local state, việc `init` thành công chưa chứng minh principal có quyền đọc VCN. Cần thực sự thực hiện các data sources trong plan.

Nên lưu lock file của root configuration trong version control. Không chạy `init -upgrade` ở mọi lần triển khai nếu mục tiêu là tái sử dụng bộ dependency đã được kiểm soát.

### 2.2. Cấu hình kết nối

Provider configuration chọn cách xác thực và region:

~~~hcl
provider "oci" {
  auth                = var.oci_auth
  region              = var.region
  config_file_profile = var.oci_auth == "InstancePrincipal" ? null : var.oci_config_profile
}
~~~

Đây là provider dùng trong bài thực hành. Các biến sẽ được khai báo đầy đủ ở phần 5. Khi dùng `InstancePrincipal`, profile API key không phải nguồn credential của runner; ví dụ truyền `null` cho thuộc tính profile trong trường hợp đó.

Không gắn mặc định `compartment_id` cho mọi resource thông qua provider. Từng resource hoặc data source có schema riêng; nhiều thao tác OCI vẫn cần đối số compartment rõ ràng.

Region là nơi gọi các API theo region, không phải home region được tự suy ra từ tên compartment. VCN thuộc region nào thì provider đọc VCN đó phải trỏ đúng region.

## 3. Chọn cơ chế xác thực cho nơi chạy Terraform

### 3.1. Các lựa chọn chính

| `auth` | Nơi dùng phù hợp | Cần chuẩn bị |
| --- | --- | --- |
| `APIKey` | Máy phát triển hoặc runner đã được cấp signing key | User, tenancy, fingerprint và private key được bảo vệ |
| `SecurityToken` | Phiên thao tác người dùng dùng token OCI CLI | Profile có token còn hạn và dữ liệu ký tương ứng |
| `InstancePrincipal` | Runner chạy trên OCI Compute | Instance thuộc dynamic group và policy thích hợp |
| `ResourcePrincipal` | Môi trường OCI cung cấp resource principal | Runtime và IAM dành cho loại resource đó |
| `OKEWorkloadIdentity` | Workload OKE được cấu hình danh tính phù hợp | Cluster, namespace, service account và policy tương ứng |

Đây là lựa chọn theo môi trường thực thi; một container bất kỳ ngoài OCI không tự có instance principal. Token tạm thời cũng cần còn hiệu lực trong thời gian job thực hiện. Tham chiếu: [Configuring the OCI Terraform Provider](https://docs.oracle.com/en-us/iaas/Content/dev/terraform/configuring.htm).

Bài thực hành cho phép ba giá trị `APIKey`, `SecurityToken` và `InstancePrincipal`. Hai cơ chế còn lại cần cấu hình runtime riêng, không chỉ đổi một chuỗi trong file biến.

### 3.2. Máy phát triển: dùng profile OCI

Với API key, lưu cấu hình ngoài repository, ví dụ tại `~/.oci/config`:

~~~ini
[LEARNING]
user=ocid1.user.oc1..<user-id>
tenancy=ocid1.tenancy.oc1..<tenancy-id>
fingerprint=<fingerprint-cua-public-key-da-dang-ky>
key_file=C:/Users/<account>/.oci/oci_api_key.pem
region=ap-singapore-1
~~~

Các placeholder phải được thay bằng giá trị thật. Đăng ký public key cho user OCI; private key ở lại máy hoặc kho credential của runner. `key_file` là tên thuộc tính trong profile OCI; `private_key_path` là tên thuộc tính tương ứng khi cấu hình trực tiếp provider.

Nếu key có passphrase, sử dụng cơ chế cấp passphrase phù hợp với profile/provider của môi trường. Không bỏ passphrase hay sao chép private key vào `.tfvars` chỉ để tránh cấu hình credential.

Để dùng một phiên Security Token đã được thiết lập bằng OCI CLI, chọn `oci_auth = "SecurityToken"` và tên profile của phiên đó. Đừng giả định profile chỉ có API signing key cũng là profile chứa security token hợp lệ.

### 3.3. OCI Compute: dùng instance principal

Một runner trên OCI Compute có thể dùng:

~~~hcl
provider "oci" {
  auth   = "InstancePrincipal"
  region = var.region
}
~~~

Cấu hình này là **phương án thay thế** provider ở phần 2, không phải block mặc định thứ hai để thêm đồng thời.

Runner cần được đưa vào dynamic group có phạm vi phù hợp, chẳng hạn khớp đúng instance chạy job. IAM policy phải cấp quyền đọc dữ liệu hoặc quản lý tài nguyên mà job thật sự dùng. Không cần lưu API signing key của một user lâu dài trên runner cho cơ chế này.

Quyền của principal nên gắn với công việc. Job chỉ đọc VCN không cần quyền tạo/xóa toàn bộ tài nguyên tenancy. Khi tách job plan và apply, xét cả việc plan vẫn cần đọc trạng thái và dữ liệu OCI.

### 3.4. Xác thực không thay thế phân quyền

Đối với lab, principal cần đọc VCN đích và gọi API liệt kê Availability Domain tại phạm vi tương ứng. Ví dụ policy tham khảo cho một group của user:

~~~text
Allow group id <GROUP_OCID> to read vcns in compartment id <COMPARTMENT_OCID>
Allow group id <GROUP_OCID> to inspect compartments in compartment id <COMPARTMENT_OCID>
~~~

Policy thứ hai liên quan các thao tác như `ListAvailabilityDomains` trong bảng quyền IAM. Người quản trị phải đặt policy ở vị trí có hiệu lực với compartment đích và thay đầy đủ placeholder. Với instance principal, dùng policy dành cho dynamic group của runner. Tham chiếu: [Core Services policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/corepolicyreference.htm) và [IAM policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/iampolicyreference.htm).

Đây không phải policy để tạo subnet hay Compute. Khi bài được mở rộng thành provisioning, xác định thêm quyền thao tác và quyền sử dụng các tài nguyên liên quan.

### 3.5. Tránh cấu hình credential bị trộn nguồn

Có hai tầng cần tách biệt:

1. Terraform nhận giá trị biến, chẳng hạn `TF_VAR_region` được gán cho biến `region`.
2. Provider OCI giải quyết các đối số và nguồn credential mà nó hỗ trợ, chẳng hạn profile hoặc các biến `OCI_*`.

`TF_VAR_project_name` chỉ trở thành đầu vào Terraform khi module có biến tương ứng; nó không tự trở thành thuộc tính OCI. Ngược lại, các biến như `OCI_USER_OCID` là nguồn cấu hình riêng của provider, không phải biến mà HCL tự tham chiếu bằng `var.OCI_USER_OCID`.

OCI provider hỗ trợ cả một số tên `TF_VAR_*` và `OCI_*` cho cấu hình của nó. Vì vậy, các biến credential cũ trong môi trường có thể làm profile được chọn không còn là nguồn duy nhất. Hãy kiểm kê **tên biến và nguồn cấp**, tránh in giá trị credential ra log.

Trong thực hành, chọn một cơ chế xác thực rõ ràng cho mỗi job, truyền region rõ ràng, và loại bỏ cấu hình credential thừa trong môi trường runner. Không dựa vào việc máy cá nhân tình cờ có một profile mặc định đang hoạt động.

## 4. Variables là hợp đồng đầu vào của module

### 4.1. Khai báo khác với gán giá trị

~~~hcl
variable "region" {
  description = "Region chứa VCN cần đọc."
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.region)) > 0
    error_message = "region không được rỗng."
  }
}
~~~

Block `variable` khai báo tên, kiểu và ràng buộc. Giá trị sử dụng trong biểu thức là `var.region`. Trong file `.tfvars`, chỉ gán giá trị:

~~~hcl
region = "ap-singapore-1"
~~~

Không đặt block `provider`, `resource` hoặc `variable` vào file `.tfvars`. Không viết `var.region = ...` trong file đó.

Biến không có `default` yêu cầu người gọi cung cấp giá trị. Trong CI, dùng `-input=false` để job không treo chờ nhập khi thiếu biến. Tham chiếu: [Input variables](https://developer.hashicorp.com/terraform/language/values/variables).

### 4.2. Kiểu dữ liệu và giá trị null

| Kiểu | Ví dụ dữ liệu |
| --- | --- |
| `string` | `"ap-singapore-1"` |
| `number` | `3` |
| `bool` | `true` |
| `list(string)` | Danh sách tên AD có thứ tự |
| `set(string)` | Tập giá trị không trùng, không có thứ tự để truy cập theo index |
| `map(string)` | Bộ tag với các khóa linh hoạt |
| `object({...})` | Một cấu trúc có tên thuộc tính và kiểu rõ ràng |

`nullable = false` không đồng nghĩa chuỗi không được rỗng. Nó cấm giá trị `null` ở mức biến; muốn cấm chuỗi rỗng cần validation riêng.

Với object, có thể dùng `optional` cho các thuộc tính có mặc định. Đoạn sau minh họa một hợp đồng đầu vào khác, không cần thêm vào lab đọc VCN:

~~~hcl
variable "workload" {
  description = "Thông số nghiệp vụ của một workload."
  type = object({
    name     = string
    replicas = number
    tags     = optional(map(string), {})
  })
  nullable = false

  validation {
    condition     = var.workload.replicas >= 1 && floor(var.workload.replicas) == var.workload.replicas
    error_message = "replicas phải là số nguyên lớn hơn hoặc bằng 1."
  }
}
~~~

Chọn `object` khi muốn cố định tên trường và kiểu. Chọn `map` khi các khóa là dữ liệu do người gọi cung cấp. Tránh dùng `any` chỉ để né việc thiết kế đầu vào. Tham chiếu: [Type constraints](https://developer.hashicorp.com/terraform/language/expressions/type-constraints).

### 4.3. Thứ tự ưu tiên khi chạy Terraform CLI cục bộ

Với root module chạy bằng CLI thông thường, thứ tự từ ưu tiên thấp đến cao là:

1. `default` trong khai báo biến.
2. Biến môi trường `TF_VAR_<tên_biến>`.
3. `terraform.tfvars`.
4. `terraform.tfvars.json`.
5. Các file `*.auto.tfvars` và `*.auto.tfvars.json` theo thứ tự từ điển.
6. Các đối số `-var` và `-var-file` trên dòng lệnh theo thứ tự xuất hiện; giá trị được gán sau thắng.

Ví dụ, dù môi trường có `TF_VAR_region=us-ashburn-1`, file được truyền bằng `-var-file` vẫn có thể đặt `region = "ap-singapore-1"`. Tên `dev.tfvars` không làm file tự được nạp; cần truyền `-var-file` nếu nó không thuộc quy tắc tự nạp trên.

HCP Terraform và các nền tảng chạy từ xa còn có cơ chế quản trị biến riêng; phải xét nguồn biến của nền tảng đó. Tham chiếu: [Assign values to variables](https://developer.hashicorp.com/terraform/language/values/variables#assign-values-to-variables).

Đừng để cả `dev.auto.tfvars` và `prod.auto.tfvars` trong cùng một working directory rồi trông đợi Terraform tự chọn theo môi trường. Một cách rõ ràng là đặt các file có tên thường trong thư mục `environments` và luôn truyền đúng một bộ file cho job.

### 4.4. Local value không phải một biến đầu vào khác

~~~hcl
locals {
  common_tags = merge(
    var.freeform_tags,
    {
      Project     = "java-learning"
      Environment = var.environment
    }
  )
}
~~~

`local.common_tags` là kết quả tính nội bộ. Người gọi không thể gán trực tiếp bằng `TF_VAR_common_tags`.

Trong `merge` trên, các khóa ở đối số sau thắng khi trùng nhau. Vì vậy, người gọi có thể thêm tag nhưng không ghi đè `Project` hoặc `Environment` qua `freeform_tags`. Đây là quyết định của hợp đồng module, không phải policy IAM. Tham chiếu: [Local values](https://developer.hashicorp.com/terraform/language/values/locals).

## 5. Lab hoàn chỉnh: đọc VCN và xuất ngữ cảnh mạng

### 5.1. Điều kiện và cấu trúc

Chuẩn bị:

- Một VCN đã tồn tại trong một compartment con của tenancy.
- OCID thật của VCN, compartment và region chứa VCN.
- Principal có quyền gọi các API được dùng.
- Máy hoặc runner có kết nối HTTPS đến endpoint OCI, cùng Terraform phù hợp yêu cầu phiên bản.
- Profile OCI ngoài repository nếu dùng `APIKey` hoặc `SecurityToken`.

Cấu trúc ví dụ:

~~~text
oci-network-context/
├── versions.tf
├── providers.tf
├── variables.tf
├── locals.tf
├── data.tf
├── outputs.tf
└── environments/
    └── dev.tfvars
~~~

Dùng `versions.tf` ở phần 2.1 và provider configuration ở phần 2.2 cho `providers.tf`. Các tệp còn lại được trình bày dưới đây. Chỉ phần từ mục 5.2 đến 5.5 thuộc cấu hình lab chính; các đoạn mở rộng phía sau được ghi rõ mục đích riêng.

### 5.2. Khai báo variables.tf

~~~hcl
variable "region" {
  description = "Region chứa VCN cần đọc."
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.region)) > 0
    error_message = "region không được rỗng."
  }
}

variable "oci_auth" {
  description = "Cơ chế xác thực cho runner của lab."
  type        = string
  default     = "APIKey"
  nullable    = false

  validation {
    condition     = contains(["APIKey", "SecurityToken", "InstancePrincipal"], var.oci_auth)
    error_message = "oci_auth phải là APIKey, SecurityToken hoặc InstancePrincipal."
  }
}

variable "oci_config_profile" {
  description = "Profile trong cấu hình OCI; không dùng làm credential cho InstancePrincipal."
  type        = string
  default     = "LEARNING"
  nullable    = false

  validation {
    condition     = length(trimspace(var.oci_config_profile)) > 0
    error_message = "oci_config_profile không được rỗng."
  }
}

variable "compartment_ocid" {
  description = "Compartment con chứa VCN đã có."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^ocid1[.]compartment[.]", var.compartment_ocid))
    error_message = "compartment_ocid phải có dạng OCID của một compartment con."
  }
}

variable "vcn_ocid" {
  description = "OCID của VCN có sẵn cần đọc."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^ocid1[.]vcn[.]", var.vcn_ocid))
    error_message = "vcn_ocid phải có dạng OCID của VCN."
  }
}

variable "environment" {
  description = "Môi trường dùng để xây ngữ cảnh triển khai."
  type        = string
  default     = "dev"
  nullable    = false

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment phải là dev, staging hoặc prod."
  }
}

variable "freeform_tags" {
  description = "Tag bổ sung để đề xuất cho các tài nguyên được tạo ở bước sau."
  type        = map(string)
  default     = {}
  nullable    = false
}
~~~

Hai kiểm tra OCID chỉ xác minh tiền tố định dạng. Chúng không chứng minh tài nguyên tồn tại, nằm đúng tenancy hay có thể truy cập được. Các điều kiện đó cần dữ liệu đọc từ OCI và quyền thực tế.

Lab chủ động yêu cầu compartment con. Nếu muốn dùng root compartment, phải thiết kế lại hợp đồng đầu vào và validation phù hợp; không thay tenancy OCID vào một biến đang chỉ chấp nhận OCID compartment con rồi bỏ qua lỗi.

`oci_auth` chỉ chấp nhận đúng cách viết các giá trị trong allowlist. Việc chọn provider và profile là dữ liệu cấu hình không nhạy cảm; nội dung private key không được đưa thành biến của lab.

### 5.3. Tính locals.tf và đọc data.tf

`locals.tf`:

~~~hcl
locals {
  common_tags = merge(
    var.freeform_tags,
    {
      Project     = "java-learning"
      Environment = var.environment
    }
  )
}
~~~

`data.tf`:

~~~hcl
data "oci_core_vcn" "selected" {
  vcn_id = var.vcn_ocid

  lifecycle {
    postcondition {
      condition     = self.compartment_id == var.compartment_ocid
      error_message = "VCN không thuộc compartment được giao cho cấu hình này."
    }
  }
}

data "oci_identity_availability_domains" "available" {
  compartment_id = var.compartment_ocid

  lifecycle {
    postcondition {
      condition     = length(self.availability_domains) > 0
      error_message = "Không nhận được Availability Domain cho ngữ cảnh OCI hiện tại."
    }
  }
}
~~~

Data source `oci_core_vcn` tra cứu một VCN bằng OCID. Sau khi đọc thành công, postcondition chặn việc tiếp tục sử dụng VCN ngoài compartment được khai báo. Nếu VCN không tồn tại hoặc không có quyền đọc, provider có thể trả lỗi trước khi điều kiện này được đánh giá. Tham chiếu: [oci_core_vcn data source](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/d/core_vcn.html).

`oci_identity_availability_domains` đọc danh sách AD theo ngữ cảnh provider/region. Đối số của nó có thể là OCID tenancy hoặc một compartment; ở đây dùng compartment của lab. Tên AD gắn với tenancy và region, không nên hardcode tên sao chép từ một tài khoản khác. Tham chiếu: [oci_identity_availability_domains](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/d/identity_availability_domains.html).

Postcondition phù hợp để kiểm tra thuộc tính trả về bởi API. `terraform validate` không thay thế việc đọc OCI để kiểm tra các điều kiện này. Tham chiếu: [Custom conditions](https://developer.hashicorp.com/terraform/language/expressions/custom-conditions).

### 5.4. Công bố outputs.tf

~~~hcl
output "vcn_id" {
  description = "OCID của VCN đã đọc và đã kiểm tra phạm vi compartment."
  value       = data.oci_core_vcn.selected.id
}

output "network_context" {
  description = "Ngữ cảnh mạng cho pipeline hoặc module triển khai tiếp theo."
  value = {
    region           = var.region
    environment      = var.environment
    compartment_ocid = data.oci_core_vcn.selected.compartment_id
    vcn_id           = data.oci_core_vcn.selected.id
    vcn_name         = data.oci_core_vcn.selected.display_name
    ipv4_cidrs       = data.oci_core_vcn.selected.cidr_blocks
    availability_domains = sort([
      for domain in data.oci_identity_availability_domains.available.availability_domains :
      domain.name
    ])
    recommended_tags = local.common_tags
  }
}
~~~

`recommended_tags` chỉ là bộ tag đề xuất cho bước triển khai sau. Lab không ghi tag vào VCN đã có. Các thông tin `vcn_name` và `ipv4_cidrs` lấy từ OCI; `environment` lấy từ đầu vào nên không được coi là bằng chứng VCN đã được phân loại môi trường đúng trong hệ thống quản trị.

Sắp xếp danh sách tên AD giúp output dễ so sánh, nhưng không tạo một hợp đồng rằng index `0` sẽ luôn là cùng một AD qua mọi tenancy hoặc mọi thời điểm. Nếu cần cố định nơi chạy workload, chọn rõ tên AD đã xác minh và kiểm tra tên đó còn trong danh sách.

Output `vcn_id` là chuỗi nhỏ để script sử dụng trực tiếp. `network_context` là đối tượng có cấu trúc cho tích hợp cần nhiều thuộc tính. Không xuất toàn bộ đối tượng provider trả về khi bên sử dụng chỉ cần một vài trường. Tham chiếu: [Output values](https://developer.hashicorp.com/terraform/language/values/outputs).

### 5.5. Giá trị environments/dev.tfvars

~~~hcl
region             = "ap-singapore-1"
oci_auth           = "APIKey"
oci_config_profile = "LEARNING"

compartment_ocid = "ocid1.compartment.oc1..<compartment-id>"
vcn_ocid         = "ocid1.vcn.oc1.ap-singapore-1.<vcn-id>"

environment = "dev"

freeform_tags = {
  Owner      = "platform"
  CostCenter = "learning"
}
~~~

Thay các placeholder bằng OCID thật. Nếu muốn chạy bằng instance principal trên Compute, chọn `oci_auth = "InstancePrincipal"` trong bộ biến của runner đó và thiết lập dynamic group/policy trước.

Các file không chứa secret vẫn có thể chứa thông tin định danh nội bộ. Quyết định lưu OCID, region và CostCenter trong Git theo quy định của dự án; đừng mặc định mọi metadata hạ tầng đều được phép công khai.

## 6. Chạy lab và đọc outputs

Các lệnh dưới đây là hướng dẫn cho người học thực hiện trên môi trường OCI của mình. Không cần tạo VCN mới nếu đã có VCN được giao.

### 6.1. Khởi tạo và kiểm tra cấu hình

Trong thư mục lab, chạy:

~~~powershell
terraform init
terraform fmt -check
terraform validate
~~~

`fmt -check` kiểm tra định dạng; `validate` kiểm tra tính hợp lệ cấu hình theo schema. Nếu cần chuẩn hóa định dạng, dùng `terraform fmt` rồi kiểm tra lại. Chỉ tiếp tục khi các bước trước thành công.

Kiểm tra các biến môi trường và profile đã được cấp cho đúng phiên terminal. Không cần in nội dung private key hoặc token để xác nhận một tên profile.

### 6.2. Tạo plan có thể xem lại

~~~powershell
terraform plan -input=false -var-file="environments/dev.tfvars" -out="dev.tfplan"
~~~

Khi plan thành công, xem kế hoạch đã lưu:

~~~powershell
terraform show "dev.tfplan"
~~~

Với đúng cấu hình lab:

- Terraform đọc VCN và danh sách AD.
- Không có resource OCI được đề xuất tạo, cập nhật hoặc xóa.
- Outputs có thể xuất hiện như thay đổi cần lưu.
- Sai quyền, sai region hoặc postcondition không đạt phải được giải quyết trước khi tiếp tục.

Nếu plan đề xuất tạo/xóa tài nguyên, kiểm tra xem thư mục lab có chứa các block `resource` từ ví dụ mở rộng hoặc từ cấu hình khác hay không. Terraform đọc tất cả tệp cấu hình phù hợp trong root module, không chỉ tệp vừa sửa.

Kế hoạch đã lưu chứa đầu vào và dữ liệu cần cho lần apply đó. Không tái sử dụng một plan cũ để triển khai môi trường khác bằng cách đổi file `.tfvars` sau khi plan đã được tạo.

### 6.3. Apply để ghi nhận kết quả vào state

Sau khi xem đúng plan, thực hiện:

~~~powershell
terraform apply -input=false "dev.tfplan"
~~~

Không truyền lại `-var-file` khi apply một saved plan; bộ giá trị đã được chốt trong plan. Quyền gọi OCI và credential vẫn cần khả dụng theo yêu cầu thực thi của provider.

Trong lab này, apply ghi nhận dữ liệu và outputs vào state, không nhận quản lý VCN chỉ vì VCN được đọc qua data source. Nếu sau đó thêm managed resource, ý nghĩa apply sẽ thay đổi theo các hành động trong plan.

### 6.4. Dùng output trong PowerShell hoặc pipeline

~~~powershell
terraform output
terraform output -raw vcn_id
terraform output -json network_context
~~~

Với script, dùng dữ liệu có cấu trúc thay vì cắt chuỗi từ màn hình plan:

~~~powershell
$contextJson = terraform output -json network_context | Out-String

if ($LASTEXITCODE -ne 0) {
    throw "Không đọc được network_context từ state"
}

$networkContext = $contextJson | ConvertFrom-Json

if ([string]::IsNullOrWhiteSpace($networkContext.vcn_id)) {
    throw "Output thiếu vcn_id"
}

$deploymentRegion = $networkContext.region
$deploymentVcnId = $networkContext.vcn_id
~~~

`-raw` phù hợp giá trị đơn giản có thể chuyển thành chuỗi; `-json` phù hợp object và collection. Khi gọi `terraform output -json network_context`, kết quả là giá trị của output đó. Khi gọi `terraform output -json` không chỉ định tên, cấu trúc chứa metadata như `value`, `type` và `sensitive` theo từng output. Tham chiếu: [terraform output command](https://developer.hashicorp.com/terraform/cli/commands/output).

`terraform output` đọc output đã lưu trong state; nó không tự chạy lại các data sources để hỏi OCI. Nếu thông tin trên OCI thay đổi, cần chạy lại quy trình plan/apply hoặc quy trình refresh được dự án lựa chọn trước khi coi output là dữ liệu đã cập nhật.

## 7. Data sources: đọc dữ liệu không đồng nghĩa quản lý vòng đời

### 7.1. Data source, resource và import

| Cách sử dụng | Terraform đang làm gì? | Hệ quả |
| --- | --- | --- |
| `data "oci_core_vcn"` | Đọc VCN có sẵn | Không nhận quyền quản lý vòng đời VCN vào cấu hình |
| `resource "oci_core_vcn"` | Mô tả VCN mà Terraform quản lý | Có thể tạo, cập nhật hoặc xóa theo kế hoạch |
| Import vào địa chỉ resource | Liên kết tài nguyên có sẵn với managed resource trong state | Cần cấu hình resource khớp với hiện trạng và quyền quản lý phù hợp |

Xóa block data source không có nghĩa xóa VCN trên OCI. Ngược lại, chuyển từ đọc VCN sang quản lý nó không thể thực hiện chỉ bằng đổi từ khóa `data` thành `resource`. Cần quy trình import, cấu hình và review plan thích hợp. Tham chiếu: [Data sources](https://developer.hashicorp.com/terraform/language/data-sources) và [Import resources](https://developer.hashicorp.com/terraform/language/import).

Dữ liệu đọc từ data source có thể được lưu trong state. “Chỉ đọc” ở đây nói về thao tác với đối tượng nguồn, không phải dữ liệu không được lưu lại.

### 7.2. Khi nào Terraform đọc data source?

Thông thường, data source có đầy đủ đối số đã biết sẽ được đọc trong giai đoạn plan. Nếu đối số phụ thuộc một resource chưa được tạo hoặc chưa xác định, lần đọc có thể bị hoãn đến apply.

Ví dụ khái niệm:

~~~hcl
data "oci_core_vcn" "after_creation" {
  vcn_id = oci_core_vcn.created_elsewhere_in_this_module.id
}
~~~

Đoạn này chỉ minh họa dependency và yêu cầu resource được tham chiếu đã được khai báo ở nơi tương ứng; không thêm vào lab chính. Với VCN vừa do module quản lý, thường có thể dùng trực tiếp thuộc tính resource thay vì đọc lại cùng đối tượng.

Không thêm `depends_on` vào mọi data source để “bảo đảm chạy sau”. Phụ thuộc rộng có thể làm dữ liệu bị đọc muộn hơn và khiến nhiều giá trị trong plan trở thành `known after apply`. Ưu tiên tham chiếu trực tiếp đến giá trị cần dùng; chỉ dùng phụ thuộc tường minh khi có quan hệ thực mà biểu thức chưa thể hiện được.

### 7.3. Không chọn tài nguyên bằng index một cách tùy tiện

Tra cứu theo OCID phù hợp khi cần chọn chính xác một VCN đã được phê duyệt. Khi phải tra cứu theo tên, phải xử lý cả không có kết quả và có nhiều kết quả.

Ví dụ độc lập thay cho cách chọn VCN bằng OCID:

~~~hcl
data "oci_core_vcns" "by_name" {
  compartment_id = var.compartment_ocid
  display_name   = "shared-network"
  state          = "AVAILABLE"

  lifecycle {
    postcondition {
      condition     = length(self.virtual_networks) == 1
      error_message = "Cần đúng một VCN AVAILABLE có tên shared-network."
    }
  }
}

locals {
  selected_vcn_by_name_id = one([
    for network in data.oci_core_vcns.by_name.virtual_networks :
    network.id
  ])
}
~~~

`display_name` giúp lọc kết quả, không bảo đảm tên duy nhất. `one` biểu đạt yêu cầu lấy tối đa một phần tử; postcondition bổ sung yêu cầu có **đúng một** kết quả. Không thay bằng `virtual_networks[0]` rồi bỏ qua các VCN còn lại. Tham chiếu: [oci_core_vcns data source](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/d/core_vcns.html).

Tương tự, đừng dựa vào thứ tự trả về của danh sách AD để chọn nơi đặt máy. Với image Compute, tiêu chí “image đầu tiên” hoặc “latest” có thể làm thay đổi bản image giữa hai lần chạy. Môi trường cần tái lập nên lưu ID đã lựa chọn qua quy trình phát hành hoặc dùng tiêu chí đủ chặt, thay vì mặc định dữ liệu khám phá luôn bất biến.

## 8. Outputs là giao diện sử dụng kết quả

### 8.1. Root output và child module output

Output trong child module được parent truy cập bằng:

~~~hcl
module.network_context.vcn_id
~~~

Terraform CLI chỉ hiển thị outputs của root module. Muốn xuất lại giá trị từ child module, root phải khai báo output tương ứng:

~~~hcl
output "application_vcn_id" {
  description = "VCN ID do child module cung cấp."
  value       = module.network_context.vcn_id
}
~~~

Các đoạn này minh họa giao diện khi đã có module `network_context`; chúng không bổ sung child module vào lab hiện tại.

Coi tên output, kiểu và ý nghĩa của các trường là một phần của hợp đồng. Nếu đổi một chuỗi `vcn_id` thành object mà không thông báo cho bên sử dụng, pipeline có thể hỏng dù OCI không có thay đổi tài nguyên nào.

Khi module chỉ cần cung cấp ID của một subnet, hãy xuất ID. Không buộc bên sử dụng biết cấu trúc nội bộ của toàn resource. Với kết quả tổng hợp như `network_context`, giữ các trường ổn định và mô tả rõ trường nào là dữ liệu thực tế, trường nào là đề xuất từ cấu hình.

### 8.2. Sensitive không phải mã hóa state

Một ví dụ về khai báo dữ liệu nhạy cảm, không thuộc lab đọc VCN:

~~~hcl
variable "database_admin_password" {
  description = "Mật khẩu được cấp từ kênh quản lý secret của pipeline."
  type        = string
  sensitive   = true
  nullable    = false
}
~~~

`sensitive = true` hỗ trợ che giá trị ở các giao diện hiển thị thông thường. Nếu giá trị đi vào thuộc tính resource, data source hoặc output được lưu trong state, chỉ thêm cờ sensitive không làm giá trị biến mất hoặc được mã hóa trong state. Cần bảo vệ cả state, saved plan, artifact và quyền của người chạy. Tham chiếu: [Manage sensitive data](https://developer.hashicorp.com/terraform/language/manage-sensitive-data).

Không tạo output private key hoặc mật khẩu chỉ để “dễ debug”. Output nhạy cảm có thể bị hiển thị rõ khi truy vấn theo tên hoặc dùng các chế độ `-raw`/`-json`. Việc pipeline che một secret trong giao diện của nó không bảo đảm mọi file artifact hay công cụ xử lý tiếp theo cũng che được.

Các dữ liệu như OCID và tên VCN không phải signing credential, nhưng vẫn có thể thuộc phạm vi thông tin nội bộ. `sensitive` nên phản ánh phân loại thông tin thực tế, không được dùng thay cho kiểm soát quyền đọc state.

### 8.3. Không mặc định chia sẻ toàn state chỉ để lấy một ID

`terraform_remote_state` cho phép đọc root outputs từ snapshot state khác. Tuy nhiên, quyền truy cập snapshot có thể mở rộng đến nhiều dữ liệu hơn các output mà bên sử dụng quan tâm. Không coi việc chỉ tham chiếu một output là cơ chế hạn chế quyền đối với toàn state. Tham chiếu: [terraform_remote_state](https://developer.hashicorp.com/terraform/language/state/remote-state-data).

Nếu hệ thống chỉ cần một số ID đã phê duyệt, cân nhắc công bố riêng các ID đó qua một kênh cấu hình có quyền phù hợp hoặc đọc lại tài nguyên bằng data source của OCI. Chọn theo yêu cầu nhất quán, quyền truy cập và cách phối hợp giữa các đội.

## 9. Provider alias cho nhiều region và cách truyền vào module

Một provider configuration thường đại diện một ngữ cảnh kết nối. Khi cần đọc thêm region, thêm alias thay vì đổi region của cấu hình mặc định trong lúc chạy.

Ví dụ mở rộng sau dùng một biến region thứ hai:

~~~hcl
variable "secondary_region" {
  description = "Region thứ hai cần đọc danh sách AD."
  type        = string
  nullable    = false
}

provider "oci" {
  alias               = "secondary"
  auth                = var.oci_auth
  region              = var.secondary_region
  config_file_profile = var.oci_auth == "InstancePrincipal" ? null : var.oci_config_profile
}

data "oci_identity_availability_domains" "secondary" {
  provider       = oci.secondary
  compartment_id = var.compartment_ocid
}

output "secondary_availability_domains" {
  value = sort([
    for domain in data.oci_identity_availability_domains.secondary.availability_domains :
    domain.name
  ])
}
~~~

Giữ provider mặc định ở phần 2 khi thêm alias này, và cung cấp thêm `secondary_region`. Thuộc tính `provider = oci.secondary` là tham chiếu cấu hình provider, không phải chuỗi `"oci.secondary"`.

Nếu child module dùng một provider mặc định tên `oci`, parent có thể ánh xạ cấu hình mong muốn qua đối số `providers` của block module:

~~~hcl
providers = {
  oci = oci.secondary
}
~~~

Đoạn này là một phần của block `module` đã có, không phải một block cấp cao độc lập. Child module vẫn khai báo requirement `source = "oracle/oci"` của nó. Nếu child muốn tự tham chiếu nhiều alias bên trong, child cần khai báo các `configuration_aliases` tương ứng. Tham chiếu: [Provider configuration](https://developer.hashicorp.com/terraform/language/providers/configuration) và [Providers within modules](https://developer.hashicorp.com/terraform/language/modules/develop/providers).

Với module tái sử dụng, để root chọn credential và provider configuration. Truyền các đầu vào nghiệp vụ như compartment, VCN hoặc tên workload vào module; tránh yêu cầu mọi child module nhận private key rồi tự tạo provider riêng.

Không lấy một giá trị chỉ có sau apply để tạo cấu hình provider mà chính các resource đó cần. Ví dụ dùng dữ liệu được tạo bởi provider OCI để quyết định credential khởi tạo cùng provider có thể tạo vòng phụ thuộc hoặc cấu hình không thể lập plan.

## 10. Vận hành trong CI, kiểm soát phạm vi và chi phí

Một job đáng tin cậy cần biết rõ bộ biến, principal, region, state và phiên bản provider mà nó dùng. Cùng một bộ HCL không đủ chứng minh hai lần chạy có cùng ngữ cảnh.

| Thành phần | Cách kiểm soát |
| --- | --- |
| Principal | Danh tính riêng của job; quyền đọc/ghi theo nhiệm vụ |
| Biến môi trường | Bộ giá trị được chọn rõ, không trộn nhiều môi trường |
| Phiên bản provider | Constraint có chủ đích và lock file được quản lý |
| Saved plan | Gắn với commit, môi trường và người xét duyệt phù hợp |
| State | Backend và quyền truy cập đúng môi trường, có cơ chế tránh ghi đồng thời phù hợp |
| Outputs | Schema ổn định; không công bố secret tùy tiện |
| Log | Ghi bước thất bại và mã request khi có; không in token, key hoặc toàn bộ dữ liệu nhạy cảm |

Các mục thường loại khỏi Git của cấu hình thực hành:

~~~gitignore
.terraform/
*.tfstate
*.tfstate.*
*.tfplan
crash.log
crash.*.log
environments/*.local.tfvars
~~~

Giữ `.terraform.lock.hcl` trong repository của root configuration. Với remote backend, credential truy cập backend có thể là một luồng cấu hình khác với credential provider OCI. Cấu hình provider không tự đồng nghĩa đã cấu hình bảo vệ hoặc khóa state.

Lab chỉ đọc dữ liệu nhưng vẫn gọi API và ghi state khi apply. Khi phát triển thêm Compute, cơ sở dữ liệu hoặc gateway có chi phí, review cả giá trị biến chi phối số lượng, shape, dung lượng và region trước khi apply. Tag `CostCenter` trong output đề xuất không tự đặt ngân sách hoặc hạn mức chi tiêu.

Data source giúp khám phá môi trường; việc đưa kết quả đó vào lựa chọn tài nguyên vẫn cần tiêu chí rõ. Không dùng “tài nguyên đầu tiên tìm thấy” làm cơ sở cho kế hoạch tính sẵn sàng hay khôi phục giữa các region.

## 11. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| `init` thành công nhưng data source lỗi | Quyền OCI, credential, đường mạng và region; `init` chưa chứng minh các điều kiện này |
| Không thấy profile | Tên profile, home directory và file cấu hình của chính user chạy tiến trình |
| Lỗi private key/fingerprint | Key đúng định dạng, public key đã đăng ký cho user đúng, fingerprint và passphrase tương ứng |
| Security token không còn dùng được | Thời hạn phiên và cơ chế cấp/refresh token trước hoặc trong job |
| Instance principal không hoạt động ở máy cá nhân | Runner không ở môi trường Compute hỗ trợ hoặc thiếu cấu hình IAM |
| `NotAuthorizedOrNotFound` khi đọc VCN | OCID, region, tenancy và policy; không suy ngay rằng VCN đã bị xóa |
| Validation OCID đạt nhưng API từ chối | Validation chỉ kiểm tra định dạng, không kiểm tra tồn tại hay quyền |
| VCN đọc được nhưng postcondition thất bại | Đối chiếu compartment thật của VCN với đầu vào |
| Chọn nhầm region dù đã đặt biến môi trường | Kiểm tra nguồn biến ưu tiên cao hơn và cấu hình provider thực tế |
| Đổi `dev.tfvars` nhưng output không đổi | File đó đã được nạp chưa, apply vào state nào, output đang đọc snapshot nào |
| Data source bị đọc muộn | Kiểm tra đối số chưa biết và `depends_on` không cần thiết |
| Tra cứu theo tên có nhiều kết quả | Thu hẹp điều kiện hoặc dùng OCID; không lấy phần tử đầu một cách tùy ý |
| Pipeline không parse được output | Phân biệt output theo tên với toàn bộ JSON outputs; không parse màn hình plan |
| Giá trị sensitive xuất hiện trong artifact | Kiểm tra đường xuất dữ liệu, state, saved plan và CLI output được gọi |

Khi hỗ trợ vận hành, thu thập provider version, Terraform version, loại xác thực, region, bước thất bại và mã request OCI nếu có. Chỉ chia sẻ dữ liệu định danh được phép; không yêu cầu người khác gửi private key hoặc dump toàn bộ môi trường.

## 12. Các tình huống người học cần tự kiểm chứng

Sau khi hoàn thành lab, thực hiện từng thay đổi nhỏ và quan sát plan hoặc lỗi:

1. Dùng đúng OCID và region: nhận VCN và danh sách AD; không có resource OCI được tạo.
2. Đặt `environment = "production"`: validation từ chối vì không thuộc allowlist.
3. Đặt region rỗng: validation từ chối trước khi dựa vào kết quả đọc VCN.
4. Đưa OCID VCN đọc được nhưng thuộc compartment khác: postcondition phải phát hiện lệch phạm vi.
5. Đặt `TF_VAR_environment` rồi đặt giá trị khác trong `-var-file`: xác nhận nguồn ưu tiên cao hơn được dùng.
6. Bỏ `-var-file` khi chưa có nguồn cấp các biến bắt buộc và dùng `-input=false`: job thất bại rõ ràng, không chờ nhập.
7. Đọc `terraform output -json network_context` sau apply: parser nhận một object có các trường được công bố.
8. So sánh bộ tag đề xuất với tag thật của VCN: hiểu rằng output không tự cập nhật tài nguyên.
9. Chạy lại với principal không đủ quyền: phân biệt lỗi cấp quyền với lỗi cú pháp hoặc validation.
10. Nếu dùng ví dụ tra cứu theo tên, kiểm tra hành vi khi có không hoặc nhiều kết quả.

Những tình huống này là bài thực hành cho môi trường người học; tài liệu không khẳng định đã chạy thành công trên tenancy cụ thể.

Bốn quyết định cần giữ rõ là: provider xác định ngữ cảnh gọi OCI, variables xác định phần cấu hình được phép thay đổi, data sources đọc hiện trạng và outputs công bố giao diện kết quả. Khi các ranh giới này được thiết kế rõ, cùng một bộ mã có thể được vận hành có kiểm soát qua nhiều compartment, region và môi trường.
