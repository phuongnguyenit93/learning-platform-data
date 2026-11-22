# Organization, folder, project và Resource Manager

Google Cloud có nhiều dịch vụ như Compute Engine, GKE, Cloud Run, Cloud Storage, Cloud SQL và VPC. Trước khi triển khai ứng dụng, cần xác định **ai sở hữu tài nguyên, tài nguyên thuộc môi trường nào, ai được phép thao tác và chính sách nào áp dụng**. Google Cloud giải quyết các câu hỏi này bằng hệ thống phân cấp tài nguyên và dịch vụ **Cloud Resource Manager**.

Bài học thuộc chương **Hệ thống tài nguyên và vị trí** của mô-đun CLOUD_PROVIDERS_GCP. Đây là nền tảng để tổ chức project, áp dụng IAM, quy hoạch VPC, triển khai workload, tự động hóa phát hành, theo dõi độ tin cậy và kiểm soát chi phí trong các phần tiếp theo.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của `Organization`, `Folder`, `Project` và tài nguyên dịch vụ trong Google Cloud.
2. Phân biệt phạm vi quản trị của resource hierarchy với tài khoản thanh toán, vùng địa lý và dịch vụ chạy ứng dụng.
3. Mô tả cách chính sách IAM và Organization Policy được áp dụng và kế thừa.
4. Dùng Console hoặc `gcloud` để khám phá cấu trúc và tạo folder/project với quyền phù hợp.
5. Đề xuất cấu trúc thực tế cho nhóm phát triển có môi trường dev, staging, production và nhu cầu quản trị tập trung.

## 1. Resource hierarchy là gì?

**Resource hierarchy** là cấu trúc cha–con dùng để quản lý tài nguyên của Google Cloud. Trong tổ chức doanh nghiệp, thứ tự thường là:

~~~mermaid
flowchart TD
    O["Organization<br/>organizations/123456789012"]
    FP["Folder: Production<br/>folders/234567890123"]
    FN["Folder: Nonproduction<br/>folders/345678901234"]
    FC["Folder: Commerce<br/>folders/456789012345"]
    PP["Project: shop-prod<br/>shop-prod-example-2026"]
    PD["Project: shop-dev<br/>shop-dev-example-2026"]
    VM["Compute Engine VM"]
    RUN["Cloud Run service"]
    DB["Cloud SQL instance"]
    O --> FP
    O --> FN
    FP --> FC
    FC --> PP
    FN --> PD
    PP --> VM
    PP --> RUN
    PP --> DB
~~~

**Lưu ý:** Tên và mã định danh trong sơ đồ chỉ là ví dụ. Một organization có thể chứa project trực tiếp; folder là tùy chọn. Folder có thể chứa các folder lồng nhau và project. Project chứa tài nguyên của những dịch vụ như Compute Engine, Cloud Run, GKE và Cloud Storage.

Các quy tắc nền tảng:

- **Mỗi đối tượng có đúng một cha trực tiếp** trong hierarchy, ngoại trừ nút gốc. Ví dụ, một project không thể đồng thời nằm dưới hai folder.
- **Chính sách có thể kế thừa từ trên xuống.** Quyền truy cập được cấp tại organization hoặc folder có thể áp dụng cho những tài nguyên bên dưới.
- **Project là đơn vị làm việc trung tâm.** Đa số dịch vụ Google Cloud cần project để bật API, tạo tài nguyên và xác định phạm vi quản lý.
- **Không phải tài khoản nào cũng có organization.** Khi sử dụng Google Cloud với tài khoản cá nhân, project có thể nằm ở đỉnh hierarchy. Muốn dùng folder cần có organization.
- **Hierarchy không phải topology mạng hoặc địa lý.** Folder `Production` không có nghĩa mọi VM nằm cùng region, và các project cùng folder không tự động kết nối mạng với nhau.

Có thể hình dung hierarchy giống hệ thống thư mục của doanh nghiệp: organization là công ty, folder là bộ phận hoặc nhóm môi trường, project là nơi triển khai một workload hay tập hợp dịch vụ có cùng chủ sở hữu.

## 2. Organization: cấp quản trị toàn doanh nghiệp

**Organization** đại diện cho doanh nghiệp hoặc đơn vị sở hữu tài nguyên Google Cloud. Nó là nút gốc của hierarchy có tổ chức và được liên kết với **Google Workspace** hoặc **Cloud Identity**. Organization có mã tài nguyên như `organizations/123456789012`.

Vai trò điển hình của organization:

- Xác lập quyền sở hữu tập trung: project thuộc phạm vi doanh nghiệp thay vì chỉ phụ thuộc vào người tạo.
- Cấp quyền cho những nhóm quản trị chung như an ninh, kiểm toán và vận hành.
- Áp dụng các quy tắc quản trị chung bằng Organization Policy.
- Tạo điểm bắt đầu để chia folder theo đơn vị kinh doanh, nhóm kỹ thuật hoặc môi trường.

Ví dụ, doanh nghiệp Atlas có các nhóm **Security**, **Platform** và **Commerce**. Nhóm Security có thể được cấp quyền kiểm tra phù hợp ở cấp organization; nhóm Commerce nhận các quyền triển khai hẹp hơn tại folder của mình.

### Organization không đồng nghĩa với billing account

Một **Cloud Billing account** chịu trách nhiệm thanh toán, được liên kết với những project đủ điều kiện sử dụng dịch vụ tính phí. Billing account **không phải folder** và **không nằm trong cây Organization → Folder → Project**. Một organization có thể có nhiều billing account; nhiều project có thể cùng liên kết đến một billing account nếu cấu hình và quyền cho phép.

Vì thế:

- **Hierarchy** trả lời: tài nguyên do ai sở hữu, nằm trong phạm vi quản trị nào?
- **IAM/Organization Policy** trả lời: ai được làm gì và những quy tắc nào ràng buộc tài nguyên?
- **Cloud Billing** trả lời: chi phí của project được ghi nhận, theo dõi và thanh toán qua đâu?
- **Region/zone** trả lời: tài nguyên được đặt hoặc phục vụ ở vị trí hạ tầng nào?

Bốn mối quan tâm này liên quan nhau nhưng cần cấu hình riêng.

## 3. Folder: nhóm project để áp dụng chính sách và phân quyền

**Folder** là lớp tổ chức tùy chọn nằm dưới organization hoặc một folder khác, với định danh như `folders/234567890123`. Folder không chạy container, VM hay database; nó nhóm các project và các folder con để quản lý.

Ví dụ một doanh nghiệp có thể chọn:

~~~text
Organization: atlas.example
├── Production
│   ├── Commerce
│   │   ├── Project: atlas-shop-prod
│   │   └── Project: atlas-payment-prod
│   └── Analytics
│       └── Project: atlas-analytics-prod
├── Nonproduction
│   └── Commerce
│       ├── Project: atlas-shop-dev
│       └── Project: atlas-shop-staging
└── Platform
    └── Project: atlas-network-hub
~~~

Cấu trúc này có ba lợi ích:

1. **Quản trị theo môi trường:** các project production cùng nhận bộ quy tắc production từ folder `Production`.
2. **Ủy quyền cho nhóm:** quản trị viên Commerce có thể được cấp quyền trong folder Commerce mà không cần quyền trên toàn organization.
3. **Mở rộng hợp lý:** tạo project mới dưới folder thích hợp để thừa hưởng các chính sách đã có.

Folder không phải ranh giới cô lập tuyệt đối. Nếu một người được cấp quyền rộng tại organization, quyền đó vẫn có thể được kế thừa xuống folder Commerce. Việc tạo folder mới **không tự xóa** những quyền kế thừa từ cấp trên.

**Khi nào nên dùng folder?** Khi có nhiều project cùng chính sách, nhóm chủ sở hữu hoặc nhu cầu phân quyền. Với một project thử nghiệm nhỏ, thêm nhiều tầng folder có thể chỉ tạo độ phức tạp không cần thiết.

## 4. Project: đơn vị triển khai, phân quyền và quản lý dịch vụ

**Project** là nơi tạo và quản lý phần lớn tài nguyên Google Cloud: VM, dịch vụ Cloud Run, cụm GKE, bucket, database, cấu hình VPC và nhiều tài nguyên khác. Nó cũng là phạm vi thường dùng để bật API, cấp quyền IAM, theo dõi quota và hạch toán mức sử dụng.

Một project có ba thuộc tính dễ nhầm:

| Thuộc tính | Ví dụ minh họa | Ý nghĩa |
| --- | --- | --- |
| **Project ID** | `atlas-shop-prod-2026` | Mã do người tạo lựa chọn; phải duy nhất toàn cục và không đổi sau khi tạo. Dùng thường xuyên trong CLI/API. |
| **Project number** | `701234567890` | Số Google Cloud tự cấp, không thay đổi; một số API và tài khoản dịch vụ sử dụng. |
| **Project name** | `Atlas Shop - Production` | Tên hiển thị có thể sửa, không dùng làm khóa định danh ổn định. |

Project còn có trạng thái vòng đời, thuộc tính parent và các label. Ví dụ:

~~~json
{
  "projectId": "atlas-shop-prod-2026",
  "projectNumber": "701234567890",
  "name": "Atlas Shop - Production",
  "parent": {
    "type": "folder",
    "id": "456789012345"
  },
  "labels": {
    "environment": "production",
    "team": "commerce"
  },
  "lifecycleState": "ACTIVE"
}
~~~

Đây là **ví dụ minh họa cấu trúc dữ liệu**, không phải phản hồi thực tế từ tài khoản Google Cloud.

### Vì sao cần tách project?

Hãy xét ứng dụng bán hàng có Cloud Run, Cloud SQL và Cloud Storage. Nếu dev và production chung project:

- Quyền triển khai và vận hành khó phân tách hơn.
- Khó quản lý quota, API, ngân sách và chi phí theo từng môi trường.
- Nguy cơ thao tác nhầm tài nguyên production tăng.

Tách `atlas-shop-dev`, `atlas-shop-staging` và `atlas-shop-prod` giúp cô lập phạm vi quản lý, phân quyền, ngân sách và tài nguyên. Tuy vậy, **tách project không đồng nghĩa tách mạng hoàn toàn**: kết nối xuyên project vẫn có thể được thiết lập bằng các tính năng mạng phù hợp, ví dụ Shared VPC, và phải cấu hình quyền cũng như kết nối một cách tường minh.

Một project có thể đổi parent bằng thao tác di chuyển hợp lệ, nhưng việc di chuyển làm thay đổi phạm vi chính sách được kế thừa. Không nên coi đây chỉ là thao tác sắp xếp thư mục.

## 5. Cloud Resource Manager quản lý những gì?

**Cloud Resource Manager** cung cấp giao diện quản lý hierarchy, gồm Console, Google Cloud CLI và Cloud Resource Manager API. Nó được dùng để:

- Tìm, tạo, liệt kê, mô tả, cập nhật và quản lý vòng đời project/folder theo quyền được cấp.
- Khám phá quan hệ parent giữa organization, folder và project.
- Thao tác chính sách IAM đối với những đối tượng hierarchy tương ứng.
- Hỗ trợ dịch chuyển project/folder khi điều kiện và quyền phù hợp.

Resource Manager không thay thế mọi dịch vụ quản trị khác:

| Công việc | Dịch vụ/cơ chế phù hợp |
| --- | --- |
| Quản lý organization, folder, project và quan hệ cha–con | **Cloud Resource Manager** |
| Cấp vai trò cho principal | **IAM** cùng chính sách truy cập của tài nguyên |
| Áp đặt ràng buộc quản trị | **Organization Policy Service** |
| Bật API cho project | **Service Usage** |
| Liên kết project với tài khoản thanh toán, theo dõi chi phí | **Cloud Billing** |
| Tìm kiếm, kiểm kê nhiều loại tài nguyên cloud | **Cloud Asset Inventory** |
| Chọn vị trí chạy VM, cluster hoặc lưu dữ liệu | Cấu hình **region/zone/location** theo từng dịch vụ |

Ví dụ: tạo project bằng Resource Manager chỉ tạo một đơn vị quản lý. Để chạy ứng dụng Cloud Run thực tế còn phải bảo đảm quyền triển khai, bật API cần thiết, liên kết billing khi được yêu cầu, tạo artifact và cấu hình networking hoặc IAM phù hợp.

## 6. Chính sách kế thừa theo hierarchy

Điểm mạnh nhất của hierarchy là có thể đặt quyền và quy tắc quản trị ở cấp phù hợp, rồi để chúng áp dụng xuống những tài nguyên bên dưới.

### 6.1. IAM allow policy: cấp quyền từ trên xuống

Giả sử:

~~~text
Organization
└── Folder: Production
    └── Folder: Commerce
        └── Project: atlas-shop-prod
~~~

- Nhóm `security-auditors@example.com` được cấp vai trò chỉ đọc phù hợp ở organization.
- Nhóm `prod-observers@example.com` được cấp quyền xem log phù hợp tại folder Production.
- Tài khoản dịch vụ triển khai của ứng dụng chỉ được cấp những vai trò cần thiết tại project `atlas-shop-prod`.

Ở project `atlas-shop-prod`, các IAM allow binding trên **chính project** kết hợp với những allow binding **kế thừa từ các ancestor**. Vai trò áp dụng còn phụ thuộc điều kiện của binding, loại tài nguyên và các cơ chế kiểm soát truy cập khác.

> **Cẩn trọng:** Xóa vai trò khỏi IAM policy của project không thu hồi được quyền vẫn đang được cấp từ organization hoặc folder. Muốn thay đổi quyền kế thừa, cần xem lại chính sách tại nơi cấp quyền.

Không nên cấp `roles/owner` hoặc quyền quản trị diện rộng tại organization cho toàn bộ lập trình viên chỉ để họ thuận tiện deploy một ứng dụng. Hãy dùng nhóm, vai trò được xác định hẹp, tài khoản dịch vụ chuyên trách và phạm vi tài nguyên nhỏ nhất đáp ứng công việc.

### 6.2. IAM Deny và Organization Policy là hai cơ chế khác nhau

**IAM Deny** có thể chặn những quyền cụ thể dù có allow binding tương ứng; chính sách deny cũng có quy tắc về phạm vi và kế thừa.

**Organization Policy** quản trị **những điều kiện cấu hình** được phép đối với tài nguyên. Ví dụ, một doanh nghiệp có thể hạn chế các vị trí triển khai nhất định hoặc kiểm soát việc sử dụng địa chỉ IP công khai theo các constraint được hỗ trợ. Chính sách hiệu lực phụ thuộc loại constraint, nơi gắn, cơ chế kế thừa và quy tắc áp dụng; không thể suy ra kết quả chỉ bằng cách cộng các quy tắc.

| Câu hỏi | Cơ chế liên quan |
| --- | --- |
| Nhóm nào được xem cấu hình project? | IAM allow policy |
| Có cần chặn principal dùng một permission cụ thể? | IAM Deny |
| Có được tạo loại cấu hình trái quy định của tổ chức? | Organization Policy |
| Người đó có thực sự truy cập được tài nguyên không? | Xem **quyền hiệu lực**, gồm allow, deny, điều kiện và các kiểm soát có liên quan |

### 6.3. Ba quy tắc an toàn

1. Gắn quyền chung ở **cấp cao nhất thực sự cần**: kiểm toán toàn tổ chức ở organization, vận hành production ở folder Production, deploy một ứng dụng ở project ứng dụng.
2. Tách vai trò **quản trị hierarchy** (tạo project, quản folder) khỏi vai trò **quản trị workload** (thay đổi Cloud Run, GKE, Cloud SQL).
3. Trước khi di chuyển project hoặc thay đổi folder, kiểm tra quyền hiệu lực, Organization Policy và các phụ thuộc vận hành; chính sách từ ancestor mới có thể khiến ứng dụng hoạt động khác đi.

## 7. Thực hành khám phá hierarchy bằng gcloud

Các lệnh dưới đây dùng trong Cloud Shell hoặc terminal đã cài **Google Cloud CLI**. Bạn phải đăng nhập đúng tài khoản và có quyền xem/tạo tài nguyên tương ứng. ID trong ví dụ là giả định; thay bằng ID thật trước khi chạy.

### Bước 1: Kiểm tra tài khoản và organization

~~~bash
gcloud auth list
gcloud organizations list
~~~

`gcloud organizations list` liệt kê các organization tài khoản hiện tại có thể truy cập. Nếu danh sách trống, có thể tài khoản không thuộc organization hoặc không có quyền xem; không nên tự kết luận organization không tồn tại.

### Bước 2: Xem folder và project

~~~bash
# Folder con trực tiếp của organization
gcloud resource-manager folders list --organization=123456789012

# Folder con trực tiếp của một folder
gcloud resource-manager folders list --folder=234567890123

# Những project tài khoản có thể liệt kê
gcloud projects list

# Xem thông tin một project
gcloud projects describe atlas-shop-prod-2026
~~~

Quan sát các trường project ID, project number, parent và trạng thái. Kết quả liệt kê phản ánh **quyền nhìn thấy** của tài khoản, vì vậy có thể chưa đầy đủ đối với toàn bộ doanh nghiệp.

### Bước 3: Tạo folder và project mẫu

Ví dụ sau là **lệnh tạo tài nguyên thật** nếu chạy bằng tài khoản có quyền. Chỉ thực hiện trong organization/lab đã được cấp phép, và chọn project ID chưa ai sử dụng.

~~~bash
# Tạo folder Commerce dưới organization
gcloud resource-manager folders create \
  --display-name="Commerce" \
  --organization=123456789012

# Dùng folder ID thực tế vừa trả về để tạo project
gcloud projects create atlas-shop-dev-2026 \
  --name="Atlas Shop Dev" \
  --folder=456789012345 \
  --labels=environment=dev,team=commerce

# Xác minh project
gcloud projects describe atlas-shop-dev-2026
~~~

Nếu không có folder, một project thuộc tổ chức có thể được tạo trực tiếp dưới organization bằng cờ `--organization=ORGANIZATION_ID` thay cho `--folder=FOLDER_ID`. Một số tài khoản cá nhân có thể tạo project không có organization. Không dùng cả hai cờ parent cùng lúc.

Tạo folder thường đòi hỏi quyền trên parent; tạo project cũng đòi hỏi quyền tạo project tại parent. Được phép sử dụng dịch vụ trong một project **không tự động** có quyền tạo project mới.

### Bước 4: Xem chính sách IAM ở project

~~~bash
gcloud projects get-iam-policy atlas-shop-dev-2026
~~~

Lệnh này hữu ích để xem **allow policy trực tiếp** gắn với project. Để đánh giá quyền hiệu lực, cần kiểm tra thêm binding kế thừa từ folder/organization và các chính sách liên quan; một lần xem policy tại project không đủ chứng minh principal có hay không có quyền.

### Bước 5: Hoàn thiện điều kiện chạy dịch vụ

Trước khi chạy VM, tạo database hay triển khai Cloud Run/GKE, cần lần lượt xác minh:

1. Billing account đã được liên kết với project nếu dịch vụ yêu cầu.
2. API cần thiết đã được bật bằng Service Usage.
3. Tài khoản triển khai có vai trò phù hợp; service account runtime cũng có quyền tối thiểu.
4. Region/zone, VPC, quy tắc bảo mật và quota đáp ứng workload.
5. Label và cơ chế theo dõi chi phí/log/metrics phù hợp môi trường.

Hierarchy quyết định **phạm vi quản trị**, không tự thực hiện năm bước này.

## 8. Tình huống thiết kế: thương mại điện tử nhiều môi trường

Công ty Atlas vận hành ứng dụng bán hàng gồm web API trên Cloud Run, xử lý sự kiện, Cloud SQL và bucket lưu ảnh. Nhóm muốn:

- Tránh vô tình triển khai thay đổi của dev lên production.
- Cho phép Security kiểm toán rộng, nhưng developer chỉ triển khai trong môi trường được phân công.
- Quản lý chi phí và quota riêng theo môi trường.
- Có thể dùng hạ tầng mạng chia sẻ khi cần, nhưng vẫn quản lý IAM tại từng project.

Một phương án hợp lý:

| Cấp | Tài nguyên mẫu | Mục đích |
| --- | --- | --- |
| Organization | `atlas.example` | Quyền sở hữu và các chính sách toàn công ty |
| Folder | `Production` | Quy tắc bảo vệ hệ thống đang phục vụ khách hàng |
| Folder con | `Production/Commerce` | Ủy quyền cho nhóm Commerce trong production |
| Project | `atlas-shop-prod` | Cloud Run, database và lưu trữ cho ứng dụng production |
| Folder | `Nonproduction` | Chính sách dành cho thử nghiệm và kiểm thử |
| Project | `atlas-shop-dev`, `atlas-shop-staging` | Môi trường phát triển và staging tách biệt |
| Folder | `Platform` | Quản trị dịch vụ hạ tầng dùng chung |
| Project | `atlas-network-hub` | Ví dụ nơi đội Platform quản lý hạ tầng mạng trung tâm |

**Luồng quyết định khi có một workload mới:**

~~~mermaid
flowchart TD
    A["Có workload mới"] --> B{"Ai sở hữu và chịu trách nhiệm?"}
    B --> C["Chọn organization và nhánh folder quản trị"]
    C --> D{"Môi trường có cần tách IAM, quota, chi phí, vòng đời?"}
    D -->|Có| E["Tạo project riêng"]
    D -->|Không| F["Đánh giá dùng project hiện có"]
    E --> G["Áp dụng IAM và Organization Policy"]
    F --> G
    G --> H["Liên kết billing, bật API, chọn location và cấu hình mạng"]
    H --> I["Triển khai, gắn nhãn, quan sát và quản lý chi phí"]
~~~

Phương án trên ưu tiên tách dev/staging/production vì chúng có khác biệt về quyền và yêu cầu vận hành. Nó không ngụ ý rằng mọi microservice đều phải có một project riêng. Khi thiết kế thực tế, cân nhắc **quyền sở hữu, mức cô lập cần thiết, quota, cách cấp quyền, chi phí và vòng đời**.

### Khi áp dụng chính sách, điều gì xảy ra?

Giả sử vai trò xem log được cấp cho nhóm trực ca tại folder `Production`. Khi tạo project `atlas-payment-prod` dưới nhánh đó, quyền tương ứng có thể được kế thừa mà không cần thêm từng binding ở mỗi project.

Ngược lại, nếu developer có quyền chỉnh sửa ở folder `Nonproduction`, đặt project production vào nhầm folder này sẽ làm sai ranh giới quyền dự định. Vì vậy, **chọn parent đúng khi tạo project là một quyết định bảo mật và vận hành**, không chỉ là đặt tên.

## 9. Những lỗi phổ biến và cách tránh

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nhầm project name với project ID | Script/API tham chiếu sai project | Dùng ID bất biến trong automation; đặt tên hiển thị để con người dễ hiểu |
| Cấp quyền quá rộng ở organization | Quyền lan xuống nhiều project | Dùng vai trò hẹp và gắn tại folder/project phù hợp |
| Nghĩ folder tự chặn IAM kế thừa | Người có quyền cấp trên vẫn có thể truy cập | Kiểm tra toàn bộ allow/deny policy hiệu lực |
| Xem billing account như folder | Thiết kế sai mô hình tổ chức và phân bổ chi phí | Quản lý liên kết billing và cost reporting riêng |
| Đặt toàn bộ dev/prod vào một project | Khó phân quyền, quota, chi phí và vòng đời | Tách project theo môi trường khi có lý do rõ ràng |
| Đổi parent project mà không đánh giá | Chính sách mới có thể chặn triển khai hoặc mở rộng quyền | Kiểm tra IAM, Organization Policy, quan hệ phụ thuộc trước/sau di chuyển |
| Cho rằng project cùng folder tự có mạng chung | Ứng dụng không kết nối như kỳ vọng | Thiết kế VPC, Shared VPC, routing và firewall riêng |
| Cho rằng folder Production quyết định vị trí dữ liệu | Workload có thể nằm ở region không mong muốn | Chọn và kiểm tra location của từng dịch vụ; áp dụng constraint khi phù hợp |

## 10. Bài tập tự kiểm tra

**Bài 1.** Organization cấp nhóm A quyền xem tài nguyên trong toàn công ty. Project X nằm dưới folder Production nhưng tại project không có binding riêng cho A. A có chắc chắn mất quyền xem vì project không khai báo binding này?

*Gợi ý trả lời:* Không. Allow binding ở organization có thể được kế thừa xuống project. Để xác định quyền thực tế còn phải xét điều kiện, deny và những kiểm soát truy cập liên quan.

**Bài 2.** Nhóm Commerce cần môi trường dev và prod tách nhau về IAM và quota. Nên tạo hai folder, hai project hay hai organization?

*Gợi ý trả lời:* Thông thường bắt đầu từ **hai project** tách môi trường, đặt dưới folder dev/prod phù hợp với cấu trúc quản trị hiện có. Hai organization chỉ vì hai môi trường thường làm tăng độ phức tạp không cần thiết.

**Bài 3.** Một project có tên hiển thị `Shop Production` và ID `atlas-shop-prod-2026`. Sau khi đổi display name, CI/CD có cần thay giá trị project ID không?

*Gợi ý trả lời:* Không. Project ID độc lập với display name và không thể đổi sau khi tạo.

**Bài 4.** Đội Platform di chuyển project từ folder Nonproduction sang Production. Hai điều quan trọng cần rà soát là gì?

*Gợi ý trả lời:* Quyền IAM hiệu lực sau khi kế thừa từ ancestor mới và Organization Policy áp dụng tại nhánh Production. Cũng cần kiểm tra ảnh hưởng đến triển khai, quota/cấu hình liên quan và các phụ thuộc khác.

**Bài 5.** Tạo project xong đã đủ để triển khai một ứng dụng Cloud Run dùng Cloud SQL chưa?

*Gợi ý trả lời:* Chưa. Cần có billing/API khi yêu cầu, IAM cho người triển khai và runtime, tài nguyên database, location, networking, bảo mật, giới hạn sử dụng và quan sát vận hành.

## 11. Ghi nhớ khi chuyển sang các bài GCP tiếp theo

- **Organization** xác định quyền sở hữu và quản trị chung của doanh nghiệp.
- **Folder** nhóm project hoặc folder con để kế thừa chính sách và phân quyền có cấu trúc.
- **Project** là đơn vị thực tế để sử dụng dịch vụ và quản lý tài nguyên.
- **Cloud Resource Manager** là bộ công cụ/API để điều phối những nút của hierarchy.
- **IAM**, **Organization Policy**, **Billing**, **VPC** và **location** giải quyết những chiều quản trị khác nhau, cần kết hợp ở đúng cấp.

Khi tạo bất kỳ workload nào ở những bài về Compute Engine, GKE, Cloud Run, lưu trữ hoặc cơ sở dữ liệu, hãy hỏi trước: **workload thuộc project nào, project nằm dưới parent nào, ai được quyền thay đổi nó, và những chính sách nào đang có hiệu lực?** Trả lời được bốn câu hỏi đó giúp quá trình triển khai, bảo mật, tự động hóa, quan sát và tối ưu chi phí có nền tảng rõ ràng.

## Tài liệu tham khảo chính thức

- [About resource hierarchy — Google Cloud Resource Manager](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy)
- [Resource Manager overview](https://docs.cloud.google.com/resource-manager/docs/resource-manager-overview)
- [Using resource hierarchy for access control — IAM](https://docs.cloud.google.com/iam/docs/resource-hierarchy-access-control)
- [Create folders](https://docs.cloud.google.com/resource-manager/docs/creating-managing-folders)
- [gcloud projects create](https://docs.cloud.google.com/sdk/gcloud/reference/projects/create)
- [gcloud resource-manager folders list](https://docs.cloud.google.com/sdk/gcloud/reference/resource-manager/folders/list)

