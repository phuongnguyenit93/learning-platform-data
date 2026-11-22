# Data quality rules và kiểm tra chất lượng dữ liệu

Một hệ thống Java trên Cloud Run nhận sự kiện đơn hàng qua Pub/Sub, đẩy dữ liệu vào Cloud Storage và BigQuery để lập báo cáo. Nếu bảng phân tích có **mã đơn trùng**, **doanh thu âm ngoài quy tắc nghiệp vụ**, **thiếu vùng bán hàng** hoặc **dữ liệu đến muộn**, dashboard vẫn chạy được nhưng kết quả kinh doanh sai.

**Data quality (DQ)** là tập hợp các tiêu chí đo được để xác định dữ liệu có **đủ, đúng, nhất quán và kịp thời cho mục đích sử dụng** hay không. Trên Google Cloud, có thể triển khai bằng **GoogleSQL trên BigQuery**, **Dataform assertions** hoặc **automatic data quality scans của Knowledge Catalog (Dataplex DataScan)**. Những công cụ này giúp *phát hiện và đo vi phạm*; chỉ khi workflow có **quality gate** thì dữ liệu lỗi mới bị chặn khỏi các bước downstream.

Bài thuộc chương **Quản trị và khai thác dữ liệu** của mô-đun `CLOUD_PROVIDERS_GCP`. Các ví dụ kết nối kiến thức project/IAM/VPC, Cloud Run, GKE, Cloud Storage, Pub/Sub và BigQuery để thiết kế kiểm tra an toàn, tự động hóa phát hành, vận hành theo SLO và quản lý chi phí. Thực hành dùng **dữ liệu giả lập** trong project lab, không ghi đè bảng production.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **completeness, validity, uniqueness, consistency, timeliness/freshness** và kiểm tra đối soát nghiệp vụ.
2. Chuyển yêu cầu kinh doanh thành **rule có chủ sở hữu, phạm vi, ngưỡng và hành động khi vi phạm**.
3. Viết GoogleSQL để kiểm tra dữ liệu ở mức hàng và toàn bảng.
4. Cấu hình **Dataplex DataScan data-quality** với built-in rules và ngưỡng đạt.
5. Dùng **Dataform assertions** làm quality gate trong workflow SQL.
6. Thiết kế **quarantine, rerun/idempotency, schema drift, freshness alerts**.
7. Bảo vệ dữ liệu lỗi, service accounts và kết quả scan bằng IAM, audit và giới hạn PII.
8. Đo tỷ lệ lỗi/chi phí để quyết định khi nào cần lấy mẫu hay quét toàn bảng.

## 1. Kiến trúc kiểm tra chất lượng trong pipeline

~~~mermaid
flowchart LR
    SOURCE["Cloud Run / Cloud SQL<br/>Pub/Sub / GCS"] --> RAW[("BigQuery raw/landing")]
    RAW --> DQ["Quality rules<br/>SQL / DataScan / Dataform"]
    DQ -->|"Pass"| CURATED[("BigQuery curated")]
    DQ -->|"Fail"| HOLD["Quarantine + alert<br/>owner xử lý"]
    CURATED --> BI["BI / ML / API"]
    DQ --> OBS["Run results + scores<br/>Knowledge Catalog / logs"]
~~~

Ba khái niệm phải tách biệt:

- **Validation:** kiểm tra một bản ghi hoặc tập dữ liệu có đáp ứng rule hay không.
- **Profiling:** quan sát thống kê như tỷ lệ NULL, phân bố giá trị, min/max để *đề xuất* rule; không tự biết quy tắc kinh doanh.
- **Enforcement/gating:** ra quyết định **dừng**, **cách ly** hoặc **cảnh báo** dựa trên kết quả validation và mức độ nghiêm trọng.

**Scan đạt** không tự chứng minh dữ liệu có thể sử dụng cho mọi mục đích. Ví dụ doanh thu âm có thể sai với `OrderCreated` nhưng đúng với `RefundIssued`. Rule phải gắn với **semantics và owner nghiệp vụ**.

## 2. Các chiều chất lượng và dạng rule tương ứng

| Chiều | Câu hỏi | Ví dụ kiểm tra |
| --- | --- | --- |
| **Completeness** | Trường bắt buộc có thiếu không? | `order_id IS NOT NULL` |
| **Validity** | Giá trị đúng kiểu, phạm vi, tập cho phép không? | `amount_vnd > 0`, region thuộc APAC/EMEA/AMER |
| **Uniqueness** | Một khóa nghiệp vụ có bị lặp? | `COUNT(*) BY order_id <= 1` |
| **Consistency** | Hai dữ liệu có tuân cùng quy tắc không? | `paid_at IS NOT NULL` khi `status='PAID'` |
| **Integrity** | Tham chiếu và quan hệ có hợp lệ không? | `customer_id` tồn tại trong bảng khách |
| **Timeliness/Freshness** | Dữ liệu có đến kịp SLA không? | Ingestion lag dưới 2 giờ |
| **Accuracy** | Dữ liệu có phản ánh đúng thực tế không? | Đối soát với hệ thống nguồn/biên bản thanh toán |
| **Volume/Anomaly** | Số bản ghi tăng/giảm bất thường? | Số đơn ngày không lệch quá ngưỡng hợp lý |

Accuracy **không thể suy ra** chỉ từ một bảng: một số tiền sai nhưng vẫn lớn hơn 0 sẽ vượt qua rule `amount_vnd > 0`. Phải đối soát với **nguồn chuẩn** hoặc quy trình xác minh độc lập.

### 2.1. Rule phải có hợp đồng rõ ràng

Mỗi rule trong production nên ghi:

| Thuộc tính | Ví dụ |
| --- | --- |
| ID và phiên bản | `orders.amount.positive.v1` |
| Owner/đầu mối xử lý | Commerce Data Steward |
| Nguồn/phạm vi | `raw.orders`, một partition/ngày hoặc toàn bảng |
| Biểu thức | `amount_vnd > 0` |
| Ngưỡng | **100%** cho giao dịch tài chính cần nghiêm ngặt |
| Mức độ | **BLOCKER** nếu vi phạm; **WARN** nếu tín hiệu theo dõi |
| Lịch/SLO | Sau mỗi batch, trước publish curated |
| Xử lý thất bại | Dừng publish, ghi số liệu, thông báo owner, quarantine |
| Bằng chứng | Run ID, query/job ID, violations count, rule version |

**Ngưỡng 99% không phải “khá tốt” cho mọi trường hợp.** Với khóa giao dịch hoặc bảo mật, một vi phạm có thể không được phép; với một số thuộc tính tùy chọn, ngưỡng linh hoạt có thể hợp lý.

## 3. Rule mức hàng và rule tổng hợp toàn bảng

**Row-level** đánh giá từng hàng. Ví dụ `amount_vnd > 0`, `region IN (...)`. Tỷ lệ đạt có thể là:

~~~text
pass_rate = passing_rows / total_rows
threshold = 1.0   → yêu cầu 100% hàng được kiểm tra đạt
threshold = 0.98  → chấp nhận tối đa khoảng 2% hàng không đạt
~~~

**Aggregate/table-level** đánh giá cả tập dữ liệu. Ví dụ `COUNT(*) > 0`, `MAX(ingested_at)` trong SLA, hoặc bảng nguồn và đích cân bằng số hàng. Không áp trực tiếp tỷ lệ `passing_rows/total_rows` cho mọi rule tổng hợp: điều kiện đúng/sai được tính ở **cấp bảng**.

Hai lỗi thường gặp:

1. **Mẫu rỗng:** `COUNTIF(valid)=0` chưa chứng minh dữ liệu sạch nếu `COUNT(*)=0`. Cần rule riêng `COUNT(*) > 0` khi mong đợi phải có dữ liệu.
2. **Quét sai phạm vi:** chỉ kiểm tra một ngày nhưng kết luận toàn bảng đạt. Phải ghi chính xác filter, partition, sampling và thời gian run.

## 4. Lab: bảng đơn hàng giả lập có lỗi có chủ đích

Giả sử project lab có billing và dataset được phê duyệt tại `asia-southeast1`. Trong **BigQuery Studio**, đặt **Processing location = asia-southeast1**, thay `PROJECT_ID` bằng project thật. Tên bảng trong SQL đã có dấu backtick.

~~~sql
CREATE SCHEMA IF NOT EXISTS `PROJECT_ID.dq_lab`
OPTIONS (location = "asia-southeast1");

-- CHỈ LAB: dùng bảng mới, không thay bảng production.
CREATE TABLE IF NOT EXISTS `PROJECT_ID.dq_lab.orders_raw` (
  order_id STRING,
  sales_region STRING,
  amount_vnd INT64,
  event_date DATE,
  ingested_at TIMESTAMP
);

INSERT INTO `PROJECT_ID.dq_lab.orders_raw`
  (order_id, sales_region, amount_vnd, event_date, ingested_at)
VALUES
('o-1001', 'APAC', 120000, DATE '2026-11-18', CURRENT_TIMESTAMP()),
('o-1002', 'EMEA',  95000, DATE '2026-11-18', CURRENT_TIMESTAMP()),
('o-1003', 'APAC',  -5000, DATE '2026-11-18', CURRENT_TIMESTAMP()),
('o-1004', 'APAC',  50000, DATE '2026-11-18', CURRENT_TIMESTAMP()),
('o-1004', 'APAC',  50000, DATE '2026-11-18', CURRENT_TIMESTAMP()),
(NULL,     NULL,    30000, DATE '2026-11-18', CURRENT_TIMESTAMP());
~~~

Dữ liệu cố ý có **6 rows** với ba nhóm lỗi: thiếu `order_id` và `sales_region` ở hàng cuối, số tiền âm của `o-1003`, khóa `o-1004` xuất hiện hai lần. Các values mang tính minh họa; **không lặp lại INSERT** nếu muốn so sánh đúng kết quả dự kiến.

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Tổng rows | 6 |
| `order_id IS NULL` | 1 row |
| `amount_vnd <= 0` | 1 row |
| `sales_region` rỗng/ngoài tập | 1 row |
| Khóa trùng `order_id` (không tính NULL) | `o-1004` có 2 rows |
| Dữ liệu hoàn toàn hợp lệ, duy nhất theo order_id | Chưa đạt |

**Cảnh báo:** `CREATE TABLE IF NOT EXISTS` không đảm bảo dữ liệu bên trong rỗng; chạy lại `INSERT` sẽ làm tăng lỗi trùng. Dùng dataset/bảng lab mới hoặc dọn dữ liệu có kiểm soát.

## 5. GoogleSQL: kiểm tra tổng quát và tìm bản ghi lỗi

Đo completeness và validity:

~~~sql
SELECT
  COUNT(*) AS total_rows,
  COUNTIF(order_id IS NULL) AS missing_order_id,
  COUNTIF(amount_vnd IS NULL OR amount_vnd <= 0) AS invalid_amount,
  COUNTIF(sales_region IS NULL
    OR sales_region NOT IN ('APAC', 'EMEA', 'AMER')) AS invalid_region,
  SAFE_DIVIDE(COUNTIF(order_id IS NOT NULL), COUNT(*)) AS id_completeness_rate
FROM `PROJECT_ID.dq_lab.orders_raw`;
~~~

Kỳ vọng: `total_rows=6`, ba bộ đếm lỗi đều `1`, `id_completeness_rate≈0.8333`. `SAFE_DIVIDE` giúp tránh phép chia 0, nhưng **NULL khi không có rows vẫn phải được kiểm soát**.

Tìm khóa trùng:

~~~sql
SELECT order_id, COUNT(*) AS occurrences
FROM `PROJECT_ID.dq_lab.orders_raw`
WHERE order_id IS NOT NULL
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

Kỳ vọng `o-1004 / 2`. Để thấy các rows vi phạm điều kiện đơn lẻ:

~~~sql
SELECT order_id, sales_region, amount_vnd, event_date
FROM `PROJECT_ID.dq_lab.orders_raw`
WHERE order_id IS NULL
   OR amount_vnd IS NULL OR amount_vnd <= 0
   OR sales_region IS NULL
   OR sales_region NOT IN ('APAC', 'EMEA', 'AMER');
~~~

Truy vấn cuối chỉ phát hiện các lỗi **completeness/validity**; hai rows `o-1004` có thể không xuất hiện vì đều có tiền và region hợp lệ. **Uniqueness phải kiểm tra riêng** hoặc kết hợp analytic function.

### 5.1. Kiểm tra trùng bằng window function

~~~sql
WITH flagged AS (
  SELECT *,
    COUNT(*) OVER (PARTITION BY order_id) AS key_occurrences
  FROM `PROJECT_ID.dq_lab.orders_raw`
)
SELECT
  order_id, sales_region, amount_vnd,
  key_occurrences
FROM flagged
WHERE order_id IS NULL
   OR key_occurrences > 1
   OR amount_vnd IS NULL OR amount_vnd <= 0
   OR sales_region IS NULL
   OR sales_region NOT IN ('APAC','EMEA','AMER');
~~~

Ở dataset lab, output gồm các hàng lỗi `o-1003`, cả hai rows `o-1004`, và hàng thiếu ID. Nếu một nhóm cần **quarantine**, việc chọn “row nào giữ lại” phải dựa vào **event version, thời điểm cập nhật và nguồn đáng tin**, không chọn ngẫu nhiên hàng có giá trị tiền cao hơn.

## 6. BigQuery constraints không thay thế data quality checks

BigQuery có hỗ trợ khai báo **NOT NULL** trên cột khi tạo schema, và khai báo **PRIMARY KEY / FOREIGN KEY NOT ENFORCED**. Điểm khác biệt:

- `NOT NULL` cột nguồn có thể ngăn insert giá trị NULL khi được thực thi trong schema thích hợp.
- `PRIMARY KEY ... NOT ENFORCED` và `FOREIGN KEY ... NOT ENFORCED` là metadata để optimizer hỗ trợ tối ưu; **BigQuery không tự xác minh dữ liệu duy nhất/toàn vẹn tham chiếu**.
- Pipeline, load job, transformation hoặc bảng staging có thể vẫn chứa giá trị sai phạm nghiệp vụ dù schema hợp lệ.

**Không khai báo một primary key chưa bảo đảm đúng** rồi trông chờ BigQuery ngăn duplicates. Cần data quality test, transformation/gating và quản lý schema.

## 7. Knowledge Catalog / Dataplex automatic data quality

Google Cloud hiện cung cấp **automatic data quality** trong **Knowledge Catalog** (các API và lệnh CLI vẫn dùng tên `dataplex`). Một **DataScan** định nghĩa:

1. **Nguồn**: thường là bảng BigQuery tiêu chuẩn được hỗ trợ trong cùng location.
2. **Rules**: built-in (non-null, uniqueness, set/range, regex) hoặc custom SQL.
3. **Scope**: toàn bảng, row filter, sampling hoặc incremental scan.
4. **Execution**: chạy theo yêu cầu hoặc lịch.
5. **Results**: trạng thái từng rule, dimension score, scan job history; có thể xuất sang BigQuery và publish vào Knowledge Catalog theo quyền hỗ trợ.

~~~mermaid
flowchart LR
    TABLE["BigQuery orders_raw"] --> SCAN["Dataplex DataScan<br/>rule YAML + scope"]
    SCAN --> JOB["Scan job"]
    JOB --> RESULTS["Pass/fail + quality scores"]
    RESULTS --> CAT["Knowledge Catalog scorecard"]
    RESULTS --> EXPORT["BigQuery results table"]
    RESULTS --> ALERT["Cloud Logging / alerts"]
~~~

**Một DataScan không tự xóa hoặc sửa rows lỗi**. Việc quyết định có nạp vào `curated`, ghi quarantine hay ngừng báo cáo thuộc **pipeline/orchestrator**.

### 7.1. Built-in rule và custom SQL khác gì?

| Rule type | Ví dụ | Cách đánh giá |
| --- | --- | --- |
| `nonNullExpectation` | `order_id` bắt buộc | Theo từng hàng |
| `uniquenessExpectation` | `order_id` không trùng | Theo cột/rows |
| `setExpectation` | Region thuộc tập cho phép | Theo từng hàng |
| `rangeExpectation` | `amount_vnd` trong khoảng | Theo từng hàng |
| `regexExpectation` | Mã có định dạng hợp lệ | Theo từng hàng |
| `rowConditionExpectation` | `amount_vnd > 0` | GoogleSQL boolean theo từng hàng |
| `tableConditionExpectation` | `COUNT(*) > 0` | Một boolean ở cấp bảng |
| `sqlAssertion` | Query trả ra rows sai | **Có bất kỳ row nào** trả về thì fail |

**Với `threshold`:** chỉ áp dụng cho các loại **row-level rules**, là tỷ lệ tối thiểu qua kiểm tra. `1.0` = 100%; nếu để `0` theo API thì dùng default **1.0**, không phải “cho qua mọi hàng”.

## 8. Lab: định nghĩa rules bằng YAML

Tạo tệp `dq-rules.yaml` **trên máy người học** (không phải tệp của dự án đang được worker chỉnh sửa):

~~~yaml
rules:
  - name: id-not-null
    dimension: COMPLETENESS
    column: order_id
    nonNullExpectation: {}
    threshold: 1.0

  - name: unique-order-id
    dimension: UNIQUENESS
    column: order_id
    uniquenessExpectation: {}
    ignoreNull: true
    threshold: 1.0

  - name: positive-amount
    dimension: VALIDITY
    rowConditionExpectation:
      sqlExpression: "amount_vnd > 0"
    threshold: 1.0

  - name: allowed-region
    dimension: VALIDITY
    column: sales_region
    setExpectation:
      values: ["APAC", "EMEA", "AMER"]
    threshold: 1.0

  - name: has-rows
    dimension: COMPLETENESS
    tableConditionExpectation:
      sqlExpression: "COUNT(*) > 0"
~~~

**Kỳ vọng:** rules `id-not-null`, `unique-order-id`, `positive-amount` và `allowed-region` fail trên bảng lab, còn `has-rows` pass. Tính năng `ignoreNull` trong rule uniqueness không thay cho rule non-null riêng.

Nếu muốn kiểm thử **độc lập với thời gian**, sử dụng bảng giả lập ở mục 4 và không đặt điều kiện “phải là ngày hôm nay”. Với production, thêm freshness rule theo SLA và chú ý timezone/late arrival.

### 8.1. Tạo và chạy scan bằng gcloud

**Yêu cầu:** project lab có Billing, quyền tạo/chạy DataScan, BigQuery API/Dataplex API và danh tính thực thi đủ quyền truy vấn dữ liệu.

~~~bash
gcloud services enable \
  dataplex.googleapis.com bigquery.googleapis.com \
  --project=PROJECT_ID

gcloud dataplex datascans create data-quality orders-dq-lab \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --data-source-resource="//bigquery.googleapis.com/projects/PROJECT_ID/datasets/dq_lab/tables/orders_raw" \
  --data-quality-spec-file=dq-rules.yaml

gcloud dataplex datascans run orders-dq-lab \
  --project=PROJECT_ID --location=asia-southeast1

gcloud dataplex datascans jobs list \
  --datascan=orders-dq-lab \
  --project=PROJECT_ID --location=asia-southeast1
~~~

Lấy **JOB_ID thật** từ kết quả `jobs list`:

~~~bash
gcloud dataplex datascans jobs describe JOB_ID \
  --datascan=orders-dq-lab \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --view=FULL
~~~

Các lệnh **tạo tài nguyên/chạy scan có phí thật** và chỉ dành cho môi trường lab. Nếu có scan cùng tên từ bài lab khác, hãy kiểm tra owner/config trước, không tự ghi đè. Lệnh `gcloud dataplex datascans ...` vẫn dùng tên Dataplex dù giao diện Console có thể gọi **Knowledge Catalog → Data profiling & quality**.

**Đọc kết quả theo hai lớp:** scan job **SUCCEEDED** chỉ cho biết tiến trình quét thực hiện xong; **data quality passed=false** mới nói rằng một hay nhiều rules không đạt. Không lấy HTTP exit code 0 từ lệnh `run` làm bằng chứng chất lượng dữ liệu pass.

## 9. Lấy mẫu, incremental và freshness

Quét toàn bảng tăng độ bao phủ nhưng có thể đắt trên bảng hàng tỷ rows.

| Phạm vi | Lợi ích | Rủi ro |
| --- | --- | --- |
| **Full scan** | Phát hiện lỗi trên toàn bộ dữ liệu hiện có | Quét nhiều, có thể tốn compute và thời gian |
| **Row filter / partition** | Tập trung batch/ngày cần phát hành | Không nói được chất lượng lịch sử |
| **Sampling** | Chi phí thấp hơn, nhanh hơn với bảng lớn | Có thể bỏ sót lỗi hiếm/khóa trùng |
| **Incremental scan** | Kiểm tra phần dữ liệu mới theo timestamp/date tăng | Bỏ sót backfill hoặc sửa rows cũ nếu thiết kế không tính tới |

Ví dụ rule scope trên bảng partition theo ngày:

~~~yaml
# Thêm vào data-quality spec nếu chỉ kiểm tra batch lab một ngày:
rowFilter: "event_date = DATE '2026-11-18'"
# samplingPercent: 25   # Không dùng khi cần kiểm tra uniqueness nghiêm ngặt.
~~~

**Đây là ví dụ đoạn cấu hình thêm**, không thay thế toàn bộ `dq-rules.yaml`. Trường `rowFilter` là biểu thức **GoogleSQL WHERE**. Khi dùng sampling, rule uniqueness có thể bỏ sót duplicates; không áp ngưỡng production một cách tùy tiện dựa trên sample.

### 9.1. Freshness và completeness là hai SLO khác nhau

Với pipeline liên tục, có thể viết kiểm tra freshness:

~~~sql
SELECT
  COUNT(*) > 0 AS non_empty,
  MAX(ingested_at) >= TIMESTAMP_SUB(
    CURRENT_TIMESTAMP(), INTERVAL 2 HOUR
  ) AS fresh_enough
FROM `PROJECT_ID.dq_lab.orders_raw`;
~~~

`ingested_at` phải phản ánh **thời gian nhận thực tế**, do hệ thống ingestion cấp; không tin timestamp dễ chỉnh sửa từ nguồn ngoài. Bảng lab được insert lúc làm bài nên có thể đạt freshness dù `event_date` cũ — đó là **ingestion freshness**, không phải event timeliness.

**Phân biệt:**

- **Data arrival freshness:** dữ liệu mới đã vào warehouse gần đây chưa?
- **Event timeliness:** dữ liệu đến trễ bao lâu so với thời điểm nghiệp vụ diễn ra?
- **Processing completeness:** có đủ số sự kiện/bản ghi theo manifest/offset/source count không?

Một bảng có `MAX(ingested_at)` mới vẫn có thể **thiếu 90% bản ghi**; cần kiểm tra volume/đối soát riêng.

## 10. Dataform assertions: quality gate cho workflow SQL

**Dataform** phù hợp khi nhóm đã xây mô hình BigQuery bằng SQLX và muốn kiểm tra chất lượng cùng dependency graph. Built-in assertions thường gặp:

- `nonNull`: không để các cột bắt buộc bị NULL.
- `uniqueKey` hoặc `uniqueKeys`: không để trùng khóa.
- `rowConditions`: điều kiện logic trên từng hàng.
- **Manual assertion**: query trả **0 rows** nếu dữ liệu hợp lệ; nếu trả bất kỳ row nào thì **fail**.

Ví dụ trong file `definitions/orders_curated.sqlx` của một Dataform workspace **đã cấu hình**:

~~~sql
config {
  type: "table",
  assertions: {
    nonNull: ["order_id"],
    uniqueKey: ["order_id"],
    rowConditions: [
      "amount_vnd > 0",
      "sales_region IN ('APAC','EMEA','AMER')"
    ]
  }
}

SELECT order_id, sales_region, amount_vnd, event_date
FROM ${ref("orders_stage")}
~~~

`ref("orders_stage")` đòi hỏi action/declaration nguồn tồn tại trong **Dataform repository**; không chạy nguyên khối SQLX này trong BigQuery Studio. Khi workflow chạy, Dataform tạo assertions và có thể ghi nhận lỗi vào assertion views trong BigQuery; **assertion không tự sửa hàng** và không biến bảng BigQuery thành khóa duy nhất có enforcement.

### 10.1. Manual assertion kiểm tra lỗi liên bảng

Tạo file `definitions/order_customer_integrity.sqlx`:

~~~sql
config { type: "assertion" }

SELECT o.order_id
FROM ${ref("orders_curated")} o
LEFT JOIN ${ref("customers")} c USING (customer_id)
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL
~~~

**Đây là ví dụ kiến trúc**, cần các bảng `orders_curated(customer_id)` và `customers(customer_id)` có thật. Query trả rows vi phạm thì assertion fail. Nếu source có late-arriving customers, quy tắc phải có grace period hoặc chuyển thành WARN có chủ đích.

**Phân biệt công cụ:** Dataform assertions phù hợp **đường biến đổi BigQuery bằng SQLX**; Dataplex DataScan phù hợp **quản trị quy tắc và scorecard quét dữ liệu** kể cả ngoài pipeline Dataform. Có thể dùng cả hai nhưng tránh chạy nhiều full scans trùng nhau mà không có mục tiêu.

## 11. Xây quality gate trong orchestration

~~~mermaid
flowchart TD
    INGEST["Ingest batch → staging"] --> SCAN["Run DQ checks"]
    SCAN --> CHECK{"Rules mức BLOCKER đạt?"}
    CHECK -->|Có| RELEASE["Publish / MERGE vào curated"]
    CHECK -->|Không| HOLD["Dừng downstream<br/>quarantine + alert"]
    HOLD --> FIX["Điều tra / sửa nguồn"]
    FIX --> REPLAY["Rerun với batch ID cũ"]
    REPLAY --> SCAN
~~~

**Không tự động “dừng pipeline” chỉ vì một DataScan rule fail**. Gating cần một bước logic do **Workflows, Composer, Cloud Run hoặc Dataform dependencies** điều phối:

1. Chạy ingestion và lưu **batch ID, input object generation, run ID**.
2. Kích hoạt DQ scan/assertions và **đợi kết quả hoàn tất**.
3. Đọc **chất lượng từng rule**, phân loại blocker/warn, không chỉ job state.
4. Nếu blocker fail, ngừng publish curated; lưu báo cáo an toàn, gửi cảnh báo.
5. Nếu pass, chạy transformation/`MERGE` idempotent sang curated.
6. Cho phép **backfill/rerun** với khóa nghiệp vụ và một phiên bản rule có thể truy vết.

**Data quality gate không thay cho data contracts ở nguồn.** Kiểm tra sớm tại Cloud Run schema validation/Pub/Sub consumer sẽ giảm lượng dữ liệu lỗi cần xử lý về sau.

## 12. Quarantine và sửa dữ liệu: không âm thầm xóa

Một quarantine table có thể giữ **khóa bản ghi, batch ID, nguồn, loại lỗi và thời gian phát hiện**, cùng payload chỉ khi có quyền truy cập phù hợp. Không ghi thẳng PII hoặc token vào log/DQ export.

Ví dụ lab tách các rows vi phạm đơn giản:

~~~sql
CREATE TABLE IF NOT EXISTS `PROJECT_ID.dq_lab.orders_quarantine` (
  order_id STRING,
  sales_region STRING,
  amount_vnd INT64,
  event_date DATE,
  reason STRING
);

INSERT INTO `PROJECT_ID.dq_lab.orders_quarantine`
SELECT order_id, sales_region, amount_vnd, event_date,
  CASE
    WHEN order_id IS NULL THEN 'MISSING_ORDER_ID'
    WHEN amount_vnd IS NULL OR amount_vnd <= 0 THEN 'INVALID_AMOUNT'
    ELSE 'INVALID_REGION'
  END AS reason
FROM `PROJECT_ID.dq_lab.orders_raw`
WHERE order_id IS NULL
   OR amount_vnd IS NULL OR amount_vnd <= 0
   OR sales_region IS NULL
   OR sales_region NOT IN ('APAC','EMEA','AMER');
~~~

**Đoạn này không tự xử lý duplicate `o-1004`.** Trước khi phát hành curated, phải chạy thêm uniqueness check và quyết định bản nào là canonical theo version/source timestamp đáng tin cậy.

Quarantine là dữ liệu cần **phân quyền**, TTL/retention và workflow sửa rõ ràng. Sau sửa, nạp lại theo **business ID/batch ID cố định** để tránh tạo hàng trùng khi retry. Không xóa raw input trước khi đối soát và có kế hoạch khôi phục.

## 13. Giám sát quality score, lỗi và xu hướng

Với Knowledge Catalog DataScan, có thể xem:

- **Job history**: lịch sử các lần scan, thời gian, trạng thái chạy.
- **Rule-level result**: từng rule pass/fail và dimension scores.
- **Published quality scorecard** trong Knowledge Catalog nếu bật và cấp quyền.
- **Export results sang BigQuery** cho dashboard/xu hướng nhiều kỳ.
- **Cloud Logging/Monitoring alerts** khi scan failed hoặc data quality score/rule fails theo thiết lập hỗ trợ.

**Một điểm số tổng không đủ để phát hành dữ liệu.** Ví dụ 99,9% quality nhưng có **một giao dịch thanh toán bị nhân đôi** vẫn có thể là blocker. Luôn theo dõi **rule trọng yếu** tách khỏi điểm trung bình.

| Tín hiệu | Ví dụ hành động |
| --- | --- |
| DQ scan job FAILED | Điều tra IAM/BigQuery quota/network/API, không hiểu là dữ liệu bẩn |
| DQ scan SUCCEEDED, quality FAILED | Điều tra hàng vi phạm và nguồn ingest |
| Completeness giảm từ 99,9% xuống 90% | Dừng curated hoặc cảnh báo theo mức nghiêm trọng |
| Uniqueness fail | Dừng publish trước khi `MERGE`, điều tra duplicate publishers/retries |
| Freshness quá SLA | Kiểm tra lịch nguồn/offset, backlog và tiến trình ingestion |
| Volume đột biến giảm 80% | Kiểm tra missing partitions, schema drift, upstream outage |
| DQ score ổn định nhưng số hàng quá ít | Thêm non-empty/volume SLA để tránh “false green” |

Dùng **Cloud Audit Logs** theo dõi ai sửa rules, lịch scan, IAM và schema. Khi kiểm tra rows lỗi, phải dùng query dưới **principal hợp lệ** và tuân thủ RLS/CLS/data masking; quyền xem DataScan result không đương nhiên cho phép xuất toàn bộ PII ra báo cáo công khai.

## 14. IAM, vùng dữ liệu và bảo vệ thông tin

| Thành phần | Quyền nên xem xét |
| --- | --- |
| Người quản lý scan | `dataplex.datascans.create/update/delete` theo phạm vi |
| Người chạy scan | `dataplex.datascans.run` |
| Người xem metadata/rules/results | `dataplex.datascans.get` và `dataplex.datascans.getData` khi cần |
| Execution identity đọc BigQuery | `bigquery.jobs.create`, `bigquery.tables.get/getData` |
| Xuất kết quả sang BigQuery | Quyền ghi destination dataset/table |
| Publish scorecard vào Knowledge Catalog | `bigquery.tables.update` và quyền sử dụng quality scorecard aspect |
| Nguồn GCS external table | Quyền đọc object/bucket phù hợp |

**Không cấp `Owner/Editor` toàn project chỉ vì scan báo `PERMISSION_DENIED`**. Xác định đúng principal: người tạo DataScan và **execution service account** có thể khác nhau. Tách roles vận hành scan khỏi quyền xem dữ liệu nhạy cảm, dùng service account được quản lý trên Cloud Run/GKE, không tải JSON key vào mã nguồn.

**Định vị dữ liệu:** DataScan và BigQuery source phải theo điều kiện region/location được hỗ trợ; kết quả xuất sang dataset đúng location và yêu cầu cư trú. VPC Service Controls/organization policies có thể giới hạn đường truy cập; đừng dùng public bucket hoặc copy PII sang region khác để lách giới hạn.

## 15. Chi phí và tối ưu phạm vi quét

Chi phí DQ gồm cả compute quét dữ liệu và phụ trợ:

- **Knowledge Catalog/Dataplex automatic DQ** có mô hình **Dataplex Compute Unit (DCU)** theo lượng xử lý, tối thiểu theo thời lượng tính phí; chế độ dùng **custom execution identity** có thể chuyển compute/storage charges sang **BigQuery project** theo sản phẩm.
- **BigQuery queries/Dataform assertions** tính theo mô hình BigQuery on-demand bytes processed hoặc reservations/slots, cùng storage.
- **Export results, logs, alerts** có thể phát sinh storage/Logging/Monitoring costs.
- **Scans nhiều vùng/bảng lớn** chịu ảnh hưởng partition, clustering, sampling, rule complexity và lịch chạy.

Ví dụ chọn tần suất:

| Dataset | Kiểm tra | Tần suất hợp lý để thử |
| --- | --- | --- |
| Giao dịch mới mỗi 5 phút | Non-null, positive amount, uniqueness trong batch mới | Sau mỗi batch, chặn phát hành |
| Bảng hàng tỷ rows | Freshness, volume theo partition | Từng partition mới; full scan định kỳ |
| Master customers | Schema, email format, cross-reference | Theo thay đổi và daily scan |
| Báo cáo tài chính tháng | Reconciliation nguồn–đích, sum/unique | Trước khi khóa sổ, yêu cầu 100% |

**Không mặc định sample cho uniqueness/financial reconciliation**: nếu chỉ kiểm 1% data, lỗi hiếm vẫn có thể lọt. Trước khi chạy full scan hàng chục TB, xem bảng giá, BigQuery bytes estimate, quota và ngân sách. **Billing budget alert không phải hard cap**.

## 16. Troubleshooting các lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Create DataScan lỗi | Thiếu `dataplex.datascans.create`, API chưa bật, location sai | Kiểm tra project/region và quyền |
| Run DataScan lỗi `PERMISSION_DENIED` | Execution SA thiếu BigQuery job/table permissions | Kiểm tra IAM của execution principal |
| Scan job chạy thành công nhưng rules fail | Dữ liệu vi phạm threshold | Xem rule results, failing-rows query |
| Scan có điểm rất cao nhưng dữ liệu rỗng | Thiếu rule `COUNT(*) > 0`/volume | Thêm table condition + source reconciliation |
| Uniqueness trên sample vẫn pass | Lấy mẫu bỏ sót duplicate | Full scan/partition logic và business key |
| DQ SQL thấy NULL lạ | `COUNTIF`, 3-valued SQL logic, NULL handling | Dùng `IS NULL` rõ ràng |
| Tình cờ quét cả bảng | Thiếu row filter/partition | Chọn scope, xem bytes processed |
| Dataform assertion pass nhưng báo cáo sai | Quy tắc quá hẹp, dữ liệu sai semantics | Thêm source reconciliation, owner review |
| Quality rules không kích hoạt downstream halt | Chưa cấu hình quality gate | Orchestration đọc status từng rule |
| Rerun thêm dữ liệu trùng | Sink append, không có idempotent MERGE | Batch ID/version + dedupe |
| Failing rows chứa dữ liệu nhạy cảm | Debug query trả nhiều cột | Giới hạn projection, IAM, mask/log policies |
| Chi phí tăng | Scan quá thường xuyên, full scan, nhiều query rules | Partition/incremental/sampling có kiểm soát |

**Quan trọng:** DataScan có thể cung cấp **failingRowsQuery** để điều tra, nhưng câu query này có thể trả **toàn bộ cột** của bảng. Không copy kết quả lên ticket/slack không được bảo vệ; tạo truy vấn chiếu các cột cần thiết nếu có PII.

## 17. Tình huống tổng hợp: báo cáo doanh thu đáng tin cậy

**Bối cảnh:** Java Order API → Pub/Sub → Dataflow/Cloud Storage → BigQuery raw. Dashboard tài chính dùng curated table mỗi sáng. Hôm qua nhà cung cấp đẩy bản ghi trùng do retry; pipeline vẫn báo SUCCEEDED.

Quy trình cải tiến:

1. **Data contract:** quy định `order_id` bắt buộc, `amount_vnd > 0` cho `OrderCreated`, region hợp lệ, event version ổn định.
2. **Validation tại nguồn:** API kiểm tra schema; subscriber xử lý retries idempotently, nhưng vẫn giữ dữ liệu raw để điều tra.
3. **DataScan hàng ngày:** chạy trên partition nhận mới, kiểm tra non-null, validity, unique, nonempty và freshness.
4. **Quality gate:** nếu finance-critical rule fail, không cập nhật curated/BI; gửi cảnh báo kèm RunID/batch ID.
5. **Quarantine:** tách các rows không hợp lệ; sự kiện duplicate được xét theo source/event version thay vì `MAX(amount)`.
6. **Dataform:** assertions ở bảng curated; kiểm tra totals, rows count và referential integrity với nguồn chính.
7. **Observability:** báo cáo score theo rule, freshness lag, số rows cách ly và chi phí scan.
8. **Recovery:** sửa nguồn/logic, rerun cùng batch ID, dùng `MERGE` để không ghi lặp; lưu audit.

**Tiêu chí chấp nhận:** không còn bản ghi trùng trong curated, tổng tiền đối soát với hệ nguồn, data arrives đúng SLA, các lần vi phạm có owner và bằng chứng xử lý. Một dashboard “xanh” chỉ vì SQL job chạy xong **không đáp ứng tiêu chí này**.

## 18. Bài tập và tự kiểm tra

**Bài 1 — Kiểm tra SQL.** Chạy ba truy vấn ở mục 5 trên bảng lab.

*Đạt:* 6 rows, thiếu ID 1, tiền âm 1, region rỗng 1, `o-1004` xuất hiện 2 lần.

**Bài 2 — Dataplex DataScan.** Tạo rules YAML ở mục 8 và chạy scan trong project lab.

*Đạt:* có JOB_ID; phân biệt **job SUCCEEDED** với **data quality failed**, xác định rules nào fail.

**Bài 3 — Ngưỡng.** Đổi threshold của `positive-amount` thành `0.80`. Điều gì thay đổi?

*Đáp án:* 5/6 rows có số tiền dương nên rule có thể pass ở mức 80%; dữ liệu lỗi vẫn tồn tại, chỉ thay **tiêu chí chấp nhận**. Không áp ngưỡng này mặc định cho tài chính production.

**Bài 4 — Quality gate.** Thiết kế Workflows/Composer chỉ chạy curated MERGE sau khi các BLOCKER rules pass.

*Đạt:* scan failure và data quality failure đều không mở đường publish, logs có batch/run ID.

**Câu 5.** Data profiling có chứng minh tất cả giá trị đúng nghiệp vụ không?

*Đáp án:* Không. Profiling mô tả phân bố; rules/owner quyết định giá trị nào được phép.

**Câu 6.** BigQuery `PRIMARY KEY NOT ENFORCED` có tự loại duplicate không?

*Đáp án:* Không. Phải kiểm tra và xử lý ở pipeline.

**Câu 7.** DataScan tự đẩy rows sai vào quarantine không?

*Đáp án:* Không. Scan đo và báo vi phạm; pipeline khác phải triển khai cách ly/gating.

**Câu 8.** Rule `nonNullExpectation` và `uniquenessExpectation` có cùng mục đích?

*Đáp án:* Không. Một rule cấm thiếu giá trị; một rule cấm trùng khóa.

**Câu 9.** Tại sao sampling có thể nguy hiểm cho uniqueness?

*Đáp án:* Những lần xuất hiện trùng có thể rơi ngoài sample, làm sai kết luận.

**Câu 10.** Một scan job SUCCEEDED nhưng quality score FAIL có mâu thuẫn không?

*Đáp án:* Không. Kỹ thuật scan hoàn tất, dữ liệu vi phạm rule.

**Câu 11.** Vì sao freshness dựa vào `ingested_at` chưa chứng minh event đến đúng thời gian?

*Đáp án:* Nó chỉ thể hiện thời điểm vào kho; cần đo cả timestamp nghiệp vụ và độ trễ nguồn→đích.

**Câu 12.** Một Dataform manual assertion đạt khi nào?

*Đáp án:* Query kiểm tra trả **0 rows** vi phạm.

**Câu 13.** Tại sao một tổng quality score cao vẫn có thể phải BLOCK?

*Đáp án:* Một rule trọng yếu như duplicate payment có mức độ rủi ro không thể bù bằng các rule khác.

**Câu 14.** Ai nên được phép xem failingRowsQuery trên bảng có PII?

*Đáp án:* Chỉ principal có quyền dữ liệu cần thiết; phải giới hạn kết quả/log và tuân thủ masking/RLS.

## 19. Checklist trước production

- [ ] Mỗi dataset quan trọng có **owner, contract, schema/version, SLA freshness**.
- [ ] Rule có ID, dimension, logic, threshold, severity và hành động khi fail.
- [ ] Có rule kiểm tra **nonempty/volume**, tránh pass giả trên dataset rỗng.
- [ ] Critical uniqueness/reconciliation không chỉ dựa vào sampling.
- [ ] DataScan scope, location, execution identity và lịch chạy đúng.
- [ ] Dataform assertions gắn với workflow/table dependencies khi dùng SQLX.
- [ ] Quality gate phân biệt **scan execution failure** với **data quality failure**.
- [ ] Quarantine có IAM, PII protection, TTL và quy trình sửa/rerun.
- [ ] Rerun/backfill dùng business key, batch ID và idempotent MERGE.
- [ ] Schema drift, late events, CDC/replay và dữ liệu đến trễ được xử lý.
- [ ] Có alert theo rule trọng yếu, lịch scan, scores và freshness.
- [ ] Query failing rows chỉ chiếu dữ liệu cần thiết; không log secrets/PII.
- [ ] Audit thay đổi rule/schema/IAM, lưu rule version và lịch sử kết quả.
- [ ] Chi phí DCU/BigQuery/Logging được đo theo scan schedule và partition.
- [ ] Staging đã thử data lỗi, thiếu input, duplicates, NULL, outage và rollback.

## 20. Kết luận

**Data quality rules** biến nhận định “dữ liệu tốt” thành điều kiện **có thể kiểm chứng**. Trên Google Cloud, dùng **BigQuery SQL** để điều tra chính xác, **Dataform assertions** để kiểm soát mô hình dữ liệu trong workflow, và **Knowledge Catalog/Dataplex DataScan** để quản lý, quét và theo dõi chất lượng ở quy mô nhiều bảng.

Công thức production ngắn gọn là: **data contract → rules có ngưỡng và owner → quét đúng phạm vi → quality gate → quarantine/đối soát → giám sát và tối ưu chi phí**. Không coi **job chạy thành công** là đồng nghĩa **dữ liệu đã đạt chất lượng**.

## Tài liệu tham khảo chính thức

- [Knowledge Catalog: Automatic data quality](https://cloud.google.com/dataplex/docs/use-auto-data-quality)
- [BigQuery: Scan for data quality issues](https://cloud.google.com/bigquery/docs/data-quality-scan)
- [Dataplex DataQualityRule REST reference](https://cloud.google.com/dataplex/docs/reference/rest/v1/DataQualityRule)
- [Dataplex DataQualitySpec REST reference](https://cloud.google.com/dataplex/docs/reference/rest/v1/DataQualitySpec)
- [gcloud dataplex datascans create data-quality](https://cloud.google.com/sdk/gcloud/reference/dataplex/datascans/create/data-quality)
- [gcloud dataplex datascans run](https://cloud.google.com/sdk/gcloud/reference/dataplex/datascans/run)
- [gcloud dataplex datascans jobs list](https://cloud.google.com/sdk/gcloud/reference/dataplex/datascans/jobs/list)
- [Dataform: Test data with assertions](https://cloud.google.com/dataform/docs/test-data)
- [Dataform core reference](https://cloud.google.com/dataform/docs/reference/dataform-core-reference)
- [BigQuery constraints: NOT ENFORCED](https://cloud.google.com/bigquery/docs/primary-foreign-keys)
- [BigQuery GoogleSQL COUNTIF and SAFE_DIVIDE](https://cloud.google.com/bigquery/docs/reference/standard-sql/aggregate_functions)
- [Knowledge Catalog pricing](https://cloud.google.com/products/knowledge-catalog/pricing)
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing)

