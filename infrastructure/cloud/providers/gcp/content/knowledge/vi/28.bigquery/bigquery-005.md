# GoogleSQL, nested fields và repeated fields trong BigQuery

Một hệ thống bán lẻ tạo đơn hàng trên **Cloud Run**, xử lý sự kiện qua **Pub/Sub** và lưu dữ liệu giao dịch tại **Cloud SQL/Spanner**. Đội phân tích muốn đưa dữ liệu đơn hàng vào **BigQuery** để tính doanh thu theo sản phẩm và khu vực. Mỗi đơn có một khách hàng, nhưng có thể chứa **nhiều dòng hàng**. Nếu tách mọi thứ thành các bảng để `JOIN` lại trong mỗi báo cáo, truy vấn có thể tốn công ghép dữ liệu; nếu làm phẳng hoàn toàn thì trường đơn hàng bị lặp nhiều lần.

**GoogleSQL** cho phép biểu diễn quan hệ cha–con ngay trong một dòng BigQuery bằng **`STRUCT`** (nested fields) và **`ARRAY`** (repeated fields). Người học cần biết cả cách **định nghĩa schema, truy cập, bung mảng, lọc, tổng hợp** và các trường hợp gây sai số như nhân đôi dòng sau `UNNEST`.

Bài thuộc chương **BigQuery**, mô-đun **CLOUD_PROVIDERS_GCP**. Nội dung liên kết lưu trữ, IAM, Google Cloud networking, Cloud Run/GKE và pipelines với quản trị dữ liệu, chi phí và độ tin cậy; trọng tâm vẫn là **GoogleSQL, nested fields và repeated fields**. Các ví dụ dùng dữ liệu giả định, không chứa thông tin khách hàng thật.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `STRUCT`/`RECORD`, `ARRAY`/`REPEATED` và các mode `NULLABLE`, `REQUIRED`, `REPEATED`.
2. Viết GoogleSQL truy cập field qua dấu chấm, đọc phần tử mảng an toàn và dùng `UNNEST`.
3. Hiểu khi nào `CROSS JOIN UNNEST` **loại mất dòng cha**, còn `LEFT JOIN UNNEST` giữ dòng cha không có phần tử.
4. Tính `COUNT`, `SUM` và tỷ lệ đúng sau khi bung mảng, tránh nhân dòng khi có nhiều repeated fields.
5. Dùng `EXISTS`, `ARRAY(...)`, `ARRAY_AGG`, `SELECT AS STRUCT` để lọc và tái tạo dữ liệu lồng nhau.
6. Chọn schema denormalized phù hợp, nạp JSON từ Cloud Storage, kiểm thử schema evolution và tối ưu chi phí BigQuery.
7. Xử lý các trường hợp `NULL`, mảng rỗng, mảng nhiều cấp và bảo vệ dữ liệu/chi phí production.

## 2. Kiểu dữ liệu và mode của BigQuery

### 2.1. Ba hình thức biểu diễn

| Dữ liệu | GoogleSQL type | BigQuery table schema | Ví dụ |
| --- | --- | --- | --- |
| Giá trị đơn | `STRING`, `INT64`, `NUMERIC`, `DATE`... | Cột scalar với mode `NULLABLE` hoặc `REQUIRED`. | `order_id STRING` |
| Một đối tượng con | `STRUCT<customer_id STRING, city STRING>` | `RECORD` có các fields con. | `customer.city` |
| Nhiều giá trị | `ARRAY<STRING>` | Cột `REPEATED`. | `tags = ['vip','mobile']` |
| Nhiều đối tượng con | `ARRAY<STRUCT<sku STRING, qty INT64>>` | `RECORD` với mode `REPEATED`. | `items` của một đơn |
| Mảng bên trong đối tượng | `STRUCT<labels ARRAY<STRING>>` | Một `RECORD` có field con `REPEATED`. | `customer.tags` |

**`RECORD` là cách schema/API mô tả**, còn **`STRUCT` là kiểu trong GoogleSQL**; tương tự **`REPEATED` trong schema được đọc như `ARRAY` trong truy vấn**. Trường `NULLABLE` cho phép giá trị `NULL`, còn `REQUIRED` không; `REPEATED` mô tả 0 hoặc nhiều phần tử. Không kết luận một `RECORD` tự là mảng nếu mode của nó không phải `REPEATED`.

Sơ đồ một dòng đơn hàng:

~~~mermaid
flowchart TD
    O["Order: order_id, order_date"] --> C["customer STRUCT"]
    C --> CID["customer_id"]
    C --> CITY["city"]
    O --> I["items ARRAY of STRUCT"]
    I --> SKU["sku"]
    I --> Q["qty"]
    I --> PRICE["unit_price"]
    O --> TAG["tags ARRAY of STRING"]
~~~

Giới hạn thiết kế: BigQuery cho phép **tối đa 15 cấp `RECORD` lồng nhau**; **không hỗ trợ `ARRAY` chứa trực tiếp một `ARRAY` khác**. Khi cần mảng của mảng, lồng thêm `STRUCT`, ví dụ `ARRAY<STRUCT<values ARRAY<INT64>>>`. Không nhất thiết phải dùng đến độ sâu tối đa: schema sâu làm consumer và migration khó hơn.

### 2.2. `STRUCT` có tên field và `ARRAY` có phần tử

~~~sql
-- Chạy trực tiếp trong BigQuery SQL editor, không cần tạo dataset.
SELECT
  STRUCT('C-01' AS customer_id, 'HCM' AS city) AS customer,
  ['web', 'mobile'] AS channels,
  [
    STRUCT('SKU-A' AS sku, 2 AS qty, NUMERIC '120000' AS unit_price),
    STRUCT('SKU-B' AS sku, 1 AS qty, NUMERIC '50000' AS unit_price)
  ] AS items;
~~~

Ở đây `customer` có **một** giá trị `STRUCT`; `channels` là `ARRAY<STRING>`; `items` là `ARRAY<STRUCT<...>>`. SQL hỗ trợ `STRUCT(...)` với named fields, không phải JSON string. `NUMERIC` phù hợp với nhiều phép tính tiền hơn `FLOAT64` vì tránh sai số nhị phân không cần thiết; cần xác định đơn vị tiền và quy tắc làm tròn với nghiệp vụ thực.

## 3. Bộ dữ liệu thực hành tự chứa

Dùng **BigQuery multi-statement SQL script** dưới đây để tạo bảng tạm trong cùng job/script. Các phần truy vấn tiếp theo giả định đã chạy khối này trong **cùng script/session**. Nếu chạy từng câu ở các job độc lập, phải tạo lại bảng tạm hoặc thay bằng bảng thực đã được phê duyệt.

~~~sql
-- WRITE trong phạm vi job: bảng TEMP không tạo bảng production.
CREATE TEMP TABLE demo_orders AS
SELECT
  'O-1001' AS order_id,
  DATE '2026-11-18' AS order_date,
  STRUCT('C-01' AS customer_id, 'HCM' AS city) AS customer,
  [
    STRUCT('SKU-A' AS sku, 2 AS qty, NUMERIC '120000' AS unit_price),
    STRUCT('SKU-B' AS sku, 1 AS qty, NUMERIC '50000' AS unit_price)
  ] AS items,
  ['web', 'vip'] AS tags
UNION ALL
SELECT
  'O-1002',
  DATE '2026-11-19',
  STRUCT('C-02' AS customer_id, 'Da Nang' AS city),
  [STRUCT('SKU-A' AS sku, 1 AS qty, NUMERIC '120000' AS unit_price)],
  ['mobile']
UNION ALL
SELECT
  'O-1003',
  DATE '2026-11-19',
  STRUCT('C-03' AS customer_id, 'HCM' AS city),
  ARRAY<STRUCT<sku STRING, qty INT64, unit_price NUMERIC>>[],
  ARRAY<STRING>[];

-- READ: có 3 đơn, tổng 3 dòng hàng, đơn O-1003 có items rỗng.
SELECT order_id, customer.city AS city,
       ARRAY_LENGTH(items) AS item_count
FROM demo_orders
ORDER BY order_id;
~~~

Kết quả mong đợi:

| order_id | city | item_count |
| --- | --- | ---: |
| O-1001 | HCM | 2 |
| O-1002 | Da Nang | 1 |
| O-1003 | HCM | 0 |

Toàn bộ số liệu và giá trị là **giả định**. Ví dụ dùng một đơn có mảng `items` rỗng để người học nhận ra lỗi thường gặp khi flatten. Đối với bảng thật, `order_id` cần duy nhất theo quy tắc dữ liệu và nên có quy trình kiểm soát trùng từ upstream; BigQuery không tự biến ví dụ thành ràng buộc khóa chính được thực thi.

## 4. Truy cập nested fields và phần tử repeated

### 4.1. Dot notation

Khi field **không repeated**, truy cập bằng dấu chấm:

~~~sql
SELECT
  order_id,
  customer.customer_id AS customer_id,
  customer.city AS city,
  ARRAY_LENGTH(tags) AS tag_count
FROM demo_orders
ORDER BY order_id;
~~~

**Không viết `items.sku` để lấy tất cả SKU của một repeated record như một scalar field.** Vì `items` là mảng, hãy dùng `UNNEST(items)` hoặc một array subquery.

### 4.2. Index bắt đầu từ 0 và truy cập an toàn

~~~sql
SELECT
  order_id,
  items[SAFE_OFFSET(0)].sku AS first_sku,
  tags[SAFE_ORDINAL(1)] AS first_tag,
  ARRAY_LENGTH(items) AS item_count
FROM demo_orders
ORDER BY order_id;
~~~

- `OFFSET(0)` lấy phần tử đầu theo chỉ số **0-based**; `ORDINAL(1)` theo **1-based**.
- `SAFE_OFFSET` và `SAFE_ORDINAL` trả `NULL` nếu **index vượt phạm vi**; `OFFSET`/`ORDINAL` thông thường có thể gây lỗi.
- `ARRAY_LENGTH([]) = 0`, còn `ARRAY_LENGTH(NULL)` cho kết quả `NULL`.
- Thứ tự array có thể mang ý nghĩa nghiệp vụ, nhưng **`UNNEST` không bảo đảm giữ thứ tự đó** nếu không mang theo offset và `ORDER BY`.

Đừng dùng `items[OFFSET(0)]` trên mọi dòng khi có đơn chưa có item.

## 5. `UNNEST`: từ một đơn thành nhiều dòng hàng

### 5.1. `CROSS JOIN` hoặc `INNER JOIN UNNEST`

~~~sql
SELECT
  o.order_id,
  i.sku,
  i.qty,
  i.unit_price
FROM demo_orders AS o
CROSS JOIN UNNEST(o.items) AS i
ORDER BY o.order_id, i.sku;
~~~

Kết quả:

| order_id | sku | qty | unit_price |
| --- | --- | ---: | ---: |
| O-1001 | SKU-A | 2 | 120000 |
| O-1001 | SKU-B | 1 | 50000 |
| O-1002 | SKU-A | 1 | 120000 |

`UNNEST` biến từng item thành một dòng **và lặp lại các field của đơn cha trên từng dòng con**. Với `CROSS JOIN`/`INNER JOIN` tương quan, `items=[]` hoặc `items IS NULL` sinh **0 dòng con**, nên **O-1003 biến mất**. Đây là hành vi join, không phải dữ liệu O-1003 đã bị xóa.

### 5.2. `LEFT JOIN UNNEST`: giữ đơn không có item

~~~sql
SELECT
  o.order_id,
  i.sku,
  i.qty
FROM demo_orders AS o
LEFT JOIN UNNEST(o.items) AS i ON TRUE
ORDER BY o.order_id, i.sku;
~~~

Kết quả có thêm **O-1003 với `sku=NULL`, `qty=NULL`**. Với một mảng trống hoặc `NULL`, outer join vẫn giữ dòng cha bằng một dòng có các cột phải là `NULL`. Hành vi này rất quan trọng khi thống kê **toàn bộ đơn hàng**, không chỉ đơn có ít nhất một item.

### 5.3. Vì sao `COUNT(*)` dễ sai?

Để đếm chính xác sau `LEFT JOIN`, **không** `GROUP BY` trực tiếp một field `ARRAY` (GoogleSQL không cho nhóm theo kiểu `ARRAY`). Dùng `MAX(ARRAY_LENGTH(...))` theo khóa đơn hàng duy nhất:

~~~sql
SELECT
  o.order_id,
  COUNT(*) AS rows_after_left_join,
  COUNT(i.sku) AS sku_count,
  MAX(ARRAY_LENGTH(o.items)) AS items_in_order
FROM demo_orders AS o
LEFT JOIN UNNEST(o.items) AS i ON TRUE
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

| order_id | rows_after_left_join | sku_count | items_in_order |
| --- | ---: | ---: | ---: |
| O-1001 | 2 | 2 | 2 |
| O-1002 | 1 | 1 | 1 |
| O-1003 | **1** | **0** | **0** |

`COUNT(*)` đếm cả dòng `NULL` do `LEFT JOIN` tạo ra. `COUNT(i.sku)` đúng ở ví dụ này **vì `sku` của mọi item hợp lệ là non-NULL**; với dữ liệu thực mà `sku` có thể `NULL`, nên đếm theo định nghĩa item hợp lệ hoặc dùng `ARRAY_LENGTH` để lấy số phần tử mảng. Đối với tổng số **đơn**, tính trước khi `UNNEST` hoặc `COUNT(DISTINCT order_id)` nếu ID được đảm bảo duy nhất và truy vấn có join.

### 5.4. Giữ thứ tự phần tử với `WITH OFFSET`

~~~sql
SELECT
  o.order_id, pos,
  i.sku
FROM demo_orders AS o
CROSS JOIN UNNEST(o.items) AS i WITH OFFSET AS pos
ORDER BY o.order_id, pos;
~~~

`pos` chạy từ 0. Khi cần khôi phục array theo đúng thứ tự gốc, mang offset qua bước xử lý và sắp xếp rõ ràng; **không dựa vào thứ tự kết quả ngầm định của SQL**.

## 6. Lọc mảng mà không nhân số dòng

### 6.1. `EXISTS` với `UNNEST`

Câu hỏi: **Đơn hàng nào có ít nhất một SKU-B?** Không nhất thiết phải `CROSS JOIN` rồi `DISTINCT`:

~~~sql
SELECT o.order_id
FROM demo_orders AS o
WHERE EXISTS (
  SELECT 1
  FROM UNNEST(o.items) AS i
  WHERE i.sku = 'SKU-B'
);
~~~

Kết quả chỉ có **O-1001**. `EXISTS` kiểm tra điều kiện có phần tử phù hợp; khi mảng rỗng, subquery không trả dòng nên điều kiện sai. Cách này tránh nhân dòng cha khi mục đích chỉ là **kiểm tra sự tồn tại**.

Với `ARRAY` scalar:

~~~sql
-- Đơn có tag 'vip'.
SELECT order_id
FROM demo_orders
WHERE 'vip' IN UNNEST(tags);
~~~

`IN UNNEST(tags)` phù hợp cho membership test. Hãy cẩn thận với **NULL elements** và phép `NOT IN`: logic ba giá trị của SQL có thể trả `NULL` thay vì `TRUE`/`FALSE` như mong đợi. Nếu cần lọc giá trị không có trong mảng, cân nhắc `NOT EXISTS` với điều kiện rõ.

### 6.2. Tính tổng tiền theo từng đơn

Một correlated scalar subquery giữ **mỗi đơn đúng một dòng**:

~~~sql
SELECT
  o.order_id,
  COALESCE((
    SELECT SUM(i.qty * i.unit_price)
    FROM UNNEST(o.items) AS i
  ), NUMERIC '0') AS total_vnd
FROM demo_orders AS o
ORDER BY o.order_id;
~~~

| order_id | total_vnd |
| --- | ---: |
| O-1001 | 290000 |
| O-1002 | 120000 |
| O-1003 | 0 |

`SUM` trên tập rỗng trả `NULL`, nên `COALESCE` biến trường hợp không có item thành `0` theo quy tắc ví dụ. Với dữ liệu thực, số tiền có thể cần thêm discount, tax, refund và kiểm tra currency; **không coi phép cộng này là tổng tiền thanh toán chính thức**.

### 6.3. Tổng hợp theo SKU

Ngược lại, khi **mục tiêu là thống kê theo dòng hàng**, bung `items` là hợp lý:

~~~sql
SELECT
  i.sku,
  SUM(i.qty) AS units_sold,
  SUM(i.qty * i.unit_price) AS gross_vnd
FROM demo_orders AS o
CROSS JOIN UNNEST(o.items) AS i
GROUP BY i.sku
ORDER BY i.sku;
~~~

Kết quả:

| sku | units_sold | gross_vnd |
| --- | ---: | ---: |
| SKU-A | 3 | 360000 |
| SKU-B | 1 | 50000 |

**Phân biệt độ hạt (grain):** bảng gốc là **một dòng/đơn**, sau `UNNEST(items)` là **một dòng/item**. Các `SUM` và `COUNT` phải được tính theo grain của câu hỏi.

## 7. Tái tạo mảng và cấu trúc sau khi biến đổi

### 7.1. `ARRAY(SELECT AS STRUCT ...)`

Muốn giữ nguyên số dòng đơn hàng nhưng chỉ lấy items có `qty >= 2`:

~~~sql
SELECT
  o.order_id,
  ARRAY(
    SELECT AS STRUCT i.sku, i.qty, i.unit_price
    FROM UNNEST(o.items) AS i
    WHERE i.qty >= 2
    ORDER BY i.sku
  ) AS large_quantity_items
FROM demo_orders AS o
ORDER BY o.order_id;
~~~

`ARRAY(subquery)` trả mảng rỗng nếu subquery không có dòng, **không trả `NULL` array**. `SELECT AS STRUCT` giữ cả ba field trong mỗi phần tử. `ORDER BY` bên trong subquery xác định thứ tự array được xây dựng; nếu không có, không được giả định thứ tự sẽ như cũ.

### 7.2. `ARRAY_AGG` và vấn đề NULL

Nếu đã bung mảng để nhóm:

~~~sql
SELECT
  o.order_id,
  COALESCE(
    ARRAY_AGG(i.sku IGNORE NULLS ORDER BY i.sku),
    ARRAY<STRING>[]
  ) AS sku_list
FROM demo_orders AS o
LEFT JOIN UNNEST(o.items) AS i ON TRUE
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

Với O-1003, `LEFT JOIN` tạo một dòng có `sku=NULL`; **`IGNORE NULLS`** tránh lưu phần tử `NULL` vào array kết quả. BigQuery có thể báo lỗi nếu array trong **kết quả cuối** chứa phần tử `NULL`; `ARRAY_AGG` trên không có phần tử được chọn có thể trả `NULL`, nên `COALESCE` đổi thành `[]`.

`ARRAY_AGG` có `DISTINCT`, `ORDER BY`, `LIMIT` khi phù hợp; cần kiểm tra logic nếu quan hệ ban đầu đã bị nhân lên do nhiều joins. **Không dùng `ARRAY_AGG(DISTINCT ...)` để che lỗi nhân dòng** nếu dữ liệu thật cho phép hai item trùng SKU nhưng khác giá/số lượng.

### 7.3. Mảng lồng mảng qua `STRUCT`

GoogleSQL **không hỗ trợ trực tiếp**:

~~~sql
-- CÚ PHÁP KHÔNG HỖ TRỢ: ARRAY<ARRAY<INT64>>
-- Chỉ minh họa điều cần tránh, không thực thi.
~~~

Muốn nhiều nhóm giá trị, bọc mảng trong một `STRUCT`:

~~~sql
SELECT [
  STRUCT('morning' AS period, [3, 5] AS counts),
  STRUCT('evening' AS period, [6, 8] AS counts)
] AS series;
~~~

Kiểu kết quả là `ARRAY<STRUCT<period STRING, counts ARRAY<INT64>>>`. Cách này cũng hữu ích khi một item có nhiều khuyến mãi hoặc một vận động viên có nhiều vòng thi.

## 8. Tránh nhân dòng do nhiều repeated fields

Nếu một đơn có **2 items** và **2 tags**, việc `UNNEST` cả hai trong cùng `FROM` tạo **4 tổ hợp** cho đơn đó:

~~~sql
-- Demo sự nhân dòng: O-1001 tạo 2 × 2 = 4 dòng.
SELECT o.order_id, i.sku, tag
FROM demo_orders AS o
CROSS JOIN UNNEST(o.items) AS i
CROSS JOIN UNNEST(o.tags) AS tag
WHERE o.order_id = 'O-1001';
~~~

Đây là **tích Descartes giữa hai mảng của cùng một dòng cha**. Nếu tính doanh thu ngay trên kết quả này, mỗi item của O-1001 sẽ bị đếm **hai lần**.

**Cách an toàn:** tính từng đại lượng ở cấp **một đơn** rồi ghép kết quả, hoặc dùng subquery tương quan:

~~~sql
SELECT
  o.order_id,
  (SELECT COUNT(*) FROM UNNEST(o.items)) AS item_count,
  (SELECT COUNT(*) FROM UNNEST(o.tags)) AS tag_count,
  COALESCE((
    SELECT SUM(i.qty * i.unit_price)
    FROM UNNEST(o.items) AS i
  ), NUMERIC '0') AS total_vnd
FROM demo_orders AS o
ORDER BY o.order_id;
~~~

Nếu cần nối hai mảng **theo vị trí** (ví dụ `codes[j]` khớp `scores[j]`) chứ không phải tích Descartes, hãy mang `WITH OFFSET`, nối theo chỉ số và xử lý mảng có độ dài khác nhau. Đừng giả định hai arrays độc lập có cùng số phần tử.

## 9. Tạo schema BigQuery thực tế

### 9.1. Bảng partitioned cho đơn hàng

Ví dụ DDL **chỉ chạy trong project lab** khi dataset `analytics` đã tồn tại. `CREATE TABLE` là thao tác ghi tài nguyên, có thể phát sinh phí lưu trữ/truy vấn.

~~~sql
-- WRITE: thay project/dataset theo môi trường được phép.
CREATE TABLE IF NOT EXISTS `retail-lab.analytics.orders_nested` (
  order_id STRING NOT NULL,
  order_date DATE,
  customer STRUCT<customer_id STRING, city STRING>,
  items ARRAY<STRUCT<sku STRING, qty INT64, unit_price NUMERIC>>,
  tags ARRAY<STRING>
)
PARTITION BY order_date
CLUSTER BY order_id
OPTIONS(description='Orders with repeated line items');
~~~

| Thiết kế | Lý do và lưu ý |
| --- | --- |
| `PARTITION BY order_date` | Lọc theo khoảng ngày giúp **partition pruning** nếu câu SQL có predicate phù hợp. |
| `CLUSTER BY order_id` | Có thể giúp lọc theo đơn hàng cụ thể trên bảng lớn, tùy phân bố dữ liệu và truy vấn. |
| `items ARRAY<STRUCT<...>>` | Giữ parent–child cùng nhau, tránh join riêng cho line items thường xuyên truy xuất chung. |
| `unit_price NUMERIC` | Hỗ trợ phép tính decimal; phải xác định cách quy đổi tiền tệ. |
| `order_id STRING NOT NULL` | Là khai báo nullability, **không tự bảo đảm uniqueness**. |

Chọn partition/clustering dựa trên **truy vấn thật**, không sao chép thiết lập này cho mọi bảng. Nếu phần lớn workload nhóm theo SKU trên hàng tỷ items, cần benchmark truy vấn/repeated cardinality; có thể dùng bảng item-grain hoặc materialized/precomputed summaries riêng.

### 9.2. Một bản ghi ndJSON có nested/repeated fields

Một object trên **một dòng** trong file `orders.jsonl`:

~~~json
{"order_id":"O-1001","order_date":"2026-11-18","customer":{"customer_id":"C-01","city":"HCM"},"items":[{"sku":"SKU-A","qty":2,"unit_price":120000},{"sku":"SKU-B","qty":1,"unit_price":50000}],"tags":["web","vip"]}
~~~

`customer` là JSON object khớp `STRUCT`; `items` là JSON array chứa objects khớp `ARRAY<STRUCT>`; `tags` là array strings. **Không** ghi toàn bộ nhiều dòng JSON array `[{...},{...}]` thay cho newline-delimited JSON: mỗi dòng phải là **một record**.

Trong môi trường thật, ưu tiên **schema rõ ràng** cho hợp đồng dữ liệu; autodetect có thể nhầm kiểu (ví dụ ID toàn số, mảng rỗng hoặc field thường vắng mặt). BigQuery có hỗ trợ load nested fields từ ndJSON/Parquet/Avro/ORC theo schema phù hợp.

### 9.3. Nạp từ Cloud Storage qua `bq`

~~~bash
# WRITE: có dataset và table đã tạo, object GCS tồn tại.
# Location BigQuery job phải phù hợp dataset và bucket theo quy định.
bq --location=asia-southeast1 load \
  --noreplace \
  --source_format=NEWLINE_DELIMITED_JSON \
  retail-lab:analytics.orders_nested \
  gs://REPLACE_WITH_BUCKET/landing/orders-*.jsonl

# READ-ONLY: xem schema, không đọc giá trị khách hàng.
bq show --schema --format=prettyjson \
  retail-lab:analytics.orders_nested
~~~

Nếu table đã có schema, load job dùng schema của đích và cần dữ liệu JSON tương thích. Với table mới và muốn autodetect, dùng `--autodetect` có kiểm chứng; trong production, quản lý schema version rõ ràng và cách xử lý records sai thay vì tự động đổi kiểu dữ liệu mỗi đợt nạp.

### 9.4. `STRUCT` khác kiểu `JSON`

| `STRUCT` / `ARRAY<STRUCT>` | `JSON` |
| --- | --- |
| Schema xác định field và kiểu ngay khi thiết kế bảng. | Cấu trúc có thể linh hoạt giữa các records. |
| SQL field access bằng `customer.city`, `i.sku` và type checking. | Thường dùng `JSON_VALUE`, `JSON_QUERY`, v.v., kèm chuyển kiểu khi cần. |
| Phù hợp nguồn giao dịch/event có hợp đồng ổn định, phân tích lặp lại. | Phù hợp dữ liệu bán cấu trúc thay đổi hoặc nhiều định dạng. |
| Cần schema evolution có kiểm soát. | Ít ràng buộc hơn nhưng phải tự kiểm soát chất lượng/casting. |

Không biến mọi đối tượng lồng nhau thành `JSON` chỉ để tránh định nghĩa schema. Cũng không cố ép một payload rất khác nhau giữa từng event vào hàng chục nested fields rỗng nếu `JSON` là lựa chọn hợp lý hơn.

## 10. Tối ưu truy vấn và kiểm soát chi phí

### 10.1. Nested không luôn tốt hơn `JOIN`

BigQuery lưu dữ liệu theo cột; schema nested/repeated thường có lợi khi **parent–child được truy vấn cùng nhau**, nhờ giảm các bước `JOIN` và dữ liệu phải trao đổi giữa các slots. Tuy nhiên:

- Quan hệ **nhiều-nhiều**, dimension lớn dùng lại ở nhiều fact tables hoặc cấu trúc **star schema** đã tối ưu có thể vẫn phù hợp hơn dạng nested.
- Array cực dài trong một row có thể gây **skew** và làm xử lý khó song song; benchmark với độ dài array thực tế.
- Nếu mỗi lần phân tích đều phải bung hàng triệu elements và nhóm theo SKU, xem xét bảng **item-grain** hoặc bảng tổng hợp riêng cho workload đó.
- Không chọn nested chỉ vì muốn “ít bảng”; hãy chọn theo **truy vấn, tần suất cập nhật, schema evolution và khả năng kiểm thử**.

### 10.2. Giảm byte scan và công việc thừa

~~~sql
-- READ-ONLY: ví dụ query trên bảng thật đã partition theo order_date.
SELECT
  o.order_date,
  i.sku,
  SUM(i.qty) AS units_sold
FROM `retail-lab.analytics.orders_nested` AS o
CROSS JOIN UNNEST(o.items) AS i
WHERE o.order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-19'
GROUP BY o.order_date, i.sku
ORDER BY o.order_date, i.sku;
~~~

Nguyên tắc:

1. **Lọc cột partition** để BigQuery có thể bỏ các partitions không cần đọc.
2. Chỉ chọn **fields thật sự dùng**, không mặc định `SELECT *` trên bảng lớn nhiều nested fields.
3. Đừng bung array nếu chỉ muốn `ARRAY_LENGTH` hoặc membership test.
4. Tránh `CROSS JOIN UNNEST` nhiều arrays độc lập khi chưa kiểm soát **cardinality**.
5. Kiểm tra **query plan, shuffle, slot time** và bytes billed; `LIMIT 10` **không bảo đảm** giảm bytes scanned trên bảng non-clustered.

### 10.3. Dry run trước truy vấn lớn

~~~bash
# READ-ONLY: dự toán bytes xử lý; thay tên project/dataset.
# Chạy trên Bash; không dùng các tên mẫu nếu tài nguyên không tồn tại.
bq --location=asia-southeast1 query \
  --use_legacy_sql=false \
  --dry_run \
  --format=prettyjson \
  'SELECT order_id, customer.city
   FROM `retail-lab.analytics.orders_nested`
   WHERE order_date = DATE "2026-11-19"'
~~~

Dry run kiểm tra khả năng biên dịch và **ước lượng bytes xử lý**, không bảo đảm chi phí thực tế bằng đúng con số đó. On-demand pricing dựa trên bytes billed theo quy tắc hiện hành; với capacity/slot editions, chi phí có cách tính khác. Kiểm tra **project, dataset location, permissions và budget/quota** trước khi chạy batch queries.

## 11. Các trường hợp `NULL` và thay đổi schema

### 11.1. `NULL` array, mảng rỗng và phần tử `NULL`

~~~sql
SELECT
  ARRAY_LENGTH(ARRAY<STRING>[]) AS empty_length,
  ARRAY_LENGTH(CAST(NULL AS ARRAY<STRING>)) AS null_length;

-- Truy vấn ra ba dòng, trong đó có một dòng element NULL:
SELECT element
FROM UNNEST([1, NULL, 2]) AS element;
~~~

- **`[]` khác `NULL` trong biểu thức SQL**: `ARRAY_LENGTH([])` bằng 0, `ARRAY_LENGTH(NULL)` là `NULL`.
- `UNNEST([])` và `UNNEST(NULL)` đều cho **0 dòng**; `UNNEST([1,NULL,2])` cho **3 dòng**, có một dòng giá trị `NULL`.
- Khi nạp dữ liệu vào repeated field từ ndJSON, cần tuân theo quy tắc của định dạng nguồn: **JSON array không được chứa phần tử `null`** theo BigQuery load contract cho repeated field; field thiếu/null và mảng rỗng có thể được xử lý khác nhau ở giao diện nguồn.
- `ARRAY_AGG` đưa phần tử `NULL` vào **array ở kết quả cuối** có thể gây lỗi; dùng `IGNORE NULLS` hoặc lọc khi phù hợp.

Tránh suy diễn rằng tất cả `NULL` arrays đều lưu xuống bảng như một trạng thái khác hẳn mảng rỗng: **các bước materialize/ghi bảng có thể chuẩn hóa `NULL` array thành `[]`**. Nếu cần phân biệt “khách chưa khai báo danh sách” với “danh sách thực sự rỗng”, hãy lưu thêm một **status flag** có ý nghĩa nghiệp vụ, không chỉ trông cậy vào cách mảng được materialize.

### 11.2. Schema evolution

Khi upstream thêm trường, ví dụ `items.discount_code`, đừng để load job tự thay đổi schema không kiểm soát trong production. Quy trình:

1. **Review contract:** trường mới optional hay required, có ý nghĩa gì cho dữ liệu lịch sử?
2. **Tạo schema mới tương thích:** thêm nested field với mode hợp lệ và dùng phương thức schema update được BigQuery hỗ trợ.
3. **Test dữ liệu cũ:** record thiếu field mới vẫn đọc được với giá trị tương ứng (`NULL` ở field nullable).
4. **Triển khai producer trước/sau theo chiến lược tương thích:** tránh phá các pipeline SQL, Dataflow hoặc BI consumers.
5. **Backfill hoặc tạo view tương thích** nếu báo cáo cần giá trị mặc định; đo chi phí và correctness.
6. **Chỉ xóa/đổi tên field cũ** sau khi xác nhận không còn người dùng/phụ thuộc và có rollback plan.

BigQuery hỗ trợ một số thay đổi schema trực tiếp, nhưng **không phải mọi thay đổi type/mode/nested structure đều tương thích**. Nếu phải tạo lại bảng, kiểm tra partitioning, clustering, access policies, downstream views và chi phí copy. Không dùng `CREATE OR REPLACE TABLE` như thao tác rollback vô hại.

## 12. Bảo mật, pipeline và chất lượng dữ liệu

### 12.1. IAM tách vai trò theo công việc

| Principal | Công việc | Quyền tối thiểu nên xem xét |
| --- | --- | --- |
| Cloud Run/GKE producer | Ghi sự kiện vào Pub/Sub/GCS. | Chỉ quyền publish/write vào đích cần thiết. |
| Load-job service account | Đọc objects GCS, tạo job và ghi table BigQuery. | Storage Object Viewer trên bucket/prefix phù hợp; BigQuery Job User và quyền ghi dữ liệu tại dataset/table cần nạp. |
| Analyst | Truy vấn bảng/vùng dữ liệu được phép. | BigQuery Job User và Data Viewer/authorized view theo tài nguyên. |
| Pipeline/CI | Deploy schema và SQL artifacts. | Dataset/table management có phạm vi, audit; không mặc định Project Owner. |
| Auditor | Xem cấu hình, metrics, audit. | Metadata/logging permissions tương ứng, không cần đọc PII mặc định. |

Một `STRUCT` chứa `customer_id`, vị trí hoặc các field liên hệ **vẫn là dữ liệu nhạy cảm** nếu có thể xác định cá nhân. Nested fields không che dữ liệu khỏi người có quyền đọc table; cần **column-level access controls/data policies, authorized views, row access policies hoặc masking** phù hợp sản phẩm và bảng. Không đưa token, mật khẩu, access keys vào payload/JSONL hoặc query logs.

### 12.2. Bài test dữ liệu tối thiểu

Chạy sau khi đã có `demo_orders` trong cùng script:

~~~sql
-- READ-ONLY: đối chiếu số đơn, số dòng hàng và tổng giá trị giả định.
SELECT
  (SELECT COUNT(*) FROM demo_orders) AS orders,
  (SELECT COUNT(*) FROM demo_orders o
   CROSS JOIN UNNEST(o.items) AS i) AS line_items,
  (SELECT SUM(i.qty * i.unit_price)
   FROM demo_orders o CROSS JOIN UNNEST(o.items) AS i) AS gross_vnd;
~~~

Kết quả kỳ vọng: **3 đơn, 3 dòng hàng, 410000 VND**. Nếu một lần sửa SQL làm `gross_vnd` thành 700000 VND, hãy nghi ngờ **nhân dòng sau `UNNEST`** trước khi kết luận doanh thu tăng.

Với dữ liệu thật, thêm test **schema required/nullable, duplicate order IDs, quantity > 0, giá không âm, currency, vị trí lồng nhau, mảng cực dài, missing fields và cập nhật chậm**. So sánh kết quả BigQuery với dữ liệu nguồn Cloud SQL/Spanner ở một mốc đối soát xác định.

## 13. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `Cannot access field sku on a value with type ARRAY...` | Đang dùng `items.sku` như scalar. | Dùng `UNNEST(items) AS i`, sau đó `i.sku`. |
| Mất những đơn không có item | Dùng `CROSS`/`INNER JOIN UNNEST`. | `LEFT JOIN UNNEST ON TRUE` hoặc tính trực tiếp trên dòng cha. |
| `COUNT(*)` nhiều hơn item thực tế | `LEFT JOIN` giữ một dòng NULL cho mảng rỗng. | `COUNT(i.sku)` khi field non-NULL hoặc `ARRAY_LENGTH`. |
| Doanh thu bị nhân 2–3 lần | Bung cả `items` và `tags` thành tích Descartes. | Tính từng array qua correlated subquery hoặc group theo grain đúng. |
| SQL báo `Array index out of bounds` | Dùng `OFFSET`/`ORDINAL` trên mảng rỗng. | `SAFE_OFFSET`/`SAFE_ORDINAL`. |
| Kết quả items đổi thứ tự | Dựa vào thứ tự mặc định của `UNNEST`/`ARRAY_AGG`. | `WITH OFFSET`, `ORDER BY` rõ ràng. |
| `Array cannot have a null element` | `ARRAY_AGG` giữ phần tử NULL ở kết quả cuối. | `IGNORE NULLS`, `COALESCE` hoặc lọc theo định nghĩa. |
| Lỗi nested data khi load JSON | Source không phải ndJSON, sai type/mode hoặc JSON array chứa null. | Kiểm tra từng dòng JSON, schema và load-job error details. |
| Job query scan nhiều dữ liệu | `SELECT *`, thiếu partition filter hoặc join phình. | Dry run, column projection, pruning, query plan. |
| `Access Denied` trên nested field | Thiếu BigQuery IAM/data policy/authorized view hoặc thiếu job permission. | Effective principal, table policy, column permissions và audit. |
| Thêm nested field làm BI report lỗi | Schema evolution không tương thích downstream. | Contract test, consumer SQL và field mode. |

**Thứ tự chẩn đoán:** xác định grain (đơn hay item) → kiểm tra kiểu/mode nested → xem phép `UNNEST` và join → kiểm tra `NULL`/empty arrays → đối chiếu aggregates → đo plan/bytes → xem IAM nếu là lỗi truy cập. Không sửa lỗi nhân dòng bằng cách thêm `DISTINCT` tùy tiện vì có thể xóa cả các bản ghi hợp lệ.

## 14. Bài tập

### Bài 1 — Nhận diện kiểu dữ liệu

Mô tả kiểu GoogleSQL và schema mode cho: (a) một `customer` có `city`; (b) danh sách `tags`; (c) danh sách `items` mỗi phần tử có `sku`, `qty`; (d) mỗi item có một mảng `promotion_codes`. Vì sao không thể khai báo trực tiếp `ARRAY<ARRAY<STRING>>`?

### Bài 2 — Truy cập an toàn

Viết SQL lấy `order_id`, `customer.city`, item đầu tiên và số items trên `demo_orders`. Truy vấn phải trả cả **O-1003** mà không lỗi out-of-range.

### Bài 3 — `UNNEST` làm mất dòng

Với 3 đơn trong dữ liệu mẫu, `CROSS JOIN UNNEST(items)` trả bao nhiêu dòng? `LEFT JOIN UNNEST(items)` trả bao nhiêu? Nêu lý do `COUNT(*)` ở kết quả LEFT không bằng tổng số item.

**Gợi ý:** CROSS = **3 dòng**; LEFT = **4 dòng**, vì O-1003 được giữ với item NULL.

### Bài 4 — Tổng tiền

Viết query tính `total_vnd` cho từng đơn mà không làm mất đơn không có item. Sau đó viết query thống kê `units_sold` theo SKU. Đối chiếu tổng các đơn và tổng theo SKU bằng **410000 VND**.

### Bài 5 — `EXISTS` và lọc mảng

Tìm các đơn có `SKU-A` và các đơn có tag `vip` **mà không bung dòng cha trong kết quả**. Giải thích khi nào dùng `EXISTS`, khi nào dùng `IN UNNEST`.

### Bài 6 — Nhân dòng giữa hai arrays

Với O-1001 có 2 items và 2 tags, nếu `CROSS JOIN UNNEST` cả hai, có bao nhiêu dòng? Tổng tiền sai sẽ là bao nhiêu? Hãy sửa truy vấn để vẫn trả item count, tag count và total.

**Gợi ý:** 4 dòng và tổng tiền có thể bị nhân từ **290000 lên 580000 VND** khi cộng theo item trên tích Descartes.

### Bài 7 — Tạo lại `ARRAY<STRUCT>`

Viết `ARRAY(SELECT AS STRUCT ...)` chỉ giữ items có `qty >= 2`. Truy vấn phải có ba đơn và mảng rỗng cho hai đơn không có item phù hợp. Vì sao nên có `ORDER BY` bên trong?

### Bài 8 — Thiết kế và nạp dữ liệu

Thiết kế bảng `orders_nested` có partition `order_date` và nested `customer`, repeated `items`. Viết một dòng ndJSON tương thích, đề xuất cách dùng `bq load`, schema contract, IAM tối thiểu và cách test load lỗi.

### Bài 9 — Tối ưu production

Một bảng có hàng tỷ đơn, mỗi đơn trung bình 3 items nhưng một số đơn có hàng chục nghìn items. Báo cáo chỉ đọc 7 ngày gần nhất và nhóm theo SKU. Chọn partition/filter, query layout, dry run/Monitoring và cân nhắc khi nào xây bảng item-grain riêng. Nêu một test ngăn việc nhân dòng do hai arrays.

## 15. Checklist áp dụng và tài liệu chính thức

| Hạng mục | Điều cần xác minh |
| --- | --- |
| **Grain và semantics** | Mỗi dòng là đơn, item hay event? `JOIN`/`UNNEST` có làm đổi grain? |
| **Schema** | `STRUCT`/`RECORD`, `ARRAY`/`REPEATED`, field modes và giới hạn lồng nhau đúng. |
| **SQL** | Dot notation, `SAFE_OFFSET`, `CROSS`/`LEFT UNNEST` và `WITH OFFSET` dùng đúng. |
| **Aggregates** | `COUNT`/`SUM` theo đúng grain, empty/null arrays được xử lý có chủ đích. |
| **Reaggregation** | `ARRAY(SELECT AS STRUCT)`, `ARRAY_AGG IGNORE NULLS` và thứ tự array đã kiểm tra. |
| **Modeling** | Nested dùng khi quan hệ cha–con được truy xuất chung; tránh arrays cực dài. |
| **Ingestion** | ndJSON/Parquet/Avro schema khớp, load có logging, hợp đồng và kiểm thử. |
| **Performance** | Partition filter, column projection, dry run, row explosion, query plan và cost. |
| **Security** | IAM Job User/Data Viewer/Writer, PII nested, masking/data policies nếu cần. |
| **Release** | Schema evolution tương thích, CI tests, đối soát dữ liệu và rollback. |

Nguồn chính thức:

- [BigQuery — Nested and repeated columns](https://cloud.google.com/bigquery/docs/nested-repeated)
- [GoogleSQL data types](https://cloud.google.com/bigquery/docs/reference/standard-sql/data-types)
- [GoogleSQL — Work with arrays](https://cloud.google.com/bigquery/docs/arrays)
- [GoogleSQL — `UNNEST` query syntax](https://cloud.google.com/bigquery/docs/reference/standard-sql/query-syntax#unnest_operator)
- [GoogleSQL — Array functions](https://cloud.google.com/bigquery/docs/reference/standard-sql/array_functions)
- [GoogleSQL — Aggregate functions](https://cloud.google.com/bigquery/docs/reference/standard-sql/aggregate_functions)
- [BigQuery — Best practices for nested/repeated fields](https://cloud.google.com/bigquery/docs/best-practices-performance-nested)
- [BigQuery — Load ndJSON from Cloud Storage](https://cloud.google.com/bigquery/docs/loading-data-cloud-storage-json)
- [BigQuery — Partitioned tables](https://cloud.google.com/bigquery/docs/partitioned-tables)
- [BigQuery — Query cost estimation](https://cloud.google.com/bigquery/docs/best-practices-costs)
- [BigQuery — Schema changes](https://cloud.google.com/bigquery/docs/managing-table-schemas)
- [BigQuery — Access control](https://cloud.google.com/bigquery/docs/access-control)

**Ghi nhớ:** `STRUCT` biểu diễn **một đối tượng lồng nhau**, `ARRAY` biểu diễn **nhiều phần tử** và `UNNEST` thay đổi **độ hạt của kết quả**. Chọn `CROSS JOIN` khi thực sự cần một dòng/item, `LEFT JOIN` nếu cần giữ đơn có mảng rỗng, còn `EXISTS` hoặc correlated subquery khi không muốn nhân dòng. Một schema tốt phải đi cùng **kiểm thử kết quả, partition pruning, IAM và đo chi phí**, không chỉ SQL chạy được.


