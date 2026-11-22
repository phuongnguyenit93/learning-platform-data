# Tổ chức project factory và quy trình cấp phát project

Một nhóm phát triển cần một Google Cloud project mới để thử nghiệm API trên Cloud Run. Nếu từng nhóm tự tạo project, bật API, cấp IAM và kết nối billing theo cách riêng, tổ chức sẽ nhanh chóng có những project không rõ chủ sở hữu, thiếu nhãn chi phí, quyền quá rộng và cấu hình mạng khó kiểm soát. Quy trình xin cấp project qua nhiều phòng ban cũng có thể kéo dài, khiến developer tìm cách đi đường vòng.

**Project factory** là quy trình và bộ công cụ **cấp phát project theo mẫu đã được phê duyệt**. Một yêu cầu hợp lệ đi qua các bước kiểm tra, phê duyệt, tự động tạo project, áp cấu hình nền tảng, kiểm chứng rồi bàn giao cho nhóm sử dụng. Khi triển khai đúng, project factory giúp tăng tốc onboarding đồng thời duy trì các kiểm soát quản trị tổ chức.

Bài thuộc chương **Quản trị tổ chức** của học phần **CLOUD_PROVIDERS_GCP**. Đây là cầu nối giữa resource hierarchy, IAM và VPC với những thao tác thực tế như tạo môi trường Compute Engine, GKE, Cloud Run, Cloud Storage hoặc cơ sở dữ liệu; đồng thời hỗ trợ tự động hóa phát hành, giám sát độ tin cậy và quản lý chi phí.

Sau bài học, bạn có thể:

- Mô tả đầu vào, đầu ra và các bước vận hành của một project factory.
- Xây dựng quy trình yêu cầu, đánh giá rủi ro, phê duyệt, cấp phát và bàn giao project.
- Chọn Folder, billing account, IAM, mạng, API và chính sách phù hợp với workload.
- Hiểu cách chuẩn hóa project bằng Terraform, CI/CD và policy as code.
- Thiết kế kiểm tra sau cấp phát, phát hiện sai lệch cấu hình và quy trình thu hồi project.
- Đánh giá khi nào cần cấp project riêng và khi nào có thể dùng project hiện hữu.

## 1. Project factory là gì, và không phải là gì?

**Google Cloud project** là đơn vị chứa phần lớn tài nguyên dịch vụ, có Project ID, Project number, IAM policy, API, quota và liên kết billing. Nó nằm trong cây **Organization → Folder → Project**. Một project chỉ có một parent tại một thời điểm; một số quyền và chính sách từ parent có thể được kế thừa xuống project và tài nguyên con.

Một **project factory** thường bao gồm:

| Thành phần | Trách nhiệm | Đầu ra |
|---|---|---|
| **Cổng yêu cầu** | Nhận mục đích, team sở hữu, môi trường, phân loại dữ liệu, ngân sách và nhu cầu mạng | Bản yêu cầu có cấu trúc |
| **Bộ kiểm tra** | Xác minh trường bắt buộc, quy tắc đặt tên, Folder/billing, quyền, giới hạn quota và chính sách | Báo cáo hợp lệ hoặc lý do từ chối |
| **Luồng phê duyệt** | Xác định bên có thẩm quyền chấp nhận rủi ro, chi phí và quyền truy cập | Quyết định có thể truy vết |
| **Bộ cấp phát** | Tạo project và áp cấu hình nền bằng API/Terraform | Project và tài nguyên nền tảng |
| **Hậu kiểm** | Đọc lại IAM, billing, API, logging, mạng, labels, policy, quota | Kết quả kiểm tra và bằng chứng |
| **Danh mục dự án** | Ghi lại chủ sở hữu, mục đích, tình trạng, ngày rà soát và cấu hình | Danh sách project có thể quản lý |
| **Quy trình vòng đời** | Sửa yêu cầu, thay đổi owner, rà soát định kỳ, ngừng sử dụng và xóa | Project được quản lý đến khi kết thúc |

Project factory **không phải một sản phẩm Google Cloud độc lập bắt buộc phải bật**. Doanh nghiệp có thể tự xây dựng bằng Terraform và pipeline, dùng các module của Cloud Foundation Toolkit/Cloud Foundation Fabric hoặc lấy Enterprise foundations blueprint làm kiến trúc tham khảo. Cách thực hiện khác nhau, nhưng mục tiêu là **cùng đầu vào và cùng chính sách thì tạo được project có nền tảng nhất quán**.

## 2. Thiết kế nền tảng trước khi tự động tạo project

Không thể có project factory đáng tin cậy nếu tổ chức chưa thống nhất hệ phân cấp, IAM, billing và kết nối mạng. Cần định nghĩa các quyết định ở **landing zone/cloud foundation** trước.

### Resource hierarchy mẫu

~~~text
Organization: example.com
├── Folder: production
│   ├── Project: shop-orders-prod-01
│   └── Project: shop-catalog-prod-01
├── Folder: nonproduction
│   ├── Folder: development
│   │   ├── Project: shop-orders-dev-01
│   │   └── Project: shop-catalog-dev-01
│   └── Folder: staging
│       └── Project: shop-orders-stg-01
└── Folder: shared-services
    ├── Project: org-project-factory
    ├── Project: org-network-prod
    ├── Project: org-network-nonprod
    ├── Project: org-cicd
    └── Project: org-security-logs
~~~

Đây là sơ đồ **minh họa**; các Project ID phải được kiểm tra tính duy nhất toàn cục trước khi tạo. Tổ chức không nhất thiết cần Folder cho từng team. Chỉ nên phân cấp Folder khi cần áp IAM/Organization Policy chung, quy định môi trường hoặc phân công quản trị rõ ràng.

**Tách biệt trách nhiệm:** project factory quản lý việc cấp phát và cấu hình nền. Nhóm platform quản trị mạng, nhóm bảo mật ban hành guardrail, nhóm tài chính quản lý billing, nhóm ứng dụng sở hữu workload. Quyền tạo project không đồng nghĩa quyền được bỏ qua các chính sách của tổ chức.

### Các quyết định cần chuẩn hóa

| Quyết định | Ví dụ quy tắc | Lý do |
|---|---|---|
| **Ranh giới project** | Production tách khỏi nonproduction; workload nhạy cảm có project riêng | Hạn chế phạm vi lỗi và quyền |
| **Parent Folder** | `production` cho production, `development` cho dev | Kế thừa đúng IAM và Organization Policy |
| **Billing account** | Theo đơn vị kinh doanh hoặc mô hình hạch toán được phê duyệt | Quản lý chi phí và trách nhiệm thanh toán |
| **Đặt tên** | `<org>-<workload>-<env>-<suffix>` | Dễ nhận diện và tra cứu |
| **Owner** | Một nhóm chịu trách nhiệm vận hành và chi phí, có owner dự phòng | Không để project “mồ côi” |
| **Labels/Tags** | `team`, `environment`, `cost_center`, `data_class` | Lọc tài nguyên, phân tích chi phí, hỗ trợ chính sách |
| **IAM** | Quyền tối thiểu, cấp theo Google Group và danh tính workload | Giảm quyền truy cập ngoài phạm vi |
| **Network** | VPC riêng hoặc Shared VPC theo môi trường | Có đường kết nối nhất quán và an toàn |
| **APIs** | Chỉ bật những API thuộc gói workload cần thiết | Giảm phạm vi vận hành và bề mặt cấu hình |
| **Operations** | Logging, Monitoring, alerting, audit, budget | Giúp phát hiện sự cố và theo dõi chi phí |
| **Vòng đời** | Ngày rà soát/expiration cho sandbox, quy trình ngừng project | Tránh tài nguyên không còn mục đích |

**Labels** chỉ là metadata; không được hiểu là ranh giới IAM. Nếu chính sách cần dùng **Resource Manager tags**, project factory phải tạo hoặc gắn tag đúng cơ chế, có xét kế thừa và quyền quản lý tag.

## 3. Xác định khi nào cần project mới

Không phải yêu cầu triển khai dịch vụ nào cũng cần project riêng. Dùng câu hỏi sau:

1. Workload có môi trường **production** hoặc dữ liệu nhạy cảm cần tách khỏi dev/staging không?
2. Nhóm sở hữu có yêu cầu IAM, mạng, quota, chi phí hay vòng đời độc lập không?
3. Có chính sách tổ chức, vị trí dữ liệu hoặc yêu cầu kiểm toán khác với workload hiện có không?
4. Các dịch vụ có được phát hành, khôi phục và giám sát độc lập không?
5. Nếu dùng chung project, một thao tác sai hoặc hết quota ở workload A có làm ảnh hưởng đáng kể workload B không?

| Tình huống | Gợi ý |
|---|---|
| Một microservice nhỏ, cùng team, chính sách và vòng đời với dịch vụ hiện tại | Cân nhắc giữ trong project hiện hữu |
| API production xử lý thanh toán và sandbox thử nghiệm | Tách project |
| Nhóm analytics có dữ liệu/region và quyền kiểm toán riêng | Cân nhắc project riêng |
| Các workload cần chung VPC | Có thể đặt project riêng, dùng Shared VPC nếu phù hợp |
| Ứng dụng chạy nhiều region | Không mặc định cần project riêng cho từng region |

Project là ranh giới **quản trị** hữu ích, nhưng không tự cô lập tuyệt đối. IAM kế thừa từ Organization/Folder và quyền truy cập xuyên project vẫn tồn tại; project factory phải đặt cả quy tắc IAM, dữ liệu và mạng phù hợp.

## 4. Thiết kế biểu mẫu yêu cầu có thể máy kiểm tra

Một form tự do khiến bộ phận xét duyệt phải hỏi lại nhiều lần. Thay vào đó, chuẩn hóa bản khai theo các trường đã thống nhất.

~~~yaml
# Ví dụ manifest NỘI BỘ cho project factory, không phải schema API Google Cloud.
request_id: PRJ-2026-0042
workload: orders-api
environment: dev
owner_group: orders-team@example.com
technical_contact: orders-techlead@example.com
cost_center: commerce
billing_profile: engineering-nonprod
data_classification: internal
parent_profile: development
network_profile: shared-nonprod
requested_services:
  - run.googleapis.com
  - artifactregistry.googleapis.com
  - secretmanager.googleapis.com
region_preference: asia-southeast1
monthly_budget_usd: 250
review_date: 2027-02-28
business_reason: "Thử nghiệm phát hành API đơn hàng trên Cloud Run"
~~~

Bộ cấp phát phải ánh xạ **profile** sang Folder ID, Billing account ID và cấu hình mạng đã được phê duyệt. Không nên tin một giá trị Folder ID hoặc billing account do người yêu cầu tự nhập khi nó chưa qua kiểm tra quyền và chính sách.

### Kiểm tra dữ liệu trước khi phê duyệt

- **Trường bắt buộc:** workload, environment, owner group, cost center, data classification, thời điểm rà soát.
- **Tính hợp lệ:** tên, độ dài, các giá trị enum, định dạng email/nhóm, request ID và project ID dự kiến.
- **Tính duy nhất:** request không bị gửi lặp; Project ID chưa được sử dụng.
- **Ràng buộc quản trị:** production phải nằm đúng Folder; profile mạng và billing phải thuộc danh sách cho phép.
- **Phân loại dữ liệu:** yêu cầu dữ liệu cá nhân, nhạy cảm hoặc hạn chế vị trí triển khai cần chính sách tương ứng.
- **Quy mô và ngân sách:** VM type, số node GKE, Cloud Run concurrency hoặc dịch vụ yêu cầu quota lớn cần được khai báo khi cần thiết.
- **Danh tính và vận hành:** Google Group owner còn hoạt động và có người chịu trách nhiệm sự cố.

Project ID Google Cloud là định danh **duy nhất toàn cục, không thể thay đổi** sau khi tạo. Theo quy định hiện hành, thường dài 6–30 ký tự, sử dụng chữ thường, số và dấu gạch nối, bắt đầu bằng chữ cái, không kết thúc bằng gạch nối và không dùng chuỗi bị cấm; ID đã sử dụng, kể cả project bị xóa, không thể dùng lại. Vì thế quy trình phải **duyệt trước tên cuối cùng**, tránh chứa thông tin bí mật trong Project ID hoặc Project name.

## 5. Luồng cấp phát từ yêu cầu đến bàn giao

~~~mermaid
flowchart TD
    A["Nhóm gửi yêu cầu"] --> B["Kiểm tra schema, ID, profile, quota"]
    B --> C{"Hợp lệ?"}
    C -- "Không" --> R["Trả lý do, yêu cầu chỉnh sửa"]
    R --> A
    C -- "Có" --> D{"Đúng ma trận phê duyệt?"}
    D -- "Không" --> E["Từ chối / chuyển người có thẩm quyền"]
    D -- "Có" --> F["Review Terraform plan và policy"]
    F --> G["Pipeline cấp project / billing / API / IAM / mạng"]
    G --> H["Hậu kiểm và ghi nhận danh mục"]
    H --> I{"Đạt tiêu chí?"}
    I -- "Không" --> J["Khắc phục / khóa bàn giao"]
    J --> H
    I -- "Có" --> K["Bàn giao project, owner xác nhận"]
    K --> L["Rà soát định kỳ / thay đổi / thu hồi"]
~~~

Các trạng thái quản trị gợi ý:

| Trạng thái | Ý nghĩa | Bằng chứng cần có |
|---|---|---|
| `REQUESTED` | Yêu cầu đã được ghi nhận | Request ID và dữ liệu người gửi |
| `VALIDATED` | Trường và quy tắc đã kiểm tra | Báo cáo kiểm tra hợp lệ |
| `APPROVED` | Đúng người có thẩm quyền phê duyệt | Mã phê duyệt và nhận xét |
| `PROVISIONING` | Pipeline đang áp dụng cấu hình | Run ID, Terraform plan/apply log |
| `VERIFIED` | Kiểm tra kỹ thuật đạt | Biên bản hậu kiểm |
| `ACTIVE` | Bàn giao cho owner | Owner xác nhận, project ID/number |
| `CHANGE_REQUESTED` | Có yêu cầu thay đổi IAM, mạng hoặc billing | Pull request/change record |
| `RETIRING` | Đang xử lý ngừng hoạt động | Kế hoạch export dữ liệu và phụ thuộc |
| `RETIRED` | Đã hoàn tất giải phóng theo chính sách | Bằng chứng ngừng sử dụng và lưu trữ |

Quy trình nên **idempotent**: chạy lại với cùng request ID và cấu hình không tạo project trùng hay cấp quyền lặp vô kiểm soát. Nếu bước tạo project thành công nhưng bước bật API thất bại, bản ghi phải cho biết trạng thái dở dang để tiếp tục hoặc sửa lỗi an toàn, thay vì tạo một project khác.

### Ai phê duyệt điều gì?

| Tình huống | Owner sản phẩm | Platform | Security | Finance/FinOps |
|---|---|---|---|---|
| Dev project theo profile chuẩn | Chịu trách nhiệm mục đích | Xác nhận profile/kỹ thuật | Chính sách kiểm tra tự động | Ngân sách đã định mức |
| Production chứa dữ liệu nội bộ | Phê duyệt mục tiêu và trách nhiệm | Kiến trúc mạng, vận hành | Kiểm soát truy cập và dữ liệu | Billing và ngân sách |
| Workload nhạy cảm hoặc cần ngoại lệ policy | Chứng minh nhu cầu | Đánh giá khả thi | Phê duyệt ngoại lệ có thời hạn | Xác định rủi ro chi phí |
| Tăng quota hoặc thay đổi billing | Xác nhận nhu cầu | Đánh giá tải và ảnh hưởng | Xem lại nếu mở rộng rủi ro | Phê duyệt chi phí |

Đây là **ma trận tham khảo**. Tổ chức cần xác định rõ ai có quyền ra quyết định cuối cùng, SLA xử lý yêu cầu và ngưỡng tự động phê duyệt để tránh mọi sandbox đều phải chờ hội đồng.

## 6. Thứ tự bootstrap tài nguyên

Một pipeline project factory có thể chạy theo trình tự:

1. **Nhận bản manifest đã phê duyệt.** Khóa các thông số ảnh hưởng quản trị như parent Folder, billing, environment và network profile.
2. **Tạo project bằng Cloud Resource Manager.** Ghi lại Project ID và Project number; đợi operation tạo thành công.
3. **Liên kết Cloud Billing account.** Đảm bảo identity dùng pipeline có quyền liên kết tài khoản thanh toán được chọn.
4. **Thiết lập nhãn/tag và các guardrail.** Xác minh project nằm dưới Folder đúng để kế thừa IAM/Organization Policy; áp thêm policy tại project nếu cần.
5. **Thiết lập IAM nền.** Cấp quyền cần thiết cho nhóm owner, nhóm vận hành và danh tính CI/CD; tránh Owner/Editor cho toàn bộ nhóm.
6. **Bật API theo workload profile.** Ví dụ Cloud Run cần `run.googleapis.com`; các dịch vụ liên quan được bật khi cần.
7. **Kết nối mạng.** Gắn project vào mô hình Shared VPC/VPC đã được phép; cấu hình subnet và quyền sử dụng theo môi trường.
8. **Cấu hình quan sát và chi phí.** Logging/Monitoring, các sink/alert cần thiết, budget và metadata phân bổ chi phí.
9. **Chạy hậu kiểm.** Đọc lại các cấu hình quan trọng; kiểm tra truy cập bằng danh tính phù hợp và khả năng gọi dịch vụ nền.
10. **Bàn giao.** Đăng ký vào danh mục, thông báo Project ID, quyền truy cập, cách deploy, người hỗ trợ và lịch rà soát.

Không nhất thiết mọi project đều có VPC riêng, cluster riêng hay tài nguyên database ngay khi tạo. Factory có thể cấp một **baseline** rồi nhóm workload triển khai tài nguyên ứng dụng ở pipeline riêng.

**Lưu ý về API và service identity:** bật API có thể tạo các service agent/service account do Google quản lý. Một số API, IAM binding hoặc subnet cần được khởi tạo theo đúng thứ tự; hậu kiểm phải đợi những tài nguyên bất đồng bộ đã sẵn sàng trước khi kết luận lỗi.

## 7. Dùng Terraform làm động cơ của project factory

Terraform cho phép khai báo cấu hình bằng mã nguồn, tạo plan để review và phát hành qua pipeline. Có thể dùng **Cloud Foundation Toolkit** hoặc **Cloud Foundation Fabric** làm nền tảng thay vì tự viết toàn bộ module.

Ví dụ HCL sau là **bản tối giản cho một dev project**. Folder và Billing account đã được quản trị viên tạo trước; project ID cần hợp lệ và duy nhất:

~~~hcl
terraform {
  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }
}

variable "project_id" {
  type = string
}

variable "folder_id" {
  type = string
}

variable "billing_account_id" {
  type = string
}

variable "developer_group_email" {
  type = string
}

resource "google_project" "orders_dev" {
  name                = "Orders Dev"
  project_id          = var.project_id
  folder_id           = var.folder_id
  billing_account     = var.billing_account_id
  auto_create_network = false

  labels = {
    environment = "dev"
    team        = "orders"
    cost_center = "commerce"
    managed_by  = "terraform"
  }
}

resource "google_project_service" "required" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
  ])

  project            = google_project.orders_dev.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_project_iam_member" "developers_view" {
  project = google_project.orders_dev.project_id
  role    = "roles/viewer"
  member  = format("group:%s", var.developer_group_email)
}

output "created_project_id" {
  value = google_project.orders_dev.project_id
}
~~~

Đoạn này **không phải một project factory hoàn chỉnh**: nó chưa tạo ngân sách, Shared VPC attachment, các sink logging, alert, tag binding hay phân quyền deployment. `roles/viewer` chỉ để minh họa cách cấp quyền đọc; muốn build/deploy Cloud Run cần thêm quyền **đúng thao tác** và service account phù hợp.

Các lưu ý khi áp dụng thực:

- Pipeline identity cần có các quyền tạo project tại parent, liên kết billing, cập nhật IAM và bật API tương ứng. Không cấp quyền Organization Admin toàn diện chỉ vì tiện.
- Với IAM Terraform, `google_project_iam_member` quản lý một thành viên của một role. Ngược lại, `google_project_iam_binding` mang tính authoritative cho **cả role** và `google_project_iam_policy` cho **toàn bộ allow policy** tại resource. Chọn sai có thể ghi đè binding do nhóm khác hoặc Google quản lý.
- **Terraform state** có thể chứa dữ liệu nhạy cảm; đặt trong backend được kiểm soát, mã hóa, giới hạn IAM và tránh đưa state vào Git.
- Với production, thêm review bắt buộc, kiểm tra plan có thao tác `destroy`/`replace`, cơ chế bảo vệ xóa và quy trình khôi phục.
- Chỉ dùng phiên bản provider/module đã được kiểm tra, thực hiện `terraform fmt`, `terraform validate` và plan trước apply trong pipeline thực.

Một pipeline GitOps cơ bản:

~~~text
Yêu cầu được phê duyệt
→ Pull request thêm manifest project
→ Kiểm tra schema / policy-as-code / lint
→ terraform plan
→ Review owner + platform (+ security nếu cần)
→ Pipeline sử dụng danh tính riêng để terraform apply
→ Kiểm tra hậu cấp phát
→ Ghi project ID, number, owner, status vào registry
~~~

**Chống thay đổi ngoài quy trình:** theo dõi drift giữa cấu hình Terraform và hệ thống đang chạy; kiểm tra Audit Logs. Nếu cần sửa khẩn cấp qua Console, ghi change record và đưa thay đổi trở lại mã nguồn sau khi xử lý.

## 8. Cấp phát thủ công để hiểu API, rồi tự động hóa

Trong buổi học hoặc khi gỡ lỗi pipeline, có thể thử các lệnh `gcloud` sau **trong project thử nghiệm được cấp quyền**, với thông số giả định:

~~~bash
PROJECT_ID="shop-orders-dev-01"
FOLDER_ID="123456789012"
BILLING_ACCOUNT_ID="000000-000000-000000"

# Tạo project dưới Folder do tổ chức quản lý.
gcloud projects create "$PROJECT_ID" \
  --folder="$FOLDER_ID" \
  --name="Orders Dev"

# Liên kết billing đã được phê duyệt.
gcloud billing projects link "$PROJECT_ID" \
  --billing-account="$BILLING_ACCOUNT_ID"

# Bật các API cần thiết, theo đúng profile ứng dụng.
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  --project="$PROJECT_ID"

# Chỉ cấp quyền xem để thử nghiệm, không cấp Owner cho cả nhóm.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="group:orders-developers@example.com" \
  --role="roles/viewer"

# Đọc lại project và policy sau cấp phát.
gcloud projects describe "$PROJECT_ID"
gcloud projects get-iam-policy "$PROJECT_ID"
gcloud billing projects describe "$PROJECT_ID"
gcloud services list --enabled --project="$PROJECT_ID"
~~~

Đây là lệnh **minh họa**, không chạy trên bất kỳ project thật nào trong bài học. Chúng có thể tạo tài nguyên và chi phí nếu người học tự thực thi. Mã Project ID và Billing account chỉ là placeholder; cần quyền `resourcemanager.projects.create` trên parent và quyền billing tương ứng. Khi dùng automation service account, project phải được tạo dưới Organization/Folder được phép; không tạo project “no organization” bằng service account.

Trong hệ thống vận hành, thao tác CLI rời rạc nên được thay bằng module IaC có retry, kiểm tra trạng thái và ghi audit. Không nên chạy lặp lệnh tạo project với ID mới để “né” lỗi chưa biết nguyên nhân.

## 9. Phân quyền project factory: không trao quyền quá rộng

Có ít nhất **ba nhóm danh tính** cần tách:

| Danh tính | Công việc | Nguyên tắc IAM |
|---|---|---|
| **Requester/owner group** | Yêu cầu và vận hành workload sau bàn giao | Không cần quyền tạo project toàn Organization |
| **Factory pipeline identity** | Tạo project, liên kết billing, áp IAM/API/metadata nền | Quyền tạo trên Folder được chỉ định và các quyền bổ sung tối thiểu |
| **Application CI/CD identity** | Triển khai Cloud Run, GKE hoặc Compute Engine trong project đã cấp | Quyền theo workload và môi trường đích |

Đối với bước tạo project, vai trò `roles/resourcemanager.projectCreator` thường được cấp trên **parent** cho danh tính factory. Đối với billing, cần quyền sử dụng Billing account được duyệt (ví dụ `roles/billing.user` theo mô hình cấp quyền); những thao tác như cập nhật IAM, API, budget hoặc network cần quyền phù hợp ở tài nguyên liên quan. Hãy tính **quyền hiệu lực**, kể cả IAM được kế thừa, trước khi cấp thêm role.

Một số guardrail nên được chuẩn hóa:

- Không cấp rộng `roles/owner`, `roles/editor` cho toàn bộ developer của mọi project.
- Quyền deploy production nằm ở service account CI/CD, có phê duyệt phù hợp.
- Không dùng khóa service account dài hạn khi có thể dùng Workload Identity Federation hoặc cơ chế token ngắn hạn.
- IAM trên Shared VPC host khác IAM trên workload service project; chỉ kết nối khi network profile cho phép.
- Tránh project mặc định tạo VPC `default` nếu thiết kế yêu cầu mạng được kiểm soát.
- Phân biệt **Organization Policy** (ràng buộc hành vi) với **IAM** (quyền của principal).
- Không ghi secret, private key hoặc dữ liệu cá nhân trong request manifest, Terraform variables hay log pipeline.

### Kiểm soát chính sách vị trí và mạng

Project bản thân không gắn cố định một region. Khi một nhóm cần lưu dữ liệu trong khu vực cụ thể, factory phải ghi nhận profile dữ liệu, áp Organization Policy về địa điểm được phép khi phù hợp và để pipeline ứng dụng kiểm tra **location từng tài nguyên**: Cloud Run region, VM zone, bucket location, database region.

Với mô hình Shared VPC, project ứng dụng có thể là **service project**; host project sở hữu mạng/subnet. Việc kết nối phụ thuộc điều kiện của Shared VPC và quyền cả hai phía, không tự xảy ra chỉ vì hai project nằm cùng Folder.

## 10. Billing, quota và FinOps theo vòng đời

### Liên kết billing có kiểm soát

Một project chỉ có thể liên kết với **một Cloud Billing account tại một thời điểm**. Factory ánh xạ `cost_center`, môi trường và đơn vị kinh doanh đến tài khoản đã được Finance phê duyệt. Người nhận project không tự ý đổi Billing account nếu không có quy trình thay đổi.

Labels gợi ý:

~~~yaml
team: orders
environment: dev
service: orders-api
cost_center: commerce
managed_by: terraform
~~~

Ngoài labels, registry phải giữ metadata mà labels không phù hợp để lưu, như email owner, thời điểm phê duyệt, lý do cấp, ngày rà soát và liên kết ticket.

### Ngân sách không phải lúc nào cũng là giới hạn chi tiêu cứng

- **Alerts-only budgets** theo dõi chi phí thực tế hoặc dự báo, gửi cảnh báo theo ngưỡng; bản thân loại này **không tự chặn** mọi mức tiêu thụ khi vượt ngân sách.
- **Spend cap budgets** có thể được dùng đối với **một số dịch vụ đủ điều kiện và phạm vi áp dụng hạn chế**, ví dụ một project và một dịch vụ tương ứng. Chúng không phải giới hạn cứng tổng thể cho mọi dịch vụ trong project; việc thực thi có thể có độ trễ và phát sinh vượt ngưỡng.
- Với project gồm nhiều dịch vụ, cần kết hợp alert, quota, cấu hình autoscaling, giới hạn tài nguyên phù hợp và quy trình xử lý chi phí bất thường.
- Nếu cần phân tích đa chiều, có thể xuất dữ liệu Cloud Billing sang BigQuery và xây báo cáo theo project, label, service và SKU.

Tài liệu hiện hành về [Cloud Billing budgets](https://cloud.google.com/billing/docs/how-to/budgets) và [spend caps](https://cloud.google.com/billing/docs/how-to/budgets-spend-caps) mô tả rõ sự khác nhau; khi triển khai phải kiểm tra dịch vụ nào đang đủ điều kiện.

### Quota và project limit

Số project có thể tạo chịu **project quota/limit** theo điều kiện tài khoản và tổ chức. Những dự án đã yêu cầu xóa nhưng chưa xóa vĩnh viễn có thể còn tính vào hạn mức. Ngoài ra, mỗi API có quota riêng theo project, vùng hoặc cấp độ dịch vụ.

Nếu factory chạy nhiều yêu cầu đồng thời, cần:

1. Hạn chế tốc độ tạo theo quota Resource Manager.
2. Retry có backoff đối với lỗi tạm thời, nhưng không retry vô hạn với lỗi IAM hoặc policy.
3. Dùng request ID và Project ID cố định để tránh tạo trùng.
4. Phân biệt lỗi hết project quota với hết Compute Engine, GKE hay Cloud Run quota.
5. Đánh giá yêu cầu tăng quota trước khi tạo workload production cần nhiều tài nguyên.

## 11. Hậu kiểm: khi nào project được xem là bàn giao xong?

Tạo được Project ID chỉ là một phần của công việc. Một bản ghi `ACTIVE` phải có kết quả của các bài kiểm tra sau:

| Kiểm tra | Tiêu chí đạt | Cách xác minh |
|---|---|---|
| **Resource Manager** | Project tồn tại, đúng parent Folder, đúng trạng thái | `gcloud projects describe` hoặc API |
| **Billing** | Đã liên kết tài khoản được duyệt | Billing API/Console |
| **Labels/Tags** | Đúng môi trường, owner/team, cost center; tag policy khi cần | Đọc lại metadata và tag bindings |
| **IAM** | Các nhóm/danh tính cần thiết có quyền tối thiểu, không có role ngoài profile | IAM policy, Policy Troubleshooter khi cần |
| **Organization Policy** | Không vi phạm guardrail; policy kế thừa đúng nhánh | Org Policy API/Console |
| **API** | Chỉ các dịch vụ cần thiết được bật và sẵn sàng | Service Usage API |
| **Network** | Đúng VPC/subnet hoặc Shared VPC service project; đường egress phù hợp | Kiểm tra cấu hình network và thử kết nối có kiểm soát |
| **Operations** | Logging, Monitoring, alerting/sink theo mức yêu cầu | Đọc lại cấu hình và thử phát sinh sự kiện mẫu |
| **Cost** | Budget/alerts hoặc spend cap đủ điều kiện đã thiết lập | Cloud Billing Console/API |
| **Registry** | Owner, deadline, project number, plan/apply run ID, ticket | Đọc danh mục project nội bộ |

Với production, có thể thêm kiểm tra đánh giá bảo mật, đường khôi phục, yêu cầu lưu giữ log và dữ liệu, hoặc bằng chứng tuân thủ. Với sandbox, baseline tối giản hơn nhưng vẫn cần owner và cơ chế xóa.

**Bàn giao** phải nói rõ: Project ID và Project number, nơi tìm project trong Console, nhóm nào có quyền, cách yêu cầu thêm API/quota, pipeline deploy tương ứng, cách xem chi phí và kênh hỗ trợ vận hành. Đừng bàn giao một project mới tạo nhưng owner không thể truy cập hoặc không biết quy trình thay đổi.

## 12. Thay đổi, phát hiện drift và kết thúc vòng đời

Project factory tốt còn xử lý **điều gì xảy ra sau ngày tạo**.

### Yêu cầu thay đổi

Ví dụ team muốn chuyển từ Cloud Run sang GKE, tăng quota, dùng subnet mới hoặc mở thêm vùng lưu dữ liệu. Thay vì chỉnh tay rồi để cấu hình lệch IaC, yêu cầu thay đổi nên đi qua bản manifest/pull request, đánh giá tác động, plan và phê duyệt phù hợp.

Phân loại thay đổi:

| Thay đổi | Độ nhạy | Hướng xử lý |
|---|---|---|
| Cập nhật owner group, nhãn không nhạy cảm | Thấp | Validate và apply có kiểm soát |
| Bật một API mới | Trung bình, tùy API | Kiểm tra quota, service agent, chi phí và dữ liệu |
| Thay IAM production hoặc service account deploy | Cao | Review platform/security, kiểm tra quyền kế thừa |
| Chuyển Folder hoặc Billing account | Cao | Đánh giá IAM/Org Policy, mạng, billing và hạn mức |
| Xóa project hoặc tắt billing | Rất cao | Xác minh phụ thuộc, backup và phê duyệt theo chính sách |

**Drift** là khi cấu hình chạy thật khác so với mô tả trong IaC. Nguồn gây drift có thể là thao tác Console, API ngoài pipeline, cập nhật mặc định hoặc thay đổi do dịch vụ quản lý. Project factory nên có lịch `terraform plan` hoặc cơ chế phát hiện thay đổi định kỳ; khi có khác biệt thì review trước khi đồng bộ, tránh tự động xóa tài nguyên đang phục vụ production.

### Quy trình thu hồi project

Đến ngày kết thúc sandbox hoặc khi workload ngừng hoạt động:

1. Xác nhận owner, người phê duyệt và các phụ thuộc còn dùng project.
2. Kiểm kê Cloud Storage, database, bí mật, service account, image và pipeline.
3. Xác định yêu cầu export/backup, thời gian lưu giữ dữ liệu và log.
4. Dừng workload an toàn; gỡ quyền hoặc kết nối không còn cần.
5. Lập kế hoạch xóa theo quy định nội bộ và xác nhận lần cuối.
6. Thực hiện xóa bằng quy trình được phê duyệt; theo dõi trạng thái và hạn khôi phục nếu có.
7. Cập nhật registry, chi phí và các hệ thống phụ thuộc.

Xóa project Google Cloud thường đưa nó vào giai đoạn **chờ xóa** trước khi bị xóa vĩnh viễn; thời gian khôi phục và điều kiện phụ thuộc cơ chế dịch vụ. Không coi thao tác xóa là cách backup hoặc một phương án rollback an toàn. Với production, bật cơ chế bảo vệ xóa trong IaC và quy trình kiểm tra phụ thuộc có thể giúp tránh sai sót.

## 13. Tình huống thực tế: mở rộng từ 3 lên 20 nhóm phát triển

Một công ty thương mại điện tử có 3 nhóm đầu tiên tự tạo project qua Console. Khi mở rộng lên 20 nhóm, có một số vấn đề:

- Nhiều project dev không có owner rõ, Billing account gắn không nhất quán.
- Nhóm hỗ trợ phải cấp IAM thủ công, một số người giữ quyền Editor sau khi đổi dự án.
- Project sản xuất và thử nghiệm bị trộn trong một Folder nên khó áp policy.
- Một số Cloud Run và database không được kết nối đúng log/alert; hóa đơn khó phân bổ.
- Developer đợi nhiều ngày để được tạo môi trường, dẫn tới các project ngoài quy trình.

Nhóm platform xây dựng **project factory** với ba profile:

| Profile | Nhu cầu | Cấu hình chuẩn |
|---|---|---|
| `sandbox` | Thử nghiệm có ngày kết thúc | Folder development, owner bắt buộc, budget alert, quyền giới hạn, tự rà soát |
| `nonprod-app` | Dev/staging thường xuyên | Folder theo môi trường, IAM nhóm, logging, CI/CD dev, mạng nonproduction |
| `production-app` | Phục vụ khách hàng | Folder production, review security/FinOps, IAM chặt, monitoring/alerts, audit, kết nối production được duyệt |

**Ví dụ yêu cầu của nhóm Orders:** tạo project dev để phát triển API Java trên Cloud Run và đọc dữ liệu thử nghiệm từ Cloud Storage. Người gửi chọn `nonprod-app`, owner là `orders-team`, cost center là `commerce`, region là khu vực đã được tổ chức phê duyệt và budget dự kiến 250 USD/tháng.

Factory kiểm tra thông tin, tạo plan, lấy phê duyệt phù hợp, sau đó tạo `shop-orders-dev-01` dưới Folder development, liên kết billing, bật Cloud Run/Artifact Registry/Cloud Storage API cần thiết, gán IAM cho nhóm và pipeline, cấu hình network/log/monitoring, đặt budget alert và bàn giao. CI/CD sau đó triển khai service Java vào project mới; project factory không phải tự triển khai toàn bộ ứng dụng.

**Khi nhóm lên production**, họ gửi yêu cầu profile `production-app`; factory cấp project mới dưới Folder production và áp chính sách nghiêm ngặt hơn. Production không phải chỉ là đổi label `environment=prod` trong cùng project dev.

### Đo lường hiệu quả của project factory

Các chỉ số hữu ích:

- **Thời gian từ REQUESTED đến ACTIVE**, phân tách chờ phê duyệt và thời gian pipeline.
- **Tỷ lệ yêu cầu thành công ngay lần đầu**, phân loại lỗi schema/IAM/quota/CI.
- **Tỷ lệ project có owner, labels và billing hợp lệ**.
- **Tỷ lệ dự án đạt hậu kiểm baseline** và thời gian xử lý sai lệch.
- **Số project hết hạn chưa thu hồi**, số project không phát sinh hoạt động và chi phí của chúng.
- **Số ngoại lệ chính sách đang mở và thời hạn xử lý**.

Mục tiêu là giảm thời gian cấp phát **trong khi vẫn có bằng chứng quản trị**. Chỉ tối ưu số project được tạo mỗi ngày mà bỏ qua owner, IAM và cleanup sẽ khiến chi phí/rủi ro tăng.

## 14. Checklist thiết kế project factory

- [ ] Cây Organization/Folder, project profiles, naming convention và owner model đã được thống nhất.
- [ ] Request schema có environment, owner, billing, phân loại dữ liệu, ngân sách và vòng đời.
- [ ] Có quy tắc quyết định dùng project mới hay tái sử dụng project đang có.
- [ ] Người phê duyệt, SLA, ngoại lệ và ngưỡng tự động hóa được định nghĩa.
- [ ] Pipeline identity chỉ có quyền tạo project và cấu hình nền trong phạm vi cần thiết.
- [ ] Terraform plan được kiểm tra trước apply, có state backend an toàn và kiểm soát thao tác destroy.
- [ ] Cấu hình IAM, Organization Policy, network, API, logging và billing đi theo từng profile.
- [ ] Factory có idempotency, retry hợp lý, theo dõi operation và xử lý trạng thái dở dang.
- [ ] Hậu kiểm xác nhận resource hierarchy, IAM, billing, API, network và theo dõi chi phí.
- [ ] Danh mục project lưu owner, thời điểm tạo, project ID/number, trạng thái và lịch rà soát.
- [ ] Có quy trình thay đổi, phát hiện drift, thu hồi sandbox và xóa project an toàn.

**Bài tập vận dụng:** Thiết kế project factory cho một doanh nghiệp có nhóm Payments, Catalog và Data. Mỗi nhóm cần dev, staging, production; Payments có dữ liệu nhạy cảm và Data cần giới hạn vị trí lưu trữ. Hãy (1) vẽ cây Folder/Project, (2) tạo ba profile cấu hình, (3) đề xuất schema yêu cầu tối thiểu, (4) mô tả ma trận phê duyệt, (5) phác thảo pipeline Terraform và các hậu kiểm, (6) đề xuất cách thu hồi sandbox sau 30 ngày, (7) xử lý tình huống pipeline tạo project thành công nhưng bật Cloud Run API thất bại. Giải thích cách giữ project factory hoạt động lại được sau lỗi mà không tạo project trùng.

## Tài liệu tham khảo chính thức

- [Create and manage projects — Cloud Resource Manager](https://cloud.google.com/resource-manager/docs/creating-managing-projects) — quyền tạo, Project ID, Folder và quota.
- [Manage projects and billing in your organization](https://cloud.google.com/resource-manager/docs/organization-resource-management) — tổ chức quyền quản trị và billing.
- [Enterprise foundations blueprint](https://cloud.google.com/architecture/blueprints/security-foundations) — kiến trúc nền tảng, GitOps/IaC, IAM, mạng và kiểm soát.
- [Landing zone design in Google Cloud](https://cloud.google.com/architecture/landing-zones) — các quyết định nền tảng khi xây môi trường doanh nghiệp.
- [Terraform blueprints and modules for Google Cloud](https://cloud.google.com/docs/terraform/blueprints/terraform-blueprints) — module project-factory và các module nền tảng.
- [Terraform best practices: Working with resources](https://cloud.google.com/docs/terraform/best-practices/working-with-resources) — lưu ý khi quản lý IAM bằng Terraform.
- [Terraform best practices: Operations](https://cloud.google.com/docs/terraform/best-practices/operations) — plan, review và pipeline.
- [Cloud Billing budgets](https://cloud.google.com/billing/docs/how-to/budgets) — cảnh báo ngân sách.
- [Spend cap budgets](https://cloud.google.com/billing/docs/how-to/budgets-spend-caps) — phạm vi dịch vụ hỗ trợ cơ chế giới hạn chi tiêu.
