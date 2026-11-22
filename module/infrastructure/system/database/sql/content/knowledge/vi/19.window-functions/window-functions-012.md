# Lọc kết quả hàm cửa sổ bằng truy vấn ngoài hoặc QUALIFY

## 1. Bài toán: đã tính thứ hạng, làm sao chỉ giữ những hàng cần thiết?

Giả sử bảng doanh số có nhiều nhân viên ở nhiều đội. Ta muốn lấy **hai nhân viên doanh số cao nhất trong từng đội**. Hàm cửa sổ `ROW_NUMBER()` có thể đánh số hàng theo doanh số giảm dần trong từng đội:

~~~sql
SELECT
    team_code,
    rep_id,
    rep_name,
    sales_amount,
    ROW_NUMBER() OVER (
        PARTITION BY team_code
        ORDER BY sales_amount DESC, rep_id
    ) AS rn
FROM sales_reps;
~~~

Tuy nhiên, khi muốn **chỉ lấy những hàng có `rn <= 2`**, nhiều người thử:

~~~sql
-- SAI trong PostgreSQL, SQL Server, MySQL và SQL thông dụng:
SELECT
    team_code,
    rep_id,
    sales_amount,
    ROW_NUMBER() OVER (
        PARTITION BY team_code
        ORDER BY sales_amount DESC, rep_id
    ) AS rn
FROM sales_reps
WHERE rn <= 2;
~~~

Câu lệnh có vấn đề vì **`WHERE` không nhìn thấy kết quả của hàm cửa sổ được tính ở cùng cấp truy vấn**. Thậm chí nếu thay alias `rn` bằng cả lời gọi `ROW_NUMBER() OVER (...)` trong `WHERE`, các DBMS phổ biến cũng không cho dùng hàm cửa sổ ở vị trí đó.

Có hai cách giải quyết chính:

1. **Truy vấn ngoài (outer query)**: tính hàm cửa sổ trong **CTE hoặc derived table**, sau đó lọc cột kết quả trong `WHERE` của truy vấn bên ngoài. Đây là cách rất phổ biến và có tính khả chuyển cao.
2. **`QUALIFY`**: ở DBMS có hỗ trợ, viết điều kiện lọc **sau giai đoạn tính window function** ngay trong cùng câu `SELECT`, tương tự vai trò lọc của `HAVING` đối với kết quả nhóm, nhưng dành cho kết quả cửa sổ.

### Hai mẫu cần ghi nhớ

**Mẫu A — CTE + WHERE bên ngoài:**

~~~sql
WITH ranked AS (
    SELECT
        team_code,
        rep_id,
        sales_amount,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC, rep_id
        ) AS rn
    FROM sales_reps
)
SELECT team_code, rep_id, sales_amount
FROM ranked
WHERE rn <= 2;
~~~

**Mẫu B — QUALIFY trong DBMS hỗ trợ:**

~~~sql
SELECT
    team_code,
    rep_id,
    sales_amount
FROM sales_reps
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY team_code
    ORDER BY sales_amount DESC, rep_id
) <= 2;
~~~

Hai mẫu hướng tới cùng ý nghĩa: **xếp hạng đầy đủ trong mỗi đội trước, rồi chỉ hiển thị hai hàng đứng đầu mỗi đội**. Nhưng đừng tự giả định mọi hệ SQL có từ khóa `QUALIFY`, hoặc `QUALIFY` và truy vấn ngoài luôn có cùng kế hoạch thực thi.

Bài học sẽ dùng dữ liệu cụ thể để tìm hiểu thứ tự xử lý logic, hai cách viết, tình huống đồng hạng, lọc trước/sau window, hàng mới nhất mỗi nhóm, tổng lũy kế, sự khác biệt giữa các DBMS và những bẫy dễ gặp.

## 2. Dữ liệu mẫu thứ nhất: doanh số theo đội

### 2.1. Tạo bảng

~~~sql
CREATE TABLE sales_reps (
    rep_id       INTEGER PRIMARY KEY,
    rep_name     VARCHAR(60) NOT NULL,
    team_code    VARCHAR(20) NOT NULL,
    sales_amount DECIMAL(12, 2) NOT NULL,
    rep_status   VARCHAR(20) NOT NULL,
    CONSTRAINT chk_sales_amount
        CHECK (sales_amount >= 0)
);
~~~

Thêm 10 nhân viên:

~~~sql
INSERT INTO sales_reps (
    rep_id, rep_name, team_code, sales_amount, rep_status
)
VALUES
    (101, 'An',    'North',   1200.00, 'ACTIVE'),
    (102, 'Binh',  'North',   1100.00, 'INACTIVE'),
    (103, 'Chi',   'North',   1100.00, 'ACTIVE'),
    (104, 'Dung',  'North',    900.00, 'ACTIVE'),
    (201, 'Ha',    'South',   1500.00, 'ACTIVE'),
    (202, 'Lan',   'South',   1200.00, 'ACTIVE'),
    (203, 'Minh',  'South',   1200.00, 'ACTIVE'),
    (204, 'Nam',   'South',    800.00, 'INACTIVE'),
    (301, 'Hoa',   'Central', 1000.00, 'ACTIVE'),
    (302, 'Linh',  'Central',  700.00, 'ACTIVE');
~~~

Dữ liệu theo doanh số giảm dần:

| Đội | Mã nhân viên | Tên | Doanh số | Trạng thái |
| --- | ---: | --- | ---: | --- |
| North | 101 | An | 1200 | ACTIVE |
| North | 102 | Binh | 1100 | INACTIVE |
| North | 103 | Chi | 1100 | ACTIVE |
| North | 104 | Dung | 900 | ACTIVE |
| South | 201 | Ha | 1500 | ACTIVE |
| South | 202 | Lan | 1200 | ACTIVE |
| South | 203 | Minh | 1200 | ACTIVE |
| South | 204 | Nam | 800 | INACTIVE |
| Central | 301 | Hoa | 1000 | ACTIVE |
| Central | 302 | Linh | 700 | ACTIVE |

Bảng có chủ đích chứa **đồng doanh số**:

- Binh và Chi cùng `1100` trong North.
- Lan và Minh cùng `1200` trong South.
- Hai nhân viên `INACTIVE` giúp thấy sự khác nhau giữa **lọc trước** và **lọc sau** khi xếp hạng.

### 2.2. Xếp hạng trước khi lọc

~~~sql
SELECT
    team_code,
    rep_id,
    rep_name,
    sales_amount,
    ROW_NUMBER() OVER (
        PARTITION BY team_code
        ORDER BY sales_amount DESC, rep_id ASC
    ) AS rn
FROM sales_reps
ORDER BY team_code, rn;
~~~

Kết quả:

| Đội | rep_id | Tên | Doanh số | rn |
| --- | ---: | --- | ---: | ---: |
| Central | 301 | Hoa | 1000 | 1 |
| Central | 302 | Linh | 700 | 2 |
| North | 101 | An | 1200 | 1 |
| North | 102 | Binh | 1100 | 2 |
| North | 103 | Chi | 1100 | 3 |
| North | 104 | Dung | 900 | 4 |
| South | 201 | Ha | 1500 | 1 |
| South | 202 | Lan | 1200 | 2 |
| South | 203 | Minh | 1200 | 3 |
| South | 204 | Nam | 800 | 4 |

`PARTITION BY team_code` yêu cầu **đánh số lại từ 1 cho mỗi đội**. `ORDER BY sales_amount DESC` xếp doanh số cao trước. `rep_id ASC` phá hòa giữa những người cùng doanh số, để kết quả `ROW_NUMBER` ổn định trên dữ liệu không đổi.

Điều này khác với `RANK`: `ROW_NUMBER()` luôn gán một số nguyên khác nhau cho từng hàng, còn `RANK()` có thể gán **cùng hạng** cho những người bằng nhau theo toàn bộ khóa sắp xếp.

## 3. Vì sao không lọc window function trực tiếp trong WHERE?

### 3.1. Trình tự xử lý logic của một truy vấn

Để hiểu vị trí của hàm cửa sổ, có thể dùng thứ tự **logic khái quát** sau:

~~~text
FROM / JOIN / ON
        |
        v
      WHERE               -- Lọc hàng nguồn
        |
        v
   GROUP BY + aggregate   -- Tạo nhóm/tổng hợp khi có
        |
        v
      HAVING              -- Lọc nhóm tổng hợp
        |
        v
  WINDOW functions        -- ROW_NUMBER, RANK, SUM OVER, ...
        |
        v
      QUALIFY             -- Chỉ ở DBMS có hỗ trợ
        |
        v
     DISTINCT
        |
        v
     ORDER BY             -- Sắp kết quả cuối
        |
        v
   LIMIT / FETCH / TOP    -- Giới hạn đầu ra theo dialect
~~~

Đây là **mô hình để suy luận ngữ nghĩa**, không phải khẳng định bộ tối ưu vật lý chạy từng khâu theo đúng thứ tự trên. Vị trí riêng của `SELECT`/biểu thức, cách xử lý alias, câu lệnh có tập hợp và các điều khoản khác có chi tiết khác nhau giữa dialect.

Ba điều quyết định ở đây:

1. `WHERE` lọc hàng **trước khi** hàm cửa sổ được tính trong cùng cấp truy vấn.
2. `HAVING` lọc **nhóm** sau khi tổng hợp nhưng **không phải chỗ lọc giá trị `ROW_NUMBER`** trong cùng cấp.
3. `QUALIFY` ở hệ có hỗ trợ được áp dụng **sau khi tính window function**, nên có thể lọc theo thứ hạng vừa tính.

Ví dụ chưa hợp lệ:

~~~sql
-- Lỗi: dùng window function trong WHERE.
SELECT rep_id, team_code, sales_amount
FROM sales_reps
WHERE ROW_NUMBER() OVER (
    PARTITION BY team_code
    ORDER BY sales_amount DESC, rep_id
) <= 2;
~~~

Nếu dùng bí danh:

~~~sql
-- Lỗi: bí danh rn cũng chưa dùng được trong WHERE cùng cấp.
SELECT
    rep_id,
    ROW_NUMBER() OVER (
        PARTITION BY team_code
        ORDER BY sales_amount DESC, rep_id
    ) AS rn
FROM sales_reps
WHERE rn <= 2;
~~~

Các DBMS có thể báo lỗi khác nhau: cột `rn` không tồn tại, hàm cửa sổ không được phép trong `WHERE`, hoặc thông báo tương tự. Lỗi cốt lõi vẫn là **lọc sai giai đoạn**.

### 3.2. Tại sao HAVING cũng không thay thế được?

Một cách thử khác:

~~~sql
-- Không dùng như cách lọc ROW_NUMBER.
SELECT
    team_code,
    rep_id,
    ROW_NUMBER() OVER (
        PARTITION BY team_code
        ORDER BY sales_amount DESC, rep_id
    ) AS rn
FROM sales_reps
HAVING rn <= 2;
~~~

`HAVING` dùng để lọc **các nhóm do `GROUP BY`/aggregate tạo ra**. Nó không phải vị trí chung để dùng kết quả cửa sổ được tính sau giai đoạn tổng hợp. Một số hệ cho dùng alias aggregate trong `HAVING`, nhưng điều đó không tạo bảo đảm dùng alias cửa sổ ở `HAVING`.

Mẫu đúng là đưa kết quả window **sang một cấp truy vấn mới**, hoặc dùng `QUALIFY` ở hệ hỗ trợ.

## 4. Cách thứ nhất: CTE và WHERE ở truy vấn ngoài

### 4.1. Mẫu phổ biến và dễ đọc

~~~sql
WITH ranked_reps AS (
    SELECT
        team_code,
        rep_id,
        rep_name,
        sales_amount,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC, rep_id ASC
        ) AS rn
    FROM sales_reps
)
SELECT
    team_code,
    rep_id,
    rep_name,
    sales_amount
FROM ranked_reps
WHERE rn <= 2
ORDER BY team_code, rn;
~~~

Kết quả:

| Đội | rep_id | Tên | Doanh số |
| --- | ---: | --- | ---: |
| Central | 301 | Hoa | 1000 |
| Central | 302 | Linh | 700 |
| North | 101 | An | 1200 |
| North | 102 | Binh | 1100 |
| South | 201 | Ha | 1500 |
| South | 202 | Lan | 1200 |

Đây là **6 hàng**: tối đa 2 hàng cho mỗi trong 3 đội.

Hai bước **logic**:

1. `ranked_reps` tính `rn` trên **toàn bộ nhân viên mỗi đội**.
2. Truy vấn bên ngoài coi `rn` là một **cột của nguồn `ranked_reps`**, nên `WHERE rn <= 2` là điều kiện lọc bình thường.

`rn` không bắt buộc phải được hiển thị ở đầu ra cuối, nhưng vẫn có thể dùng trong `WHERE` và `ORDER BY` của truy vấn ngoài.

### 4.2. Dùng derived table thay vì CTE

Cùng ý nghĩa có thể viết bằng truy vấn con trong `FROM`:

~~~sql
SELECT
    q.team_code,
    q.rep_id,
    q.rep_name,
    q.sales_amount
FROM (
    SELECT
        team_code,
        rep_id,
        rep_name,
        sales_amount,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC, rep_id
        ) AS rn
    FROM sales_reps
) AS q
WHERE q.rn <= 2
ORDER BY q.team_code, q.rn;
~~~

Trong mẫu này:

- Truy vấn trong tạo **nguồn dẫn xuất** `q`.
- Truy vấn ngoài thấy cột `q.rn` như một cột dữ liệu của nguồn.
- `WHERE q.rn <= 2` hợp lệ.

Cách CTE thường dễ đọc hơn với nhiều bước; derived table có lợi khi chỉ cần một lần phân lớp đơn giản. **Không có quy tắc tuyệt đối rằng CTE luôn nhanh hơn hoặc chậm hơn derived table**: bộ tối ưu có thể inline, materialize hoặc biến đổi theo phiên bản và kế hoạch.

### 4.3. Vì sao có thể lọc rn ở truy vấn ngoài?

Ở cấp truy vấn ngoài, phép tính `ROW_NUMBER` **không còn nằm trong cùng biểu thức `WHERE`**. Nó đã trở thành cột `rn` của một nguồn quan hệ:

~~~text
sales_reps
    |
    |  SELECT ROW_NUMBER() OVER (...) AS rn
    v
ranked_reps: có cột rn
    |
    |  WHERE rn <= 2
    v
top 2 hàng mỗi đội
~~~

Sơ đồ này mô tả **phạm vi logic và khả năng tham chiếu cột**. Nó không có nghĩa CTE buộc được lưu thành bảng vật lý trên đĩa. Nếu một tối ưu hóa đẩy điều kiện có thể làm thay đổi ngữ nghĩa cửa sổ, DBMS phải bảo toàn kết quả đúng khi biến đổi kế hoạch.

### 4.4. CTE vẫn hữu ích khi nhiều cột cửa sổ

Ví dụ tính đồng thời **số thứ tự** và **thứ hạng có đồng điểm**:

~~~sql
WITH measured AS (
    SELECT
        team_code,
        rep_id,
        rep_name,
        sales_amount,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC, rep_id
        ) AS rn,
        RANK() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC
        ) AS sales_rank
    FROM sales_reps
)
SELECT
    team_code,
    rep_id,
    rep_name,
    sales_amount,
    rn,
    sales_rank
FROM measured
WHERE sales_rank <= 2
ORDER BY team_code, sales_rank, rep_id;
~~~

Ở đây `rn` và `sales_rank` **không dùng cùng khóa `ORDER BY` có chủ đích**:

- `ROW_NUMBER` cần `rep_id` phá hòa để chọn **chính xác một hàng cho từng số thứ tự**.
- `RANK` chỉ theo `sales_amount` để **những người cùng doanh số nhận cùng hạng**.

Điều kiện `sales_rank <= 2` có thể trả **nhiều hơn hai hàng mỗi đội** nếu hạng 2 có người đồng điểm.

## 5. Cách thứ hai: QUALIFY ở DBMS hỗ trợ

### 5.1. QUALIFY dùng để làm gì?

`QUALIFY` là mệnh đề lọc dựa trên **kết quả window function** ở một cấp truy vấn. Nó giúp tránh phải bọc câu `SELECT` trong CTE/derived table khi chỉ muốn lấy một vài hàng dựa trên thứ hạng hoặc giá trị cửa sổ.

Ví dụ ở BigQuery, Snowflake, DuckDB và các hệ/phiên bản có hỗ trợ:

~~~sql
SELECT
    team_code,
    rep_id,
    rep_name,
    sales_amount
FROM sales_reps
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY team_code
    ORDER BY sales_amount DESC, rep_id
) <= 2
ORDER BY team_code, sales_amount DESC, rep_id;
~~~

Kết quả vẫn là **6 hàng** với các mã:

~~~text
Central: 301, 302
North:   101, 102
South:   201, 202
~~~

Ở đây `QUALIFY` đánh giá điều kiện **sau khi hàm `ROW_NUMBER()` được tính** trên tập hàng còn lại của truy vấn.

### 5.2. Có thể đặt alias rồi lọc trong QUALIFY?

Nhiều dialect hỗ trợ `QUALIFY` cho phép tham chiếu alias của biểu thức cửa sổ trong danh sách `SELECT`. Ví dụ:

~~~sql
SELECT
    team_code,
    rep_id,
    rep_name,
    sales_amount,
    ROW_NUMBER() OVER (
        PARTITION BY team_code
        ORDER BY sales_amount DESC, rep_id
    ) AS rn
FROM sales_reps
QUALIFY rn <= 2
ORDER BY team_code, rn;
~~~

BigQuery, Snowflake và DuckDB có hỗ trợ những mẫu tham chiếu alias này theo quy tắc riêng của từng sản phẩm. Tuy nhiên **phạm vi alias, xử lý tên trùng và khả năng dùng alias ở QUALIFY không phải hợp đồng chung của mọi DBMS**. Khi cần khả chuyển giữa các dialect `QUALIFY`, có thể viết điều kiện bằng lời gọi window function trực tiếp:

~~~sql
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY team_code
    ORDER BY sales_amount DESC, rep_id
) <= 2
~~~

hoặc quay lại mẫu CTE + `WHERE`.

Trong một số hệ như BigQuery, `QUALIFY` yêu cầu có ít nhất một window function trong `SELECT` hoặc trong chính `QUALIFY`. Đừng dùng `QUALIFY` chỉ để thay thế một `WHERE` thông thường khi không có nhu cầu phân tích cửa sổ.

### 5.3. QUALIFY không phải cú pháp SQL phổ quát

**Không phải DBMS nào cũng hỗ trợ từ khóa `QUALIFY`.** Các hệ có hỗ trợ được biết đến gồm **BigQuery, Snowflake, DuckDB, Amazon Redshift, Teradata** và một số nền tảng phân tích khác, tùy phiên bản.

Trong các bản PostgreSQL, MySQL 8.x, SQL Server và SQLite được dùng rộng rãi, hãy mặc định dùng **CTE/derived table + `WHERE`** thay vì chép thẳng `QUALIFY`. Với Oracle và các bản phát hành mới của những DBMS khác, cần kiểm tra tài liệu của **đúng phiên bản đang triển khai** trước khi quyết định có thể dùng `QUALIFY`.

Ví dụ:

~~~sql
-- Mẫu có tính khả chuyển cao:
WITH ranked AS (
    SELECT
        team_code,
        rep_id,
        sales_amount,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC, rep_id
        ) AS rn
    FROM sales_reps
)
SELECT team_code, rep_id, sales_amount
FROM ranked
WHERE rn <= 2;
~~~

Không cần có `QUALIFY` để thực hiện bài toán top-N-per-group.

### 5.4. Bảng so sánh hai cách

| Tiêu chí | Truy vấn ngoài / CTE | QUALIFY |
| --- | --- | --- |
| Mục đích | Lọc trên cột cửa sổ đã tính ở cấp trong | Lọc trên biểu thức cửa sổ trong cùng cấp |
| Tính khả chuyển | Rộng trên DBMS hỗ trợ window functions | Phụ thuộc DBMS/phiên bản |
| Độ dài câu SQL | Dài hơn vì có hai cấp truy vấn | Gọn hơn |
| Dễ dùng lại nhiều kết quả trung gian | Tốt, có thể đặt tên nhiều CTE | Thường hợp với lọc ngắn |
| Phạm vi alias | Alias CTE trở thành cột ở truy vấn ngoài | Quy tắc alias riêng từng dialect |
| Hiệu năng | Phụ thuộc optimizer và kế hoạch | Cũng phụ thuộc optimizer và kế hoạch |
| Vị trí lọc | `WHERE` ở **cấp ngoài** | `QUALIFY` ở **cấp có window function** |

**Không kết luận rằng `QUALIFY` chắc chắn nhanh hơn CTE** chỉ vì viết ngắn hơn. Nhiều bộ tối ưu có thể đưa hai cách về kế hoạch tương đương hoặc gần nhau.

## 6. Top N mỗi nhóm: ROW_NUMBER khác RANK và DENSE_RANK

### 6.1. ROW_NUMBER: tối đa N hàng mỗi phân vùng

Khi yêu cầu là “**chọn đúng tối đa 2 người mỗi đội**”, `ROW_NUMBER()` với khóa phá hòa phù hợp:

~~~sql
WITH ranked AS (
    SELECT
        team_code,
        rep_id,
        rep_name,
        sales_amount,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC, rep_id ASC
        ) AS rn
    FROM sales_reps
)
SELECT team_code, rep_id, rep_name, sales_amount
FROM ranked
WHERE rn <= 2
ORDER BY team_code, rn;
~~~

Mỗi đội có ít nhất hai người trong bộ dữ liệu mẫu, nên kết quả có đúng **2 hàng mỗi đội**.

Nếu một đội có ít hơn 2 người, truy vấn chỉ trả **số người thực có**, không tạo hàng giả. Nếu hai người bằng doanh số, `rep_id` giải quyết thứ tự để chọn người đứng trước theo một tiêu chí phụ được công khai.

### 6.2. RANK: giữ cả người đồng hạng ở ranh giới

Nếu chính sách là “**lấy tất cả nhân viên có thứ hạng doanh số từ 1 tới 2, bao gồm người đồng hạng**”:

~~~sql
WITH ranked AS (
    SELECT
        team_code,
        rep_id,
        rep_name,
        sales_amount,
        RANK() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC
        ) AS sales_rank
    FROM sales_reps
)
SELECT team_code, rep_id, rep_name, sales_amount, sales_rank
FROM ranked
WHERE sales_rank <= 2
ORDER BY team_code, sales_rank, rep_id;
~~~

Kết quả:

| Đội | Nhân viên | Doanh số | sales_rank |
| --- | --- | ---: | ---: |
| Central | Hoa | 1000 | 1 |
| Central | Linh | 700 | 2 |
| North | An | 1200 | 1 |
| North | Binh | 1100 | 2 |
| North | Chi | 1100 | 2 |
| South | Ha | 1500 | 1 |
| South | Lan | 1200 | 2 |
| South | Minh | 1200 | 2 |

Tổng cộng **8 hàng**: North và South mỗi đội có 3 người do đồng hạng 2.

Cách `QUALIFY` tương đương trên hệ hỗ trợ:

~~~sql
SELECT
    team_code,
    rep_id,
    rep_name,
    sales_amount
FROM sales_reps
QUALIFY RANK() OVER (
    PARTITION BY team_code
    ORDER BY sales_amount DESC
) <= 2
ORDER BY team_code, sales_amount DESC, rep_id;
~~~

### 6.3. DENSE_RANK: chọn N mức doanh số phân biệt

`DENSE_RANK()` không nhảy hạng sau đồng điểm. Trong bảng mẫu, hai đội North/South đều có hạng 1, hạng 2 (đồng điểm) rồi hạng 3 ở mức doanh số thấp hơn. Vì thế `DENSE_RANK() <= 2` tình cờ trả cùng 8 hàng như `RANK() <= 2`.

Nhưng hai hàm không luôn giống nhau. Giả sử điểm giảm dần là:

~~~text
1200, 1100, 1100, 900, 800

RANK():       1, 2, 2, 4, 5
DENSE_RANK(): 1, 2, 2, 3, 4
~~~

Với điều kiện `<= 3`:

- `RANK() <= 3` chỉ lấy `1200, 1100, 1100`.
- `DENSE_RANK() <= 3` lấy thêm `900`.

Vì vậy trước khi viết `WHERE rank_col <= N` hay `QUALIFY ... <= N`, hãy xác định muốn **N người**, **N vị trí hạng có lỗ trống**, hay **N mức giá trị phân biệt**.

### 6.4. Sai lầm khi thêm khóa phá hòa cho RANK

Nếu viết:

~~~sql
RANK() OVER (
    PARTITION BY team_code
    ORDER BY sales_amount DESC, rep_id ASC
)
~~~

thì `rep_id` là duy nhất, hai nhân viên cùng doanh số **không còn đồng hạng theo toàn bộ ORDER BY**. Họ có thể nhận rank khác nhau. Nếu nghiệp vụ muốn giữ **đồng hạng doanh số**, chỉ dùng `sales_amount` (và những tiêu chí thật sự định nghĩa đồng hạng) trong cửa sổ của `RANK`.

Để sắp đầu ra cuối giữa những người đồng hạng, có thể thêm `rep_id` ở **ORDER BY cuối truy vấn**, không cần đưa vào thứ tự dùng để tính hạng.

## 7. Lọc trước và sau cửa sổ: cùng điều kiện, khác kết quả

Đây là một trong những điểm quan trọng nhất của bài.

Giả sử yêu cầu: “Lấy hai nhân viên doanh số cao nhất **đang hoạt động** trong mỗi đội.” Có hai cách hiểu dễ bị lẫn:

- **A — Xếp hạng chỉ trên người ACTIVE:** loại người INACTIVE trước, rồi tính `ROW_NUMBER` trên những người còn lại.
- **B — Xếp hạng trên toàn bộ nhân viên:** tính `ROW_NUMBER` cho tất cả, sau đó chỉ hiển thị những người ACTIVE nằm trong hai vị trí đầu.

Hai cách trả kết quả **khác nhau**.

### 7.1. Lọc trước khi tính ROW_NUMBER

~~~sql
WITH ranked_active AS (
    SELECT
        team_code,
        rep_id,
        rep_name,
        sales_amount,
        rep_status,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC, rep_id
        ) AS rn
    FROM sales_reps
    WHERE rep_status = 'ACTIVE'
)
SELECT team_code, rep_id, rep_name, sales_amount
FROM ranked_active
WHERE rn <= 2
ORDER BY team_code, rn;
~~~

Kết quả:

| Đội | Nhân viên | Doanh số |
| --- | --- | ---: |
| Central | Hoa | 1000 |
| Central | Linh | 700 |
| North | An | 1200 |
| North | Chi | 1100 |
| South | Ha | 1500 |
| South | Lan | 1200 |

Ở North, Binh INACTIVE bị loại **trước khi xếp hạng**. Khi đó An ở vị trí 1 và Chi trở thành người ACTIVE ở vị trí 2.

Cách `QUALIFY` tương đương:

~~~sql
SELECT
    team_code,
    rep_id,
    rep_name,
    sales_amount
FROM sales_reps
WHERE rep_status = 'ACTIVE'
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY team_code
    ORDER BY sales_amount DESC, rep_id
) <= 2
ORDER BY team_code, sales_amount DESC, rep_id;
~~~

`WHERE` lọc ACTIVE trước, `QUALIFY` lọc hai vị trí trong tập đã được lọc.

### 7.2. Lọc sau khi tính ROW_NUMBER

~~~sql
WITH ranked_all AS (
    SELECT
        team_code,
        rep_id,
        rep_name,
        sales_amount,
        rep_status,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC, rep_id
        ) AS rn
    FROM sales_reps
)
SELECT team_code, rep_id, rep_name, sales_amount
FROM ranked_all
WHERE rn <= 2
  AND rep_status = 'ACTIVE'
ORDER BY team_code, rn;
~~~

Kết quả:

| Đội | Nhân viên | Doanh số |
| --- | --- | ---: |
| Central | Hoa | 1000 |
| Central | Linh | 700 |
| North | An | 1200 |
| South | Ha | 1500 |
| South | Lan | 1200 |

Tổng cộng **5 hàng**. North chỉ còn An vì Binh đứng thứ 2 theo **toàn bộ nhân viên**, nhưng Binh INACTIVE nên bị loại **sau** khi xếp hạng; Chi có `rn = 3` và không được “đôn” lên vị trí 2.

Ở hệ có `QUALIFY`, một cách viết là:

~~~sql
SELECT
    team_code,
    rep_id,
    rep_name,
    sales_amount,
    rep_status
FROM sales_reps
QUALIFY
    ROW_NUMBER() OVER (
        PARTITION BY team_code
        ORDER BY sales_amount DESC, rep_id
    ) <= 2
    AND rep_status = 'ACTIVE'
ORDER BY team_code, sales_amount DESC, rep_id;
~~~

Điều kiện `rep_status = 'ACTIVE'` ở **QUALIFY** nên được áp dụng sau khi tính thứ hạng trên cả những người INACTIVE, theo ngữ nghĩa của mệnh đề.

### 7.3. Một bộ lọc có thể đổi quần thể tính toán

Mẫu tư duy:

~~~text
Cách A — lọc trước:

sales_reps
   |
WHERE rep_status = 'ACTIVE'
   |
ROW_NUMBER() trên người ACTIVE
   |
chỉ giữ rn <= 2


Cách B — lọc sau:

sales_reps
   |
ROW_NUMBER() trên toàn bộ nhân viên
   |
chỉ giữ rn <= 2 và ACTIVE
~~~

Câu hỏi phải rõ: **“đứng đầu trong tập nào?”**

Cùng nguyên tắc áp dụng cho `RANK`, `DENSE_RANK`, `NTILE`, `PERCENT_RANK`, `CUME_DIST`, `LAG`, `LEAD` và các hàm tổng hợp cửa sổ. Lọc hàng trước window thay đổi tập hàng mà các hàm được phép nhìn thấy; lọc sau window giữ nguyên kết quả tính trên quần thể ban đầu.

### 7.4. Lọc theo đội có khác lọc theo trạng thái không?

Nếu cửa sổ dùng `PARTITION BY team_code`, điều kiện:

~~~sql
WHERE team_code = 'North'
~~~

lọc trước window thường **không thay đổi thứ hạng giữa những người North**, vì các đội đã là các phân vùng độc lập. Nó chỉ loại những phân vùng không cần hiển thị.

Ngược lại:

~~~sql
WHERE rep_status = 'ACTIVE'
~~~

thay đổi **số hàng trong chính phân vùng North**, nên có thể thay đổi `ROW_NUMBER` của các nhân viên còn lại.

Đây là lý do một số bộ tối ưu có thể đẩy những bộ lọc **trên toàn bộ khóa phân vùng** vào trước window mà không đổi ý nghĩa, nhưng không thể tùy tiện đẩy mọi điều kiện lọc hàng vào trước cửa sổ.

## 8. Dữ liệu mẫu thứ hai: tìm đơn hàng mới nhất của từng khách

Top-N theo nhóm là một ứng dụng phổ biến. Ứng dụng khác là **lấy một hàng mới nhất theo từng khóa** (*latest row per group*).

### 8.1. Tạo bảng đơn hàng

~~~sql
CREATE TABLE orders (
    order_id     INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL,
    ordered_at   TIMESTAMP NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL
);

INSERT INTO orders (
    order_id, customer_id, ordered_at, order_status, total_amount
)
VALUES
    (501, 1, TIMESTAMP '2026-07-01 09:00:00', 'PAID',       120.00),
    (502, 1, TIMESTAMP '2026-07-03 10:00:00', 'PENDING',    150.00),
    (503, 1, TIMESTAMP '2026-07-03 10:00:00', 'PAID',       200.00),
    (504, 2, TIMESTAMP '2026-07-02 08:00:00', 'PAID',        70.00),
    (505, 2, TIMESTAMP '2026-07-04 08:00:00', 'CANCELLED',   90.00),
    (506, 3, TIMESTAMP '2026-07-01 11:00:00', 'PAID',        40.00),
    (507, 3, TIMESTAMP '2026-07-05 11:00:00', 'PAID',        60.00),
    (508, 4, TIMESTAMP '2026-07-03 16:00:00', 'PENDING',     30.00);
~~~

Mỗi khách có từ một tới ba đơn. Khách 1 có hai đơn cùng `ordered_at` nên cần quy tắc **phá hòa** khi chọn đơn mới nhất.

Trong ví dụ, `ordered_at` là timestamp dùng cho việc sắp thứ tự; trong hệ thống thật cần xác định rõ **múi giờ, độ chính xác và nguồn thời gian** khi ghi đơn. Khi hai đơn có cùng timestamp, `order_id DESC` ở đây là quy tắc phá hòa minh họa, không tự khẳng định đơn có ID lớn hơn thực sự xảy ra muộn hơn nếu ID không tăng theo thời gian.

### 8.2. Lấy đúng một đơn mới nhất cho mỗi khách

Mẫu CTE:

~~~sql
WITH newest_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        order_status,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM orders
)
SELECT
    customer_id,
    order_id,
    ordered_at,
    order_status,
    total_amount
FROM newest_orders
WHERE rn = 1
ORDER BY customer_id;
~~~

Kết quả:

| customer_id | order_id | order_status | total_amount |
| ---: | ---: | --- | ---: |
| 1 | 503 | PAID | 200 |
| 2 | 505 | CANCELLED | 90 |
| 3 | 507 | PAID | 60 |
| 4 | 508 | PENDING | 30 |

Khách 1 có hai đơn cùng timestamp, nhưng `order_id DESC` khiến đơn 503 được chọn thay vì 502.

`QUALIFY` tương đương trong hệ hỗ trợ:

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    order_status,
    total_amount
FROM orders
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at DESC, order_id DESC
) = 1
ORDER BY customer_id;
~~~

### 8.3. “Đơn mới nhất đã thanh toán” khác “đơn mới nhất rồi kiểm tra đã thanh toán”

**Câu hỏi A: Đơn PAID mới nhất của mỗi khách là gì?**

Lọc `PAID` trước khi tính `ROW_NUMBER`:

~~~sql
WITH ranked_paid AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM orders
    WHERE order_status = 'PAID'
)
SELECT customer_id, order_id, total_amount
FROM ranked_paid
WHERE rn = 1
ORDER BY customer_id;
~~~

Kết quả:

| customer_id | order_id | total_amount |
| ---: | ---: | ---: |
| 1 | 503 | 200 |
| 2 | 504 | 70 |
| 3 | 507 | 60 |

Khách 4 không có đơn PAID. Khách 2 lấy đơn 504 vì đơn mới hơn 505 đã bị loại từ trước do trạng thái CANCELLED.

**Câu hỏi B: Đơn mới nhất của mỗi khách có phải PAID không?**

Tính đơn mới nhất trên **mọi trạng thái**, rồi lọc:

~~~sql
WITH ranked_all AS (
    SELECT
        customer_id,
        order_id,
        order_status,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM orders
)
SELECT customer_id, order_id
FROM ranked_all
WHERE rn = 1
  AND order_status = 'PAID'
ORDER BY customer_id;
~~~

Kết quả chỉ gồm:

| customer_id | order_id |
| ---: | ---: |
| 1 | 503 |
| 3 | 507 |

Khách 2 **không** xuất hiện vì đơn mới nhất của họ là 505 CANCELLED. Khách 4 có đơn mới nhất PENDING.

Một cách `QUALIFY` cho câu hỏi B:

~~~sql
SELECT
    customer_id,
    order_id,
    order_status
FROM orders
QUALIFY
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC, order_id DESC
    ) = 1
    AND order_status = 'PAID'
ORDER BY customer_id;
~~~

**Khi nào dùng mỗi cách?** Câu hỏi A thuộc nhóm “chọn bản ghi mới nhất trong **tập hợp lệ đã lọc**”; câu hỏi B thuộc nhóm “chọn bản ghi mới nhất **trong toàn bộ dữ liệu**, rồi kiểm tra một đặc tính của bản ghi đó”. Thứ tự đặt bộ lọc quyết định ý nghĩa.

## 9. Lọc kết quả của hàm tổng hợp cửa sổ

Không chỉ `ROW_NUMBER`/`RANK` mới cần lọc sau window. Các hàm như `SUM(...) OVER (...)`, `AVG(...) OVER (...)` và `COUNT(...) OVER (...)` cũng thường được dùng làm tiêu chí lọc.

### 9.1. Lọc nhân viên có doanh số vượt trung bình đội

Ví dụ:

~~~sql
WITH measured AS (
    SELECT
        team_code,
        rep_id,
        rep_name,
        sales_amount,
        AVG(sales_amount) OVER (
            PARTITION BY team_code
        ) AS team_avg
    FROM sales_reps
)
SELECT
    team_code,
    rep_id,
    rep_name,
    sales_amount,
    team_avg
FROM measured
WHERE sales_amount > team_avg
ORDER BY team_code, sales_amount DESC, rep_id;
~~~

Tính trung bình đội từ toàn bộ dữ liệu:

| Đội | Tổng doanh số | Số người | Trung bình |
| --- | ---: | ---: | ---: |
| Central | 1700 | 2 | 850 |
| North | 4300 | 4 | 1075 |
| South | 4700 | 4 | 1175 |

Kết quả nhân viên có doanh số **lớn hơn trung bình đội**:

| Đội | Nhân viên | Doanh số | team_avg |
| --- | --- | ---: | ---: |
| Central | Hoa | 1000 | 850 |
| North | An | 1200 | 1075 |
| North | Binh | 1100 | 1075 |
| North | Chi | 1100 | 1075 |
| South | Ha | 1500 | 1175 |
| South | Lan | 1200 | 1175 |
| South | Minh | 1200 | 1175 |

Không có Linh, Dung và Nam vì doanh số thấp hơn trung bình đội tương ứng.

Mẫu `QUALIFY` trong dialect hỗ trợ:

~~~sql
SELECT
    team_code,
    rep_id,
    rep_name,
    sales_amount
FROM sales_reps
QUALIFY sales_amount > AVG(sales_amount) OVER (
    PARTITION BY team_code
)
ORDER BY team_code, sales_amount DESC, rep_id;
~~~

`AVG(...) OVER (...)` khác với `AVG(...)` tổng hợp không có `OVER`: ở đây mỗi hàng vẫn giữ nguyên, chỉ thêm một giá trị trung bình nhóm để so sánh.

### 9.2. Nếu lọc ACTIVE trước thì trung bình cũng thay đổi

Ví dụ:

~~~sql
SELECT
    team_code,
    rep_id,
    rep_name,
    sales_amount,
    AVG(sales_amount) OVER (
        PARTITION BY team_code
    ) AS active_team_avg
FROM sales_reps
WHERE rep_status = 'ACTIVE';
~~~

`AVG` ở đây chỉ nhìn những nhân viên `ACTIVE`, không còn là trung bình của **toàn bộ** đội. North lúc này có các doanh số 1200, 1100, 900; trung bình là `3200/3 ≈ 1066.67` thay vì 1075.

Nếu yêu cầu hiển thị chỉ nhân viên ACTIVE **nhưng vẫn so với trung bình toàn đội**, cần tính window trước, lọc ACTIVE sau:

~~~sql
WITH team_measures AS (
    SELECT
        team_code,
        rep_id,
        rep_name,
        sales_amount,
        rep_status,
        AVG(sales_amount) OVER (
            PARTITION BY team_code
        ) AS team_avg_all
    FROM sales_reps
)
SELECT *
FROM team_measures
WHERE rep_status = 'ACTIVE'
  AND sales_amount > team_avg_all
ORDER BY team_code, sales_amount DESC, rep_id;
~~~

Ở hệ `QUALIFY`, điều kiện có thể dùng:

~~~sql
SELECT
    team_code,
    rep_id,
    rep_name,
    sales_amount,
    rep_status
FROM sales_reps
QUALIFY
    rep_status = 'ACTIVE'
    AND sales_amount > AVG(sales_amount) OVER (
        PARTITION BY team_code
    );
~~~

Điểm quan trọng là **điều kiện ACTIVE nằm sau window**, không thay đổi quần thể dùng để tính trung bình.

## 10. Lọc theo tổng lũy kế

Một trường hợp hay gặp trong báo cáo tài chính là:

> Với mỗi khách hàng, lấy các đơn kể từ thời điểm **tổng tiền tích lũy vượt 250**.

Dùng bảng `orders` ở mục 8. Trước hết tính tổng lũy kế theo khách và thứ tự ngày/ID:

~~~sql
WITH running AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        total_amount,
        SUM(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at ASC, order_id ASC
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ) AS running_total
    FROM orders
)
SELECT
    customer_id,
    order_id,
    total_amount,
    running_total
FROM running
WHERE running_total > 250
ORDER BY customer_id, ordered_at, order_id;
~~~

Với khách 1, các đơn theo thứ tự tăng dần là:

| order_id | total_amount | running_total |
| ---: | ---: | ---: |
| 501 | 120 | 120 |
| 502 | 150 | 270 |
| 503 | 200 | 470 |

Kết quả lọc `running_total > 250` của toàn bộ bảng chỉ có **đơn 502 và 503** thuộc khách 1. Các khách khác có tổng lũy kế không vượt 250 trong dữ liệu mẫu.

Phiên bản `QUALIFY`:

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    total_amount
FROM orders
QUALIFY SUM(total_amount) OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at ASC, order_id ASC
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND CURRENT ROW
) > 250
ORDER BY customer_id, ordered_at, order_id;
~~~

### Vì sao phải ghi ROWS rõ ràng?

Khi tính tổng lũy kế, có hai cách phổ biến định nghĩa khung:

- `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`: tính trên **các hàng vật lý theo thứ tự được xác định**.
- `RANGE ...`: có thể xét cả những hàng **đồng hạng theo giá trị ORDER BY** trong cùng khung, tùy cú pháp và dialect.

Dữ liệu có hai đơn 502 và 503 cùng `ordered_at`. Thêm `order_id` vào `ORDER BY` và dùng `ROWS` giúp thứ tự lũy kế rõ ràng: 502 được cộng trước 503 khi sắp tăng theo ID.

Không viết:

~~~sql
-- Sai ý nghĩa: lọc giá trị từng đơn, không phải tổng tích lũy.
WHERE total_amount > 250
~~~

vì trong bộ dữ liệu mẫu **không đơn nào** có `total_amount > 250`, dù tổng lũy kế của khách 1 vượt ngưỡng.

## 11. Lọc theo LAG hoặc LEAD

`LAG` và `LEAD` so với hàng trước hoặc sau trong **thứ tự cửa sổ**. Khi muốn chỉ giữ những hàng có chênh lệch so với hàng trước, cũng phải lọc **sau khi tính** `LAG`.

Ví dụ tìm những đơn có tiền **lớn hơn đơn trước đó của cùng khách**:

~~~sql
WITH compared AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        total_amount,
        LAG(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at ASC, order_id ASC
        ) AS previous_amount
    FROM orders
)
SELECT
    customer_id,
    order_id,
    total_amount,
    previous_amount
FROM compared
WHERE total_amount > previous_amount
ORDER BY customer_id, ordered_at, order_id;
~~~

Kết quả:

| customer_id | order_id | total_amount | previous_amount |
| ---: | ---: | ---: | ---: |
| 1 | 502 | 150 | 120 |
| 1 | 503 | 200 | 150 |
| 2 | 505 | 90 | 70 |
| 3 | 507 | 60 | 40 |

Khách 4 chỉ có một đơn nên `LAG` trả `NULL`, và điều kiện `total_amount > NULL` không là `TRUE` trong `WHERE`.

Trong hệ có `QUALIFY`:

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    total_amount
FROM orders
QUALIFY total_amount > LAG(total_amount) OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at ASC, order_id ASC
)
ORDER BY customer_id, ordered_at, order_id;
~~~

Ở đây câu hỏi so sánh **các đơn liên tiếp bất kể trạng thái**. Nếu chỉ muốn so sánh các đơn PAID liên tiếp, phải lọc `order_status = 'PAID'` **trước** khi tính `LAG`; nếu lọc `PAID` sau, `LAG` vẫn có thể so với đơn PENDING/CANCELLED trước đó. Hai nghiệp vụ cần SQL khác nhau.

## 12. Nhiều cấp cửa sổ: khi nào cần thêm một CTE?

Một window function không tự biến alias của mình thành biểu thức sẵn có cho **window function khác ngay trong cùng cấp `SELECT`** ở nhiều DBMS.

Ví dụ yêu cầu hai bước:

1. Tính tổng tiền tích lũy cho từng khách.
2. Xếp hạng các hàng **theo tổng tích lũy** vừa tính.

Không nên viết dạng lồng window function:

~~~sql
-- Không phải mẫu hợp lệ trong nhiều DBMS:
SELECT
    order_id,
    RANK() OVER (
        ORDER BY SUM(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at, order_id
        ) DESC
    )
FROM orders;
~~~

Một cách rõ ràng là phân làm hai cấp CTE:

~~~sql
WITH running AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        total_amount,
        SUM(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at, order_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ) AS running_total
    FROM orders
),
ranked_running AS (
    SELECT
        customer_id,
        order_id,
        running_total,
        ROW_NUMBER() OVER (
            ORDER BY running_total DESC, customer_id, order_id
        ) AS global_running_rank
    FROM running
)
SELECT
    customer_id,
    order_id,
    running_total,
    global_running_rank
FROM ranked_running
WHERE global_running_rank <= 3
ORDER BY global_running_rank;
~~~

Với dữ liệu mẫu, hai giá trị lớn nhất là 470 (đơn 503) và 270 (đơn 502) của khách 1; giá trị tiếp theo là 160 (đơn 505) của khách 2. Truy vấn trả ba hàng tương ứng nếu dùng sắp thứ tự nêu trên.

**Vì sao cần hai cấp?** Vì bước thứ hai cần dùng **cột là kết quả của bước cửa sổ trước** như dữ liệu đầu vào. `QUALIFY` lọc một cửa sổ đã tính trong cùng cấp, nhưng **không phải** cách để tùy tiện lồng hai window functions vào nhau.

## 13. GROUP BY, HAVING, WINDOW và QUALIFY

Đôi khi yêu cầu là:

> Tính **doanh số tổng của từng đội**, rồi chỉ lấy **hai đội có tổng cao nhất**.

Ở đây trước khi xếp hạng phải chuyển **mức hạt dữ liệu** từ từng nhân viên sang từng đội.

### 13.1. Cách khả chuyển: tổng hợp, rồi xếp hạng, rồi lọc

~~~sql
WITH team_totals AS (
    SELECT
        team_code,
        SUM(sales_amount) AS total_sales
    FROM sales_reps
    GROUP BY team_code
),
ranked_teams AS (
    SELECT
        team_code,
        total_sales,
        ROW_NUMBER() OVER (
            ORDER BY total_sales DESC, team_code
        ) AS rn
    FROM team_totals
)
SELECT team_code, total_sales
FROM ranked_teams
WHERE rn <= 2
ORDER BY total_sales DESC, team_code;
~~~

Tổng doanh số:

| Đội | total_sales |
| --- | ---: |
| South | 4700 |
| North | 4300 |
| Central | 1700 |

Kết quả top 2 đội là **South, North**.

### 13.2. Kết hợp GROUP BY và QUALIFY

Ở dialect hỗ trợ `QUALIFY`, có thể viết:

~~~sql
WITH team_totals AS (
    SELECT
        team_code,
        SUM(sales_amount) AS total_sales
    FROM sales_reps
    GROUP BY team_code
)
SELECT
    team_code,
    total_sales
FROM team_totals
QUALIFY ROW_NUMBER() OVER (
    ORDER BY total_sales DESC, team_code
) <= 2
ORDER BY total_sales DESC, team_code;
~~~

Nhìn vào dữ liệu mà `QUALIFY` đang xử lý: nguồn `team_totals` có **một hàng cho mỗi đội**, nên cửa sổ xếp hạng **đội**, không phải nhân viên.

Một số dialect còn cho viết aggregate trực tiếp trong `ORDER BY` của cửa sổ cùng truy vấn `GROUP BY`, nhưng mẫu CTE trên dễ đọc hơn và giúp tránh nhầm lẫn giữa kết quả ở **cấp nhóm** với cấp hàng nguyên bản.

### 13.3. HAVING lọc nhóm, QUALIFY lọc kết quả cửa sổ

Nếu bài toán là “chỉ lấy **đội có tổng doanh số trên 4000**”:

~~~sql
SELECT
    team_code,
    SUM(sales_amount) AS total_sales
FROM sales_reps
GROUP BY team_code
HAVING SUM(sales_amount) > 4000
ORDER BY total_sales DESC;
~~~

`HAVING` rất phù hợp: nó lọc dựa trên **giá trị tổng hợp của từng đội**.

Nếu bài toán là “lấy **hai đội có tổng doanh số cao nhất**”, cần một **xếp hạng giữa các đội**, vì điều kiện không phải một ngưỡng cố định mà là vị trí sau khi so sánh các tổng. `ROW_NUMBER() OVER (ORDER BY total_sales DESC)` + truy vấn ngoài hoặc `QUALIFY` diễn đạt trực tiếp hơn.

Không dùng `HAVING` chỉ vì nhìn thấy một từ “sau” trong yêu cầu; phải biết điều kiện lọc áp dụng **sau phép nhóm** hay **sau phép cửa sổ**.

## 14. QUALIFY và DISTINCT, ORDER BY, LIMIT

### 14.1. QUALIFY thường được xử lý trước DISTINCT

Trong mô hình xử lý logic của các hệ hỗ trợ `QUALIFY` như BigQuery và Snowflake, thứ tự liên quan thường là:

~~~text
WINDOW → QUALIFY → DISTINCT → ORDER BY → LIMIT
~~~

Điều này có nghĩa `QUALIFY` lọc **các hàng có kết quả window** rồi `DISTINCT` mới loại trùng theo những cột được chọn trong đầu ra.

Ví dụ:

~~~sql
SELECT DISTINCT team_code
FROM sales_reps
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY team_code
    ORDER BY sales_amount DESC, rep_id
) <= 2
ORDER BY team_code;
~~~

`QUALIFY` giữ hai người đứng đầu mỗi đội, nhưng `SELECT DISTINCT team_code` sau đó chỉ giữ **một mã mỗi đội**. Kết quả có **3 hàng**: Central, North, South, không phải 6.

Đừng suy rằng `QUALIFY` tự tương đương `DISTINCT`; chúng giải quyết **hai vấn đề khác nhau**. Mức hạt của đầu ra cuối phụ thuộc **cột được SELECT** và việc có `DISTINCT` hay không.

### 14.2. ORDER BY trong OVER không quyết định thứ tự đầu ra

~~~sql
SELECT
    team_code,
    rep_id,
    sales_amount
FROM sales_reps
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY team_code
    ORDER BY sales_amount DESC, rep_id
) <= 2;
~~~

Truy vấn trả đúng **tập** sáu nhân viên, nhưng không có `ORDER BY` cuối thì thứ tự trình bày **không được đảm bảo**.

Khi hiển thị báo cáo:

~~~sql
ORDER BY team_code, sales_amount DESC, rep_id;
~~~

Cũng cần nhớ `ORDER BY` trong window có thể khác `ORDER BY` cuối: một cái định nghĩa tiêu chí tính, một cái định nghĩa sắp hàng kết quả.

### 14.3. LIMIT 2 không thay cho top 2 mỗi đội

~~~sql
-- Chỉ lấy 2 hàng của toàn bộ kết quả, không phải 2 hàng mỗi đội.
SELECT
    team_code,
    rep_id,
    sales_amount
FROM sales_reps
ORDER BY sales_amount DESC, rep_id
LIMIT 2;
~~~

Cú pháp `LIMIT 2` ở hệ hỗ trợ `LIMIT` cho **2 hàng toàn bộ dữ liệu**, không tạo phân vùng North/South/Central.

Để lấy hai hàng **trong từng đội**, cần:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY team_code
    ORDER BY sales_amount DESC, rep_id
)
~~~

rồi lọc `rn <= 2` bằng truy vấn ngoài/`QUALIFY`. Các hệ khác có thể dùng `TOP` hoặc `FETCH FIRST` thay cho `LIMIT`, nhưng giới hạn hàng cuối vẫn không tự là giới hạn **mỗi phân vùng**.

## 15. Các dialect hỗ trợ QUALIFY và cách viết thay thế

Từ khóa `QUALIFY` có lịch sử trong các nền tảng phân tích dữ liệu và ngày càng xuất hiện ở nhiều hệ, nhưng **không phải phần cú pháp có mặt đồng đều trong mọi engine**.

| Hệ quản trị | Cách tiếp cận phù hợp |
| --- | --- |
| Google BigQuery | Có `QUALIFY`; thường dùng trực tiếp window expression hoặc alias được hỗ trợ |
| Snowflake | Có `QUALIFY`; hỗ trợ tham chiếu alias SELECT theo quy tắc của Snowflake |
| DuckDB | Có `QUALIFY`; hỗ trợ dạng trực tiếp và dạng dùng alias của window |
| Amazon Redshift | Có `QUALIFY`; chú ý yêu cầu alias của quan hệ trong một số vị trí cú pháp |
| Teradata | Có `QUALIFY` trong hệ sinh thái Teradata |
| Databricks SQL / các nền tảng phân tích khác | Có thể có `QUALIFY` tùy sản phẩm và phiên bản; kiểm tra tài liệu cụ thể |
| PostgreSQL | Cách khả chuyển: `WITH`/subquery rồi `WHERE` ở ngoài |
| Microsoft SQL Server | Cách khả chuyển: CTE/derived table rồi lọc; không dùng `QUALIFY` theo mẫu T-SQL thông dụng |
| MySQL 8.x | Hỗ trợ window functions nhưng không dùng `QUALIFY` trong cú pháp MySQL phổ biến; dùng truy vấn ngoài |
| SQLite có window functions | Dùng CTE/derived table và `WHERE` bên ngoài |
| Oracle | Kiểm tra phiên bản và hỗ trợ thực tế; mẫu truy vấn ngoài vẫn có thể dùng |

### Một số ví dụ ngắn theo dialect

**BigQuery — trực tiếp QUALIFY:**

~~~sql
SELECT
    team_code,
    rep_id,
    sales_amount
FROM sales_reps
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY team_code
    ORDER BY sales_amount DESC, rep_id
) <= 2
ORDER BY team_code, sales_amount DESC, rep_id;
~~~

**Redshift — đặt alias cho bảng trong trường hợp cần phân biệt QUALIFY sau FROM:**

~~~sql
SELECT
    s.team_code,
    s.rep_id,
    s.sales_amount
FROM sales_reps AS s
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY s.team_code
    ORDER BY s.sales_amount DESC, s.rep_id
) <= 2
ORDER BY s.team_code, s.sales_amount DESC, s.rep_id;
~~~

**PostgreSQL/SQL Server/MySQL/SQLite — hai cấp truy vấn:**

~~~sql
WITH ranked AS (
    SELECT
        team_code,
        rep_id,
        sales_amount,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC, rep_id
        ) AS rn
    FROM sales_reps
)
SELECT team_code, rep_id, sales_amount
FROM ranked
WHERE rn <= 2
ORDER BY team_code, sales_amount DESC, rep_id;
~~~

SQL Server cũng có thể dùng `TOP`, `CROSS APPLY`/`OUTER APPLY` hoặc chiến lược khác cho một số bài toán top-N-per-group, nhưng CTE + `ROW_NUMBER` là mẫu dễ đọc và phổ biến. Trong PostgreSQL còn có `DISTINCT ON` cho trường hợp **một hàng theo mỗi khóa**, nhưng đây là cú pháp đặc thù PostgreSQL, không thay thế tổng quát cho `ROW_NUMBER` và `QUALIFY`.

### Quy tắc thực dụng khi viết SQL dùng nhiều hệ

- Nếu có **một DBMS đích cố định** và nó hỗ trợ `QUALIFY`, dùng `QUALIFY` để câu truy vấn ngắn gọn khi phù hợp.
- Nếu code phải chạy trên **nhiều DBMS**, ưu tiên **CTE/derived table + `WHERE`**.
- Nếu SQL được ORM/query builder sinh ra, kiểm tra nó có hỗ trợ `QUALIFY` theo dialect hay không.
- Không tự đổi `WHERE` thành `QUALIFY` chỉ vì muốn “lọc muộn”: chỉ dùng khi **ngữ nghĩa sau window** đúng yêu cầu.

## 16. Hiệu năng: QUALIFY có nhanh hơn CTE không?

### 16.1. Cú pháp ngắn không đồng nghĩa chi phí thấp

Hai truy vấn sau có thể cùng trả top 2 mỗi đội:

~~~sql
-- CTE:
WITH ranked AS (
    SELECT
        team_code, rep_id, sales_amount,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC, rep_id
        ) AS rn
    FROM sales_reps
)
SELECT team_code, rep_id, sales_amount
FROM ranked
WHERE rn <= 2;
~~~

~~~sql
-- QUALIFY:
SELECT team_code, rep_id, sales_amount
FROM sales_reps
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY team_code
    ORDER BY sales_amount DESC, rep_id
) <= 2;
~~~

Bộ tối ưu có thể triển khai bằng sort/window, lựa chọn top-N theo phân vùng, index lookup hoặc các kỹ thuật khác tùy hệ và phiên bản. Không có bảo đảm chung rằng `QUALIFY` tự động **ít thao tác hơn** chỉ vì bỏ được CTE ở văn bản SQL.

Một số engine nhận ra điều kiện `ROW_NUMBER <= N` và có tối ưu chuyên biệt; nhưng việc có tối ưu đó, phạm vi áp dụng và cách xử lý khi có đồng hạng **phụ thuộc engine**. Đừng mặc định mọi hàng phía sau N chắc chắn không được xử lý.

### 16.2. Chỉ mục phục vụ thứ tự cửa sổ

Nếu bảng rất lớn và thường cần xếp nhân viên theo đội và doanh số:

~~~sql
CREATE INDEX idx_sales_reps_team_amount
ON sales_reps (
    team_code,
    sales_amount DESC,
    rep_id
);
~~~

Đây là **ứng viên chỉ mục** phù hợp với:

~~~sql
PARTITION BY team_code
ORDER BY sales_amount DESC, rep_id
~~~

Một chỉ mục có thứ tự phù hợp **có thể** giúp giảm chi phí truy cập/sắp xếp ở một số kế hoạch, nhưng không đảm bảo luôn được dùng hoặc tránh mọi sort. Cần xét số hàng, độ chọn lọc, các cột khác cần đọc, chi phí duy trì index khi ghi dữ liệu và đặc điểm DBMS.

Với bảng `orders` và bài toán đơn mới nhất:

~~~sql
CREATE INDEX idx_orders_customer_latest
ON orders (
    customer_id,
    ordered_at DESC,
    order_id DESC
);
~~~

Index này có thể hữu ích khi truy vấn lấy những đơn mới nhất theo từng `customer_id`. Tuy nhiên nếu muốn giảm chi phí hơn nữa, có thể cần thiết kế thêm dựa trên workload thực tế, không chỉ một câu SQL mẫu.

### 16.3. Đo kế hoạch thực thi

Trong PostgreSQL:

~~~sql
EXPLAIN
WITH ranked AS (
    SELECT
        rep_id,
        team_code,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC, rep_id
        ) AS rn
    FROM sales_reps
)
SELECT rep_id, team_code
FROM ranked
WHERE rn <= 2;
~~~

Có thể xem `EXPLAIN (ANALYZE, BUFFERS)` với truy vấn `SELECT` đã kiểm soát phạm vi; `ANALYZE` chạy thật câu lệnh để đo. Ở BigQuery, Snowflake hoặc Redshift, xem công cụ kế hoạch/profiling của hệ tương ứng.

Cần quan sát:

- Bao nhiêu hàng đi vào bước window?
- Có sort lớn, spill xuống đĩa hoặc trao đổi dữ liệu giữa các nút xử lý không?
- Kế hoạch có khai thác index/cluster/sort key tương ứng không?
- Một CTE có bị materialize hoặc được inline không?
- Các điều kiện lọc có thể đặt **trước** window mà vẫn đúng nghiệp vụ không?
- Nếu nhiều cửa sổ có `ORDER BY` khác nhau, có bao nhiêu bước sắp xếp cần thiết?

### 16.4. CTE không tự là hàng rào vật chất hóa

Một hiểu lầm phổ biến là “CTE chắc chắn tính xong thành bảng tạm rồi mới `WHERE`”. Nhiều DBMS có thể **inline** hoặc biến đổi CTE vào kế hoạch lớn hơn; một số cho lựa chọn materialization/hint cụ thể.

Điều ta dựa vào là **ngữ nghĩa SQL**: khi dùng `WHERE rn <=2` ở cấp ngoài, kết quả phải tương đương với việc xét giá trị `rn` tính trên tập hàng thích hợp của cấp trong. Bộ tối ưu được phép đổi kế hoạch miễn là **giữ nguyên kết quả logic**, không phải nó phải chạy từng cấp bằng một vòng lặp vật lý riêng.

## 17. Những tình huống cần kiểm tra khi dùng QUALIFY

### 17.1. Alias trùng tên cột thật

Nếu bảng nguồn đã có một cột tên `rn` mà `SELECT` cũng khai báo `ROW_NUMBER(...) AS rn`, các dialect có thể có quy tắc **độ ưu tiên tên** khác nhau khi `QUALIFY rn = 1`. Truy vấn có thể gây nhập nhằng hoặc tham chiếu không đúng cột tác giả định dùng.

Một cách tránh nhầm:

~~~sql
SELECT
    s.team_code,
    s.rep_id,
    s.sales_amount
FROM sales_reps AS s
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY s.team_code
    ORDER BY s.sales_amount DESC, s.rep_id
) = 1;
~~~

Hoặc dùng CTE và một alias ít dễ trùng, chẳng hạn `window_row_num`, rồi tham chiếu có tiền tố alias nguồn ở cấp ngoài.

### 17.2. Window function cần được xác định đúng quần thể

`QUALIFY` không tự hiểu ý nghĩa “trong đội”, “trong tháng” hay “trong loại sản phẩm”. Những điều đó nằm trong:

~~~sql
PARTITION BY ...
ORDER BY ...
~~~

Thiếu `PARTITION BY team_code`, điều kiện `ROW_NUMBER() <= 2` có thể chỉ lấy **hai hàng trên toàn bộ bảng**, chứ không phải hai hàng mỗi đội.

### 17.3. Không đẩy điều kiện sau window vào WHERE một cách máy móc

Giả sử:

~~~sql
QUALIFY
    ROW_NUMBER() OVER (
        PARTITION BY team_code
        ORDER BY sales_amount DESC, rep_id
    ) <= 2
    AND rep_status = 'ACTIVE'
~~~

Nếu người viết chuyển `rep_status = 'ACTIVE'` sang `WHERE` để “tối ưu”, kết quả có thể đổi từ **5 hàng** thành **6 hàng** như đã chứng minh ở mục 7. Đây là thay đổi **ngữ nghĩa**, không chỉ làm gọn câu lệnh.

### 17.4. QUALIFY không phải công cụ bắt lỗi

Một điều kiện ở `QUALIFY` không có nghĩa nó có thể bảo vệ mọi biểu thức nguy hiểm trong các pha xử lý trước đó khỏi lỗi ép kiểu, chia cho 0, hàm toán học ngoài miền giá trị hoặc aggregate không hợp lệ.

Hãy làm dữ liệu/biểu thức an toàn tại nơi tính toán; `QUALIFY` chỉ là mệnh đề **lọc hàng dựa trên kết quả phân tích cửa sổ**.

### 17.5. Cẩn thận với tính ổn định khi dữ liệu thay đổi

Với `ROW_NUMBER`, nếu khóa `ORDER BY` không duy nhất, một số hàng đồng hạng có thể đổi vị trí khi execution plan, dữ liệu hoặc cấu hình thay đổi. Nếu có yêu cầu “chọn đúng một bản ghi”, cần **khóa phá hòa ổn định** như ID duy nhất.

Ngay cả khi thứ tự xác định, một bản ghi mới có doanh số cao hơn vẫn có thể làm thứ hạng cũ thay đổi. Đây là thay đổi dữ liệu thực tế, không phải lỗi của `QUALIFY` hoặc CTE. Với dashboard thời gian thực, cần làm rõ tính nhất quán theo thời điểm và quy tắc làm mới dữ liệu.

## 18. Checklist thiết kế trước khi lọc window function

Trước khi viết một truy vấn có `ROW_NUMBER`, `RANK`, `LAG` hoặc một hàm `... OVER (...)` và điều kiện lọc theo nó, hãy tự trả lời:

1. **Đầu ra có mức hạt nào?** Một hàng cho mỗi khách hàng, mỗi đội, mỗi giao dịch hay mỗi sản phẩm?
2. **Quần thể dùng để tính cửa sổ là gì?** Toàn bộ hàng, chỉ người ACTIVE, chỉ đơn PAID hay một khoảng ngày đã lọc?
3. **Phân vùng theo gì?** `PARTITION BY customer_id`, `team_code` hay không chia phân vùng?
4. **Thứ tự tính theo gì?** Cao trước hay thấp trước; sớm trước hay muộn trước?
5. **Đồng hạng xử lý thế nào?** Dùng `ROW_NUMBER` với khóa phá hòa, `RANK` giữ tie, hay `DENSE_RANK` theo mức giá trị?
6. **Điều kiện là lọc hàng nguồn hay lọc kết quả cửa sổ?** `WHERE` trước window, `QUALIFY` hoặc `WHERE` cấp ngoài sau window.
7. **Đang lọc cùng cấp có hợp lệ không?** Window function không dùng trực tiếp trong `WHERE` cùng cấp.
8. **DBMS có `QUALIFY` không?** Nếu không hoặc muốn đa hệ, dùng CTE/derived table.
9. **Có nhiều tầng tính cửa sổ không?** Nếu có, tách các tầng CTE thay vì lồng window functions bất hợp lệ.
10. **Kết quả có cần thứ tự ổn định?** Có `ORDER BY` cuối cùng và khóa phá hòa thích hợp chưa?
11. **Số hàng đầu vào và phân vùng lớn không?** Cần index, thống kê, hạn chế dữ liệu đúng nghiệp vụ và xem execution plan.
12. **Có `NULL`, nhóm rỗng hoặc giá trị đặc biệt không?** Xác định rõ quy tắc xử lý thay vì để engine chọn theo mặc định.

## 19. Những lỗi thường gặp

| Lỗi/hiểu nhầm | Hệ quả | Cách làm phù hợp |
| --- | --- | --- |
| Dùng `WHERE ROW_NUMBER() OVER (...) <= 2` cùng cấp | Hàm cửa sổ chưa có ở giai đoạn `WHERE` | CTE/derived table hoặc `QUALIFY` |
| Dùng `WHERE rn <= 2` với alias `rn` ngay trong cùng SELECT | Alias chưa là cột khả dụng cho `WHERE` | Lọc `rn` ở truy vấn ngoài |
| Thay `WHERE` bằng `HAVING` để lọc `ROW_NUMBER` | `HAVING` dành cho giai đoạn nhóm/tổng hợp | Dùng `QUALIFY` hoặc truy vấn ngoài |
| Đặt `WHERE rep_status='ACTIVE'` trước window dù muốn rank toàn bộ | Đổi thứ hạng và số hàng được chọn | Tính window trước, lọc trạng thái sau |
| Đặt trạng thái ở `QUALIFY` dù muốn rank chỉ người ACTIVE | Rank cả người INACTIVE, không “đôn” người khác lên | `WHERE ACTIVE` trước `QUALIFY` |
| Quên `PARTITION BY team_code` | Chọn top 2 toàn bảng thay vì mỗi đội | Thêm khóa phân vùng phù hợp |
| Quên khóa phá hòa khi dùng `ROW_NUMBER` | Bản ghi được chọn giữa các hàng bằng nhau có thể thay đổi | `ORDER BY amount DESC, id` |
| Thêm ID vào `ORDER BY` của `RANK` nhưng muốn đồng doanh số cùng hạng | Phá đồng hạng | Chỉ dùng tiêu chí định nghĩa tie |
| Nghĩ `LIMIT 2` là top 2 mỗi đội | Chỉ giới hạn đầu ra toàn bộ | `ROW_NUMBER` phân vùng rồi lọc |
| Cho rằng `QUALIFY` hỗ trợ trong mọi DBMS | Lỗi cú pháp | Kiểm tra dialect hoặc dùng CTE |
| Cho rằng `QUALIFY` chắc chắn nhanh hơn CTE | Không có bằng chứng kế hoạch | Đo execution plan |
| Dùng `ROW_NUMBER` rồi `DISTINCT` nhưng không xét mức hạt | Có thể loại thêm dữ liệu hoặc trả số hàng bất ngờ | Xác định đối tượng một hàng kết quả |
| Tính tổng lũy kế nhưng lọc `WHERE amount > ngưỡng` | Lọc giá trị từng giao dịch, không phải tổng tích lũy | Lọc `running_total` ở cấp ngoài/QUALIFY |
| Tính `LAG` sau khi đã lọc hàng không mong muốn | “Hàng trước” đổi nghĩa | Quyết định rõ tập và thứ tự so sánh |
| Thêm window function khác lên kết quả window trong cùng cấp | Có thể lỗi lồng hàm cửa sổ | Tách nhiều CTE |
| Coi CTE chắc chắn materialize | Hiểu sai optimizer | Dựa trên ngữ nghĩa, xem kế hoạch |
| Không có `ORDER BY` cuối câu | Thứ tự hiển thị không ổn định | Thêm sắp xếp ngoài cùng |

## 20. Bài tập thực hành

Sử dụng hai bảng `sales_reps` và `orders` ở mục 2 và mục 8. Nếu đã sửa dữ liệu, tạo lại bộ dữ liệu mẫu trước khi đối chiếu. Các bài tập có đáp án gợi ý và kết quả kỳ vọng.

### Bài 1 — Top 2 người trong từng đội bằng CTE

Viết truy vấn trả `team_code`, `rep_id`, `rep_name` và `sales_amount` cho **hai người doanh số cao nhất mỗi đội**, dùng `ROW_NUMBER` và `WHERE` của truy vấn ngoài.

**Đáp án:**

~~~sql
WITH ranked AS (
    SELECT
        team_code,
        rep_id,
        rep_name,
        sales_amount,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC, rep_id
        ) AS rn
    FROM sales_reps
)
SELECT team_code, rep_id, rep_name, sales_amount
FROM ranked
WHERE rn <= 2
ORDER BY team_code, rn;
~~~

Kết quả: Central `301, 302`; North `101, 102`; South `201, 202`.

### Bài 2 — Viết lại bằng QUALIFY

Đổi câu ở bài 1 sang `QUALIFY` tại DBMS có hỗ trợ.

**Đáp án:**

~~~sql
SELECT
    team_code,
    rep_id,
    rep_name,
    sales_amount
FROM sales_reps
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY team_code
    ORDER BY sales_amount DESC, rep_id
) <= 2
ORDER BY team_code, sales_amount DESC, rep_id;
~~~

Cùng sáu hàng như bài 1. Nếu đang học trên PostgreSQL/MySQL/SQL Server/SQLite không hỗ trợ `QUALIFY`, dùng bản CTE để thực thi.

### Bài 3 — Sửa truy vấn sai WHERE

Truy vấn này sai ở đâu?

~~~sql
SELECT
    rep_id,
    ROW_NUMBER() OVER (
        PARTITION BY team_code
        ORDER BY sales_amount DESC, rep_id
    ) AS rn
FROM sales_reps
WHERE rn = 1;
~~~

**Đáp án:** `rn` là alias của biểu thức cửa sổ cùng cấp, không dùng được trong `WHERE` ở giai đoạn đó. Đưa `ROW_NUMBER` vào CTE/derived table rồi lọc `WHERE rn = 1` ở cấp ngoài, hoặc dùng `QUALIFY ROW_NUMBER() OVER (...) = 1`.

### Bài 4 — Phân biệt hai cách lọc ACTIVE

Dự đoán kết quả riêng đội North:

A. `WHERE rep_status = 'ACTIVE'` trước `ROW_NUMBER`, rồi lọc `rn <= 2`.

B. Tính `ROW_NUMBER` trên toàn bộ North, sau đó lọc đồng thời `rn <= 2 AND rep_status = 'ACTIVE'`.

**Đáp án:** A trả **An và Chi**. B chỉ trả **An**, vì Binh INACTIVE nằm ở vị trí thứ 2, còn Chi vị trí thứ 3 trước khi lọc. Đây là khác biệt ngữ nghĩa của lọc trước và sau window.

### Bài 5 — Giữ cả người đồng hạng

Muốn chọn các nhân viên **hạng doanh số 1 hoặc 2** trong từng đội, giữ cả người cùng doanh số, dùng hàm nào?

**Đáp án:** `RANK()` chỉ theo `sales_amount DESC`, rồi lọc `sales_rank <= 2`.

~~~sql
WITH ranked AS (
    SELECT
        team_code,
        rep_id,
        sales_amount,
        RANK() OVER (
            PARTITION BY team_code
            ORDER BY sales_amount DESC
        ) AS sales_rank
    FROM sales_reps
)
SELECT team_code, rep_id, sales_amount, sales_rank
FROM ranked
WHERE sales_rank <= 2
ORDER BY team_code, sales_rank, rep_id;
~~~

Kết quả có **8 hàng** vì North có Binh/Chi đồng hạng 2 và South có Lan/Minh đồng hạng 2.

### Bài 6 — Lấy đơn mới nhất của mỗi khách

Viết SQL lấy đúng một đơn của mỗi khách, theo `ordered_at DESC`; nếu bằng thời gian thì chọn `order_id` lớn hơn.

**Đáp án:**

~~~sql
WITH latest AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        order_status,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM orders
)
SELECT customer_id, order_id, order_status
FROM latest
WHERE rn = 1
ORDER BY customer_id;
~~~

Kết quả: khách 1 → `503`; khách 2 → `505`; khách 3 → `507`; khách 4 → `508`.

### Bài 7 — Đơn PAID mới nhất và đơn mới nhất là PAID

Hai yêu cầu khác nhau thế nào?

1. Lấy **đơn PAID mới nhất** của mỗi khách.
2. Lấy **đơn mới nhất**, nhưng chỉ giữ khách nếu đơn đó có trạng thái PAID.

**Đáp án:** yêu cầu 1 đặt `WHERE order_status='PAID'` **trước cửa sổ**, trả `503, 504, 507`. Yêu cầu 2 tính cửa sổ **trên mọi đơn** rồi lọc trạng thái ở ngoài, trả `503, 507`. Khách 2 có đơn mới nhất bị CANCELLED nên không thuộc yêu cầu 2.

### Bài 8 — Lọc nhân viên cao hơn trung bình đội

Viết SQL trả nhân viên có `sales_amount > AVG(sales_amount)` của đội mình.

**Đáp án:**

~~~sql
WITH measured AS (
    SELECT
        team_code,
        rep_id,
        sales_amount,
        AVG(sales_amount) OVER (
            PARTITION BY team_code
        ) AS team_avg
    FROM sales_reps
)
SELECT team_code, rep_id, sales_amount, team_avg
FROM measured
WHERE sales_amount > team_avg
ORDER BY team_code, sales_amount DESC, rep_id;
~~~

Kết quả có **7 người**: Hoa, An, Binh, Chi, Ha, Lan và Minh.

### Bài 9 — Tổng lũy kế vượt 250

Với bảng `orders`, tính tổng tiền lũy kế của từng khách theo thứ tự ngày/ID tăng dần. Chỉ hiển thị các hàng có tổng lũy kế lớn hơn `250`.

**Đáp án:**

~~~sql
WITH running AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        SUM(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at, order_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ) AS running_total
    FROM orders
)
SELECT customer_id, order_id, running_total
FROM running
WHERE running_total > 250
ORDER BY customer_id, ordered_at, order_id;
~~~

Kết quả: `(1, 502, 270)` và `(1, 503, 470)`.

### Bài 10 — Phân biệt LIMIT với top N per group

Tại sao:

~~~sql
SELECT *
FROM sales_reps
ORDER BY sales_amount DESC
LIMIT 2;
~~~

không giải quyết được “top 2 của từng đội”?

**Đáp án:** `LIMIT 2` chỉ lấy **2 hàng của toàn bộ kết quả**, không tính lại thứ tự cho từng `team_code`. Phải dùng `PARTITION BY team_code` trong window và lọc theo `ROW_NUMBER` bằng CTE/`QUALIFY`.

### Bài 11 — Lọc sau LAG

Muốn tìm các đơn có `total_amount` lớn hơn đơn ngay trước của cùng khách, phải lọc ở đâu?

**Đáp án:** tính `LAG(total_amount) OVER (PARTITION BY customer_id ORDER BY ordered_at, order_id)` trong CTE, rồi lọc `total_amount > previous_amount` ở ngoài; hoặc dùng `QUALIFY` trực tiếp. Kết quả theo dữ liệu mẫu là các đơn `502, 503, 505, 507`.

### Bài 12 — Tổng hợp trước khi xếp hạng

Viết truy vấn lấy hai đội có **tổng doanh số** cao nhất, không phải hai nhân viên có doanh số cao nhất.

**Đáp án:**

~~~sql
WITH totals AS (
    SELECT
        team_code,
        SUM(sales_amount) AS total_sales
    FROM sales_reps
    GROUP BY team_code
),
ranked AS (
    SELECT
        team_code,
        total_sales,
        ROW_NUMBER() OVER (
            ORDER BY total_sales DESC, team_code
        ) AS rn
    FROM totals
)
SELECT team_code, total_sales
FROM ranked
WHERE rn <= 2
ORDER BY rn;
~~~

Kết quả: **South 4700**, **North 4300**. Bước `GROUP BY` chuyển mức hạt về một hàng mỗi đội trước khi xếp hạng.

### Bài 13 — Vì sao QUALIFY + DISTINCT có thể ít hàng hơn dự kiến?

Xem:

~~~sql
SELECT DISTINCT team_code
FROM sales_reps
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY team_code
    ORDER BY sales_amount DESC, rep_id
) <= 2;
~~~

Vì sao kết quả có ba hàng thay vì sáu?

**Đáp án:** `QUALIFY` chọn tối đa hai nhân viên của từng đội, nhưng `SELECT DISTINCT team_code` sau đó chỉ còn **một mã đội phân biệt** ở đầu ra. Mức hạt đầu ra đã trở thành **đội**, không còn là nhân viên.

### Bài 14 — Thiết kế ngữ nghĩa cho báo cáo

Một người quản lý nói: “Tìm top 2 người bán hàng đang ACTIVE ở từng đội; nếu người đứng thứ hai trên toàn đội nghỉ việc, tự chọn người ACTIVE tiếp theo.” Hãy quyết định dùng `WHERE ACTIVE` trước hay sau window.

**Gợi ý đáp án:** cần **lọc ACTIVE trước**, rồi tính `ROW_NUMBER` trên tập nhân viên ACTIVE của từng đội và lọc `rn <= 2` sau. Nếu lọc ACTIVE sau khi xếp hạng toàn đội, người ACTIVE thứ ba sẽ không được bổ sung vào top 2.

### Bài 15 — Chọn cách viết đa hệ

Một dự án cần chạy cùng logic top 1 theo `customer_id` trên PostgreSQL, SQL Server và một hệ phân tích có `QUALIFY`. Nên lấy kỹ thuật nào làm bản SQL chung?

**Gợi ý đáp án:** dùng **CTE hoặc derived table với `ROW_NUMBER`**, rồi lọc `rn = 1` ở truy vấn ngoài. Đây là mẫu khả chuyển trên cả ba hệ khi hàm cửa sổ được hỗ trợ. Nếu dự án có riêng lớp SQL theo dialect, có thể cung cấp biến thể `QUALIFY` cho engine hỗ trợ.

## 21. Kết luận

**Lọc kết quả hàm cửa sổ** đòi hỏi phân biệt rõ hai giai đoạn:

- **Lọc hàng nguồn trước khi tính** bằng `WHERE` trong cùng truy vấn. Điều này thay đổi quần thể, thứ hạng, tổng/tỷ lệ và hàng trước-sau mà window function nhìn thấy.
- **Lọc giá trị cửa sổ sau khi tính** bằng `WHERE` ở **truy vấn ngoài** hoặc `QUALIFY` trong DBMS hỗ trợ. Điều này giữ đúng kết quả phân tích trên tập hàng ban đầu của cấp đó rồi mới chọn hàng hiển thị.

Với `ROW_NUMBER()`, `RANK()`, `DENSE_RANK()`, `SUM(...) OVER (...)`, `AVG(...) OVER (...)` hay `LAG()`, cách viết **CTE/derived table + WHERE bên ngoài** là kỹ thuật nền tảng và khả chuyển rộng. `QUALIFY` làm cùng ý tưởng ngắn hơn khi có hỗ trợ, nhưng **không nên coi là cú pháp phổ quát hay mặc định nhanh hơn**.

Hãy luôn hỏi: **“Điều kiện này dùng để quyết định hàng nào được tham gia tính cửa sổ, hay dùng để chọn những hàng sau khi cửa sổ đã tính xong?”** Khi phân biệt được hai ý nghĩa ấy, ta có thể viết đúng top-N theo nhóm, chọn bản ghi mới nhất, lọc theo trung bình/tổng lũy kế và giữ kết quả nhất quán giữa các DBMS.
