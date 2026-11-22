# Terraform state trên Cloud Storage và kiểm soát truy cập

Terraform dùng **state** để ghi nhớ mối quan hệ giữa cấu hình Infrastructure as Code và các tài nguyên thực tế trên Google Cloud. Khi nhiều kỹ sư hoặc pipeline cùng quản lý một hạ tầng, state cần được lưu ở nơi dùng chung, có cơ chế khóa khi cập nhật và có quyền truy cập được kiểm soát chặt chẽ. Google Cloud Storage (GCS) cung cấp backend từ xa cho Terraform: state được lưu thành object trong bucket, Terraform hỗ trợ khóa state khi thực hiện thao tác ghi và Cloud Storage cung cấp IAM, mã hóa, versioning cùng audit log để bảo vệ dữ liệu.

Trong module `CLOUD_PROVIDERS_GCP`, bài học này kết nối Terraform với việc tổ chức project, IAM và VPC, triển khai Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. State là dữ liệu quản trị quan trọng của toàn bộ quy trình đó. Nếu state bị mất, bị ghi đè hoặc lộ cho người không có thẩm quyền, nhóm có thể mất khả năng quản lý chính xác tài nguyên hoặc làm lộ thông tin nhạy cảm của hạ tầng.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vai trò của Terraform state, backend từ xa và state locking.
- Cấu hình backend `gcs` để lưu state trong Cloud Storage.
- Tạo bucket state với Uniform bucket-level access, Public access prevention và Object Versioning.
- Phân quyền cho Terraform runner bằng IAM tối thiểu và service account impersonation.
- Di chuyển state từ local sang GCS, sử dụng workspace và quản lý nhiều state độc lập.
- Bảo vệ state bằng mã hóa, audit log, quy trình backup và phục hồi.
- Nhận biết các rủi ro khi chia sẻ `terraform_remote_state`, sử dụng workspace như ranh giới bảo mật hoặc lưu credential trong backend configuration.

## 1. Terraform state là gì?

### Vai trò của state

Terraform đọc cấu hình `.tf`, gọi provider để truy vấn hoặc thay đổi tài nguyên, rồi lưu trạng thái đã biết vào state. State ánh xạ địa chỉ resource trong cấu hình với ID và thuộc tính của tài nguyên thực tế. Nó còn lưu thông tin phụ trợ để Terraform tính toán thay đổi trong lần `plan` tiếp theo.

Ví dụ cấu hình:

```hcl
resource "google_storage_bucket" "app_data" {
  name                        = "example-app-data"
  location                    = "ASIA-SOUTHEAST1"
  uniform_bucket_level_access = true
}
```

Trong state, Terraform có thể lưu địa chỉ `google_storage_bucket.app_data`, ID bucket, location, thuộc tính cấu hình và metadata do provider trả về. Khi chạy `terraform plan`, Terraform đối chiếu ba nguồn:

1. **Configuration**: trạng thái mong muốn được mô tả trong mã Terraform.
2. **State**: trạng thái gần nhất Terraform đã ghi nhận và ánh xạ với resource.
3. **Remote infrastructure**: tài nguyên thực tế trên Google Cloud mà provider truy vấn được.

Từ đó Terraform xác định resource cần tạo, cập nhật, thay thế hoặc xóa.

### State không phải bản sao đầy đủ của hạ tầng

State không thay thế Cloud Asset Inventory, Cloud Monitoring hay cấu hình thực tế của từng dịch vụ. Nó chỉ ghi nhận các resource thuộc phạm vi quản lý của một cấu hình và provider. Nếu một kỹ sư tạo VM thủ công ngoài Terraform, resource đó không tự động xuất hiện trong state. Muốn Terraform quản lý resource đã tồn tại, cần dùng quy trình `terraform import` hoặc import block phù hợp.

State cũng không phải file cấu hình để chỉnh sửa trực tiếp. Terraform lưu state dưới dạng JSON, nhưng việc sửa JSON bằng tay có thể làm sai lineage, serial hoặc ánh xạ resource. Hãy dùng các lệnh `terraform state` và quy trình import/move/remove được hỗ trợ.

### Vì sao state cần được bảo vệ?

State và plan file có thể chứa:

- Resource ID, tên project, tên bucket, địa chỉ IP, network topology và metadata của workload.
- Giá trị được provider trả về, data source results và các thuộc tính cấu hình.
- Mật khẩu database, token, private endpoint, thông tin xác thực hoặc secret nếu provider lưu chúng vào state.
- Giá trị biến/output nhạy cảm được Terraform đánh dấu `sensitive`.

Thuộc tính `sensitive = true` chủ yếu che giá trị khỏi một số đầu ra CLI và giao diện. Terraform vẫn lưu giá trị đó trong state và plan file nếu thuộc tính resource yêu cầu lưu. Vì vậy, người có quyền đọc state có thể lấy được những giá trị nhạy cảm nằm trong đó. Cần coi state và các bản sao state là dữ liệu bí mật.

Không commit state, plan file hoặc thư mục backend cache vào Git. Một `.gitignore` cơ bản có thể gồm:

```gitignore
.terraform/
*.tfstate
*.tfstate.*
*.tfplan
crash.log
```

Giữ file `.terraform.lock.hcl` trong Git để nhóm dùng cùng phiên bản provider đã được khóa. Nếu tạo plan artifact trong CI, lưu artifact trong kho có IAM và thời hạn lưu phù hợp; không đính kèm plan vào issue hoặc chat công khai.

## 2. Remote backend và GCS backend

### Backend làm nhiệm vụ gì?

Backend quyết định nơi Terraform lưu state và cơ chế phối hợp giữa các lần chạy. Backend local mặc định lưu `terraform.tfstate` trên máy đang chạy. Khi nhiều người làm việc trên cùng một hệ thống, local state dễ bị lệch phiên bản, mất khi máy hỏng hoặc bị ghi đè nếu nhiều người thao tác không đồng bộ.

Remote backend lưu state ở một hệ thống dùng chung. Các thành viên và pipeline có thể làm việc với cùng một state mới nhất mà không phải gửi file qua email hoặc commit vào Git. Backend có hỗ trợ locking sẽ khóa state trong các thao tác có thể ghi, tránh hai tiến trình cùng cập nhật một state.

### GCS backend

Terraform backend `gcs` lưu state thành object trong một bucket Google Cloud Storage đã tồn tại. Backend hỗ trợ state locking và nhiều workspace. Bucket phải được tạo trước khi cấu hình backend; không thể dùng chính cấu hình cần backend đó để lần đầu tạo bucket chứa state.

Ví dụ cấu trúc lưu trữ:

```text
Cloud Storage project: platform-state-prod
└── Bucket: acme-tf-state-prod
    └── Prefix: gcp/network
        ├── default.tfstate
        ├── staging.tfstate
        └── production.tfstate
```

Với named workspace, GCS backend lưu state theo object path dạng `<prefix>/<workspace-name>.tfstate`. State của workspace `default` cũng nằm dưới prefix của backend. Hãy dùng đúng prefix cho từng root module hoặc stack để tránh các cấu hình độc lập ghi vào cùng một state.

### Lợi ích và giới hạn

| Khả năng | Lợi ích | Điều cần quản lý |
|---|---|---|
| Lưu object trong GCS | Có nơi lưu dùng chung, bền vững và tích hợp IAM. | Bảo vệ bucket và các object state như dữ liệu nhạy cảm. |
| State locking | Ngăn các thao tác ghi đồng thời lên cùng state. | Không bỏ qua lock khi chạy production; xử lý lock lỗi theo quy trình. |
| Object Versioning | Giữ phiên bản cũ khi object state bị thay thế hoặc xóa. | Theo dõi dung lượng và lifecycle của các phiên bản cũ. |
| IAM | Cấp quyền theo user, group hoặc service account. | Quyền ở bucket áp dụng cho các object; workspace prefix không tự tạo ranh giới IAM. |
| Cloud KMS CMEK | Cho phép khách hàng quản lý khóa mã hóa dữ liệu state. | GCS service agent cần quyền dùng khóa; không được xóa khóa đang cần để giải mã state. |

## 3. Chuẩn bị Cloud Storage bucket cho Terraform state

### Chọn project và location

Nên đặt bucket state trong một project quản lý nền tảng riêng, ví dụ `platform-state-prod`, tách khỏi project chạy ứng dụng. Cách tổ chức này giúp nhóm nền tảng quản lý vòng đời bucket, IAM, logging và khóa độc lập với nhóm phát triển workload.

Chọn location theo yêu cầu data residency, độ trễ của pipeline và chính sách vận hành. Nếu state chứa metadata nhạy cảm hoặc định danh hạ tầng thuộc một khu vực được quản lý, location của bucket phải phù hợp với chính sách đó. Tên bucket là tên toàn cục và có thể được nhìn thấy công khai; không đưa thông tin bí mật, tên khách hàng hoặc dữ liệu nhạy cảm vào tên bucket.

### Các cấu hình bảo mật nên bật

| Cấu hình | Khuyến nghị | Lý do |
|---|---|---|
| Uniform bucket-level access (UBLA) | Bật. | Dùng IAM thống nhất ở cấp bucket và vô hiệu hóa ACL ở cấp object. |
| Public access prevention (PAP) | Enforced. | Ngăn cấp quyền công khai qua `allUsers` hoặc `allAuthenticatedUsers`. |
| Object Versioning | Bật. | Giữ phiên bản state trước đó để hỗ trợ phục hồi khi xóa hoặc ghi nhầm. |
| Encryption at rest | Giữ mã hóa mặc định của Cloud Storage hoặc dùng CMEK nếu chính sách yêu cầu. | Bảo vệ state khi lưu trữ. |
| Data Access audit logs | Bật theo yêu cầu kiểm toán. | Ghi nhận hoạt động đọc/ghi object state để điều tra. |
| Lifecycle | Đặt theo chính sách lưu giữ và chi phí. | Tránh tích lũy quá nhiều noncurrent object versions. |

UBLA làm cho IAM trở thành cơ chế kiểm soát truy cập duy nhất đối với bucket và object; các ACL riêng lẻ không còn được áp dụng. PAP bảo vệ bucket khỏi việc vô tình cấp quyền truy cập công khai. Hai cơ chế có mục đích khác nhau và nên dùng cùng nhau cho bucket state riêng tư.

### Tạo bucket bằng gcloud

Ví dụ dưới đây tạo bucket state tại `asia-southeast1`. Hãy thay `STATE_PROJECT_ID` và `BUCKET_NAME` bằng giá trị thực. Bucket name phải duy nhất toàn cầu.

```bash
gcloud config set project STATE_PROJECT_ID

gcloud services enable storage.googleapis.com

gcloud storage buckets create gs://BUCKET_NAME \
  --project=STATE_PROJECT_ID \
  --location=asia-southeast1 \
  --uniform-bucket-level-access \
  --public-access-prevention

# Bật Object Versioning để giữ các phiên bản state cũ.
gcloud storage buckets update gs://BUCKET_NAME --versioning

# Kiểm tra cấu hình bucket.
gcloud storage buckets describe gs://BUCKET_NAME
```

`asia-southeast1` chỉ là location minh họa. Không dùng region này nếu yêu cầu data residency hoặc kiến trúc của tổ chức cần location khác.

### Vì sao cần Object Versioning?

Terraform thường xuyên ghi phiên bản mới của state sau các thao tác apply. Khi Object Versioning được bật, Cloud Storage giữ các generation cũ dưới dạng noncurrent versions khi object hiện tại bị thay thế hoặc xóa. Điều này giúp phục hồi state trong các tình huống như thao tác thủ công nhầm, lỗi automation hoặc cần điều tra lịch sử.

Object Versioning không thay thế state locking. Versioning giữ lịch sử object; locking điều phối các thao tác Terraform đang chạy. Cả hai giải quyết hai rủi ro khác nhau.

Các phiên bản cũ tiêu thụ dung lượng lưu trữ. Nên định nghĩa lifecycle rule để quản lý noncurrent versions theo chính sách, nhưng không xóa phiên bản quá sớm nếu tổ chức cần thời gian phục hồi hoặc kiểm toán. Kết hợp Object Versioning với soft delete nếu chính sách bảo vệ dữ liệu yêu cầu và ngân sách cho phép.

### Tránh retention policy không phù hợp

Bucket state cần được Terraform cập nhật liên tục. Một retention policy hoặc bucket lock có thể ngăn xóa object trong thời hạn đã đặt, dẫn tới thao tác ghi state hoặc dọn lock không hoàn tất như mong đợi. Chỉ áp dụng retention policy có thời hạn hoặc khóa retention khi đã kiểm thử đầy đủ hành vi của GCS backend và có quy trình thay đổi state tương ứng. Object Versioning thường là lựa chọn phục hồi đơn giản hơn cho bucket state.

## 4. IAM và kiểm soát truy cập bucket state

### Tách danh tính quản trị bucket và danh tính chạy Terraform

Nên tách ít nhất ba nhóm danh tính:

1. **Bucket administrators**: tạo bucket, bật versioning, cấu hình UBLA/PAP, IAM, CMEK và lifecycle. Nhóm này có quyền quản trị bucket nhưng không cần tham gia mọi lần `terraform apply`.
2. **Terraform runtime identity**: service account mà pipeline hoặc người vận hành impersonate để đọc, ghi và khóa state. Chỉ cấp quyền trên bucket state cần dùng.
3. **State readers / auditors**: người cần kiểm tra state hoặc lịch sử truy cập. Quyền đọc state vẫn có thể làm lộ secret, nên cần giới hạn số người được cấp.

### Vai trò cho Terraform runtime

HashiCorp GCS backend yêu cầu danh tính dùng backend có quyền **Storage Object Admin** (`roles/storage.objectAdmin`) trên bucket chứa state. Vai trò này cho phép đọc, liệt kê, tạo, cập nhật và xóa object cần cho state cùng lock. Nếu tổ chức xây dựng custom role, cần bảo đảm đủ các quyền object mà backend sử dụng và kiểm thử trên phiên bản Terraform đang triển khai.

Ví dụ cấp quyền ở đúng bucket:

```bash
gcloud storage buckets add-iam-policy-binding gs://BUCKET_NAME \
  --member="serviceAccount:terraform-state-writer@STATE_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

Không cấp `roles/storage.admin` ở project chỉ để Terraform đọc/ghi state. Storage Admin có quyền quản trị bucket và IAM rộng hơn nhu cầu runtime. Nhóm quản trị bucket có thể giữ vai trò rộng; service account chạy Terraform chỉ cần Object Admin trên bucket state tương ứng.

IAM thay đổi trên bucket có thể mất một khoảng thời gian để có hiệu lực. Nếu backend trả `403` ngay sau khi cấp quyền, hãy kiểm tra đúng principal, bucket, project và chờ policy propagation trước khi thay đổi cấu hình khác.

### Quyền đọc state cũng là quyền đọc dữ liệu nhạy cảm

Một người có `roles/storage.objectViewer` hoặc quyền đọc object phù hợp có thể tải state JSON. Họ có thể xem nhiều thuộc tính của hạ tầng và các giá trị bí mật được provider lưu trong state. Vì vậy:

- Không cấp quyền đọc state cho toàn bộ developer nếu họ chỉ cần xem output của một dịch vụ.
- Tách bucket hoặc project cho các ranh giới bảo mật khác nhau, đặc biệt production và non-production.
- Dùng group quản trị thay vì cấp quyền trực tiếp cho nhiều user cá nhân.
- Rà soát IAM policy định kỳ và thu hồi quyền khi nhân sự hoặc pipeline không còn phụ trách stack.
- Bật Data Access audit logs để có thể điều tra hoạt động đọc và ghi state.

### Workspace không phải ranh giới bảo mật

Terraform workspace tạo nhiều state logic dưới cùng một backend. Workspace có ích để triển khai nhiều bản sao của cùng cấu hình, nhưng không phù hợp cho hệ thống cần credential và access control độc lập. Nếu một service account có quyền Object Admin trên bucket, nó có thể truy cập object của các workspace khác trong bucket đó.

Với production, staging và development cần người quản trị hoặc quyền truy cập khác nhau, nên dùng bucket riêng hoặc project riêng với IAM riêng. Không dựa vào prefix hoặc tên workspace để thay thế phân tách quyền.

## 5. Xác thực an toàn cho GCS backend

### Application Default Credentials trên máy phát triển

Khi chạy Terraform từ workstation, có thể sử dụng Application Default Credentials (ADC):

```bash
gcloud auth application-default login
gcloud config set project STATE_PROJECT_ID
```

Terraform GCS backend sẽ dùng ADC nếu không cấu hình credential khác. ADC của user có thể hết hạn; khi gặp lỗi xác thực, làm mới ADC theo quy trình đăng nhập của tổ chức. Không sao chép credential file vào repository.

### Service account trên Google Cloud

Nếu Terraform chạy trên môi trường Google Cloud, ví dụ VM hoặc runner trên GKE, ưu tiên gắn service account phù hợp với workload. Terraform có thể sử dụng ADC của môi trường đó để gọi Cloud Storage. Không cần tạo và lưu service account JSON key chỉ để backend truy cập bucket.

### Impersonate service account

Một mô hình thường dùng là kỹ sư hoặc CI runner xác thực bằng danh tính ngắn hạn rồi impersonate service account chuyên dùng cho state. Backend hỗ trợ `impersonate_service_account`.

Ví dụ cấu hình:

```hcl
terraform {
  backend "gcs" {
    bucket                      = "BUCKET_NAME"
    prefix                      = "gcp/network/prod"
    impersonate_service_account = "terraform-state-writer@STATE_PROJECT_ID.iam.gserviceaccount.com"
  }
}
```

Danh tính nguồn phải có quyền `roles/iam.serviceAccountTokenCreator` trên service account đích để việc impersonation thành công. Service account đích có `roles/storage.objectAdmin` trên bucket state. Khi dùng Workload Identity Federation trong CI, cấu hình federation để runner nhận credential ngắn hạn và chỉ được impersonate đúng service account cần thiết.

Backend và provider là hai phần cấu hình xác thực riêng. Nếu backend dùng service account impersonation để truy cập state, provider Google cũng cần cấu hình danh tính phù hợp để tạo hoặc quản lý tài nguyên trong project đích. Không giả định backend identity tự động trở thành provider identity trong mọi cấu hình.

### Tránh lưu credential trong backend configuration

Không hardcode service account key JSON, access token hoặc credential nhạy cảm trong `backend "gcs"` hay truyền trực tiếp qua `-backend-config` nếu giá trị đó là bí mật. Terraform có thể ghi backend configuration vào `.terraform` và plan file; credential đặt ở đó có thể bị lưu dưới dạng văn bản.

Ưu tiên ADC, Workload Identity Federation, service account gắn với workload hoặc impersonation. Nếu cần truyền cấu hình backend riêng qua file, chỉ truyền các giá trị không bí mật như bucket, prefix hoặc service account email và bảo vệ file theo quy trình nội bộ.

## 6. Cấu hình Terraform backend `gcs`

### Backend block tối thiểu

Thêm block sau vào root module:

```hcl
terraform {
  backend "gcs" {
    bucket = "BUCKET_NAME"
    prefix = "gcp/network/prod"
  }
}
```

`bucket` là tên bucket đã tạo trước đó. `prefix` là đường dẫn logic trong bucket để tách state của root module. Không dùng dấu slash đầu prefix và tránh để nhiều cấu hình độc lập dùng cùng bucket/prefix/workspace.

Backend block chỉ được cấu hình bằng giá trị tĩnh. Không thể tham chiếu `var.*`, `local.*`, output của resource hoặc data source trong backend block vì Terraform phải khởi tạo backend trước khi đánh giá phần còn lại của cấu hình.

### Backend với CMEK

Nếu tổ chức yêu cầu Customer-Managed Encryption Key, có thể khai báo `kms_encryption_key` trong GCS backend:

```hcl
terraform {
  backend "gcs" {
    bucket           = "BUCKET_NAME"
    prefix           = "gcp/network/prod"
    kms_encryption_key = "projects/KEY_PROJECT_ID/locations/asia-southeast1/keyRings/tf-state-ring/cryptoKeys/tf-state-key"
  }
}
```

Khóa Cloud KMS phải ở location tương thích với bucket theo yêu cầu Cloud Storage. GCS service agent của project chứa bucket cần vai trò `roles/cloudkms.cryptoKeyEncrypterDecrypter` trên CryptoKey. Service agent thường có dạng:

```text
service-PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com
```

Đây là danh tính dịch vụ Cloud Storage, khác với Terraform runtime service account. Nếu dùng CMEK, hãy bảo đảm key vẫn hoạt động và không bị lên lịch hủy trong suốt thời gian state cần được đọc. State đã mã hóa bằng khóa bị xóa hoặc mất quyền sử dụng có thể không khôi phục được.

Cloud Storage mặc định mã hóa dữ liệu at rest và bảo vệ kết nối API bằng TLS. CMEK bổ sung quyền kiểm soát khóa và yêu cầu vận hành KMS; chỉ bật khi có yêu cầu quản trị hoặc tuân thủ rõ ràng.

### Khởi tạo backend

Sau khi bucket và IAM đã sẵn sàng:

```bash
terraform init
```

Terraform tải provider/module cần thiết, khởi tạo backend và tạo thư mục `.terraform` cục bộ chứa metadata backend. Nếu thư mục trước đó đã khởi tạo bằng backend local và có state, Terraform có thể hỏi có muốn di chuyển state sang GCS hay không.

Khi chủ động chuyển local state sang GCS, dùng:

```bash
terraform init -migrate-state
```

Đọc kỹ thông báo migration, xác nhận bucket/prefix và kiểm tra state đã được lưu từ xa. Không xóa bản state local hoặc bản backup migration cho đến khi đã xác minh remote state hoạt động và quy trình khôi phục đã được hiểu rõ.

Sau khi khởi tạo, có thể kiểm tra backend đang dùng bằng `terraform init` output và kiểm tra state:

```bash
terraform workspace show
terraform state list
terraform plan
```

## 7. State locking và thao tác đồng thời

### Locking hoạt động như thế nào?

GCS backend hỗ trợ state locking. Terraform tự động lấy lock trước các thao tác có thể ghi state, ví dụ `apply`, `import` hoặc một số thao tác state. Nếu một tiến trình khác đang giữ lock, tiến trình mới phải chờ hoặc thất bại theo timeout đã cấu hình. Điều này ngăn nhiều người cùng ghi state và làm hỏng ánh xạ resource.

Có thể đặt thời gian chờ lock khi chạy lệnh:

```bash
terraform apply -lock-timeout=5m
```

Locking là cơ chế phối hợp giữa các tiến trình Terraform. Nó không ngăn người có quyền Storage Object Admin xóa hoặc sửa object trực tiếp bằng Cloud Storage API, và không thay thế IAM.

### Không tắt locking trong production

Terraform có tùy chọn `-lock=false` cho một số lệnh, nhưng bỏ lock khi có nhiều người hoặc pipeline cùng làm việc có thể gây ghi đè state. Không dùng tùy chọn này để vượt qua lỗi lock trong production.

Nếu lock bị giữ sau khi runner bị dừng đột ngột:

1. Xác định pipeline hoặc người dùng nào đã tạo lock.
2. Kiểm tra tiến trình Terraform có còn chạy hoặc có job khác đang apply hay không.
3. Chỉ khi chắc chắn lock là stale và không còn writer hoạt động, mới xem xét `terraform force-unlock LOCK_ID`.
4. Dùng đúng lock ID do Terraform hiển thị; ghi nhận lý do và người thực hiện.
5. Chạy `terraform plan` để kiểm tra state và remote infrastructure trước thao tác tiếp theo.

`force-unlock` không phải cách khắc phục chung cho lỗi 403, lỗi quyền hoặc lỗi backend. Hãy xử lý nguyên nhân gốc trước.

### Object Versioning không phải locking

| Cơ chế | Bảo vệ trước điều gì? | Không giải quyết điều gì? |
|---|---|---|
| State locking | Hai tiến trình Terraform cùng ghi một state. | Người có IAM xóa hoặc ghi object trực tiếp. |
| Object Versioning | Mất phiên bản state do thay thế/xóa object. | Hai tiến trình cùng chạy plan/apply và xung đột logic. |
| IAM | Danh tính không được phép đọc/ghi state. | Lỗi logic do người có quyền thực hiện. |
| CMEK | Bảo vệ khóa mã hóa và quyền giải mã object. | Phân quyền ai được đọc state; người có quyền đọc object vẫn nhận plaintext nếu được phép dùng key. |

## 8. Workspace, prefix và phân chia state

### Tạo workspace

GCS backend hỗ trợ Terraform CLI workspaces. Ví dụ:

```bash
terraform workspace new staging
terraform workspace new production

terraform workspace list
terraform workspace select staging
terraform workspace show
```

Mỗi workspace có state riêng dưới cùng bucket/prefix. Terraform workspace cho phép một cấu hình tạo nhiều instance logic, nhưng tất cả vẫn dùng cùng backend configuration và thường chia sẻ một danh tính backend.

### Khi nào nên dùng workspace?

Workspace phù hợp khi:

- Các môi trường có cùng cấu trúc hạ tầng và cùng bộ quyền triển khai.
- Khác biệt chủ yếu là giá trị biến, kích thước hoặc tên tài nguyên.
- Một nhóm vận hành có quyền quản lý tất cả workspace trong cùng phạm vi.

Workspace không phù hợp khi production cần người phê duyệt khác, credential khác hoặc quyền đọc state tách biệt với staging. Trong trường hợp đó, hãy tạo root module hoặc stack riêng, bucket/prefix riêng và service account riêng.

### Chia state theo trách nhiệm

Một cách chia phổ biến:

```text
Bucket: acme-tf-state-prod
├── foundation/network/default.tfstate
├── platform/cluster/default.tfstate
├── application/checkout/default.tfstate
└── data/warehouse/default.tfstate

Bucket: acme-tf-state-nonprod
├── foundation/network/default.tfstate
├── platform/cluster/default.tfstate
└── application/checkout/default.tfstate
```

Chia state theo vòng đời và quyền sở hữu của thành phần hạ tầng. Network foundation, cluster platform và application có thể có nhóm vận hành, chu kỳ phát hành và quyền khác nhau. Mỗi root module nên có state riêng để giảm blast radius khi một lần apply lỗi.

Nếu dùng một bucket chung cho nhiều stack, prefix giúp tổ chức object nhưng IAM ở cấp bucket thường áp dụng trên toàn bucket. Muốn tách quyền thật sự, dùng bucket riêng hoặc cơ chế Managed Folders/IAM phù hợp và kiểm tra đầy đủ quyền `storage.objects.list`; không giả định IAM condition theo tên object sẽ giới hạn mọi thao tác list.

## 9. Quản lý dữ liệu nhạy cảm và remote state

### `sensitive` không loại bỏ dữ liệu khỏi state

Ví dụ:

```hcl
variable "database_password" {
  type      = string
  sensitive = true
}

output "database_connection_secret" {
  value     = var.database_password
  sensitive = true
}
```

Terraform sẽ che giá trị trong một số output của CLI, nhưng vẫn lưu giá trị nếu resource/output cần lưu vào state. Người có thể tải state vẫn có thể đọc giá trị đó. Không xem `sensitive = true` là cơ chế mã hóa hoặc phân quyền truy cập.

Terraform phiên bản mới có `ephemeral` values và một số provider resource hỗ trợ write-only arguments để không ghi một số giá trị vào state/plan. Chỉ sử dụng khi phiên bản Terraform và provider hỗ trợ đúng ngữ cảnh; cần đọc tài liệu provider. Thiết kế tốt nhất vẫn là tránh đưa secret vào resource attribute nếu dịch vụ hỗ trợ cơ chế tham chiếu Secret Manager hoặc credential ngắn hạn.

### `terraform_remote_state` có rủi ro gì?

Data source `terraform_remote_state` cho phép một cấu hình đọc output từ state của cấu hình khác. Ví dụ:

```hcl
data "terraform_remote_state" "network" {
  backend = "gcs"
  config = {
    bucket = "acme-tf-state-prod"
    prefix = "foundation/network"
  }
}

output "application_network_id" {
  value = data.terraform_remote_state.network.outputs.network_id
}
```

Mặc dù cấu hình chỉ tham chiếu output `network_id`, quyền truy cập backend cần đọc state object. State có thể chứa nhiều thuộc tính khác ngoài output đó, bao gồm dữ liệu nhạy cảm. Vì vậy, quyền đọc remote state là quyền truy cập vào toàn bộ snapshot state. Nếu chỉ cần chia sẻ một vài giá trị, cân nhắc xuất chúng qua một kênh được kiểm soát riêng như Secret Manager, cấu hình service discovery hoặc một API nội bộ có quyền hẹp.

## 10. Backup, phục hồi và di chuyển state

### Bảo vệ trước lỗi thao tác

Các biện pháp cơ bản:

- Bật Object Versioning cho bucket state.
- Cấu hình lifecycle cho noncurrent versions theo yêu cầu lưu giữ.
- Giới hạn IAM người có quyền xóa object hoặc thay đổi policy.
- Bật Data Access audit logs cho Cloud Storage nếu cần điều tra ai đã đọc/ghi object.
- Có quy trình backup và phục hồi được kiểm thử, không chỉ dựa vào việc versioning đang bật.
- Tránh chạy lệnh `terraform state push` hoặc sửa state JSON trực tiếp nếu không có kế hoạch khôi phục rõ ràng.

Có thể dùng `terraform state pull` để đọc snapshot state hiện tại, ví dụ khi tạo bản sao lưu có kiểm soát:

```bash
terraform state pull > state-backup.json
```

File `state-backup.json` chứa dữ liệu state đầy đủ và có thể bao gồm secret. Lưu file trong vùng mã hóa, giới hạn quyền đọc và xóa an toàn sau khi hoàn tất mục đích backup. Không để lệnh này ghi nội dung state vào log của pipeline.

### Phục hồi state từ object version cũ

Nếu state hiện tại bị ghi nhầm hoặc xóa:

1. Dừng các pipeline và yêu cầu không chạy `plan/apply` trên stack bị ảnh hưởng.
2. Xác định bucket, prefix, workspace và object path chính xác.
3. Liệt kê các object generations/versions và xác định phiên bản cuối cùng trước sự cố.
4. Tạo bản sao lưu riêng của state hiện tại để có thể quay lại nếu chọn nhầm generation.
5. Khôi phục phiên bản đã chọn về object path mà backend sử dụng theo quy trình Cloud Storage.
6. Kiểm tra state lineage, serial, resource list và đối chiếu với tài nguyên thực tế.
7. Chạy `terraform plan` để đánh giá drift trước khi cho phép apply.

Không khôi phục state cũ một cách vội vàng khi có một lần apply thành công sau thời điểm version đó. State cũ có thể không chứa các resource vừa tạo hoặc có serial thấp hơn; apply ngay có thể dẫn đến tạo trùng hoặc phá hủy tài nguyên.

### Di chuyển backend

Khi chuyển state từ local sang GCS hoặc từ bucket cũ sang bucket mới:

1. Tạm dừng các pipeline và người dùng đang thao tác trên stack.
2. Sao lưu state hiện tại và xác minh bản sao có thể đọc.
3. Cập nhật backend block tới bucket/prefix mới.
4. Chạy `terraform init -migrate-state` để Terraform chuyển state.
5. Xác nhận workspace, resource list và output không đổi ngoài dự kiến.
6. Chạy `terraform plan` và xác nhận không xuất hiện kế hoạch tạo/xóa hàng loạt bất thường.
7. Chỉ sau khi xác minh xong mới thu hồi quyền ở backend cũ hoặc áp dụng quy trình lưu trữ backend cũ.

Nếu đổi hoặc loại bỏ customer-supplied encryption key (CSEK), quy trình migration có thể cần thao tác rewrite object thủ công vì Cloud Storage không giữ key để tự giải mã. Với CMEK, Cloud Storage giữ metadata key và có thể hỗ trợ migration backend, nhưng cần giữ khóa cũ cho đến khi object state đã được ghi lại bằng khóa mới. Không xóa khóa KMS đang dùng để mã hóa state.

## 11. Audit và giám sát bucket state

### Cloud Audit Logs

Cloud Storage hỗ trợ Cloud Audit Logs để ghi nhận hoạt động quản trị và truy cập dữ liệu. Admin Activity logs giúp theo dõi thay đổi bucket/IAM. Data Access logs có thể ghi nhận thao tác đọc, ghi hoặc liệt kê object state; cần bật theo chính sách logging của organization/project và lưu ý chi phí log.

Nên theo dõi các sự kiện:

- Thay đổi IAM policy của bucket state.
- Thay đổi UBLA, PAP, versioning, retention hoặc encryption configuration.
- Tạo, đọc, ghi và xóa object state.
- Hoạt động truy cập bất thường từ principal không thuộc pipeline Terraform.
- Thay đổi hoặc xóa CryptoKey nếu bucket dùng CMEK.

### Tìm log Cloud Storage

Trong Logs Explorer, có thể lọc audit log của Cloud Storage theo service name:

```text
protoPayload.serviceName="storage.googleapis.com"
```

Sau đó giới hạn theo bucket resource, principal email hoặc method name để điều tra. Tên method có thể khác nhau theo JSON API và thao tác được gọi; hãy kiểm tra `protoPayload.methodName`, `resourceName` và `authenticationInfo.principalEmail` trong log thực tế.

### Cảnh báo vận hành

Có thể xây alert hoặc quy tắc SIEM cho:

- IAM policy bucket có thay đổi ngoài change window.
- Bucket state bị xóa hoặc cấu hình PAP/UBLA/versioning bị tắt.
- Object state bị xóa bất thường hoặc có principal lạ đọc state.
- Terraform backend trả lỗi 403, 412 hoặc lock timeout liên tục.
- KMS key bị disable, lên lịch hủy hoặc mất quyền truy cập.

Khi bật Data Access logs, cần đánh giá ingestion volume và thời gian lưu log. Log audit giúp điều tra truy cập nhưng không thay thế việc hạn chế IAM ngay từ đầu.

## 12. Quy trình triển khai mẫu cho network stack

Giả sử nhóm nền tảng quản lý VPC và subnet bằng Terraform. State của stack network được lưu trong bucket riêng `acme-tf-state-prod` ở project `platform-state-prod`.

### Bước 1: Tạo bucket state

```bash
gcloud config set project platform-state-prod

gcloud storage buckets create gs://acme-tf-state-prod \
  --project=platform-state-prod \
  --location=asia-southeast1 \
  --uniform-bucket-level-access \
  --public-access-prevention

gcloud storage buckets update gs://acme-tf-state-prod --versioning
```

### Bước 2: Tạo service account runtime và cấp quyền

```bash
gcloud iam service-accounts create terraform-state-writer \
  --project=platform-state-prod \
  --display-name="Terraform state writer"

gcloud storage buckets add-iam-policy-binding gs://acme-tf-state-prod \
  --member="serviceAccount:terraform-state-writer@platform-state-prod.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

Danh tính người dùng hoặc CI runner cần quyền impersonate service account này theo chính sách IAM của tổ chức. Service account runtime không cần quyền quản trị bucket hoặc quyền Owner trên project.

### Bước 3: Cấu hình backend

```hcl
terraform {
  backend "gcs" {
    bucket                      = "acme-tf-state-prod"
    prefix                      = "foundation/network"
    impersonate_service_account = "terraform-state-writer@platform-state-prod.iam.gserviceaccount.com"
  }
}
```

### Bước 4: Khởi tạo và kiểm tra

```bash
terraform init
terraform workspace show
terraform plan
```

Nếu stack trước đó đang dùng local state, thêm `-migrate-state` vào `terraform init` theo quy trình migration. Xác minh bucket đã có object state sau lần ghi đầu tiên và người không có quyền không thể đọc object.

### Bước 5: Chạy pipeline có kiểm soát

Pipeline cần xác thực qua Workload Identity Federation hoặc cơ chế credential ngắn hạn được tổ chức phê duyệt. Trước `terraform apply`, pipeline chạy `terraform plan`, lưu plan artifact trong vùng bảo vệ phù hợp và yêu cầu approval theo môi trường. Khi apply, Terraform tự dùng state lock. Pipeline phải dừng nếu không lấy được lock hoặc backend trả lỗi; không tự động bỏ lock để tiếp tục.

### Bước 6: Kiểm tra bảo vệ sau triển khai

- Xác nhận UBLA và PAP vẫn bật.
- Xác nhận Object Versioning đang hoạt động.
- Kiểm tra IAM chỉ có nhóm quản trị và runtime identity được phê duyệt.
- Kiểm tra audit log có thể truy vấn hoạt động object theo yêu cầu.
- Xác nhận prefix state không dùng chung với stack khác.
- Kiểm thử quy trình phục hồi state trên môi trường thử nghiệm.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `terraform init` báo bucket không tồn tại | Bucket chưa được tạo, sai project hoặc sai tên bucket. | Dùng `gcloud storage buckets describe` và kiểm tra `bucket` trong backend. |
| HTTP 403 khi đọc/ghi state | Principal thiếu quyền object, sai service account impersonation hoặc IAM chưa propagate. | Kiểm tra bucket IAM, principal thực tế, `roles/storage.objectAdmin` và token creator. |
| `terraform init` yêu cầu migrate | Working directory từng dùng backend khác hoặc local state đã tồn tại. | Xác nhận đúng bucket/prefix rồi dùng `-migrate-state` nếu muốn chuyển state. |
| Lock timeout | Pipeline khác đang chạy hoặc lock cũ chưa được giải phóng. | Kiểm tra job đang chạy; chỉ force-unlock khi chắc chắn lock stale. |
| Backend không đọc được CMEK object | GCS service agent thiếu quyền KMS, key bị disable hoặc location không phù hợp. | Kiểm tra CryptoKey IAM, trạng thái key, location và audit log KMS. |
| State bị lộ trong plan artifact | Plan file hoặc `.terraform` chứa backend config/giá trị nhạy cảm. | Giới hạn quyền artifact, không commit file, thay credential đã lộ và rà soát log. |
| Workspace dùng nhầm state | Sai workspace hoặc prefix giữa các root module. | Chạy `terraform workspace show`, kiểm tra backend block và object path. |
| Apply muốn tạo lại nhiều tài nguyên | State sai, workspace sai, provider/project khác hoặc resource đã drift. | Dừng apply, kiểm tra state list, project, lineage và remote resource trước khi xử lý. |

Khi backend gặp lỗi ghi state không thể phục hồi, Terraform có thể lưu state mới cục bộ để tránh mất dữ liệu. Hãy kiểm tra output của lệnh và tìm local state recovery file theo hướng dẫn Terraform; không tiếp tục apply cho đến khi state remote được đồng bộ và xác minh.

## 14. Checklist bảo mật Terraform state trên GCS

- [ ] Bucket state được tạo trước khi Terraform khởi tạo backend.
- [ ] Bucket nằm trong project quản lý nền tảng và location đáp ứng data residency.
- [ ] UBLA bật, PAP enforced và bucket không có public principal.
- [ ] Object Versioning bật và lifecycle noncurrent versions phù hợp chính sách.
- [ ] Không có retention policy/lock cản trở ghi state nếu chưa được kiểm thử.
- [ ] Terraform runtime dùng service account riêng, chỉ có `roles/storage.objectAdmin` trên bucket cần thiết.
- [ ] Nhóm người dùng được quyền impersonate service account có phạm vi hẹp.
- [ ] CI sử dụng credential ngắn hạn/WIF; không lưu service account JSON key trong repository.
- [ ] Backend config không chứa secret hoặc token có thể bị ghi vào `.terraform`/plan file.
- [ ] Backend prefix tách biệt giữa root module và stack.
- [ ] Production và non-production có bucket/project/IAM tách biệt khi cần ranh giới bảo mật.
- [ ] State và plan file được coi là dữ liệu nhạy cảm; không commit vào Git hoặc chia sẻ qua kênh không bảo vệ.
- [ ] Nếu dùng CMEK, GCS service agent có quyền Encrypter/Decrypter và key có kế hoạch vòng đời rõ ràng.
- [ ] State locking được giữ mặc định; quy trình force-unlock chỉ dành cho lock stale đã xác minh.
- [ ] Audit logs và cảnh báo thay đổi IAM/object được cấu hình theo yêu cầu.
- [ ] Quy trình restore từ object version cũ và migration backend đã được diễn tập.

## 15. Kết luận

Terraform state là dữ liệu cốt lõi để Terraform ánh xạ cấu hình với tài nguyên Google Cloud. GCS backend cung cấp nơi lưu từ xa, hỗ trợ locking và tích hợp IAM, Object Versioning cùng Cloud KMS. Một thiết kế an toàn bắt đầu bằng bucket riêng đã được bootstrap, bật UBLA/PAP/versioning, cấp quyền Object Admin ở đúng bucket cho runtime identity và dùng xác thực ngắn hạn hoặc service account impersonation.

State chứa thông tin hạ tầng và có thể chứa secret. Vì vậy, quyền đọc state phải được kiểm soát như quyền đọc dữ liệu nhạy cảm. Workspace chỉ giúp tách state logic; bucket, project và IAM mới là những thành phần cần dùng để tạo ranh giới truy cập. Kết hợp locking, versioning, audit log, quy trình backup/restore và phân tách stack sẽ giúp các nhóm triển khai Terraform trên Compute Engine, GKE, Cloud Run, storage và database an toàn, có thể cộng tác và khôi phục khi có sự cố.

## Tài liệu tham khảo

- [Terraform GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs)
- [Terraform state](https://developer.hashicorp.com/terraform/language/state)
- [Terraform state locking](https://developer.hashicorp.com/terraform/language/state/locking)
- [Terraform remote state](https://developer.hashicorp.com/terraform/language/state/remote)
- [Terraform workspaces](https://developer.hashicorp.com/terraform/language/state/workspaces)
- [Manage sensitive data in Terraform](https://developer.hashicorp.com/terraform/language/manage-sensitive-data)
- [Terraform backend configuration](https://developer.hashicorp.com/terraform/language/backend)
- [Cloud Storage uniform bucket-level access](https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access)
- [Use uniform bucket-level access](https://docs.cloud.google.com/storage/docs/using-uniform-bucket-level-access)
- [Cloud Storage public access prevention](https://docs.cloud.google.com/storage/docs/public-access-prevention)
- [Cloud Storage Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Cloud Storage IAM](https://docs.cloud.google.com/storage/docs/access-control/iam)
- [Cloud Storage customer-managed encryption keys](https://docs.cloud.google.com/storage/docs/encryption/customer-managed-keys)
- [Cloud Storage audit logging](https://docs.cloud.google.com/storage/docs/audit-logging)
- [gcloud storage buckets create](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/create)
- [gcloud storage buckets update](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/update)
