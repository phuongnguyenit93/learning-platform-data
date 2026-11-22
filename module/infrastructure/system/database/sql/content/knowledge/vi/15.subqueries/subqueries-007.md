# Truy vấn con trong SELECT, WHERE và HAVING

Khi viết SQL, đôi khi một câu truy vấn cần dùng **kết quả của một truy vấn khác** để tính toán, lọc dữ liệu hoặc quyết định có giữ một nhóm hay không. Chẳng hạn, bạn muốn hiển thị số đơn bên cạnh từng khách hàng, tìm đơn có số tiền lớn hơn mức trung bình, hoặc chỉ giữ khách hàng có số đơn vượt một ngưỡng thống kê. **Truy vấn con** (*subquery*) là cách đặt một câu `SELECT` bên trong một câu SQL khác để giải quyết những yêu cầu đó.

Ba vị trí thường gặp của truy vấn con là:

- **Trong `SELECT`:** tính **một giá trị** để hiển thị cùng mỗi dòng kết quả, ví dụ số đơn của một khách hàng.
- **Trong `WHERE`:** dùng kết quả truy vấn con để quyết định **hàng nào** được giữ lại, ví dụ khách có đơn đã thanh toán hoặc đơn có tiền lớn hơn trung bình.
- **Trong `HAVING`:** dùng kết quả truy vấn con để quyết định **nhóm nào** được giữ lại sau tổng hợp, ví dụ nhóm khách có giá trị trung bình cao hơn mức trung bình toàn hệ thống.

Bài học thuộc **Database SQL → Truy vấn con** và sử dụng **PostgreSQL** làm hệ quản trị để thực hành nhất quán. Phần lớn cú pháp cốt lõi như `SELECT` lồng nhau, `IN`, `EXISTS`, `NOT EXISTS`, `GROUP BY` và `HAVING` là những kiến thức SQL phổ biến.

## 1. Truy vấn con là gì?

Truy vấn con là câu `SELECT` được lồng vào một biểu thức hoặc một câu SQL lớn hơn. Ví dụ:

~~~sql
SELECT order_id, amount
FROM lab_sq195_orders
WHERE amount > (
    SELECT AVG(amount)
    FROM lab_sq195_orders
);
~~~

Trong câu trên:

1. Truy vấn con `SELECT AVG(amount) ...` trả về **một giá trị trung bình**.
2. Truy vấn ngoài đọc các đơn hàng.
3. Điều kiện `WHERE amount > (...)` so tiền của từng đơn với giá trị trung bình vừa xác định.

Dấu ngoặc `(...)` giúp chỉ ra ranh giới truy vấn con khi nó là một biểu thức. Truy vấn con không phải một bảng đã được lưu sẵn, cũng không tự cập nhật dữ liệu. Nó là một phần logic của câu SQL đang được thực thi.

### Ba hình dạng kết quả cần phân biệt

| Dạng kết quả truy vấn con | Ví dụ | Thường dùng với |
| --- | --- | --- |
| **Một giá trị** (*scalar*) | Một giá trị `AVG(amount)` | Cột biểu thức trong `SELECT`; so sánh `=`, `>`, `<` ở `WHERE`/`HAVING` |
| **Một cột, nhiều hàng** | Danh sách `customer_id` của các đơn PAID | `IN`, `NOT IN`, `ANY`, `ALL` |
| **Kiểm tra sự tồn tại hàng** | “Có ít nhất một đơn khớp khách này?” | `EXISTS`, `NOT EXISTS` |

Một truy vấn con còn có thể trả **nhiều cột** khi đặt trong `FROM` như một bảng dẫn xuất, hoặc khi dùng các phép so sánh hàng phù hợp. Nhưng **truy vấn con ở vị trí một biểu thức đơn lẻ trong `SELECT` phải phù hợp với yêu cầu một giá trị**, không thể tùy ý trả nhiều hàng hoặc nhiều cột.

### Truy vấn con độc lập và truy vấn con tương quan

Truy vấn con **không tương quan** (*uncorrelated*) không tham chiếu cột từ truy vấn ngoài:

~~~sql
SELECT AVG(amount)
FROM lab_sq195_orders;
~~~

Truy vấn con **tương quan** (*correlated*) có tham chiếu đến cột/bí danh của truy vấn ngoài:

~~~sql
SELECT COUNT(*)
FROM lab_sq195_orders AS o
WHERE o.customer_id = c.customer_id;
~~~

Biểu thức thứ hai giả định rằng `c` đã được khai báo trong truy vấn ngoài. Về **mặt ngữ nghĩa**, nó tính số đơn cho từng khách hàng đang xét. Bộ tối ưu SQL có thể biến đổi cách thực thi; không nên mặc định hệ quản trị buộc phải chạy truy vấn con vật lý một lần cho mỗi hàng.

## 2. Chuẩn bị dữ liệu mẫu

Các ví dụ trong bài sử dụng hai bảng **khách hàng** và **đơn hàng**. Hãy chạy đoạn sau **một lần** trong database PostgreSQL thực hành, khi chưa có hai bảng cùng tên:

~~~sql
CREATE TABLE lab_sq195_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(80) NOT NULL,
    region VARCHAR(20) NOT NULL
);

CREATE TABLE lab_sq195_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lab_sq195_customers(customer_id),
    order_status VARCHAR(12) NOT NULL
        CHECK (order_status IN ('NEW', 'PAID', 'CANCELLED')),
    amount NUMERIC(12, 2) CHECK (amount >= 0),
    ordered_on DATE NOT NULL
);

INSERT INTO lab_sq195_customers
    (customer_id, customer_name, region)
VALUES
    (1, 'An',   'North'),
    (2, 'Binh', 'South'),
    (3, 'Chi',  'Central'),
    (4, 'Dung', 'North'),
    (5, 'Em',   'South');

INSERT INTO lab_sq195_orders
    (order_id, customer_id, order_status, amount, ordered_on)
VALUES
    (101, 1, 'PAID',      120.00, DATE '2026-10-01'),
    (102, 1, 'PAID',       80.00, DATE '2026-10-02'),
    (103, 1, 'NEW',        40.00, DATE '2026-10-03'),
    (104, 2, 'PAID',      200.00, DATE '2026-10-04'),
    (105, 2, 'CANCELLED', 300.00, DATE '2026-10-05'),
    (106, 3, 'PAID',       70.00, DATE '2026-10-06'),
    (107, 3, 'PAID',       50.00, DATE '2026-10-07'),
    (108, 4, 'NEW',        90.00, DATE '2026-10-08'),
    (109, 4, 'PAID',        NULL,  DATE '2026-10-09'),
    (110, 2, 'PAID',       40.00, DATE '2026-10-10');
~~~

Bảng `lab_sq195_customers` có **5 khách**; khách **Em** chưa có đơn. Bảng `lab_sq195_orders` có **10 đơn** thuộc ba trạng thái; đơn **109** đã được đánh dấu PAID nhưng `amount IS NULL` nhằm quan sát cách tổng hợp và so sánh xử lý giá trị thiếu. Đó là dữ liệu thực hành, không phải mô hình nghiệp vụ thanh toán hoàn chỉnh.

Xem hai tập dữ liệu:

~~~sql
SELECT customer_id, customer_name, region
FROM lab_sq195_customers
ORDER BY customer_id;

SELECT order_id, customer_id, order_status, amount, ordered_on
FROM lab_sq195_orders
ORDER BY order_id;
~~~

| customer_id | customer_name | region |
| ---: | --- | --- |
| 1 | An | North |
| 2 | Binh | South |
| 3 | Chi | Central |
| 4 | Dung | North |
| 5 | Em | South |

| order_id | customer_id | order_status | amount |
| ---: | ---: | --- | ---: |
| 101 | 1 | PAID | 120.00 |
| 102 | 1 | PAID | 80.00 |
| 103 | 1 | NEW | 40.00 |
| 104 | 2 | PAID | 200.00 |
| 105 | 2 | CANCELLED | 300.00 |
| 106 | 3 | PAID | 70.00 |
| 107 | 3 | PAID | 50.00 |
| 108 | 4 | NEW | 90.00 |
| 109 | 4 | PAID | `NULL` |
| 110 | 2 | PAID | 40.00 |

Một số con số hữu ích cho việc hiểu ví dụ:

- Tổng **10 đơn**, trong đó **7 đơn PAID**, **2 đơn NEW** và **1 đơn CANCELLED**.
- Có **9 đơn có `amount` khác `NULL`**. Tổng các số tiền đã biết là **990.00**, nên trung bình của các đơn có tiền là **110.00**.
- Tổng tiền **PAID đã biết** là **560.00**; có **6 giá trị tiền PAID khác `NULL`**, nên trung bình PAID là xấp xỉ **93.33**.
- Mỗi khách có số đơn lần lượt: An **3**, Bình **3**, Chi **2**, Dũng **2**, Em **0**.

Chúng ta dùng `ORDER BY` ở truy vấn ngoài để đưa bảng kết quả về thứ tự dễ đối chiếu. **Truy vấn không có `ORDER BY` không được bảo đảm thứ tự hàng**, kể cả sau khi dữ liệu vừa được `INSERT`.

## 3. Truy vấn con trong SELECT: tạo một giá trị cho mỗi hàng

`SELECT` thường dùng để chọn các cột gốc. Tuy nhiên, một biểu thức trong danh sách `SELECT` cũng có thể là **truy vấn con trả về một giá trị** (*scalar subquery*).

Cấu trúc khái quát:

~~~sql
SELECT
    cot_goc,
    (
        SELECT mot_bieu_thuc
        FROM bang_khac
        WHERE dieu_kien
    ) AS cot_tinh_toan
FROM bang_goc;
~~~

Điều kiện quan trọng: ở vị trí này, truy vấn con phải trả **không quá một hàng và một cột** cho mỗi lần đánh giá. Nếu không có hàng nào thì giá trị scalar subquery là `NULL`; nếu trả nhiều hàng, PostgreSQL báo lỗi.

### 3.1. Truy vấn con tương quan: đếm đơn theo từng khách

Yêu cầu: “Liệt kê **mọi khách hàng**, kèm số đơn của từng người.”

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM lab_sq195_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM lab_sq195_customers AS c
ORDER BY c.customer_id;
~~~

Kết quả:

| customer_id | customer_name | order_count |
| ---: | --- | ---: |
| 1 | An | 3 |
| 2 | Binh | 3 |
| 3 | Chi | 2 |
| 4 | Dung | 2 |
| 5 | Em | 0 |

Cách đọc:

1. Truy vấn ngoài `FROM lab_sq195_customers AS c` tạo các hàng khách hàng.
2. Ở mỗi hàng về **mặt ngữ nghĩa**, điều kiện trong truy vấn con `o.customer_id = c.customer_id` chọn đơn của khách đó.
3. `COUNT(*)` trả về một số đếm. Ngay cả khi không có đơn, truy vấn tổng hợp không `GROUP BY` vẫn trả về **một dòng với `COUNT(*) = 0`**.
4. `AS order_count` đặt tên cột đầu ra; bảng khách hàng không được thêm một cột vật lý mới.

`c.customer_id` là **tham chiếu tương quan** đến hàng của truy vấn ngoài. Nếu bỏ điều kiện này, kết quả số đếm sẽ là **10 cho mọi khách hàng**, không còn là số đơn riêng của từng người.

### 3.2. SELECT có thể chứa nhiều scalar subquery

Giả sử muốn xem cả số đơn và **tổng tiền các đơn PAID**:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM lab_sq195_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count,
    (
        SELECT SUM(o.amount)
        FROM lab_sq195_orders AS o
        WHERE o.customer_id = c.customer_id
          AND o.order_status = 'PAID'
    ) AS paid_total
FROM lab_sq195_customers AS c
ORDER BY c.customer_id;
~~~

| customer_id | customer_name | order_count | paid_total |
| ---: | --- | ---: | ---: |
| 1 | An | 3 | 200.00 |
| 2 | Binh | 3 | 240.00 |
| 3 | Chi | 2 | 120.00 |
| 4 | Dung | 2 | `NULL` |
| 5 | Em | 0 | `NULL` |

Điểm dễ nhầm là **`COUNT(*)` và `SUM(amount)` xử lý tập rỗng khác nhau**:

- `COUNT(*)` trên không có đơn trả về **0**.
- `SUM(amount)` trên không có hàng phù hợp trả về **`NULL`**.
- `SUM(amount)` trên các hàng có số tiền **đều `NULL`** cũng trả về **`NULL`**. Khách Dũng có một đơn PAID (109) nhưng số tiền chưa được biết, nên `paid_total` là `NULL`, không phải một tổng 0 đã được xác nhận.

Nếu báo cáo **quy định** “không có tổng tính được thì hiển thị 0”, có thể dùng `COALESCE`:

~~~sql
SELECT
    c.customer_id,
    COALESCE(
        (
            SELECT SUM(o.amount)
            FROM lab_sq195_orders AS o
            WHERE o.customer_id = c.customer_id
              AND o.order_status = 'PAID'
        ),
        0
    ) AS paid_total_display
FROM lab_sq195_customers AS c
ORDER BY c.customer_id;
~~~

Nhưng việc hiển thị 0 cần thống nhất với nghiệp vụ, vì nó **gộp hai trường hợp khác nhau**: không có đơn PAID và có đơn PAID nhưng toàn bộ số tiền bị thiếu.

### 3.3. Truy vấn con không tương quan trong SELECT

Nếu không tham chiếu `c`, truy vấn con tính một giá trị chung:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (SELECT COUNT(*) FROM lab_sq195_orders) AS all_order_count
FROM lab_sq195_customers AS c
ORDER BY c.customer_id;
~~~

Mỗi hàng kết quả đều có `all_order_count = 10`, vì truy vấn con tính tổng số đơn của **cả hệ thống**. Điều này có thể hữu ích khi mỗi hàng cần kèm chỉ số toàn cục để so sánh.

Không tương quan nghĩa là kết quả truy vấn con **không thay đổi theo từng giá trị khách hàng**, trong cùng trạng thái dữ liệu mà câu truy vấn quan sát. Cách thực thi thực tế do bộ tối ưu quyết định.

## 4. Truy vấn con scalar trả nhiều hàng: lỗi và cách chọn một hàng

Giả sử viết:

~~~sql
-- SAI: mot khach co the co nhieu don.
SELECT
    c.customer_id,
    (
        SELECT o.amount
        FROM lab_sq195_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS one_amount
FROM lab_sq195_customers AS c;
~~~

Khách An có ba đơn, Bình có ba đơn; truy vấn con tương ứng trả **nhiều hàng**. Trong PostgreSQL, scalar subquery không thể lấy một giá trị duy nhất từ tập đó và sẽ báo lỗi gần nghĩa “more than one row returned by a subquery used as an expression”.

Có nhiều cách sửa, **tùy câu hỏi nghiệp vụ**:

| Câu hỏi | Cách làm |
| --- | --- |
| Tổng số tiền của khách là bao nhiêu? | `SELECT SUM(o.amount) ...` |
| Giá trị đơn lớn nhất của khách là bao nhiêu? | `SELECT MAX(o.amount) ...` |
| Đơn gần đây nhất của khách có số tiền bao nhiêu? | `ORDER BY o.ordered_on DESC, o.order_id DESC LIMIT 1` |
| Muốn xem **mọi** đơn và tiền của khách | Dùng `JOIN` hoặc truy vấn kết quả một dòng mỗi đơn, **không ép** thành scalar subquery |

Ví dụ lấy số tiền của **đơn mới nhất theo ngày, hòa ngày thì theo ID lớn hơn**:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT o.amount
        FROM lab_sq195_orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.ordered_on DESC, o.order_id DESC
        LIMIT 1
    ) AS newest_order_amount
FROM lab_sq195_customers AS c
ORDER BY c.customer_id;
~~~

| customer_id | newest_order_amount | Vì sao? |
| ---: | ---: | --- |
| 1 | 40.00 | Đơn 103 mới nhất của An |
| 2 | 40.00 | Đơn 110 mới nhất của Bình |
| 3 | 50.00 | Đơn 107 mới nhất của Chi |
| 4 | `NULL` | Đơn 109 mới nhất của Dũng có số tiền NULL |
| 5 | `NULL` | Em chưa có đơn nào |

Hai ô `NULL` ở dòng 4 và 5 có **nguyên nhân khác nhau**. Với Dũng, subquery **có hàng** nhưng giá trị `amount` là `NULL`; với Em, subquery **không có hàng** nên scalar subquery cũng trả `NULL`.

`LIMIT 1` đảm bảo nhiều nhất một hàng trong PostgreSQL, nhưng cần `ORDER BY` phản ánh đúng tiêu chí “mới nhất”. Nếu không có `ORDER BY`, một hàng được chọn tùy kế hoạch thực thi và không thể gọi là đơn mới nhất. Các hệ quản trị SQL khác có thể dùng `FETCH FIRST 1 ROW ONLY` hoặc `TOP 1`.

## 5. Truy vấn con trong WHERE: so sánh với giá trị tổng hợp

`WHERE` kiểm tra **hàng** của truy vấn ngoài. Một scalar subquery có thể cung cấp **ngưỡng động** cho phép so sánh thay vì viết cứng một con số.

### 5.1. Tìm đơn lớn hơn mức trung bình toàn bảng

~~~sql
SELECT o.order_id, o.customer_id, o.amount
FROM lab_sq195_orders AS o
WHERE o.amount > (
    SELECT AVG(o2.amount)
    FROM lab_sq195_orders AS o2
)
ORDER BY o.order_id;
~~~

Truy vấn con trả về trung bình **110.00** trên chín giá trị tiền khác `NULL`, nên kết quả là:

| order_id | customer_id | amount |
| ---: | ---: | ---: |
| 101 | 1 | 120.00 |
| 104 | 2 | 200.00 |
| 105 | 2 | 300.00 |

`AVG(amount)` bỏ qua `NULL` của đơn 109. Ở đơn 109, điều kiện `NULL > 110` tạo kết quả **UNKNOWN**, nên `WHERE` không giữ hàng đó.

Đơn 105 có trạng thái `CANCELLED` vẫn nằm trong kết quả, vì câu hỏi chỉ xét `amount` và **chưa yêu cầu lọc trạng thái**. Nếu mục tiêu là “đơn PAID lớn hơn mức trung bình của các đơn PAID”, phải nêu rõ hai điều kiện:

~~~sql
SELECT o.order_id, o.amount
FROM lab_sq195_orders AS o
WHERE o.order_status = 'PAID'
  AND o.amount > (
      SELECT AVG(o2.amount)
      FROM lab_sq195_orders AS o2
      WHERE o2.order_status = 'PAID'
  )
ORDER BY o.order_id;
~~~

Trung bình tiền PAID đã biết là `560 / 6 ≈ 93.33`; kết quả chỉ còn **101 (120.00)** và **104 (200.00)**. Cách đặt điều kiện cho truy vấn ngoài và truy vấn con phải nhất quán với định nghĩa tập dữ liệu cần so sánh.

### 5.2. Truy vấn con tương quan trong WHERE: so với trung bình của chính khách hàng

Yêu cầu: “Tìm đơn có tiền lớn hơn mức trung bình các đơn của **cùng khách hàng**”.

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    o.amount
FROM lab_sq195_orders AS o
WHERE o.amount > (
    SELECT AVG(o2.amount)
    FROM lab_sq195_orders AS o2
    WHERE o2.customer_id = o.customer_id
)
ORDER BY o.order_id;
~~~

Kết quả:

| order_id | customer_id | amount |
| ---: | ---: | ---: |
| 101 | 1 | 120.00 |
| 104 | 2 | 200.00 |
| 105 | 2 | 300.00 |
| 106 | 3 | 70.00 |

Lý do:

- An có ba đơn tổng 240, trung bình **80**, chỉ đơn 101 trị giá 120 cao hơn.
- Bình có ba đơn tổng 540, trung bình **180**, nên các đơn 104 và 105 cao hơn.
- Chi có hai đơn trung bình **60**, nên đơn 106 trị giá 70 cao hơn.
- Dũng có 90 và `NULL`, trung bình các giá trị đã biết là **90**, không có đơn nào lớn hơn 90.

Sự khác biệt nằm ở điều kiện tương quan `o2.customer_id = o.customer_id`. Nó khiến ngưỡng so sánh thay đổi theo **khách hàng của đơn đang xét**, thay vì một ngưỡng toàn bảng.

## 6. WHERE ... IN (subquery): kiểm tra một giá trị có thuộc tập kết quả

Khi truy vấn con trả **một cột nhưng nhiều hàng**, không thể đặt nó sau `=` như một scalar subquery. Nếu mục tiêu là kiểm tra **giá trị có nằm trong tập**, dùng `IN`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM lab_sq195_customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM lab_sq195_orders AS o
    WHERE o.order_status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Kết quả: **An, Bình, Chi, Dũng**. Em không có đơn nên không xuất hiện.

Truy vấn con trả các `customer_id` tương ứng đơn PAID, trong đó một ID có thể xuất hiện nhiều lần. `IN` kiểm tra **tư cách thành viên của tập**, chứ không tạo nhiều bản sao của khách hàng do có nhiều đơn khớp. Vì thế không cần thêm `DISTINCT` vào truy vấn con chỉ để làm đúng ngữ nghĩa `IN`.

So sánh:

~~~sql
-- Dung IN vi truy van con co the tra nhieu hang.
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM lab_sq195_orders AS o
)
~~~

và:

~~~sql
-- SAI trong truong hop co nhieu hang: dau = mong mot gia tri.
WHERE c.customer_id = (
    SELECT o.customer_id
    FROM lab_sq195_orders AS o
)
~~~

Biểu thức sau không hợp lệ với dữ liệu mẫu vì truy vấn con trả nhiều hàng. Nếu chỉ định lấy một hàng bằng `LIMIT 1`, nó sẽ thay đổi câu hỏi từ “có thuộc danh sách khách đã mua không?” thành “bằng một ID được chọn không?”, thường không phải ý định ban đầu.

## 7. EXISTS và NOT EXISTS: kiểm tra sự tồn tại

`EXISTS (subquery)` trả **TRUE nếu truy vấn con có ít nhất một hàng**; trả FALSE nếu không có hàng. Không quan trọng các giá trị được chọn bên trong là bao nhiêu.

### 7.1. Khách hàng có ít nhất một đơn NEW

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM lab_sq195_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_sq195_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'NEW'
)
ORDER BY c.customer_id;
~~~

Kết quả: **An** và **Dũng**. An có đơn 103 NEW, Dũng có đơn 108 NEW. Bình có đơn CANCELLED nhưng không có đơn NEW; Chi chỉ có đơn PAID; Em chưa có đơn.

Đây là **truy vấn con tương quan**: `c.customer_id` được lấy từ hàng khách hàng của truy vấn ngoài. `SELECT 1` chỉ là cách viết quen thuộc để nhấn mạnh rằng ta quan tâm **có hàng hay không**, không quan tâm lấy cột nào.

Về mặt logic, `EXISTS` không đòi truy vấn con trả đúng một hàng: **một hoặc nhiều hàng** đều cho TRUE.

### 7.2. Khách hàng chưa từng có đơn

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM lab_sq195_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_sq195_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Kết quả là **Em (ID 5)**. `NOT EXISTS` phù hợp với câu hỏi “không tồn tại một bản ghi liên quan nào”.

Nếu muốn tìm khách **không có đơn PAID** nhưng có thể có đơn khác, bổ sung điều kiện trạng thái **bên trong** truy vấn con:

~~~sql
SELECT c.customer_id, c.customer_name
FROM lab_sq195_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_sq195_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Với dữ liệu mẫu, chỉ Em thỏa vì An, Bình, Chi và Dũng đều có ít nhất một đơn PAID. Nếu đổi điều kiện thành `o.order_status = 'NEW'`, kết quả sẽ là **Bình, Chi và Em**.

### 7.3. IN và EXISTS khác nhau ở cách biểu đạt

| Nhu cầu | Dạng thường dùng |
| --- | --- |
| Khóa của hàng ngoài thuộc một danh sách một cột | `x IN (SELECT y ...)` |
| Có ít nhất một hàng liên quan thỏa nhiều điều kiện | `EXISTS (SELECT 1 ... WHERE y = x ...)` |
| Không có hàng liên quan nào | `NOT EXISTS (...)` |
| So với đúng một giá trị như trung bình hoặc cực đại | `x > (SELECT AVG(...) ...)` |

Với các khóa không `NULL` và điều kiện tương ứng, `IN` và `EXISTS` có thể cho cùng tập kết quả. Không nên khẳng định một cách viết **luôn nhanh hơn** cách kia: PostgreSQL và các bộ tối ưu hiện đại có thể chuyển đổi chúng thành những kế hoạch thực thi tương đương, tùy truy vấn, dữ liệu và chỉ mục.

## 8. Bẫy NULL khi dùng NOT IN với truy vấn con

`NOT IN` dễ gây nhầm nếu **tập kết quả truy vấn con chứa `NULL`**. Xét ví dụ PostgreSQL:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM lab_sq195_customers AS c
WHERE c.customer_id NOT IN (
    SELECT 1
    UNION ALL
    SELECT NULL::integer
)
ORDER BY c.customer_id;
~~~

Truy vấn con trả tập giá trị **1 và `NULL`**. Kết quả của truy vấn ngoài là **không có dòng nào**, dù khách ID 2, 3, 4, 5 đều không bằng 1. Vì sao?

- Với ID 1, điều kiện “không thuộc tập” là FALSE vì đã có giá trị 1 khớp.
- Với ID 2, 3, 4, 5, không có giá trị cụ thể nào khớp, nhưng việc so sánh với `NULL` cho kết quả **UNKNOWN**. Kết quả `NOT IN` do đó không phải TRUE.
- `WHERE` chỉ giữ những hàng có điều kiện TRUE, nên tất cả đều bị loại.

Đây là **logic ba giá trị của SQL**, không phải lỗi cú pháp.

Nếu bài toán là “khách hàng không có đơn”, ta đã có điều kiện `NOT EXISTS` an toàn theo ý nghĩa tồn tại:

~~~sql
SELECT c.customer_id, c.customer_name
FROM lab_sq195_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_sq195_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Trong **bảng đơn mẫu**, `orders.customer_id` đã được khai báo `NOT NULL`, nên truy vấn `customer_id NOT IN (SELECT customer_id FROM lab_sq195_orders)` cũng có thể trả **Em** như mong đợi. Nhưng nếu sau này truy vấn con lấy một cột **có thể `NULL`** hoặc dùng biểu thức sinh `NULL`, `NOT IN` có thể đổi hành vi. `NOT EXISTS` thường diễn đạt “không có bản ghi liên quan” rõ ràng hơn.

Khi thực sự cần `NOT IN`, có thể lọc `NULL` từ truy vấn con nếu quy tắc dữ liệu cho phép:

~~~sql
WHERE c.customer_id NOT IN (
    SELECT some_nullable_id
    FROM some_table
    WHERE some_nullable_id IS NOT NULL
)
~~~

Ví dụ này **là mẫu cú pháp**, không chạy được nếu chưa có `some_table`. Không dùng việc loại `NULL` như một mẹo máy móc khi giá trị thiếu có ý nghĩa nghiệp vụ cần được giải quyết riêng.

## 9. Truy vấn con trong HAVING: so sánh điều kiện của nhóm

`WHERE` lọc **hàng trước tổng hợp**; `HAVING` lọc **nhóm sau `GROUP BY`**. Truy vấn con trong `HAVING` thường tạo **một ngưỡng thống kê** để so với `COUNT`, `SUM`, `AVG` hoặc một điều kiện tổng hợp.

### 9.1. Khách hàng có mức chi trung bình cao hơn toàn hệ thống

~~~sql
SELECT
    o.customer_id,
    COUNT(*) AS order_count,
    AVG(o.amount) AS customer_avg_amount
FROM lab_sq195_orders AS o
GROUP BY o.customer_id
HAVING AVG(o.amount) > (
    SELECT AVG(o2.amount)
    FROM lab_sq195_orders AS o2
)
ORDER BY o.customer_id;
~~~

Giá trị trung bình toàn bảng là **110.00**, còn trung bình theo khách là:

| customer_id | order_count | customer_avg_amount | So với 110.00 |
| ---: | ---: | ---: | --- |
| 1 | 3 | 80.00 | Không đạt |
| 2 | 3 | 180.00 | Đạt |
| 3 | 2 | 60.00 | Không đạt |
| 4 | 2 | 90.00 | Không đạt |

Kết quả câu `HAVING` chỉ gồm **Bình (ID 2)** với `customer_avg_amount = 180.00`. Khách Em không có đơn nên không tạo thành nhóm trong truy vấn bắt đầu từ bảng `orders`.

Đây là ví dụ điển hình: `AVG(o.amount)` bên ngoài tính **trung bình cho từng nhóm khách**, còn `SELECT AVG(o2.amount)` bên trong tính **mức trung bình toàn bộ đơn** để làm ngưỡng.

### 9.2. Vì sao không đặt AVG của nhóm vào WHERE?

Truy vấn dưới đây **sai**:

~~~sql
-- SAI: aggregate cua cung cap truy van khong thuoc giai doan WHERE.
SELECT o.customer_id, AVG(o.amount)
FROM lab_sq195_orders AS o
WHERE AVG(o.amount) > (
    SELECT AVG(o2.amount)
    FROM lab_sq195_orders AS o2
)
GROUP BY o.customer_id;
~~~

`WHERE` xử lý từng hàng **trước `GROUP BY`**, nên giá trị `AVG(o.amount)` của nhóm khách chưa tồn tại ở cấp truy vấn ngoài. Cần chuyển điều kiện tổng hợp của nhóm sang `HAVING`.

Ngược lại, có thể dùng **một truy vấn con tổng hợp ở phía phải của điều kiện `WHERE`**, như mục 5, vì kết quả `AVG(...)` được tính **trong cấp truy vấn con riêng**. Sự khác biệt là cấp nào đang sở hữu phép tổng hợp, không phải việc chữ `AVG` có xuất hiện ở đâu trong toàn bộ câu SQL.

### 9.3. Kết hợp WHERE trước nhóm và subquery trong HAVING

Yêu cầu: “Chỉ xét **đơn PAID**; trong số khách có các đơn ấy, chọn khách có tổng tiền PAID lớn hơn **hai lần mức tiền trung bình của một đơn PAID**”.

~~~sql
SELECT
    o.customer_id,
    COUNT(*) AS paid_order_count,
    SUM(o.amount) AS paid_total
FROM lab_sq195_orders AS o
WHERE o.order_status = 'PAID'
GROUP BY o.customer_id
HAVING SUM(o.amount) > (
    SELECT AVG(o2.amount) * 2
    FROM lab_sq195_orders AS o2
    WHERE o2.order_status = 'PAID'
)
ORDER BY o.customer_id;
~~~

Mức trung bình của các số tiền PAID đã biết xấp xỉ **93.33**; hai lần trung bình xấp xỉ **186.67**. Tổng tiền PAID theo khách là:

| customer_id | paid_order_count | paid_total | Có lớn hơn 186.67? |
| ---: | ---: | ---: | --- |
| 1 | 2 | 200.00 | Có |
| 2 | 2 | 240.00 | Có |
| 3 | 2 | 120.00 | Không |
| 4 | 1 | `NULL` | Không có tổng để so sánh |

Kết quả là **An và Bình**.

Lưu ý: điều kiện `WHERE o.order_status = 'PAID'` quyết định **những đơn được cộng trong từng nhóm**. Truy vấn con cũng lọc PAID để ngưỡng so sánh dùng **cùng phạm vi dữ liệu**. `HAVING` sau cùng quyết định **nhóm khách nào được giữ**.

Nếu quy tắc muốn so với “hai lần mức trung bình của **mọi đơn**”, phải bỏ lọc PAID **bên trong subquery** và chấp nhận rằng kết quả có thể đổi. Thay đổi phạm vi bên trong và bên ngoài là thay đổi ý nghĩa báo cáo, không đơn thuần là tối ưu cú pháp.

## 10. Truy vấn con trong HAVING cũng có thể tương quan

Truy vấn con trong `HAVING` có thể tham chiếu **khóa nhóm của truy vấn ngoài**. Ví dụ: “Khách nào có giá trị đơn hàng trung bình **cao hơn mức trung bình của các đơn thuộc cùng khu vực của khách đó**?”.

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    c.region,
    AVG(o.amount) AS customer_avg_amount
FROM lab_sq195_customers AS c
JOIN lab_sq195_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY
    c.customer_id,
    c.customer_name,
    c.region
HAVING AVG(o.amount) > (
    SELECT AVG(o2.amount)
    FROM lab_sq195_orders AS o2
    JOIN lab_sq195_customers AS c2
        ON c2.customer_id = o2.customer_id
    WHERE c2.region = c.region
)
ORDER BY c.customer_id;
~~~

Cách hiểu:

1. Truy vấn ngoài nhóm các đơn theo khách hàng và khu vực; `AVG(o.amount)` là **trung bình đơn của khách**.
2. Truy vấn con lấy các đơn thuộc những khách trong **cùng khu vực** với nhóm đang xét, nhờ `c2.region = c.region`.
3. `HAVING` chỉ giữ nhóm khách có trung bình riêng **cao hơn** trung bình đơn của khu vực ấy.

Với dữ liệu mẫu:

- Khu vực **North** có các số tiền đã biết của An và Dũng: `120, 80, 40, 90`. Trung bình khu vực **82.50**. An trung bình 80, Dũng trung bình **90**, nên chỉ Dũng cao hơn.
- Khu vực **South** có các đơn của Bình, trung bình **180**; Em chưa có đơn nên không đóng góp số tiền. Bình bằng ngưỡng, không **cao hơn**.
- Khu vực **Central** chỉ có các đơn của Chi, trung bình **60**, nên Chi bằng ngưỡng.

Kết quả là **Dũng (ID 4)** với `customer_avg_amount = 90.00`.

Phần tham chiếu tương quan `c.region` là cột được khai báo trong `GROUP BY` ngoài, nên dùng nó để xác định khu vực cho mỗi nhóm là rõ ràng. Không được tùy ý tham chiếu một cột của hàng ngoài **không thuộc nhóm và không được tổng hợp** trong `HAVING`, vì một nhóm có thể chứa nhiều giá trị khác nhau.

### 10.1. HAVING với truy vấn con trả về danh sách

`HAVING` không bị giới hạn chỉ dùng scalar subquery. Khi cần lọc nhóm theo một danh sách khóa, có thể dùng `IN`:

~~~sql
SELECT
    o.customer_id,
    COUNT(*) AS order_count
FROM lab_sq195_orders AS o
GROUP BY o.customer_id
HAVING o.customer_id IN (
    SELECT c.customer_id
    FROM lab_sq195_customers AS c
    WHERE c.region = 'North'
)
ORDER BY o.customer_id;
~~~

Kết quả gồm **An (3 đơn)** và **Dũng (2 đơn)**. Tuy nhiên, vì đây chỉ là điều kiện trên **khóa nhóm**, nhiều trường hợp viết điều kiện vào `WHERE` hoặc dùng `JOIN` trước nhóm sẽ dễ đọc hơn:

~~~sql
SELECT o.customer_id, COUNT(*) AS order_count
FROM lab_sq195_orders AS o
WHERE o.customer_id IN (
    SELECT c.customer_id
    FROM lab_sq195_customers AS c
    WHERE c.region = 'North'
)
GROUP BY o.customer_id
ORDER BY o.customer_id;
~~~

Hai truy vấn này cùng kết quả trên dữ liệu mẫu. Điểm cần phân biệt là **điều kiện dựa trên hàng/khóa nhóm** khác với điều kiện cần **tính `SUM` hay `AVG` của nhóm**; điều kiện tổng hợp buộc phải được xử lý sau khi nhóm.

## 11. HAVING không có GROUP BY vẫn có thể dùng subquery

Nếu không viết `GROUP BY` nhưng truy vấn dùng các hàm tổng hợp, toàn bộ tập hàng có thể được xem như **một nhóm**:

~~~sql
SELECT COUNT(*) AS all_order_count
FROM lab_sq195_orders
HAVING COUNT(*) > (
    SELECT COUNT(*)
    FROM lab_sq195_orders
    WHERE order_status = 'PAID'
);
~~~

Tổng tất cả đơn là **10**, tổng đơn PAID là **7**; điều kiện `10 > 7` đúng, nên kết quả trả **một dòng** với `all_order_count = 10`.

Nếu thay điều kiện bằng `COUNT(*) > 20`, nhóm duy nhất không đạt yêu cầu và truy vấn **không trả dòng nào**. Không nên nhầm “không có dòng kết quả do `HAVING` loại” với “trả một dòng có số đếm bằng 0”.

Trong các truy vấn nhóm thông thường, giá trị cột trong `HAVING` phải tuân thủ quy tắc nhóm và tổng hợp của hệ quản trị, dù nó có chứa subquery hay không.

## 12. Truy vấn con lồng nhau và phạm vi bí danh

Truy vấn con có thể chứa **một truy vấn con khác**. Ví dụ, chọn khách hàng có số đơn **lớn hơn số đơn trung bình của những khách đã từng có đơn**:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM lab_sq195_customers AS c
WHERE (
    SELECT COUNT(*)
    FROM lab_sq195_orders AS o
    WHERE o.customer_id = c.customer_id
) > (
    SELECT AVG(t.order_count)
    FROM (
        SELECT COUNT(*) AS order_count
        FROM lab_sq195_orders
        GROUP BY customer_id
    ) AS t
)
ORDER BY c.customer_id;
~~~

Phần `FROM (SELECT ... GROUP BY customer_id) AS t` là **bảng dẫn xuất**, có bốn hàng số đếm của những khách đã có đơn: **3, 3, 2, 2**. Trung bình của bốn số đếm là **2.5**, nên truy vấn ngoài chọn **An và Bình**, mỗi người có 3 đơn.

**Quan trọng về phạm vi thống kê:** khách Em chưa có đơn nên **không xuất hiện** trong bảng dẫn xuất `t`. Vì vậy con số 2.5 là trung bình trên **khách có đơn**, không phải trung bình trên **toàn bộ năm khách**. Nếu muốn trung bình kể cả khách có 0 đơn, phải bắt đầu từ `customers` và dùng `LEFT JOIN` hoặc một phương pháp đếm tương đương, khi đó trung bình là `10 / 5 = 2` và nhóm khách có số đơn lớn hơn 2 vẫn là An, Bình trong bộ dữ liệu này nhưng ngưỡng đã khác.

Trong truy vấn trên:

- `c` là bí danh khách hàng thuộc truy vấn ngoài cùng.
- `o` thuộc scalar subquery đếm đơn.
- `t` là bí danh của bảng dẫn xuất trong scalar subquery tính trung bình.

Bí danh chỉ có hiệu lực theo **phạm vi truy vấn**; cần đặt tên khác nhau và viết điều kiện tương quan rõ ràng để tránh tham chiếu nhầm cột ở cấp ngoài hay cấp trong.

## 13. So sánh subquery với JOIN và CTE

Truy vấn con không phải cách duy nhất để giải quyết những vấn đề trên. `JOIN` và **CTE** (`WITH ... AS (...)`) cũng có thể trả kết quả tương đương, đôi khi dễ bảo trì hơn.

### 13.1. Đếm đơn: scalar subquery so với LEFT JOIN + GROUP BY

Phiên bản truy vấn con trong `SELECT`:

~~~sql
SELECT
    c.customer_id,
    (
        SELECT COUNT(*)
        FROM lab_sq195_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM lab_sq195_customers AS c
ORDER BY c.customer_id;
~~~

Phiên bản `LEFT JOIN` và tổng hợp:

~~~sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count
FROM lab_sq195_customers AS c
LEFT JOIN lab_sq195_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Cả hai trả số đếm **3, 3, 2, 2, 0** theo ID khách. Ở phiên bản `LEFT JOIN`, phải dùng `COUNT(o.order_id)` thay cho `COUNT(*)`, vì khách Em không có đơn vẫn sinh một hàng ngoài với giá trị bên phải là `NULL`.

Nếu bổ sung nhiều bảng con một–nhiều vào cùng `JOIN`, kết quả có thể bị nhân hàng; khi đó cần xác định đúng độ hạt trước khi đếm/cộng. Scalar subquery đôi khi giúp giữ một hàng theo khách dễ dàng hơn, còn `JOIN` có thể hữu ích khi cần nhiều cột hoặc thực hiện tính toán tập hợp rộng.

### 13.2. Chuyển điều kiện HAVING thành WHERE ở cấp ngoài CTE

Truy vấn dùng `HAVING`:

~~~sql
SELECT customer_id, AVG(amount) AS avg_amount
FROM lab_sq195_orders
GROUP BY customer_id
HAVING AVG(amount) > (
    SELECT AVG(amount)
    FROM lab_sq195_orders
);
~~~

Có thể viết lại:

~~~sql
WITH customer_averages AS (
    SELECT customer_id, AVG(amount) AS avg_amount
    FROM lab_sq195_orders
    GROUP BY customer_id
)
SELECT customer_id, avg_amount
FROM customer_averages
WHERE avg_amount > (
    SELECT AVG(amount)
    FROM lab_sq195_orders
)
ORDER BY customer_id;
~~~

Hai truy vấn cùng giữ **Bình** trên dữ liệu mẫu. Không có mâu thuẫn với quy tắc “`WHERE` không được dùng hàm tổng hợp của cùng cấp”:

- Trong CTE `customer_averages`, phép `AVG` đã được tính **tại cấp truy vấn trong**.
- Ở truy vấn ngoài, `avg_amount` là **cột kết quả thông thường**, nên `WHERE avg_amount > (...)` hợp lệ.

### 13.3. Đừng thay IN bằng JOIN mà bỏ qua khả năng nhân hàng

Truy vấn:

~~~sql
SELECT c.customer_id
FROM lab_sq195_customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM lab_sq195_orders AS o
);
~~~

trả mỗi khách có đơn **một lần**. Nếu thay bằng:

~~~sql
SELECT c.customer_id
FROM lab_sq195_customers AS c
JOIN lab_sq195_orders AS o
    ON o.customer_id = c.customer_id;
~~~

thì An và Bình xuất hiện **ba lần**, Chi và Dũng **hai lần**, vì kết quả có một hàng cho **mỗi đơn**. `JOIN` không tương đương `IN` về số hàng nếu quan hệ là một–nhiều. Có thể dùng `DISTINCT`, tổng hợp hoặc `EXISTS` tùy câu hỏi; ưu tiên diễn đạt đúng **độ hạt kết quả** ngay từ đầu.

## 14. Các vấn đề NULL trong SELECT, WHERE và HAVING

`NULL` có nhiều ảnh hưởng khác nhau, tùy **hình dạng** của subquery và toán tử bên ngoài:

| Tình huống | Kết quả trong PostgreSQL |
| --- | --- |
| Scalar subquery không trả hàng nào | `NULL` |
| Scalar subquery trả đúng một hàng với cột `NULL` | `NULL` |
| Scalar subquery trả nhiều hàng | Lỗi vì cần một giá trị |
| `COUNT(*)` trong subquery tổng hợp trên tập rỗng (không `GROUP BY`) | Một hàng mang số **0** |
| `SUM(amount)`/`AVG(amount)` trên tập không có giá trị khác NULL | Một hàng mang `NULL` |
| `WHERE amount > (SELECT ... )`, bên phải là `NULL` | Điều kiện UNKNOWN; hàng không được giữ |
| `HAVING SUM(amount) > (SELECT ... )`, vế so sánh `NULL` | UNKNOWN; nhóm không được giữ |
| `EXISTS (SELECT ... )` | TRUE/FALSE theo **có hay không có hàng**, không phụ thuộc giá trị cột được chọn |
| `NOT IN (subquery)` với danh sách có `NULL` | Có thể cho UNKNOWN và loại cả hàng tưởng như “không thuộc danh sách” |

Ví dụ khi cả bảng con dùng để tính `AVG` đều không có hàng phù hợp:

~~~sql
SELECT o.order_id, o.amount
FROM lab_sq195_orders AS o
WHERE o.amount > (
    SELECT AVG(o2.amount)
    FROM lab_sq195_orders AS o2
    WHERE o2.order_status = 'NOT_A_REAL_STATUS'
);
~~~

Vì không có đơn nào mang trạng thái đó, subquery tổng hợp trả `AVG = NULL`; phép so sánh với `NULL` là UNKNOWN, nên câu ngoài **không trả dòng**. Đây là ví dụ minh họa cách xử lý dữ liệu, không phải một giá trị trạng thái hợp lệ trong mô hình bảng mẫu.

Nếu muốn phân biệt **không có đơn**, **có đơn nhưng thiếu tiền** và **có tiền**, đừng chỉ xem `SUM`. Có thể tính cả `COUNT(*)` và `COUNT(amount)`:

~~~sql
SELECT
    c.customer_id,
    (
        SELECT COUNT(*)
        FROM lab_sq195_orders AS o
        WHERE o.customer_id = c.customer_id
          AND o.order_status = 'PAID'
    ) AS paid_order_count,
    (
        SELECT COUNT(o.amount)
        FROM lab_sq195_orders AS o
        WHERE o.customer_id = c.customer_id
          AND o.order_status = 'PAID'
    ) AS paid_orders_with_amount
FROM lab_sq195_customers AS c
ORDER BY c.customer_id;
~~~

| customer_id | paid_order_count | paid_orders_with_amount |
| ---: | ---: | ---: |
| 1 | 2 | 2 |
| 2 | 2 | 2 |
| 3 | 2 | 2 |
| 4 | 1 | 0 |
| 5 | 0 | 0 |

Nhờ đó, nhóm Dũng (có đơn PAID nhưng thiếu số tiền) không bị gộp với Em (chưa có đơn nào).

## 15. Hiệu năng và cách chọn hình thức truy vấn

Về mặt tư duy, truy vấn con tương quan thường được giải thích là “xem hàng ngoài rồi tìm hàng liên quan trong bảng con”. Nhưng không nên suy luận rằng **mọi truy vấn con tương quan đều chắc chắn chạy chậm hơn JOIN**. Các bộ tối ưu như PostgreSQL có thể tối ưu `EXISTS`, `IN` và một số truy vấn con thành các phép nối hoặc kế hoạch tương đương.

Để viết truy vấn có khả năng hoạt động tốt khi dữ liệu lớn:

1. **Chọn đúng hình dạng kết quả.** Cần một giá trị thì dùng scalar subquery; kiểm tra tồn tại thì `EXISTS`; kiểm tra thuộc tập thì `IN`; so nhóm với ngưỡng thì `HAVING`.
2. **Giới hạn dữ liệu trong truy vấn con theo đúng nghiệp vụ.** Nếu chỉ cần các đơn PAID, đặt điều kiện `order_status = 'PAID'` ở truy vấn liên quan.
3. **Dùng khóa liên kết rõ ràng.** Điều kiện `o.customer_id = c.customer_id` thường tận dụng được chỉ mục ở phía thích hợp, tùy kiểu kế hoạch.
4. **Tránh scalar subquery có thể trả nhiều hàng.** Dùng phép tổng hợp, lựa chọn `ORDER BY ... LIMIT 1` có chủ đích, hoặc chuyển sang một kết quả nhiều dòng.
5. **Không nhân hàng vô ý khi thay subquery bằng JOIN.** Tách và tổng hợp bảng chi tiết trước nếu cần một hàng cho mỗi khách hoặc mỗi đơn.
6. **Kiểm tra kế hoạch với dữ liệu thực tế.** Trên bảng chỉ có vài dòng, sự khác biệt hiệu năng thường không đáng kể.

Ví dụ PostgreSQL có thể xem kế hoạch:

~~~sql
EXPLAIN
SELECT c.customer_id, c.customer_name
FROM lab_sq195_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_sq195_orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

`EXPLAIN` cho thấy kế hoạch mà hệ thống dự kiến sử dụng, không cần chạy `EXPLAIN ANALYZE` chỉ để học cú pháp. Với bảng thật lớn, cột khóa ngoại `lab_sq195_orders.customer_id` có thể cần chỉ mục phục vụ tìm đơn theo khách:

~~~sql
-- DDL minh hoa: chi tao neu co ly do hieu nang phu hop.
CREATE INDEX lab_sq195_orders_customer_idx
ON lab_sq195_orders (customer_id);
~~~

Lệnh `CREATE INDEX` tạo đối tượng vật lý thật nếu chạy; nó không phải điều kiện bắt buộc để truy vấn con đúng về ngữ nghĩa. Chỉ mục tốn không gian và có chi phí duy trì khi ghi dữ liệu. Bộ tối ưu có thể vẫn chọn quét bảng nếu ít hàng hoặc cách quét khác có chi phí thấp hơn.

### 15.1. Cẩn thận với phép so sánh và thứ tự thực thi

Trình tự **logic** của truy vấn tổng hợp thường được diễn giải là `FROM/JOIN → WHERE → GROUP BY → HAVING → SELECT → ORDER BY`. Tuy nhiên, đó là mô hình **ngữ nghĩa**, không phải lịch trình vật lý bắt buộc của máy chủ.

Tương tự, scalar subquery độc lập có thể được tính và tái sử dụng một cách tối ưu, trong khi correlated subquery có thể được chuyển thành phép nối. Khi phân tích đúng/sai, hãy dựa vào **quy tắc SQL và số hàng được phép trả**, không dựa vào giả định máy chủ luôn “chạy truy vấn trong trước rồi mới chạy truy vấn ngoài một lần duy nhất”.

## 16. Khác biệt giữa các SQL dialect

Các hệ quản trị SQL lớn đều hỗ trợ truy vấn con trong `SELECT`, `WHERE` và `HAVING`, nhưng có khác biệt ở **giới hạn, kiểu, cú pháp lấy hàng đầu tiên** và cách tối ưu:

| Vấn đề | PostgreSQL | Ghi chú ở hệ khác |
| --- | --- | --- |
| Scalar subquery trong `SELECT` | `(SELECT ...) AS alias` | Có ở MySQL, SQL Server, SQLite, Oracle; cần không quá một hàng trong ngữ cảnh một giá trị |
| Subquery nhiều hàng trong `WHERE` | `IN`, `EXISTS`, `ANY`/`ALL` | Hỗ trợ phổ biến, nhưng cú pháp và chi tiết tối ưu có thể khác |
| Subquery trong `HAVING` | Có, gồm subquery tương quan hợp lệ | Hỗ trợ phổ biến; các quy tắc cột nhóm/phụ thuộc hàm có khác biệt |
| Lấy một hàng có thứ tự | `ORDER BY ... LIMIT 1` hoặc `FETCH FIRST 1 ROW ONLY` | SQL Server thường dùng `TOP (1)`/`OFFSET FETCH`, Oracle hiện đại có `FETCH FIRST` |
| Bí danh `SELECT` trong `HAVING` cùng cấp | PostgreSQL không cho dùng trực tiếp alias tổng hợp theo cách MySQL có thể cho phép | Dùng lại biểu thức tổng hợp hoặc CTE/truy vấn con ở cấp ngoài |
| Giá trị `NULL` và `NOT IN` | Logic ba giá trị | Quy tắc SQL phổ biến, không phải vấn đề riêng của PostgreSQL |
| Ép kiểu ngắn `::numeric` | Cú pháp PostgreSQL | Khi chuyển hệ, dùng `CAST(... AS ...)` tương ứng |

Trong **SQL Server**, ví dụ tìm một đơn mới nhất thường viết bằng `TOP (1)`:

~~~sql
-- Vi du T-SQL, gia dinh co bang dbo.orders.
SELECT TOP (1) o.amount
FROM dbo.orders AS o
WHERE o.customer_id = 1
ORDER BY o.ordered_on DESC, o.order_id DESC;
~~~

Trong **PostgreSQL**, cách tương ứng là:

~~~sql
SELECT o.amount
FROM lab_sq195_orders AS o
WHERE o.customer_id = 1
ORDER BY o.ordered_on DESC, o.order_id DESC
LIMIT 1;
~~~

Hai ví dụ ở đây **không cùng tên bảng**, chỉ để so sánh cú pháp giới hạn một hàng. Khi dùng trong scalar subquery, cần đảm bảo **điều kiện tương quan** và **tiêu chí thứ tự** khớp đúng yêu cầu nghiệp vụ.

## 17. Những lỗi thường gặp

| Cách viết hoặc suy luận | Vấn đề | Hướng giải quyết |
| --- | --- | --- |
| `SELECT (SELECT amount FROM orders WHERE customer_id = c.customer_id)` | Mỗi khách có thể có nhiều đơn → scalar subquery trả nhiều hàng | Dùng `SUM`/`MAX`, `ORDER BY ... LIMIT 1` hoặc JOIN theo đúng số hàng muốn hiển thị |
| `WHERE customer_id = (SELECT customer_id FROM orders)` | Vế phải trả nhiều ID | Dùng `IN` hoặc `EXISTS` khi mục tiêu là kiểm tra thuộc/tồn tại |
| Quên `o.customer_id = c.customer_id` trong correlated subquery | Đếm/tính toàn bộ đơn cho mọi khách | Viết rõ điều kiện liên kết với bí danh ngoài |
| `WHERE AVG(o.amount) > ...` ở cùng cấp đang `GROUP BY` | `WHERE` không lọc giá trị tổng hợp của nhóm | Đặt ở `HAVING` |
| `HAVING average_amount > ...` với alias `SELECT` trong PostgreSQL | Alias đầu ra không có phạm vi như mong đợi tại `HAVING` | Lặp `AVG(amount)` hoặc dùng CTE |
| `NOT IN (subquery)` khi subquery có `NULL` | UNKNOWN có thể khiến không hàng nào được chọn | Ưu tiên `NOT EXISTS` hoặc lọc `NULL` đúng yêu cầu |
| Cho rằng `EXISTS (SELECT NULL ...)` luôn là FALSE | `EXISTS` xét **số hàng**, không xét giá trị NULL | Dựa vào điều kiện `WHERE` trong subquery để định nghĩa hàng khớp |
| Coi `SUM(amount) IS NULL` luôn có nghĩa không có đơn | Có thể có đơn nhưng tiền ở mọi hàng đều NULL | Dùng thêm `COUNT(*)`/`COUNT(amount)` để phân biệt |
| Dùng `LIMIT 1` nhưng không có `ORDER BY` và gọi là “đơn mới nhất” | Không xác định hàng nào được chọn | Thêm `ORDER BY` theo ngày và khóa phụ |
| Thay `IN` bằng `JOIN` rồi quên quan hệ 1–N | JOIN có thể lặp khách theo số đơn | Giữ `IN`/`EXISTS` hoặc kiểm soát độ hạt bằng tổng hợp |
| Đặt lọc PAID chỉ ngoài truy vấn nhưng ngưỡng trung bình tính cả CANCELLED | Hai phía dùng hai tập dữ liệu khác nhau | Xác nhận rõ tập dữ liệu trong cả subquery và truy vấn ngoài |
| Coi truy vấn con tương quan luôn chậm | Kế hoạch phụ thuộc bộ tối ưu và dữ liệu | Kiểm tra `EXPLAIN`, chỉ mục và kế hoạch thực tế |

## 18. Bài tập thực hành có đáp án

Các bài dưới đây dựa trên **5 khách hàng và 10 đơn** của mục 2. Hãy thử viết SQL, xác định truy vấn con trả về **một giá trị, một danh sách hay kiểm tra tồn tại**, rồi đối chiếu kết quả. Các câu đều chỉ đọc dữ liệu.

### Bài 1 — Đếm đơn trong SELECT

**Yêu cầu:** hiển thị ID, tên khách và số đơn của mỗi khách; kể cả khách chưa mua.

**Đáp án:**

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM lab_sq195_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM lab_sq195_customers AS c
ORDER BY c.customer_id;
~~~

Các số đếm theo ID 1–5 là **3, 3, 2, 2, 0**.

### Bài 2 — Lấy giá trị của đơn gần đây nhất

**Yêu cầu:** lấy tên khách và số tiền của đơn gần đây nhất theo `ordered_on`, khi cùng ngày dùng `order_id` lớn hơn; không yêu cầu khách phải có đơn.

**Đáp án:**

~~~sql
SELECT
    c.customer_name,
    (
        SELECT o.amount
        FROM lab_sq195_orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.ordered_on DESC, o.order_id DESC
        LIMIT 1
    ) AS newest_amount
FROM lab_sq195_customers AS c
ORDER BY c.customer_id;
~~~

Theo thứ tự An, Bình, Chi, Dũng, Em: **40.00, 40.00, 50.00, NULL, NULL**. Dũng có đơn mới nhất với tiền NULL; Em không có đơn.

### Bài 3 — Đơn lớn hơn trung bình các đơn trong hệ thống

**Yêu cầu:** lấy ID những đơn có `amount` lớn hơn trung bình của **mọi số tiền đã biết**.

**Đáp án:**

~~~sql
SELECT o.order_id, o.amount
FROM lab_sq195_orders AS o
WHERE o.amount > (
    SELECT AVG(amount)
    FROM lab_sq195_orders
)
ORDER BY o.order_id;
~~~

Trung bình là **110.00**; ID kết quả **101, 104, 105**.

### Bài 4 — Tìm khách đã có đơn PAID bằng IN

**Đáp án:**

~~~sql
SELECT c.customer_id, c.customer_name
FROM lab_sq195_customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM lab_sq195_orders AS o
    WHERE o.order_status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Kết quả **An, Bình, Chi, Dũng**. Dùng `IN` vì truy vấn con có thể trả nhiều `customer_id`.

### Bài 5 — Khách có đơn NEW bằng EXISTS

**Yêu cầu:** lấy các khách có ít nhất một đơn NEW.

**Đáp án:**

~~~sql
SELECT c.customer_id, c.customer_name
FROM lab_sq195_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_sq195_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'NEW'
)
ORDER BY c.customer_id;
~~~

Kết quả **An** và **Dũng**.

### Bài 6 — Khách chưa có đơn bằng NOT EXISTS

**Đáp án:**

~~~sql
SELECT c.customer_id, c.customer_name
FROM lab_sq195_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_sq195_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Kết quả **Em (ID 5)**.

### Bài 7 — HAVING với mức trung bình của truy vấn con

**Yêu cầu:** nhóm đơn theo khách hàng, chỉ giữ khách có trung bình `amount` lớn hơn trung bình số tiền của toàn bộ đơn.

**Đáp án:**

~~~sql
SELECT o.customer_id, AVG(o.amount) AS customer_avg
FROM lab_sq195_orders AS o
GROUP BY o.customer_id
HAVING AVG(o.amount) > (
    SELECT AVG(o2.amount)
    FROM lab_sq195_orders AS o2
)
ORDER BY o.customer_id;
~~~

Kết quả duy nhất **Bình (ID 2)** với trung bình **180.00**.

### Bài 8 — WHERE trước nhóm và HAVING sau nhóm

**Yêu cầu:** chỉ xét các đơn PAID; lấy những khách có ít nhất **hai đơn PAID** và tổng tiền PAID từ **150** trở lên.

**Đáp án:**

~~~sql
SELECT
    o.customer_id,
    COUNT(*) AS paid_count,
    SUM(o.amount) AS paid_total
FROM lab_sq195_orders AS o
WHERE o.order_status = 'PAID'
GROUP BY o.customer_id
HAVING COUNT(*) >= 2
   AND SUM(o.amount) >= (
       SELECT 150::numeric
   )
ORDER BY o.customer_id;
~~~

Kết quả **An (2 đơn, 200.00)** và **Bình (2 đơn, 240.00)**. Subquery `SELECT 150::numeric` ở đây **chỉ để minh họa biểu thức trong HAVING** và không cần thiết khi ngưỡng 150 là hằng số: trong thực tế nên viết trực tiếp `HAVING ... SUM(o.amount) >= 150`. Nếu ngưỡng được tính từ dữ liệu khác, subquery mới thực sự hữu ích.

### Bài 9 — Tìm và sửa lỗi scalar subquery nhiều hàng

Một người viết:

~~~sql
SELECT c.customer_name
FROM lab_sq195_customers AS c
WHERE c.customer_id = (
    SELECT o.customer_id
    FROM lab_sq195_orders AS o
    WHERE o.order_status = 'PAID'
);
~~~

**Câu hỏi:** vì sao PostgreSQL báo lỗi và sửa thế nào nếu muốn lấy các khách có đơn PAID?

**Đáp án:** subquery trả nhiều hàng, nhưng dấu `=` đòi hỏi một giá trị đơn. Đổi `=` thành `IN`, hoặc viết `EXISTS` với điều kiện `o.customer_id = c.customer_id`. Tập khách đúng là An, Bình, Chi và Dũng.

### Bài 10 — NOT IN có NULL

**Yêu cầu:** dự đoán kết quả truy vấn:

~~~sql
SELECT c.customer_id
FROM lab_sq195_customers AS c
WHERE c.customer_id NOT IN (
    SELECT 1
    UNION ALL
    SELECT NULL::integer
);
~~~

**Đáp án:** **không có hàng nào**. ID 1 chắc chắn nằm trong danh sách, các ID khác có so sánh với `NULL` tạo UNKNOWN; `WHERE` loại cả FALSE và UNKNOWN. Khi muốn tìm khách không có đơn, dùng `NOT EXISTS` với điều kiện nối đúng khóa.

### Bài 11 — Correlated subquery trong HAVING theo khu vực

**Yêu cầu:** tìm khách có trung bình tiền đơn lớn hơn trung bình tiền đơn của **khu vực** họ thuộc về.

**Đáp án:**

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    c.region,
    AVG(o.amount) AS avg_amount
FROM lab_sq195_customers AS c
JOIN lab_sq195_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name, c.region
HAVING AVG(o.amount) > (
    SELECT AVG(o2.amount)
    FROM lab_sq195_orders AS o2
    JOIN lab_sq195_customers AS c2
        ON c2.customer_id = o2.customer_id
    WHERE c2.region = c.region
)
ORDER BY c.customer_id;
~~~

Kết quả là **Dũng (ID 4)** với trung bình **90.00**, cao hơn trung bình khu vực North **82.50**.

## 19. Ghi nhớ và lựa chọn đúng nơi đặt truy vấn con

| Nhu cầu | Mẫu cú pháp | Điều phải kiểm tra |
| --- | --- | --- |
| Tạo một cột tính riêng cho mỗi hàng | `SELECT ..., (SELECT COUNT(*) ... WHERE inner.key = outer.key) AS n` | Có tương quan đúng khóa; scalar subquery không trả nhiều hàng |
| So một giá trị với ngưỡng tính động | `WHERE amount > (SELECT AVG(amount) ...)` | Truy vấn con trả một giá trị; dữ liệu đầu vào ngưỡng đúng phạm vi |
| Kiểm tra khóa có trong danh sách | `WHERE id IN (SELECT id ...)` | Truy vấn con một cột; hiểu ý nghĩa NULL |
| Kiểm tra tồn tại quan hệ | `WHERE EXISTS (SELECT 1 ... WHERE inner.key = outer.key)` | Điều kiện tương quan đúng, không quan tâm các giá trị trong `SELECT 1` |
| Kiểm tra không có bản ghi liên quan | `WHERE NOT EXISTS (SELECT 1 ... )` | An toàn về ngữ nghĩa tồn tại khi cột trong dữ liệu có thể NULL |
| Lọc nhóm theo mức trung bình hoặc tổng động | `GROUP BY key HAVING AVG(x) > (SELECT AVG(x) ...)` | `AVG` ngoài tính theo nhóm, subquery bên trong tính đúng ngưỡng |
| So nhóm với thống kê của nhóm liên quan | `HAVING AVG(x) > (SELECT AVG(y) ... WHERE other.region = outer.region)` | Chỉ tương quan với khóa nhóm hợp lệ; chọn đúng phạm vi |

Trước khi dùng truy vấn con, hãy hỏi ba câu:

1. **“Kết quả cần từ truy vấn con là một giá trị, danh sách giá trị hay sự tồn tại của hàng?”** — Điều đó quyết định dùng scalar subquery, `IN` hay `EXISTS`.
2. **“Điều kiện này lọc hàng hay lọc nhóm?”** — Lọc hàng dùng `WHERE`, lọc nhóm sau `GROUP BY` dùng `HAVING`.
3. **“Truy vấn con có phụ thuộc hàng hoặc nhóm của truy vấn ngoài không?”** — Nếu có, phải khai báo bí danh và điều kiện tương quan rõ ràng.

Hiểu được ba yếu tố **hình dạng kết quả**, **giai đoạn lọc** và **phạm vi tương quan** sẽ giúp bạn viết đúng truy vấn con trong `SELECT`, `WHERE` và `HAVING`, tránh các lỗi khó thấy do nhiều hàng, `NULL` hoặc so sánh sai tập dữ liệu.
