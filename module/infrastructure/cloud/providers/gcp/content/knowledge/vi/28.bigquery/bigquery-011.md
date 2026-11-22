# Row-level security, column-level security và data masking trong BigQuery

Một công ty có bảng `orders` chứa đơn hàng của nhiều khu vực, địa chỉ email khách hàng và doanh thu. Nhóm phân tích APAC chỉ được xem đơn thuộc APAC; tài chính được xem tất cả đơn và email gốc; nhân viên phân tích chỉ cần email đã che. Nếu chỉ nhắc mọi người thêm `WHERE sales_region = 'APAC'` hoặc tự xóa cột email trong câu SQL, một truy vấn sai có thể làm lộ dữ liệu.

**BigQuery** cung cấp ba lớp kiểm soát bổ sung cho IAM:

- **Row-level security (RLS):** giới hạn những **hàng** người dùng được truy vấn bằng row access policies.
- **Column-level security (CLS):** giới hạn những **cột** người dùng được xem ở dạng gốc thông qua policy tags và quyền fine-grained.
- **Dynamic data masking:** cho phép nhóm được ủy quyền nhìn **giá trị đã che** thay vì cột gốc, dựa trên data policies.

Bài thuộc chương **BigQuery** của mô-đun `CLOUD_PROVIDERS_GCP`. Kết quả là một thiết kế quản trị dữ liệu có thể ứng dụng cho pipeline từ Cloud Storage, Pub/Sub, Cloud Run/GKE, Cloud SQL đến phân tích BigQuery: đúng phạm vi truy cập, có audit, kiểm chứng truy vấn và kiểm soát chi phí. Các lệnh có tác động chỉ dành cho **project lab được phê duyệt**, không chạy trên bảng production.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt IAM cấp project/dataset/table với RLS, CLS và masking tại thời điểm truy vấn.
2. Tạo row access policy bằng GoogleSQL DDL, hiểu **deny by default** và phép **OR** giữa các policies.
3. Dùng **policy tag taxonomy** và `roles/datacatalog.categoryFineGrainedReader` để bảo vệ dữ liệu gốc.
4. Dùng **data policy** và `roles/bigquerydatapolicy.maskedReader` để cấp quyền xem dữ liệu đã che.
5. Hiểu sự tương tác RLS–CLS–masking và các giới hạn về views, query, export, partition pruning.
6. Thiết kế thử nghiệm với nhiều danh tính để chứng minh không rò dữ liệu.
7. Vận hành policies qua CLI/SQL, kiểm soát IAM, audit logs và chi phí truy vấn.

## 1. Ba lớp kiểm soát áp dụng vào đâu?

~~~mermaid
flowchart LR
    A["Principal + BigQuery job IAM"] --> T["Quyền truy vấn table"]
    T --> R["Row access policies<br/>chọn rows được thấy"]
    R --> C["Column policy tags / data policies<br/>raw, masked, denied"]
    C --> Q["Kết quả SQL theo quyền caller"]
~~~

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **IAM** | Caller có được tạo query job và đọc table không? | `bigquery.jobs.create` + `bigquery.tables.getData` |
| **RLS** | Caller được xem những **hàng nào**? | Nhóm APAC chỉ thấy `sales_region='APAC'` |
| **CLS** | Caller có được truy cập **giá trị cột gốc** không? | Chỉ finance/PII stewards thấy `customer_email` nguyên vẹn |
| **Masking** | Nếu không được xem giá trị gốc, caller có được xem **giá trị thay thế** không? | Analyst thấy email nullified/hashed/partially masked |

**Quyền từ một lớp không tự thay thế lớp khác.** Được liệt kê trong RLS không cấp quyền tạo job/đọc table. Có `bigquery.dataViewer` không tự mở cột đang có policy tag. Được cấp Masked Reader không mở rộng sang các hàng bị RLS loại bỏ.

### 1.1. Ví dụ quyền truy cập mong muốn

Bảng `bq_governance_lab.orders`:

| Nhóm | Hàng | Email | Doanh thu |
| --- | --- | --- | --- |
| `analytics-apac` | Chỉ APAC | Đã che | Xem theo quyền table |
| `analytics-emea` | Chỉ EMEA | Đã che | Xem theo quyền table |
| `finance` | Tất cả regions | Gốc | Xem |
| `unapproved` | Không có hàng hoặc bị từ chối | Không truy cập | Không truy cập |

Giả định những nhóm trên có **table access cơ sở** theo phê duyệt; RLS và masking tiếp tục thu hẹp phạm vi. Tên nhóm/domain trong lab là placeholder, **không phải email thật** và phải thay bằng principal tồn tại trước khi tạo policy.

## 2. Row-level security hoạt động ra sao?

Row access policy gắn trực tiếp với **table** và định nghĩa:

- Tên policy duy nhất trong table.
- Danh sách người/nhóm/service accounts được cấp (`GRANT TO`).
- Biểu thức lọc (`FILTER USING`), tương tự điều kiện `WHERE`.

Ví dụ:

~~~sql
CREATE ROW ACCESS POLICY apac_orders
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('group:analytics-apac@example.com')
FILTER USING (sales_region = 'APAC');
~~~

Trong BigQuery Studio, **thay `PROJECT_ID` và địa chỉ nhóm bằng giá trị lab thật**; giữ nguyên dấu backtick bao quanh tên bảng theo cú pháp GoogleSQL. Lệnh tạo policy cần quyền quản trị row access policies, quyền đọc table và tạo job.

**Ngay khi bảng có row access policy, người dùng không được liệt kê trong bất kỳ policy phù hợp nào sẽ không tự có quyền xem toàn bộ hàng**, kể cả trước đó có quyền table. Vì thế phải chuẩn bị một `TRUE` filter riêng cho nhóm quản trị/ETL cần full access **trước khi bật các filter khác**.

~~~sql
CREATE ROW ACCESS POLICY full_for_finance
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('group:finance@example.com')
FILTER USING (TRUE);
~~~

`TRUE` cấp **mọi hàng**, nhưng vẫn chịu **CLS và masking ở cấp cột**, cũng như IAM table. Không dùng `allAuthenticatedUsers` hoặc `TRUE` cho nhóm quá rộng.

### 2.1. Nhiều policies không tự tạo phép AND

Nếu một user thuộc **hai groups**, BigQuery cấp hợp các hàng mà **bất kỳ policy nào** của user đó cho xem: **OR**, không phải AND.

~~~sql
-- Analyst thuộc cả nhóm APAC và nhóm VIP sẽ thấy:
-- (sales_region='APAC') OR (segment='VIP').
CREATE ROW ACCESS POLICY vip_orders
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('group:analytics-apac@example.com')
FILTER USING (segment = 'VIP');
~~~

Nếu ý định là “chỉ VIP **trong APAC**”, gộp điều kiện vào **cùng policy**:

~~~sql
FILTER USING (sales_region = 'APAC' AND segment = 'VIP')
~~~

**Rủi ro:** thêm một policy rộng có thể **mở rộng** tập hàng người dùng thấy. Mọi thay đổi policy cần kiểm thử như thay đổi IAM.

## 3. Policy RLS theo danh tính: dùng thận trọng

Có thể dùng `SESSION_USER()` trong biểu thức lọc để gắn hàng với caller thực tế:

~~~sql
CREATE ROW ACCESS POLICY own_orders
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('domain:example.com')
FILTER USING (owner_email = SESSION_USER());
~~~

Mẫu này phù hợp khi mỗi hàng có `owner_email` đáng tin cậy. Nếu mapping nhiều user–region hoặc phân cấp quản lý, có thể dùng **subquery row access policy** tới bảng ánh xạ do hệ thống bảo vệ. Tuy nhiên loại policy có subquery có **hạn chế bổ sung**: khả năng dùng Storage Read API, masking và các cột được filter có thể khác với simple predicates. Với workload cần **CLS + masking**, nên ưu tiên **filter đơn giản** hoặc kiểm tra compatibility chính thức trước khi dùng subquery.

Không tin cột `owner_email` do client tự ghi nếu chưa xác thực; RLS chỉ đúng khi **dữ liệu dùng làm điều kiện lọc cũng đúng**.

## 4. IAM của người tạo policy và người truy vấn

| Vai trò/quyền | Mục đích |
| --- | --- |
| `roles/bigquery.admin` / `roles/bigquery.dataOwner` | Quản trị bảng và row access policies theo phạm vi |
| `roles/bigquery.jobUser` | Tạo query jobs trên project được cấp |
| `roles/bigquery.dataViewer` | Đọc dữ liệu bảng/dataset được cấp |
| `roles/bigquery.filteredDataViewer` | BigQuery **tự quản lý** cho danh sách `GRANT TO` trong row policy |
| `roles/datacatalog.categoryAdmin` | Tạo/quản lý taxonomy và policy tags |
| `roles/datacatalog.categoryFineGrainedReader` | Được xem cột gốc gắn policy tag |
| `roles/bigquerydatapolicy.admin` | Tạo/quản trị BigQuery data policies |
| `roles/bigquerydatapolicy.maskedReader` | Xem dữ liệu đã che theo data policy được cấp |

**Không cấp `roles/bigquery.filteredDataViewer` thủ công qua IAM.** BigQuery gán quyền này theo row access policy. Phần IAM table vẫn phải được cấp riêng.

Người quản trị nên phân tách quyền: **Data Owner** quản schema/table, **Security/Data Policy Admin** quản phân loại và masking, **analyst** chỉ có quyền query và đúng cột/hàng đã được cấp. Không dùng một service account có `bigquery.admin` cho toàn bộ ứng dụng Cloud Run chỉ để tránh lỗi permission.

## 5. Column-level security: taxonomy và policy tags

Trong cách triển khai dựa trên **Data Catalog policy tags**, doanh nghiệp tạo một **taxonomy** phân loại dữ liệu, ví dụ:

~~~text
Taxonomy: commerce-classification
├── PUBLIC
├── INTERNAL
└── SENSITIVE
    ├── PII_EMAIL
    └── PII_PHONE
~~~

Khi gắn policy tag `PII_EMAIL` vào cột `customer_email`, BigQuery kiểm tra quyền tương ứng khi query. Nhóm cần đọc **giá trị gốc** được cấp `roles/datacatalog.categoryFineGrainedReader` tại policy tag/taxonomy thích hợp.

**Chú ý:** policy tag là một **tài nguyên quản trị** (resource name dài), không phải chuỗi mô tả đặt trong `OPTIONS(description=...)`. Một cột chỉ gắn **một policy tag** trong mô hình này; các mức độ truy cập có thể kế thừa từ cây taxonomy.

### 5.1. Quy trình cấu hình CLS

1. Chọn **region của taxonomy khớp vị trí dữ liệu BigQuery**, ví dụ `asia-southeast1`. Project chứa taxonomy phải thuộc một organization theo điều kiện của tính năng.
2. Tạo taxonomy và các policy tags trong Console (**Policy tag taxonomies**) hoặc Data Catalog API.
3. Chọn tag `PII_EMAIL`, **bật enforce access control**/tạo data policy theo giao diện và phiên bản hỗ trợ.
4. Cấp `Fine-Grained Reader` cho finance/PII stewards ở tag đúng phạm vi.
5. Gắn tag vào cột `customer_email` trong BigQuery table schema.
6. Thử query dưới **identities thực của nhóm** và xem audit logs.

Nếu người dùng có quyền đọc bảng nhưng không có quyền cột, lệnh `SELECT customer_email` có thể báo **Access Denied**. Lệnh `SELECT *` cũng có thể lỗi nếu nó chọn một cột được bảo vệ mà caller không có quyền; cần chọn các cột được phép hoặc dùng `SELECT * EXCEPT(customer_email)`.

### 5.2. Ví dụ gắn policy tag bằng bq schema

Trong terminal **lab**, đọc schema hiện tại:

~~~bash
bq show --schema --format=prettyjson \
  PROJECT_ID:bq_governance_lab.orders > orders-schema.json
~~~

Trong đối tượng của cột `customer_email`, thêm trường `policyTags` với resource name thật:

~~~json
{
  "name": "customer_email",
  "type": "STRING",
  "mode": "NULLABLE",
  "policyTags": {
    "names": [
      "projects/PROJECT_ID/locations/asia-southeast1/taxonomies/TAXONOMY_ID/policyTags/TAG_ID"
    ]
  }
}
~~~

**Đây là một phần của schema**, không phải toàn bộ file. Giữ nguyên tất cả cột và thuộc tính khác khi cập nhật:

~~~bash
# CẢNH BÁO: thao tác cập nhật schema thật.
bq update PROJECT_ID:bq_governance_lab.orders orders-schema.json
~~~

Trước khi thực hiện, lưu bản schema gốc, xác nhận taxonomy/tag resource và có quyền `bigquery.tables.setCategory` cùng `datacatalog.taxonomies.get`. Không cập nhật schema production bằng file chỉ chứa một cột.

## 6. Dynamic data masking: xem được nhưng không xem giá trị gốc

**Data masking** dùng **data policy** để liên kết masking rule với principal. Khi truy vấn, BigQuery trả dữ liệu thay thế cho người có Masked Reader nhưng không có quyền raw phù hợp.

~~~mermaid
flowchart TD
    T["Cột customer_email có policy tag PII_EMAIL"] --> IAM{"Principal được cấp quyền gì?"}
    IAM -->|"Fine-Grained Reader theo hierarchy"| RAW["Email gốc"]
    IAM -->|"Masked Reader theo data policy"| MASK["Email đã che"]
    IAM -->|"Không quyền phù hợp"| DENY["Access denied"]
~~~

Ví dụ phân quyền:

| Nhóm | Quyền trên cột `customer_email` | Kết quả kỳ vọng |
| --- | --- | --- |
| Finance | Fine-Grained Reader phù hợp | `alice@demo.invalid` |
| Analyst | Masked Reader cho email policy | `aXXXX@...` hoặc `NULL` tùy mask rule |
| Không được phê duyệt | Không có raw/masked permissions | Query cột bị từ chối |

**Chú ý đến thứ tự kiểm tra quyền khi người dùng thuộc nhiều nhóm:** policy tag **hierarchy** có thể làm quyền raw hoặc masked thắng tùy cấp tag được gán. Không tuyên bố đơn giản rằng “Fine-Grained Reader luôn thắng” khi có thừa kế; phải thử với nhóm chồng lấp.

### 6.1. Một số masking rules

| Rule | Đặc điểm | Lưu ý |
| --- | --- | --- |
| **Nullify** | Trả `NULL` | Không thể phân biệt nhóm dữ liệu bằng giá trị cột |
| **Default masking value** | Giá trị mặc định theo kiểu dữ liệu | Không dùng như dữ liệu chính xác |
| **Email mask** | Giữ một phần cấu trúc email | Có thể còn tiết lộ một số thông tin |
| **First/last four characters** | Giữ 4 ký tự đầu/cuối; phần khác bị che | Kiểu dữ liệu phải phù hợp |
| **Hash (SHA-256)** | Hash xác định được từ dữ liệu | Dễ liên kết các giá trị giống nhau, **không phải mã hóa** |
| **Random hash** | Salt thay đổi theo truy vấn | Chỉ hỗ trợ data policies gắn **trực tiếp trên cột**, khác policy tags |
| **Date year mask** | Chỉ giữ thông tin năm | Mất độ chính xác ngày/tháng |
| **Custom masking routine** | UDF riêng để che dữ liệu | Cần xem permissions, kiểu dữ liệu và giới hạn |

Hashing/masking không thay thế **encryption**, tokenization hay quyền truy cập vào dữ liệu gốc. Với giá trị dễ đoán (số điện thoại, mã vùng), hash xác định vẫn có nguy cơ suy luận. Masking cũng không làm một tập dữ liệu tự động **ẩn danh** cho mọi mục đích pháp lý.

## 7. Tạo data policy và gắn masking rule

Có **hai đường triển khai hiện hành**, chọn một và giữ nhất quán trong môi trường:

**Đường A — Policy tags (phổ biến khi cần phân loại tập trung):**

1. Tạo taxonomy/tag `PII_EMAIL`.
2. Gắn tag vào cột email.
3. Trong **Policy tag taxonomies → Manage Data Policies**, tạo data policy với một rule, ví dụ **Email mask**.
4. Cấp `roles/bigquerydatapolicy.maskedReader` cho nhóm analyst tại **data policy**.
5. Cấp `Fine-Grained Reader` riêng cho nhóm được xem dữ liệu gốc.
6. Kiểm tra bằng query đúng identity, không chỉ bằng tài khoản admin.

**Đường B — Gắn data policy trực tiếp vào cột (không cần taxonomy):** BigQuery Data Policy API v2 và DDL hỗ trợ tạo policy, gắn vào trường `data_policies` của column schema. Những cú pháp SQL quản lý policy có thể ở **Pre-GA/Preview**, nên cần kiểm tra khả dụng trong edition/region trước khi áp vào production.

Ví dụ **minh họa hướng trực tiếp**, chọn rule `ALWAYS_NULL` theo tài liệu:

~~~sql
-- Thay PROJECT_ID bằng project lab thật; chọn đúng location.
CREATE DATA_POLICY `PROJECT_ID.region-asia-southeast1.email_null_lab`
OPTIONS (
  data_policy_type = "DATA_MASKING_POLICY",
  masking_expression = "ALWAYS_NULL"
);

ALTER TABLE `PROJECT_ID.bq_governance_lab.orders`
ALTER COLUMN customer_email SET OPTIONS (
  data_policies += [
    "{'name':'PROJECT_ID.region-asia-southeast1.email_null_lab'}"
  ]
);
~~~

Tạo/attach **chưa tự cấp quyền Masked Reader** cho analyst. IAM data policy phải được cấp ở phạm vi thích hợp bằng Console/API, tránh cấp ở project rộng. Có thể cấp quyền đọc giá trị gốc bằng cơ chế `RAW_DATA_ACCESS_POLICY`/fine-grained phù hợp với đường trực tiếp. **Không trộn policy tag và direct data policy trên cùng cột mà chưa kiểm tra compatibility.**

Nếu sử dụng **data governance tags (Resource Manager tags)** thay policy tags, đó là một cơ chế ABAC khác với tính năng/trạng thái hỗ trợ riêng; không giả định tên tag của Resource Manager dùng thay resource name của Data Catalog taxonomy.

## 8. Kết hợp RLS, CLS và masking: những trường hợp cần thử

Giả sử analyst thuộc nhóm `analytics-apac`, có Data Viewer bảng, được cấp Masked Reader cho email và có RLS `APAC`.

| Câu truy vấn | Kết quả mong đợi |
| --- | --- |
| `SELECT order_id, sales_region, total FROM orders` | Chỉ hàng APAC, các cột được phép |
| `SELECT customer_email FROM orders` | Chỉ hàng APAC, email đã che |
| `SELECT * FROM orders` | Thành công nếu caller có quyền **raw hoặc masked** với mọi cột bảo vệ |
| `SELECT * EXCEPT(customer_email) FROM orders` | Không cần quyền xem cột email trong projected fields |
| Query ngoài region APAC | Không thấy hàng EMEA/AMER do RLS |
| User thiếu table Data Viewer | **Access denied** trước khi chính sách row/masking cấp ích lợi |
| User có Data Viewer, không raw/masked email | Query có email bị **Access denied** |

**RLS được áp trước masking** theo semantics truy vấn. Data masking có giới hạn khi **RLS dùng subquery**; theo tài liệu, masking chỉ tương thích với truy vấn có **non-subquery row access policies**. Nếu filter RLS đọc cột có CLS, phải kiểm tra quyền Fine-Grained Reader cần thiết với chính cột đó.

### 8.1. Đừng dùng view, extract hay copy làm đường vòng

- **Authorized views** có thể là cơ chế khác để chỉ đưa ra subset được phép, nhưng quyền access và tính năng kết hợp với RLS/CLS/masking cần được kiểm thử.
- **Extract jobs** trên bảng có RLS chỉ xuất dữ liệu mà identity có quyền xem theo cơ chế hỗ trợ. Không suy ra export đã giải quyết mọi vấn đề với dữ liệu masked.
- Người có quyền **bỏ policy, thay schema, truy cập bản sao/exports/raw source** có thể mở dữ liệu ngoài phạm vi một query được che. Cần quản trị **derived tables, scheduled queries, extracts, backups, destination buckets**, IAM của service accounts và audit.
- **Legacy SQL**, table preview và một số khả năng BI Engine/materialized views/Storage Read API không tương thích đầy đủ với RLS hoặc masking; kiểm tra danh sách giới hạn cho pipeline sử dụng.

## 9. Lab: tạo bảng mẫu không có dữ liệu thật

**Chỉ chạy trong project lab có Billing và quyền tạo BigQuery dataset/table.** Chọn thống nhất location `asia-southeast1` cho dataset, taxonomy và data policies. Không sử dụng email/đơn hàng khách thật.

### 9.1. Preflight

~~~bash
gcloud auth list
gcloud config get-value project
bq ls --project_id=PROJECT_ID

# Xem cấu hình và quyền trước khi ghi:
gcloud services list --enabled --project=PROJECT_ID \
  --filter="name:bigquery.googleapis.com"
~~~

### 9.2. Tạo dataset/bảng tại BigQuery Studio

Chạy GoogleSQL trong **BigQuery Studio**, đặt **Processing location = asia-southeast1** và thay `PROJECT_ID`. Tên bảng trong các khối SQL đã có dấu backtick; sau khi thay project ID, có thể dùng tên như `demo-project.bq_governance_lab.orders`.

~~~sql
CREATE SCHEMA IF NOT EXISTS `PROJECT_ID.bq_governance_lab`
OPTIONS (location = "asia-southeast1");

-- KHÔNG chạy CREATE OR REPLACE TABLE trên dữ liệu không phải lab.
CREATE OR REPLACE TABLE `PROJECT_ID.bq_governance_lab.orders` (
  order_id STRING,
  sales_region STRING,
  customer_email STRING,
  customer_phone STRING,
  total NUMERIC,
  segment STRING
);

INSERT INTO `PROJECT_ID.bq_governance_lab.orders`
(order_id, sales_region, customer_email, customer_phone, total, segment)
VALUES
('o-001', 'APAC', 'a@demo.invalid', '0000000001', 125000, 'REGULAR'),
('o-002', 'EMEA', 'b@demo.invalid', '0000000002', 450000, 'VIP'),
('o-003', 'APAC', 'c@demo.invalid', '0000000003', 220000, 'VIP'),
('o-004', 'AMER', 'd@demo.invalid', '0000000004', 80000, 'REGULAR');
~~~

**Dữ liệu giả lập** có 2 hàng APAC, 1 EMEA, 1 AMER. Nếu môi trường đã có bảng `orders`, **không dùng `OR REPLACE`**, phải đổi tên lab khác hoặc xin quyền chủ sở hữu.

### 9.3. Cấp table IAM trước khi bật RLS

Để query kết quả bằng tài khoản thử nghiệm, cấp quyền tạo job trên project và **Data Viewer trên đúng dataset/table** theo phạm vi đã duyệt cho ba nhóm. Phải làm bằng quản trị viên IAM, không cấp Editor/Owner toàn project chỉ để demo.

Tạo/kiểm tra **nhóm thật** với tên thay cho `finance@example.com`, `analytics-apac@example.com` và `analytics-emea@example.com`. Principal chưa tồn tại làm `CREATE ROW ACCESS POLICY` thất bại.

### 9.4. Tạo các row policies

~~~sql
-- Tạo full-access policy trước để giữ đường ETL/quản trị.
CREATE ROW ACCESS POLICY finance_all
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('group:finance@example.com')
FILTER USING (TRUE);

CREATE ROW ACCESS POLICY apac_only
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('group:analytics-apac@example.com')
FILTER USING (sales_region = 'APAC');

CREATE ROW ACCESS POLICY emea_only
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('group:analytics-emea@example.com')
FILTER USING (sales_region = 'EMEA');
~~~

**Kiểm tra bằng CLI:**

~~~bash
bq ls --row_access_policies \
  PROJECT_ID:bq_governance_lab.orders

bq show --schema --format=prettyjson \
  PROJECT_ID:bq_governance_lab.orders
~~~

Kỳ vọng principal APAC thấy 2 hàng, EMEA thấy 1 hàng, finance thấy 4 hàng; người dùng không thuộc row policy phù hợp **bị từ chối truy cập dữ liệu hàng**. **Phải chạy bằng danh tính tương ứng**, không kết luận từ query của admin vì admin có thể được cấp quyền rộng khác.

## 10. Lab: cột email chỉ cho finance xem gốc

Tiếp tục sau mục 9:

1. Trong Data Catalog policy tag taxonomies tại `asia-southeast1`, tạo taxonomy `commerce_lab`, tag `PII_EMAIL`.
2. Bật column-level enforcement cho taxonomy/tag theo luồng Console.
3. Cấp `Fine-Grained Reader` trên tag `PII_EMAIL` cho nhóm `finance`.
4. Gắn `PII_EMAIL` vào cột `customer_email` của bảng lab.
5. Dùng một **tài khoản APAC không có Fine-Grained Reader** query `SELECT customer_email`: phải bị từ chối nếu chưa có masking policy thích hợp.

**Không dùng chính tài khoản admin để giả lập “người dùng không có quyền”.** Admin có thể được cấp Data Owner/Fine-Grained Reader hoặc quyền điều chỉnh chính sách; kiểm thử bằng security principal có IAM chính xác.

### 10.1. Bật masking cho nhóm analytics

1. Trên tag `PII_EMAIL`, chọn **Manage Data Policies**.
2. Tạo data policy `mask_email_analyst_lab`, ví dụ rule **Email mask** hoặc **Nullify**.
3. Cấp **BigQuery Masked Reader** trên data policy cho `analytics-apac` và `analytics-emea`; không cấp role rộng ở project.
4. Query lại dưới hai analyst: chỉ thấy hàng theo RLS, giá trị email bị che. Dưới finance, email gốc được thấy theo Fine-Grained Reader ở tag.
5. Thử query `SELECT order_id, sales_region, total` để xác nhận các cột công khai vẫn truy cập đúng.

**Kỳ vọng bảo mật:** analyst APAC **không** thể lấy email gốc; finance thấy email gốc nhưng không vì vậy bỏ qua RLS nếu không có policy `TRUE`; danh tính không được phê duyệt không được xem dữ liệu. Với nullify, kết quả email có thể là `NULL` nhưng type schema vẫn như cột nguồn.

## 11. Checklist kiểm thử positive và negative

| Thử nghiệm | Đầu ra cần chứng minh |
| --- | --- |
| APAC analyst query các cột không bảo vệ | Chính xác **2** hàng APAC |
| EMEA analyst query | Chính xác **1** hàng EMEA |
| Finance có `TRUE` policy | **4** hàng giả lập |
| Analyst query email trước khi cấp masked role | **Access denied** |
| Analyst query email sau khi cấp masked role | Email **đã che**, không phải gốc |
| Finance query email | Giá trị gốc, không bị che ngoài ý muốn |
| User chỉ có table Data Viewer, không có row policy | Không truy cập được các hàng được bảo vệ |
| Analyst thuộc cả APAC và EMEA | **Hợp** của hai policy: 3 hàng; phải được duyệt rõ |
| Analyst có raw policy tag nhưng không có table access | Vẫn **Access denied** |
| ETL SA thiếu `TRUE` row policy | Job copy/transform có thể bị lọc hoặc fail |
| Cột nhạy cảm qua view/export/scheduled query | Không có đường tạo derived asset mở rộng dữ liệu |
| Thay policy/masking rule | Có change log, test và rollback rõ |

**Thứ tự kiểm tra:** IAM table/job → RLS hàng → CLS/masking cột → kết quả trên view/export/BI. Nếu thử `SELECT *` thất bại, thử query chỉ các cột không nhạy cảm để xác định lỗi nằm ở CLS chứ không phải RLS.

## 12. Vận hành: thay đổi, xem và dọn policies an toàn

Tất cả thay đổi security policies phải đi qua code review/change approval. Với RLS:

~~~sql
-- Thay định nghĩa và danh sách người nhận của policy có tên cụ thể.
CREATE OR REPLACE ROW ACCESS POLICY apac_only
ON `PROJECT_ID.bq_governance_lab.orders`
GRANT TO ('group:analytics-apac@example.com')
FILTER USING (sales_region = 'APAC' AND segment = 'VIP');
~~~

**Cảnh báo:** đây là thay đổi quyền có tác động thực; nếu chỉ thêm policy khác, nhiều policies được **OR** với nhau. Không coi một policy hẹp hơn là bảo đảm toàn bộ quyền đã hẹp lại khi vẫn còn các policy khác.

Dọn lab sau khi người sở hữu xác nhận:

~~~sql
-- CẢNH BÁO: gỡ tất cả row policies là gỡ lớp bảo vệ hàng!
DROP ALL ROW ACCESS POLICIES
ON `PROJECT_ID.bq_governance_lab.orders`;
~~~

BigQuery **không cho xóa policy cuối cùng bằng `DROP ROW ACCESS POLICY` đơn lẻ**; phải dùng `DROP ALL ROW ACCESS POLICIES` khi muốn gỡ hoàn toàn RLS. Điều này có thể **mở lại mọi hàng cho người còn Data Viewer**, vì thế chỉ làm khi đã thu hồi IAM hoặc chuẩn bị biện pháp bảo vệ thay thế.

Để xóa taxonomy/policy tags/data policies, phải xử lý **liên kết cột, quyền raw/masked, những data policies đang tham chiếu** theo đúng thứ tự phụ thuộc. Không xóa taxonomy production để giải quyết một lỗi permission của analyst.

## 13. Audit, giám sát và chi phí

### 13.1. Xác minh kết quả truy vấn và quyền truy cập

- **BigQuery Jobs / INFORMATION_SCHEMA** cho thấy job, người chạy, bytes processed và lỗi; không thay cho **Cloud Audit Logs** về hành động quản trị policy và data access.
- **BigQuery Job API** có `rowLevelSecurityStatistics.rowLevelSecurityApplied` để cho biết bảng trong query được áp row access policies; trường này **không chứng minh mask rule đúng**, cần kiểm tra với test identity.
- **Cloud Audit Logs** ghi nhận hành vi truy vấn và thay đổi policies theo loại audit logs/quyền xem log; triển khai cảnh báo khi row policy, taxonomy, policy tag hoặc data policy thay đổi.
- Kiểm tra **data lineage và derived assets**: authorized views, scheduled queries, destination tables, extracts sang Cloud Storage, BI connectors.

Ví dụ query công việc trong **BigQuery Studio** (cần quyền xem job metadata và đúng location):

~~~sql
SELECT creation_time, user_email, job_id,
       total_bytes_processed, total_slot_ms,
       error_result.message AS error_message
FROM `PROJECT_ID.region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND job_type = 'QUERY'
ORDER BY creation_time DESC
LIMIT 100;
~~~

Không ghi kết quả query có PII vào incident ticket công khai; chỉ lưu job ID, request IDs, policy version và các số đo an toàn.

### 13.2. Giá và tối ưu query

**RLS không có phụ phí tính năng riêng**, nhưng vẫn có **chi phí truy vấn BigQuery** theo bytes processed hoặc slots/reservations. Row policy filter không tự tham gia **partition pruning**; nếu query cần đọc ít phân vùng, viết **`WHERE` trên partition column** ở câu query người dùng. Row policies dùng subqueries có thể quét thêm bảng mapping, tăng chi phí.

**Masking** có thể làm thay đổi lượng bytes được quét; quy tắc Nullify/Default có thể không cần quét cột gốc trong một số queries. Không hứa “masking luôn giảm giá” hoặc “RLS luôn làm query nhanh hơn”. Theo dõi các số liệu thực tế trên **Billing Reports/INFORMATION_SCHEMA**, kết hợp SLO latency và bytes processed.

## 14. Sai lầm phổ biến khi triển khai

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Analyst thấy nhiều regions hơn dự kiến | User thuộc nhiều `GRANT TO`; nhiều policies được OR | Audit mọi policy áp dụng cho user |
| Không ai ngoài admin thấy hàng | Thiếu `TRUE` policy hoặc grantee sai | Thêm policy full-access đúng phạm vi, test lại |
| RLS policy không tạo được | Nhóm không tồn tại, IAM thiếu, biểu thức unsupported | Kiểm tra principal và permissions |
| Có RLS nhưng `SELECT *` lỗi | Cột gắn policy tag thiếu raw/masked quyền | Kiểm tra CLS/data policy, query cột được phép |
| Analyst xem được email gốc | Fine-Grained Reader gán quá rộng/kế thừa cấp cha | Audit hierarchy và policy bindings |
| Masking không áp vào email | Chưa gắn tag/policy vào column, chưa cấp Masked Reader | Kiểm tra schema/data policies và principal |
| Job ETL/export thiếu dòng | Service account không có `TRUE` row access policy | Rà soát quyền và business requirement |
| Preview table không hoạt động | RLS không hỗ trợ preview | Dùng query với identity hợp lệ |
| Query với Storage Read API lỗi | RLS subquery policy hoặc masking không tương thích | Dùng filter đơn giản/đường query hỗ trợ |
| Query tốn tiền hơn | Không prune partitions theo RLS, subquery table | Thêm partition filter vào user query, đo bytes |
| Test admin pass nhưng analyst fail | Principal khác, IAM/policy khác | Test dưới chính service account/user thật |
| Bỏ policy khiến lộ dữ liệu | `DROP ALL` mở hàng khi vẫn có table access | Change review, thu hồi quyền/rollback plan |

## 15. Tình huống tổng hợp: dữ liệu bán hàng nhiều khu vực

**Bối cảnh:** Commerce dùng Cloud Run để tiếp nhận đơn, Pub/Sub để truyền events, Dataflow/BigQuery để phân tích. Bảng BigQuery tập trung có email khách hàng và doanh thu theo khu vực. Yêu cầu:

- Analyst APAC chỉ thấy đơn APAC, email đã che.
- Finance thấy đủ vùng và email gốc.
- Dịch vụ ETL vẫn có thể làm việc trên toàn bảng.
- BI dashboards không công bố PII.
- Compliance truy được ai thay policy và khi nào.

**Kiến trúc đề xuất:**

~~~mermaid
flowchart LR
    SRC["Cloud Run / Dataflow"] --> T["BigQuery orders table"]
    T --> ROW["RLS theo sales_region"]
    ROW --> COL["CLS policy tag PII_EMAIL"]
    COL --> MASK["Masking data policy"]
    MASK --> A["APAC analyst<br/>APAC rows + masked email"]
    MASK --> F["Finance<br/>all rows + raw email"]
    T --> AUD["Audit Logs + Jobs + Billing"]
~~~

Quy trình triển khai:

1. Xác định chủ sở hữu dữ liệu, phân loại PII và yêu cầu lưu trữ/quốc gia.
2. Giảm quyền IAM cơ sở, tạo group/service account theo vai trò; định nghĩa nhóm cần full access.
3. Bật RLS theo region và thử mọi identity, đặc biệt memberships chồng lấp.
4. Gắn policy tag vào email, thử deny trước khi cấp Masked Reader.
5. Cấp masked/raw access theo nhu cầu; thử qua BigQuery Studio, BI và ETL connectors.
6. Đặt logging/alert cho thay policy, kiểm tra derived tables/sinks.
7. Theo dõi chi phí query và báo cáo định kỳ để tránh chính sách tăng gánh quét dữ liệu.

**Định nghĩa thành công:** analyst không truy cập được email gốc hoặc hàng ngoài khu vực, trong khi tài chính/ETL làm việc đủ phạm vi và có bằng chứng test/audit. Không lấy một ảnh chụp query của admin làm chứng cứ.

## 16. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — Kiểm tra RLS.** Với dữ liệu bốn đơn ở mục 9, tạo APAC và EMEA policies; truy vấn bằng hai groups.

*Đạt:* APAC thấy 2 rows, EMEA thấy 1 row; không rò hàng ngoài region.

**Bài 2 — Quyền chồng lấp.** User thuộc cả APAC và EMEA groups. Bao nhiêu hàng được thấy?

*Đáp án:* 3 hàng (hợp hai policies), nếu IAM table hợp lệ.

**Bài 3 — Bảo vệ email.** Gắn tag, thử query email với analyst trước và sau khi được cấp Masked Reader.

*Đạt:* Trước bị từ chối; sau chỉ thấy giá trị che; finance được xem raw nếu được cấp Fine-Grained Reader.

**Bài 4 — Audit ETL.** Một service account phải copy/transform toàn bảng nhưng chỉ có Data Viewer và nằm ngoài mọi RLS policy. Vì sao job có thể lỗi hoặc thiếu dòng?

*Đáp án:* Bởi vì IAM table không thay row policy. Cần `TRUE` policy ở đúng SA theo approval.

**Câu 5.** RLS áp theo hàng hay cột?

*Đáp án:* Hàng; CLS/masking kiểm soát cột.

**Câu 6.** Hai RLS policies của cùng user được AND hay OR?

*Đáp án:* OR. Muốn AND, gộp điều kiện trong cùng filter.

**Câu 7.** Có nên tự cấp `roles/bigquery.filteredDataViewer` để sửa lỗi query không?

*Đáp án:* Không. Đây là quyền hệ thống được tạo qua row access policy.

**Câu 8.** `SELECT *` có an toàn khi user thiếu quyền cột nhạy cảm?

*Đáp án:* Có thể bị Access Denied; chỉ chọn cột được phép hoặc cấp raw/masked quyền đúng.

**Câu 9.** Masking SHA-256 có thay thế mã hóa và ẩn danh mọi trường hợp?

*Đáp án:* Không. Hash cố định có thể giúp liên kết/suy luận giá trị.

**Câu 10.** Data policy và policy tag là một tài nguyên?

*Đáp án:* Không. Tag phân loại/gắn cột; policy xác định rule và quyền đọc raw/masked.

**Câu 11.** BigQuery RLS filter tự tạo partition pruning cho query?

*Đáp án:* Không. Query người dùng cần filter partition thích hợp.

**Câu 12.** RLS có tương thích mọi Storage Read API, Legacy SQL và materialized views?

*Đáp án:* Không. Có giới hạn theo loại policy và tính năng; kiểm tra tài liệu.

**Câu 13.** Tại sao chỉ kiểm tra bằng tài khoản admin không đủ?

*Đáp án:* Admin có IAM/policy khác analyst, dễ che lấp lỗi cấu hình.

**Câu 14.** Xóa row access policy cuối cùng bằng `DROP ALL` có thể gây hậu quả gì?

*Đáp án:* Gỡ bảo vệ hàng; những người vẫn có table IAM có thể thấy nhiều dữ liệu hơn.

## 17. Checklist triển khai production

- [ ] Phân loại dữ liệu và owner cho table/cột PII; có data inventory/lineage.
- [ ] IAM table/job theo least privilege, tách quản trị policy và người tiêu thụ dữ liệu.
- [ ] RLS có `TRUE` policy đúng nhóm quản trị/ETL; không cấp đại trà.
- [ ] Hiểu phép **OR** giữa policies; test memberships chồng lấp và deny-by-default.
- [ ] CLS policy tag/taxonomy đúng location; Fine-Grained Reader chỉ đúng nhóm.
- [ ] Masking rule có threat model; Masked Reader cấp đúng data policy.
- [ ] Kiểm tra đường **policy tag** so với **direct data policy**/data governance tags.
- [ ] Test positive/negative bằng danh tính thật, gồm BI/ETL/Storage Read API khi dùng.
- [ ] Không giả định masking là encryption/anonymization hoàn toàn.
- [ ] Có review khi đổi/grant/revoke/drop RLS, tag hoặc data policy; backup/rollback script.
- [ ] Kiểm toán derived tables, authorized views, scheduled queries, exports và backups.
- [ ] Theo dõi Audit Logs, Jobs metadata, rowLevelSecurityApplied và query failures.
- [ ] Theo dõi bytes scanned, partition pruning, slot usage và Billing.
- [ ] Có staging/test trước khi thay policy production; không hard-code PII vào lab.

## 18. Kết luận

**RLS bảo vệ hàng; CLS bảo vệ cột gốc; masking cho phép xem một biểu diễn đã che của cột.** Chúng tạo thành nhiều lớp kiểm soát dựa trên danh tính, nhưng phải đi cùng IAM, dữ liệu phân loại đúng, quản trị derived assets và kiểm thử thực tế.

Với BigQuery, một chính sách tốt không chỉ là DDL đúng cú pháp: phải chứng minh **người đúng thấy hàng đúng, cột đúng ở dạng được phép; người không được phép bị từ chối; và các pipeline/chi phí/audit vẫn hoạt động an toàn**.

## Tài liệu tham khảo chính thức

- [Introduction to row-level security](https://cloud.google.com/bigquery/docs/row-level-security-intro)
- [Use row-level security](https://cloud.google.com/bigquery/docs/managing-row-level-security)
- [RLS with other BigQuery features](https://cloud.google.com/bigquery/docs/using-row-level-security-with-features)
- [Introduction to column-level access control](https://cloud.google.com/bigquery/docs/column-level-security-intro)
- [Restrict access with column-level security](https://cloud.google.com/bigquery/docs/column-level-security)
- [Introduction to data masking](https://cloud.google.com/bigquery/docs/column-data-masking-intro)
- [Mask column data](https://cloud.google.com/bigquery/docs/column-data-masking)
- [BigQuery DDL: CREATE DATA_POLICY](https://cloud.google.com/bigquery/docs/reference/standard-sql/data-definition-language)
- [BigQuery IAM roles and permissions](https://cloud.google.com/bigquery/docs/access-control)
- [BigQuery INFORMATION_SCHEMA JOBS](https://cloud.google.com/bigquery/docs/information-schema-jobs)
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing)

