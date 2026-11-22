# Truy vấn, lọc và định dạng kết quả gcloud

Trong Google Cloud, một tổ chức thường quản lý nhiều **project**, mỗi project chứa các tài nguyên như mạng **VPC**, máy ảo **Compute Engine**, cụm **Google Kubernetes Engine (GKE)**, ứng dụng **Cloud Run**, dịch vụ lưu trữ và cơ sở dữ liệu. Khi số lượng tài nguyên tăng lên, việc xem danh sách dài trong Console không còn đủ để kiểm kê, đối chiếu cấu hình hoặc kiểm tra vận hành. **Google Cloud CLI (`gcloud`)** cho phép truy vấn thông tin tài nguyên, lọc những đối tượng cần quan tâm và xuất kết quả theo định dạng thích hợp cho người đọc hoặc chương trình tự động.

Bài học thuộc chương **Công cụ và môi trường GCP** của mô-đun **CLOUD_PROVIDERS_GCP**. Mục tiêu là xây dựng kỹ năng dùng `gcloud` để tìm đúng tài nguyên, quan sát trạng thái, phát hiện cấu hình cần kiểm tra và cung cấp dữ liệu cho các quy trình quản trị, bảo mật, triển khai và theo dõi độ tin cậy, chi phí. Những ví dụ bên dưới là thao tác **đọc**; chúng không tạo hoặc sửa tài nguyên Google Cloud.

## 1. Mô hình truy vấn của gcloud

### 1.1. Cấu trúc lệnh

Một truy vấn điển hình có cấu trúc:

~~~text
gcloud <nhóm-lệnh> <tài-nguyên> <thao-tác> [đối-số] [các-cờ]
~~~

Ví dụ:

~~~bash
# Liệt kê các VM thuộc một project.
gcloud compute instances list --project=my-prod-project

# Xem một VM cụ thể ở đúng zone.
gcloud compute instances describe web-01 \
  --project=my-prod-project \
  --zone=asia-southeast1-a
~~~

Trong các lệnh trên:

- `compute instances` xác định loại tài nguyên cần truy vấn.
- `list` lấy tập hợp tài nguyên; `describe` lấy thông tin chi tiết của một tài nguyên xác định.
- `--project` chỉ định **project ID**, tránh phụ thuộc vào project mặc định trên máy.
- `--zone` xác định vị trí của tài nguyên theo yêu cầu lệnh `describe`.

Những ví dụ sử dụng `my-prod-project`, `web-01` và `asia-southeast1-a` chỉ là dữ liệu minh họa. Khi thực hành, thay chúng bằng project, tên tài nguyên và vị trí hợp lệ mà tài khoản của bạn có quyền xem.

### 1.2. `list`, `describe` và các nhóm lệnh liên quan

| Nhu cầu | Ví dụ lệnh | Kết quả mong đợi |
| --- | --- | --- |
| Liệt kê project có quyền truy cập | `gcloud projects list` | Danh sách project và metadata liên quan. |
| Liệt kê máy ảo | `gcloud compute instances list --project=my-prod-project` | Danh sách VM kèm các thuộc tính phổ biến. |
| Xem chi tiết một VM | `gcloud compute instances describe web-01 --zone=asia-southeast1-a --project=my-prod-project` | Bản ghi chi tiết của VM. |
| Liệt kê VPC | `gcloud compute networks list --project=my-prod-project` | Các mạng VPC trong project. |
| Liệt kê cụm GKE | `gcloud container clusters list --project=my-prod-project` | Các cụm Kubernetes được quản lý bởi GKE. |
| Liệt kê Cloud SQL | `gcloud sql instances list --project=my-prod-project` | Các instance cơ sở dữ liệu Cloud SQL. |
| Liệt kê Cloud Run | `gcloud run services list --project=my-prod-project --region=asia-southeast1` | Các dịch vụ Cloud Run trong region đã chỉ định. |
| Đọc IAM policy của project | `gcloud projects get-iam-policy my-prod-project` | Policy IAM; đây là một lệnh đọc khác với `list`/`describe`. |

`list` thường là điểm xuất phát để tìm tài nguyên. Khi đã biết tài nguyên cần khảo sát, dùng `describe` để xem thêm các trường không có trong bảng mặc định. Không phải mọi nhóm lệnh đều hỗ trợ chính xác cùng một tập cờ: cần xem `gcloud <nhóm-lệnh> <lệnh> --help` khi chuyển sang loại dịch vụ khác.

### 1.3. Ngữ cảnh của truy vấn: cấu hình, tài khoản và quyền

Trước khi kết luận một tài nguyên “không tồn tại”, hãy kiểm tra truy vấn đang chạy với tài khoản và project nào:

~~~bash
# Xem project đang được chọn mặc định.
gcloud config get-value project

# Xem các tài khoản đã được đăng nhập vào CLI và tài khoản đang hoạt động.
gcloud auth list

# Xem cấu hình gcloud đang dùng.
gcloud config list
~~~

Các cờ như `--project`, `--region`, `--zone` giúp truy vấn tường minh hơn. **IAM quyết định khả năng đọc thực tế**: `--filter` không vượt qua quyền truy cập; kết quả rỗng hoặc lỗi quyền truy cập có thể liên quan tới sai project, sai vị trí, API chưa bật hoặc thiếu quyền. Với automation, ưu tiên danh tính phù hợp và quyền tối thiểu, không phụ thuộc vào tài khoản cá nhân của người chạy.

## 2. Chọn trường bằng `--format`

### 2.1. Vì sao cần định dạng kết quả?

Kết quả mặc định của `gcloud ... list` thường được tối ưu để đọc trên terminal, nhưng không nhất thiết chứa mọi trường. Cờ `--format` quyết định **cách biểu diễn kết quả**: hiển thị bảng ngắn, lấy một giá trị, xuất JSON/YAML hoặc tạo CSV. Việc đổi định dạng không tự thay đổi tài nguyên và cũng không cấp thêm quyền đọc.

Ví dụ xuất danh sách VM theo các cách:

~~~bash
# Bảng ngắn, dễ đọc.
gcloud compute instances list \
  --project=my-prod-project \
  --format="table(name,zone.basename(),machineType.basename(),status)"

# Một tên VM trên mỗi dòng.
gcloud compute instances list \
  --project=my-prod-project \
  --format="value(name)"

# Dữ liệu JSON để chương trình khác phân tích.
gcloud compute instances list \
  --project=my-prod-project \
  --format="json"

# Dữ liệu YAML để người vận hành đọc chi tiết.
gcloud compute instances list \
  --project=my-prod-project \
  --format="yaml"

# CSV để nhập vào bảng tính hoặc báo cáo.
gcloud compute instances list \
  --project=my-prod-project \
  --format="csv(name,zone.basename(),status)"
~~~

### 2.2. Chọn định dạng theo mục đích

| Định dạng | Ví dụ | Tình huống phù hợp | Điều cần nhớ |
| --- | --- | --- | --- |
| `table(...)` | `--format="table(name,status)"` | Xem nhanh nhiều tài nguyên trên terminal. | Được thiết kế cho người đọc; tiêu đề và cột không phải hợp đồng dữ liệu cho script. |
| `value(...)` | `--format="value(name)"` | Lấy danh sách ID/tên cho một bước xử lý tiếp theo. | Đặc biệt hữu ích khi chọn một trường; vẫn cần xử lý trường rỗng và tên có ký tự đặc biệt. |
| `json` | `--format="json"` | Xử lý dữ liệu có cấu trúc, bao gồm trường lồng nhau và danh sách. | Một trường có thể là chuỗi, đối tượng hoặc mảng; kiểm tra cấu trúc thực tế trước khi phân tích. |
| `yaml` | `--format="yaml"` | Đọc cấu hình và thuộc tính tài nguyên chi tiết. | Dễ đọc, nhưng không nên phân tích bằng cách cắt chuỗi thủ công. |
| `csv(...)` | `--format="csv(name,status)"` | Xuất dữ liệu dạng bảng cho kiểm kê. | Trường có dấu phẩy hoặc ký tự đặc biệt cần được xử lý bằng công cụ đọc CSV. |
| `list(...)` | `--format="list(name,status)"` | Xem các trường dạng mục trên nhiều bản ghi. | Phù hợp khi bảng quá rộng hoặc cần xem từng bản ghi theo chiều dọc. |

Một số định dạng cho phép chỉ định trường trong dấu ngoặc. Chẳng hạn:

~~~bash
# JSON đầy đủ của mỗi VM trong danh sách.
gcloud compute instances list --project=my-prod-project --format="json"

# JSON chỉ gồm các trường phục vụ báo cáo.
gcloud compute instances list \
  --project=my-prod-project \
  --format="json(name,status,zone)"
~~~

Đối với ứng dụng tự động hóa cần nhiều trường hoặc dữ liệu lồng nhau, `json` thường dễ kiểm tra và xử lý một cách nhất quán hơn bảng văn bản. Tuy nhiên, các trường do API trả về có thể thay đổi theo loại tài nguyên, quyền truy cập và phiên bản công cụ.

### 2.3. Trường dữ liệu và phép biến đổi `basename()`

Một số giá trị trong kết quả Google Cloud là URL tham chiếu tới tài nguyên, ví dụ:

~~~text
https://www.googleapis.com/compute/v1/projects/my-prod-project/zones/asia-southeast1-a
~~~

Nếu chỉ cần tên zone, `gcloud` hỗ trợ phép biến đổi trường như `basename()` trong biểu thức định dạng:

~~~bash
gcloud compute instances list \
  --project=my-prod-project \
  --format="table(name,zone.basename(),machineType.basename(),status)"
~~~

Ví dụ minh họa cách đọc bảng (giá trị cụ thể phụ thuộc tài nguyên thật):

~~~text
NAME    ZONE                 MACHINE_TYPE  STATUS
web-01  asia-southeast1-a    e2-medium     RUNNING
job-02  asia-southeast1-b    e2-small      TERMINATED
~~~

`zone.basename()` chỉ ảnh hưởng đến cách hiển thị, không di chuyển VM sang zone khác. Cú pháp trường và phép biến đổi thuộc **projection** của CLI; hãy dùng `gcloud topic projections` để xem hướng dẫn và `--format=json` để xác định tên trường trước khi viết projection phức tạp.

## 3. Lọc tài nguyên bằng `--filter`

### 3.1. Cú pháp cơ bản

`--filter=EXPRESSION` chọn các bản ghi phù hợp với điều kiện. Một biểu thức thường có dạng:

~~~text
TRƯỜNG TOÁN_TỬ GIÁ_TRỊ
~~~

Các toán tử thường dùng:

| Toán tử | Mục đích | Ví dụ minh họa |
| --- | --- | --- |
| `=` | So sánh giá trị bằng nhau. | `status=RUNNING` |
| `!=` | So sánh khác nhau. | `status!=RUNNING` |
| `:` | Khớp chuỗi/giá trị theo ngữ nghĩa của bộ lọc; thường dùng để tìm thành phần văn bản. | `zone:asia-southeast1` |
| `~` | Khớp theo biểu thức chính quy. | `name~^web-` |
| `AND` | Phải thỏa cả hai điều kiện. | `status=RUNNING AND labels.env=prod` |
| `OR` | Thỏa ít nhất một điều kiện. | `status=RUNNING OR status=TERMINATED` |
| `NOT` | Phủ định điều kiện. | `NOT status=RUNNING` |

Ví dụ:

~~~bash
# Chỉ liệt kê các VM đang chạy.
gcloud compute instances list \
  --project=my-prod-project \
  --filter="status=RUNNING"

# Tìm các VM có tên bắt đầu bằng web-.
gcloud compute instances list \
  --project=my-prod-project \
  --filter="name~^web-"

# Chỉ xem các VM đang chạy và có label env=prod.
gcloud compute instances list \
  --project=my-prod-project \
  --filter="status=RUNNING AND labels.env=prod" \
  --format="table(name,zone.basename(),status,labels.env)"

# Giới hạn theo zone bằng phép so khớp một phần chuỗi.
gcloud compute instances list \
  --project=my-prod-project \
  --filter="zone:asia-southeast1-a" \
  --format="table(name,zone.basename(),status)"
~~~

Biểu thức sử dụng đúng tên trường của **loại tài nguyên được truy vấn**, ví dụ `status` của VM không đồng nghĩa với `state` của Cloud SQL. Với trường nhãn `labels.env`, những VM không có nhãn `env` sẽ không thỏa phép so sánh bằng `prod`.

### 3.2. Kết hợp điều kiện và dấu ngoặc

Khi một biểu thức chứa nhiều phép toán, dùng dấu ngoặc để thể hiện rõ ý định:

~~~bash
# VM tên bắt đầu bằng web- hoặc api-, đồng thời đang chạy.
gcloud compute instances list \
  --project=my-prod-project \
  --filter="status=RUNNING AND (name~^web- OR name~^api-)" \
  --format="table(name,zone.basename(),status)"

# VM trong nhóm không đang chạy, dùng để rà soát trạng thái.
gcloud compute instances list \
  --project=my-prod-project \
  --filter="NOT status=RUNNING" \
  --format="table(name,zone.basename(),status)"
~~~

Việc nhóm biểu thức tránh nhầm lẫn giữa điều kiện “VM phải đang chạy” với điều kiện “tên thuộc một trong hai nhóm”. Thực tế có thể có nhiều trạng thái VM ngoài `RUNNING` và `TERMINATED`; không nên giả định mọi kết quả không chạy đều có thể xóa.

### 3.3. So khớp chuỗi, regex và các lỗi thường gặp

Các biểu thức sau phục vụ những nhu cầu khác nhau:

~~~text
name=web-01        # Giá trị bằng tên xác định.
name:web           # Tìm theo phép so khớp chuỗi.
name~^web-         # Biểu thức chính quy: bắt đầu bằng "web-".
name~-(dev|test)$  # Biểu thức chính quy: kết thúc bằng "-dev" hoặc "-test".
~~~

Cần chú ý:

1. `=` là so sánh bằng; `:` không nên được hiểu là tương đương hoàn toàn với `=`. Chi tiết so khớp của `:` có thể phụ thuộc kiểu dữ liệu và cách thực thi bộ lọc.
2. `~` có cú pháp regex. Ký tự `^`, `$`, `.`, `*`, `(`, `)` có ý nghĩa đặc biệt; một dấu chấm trong regex không tự động là dấu chấm ký tự.
3. Biểu thức đặt trong dấu nháy kép như `--filter="..."` giúp shell truyền các khoảng trắng và dấu ngoặc như một đối số. Với nội dung chứa `$`, dấu nháy đơn có thể phù hợp hơn trong Bash/PowerShell, nhưng quy tắc quoting thay đổi theo shell.
4. Các API khác nhau có thể hỗ trợ **lọc phía máy chủ**, **lọc phía CLI** hoặc kết hợp. Đừng mặc định mọi biểu thức đều giảm số bản ghi được tải qua mạng, hoặc hoạt động giống nhau trên mọi lệnh.
5. Trường thiếu/null và trường là danh sách có hành vi cần kiểm tra thực tế; đừng tự suy rằng một bản ghi không có trường sẽ luôn được xử lý giống chuỗi rỗng.

Tham khảo cú pháp chính thức bằng `gcloud topic filters` và trợ giúp ngay trên lệnh đang dùng.

## 4. Sắp xếp, giới hạn và xử lý kết quả lớn

### 4.1. `--sort-by`

`--sort-by` điều khiển thứ tự hiển thị. Theo quy ước của cờ này, tiền tố `~` trước tên trường thể hiện thứ tự giảm dần:

~~~bash
# Sắp theo tên.
gcloud compute instances list \
  --project=my-prod-project \
  --sort-by="name" \
  --format="table(name,status)"

# Các VM có thời điểm tạo mới hơn đứng trước.
gcloud compute instances list \
  --project=my-prod-project \
  --sort-by="~creationTimestamp" \
  --format="table(name,creationTimestamp,status)"
~~~

Thứ tự sắp xếp phụ thuộc vào kiểu dữ liệu và trường được API trả về. Hãy tránh tự giả định rằng chuỗi hiển thị đã được chuẩn hóa như một timestamp hoặc số trong mọi dịch vụ.

### 4.2. `--limit` và `--page-size`

~~~bash
# Chỉ hiển thị tối đa 10 VM theo thứ tự tên.
gcloud compute instances list \
  --project=my-prod-project \
  --sort-by="name" \
  --limit=10 \
  --format="table(name,status)"
~~~

- `--limit=N` đặt giới hạn số tài nguyên được xuất ra theo cơ chế của lệnh. Nó hữu ích khi khám phá một tập tài nguyên lớn, nhưng không có nghĩa chỉ có N tài nguyên trong project.
- Một số lệnh hỗ trợ `--page-size=N`, dùng để điều chỉnh số phần tử mỗi trang lấy từ API. Cờ này có thể ảnh hưởng đến số lượt gọi và hiệu năng; không đồng nghĩa với giới hạn tổng số kết quả hiển thị.
- Với kiểm kê đầy đủ hoặc báo cáo dùng cho kiểm toán, tránh `--limit` trừ khi phạm vi giới hạn đã được định nghĩa rõ. Kiểm tra cách phân trang của từng lệnh và hành vi thực tế khi kết hợp lọc/sắp xếp.

`--filter`, `--sort-by`, `--limit` và `--format` có thể phối hợp trên nhiều lệnh `list`, song không phải mọi dịch vụ có cùng tên trường, cách phân trang hoặc tập cờ. Các bước xử lý phía CLI và phía API cũng có thể khác nhau.

### 4.3. Kết hợp thành một truy vấn kiểm kê

~~~bash
# Tìm tối đa 20 VM production đang chạy, sắp theo tên.
gcloud compute instances list \
  --project=my-prod-project \
  --filter="status=RUNNING AND labels.env=prod" \
  --sort-by="name" \
  --limit=20 \
  --format="table(name,zone.basename(),machineType.basename(),status)"
~~~

Tách từng phần để kiểm tra khi không thấy kết quả: đầu tiên chạy `list` không lọc trong đúng project, sau đó thêm `--filter`, rồi mới sắp xếp, giới hạn và định dạng. Quy trình này giúp phân biệt lỗi điều kiện truy vấn với lỗi nhận diện tài nguyên và phạm vi quyền IAM.

## 5. Khám phá trường dữ liệu trước khi viết truy vấn

### 5.1. Dùng JSON để kiểm tra cấu trúc

Các trường mà một lệnh `list` trả về không nhất thiết trùng với cách Console đặt tên. Ví dụ một VM có `zone` là URL tham chiếu, `labels` là một map và `networkInterfaces` là danh sách các đối tượng chứa thông tin kết nối.

~~~bash
# Giới hạn số bản ghi để dễ đọc cấu trúc.
gcloud compute instances list \
  --project=my-prod-project \
  --limit=1 \
  --format="json"

# Kiểm tra chi tiết một VM xác định.
gcloud compute instances describe web-01 \
  --project=my-prod-project \
  --zone=asia-southeast1-a \
  --format="json"
~~~

Nếu cần tìm thông tin của một trường lồng nhau, nên xem cấu trúc JSON trước, sau đó quyết định dùng projection của `gcloud` hay bộ xử lý JSON chuyên dụng. Đặc biệt, danh sách nhiều phần tử (chẳng hạn các network interface hoặc disk) không nên bị hiểu nhầm thành một trường chuỗi đơn.

### 5.2. Ví dụ truy vấn với các dịch vụ khác

Mặc dù cơ chế `--format` tương tự, **tên field khác nhau giữa các sản phẩm**:

~~~bash
# Các project: dùng projectId, không phải luôn là id.
gcloud projects list \
  --format="table(projectId,name,lifecycleState)"

# Cụm GKE: xem tên, vị trí, trạng thái.
gcloud container clusters list \
  --project=my-prod-project \
  --format="table(name,location,status)"

# Cloud SQL: xem loại engine/phiên bản và trạng thái.
gcloud sql instances list \
  --project=my-prod-project \
  --format="table(name,region,databaseVersion,state)"

# VPC: xem tên mạng và cấu hình tạo subnet tự động.
gcloud compute networks list \
  --project=my-prod-project \
  --format="table(name,autoCreateSubnetworks)"

# Cloud Run: khi chưa biết cấu trúc field, xuất JSON để khảo sát.
gcloud run services list \
  --project=my-prod-project \
  --region=asia-southeast1 \
  --format="json"
~~~

Với IAM, dùng lệnh trả về policy của đúng phạm vi, chẳng hạn:

~~~bash
gcloud projects get-iam-policy my-prod-project --format="json"
~~~

Thông tin IAM có thể chứa danh sách principal, role và điều kiện ràng buộc. Đọc và chia sẻ dữ liệu này theo quyền và chính sách bảo mật của tổ chức. Việc lọc output trên máy người dùng không làm dữ liệu đã truy xuất trở thành công khai.

## 6. Dùng kết quả gcloud trong script và báo cáo

### 6.1. Phân biệt định dạng cho con người và cho máy

Để đọc nhanh, `table(...)` là lựa chọn thuận tiện. Để xử lý tự động, nên dùng dữ liệu có cấu trúc hoặc một trường đơn:

~~~bash
# Một VM trên mỗi dòng: thích hợp cho danh sách tên đơn giản.
gcloud compute instances list \
  --project=my-prod-project \
  --filter="status=RUNNING" \
  --format="value(name)"

# CSV có những cột cố định để nhập vào báo cáo.
gcloud compute instances list \
  --project=my-prod-project \
  --sort-by="name" \
  --format="csv(name,zone.basename(),status)" \
  > vm-inventory.csv
~~~

Ví dụ trên chuyển kết quả CSV vào một file trong thư mục hiện hành của **người thực hành**. Khi đưa vào quy trình thật, xác định rõ nơi lưu, quyền truy cập, thời điểm kiểm kê và quy tắc bảo vệ metadata nhạy cảm. Nếu muốn kiểm kê cả những VM đang dừng hoặc các môi trường khác nhau, bỏ điều kiện `status=RUNNING` hoặc thay bằng phạm vi được yêu cầu.

### 6.2. Xử lý JSON trong shell

Khi cần lọc mảng, trích trường lồng nhau hoặc kết hợp dữ liệu từ nhiều nguồn, chương trình xử lý JSON sẽ rõ ràng hơn việc cắt chuỗi của bảng. Ví dụ trên hệ thống đã cài `jq`:

~~~bash
gcloud compute instances list \
  --project=my-prod-project \
  --format=json \
  | jq -r '.[] | select(.status == "RUNNING") | .name'
~~~

Ở đây `gcloud` tạo mảng JSON, còn `jq` chọn các phần tử có trạng thái `RUNNING` và in tên. `jq` là công cụ riêng, **không phải thành phần luôn có sẵn** trong mọi môi trường cài `gcloud`.

Ví dụ tương đương về ý định trên Windows PowerShell:

~~~powershell
$instances = gcloud compute instances list --project=my-prod-project --format=json |
    ConvertFrom-Json

$instances |
    Where-Object { $_.status -eq 'RUNNING' } |
    Select-Object -ExpandProperty name
~~~

Lựa chọn dùng `--filter` ngay trong `gcloud` hay lọc JSON sau đó phụ thuộc vào nhu cầu. Lọc ngay tại nguồn thường giúp câu lệnh ngắn gọn; hậu xử lý JSON thích hợp với cấu trúc phức tạp. Không nên giả định mọi filter được thực thi ở máy chủ hoặc API, nên với dữ liệu lớn cần quan sát hiệu năng thực tế.

### 6.3. Đầu ra rỗng, lỗi và tính ổn định của automation

Một script cần phân biệt ít nhất ba trường hợp:

1. **Có dữ liệu:** `gcloud` chạy thành công và xuất một hoặc nhiều phần tử.
2. **Không có bản ghi phù hợp:** lệnh chạy thành công nhưng danh sách rỗng; đây có thể là kết quả đúng của bộ lọc.
3. **Lệnh lỗi:** project không tồn tại/không được phép xem, thiếu quyền, API chưa sẵn sàng, tham số sai, mất mạng hoặc hết quota.

Khi chạy trong CI/CD, phải kiểm tra **exit code**, tiêu chuẩn ghi log và cấu trúc đầu ra; không nên coi “không in gì” là bằng chứng rằng mọi thứ bình thường. Với JSON, ứng dụng nên xử lý `[]` và trường không có giá trị. Với CSV, dùng trình phân tích CSV thật thay vì tách chuỗi thủ công theo dấu phẩy.

Trong báo cáo nhiều project, hãy lưu cả `project ID`, vị trí và thời điểm kiểm kê. Các tên như `web-01` có thể trùng giữa những project hoặc zone khác nhau, vì vậy tên tài nguyên đơn lẻ không đủ để xác định duy nhất mọi VM.

## 7. Tình huống thực tế: kiểm kê môi trường production

Giả sử nhóm vận hành quản lý nhiều project của một nền tảng bán hàng. Mục tiêu là tìm các VM production đang chạy, xem cụm GKE và Cloud SQL liên quan, rồi xuất dữ liệu để đối chiếu với kế hoạch bảo mật, độ tin cậy và tối ưu chi phí.

### Bước 1: Xác định đúng project

~~~bash
gcloud projects list \
  --format="table(projectId,name,lifecycleState)"
~~~

Từ danh sách này, chọn project ID đã được tổ chức xác nhận. Không suy luận rằng project có tên hiển thị chứa từ “prod” luôn chính là môi trường production được phê duyệt.

### Bước 2: Lọc VM theo label và trạng thái

~~~bash
gcloud compute instances list \
  --project=my-prod-project \
  --filter="labels.env=prod AND status=RUNNING" \
  --sort-by="name" \
  --format="table(name,zone.basename(),machineType.basename(),status)"
~~~

Kiểm tra liệu toàn bộ VM production đã được gắn nhãn `env=prod` chưa. Nếu quy tắc gắn label chưa nhất quán, bộ lọc sẽ bỏ sót tài nguyên dù VM thật sự đang phục vụ production. Đây là lý do việc quản trị label quan trọng đối với kiểm kê và báo cáo chi phí.

### Bước 3: Quan sát các thành phần vận hành liên quan

~~~bash
gcloud container clusters list \
  --project=my-prod-project \
  --format="table(name,location,status)"

gcloud sql instances list \
  --project=my-prod-project \
  --format="table(name,region,databaseVersion,state)"

gcloud compute networks list \
  --project=my-prod-project \
  --format="table(name,autoCreateSubnetworks)"
~~~

Những bảng này giúp nhận diện tài nguyên cần kiểm tra tiếp. Chúng **chưa chứng minh** cụm GKE, mạng VPC và Cloud SQL có kết nối hoặc phụ thuộc vào nhau; việc đối chiếu quan hệ cần xem thêm cấu hình, policy, địa chỉ mạng, service account và tài liệu kiến trúc.

### Bước 4: Xuất kết quả ổn định để phân tích

~~~bash
gcloud compute instances list \
  --project=my-prod-project \
  --filter="labels.env=prod" \
  --sort-by="name" \
  --format="csv(name,zone.basename(),machineType.basename(),status)" \
  > vm-prod-inventory.csv
~~~

File CSV có thể dùng để rà soát loại máy, số VM đang chạy hoặc đã dừng. Tuy nhiên, **danh sách VM không phải hóa đơn**: để đánh giá chi phí cần đối chiếu với Billing, mức sử dụng thực, cam kết chiết khấu, tài nguyên liên quan và thời gian chạy. Tương tự, trạng thái `RUNNING` không chứng minh dịch vụ ứng dụng đang đáp ứng SLO; cần thêm metrics và kiểm tra đầu cuối qua các công cụ quan sát.

### Bước 5: Điều tra một tài nguyên bất thường

Khi phát hiện một VM không đúng dự kiến, lấy thông tin chi tiết bằng `describe`:

~~~bash
gcloud compute instances describe web-01 \
  --project=my-prod-project \
  --zone=asia-southeast1-a \
  --format="yaml"
~~~

Đọc loại máy, interface mạng, disk, service account, label và trạng thái phù hợp với mục tiêu rà soát. Nếu phát hiện khả năng cấu hình sai IAM hoặc VPC, bước tiếp theo là đối chiếu chính sách và quy trình thay đổi của đội vận hành; bài học này chỉ thực hành các thao tác truy vấn.

## 8. Những lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân có thể gặp | Cách tiếp cận |
| --- | --- | --- |
| Lệnh chạy nhưng không có tài nguyên | Chọn sai project/region/zone; filter quá chặt; tài nguyên chưa có. | Kiểm tra context, bỏ filter, liệt kê lại rồi thêm điều kiện từng bước. |
| Báo lỗi permission | Thiếu quyền IAM trên resource hoặc project. | Kiểm tra danh tính, vai trò và phạm vi quyền được cấp; liên hệ quản trị viên nếu cần. |
| `--format` trả cột trống | Dùng sai tên field, trường không tồn tại hoặc không có giá trị ở bản ghi đó. | Xem `--format=json` và `describe` để tìm đúng đường dẫn trường. |
| Regex lọc không như mong đợi | Nhầm cú pháp regex với phép so khớp chuỗi; shell xử lý ký tự đặc biệt. | Thử biểu thức đơn giản, dùng dấu nháy phù hợp và kiểm tra bằng danh sách không lọc. |
| Script đọc sai cột | Phân tích đầu ra bảng bằng khoảng trắng hoặc giả định thứ tự cột. | Dùng `json`, `csv` hoặc `value(...)` có cấu trúc dự kiến; kiểm tra dữ liệu rỗng. |
| Truy vấn quá chậm hoặc quá nhiều kết quả | Phạm vi tài nguyên lớn; filter có thể thực thi ở client; nhiều trang API. | Thu hẹp phạm vi project/region theo dịch vụ, đánh giá filter, phân trang và yêu cầu báo cáo. |
| Kết luận sai về production | Label thiếu hoặc sai, tài nguyên dùng chung, tên không duy nhất. | Đối chiếu nhãn, project, zone và nguồn quản lý tài nguyên của tổ chức. |

## 9. Bài thực hành tự kiểm tra

Thực hiện với một project có quyền **chỉ đọc**; không cần sửa tài nguyên.

**Bài 1 — Chọn trường:** Viết lệnh liệt kê tất cả project mà tài khoản truy cập được, chỉ hiển thị `projectId` và `name` dưới dạng bảng.

~~~bash
gcloud projects list --format="table(projectId,name)"
~~~

**Bài 2 — Lọc và sắp xếp:** Viết lệnh lấy những VM có tên bắt đầu bằng `web-`, đang chạy, sắp xếp theo tên và chỉ hiển thị tên, zone, trạng thái.

~~~bash
gcloud compute instances list \
  --project=my-prod-project \
  --filter="name~^web- AND status=RUNNING" \
  --sort-by="name" \
  --format="table(name,zone.basename(),status)"
~~~

**Bài 3 — Xuất dữ liệu cho chương trình:** Viết lệnh xuất danh sách Cloud SQL thành JSON.

~~~bash
gcloud sql instances list \
  --project=my-prod-project \
  --format="json"
~~~

**Bài 4 — Điều tra filter rỗng:** Một người chạy `--filter="labels.env=prod"` và không thấy VM nào. Nêu ít nhất ba giả thuyết: project không đúng, không có VM, VM không gắn nhãn hoặc giá trị label khác, thiếu quyền, hay phạm vi vị trí bị giới hạn. Thử lại không có filter, kiểm tra JSON của bản ghi và chỉ thêm điều kiện sau khi xác nhận trường thực tế.

**Bài 5 — Chọn định dạng phù hợp:** Với báo cáo kiểm kê cần nhập vào bảng tính, hãy chọn `csv(...)`. Với pipeline cần xử lý network interface lồng nhau, hãy ưu tiên `json` và trình xử lý cấu trúc. Với thao tác đọc nhanh vài cột trên terminal, dùng `table(...)`.

## 10. Ghi nhớ và nguồn tra cứu

Một truy vấn `gcloud` dễ kiểm chứng thường trả lời được bốn câu hỏi: **đang hỏi dịch vụ nào, ở project/vị trí nào, chọn bản ghi theo điều kiện gì và muốn kết quả có cấu trúc ra sao**.

- Dùng **`list`** để tìm đối tượng và **`describe`** để xem chi tiết một đối tượng xác định.
- Dùng **`--filter`** cho điều kiện, **`--sort-by`** cho thứ tự, **`--limit`** cho số bản ghi hiển thị và **`--format`** để chọn cách biểu diễn.
- Kiểm tra **field thực tế qua JSON** trước khi viết biểu thức phức tạp; không suy tên field từ giao diện Console.
- Dùng **JSON, CSV hoặc `value(...)`** cho tự động hóa; kiểm tra exit code và kết quả rỗng.
- Ghi rõ **project, zone/region, danh tính và thời điểm** để kết quả kiểm kê có thể đối chiếu và phục vụ các quyết định về IAM, VPC, vận hành Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu.

Các lệnh trợ giúp và tài liệu để tra cứu cú pháp theo phiên bản `gcloud` đang cài:

~~~bash
gcloud topic filters
gcloud topic formats
gcloud topic projections
gcloud compute instances list --help
gcloud help
~~~

Tài liệu chính thức: [Google Cloud CLI reference](https://cloud.google.com/sdk/gcloud/reference), [gcloud topic filters](https://cloud.google.com/sdk/gcloud/reference/topic/filters), [gcloud topic formats](https://cloud.google.com/sdk/gcloud/reference/topic/formats), [gcloud topic projections](https://cloud.google.com/sdk/gcloud/reference/topic/projections).

Khi thành thạo các thao tác này, người học có thể chuyển từ việc tra cứu thủ công sang những câu lệnh kiểm kê có thể lặp lại, phục vụ kiểm tra cấu hình, phát hiện sai lệch trước khi phát hành ứng dụng và cung cấp đầu vào đáng tin cậy hơn cho quy trình theo dõi độ tin cậy và chi phí trên Google Cloud.
