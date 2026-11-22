# Cost Analysis, cost reports và phân bổ chi phí bằng tags

## 1. Từ tổng chi phí tenancy đến trách nhiệm của từng nhóm

Trong chương **Chi phí và quản lý năng lực** của module **CLOUD_PROVIDERS_ORACLE**, bài này tập trung vào ba công việc nối tiếp nhau: tìm nơi phát sinh chi phí bằng Cost Analysis, lấy dữ liệu chi tiết bằng cost reports và phân bổ chi phí cho ứng dụng hoặc đơn vị bằng tags.

Một hệ thống OCI có thể gồm Compute chạy ứng dụng Java, boot volume và block volume, Object Storage lưu bản sao lưu, cùng dịch vụ cơ sở dữ liệu Oracle. Nhìn riêng chi phí Compute chưa cho biết toàn bộ chi phí vận hành ứng dụng. Ngược lại, tổng chi phí tenancy chưa trả lời được nhóm nào chịu trách nhiệm cho phần tăng thêm.

Giả sử doanh nghiệp có hai ứng dụng `payments` và `analytics`, sử dụng một nền tảng thu thập log dùng chung. Người phụ trách cần trả lời:

- Chi phí tăng ở dịch vụ, region hay ứng dụng nào?
- Khoản nào có thể quy trực tiếp cho một cost center?
- Nền tảng dùng chung được chia theo tiêu chí nào?
- Bao nhiêu tiền còn thiếu thông tin để phân bổ?
- Kết quả phân bổ có giữ nguyên tổng chi phí nguồn không?

Sau bài học, người học có thể xây dựng một báo cáo giải thích được các con số trên, biết nguồn dữ liệu của từng con số và biết phần nào cần phối hợp với nhóm tài chính trước khi chốt kỳ.

## 2. Phân biệt ba lớp thông tin

| Lớp | Công cụ hoặc dữ liệu | Mục đích sử dụng |
| --- | --- | --- |
| Khám phá | Cost Analysis | Khoanh vùng xu hướng và những phần cần điều tra |
| Chi tiết | Cost reports | Truy vết các khoản tiêu thụ và xây dựng dữ liệu phân tích |
| Phân bổ nội bộ | Quy tắc nghiệp vụ kết hợp tags, danh mục chủ sở hữu và số liệu sử dụng | Xác định số tiền mỗi đơn vị phải chịu |

**Showback** là trình bày chi phí của từng nhóm để nhóm hiểu và chịu trách nhiệm. **Chargeback** đi thêm một bước: sử dụng kết quả đã được duyệt để ghi nhận hoặc thu hồi chi phí nội bộ. Một bảng showback ban đầu có thể chấp nhận khoản chưa xác định, trong khi chargeback cần quy tắc xử lý khoản đó và quy trình điều chỉnh rõ ràng.

Cũng cần phân biệt **saved report** với **cost report**. Saved report lưu cấu hình phân tích để mở lại; nó không thay thế bộ dữ liệu chi tiết đã thu thập. Khi cần tái hiện một kết quả đã chốt, nên lưu cả dữ liệu đầu vào và phiên bản quy tắc phân bổ.

Một nguyên tắc xuyên suốt là:

~~~text
Chi phí quan sát được
    → xác định phạm vi và nguồn dữ liệu
    → phân loại trực tiếp / dùng chung / chưa xác định
    → áp dụng quy tắc phân bổ
    → đối soát và công bố
~~~

Tags cung cấp nhãn nhận diện. Quyết định chia một khoản dùng chung theo tỷ lệ nào vẫn là quyết định của tổ chức.

## 3. Chuẩn bị phạm vi và quyền truy cập

### 3.1. Ghi rõ phạm vi trước khi so sánh

Mỗi báo cáo nên có thông tin tối thiểu sau:

| Thuộc tính | Ví dụ cho một kỳ minh họa |
| --- | --- |
| Tenancy và subscription | Ghi OCID hoặc định danh đã thống nhất |
| Kỳ phân tích | Tháng 10 năm 2026 |
| Múi giờ chuẩn | UTC |
| Tiền tệ | USD |
| Chỉ tiêu | Chi phí tiêu thụ theo nguồn đã chọn |
| Phạm vi | Toàn bộ các region liên quan |
| Thời điểm lấy dữ liệu | Ghi thời gian thực tế của lần trích xuất |
| Trạng thái | Tạm tính hoặc đã chốt theo quy trình nội bộ |

Không cộng trực tiếp nhiều loại tiền tệ. Nếu báo cáo quản trị cần VND, hãy lưu cả số tiền nguyên tệ, tỷ giá, ngày tỷ giá và quy tắc làm tròn.

Đối với Việt Nam, `2026-10-01 00:00:00 UTC` là `07:00:00` cùng ngày theo giờ địa phương. Nếu tổ chức tính kỳ theo giờ Việt Nam, phải chuyển ranh giới kỳ một cách nhất quán; không lấy tháng UTC ở nguồn này rồi so với tháng giờ địa phương ở nguồn khác.

### 3.2. Tách quyền xem chi phí và quyền quản trị báo cáo

Chính sách mẫu để nhóm xem Cost Analysis:

~~~text
Allow group FinOpsReaders to read usage-report in tenancy
~~~

Để quản lý saved reports, tài liệu OCI sử dụng quyền `manage usage-report`. Chỉ cấp quyền này cho nhóm thực sự cần quản lý cấu hình báo cáo. Cú pháp tham chiếu nhóm cần phù hợp với identity domain trong tenancy. Xem [quyền IAM cho Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm#RequiredIAMPolicy).

Quyền `usage-report` không đồng nghĩa với quyền đọc mọi object của cost reports. Việc tải các file do Oracle lưu trữ cần chính sách truy cập tương ứng vào nơi lưu báo cáo. Tài liệu [Downloading a Cost Report](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/download-cost-usage-report.htm) cung cấp mẫu chính sách `define tenancy` và `endorse group`; OCID tenancy trong mẫu đó là tenancy của Oracle, không phải OCID tenancy khách hàng để tùy ý thay thế.

Đừng dùng bộ lọc compartment hoặc tag trên một màn hình làm bằng chứng rằng người dùng chỉ có thể xem chi phí của một nhóm. Bộ lọc phục vụ phân tích; ranh giới truy cập cần được kiểm tra ở lớp IAM và nơi chia sẻ dữ liệu. Với báo cáo cho từng nhóm, có thể xuất tập dữ liệu đã giới hạn phạm vi vào kho báo cáo do tổ chức kiểm soát quyền đọc.

## 4. Thiết kế tags để nhận diện chi phí

### 4.1. Bắt đầu từ các chiều có quyết định nghiệp vụ

Một bộ defined tags minh họa:

| Namespace và key | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| `Finance.CostCenter` | `CC100` | Đơn vị chịu chi phí |
| `Finance.Application` | `payments` | Ứng dụng hoặc sản phẩm |
| `Finance.Environment` | `prod` | Môi trường vận hành |
| `Finance.OwnerTeam` | `payments-platform` | Nhóm xử lý khi cần xác minh |
| `Finance.AllocationMode` | `direct` hoặc `shared` | Định tuyến tới quy tắc phân bổ |

Đây là quy ước của ví dụ, không phải bộ tag OCI tạo sẵn. Trước khi áp dụng, cần tạo namespace và các key tương ứng.

Chọn những chiều có chủ sở hữu duy trì. Ví dụ, tên nhân viên dễ thay đổi và có thể trở thành thông tin cá nhân trong dữ liệu báo cáo; mã nhóm thường thích hợp hơn cho `OwnerTeam`.

**Defined tags** có namespace và định nghĩa do tổ chức quản lý. **Free-form tags** thuận tiện cho nhãn tự do nhưng khó chuẩn hóa hơn. Oracle khuyến nghị defined tags cho dữ liệu quản trị; không bắt buộc đánh dấu tag là cost-tracking để tag xuất hiện trong Cost Analysis hoặc Cost and Usage Reports. Xem [Overview of Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).

Nếu gặp hướng dẫn cũ yêu cầu “bật cost-tracking rồi mới phân tích được chi phí”, hãy đối chiếu tài liệu hiện hành trước khi đưa bước đó thành điều kiện bắt buộc.

### 4.2. Quy định giá trị hợp lệ

Tổ chức cần thống nhất:

- `prod`, `test` và `dev` là các giá trị môi trường được sử dụng trong ví dụ.
- `CC100` và `CC200` là mã có thật trong danh mục cost center nội bộ.
- `SHARED` là một nhóm chờ phân bổ đã được chủ sở hữu chấp nhận.
- Giá trị rỗng, mã không có trong danh mục hoặc cặp ứng dụng–cost center mâu thuẫn đều phải được đưa vào danh sách ngoại lệ.

Có tag chưa đủ để chứng minh tag đúng. Một tài nguyên gắn `CostCenter=CC100` nhưng phục vụ `analytics` có thể vẫn cần xác minh.

OCI hỗ trợ danh sách giá trị định sẵn và có thể kết hợp với tag default yêu cầu người tạo tài nguyên nhập giá trị. Điều này giúp hạn chế lỗi nhập tay. Xem [Using Predefined Values](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/usingpredefinedvalues.htm).

### 4.3. Áp dụng trên đúng tài nguyên phát sinh chi phí

Ví dụ phần dữ liệu `definedTags` trong yêu cầu tạo tài nguyên hỗ trợ defined tags:

~~~json
{
  "definedTags": {
    "Finance": {
      "CostCenter": "CC100",
      "Application": "payments",
      "Environment": "prod",
      "OwnerTeam": "payments-platform",
      "AllocationMode": "direct"
    }
  }
}
~~~

Đây chỉ là phần metadata, chưa phải payload hoàn chỉnh để tạo Compute instance hay database. Khi dùng Terraform hoặc công cụ khác, biểu diễn trường dữ liệu có thể khác.

Lập danh sách các thành phần phục vụ ứng dụng: instance, volume, bucket, database và các thành phần liên quan. Kiểm tra tags ở từng loại tài nguyên và trên dữ liệu chi phí thực tế. Không giả định rằng việc gắn tag lên instance sẽ tự gắn cùng tag lên mọi volume, bản sao lưu hay thành phần do dịch vụ tạo ra.

Tương tự, một tag trên bucket chỉ mô tả bucket. Nếu nhiều ứng dụng cùng lưu dữ liệu trong đó, một nhãn duy nhất không tự cho biết ứng dụng nào chiếm bao nhiêu dung lượng hoặc thực hiện bao nhiêu request. Khi cần mức chi tiết đó, tổ chức phải bổ sung số liệu sử dụng và quy tắc chia.

### 4.4. Tag defaults và yếu tố thời gian

Tag defaults áp dụng cho tài nguyên mới khi tạo trong compartment, bao gồm phạm vi kế thừa xuống các compartment con. Chúng không gắn bù cho tài nguyên đã tồn tại; đổi giá trị default cũng không sửa các tag đã áp dụng trước đó. Xem [Managing Tag Defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagdefaults.htm).

Vì vậy, một kế hoạch triển khai thực tế gồm hai việc:

1. Đặt quy tắc cho tài nguyên mới qua tag defaults hoặc quy trình triển khai hạ tầng.
2. Rà soát tài nguyên hiện hữu và bổ sung tags sau khi xác minh chủ sở hữu.

Cost Analysis ghi nhận chi phí theo thời điểm tag được liên kết với tài nguyên, không phân loại hồi tố toàn bộ chi phí trước đó. Xem [lưu ý về thời điểm áp dụng tags](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm).

Ví dụ, một volume phát sinh chi phí từ ngày 1 nhưng đến ngày 15 mới được gắn `CC100`. Không nên kỳ vọng rằng truy vấn tag lập tức quy cả nửa tháng đầu cho `CC100`.

Nếu cần phân bổ lại phần lịch sử, hãy tạo bảng ánh xạ có thời hạn hiệu lực trong hệ thống báo cáo nội bộ:

| Tài nguyên | Cost center | Có hiệu lực từ | Có hiệu lực đến | Căn cứ |
| --- | --- | --- | --- | --- |
| `volume-A` | `CC100` | `2026-10-01T00:00:00Z` | `2026-10-15T00:00:00Z` | Xác nhận chủ sở hữu và hồ sơ triển khai |

Lớp ánh xạ này bổ sung cách nhìn nghiệp vụ. Cần giữ nguyên dữ liệu nguồn để có thể giải thích vì sao báo cáo nội bộ phân loại khác kết quả truy vấn tags trong OCI.

## 5. Dùng Cost Analysis để khoanh vùng

Trong Console, mở **Billing & Cost Management → Cost Management → Cost Analysis**. Chọn khoảng ngày theo UTC, hiển thị Cost, áp dụng bộ lọc và chiều nhóm phù hợp, rồi kiểm tra bảng kết quả. Có thể lưu cấu hình thường dùng thành saved report. Xem [Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm).

Thay vì thêm tất cả bộ lọc ngay từ đầu, hãy thực hiện chuỗi phân tích có mục đích:

| Lượt phân tích | Cấu hình đề xuất | Điều cần rút ra |
| --- | --- | --- |
| Tổng quan kỳ | Phạm vi rộng, nhóm theo service | Dịch vụ nào chiếm phần lớn tổng tiền |
| Điều tra mức tăng | Cùng phạm vi, xem theo ngày | Mức tăng bắt đầu từ khi nào |
| Khoanh vùng hạ tầng | Xét region hoặc compartment liên quan | Thay đổi tập trung ở đâu |
| Xác định trách nhiệm | Xét tag `Finance.CostCenter` | Nhóm nào được quy chi phí trực tiếp |
| Truy vết phần còn thiếu | Đối chiếu với dữ liệu chi tiết | Khoản nào chưa được nhận diện |

Với mỗi lượt, ghi lại bộ lọc và tổng tiền. Nếu tổng giảm sau khi thêm tag filter, phần chênh lệch có thể là chi phí không khớp điều kiện; không nên tự coi đó là chi phí đã biến mất.

Một lỗi dễ gặp là nhập nhiều điều kiện rồi diễn giải chúng theo phép giao mà chưa xác nhận logic của công cụ. Hãy kiểm tra các dòng kết quả đại diện trước khi dùng một truy vấn làm báo cáo chính thức, đặc biệt khi phối hợp nhiều điều kiện tag.

Khi so hai kỳ, kiểm soát số ngày và mức độ hoàn chỉnh của dữ liệu. Chi phí của 20 ngày chưa phải số tương đương với một tháng trọn vẹn. Có thể tính chi phí trung bình mỗi ngày để quan sát sơ bộ, rồi bổ sung ảnh hưởng của cuối tuần, batch processing và sự kiện nghiệp vụ.

Cũng cần tách **cost** và **usage**. Hai dịch vụ có thể cùng tăng chi phí nhưng sử dụng các đơn vị khác nhau. Không cộng OCPU-hour, GB-month và request thành một tổng usage có ý nghĩa. Để giải thích mức tăng tiền, xem cả lượng sử dụng, đơn vị tính và thành phần giá tương ứng.

## 6. Dùng cost reports làm dữ liệu chi tiết

### 6.1. Chọn định dạng đầu vào

OCI cung cấp cost reports theo định dạng riêng và FOCUS. Usage reports cũ đã ngừng được khuyến nghị sử dụng từ ngày 31/01/2025; quy trình mới nên dựa trên cost reports. Mục **Cost Report Types** mô tả chu kỳ tạo khoảng sáu giờ, độ trễ có thể tới 24 giờ và thời gian lưu một năm. Xem [Cost Reports](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costusagereportsoverview.htm).

Chọn một định dạng làm nguồn chính cho cùng phạm vi. Nếu nhập cả định dạng riêng và FOCUS để kiểm chứng, giữ ở các tập dữ liệu riêng; không nối hai tập rồi cộng tiền vì có thể đếm hai lần cùng khoản tiêu thụ.

| Lựa chọn | Khi phù hợp |
| --- | --- |
| Định dạng riêng của OCI | Cần phân tích theo các trường gốc của OCI |
| FOCUS | Cần chuẩn hóa đầu vào cho hệ thống phân tích nhiều cloud |

Một số trường thường dùng trong định dạng riêng:

| Trường | Vai trò |
| --- | --- |
| `lineItem/intervalUsageStart` | Mốc bắt đầu sử dụng UTC |
| `product/resourceId` | Định danh tài nguyên |
| `product/compartmentId` | Định danh compartment |
| `cost/productSku` | SKU |
| `cost/myCost` | Chi phí dòng |
| `cost/currencyCode` | Tiền tệ |
| `tags/…` | Nhãn phân loại |

Tên và ngữ nghĩa trường đầy đủ nằm trong [schema cost reports của OCI](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costusagereportsoverview.htm#CostReportTypes). Khi xây dựng bộ đọc CSV, lấy tên cột từ header thực tế và đối chiếu schema; đừng tự suy tên cột tag từ cách hiển thị trên Console.

### 6.2. Phân biệt thời điểm sử dụng và thời điểm nhận dữ liệu

Hệ thống báo cáo nên lưu ít nhất hai mốc:

- **Thời gian sử dụng** để xếp khoản chi vào đúng kỳ.
- **Thời gian tiếp nhận** để biết kết quả được dựng từ dữ liệu có mặt lúc nào.

Một file mới nhận hôm nay có thể chứa dữ liệu sử dụng của ngày trước. Nếu chỉ đọc file có ngày tạo trùng ngày cần thống kê, quy trình có thể bỏ sót dữ liệu đến muộn.

Có thể áp dụng cửa sổ đối soát lại, chẳng hạn đọc lại các ngày gần đây và mở rộng khoảng đọc vào cuối kỳ. Đây là lựa chọn thiết kế của tổ chức, cần điều chỉnh theo dữ liệu quan sát được; không coi một lần chạy mỗi ngày là bảo đảm dữ liệu đã hoàn chỉnh.

### 6.3. Tải báo cáo từ Console

Chuyển sang **home region** của tenancy rồi mở **Cost and Usage Reports**. Chọn báo cáo và thao tác tải xuống; các báo cáo FOCUS được tổ chức theo ngày sử dụng trong giao diện. Xem [Listing Cost Reports](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/list-cost-usage-report.htm).

Khi lấy dữ liệu cho một kỳ, lập manifest các object đã tải và giữ cấu trúc tên nguồn. Không chỉ lấy một file đầu tiên nhìn thấy. Dùng manifest để biết lần chạy nào đã xử lý những object nào và giải thích chênh lệch giữa hai lần tổng hợp.

## 7. Tự động hóa thao tác đọc bằng OCI CLI

Các lệnh dưới đây dành cho **Bash**, ví dụ trong OCI Cloud Shell. Chúng minh họa thao tác đọc; người học cần thay các giá trị placeholder và có sẵn cấu hình xác thực, IAM phù hợp. Không đặt API key hoặc private key vào mã nguồn bài thực hành.

### 7.1. Truy vấn tổng hợp theo service và region

~~~bash
TENANCY_OCID='<your-tenancy-ocid>'
HOME_REGION='<your-home-region>'

oci usage-api usage-summary request-summarized-usages \
  --tenant-id "$TENANCY_OCID" \
  --time-usage-started '2026-10-01T00:00:00Z' \
  --time-usage-ended '2026-11-01T00:00:00Z' \
  --granularity DAILY \
  --query-type COST \
  --group-by '["service","region"]' \
  --region "$HOME_REGION"
~~~

Lệnh chọn dữ liệu chi phí thay vì chỉ tiêu usage và nhóm theo hai chiều. Có thể dùng `--group-by-tag` với cấu trúc JSON theo tài liệu CLI để phân tích một key cụ thể. Khi tự động hóa, xử lý phân trang nếu phản hồi có trang tiếp theo; đừng dùng `--limit` nhỏ rồi coi kết quả là toàn bộ dữ liệu. Xem [request-summarized-usages](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/usage-api/usage-summary/request-summarized-usages.html).

Usage API dùng mốc bắt đầu bao gồm và mốc kết thúc loại trừ. Khoảng trên là `[01/10, 01/11)` theo UTC. Xem [hướng dẫn Usage API trong Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm#UsingtheAPI).

Khi triển khai lịch chạy, tạo cả hai ranh giới từ cùng một quy tắc lịch. Không ghép các khoảng `[ngày 1, ngày 2]` và `[ngày 2, ngày 3]` theo cách vô tình tính ngày 2 hai lần.

### 7.2. Liệt kê và tải object của cost reports

Oracle sử dụng namespace `bling` và bucket có tên là OCID tenancy khách hàng để cung cấp các báo cáo này. Lệnh liệt kê mẫu:

~~~bash
oci os object list \
  --namespace-name bling \
  --bucket-name "$TENANCY_OCID" \
  --prefix 'reports/cost-csv' \
  --region "$HOME_REGION" \
  --all
~~~

Lấy **nguyên tên object** từ kết quả liệt kê rồi tải:

~~~bash
REPORT_OBJECT_NAME='<exact-object-name-from-list>'

oci os object get \
  --namespace-name bling \
  --bucket-name "$TENANCY_OCID" \
  --name "$REPORT_OBJECT_NAME" \
  --file './cost-report.csv.gz' \
  --region "$HOME_REGION"
~~~

Không tự tạo bucket `bling` trong tenancy của mình và không đoán tên file từ ngày tháng. Xem [liệt kê cost reports bằng CLI](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/list-cost-usage-report.htm) và [tải cost report bằng CLI](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/download-cost-usage-report.htm).

Tên file cục bộ cố định trong ví dụ chỉ phục vụ việc tải một object. Khi tải nhiều object, ánh xạ tên nguồn sang đường dẫn cục bộ duy nhất để không ghi đè file trước. Kiểm tra exit code của lệnh tải trước khi giải nén và nhập dữ liệu.

## 8. Xây dựng dữ liệu phân bổ có thể truy vết

Một mô hình xử lý đề xuất:

~~~mermaid
flowchart LR
    A[Cost reports] --> B[Lưu dữ liệu gốc và manifest]
    B --> C[Chuẩn hóa và đối soát]
    D[Danh mục cost center] --> E[Phân loại chi phí]
    F[Ánh xạ lịch sử có hiệu lực] --> E
    C --> E
    E --> G[Chi phí trực tiếp]
    E --> H[Chi phí dùng chung]
    E --> I[Chưa xác định]
    J[Số liệu và quy tắc chia] --> K[Phân bổ dùng chung]
    H --> K
    G --> L[Báo cáo và đối soát tổng]
    K --> L
    I --> L
~~~

### 8.1. Giữ dữ liệu gốc, chuẩn hóa ở lớp riêng

Với mỗi file, lưu định danh object, dấu thời gian nhận, kích thước hoặc checksum và phiên bản bộ đọc. Mỗi dòng chuẩn hóa nên truy ngược được tới object và vị trí hoặc định danh của nó trong dữ liệu gốc.

Đặt tên rõ cho trường chuẩn hóa như `usage_start_utc`, `currency`, `cost_amount`, `cost_center` và `allocation_mode`. Đây là schema nội bộ do tổ chức thiết kế, không phải tên trường OCI bắt buộc.

Một bộ nhập liệu phải chạy lại an toàn: nhập lại cùng object không được làm tăng gấp đôi tiền. Có thể dùng manifest và giao dịch nạp dữ liệu để bảo đảm một phiên bản object được ghi nhận một lần.

Không dùng riêng `resourceId + ngày` làm khóa duy nhất. Cùng một tài nguyên có thể xuất hiện ở nhiều khoảng thời gian và nhiều thành phần tính phí. Gộp quá sớm sẽ làm mất khả năng giải thích.

### 8.2. Giữ các dòng điều chỉnh

Cost reports có thể bổ sung dòng correction và tham chiếu dòng trước bằng các trường `lineItem/isCorrection`, `lineItem/backReferenceNo`. Xem [schema và cơ chế correction](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costusagereportsoverview.htm).

Phân biệt **nhập trùng dữ liệu** với **một điều chỉnh hợp lệ**. Cả hai có thể cùng nhắc tới một tài nguyên nhưng cần cách xử lý khác nhau.

Giữ nguyên liên kết và dấu của giá trị nguồn. Không xóa tất cả dòng correction, không tự lấy trị tuyệt đối và không mặc định “dòng mới nhất luôn thay hoàn toàn dòng trước”. Quy tắc đưa điều chỉnh vào số liệu phải dựa trên ngữ nghĩa dữ liệu và được đối soát trước khi sử dụng cho chargeback.

Các ví dụ SQL bên dưới giả định đã có một lớp dữ liệu hoàn tất bước nhập trùng, xử lý điều chỉnh và chọn kỳ. Chúng không phải bộ đọc cost report thô.

### 8.3. Đưa ngoại lệ vào báo cáo

Có thể phân loại mỗi dòng vào một trong ba nhóm:

| Nhóm | Điều kiện nghiệp vụ minh họa | Cách xử lý |
| --- | --- | --- |
| `direct` | Mã cost center hợp lệ, ứng dụng khớp danh mục | Quy trực tiếp |
| `shared` | Thuộc pool dùng chung đã đăng ký | Chờ áp dụng quy tắc chia |
| `unallocated` | Thiếu hoặc mâu thuẫn thông tin | Ghi riêng và giao xác minh |

Không thay mọi giá trị rỗng bằng cost center của nhóm hạ tầng. Làm vậy có thể che mất vấn đề quản trị tags và khiến nhóm hạ tầng phải chịu chi phí của các ứng dụng khác.

Nếu cần suy từ compartment, dùng bảng ánh xạ được duyệt và đánh dấu nguồn phân loại là `compartment_mapping`. Với ánh xạ từ tag, đánh dấu `resource_tag`. Từ đó có thể báo cáo rõ bao nhiêu tiền được xác định trực tiếp, bao nhiêu tiền dựa trên suy luận bổ sung.

## 9. Ví dụ phân bổ 1.000 USD

Các số sau **hoàn toàn giả định**, không phải bảng giá OCI. Giả sử dữ liệu một kỳ đã đủ để dùng trong ví dụ, cùng USD, không có điều chỉnh chưa xử lý.

| Khoản mục | Cost center | Chế độ | Chi phí USD |
| --- | --- | --- | ---: |
| Compute của `payments` | `CC100` | `direct` | 420 |
| Volume của `payments` | `CC100` | `direct` | 200 |
| Database của `analytics` | `CC200` | `direct` | 240 |
| Lưu trữ log dùng chung | `SHARED` | `shared` | 60 |
| Compute xử lý log dùng chung | `SHARED` | `shared` | 40 |
| Volume chưa xác định chủ sở hữu | Trống | `unallocated` | 40 |
| **Tổng** | | | **1.000** |

### 9.1. Bước đầu: giữ riêng ba nhóm

~~~text
Trực tiếp CC100       = 420 + 200 = 620 USD
Trực tiếp CC200       = 240 USD
Pool log dùng chung  = 60 + 40   = 100 USD
Chưa phân bổ         = 40 USD

620 + 240 + 100 + 40 = 1.000 USD
~~~

`SHARED` là nhãn định tuyến vào pool. Trong báo cáo sau phân bổ, không giữ thêm 100 USD như một khoản cuối cùng của nhóm nền tảng rồi lại cộng 100 USD đã chia cho hai ứng dụng.

### 9.2. Chọn tiêu chí chia và đóng băng số liệu kỳ

Trong ví dụ, tổ chức thỏa thuận chia pool xử lý và lưu trữ log theo dung lượng log tiếp nhận trong kỳ:

- `payments`: 3 đơn vị đo đã thống nhất.
- `analytics`: 2 đơn vị đo cùng loại.
- Tổng: 5 đơn vị.

Đây là một quy tắc đơn giản phục vụ minh họa. Khi thực tế cho thấy xử lý và lưu trữ có động lực chi phí khác nhau, nên tách chúng thành các pool có tiêu chí riêng.

Với pool `S` và trọng số `w_i`:

~~~text
SharedAllocation_i = S × w_i / Σw

payments:  100 × 3/5 = 60 USD
analytics: 100 × 2/5 = 40 USD
~~~

Nếu tổng trọng số bằng 0, không thực hiện phép chia. Giữ khoản tiền trong pool chưa phân bổ hoặc áp dụng quy tắc dự phòng đã được duyệt. Không tự chuyển thành chia đều chỉ vì thiếu dữ liệu.

### 9.3. Báo cáo kết quả và kiểm tra bảo toàn tổng

| Đơn vị hoặc bucket | Chi phí gốc | Nhận từ pool | Tổng USD |
| --- | ---: | ---: | ---: |
| `CC100` | 620 | 60 | 680 |
| `CC200` | 240 | 40 | 280 |
| Chưa phân bổ | 40 | 0 | 40 |
| **Tổng** | **900** | **100** | **1.000** |

Cột “Chi phí gốc” gồm 860 USD trực tiếp và 40 USD chưa nhận diện. Trong mô hình dữ liệu, khoản 40 USD vẫn thuộc nhóm `unallocated` riêng.

Đẳng thức cần giữ:

~~~text
Chi phí nguồn
  = Chi phí trực tiếp hợp lệ
  + Chi phí dùng chung
  + Chi phí chưa phân bổ ban đầu

Chi phí nguồn
  = Tổng chi phí cuối của các đơn vị
  + Chi phí còn chưa phân bổ

1.000 = 680 + 280 + 40
~~~

Nếu sau đó xác minh volume 40 USD thuộc `CC200`, số của `CC200` trở thành 320 USD và chưa phân bổ về 0. Đây là thay đổi phân loại có hồ sơ; tổng nguồn vẫn là 1.000 USD.

Khi tỷ lệ tạo số lẻ, tính bằng số thập phân đủ chính xác và làm tròn ở bước xuất báo cáo. Phần chênh một vài cent cần được phân bổ theo quy tắc cố định, có thể giải thích và tái hiện được.

## 10. SQL tổng hợp trên schema nội bộ

Giả sử view `cost_lines_ready` có các cột sau:

~~~text
usage_start_utc, currency, cost_amount,
cost_center, application, allocation_mode
~~~

View này đã chọn một nguồn chi phí, loại nhập trùng, xử lý điều chỉnh và chuẩn hóa phân loại theo mục 8. `cost_amount` dùng kiểu số thập phân, không dùng số dấu phẩy động cho phép tính tiền.

Ví dụ dưới đây dùng cú pháp PostgreSQL và tham số `:period_start_utc`, `:period_end_utc` do ứng dụng truyền vào. Các tham số phải là thời điểm UTC tương thích với kiểu cột.

~~~sql
SELECT
    currency,
    allocation_mode,
    CASE
        WHEN allocation_mode = 'direct' THEN cost_center
        WHEN allocation_mode = 'shared' THEN 'SHARED'
        ELSE 'UNALLOCATED'
    END AS allocation_bucket,
    SUM(cost_amount) AS source_cost
FROM cost_lines_ready
WHERE usage_start_utc >= :period_start_utc
  AND usage_start_utc <  :period_end_utc
GROUP BY
    currency,
    allocation_mode,
    CASE
        WHEN allocation_mode = 'direct' THEN cost_center
        WHEN allocation_mode = 'shared' THEN 'SHARED'
        ELSE 'UNALLOCATED'
    END
ORDER BY currency, allocation_mode, allocation_bucket;
~~~

Tách theo `currency` ngay từ đầu giúp tránh một tổng có ý nghĩa sai. Việc chọn kỳ bằng thời gian bắt đầu phù hợp với giả định các dòng đã được chuẩn hóa theo ranh giới kỳ. Nếu một dòng trải qua ranh giới đó, lớp chuẩn hóa phải xử lý theo quy tắc đã chọn trước.

Một phép đối soát tối thiểu so tổng nguồn và tổng sau phân bổ theo từng tiền tệ:

~~~sql
WITH source_total AS (
    SELECT currency, SUM(cost_amount) AS amount
    FROM source_cost_for_period
    GROUP BY currency
),
allocated_total AS (
    SELECT currency, SUM(allocated_amount) AS amount
    FROM final_allocations_for_period
    GROUP BY currency
)
SELECT
    COALESCE(s.currency, a.currency) AS currency,
    COALESCE(s.amount, 0) AS source_amount,
    COALESCE(a.amount, 0) AS allocated_amount,
    COALESCE(a.amount, 0) - COALESCE(s.amount, 0) AS difference
FROM source_total s
FULL OUTER JOIN allocated_total a
    ON a.currency = s.currency;
~~~

`source_cost_for_period` và `final_allocations_for_period` là hai view nội bộ đã được giới hạn cùng kỳ. View kết quả phải bao gồm cả các bucket chưa phân bổ. `FULL OUTER JOIN` giúp không bỏ qua loại tiền chỉ xuất hiện ở một phía. Kỳ vọng chênh lệch bằng 0, hoặc nằm trong ngưỡng làm tròn đã công bố khi đối soát báo cáo đã làm tròn.

Không cần chạy SQL này trực tiếp trên OCI Console. Nó minh họa cách tổ chức dữ liệu trong kho phân tích của doanh nghiệp.

## 11. Đối soát với báo cáo tài chính

Đối soát nên thực hiện theo thứ tự để tránh sửa quy tắc phân bổ nhằm che một lỗi phạm vi.

1. **Phạm vi:** cùng tenancy, subscription, kỳ và region liên quan.
2. **Tiền tệ và chỉ tiêu:** cùng loại chi phí, cùng cách ghi nhận.
3. **Mức độ đầy đủ:** đã thu thập hết object và xử lý các lần chạy lỗi.
4. **Điều chỉnh:** đã đưa dữ liệu đến muộn và các correction liên quan vào lần tính.
5. **Phân loại:** tổng trực tiếp, dùng chung và chưa xác định khớp nguồn.
6. **Phân bổ:** tổng số tiền sau chia khớp tổng trước chia.
7. **Kế toán:** giải thích các khoản khác biệt với chứng từ cần đối soát.

Chi phí tiêu thụ dùng cho phân tích vận hành và số tiền phải trả trên một chứng từ có thể có phạm vi ghi nhận khác nhau. Tổ chức cần đối chiếu riêng thuế, credits, khoản cam kết và điều chỉnh liên quan theo chứng từ cùng điều kiện subscription thực tế. Không ép hai con số bằng nhau bằng cách thêm một khoản không có căn cứ vào cost center bất kỳ.

Một bảng đối soát có thể ghi:

| Khoản | Số tiền | Nguồn chứng minh | Cách xử lý |
| --- | ---: | --- | --- |
| Chi phí tiêu thụ của kỳ | Theo dữ liệu đã chốt | Manifest và dữ liệu nguồn | Phân bổ theo quy tắc |
| Khoản khác biệt được xác nhận | Theo chứng từ | Tham chiếu chứng từ | Ghi rõ thuộc hay ngoài phạm vi |
| Chênh lệch chưa giải thích | Theo phép đối soát | Hồ sơ đang xác minh | Giữ riêng, chưa chốt chargeback |

Một báo cáo có thể được công bố là “tạm tính” trong lúc chờ xác minh. Ngày chốt và người duyệt cần rõ ràng; sửa kỳ đã chốt phải tạo phiên bản điều chỉnh để người dùng hiểu sự thay đổi.

## 12. Đo chất lượng phân bổ và xử lý sai lệch

### 12.1. Theo dõi chất lượng theo giá trị tiền

Đếm số tài nguyên có tags hữu ích cho quản trị, nhưng chưa phản ánh mức độ bao phủ về tiền. Một database lớn thiếu tags có thể quan trọng hơn hàng trăm tài nguyên nhỏ đã được gắn đầy đủ.

Với dữ liệu chi phí không âm trong ví dụ:

~~~text
Tỷ lệ chi phí đã nhận diện
  = (Chi phí trực tiếp hợp lệ + Pool dùng chung hợp lệ)
    / Tổng chi phí nguồn

  = (860 + 100) / 1.000
  = 96%
~~~

“Đã nhận diện” bao gồm 100 USD đã xác định đúng pool; nó không có nghĩa là tiền đã được chia cho đơn vị cuối cùng. Sau khi chia pool, tỷ lệ chi phí đã quy cho đơn vị cuối là `(680 + 280) / 1.000 = 96%`; hai tỷ lệ bằng nhau ở ví dụ này nhưng không phải luôn như vậy.

Nếu có credits hoặc chi phí âm, tổng ròng có thể làm tỷ lệ khó diễn giải. Khi đó cần công bố cách tính riêng cho phần chi phí dương, credits và điều chỉnh, thay vì áp dụng máy móc công thức trên.

Nên theo dõi thêm số tiền chưa phân bổ, tuổi của các ngoại lệ, số tiền trong pool chưa có trọng số và số kỳ phải sửa sau khi chốt. Mỗi ngoại lệ cần một nhóm phụ trách cùng hạn xử lý.

### 12.2. Các tình huống thường gặp

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Tag vừa gắn chưa hiện trong chi phí | Kiểm tra thời điểm gắn và độ mới của dữ liệu |
| Lọc tag thấy tổng thấp hơn tổng tenancy | Tìm khoản không khớp tag, thiếu tag hoặc ngoài phạm vi đã chọn |
| Tải reports bị từ chối nhưng vẫn xem được Cost Analysis | Kiểm tra riêng quyền tải object và nơi lưu báo cáo |
| Không thấy báo cáo mong đợi | Kiểm tra home region, quyền truy cập và danh sách object |
| Tổng tăng gấp đôi sau một lần chạy lại | Kiểm tra nhập trùng hoặc nạp cả hai định dạng vào cùng tổng |
| Tổng usage lớn nhưng không giải thích được | Tách SKU và đơn vị đo trước khi cộng |
| Nhóm nhận chi phí mà không sở hữu tài nguyên | Kiểm tra ánh xạ lịch sử, quy tắc pool và metadata gốc |
| Tổng sau phân bổ lớn hơn nguồn | Kiểm tra pool còn bị cộng thêm sau khi đã chia hoặc join nhân bản dòng |

Đối với lỗi join, đặc biệt chú ý bảng ánh xạ một tài nguyên với nhiều bản ghi có thời hạn hiệu lực chồng lấn. Một dòng chi phí ghép với hai cost center có thể bị tính hai lần dù dữ liệu gốc chỉ được nhập một lần.

## 13. Quy trình thực hành và kết quả cần lưu

Có thể thực hành trên tài nguyên đã có quyền xem mà không tạo thêm hạ tầng trả phí:

1. Chọn một kỳ đã có dữ liệu và ghi đầy đủ phạm vi.
2. Dùng Cost Analysis xác định hai hoặc ba nhóm chi phí lớn.
3. Chọn một tag phân bổ chính và kiểm tra vài tài nguyên đại diện.
4. Tải cost reports phù hợp, ghi manifest và lưu nguyên bản.
5. Chuẩn hóa dữ liệu, xác định chi phí trực tiếp, pool và ngoại lệ.
6. Áp dụng một quy tắc chia đã nêu rõ trọng số và nguồn đo.
7. Đối soát theo tiền tệ, giữ riêng các khoản chưa giải thích.
8. Xuất bảng showback với trạng thái dữ liệu và ngày tính.

Kết quả thực hành nên có một bảng tổng nguồn, một bảng phân bổ, một danh sách ngoại lệ và mô tả quy tắc đủ để người khác tính lại. Không cần sửa tags trên tài nguyên sản xuất chỉ để làm đẹp báo cáo thực hành.

Trong vận hành, dữ liệu này hỗ trợ quyết định về chi phí và năng lực. Ví dụ, khi chi phí volume của `payments` tăng, kết hợp với số liệu dung lượng sử dụng và yêu cầu lưu giữ để đánh giá phương án. Khi chi phí database tăng, cần xem cả tải nghiệp vụ và yêu cầu sẵn sàng trước khi thay đổi cấu hình.

Báo cáo chi phí chỉ ra nơi cần điều tra. Quyết định tối ưu cần thêm bằng chứng vận hành, chủ sở hữu chịu trách nhiệm và phương án duy trì chất lượng dịch vụ.

## 14. Tài liệu tham khảo

Các nguồn dưới đây phục vụ tra cứu hành vi OCI và cú pháp; các số tiền, tên ứng dụng, mô hình dữ liệu và quy tắc chia trong bài là ví dụ học tập.

- [OCI Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm).
- [OCI Cost Reports và schema](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costusagereportsoverview.htm).
- [Listing Cost Reports](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/list-cost-usage-report.htm).
- [Downloading a Cost Report](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/download-cost-usage-report.htm).
- [Overview of Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).
- [Managing Tag Defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagdefaults.htm).
- [Using Predefined Values](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/usingpredefinedvalues.htm).
- [OCI CLI: request-summarized-usages](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/usage-api/usage-summary/request-summarized-usages.html).
