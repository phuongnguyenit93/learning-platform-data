# WHERE và HAVING ở hai giai đoạn lọc

Trong một báo cáo bán hàng, có thể xuất hiện yêu cầu: **“Chỉ xét những đơn đã thanh toán, sau đó tìm khách hàng có từ hai đơn đã thanh toán trở lên và tổng giá trị ít nhất 150.”** Đây là một bài toán chứa hai loại điều kiện:

- **Lọc từng hàng trước khi tổng hợp:** đơn hàng phải có trạng thái `PAID`.
- **Lọc kết quả sau khi đã nhóm:** mỗi khách hàng phải có ít nhất hai đơn hợp lệ và tổng tiền đạt ngưỡng.

SQL sử dụng **`WHERE`** để lọc **hàng đầu vào** và **`HAVING`** để lọc **nhóm sau `GROUP BY`**. Cả hai đều viết điều kiện dạng Boolean, nhưng áp dụng ở **hai giai đoạn logic khác nhau**. Nhầm vị trí đặt điều kiện có thể khiến câu SQL báo lỗi hoặc, nguy hiểm hơn, chạy thành công nhưng đếm và cộng sai đối tượng.

Bài học thuộc **Database SQL → Tổng hợp dữ liệu**. Ví dụ thực hành sử dụng **PostgreSQL**, với cú pháp `SELECT`, `WHERE`, `GROUP BY`, `HAVING`, `COUNT` và `SUM` phổ biến trong SQL. Một số khác biệt giữa các hệ quản trị được ghi chú ở cuối.

## 1. Hai giai đoạn lọc trong một truy vấn

Hãy đọc câu SQL tổng quát:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_total
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2
   AND SUM(amount) >= 150
ORDER BY paid_total DESC;
~~~

Trong câu này:

1. `FROM orders` xác định tập hàng nguồn.
2. `WHERE order_status = 'PAID'` chỉ giữ các **đơn đã thanh toán**.
3. `GROUP BY customer_id` chia những đơn còn lại thành nhóm theo khách hàng.
4. `COUNT(*)` và `SUM(amount)` tính giá trị tổng hợp trên **mỗi nhóm**.
5. `HAVING COUNT(*) >= 2 AND SUM(amount) >= 150` chỉ giữ các **nhóm** đạt cả hai điều kiện.
6. `SELECT` tạo cột kết quả và `ORDER BY` sắp xếp các nhóm còn lại.

Sơ đồ thứ tự **logic** của một truy vấn tổng hợp điển hình:

~~~text
FROM / JOIN             Xác định dữ liệu nguồn và quan hệ giữa bảng
     |
     v
WHERE                   Lọc từng hàng trước khi nhóm
     |
     v
GROUP BY                Gom các hàng còn lại thành từng nhóm
     |
     v
TÍNH TỔNG HỢP           COUNT, SUM, AVG, MIN, MAX ... cho mỗi nhóm
     |
     v
HAVING                  Lọc những nhóm không đạt điều kiện
     |
     v
SELECT                  Chọn các cột/biểu thức kết quả
     |
     v
ORDER BY / LIMIT        Sắp xếp và giới hạn kết quả đầu ra
~~~

Đây là **mô hình logic để hiểu ngữ nghĩa**, không phải cam kết cơ sở dữ liệu luôn thực hiện đúng thứ tự vật lý đó. Bộ tối ưu truy vấn có thể sắp xếp lại các thao tác nội bộ mà vẫn bảo đảm kết quả tương đương.

| Tiêu chí | `WHERE` | `HAVING` |
| --- | --- | --- |
| Đối tượng kiểm tra | Từng **hàng** từ nguồn truy vấn | Từng **nhóm** sau khi tổng hợp |
| Vị trí viết thông thường | Sau `FROM`/`JOIN`, trước `GROUP BY` | Sau `GROUP BY`, trước `ORDER BY` |
| Có dùng hàm tổng hợp trực tiếp như `COUNT(*)` hoặc `SUM(amount)` không? | Không, tại cùng cấp truy vấn | Có |
| Điều kiện ví dụ | `order_status = 'PAID'` | `COUNT(*) >= 2` |
| Ảnh hưởng số liệu tổng hợp | Xác định **những hàng nào được mang đi đếm/cộng** | Chọn **những kết quả nhóm nào được hiển thị** |
| Có cần `GROUP BY`? | Không | Thường dùng cùng `GROUP BY`; một số trường hợp tổng hợp toàn bộ tập có thể dùng `HAVING` mà không viết `GROUP BY` |

Một mẹo đọc yêu cầu: nếu điều kiện hỏi **“đơn hàng nào được tính?”**, thường đặt ở `WHERE`; nếu hỏi **“khách hàng/nhóm nào đạt số lượng hoặc tổng tiền bao nhiêu?”**, thường đặt ở `HAVING`.

## 2. Tạo dữ liệu mẫu để quan sát hai giai đoạn

Trong database **PostgreSQL thực hành riêng**, hãy chạy đoạn sau một lần, với điều kiện chưa có hai bảng cùng tên. Các bảng có tiền tố `lab_wh_165_` để tránh lẫn với bảng khác.

~~~sql
CREATE TABLE lab_wh_165_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(80) NOT NULL
);

CREATE TABLE lab_wh_165_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lab_wh_165_customers(customer_id),
    order_status VARCHAR(12) NOT NULL
        CHECK (order_status IN ('NEW', 'PAID', 'CANCELLED')),
    amount NUMERIC(12, 2)
        CHECK (amount >= 0),
    placed_on DATE NOT NULL
);

INSERT INTO lab_wh_165_customers (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi'),
    (4, 'Dung'),
    (5, 'Em'),
    (6, 'Giang');

INSERT INTO lab_wh_165_orders
    (order_id, customer_id, order_status, amount, placed_on)
VALUES
    (101, 1, 'PAID',      120.00, DATE '2026-10-01'),
    (102, 1, 'PAID',       80.00, DATE '2026-10-02'),
    (103, 1, 'CANCELLED',  50.00, DATE '2026-10-03'),
    (104, 2, 'PAID',      200.00, DATE '2026-10-02'),
    (105, 2, 'NEW',       300.00, DATE '2026-10-04'),
    (106, 3, 'PAID',       50.00, DATE '2026-10-02'),
    (107, 3, 'PAID',       70.00, DATE '2026-10-07'),
    (108, 4, 'NEW',        90.00, DATE '2026-10-08'),
    (109, 4, 'CANCELLED',   NULL,  DATE '2026-10-09'),
    (110, 5, 'PAID',        0.00, DATE '2026-10-10'),
    (111, 2, 'PAID',       40.00, DATE '2026-09-29');
~~~

Bảng khách hàng có **6 người**; người tên **Giang** chưa có đơn nào. Bảng đơn hàng có **11 đơn**, thuộc ba trạng thái `PAID`, `NEW` và `CANCELLED`. Đơn 109 có `amount IS NULL` để thực hành phép tổng hợp khi thiếu giá trị.

Đọc dữ liệu đơn hàng:

~~~sql
SELECT order_id, customer_id, order_status, amount, placed_on
FROM lab_wh_165_orders
ORDER BY order_id;
~~~

| order_id | customer_id | order_status | amount | placed_on |
| ---: | ---: | --- | ---: | --- |
| 101 | 1 | PAID | 120.00 | 2026-10-01 |
| 102 | 1 | PAID | 80.00 | 2026-10-02 |
| 103 | 1 | CANCELLED | 50.00 | 2026-10-03 |
| 104 | 2 | PAID | 200.00 | 2026-10-02 |
| 105 | 2 | NEW | 300.00 | 2026-10-04 |
| 106 | 3 | PAID | 50.00 | 2026-10-02 |
| 107 | 3 | PAID | 70.00 | 2026-10-07 |
| 108 | 4 | NEW | 90.00 | 2026-10-08 |
| 109 | 4 | CANCELLED | `NULL` | 2026-10-09 |
| 110 | 5 | PAID | 0.00 | 2026-10-10 |
| 111 | 2 | PAID | 40.00 | 2026-09-29 |

Những kết quả minh họa sau dựa trên **bảng chưa bị sửa**. `ORDER BY` được dùng để bảo đảm cách trình bày có thứ tự rõ ràng, không dựa vào thứ tự vật lý của hàng.

## 3. WHERE: chọn từng hàng trước khi tổng hợp

Giả sử yêu cầu “Chỉ xét các đơn hàng đã thanh toán”. Điều kiện liên quan tới **từng đơn** nên viết trong `WHERE`:

~~~sql
SELECT order_id, customer_id, order_status, amount
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
ORDER BY order_id;
~~~

Kết quả có các đơn **101, 102, 104, 106, 107, 110, 111** — tổng cộng **7 hàng**. Các đơn `NEW` hoặc `CANCELLED` không đi qua bộ lọc.

Nếu sau đó nhóm theo khách hàng, `COUNT(*)` chỉ nhìn thấy **bảy đơn PAID** này, không nhìn thấy toàn bộ 11 đơn ban đầu.

### 3.1. Lọc theo nhiều điều kiện trên hàng

Yêu cầu: “Đơn đã thanh toán **từ ngày 01/10/2026 trở đi**”:

~~~sql
SELECT order_id, customer_id, amount, placed_on
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
  AND placed_on >= DATE '2026-10-01'
ORDER BY order_id;
~~~

Đơn **111** bị loại vì ngày `2026-09-29`, dù trạng thái là `PAID`. Còn lại các đơn **101, 102, 104, 106, 107, 110** — tổng cộng **6 hàng**.

Điều kiện `WHERE` không cần biết dữ liệu sẽ được nhóm theo cột nào; nó quyết định hàng nào đủ điều kiện **ngay trước giai đoạn tổng hợp**.

### 3.2. WHERE không tính tổng hợp ngay tại cùng cấp

Ví dụ sau **không hợp lệ**:

~~~sql
-- SAI: COUNT(*) la ham tong hop, khong duoc dung trong WHERE cung cap.
SELECT customer_id, COUNT(*) AS order_count
FROM lab_wh_165_orders
WHERE COUNT(*) >= 2
GROUP BY customer_id;
~~~

Tại giai đoạn `WHERE`, chưa có các nhóm để `COUNT(*)` đại diện cho “số đơn mỗi khách hàng”. Điều kiện đếm sau nhóm phải đặt ở `HAVING`:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM lab_wh_165_orders
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

Một điểm phân biệt khác: `WHERE` **có thể dùng các biểu thức thông thường** như so sánh, `IN`, `BETWEEN`, `LIKE`, `IS NULL`, `AND` và `OR`. Điều bị cấm trong ví dụ là tham chiếu trực tiếp giá trị **tổng hợp của cùng cấp truy vấn**, không phải tất cả những câu SQL chứa một từ khóa hay tên hàm nào đó.

## 4. GROUP BY: tạo nhóm từ tập hàng đã qua WHERE

Trước khi nói về `HAVING`, hãy quan sát kết quả tổng hợp **không lọc theo trạng thái**:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS all_order_count,
    SUM(amount) AS all_order_amount
FROM lab_wh_165_orders
GROUP BY customer_id
ORDER BY customer_id;
~~~

| customer_id | all_order_count | all_order_amount |
| ---: | ---: | ---: |
| 1 | 3 | 250.00 |
| 2 | 3 | 540.00 |
| 3 | 2 | 120.00 |
| 4 | 2 | 90.00 |
| 5 | 1 | 0.00 |

Để tính các số này:

- Khách hàng **1 (An)** có ba đơn 101, 102, 103; tổng tiền 120 + 80 + 50 = **250**.
- Khách hàng **2 (Bình)** có ba đơn 104, 105, 111; tổng tiền 200 + 300 + 40 = **540**.
- Khách hàng **3 (Chi)** có hai đơn 106, 107; tổng **120**.
- Khách hàng **4 (Dũng)** có hai đơn 108, 109; `SUM` bỏ qua `NULL` của đơn 109 nên tổng **90**.
- Khách hàng **5 (Em)** có một đơn giá trị **0**, nên tổng **0**.
- Khách hàng **6 (Giang)** không xuất hiện vì bảng `orders` không có hàng nào mang `customer_id = 6`.

Ở câu này, `GROUP BY customer_id` tạo **một nhóm cho mỗi giá trị khách hàng xuất hiện ở đầu vào**. `COUNT(*)` và `SUM(amount)` tính trên những hàng **trong từng nhóm**, không phải trên toàn bộ bảng một lần.

### 4.1. WHERE trước GROUP BY làm số liệu thay đổi

Thêm điều kiện `WHERE order_status = 'PAID'`:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_total
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
GROUP BY customer_id
ORDER BY customer_id;
~~~

Kết quả:

| customer_id | paid_order_count | paid_total |
| ---: | ---: | ---: |
| 1 | 2 | 200.00 |
| 2 | 2 | 240.00 |
| 3 | 2 | 120.00 |
| 5 | 1 | 0.00 |

So với bảng trước:

- An từ **3 đơn** còn **2 đơn PAID**; tổng từ 250 còn 200 vì đơn CANCELLED bị loại.
- Bình từ tổng **540** còn **240** vì đơn NEW trị giá 300 không được tính.
- Chi vẫn có hai đơn đều PAID, tổng 120.
- Dũng biến mất khỏi kết quả vì không có đơn PAID nào để tạo thành nhóm.
- Em vẫn có một đơn PAID trị giá 0, nên nhóm vẫn tồn tại.

**WHERE không chỉ loại các hàng khỏi đầu ra; nó còn quyết định những hàng được phép đóng góp vào các phép đếm, cộng và tính trung bình kế tiếp.**

## 5. HAVING: chọn nhóm sau khi đã tính COUNT, SUM, AVG…

Yêu cầu: “Trong những khách hàng có đơn hàng, chỉ hiển thị khách có **ít nhất 2 đơn bất kỳ trạng thái nào**”.

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM lab_wh_165_orders
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

Kết quả:

| customer_id | order_count |
| ---: | ---: |
| 1 | 3 |
| 2 | 3 |
| 3 | 2 |
| 4 | 2 |

Khách hàng 5 bị loại vì chỉ có một đơn. Khách hàng 6 chưa từng tạo nhóm vì không có dòng nguồn; `HAVING` không tự sinh nhóm cho những giá trị vắng mặt.

### 5.1. HAVING dùng nhiều điều kiện nhóm

Trở lại yêu cầu chính: “Chỉ xét các đơn PAID, sau đó lấy khách có **từ 2 đơn PAID** và **tổng tiền PAID ít nhất 150**”.

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_total
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2
   AND SUM(amount) >= 150
ORDER BY customer_id;
~~~

Kết quả cuối:

| customer_id | paid_order_count | paid_total |
| ---: | ---: | ---: |
| 1 | 2 | 200.00 |
| 2 | 2 | 240.00 |

Lý do:

- An có 2 đơn PAID, tổng 200 → đạt cả hai điều kiện.
- Bình có 2 đơn PAID, tổng 240 → đạt cả hai điều kiện.
- Chi có 2 đơn PAID nhưng tổng 120 → không đạt ngưỡng 150.
- Em có 1 đơn PAID và tổng 0 → không đạt.
- Dũng không có đơn PAID → không có nhóm sau `WHERE`.

Hãy đọc câu này từ **trái sang phải theo dữ liệu**: `WHERE` chọn **đơn được xét**, `GROUP BY` tạo **khách hàng**, `HAVING` chọn **khách hàng đạt điều kiện tổng hợp**.

### 5.2. HAVING có thể kiểm tra AVG, MIN, MAX

Ví dụ chọn khách hàng có từ hai đơn PAID và giá trị trung bình mỗi đơn PAID ít nhất 100:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    AVG(amount) AS average_paid_amount
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2
   AND AVG(amount) >= 100
ORDER BY customer_id;
~~~

An có trung bình `(120 + 80)/2 = 100`, Bình có `(200 + 40)/2 = 120`, Chi có `(50 + 70)/2 = 60`. Vì vậy chỉ An và Bình đạt điều kiện.

Tương tự, `HAVING MAX(amount) >= 200` có thể được dùng để tìm nhóm có ít nhất một đơn PAID đạt 200 trở lên, nhưng nhớ rằng hàm `MAX` bỏ qua `NULL` như các hàm tổng hợp số học thông thường.

## 6. Kết hợp WHERE và HAVING với điều kiện thời gian

Thêm giới hạn thời gian: “Chỉ xét đơn PAID **từ 01/10/2026**, lấy khách có tổng tiền PAID từ 200 trở lên”.

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_total
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
  AND placed_on >= DATE '2026-10-01'
GROUP BY customer_id
HAVING SUM(amount) >= 200
ORDER BY customer_id;
~~~

Kết quả:

| customer_id | paid_order_count | paid_total |
| ---: | ---: | ---: |
| 1 | 2 | 200.00 |
| 2 | 1 | 200.00 |

Bình có hai đơn PAID trên **mọi thời điểm** (đơn 104 và 111) với tổng 240, nhưng chỉ một đơn PAID trong khoảng từ 01/10 (đơn 104). Vì thế tổng trong phạm vi mới là **200**, không còn 240.

Nếu đổi `HAVING` thành:

~~~sql
HAVING COUNT(*) >= 2
   AND SUM(amount) >= 200
~~~

thì chỉ còn **An**, vì Bình chỉ có một đơn PAID trong giai đoạn đó. Điều này cho thấy thay đổi điều kiện **WHERE** có thể đổi số hàng trong nhóm, và do đó đổi quyết định của **HAVING**.

### Hai câu hỏi nghiệp vụ khác nhau

Hãy phân biệt:

1. “Khách có **tổng tiền các đơn PAID từ ngày X** ít nhất 200?” → lọc ngày trong `WHERE`, rồi `SUM` và `HAVING`.
2. “Khách có **ít nhất một đơn PAID từ ngày X**, nhưng tổng tiền xét trên **tất cả đơn** ít nhất 200?” → không thể đơn giản lọc bỏ các đơn khác trước khi tính tổng tất cả. Cần tổng hợp có điều kiện hoặc nhiều tập dữ liệu riêng.

Hai yêu cầu có thể chọn ra những người giống hoặc khác nhau tùy dữ liệu. Việc hiểu rõ **phạm vi của phép tổng hợp** quan trọng hơn việc thuộc vị trí từ khóa.

## 7. Khi WHERE và HAVING cùng có điều kiện về trạng thái, chúng có tương đương không?

Xét hai yêu cầu dễ nhầm:

**Yêu cầu A:** “Tìm khách hàng có ít nhất **hai đơn PAID**, rồi hiển thị **số lượng đơn PAID**.”

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

Kết quả:

| customer_id | paid_order_count |
| ---: | ---: |
| 1 | 2 |
| 2 | 2 |
| 3 | 2 |

**Yêu cầu B:** “Tìm khách hàng có ít nhất **hai đơn PAID**, nhưng hiển thị **tổng số đơn mọi trạng thái** của những khách hàng đó.”

~~~sql
SELECT
    customer_id,
    COUNT(*) AS all_order_count
FROM lab_wh_165_orders
GROUP BY customer_id
HAVING SUM(
    CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END
) >= 2
ORDER BY customer_id;
~~~

Kết quả:

| customer_id | all_order_count |
| ---: | ---: |
| 1 | 3 |
| 2 | 3 |
| 3 | 2 |

Hai câu chọn cùng ba khách hàng nhưng cột đếm **khác ý nghĩa**:

- Ở A, `WHERE` **loại đơn không PAID trước khi `COUNT(*)`** nên chỉ đếm đơn PAID.
- Ở B, **mọi đơn vẫn ở đầu vào** của `COUNT(*)`. Biểu thức `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` chỉ đếm đơn PAID **để quyết định điều kiện HAVING**, không loại những đơn khác khỏi `COUNT(*)`.

Đây là một minh họa quan trọng: **di chuyển điều kiện từ WHERE sang HAVING không đơn giản là đổi vị trí viết**; còn phải xét điều kiện đang chọn **hàng đầu vào** hay đang kiểm tra **thống kê của nhóm**.

### 7.1. Tổng hợp có điều kiện với FILTER

Trong PostgreSQL, có cú pháp `FILTER` giúp viết gọn một phép tổng hợp chỉ xét hàng thỏa điều kiện:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS all_order_count,
    COUNT(*) FILTER (WHERE order_status = 'PAID') AS paid_order_count
FROM lab_wh_165_orders
GROUP BY customer_id
HAVING COUNT(*) FILTER (WHERE order_status = 'PAID') >= 2
ORDER BY customer_id;
~~~

Kết quả:

| customer_id | all_order_count | paid_order_count |
| ---: | ---: | ---: |
| 1 | 3 | 2 |
| 2 | 3 | 2 |
| 3 | 2 | 2 |

**`FILTER (WHERE ...)` là bộ lọc bên trong một hàm tổng hợp**, không phải `WHERE` cấp truy vấn. Nó cho phép nhiều phép đếm hoặc cộng với những điều kiện khác nhau cùng tồn tại trên một tập nhóm.

Ví dụ:

~~~sql
SELECT
    customer_id,
    COUNT(*) FILTER (WHERE order_status = 'PAID') AS paid_count,
    COUNT(*) FILTER (WHERE order_status = 'NEW') AS new_count,
    COUNT(*) FILTER (WHERE order_status = 'CANCELLED') AS cancelled_count
FROM lab_wh_165_orders
GROUP BY customer_id
ORDER BY customer_id;
~~~

| customer_id | paid_count | new_count | cancelled_count |
| ---: | ---: | ---: | ---: |
| 1 | 2 | 0 | 1 |
| 2 | 2 | 1 | 0 |
| 3 | 2 | 0 | 0 |
| 4 | 0 | 1 | 1 |
| 5 | 1 | 0 | 0 |

Một số SQL dialect không hỗ trợ `FILTER` trực tiếp; khi đó `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` là lựa chọn thông dụng. Đừng nhầm các bộ lọc khác nhau chỉ vì đều dùng chữ `WHERE` trong cú pháp.

## 8. HAVING không nhất thiết phải có GROUP BY

Trong SQL, nếu truy vấn dùng phép tổng hợp mà không khai báo `GROUP BY`, có thể hiểu toàn bộ tập đầu vào là **một nhóm tổng hợp duy nhất**. `HAVING` có thể quyết định giữ hay bỏ nhóm tổng hợp đó.

~~~sql
SELECT COUNT(*) AS total_paid_orders
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
HAVING COUNT(*) >= 5;
~~~

Với dữ liệu mẫu, có **7** đơn PAID, nên truy vấn trả về **một dòng** có `total_paid_orders = 7`.

Đổi ngưỡng:

~~~sql
SELECT COUNT(*) AS total_paid_orders
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
HAVING COUNT(*) >= 8;
~~~

Vì `7 >= 8` là FALSE, truy vấn trả về **không dòng nào**, chứ không trả về một dòng có giá trị 0. Nếu bỏ `HAVING`, `COUNT(*)` sẽ trả về một dòng đếm được 7.

Đối với một tập đầu vào rỗng, `COUNT(*)` trả về 0, còn `SUM(amount)` thường trả `NULL`. Nếu có `HAVING` thì điều kiện của nhóm tổng hợp có thể làm cả dòng kết quả đó biến mất.

Không nên hiểu “HAVING không có GROUP BY” là có thể tùy ý chọn một cột bất kỳ chưa tổng hợp. Trong PostgreSQL, khi toàn bộ truy vấn là một nhóm tổng hợp, các cột ở `SELECT` hoặc điều kiện `HAVING` vẫn phải tuân theo quy tắc nhóm/tổng hợp; tham chiếu một cột không được nhóm hay tổng hợp thường sẽ bị từ chối.

## 9. WHERE và HAVING với NULL: COUNT(*) khác COUNT(column)

Một điểm dễ gây sai khi lọc nhóm là các hàm tổng hợp xử lý `NULL` không giống nhau.

Đếm tất cả đơn, số đơn có `amount` khác `NULL` và tổng tiền:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS all_orders,
    COUNT(amount) AS orders_with_amount,
    SUM(amount) AS total_amount
FROM lab_wh_165_orders
GROUP BY customer_id
ORDER BY customer_id;
~~~

| customer_id | all_orders | orders_with_amount | total_amount |
| ---: | ---: | ---: | ---: |
| 1 | 3 | 3 | 250.00 |
| 2 | 3 | 3 | 540.00 |
| 3 | 2 | 2 | 120.00 |
| 4 | 2 | 1 | 90.00 |
| 5 | 1 | 1 | 0.00 |

Đơn 109 của Dũng có số tiền `NULL`:

- `COUNT(*)` vẫn **đếm hàng đó**.
- `COUNT(amount)` **không đếm** giá trị `NULL`.
- `SUM(amount)` bỏ qua giá trị `NULL` và chỉ cộng số tiền của các hàng có giá trị.

Vì thế, các điều kiện này **không đồng nghĩa**:

~~~sql
HAVING COUNT(*) >= 2

HAVING COUNT(amount) >= 2
~~~

Trên dữ liệu mẫu, Dũng đạt `COUNT(*) >= 2` nhưng **không** đạt `COUNT(amount) >= 2`. Nếu nghiệp vụ muốn “hai đơn đã có số tiền được xác định”, phải dùng tiêu chí thứ hai hoặc một điều kiện tương đương được xác định rõ.

### 9.1. WHERE loại bỏ NULL trước khi nhóm

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM lab_wh_165_orders
WHERE amount IS NOT NULL
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

Dòng có `amount IS NULL` bị loại **trước `GROUP BY`**, nên kết quả gồm khách **1, 2, 3**, không còn khách 4.

Nếu chỉ muốn **khách nào có ít nhất hai đơn đã biết tiền** nhưng vẫn cần thống kê **tổng mọi đơn**, hãy chọn hướng tổng hợp có điều kiện thay vì loại các hàng có số tiền NULL khỏi toàn bộ đầu vào:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS all_order_count,
    COUNT(amount) AS priced_order_count
FROM lab_wh_165_orders
GROUP BY customer_id
HAVING COUNT(amount) >= 2
ORDER BY customer_id;
~~~

### 9.2. HAVING khi SUM hoặc AVG trả NULL

Nếu một nhóm chỉ có các giá trị `amount IS NULL`, `SUM(amount)` và `AVG(amount)` sẽ trả `NULL`. Điều kiện:

~~~sql
HAVING SUM(amount) > 0
~~~

trả kết quả Boolean **UNKNOWN** cho nhóm ấy; trong `HAVING`, giống `WHERE`, chỉ điều kiện **TRUE** mới được giữ.

Nếu cần đưa nhóm có tổng thiếu dữ liệu vào một loại riêng, hãy mô tả rõ quy tắc và có thể dùng `CASE` hoặc `HAVING SUM(amount) IS NULL`. Không mặc nhiên coi `NULL` là 0 vì “chưa biết tổng” và “tổng bằng 0” là hai trạng thái khác nhau.

## 10. JOIN, WHERE, HAVING và khách hàng không có đơn

Khi tổng hợp trên nhiều bảng, cần quan tâm một giai đoạn nữa: **`JOIN` tạo ra những hàng nào trước khi `WHERE` và `GROUP BY` xử lý**.

### 10.1. INNER JOIN chỉ có khách hàng khớp với đơn

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS paid_order_count
FROM lab_wh_165_customers AS c
JOIN lab_wh_165_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'PAID'
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(*) >= 2
ORDER BY c.customer_id;
~~~

Kết quả là An, Bình, Chi (mỗi người 2 đơn PAID). Dũng không có đơn PAID, Giang chưa có đơn nào; cả hai không tham gia các nhóm sau `INNER JOIN` và `WHERE`.

### 10.2. LEFT JOIN rồi WHERE ở bảng phải có thể làm mất hàng không khớp

Giả sử muốn thống kê **mọi khách hàng**, kể cả người không có đơn PAID. Câu sau **không thực hiện đúng mục tiêu**:

~~~sql
-- SAI neu can giu ca khach hang khong co don PAID.
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count
FROM lab_wh_165_customers AS c
LEFT JOIN lab_wh_165_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Mặc dù đã dùng `LEFT JOIN`, điều kiện `WHERE o.order_status = 'PAID'` loại các hàng mà `o.order_status` không phải PAID hoặc là `NULL` từ phía bảng phải. Dũng và Giang bị loại, nên danh sách **không còn đủ sáu khách hàng**.

### 10.3. Đặt điều kiện ở ON để giữ tất cả khách hàng

Nếu quy tắc là “giữ mọi khách hàng, chỉ ghép các đơn PAID để đếm”, đặt điều kiện trạng thái trong `ON`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count
FROM lab_wh_165_customers AS c
LEFT JOIN lab_wh_165_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

| customer_id | customer_name | paid_order_count |
| ---: | --- | ---: |
| 1 | An | 2 |
| 2 | Binh | 2 |
| 3 | Chi | 2 |
| 4 | Dung | 0 |
| 5 | Em | 1 |
| 6 | Giang | 0 |

Chọn `COUNT(o.order_id)` là có chủ đích. Với `LEFT JOIN`, khách hàng không có đơn PAID vẫn có **một hàng kết quả nối**, nhưng các cột `o.*` là `NULL`. `COUNT(*)` sẽ đếm hàng đó thành **1**, còn `COUNT(o.order_id)` trả **0** vì `order_id` từ bảng phải không hiện diện.

### 10.4. HAVING tìm khách hàng không có đơn PAID

Sau khi giữ tất cả khách hàng bằng `LEFT JOIN`, lọc nhóm có số đơn PAID bằng 0:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count
FROM lab_wh_165_customers AS c
LEFT JOIN lab_wh_165_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'PAID'
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(o.order_id) = 0
ORDER BY c.customer_id;
~~~

Kết quả gồm **Dũng** và **Giang**. Dũng có đơn nhưng không có đơn PAID; Giang chưa có đơn nào.

Ví dụ cho thấy `ON`, `WHERE` và `HAVING` có ba vai trò cần tách bạch:

- `ON` xác định điều kiện **ghép hàng**.
- `WHERE` xác định **hàng nào được giữ** sau phần `FROM`/`JOIN`.
- `HAVING` xác định **nhóm nào được giữ** sau tổng hợp.

Những điều kiện chỉ dành cho bảng bên phải của `LEFT JOIN` không thể di chuyển tùy ý giữa `ON` và `WHERE` mà không thay đổi ý nghĩa.

## 11. SELECT alias, GROUP BY và HAVING: tránh nhầm phạm vi tên

Trong PostgreSQL, bí danh cột trong danh sách `SELECT` có thể được dùng trong `ORDER BY`, nhưng **không được dùng trực tiếp như một tên tổng hợp trong `HAVING` ở cùng cấp**.

Ví dụ sau dễ viết nhầm:

~~~sql
-- SAI tren PostgreSQL: paid_order_count la alias SELECT, khong phai cot nguon.
SELECT
    customer_id,
    COUNT(*) AS paid_order_count
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING paid_order_count >= 2;
~~~

Viết đúng bằng cách lặp lại biểu thức tổng hợp:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY paid_order_count DESC, customer_id ASC;
~~~

Truy vấn này hợp lệ: `HAVING COUNT(*) >= 2` kiểm tra tổng hợp, còn `ORDER BY paid_order_count` sử dụng **bí danh đầu ra**.

### 11.1. Dùng CTE khi muốn lọc theo tên tổng hợp

Nếu nhiều điều kiện dựa trên các giá trị tính toán, một **CTE** (`WITH ... AS (...)`) giúp chia truy vấn thành hai cấp:

~~~sql
WITH paid_summary AS (
    SELECT
        customer_id,
        COUNT(*) AS paid_order_count,
        SUM(amount) AS paid_total
    FROM lab_wh_165_orders
    WHERE order_status = 'PAID'
    GROUP BY customer_id
)
SELECT
    customer_id,
    paid_order_count,
    paid_total
FROM paid_summary
WHERE paid_order_count >= 2
  AND paid_total >= 150
ORDER BY customer_id;
~~~

Kết quả là **An (ID 1)** và **Bình (ID 2)**, tương đương ví dụ `HAVING` ở mục 5.

Ở đây, `paid_summary` đã là **một bảng kết quả trung gian có một hàng cho mỗi khách hàng**. Vì vậy tại **cấp truy vấn ngoài**, `paid_order_count` và `paid_total` là các **cột thông thường**; dùng `WHERE` để lọc chúng là đúng. Không có mâu thuẫn với nguyên tắc “`WHERE` không dùng tổng hợp cùng cấp”: phép tổng hợp được thực hiện ở **cấp truy vấn bên trong**.

Mẫu CTE hữu ích khi cần nhiều phép tính, muốn đặt tên dễ hiểu hoặc cần kiểm tra từng bước của báo cáo.

## 12. Điều kiện nào nên đặt ở WHERE, điều kiện nào ở HAVING?

Khi cả hai vị trí đều có vẻ dùng được, hãy xác định **đối tượng bị lọc**.

| Yêu cầu | Mệnh đề thường phù hợp | Giải thích |
| --- | --- | --- |
| Chỉ tính những đơn có trạng thái PAID | `WHERE order_status = 'PAID'` | Loại đơn không PAID khỏi dữ liệu đầu vào |
| Chỉ tính đơn phát sinh trong tháng 10 | `WHERE placed_on >= ... AND placed_on < ...` | Lọc thời gian của từng đơn trước tổng hợp |
| Chỉ lấy khách hàng có ít nhất 2 đơn PAID | `HAVING COUNT(*) >= 2` sau `WHERE status='PAID'` | Đếm số đơn trong từng nhóm đã lọc |
| Chỉ lấy khách hàng có tổng tiền PAID ít nhất 150 | `HAVING SUM(amount) >= 150` sau `WHERE status='PAID'` | So ngưỡng với tổng nhóm |
| Chỉ thống kê các khách hàng có ID từ 3 trở lên | `WHERE customer_id >= 3` | Điều kiện trực tiếp trên mỗi hàng/khóa nhóm, thường lọc sớm được |
| Chỉ lấy nhóm có trung bình số tiền lớn hơn 100 | `HAVING AVG(amount) > 100` | Điều kiện cần giá trị tổng hợp |
| Hiển thị tất cả khách nhưng chỉ đếm đơn PAID trong LEFT JOIN | Điều kiện PAID trong `ON` hoặc tổng hợp có điều kiện | Giữ khách không có đơn PAID |
| Đếm toàn bộ đơn của khách, nhưng chỉ chọn khách có từ 2 đơn PAID | Tổng hợp có điều kiện trong `HAVING` | Không thể lọc bỏ đơn khác bằng `WHERE` rồi vẫn đếm “toàn bộ” |

### 12.1. Có thể đặt điều kiện của cột nhóm vào HAVING không?

Trong PostgreSQL, một điều kiện dựa trên **khóa nhóm** có thể được viết trong `HAVING`:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM lab_wh_165_orders
GROUP BY customer_id
HAVING customer_id >= 3
ORDER BY customer_id;
~~~

Tuy nhiên, nếu mục tiêu chỉ là loại những khách hàng ID nhỏ hơn 3 **trước khi đếm**, thường nên đặt điều kiện đó vào `WHERE`:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM lab_wh_165_orders
WHERE customer_id >= 3
GROUP BY customer_id
ORDER BY customer_id;
~~~

Với điều kiện chỉ liên quan tới **khóa nhóm** và không có tương tác phức tạp khác, kết quả trong ví dụ là tương đương. `WHERE` biểu đạt rõ việc **giảm đầu vào** và có thể giúp bộ tối ưu hạn chế lượng hàng cần xử lý. Không nên chuyển tùy tiện mọi điều kiện `HAVING` về `WHERE`, đặc biệt khi điều kiện phụ thuộc `COUNT`, `SUM` hoặc dữ liệu từ `LEFT JOIN`.

### 12.2. Điều kiện trên cột không có trong GROUP BY

Ví dụ dễ sai trên PostgreSQL:

~~~sql
-- SAI: order_status khong nam trong GROUP BY va khong duoc tong hop.
SELECT customer_id, COUNT(*) AS order_count
FROM lab_wh_165_orders
GROUP BY customer_id
HAVING order_status = 'PAID';
~~~

Một khách hàng có thể vừa có đơn PAID vừa có đơn NEW/CANCELLED; sau khi gộp nhóm, không còn một giá trị `order_status` duy nhất để `HAVING` đọc như một cột bình thường.

Nếu muốn **chỉ đếm đơn PAID**, viết `WHERE order_status = 'PAID'` trước `GROUP BY`. Nếu muốn **chọn nhóm có ít nhất một đơn PAID** nhưng vẫn đếm mọi đơn, dùng tổng hợp có điều kiện như `SUM(CASE WHEN order_status='PAID' THEN 1 ELSE 0 END) > 0`.

Một số SQL dialect có chế độ cho phép chọn cột không nhóm một cách linh hoạt hoặc có quy tắc phụ thuộc hàm; không nên dựa vào hành vi thiếu xác định của một hệ để viết truy vấn báo cáo dùng được ở mọi nơi.

## 13. Hiệu năng: lọc sớm khi điều kiện thực sự thuộc hàng

Về mặt logic, `WHERE` nằm trước `GROUP BY`, nên việc lọc bớt hàng có thể giảm số lượng dữ liệu cần tổng hợp. Ví dụ:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
  AND placed_on >= DATE '2026-10-01'
  AND placed_on < DATE '2026-11-01'
GROUP BY customer_id
HAVING COUNT(*) >= 2;
~~~

Điều kiện thời gian ở đây dùng khoảng **đầu bao gồm, cuối không bao gồm**, giúp biểu diễn các khoảng lịch một cách rõ ràng; nó cũng phù hợp khi chuyển từ cột `DATE` sang kiểu thời gian có giờ/phút.

Trên bảng lớn, chỉ mục phù hợp có thể hỗ trợ một số điều kiện `WHERE`:

~~~sql
-- Chi tao chi muc khi co nhu cau phu hop; day la lenh DDL that.
CREATE INDEX lab_wh_165_orders_status_date_customer_idx
ON lab_wh_165_orders (order_status, placed_on, customer_id);
~~~

Chỉ mục này **có thể** hỗ trợ tìm những đơn theo trạng thái và khoảng ngày. Tuy nhiên, không có bảo đảm bộ tối ưu sẽ dùng nó cho mọi truy vấn: kế hoạch phụ thuộc phân bố dữ liệu, kích thước bảng, thống kê, mục tiêu truy vấn và chi phí I/O. Trên bảng thực hành chỉ 11 hàng, quét tuần tự có thể rẻ hơn dùng chỉ mục.

PostgreSQL có thể xem kế hoạch mà không thay đổi dữ liệu:

~~~sql
EXPLAIN
SELECT customer_id, COUNT(*) AS paid_order_count
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2;
~~~

Đừng suy luận rằng việc chuyển mọi điều kiện từ `HAVING` sang `WHERE` luôn tăng tốc và giữ nguyên số liệu. Điều kiện tổng hợp như `COUNT(*) >= 2` **không thể** kiểm tra trên từng hàng trước khi lập nhóm. Tối ưu chỉ có ý nghĩa khi giữ đúng quy tắc dữ liệu cần tính.

## 14. Khác biệt và tính tương thích giữa các hệ quản trị

Nguyên tắc “`WHERE` lọc hàng; `HAVING` lọc nhóm” là nền tảng phổ biến của SQL và được hỗ trợ trong PostgreSQL, MySQL, SQL Server, SQLite, Oracle Database. Tuy vậy, có một số khác biệt cần chú ý:

| Vấn đề | PostgreSQL | Ghi chú chuyển hệ |
| --- | --- | --- |
| `WHERE` + `GROUP BY` + `HAVING` | Hỗ trợ đầy đủ | Phổ biến ở các hệ quản trị lớn |
| `HAVING COUNT(*) >= 2` | Hợp lệ | Cách viết tổng hợp phổ biến |
| Dùng alias `SELECT` trong `HAVING` cùng cấp | Thông thường **không** hỗ trợ | MySQL và một số hệ có thể cho phép; nên lặp biểu thức hoặc dùng CTE để dễ chuyển hệ |
| `COUNT(*) FILTER (WHERE ...)` | Hỗ trợ | SQL Server và một số hệ không hỗ trợ trực tiếp; dùng `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` |
| `HAVING` không có `GROUP BY` khi tổng hợp toàn bảng | Hỗ trợ | Nhiều hệ hỗ trợ nhưng có chi tiết ngữ nghĩa/cú pháp riêng |
| Cột trong `SELECT`/`HAVING` không được nhóm hoặc tổng hợp | PostgreSQL kiểm tra khá chặt, với ngoại lệ dựa trên phụ thuộc hàm trong một số trường hợp | MySQL có chế độ `ONLY_FULL_GROUP_BY` và quy tắc phụ thuộc hàm; SQLite có thể cho phép cột không nhóm với kết quả không nên dựa vào |
| Lọc và ghép với `LEFT JOIN` | `ON` và `WHERE` có thể khác ý nghĩa | Nguyên tắc tương tự trên các hệ phổ biến |

Ví dụ một câu khá dễ chuyển đổi giữa nhiều SQL dialect:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_count,
    SUM(amount) AS paid_total
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2
   AND SUM(amount) >= 150
ORDER BY customer_id;
~~~

Khi chuyển hệ, hãy thay tên bảng/schema và kiểu literal cho đúng môi trường; không mặc định PostgreSQL `FILTER` hoặc cách dùng bí danh sẽ chạy ở mọi cơ sở dữ liệu. Nếu mục tiêu là dùng chung nhiều hệ, chọn cú pháp tổng hợp phổ biến và thử nghiệm trên đúng SQL dialect.

## 15. Những lỗi thường gặp

| Câu viết hoặc suy luận | Vấn đề | Hướng sửa |
| --- | --- | --- |
| `WHERE COUNT(*) >= 2` | `COUNT(*)` chưa có nhóm tại giai đoạn `WHERE` cùng cấp | `GROUP BY ... HAVING COUNT(*) >= 2` |
| `WHERE SUM(amount) >= 150` | Tổng tiền là giá trị **sau nhóm** | `HAVING SUM(amount) >= 150` |
| `HAVING order_status = 'PAID'` khi chỉ nhóm theo khách | `order_status` không có một giá trị đại diện duy nhất cho mỗi nhóm | `WHERE` trước nhóm nếu chỉ xét đơn PAID; hoặc tổng hợp có điều kiện |
| Dùng `WHERE order_status='PAID'` nhưng cần đếm **mọi** đơn của khách | Đơn NEW/CANCELLED đã bị loại trước `COUNT(*)` | Giữ mọi đơn, dùng `SUM(CASE ...)` hoặc `FILTER` để kiểm tra đơn PAID trong `HAVING` |
| `HAVING paid_count >= 2` ở cùng cấp `SELECT COUNT(*) AS paid_count` (PostgreSQL) | Alias đầu ra không có phạm vi ở `HAVING` | Viết `HAVING COUNT(*) >= 2` hoặc dùng CTE |
| `COUNT(*)` trong `LEFT JOIN` rồi gọi là “số đơn có thật” | Hàng khách không khớp vẫn tạo một hàng nối với cột đơn NULL | `COUNT(o.order_id)` |
| Đặt `o.order_status='PAID'` trong `WHERE` sau `LEFT JOIN` khi cần giữ khách không có đơn PAID | Hàng phía phải là NULL bị bộ lọc loại | Đặt điều kiện ở `ON` hoặc tổng hợp có điều kiện |
| `HAVING COUNT(*) = 0` trên bảng `orders` để tìm khách chưa có đơn | Khách không có hàng nguồn nên không tạo nhóm | Đi từ bảng khách và `LEFT JOIN`/`NOT EXISTS` |
| Dùng `COUNT(amount)` như thể đếm tất cả đơn | `COUNT(amount)` bỏ qua hàng có `amount IS NULL` | Chọn `COUNT(*)` hoặc đếm khóa đơn phù hợp |
| Dùng `SUM(amount) = 0` và coi nhóm toàn NULL là tổng bằng 0 | `SUM` của nhóm chỉ có NULL trả NULL, không bằng 0 | Quy định rõ muốn giữ NULL hay thay bằng 0 |
| Không viết `ORDER BY` nhưng mong nhóm trả theo ID | `GROUP BY` không cam kết thứ tự kết quả | `ORDER BY customer_id` rõ ràng |
| Dùng `HAVING` chỉ để lọc ngày/status của từng đơn | Khó đọc, có thể sai hoặc tốn công xử lý nhóm | Dùng `WHERE` cho điều kiện hàng |

## 16. Bài tập thực hành có đáp án

Các bài dưới đây dùng sáu khách hàng và 11 đơn hàng ở mục 2. Hãy xác định **điều kiện nào thuộc hàng, điều kiện nào thuộc nhóm**, rồi mới viết câu truy vấn. Đối chiếu kết quả sau khi thử trên database thực hành.

### Bài 1 — Tối thiểu hai đơn bất kỳ trạng thái

**Yêu cầu:** liệt kê mã khách hàng và số đơn của những khách có ít nhất hai đơn, không phân biệt trạng thái.

**Đáp án:**

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM lab_wh_165_orders
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

Kết quả: **(1,3), (2,3), (3,2), (4,2)**. Không cần `WHERE` vì mọi trạng thái đều được xét.

### Bài 2 — Chỉ xét đơn PAID, rồi lọc nhóm theo tổng tiền

**Yêu cầu:** mỗi khách phải có ít nhất hai đơn PAID và tổng tiền PAID từ 150 trở lên.

**Đáp án:**

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_total
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2
   AND SUM(amount) >= 150
ORDER BY customer_id;
~~~

Kết quả: **ID 1 (2 đơn, 200.00)** và **ID 2 (2 đơn, 240.00)**.

### Bài 3 — Giới hạn tháng 10 rồi đếm

**Yêu cầu:** chỉ tính đơn PAID từ 01/10/2026 đến trước 01/11/2026; lấy khách có ít nhất hai đơn trong phạm vi này.

**Đáp án:**

~~~sql
SELECT customer_id, COUNT(*) AS paid_october_count
FROM lab_wh_165_orders
WHERE order_status = 'PAID'
  AND placed_on >= DATE '2026-10-01'
  AND placed_on < DATE '2026-11-01'
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

Kết quả: **ID 1 (2 đơn)** và **ID 3 (2 đơn)**. ID 2 chỉ có một đơn PAID trong tháng 10; đơn PAID 111 ở tháng 9 không được xét.

### Bài 4 — Đếm tất cả đơn nhưng chọn khách có từ hai đơn PAID

**Yêu cầu:** cột hiển thị phải là **tổng số đơn mọi trạng thái**, nhưng chỉ chọn những khách có ít nhất hai đơn PAID.

**Đáp án:**

~~~sql
SELECT
    customer_id,
    COUNT(*) AS all_order_count
FROM lab_wh_165_orders
GROUP BY customer_id
HAVING SUM(
    CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END
) >= 2
ORDER BY customer_id;
~~~

Kết quả: **(1,3), (2,3), (3,2)**. Không thể thêm `WHERE order_status='PAID'` mà vẫn gọi `COUNT(*)` là đếm mọi trạng thái.

### Bài 5 — Khách hàng không có đơn PAID

**Yêu cầu:** tính cả khách chưa tạo đơn; chỉ trả các khách có **0 đơn PAID**.

**Đáp án:**

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_count
FROM lab_wh_165_customers AS c
LEFT JOIN lab_wh_165_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'PAID'
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(o.order_id) = 0
ORDER BY c.customer_id;
~~~

Kết quả: **Dũng (ID 4)** và **Giang (ID 6)**, đều có `paid_count = 0`. Trong `LEFT JOIN` dùng `COUNT(o.order_id)` thay cho `COUNT(*)`.

### Bài 6 — Phân biệt hai cách đếm khi có NULL

**Yêu cầu:** tìm khách có ít nhất hai đơn **đã có số tiền khác NULL**.

**Đáp án:**

~~~sql
SELECT
    customer_id,
    COUNT(*) AS all_count,
    COUNT(amount) AS priced_count
FROM lab_wh_165_orders
GROUP BY customer_id
HAVING COUNT(amount) >= 2
ORDER BY customer_id;
~~~

Kết quả là khách **1, 2, 3**. Khách 4 có hai đơn nhưng chỉ một đơn có số tiền, nên không được chọn.

### Bài 7 — Tại sao WHERE với COUNT(*) lại lỗi?

Một người viết:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM lab_wh_165_orders
WHERE COUNT(*) >= 2
GROUP BY customer_id;
~~~

**Yêu cầu:** giải thích và sửa.

**Đáp án:** `WHERE` kiểm tra các hàng trước khi tổng hợp; `COUNT(*)` là giá trị của mỗi nhóm, chưa tồn tại ở giai đoạn đó. Đổi `WHERE COUNT(*) >= 2` thành `HAVING COUNT(*) >= 2` đặt sau `GROUP BY`.

### Bài 8 — Lọc theo alias của phép tổng hợp

Một người viết PostgreSQL:

~~~sql
SELECT customer_id, SUM(amount) AS total_amount
FROM lab_wh_165_orders
GROUP BY customer_id
HAVING total_amount >= 200;
~~~

**Yêu cầu:** viết lại để chạy được và sắp ID tăng dần.

**Đáp án:**

~~~sql
SELECT customer_id, SUM(amount) AS total_amount
FROM lab_wh_165_orders
GROUP BY customer_id
HAVING SUM(amount) >= 200
ORDER BY customer_id;
~~~

Kết quả là khách **1 (250.00)** và **2 (540.00)** khi xét **mọi trạng thái**. Nếu chỉ xét đơn PAID, cần thêm `WHERE order_status = 'PAID'` và kết quả tổng sẽ khác.

### Bài 9 — Nhóm có tổng đơn PAID bằng 0 nhưng vẫn giữ mọi khách hàng

**Yêu cầu:** tạo báo cáo một dòng mỗi khách hàng, có số đơn PAID, và chỉ lấy nhóm có số đơn PAID bằng 0. Có thể dùng `FILTER` thay cho điều kiện trạng thái ở `ON` không?

**Đáp án (PostgreSQL):**

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) FILTER (
        WHERE o.order_status = 'PAID'
    ) AS paid_count
FROM lab_wh_165_customers AS c
LEFT JOIN lab_wh_165_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(o.order_id) FILTER (
    WHERE o.order_status = 'PAID'
) = 0
ORDER BY c.customer_id;
~~~

Kết quả vẫn là **Dũng và Giang**. `LEFT JOIN` giữ mọi khách, còn `FILTER` chỉ áp dụng cho phép `COUNT`, không loại các hàng nối khỏi toàn bộ truy vấn. Đây là một lựa chọn khi muốn trong cùng truy vấn có nhiều phép tổng hợp theo điều kiện.

## 17. Ghi nhớ: chọn đúng giai đoạn lọc

| Bạn muốn làm gì? | Nơi nên đặt điều kiện |
| --- | --- |
| Chọn **đơn hàng nào** được tính | `WHERE` trước `GROUP BY` |
| Chọn **khách hàng/nhóm nào** đạt số lượng hoặc tổng tiền | `HAVING` sau `GROUP BY` |
| Giữ đủ hàng bên trái của `LEFT JOIN`, chỉ giới hạn hàng bên phải được ghép | Điều kiện trong `ON` phù hợp |
| Đếm nhiều loại trạng thái **trong cùng một nhóm** | `CASE` trong hàm tổng hợp hoặc `FILTER` nếu hệ hỗ trợ |
| Lọc theo **tên cột tổng hợp đã tính** ở cấp truy vấn mới | CTE/truy vấn con rồi dùng `WHERE` ở cấp ngoài |

Hai câu hỏi cần đặt trước khi viết SQL là:

1. **“Những hàng nào phải tham gia phép tổng hợp?”** — Đây là công việc của `WHERE` hoặc điều kiện ghép phù hợp.
2. **“Những nhóm nào đạt điều kiện sau khi tổng hợp?”** — Đây là công việc của `HAVING`.

Khi phân biệt rõ **lọc trước nhóm** và **lọc sau nhóm**, bạn sẽ tránh được lỗi đưa `COUNT(*)` vào `WHERE`, nhầm số lượng đơn PAID với tổng số đơn, hoặc vô tình làm mất khách hàng không có đơn trong báo cáo `LEFT JOIN`. Đó là nền tảng để viết truy vấn tổng hợp đúng nghĩa nghiệp vụ và dễ kiểm chứng.
