# Chọn project, region và zone mặc định cho gcloud

## 1. Mục tiêu và bối cảnh

Khi làm việc với **Google Cloud CLI (`gcloud`)** trên máy cá nhân, Cloud Shell hoặc trong quy trình tự động hóa, gần như mọi thao tác đều cần xác định **project** và một số thao tác còn cần **region** hoặc **zone**. Nếu phải nhập lại các tham số này cho từng lệnh, người dùng dễ gõ nhầm, nhất là khi cùng quản lý môi trường thử nghiệm và production.

Ví dụ, một nhóm đang học về **Compute Engine, GKE, Cloud Run, IAM, VPC, lưu trữ và cơ sở dữ liệu** trên Google Cloud. Nhóm có project dành cho phát triển và project dành cho production, còn các tài nguyên máy ảo đặt ở một region đã chọn. Cấu hình mặc định phù hợp giúp:

- Rút gọn lệnh thường dùng và thống nhất vị trí triển khai trong phiên làm việc.
- Giảm nguy cơ tạo hoặc kiểm tra tài nguyên ở sai project hay sai zone.
- Dễ thay đổi ngữ cảnh giữa môi trường phát triển, kiểm thử và production.
- Có điểm khởi đầu rõ ràng cho việc kiểm soát IAM, chi phí, vận hành và độ tin cậy.

Sau bài học, bạn sẽ biết cách **chọn, thiết lập, xem, ghi đè và hủy** giá trị mặc định của project, region, zone; đồng thời hiểu vì sao các giá trị này không tự động áp dụng cho mọi dịch vụ Google Cloud.

> **Điều quan trọng:** Đặt mặc định trong `gcloud` chỉ thay đổi cách **công cụ dòng lệnh chọn tham số cho những lệnh có hỗ trợ**. Nó không di chuyển tài nguyên, không thay đổi vùng của tài nguyên đã tạo, không tự cấp quyền IAM và không bảo đảm dịch vụ khác cũng sử dụng cùng vùng.

## 2. Phân biệt project, region và zone

Ba khái niệm nằm ở những cấp khác nhau trong hệ thống tài nguyên Google Cloud:

| Khái niệm | Vai trò | Ví dụ | Ảnh hưởng khi chọn sai |
| --- | --- | --- | --- |
| **Project** | Ranh giới quản lý tài nguyên, API, IAM và theo dõi chi phí/billing | `acme-dev-123` | Lệnh có thể chạy trên môi trường hoặc dữ liệu không dự định |
| **Region** | Khu vực địa lý chứa các zone, dùng cho nhiều tài nguyên khu vực | `asia-southeast1` (Singapore) | Có thể ảnh hưởng độ trễ, nơi lưu dữ liệu, khả năng sẵn có và giá |
| **Zone** | Một miền triển khai trong region, phù hợp các tài nguyên theo zone | `asia-southeast1-a` | Tài nguyên zonal có thể không nằm ở vị trí mong muốn |

Quan hệ giữa chúng được hình dung như sau:

```text
Google Cloud
└── Project: acme-dev-123
    ├── Region: asia-southeast1 (Singapore)
    │   ├── Zone: asia-southeast1-a
    │   ├── Zone: asia-southeast1-b
    │   └── Zone: asia-southeast1-c
    └── Region khác...
```

Đây là **sơ đồ ngữ cảnh**, không phải cây phân cấp quản trị hoàn chỉnh: trong thực tế, một project có thể chứa tài nguyên ở nhiều region và zone. Google Cloud còn có phân cấp **Organization → Folder → Project** để quản trị IAM và chính sách. **Region và zone là vị trí triển khai**, không phải cấp thay thế Folder hoặc Project.

### Tên project, Project ID và Project number

Một project có ba thông tin dễ bị nhầm:

- **Project name:** tên hiển thị, có thể thay đổi, không nhất thiết duy nhất.
- **Project ID:** định danh dạng chuỗi, thường được dùng cho `--project` và `gcloud config set project`; duy nhất trên Google Cloud.
- **Project number:** số định danh do Google cấp, thường xuất hiện trong đường dẫn tài nguyên và danh tính dịch vụ.

Trong các ví dụ bên dưới, `acme-dev-123` là **Project ID minh họa**, không phải project thật có sẵn trong tài khoản của bạn. Hãy thay bằng Project ID được cấp cho môi trường học tập hoặc công việc.

## 3. Chuẩn bị Google Cloud CLI và kiểm tra ngữ cảnh

Bạn có thể chạy `gcloud` trên máy đã cài **Google Cloud CLI** hoặc trong **Cloud Shell**. Cloud Shell thường có sẵn CLI và ngữ cảnh đăng nhập; môi trường local có thể cần khởi tạo lần đầu:

```bash
# Kiểm tra CLI đã có trên máy
gcloud version

# Khởi tạo/cấu hình tương tác nếu cần
gcloud init

# Kiểm tra tài khoản đã đăng nhập cho gcloud CLI
gcloud auth list

# Liệt kê các project mà tài khoản có quyền xem
gcloud projects list
```

Nếu sử dụng máy cá nhân và chưa đăng nhập, có thể dùng `gcloud auth login` theo chính sách của tổ chức. **Tài khoản đang xác thực và project mặc định là hai thiết lập khác nhau**: đăng nhập thành công không có nghĩa tài khoản có quyền thao tác trên project đang chọn.

Lưu ý thêm: `gcloud auth login` phục vụ **gcloud CLI**, còn chương trình sử dụng **Application Default Credentials (ADC)** có cơ chế xác thực riêng. Thay đổi project mặc định của CLI không đồng nghĩa tự thay đổi mọi cấu hình ADC hoặc quota project của ứng dụng.

Để biết ngay ngữ cảnh hiện hành:

```bash
gcloud config list
gcloud config get-value project
gcloud config get-value compute/region
gcloud config get-value compute/zone
```

Nếu một thuộc tính chưa được cấu hình, lệnh `get-value` có thể hiển thị `(unset)`. Đây là trạng thái hợp lệ: CLI có thể hỏi thêm giá trị, suy ra từ tùy chọn khác hoặc báo thiếu tham số, tùy lệnh đang chạy.

## 4. Cách chọn project mặc định

### Bước 1: Xác định đúng Project ID

Trong giao diện Google Cloud Console, hãy chọn project và xem **Project ID**. Nếu dùng CLI, bạn có thể liệt kê những project mình được phép xem:

```bash
gcloud projects list --format="table(projectId,name,projectNumber)"
```

Việc không thấy một project trong danh sách có thể do quyền liệt kê hoặc quyền truy cập; không nên tự suy luận rằng project đó không tồn tại. Khi không chắc, hãy xác nhận Project ID với người quản trị.

### Bước 2: Lưu Project ID vào cấu hình `gcloud` đang hoạt động

```bash
gcloud config set project acme-dev-123
```

Kiểm tra lại:

```bash
gcloud config get-value project
```

Kỳ vọng kết quả:

```text
acme-dev-123
```

Từ lúc này, các lệnh hỗ trợ thuộc tính project sẽ dùng project vừa đặt **nếu không được ghi đè bằng tham số hoặc cấu hình có độ ưu tiên cao hơn**. Ví dụ, lệnh đọc tài nguyên sau sẽ hướng đến project mặc định:

```bash
gcloud compute instances list
```

Lệnh trên chỉ liệt kê VM. Nó có thể yêu cầu Compute Engine API đã được bật và tài khoản có quyền phù hợp; kết quả không có VM không chứng minh project không tồn tại.

### Ghi đè project cho một lệnh

Không cần đổi cấu hình lưu sẵn khi chỉ muốn xem một project khác:

```bash
gcloud compute instances list --project=acme-test-456
```

Trong lệnh này, `--project=acme-test-456` áp dụng cho **chính lệnh đó**; project mặc định vẫn là `acme-dev-123`. Thói quen chỉ rõ `--project` đặc biệt hữu ích trong script, khi làm việc với production và khi chia sẻ lệnh giữa nhiều người.

## 5. Chọn region mặc định cho các lệnh Compute Engine

Một region thường chứa nhiều zone. Trước khi chọn, hãy cân nhắc:

1. **Vị trí người dùng và độ trễ:** ứng dụng phục vụ khách hàng ở Việt Nam có thể thử đo độ trễ đến `asia-southeast1` (Singapore) và các region phù hợp khác.
2. **Yêu cầu vị trí dữ liệu và tuân thủ:** không mặc định rằng region gần nhất đáp ứng mọi yêu cầu lưu trữ dữ liệu.
3. **Dịch vụ, loại máy, quota và tính năng:** không phải dịch vụ, machine type hoặc tính năng nào cũng hỗ trợ tại mọi region.
4. **Độ tin cậy và phục hồi:** cân nhắc phân bố zone, kiến trúc đa region nếu có yêu cầu, cùng RTO/RPO.
5. **Chi phí:** giá tài nguyên, truyền dữ liệu giữa các vùng, lưu trữ và kết nối khác nhau theo kiến trúc.

Tra cứu các region khả dụng đối với Compute Engine:

```bash
gcloud compute regions list
```

Đặt region mặc định:

```bash
gcloud config set compute/region asia-southeast1
```

Xem lại:

```bash
gcloud config get-value compute/region
```

Kết quả kỳ vọng:

```text
asia-southeast1
```

Thuộc tính `compute/region` được các lệnh `gcloud compute` có hỗ trợ dùng làm **region mặc định**. Một số lệnh của dịch vụ khác có tên tham số cũng là `--region` nhưng dùng **cấu hình riêng** hoặc yêu cầu chỉ rõ region. Không coi `compute/region` là “region toàn Google Cloud”.

Ví dụ, khi thao tác với **Cloud Run**, có thể chỉ định rõ `--region` cho lệnh và thiết lập thuộc tính riêng `run/region` nếu thường xuyên dùng Cloud Run:

```bash
# Đọc danh sách dịch vụ Cloud Run tại region đã chỉ định
gcloud run services list --project=acme-dev-123 --region=asia-southeast1

# Mặc định riêng cho các lệnh Cloud Run hỗ trợ thuộc tính này
gcloud config set run/region asia-southeast1
gcloud config get-value run/region
```

Với **Cloud Storage**, vị trí bucket được chọn theo `location` khi tạo bucket; với **Cloud SQL**, khu vực triển khai phải được đánh giá theo tham số của chính dịch vụ. Việc đặt `compute/region` không làm thay đổi vị trí dữ liệu trong bucket hay database đã tồn tại.

## 6. Chọn zone mặc định cho tài nguyên theo zone

Các tài nguyên **zonal**, chẳng hạn nhiều VM Compute Engine và persistent disk zonal, cần xác định zone. Zone được chọn phải **thuộc region tương ứng**.

Liệt kê các zone Compute Engine có thể chọn:

```bash
gcloud compute zones list
```

Ví dụ, nếu region là `asia-southeast1`, một zone thuộc region này là `asia-southeast1-a`:

```bash
gcloud config set compute/zone asia-southeast1-a
gcloud config get-value compute/zone
```

Kết quả kỳ vọng:

```text
asia-southeast1-a
```

Giờ có thể kiểm tra các thuộc tính liên quan trong cấu hình đang hoạt động:

```bash
gcloud config list
```

Ví dụ một phần kết quả (các trường khác có thể xuất hiện):

```ini
[core]
project = acme-dev-123
[compute]
region = asia-southeast1
zone = asia-southeast1-a
```

### Khi nào không nên đặt zone cố định?

Nếu công việc chủ yếu với **dịch vụ regional** hoặc thường chuyển giữa nhiều zone, bạn có thể chỉ giữ region mặc định và chỉ rõ `--zone` khi lệnh thực sự cần:

```bash
gcloud config unset compute/zone
```

Đối với lệnh nhắm vào VM cụ thể, chỉ rõ zone tránh nhầm vị trí:

```bash
# Lệnh chỉ đọc; thay tên VM, project và zone bằng giá trị thực
gcloud compute instances describe VM_NAME \
  --project=acme-dev-123 \
  --zone=asia-southeast1-a
```

Ví dụ trên dùng cú pháp xuống dòng của **Bash**. Nếu đang dùng **PowerShell** trên Windows, nên nhập nguyên lệnh trên một dòng:

```powershell
gcloud compute instances describe VM_NAME --project=acme-dev-123 --zone=asia-southeast1-a
```

Khi tạo cluster **GKE regional**, tài nguyên được quản lý theo region và có thể trải trên nhiều zone tùy cấu hình; vì vậy không nên áp đặt suy luận rằng “đã có zone mặc định thì mọi cluster GKE sẽ nằm tại đúng zone đó”. Khi lập script triển khai, luôn chỉ rõ `--region` hoặc `--zone` theo loại cluster.

## 7. Quy trình nhanh: cấu hình một môi trường học tập

Nếu đã có project, tài khoản và quyền phù hợp, bộ lệnh sau là cấu hình tối thiểu cho các bài thực hành Compute Engine. Các giá trị đều là **ví dụ**, cần thay Project ID thật:

```bash
# 1. Đặt project cho các lệnh không chỉ rõ --project
gcloud config set project acme-dev-123

# 2. Đặt khu vực mặc định cho các lệnh Compute Engine hỗ trợ
gcloud config set compute/region asia-southeast1

# 3. Đặt zone thuộc region vừa chọn
gcloud config set compute/zone asia-southeast1-a

# 4. Kiểm tra cả ba thuộc tính đã được lưu
gcloud config get-value project
gcloud config get-value compute/region
gcloud config get-value compute/zone
```

Một quy trình làm việc an toàn là **đọc cấu hình trước → thực hiện lệnh → xác minh tài nguyên/đầu ra sau lệnh**. Với tài nguyên tạo mới, cần kiểm tra cả quyền, quota, chi phí dự kiến và loại dịch vụ trước khi triển khai.

## 8. Quản lý nhiều project bằng named configurations

Người dùng có thể cần làm việc đồng thời với nhiều môi trường. `gcloud` hỗ trợ **named configurations**: mỗi cấu hình lưu một bộ thuộc tính như project, region và zone. Chỉ một cấu hình được kích hoạt làm cấu hình mặc định tại một thời điểm trong ngữ cảnh CLI hiện hành.

Ví dụ tạo cấu hình phục vụ học tập:

```bash
# Tạo cấu hình mới và kích hoạt nó
gcloud config configurations create training

# Đặt thuộc tính cho cấu hình training
gcloud config set project acme-dev-123
gcloud config set compute/region asia-southeast1
gcloud config set compute/zone asia-southeast1-a

# Kiểm tra cấu hình đã tạo và cấu hình đang active
gcloud config configurations list
gcloud config list
```

Tên `training` chỉ là ví dụ; nếu đã tồn tại một cấu hình cùng tên, hãy dùng tên khác hoặc kích hoạt cấu hình hiện có.

Nếu có cấu hình `production` được tạo và thiết lập riêng từ trước, chuyển ngữ cảnh bằng:

```bash
gcloud config configurations activate production
gcloud config list

# Quay lại cấu hình học tập
gcloud config configurations activate training
```

Trong script chỉ đọc, có thể chọn cấu hình cho từng lệnh qua `--configuration` mà không cần đổi cấu hình đang active:

```bash
gcloud --configuration=training config list
```

**Gợi ý cho môi trường nhiều project:** đặt tên cấu hình rõ ràng, ví dụ `training`, `staging`, `production`; kiểm tra project trước các lệnh có khả năng làm thay đổi tài nguyên. Named configuration giúp giảm nhầm lẫn nhưng **không phải cơ chế phân quyền**; IAM và chính sách tổ chức vẫn quyết định tài khoản thực hiện được những gì.

## 9. Thứ tự ưu tiên: cờ lệnh, biến môi trường và cấu hình lưu sẵn

Trong những lệnh có hỗ trợ thuộc tính tương ứng, hãy hiểu thứ tự thường gặp:

1. **Cờ chỉ rõ trên lệnh** như `--project`, `--region`, `--zone`.
2. **Biến môi trường Cloud SDK** tương ứng.
3. **Thuộc tính của cấu hình `gcloud` đang hoạt động**.
4. Khi chưa có giá trị, cách xử lý mặc định của chính lệnh hoặc dịch vụ: hỏi tham số, suy ra giá trị hoặc báo lỗi.

Ví dụ chỉ đặt project cho **phiên Bash hiện tại** mà không ghi vào file cấu hình:

```bash
export CLOUDSDK_CORE_PROJECT=acme-test-456
gcloud config get-value project
```

Tương tự trên **PowerShell**:

```powershell
$env:CLOUDSDK_CORE_PROJECT = "acme-test-456"
gcloud config get-value project
```

Hai ví dụ thay đổi biến môi trường của shell hiện tại (và các tiến trình con). Vì biến môi trường có thể **ghi đè thuộc tính đã lưu**, kết quả một lệnh có thể khác với những gì người dùng nhớ đã đặt qua `gcloud config set`.

Các biến liên quan thường gặp:

| Thuộc tính `gcloud` | Biến môi trường | Cờ lệnh thường dùng |
| --- | --- | --- |
| `core/project` (đặt bằng `project`) | `CLOUDSDK_CORE_PROJECT` | `--project` |
| `compute/region` | `CLOUDSDK_COMPUTE_REGION` | `--region` với lệnh phù hợp |
| `compute/zone` | `CLOUDSDK_COMPUTE_ZONE` | `--zone` với lệnh phù hợp |

**Lưu ý:** không phải mọi lệnh đều dùng ba thuộc tính này. Chẳng hạn `--region` của Cloud Run thuộc ngữ cảnh Cloud Run; không nên dựa vào `CLOUDSDK_COMPUTE_REGION` để định vị dịch vụ Cloud Run. Cần kiểm tra `gcloud <nhóm-lệnh> <lệnh> --help` khi không rõ hành vi mặc định.

Với **CI/CD và hạ tầng dưới dạng mã (IaC)**, hãy xác định project và location một cách tường minh trong pipeline hoặc biến cấu hình được quản lý, thay vì phụ thuộc vào cấu hình cá nhân trên máy phát triển. Điều này giúp tái hiện việc triển khai và kiểm soát quyền dịch vụ, chi phí và tài nguyên theo môi trường.

## 10. Các lỗi thường gặp và cách tự kiểm tra

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Lệnh thao tác sai project | Cấu hình đang active khác dự kiến; có cờ `--project` hoặc biến môi trường ghi đè | Chạy `gcloud config configurations list`, `gcloud config get-value project` và xem lại cờ/biến môi trường |
| Báo không tìm thấy VM dù đã thấy ở Console | Nhầm project hoặc zone | Xác nhận Project ID, tên VM và zone; chạy `gcloud compute instances list --project=PROJECT_ID` |
| Lỗi thiếu region/zone | Thuộc tính chưa đặt hoặc lệnh cần vị trí cụ thể | Dùng `gcloud config list` rồi bổ sung `--region`/`--zone` đúng ngữ cảnh |
| Zone không thuộc region mong muốn | Ví dụ chọn `asia-southeast1` nhưng zone `us-central1-a` | Kiểm tra danh sách zone và đồng bộ lại region/zone trước khi tạo tài nguyên |
| `PERMISSION_DENIED` hoặc `403` | Tài khoản thiếu IAM, API chưa bật hoặc policy chặn | Kiểm tra `gcloud auth list`, project, API và quyền; cấu hình mặc định không cấp thêm quyền |
| Cloud Run vẫn yêu cầu region | `compute/region` không phải region mặc định chung | Chỉ rõ `--region` hoặc kiểm tra `run/region` |
| Vùng mong muốn không hỗ trợ dịch vụ/loại máy | Khác biệt về danh mục sản phẩm, quota hoặc vùng | Tra cứu availability, quota, machine type và cấu hình dịch vụ tại region dự định |
| Lệnh ở terminal mới cho kết quả khác | Biến môi trường, cấu hình được kích hoạt hoặc tài khoản khác | Kiểm tra cấu hình active, `gcloud auth list` và các biến `CLOUDSDK_*` tại terminal đó |

Nếu muốn hủy mặc định đã lưu trong cấu hình đang hoạt động:

```bash
gcloud config unset compute/zone
gcloud config unset compute/region
gcloud config unset project
```

Những lệnh này chỉ xóa thuộc tính cấu hình CLI, **không xóa project, VM, VPC hoặc bất kỳ tài nguyên đám mây nào**. Nếu có biến môi trường ghi đè, giá trị hiệu lực vẫn có thể xuất hiện cho đến khi biến đó được gỡ khỏi phiên shell.

## 11. Bài thực hành kiểm chứng

Hãy thực hiện trên một project dành cho học tập mà bạn có quyền truy cập. Bài tập này chỉ yêu cầu thay đổi **cấu hình CLI và đọc danh sách tài nguyên**, không yêu cầu tạo dịch vụ có tính phí.

**Bài 1 – Xác định ngữ cảnh**

1. Chạy `gcloud auth list`, `gcloud projects list` và xác định Project ID được phép sử dụng.
2. Chạy `gcloud config list`, ghi lại project, compute/region và compute/zone đang có.
3. Phân biệt Project ID với Project name hiển thị trong Console.

**Bài 2 – Thiết lập mặc định**

1. Chọn một region có hỗ trợ Compute Engine, chẳng hạn `asia-southeast1` nếu phù hợp quyền và mục tiêu của bạn.
2. Dùng `gcloud compute zones list` để chọn một zone thuộc region đó.
3. Thiết lập ba thuộc tính bằng `gcloud config set`, sau đó đọc lại từng giá trị bằng `get-value`.

**Bài 3 – Kiểm tra cơ chế ghi đè**

1. Chạy `gcloud compute instances list` trên project mặc định.
2. Chạy `gcloud compute instances list --project=PROJECT_ID_KHAC`, với Project ID khác mà bạn được phép xem.
3. Kiểm tra lại `gcloud config get-value project` và giải thích vì sao cấu hình lưu sẵn không đổi.

**Bài 4 – Làm việc với nhiều môi trường**

1. Tạo named configuration riêng cho môi trường học tập; đặt lại project, region và zone.
2. Chạy `gcloud config configurations list` để xác nhận cấu hình đang active.
3. Đề xuất cách tổ chức cấu hình dev/prod để giảm nguy cơ thao tác nhầm và giải thích vì sao IAM vẫn cần thiết.

Bạn hoàn thành bài khi có thể trả lời ba câu hỏi: **Tài nguyên của lệnh sắp chạy thuộc project nào? Vị trí của nó được quyết định bằng tham số nào? Giá trị đó lấy từ cờ lệnh, biến môi trường hay cấu hình `gcloud`?**

## 12. Tài liệu Google Cloud chính thức

- [Google Cloud CLI – cài đặt và khởi tạo](https://cloud.google.com/sdk/docs/install)
- [Quản lý cấu hình gcloud CLI](https://cloud.google.com/sdk/docs/configurations)
- [gcloud config set](https://cloud.google.com/sdk/gcloud/reference/config/set)
- [gcloud config get-value](https://cloud.google.com/sdk/gcloud/reference/config/get-value)
- [gcloud config configurations](https://cloud.google.com/sdk/gcloud/reference/config/configurations)
- [Regions and zones – Compute Engine](https://cloud.google.com/compute/docs/regions-zones)
- [Cloud Run locations](https://cloud.google.com/run/docs/locations)
- [Resource hierarchy – Organization, Folder, Project](https://cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy)

Khi thực hành với Google Cloud, hãy kiểm tra cú pháp `--help` và tài liệu dịch vụ tại thời điểm thao tác vì khả năng hỗ trợ region, zone, cờ lệnh và thuộc tính cấu hình có thể thay đổi theo phiên bản.
