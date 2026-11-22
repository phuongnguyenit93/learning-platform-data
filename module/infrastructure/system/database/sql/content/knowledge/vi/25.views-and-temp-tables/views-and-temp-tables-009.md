# Bảng tạm, bảng trung gian và kết quả vật chất hóa

Giả sử một nhóm phân tích phải tạo báo cáo doanh số mỗi ngày từ hàng triệu đơn hàng. Một truy vấn nhiều bước có thể lọc đơn đã thanh toán, tổng hợp theo vùng, kiểm tra dữ liệu nhập và kết hợp thêm một số bảng khác. Có ít nhất ba câu hỏi khác nhau:

- **Tôi chỉ muốn giữ kết quả trong phiên làm việc này** để xử lý tiếp và bỏ đi khi hết phiên?
- **Tôi muốn lưu một tập dữ liệu trung gian có thể dùng lại** cho nhiều bước ETL, nhiều phiên hoặc phục vụ kiểm tra lỗi?
- **Tôi muốn lưu sẵn kết quả của một truy vấn tốn kém** để những lần đọc sau không phải tính lại, chấp nhận việc kết quả có thể chưa phản ánh thay đổi mới nhất?

Các nhu cầu ấy dẫn tới **bảng tạm** (*temporary table*), **bảng trung gian** (*intermediate/staging table*) và **kết quả vật chất hóa** (*materialized result*), thường được triển khai bằng **materialized view** hoặc **bảng tổng hợp lưu sẵn**.

Bài học **Database SQL → View và bảng trung gian** sẽ phân biệt rõ **phạm vi tồn tại**, **tính mới của dữ liệu**, **chi phí đọc/ghi**, **transaction**, **quyền truy cập** và **cách bảo trì** của từng lựa chọn. Ví dụ chính dùng **PostgreSQL**; cuối bài có hướng chuyển sang MySQL, SQL Server, Oracle và SQLite.

## 1. Bản đồ khái niệm: kết quả truy vấn được giữ ở đâu?

Xem sơ đồ:

~~~text
Bang nguon: ORDERS
       |
       +--> SELECT ... FROM (subquery) ...  --> Ket qua cua mot cau lenh
       |
       +--> WITH filtered AS (...) SELECT  --> CTE trong mot cau lenh
       |
       +--> CREATE TEMP TABLE ... AS SELECT --> Bang tam theo session
       |
       +--> CREATE TABLE ... AS SELECT      --> Bang luu lau, phai quan ly
       |                                      viec cap nhat/xoa/tai tao
       |
       +--> CREATE VIEW ... AS SELECT       --> Dinh nghia truy van luu lai
       |                                      du lieu doc theo snapshot
       |
       +--> CREATE MATERIALIZED VIEW ...    --> Ket qua truy van duoc luu
                                               can REFRESH de lam moi
~~~

Điểm quan trọng: **“trung gian” mô tả vai trò trong quy trình**, còn **“tạm” mô tả vòng đời đối tượng**, và **“vật chất hóa” mô tả việc kết quả được lưu thành dữ liệu**. Các khái niệm này không loại trừ nhau:

- Một bảng **tạm** có thể là nơi lưu **dữ liệu trung gian**.
- Một bảng **thường trực** cũng có thể là bảng trung gian của quy trình ETL.
- Một materialized view là **kết quả đã lưu vật lý**, nhưng không tự có vòng đời ngắn như bảng tạm.
- Một CTE có thể được bộ tối ưu **materialize tạm trong kế hoạch thực thi**, nhưng đó **không phải materialized view lưu bền vững**.

### 1.1. So sánh nhanh

| Cấu trúc | Dữ liệu có được lưu thành đối tượng dùng lại? | Phạm vi tồn tại điển hình | Dữ liệu có tự cập nhật khi bảng gốc đổi không? |
| --- | --- | --- | --- |
| **Derived table**: subquery trong `FROM` | Không tạo bảng tên mới trong schema | Một câu lệnh | Được đánh giá theo snapshot/quy tắc của câu lệnh hiện tại |
| **CTE**: `WITH ... AS (...)` | Không tạo bảng thường trực | Một câu lệnh | Cùng phạm vi thực thi câu lệnh |
| **VIEW thông thường** | Lưu **định nghĩa truy vấn** | Tồn tại đến khi bị `DROP` | Khi truy vấn view, kết quả phản ánh dữ liệu gốc theo snapshot áp dụng |
| **TEMP TABLE** | Có, giữ dữ liệu bảng tạm | Session hoặc ngắn hơn theo `ON COMMIT` | **Không**; phải nạp/sửa dữ liệu bảng tạm |
| **Bảng trung gian thường trực** | Có | Đến khi bị xóa/ghi đè theo quy trình | **Không**; ETL hoặc ứng dụng phải duy trì |
| **MATERIALIZED VIEW** | Có, lưu kết quả truy vấn | Đến khi bị `DROP` | Trong PostgreSQL **không**; cần `REFRESH MATERIALIZED VIEW` |

**Không có lựa chọn nào luôn tốt nhất.** Nếu chỉ cần đặt tên một bước truy vấn, CTE thường đơn giản hơn. Nếu cần nhiều bước SQL trong một session và tạo chỉ mục tạm, TEMP TABLE có thể phù hợp. Nếu cần phục vụ báo cáo lặp lại trong nhiều session, hãy cân nhắc bảng tổng hợp hoặc materialized view kèm **chính sách làm mới**.

## 2. Dữ liệu mẫu chung cho cả bài

Ta dùng bảng đơn hàng để minh họa. Trong database PostgreSQL **thực hành riêng**, chạy script này **một lần** khi chưa có bảng `lab_v319_orders`:

~~~sql
CREATE TABLE lab_v319_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id VARCHAR(12) NOT NULL,
    order_date DATE NOT NULL,
    region VARCHAR(10) NOT NULL
        CHECK (region IN ('NORTH', 'SOUTH')),
    gross_amount NUMERIC(12, 2) NOT NULL
        CHECK (gross_amount >= 0),
    order_status VARCHAR(12) NOT NULL
        CHECK (order_status IN ('PAID', 'CANCELLED', 'REFUNDED'))
);

INSERT INTO lab_v319_orders
    (order_id, customer_id, order_date, region, gross_amount, order_status)
VALUES
    (1001, 'C001', DATE '2026-09-02', 'NORTH', 120000.00, 'PAID'),
    (1002, 'C002', DATE '2026-09-05', 'SOUTH',  80000.00, 'PAID'),
    (1003, 'C001', DATE '2026-09-12', 'NORTH', 200000.00, 'PAID'),
    (1004, 'C003', DATE '2026-09-15', 'SOUTH',  50000.00, 'CANCELLED'),
    (1005, 'C004', DATE '2026-09-29', 'NORTH',  90000.00, 'PAID'),
    (1006, 'C001', DATE '2026-10-03', 'NORTH', 150000.00, 'PAID'),
    (1007, 'C002', DATE '2026-10-05', 'SOUTH',  60000.00, 'PAID'),
    (1008, 'C003', DATE '2026-10-11', 'SOUTH', 110000.00, 'PAID'),
    (1009, 'C004', DATE '2026-10-18', 'NORTH',  40000.00, 'REFUNDED'),
    (1010, 'C002', DATE '2026-10-20', 'SOUTH',  70000.00, 'PAID'),
    (1011, 'C003', DATE '2026-10-27', 'NORTH', 130000.00, 'PAID'),
    (1012, 'C001', DATE '2026-11-04', 'NORTH',  95000.00, 'PAID');
~~~

Kiểm tra dữ liệu:

~~~sql
SELECT order_id, order_date, region, gross_amount, order_status
FROM lab_v319_orders
ORDER BY order_date, order_id;
~~~

Bảng có **12 đơn**, trong đó **10 đơn PAID**, **1 đơn CANCELLED**, **1 đơn REFUNDED**. Khi tính doanh thu ở bài này, chỉ lấy `order_status = 'PAID'`.

### 2.1. Kết quả tổng hợp chuẩn để đối chiếu

~~~sql
SELECT
    date_trunc('month', order_date)::date AS month_start,
    region,
    COUNT(*) AS paid_orders,
    SUM(gross_amount) AS paid_revenue
FROM lab_v319_orders
WHERE order_status = 'PAID'
GROUP BY date_trunc('month', order_date)::date, region
ORDER BY month_start, region;
~~~

Kết quả ban đầu:

| month_start | region | paid_orders | paid_revenue |
| --- | --- | ---: | ---: |
| 2026-09-01 | NORTH | 3 | 410000.00 |
| 2026-09-01 | SOUTH | 1 | 80000.00 |
| 2026-10-01 | NORTH | 2 | 280000.00 |
| 2026-10-01 | SOUTH | 3 | 240000.00 |
| 2026-11-01 | NORTH | 1 | 95000.00 |

Ví dụ, tháng 10 vùng SOUTH có ba đơn PAID: **60000 + 110000 + 70000 = 240000**. Đơn `REFUNDED` 1009 không được cộng vào NORTH. Tổng doanh thu PAID của ba tháng là **1105000.00**.

Các ví dụ về bảng tạm, view và materialized view bên dưới đều dựa trên bảng này; sự khác nhau nằm ở **cách giữ kết quả**, không nhất thiết ở công thức tính doanh thu.

## 3. Chưa cần tạo bảng: derived table và CTE

Một “bước trung gian” trong logic SQL **không nhất thiết phải thành một bảng vật lý**.

### 3.1. Derived table: truy vấn con trong FROM

~~~sql
SELECT
    x.region,
    COUNT(*) AS paid_order_count,
    SUM(x.gross_amount) AS total_paid
FROM (
    SELECT region, gross_amount
    FROM lab_v319_orders
    WHERE order_status = 'PAID'
      AND order_date >= DATE '2026-10-01'
      AND order_date < DATE '2026-11-01'
) AS x
GROUP BY x.region
ORDER BY x.region;
~~~

Kết quả:

| region | paid_order_count | total_paid |
| --- | ---: | ---: |
| NORTH | 2 | 280000.00 |
| SOUTH | 3 | 240000.00 |

`x` là **tên của kết quả truy vấn con** trong câu SQL hiện tại. Nó không tạo một bảng `x` trong schema và không thể được một connection khác gọi trực tiếp qua `SELECT * FROM x`.

### 3.2. CTE: đặt tên cho bước trung gian của một câu lệnh

~~~sql
WITH paid_october AS (
    SELECT order_id, region, gross_amount
    FROM lab_v319_orders
    WHERE order_status = 'PAID'
      AND order_date >= DATE '2026-10-01'
      AND order_date < DATE '2026-11-01'
)
SELECT
    region,
    COUNT(*) AS paid_order_count,
    SUM(gross_amount) AS total_paid
FROM paid_october
GROUP BY region
ORDER BY region;
~~~

Kết quả giống derived table phía trên. CTE giúp truy vấn **có cấu trúc rõ ràng**, đặc biệt khi có nhiều bước đặt tên:

~~~sql
WITH paid_october AS (
    SELECT order_id, customer_id, region, gross_amount
    FROM lab_v319_orders
    WHERE order_status = 'PAID'
      AND order_date >= DATE '2026-10-01'
      AND order_date < DATE '2026-11-01'
),
by_customer AS (
    SELECT
        customer_id,
        SUM(gross_amount) AS total_amount
    FROM paid_october
    GROUP BY customer_id
)
SELECT customer_id, total_amount
FROM by_customer
WHERE total_amount >= 100000
ORDER BY total_amount DESC, customer_id;
~~~

Với dữ liệu mẫu tháng 10, khách **C001 = 150000**, **C003 = 240000** (110000 + 130000), **C002 = 130000** (60000 + 70000); cả ba đủ ngưỡng và được trả theo tổng giảm dần.

### 3.3. CTE không mặc định đồng nghĩa một bảng đã lưu

Trong PostgreSQL, bộ tối ưu có thể **gộp CTE vào truy vấn cha** hoặc xử lý CTE như một bước vật chất hóa tạm thời tùy cấu trúc, số lần tham chiếu và đặc tính của truy vấn. **CTE không tự tạo bảng sử dụng lại qua nhiều câu lệnh.**

PostgreSQL 12+ cho phép điều khiển một số trường hợp bằng:

~~~sql
WITH paid_october AS MATERIALIZED (
    SELECT order_id, region, gross_amount
    FROM lab_v319_orders
    WHERE order_status = 'PAID'
      AND order_date >= DATE '2026-10-01'
      AND order_date < DATE '2026-11-01'
)
SELECT region, SUM(gross_amount) AS revenue
FROM paid_october
GROUP BY region;
~~~

và:

~~~sql
WITH paid_october AS NOT MATERIALIZED (
    SELECT order_id, region, gross_amount
    FROM lab_v319_orders
    WHERE order_status = 'PAID'
      AND order_date >= DATE '2026-10-01'
      AND order_date < DATE '2026-11-01'
)
SELECT region, SUM(gross_amount) AS revenue
FROM paid_october
GROUP BY region;
~~~

`MATERIALIZED` là một chỉ dẫn về **cách xử lý CTE trong một statement**; `NOT MATERIALIZED` có thể cho phép kết hợp/tối ưu cùng truy vấn cha trong trường hợp được hỗ trợ. Không nên hiểu rằng `WITH ... MATERIALIZED` tạo một `MATERIALIZED VIEW`, bảng bền vững hoặc cache dùng lại giữa các transaction. Với CTE đệ quy, biểu thức có side effect hay volatile, quy tắc tối ưu có ngoại lệ; chỉ áp dụng gợi ý này khi hiểu kế hoạch thực thi.

### 3.4. Khi nào chỉ cần CTE?

Dùng derived table hoặc CTE khi:

- Kết quả trung gian chỉ được dùng trong **một câu SQL**.
- Không cần tạo chỉ mục riêng hay sửa kết quả trung gian qua những statement tiếp theo.
- Muốn một truy vấn dễ đọc, dễ quản lý phụ thuộc và được tối ưu như một tổng thể.

Chưa nên tạo bảng tạm hoặc materialized view chỉ vì truy vấn có **hai tầng SELECT**. Sự cần thiết phải lưu dữ liệu xuất phát từ **vòng đời, khả năng tái sử dụng và chi phí**.

## 4. Bảng tạm: CREATE TEMP TABLE

Trong PostgreSQL:

~~~sql
CREATE TEMP TABLE ten_bang_tam (
    cot_1 kieu_du_lieu,
    cot_2 kieu_du_lieu
);
~~~

hoặc tạo bảng tạm trực tiếp từ một truy vấn:

~~~sql
CREATE TEMP TABLE ten_bang_tam AS
SELECT ...
FROM ...;
~~~

`TEMP` là dạng rút gọn của `TEMPORARY`. Đặc điểm điển hình PostgreSQL:

1. Bảng tạm có phạm vi **session**; session khác không nhìn thấy đối tượng tạm của bạn.
2. Bảng tạm vẫn là một **bảng có thể truy vấn, INSERT, UPDATE, DELETE**, tạo chỉ mục khi cần.
3. Mặc định của PostgreSQL là **giữ bảng và hàng qua COMMIT trong cùng session** (`ON COMMIT PRESERVE ROWS`).
4. Khi session kết thúc, bảng tạm được dọn dẹp; hoặc kết thúc sớm hơn theo `ON COMMIT DROP`.
5. Nội dung được **chụp lại tại thời điểm nạp**; khi bảng nguồn thay đổi, dữ liệu trong TEMP TABLE **không tự cập nhật**.

### 4.1. Tạo một bảng tạm chứa đơn PAID tháng 10

Trong một kết nối PostgreSQL thử nghiệm:

~~~sql
CREATE TEMP TABLE lab_v319_tmp_oct_paid AS
SELECT
    order_id,
    customer_id,
    order_date,
    region,
    gross_amount
FROM lab_v319_orders
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-10-01'
  AND order_date < DATE '2026-11-01';
~~~

Sau khi câu lệnh thành công, bảng tạm có **5 hàng**:

| order_id | customer_id | region | gross_amount |
| ---: | --- | --- | ---: |
| 1006 | C001 | NORTH | 150000.00 |
| 1007 | C002 | SOUTH | 60000.00 |
| 1008 | C003 | SOUTH | 110000.00 |
| 1010 | C002 | SOUTH | 70000.00 |
| 1011 | C003 | NORTH | 130000.00 |

Thứ tự hàng **không được bảo đảm** chỉ vì câu `CREATE TEMP TABLE AS` có thứ tự đọc nguồn nào đó. Muốn hiển thị ổn định, luôn viết `ORDER BY` ở `SELECT` sử dụng bảng tạm:

~~~sql
SELECT order_id, region, gross_amount
FROM lab_v319_tmp_oct_paid
ORDER BY order_id;
~~~

### 4.2. Tái sử dụng qua nhiều câu SQL trong cùng session

~~~sql
SELECT region, COUNT(*) AS order_count, SUM(gross_amount) AS revenue
FROM lab_v319_tmp_oct_paid
GROUP BY region
ORDER BY region;
~~~

~~~sql
SELECT
    customer_id,
    SUM(gross_amount) AS amount_by_customer
FROM lab_v319_tmp_oct_paid
GROUP BY customer_id
ORDER BY amount_by_customer DESC, customer_id;
~~~

Thay vì lặp điều kiện trạng thái/ngày ở mỗi câu, ta đã **nạp kết quả lọc một lần vào một bảng được đặt tên**. Điều này hữu ích nếu nhiều bước tiếp theo dùng đúng cùng tập đầu vào.

Nhưng cũng có chi phí: tạo bảng, ghi các hàng vào nơi lưu tạm, và có thể cần thống kê/chỉ mục. Nếu tập dữ liệu nhỏ hoặc chỉ được dùng một lần, CTE thường gọn hơn và tránh ghi dữ liệu trung gian không cần thiết.

### 4.3. Bảng tạm có thể sửa dữ liệu độc lập

~~~sql
BEGIN;

UPDATE lab_v319_tmp_oct_paid
SET gross_amount = gross_amount + 1000
WHERE order_id = 1007;

SELECT order_id, gross_amount
FROM lab_v319_tmp_oct_paid
WHERE order_id = 1007;

ROLLBACK;
~~~

Trong transaction, bảng tạm có thể hiện giá `61000` ở đơn 1007. `ROLLBACK` hoàn tác sửa bảng tạm, trở về **60000**. Bảng nguồn `lab_v319_orders` **không bị cập nhật** bởi câu `UPDATE` trên bảng tạm.

**Bảng tạm được nạp bằng SELECT không phải một “cửa sổ sửa trực tiếp” vào bảng nguồn.** Nó là tập dữ liệu khác; nếu cần ghi ngược kết quả, phải thiết kế một `UPDATE`/`MERGE` rõ khóa và điều kiện.

### 4.4. Kết thúc bài thực hành bảng tạm

Khi không cần bảng tạm nữa, trong **chính session đã tạo bảng** có thể dùng:

~~~sql
DROP TABLE lab_v319_tmp_oct_paid;
~~~

Không nên gọi một bảng tạm là “tự biến mất sau mỗi câu lệnh”: mặc định PostgreSQL giữ đến cuối session, trừ khi có cấu hình `ON COMMIT` khác. Nếu chạy lại `CREATE TEMP TABLE lab_v319_tmp_oct_paid` trong cùng session khi bảng còn tồn tại, sẽ gặp lỗi tên đã tồn tại.

## 5. Ba chính sách ON COMMIT của PostgreSQL TEMP TABLE

PostgreSQL hỗ trợ:

~~~sql
ON COMMIT PRESERVE ROWS
ON COMMIT DELETE ROWS
ON COMMIT DROP
~~~

Chúng trả lời: **khi transaction commit, xử lý đối tượng và dữ liệu tạm thế nào?**

| Chính sách | Sau `COMMIT` bảng còn không? | Sau `COMMIT` hàng còn không? |
| --- | --- | --- |
| `PRESERVE ROWS` | **Có** trong session | **Có**; đây là mặc định PostgreSQL |
| `DELETE ROWS` | **Có** trong session | **Không**, các hàng bị xóa ở mốc commit |
| `DROP` | **Không** | Không còn bảng để truy vấn |

Đừng nhầm **transaction** với **session**. Một session có thể chứa nhiều transaction. `COMMIT` kết thúc transaction, nhưng kết nối/session chưa nhất thiết đóng.

### 5.1. PRESERVE ROWS: giữ dữ liệu qua COMMIT

Ví dụ độc lập, chạy một lần trong session:

~~~sql
BEGIN;

CREATE TEMP TABLE lab_v319_tmp_preserve (
    id INTEGER PRIMARY KEY,
    note TEXT
) ON COMMIT PRESERVE ROWS;

INSERT INTO lab_v319_tmp_preserve (id, note)
VALUES (1, 'Còn sau COMMIT');

COMMIT;

SELECT id, note
FROM lab_v319_tmp_preserve;
~~~

`SELECT` cuối trả một hàng, vì bảng và dữ liệu vẫn tồn tại **trong session hiện tại**. Khi đã xong:

~~~sql
DROP TABLE lab_v319_tmp_preserve;
~~~

### 5.2. DELETE ROWS: tự làm rỗng bảng sau COMMIT

~~~sql
BEGIN;

CREATE TEMP TABLE lab_v319_tmp_delete (
    id INTEGER PRIMARY KEY,
    note TEXT
) ON COMMIT DELETE ROWS;

INSERT INTO lab_v319_tmp_delete (id, note)
VALUES (1, 'Chỉ tồn tại trong transaction');

SELECT COUNT(*) AS rows_before_commit
FROM lab_v319_tmp_delete;

COMMIT;

SELECT COUNT(*) AS rows_after_commit
FROM lab_v319_tmp_delete;
~~~

`rows_before_commit = 1`; `rows_after_commit = 0`. **Bảng còn**, nhưng dữ liệu đã được làm rỗng ở mốc commit. Kết thúc:

~~~sql
DROP TABLE lab_v319_tmp_delete;
~~~

Chính sách này có thể hữu ích cho một vùng xử lý **mỗi transaction một tập dữ liệu**, nhưng nếu ứng dụng vô tình autocommit ngay sau câu `INSERT`, các hàng có thể biến mất **trước khi câu SQL tiếp theo kịp sử dụng**. Phải hiểu chế độ transaction của client.

### 5.3. DROP: đối tượng tạm bị xóa sau COMMIT

~~~sql
BEGIN;

CREATE TEMP TABLE lab_v319_tmp_drop (
    id INTEGER PRIMARY KEY,
    note TEXT
) ON COMMIT DROP;

INSERT INTO lab_v319_tmp_drop (id, note)
VALUES (1, 'Chỉ dùng trong giao dịch này');

SELECT * FROM lab_v319_tmp_drop;

COMMIT;
~~~

Sau `COMMIT`, bảng `lab_v319_tmp_drop` không còn trong session. Một câu `SELECT` tiếp theo gọi tên bảng sẽ **báo không tồn tại**, vì vậy không đặt truy vấn đó vào block như thể nó là thao tác thành công.

### 5.4. ROLLBACK có giống COMMIT không?

**Không.** `ON COMMIT` quy định hành động tại **COMMIT**. Còn `ROLLBACK` hoàn tác các thay đổi đã thực hiện trong transaction. Nếu bảng tạm **được tạo trong transaction rồi rollback transaction ấy**, chính việc tạo bảng cũng có thể bị hoàn tác: bảng không còn, vì DDL trong PostgreSQL có tính giao dịch.

Nếu bảng tạm đã tồn tại **trước transaction**, các thay đổi `INSERT`/`UPDATE` trong transaction có thể được rollback, còn bảng tiếp tục tồn tại theo vòng đời của nó.

Do đó hãy phân biệt:

~~~text
CREATE TEMP TABLE trong transaction A
  + COMMIT + ON COMMIT PRESERVE ROWS -> bang con, du lieu con
  + COMMIT + ON COMMIT DELETE ROWS   -> bang con, khong con hang
  + COMMIT + ON COMMIT DROP          -> bang bi drop
  + ROLLBACK A                       -> viec tao bang bi huy
~~~

## 6. Phạm vi session: hai kết nối có nhìn thấy bảng tạm của nhau không?

Giả sử **session A** đã tạo:

~~~sql
CREATE TEMP TABLE lab_v319_tmp_private AS
SELECT order_id, gross_amount
FROM lab_v319_orders
WHERE order_id IN (1001, 1002);
~~~

Trong **session A**:

~~~sql
SELECT COUNT(*) FROM lab_v319_tmp_private;
~~~

trả **2**.

Nhưng trong một **session B thực sự độc lập**, câu:

~~~sql
-- Chay o session B: bang tam cua A khong duoc chia se.
SELECT COUNT(*) FROM lab_v319_tmp_private;
~~~

**không truy cập được bảng tạm của A**. Nếu B không có đối tượng thường trực hoặc bảng tạm khác trùng tên, truy vấn sẽ báo không tìm thấy quan hệ. Các session khác có thể tự tạo **bảng tạm trùng tên** trong vùng tạm riêng mà không chia sẻ dữ liệu.

### 6.1. Cẩn trọng khi dùng connection pool

Trong ứng dụng web, một request logic có thể dùng **connection A** ở bước đầu và **connection B** ở bước sau do connection pool cấp phát. Bảng tạm được gắn với **session database/connection thực tế**, không gắn với người dùng đăng nhập ứng dụng.

Vì vậy:

- Không thiết kế một quy trình phụ thuộc bảng tạm tồn tại qua nhiều request nếu không bảo đảm cùng database session.
- Một connection được đưa lại vào pool có thể còn bảng tạm `PRESERVE ROWS` nếu không có cơ chế reset thích hợp, tạo nguy cơ kết quả cũ hoặc lỗi tên trùng ở request khác.
- Không dùng TEMP TABLE làm kênh truyền dữ liệu giữa hai worker có connection khác nhau.

Nếu cần nhiều session nhìn thấy cùng kết quả, hãy dùng **bảng thường trực có khóa batch** hoặc **materialized view** với quyền truy cập và chính sách vòng đời phù hợp.

### 6.2. Bảng tạm có thể che khuất tên bảng thường trực

Trong PostgreSQL, bảng tạm được tạo ở một schema tạm riêng. Khi truy vấn không ghi tên schema, một bảng tạm trùng tên có thể được tìm thấy **trước** bảng thường trực, tùy quy tắc tìm kiếm đối tượng.

Ví dụ nếu đã có `public.orders` mà lại tạo một bảng tạm tên `orders`, `SELECT * FROM orders` trong cùng session có thể không còn tham chiếu `public.orders` như người đọc tưởng.

Thực hành tốt:

- Dùng tên tạm dễ nhận diện, như `tmp_paid_orders`.
- Dùng tên schema rõ ràng, ví dụ `public.orders`, khi cần chắc chắn lấy bảng thường trực.
- Không tạo bảng tạm trùng tên đối tượng quan trọng của ứng dụng.

## 7. Chỉ mục và thống kê trên bảng tạm

Bảng tạm là một bảng thực sự trong session nên có thể tạo **index** và `ANALYZE`:

~~~sql
CREATE TEMP TABLE lab_v319_tmp_for_index AS
SELECT
    order_id,
    customer_id,
    region,
    gross_amount
FROM lab_v319_orders
WHERE order_status = 'PAID';

CREATE INDEX lab_v319_tmp_customer_idx
ON lab_v319_tmp_for_index (customer_id);

ANALYZE lab_v319_tmp_for_index;

SELECT customer_id, SUM(gross_amount) AS total_paid
FROM lab_v319_tmp_for_index
WHERE customer_id = 'C001'
GROUP BY customer_id;
~~~

Trên dữ liệu mẫu, C001 có các đơn PAID 1001, 1003, 1006 và 1012, tổng **565000.00**. Bảng tạm có 10 hàng PAID.

### 7.1. Chỉ mục tạm không luôn giúp nhanh hơn

Với chỉ mười hàng, bộ tối ưu thường có thể quét tuần tự rất rẻ. Chi phí **tạo chỉ mục và nạp dữ liệu** có thể lớn hơn lợi ích đọc.

Chỉ cân nhắc tạo index tạm khi:

- Bảng tạm đủ lớn.
- Nhiều câu truy vấn tiếp theo dùng lại cột lọc hoặc ghép.
- Tối ưu truy vấn có thể bù chi phí xây chỉ mục.

Đối với bảng tạm lớn trong PostgreSQL, chạy `ANALYZE` sau khi nạp có thể giúp planner có thống kê tốt hơn. Các tiến trình tự động duy trì thống kê thông thường **không xử lý bảng tạm của session người dùng theo cách tương tự bảng thường trực**, nên không mặc định thông số tạm lúc nào cũng mới.

Khi kết thúc:

~~~sql
DROP TABLE lab_v319_tmp_for_index;
~~~

### 7.2. CTAS không tự nhân bản khóa/chỉ mục của bảng nguồn

`CREATE TEMP TABLE ... AS SELECT ...` lấy **kết quả và các cột suy ra**, chứ không biến bảng tạm thành một bản sao đầy đủ của mọi `PRIMARY KEY`, `UNIQUE`, `CHECK`, trigger hoặc index từ bảng gốc.

Nếu cần bảo đảm `order_id` duy nhất trong bảng tạm, hãy khai báo hoặc thêm ràng buộc phù hợp:

~~~sql
CREATE TEMP TABLE lab_v319_tmp_unique AS
SELECT order_id, customer_id
FROM lab_v319_orders
WHERE order_status = 'PAID';

ALTER TABLE lab_v319_tmp_unique
ADD PRIMARY KEY (order_id);

DROP TABLE lab_v319_tmp_unique;
~~~

Không nên dựa vào chuyện `order_id` đang duy nhất trong dữ liệu tại thời điểm tạo để kết luận **mọi lần INSERT sau vào bảng tạm đều bị kiểm tra duy nhất** nếu chưa có constraint.

## 8. Bảng trung gian lưu lâu: staging và ETL

**Bảng trung gian** là một vai trò trong pipeline dữ liệu. Có thể là:

- **Staging**: lưu dữ liệu thô được nhập từ CSV, API hoặc hệ khác, để kiểm tra trước khi ghi vào bảng nghiệp vụ.
- **Work table**: lưu các hàng cần xử lý ở nhiều bước hoặc nhiều job.
- **Bảng chuẩn hóa/tổng hợp**: lưu kết quả đã làm sạch hoặc tính toán để người dùng/báo cáo dùng lại.
- **Bảng kiểm tra lỗi**: lưu các hàng không hợp lệ để xử lý, audit và chạy lại.

Nếu đối tượng cần sống qua nhiều session và nhiều ngày, hãy dùng **bảng thường trực** với khóa batch, chính sách dọn dẹp và quản lý quyền. Không gọi nó là “temporary table” chỉ vì nó được sử dụng trong một giai đoạn tạm của pipeline.

### 8.1. Tạo bảng staging có khóa batch

Ví dụ một luồng nhập đơn từ đối tác; đầu vào chưa chắc có kiểu số hoặc ngày hợp lệ nên ta lưu **giá trị thô dạng text**:

~~~sql
CREATE TABLE lab_v319_import_stage (
    batch_id INTEGER NOT NULL,
    row_no INTEGER NOT NULL,
    external_order_code VARCHAR(30),
    raw_amount VARCHAR(30),
    raw_region VARCHAR(20),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id, row_no)
);

INSERT INTO lab_v319_import_stage (
    batch_id, row_no, external_order_code, raw_amount, raw_region
)
VALUES
    (42, 1, 'EXT-001', '125000.00', 'NORTH'),
    (42, 2, 'EXT-002', '85000.00',  'SOUTH'),
    (42, 3, 'EXT-002', '85000.00',  'SOUTH'),
    (42, 4, 'EXT-003', 'abc',       'NORTH'),
    (42, 5, 'EXT-004', '-3000',     'SOUTH'),
    (42, 6, NULL,      '45000',    'NORTH'),
    (42, 7, 'EXT-005', '70000.00', 'WEST');
~~~

Đây là **bảng thường trực**. Các phiên khác có quyền thích hợp có thể truy vấn `batch_id = 42` sau khi transaction nhập được commit; dữ liệu không tự biến mất khi session nhập kết thúc.

### 8.2. Kiểm tra định dạng trước khi chuyển kiểu

Với PostgreSQL, một ví dụ để đánh dấu giá trị tiền hợp lệ:

~~~sql
SELECT
    row_no,
    external_order_code,
    raw_amount,
    CASE
        WHEN raw_amount ~ '^[0-9]+(\.[0-9]{1,2})?$'
            THEN 'VALID_AMOUNT_FORMAT'
        ELSE 'INVALID_AMOUNT_FORMAT'
    END AS amount_check
FROM lab_v319_import_stage
WHERE batch_id = 42
ORDER BY row_no;
~~~

Trong dữ liệu mẫu, `abc` và `-3000` bị đánh dấu sai định dạng theo **quy tắc ví dụ chỉ nhận số không âm, tối đa hai chữ số thập phân**. Đây mới là bước kiểm tra chuỗi, **chưa** chứng minh giá trị không vượt giới hạn kiểu số của bảng đích hoặc phù hợp mọi quy tắc tài chính.

Có thể kiểm tra đồng thời mã đơn và vùng:

~~~sql
SELECT
    row_no,
    external_order_code,
    CASE
        WHEN external_order_code IS NULL
            THEN 'MISSING_ORDER_CODE'
        WHEN raw_region NOT IN ('NORTH', 'SOUTH')
            THEN 'INVALID_REGION'
        WHEN raw_amount !~ '^[0-9]+(\.[0-9]{1,2})?$'
            THEN 'INVALID_AMOUNT'
        ELSE 'FORMAT_OK'
    END AS validation_status
FROM lab_v319_import_stage
WHERE batch_id = 42
ORDER BY row_no;
~~~

Lưu ý: hai hàng `EXT-002` (row 2 và 3) đều có thể đạt `FORMAT_OK` **nhưng vẫn trùng mã đơn**. Kiểm tra bản ghi trùng là một bước riêng.

### 8.3. Phát hiện hàng nhập trùng trong cùng batch

~~~sql
SELECT
    batch_id,
    external_order_code,
    COUNT(*) AS source_rows
FROM lab_v319_import_stage
WHERE batch_id = 42
  AND external_order_code IS NOT NULL
GROUP BY batch_id, external_order_code
HAVING COUNT(*) > 1
ORDER BY external_order_code;
~~~

Kết quả có **EXT-002** với `source_rows = 2`.

**Không dùng `SELECT DISTINCT *` rồi tưởng đã giải quyết mọi xung đột.** Hai hàng cùng mã nghiệp vụ nhưng khác số tiền hoặc trạng thái cần được quyết định theo quy tắc nguồn, phiên bản, ngày hiệu lực hoặc quy trình rà soát; không tự chọn ngẫu nhiên.

### 8.4. Vì sao staging thường cần batch_id?

`batch_id` giúp:

- Nhập nhiều lô mà không trộn dữ liệu.
- Đánh dấu lô đã kiểm tra/đang xử lý/đã hoàn tất.
- Chạy lại một lô cụ thể mà không xóa dữ liệu lô khác.
- Đối chiếu số hàng vào, số hàng hợp lệ, số hàng lỗi.
- Giữ nguồn để truy vết khi có vấn đề.

**Bảng staging không phải cache báo cáo.** Nó thường chứa dữ liệu **chưa được xác nhận**; cấp quyền đọc như thể đây là dữ liệu nghiệp vụ chuẩn có thể gây hiểu nhầm nghiêm trọng.

### 8.5. Vòng đời dữ liệu staging

Bảng vẫn tồn tại sau `COMMIT`. Từng hàng cũng tồn tại cho đến khi có lệnh `DELETE`/`TRUNCATE`, chính sách phân vùng/lưu trữ hoặc quy trình dọn dẹp. Ví dụ:

~~~sql
-- Chi xoa mot batch khi quy trinh cho phep.
-- KHONG CHAY neu can giu du lieu de audit.
DELETE FROM lab_v319_import_stage
WHERE batch_id = 42;
~~~

`TRUNCATE lab_v319_import_stage` sẽ xóa **mọi hàng** của bảng, không chỉ batch 42. Không dùng `TRUNCATE` như biện pháp dọn một lô trong bảng dùng chung.

## 9. CREATE TABLE AS: tạo bảng trung gian từ kết quả truy vấn

Trong PostgreSQL:

~~~sql
CREATE TABLE new_table AS
SELECT ...
FROM ...;
~~~

`CREATE TABLE AS` (CTAS) tạo **một bảng mới chứa kết quả của truy vấn tại thời điểm chạy**. Nếu không ghi `TEMP`, đối tượng mới là **bảng thường trực** theo quy tắc schema và quyền hiện hành.

### 9.1. Chụp kết quả doanh số tháng 10 thành một bảng

~~~sql
CREATE TABLE lab_v319_oct_snapshot AS
SELECT
    region,
    COUNT(*)::integer AS paid_orders,
    SUM(gross_amount) AS paid_revenue
FROM lab_v319_orders
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-10-01'
  AND order_date < DATE '2026-11-01'
GROUP BY region;
~~~

Truy vấn:

~~~sql
SELECT region, paid_orders, paid_revenue
FROM lab_v319_oct_snapshot
ORDER BY region;
~~~

trả **NORTH: 2 đơn, 280000.00**; **SOUTH: 3 đơn, 240000.00**.

Sau đó nếu `lab_v319_orders` có đơn mới, **bảng snapshot không tự đổi**. CTAS không tạo một liên kết live tới truy vấn nguồn; nó **chụp dữ liệu và lưu hàng**.

### 9.2. Thêm ràng buộc/khóa cho bảng CTAS

Nếu mỗi vùng trong snapshot chỉ được xuất hiện một lần và dữ liệu cần cập nhật về sau:

~~~sql
ALTER TABLE lab_v319_oct_snapshot
ADD PRIMARY KEY (region);
~~~

Đây là **ràng buộc mới trên bảng snapshot**, không phải một ràng buộc đã được tự sao chép từ bảng nguồn. Khi tạo bảng từ tổng hợp, cũng nên xem xét kiểu dữ liệu suy ra và các thuộc tính như `NOT NULL`/`DEFAULT`.

### 9.3. Kết thúc ví dụ CTAS

~~~sql
DROP TABLE lab_v319_oct_snapshot;
~~~

Đừng tạo đi tạo lại cùng tên snapshot trong production mà không có chiến lược thay thế hoặc versioning. Nếu bảng đang được dashboard đọc, `DROP`/`CREATE` có thể làm báo cáo gặp lỗi hoặc thay đổi quyền/metadata; một quy trình đồng bộ có kiểm soát sẽ phù hợp hơn.

## 10. Bảng tổng hợp thường trực: kết quả vật chất hóa do ứng dụng quản lý

Không phải kết quả lưu sẵn nào cũng phải dùng `CREATE MATERIALIZED VIEW`. Ta có thể xây dựng **bảng tổng hợp** có khóa và nạp lại bằng ETL:

~~~sql
CREATE TABLE lab_v319_monthly_summary (
    month_start DATE NOT NULL,
    region VARCHAR(10) NOT NULL,
    paid_orders BIGINT NOT NULL,
    paid_revenue NUMERIC(14, 2) NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (month_start, region)
);
~~~

Nạp số liệu theo snapshot hiện tại:

~~~sql
INSERT INTO lab_v319_monthly_summary (
    month_start, region, paid_orders, paid_revenue, computed_at
)
SELECT
    date_trunc('month', order_date)::date AS month_start,
    region,
    COUNT(*) AS paid_orders,
    SUM(gross_amount) AS paid_revenue,
    CURRENT_TIMESTAMP AS computed_at
FROM lab_v319_orders
WHERE order_status = 'PAID'
GROUP BY date_trunc('month', order_date)::date, region;
~~~

Ưu điểm của bảng thường trực có schema rõ ràng:

- Có thể thêm khóa, index, các cột nghiệp vụ hoặc metadata như `computed_at`, `batch_id`, `source_watermark`.
- Nhiều session và ứng dụng có quyền phù hợp có thể đọc.
- Có thể dùng `INSERT ... ON CONFLICT DO UPDATE` để làm mới **một phần** theo khóa, hoặc cập nhật gia tăng theo thiết kế.
- Có thể áp dụng lưu trữ lịch sử, phân vùng, audit và chính sách quyền riêng.

Đổi lại, **ứng dụng/ETL chịu trách nhiệm giữ dữ liệu đúng và mới**. Một dòng doanh thu trong bảng tổng hợp không tự cập nhật khi hàng `orders` bị hủy, hoàn tiền hoặc thay đổi số tiền.

### 10.1. Làm mới một phần bằng UPSERT theo khóa

Ví dụ: tính lại **tháng 10/2026**:

~~~sql
INSERT INTO lab_v319_monthly_summary AS m (
    month_start, region, paid_orders, paid_revenue, computed_at
)
SELECT
    date_trunc('month', order_date)::date,
    region,
    COUNT(*),
    SUM(gross_amount),
    CURRENT_TIMESTAMP
FROM lab_v319_orders
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-10-01'
  AND order_date < DATE '2026-11-01'
GROUP BY date_trunc('month', order_date)::date, region
ON CONFLICT (month_start, region) DO UPDATE
SET
    paid_orders = EXCLUDED.paid_orders,
    paid_revenue = EXCLUDED.paid_revenue,
    computed_at = EXCLUDED.computed_at;
~~~

Ở đây khóa tổng hợp là **`(month_start, region)`**, không phải `order_id`. `EXCLUDED` chỉ hàng dữ liệu tổng hợp **đề xuất chèn** nhưng trùng khóa đã có.

**Hạn chế quan trọng:** `UPSERT` này cập nhật những nhóm **có xuất hiện trong kết quả SELECT**, nhưng **không tự xóa nhóm đã biến mất** khỏi dữ liệu nguồn. Nếu một vùng/tháng không còn đơn PAID nào, không có hàng nguồn mới cho khóa đó; dòng tổng hợp cũ có thể tiếp tục tồn tại. Phải thiết kế quy tắc làm mới toàn bộ tập khóa của kỳ, ví dụ xóa và tính lại trong một transaction phù hợp, hoặc xây nguồn đầy đủ bao gồm các nhóm có tổng 0.

### 10.2. Full rebuild và incremental refresh

| Cách duy trì | Ý tưởng | Đánh đổi |
| --- | --- | --- |
| **Full rebuild** | Tính lại toàn bộ bảng tổng hợp từ nguồn | Dễ hiểu, nhưng tốn chi phí và có thể khóa tài nguyên |
| **Rebuild theo phân vùng/kỳ** | Tính lại từng tháng/nhóm chịu ảnh hưởng | Cần xác định đầy đủ khóa bị ảnh hưởng, gồm nhóm vừa biến mất |
| **Incremental** | Áp dụng chênh lệch từ những sự kiện thay đổi | Nhanh khi dữ liệu đổi ít, nhưng phức tạp với hoàn tiền, sửa/xóa và sự kiện đến muộn |
| **Snapshot có version** | Tạo bảng phiên bản mới rồi đổi nguồn đọc một cách có kiểm soát | Cần quản lý dung lượng, quyền và thời điểm chuyển đổi |

Không nên nhầm **bảng tổng hợp có UPSERT** với một materialized view tự động cập nhật. Chúng có thể phục vụ mục tiêu đọc giống nhau, nhưng **cơ chế refresh và trách nhiệm vận hành khác nhau**.

## 11. VIEW thường: lưu định nghĩa, không lưu kết quả

Tạo một view:

~~~sql
CREATE VIEW lab_v319_v_monthly_paid AS
SELECT
    date_trunc('month', order_date)::date AS month_start,
    region,
    COUNT(*) AS paid_orders,
    SUM(gross_amount) AS paid_revenue
FROM lab_v319_orders
WHERE order_status = 'PAID'
GROUP BY date_trunc('month', order_date)::date, region;
~~~

Gọi view:

~~~sql
SELECT month_start, region, paid_orders, paid_revenue
FROM lab_v319_v_monthly_paid
ORDER BY month_start, region;
~~~

Kết quả giống bảng đối chiếu ở mục 2. Điểm khác là PostgreSQL lưu **định nghĩa truy vấn của view**; khi truy vấn view, hệ thống thực thi/tối ưu logic đó trên dữ liệu gốc tương ứng với **snapshot của lần truy vấn**.

### 11.1. VIEW có phải là bảng sao chép không?

**Không.** Dùng:

~~~sql
CREATE VIEW lab_v319_v_monthly_paid AS SELECT ...;
~~~

không tạo năm hàng tổng hợp cố định theo nghĩa vật chất hóa. Nếu một đơn PAID bị sửa và transaction đó được commit, lần đọc view tiếp theo theo snapshot phù hợp sẽ tính theo dữ liệu mới.

### 11.2. Không thể tạo index trên một view thường của PostgreSQL như trên bảng

Với PostgreSQL, một view thường **không có bộ hàng riêng được lưu** để bạn tạo chỉ mục B-tree trực tiếp trên các hàng kết quả. Hãy tối ưu **bảng nguồn**, điều kiện lọc và câu truy vấn; hoặc cân nhắc **materialized view** nếu cần lưu sẵn kết quả có index riêng.

Một số hệ quản trị, đặc biệt SQL Server với **indexed views**, có cơ chế khác; không suy luận khả năng từ PostgreSQL cho toàn bộ SQL dialect.

## 12. MATERIALIZED VIEW: kết quả truy vấn được lưu vật lý

PostgreSQL hỗ trợ:

~~~sql
CREATE MATERIALIZED VIEW ten_mv AS
SELECT ...
FROM ...
WITH DATA;
~~~

`WITH DATA` nghĩa là tính và nạp kết quả khi tạo; đây là hành vi mặc định nếu không viết rõ. `WITH NO DATA` tạo định nghĩa nhưng chưa nạp dữ liệu và materialized view sẽ **không thể truy vấn** cho tới khi được nạp bằng `REFRESH MATERIALIZED VIEW ... WITH DATA`.

### 12.1. Tạo materialized view doanh số theo tháng và vùng

~~~sql
CREATE MATERIALIZED VIEW lab_v319_mv_monthly_paid AS
SELECT
    date_trunc('month', order_date)::date AS month_start,
    region,
    COUNT(*) AS paid_orders,
    SUM(gross_amount) AS paid_revenue
FROM lab_v319_orders
WHERE order_status = 'PAID'
GROUP BY date_trunc('month', order_date)::date, region
WITH DATA;
~~~

Đọc kết quả lưu sẵn:

~~~sql
SELECT month_start, region, paid_orders, paid_revenue
FROM lab_v319_mv_monthly_paid
ORDER BY month_start, region;
~~~

Vừa tạo xong trên dữ liệu ban đầu, materialized view có **5 hàng**:

| month_start | region | paid_orders | paid_revenue |
| --- | --- | ---: | ---: |
| 2026-09-01 | NORTH | 3 | 410000.00 |
| 2026-09-01 | SOUTH | 1 | 80000.00 |
| 2026-10-01 | NORTH | 2 | 280000.00 |
| 2026-10-01 | SOUTH | 3 | 240000.00 |
| 2026-11-01 | NORTH | 1 | 95000.00 |

### 12.2. Vì sao gọi là “vật chất hóa”?

Kết quả của truy vấn được **lưu thành những hàng dữ liệu**. Khi chạy `SELECT` trên materialized view, PostgreSQL có thể đọc các hàng đã lưu mà **không tính lại toàn bộ phép GROUP BY trên bảng nguồn** ở mỗi lần đọc.

Đó là lợi ích đối với:

- Dashboard được đọc nhiều lần trong ngày.
- Báo cáo tổng hợp nhiều bảng tốn kém.
- Tập kết quả không cần độ mới tuyệt đối theo từng giao dịch.
- Truy vấn có thể tận dụng **index riêng trên materialized view**.

Đánh đổi là kết quả **có thể cũ** và việc làm mới có chi phí. PostgreSQL materialized view không phải một “view thường chạy nhanh hơn mà vẫn cập nhật tự động”.

## 13. VIEW thấy dữ liệu mới, MATERIALIZED VIEW có thể còn dữ liệu cũ

Thử cùng lúc trên bảng nguồn, view thường và materialized view. Thực hiện khi cả hai đối tượng ở mục 11–12 đã được tạo thành công và chưa có thay đổi trước đó.

### 13.1. Sửa một đơn trong transaction thử nghiệm

~~~sql
BEGIN;

UPDATE lab_v319_orders
SET gross_amount = 65000.00
WHERE order_id = 1007
  AND gross_amount = 60000.00;

-- (1) Truy van truc tiep du lieu nguon thang 10, SOUTH:
SELECT SUM(gross_amount) AS live_revenue
FROM lab_v319_orders
WHERE order_status = 'PAID'
  AND region = 'SOUTH'
  AND order_date >= DATE '2026-10-01'
  AND order_date < DATE '2026-11-01';

-- (2) Doc VIEW thuong:
SELECT paid_revenue AS view_revenue
FROM lab_v319_v_monthly_paid
WHERE month_start = DATE '2026-10-01'
  AND region = 'SOUTH';

-- (3) Doc MATERIALIZED VIEW:
SELECT paid_revenue AS mv_revenue_before_refresh
FROM lab_v319_mv_monthly_paid
WHERE month_start = DATE '2026-10-01'
  AND region = 'SOUTH';

ROLLBACK;
~~~

Trong **cùng transaction**, câu `UPDATE` đổi tạm số tiền đơn 1007 từ **60000** lên **65000**:

| Nguồn đọc | Doanh thu SOUTH tháng 10 |
| --- | ---: |
| Tổng trực tiếp từ `orders` | **245000.00** |
| View thường | **245000.00** |
| Materialized view chưa refresh | **240000.00** |

Điều này minh họa **độ mới dữ liệu**: trong cùng transaction, `VIEW` tính từ bảng nguồn đã sửa; `MATERIALIZED VIEW` vẫn chứa snapshot đã vật chất hóa trước đó. Sau `ROLLBACK`, dữ liệu `orders` trở về 60000, kết quả view thường trở lại 240000.

### 13.2. Refresh materialized view

Nếu một thay đổi nguồn được **commit**, materialized view vẫn giữ kết quả cũ cho tới khi refresh:

~~~sql
REFRESH MATERIALIZED VIEW lab_v319_mv_monthly_paid;
~~~

Lệnh này tính lại và thay dữ liệu vật chất hóa theo truy vấn định nghĩa. Trong PostgreSQL, một lệnh refresh thông thường là thao tác **ghi dữ liệu** của materialized view, không phải SELECT chỉ đọc.

Để **thử refresh mà không giữ thay đổi**, ta có thể đặt cả thay đổi nguồn và refresh vào một transaction rồi rollback:

~~~sql
BEGIN;

UPDATE lab_v319_orders
SET gross_amount = 65000.00
WHERE order_id = 1007
  AND gross_amount = 60000.00;

REFRESH MATERIALIZED VIEW lab_v319_mv_monthly_paid;

SELECT paid_revenue
FROM lab_v319_mv_monthly_paid
WHERE month_start = DATE '2026-10-01'
  AND region = 'SOUTH';

ROLLBACK;
~~~

Trong transaction thử, kết quả sau refresh là **245000.00**. Khi rollback, PostgreSQL hoàn tác cả việc sửa `orders` và việc refresh đã thực hiện trong transaction, nên các đối tượng trở về trạng thái ban đầu.

**Ghi chú:** hành vi giao dịch nêu trên là đặc điểm của PostgreSQL. Không suy ra rằng mọi SQL dialect thực thi refresh và DDL giống nhau.

### 13.3. REFRESH không đồng nghĩa tự cập nhật liên tục

PostgreSQL **không tự refresh materialized view sau mỗi INSERT/UPDATE/DELETE ở bảng nguồn** theo mặc định. Cần có một lịch chạy hoặc quy trình gọi `REFRESH MATERIALIZED VIEW`:

~~~text
09:00   REFRESH MV -> ket qua tinh den snapshot tai lan refresh
09:05   INSERT them don hang PAID vao bang nguon
09:06   SELECT tu MV -> chua co don moi
09:10   REFRESH MV -> ket qua duoc tinh lai
09:11   SELECT tu MV -> doc snapshot moi
~~~

Thời điểm cập nhật tự động nếu có phải do **job scheduler, ứng dụng hoặc hệ thống điều phối** được cấu hình; nó không phát sinh chỉ vì đối tượng được đặt tên là materialized view.

## 14. REFRESH MATERIALIZED VIEW CONCURRENTLY

Trong PostgreSQL:

~~~sql
REFRESH MATERIALIZED VIEW lab_v319_mv_monthly_paid;
~~~

là dạng refresh thông thường. Trong thời gian chạy, hoạt động đọc đối tượng có thể bị **chặn bởi khóa phù hợp**. Với dashboard được nhiều người dùng truy vấn, việc refresh gây gián đoạn đọc có thể là vấn đề.

PostgreSQL có thêm:

~~~sql
REFRESH MATERIALIZED VIEW CONCURRENTLY lab_v319_mv_monthly_paid;
~~~

Mục tiêu là cho phép **các truy vấn SELECT khác vẫn có thể truy cập materialized view trong khi refresh** theo cơ chế đồng thời của PostgreSQL. Đây **không** có nghĩa việc refresh trở nên miễn phí, không dùng khóa, luôn nhanh hơn hoặc tự động cập nhật từng hàng tức thời.

### 14.1. Điều kiện về unique index

Để dùng `CONCURRENTLY` trên một materialized view PostgreSQL, đối tượng phải:

1. **Đã được nạp dữ liệu** (*populated*).
2. Có ít nhất một **unique index** phù hợp, sử dụng **chỉ tên cột**, bao phủ **mọi hàng**; không phải chỉ mục duy nhất dạng biểu thức hay partial index có `WHERE`.
3. Không có một refresh khác của **cùng materialized view** đang chạy theo cách bị PostgreSQL cấm.

Với kết quả doanh số, mỗi cặp `(month_start, region)` đại diện một nhóm duy nhất, nên có thể tạo:

~~~sql
CREATE UNIQUE INDEX lab_v319_mv_month_region_uidx
ON lab_v319_mv_monthly_paid (month_start, region);
~~~

Sau đó có thể chạy:

~~~sql
REFRESH MATERIALIZED VIEW CONCURRENTLY lab_v319_mv_monthly_paid;
~~~

**Cẩn trọng:** chỉ tạo unique index trên tập cột thực sự **duy nhất theo định nghĩa kết quả**. Nếu view có nhiều hàng cùng tháng/vùng vì thiếu chiều phân nhóm trong khóa, tạo index sẽ thất bại hoặc khóa không phản ánh đúng tập dữ liệu.

### 14.2. Vì sao index expression/partial không đủ?

Ví dụ sau **không thỏa yêu cầu unique index cho concurrent refresh** của PostgreSQL, dù có thể là một index hữu ích cho truy vấn khác:

~~~sql
-- Chi la vi du ve index KHONG du dieu kien CONCURRENTLY:
-- CREATE UNIQUE INDEX ... ON mv (month_start) WHERE region = 'NORTH';
-- CREATE UNIQUE INDEX ... ON mv ((date_trunc('year', month_start)));
~~~

Một index partial chỉ bao phủ một phần hàng, còn index biểu thức không phải unique index trên **danh sách cột đơn thuần** theo điều kiện PostgreSQL yêu cầu cho `REFRESH ... CONCURRENTLY`. Trong bài này dùng chỉ mục trực tiếp trên `(month_start, region)`, không có điều kiện `WHERE`.

### 14.3. WITH NO DATA và lần refresh đầu

Nếu tạo:

~~~sql
CREATE MATERIALIZED VIEW lab_v319_mv_unpopulated AS
SELECT order_id, gross_amount
FROM lab_v319_orders
WITH NO DATA;
~~~

đối tượng đã có định nghĩa nhưng **chưa populated**. Bạn không thể truy vấn dữ liệu của nó như một MV sẵn sàng và không thể chọn `CONCURRENTLY` cho **lần nạp đầu** chỉ vì đã tạo một unique index.

Cách nạp lần đầu:

~~~sql
REFRESH MATERIALIZED VIEW lab_v319_mv_unpopulated WITH DATA;

SELECT COUNT(*) AS rows_in_mv
FROM lab_v319_mv_unpopulated;
~~~

Kết quả là **12** khi dữ liệu nguồn vẫn ban đầu. Nếu muốn dùng concurrent refresh ở các lần sau, còn phải tạo **unique index thích hợp**, ví dụ trên `order_id`:

~~~sql
CREATE UNIQUE INDEX lab_v319_mv_unpopulated_order_uidx
ON lab_v319_mv_unpopulated (order_id);
~~~

Kết thúc ví dụ:

~~~sql
DROP MATERIALIZED VIEW lab_v319_mv_unpopulated;
~~~

### 14.4. Giới hạn thực tế của CONCURRENTLY

- Vẫn phải **tính lại truy vấn nguồn** và xử lý kết quả mới.
- Vẫn sử dụng tài nguyên CPU, I/O, bộ nhớ, temp files và cơ chế khóa cần thiết.
- Thường không có lợi khi materialized view rất nhỏ hoặc dữ liệu nguồn truy vấn đơn giản; cần đo thực tế.
- Hai lệnh refresh đồng thời trên **cùng một MV** không được phép tự do chạy song song như hai `SELECT`.
- Thứ tự hàng sau refresh **không được bảo đảm**; vẫn phải dùng `ORDER BY` khi đọc kết quả.

**Hãy chọn CONCURRENTLY để giảm tác động chặn người đọc khi cần**, không phải vì chữ này tự bảo đảm tốc độ nhanh hơn.

## 15. Chỉ mục và truy vấn trên materialized view

Vì materialized view PostgreSQL có dữ liệu lưu riêng, có thể tạo index trên **các cột kết quả**:

~~~sql
CREATE INDEX lab_v319_mv_region_idx
ON lab_v319_mv_monthly_paid (region);
~~~

Ví dụ:

~~~sql
SELECT
    month_start,
    paid_orders,
    paid_revenue
FROM lab_v319_mv_monthly_paid
WHERE region = 'SOUTH'
ORDER BY month_start;
~~~

Trên năm hàng ví dụ, index bổ sung có thể **không có lợi** vì bảng quá nhỏ. Trên materialized view hàng triệu dòng, index có thể giúp nhiều truy vấn lọc/sắp xếp, nhưng cũng tiêu tốn dung lượng và chi phí duy trì khi refresh.

### 15.1. MV không có nghĩa làm mọi truy vấn nhanh

Hiệu quả phụ thuộc:

- Truy vấn nguồn tốn bao nhiêu chi phí?
- Materialized view có giảm đáng kể số hàng/cột cần đọc không?
- Người dùng có truy vấn lặp lại theo các điều kiện mà MV đã chuẩn bị không?
- Kết quả lưu sẵn có phù hợp **độ hạt** của báo cáo cần đọc không?
- Chi phí refresh có lớn hơn tổng chi phí tiết kiệm khi đọc không?

Ví dụ, một materialized view **chỉ tổng hợp theo tháng/vùng** không giúp truy vấn cần **chi tiết từng đơn hàng theo khách** nếu nó đã loại bỏ `order_id` và `customer_id`. Không thể từ năm dòng tổng hợp khôi phục chính xác toàn bộ mười đơn PAID.

### 15.2. Làm mới không bảo đảm giữ thứ tự vật lý

Ngay cả khi truy vấn định nghĩa MV có `ORDER BY`, PostgreSQL không bảo đảm refresh duy trì thứ tự hàng trên lưu trữ hay kết quả SELECT. Viết:

~~~sql
SELECT month_start, region, paid_revenue
FROM lab_v319_mv_monthly_paid
ORDER BY month_start, region;
~~~

thay vì tin vào thứ tự xuất hiện sau `CREATE MATERIALIZED VIEW` hoặc `REFRESH`.

## 16. Tính mới dữ liệu: chấp nhận trễ bao nhiêu?

Giả sử dashboard cập nhật doanh thu:

| Yêu cầu nghiệp vụ | Giải pháp đáng cân nhắc |
| --- | --- |
| Mỗi truy vấn phải nhìn dữ liệu mới nhất theo snapshot/transaction | View thường hoặc truy vấn trực tiếp nguồn |
| Chỉ cần cập nhật mỗi giờ | Materialized view với lịch refresh phù hợp |
| Cần báo cáo rất nhanh và có pipeline ETL sẵn | Bảng tổng hợp thường trực, quản lý theo batch và watermark |
| Cần thao tác thử với tập dữ liệu trong một session | TEMP TABLE |
| Cần chuẩn hóa nhiều bước, ghi log lỗi và retry theo lô | Bảng staging thường trực |

### 16.1. Freshness và consistency không giống nhau

Một materialized view được refresh lúc 10:00 có thể **nhất quán với một snapshot nguồn**, nhưng đến 10:05 đã **cũ** so với bảng gốc. Ngược lại, đọc nhiều bảng nguồn bằng các statement riêng ở `READ COMMITTED` có thể thấy **các snapshot khác nhau** giữa những câu lệnh, dù dữ liệu được đọc rất mới.

Hãy hỏi rõ:

1. Báo cáo được phép trễ **bao nhiêu phút/giờ**?
2. Các bảng liên quan phải phản ánh **cùng một mốc dữ liệu** không?
3. Có cần “đúng đến cuối ngày đã khóa sổ”, hay phải gần thời gian thực?
4. Nếu refresh thất bại, hệ thống cho phép tiếp tục hiển thị snapshot cũ trong bao lâu?
5. Có cần hiển thị **mốc refresh/watermark** để người xem hiểu độ trễ?

### 16.2. Đừng chỉ dùng thời gian chạy job làm mốc dữ liệu nguồn

Một cột `computed_at` cho biết khi kết quả được tính, nhưng **không tự chứng minh** tất cả nguồn đều đã cập nhật tới cùng timestamp. Trong pipeline ETL có nhiều nguồn bất đồng bộ, có thể cần **source_watermark**, phiên bản lô, ID sự kiện hoặc ngày khóa sổ để mô tả mức bao phủ dữ liệu.

Đối với materialized view PostgreSQL, nếu cần biết refresh thành công lúc nào, nên có **quy trình logging** đi kèm. Không đoán rằng MV mặc định luôn có trường `last_refreshed_at`. Trong môi trường học, một cột `CURRENT_TIMESTAMP` thêm vào truy vấn MV có thể chỉ cho biết thời điểm giao dịch thực thi, không giải quyết toàn bộ bài toán watermark của pipeline thực.

## 17. Mối quan hệ với transaction và đồng thời

### 17.1. TEMP TABLE và rollback

TEMP TABLE vẫn chịu các quy tắc transaction PostgreSQL. `INSERT`/`UPDATE` trên bảng tạm có thể rollback. DDL tạo bảng tạm trong transaction cũng có thể rollback. `ON COMMIT` tác động **tại commit**, không phải cứ kết thúc một câu lệnh là xóa hàng.

### 17.2. Staging thường trực trong nhiều phiên

Bảng staging có thể được nhiều session đọc hoặc ghi nếu có quyền. Khi hai worker cùng xử lý `batch_id = 42`, chúng cần cơ chế **claim batch, unique key, transaction và xử lý retry**, không chỉ dựa vào tên bảng.

Một cột trạng thái batch có thể giúp biết lô nào đang PROCESSING, DONE hay FAILED, nhưng **gán trạng thái không tự bảo đảm hai worker không tranh nhau**. Thiết kế thực tế cần cập nhật có điều kiện, khóa phù hợp hoặc hàng đợi điều phối.

### 17.3. MV refresh và dữ liệu nguồn đang thay đổi

Refresh là một thao tác có snapshot/giao dịch. Nếu nguồn bị sửa liên tục, kết quả refresh phản ánh **dữ liệu mà truy vấn refresh quan sát theo quy tắc cô lập áp dụng**, không phải một phép tổng cộng “liên tục cập nhật mọi thay đổi đến từng microsecond”.

Với PostgreSQL, một MV được refresh không tự sửa các bảng nguồn. Nó thay đổi **kết quả đã lưu trong chính MV**. Nếu cần các bảng phân tích khác luôn cùng một version báo cáo, có thể phải điều phối **nhiều bước refresh** trong chiến lược giao dịch/triển khai phù hợp.

### 17.4. Rủi ro “full refresh” khi nhiều người đang đọc

Làm mới toàn bộ có thể tốn thời gian, dùng khóa và gây gián đoạn. Với PostgreSQL, `REFRESH ... CONCURRENTLY` giúp người đọc có thể tiếp tục truy vấn trong điều kiện cho phép; với bảng tổng hợp tự quản lý, một chiến lược khác là **nạp vào bảng phiên bản mới rồi chuyển điểm đọc** theo cách có kiểm soát.

Không dùng `TRUNCATE` bảng đang được dashboard đọc mà không đánh giá transaction, locking, quyền, phụ thuộc và trải nghiệm người dùng.

## 18. Bảng tạm, bảng trung gian và MV khác gì về tài nguyên?

| Khía cạnh | TEMP TABLE | Bảng staging/tổng hợp thường trực | MATERIALIZED VIEW |
| --- | --- | --- | --- |
| Dung lượng | Theo dữ liệu và lifetime session | Tồn tại cho đến khi xóa/dọn theo chính sách | Tồn tại đến khi DROP, thay nội dung khi refresh |
| Chi phí tạo/nạp | Tạo/nạp mỗi lần hoặc mỗi session | Theo batch/ETL | Tạo ban đầu và refresh |
| Đọc lại | Nhiều câu trong cùng session | Nhiều session, nhiều job | Nhiều session, nhiều truy vấn |
| Index | Tạo trên bảng tạm | Thiết kế như bảng thường | Có thể tạo trên MV PostgreSQL |
| Cập nhật khi nguồn đổi | Không tự đổi | Phải có ETL/ứng dụng | `REFRESH` trong PostgreSQL |
| Quyền truy cập | Đối tượng riêng session | Quyền bảng/schema rõ ràng | Quyền đối tượng MV |
| Giám sát lỗi | Ít phù hợp để lưu audit lâu dài | Hợp với batch log/quarantine | Cần theo dõi refresh và độ trễ |
| Thích hợp nhiều worker dùng chung | Không (session riêng) | Có nếu thiết kế đồng thời | Có cho workload đọc |

### 18.1. TEMP TABLE và UNLOGGED TABLE trong PostgreSQL không giống nhau

PostgreSQL còn có:

~~~sql
CREATE UNLOGGED TABLE ten_bang (
    id INTEGER,
    value NUMERIC
);
~~~

**UNLOGGED TABLE không phải TEMP TABLE**:

- UNLOGGED TABLE là **đối tượng thường trực**, các session có quyền có thể truy cập; nó không tự xóa khi session tạo kết thúc.
- Dữ liệu UNLOGGED bỏ qua một số cơ chế ghi WAL cho nội dung bảng, có thể giảm chi phí ghi nhưng **không có bảo đảm crash safety như bảng logged**, có thể bị truncate sau crash hoặc shutdown không sạch.
- Nội dung UNLOGGED không được replicate theo cơ chế streaming replication thông thường của PostgreSQL.

Vì vậy không đổi một bảng staging quan trọng thành UNLOGGED chỉ vì nó mang tên “trung gian”; phải chấp nhận được **mất dữ liệu khi sự cố** và mô hình phục hồi.

### 18.2. “Materialization” trong execution plan khác “MATERIALIZED VIEW”

Khi xem `EXPLAIN`, PostgreSQL có thể xuất hiện bước `Materialize` hoặc cơ chế tuplestore/spool ở một truy vấn. Đó là **kỹ thuật bên trong kế hoạch thực thi**, có thể tạo vùng giữ kết quả tạm để phục vụ những bước khác của **câu SQL hiện tại**.

Nó **không** tương đương một đối tượng `CREATE MATERIALIZED VIEW ...` bền vững mà người dùng truy vấn qua tên. Không nên đọc tên nút kế hoạch rồi kết luận cơ sở dữ liệu đã tự tạo materialized view dùng lại cho các lần chạy sau.

## 19. Chọn công cụ đúng theo câu hỏi nghiệp vụ

### Trường hợp A — Một báo cáo một lần, không cần lưu kết quả

**Đề xuất:** CTE hoặc derived table:

~~~sql
WITH paid AS (
    SELECT region, gross_amount
    FROM lab_v319_orders
    WHERE order_status = 'PAID'
)
SELECT region, SUM(gross_amount) AS revenue
FROM paid
GROUP BY region;
~~~

Không cần tạo bảng tạm chỉ vì có bước lọc `paid`.

### Trường hợp B — Cùng tập lọc dùng trong năm phép phân tích của một session

**Đề xuất:** cân nhắc TEMP TABLE sau khi đánh giá chi phí:

~~~sql
CREATE TEMP TABLE lab_v319_tmp_reuse AS
SELECT order_id, customer_id, region, gross_amount
FROM lab_v319_orders
WHERE order_status = 'PAID';

SELECT COUNT(*) FROM lab_v319_tmp_reuse;
SELECT region, SUM(gross_amount)
FROM lab_v319_tmp_reuse
GROUP BY region;

DROP TABLE lab_v319_tmp_reuse;
~~~

Nó giúp dùng chung một snapshot đã nạp. Nhưng nếu dữ liệu nguồn được sửa trong lúc session vẫn còn, `lab_v319_tmp_reuse` **không tự nhận thay đổi**.

### Trường hợp C — Nhập dữ liệu từ API, cần kiểm tra lỗi và chạy lại lô

**Đề xuất:** bảng staging thường trực có `batch_id`, nguồn raw, trạng thái xử lý, bảng lỗi và chính sách dọn dữ liệu. TEMP TABLE riêng session không đủ nếu một worker nhập và worker khác kiểm tra/duyệt.

### Trường hợp D — Dashboard doanh thu truy vấn liên tục, chấp nhận trễ 15 phút

**Đề xuất:** materialized view hoặc bảng tổng hợp đã lưu, có job refresh định kỳ, giám sát lỗi và thông báo độ mới. PostgreSQL MV đòi hỏi explicit `REFRESH`; bảng tổng hợp thì cần pipeline tính lại/gia tăng.

### Trường hợp E — Hệ thống thanh toán cần số dư hiện hành chính xác

**Đề xuất:** không lấy một materialized view refresh mỗi giờ làm nguồn quyết định tiền có thể chi. Với nghiệp vụ yêu cầu **trạng thái giao dịch hiện tại**, hãy truy vấn bảng nghiệp vụ và xử lý transaction/khóa/ràng buộc phù hợp.

**Tốc độ báo cáo và tính chính xác giao dịch là hai mục tiêu khác nhau.** Một bản tổng hợp vật chất hóa có thể rất phù hợp cho dashboard nhưng không phù hợp để phê duyệt một thao tác tài chính tức thời.

## 20. Khác biệt giữa các SQL dialect

Tên khái niệm thường giống nhau, nhưng **phạm vi bảng tạm, thời điểm xóa hàng, cú pháp materialized view và cơ chế refresh** khác đáng kể. Không mang nguyên các lệnh PostgreSQL sang hệ khác.

### 20.1. PostgreSQL

Các cú pháp đã thực hành:

~~~sql
CREATE TEMP TABLE tmp AS SELECT ...;
CREATE TEMP TABLE tmp2 (...) ON COMMIT DELETE ROWS;
CREATE TABLE snapshot AS SELECT ...;
CREATE VIEW v AS SELECT ...;
CREATE MATERIALIZED VIEW mv AS SELECT ... WITH DATA;
REFRESH MATERIALIZED VIEW mv;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv;
~~~

Trong PostgreSQL, materialized view có thể tạo index trên dữ liệu đã lưu; `CONCURRENTLY` yêu cầu unique index đáp ứng điều kiện. Bảng tạm mặc định tồn tại trong session và giữ hàng qua commit.

### 20.2. MySQL

MySQL hỗ trợ `CREATE TEMPORARY TABLE` với phạm vi session:

~~~sql
-- MySQL minh hoa, gia dinh bang orders da ton tai.
CREATE TEMPORARY TABLE tmp_paid_orders AS
SELECT order_id, gross_amount
FROM orders
WHERE order_status = 'PAID';

SELECT COUNT(*) FROM tmp_paid_orders;

DROP TEMPORARY TABLE tmp_paid_orders;
~~~

**Không dùng nguyên `ON COMMIT DELETE ROWS` của PostgreSQL** rồi cho rằng MySQL TEMPORARY TABLE tự làm rỗng sau mỗi commit. Vòng đời và transaction/engine có quy tắc khác.

MySQL không có một đối tượng `CREATE MATERIALIZED VIEW` native tương đương PostgreSQL trong các phiên bản MySQL thông dụng. Nếu cần kết quả lưu sẵn, thường dùng **bảng tổng hợp thường trực**, job/scheduler và cơ chế cập nhật nguồn phù hợp.

### 20.3. SQL Server

SQL Server sử dụng **local temporary table** với tiền tố `#` và **global temporary table** với `##`, có vòng đời và phạm vi nhìn thấy riêng. Ví dụ T-SQL:

~~~sql
-- SQL Server/T-SQL minh hoa:
SELECT order_id, gross_amount
INTO #tmp_paid_orders
FROM dbo.Orders
WHERE order_status = 'PAID';

SELECT COUNT(*) FROM #tmp_paid_orders;

DROP TABLE #tmp_paid_orders;
~~~

`SELECT ... INTO #tmp_paid_orders` của SQL Server tạo bảng từ kết quả truy vấn, **không phải cú pháp PostgreSQL `CREATE TEMP TABLE ... AS`**. SQL Server còn có **table variable** như `DECLARE @t TABLE (...)`, nhưng hành vi tối ưu và phạm vi khác temporary table; không mặc định hai cách là một.

Để phục vụ truy vấn đã vật chất hóa, SQL Server có **indexed views** trong những điều kiện ràng buộc cụ thể (ví dụ schema binding, truy vấn được phép, index unique clustered ban đầu, yêu cầu SET options). Đây không phải bản sao cú pháp `CREATE MATERIALIZED VIEW ... REFRESH` của PostgreSQL: cơ chế duy trì indexed view gắn với thay đổi bảng nguồn và có chi phí ghi tương ứng.

### 20.4. Oracle Database

Oracle có **Global Temporary Table** (*GTT*). “Global” ở đây nói tới **định nghĩa bảng dùng chung**, không có nghĩa các session nhìn thấy **cùng dữ liệu tạm**. Nội dung GTT là riêng theo session/transaction theo cấu hình:

~~~sql
-- Oracle SQL minh hoa:
CREATE GLOBAL TEMPORARY TABLE tmp_paid_orders (
    order_id NUMBER,
    gross_amount NUMBER(12,2)
) ON COMMIT DELETE ROWS;
~~~

Hoặc:

~~~sql
CREATE GLOBAL TEMPORARY TABLE tmp_keep_rows (
    order_id NUMBER
) ON COMMIT PRESERVE ROWS;
~~~

Với Oracle GTT, **định nghĩa đối tượng có thể tồn tại lâu dài trong schema**, trong khi dữ liệu riêng của mỗi session hoặc transaction. Điều này **khác** PostgreSQL TEMP TABLE, nơi bản thân đối tượng tạm thông thường có vòng đời gắn session. Oracle còn có **private temporary tables** ở các phiên bản hỗ trợ, với cú pháp và vòng đời riêng.

Oracle hỗ trợ **materialized view** với các lựa chọn refresh phong phú, ví dụ `COMPLETE`, `FAST`, theo yêu cầu (*ON DEMAND*) hoặc theo commit (*ON COMMIT*) khi thỏa điều kiện. Khả năng **fast refresh** phụ thuộc cấu trúc truy vấn, materialized view logs và nhiều điều kiện khác; không phải truy vấn tùy ý nào cũng hỗ trợ mọi chế độ refresh.

### 20.5. SQLite

SQLite hỗ trợ bảng tạm:

~~~sql
-- SQLite minh hoa, gia dinh bang orders da ton tai.
CREATE TEMP TABLE tmp_paid_orders AS
SELECT order_id, gross_amount
FROM orders
WHERE order_status = 'PAID';

SELECT COUNT(*) FROM tmp_paid_orders;

DROP TABLE tmp_paid_orders;
~~~

Bảng `TEMP` nằm trong **temporary database gắn với connection**; không phải đối tượng chung để các connection cùng sửa/đọc. SQLite có `VIEW` và CTE, nhưng không có native `CREATE MATERIALIZED VIEW ... REFRESH` như PostgreSQL. Muốn kết quả lưu sẵn, thường phải dùng **bảng thường trực + quy trình làm mới**, hoặc trigger phù hợp theo thiết kế.

### 20.6. Bảng tổng kết dialect

| Hệ quản trị | Bảng tạm | Bảng trung gian bền vững | Kết quả vật chất hóa |
| --- | --- | --- | --- |
| **PostgreSQL** | `CREATE TEMP TABLE`; `ON COMMIT` | Bảng thường/`CREATE TABLE AS`, staging theo batch | Native materialized view, `REFRESH`, tùy chọn `CONCURRENTLY` |
| **MySQL** | `CREATE TEMPORARY TABLE` theo session | Bảng thường trực + ETL | Thường dựng bằng bảng tổng hợp do ứng dụng/job làm mới |
| **SQL Server** | `#temp`, `##temp`, table variables có quy tắc riêng | Bảng thường trực, `SELECT INTO` | Indexed view theo điều kiện; khác MV refresh thủ công PostgreSQL |
| **Oracle** | GTT và private temporary table theo phiên bản | Bảng staging/ETL thường trực | Native materialized views với nhiều kiểu refresh |
| **SQLite** | `CREATE TEMP TABLE` theo connection | Bảng thường trực/`CREATE TABLE AS` | Tự quản lý bảng tổng hợp/trigger, không có native MV PostgreSQL |

## 21. Hiệu năng: đừng vật chất hóa chỉ vì truy vấn dài

Chi phí tổng thể có thể hình dung:

~~~text
Chi phi truc tiep:
    so lan doc * chi phi truy van tren bang nguon

Chi phi vat chat hoa:
    chi phi tao/nap ban dau
  + chi phi refresh/duy tri
  + chi phi luu tru/index
  + so lan doc * chi phi doc ket qua da luu
~~~

Lựa chọn vật chất hóa hợp lý khi tổng chi phí **đọc lặp lại** tiết kiệm được đủ lớn để bù **ghi/refresh/lưu trữ**, và dữ liệu cũ giữa các lần refresh **được nghiệp vụ chấp nhận**.

### 21.1. Dùng EXPLAIN để hiểu truy vấn

~~~sql
EXPLAIN
SELECT
    date_trunc('month', order_date)::date AS month_start,
    region,
    SUM(gross_amount) AS revenue
FROM lab_v319_orders
WHERE order_status = 'PAID'
GROUP BY date_trunc('month', order_date)::date, region;
~~~

Hoặc:

~~~sql
EXPLAIN
SELECT month_start, region, paid_revenue
FROM lab_v319_mv_monthly_paid
WHERE month_start = DATE '2026-10-01';
~~~

`EXPLAIN` không `ANALYZE` chỉ cho biết **kế hoạch dự kiến**. Với truy vấn SELECT trong môi trường thực hành, `EXPLAIN ANALYZE` có thể hữu ích để đo thực tế, nhưng nó **thực thi truy vấn** và có thể tiêu thụ tài nguyên đáng kể khi dữ liệu lớn. Không dùng `EXPLAIN ANALYZE` với lệnh ghi/refresh trên dữ liệu thật rồi nghĩ rằng nó chỉ phân tích mà không thực thi.

### 21.2. Tránh lưu dữ liệu quá chi tiết

Nếu dashboard chỉ cần tổng theo tháng/vùng, materialized view năm dòng là đủ cho dữ liệu mẫu. Chép toàn bộ đơn hàng vào một bảng khác **không tạo ra nhiều lợi ích tổng hợp**; nó tăng dung lượng và rủi ro phải duy trì hai bản dữ liệu chi tiết.

Ngược lại, nếu báo cáo cần drill-down đến từng khách và đơn, một MV chỉ có tổng theo tháng/vùng **không đủ chiều dữ liệu**. Thiết kế độ hạt trước khi chọn nơi lưu.

### 21.3. Tránh làm mới thừa

Nếu nguồn chỉ thay đổi sau khi khóa sổ theo ngày, không nhất thiết refresh mỗi phút. Nếu nguồn có cập nhật liên tục mà dashboard chỉ chấp nhận trễ 5 phút, lịch refresh mỗi ngày không phù hợp.

Thiết kế tần suất refresh từ **SLA về độ mới** và chi phí, không từ sở thích kỹ thuật.

## 22. Bảo mật, quyền và dữ liệu nhạy cảm

Bảng tạm, bảng staging và materialized view đều có thể **chứa bản sao dữ liệu quan trọng**. Những câu hỏi vận hành cần xem xét:

- Đối tượng trung gian có lưu thông tin khách hàng, mã định danh hoặc dữ liệu cần bảo vệ không?
- Các role được phép đọc bảng nguồn có tự động được cấp quyền đọc bảng trung gian hoặc MV không? **Không được giả định quyền giống hệt nhau**; cần quản lý quyền đối tượng cụ thể.
- Khi tạo MV/bảng tổng hợp, người dùng truy vấn sẽ nhìn thấy **dữ liệu tổng hợp** hay **chi tiết nhạy cảm**?
- Có lịch xóa staging sau khi hết thời hạn lưu trữ không?
- Khi refresh thất bại, hệ thống có cảnh báo hoặc tiếp tục hiển thị snapshot cũ mà không ghi rõ độ mới?
- Dữ liệu tạm có thể để lại tài nguyên cho connection pool nếu session không được reset không?

Một bảng staging thường trực có thể hữu ích cho audit, nhưng giữ vô thời hạn dữ liệu thô không cần thiết làm tăng rủi ro và chi phí. Phạm vi truy cập, vòng đời và chính sách lưu trữ là **một phần của thiết kế**, không chỉ là lệnh `CREATE TABLE`.

## 23. Những lỗi thường gặp

| Cách hiểu/cách làm | Vấn đề | Cách sửa |
| --- | --- | --- |
| “CTE là một bảng tạm được tạo trong database” | CTE không tự tạo đối tượng schema dùng lại qua nhiều câu lệnh | Dùng CTE cho một statement, TEMP TABLE khi cần lưu qua nhiều câu |
| “MATERIALIZED CTE giống MATERIALIZED VIEW” | Một cái là gợi ý/thực thi statement, một cái là đối tượng lưu kết quả | Phân biệt thời gian sống và khả năng refresh |
| “TEMP TABLE sẽ mất ngay sau SELECT” | Mặc định PostgreSQL giữ qua commit trong cùng session | Hiểu `ON COMMIT` và vòng đời session |
| “TEMP TABLE luôn tồn tại qua COMMIT” | `ON COMMIT DELETE ROWS`/`DROP` có hành vi khác | Chọn chính sách đúng |
| Chạy autocommit với `ON COMMIT DELETE ROWS` rồi truy vấn ở statement sau | Dữ liệu đã bị xóa khi statement nhập commit | Dùng transaction phù hợp hoặc PRESERVE ROWS |
| Tạo TEMP TABLE ở connection A, đọc ở connection B | Session khác không thấy cùng bảng tạm | Dùng bảng thường trực cho dữ liệu chia sẻ |
| Quên dọn bảng tạm trong pool | Có thể còn đối tượng/dữ liệu khi reuse connection | Reset session, drop rõ ràng |
| Tạo TEMP TABLE trùng tên bảng production | Có thể che khuất đối tượng thường trực | Đặt tên riêng, schema-qualified query |
| Cho rằng CTAS sao chép mọi constraint/index | CTAS lấy kết quả và kiểu suy ra, không nhân bản đầy đủ DDL nguồn | Tạo khóa/index/constraint cần thiết riêng |
| Dùng bảng staging không có batch_id | Dễ trộn nhiều lần nhập và khó retry/audit | Gắn mã lô, khóa dòng, trạng thái quy trình |
| `SELECT DISTINCT *` để “xử lý mọi dữ liệu trùng” | Không xử lý xung đột cùng khóa nghiệp vụ khác thuộc tính | Kiểm tra theo khóa và quy tắc nguồn |
| “VIEW thường lưu sẵn hàng tổng hợp” | View thường lưu định nghĩa | Dùng MV hoặc bảng tổng hợp nếu cần lưu hàng |
| “MATERIALIZED VIEW tự cập nhật khi bảng gốc đổi” | PostgreSQL MV cần REFRESH | Thiết kế lịch refresh và giám sát độ trễ |
| Tạo MV `WITH NO DATA` rồi SELECT ngay | MV chưa populated, không đọc được như dữ liệu sẵn | `REFRESH ... WITH DATA` trước |
| `REFRESH ... CONCURRENTLY` khi chưa có unique index thích hợp | PostgreSQL từ chối | Tạo unique index cột đơn thuần, bao phủ toàn bộ hàng |
| Cho rằng CONCURRENTLY luôn nhanh hơn | Vẫn phải tính nguồn, ghi và đối chiếu dữ liệu | Đo thực tế, chỉ chọn khi cần giảm chặn người đọc |
| Sau REFRESH tin rằng kết quả luôn có thứ tự | MV không bảo đảm thứ tự lưu/trả | `ORDER BY` ở SELECT cuối |
| Refresh bảng tổng hợp bằng upsert nhưng không xóa khóa đã biến mất | Dòng cũ có thể tồn tại mãi | Làm mới đủ tập khóa theo kỳ/batch |
| Dùng MV trễ một giờ để quyết định thanh toán tức thời | Dữ liệu không đủ mới cho nghiệp vụ giao dịch | Đọc dữ liệu giao dịch và thiết kế transaction đúng |
| Tạo quá nhiều index trên bảng tạm rất nhỏ | Chi phí tạo index cao hơn lợi ích | Đo và chọn index theo truy vấn |
| Coi UNLOGGED là TEMP | UNLOGGED dùng chung, bền đối tượng nhưng không crash-safe như logged | Chọn theo yêu cầu mất dữ liệu/replication |
| Mang `CREATE MATERIALIZED VIEW` PostgreSQL sang MySQL/SQLite | Không có cùng native feature/cú pháp | Dùng bảng tổng hợp và cơ chế refresh tự quản |
| Nhầm GTT của Oracle với TEMP TABLE PostgreSQL | Oracle GTT có định nghĩa chung, dữ liệu riêng | Đọc đúng quy tắc dialect |

## 24. Bài tập thực hành có đáp án

Các bài dựa trên `lab_v319_orders`. Các đối tượng trung gian được đặt tên khác nhau để tránh xung đột. Nếu chạy lại một đoạn `CREATE TABLE`/`CREATE VIEW` mà đối tượng đã tồn tại, hãy **dọn đúng đối tượng của bài** hoặc tạo trong database thực hành mới; không dùng `DROP CASCADE` tùy tiện lên đối tượng khác.

### Bài 1 — Chọn CTE hay TEMP TABLE?

**Yêu cầu:** chỉ cần tính doanh thu PAID tháng 10 một lần theo vùng. Có nhất thiết tạo TEMP TABLE không?

**Đáp án:** không. Một CTE là đủ:

~~~sql
WITH paid_oct AS (
    SELECT region, gross_amount
    FROM lab_v319_orders
    WHERE order_status = 'PAID'
      AND order_date >= DATE '2026-10-01'
      AND order_date < DATE '2026-11-01'
)
SELECT region, SUM(gross_amount) AS revenue
FROM paid_oct
GROUP BY region
ORDER BY region;
~~~

Kết quả **NORTH = 280000**, **SOUTH = 240000**. CTE không tạo bảng lưu bền vững.

### Bài 2 — Tạo TEMP TABLE từ kết quả SELECT

**Yêu cầu:** nạp các đơn PAID tháng 9 vào bảng tạm `lab_v319_ex_tmp_sep`, rồi đếm số hàng.

**Đáp án:**

~~~sql
CREATE TEMP TABLE lab_v319_ex_tmp_sep AS
SELECT order_id, region, gross_amount
FROM lab_v319_orders
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-09-01'
  AND order_date < DATE '2026-10-01';

SELECT COUNT(*) AS paid_sep_orders
FROM lab_v319_ex_tmp_sep;

DROP TABLE lab_v319_ex_tmp_sep;
~~~

Kết quả đếm **4**. Đơn CANCELLED 1004 không được nạp.

### Bài 3 — Sau COMMIT, bảng tạm còn không?

**Yêu cầu:** dự đoán trạng thái bảng sau:

~~~sql
BEGIN;
CREATE TEMP TABLE lab_v319_ex_keep (
    id INTEGER
) ON COMMIT PRESERVE ROWS;
INSERT INTO lab_v319_ex_keep VALUES (1);
COMMIT;
~~~

**Đáp án:** trong cùng session, bảng còn và có **một hàng**. Nếu connection/session kết thúc, bảng tạm không còn. Có thể dọn bằng:

~~~sql
DROP TABLE lab_v319_ex_keep;
~~~

### Bài 4 — Phân biệt DELETE ROWS và DROP

**Câu hỏi:** với `ON COMMIT DELETE ROWS` và `ON COMMIT DROP`, sau `COMMIT` có gì khác?

**Đáp án:** `DELETE ROWS` giữ **đối tượng bảng** nhưng **xóa hết hàng**; `DROP` xóa **cả đối tượng bảng**. Đây là hành vi PostgreSQL tại mốc commit, khác `ROLLBACK` của transaction đã tạo bảng.

### Bài 5 — Hai session có dùng chung một TEMP TABLE không?

**Tình huống:** A tạo `CREATE TEMP TABLE t AS SELECT ...`; B chạy `SELECT * FROM t` nhưng không có đối tượng tên t của riêng B.

**Đáp án:** **không**. TEMP TABLE của PostgreSQL thuộc session A, không tự chia sẻ sang B. Nếu hai worker cần xem cùng dữ liệu trung gian, hãy dùng bảng thường trực có khóa batch và quyền thích hợp.

### Bài 6 — Tạo CTAS, rồi suy luận về cập nhật nguồn

**Yêu cầu:** chụp tổng PAID theo vùng vào bảng thường trực và giải thích bảng có tự đổi khi orders được sửa không.

**Đáp án:**

~~~sql
CREATE TABLE lab_v319_ex_snapshot AS
SELECT region, SUM(gross_amount) AS revenue
FROM lab_v319_orders
WHERE order_status = 'PAID'
GROUP BY region;

SELECT region, revenue
FROM lab_v319_ex_snapshot
ORDER BY region;

DROP TABLE lab_v319_ex_snapshot;
~~~

Với dữ liệu ban đầu, **NORTH = 785000** (410000 + 280000 + 95000) và **SOUTH = 320000** (80000 + 240000). Đây là **bảng lưu kết quả tại thời điểm CTAS**, không tự cập nhật nếu bảng orders thay đổi về sau.

### Bài 7 — Thiết kế bảng staging để nhập nhiều lô

**Yêu cầu:** cần lưu dữ liệu thô từ đối tác, cho phép xem lỗi của lô 42 và thử lại sau một ngày. Nên dùng TEMP TABLE hay bảng staging thường trực? Khóa gì?

**Đáp án:** bảng staging **thường trực**, ví dụ `lab_v319_import_stage` với khóa **`PRIMARY KEY(batch_id, row_no)`**. Nó sống qua nhiều session, cho phép truy vết, kiểm tra số hàng, trạng thái và retry theo batch. Cần thêm ràng buộc dữ liệu nguồn/kiểm tra trùng mã nghiệp vụ trước khi nhập vào bảng chính.

### Bài 8 — Tìm mã đơn nhập trùng

**Yêu cầu:** trong `lab_v319_import_stage`, tìm mã đơn xuất hiện hơn một lần trong batch 42.

**Đáp án:**

~~~sql
SELECT external_order_code, COUNT(*) AS occurrences
FROM lab_v319_import_stage
WHERE batch_id = 42
  AND external_order_code IS NOT NULL
GROUP BY external_order_code
HAVING COUNT(*) > 1
ORDER BY external_order_code;
~~~

Kết quả **EXT-002 = 2**. Đây là kiểm tra trùng **theo khóa nghiệp vụ**, không phải loại những hàng có toàn bộ cột giống nhau bằng `DISTINCT *`.

### Bài 9 — VIEW thường và dữ liệu mới

**Yêu cầu:** tạo view doanh số PAID theo vùng. Nếu một giao dịch mới được commit vào bảng orders, view có cần REFRESH không?

**Đáp án:**

~~~sql
CREATE VIEW lab_v319_ex_view AS
SELECT region, SUM(gross_amount) AS revenue
FROM lab_v319_orders
WHERE order_status = 'PAID'
GROUP BY region;

SELECT region, revenue
FROM lab_v319_ex_view
ORDER BY region;

DROP VIEW lab_v319_ex_view;
~~~

PostgreSQL view thường **không cần REFRESH** vì nó lưu định nghĩa truy vấn và khi đọc sẽ tính theo snapshot dữ liệu nguồn thích hợp. Nó không có dữ liệu tổng hợp được lưu bền vững riêng.

### Bài 10 — Tạo materialized view đơn giản

**Yêu cầu:** tạo MV số đơn PAID theo vùng và đọc kết quả.

**Đáp án:**

~~~sql
CREATE MATERIALIZED VIEW lab_v319_ex_mv_region AS
SELECT
    region,
    COUNT(*) AS paid_orders,
    SUM(gross_amount) AS revenue
FROM lab_v319_orders
WHERE order_status = 'PAID'
GROUP BY region
WITH DATA;

SELECT region, paid_orders, revenue
FROM lab_v319_ex_mv_region
ORDER BY region;
~~~

Kết quả ban đầu **NORTH: 6 đơn, 785000**; **SOUTH: 4 đơn, 320000**. Cần `REFRESH MATERIALIZED VIEW` nếu muốn MV tính lại sau khi nguồn thay đổi.

Kết thúc:

~~~sql
DROP MATERIALIZED VIEW lab_v319_ex_mv_region;
~~~

### Bài 11 — Tại sao WITH NO DATA chưa đọc được?

**Yêu cầu:** giải thích `WITH NO DATA` và cách để MV trở nên dùng được.

**Đáp án:**

~~~sql
CREATE MATERIALIZED VIEW lab_v319_ex_mv_empty AS
SELECT order_id, gross_amount
FROM lab_v319_orders
WITH NO DATA;

-- MV chua populated, khong SELECT du lieu ngay.
REFRESH MATERIALIZED VIEW lab_v319_ex_mv_empty WITH DATA;

SELECT COUNT(*) AS rows_after_refresh
FROM lab_v319_ex_mv_empty;

DROP MATERIALIZED VIEW lab_v319_ex_mv_empty;
~~~

Sau `REFRESH ... WITH DATA`, kết quả đếm **12** nếu dữ liệu mẫu chưa bị thay đổi. Trước lần nạp đầu, MV chưa thể truy vấn như một bảng có dữ liệu sẵn.

### Bài 12 — Điều kiện để REFRESH CONCURRENTLY

**Yêu cầu:** MV `lab_v319_mv_monthly_paid` có một hàng cho mỗi `month_start, region`. Chuẩn bị gì để dùng `REFRESH ... CONCURRENTLY`?

**Đáp án:**

~~~sql
CREATE UNIQUE INDEX lab_v319_mv_month_region_uidx
ON lab_v319_mv_monthly_paid (month_start, region);

REFRESH MATERIALIZED VIEW CONCURRENTLY lab_v319_mv_monthly_paid;
~~~

Đối tượng phải **đã populated** và có unique index phù hợp, dựa vào cột, bao phủ mọi hàng, không phải partial/expression unique index. `CONCURRENTLY` giúp người đọc tiếp tục truy vấn, không có nghĩa dữ liệu tự cập nhật hay refresh luôn nhanh hơn.

Nếu index này đã được tạo ở mục 14, không chạy lại cùng `CREATE INDEX` nếu chưa xử lý tên đối tượng trùng.

### Bài 13 — Báo cáo được phép trễ 30 phút

**Tình huống:** dashboard chỉ cần số liệu tối đa trễ nửa giờ, nhưng mỗi lượt tính tổng trên bảng đơn hàng rất lớn.

**Đáp án:** cân nhắc **materialized view hoặc bảng tổng hợp vật chất hóa** được refresh theo lịch, ví dụ 15 phút/lần nếu chi phí cho phép; theo dõi mốc refresh thành công và lỗi. Không để dashboard hiểu nhầm số liệu là thời gian thực. Nếu phần truy vấn nguồn đủ nhanh, view thường vẫn có thể đơn giản và phù hợp hơn.

### Bài 14 — Tại sao upsert bảng tổng hợp có thể bỏ sót nhóm đã biến mất?

**Tình huống:** trước đây một vùng có doanh thu PAID, nhưng sau khi hoàn tiền, không còn đơn PAID nào trong kỳ. Một job chỉ chạy `INSERT ... SELECT GROUP BY ... ON CONFLICT DO UPDATE`.

**Đáp án:** nhóm đó **không còn xuất hiện trong kết quả `GROUP BY`**, nên không có hàng đề xuất chèn/cập nhật cho khóa cũ. Bảng tổng hợp thường trực có thể giữ lại số tiền **lỗi thời**. Cần định nghĩa tập khóa phải làm mới và xóa/đặt 0 cho nhóm biến mất, hoặc full rebuild theo kỳ trong transaction phù hợp.

### Bài 15 — Khi nào không nên materialize?

**Tình huống:** một câu SQL nhỏ tính số đơn PAID theo vùng chỉ chạy một lần, mất rất ít thời gian. Có nên tạo MV và job refresh?

**Đáp án:** thông thường **không cần**. `SELECT` với `GROUP BY` hoặc CTE có thể đủ. Materialized view thêm chi phí đối tượng, quyền, lưu trữ, index, refresh, giám sát và nguy cơ số liệu cũ. Chỉ đưa vào khi lợi ích đọc lặp lại/độ ổn định báo cáo xứng đáng.

## 25. Ghi nhớ

| Câu hỏi | Lựa chọn/kiến thức cần nhớ |
| --- | --- |
| Chỉ cần bước trung gian của một câu SQL? | **CTE** hoặc derived table |
| Cần giữ dữ liệu qua vài câu SQL trong cùng kết nối? | **TEMP TABLE** |
| Cần dữ liệu được chia sẻ giữa session/job và có batch audit? | **Bảng staging/trung gian thường trực** |
| Muốn chụp kết quả một lần thành bảng? | `CREATE TABLE ... AS SELECT` |
| Muốn đặt tên một truy vấn để lần đọc sau dùng dữ liệu nguồn hiện tại? | **VIEW thông thường** |
| Muốn lưu kết quả truy vấn để đọc lặp lại nhanh hơn? | **MATERIALIZED VIEW** hoặc bảng tổng hợp |
| Temp table PostgreSQL mặc định sau commit? | Giữ bảng và hàng (`PRESERVE ROWS`) |
| Temp chỉ giữ dữ liệu đến commit? | `ON COMMIT DELETE ROWS` |
| Temp bị xóa khi commit? | `ON COMMIT DROP` |
| MV PostgreSQL có tự theo cập nhật nguồn không? | **Không**; cần `REFRESH MATERIALIZED VIEW` |
| Cần cho phép SELECT đọc khi refresh MV? | Xem `REFRESH ... CONCURRENTLY` và unique index phù hợp |
| MV nạp bằng `WITH NO DATA` có đọc ngay không? | **Không**; nạp bằng `REFRESH ... WITH DATA` |
| CTAS có tự sao chép primary key/index nguồn? | **Không**; phải thiết kế ràng buộc/index riêng |
| Bảng staging có tự xóa theo session không? | **Không**, nếu là bảng thường trực |
| Các hệ quản trị có cùng cú pháp MV/temp không? | **Không**; luôn kiểm tra SQL dialect và phiên bản |

**Nguyên tắc tổng kết:** hãy bắt đầu từ **thời gian cần giữ kết quả**, **ai phải đọc được kết quả**, **độ mới dữ liệu được phép**, **khả năng kiểm tra/chạy lại** và **chi phí tạo–làm mới**. Dùng CTE khi chỉ cần đặt tên bước tính; TEMP TABLE khi cần dữ liệu trung gian riêng session; bảng staging khi cần quy trình bền vững nhiều bước; và materialized view khi lợi ích đọc lại kết quả đã lưu lớn hơn chi phí refresh. Điều quyết định không phải tên kỹ thuật nghe giống nhau, mà là **vòng đời và trách nhiệm duy trì tính đúng của dữ liệu**.
