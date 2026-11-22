# Project ID, project number và quy tắc định danh tài nguyên

Trong Google Cloud, một tên dễ đọc như **Retail Production** chưa đủ để xác định chính xác tài nguyên cần quản lý. Khi triển khai máy ảo, tạo VPC, cấp quyền IAM, bật API hay xem chi phí, bạn phải biết **project** nào đang được sử dụng và dịch vụ đó nhận dạng tài nguyên bằng những thành phần nào. Bài học này tập trung vào ba khái niệm thường bị nhầm lẫn: **project name**, **project ID**, **project number**; sau đó mở rộng sang quy tắc đặt tên và phạm vi duy nhất của tài nguyên.

Đây là kiến thức nền cho các bài thực hành Google Cloud tiếp theo: tổ chức project, phân quyền IAM, triển khai Compute Engine/GKE/Cloud Run, lưu dữ liệu, tự động hóa phát hành và theo dõi độ tin cậy cũng như chi phí.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt project name, project ID và project number, biết trường nào thay đổi được.
2. Kiểm tra một project ID có đúng **quy tắc cú pháp** và hiểu vì sao đúng cú pháp chưa đảm bảo tạo được project.
3. Tìm project ID và project number qua Google Cloud console hoặc `gcloud`.
4. Đọc một định danh tài nguyên để chỉ ra project, dịch vụ, region/zone và tên tài nguyên.
5. Thiết kế quy ước đặt tên giúp tránh triển khai nhầm môi trường, dễ kiểm toán IAM và phân bổ chi phí.

## 1. Project nằm ở đâu trong hệ thống tài nguyên?

Trong Google Cloud, **project** là đơn vị cơ bản để tạo và quản lý phần lớn tài nguyên dịch vụ. Project gắn với việc bật API, kiểm soát truy cập, quản lý hạn mức và hạch toán chi phí. Trong một tổ chức, project có thể nằm trực tiếp dưới **organization** hoặc dưới **folder**; tài nguyên dịch vụ được tạo trong project tương ứng.

```text
Organization (tổ chức)
└── Folder (có thể có nhiều cấp)
    ├── Project: retail-dev-01
    │   ├── VPC network: retail-dev-vpc
    │   ├── VM: web-01 (trong một zone)
    │   └── Cloud Run service: api (trong một region)
    └── Project: retail-prod-01
        ├── VPC network: retail-prod-vpc
        └── VM: web-01 (có thể trùng tên VM ở project dev)
```

Sơ đồ chỉ minh họa sự sở hữu và phân cấp. **Tên `web-01` không tự cho biết VM thuộc project nào**. Để xác định một VM cụ thể, cần thêm project và zone; trong những hệ thống dùng DNS nội bộ toàn cục còn có ràng buộc duy nhất tên VM ở cấp project.

Trong vận hành, sai project có thể dẫn đến triển khai sang môi trường production, áp IAM policy sai nơi hoặc ghi nhận chi phí vào đơn vị khác. Vì vậy, project ID phải là một phần của ngữ cảnh khi chạy lệnh và xử lý sự cố.

## 2. Ba thông tin của một project

Giả sử nhóm đang vận hành project minh họa sau:

| Thuộc tính | Giá trị ví dụ | Ý nghĩa | Ai chọn? | Thay đổi sau khi tạo? |
| --- | --- | --- | --- | --- |
| **Project name** (tên hiển thị) | `Retail Production` | Nhãn dễ đọc trong giao diện quản trị | Người tạo project | **Có** |
| **Project ID** | `retail-prod-01` | Chuỗi định danh project duy nhất trên Google Cloud | Người tạo chọn hoặc dùng gợi ý của hệ thống | **Không** |
| **Project number** | `123456789012` | Mã số duy nhất do Google Cloud cấp | Google Cloud | **Không** |

Các giá trị trên chỉ là **ví dụ**, không khẳng định project đó tồn tại hay project ID đang sẵn dùng.

### Project name: để con người đọc

Project name là tên hiển thị, không cần duy nhất. Tên có thể được đổi khi nhu cầu tổ chức thay đổi. Theo quy tắc tạo project, tên dài **4–30 ký tự**, hỗ trợ chữ cái, số, dấu cách và một số dấu câu được cho phép; tên phải kết thúc bằng chữ hoặc số.

API thường không dùng project name làm khóa nhận dạng. Việc đổi `Retail Production` thành `Retail Core Production` không làm đổi project ID hoặc project number.

### Project ID: định danh do người dùng lựa chọn

Project ID là chuỗi duy nhất trên **toàn Google Cloud**, ví dụ `retail-prod-01`. Đây là giá trị thường được truyền qua tham số `--project` của `gcloud`, trong cấu hình SDK, Terraform, đường dẫn API và tên của một số tài nguyên.

Project ID **bất biến sau khi project được tạo**. ID đã dùng, kể cả của project đã xóa, không thể được tái sử dụng cho một project mới. Vì vậy cần chọn ID có khả năng dùng lâu dài, không phụ thuộc tên nhân viên, nhiệm vụ tạm thời hoặc bí mật kinh doanh.

### Project number: định danh hệ thống tự sinh

Project number là mã số duy nhất, được Google Cloud cấp tự động và ở chế độ chỉ đọc. Người dùng không thể chọn số này khi tạo project. Một số API và danh tính do Google quản lý dùng **project number**, đặc biệt trong tên tài nguyên chuẩn của Cloud Resource Manager và email service account mặc định.

Ví dụ, service account mặc định của Compute Engine (khi được tạo) thường có email theo mẫu:

```text
PROJECT_NUMBER-compute@developer.gserviceaccount.com
```

Với project number minh họa ở bảng, mẫu này cho ra `123456789012-compute@developer.gserviceaccount.com`. Đừng thay bằng `retail-prod-01-compute@...`: đây là hai loại định danh khác nhau. Tài khoản mặc định có được tạo hay không còn phụ thuộc API/dịch vụ đã bật và vòng đời project.

> **Điểm cần nhớ:** Project name phục vụ người đọc; project ID là khóa định danh do người tạo chọn; project number là khóa định danh do Google Cloud cấp. Một project có **một ID và một number**, nhưng nhiều dịch vụ có cách yêu cầu hai giá trị này khác nhau.

## 3. Quy tắc tạo project ID

Google Cloud áp dụng các điều kiện sau cho **project ID**:

- Dài **6–30 ký tự**.
- Chỉ gồm **chữ thường a–z**, **chữ số 0–9** và **dấu gạch nối `-`**.
- **Bắt đầu bằng chữ cái** và **không kết thúc bằng dấu gạch nối**.
- **Duy nhất trên toàn Google Cloud**; một ID đã từng được sử dụng, kể cả ở project đã xóa, không còn khả dụng.
- Không chứa chuỗi bị hạn chế, chẳng hạn `google` hoặc `ssl`. Nên tránh các chuỗi dễ gây vấn đề như `undefined` hay `null`.

Biểu thức chính quy dưới đây chỉ kiểm tra **độ dài và bộ ký tự**; nó không thể kiểm tra ID đã được sử dụng hay nằm trong danh sách hạn chế của Google Cloud:

```regex
^[a-z][a-z0-9-]{4,28}[a-z0-9]$
```

| Giá trị đề xuất | Đánh giá | Lý do |
| --- | --- | --- |
| `retail-prod-01` | Đúng cú pháp | Chữ thường, 6–30 ký tự, bắt đầu bằng chữ và kết thúc bằng số |
| `retail-dev-02` | Đúng cú pháp | Phù hợp cho một môi trường khác; vẫn phải kiểm tra tính khả dụng |
| `Retail-Prod` | Không hợp lệ | Có chữ hoa |
| `2-retail-prod` | Không hợp lệ | Bắt đầu bằng chữ số |
| `retail_prod_01` | Không hợp lệ | Chứa dấu gạch dưới `_` |
| `retail-prod-` | Không hợp lệ | Kết thúc bằng `-` |
| `app01` | Không hợp lệ | Chỉ có 5 ký tự |
| `google-retail-prod` | Không hợp lệ | Chứa chuỗi hạn chế `google` |

**Đúng cú pháp ≠ tạo được project**: tên có thể đã có chủ, từng được sử dụng hoặc chịu ràng buộc bổ sung. Cần để Google Cloud xác nhận khi tạo project, đồng thời kiểm tra quyền tạo project và chính sách tổ chức.

Project ID có thể xuất hiện trong URL, đường dẫn API, log hoặc tên tài nguyên. Không nên nhét **mật khẩu, token, thông tin cá nhân hoặc dữ liệu nhạy cảm** vào project ID, project name hay các tên tài nguyên.

## 4. Tra cứu ID và number của project

### Qua Google Cloud console

Mở [Google Cloud console](https://console.cloud.google.com/), chọn đúng project trong bộ chọn project. Trang **Welcome** hiển thị project name, project ID và project number. Nếu đang quản lý nhiều project, có thể tìm trong **Manage resources**.

### Qua Google Cloud CLI

Các lệnh sau chỉ minh họa cách tra cứu. Chúng yêu cầu `gcloud` đã được cài đặt, đăng nhập và tài khoản có quyền xem project.

```bash
# Liệt kê những project tài khoản hiện tại nhìn thấy.
gcloud projects list --format="table(projectId,projectNumber,name)"

# Xem thông tin một project bằng ID.
gcloud projects describe retail-prod-01

# Lấy riêng project number để dùng cho tích hợp cần số.
gcloud projects describe retail-prod-01 --format="value(projectNumber)"

# Kiểm tra project mặc định trong cấu hình gcloud hiện tại.
gcloud config get-value project

# Kiểm tra danh tính đang dùng.
gcloud auth list
```

Nếu `gcloud projects describe` báo project không tồn tại hoặc không truy cập được, nguyên nhân có thể là **ID sai, project không tồn tại hoặc thiếu quyền**. Đừng vội suy luận từ một thông báo lỗi rằng ID chắc chắn chưa từng được sử dụng.

Khi thao tác một dự án cụ thể, có thể đặt project mặc định:

```bash
gcloud config set project retail-dev-01
```

Tuy nhiên, trước một lệnh quan trọng, nên truyền project **tường minh** để hạn chế phụ thuộc vào cấu hình hiện tại:

```bash
# Chỉ đọc danh sách VM trong project dev.
gcloud compute instances list --project=retail-dev-01
```

Việc đặt `gcloud config` chỉ thay đổi ngữ cảnh của CLI; nó **không tự cấp quyền IAM** và không chuyển tài nguyên giữa các project. Với pipeline CI/CD, hãy chỉ định project rõ ràng trong từng bước triển khai và kiểm tra đúng danh tính thực thi.

## 5. Định danh tài nguyên có nhiều lớp

Không có một quy tắc đặt tên duy nhất áp dụng cho toàn bộ Compute Engine, VPC, GKE, Cloud Run, Cloud Storage và cơ sở dữ liệu. Định danh đầy đủ thường kết hợp:

1. **Project** đang sở hữu hoặc được dùng để tra cứu tài nguyên.
2. **Dịch vụ và loại tài nguyên** (VM, VPC, subnet, Cloud Run service, bucket...).
3. **Phạm vi vị trí** nếu dịch vụ dùng region hoặc zone.
4. **Tên tài nguyên** theo quy tắc riêng của dịch vụ.

Ví dụ, API Compute Engine nhận dạng một VM bằng đường dẫn:

```text
projects/retail-prod-01/zones/asia-southeast1-b/instances/web-01
```

Trong đó:

| Thành phần | Giá trị | Cách hiểu |
| --- | --- | --- |
| `projects/retail-prod-01` | `retail-prod-01` | Project ID |
| `zones/asia-southeast1-b` | `asia-southeast1-b` | Zone chứa VM |
| `instances/web-01` | `web-01` | Tên VM trong phạm vi được dịch vụ áp dụng |

Nếu chỉ đưa `web-01`, chưa đủ biết đó là VM nào. Một tên tương tự có thể tồn tại ở project hoặc zone khác, tùy cấu hình DNS và quy tắc của loại tài nguyên.

Cloud Run API v2 sử dụng mẫu tên tài nguyên:

```text
projects/retail-prod-01/locations/asia-southeast1/services/api
```

Ở đây `locations/asia-southeast1` biểu thị **region**, không phải zone. Với một số phương thức Cloud Run, thành phần project nhận **project ID hoặc project number**. Không được tự suy ra mọi API Google Cloud đều nhận cả hai: hãy đọc tài liệu của đúng API và trường dữ liệu. Ví dụ, REST Compute Engine `instances.get` chỉ rõ tham số `project` là project ID.

### Phạm vi duy nhất của tên tài nguyên

| Loại tài nguyên | Phạm vi cần phân biệt | Ví dụ và lưu ý |
| --- | --- | --- |
| Project | Toàn Google Cloud | `retail-prod-01` phải duy nhất toàn cục |
| Compute Engine VPC network | Toàn project (tài nguyên global) | `retail-vpc` có thể được đặt ở project khác |
| Compute Engine subnet | Theo region trong project | Cần project + region + subnet name |
| Compute Engine VM | Theo zone trong project; **có ngoại lệ DNS** | Cùng tên VM có thể được dùng ở hai zone khi dùng Zonal DNS; với cấu hình DNS toàn cục, tên VM phải duy nhất trong project |
| Cloud Run service | Theo region trong project | Cần project + region + service name |
| Cloud Storage bucket | **Toàn không gian tên Cloud Storage** | Bucket `retail-assets-demo-01` chỉ có thể thuộc một chủ sở hữu tại cùng thời điểm, dù các project khác nhau |

Compute Engine có quy tắc tên phổ biến: **1–63 ký tự**, chữ thường và số cùng dấu `-`; bắt đầu bằng chữ thường, kết thúc bằng chữ hoặc số (trừ trường hợp tài liệu của loại tài nguyên nói khác). Không nên lấy quy tắc này áp cho bucket, BigQuery dataset hay Cloud Run service vì mỗi dịch vụ có điều kiện riêng.

Cloud Storage là ngoại lệ dễ gặp: **bucket name phải duy nhất trên toàn không gian tên bucket**, không chỉ trong project. URI dạng `gs://bucket-name/path/to/object` là cách gọi đối tượng; thành phần bucket trong URI không tự thể hiện project sở hữu. Cloud Storage bucket cũng có bộ ký tự và giới hạn tên riêng, khác project ID.

### Phân biệt tên logic và định danh do hệ thống cấp

Ngoài project number, nhiều dịch vụ có **ID/UID nội bộ** cho tài nguyên hoặc phiên bản triển khai. Chẳng hạn, Compute Engine VM có trường `name` và trường `id` do hệ thống cấp. Chúng không phải project ID hoặc project number. Khi phân tích sự kiện, hãy ghi rõ đang nói đến **project number**, **instance ID** hay **service account ID** để tránh tra cứu nhầm.

## 6. Quy ước đặt tên cho hệ thống nhiều môi trường

Một tổ chức có thể tổ chức project theo sản phẩm, môi trường và ranh giới quyền:

| Môi trường | Project name | Project ID minh họa | Gợi ý tài nguyên |
| --- | --- | --- | --- |
| Development | Retail Development | `retail-app-dev-01` | `retail-dev-vpc`, VM `web-01` |
| Staging | Retail Staging | `retail-app-stg-01` | `retail-stg-vpc`, Cloud Run `api` |
| Production | Retail Production | `retail-app-prod-01` | `retail-prod-vpc`, Cloud Run `api` |

Lưu ý các ví dụ chỉ biểu diễn **quy ước đặt tên**, không đảm bảo ID hoặc tên bucket đang còn trống.

Một mẫu tham khảo:

```text
<san-pham>-<thanh-phan-tuy-chon>-<moi-truong>-<so-thu-tu>
retail-app-prod-01
retail-data-dev-01
```

Khi thiết kế quy ước:

- Chọn các thành phần **ổn định** như sản phẩm, phạm vi nghiệp vụ và môi trường; tránh đặt ID bằng tên người phụ trách.
- Thống nhất viết tắt `dev`, `stg`, `prod`; đưa môi trường vào ID để giảm khả năng chọn sai.
- Kiểm tra giới hạn 30 ký tự của project ID trước khi bổ sung mã phòng ban, vùng hoặc số thứ tự.
- Chỉ thêm mã **region/zone** vào nơi thực sự cần thể hiện vị trí; project ID không có nghĩa dự án chỉ hoạt động tại một region.
- Gắn **labels** phù hợp (team, environment, cost center) để lọc và phân bổ chi phí; đừng yêu cầu mọi thông tin quản trị phải được mã hóa trong tên bất biến.
- Ghi nhận ánh xạ **project name ↔ project ID ↔ project number**, owner, môi trường và billing account trong hệ thống quản lý hạ tầng.
- Với IAM, cấp quyền cho đúng danh tính và đúng phạm vi tài nguyên, theo nguyên tắc **đặc quyền tối thiểu**. Cú pháp tên hợp lý không thay thế việc kiểm soát truy cập.

## 7. Tình huống thực tế: pipeline triển khai nhầm project

Giả sử nhóm có hai project `retail-app-dev-01` và `retail-app-prod-01`, cùng có Cloud Run service tên `api`. Một kỹ sư muốn triển khai phiên bản mới lên development, nhưng cấu hình `gcloud` hiện đang trỏ tới production.

**Vấn đề:** Lệnh chỉ nêu `--service=api` hoặc dựa vào project mặc định có thể hướng đến sai môi trường. Cùng tên service không chứng minh đó là cùng tài nguyên.

**Cách xác định đúng đích:**

1. Xác nhận project ID mục tiêu là `retail-app-dev-01`.
2. Kiểm tra danh tính chạy lệnh và quyền đối với project dev.
3. Kiểm tra đúng region, chẳng hạn `asia-southeast1`.
4. Khi liệt kê hoặc triển khai, chỉ định `--project=retail-app-dev-01` và `--region=asia-southeast1`.
5. Ghi project ID, project number, region và tên service trong bản ghi phát hành để có thể truy ngược.

Ví dụ kiểm tra **chỉ đọc** trước khi triển khai:

```bash
gcloud config get-value project
gcloud projects describe retail-app-dev-01 --format="value(projectNumber)"
gcloud run services describe api \
  --project=retail-app-dev-01 \
  --region=asia-southeast1
```

Nếu dịch vụ chưa tồn tại trong project dev, cần kiểm tra lại project/region trước khi tạo mới. Không nên khắc phục bằng cách đổi tên tài nguyên đang có ở production hoặc thử triển khai sang một project khác mà chưa xác nhận.

**Liên hệ IAM và chi phí:** Một tài khoản CI có thể có quyền ở nhiều project, nên lệnh chạy thành công không có nghĩa chạy đúng môi trường. Ngoài ra, chi phí chủ yếu được hạch toán theo project sử dụng tài nguyên và billing account liên kết; đặt đúng project giúp tách báo cáo chi phí và hạn mức giữa dev/prod.

## 8. Những nhầm lẫn cần tránh

| Nhầm lẫn | Điều chỉnh đúng |
| --- | --- |
| “Đổi project name sẽ đổi project ID” | Tên hiển thị đổi được; project ID vẫn giữ nguyên |
| “Project ID đúng regex thì chắc chắn còn trống” | Còn phải kiểm tra duy nhất toàn cục, lịch sử sử dụng và chuỗi hạn chế |
| “Project number là số đuôi trong project ID” | Project number do Google cấp, độc lập với quy ước đặt ID |
| “Mọi tài nguyên phải có tên duy nhất toàn Google Cloud” | Phạm vi khác nhau theo dịch vụ, loại tài nguyên và vị trí; bucket là ví dụ duy nhất toàn cục |
| “Mọi API nhận project ID và number thay thế cho nhau” | Trường nào chấp nhận giá trị gì phải đọc đúng đặc tả API |
| “Chọn project trong console nghĩa là CLI sẽ dùng project đó” | Console và `gcloud` có ngữ cảnh riêng; phải kiểm tra cấu hình CLI |
| “Project number là thông tin bí mật dùng để xác thực” | Đây là định danh, **không phải credential**; quyền truy cập do IAM và cơ chế xác thực quyết định |
| “Đặt tên có `prod` là đủ bảo vệ production” | Cần thêm IAM, kiểm soát phát hành, tổ chức project và chính sách phù hợp |

## 9. Tự kiểm tra

**Câu 1.** Project `retail-dev-01` được đổi tên hiển thị từ “Retail Dev” thành “Retail Development”. Hai giá trị nào vẫn giữ nguyên?

<details>
<summary>Đáp án</summary>

Project ID và project number. Chỉ project name thay đổi.
</details>

**Câu 2.** Hai project khác nhau có thể cùng có một VM tên `web-01` không? Có thể cùng có bucket tên `retail-shared-assets` không?

<details>
<summary>Đáp án</summary>

Hai VM cùng tên có thể nằm ở hai project khác nhau vì phạm vi tên VM không toàn Google Cloud. Hai bucket Cloud Storage không thể đồng thời có cùng tên trong không gian tên bucket toàn cục.
</details>

**Câu 3.** Một API báo định danh service `projects/123456789012/locations/asia-southeast1/services/api`. Thành phần `123456789012` chắc chắn là gì và khi nào cần tra cứu lại?

<details>
<summary>Đáp án</summary>

Trong tình huống này, đó là **project number** minh họa. Khi dùng lại trong CLI hoặc API khác, cần tra cứu project ID tương ứng và kiểm tra API đó chấp nhận ID, number hay cả hai.
</details>

**Câu 4.** Vì sao `retail-prod-01` vượt qua kiểm tra cú pháp nhưng vẫn có thể không tạo được?

<details>
<summary>Đáp án</summary>

Vì project ID phải duy nhất toàn cục và không thể dùng lại nếu đã từng được sử dụng; ngoài ra việc tạo project còn phụ thuộc quyền và chính sách tổ chức.
</details>

## Tài liệu tham khảo chính thức

- [Google Cloud — Create projects](https://cloud.google.com/resource-manager/docs/creating-managing-projects): project name, ID, number và quy tắc đặt ID.
- [Google Cloud — View and update projects](https://cloud.google.com/resource-manager/docs/view-update-projects): xác định thông tin project qua console và CLI.
- [Google Cloud — Resource hierarchy](https://cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy): vị trí của project trong hệ thống tài nguyên.
- [Compute Engine — Naming resources](https://cloud.google.com/compute/docs/naming-resources): cú pháp và phạm vi duy nhất của tên tài nguyên Compute Engine.
- [Compute Engine — Global, regional, and zonal resources](https://cloud.google.com/compute/docs/regions-zones/global-regional-zonal-resources): quy tắc phân biệt vị trí tài nguyên.
- [Cloud Storage — About buckets](https://cloud.google.com/storage/docs/buckets): phạm vi duy nhất và cú pháp tên bucket.
- [Compute Engine — Service accounts](https://cloud.google.com/compute/docs/access/service-accounts): nhận diện service account mặc định dùng project number.
- [Cloud Run API v2 — Services](https://cloud.google.com/run/docs/reference/rest/v2/projects.locations.services): mẫu định danh service theo project và location.

