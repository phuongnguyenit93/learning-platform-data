# Lưu cấu hình Terraform trong Git và kết nối Resource Manager

## Mục tiêu bài học

Trong chương **Hạ tầng dưới dạng mã** của module **CLOUD_PROVIDERS_ORACLE**, bài này hướng dẫn đưa cấu hình Terraform lên Git và dùng Oracle Cloud Infrastructure Resource Manager để thực thi cấu hình đó. Đây là bước nối giữa mã hạ tầng được nhóm phát triển quản lý và tài nguyên thật trong một tenancy OCI.

Sau bài học, bạn có thể:

- Tổ chức repository sao cho Resource Manager chạy đúng thư mục Terraform.
- Phân biệt quyền truy cập Git, quyền quản lý stack/job và quyền tác động lên tài nguyên OCI.
- Tạo configuration source provider, nối repository với stack và chạy plan trước apply.
- Theo dõi thay đổi bằng commit, job và state; xử lý lỗi kết nối thường gặp.
- Áp dụng cùng quy trình khi mở rộng từ VCN sang Compute, lưu trữ hoặc cơ sở dữ liệu Oracle, có cân nhắc chi phí và tính sẵn sàng.

Ví dụ xuyên suốt là một repository GitHub riêng tư chứa cấu hình tạo **một VCN phục vụ phòng thực hành**. Bài không yêu cầu tạo máy ảo, volume, gateway hay cơ sở dữ liệu để kiểm chứng kết nối.

## 1. Git và Resource Manager đảm nhiệm phần nào?

Git lưu lịch sử **cấu hình mong muốn**: tài nguyên cần tồn tại, thuộc tính của chúng và lý do thay đổi. Resource Manager cung cấp môi trường chạy Terraform dưới dạng dịch vụ OCI, quản lý stack, job và state.

| Thành phần | Vai trò | Ví dụ trong bài |
| --- | --- | --- |
| Git repository | Lưu mã, lịch sử commit và quá trình review | `oci-iac-lab` |
| Branch | Chọn dòng phát triển được stack sử dụng | `main` |
| Working directory | Thư mục root module để chạy Terraform trong repository | `environments/dev` |
| Configuration source provider | Lưu thông tin kết nối và xác thực tới dịch vụ Git | `github-iac-lab` |
| Terraform provider OCI | Plugin hiểu tài nguyên OCI và gọi API OCI | `oracle/oci` |
| Stack | Gắn cấu hình với biến đầu vào, phiên bản Terraform và state | `oci-iac-dev` |
| Job | Một lần thực hiện plan, apply hoặc destroy | Một plan job cần review |
| State | Ánh xạ địa chỉ Terraform với tài nguyên đã quản lý | `oci_core_vcn.lab` ↔ OCID của VCN |

**Configuration source provider và Terraform provider là hai khái niệm khác nhau.** Thành phần thứ nhất giúp Resource Manager lấy mã từ Git; thành phần thứ hai giúp Terraform làm việc với OCI.

Resource Manager tự sinh và cập nhật state cho stack. Git không thay thế nơi quản lý state. Việc Git đã chứa mã của một VCN cũng không có nghĩa stack mới đã biết VCN đang tồn tại ngoài thực tế. Xem [tổng quan Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/resourcemanager.htm).

~~~mermaid
flowchart LR
    A["Sửa mã trên nhánh làm việc"] --> B["Review và merge vào main"]
    B --> C["Repository: environments/dev"]
    C --> D["Resource Manager lấy mã qua configuration source provider"]
    D --> E["Stack và biến đầu vào"]
    E --> F["Plan job"]
    F --> G["Review thay đổi"]
    G --> H["Apply dùng plan đã chọn"]
    H --> I["VCN trong compartment đích"]
    H --> J["State và lịch sử job"]
~~~

Mũi tên từ Git sang Resource Manager biểu diễn việc lấy mã khi thực hiện thao tác liên quan. **Chỉ nối Git với stack chưa thiết lập trigger để mỗi lần push tự chạy apply.** Trong bài, người vận hành chủ động tạo job; một pipeline gọi API/CLI là lớp tự động hóa bổ sung.

## 2. Chuẩn bị phạm vi thực hành và quyền truy cập

### 2.1. Những thông tin cần chốt trước

Chuẩn bị một tenancy, một region đã được tenancy đăng ký và một compartment dành riêng cho bài thực hành. Ghi lại:

| Thông tin | Ý nghĩa |
| --- | --- |
| Region thao tác Resource Manager | Nơi bạn tạo và tìm stack, configuration source provider, job |
| OCID compartment chứa stack | Vị trí quản lý đối tượng stack |
| OCID compartment chứa VCN | Đích của `var.compartment_ocid` |
| Git server URL | Endpoint của dịch vụ Git, không phải URL của một file Terraform |
| Repository URL | Đường dẫn repository mà stack sẽ đọc |
| Branch và working directory | Cặp giá trị xác định root module sẽ chạy |

Để dễ theo dõi, ví dụ dùng cùng region cho Resource Manager và VCN, đồng thời đặt stack, configuration source provider và VCN trong cùng compartment lab. Trong hệ thống thật, chúng có thể được phân tách; khi đó IAM phải bao phủ từng compartment liên quan.

**Compartment chứa stack không tự quyết định compartment của VCN.** Tài nguyên `oci_core_vcn` dùng giá trị `compartment_id` trong mã. Tương tự, region của tài nguyên do cấu hình provider quyết định; luôn đối chiếu với region đang chọn trên Console.

### 2.2. Ba lớp quyền độc lập

| Lớp | Kiểm soát điều gì? | Lỗi điển hình |
| --- | --- | --- |
| Git | Resource Manager có đọc được repository và nhánh không? | Token hết hạn, repository không hiện |
| Resource Manager IAM | Người vận hành có tạo stack, đọc source provider, chạy job không? | Không được tạo stack hoặc job |
| IAM cho tài nguyên đích | Thao tác Terraform có được quản lý VCN trong compartment đích không? | Lấy mã thành công nhưng OCI từ chối tạo VCN |

Ví dụ chính sách **cho nhóm vận hành trong compartment lab**:

~~~text
Allow group 'Default'/'IacOperators' to read orm-config-source-providers in compartment IacLab
Allow group 'Default'/'IacOperators' to manage orm-stacks in compartment IacLab
Allow group 'Default'/'IacOperators' to manage orm-jobs in compartment IacLab
Allow group 'Default'/'IacOperators' to manage virtual-network-family in compartment IacLab
~~~

Nhóm được giao quản trị kết nối Git cần thêm quyền tương ứng, chẳng hạn:

~~~text
Allow group 'Default'/'IacSourceAdmins' to manage orm-config-source-providers in compartment IacLab
~~~

Thay identity domain, tên nhóm và compartment bằng đối tượng thật. Chính sách phải được quản trị viên đặt tại vị trí có phạm vi áp dụng phù hợp. Quyền `manage virtual-network-family` bao phủ nhiều tài nguyên mạng hơn một VCN; ở đây nó giới hạn trong compartment lab, không phải mẫu phân quyền tối thiểu cho mọi hệ thống.

Quyền Resource Manager không tự cấp quyền Compute, Object Storage hay Database. Khi mở rộng bài, phải bổ sung quyền cho đúng loại tài nguyên và compartment đích. Oracle mô tả hai nhóm quyền này trong [Securing Resource Manager](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/resourcemanager_security.htm); quan hệ giữa quyền stack và job được liệt kê trong [Details for Resource Manager](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/resourcemanagerpolicyreference.htm).

## 3. Thiết kế repository để Resource Manager chạy đúng cấu hình

### 3.1. Một root module cho một phạm vi state

Bố cục đề xuất cho phòng thực hành:

~~~text
oci-iac-lab/
├── .gitignore
├── README.md
└── environments/
    └── dev/
        ├── versions.tf
        ├── providers.tf
        ├── variables.tf
        ├── main.tf
        ├── outputs.tf
        ├── terraform.tfvars.example
        └── .terraform.lock.hcl
~~~

`README.md` nên mô tả mục đích, root module, biến cần nhập, chủ sở hữu và cách dọn tài nguyên. `.terraform.lock.hcl` được sinh sau khi khởi tạo Terraform; không tự viết checksum bằng tay.

Trong bố cục này, working directory của stack là **`environments/dev`**, không phải `/environments/dev` và cũng không phải URL GitHub dạng `.../tree/main/environments/dev`.

Resource Manager yêu cầu working directory có ít nhất một file `.tf`; cấu hình không được chứa state hay thư mục `.terraform`. Nếu chọn nhầm thư mục gốc repository, các file Terraform nằm sâu trong `environments/dev` không tự trở thành root module. Xem [yêu cầu cấu hình Terraform cho Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/terraformconfigresourcemanager.htm).

Khi có production, tạo root module và stack riêng cho production, với state, compartment và quyền riêng. Không trỏ hai stack độc lập vào cùng tài nguyên thật rồi kỳ vọng Git sẽ đồng bộ state giữa chúng.

### 3.2. File nào đưa vào Git?

Đưa vào Git mã `.tf`, tài liệu, file biến mẫu không chứa bí mật và lock file của root module. Loại bỏ thư mục tải provider/module, state, plan đã lưu và thông tin xác thực.

Ví dụ `.gitignore` ở gốc repository:

~~~gitignore
# Dữ liệu làm việc và state
**/.terraform/
*.tfstate
*.tfstate.*
.terraform.tfstate.lock.info

# Plan được lưu theo quy ước của nhóm
*.tfplan
tfplan
plan.out
crash.log
crash.*.log

# Giá trị riêng theo môi trường
*.tfvars
*.tfvars.json

# Khóa và cấu hình xác thực cục bộ
*.pem
*.key
.oci/
.env
.env.*

# Không bỏ qua .terraform.lock.hcl
~~~

`terraform.tfvars.example` không khớp mẫu `*.tfvars` nên có thể được commit. Terraform cũng không tự nạp file có hậu tố `.example` này.

HashiCorp khuyến nghị commit mã và dependency lock file, đồng thời loại state, thư mục `.terraform`, saved plan và các file biến có dữ liệu nhạy cảm khỏi version control. Xem [Terraform Style Guide](https://developer.hashicorp.com/terraform/language/style).

`.gitignore` chỉ tác động tới file chưa được theo dõi. Nếu bí mật đã vào lịch sử Git, cần thu hồi hoặc xoay vòng bí mật đó trước, rồi xử lý lịch sử theo quy trình của nhóm. Xóa file ở commit mới không làm giá trị biến mất khỏi commit cũ.

## 4. Cấu hình Terraform tối thiểu cho VCN lab

Tạo các file dưới `environments/dev`. Các đoạn mã bên dưới là nội dung mẫu để người học đưa vào repository của mình.

### 4.1. Ràng buộc phiên bản

`versions.tf`:

~~~hcl
terraform {
  required_version = ">= 1.2.0, < 2.0.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 7.0"
    }
  }
}
~~~

`~> 7.0` cho phép các phiên bản provider từ `7.0.0` đến trước `8.0.0`. Đây là lựa chọn minh họa để giới hạn một major version, không phải khẳng định provider 7.x là bản mới nhất. Khi áp dụng cho dự án, nhóm chọn dải phiên bản đã kiểm chứng và Terraform runtime tương thích mà Resource Manager cung cấp.

Lock file ghi phiên bản provider thực sự được chọn cùng thông tin kiểm tra gói. Nó không thay thế ràng buộc phiên bản trong mã và không khóa phiên bản của mọi remote module. Xem [Dependency Lock File](https://developer.hashicorp.com/terraform/language/files/dependency-lock).

### 4.2. Provider và biến đầu vào

`providers.tf`:

~~~hcl
provider "oci" {
  region = var.region
}
~~~

Trong Resource Manager, provider OCI không cần nhúng user OCID, fingerprint hay private key vào mã; region là trường cấu hình bắt buộc được Oracle nêu cho cách chạy này. Cấu hình xác thực khi chạy Terraform trực tiếp trên máy cá nhân là việc riêng, không được sao chép khóa cá nhân lên Git. Xem [Terraform Configurations for Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/terraformconfigresourcemanager.htm).

`variables.tf`:

~~~hcl
variable "region" {
  description = "OCI region đã được tenancy đăng ký."
  type        = string
}

variable "compartment_ocid" {
  description = "OCID compartment đích chứa VCN lab."
  type        = string
}

variable "environment" {
  description = "Tên môi trường dùng trong tên và tag."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "environment phải là dev, test hoặc prod."
  }
}

variable "vcn_cidr" {
  description = "IPv4 CIDR dành cho VCN; cần tránh trùng mạng kết nối."
  type        = string
  default     = "10.42.0.0/16"
}

variable "owner" {
  description = "Tên nhóm chịu trách nhiệm, không dùng dữ liệu bí mật."
  type        = string
  default     = "platform-lab"
}
~~~

`terraform.tfvars.example`:

~~~hcl
region           = "ap-singapore-1"
compartment_ocid = "ocid1.compartment.oc1..REPLACE_WITH_LAB_COMPARTMENT"
environment      = "dev"
vcn_cidr         = "10.42.0.0/16"
owner            = "platform-lab"
~~~

Region và OCID ở đây là ví dụ, không phải tài khoản có sẵn. Khi tạo stack, nhập giá trị thật vào màn hình cấu hình biến. Việc commit file mẫu không làm Resource Manager tự dùng các giá trị trong file đó.

### 4.3. Tài nguyên và output

`main.tf`:

~~~hcl
resource "oci_core_vcn" "lab" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = [var.vcn_cidr]
  display_name   = format("iac-lab-%s", var.environment)
  dns_label      = "iaclab"

  freeform_tags = {
    Environment = var.environment
    Owner       = var.owner
    ManagedBy   = "Terraform"
  }
}
~~~

`outputs.tf`:

~~~hcl
output "vcn_ocid" {
  description = "OCID dùng để đối chiếu VCN được stack quản lý."
  value       = oci_core_vcn.lab.id
}

output "vcn_display_name" {
  value = oci_core_vcn.lab.display_name
}
~~~

Cấu hình chỉ khai báo một resource VCN. OCI tự tạo các đối tượng mạng mặc định đi kèm như route table, security list và DHCP options; chúng không phải ba resource Terraform riêng trong ví dụ này. Thuộc tính `cidr_blocks` và hành vi mặc định được mô tả trong [tài liệu resource oci_core_vcn](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/r/core_vcn.html).

Không thêm mật khẩu cơ sở dữ liệu hoặc private key vào output. Khi áp dụng quy trình này cho dịch vụ Database, cần thiết kế riêng cách cung cấp bí mật và kiểm soát state; đánh dấu một giá trị là nhạy cảm không đồng nghĩa bí mật được loại khỏi state.

## 5. Kiểm tra mã và tạo lịch sử Git đầu tiên

Các lệnh dưới đây dành cho người học thực hiện trong checkout của repository. Chúng không chạy apply trên máy cá nhân.

Từ gốc repository:

~~~powershell
terraform fmt -recursive
terraform -chdir=environments/dev init -backend=false
terraform -chdir=environments/dev validate
~~~

`init` tải provider/module và tạo lock file; `validate` kiểm tra cấu hình nhưng không chứng minh IAM, quota hay tính khả dụng của tài nguyên OCI. `-backend=false` giúp bước khởi tạo này phục vụ kiểm tra cục bộ, không thiết lập backend để triển khai thay stack.

Nếu cả máy cá nhân Windows và runner Linux cùng sử dụng root module, có thể chuẩn bị checksum cho các nền tảng đó:

~~~powershell
terraform -chdir=environments/dev providers lock -platform=windows_amd64 -platform=linux_amd64
~~~

Review lock file sinh ra rồi commit cùng mã. Resource Manager tự quản lý dependency lock file cho stack mới hoặc đã cập nhật; vì vậy cần kiểm tra phiên bản provider trong job log và quản lý việc nâng cấp có chủ đích, không mặc định rằng lock file cục bộ là toàn bộ cơ chế khóa của dịch vụ. Hành vi lock file và tùy chọn nâng cấp được Oracle mô tả trong [Creating a Plan Job](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-job-plan.htm).

Nếu đây là thư mục Git mới, khởi tạo rồi kiểm tra danh sách file:

~~~powershell
git init -b main
git status --short
git add .gitignore README.md environments/dev
git diff --cached --stat
git diff --cached
git commit -m "Add OCI lab VCN configuration"
git remote add origin https://github.com/YOUR_ACCOUNT/oci-iac-lab.git
git push -u origin main
~~~

Thay `YOUR_ACCOUNT` và tạo repository đích trước khi push. Nếu repository đã có lịch sử hoặc remote `origin`, dùng checkout và remote hiện có, không chạy lại các bước khởi tạo.

Trước commit, xác nhận không có state, PAT, OCI signing key hoặc plan đã lưu trong staging area. Không chèn token vào URL của `git remote`. Xác thực việc push từ máy cá nhân bằng cơ chế Git của tổ chức; cơ chế này độc lập với PAT mà Resource Manager sử dụng.

## 6. Tạo configuration source provider trên OCI

### 6.1. Chọn đúng hình thức kết nối

Resource Manager hỗ trợ các configuration source provider thuộc nhóm GitHub, GitLab và Bitbucket; OCI DevOps có luồng tạo stack riêng. Các sản phẩm và endpoint cụ thể được liệt kê trong [Managing Configuration Source Providers](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/managingconfigurationsourceproviders.htm).

Bài thực hành dùng **GitHub trên máy chủ công khai với repository riêng tư**. Hai thuộc tính này khác nhau:

- Repository riêng tư yêu cầu xác thực và quyền đọc mã.
- Git server trong mạng riêng còn yêu cầu đường mạng, phân giải DNS và tin cậy TLS từ Resource Manager.

Máy cá nhân truy cập được Git server qua VPN không chứng minh runner của Resource Manager cũng truy cập được.

### 6.2. Chuẩn bị PAT phù hợp với tích hợp GitHub

Tại tài liệu Oracle được đối chiếu cho bài, điều kiện GitHub gồm quyền admin/owner trên repository và PAT có scope `repo`. Với GitHub Enterprise Cloud, Oracle còn nêu yêu cầu SSO cho PAT. Không tự suy rằng mọi loại fine-grained PAT đều tương thích với tích hợp này.

Scope `repo` rộng hơn một quyền chỉ đọc thuần túy, dù Resource Manager chỉ đọc repository và không push thay đổi. Hãy dùng tài khoản tích hợp có phạm vi repository được kiểm soát, đặt thời hạn token và có người chịu trách nhiệm xoay vòng.

Các bước trên Console:

1. Tìm **Resource Manager → Configuration source providers**, kiểm tra region và compartment.
2. Chọn **Create configuration source provider**, đặt tên `github-iac-lab`.
3. Chọn loại **GitHub** và nhập server URL phù hợp. Với GitHub tài khoản cá nhân, ví dụ là `https://github.com`; trường này khác repository URL.
4. Nhập PAT vào trường thông tin xác thực của kết nối.
5. Tạo provider rồi mở chi tiết, chọn **Validate connection**.

Nguồn cho điều kiện, endpoint và thao tác này: [Creating a GitHub Configuration Source Provider](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-csp-github.htm).

Không lưu PAT vào `variables.tf`, `terraform.tfvars`, README, output hoặc ảnh chụp màn hình. Với Git server nội bộ, cần chuẩn bị Resource Manager private endpoint, DNS, route, luật mạng và certificate phù hợp trước khi sử dụng; không bỏ kiểm tra TLS để xử lý lỗi kết nối.

Validate connection thành công mới chứng minh kết nối có thể xác thực tới endpoint; vẫn cần xác nhận repository và branch cụ thể được phép truy cập khi tạo stack.

## 7. Tạo stack từ repository Git

Trên trang **Stacks**, chọn **Create stack** và cấu hình:

| Trường | Giá trị cho bài thực hành |
| --- | --- |
| Origin | Source code control system |
| Source code management type | GitHub |
| Configuration source provider | `github-iac-lab` |
| Repository | Repository `oci-iac-lab` của bạn |
| Branch | `main` |
| Working directory | `environments/dev` |
| Stack name | `oci-iac-dev` |
| Compartment | Compartment quản lý stack lab |
| Terraform version | Runtime dịch vụ hỗ trợ, thỏa `required_version` |

Tiếp tục tới phần biến, nhập đúng `region`, `compartment_ocid`, `environment`, `vcn_cidr` và `owner`. Review toàn bộ cấu hình rồi tạo stack. Trong bài này, **để tùy chọn Run apply tắt** nhằm xem plan trước.

Việc chọn repository/branch/working directory và nhập biến theo luồng chính thức tại [Creating a Stack from Git](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-stack-git.htm).

Nếu repository không xuất hiện, kiểm tra quyền Git và endpoint. Nếu không tìm thấy source provider, kiểm tra region, compartment và IAM trước khi tạo lại kết nối. Không đưa khóa cá nhân vào biến để thử khắc phục.

### Tạo stack bằng OCI CLI khi cần tự động hóa

Sau khi có configuration source provider, có thể tạo cùng loại stack bằng CLI. Ví dụ PowerShell dưới đây giả định OCI CLI đã được cấu hình xác thực và quyền phù hợp:

~~~powershell
$stackCompartmentOcid = "ocid1.compartment.oc1..REPLACE_STACK_COMPARTMENT"
$sourceProviderOcid = "ocid1.ormconfigsourceprovider.oc1..REPLACE_SOURCE_PROVIDER"
$targetCompartmentOcid = "ocid1.compartment.oc1..REPLACE_TARGET_COMPARTMENT"

$stackVariables = @{
    region           = "ap-singapore-1"
    compartment_ocid = $targetCompartmentOcid
    environment      = "dev"
    vcn_cidr         = "10.42.0.0/16"
    owner            = "platform-lab"
} | ConvertTo-Json -Compress

$variablesPath = Join-Path $env:TEMP "oci-iac-lab-variables.json"
[System.IO.File]::WriteAllText(
    $variablesPath,
    $stackVariables,
    [System.Text.UTF8Encoding]::new($false)
)

oci resource-manager stack create-from-git-provider `
    --compartment-id $stackCompartmentOcid `
    --config-source-configuration-source-provider-id $sourceProviderOcid `
    --config-source-repository-url "https://github.com/YOUR_ACCOUNT/oci-iac-lab.git" `
    --config-source-branch-name "main" `
    --config-source-working-directory "environments/dev" `
    --display-name "oci-iac-dev" `
    --variables ("file://" + $variablesPath)
~~~

Thay các placeholder và region trước khi chạy. Ví dụ bỏ qua `--terraform-version` để dùng mặc định của dịch vụ; trong pipeline thật, chọn runtime đã phê duyệt và truyền tùy chọn này rõ ràng. Kiểm tra stack sau khi tạo, lưu OCID trả về và xóa file biến tạm khi không cần.

Lưu ý tên tùy chọn working directory cho lệnh này là `--config-source-working-directory`. Xem [OCI CLI: create-from-git-provider](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/resource-manager/stack/create-from-git-provider.html).

## 8. Chạy plan, review rồi apply

### 8.1. Plan là điểm kiểm soát thay đổi

Mở stack, chọn **Plan**, đặt tên job dễ liên hệ với thay đổi Git và chờ kết quả. Job được tạo thành công chưa đồng nghĩa Terraform đã chạy xong.

Với stack mới và cấu hình mẫu, kỳ vọng plan đề xuất thêm một resource `oci_core_vcn.lab`. Đối chiếu:

- Compartment và region đúng môi trường.
- CIDR thuộc dải mạng dự kiến.
- Tên và tag đúng nhóm chịu trách nhiệm.
- Không có hành động destroy hoặc thay thế tài nguyên ngoài dự kiến.
- Provider và runtime đúng lựa chọn đã kiểm chứng.

Trạng thái `SUCCEEDED` của plan chỉ cho biết việc lập kế hoạch hoàn tất. Nó không phải xác nhận rằng mọi thay đổi đều được nhóm chấp nhận hoặc rằng apply chắc chắn thành công.

### 8.2. Apply tham chiếu plan đã review

Trên stack, chọn **Apply**, chọn plan job vừa review trong phần **Apply job plan resolution**, rồi chạy. Console chỉ cung cấp plan được tạo gần nhất; nếu plan thay đổi, người duyệt phải xem lại đúng plan sẽ áp dụng.

Theo dõi tới khi apply đạt `SUCCEEDED`, xem output và kiểm tra VCN trong compartment đích. Nếu thất bại, đọc log và xác định phần đã thực hiện trước khi chạy lại; thất bại không bảo đảm chưa có tài nguyên nào được tạo. Các lựa chọn apply được Oracle mô tả tại [Creating an Apply Job](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-job-apply.htm).

CLI tương đương cho phần tạo job:

~~~powershell
$stackOcid = "ocid1.ormstack.oc1..REPLACE_STACK"

oci resource-manager job create-plan-job --stack-id $stackOcid
~~~

Lưu OCID của plan job từ kết quả trả về. Sau khi job hoàn tất và plan đã được review:

~~~powershell
$planJobOcid = "ocid1.ormjob.oc1..REPLACE_REVIEWED_PLAN"

oci resource-manager job create-apply-job `
    --stack-id $stackOcid `
    --execution-plan-strategy $planJobOcid
~~~

Tham số `--execution-plan-strategy` trong lệnh tiện ích này nhận OCID plan job để tham chiếu plan. Không thay bằng chuỗi `FROM_PLAN_JOB_ID` rồi bỏ thiếu ID. Xem [tham chiếu CLI create-apply-job](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/resource-manager/job/create-apply-job.html).

### 8.3. Kiểm soát nhánh thay đổi giữa plan và apply

Oracle nêu rằng job dùng commit mới nhất đối với cấu hình lưu ở hệ thống quản lý mã nguồn. Vì vậy, **stack trỏ vào `main` không có nghĩa đã khóa vào một commit cố định**. Xem [hành vi lấy mã của plan job](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-job-plan.htm).

Quy trình vận hành nên:

1. Ghi nhận commit dự định triển khai và cấu hình nguồn của stack trước plan.
2. Hạn chế thay đổi trên nhánh triển khai trong cửa sổ review/apply.
3. Giữ nguyên biến stack, dependency và provider giữa hai bước.
4. Chọn plan đã review thay vì chạy apply tự phê duyệt.
5. Nếu mã, biến hoặc dependency thay đổi, tạo plan mới và review lại.

Tham chiếu saved plan giúp chỉ rõ kế hoạch được chọn; nó không biến branch Git thành định danh bất biến hay làm các dependency ngoài Git tự cố định. Nếu cần bằng chứng, kiểm tra cấu hình thực tế gắn với job và thông tin nguồn mà dịch vụ cung cấp; không chỉ lấy HEAD hiện tại rồi gán ngược cho một job đã chạy trước đó.

## 9. Đưa một thay đổi qua Git và kiểm chứng tính lặp lại

Sau lần apply đầu, thử đổi tag chủ sở hữu trong `main.tf` bằng cách sửa:

~~~hcl
Owner = format("%s-team", var.owner)
~~~

Thực hiện theo nhánh làm việc:

~~~powershell
git switch -c change/lab-owner-tag
terraform fmt -recursive
terraform -chdir=environments/dev validate
git add environments/dev/main.tf
git diff --cached
git commit -m "Clarify owner tag for OCI lab VCN"
git push -u origin change/lab-owner-tag
~~~

Tạo pull request, review rồi merge vào `main`. Sau merge, chủ động chạy plan mới trên stack. Thay đổi dự kiến là cập nhật tag của VCN; nếu plan đề xuất tạo thêm VCN hoặc thay thế VCN, dừng lại để kiểm tra state, địa chỉ resource và cấu hình nguồn.

Sau apply thành công, chạy thêm một plan khi không có thay đổi mã, biến hay tài nguyên ngoài luồng. Kỳ vọng không còn thay đổi cần thực hiện. Nếu vẫn có diff, xem xét drift, thuộc tính do dịch vụ chuẩn hóa hoặc đầu vào chưa được kiểm soát.

Git revert tạo một phiên bản cấu hình khác; nó **không tự phục hồi hạ tầng**. Muốn áp dụng mã đã revert vẫn cần plan và apply. Với Compute có dữ liệu, volume hay cơ sở dữ liệu Oracle, khôi phục mã còn phải xét tương thích, backup và tác động gián đoạn.

## 10. Quản lý nhiều môi trường, bí mật và bằng chứng vận hành

### 10.1. Tách state theo môi trường và phạm vi trách nhiệm

| Nội dung | Dev | Production |
| --- | --- | --- |
| Root module | `environments/dev` | `environments/prod` |
| Stack/state | Stack dev riêng | Stack production riêng |
| Compartment đích | Lab hoặc dev | Compartment production |
| Thay đổi Git | Review theo quy trình nhóm | Review và quyền merge chặt hơn |
| Apply | Người được giao vận hành dev | Danh tính triển khai được phân quyền riêng |

Đây là thiết kế gợi ý, không phải khả năng tự suy ra môi trường từ tên branch. Biến `environment = "prod"` chỉ thay đổi cách mã sử dụng biến; nó không tự di chuyển tài nguyên sang compartment production.

Một stack mới tạo từ cùng repository sẽ có state riêng. Không dùng việc tạo lại stack như cách sửa lỗi một stack đang quản lý tài nguyên thật; nếu cần chuyển quyền quản lý, phải thực hiện quy trình di chuyển/import state thích hợp.

### 10.2. Giữ bí mật ngoài mã và kiểm soát state

PAT đọc Git và OCI credential của hệ thống gọi CLI là hai bí mật khác nhau. Thu hồi một loại không tự thu hồi loại kia. Phân công người sở hữu, theo dõi ngày hết hạn và thử lại kết nối sau khi xoay vòng PAT.

Không coi toàn bộ stack variables là kho bí mật. Với bài này, chúng chỉ chứa region, compartment và các chuỗi cấu hình không bí mật. Khi mở rộng tới Database, dùng cơ chế quản lý bí mật được tổ chức phê duyệt, đồng thời đánh giá dữ liệu nào Terraform sẽ lưu trong state.

Quyền đọc job cũng cần giới hạn: theo [tham chiếu quyền Resource Manager](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/resourcemanagerpolicyreference.htm), nhóm quyền `read orm-jobs` bao gồm thao tác lấy log, cấu hình, plan và state của job. Không chia sẻ các bản tải xuống này như tài liệu công khai.

### 10.3. Liên hệ thay đổi mã với tài nguyên và chi phí

Cho mỗi lần triển khai, lưu trong hệ thống theo dõi thay đổi của nhóm:

- Pull request và commit đã dự định triển khai.
- Repository, branch, working directory và stack OCID.
- Plan job OCID được review, apply job OCID và kết quả.
- Region, compartment đích, phiên bản Terraform/provider.
- Người thực hiện, người review và thay đổi đáng chú ý về tài nguyên.

Job log phục vụ chẩn đoán; lịch sử Git phục vụ giải thích thay đổi; OCI Audit phục vụ truy vết thao tác API. Chúng bổ sung cho nhau, không thay thế nhau.

Khi tái sử dụng quy trình cho Compute, lưu trữ và cơ sở dữ liệu, review cả shape, số lượng, dung lượng và phương án dự phòng. Plan mô tả thao tác hạ tầng, không phải báo giá đầy đủ hay bằng chứng tính sẵn sàng. Một commit thêm replica hoặc tăng dung lượng có thể tạo chi phí dù pipeline chạy thành công.

## 11. Chẩn đoán lỗi theo từng lớp

| Biểu hiện | Điểm cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Validate connection thất bại | Endpoint, PAT, hạn token, SSO | Sửa đúng kết nối, cấp lại token theo quy trình và validate lại |
| Kết nối hợp lệ nhưng không thấy repository | Phạm vi tài khoản/token, tổ chức sở hữu | Cấp quyền vào repository cụ thể; phân biệt server URL với repo URL |
| Không thấy source provider hoặc stack | Region, compartment, quyền IAM | Chọn lại đúng phạm vi và xác nhận quyền cần thiết |
| Không tìm thấy cấu hình Terraform | Branch và working directory | Kiểm tra thư mục được chọn có `.tf`; dùng đường dẫn tương đối |
| Git nội bộ bị timeout hoặc lỗi TLS | DNS, private endpoint, route, luật mạng, certificate | Kiểm tra đường truy cập từ dịch vụ; giữ kiểm tra TLS |
| Clone root repository được nhưng module tải lỗi | URL/ref module và quyền vào repository module | Kiểm tra từng nguồn phụ thuộc, không nhúng credential vào URL |
| Plan/apply báo NotAuthorizedOrNotFound | Quyền tài nguyên đích, OCID, region | Kiểm tra cả quyền lẫn sự tồn tại và vị trí tài nguyên |
| Apply thất bại sau khi đã tạo một phần | Log, tài nguyên đã có, state | Xác định bước lỗi, sửa nguyên nhân và plan lại trên chính stack |
| Mã mới không xuất hiện trong plan | Chưa push/merge, sai branch hoặc sai stack | Đối chiếu nguồn và cấu hình job thực tế |
| Provider không đúng dự kiến | Version constraint, lock và tùy chọn upgrade | Review phiên bản trong log; nâng cấp qua thay đổi có kiểm soát |

Với module trong private Git repository trên public Git server, Oracle mô tả khả năng cài module không cần credential trong source URL khi configuration source provider có quyền vào repository đó. Không suy rộng điều này thành mọi mô hình SSH hoặc mọi Git server riêng đều hoạt động giống nhau. Xem [Modules from Private Git Repositories](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-stack-git.htm#).

Tránh xử lý lỗi bằng cách cấp `manage all-resources in tenancy`, xóa state hoặc tạo stack trùng để thử lại. Các thao tác đó làm khó xác định nguyên nhân và có thể dẫn tới tài nguyên ngoài kiểm soát.

## 12. Tiêu chí hoàn thành và dọn phòng thực hành

Một lần thực hành hoàn chỉnh có đủ các dấu hiệu:

- Repository có mã, file biến mẫu và lock file; không có token, khóa cá nhân, state hoặc saved plan.
- Configuration source provider kết nối thành công và stack đọc đúng branch/thư mục.
- Plan đầu được review; apply tham chiếu plan đó và kết thúc thành công.
- Output OCID khớp VCN thực tế trong compartment/region đích.
- Thay đổi tag đi qua Git, được plan/apply và có thể truy vết tới job.
- Plan cuối không còn thay đổi khi mã, biến và hạ tầng giữ nguyên.

Khi kết thúc lab, dùng quy trình **Destroy** trên chính stack lab sau khi kiểm tra phạm vi tài nguyên và các phụ thuộc. Chỉ thực hiện khi VCN không được workload khác sử dụng. Theo dõi job, kiểm tra tài nguyên đã được dọn, rồi mới cân nhắc xóa stack và source provider không còn dùng chung.

Xóa repository hoặc configuration source provider không phải thao tác destroy hạ tầng. Xóa stack cũng không được dùng thay cho việc xác nhận tài nguyên đã dọn. Giữ đủ lịch sử và bằng chứng của lần triển khai cho tới khi hoàn tất công việc vận hành.

Sau bài này, một thay đổi hạ tầng OCI cần được nhận diện bằng cả **phiên bản mã, cấu hình stack và kết quả job**. Khi phạm vi mở rộng tới Compute, lưu trữ và Database, giữ nguyên kỷ luật đó, đồng thời bổ sung phân quyền, giám sát, kiểm soát chi phí và phương án duy trì dịch vụ tương ứng.
