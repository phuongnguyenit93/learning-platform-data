# Phân chia module tái sử dụng và phạm vi sở hữu

## Mục tiêu học tập

Infrastructure as Code (IaC) giúp mô tả hạ tầng bằng code có thể review, version, test và triển khai lặp lại. Khi số lượng workload, environment, account và team tăng lên, việc tổ chức IaC thành các module trở thành một quyết định kiến trúc quan trọng. Nếu mỗi đội tự sao chép cấu hình network, database, identity và logging, hệ thống sẽ nhanh chóng có nhiều biến thể khó kiểm soát. Ngược lại, nếu gom mọi thứ vào một module tổng quát với hàng trăm tham số, thay đổi nhỏ có thể ảnh hưởng nhiều workload và làm mất quyền tự chủ của team.

**Module reusable** là một đơn vị cấu hình có interface, trách nhiệm và hành vi được định nghĩa rõ, có thể được dùng lại mà không cần sao chép implementation. **Module boundary** xác định phần nào thuộc một module, phần nào module sở hữu và cách module tương tác với phần còn lại. **Ownership boundary** xác định team hoặc capability nào chịu trách nhiệm thiết kế, thay đổi, vận hành và hỗ trợ module hoặc resource được tạo ra.

Bài học tập trung vào cách chia module tái sử dụng và phạm vi sở hữu trong IaC. Một thiết kế tốt cần cân bằng khả năng tái sử dụng với tính rõ ràng, cô lập thay đổi, kiểm soát state, bảo mật, tốc độ triển khai và khả năng vận hành. Module không chỉ là cách giảm số dòng code; nó là hợp đồng kỹ thuật giữa platform team và các workload sử dụng hạ tầng.

Bài học thuộc chương **Hạ tầng dưới dạng mã**, tập trung vào **phân chia module tái sử dụng và phạm vi sở hữu**. Trong phạm vi Cloud Architecture, module cần phản ánh yêu cầu nghiệp vụ và ranh giới network, compute, data, deployment; đồng thời hỗ trợ độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt module, root configuration, component, stack, workspace và state.
- Xác định module boundary theo domain, lifecycle, ownership và change coupling.
- Thiết kế input/output contract có kiểu dữ liệu, validation, default và semantics rõ.
- Phân chia module nền tảng, module capability và module workload.
- Quyết định khi nào nên dùng module chung, module chuyên biệt hoặc composition.
- Tránh module quá tổng quát, abstraction quá sớm và copy/paste configuration.
- Thiết kế dependency giữa module qua output contract, tránh phụ thuộc nội bộ.
- Quản lý version, compatibility, deprecation và migration.
- Chọn state boundary, locking, permission và deployment ownership phù hợp.
- Tổ chức repository, review, testing, release và promotion giữa environment.
- Thiết kế security guardrails, policy và cost ownership trong module.
- Xây dựng ADR và đánh giá kiến trúc module theo Well-Architected.

## 1. Vì sao cần phân chia module?

Giả sử một công ty vận hành nhiều ứng dụng trên cloud: booking API, payment service, reporting platform, data warehouse và các worker nền. Các workload đều cần network, IAM, logging, encryption, monitoring và compute, nhưng nhu cầu không giống nhau.

Nếu mỗi workload tự định nghĩa mọi resource:

- Network rules có thể khác nhau giữa các môi trường.
- Encryption, backup và logging dễ bị bỏ sót.
- Team phải tự cập nhật cùng một cấu hình khi có security baseline mới.
- Cost tags và ownership không nhất quán.
- Cấu hình sai có thể tồn tại ở một số workload mà không được phát hiện.

Nếu mọi resource lại được đặt trong một module duy nhất:

- Mọi team phụ thuộc vào một release lớn.
- Một thay đổi cho workload A có thể ảnh hưởng workload B.
- Module có nhiều conditional, flag và trường hợp ngoại lệ.
- Review khó biết thay đổi tác động đến ai.
- Team không thể release độc lập.
- State và quyền thay đổi tập trung quá rộng.

Chia module hợp lý tạo ra các capability có thể dùng lại, nhưng mỗi capability vẫn có trách nhiệm và vòng đời quản lý rõ ràng.

### 1.1. Module là boundary của hợp đồng

Một module nên trả lời bốn câu hỏi:

1. **Nó sở hữu gì?** Resource, logic và lifecycle nào thuộc phạm vi module?
2. **Nó cần gì?** Input nào cần từ caller hoặc platform?
3. **Nó cung cấp gì?** Output nào caller được phép sử dụng?
4. **Ai chịu trách nhiệm?** Team nào phát hành, hỗ trợ, xử lý incident và thay đổi contract?

Một module không nên buộc caller hiểu cấu trúc nội bộ của nó. Caller nên dùng interface công khai thay vì tham chiếu resource nội bộ hoặc tự suy ra tên resource được tạo.

~~~mermaid
flowchart LR
    CALLER["Root / workload stack"] --> INPUT["Module inputs"]
    INPUT --> MODULE["Reusable module"]
    MODULE --> RES["Owned resources"]
    RES --> OUTPUT["Public outputs"]
    OUTPUT --> CONSUMER["Dependent module / workload"]
    OWNER["Module owner"] --> MODULE
    OWNER --> SUPPORT["Support / lifecycle"]
~~~

## 2. Những khái niệm cần phân biệt

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Module | Đơn vị cấu hình có interface và trách nhiệm | VPC module, managed database module |
| Root configuration | Điểm ghép module cho một deployment | Production booking stack |
| Component | Thành phần kiến trúc có thể gồm nhiều resource/module | Application platform component |
| Stack | Tập resource được triển khai và quản lý cùng nhau | Booking production stack |
| Workspace/environment | Ngữ cảnh triển khai hoặc cấu hình | dev, staging, production |
| State | Metadata ánh xạ resource với cấu hình IaC | Terraform state |
| Provider | Plugin giao tiếp API của nền tảng | AWS/Azure/GCP provider |
| Module registry | Nơi lưu và phát hành module versioned | Internal Terraform registry |

Một module không đồng nghĩa với một state. Có thể nhiều module được gọi từ cùng một root configuration và cùng state; cũng có thể mỗi stack/module boundary được triển khai trong state riêng. Quyết định state boundary cần xét quyền truy cập, blast radius, locking, release cadence và ownership.

### 2.1. Reusable module và deployment instance

Một module reusable là blueprint. Mỗi lần gọi module tạo một instance cấu hình trong deployment cụ thể. Ví dụ module network có thể được gọi ở production và staging với CIDR, AZ và tags khác nhau. Hai instance đó có resource identity và lifecycle riêng dù dùng chung implementation.

### 2.2. Module không nhất thiết phải là resource duy nhất

Module có thể bao gồm nhiều resource để tạo thành một capability hoàn chỉnh: network module gồm VPC, subnet, route và security baseline; database module gồm database instance, subnet group, parameter group, monitoring và backup settings. Ranh giới nên dựa trên trách nhiệm và thay đổi cùng nhau, không dựa trên số lượng resource.

## 3. Nguyên tắc xác định module boundary

### 3.1. Cohesion: những gì thay đổi cùng nhau nên ở gần nhau

Nếu một nhóm resource luôn được tạo, kiểm thử, nâng cấp và rollback cùng nhau, chúng có thể thuộc cùng module. Ví dụ database subnet group, parameter group và database instance thường có quan hệ lifecycle rõ; chia thành các module quá nhỏ có thể tạo nhiều dependency và khó hiểu.

Ngược lại, network foundation có lifecycle dài và được nhiều workload dùng chung, trong khi database instance có lifecycle theo ứng dụng. Có thể tách chúng để thay đổi database không phải release lại toàn bộ network.

### 3.2. Loose coupling: caller phụ thuộc interface, không phụ thuộc nội bộ

Module A nên cung cấp output có ý nghĩa như subnet IDs, endpoint, security group ID hoặc role ARN. Module B nhận những output đó qua input. Caller không nên tham chiếu trực tiếp địa chỉ nội bộ như tên resource local, map key ngầm hoặc đường dẫn state của module khác.

### 3.3. Ownership: một boundary cần owner rõ

Nếu hai team cùng sở hữu một module nhưng không có quy tắc quyết định, thay đổi có thể bị trì hoãn hoặc xung đột. Mỗi module cần owner chịu trách nhiệm contract, release và support. Consumer có thể đóng góp code qua review, nhưng owner vẫn chịu trách nhiệm chất lượng và tương thích của release.

### 3.4. Lifecycle: tách theo chu kỳ thay đổi

Network foundation, identity baseline và audit logging thường thay đổi ít hơn application deployment. Workload compute, autoscaling và service-specific permissions có chu kỳ nhanh hơn. Khi lifecycle khác nhau đáng kể, cân nhắc tách module hoặc state để giảm coupling.

### 3.5. Security boundary: tách theo quyền và mức tin cậy

Module quản lý KMS key, IAM policy hoặc network perimeter có thể cần quyền cao hơn module tạo ứng dụng. Tách boundary giúp pipeline và team workload không cần quyền quản trị toàn account. Module nào thay đổi resource bảo mật trọng yếu cần review và approval tương xứng.

### 3.6. Change impact và blast radius

Cần hỏi: nếu module thay đổi hoặc bị triển khai sai, bao nhiêu workload bị ảnh hưởng? Shared network module có thể tác động nhiều ứng dụng; module queue riêng có blast radius nhỏ hơn. Boundary nên làm rõ blast radius và tạo cách triển khai/rollback có kiểm soát.

### 3.7. Không chia module chỉ theo loại resource

Một module riêng cho từng resource nhỏ có thể khiến root configuration phải nối quá nhiều output/input. Ví dụ tách security group, rule, ingress, egress và attachment thành năm module có thể làm interface phức tạp mà không tạo ownership tốt hơn.

Thay vào đó, gom theo capability có ngữ nghĩa, chẳng hạn service network policy module nhận ingress/egress rule có cấu trúc, validate và tạo các resource liên quan.

## 4. Mô hình phân tầng module

Một mô hình hữu ích là chia module thành ba nhóm: foundation, capability và workload.

~~~mermaid
flowchart TB
    ROOT["Environment root / application stack"]
    ROOT --> WORK["Workload modules"]
    WORK --> CAP["Capability modules"]
    CAP --> BASE["Foundation modules"]
    BASE --> CLOUD["Cloud provider resources"]
    WORK --> CLOUD
    CAP --> CLOUD
~~~

### 4.1. Foundation modules

Foundation tạo nền tảng dùng chung hoặc baseline của một account/region/environment:

- Network/VPC/VNet, subnet, route, endpoint.
- Identity baseline, role, policy boundary.
- KMS/key management và encryption defaults.
- Audit logging, centralized log destination.
- Shared DNS, certificate và connectivity.
- Guardrails, tagging policy và account baseline.

Foundation thường có blast radius lớn, lifecycle dài và owner thuộc platform/security/network team. Cần release process thận trọng, compatibility và migration plan.

### 4.2. Capability modules

Capability cung cấp một năng lực có thể dùng lại:

- Managed PostgreSQL với backup/monitoring baseline.
- Queue/topic với encryption, DLQ và retention.
- Object storage bucket theo data classification.
- Container service hoặc serverless function.
- Observability integration.
- Private service endpoint.
- Autoscaling profile hoặc workload identity.

Capability module có thể được nhiều workload gọi với cấu hình khác nhau nhưng vẫn giữ guardrail và defaults chung.

### 4.3. Workload modules/stacks

Workload root ghép capability để tạo hệ thống cụ thể: booking API, payment worker, analytics pipeline. Nó quyết định số lượng instance, sizing, scaling profile, service-specific environment variable, integration và network connection tới foundation.

Không nên đẩy toàn bộ logic nghiệp vụ hoặc toàn bộ resource app vào generic foundation module. Workload owner cần kiểm soát cấu hình gắn với nhu cầu riêng.

### 4.4. Phân tầng không phải hierarchy bắt buộc

Một module có thể gọi module khác, nhưng không nhất thiết mọi tầng đều phải tạo wrapper. Nếu workload chỉ dùng một resource rất đơn giản và không có policy/contract riêng, gọi provider resource trực tiếp trong root đôi khi rõ ràng hơn tạo module wrapper không thêm giá trị.

## 5. Ví dụ: module network foundation

Giả sử nhiều workload cần network private với subnet ở nhiều AZ. Module network nên sở hữu cấu trúc network và trả về outputs ổn định.

Cấu trúc ví dụ:

~~~text
modules/
  network/
    main.tf
    variables.tf
    outputs.tf
    versions.tf
    README.md
    examples/
      basic/
      private-app/
    tests/
      network.tftest.hcl
~~~

### 5.1. Input contract

~~~hcl
variable "name" {
  description = "Stable name for the network deployment"
  type        = string
}

variable "cidr_block" {
  description = "Primary IPv4 CIDR for the network"
  type        = string

  validation {
    condition     = can(cidrnetmask(var.cidr_block))
    error_message = "cidr_block must be a valid IPv4 CIDR."
  }
}

variable "availability_zones" {
  description = "Availability zones used by the network"
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) >= 2
    error_message = "At least two availability zones are required."
  }
}

variable "tags" {
  description = "Additional resource tags"
  type        = map(string)
  default     = {}
}
~~~

Contract chỉ nên yêu cầu input caller thực sự cần quyết định. Không đưa hàng chục provider-specific flags ra public interface nếu phần lớn workload không cần chúng. Security baseline và naming convention có thể được module áp dụng mặc định.

### 5.2. Implementation sở hữu resource

~~~hcl
resource "aws_vpc" "this" {
  cidr_block           = var.cidr_block
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, {
    Name = var.name
    ManagedBy = "terraform"
  })
}
~~~

Ví dụ rút gọn chỉ tạo VPC. Production module thường còn cần subnet strategy, route, endpoint, flow logs, IPv6 policy, IPAM, NAT topology và security guardrails.

### 5.3. Public outputs

~~~hcl
output "vpc_id" {
  description = "ID of the created VPC"
  value       = aws_vpc.this.id
}

output "vpc_cidr_block" {
  description = "Primary IPv4 CIDR of the VPC"
  value       = aws_vpc.this.cidr_block
}
~~~

Caller phụ thuộc vào output contract. Không nên buộc caller dựa vào tên resource nội bộ như aws_vpc.this nếu implementation có thể thay đổi.

### 5.4. Root configuration gọi module

~~~hcl
module "network" {
  source  = "app.terraform.io/acme/network/aws"
  version = "2.3.0"

  name               = "booking-prod"
  cidr_block         = "10.40.0.0/16"
  availability_zones = ["ap-southeast-1a", "ap-southeast-1b"]

  tags = {
    Environment = "production"
    Owner       = "platform-network"
    CostCenter  = "CC-BOOKING"
  }
}
~~~

Tên registry và version là ví dụ. Caller chọn version rõ ràng và review plan khi nâng cấp.

## 6. Ví dụ: database capability module

Database module có thể sở hữu database instance, subnet group, parameter group, monitoring, backup và các security setting liên quan. Module nên nhận network identity từ foundation thay vì tự tạo network mới.

~~~hcl
variable "private_subnet_ids" {
  description = "Private subnets for database placement"
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "Database must span at least two private subnets."
  }
}

variable "engine_version" {
  description = "Approved database engine version"
  type        = string
}

variable "backup_retention_days" {
  description = "Automated backup retention in days"
  type        = number
  default     = 14

  validation {
    condition     = var.backup_retention_days >= 7
    error_message = "Backup retention must meet the platform baseline."
  }
}
~~~

Root configuration ghép hai capability:

~~~hcl
module "network" {
  source  = "app.terraform.io/acme/network/aws"
  version = "2.3.0"

  name               = "booking-prod"
  cidr_block         = "10.40.0.0/16"
  availability_zones = ["ap-southeast-1a", "ap-southeast-1b"]
}

module "booking_database" {
  source  = "app.terraform.io/acme/postgres/aws"
  version = "4.1.2"

  name                  = "booking-prod"
  private_subnet_ids    = module.network.private_subnet_ids
  engine_version        = "16.4"
  backup_retention_days = 14
}
~~~

Dependency được thể hiện bằng output/input contract. Terraform có thể suy ra dependency graph từ các tham chiếu đó. Tránh dùng depends_on rộng chỉ để ép thứ tự khi reference đã mô tả quan hệ; dependency graph nên phản ánh quan hệ thực.

### 6.1. Một module không nên âm thầm chiếm quyền sở hữu dependency

Database module không nên tự sửa route table hoặc security group của network module mà không có contract rõ. Nếu cần network rule, có thể:
- Database module xuất security group ID và yêu cầu root kết nối rule module.
- Database module nhận source security group IDs rồi tạo rule do chính nó sở hữu.
- Một network policy capability module sở hữu rule và có input rõ.

Chọn một mô hình nhất quán để không có hai module cùng quản lý một resource hoặc một thuộc tính.

## 7. Interface design: inputs, outputs và validation

### 7.1. Input tối thiểu nhưng đủ ngữ nghĩa

Input nên diễn tả ý định, không bắt caller biết quá nhiều chi tiết provider. Ví dụ nhận retention_days thay vì yêu cầu caller tạo toàn bộ lifecycle rule nếu module sở hữu policy lifecycle.

Tuy nhiên, abstraction không nên che mất quyết định có ảnh hưởng quan trọng. Caller phải biết module tạo public/private subnet, mã hóa loại nào, backup retention bao lâu và có tạo NAT gateway hay không nếu chúng ảnh hưởng security/cost.

### 7.2. Required, optional và default

- Required input: quyết định mà module không thể tự suy ra an toàn.
- Optional input: biến thể hợp lệ nhưng không phải workload nào cũng cần.
- Default: baseline được module owner lựa chọn và duy trì.
- Derived value: module tự tính từ input đã xác thực.
- Forbidden/unsupported: cấu hình bị policy chặn hoặc không được module hỗ trợ.

Không dùng default mơ hồ như false cho một control bảo mật nếu người gọi có thể hiểu là tắt encryption. Với thuộc tính critical, default nên an toàn và contract phải giải thích rõ.

### 7.3. Validation và precondition

Validation nên bắt lỗi sớm:
- CIDR hợp lệ và không overlap với vùng đã biết.
- AZ count đủ cho availability target.
- Backup retention đạt policy.
- Engine version nằm trong danh sách hỗ trợ.
- Instance size phù hợp workload tier.
- Tags bắt buộc có owner/environment/cost center.
- Public exposure cần exception rõ.
- Replica count/concurrency nằm trong quota.

Validation local không thể xác minh mọi điều kiện runtime; policy engine hoặc deployment pipeline có thể cần kiểm tra cross-resource và account-wide constraints.

### 7.4. Outputs là API

Outputs nên:
- Có tên và kiểu dữ liệu ổn định.
- Chỉ xuất thông tin consumer cần.
- Không trả secret/password/private key.
- Có description và semantics rõ.
- Có thể deprecate theo versioning policy.
- Tránh expose resource internals không cần thiết.

Không xuất quá nhiều output chỉ vì chúng dễ lấy. Mỗi output công khai tạo thêm compatibility obligation.

## 8. Module composition và tránh dependency cycle

Module composition là ghép các capability để triển khai workload. Root configuration thường là nơi biết toàn bộ ngữ cảnh và kết nối module.

~~~mermaid
flowchart TB
    ROOT["Root stack: booking-prod"]
    ROOT --> NET["Network module"]
    ROOT --> DB["Database module"]
    ROOT --> QUEUE["Queue module"]
    ROOT --> APP["Application module"]
    NET --> DB
    NET --> APP
    DB --> APP
    QUEUE --> APP
~~~

Sơ đồ minh họa dependency một chiều. Cần tránh vòng dependency như network module đòi security group của database trong khi database module lại cần subnet output của network; nếu quan hệ bị vòng, tách network foundation và security policy interface rõ hơn.

### 8.1. Root module điều phối

Root module chịu trách nhiệm:
- Chọn module version.
- Truyền environment-specific configuration.
- Kết nối outputs/inputs.
- Chọn provider alias/region/account.
- Xác định naming, tags và policy context.
- Điều phối thứ tự deploy thông qua dependency graph.
- Ghi nhận stack ownership và release.

Root không nên chứa quá nhiều implementation detail; nhưng cũng không cần tạo wrapper module cho từng lần gọi nếu wrapper không có contract hoặc policy riêng.

### 8.2. Data source và cross-stack reference

Nếu module cần resource do stack khác quản lý, dùng contract có version và quyền đọc rõ: remote state output, service discovery, parameter store, resource registry hoặc explicit input. Remote state thuận tiện nhưng cấp quyền đọc state có thể lộ nhiều metadata hơn output cần thiết. Với boundary bảo mật cao, ưu tiên publish chỉ các output cần dùng qua registry/parameter có access policy phù hợp.

### 8.3. Cross-account và cross-region

Module có thể nhận provider alias hoặc được root cấu hình provider cụ thể. Không nên hard-code region/account vào implementation reusable. Root hoặc deployment pipeline xác định target account/region; module validate resource compatibility và tạo resource trong provider context được truyền vào.

## 9. Module versioning và compatibility

Reusable module là API. Khi consumer dùng module, họ phụ thuộc vào input/output, behavior và lifecycle. Thay đổi contract cần quản lý như thay đổi API.

### 9.1. Semantic versioning

Một quy ước phổ biến:
- **Patch:** sửa lỗi không đổi contract/behavior theo ý nghĩa caller.
- **Minor:** thêm capability tương thích ngược, input optional hoặc output mới.
- **Major:** breaking change như đổi input type, xóa output, đổi default behavior hoặc thay resource identity.

Semantic versioning là quy ước cần được áp dụng nhất quán; không chỉ tăng version theo cảm tính. Provider/resource behavior có thể buộc major upgrade dù interface vẫn giống nhau nếu migration tác động lifecycle.

### 9.2. Breaking change

Ví dụ:
- Đổi backup_retention_days từ 7 mặc định thành 1.
- Đổi subnet selection từ private sang public.
- Thay engine family dẫn đến replace database.
- Rename output đang được consumer sử dụng.
- Đổi security group rule ownership.
- Đổi encryption key hoặc KMS policy.
- Thay resource naming gây destroy/create.

Không coi thay đổi default là luôn non-breaking. Default behavior là một phần contract; thay đổi có thể tác động security, availability, cost hoặc replace resource.

### 9.3. Deprecation policy

Một output/input cần bỏ:
1. Đánh dấu deprecated và giải thích thay thế.
2. Cung cấp version/module migration guide.
3. Tìm consumer bằng registry/usage inventory nếu có.
4. Cho thời gian chuyển đổi theo policy.
5. Phát hành major version để remove.
6. Giữ bản cũ trong thời gian hỗ trợ đã công bố.

### 9.4. Pin version và controlled upgrade

Production nên pin module version cụ thể hoặc immutable reference. Upgrade qua pull request, changelog, plan review, test và staged rollout. Tránh source trỏ branch main hoặc tag mutable trong deployment nhạy cảm.

## 10. State boundary và phạm vi sở hữu tài nguyên

State giữ mapping giữa configuration và tài nguyên thực. Tách module không bắt buộc phải tách state; tách state là quyết định về quyền, lifecycle và blast radius.

### 10.1. Một state lớn

Ưu điểm:
- Dependency giữa resource được Terraform quản lý trực tiếp.
- Dễ apply một graph nhất quán.
- Ít remote-state interface.

Giới hạn:
- Blast radius lớn.
- Lock contention giữa team.
- Quyền đọc state rộng.
- Một thay đổi có thể ảnh hưởng nhiều workload.
- Apply duration lớn.

### 10.2. Nhiều state nhỏ

Ưu điểm:
- Isolation theo team/environment/domain.
- Lock và deployment độc lập.
- Permission dễ giới hạn hơn.
- Blast radius nhỏ hơn.

Giới hạn:
- Cần publish/consume interface giữa state.
- Ordering và orchestration phức tạp hơn.
- Có thể tồn tại partial deployment.
- Refactor resource giữa state cần import/move có kiểm soát.
- Nhiều backend, lock và backup cần vận hành.

### 10.3. Chọn boundary theo ownership

Một gợi ý:
- Account/network foundation state: platform/network owner.
- Security baseline/identity state: security/platform owner.
- Shared data platform state: data platform owner.
- Mỗi workload stack state: workload team.
- Ephemeral test state: pipeline/test owner và TTL.

Không dùng một state dùng chung cho tất cả team chỉ vì thuận tiện lúc đầu. Cũng không tách một state cho mỗi resource nếu chi phí orchestration lớn hơn lợi ích isolation.

### 10.4. Resource ownership không được trùng

Mỗi resource nên có một authoritative state owner. Hai state hoặc hai tool cùng quản lý một resource có thể tranh chấp, destroy nhầm hoặc phát hiện drift liên tục. Nếu chuyển ownership:
1. Freeze thay đổi liên quan.
2. Lập kế hoạch import/move.
3. Backup state và ghi mapping.
4. Remove binding khỏi state cũ theo quy trình an toàn, không destroy remote object.
5. Import vào state mới.
6. Chạy plan ở cả hai phía.
7. Xác minh không có create/destroy ngoài ý muốn.
8. Mở lại pipeline và ghi audit.

Các lệnh state thao tác trực tiếp cần được review và thực hiện bởi owner có thẩm quyền.

## 11. Repository structure và team ownership

### 11.1. Cấu trúc mono-repo minh họa

~~~text
infrastructure/
  modules/
    network/
    postgres/
    queue/
    object-storage/
    workload-identity/
    observability/
  stacks/
    production/
      booking/
      payment/
      analytics/
    staging/
      booking/
      payment/
  policies/
    security/
    cost/
    compliance/
  tests/
    integration/
    policy/
  docs/
    architecture/
    module-catalog/
~~~

Mono-repo giúp review dependency/module cùng một nơi và thay đổi đồng bộ. Nó cần CI phù hợp, ownership rules và không để một thay đổi nhỏ buộc mọi stack deploy lại.

### 11.2. Multi-repo

Có thể tách module library và workload stack thành repository riêng. Ưu điểm là version/release module rõ và permission tách biệt; hạn chế là cần registry, dependency update automation và compatibility testing giữa repo.

### 11.3. Ownership catalog

Mỗi module cần catalog entry:
- Module name và purpose.
- Owner team và contact/on-call.
- Repository/registry location.
- Supported provider/engine/version.
- Input/output contract.
- Security/cost defaults.
- Dependencies và consumers chính.
- Version support/deprecation.
- Test status và release cadence.
- Documentation/example.
- Incident/runbook và escalation.

Ownership nên được thể hiện trong repository metadata, CODEOWNERS hoặc registry catalog để review tự động định tuyến đúng team.

## 12. Testing strategy cho reusable module

Module dùng lại nhiều nơi có thể nhân lỗi nhanh. Test nên kiểm tra contract và behavior, không chỉ xác minh syntax.

### 12.1. Test layers

| Test level | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Static/lint | Syntax và style | fmt, validate, lint |
| Unit/plan test | Input/output và resource intent | Check encryption, tags, backup |
| Policy test | Guardrail và security baseline | Public access bị deny |
| Integration | Provider behavior thật trong test account | Tạo VPC/database sandbox |
| Contract test | Consumer expectation | Output type/name không bị đổi |
| Upgrade test | Nâng version từ bản cũ | Plan không replace ngoài dự kiến |
| Destruction test | Teardown an toàn | Không xóa shared resource ngoài owner |
| Example test | Documentation chạy được | Example stack validate/apply |

### 12.2. Test default behavior

Default quan trọng như input explicit. Test cần xác nhận:
- Encryption bật mặc định.
- Public exposure không bật ngoài chủ đích.
- Backup retention đạt baseline.
- Required logs/metrics được bật.
- Tags owner/environment/cost center được truyền.
- Quota và naming validation hoạt động.

### 12.3. Negative test

Cần kiểm tra input sai hoặc nguy hiểm bị từ chối:
- CIDR sai hoặc overlap.
- Engine version ngoài support matrix.
- Public subnet cho workload yêu cầu private.
- Backup retention thấp hơn minimum.
- Thiếu owner/cost center.
- KMS key không tương thích.
- Ingress từ mọi địa chỉ cho port quản trị.
- Tier vượt quota account.

### 12.4. Integration test có cost guardrail

Integration test có thể tạo tài nguyên thật, phát sinh chi phí hoặc quota. Cần account/project riêng, budget, TTL, tagging, cleanup và giới hạn concurrency. Không chạy test phá hủy vào production state.

## 13. Documentation và module contract

README của module nên trả lời:
- Module giải quyết capability nào?
- Khi nào nên/không nên dùng?
- Ai là owner?
- Supported versions/providers/regions.
- Inputs/outputs và defaults.
- Resource nào module tạo/sở hữu?
- Resource nào được giả định có sẵn?
- Security/cost implications.
- Upgrade/breaking change.
- Example tối thiểu và example production-like.
- Test command và support path.

Ví dụ usage docs cần thể hiện decision quan trọng như private/public, encryption, backup và retention. Không chỉ sinh bảng biến tự động mà thiếu semantics.

## 14. Security và policy trong module reusable

Một module được sử dụng rộng rãi có thể trở thành đường cung cấp mặc định cho toàn tổ chức. Vì vậy baseline security nên nằm gần nơi resource được tạo, nhưng không nên biến module thành hệ thống policy duy nhất.

### 14.1. Secure defaults

Ví dụ:
- Database private-only, encryption enabled, backup bật.
- Object storage block public access và encryption.
- Queue/topic có encryption, TLS và DLQ theo yêu cầu.
- IAM role theo least privilege.
- Log/audit destination không do workload tự xóa.
- Network ingress hạn chế theo explicit security group.
- Tags owner/environment/data classification.

### 14.2. Policy layering

- Module validation bắt lỗi input cục bộ.
- IaC policy gate kiểm tra plan toàn stack.
- Organization policy chặn hành vi nguy hiểm cấp account.
- Runtime config monitoring phát hiện drift.
- Security monitoring kiểm tra hành vi và exposure.

Một module private database không thể một mình bảo đảm toàn bộ data security nếu account policy, KMS key, identity hoặc network routing bị cấu hình sai.

### 14.3. Không expose secret qua output/state

Terraform state có thể chứa sensitive values dù output được đánh dấu sensitive. Không dùng output để truyền password/token không cần thiết; ưu tiên secret manager reference và workload identity. Giới hạn state access và log plan/apply để tránh lộ dữ liệu.

## 15. Cost ownership và tagging trong module

Module reusable nên áp dụng tagging convention thống nhất nhưng không nhất thiết tự đoán cost center. Caller có thể truyền owner, environment, product, cost center, data classification và managed-by. Module có thể enforce field bắt buộc và propagate xuống resource hỗ trợ tag.

### 15.1. Shared resource

Với resource dùng chung như NAT gateway, centralized logging, shared cluster hoặc network hub, chi phí cần có cost allocation rule:
- Direct allocation theo tenant/workload.
- Usage driver như bytes, CPU, request units.
- Fixed allocation theo subscription/tier.
- Shared overhead hiển thị riêng.

Không gắn tag một workload lên resource shared phục vụ hàng trăm workload nếu tag sẽ làm sai cost ownership.

### 15.2. Cost interface

Module có thể expose outputs phục vụ cost visibility:
- Resource identifiers.
- Capacity/reservation parameters.
- Storage retention/size.
- Scaling bounds.
- Estimated cost metadata nếu có nguồn tin cậy.

Không tuyên bố cost chính xác chỉ từ Terraform input; pricing phụ thuộc region, usage và provider meter. Cost estimation là đầu vào planning cần đối chiếu billing export.

## 16. Migration và refactor module

Refactor từ copy/paste sang module reusable có thể mang rủi ro thay đổi resource identity hoặc lifecycle.

### 16.1. Refactor không làm thay đổi resource

Mục tiêu là giữ nguyên resource identity và state binding trong khi chuyển cấu trúc code. Với Terraform, module address mới có thể thay đổi địa chỉ state. Có thể dùng moved blocks hoặc state move theo quy trình được hỗ trợ, rồi plan để xác nhận không destroy/create ngoài ý muốn.

Ví dụ moved block:

~~~hcl
moved {
  from = aws_vpc.main
  to   = module.network.aws_vpc.this
}
~~~

Cú pháp và khả năng phụ thuộc Terraform version. Phải test trên bản sao state/staging trước khi áp dụng production.

### 16.2. Migration có thay đổi resource

Nếu module mới đổi resource type hoặc kiến trúc, chia migration thành giai đoạn:
1. Tạo capability mới song song.
2. Đồng bộ dữ liệu/config nếu cần.
3. Chuyển consumer hoặc traffic.
4. Xác minh health và parity.
5. Gỡ resource cũ sau approval.
6. Cập nhật state và documentation.

Không kết hợp refactor code thuần với thay đổi network/database/security lớn trong một apply khó review.

### 16.3. Rollback và state recovery

Rollback module version không phải lúc nào cũng đảo ngược resource change. Có thể code cũ không nhận diện state mới hoặc provider đã thay đổi resource. Cần backup state, migration guide và recovery plan; ưu tiên forward-fix khi rollback có thể phá resource.

## 17. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Copy/paste module giữa repo | Baseline lệch và patch không đồng nhất | Internal module registry và release |
| Module quá tổng quát | Nhiều flag, conditional và khó hiểu | Chia theo capability và use case thực |
| Module quá nhỏ | Root wiring phức tạp | Gom resource cùng lifecycle/cohesion |
| Một module sở hữu mọi thứ | Blast radius và release coupling lớn | Tách foundation/capability/workload |
| Nhiều module cùng quản lý một resource | State conflict và drift | Một authoritative owner |
| Output expose implementation detail | Consumer coupling | Contract outputs ổn định, có ngữ nghĩa |
| Module gọi ngược caller hoặc tạo cycle | Dependency graph khó triển khai | Composition tại root |
| Hard-code account/region | Khó tái sử dụng và promotion | Provider context từ root |
| Default bảo mật không an toàn | Consumer dùng mặc định nguy hiểm | Secure defaults và policy test |
| Breaking change không version | Consumer bị hỏng âm thầm | Semantic version và migration |
| Pin branch main trong production | Deployment không tái lập | Pin immutable version |
| Refactor và replace cùng lúc | Plan khó review, downtime | Tách migration thành bước |
| Dùng remote state quá rộng | Lộ metadata và coupling | Publish outputs tối thiểu |
| Không có owner/on-call | Module lỗi không ai nhận trách nhiệm | Ownership catalog/CODEOWNERS |

## 18. Case study: xây module library cho nền tảng booking

### 18.1. Bối cảnh

Một tổ chức có 12 workload dùng chung cloud account family. Mỗi workload tự định nghĩa VPC/subnet, managed database, queue, bucket và IAM role. Sau vài quý, network policy khác nhau, backup retention không đồng nhất và security team khó xác định ai sở hữu resource.

Mục tiêu là tạo module library dùng chung nhưng vẫn cho các team triển khai workload độc lập.

### 18.2. Chọn module boundary

Platform/network team sở hữu module network foundation: VPC, subnet, route, endpoint và flow logs. Security team sở hữu workload identity baseline, key integration và policy rules. Data platform sở hữu PostgreSQL capability với encryption/backup/monitoring baseline. Platform messaging sở hữu queue capability với retention, DLQ và encryption. Mỗi workload team sở hữu root stack và application-specific settings.

### 18.3. Contract và composition

Root booking production gọi network module, database module, queue module và application module. Database module nhận private subnet IDs từ network output. Queue module nhận key reference từ key service contract. Application module nhận database endpoint và queue ARN nhưng không nhận password; workload identity lấy secret/credential theo runtime identity.

~~~mermaid
flowchart TB
    ROOT["Booking production root"]
    ROOT --> NET["Network foundation"]
    ROOT --> ID["Workload identity"]
    ROOT --> DB["PostgreSQL capability"]
    ROOT --> Q["Queue capability"]
    ROOT --> APP["Booking application"]
    NET --> DB
    NET --> APP
    ID --> APP
    DB --> APP
    Q --> APP
~~~

### 18.4. Ownership và state

- Network foundation state: platform-network team.
- Identity/security state: security-platform team.
- Shared key/logging state: security/platform owner.
- Booking production state: booking team.
- Staging booking state: booking team với permission và backend riêng.
- Module library release: module owner qua registry.

Resource chỉ có một authoritative state owner. Root stack tham chiếu outputs đã publish theo interface được cấp quyền.

### 18.5. Versioning và rollout

Module network v2.0 thay đổi naming/outputs nên là breaking release. Owner phát migration guide, test với staging stack, tạo moved block khi có thể giữ resource identity, rồi nâng từng workload theo wave. Module database minor release thêm output monitoring endpoint không phá consumer; workload có thể nâng theo cadence riêng.

### 18.6. Kết quả cần đo

- Số cấu hình duplicate giảm.
- Tỷ lệ workload đạt encryption/backup/network baseline tăng.
- Thời gian tạo workload mới giảm.
- Module upgrade success rate.
- Số breaking change và consumer bị ảnh hưởng.
- Drift và security finding theo module version.
- Cost baseline và idle resource.
- Thời gian incident được route tới đúng owner.

Đây là các chỉ số cần đo sau rollout, không phải kết quả mặc định chỉ vì có module library.

## 19. Quy trình thiết kế và phát hành module mới

1. Xác định capability và vấn đề cần chuẩn hóa.
2. Xác định consumer, owner và lifecycle.
3. Liệt kê resource module sở hữu và dependency bên ngoài.
4. Thiết kế input/output contract.
5. Xác định secure defaults, quota và cost tags.
6. Chọn state/deployment boundary.
7. Viết example root configuration.
8. Viết unit, policy, integration và upgrade tests.
9. Review plan để nhận diện create/update/replace/destroy.
10. Tài liệu hóa limitations, support và migration.
11. Publish version bất biến vào registry.
12. Rollout canary/staging trước production.
13. Theo dõi adoption, errors, drift và feedback.
14. Deprecate version cũ theo policy.

## 20. Bài tập thực hành

Một tổ chức có 8 microservices, 3 environment và 2 cloud regions. Các service đều cần network, workload identity, PostgreSQL hoặc key-value store, queue, object storage và observability. Hiện tại mỗi service sao chép IaC từ repository khác.

Hãy thực hiện:

1. Phân loại module nào là foundation, capability và workload.
2. Xác định boundary/owner cho VPC, identity, KMS, database, queue, bucket và service compute.
3. Viết contract cho network module gồm required/optional inputs, validations và outputs.
4. Thiết kế database module nhận private subnet IDs, backup policy và encryption key reference.
5. Vẽ dependency graph, đảm bảo không có module cycle.
6. Đề xuất repository mono-repo hay multi-repo; giải thích trade-off.
7. Chọn state boundary theo account/environment/team và quyền truy cập.
8. Định nghĩa semantic versioning, deprecation và support policy.
9. Viết test cases cho secure defaults, invalid CIDR, backup retention và public exposure.
10. Thiết kế quy trình migration từ copy/paste resources sang module library mà không replace nhầm resource.
11. Xác định cách xử lý emergency change và resource ownership transfer.
12. Lập dashboard theo dõi module adoption, version, drift, deployment success và cost.
13. Viết ADR nêu module boundaries, owner, state model và tiêu chí tái cấu trúc.

**Gợi ý tự đánh giá:** Bài làm đạt khi module có capability/owner rõ, contract không expose implementation detail, dependency một chiều, resource chỉ có một state owner, version upgrade kiểm thử được và workload team vẫn có quyền quyết định cấu hình riêng trong guardrail.

## 21. Checklist trước production

- [ ] Module giải quyết một capability hoặc lifecycle có cohesion rõ.
- [ ] Resource ownership và team owner được ghi nhận.
- [ ] Module có input/output contract, description, type và validation.
- [ ] Secure defaults và cost tags được áp dụng.
- [ ] Caller không phụ thuộc resource nội bộ.
- [ ] Dependency graph không có cycle và root chịu trách nhiệm composition.
- [ ] Provider/account/region context không hard-code trong reusable module.
- [ ] State boundary có owner, locking, backup và permission rõ.
- [ ] Mỗi resource có một authoritative state owner.
- [ ] Version và breaking change có policy.
- [ ] Production pin immutable module version.
- [ ] Unit, policy, integration, contract và upgrade test phù hợp.
- [ ] Example có thể validate và phản ánh cách sử dụng được hỗ trợ.
- [ ] Migration/rollback có plan và state recovery evidence.
- [ ] Exception và emergency change được audit.
- [ ] Module catalog có owner, support, changelog và deprecation.
- [ ] Cost attribution, tagging và lifecycle được xác định.
- [ ] Adoption, drift, failure và cost được theo dõi sau release.

## 22. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi review module boundary |
| --- | --- |
| **Operational Excellence** | Module có owner, contract, docs, CI, version, migration và support process rõ không? |
| **Security** | State, IAM, secret, network và policy được tách quyền; secure defaults và audit có được kiểm tra không? |
| **Reliability** | Module có test, rollback/migration plan và blast radius phù hợp; shared foundation có release an toàn không? |
| **Performance Efficiency** | Module có hỗ trợ scaling/capacity đúng workload; abstraction có thêm dependency hoặc overhead không cần thiết không? |
| **Cost Optimization** | Tag, lifecycle, sizing, shared-cost ownership và quota có được áp dụng nhất quán không? |
| **Sustainability** | Module có giảm copy/paste, resource mồ côi, overprovision và effort bảo trì lặp lại không? |

**Kết luận:** Phân chia module reusable là quyết định về capability, contract, lifecycle và ownership. Module nên gom những resource có cùng trách nhiệm và thay đổi cùng nhau; caller tương tác qua input/output ổn định; root stack điều phối composition; mỗi resource có một state owner; version và migration được kiểm thử trước production. Hãy tái sử dụng những gì thực sự có chung semantics và guardrail, giữ khác biệt nghiệp vụ ở workload layer, đồng thời đo blast radius, adoption, drift và chi phí theo tinh thần Well-Architected.
