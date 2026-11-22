# Thực hành tổ chức miền dữ liệu và phân quyền phân tích

Một doanh nghiệp có nhóm **Sales** sở hữu dữ liệu đơn hàng, nhóm **Customer** quản lý hồ sơ khách hàng và nhóm **Analytics** xây dashboard. Nếu mọi nhà phân tích đều có quyền đọc toàn bộ các bảng, người làm báo cáo doanh thu cũng có thể nhìn thấy email, số điện thoại hoặc dữ liệu ngoài phạm vi công việc. Giải pháp không phải là tạo thật nhiều project rồi mặc định mọi dữ liệu an toàn: cần **miền dữ liệu có chủ sở hữu**, **hợp đồng dữ liệu** và **phân quyền ở đúng lớp**.

Bài thuộc chương **Quản trị và khai thác dữ liệu** của học phần **CLOUD_PROVIDERS_GCP**. Chúng ta kết hợp project, IAM, BigQuery, Cloud Storage, Knowledge Catalog, ứng dụng Java/Cloud Run, pipeline dữ liệu, giám sát và chi phí để triển khai một **data product phân tích doanh thu** có thể kiểm thử quyền truy cập. Ví dụ sử dụng dữ liệu giả và GoogleSQL; phần mở rộng mô tả row-level security, column policy tags, masking, BigQuery sharing và data-quality controls.

Sau bài học, bạn có thể:

- Phân định **data domain**, **data owner**, **data steward**, **data producer** và **data consumer**.
- Thiết kế ranh giới project/dataset/table/view phù hợp với miền và môi trường.
- Tách quyền **chạy query jobs** khỏi quyền **đọc dữ liệu**, tránh cấp Viewer/Editor toàn project.
- Tạo **BigQuery authorized view** để Analytics đọc aggregate mà không cần quyền bảng nguồn.
- Dùng **row access policies**, column-level access control và masking trong những tình huống thích hợp.
- Kiểm chứng quyền với hai danh tính độc lập, kiểm tra IAM hiệu lực và lập runbook sự cố.
- Định nghĩa data contract, metadata/glossary/lineage, quality assertions và quyền yêu cầu truy cập.
- Ước tính chi phí query/storage/governance và tổ chức rollout có khả năng rollback.

> **Giới hạn lab:** mọi project ID, Google Group, service account, dataset và địa chỉ email dưới đây là **placeholder**. Không chạy IAM/DDL trong project production hoặc với dữ liệu thật khi chưa được phê duyệt. Bài chỉ hướng dẫn; không thực thi lệnh trên tài khoản GCP. Tạo query jobs, bảng, scan và tài nguyên liên quan có thể phát sinh phí.

## 1. Miền dữ liệu là trách nhiệm nghiệp vụ, không chỉ thư mục

**Data domain** là phạm vi nghiệp vụ có người chịu trách nhiệm về nghĩa, chất lượng và cách công bố dữ liệu. Một miền có thể có nhiều bảng/project, và một project có thể chứa nhiều dataset; **tên folder/project không tự tạo chính sách truy cập**.

| Miền | Nguồn dữ liệu | Data product công bố | Chủ sở hữu/đối tượng tiêu thụ |
|---|---|---|---|
| **Sales** | Đơn hàng, thanh toán, hoàn tiền | Doanh thu theo ngày/khu vực | Sales owner → Analytics |
| **Customer** | Hồ sơ, địa chỉ liên hệ, consent | Customer segments ít nhạy cảm | Customer owner → Marketing/Analytics |
| **Inventory** | Tồn kho, nhập/xuất | Tồn kho khả dụng theo SKU | Supply chain → Sales |
| **Analytics** | Các data products được cho phép | Dashboard/metric definitions | Analytics owner → người ra quyết định |

### Vai trò không nên nhập làm một

| Vai trò | Chịu trách nhiệm chính | Không mặc nhiên được quyền |
|---|---|---|
| **Domain owner** | Quyết định mục đích sử dụng, tiêu chuẩn và chính sách chia sẻ | Project Owner trên toàn bộ GCP |
| **Data steward** | Thuật ngữ, quality, classification, lineage, yêu cầu truy cập | Đọc tất cả cột PII |
| **Data engineer / producer** | Ingestion, schema, pipeline, freshness, publish | Cấp quyền IAM cho bất kỳ ai |
| **Platform/IAM team** | Project factory, service accounts, IAM, policies, audit | Quyết định ngữ nghĩa `doanh_thu_thuan` |
| **Analytics consumer** | Truy vấn dữ liệu được công bố, tạo dashboard | Xem bảng raw/private hoặc sửa policy |

Một **data product** cần có owner, định nghĩa, dữ liệu đầu ra, tiêu chí chất lượng, thời gian cập nhật, phân loại nhạy cảm và quy trình yêu cầu quyền. Ví dụ: “Doanh thu thanh toán đã hoàn tất, nhóm theo ngày UTC và khu vực, không bao gồm hoàn tiền, cập nhật trước 08:00, người nhận chỉ được xem aggregate”.

## 2. Kiến trúc miền Sales → Analytics

~~~mermaid
flowchart LR
  SRC["Cloud Run / Pub/Sub / Cloud SQL"] --> RAW["sales-private project<br/>sales_private.orders"]
  RAW --> VIEW["sales-private project<br/>sales_public.v_paid_daily<br/>authorized view"]
  VIEW --> Q["analytics-query project<br/>BigQuery query job / Java BI API"]
  Q --> BI["Dashboard"]
  CAT["Knowledge Catalog<br/>owner + glossary + lineage + quality"] --> RAW
  CAT --> VIEW
  IAM["IAM + source dataset authorization<br/>+ row/column policies"] --> RAW
  IAM --> VIEW
~~~

Để thao tác dễ kiểm soát, lab có **hai Google Cloud projects**:

~~~text
DATA_PROJECT (ví dụ: company-sales-lab)
  ├── sales_private  ← BigQuery dataset, bảng đơn hàng có PII
  │   └── orders
  ├── sales_public   ← Dataset chỉ cho analytics products
  │   └── v_paid_daily  ← Authorized logical view
  └── sales_rls_lab  ← Dataset riêng để kiểm thử row-level policy
      └── regional_orders

QUERY_PROJECT (ví dụ: company-analytics-lab)
  ├── nhóm/caller được phép tạo query jobs
  └── Java Cloud Run hoặc BI client truy vấn view ở DATA_PROJECT
~~~

| Ranh giới | Quyết định | Lý do |
|---|---|---|
| **Project** | Tách Sales data hosting và Analytics query/billing | Ownership, billing, job permissions và quota có thể quản lý riêng |
| **Dataset** | `sales_private` khác `sales_public` | Không trao Data Viewer của bảng PII khi cần đọc views |
| **View** | Chỉ aggregate `sale_date, region, paid_orders, revenue_minor` | Giảm dữ liệu cần chia sẻ; tránh email/customer ID |
| **IAM** | Consumer có `jobUser` tại QUERY_PROJECT và `dataViewer` ở sales_public | Không cần Data Viewer trên sales_private |
| **Authorized view** | Source dataset cho phép đúng view đọc bảng gốc | View chạy được khi consumer không có quyền nguồn |
| **Security nâng cao** | RLS/column policy tags/BigQuery masking khi phù hợp | Hàng và cột nhạy cảm có chính sách riêng |

**Quan trọng:** authorized view **không phải** view thông thường với một câu `WHERE`. Nếu analyst vẫn có quyền đọc `sales_private.orders` từ một role ở project/folder/organization, họ có thể bỏ qua view và truy cập bảng nguồn. Phải kiểm tra **IAM hiệu lực** ở mọi cấp và các quyền kế thừa.

### Môi trường và location

- Tách **dev/staging/prod** và **real/fictional data**, không mang bản sao PII production về lab tùy tiện.
- Dataset nguồn và authorized view cần ở **cùng BigQuery location**; cross-region queries không tự hoạt động chỉ nhờ IAM.
- Query jobs có **billing/execution project** và location xác định; QUERY_PROJECT có thể khác DATA_PROJECT.
- Cross-project billing không tự thay đổi quyền truy cập dữ liệu. VPC Service Controls, organization policies, data residency và CMEK có thể chặn thao tác dù BigQuery IAM cho phép.

## 3. BigQuery IAM: quyền chạy job khác quyền xem dữ liệu

| Quyền | Scope điển hình | Tác dụng |
|---|---|---|
| `roles/bigquery.jobUser` | **QUERY_PROJECT** | Cho phép `bigquery.jobs.create` để chạy query trong project |
| `roles/bigquery.dataViewer` | `DATA_PROJECT.sales_public` hoặc view cụ thể | Đọc tables/views được cấp, không tự mở dataset khác |
| `roles/bigquery.dataEditor` | Dataset producer được giao | Sửa/tạo bảng hoặc view theo quyền của role |
| `roles/bigquery.dataOwner` | Dataset cần quản trị | Quản lý dữ liệu và quyền dataset; cấp cho rất ít principal |
| `roles/bigquery.metadataViewer` | Dataset cần khám phá | Xem metadata mà không cần đọc dữ liệu |
| `roles/bigquery.securityAdmin` / policy tag admin | Phạm vi phân quyền an ninh theo chức năng | Quản trị row policies/data policies/taxonomy, không phải role analyst phổ thông |

**Tách hai quyền:** có `bigquery.jobs.create` nhưng không có `bigquery.tables.getData` → query bảng bị từ chối. Có Data Viewer trên view nhưng thiếu jobUser ở **project chạy query** → cũng không tạo được job. `roles/bigquery.jobUser` không nên cấp toàn organization nếu chỉ cần một project billing.

**Bẫy dataset IAM:** `bq add-iam-policy-binding` được dùng cho **table/view**, **không hỗ trợ dataset**. Trong lab, dùng **GoogleSQL DCL `GRANT ... ON SCHEMA`**, Console Dataset Sharing, hoặc API/`bq update` khi thực sự phải sửa dataset access controls.

### Nguyên tắc giới hạn quyền

1. Dùng Google Groups theo **vai trò nghiệp vụ**, ví dụ `analytics-revenue@example.com` thay vì cấp cho hàng chục user lẻ.
2. Runtime service account của Java dashboard có quyền **query product**, không có quyền quản lý IAM hoặc data engineering.
3. Chỉ nhóm quản trị Sales có quyền sửa nội dung authorized view và quyền cho view đọc source; reviewer phải kiểm tra thay đổi SQL của view.
4. Không cấp `roles/viewer`/`roles/editor` tại project gốc để “chữa nhanh” lỗi 403; quyền rộng/kế thừa có thể làm lộ bảng private.
5. Kiểm tra permission từ **org → folder → project → dataset → table/view**, cộng row policies, column policies, masking và perimeter.

## 4. Lab A — tạo miền Sales và một data product phân tích

Lab tạo hai datasets tách biệt trong DATA_PROJECT. Người thực thi là **platform/data engineer được ủy quyền** có khả năng bật API, tạo dataset/table/view và chạy query. Không trao những quyền này cho analyst chỉ để làm bài thử nghiệm.

### Bước 1 — chuẩn bị project và datasets

~~~bash
DATA_PROJECT="company-sales-lab"
QUERY_PROJECT="company-analytics-lab"
LOCATION="asia-southeast1"

# Hai project phải tồn tại, billing/API/permissions hợp lệ trước khi chạy.
gcloud services enable bigquery.googleapis.com --project="$DATA_PROJECT"
gcloud services enable bigquery.googleapis.com --project="$QUERY_PROJECT"

# Chỉ tạo datasets LAB nếu chưa có, không chạm dữ liệu production.
bq --location="$LOCATION" mk --dataset "$DATA_PROJECT:sales_private"
bq --location="$LOCATION" mk --dataset "$DATA_PROJECT:sales_public"
bq --location="$LOCATION" mk --dataset "$DATA_PROJECT:sales_rls_lab"

bq --location="$LOCATION" show "$DATA_PROJECT:sales_private"
bq --location="$LOCATION" show "$DATA_PROJECT:sales_public"
~~~

Đặt cùng location để view tham chiếu bảng nguồn; trong công ty thực tế có thể dùng project khác nhau cho từng miền, nhưng **không bắt buộc** một miền đúng bằng một project. Nên thêm dataset labels, owner, classification và retention policy thông qua IaC/cấu hình chuẩn của tổ chức.

### Bước 2 — tạo bảng nguồn riêng tư bằng GoogleSQL

Trong BigQuery Studio, chọn **DATA_PROJECT**, location `asia-southeast1`; thay `DATA_PROJECT` trong câu SQL bằng project ID thật:

~~~sql
-- Chỉ trong lab: CREATE OR REPLACE có thể xóa dữ liệu bảng cũ.
CREATE OR REPLACE TABLE `DATA_PROJECT.sales_private.orders` (
  order_id STRING NOT NULL,
  order_date DATE NOT NULL,
  region STRING NOT NULL,
  customer_id STRING NOT NULL,
  customer_email STRING,
  amount_minor INT64 NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL
)
PARTITION BY order_date
CLUSTER BY region
OPTIONS (
  description = 'Sales domain: order events, restricted dataset'
);

INSERT INTO `DATA_PROJECT.sales_private.orders` (
  order_id, order_date, region, customer_id, customer_email,
  amount_minor, currency, status
)
VALUES
  ('O-101', DATE '2026-11-18', 'APAC', 'C-01',
   'alice@example.test', 12500, 'USD', 'PAID'),
  ('O-102', DATE '2026-11-18', 'APAC', 'C-02',
   'bob@example.test', 5000, 'USD', 'PAID'),
  ('O-103', DATE '2026-11-18', 'EMEA', 'C-03',
   'carol@example.test', 8600, 'USD', 'PAID'),
  ('O-104', DATE '2026-11-18', 'EMEA', 'C-04',
   'dan@example.test', 2000, 'USD', 'REFUNDED'),
  ('O-105', DATE '2026-11-18', 'APAC', 'C-05',
   'eve@example.test', 9000, 'USD', 'CANCELLED'),
  ('O-106', DATE '2026-11-18', 'EMEA', 'C-06',
   'fay@example.test', 12000, 'USD', 'PAID');
~~~

Email `example.test` là dữ liệu giả. Production phải dùng dữ liệu tối thiểu, phân loại `customer_email` là **PII** và xử lý retention/consent. Dùng `INT64` theo **minor units** để tránh lỗi floating-point; nếu có nhiều đồng tiền, **không cộng trực tiếp USD với EUR**. Lab chỉ có USD.

### Bước 3 — kiểm tra chất lượng dữ liệu nguồn

~~~sql
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT order_id) AS distinct_orders,
  COUNTIF(amount_minor <= 0 OR amount_minor IS NULL) AS invalid_amounts,
  COUNTIF(currency != 'USD') AS unexpected_currency,
  COUNTIF(status = 'PAID') AS paid_orders,
  SUM(IF(status = 'PAID', amount_minor, 0)) AS paid_revenue_minor
FROM `DATA_PROJECT.sales_private.orders`;
~~~

Kết quả kỳ vọng: `row_count=6`, `distinct_orders=6`, `invalid_amounts=0`, `unexpected_currency=0`, `paid_orders=4`, `paid_revenue_minor=38100`. Việc một query trả đúng 6 hàng **không tự chứng minh** dữ liệu mới đầy đủ hay đúng nghiệp vụ; kiểm tra thêm freshness, schema contract, source batch ID, duplicate order events và refunds.

## 5. Lab B — công bố authorized view, không mở bảng raw

**Authorized logical view** cho phép Analytics chạy SQL đọc **chỉ những cột/hàng trong view** dù không có quyền `sales_private.orders`. Phải thực hiện **hai hành động riêng biệt**:

1. Tạo view trong dataset `sales_public` và cấp consumer quyền đọc **view hoặc dataset đó**.
2. **Ủy quyền view** trong **source dataset `sales_private`** để view được đọc bảng nguồn thay mặt consumer.

### Bước 1 — định nghĩa hợp đồng đầu ra và tạo view

~~~sql
CREATE OR REPLACE VIEW `DATA_PROJECT.sales_public.v_paid_daily`
OPTIONS (
  description = 'Sales product v1: paid USD revenue by UTC date and region'
)
AS
SELECT
  order_date AS sale_date,
  region,
  COUNT(*) AS paid_orders,
  SUM(amount_minor) AS revenue_minor
FROM `DATA_PROJECT.sales_private.orders`
WHERE status = 'PAID'
  AND currency = 'USD'
GROUP BY sale_date, region
HAVING COUNT(*) >= 2;

-- Producer, người có quyền dữ liệu gốc, kiểm tra:
SELECT sale_date, region, paid_orders, revenue_minor
FROM `DATA_PROJECT.sales_public.v_paid_daily`
ORDER BY region;
~~~

**Kết quả mong đợi**:

| sale_date | region | paid_orders | revenue_minor |
|---|---|---:|---:|
| 2026-11-18 | APAC | 2 | 17.500 |
| 2026-11-18 | EMEA | 2 | 20.600 |

Mục tiêu view là **chỉ công bố aggregate**, bỏ mọi `customer_id/email`, không cho drill down về từng giao dịch. `HAVING COUNT(*) >= 2` chỉ là **ngưỡng minh họa** giảm lộ nhóm có một người, **không bảo đảm ẩn danh**: nếu kết hợp nguồn khác, người tiêu thụ có thể suy ra thông tin; sản phẩm thật cần privacy assessment và tiêu chí group-size/k-anonymity hoặc privacy-preserving analytics phù hợp.

### Bước 2 — cấp quyền *view → source dataset*

Trong Google Cloud Console, chuyển sang **DATA_PROJECT → BigQuery → Dataset sales_private → Sharing → Authorize views**, chọn:

~~~text
DATA_PROJECT.sales_public.v_paid_daily
~~~

Thêm **đúng view** vào authorized views của `sales_private` rồi kiểm tra lại dataset access. **Không** cấp nhóm Analytics `dataViewer` trên `sales_private`. Đây là thao tác quyền quản trị nguồn của domain owner/platform team, không phải người dùng BI tự thực hiện.

> Có thể sử dụng BigQuery API hoặc `bq update --source ...` để duy trì access entry loại `view` dưới IaC. Khi sửa dataset ACL bằng JSON, phải **giữ nguyên toàn bộ các access entries cũ**; nếu viết đè danh sách, bạn có thể vô tình thu hồi hoặc mở quyền. Console đơn giản hơn cho lần học đầu.

**Authorized dataset** là biến thể cho phép **mọi views hiện tại và tương lai** trong dataset được ủy quyền truy cập source dataset. Cách này giảm cấu hình khi có rất nhiều views, nhưng tăng blast radius: người có quyền tạo/sửa views trong dataset đó có thể tạo luồng đọc dữ liệu ngoài dự định. Với một sản phẩm lab, **authorize đúng một view** là lựa chọn dễ kiểm toán hơn.

### Bước 3 — cấp quyền *consumer → view dataset* và *query project*

Sau khi đã tạo Google Group tồn tại thật và được phê duyệt, domain owner dùng BigQuery **GoogleSQL DCL**:

~~~sql
-- Chạy với danh tính có bigquery.datasets.update trên sales_public.
-- Thay email ví dụ bằng Google Group đã được quản trị thực tế.
GRANT `roles/bigquery.dataViewer`
ON SCHEMA `DATA_PROJECT`.sales_public
TO "group:analytics-revenue@example.com";
~~~

Platform/IAM team cấp quyền **tạo query job** cho chính group đó ở **QUERY_PROJECT**:

~~~bash
gcloud projects add-iam-policy-binding "$QUERY_PROJECT" \
  --member="group:analytics-revenue@example.com" \
  --role="roles/bigquery.jobUser"
~~~

**Không cần cấp `roles/bigquery.jobUser` trên DATA_PROJECT** nếu người tiêu thụ chạy job trong QUERY_PROJECT. Trong hệ thống nhiều data products, có thể cấp `dataViewer` trên **view riêng** thay vì cả `sales_public` để ít lộ metadata/data của các views khác.

### Bước 4 — kiểm chứng bằng chính danh tính người tiêu thụ

Sau khi Google Group/IAM đã có hiệu lực, đăng nhập CLI bằng **một account thật thuộc group Analyst**, hoặc chạy Java/BI bằng runtime service account thực sự được cấp quyền:

~~~bash
# Chạy query job trên QUERY_PROJECT; đọc view ở DATA_PROJECT.
# Đặt project query explicitly, cùng location với hai datasets.
bq --project_id="$QUERY_PROJECT" --location="$LOCATION" \
  query --use_legacy_sql=false \
  'SELECT sale_date, region, paid_orders, revenue_minor
   FROM `DATA_PROJECT.sales_public.v_paid_daily`
   ORDER BY region'

# Query bảng nguồn phải bị từ chối đối với consumer.
bq --project_id="$QUERY_PROJECT" --location="$LOCATION" \
  query --use_legacy_sql=false \
  'SELECT customer_email FROM `DATA_PROJECT.sales_private.orders` LIMIT 1'
~~~

Trong lệnh `bq` trên, thay literal `DATA_PROJECT` bằng **project ID thật** trong câu query. **Đừng thử giả làm người khác bằng cách sửa biến email**; kiểm thử chỉ có ý nghĩa khi dùng identity thực (user hoặc SA) được Google Cloud xác thực.

**Hai phép thử chấp nhận:**

- Query **authorized view thành công** và đúng hai nhóm tổng hợp.
- Query trực tiếp **sales_private.orders bị `Access Denied`**. Nếu query raw thành công, tìm role kế thừa hoặc binding cũ ở project/folder/org/table; **không coi lab đạt**.

### Bước 5 — kiểm thử thu hồi quyền

Trong môi trường riêng biệt, owner dùng DCL `REVOKE roles/bigquery.dataViewer ON SCHEMA ...` đối với group thử nghiệm, sau đó consumer chạy lại query view. Kỳ vọng bị từ chối khi IAM đã hiệu lực. Nếu chạy query raw vẫn thành công, đó là vấn đề ở **source IAM**, không phải việc thu hồi view. Đừng xóa authorization của view khi còn người dùng hợp lệ hoặc các dashboard đang dựa vào nó.

## 6. Lab C — row-level security theo vùng, đúng phạm vi

**Row-level security (RLS)** giúp một số người dùng được đọc **cùng một bảng**, nhưng chỉ thấy các hàng thỏa điều kiện. Nếu nhóm APAC chỉ được xem `region='APAC'` và nhóm EMEA chỉ được xem `region='EMEA'`, RLS thích hợp hơn việc tạo rất nhiều bảng sao chép.

**Để tránh cấp nhầm quyền PII**, lab RLS dùng **dataset `sales_rls_lab` riêng**, không gắn role Data Viewer trên `sales_private`. Bảng thử nghiệm cũng chỉ chứa các cột cần thiết.

### Bước 1 — tạo bảng dùng để kiểm thử

~~~sql
-- Chạy với domain owner đã có quyền đọc sales_private.
CREATE OR REPLACE TABLE `DATA_PROJECT.sales_rls_lab.regional_orders`
PARTITION BY order_date
CLUSTER BY region
AS
SELECT order_id, order_date, region, amount_minor, status
FROM `DATA_PROJECT.sales_private.orders`;
~~~

**Quan trọng:** đây là dữ liệu được sao chép trong lab để tập quyền rõ ràng; trong production, việc tạo thêm bản sao còn phát sinh lưu trữ, retention và trách nhiệm xóa/đồng bộ. Bảng mới **chưa được RLS bảo vệ** ngay sau CTAS. **Đừng cấp analyst quyền đọc trước khi tạo policies**.

### Bước 2 — tạo row access policies

Các Google Groups phải tồn tại thật trước khi chạy; thay miền `example.com` bằng domain tổ chức:

~~~sql
CREATE ROW ACCESS POLICY apac_only
ON `DATA_PROJECT.sales_rls_lab.regional_orders`
GRANT TO ('group:sales-apac@example.com')
FILTER USING (region = 'APAC');

CREATE ROW ACCESS POLICY emea_only
ON `DATA_PROJECT.sales_rls_lab.regional_orders`
GRANT TO ('group:sales-emea@example.com')
FILTER USING (region = 'EMEA');
~~~

Người dùng không thuộc nhóm được cấp row access policy **không nhìn thấy các hàng**. Người có **hai policies** phù hợp sẽ nhìn thấy **hợp (OR)** của những hàng mà từng policy cho phép, không phải chỉ phần giao. Data Owner/Admin có thể sửa hoặc quản trị policy, vì vậy **phải dùng danh tính consumer thông thường** để xác nhận hành vi đọc.

### Bước 3 — cấp Data Viewer trên dataset kiểm thử

~~~sql
GRANT `roles/bigquery.dataViewer`
ON SCHEMA `DATA_PROJECT`.sales_rls_lab
TO "group:sales-apac@example.com",
   "group:sales-emea@example.com";
~~~

Mỗi tester còn cần `roles/bigquery.jobUser` ở **QUERY_PROJECT** (hoặc project chạy query mà họ được phép dùng). Từ hai danh tính thật:

~~~sql
SELECT order_id, region, amount_minor, status
FROM `DATA_PROJECT.sales_rls_lab.regional_orders`
ORDER BY order_id;
~~~

**Kỳ vọng theo group đơn lẻ:** APAC thấy `O-101`, `O-102`, `O-105` (3 dòng); EMEA thấy `O-103`, `O-104`, `O-106` (3 dòng). Hai nhóm cùng lúc có thể thấy 6 dòng. Nếu nhận 0 dòng, phân biệt giữa **RLS không cấp policy** và **IAM chặn cả table/query job**. Nếu nhận 6 dòng khi chỉ thuộc một group, kiểm tra policies khác như `FILTER USING (TRUE)`, quyền quá rộng và quyền kế thừa.

### Bước 4 — kiểm tra và quản lý chính sách

~~~sql
-- Cần quyền xem row policy metadata (ví dụ BigQuery Security Admin).
SELECT
  table_name,
  row_access_policy_name,
  filter_predicate,
  creation_time,
  last_modified_time
FROM `DATA_PROJECT.sales_rls_lab.INFORMATION_SCHEMA.ROW_ACCESS_POLICIES`
WHERE table_name = 'regional_orders'
ORDER BY row_access_policy_name;
~~~

`ROW_ACCESS_POLICIES` hiển thị **tên, điều kiện lọc và metadata** nhưng **không liệt kê danh tính grantees**. Muốn kiểm toán ai có quyền, dùng Console/bq/API để đọc IAM policies của từng row access policy. Không coi metadata row filter là bằng chứng đầy đủ về principal hiệu lực.

**Phòng tránh rò rỉ:** chỉ định RLS **trên bảng thật** khi cần chia sẻ quyền đọc từng hàng. Nếu bạn tạo một authorized view trên source table đã có RLS, **đánh giá tương tác quyền source và view** thay vì mặc định view bỏ qua mọi row policy. Ứng dụng Java phải bảo vệ theo tenant/owner ở cấp nghiệp vụ dù BigQuery đã lọc rows.

## 7. Column-level access, masking và kiểm soát dữ liệu PII

RLS chỉ kiểm soát **hàng**, không tự ẩn cột `customer_email` đối với nhóm đã được xem hàng đó. Có ba phương án thường gặp:

| Nhu cầu | Công cụ | Lưu ý |
|---|---|---|
| Analyst chỉ cần tổng hợp | **Authorized view** bỏ PII và nhóm dữ liệu | Đơn giản, dễ giới hạn mục đích sử dụng |
| Một nhóm được đọc bảng nhưng không đọc email/SSN | **Column-level access control** qua policy tags hoặc data governance tags | Quyền cột được kiểm tra cả khi truy vấn qua view có dùng cột |
| Analyst cần một dạng email/ID không phải raw value | **BigQuery data masking policies** | Masked Reader thấy giá trị đã biến đổi theo policy |

### Quy trình policy tag/masking

1. Domain steward và security team phân loại `customer_email` thành **PII/Confidential** và định nghĩa ai được xem bản gốc, ai được xem bản mask.
2. Tạo **policy tag taxonomy** ở location phù hợp; áp policy tag vào cột `sales_private.orders.customer_email`.
3. **Enforce column-level access** bằng data policies; người cần raw data được cấp **Data Catalog Fine-Grained Reader** ở tag tương ứng, ngoài quyền truy cập bảng.
4. Nếu cần dữ liệu mask, tạo **data masking policy** cho tag (ví dụ NULL/default/hash theo quy tắc hỗ trợ), rồi cấp **BigQuery Masked Reader** ở đúng data policy.
5. Dùng ít nhất ba identities để thử: người có raw access; người chỉ có masked access; người không có cả hai. Xác minh phép đọc cả qua SQL trực tiếp lẫn những views được phép.

**Không viết thông tin thật vào tag tên hoặc mô tả.** Metadata classification không phải một kho lưu PII. Policy tags, resource tags và Knowledge Catalog glossary/aspects là các khái niệm khác: **gắn một business term “email khách hàng” không tự tạo IAM policy**. Cũng không nên coi hàm hash thông thường là đã ẩn danh tuyệt đối; có thể suy ngược bằng dictionary/correlation.

**Khi nào dùng policy tag thay authorized view?** Nếu nhóm cần hàng/chi tiết của bảng nhưng cột nhạy cảm phải được bảo vệ nhất quán trên nhiều queries, policy tags tốt hơn việc yêu cầu từng tác giả view tự nhớ bỏ email. Nếu consumer chỉ cần doanh thu theo ngày, **không cần cấp quyền bảng gốc rồi lại dùng column masking để sửa quyền quá rộng**: tiếp tục dùng authorized aggregate view.

## 8. Data contract: hợp đồng phân tích giữa Sales và Analytics

IAM trả lời “ai được truy cập”; **data contract** trả lời “được sử dụng dữ liệu nào, ý nghĩa gì, độ mới bao nhiêu và làm thế nào biết dữ liệu đúng”. Ví dụ contract v1 cho `v_paid_daily`:

| Trường | Hợp đồng minh họa |
|---|---|
| Tên / owner | `sales.paid_daily.v1` — Sales domain owner |
| Consumers | Analytics revenue group và các dashboards đã phê duyệt |
| Schema | `sale_date DATE`, `region STRING`, `paid_orders INT64`, `revenue_minor INT64` |
| Ngữ nghĩa | Chỉ orders `status='PAID'` và `currency='USD'`; tiền tính theo minor units |
| Scope | Aggregate theo ngày UTC và vùng; có ngưỡng nhóm `COUNT(*) >= 2` |
| Freshness | Dữ liệu ngày D phải sẵn sàng trước 08:00 ngày D+1 (ví dụ) |
| Quality | Không duplicate `(sale_date, region)`; số tiền không âm; reconciliation với source |
| Sensitivity | Không phát trực tiếp PII; aggregate vẫn phải privacy-review |
| Change policy | Thêm cột tương thích có thông báo; đổi nghĩa metric phải tạo v2 |
| Access/incident | Phê duyệt bởi owner, quyền có thời hạn, contact và runbook SLA |

**Schema evolution:** thêm một cột nullable vào view có thể không phá một số client, nhưng thay `revenue_minor` từ cents sang dollars dù tên không đổi là **breaking semantic change**. Nếu cần điều chỉnh quy tắc hoàn tiền, viết `v_paid_daily_v2`, so sánh song song và chuyển dashboard có kiểm soát.

### Kiểm thử SQL chất lượng

~~~sql
-- Kiểm tra tính duy nhất của khóa đầu ra.
SELECT sale_date, region, COUNT(*) AS duplicates
FROM `DATA_PROJECT.sales_public.v_paid_daily`
GROUP BY sale_date, region
HAVING COUNT(*) > 1;

-- Kiểm tra số liệu có bất thường theo contract.
SELECT *
FROM `DATA_PROJECT.sales_public.v_paid_daily`
WHERE paid_orders < 2 OR revenue_minor < 0;

-- Đối soát source vs view trên các nhóm có đủ 2 đơn PAID.
WITH expected AS (
  SELECT order_date AS sale_date, region,
         COUNT(*) AS paid_orders, SUM(amount_minor) AS revenue_minor
  FROM `DATA_PROJECT.sales_private.orders`
  WHERE status = 'PAID' AND currency = 'USD'
  GROUP BY sale_date, region
  HAVING COUNT(*) >= 2
),
actual AS (
  SELECT sale_date, region, paid_orders, revenue_minor
  FROM `DATA_PROJECT.sales_public.v_paid_daily`
)
SELECT * FROM expected
EXCEPT DISTINCT
SELECT * FROM actual;
~~~

Kỳ vọng ba truy vấn trên **không có hàng**. Query reconciliation chỉ chạy bằng **domain owner/quality service account được cấp quyền đọc source**, không trao nó cho analyst như một cách “test dataset”. Với dữ liệu liên tục thay đổi, phải so ở cùng snapshot/timestamp hoặc cửa sổ batch đã chốt; hai query khác thời điểm có thể tạm lệch.

## 9. Knowledge Catalog: giúp người dùng hiểu và tìm được data product

Trong Google Cloud hiện hành, sản phẩm **Knowledge Catalog** (trước đây là **Dataplex Universal Catalog**) hỗ trợ khám phá tài sản dữ liệu, business glossary, metadata **aspects**, lineage, data quality và quản lý data products. **Data Catalog policy tags** vẫn là khái niệm được dùng trong cơ chế column-level security của BigQuery; đừng nhầm tên hai sản phẩm chỉ vì cùng liên quan đến metadata.

~~~mermaid
flowchart LR
  A["BigQuery sales_private.orders"] --> L["Lineage: source → transform → view"]
  L --> V["BigQuery sales_public.v_paid_daily"]
  G["Glossary: doanh thu đã thanh toán"] --> V
  M["Aspect: owner, classification, SLA"] --> V
  D["Data quality: completeness, validity"] --> V
  V --> P["Data product: Sales Revenue v1"]
  P --> C["Analytics / BI consumer"]
~~~

### Metadata tối thiểu nên công bố

| Thuộc tính | Ví dụ | Ai duy trì |
|---|---|---|
| Display name | Sales Paid Revenue Daily | Data product owner |
| Technical asset | `DATA_PROJECT.sales_public.v_paid_daily` | Data engineer |
| Business term | “Doanh thu đã thanh toán” | Sales steward |
| Description | Chỉ PAID/USD, loại refund/cancelled, daily UTC | Sales owner |
| Sensitivity | Internal aggregate; không chứa email, nhưng có privacy review | Security + steward |
| Freshness / SLA | D+1 trước 08:00 | Pipeline owner |
| Lineage | orders → paid daily view → dashboard | Pipeline/catalog integration |
| Quality score | Số kiểm tra đạt, ngày chạy gần nhất | Quality owner |
| Contact / runbook | Nhóm Sales data product support | Operations |

**Business glossary** thống nhất thuật ngữ: “đơn thanh toán” là gì, có trừ refund chưa, ngày được xác định theo timezone nào, doanh thu có thuế hay không. Một tài sản có thể liên kết tới thuật ngữ qua **glossary terms**. **Aspects** gắn metadata có cấu trúc như owner, classification, contract version và chất lượng. **Lineage** biểu diễn nguồn/phụ thuộc để biết dashboard nào chịu ảnh hưởng khi thay bảng.

Trong **Knowledge Catalog → Data products**, producer có thể nhóm tài sản đã được kiểm duyệt cùng hợp đồng refresh và thông tin onboarding; consumer tìm và **yêu cầu quyền** theo workflow được hỗ trợ. **Tìm thấy data product không có nghĩa đã có quyền đọc BigQuery**: quy trình yêu cầu phải tạo/phê duyệt IAM hoặc data-product access group theo chính sách; cần test lại quyền thực tế.

### Áp dụng lên lab bằng Console

1. Mở **Google Cloud Console → Knowledge Catalog**, tìm `sales_public.v_paid_daily` (API/permissions phải được bật theo tổ chức).
2. Thêm business description, liên kết thuật ngữ “paid revenue”, owner/contact và **aspects** metadata phù hợp.
3. Ghi vào data product contract: `sale_date` theo UTC, `revenue_minor` là cents USD, ngưỡng nhóm ≥2, SLA D+1 08:00.
4. Kết nối/quan sát lineage từ bảng `orders` tới view; nếu pipeline là Java/SQL tùy biến không tự hiện đầy đủ lineage, bổ sung metadata/lineage bằng cơ chế được hỗ trợ.
5. Tạo **data quality scan** hoặc rules trên bảng và kiểm tra kết quả, sau đó publish scorecard vào catalog nếu được phép.

**Giới hạn:** tính năng metadata tự động, data products, access requests và giao diện có thể khác nhau theo vùng, quyền, edition và rollout; owner phải xác nhận availability trước khi dựa vào làm điều kiện production.

## 10. Data quality scans và tín hiệu đáng tin cậy

Ngoài kiểm thử SQL thủ công, **Knowledge Catalog auto data quality** (trước đây thuộc Dataplex) có thể chạy scans trên bảng BigQuery, áp quy tắc về tính đầy đủ, định dạng, tập giá trị, uniqueness hoặc SQL tùy chỉnh. Đây là **kiểm soát chất lượng**, không phải quyền truy cập hay công cụ sửa dữ liệu tự động.

| Quy tắc | Ví dụ cho `orders` | Hành động nếu sai |
|---|---|---|
| Completeness | `order_id`/`order_date` không NULL | Chặn publish, gửi quarantine |
| Uniqueness | Một `order_id` không xuất hiện nhiều bản không hợp lệ | Kiểm tra CDC/producer retry |
| Validity | `amount_minor > 0` cho PAID | Quarantine và đối soát payment |
| Valid values | `currency` thuộc tập cho phép; `status` theo enum | Version hóa schema/contract |
| Freshness | Có dữ liệu ngày hôm trước trước 08:00 | Alert ingest owner |
| Reconciliation | Tổng revenue view khớp source trong kỳ chốt | Không phát hành dashboard sai |

Chạy scan có thể phát sinh chi phí xử lý/BigQuery; identity thực thi cần **đọc đúng bảng, quyền data scan và quyền liên quan**. Muốn publish kết quả scorecard lên Knowledge Catalog còn cần permissions cập nhật metadata; không cần cấp `roles/owner`.

Lệnh **chỉ chạy scan đã được owner tạo trước**:

~~~bash
gcloud dataplex datascans run sales-orders-quality \
  --project="$DATA_PROJECT" \
  --location="$LOCATION"
~~~

Lệnh này **không tự tạo** scan `sales-orders-quality`. Trong Console, cấu hình scope toàn bảng hoặc incremental theo `order_date`, rules, schedule, IAM, notifications và chỗ lưu kết quả trước; hãy thử trước bằng dataset lab. **Quality pass không chứng minh dữ liệu được phép chia sẻ**: còn phải kiểm tra privacy policy và access approvals.

### Vì sao glossary và policy phải đi cùng

Một data product ghi “Chỉ dữ liệu tổng hợp” nhưng view vô tình thêm `customer_email` là **breaking change về an ninh**, dù query vẫn chạy và freshness vẫn đạt. Thay đổi schema/view phải đi qua **code review** từ producer, steward và security team, cùng test quyền của từng loại consumer.

## 11. Chia sẻ nhiều data products: authorized datasets và BigQuery sharing

**Authorized view** phù hợp khi một số views cần quyền đọc dữ liệu nguồn. Khi có hàng trăm views, có thể dùng **authorized dataset** để ủy quyền *toàn bộ views hiện tại và tương lai* trong một dataset — nhưng cần quản rất chặt **ai được tạo/sửa view trong dataset được ủy quyền**.

**BigQuery sharing** (tên trước đây **Analytics Hub**) là nền tảng **data exchange/listing/subscription**, phù hợp khi producer muốn công bố dataset qua cơ chế khám phá/subscribe có kiểm soát, trong nội bộ hoặc giữa các tổ chức. Consumer có thể tạo **linked dataset** thay vì sao chép dữ liệu cho mỗi project; không nên tự hiểu đây là cấp quyền đọc PII cho mọi subscriber. Các lớp IAM, policy tags, row filtering và governance của nguồn vẫn phải được thiết kế/phê duyệt theo khả năng được hỗ trợ.

| Hình thức | Trường hợp phù hợp | Mặt trái cần quản trị |
|---|---|---|
| **Dataset/table IAM** | Nhóm được phép đọc trực tiếp dữ liệu chi tiết | Quyền rộng, thiếu mục đích giới hạn |
| **Authorized view** | Chia sẻ một tập columns/rows/aggregates cụ thể | Phải review SQL và source authorization |
| **Authorized dataset** | Nhiều authorized views chung owner | View mới có thể kế thừa đường đọc nguồn |
| **Row policies** | Nhiều nhóm cùng bảng nhưng mỗi nhóm chỉ thấy một phần rows | Union-of-policies, hiệu năng và kiểm toán grantees |
| **Column tags/masking** | Quản trị PII nhất quán theo cột trên nhiều truy vấn | Taxonomy/data policies, group/role semantics |
| **BigQuery sharing** | Công bố theo data exchange, publisher/subscriber workflow | Listing/subscription/linked datasets và IAM phải kiểm soát |
| **Knowledge Catalog data products** | Discovery, glossary, contract, access request | Metadata **không thay** quyền BigQuery thực tế |

**Đặt lựa chọn đơn giản trước:** đối với dashboard chỉ cần doanh thu tổng hợp, authorized view của lab đủ dễ hiểu, ít thay đổi và dễ kiểm thử. Không cần tạo data exchange hoặc hệ thống data mesh phức tạp chỉ để cho một nhóm xem hai số liệu.

## 12. Java Cloud Run: chạy query bằng danh tính consumer

Một dịch vụ Java 17+ đọc doanh thu qua BigQuery client bằng **ADC** của Cloud Run runtime service account. Runtime SA chỉ cần `roles/bigquery.jobUser` ở **QUERY_PROJECT** và `roles/bigquery.dataViewer` trên **sales_public/view**. Đừng dùng key JSON của Sales producer hoặc IAM impersonation rộng để chạy dashboard.

Trong Maven/Gradle project dùng Google Cloud Java libraries phù hợp, thêm `com.google.cloud:google-cloud-bigquery`. Ví dụ sau tạo job ở đúng project/location, parameterize ngày và **chỉ truy vấn authorized view**:

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.BigQueryOptions;
import com.google.cloud.bigquery.FieldValueList;
import com.google.cloud.bigquery.Job;
import com.google.cloud.bigquery.JobId;
import com.google.cloud.bigquery.JobInfo;
import com.google.cloud.bigquery.QueryJobConfiguration;
import com.google.cloud.bigquery.QueryParameterValue;
import com.google.cloud.bigquery.TableResult;
import java.util.UUID;

public final class RevenueReader {
    public static void main(String[] args) throws InterruptedException {
        String queryProject = "company-analytics-lab";
        String dataProject = "company-sales-lab";
        String location = "asia-southeast1";
        BigQuery bigquery = BigQueryOptions.newBuilder()
            .setProjectId(queryProject).build().getService();

        // Table identifier do server config kiểm soát, không lấy từ HTTP input.
        String sql = """
            SELECT sale_date, region, paid_orders, revenue_minor
            FROM `DATA_PROJECT.sales_public.v_paid_daily`
            WHERE sale_date BETWEEN @start_date AND @end_date
            ORDER BY sale_date, region
            """.replace("DATA_PROJECT", dataProject);

        QueryJobConfiguration query = QueryJobConfiguration.newBuilder(sql)
            .addNamedParameter("start_date",
                QueryParameterValue.date("2026-11-18"))
            .addNamedParameter("end_date",
                QueryParameterValue.date("2026-11-18"))
            .setUseLegacySql(false)
            .setMaximumBytesBilled(500_000_000L)
            .build();

        JobId jobId = JobId.newBuilder()
            .setProject(queryProject)
            .setLocation(location)
            .setJob("sales_view_" + UUID.randomUUID())
            .build();
        Job job = bigquery.create(JobInfo.newBuilder(query)
            .setJobId(jobId).build()).waitFor();

        if (job == null || job.getStatus().getError() != null) {
            throw new IllegalStateException(
                "BigQuery job failed or no longer exists");
        }
        TableResult result = job.getQueryResults();
        for (FieldValueList row : result.iterateAll()) {
            System.out.printf("%s | %s | %d | %d%n",
                row.get("sale_date").getStringValue(),
                row.get("region").getStringValue(),
                row.get("paid_orders").getLongValue(),
                row.get("revenue_minor").getLongValue());
        }
    }
}
~~~

Ví dụ là **console app tối thiểu**, chưa có HTTP endpoint, input validation, timeout/cancellation, pagination, metrics hoặc authorization theo người dùng cuối. Với Cloud Run triển khai thực:

- Gắn **runtime SA** riêng cho service, không dùng default service account có quyền rộng.
- Cloud Run là một lớp bảo mật HTTP; **chỉ vì API Java chạy dưới SA được quyền view không có nghĩa mọi caller HTTP đều được phép xem dashboard**.
- Giới hạn truy vấn bằng date range/query parameters, rate limits và budget; không nối user-supplied table names thành dynamic SQL.
- Truy vấn xuyên project có billing ở QUERY_PROJECT; theo dõi job ID, P95 latency, bytes billed và Cloud Logging mà không log PII/token.
- Dùng Google Groups/IAM hoặc mô hình workload identity thay vì key files trong container; audit runtime principal và quyền source/view định kỳ.

## 13. Theo dõi quyền, chất lượng, chi phí và dấu vết thay đổi

Một chương trình governance chỉ tồn tại trên slide sẽ không phát hiện được **quyền kế thừa mới**, **view thay SQL** hoặc **báo cáo sai số liệu sau backfill**. Đặt giám sát cho cả dữ liệu và control plane:

| Tín hiệu | Câu hỏi phải trả lời | Chủ sở hữu |
|---|---|---|
| BigQuery IAM/dataset ACL | Có ai được quyền đọc `sales_private` ngoài owner? | IAM/Sales owner |
| Authorized views/datasets | Những views nào được source cho đọc? Có view mới bất ngờ? | Sales owner |
| Row access policies | Bộ lọc hiện tại, các grantees, có `TRUE` hoặc chồng quyền? | Security/data steward |
| Policy tags/data policies | Cột PII nào được bảo vệ, ai có Fine-Grained/Masked Reader? | Privacy/security |
| Query jobs metadata | Ai chạy jobs, dùng project nào, bytes processed/billed? | SRE/FinOps |
| Data quality | DQ pass rate, duplicate IDs, missing dates, reconcile mismatch | Data engineering |
| Freshness | Bản dữ liệu D có trước 08:00 D+1? | Producer |
| Catalog metadata/lineage | Owner, SLA, downstream dashboards còn chính xác? | Data steward |
| Cloud Audit Logs | Ai tạo/thay grants, view SQL, row policies, dataset settings? | Security/SRE |
| Billing | Query/storage/scan/metadata/governance costs có vượt budget? | FinOps |

### BigQuery query jobs audit

~~~sql
-- Chạy tại đúng location, ví dụ asia-southeast1.
-- Chỉ cho người được quyền xem jobs toàn project.
SELECT
  creation_time,
  job_id,
  user_email,
  project_id,
  total_bytes_processed,
  total_bytes_billed,
  total_slot_ms,
  error_result
FROM `QUERY_PROJECT.region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND job_type = 'QUERY'
ORDER BY creation_time DESC
LIMIT 50;
~~~

**Đọc metadata jobs toàn project có thể tiết lộ SQL, principal và pattern sử dụng nhạy cảm**. Không cấp quyền xem `JOBS_BY_PROJECT` toàn bộ cho bất kỳ analyst; với người dùng tự xem query của mình, dùng `JOBS_BY_USER`/job API theo quyền. Bật billing budgets và cảnh báo theo labels/project/owner; tránh dùng một query không giới hạn bytes chỉ để chạy kiểm tra thường xuyên.

### Chi phí phân tách

~~~text
DATA_PROJECT:
  BigQuery table storage, view metadata
  + ingestion/load, source DML, quality scans/lineage metadata
QUERY_PROJECT:
  query compute (on-demand bytes hoặc reservations/slots)
  + Java Cloud Run/API workloads, dashboard refresh
Hạ tầng chung:
  Cloud Logging/Monitoring, networking, optional Catalog features
~~~

**Authorized view không tự sao chép dữ liệu**, nhưng truy vấn view vẫn xử lý bảng gốc và có thể quét bytes. Row-level policies và masking cũng có tác động chi phí/hiệu năng tùy query. Việc dùng riêng QUERY_PROJECT cho chargeback không thay quyền sở hữu DATA_PROJECT và không tự giới hạn chi phí — cần quotas, budgets, maximum bytes billed, query validation và giám sát.

## 14. Runbook khi người dùng không xem đúng dữ liệu

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| `Access Denied: User does not have permission to create jobs` | Thiếu `roles/bigquery.jobUser` tại **QUERY_PROJECT** | Job project, IAM hiệu lực của caller |
| `Access Denied` trên `sales_public.v_paid_daily` | Thiếu Data Viewer trên view/dataset | Consumer group/SA, dataViewer bindings |
| View có quyền nhưng query bị từ chối ở bảng nguồn | Chưa authorize view trong `sales_private` hoặc source permission đã đổi | Source dataset Sharing → Authorized views |
| Analyst đọc được `customer_email` trong raw | Role Data Viewer kế thừa từ project/folder/org/table hoặc role quá rộng | Effective IAM, project/folder/org policy |
| View trả ít/không có rows | `HAVING COUNT(*)>=2`, dữ liệu chưa được nạp, policy nguồn hoặc SQL khác contract | Đối soát bằng domain owner identity |
| APAC tester thấy cả EMEA | Có policy thứ hai với OR/TRUE, quyền override hoặc đang dùng admin identity | Row policy list/grantees, effective role |
| APAC tester không thấy dòng nào | Không thuộc group, policy chưa propagate, thiếu table Data Viewer hoặc không có matching rows | Group membership và policies/SQL |
| Column PII đọc raw dù không mong muốn | Taxonomy chưa enforce, tag chưa gắn cột, Fine-Grained Reader bị cấp rộng | Policy tag/data policy và quyền IAM |
| Masked reader bị từ chối | Chưa có masking data policy hoặc Masked Reader chưa gắn đúng policy | Data policy IAM, column tag |
| Có quyền IAM nhưng job bị perimeter violation | VPC Service Controls ingress/egress hoặc org policy | Perimeter logs, project boundaries |
| Job báo `Location mismatch` | Source/view/query job ở locations không tương thích | Dataset locations, job location |
| Query đột nhiên đắt | Dashboard mất partition filter, view SQL đổi, query quét rộng | Job metadata, bytes/slot-ms, version view |
| Catalog tìm thấy product nhưng query không chạy | Metadata/discovery không phải BigQuery IAM | Access request approval và bindings thực |
| Dashboard sai số sau backfill | Source CDC/dedup thay đổi hoặc contract đổi nghĩa | Quality checks, lineage, snapshot, owner |

**Thứ tự xử lý lỗi truy cập:** xác nhận danh tính người dùng → query project → jobUser → view/table Data Viewer → source authorization → RLS/column/masking → location/perimeter. Đừng sửa IAM bằng việc cấp `roles/owner` hoặc mở source dataset chỉ để vượt một lỗi 403. **Thứ tự xử lý sai dữ liệu:** kiểm tra contract → source snapshot → SQL view → group suppression/row policy → pipeline/quality → dashboard.

## 15. Đưa data product vào production mà không lộ dữ liệu

1. **Định nghĩa miền:** owner/steward, glossary, mục đích sử dụng, phân loại PII, dữ liệu đầu ra và thời hạn lưu trữ.
2. **Project/dataset design:** tách nguồn private và lớp publish; xác minh location, Shared VPC/CMEK/VPC SC nếu tổ chức dùng.
3. **Data contract và SQL review:** chốt metric semantics, timezone, tiền tệ, freshness, schema version; bổ sung unit tests.
4. **Security review:** cấp quyền đúng group/SA trên **đúng source/view/query project**, không sử dụng Project Viewer/Editor để thay kiểm soát dataset.
5. **Authorize view:** chủ sở hữu bảng nguồn cho view quyền đọc; test positive và **negative** với identity thật.
6. **RLS/masking khi cần:** áp trên bảng/columns cụ thể, kiểm tra tương tác với authorized views và nhóm đa vai trò.
7. **Metadata và DQ:** đăng ký product trong Knowledge Catalog; glossary, owner, lineage, quality rules, scorecard và notifications.
8. **Canary:** chuyển một dashboard staging sang view mới, kiểm tra kết quả, P95 latency, bytes billed và người được phép truy cập.
9. **Chuyển production:** cập nhật catalog, access contract và alert owner; giới hạn quyền cấp tạm theo hạn sử dụng/review định kỳ.
10. **Rollback:** đổi dashboard trở lại view/version cũ đã phê duyệt; **không xóa nguồn hoặc gỡ IAM tràn lan** khi các consumer khác còn đang dùng; xử lý sự cố lộ dữ liệu như security incident.

### Thay đổi SQL view là thay đổi sản phẩm

Khi `v_paid_daily` cần bổ sung cột `store_id`, một nhóm nhỏ có thể làm lộ thông tin theo cửa hàng. Nếu đổi `COUNT(*) >= 2` thành `>= 1`, quyền xem dữ liệu **vẫn là cùng view** nhưng privacy guarantee đã khác. Phải dùng review của domain owner/steward, test data disclosure và hợp đồng phiên bản — IAM không tự kiểm duyệt ý nghĩa SQL.

## 16. Checklist kiểm chứng trước bàn giao

- [ ] Domain owner và steward có tên, trách nhiệm, contact/on-call.
- [ ] Dữ liệu raw/sensitive và published analytics nằm trong datasets có quyền **khác nhau**.
- [ ] DATA_PROJECT và QUERY_PROJECT có location/billing/project ownership rõ.
- [ ] Consumer chỉ có `jobUser` ở query project và `dataViewer` trên resource được công bố.
- [ ] Authorized view được **source dataset** cấp quyền; không grant consumer trực tiếp vào source.
- [ ] Có thử nghiệm **query view = OK** và **query PII raw = DENIED** với danh tính thật.
- [ ] RLS testing dùng dataset riêng hoặc bảng được bảo vệ sẵn **trước** khi cấp viewer.
- [ ] Policy tags/masking dùng đúng trường nhạy cảm và test raw/masked/denied.
- [ ] Có kiểm tra quyền kế thừa ở org/folder/project; không để Editor/Owner quá rộng.
- [ ] Data contract nêu metric, timezone, currency, schema version, freshness và quality.
- [ ] Knowledge Catalog metadata có glossary/owner/lineage hoặc quy trình cập nhật tương ứng.
- [ ] DQ checks, reconciliation và alerts chạy với **quality SA** có quyền riêng.
- [ ] Dashboard Java/BI dùng ADC và service account ít quyền; không có credential JSON trong code.
- [ ] Có audit logs, query jobs/billing dashboard và cơ chế duyệt/thu hồi quyền định kỳ.
- [ ] Rollout/backfill/revoke có kế hoạch và không khiến dashboard khác mất truy cập ngoài dự kiến.

## 17. Bài tập vận dụng

**Bài 1 — Xác định miền.** Một công ty có đơn hàng, thông tin khách hàng, tồn kho và báo cáo doanh thu. Vẽ 4 miền, nêu owner/steward/producer/consumer và định nghĩa ít nhất hai data products với hợp đồng dữ liệu.

**Bài 2 — Quy hoạch dự án.** Thiết kế `sales-private`, `sales-public` và `analytics-query` như lab. Giải thích vì sao dataset private/public cần khác nhau, tại sao query project không cần Data Viewer trên source, và hậu quả khi người dùng có quyền kế thừa ở cấp folder.

**Bài 3 — IAM đúng scope.** Analyst được cấp `roles/bigquery.dataViewer` trên `sales_public` nhưng không tạo được query job. Chỉ ra permission còn thiếu, **project nào** cần cấp và vì sao không chọn `BigQuery Admin`.

**Bài 4 — Authorized view.** Tạo `v_paid_daily` theo lab và authorize nó tại `sales_private`. Với một consumer identity thật, chứng minh view trả hai dòng còn truy vấn `customer_email` từ bảng nguồn bị từ chối. Nếu source query thành công, bước tiếp theo là gì?

**Bài 5 — Row-level security.** Group APAC chỉ xem 3 rows, group EMEA chỉ xem 3 rows. Viết hai `CREATE ROW ACCESS POLICY` và giải thích vì sao người thuộc cả hai group có thể xem 6 rows.

**Bài 6 — Column masking.** Người dùng A được đọc email raw, B chỉ xem email mask, C không được đọc cột. Đề xuất taxonomy/tag, Fine-Grained Reader, Masked Reader và các phép test; nêu khác biệt với authorized view loại bỏ email hoàn toàn.

**Bài 7 — Hợp đồng dữ liệu.** Business đổi định nghĩa doanh thu từ “paid gross” sang “net of refunds” và yêu cầu chấp nhận EUR ngoài USD. Hãy liệt kê những thay đổi cần version hóa: schema, currency/FX, dashboard, glossary, data quality và privacy review.

**Bài 8 — Data quality.** Trên bảng nguồn xuất hiện một đơn có `order_id` trùng, `amount_minor` âm và pipeline trễ 3 giờ. Viết ba SQL quality assertions và mô tả quy trình quarantine, alert và ngăn publish product sai.

**Bài 9 — Catalog vs permissions.** Một analyst nhìn thấy “Sales Paid Revenue v1” trong Knowledge Catalog nhưng `SELECT` báo 403. Liệt kê các kiểm tra theo thứ tự từ access request approval, jobUser, dataViewer, authorized view tới project perimeter.

**Bài 10 — Java runtime.** Java Cloud Run trong QUERY_PROJECT cần đọc view thuộc DATA_PROJECT. Liệt kê tối thiểu hai IAM bindings, cách dùng ADC, query parameters, tránh user-supplied table name và nơi xem job/billing.

**Bài 11 — Audit quyền và chi phí.** Một team cấp `BigQuery Data Viewer` trên cả project Sales cho group Analysts để sửa một dashboard. Xây kế hoạch thu hồi, kiểm tra người phụ thuộc, thay bằng authorized view và dashboard theo dõi chi phí truy vấn.

**Bài 12 — Incident thay đổi view.** Producer vô tình thêm `customer_email` vào một view được authorize, còn consumer được xem view. Xây runbook: xác nhận phạm vi, ngăn truy cập, rollback view, truy vết audit/query jobs, đánh giá thông báo sự cố và thay đổi quy trình review.

## Tài liệu tham khảo chính thức

- [BigQuery IAM roles](https://cloud.google.com/bigquery/docs/access-control) — Job User, Data Viewer, Data Owner và scope.
- [Grant access to datasets](https://cloud.google.com/bigquery/docs/control-access-to-resources-iam) — role inheritance, dataset/table/view controls.
- [GoogleSQL GRANT/REVOKE](https://cloud.google.com/bigquery/docs/reference/standard-sql/data-control-language) — `GRANT roles/bigquery.dataViewer ON SCHEMA`.
- [Create authorized views](https://cloud.google.com/bigquery/docs/create-authorized-views) — tạo view và source authorization.
- [Authorized views](https://cloud.google.com/bigquery/docs/authorized-views) — quyền consumer/job project và tương tác security.
- [Authorized datasets](https://cloud.google.com/bigquery/docs/authorized-datasets) — chia sẻ một tập views và cảnh báo quyền sửa view.
- [Introduction to row-level security](https://cloud.google.com/bigquery/docs/row-level-security-intro) — bộ lọc hàng và hợp policy.
- [Manage row access policies](https://cloud.google.com/bigquery/docs/managing-row-level-security) — `CREATE ROW ACCESS POLICY`, IAM, audit.
- [ROW_ACCESS_POLICIES information schema](https://cloud.google.com/bigquery/docs/information-schema-row-access-policies) — xem điều kiện policy.
- [Column-level security](https://cloud.google.com/bigquery/docs/column-level-security) — policy tags, fine-grained read.
- [BigQuery data masking](https://cloud.google.com/bigquery/docs/column-data-masking) — masked data policies/readers.
- [Knowledge Catalog](https://cloud.google.com/knowledge-catalog/docs) — formerly Dataplex Universal Catalog, glossary/aspects/lineage.
- [Knowledge Catalog data products](https://cloud.google.com/knowledge-catalog/docs/data-products-overview) — product contract và access workflow.
- [Knowledge Catalog data quality](https://cloud.google.com/knowledge-catalog/docs/use-auto-data-quality) — scans, rules, quality metrics.
- [BigQuery sharing](https://cloud.google.com/bigquery/docs/analytics-hub-introduction) — formerly Analytics Hub; data exchange/listings/subscriptions.
- [JOBS_BY_PROJECT metadata](https://cloud.google.com/bigquery/docs/information-schema-jobs) — query auditing, cost.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) — query compute/storage và chọn mô hình tính phí.
