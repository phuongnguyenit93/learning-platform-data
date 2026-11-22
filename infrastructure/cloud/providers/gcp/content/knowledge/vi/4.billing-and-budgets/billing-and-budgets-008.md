# Xuất dữ liệu thanh toán sang BigQuery

> **Chương:** Thanh toán và ngân sách  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Khi quản lý nhiều project trên Google Cloud, Cloud Billing Reports giúp xem nhanh chi phí, nhưng các nhóm kỹ thuật và tài chính thường cần trả lời câu hỏi sâu hơn: *Project production tiêu bao nhiêu so với development? Dịch vụ nào khiến hóa đơn tăng? SKU nào phát sinh phí truyền dữ liệu? Chiết khấu và credit đã được tính như thế nào?* Khi cần dữ liệu có thể truy vấn bằng SQL, chia sẻ cho các báo cáo nội bộ hoặc kết hợp với thông tin owner/team, **Cloud Billing export to BigQuery** là công cụ thích hợp.

Bài học này thuộc **CLOUD_PROVIDERS_GCP**, mô-đun khám phá Google Cloud từ tổ chức project, IAM, VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học cần biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Bài học tập trung vào cấu hình luồng export, hiểu dữ liệu, viết truy vấn và vận hành báo cáo chi phí đúng cách.

Sau bài học, người học có thể:

1. Giải thích sự khác nhau giữa Cloud Billing Reports, Budgets và dữ liệu export sang BigQuery.
2. Chọn loại export phù hợp giữa Standard, Detailed, Pricing, FOCUS và CUD metadata.
3. Chuẩn bị billing account, project, quyền IAM, BigQuery API, dataset và location.
4. Bật export trong Console, kiểm tra bảng và hiểu phạm vi dữ liệu được hồi tố.
5. Viết SQL tổng hợp chi phí theo project, service, SKU, thời gian và credits.
6. Xử lý các trường hợp bảng trễ, số liệu không khớp hóa đơn, thiếu nhãn hoặc nhân đôi chi phí.

## 1. Dòng dữ liệu từ Cloud Billing đến BigQuery

**Cloud Billing account** là tài khoản thanh toán liên kết với một hoặc nhiều Google Cloud project. Khi bật export, Google Cloud tự động ghi các bản ghi chi phí/usage tương ứng vào **BigQuery dataset** được cấu hình. Sau đó, người có quyền truy vấn dataset có thể chạy GoogleSQL, tạo view, dashboard hoặc bảng tổng hợp.

~~~mermaid
flowchart LR
  subgraph APP["Project phát sinh chi phí"]
    P1["app-dev"]
    P2["app-prod"]
    P3["data-prod"]
  end
  P1 --> B["Cloud Billing account"]
  P2 --> B
  P3 --> B
  B --> EX["Cloud Billing export"]
  EX --> DS["BigQuery dataset trong project FinOps"]
  DS --> SQL["SQL / View / Scheduled query"]
  SQL --> DASH["Báo cáo / Dashboard"]
  SQL --> FIN["Điều tra biến động chi phí"]
~~~

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Billing account** | Đơn vị thanh toán nhận chi phí từ nhiều project | Billing account của doanh nghiệp |
| **Workload project** | Chạy VM, GKE, Cloud Run, Cloud SQL và phát sinh usage | `app-prod` |
| **Export project** | Chứa dataset, quản lý quyền và chi phí BigQuery | `finops-admin` |
| **Dataset** | Container của bảng dữ liệu và view | `billing_export` |
| **Export table** | Bảng do dịch vụ Billing tạo và ghi | `gcp_billing_export_v1_...` |
| **Query job** | Truy vấn bảng trong BigQuery, có thể phát sinh chi phí | Phân tích net cost theo project |

Đối với **Standard** và **Detailed usage export**, bảng ghi dữ liệu usage/cost của **các project do cùng billing account chi trả**, không chỉ project chứa BigQuery dataset. Project lưu export cần được bật billing và liên kết với billing account cần xuất theo tài liệu cấu hình hiện hành.

### 1.1. Vì sao không chỉ dùng Cloud Billing Reports?

| Nhu cầu | Reports/Budgets | Export + BigQuery |
| --- | --- | --- |
| Xem xu hướng chi phí theo project, service | Giao diện có sẵn và trực quan | Viết truy vấn hoặc dựng dashboard |
| Đặt ngưỡng ngân sách và nhận thông báo | Dùng Budgets & alerts | Cần thêm cơ chế cảnh báo riêng nếu dựa vào SQL |
| Xem phân bổ theo team, cost center, quy tắc nội bộ | Tùy bộ lọc có sẵn | Linh hoạt kết hợp label, tag, bảng metadata |
| Phân tích invoice, adjustment, credits, SKU | Báo cáo tổng hợp | Truy cập dữ liệu để tính toán chi tiết |
| Kết hợp với danh mục ứng dụng hoặc bảng owner | Hạn chế | Dùng JOIN dữ liệu có quyền truy cập |
| Tạo báo cáo định kỳ tùy chỉnh | Có lựa chọn sẵn trong sản phẩm | Dùng view, scheduled query và công cụ BI |

**Không coi BigQuery export là nguồn realtime**: từng dịch vụ báo cáo usage theo chu kỳ khác nhau; quá trình export có độ trễ và không có bảo đảm cố định về thời gian giao nhận. Budget alert cũng không tự động tắt toàn bộ dịch vụ khi vượt ngưỡng. Export hữu ích để phân tích và ra quyết định, còn phản ứng tự động cần thiết kế riêng.

## 2. Các loại dữ liệu có thể xuất

Cloud Billing cung cấp nhiều tùy chọn. Khi học, cần phân biệt **dữ liệu chi phí đã phát sinh** với **danh mục giá** hoặc **metadata cam kết**.

| Loại | Thông tin chính | Tên bảng/đích thường gặp | Phù hợp khi |
| --- | --- | --- | --- |
| **Standard usage cost** | Billing account, project, service, SKU, usage, cost, credits, labels, invoice, currency | `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>` | Tổng hợp chi phí theo project, service, SKU |
| **Detailed usage cost** | Mọi trường Standard và dữ liệu chi tiết cấp resource của những dịch vụ được hỗ trợ | `gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>` | Tìm VM/resource gây tăng phí |
| **Pricing data** | Giá theo billing account, SKU, đơn vị tính, bậc giá, vùng | `cloud_pricing_export` | Nghiên cứu đơn giá và chính sách giá |
| **FOCUS usage cost** | Bản ghi usage/cost chuẩn hóa theo FinOps Open Cost and Usage Specification | Dataset do Google cung cấp với bảng `gcp_billing_export_focus_<BILLING_ACCOUNT_ID>` | Chuẩn hóa dữ liệu cho FinOps/đa đám mây |
| **CUD metadata** | Cam kết sử dụng, loại sản phẩm, scope, thời hạn, lượng cam kết | Linked dataset với bảng `cud_subscriptions_export` | Theo dõi danh mục committed use discounts |

**Bắt đầu với Standard** nếu mục tiêu là biết project nào tiêu nhiều tiền hoặc dịch vụ nào tăng. Chỉ bật **Detailed** khi cần chiều resource; dữ liệu chi tiết thường chiếm dung lượng và chi phí phân tích lớn hơn.

Một vài khác biệt thực tế:

- Detailed chứa các trường Standard và thêm một số thông tin resource, nhưng **không phải mọi dịch vụ hoặc SKU đều xuất chi tiết giống nhau**.
- Muốn phân tích chi phí theo workload/namespace của **GKE**, cần kiểm tra khả năng **GKE cost allocation** và kích hoạt theo hướng dẫn tương ứng; chỉ bật Detailed không đủ bảo đảm có mọi chiều phân bổ.
- Pricing data là dòng xuất riêng, yêu cầu điều kiện API/quyền khác với usage export.
- FOCUS/CUD metadata có thể ở trạng thái **Preview** và cách tạo dataset/vòng đời dữ liệu khác nhau. Theo tài liệu đang công bố, bảng FOCUS do Google cung cấp có chính sách **TTL hai năm**.
- **Không cộng Standard và Detailed vào cùng một tổng**: cùng một usage có thể xuất hiện ở cả hai bảng, dẫn đến đếm trùng.

### 2.1. Chọn loại export từ câu hỏi cần giải quyết

- “Chi phí tháng này của app-prod là bao nhiêu?” → Standard theo project/invoice.
- “Compute Engine tăng do SKU nào?” → Standard theo service và SKU.
- “VM nào chiếm tỷ trọng lớn?” → Detailed theo trường resource, nếu được hỗ trợ.
- “Giá của SKU theo tầng/mô hình consumption?” → Pricing.
- “Hợp đồng cam kết nào sắp hết hạn?” → CUD metadata kết hợp báo cáo quản lý CUD.
- “Muốn chuẩn hóa đa nhà cung cấp theo FOCUS?” → Xem FOCUS export và phiên bản schema hiện hành.

## 3. Chuẩn bị billing account, project và IAM

### 3.1. Chọn project lưu dữ liệu

Một kiến trúc thường dùng:

~~~text
Cloud Billing account BILLING_ACCOUNT_ID
├── app-dev                (workload)
├── app-prod               (workload)
├── analytics-prod         (workload)
└── finops-admin           (project lưu export)
    └── billing_export     (BigQuery dataset)
        ├── gcp_billing_export_v1_...
        └── gcp_billing_export_resource_v1_...
~~~

Dùng project FinOps riêng giúp đặt quyền, budget và vòng đời dữ liệu độc lập với hệ thống ứng dụng. **Đảm bảo export project được liên kết với đúng billing account cần xuất.** Billing account và project có quan hệ thanh toán; việc đặt cùng tên không bảo đảm đã liên kết đúng.

### 3.2. Vai trò cần có

Tài liệu của Google phân biệt quyền theo loại export:

| Tác vụ | Điều kiện quyền cần kiểm tra |
| --- | --- |
| Bật Standard/Detailed usage export | **Billing Account Costs Manager** hoặc **Billing Account Administrator** trên billing account; **BigQuery User** trên project chứa dataset |
| Bật Pricing/CUD metadata export | **Billing Account Administrator** trên billing account; **BigQuery Admin** trên project chứa dataset, cùng quyền `resourcemanager.projects.update` theo hướng dẫn |
| Tạo project mới | Quyền tạo project do tổ chức cấp, thường qua Project Creator |
| Tạo dataset hoặc bật API | Quyền BigQuery/Service Usage tương ứng trên export project |
| Đọc bảng và chạy SQL | Quyền truy cập dữ liệu bảng và quyền tạo query job trên project dùng để chạy |

Quyền trên **billing account** và quyền trên **project/dataset BigQuery** là hai lớp riêng. Người có thể xem Billing Reports chưa chắc có quyền tạo dataset; người có quyền BigQuery chưa chắc có quyền bật export. Cần tuân thủ IAM tối thiểu, thay vì cấp Owner rộng để vượt lỗi permission.

### 3.3. API và chi phí

- **BigQuery API** phải được bật trên project đích; Console có thể nhắc bật khi cấu hình.
- Nếu bật **Pricing data export**, cần bật **BigQuery Data Transfer Service API** trên project chứa dataset.
- Standard/Detailed usage export không cần Data Transfer Service API **chỉ vì** là luồng cost export.
- Lưu trữ BigQuery và các truy vấn/scheduled query có thể phát sinh chi phí. Nên bật budget cho export project và theo dõi usage.

### 3.4. Chọn location trước khi tạo dataset

Location của BigQuery dataset **không đổi được sau khi tạo**. Cloud Billing hỗ trợ hai multi-region **US/EU** và chỉ một số region riêng lẻ.

| Location của dataset | Khi **bật mới lần đầu** usage export | Điều cần nhớ |
| --- | --- | --- |
| **US/EU multi-region** | Google có thể backfill dữ liệu từ **ngày đầu tháng trước** so với ngày bật | Dữ liệu lịch sử được nạp tuần tự; có thể mất đến khoảng năm ngày mới bắt kịp |
| **Region được hỗ trợ** | Chỉ bắt đầu từ **ngày bật export** | Không tự hồi tố lịch sử trước đó |
| **Region không được hỗ trợ** | Không thể lưu cấu hình | Có thể báo `Invalid dataset region` |

**Ví dụ:** Bật Standard export lần đầu ngày **19/11/2026** tại dataset US multi-region có thể nhận dữ liệu từ **01/10/2026**, theo chính sách hiện công bố. Nếu dùng dataset ở một region được hỗ trợ, dữ liệu chỉ bắt đầu từ ngày bật. Đây là ví dụ về chính sách và phạm vi lịch sử, **không phải cam kết đã có đầy đủ dữ liệu ngay ngày bật**.

Những ngoại lệ cần nhớ:

- **Pricing export không backfill** dữ liệu trước thời điểm bật.
- Tắt rồi bật lại có thể để lại khoảng thiếu export trong giai đoạn tắt.
- Chuyển sang project/dataset mới **không tự sao chép** lịch sử đã xuất sang nơi cũ.
- Dữ liệu đã xóa khỏi bảng export thường không thể yêu cầu dịch vụ backfill lại tùy ý.
- Việc chọn US/EU phải phù hợp chính sách lưu trú dữ liệu. Nếu tổ chức bắt buộc region cụ thể, hãy xác minh region đó được hỗ trợ và chấp nhận giới hạn không hồi tố.

Xem danh sách location được Google duy trì tại [Set up Cloud Billing data export](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup#dataset-locations). Không giả định mọi region của BigQuery đều hợp lệ cho Billing export.

### 3.5. Ước lượng dữ liệu và chi phí BigQuery

Bật Detailed có thể tạo nhiều bản ghi hơn Standard. Khi xây dashboard, chi phí còn đến từ quét dữ liệu hoặc bảng kết quả lưu lại. Cách quản lý:

1. Chọn loại export đủ dùng cho câu hỏi.
2. Giới hạn thời gian và các trường truy vấn cần thiết; kiểm tra **bytes processed** trước khi chạy truy vấn lớn.
3. Dùng view để chuẩn hóa schema và bảng tổng hợp cho báo cáo lặp lại.
4. Đặt budget và theo dõi chính chi phí BigQuery của project FinOps.
5. Đánh giá nhu cầu lưu trữ, quyền truy cập và retention trước khi bật hàng loạt loại export.

## 4. Bật Standard/Detailed export trong Google Cloud Console

### Bước 1 — Chuẩn bị project và dataset

Mở [BigQuery Console](https://console.cloud.google.com/bigquery), chọn export project và **Create dataset** trong Explorer. Ví dụ:

~~~text
Billing account : BILLING_ACCOUNT_ID
Export project  : finops-admin
Dataset ID      : billing_export
Dataset location: US (hoặc vị trí đã được phê duyệt)
~~~

Kiểm tra billing đã bật trên export project và project liên kết với đúng billing account. Dataset phải ở một location được Billing export hỗ trợ. Nếu có yêu cầu mã hóa bằng khóa do khách hàng quản lý (CMEK), cần xem quy định đặc thù; không mặc định mọi thiết lập CMEK đều dùng được ngay.

### Bước 2 — Mở Billing export

1. Mở [Billing Console](https://console.cloud.google.com/billing).
2. Chọn **Billing account** cần xuất.
3. Vào trang **Billing export** → tab **BigQuery export**.
4. Chọn **Enable standard usage cost export** hoặc **Enable detailed usage cost export**.
5. Chọn export project và dataset đích đã chuẩn bị.
6. Xác nhận Billing Account ID, Project ID, Dataset ID và loại export, sau đó **Save**.

Với Pricing, bật riêng mục **Pricing data export** và bảo đảm API/quyền của loại này. Với FOCUS/CUD metadata, đọc riêng hướng dẫn setup vì quy trình và dataset không hoàn toàn giống Standard/Detailed.

**Không cần tự tạo export table hay chạy `bq load`**. Dịch vụ Cloud Billing tạo và ghi bảng sau khi bạn bật thành công. Tên/nút trên Console có thể đổi qua các phiên bản; nên đối chiếu với tài liệu chính thức trước khi thao tác trong môi trường thực.

### Bước 3 — Chờ dữ liệu và xác minh

- Standard/Detailed usage export có thể cần **vài giờ** để bắt đầu có dữ liệu.
- Khi backfill lịch sử vào US/EU multi-region, dữ liệu được xuất theo thứ tự thời gian và có thể cần tới **năm ngày** để bắt kịp usage gần nhất.
- Pricing export có thể mất đến **48 giờ** để xuất bản ghi đầu tiên; sau đó dữ liệu giá được xuất theo chu kỳ ngày.
- Không có bảo đảm dữ liệu usage sẽ luôn xuất trong một số phút cố định.

Trong BigQuery Explorer, mở dataset và kiểm tra bảng. Nếu dùng CLI đã đăng nhập và được cấp quyền:

~~~bash
# Xem dataset trong project (chỉ đọc)
bq ls --project_id=FINOPS_PROJECT_ID

# Xem bảng bên trong dataset (chỉ đọc)
bq ls FINOPS_PROJECT_ID:billing_export
~~~

Trường hợp bảng chưa xuất hiện ngay sau Save chưa đủ để kết luận cấu hình bị hỏng. Hãy kiểm tra đúng Billing account/project/dataset và trạng thái export trước khi lặp lại thao tác bật/tắt.

## 5. Tên bảng và schema cơ bản

Khi dữ liệu đến BigQuery, một số tên bảng thường gặp:

~~~text
gcp_billing_export_v1_<BILLING_ACCOUNT_ID>
gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>
cloud_pricing_export
gcp_billing_export_focus_<BILLING_ACCOUNT_ID>
cud_subscriptions_export
~~~

Bảng FOCUS và CUD metadata có cách tạo/đích riêng. **Luôn sao chép tên bảng đầy đủ trong BigQuery Explorer**, vì phần định dạng Billing Account ID trong table ID thực tế có thể khác cách hiển thị ID ngoài Console.

| Trường Standard/Detailed | Ý nghĩa |
| --- | --- |
| `billing_account_id` | Billing account gắn với chi phí |
| `project.id`, `project.name` | Project phát sinh chi phí; có thể thiếu trên một số dòng |
| `service.description` | Dịch vụ phát sinh usage |
| `sku.description` | SKU tính phí |
| `usage_start_time`, `usage_end_time` | Khoảng thời gian usage |
| `invoice.month` | Tháng hóa đơn ở dạng `YYYYMM` |
| `cost` | Chi phí ghi trên dòng theo `currency`, chưa cộng các credit của dòng |
| `credits` | Mảng credit/discount của dòng; `credits.amount` thường âm |
| `cost_type` | Loại dòng: `regular`, `tax`, `adjustment`, `rounding_error` |
| `currency` | Đồng tiền của cost/credits |
| `labels`, `project.labels`, `tags` | Thuộc tính hỗ trợ phân bổ chi phí |
| `location` | Chiều địa lý tùy SKU/dịch vụ |
| `export_time` | Thời điểm dữ liệu được xuất |

Bảng **Detailed** có thêm một số trường cấp resource như `resource.name`, `resource.global_name`. Các trường này **không có dữ liệu đầy đủ cho mọi dịch vụ và dòng phí**.

**Invoice month khác usage month:** Usage ngày cuối tháng có thể được ghi vào hóa đơn của tháng sau; thuế và điều chỉnh cũng có quy tắc ghi riêng. Vì vậy tổng theo `DATE(usage_start_time)` có thể khác tổng theo `invoice.month`.

**Schema có thể thay đổi:** Google có thể thêm trường khi mở rộng tính năng export. Để báo cáo ổn định, sử dụng view chuẩn hóa các trường cần dùng, tránh phụ thuộc `SELECT *` hoặc tự thay cấu trúc bảng do dịch vụ quản lý.

## 6. Tính đúng chi phí và credits

**Gross cost** là tổng `cost` của các dòng được chọn. **Credits** là khoản giảm trừ gắn với dòng, ví dụ Free Tier, ưu đãi hoặc committed use discount. **Net cost** của báo cáo học tập thường tính:

~~~text
net_cost = SUM(cost + tổng credits.amount của từng dòng)
~~~

Ví dụ giả định cùng một đồng tiền:

| Khoản mục | Cost | Credits | Net |
| --- | ---: | ---: | ---: |
| Compute Engine | 100 | -20 | 80 |
| Cloud Run | 10 | -3 | 7 |
| Cloud Storage | 15 | Không có | 15 |
| **Tổng** | **125** | **-23** | **102** |

Một dòng có thể có **nhiều credits** hoặc không có credit nào. Nếu nối trực tiếp `CROSS JOIN UNNEST(credits)` rồi tính `SUM(cost)`, dòng có hai credits làm cost bị nhân đôi; dòng không có credits có thể biến mất.

Để giữ mỗi cost line đúng một lần, dùng *scalar subquery*:

~~~sql
-- Tổng các credit của một dòng, trả 0 nếu không có credit
IFNULL(
  (SELECT SUM(c.amount) FROM UNNEST(credits) AS c),
  0
)
~~~

Công thức trên lấy tổng mảng credits riêng cho từng dòng mà không sinh dòng bổ sung. Với báo cáo tài chính, cần thống nhất quy tắc làm tròn, loại cost và thời điểm chốt số liệu; không suy rằng `net_cost` tự động bằng số tiền đã trả sau mọi loại thanh toán, thuế hoặc điều chỉnh.

## 7. Các truy vấn GoogleSQL để thực hành

Các ví dụ sau sử dụng **Standard usage cost export** và chỉ đọc bảng. Trước khi chạy, thay tên bảng bằng **đường dẫn bảng chính xác** được sao chép từ BigQuery Explorer. Một ví dụ tên dạng:

~~~text
FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC
~~~

Phần `ABCDEF_123456_789ABC` chỉ là ví dụ placeholder. Trong BigQuery SQL, tên đầy đủ của bảng được đặt giữa dấu backtick. Dùng một bảng usage export cho một phép tổng hợp, không nối Standard và Detailed làm nguồn cho cùng phép tính.

### 7.1. Bảng có bao nhiêu dòng và mới đến đâu?

~~~sql
SELECT
  COUNT(*) AS total_rows,
  MIN(usage_start_time) AS earliest_usage,
  MAX(usage_start_time) AS latest_usage,
  MAX(export_time) AS latest_export
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC`;
~~~

- `total_rows = 0`: có thể chưa phát sinh usage được ghi hoặc export mới được bật.
- `latest_usage`: thời điểm usage mới nhất có trong bảng; không chứng minh tất cả dịch vụ đã báo cáo đủ.
- `latest_export`: mốc export cuối có trong các bản ghi, hữu ích để đánh giá độ mới, không phải cam kết thời gian cập nhật.

Với dataset lớn, truy vấn không có bộ lọc có thể quét nhiều dữ liệu. Sau khi xác minh bước đầu, nên giới hạn phạm vi hoặc dùng bảng tổng hợp đã tạo cho kiểm tra lặp lại.

### 7.2. Chi phí theo project cho một tháng hóa đơn

~~~sql
SELECT
  invoice.month AS invoice_month,
  COALESCE(project.id, '(khong-co-project)') AS project_id,
  currency,
  ROUND(SUM(cost), 2) AS gross_cost,
  ROUND(
    SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS credits_total,
  ROUND(
    SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS net_cost
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC`
WHERE invoice.month = '202611'
GROUP BY invoice_month, project_id, currency
ORDER BY net_cost DESC;
~~~

Kết quả ghi rõ cả **gross**, **credits** và **net**. Nhóm `(khong-co-project)` không nên bị bỏ mặc: một số dòng liên quan đến Billing account có thể không quy thuộc riêng một project. Đồng tiền được giữ trong `GROUP BY` để không cộng USD và VND thành một con số không có ý nghĩa.

### 7.3. Chi phí theo ngày sử dụng và dịch vụ

~~~sql
SELECT
  DATE(usage_start_time, 'UTC') AS usage_day,
  service.description AS service_name,
  currency,
  ROUND(
    SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS net_cost
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC`
WHERE usage_start_time >= TIMESTAMP('2026-11-01 00:00:00+00')
  AND usage_start_time < TIMESTAMP('2026-12-01 00:00:00+00')
GROUP BY usage_day, service_name, currency
ORDER BY usage_day, net_cost DESC;
~~~

Ở đây ngày được chuẩn hóa theo **UTC**. Nếu báo cáo nội bộ cần múi giờ Việt Nam, có thể đổi sang `DATE(usage_start_time, 'Asia/Ho_Chi_Minh')` và điều chỉnh ranh giới thời gian truy vấn cho nhất quán.

Báo cáo “usage trong tháng 11” **không nhất thiết** bằng báo cáo “invoice month 202611” vì thời điểm sử dụng và thời điểm ghi vào hóa đơn có thể khác nhau.

### 7.4. Top SKU theo net cost của một kỳ

~~~sql
SELECT
  service.description AS service_name,
  sku.description AS sku_name,
  currency,
  ROUND(
    SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS net_cost
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC`
WHERE invoice.month = '202611'
  AND cost_type = 'regular'
GROUP BY service_name, sku_name, currency
ORDER BY net_cost DESC
LIMIT 30;
~~~

Lọc `cost_type = 'regular'` giúp nghiên cứu các SKU usage. Điều đó **loại bỏ** dòng thuế, một số điều chỉnh và làm tròn, nên không được dùng kết quả top SKU để khẳng định đã đối chiếu đủ toàn bộ hóa đơn.

### 7.5. Chi phí theo nhãn `team` của project

Giả sử các project đã có label chuẩn `team`:

~~~sql
SELECT
  COALESCE(
    (SELECT ANY_VALUE(l.value)
     FROM UNNEST(project.labels) AS l
     WHERE l.key = 'team'),
    '(chua-gan-team)'
  ) AS team,
  currency,
  ROUND(
    SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS net_cost
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC`
WHERE invoice.month = '202611'
GROUP BY team, currency
ORDER BY net_cost DESC;
~~~

Đây là phân bổ theo **project label**, không phải tất cả resource label hoặc tag. Nếu nhãn trống, dòng nằm trong nhóm chưa phân bổ. Khi đổi label, các dòng lịch sử thường phản ánh trạng thái của tài nguyên tại thời điểm usage được ghi, chứ không tự đổi theo label mới.

Để phân bổ chi phí đáng tin cậy, cần quy định: nhãn nào bắt buộc, ai là owner, cách xử lý missing label, và những chi phí dùng chung như network hoặc dịch vụ nền được chia theo công thức nào.

### 7.6. Kiểm tra cost theo resource bằng bảng Detailed

Với Detailed export, có thể thử nhóm theo trường resource:

~~~sql
SELECT
  project.id AS project_id,
  service.description AS service_name,
  COALESCE(resource.name, '(khong-co-resource-name)') AS resource_name,
  currency,
  ROUND(
    SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS net_cost
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_resource_v1_ABCDEF_123456_789ABC`
WHERE invoice.month = '202611'
GROUP BY project_id, service_name, resource_name, currency
ORDER BY net_cost DESC
LIMIT 50;
~~~

Chỉ dùng truy vấn này với bảng Detailed và kiểm tra schema thực tế. `resource.name` có thể NULL nếu service/SKU không xuất thông tin cấp resource. Không nên suy rằng những chi phí không có resource name là chi phí “không có chủ”.

### 7.7. Phân tích đối soát theo invoice month và cost type

~~~sql
SELECT
  invoice.month AS invoice_month,
  cost_type,
  currency,
  ROUND(SUM(cost), 2) AS gross_cost,
  ROUND(
    SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS credits_total,
  ROUND(
    SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)),
    2
  ) AS net_cost
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC`
WHERE invoice.month = '202611'
GROUP BY invoice_month, cost_type, currency
ORDER BY cost_type;
~~~

Đây là cách bắt đầu tốt khi so khớp hóa đơn, vì chưa loại bất kỳ `cost_type` nào. Nếu số vẫn khác chứng từ, tiếp tục kiểm tra phạm vi billing account, dữ liệu export đã đầy đủ chưa, thuế, adjustment, corrections, đổi tiền, quy tắc làm tròn và điều kiện hợp đồng.

**Quy tắc thực hành:** Ghi rõ mỗi bảng báo cáo sử dụng *usage month* hay *invoice month*, đồng tiền nào, đã tính credits hay chưa và có bao gồm tax/adjustment không. Thiếu một trong các thông tin đó khiến hai biểu đồ đúng riêng rẽ nhưng không thể so sánh trực tiếp.

## 8. Từ export table đến dashboard FinOps

Một pipeline báo cáo có thể gồm:

~~~mermaid
flowchart TD
  RAW["Bảng Cloud Billing export (Google quản lý)"] --> VIEW["View chuẩn hóa và kiểm soát truy cập"]
  VIEW --> DAILY["Bảng tổng hợp theo ngày / project / service"]
  DAILY --> BI["Dashboard và báo cáo định kỳ"]
  DAILY --> REVIEW["Họp đánh giá chi phí"]
  REVIEW --> ACTION["Đối chiếu metric, tối ưu cấu hình"]
~~~

### 8.1. Chuẩn hóa trường bằng BigQuery view

Bảng export gốc do Google ghi và có thể thay đổi schema khi dịch vụ mở rộng. Thay vì để mọi dashboard trực tiếp dùng `SELECT *`, một view nội bộ có thể chuẩn hóa các cột cần thiết.

Ví dụ dưới đây là **DDL tạo/sửa view**, nên chỉ chạy sau khi được cấp quyền ghi vào dataset báo cáo và đã kiểm tra đích:

~~~sql
CREATE OR REPLACE VIEW
  `FINOPS_PROJECT_ID.billing_reporting.v_cost_standard` AS
SELECT
  billing_account_id,
  invoice.month AS invoice_month,
  DATE(usage_start_time, 'UTC') AS usage_day_utc,
  project.id AS project_id,
  service.description AS service_name,
  sku.description AS sku_name,
  currency,
  cost_type,
  cost AS gross_cost,
  IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0) AS credit_amount,
  cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0) AS net_cost
FROM `FINOPS_PROJECT_ID.billing_export.gcp_billing_export_v1_ABCDEF_123456_789ABC`;
~~~

Dataset `billing_reporting` là ví dụ cần được tạo trước, ở location tương thích. Với người chỉ được xem một team, có thể dùng mô hình phân quyền dataset, authorized views hoặc chính sách hàng/cột thích hợp. **Chỉ tạo view/bảng của mình**, không chỉnh bảng gốc do Billing export đang quản lý.

### 8.2. Scheduled query cho báo cáo ngày

Một dashboard chạy liên tục có thể quét toàn bộ lịch sử và phát sinh chi phí BigQuery không cần thiết. Có thể dùng bảng tổng hợp định kỳ, nhưng cần thiết kế:

- **Độ trễ hợp lý:** ví dụ báo cáo ngày hôm qua; không gắn nhãn “thời gian thực”.
- **Cửa sổ cập nhật:** vì usage đến trễ và adjustment có thể được bổ sung sau, cần tính lại một khoảng dữ liệu phù hợp thay vì chỉ cộng dòng mới nhất.
- **Nguồn sự thật:** một bảng usage export và một định nghĩa net cost rõ ràng cho mỗi báo cáo.
- **Chất lượng dữ liệu:** kiểm tra ngày export mới nhất, dòng NULL project/team, currency, cost type.
- **Chi phí xử lý:** cân nhắc refresh ít lần hơn, dùng dry run hoặc bytes processed, lưu bảng tổng hợp cho nhiều dashboard.

### 8.3. Kết hợp Cloud Billing budgets

Cloud Billing Budgets và cảnh báo hữu ích khi cần biết ngưỡng chi tiêu theo project, dịch vụ hoặc phạm vi được hỗ trợ. BigQuery export dùng để **giải thích nguyên nhân**: service/SKU nào tăng, tăng ở project/team nào, đã được credits giảm bao nhiêu. Nếu muốn gửi thông báo từ kết quả SQL, cần thêm workflow có lịch chạy và quyền gửi thông báo. Không giả định chỉ bật export là đã có cảnh báo vượt ngưỡng.

## 9. Giới hạn và bảo vệ dữ liệu export

### 9.1. Luồng export có độ trễ và có thể có điều chỉnh

Mỗi dịch vụ gửi usage đến Billing theo nhịp riêng; export tải các bản ghi theo chu kỳ, không có thời hạn giao nhận cố định. Những khoản phí cuối kỳ, corrections và adjustments có thể xuất hiện sau thời điểm sử dụng. Khi xây báo cáo ngày/tháng, nên công bố **mốc dữ liệu cập nhật** và lập thời gian đối soát sau khi hóa đơn hoàn chỉnh.

### 9.2. Không sửa bảng do Google quản lý

Google tạo và quản lý schema/bảng export. Những hành động cần tránh:

- Đổi cột, tự tạo lại bảng export với schema khác.
- `INSERT`/`MERGE` dữ liệu của mình vào bảng export, kể cả để “bù” một kỳ thiếu.
- Xóa bảng/row rồi giả định Google sẽ tự backfill lại.
- Tắt export hoặc đổi đích mà chưa đánh giá khoảng dữ liệu bị gián đoạn.

Nếu cần gộp lịch sử từ dataset cũ và mới, **giữ nguyên bảng nguồn** rồi tạo một view/bảng báo cáo riêng với `UNION ALL`, bộ lọc thời gian loại phần chồng lấn và kiểm tra trùng dữ liệu.

### 9.3. Giữ quyền của service account xuất dữ liệu

Cloud Billing tự thêm service account do Google quản lý để ghi vào dataset. Tùy loại export, các principal hiện được tài liệu mô tả gồm:

~~~text
billing-export-bigquery@system.gserviceaccount.com
cloud-account-pricing@cloud-account-pricing.iam.gserviceaccount.com
~~~

Loại bỏ các principal này khỏi dataset có thể khiến export ngừng cập nhật, dẫn tới mất dữ liệu. CUD metadata dùng quy trình linked dataset riêng, không áp dụng đồng nhất mọi service account như Standard/Pricing.

### 9.4. Bảo mật dữ liệu tài chính

Bảng export có thể chứa tên project, label, tên resource, SKU và thông tin giá, credit liên quan hợp đồng. Hãy:

1. Cấp quyền đọc bảng gốc theo nhu cầu thực tế.
2. Tạo view/báo cáo được lọc cho từng nhóm ứng dụng khi cần.
3. Kiểm soát quyền tạo query job và chi phí BigQuery.
4. Không sao chép billing export lên repository công khai hoặc gửi qua kênh không phù hợp.
5. Định nghĩa retention, audit access và nơi lưu dữ liệu theo chính sách công ty.
6. Kiểm tra IAM khi nhân sự đổi nhóm hoặc ứng dụng đổi billing account.

### 9.5. FOCUS và quản lý lưu trữ dài hạn

FOCUS là một lựa chọn phục vụ chuẩn hóa FinOps và có schema/vòng đời riêng. Nếu doanh nghiệp cần báo cáo lịch sử trên hai năm, cần lưu ý **TTL hai năm của bảng FOCUS do Google cung cấp** theo tài liệu hiện tại và chuẩn bị bản sao dài hạn trong bảng do tổ chức sở hữu nếu được phép. Bảng Standard/Detailed có các hạn chế và chính sách khác; đọc từng loại thay vì áp một quy tắc TTL chung cho tất cả.

## 10. Khắc phục sự cố thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không bật được export | Thiếu quyền với Billing account hoặc BigQuery project | Kiểm tra IAM theo đúng **loại export** và tài khoản đang dùng |
| `Invalid dataset region` | Location không được Cloud Billing export hỗ trợ | Chọn dataset khác có location hợp lệ |
| Không thấy dataset khi thiết lập | Sai project, quyền hoặc quan hệ billing account | Kiểm tra Billing Account ID, project và IAM |
| Không thấy bảng ngay sau khi Save | Luồng export đang khởi tạo | Đọc trạng thái export, chờ theo tài liệu; tránh bật/tắt lặp lại |
| Có bảng nhưng thiếu ngày gần nhất | Dữ liệu usage đến trễ hoặc đang backfill | Xem `MAX(export_time)`, `MAX(usage_start_time)` và lịch cập nhật |
| Không thấy chi phí trước ngày bật | Dùng dataset region, vừa đổi đích hoặc từng tắt export | Kiểm tra chính sách hồi tố theo location và lịch sử thiết lập |
| Pricing export chưa có dữ liệu | Chưa bật BigQuery Data Transfer Service API hoặc chưa đủ quyền | Kiểm tra API/IAM và khoảng khởi tạo tới 48 giờ |
| Dữ liệu ngừng cập nhật sau khi chỉnh IAM | Service account ghi export không còn quyền | Kiểm tra dataset access và trạng thái Billing export |
| SQL báo `Access Denied` | Thiếu quyền đọc bảng hoặc chạy query job | Kiểm tra IAM dataset và query project |
| Tổng chi phí gấp đôi | Kết hợp Standard + Detailed hoặc JOIN credits gây nhân dòng | Chỉ dùng một bảng usage; tổng credit bằng scalar subquery |
| Invoice total khác report theo usage | Khác thời gian, currency, tax, adjustment hoặc dữ liệu trễ | So sánh `invoice.month` và `cost_type`, kiểm tra kỳ hóa đơn |
| Query có chi phí cao | Quét nhiều dữ liệu hoặc dashboard refresh liên tục | Giới hạn thời gian, xem bytes processed và tạo bảng tổng hợp |

Luồng chẩn đoán:

~~~text
Đúng Billing Account ID?
  ↓
Đúng export type, project, dataset và location?
  ↓
Đủ IAM, BigQuery API và API bổ sung?
  ↓
Bảng đã được tạo, có dữ liệu và cập nhật đến đâu?
  ↓
Query có đúng schema, thời gian, currency và cost type?
  ↓
Đã xử lý credits mà không nhân dòng?
  ↓
Đã đối chiếu dữ liệu với Billing Console/hóa đơn?
~~~

Nếu thiếu dữ liệu, **không tự động tắt rồi bật lại export như bước đầu tiên**: thao tác đó có thể làm thiếu thêm một giai đoạn dữ liệu. Trước khi đổi đích, xác định cách lưu lịch sử và hợp nhất những bảng cũ/mới ở tầng báo cáo riêng.

## 11. Tình huống thực tế: kiểm soát chi phí hệ thống đặt hàng

Một nhóm phát triển quản lý ba project cùng Billing account:

- `orders-dev`: thử nghiệm API Cloud Run và Cloud Storage.
- `orders-prod`: ứng dụng production với Cloud Run, Cloud SQL, Pub/Sub, load balancing.
- `analytics-prod`: pipeline dữ liệu và BigQuery.

Nhóm cần biết chi phí của development/production, dịch vụ/SKU nào đang tăng và có nên tối ưu cấu hình. Có thể xây quy trình sau:

1. Chọn `finops-admin` làm export project và cấp quyền phân tích thích hợp.
2. Bật **Standard usage cost export** để có dữ liệu theo project, service, SKU, invoice month và credits.
3. Chạy báo cáo theo `invoice.month` cho kế toán; chạy báo cáo theo `usage_start_time` cho xu hướng vận hành.
4. Chuẩn hóa label `team` và `env`, ghi nhận phần chi phí không có chủ.
5. Xác định top SKU tăng chi phí, kiểm tra kỹ `cost_type`, currency và độ trễ dữ liệu.
6. Kết hợp với Cloud Monitoring, log và lịch phát hành để kiểm chứng nguyên nhân.
7. Bật Detailed khi cần điều tra resource được hỗ trợ; dùng GKE cost allocation nếu bài toán đòi chi tiết GKE.
8. Theo dõi ngân sách và đánh giá lợi ích sau mỗi thay đổi kỹ thuật.

Một số giả thuyết điều tra:

| Tín hiệu chi phí | Giả thuyết cần kiểm chứng | Nguồn dữ liệu bổ sung |
| --- | --- | --- |
| Cloud Run tăng đột biến | Request tăng, min instances, concurrency hoặc CPU/memory không hợp lý | Cloud Run metrics, traffic, revision config |
| Cloud SQL tăng | Instance tier/HA, storage, backup hoặc network | Cloud SQL metrics, cấu hình instance và backup |
| Network egress tăng | Lưu lượng Internet hoặc kết nối xuyên region | SKU mạng, VPC, đường đi dữ liệu |
| GKE chi phí chưa phân bổ | Chưa bật cost allocation hoặc thiếu nhãn | Detailed export, GKE allocation và labels |
| BigQuery FinOps tăng | Query dashboard quét nhiều dữ liệu | BigQuery job history, bytes processed |

Từ bảng Billing chỉ có thể nhận diện **chi phí tăng ở đâu**, chưa thể kết luận nguyên nhân kỹ thuật. Cần đối chiếu metric, thay đổi kiến trúc và lịch phát hành.

### 11.1. Ghi lại quyết định tối ưu

~~~text
Vấn đề: Chi phí Cloud Run của orders-prod tăng qua hai tuần
Bằng chứng: Query usage ngày, service, SKU, credits và currency
Giả thuyết: Tải tăng hoặc cấu hình instance/revision thay đổi
Kiểm chứng thêm: Request count, p95 latency, min instances, logs
Phương án: Điều chỉnh concurrency hoặc resource sizing sau thử nghiệm
Rủi ro: Hiệu năng/độ tin cậy suy giảm nếu giảm tài nguyên quá mức
Đánh giá: Cost/request và SLO sau khi thay đổi
Owner: Nhóm API; ngày review tiếp theo: ...
~~~

Giảm chi phí phải được đánh giá cùng tính sẵn sàng, độ trễ, khả năng phục hồi và bảo mật. Đừng chọn giải pháp chỉ vì tổng hóa đơn thấp hơn.

## 12. Bài thực hành: xuất Standard usage cost và lập báo cáo

**Mục tiêu:** Thiết lập Standard export, xác minh dữ liệu và tạo báo cáo chi phí theo project, dịch vụ, hóa đơn.

**Điều kiện:** Có quyền IAM với billing account và export project, dataset ở location phù hợp, ngân sách BigQuery được phê duyệt. Người không có quyền cấu hình vẫn có thể làm phần SQL trên dataset demo được cấp quyền đọc.

### Phần A — Thiết lập

1. Ghi Billing Account ID, export Project ID, Dataset ID, location, ngày bật.
2. Chọn Standard export và giải thích vì sao chưa cần Detailed.
3. Kiểm tra project được liên kết với đúng Billing account, quyền IAM và BigQuery API.
4. Trong Billing Console → Billing export → BigQuery export, bật và lưu Standard.
5. Sau khi bảng được tạo, lấy chính xác table ID trong BigQuery Explorer.
6. Chạy truy vấn xác minh số dòng, usage sớm nhất/mới nhất và export time.

### Phần B — Phân tích SQL

Dùng các truy vấn mục 7, thay table ID và tháng theo dữ liệu thực:

- **Theo project:** Gross, credits và net cost trong cùng invoice month.
- **Theo service/SKU:** Top chi phí usage và điều kiện `cost_type`.
- **Theo ngày:** Xu hướng chi phí theo ngày sử dụng, có timezone được công bố.

Viết giải thích về khả năng chênh lệch giữa các tổng: phạm vi khác nhau, invoice vs usage time, tax/adjustment, credits, dữ liệu tới trễ, currency hoặc thiếu phân bổ.

### Phần C — Báo cáo chất lượng

| Câu hỏi | Bằng chứng cần lưu |
| --- | --- |
| Dữ liệu bắt đầu ngày nào? | Ngày bật, location và thời điểm usage sớm nhất |
| Export gần nhất khi nào? | `MAX(export_time)` và thời điểm kiểm tra |
| Project nào chưa có team label? | Danh sách/chi phí của nhóm thiếu nhãn |
| SQL tính credits đúng không? | Công thức scalar subquery, không nhân dòng |
| Có gồm tax và adjustments? | Danh sách `cost_type` được lọc/giữ |
| Báo cáo dùng invoice hay usage time? | Tên trường, kỳ và timezone |
| Ai được xem báo cáo? | Scope IAM và yêu cầu bảo mật |
| BigQuery có vượt chi phí dự kiến? | Số bytes quét, tần suất refresh và budget |

### Phần D — Câu hỏi tình huống

Giả sử `orders-prod` tăng phí, trong khi top SKU cho thấy network egress tăng. Đưa ra ít nhất **hai giả thuyết**, **ba dữ liệu cần thu thập để xác nhận** và **một phép đo sau tối ưu**. Không suy nguyên nhân từ giá trị tiền đơn lẻ.

## 13. Câu hỏi tự kiểm tra

1. Standard/Detailed export ghi dữ liệu của project chứa dataset hay của các project thuộc Billing account?
2. Khi nào cần Detailed thay vì Standard?
3. Tại sao cộng tổng cả Standard và Detailed có thể sai?
4. Bật export lần đầu vào US/EU multi-region khác supported region ở dữ liệu hồi tố thế nào?
5. Vì sao Pricing export cần BigQuery Data Transfer Service API?
6. `invoice.month` có thể khác tháng `usage_start_time` bởi nguyên nhân nào?
7. Vì sao JOIN trực tiếp `UNNEST(credits)` có thể làm sai `SUM(cost)`?
8. Tại sao cần giữ `cost_type` và `currency` trong đối soát?
9. Chuyển đích dataset ảnh hưởng thế nào đến lịch sử dữ liệu?
10. Vì sao không nên cho mọi nhóm xem bảng export gốc của toàn công ty?

**Gợi ý:** (1) theo Billing account; (2) khi cần dữ liệu cấp resource được hỗ trợ; (3) trùng usage; (4) multi-region có thể backfill từ đầu tháng trước khi bật mới, supported region chỉ từ ngày bật; (5) điều kiện riêng Pricing; (6) usage báo cáo trễ, corrections/điều chỉnh; (7) nhân dòng hoặc mất dòng không credit; (8) tránh trộn đồng tiền, thuế và regular usage; (9) không tự backfill lịch sử sang đích mới; (10) dữ liệu tài chính có phạm vi rộng và cần kiểm soát truy cập.

## 14. Checklist trước khi dùng báo cáo để quyết định

- [ ] Đã xác minh Billing Account ID, export project, dataset và loại export.
- [ ] IAM, BigQuery API và API riêng cho Pricing đã được kiểm tra.
- [ ] Location phù hợp chính sách dữ liệu và hiểu giới hạn backfill.
- [ ] Bảng có dữ liệu và biết độ mới/độ trễ.
- [ ] Dùng một bảng usage làm nguồn tính tổng để tránh nhân đôi.
- [ ] SQL tính credits an toàn trên từng dòng.
- [ ] Dashboard ghi rõ invoice month hay usage time, timezone và currency.
- [ ] Công khai điều kiện `cost_type` và xử lý adjustments.
- [ ] Đã xử lý project/team NULL và chi phí chưa phân bổ.
- [ ] Giữ nguyên bảng do Google quản lý; báo cáo nằm ở view/bảng riêng.
- [ ] Có quy trình IAM, retention, audit và đối chiếu hóa đơn.
- [ ] Có budget theo dõi chi phí BigQuery và hiệu quả tối ưu.

## 15. Tài liệu chính thức

Các trang sau được Google Cloud cập nhật theo sản phẩm, schema và khả năng hỗ trợ; kiểm tra phiên bản hiện hành trước khi triển khai production:

- [Export Cloud Billing data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery) — tổng quan và các loại export.
- [Set up Cloud Billing data export to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup) — IAM, API, dataset, location, backfill.
- [Understand Cloud Billing data tables](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables) — bảng tự tạo, lịch xuất và giới hạn.
- [Standard usage cost schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage) — các trường, invoice, credits, tax/adjustments.
- [Detailed usage cost schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage) — thông tin cấp resource.
- [Example queries for Billing export](https://docs.cloud.google.com/billing/docs/how-to/bq-examples) — truy vấn SQL mẫu.
- [Cloud Billing budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets) — ngân sách và thông báo.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) — chi phí truy vấn/lưu trữ.
- [GKE cost allocation](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cost-allocations) — mở rộng phân tích GKE.

**Điểm cần nhớ:** Một báo cáo FinOps đáng tin cậy đi từ **bật đúng export → hiểu schema, độ trễ và location → tính cost/credits chính xác → phân bổ theo project/team → kiểm chứng và tối ưu**. Mục tiêu là đưa chi phí vào quyết định kiến trúc cùng với bảo mật, độ tin cậy và hiệu năng.
