# Thực hành kho dữ liệu và dashboard phân tích chi phí

> **Chương:** BigQuery  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một nhóm vận hành quản lý nhiều Google Cloud projects: API chạy trên Cloud Run, dịch vụ phân tích dùng BigQuery, dữ liệu lưu ở Cloud Storage, một số hệ thống chạy GKE. Báo cáo chi phí trên Cloud Billing cho biết tổng chi phí và xu hướng, nhưng nhóm cần trả lời sâu hơn: **dịch vụ nào tăng phí trong tuần, project nào vượt ngân sách, chi phí sau credits là bao nhiêu, nhãn `cost_center` nào chưa được gán?** Bài này xây một đường phân tích chi phí theo hướng **Cloud Billing export → BigQuery → SQL views → dashboard trong Looker Studio (Data Studio)**.

Đây là bài thực hành thuộc mô-đun **CLOUD_PROVIDERS_GCP**, nối kiến thức tổ chức project/IAM, VPC, Compute Engine, GKE, Cloud Run và cơ sở dữ liệu với vận hành độ tin cậy và kiểm soát chi phí. Mục tiêu là **hiểu số liệu và có dashboard có thể đối soát**, không phải chỉ tạo biểu đồ đẹp. Các tên project, dataset, billing account và số tiền trong ví dụ đều **giả định**.

**Sau bài học, bạn có thể:**

1. Chọn đúng loại Cloud Billing export: **Standard**, **Detailed**, **Pricing**, **CUD metadata** và biết khi nào cần dữ liệu resource-level.
2. Tạo dataset theo khu vực hỗ trợ, bật export với IAM và ngân sách phù hợp.
3. Đọc các field `cost`, `credits`, `invoice.month`, `usage_start_time`, `cost_type`, `project`, `service`, `sku`, `labels` và `export_time`.
4. Viết BigQuery SQL **không nhân đôi chi phí** khi xử lý repeated credits/labels.
5. Tạo view chuẩn hóa dữ liệu và daily-cost mart để dashboard dùng lại.
6. Thiết kế KPI theo project/service/ngày, dashboard filters và bảng unallocated cost.
7. Tách **chi phí sử dụng** khỏi **tổng tiền hóa đơn**; đối soát thuế, adjustments, credits và dữ liệu đến muộn.
8. Giảm chi phí chính hệ thống báo cáo bằng dry run, maximum bytes billed, partition/cluster và giới hạn refresh.
9. Phân quyền người xem an toàn, kiểm thử một lab bằng dữ liệu giả khi không có quyền xem hóa đơn thật.

## 1. Kiến trúc mục tiêu

~~~mermaid
flowchart LR
  CLOUD["Các Google Cloud services\nusage + charges"] --> BILL["Cloud Billing account"]
  BILL -->|"Managed export"| RAW["BigQuery dataset\nbilling_raw\nStandard/Detailed"]
  RAW -->|"SQL, kiểm tra schema"| VIEW["billing_mart\nv_cost_lines"]
  VIEW --> DAILY["v_daily_cost\nv_invoice_cost"]
  DAILY --> BI["Looker Studio / Data Studio\nDashboard chi phí"]
  DAILY --> ALERT["Scheduled check / report\nngưỡng và bất thường"]
  RAW --> QA["Reconciliation\nCloud Billing Reports/Invoice"]
~~~

**Ba lớp cần tách:**

| Lớp | Sở hữu | Chức năng | Quy tắc |
| --- | --- | --- | --- |
| **Raw export** | Cloud Billing quản lý việc ghi | Bản ghi chi phí/credits gốc, có thể cập nhật đến trễ | Không tự chỉnh/xóa rows; không dùng làm dashboard truy cập rộng |
| **Semantic/mart** | Nhóm phân tích/FinOps | Chuẩn hóa metrics/dimensions, chi phí thực sau credits | Có SQL versioning, kiểm thử và ghi rõ định nghĩa KPI |
| **Presentation** | Nhóm BI | Biểu đồ, filters, bảng, lịch refresh | Chỉ đọc bảng/view đã được cấp phép |

**Không lấy BigQuery làm cơ chế chặn chi phí:** dashboard là công cụ quan sát và quyết định. **Cloud Billing Budgets**, quotas, policies và phương án tắt/tăng giảm tài nguyên mới hỗ trợ phản ứng với overspend. Budget alerts không phải hard spending cap.

## 2. Chọn đúng dữ liệu xuất từ Cloud Billing

| Loại export | Bảng/dataset thường gặp | Khi nên dùng |
| --- | --- | --- |
| **Standard usage cost** | `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>` | Dashboard xu hướng theo ngày, project, service/SKU và credits |
| **Detailed usage cost** | `gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>` | Điều tra chi phí theo **resource**; bảng có thể lớn hơn |
| **Pricing** | `cloud_pricing_export` | Tra bảng giá theo SKUs/account, phân tích giả thuyết tăng giá |
| **CUD metadata** | Bảng metadata do export tạo | Phân tích phân bổ/hiệu quả committed use discounts |
| **FOCUS usage** | Export FOCUS theo cơ chế/dataset được Google cung cấp | Chuẩn hóa FinOps đa nhà cung cấp; kiểm tra availability/schema riêng |

Ví dụ trong bài sử dụng **Standard usage export** vì nó đủ cho dashboard tổng quan và thường giảm chi phí truy vấn so với Detailed. Nếu cần bảng “Top 20 Compute Engine instances đắt nhất”, phải bật **Detailed**; Standard **không có** đầy đủ resource-level identifiers. Không cộng Standard và Detailed lại: cả hai có thể phản ánh cùng usage, gây **double count**.

### 2.1. Một bảng export không phải một hóa đơn tĩnh

- Dữ liệu được xuất **định kỳ**, không có cam kết latency như một hệ thống streaming real-time.
- Các dịch vụ báo usage ở tần suất khác nhau; vài giờ đầu có thể chưa đủ dữ liệu.
- Một số dòng điều chỉnh, tax/rounding hoặc committed-use credits có thể đến muộn.
- `export_time` cho biết thời điểm xuất bản ghi; **không** đồng nghĩa thời gian dịch vụ được sử dụng.
- Schema có thể thêm fields theo thời gian; nên đặt **view** làm hợp đồng ổn định cho dashboard.

### 2.2. Lựa chọn location ảnh hưởng backfill

Theo tài liệu Cloud Billing export, với Standard/Detailed/FOCUS:

- Dataset ở **US/EU multi-region** có thể nhận dữ liệu **hồi tố tháng hiện tại và tháng trước** khi bật lần đầu; quá trình backfill có thể mất vài ngày.
- Dataset ở **supported single region** chỉ có dữ liệu kể từ ngày bật export trở đi, **không hồi tố** cho trước đó.
- Export chỉ hỗ trợ một tập regions nhất định; **không tạo dataset ở một region bất kỳ rồi giả định export sẽ nhận**.
- Pricing export không có backfill như usage export.

Chọn region theo chính sách data residency và yêu cầu lịch sử, **trước** khi bật. Đổi dataset export về sau không tự mang dữ liệu cũ sang dataset mới.

## 3. Chuẩn bị project, IAM, dataset và nguồn xuất

### 3.1. Mô hình lab

| Thông tin | Giá trị minh họa |
| --- | --- |
| Cloud Billing account | `XXXXXX-XXXXXX-XXXXXX` |
| Project chứa BigQuery | `LAB_BILLING_PROJECT` |
| Dataset raw | `billing_raw` |
| Dataset mart | `billing_mart` |
| Location | `US` (chỉ ví dụ, cần duyệt data residency) |
| Standard table | `gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX` |
| View chuẩn hóa | `billing_mart.v_cost_lines` |
| View daily | `billing_mart.v_daily_cost` |
| View invoice | `billing_mart.v_invoice_cost` |
| Dashboard | `Cloud Cost Overview – Lab` |

**Lưu ý bảo mật:** Dữ liệu chi phí có thể tiết lộ cấu trúc dự án, tài nguyên và chiến lược vận hành. Chỉ dùng **project/billing account lab** được ủy quyền. Nếu không có quyền Cloud Billing, sử dụng dữ liệu giả ở mục 11, **không yêu cầu quyền billing admin chỉ để làm bài**.

### 3.2. Điều kiện quyền

- Bật export **usage cost** thường cần **Billing Account Costs Manager hoặc Billing Account Administrator** trên billing account, kèm **BigQuery User** trên project chứa dataset.
- Bật **pricing/CUD metadata** cần quyền cao hơn; theo tài liệu gồm Billing Account Administrator, BigQuery Admin và quyền cập nhật project tương ứng.
- Để tạo dataset/table/view, người thực hiện cần IAM BigQuery thích hợp; để chạy SQL cần `bigquery.jobs.create` và quyền đọc các tables/views liên quan.
- Dịch vụ Cloud Billing thêm **export service account** vào dataset để ghi dữ liệu. **Không xóa/revoke** quyền đó khi gia cố IAM.
- Người xem dashboard chỉ cần quyền để đọc **mart** và chạy query theo phương thức credential của Data Studio; không mặc nhiên được quyền đọc raw billing.

Không cấp `roles/owner` hoặc `roles/editor` rộng nếu chỉ thiếu quyền xem dashboard. Với raw billing, dùng project/dataset riêng, authorized views hoặc bảng aggregate đã lọc để hạn chế dữ liệu được chia sẻ.

### 3.3. Thao tác tạo dataset trong project lab

**Lệnh chỉ đọc trước khi thay đổi:**

~~~bash
gcloud config get-value project
gcloud billing accounts list
bq ls --project_id=LAB_BILLING_PROJECT
~~~

Các lệnh dưới đây **tạo dataset và có thể phát sinh phí**; chỉ chạy trong project lab đã được duyệt. Dataset `US` chỉ là ví dụ; đổi sang location được Cloud Billing export hỗ trợ và được chính sách cho phép:

~~~bash
bq --location=US mk --dataset LAB_BILLING_PROJECT:billing_raw
bq --location=US mk --dataset LAB_BILLING_PROJECT:billing_mart

bq show --format=prettyjson LAB_BILLING_PROJECT:billing_raw
bq show --format=prettyjson LAB_BILLING_PROJECT:billing_mart
~~~

**Không tạo table Standard export thủ công.** Sau khi bật Cloud Billing export, dịch vụ tự tạo bảng `gcp_billing_export_v1_...` trong dataset được chỉ định.

### 3.4. Bật export qua Google Cloud Console

1. Vào **Billing → Billing export → BigQuery export** và chọn đúng billing account.
2. Chọn **Enable standard usage cost export**.
3. Chọn project `LAB_BILLING_PROJECT` và dataset `billing_raw`, sau đó xác nhận.
4. Nếu cần phân tích resource-level, bật **Detailed usage cost export** riêng, tránh tưởng Standard có đủ chi tiết.
5. Xem tab BigQuery để xác minh bảng xuất hiện; kiểm tra ngày đầu tiên có dữ liệu và khoảng thời gian backfill.
6. Kiểm tra Billing export configuration, BigQuery IAM và Billing Budgets; ghi lại ai sở hữu dashboard.

**Chờ dữ liệu thực tế xuất hiện** trước khi kiểm tra số liệu; không tự tạo tên bảng bất kỳ rồi coi đó là dữ liệu hóa đơn. Một billing account có thể thanh toán **nhiều projects**; export không chỉ chứa chi phí của project lưu BigQuery.

## 4. Hiểu schema trước khi viết SQL

Một số fields của **Standard usage cost export**:

| Field | Kiểu/ý nghĩa | Cảnh báo |
| --- | --- | --- |
| `billing_account_id` | Billing account xuất usage | Phạm vi có thể nhiều projects |
| `invoice.month` | Tháng hóa đơn, dạng `YYYYMM` | **Có thể khác tháng usage** |
| `usage_start_time` | Thời điểm bắt đầu cửa sổ usage (TIMESTAMP) | Không phải lúc hàng được export |
| `export_time` | Thời điểm hệ thống Billing xuất dữ liệu | Dùng phát hiện freshness |
| `project.id`, `project.name` | Project chịu chi phí | Có thể `NULL` với dòng không gắn project |
| `service.id/description` | Dịch vụ, ví dụ BigQuery | Group ổn định bằng ID khi cần |
| `sku.id/description` | Loại usage cụ thể | Một service có nhiều SKUs |
| `cost` | Chi phí dòng, **chưa cộng credits** | Không phải số cuối cùng phải trả |
| `credits` | **ARRAY** các credits với `amount`, type... | Có thể rỗng hoặc nhiều phần tử |
| `cost_type` | `regular`, `tax`, `adjustment`, `rounding_error` | Không trộn hết vào usage trend nếu không giải thích |
| `currency` | Đơn vị tiền tệ của billing account | **Không cộng USD với VND** |
| `labels`, `project.labels`, `tags` | Metadata phân bổ chi phí | Có thể thiếu, trễ hoặc nhiều nhãn |

**Quy tắc tính tiền:**

\[
\text{Net cost} = \sum \text{cost} + \sum \text{credits.amount}
\]

Trong export thông dụng, `credits.amount` thường là số âm, nên **cộng** credits thay vì trừ nó lần nữa. Ví dụ `cost = 120`, `credits = [-20,-10]` thì net = 90 (cùng currency).

### 4.1. Ba “ngày/tháng” khác nhau

| Mốc thời gian | Ví dụ | Trả lời câu hỏi |
| --- | --- | --- |
| `DATE(usage_start_time)` | 2026-11-01 | Dùng tài nguyên vào ngày nào? |
| `invoice.month` | `202611` hoặc `202612` | Dòng được ghi trên hóa đơn tháng nào? |
| `export_time` | 2026-11-04 08:10 UTC | Dòng được cập nhật/xuất lúc nào? |

Một khoản dùng cuối tháng 11 có thể lên hóa đơn tháng 12; không so tổng chi phí của **usage November** với **invoice November** rồi khẳng định “sai hóa đơn”. Cũng cần thống nhất **múi giờ**: ngày usage lấy theo UTC hay `Asia/Ho_Chi_Minh` có thể khác tại ranh giới ngày.

### 4.2. Cẩn thận với nested arrays

Ví dụ **một dòng** có `cost=100` và hai credits `-10`, `-5`. Query dưới đây là **sai**:

~~~sql
-- SAI: UNNEST có thể nhân bản hàng gốc.
SELECT SUM(cost)
FROM `LAB_BILLING_PROJECT.billing_raw.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`,
UNNEST(credits) AS c;
~~~

Khi UNNEST thành hai hàng, SUM(cost) sẽ thành 200 thay vì 100; các dòng không có credits còn có thể bị loại. **Cách đúng:** tính tổng credits **trong từng row bằng scalar subquery**, sau đó tổng hợp.

## 5. Tạo view chuẩn hóa: một dòng nguồn → một dòng phân tích

Tạo view `billing_mart.v_cost_lines` từ **Standard**. Thay tên billing export table bằng bảng thật có trong Explorer; không chạy SQL này nếu chưa được phép đọc dữ liệu billing.

~~~sql
-- BigQuery GoogleSQL; tạo view trong cùng location với nguồn.
CREATE OR REPLACE VIEW
  `LAB_BILLING_PROJECT.billing_mart.v_cost_lines` AS
SELECT
  billing_account_id,
  DATE(usage_start_time, "Asia/Ho_Chi_Minh") AS usage_date,
  invoice.month AS invoice_month,
  usage_start_time,
  export_time,
  currency,
  COALESCE(project.id, "UNATTRIBUTED") AS project_id,
  COALESCE(project.name, "Unknown project") AS project_name,
  service.id AS service_id,
  service.description AS service_name,
  sku.id AS sku_id,
  sku.description AS sku_name,
  cost_type,
  CAST(cost AS NUMERIC) AS gross_cost,
  COALESCE(
    (SELECT SUM(CAST(c.amount AS NUMERIC))
     FROM UNNEST(credits) AS c), 0
  ) AS credit_amount,
  CAST(cost AS NUMERIC) + COALESCE(
    (SELECT SUM(CAST(c.amount AS NUMERIC))
     FROM UNNEST(credits) AS c), 0
  ) AS net_cost,
  COALESCE(
    (SELECT l.value FROM UNNEST(labels) AS l
     WHERE l.key = "cost_center" LIMIT 1),
    (SELECT p.value FROM UNNEST(project.labels) AS p
     WHERE p.key = "cost_center" LIMIT 1),
    "unallocated"
  ) AS cost_center
FROM
  `LAB_BILLING_PROJECT.billing_raw.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`;
~~~

**Tại sao dùng view?** Cô lập biểu thức tính net cost, đổi tên cột và quy tắc fallback labels để mọi KPI dùng chung định nghĩa. Khi export thêm/sửa fields, cập nhật một view thay vì sửa 10 biểu đồ. View **không tự lưu cache hoặc làm truy vấn rẻ hơn**: mỗi truy vấn qua view có thể quét dữ liệu nguồn.

**Hai lưu ý quan trọng:**

- `cost_center` ở đây ưu tiên **resource label**, rồi **project label**; thiếu cả hai thì `unallocated`. Nếu labels cùng tên nhưng khác ý nghĩa ở các nhóm tài nguyên, phải chuẩn hóa taxonomy trước.
- Nhãn có thể được gắn sau khi usage xảy ra hoặc không được sản phẩm hỗ trợ xuất; **unallocated không tự có nghĩa đội đó chi tiêu sai**. Với invoice tax/adjustment, project/cost center có thể rỗng; allocation nội bộ cần quy tắc khác.

### 5.1. View tổng hợp theo ngày cho dashboard vận hành

~~~sql
CREATE OR REPLACE VIEW
  `LAB_BILLING_PROJECT.billing_mart.v_daily_cost` AS
SELECT
  usage_date,
  currency,
  project_id,
  project_name,
  service_id,
  service_name,
  cost_center,
  SUM(gross_cost) AS gross_cost,
  SUM(credit_amount) AS credits,
  SUM(net_cost) AS net_cost
FROM `LAB_BILLING_PROJECT.billing_mart.v_cost_lines`
WHERE cost_type = "regular"
GROUP BY 1, 2, 3, 4, 5, 6, 7;
~~~

Bản `v_daily_cost` phục vụ **chi phí sử dụng thường kỳ** (exclude tax, adjustments và rounding) để dashboard vận hành dễ giải thích. Nó **không phải số hóa đơn phải trả**. Nếu một organization có nhiều currencies, **luôn group theo `currency`** và dùng separate scorecards/currency filters, hoặc chuyển đổi với tỷ giá/chính sách được duyệt.

### 5.2. View tổng hóa đơn cho đối soát

~~~sql
CREATE OR REPLACE VIEW
  `LAB_BILLING_PROJECT.billing_mart.v_invoice_cost` AS
SELECT
  invoice_month,
  currency,
  cost_type,
  SUM(gross_cost) AS gross_cost,
  SUM(credit_amount) AS credits,
  SUM(net_cost) AS net_cost
FROM `LAB_BILLING_PROJECT.billing_mart.v_cost_lines`
GROUP BY 1, 2, 3;
~~~

**Mục đích:** giữ riêng `regular/tax/adjustment/rounding_error` để đối soát hóa đơn. Khi cần chính xác đến đơn vị siêu nhỏ (*micros*), tham khảo mẫu của Google dùng chuyển `cost/credits` thành micro-units trước khi tổng hợp, tránh sai khác dấu phẩy động; đối soát cuối cùng còn phải kiểm tra quy tắc invoice và credit types.

### 5.3. Kiểm thử một vài hàng, không đếm mù

~~~sql
-- Kiểm tra bảng/view đã đọc được và các trường quan trọng
SELECT
  usage_date, invoice_month, project_id, service_name,
  currency, gross_cost, credit_amount, net_cost
FROM `LAB_BILLING_PROJECT.billing_mart.v_cost_lines`
WHERE usage_date >= DATE "2026-11-01"
  AND usage_date < DATE "2026-12-01"
LIMIT 20;
~~~

Trong một table **không phân vùng**, `LIMIT 20` thường **không giảm bytes scanned**. Trước khi chạy trên billing export lớn, mở **Preview** miễn phí, chạy dry run và dùng maximum bytes billed. Phần tối ưu hóa ở mục 9.

## 6. Truy vấn KPI thực tế

### 6.1. Top project/service trong tháng sử dụng

~~~sql
SELECT
  currency, project_id, service_name,
  ROUND(SUM(net_cost), 2) AS net_cost
FROM `LAB_BILLING_PROJECT.billing_mart.v_daily_cost`
WHERE usage_date >= DATE "2026-11-01"
  AND usage_date < DATE "2026-12-01"
GROUP BY 1, 2, 3
ORDER BY net_cost DESC
LIMIT 15;
~~~

**Không cộng số tiền khác currency.** Nếu `project_id = UNATTRIBUTED`, đừng mặc nhiên gán chi phí cho project lưu export; nó có thể là dòng không gắn project.

### 6.2. Xu hướng chi phí 7 ngày theo service

~~~sql
SELECT
  usage_date, currency, service_name,
  ROUND(SUM(net_cost), 2) AS daily_net_cost
FROM `LAB_BILLING_PROJECT.billing_mart.v_daily_cost`
WHERE usage_date BETWEEN DATE "2026-11-12" AND DATE "2026-11-18"
GROUP BY 1, 2, 3
ORDER BY usage_date, service_name;
~~~

So sánh với 7 ngày trước khi điều tra tăng trưởng. Nếu chỉ nhìn số tiền tuyệt đối, tải thật tăng cũng làm chi phí tăng; muốn biết **hiệu quả**, cần kết hợp metric như requests, GB xử lý hoặc số đơn hàng.

### 6.3. Tỷ lệ chi phí chưa phân bổ

~~~sql
SELECT
  currency,
  ROUND(SUM(IF(cost_center = "unallocated", net_cost, 0)), 2)
    AS unallocated_net_cost,
  ROUND(SUM(net_cost), 2) AS total_net_cost,
  SAFE_DIVIDE(
    SUM(IF(cost_center = "unallocated", net_cost, 0)),
    NULLIF(SUM(net_cost), 0)
  ) AS unallocated_ratio
FROM `LAB_BILLING_PROJECT.billing_mart.v_daily_cost`
WHERE usage_date >= DATE "2026-11-01"
  AND usage_date < DATE "2026-12-01"
GROUP BY currency;
~~~

`SAFE_DIVIDE` tránh division by zero. Nếu net cost âm do credits lớn, ratio này **không còn là tỷ lệ trong khoảng 0–100%**; khi đó dùng gross usage cost hoặc quy tắc allocation riêng làm mẫu số, ghi rõ trong KPI.

## 7. Dashboard Looker Studio (Data Studio): từ SQL view đến biểu đồ

**Data Studio** là tên sử dụng trong tài liệu kết nối BigQuery hiện hành; nhiều đội vẫn gọi **Looker Studio**. Cả hai tên trong bài chỉ cùng công cụ báo cáo BI kết nối BigQuery, **không** phải Looker (Google Cloud core) dùng LookML.

### 7.1. Thiết lập data source

1. Mở Looker Studio/Data Studio và tạo **Report → Add data**.
2. Chọn **Google BigQuery** connector.
3. Chọn **Project → Dataset `billing_mart` → View `v_daily_cost`**. Có thể dùng **Custom Query** nhưng nên kiểm thử SQL trước trong BigQuery.
4. Chọn **billing project** trả phí xử lý truy vấn và credential mode phù hợp chính sách.
5. Xác nhận field types: `usage_date` là Date; `net_cost`, `gross_cost`, `credits` là numeric/currency; `currency` là dimension.
6. Cấp quyền người xem báo cáo đúng phạm vi và kiểm tra trên tài khoản không có quyền raw export.

**Quyền tối thiểu:** Người query cần `bigquery.jobs.create` ở project chạy jobs và quyền đọc view/tables phù hợp. Nếu viewer không nên đọc raw, dùng **authorized view** hoặc **bảng tổng hợp có phân quyền** thay vì cấp Data Viewer trên toàn `billing_raw`. Chế độ **Owner's credentials** trong dashboard có thể cho người xem nhìn thấy dữ liệu mà tài khoản họ không được đọc trực tiếp; phải xét như một quyết định phân quyền, không phải lựa chọn giao diện đơn thuần.

### 7.2. Bố cục dashboard gợi ý

~~~text
┌───────────────────── Cloud Cost Overview ─────────────────────┐
│ Date range   Project   Service   Cost center   Currency       │
├────────────────┬────────────────┬────────────────────────────┤
│ Net usage cost │ Gross usage    │ Credits                    │
├────────────────┴────────────────┴────────────────────────────┤
│ Line chart: Daily net cost (theo usage_date)                  │
├───────────────────────────┬───────────────────────────────────┤
│ Bar: Top 10 services      │ Bar: Top 10 projects              │
├───────────────────────────┴───────────────────────────────────┤
│ Table: Project × Service × Cost center × Net cost             │
├───────────────────────────────────────────────────────────────┤
│ Unallocated cost + Ghi chú: export delay, invoice khác usage  │
└───────────────────────────────────────────────────────────────┘
~~~

| Thành phần | Dimension | Metric | Để trả lời |
| --- | --- | --- | --- |
| Scorecard “Net usage cost” | Date range + currency | `SUM(net_cost)` | Chi phí vận hành sau credits |
| Scorecard “Gross” | Date range + currency | `SUM(gross_cost)` | Chi phí trước credits |
| Scorecard “Credits” | Date range + currency | `SUM(credits)` | Credits đã được áp dụng |
| Time series | `usage_date` | `SUM(net_cost)` | Ngày nào tăng bất thường? |
| Top services | `service_name` | `SUM(net_cost)` | Dịch vụ nào đóng góp lớn? |
| Top projects | `project_id` | `SUM(net_cost)` | Project nào cần điều tra? |
| Cost center table | `cost_center` | `SUM(net_cost)` | Chưa phân bổ bao nhiêu? |

**Đặt tiêu đề chính xác:** Scorecard này là **Net usage cost**, không gọi “Invoice due” vì daily view loại `tax/adjustment/rounding` và nhóm theo ngày sử dụng. Tạo **trang Invoice reconciliation riêng** nối với `v_invoice_cost`, lọc `invoice_month` và hiện đủ cost types.

### 7.3. Bộ lọc và định dạng

- Đặt **Date range control** trên `usage_date`, mặc định “30 ngày gần nhất” hoặc khoảng được duyệt.
- Thêm dropdowns cho `project_id`, `service_name`, `cost_center` và `currency`.
- Đặt currency rõ ràng trong metric/title. Không dùng ký hiệu `$` cho hóa đơn tính VND.
- Giữ “Unknown/unallocated” trong biểu đồ để thấy thiếu nhãn thay vì lọc mất nó.
- Với top-N, có **bảng đầy đủ và export CSV** cho nhóm điều tra (tùy quyền).
- Cấu hình refresh/cache phù hợp; không tạo dashboard tự refresh mỗi vài giây khi Billing export không có realtime SLA.

## 8. Đối soát số liệu trước khi chia sẻ

**Một dashboard được coi là đúng khi định nghĩa metric và kỳ báo cáo khớp với báo cáo chính thức.**

### 8.1. Hai cách xem phải tách

- **Usage cost dashboard:** nhóm theo `usage_date`, thường tập trung `cost_type="regular"`. Dùng để đánh giá xu hướng, tác động workload và cost center.
- **Invoice reconciliation:** nhóm theo `invoice.month`, gồm các loại `regular/tax/adjustment/rounding_error` và credits phù hợp. Dùng so sánh với Cloud Billing invoice/Reports theo cùng currency/billing account.

Bảng sau là ví dụ **giả định**, không phải số tiền thực tế:

| Dòng | Usage month | Invoice month | Cost type | Gross | Credits | Net |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Compute Engine usage | 202611 | 202611 | regular | 120.00 | -20.00 | 100.00 |
| BigQuery usage cuối tháng | 202611 | 202612 | regular | 10.00 | 0.00 | 10.00 |
| Thuế hóa đơn | — | 202611 | tax | 5.00 | 0.00 | 5.00 |
| Điều chỉnh | 202610 | 202611 | adjustment | -2.00 | 0.00 | -2.00 |

**Kết quả:** Usage November (regular) = 110.00; Invoice November (tất cả cost types ở bảng) = 103.00; **khác nhau hợp lý** vì thời điểm ghi hóa đơn và adjustments/tax. Đừng “sửa” bằng cách cộng lại các dòng export cho bằng một số không cùng kỳ.

### 8.2. Quy trình đối soát

1. Xác định **billing account, currency, invoice month, time zone và filter** giống Cloud Billing Reports.
2. So sánh **gross, credits, net** riêng theo `cost_type`.
3. Kiểm tra export đã đầy đủ chưa bằng `MAX(export_time)` và mốc usage mới nhất; lưu ý export_time mới không bảo đảm mọi sản phẩm đã báo cáo xong.
4. Kiểm tra dòng `project_id IS NULL`, adjustments và roundings trước khi ép gán chi phí.
5. Nếu dùng CUD, phân biệt **commitment fees**, **credits** và lựa chọn phân bổ chi phí; không cộng credits hoặc subtract hai lần.
6. Ghi nhận số chênh và giải thích; nếu invoice đã phát hành, **invoice là chuẩn đối soát thanh toán**.
7. Lưu kiểm tra này thành một quy trình tháng thay vì sửa số liệu thủ công trong dashboard.

### 8.3. Kiểm tra độ tươi dữ liệu

~~~sql
SELECT
  currency,
  MAX(export_time) AS last_export_time,
  MAX(usage_start_time) AS latest_usage_start,
  COUNT(*) AS rows_seen
FROM
  `LAB_BILLING_PROJECT.billing_raw.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
GROUP BY currency;
~~~

Lệnh chỉ đọc nhưng có **query cost**. Nếu view/mart được làm mới theo lịch, cần phân biệt `last_export_time` của nguồn và `last_mart_refresh_time` của bảng tổng hợp; dashboard không nên hiển thị như “live billing”.

## 9. Không để dashboard tạo thêm hóa đơn lớn

Mỗi lần dashboard tải, thay đổi filter hoặc refresh, BigQuery có thể chạy query mới. Nếu raw export lớn, truy vấn qua view quét lại bảng gốc có thể tốn phí đáng kể. Cần quản lý **chi phí của chính hệ thống phân tích chi phí**.

### 9.1. Dry run và maximum bytes billed

~~~bash
# Chỉ ước lượng, không thực thi query thật
bq query \
  --project_id=LAB_BILLING_PROJECT \
  --use_legacy_sql=false \
  --dry_run \
  'SELECT COUNT(*) FROM `LAB_BILLING_PROJECT.billing_mart.v_daily_cost`'

# Thực thi có giới hạn 1 GiB bytes billed (có thể bị từ chối)
bq query \
  --project_id=LAB_BILLING_PROJECT \
  --use_legacy_sql=false \
  --maximum_bytes_billed=1073741824 \
  'SELECT currency, SUM(net_cost) AS cost
   FROM `LAB_BILLING_PROJECT.billing_mart.v_daily_cost`
   WHERE usage_date >= DATE "2026-11-01"
   GROUP BY currency'
~~~

*Dry run* là bước kiểm tra cú pháp và ước lượng bytes được xử lý; BigQuery không tính phí xử lý query trong dry run. `maximum_bytes_billed` giúp từ chối query khi ước lượng vượt ngưỡng **trước khi tính phí thực thi**. Với clustered table, ước lượng trước khi chạy có thể cao hơn bytes quét thực tế.

**Không coi `LIMIT 10` là biện pháp giảm phí** đối với bảng không clustered. Để khám phá vài hàng, dùng **BigQuery Preview** hoặc `bq head` khi phù hợp, thay vì `SELECT *` toàn nguồn.

### 9.2. Thiết kế mart tổng hợp được partition/cluster

Bản `v_daily_cost` là **view**, không phải bảng đã partition. Khi dashboard thường xuyên quét nhiều tháng của bảng raw, cân nhắc **tạo bảng vật lý tổng hợp**:

~~~sql
-- Ví dụ tạo dữ liệu tổng hợp trong LAB, có chi phí lưu trữ/query.
-- Không chạy định kỳ nguyên lệnh này trên raw dataset rất lớn.
CREATE OR REPLACE TABLE
  `LAB_BILLING_PROJECT.billing_mart.daily_cost_snapshot`
PARTITION BY usage_date
CLUSTER BY project_id, service_id
AS
SELECT *
FROM `LAB_BILLING_PROJECT.billing_mart.v_daily_cost`;
~~~

Truy vấn dashboard sang `daily_cost_snapshot` sẽ tận dụng **partition pruning** khi lọc trực tiếp `usage_date` và block pruning khi lọc `project_id/service_id`. Đánh đổi là phải trả phí lưu trữ và **cập nhật bảng snapshot khi raw export có dữ liệu mới hoặc điều chỉnh**.

**Đối với production:** Dùng Scheduled Queries hoặc workflow được phê duyệt để cập nhật những partitions gần đây, có checkpoint và kiểm tra duplicates. Nếu chỉ refresh **30 ngày gần nhất**, những điều chỉnh thuộc kỳ xa hơn có thể bị bỏ sót; cần **đối soát invoice theo kỳ** và cơ chế cập nhật lại khi có điều chỉnh trễ. Không thay raw export; mart là dữ liệu dẫn xuất.

### 9.3. Nguyên tắc giảm phí báo cáo

- Dùng **Standard export** cho dashboard tổng quan; Detailed chỉ cho câu hỏi resource-level.
- Chọn các cột cần dùng; tránh `SELECT *` trong truy vấn trực tiếp dữ liệu thô.
- Với bảng **thực sự có partition**, lọc theo partition column và kiểm tra pruning. Không khẳng định raw billing export tự partition theo cấu hình của bạn.
- Đừng tạo một biểu đồ chạy `SELECT * FROM raw` cho mỗi người dùng.
- Ưu tiên daily/monthly aggregate khi số người xem nhiều.
- Điều chỉnh **data freshness** theo lịch export thực tế, tránh refresh từng giây.
- Dùng Monitoring/Cloud Billing Reports để quan sát trước khi tăng query frequency.
- Kiểm tra BigQuery job costs/bytes billed theo project và gắn nhãn nhóm báo cáo khi phù hợp.

## 10. Phân quyền, bảo mật và quản trị dashboard

### 10.1. Ai được làm gì?

| Vai trò | Phạm vi nên có | Tránh cấp |
| --- | --- | --- |
| Billing export operator | Billing account + dataset setup | Owner toàn organization nếu không cần |
| FinOps analyst | Đọc raw/mart và chạy query trong project phân tích | Quyền xóa/sửa raw |
| Data engineer | Tạo/sửa views, mart, scheduled queries | Billing admin nếu không vận hành export |
| Dashboard consumer | Đọc **bảng/view tổng hợp** theo giới hạn đã duyệt | Full raw export, thông tin resource không cần |
| Pipeline identity | Ghi bảng mart hoặc chạy scheduled query | Project Editor |
| Auditor | Đọc báo cáo đối soát/bằng chứng | Quyền thay billing export |

**Cần có `bigquery.jobs.create`** ở project thực thi query cùng quyền đọc bảng/view cần thiết. Với dashboard dùng **Owner's credentials**, phải duyệt dữ liệu mà chủ sở hữu cho phép xem, vì người mở báo cáo có thể không có quyền BigQuery trực tiếp. Với **Viewer's credentials**, mỗi người xem phải có quyền thích hợp để query; hai cơ chế có hệ quả kiểm soát truy cập khác nhau.

Nếu dashboard cần tiết lộ **chỉ tổng theo cost center**, có thể xây bảng daily aggregate riêng theo cost center, rồi cấp Data Viewer ở dataset hẹp. Không chia sẻ view có `project_name`, labels hoặc SKU nhạy cảm cho bên không có nhu cầu.

### 10.2. Chất lượng dữ liệu và quy tắc phân bổ

- Chuẩn hóa `cost_center` / `env` / `team` bằng labels/tags cùng taxonomy.
- Phân biệt nhãn **project-level** và **resource-level**; tỷ lệ bao phủ có thể không giống nhau.
- Đưa `UNATTRIBUTED/unallocated` thành category hữu hình, không gán đại vào nhóm “Other”.
- Với chi phí chia sẻ như network, centralized logging hoặc commitment fees, lập **allocation rule** độc lập; không tự đẩy hết cho project chứa dữ liệu.
- Định nghĩa gross, credits, net, invoice và usage date bằng **data dictionary**.
- Áp dụng chính sách retention, audit logs và BigQuery IAM cho cả dữ liệu billing và mart.

### 10.3. Khi nào cần BigQuery row-level security?

Nếu một bảng vật lý có nhiều cost centers mà mỗi đội chỉ được xem chi phí của mình, có thể cân nhắc **row access policies** hoặc tạo các **authorized views** theo team. Nhưng nếu áp dụng row-level security trực tiếp trên **raw export**, phải đảm bảo service account hệ thống của Cloud Billing **vẫn đọc/ghi được toàn bảng theo hướng dẫn**, tránh làm hỏng export.

Với bài lab, cách an toàn và dễ hiểu là chỉ chia sẻ **tổng hợp đã lọc/kiểm định**. Thiết kế bảo mật thật cần review riêng bởi đội dữ liệu và IAM.

## 11. Thực hành bằng dữ liệu giả — không cần xem hóa đơn thật

Phần này **có thể chạy trong BigQuery SQL editor** khi tài khoản chỉ có quyền thực hiện query trong một project lab, không cần Billing Account Admin hoặc export thật. Nó sử dụng dữ liệu **inline**, không tạo/sửa bảng.

### 11.1. Bộ dữ liệu giả

Giả định currency VND, hai ngày và ba dòng usage:

| Ngày | Project | Dịch vụ | Gross (VND) | Credits | Net (VND) |
| --- | --- | --- | ---: | ---: | ---: |
| 2026-11-17 | p-shop | Compute Engine | 120.000 | -15.000, -5.000 | 100.000 |
| 2026-11-17 | p-shop | BigQuery | 30.000 | 0 | 30.000 |
| 2026-11-18 | p-analytics | Cloud Storage | 50.000 | -5.000 | 45.000 |
| **Tổng** | | | **200.000** | **-25.000** | **175.000** |

Ví dụ đầu tiên có **hai credits trên một dòng** để kiểm tra lỗi `UNNEST` nhân đôi `cost`.

### 11.2. SQL hoàn chỉnh có thể chạy độc lập

~~~sql
-- Query từ dữ liệu inline; chỉ tạo kết quả, không ghi vào BigQuery table.
WITH sample AS (
  SELECT
    DATE "2026-11-17" AS usage_date,
    "p-shop" AS project_id,
    "Compute Engine" AS service_name,
    "VND" AS currency,
    NUMERIC "120000" AS cost,
    [STRUCT(NUMERIC "-15000" AS amount),
     STRUCT(NUMERIC "-5000" AS amount)] AS credits
  UNION ALL
  SELECT
    DATE "2026-11-17", "p-shop", "BigQuery", "VND",
    NUMERIC "30000",
    ARRAY<STRUCT<amount NUMERIC>>[]
  UNION ALL
  SELECT
    DATE "2026-11-18", "p-analytics", "Cloud Storage", "VND",
    NUMERIC "50000",
    [STRUCT(NUMERIC "-5000" AS amount)]
),
cost_lines AS (
  SELECT
    usage_date, project_id, service_name, currency,
    cost AS gross_cost,
    COALESCE(
      (SELECT SUM(c.amount) FROM UNNEST(credits) AS c),
      NUMERIC "0"
    ) AS credit_amount
  FROM sample
)
SELECT
  currency,
  project_id,
  SUM(gross_cost) AS gross_cost,
  SUM(credit_amount) AS credits,
  SUM(gross_cost + credit_amount) AS net_cost
FROM cost_lines
GROUP BY currency, project_id
ORDER BY project_id;
~~~

**Kết quả mong đợi:**

| Project | Gross (VND) | Credits (VND) | Net (VND) |
| --- | ---: | ---: | ---: |
| p-analytics | 50.000 | -5.000 | 45.000 |
| p-shop | 150.000 | -20.000 | 130.000 |

Nếu query dùng `LEFT JOIN UNNEST(credits)` rồi cộng `cost`, p-shop gross có thể bị tính thành **270.000** vì hàng Compute Engine có hai credits. Nếu dùng `CROSS JOIN UNNEST(credits)`, dòng BigQuery không có credits còn bị loại; cả hai đều sai cho phép cộng gross cost.

### 11.3. Nhiệm vụ mở rộng

1. Sửa query để nhóm theo **`usage_date`**; xác nhận ngày 17 net = **130.000**, ngày 18 net = **45.000**.
2. Sửa query nhóm theo **`service_name`**, tìm dịch vụ có net cost lớn nhất.
3. Thêm một dòng `cost_type = "tax"` giả và chứng minh daily usage view không tính tax, còn invoice view có.
4. Tạo thêm field `cost_center`, cho một dòng giá trị `unallocated`; viết KPI tỷ lệ chi phí chưa gán.
5. Giải thích tại sao `sum(cost) - sum(credits.amount)` là sai khi credits âm.
6. Nếu một dòng currency = USD, sửa query để **không cộng USD với VND**.

**Không copy số giả này vào dashboard production.** Nếu muốn dựng báo cáo trực quan thuần demo, tạo **dataset/sample table riêng** theo phê duyệt hoặc dùng nguồn báo cáo CSV riêng; không đưa records giả vào `billing_raw`.

## 12. Lab thực tế: Cloud Billing → dashboard có thể kiểm định

**Điều kiện:** Chỉ thực hiện nếu được cấp **Billing export dataset lab** và các IAM cần thiết. Nếu chưa có quyền, hoàn thành mục 11 và mô tả dashboard bằng sơ đồ; không tự xin quyền Billing Admin để lấy dữ liệu tổ chức.

| Bước | Thao tác | Bằng chứng |
| --- | --- | --- |
| 1 | Ghi billing account, dataset location, export type | Không nhầm Standard với Detailed |
| 2 | Xác minh bảng Standard có dữ liệu | Tên bảng, sơ bộ date range, `MAX(export_time)` |
| 3 | Tạo `billing_mart.v_cost_lines` | Net = cost + per-row credits |
| 4 | Tạo `v_daily_cost` và `v_invoice_cost` | Cùng source, khác cách nhóm kỳ/cost_type |
| 5 | Dry run query và đặt maximum bytes billed | Biết bytes ước lượng, không quét mù |
| 6 | Thử một project một tuần | SQL result group/currency đúng |
| 7 | Kết nối Data Studio với daily view | Có data source, đúng field types |
| 8 | Dựng scorecards, time series, service/project bars | Có date/project/currency filters |
| 9 | Dựng trang invoice reconciliation riêng | Dùng `invoice_month` và mọi cost types |
| 10 | Đối chiếu với Cloud Billing Reports | Ghi khác biệt và nguyên nhân |
| 11 | Chia sẻ với tài khoản có quyền thấp | Không lộ raw billing ngoài phạm vi |
| 12 | Ghi refresh interval, owner và cost monitoring | Báo cáo có trách nhiệm vận hành |

**Lựa chọn giảm phí:** Với dữ liệu thật, làm các SQL trên **một kỳ nhỏ** đầu tiên, xem bytes và bảng export có dung lượng bao nhiêu trước khi chạy dashboard/refresh rộng.

## 13. Phát hiện biến động: câu hỏi thực tế từ dashboard

Ngoài các chart cơ bản, một cách phát hiện tăng chi phí là so **7 ngày đã hoàn tất** gần nhất với **7 ngày trước đó**, theo project/currency. Với dữ liệu Billing export đến muộn, kết quả này chỉ là **tín hiệu điều tra**, không kết luận chắc đã tăng chi phí do hệ thống.

~~~sql
WITH by_day AS (
  SELECT
    usage_date, currency, project_id,
    SUM(net_cost) AS daily_cost
  FROM `LAB_BILLING_PROJECT.billing_mart.v_daily_cost`
  WHERE usage_date >= DATE_SUB(CURRENT_DATE("Asia/Ho_Chi_Minh"), INTERVAL 14 DAY)
    AND usage_date < CURRENT_DATE("Asia/Ho_Chi_Minh")
  GROUP BY 1, 2, 3
),
compared AS (
  SELECT
    currency,
    project_id,
    SUM(IF(
      usage_date >= DATE_SUB(CURRENT_DATE("Asia/Ho_Chi_Minh"), INTERVAL 7 DAY),
      daily_cost, 0
    )) AS last_7_days,
    SUM(IF(
      usage_date < DATE_SUB(CURRENT_DATE("Asia/Ho_Chi_Minh"), INTERVAL 7 DAY),
      daily_cost, 0
    )) AS previous_7_days
  FROM by_day
  GROUP BY 1, 2
)
SELECT
  currency, project_id,
  ROUND(previous_7_days, 2) AS previous_7_days,
  ROUND(last_7_days, 2) AS last_7_days,
  ROUND(last_7_days - previous_7_days, 2) AS delta,
  SAFE_DIVIDE(
    last_7_days - previous_7_days,
    NULLIF(previous_7_days, 0)
  ) AS change_ratio
FROM compared
ORDER BY delta DESC;
~~~

**Khi đánh giá biến động:** So sánh lượng workload (requests, GB storage, slot-hours), thay đổi release, CUD, pricing/SKU, credit, các dòng late export và lịch làm việc (ngày thường/cuối tuần). Nếu baseline = 0 hoặc có giá trị âm do credits/adjustments, cần xử lý riêng thay vì hiển thị tỷ lệ “+∞%”.

**Không tự shutdown production chỉ vì query có `delta > 0`.** Cloud Billing Budgets/Monitoring alert và quy trình triage phải có ngưỡng, chủ sở hữu, bước xác minh và hành động được phê duyệt.

## 14. Các lỗi hay gặp và cách điều tra

| Hiện tượng | Nguyên nhân thường gặp | Xử lý |
| --- | --- | --- |
| Không thấy bảng export | Chưa bật export, chọn nhầm billing account/dataset, chưa có data | Kiểm tra Billing export config, vài giờ propagation |
| Không có chi phí tháng trước | Dataset ở region không backfill | Không tự giả định dữ liệu bị mất; tra điều kiện export |
| Dashboard cao gấp đôi | Cộng Standard + Detailed, `UNNEST credits` tạo nhiều hàng | Chỉ chọn một nguồn usage, kiểm tra SQL one-row semantics |
| Net cost lớn hơn gross bất thường | Trừ credits âm thêm lần nữa | `cost + SUM(credits.amount)` |
| Tổng dashboard không khớp hóa đơn | Dùng usage date, loại tax/adjustment/rounding, currency mismatch | Đối soát theo `invoice.month`, cost types, currency |
| Một project “0 chi phí” | Lọc sai project hoặc `project.id` NULL; export đến trễ | Kiểm tra filters/schema/số ngày đã xuất |
| Label cost center trống | Chưa gắn label hoặc loại usage không có | Xếp `unallocated`; xem taxonomy/scope |
| Có quyền xem report nhưng Access Denied | BigQuery Data Viewer/jobs.create hoặc Owner/Viewer credentials | Kiểm tra identity dùng để query và permissions |
| Dashboard rất chậm/tốn tiền | Query raw export lớn, refresh quá thường | Dry run, aggregate, partitioned mart, cache |
| Ảnh hưởng sau schema update | View `SELECT *` hoặc field mới khác schema | Định nghĩa view chọn cột ổn định, tests |
| Daily cost hôm nay thấp | Export chưa đầy đủ hoặc services report chậm | Gắn chú thích “dữ liệu chưa chốt”, không dùng realtime SLA |
| Tiền theo project khác báo cáo chính thức | Shared costs, CUD allocation, taxonomy chưa thống nhất | Lập quy tắc phân bổ và reconcile |
| Currency hiển thị sai | Trộn currencies hoặc format `$` cố định | Group/filter currency trước khi tạo metrics |

**Thứ tự kiểm tra:** billing account → export settings/dataset location → table/date coverage → IAM → SQL net/credits → invoice vs usage period → labels/filters → dashboard credential → bytes billed/freshness.

## 15. Bài tập ôn tập kèm đáp án gợi ý

1. **Standard khác Detailed export?** Standard phù hợp tổng quan; Detailed thêm resource-level fields.
2. **Dùng cả Standard lẫn Detailed cộng chung được không?** Không, có thể đếm cùng một usage hai lần.
3. **Cost 100, credits -20, -5 thì net?** 75, không phải 125.
4. **Vì sao không `LEFT JOIN UNNEST(credits)` rồi `SUM(cost)`?** Một source row có nhiều credits sẽ nhân bản cost.
5. **`invoice.month` và `usage_start_time` luôn cùng tháng?** Không.
6. **`export_time` có phải thời điểm sử dụng?** Không, đó là thời điểm xuất.
7. **Có thể dùng dashboard làm giới hạn chi phí cứng?** Không.
8. **Vì sao `LIMIT 10` không đảm bảo giảm query cost?** Không giúp giảm scan trên bảng không clustered.
9. **Giữ credit ở repeated field cần xử lý thế nào?** Tổng credit trong **mỗi row**, sau đó mới aggregate.
10. **Nhóm VND và USD trong một KPI được không?** Không, trừ khi có quy tắc chuyển đổi được duyệt.
11. **Một dòng tax có nên nằm trong Net usage daily?** Không theo định nghĩa ví dụ; nằm ở invoice reconciliation.
12. **Bật export Standard hôm nay trong single region, có dữ liệu năm trước?** Thường không backfill trước ngày bật.
13. **Thêm label cost_center hôm nay, báo cáo chi phí tháng trước sẽ tự có label?** Không.
14. **Tại sao dùng view trước dashboard?** Chuẩn hóa schema, metrics và hạn chế truy vấn ad hoc khác định nghĩa.
15. **Authorized view khác owner credentials ở dashboard?** Authorized view giới hạn dữ liệu BigQuery được truy cập; owner credentials cho phép query theo danh tính chủ sở hữu báo cáo.
16. **Tối ưu dashboard cần gì?** Dry run, max bytes billed, aggregate table, partition filters và refresh phù hợp.
17. **Cần KPI nào để điều tra overspend?** Gross/net/credits, trends, top service/project, unallocated và biến động so baseline.
18. **Đối soát cuối tháng dùng nhóm thời gian nào?** `invoice.month` và đầy đủ cost types/credits.

## 16. Checklist hoàn thành và nguồn tham khảo

- [ ] Dữ liệu lấy từ đúng billing account, Standard/Detailed không bị cộng đôi.
- [ ] Dataset location/backfill phù hợp chính sách; export đã có đủ kỳ cần xem.
- [ ] Phân quyền export operator, BigQuery analyst, dashboard consumer riêng.
- [ ] Một view chuẩn hóa `cost` và repeated `credits` bằng phép tổng trên từng row.
- [ ] Có phân biệt `usage_date`, `invoice_month` và `export_time`.
- [ ] `currency` là dimension/filter bắt buộc để tránh tổng sai đơn vị.
- [ ] Dashboard vận hành phân biệt regular cost với tax/adjustment/invoice.
- [ ] Có metadata project/service/SKU/cost center và mục `unallocated`.
- [ ] Dashboard filters được kiểm tra với nhiều projects/services.
- [ ] Có dry run, maximum bytes billed và ngân sách cho BigQuery dashboard.
- [ ] Nếu snapshot/aggregate: có kế hoạch refresh, late adjustments và reconciliation.
- [ ] View/authorized tables bảo vệ raw billing; credential mode đã review.
- [ ] KPI total đã đối soát với Cloud Billing Reports/Invoice cùng kỳ/currency.
- [ ] Có refresh time, owner, thông báo dữ liệu hiện tại có thể chưa hoàn chỉnh.
- [ ] Có bài test dữ liệu giả, kiểm tra credits hai phần tử không nhân đôi cost.

**Nguồn Google Cloud chính thức:**

- [Export Cloud Billing data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery) — loại export và phạm vi.
- [Set up Cloud Billing data export](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup) — IAM, dataset location, backfill và độ trễ.
- [Understand export tables](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables) — Standard/Detailed/FOCUS và schemas.
- [Standard usage cost schema và queries](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage) — cost, credits, invoice.month, labels.
- [Detailed usage cost schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage) — resource-level costs.
- [Example queries for Billing data](https://docs.cloud.google.com/billing/docs/how-to/bq-examples) — đối soát và tính credits.
- [Cloud Billing Reports](https://docs.cloud.google.com/billing/docs/how-to/reports) — giải thích số liệu và Generate query.
- [Data Studio BigQuery connector](https://docs.cloud.google.com/data-studio/connect-to-google-bigquery) — kết nối tables/views/custom SQL và credentials.
- [BigQuery visualization with Data Studio](https://docs.cloud.google.com/bigquery/docs/visualize-looker-studio) — tạo và chia sẻ báo cáo.
- [BigQuery: Estimate and control costs](https://docs.cloud.google.com/bigquery/docs/best-practices-costs) — dry run và maximum bytes billed.
- [Partitioned tables](https://docs.cloud.google.com/bigquery/docs/partitioned-tables) và [Clustered tables](https://docs.cloud.google.com/bigquery/docs/clustered-tables) — tối ưu scan trên mart.
- [Cloud Billing budgets and alerts](https://docs.cloud.google.com/billing/docs/how-to/manage-budgets) — cảnh báo và quy trình quản lý chi tiêu.
- [BigQuery IAM](https://docs.cloud.google.com/bigquery/docs/access-control) — least privilege, views và jobs.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) — compute/storage và chi phí dashboard.

**Ghi nhớ:** Dashboard chi phí đáng tin cậy không chỉ cần `SUM(cost)`. Hãy **chọn đúng nguồn export, cộng credits ở từng dòng, không trộn currencies, tách tháng sử dụng với tháng hóa đơn, đối soát và giới hạn quyền truy cập**. Dùng BigQuery views/mart để cố định định nghĩa KPI, rồi Looker Studio/Data Studio để trực quan hóa mà vẫn kiểm soát bytes quét và phí vận hành.
