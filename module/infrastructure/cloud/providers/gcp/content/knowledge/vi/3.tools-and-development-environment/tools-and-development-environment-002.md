# Cài đặt và cấu hình Google Cloud CLI

> **Chương:** Công cụ và môi trường GCP  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

**Google Cloud CLI** là bộ công cụ dòng lệnh để làm việc với tài nguyên và dịch vụ Google Cloud. Thay vì chỉ thao tác trên Google Cloud Console, kỹ sư có thể sử dụng lệnh để kiểm tra project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; kết hợp các lệnh này trong script và quy trình triển khai. Đây là công cụ nền tảng trong quá trình lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cũng như chi phí.

Bài học hướng dẫn cài đặt và cấu hình CLI trên máy cá nhân, chọn đúng tài khoản/project/vùng tài nguyên, phân biệt đăng nhập cho CLI với thông tin xác thực của ứng dụng, và xây dựng thói quen kiểm tra môi trường trước khi chạy lệnh có tác động đến hệ thống.

**Kết quả học tập:** Sau bài này, người học có thể:

1. Cài đặt Google Cloud CLI trên Windows, macOS hoặc Linux và xác minh cài đặt.
2. Chạy `gcloud init`, đăng nhập và đặt project/region/zone mặc định.
3. Quản lý nhiều cấu hình cho các môi trường như development và production.
4. Phân biệt xác thực lệnh `gcloud`, Application Default Credentials (ADC), và danh tính workload.
5. Sử dụng những lệnh đọc tài nguyên, tra cứu trợ giúp và xử lý lỗi cấu hình thường gặp.
6. Cập nhật CLI và quản lý component phù hợp với phương thức cài đặt.

## 1. Google Cloud CLI gồm những gì?

Lệnh chính là `gcloud`. Đây là một phần của Google Cloud CLI, cung cấp các nhóm lệnh theo tài nguyên hoặc dịch vụ.

| Công cụ | Vai trò | Ví dụ |
| --- | --- | --- |
| `gcloud` | Cấu hình môi trường và quản lý tài nguyên GCP | `gcloud projects list`, `gcloud run services list` |
| `gcloud storage` | Làm việc với Cloud Storage | `gcloud storage buckets list` |
| `bq` | Công cụ dòng lệnh cho BigQuery | `bq ls` |
| `gsutil` | Công cụ Cloud Storage truyền thống | `gsutil ls`; các thao tác mới nên tham khảo `gcloud storage` |
| `kubectl` | Tương tác Kubernetes API sau khi cấu hình kết nối cluster | `kubectl get pods` |

`kubectl` có thể cần cài riêng; việc cài Google Cloud CLI bằng trình quản lý gói Linux không đảm bảo đã có mọi component mở rộng. Công cụ CLI là *client*: mỗi lệnh gửi yêu cầu đến API tương ứng. Đã cài CLI **không có nghĩa** tài khoản có quyền với mọi tài nguyên, các API đã được bật hoặc hệ thống đã bật tính phí.

### 1.1. Một lệnh `gcloud` được cấu thành như thế nào?

~~~text
gcloud <nhóm> <tài_nguyên> <hành_động> [đối_số] [--cờ=giá_trị]
       └──────────────┬──────────────┘
               tên lệnh đầy đủ
~~~

Ví dụ:

~~~bash
# Liệt kê các VM trong project được chọn
gcloud compute instances list

# Chỉ định project rõ ràng cho riêng lệnh này
gcloud compute instances list --project=PROJECT_ID

# Tra cứu tùy chọn và ví dụ
gcloud compute instances list --help
~~~

Các cờ thông dụng:

- `--project=PROJECT_ID`: chỉ định project cho một lần gọi lệnh.
- `--region=REGION` và `--zone=ZONE`: chọn vùng/khu vực triển khai khi nhóm lệnh hỗ trợ.
- `--format=...`: chọn cấu trúc dữ liệu xuất ra, chẳng hạn `table(...)`, `value(...)`, `json`.
- `--filter=...`: lọc danh sách tài nguyên.
- `--configuration=NAME`: sử dụng một cấu hình được đặt tên cho lệnh hiện tại.
- `--help`: mở tài liệu cú pháp ngay trong terminal.

Không phải lệnh nào cũng chấp nhận cùng một tập cờ dịch vụ. Hãy xem trợ giúp của lệnh cụ thể trước khi tự động hóa.

## 2. Chuẩn bị trước khi cài đặt

Bạn cần:

- **Máy tính và terminal:** PowerShell hoặc Command Prompt trên Windows; Terminal/zsh trên macOS; Bash hoặc shell tương đương trên Linux.
- **Kết nối Internet:** để tải gói cài và gọi API Google Cloud; proxy hoặc firewall doanh nghiệp có thể yêu cầu cấu hình riêng.
- **Tài khoản phù hợp:** Google Account hoặc danh tính do tổ chức quản lý, được cấp quyền IAM với tài nguyên cần thao tác.
- **Project ID:** ví dụ minh họa `demo-gcp-dev`; **Project ID** dùng trong phần lớn lệnh, khác với tên hiển thị và project number.
- **Billing nếu bài thực hành sử dụng tài nguyên tính phí:** một số thao tác đọc và cấu hình CLI không cần tạo tài nguyên; khi triển khai Compute Engine, Cloud SQL hoặc dịch vụ khác phải xem điều kiện bật API, billing và chi phí.

Để chỉ cài đặt và kiểm tra `gcloud --version`, bạn chưa cần một project. Để làm việc với project hiện có, cần có quyền IAM phù hợp. Không tự tạo project hoặc bật dịch vụ có tính phí trên môi trường chung nếu bài thực hành chưa yêu cầu.

### 2.1. Máy cục bộ hay Cloud Shell?

| Môi trường | Khi nào chọn? | Điểm cần nhớ |
| --- | --- | --- |
| **Cài local** | Phát triển trên máy cá nhân, kết hợp IDE, script và hệ thống mã nguồn | Tự quản phiên bản, đường dẫn executable, cấu hình và credential trên máy |
| **Google Cloud Shell** | Muốn thực hành nhanh trên môi trường terminal do Google cung cấp | CLI thường đã có sẵn; xác thực được tích hợp với phiên Cloud Shell; một số tùy chọn cấu hình CLI theo tab không được lưu lâu dài |
| **CI/CD runner** | Chạy tự động khi build/deploy | Cần cơ chế xác thực workload và cấu hình project rõ ràng; không sao chép thông tin đăng nhập của người dùng |

Tài liệu bên dưới tập trung vào **máy local**. Với Cloud Shell, có thể bỏ qua phần cài đặt và bắt đầu kiểm tra `gcloud config list`.

## 3. Cài đặt trên Windows

1. Mở trang chính thức [Install the Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk), chọn phần **Windows**, rồi tải trình cài đặt từ Google.
2. Chạy installer, xác nhận nhà phát hành **Google LLC**, làm theo hướng dẫn. Bản cài đặt thường đi kèm Python cần thiết; sử dụng Python được đóng gói nếu không có nhu cầu cấu hình Python riêng.
3. Cho phép thêm CLI vào `PATH` và bật công cụ trong terminal nếu installer có tùy chọn tương ứng.
4. Mở **cửa sổ PowerShell mới** sau khi hoàn tất.

Kiểm tra trong PowerShell:

~~~powershell
# Tìm lệnh trong PATH
Get-Command gcloud

# Xem phiên bản đã cài
gcloud version

# Xem danh sách lệnh cấp cao
gcloud help
~~~

**Kết quả mong đợi:** `Get-Command` tìm được executable hoặc command wrapper của `gcloud`; lệnh `gcloud version` in thông tin phiên bản, không báo `command not found`.

Nếu PowerShell không tìm thấy `gcloud`, thử terminal do installer tạo hoặc đóng và mở lại terminal. Kiểm tra tùy chọn bổ sung đường dẫn vào `PATH` trước khi cài lại.

## 4. Cài đặt trên macOS

Google cung cấp gói cài đặt cho các kiến trúc máy khác nhau. Đầu tiên xác định kiến trúc:

~~~bash
uname -m
~~~

Các máy Apple silicon thường trả về `arm64`; máy Intel thường trả về `x86_64`. Trên trang [Install the Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk), chọn đúng gói macOS hoặc dùng trình cài đặt tương tác.

Ví dụ lưu script chính thức về máy và chạy bằng Bash:

~~~bash
curl -fsSL https://sdk.cloud.google.com -o install-gcloud.sh
bash install-gcloud.sh
~~~

Trong quá trình cài, chọn đường dẫn cài đặt và cho phép cập nhật `PATH`/command completion theo nhu cầu. Sau đó mở shell mới hoặc khởi động lại shell:

~~~bash
exec -l "$SHELL"
gcloud version
~~~

Trình cài đặt có thể cài hoặc chọn bản Python hỗ trợ phù hợp. Nếu máy đã cấu hình nhiều phiên bản Python, xem [gcloud topic startup](https://docs.cloud.google.com/sdk/gcloud/reference/topic/startup) để quản lý interpreter. Không nên sửa biến môi trường Python một cách tùy tiện chỉ để giải quyết lỗi `gcloud`.

## 5. Cài đặt trên Linux

### 5.1. Debian và Ubuntu bằng APT

Trên phiên bản Debian/Ubuntu còn được hỗ trợ, có thể thêm kho gói Google Cloud chính thức rồi cài package `google-cloud-cli`.

~~~bash
# 1. Cài tiện ích cần thiết
sudo apt-get update
sudo apt-get install ca-certificates gnupg curl

# 2. Cài khóa ký repository
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
  | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg

# 3. Thêm nguồn package (thực hiện một lần)
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
  | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list

# 4. Cài đặt CLI
sudo apt-get update
sudo apt-get install google-cloud-cli

# 5. Kiểm tra
gcloud version
~~~

Nếu môi trường đã cấu hình repository, kiểm tra và tránh thêm mục trùng. Các bản phân phối Linux khác có phương pháp riêng (RPM/DNF hoặc gói tar); xem hướng dẫn chính thức để chọn nguồn gói tương ứng.

### 5.2. Cài bằng gói nén hoặc trình cài đặt

Với Linux không dùng APT, có thể tải gói `tar.gz` phù hợp kiến trúc CPU từ trang cài đặt, giải nén và chạy `./google-cloud-sdk/install.sh`. Ví dụ sau chỉ minh họa **sau khi đã tải và giải nén đúng gói**:

~~~bash
./google-cloud-sdk/install.sh
gcloud version
~~~

Cách cài quyết định cách cập nhật và cách thêm component sau này. Hãy ghi lại bạn đã cài bằng APT/DNF, installer hay archive.

## 6. Xác minh CLI sau cài đặt

Các lệnh dưới đây chỉ tra cứu thông tin, không tạo tài nguyên GCP:

~~~bash
# Phiên bản CLI và các component
gcloud version

# Thông tin môi trường CLI
gcloud info

# Đường dẫn thư mục cấu hình đang được sử dụng
gcloud info --format="value(config.paths.global_config_dir)"

# Trợ giúp cho nhóm lệnh
gcloud help
gcloud help config
~~~

**Ba lớp cần tách biệt:**

1. **Cài đặt:** Hệ điều hành nhận lệnh `gcloud`.
2. **Xác thực:** CLI có thông tin đăng nhập để gọi API.
3. **Ủy quyền:** Tài khoản có IAM permissions cần thiết trên project/tài nguyên.

Một máy có thể vượt qua bước 1 nhưng thất bại ở bước 2 hoặc 3. Vì thế `gcloud version` thành công chưa chứng minh rằng người dùng có thể liệt kê VM hay triển khai ứng dụng.

## 7. Khởi tạo cấu hình bằng `gcloud init`

Sau khi cài xong:

~~~bash
gcloud init
~~~

Trình hướng dẫn thường thực hiện:

1. Chọn hoặc tạo một **named configuration**.
2. Đăng nhập tài khoản Google nếu cần.
3. Chọn **Project ID** mặc định trong số những project tài khoản có thể truy cập, hoặc nhập trực tiếp.
4. Chọn region/zone mặc định cho Compute Engine nếu có bước hỏi và thông tin cần thiết.

Khi chạy trong môi trường terminal từ xa mà trình duyệt không mở trực tiếp được:

~~~bash
gcloud init --console-only
~~~

Lệnh hiển thị hướng dẫn xác thực qua trình duyệt thay vì tự cố mở cửa sổ trình duyệt trên máy từ xa. Đây là quy trình tương tác dành cho người dùng; với CI/CD, hãy dùng cơ chế xác thực workload.

Sau khi hoàn tất:

~~~bash
gcloud auth list
gcloud config list
gcloud config get-value project
~~~

Ví dụ minh họa (không phải kết quả cố định):

~~~text
[compute]
region = asia-southeast1
zone = asia-southeast1-a
[core]
account = engineer@example.com
project = demo-gcp-dev
~~~

Trong ví dụ, `asia-southeast1` là region Singapore. Hãy chọn region và zone dựa trên yêu cầu dữ liệu, độ trễ, dịch vụ có sẵn và chính sách của tổ chức, thay vì sao chép máy móc giá trị ví dụ.

## 8. Cấu hình project, region, zone và tài khoản

Có thể đặt từng thuộc tính mà không cần chạy lại toàn bộ `gcloud init`:

~~~bash
# Dùng Project ID (không phải display name)
gcloud config set project PROJECT_ID

# Giá trị mặc định cho lệnh có sử dụng Compute Engine region/zone
gcloud config set compute/region REGION
gcloud config set compute/zone ZONE

# Xem lại cấu hình hiện tại
gcloud config list
~~~

Ví dụ thực tế cho môi trường thử nghiệm tại Singapore:

~~~bash
gcloud config set project demo-gcp-dev
gcloud config set compute/region asia-southeast1
gcloud config set compute/zone asia-southeast1-a
~~~

Nếu máy đã đăng nhập nhiều tài khoản, xem tài khoản được lưu và chọn tài khoản đã đăng nhập:

~~~bash
gcloud auth list
gcloud config set account USER_EMAIL
~~~

**Lưu ý:** `gcloud config set account` không thay thế bước đăng nhập. Nếu `USER_EMAIL` chưa có credential hợp lệ, bạn cần chạy `gcloud auth login` cho tài khoản đó. Quyền đối với project phụ thuộc IAM, không phụ thuộc việc gán project vào cấu hình CLI.

### 8.1. Giá trị mặc định và cờ của từng lệnh

Giả sử cấu hình đang chọn `demo-gcp-dev`:

~~~bash
# Dùng project trong cấu hình hiện tại
gcloud projects describe demo-gcp-dev

# Lệnh này chỉ định project khác cho lần chạy hiện tại
gcloud run services list --project=demo-gcp-prod --region=asia-southeast1

# Kiểm tra lại: project mặc định vẫn là demo-gcp-dev
gcloud config get-value project
~~~

Cờ `--project` thường được ưu tiên so với project trong configuration cho lệnh đang chạy. Không thay đổi ngầm cấu hình trên máy chỉ vì đã dùng cờ. Với lệnh liên quan vùng tài nguyên, cung cấp rõ `--region` hoặc `--zone` giúp giảm nguy cơ thao tác sai vị trí.

### 8.2. Không phải mọi tài nguyên dùng cùng phạm vi

- **Project:** đơn vị quản lý tài nguyên, API, nhiều chính sách IAM và chi phí.
- **Region:** vị trí địa lý; Cloud Run và nhiều cơ sở dữ liệu sử dụng region khi tạo/liệt kê tài nguyên.
- **Zone:** khu vực bên trong region; nhiều lệnh Compute Engine gắn với zone.
- **Global:** một số tài nguyên VPC/Load Balancing có phạm vi toàn cục; `compute/region` và `compute/zone` không áp dụng giống nhau cho tất cả lệnh.

Thay đổi `compute/region` không chuyển tài nguyên hiện có sang vùng mới. Nó chỉ ảnh hưởng giá trị mặc định của các lệnh tương ứng.

## 9. Nhiều cấu hình cho development và production

Một cấu hình gồm các thuộc tính như account, project, region và zone. Khi làm việc với nhiều project, nên tạo các tên dễ nhận biết.

~~~bash
# Tạo profile phát triển
gcloud config configurations create dev
gcloud config configurations activate dev
gcloud config set project demo-gcp-dev
gcloud config set compute/region asia-southeast1

# Tạo profile production
gcloud config configurations create prod
gcloud config configurations activate prod
gcloud config set project demo-gcp-prod
gcloud config set compute/region asia-southeast1

# Xem tất cả cấu hình và cấu hình đang được chọn
gcloud config configurations list
~~~

Sau đó có thể chuyển qua lại:

~~~bash
gcloud config configurations activate dev
gcloud config list

# Chỉ chọn profile prod cho một lệnh, không đổi profile đang active
gcloud projects describe demo-gcp-prod --configuration=prod
~~~

| Cách chọn môi trường | Phạm vi áp dụng | Tình huống nên dùng |
| --- | --- | --- |
| `gcloud config configurations activate prod` | Các lệnh tiếp theo dùng profile active mới | Làm việc theo phiên trong một môi trường |
| `--configuration=prod` | Một lệnh cụ thể | Script hoặc kiểm tra có mục tiêu |
| `--project=demo-gcp-prod` | Một lệnh cụ thể | Thao tác trên tài nguyên thuộc project khác |
| `CLOUDSDK_ACTIVE_CONFIG_NAME` | Theo biến môi trường của phiên shell/process | Tự động hóa hoặc môi trường tách biệt |

**Giới hạn quan trọng:** Các profile `dev` và `prod` không tự động tạo một kho credential độc lập cho từng profile, không tạo hàng rào IAM và không ngăn thao tác nhầm production. Cần kiểm tra account, project, flags và quyền IAM, nhất là trước các lệnh `create`, `update`, `delete` hoặc `deploy`.

## 10. Phân biệt xác thực CLI và Application Default Credentials

Đây là điểm hay gây nhầm lẫn khi người học bắt đầu viết ứng dụng Java/Python/Node.js gọi API GCP.

| Tình huống | Cơ chế thường dùng | Lệnh / hành động |
| --- | --- | --- |
| Người dùng chạy lệnh `gcloud` trên máy | Credential của Google Cloud CLI | `gcloud init` hoặc `gcloud auth login` |
| Ứng dụng chạy local dùng Cloud Client Library | Application Default Credentials (ADC) | `gcloud auth application-default login` |
| Ứng dụng chạy trên Compute Engine/Cloud Run | Danh tính gắn với workload | Gắn service account và cấp quyền IAM tối thiểu |
| Job CI/CD ở môi trường ngoài Google Cloud | Federation hoặc cơ chế ngắn hạn phù hợp | Thiết lập Workload Identity Federation cho runner |
| Kỹ sư cần chạy lệnh dưới quyền service account | Impersonation khi được cấp quyền phù hợp | Cờ `--impersonate-service-account` trên lệnh hỗ trợ |

### 10.1. Đăng nhập cho lệnh `gcloud`

~~~bash
gcloud auth login
gcloud auth list
~~~

Lệnh `gcloud auth login` cho phép CLI sử dụng tài khoản người dùng. Nó không có nghĩa là mọi ứng dụng dùng Google Cloud client library cũng nhận được credential tương ứng.

### 10.2. Đăng nhập ADC cho phát triển ứng dụng trên máy

~~~bash
gcloud auth application-default login
~~~

Lệnh tạo một tệp credential dùng bởi cơ chế ADC của thư viện, tách biệt với credential mà `gcloud` sử dụng. Tệp này thường nằm trong thư mục cấu hình người dùng:

- Linux/macOS: `~/.config/gcloud/application_default_credentials.json`.
- Windows: `%APPDATA%\gcloud\application_default_credentials.json`.

Ứng dụng dùng thư viện Google Cloud có thể tìm credential qua các nguồn theo thứ tự ưu tiên, thường gồm biến `GOOGLE_APPLICATION_CREDENTIALS`, tệp ADC local, sau đó danh tính gắn với môi trường chạy có metadata server.

Nếu thư viện thông báo lỗi quota project, kiểm tra tài liệu xác thực của dịch vụ và quyền của tài khoản trước khi thiết lập:

~~~bash
gcloud auth application-default set-quota-project PROJECT_ID
~~~

Việc chọn quota project và quyền sử dụng quota phụ thuộc cơ chế tính phí/quota của API. Cấu hình `gcloud config set project` không đảm bảo đã cấu hình quota project cho ADC.

### 10.3. Xác thực an toàn trong môi trường triển khai

Đối với Cloud Run, Compute Engine và nhiều dịch vụ managed khác, thông thường nên **gắn service account cho workload** rồi cấp IAM tối thiểu theo chức năng. Với hệ thống CI/CD bên ngoài Google Cloud, sử dụng Workload Identity Federation nếu nhà cung cấp và luồng triển khai hỗ trợ.

Tránh commit hoặc chia sẻ service account key JSON. Thông tin xác thực, tệp ADC, token và output chứa bí mật phải được bảo vệ. Các lệnh in token truy cập không phù hợp để đưa trực tiếp vào tài liệu chia sẻ hoặc log build. Không dùng tài khoản cá nhân lưu trên máy để thay cho danh tính của ứng dụng chạy production.

## 11. Sử dụng CLI để kiểm tra tài nguyên GCP

Sau khi có tài khoản và project hợp lệ, những lệnh **chỉ đọc** sau giúp xác nhận môi trường:

~~~bash
# Tài khoản CLI hiện có và profile đang active
gcloud auth list
gcloud config configurations list
gcloud config list

# Liệt kê các project mà tài khoản có quyền xem
gcloud projects list

# Tra cứu metadata project
gcloud projects describe PROJECT_ID

# Liệt kê API đã được bật trong project
gcloud services list --enabled --project=PROJECT_ID

# Liệt kê mạng VPC
gcloud compute networks list --project=PROJECT_ID

# Liệt kê Cloud Run services trong một region
gcloud run services list --project=PROJECT_ID --region=REGION

# Liệt kê bucket Cloud Storage
gcloud storage buckets list --project=PROJECT_ID
~~~

Một số lệnh có thể báo lỗi nếu API liên quan chưa bật, tài khoản thiếu quyền IAM hoặc project/vùng không có tài nguyên. Trả về danh sách trống không nhất thiết là lỗi cài đặt.

### 11.1. Tùy biến kết quả trả về

~~~bash
# Chỉ in ID project (dễ sử dụng trong script)
gcloud projects list --format="value(projectId)"

# Hiển thị thông tin thành bảng
gcloud projects list --format="table(projectId,name)"

# Lấy kết quả JSON để xử lý bằng chương trình
gcloud projects describe PROJECT_ID --format=json

# Xem mô tả chi tiết tùy chọn --format và --filter
gcloud topic formats
gcloud topic filters
~~~

Trong script, ưu tiên output có cấu trúc hoặc định dạng trường xác định. Không nên phân tích output bảng căn cột theo vị trí ký tự, vì các cột, độ rộng và biểu diễn có thể thay đổi.

### 11.2. Đọc tài liệu ngay trong terminal

~~~bash
gcloud help
gcloud help compute
gcloud help compute instances list
gcloud run services list --help
gcloud topic configurations
~~~

Khi cần lệnh mới, bắt đầu từ cú pháp trên reference và kiểm tra cờ cụ thể. Một lệnh ở nhóm `alpha`/`beta` có thể có tính ổn định và điều kiện hỗ trợ khác với lệnh ở trạng thái chính thức.

## 12. Cập nhật CLI và cài các component bổ sung

Cơ chế cập nhật phụ thuộc **cách cài ban đầu**.

| Cách cài đặt | Cách cập nhật phù hợp |
| --- | --- |
| Installer/archive có component manager | `gcloud components update` |
| APT trên Debian/Ubuntu | `sudo apt-get update` rồi `sudo apt-get install --only-upgrade google-cloud-cli` |
| DNF/YUM trên RPM Linux | Cập nhật package `google-cloud-cli` bằng trình quản lý gói của hệ điều hành |
| Cloud Shell | Dùng bản CLI do môi trường Cloud Shell cung cấp; kiểm tra phiên bản hiện có |

Với bản cài có component manager:

~~~bash
# Xem component đã có và component có thể cài
gcloud components list

# Cập nhật CLI cùng các component đang cài
gcloud components update

# Ví dụ thêm công cụ quản lý Kubernetes nếu được hỗ trợ
gcloud components install kubectl
~~~

Với bản cài bằng APT/DNF, **component manager của `gcloud` có thể bị vô hiệu hóa**: dùng package tương ứng của hệ điều hành thay vì lặp lại `gcloud components install`. Ví dụ trên Debian/Ubuntu, gói `google-cloud-cli-gke-gcloud-auth-plugin` có thể dùng khi cần cơ chế xác thực GKE; `kubectl` có thể cài bằng package riêng.

Một số công cụ và component có vòng đời phát hành riêng. Với pipeline CI/CD, cân nhắc cố định phiên bản CLI/package phù hợp để kết quả triển khai có thể lặp lại, đồng thời có lịch cập nhật và kiểm thử.

## 13. Quy trình cấu hình trước khi làm việc với GCP

Trước thao tác triển khai trên Compute Engine, GKE, Cloud Run hoặc cơ sở dữ liệu, thực hiện quy trình ngắn:

~~~mermaid
flowchart TD
    A["Mở terminal"] --> B{"CLI đã cài?"}
    B -- "Chưa" --> C["Cài gcloud và kiểm tra phiên bản"]
    C --> D["Kiểm tra tài khoản và profile"]
    B -- "Rồi" --> D
    D --> E{"Đúng account, project?"}
    E -- "Chưa" --> F["Đăng nhập/chuyển profile/đặt project"]
    F --> G["Xác nhận region, zone và quyền IAM"]
    E -- "Đúng" --> G
    G --> H["Chạy lệnh đọc để xác minh"]
    H --> I{"Đủ điều kiện?"}
    I -- "Chưa" --> J["Kiểm tra API, IAM, network, billing"]
    J --> H
    I -- "Rồi" --> K["Thực hiện thao tác được phép và quan sát kết quả"]
~~~

Ở bất kỳ bước nào, nếu quyền truy cập không đủ, xử lý theo quy trình IAM. Không tự cấp vai trò Owner hoặc Editor quá rộng chỉ để vượt qua lỗi permission.

## 14. Khắc phục sự cố thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra và xử lý |
| --- | --- | --- |
| `gcloud: command not found` / `not recognized` | Chưa cài hoặc PATH chưa cập nhật | Mở terminal mới, chạy `gcloud version`, kiểm tra đường dẫn cài |
| `You do not currently have an active account` | Chưa đăng nhập hoặc chưa chọn tài khoản | `gcloud auth list`, `gcloud auth login`, `gcloud config set account ...` |
| `PERMISSION_DENIED` | IAM thiếu quyền hoặc resource không thuộc project | Xem account/project thực tế, kiểm tra quyền trên tài nguyên |
| `The project property is not set` | Thiếu project mặc định | `gcloud config set project PROJECT_ID` hoặc `--project=...` |
| `API has not been used or is disabled` | Dịch vụ API cần gọi chưa được bật | Xác nhận project, API tương ứng và người có quyền bật |
| Không thấy service/VM | Sai project, region/zone hoặc quyền liệt kê | `gcloud config list`, truyền `--project`, `--region`/`--zone` |
| Timeout / lỗi TLS khi `gcloud init` | Kết nối, proxy, tường lửa hoặc CA doanh nghiệp | Kiểm tra kết nối và [proxy configuration](https://docs.cloud.google.com/sdk/docs/proxy-settings) |
| `gcloud components update` không dùng được | Cài bằng APT/DNF nên component manager không hoạt động | Cập nhật bằng package manager |
| Ứng dụng lỗi `DefaultCredentialsError` dù CLI đã đăng nhập | Chưa có ADC hoặc cấu hình ADC bị ghi đè | Xác minh `gcloud auth application-default login`, biến `GOOGLE_APPLICATION_CREDENTIALS` và môi trường chạy |
| Lệnh yêu cầu chọn region/zone | Tài nguyên vùng chưa có giá trị mặc định hoặc dịch vụ dùng vùng riêng | Chỉ định cờ theo lệnh và đọc tài liệu dịch vụ |

**Trình tự chẩn đoán hiệu quả:** kiểm tra `gcloud version` → `gcloud auth list` → `gcloud config list` → project/region được truyền trong lệnh → IAM → trạng thái API → mạng/quota. Phân biệt lỗi cài đặt, xác thực và ủy quyền trước khi sửa cấu hình.

### 14.1. Cấu hình proxy

Nếu mạng công ty yêu cầu proxy, CLI có các thuộc tính cấu hình như `proxy/type`, `proxy/address`, `proxy/port` và tùy chọn về chứng chỉ; cấu hình phụ thuộc proxy của doanh nghiệp. Ví dụ tham khảo **chỉ dùng khi đã biết đúng máy chủ proxy**:

~~~bash
gcloud config set proxy/type http
gcloud config set proxy/address PROXY_HOST
gcloud config set proxy/port PROXY_PORT
~~~

Không đưa tên người dùng/mật khẩu proxy vào script công khai. Đối với TLS inspection và CA nội bộ, cần hướng dẫn từ quản trị mạng; tránh bỏ qua xác thực chứng chỉ để xử lý lỗi kết nối.

### 14.2. Quản lý cấu hình trên máy dùng chung

Cấu hình CLI mặc định thường được lưu trong thư mục người dùng, có thể xác định bằng:

~~~bash
gcloud info --format="value(config.paths.global_config_dir)"
~~~

Biến môi trường `CLOUDSDK_CONFIG` cho phép chỉ định thư mục cấu hình riêng khi thực sự cần tách môi trường vận hành. Điều này không tự cấp quyền IAM; thư mục phải có quyền ghi và bảo vệ phù hợp.

Khi không còn sử dụng máy, có thể xem tài liệu [gcloud auth revoke](https://docs.cloud.google.com/sdk/gcloud/reference/auth/revoke) và [gcloud auth application-default revoke](https://docs.cloud.google.com/sdk/gcloud/reference/auth/application-default/revoke) để chủ động thu hồi credential local. Hai cơ chế dùng kho credential khác nhau nên thao tác thu hồi cũng khác nhau.

## 15. Bài thực hành: thiết lập hai profile GCP

**Bối cảnh:** Nhóm phát triển quản lý một dịch vụ web có môi trường thử nghiệm và production. Bạn được cấp quyền xem hai project và cần kiểm tra dịch vụ Cloud Run mà không vô tình đổi project mặc định trong phiên làm việc.

> Thay `DEMO_DEV_PROJECT_ID`, `DEMO_PROD_PROJECT_ID` và `REGION` bằng giá trị thật. Thực hành chỉ dùng các lệnh cấu hình local và đọc tài nguyên; không tạo VM hay triển khai ứng dụng.

**Bước 1 — Xác minh công cụ và danh tính:**

~~~bash
gcloud version
gcloud auth list
gcloud projects list --format="table(projectId,name)"
~~~

Nếu chưa đăng nhập, thực hiện `gcloud auth login`. Nếu project không xuất hiện, kiểm tra quyền IAM thay vì tạo project mới.

**Bước 2 — Tạo profile dev:**

~~~bash
gcloud config configurations create demo-dev
gcloud config configurations activate demo-dev
gcloud config set project DEMO_DEV_PROJECT_ID
gcloud config set compute/region REGION
gcloud config list
~~~

**Bước 3 — Tạo profile prod:**

~~~bash
gcloud config configurations create demo-prod
gcloud config configurations activate demo-prod
gcloud config set project DEMO_PROD_PROJECT_ID
gcloud config set compute/region REGION
gcloud config configurations list
~~~

**Bước 4 — Chọn dev làm profile active và xem production cho một lệnh:**

~~~bash
gcloud config configurations activate demo-dev

# Kiểm tra project dev
gcloud projects describe DEMO_DEV_PROJECT_ID

# Chạy riêng một lệnh theo profile prod
gcloud projects describe DEMO_PROD_PROJECT_ID --configuration=demo-prod

# Profile active vẫn là demo-dev
gcloud config configurations list
gcloud config get-value project
~~~

**Bước 5 — Xem Cloud Run của dev (nếu API và IAM cho phép):**

~~~bash
gcloud run services list \
  --project=DEMO_DEV_PROJECT_ID \
  --region=REGION
~~~

Nếu dùng Windows PowerShell, nhập câu lệnh này trên **một dòng** hoặc dùng cú pháp xuống dòng riêng của PowerShell; ký tự `\` ở cuối dòng trong ví dụ là cách nối dòng của Bash.

**Bước 6 — Ghi lại kết quả trong báo cáo thực hành:**

| Thông tin | Cần ghi |
| --- | --- |
| Phiên bản CLI | Kết quả `gcloud version` |
| Tài khoản active | Email được đánh dấu active trong `gcloud auth list` |
| Profile active | Tên profile trong `gcloud config configurations list` |
| Project ID hiện tại | Kết quả `gcloud config get-value project` |
| Region | Giá trị `compute/region` |
| Tình trạng truy cập Cloud Run | Thành công/danh sách rỗng/lỗi kèm thông báo chính |
| Cách đã xác minh đúng môi trường | Project và region được chọn theo cấu hình hoặc cờ cụ thể |

Nếu bạn chạy lại bài thực hành, `gcloud config configurations create` có thể báo profile đã tồn tại. Khi đó chỉ cần `activate` profile cũ rồi kiểm tra các thuộc tính; không xóa hoặc ghi đè profile đang được sử dụng nếu chưa xác định người sở hữu.

## 16. Câu hỏi tự kiểm tra

1. `gcloud version` chạy thành công nhưng `gcloud projects list` báo chưa đăng nhập. Vấn đề thuộc lớp cài đặt, xác thực hay ủy quyền?
2. Hai cấu hình `dev` và `prod` có bảo đảm một tài khoản chỉ nhìn thấy tài nguyên của đúng môi trường không? Vì sao?
3. `gcloud auth login` khác `gcloud auth application-default login` như thế nào?
4. Tại sao cần ghi rõ `--project` và `--region` trong các script triển khai?
5. Khi cài CLI bằng APT, vì sao `gcloud components update` không phải cách cập nhật thích hợp?
6. Một ứng dụng Java chạy trên Cloud Run nên lấy credential bằng file JSON được commit cùng mã nguồn hay bằng danh tính gắn với workload?

**Gợi ý đối chiếu:** (1) xác thực; (2) không, profile là nhóm thuộc tính và quyền do IAM quyết định; (3) CLI credentials và ADC phục vụ hai luồng xác thực khác nhau; (4) tránh phụ thuộc profile active và vị trí mặc định trên máy runner; (5) trình quản lý gói của hệ điều hành sở hữu bản cài; (6) ưu tiên danh tính gắn với Cloud Run và quyền tối thiểu.

## 17. Checklist sử dụng Google Cloud CLI

- [ ] Có thể chạy `gcloud version` và `gcloud help`.
- [ ] Biết máy đang dùng CLI local hay Cloud Shell, và CLI được cài theo phương pháp nào.
- [ ] Có thể giải thích account, project ID, region và zone đang được chọn.
- [ ] Biết dùng `gcloud config list`, `gcloud auth list` và `--project` để xác minh môi trường.
- [ ] Biết tạo, kích hoạt và chọn profile theo từng lệnh.
- [ ] Phân biệt CLI credential với ADC của ứng dụng.
- [ ] Hiểu vì sao production nên dùng workload identity/service account và IAM tối thiểu.
- [ ] Biết cách xem trợ giúp, lọc output và kiểm tra quyền trước khi thao tác.
- [ ] Biết cách cập nhật CLI và khắc phục các lỗi cơ bản.

## 18. Tài liệu tham khảo chính thức

Các liên kết dưới đây là tài liệu của Google Cloud. Trước khi cài đặt trên máy thực tế, kiểm tra phiên bản CLI, kiến trúc hệ điều hành và các bước tương ứng trên trang hiện hành.

- [Install the Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk) — hướng dẫn cài theo hệ điều hành.
- [Using the Google Cloud CLI installer](https://docs.cloud.google.com/sdk/docs/downloads-interactive) — cài đặt tương tác và tự động.
- [Initialize the gcloud CLI](https://docs.cloud.google.com/sdk/docs/initialize) — `gcloud init` và cấu hình bước đầu.
- [Google Cloud CLI overview](https://docs.cloud.google.com/sdk/gcloud) — mô hình sử dụng và nhóm lệnh.
- [Managing gcloud CLI configurations](https://docs.cloud.google.com/sdk/docs/configurations) — nhiều profile và thuộc tính.
- [Managing gcloud CLI components](https://docs.cloud.google.com/sdk/docs/components) — cài/cập nhật component.
- [Authentication basics](https://docs.cloud.google.com/docs/get-started/authentication) — nguyên tắc xác thực.
- [How Application Default Credentials works](https://docs.cloud.google.com/docs/authentication/application-default-credentials) — thứ tự tìm credential và phân biệt ADC với CLI.
- [gcloud CLI reference](https://docs.cloud.google.com/sdk/gcloud/reference) — cú pháp và cờ của các lệnh.
- [Proxy configuration](https://docs.cloud.google.com/sdk/docs/proxy-settings) — cấu hình môi trường mạng có proxy.

**Ghi nhớ:** Để làm việc an toàn và lặp lại được với Google Cloud, hãy luôn biết **lệnh đang chạy với danh tính nào, trên project nào, ở vùng nào và với quyền gì**. Đây là điều kiện tiên quyết trước khi sử dụng CLI để quản lý IAM, VPC, Compute Engine, GKE, Cloud Run, cơ sở dữ liệu hoặc tự động hóa phát hành.
