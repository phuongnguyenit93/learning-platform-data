# Quản lý gcloud configurations theo tài khoản và môi trường

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **gcloud configuration** là gì, nó lưu những thiết lập nào và khác gì với thông tin đăng nhập, IAM, Google Cloud project và Application Default Credentials (ADC).
2. Tạo, đặt tên, kiểm tra, kích hoạt và xóa cấu hình để làm việc với nhiều **tài khoản** và môi trường **development, staging, production**.
3. Chủ động chọn cấu hình theo từng lệnh, phiên terminal hoặc ngữ cảnh làm việc; hiểu thứ tự ưu tiên giữa cờ lệnh, biến môi trường và giá trị cấu hình.
4. Phát hiện và ngăn thao tác nhầm project, nhầm tài khoản hoặc nhầm GKE cluster trước khi triển khai Compute Engine, Cloud Run, GKE và tài nguyên dữ liệu.
5. Thiết lập quy tắc dùng gcloud an toàn trong phát triển cá nhân và quy trình tự động hóa.

## 1. Vì sao cần nhiều gcloud configurations?

Trong Google Cloud, một kỹ sư có thể đồng thời làm việc với:

- **Development**: thử API, tạo Cloud Run service và kiểm thử thay đổi.
- **Staging**: chạy kiểm thử tích hợp bằng cấu hình gần giống production.
- **Production**: vận hành hệ thống thực, dữ liệu quan trọng và quyền truy cập bị giới hạn.
- **Nhiều danh tính**: tài khoản cá nhân cho phát triển, tài khoản doanh nghiệp cho vận hành và service account được ủy quyền cho một số công việc.

Nếu chỉ dùng một project và một tài khoản, cấu hình mặc định của Google Cloud CLI thường đã đủ. Khi làm việc với nhiều môi trường, việc liên tục đổi project bằng lệnh thủ công làm tăng nguy cơ chạy lệnh vào nhầm môi trường. **Named configurations** giúp nhóm các giá trị mặc định dưới một tên có ý nghĩa, sau đó chọn đúng nhóm khi làm việc.

Ví dụ: cùng một lệnh xem máy ảo có thể đọc danh sách VM ở development hoặc production tùy vào **project và tài khoản hiệu lực**. Tạo riêng hai cấu hình giúp dễ kiểm tra ngữ cảnh trước khi thao tác.

Khả năng này là một phần của mô-đun **CLOUD_PROVIDERS_GCP**: người học sẽ tiếp tục sử dụng project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, CI/CD, quan sát vận hành và tối ưu chi phí. Quản lý đúng ngữ cảnh lệnh là bước chuẩn bị trước khi chạm vào các tài nguyên đó.

## 2. Mô hình khái niệm: configuration, account, project và credentials

**gcloud configuration** là **tập hợp các property có tên** dùng để điều khiển hành vi mặc định của Google Cloud CLI. Mỗi property gồm tên theo nhóm và giá trị; ví dụ:

| Property | Vai trò | Giá trị minh họa |
|---|---|---|
| **core/account** | Danh tính mà gcloud chọn dùng mặc định | dev@example.com |
| **core/project** | Project ID mặc định cho các lệnh hỗ trợ project | shop-dev-123 |
| **compute/region** | Region mặc định cho những lệnh Compute phù hợp | asia-southeast1 |
| **compute/zone** | Zone mặc định cho những lệnh Compute phù hợp | asia-southeast1-b |
| **core/disable_prompts** | Có hỏi xác nhận tương tác hay không | false |
| **auth/impersonate_service_account** | Service account cần mạo danh trong các lệnh hỗ trợ | deployer@shop-prod-123.iam.gserviceaccount.com |

Tất cả giá trị, ID và email trong bài là **ví dụ**. Khi áp dụng thật, thay bằng account, project và region có tồn tại và được cấp quyền.

### 2.1. Tên configuration không tạo tài nguyên Google Cloud

Ví dụ, tạo cấu hình **shop-prod** trên máy không tạo ra project **shop-prod-123** ở Google Cloud. Cấu hình chỉ lưu giá trị tham chiếu đến project đó. Tương tự, thiết lập **core/account** không đăng nhập thay người dùng và cũng không cấp quyền IAM cho tài khoản.

Một lời gọi API thành công cần đồng thời:

1. **Đúng đích**: project, region, zone và tài nguyên cần thao tác.
2. **Đúng danh tính**: tài khoản gcloud đã xác thực hoặc danh tính được sử dụng qua cơ chế khác.
3. **Có quyền thực tế**: IAM, chính sách tổ chức và các điều kiện truy cập phải cho phép hành động.

### 2.2. Configuration khác kho credentials

Khi chạy **gcloud auth login**, Google Cloud CLI lưu thông tin xác thực vào vùng cấu hình người dùng trên máy. Nhiều named configurations có thể **tham chiếu đến các tài khoản đã đăng nhập** thông qua property **core/account**. Chúng không tự tạo ra nhiều phiên đăng nhập độc lập và không thay thế IAM.

Ví dụ, nếu cùng một kỹ sư có quyền trên hai project, hai cấu hình có thể dùng **cùng account** nhưng **khác project**. Ngược lại, hai cấu hình có thể trỏ đến hai account khác nhau cùng có quyền trên một project.

~~~mermaid
flowchart TD
    A["Named configuration: shop-dev"] --> B["core/account: dev@example.com"]
    A --> C["core/project: shop-dev-123"]
    A --> D["compute/region: asia-southeast1"]
    B --> E["Kho thông tin xác thực gcloud"]
    E --> F["Google Cloud API và kiểm tra IAM"]
    C --> F
    D --> F
    G["Ứng dụng Java / Client Libraries"] --> H["Application Default Credentials (ADC)"]
    H --> F
~~~

**ADC (Application Default Credentials)** là cơ chế tìm danh tính của nhiều Google Cloud Client Libraries, chẳng hạn thư viện Java truy cập Cloud Storage hoặc BigQuery. Đường đi của ADC có thể khác với danh tính mà lệnh gcloud dùng. Sự phân biệt này rất quan trọng khi terminal chạy được một lệnh nhưng chương trình Java lại báo lỗi xác thực.

## 3. Thiết kế bộ configurations theo tài khoản và môi trường

Giả sử dự án thương mại điện tử có ba môi trường. Một cách đặt tên nhất quán:

| Tên cấu hình cục bộ | Account dự kiến | Project ID | Mục đích |
|---|---|---|---|
| **shop-dev** | dev@example.com | shop-dev-123 | Viết mã và thử nghiệm |
| **shop-staging** | dev@example.com | shop-staging-123 | Kiểm thử tích hợp |
| **shop-prod** | ops@example.com | shop-prod-123 | Quan sát và vận hành sản xuất |

Đây là **tên môi trường do nhóm đặt**, không phải loại configuration có sẵn trong Google Cloud. Project ID phải được xác minh từ hệ thống thật. Production nên có quyền IAM tối thiểu, quy trình phê duyệt thay đổi và cơ chế nhận diện ngữ cảnh rõ ràng.

### Nguyên tắc chọn tên

- Dùng chữ thường, số và dấu gạch nối theo cú pháp tên configuration; chọn tên có tính gợi nhớ như **shop-dev**, **shop-prod**.
- Đưa **sản phẩm/dịch vụ** và **môi trường** vào tên khi phải quản lý nhiều hệ thống.
- Không đặt tên theo bí mật, mật khẩu hay token.
- Không cho rằng tên cấu hình quyết định mức quyền truy cập. Quyền thực tế vẫn do IAM và chính sách quản lý.
- Khi một cá nhân quản lý nhiều project của nhiều tổ chức, có thể thêm mã tổ chức hoặc nhóm vào tên để tránh nhầm lẫn.

## 4. Thao tác cơ bản với named configurations

Ví dụ bên dưới sử dụng **Google Cloud CLI (gcloud)** đã được cài đặt. Lệnh có thể chạy trong terminal thông thường, Cloud Shell hoặc máy phát triển. Trước khi chạy các ví dụ có truy cập tài nguyên, phải thay các ID và email minh họa bằng giá trị thật.

### Bước 1 — Kiểm tra CLI và các cấu hình hiện có

~~~bash
# Kiểm tra CLI đã cài
gcloud version

# Cấu hình đang có và cấu hình đang active
gcloud config configurations list

# Xem các property hiệu lực của cấu hình đang active
gcloud config list

# Xem tài khoản đã xác thực trên máy
gcloud auth list

# Xem chi tiết cấu hình mặc định nếu tồn tại
gcloud config configurations describe default
~~~

Lệnh **gcloud init** thích hợp cho lần thiết lập ban đầu: chương trình hướng dẫn chọn hoặc tạo configuration, đăng nhập và chọn project. Khi đã có nhiều cấu hình, hãy thận trọng với thao tác **re-initialize** vì có thể thay thế các property hiện có.

Trong kết quả **gcloud config configurations list**, cột **IS_ACTIVE** cho biết cấu hình mặc định hiện tại. Kết quả **gcloud auth list** cho biết các account đã xác thực; nên đối chiếu cả hai khi nghi ngờ nhầm tài khoản.

### Bước 2 — Đăng nhập những tài khoản cần dùng

~~~bash
# Chạy một lần và chọn dev@example.com trong trình duyệt
gcloud auth login

# Chạy lại nếu cần thêm tài khoản ops@example.com
gcloud auth login

# Kiểm tra tài khoản thực tế đã đăng nhập
gcloud auth list
~~~

Hai email trên chỉ mang tính minh họa. Quy trình đăng nhập phụ thuộc cơ chế SSO/MFA của tổ chức. Lệnh đăng nhập có thể thay account được đánh dấu active trong configuration đang dùng; vì vậy, **kiểm tra và đặt core/account một cách tường minh** sau bước này.

**Không chia sẻ thư mục credentials cá nhân**, không đưa token hoặc file xác thực lên Git và không dùng đăng nhập người dùng tương tác để chạy job tự động dài hạn.

### Bước 3 — Tạo ba cấu hình mà chưa kích hoạt

~~~bash
gcloud config configurations create shop-dev --no-activate
gcloud config configurations create shop-staging --no-activate
gcloud config configurations create shop-prod --no-activate

gcloud config configurations list
~~~

Trong các phiên bản gcloud CLI hiện hành, lệnh **create** mặc định có thể kích hoạt cấu hình mới; cờ **--no-activate** giữ nguyên ngữ cảnh hiện tại. Nếu đã tồn tại tên cấu hình, dùng **describe** để kiểm tra trước, tránh ghi đè ngoài ý muốn.

### Bước 4 — Gán account, project và region theo từng configuration

Cờ toàn cục **--configuration** cho phép chỉnh một cấu hình đã đặt tên mà không cần kích hoạt nó cho mọi lệnh.

~~~bash
# Development
gcloud config set core/account dev@example.com --configuration=shop-dev
gcloud config set core/project shop-dev-123 --configuration=shop-dev
gcloud config set compute/region asia-southeast1 --configuration=shop-dev
gcloud config set compute/zone asia-southeast1-b --configuration=shop-dev

# Staging
gcloud config set core/account dev@example.com --configuration=shop-staging
gcloud config set core/project shop-staging-123 --configuration=shop-staging
gcloud config set compute/region asia-southeast1 --configuration=shop-staging
gcloud config set compute/zone asia-southeast1-b --configuration=shop-staging

# Production
gcloud config set core/account ops@example.com --configuration=shop-prod
gcloud config set core/project shop-prod-123 --configuration=shop-prod
gcloud config set compute/region asia-southeast1 --configuration=shop-prod
gcloud config set compute/zone asia-southeast1-b --configuration=shop-prod
~~~

**core/account** cần trỏ đến tài khoản đã xác thực và có quyền phù hợp. Nếu chưa đăng nhập **ops@example.com**, chỉ đặt property sẽ không khiến tài khoản này dùng được. **compute/region** và **compute/zone** hỗ trợ các lệnh Compute phù hợp; một số dịch vụ khác như Cloud Run yêu cầu **--region** riêng hoặc có property theo dịch vụ.

### Bước 5 — Đọc lại từng cấu hình

~~~bash
gcloud config configurations describe shop-dev
gcloud config configurations describe shop-staging
gcloud config configurations describe shop-prod

# Đọc giá trị project hiệu lực trong một configuration cụ thể
gcloud config get-value core/project --configuration=shop-dev

# Xem tất cả cấu hình và trạng thái active
gcloud config configurations list
~~~

**Kiểm tra trước khi sử dụng production**: account, project ID và vùng triển khai có đúng không; có biến môi trường nào đang ghi đè không; danh tính có quyền đúng mục đích không.

### Bước 6 — Kích hoạt cấu hình và chạy lệnh

~~~bash
# Chuyển ngữ cảnh mặc định sang development
gcloud config configurations activate shop-dev

gcloud config list
gcloud config get-value core/account
gcloud config get-value core/project

# Chỉ kiểm tra thông tin project (cần quyền tương ứng)
gcloud projects describe shop-dev-123

# Chạy một lệnh với production, không chuyển active mặc định
gcloud projects describe shop-prod-123 --configuration=shop-prod
~~~

Khi **activate**, bạn đổi configuration mặc định của khu vực cấu hình gcloud đang dùng. Khi dùng **--configuration=shop-prod**, chỉ lần gọi lệnh đó chọn cấu hình production. Hai cách phục vụ hai nhu cầu khác nhau: đổi phiên làm việc hoặc gọi một lệnh rõ ngữ cảnh.

## 5. Ba cách chọn configuration và phạm vi ảnh hưởng

| Cơ chế | Cách dùng | Phạm vi | Khi nào phù hợp |
|---|---|---|---|
| **activate** | gcloud config configurations activate shop-dev | Thay cấu hình active của bộ cấu hình gcloud cục bộ | Làm việc tương đối lâu trong một môi trường |
| **--configuration** | gcloud projects list --configuration=shop-prod | Chỉ một lệnh | Script hoặc thao tác cần minh định môi trường |
| **CLOUDSDK_ACTIVE_CONFIG_NAME** | Đặt biến môi trường trước khi chạy gcloud | Tiến trình terminal và tiến trình con thừa kế biến | Mỗi cửa sổ terminal hoặc thư mục dự án dùng môi trường riêng |

### 5.1. Chọn cấu hình cho một lệnh

~~~bash
gcloud compute instances list --configuration=shop-dev
gcloud compute instances list --configuration=shop-prod

# Với dịch vụ yêu cầu region, chỉ định thêm vị trí rõ ràng
gcloud run services list --region=asia-southeast1 --configuration=shop-staging
~~~

Cách này dễ kiểm tra khi review script: lệnh đã nêu rõ environment. Với tài nguyên production, vẫn cần phân quyền IAM và thủ tục phê duyệt thay đổi phù hợp.

### 5.2. Chọn cấu hình trong terminal Linux/macOS

~~~bash
# Chỉ ảnh hưởng terminal hiện tại và tiến trình con
export CLOUDSDK_ACTIVE_CONFIG_NAME=shop-staging
gcloud config list
gcloud projects describe shop-staging-123

# Bỏ thiết lập của terminal
unset CLOUDSDK_ACTIVE_CONFIG_NAME
~~~

### 5.3. Chọn cấu hình trong Windows PowerShell

~~~powershell
# Chọn cấu hình chỉ cho phiên PowerShell hiện tại
$env:CLOUDSDK_ACTIVE_CONFIG_NAME = "shop-dev"
gcloud config list
gcloud projects describe shop-dev-123

# Bỏ biến môi trường trong phiên hiện tại
Remove-Item Env:CLOUDSDK_ACTIVE_CONFIG_NAME
~~~

**Lưu ý về nhiều terminal:** thao tác **activate** thay giá trị cấu hình active của vùng cấu hình gcloud dùng chung, vì vậy cửa sổ terminal khác có thể chịu ảnh hưởng nếu cùng dùng vùng cấu hình và không đặt override. Biến môi trường trong từng terminal hoặc cờ **--configuration** giúp xác định ngữ cảnh riêng.

## 6. Thứ tự ưu tiên: cờ lệnh, biến môi trường, cấu hình đã lưu

Một số lệnh gcloud cho phép ghi đè property của cấu hình. Ví dụ với **project**:

1. **Cờ của lệnh** như **--project** có độ ưu tiên cao nhất cho lần chạy đó.
2. **Biến môi trường** như **CLOUDSDK_CORE_PROJECT** có thể ghi đè giá trị lưu trong configuration.
3. **Property core/project** trong named configuration đang được chọn là giá trị mặc định khi không bị override.

~~~bash
# Ví dụ: property lưu sẵn trong shop-dev là shop-dev-123
gcloud config configurations describe shop-dev

# Ghi đè project chỉ cho lệnh này
gcloud compute instances list --configuration=shop-dev --project=shop-staging-123
~~~

Lệnh trên **vẫn chọn configuration shop-dev**, nhưng **--project** khiến việc liệt kê VM hướng đến **shop-staging-123**. Đây là ví dụ cho thấy **tên configuration không bảo đảm project thực thi** khi có override.

Ví dụ với terminal:

~~~bash
# Linux/macOS
export CLOUDSDK_ACTIVE_CONFIG_NAME=shop-dev
export CLOUDSDK_CORE_PROJECT=shop-staging-123

# Giá trị core/project hiệu lực có thể là shop-staging-123
gcloud config get-value core/project

# Gỡ override để quay lại giá trị lưu trong configuration
unset CLOUDSDK_CORE_PROJECT
~~~

~~~powershell
# Windows PowerShell
$env:CLOUDSDK_ACTIVE_CONFIG_NAME = "shop-dev"
$env:CLOUDSDK_CORE_PROJECT = "shop-staging-123"

gcloud config get-value core/project

Remove-Item Env:CLOUDSDK_CORE_PROJECT
~~~

Biến môi trường tương ứng các property thường có dạng **CLOUDSDK_SECTION_PROPERTY**. Ví dụ: **CLOUDSDK_CORE_PROJECT**, **CLOUDSDK_CORE_ACCOUNT**, **CLOUDSDK_COMPUTE_ZONE**. Cần kiểm tra môi trường terminal và cấu hình đã lưu trước khi kết luận lệnh sẽ tác động đến đâu.

**Không nhầm ba biến/cờ khác nhau:**

- **CLOUDSDK_ACTIVE_CONFIG_NAME** chọn **tên configuration** cho phiên.
- **CLOUDSDK_CORE_PROJECT** ghi đè **project** của configuration hiệu lực.
- **CLOUDSDK_CONFIG** chọn **thư mục chứa toàn bộ trạng thái gcloud cục bộ**, gồm configurations và dữ liệu xác thực; đây không phải tên một named configuration.

Thay **CLOUDSDK_CONFIG** có thể khiến CLI không tìm thấy tên cấu hình hoặc credential đã thiết lập ở thư mục cũ. Giá trị này cần trỏ tới một thư mục phù hợp có quyền ghi. Việc thay thư mục cấu hình nên có chủ đích, nhất là trên máy dùng chung hoặc trong môi trường CI.

## 7. Tách biệt gcloud CLI authentication và ADC cho ứng dụng

### 7.1. Truy cập API qua lệnh gcloud

Với Google Cloud CLI, hãy kiểm tra account mà cấu hình chọn:

~~~bash
gcloud auth list
gcloud config get-value core/account --configuration=shop-dev
gcloud config get-value core/account --configuration=shop-prod
~~~

**gcloud auth login** bổ sung hoặc làm mới credentials cho gcloud. **gcloud config set core/account** chỉ xác định tài khoản gcloud định dùng; nó không tạo danh tính hay cấp IAM.

### 7.2. Truy cập API từ thư viện Java và các client libraries

Ứng dụng Java sử dụng Google Cloud Client Libraries thường dùng **Application Default Credentials (ADC)**. Trong môi trường phát triển cá nhân, một cách thiết lập là:

~~~bash
# Đăng nhập ADC cho ứng dụng chạy local
gcloud auth application-default login

# Khi cần, đặt quota project cho ADC bằng một project có quyền phù hợp
gcloud auth application-default set-quota-project shop-dev-123
~~~

Thông tin ADC được quản lý riêng với credentials của các lệnh gcloud. Việc **activate shop-prod** không đồng nghĩa ứng dụng Java đang chạy local tự đổi sang production. Nếu dùng biến **GOOGLE_APPLICATION_CREDENTIALS**, ADC có thể lấy thông tin theo đường dẫn file chỉ định; đường dẫn này có thể chứa cấu hình federation hoặc loại credential khác được hỗ trợ. Không đưa file nhạy cảm hoặc service account key vào kho mã nguồn.

Ví dụ thường gặp:

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| gcloud đọc Cloud Storage thành công, ứng dụng Java báo lỗi thiếu credentials | Ứng dụng dùng ADC chưa được thiết lập trong môi trường chạy |
| gcloud đang chọn project dev, thư viện Java truy cập dữ liệu ở project khác | Project mà ứng dụng truyền vào SDK và ADC có thể độc lập với configuration gcloud |
| Máy dev chạy ổn, CI báo lỗi xác thực | CI cần cơ chế danh tính workload của riêng nó; không có sẵn phiên đăng nhập cá nhân |

Trên Google Cloud, workload nên dùng **service account gắn với tài nguyên chạy** khi phù hợp; với CI/CD ngoài Google Cloud, ưu tiên **Workload Identity Federation** hoặc phương án danh tính ngắn hạn được tổ chức chấp thuận. Hạn chế tạo service account key dài hạn.

### 7.3. Impersonation: sử dụng danh tính được ủy quyền

Trong một số công việc, người vận hành cần gọi API bằng service account triển khai có quyền giới hạn. Google Cloud CLI hỗ trợ cờ **--impersonate-service-account** khi tài khoản gọi đã được cấp quyền mạo danh tương ứng.

~~~bash
# Chỉ sử dụng khi tài khoản hiện tại đã được cấp quyền impersonation
gcloud run services list --region=asia-southeast1 \
  --configuration=shop-prod \
  --impersonate-service-account=deployer@shop-prod-123.iam.gserviceaccount.com
~~~

Ví dụ sử dụng dấu nối dòng của **Bash**. Trong PowerShell, hãy viết một dòng hoặc dùng cú pháp xuống dòng của PowerShell. Impersonation **không vượt qua IAM**: tài khoản nguồn cần quyền tạo token cho service account, đồng thời service account đích cần quyền đối với tài nguyên cần thao tác.

Nếu dùng thường xuyên, có thể cấu hình **auth/impersonate_service_account** riêng cho một named configuration:

~~~bash
gcloud config set auth/impersonate_service_account \
  deployer@shop-prod-123.iam.gserviceaccount.com \
  --configuration=shop-prod

# Gỡ property khi không còn cần
gcloud config unset auth/impersonate_service_account --configuration=shop-prod
~~~

Thiết lập impersonation cũng là một property có thể chịu override; cần kiểm tra khi phân tích **danh tính hiệu lực** của một lệnh.

## 8. Thao tác an toàn trước khi triển khai hoặc thay đổi production

### 8.1. Checklist ngữ cảnh trước lệnh có tác động

Trước thao tác như triển khai Cloud Run, sửa VM, đổi IAM, chạy database migration hay xóa Cloud Storage bucket:

1. **Xác nhận tên configuration** qua danh sách hoặc dùng **--configuration** rõ ràng.
2. **Xác nhận project**: xem **core/project**, các biến môi trường và cờ **--project** của lệnh.
3. **Xác nhận danh tính**: **core/account**, danh sách credentials và cờ/thuộc tính impersonation nếu có.
4. **Xác nhận vị trí và tài nguyên**: region/zone/cluster/service/bucket thực sự tồn tại ở môi trường đích.
5. **Kiểm tra trước bằng lệnh đọc** và tài liệu thay đổi; chỉ thực hiện thay đổi khi có quyền và phê duyệt phù hợp.
6. **Chuẩn bị khả năng khôi phục** cho thay đổi có rủi ro: ví dụ rollback phiên bản Cloud Run, kiểm thử restore dữ liệu hoặc snapshot theo chính sách.

Ví dụ quy trình **đọc thông tin** trước một lần phát hành Cloud Run:

~~~bash
gcloud config configurations describe shop-prod
gcloud auth list

# Dùng project và region tường minh
gcloud run services list \
  --configuration=shop-prod \
  --project=shop-prod-123 \
  --region=asia-southeast1
~~~

Việc ghi rõ project trong lệnh giúp reviewer nhìn thấy đích dự kiến. Tuy nhiên, người chạy vẫn phải kiểm tra danh tính và các override khác; bản thân **--project** không ngăn được một người chọn sai project ID.

### 8.2. Với GKE, kubectl có ngữ cảnh riêng

Đặc biệt lưu ý: **kubectl** đọc **kubeconfig** với **current-context** riêng. Chuyển từ **shop-dev** sang **shop-prod** trong gcloud không có nghĩa kubectl tự chọn cluster production tương ứng.

~~~bash
# Xác định cluster mà kubectl đang hướng đến
kubectl config current-context
kubectl config get-contexts

# Chỉ dùng lệnh dưới đây khi muốn cập nhật kubeconfig cho cluster đích
# và đã kiểm tra dự án, vùng cùng quyền truy cập
gcloud container clusters get-credentials shop-cluster \
  --project=shop-staging-123 \
  --location=asia-southeast1 \
  --configuration=shop-staging

# Kiểm tra lại sau khi get-credentials
kubectl config current-context
~~~

Lệnh **get-credentials** cập nhật kubeconfig và có thể đặt current-context mới cho kubectl. Hãy xem **kubectl config current-context** trước mọi thao tác thay đổi Kubernetes namespace, deployment hoặc secret.

### 8.3. Với Terraform và pipeline, truyền project tường minh

Không mặc định rằng **gcloud config configurations activate** sẽ điều khiển project của Terraform, Docker, ứng dụng Java, kubectl hoặc mọi công cụ khác. Mỗi công cụ có cơ chế cấu hình/credentials riêng.

Trong tự động hóa, nên:

- Truyền **project, environment và region** tường minh theo biến pipeline hoặc cấu hình hạ tầng được review.
- Dùng **service account có quyền tối thiểu** và cơ chế danh tính ngắn hạn; tránh dựa vào phiên đăng nhập cá nhân trên máy build.
- Tách thông tin triển khai của dev/staging/prod, có các bước review và phê duyệt phù hợp với production.
- Ghi lại **đích thực thi, phiên bản artifact, kết quả kiểm thử và lịch sử triển khai**; không ghi access token vào log.
- Kiểm tra các **override** của gcloud nếu pipeline có dùng gcloud.

## 9. Quản lý vòng đời và làm sạch cấu hình

### 9.1. Cập nhật hoặc bỏ property

~~~bash
# Thay đổi project mặc định của một configuration
gcloud config set core/project shop-dev-123 --configuration=shop-dev

# Xóa zone mặc định nếu workflow không dùng Compute Engine theo zone
gcloud config unset compute/zone --configuration=shop-dev

# Kiểm tra lại sau thay đổi
gcloud config configurations describe shop-dev
~~~

**unset** bỏ một property; lần chạy sau có thể cần truyền cờ tương ứng hoặc dùng giá trị mặc định khác của CLI.

### 9.2. Xóa named configuration không còn dùng

~~~bash
# Chuyển sang cấu hình khác trước nếu shop-staging đang active
gcloud config configurations activate shop-dev

# Xem cấu hình dự định xóa
gcloud config configurations describe shop-staging

# Xóa khi đã xác nhận không còn dùng
gcloud config configurations delete shop-staging

gcloud config configurations list
~~~

Không thể xóa configuration **đang active** bằng lệnh delete. Xóa tên configuration **không đồng nghĩa thu hồi IAM** và **không mặc nhiên xóa credentials** đã lưu của account; đây là các việc quản trị riêng.

Nếu một account cá nhân không còn được phép sử dụng, cần phối hợp với tổ chức để thu hồi quyền truy cập ở hệ thống IAM/IdP. Việc dọn thông tin xác thực local có thể dùng lệnh **gcloud auth revoke** phù hợp sau khi kiểm tra các cấu hình khác còn cần account đó hay không.

### 9.3. Vị trí lưu gcloud configurations

Thông thường, Google Cloud CLI lưu cấu hình người dùng tại:

| Hệ điều hành | Đường dẫn phổ biến |
|---|---|
| Linux/macOS | ~/.config/gcloud |
| Windows | %APPDATA%\\gcloud |

Đường dẫn cụ thể có thể khác do cài đặt, **CLOUDSDK_CONFIG** hoặc môi trường sử dụng. Kiểm tra bằng:

~~~bash
gcloud info --format="value(config.paths.global_config_dir)"
gcloud info --format="value(config.paths.active_config_path)"
~~~

Thư mục này có thể bao gồm thông tin xác thực, vì vậy không sao chép bừa bãi lên máy khác và không commit vào repository. Trong **Cloud Shell**, tùy bối cảnh phiên làm việc, các thiết lập gcloud ở vùng tạm của từng tab có thể không tồn tại giữa các phiên; cần kiểm tra lại nơi lưu thực tế thay vì giả định.

## 10. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/xử lý |
|---|---|---|
| Lệnh nhìn thấy VM của project khác | **--project** hoặc **CLOUDSDK_CORE_PROJECT** override | Xem toàn bộ lệnh, biến môi trường và **core/project** |
| Account sai dù đã **activate shop-prod** | **core/account** chưa đặt, có override hoặc account khác được login gần đây | **gcloud auth list**, **gcloud config configurations describe shop-prod** |
| Lỗi **PERMISSION_DENIED / 403** | Account hiệu lực thiếu IAM hoặc bị policy chặn | Kiểm tra principal, project, quyền theo thao tác, impersonation |
| Không tìm thấy configuration đã tạo | Đang dùng **CLOUDSDK_CONFIG** khác | Kiểm tra đường dẫn bằng **gcloud info** và biến môi trường |
| **gcloud config list** không giống giá trị của file đã lưu | Biến môi trường hoặc cờ lệnh override | So sánh **describe** với các override trong terminal |
| Chương trình Java báo lỗi ADC, gcloud vẫn chạy | Credentials gcloud và ADC là hai hệ thống sử dụng khác nhau | Kiểm tra cơ chế ADC và danh tính của ứng dụng |
| kubectl thao tác nhầm cluster | current-context của kubeconfig khác kỳ vọng | **kubectl config current-context**, chọn context có chủ đích |
| Lệnh GKE/Compute yêu cầu zone hoặc region | Location chưa được cấu hình hoặc workload ở vùng khác | Xác định vùng của tài nguyên và truyền **--location**, **--zone** hoặc **--region** phù hợp |
| Xóa configuration nhưng account vẫn có thể truy cập | Xóa cấu hình không thu hồi credentials hoặc IAM | Kiểm tra **gcloud auth list**, thu hồi local credentials và quyền thực tế nếu được yêu cầu |

Khi kiểm tra sự cố, nên bắt đầu bằng câu hỏi **“Lệnh đang chạy dưới danh tính nào, hướng đến project nào, lấy giá trị đó từ nguồn nào?”**. Câu trả lời thường giải thích được phần lớn lỗi cấu hình.

## 11. Bài tập tình huống

Một công ty xây API Java/Spring chạy trên **Cloud Run**, lưu dữ liệu trong **Cloud SQL**, ảnh trong **Cloud Storage** và dự kiến có thêm GKE cho một nhóm dịch vụ khác. Nhóm có hai tài khoản người dùng và ba Google Cloud projects: **catalog-dev-001**, **catalog-stg-001**, **catalog-prod-001**.

### Yêu cầu thực hành

1. Đề xuất cách đặt tên **ba configurations** để nhận ra môi trường ngay trong lệnh.
2. Viết các lệnh tạo cấu hình ở trạng thái **chưa active**, đặt **core/project**, **core/account** và **compute/region** cho từng môi trường.
3. Viết hai cách liệt kê Cloud Run services ở staging mà **không thay đổi cấu hình mặc định**: một cách dùng **--configuration**, một cách dùng biến môi trường trong terminal.
4. Giải thích vì sao tài khoản đã login vào gcloud nhưng ứng dụng Java dùng Cloud Storage Client Library vẫn có thể bị lỗi xác thực.
5. Cho biết vì sao chuyển configuration từ dev sang prod chưa đủ để bảo đảm **kubectl** trỏ đến cluster production.
6. Đề xuất các bước kiểm tra an toàn trước khi sửa cấu hình một Cloud SQL instance trong production.

### Đáp án định hướng

- Có thể dùng **catalog-dev**, **catalog-stg**, **catalog-prod** và project ID tương ứng; account phải có credentials cùng IAM phù hợp.
- Dùng **gcloud config configurations create NAME --no-activate**; các lệnh **gcloud config set ... --configuration=NAME** để chỉnh từng cấu hình mà không đổi ngữ cảnh đang dùng.
- Ví dụ xem staging:

~~~bash
gcloud run services list \
  --configuration=catalog-stg \
  --project=catalog-stg-001 \
  --region=asia-southeast1
~~~

- Nếu cần cấu hình phiên terminal, đặt **CLOUDSDK_ACTIVE_CONFIG_NAME=catalog-stg** bằng cú pháp tương ứng hệ điều hành rồi chạy lệnh; gỡ biến khi hoàn tất.
- Client Library thường sử dụng **ADC**, không phụ thuộc trực tiếp vào configuration đã active.
- kubectl có **current-context** riêng trong kubeconfig.
- Trước thay đổi database thật, cần kiểm tra **project/region/instance/account/IAM**, kế hoạch sao lưu và khôi phục, tác động downtime, cửa sổ triển khai và quyền phê duyệt.

## 12. Ghi nhớ và tài liệu tham khảo

**Năm điều cần nhớ:**

1. Named configuration là **nhóm property cục bộ**, không phải project hoặc cơ chế cấp IAM.
2. **core/account** chọn danh tính gcloud mặc định; credentials phải có thật và có quyền. **ADC** dành cho ứng dụng có vòng đời riêng.
3. Dùng **--configuration** cho một lệnh, **CLOUDSDK_ACTIVE_CONFIG_NAME** cho terminal, hoặc **activate** để đổi cấu hình mặc định của gcloud.
4. **--project**, **CLOUDSDK_CORE_PROJECT** và các override khác có thể khiến lệnh sử dụng đích khác với project lưu trong configuration.
5. Trước mọi thay đổi trên production, xác nhận **ngữ cảnh, danh tính, project, region/zone, tài nguyên và khả năng khôi phục**.

**Tài liệu Google Cloud chính thức:**

1. [Managing gcloud CLI configurations](https://docs.cloud.google.com/sdk/docs/configurations) — tạo, chọn, xem và xóa named configurations.
2. [Managing gcloud CLI properties](https://docs.cloud.google.com/sdk/docs/properties) — các property và biến môi trường ghi đè.
3. [gcloud config configurations create — CLI reference](https://docs.cloud.google.com/sdk/gcloud/reference/config/configurations/create) — cú pháp và cờ **--no-activate**.
4. [Authenticate for the gcloud CLI](https://docs.cloud.google.com/sdk/docs/authenticate) — xác thực người dùng, workload và service account impersonation.
5. [How Application Default Credentials works](https://docs.cloud.google.com/docs/authentication/application-default-credentials) — nguồn credentials của Client Libraries.
6. [Install kubectl and configure cluster access](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl) — cấu hình **kubeconfig** và **current-context** khi dùng GKE.
