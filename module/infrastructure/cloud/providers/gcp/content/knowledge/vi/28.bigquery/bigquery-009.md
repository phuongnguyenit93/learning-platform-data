# Materialized views, BI Engine và tăng tốc truy vấn

Một ứng dụng Java hiển thị dashboard doanh thu theo ngày và cửa hàng. Dữ liệu đơn hàng nằm trong **BigQuery** với hàng trăm triệu bản ghi; mỗi lần mở trang, cùng một phép `GROUP BY` được chạy lại. Để giảm độ trễ và chi phí, có thể **tổ chức bảng nguồn** bằng partition/clustering, tạo **materialized view** cho kết quả tổng hợp được sử dụng thường xuyên, rồi đánh giá **BI Engine** cho dashboard tương tác có truy vấn phù hợp.

Bài thuộc chương **BigQuery** của học phần **CLOUD_PROVIDERS_GCP**: kết nối lựa chọn dịch vụ dữ liệu với project/IAM, Cloud Run/GKE, tự động hóa phát hành, độ tin cậy và kiểm soát chi phí. Trọng tâm là **phân tích nguyên nhân chậm và chọn cơ chế tăng tốc**, không phải chỉ thuộc các lệnh tạo tài nguyên.

Sau bài học, bạn có thể:

- Phân biệt **logical view**, **materialized view (MV)**, **query-result cache** và **BI Engine**.
- Tạo bảng phân vùng, clustering, materialized view tổng hợp và kiểm tra tính đúng của kết quả.
- Giải thích **incremental refresh**, **smart tuning/query rewrite**, `max_staleness` và các trường hợp phải đọc bảng nguồn.
- Tạo/điều chỉnh BI Engine reservation theo **project và location**, kiểm tra preferred tables và lý do query không tăng tốc.
- Đọc query plan, bytes processed, slot-ms, `materialized_view_statistics` và `bi_engine_statistics` để đánh giá.
- Truy vấn từ ứng dụng Java qua ADC và IAM ít quyền, tránh lỗi phân quyền khi dùng MV.
- Chọn giải pháp theo SLO, tính mới của dữ liệu, chi phí refresh/storage/BI capacity và khả năng rollback.

> **Giới hạn lab:** tên project/dataset là ví dụ, mọi lệnh tạo bảng/MV/reservation chỉ chạy ở project thử nghiệm được cho phép. BI Engine reservation có thể **tính phí ngay cả khi ít truy vấn**; không bật trên production chỉ để đo thử. Tài liệu dùng **GoogleSQL** và một vùng triển khai thống nhất.

## 1. Chẩn đoán trước khi mua thêm công suất

~~~mermaid
flowchart LR
  A["Cloud Run Java API / BI dashboard"] --> Q["BigQuery SQL"]
  Q --> P["Partition pruning + clustering"]
  P --> M["Materialized view: tổng hợp lưu sẵn"]
  M --> E["BI Engine: in-memory, vectorized"]
  E --> R["Kết quả dashboard"]
  Q --> O["Query plan + JOBS_BY_PROJECT"]
  O --> C["Đo P95, bytes, slot-ms, cache-hit, chi phí"]
~~~

Một query chậm có thể do **đọc quá nhiều bytes**, **shuffle/join lớn**, **quét quá nhiều partitions**, **slot contention**, **thời gian trả dữ liệu về client** hoặc SQL không tối ưu. MV và BI Engine chỉ giúp khi dữ liệu/truy vấn **đủ điều kiện**; chúng không tự sửa một query trả về 10 triệu hàng hay một Java API chậm vì Cloud SQL.

| Cơ chế | Lưu gì? | Khi có hiệu lực | Có bảo đảm tăng tốc mọi SQL? |
|---|---|---|---|
| **Partitioning/clustering** | Tổ chức dữ liệu bảng nguồn | Query lọc đúng partition/cluster keys | Không; còn tùy predicate và layout |
| **Logical view** | Định nghĩa SQL | Chạy SQL khi được gọi | Không, bản thân nó không lưu kết quả |
| **Materialized view** | Kết quả SQL đã tính trước và metadata refresh | Query trực tiếp hoặc optimizer rewrite phù hợp | Không; tùy SQL shape, freshness và cost |
| **Query-result cache** | Kết quả truy vấn trước đó | Query có điều kiện cache reuse | Không; có thể bị invalidated hoặc không đủ điều kiện |
| **BI Engine** | Dữ liệu/cột hay dùng trong bộ nhớ theo reservation | Query được hỗ trợ và có capacity hợp lệ | Không; có thể FULL/PARTIAL/FALLBACK |
| **Slot reservation/edition** | Công suất compute cho query jobs | Workload cần đủ compute/concurrency | Không; không loại bỏ scan thừa |

Thứ tự ưu tiên thường là **đo → lọc cột/partition → giảm dữ liệu trước JOIN → xem query plan → cân nhắc MV → cân nhắc BI Engine**. Tránh khởi tạo reservation trước khi biết dashboard cần tables/columns nào.

## 2. Lab thống nhất: dashboard doanh thu cửa hàng

Ví dụ tạo dataset tại **`asia-southeast1`**; thực thi trên Bash/Cloud Shell với tài khoản có quyền tạo dataset/table/query trong project lab.

~~~bash
PROJECT_ID="my-bigquery-lab"
LOCATION="asia-southeast1"
DATASET="analytics_lab"

gcloud config set project "$PROJECT_ID"
gcloud services enable bigquery.googleapis.com
bq --location="$LOCATION" mk --dataset "$PROJECT_ID:$DATASET"
~~~

Nếu dataset đã tồn tại, kiểm tra location và owner, **không tạo trùng**. Dataset cùng tên nhưng ở vùng khác không thể được query/job trong một location không khớp; BI Engine capacity cũng phải ở location tương ứng. Quyền tạo dataset và table khác quyền đọc dữ liệu sản xuất.

### Bước 1 — tạo bảng phân vùng và dữ liệu giả

Chạy script SQL sau trong BigQuery Studio tại location `asia-southeast1`; thay **`MY_PROJECT`** bằng project lab thật trước khi chạy:

~~~sql
CREATE OR REPLACE TABLE `MY_PROJECT.analytics_lab.orders` (
  order_id STRING NOT NULL,
  order_date DATE NOT NULL,
  store_id STRING NOT NULL,
  amount NUMERIC NOT NULL,
  status STRING NOT NULL
)
PARTITION BY order_date
CLUSTER BY store_id;

INSERT INTO `MY_PROJECT.analytics_lab.orders`
  (order_id, order_date, store_id, amount, status)
SELECT
  FORMAT('ORD-%06d', n),
  DATE_ADD(DATE '2026-11-01', INTERVAL MOD(n, 14) DAY),
  CONCAT('STORE-', CAST(1 + MOD(n, 10) AS STRING)),
  CAST(10 + MOD(n, 150) AS NUMERIC),
  IF(MOD(n, 7) = 0, 'CANCELLED', 'PAID')
FROM UNNEST(GENERATE_ARRAY(1, 10000)) AS n;
~~~

Dữ liệu gồm **10.000 đơn giả**, 14 ngày, 10 cửa hàng và hai trạng thái. `NUMERIC` tránh sai số floating-point khi cộng doanh thu; trong hệ thống tiền tệ thật, xác định rõ currency, mức làm tròn và refunds. Việc chạy lại `INSERT` sẽ **nhân đôi dữ liệu**; nếu muốn làm lại lab, dùng project/bảng thử nghiệm và quy trình reset có kiểm soát.

~~~sql
SELECT COUNT(*) AS rows_total,
       COUNTIF(status = 'PAID') AS paid_rows,
       MIN(order_date) AS min_day,
       MAX(order_date) AS max_day
FROM `MY_PROJECT.analytics_lab.orders`;
~~~

**Kỳ vọng:** 10.000 rows, `min_day = 2026-11-01` và `max_day = 2026-11-14`. Mục tiêu lab là so sánh **cơ chế** chứ không chứng minh tăng tốc bằng vài nghìn dòng: với bảng nhỏ, MV có thể không được chọn vì optimizer thấy đọc base table đã rẻ.

### Bước 2 — baseline query trên bảng gốc

~~~sql
SELECT
  order_date,
  store_id,
  COUNT(*) AS paid_orders,
  SUM(amount) AS revenue
FROM `MY_PROJECT.analytics_lab.orders`
WHERE status = 'PAID'
  AND order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-07'
GROUP BY order_date, store_id
ORDER BY order_date, store_id;
~~~

Đây là query **có partition pruning** vì lọc trực tiếp `order_date`. `CLUSTER BY store_id` giúp khi truy vấn còn lọc/nhóm theo cửa hàng và có đủ dữ liệu để layout phát huy tác dụng. Tránh `SELECT *`, tránh quét tất cả ngày rồi mới lọc ngoài một subquery, và không kỳ vọng `LIMIT 100` trên bảng lớn tự giảm bytes scanned.

**Phép đo đầu tiên:** trong BigQuery Console, xem **Execution details → Query plan**, `total bytes processed`, `slot-ms`, query latency và cache hit. Cùng một SQL có thể chậm khác nhau vì số job chạy đồng thời, slot availability và kết quả cache; phải đo nhiều lần và kiểm soát điều kiện so sánh.

## 3. Materialized view giải quyết điều gì?

**Materialized view** lưu trước kết quả một phép tính được dùng lại. Với daily revenue, thay vì mỗi dashboard request phải đọc hàng triệu orders rồi `GROUP BY`, có thể đọc tập kết quả nhỏ theo `order_date, store_id`.

~~~text
orders (bảng lớn, cập nhật liên tục)
   │ SELECT order_date, store_id, COUNT(*), SUM(amount)
   ▼
mv_paid_daily (tổng hợp lưu sẵn, có refresh)
   │
   ├── SELECT trực tiếp từ MV
   └── BigQuery smart tuning: query base table được rewrite khi phù hợp
~~~

BigQuery hỗ trợ **incremental materialized views** cho những SQL patterns đáp ứng điều kiện. Khi base table chủ yếu **append**, BigQuery có thể refresh phần thay đổi thay vì tính lại toàn bộ. Với updates/deletes hoặc một số joins, MV có thể bị invalidated/full refresh hoặc truy vấn phải đọc base table. **Không mặc định mọi materialized view đều incremental**.

### Bước 3 — tạo MV tổng hợp có partition alignment

~~~sql
CREATE MATERIALIZED VIEW `MY_PROJECT.analytics_lab.mv_paid_daily`
PARTITION BY order_date
CLUSTER BY store_id
OPTIONS (
  enable_refresh = TRUE,
  refresh_interval_minutes = 60
)
AS
SELECT
  order_date,
  store_id,
  COUNT(*) AS paid_orders,
  SUM(amount) AS revenue
FROM `MY_PROJECT.analytics_lab.orders`
WHERE status = 'PAID'
GROUP BY order_date, store_id;
~~~

- `PARTITION BY order_date` của MV khớp với partitioning trên bảng gốc, giúp refresh và query chỉ liên quan các partitions cần thiết.
- `CLUSTER BY store_id` áp theo **output column không phải aggregate**, hỗ trợ workload thường lọc theo store.
- `refresh_interval_minutes = 60` yêu cầu lịch refresh **không thường xuyên hơn mỗi 60 phút**; đây **không phải cam kết** dữ liệu chỉ trễ tối đa đúng 60 phút.
- MV có storage/refresh cost. Nếu dữ liệu nguồn quá nhỏ hoặc ít dashboard users, lợi ích có thể không đủ bù phí.

### Bước 4 — đọc trực tiếp và kiểm tra đối soát

~~~sql
SELECT order_date, store_id, paid_orders, revenue
FROM `MY_PROJECT.analytics_lab.mv_paid_daily`
WHERE order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-07'
ORDER BY order_date, store_id;

-- Mỗi ngày/cửa hàng trong lab cần khớp với baseline.
WITH raw AS (
  SELECT order_date, store_id,
         COUNT(*) AS paid_orders, SUM(amount) AS revenue
  FROM `MY_PROJECT.analytics_lab.orders`
  WHERE status = 'PAID'
  GROUP BY order_date, store_id
),
agg AS (
  SELECT order_date, store_id, paid_orders, revenue
  FROM `MY_PROJECT.analytics_lab.mv_paid_daily`
)
SELECT COALESCE(raw.order_date, agg.order_date) AS day,
       COALESCE(raw.store_id, agg.store_id) AS store_id,
       raw.paid_orders AS base_count, agg.paid_orders AS mv_count,
       raw.revenue AS base_revenue, agg.revenue AS mv_revenue
FROM raw FULL OUTER JOIN agg
  ON raw.order_date = agg.order_date
 AND raw.store_id = agg.store_id
WHERE raw.paid_orders IS DISTINCT FROM agg.paid_orders
   OR raw.revenue IS DISTINCT FROM agg.revenue;
~~~

Kết quả đối soát mong đợi: **0 hàng** khi không có ghi mới trong lúc so sánh và MV được đọc với ngữ nghĩa freshness mặc định. Với nguồn liên tục thay đổi, hai SELECT độc lập có thể nhìn thấy **snapshot thời điểm khác nhau**; muốn đánh giá chính xác phải cố định dữ liệu, thời điểm/snapshot hoặc xem cơ chế time travel phù hợp, không kết luận hệ thống sai chỉ vì race giữa hai query.

## 4. Smart tuning và giới hạn query rewrite

**Smart tuning** là khả năng BigQuery **tự viết lại** một query trên bảng nguồn để dùng MV, dù SQL **không nhắc đến tên MV**. Việc rewrite là lựa chọn của optimizer, không phải bảo đảm mọi query liên quan đều được tăng tốc.

Điều kiện tham khảo:

- MV phải nằm trong project chứa một bảng nguồn của query hoặc project chạy query.
- Query và MV dùng **cùng tập bảng nguồn**, MV cung cấp **đủ cột và đủ hàng** mà query cần.
- Các phép tổng hợp, JOIN, filter và chính sách bảo mật phải đủ điều kiện; optimizer còn xét **chi phí** và tính mới.
- Không có smart tuning với **non-incremental MV**, MV chứa `UNION ALL`/`LEFT OUTER JOIN`, MV tham chiếu logical view hoặc các bảng CDC theo các trường hợp tài liệu mô tả.

### Ví dụ rewrite có khả năng dùng MV

~~~sql
-- Query trên bảng nguồn, không tham chiếu mv_paid_daily.
SELECT order_date, store_id,
       COUNT(*) AS paid_orders, SUM(amount) AS revenue
FROM `MY_PROJECT.analytics_lab.orders`
WHERE status = 'PAID'
  AND order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-07'
GROUP BY order_date, store_id;
~~~

MV của lab đã chứa `order_date`, `store_id`, `COUNT(*)` và `SUM(amount)` cho đúng các hàng `status='PAID'`. Đây là **ứng viên** để optimizer dùng MV; với 10.000 records, nó **có thể vẫn đọc bảng gốc** vì ít chi phí hơn.

Ngược lại, các query dưới đây **không được MV giải quyết đầy đủ**:

~~~sql
-- (A) Cần tổng ALL orders, nhưng MV chỉ có status PAID.
SELECT order_date, SUM(amount)
FROM `MY_PROJECT.analytics_lab.orders`
GROUP BY order_date;

-- (B) Cần lọc theo order_id, nhưng MV không giữ order_id.
SELECT order_id, amount
FROM `MY_PROJECT.analytics_lab.orders`
WHERE order_id = 'ORD-000042';
~~~

MV không phải index cho mọi predicate. Nếu dashboard còn cần `status='CANCELLED'` hay từng `order_id`, hãy chọn thêm bảng tổng hợp/mô hình đọc phù hợp; không dùng một MV duy nhất để hứa đáp ứng cả hai.

### Xác nhận optimizer có dùng MV không

Trong BigQuery Console, mở **Execution details → Query plan**. Nếu smart tuning dùng MV, plan có thể xuất hiện `READ ...mv_paid_daily`. Nếu không, đọc statistics của job để xem MV có được xét/chọn hay bị loại:

~~~sql
SELECT
  creation_time,
  job_id,
  total_bytes_processed,
  total_slot_ms,
  cache_hit,
  TO_JSON_STRING(materialized_view_statistics) AS mv_stats
FROM `MY_PROJECT.region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND job_type = 'QUERY'
ORDER BY creation_time DESC
LIMIT 30;
~~~

Trong `materialized_view_statistics`, xem các trường như `chosen` và `rejected_reason`. Ví dụ `COST` có thể có nghĩa optimizer thấy cách khác rẻ hơn. **Không ép mọi query phải dùng MV** chỉ vì MV đã tồn tại; thử trực tiếp MV và đối chiếu latency/bytes/slot-ms.

## 5. Refresh, incremental maintenance và tính mới của dữ liệu

### Ba khái niệm cần phân biệt

| Khái niệm | Tác động | Điều **không** có nghĩa |
|---|---|---|
| **Automatic refresh** | BigQuery cập nhật kết quả vật lý của MV trong nền | Không phải job được chạy chính xác vào mỗi mốc phút |
| **Incremental maintenance** | Có thể tính dựa trên phần thay đổi của base tables | Không phải mọi DML/update/delete đều incremental |
| **Query trực tiếp MV mặc định** | BigQuery có thể kết hợp MV và thay đổi chưa refresh để trả dữ liệu mới | Không nhất thiết chỉ đọc storage của MV |
| **`max_staleness`** | Cho phép direct MV query trả dữ liệu với độ trễ được chấp nhận để tăng tốc | Không bảo đảm job refresh luôn xong trong khoảng đó |
| **Smart tuning trên base query** | Optimizer có thể dùng MV mà vẫn giữ semantics query nguồn | `max_staleness` của MV **không** làm thay đổi kết quả query được rewrite |

Với base table **append-only** và aggregate được hỗ trợ, BigQuery thường có thể cập nhật MV từ các dòng mới. Khi update/delete làm mất hiệu lực phần vật hóa, engine có thể phải đọc bảng nguồn, refresh lại nhiều dữ liệu hoặc không chọn MV; các joins cũng có điều kiện incremental riêng. Nếu workload chủ yếu sửa những partition cũ mỗi giờ, cần đo lại hiệu quả MV.

### Bật staleness có kiểm soát

Dashboard chấp nhận dữ liệu trễ tối đa **4 giờ**. Có thể chỉnh MV:

~~~sql
ALTER MATERIALIZED VIEW `MY_PROJECT.analytics_lab.mv_paid_daily`
SET OPTIONS (
  enable_refresh = TRUE,
  refresh_interval_minutes = 120,
  max_staleness = INTERVAL '4' HOUR
);
~~~

Khi **truy vấn trực tiếp MV**, nếu lần refresh gần đây nằm trong `max_staleness`, query có thể đọc kết quả vật hóa mà không phải hòa phần mới từ base table. Nếu refresh đã cũ hơn khoảng đó, BigQuery có thể phải kết hợp dữ liệu nguồn và MV; **không phải cứ quá 4 giờ thì hệ thống trả lỗi ngay**. Tuy nhiên streaming buffers và một số loại MV/nguồn dữ liệu có giới hạn riêng; nếu refresh bị ngừng quá lâu, khả năng query lỗi/phải scan tăng lên.

**Điểm cực quan trọng:** `max_staleness` **không ảnh hưởng** đến semantics của query trên base table mà được **smart tuning rewrite**. Muốn dashboard có hợp đồng “được dùng bản tổng hợp trễ tối đa 4 giờ”, hãy thiết kế nó **truy vấn trực tiếp MV**, test kết quả và đo freshness.

### Kiểm tra refresh sau DML

~~~sql
-- Thêm một order vào ngày lab để thử.
INSERT INTO `MY_PROJECT.analytics_lab.orders`
  (order_id, order_date, store_id, amount, status)
VALUES ('ORD-EXTRA-1', DATE '2026-11-07',
        'STORE-1', NUMERIC '125.00', 'PAID');

-- Truy vấn MV trực tiếp với policy hiện tại:
SELECT order_date, store_id, paid_orders, revenue
FROM `MY_PROJECT.analytics_lab.mv_paid_daily`
WHERE order_date = DATE '2026-11-07' AND store_id = 'STORE-1';
~~~

Nếu đã bật `max_staleness`, dashboard **có thể chưa thấy** order mới cho đến lần refresh. Chạy lại `INSERT` sẽ tạo trùng `order_id` vì BigQuery không enforce primary key như một OLTP database; chỉ insert **một lần** hoặc dùng dữ liệu thử có unique ID/quy trình reset. Khi cần chính xác đến từng giao dịch ngay tức thời, xem xét đường đọc transactional (Spanner/Cloud SQL) thay vì chỉ dựa vào tổng hợp BI.

### MV không incremental: lựa chọn có đánh đổi

BigQuery còn có `allow_non_incremental_definition = true` cho một số SQL phức tạp, **phải cấu hình `max_staleness`**. Loại này refresh **toàn bộ** thay vì incremental, **không được smart tuning**, chỉ có lợi khi query **trực tiếp** MV. Nếu phải refresh toàn bộ một nguồn vài TB mỗi giờ, có thể tốn hơn lợi ích dashboard; cân nhắc scheduled query/ETL + bảng tổng hợp có lịch rõ ràng.

## 6. BI Engine: bộ nhớ tăng tốc truy vấn tương tác

**BigQuery BI Engine** sử dụng **in-memory vectorized execution** để tăng tốc một số truy vấn `SELECT`. Khác MV, BI Engine **không định nghĩa lại tổng hợp**: nó cấp vùng nhớ theo **project/location** và tự tải các cột/partition cần cho các query đủ điều kiện.

~~~text
Dashboard / Java BI API
       │ SQL SELECT
       ▼
BigQuery query optimizer
       ├── query-result cache (nếu đủ điều kiện)
       ├── MV rewrite/direct MV (nếu phù hợp)
       └── BI Engine in-memory + vectorized execution
             └── fallback to regular BigQuery slots khi không hỗ trợ/thiếu RAM
~~~

| Tình huống | BI Engine có thể có lợi? | Lưu ý |
|---|---|---|
| Dashboard lặp lại nhiều câu `SELECT` trên bảng/MV nhỏ, phổ biến | **Có** | Đo tỷ lệ FULL/PARTIAL acceleration |
| Cột cần đọc ít, lọc theo ngày/cửa hàng | **Có** | Có thể cache partitions/columns hay dùng |
| Wildcard tables `orders_*` | **Không** | Không được BI Engine hỗ trợ |
| External tables, non-SQL UDF, một số SQL features | **Hạn chế/không** | Xem reasons trong job stats |
| Row-level security trên bảng | **Không** với hỗ trợ BI Engine hiện hành | Thiết kế auth và đo fallback |
| Nhiều JOIN lớn, scan các bảng không được cache | **Không chắc** | Dùng pre-aggregation/MV hoặc tối ưu JOIN |
| Nhiều tài khoản chạy query ở regions khác nhau | Phải có capacity **đúng location** | Một reservation ở Singapore không tăng tốc region US |

BI Engine **không phải Redis cache** mà Java ứng dụng tự đọc/ghi; không cần app gọi một API cache riêng. Backend Java vẫn gửi GoogleSQL qua BigQuery client thông thường, BI Engine quyết định phần xử lý được tăng tốc.

### Preferred tables

Bạn có thể chỉ định **preferred tables** để dành capacity cho những bảng ưu tiên. Khi có preferred tables:

- Các query dùng bảng ngoài danh sách không được hưởng BI Engine reservation đó.
- Một query JOIN nhiều tables thường chỉ được tăng tốc khi **tất cả bảng tham gia** nằm trong preferred list.
- **Query trực tiếp MV** cần đưa **cả MV và bảng nguồn** vào preferred list để đủ điều kiện BI Engine acceleration.
- Logical views không thể là preferred table; `JSON` columns không được hỗ trợ tăng tốc tương ứng.
- BI Engine cache có thể chỉ chứa các cột/partitions đang cần; **1 GiB không đồng nghĩa bảng nguồn phải bé hơn 1 GiB**, nhưng dung lượng không đủ có thể khiến nhiều truy vấn fallback.

### Tạo BI Engine reservation trong lab (tùy chọn có tính phí)

Chỉ thực hiện nếu đã được phê duyệt ngân sách và dự đoán capacity tối thiểu. Ví dụ SQL này **tạo hoặc chỉnh** reservation `default` trong project/vùng (nếu đã có sẽ thay đổi cấu hình hiện hữu):

~~~sql
ALTER BI_CAPACITY `MY_PROJECT.region-asia-southeast1.default`
SET OPTIONS (
  size_gb = 1,
  preferred_tables = [
    `MY_PROJECT.analytics_lab.orders`,
    `MY_PROJECT.analytics_lab.mv_paid_daily`
  ]
);
~~~

**Đừng chạy lệnh trên dự án chia sẻ** nếu chưa kiểm tra reservation đang tồn tại và owner. `size_gb=1` là dung lượng cấp phát minh họa, không phải recommendation sizing cho production. Trong Console vào **BigQuery → BI Engine**, chọn project/location, dung lượng và preferred tables; cần role/permission quản lý BI reservation tương ứng.

Kiểm tra trạng thái và lịch sử thay đổi:

~~~sql
SELECT *
FROM `MY_PROJECT.region-asia-southeast1.INFORMATION_SCHEMA.BI_CAPACITIES`;

SELECT *
FROM `MY_PROJECT.region-asia-southeast1.INFORMATION_SCHEMA.BI_CAPACITY_CHANGES`
ORDER BY change_timestamp DESC
LIMIT 10;
~~~

Mức BI Engine acceleration được quyết định theo từng query, có thể là **FULL**, **PARTIAL**, **FULL_INPUT**, hoặc **DISABLED** tùy query plan và statistics. Không dùng việc “reservation tồn tại” làm bằng chứng dashboard đã được tăng tốc.

## 7. Giám sát MV, BI Engine và query plan

### Xác nhận MV refresh thành công

~~~sql
SELECT
  table_name,
  last_refresh_time,
  refresh_watermark,
  last_refresh_status
FROM `MY_PROJECT.analytics_lab.INFORMATION_SCHEMA.MATERIALIZED_VIEWS`
WHERE table_name = 'mv_paid_daily';
~~~

`last_refresh_time` là thời điểm refresh được thực hiện; `refresh_watermark` cho biết dữ liệu nguồn tới mốc nào đã được tính vào kết quả vật hóa. Hai thời điểm có thể khác nhau; nếu nguồn không đổi, watermark có thể vẫn tiến lên mà không cần refresh vật lý. `last_refresh_status IS NOT NULL` thường báo lỗi refresh tự động, cần xem chi tiết và query job tương ứng.

Để tìm automatic refresh jobs:

~~~sql
SELECT job_id, creation_time, state, error_result,
       total_bytes_processed, total_slot_ms
FROM `MY_PROJECT.region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  AND job_id LIKE '%materialized_view_refresh_%'
ORDER BY creation_time DESC
LIMIT 50;
~~~

Refresh nhiều bytes khi data ít thay đổi có thể chỉ ra base table bị cập nhật/xóa, partition bị expire, MV phải full refresh, hoặc SQL không thích hợp incremental. Đừng đo kết quả dựa riêng vào một lần query rất nhanh do query-result cache.

### Xác nhận BI Engine thực sự tăng tốc

~~~sql
SELECT
  creation_time,
  job_id,
  cache_hit,
  total_bytes_processed,
  total_slot_ms,
  TO_JSON_STRING(bi_engine_statistics) AS bi_stats,
  TO_JSON_STRING(materialized_view_statistics) AS mv_stats
FROM `MY_PROJECT.region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND job_type = 'QUERY'
ORDER BY creation_time DESC
LIMIT 50;
~~~

Trong dữ liệu API/`INFORMATION_SCHEMA`:

- `biEngineMode` thường nhận `FULL`, `PARTIAL` hoặc `DISABLED`. `accelerationMode` chi tiết hơn: `FULL_QUERY`, `FULL_INPUT`, `PARTIAL_INPUT` hoặc `BI_ENGINE_DISABLED`.
- Nếu không tăng tốc, đọc `biEngineReasons`: `NO_RESERVATION`, `INSUFFICIENT_RESERVATION`, `TABLE_EXCLUDED`, `INPUT_TOO_LARGE`, `UNSUPPORTED_SQL_TEXT` v.v.
- `cache_hit = TRUE` cho thấy query-result cache có thể khiến bài đo quá lạc quan; để kiểm tra tác động BI Engine, chạy cùng query với **Use cached results = OFF**.
- `total_slot_ms`, `total_bytes_processed` và elapsed time phản ánh các mặt khác nhau của tải; một query dùng BI Engine có thể báo slot usage khác regular BigQuery và không nên suy giá tiền chỉ từ slot-ms.

Query theo `JOBS_BY_PROJECT` thường cần quyền xem metadata jobs của project và có thể lộ SQL chứa dữ liệu nhạy cảm. Nhóm ứng dụng chỉ được xem jobs của chính mình nên ưu tiên `JOBS_BY_USER`/job logs đúng phạm vi; dành dashboard toàn project cho SRE/data admins.

### BI Engine capacity đang dùng

Theo dõi Cloud Monitoring metrics của BigQuery BI Engine, đặc biệt **reserved/used bytes**, memory pressure, query acceleration, project/location. Khi `used_bytes` đạt gần reservation và query fallback, có thể tăng capacity **hoặc** tối ưu column selection, preferred tables, pre-aggregation. Không tăng RAM cho một query dùng SQL unsupported; phải sửa query trước.

## 8. Từ Java Cloud Run gọi BigQuery đúng cách

Một Java dashboard API có thể truy vấn thẳng MV bằng **BigQuery Java client**. Với production, cân nhắc backend cache theo TTL ngắn, giới hạn request rate và không để một HTTP request mở quá lâu để chờ một query nặng. Ví dụ sau dùng thư viện `com.google.cloud:google-cloud-bigquery`, Java 17+, project lab và **Application Default Credentials (ADC)** của runtime.

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.BigQueryOptions;
import com.google.cloud.bigquery.FieldValueList;
import com.google.cloud.bigquery.QueryJobConfiguration;
import com.google.cloud.bigquery.QueryParameterValue;
import com.google.cloud.bigquery.TableResult;

public final class RevenueDashboard {
    public static void main(String[] args) throws InterruptedException {
        // Ví dụ: projectId phải đến từ config được kiểm tra,
        // không nối nguyên chuỗi SQL từ input không tin cậy.
        String projectId = "my-bigquery-lab";
        BigQuery bigquery = BigQueryOptions.newBuilder()
            .setProjectId(projectId)
            .build()
            .getService();

        // Đọc TRỰC TIẾP materialized view; không cần rewrite tự động.
        String sql = """
            SELECT order_date, store_id, paid_orders, revenue
            FROM `MY_PROJECT.analytics_lab.mv_paid_daily`
            WHERE order_date BETWEEN @from_date AND @to_date
            ORDER BY order_date, store_id
            """.replace("MY_PROJECT", projectId);

        QueryJobConfiguration config = QueryJobConfiguration.newBuilder(sql)
            .addNamedParameter("from_date",
                QueryParameterValue.date("2026-11-01"))
            .addNamedParameter("to_date",
                QueryParameterValue.date("2026-11-07"))
            .setUseLegacySql(false)
            .setUseQueryCache(false) // chỉ để benchmark; tùy nhu cầu production
            .setMaximumBytesBilled(1_000_000_000L) // safety cap on-demand
            .build();

        TableResult result = bigquery.query(config);
        for (FieldValueList row : result.iterateAll()) {
            System.out.printf("%s | %s | %d | %s%n",
                row.get("order_date").getStringValue(),
                row.get("store_id").getStringValue(),
                row.get("paid_orders").getLongValue(),
                row.get("revenue").getNumericValue());
        }
    }
}
~~~

**Điểm thiết kế:**

- Câu SQL đặt **tên bảng cố định trong cấu hình server**; hai ngày được bind bằng `QueryParameterValue`, không nối request input vào SQL để tránh injection.
- BigQuery client dùng ADC (Cloud Run `--service-account`, GKE Workload Identity Federation); không tải key JSON vào container.
- Với dữ liệu thật, **không tin project ID/tenant ID do client tự gửi** để định tuyến đến bất kỳ dataset nào. Java phải xác minh authorization và chỉ cho truy vấn những dataset đã được cấp quyền.
- `setMaximumBytesBilled` giúp chặn query on-demand vượt giới hạn bytes billed được cho phép; **không thay mọi loại budget/quota và không tự giới hạn phí BI Engine reservation**.
- Java nên kiểm soát request timeout, job polling, pagination, cancellation, rate limit và Cloud Run concurrency. Với query dài, tạo job bất đồng bộ rồi trả job ID có phân quyền xem kết quả.
- Trong hệ thống BigQuery đa vùng, truyền **location chính xác** khi tạo job (qua JobId/JobInfo theo phiên bản SDK) và giữ query cùng location dataset/reservation; đừng để cấu hình môi trường ngầm dùng vùng khác.
- BI Engine cũng đòi **edition/region được hỗ trợ**; xác minh entitlement, quota và chính sách cấp capacity trước khi bật reservation, không chỉ kiểm tra tên dataset.

### IAM cho Java và công việc biên tập dữ liệu

| Danh tính | Quyền thường cần | Nguyên tắc |
|---|---|---|
| Cloud Run runtime SA | `roles/bigquery.jobUser` ở query/billing project; `roles/bigquery.dataViewer` trên dataset/bảng/MV cần đọc | Không cấp `BigQuery Admin` chỉ để đọc doanh thu |
| Data engineer / CI DDL | Quyền tạo table/MV/alter (ví dụ `bigquery.tables.create` và update phù hợp) | Tách khỏi runtime app |
| BI Engine capacity admin | Quyền quản lý BI reservations/capacity | Không cấp cho Java dashboard |
| SRE/FinOps | Metadata jobs, MV refresh, BI capacity, monitoring và billing | Hạn chế truy cập SQL chứa PII |

**Quyền MV phụ thuộc nguồn dữ liệu:** đọc materialized view thông thường phải xét quyền trên MV và underlying tables; nếu cần chia sẻ aggregates mà **không cấp quyền bảng nguồn**, dùng mô hình **authorized materialized view** theo hướng dẫn. Không mặc định chỉ grant `Data Viewer` trên MV là đủ cho mọi cấu hình.

### Row-level/column-level security

Nếu bảng nguồn dùng **row-level access policies**, kết quả query MV vẫn phải tôn trọng chính sách hàng; BigQuery có thể **không đem lại lợi ích performance như MV bình thường** và BI Engine có giới hạn hỗ trợ. Nếu có **column-level access controls/data masking**, kiểm tra quyền và query shape trước khi đánh giá tăng tốc. Không bỏ RLS hoặc mở IAM rộng chỉ để ép query dùng BI Engine.

## 9. Benchmark và tối ưu query theo số đo

### Bộ phép thử tối thiểu

| Test | Query | Cần ghi lại |
|---|---|---|
| A | Baseline aggregate trên `orders` | P50/P95 latency, bytes scanned/billed, slot-ms |
| B | Query trực tiếp `mv_paid_daily` | Same metrics, refresh status/watermark |
| C | Query lại base SQL, có MV trong project | `materialized_view_statistics.chosen`, latency, cost |
| D | Sau khi bật BI Engine 1 GiB, query MV/base phù hợp | `biEngineMode`/`accelerationMode`, fallback reason |
| E | Query không đủ điều kiện (wildcard table/JOIN unsupported) | Lý do DISABLED và chi phí fallback |

Quy trình đo:

1. **Cố định workload và dataset/location**; chụp query text, row count, partition filters, concurrency và pricing mode.
2. **Tắt cached query results** khi so sánh tác động MV/BI Engine, vì cache kết quả cũ có thể trả rất nhanh mà không thể quy công cho BI Engine.
3. Chạy nhiều lần ở các thời điểm tải tương đương; so sánh **P50/P95** thay vì một lần nhanh nhất. Đo riêng query cold/warm sau khi BI cache nạp dữ liệu.
4. Kiểm tra correctness và freshness; nếu bật `max_staleness`, yêu cầu dashboard phải ghi rõ “Cập nhật đến…” hoặc có hợp đồng độ trễ.
5. Tính tổng phí **refresh + MV storage + BI reservation + query/billed bytes + downstream**. Không chỉ so latency.
6. Quyết định giữ hoặc tháo MV/BI Engine theo SLO và tiết kiệm ròng trong workload thực.

### Những tối ưu chi phí thấp cần thử trước

| Dấu hiệu ở query plan | Hành động nên thử |
|---|---|
| `READ` nhiều bytes từ bảng nhiều năm | Lọc partition column `order_date` trực tiếp; chọn cột cần thiết |
| Nhiều `shuffle bytes` sau JOIN | Aggregate/filter sớm, tránh JOIN bảng fact cực lớn trước khi nhóm |
| Query scan bảng nhưng chỉ cần vài giá trị | Cân nhắc clustering, search index hoặc thiết kế lookup phù hợp |
| Job chờ slots lâu, P95 cao khi concurrency tăng | Đánh giá reservations/edition/capacity thay vì chỉ thêm MV |
| Query lặp cùng phép aggregate từ nhiều dashboard | MV hoặc scheduled aggregate table |
| Dashboard có nhiều số liệu gần thời gian thực | BI Engine nếu workload/SQL hỗ trợ; kiểm tra fallback và freshness |
| Java trả quá nhiều rows | Pagination, giới hạn output, aggregation trong BigQuery |
| Query refresh/MV đắt hơn lợi ích | Giảm refresh frequency, dùng batching hoặc scheduled query |

**Khi nào dùng scheduled query thay MV?** Nếu phép tổng hợp rất phức tạp, có logic ETL cần kiểm soát, chỉ cần cập nhật theo ngày và cần kết quả vật hóa ở bảng riêng, scheduled query thường đơn giản hơn về semantics. Nhưng mỗi scheduled run có thể tính toán lại nhiều dữ liệu; MV incremental có lợi khi aggregate lặp lại và dữ liệu append nhiều.

## 10. Chi phí, SLO và quyết định triển khai

Chi phí “tăng tốc” phải tính trên **toàn hệ thống**, không chỉ một query:

~~~text
Tổng chi phí liên quan
  = lưu trữ BigQuery base tables và materialized results
  + query compute (on-demand bytes billed hoặc editions/slots)
  + MV automatic/manual refresh compute
  + BI Engine capacity reservation theo thời gian/dung lượng
  + streaming/ingestion, Cloud Storage, network, Cloud Logging
  + API Java/Cloud Run/GKE và các services downstream
~~~

**Giá cụ thể và free-tier/quota thay đổi theo region, pricing model và thời gian**. Xem Billing SKUs thực tế thay vì tính phí từ số dòng SQL. MV có thể làm giảm bytes scanned cho hàng nghìn truy vấn lặp lại, nhưng nếu refresh thường xuyên trên bảng có DML/update lớn, phí refresh có thể lấn át khoản tiết kiệm.

### Công thức đánh giá sơ bộ

~~~text
Tiết kiệm ròng mỗi tháng (ước tính)
  = phí compute query trước tối ưu
    - phí compute query sau tối ưu
    - phí MV refresh + MV storage
    - phí BI Engine reservation
    - phí vận hành phát sinh
~~~

Hai metrics cần báo cáo cùng nhau:

- **SLO:** ví dụ P95 load dashboard dưới 2 giây, dữ liệu chậm tối đa 4 giờ khi hiển thị `max_staleness`.
- **FinOps:** phí mỗi 1.000 lần mở dashboard, tổng chi phí BigQuery/BI Engine theo project, số refresh lỗi và số byte được quét.

Đừng tăng BI Engine reservation khi dashboard có 500 ms chậm ở front-end/Java serialization; profiling từng lớp mới xác định bottleneck.

### Mẫu quyết định kiến trúc

| Hệ thống | Giải pháp thử trước | Vì sao |
|---|---|---|
| Truy vấn theo một khoảng 7 ngày trong bảng theo năm | Partition filter + clustering | Giảm scan khi không cần thêm dịch vụ |
| Nhiều dashboards cùng dùng `SUM/COUNT` theo ngày/cửa hàng | Materialized view incremental | Tái sử dụng aggregate, có thể smart tuning |
| Dashboard BI tương tác nhiều lần, SQL được hỗ trợ | BI Engine trên tables/MV ưu tiên | Giảm latency thông qua memory/vectorization |
| Batch tài chính phức tạp chỉ chốt một lần/ngày | Scheduled aggregate table | Kiểm soát lịch và snapshot dễ hơn |
| API trả trạng thái thanh toán **ngay sau commit** | Cloud SQL/Spanner cho đường OLTP | Không hứa BigQuery MV là nguồn sự thật real-time |
| Nhiều đối tác/tenant có chính sách row-level phức tạp | Ưu tiên security đúng, benchmark lại MV/BI | RLS/masking có thể giới hạn acceleration |

## 11. Runbook: MV/BI Engine không nhanh hoặc kết quả “cũ”

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra/hành động |
|---|---|---|
| `CREATE MATERIALIZED VIEW` bị từ chối | SQL/aggregate không đủ điều kiện incremental hoặc thiếu permission | Docs supported query patterns, `bigquery.tables.create` |
| MV refresh thất bại | Thay schema, mất base table, DML/partition invalidation | `INFORMATION_SCHEMA.MATERIALIZED_VIEWS.last_refresh_status`, refresh jobs |
| Query base không dùng MV | Cần cột/hàng MV không có, SQL shape khác hoặc optimizer chọn phương án rẻ hơn | `materialized_view_statistics.chosen/rejected_reason`, Query plan |
| Query trực tiếp MV còn đọc nhiều bytes | Chưa refresh, phải hòa delta, freshness policy hoặc toàn bộ refresh invalidated | Refresh watermark, base DML, `max_staleness` |
| Dashboard chưa thấy đơn mới | `max_staleness` cho phép dùng snapshot refresh trước | Kiểm tra last refresh, show data-as-of, cân nhắc direct base query |
| Bật BI Engine nhưng `NO_RESERVATION` | Capacity chưa tạo/khác region/project | `BI_CAPACITIES`, project/location của query |
| `INSUFFICIENT_RESERVATION` hoặc `INPUT_TOO_LARGE` | Memory không đủ với columns/partitions/JOIN | Used/reserved bytes, lọc cột/partition hoặc sizing |
| `TABLE_EXCLUDED` | Preferred table list thiếu base table/MV hoặc một JOIN table | `preferred_tables` và toàn bộ nguồn của query |
| `UNSUPPORTED_SQL_TEXT` | Wildcard table, external table, UDF hoặc đặc tính SQL không hỗ trợ | Rewrite query, giảm phức tạp, chấp nhận fallback |
| Chỉ thấy query nhanh sau lần chạy thứ hai | Query-result cache hoặc BI Engine warmup | Tắt result cache khi benchmark, đo cold/warm riêng |
| `PERMISSION_DENIED` khi Java đọc MV | Runtime SA thiếu jobUser/dataViewer, underlying source access hoặc RLS/column policy | Identity, dataset/view IAM, authorized MV setup |
| `Location mismatch` | Dataset/query jobs/BI reservation ở các locations khác nhau | Cấu hình job location, kiểm tra dataset region |
| BigQuery bill tăng sau tối ưu | MV refresh/storage, BI reservation, thêm scan/JOIN | Billing by SKU, refresh job bytes, reservation size |

Lệnh điều tra chỉ đọc:

~~~bash
PROJECT_ID="my-bigquery-lab"
LOCATION="asia-southeast1"

bq --location="$LOCATION" ls "$PROJECT_ID:analytics_lab"
bq --location="$LOCATION" show \
  "$PROJECT_ID:analytics_lab.mv_paid_daily"

# Thay JOB_ID bằng job thực từ Console hoặc INFORMATION_SCHEMA.
bq --location="$LOCATION" show --format=prettyjson \
  -j "JOB_ID"
~~~

Với query không đạt mục tiêu, ghi lại **SQL text, Job ID, location, cache_hit, plan, bytes, slot-ms, MV/BI statistics và thời điểm refresh** trước khi sửa cấu hình. Một HTTP 500 ở Java có thể do timeout/backend exception không liên quan BI Engine; phải phân biệt lỗi ở lớp nào.

## 12. Tình huống mở rộng: dashboard bán hàng đa khu vực

Một doanh nghiệp có các nguồn giao dịch từ Cloud SQL/Spanner, ứng dụng Java trên Cloud Run và dashboard doanh thu:

~~~mermaid
flowchart TD
  A["Cloud SQL / Spanner: đơn hàng đã commit"] --> I["ELT / CDC / BigQuery ingestion"]
  I --> B["BigQuery orders: partition + cluster"]
  B --> MV["MV: paid revenue by day/store"]
  MV --> BI["BI Engine reservation: preferred tables"]
  BI --> J["Cloud Run Java Dashboard API"]
  J --> U["Biểu đồ/BI client"]
  M["Job metadata + Cloud Monitoring + Billing"] --> MV
  M --> BI
~~~

**Thiết kế hai đường đọc:**

- **Báo cáo doanh thu** chấp nhận độ trễ theo SLO, dùng BigQuery MV/BI Engine, phân tách quyền đọc aggregates.
- **Tra trạng thái một đơn ngay sau thanh toán** dùng OLTP database có transaction semantics. Không lấy việc ingestion vào BigQuery/MV hoàn tất làm điều kiện để xác nhận đơn được thanh toán.

Với multi-region, lưu ý dataset và BI Engine reservation **cùng location**. Nếu nguồn dữ liệu ở các locations khác nhau, cần pipeline đồng bộ dữ liệu và đánh giá data residency/egress; không mặc định một reservation ở vùng A tăng tốc query jobs vùng B. Dashboard đa tenant phải kiểm tra row-level/column-level policies; performance optimization không được thay đổi quyền xem dữ liệu.

### Quy trình triển khai có rollback

1. Data team review schema, partition/cluster keys và query patterns từ query history.
2. Tạo MV dưới tên versioned ở staging; so sánh số liệu với base query.
3. Benchmark latency/bytes/slot-ms và MV usage; bật `max_staleness` **chỉ sau khi business chấp nhận độ mới**.
4. Bật BI Engine cho project/location lab hoặc reservation riêng có owner; kiểm tra acceleration reasons.
5. Java API chuyển sang đọc MV theo feature flag; canary một phần traffic, đo P95 và correctness.
6. Nếu lỗi, **đổi Java query về base table/aggregate table trước**, rồi mới tháo capacity/MV không còn dùng; đừng drop MV khi các clients khác vẫn đang đọc.
7. Theo dõi refresh errors, BI memory pressure, bill và dữ liệu trễ theo thời gian.

## 13. Checklist trước production

- [ ] Có baseline query, latency P50/P95, scan bytes, slot-ms, query-plan và chi phí.
- [ ] Partition filters áp vào đúng partition column; không `SELECT *` khi không cần.
- [ ] MV definition chỉ chứa cột/hàng cần cho các query quan trọng và thuộc SQL pattern được hỗ trợ.
- [ ] Nếu base partitioned, MV có partition alignment phù hợp và kiểm tra expiration/invalidation.
- [ ] Có số liệu `last_refresh_time`, `refresh_watermark`, `last_refresh_status`.
- [ ] Phân biệt incremental refresh, smart tuning và direct MV query; kiểm tra `chosen/rejected_reason`.
- [ ] `max_staleness` phù hợp SLO dữ liệu, được hiển thị trong dashboard và không bị hiểu như cam kết refresh đúng giờ.
- [ ] BI Engine reservation nằm đúng project/location, có ngân sách và preferred tables chính xác.
- [ ] Có thống kê `bi_engine_statistics`, kiểm tra FULL/PARTIAL/DISABLED và fallback reasons.
- [ ] Benchmarks tắt query-result cache và kiểm thử cả cold/warm workloads.
- [ ] Java runtime SA dùng ADC, jobUser/dataViewer tối thiểu; view/underlying IAM và RLS được review.
- [ ] Không hy sinh row/column security để tăng tốc BI; không xuất PII trong debug logs.
- [ ] Có thông số billing, refresh cost, storage cost, BI reserved GiB và rollback.
- [ ] Java API có rate limit, query timeout và không để một request mở vô hạn.

## 14. Bài tập vận dụng

**Bài 1 — Phân biệt cơ chế.** So sánh logical view, materialized view, query-result cache và BI Engine theo nơi lưu dữ liệu, khi nào dùng, cách xử lý data freshness và yếu tố chi phí.

**Bài 2 — Partition pruning.** Bảng `orders` chứa 3 năm đơn hàng; dashboard chỉ hỏi 7 ngày. Viết query có filter `order_date BETWEEN ...` và giải thích vì sao `SELECT *`/query toàn bảng có thể tốn hơn. Đề xuất trường nào để clustering khi thường lọc theo `store_id`.

**Bài 3 — MV lab.** Tạo `mv_paid_daily` với `COUNT(*)` và `SUM(amount)` theo ngày/cửa hàng, đối soát với bảng gốc. Chạy query trên bảng gốc và chỉ ra cách xác minh optimizer có dùng MV bằng `materialized_view_statistics`.

**Bài 4 — Smart tuning.** Vì sao một MV chỉ chứa `status='PAID'` và grouped by `order_date,store_id` không giải quyết query lấy `order_id` cụ thể hoặc tổng mọi trạng thái? Hãy đề xuất một bảng hoặc mô hình khác.

**Bài 5 — Freshness.** BI dashboard chấp nhận dữ liệu trễ tối đa 4 giờ, nhưng realtime order status phải mới tức thời. Chọn đường đọc cho từng chức năng; nêu tác động của `max_staleness` và vì sao smart tuning trên base table không làm dữ liệu query “cũ đi”.

**Bài 6 — BI Engine.** Tạo reservation 1 GiB ở project/location lab và preferred tables gồm `orders` và `mv_paid_daily`. Nếu query dùng một bảng JOIN thứ ba ngoài preferred list, dự đoán khả năng acceleration và nơi xem lý do.

**Bài 7 — Benchmark.** Thiết kế phép thử A/B/C/D giữa base query, query trực tiếp MV, base query có smart tuning và BI Engine; phải kiểm soát cache, rows, location, concurrency và những metrics nào?

**Bài 8 — IAM/RLS.** Cloud Run runtime SA chỉ được cấp `roles/bigquery.jobUser` ở project, nhưng `PERMISSION_DENIED` khi đọc MV. Nêu các quyền/data access cần kiểm tra, vai trò authorized materialized view, và vì sao không được xóa row-level policy chỉ để tăng tốc.

**Bài 9 — Chi phí.** Một dashboard có nhiều query lặp lại nhưng refresh MV thường xuyên trên bảng được UPDATE lớn mỗi giờ. Liệt kê đủ thành phần phí và đề xuất cách so sánh incremental MV, scheduled aggregate table, partitioning và BI Engine.

**Bài 10 — Sự cố thực tế.** Sau deploy, BI Engine báo `TABLE_EXCLUDED`, MV `last_refresh_status` có lỗi và P95 tăng. Xây runbook theo thứ tự từ IAM/location/SQL, refresh job, query-plan, preferred tables đến rollback.

## Tài liệu tham khảo chính thức

- [BigQuery query performance overview](https://cloud.google.com/bigquery/docs/best-practices-performance-overview) — đo I/O, shuffle, computation, slots.
- [Optimize query computation](https://cloud.google.com/bigquery/docs/best-practices-performance-compute) — partition pruning, clustering, MV, BI Engine.
- [Introduction to materialized views](https://cloud.google.com/bigquery/docs/materialized-views-intro) — incremental refresh và precomputation.
- [Create materialized views](https://cloud.google.com/bigquery/docs/materialized-views-create) — SQL, partition alignment, refresh và `max_staleness`.
- [Use materialized views](https://cloud.google.com/bigquery/docs/materialized-views-use) — smart tuning, `chosen` và `rejected_reason`.
- [Monitor materialized views](https://cloud.google.com/bigquery/docs/materialized-views-monitor) — refresh jobs, `INFORMATION_SCHEMA.MATERIALIZED_VIEWS`.
- [Troubleshoot materialized views](https://cloud.google.com/bigquery/docs/materialized-views-troubleshoot) — lỗi invalidation và rewrite.
- [BI Engine introduction](https://cloud.google.com/bigquery/docs/bi-engine-intro) — memory/vectorization và hỗ trợ SQL.
- [Reserve BI Engine capacity](https://cloud.google.com/bigquery/docs/bi-engine-reserve-capacity) — reservation, preferred tables và `BI_CAPACITIES`.
- [Monitor BI Engine](https://cloud.google.com/bigquery/docs/bi-engine-monitor) — `bi_engine_statistics`, job metadata, Cloud Monitoring.
- [JOBS_BY_PROJECT information schema](https://cloud.google.com/bigquery/docs/information-schema-jobs) — job cost, cache và query insights.
- [BigQuery Java client library](https://cloud.google.com/java/docs/reference/google-cloud-bigquery/latest/overview) — query jobs, parameters và ADC.
- [BigQuery IAM](https://cloud.google.com/bigquery/docs/access-control) — jobUser, dataset/view access và least privilege.
- [Using row-level security with other features](https://cloud.google.com/bigquery/docs/using-row-level-security-with-features) — tác động đến MV/BI Engine.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) — compute, storage và BI Engine capacity.
