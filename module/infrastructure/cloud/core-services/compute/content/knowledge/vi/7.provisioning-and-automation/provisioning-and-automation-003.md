# Mẫu khai báo, biến đầu vào và tái sử dụng cấu hình máy

Khi một nhóm phải tạo nhiều máy ảo cho development, staging và production, việc cấu hình từng máy bằng thao tác thủ công rất dễ dẫn đến sai khác. Một máy có thể thiếu bản vá, máy khác mở cổng mạng quá rộng, hoặc môi trường production dùng nhầm kích thước máy. **Mẫu khai báo (declarative template)** giúp mô tả trạng thái hạ tầng mong muốn bằng mã. **Biến đầu vào** cho phép thay đổi những giá trị cần thiết theo workload hoặc môi trường, còn **module và mẫu dùng lại** giúp nhiều nhóm triển khai theo cùng một chuẩn.

Trong cloud compute, cấu hình máy không chỉ gồm số CPU và RAM. Một máy ảo còn có image hệ điều hành, vùng và subnet, security group, đĩa, danh tính, metadata, script khởi tạo, nhãn quản trị và chính sách giám sát. Nếu các giá trị này được khai báo rõ ràng, nhóm có thể xem xét thay đổi trước khi áp dụng, tái tạo môi trường và truy vết cấu hình theo phiên bản.

Bài học thuộc module **CLOUD_CORE_SERVICES_COMPUTE**, tập trung vào cách mô tả, tham số hóa và tái sử dụng cấu hình máy trong quy trình cấp phát và tự động hóa. Ví dụ chính dùng Terraform để minh họa biến, local value, output và module; cloud-init được dùng để minh họa mẫu khởi tạo bên trong VM. Các khái niệm này cũng áp dụng cho công cụ IaC và nền tảng cloud khác, dù cú pháp cụ thể có thể khác.

## 1. Vì sao cần mẫu cấu hình máy?

Một máy ảo thường được tạo từ nhiều quyết định:

- Image và phiên bản hệ điều hành.
- Loại instance, số vCPU và dung lượng RAM.
- Vùng, subnet, địa chỉ IP và security group.
- Đĩa khởi động, loại lưu trữ, dung lượng và mã hóa.
- Danh tính máy hoặc instance role để gọi dịch vụ cloud.
- User-data hoặc cloud-init để cấu hình lần khởi động đầu tiên.
- Nhãn môi trường, chủ sở hữu, ứng dụng và trung tâm chi phí.
- Cấu hình giám sát, logging, backup và cập nhật.

Nếu mỗi kỹ sư tự tạo máy theo trí nhớ, những thông số quan trọng dễ bị bỏ sót. Mẫu cấu hình giải quyết vấn đề bằng cách xác định những thuộc tính bắt buộc và những điểm được phép tùy chỉnh.

Ví dụ, một tổ chức có thể quy định mọi VM ứng dụng phải dùng image đã phê duyệt, đĩa mã hóa, không mở SSH/RDP ra Internet, có tag owner và environment, đồng thời dùng instance identity thay cho khóa truy cập tĩnh. Nhóm phát triển vẫn có thể chọn kích thước máy phù hợp với tải trong một danh sách được cho phép.

Mẫu tốt mang lại các lợi ích:

1. **Nhất quán:** các môi trường tuân theo cùng baseline.
2. **Tái tạo:** có thể tạo lại máy hoặc môi trường từ mã đã lưu.
3. **Kiểm tra trước:** thay đổi được xem xét qua diff và plan trước khi triển khai.
4. **Truy vết:** biết ai thay đổi cấu hình, thay đổi gì và vì sao.
5. **Tái sử dụng:** cùng một module có thể phục vụ nhiều ứng dụng.
6. **Giảm lỗi thao tác:** hạn chế nhập sai giá trị hoặc quên bước cấu hình.
7. **Quản lý quy mô:** có thể áp dụng chính sách chung cho nhiều VM và nhiều môi trường.

Tự động hóa không tự động làm cấu hình an toàn. Một mẫu sai có thể nhân bản lỗi trên hàng trăm máy. Vì vậy, cần kiểm thử, review, quản lý phiên bản và kiểm soát quyền trước khi dùng rộng rãi.

## 2. Mô tả khai báo và mô tả mệnh lệnh

Có hai cách phổ biến để mô tả việc cấp phát hạ tầng.

**Mô tả mệnh lệnh (imperative)** nêu các bước cần thực hiện theo thứ tự, ví dụ gọi API tạo VM, gắn đĩa, cấu hình mạng rồi thêm tag. Người viết phải quản lý thứ tự, trạng thái hiện tại và cách xử lý khi một bước chạy lại.

**Mô tả khai báo (declarative)** nêu trạng thái mong muốn, ví dụ một VM có image đã chọn, hai vCPU, 4 GiB RAM, một đĩa mã hóa và nằm trong subnet riêng. Công cụ đọc trạng thái mong muốn, so sánh với trạng thái thực tế rồi xác định thao tác cần thực hiện.

| Tiêu chí | Mệnh lệnh | Khai báo |
|---|---|---|
| Trọng tâm | Các bước phải chạy | Trạng thái cuối cần đạt |
| Quản lý trạng thái | Thường do script hoặc người viết tự xử lý | Công cụ IaC thường theo dõi trạng thái tài nguyên |
| Chạy lại | Cần tự thiết kế để tránh tạo trùng hoặc gây lỗi | Thường có cơ chế hội tụ về trạng thái khai báo |
| Xem trước thay đổi | Phải tự xây dựng | Công cụ có thể tạo plan hoặc diff |
| Phù hợp | Tác vụ tuần tự, bootstrap hoặc thao tác chuyên biệt | Quản lý hạ tầng lặp lại, có cấu trúc và cần review |

Khai báo không có nghĩa là công cụ không thực hiện các bước bên dưới. Công cụ vẫn gọi API theo thứ tự phụ thuộc, nhưng người dùng tập trung mô tả kết quả mong muốn. Các script imperative vẫn hữu ích cho một số tác vụ khởi tạo hoặc tích hợp; nên đặt chúng trong phạm vi rõ ràng và có thể kiểm soát.

Một quy trình cấp phát khai báo thường diễn ra theo luồng sau:

~~~mermaid
flowchart TD
    A["Yêu cầu workload"] --> B["Chọn baseline và image"]
    B --> C["Cung cấp input variables"]
    C --> D["Render module và template"]
    D --> E["Validate và kiểm tra policy"]
    E --> F["Tạo plan / diff"]
    F --> G{"Được review và phê duyệt?"}
    G -- "Không" --> H["Điều chỉnh cấu hình"]
    H --> C
    G -- "Có" --> I["Apply hạ tầng"]
    I --> J["Bootstrap và kiểm tra VM"]
    J --> K["Theo dõi drift và vòng đời"]
~~~

## 3. Các thành phần của một mẫu khai báo

Một mẫu cấp phát máy có thể được chia thành các phần:

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| Resource | Khai báo tài nguyên cần tạo hoặc quản lý | VM, disk, NIC, security group |
| Input variable | Nhận giá trị từ bên gọi hoặc môi trường | image ID, instance type, subnet ID |
| Local value | Tạo giá trị dẫn xuất dùng nội bộ | tên máy, tag chung, tên resource |
| Output | Công bố thông tin cần cho thành phần khác | instance ID, private IP |
| Data source | Đọc thông tin của tài nguyên đã tồn tại | image được phê duyệt, subnet có sẵn |
| Module | Đóng gói nhóm resource và giao diện đầu vào/đầu ra | module tạo compute instance |
| Template | Mẫu nội dung có placeholder được thay bằng giá trị | cloud-init, user-data hoặc file cấu hình |

Một mẫu tốt có giao diện rõ ràng. Người dùng cần biết biến nào bắt buộc, biến nào có mặc định, giá trị hợp lệ là gì, output nào được cung cấp và những tài nguyên nào sẽ được tạo.

### 3.1. Biến đầu vào

Biến đầu vào (input variable hoặc parameter) giúp tách phần cấu trúc dùng chung khỏi những giá trị thay đổi theo lần triển khai.

Các giá trị thường được tham số hóa:

- Image ID hoặc phiên bản image.
- Instance type hoặc nhóm cấu hình CPU/RAM.
- Subnet, security group và vùng triển khai.
- Dung lượng đĩa và loại volume.
- Tên máy, môi trường, owner và application.
- Số lượng replica hoặc số VM.
- Cấu hình khởi tạo không chứa bí mật.

Không nên biến mọi chuỗi trong mẫu thành input. Nếu một giá trị luôn phải theo chuẩn tổ chức, hãy giữ nó trong module hoặc policy chung. Quá nhiều biến làm giao diện phức tạp và cho phép người gọi vô tình phá vỡ baseline.

### 3.2. Kiểu dữ liệu, mặc định và mô tả

Khai báo kiểu giúp công cụ phát hiện giá trị sai trước khi gọi API. Những kiểu thường gặp gồm string, number, bool, list, map, object và set.

Ví dụ:

~~~hcl
variable "instance_type" {
  description = "Loại máy tính toán được phê duyệt cho workload"
  type        = string
  default     = "t3.small"
}

variable "root_volume_gib" {
  description = "Dung lượng đĩa khởi động tính bằng GiB"
  type        = number
  default     = 30
}

variable "security_group_ids" {
  description = "Danh sách security group gắn vào máy"
  type        = list(string)
}

variable "enable_monitoring" {
  description = "Bật giám sát chi tiết nếu nền tảng hỗ trợ"
  type        = bool
  default     = true
}
~~~

Biến có default là tùy chọn với người gọi; biến không có default thường phải được cung cấp. Mặc định nên an toàn và hợp lý. Không nên đặt một subnet production, image cũ hoặc quyền truy cập rộng làm mặc định chung chỉ để mẫu dễ chạy.

### 3.3. Kiểm tra giá trị đầu vào

Validation giúp phát hiện lỗi cấu hình sớm. Có thể kiểm tra dải số, danh sách lựa chọn, định dạng tên hoặc mối quan hệ giữa các biến.

~~~hcl
variable "environment" {
  description = "Môi trường triển khai"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment phải là dev, staging hoặc prod."
  }
}

variable "root_volume_gib" {
  description = "Dung lượng đĩa khởi động tính bằng GiB"
  type        = number
  default     = 30

  validation {
    condition     = var.root_volume_gib >= 20 && var.root_volume_gib <= 500
    error_message = "root_volume_gib phải nằm trong khoảng 20 đến 500 GiB."
  }
}
~~~

Validation trong module kiểm tra tính hợp lệ của giá trị, nhưng không thay thế policy ở cấp tổ chức. Ví dụ, việc một security group ID đúng định dạng không chứng minh rằng rule bên trong chỉ mở các cổng cần thiết.

### 3.4. Local values

Local value là giá trị dẫn xuất được đặt tên để tránh lặp biểu thức và giữ cấu hình dễ đọc. Local không phải input của người dùng.

~~~hcl
locals {
  name_prefix = "${var.environment}-${var.application}"

  common_tags = {
    Environment = var.environment
    Application = var.application
    ManagedBy   = "Terraform"
  }
}
~~~

Nếu tên máy, tag hoặc một biểu thức được dùng nhiều nơi, local giúp thay đổi ở một chỗ. Tuy nhiên, không nên tạo nhiều tầng local chỉ để che giấu biểu thức đơn giản.

### 3.5. Outputs

Output công bố thông tin mà module khác hoặc quy trình tiếp theo cần sử dụng. Ví dụ, module tạo VM có thể trả về instance ID, private IP và tên DNS. Không nên output private key, password hoặc dữ liệu bí mật.

~~~hcl
output "instance_id" {
  description = "ID của máy ảo được tạo"
  value       = aws_instance.this.id
}

output "private_ip" {
  description = "Địa chỉ IP riêng của máy"
  value       = aws_instance.this.private_ip
}
~~~

Output tạo ra hợp đồng rõ ràng giữa module và thành phần gọi. Người gọi không cần biết toàn bộ chi tiết nội bộ của module.

## 4. Biến đầu vào và quản lý theo môi trường

Một cấu trúc hạ tầng có thể được dùng cho nhiều môi trường. Phần cấu trúc nên giống nhau, còn các giá trị như image, subnet, instance type, số lượng máy và tag có thể khác.

Ví dụ:

| Thuộc tính | Development | Staging | Production |
|---|---|---|---|
| Instance type | Nhỏ, tối ưu chi phí | Gần production để kiểm thử | Theo tải và SLO |
| Image | Bản đã phê duyệt mới nhất trong kênh test | Bản đã kiểm thử | Bản phát hành đã phê duyệt |
| Subnet | Mạng dev riêng | Mạng staging riêng | Private subnet production |
| Số lượng | Một hoặc ít replica | Gần cấu hình production | Theo tải và HA |
| Logging | Đủ cho debug | Giữ log kiểm thử | Theo retention và yêu cầu audit |
| Backup | Theo nhu cầu dữ liệu test | Theo quy trình kiểm thử phục hồi | Theo RPO/RTO |
| Quyền | Giới hạn theo nhóm dev | Giới hạn theo nhóm kiểm thử | Theo quy trình production |

Có thể dùng các file biến riêng, chẳng hạn dev.tfvars, staging.tfvars và prod.tfvars. Các file này chỉ chứa giá trị khác nhau; cấu trúc resource vẫn nằm trong cùng module.

Ví dụ file dev.tfvars:

~~~hcl
environment        = "dev"
application        = "catalog"
ami_id             = "ami-0123456789abcdef0"
instance_type      = "t3.small"
subnet_id          = "subnet-0123456789abcdef0"
security_group_ids = ["sg-0123456789abcdef0"]
hostname           = "catalog-dev-01"
root_volume_gib    = 30
~~~

Các ID trên chỉ là giá trị minh họa theo định dạng quen thuộc của AWS, không phải tài nguyên có thật. Khi triển khai, phải dùng ID thuộc đúng tài khoản, vùng và môi trường. Với production, cần review file biến và plan trước khi áp dụng.

Không nên sao chép toàn bộ thư mục cấu hình cho từng môi trường rồi chỉnh sửa thủ công. Cách đó dễ làm các bản sao lệch nhau theo thời gian. Hãy dùng chung module và cung cấp input riêng cho từng môi trường.

## 5. Đóng gói cấu hình thành module có thể tái sử dụng

Module là một đơn vị cấu hình được đóng gói để thực hiện một nhiệm vụ rõ ràng. Trong Terraform, thư mục chứa một hoặc nhiều file .tf được xem là một module. Root module gọi các child module để tổ chức hệ thống thành những phần có trách nhiệm riêng.

Ví dụ, một module compute-instance có thể nhận image, loại máy, subnet, security group, hostname và tag; module chịu trách nhiệm tạo VM cùng đĩa mã hóa. Nhiều ứng dụng có thể gọi module đó với các giá trị khác nhau.

Một cấu trúc thư mục minh họa:

~~~text
infrastructure/
├── environments/
│   ├── dev/
│   │   ├── main.tf
│   │   └── dev.tfvars
│   ├── staging/
│   │   ├── main.tf
│   │   └── staging.tfvars
│   └── prod/
│       ├── main.tf
│       └── prod.tfvars
└── modules/
    └── compute-instance/
        ├── main.tf
        ├── variables.tf
        ├── outputs.tf
        └── cloud-init.yaml.tftpl
~~~

Root module chứa cấu hình của một môi trường và gọi module dùng chung. Child module định nghĩa resource, biến và output. Cấu trúc thư mục có thể thay đổi theo quy mô dự án; mục tiêu là phân định rõ phần dùng chung và phần thuộc môi trường.

### 5.1. Thiết kế giao diện module

Một module nên có phạm vi đủ nhỏ để mô tả một trách nhiệm, nhưng không nhỏ đến mức người dùng phải nối quá nhiều module vụn vặt. Ví dụ, module compute-instance có thể tạo một máy ảo hoàn chỉnh; module lớn hơn có thể tạo nhóm web server và load balancer nếu chúng luôn được quản lý như một đơn vị.

Giao diện module cần:

- Tên biến phản ánh ý nghĩa nghiệp vụ, không chỉ tên trường API của provider.
- Kiểu dữ liệu và mô tả rõ ràng.
- Mặc định an toàn cho những input thật sự có thể mặc định.
- Validation cho giá trị và quan hệ quan trọng.
- Output tối thiểu nhưng đủ dùng.
- Phiên bản module và hướng dẫn thay đổi tương thích.

Không nên đưa quá nhiều logic riêng của một ứng dụng vào module dùng chung. Những phần đặc thù có thể được truyền qua input có kiểm soát hoặc đặt ở root module.

### 5.2. Tái sử dụng mà vẫn giữ được khác biệt

Tái sử dụng không có nghĩa mọi VM phải giống hệt nhau. Module cung cấp cấu trúc chung, còn biến đầu vào thể hiện khác biệt hợp lệ.

Ví dụ:

- API cần nhiều CPU hơn worker xử lý file.
- Production cần nhiều replica và backup chặt hơn dev.
- VM xử lý dữ liệu cần đĩa lớn, VM proxy cần băng thông mạng cao.
- Một ứng dụng cần image Linux, ứng dụng khác cần Windows Server.

Hãy tạo input cho khác biệt có chủ đích. Nếu có một ngoại lệ hiếm, hãy cân nhắc module chuyên biệt hoặc một biến tùy chọn có giới hạn rõ ràng thay vì thêm nhiều nhánh logic khó hiểu vào module chung.

## 6. Ví dụ: module Terraform tạo một máy ảo

Ví dụ sau dùng provider AWS để minh họa resource VM. Cấu trúc module và cách dùng biến áp dụng tương tự cho provider khác, nhưng tên resource, trường cấu hình và quy tắc bảo mật sẽ khác. Mẫu giả định subnet và security group đã được tạo ở nơi khác; module chỉ tạo EC2 instance.

### 6.1. variables.tf

~~~hcl
variable "ami_id" {
  description = "ID của image đã được phê duyệt"
  type        = string
}

variable "instance_type" {
  description = "Loại EC2 instance"
  type        = string
  default     = "t3.small"
}

variable "subnet_id" {
  description = "Subnet nơi đặt instance"
  type        = string
}

variable "security_group_ids" {
  description = "Các security group được gắn vào instance"
  type        = list(string)
}

variable "hostname" {
  description = "Tên máy được cấu hình trong guest"
  type        = string
}

variable "environment" {
  description = "Tên môi trường triển khai"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment phải là dev, staging hoặc prod."
  }
}

variable "root_volume_gib" {
  description = "Dung lượng root volume"
  type        = number
  default     = 30

  validation {
    condition     = var.root_volume_gib >= 20 && var.root_volume_gib <= 500
    error_message = "root_volume_gib phải nằm trong khoảng 20 đến 500 GiB."
  }
}

variable "tags" {
  description = "Các tag bổ sung cho instance"
  type        = map(string)
  default     = {}
}
~~~

Các biến bắt buộc như ami_id, subnet_id và security_group_ids không có default. Người gọi phải cung cấp chúng, giúp tránh việc module tự chọn nhầm mạng hoặc image.

### 6.2. main.tf

~~~hcl
locals {
  common_tags = {
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_instance" "this" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = var.security_group_ids

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    hostname    = var.hostname
    environment = var.environment
  })

  root_block_device {
    volume_size = var.root_volume_gib
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = merge(local.common_tags, var.tags, {
    Name = var.hostname
  })
}
~~~

Resource dùng input để cấu hình máy. Local value tạo tag chung; merge kết hợp tag chung với tag do người gọi truyền. Trong ví dụ này, tag Name được đặt sau cùng nên giá trị hostname là giá trị cuối cùng. Module bật mã hóa root volume và yêu cầu token IMDSv2 trên instance AWS. Các thuộc tính này là ví dụ theo AWS provider; cần kiểm tra phiên bản provider và chính sách của tổ chức trước khi sử dụng.

### 6.3. cloud-init.yaml.tftpl

~~~yaml
#cloud-config
preserve_hostname: false
hostname: ${hostname}
package_update: true
packages:
  - nginx
  - curl
write_files:
  - path: /etc/motd
    permissions: "0644"
    content: |
      Environment: ${environment}
runcmd:
  - [systemctl, enable, --now, nginx]
~~~

Đây là template cloud-init được Terraform render bằng templatefile. Các placeholder hostname và environment nhận giá trị từ map truyền vào. File template chỉ chứa cấu hình khởi tạo không bí mật. Không đặt password, private key hoặc token trong template hay user-data.

### 6.4. outputs.tf

~~~hcl
output "instance_id" {
  description = "ID của instance"
  value       = aws_instance.this.id
}

output "private_ip" {
  description = "Địa chỉ IP riêng của instance"
  value       = aws_instance.this.private_ip
}

output "instance_arn" {
  description = "ARN của instance"
  value       = aws_instance.this.arn
}
~~~

### 6.5. Gọi module từ root module

~~~hcl
module "catalog_vm" {
  source = "../../modules/compute-instance"

  ami_id             = var.catalog_ami_id
  instance_type      = var.catalog_instance_type
  subnet_id          = var.private_subnet_id
  security_group_ids = [aws_security_group.catalog.id]
  hostname           = "catalog-${var.environment}-01"
  environment        = var.environment
  root_volume_gib    = 40

  tags = {
    Application = "catalog"
    Owner       = "commerce-platform"
  }
}
~~~

Root module truyền các giá trị theo môi trường và workload. Module có thể được gọi nhiều lần cho các VM khác nhau mà không phải sao chép resource. Nếu cần nhiều instance giống nhau, có thể dùng for_each hoặc count ở nơi gọi, nhưng phải xác định khóa ổn định để tránh thay thế tài nguyên ngoài ý muốn khi danh sách thay đổi.

## 7. Tạo cấu hình máy theo danh sách hoặc ma trận

Một hệ thống có thể có nhiều nhóm máy với vai trò khác nhau: web, worker, batch và monitoring. Có thể mô tả mỗi nhóm bằng một object gồm số lượng, loại instance, image và tag.

Ví dụ về dữ liệu cấu hình:

~~~hcl
variable "node_pools" {
  description = "Cấu hình các nhóm máy theo vai trò"
  type = map(object({
    instance_type = string
    desired_count = number
    ami_id         = string
    volume_gib     = number
  }))
}
~~~

Một file biến có thể khai báo:

~~~hcl
node_pools = {
  web = {
    instance_type = "t3.small"
    desired_count = 2
    ami_id         = "ami-0123456789abcdef0"
    volume_gib     = 30
  }
  worker = {
    instance_type = "t3.medium"
    desired_count = 3
    ami_id         = "ami-0123456789abcdef0"
    volume_gib     = 50
  }
}
~~~

Cấu trúc object giúp người đọc thấy rõ những thuộc tính cần có cho mỗi nhóm máy. Có thể dùng for_each để tạo resource hoặc gọi module theo từng phần tử. Tuy nhiên, cần xem xét liệu các nhóm có cùng vòng đời và chính sách hay không. Nếu web và worker có cách triển khai, scale và backup khác nhau, có thể quản lý chúng bằng các module riêng dù cùng dùng một module compute cơ sở.

Không nên đưa danh sách tùy ý từ người dùng vào mọi trường cấu hình. Hãy kiểm soát các giá trị được phép, ví dụ danh sách instance type, image đã phê duyệt và subnet hợp lệ cho từng môi trường.

## 8. Tái sử dụng image và cấu hình khởi tạo

Module IaC mô tả tài nguyên cloud; machine image cung cấp hệ điều hành và phần mềm nền; cloud-init hoặc bootstrap script cấu hình instance khi khởi động. Ba lớp này bổ sung cho nhau:

| Lớp | Trách nhiệm | Ví dụ |
|---|---|---|
| Machine image | Hệ điều hành, package nền và agent đã chuẩn hóa | Linux image có monitoring agent và bản vá đã kiểm thử |
| IaC module/template | Tài nguyên cloud và kết nối giữa chúng | VM, subnet, security group, disk và instance role |
| Bootstrap/configuration | Cấu hình riêng của instance và ứng dụng | hostname, package bổ sung, service và cấu hình runtime |

Không nên cài lại toàn bộ hệ điều hành và package lớn mỗi lần VM khởi động nếu có thể chuẩn bị image đã kiểm thử. Bootstrap nên tập trung vào cấu hình theo instance hoặc những bước cần thay đổi theo môi trường.

Với Windows, có thể dùng EC2Launch, cloudbase-init, PowerShell hoặc agent bootstrap của nhà cung cấp. Với Linux, cloud-init là lựa chọn phổ biến. Cần bảo đảm script chạy an toàn khi khởi động lại hoặc có cơ chế kiểm soát lần chạy.

## 9. Tách cấu hình khỏi bí mật

Một lỗi nghiêm trọng là đặt password, access key, private key hoặc token trực tiếp trong file .tf, file tfvars, user-data hay template. Những giá trị này có thể bị lưu trong Git, log, plan hoặc state.

Nên áp dụng các nguyên tắc:

- Chỉ lưu trong mã những giá trị cấu hình không nhạy cảm.
- Dùng IAM role, instance profile hoặc managed identity để cấp quyền cho workload.
- Lưu bí mật trong secret manager hoặc vault được tổ chức phê duyệt.
- Cho VM lấy bí mật khi chạy bằng danh tính riêng và quyền tối thiểu.
- Tránh output bí mật từ module.
- Bảo vệ state file và plan artifact vì chúng có thể chứa dữ liệu nhạy cảm.
- Không commit file tfvars có secret vào repository.

Trong Terraform, thuộc tính sensitive = true giúp che giá trị trong một số output của CLI, nhưng không tự mã hóa hoặc loại bỏ giá trị khỏi state. Cần dùng backend state an toàn, mã hóa khi lưu, kiểm soát quyền đọc, bật locking khi backend hỗ trợ và lưu trữ bản sao theo chính sách.

## 10. Quản lý trạng thái và thay đổi hạ tầng

Với công cụ IaC có state như Terraform, state liên kết cấu hình khai báo với tài nguyên thực tế. Nó giúp công cụ biết resource nào đã được tạo, ID của resource và những thuộc tính cần theo dõi.

State là thành phần quan trọng:

- Dùng remote backend khi nhiều người cùng quản lý hạ tầng.
- Bật state locking nếu backend hỗ trợ để tránh hai lần apply đồng thời.
- Mã hóa state khi lưu và giới hạn quyền truy cập.
- Sao lưu state và có quy trình khôi phục.
- Không chỉnh sửa state bằng tay nếu chưa hiểu tác động và chưa có backup.
- Không dùng chung một state cho các môi trường cần ranh giới quyền và vòng đời độc lập.

### 10.1. Quy trình plan và apply

Một quy trình Terraform cơ bản:

~~~bash
# Khởi tạo thư mục và provider
terraform init

# Kiểm tra cú pháp và cấu trúc
terraform fmt -check
terraform validate

# Xem thay đổi dự kiến cho môi trường dev
terraform plan -var-file="dev.tfvars" -out="dev.tfplan"

# Review plan, sau đó áp dụng đúng plan đã lưu
terraform apply "dev.tfplan"

# Xem các output đã công bố
terraform output
~~~

Không nên chạy apply tự động cho production chỉ vì plan không báo lỗi. Cần review thay đổi có thể thay thế hoặc xóa VM, đĩa, security group và các tài nguyên phụ thuộc. Khi công cụ cho biết resource sẽ bị destroy/create, hãy xác minh tác động dữ liệu và thời gian gián đoạn.

### 10.2. Drift detection

Configuration drift xảy ra khi trạng thái thực tế khác với mã khai báo, chẳng hạn người vận hành thay đổi security group trực tiếp trên console. Lần plan tiếp theo có thể phát hiện một phần sai khác và đề xuất đưa tài nguyên về cấu hình khai báo.

Không phải mọi thay đổi ngoài mã đều sai; đôi khi có thay đổi khẩn cấp cần được hợp thức hóa. Hãy cập nhật mã nguồn sau thay đổi được phê duyệt để mã và hạ tầng trở lại cùng một nguồn sự thật. Nếu bỏ qua drift lâu dài, lần apply sau có thể tạo thay đổi ngoài dự kiến.

## 11. Phiên bản, tương thích và phát hành module

Module dùng chung trở thành giao diện mà nhiều nhóm phụ thuộc. Thay đổi tên biến, kiểu dữ liệu, default hoặc output có thể ảnh hưởng nhiều workload.

Một số nguyên tắc:

1. Gắn version cho module hoặc release.
2. Khóa phiên bản provider và module theo chính sách dự án.
3. Ghi lại thay đổi trong changelog hoặc release notes.
4. Ưu tiên thay đổi tương thích ngược khi có thể.
5. Nếu cần loại bỏ biến, có giai đoạn deprecation và hướng dẫn migration.
6. Kiểm thử module bằng một cấu hình mẫu tối thiểu và một cấu hình đại diện production.
7. Review bảo mật và policy trước khi phát hành module dùng chung.

Khi gọi module từ registry hoặc repository Git, nên pin vào version hoặc tag cụ thể thay vì luôn lấy nhánh mới nhất. Điều này giúp lần triển khai sau có thể tái tạo đúng phiên bản đã kiểm thử.

## 12. Kiểm tra chất lượng và chính sách cho mẫu

Một mẫu cấu hình cần được kiểm tra trước khi đưa vào sử dụng rộng rãi. Các lớp kiểm tra thường gồm:

- **Format và syntax:** định dạng mã nhất quán, cấu trúc hợp lệ.
- **Validation:** biến có kiểu, giá trị và ràng buộc đúng.
- **Static analysis:** phát hiện cấu hình rủi ro hoặc thuộc tính lỗi thời.
- **Policy as code:** kiểm tra rule như đĩa phải mã hóa, không có cổng quản trị mở công khai, tag bắt buộc và image được phê duyệt.
- **Plan review:** xem tài nguyên sẽ được tạo, sửa, thay thế hoặc xóa.
- **Integration test:** triển khai vào môi trường thử nghiệm và kiểm tra kết nối, bootstrap, giám sát.
- **Security scan:** kiểm tra image, package, cấu hình và quyền.

Ví dụ, một policy có thể yêu cầu mọi máy production phải có tag Environment, Owner, Application; root disk phải mã hóa; VM không được gắn public IP nếu workload không có ngoại lệ được phê duyệt. Policy cần được thực thi ở pipeline hoặc nền tảng quản trị để tránh chỉ tồn tại trong tài liệu.

Không nên dựa hoàn toàn vào validation bên trong module để bảo vệ toàn bộ cloud. Security group có thể được tạo ở nơi khác, quyền IAM có thể nằm trong module khác, và policy tổ chức có thể áp dụng ở cấp account hoặc subscription.

## 13. Ví dụ quy trình từ yêu cầu đến máy ảo

Giả sử nhóm phát triển cần một VM Linux chạy API catalog trong môi trường dev. Nhóm đã có image được phê duyệt, subnet riêng và security group chỉ cho phép lưu lượng cần thiết.

Quy trình có thể diễn ra như sau:

1. Nhóm chọn module compute-instance đã được phát hành.
2. Cung cấp ami_id, instance_type, subnet_id, security_group_ids, hostname và environment.
3. Module kiểm tra kiểu và giá trị đầu vào.
4. Terraform tạo plan, hiển thị VM, đĩa mã hóa và các tag sẽ được áp dụng.
5. Người review xác nhận không có thay đổi ngoài dự kiến.
6. Pipeline áp dụng plan bằng danh tính triển khai được cấp quyền giới hạn.
7. VM khởi động, cloud-init đặt hostname, cài package cần thiết và bật service.
8. Instance đăng ký vào hệ thống giám sát và lấy secret bằng instance identity nếu cần.
9. Pipeline kiểm tra health endpoint và lưu output instance ID/private IP.
10. Mọi thay đổi sau đó được thực hiện qua mã và quy trình review.

Nếu nhóm cần staging, có thể gọi lại cùng module với file biến staging. Cấu trúc resource vẫn được dùng chung; các giá trị môi trường được kiểm soát riêng.

## 14. Những sai lầm thường gặp

- **Hard-code giá trị môi trường:** khiến dev, staging và production dễ dùng nhầm subnet, image hoặc quyền.
- **Tạo quá nhiều biến:** làm giao diện module phức tạp và mở ra những tùy chỉnh không cần thiết.
- **Không kiểm tra input:** có thể tạo VM với kích thước, image hoặc vùng không hợp lệ.
- **Sao chép module cho từng ứng dụng:** khiến các bản sao lệch nhau và khó cập nhật chuẩn bảo mật.
- **Dùng một module quá lớn:** gom nhiều trách nhiệm và làm mọi thay đổi có phạm vi ảnh hưởng rộng.
- **Đặt secret trong mã hoặc user-data:** làm lộ bí mật qua repository, log, plan hoặc state.
- **Coi sensitive là mã hóa:** sensitive chủ yếu che hiển thị; state vẫn cần được bảo vệ.
- **Không pin version:** một thay đổi ở module hoặc provider có thể làm lần triển khai sau khác lần trước.
- **Apply mà không review plan:** có thể xóa hoặc thay thế máy và volume đang chứa dữ liệu.
- **Bỏ qua drift:** cấu hình thực tế và mã khai báo dần mất đồng nhất.
- **Chỉ kiểm thử cú pháp:** mẫu có thể hợp lệ về cú pháp nhưng vẫn thiếu quyền, mạng, backup hoặc giám sát.

## 15. Quy trình xây dựng mẫu cấu hình dùng chung

Có thể áp dụng quy trình sau khi xây dựng một module cấp phát máy:

1. **Thu thập yêu cầu:** xác định loại workload, OS, CPU/RAM, lưu trữ, mạng, bảo mật và khả năng sẵn sàng.
2. **Xác định baseline:** phân biệt thuộc tính bắt buộc với giá trị được phép thay đổi.
3. **Thiết kế input/output:** chọn kiểu dữ liệu, default, validation và output cần thiết.
4. **Tách trách nhiệm:** quyết định phần nào thuộc image, module IaC và bootstrap/configuration.
5. **Viết module:** đặt tên rõ ràng, tổ chức resource và local value dễ hiểu.
6. **Kiểm tra bảo mật:** loại secret khỏi mã, bảo vệ state, kiểm soát quyền và áp dụng policy.
7. **Kiểm thử:** format, validate, plan, triển khai môi trường thử nghiệm và xác minh ứng dụng.
8. **Phát hành có version:** ghi changelog, khóa phiên bản và hướng dẫn sử dụng.
9. **Vận hành và cải tiến:** theo dõi drift, cập nhật image, provider, module và policy theo chu kỳ.

## 16. Ghi nhớ

Mẫu khai báo mô tả trạng thái hạ tầng mong muốn; biến đầu vào thể hiện những khác biệt hợp lệ giữa workload và môi trường; local value giảm lặp biểu thức; output tạo giao diện cho thành phần khác; module đóng gói cấu hình để tái sử dụng. Image và cloud-init bổ sung phần hệ điều hành cùng cấu hình khởi tạo bên trong VM.

Để tự động hóa compute an toàn và có thể lặp lại, hãy thiết kế module với giao diện nhỏ và rõ, xác thực đầu vào, tách cấu hình khỏi bí mật, quản lý state và version, review plan trước khi áp dụng, đồng thời kiểm tra policy và khả năng phục hồi. Khi mã trở thành nguồn mô tả hạ tầng, nhóm có thể tạo lại máy một cách nhất quán và kiểm soát thay đổi trong suốt vòng đời vận hành.
