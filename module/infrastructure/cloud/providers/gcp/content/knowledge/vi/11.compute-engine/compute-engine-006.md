# Metadata server và startup scripts

Một máy ảo Compute Engine cần biết **nó là máy nào, đang thuộc project/zone nào, dùng cấu hình ứng dụng gì và phải làm gì khi khởi động**. Thay vì ghi cứng những giá trị này vào image hoặc đăng nhập thủ công vào từng VM, Google Cloud cung cấp **metadata server** và **startup scripts** để lấy thông tin và tự động hóa quá trình chuẩn bị máy.

Trong chương **Compute Engine** thuộc module **CLOUD_PROVIDERS_GCP**, bài học này kết nối các kiến thức về project, IAM, VPC với việc cài đặt ứng dụng, quản lý danh tính, phát hành và giám sát độ tin cậy/chi phí. Ví dụ một nhóm chạy API trên Compute Engine có thể dùng cùng một image và cùng startup script cho các môi trường khác nhau, nhưng truyền `app-env=dev` hoặc `app-env=prod` qua metadata. Khi VM boot, script đọc giá trị tương ứng để chuẩn bị cấu hình.

**Kết quả học tập**

1. Phân biệt metadata có sẵn, custom metadata và thông tin xác thực tạm thời của service account.
2. Truy vấn metadata **từ bên trong VM** qua HTTP với header bắt buộc.
3. Giải thích metadata theo phạm vi project, zone và instance; biết khi nào cấu hình cấp instance ghi đè cấp project.
4. Dùng startup scripts trên Linux/Windows và hiểu vai trò của Google Guest Environment.
5. Tự viết startup script có thể chạy lại an toàn, ghi log, kiểm tra lỗi và không làm lộ bí mật.
6. Thực hành tạo một VM dùng startup script, kiểm tra kết quả, cập nhật metadata và dọn tài nguyên.
7. Nhận diện lỗi phổ biến và lựa chọn giải pháp cấu hình phù hợp cho VM đơn lẻ, managed instance group (MIG) và pipeline triển khai.

## 1. Metadata server là gì?

**Metadata server** là dịch vụ mà một VM Compute Engine có thể truy vấn để đọc những dữ liệu mô tả chính nó và môi trường Google Cloud liên quan. Mỗi VM nhìn thấy metadata theo ngữ cảnh của VM đó. Các giá trị có thể là do Google Cloud cung cấp sẵn hoặc do người quản trị thêm vào.

Máy ảo truy cập metadata server qua tên DNS hoặc địa chỉ link-local, ví dụ:

~~~text
http://metadata.google.internal/computeMetadata/v1/
http://169.254.169.254/computeMetadata/v1/
~~~

Máy không cần public IP, Cloud NAT hoặc truy cập Internet để dùng endpoint metadata HTTP nội bộ này. Google Cloud cũng có **HTTPS metadata server** dành cho Shielded VM đáp ứng điều kiện guest environment và chứng chỉ; không nên chỉ thay tiền tố `http` thành `https` trong một script cũ mà chưa chuẩn bị xác thực/certificate được yêu cầu.

**Điểm bảo mật cốt lõi:** metadata server có thể được truy cập từ các tiến trình bên trong VM mà không cần thêm một lần đăng nhập IAM cho từng request metadata. Bởi vậy, mã không đáng tin chạy trên VM hoặc một lỗ hổng server-side request forgery (SSRF) có thể khiến dữ liệu metadata, kể cả token từ service account gắn với VM, bị truy cập trái ý muốn. Không dùng metadata làm kho lưu bí mật.

### 1.1. Cây metadata thường gặp

Metadata được tổ chức thành những thư mục/khóa. Ví dụ:

~~~text
computeMetadata/v1/
├── instance/
│   ├── name
│   ├── id
│   ├── zone
│   ├── attributes/
│   │   ├── app-env
│   │   └── startup-script
│   ├── network-interfaces/
│   └── service-accounts/
│       └── default/
│           ├── email
│           └── token   # Nội dung nhạy cảm; KHÔNG ghi ra log
└── project/
    ├── project-id
    ├── numeric-project-id
    └── attributes/
        └── app-env
~~~

Đây là sơ đồ ví dụ, không có nghĩa mọi key đều tồn tại ở mọi VM. `app-env` là **custom metadata** chỉ có sau khi người quản trị thêm. Cây metadata thực tế còn có các mục do hệ thống cung cấp và có thể thay đổi theo loại VM.

| Nhóm dữ liệu | Ví dụ | Cách sử dụng |
| --- | --- | --- |
| Metadata hệ thống về instance | `instance/name`, `instance/id`, `instance/zone` | Nhận diện máy, ghi nhãn log hoặc lựa chọn cấu hình theo môi trường. |
| Metadata hệ thống về project | `project/project-id`, `project/numeric-project-id` | Xác định project chứa VM; tránh hard-code Project ID. |
| Custom metadata | `instance/attributes/app-env` | Chuyển cấu hình **không nhạy cảm**, ví dụ `dev` hoặc `production`. |
| Thông tin service account | `instance/service-accounts/default/email` | Xác định danh tính được gắn với VM. |
| Access token của service account | `instance/service-accounts/default/token` | Thư viện Google Cloud/ADC dùng để xác thực tới API; tuyệt đối không đưa token vào log, website hoặc output chia sẻ. |
| Khóa dành cho guest agent | `startup-script`, `startup-script-url` | Chỉ dẫn guest environment cách tải và chạy script khi VM khởi động. |

### 1.2. Phạm vi project, zone và instance

Google Cloud có metadata được đặt theo phạm vi **project**, **zone** (với những chức năng/cách quản lý được hỗ trợ) và **VM instance**.

- **Project metadata** có thể truyền các giá trị chung tới nhiều VM trong project, ví dụ thông tin cấu hình được chủ động dùng chung. Các tác động của sửa project-wide metadata vì thế có phạm vi lớn.
- **Zonal metadata** hỗ trợ giá trị theo zone theo quy tắc của Compute Engine; phải kiểm tra loại key và cách cấu hình được hỗ trợ.
- **Instance metadata** là giá trị chỉ định cho một VM cụ thể. Với các khóa cấu hình trùng nhau được hỗ trợ, giá trị instance có thể ưu tiên so với giá trị ở phạm vi rộng hơn.

Ví dụ project khai báo `app-env=dev` nhưng VM production khai báo `app-env=prod`. Ứng dụng phải **đọc đúng nguồn và hiểu quy tắc ưu tiên**; truy vấn trực tiếp `project/attributes/app-env` sẽ cho bạn giá trị cấp project, chứ không tự biến thành giá trị cấp VM. Khi muốn tùy biến script cho mỗi VM, nên truyền instance metadata rõ ràng và thống nhất quy ước giữa các nhóm.

**Không trộn lẫn metadata với IAM:** quyền thay đổi metadata qua Compute Engine API được bảo vệ bởi IAM, nhưng việc đọc metadata *từ tiến trình chạy trong VM* có mô hình truy cập khác. Phân quyền `compute.instances.setMetadata` hoặc `compute.projects.setCommonInstanceMetadata` cần được kiểm soát chặt vì người có quyền sửa script có thể khiến mã được thực thi với quyền cao lúc khởi động.

### 1.3. Metadata server hoạt động độc lập với Internet

~~~mermaid
flowchart LR
    A["Ứng dụng / script trong VM"] -->|"Metadata-Flavor: Google"| M["Metadata server<br/>metadata.google.internal"]
    M --> C["Thông tin VM, project<br/>và custom attributes"]
    M --> SA["Thông tin service account<br/>và token ngắn hạn"]
    A -. "API Google Cloud, khi được cấp IAM" .-> G["Cloud Storage / Logging / API"]
~~~

Metadata request được xử lý trong môi trường hạ tầng liên quan tới máy chủ vật lý của VM, không phải một cuộc gọi Internet công khai. Dù vậy, tính sẵn sàng có thể bị gián đoạn thoáng qua, chẳng hạn khi VM vừa boot hoặc có hoạt động bảo trì. Script cần xử lý timeout và retry phù hợp thay vì mặc định mọi request luôn thành công ngay lần đầu.

## 2. Truy vấn metadata từ bên trong VM

### 2.1. Header bắt buộc

Để truy cập HTTP metadata server, gửi header:

~~~http
Metadata-Flavor: Google
~~~

Header này giúp phân biệt những request metadata có chủ đích với request không mong muốn. Khi thiếu header, máy chủ metadata từ chối request. Header không phải một secret hay token xác thực; **bất kỳ tiến trình nào có quyền gửi HTTP request từ VM đều có thể thêm header**.

Trên **shell của VM Linux** (qua SSH hoặc Console), ví dụ:

~~~bash
MDS="http://metadata.google.internal/computeMetadata/v1"

# Tên VM hiện tại
curl --fail --silent --show-error \
  -H "Metadata-Flavor: Google" \
  "$MDS/instance/name"

# Project ID
curl --fail --silent --show-error \
  -H "Metadata-Flavor: Google" \
  "$MDS/project/project-id"

# Zone của VM (thường là resource path)
curl --fail --silent --show-error \
  -H "Metadata-Flavor: Google" \
  "$MDS/instance/zone"
~~~

Đây là những lệnh **chỉ đọc** và không sinh tài nguyên mới. Không thể chạy ví dụ và kỳ vọng dữ liệu VM thật khi đang ở laptop hoặc Cloud Shell bên ngoài VM, vì endpoint metadata trả dữ liệu theo ngữ cảnh máy tính có quyền truy cập nó.

### 2.2. Đọc custom metadata

Giả sử VM đã được gán key `app-env`:

~~~bash
curl --fail --silent --show-error \
  -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/attributes/app-env"
~~~

Nếu giá trị là `training`, kết quả:

~~~text
training
~~~

Nếu key không tồn tại, truy vấn có thể trả HTTP 404; đây là lỗi cần được xử lý trong script, không nên lặng lẽ coi là một giá trị cấu hình an toàn mặc định khi ứng dụng cần xác nhận môi trường. Bạn có thể liệt kê directory `instance/attributes/` hoặc `project/attributes/` để biết các key hiện có, nhưng **không in nguyên tất cả metadata trong môi trường chứa dữ liệu nhạy cảm**.

### 2.3. Dùng Windows PowerShell

Trên **Windows VM**, có thể gọi:

~~~powershell
$mds = "http://metadata.google.internal/computeMetadata/v1"
$headers = @{"Metadata-Flavor" = "Google"}

$vmName = Invoke-RestMethod -Uri "$mds/instance/name" -Headers $headers
$projectId = Invoke-RestMethod -Uri "$mds/project/project-id" -Headers $headers
Write-Output "VM=$vmName Project=$projectId"
~~~

Máy Windows vẫn dùng giao thức metadata với header nêu trên; thứ thay đổi là shell và các lệnh của hệ điều hành. Những endpoint chứa token vẫn phải được bảo vệ, không đưa vào `Write-Output` hoặc transcript.

### 2.4. Khi cần phản ứng với thay đổi metadata

Metadata server hỗ trợ hình thức theo dõi sự thay đổi của **một key cụ thể**, ví dụ tham số `wait_for_change=true`; có thể sử dụng trong những ứng dụng cần cập nhật cấu hình mà không khởi động lại VM:

~~~bash
curl --fail --silent --show-error \
  -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/attributes/app-env?wait_for_change=true&timeout_sec=60"
~~~

Đây là request chờ thay đổi của một giá trị, **không phải** cơ chế chạy lại startup script tự động. Không dùng long polling lên endpoint access token; metadata server có các hạn chế riêng đối với loại request và key được theo dõi. Khi thiết kế luồng quan sát, nên thêm giới hạn số lần retry, backoff và logic xử lý timeout để tránh gây tải không cần thiết.

## 3. Startup scripts: tự động hóa khi VM khởi động

**Startup script** là một tập lệnh được Compute Engine guest environment thực thi trong quá trình VM boot. Những tác vụ phổ biến:

- Chuẩn bị directory, file cấu hình và phân quyền file.
- Cài hoặc cập nhật gói phần mềm cần thiết, khi môi trường mạng và package repository cho phép.
- Lấy thông số từ custom metadata để đặt tên môi trường, cấu hình địa chỉ dịch vụ hoặc chọn profile ứng dụng.
- Khởi tạo systemd service, agent giám sát hoặc bước kiểm tra sức khỏe.
- Tải bản phát hành có phiên bản xác định từ kho đáng tin cậy, nếu danh tính VM có quyền thích hợp.

**Startup scripts không phải một dịch vụ điều phối phát hành hoàn chỉnh.** Khi có hàng trăm VM, nhiều biến thể cấu hình hoặc cần rollback nhất quán, nên kết hợp image, instance template, managed instance group, Infrastructure as Code và CI/CD. Dùng startup script cho bước bootstrap cần thiết; dùng công cụ quản lý cấu hình/deploy phù hợp cho phần vòng đời ứng dụng rộng hơn.

### 3.1. Điều kiện để script chạy

Google Cloud cung cấp **Google Guest Environment**, trong đó có guest agent và các thành phần chạy metadata scripts. Compute Engine public images thông thường đã có guest environment. Với custom image, bạn phải bảo đảm môi trường guest được cài, chạy và cấu hình phù hợp.

~~~mermaid
flowchart TD
    BOOT["VM boot / reboot"] --> G["Google Guest Environment<br/>guest agent / metadata scripts"]
    G --> M["Đọc instance/project metadata"]
    M --> S{"Có startup script<br/>hợp lệ không?"}
    S -->|Không| END["VM tiếp tục khởi động"]
    S -->|Có| RUN["Lấy nội dung script<br/>và thực thi trong guest OS"]
    RUN --> STATUS["Ghi exit status và output<br/>vào log phù hợp"]
    STATUS --> END
~~~

Trên Linux, script được chạy với **đặc quyền root** theo cơ chế startup scripts. Vì vậy quyền sửa metadata khởi động có tác động bảo mật rất lớn: người sửa nội dung script có thể đưa vào lệnh thực thi với quyền hệ thống trong lần boot sau. Không chạy script từ nguồn chưa xác minh hoặc chứa mã không được review.

Startup script thường chạy **mỗi khi VM khởi động**, bao gồm các lần boot/reboot tiếp theo nếu guest environment hoạt động. **Sửa metadata của VM đang chạy không đồng nghĩa script lập tức chạy lại.** Người vận hành phải cân nhắc khởi động lại VM hoặc chủ động gọi runner đúng cách sau khi kiểm tra tác động.

### 3.2. Các khóa metadata dành cho Linux

| Khóa | Cách cung cấp | Khi nào phù hợp |
| --- | --- | --- |
| `startup-script` | Nội dung script được đặt trực tiếp hoặc đọc từ file local khi gọi gcloud. | Script ngắn, đủ nhỏ để nằm trong giới hạn metadata. |
| `startup-script-url` | Đường dẫn tới script lưu trong Cloud Storage, như `gs://bucket/bootstrap.sh` hoặc URL Cloud Storage được hỗ trợ. | Script lớn hơn, quản lý file riêng, hoặc cần quy trình phát hành script. |

Với Linux, tài liệu Compute Engine nêu ngưỡng **256 KB** cho nội dung startup script được truyền trực tiếp; script lớn nên đặt ở Cloud Storage theo hướng dẫn hiện hành. Sử dụng URL Cloud Storage cần bảo đảm VM có **đường kết nối, service account và quyền đọc object**. Ví dụ gán `roles/storage.objectViewer` cho service account **trên đúng bucket**; access scopes của VM cũng phải cho phép hoạt động tương ứng nếu áp dụng.

Nếu cấu hình cả `startup-script` và `startup-script-url`, guest environment có thể xử lý **nhiều script** cho cùng sự kiện khởi động. Đừng xây hệ thống phụ thuộc vào thứ tự thực thi ngầm định giữa các loại script hoặc các phiên bản guest agent; thay vào đó, gom các bước có phụ thuộc vào một script được quản lý rõ ràng và kiểm tra kết quả sau mỗi bước.

### 3.3. Ví dụ startup script trên Linux

Giả sử VM cần tạo một tệp mô tả bản thân khi boot và ghi một dòng log. Script này không tải gói từ Internet và có thể chạy lại mà không tạo thêm tài nguyên không mong muốn:

~~~bash
#!/usr/bin/env bash
set -Eeuo pipefail

MDS="http://metadata.google.internal/computeMetadata/v1"

metadata() {
  curl --fail --silent --show-error \
    --retry 5 --retry-delay 2 \
    -H "Metadata-Flavor: Google" \
    "$MDS/$1"
}

VM_NAME="$(metadata instance/name)"
PROJECT_ID="$(metadata project/project-id)"
APP_ENV="$(metadata instance/attributes/app-env)"

# Chỉ dùng app-env cho cấu hình không nhạy cảm
install -d -m 0755 /var/lib/metadata-demo
printf 'vm=%s\nproject=%s\nenvironment=%s\n' \
  "$VM_NAME" "$PROJECT_ID" "$APP_ENV" \
  > /var/lib/metadata-demo/info.txt
chmod 0644 /var/lib/metadata-demo/info.txt

logger -t metadata-demo "Startup completed for $VM_NAME"
~~~

Trong ví dụ:

1. `set -Eeuo pipefail` giúp phát hiện nhiều lỗi shell, tránh tiếp tục theo cách gây hiểu nhầm rằng bootstrap đã hoàn tất.
2. Hàm `metadata` luôn gửi header đúng và thử lại khi có lỗi tạm thời.
3. `VM_NAME` và `PROJECT_ID` được đọc từ môi trường VM, không hard-code theo từng máy.
4. `APP_ENV` là một custom key cần được cung cấp lúc tạo VM; nếu thiếu sẽ báo lỗi, tránh tự chạy với nhầm môi trường.
5. Lệnh `install -d` và ghi đè file tạo kết quả nhất quán khi chạy lại.
6. `logger` gửi thông tin trạng thái không chứa secret tới log cục bộ.

Lệnh `curl --retry` xử lý một số lỗi có thể thử lại theo chính sách của curl; với hệ thống production, nên đặt giới hạn thời gian kết nối/tổng thời gian, retry cho các loại lỗi phù hợp và kiểm soát phụ thuộc để startup không bị treo quá lâu.

### 3.4. Inline script và script từ Cloud Storage

**Cách A — cung cấp nội dung từ file local:**

~~~bash
gcloud compute instances create vm-lab \
  --zone=asia-southeast1-b \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --metadata=app-env=training \
  --metadata-from-file=startup-script=./startup.sh
~~~

CLI **đọc file local và truyền nội dung vào metadata** khi chạy lệnh. Nó không yêu cầu VM tự truy cập file trên laptop.

**Cách B — chỉ định object Cloud Storage:**

~~~bash
gcloud compute instances create vm-lab \
  --zone=asia-southeast1-b \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --metadata=app-env=training,startup-script-url=gs://EXAMPLE_BUCKET/bootstrap.sh
~~~

Các lệnh tạo VM là **thao tác ghi có thể phát sinh chi phí**; `vm-lab` và `EXAMPLE_BUCKET` chỉ là placeholders, không chạy cả hai lệnh tạo cùng một VM. Với phương án B, bạn cần upload script vào Cloud Storage trước, xác nhận IAM đọc object, access scopes và đường kết nối, sau đó bảo vệ việc thay đổi nội dung object vì lần boot tiếp theo có thể đọc phiên bản script mới.

Nếu muốn version hóa chắc chắn, có thể dùng tên object có phiên bản hoặc quy trình phát hành bất biến và chỉ cập nhật URL trong instance template sau khi review. Không coi một URL không kiểm soát mà script tải được là nguồn mã an toàn.

### 3.5. Startup scripts trên Windows

Windows VM có các khóa metadata riêng, ví dụ:

| Khóa Windows | Ý nghĩa |
| --- | --- |
| `windows-startup-script-ps1` | Startup script bằng PowerShell. |
| `windows-startup-script-cmd` | Startup script kiểu CMD. |
| `windows-startup-script-bat` | Startup script kiểu batch file. |
| `windows-startup-script-url` | Script tải từ location hỗ trợ, tùy cấu hình guest environment. |

Ví dụ PowerShell tối giản chạy **trong Windows VM khi boot**:

~~~powershell
$mds = "http://metadata.google.internal/computeMetadata/v1"
$headers = @{"Metadata-Flavor" = "Google"}
$vm = Invoke-RestMethod -Uri "$mds/instance/name" -Headers $headers

New-Item -Path "C:\ProgramData\MetadataDemo" -ItemType Directory -Force |
  Out-Null
Set-Content -Path "C:\ProgramData\MetadataDemo\boot.txt" `
  -Value "VM=$vm"
~~~

Khi tạo Windows VM, bạn truyền file PowerShell bằng `--metadata-from-file=windows-startup-script-ps1=./startup.ps1` và chọn image Windows thích hợp. Nhật ký startup script Windows có thể được quan sát qua **Windows Event Viewer** với những event của `GCEMetadataScripts`, cùng serial console theo tài liệu. Đừng dùng khóa Linux `startup-script` rồi kỳ vọng nó hoạt động giống khóa Windows.

## 4. Startup scripts trong vòng đời VM

### 4.1. Startup script khác với một lần chạy lệnh qua SSH

| Cách thực hiện | Thời điểm và tác động | Dùng khi |
| --- | --- | --- |
| **Startup script qua metadata** | Guest environment chạy khi boot; có thể chạy lại ở lần boot sau. | Bootstrap tự động cho VM mới hoặc instance từ template. |
| **SSH / PowerShell Remoting** | Người vận hành chủ động chạy lệnh trong phiên quản trị. | Điều tra sự cố, thao tác thủ công đã được phê duyệt. |
| **systemd service / Windows Service** | Hệ điều hành quản lý một tiến trình dài hạn, restart và trạng thái. | Chạy ứng dụng hoặc agent liên tục, sau khi startup chuẩn bị máy. |
| **Instance template + MIG** | Nhiều VM được tạo từ mẫu cấu hình, có cơ chế thay thế và mở rộng. | Fleet VM, tự động hóa rollout/rollback theo thiết kế. |
| **Custom image / image baking** | Đóng gói phần mềm và cấu hình cơ bản sẵn vào image. | Giảm thời gian startup, tăng tính nhất quán và khả năng kiểm soát phiên bản. |

Không nên dùng script boot để chạy foreground server vô thời hạn, vì việc bootstrap có thể không bao giờ trả về trạng thái hoàn tất. Hãy tạo **systemd unit** hoặc dịch vụ Windows rồi bật để hệ điều hành quản lý vòng đời tiến trình.

### 4.2. Script phải idempotent

**Idempotent** nghĩa là chạy lại không làm hỏng trạng thái hoặc nhân đôi kết quả ngoài ý muốn. Đây là thuộc tính quan trọng vì VM có thể reboot do bảo trì, sự cố hoặc thao tác vận hành.

| Cách viết dễ gây lỗi | Cách cải thiện |
| --- | --- |
| Mỗi boot dùng `>>` thêm cấu hình lặp lại vào một file. | Tạo file từ mẫu chính xác hoặc cập nhật có kiểm tra điều kiện. |
| Mỗi boot tạo thêm user với tên mới. | Kiểm tra user tồn tại trước khi tạo; quản lý trạng thái bằng công cụ phù hợp. |
| Tự chạy migration database khi VM khởi động, không có khóa. | Dùng quy trình migration riêng, có điều phối và rollback. |
| Tải bản phát hành từ đường dẫn `latest` không cố định. | Ghim artifact version hoặc checksum được phê duyệt. |
| Tải gói và tiếp tục dù command thất bại. | Dừng theo mã lỗi, ghi log không chứa secret, retry có giới hạn. |
| In toàn bộ environment, HTTP response hoặc token ra serial log. | Chỉ ghi sự kiện, ID không nhạy cảm và mã lỗi cần thiết. |

Khởi động an toàn không chỉ là “script chạy thành công một lần”. Cần kiểm chứng cả **lần boot đầu**, **lần reboot**, **lần thay instance từ template** và **khi dependency tạm thời không sẵn sàng**.

### 4.3. Thay đổi metadata có chạy lại script không?

Giả sử VM đang chạy và bạn cập nhật:

~~~bash
gcloud compute instances add-metadata vm-lab \
  --zone=asia-southeast1-b \
  --metadata=app-env=staging
~~~

Giá trị metadata mới có thể được truy vấn từ bên trong VM theo cơ chế cập nhật metadata, nhưng **startup script không tự thực thi lại** chỉ vì key `app-env` đổi. Các ứng dụng cần cập nhật nóng phải tự theo dõi giá trị và reload cấu hình đúng cách. Nếu chủ động chạy lại startup script trên Linux có guest environment hỗ trợ, có thể sử dụng:

~~~bash
# Thực thi bên trong Linux VM, sau khi đã kiểm tra hệ quả
sudo google_metadata_script_runner startup
~~~

Đây là thao tác có thể chạy lại lệnh root và gây thay đổi trạng thái VM; không dùng thử trên production nếu script chưa được kiểm chứng idempotent. Việc **reboot VM** cũng có thể kích hoạt script lại, nhưng cần kế hoạch giảm gián đoạn, đặc biệt khi VM chạy ứng dụng có trạng thái.

### 4.4. Theo dõi kết quả và mã thoát

Trên Linux VM, kiểm tra nhật ký startup script:

~~~bash
# Thực thi bên trong Linux VM
sudo journalctl -u google-startup-scripts.service --no-pager
sudo journalctl -u google-startup-scripts.service -b --no-pager
~~~

Có thể xem thông tin liên quan qua **serial port 1** trong Cloud Console hoặc:

~~~bash
# Từ máy có gcloud và quyền đọc instance/serial output
gcloud compute instances get-serial-port-output vm-lab \
  --zone=asia-southeast1-b \
  --port=1
~~~

Các cơ chế ghi log cụ thể phụ thuộc image và guest environment. Không phải mọi lệnh `echo` được viết ra tệp trên disk đều tự xuất hiện trong Cloud Logging; muốn có log tập trung còn cần agent/đường xuất log phù hợp.

## 5. Bảo mật metadata, service account và startup scripts

### 5.1. Metadata không phải kho bí mật

Không ghi **password, API key, private key, access token, refresh token, nội dung chứng chỉ riêng tư** hoặc chuỗi kết nối có mật khẩu vào custom metadata. Lý do:

- Những tiến trình trên cùng VM có thể truy vấn metadata server.
- Người có quyền đọc hoặc sửa metadata qua control plane có thể nhìn thấy giá trị theo quyền được cấp.
- Startup script có thể làm giá trị đi vào serial output, journal, log ứng dụng hoặc lệnh shell khi debug.
- Metadata ở cấp project có thể được nhiều VM sử dụng và tạo phạm vi ảnh hưởng rộng.

Thay vào đó, dùng **Secret Manager** hoặc hệ thống quản lý bí mật được tổ chức phê duyệt. Khi VM cần secret lúc chạy, gắn service account chỉ có quyền truy cập đúng secret/version cần thiết, dùng thư viện/ADC phù hợp và tránh ghi nội dung ra disk hoặc log ngoài mục đích.

### 5.2. Service account token là thông tin xác thực nhạy cảm

Một VM có service account gắn kèm có thể nhận credential ngắn hạn qua metadata server để gọi Google Cloud APIs. Đường dẫn phổ biến thuộc nhánh:

~~~text
instance/service-accounts/default/
instance/service-accounts/default/email
instance/service-accounts/default/token
~~~

`default` ở đây là **alias** cho service account được gắn với VM theo cấu hình, không nhất thiết là Compute Engine default service account của project. Endpoint `token` trả access token nhạy cảm; tài liệu chỉ minh họa tên đường dẫn, **không yêu cầu in token ra terminal hay chép vào log**.

Quyền API thực tế phụ thuộc vào **IAM roles của service account** và **access scopes của VM** theo cơ chế Compute Engine. Để giảm rủi ro:

1. Tạo service account chuyên trách theo workload/môi trường.
2. Cấp quyền tối thiểu trên tài nguyên đích thay vì role Editor toàn project.
3. Giới hạn người được phép thay service account, quản lý VM, sửa metadata hoặc impersonate danh tính.
4. Ưu tiên credential do môi trường cung cấp và thư viện Google Cloud/ADC thay vì khóa service account JSON tồn tại lâu.
5. Kiểm soát những tiến trình không đáng tin và endpoint ứng dụng có khả năng truy cập metadata.

### 5.3. SSRF và tiến trình không đáng tin

Một ứng dụng web có tính năng “tải nội dung từ URL do người dùng nhập” nhưng không giới hạn đích có thể trở thành kênh **server-side request forgery (SSRF)** tới metadata server. Header `Metadata-Flavor: Google` giảm một số request vô tình nhưng **không phải ranh giới bảo mật đầy đủ** nếu mã chạy trên VM có thể tạo request kèm header.

Vì vậy cần:

- Không cho người dùng điều khiển URL đích tùy ý khi ứng dụng thực hiện HTTP request từ server.
- Validate và allowlist host/scheme/port ở mức ứng dụng; kiểm soát redirect và DNS re-resolution.
- Áp sandbox hoặc cơ chế phân tách workload/process để mã không tin cậy không có đường truy cập metadata khi có thể.
- Hạn chế đặc quyền của service account để giảm hậu quả nếu token bị lộ.
- Kiểm tra HTTPS metadata endpoint trên Shielded VM nếu phù hợp; HTTPS bảo vệ kênh trao đổi nhưng **không thay thế cách ly tiến trình hoặc IAM**.

### 5.4. Người có quyền sửa startup script có thể leo thang đặc quyền

Trên Linux, startup script có thể chạy với quyền root khi máy boot; do đó `compute.instances.setMetadata` là permission nhạy cảm. Nếu một người có quyền này nhưng không được phép quản trị VM, người đó vẫn có thể chỉnh startup script nhằm thay đổi hệ thống ở lần khởi động tới.

Với project-wide metadata, permission `compute.projects.setCommonInstanceMetadata` có thể tác động đến nhiều VM thuộc project. Cần bảo vệ thay đổi thông qua IAM tối thiểu, tách nhiệm vụ, review và dấu vết thay đổi. Nếu script được trỏ tới object Cloud Storage, người có thể sửa object đó cũng có thể ảnh hưởng lệnh được chạy khi VM khởi động.

~~~mermaid
flowchart LR
    EDIT["Người được sửa metadata<br/>hoặc object bootstrap"] --> SCRIPT["Startup script"]
    SCRIPT --> ROOT["Lệnh chạy trong guest OS<br/>với đặc quyền cao"]
    ROOT --> SA["Mã chạy trên VM<br/>có thể dùng service account"]
    SA --> API["Google Cloud API / dữ liệu<br/>theo IAM và scopes"]
~~~

**Mục tiêu kiểm soát:** giảm người có thể thay script, review thay đổi artifact, phân quyền service account hẹp và lưu log audit phù hợp. Không nên chỉ dựa vào firewall VPC để ngăn một script root đã được chạy trong VM.

### 5.5. Logging và chi phí

Đọc metadata từ bên trong VM không phát sinh phí egress và không tiêu hao Compute Engine API quota thông thường. Tuy nhiên, tạo VM, disk, external IP, lưu trữ script ở Cloud Storage, gửi log và kết nối Internet có thể tính phí. Script tải gói hoặc artifact khi boot cũng có thể làm tăng thời gian VM khởi động và lưu lượng mạng.

**Không log token hoặc secrets.** Cấu hình retention, IAM đọc log và vị trí lưu trữ theo yêu cầu vận hành/dữ liệu. Nếu ghi log startup tập trung, nên đưa vào những trường như VM name, image version, startup version, elapsed time và exit status để chẩn đoán, không chứa dữ liệu cá nhân hoặc credential.

## 6. Bài thực hành: tạo VM đọc metadata khi boot

**Mục tiêu:** tạo một VM Linux không có external IPv4, không có service account và chạy một startup script đọc tên VM, Project ID và custom metadata `app-env`. Script ghi thông tin không nhạy cảm vào file cục bộ rồi thông báo trạng thái để kiểm tra.

**Bối cảnh lab:** một project thử nghiệm có Cloud Billing account hoạt động, quyền tạo Compute Engine VM/VPC/subnet, quyền đọc serial output và hạn mức VM phù hợp. Bạn chạy các lệnh dưới đây trong **Bash** qua Cloud Shell hoặc môi trường đã cài gcloud. Không thực hiện trực tiếp trên project production.

### 6.1. Sơ đồ lab và nguyên tắc an toàn

~~~mermaid
flowchart LR
    PC["Người học / Cloud Shell"] --> API["Compute Engine API"]
    API --> VM["VM mds-lab-vm<br/>Debian 12, không external IP"]
    VM --> MDS["Metadata server<br/>link-local"]
    MDS --> VM
    VM --> FILE["/var/lib/metadata-demo/info.txt"]
    VM --> LOG["Startup logs / serial output"]
~~~

| Hạng mục | Giá trị minh họa | Lý do |
| --- | --- | --- |
| Project | `YOUR_LAB_PROJECT_ID` | Thay bằng ID project được phép. |
| VPC | `mds-lab-vpc`, custom mode | Tách mạng lab khỏi mạng production. |
| Subnet | `mds-lab-subnet` tại `asia-southeast1`, `10.88.0.0/24` | Dải mẫu để cấp private IP. |
| VM | `mds-lab-vm` tại `asia-southeast1-b` | Máy Linux chạy startup script. |
| Machine type | `e2-micro` | Cấu hình nhỏ để thử; kiểm tra khả dụng/quota và giá vùng. |
| Image | `debian-12` từ `debian-cloud` | Image phổ biến có guest environment. |
| External IP | Không cấp | Lab không cần Internet inbound hoặc NAT. |
| Service account | Không gắn | Script không gọi Google Cloud API; giảm đặc quyền. |
| Custom metadata | `app-env=training` | Cấu hình môi trường không nhạy cảm. |

Không mặc định dải `10.88.0.0/24` phù hợp với tất cả project: nếu dự kiến kết nối hybrid hoặc đã có mạng trùng IP, phải chọn dải được bộ phận mạng phê duyệt. Tên, zone và machine type cũng cần kiểm tra trước khi chạy.

### 6.2. Chọn project và kiểm tra môi trường

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export REGION="asia-southeast1"
export ZONE="asia-southeast1-b"
export VM_NAME="mds-lab-vm"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project
gcloud compute machine-types describe e2-micro --zone="$ZONE"
~~~

Nếu Compute Engine API chưa bật, người có quyền thực hiện trong **project lab**:

~~~bash
gcloud services enable compute.googleapis.com
~~~

Đây là thao tác thay đổi cấu hình API của project; kiểm tra quyền và chính sách tổ chức trước khi thực hiện. Việc bật API không tự cấp quota VM hay quyền tạo mạng.

### 6.3. Tạo VPC và subnet của bài lab

~~~bash
gcloud compute networks create mds-lab-vpc \
  --subnet-mode=custom

gcloud compute networks subnets create mds-lab-subnet \
  --network=mds-lab-vpc \
  --region="$REGION" \
  --range=10.88.0.0/24
~~~

VPC thuộc phạm vi **global**, subnet có phạm vi **regional**. VM ở zone `asia-southeast1-b` sẽ dùng subnet của region `asia-southeast1`. Vì startup script chỉ truy cập metadata server nội bộ, bài lab này **không cần** Cloud NAT, VPN hoặc default Internet egress.

### 6.4. Tạo startup script local

**Trên Cloud Shell** hoặc máy đang chạy gcloud, tạo file `startup.sh` để truyền vào metadata lúc tạo VM:

~~~bash
cat > startup.sh <<'SCRIPT'
#!/usr/bin/env bash
set -Eeuo pipefail

MDS="http://metadata.google.internal/computeMetadata/v1"

metadata() {
  curl --fail --silent --show-error \
    --connect-timeout 3 --max-time 10 \
    --retry 5 --retry-delay 2 \
    -H "Metadata-Flavor: Google" \
    "$MDS/$1"
}

VM_NAME="$(metadata instance/name)"
PROJECT_ID="$(metadata project/project-id)"
APP_ENV="$(metadata instance/attributes/app-env)"

install -d -m 0755 /var/lib/metadata-demo
printf 'vm=%s\nproject=%s\nenvironment=%s\n' \
  "$VM_NAME" "$PROJECT_ID" "$APP_ENV" \
  > /var/lib/metadata-demo/info.txt
chmod 0644 /var/lib/metadata-demo/info.txt

echo "metadata-demo: bootstrap succeeded for $VM_NAME"
logger -t metadata-demo "bootstrap succeeded for $VM_NAME"
SCRIPT
~~~

**Vì sao script an toàn cho lab?** Nó không cần Internet để tải gói, không cần service account, không chứa bí mật, chỉ tạo một thư mục/file và ghi đè nội dung khi chạy lại. `echo` và `logger` cung cấp tín hiệu hoàn thành mà không in token hoặc password.

### 6.5. Tạo VM và gắn script

~~~bash
gcloud compute instances create "$VM_NAME" \
  --zone="$ZONE" \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --subnet=mds-lab-subnet \
  --no-address \
  --no-service-account \
  --no-scopes \
  --metadata=app-env=training \
  --metadata-from-file=startup-script=./startup.sh
~~~

Các flag quan trọng:

| Flag | Vai trò |
| --- | --- |
| `--no-address` | Không cấp external IPv4 cho VM. |
| `--no-service-account` và `--no-scopes` | Không gắn service account và OAuth access scopes; script không cần token để gọi API. |
| `--metadata=app-env=training` | Thêm một custom metadata value cho instance. |
| `--metadata-from-file=startup-script=./startup.sh` | CLI đọc file local và đưa nội dung vào VM metadata; guest environment chạy khi VM boot. |

**Không cố truy vấn access token** từ VM này vì không có service account được gắn vào. Nếu cần script truy cập Cloud Storage hoặc Secret Manager ở bài tập khác, hãy tạo và gắn service account riêng có quyền IAM tối thiểu, thay vì bỏ `--no-service-account` rồi mặc định dùng bất kỳ account nào có sẵn.

### 6.6. Xem trạng thái và log startup

Sau khi VM boot, từ shell gcloud bên ngoài VM:

~~~bash
gcloud compute instances describe "$VM_NAME" \
  --zone="$ZONE" \
  --format="yaml(name,status,zone,networkInterfaces,metadata.items)"

gcloud compute instances get-serial-port-output "$VM_NAME" \
  --zone="$ZONE" \
  --port=1
~~~

Trong serial output, tìm thông tin guest agent chạy startup script, mã thoát hoặc chuỗi:

~~~text
metadata-demo: bootstrap succeeded for mds-lab-vm
~~~

Serial output có thể chứa thông tin môi trường máy và bản ghi của hệ điều hành, nên chỉ chia sẻ phần cần thiết. Nếu lệnh chưa thấy chuỗi này, kiểm tra thời điểm VM đã boot xong và đợi log được ghi trước khi kết luận lỗi; khi vẫn thất bại, xem mục xử lý sự cố bên dưới.

**Tùy chọn:** nếu tổ chức đã cấu hình SSH qua **IAP TCP forwarding** và bạn có IAM/OS Login/SSH key phù hợp, hãy đăng nhập vào VM (không cần thêm external IP) để xác minh file:

~~~bash
gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --tunnel-through-iap \
  --command="sudo cat /var/lib/metadata-demo/info.txt"
~~~

Lệnh IAP chỉ hoạt động khi môi trường đã cho phép đường TCP 22 từ IAP tới VM và đủ quyền truy cập; bài lab **không tự mở firewall SSH**. Kết quả mong đợi trên VM là:

~~~text
vm=mds-lab-vm
project=YOUR_LAB_PROJECT_ID
environment=training
~~~

Đây là kết quả minh họa; Project ID thực sẽ là giá trị bạn đã chọn.

### 6.7. Cập nhật metadata và hiểu khi nào script chạy lại

**Thao tác ghi trên VM lab:**

~~~bash
gcloud compute instances add-metadata "$VM_NAME" \
  --zone="$ZONE" \
  --metadata=app-env=staging
~~~

Đọc lại metadata qua control plane:

~~~bash
gcloud compute instances describe "$VM_NAME" \
  --zone="$ZONE" \
  --format="yaml(metadata.items)"
~~~

`app-env` giờ là `staging` nhưng file `/var/lib/metadata-demo/info.txt` **vẫn phản ánh lần startup trước**, cho đến khi script được chạy lại. Để kiểm chứng idempotency trong **project lab**, bạn có thể chủ động stop/start VM:

~~~bash
# Chỉ thực hiện khi lab không phục vụ người dùng
gcloud compute instances stop "$VM_NAME" --zone="$ZONE"
gcloud compute instances start "$VM_NAME" --zone="$ZONE"
~~~

Khi máy boot lần nữa, guest environment chạy lại startup script và file mẫu sẽ ghi `environment=staging`. Trong hệ thống production, stop/start có thể làm gián đoạn dịch vụ, thay đổi external IP tạm thời (nếu có), và cần đánh giá tác động trước.

### 6.8. Dọn tài nguyên và kiểm tra chi phí

Sau thực hành, xác nhận project và tên tài nguyên đều thuộc đúng bài lab:

~~~bash
gcloud config get-value project
gcloud compute instances list --filter="name=mds-lab-vm"
gcloud compute networks subnets list --filter="name=mds-lab-subnet"
~~~

**Chỉ xóa những tài nguyên bạn đã tạo trong project lab**:

~~~bash
gcloud compute instances delete "$VM_NAME" \
  --zone="$ZONE" --quiet

gcloud compute networks subnets delete mds-lab-subnet \
  --region="$REGION" --quiet

gcloud compute networks delete mds-lab-vpc --quiet
~~~

File `startup.sh` trên Cloud Shell/laptop là tệp local phục vụ thực hành, không phải tài nguyên GCP. Bạn có thể lưu trong kho mã được review hoặc xóa thủ công khi không còn sử dụng. Đừng xóa file hoặc mạng mang cùng tên mà người khác đã tiếp quản.

**Kiểm tra sau dọn:** không còn VM, subnet và VPC của lab trong Console/gcloud. VM và disk có thể phát sinh phí trong thời gian tồn tại; chi phí đã phát sinh có thể xuất hiện trễ trên Cloud Billing. Việc đọc metadata nội bộ không làm tăng egress Internet, nhưng không có nghĩa toàn bộ bài lab miễn phí.

## 7. Xử lý sự cố metadata server và startup scripts

### 7.1. Quy trình chẩn đoán từ ngoài vào trong

Khi VM đã chạy nhưng cấu hình mong đợi chưa xuất hiện, hãy kiểm tra theo thứ tự:

1. **Đúng VM/project/zone chưa?** Đối chiếu `gcloud compute instances describe`, tên VM, zone và metadata đã gắn.
2. **Guest environment có hoạt động không?** Public image phù hợp thường có sẵn guest agent; custom image hoặc guest configuration có thể thiếu/tắt thành phần chạy startup.
3. **Metadata server có phản hồi từ bên trong VM không?** Kiểm tra DNS, HTTP endpoint, header bắt buộc, proxy và firewall của hệ điều hành.
4. **Key metadata có tồn tại không?** Xác minh chính xác `startup-script`/`startup-script-url` và custom attribute mà script đọc.
5. **Script đã chạy và thoát với mã gì?** Xem serial output, `journalctl` hoặc Windows Event Viewer.
6. **Có phụ thuộc ngoài VM không?** Script tải từ Cloud Storage, cài package, gọi Google Cloud API hoặc lấy secret có cần quyền và mạng tương ứng không?
7. **Bước nào không idempotent?** Nếu lần đầu chạy được nhưng reboot thất bại, xem thao tác ghi file, tạo user, package manager và trạng thái ứng dụng.

### 7.2. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xác minh |
| --- | --- | --- |
| `curl` tới metadata báo 403 hoặc bị từ chối | Thiếu/sai header `Metadata-Flavor`; endpoint bị hạn chế theo cấu hình; yêu cầu không hợp lệ. | Gọi lại endpoint vô hại `instance/name` với đúng header; đọc HTTP status và tài liệu xử lý lỗi. |
| `curl` báo 404 | Key hoặc đường dẫn không tồn tại, ví dụ thiếu `app-env`. | Kiểm tra metadata ở instance/project và chính tả key (có phân biệt chữ hoa/chữ thường). |
| Metadata tạm trả 429 hoặc 503 | Giới hạn tần suất hoặc server tạm bận khi boot/bảo trì. | Retry có giới hạn và backoff; tránh polling dày, đặc biệt với token. |
| Không phân giải `metadata.google.internal` | DNS/guest network configuration, resolver, proxy hoặc chỉnh sửa hệ thống. | Kiểm tra DNS trong VM; thử endpoint IP link-local `169.254.169.254` với header đúng. |
| Request đi qua proxy doanh nghiệp và lỗi | HTTP proxy hoặc `NO_PROXY` chưa loại trừ metadata endpoint. | Đảm bảo metadata được truy cập trực tiếp theo chính sách mạng; kiểm tra `NO_PROXY` và cấu hình proxy. |
| Startup script không chạy | Guest agent thiếu/tắt, key sai, không đúng image/OS, VM chưa hoàn tất boot. | Xem serial port và guest environment; xác minh khóa Linux/Windows chính xác. |
| Script chạy nhưng thoát non-zero | Lệnh lỗi, metadata thiếu, package repository lỗi hoặc script không xử lý exit code. | Xem log theo thời điểm và mã lỗi; chạy lại có kiểm soát trên VM lab. |
| `startup-script-url` không tải được | URL/object sai, không có đường egress thích hợp, IAM hoặc access scope của VM không đủ. | Kiểm tra đường dẫn object, quyền của attached service account, scopes và NAT/Private Google Access nếu cần. |
| Script chạy lại làm lỗi ứng dụng | Không idempotent, lặp cấu hình hoặc migration, phiên bản artifact thay đổi. | So sánh log lần boot trước và sau, kiểm tra script version; đưa migration/deploy ra workflow riêng. |
| Lệnh `gcloud` trong script không gọi được API | VM không có service account, scopes/IAM thiếu, API chưa bật hoặc mạng không phù hợp. | Kiểm tra danh tính, IAM, OAuth scopes, API enablement và đường kết nối; không in access token. |
| Cloud Logging không thấy log startup | Startup script chỉ ghi log trên VM/serial, không có đường thu thập vào Logging. | Xem `journalctl`, serial output; cấu hình agent/sink nếu cần log tập trung. |

### 7.3. Kiểm tra metadata server an toàn

**Trong VM Linux**:

~~~bash
# Không truy vấn token trong quá trình chẩn đoán thông thường
curl --fail --show-error --silent \
  --connect-timeout 3 --max-time 10 \
  --noproxy '*' \
  -H 'Metadata-Flavor: Google' \
  http://169.254.169.254/computeMetadata/v1/instance/name
~~~

Nếu truy vấn theo IP thành công nhưng theo DNS thất bại, cần kiểm tra resolver/DNS. Nếu cả hai đều không kết nối được, kiểm tra cấu hình mạng trong guest OS, proxy, routes và tài liệu hỗ trợ metadata server. Đừng thay VPC firewall theo phỏng đoán: metadata server có đường truy cập đặc thù, và lỗi có thể đến từ hệ điều hành.

**Kiểm tra log script Linux:**

~~~bash
sudo systemctl status google-startup-scripts.service --no-pager
sudo journalctl -u google-startup-scripts.service -b -n 100 --no-pager
~~~

Tùy image và guest environment, tên unit/log có thể khác; xem tài liệu của image nếu unit trên không có. Trên Windows, kiểm tra Application Log trong Event Viewer với nguồn sự kiện của Google Compute Engine metadata scripts.

### 7.4. Khi script tải từ Cloud Storage nhưng VM không có external IP

Không có external IP **không nhất thiết** làm VM không truy cập được Google Cloud APIs hoặc Cloud Storage. Có thể sử dụng **Private Google Access**, cấu hình DNS/route/firewall phù hợp hoặc những phương án egress khác được dịch vụ hỗ trợ. Nếu script cần tải package từ Internet công khai, có thể cần **Cloud NAT** hoặc proxy; Private Google Access không tự cung cấp đường Internet chung.

Ngoài mạng, IAM phải phù hợp. Ví dụ VM đọc một object script trong bucket private: attached service account cần permission đọc object, và access scopes không được chặn phạm vi API cần thiết. **Có IAM mà thiếu mạng, hoặc có mạng mà thiếu IAM, đều có thể thất bại.**

## 8. Áp dụng trong hệ thống triển khai và vận hành nhiều VM

### 8.1. Ví dụ: nhiều VM cùng image nhưng cấu hình khác nhau

Một doanh nghiệp triển khai backend học trực tuyến:

| Môi trường | Tên VM/nhóm | Custom metadata | Mục tiêu |
| --- | --- | --- | --- |
| Development | `course-dev-vm` | `app-env=dev` | Kết nối dịch vụ thử nghiệm và bật quan sát lỗi phù hợp. |
| Staging | `course-stage-vm` | `app-env=staging` | Chạy cấu hình gần production, không dùng secret production. |
| Production | MIG `course-prod-mig` | `app-env=prod` trong template/cấu hình tạo VM | Khởi tạo VM nhất quán và kết nối tới những dependency production được phép. |

Các máy có thể sử dụng chung logic bootstrap nhưng **không chia sẻ quyền service account hay secret giữa môi trường**. Khi một VM bị thay thế do autoscaling hoặc health check, VM mới chạy startup script; vì vậy script phải khởi tạo đúng từ trạng thái trống, không trông chờ cấu hình lưu cục bộ của VM cũ.

Với **managed instance group (MIG)**, hãy sử dụng **instance template** có metadata, image, network và service account đúng phiên bản. Cập nhật template không có nghĩa toàn bộ VM hiện có sẽ tự áp dụng mọi thay đổi ngay lập tức; cần kế hoạch cập nhật/rolling replacement phù hợp và kiểm tra sự khác biệt giữa VM cũ và VM mới.

### 8.2. Tách cấu hình, bí mật và mã triển khai

| Loại thông tin | Nơi quản lý ưu tiên | Lý do |
| --- | --- | --- |
| Tên môi trường, cờ chức năng không nhạy cảm | Custom metadata được kiểm soát | VM có thể đọc khi boot mà không phải hard-code. |
| Mật khẩu, API key, secret database | Secret Manager hoặc hệ thống secrets được duyệt | Quyền riêng, kiểm toán truy cập và cơ chế luân phiên. |
| Binary/container image của ứng dụng | Artifact Registry hoặc kho artifact tin cậy | Versioning, quét và xác minh artifact. |
| Hệ điều hành và gói nền tảng | Base image/custom image được kiểm thử | Giảm thời gian cài đặt và sai lệch khi boot. |
| Startup script | Repository có code review, build/release artifact hoặc metadata được quản lý bằng IaC | Dễ kiểm soát phiên bản và truy nguyên thay đổi. |
| IAM và VPC | Chính sách/phân quyền và cấu hình hạ tầng do nhóm quản trị sở hữu | Giảm khả năng script tự mở quyền hoặc thay đổi mạng sai phạm vi. |

Một chiến lược đáng cân nhắc:

1. CI/CD kiểm thử startup script, lint shell và xác minh không có bí mật.
2. Build image hoặc artifact đã được review, gắn **version** bất biến.
3. Cập nhật instance template cùng script URL hoặc metadata đã kiểm duyệt.
4. Triển khai một nhóm nhỏ/canary, đo thời gian bootstrap, sức khỏe ứng dụng và log startup.
5. Nếu đạt tiêu chí, tiếp tục rollout; nếu thất bại, rollback bằng template/artifact đã xác minh.

### 8.3. Startup script có thay thế Cloud Run hoặc GKE không?

Không. Startup scripts trực tiếp giải quyết **khởi tạo VM Compute Engine**. Với GKE, bạn còn phải xét Kubernetes workload, node image, init containers, DaemonSets, Workload Identity Federation và cơ chế phát hành của cluster. Với Cloud Run, ứng dụng chạy container do nền tảng quản lý, có cơ chế cấu hình và startup riêng; bạn không gắn một Linux Compute Engine `startup-script` vào Cloud Run service như gắn vào VM.

Khi chọn Compute Engine vì cần kiểm soát OS, hệ thống legacy hoặc phần mềm đặc thù, metadata scripts giúp giảm thao tác thủ công. Khi workload có thể vận hành trên GKE/Cloud Run, nên lựa chọn cách cấu hình và danh tính phù hợp với chính dịch vụ đó.

## 9. Tình huống thực hành và câu hỏi tự kiểm tra

**Tình huống:** đội backend nhận bàn giao ba VM production chạy API. Mỗi lần máy được tạo lại, người trực phải SSH cài package, ghi một file cấu hình có Project ID, rồi khởi động service. Có một file chứa password được lưu trong metadata, và script luôn tải artifact từ URL `latest`. Trong lần reboot gần đây, một VM chạy bản ứng dụng khác với hai máy còn lại.

Hãy lập kế hoạch thay đổi với các bước:

1. Tách thông tin nào có thể để trong custom metadata và thông tin nào phải chuyển vào Secret Manager.
2. Thiết kế một startup script idempotent: chuẩn bị directory, đọc metadata có kiểm tra lỗi, tải đúng artifact version, cấu hình systemd và báo exit status.
3. Xác định service account riêng cho workload, quyền truy cập secret/artifact và quyền ai được sửa metadata/script.
4. Đề xuất cách dùng instance template, canary và rollout để ba VM có cùng phiên bản cấu hình.
5. Chỉ ra log và phép kiểm tra cần thu thập sau VM boot, gồm cả trường hợp Cloud Storage/API tạm unavailable.
6. Đề xuất cách kiểm chứng reboot lần thứ hai không sinh cấu hình lặp, không chạy migration sai và không làm lộ token.

### Câu hỏi ôn tập

**1. Metadata server chỉ truy cập được khi VM có public IP và Cloud NAT?**  
Không. Metadata server có endpoint nội bộ theo ngữ cảnh VM; truy vấn không cần Internet egress thông thường.

**2. Vì sao phải gửi `Metadata-Flavor: Google`? Header này có phải secret không?**  
Đây là header bắt buộc cho yêu cầu metadata có chủ đích; nó không phải secret và không thay thế cách ly tiến trình hoặc IAM.

**3. Đặt `startup-script` mới vào metadata của VM đang chạy có khiến script tự chạy ngay không?**  
Không. Thông thường script chạy khi VM boot; muốn chạy lại phải thao tác chủ động theo guest environment và quy trình vận hành.

**4. Dùng `startup-script-url` thì VM cần điều kiện gì?**  
Cần URL/object đúng, đường mạng phù hợp và permission đọc object của attached service account (cùng access scopes khi áp dụng).

**5. Tại sao quyền sửa metadata nguy hiểm dù người dùng không có SSH vào VM?**  
Vì startup script Linux có thể chạy với quyền root khi boot, và từ đó có thể sử dụng quyền của service account gắn với VM.

**6. Có nên ghi OAuth access token được cấp qua metadata server vào Cloud Logging để debug?**  
Không. Token là thông tin xác thực nhạy cảm; chỉ ghi mã lỗi, danh tính không nhạy cảm và thông tin trạng thái phù hợp.

**7. Vì sao startup script cần idempotent khi triển khai qua MIG?**  
VM có thể được tạo thay thế hoặc reboot nhiều lần; script phải tạo kết quả nhất quán mà không nhân đôi cấu hình hoặc gây hỏng dữ liệu.

**8. Vì sao một VM không có service account vẫn đọc được `instance/name`?**  
Đọc metadata hệ thống từ bên trong VM khác với việc gọi Google Cloud APIs bằng OAuth credential. Không cần service account để đọc tên VM.

## Tài liệu Google Cloud để đối chiếu khi triển khai

- **About VM metadata:** https://cloud.google.com/compute/docs/metadata/overview — cấu trúc metadata, endpoint và an toàn truy cập.
- **View and query VM metadata:** https://cloud.google.com/compute/docs/metadata/querying-metadata — cú pháp HTTP, header, truy vấn thay đổi và điều kiện HTTPS.
- **Set and remove custom metadata:** https://cloud.google.com/compute/docs/metadata/setting-custom-metadata — metadata cấp project/VM, quyền sửa và giới hạn.
- **About startup scripts:** https://cloud.google.com/compute/docs/instances/startup-scripts — vòng đời và yêu cầu guest environment.
- **Use startup scripts on Linux VMs:** https://cloud.google.com/compute/docs/instances/startup-scripts/linux — khóa, gcloud, logs và chạy lại.
- **Use startup scripts on Windows VMs:** https://cloud.google.com/compute/docs/instances/startup-scripts/windows — các khóa PowerShell/CMD và Windows Event Viewer.
- **Guest agent functionality:** https://cloud.google.com/compute/docs/images/guest-agent-functions — trách nhiệm và khả năng quản lý metadata scripts.
- **Troubleshoot metadata server access:** https://cloud.google.com/compute/docs/troubleshooting/troubleshoot-metadata-server — DNS, proxy, HTTP errors và lỗi token.
- **Service accounts on Compute Engine:** https://cloud.google.com/compute/docs/access/service-accounts — danh tính, IAM roles và access scopes.
- **Secret Manager:** https://cloud.google.com/secret-manager/docs/overview — quản lý bí mật thay vì đặt trong metadata.
- **Managed instance groups:** https://cloud.google.com/compute/docs/instance-groups — template, cập nhật và tự động quản lý nhóm VM.

Tên flag, quyền IAM, tính năng HTTPS metadata endpoint và guest agent có thể thay đổi theo phiên bản sản phẩm. Hãy kiểm tra tài liệu chính thức, loại image và cấu hình của project trước khi dùng trên production. Một hệ thống được chuẩn bị tốt khi **VM đọc được metadata đúng phạm vi, khởi động nhất quán, không lộ thông tin xác thực, có log đủ để chẩn đoán và có thể triển khai lại bằng cùng một quy trình đã kiểm thử**.
