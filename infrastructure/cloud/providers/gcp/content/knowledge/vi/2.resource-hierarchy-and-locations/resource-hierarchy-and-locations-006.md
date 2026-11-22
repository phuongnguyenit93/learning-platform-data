# Thiết kế project cho môi trường và nhóm phát triển

Trong Google Cloud, quyết định tạo bao nhiêu **project**, đặt chúng ở đâu trong cây tài nguyên và giao quyền cho ai ảnh hưởng trực tiếp đến khả năng triển khai, mức độ cô lập sự cố, quản trị chi phí và bảo mật. Một ứng dụng có thể chạy tốt khi mọi thứ nằm trong một project thử nghiệm, nhưng cách tổ chức đó thường trở nên khó kiểm soát khi có thêm nhóm phát triển, môi trường staging, dữ liệu sản xuất và quy trình phát hành.

Bài học thuộc phạm vi **CLOUD_PROVIDERS_GCP**, đặt nền tảng cho việc sử dụng IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu trong những bài tiếp theo. Mục tiêu là thiết kế cấu trúc project đủ rõ để các nhóm làm việc độc lập, vận hành an toàn và vẫn có thể dùng chung các năng lực hạ tầng cần thiết.

Sau bài học, bạn có thể:

- Phân biệt Organization, Folder, Project, tài nguyên dịch vụ và vị trí triển khai.
- Chọn ranh giới project theo môi trường, nhóm sở hữu và mức độ rủi ro.
- Đề xuất cấu trúc IAM, mạng, thanh toán và giám sát giữa nhiều project.
- Lập quy ước đặt tên, gắn nhãn và tự động hóa tạo project.
- Nhận diện những dấu hiệu cho thấy cấu trúc project cần được tách hoặc điều chỉnh.

## 1. Project là đơn vị quản trị quan trọng nhất của workload

Một project chứa tài nguyên như Cloud Run service, máy ảo Compute Engine, bucket Cloud Storage hay cơ sở dữ liệu. Mỗi project có các đặc điểm chính:

| Thành phần | Ý nghĩa khi thiết kế |
|---|---|
| **Project ID** | Định danh sử dụng trong API, CLI và nhiều tên tài nguyên; phải duy nhất trên toàn Google Cloud và không thể đổi sau khi tạo. |
| **Project number** | Định danh số do Google Cloud cấp, thường xuất hiện trong service agent và một số cấu hình quyền. |
| **Project name** | Tên hiển thị cho người dùng; có thể thay đổi mà không thay Project ID. |
| **IAM policy** | Điểm gán quyền cho nhóm, người dùng và service account; vẫn chịu ảnh hưởng từ quyền được kế thừa ở cấp cao hơn. |
| **API và quota** | API được bật theo project; nhiều quota được tính theo project, dịch vụ và đôi khi theo region hoặc zone. |
| **Billing** | Project được liên kết với một Cloud Billing account đang hoạt động để tính phí các tài nguyên có trả tiền. |
| **Vòng đời** | Project có thể bị vô hiệu hóa, xóa hoặc di chuyển trong cây tài nguyên; các thao tác này có phạm vi ảnh hưởng lớn. |

Project là một **ranh giới quản trị và phân tách tài nguyên hữu ích**, nhưng không phải bức tường an ninh tuyệt đối. IAM cấp Organization/Folder có thể được kế thừa; các service account vẫn có thể được cấp quyền truy cập xuyên project; Shared VPC có thể cho phép nhiều project dùng chung mạng. Vì vậy, cần thiết kế đồng thời project, IAM, network và chính sách tổ chức.

### Cây tài nguyên và quan hệ kế thừa

~~~text
Organization (doanh nghiệp)
└── Folder (nhóm quản trị hoặc môi trường)
    └── Folder (cấp phân nhóm tùy chọn)
        └── Project
            ├── Cloud Run service
            ├── Compute Engine VM
            └── Cloud Storage bucket
~~~

- **Organization** đại diện phạm vi quản trị cao nhất của doanh nghiệp khi doanh nghiệp có tài nguyên Organization.
- **Folder** nhóm các project theo cấu trúc quản trị; folder không chứa máy ảo hoặc database trực tiếp.
- **Project** là cha của nhiều loại tài nguyên dịch vụ và là phạm vi triển khai phổ biến.
- **IAM** có thể được gán ở nhiều cấp. Quyền cho một nhóm tại Folder thường được kế thừa xuống các project con; việc gán quyền ở project không tự xóa quyền đã kế thừa.
- **Organization Policy** giới hạn cách sử dụng dịch vụ hoặc tài nguyên, ví dụ hạn chế vị trí triển khai được phép. Nó có mục đích khác IAM: chính sách này giới hạn hành vi, còn IAM kiểm soát danh tính nào được thực hiện hành động.

Nếu tổ chức chưa có Organization, vẫn có thể tạo project, nhưng mô hình quản trị theo Folder và chính sách tập trung sẽ bị hạn chế. Với hệ thống doanh nghiệp, nên thiết lập Organization trước khi mở rộng thành nhiều workload sản xuất.

## 2. Chọn ranh giới project theo tiêu chí nào?

Ba yếu tố thường quyết định phương án tách project: **môi trường**, **chủ sở hữu** và **mức độ cô lập cần thiết**.

### Tách môi trường

Dev, staging và production có mục đích khác nhau:

| Môi trường | Mục đích | Nguyên tắc quản trị |
|---|---|---|
| **Dev** | Phát triển và thử nghiệm thường xuyên | Quyền linh hoạt hơn, tài nguyên có thể thay thế, có giới hạn chi phí. |
| **Staging/UAT** | Kiểm thử tích hợp, chấp nhận và quy trình phát hành | Cấu hình đủ gần production để phát hiện lỗi trước khi phát hành. |
| **Production** | Phục vụ người dùng hoặc dữ liệu thật | Quyền chặt chẽ, thay đổi có phê duyệt, logging và khôi phục sự cố đầy đủ. |

Đối với ứng dụng quan trọng, sử dụng **project riêng cho production** là lựa chọn mặc định hợp lý. Như vậy, một thao tác xóa tài nguyên, thay đổi IAM, bật API hoặc dùng hết quota trong dev ít có khả năng tác động trực tiếp đến production.

Tách project chỉ là một phần của giải pháp: phải tách thêm danh tính triển khai, secrets, dữ liệu và quyền truy cập. Không nên đưa dữ liệu nhạy cảm của production sang dev khi chưa có biện pháp ẩn danh hoặc kiểm soát phù hợp.

### Tách nhóm hoặc workload

Một nhóm có thể sở hữu nhiều dịch vụ, và một dịch vụ có thể có vòng đời hoàn toàn độc lập với dịch vụ khác. Dùng bảng sau để quyết định:

| Dấu hiệu | Hướng thiết kế phù hợp | Lý do |
|---|---|---|
| Hai workload có nhóm sở hữu, quyền hoặc mức rủi ro khác nhau | Project riêng theo workload, ít nhất ở production | Tách trách nhiệm và giảm phạm vi ảnh hưởng của sai sót. |
| Cùng nhóm, các thành phần nhỏ được phát hành cùng nhau và dùng chung chính sách | Có thể dùng chung project trong từng môi trường | Giảm số project và công việc quản trị. |
| Cần hạch toán chi phí hoặc quản lý quota độc lập | Cân nhắc project riêng | Dễ quan sát chi phí và sử dụng quota theo workload. |
| Hai ứng dụng cần liên lạc mạng với nhau | Không bắt buộc cùng project | Có thể dùng Shared VPC hoặc kết nối được kiểm soát. |
| Một ứng dụng chạy nhiều region | Không mặc nhiên cần nhiều project | Region/zone là thuộc tính vị trí của tài nguyên; chỉ tách project nếu có yêu cầu vận hành hay tuân thủ. |
| Dữ liệu hoặc yêu cầu tuân thủ khác biệt đáng kể | Ưu tiên project riêng và chính sách phù hợp | Dễ hạn chế danh tính truy cập, vị trí lưu trữ và phạm vi kiểm toán. |

Không có quy tắc “một microservice = một project” cho mọi hệ thống. Tạo quá ít project dễ gây chồng chéo quyền; tạo quá nhiều project khiến quy trình bootstrap, IAM, mạng và giám sát khó bảo trì. Chọn mức tách theo **ranh giới trách nhiệm và rủi ro thực tế**.

## 3. Ba mẫu tổ chức thường gặp

**Mẫu A — theo môi trường trước.** Folder production, staging, dev chứa các project ứng dụng tương ứng. Hữu ích khi yêu cầu kiểm soát production khác rõ rệt với các môi trường còn lại, và đội platform muốn áp dụng chính sách chung ở cấp Folder.

**Mẫu B — theo nhóm sản phẩm trước.** Folder payments, catalog, analytics; mỗi nhóm chứa các project dev, staging, prod. Hữu ích khi nhóm tự quản phần lớn vòng đời ứng dụng và có chính sách khác nhau theo domain.

**Mẫu C — kết hợp.** Dùng Folder cấp cao theo rủi ro/môi trường, sau đó phân nhóm theo team hoặc workload; dành các project riêng cho năng lực dùng chung như CI/CD, security logging, networking. Đây là điểm xuất phát thực tế cho nhiều doanh nghiệp có nhiều nhóm và môi trường.

Ví dụ doanh nghiệp có nhóm **Payments** và **Catalog**:

~~~text
Organization: example.com
├── Folder: production
│   ├── Project: acme-payments-prod
│   ├── Project: acme-catalog-prod
│   └── Project: acme-network-prod         (Shared VPC host)
├── Folder: nonproduction
│   ├── Folder: development
│   │   ├── Project: acme-payments-dev
│   │   └── Project: acme-catalog-dev
│   ├── Folder: staging
│   │   ├── Project: acme-payments-stg
│   │   └── Project: acme-catalog-stg
│   └── Project: acme-network-nonprod      (Shared VPC host)
└── Folder: shared-services
    ├── Project: acme-cicd
    └── Project: acme-security-logs
~~~

Các tên ở đây chỉ minh họa. Khi tạo thật, **Project ID phải duy nhất toàn cục**, vì vậy có thể cần thêm mã doanh nghiệp, sản phẩm hoặc hậu tố thích hợp. Không cần tạo Folder cho từng team nếu các Folder đó chưa phục vụ mục đích phân quyền hoặc áp chính sách cụ thể.

Với sơ đồ trên:

1. Thay đổi ở `acme-payments-dev` không đụng trực tiếp tài nguyên của `acme-payments-prod`.
2. Nhóm Payments có thể được cấp quyền phát triển trong project dev; quyền triển khai production thuộc danh tính pipeline với phạm vi tối thiểu.
3. Các project production kế thừa chính sách của Folder production.
4. Nhóm platform quản lý mạng dùng chung và giám sát; từng nhóm ứng dụng chịu trách nhiệm workload của mình.
5. Khi một nhóm có thêm workload mang rủi ro riêng, có thể thêm project độc lập mà không cần tổ chức lại mọi project hiện có.

## 4. Thiết kế quyền truy cập cùng lúc với project

Tạo project trước rồi cấp quyền tùy tiện thường dẫn đến môi trường development có thể tác động production. Hãy xác định **ai vận hành**, **ai triển khai**, **ai chỉ xem** ngay trong lúc vẽ cây tài nguyên.

| Danh tính hoặc nhóm | Dev | Staging | Production |
|---|---|---|---|
| Nhóm phát triển | Quyền phù hợp để xây dựng và thử nghiệm | Chủ yếu xem, một số thao tác kiểm thử | Xem thông tin vận hành cần thiết; không mặc định có quyền sửa |
| Pipeline CI/CD | Triển khai bằng danh tính riêng cho dev | Triển khai bằng danh tính riêng cho staging | Chỉ danh tính phát hành được phê duyệt mới triển khai |
| Nhóm platform/SRE | Quản trị nền tảng theo trách nhiệm | Quản trị nền tảng theo trách nhiệm | Quyền vận hành có kiểm soát và có thể kiểm toán |
| Nhóm bảo mật/kiểm toán | Truy cập phục vụ rà soát | Truy cập phục vụ rà soát | Quyền xem log và cấu hình cần thiết, tránh quyền thay đổi không cần thiết |

Các nguyên tắc:

- **Gán quyền cho nhóm** thay vì từng cá nhân khi có thể; quản lý thành viên nhóm theo quy trình nhân sự.
- **Quyền tối thiểu**: ưu tiên vai trò được định nghĩa sẵn phù hợp từng dịch vụ, cân nhắc custom role khi cần; tránh cấp rộng `Owner` hoặc `Editor` cho cả nhóm chỉ để thuận tiện.
- **Phạm vi nhỏ nhất hợp lý**: chỉ cấp ở Folder nếu cần áp dụng cho mọi project bên dưới; nếu chỉ một project cần quyền thì gán tại project hoặc tài nguyên tương ứng.
- **Tách danh tính người và workload**: dùng service account riêng cho ứng dụng hoặc pipeline; tránh chia sẻ một service account có quyền ở mọi môi trường.
- **Hạn chế khóa service account dài hạn**: ưu tiên cơ chế danh tính ngắn hạn, liên kết danh tính workload hoặc impersonation khi phù hợp.
- **Xem xét kế thừa trước khi mở rộng quyền**: một thành viên đã có quyền từ Organization hoặc Folder thì không cần cấp trùng lặp tại project.

Ví dụ, hệ thống CI/CD đặt tại `acme-cicd` vẫn có thể triển khai vào `acme-payments-prod` thông qua một danh tính chuyên dụng được cấp quyền cần thiết **trên project đích và các tài nguyên liên quan**. Bản thân việc CI/CD nằm ở project dùng chung không tự cấp cho nó quyền triển khai mọi nơi. Trong một số luồng triển khai còn cần quyền sử dụng service account chạy ứng dụng, vì vậy phải kiểm tra cả hai lớp quyền.

IAM và Organization Policy bổ sung cho nhau. Một người có IAM phù hợp vẫn không thể tạo tài nguyên vi phạm ràng buộc Organization Policy đang áp dụng. Khi di chuyển project sang Folder khác, hãy rà soát cả **quyền kế thừa lẫn chính sách được kế thừa**, vì hành vi của project có thể thay đổi.

## 5. Dùng chung hạ tầng nhưng giữ ranh giới trách nhiệm

### Mạng và Shared VPC

Mỗi project ứng dụng không nhất thiết phải sở hữu một VPC độc lập. Với **Shared VPC**, một **host project** quản lý VPC và subnet; những **service project** được liên kết có thể dùng subnet của host nếu được cấp quyền tương ứng.

~~~text
acme-network-prod (host project)
└── production-vpc
    ├── subnet-app (region A)
    └── subnet-data (region A)
         ↑                     ↑
acme-payments-prod       acme-catalog-prod
 (service project)        (service project)
~~~

Cách này giúp nhóm mạng quản lý dải địa chỉ, định tuyến và quy tắc firewall tập trung, còn nhóm ứng dụng triển khai workload trong project của mình. Các project tham gia Shared VPC phải đáp ứng yêu cầu của Google Cloud, trong đó host và service project thuộc cùng Organization. Chia sẻ VPC không thay thế việc phân quyền mạng: cần giới hạn ai được sử dụng subnet, quy tắc kết nối nào được phép và lưu lượng ra ngoài được kiểm soát thế nào.

Nếu production và nonproduction cần cách ly chặt, dùng host project hoặc VPC riêng cho từng phạm vi là lựa chọn dễ quản trị hơn. Đừng nối mạng xuyên môi trường chỉ vì các ứng dụng đang dùng chung mã nguồn.

### Dữ liệu, secrets và dịch vụ dùng chung

- **Dữ liệu production** nên ở project và tài nguyên chịu chính sách sản xuất. Truy cập xuyên project chỉ mở cho danh tính thực sự cần, với quyền tối thiểu.
- **Secrets** cần chia theo môi trường; không tái sử dụng cùng thông tin xác thực cho dev và prod.
- **Artifact Registry, build và CI/CD** có thể đặt tập trung, nhưng danh tính đọc artifact và triển khai vẫn được gán theo workload đích.
- **Cloud Logging và Cloud Monitoring** có thể thu thập hoặc hiển thị dữ liệu xuyên project theo cấu hình và quyền phù hợp; cân nhắc đưa bản sao log cần thiết về nơi lưu trữ tập trung phục vụ kiểm toán.
- **Cloud KMS**, backup và quản lý khóa mã hóa cần được thiết kế theo yêu cầu bảo mật và khôi phục; không mặc định rằng tài nguyên ở project khác thì không thể truy cập lẫn nhau.

## 6. Phân biệt ranh giới project với vị trí địa lý

Project là đối tượng quản trị ở phạm vi toàn cục; **project không có một region duy nhất**. Từng dịch vụ có phạm vi vị trí riêng:

| Loại tài nguyên | Ví dụ về phạm vi vị trí | Điều cần quyết định |
|---|---|---|
| Compute Engine VM | Zone | Chọn zone, khả năng mở rộng và phương án chịu lỗi. |
| Cloud Run service | Region | Chọn region gần người dùng và phù hợp phụ thuộc dữ liệu. |
| GKE cluster | Zonal hoặc regional tùy cấu hình | Chọn kiến trúc tính sẵn sàng và nơi đặt node/control plane. |
| Cloud Storage bucket | Region, dual-region hoặc multi-region theo cấu hình | Chọn nơi lưu dữ liệu theo độ trễ, độ bền và chính sách dữ liệu. |
| Cơ sở dữ liệu | Tùy dịch vụ, thường có lựa chọn region và cấu hình HA | Chọn nơi đặt dữ liệu, replica và cách khôi phục. |

Ví dụ, `acme-payments-prod` có thể chứa Cloud Run tại một region và bucket tại vị trí tương thích với yêu cầu lưu trữ. Nếu yêu cầu lưu dữ liệu chỉ trong một vùng địa lý được phép, cần kiểm tra vị trí thực tế của **từng dịch vụ**, đồng thời cấu hình Organization Policy khi phù hợp. Chỉ đặt tên project có chữ “asia” hoặc “eu” không tạo ra giới hạn vị trí.

Tách thành project riêng theo region chỉ khi điều đó mang lại lợi ích rõ ràng, chẳng hạn cần quyền quản trị, hạch toán, quota hoặc phạm vi sự cố độc lập. Với nhiều ứng dụng, một project production có tài nguyên ở nhiều region là hợp lý.

## 7. Quy ước đặt tên, nhãn và chi phí

Một quy ước đơn giản là:

~~~text
<tổ chức>-<workload>-<môi trường>[-<hậu tố>]
~~~

Ví dụ minh họa: `acme-payments-dev`, `acme-payments-stg`, `acme-payments-prod`. Trong hệ thống thực, tên cần tuân thủ quy tắc ký tự/độ dài của Google Cloud và đảm bảo tính duy nhất toàn cục của Project ID. Vì Project ID không đổi sau khi tạo, hãy duyệt tên trước khi cấp tài nguyên.

Nên gắn **labels** nhất quán để hỗ trợ tìm kiếm và phân tích chi phí, chẳng hạn:

~~~yaml
environment: prod
team: payments
service: checkout
cost_center: commerce
managed_by: terraform
~~~

Labels là metadata; chúng **không phải** cơ chế IAM. Khi cần điều kiện chính sách dựa trên tags, phải dùng cơ chế **Resource Manager tags** phù hợp thay vì cho rằng labels tự tạo ranh giới bảo mật.

Về chi phí, thiết kế nên bao gồm:

1. **Billing account**: liên kết từng project với tài khoản thanh toán thích hợp; một project chỉ liên kết một Billing account tại một thời điểm.
2. **Budgets và alerts**: đặt cảnh báo chi phí phù hợp cho production và nonproduction. Budget không tự động chặn tiêu thụ dịch vụ khi vượt ngưỡng.
3. **Billing export**: nếu cần phân tích chi tiết theo project, team, service hoặc thời gian, có thể xuất dữ liệu thanh toán sang BigQuery và xây dựng báo cáo.
4. **Quotas**: kiểm tra quota của dịch vụ tại đúng project, region/zone và cấp độ áp dụng trước khi triển khai tải lớn. Quota không phải công cụ thay thế ngân sách.
5. **Quyền sở hữu**: mỗi project cần người/nhóm chịu trách nhiệm phê duyệt chi phí, dọn tài nguyên và xử lý cảnh báo.

## 8. Tự động hóa việc tạo project bằng Infrastructure as Code

Khi số project tăng, tạo thủ công qua Console dễ gây sai lệch về quyền, nhãn, API và logging. Một quy trình “project factory” có thể chuẩn hóa các bước: chọn Folder → cấp Project ID → liên kết Billing → bật API cần thiết → gán IAM → cấu hình mạng, logs, chính sách và giám sát.

Ví dụ Terraform tối giản:

~~~hcl
resource "google_project" "payments_dev" {
  name            = "Payments Dev"
  project_id      = var.payments_dev_project_id
  folder_id       = var.dev_folder_id
  billing_account = var.billing_account_id

  labels = {
    environment = "dev"
    team        = "payments"
    service     = "checkout"
  }
}

resource "google_project_service" "cloud_run" {
  project            = google_project.payments_dev.project_id
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_iam_member" "developers_read" {
  project = google_project.payments_dev.project_id
  role    = "roles/viewer"
  member  = "group:payments-devs@example.com"
}
~~~

Đoạn mã minh họa cách liên kết cấu hình. Trước khi áp dụng cần có Folder, Billing account, Project ID hợp lệ và danh tính Terraform đủ quyền; cũng cần xét IAM cụ thể cho mỗi dịch vụ. `roles/viewer` trong ví dụ chỉ thể hiện quyền đọc ở project, **không phải quyền triển khai Cloud Run**. Thực tế còn cần cấu hình state, bảo vệ thao tác xóa, quy trình review và các module quản trị chung.

Quy trình triển khai đề xuất:

1. Người yêu cầu khai báo chủ sở hữu, workload, môi trường, phân loại dữ liệu, region dự kiến và ngân sách.
2. Pipeline kiểm tra quy tắc tên, nhãn, Folder và chính sách áp dụng.
3. Thay đổi Terraform được review; production yêu cầu phê duyệt rõ ràng theo quy trình tổ chức.
4. Project được tạo cùng IAM và API tối thiểu; dịch vụ được triển khai bởi danh tính riêng cho môi trường.
5. Hệ thống kiểm tra lại IAM, policy, networking, logging, nhãn và chi phí sau khi provisioning.

Với production, phân quyền tạo project và đổi Billing account cần được quản lý chặt vì chúng có thể mở rộng đáng kể phạm vi sử dụng tài nguyên và chi phí.

## 9. Tình huống thiết kế: hai nhóm phát hành độc lập

Một công ty thương mại điện tử có nhóm Payments và Catalog. Payments xử lý giao dịch nhạy cảm; Catalog thay đổi giao diện và dữ liệu sản phẩm thường xuyên. Cả hai muốn phát hành hàng ngày nhưng không được để lỗi dev ảnh hưởng production.

**Phương án phù hợp:** tách `payments-dev/stg/prod` và `catalog-dev/stg/prod` thành sáu project ứng dụng. Project production nằm dưới Folder production; quyền sửa trực tiếp bị hạn chế, danh tính triển khai tách theo ứng dụng. Hai ứng dụng có thể dùng Shared VPC production do nhóm platform vận hành, nhưng quyền kết nối và truy cập dữ liệu phải được phê duyệt. Logging và billing được tổng hợp tập trung, còn chi phí vẫn theo dõi ở từng project.

Nếu Catalog sau này có một hệ thống xử lý ảnh tốn quota lớn và có chu kỳ triển khai độc lập, có thể tách thành project riêng mà không phải tách toàn bộ hệ thống thương mại điện tử. Ngược lại, hai thành phần nhỏ của Payments có cùng nhóm vận hành, cùng nhu cầu bảo mật và phát hành cùng nhau có thể tiếp tục cùng project trong mỗi môi trường.

Phương án này cân bằng giữa cô lập sự cố, tự chủ của nhóm, chi phí vận hành và khả năng sử dụng hạ tầng chung. Tuy nhiên, muốn đạt được sự cô lập dự kiến thì **IAM, mạng, dữ liệu và pipeline phải thực thi đúng ranh giới đã thiết kế**.

## 10. Checklist để rà soát một thiết kế project

Trước khi tạo project hoặc chuyển một workload sang production, hãy kiểm tra:

- [ ] Mỗi project có mục đích, môi trường, chủ sở hữu và người chịu trách nhiệm chi phí rõ ràng.
- [ ] Production được phân tách hợp lý với dev và staging, bao gồm cả service account và secrets.
- [ ] Folder phản ánh nơi cần áp chính sách hoặc quyền chung; không tạo phân cấp chỉ để làm đẹp sơ đồ.
- [ ] Quyền được cấp theo nhóm và theo phạm vi tối thiểu; quyền kế thừa đã được rà soát.
- [ ] Các kết nối xuyên project và Shared VPC được mô tả, cấp quyền và kiểm soát.
- [ ] Vị trí triển khai được kiểm tra theo từng dịch vụ và yêu cầu lưu trữ dữ liệu.
- [ ] Có nhãn, budget alerts, logging, giám sát và kế hoạch theo dõi quota phù hợp.
- [ ] Tạo project, bật API, quản lý IAM và thay đổi cấu hình có thể lặp lại bằng code.
- [ ] Project ID và mọi lựa chọn khó thay đổi về sau đã được review trước khi tạo.

**Bài tập vận dụng:** Hãy thiết kế cây Folder/Project cho ba nhóm Web, Payments và Analytics, mỗi nhóm có dev và production. Payments cần kiểm soát quyền chặt hơn; Analytics cần region lưu dữ liệu được phê duyệt; nhóm platform sở hữu mạng dùng chung và CI/CD. Với từng project, chỉ ra owner, môi trường, Billing account, các nhóm IAM chính và nơi đặt dữ liệu. Sau đó giải thích trường hợp nào có thể dùng chung project, trường hợp nào cần tách, và cách thay đổi chính sách của Folder ảnh hưởng các project con.
