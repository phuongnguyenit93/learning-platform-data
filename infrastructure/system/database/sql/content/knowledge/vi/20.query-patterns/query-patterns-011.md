# PIVOT, UNPIVOT và cách thay thế theo phương ngữ

Trong báo cáo SQL, dữ liệu giao dịch thường được lưu theo dạng **dài** (*long/tidy format*): mỗi hàng là một giao dịch, một chỉ tiêu hoặc một cặp kỳ–giá trị. Tuy nhiên, người đọc báo cáo thường muốn dạng **rộng** (*wide format*): các tháng, quý, trạng thái hay loại sản phẩm trở thành **những cột cạnh nhau**.

Ví dụ, từ các dòng:

| Khu vực | Tháng | Doanh số |
| --- | --- | ---: |
| North | 2026-01 | 100 |
| North | 2026-01 | 40 |
| North | 2026-02 | 80 |
| South | 2026-01 | 50 |

ta muốn một hàng cho mỗi khu vực:

| Khu vực | Tháng 01 | Tháng 02 |
| --- | ---: | ---: |
| North | 140 | 80 |
| South | 50 | `NULL` |

Biến đổi này được gọi là **PIVOT**: đưa các **giá trị phân loại ở hàng** thành **tên cột**, thường phải dùng phép **tổng hợp** như `SUM`, `COUNT` hoặc `MAX`. Hướng ngược lại là **UNPIVOT**: chuyển một số cột thành các hàng có dạng `(tên_chỉ_tiêu, giá_trị)`.

Nhưng SQL không có một cú pháp PIVOT/UNPIVOT thống nhất được mọi hệ quản trị hỗ trợ theo cùng cách. **SQL Server** và **Oracle** có toán tử riêng; **DuckDB** có cú pháp pivot/unpivot tiện dụng; **PostgreSQL** thường dùng tổng hợp có điều kiện hoặc tiện ích `tablefunc.crosstab`; **MySQL** và **SQLite** thường dùng `CASE`/`GROUP BY` hoặc `UNION ALL`. Cách xử lý `NULL`, tên cột, khóa nhóm và tổng hợp cũng có thể khác nhau.

Bài học thuộc **Database SQL → Mẫu truy vấn → PIVOT, UNPIVOT và cách thay thế theo phương ngữ**. Mục tiêu là hiểu **mô hình dữ liệu và ngữ nghĩa trước cú pháp**, sau đó viết truy vấn phù hợp hệ quản trị đang dùng, tránh nhân đôi số liệu hoặc làm mất thông tin.

## 1. Dữ liệu dài và dữ liệu rộng

### Dạng dài (long format)

Một bảng dài có thể gồm:

```text
region | month_start | amount
-------+-------------+--------
North  | 2026-01-01  | 100
North  | 2026-01-01  | 40
North  | 2026-02-01  | 80
South  | 2026-01-01  | 50
```

Ở đây `month_start` là **giá trị của một cột**, không phải tên nhiều cột khác nhau. Một khu vực trong một tháng có thể có nhiều giao dịch.

### Dạng rộng (wide format)

```text
region | jan_total | feb_total
-------+-----------+----------
North  | 140       | 80
South  | 50        | NULL
```

Giá trị phân loại tháng đã chuyển thành tên cột. Để có `140` cho North–January, ta phải **cộng hai giao dịch** `100 + 40`.

### Hai hướng biến đổi

```text
LONG FORMAT                         WIDE FORMAT

region | month | amount             region | Jan | Feb | Mar
-------+-------+-------            -------+-----+-----+-----
North  | Jan   | 100     ───────▶   North  | 140 |  80 |  60
North  | Jan   |  40       PIVOT    South  |  50 | 100 |   0
North  | Feb   |  80
North  | Mar   |  60
South  | Jan   |  50
South  | Feb   |  75
South  | Feb   |  25
South  | Mar   |   0
                                    │
                                    │ UNPIVOT
                                    ▼
                             region | month | total
                             North  | Jan   | 140
                             North  | Feb   |  80
                             ...
```

**PIVOT rồi UNPIVOT không nhất thiết khôi phục bảng giao dịch ban đầu.** Các giao dịch North–January có thể đã bị gộp từ hai dòng thành một ô 140. Sau khi gộp, ta không còn biết hai giao dịch gốc là 100 và 40 nếu không lưu thêm thông tin.

### Ba thành phần của một PIVOT

Trước khi viết SQL, hãy xác định:

1. **Khóa của mỗi hàng đầu ra** (*row/grain key*): ví dụ `region`. Mỗi vùng mong muốn có một hàng.
2. **Giá trị trở thành cột** (*pivot key/category*): ví dụ `month_start` với các tháng 01, 02, 03.
3. **Phép tổng hợp và biểu thức giá trị** (*measure/aggregation*): ví dụ `SUM(amount)`.

Có thể viết ngắn:

```text
PIVOT = nhóm theo row key
      + chia theo category
      + tổng hợp measure
      + đặt tên các cột category
```

Bỏ qua bất kỳ thành phần nào cũng dễ gây sai số liệu.

## 2. Dữ liệu PostgreSQL để thực hành

Tạo hai bảng tạm:

- `sales_long_257`: giao dịch ở dạng dài, có các khu vực, tháng, kênh bán và số tiền.
- `metrics_wide_257`: chỉ tiêu kinh doanh ở dạng rộng, để thực hành UNPIVOT.

Hãy chạy các câu lệnh trong cùng một kết nối **PostgreSQL thực hành**. Bảng tạm chỉ tồn tại trong phiên. Nếu bảng cùng tên đã có, hãy dùng phiên mới hoặc đổi tên trước khi chạy lại.

### 2.1. Bảng bán hàng dạng dài

```sql
CREATE TEMP TABLE sales_long_257 (
    sale_id      INTEGER PRIMARY KEY,
    region       TEXT NOT NULL,
    month_start  DATE NOT NULL,
    channel      TEXT NOT NULL,
    amount       NUMERIC(12, 2)
);

INSERT INTO sales_long_257 (
    sale_id, region, month_start, channel, amount
)
VALUES
    (1,  'North', DATE '2026-01-01', 'Online', 100.00),
    (2,  'North', DATE '2026-01-01', 'Store',   40.00),
    (3,  'North', DATE '2026-02-01', 'Online',  80.00),
    (4,  'North', DATE '2026-02-01', 'Store',     NULL),
    (5,  'North', DATE '2026-03-01', 'Store',   60.00),

    (6,  'South', DATE '2026-01-01', 'Online',  50.00),
    (7,  'South', DATE '2026-02-01', 'Store',   75.00),
    (8,  'South', DATE '2026-02-01', 'Online',  25.00),
    (9,  'South', DATE '2026-03-01', 'Online',   0.00),
    (10, 'South', DATE '2026-03-01', 'Store',     NULL),

    (11, 'East',  DATE '2026-01-01', 'Online',  30.00),
    (12, 'East',  DATE '2026-03-01', 'Store',     NULL);

SELECT sale_id, region, month_start, channel, amount
FROM sales_long_257
ORDER BY region, month_start, sale_id;
```

Tập dữ liệu có ba trạng thái quan trọng:

- **North–January:** hai hàng hợp lệ, cần tổng hợp thành `140`.
- **East–February:** **không có giao dịch nào** trong tháng.
- **East–March:** có **một giao dịch nhưng amount = NULL**.

Trong khi đó South–March có hai giao dịch, `0` và `NULL`, nên tổng các số tiền **đã biết** là **0**, không phải `NULL`.

### 2.2. Bảng chỉ tiêu dạng rộng

```sql
CREATE TEMP TABLE metrics_wide_257 (
    region   TEXT PRIMARY KEY,
    revenue  NUMERIC(12, 2),
    cost     NUMERIC(12, 2),
    refunds  NUMERIC(12, 2)
);

INSERT INTO metrics_wide_257 (region, revenue, cost, refunds)
VALUES
    ('North', 240.00, 180.00, NULL),
    ('South', 190.00, 130.00, 0.00),
    ('East',   30.00,   NULL, NULL);

SELECT *
FROM metrics_wide_257
ORDER BY region;
```

| region | revenue | cost | refunds |
| --- | ---: | ---: | ---: |
| East | 30 | `NULL` | `NULL` |
| North | 240 | 180 | `NULL` |
| South | 190 | 130 | 0 |

Bảng này minh họa **ba loại chỉ tiêu**, không phải ba kỳ thời gian. UNPIVOT được sử dụng cho cả hai dạng: cột tháng và cột chỉ tiêu.

## 3. PIVOT bằng tổng hợp có điều kiện: cách dễ chuyển hệ nhất

Khi đã biết trước danh sách cột cần xuất, phương pháp phổ biến là:

```sql
SELECT row_key,
       AGG(
           CASE WHEN category = 'A' THEN measure END
       ) AS column_a,
       AGG(
           CASE WHEN category = 'B' THEN measure END
       ) AS column_b
FROM source
GROUP BY row_key;
```

Ở đây `AGG` là `SUM`, `COUNT`, `MAX` hoặc hàm phù hợp với nghiệp vụ.

### PostgreSQL: SUM và CASE

```sql
SELECT
    region,
    SUM(
        CASE
            WHEN month_start = DATE '2026-01-01' THEN amount
        END
    ) AS jan_total,
    SUM(
        CASE
            WHEN month_start = DATE '2026-02-01' THEN amount
        END
    ) AS feb_total,
    SUM(
        CASE
            WHEN month_start = DATE '2026-03-01' THEN amount
        END
    ) AS mar_total
FROM sales_long_257
GROUP BY region
ORDER BY region;
```

Kết quả:

| region | jan_total | feb_total | mar_total |
| --- | ---: | ---: | ---: |
| East | 30 | `NULL` | `NULL` |
| North | 140 | 80 | 60 |
| South | 50 | 100 | 0 |

Ý nghĩa:

- `GROUP BY region` xác định **mỗi hàng đầu ra**.
- Mỗi `CASE` chỉ cho phép số tiền của một tháng đi vào phép `SUM`.
- Khi `WHEN` không đúng và không có `ELSE`, `CASE` trả `NULL`.
- `SUM` bỏ qua các đầu vào `NULL`.
- Một ô có thể `NULL` nếu tháng đó **không có hàng** hoặc **có hàng nhưng toàn amount = NULL**.

### Tại sao phải GROUP BY?

Nếu bỏ `GROUP BY region` nhưng vẫn chọn `region` và `SUM(...)`, PostgreSQL sẽ báo lỗi vì `region` không được tổng hợp hoặc nhóm.

Trong mẫu này, khóa nhóm là `region`. Với hệ đa tenant, khóa đúng có thể phải là cặp `(tenant_id, region)`. Nếu chỉ nhóm theo region, số liệu các tenant cùng tên vùng bị cộng vào nhau.

**Mỗi ô của PIVOT phải thuộc một nhóm dữ liệu được xác định rõ**, không thể chỉ “đảo cột và hàng” mà không định nghĩa mức độ tổng hợp.

## 4. PostgreSQL: PIVOT bằng FILTER

PostgreSQL hỗ trợ cú pháp `FILTER (WHERE ...)` cho hàm tổng hợp. Nó thường dễ đọc hơn nhiều biểu thức `CASE` lồng trong `SUM`.

```sql
SELECT
    region,
    SUM(amount) FILTER (
        WHERE month_start = DATE '2026-01-01'
    ) AS jan_total,
    SUM(amount) FILTER (
        WHERE month_start = DATE '2026-02-01'
    ) AS feb_total,
    SUM(amount) FILTER (
        WHERE month_start = DATE '2026-03-01'
    ) AS mar_total
FROM sales_long_257
GROUP BY region
ORDER BY region;
```

Kết quả giống truy vấn `SUM(CASE...)` ở mục 3.

Đọc biểu thức:

```sql
SUM(amount) FILTER (WHERE month_start = DATE '2026-01-01')
```

thành: “Chỉ đưa số tiền thuộc tháng 1 vào **hàm SUM này**, không thay đổi tập hàng được các hàm khác nhìn thấy”.

### FILTER cho nhiều chỉ số trong cùng báo cáo

```sql
SELECT
    region,

    SUM(amount) FILTER (
        WHERE month_start = DATE '2026-03-01'
    ) AS mar_total,

    COUNT(*) FILTER (
        WHERE month_start = DATE '2026-03-01'
    ) AS mar_sales_rows,

    COUNT(amount) FILTER (
        WHERE month_start = DATE '2026-03-01'
    ) AS mar_known_amount_rows

FROM sales_long_257
GROUP BY region
ORDER BY region;
```

| region | mar_total | mar_sales_rows | mar_known_amount_rows |
| --- | ---: | ---: | ---: |
| East | `NULL` | 1 | 0 |
| North | 60 | 1 | 1 |
| South | 0 | 2 | 1 |

Ở East–March, có **một hàng thật** nhưng số tiền thiếu; ở South–March có một số tiền 0 thật và một giá trị thiếu. Việc dùng `COUNT(*)` cùng `COUNT(amount)` giúp phân biệt mức độ đầy đủ của dữ liệu.

### FILTER không phải cú pháp chung cho mọi DBMS

PostgreSQL và các phiên bản SQLite phù hợp hỗ trợ dạng `FILTER`. SQL Server và MySQL không có cùng cú pháp `SUM(x) FILTER (WHERE ...)` thông dụng. Khi chuyển sang những hệ đó, dùng `CASE` bên trong hàm tổng hợp:

```sql
SUM(CASE WHEN category = 'A' THEN measure END)
```

Với các ví dụ ngày tháng, cú pháp literal ngày cũng cần đổi theo phương ngữ.

## 5. NULL: không có hàng, toàn NULL và giá trị 0

PIVOT tạo các cột theo một danh sách category, nhưng với mỗi cột, phép tổng hợp vẫn tuân theo quy tắc `NULL` thông thường.

### Ba tình huống trên bộ dữ liệu

| Cặp region–month | Trạng thái dữ liệu nguồn | `SUM(amount)` |
| --- | --- | ---: |
| East–2026-02 | Không có hàng | `NULL` |
| East–2026-03 | Một hàng, amount = `NULL` | `NULL` |
| South–2026-03 | Hai hàng, amount = 0 và `NULL` | 0 |

**Chỉ nhìn cột pivot sau `SUM` không phân biệt được “không có hàng” và “toàn `NULL`”.**

### COALESCE sau tổng hợp

Nếu nghiệp vụ quy định mọi ô không có tổng đều được **hiển thị** bằng 0:

```sql
SELECT
    region,
    COALESCE(
        SUM(amount) FILTER (
            WHERE month_start = DATE '2026-01-01'
        ), 0::NUMERIC
    ) AS jan_display,
    COALESCE(
        SUM(amount) FILTER (
            WHERE month_start = DATE '2026-02-01'
        ), 0::NUMERIC
    ) AS feb_display,
    COALESCE(
        SUM(amount) FILTER (
            WHERE month_start = DATE '2026-03-01'
        ), 0::NUMERIC
    ) AS mar_display
FROM sales_long_257
GROUP BY region
ORDER BY region;
```

Khi đó East–February và East–March đều hiện **0**, dù ý nghĩa dữ liệu nguồn khác nhau. Đây là chính sách hiển thị, không phải cách tự động làm dữ liệu đầy đủ.

### COALESCE bên trong có thể khác COALESCE bên ngoài

Hai biểu thức:

```sql
COALESCE(SUM(amount) FILTER (WHERE p), 0)
```

và:

```sql
SUM(CASE WHEN p THEN COALESCE(amount, 0) END)
```

không luôn giống nhau.

- Nếu **không có hàng** thỏa `p`, biểu thức thứ nhất trả 0, biểu thức thứ hai trả `NULL`.
- Nếu **có hàng** thỏa `p` nhưng tất cả amount đều `NULL`, cả hai có thể trả 0, nhưng cách thứ hai đã **chuyển thiếu dữ liệu thành giá trị 0 trước khi cộng**.
- Với `AVG`, việc thay `NULL` bằng 0 trước tổng hợp còn có thể làm đổi **mẫu số**.

Cần đặt `COALESCE` ở cấp đúng với chính sách dữ liệu.

## 6. Một mẫu PIVOT khác: tổng hợp theo trạng thái hoặc kênh bán

Không nhất thiết chỉ pivot theo tháng. Có thể đưa `channel` thành các cột:

```sql
SELECT
    region,
    SUM(amount) FILTER (
        WHERE channel = 'Online'
    ) AS online_total,
    SUM(amount) FILTER (
        WHERE channel = 'Store'
    ) AS store_total
FROM sales_long_257
GROUP BY region
ORDER BY region;
```

Kết quả:

| region | online_total | store_total |
| --- | ---: | ---: |
| East | 30 | `NULL` |
| North | 180 | 100 |
| South | 75 | 75 |

Tổng North: Online = 100 + 80 = 180; Store = 40 + 60 + một giá trị `NULL` = 100. South: Online = 50 + 25 + 0 = 75; Store = 75 + `NULL` = 75.

**Nếu muốn pivot theo cả tháng và kênh**, tên cột là các tổ hợp như `jan_online`, `jan_store`, `feb_online`:

```sql
SELECT
    region,
    SUM(amount) FILTER (
        WHERE month_start = DATE '2026-01-01'
          AND channel = 'Online'
    ) AS jan_online,

    SUM(amount) FILTER (
        WHERE month_start = DATE '2026-01-01'
          AND channel = 'Store'
    ) AS jan_store,

    SUM(amount) FILTER (
        WHERE month_start = DATE '2026-02-01'
          AND channel = 'Online'
    ) AS feb_online,

    SUM(amount) FILTER (
        WHERE month_start = DATE '2026-02-01'
          AND channel = 'Store'
    ) AS feb_store
FROM sales_long_257
GROUP BY region
ORDER BY region;
```

Mỗi ô tương ứng với **một tổ hợp điều kiện**. Khi danh sách category nhiều chiều tăng lên, số cột có thể tăng rất nhanh; lúc này việc giữ dạng dài để phân tích hoặc dùng công cụ BI chuyên biệt có thể hiệu quả hơn.

## 7. Đếm, tính tỷ lệ, lấy MAX thay cho SUM

PIVOT không đồng nghĩa luôn dùng `SUM`. Phép tổng hợp phải đúng ý nghĩa đo lường.

### 7.1. Đếm số giao dịch

```sql
SELECT
    region,
    COUNT(*) FILTER (
        WHERE month_start = DATE '2026-01-01'
    ) AS jan_transactions,
    COUNT(*) FILTER (
        WHERE month_start = DATE '2026-02-01'
    ) AS feb_transactions,
    COUNT(*) FILTER (
        WHERE month_start = DATE '2026-03-01'
    ) AS mar_transactions
FROM sales_long_257
GROUP BY region
ORDER BY region;
```

Kết quả:

| region | jan_transactions | feb_transactions | mar_transactions |
| --- | ---: | ---: | ---: |
| East | 1 | 0 | 1 |
| North | 2 | 2 | 1 |
| South | 1 | 2 | 2 |

`COUNT(*) FILTER` trả 0 khi không có hàng thỏa điều kiện trong nhóm khu vực.

### 7.2. Đếm số giao dịch đã biết tiền

```sql
COUNT(amount) FILTER (
    WHERE month_start = DATE '2026-03-01'
)
```

khác `COUNT(*) FILTER` ở những giao dịch `amount = NULL`.

### 7.3. MAX cho dữ liệu có một giá trị mỗi nhóm

Nếu nguồn đã đảm bảo một giá trị cho mỗi `(region, month)`, có thể dùng:

```sql
MAX(CASE
    WHEN month_start = DATE '2026-01-01' THEN amount
END) AS jan_value
```

Nhưng trong bảng giao dịch hiện tại, North–January có **100 và 40**:

- `SUM` trả **140**.
- `MAX` trả **100**.
- `AVG` trả **70**.

Không có một hàm “đúng” cho mọi mô hình dữ liệu. Nếu yêu cầu là **tổng doanh thu**, chọn `SUM`; nếu yêu cầu là **giao dịch lớn nhất**, chọn `MAX`.

Nếu muốn chọn một bản ghi trạng thái *mới nhất* theo thời điểm, dùng `MAX(status)` có thể chỉ chọn theo **thứ tự chữ** chứ không phải bản ghi mới nhất. Cần xác định bản ghi theo thời gian hoặc thứ tự ưu tiên trước khi pivot.

### 7.4. Không nên dùng DISTINCT để chữa sai grain

`SUM(DISTINCT amount)` cộng **các giá trị tiền khác nhau**, không phải cộng mọi giao dịch khác nhau. Nếu hai giao dịch hợp lệ cùng có số tiền 100, `SUM(DISTINCT amount)` chỉ cộng 100 một lần.

Khi kết quả pivot bị nhân đôi, phải kiểm tra quan hệ nối và khóa nhóm trước khi dùng `DISTINCT`.

## 8. PIVOT trước hay sau JOIN? Cẩn thận nhân bản hàng nguồn

Giả sử một giao dịch được nối tới nhiều dòng chi tiết khác, ví dụ nhiều mã khuyến mãi. Nếu viết:

```sql
FROM sales AS s
JOIN sale_promotions AS p
  ON p.sale_id = s.sale_id
```

và một `sale_id` khớp ba dòng `promotion`, tiền của sale đó có thể bị lặp **ba lần** trước khi đi vào `SUM` pivot.

Đây là lỗi **cardinality** của `JOIN`, không phải lỗi toán tử PIVOT.

Một hướng xử lý là tổng hợp đúng cấp trước:

```sql
-- Mẫu minh họa với các bảng giả định
WITH sales_at_grain AS (
    SELECT s.sale_id,
           s.region,
           s.month_start,
           s.amount
    FROM sales AS s
),
monthly_sales AS (
    SELECT region,
           month_start,
           SUM(amount) AS month_total
    FROM sales_at_grain
    GROUP BY region, month_start
)
SELECT
    region,
    SUM(month_total) FILTER (
        WHERE month_start = DATE '2026-01-01'
    ) AS jan_total
FROM monthly_sales
GROUP BY region;
```

Đoạn trên minh họa việc **giữ đúng grain giao dịch trước khi tổng hợp**; trong trường hợp đơn giản, tầng `sales_at_grain` không cần thiết. Nếu cần dữ liệu từ bảng một-nhiều, phải xác định cách chọn hoặc tính tổng từ bảng đó sao cho không nhân bản một sự kiện.

### Kiểm tra tính duy nhất của grain

```sql
SELECT region, month_start, COUNT(*) AS source_rows
FROM sales_long_257
GROUP BY region, month_start
HAVING COUNT(*) > 1
ORDER BY region, month_start;
```

Truy vấn trên chỉ ra các cặp `(region, month_start)` có nhiều giao dịch. Với **dữ liệu giao dịch**, điều này là bình thường; PIVOT cần phép tổng hợp. Với **bảng đã tổng hợp sẵn theo tháng**, nhiều dòng có thể là lỗi dữ liệu cần điều tra.

## 9. PIVOT tĩnh và PIVOT động

### PIVOT tĩnh: biết trước danh sách cột

Ví dụ ba tháng:

```text
jan_total, feb_total, mar_total
```

Các cột được viết sẵn trong SQL. Cách này thích hợp cho báo cáo có kỳ cố định hoặc hợp đồng API rõ ràng.

**Ưu điểm:** metadata ổn định, dễ dùng với Java DTO, ORM, bảng báo cáo, kiểm soát kiểu và dễ bảo trì.

**Giới hạn:** khi xuất hiện tháng mới hoặc category mới, phải cập nhật câu truy vấn hoặc sinh thêm cột.

### PIVOT động: cột xuất hiện theo dữ liệu

Nếu muốn “mỗi tháng có trong dữ liệu tự trở thành một cột”, không thể kỳ vọng một câu `SELECT` tĩnh đơn giản tự thay đổi danh sách cột ở mọi DBMS. Tên cột là một phần của cấu trúc kết quả SQL và thường cần được xác định khi phân tích truy vấn.

Các hướng triển khai:

1. Ở tầng ứng dụng, truy vấn danh sách category được phép hiển thị, **sinh SQL** với các cột thích hợp, rồi thực thi bằng cơ chế an toàn.
2. Dùng dynamic SQL hoặc tính năng dynamic PIVOT của DBMS nếu có.
3. Trả **JSON object** hoặc cấu trúc map/array chứa category→giá trị, giữ một schema cột cố định.
4. Trả dữ liệu **dài**, để công cụ BI/frontend tự pivot.

### PostgreSQL: trả JSONB thay vì sinh hàng chục cột

```sql
WITH monthly_totals AS (
    SELECT
        region,
        TO_CHAR(month_start, 'YYYY-MM') AS month_key,
        SUM(amount) AS month_total
    FROM sales_long_257
    GROUP BY region, TO_CHAR(month_start, 'YYYY-MM')
)
SELECT
    region,
    JSONB_OBJECT_AGG(
        month_key, month_total ORDER BY month_key
    ) AS totals_by_month
FROM monthly_totals
GROUP BY region
ORDER BY region;
```

Dạng kết quả ví dụ:

```json
{
  "region": "North",
  "totals_by_month": {
    "2026-01": 140.00,
    "2026-02": 80.00,
    "2026-03": 60.00
  }
}
```

Với East:

- Không có giao dịch February → khóa `"2026-02"` **không xuất hiện** trong JSON.
- March có giao dịch nhưng tổng toàn `NULL` → khóa `"2026-03"` có giá trị JSON `null`.

Đây là sự khác biệt có ích giữa **thiếu khóa** và **khóa có giá trị null** mà nhiều bảng pivot tĩnh dễ làm mờ nếu chỉ nhìn một ô `NULL`.

### An toàn khi sinh SQL động

Tên cột và tên đối tượng SQL **không được thay thế bằng tham số giá trị thông thường** theo cách giống `WHERE region = ?`. Nếu phải ghép danh sách định danh vào SQL động:

- Lấy category từ dữ liệu đáng tin cậy hoặc **allowlist** đã xác định.
- Dùng cơ chế quote định danh **đúng DBMS**: ví dụ `QUOTENAME` của SQL Server hoặc `format('%I', identifier)` của PostgreSQL.
- Không nối nguyên văn chuỗi người dùng vào danh sách tên cột.
- Sử dụng tham số ràng buộc cho **giá trị lọc** thay vì ghép chuỗi.
- Giới hạn số cột, độ dài tên và số category để tránh truy vấn quá lớn.
- Xác định cơ chế phá trùng tên cột sau chuẩn hóa category.

Dynamic SQL có thể hữu ích, nhưng là bài toán **thiết kế truy vấn và an toàn dữ liệu**, không chỉ là thêm một vòng lặp ghép chuỗi.

## 10. SQL Server: cú pháp PIVOT gốc

SQL Server hỗ trợ toán tử `PIVOT` trong `FROM`. Với một bảng có cấu trúc tương đương `sales_long_257` trên SQL Server, có thể viết:

```sql
-- SQL Server: cú pháp riêng của SQL Server
SELECT
    p.region,
    p.[2026-01] AS jan_total,
    p.[2026-02] AS feb_total,
    p.[2026-03] AS mar_total
FROM (
    SELECT
        region,
        CONVERT(CHAR(7), month_start, 120) AS month_key,
        amount
    FROM sales_long_257
) AS src
PIVOT (
    SUM(amount)
    FOR month_key IN (
        [2026-01],
        [2026-02],
        [2026-03]
    )
) AS p
ORDER BY p.region;
```

**Đây là mã SQL Server, không chạy nguyên văn trên PostgreSQL.**

Giải thích:

- Truy vấn nguồn `src` chỉ xuất ra `region`, `month_key`, `amount`.
- `SUM(amount)` là phép tổng hợp.
- `FOR month_key IN (...)` liệt kê giá trị sẽ trở thành cột.
- `[2026-01]` là **định danh cột được quote theo cú pháp SQL Server**, không phải một hằng số SQL trừ đi phép toán.
- Phần `SELECT` ngoài đổi tên cột thành `jan_total`, `feb_total`, `mar_total` dễ dùng hơn.

### Tại sao phải cắt nguồn còn đúng các cột cần thiết?

Một lỗi hay gặp ở SQL Server `PIVOT` là đưa thêm `sale_id`, `channel` hoặc cột khác vào nguồn `src`:

```sql
-- Sai ý định một hàng mỗi region:
SELECT sale_id, region, month_key, amount
FROM ...
```

`PIVOT` của SQL Server thực hiện nhóm theo các cột nguồn còn lại sau khi trừ cột pivot và cột aggregate. Nếu còn `sale_id`, kết quả có thể **tách thành nhiều hàng cho một region**, thay vì một hàng tổng.

Vì vậy trong nguồn PIVOT, hãy **chỉ chọn cột khóa hàng, cột pivot và cột giá trị cần tổng hợp**. Với yêu cầu một hàng mỗi khu vực, nguồn đúng là ba cột `region`, `month_key`, `amount`.

### Dynamic PIVOT trong SQL Server

Một cách tiếp cận thường gặp:

1. Truy vấn danh sách `month_key`.
2. Chuyển từng giá trị thành định danh an toàn bằng `QUOTENAME(month_key)`.
3. Ghép các tên đã được quote thành danh sách `IN (...)`.
4. Tạo câu PIVOT động và thực thi bằng `sp_executesql`.
5. Giới hạn danh sách cột theo kỳ báo cáo thực sự được phép xuất.

Ví dụ lấy chuỗi tên cột an toàn trong một ngữ cảnh SQL Server hiện đại:

```sql
-- SQL Server: chỉ minh họa bước xây danh sách định danh
SELECT STRING_AGG(
           QUOTENAME(month_key), ','
       ) AS pivot_column_list
FROM (
    SELECT DISTINCT
        CONVERT(CHAR(7), month_start, 120) AS month_key
    FROM sales_long_257
) AS m;
```

Chuỗi thu được có dạng:

```text
[2026-01],[2026-02],[2026-03]
```

Muốn thứ tự cột được bảo đảm, cần thêm cơ chế thứ tự được hỗ trợ (chẳng hạn `WITHIN GROUP (ORDER BY ...)` khi phù hợp). Mẫu trên mới là **bước chuẩn bị**, không phải toàn bộ dynamic SQL.

Không lấy `month_key` từ một input không kiểm soát rồi ghép thẳng vào truy vấn.

## 11. Oracle: PIVOT với danh sách giá trị

Oracle Database cũng hỗ trợ `PIVOT`. Giả sử bảng đã có cùng ý nghĩa nhưng dùng kiểu dữ liệu của Oracle:

```sql
-- Oracle Database
SELECT
    region,
    jan_total,
    feb_total,
    mar_total
FROM (
    SELECT region, month_start, amount
    FROM sales_long_257
)
PIVOT (
    SUM(amount)
    FOR month_start IN (
        DATE '2026-01-01' AS jan_total,
        DATE '2026-02-01' AS feb_total,
        DATE '2026-03-01' AS mar_total
    )
)
ORDER BY region;
```

Ở đây `DATE '2026-01-01'` là giá trị tháng được so khớp với cột `month_start`, còn `AS jan_total` đặt tên cột đầu ra.

Một ưu điểm của `PIVOT` gốc là thể hiện rất rõ quan hệ **aggregation → pivot key → danh sách cột**, nhưng bạn vẫn phải hiểu khóa nhóm ẩn, sự trùng dữ liệu và ý nghĩa `NULL`.

### Oracle PIVOT có thể dùng nhiều aggregate

Khi cần vừa tổng tiền vừa đếm giao dịch:

```sql
-- Oracle: ví dụ cú pháp nhiều phép tổng hợp
SELECT *
FROM (
    SELECT region, month_start, amount
    FROM sales_long_257
)
PIVOT (
    SUM(amount) AS total,
    COUNT(amount) AS known_count
    FOR month_start IN (
        DATE '2026-01-01' AS jan,
        DATE '2026-02-01' AS feb
    )
);
```

Các cột kết quả được tạo dựa trên kết hợp **alias category** và **alias aggregate**, chẳng hạn `JAN_TOTAL` và `JAN_KNOWN_COUNT` theo quy tắc đặt tên của Oracle.

Oracle còn có những biến thể như `PIVOT XML` trong một số trường hợp cần category động, nhưng đầu ra XML/metadata và cách truy cập khác bảng cột tĩnh. Không nên hiểu PIVOT XML là tự động biến mọi category thành cột SQL cố định.

## 12. PostgreSQL: crosstab của tiện ích tablefunc

PostgreSQL **không có toán tử `PIVOT ... FOR ... IN ...` gốc theo cách SQL Server/Oracle**. Ngoài `FILTER` và `CASE`, PostgreSQL còn có hàm `crosstab` của extension `tablefunc`.

Phần này là **tùy chọn nâng cao**: extension có thể chưa được cài, chưa được bật hoặc tài khoản thực hành không có quyền tạo extension. Những ví dụ `FILTER` ở các mục trước **không cần** extension này.

### 12.1. Kích hoạt tablefunc nếu môi trường cho phép

```sql
-- PostgreSQL: chỉ chạy khi môi trường thực hành cho phép
CREATE EXTENSION IF NOT EXISTS tablefunc;
```

Nếu thiếu quyền, không cần cố thực thi bằng tài khoản sản xuất. Có thể tiếp tục thực hành PIVOT bằng `SUM(...) FILTER` hoặc `SUM(CASE...)`.

### 12.2. crosstab với hai truy vấn nguồn

```sql
-- PostgreSQL, cần extension tablefunc
SELECT *
FROM crosstab(
    $source$
        SELECT
            region,
            TO_CHAR(month_start, 'YYYY-MM') AS month_key,
            SUM(amount)::NUMERIC AS month_total
        FROM sales_long_257
        GROUP BY region, TO_CHAR(month_start, 'YYYY-MM')
        ORDER BY 1, 2
    $source$,
    $category$
        SELECT UNNEST(
            ARRAY['2026-01', '2026-02', '2026-03']::TEXT[]
        )
    $category$
) AS pivot_result(
    region    TEXT,
    jan_total NUMERIC,
    feb_total NUMERIC,
    mar_total NUMERIC
)
ORDER BY region;
```

Giải thích:

1. Truy vấn thứ nhất tạo **row key** (`region`), **category** (`month_key`) và **measure** (`month_total`).
2. Vì dữ liệu giao dịch có nhiều hàng cùng region–month, ta **SUM trước** để mỗi cặp thành một giá trị.
3. Truy vấn thứ hai liệt kê category theo **thứ tự cột mong muốn**.
4. Câu `AS pivot_result(...)` khai báo **tên và kiểu cột đầu ra**. Điều này là bắt buộc cho dạng `crosstab` trả một kiểu bản ghi tổng quát.
5. Các category không có giá trị ứng với một row key thường tạo ô `NULL`.

### crosstab không phải câu thần chú thay thế GROUP BY

Nếu nguồn của `crosstab` còn nhiều hàng cho cùng `(region, month_key)`, công cụ không có nghĩa vụ tự quyết định cần cộng hay đếm theo nghiệp vụ. Tốt nhất **tổng hợp trước** như ví dụ.

Ngoài ra:

- Danh sách category phải nhất quán với kiểu dữ liệu đầu ra và thứ tự cột.
- Kiểu giá trị trong nguồn phải tương thích với kiểu cột được khai báo.
- Dữ liệu category sai tên hoặc thiếu có thể làm mất/để trống ô.
- Cách lập truy vấn crosstab và quyền extension không thuận tiện trong mọi môi trường.

Với báo cáo có ba hoặc vài cột cố định, `FILTER` thường đơn giản và dễ bảo trì hơn.

## 13. MySQL và SQLite: PIVOT bằng CASE

MySQL không có một toán tử `PIVOT` gốc tương tự `PIVOT ... FOR ... IN ...` của SQL Server. Cách thực tế thường là `SUM(CASE...)`:

```sql
-- MySQL 8+: bảng có month_start kiểu DATE
SELECT
    region,
    SUM(
        CASE WHEN month_start = '2026-01-01'
             THEN amount END
    ) AS jan_total,
    SUM(
        CASE WHEN month_start = '2026-02-01'
             THEN amount END
    ) AS feb_total,
    SUM(
        CASE WHEN month_start = '2026-03-01'
             THEN amount END
    ) AS mar_total
FROM sales_long_257
GROUP BY region
ORDER BY region;
```

`'2026-01-01'` ở đây là biểu diễn ngày có thể được MySQL chuyển phù hợp khi so với cột kiểu DATE; khi triển khai thực tế, nên dùng tham số kiểu ngày hoặc cách truyền ngày tương thích DBMS.

### SQLite với ngày được lưu dạng TEXT ISO

SQLite không có kiểu `DATE` riêng với cùng cơ chế của PostgreSQL. Nếu `month_start` được lưu dạng văn bản ISO `YYYY-MM-DD`:

```sql
-- SQLite: giả định month_start là TEXT dạng YYYY-MM-DD
SELECT
    region,
    SUM(CASE
        WHEN month_start = '2026-01-01' THEN amount
    END) AS jan_total,
    SUM(CASE
        WHEN month_start = '2026-02-01' THEN amount
    END) AS feb_total,
    SUM(CASE
        WHEN month_start = '2026-03-01' THEN amount
    END) AS mar_total
FROM sales_long_257
GROUP BY region
ORDER BY region;
```

SQLite còn hỗ trợ `FILTER` trong các phiên bản phù hợp, nhưng `SUM(CASE...)` là mẫu dễ hiểu khi cần hướng tới nhiều DBMS.

### Không đổi cách viết hằng ngày một cách máy móc

Một số DBMS hỗ trợ `DATE '2026-01-01'`, một số dùng hàm hoặc cơ chế chuyển kiểu khác. Khi cột gốc là `TIMESTAMP`, so sánh bằng ngày đầu tháng **không** tự lấy tất cả giao dịch của cả tháng. Cần xác định kỳ:

```sql
-- PostgreSQL: khi có cột timestamp sold_at
WHERE sold_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND sold_at <  TIMESTAMP '2026-02-01 00:00:00'
```

Hoặc chuẩn hóa đầu vào:

```sql
-- PostgreSQL
DATE_TRUNC('month', sold_at)::DATE AS month_start
```

với lưu ý về múi giờ nếu nguồn là `TIMESTAMPTZ`.

**PIVOT theo tháng trước hết cần định nghĩa tháng và chuẩn hóa kỳ**, rồi mới chuyển category thành cột.

## 14. DuckDB: cú pháp PIVOT tiện cho phân tích

DuckDB cung cấp cú pháp `PIVOT` thuận tiện cho phân tích dữ liệu. Với bảng tương đương:

```sql
-- DuckDB, không phải PostgreSQL:
PIVOT sales_long_257
ON strftime(month_start, '%Y-%m')
IN ('2026-01', '2026-02', '2026-03')
USING sum(amount)
GROUP BY region;
```

Ý nghĩa:

- `ON ...` xác định category trở thành cột.
- `IN (...)` liệt kê các category mục tiêu.
- `USING sum(amount)` chọn phép tổng hợp.
- `GROUP BY region` quy định mỗi hàng theo khu vực.

DuckDB còn hỗ trợ dạng đơn giản hơn mà danh sách category có thể được suy ra từ dữ liệu trong những tình huống phù hợp. Đây là tiện ích của **phương ngữ DuckDB**, không phải khả năng chung của mọi DBMS.

Dù cú pháp ngắn gọn, các câu hỏi về **trùng key**, `NULL`, số lượng category và khả năng phục hồi dữ liệu sau pivot vẫn giữ nguyên.

## 15. So sánh nhanh phương pháp PIVOT

| Hệ quản trị | Cách thường dùng | Ghi chú |
| --- | --- | --- |
| **PostgreSQL** | `SUM(CASE...)`; `SUM(...) FILTER (WHERE ...)` | Dễ đọc, tên cột tĩnh; có thể dùng `tablefunc.crosstab` nếu bật extension |
| **SQL Server** | `PIVOT (SUM(...) FOR category IN (...))` | Nguồn PIVOT chỉ nên chứa đúng row key, category và measure để tránh nhóm ngoài ý muốn |
| **Oracle Database** | `PIVOT (SUM(...) FOR category IN (...))` | Hỗ trợ nhiều aggregate và biến thể nâng cao như PIVOT XML |
| **MySQL** | `SUM(CASE...)` | Danh sách cột động thường cần dynamic SQL hoặc thực hiện ở ứng dụng |
| **SQLite** | `SUM(CASE...)`, `FILTER` ở phiên bản phù hợp | Kiểu ngày và quy tắc động kiểu khác PostgreSQL |
| **DuckDB** | `PIVOT ... ON ... USING ... GROUP BY ...` | Thuận tiện cho phân tích, có những tính năng dynamic pivot riêng |

Mẫu **conditional aggregation** thường là điểm chung dễ di chuyển nhất. Nhưng “có thể viết lại bằng CASE” không đồng nghĩa mọi hàm, kiểu dữ liệu và chi tiết kết quả đều giống hệt giữa các DBMS.

---

## 16. UNPIVOT: chuyển cột thành các hàng

UNPIVOT là hướng ngược với PIVOT ở mức **hình dạng dữ liệu**.

Từ:

| region | revenue | cost | refunds |
| --- | ---: | ---: | ---: |
| North | 240 | 180 | `NULL` |
| South | 190 | 130 | 0 |

muốn có:

| region | metric_name | metric_value |
| --- | --- | ---: |
| North | revenue | 240 |
| North | cost | 180 |
| North | refunds | `NULL` |
| South | revenue | 190 |
| South | cost | 130 |
| South | refunds | 0 |

Mỗi cột nguồn được chuyển thành:

- **Tên của chỉ tiêu:** `'revenue'`, `'cost'`, `'refunds'`.
- **Giá trị của chỉ tiêu:** giá trị trong cột tương ứng.

Trong UNPIVOT, cần phân biệt **giữ NULL** và **loại NULL**. Một số toán tử UNPIVOT gốc mặc định **bỏ các ô NULL**, nhưng cách dùng `UNION ALL` hoặc `VALUES` thường giữ lại chúng nếu không thêm bộ lọc.

### Không nên nghĩ UNPIVOT chỉ dùng cho tháng

UNPIVOT hữu ích với:

- Bảng khảo sát có cột `answer_q1`, `answer_q2`, `answer_q3`.
- Bảng chỉ tiêu có `revenue`, `cost`, `refunds`.
- Bảng năng lực có cột điểm của nhiều môn học.
- Bảng báo cáo cũ có `jan`, `feb`, `mar`.
- Bảng cấu hình có nhiều thuộc tính cần chuyển thành cặp key–value.

Tuy nhiên, không phải mọi bảng rộng đều nên UNPIVOT. Nếu các cột mang kiểu rất khác nhau (ngày, số, boolean, JSON), một cột `metric_value` chung có thể cần chuyển thành kiểu chung, gây mất tính chặt chẽ của schema.

## 17. PostgreSQL: UNPIVOT bằng CROSS JOIN LATERAL (VALUES ...)

PostgreSQL không có toán tử `UNPIVOT` gốc theo kiểu SQL Server/Oracle, nhưng có thể chuyển từng hàng rộng thành nhiều hàng bằng `CROSS JOIN LATERAL`:

```sql
SELECT
    m.region,
    v.metric_name,
    v.metric_value
FROM metrics_wide_257 AS m
CROSS JOIN LATERAL (
    VALUES
        ('revenue'::TEXT, m.revenue),
        ('cost'::TEXT,    m.cost),
        ('refunds'::TEXT, m.refunds)
) AS v(metric_name, metric_value)
ORDER BY m.region, v.metric_name;
```

Mỗi hàng `m` sinh **ba hàng v**:

- `('revenue', m.revenue)`.
- `('cost', m.cost)`.
- `('refunds', m.refunds)`.

Kết quả đủ chín hàng:

| region | metric_name | metric_value |
| --- | --- | ---: |
| East | cost | `NULL` |
| East | refunds | `NULL` |
| East | revenue | 30 |
| North | cost | 180 |
| North | refunds | `NULL` |
| North | revenue | 240 |
| South | cost | 130 |
| South | refunds | 0 |
| South | revenue | 190 |

**LATERAL** cho phép biểu thức trong `VALUES` tham chiếu tới các cột của hàng `m` ở phía trước trong `FROM`.

### Có phải lúc nào cũng cần từ khóa LATERAL?

Trong PostgreSQL, một số dạng hàm và cấu trúc trong `FROM` có khả năng tham chiếu tương quan theo quy tắc riêng. Viết `CROSS JOIN LATERAL (VALUES ...)` là cách **tường minh và dễ đọc** để thể hiện ý định “với mỗi hàng m, tạo các cặp tên–giá trị”.

### Muốn bỏ các ô NULL

```sql
SELECT m.region, v.metric_name, v.metric_value
FROM metrics_wide_257 AS m
CROSS JOIN LATERAL (
    VALUES
        ('revenue'::TEXT, m.revenue),
        ('cost'::TEXT,    m.cost),
        ('refunds'::TEXT, m.refunds)
) AS v(metric_name, metric_value)
WHERE v.metric_value IS NOT NULL
ORDER BY m.region, v.metric_name;
```

Kết quả chỉ còn **5 hàng**:

- East: revenue 30.
- North: revenue 240, cost 180.
- South: revenue 190, cost 130, refunds 0.

Hàng `refunds = 0` của South **không bị loại** vì 0 khác `NULL`.

### UNPIVOT với cột khác kiểu

Trong ví dụ, ba cột đều `NUMERIC(12,2)`, nên `metric_value` có kiểu số thống nhất. Nếu một cột là `TEXT` và cột khác là `DATE`, `VALUES` phải tìm một kiểu chung hoặc báo lỗi.

Có thể ép tất cả thành `TEXT` nếu kết quả chỉ dùng hiển thị:

```sql
SELECT m.region,
       v.attribute_name,
       v.attribute_text
FROM metrics_wide_257 AS m
CROSS JOIN LATERAL (
    VALUES
        ('revenue', m.revenue::TEXT),
        ('cost',    m.cost::TEXT),
        ('refunds', m.refunds::TEXT)
) AS v(attribute_name, attribute_text);
```

Nhưng khi chuyển tiền thành `TEXT`, không nên dùng cột đó để cộng tiền nếu chưa chuyển lại và kiểm tra dữ liệu. Với ứng dụng phân tích cần kiểu số, giữ kiểu `NUMERIC` khi có thể.

## 18. UNPIVOT bằng UNION ALL: mẫu có tính di chuyển cao

Khi không có `UNPIVOT` gốc hoặc không muốn dùng `LATERAL`, có thể ghép từng cột thành một tập hàng rồi `UNION ALL`:

```sql
SELECT region,
       'revenue' AS metric_name,
       revenue AS metric_value
FROM metrics_wide_257

UNION ALL

SELECT region,
       'cost' AS metric_name,
       cost AS metric_value
FROM metrics_wide_257

UNION ALL

SELECT region,
       'refunds' AS metric_name,
       refunds AS metric_value
FROM metrics_wide_257

ORDER BY region, metric_name;
```

Kết quả tương tự ví dụ `LATERAL VALUES`: gồm **9 hàng**, kể cả các ô `NULL`.

### Vì sao dùng UNION ALL, không phải UNION?

`UNION ALL` giữ **mọi hàng được sinh** từ các cột. `UNION` còn thực hiện loại trùng trên **toàn bộ các cột đầu ra**.

Trong ví dụ tên chỉ tiêu khác nhau, hai hàng giá trị bằng nhau chưa chắc trùng vì `metric_name` khác. Nhưng nếu dữ liệu hoặc cách đặt tên làm hai hàng đầu ra giống hệt nhau, `UNION` có thể âm thầm loại một hàng. Thường **UNPIVOT không có nghĩa khử trùng**, nên `UNION ALL` mô tả ý định đúng hơn và tránh chi phí dedup không cần thiết.

### Muốn loại NULL khi dùng UNION ALL

Có thể dùng một CTE:

```sql
WITH long_metrics AS (
    SELECT region, 'revenue' AS metric_name, revenue AS metric_value
    FROM metrics_wide_257

    UNION ALL

    SELECT region, 'cost', cost
    FROM metrics_wide_257

    UNION ALL

    SELECT region, 'refunds', refunds
    FROM metrics_wide_257
)
SELECT region, metric_name, metric_value
FROM long_metrics
WHERE metric_value IS NOT NULL
ORDER BY region, metric_name;
```

Đặt bộ lọc ở ngoài khiến logic dễ đọc hơn và không cần lặp `WHERE <column> IS NOT NULL` trong từng nhánh.

### Chi phí đọc bảng nguồn

Với các DBMS, một truy vấn `UNION ALL` ba nhánh có thể phải đọc bảng nguồn nhiều lần tùy kế hoạch. Cách `CROSS JOIN LATERAL VALUES` hoặc cấu trúc row generator có thể diễn đạt việc đọc mỗi hàng rồi sinh nhiều hàng rõ hơn. Nhưng hiệu năng cụ thể phải được đo, không được khẳng định một mẫu luôn nhanh hơn mẫu kia.

## 19. SQL Server: cú pháp UNPIVOT gốc

SQL Server hỗ trợ `UNPIVOT`, ví dụ trên bảng tương đương:

```sql
-- SQL Server:
SELECT
    u.region,
    u.metric_name,
    u.metric_value
FROM (
    SELECT region, revenue, cost, refunds
    FROM metrics_wide_257
) AS src
UNPIVOT (
    metric_value
    FOR metric_name IN ([revenue], [cost], [refunds])
) AS u
ORDER BY u.region, u.metric_name;
```

Ý nghĩa:

- `metric_value` là cột giá trị sau khi chuyển.
- `metric_name` là cột chứa **tên cột nguồn**.
- `IN ([revenue], [cost], [refunds])` xác định các cột được chuyển thành hàng.
- `region` là cột được giữ lại, dùng làm khóa định danh đối tượng.

### SQL Server UNPIVOT mặc định loại NULL

Với dữ liệu mẫu, `UNPIVOT` của SQL Server sẽ bỏ các hàng từ ô có giá trị `NULL`. Vì vậy nó có thể chỉ trả **5 hàng**, không phải 9 như `UNION ALL` hoặc `LATERAL VALUES` ở PostgreSQL khi chưa lọc.

Điều này quan trọng nếu một ô `NULL` mang nghĩa “chưa có chỉ tiêu cần kiểm tra”, và báo cáo cần biết **tên của chỉ tiêu bị thiếu**.

### Giữ NULL trong SQL Server

Một cách dễ hiểu là dùng `CROSS APPLY (VALUES ...)`:

```sql
-- SQL Server: giữ cả các giá trị NULL
SELECT
    m.region,
    v.metric_name,
    v.metric_value
FROM metrics_wide_257 AS m
CROSS APPLY (
    VALUES
        ('revenue', m.revenue),
        ('cost',    m.cost),
        ('refunds', m.refunds)
) AS v(metric_name, metric_value)
ORDER BY m.region, v.metric_name;
```

Cách này giữ cả 9 cặp tên–giá trị, với các `NULL` được bảo toàn. Nếu muốn bỏ chúng, thêm `WHERE v.metric_value IS NOT NULL`.

**Đừng thay `UNPIVOT` bằng `CROSS APPLY` mà bỏ qua kiểu dữ liệu:** các giá trị trong `VALUES` cần có kiểu kết quả tương thích theo quy tắc SQL Server.

## 20. Oracle: UNPIVOT INCLUDE NULLS và EXCLUDE NULLS

Oracle có cú pháp UNPIVOT gốc và cho phép chỉ rõ việc giữ `NULL`.

### Giữ các ô NULL

```sql
-- Oracle Database
SELECT
    region,
    metric_name,
    metric_value
FROM metrics_wide_257
UNPIVOT INCLUDE NULLS (
    metric_value FOR metric_name IN (
        revenue AS 'revenue',
        cost    AS 'cost',
        refunds AS 'refunds'
    )
)
ORDER BY region, metric_name;
```

Với `INCLUDE NULLS`, kết quả có một hàng cho từng cột được liệt kê trên mỗi khu vực, kể cả khi giá trị bằng `NULL`.

### Loại các ô NULL

```sql
-- Oracle Database
SELECT
    region,
    metric_name,
    metric_value
FROM metrics_wide_257
UNPIVOT EXCLUDE NULLS (
    metric_value FOR metric_name IN (
        revenue AS 'revenue',
        cost    AS 'cost',
        refunds AS 'refunds'
    )
)
ORDER BY region, metric_name;
```

`EXCLUDE NULLS` là cách chỉ rõ quy tắc bỏ những ô thiếu. Trong Oracle, hành vi mặc định của UNPIVOT thông thường là bỏ `NULL` nếu không chọn `INCLUDE NULLS`.

Khác biệt này cho thấy hai hệ cùng hỗ trợ từ khóa `UNPIVOT` **không có nghĩa** người viết được bỏ qua chi tiết giữ/lọc `NULL`.

## 21. DuckDB: cú pháp UNPIVOT gọn

DuckDB hỗ trợ cú pháp tương tự:

```sql
-- DuckDB, không phải PostgreSQL:
UNPIVOT metrics_wide_257
ON revenue, cost, refunds
INTO
    NAME metric_name
    VALUE metric_value;
```

Kết quả có hai cột mới:

- `metric_name`: tên của các cột đã chuyển.
- `metric_value`: giá trị của từng cột.

`region` được giữ ở đầu ra như định danh nguồn.

Với nhu cầu phải bảo toàn mọi ô `NULL` hoặc kiểm soát kiểu dữ liệu chi tiết, cần xác nhận quy tắc `NULL` của phiên bản/cú pháp DuckDB cụ thể. Mẫu `UNION ALL` vẫn là phương án dễ nắm ngữ nghĩa khi cần kiểm soát chính xác từng hàng được sinh.

## 22. MySQL và SQLite: UNPIVOT bằng UNION ALL

MySQL và SQLite thường dùng `UNION ALL` để chuyển các cột cố định thành hàng:

```sql
-- MySQL hoặc SQLite: giả định bảng metrics_wide_257 cùng cấu trúc
SELECT region, 'revenue' AS metric_name, revenue AS metric_value
FROM metrics_wide_257

UNION ALL

SELECT region, 'cost', cost
FROM metrics_wide_257

UNION ALL

SELECT region, 'refunds', refunds
FROM metrics_wide_257

ORDER BY region, metric_name;
```

Nếu muốn loại những ô chưa có giá trị:

```sql
SELECT region, metric_name, metric_value
FROM (
    SELECT region, 'revenue' AS metric_name, revenue AS metric_value
    FROM metrics_wide_257
    UNION ALL
    SELECT region, 'cost', cost
    FROM metrics_wide_257
    UNION ALL
    SELECT region, 'refunds', refunds
    FROM metrics_wide_257
) AS u
WHERE metric_value IS NOT NULL
ORDER BY region, metric_name;
```

**Lưu ý:** trong thực tế, tên bảng và các kiểu dữ liệu sẽ do schema của từng DBMS quyết định. Câu SQL trên là mẫu biến đổi, không có nghĩa bảng tạm PostgreSQL được tạo ở mục 2 tự tồn tại trên MySQL hoặc SQLite.

## 23. PIVOT rồi UNPIVOT: khi nào phục hồi được, khi nào không?

Hãy quan sát quy trình:

```text
sales_long_257
    │
    │ GROUP BY region + month, SUM(amount)
    ▼
wide_monthly_sales
    │
    │ chuyển jan/feb/mar thành các hàng
    ▼
region | month | monthly_total
```

Kết quả cuối có **một hàng cho mỗi cặp region–month được giữ**, nhưng **không phải các giao dịch riêng lẻ**.

Ví dụ North–January:

```text
Giao dịch gốc:
  sale 1: 100
  sale 2:  40

Sau PIVOT:
  jan_total = 140

Sau UNPIVOT:
  region = North, month = 2026-01, monthly_total = 140
```

Không còn đủ thông tin để khôi phục `sale_id = 1,2` hoặc hai số tiền 100 và 40.

### Một truy vấn làm cả hai bước trong PostgreSQL

```sql
WITH wide AS (
    SELECT
        region,
        SUM(amount) FILTER (
            WHERE month_start = DATE '2026-01-01'
        ) AS jan_total,
        SUM(amount) FILTER (
            WHERE month_start = DATE '2026-02-01'
        ) AS feb_total,
        SUM(amount) FILTER (
            WHERE month_start = DATE '2026-03-01'
        ) AS mar_total
    FROM sales_long_257
    GROUP BY region
)
SELECT
    w.region,
    u.month_key,
    u.monthly_total
FROM wide AS w
CROSS JOIN LATERAL (
    VALUES
        ('2026-01'::TEXT, w.jan_total),
        ('2026-02'::TEXT, w.feb_total),
        ('2026-03'::TEXT, w.mar_total)
) AS u(month_key, monthly_total)
ORDER BY w.region, u.month_key;
```

Vì nguồn `wide` có ba khu vực và `VALUES` có ba tháng, kết quả có **9 hàng**, nếu không lọc `NULL`.

- East–February trở thành một hàng có `monthly_total = NULL` dù không hề có giao dịch February.
- East–March cũng có `monthly_total = NULL` dù có một giao dịch với giá trị thiếu.
- South–March trở thành một hàng có `monthly_total = 0`.

**UNPIVOT không biết nguồn gốc của một ô NULL nếu PIVOT đã gộp các tình huống khác nhau về cùng NULL.**

### Khi nào có thể coi là “đảo ngược”?

Nếu mỗi cặp `(row_key, pivot_key)` có **đúng một giá trị**, các giá trị cần giữ không bị loại bởi chính sách `NULL`, tập category không bị cắt bớt, kiểu dữ liệu không bị mất và không có tổng hợp làm mất chi tiết, thao tác pivot→unpivot có thể phục hồi **các cặp khóa–giá trị** về mặt thông tin (bỏ qua thứ tự hàng, vì bảng quan hệ không có thứ tự mặc định).

Nhưng với các bảng giao dịch có nhiều hàng cùng category, cần coi PIVOT là **một phép biến đổi kèm tổng hợp**, không phải chỉ là phép xoay hình dạng có tính đảo ngược hoàn toàn.

## 24. Xử lý category không xuất hiện và hàng không có dữ liệu

Một truy vấn PIVOT dựa vào bảng giao dịch chỉ trả **những row key hiện có trong nguồn**. Nếu khu vực `West` chưa có giao dịch nào, nó không xuất hiện sau:

```sql
FROM sales_long_257
GROUP BY region
```

dù bạn liệt kê đủ các cột tháng.

Nếu yêu cầu báo cáo bắt buộc có cả West, cần một **bảng danh mục khu vực** (dimension) hoặc nguồn danh sách khu vực độc lập.

Ví dụ PostgreSQL:

```sql
WITH regions(region) AS (
    VALUES
        ('North'::TEXT),
        ('South'::TEXT),
        ('East'::TEXT),
        ('West'::TEXT)
),
monthly_totals AS (
    SELECT
        region,
        month_start,
        SUM(amount) AS month_total
    FROM sales_long_257
    GROUP BY region, month_start
)
SELECT
    r.region,
    SUM(m.month_total) FILTER (
        WHERE m.month_start = DATE '2026-01-01'
    ) AS jan_total,
    SUM(m.month_total) FILTER (
        WHERE m.month_start = DATE '2026-02-01'
    ) AS feb_total,
    SUM(m.month_total) FILTER (
        WHERE m.month_start = DATE '2026-03-01'
    ) AS mar_total
FROM regions AS r
LEFT JOIN monthly_totals AS m
  ON m.region = r.region
GROUP BY r.region
ORDER BY r.region;
```

Kết quả có cả `West` với mọi tổng tháng là `NULL`, vì không có giao dịch. Nếu chính sách báo cáo quy định “vùng không có hoạt động được hiển thị bằng 0”, có thể dùng `COALESCE` **sau tổng hợp** và giữ cột đếm để nhận diện không có giao dịch.

### Đừng đặt bộ lọc của bảng phải vào WHERE nếu cần giữ mọi region

Câu sau làm mất West:

```sql
-- Minh họa sai mục đích giữ toàn bộ khu vực:
...
FROM regions AS r
LEFT JOIN monthly_totals AS m
  ON m.region = r.region
WHERE m.month_start >= DATE '2026-01-01'
...
```

Khi không có hàng `m` khớp, `m.month_start` là `NULL`; điều kiện trong `WHERE` trở thành UNKNOWN và loại hàng West. Cần đưa điều kiện thời gian vào `ON` hoặc lọc `monthly_totals` trước khi nối theo đúng mục tiêu.

## 25. Tại sao không thể tự sinh cột chỉ bằng CASE khi category động?

Một biểu thức:

```sql
CASE WHEN month_start = DATE '2026-01-01'
     THEN amount
END
```

chỉ tạo ra **giá trị cho một cột cố định** trong kết quả. Nó không tự thay đổi tên cột theo dữ liệu.

Để PIVOT từ danh sách tháng động thành nhiều cột vật lý, có ba vấn đề:

1. **Tập tên cột phải xác định:** ví dụ January, February, March.
2. **Kiểu mỗi cột phải biết:** ví dụ `NUMERIC`.
3. **Metadata của kết quả phải ổn định trong một lần chạy:** ứng dụng cần biết các trường sẽ đọc.

Dynamic SQL giải quyết bằng cách **tạo một câu SQL mới** từ danh sách category trước khi thực thi. Dữ liệu JSON/map giải quyết bằng cách giữ **một cột có cấu trúc động**, thay vì thay đổi các cột của bảng kết quả.

### Lựa chọn API

Nếu API trả:

```json
{
  "region": "North",
  "janTotal": 140,
  "febTotal": 80,
  "marTotal": 60
}
```

thì schema tĩnh phù hợp khi báo cáo chỉ cố định ba tháng.

Nếu người dùng chọn bất kỳ khoảng nhiều tháng:

```json
{
  "region": "North",
  "monthlyTotals": {
    "2026-01": 140,
    "2026-02": 80,
    "2026-03": 60
  }
}
```

thì map trong JSON hoặc danh sách các cặp `(month, total)` có thể linh hoạt hơn việc sinh ra hàng chục cột SQL có tên thay đổi.

**Không phải lúc nào PIVOT ở tầng database cũng là lựa chọn tốt nhất.** Với một công cụ BI tự hỗ trợ crosstab, trả dữ liệu dài từ SQL đôi khi đơn giản và an toàn hơn.

## 26. Tên cột, định danh và xung đột tên

Category có thể là:

- `'2026-01'`: chứa dấu gạch nối, thường cần quote nếu dùng nguyên làm tên cột.
- `'Premium Customer'`: chứa dấu cách.
- `'A/B'`: có ký tự đặc biệt.
- `'Revenue'` và `'revenue'`: có thể trở thành tên trùng tùy quy tắc nhận diện chữ hoa/thường của DBMS.

Vì vậy nên **ánh xạ category vào alias an toàn**:

```text
category value     column alias
--------------     ------------
2026-01            jan_total
2026-02            feb_total
2026-03            mar_total
```

Trong SQL Server, `[2026-01]` là định danh có dấu gạch nối được quote. Trong PostgreSQL, có thể dùng dấu nháy kép `"2026-01"` nếu thật sự cần tên đó, nhưng tên `jan_total` thường thân thiện hơn.

Trong SQL:

- Dấu nháy đơn như `'2026-01'` biểu diễn **giá trị chuỗi**.
- Dấu quote định danh phụ thuộc phương ngữ.
- Alias nên không trùng nhau sau mọi bước chuẩn hóa để không tạo cột không rõ danh tính.

Đặt tên có mục đích và giữ hợp đồng rõ ràng sẽ giúp truy vấn dễ sử dụng hơn trong Java, DTO, BI và CSV.

## 27. Chọn nơi pivot: tại SQL hay tầng ứng dụng?

| Tiêu chí | Pivot trong SQL | Pivot ở ứng dụng/BI |
| --- | --- | --- |
| Cần tính tổng trên tập dữ liệu lớn | Có thể giảm số hàng truyền ra khỏi database | Có thể phải truyền nhiều hàng dài hơn |
| Số category cố định | Rất phù hợp | Cũng có thể làm nhưng đôi khi dư công |
| Số category thay đổi liên tục | Thường cần dynamic SQL hoặc JSON | Thường linh hoạt hơn |
| Cần schema API cố định | Phù hợp với cột được thiết kế sẵn | Phải định nghĩa hợp đồng đầu ra riêng |
| Cần tùy biến hiển thị nhiều cách | Có thể trở nên nhiều cột, khó bảo trì | BI/frontend thuận tiện hơn |
| Cần kiểm tra từng giao dịch gốc | PIVOT tổng hợp có thể làm mất chi tiết | Dạng dài giữ thông tin tốt hơn |
| Cần tối ưu mạng và khối lượng kết quả | Có thể lợi khi pivot giảm hàng đáng kể | Phụ thuộc số lượng bản ghi và định dạng |
| Nhiều phương ngữ DBMS | Conditional aggregation tương đối dễ chuyển | Logic pivot ở một tầng có thể thống nhất cách xử lý |

Một hệ thống thực tế có thể kết hợp: SQL **lọc và tổng hợp** ở cấp `(region,month)`; ứng dụng pivot các tháng thành cột hiển thị. Phương án đó vừa giảm số hàng giao dịch vừa không cần SQL động.

## 28. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| North–January chỉ có 100 thay vì 140 | Dùng `MAX` thay vì `SUM` dù có hai giao dịch | Chọn đúng phép tổng hợp |
| Tổng tăng gấp đôi sau khi PIVOT | `JOIN` trước đó làm nhân bản hàng nguồn | Kiểm tra grain và số hàng sau JOIN |
| PIVOT trên SQL Server trả nhiều hàng cho một region | Đưa thừa `sale_id` hoặc `channel` vào nguồn `PIVOT` | Chỉ chọn đúng row key, pivot key, measure |
| East–February là NULL | Không có giao dịch tháng 2 | Dùng cột đếm nếu phải phân biệt thiếu giao dịch |
| East–March là NULL | Có một giao dịch nhưng amount thiếu | `COUNT(*)` và `COUNT(amount)` giúp nhận diện |
| South–March bằng 0 | Có số 0 thật và một giá trị NULL | Không đánh đồng với tình trạng thiếu hoàn toàn |
| COALESCE làm mọi ô NULL thành 0 | Chính sách thay thế kết quả che ý nghĩa dữ liệu | Giữ thêm trạng thái/đếm hoặc chỉ COALESCE khi được phép |
| Thiếu vùng West khỏi báo cáo | GROUP BY chỉ tạo các vùng có trong bảng giao dịch | Bắt đầu từ bảng dimension và LEFT JOIN |
| Vùng West biến mất sau LEFT JOIN | Lọc cột bên phải trong WHERE | Đặt bộ lọc ở ON hoặc nguồn trước join |
| SQL Server/Oracle UNPIVOT thiếu các ô NULL | Toán tử mặc định loại NULL | Dùng Oracle `INCLUDE NULLS` hoặc mẫu `VALUES/UNION ALL` khi cần giữ |
| UNPIVOT trả quá nhiều hàng | Mỗi cột được chọn sinh một hàng cho từng row key | Chọn đúng danh sách cột và lọc cần thiết |
| UNION thay UNION ALL làm mất bản ghi | UNION loại các hàng đầu ra trùng | Dùng UNION ALL cho thao tác chuyển cột thành hàng |
| Không thể dùng một cột value cho số, ngày và chữ | Kiểu dữ liệu không tương thích | CAST có chủ đích hoặc tách theo nhóm kiểu |
| Cột mới không xuất hiện khi có category mới | PIVOT tĩnh chỉ liệt kê category được khai báo | Cập nhật SQL, dùng dynamic SQL/JSON hoặc BI |
| Dynamic PIVOT gặp lỗi/tấn công chèn SQL | Ghép tên cột từ input không kiểm soát | Allowlist, quote identifier theo DBMS và dùng parameter cho value |
| PIVOT→UNPIVOT không khôi phục sale_id | Tổng hợp đã gộp nhiều giao dịch | Giữ dữ liệu chi tiết ở nguồn nếu cần truy vết |
| Tổng theo tháng bị sai do timestamp | So bằng ngày đầu tháng thay vì lấy cả khoảng tháng | Chuẩn hóa kỳ hoặc lọc khoảng nửa mở |
| Câu PIVOT chạy ở Oracle nhưng lỗi ở PostgreSQL | Cú pháp phương ngữ không tương thích | Dùng FILTER/CASE của PostgreSQL hoặc adapter theo DBMS |

## 29. Bài tập tự luyện

Dùng hai bảng PostgreSQL đã tạo ở mục 2. Với mỗi bài, hãy xác định **khóa hàng**, **category**, **measure**, **phép tổng hợp** và **quy tắc NULL** trước khi viết SQL.

### Bài 1. PIVOT doanh số theo tháng bằng CASE

Trả một hàng cho mỗi `region`, các cột `jan_total`, `feb_total`, `mar_total`. Dùng `SUM(CASE WHEN ... THEN amount END)`.

Dự đoán kết quả của East.

### Bài 2. Viết lại bằng FILTER

Viết câu ở bài 1 bằng `SUM(amount) FILTER (WHERE ...)`. So sánh kết quả.

### Bài 3. Đếm giao dịch theo tháng

Tạo các cột `jan_rows`, `feb_rows`, `mar_rows` bằng `COUNT(*) FILTER`. Khu vực East–March có bao nhiêu giao dịch?

### Bài 4. Phân biệt NULL và 0

Với March của mỗi khu vực, trả:

- Tổng tiền đã biết.
- Số giao dịch.
- Số giao dịch có `amount IS NOT NULL`.

Giải thích sự khác biệt giữa East và South.

### Bài 5. Pivot theo kênh Online/Store

Trả `online_total` và `store_total` theo mỗi `region`. Tổng Online của North là bao nhiêu? Nếu Store của East chỉ có giá trị NULL, cột Store trả gì?

### Bài 6. Phép tổng hợp MAX có phù hợp không?

Thay `SUM` bằng `MAX` cho January. North sẽ nhận giá trị nào? Trong tình huống nghiệp vụ nào `MAX` là phép tổng hợp đúng?

### Bài 7. UNPIVOT giữ mọi ô NULL

Dùng `CROSS JOIN LATERAL (VALUES ...)` đưa `revenue`, `cost`, `refunds` thành các cặp `metric_name`/`metric_value`. Truy vấn có bao nhiêu hàng?

### Bài 8. UNPIVOT bỏ ô NULL

Viết lại bài 7 nhưng chỉ giữ `metric_value IS NOT NULL`. Có bao nhiêu hàng? `refunds = 0` của South có được giữ không?

### Bài 9. UNPIVOT bằng UNION ALL

Viết ba nhánh `SELECT` ghép bằng `UNION ALL` để có cùng 9 hàng như bài 7. Vì sao không dùng `UNION` nếu mục tiêu là giữ mọi cặp tên–giá trị?

### Bài 10. PIVOT rồi UNPIVOT

Dùng CTE tạo ba cột tổng theo tháng bằng `FILTER`, sau đó dùng `LATERAL VALUES` chuyển trở lại ba hàng cho mỗi vùng.

Câu hỏi: có thể khôi phục sale 1 và sale 2 của North–January bằng phép chuyển ngược này không?

### Bài 11. Thêm khu vực không có giao dịch

Tạo nguồn `VALUES ('North'), ('South'), ('East'), ('West')` và `LEFT JOIN` với số liệu tổng theo tháng. Bảo đảm West xuất hiện trong kết quả.

### Bài 12. JSON cho danh sách tháng động

Trả một JSONB object cho mỗi `region` có key `YYYY-MM` và value là tổng tiền tháng tương ứng. Với East, February và March biểu hiện khác nhau thế nào?

### Bài 13. Giải thích PIVOT SQL Server

Cho nguồn `src` gồm `region`, `month_key`, `amount`. Viết SQL Server `PIVOT SUM(amount) FOR month_key IN ([2026-01],[2026-02],[2026-03])`. Điều gì xảy ra nếu thêm `sale_id` vào nguồn?

### Bài 14. Giữ NULL khi UNPIVOT Oracle

Viết mẫu `UNPIVOT INCLUDE NULLS` cho `revenue`, `cost`, `refunds`. Nếu bỏ `INCLUDE NULLS` và hệ dùng mặc định loại NULL, số hàng dự kiến thay đổi thế nào?

### Bài 15. Chọn kiến trúc

Một dashboard cho người dùng chọn bất kỳ 1–36 tháng, mỗi tháng được hiển thị như một cột. Hãy so sánh ba giải pháp:

- Dynamic PIVOT bằng SQL.
- Trả JSON map tháng→tổng.
- Trả dữ liệu dài đã tổng hợp theo tháng và pivot trên frontend.

Nêu cách quản lý metadata, giới hạn số cột, xử lý NULL và an toàn.

## 30. Gợi ý lời giải

### Bài 1

```sql
SELECT region,
       SUM(CASE
           WHEN month_start = DATE '2026-01-01' THEN amount
       END) AS jan_total,
       SUM(CASE
           WHEN month_start = DATE '2026-02-01' THEN amount
       END) AS feb_total,
       SUM(CASE
           WHEN month_start = DATE '2026-03-01' THEN amount
       END) AS mar_total
FROM sales_long_257
GROUP BY region
ORDER BY region;
```

East có `jan_total = 30`, `feb_total = NULL`, `mar_total = NULL`.

### Bài 2

```sql
SELECT region,
       SUM(amount) FILTER (
           WHERE month_start = DATE '2026-01-01'
       ) AS jan_total,
       SUM(amount) FILTER (
           WHERE month_start = DATE '2026-02-01'
       ) AS feb_total,
       SUM(amount) FILTER (
           WHERE month_start = DATE '2026-03-01'
       ) AS mar_total
FROM sales_long_257
GROUP BY region
ORDER BY region;
```

Với bộ dữ liệu này, kết quả tương đương bài 1.

### Bài 3

```sql
SELECT region,
       COUNT(*) FILTER (
           WHERE month_start = DATE '2026-01-01'
       ) AS jan_rows,
       COUNT(*) FILTER (
           WHERE month_start = DATE '2026-02-01'
       ) AS feb_rows,
       COUNT(*) FILTER (
           WHERE month_start = DATE '2026-03-01'
       ) AS mar_rows
FROM sales_long_257
GROUP BY region
ORDER BY region;
```

East–March có **1** giao dịch.

### Bài 4

```sql
SELECT region,
       SUM(amount) FILTER (
           WHERE month_start = DATE '2026-03-01'
       ) AS mar_total,
       COUNT(*) FILTER (
           WHERE month_start = DATE '2026-03-01'
       ) AS mar_rows,
       COUNT(amount) FILTER (
           WHERE month_start = DATE '2026-03-01'
       ) AS mar_known_values
FROM sales_long_257
GROUP BY region
ORDER BY region;
```

East là `(NULL, 1, 0)`; South là `(0, 2, 1)`. South có số 0 đã biết còn East thiếu mọi số tiền.

### Bài 5

```sql
SELECT region,
       SUM(amount) FILTER (
           WHERE channel = 'Online'
       ) AS online_total,
       SUM(amount) FILTER (
           WHERE channel = 'Store'
       ) AS store_total
FROM sales_long_257
GROUP BY region
ORDER BY region;
```

North Online = **180**. East Store = `NULL` vì chỉ có một giá trị `NULL`.

### Bài 6

```sql
SELECT region,
       MAX(amount) FILTER (
           WHERE month_start = DATE '2026-01-01'
       ) AS jan_largest_sale
FROM sales_long_257
GROUP BY region
ORDER BY region;
```

North nhận **100**, là giao dịch lớn nhất trong January, không phải tổng doanh thu 140.

### Bài 7

```sql
SELECT m.region, v.metric_name, v.metric_value
FROM metrics_wide_257 AS m
CROSS JOIN LATERAL (
    VALUES
        ('revenue'::TEXT, m.revenue),
        ('cost'::TEXT, m.cost),
        ('refunds'::TEXT, m.refunds)
) AS v(metric_name, metric_value)
ORDER BY m.region, v.metric_name;
```

Ba khu vực × ba cột chỉ tiêu = **9 hàng**, kể cả `NULL`.

### Bài 8

```sql
SELECT m.region, v.metric_name, v.metric_value
FROM metrics_wide_257 AS m
CROSS JOIN LATERAL (
    VALUES
        ('revenue'::TEXT, m.revenue),
        ('cost'::TEXT, m.cost),
        ('refunds'::TEXT, m.refunds)
) AS v(metric_name, metric_value)
WHERE v.metric_value IS NOT NULL
ORDER BY m.region, v.metric_name;
```

Kết quả **5 hàng**. South–refunds = 0 được giữ vì không phải `NULL`.

### Bài 9

```sql
SELECT region, 'revenue' AS metric_name, revenue AS metric_value
FROM metrics_wide_257
UNION ALL
SELECT region, 'cost', cost
FROM metrics_wide_257
UNION ALL
SELECT region, 'refunds', refunds
FROM metrics_wide_257
ORDER BY region, metric_name;
```

`UNION ALL` không khử trùng các hàng được sinh; nó phù hợp với yêu cầu giữ từng cặp cột–giá trị của nguồn.

### Bài 10

```sql
WITH wide AS (
    SELECT region,
           SUM(amount) FILTER (
               WHERE month_start = DATE '2026-01-01'
           ) AS jan_total,
           SUM(amount) FILTER (
               WHERE month_start = DATE '2026-02-01'
           ) AS feb_total,
           SUM(amount) FILTER (
               WHERE month_start = DATE '2026-03-01'
           ) AS mar_total
    FROM sales_long_257
    GROUP BY region
)
SELECT w.region, v.month_key, v.total_amount
FROM wide AS w
CROSS JOIN LATERAL (
    VALUES
        ('2026-01'::TEXT, w.jan_total),
        ('2026-02'::TEXT, w.feb_total),
        ('2026-03'::TEXT, w.mar_total)
) AS v(month_key, total_amount)
ORDER BY w.region, v.month_key;
```

Không thể khôi phục từng giao dịch `sale_id = 1, 2` và số tiền 100, 40 từ tổng 140.

### Bài 11

```sql
WITH regions(region) AS (
    VALUES ('North'::TEXT), ('South'), ('East'), ('West')
),
monthly_totals AS (
    SELECT region, month_start,
           SUM(amount) AS monthly_amount
    FROM sales_long_257
    GROUP BY region, month_start
)
SELECT r.region,
       SUM(m.monthly_amount) FILTER (
           WHERE m.month_start = DATE '2026-01-01'
       ) AS jan_total,
       SUM(m.monthly_amount) FILTER (
           WHERE m.month_start = DATE '2026-02-01'
       ) AS feb_total,
       SUM(m.monthly_amount) FILTER (
           WHERE m.month_start = DATE '2026-03-01'
       ) AS mar_total
FROM regions AS r
LEFT JOIN monthly_totals AS m
  ON m.region = r.region
GROUP BY r.region
ORDER BY r.region;
```

West hiện diện với ba cột tổng `NULL`. Nếu muốn hiển thị 0 phải có chính sách `COALESCE`.

### Bài 12

```sql
WITH monthly_totals AS (
    SELECT region,
           TO_CHAR(month_start, 'YYYY-MM') AS month_key,
           SUM(amount) AS month_total
    FROM sales_long_257
    GROUP BY region, TO_CHAR(month_start, 'YYYY-MM')
)
SELECT region,
       JSONB_OBJECT_AGG(month_key, month_total) AS monthly_values
FROM monthly_totals
GROUP BY region
ORDER BY region;
```

East không có key `2026-02`, nhưng có key `2026-03` với giá trị JSON `null`.

### Bài 13

```sql
-- SQL Server
SELECT region,
       [2026-01], [2026-02], [2026-03]
FROM (
    SELECT region,
           CONVERT(CHAR(7), month_start, 120) AS month_key,
           amount
    FROM sales_long_257
) AS src
PIVOT (
    SUM(amount)
    FOR month_key IN ([2026-01], [2026-02], [2026-03])
) AS p;
```

Nếu thêm `sale_id` vào nguồn, SQL Server PIVOT có thể nhóm theo sale_id, làm một khu vực xuất hiện nhiều hàng. Phải chọn đúng khóa hàng đầu ra.

### Bài 14

```sql
-- Oracle
SELECT region, metric_name, metric_value
FROM metrics_wide_257
UNPIVOT INCLUDE NULLS (
    metric_value FOR metric_name IN (
        revenue AS 'revenue',
        cost AS 'cost',
        refunds AS 'refunds'
    )
);
```

`INCLUDE NULLS` giữ **9 hàng**. Với `EXCLUDE NULLS` hoặc mặc định loại NULL, ví dụ còn **5 hàng**.

### Bài 15

Một câu trả lời hợp lý có thể là:

- **Dynamic PIVOT SQL:** phù hợp khi cần bảng cột thực sự và số category có giới hạn. Phải sinh/quote tên cột an toàn, kiểm soát kiểu, số cột tối đa và metadata biến động.
- **JSON map:** schema SQL/API có thể cố định, category linh hoạt. Cần định nghĩa ý nghĩa key thiếu và key chứa `null`, và chuẩn hóa cách sắp xếp ở ứng dụng.
- **Dữ liệu dài đã tổng hợp:** SQL trả `region, month_key, monthly_total`; frontend/BI dựng cột theo thời gian. Cách này dễ hỗ trợ 1–36 tháng, phù hợp nhiều DBMS, và giữ rõ cấu trúc dữ liệu.

Lựa chọn phụ thuộc độ lớn dữ liệu, yêu cầu xuất CSV/Excel, cấu trúc API và công cụ trình bày đang sử dụng.

## 31. Quy trình chọn PIVOT/UNPIVOT trong một bài toán thật

Một quy trình thiết kế tránh lỗi:

1. **Xác định đơn vị hàng gốc:** một giao dịch, một đơn hàng, một khách hàng, hay một tổng theo tháng?
2. **Xác định khóa hàng đầu ra:** chẳng hạn `(tenant_id, region)`, không nhất thiết chỉ là một cột.
3. **Chọn category trở thành cột:** tháng, trạng thái, kênh bán hay chỉ tiêu.
4. **Chọn measure và hàm tổng hợp:** `SUM` cho tổng tiền, `COUNT` cho số dòng, `MAX` cho giá trị lớn nhất; không thay tùy tiện.
5. **Kiểm tra trùng (row key, category):** nếu có nhiều hàng, phải xác định cách tổng hợp hoặc lựa chọn bản ghi.
6. **Định nghĩa ý nghĩa NULL và zero:** thiếu giao dịch, có giao dịch thiếu tiền, hoặc tổng bằng 0.
7. **Liệt kê danh sách category cần hiển thị:** cố định, động, hay lấy từ dimension.
8. **Chọn phương ngữ:** PostgreSQL `FILTER/CASE`, SQL Server/Oracle PIVOT, DuckDB PIVOT hoặc lớp BI.
9. **Khi UNPIVOT, quyết định giữ NULL hay loại NULL:** khác nhau đáng kể giữa toán tử gốc và cách làm thủ công.
10. **Xác định kiểu chung của cột giá trị sau UNPIVOT:** tránh trộn số, ngày và văn bản nếu nghiệp vụ cần tính toán.
11. **Nếu cần dữ liệu chi tiết về sau, không chỉ lưu kết quả đã PIVOT:** phép tổng hợp có thể mất thông tin.
12. **Sau khi truy vấn đúng, mới đo hiệu năng:** kiểm tra kế hoạch truy vấn, chỉ mục, số category và kích thước kết quả.

**Kết luận:** PIVOT và UNPIVOT là **mẫu biến đổi hình dạng dữ liệu**, nhưng PIVOT thường còn bao gồm **tổng hợp theo một grain**, còn UNPIVOT đặt ra quyết định **giữ hay loại các ô NULL**. Cú pháp giữa PostgreSQL, SQL Server, Oracle, MySQL, SQLite và DuckDB khác nhau, nhưng cách nghĩ cốt lõi giống nhau: xác định **khóa hàng, category, giá trị, phép tổng hợp, chính sách NULL và hợp đồng đầu ra** trước khi chọn câu SQL.
