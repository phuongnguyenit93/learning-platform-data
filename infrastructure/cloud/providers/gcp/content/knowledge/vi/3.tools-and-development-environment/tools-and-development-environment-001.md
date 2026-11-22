# Làm quen Google Cloud Console và Cloud Shell

> **Chương:** Công cụ và môi trường GCP  
> **Bài học:** Làm quen Google Cloud Console và Cloud Shell

Trong mô-đun **CLOUD_PROVIDERS_GCP**, bạn sẽ khám phá Google Cloud từ cấu trúc tổ chức và project, IAM, VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Bạn cũng cần biết cách chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Hai công cụ mở đầu hành trình đó là **Google Cloud Console** và **Cloud Shell**.

Console giúp bạn quan sát, cấu hình và quản trị Google Cloud bằng giao diện web. Cloud Shell cung cấp một môi trường dòng lệnh chạy trên đám mây, có sẵn công cụ như Google Cloud CLI (`gcloud`). Thành thạo cả hai giúp bạn hiểu cấu trúc dự án bằng hình ảnh, rồi lặp lại và tự động hóa thao tác một cách nhất quán.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Giải thích vai trò khác nhau của Google Cloud Console, Cloud Shell và Google Cloud CLI.
- Chọn đúng **project** trước khi quan sát hoặc thay đổi tài nguyên; phân biệt project name, project ID và project number.
- Tìm các khu vực quản lý project, IAM, API, billing, Compute Engine, Cloud Run và giám sát trong Console.
- Mở Cloud Shell, sử dụng terminal và Cloud Shell Editor, kiểm tra tài khoản, cấu hình project và các tài nguyên qua `gcloud`.
- Nhận diện ranh giới giữa một môi trường thực hành và hạ tầng chạy ứng dụng thực tế.
- Phát hiện các lỗi phổ biến về quyền truy cập, API chưa bật, nhầm project/region và rủi ro chi phí.

## 2. Ba khái niệm dễ nhầm lẫn

| Thành phần | Bản chất | Khi nào nên dùng | Điều cần nhớ |
|---|---|---|---|
| **Google Cloud Console** | Giao diện web quản trị Google Cloud | Khám phá tài nguyên, kiểm tra cấu hình, theo dõi log/metric/billing, thao tác ít lặp lại | Chịu sự kiểm soát của IAM và chính sách tổ chức |
| **Cloud Shell** | Môi trường terminal và editor chạy trên một VM do Google vận hành | Thực hành lệnh, kiểm tra trạng thái, chạy script nhỏ, thao tác với repo | VM phiên làm việc có thể được tái tạo; không phải server production |
| **Google Cloud CLI (`gcloud`)** | Bộ công cụ dòng lệnh gọi API Google Cloud | Truy vấn tài nguyên, cấu hình và tự động hóa thao tác | Có thể chạy trong Cloud Shell, máy cá nhân hoặc CI/CD |

Nói cách khác, **Cloud Shell là nơi chạy lệnh; `gcloud` là công cụ thực thi lệnh**. Console và CLI thường tương tác với cùng tài nguyên qua API, nên thao tác thay đổi trong một công cụ có thể được quan sát ở công cụ còn lại.

~~~mermaid
flowchart LR
    U["Người học / quản trị viên"] --> Console["Google Cloud Console<br/>Giao diện trình duyệt"]
    U --> Shell["Cloud Shell<br/>Terminal + Editor"]
    Shell --> CLI["gcloud và công cụ dòng lệnh"]
    Console --> API["Google Cloud APIs"]
    CLI --> API
    API --> IAM["Kiểm tra danh tính, IAM<br/>và chính sách tổ chức"]
    IAM --> Resources["Project và tài nguyên<br/>Compute, GKE, Cloud Run, Storage..."]
~~~

*Lược đồ khái niệm: quyền truy cập được kiểm tra khi gọi dịch vụ. Đăng nhập Console hay mở Cloud Shell không tự tạo quyền quản trị mọi project.*

### 2.1. Cloud Shell không phải Compute Engine để triển khai production

Cloud Shell cung cấp máy ảo tạm thời dành cho tác vụ tương tác, phát triển và quản trị. Compute Engine là dịch vụ tạo VM để bạn thiết kế workload thực tế, quản lý cấu hình, vòng đời và độ tin cậy. Không đặt cơ sở dữ liệu hay API production trong Cloud Shell và trông đợi phiên terminal chạy liên tục.

Cloud Shell có bộ nhớ, tài nguyên, thời lượng phiên và các giới hạn sử dụng theo chính sách hiện hành. Nội dung trong thư mục home thường có cơ chế lưu giữ giữa các phiên trong giới hạn dịch vụ, nhưng máy ảo và các thư mục tạm có thể bị thay thế. **Mã nguồn quan trọng cần lưu bằng Git hoặc kho lưu trữ phù hợp**, không coi Cloud Shell là nơi sao lưu duy nhất.

## 3. Chuẩn bị và hiểu phạm vi truy cập

Bạn cần một tài khoản Google có thể dùng Google Cloud, một trình duyệt và quyền truy cập đến ít nhất một project phù hợp cho thực hành. Tùy tổ chức, bạn có thể cần quản trị viên cấp quyền để xem project, sử dụng Cloud Shell hoặc liệt kê dịch vụ.

Trước khi thao tác, ghi lại các thông tin sau:

| Thông tin | Ý nghĩa | Ví dụ minh họa |
|---|---|---|
| **Organization** | Cấp quản trị cao nhất cho tài nguyên tổ chức, nếu có | `example.com` |
| **Folder** | Nhóm project phục vụ cấu trúc quản trị, nếu tổ chức sử dụng | `Engineering / Sandbox` |
| **Project name** | Tên dễ đọc, có thể trùng giữa các project | `GCP Training` |
| **Project ID** | Định danh duy nhất của project, thường dùng trong `gcloud` và API | `gcp-training-12345` |
| **Project number** | Định danh số do Google cấp, dùng trong nhiều danh tính/cấu hình dịch vụ | `123456789012` |
| **Billing account** | Tài khoản thanh toán liên kết với project đủ điều kiện | Chỉ kiểm tra trạng thái, không cần tiết lộ mã cho người khác |
| **Region / Zone** | Vị trí triển khai tài nguyên vùng / vùng sẵn sàng | `asia-southeast1` / `asia-southeast1-a` |

Các giá trị trên chỉ là ví dụ. **Project name, project ID và project number là ba giá trị khác nhau.** Khi một lệnh yêu cầu `--project`, thông thường bạn cần **project ID**.

### 3.1. Project không đồng nghĩa với tài khoản Google

Một người dùng có thể truy cập nhiều project; một project có thể được nhiều người hoặc service account sử dụng. Project tạo ranh giới quản lý API, quota, tài nguyên, logging và nhiều chính sách; billing có thể được liên kết từ một billing account.

Mô hình quản trị tài nguyên thường là:

~~~text
Organization (nếu có)
└── Folder (nếu có)
    ├── Project: development
    │   ├── Cloud Run service
    │   ├── Cloud SQL instance
    │   └── Cloud Storage bucket
    └── Project: production
        ├── Cloud Run service
        └── Cloud SQL instance
~~~

Khi học, nên dùng **project sandbox được tổ chức cho phép** để giảm nguy cơ ảnh hưởng tài nguyên thật. Nếu chưa có project hoặc thiếu quyền, hãy yêu cầu quản trị viên cung cấp project thực hành và vai trò phù hợp; không tự mở rộng quyền.

## 4. Thao tác cơ bản trên Google Cloud Console

Mở [Google Cloud Console](https://console.cloud.google.com/) và đăng nhập bằng tài khoản được cấp quyền. Tên mục và vị trí menu có thể thay đổi theo phiên bản giao diện; thanh tìm kiếm ở phía trên là cách nhanh để tìm đúng dịch vụ.

### 4.1. Chọn project

1. Tìm **project selector** ở thanh trên cùng; mở danh sách project.
2. Chọn project dành cho bài thực hành.
3. Vào **Dashboard** hoặc khu vực thông tin project để xác nhận **project ID** và **project number**.
4. Ghi lại project ID. Kiểm tra lại lựa chọn này trước mọi thao tác tạo/xóa tài nguyên.

Nếu danh sách không chứa project mong muốn, bạn có thể đang đăng nhập sai tài khoản, project chưa được chia sẻ hoặc quyền của bạn chưa đủ để thấy tài nguyên.

### 4.2. Làm quen các khu vực quan trọng

| Khu vực cần tìm trong Console | Bạn quan sát điều gì? | Liên hệ với các bài học tiếp theo |
|---|---|---|
| **IAM & Admin → IAM** | Principal và role được cấp trên project | Quyền tối thiểu, danh tính người dùng và service account |
| **APIs & Services** | API đang bật, thư viện API, quota và thông tin sử dụng | Điều kiện để thao tác dịch vụ và điều tra lỗi API |
| **Billing** | Project đã liên kết thanh toán hay chưa; chi phí và ngân sách nếu được phép | Theo dõi chi phí, budget, cảnh báo |
| **VPC network** | Mạng, subnet, firewall và các tuyến liên quan | Tổ chức kết nối private/public |
| **Compute Engine → VM instances** | Các VM đã có và vị trí triển khai | Mô hình IaaS |
| **Kubernetes Engine** | Cluster GKE (nếu có) | Vận hành container với Kubernetes |
| **Cloud Run** | Service/job và thông tin triển khai (nếu có) | Nền tảng serverless container |
| **Cloud Storage → Buckets** | Bucket, vị trí, quyền và cấu hình lưu trữ | Object storage |
| **SQL** | Instance Cloud SQL nếu project đã sử dụng | Dữ liệu quan hệ được quản lý |
| **Logging / Monitoring** | Log, metric, dashboard và cảnh báo | Giám sát độ tin cậy và vận hành |

Những trang này có thể trống trong một project mới. **Trang trống không nhất thiết là lỗi:** có thể chưa có tài nguyên, API chưa bật, bộ lọc location chưa đúng hoặc quyền xem chưa đủ.

### 4.3. Quan sát IAM và API

Trong **IAM**, phân biệt:

- **Principal**: người dùng, nhóm, service account hoặc danh tính được cấp quyền.
- **Role**: tập quyền (permissions) mà principal có trong phạm vi nhất định.
- **Resource scope**: tổ chức, folder, project hoặc tài nguyên cụ thể nơi role được gán.
- **Policy/organization policy**: các ràng buộc quản trị có thể chặn thao tác ngay cả khi một role tưởng như cho phép.

Trong **APIs & Services**, nhận diện API đã bật và API chưa bật. Bật API là **một thay đổi cấu hình project** và có thể yêu cầu quyền riêng; bài thực hành đầu tiên chỉ quan sát trạng thái.

### 4.4. Quan sát Billing an toàn

Nếu được cấp quyền, xem project liên kết với billing account nào và có **budget/alert** hay chưa. Budget alert giúp phát hiện chi phí nhưng **không mặc định là cơ chế tự động dừng chi tiêu**. Việc tạo VM, cơ sở dữ liệu, bucket, public IP hay bật các workload có thể phát sinh chi phí tùy cấu hình và thời gian sử dụng.

Bạn không cần tạo tài nguyên trả phí để hoàn tất bài làm quen này.

## 5. Khởi động Cloud Shell

Từ Console, chọn nút **Activate Cloud Shell** (biểu tượng terminal ở phía trên giao diện). Chấp nhận bước cấp phép/khởi tạo nếu hệ thống yêu cầu theo chính sách tổ chức. Cửa sổ terminal sẽ xuất hiện trong trình duyệt.

Cloud Shell thường cung cấp một môi trường Linux với Google Cloud CLI cùng nhiều công cụ phát triển quen thuộc. Danh sách và phiên bản công cụ có thể thay đổi, nên hãy kiểm tra trực tiếp.

~~~bash
pwd
echo "$HOME"
command -v gcloud
gcloud version
command -v git
git --version
~~~

**Giải thích:**

- `pwd`: vị trí thư mục làm việc hiện tại.
- `$HOME`: đường dẫn home của người dùng trong phiên shell.
- `command -v`: tìm vị trí thực thi của công cụ.
- `gcloud version`: xác nhận phiên bản Google Cloud CLI.
- `git --version`: xác nhận công cụ Git.

Các lệnh này chỉ quan sát môi trường và **không tạo tài nguyên Google Cloud**.

### 5.1. Terminal, Editor và Web Preview

- **Terminal:** phù hợp cho `gcloud`, `git`, kiểm tra cấu hình, chạy tiện ích và script.
- **Cloud Shell Editor:** chỉnh sửa mã nguồn/cấu hình bằng giao diện editor gắn với môi trường Cloud Shell; có thể mở từ giao diện Cloud Shell tùy phiên bản.
- **Web Preview:** xem ứng dụng web đang chạy trên cổng tương thích trong môi trường phát triển; đây là công cụ xem thử, không thay thế triển khai production.

Một vòng làm việc điển hình: lấy mã từ Git vào Cloud Shell, sửa trong Editor, chạy kiểm tra, xem preview rồi commit/push về kho theo quyền được cấp. Không lưu token, mật khẩu hoặc khóa riêng vào repo.

### 5.2. Phiên làm việc và tệp

Phân biệt hai loại dữ liệu:

| Nơi lưu | Cách sử dụng | Cần chú ý |
|---|---|---|
| **Home của Cloud Shell** | Mã nguồn và cấu hình phục vụ thực hành; được lưu giữa phiên theo chính sách dịch vụ | Có quota, điều kiện lưu giữ, không phải backup lâu dài |
| **Thư mục tạm và tiến trình của phiên VM** | Build, cache, dịch vụ thử nghiệm | Có thể mất khi VM bị khởi tạo lại hoặc phiên chấm dứt |
| **Cloud Storage/Git/Artifact Registry** | Lưu trữ có chủ đích cho object, source và artifact | Có IAM, vòng đời, mức phí và quy tắc quản trị riêng |

Nếu Shell đột ngột mất kết nối, ưu tiên kiểm tra trạng thái phiên và khôi phục từ Git. Không kết luận tài nguyên Google Cloud đã bị xóa chỉ vì terminal đóng.

## 6. Làm việc với `gcloud`: tài khoản, project và cấu hình

Cloud Shell thường đã được tích hợp cơ chế xác thực cho người dùng đăng nhập; bạn không cần chạy lệnh đăng nhập lặp lại trong mỗi phiên bình thường. Tuy nhiên, **xác thực** (bạn là ai) và **ủy quyền** (bạn được làm gì) là hai việc khác nhau.

### 6.1. Kiểm tra phiên hiện tại

~~~bash
gcloud auth list
gcloud config list
gcloud config get-value project
gcloud config configurations list
~~~

Ý nghĩa:

- `gcloud auth list` cho biết các tài khoản đã có thông tin xác thực trong CLI và tài khoản đang được chọn. Đừng đăng ảnh chụp màn hình chứa email cá nhân hoặc thông tin nhạy cảm khi không cần thiết.
- `gcloud config list` hiển thị thuộc tính cấu hình đang có như account, project và default region/zone nếu được thiết lập.
- `gcloud config get-value project` in ra project ID mặc định; nếu chưa cấu hình có thể trả về trạng thái chưa đặt.
- `gcloud config configurations list` liệt kê các cấu hình CLI, hữu ích khi làm việc với nhiều môi trường.

**Quan trọng:** Project được chọn trong Console và project mặc định của CLI có thể không khớp trong một số phiên hoặc sau khi thay đổi cấu hình. Hãy xác minh **cả hai** trước khi thực hiện lệnh ghi tài nguyên.

### 6.2. Chỉ định project rõ ràng

Khi đã biết project ID phù hợp, bạn có hai cách:

~~~bash
# Cách A: chọn project mặc định cho cấu hình CLI hiện tại.
gcloud config set project YOUR_PROJECT_ID

# Cách B: chỉ định project riêng cho lệnh cụ thể.
gcloud projects describe YOUR_PROJECT_ID \
  --project=YOUR_PROJECT_ID
~~~

Thay `YOUR_PROJECT_ID` bằng project ID thật; không dùng nguyên chuỗi minh họa.

`gcloud config set project` chỉ thay đổi **cấu hình CLI**, không tự tạo hay đổi tên project. Với script vận hành nhiều môi trường, truyền `--project` trong từng lệnh thường giúp tránh nhầm lẫn hơn so với dựa vào cấu hình ngầm.

Bạn cũng có thể đặt cấu hình mặc định cho các dịch vụ vùng khi cần:

~~~bash
# Minh họa, chỉ thay đổi cấu hình CLI.
gcloud config set compute/region asia-southeast1
gcloud config set compute/zone asia-southeast1-a
~~~

Ở đây `asia-southeast1` là vùng Singapore; `asia-southeast1-a` là một zone trong vùng đó. Vị trí thực tế phải chọn theo yêu cầu độ trễ, dữ liệu, dịch vụ sẵn có, khả năng chịu lỗi và chi phí. Nhiều lệnh Cloud Run hoặc dịch vụ khác vẫn yêu cầu `--region`/`--location` riêng.

### 6.3. Quan sát project bằng lệnh chỉ đọc

~~~bash
# Các project mà danh tính hiện tại có thể liệt kê.
gcloud projects list \
  --format="table(projectId,name,projectNumber)"

# Thông tin project đang thực hành.
gcloud projects describe YOUR_PROJECT_ID \
  --format="yaml(projectId,name,projectNumber,lifecycleState)"

# Các API đang bật trong project (nếu có quyền xem).
gcloud services list \
  --enabled \
  --project=YOUR_PROJECT_ID \
  --format="table(config.name)"
~~~

Các lệnh trên không tạo VM, API hoặc database. Kết quả `projects list` chỉ phản ánh phạm vi mà danh tính hiện tại được phép liệt kê; không nhất thiết bao gồm mọi project trong một tổ chức.

Nếu `services list` báo `PERMISSION_DENIED`, bạn cần kiểm tra quyền liệt kê dịch vụ; không nên tự cấp role quản trị rộng để “sửa nhanh”.

## 7. Từ Console sang Cloud Shell: cùng một tài nguyên, hai góc nhìn

Giả sử bạn đã chọn `YOUR_PROJECT_ID` trong Console và muốn biết project có VM hoặc Cloud Run service hay không.

| Nhiệm vụ | Trong Console | Trong Cloud Shell |
|---|---|---|
| Xem danh tính và quyền truy cập | **IAM & Admin → IAM** | `gcloud auth list` chỉ xem danh tính CLI; không thay thế việc xem policy IAM |
| Xem project hiện tại | Project selector / dashboard | `gcloud config get-value project` và `gcloud projects describe` |
| Xem API đã bật | **APIs & Services → Enabled APIs** | `gcloud services list --enabled --project=YOUR_PROJECT_ID` |
| Xem VM | **Compute Engine → VM instances** | `gcloud compute instances list --project=YOUR_PROJECT_ID` |
| Xem Cloud Run service | **Cloud Run → Services** | `gcloud run services list --project=YOUR_PROJECT_ID --region=asia-southeast1` |
| Quan sát log | **Logging → Logs Explorer** | `gcloud logging read` với filter và project phù hợp |
| Kiểm tra chi phí | **Billing → Reports/Budgets** | Console dễ quan sát hơn trong bài mở đầu; quyền xem billing có thể độc lập với project |

Hai lệnh thực hành sau đây chỉ **liệt kê** tài nguyên đã có:

~~~bash
gcloud compute instances list \
  --project=YOUR_PROJECT_ID

gcloud run services list \
  --project=YOUR_PROJECT_ID \
  --region=asia-southeast1
~~~

Nếu một dịch vụ chưa có tài nguyên, bạn sẽ thấy danh sách trống. Nếu API chưa được bật hoặc quyền chưa đủ, lệnh có thể báo lỗi; đó là cơ hội phân biệt **API**, **IAM** và **chọn nhầm project**, thay vì suy đoán dự án bị hỏng.

### 7.1. Bộ lọc và cách đọc kết quả

Google Cloud CLI hỗ trợ định dạng và bộ lọc đầu ra để đọc kết quả nhanh hơn:

~~~bash
# Chỉ xem các cột cần thiết của danh sách project.
gcloud projects list \
  --format="table(projectId,name,projectNumber)"

# Đầu ra JSON phù hợp khi cần tích hợp script.
gcloud projects describe YOUR_PROJECT_ID \
  --format=json
~~~

Khi dùng script, nên dựa vào trường dữ liệu có cấu trúc (`--format=json` hoặc biểu thức format rõ ràng) thay vì đọc các cột in tự do. Có thể khám phá tham số lệnh với:

~~~bash
gcloud help
gcloud projects --help
gcloud run services list --help
~~~

`--help` hiển thị trợ giúp mà không thay đổi tài nguyên. Tên lệnh và cờ có thể thay đổi khi CLI được cập nhật; kiểm tra tài liệu/`--help` của phiên bản đang dùng.

## 8. Thực hành có hướng dẫn: khám phá project mà không tạo tài nguyên

**Mục tiêu:** hoàn thành một vòng xác minh Console ↔ Cloud Shell bằng thao tác chỉ đọc. Nếu không đủ quyền ở một bước, ghi lại kết quả và lý do; không cần xin role rộng chỉ để hoàn tất bài tập.

### Bước 1 — Xác minh trên Console

1. Đăng nhập Console và chọn project sandbox được giao.
2. Ghi lại **project name**, **project ID** và **project number** từ trang thông tin project.
3. Truy cập **IAM** để quan sát cách principal được gán role; không chỉnh sửa policy.
4. Vào **APIs & Services** để xem danh sách API đã bật.
5. Kiểm tra **Compute Engine**, **Cloud Run** hoặc **Cloud Storage** để xem có tài nguyên nào đã tồn tại.

### Bước 2 — Mở Cloud Shell và đối chiếu danh tính

~~~bash
gcloud version
gcloud auth list
gcloud config get-value project
~~~

So sánh tài khoản hiện tại và project mặc định của CLI với thông tin Console. Nếu project chưa đúng, bạn có thể dùng `--project=YOUR_PROJECT_ID` cho các lệnh tiếp theo thay vì sửa cấu hình toàn cục.

### Bước 3 — Xác nhận project qua API

~~~bash
gcloud projects describe YOUR_PROJECT_ID \
  --format="table(projectId,name,projectNumber,lifecycleState)"
~~~

Đối chiếu **project ID** và **project number** với Console. Nếu thông tin không khớp, dừng các lệnh có tác động và xác nhận lại đúng project.

### Bước 4 — Quan sát dịch vụ hiện có

~~~bash
gcloud services list \
  --enabled \
  --project=YOUR_PROJECT_ID \
  --format="table(config.name)"

gcloud run services list \
  --project=YOUR_PROJECT_ID \
  --region=asia-southeast1
~~~

So sánh danh sách API và dịch vụ với các trang tương ứng. Lưu ý Cloud Run là tài nguyên theo region: không tìm thấy service ở `asia-southeast1` **không chứng minh** rằng project không có Cloud Run service ở region khác.

### Bước 5 — Nhìn rộng hơn về chi phí và độ tin cậy

Trong Console, tìm **Billing → Budgets**, **Logging → Logs Explorer** và **Monitoring**. Quan sát các tín hiệu nếu project đã có workload. Không kết luận hệ thống thiếu monitoring khi project mới trống hoặc quyền của bạn chỉ cho phép xem một phần.

### Bước 6 — Ghi nhận kết quả

Bạn có thể dùng mẫu kiểm tra ngắn này:

| Mục đã xác minh | Giá trị cần ghi | Kết quả |
|---|---|---|
| Project ID của Console | Project ID thật | Trùng/khác CLI |
| Project ID của `gcloud` | `gcloud config get-value project` | Đúng/chưa đặt/cần sửa |
| Danh tính CLI | Tài khoản active từ `gcloud auth list` | Có quyền/không đủ quyền |
| Project number | Từ dashboard và `projects describe` | Trùng/khác |
| API đang bật | Tên 2–3 API đã thấy | Xem được/thiếu quyền |
| Cloud Run ở region được kiểm tra | Danh sách service hoặc trống | Thành công/lỗi có giải thích |
| Billing và giám sát | Đã tìm được trang tương ứng | Xem được/thiếu quyền |

Kết thúc bài thực hành khi bạn giải thích được dữ liệu đang xem thuộc **project nào**, truy vấn đang chạy với **danh tính nào** và có **tác động gì**.

## 9. IAM, bảo mật và các lưu ý trong môi trường học

### 9.1. Nguyên tắc quyền tối thiểu

- Chỉ dùng tài khoản và project được phép; tách sandbox khỏi production nếu có thể.
- Cấp **role phù hợp với nhiệm vụ**; không cấp `Owner`/`Editor` chỉ để xử lý lỗi lệnh chỉ đọc.
- Dùng **service account** thích hợp cho ứng dụng/CI; không mặc định dùng danh tính cá nhân cho workload production.
- Không chép access token, service account key, mật khẩu hoặc secret vào tệp thực hành, Git và ảnh chụp màn hình.
- Kiểm tra project và region trước lệnh tạo, cập nhật hoặc xóa tài nguyên.

Trong Cloud Shell, phiên CLI tích hợp với tài khoản của bạn; việc chạy lệnh vẫn chịu ràng buộc IAM. Một tài khoản xem được trang project chưa chắc có quyền tạo VM, bật API hay quản lý billing.

### 9.2. Phân biệt ba nhóm thao tác

| Nhóm thao tác | Ví dụ | Mức ảnh hưởng |
|---|---|---|
| **Quan sát** | `gcloud projects describe`, `gcloud services list`, xem dashboard | Thường không thay đổi tài nguyên; vẫn cần quyền đọc |
| **Đổi cấu hình CLI cục bộ** | `gcloud config set project`, đổi region mặc định | Đổi ngữ cảnh lệnh sau đó, không tự sửa project trên cloud |
| **Thay đổi cloud** | `gcloud services enable`, `gcloud run deploy`, tạo VM/bucket, sửa IAM | Có thể thay đổi bảo mật, quota hoặc phát sinh chi phí |

Khi chuyển từ khám phá sang triển khai Compute Engine, GKE hay Cloud Run, hãy xác định rõ nhóm thứ ba và quy trình kiểm soát thay đổi của tổ chức.

### 9.3. Cloud Shell và Application Default Credentials

`gcloud` sử dụng thông tin xác thực do CLI quản lý. **Application Default Credentials (ADC)** là cơ chế tìm thông tin xác thực của các thư viện ứng dụng. Hai luồng có quan hệ nhưng không nên xem là hoàn toàn đồng nhất. Khi viết ứng dụng dùng client library hoặc chạy mã trên Cloud Run/GKE/VM, cần chọn cơ chế danh tính phù hợp, tránh đưa key JSON vào source code.

Trong bài làm quen này, bạn chỉ cần danh tính đã có trong Cloud Shell để thực hiện các lệnh truy vấn. Việc cấp quyền cho ứng dụng sẽ được xem xét khi học IAM và triển khai workload.

## 10. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra an toàn |
|---|---|---|
| Không thấy project trong Console | Sai tài khoản, thiếu quyền hoặc project chưa được chia sẻ | Kiểm tra tài khoản đăng nhập, project selector và hỏi quản trị project |
| `gcloud config get-value project` chưa có giá trị | Chưa chọn project mặc định trong CLI | Truyền `--project=YOUR_PROJECT_ID` hoặc đặt cấu hình sau khi xác nhận ID |
| `PERMISSION_DENIED` | Danh tính thiếu quyền IAM hoặc bị chính sách tổ chức chặn | Kiểm tra `gcloud auth list`, đúng project và role cụ thể cần thiết |
| `API has not been used / is disabled` | API dịch vụ chưa được bật | Quan sát **APIs & Services**; chỉ bật khi được phép và có nhu cầu |
| Không thấy VM/service như trong Console | Nhầm project, region, bộ lọc hoặc quyền liệt kê | So sánh project ID và location giữa hai công cụ |
| `NOT_FOUND` hoặc project không hợp lệ | Gõ sai project ID, dùng project name thay ID hoặc thiếu quyền truy cập | Dùng `gcloud projects list`/`describe` và đối chiếu dashboard |
| Không dùng được Cloud Shell | Chính sách tổ chức, quyền truy cập, quota hoặc lỗi phiên | Kiểm tra thông báo Console; liên hệ quản trị hoặc thử phiên mới khi phù hợp |
| Bị ngắt terminal, tiến trình thử nghiệm dừng | Phiên Cloud Shell đã hết hoặc VM thay đổi | Khởi động lại shell; phục hồi code từ Git, kiểm tra dữ liệu đã lưu ở nơi bền vững |
| Tài nguyên tạo ra phát sinh phí ngoài dự kiến | Có workload/DB/IP/storage hoặc cấu hình mở rộng vẫn hoạt động | Xem Billing, nhãn tài nguyên, budget, usage và xử lý tài nguyên không cần thiết |

Một số API trả lỗi tương tự nhau khi thiếu quyền hoặc không tìm thấy tài nguyên. **Đừng suy ra chắc chắn tài nguyên không tồn tại chỉ từ một thông báo lỗi.** Xác minh danh tính, project, location, API và role theo thứ tự.

## 11. Liên hệ với việc triển khai Google Cloud thực tế

Bạn sẽ dùng Console và Cloud Shell xuyên suốt mô-đun:

| Chủ đề tiếp theo | Dùng Console để | Dùng Cloud Shell/CLI để |
|---|---|---|
| **Project và IAM** | Xem cấu trúc project, principal và role | Kiểm tra project, chính sách và cấu hình CLI với quyền phù hợp |
| **VPC** | Quan sát subnet, route và firewall | Liệt kê cấu hình mạng, hỗ trợ script và kiểm tra trạng thái |
| **Compute Engine** | Xem VM, boot disk, zone, metric | Tự động hóa truy vấn, tạo/cấu hình VM khi được phép |
| **GKE** | Xem cluster và workload | Dùng `gcloud` lấy thông tin cluster, `kubectl` khi đã được cấp quyền |
| **Cloud Run** | Xem service, revision, traffic và log | Triển khai container, kiểm tra service hoặc job bằng CLI |
| **Storage / Database** | Xem bucket, instance, cấu hình backup | Quản lý cấu hình và vận hành bằng lệnh phù hợp |
| **Vận hành / chi phí** | Xem dashboard, log, alert và budget | Tạo thao tác lặp lại, kiểm tra cấu hình và hỗ trợ pipeline |

Ví dụ một đội phát triển triển khai API trên Cloud Run có thể bắt đầu trong Console để kiểm tra project, IAM và budget; dùng Cloud Shell để chạy lệnh thử trong sandbox; chuyển cùng nguyên tắc CLI sang CI/CD với service account và quyền tối thiểu; cuối cùng trở lại Console để kiểm tra log, độ trễ, lỗi và chi phí.

Cloud Shell rất hữu ích cho bước học và thử nghiệm, nhưng **pipeline production** nên chạy từ môi trường CI/CD được quản lý với danh tính riêng, khả năng kiểm soát phiên bản, phê duyệt và nhật ký thay đổi.

## 12. Bài tập tự đánh giá

1. **Một project có tên `Training` và project ID `gcp-training-12345`.** Khi chạy lệnh `gcloud`, bạn nên dùng giá trị nào cho `--project`? Vì sao?
2. **Bạn chọn project A trong Console nhưng CLI trả về project B.** Bạn sẽ kiểm tra và sửa ngữ cảnh lệnh ra sao?
3. **Cloud Run page trong Console không có service ở vùng Singapore.** Có thể kết luận cả project chưa dùng Cloud Run không? Cần kiểm tra gì thêm?
4. **Đăng nhập thành công nhưng `gcloud services list` bị từ chối.** Đây nhất thiết là lỗi xác thực hay có thể là lỗi ủy quyền?
5. **Bạn muốn chạy API lâu dài cho người dùng thật.** Vì sao không nên dùng Cloud Shell? Những dịch vụ nào trong phạm vi mô-đun phù hợp hơn?
6. **Tại sao đã thiết lập budget alert vẫn phải theo dõi chi phí?** Chỉ ra khác biệt giữa cảnh báo và giới hạn chi tiêu.
7. **Tại sao nên xác nhận project ID, danh tính và region trước một lệnh triển khai?** Nêu một hậu quả của việc chọn sai từng yếu tố.

**Gợi ý đáp án:** (1) Dùng project ID; (2) so sánh selector và `gcloud config get-value project`, truyền `--project` hoặc cập nhật cấu hình CLI; (3) không, kiểm tra region khác và quyền; (4) thường cần xác minh IAM/organization policy; (5) Cloud Shell là môi trường tương tác, xem Cloud Run, GKE hoặc Compute Engine theo nhu cầu; (6) budget alert không mặc định chặn hóa đơn; (7) nhầm project có thể đụng production, sai danh tính có thể vi phạm quyền, sai region ảnh hưởng độ trễ, lưu trú dữ liệu và chi phí.

## 13. Checklist hoàn thành

- [ ] Truy cập đúng Google Cloud Console và chọn được project sandbox.
- [ ] Phân biệt project name, project ID và project number.
- [ ] Tìm được các mục IAM, APIs & Services, Billing, Compute Engine, Cloud Run, Logging và Monitoring.
- [ ] Mở được Cloud Shell, biết dùng terminal, editor và hiểu giới hạn phiên làm việc.
- [ ] Chạy và giải thích được `gcloud auth list`, `gcloud config list` và `gcloud projects describe`.
- [ ] Đối chiếu đúng project giữa Console và CLI; hiểu cách dùng `--project` và `--region`.
- [ ] Thực hiện được ít nhất một phép quan sát API hoặc tài nguyên chỉ đọc.
- [ ] Giải thích được nguyên tắc quyền tối thiểu, ranh giới môi trường và nguy cơ chi phí.

**Điểm cần nhớ:** Console giúp bạn **nhìn thấy** tài nguyên và chính sách; Cloud Shell giúp bạn **thao tác bằng dòng lệnh**; `gcloud` nối các thao tác đó với API Google Cloud. Trước mọi thay đổi thực tế, hãy biết rõ **ai đang thực hiện**, **trên project nào**, **tại location nào** và **thao tác ảnh hưởng đến điều gì**.
