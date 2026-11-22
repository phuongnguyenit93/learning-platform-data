# Chọn CTE, view hay bảng tạm theo phạm vi tái sử dụng

## 1. Cùng một logic SQL, vì sao có ba lựa chọn?

Giả sử bộ phận kinh doanh cần thống kê các đơn hàng đã thanh toán trong tháng 10/2026. Lúc đầu, một lập trình viên chỉ cần tính tổng tiền mỗi khách hàng để hiển thị một báo cáo. Sau đó, các yêu cầu xuất hiện thêm:

- Trang báo cáo thứ hai cũng cần biết đơn hàng nào đã thanh toán.
- Một tác vụ xử lý cần tính **ba báo cáo khác nhau** từ cùng tập kết quả trung gian trong một lần chạy.
- Nhiều người dùng, nhiều dịch vụ và nhiều phiên kết nối muốn dùng chung một **định nghĩa nghiệp vụ**.
- Có báo cáo quá tốn tài nguyên, muốn lưu kết quả và cập nhật theo lịch.

Những yêu cầu này có **phạm vi tái sử dụng** khác nhau. Ta không nên tự động biến mọi truy vấn con thành view, cũng không nên tạo bảng tạm cho một câu SELECT đơn giản.

Ba công cụ trọng tâm:

1. **CTE** (*Common Table Expression*, biểu thức bảng chung) — đặt tên cho một kết quả/truy vấn trung gian **trong phạm vi một câu lệnh SQL**.
2. **View** (*khung nhìn*) — lưu **định nghĩa truy vấn** trong lược đồ database, để những câu lệnh và phiên làm việc khác nhau sử dụng lại.
3. **Bảng tạm** (*temporary table*) — tạo **một bảng có dữ liệu và vòng đời giới hạn**, thường theo phiên kết nối hoặc giao dịch; thích hợp khi cần tái sử dụng kết quả **qua nhiều câu lệnh** của một tác vụ.

Hãy bắt đầu bằng câu hỏi **“Ai cần dùng lại cái gì, trong bao lâu?”**, rồi mới đánh giá hiệu năng, quyền truy cập, khả năng cập nhật và chi phí bảo trì.

### 1.1. Ví dụ ngắn nhất cho ba cách

**CTE: chỉ dùng trong câu lệnh chứa `WITH`.**

~~~sql
WITH paid_orders AS (
    SELECT customer_id, total_amount
    FROM orders
    WHERE order_status = 'PAID'
)
SELECT customer_id, SUM(total_amount) AS revenue
FROM paid_orders
GROUP BY customer_id;
~~~

**View: định nghĩa nằm trong database và có thể dùng lại.**

~~~sql
CREATE VIEW v_paid_orders AS
SELECT customer_id, total_amount
FROM orders
WHERE order_status = 'PAID';

SELECT customer_id, SUM(total_amount) AS revenue
FROM v_paid_orders
GROUP BY customer_id;
~~~

**Bảng tạm: dữ liệu được tạo ở một bước rồi đọc trong các bước tiếp theo.**

~~~sql
CREATE TEMP TABLE tmp_paid_orders AS
SELECT customer_id, total_amount
FROM orders
WHERE order_status = 'PAID';

SELECT customer_id, SUM(total_amount) AS revenue
FROM tmp_paid_orders
GROUP BY customer_id;

-- Khi xong:
DROP TABLE tmp_paid_orders;
~~~

Các đoạn trên là hình thức PostgreSQL, và giả định bảng `orders` đã tồn tại. Những phần sau sẽ cung cấp **toàn bộ schema mẫu có thể chạy**.

### 1.2. Đừng nhầm “tái sử dụng câu SQL” với “tái sử dụng dữ liệu đã tính”

Đây là hai ý nghĩa rất khác:

- Dùng chung **định nghĩa** “đơn PAID là đơn nào” qua nhiều dịch vụ: thường phù hợp với **view**.
- Dùng chung **cùng một bản kết quả đã tính** qua nhiều SELECT trong một tác vụ: thường phù hợp với **bảng tạm**.
- Dùng lại tên một phép biến đổi ở nhiều vị trí **của cùng câu SQL**: thường phù hợp với **CTE**.

**View thông thường không tự lưu tập hàng**. Mỗi lần SELECT view, hệ quản trị thực thi logic truy vấn của view trên dữ liệu phù hợp với snapshot/transaction đang được đọc. **CTE cũng không mặc nhiên là một bảng được lưu một lần**. **Bảng tạm** thì thực sự có các hàng được lưu trong phạm vi sống của nó, nhưng các hàng đó không tự đồng bộ với bảng gốc khi dữ liệu nguồn thay đổi.

## 2. So sánh nhanh theo phạm vi

| Tiêu chí | CTE (`WITH`) | View thông thường | Bảng tạm |
| --- | --- | --- | --- |
| Vòng đời tên kết quả | Một câu lệnh SQL | Đối tượng schema tồn tại cho đến khi thay đổi/xóa | Theo phiên kết nối hoặc giao dịch, tùy DBMS/cấu hình |
| Dùng lại trong **cùng câu SQL** | Có, nhiều chỗ tham chiếu nếu phạm vi cho phép | Có | Có |
| Dùng lại trong **câu SQL tiếp theo** | Không, nếu không khai báo lại | Có | Có khi cùng phiên và bảng còn tồn tại |
| Dùng qua **kết nối khác** | Không có đối tượng dùng chung | Có, theo quyền và schema | Thông thường không chia sẻ dữ liệu tạm giữa các session |
| Lưu định nghĩa trong catalog lâu dài | Không | Có | Thông thường đối tượng/dữ liệu tạm có vòng đời ngắn; cách quản lý metadata khác nhau |
| Lưu dữ liệu đã tính | Không được bảo đảm; do optimizer/engine | Không, với view thông thường | Có |
| Tự phản ánh dữ liệu nguồn mới ở lần đọc khác | Câu SQL mới phải tính lại | Thường có, theo snapshot/isolation | Không, trừ khi nạp/cập nhật lại bảng tạm |
| Tạo index trực tiếp trên kết quả | Không tạo index CTE như bảng thường | Không tạo index trên view thường theo cùng cách; có ngoại lệ indexed view ở DBMS cụ thể | Nhiều DBMS hỗ trợ index trên bảng tạm |
| Phân quyền chia sẻ định nghĩa | Không có đối tượng schema riêng | Có thể cấp quyền theo view | Quyền và khả năng truy cập chịu phạm vi temp/session |
| Điểm mạnh | Phân rã logic một truy vấn | Quy ước nghiệp vụ dùng chung nhiều truy vấn/ứng dụng | Giữ snapshot trung gian cho nhiều bước |
| Rủi ro thường gặp | Tưởng CTE tồn tại giữa hai câu SQL hoặc luôn materialize | Tưởng view luôn có cache và tự tăng tốc | Quên dọn dẹp, session pooling, dữ liệu cũ, chi phí ghi |

Không phải quy tắc “CTE nhanh nhất, view chậm hơn, temp table chậm nhất”. **Phạm vi dùng lại** là tiêu chí chính của bài, nhưng sau đó vẫn cần đánh giá chi phí thực thi, lượng dữ liệu, quyền hạn và khả năng bảo trì.

### 2.1. Sơ đồ vòng đời

~~~text
Một câu SQL:
┌───────────────────────────────────────────────────────┐
│ WITH paid_oct AS (...)                                │
│ SELECT ... FROM paid_oct;                             │
│             └── CTE chỉ có tên trong câu này          │
└───────────────────────────────────────────────────────┘
             Câu SELECT tiếp theo: không còn paid_oct

Nhiều câu SQL / nhiều kết nối:
┌───────────────────────────────────────────────────────┐
│ CREATE VIEW v_paid_order_lines AS ...;                │
│ Session A: SELECT ... FROM v_paid_order_lines;        │
│ Session B: SELECT ... FROM v_paid_order_lines;        │
│ Session C: SELECT ... FROM v_paid_order_lines;        │
│ Định nghĩa view còn cho đến DROP/ALTER và theo quyền. │
└───────────────────────────────────────────────────────┘

Một phiên hoặc một giao dịch:
┌───────────────────────────────────────────────────────┐
│ Connection A / transaction T                          │
│   CREATE TEMP TABLE tmp_oct AS SELECT ...;            │
│   SELECT ... FROM tmp_oct;                            │
│   UPDATE tmp_oct ...;                                 │
│   SELECT ... FROM tmp_oct;                            │
│   DROP TABLE hoặc COMMIT/đóng phiên theo cấu hình      │
└───────────────────────────────────────────────────────┘
             Connection B thường không thấy tmp_oct của A
~~~

## 3. Bộ dữ liệu mẫu: doanh thu khách hàng

Các ví dụ chính dùng **PostgreSQL** với `TIMESTAMPTZ`, SQL tổng hợp và truy vấn giao dịch tháng 10/2026 theo múi giờ Việt Nam (UTC+07:00).

### 3.1. Bảng khách hàng

~~~sql
CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    city          VARCHAR(50) NOT NULL
);

INSERT INTO customers (customer_id, customer_name, city)
VALUES
    (1, 'An',   'Ha Noi'),
    (2, 'Binh', 'TP HCM'),
    (3, 'Chi',  'Da Nang'),
    (4, 'Dung', 'TP HCM');
~~~

### 3.2. Bảng đơn hàng

~~~sql
CREATE TABLE orders (
    order_id      INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL
        REFERENCES customers(customer_id),
    ordered_at    TIMESTAMPTZ NOT NULL,
    order_status  VARCHAR(20) NOT NULL,
    total_amount  NUMERIC(12, 2) NOT NULL,

    CONSTRAINT chk_order_status CHECK (
        order_status IN ('PAID', 'PENDING', 'CANCELLED', 'REFUNDED')
    ),
    CONSTRAINT chk_order_amount CHECK (total_amount >= 0)
);

INSERT INTO orders (
    order_id, customer_id, ordered_at, order_status, total_amount
)
VALUES
    (1001, 1, TIMESTAMPTZ '2026-10-01 09:00:00+07', 'PAID',      120.00),
    (1002, 1, TIMESTAMPTZ '2026-10-10 12:00:00+07', 'PAID',       80.00),
    (1003, 1, TIMESTAMPTZ '2026-10-12 10:00:00+07', 'CANCELLED', 300.00),
    (1004, 2, TIMESTAMPTZ '2026-10-04 11:00:00+07', 'PAID',      200.00),
    (1005, 2, TIMESTAMPTZ '2026-10-08 14:00:00+07', 'PAID',       50.00),
    (1006, 2, TIMESTAMPTZ '2026-10-29 09:00:00+07', 'REFUNDED',   70.00),
    (1007, 3, TIMESTAMPTZ '2026-10-05 16:00:00+07', 'PAID',       40.00),
    (1008, 3, TIMESTAMPTZ '2026-11-02 10:00:00+07', 'PAID',       60.00),
    (1009, 4, TIMESTAMPTZ '2026-10-20 10:00:00+07', 'PENDING',    90.00),
    (1010, 4, TIMESTAMPTZ '2026-10-21 17:00:00+07', 'PAID',       90.00);
~~~

Bảng này có đủ trường hợp để thấy bộ lọc:

- `CANCELLED` không phải doanh thu đơn PAID.
- `REFUNDED` không được tính trong chính sách minh họa “chỉ PAID”. Trong thực tế, việc hoàn tiền và doanh thu ròng có thể cần sổ cái/logic khác; đây là **quy tắc giả định của bài**.
- `PENDING` không được tính.
- Đơn `1008` được thanh toán nhưng nằm **ngoài tháng 10**.
- Hai khách ở TP HCM giúp thấy phép tổng hợp theo thành phố.

### 3.3. Kết quả đúng kỳ vọng cho tháng 10

Ta định nghĩa doanh thu tháng 10 là **tổng `total_amount` của những đơn có trạng thái PAID và thời điểm nằm trong nửa khoảng [01/10, 01/11) theo giờ +07:00**.

| customer_id | Khách | Thành phố | Số đơn PAID tháng 10 | Doanh thu |
| ---: | --- | --- | ---: | ---: |
| 1 | An | Ha Noi | 2 | 200.00 |
| 2 | Binh | TP HCM | 2 | 250.00 |
| 3 | Chi | Da Nang | 1 | 40.00 |
| 4 | Dung | TP HCM | 1 | 90.00 |

Tổng tháng 10: `200 + 250 + 40 + 90 = 580`, gồm `6` đơn PAID.

Dùng **nửa khoảng thời gian**:

~~~sql
WHERE ordered_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND ordered_at <  TIMESTAMPTZ '2026-11-01 00:00:00+07'
~~~

Thay vì cố dùng `BETWEEN '2026-10-01' AND '2026-10-31 23:59:59'`, cách này tránh bỏ sót dữ liệu có phần giây nhỏ hơn một giây ở cuối tháng. Nếu hệ thống thật dùng múi giờ có DST, ranh giới phải được tính theo lịch địa phương của vùng đó, không mặc định tháng/ngày luôn có số giờ cố định.

## 4. Chọn CTE khi logic chỉ cần dùng trong một câu truy vấn

### 4.1. Viết một báo cáo bằng nhiều bước có tên

Yêu cầu: lấy **ba khách có doanh thu PAID cao nhất trong tháng 10**.

~~~sql
WITH paid_october AS (
    SELECT
        o.customer_id,
        c.customer_name,
        c.city,
        o.total_amount
    FROM orders AS o
    JOIN customers AS c
      ON c.customer_id = o.customer_id
    WHERE o.order_status = 'PAID'
      AND o.ordered_at >=
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND o.ordered_at <
          TIMESTAMPTZ '2026-11-01 00:00:00+07'
),
customer_totals AS (
    SELECT
        customer_id,
        customer_name,
        city,
        COUNT(*) AS paid_order_count,
        SUM(total_amount) AS revenue
    FROM paid_october
    GROUP BY customer_id, customer_name, city
)
SELECT
    customer_id,
    customer_name,
    paid_order_count,
    revenue
FROM customer_totals
ORDER BY revenue DESC, customer_id
LIMIT 3;
~~~

Kết quả:

| customer_id | customer_name | paid_order_count | revenue |
| ---: | --- | ---: | ---: |
| 2 | Binh | 2 | 250.00 |
| 1 | An | 2 | 200.00 |
| 4 | Dung | 1 | 90.00 |

Ở đây:

1. `paid_october` diễn đạt **tập hàng nguồn** sau khi lọc ngày và trạng thái.
2. `customer_totals` tổng hợp về **một hàng mỗi khách**.
3. `SELECT` cuối chỉ trình bày ba khách đứng đầu.

Đây là cách lý tưởng để viết **một truy vấn tương đối phức tạp nhưng vẫn theo dõi được các bước logic**. Không phải tạo đối tượng schema nào trong database, cũng không cần quyền `CREATE VIEW` hay `CREATE TABLE` nếu người dùng đã có quyền đọc bảng nền.

### 4.2. CTE chỉ có phạm vi trong chính câu SQL chứa WITH

Sau câu trên, nếu chạy:

~~~sql
-- Lỗi: customer_totals không phải một bảng/view tồn tại độc lập.
SELECT *
FROM customer_totals;
~~~

hệ sẽ không tìm thấy quan hệ `customer_totals`, trừ khi tình cờ có một bảng/view thật cùng tên trong schema. Tên CTE đã hết phạm vi sau khi câu SQL trước kết thúc.

Ngay cả khi hai câu cùng nằm trong một transaction:

~~~sql
BEGIN;

WITH x AS (
    SELECT 1 AS value
)
SELECT value FROM x;

-- x KHÔNG còn tồn tại trong câu tiếp theo.
SELECT value FROM x;

ROLLBACK;
~~~

`BEGIN/COMMIT` không kéo dài vòng đời của CTE. **Phạm vi CTE là statement**, không phải transaction.

### 4.3. Có thể tham chiếu CTE nhiều lần trong cùng một statement

~~~sql
WITH paid_october AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE order_status = 'PAID'
      AND ordered_at >=
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND ordered_at <
          TIMESTAMPTZ '2026-11-01 00:00:00+07'
)
SELECT
    (SELECT COUNT(*) FROM paid_october) AS paid_orders,
    (SELECT SUM(total_amount) FROM paid_october) AS revenue;
~~~

Kết quả:

| paid_orders | revenue |
| ---: | ---: |
| 6 | 580.00 |

Hai scalar subquery cùng dùng tên `paid_october` **trong cùng một câu SQL**. Điều này là **tái sử dụng tên/logic**, không phải bằng chứng engine bắt buộc tính CTE đúng một lần rồi cache kết quả.

### 4.4. CTE không mặc định là bảng vật lý trung gian

Một hiểu nhầm phổ biến:

> Viết `WITH paid_october AS (...)` nghĩa là database tạo một bảng tạm rồi SELECT từ bảng đó.

Điều này **không đúng như một quy tắc chung**. Bộ tối ưu của nhiều DBMS có thể gộp CTE vào truy vấn ngoài, thực thi một lần, tính lại hoặc chọn chiến lược khác theo ngữ nghĩa và kế hoạch.

Trong PostgreSQL hiện đại, một CTE chỉ đọc và không có hàm dễ gây side effect có thể được *fold* vào truy vấn ngoài ở một số trường hợp; một số CTE khác được materialize. PostgreSQL hỗ trợ các lựa chọn `MATERIALIZED` và `NOT MATERIALIZED` cho những trường hợp phù hợp, nhưng chúng không biến CTE thành một bảng có thể đọc ở **statement khác**.

Ví dụ cú pháp PostgreSQL:

~~~sql
WITH paid_october AS MATERIALIZED (
    SELECT customer_id, total_amount
    FROM orders
    WHERE order_status = 'PAID'
      AND ordered_at >=
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND ordered_at <
          TIMESTAMPTZ '2026-11-01 00:00:00+07'
)
SELECT customer_id, SUM(total_amount)
FROM paid_october
GROUP BY customer_id;
~~~

Đây là một **hướng dẫn cho optimizer của PostgreSQL**, không phải cách lưu kết quả dùng lại ở câu lệnh sau. Tránh thêm `MATERIALIZED` chỉ theo cảm tính; đo kế hoạch thực thi và cân nhắc ảnh hưởng đẩy bộ lọc vào trong.

### 4.5. Khi nào CTE thực sự phù hợp?

Dùng CTE khi:

- Một báo cáo chỉ chạy bằng **một SELECT**.
- Muốn tách phép lọc, JOIN, aggregate, window function thành các bước dễ hiểu.
- Cần tham chiếu cùng logic nhiều lần nhưng **vẫn nằm trong cùng statement**.
- Muốn logic thay đổi theo các tham số khác nhau của từng lần gọi.
- Không muốn quản lý đối tượng schema sống lâu.

CTE không thay thế được view nếu **nhiều ứng dụng cần dùng chung một định nghĩa chuẩn** mà không muốn sao chép SQL. Nó cũng không thay thế được bảng tạm nếu **nhiều statement cần đọc cùng một snapshot đã tính sẵn**.

## 5. Chọn view khi cần dùng chung định nghĩa qua nhiều truy vấn và phiên

### 5.1. Đưa quy tắc “đơn PAID” thành một đối tượng schema

Giả sử ba màn hình khác nhau đều cần kết hợp khách hàng với đơn đã thanh toán. Thay vì mỗi màn hình chép lại cùng điều kiện:

~~~sql
o.order_status = 'PAID'
~~~

ta có thể tạo view chung:

~~~sql
CREATE VIEW v_paid_order_lines AS
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name,
    c.city,
    o.ordered_at,
    o.total_amount
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID';
~~~

Sau đó các câu lệnh khác dùng view như một nguồn quan hệ:

~~~sql
SELECT
    customer_id,
    customer_name,
    SUM(total_amount) AS revenue
FROM v_paid_order_lines
WHERE ordered_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND ordered_at <
      TIMESTAMPTZ '2026-11-01 00:00:00+07'
GROUP BY customer_id, customer_name
ORDER BY revenue DESC, customer_id;
~~~

Kết quả là bốn khách với doanh thu `250, 200, 90, 40` tương ứng Binh, An, Dung, Chi.

Một báo cáo khác theo thành phố:

~~~sql
SELECT
    city,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS revenue
FROM v_paid_order_lines
WHERE ordered_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND ordered_at <
      TIMESTAMPTZ '2026-11-01 00:00:00+07'
GROUP BY city
ORDER BY revenue DESC, city;
~~~

Kết quả:

| city | paid_orders | revenue |
| --- | ---: | ---: |
| TP HCM | 3 | 340.00 |
| Ha Noi | 2 | 200.00 |
| Da Nang | 1 | 40.00 |

**Một định nghĩa view** phục vụ được nhiều câu SQL, nhiều báo cáo và nhiều kết nối — theo quyền truy cập đã cấu hình.

### 5.2. Vì sao view ở đây không khóa cứng tháng 10?

View trên định nghĩa **quy tắc nghiệp vụ có khả năng tái sử dụng lâu dài**: trạng thái PAID và các cột khách hàng/đơn hàng.

Nếu tạo view:

~~~sql
-- Không sai cú pháp, nhưng bị khóa chặt tháng cụ thể:
CREATE VIEW v_paid_october_2026 AS
SELECT ...
FROM orders
WHERE order_status = 'PAID'
  AND ordered_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND ordered_at <
      TIMESTAMPTZ '2026-11-01 00:00:00+07';
~~~

thì muốn xem tháng 11 phải tạo view khác hoặc thay định nghĩa. Đó là dấu hiệu **tham số động** đã bị đưa vào một đối tượng lược đồ cứng, có thể không phù hợp.

Quy tắc gợi ý:

- **View:** giữ logic ổn định, dùng chung qua nhiều tháng/khách hàng/báo cáo.
- **Câu SELECT từ view:** cung cấp bộ lọc thời gian, khách hàng hoặc ngưỡng theo từng yêu cầu.
- **CTE:** tiếp tục phân tách xử lý phức tạp trong báo cáo cụ thể sử dụng view.

Có thể kết hợp:

~~~sql
WITH oct_totals AS (
    SELECT
        customer_id,
        customer_name,
        SUM(total_amount) AS revenue
    FROM v_paid_order_lines
    WHERE ordered_at >=
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND ordered_at <
          TIMESTAMPTZ '2026-11-01 00:00:00+07'
    GROUP BY customer_id, customer_name
)
SELECT *
FROM oct_totals
WHERE revenue >= 100
ORDER BY revenue DESC, customer_id;
~~~

Đầu ra: Binh `250` và An `200`.

### 5.3. View thường lưu câu truy vấn, không lưu snapshot hàng

Một view thông thường **không phải bảng kết quả đã sao chép**. Khi đọc view, DBMS sử dụng định nghĩa nó để lấy dữ liệu hiện có theo transaction snapshot phù hợp.

Nếu một đơn PAID mới được chèn và commit vào bảng `orders`, một truy vấn view mới có thể thấy nó theo isolation/visibility đang áp dụng. Không cần tự chạy `REFRESH VIEW` đối với view thông thường.

Ngược lại, một số loại **materialized view** hoặc indexed view có cơ chế lưu dữ liệu riêng. Đừng dùng đặc điểm của chúng để suy về view thông thường; mục 12 sẽ phân biệt rõ.

### 5.4. View không tự cải thiện tốc độ

Ví dụ:

~~~sql
SELECT COUNT(*)
FROM v_paid_order_lines
WHERE ordered_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND ordered_at <
      TIMESTAMPTZ '2026-11-01 00:00:00+07';
~~~

DBMS thường cần đọc dữ liệu phù hợp từ các bảng nền hoặc tận dụng kế hoạch/index của chúng. Việc view tồn tại **không chứng minh truy vấn đã được cache hay precompute**.

Bộ tối ưu có thể mở rộng định nghĩa view và đẩy điều kiện lọc vào bảng nguồn ở nhiều trường hợp. Nhưng nếu view có aggregate phức tạp, DISTINCT, window, hàm có side effect hoặc hàng rào bảo mật, khả năng tối ưu có thể bị giới hạn theo DBMS và cấu trúc truy vấn.

### 5.5. View là giao diện dữ liệu có thể quản lý tập trung

View có ích khi muốn:

- Đặt tên một quan niệm nghiệp vụ ổn định như `v_paid_order_lines`.
- Ẩn các chi tiết JOIN khỏi nhiều báo cáo.
- Giới hạn tập cột cung cấp cho một nhóm người dùng.
- Cung cấp cấu trúc đọc có hợp đồng rõ ràng giữa database và ứng dụng.
- Thay đổi cách tổ chức bảng nền trong tương lai, với điều kiện giữ được interface của view và các phụ thuộc.

Ví dụ chỉ cung cấp các cột công khai:

~~~sql
CREATE VIEW v_customer_public AS
SELECT
    customer_id,
    customer_name,
    city
FROM customers;
~~~

Không nhất thiết view phải là một phép tính phức tạp. Đôi khi giá trị lớn nhất của nó là **đặt ra một giao diện dữ liệu có tên và quyền truy cập**.

Tuy nhiên, view không tự biến thành “hàng rào bảo mật tuyệt đối”. Quyền bảng nền, chủ sở hữu view, RLS, chính sách SQL và khả năng truy cập trực tiếp bảng gốc vẫn phải được thiết kế đúng; xem mục 11.

### 5.6. Quản lý vòng đời view

Trong PostgreSQL:

~~~sql
CREATE OR REPLACE VIEW v_paid_order_lines AS
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name,
    c.city,
    o.ordered_at,
    o.total_amount
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID';
~~~

`CREATE OR REPLACE VIEW` có những giới hạn khi thay đổi tên, thứ tự và kiểu cột đã tồn tại trong PostgreSQL; không coi nó là công cụ đổi tùy ý mọi cấu trúc mà không ảnh hưởng client. Nếu nhiều ứng dụng sử dụng view, cần **migration, quyền, kiểm soát phiên bản và kế hoạch tương thích**.

Xóa view khi thật sự không còn phụ thuộc:

~~~sql
DROP VIEW v_paid_order_lines;
~~~

Không chạy `DROP VIEW` tùy tiện trên cơ sở dữ liệu chung; các câu truy vấn hoặc view khác có thể đang tham chiếu nó.

## 6. Chọn bảng tạm khi cần tái sử dụng kết quả qua nhiều statement trong một tác vụ

### 6.1. Bài toán: tính một lần, đọc ba báo cáo trong cùng giao dịch

Giả sử một tác vụ cuối tháng cần tạo:

1. Top 3 khách theo doanh thu.
2. Danh sách khách có doanh thu từ 100 trở lên.
3. Tổng doanh thu theo thành phố.

Cả ba câu sử dụng **cùng dữ liệu tháng 10 đã tổng hợp**. Không muốn mỗi SELECT phải khai báo lại phép JOIN + lọc + GROUP BY. Nếu các báo cáo cần một **snapshot trung gian cố định** trong cùng một tác vụ, bảng tạm là lựa chọn đáng cân nhắc.

### 6.2. Tạo bảng tạm từ kết quả SELECT

Ví dụ PostgreSQL:

~~~sql
BEGIN;

CREATE TEMP TABLE tmp_oct_customer_totals
ON COMMIT DROP
AS
SELECT
    c.customer_id,
    c.customer_name,
    c.city,
    COUNT(*) AS paid_order_count,
    SUM(o.total_amount) AS revenue
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID'
  AND o.ordered_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND o.ordered_at <
      TIMESTAMPTZ '2026-11-01 00:00:00+07'
GROUP BY c.customer_id, c.customer_name, c.city;

SELECT *
FROM tmp_oct_customer_totals
ORDER BY customer_id;

COMMIT;
~~~

Trong transaction, bảng tạm chứa bốn hàng giống bảng kết quả ở mục 3.3. Với `ON COMMIT DROP` của PostgreSQL, **bảng tạm bị xóa khi COMMIT**; vì vậy câu SELECT sau COMMIT ở một statement khác không còn đọc được `tmp_oct_customer_totals`.

Để chạy đủ ba báo cáo, đặt chúng **trước COMMIT** trong cùng giao dịch.

### 6.3. Ba câu truy vấn từ cùng bảng tạm

~~~sql
BEGIN;

CREATE TEMP TABLE tmp_oct_customer_totals
ON COMMIT DROP
AS
SELECT
    c.customer_id,
    c.customer_name,
    c.city,
    COUNT(*) AS paid_order_count,
    SUM(o.total_amount) AS revenue
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID'
  AND o.ordered_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND o.ordered_at <
      TIMESTAMPTZ '2026-11-01 00:00:00+07'
GROUP BY c.customer_id, c.customer_name, c.city;

-- Báo cáo 1: top 3 khách.
SELECT customer_id, customer_name, revenue
FROM tmp_oct_customer_totals
ORDER BY revenue DESC, customer_id
LIMIT 3;

-- Báo cáo 2: khách có doanh thu ít nhất 100.
SELECT customer_id, customer_name, revenue
FROM tmp_oct_customer_totals
WHERE revenue >= 100
ORDER BY revenue DESC, customer_id;

-- Báo cáo 3: tổng theo thành phố.
SELECT city, SUM(revenue) AS city_revenue
FROM tmp_oct_customer_totals
GROUP BY city
ORDER BY city_revenue DESC, city;

COMMIT;
~~~

Các kết quả:

**Top 3:** Binh `250`, An `200`, Dung `90`.

**Doanh thu từ 100:** Binh `250`, An `200`.

**Theo thành phố:** TP HCM `340`, Ha Noi `200`, Da Nang `40`.

Tất cả đọc cùng tập tổng hợp `tmp_oct_customer_totals` đã được tạo **một lần**. Đó là ý nghĩa “tái sử dụng kết quả đã tính” mà view thông thường hoặc hai câu CTE độc lập không tự bảo đảm.

### 6.4. Bảng tạm có thể được lập chỉ mục và cập nhật

Với lượng dữ liệu trung gian lớn, PostgreSQL cho phép tạo index:

~~~sql
CREATE UNIQUE INDEX tmp_oct_customer_totals_uidx
ON tmp_oct_customer_totals (customer_id);

CREATE INDEX tmp_oct_customer_totals_revenue_idx
ON tmp_oct_customer_totals (revenue DESC);

ANALYZE tmp_oct_customer_totals;
~~~

Đặt các câu trên **sau khi bảng tạm được tạo và trước khi bị DROP**. Chúng là cú pháp PostgreSQL và mang ý nghĩa:

- Unique index trên `customer_id` giúp bảo vệ quan hệ một hàng mỗi khách, nếu dữ liệu đúng.
- Index trên `revenue` có thể hỗ trợ một số bộ lọc/sắp xếp trên tập lớn.
- `ANALYZE` cập nhật thống kê để optimizer ước lượng dữ liệu ở bảng tạm.

Nhưng với **4 hàng mẫu**, các index chỉ nhằm minh họa và có thể tốn công hơn lợi ích. Không tự động tạo index cho mọi bảng tạm; cần xem số hàng, số lần đọc và kế hoạch thực thi.

Có thể cập nhật bảng tạm cho một bước xử lý trung gian:

~~~sql
UPDATE tmp_oct_customer_totals
SET revenue = revenue * 0.95
WHERE city = 'TP HCM';
~~~

Tuy nhiên **đây là sửa bản sao trung gian**, **không sửa doanh thu trong bảng `orders`**. Cần đặt tên cột/logic để người dùng không nhầm một phép biến đổi tạm thời với dữ liệu gốc.

### 6.5. CREATE TEMP TABLE ... AS không mặc định sao chép mọi constraint

Trong PostgreSQL, `CREATE TEMP TABLE ... AS SELECT ...` tạo các cột và hàng từ SELECT. Đừng giả định nó tự sao chép đầy đủ:

- Primary key hoặc unique constraints của bảng nguồn;
- Foreign keys;
- Triggers;
- Index;
- Default values và mọi thuộc tính schema khác.

Nếu kết quả tạm đòi hỏi ràng buộc hoặc index, hãy khai báo/thêm chúng một cách có chủ đích theo dialect. Không nên hiểu “bảng tạm” là một bản sao toàn vẹn của bảng gốc chỉ vì lấy dữ liệu từ `SELECT`.

## 7. Vòng đời bảng tạm: phiên, giao dịch và ON COMMIT

Đây là điểm dễ gây lỗi nhất khi sử dụng bảng tạm với connection pooling.

### 7.1. PostgreSQL: ON COMMIT PRESERVE ROWS

Mặc định thông dụng của PostgreSQL khi tạo temp table mà không khai báo `ON COMMIT` là **giữ hàng qua các lần COMMIT** cho tới khi bảng tạm bị drop hoặc phiên kết nối kết thúc.

~~~sql
CREATE TEMP TABLE tmp_session_example
ON COMMIT PRESERVE ROWS
AS
SELECT 1 AS n;

BEGIN;
SELECT n FROM tmp_session_example;  -- 1
COMMIT;

-- Vẫn cùng một physical connection:
SELECT n FROM tmp_session_example;  -- 1

DROP TABLE tmp_session_example;
~~~

Tuy nhiên nếu ứng dụng “mở kết nối mới” hoặc một pool trả về **physical connection khác**, bảng tạm của phiên cũ **không tự xuất hiện** trên kết nối mới.

### 7.2. PostgreSQL: ON COMMIT DELETE ROWS

~~~sql
CREATE TEMP TABLE tmp_delete_on_commit (
    item_id INTEGER
)
ON COMMIT DELETE ROWS;

BEGIN;
INSERT INTO tmp_delete_on_commit (item_id)
VALUES (1), (2);
SELECT COUNT(*) FROM tmp_delete_on_commit;  -- 2
COMMIT;

-- Cùng phiên: bảng còn, nhưng dữ liệu bị xóa tại COMMIT.
SELECT COUNT(*) FROM tmp_delete_on_commit;  -- 0

DROP TABLE tmp_delete_on_commit;
~~~

Ý nghĩa: **đối tượng tạm còn tồn tại trong session**, nhưng các hàng được xóa khi transaction commit.

Đây không phải hành vi mặc định chung của mọi DBMS; với Oracle global temporary table, quy tắc transaction/session phải được khai báo theo cú pháp Oracle.

### 7.3. PostgreSQL: ON COMMIT DROP

~~~sql
BEGIN;

CREATE TEMP TABLE tmp_drop_on_commit
ON COMMIT DROP
AS
SELECT 1 AS n;

SELECT * FROM tmp_drop_on_commit; -- một hàng

COMMIT;

-- Bảng bị drop sau COMMIT, không đọc được ở câu tiếp theo.
~~~

Mẫu này phù hợp khi kết quả trung gian cần đúng **một transaction** và muốn giảm nguy cơ để sót bảng tạm trong phiên được tái sử dụng.

### 7.4. Đừng nhầm transaction và session

| Sự kiện | CTE | PostgreSQL temp PRESERVE ROWS | PostgreSQL temp DELETE ROWS | PostgreSQL temp DROP | View thường |
| --- | --- | --- | --- | --- | --- |
| Kết thúc một SELECT | Tên CTE hết phạm vi | Không tự xóa bảng/hàng | Không tự xóa bảng/hàng | Không tự xóa ngay, trừ khi transaction kết thúc | View vẫn còn |
| COMMIT | Không liên quan vì CTE đã hết | Hàng vẫn còn | Xóa hàng, giữ bảng | Xóa bảng | View vẫn còn |
| ROLLBACK | Không tạo đối tượng tồn tại | Hoàn tác thay đổi tạm trong transaction theo quy tắc DBMS | Tác động theo transaction và thời điểm tạo/sửa | Tác động theo giao dịch; bảng tạo trong transaction có thể bị rollback | View schema chịu transaction DDL nếu được sửa |
| Đóng physical session | Không liên quan | Bảng/hàng tạm biến mất | Bảng/hàng tạm biến mất | Bảng tạm biến mất | View vẫn còn |
| Kết nối session khác | Không thấy CTE cũ | Không thấy bảng tạm của session A | Không thấy bảng tạm của session A | Không thấy bảng tạm của session A | Có thể truy cập theo quyền |

Các dòng trên là cách khái quát **PostgreSQL**, không phải hợp đồng SQL chuẩn cho mọi DBMS. Đặc biệt, khi dùng pool, việc “đóng connection” ở lớp Java có thể chỉ **trả connection về pool**, physical session có thể vẫn còn sống.

### 7.5. Tên bảng tạm có thể che khuất bảng thật

Trong PostgreSQL, temp schema có thể được ưu tiên khi phân giải tên quan hệ. Nếu tạo:

~~~sql
CREATE TEMP TABLE orders (
    order_id INTEGER
);
~~~

thì một số câu `SELECT * FROM orders` không có schema prefix trong cùng session có thể tham chiếu **bảng tạm**, không phải bảng `orders` thật.

Vì thế:

- Dùng tên tạm có tiền tố rõ như `tmp_`.
- Khi cần chắc chắn đọc bảng gốc, dùng schema-qualified name như `public.orders` ở môi trường phù hợp.
- Không dùng bảng tạm có tên trùng bảng nghiệp vụ trừ khi thật sự có chủ đích và đã kiểm soát hệ quả.

### 7.6. Khi dùng connection pool hoặc transaction pooler

Một request tạo bảng tạm trên connection A, request sau đọc `tmp_x` trên connection B thì thường không tìm thấy bảng. Ngược lại, nếu physical connection A được tái sử dụng nhưng bảng tạm chưa được drop, request tiếp theo có thể gặp **name collision** hoặc nhìn thấy dữ liệu còn sót nếu không dọn dẹp đúng.

Một số pooler vận hành ở chế độ **transaction pooling** (chẳng hạn PgBouncer) có thể gắn các transaction kế tiếp vào những server connection khác nhau. Bảng tạm dựa trên **session state** không phải lựa chọn an toàn cho luồng nhiều transaction đi qua kiểu pooler này.

Giải pháp tùy bài toán:

- Gói việc tạo, dùng và xóa bảng tạm trong **cùng một transaction** với `ON COMMIT DROP` trên PostgreSQL;
- Giữ đúng một physical connection cho toàn bộ tác vụ nếu cần session temp;
- Dọn dẹp rõ ràng khi trả kết nối cho pool;
- Hoặc dùng bảng công việc bền vững có `job_id` và quy tắc TTL nếu cần chia sẻ dữ liệu giữa nhiều kết nối/worker.

Không tự coi bảng tạm là một hàng đợi tác vụ đa người dùng.

## 8. Dữ liệu mới có xuất hiện trong CTE, view và bảng tạm không?

### 8.1. Bảng tạm là một tập hàng đã được nạp

Tạo temp table với dữ liệu tháng 10 trong một transaction, sau đó chèn thêm một đơn PAID của Chi:

~~~sql
BEGIN;

CREATE TEMP TABLE tmp_oct_paid_rows
ON COMMIT DROP
AS
SELECT
    o.order_id,
    o.customer_id,
    o.total_amount
FROM orders AS o
WHERE o.order_status = 'PAID'
  AND o.ordered_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND o.ordered_at <
      TIMESTAMPTZ '2026-11-01 00:00:00+07';

-- Trước thay đổi: Chi có 40 doanh thu.
SELECT SUM(total_amount)
FROM tmp_oct_paid_rows
WHERE customer_id = 3;
-- 40

INSERT INTO orders (
    order_id, customer_id, ordered_at,
    order_status, total_amount
)
VALUES (
    1011, 3,
    TIMESTAMPTZ '2026-10-25 10:00:00+07',
    'PAID', 10.00
);

-- Bảng tạm vẫn là snapshot đã copy trước đó.
SELECT SUM(total_amount)
FROM tmp_oct_paid_rows
WHERE customer_id = 3;
-- 40

-- View thường đọc bảng nền, thấy cả thay đổi do chính transaction tạo:
SELECT SUM(total_amount)
FROM v_paid_order_lines
WHERE customer_id = 3
  AND ordered_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND ordered_at <
      TIMESTAMPTZ '2026-11-01 00:00:00+07';
-- 50

ROLLBACK;
~~~

Bảng tạm không tự chứa đơn `1011` vì nó chỉ nhận các hàng tại thời điểm `CREATE TEMP TABLE ... AS`. View trong chính transaction có thể đọc hàng vừa INSERT vào bảng nền. Sau ROLLBACK, lần chèn cũng được hoàn tác.

**Điểm quan trọng:** “View luôn đọc mới” không có nghĩa bỏ qua transaction isolation. Trong một transaction có snapshot ổn định như REPEATABLE READ, thay đổi do transaction khác mới commit có thể chưa được thấy theo quy tắc visibility; nhưng thay đổi của **chính transaction** thường được nhìn thấy.

### 8.2. CTE là một phần của snapshot câu lệnh

Khi chạy lại một câu CTE ở statement mới, nó dựa trên dữ liệu nhìn thấy tại thời điểm/snapshot của statement đó. Nó không giữ bản kết quả từ lần trước chỉ vì cùng tên CTE.

### 8.3. View là định nghĩa động, không phải cache

Khi cần hai báo cáo ở hai thời điểm khác nhau:

- View phản ánh dữ liệu phù hợp với từng truy vấn/snapshot;
- Bảng tạm chứa dữ liệu từ lần nạp trước cho tới khi được thay đổi/nạp lại;
- Hai câu CTE độc lập tính lại logic theo dữ liệu mà mỗi câu thấy.

Nếu báo cáo cần **nhất quán tuyệt đối giữa nhiều SELECT**, chỉ chọn view không tự đủ. Có thể cần transaction isolation phù hợp hoặc một snapshot/bảng tạm cố định theo yêu cầu.

### 8.4. Snapshot tạm cũng không phải transaction isolation

Một bảng tạm tạo bằng `CREATE TEMP ... AS SELECT` sao chép kết quả tại thời điểm tạo. Sau đó các bảng nền tiếp tục thay đổi, nhưng dữ liệu tạm không tự đồng bộ.

Điều này hữu ích cho báo cáo nhất quán giữa nhiều bước, nhưng không chứng minh **mọi bảng liên quan trong toàn bộ quy trình** đã được đọc trong cùng một snapshot hợp lệ. Nếu tạo hai bảng tạm bằng hai SELECT tách rời ở READ COMMITTED, chúng có thể phản ánh hai thời điểm khác nhau khi có ghi đồng thời.

Để bảo đảm snapshot liên câu lệnh, cần cân nhắc isolation như REPEATABLE READ hoặc một chiến lược đọc nhất quán do DBMS cung cấp, ngoài quyết định CTE/view/temp table.

## 9. Hiệu năng: đừng chọn chỉ vì “cái nào chạy nhanh nhất”

### 9.1. CTE thường có cơ hội được tối ưu chung với truy vấn ngoài

Trong nhiều DBMS hiện đại, một CTE đọc dữ liệu có thể được optimizer tích hợp vào kế hoạch cuối. Có trường hợp phù hợp để chia logic mà không tạo một bảng vật lý.

Tuy nhiên:

- Một CTE được tham chiếu nhiều lần có thể có cách materialize/tính lại khác.
- CTE đệ quy có yêu cầu đánh giá riêng.
- CTE có hàm volatile/side effects hoặc DML có thể có hạn chế.
- CTE quá phức tạp hoặc bị materialize có thể hạn chế predicate pushdown trong một số kế hoạch.

**Không khẳng định CTE luôn nhanh hơn view hoặc bảng tạm.**

### 9.2. View thường được mở rộng thành truy vấn trên bảng nền

Với view không materialized, database có thể phân tích lại definition và tối ưu cùng điều kiện của SELECT gọi nó. Index trên `orders`, `customers` và các bảng nền có thể hỗ trợ:

~~~sql
SELECT *
FROM v_paid_order_lines
WHERE ordered_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND ordered_at <
      TIMESTAMPTZ '2026-11-01 00:00:00+07';
~~~

Ví dụ một index ứng viên trên bảng đơn:

~~~sql
CREATE INDEX idx_orders_status_time_customer
ON orders (order_status, ordered_at, customer_id);
~~~

Chỉ mục có thể giúp một số kế hoạch lọc theo trạng thái và thời gian. Trên bảng mẫu rất nhỏ, quét bảng có thể tốt hơn. Cần xét tần suất ghi, tính chọn lọc, phân phối thời gian và công cụ tối ưu của DBMS.

### 9.3. Bảng tạm có chi phí tạo và ghi

Bảng tạm có thể giúp khi:

- Một kết quả trung gian **đắt tiền** được dùng lại nhiều lần;
- Nhiều câu SQL cần dựa vào **cùng snapshot**;
- Muốn tạo index/thống kê trên tập trung gian;
- Pipeline cần các bước xử lý riêng, cập nhật/trộn dữ liệu tạm;
- Truy vấn đơn khổng lồ khó tối ưu/khó vận hành.

Nhưng nó cũng có chi phí:

- Thực thi SELECT nguồn để nạp;
- Ghi dữ liệu tạm vào cấu trúc lưu trữ/bộ nhớ/đĩa tùy engine;
- Tạo index và ANALYZE nếu cần;
- Quản lý lifecycle và cleanup;
- Có thể làm optimizer mất cơ hội tối ưu **xuyên qua ranh giới hai câu**;
- Dữ liệu tạm có thể lỗi thời nếu nguồn thay đổi.

Một truy vấn CTE chỉ chạy một lần có thể nhanh và đơn giản hơn nhiều so với việc ghi vài triệu hàng vào bảng tạm rồi chỉ SELECT một lần.

### 9.4. Số lần sử dụng là một yếu tố, không phải công thức tuyệt đối

Không có ngưỡng chung “dùng hai lần thì tạo bảng tạm”. Hãy xét:

- Chi phí tính tập nguồn một lần;
- Số lần và cách dùng lại;
- Kích thước kết quả trung gian;
- Bộ lọc riêng của từng báo cáo có đẩy được vào nguồn không;
- Chi phí tạo/index/drop bảng tạm;
- Khả năng index trên dữ liệu trung gian;
- Yêu cầu nhất quán dữ liệu;
- Tài nguyên temp space khi nhiều job chạy cùng lúc.

Nếu ba báo cáo đều có bộ lọc tháng khác nhau, việc materialize **toàn bộ** lịch sử vào một bảng tạm có thể còn tệ hơn chạy ba truy vấn lọc riêng bằng index phù hợp.

### 9.5. Đo bằng kế hoạch thực thi

PostgreSQL:

~~~sql
EXPLAIN
WITH paid_october AS (
    SELECT *
    FROM orders
    WHERE order_status = 'PAID'
      AND ordered_at >=
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND ordered_at <
          TIMESTAMPTZ '2026-11-01 00:00:00+07'
)
SELECT customer_id, SUM(total_amount)
FROM paid_october
GROUP BY customer_id;
~~~

Với những câu `SELECT` trên dữ liệu thử nghiệm, có thể dùng `EXPLAIN (ANALYZE, BUFFERS)` để đo thực tế. `ANALYZE` **chạy truy vấn thật**, nên với DML có thể thay đổi dữ liệu. Đối với CREATE TEMP TABLE AS hoặc INSERT/UPDATE, phải có transaction/môi trường thử phù hợp khi đo.

Các tín hiệu cần xem: scans, sort/hash aggregate, số hàng thực, temp I/O/spill, chi phí ghi trung gian, số lần thực thi nguồn và thống kê. Không dựa chỉ vào số dòng SQL.

## 10. Quyền truy cập, bảo mật và quản trị view

### 10.1. View là đối tượng schema có quyền

Khi một ứng dụng/nhóm báo cáo cần đọc định nghĩa chuẩn nhưng không nên truy cập trực tiếp mọi bảng nguồn, view có thể là một phần của mô hình cấp quyền.

Ví dụ ý tưởng PostgreSQL:

~~~sql
-- Chạy bởi quản trị viên, khi role đã được tạo và quyền phù hợp:
GRANT SELECT ON v_paid_order_lines TO report_reader;
~~~

`report_reader` là role **giả định**, không có trong bộ dữ liệu mẫu. Chỉ dùng đoạn này trong môi trường đã tạo role và kiểm tra chính sách quyền thật.

Trong PostgreSQL, view thông thường mặc định xử lý quyền đối với các bảng nền theo ngữ cảnh **chủ sở hữu view** trong nhiều trường hợp; từ PostgreSQL 15 có tùy chọn `security_invoker` để dùng quyền người gọi đối với các bảng nền. Những quy tắc tương tác với Row-Level Security (RLS) cần được thiết kế và kiểm tra theo phiên bản:

~~~sql
-- Ví dụ PostgreSQL 15+ về cú pháp; không tự dùng cho mọi view.
CREATE VIEW v_paid_order_lines_invoker
WITH (security_invoker = true)
AS
SELECT
    order_id,
    customer_id,
    total_amount
FROM orders
WHERE order_status = 'PAID';
~~~

Không suy rằng “cấp SELECT trên view là tự động an toàn” trong mọi hệ. Cần xác định:

- Người dùng có quyền đọc trực tiếp bảng gốc không?
- View có lộ các cột nhạy cảm hoặc tenant khác không?
- Quy tắc RLS có áp dụng với chủ sở hữu/người gọi như kỳ vọng không?
- View có chức năng hoặc biểu thức nào làm lộ dữ liệu qua lỗi/tối ưu không?
- Người dùng có thể tạo đối tượng trùng tên trong search_path không?

### 10.2. View không tự là security barrier

PostgreSQL hỗ trợ tùy chọn `security_barrier` cho các trường hợp nhất định. Không có nghĩa mọi view thường tự hoạt động như hàng rào bảo vệ tuyệt đối chống rò rỉ thông tin qua biểu thức truy vấn. Nếu dùng view để thực thi chính sách an ninh, phải xem tài liệu, quyền, RLS và các trường hợp truy cập bảng trực tiếp.

Tương tự, một view có `WHERE tenant_id = 10` chỉ lọc tenant 10 theo định nghĩa tĩnh; nó không phải chính sách đa tenant tổng quát nếu có nhiều tenant khác nhau và người dùng có quyền vào bảng nền.

### 10.3. Bảng tạm không tự phù hợp cho dữ liệu nhạy cảm

Bảng tạm thường không chia sẻ dữ liệu giữa các session, nhưng nó vẫn có thể chứa thông tin cá nhân, tài chính hoặc dữ liệu quan trọng. Cần chú ý:

- Chi phí và vị trí lưu trữ temp space;
- Quyền của người sở hữu và quản trị viên DBMS;
- Dữ liệu còn lại trong physical session dùng chung pool;
- Logging và công cụ giám sát có thể ghi lại SQL/dữ liệu;
- Cleanup khi lỗi hoặc transaction dở dang;
- Hạn chế đưa những cột không cần thiết vào bảng tạm.

Tên “temporary” **không có nghĩa mọi dữ liệu tự được mã hóa, xóa an toàn ngay tức thì hoặc không thể bị quan sát** theo mọi nghĩa.

### 10.4. CTE không tạo thêm đối tượng cấp quyền

CTE chạy với quyền đọc/ghi của truy vấn chứa nó. Nó không tạo một đối tượng schema riêng để cấp `GRANT SELECT ON cte_name`. Nếu mục tiêu là **quản trị giao diện truy cập dùng chung**, view thường phù hợp hơn.

## 11. Tham số hóa và kiểm soát thay đổi

### 11.1. CTE có thể chứa điều kiện theo tham số từng request

Ví dụ JDBC/PostgreSQL:

~~~sql
WITH paid_in_range AS (
    SELECT
        customer_id,
        total_amount
    FROM orders
    WHERE order_status = 'PAID'
      AND ordered_at >= ?
      AND ordered_at < ?
)
SELECT
    customer_id,
    SUM(total_amount) AS revenue
FROM paid_in_range
GROUP BY customer_id;
~~~

Hai dấu `?` là tham số **thời điểm bắt đầu và kết thúc** được driver bind đúng kiểu. CTE nằm trong SQL được gọi từng lần nên phù hợp với phạm vi tham số động.

### 11.2. View thường không nhận tham số như hàm

Một view thông thường không có dạng cú pháp phổ quát:

~~~sql
-- Không phải cú pháp CREATE VIEW tham số hóa thông thường:
CREATE VIEW v_paid_orders(start_date, end_date) AS ...
~~~

Danh sách tên cột của `CREATE VIEW` nếu có **không phải danh sách tham số đầu vào**. Để lọc ngày, viết `WHERE` khi SELECT view hoặc dùng một loại đối tượng khác như **table-valued function/stored function** nếu DBMS hỗ trợ và nghiệp vụ yêu cầu.

### 11.3. Bảng tạm có thể nạp dữ liệu cho tham số của một job

Ví dụ một job được giao kỳ báo cáo:

~~~sql
CREATE TEMP TABLE tmp_job_orders AS
SELECT *
FROM orders
WHERE order_status = 'PAID'
  AND ordered_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND ordered_at <
      TIMESTAMPTZ '2026-11-01 00:00:00+07';
~~~

Nếu một job thứ hai chạy tháng 11, nó phải nạp **tập dữ liệu tháng 11** vào bảng tạm riêng theo session/job. Một temp table không tự thay đổi phạm vi chỉ vì có tham số khác ở bước đọc.

### 11.4. View cần versioning và migration giống API

Khi một view được nhiều hệ thống sử dụng, đổi tên cột hoặc thay công thức doanh thu có thể ảnh hưởng hàng loạt dashboard. Quản lý bằng migration, kiểm tra phụ thuộc và các phiên bản interface nếu cần.

Một chiến lược có thể tạo `v_paid_order_lines_v2` khi thay đổi không tương thích, cho hệ tiêu thụ chuyển dần. Không nên đặt mọi phép biến đổi tùy từng request vào một view khổng lồ và thay definition liên tục.

## 12. Materialized view và bảng tổng hợp bền vững nằm ở đâu?

Ba lựa chọn chính chưa bao phủ mọi yêu cầu.

### 12.1. Materialized view: lưu kết quả và dùng xuyên nhiều session

Nếu một báo cáo tổng hợp phải phục vụ **nhiều người dùng**, chi phí tính lại quá cao và chấp nhận dữ liệu có độ trễ, cân nhắc **materialized view**.

PostgreSQL:

~~~sql
CREATE MATERIALIZED VIEW mv_paid_revenue_by_month AS
SELECT
    DATE_TRUNC(
        'month',
        o.ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::DATE AS month_local,
    o.customer_id,
    COUNT(*) AS paid_order_count,
    SUM(o.total_amount) AS revenue
FROM orders AS o
WHERE o.order_status = 'PAID'
GROUP BY
    DATE_TRUNC(
        'month',
        o.ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::DATE,
    o.customer_id;
~~~

Truy vấn:

~~~sql
SELECT customer_id, paid_order_count, revenue
FROM mv_paid_revenue_by_month
WHERE month_local = DATE '2026-10-01'
ORDER BY revenue DESC, customer_id;
~~~

Kết quả lưu tương ứng doanh thu 250, 200, 90, 40 nếu materialized view đã được tạo/refresh theo dữ liệu mẫu.

Khác view thường:

- **Có dữ liệu kết quả được lưu** và truy vấn lại được qua nhiều session.
- Có thể tạo index theo khả năng DBMS.
- **Không tự đảm bảo phản ánh ngay mọi INSERT/UPDATE ở bảng nguồn**.
- Cần cơ chế refresh/maintenance thích hợp.

PostgreSQL:

~~~sql
REFRESH MATERIALIZED VIEW mv_paid_revenue_by_month;
~~~

Có các tùy chọn refresh khác và hạn chế tùy phiên bản. Không coi `REFRESH MATERIALIZED VIEW` là thao tác miễn phí; nó có thể tốn tài nguyên và ảnh hưởng truy cập đồng thời tùy cách dùng.

### 12.2. Materialized view khác bảng tạm

| Nhu cầu | Bảng tạm | Materialized view |
| --- | --- | --- |
| Nhiều câu lệnh trong cùng job/session | Phù hợp | Có thể, nhưng quản trị quá mức |
| Nhiều phiên/người dùng truy cập chung dữ liệu đã tính | Không phải phạm vi thông thường | Phù hợp hơn |
| Snapshot theo một lần xử lý cụ thể | Tốt | Không nhất thiết phù hợp, do dùng chung kết quả |
| Kết quả cần lưu lâu dài | Không | Có |
| Quản lý refresh, quyền, index lâu dài | Hạn chế theo vòng đời tạm | Cần quản trị như một đối tượng schema |
| Dọn dẹp khi kết thúc job | Có | Không tự theo job |

Nếu cần dữ liệu trung gian chia sẻ giữa **nhiều worker**, có thể dùng **bảng công việc bền vững** với `job_id`, trạng thái, TTL và quyền thay vì temp table. Đây là một lựa chọn khác với materialized view, đặc biệt khi cần ghi/chỉnh sửa từng hàng và audit kết quả của job.

### 12.3. Một số hệ có indexed views hoặc auto-maintained summaries

SQL Server có tính năng indexed views theo những điều kiện nghiêm ngặt. Các nền tảng kho dữ liệu có thể có materialized view và refresh tự động. Không kết luận mọi `CREATE VIEW` đều là materialized, hay cú pháp PostgreSQL `CREATE MATERIALIZED VIEW` chạy được ở MySQL/SQL Server/Oracle.

Chủ đề chính vẫn là: **vòng đời và nơi sử dụng kết quả** phải rõ trước khi chọn đối tượng.

## 13. Khác biệt giữa các hệ quản trị SQL

SQL ý tưởng có tính phổ biến, nhưng các từ khóa, vòng đời bảng tạm và tối ưu khác nhau.

### 13.1. PostgreSQL

- `WITH name AS (...) SELECT ...` cho CTE trong phạm vi statement.
- `CREATE VIEW ... AS SELECT ...` tạo view lâu dài.
- `CREATE TEMP TABLE ... AS SELECT ...` tạo bảng tạm phiên; `ON COMMIT PRESERVE ROWS/DELETE ROWS/DROP` định nghĩa hành vi commit.
- Cho phép index/ANALYZE bảng tạm.
- Có `CREATE MATERIALIZED VIEW` và `REFRESH MATERIALIZED VIEW`.
- PostgreSQL 12+ có `MATERIALIZED`/`NOT MATERIALIZED` cho những CTE phù hợp; không đồng nhất với bảng tạm.

### 13.2. MySQL 8.x

MySQL 8.0 trở lên hỗ trợ CTE, gồm một số mẫu CTE đệ quy theo cú pháp MySQL:

~~~sql
WITH paid_orders AS (
    SELECT customer_id, total_amount
    FROM orders
    WHERE order_status = 'PAID'
)
SELECT customer_id, SUM(total_amount)
FROM paid_orders
GROUP BY customer_id;
~~~

View:

~~~sql
CREATE VIEW v_paid_orders AS
SELECT customer_id, total_amount
FROM orders
WHERE order_status = 'PAID';
~~~

Bảng tạm:

~~~sql
CREATE TEMPORARY TABLE tmp_paid_orders AS
SELECT customer_id, total_amount
FROM orders
WHERE order_status = 'PAID';
~~~

Lưu ý:

- Tên lệnh `CREATE TEMPORARY TABLE` thay vì chỉ dùng `TEMP` như PostgreSQL.
- Bảng tạm gắn với session, tự được dọn khi connection thực sự kết thúc theo cơ chế MySQL.
- `CREATE TEMPORARY TABLE` có những đặc điểm riêng về transaction/rollback: không giả định tạo/drop temp table được rollback giống PostgreSQL.
- `WITH`/view/temporary table có quy tắc optimizer, quyền và phiên bản khác PostgreSQL.
- MySQL không cung cấp materialized view như một đối tượng gốc có cùng cú pháp PostgreSQL trong các bản phổ biến; có thể cần bảng tổng hợp và job refresh riêng.

### 13.3. SQL Server

T-SQL hỗ trợ CTE thường viết `;WITH` khi có câu trước đó trong batch:

~~~sql
;WITH paid_orders AS (
    SELECT customer_id, total_amount
    FROM dbo.orders
    WHERE order_status = 'PAID'
)
SELECT customer_id, SUM(total_amount) AS revenue
FROM paid_orders
GROUP BY customer_id;
~~~

Tên CTE chỉ khả dụng trong **một statement ngay sau định nghĩa**. View là schema object được tạo bằng `CREATE VIEW`/`CREATE OR ALTER VIEW` theo phiên bản và quy tắc batch.

Bảng tạm cục bộ dùng tên bắt đầu `#`:

~~~sql
SELECT customer_id, total_amount
INTO #tmp_paid_orders
FROM dbo.orders
WHERE order_status = 'PAID';

SELECT customer_id, SUM(total_amount) AS revenue
FROM #tmp_paid_orders
GROUP BY customer_id;

DROP TABLE #tmp_paid_orders;
~~~

Các điểm riêng:

- Local temporary table `#name` có phạm vi phiên/procedure với chi tiết T-SQL.
- SQL Server có `##global_temp_name` với ngữ nghĩa khác; không coi nó giống temp session thông thường.
- Có table variables `@name`, không hoàn toàn tương đương bảng tạm.
- Có indexed views với những điều kiện riêng.
- Không mang `ON COMMIT DROP` của PostgreSQL sang SQL Server.

### 13.4. Oracle Database

Oracle hỗ trợ CTE qua `WITH` và view qua `CREATE VIEW`. Về “bảng tạm”, Oracle nổi bật với **Global Temporary Table (GTT)**:

~~~sql
CREATE GLOBAL TEMPORARY TABLE tmp_paid_orders (
    customer_id  NUMBER,
    total_amount NUMBER(12, 2)
)
ON COMMIT DELETE ROWS;
~~~

Sau đó trong session:

~~~sql
INSERT INTO tmp_paid_orders (
    customer_id, total_amount
)
SELECT customer_id, total_amount
FROM orders
WHERE order_status = 'PAID';
~~~

**Điểm khác rất quan trọng:** với Oracle GTT, **định nghĩa bảng tồn tại trong schema**, nhưng **dữ liệu bên trong có tính tạm theo session/transaction**. `ON COMMIT DELETE ROWS` xóa các hàng theo giao dịch; `ON COMMIT PRESERVE ROWS` có thể dùng cho dữ liệu theo session. Không coi `CREATE GLOBAL TEMPORARY TABLE` ở Oracle là “mỗi phiên tạo đối tượng mới rồi tự DROP cả definition khi đóng phiên” như cách thường nghĩ từ PostgreSQL.

Oracle còn có các biến thể private temporary table ở những phiên bản hỗ trợ, với vòng đời khác. Hãy xác định loại bảng tạm chính xác theo phiên bản Oracle.

### 13.5. SQLite

SQLite có CTE, view và bảng TEMP theo connection:

~~~sql
CREATE TEMP TABLE tmp_paid_orders AS
SELECT customer_id, total_amount
FROM orders
WHERE order_status = 'PAID';
~~~

Dữ liệu tạm gắn với kết nối SQLite và có các quy tắc transaction riêng. View thường được lưu trong schema, còn `TEMP VIEW` nếu dùng có phạm vi riêng. SQLite có optimizer và mô hình đồng thời khác PostgreSQL; không sao chép chiến lược temp table để tối ưu một warehouse lớn mà không đo trên SQLite.

### 13.6. Bảng đối chiếu

| DBMS | CTE | View thông thường | Bảng tạm tiêu biểu | Ghi chú vòng đời |
| --- | --- | --- | --- | --- |
| PostgreSQL | `WITH` | `CREATE VIEW` | `CREATE TEMP TABLE` | Temp session, có `ON COMMIT` |
| MySQL 8+ | `WITH` | `CREATE VIEW` | `CREATE TEMPORARY TABLE` | Temp gắn với physical session |
| SQL Server | `;WITH` | `CREATE VIEW` | `#local_temp`, `##global_temp` | Scope theo session/procedure và loại bảng |
| Oracle | `WITH` | `CREATE VIEW` | `GLOBAL TEMPORARY TABLE` | Definition có thể tồn tại lâu dài, rows tạm |
| SQLite | `WITH` | `CREATE VIEW` | `CREATE TEMP TABLE` | TEMP theo connection |
| DuckDB và các analytic engines | Thường có CTE/view | Theo engine | Có temp theo engine | Kiểm tra syntax/lifecycle chính xác |

Không dùng bảng này thay thế tài liệu của DBMS đang chạy, nhất là khi ứng dụng sử dụng connection pool, cluster hoặc các loại session đặc biệt.

## 14. Sơ đồ quyết định chọn công cụ

~~~text
Bạn cần tái sử dụng điều gì?
|
+-- Chỉ một câu SELECT/UPDATE/INSERT...?
|      |
|      +-- Cần chia logic cho dễ đọc?
|             → CTE (WITH)
|
+-- Nhiều câu SQL cần cùng định nghĩa logic?
|      |
|      +-- Nhiều session / dịch vụ / người dùng?
|             → View thông thường
|                  |
|                  +-- Quá đắt để tính lại, chấp nhận độ trễ?
|                         → Xem materialized view / summary table
|
+-- Nhiều câu SQL trong cùng job cần cùng dữ liệu đã tính?
|      |
|      +-- Chỉ một transaction / physical session?
|             → Temporary table
|
+-- Nhiều worker / nhiều connection cần cùng snapshot?
       → Bảng công việc bền vững có job_id/TTL hoặc
         materialized/shared staging theo nghiệp vụ,
         KHÔNG dựa vào session temp table
~~~

Đây là **khung quyết định ban đầu**. Còn phải cân nhắc quyền, phiên bản DBMS, chi phí tính, tính mới của dữ liệu, lock, số hàng và yêu cầu triển khai.

### 14.1. Các tình huống thực tế

| Tình huống | Phương án ban đầu | Vì sao |
| --- | --- | --- |
| Một truy vấn top 10 sản phẩm bán chạy | CTE | Chỉ cần phân nhóm/đặt tên trong một statement |
| Nhiều báo cáo cần cùng định nghĩa đơn “PAID hợp lệ” | View | Chuẩn hóa logic dùng chung lâu dài |
| Một ETL job cần lọc, chuẩn hóa, đối soát và xuất ba báo cáo từ cùng dữ liệu | Bảng tạm | Cần đọc/sửa kết quả trung gian qua nhiều bước |
| Một dashboard chạy mỗi giây cho hàng nghìn người và aggregate quá nặng | Materialized view/summary table | Cần tái sử dụng dữ liệu đã tính qua nhiều session |
| Một CTE được tham chiếu ba lần trong cùng SELECT | CTE vẫn phù hợp | Không cần tự tạo temp chỉ vì có nhiều tham chiếu |
| Một quy tắc lọc thay đổi theo request (ngày, khu vực) | CTE hoặc SELECT từ view chung | Tham số nằm ở câu truy vấn, không phải view cứng |
| Dữ liệu tạm phải đọc ở connection của worker khác | Bảng staging bền vững theo job | Temp session không chia sẻ thông thường |
| Báo cáo bảo mật cần hạn chế cột nhìn thấy | View + cấp quyền/RLS phù hợp | View là một thành phần quản trị giao diện dữ liệu |
| Tác vụ xử lý hàng triệu hàng với nhiều phép JOIN lặp | Đánh giá temp hoặc materialize | Chỉ chọn sau khi đo chi phí và phạm vi dùng lại |
| Một SELECT chỉ đọc 10 hàng | CTE hoặc SELECT trực tiếp | Temp table có thể thừa chi phí |
| Cần giữ kết quả đúng lúc job khởi chạy dù bảng nền đổi | Temp snapshot hoặc persisted job snapshot | View thường đọc lại theo snapshot truy vấn |

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ CTE tồn tại tới cuối transaction | Statement sau không tìm thấy CTE | Dùng temp table nếu cần nhiều statement |
| Nghĩ CTE luôn materialize | Đánh giá sai hiệu năng/đẩy bộ lọc | Xem kế hoạch, hiểu optimizer |
| Nghĩ view lưu dữ liệu sẵn | Mỗi SELECT vẫn có thể tốn JOIN/aggregate | Cân nhắc materialized view nếu cần cache |
| Tạo view riêng cho mọi tháng/ngày | Schema phình to, khó bảo trì | View logic chung, lọc thời gian ở câu SELECT |
| Dùng temp table cho một SELECT nhỏ | Chi phí ghi/cleanup không cần thiết | Chọn CTE/subquery |
| Coi temp table chia sẻ giữa hai connection | Connection khác không thấy dữ liệu | Giữ cùng session hoặc dùng bảng shared theo job |
| Quên `ON COMMIT DROP` hoặc DROP ở pool | Collision/dữ liệu còn lại trong session | Quản lý lifecycle rõ, transaction scope |
| Nghĩ PostgreSQL temp luôn xóa ở COMMIT | Dữ liệu có thể tồn tại theo mặc định PRESERVE ROWS | Khai báo ON COMMIT theo nhu cầu |
| Áp PostgreSQL temp sang Oracle GTT | Nhầm thời gian tồn tại definition | Phân biệt schema metadata và temp rows |
| Không biết temp table che tên bảng gốc | Query vô tình đọc bảng tạm | Tên `tmp_`, schema-qualified base tables |
| Nghĩ temp table tự phản ánh dữ liệu nguồn | Báo cáo đọc snapshot cũ | Nạp/cập nhật lại có kiểm soát |
| Nghĩ view luôn thấy commit mới bất kể isolation | Đọc sai snapshot mong đợi | Hiểu MVCC/isolation |
| Tạo index cho mọi bảng tạm | Overhead ghi/index cao | Chỉ tạo khi có lợi sau đo |
| Nghĩ CTAS giữ PK/FK/index của nguồn | Không còn ràng buộc mong muốn | Đặt constraint/index tường minh nếu cần |
| Dùng view làm chính sách bảo mật duy nhất | Có thể lộ bảng nền/vi phạm RLS | Thiết kế GRANT, owner/invoker, RLS |
| Thêm `ORDER BY` trong view/CTE và tưởng kết quả cuối có thứ tự | Kết quả có thể sắp khác | `ORDER BY` ở SELECT ngoài cùng |
| Tạo bảng tạm và mong mọi HTTP request dùng được | Pool chuyển physical connection | Giữ transaction/connection hoặc persisted staging |
| Nghĩ materialized view tự cập nhật ngay | Báo cáo bị trễ dữ liệu | Thiết kế refresh và SLA freshness |
| Sao chép cú pháp temp từ DBMS khác | Lỗi cú pháp/scope | Kiểm tra dialect và phiên bản |
| Chọn công cụ chỉ theo số dòng SQL | Khó bảo trì hoặc chậm | Bắt đầu từ vòng đời và mục đích tái sử dụng |

## 16. Bài tập thực hành

Dùng hai bảng `customers` và `orders` từ mục 3. Các đoạn dùng view/temp nên thực hành trên database thử có quyền CREATE; để chạy lại, cần xóa đối tượng cũ hoặc dùng tên mới. Với bảng tạm `ON COMMIT DROP`, tạo và đọc trong cùng transaction.

### Bài 1 — Chọn CTE cho một báo cáo

Yêu cầu chỉ có một câu SELECT: tính doanh thu PAID tháng 10 của từng khách, sắp giảm dần. Dùng công cụ nào?

**Đáp án:** CTE là lựa chọn phù hợp để phân rõ lọc và nhóm trong cùng câu.

~~~sql
WITH paid_oct AS (
    SELECT customer_id, total_amount
    FROM orders
    WHERE order_status = 'PAID'
      AND ordered_at >=
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND ordered_at <
          TIMESTAMPTZ '2026-11-01 00:00:00+07'
)
SELECT customer_id, SUM(total_amount) AS revenue
FROM paid_oct
GROUP BY customer_id
ORDER BY revenue DESC, customer_id;
~~~

Kết quả theo ID là `2:250`, `1:200`, `4:90`, `3:40`.

### Bài 2 — Một CTE có dùng được trong câu sau không?

~~~sql
WITH x AS (SELECT 10 AS n)
SELECT n FROM x;

SELECT n FROM x;
~~~

**Đáp án:** câu thứ hai không thể tham chiếu CTE `x` của câu thứ nhất. CTE có phạm vi trong **một statement**. Muốn dùng nhiều statement, dùng bảng tạm hoặc view/bảng phù hợp.

### Bài 3 — Dùng lại CTE hai lần trong cùng một câu

Tính số đơn PAID tháng 10 và tổng tiền trong **một SQL statement**.

**Đáp án:**

~~~sql
WITH paid_oct AS (
    SELECT total_amount
    FROM orders
    WHERE order_status = 'PAID'
      AND ordered_at >=
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND ordered_at <
          TIMESTAMPTZ '2026-11-01 00:00:00+07'
)
SELECT
    (SELECT COUNT(*) FROM paid_oct) AS paid_count,
    (SELECT SUM(total_amount) FROM paid_oct) AS revenue;
~~~

Kết quả `paid_count=6` và `revenue=580`. Đây là tham chiếu hai lần **cùng CTE**, không cam kết engine chỉ quét nguồn một lần.

### Bài 4 — Chuẩn hóa logic dùng chung

Ba báo cáo ở những phiên khác nhau đều cần dữ liệu đơn PAID ghép với tên khách. Nên dùng CTE trong mỗi báo cáo hay một view?

**Đáp án:** view hợp lý hơn nếu muốn định nghĩa dùng chung:

~~~sql
CREATE VIEW v_paid_order_lines AS
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name,
    c.city,
    o.ordered_at,
    o.total_amount
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID';
~~~

Các báo cáo SELECT từ view rồi thêm điều kiện ngày, khách hoặc nhóm.

### Bài 5 — View có phải cache không?

Một đơn PAID mới được commit. Truy vấn view thường sau đó có thể thấy đơn mới không?

**Đáp án:** có, khi dữ liệu đã visible theo transaction/isolation của truy vấn. View thường lưu **định nghĩa**, không phải tập hàng cố định. Không cần refresh view thường; materialized view là cơ chế khác.

### Bài 6 — Chỉ định kỳ báo cáo động

Một view được dùng cho tháng 10, tháng 11 và tháng 12. Có nên tạo ba view riêng có ngày cố định không?

**Đáp án:** thường không cần. Dùng view quy tắc PAID chung rồi SELECT với ranh giới ngày theo tham số:

~~~sql
SELECT customer_id, SUM(total_amount)
FROM v_paid_order_lines
WHERE ordered_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND ordered_at <
      TIMESTAMPTZ '2026-11-01 00:00:00+07'
GROUP BY customer_id;
~~~

Tháng khác chỉ cần đổi ranh giới được bind đúng kiểu.

### Bài 7 — Cần ba SELECT từ cùng tập tính sẵn

Một ETL job chạy ba câu tổng hợp riêng trên cùng dữ liệu tháng 10 và muốn kết quả trung gian cố định. Nên chọn gì?

**Đáp án:** bảng tạm trong phạm vi job/transaction, nếu tất cả câu SQL dùng cùng physical session và DBMS hỗ trợ.

~~~sql
BEGIN;

CREATE TEMP TABLE tmp_oct_totals
ON COMMIT DROP
AS
SELECT
    customer_id,
    SUM(total_amount) AS revenue
FROM orders
WHERE order_status = 'PAID'
  AND ordered_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND ordered_at <
      TIMESTAMPTZ '2026-11-01 00:00:00+07'
GROUP BY customer_id;

SELECT * FROM tmp_oct_totals ORDER BY revenue DESC;
SELECT * FROM tmp_oct_totals WHERE revenue >= 100;
SELECT SUM(revenue) FROM tmp_oct_totals;

COMMIT;
~~~

Các báo cáo có cùng dữ liệu trung gian đã tính trước COMMIT.

### Bài 8 — ON COMMIT DROP

Trong PostgreSQL:

~~~sql
BEGIN;
CREATE TEMP TABLE tmp_x ON COMMIT DROP AS SELECT 1 AS n;
SELECT * FROM tmp_x;
COMMIT;
SELECT * FROM tmp_x;
~~~

Câu SELECT sau COMMIT có chạy được không?

**Đáp án:** không, vì `ON COMMIT DROP` xóa bảng tại COMMIT.

### Bài 9 — ON COMMIT DELETE ROWS

Trong PostgreSQL, `ON COMMIT DELETE ROWS` khác `ON COMMIT DROP` như thế nào?

**Đáp án:** `DELETE ROWS` giữ định nghĩa bảng tạm trong session nhưng xóa hàng khi commit. `DROP` xóa cả bảng tạm. `PRESERVE ROWS` giữ hàng qua commit tới khi bảng/session kết thúc hoặc có thao tác khác.

### Bài 10 — Connection pool

Request A tạo `tmp_report` rồi trả connection về pool. Request B lấy một connection khác và cố SELECT từ `tmp_report`. Có đảm bảo thành công không?

**Đáp án:** không. Bảng tạm thuộc physical session/connection theo DBMS, request B có thể ở session khác. Thiết kế lại để tạo/dùng/drop trong cùng transaction/connection hoặc dùng persisted job table khi cần chia sẻ.

### Bài 11 — View và bảng tạm khác nhau về dữ liệu mới

Bảng tạm đã copy 6 đơn PAID tháng 10. Sau đó có thêm một đơn PAID hợp lệ trong bảng gốc. Không reload bảng tạm. Bảng tạm tự có 7 hàng không?

**Đáp án:** không. Bảng tạm vẫn chứa 6 hàng từ lần nạp, trừ khi có thao tác INSERT/REFRESH thủ công. View thường của bảng nguồn có thể thấy 7 hàng trong một truy vấn mới tùy transaction visibility.

### Bài 12 — Index cho bảng tạm

Một bảng tạm có bốn hàng và chỉ dùng hai lần. Có nên tạo ba index và chạy ANALYZE chỉ vì DBMS cho phép không?

**Đáp án:** không nên tự động. Chi phí tạo và duy trì index có thể lớn hơn lợi ích. Với bảng tạm rất lớn, nhiều JOIN/lọc, có thể cân nhắc index và thống kê sau khi đo workload.

### Bài 13 — CTAS có sao chép ràng buộc không?

~~~sql
CREATE TEMP TABLE tmp_orders AS
SELECT * FROM orders;
~~~

Có được kết luận `tmp_orders.order_id` có PRIMARY KEY và FK giống `orders` không?

**Đáp án:** không. `CREATE TABLE AS` không mặc định sao chép mọi constraint/index/default của bảng nguồn. Nếu cần tính duy nhất hoặc FK trong bảng tạm, phải tạo riêng theo tính năng DBMS.

### Bài 14 — SQL Server dùng tên nào cho temp?

Viết ý tưởng T-SQL lưu kết quả PAID vào local temp table.

**Đáp án:**

~~~sql
SELECT customer_id, total_amount
INTO #tmp_paid_orders
FROM dbo.orders
WHERE order_status = 'PAID';

SELECT customer_id, SUM(total_amount) AS revenue
FROM #tmp_paid_orders
GROUP BY customer_id;

DROP TABLE #tmp_paid_orders;
~~~

Không dùng PostgreSQL `ON COMMIT DROP` trong T-SQL.

### Bài 15 — Oracle GTT khác PostgreSQL temp

Một Oracle GTT được tạo một lần trong schema và mỗi session nạp hàng của mình. Khi session kết thúc, có phải định nghĩa GTT bị xóa như PostgreSQL temp table không?

**Đáp án:** không. Trong Oracle GTT, **metadata/definition có thể tồn tại lâu dài**, còn dữ liệu mang tính tạm theo transaction hoặc session. Phải phân biệt vòng đời definition với vòng đời hàng.

### Bài 16 — Nhiều người dùng cần cùng bảng kết quả đã tính

Một dashboard phục vụ hàng nghìn người cần cùng aggregate phức tạp, cập nhật mỗi giờ là chấp nhận được. Chọn view thường, temp table mỗi session hay materialized view/bảng tổng hợp?

**Đáp án:** xem xét **materialized view hoặc bảng tổng hợp bền vững** được refresh có kiểm soát. Nó tái sử dụng dữ liệu đã tính qua nhiều session. View thường có thể phải tính lại; temp session không chia sẻ được giữa các người dùng.

### Bài 17 — Bảo mật view

Có thể chỉ tạo view lọc tenant rồi tin chắc dữ liệu tenant khác không bao giờ bị lộ không?

**Đáp án:** không. Cần kiểm tra quyền truy cập trực tiếp bảng nền, chủ sở hữu/người gọi, RLS, điều kiện tenant, chức năng truy vấn và phiên bản DBMS. View có thể là một **thành phần của thiết kế bảo mật**, không tự là toàn bộ chính sách.

### Bài 18 — Kết hợp view và CTE

Hệ thống có view `v_paid_order_lines` dùng chung. Một báo cáo cần top 2 khách doanh thu tháng 10. Hãy viết câu với CTE đọc view.

**Đáp án:**

~~~sql
WITH customer_revenue AS (
    SELECT
        customer_id,
        customer_name,
        SUM(total_amount) AS revenue
    FROM v_paid_order_lines
    WHERE ordered_at >=
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND ordered_at <
          TIMESTAMPTZ '2026-11-01 00:00:00+07'
    GROUP BY customer_id, customer_name
)
SELECT customer_id, customer_name, revenue
FROM customer_revenue
ORDER BY revenue DESC, customer_id
LIMIT 2;
~~~

Kết quả: Binh `250`, An `200`. **View tái sử dụng quy tắc nghiệp vụ**, CTE tổ chức một câu báo cáo cụ thể.

### Bài 19 — Sắp xếp trong view có đủ không?

Một người tạo view với `ORDER BY revenue DESC` rồi câu ngoài chỉ `SELECT * FROM view`. Có được bảo đảm thứ tự trình bày cuối cùng không?

**Đáp án:** không nên dựa vào thứ tự từ bên trong view/CTE như một hợp đồng sắp xếp kết quả. Muốn đầu ra ổn định, dùng `ORDER BY` của **SELECT ngoài cùng**, với khóa phá hòa nếu cần.

### Bài 20 — Một job chạy trên nhiều worker

Ba worker độc lập, mỗi worker mở một database connection, cần đọc chung tiến độ và hàng đã chuẩn hóa của cùng lô import. Có phù hợp khi worker đầu tạo temp table không?

**Đáp án:** thường không. Dùng **bảng staging/work bền vững** có `job_id`, ràng buộc và quyền, hoặc cơ chế chia sẻ phù hợp. Temp table theo session không phải kho dữ liệu chung cho các worker.

### Bài 21 — Chọn công cụ theo năm kịch bản

Hãy chọn CTE, view, bảng tạm hoặc materialized view/bảng tổng hợp cho:

1. Một câu truy vấn phân tích có 4 bước lọc/nhóm.
2. Năm dashboard cùng dùng định nghĩa “đơn đã thanh toán”.
3. Một transaction cần đọc cùng snapshot trung gian bằng 6 câu SELECT.
4. Hàng trăm session cần đọc aggregate đã tính, cho phép trễ 10 phút.
5. Một câu SELECT dùng cùng named subquery ở hai nhánh.

**Đáp án gợi ý:** (1) CTE; (2) view; (3) bảng tạm; (4) materialized view/bảng tổng hợp; (5) CTE. Sau đó đo hiệu năng và kiểm tra DBMS, quyền truy cập và độ mới dữ liệu.

## 17. Checklist khi thiết kế

Trước khi tạo CTE, view hoặc bảng tạm, hãy trả lời:

1. **Phạm vi sử dụng:** Một statement, nhiều statement cùng session, hay nhiều session?
2. **Tái sử dụng cái gì:** Một định nghĩa logic hay kết quả đã tính?
3. **Thời gian tồn tại:** Chỉ tới hết câu SQL, tới COMMIT, tới đóng session hay dài hạn?
4. **Tham số:** Logic có thay đổi theo ngày/khách/tenant của mỗi request không?
5. **Độ mới dữ liệu:** Có phải nhìn thấy thay đổi gần nhất hay chấp nhận snapshot?
6. **Nhất quán:** Nhiều câu SQL phải dùng cùng snapshot hay mỗi câu đọc mới đều được?
7. **Khả năng chia sẻ:** Có nhiều physical connections, workers hay app servers không?
8. **Connection pool:** Có session pooling/transaction pooling, cleanup và nguy cơ reuse?
9. **Quyền:** Cần cấp SELECT trên đối tượng dùng chung, RLS hoặc giới hạn cột không?
10. **Bảo trì:** Ai sở hữu view? Có migration và quy tắc versioning khi thay đổi không?
11. **Dữ liệu nhạy cảm:** Có đang copy quá nhiều thông tin vào bảng tạm không?
12. **Kích thước:** Tập trung gian bao nhiêu hàng và được đọc bao nhiêu lần?
13. **Hiệu năng:** Cần index, statistics, predicate pushdown hay materialization?
14. **Ràng buộc:** CTAS có giữ được những unique/foreign key cần cho xử lý tiếp không?
15. **Dialect:** `ON COMMIT`, `CREATE TEMPORARY`, `#temp`, Oracle GTT khác nhau thế nào?
16. **Cleanup:** Bảng tạm còn sau lỗi/rollback/connection pool không?
17. **Sắp xếp:** SELECT ngoài cùng có `ORDER BY` nếu cần kết quả ổn định không?
18. **Khả năng mở rộng:** Nếu dữ liệu phải dùng chung nhiều job, có cần persisted staging với `job_id` không?

## 18. Tổng kết

**CTE, view và bảng tạm không chỉ là ba cách viết SQL tương đương**. Chúng giải quyết những phạm vi tái sử dụng khác nhau:

- **CTE**: đặt tên và phân rã logic **trong một câu SQL**. Nó thích hợp để làm một truy vấn phức tạp dễ đọc, có thể được optimizer tích hợp; **không tồn tại sau statement** và không mặc định tạo bảng vật lý.
- **View thông thường**: lưu **định nghĩa truy vấn lâu dài trong schema**, dùng chung qua nhiều statement, kết nối và ứng dụng theo quyền. Nó thuận tiện cho quy tắc nghiệp vụ ổn định, nhưng **không mặc định cache dữ liệu**.
- **Bảng tạm**: lưu **kết quả trung gian thật** trong phạm vi session/transaction, cho phép nhiều câu SQL cùng tái sử dụng hoặc biến đổi snapshot. Nó đòi hỏi quản lý vòng đời, kết nối, dữ liệu cũ và chi phí nạp/index.
- **Materialized view/bảng tổng hợp**: lựa chọn bổ sung khi muốn **chia sẻ kết quả đã tính qua nhiều session** và có cơ chế refresh/lưu trữ lâu dài.

Hãy chọn trước bằng hai câu hỏi: **“Kết quả/định nghĩa này cần được dùng lại ở phạm vi nào?”** và **“Người dùng cần dữ liệu mới mỗi lần đọc hay cùng một bản trung gian đã tính?”**. Sau đó mới quyết định cách tối ưu bằng index, cache, kế hoạch thực thi, transaction và quyền truy cập.

**Nguyên tắc cần nhớ:** *một statement thì nghĩ đến CTE; nhiều người dùng cần cùng định nghĩa thì nghĩ đến view; nhiều bước trong một phiên cần cùng dữ liệu đã tính thì nghĩ đến bảng tạm*. Đừng nhầm phạm vi tái sử dụng với tốc độ hay tính mới của dữ liệu.
