# Import tài nguyên GCP đang tồn tại

Trong một tổ chức, nhiều tài nguyên Google Cloud đã được tạo trước khi dự án áp dụng Terraform: VPC do nhóm network cấu hình trên Console, bucket được tạo bởi pipeline cũ, VM được triển khai thủ công hoặc Cloud SQL được thiết lập từ một dự án trước. Khi muốn quản lý các tài nguyên này bằng Infrastructure as Code (IaC), không nên tạo một bản sao mới rồi chuyển traffic sang. Cách phù hợp là **import tài nguyên hiện có vào Terraform state**, sau đó viết và điều chỉnh cấu hình để Terraform quản lý đúng trạng thái mong muốn.

Import là bước tiếp nhận quyền quản lý trong state. Nó không tự động thiết kế lại tài nguyên, cũng không bảo đảm cấu hình Terraform đã khớp với cấu hình thật trên GCP. Người vận hành cần xác định đúng resource address, import ID, provider configuration và backend state; sau đó đối chiếu plan để tránh một lần apply ngoài ý muốn thay đổi hoặc thay thế tài nguyên production.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của Terraform state khi tiếp nhận tài nguyên GCP đã tồn tại.
- Phân biệt lệnh import CLI và import block khai báo trong cấu hình.
- Xác định resource address và import ID theo từng loại tài nguyên của Google provider.
- Chuẩn bị backend, credentials và quyền cần thiết trước khi import.
- Viết cấu hình Terraform phản ánh tài nguyên hiện tại và xử lý drift sau import.
- Dùng plan, state show và state list để xác minh kết quả.
- Nhận biết rủi ro như quản lý trùng state, sai project/region, ForceNew và thay đổi production ngoài dự kiến.

## 1. Import giải quyết vấn đề gì?

Terraform quản lý tài nguyên thông qua hai thành phần:

- **Configuration:** mô tả trạng thái mong muốn bằng HCL, ví dụ một VPC có tên, routing mode và cấu hình subnet nhất định.
- **State:** ánh xạ resource address trong cấu hình Terraform với đối tượng thật trên provider, đồng thời lưu các thuộc tính Terraform cần để lập kế hoạch thay đổi.

Khi một VPC đã tồn tại trên GCP nhưng chưa có trong state, Terraform chưa biết resource address nào đại diện cho VPC đó. Nếu chỉ viết resource block rồi chạy apply, Terraform có thể cố tạo một VPC mới. Nếu tên đã được sử dụng, thao tác tạo sẽ thất bại; nếu tên khác, hệ thống có thể tạo tài nguyên trùng lặp.

Import thiết lập ánh xạ giữa resource address và đối tượng từ xa:

~~~text
Tài nguyên đã tồn tại trên GCP
          |
          | import
          v
Terraform state: google_compute_network.shared
          |
          | plan / refresh
          v
Đối chiếu cấu hình HCL với trạng thái thực tế
~~~

Sau khi import, Terraform có thể đọc tài nguyên và so sánh nó với configuration. Nếu configuration mô tả đúng trạng thái hiện tại, plan thường không còn thay đổi cần thực hiện. Nếu có khác biệt, Terraform sẽ đề xuất cập nhật hoặc thay thế tùy thuộc thuộc tính và schema của resource.

**Import không phải là thao tác tạo tài nguyên.** Mục tiêu của import là đưa một đối tượng hiện có vào phạm vi quản lý của một state.

## 2. Các khái niệm cần phân biệt

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Provider | Plugin giao tiếp với GCP API | hashicorp/google |
| Resource type | Loại tài nguyên Terraform quản lý | google_compute_network |
| Resource address | Địa chỉ tài nguyên trong cấu hình/state | google_compute_network.shared |
| Import ID | Định danh mà provider dùng để tìm tài nguyên từ xa | projects/my-project/global/networks/shared-vpc |
| State | Dữ liệu ánh xạ và thuộc tính của tài nguyên Terraform quản lý | State trong backend GCS |
| Drift | Khác biệt giữa configuration/state và tài nguyên thật | Console thay đổi routing mode |
| Import block | Khai báo import trong HCL | import { to = ... id = ... } |
| CLI import | Lệnh import trực tiếp một resource vào state | terraform import ... |

Resource address và import ID là hai giá trị khác nhau:

- Resource address nói Terraform sẽ quản lý tài nguyên ở vị trí nào trong cấu hình.
- Import ID nói Google provider phải tìm đối tượng nào trên GCP.

Ví dụ, cùng một VPC có thể được quản lý ở địa chỉ google_compute_network.shared trong root module hoặc module.network.google_compute_network.shared trong child module. Import ID vẫn tham chiếu đến VPC trên GCP.

## 3. Chuẩn bị trước khi import

Import vào nhầm state hoặc nhầm project có thể tạo ra rủi ro quản trị lâu dài. Trước khi thực hiện, hãy hoàn tất các bước sau.

### Xác định quyền sở hữu hiện tại

Thu thập thông tin:

- Project ID, folder/organization nếu có liên quan.
- Loại tài nguyên, tên, region hoặc zone.
- Chủ sở hữu nghiệp vụ và nhóm đang vận hành.
- Tài nguyên có đang được một Terraform state khác quản lý hay không.
- Các dependency như subnet, firewall rule, service account, disk, IAM policy hoặc database.
- Môi trường đích: development, staging hay production.

Một tài nguyên từ xa chỉ nên được quản lý bởi một Terraform state tại một thời điểm. Nếu một state khác đang quản lý đối tượng đó, cần thống nhất kế hoạch chuyển quyền sở hữu trước khi import. Không tạo thêm một ánh xạ độc lập cho cùng đối tượng vì hai state có thể cùng đề xuất thay đổi hoặc phá hủy tài nguyên.

### Kiểm tra phiên bản Terraform và Google provider

Import block được hỗ trợ từ Terraform 1.5.0. Tính năng sinh cấu hình bằng tùy chọn generate-config-out cũng có từ Terraform 1.5.0. Hãy kiểm tra phiên bản CLI và provider mà repository đang dùng:

~~~bash
terraform version
terraform providers
~~~

Giữ phiên bản provider đã được dự án kiểm thử và commit file .terraform.lock.hcl. Không tự ý nâng cấp provider ngay trong một thay đổi chỉ nhằm import, vì schema và cách provider đọc thuộc tính có thể thay đổi giữa các phiên bản.

### Chuẩn bị xác thực và quyền IAM

Google provider có thể dùng Application Default Credentials (ADC), service account impersonation hoặc cơ chế workload identity được tổ chức phê duyệt. Tránh đưa service account key vào mã nguồn hoặc file cấu hình.

Danh tính thực hiện import cần có quyền đọc metadata của resource qua Google Cloud API. Tùy loại tài nguyên, có thể cần thêm quyền đọc các thuộc tính liên quan. Backend GCS cũng cần quyền đọc/ghi object state và sử dụng cơ chế locking.

Ví dụ cấu hình provider:

~~~hcl
provider "google" {
  project = var.project_id
  region  = var.region
}
~~~

Cấu hình xác thực nên được thiết lập bên ngoài HCL theo môi trường thực thi. Giá trị project và region cần được kiểm tra trước khi chạy lệnh.

### Chuẩn bị Terraform backend

Với môi trường dùng chung, nên dùng remote backend để các thành viên làm việc trên cùng state. Google Cloud Storage backend hỗ trợ state locking. Bucket chứa state nên có versioning, IAM tối thiểu và chính sách bảo vệ phù hợp vì state có thể chứa dữ liệu nhạy cảm.

Ví dụ:

~~~hcl
terraform {
  backend "gcs" {
    bucket = "company-terraform-state"
    prefix = "gcp/network/production"
  }
}
~~~

Bucket backend cần được tạo và bảo vệ trước. Không dùng bucket chứa dữ liệu ứng dụng làm nơi lưu state nếu không có thiết kế riêng. Phân tách state theo phạm vi quản lý và môi trường để giảm blast radius.

Sau khi cấu hình backend, khởi tạo thư mục làm việc:

~~~bash
terraform init
~~~

Nếu đang chuyển một local state sang backend mới, hãy dùng quy trình migrate state có kiểm soát và đọc kỹ thông báo của Terraform. Không khởi tạo một state mới rỗng rồi import trong khi state cũ vẫn đang quản lý cùng tài nguyên.

### Sao lưu và khóa state

Trước import:

- Xác nhận backend và workspace đúng.
- Đảm bảo không có pipeline hoặc người khác đang thao tác state đồng thời.
- Kiểm tra state hiện tại bằng terraform state list.
- Sao lưu state theo quy trình lưu trữ an toàn của tổ chức.
- Không commit state backup vào Git hoặc gửi state vào chat/ticket công khai.

Remote backend có locking giúp tránh một số thao tác ghi đồng thời, nhưng không thay thế quy trình phối hợp. Không chỉnh sửa JSON state bằng tay.

## 4. Hai cách import tài nguyên vào Terraform

Terraform cung cấp hai cách chính.

| Cách | Cơ chế | Khi phù hợp |
|---|---|---|
| CLI import | Chạy lệnh terraform import để thêm mapping vào state ngay | Import từng tài nguyên, thao tác có kiểm soát hoặc quy trình cũ |
| Import block | Khai báo import trong HCL, xem kế hoạch và thực hiện qua terraform apply | Muốn lưu lại ý định import trong code, review qua pull request và CI |

Cả hai cách đều cần xác định đúng resource address và import ID. Import block giúp quá trình có thể review và tái lập từ repository; CLI import phù hợp với thao tác state trực tiếp.

## 5. Cách 1: import bằng Terraform CLI

Cú pháp:

~~~bash
terraform import RESOURCE_ADDRESS IMPORT_ID
~~~

Ví dụ, VPC tên shared-vpc đã tồn tại trong project my-project. Configuration đã có resource block:

~~~hcl
resource "google_compute_network" "shared" {
  project                 = "my-project"
  name                    = "shared-vpc"
  auto_create_subnetworks = false
}
~~~

Import VPC vào state:

~~~bash
terraform import google_compute_network.shared projects/my-project/global/networks/shared-vpc
~~~

Sau đó kiểm tra:

~~~bash
terraform state list
terraform state show google_compute_network.shared
~~~

Lệnh terraform import cập nhật state, không tự sinh đầy đủ HCL và không thay đổi cấu hình VPC trên GCP. Resource block cần tồn tại trong configuration để Terraform biết địa chỉ đích. Sau import, hãy chạy terraform plan để xem configuration có khớp tài nguyên thật hay không.

### Import vào module

Nếu resource nằm trong child module:

~~~bash
terraform import module.network.google_compute_network.shared projects/my-project/global/networks/shared-vpc
~~~

Nếu resource sử dụng for_each, address cần bao gồm key:

~~~bash
terraform import 'google_compute_network.vpc["production"]' projects/my-project/global/networks/prod-vpc
~~~

Trên PowerShell, Bash hoặc CI shell, cách trích dẫn address có thể khác. Hãy kiểm tra shell đang dùng để dấu ngoặc kép và dấu ngoặc vuông được truyền nguyên vẹn cho Terraform.

### Giới hạn của CLI import

- Mỗi lệnh import ánh xạ một đối tượng từ xa vào một resource address.
- Lệnh không tự tạo cấu hình đầy đủ.
- Không import cùng một đối tượng vào nhiều resource address hoặc nhiều state độc lập.
- Không dùng import để thay thế quy trình chuyển state đã tồn tại.
- Resource phải hỗ trợ import trong Google provider; xem phần Import của tài liệu resource cụ thể.

## 6. Cách 2: khai báo import block trong HCL

Import block cho phép mô tả đối tượng cần import ngay trong cấu hình.

Ví dụ:

~~~hcl
resource "google_compute_network" "shared" {
  project                 = "my-project"
  name                    = "shared-vpc"
  auto_create_subnetworks = false
}

import {
  to = google_compute_network.shared
  id = "projects/my-project/global/networks/shared-vpc"
}
~~~

Chạy:

~~~bash
terraform init
terraform fmt -check
terraform validate
terraform plan
~~~

Plan sẽ cho biết Terraform dự kiến import resource vào địa chỉ nào và có thay đổi nào khác được đề xuất. Nếu cấu hình phù hợp với tài nguyên hiện tại, kế hoạch có thể chỉ gồm thao tác import mà không cần thay đổi đối tượng từ xa.

Sau khi review plan, thực hiện:

~~~bash
terraform apply
~~~

Import block được xử lý khi apply. Nếu plan có thêm update hoặc replacement ngoài dự kiến, không tiếp tục apply. Hãy điều chỉnh HCL hoặc tìm hiểu khác biệt trước.

Import block có thể được giữ lại trong repository như một phần lịch sử khai báo. Sau khi import hoàn tất, có thể xóa import block nếu nhóm không muốn giữ chỉ thị import trong cấu hình; resource block và state mapping vẫn tiếp tục quản lý tài nguyên.

## 7. Sinh cấu hình ban đầu bằng generate-config-out

Khi chưa có resource block, Terraform có thể tạo cấu hình sơ bộ từ đối tượng được import. Tính năng này cần Terraform 1.5.0 trở lên.

Ví dụ chỉ khai báo import block:

~~~hcl
import {
  to = google_compute_network.shared
  id = "projects/my-project/global/networks/shared-vpc"
}
~~~

Sinh cấu hình:

~~~bash
terraform plan -generate-config-out=generated.tf
~~~

Terraform đọc resource qua provider và ghi cấu hình gợi ý vào generated.tf. Sau đó:

1. Đọc toàn bộ file được sinh.
2. Loại bỏ thuộc tính mặc định hoặc thuộc tính không cần thiết nếu phù hợp với chuẩn repository.
3. Bổ sung biến, module và quy ước đặt tên của dự án.
4. Kiểm tra thuộc tính có giá trị nhạy cảm hoặc phụ thuộc môi trường.
5. Chạy terraform fmt và terraform validate.
6. Chạy lại terraform plan để xem chính xác thay đổi sẽ được thực hiện.

Generated configuration chỉ là điểm khởi đầu. Nó có thể chứa nhiều thuộc tính hơn mức cần thiết, giá trị cố định hoặc thuộc tính chưa phù hợp với cấu trúc module. Không đưa file được sinh thẳng vào production mà chưa review.

## 8. Import ID của một số tài nguyên Google Cloud phổ biến

Google provider định nghĩa import ID theo từng resource type. Một số resource chấp nhận tên đơn giản; resource khác cần đường dẫn đầy đủ gồm project, region hoặc zone.

Các ví dụ thường gặp:

| Terraform resource | Import ID minh họa |
|---|---|
| google_project | my-project |
| google_compute_network | projects/my-project/global/networks/shared-vpc |
| google_compute_subnetwork | projects/my-project/regions/asia-southeast1/subnetworks/app-subnet |
| google_compute_instance | projects/my-project/zones/asia-southeast1-a/instances/app-vm |
| google_compute_firewall | projects/my-project/global/firewalls/allow-internal |
| google_storage_bucket | company-archive-bucket |
| google_sql_database_instance | projects/my-project/instances/orders-db |

Đây là các dạng ID phổ biến để minh họa. Hãy kiểm tra tài liệu import của đúng resource và phiên bản Google provider đang khóa trong dự án trước khi chạy. Không suy ra ID chỉ từ tên hiển thị trên Console.

### Tại sao cần project, region và zone?

Tên tài nguyên thường chỉ duy nhất trong một phạm vi. Ví dụ:

- Compute Engine network là tài nguyên global trong project.
- Subnetwork thuộc một region.
- VM thuộc một zone.
- Cloud SQL instance thuộc project.
- Cloud Storage bucket có tên toàn cục trong namespace bucket.

Nếu thiếu project hoặc location trong import ID, provider có thể không tìm thấy resource hoặc tìm nhầm đối tượng cùng tên trong một phạm vi khác.

## 9. Ví dụ thực hành: tiếp nhận một VPC và subnet hiện có

Giả sử project my-project có:

- VPC shared-vpc.
- Subnet app-subnet trong region asia-southeast1.
- VPC không dùng auto-created subnetworks.
- Subnet có primary IP range đã được nhóm network phê duyệt.

### Bước 1: cấu hình provider và resource

~~~hcl
provider "google" {
  project = "my-project"
  region  = "asia-southeast1"
}

resource "google_compute_network" "shared" {
  project                 = "my-project"
  name                    = "shared-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "app" {
  project       = "my-project"
  name          = "app-subnet"
  region        = "asia-southeast1"
  network       = google_compute_network.shared.id
  ip_cidr_range = "10.20.0.0/20"
}
~~~

Các giá trị CIDR và thuộc tính trong ví dụ phải được thay bằng cấu hình thực tế. Đừng chọn một CIDR mới nếu subnet đã có dải địa chỉ đang phục vụ workload.

### Bước 2: khai báo import

~~~hcl
import {
  to = google_compute_network.shared
  id = "projects/my-project/global/networks/shared-vpc"
}

import {
  to = google_compute_subnetwork.app
  id = "projects/my-project/regions/asia-southeast1/subnetworks/app-subnet"
}
~~~

### Bước 3: tạo và review plan

~~~bash
terraform init
terraform fmt
terraform validate
terraform plan
~~~

Kiểm tra:

- Hai resource được nhận diện là sẽ import.
- Không có resource mới cùng tên được đề xuất tạo.
- Terraform không đề xuất thay đổi CIDR hoặc cấu hình network ngoài dự kiến.
- Network reference trong subnet trỏ đúng VPC.
- Không có thao tác destroy/replace ngoài phạm vi.

### Bước 4: import và xác minh state

Sau khi review plan và được phê duyệt theo quy trình của dự án:

~~~bash
terraform apply
terraform state list
terraform state show google_compute_network.shared
terraform state show google_compute_subnetwork.app
~~~

Cuối cùng chạy:

~~~bash
terraform plan
~~~

Mục tiêu là plan không còn thay đổi ngoài dự kiến. Nếu Terraform đề xuất thay đổi, hãy xác định nguyên nhân trước khi apply lần tiếp theo.

## 10. Ví dụ thực hành: import bucket Cloud Storage

Giả sử bucket company-archive-bucket đã tồn tại. Resource block cần mô tả đúng các thuộc tính đang dùng.

~~~hcl
resource "google_storage_bucket" "archive" {
  project                     = "my-project"
  name                        = "company-archive-bucket"
  location                    = "ASIA-SOUTHEAST1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
}
~~~

Import block:

~~~hcl
import {
  to = google_storage_bucket.archive
  id = "company-archive-bucket"
}
~~~

Nếu dùng CLI:

~~~bash
terraform import google_storage_bucket.archive company-archive-bucket
~~~

Sau import, kiểm tra các thuộc tính như location, storage class, uniform bucket-level access, retention policy, versioning, lifecycle rule, encryption và public access prevention. Bucket có thể chứa dữ liệu production; thay đổi retention hoặc lifecycle có thể ảnh hưởng đến khả năng truy cập và lưu giữ dữ liệu.

Không thêm lifecycle rule hoặc thay đổi quyền public chỉ vì muốn HCL ngắn hơn. Hãy phản ánh trạng thái đang được phê duyệt và tách thay đổi thiết kế khỏi hoạt động import.

## 11. Xử lý drift sau import

Sau khi import, Terraform refresh các thuộc tính thực tế và so sánh với HCL. Một số khác biệt là bình thường vì cấu hình cũ được tạo bằng Console hoặc công cụ khác.

Ví dụ:

- Tài nguyên có label do hệ thống khác thêm.
- VPC dùng routing mode khác với giá trị trong HCL.
- Bucket bật versioning nhưng configuration chưa khai báo.
- VM có machine type, disk hoặc metadata khác dự kiến.
- Cloud SQL có backup, maintenance window hoặc database flag được cấu hình ngoài Terraform.

### Phân loại khác biệt

| Loại khác biệt | Hành động |
|---|---|
| Thuộc tính thực tế đúng và cần tiếp tục giữ | Bổ sung vào HCL hoặc dùng giá trị phù hợp |
| Thuộc tính do provider tự suy ra/default | Xem schema và plan; tránh khai báo thừa gây diff |
| Thay đổi thủ công không được phê duyệt | Làm rõ owner và quyết định khôi phục hay chấp nhận |
| Thuộc tính nhạy cảm hoặc không cần quản lý | Xem xét data source hoặc cách quản lý phù hợp |
| Thuộc tính buộc thay thế resource | Đánh giá downtime, dữ liệu và kế hoạch migration trước khi thực hiện |

### Hiểu các action trong plan

- **No changes:** configuration và state/remote object đã khớp theo các thuộc tính Terraform quản lý.
- **Update in-place:** Terraform dự kiến cập nhật thuộc tính mà provider cho phép thay đổi trực tiếp.
- **Destroy and create / replacement:** một hoặc nhiều thuộc tính yêu cầu thay thế resource; có thể gây gián đoạn hoặc mất dữ liệu nếu không có kế hoạch.
- **Read:** Terraform chỉ đọc data source hoặc làm mới thông tin.

Sau import, không chạy apply chỉ để làm plan “xanh”. Nếu có replacement, hãy kiểm tra thuộc tính nào buộc thay thế, tác động và khả năng migration. Một số resource có trường ForceNew; thay đổi trường đó có thể khiến Terraform tạo tài nguyên mới rồi xóa tài nguyên cũ.

## 12. Import nhiều tài nguyên và tổ chức module

Khi tiếp nhận một hệ thống đã tồn tại, thường cần import nhiều resource có quan hệ với nhau. Hãy phân nhóm theo ranh giới quản lý thay vì import mọi thứ vào một state lớn.

Ví dụ nhóm network có thể quản lý:

- VPC và subnet.
- Firewall rule.
- Cloud Router và Cloud NAT.
- Static external IP.
- Load balancer components.

Nhóm compute có thể quản lý:

- VM và boot disk.
- Instance template và Managed Instance Group.
- Service account và IAM binding liên quan.
- Health check và autoscaling policy.

### Thứ tự import

Nên bắt đầu từ tài nguyên nền tảng mà các resource khác tham chiếu, chẳng hạn project, network và subnet; tiếp theo import compute, database và các thành phần phụ thuộc. Thứ tự này giúp dễ viết references trong HCL và đọc plan.

Tuy nhiên, thứ tự import không tự tạo dependency. Terraform xác định dependency từ các expression references và meta-arguments trong configuration. Hãy khai báo tham chiếu rõ ràng thay vì hardcode ID khi tài nguyên được quản lý trong cùng module.

### Import block với nhiều resource

Có thể khai báo nhiều import block trong cùng cấu hình:

~~~hcl
import {
  to = google_compute_network.shared
  id = "projects/my-project/global/networks/shared-vpc"
}

import {
  to = google_compute_firewall.internal
  id = "projects/my-project/global/firewalls/allow-internal"
}

import {
  to = google_storage_bucket.archive
  id = "company-archive-bucket"
}
~~~

Mỗi block cần một target address duy nhất và một import ID chính xác. Khi import số lượng lớn, chia thành nhóm nhỏ theo service hoặc dependency để review và rollback state dễ hơn.

## 13. Những tình huống cần xử lý riêng

### Resource đã nằm trong Terraform state khác

Không import thêm vào state mới trước khi xác định state hiện tại và chủ sở hữu. Nếu cần chuyển quyền quản lý, hãy lập kế hoạch state migration bằng công cụ Terraform phù hợp và kiểm tra mapping trước/sau. Không để hai pipeline cùng apply lên một resource.

### Resource không được provider hỗ trợ import

Kiểm tra tài liệu resource. Nếu provider không hỗ trợ import, có thể cần dùng resource khác, data source, nâng cấp provider đã được kiểm thử hoặc thiết kế lại cách quản lý. Không tự chỉnh sửa state JSON để ép ánh xạ.

### Resource nằm trong module hoặc dùng count/for_each

Địa chỉ phải khớp chính xác với cấu trúc configuration, bao gồm module path và instance key/index. Một địa chỉ sai có thể khiến import thất bại hoặc gắn resource vào vị trí không mong muốn.

### Resource có dependency ngoài Terraform

Một VM có thể phụ thuộc vào service account, subnet, disk, firewall rule và metadata do hệ thống khác quản lý. Import VM không tự import những dependency đó. Hãy quyết định dependency nào thuộc state này, dependency nào được quản lý ở state khác và dependency nào chỉ cần đọc bằng data source.

### Resource chứa dữ liệu hoặc có tác động khó đảo ngược

Bucket, database, disk và resource IAM có thể chứa dữ liệu hoặc quyền truy cập quan trọng. Import không thay đổi đối tượng từ xa, nhưng apply sau đó có thể thay đổi retention, encryption, network access hoặc xóa tài nguyên. Cần kiểm tra lifecycle, deletion protection và backup trước khi thay đổi.

## 14. Những lệnh Terraform hữu ích khi import

| Lệnh | Mục đích |
|---|---|
| terraform version | Xác nhận phiên bản CLI |
| terraform init | Khởi tạo backend và provider |
| terraform providers | Xem provider đang được cấu hình |
| terraform fmt | Chuẩn hóa HCL |
| terraform validate | Kiểm tra cấu trúc configuration |
| terraform plan | Xem thay đổi dự kiến |
| terraform plan -generate-config-out=generated.tf | Sinh cấu hình sơ bộ cho resource chưa có block |
| terraform import ADDRESS ID | Import một resource vào state |
| terraform state list | Liệt kê resource address trong state |
| terraform state show ADDRESS | Xem thuộc tính state của một resource |
| terraform state pull | Đọc bản state hiện tại từ backend |
| terraform plan -refresh-only | Xem kế hoạch chỉ cập nhật state theo remote |

Các lệnh đọc state có thể hiển thị thuộc tính nhạy cảm. Chỉ chạy trong môi trường tin cậy và không chia sẻ output chứa secret.

## 15. Checklist trước và sau import production

**Trước import**

- [ ] Đã xác định đúng project, organization, region và zone.
- [ ] Đã xác minh resource chưa bị quản lý bởi Terraform state khác.
- [ ] Đã thống nhất service owner và phạm vi tài nguyên sẽ tiếp nhận.
- [ ] Đã kiểm tra phiên bản Terraform và Google provider.
- [ ] Đã cấu hình ADC/impersonation và quyền IAM tối thiểu.
- [ ] Đã xác nhận GCS backend, prefix, locking và versioning.
- [ ] Đã sao lưu state hiện tại theo quy trình an toàn.
- [ ] Đã viết resource block hoặc import block với đúng address và import ID.
- [ ] Đã kiểm tra dependency và các thuộc tính quan trọng.

**Sau import**

- [ ] terraform state list hiển thị đúng resource address.
- [ ] terraform state show xác nhận đúng project, tên và location.
- [ ] Không có resource bị import trùng hoặc quản lý bởi hai state.
- [ ] terraform plan không đề xuất thay đổi ngoài dự kiến.
- [ ] Mọi update hoặc replacement đều đã được review và phê duyệt riêng.
- [ ] HCL được chuẩn hóa, biến hóa và đặt trong module phù hợp.
- [ ] State backend có IAM, versioning và quy trình backup.
- [ ] CI/CD dùng đúng workspace/backend và provider lock file.
- [ ] Runbook hoặc tài liệu vận hành được cập nhật khi ownership thay đổi.

## Kết luận

Import là bước đưa tài nguyên GCP đang tồn tại vào phạm vi quản lý của Terraform thông qua state mapping. CLI import phù hợp với thao tác trực tiếp; import block giúp lưu ý định import trong HCL và review qua plan. Thành công không chỉ là lệnh import chạy xong: configuration phải phản ánh tài nguyên thực tế, state phải đúng backend, dependency và quyền sở hữu phải rõ ràng, và plan sau import không được chứa thay đổi ngoài dự kiến. Khi thực hiện theo từng nhóm nhỏ, có backup và review plan kỹ, tổ chức có thể tiếp nhận hạ tầng tạo thủ công vào IaC mà giảm rủi ro gián đoạn production.

## Tài liệu tham khảo

- [Terraform: Import existing resources](https://developer.hashicorp.com/terraform/language/import)
- [Terraform CLI: import command](https://developer.hashicorp.com/terraform/cli/commands/import)
- [Terraform: Import block reference](https://developer.hashicorp.com/terraform/language/block/import)
- [Terraform: Generate configuration](https://developer.hashicorp.com/terraform/language/import/generating-configuration)
- [Terraform: State](https://developer.hashicorp.com/terraform/language/state)
- [Terraform: GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs)
- [Google provider: Resource documentation](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [Google provider: Compute network resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_network)
- [Google provider: Compute subnetwork resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_subnetwork)
- [Google provider: Compute instance resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_instance)
- [Google provider: Storage bucket resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/storage_bucket)

