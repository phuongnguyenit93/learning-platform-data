# Lấy các hàng đầu mỗi nhóm với thứ tự xác định

Trong báo cáo SQL, nhiều yêu cầu không phải là “lấy 10 hàng đầu tiên của cả bảng”, mà là **lấy một hoặc vài hàng đứng đầu trong *từng nhóm***: đơn mới nhất của mỗi khách hàng, ba sản phẩm bán chạy nhất của mỗi danh mục, giao dịch có giá trị cao nhất của mỗi tài khoản, hoặc hai bài viết mới nhất của mỗi tác giả.

Điểm khó không chỉ nằm ở việc chia nhóm, mà ở câu hỏi: **thế nào là “đứng đầu” và điều gì xảy ra khi hai hàng có cùng tiêu chí sắp xếp?** Nếu chỉ viết `ORDER BY created_at DESC`, hai bản ghi có cùng thời điểm có thể đổi vị trí giữa các lần chạy. Một truy vấn trông đúng trên dữ liệu nhỏ vẫn có thể chọn hàng khác khi thay đổi chỉ mục, kế hoạch thực thi hoặc số lượng bản ghi.

**Hàm cửa sổ (*window functions*)** là công cụ SQL rất phù hợp để giải quyết bài toán này. Với `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)`, ta đánh số hàng **riêng trong từng nhóm** rồi chọn hàng số 1 hoặc các hàng số 1 đến N. Khi muốn giữ **tất cả hàng đồng hạng**, có thể dùng `RANK` hay `DENSE_RANK` theo định nghĩa hạng mà nghiệp vụ cần.

Bài này sử dụng PostgreSQL làm môi trường thực hành chính, có bộ dữ liệu tự chứa, giải thích thứ tự xác định (*deterministic ordering*), ranh giới nhóm, xử lý `NULL`, sự khác nhau giữa lọc trước và sau khi xếp hạng, cách giữ nhóm rỗng, và các lựa chọn theo phương ngữ SQL Server, MySQL, SQLite, Oracle cùng PostgreSQL.

## 1. “Hàng đầu mỗi nhóm” nghĩa là gì?

Trước khi viết SQL, hãy xác định **ba thành phần**:

1. **Nhóm là gì?** Ví dụ mỗi `customer_id` là một nhóm, hoặc mỗi cặp `(department_id, year)` là một nhóm.
2. **Thứ tự ưu tiên là gì?** Mới nhất theo `ordered_at`, lớn nhất theo `amount`, ưu tiên trạng thái `PAID` trước, hay kết hợp nhiều tiêu chí?
3. **Xử lý đồng hạng thế nào?** Chỉ lấy đúng **một** hàng với khóa phụ phân định, hay lấy **mọi** hàng có cùng mức ưu tiên?

| Câu hỏi | Ý nghĩa một nhóm | Tiêu chí “đầu” | Số hàng mỗi nhóm |
|---|---|---|---|
| Đơn mới nhất của mỗi khách | Một `customer_id` | Thời điểm giảm dần | Tối đa 1 |
| Ba đơn mới nhất của mỗi khách | Một `customer_id` | Thời điểm giảm dần, ID phân định | Tối đa 3 |
| Mọi đơn đồng thời điểm mới nhất | Một `customer_id` | Chỉ thời điểm giảm dần | Có thể nhiều hơn 1 |
| Đơn giá trị lớn nhất mỗi khách | Một `customer_id` | Số tiền giảm dần | Tối đa 1 hoặc tất cả đồng giá |
| Hai sản phẩm bán chạy nhất mỗi danh mục mỗi tháng | Một cặp danh mục × tháng | Tổng số lượng giảm dần | Tối đa 2, hoặc hơn nếu giữ đồng hạng |

Đừng nhầm yêu cầu **“một hàng đầu mỗi nhóm”** với **“một hàng đầu toàn bộ bảng”**. Câu:

```sql
SELECT *
FROM orders_demo
ORDER BY ordered_at DESC, order_id DESC
LIMIT 1;
```

chỉ trả **một đơn mới nhất của toàn bộ bảng**, không phải đơn mới nhất của **mỗi khách**.

### 1.1. Mức chi tiết của kết quả

Nếu bảng đơn có nhiều hàng cho cùng khách, truy vấn chưa lọc có mức chi tiết **một hàng mỗi đơn**. Sau khi chọn `ROW_NUMBER = 1` theo khách, kết quả có mức chi tiết **tối đa một hàng mỗi khách có đơn**. Với `ROW_NUMBER <= 2`, kết quả có **tối đa hai hàng mỗi khách**.

Từ “**tối đa**” quan trọng: một khách chỉ có một đơn không thể có hai hàng; một khách chưa có đơn sẽ không xuất hiện nếu truy vấn bắt đầu từ bảng đơn. Muốn **mọi khách đều hiện** dù chưa có đơn, cần thêm cách nối phù hợp từ bảng khách hàng.

## 2. Dữ liệu mẫu: khách hàng và đơn hàng có thời điểm trùng

Các ví dụ chạy trên **PostgreSQL**. Hãy tạo trong một database thực hành riêng; không chạy lệnh tạo/xóa/cập nhật trên dữ liệu sản xuất.

### 2.1. Định nghĩa hai bảng

```sql
CREATE TABLE customers_demo (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(50) NOT NULL
);

CREATE TABLE orders_demo (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES customers_demo(customer_id),
    ordered_at TIMESTAMP NOT NULL,
    amount NUMERIC(12, 2),
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);
```

`order_id` là khóa chính, nên **không thể trùng** giữa hai đơn. `ordered_at` chỉ là thời điểm ghi nhận, có thể **trùng trong cùng khách**. `amount` cố ý được phép `NULL` để minh họa trường hợp chưa xác định số tiền. `status` có ba trạng thái.

### 2.2. Nạp dữ liệu cố định

```sql
INSERT INTO customers_demo (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi'),
    (4, 'Dung'),
    (5, 'Em'),
    (6, 'Giang');

INSERT INTO orders_demo
    (order_id, customer_id, ordered_at, amount, status)
VALUES
    (101, 1, TIMESTAMP '2025-02-10 09:00:00', 120000.00, 'PAID'),
    (102, 1, TIMESTAMP '2025-02-12 10:00:00',  90000.00, 'PAID'),
    (103, 1, TIMESTAMP '2025-02-12 10:00:00', 150000.00, 'PAID'),
    (104, 2, TIMESTAMP '2025-01-21 09:00:00', 200000.00, 'PAID'),
    (105, 2, TIMESTAMP '2025-02-15 16:00:00',  50000.00, 'NEW'),
    (106, 2, TIMESTAMP '2025-02-15 16:00:00',  50000.00, 'PAID'),
    (107, 3, TIMESTAMP '2025-02-20 14:00:00',  80000.00, 'PAID'),
    (108, 3, TIMESTAMP '2025-02-19 08:30:00', 110000.00, 'PAID'),
    (109, 3, TIMESTAMP '2025-02-20 14:00:00',  80000.00, 'CANCELLED'),
    (110, 4, TIMESTAMP '2025-02-01 12:00:00',  70000.00, 'NEW'),
    (111, 4, TIMESTAMP '2025-02-01 12:00:00',  70000.00, 'PAID'),
    (112, 5, TIMESTAMP '2025-02-22 11:00:00',       NULL, 'PAID'),
    (113, 5, TIMESTAMP '2025-02-23 08:00:00',  40000.00, 'NEW'),
    (114, 5, TIMESTAMP '2025-02-23 08:00:00',  40000.00, 'PAID');
```

Kết quả nguồn có **6 khách hàng** và **14 đơn hàng**. Khách **Giang [6]** chưa có đơn. Nhiều khách có các đơn được tạo **cùng giây**: An có 102 và 103; Binh có 105 và 106; Chi có 107 và 109; Dung có 110 và 111; Em có 113 và 114.

### 2.3. Bảng dữ liệu để đối chiếu kết quả

| Khách | order_id | ordered_at | amount | status |
|---|---:|---|---:|---|
| An (1) | 101 | 2025-02-10 09:00 | 120.000 | PAID |
| An (1) | 102 | 2025-02-12 10:00 | 90.000 | PAID |
| An (1) | 103 | 2025-02-12 10:00 | 150.000 | PAID |
| Binh (2) | 104 | 2025-01-21 09:00 | 200.000 | PAID |
| Binh (2) | 105 | 2025-02-15 16:00 | 50.000 | NEW |
| Binh (2) | 106 | 2025-02-15 16:00 | 50.000 | PAID |
| Chi (3) | 107 | 2025-02-20 14:00 | 80.000 | PAID |
| Chi (3) | 108 | 2025-02-19 08:30 | 110.000 | PAID |
| Chi (3) | 109 | 2025-02-20 14:00 | 80.000 | CANCELLED |
| Dung (4) | 110 | 2025-02-01 12:00 | 70.000 | NEW |
| Dung (4) | 111 | 2025-02-01 12:00 | 70.000 | PAID |
| Em (5) | 112 | 2025-02-22 11:00 | `NULL` | PAID |
| Em (5) | 113 | 2025-02-23 08:00 | 40.000 | NEW |
| Em (5) | 114 | 2025-02-23 08:00 | 40.000 | PAID |

Thiết kế có các trường hợp biên có chủ đích:

- Thời điểm trùng để thấy vì sao cần **khóa phụ** trong `ORDER BY`.
- Số tiền trùng để phân biệt `ROW_NUMBER`, `RANK` và `DENSE_RANK`.
- Một đơn có `amount = NULL` để học cách xếp giá trị chưa biết.
- Một khách chưa có đơn để minh họa **nhóm rỗng**.
- Trạng thái `NEW`, `PAID`, `CANCELLED` để phân biệt lọc trước và sau khi lấy hàng mới nhất.

## 3. ROW_NUMBER: đánh số riêng trong từng nhóm

Cú pháp cốt lõi:

```sql
ROW_NUMBER() OVER (
    PARTITION BY khoa_nhom
    ORDER BY tieu_chi_1, tieu_chi_2, ...
)
```

Trong đó:

- `PARTITION BY customer_id` chia các đơn thành **những nhóm độc lập theo khách**.
- `ORDER BY ordered_at DESC` đưa các đơn mới hơn lên trước **trong từng nhóm**.
- `ROW_NUMBER()` đánh số **1, 2, 3, ...** trong từng nhóm theo thứ tự cửa sổ.
- `ORDER BY order_id DESC` có thể bổ sung làm **tiêu chí phân định** khi hai đơn cùng thời điểm.

### 3.1. Xem số thứ tự của mọi đơn

```sql
SELECT
    o.customer_id,
    o.order_id,
    o.ordered_at,
    ROW_NUMBER() OVER (
        PARTITION BY o.customer_id
        ORDER BY o.ordered_at DESC, o.order_id DESC
    ) AS rn
FROM orders_demo AS o
ORDER BY o.customer_id, rn;
```

Kết quả:

| customer_id | order_id | ordered_at | rn |
|---:|---:|---|---:|
| 1 | 103 | 2025-02-12 10:00 | 1 |
| 1 | 102 | 2025-02-12 10:00 | 2 |
| 1 | 101 | 2025-02-10 09:00 | 3 |
| 2 | 106 | 2025-02-15 16:00 | 1 |
| 2 | 105 | 2025-02-15 16:00 | 2 |
| 2 | 104 | 2025-01-21 09:00 | 3 |
| 3 | 109 | 2025-02-20 14:00 | 1 |
| 3 | 107 | 2025-02-20 14:00 | 2 |
| 3 | 108 | 2025-02-19 08:30 | 3 |
| 4 | 111 | 2025-02-01 12:00 | 1 |
| 4 | 110 | 2025-02-01 12:00 | 2 |
| 5 | 114 | 2025-02-23 08:00 | 1 |
| 5 | 113 | 2025-02-23 08:00 | 2 |
| 5 | 112 | 2025-02-22 11:00 | 3 |

**Khách 6 không xuất hiện**, bởi bảng `orders_demo` không có đơn của khách đó. Khi `PARTITION BY` chia 14 dòng thành các nhóm, nó không tự tạo nhóm cho khóa không có hàng đầu vào.

### 3.2. Tại sao ROW_NUMBER vẫn đánh số khác nhau khi thời gian trùng?

Xét hai đơn của An:

```text
102 — 2025-02-12 10:00
103 — 2025-02-12 10:00
```

Nếu `ORDER BY` trong cửa sổ chỉ có `ordered_at DESC`, hai hàng được coi là **đồng hạng theo tiêu chí thời điểm**, nhưng `ROW_NUMBER` vẫn phải chọn một hàng làm số 1 và hàng còn lại làm số 2. **SQL không bảo đảm hàng nào nhận số nào** khi chúng đồng hạng trên toàn bộ danh sách `ORDER BY`.

Khi bổ sung:

```sql
ORDER BY ordered_at DESC, order_id DESC
```

hai hàng không còn đồng hạng vì `order_id` là khóa chính duy nhất. Đơn **103** đứng trước **102**. Nhờ đó, truy vấn chọn `rn = 1` có **quy tắc xác định**.

**“Xác định” không có nghĩa ID lớn hơn chắc chắn được tạo muộn hơn trong thế giới thực.** ID chỉ là tiêu chí phân định được quy ước khi thời điểm bằng nhau. Nếu nghiệp vụ cần thứ tự thực tế của sự kiện, dữ liệu nguồn phải có cột thứ tự hoặc timestamp đáng tin cậy, ví dụ một sequence sự kiện đơn điệu trong phạm vi phù hợp.

## 4. Lấy một hàng mới nhất của mỗi khách

Muốn lấy **đơn mới nhất của mỗi khách**, ta đánh số trong CTE rồi lọc `rn = 1` **ở truy vấn bên ngoài**:

```sql
WITH ranked_orders AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.ordered_at,
        o.amount,
        o.status,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM orders_demo AS o
)
SELECT
    customer_id,
    order_id,
    ordered_at,
    amount,
    status
FROM ranked_orders
WHERE rn = 1
ORDER BY customer_id;
```

Kết quả:

| customer_id | order_id | ordered_at | amount | status |
|---:|---:|---|---:|---|
| 1 | 103 | 2025-02-12 10:00 | 150.000 | PAID |
| 2 | 106 | 2025-02-15 16:00 | 50.000 | PAID |
| 3 | 109 | 2025-02-20 14:00 | 80.000 | CANCELLED |
| 4 | 111 | 2025-02-01 12:00 | 70.000 | PAID |
| 5 | 114 | 2025-02-23 08:00 | 40.000 | PAID |

Có **5 hàng**, đúng một hàng cho mỗi khách **có ít nhất một đơn**. Khách Giang không xuất hiện.

### 4.1. Vì sao lọc rn phải nằm ở truy vấn ngoài?

Nhiều DBMS không cho dùng hàm cửa sổ trực tiếp trong `WHERE` của cùng cấp truy vấn:

```sql
-- Không hợp lệ trong PostgreSQL:
SELECT order_id, customer_id
FROM orders_demo
WHERE ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at DESC, order_id DESC
) = 1;
```

Lý do về thứ tự xử lý logic: `WHERE` lọc các hàng đầu vào **trước giai đoạn tính kết quả hàm cửa sổ** trong cùng cấp `SELECT`. Ta không thể dùng `rn` của một hàm cửa sổ chưa được tính ở `WHERE` cùng cấp.

Vì vậy, hãy tách thành:

1. **Cấp trong**: tính `ROW_NUMBER` trên dữ liệu cần xếp.
2. **Cấp ngoài**: lọc `rn = 1`, hoặc `rn <= N`.

Ngoài CTE, một **derived table** cũng đúng:

```sql
SELECT x.customer_id, x.order_id, x.ordered_at
FROM (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM orders_demo
) AS x
WHERE x.rn = 1
ORDER BY x.customer_id;
```

CTE dễ đặt tên bước tính hơn; derived table hữu ích nếu chỉ cần một truy vấn ngắn. CTE không phải bảng tạm tồn tại vĩnh viễn và **không tự bảo đảm nhanh hơn**; kế hoạch thực thi phụ thuộc DBMS.

### 4.2. Lọc rn = 1 không sắp thứ tự kết quả cuối

`ORDER BY` **bên trong `OVER(...)`** chỉ xác định cách **đánh số của từng nhóm**, không cam kết hàng đầu ra cuối cùng được hiển thị theo thứ tự nào.

Hai mệnh đề phục vụ hai mục đích:

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at DESC, order_id DESC
) AS rn
-- Quyết định ai nhận rn = 1, rn = 2...

...
ORDER BY customer_id;
-- Quyết định thứ tự các hàng khi hiển thị cuối cùng.
```

Nếu cần phân trang hoặc đối chiếu kết quả ổn định, không bỏ qua `ORDER BY` cuối.

## 5. Lấy N hàng đầu cho từng nhóm

Muốn **hai đơn mới nhất mỗi khách**, giữ CTE xếp hạng nhưng đổi điều kiện thành:

```sql
WITH ranked_orders AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM orders_demo AS o
)
SELECT customer_id, order_id, ordered_at, rn
FROM ranked_orders
WHERE rn <= 2
ORDER BY customer_id, rn;
```

Kết quả:

| customer_id | order_id | rn |
|---:|---:|---:|
| 1 | 103 | 1 |
| 1 | 102 | 2 |
| 2 | 106 | 1 |
| 2 | 105 | 2 |
| 3 | 109 | 1 |
| 3 | 107 | 2 |
| 4 | 111 | 1 |
| 4 | 110 | 2 |
| 5 | 114 | 1 |
| 5 | 113 | 2 |

Có **10 hàng**: năm khách có đơn, mỗi khách có ít nhất hai đơn. Trong dữ liệu khác, khách chỉ có một đơn sẽ đóng góp **một** hàng chứ không được tạo thêm hàng giả.

### 5.1. Top 3 và top N

Chỉ cần thay số:

```sql
WHERE rn <= 3
```

Nếu N do ứng dụng cung cấp, sử dụng **tham số truy vấn** để truyền giá trị N thay vì nối chuỗi SQL từ đầu vào người dùng. Ngoài ra nên kiểm tra N dương và có giới hạn phù hợp nếu màn hình không được phép trả số lượng hàng quá lớn.

### 5.2. Top N khác phân trang toàn bảng

`LIMIT 2` ở cuối câu lệnh:

```sql
SELECT *
FROM orders_demo
ORDER BY ordered_at DESC, order_id DESC
LIMIT 2;
```

trả **hai đơn toàn bảng**. Trong khi `WHERE rn <= 2` trên CTE xếp hạng theo `customer_id` có thể trả **tối đa hai đơn của *mỗi* khách**.

Nếu muốn phân trang *trong từng nhóm*, có thể lọc khoảng `rn BETWEEN 3 AND 4`, nhưng phải giữ cùng tiêu chí sắp xếp ổn định. Khi dữ liệu thay đổi giữa các lần lấy trang, cách đánh số vẫn có thể dịch chuyển; cần cân nhắc giao dịch/snapshot hoặc chiến lược phân trang theo khóa nếu ứng dụng đòi hỏi tính nhất quán cao.

## 6. Thứ tự xác định: giải quyết đồng hạng thế nào?

Đây là trọng tâm của bài. **Một tiêu chí sắp xếp xác định thứ tự hoàn toàn** khi hai hàng khác nhau không còn đồng hạng trên toàn bộ danh sách `ORDER BY`.

Ví dụ:

```sql
ORDER BY ordered_at DESC
```

không đủ phân định các đơn 102 và 103 của An vì có cùng `ordered_at`.

Thêm khóa chính:

```sql
ORDER BY ordered_at DESC, order_id DESC
```

giúp chọn **103** ổn định theo quy tắc đã công bố.

### 6.1. Quy tắc chọn khóa phụ (*tie-breaker*)

Khóa phụ nên:

- Có giá trị được xác định, tránh tình trạng hai hàng vẫn đồng hạng.
- Là **duy nhất trong phạm vi nhóm** hoặc kết hợp với các cột khác tạo khóa duy nhất.
- Phù hợp với nghiệp vụ: ví dụ ưu tiên đơn `PAID` trước đơn `NEW`, rồi mới lấy ID lớn nhất nếu vẫn cùng thời gian.
- Không dựa trên thứ tự chèn ngẫu nhiên hay thứ tự vật lý của bảng.

| Tiêu chí `ORDER BY` | Có xác định hoàn toàn không? | Lý do |
|---|---|---|
| `ordered_at DESC` | Không, trong dữ liệu mẫu | Nhiều đơn có cùng thời điểm |
| `ordered_at DESC, order_id DESC` | Có, với bảng mẫu | `order_id` là khóa chính duy nhất |
| `amount DESC` | Không | Nhiều đơn có cùng giá trị; có `NULL` |
| `amount DESC NULLS LAST, order_id DESC` | Có, với bảng mẫu | Quy tắc `NULL` rõ ràng, ID duy nhất |
| `status ASC, ordered_at DESC` | Chưa chắc | Có thể trùng trạng thái và thời điểm |
| `status ASC, ordered_at DESC, order_id DESC` | Có, với bảng mẫu | ID làm khóa cuối phân định |

**Chú ý về tính nhất quán:** truy vấn có thứ tự xác định không đảm bảo hai lần chạy trên **hai ảnh chụp dữ liệu khác nhau** cho cùng kết quả. Nếu có đơn mới, đơn mới có thể trở thành hàng số 1. “Xác định” ở đây nghĩa là **cùng một tập dữ liệu và cùng quy tắc so sánh sẽ chọn cùng hàng**, không phải dữ liệu bất biến mãi mãi.

### 6.2. Tránh sử dụng cột mang ý nghĩa mơ hồ

Nếu `order_id` được sinh theo cơ chế phân tán, ID lớn hơn có thể **không** tương ứng với thời điểm xảy ra sự kiện muộn hơn. Việc dùng `order_id DESC` để phân định là **quy tắc kỹ thuật**, cần được chấp nhận hoặc thay thế bằng một trường thứ tự nghiệp vụ đáng tin cậy.

Trong ví dụ, `ordered_at` là `TIMESTAMP` không có múi giờ. Với hệ thống đa vùng, nên định nghĩa rõ thời điểm được lưu ở UTC hay theo vùng và sử dụng kiểu/timezone phù hợp; mọi so sánh “mới nhất” phải dựa trên cùng một chuẩn thời gian.

## 7. Một hàng duy nhất hay mọi hàng đồng hạng? ROW_NUMBER, RANK, DENSE_RANK

Ba hàm phổ biến:

| Hàm | Cách đánh số | Khi nào phù hợp? |
|---|---|---|
| `ROW_NUMBER()` | Luôn 1, 2, 3... cho từng hàng; không lặp số | Muốn **tối đa N hàng** trong mỗi nhóm |
| `RANK()` | Các hàng cùng tiêu chí có **cùng hạng**, hạng sau có thể bị nhảy | Muốn giữ các hàng đồng hạng theo thứ hạng thi đấu |
| `DENSE_RANK()` | Các hàng đồng hạng cùng số, nhưng **không nhảy hạng** | Muốn lấy **N mức giá trị/thứ hạng khác biệt** đầu tiên |

**Các hàng được coi là đồng hạng khi bằng nhau trên toàn bộ biểu thức `ORDER BY` trong cửa sổ.** Nếu thêm `order_id` duy nhất vào `ORDER BY`, mỗi hàng sẽ là một nhóm đồng hạng riêng, làm `RANK`/`DENSE_RANK` có thể không còn đúng ý nghĩa “giữ những đơn có cùng thời điểm/giá tiền”.

### 7.1. So sánh trên dữ liệu có giá trị bằng nhau

Xét khách Em, có ba đơn:

| order_id | amount |
|---:|---:|
| 113 | 40.000 |
| 114 | 40.000 |
| 112 | `NULL` |

Trong PostgreSQL, ta đặt `NULLS LAST` để số tiền chưa biết không được coi là lớn hơn số tiền xác định:

```sql
SELECT
    order_id,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY amount DESC NULLS LAST, order_id DESC
    ) AS row_no,
    RANK() OVER (
        PARTITION BY customer_id
        ORDER BY amount DESC NULLS LAST
    ) AS sales_rank,
    DENSE_RANK() OVER (
        PARTITION BY customer_id
        ORDER BY amount DESC NULLS LAST
    ) AS dense_sales_rank
FROM orders_demo
WHERE customer_id = 5
ORDER BY amount DESC NULLS LAST, order_id DESC;
```

Kết quả:

| order_id | amount | row_no | sales_rank | dense_sales_rank |
|---:|---:|---:|---:|---:|
| 114 | 40.000 | 1 | 1 | 1 |
| 113 | 40.000 | 2 | 1 | 1 |
| 112 | `NULL` | 3 | 3 | 2 |

Giải thích:

- `ROW_NUMBER` cần chọn một đơn đầu tiên, nên nhờ ID giảm dần: **114** số 1, **113** số 2.
- `RANK` xét **chỉ amount**, nên 114 và 113 cùng hạng 1; hàng sau nhận hạng **3**.
- `DENSE_RANK` cũng cho hai đơn cùng hạng 1, nhưng hàng sau nhận hạng **2** vì không bỏ qua số hạng.

Lưu ý: các giá trị `NULL` có thể được xem là đồng hạng với nhau trong bảng xếp hạng cửa sổ theo quy tắc so sánh của DBMS. Nhưng `amount = NULL` trong `WHERE` vẫn không cho `TRUE`; đây là hai ngữ cảnh khác nhau.

### 7.2. Lấy mọi đơn cùng thời điểm mới nhất

Yêu cầu **“tất cả đơn được ghi nhận tại thời điểm mới nhất của mỗi khách”**, dù nhiều đơn cùng giờ. Đây không phải “chọn đúng một hàng rồi phân định theo ID”.

```sql
WITH time_ranked AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC
        ) AS time_rank
    FROM orders_demo
)
SELECT customer_id, order_id, ordered_at
FROM time_ranked
WHERE time_rank = 1
ORDER BY customer_id, order_id DESC;
```

Kết quả:

| customer_id | order_id |
|---:|---:|
| 1 | 103 |
| 1 | 102 |
| 2 | 106 |
| 2 | 105 |
| 3 | 109 |
| 3 | 107 |
| 4 | 111 |
| 4 | 110 |
| 5 | 114 |
| 5 | 113 |

Kết quả **10 hàng**, vì mỗi khách có hai đơn cùng thời điểm mới nhất trong dữ liệu mẫu. `RANK() = 1` lấy mọi đơn **đồng hạng theo thời điểm**, không ép chọn một đơn.

**Cực kỳ quan trọng:** Không thêm `order_id DESC` vào `ORDER BY` **bên trong `RANK`** nếu mục tiêu là giữ mọi đơn cùng thời điểm. Làm vậy sẽ phá đồng hạng, khiến kết quả lại chỉ còn một hàng mỗi khách. Ta có thể đặt `order_id DESC` trong **`ORDER BY` cuối** để sắp ổn định **những hàng đã được giữ**.

### 7.3. Top 2 với RANK và DENSE_RANK khác Top 2 với ROW_NUMBER

Khi nói “**Top 2 đơn giá trị cao nhất của mỗi khách**”, có ba cách hiểu:

1. **Đúng tối đa 2 đơn**: `ROW_NUMBER() <= 2` với khóa phụ duy nhất.
2. **Những đơn có thứ hạng thi đấu từ 1 tới 2, gồm đồng hạng**: `RANK() <= 2`.
3. **Những đơn thuộc hai mức giá trị cao nhất, gồm toàn bộ đồng giá**: `DENSE_RANK() <= 2`.

Ví dụ khách Binh có các mức tiền `200.000, 50.000, 50.000`:

- `ROW_NUMBER <= 2` chọn **104** và **106** nếu phân định bằng `order_id DESC`.
- `RANK <= 2` chọn **104, 105, 106** vì hai đơn 50.000 cùng hạng 2.
- `DENSE_RANK <= 2` cũng chọn **104, 105, 106** ở ví dụ này, nhưng khác `RANK` khi sau một hạng đồng điểm xuất hiện mức hạng tiếp theo.

Với khách Em, `RANK` và `DENSE_RANK` ở mục 7.1 cho thấy mức `NULL` có hạng 3 và 2. Do đó `RANK <= 2` giữ hai đơn 40.000, còn `DENSE_RANK <= 2` sẽ giữ cả hàng `NULL` nếu không **lọc amount IS NOT NULL** trước. Với nghiệp vụ “giá trị cao nhất”, nên quyết định rõ có xem `NULL` là một mức để xếp hạng không.

### 7.4. “WITH TIES” ở cấp toàn cục không tự chia nhóm

Một số DBMS hỗ trợ `FETCH FIRST N ROWS WITH TIES` hoặc `TOP (N) WITH TIES` trong cú pháp chọn hàng đầu. Nếu áp vào một `SELECT` toàn bảng, chúng thường xét **toàn bộ tập truy vấn** theo `ORDER BY` chứ không tự hiểu “mỗi khách một nhóm”.

Để làm **top N mỗi khách kèm đồng hạng**, hãy định nghĩa nhóm tường minh bằng `PARTITION BY customer_id` và dùng `RANK`/`DENSE_RANK` theo yêu cầu. Hoặc áp dụng `WITH TIES` bên trong một truy vấn con tương quan `LATERAL`/`APPLY` khi DBMS hỗ trợ, với phạm vi một khách trong từng lượt.

## 8. Lọc trước hay sau khi xếp hạng: hai câu hỏi khác nhau

Hãy phân biệt:

- **“Đơn PAID mới nhất của từng khách”**: loại các đơn khác `PAID` **trước khi xếp hạng**.
- **“Đơn mới nhất của từng khách, nhưng chỉ hiện nếu nó PAID”**: xếp hạng **mọi đơn trước**, rồi kiểm tra trạng thái của hàng mới nhất.

Trên dữ liệu mẫu, khách Chi có đơn mới nhất **109 CANCELLED**, còn đơn `PAID` mới nhất là **107**. Hai câu hỏi sẽ cho kết quả khác.

### 8.1. Cách A — Xếp hạng sau khi lọc đơn PAID

```sql
WITH ranked_paid AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM orders_demo AS o
    WHERE o.status = 'PAID'
)
SELECT customer_id, order_id, ordered_at
FROM ranked_paid
WHERE rn = 1
ORDER BY customer_id;
```

Kết quả:

| customer_id | order_id | Ý nghĩa |
|---:|---:|---|
| 1 | 103 | Đơn PAID mới nhất của An |
| 2 | 106 | Đơn PAID mới nhất của Binh |
| 3 | 107 | Đơn PAID mới nhất của Chi |
| 4 | 111 | Đơn PAID mới nhất của Dung |
| 5 | 114 | Đơn PAID mới nhất của Em |

Trong CTE, `WHERE status = 'PAID'` bỏ đơn 109 trước khi `ROW_NUMBER` được tính; đối với Chi, 107 trở thành số 1.

### 8.2. Cách B — Lấy đơn mới nhất bất kể trạng thái, rồi mới lọc PAID

```sql
WITH ranked_all AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.status,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM orders_demo AS o
)
SELECT customer_id, order_id, status
FROM ranked_all
WHERE rn = 1
  AND status = 'PAID'
ORDER BY customer_id;
```

Kết quả: khách **1 → 103, 2 → 106, 4 → 111, 5 → 114**. Khách **3** không xuất hiện vì đơn mới nhất đã chọn là **109 CANCELLED**.

Sự khác biệt nằm ở **phạm vi các hàng được xếp hạng**, không phải cách tính `ROW_NUMBER`. Khi đọc một yêu cầu báo cáo, cần xác định rõ các điều kiện nên áp dụng **trước** hay **sau** phép chọn top.

### 8.3. Lọc theo ngày cũng có vấn đề tương tự

“Đơn mới nhất *trong tháng 2* của mỗi khách” yêu cầu lọc khoảng ngày **trong CTE trước xếp hạng**. “Đơn mới nhất của mỗi khách *nếu nó thuộc tháng 2*” yêu cầu chọn trên tất cả đơn trước, rồi kiểm tra ngày ở ngoài.

```sql
-- Mẫu: lọc tháng trong tập đầu vào rồi tìm mới nhất.
WITH ranked_feb AS (
    SELECT
        o.customer_id,
        o.order_id,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM orders_demo AS o
    WHERE o.ordered_at >= TIMESTAMP '2025-02-01 00:00:00'
      AND o.ordered_at <  TIMESTAMP '2025-03-01 00:00:00'
)
SELECT customer_id, order_id
FROM ranked_feb
WHERE rn = 1
ORDER BY customer_id;
```

Khoảng **nửa mở** `>= đầu tháng` và `< đầu tháng sau` tránh vấn đề bỏ sót bản ghi có phần giây hoặc precision cao ở cuối ngày. Ví dụ sử dụng `TIMESTAMP` vì dữ liệu mẫu có kiểu này.

## 9. Giữ cả khách chưa có đơn: LEFT JOIN sau khi xếp hạng

Nếu bài toán là **“Mỗi khách một hàng, kèm đơn mới nhất nếu có”**, phải bắt đầu từ danh sách **tất cả khách**. Chỉ xếp hạng bảng đơn rồi lọc `rn = 1` sẽ bỏ khách Giang.

Cách phù hợp:

```sql
WITH ranked_orders AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.ordered_at,
        o.status,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM orders_demo AS o
)
SELECT
    c.customer_id,
    c.customer_name,
    r.order_id AS latest_order_id,
    r.status AS latest_status
FROM customers_demo AS c
LEFT JOIN ranked_orders AS r
    ON r.customer_id = c.customer_id
   AND r.rn = 1
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | customer_name | latest_order_id | latest_status |
|---:|---|---:|---|
| 1 | An | 103 | PAID |
| 2 | Binh | 106 | PAID |
| 3 | Chi | 109 | CANCELLED |
| 4 | Dung | 111 | PAID |
| 5 | Em | 114 | PAID |
| 6 | Giang | `NULL` | `NULL` |

Khách Giang không có đơn nên các cột của phía `ranked_orders` là `NULL`, nhưng hàng khách vẫn được giữ nhờ `LEFT JOIN`.

### 9.1. Đặt rn = 1 trong ON, không đặt trong WHERE

So sánh hai cách:

```sql
-- Giữ khách chưa có đơn:
LEFT JOIN ranked_orders AS r
    ON r.customer_id = c.customer_id
   AND r.rn = 1
```

với:

```sql
-- Làm mất khách chưa có đơn:
LEFT JOIN ranked_orders AS r
    ON r.customer_id = c.customer_id
WHERE r.rn = 1
```

Ở cách thứ hai, hàng Giang có `r.rn = NULL` nên điều kiện `r.rn = 1` cho `UNKNOWN`, và `WHERE` loại hàng đó. `LEFT JOIN` vốn giữ khách không có đối tác, nhưng bộ lọc đặt sau phép nối đã làm mất hàng.

Đây là lỗi thường thấy khi muốn báo cáo **đầy đủ danh mục, nhân viên hoặc khách hàng** kèm một bản ghi liên quan “mới nhất”.

### 9.2. Không dùng LEFT JOIN trước khi xếp hạng một cách tùy tiện

Có thể đánh số trên kết quả `customers LEFT JOIN orders`, nhưng khách không có đơn sẽ có một **hàng bổ sung với các cột đơn `NULL`**, và `ROW_NUMBER` có thể đánh số 1 cho chính hàng đó. Điều đó không có nghĩa khách có một đơn thực.

Tách hai bước **xếp hạng đơn thật** rồi `LEFT JOIN` với bảng khách giúp phân biệt rõ:

- Bảng `orders_demo`: chỉ có các đơn thực sự.
- Kết quả `ranked_orders`: tối đa một đơn đứng đầu mỗi khách sau khi lọc.
- Bảng `customers_demo`: quyết định tập khách phải hiển thị.

## 10. Ưu tiên nghiệp vụ nhiều cấp bằng CASE trong ORDER BY

Đôi khi “hàng đầu” không phải hàng mới nhất tuyệt đối. Ví dụ:

> Với mỗi khách, ưu tiên một đơn `PAID` nếu có; trong các đơn `PAID` chọn mới nhất; nếu không có `PAID` thì chọn `NEW`; nếu cũng không có thì chọn `CANCELLED`.

Ta có thể đưa **độ ưu tiên trạng thái** vào `ORDER BY` trong cửa sổ:

```sql
WITH preferred AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.status,
        o.ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY
                CASE o.status
                    WHEN 'PAID' THEN 1
                    WHEN 'NEW' THEN 2
                    WHEN 'CANCELLED' THEN 3
                    ELSE 4
                END ASC,
                o.ordered_at DESC,
                o.order_id DESC
        ) AS rn
    FROM orders_demo AS o
)
SELECT customer_id, order_id, status
FROM preferred
WHERE rn = 1
ORDER BY customer_id;
```

Kết quả: **1 → 103 PAID; 2 → 106 PAID; 3 → 107 PAID; 4 → 111 PAID; 5 → 114 PAID**.

Với khách Chi, truy vấn **không** chọn đơn 109 CANCELLED dù nó có thời điểm bằng đơn 107 và ID lớn hơn. `CASE` đặt `PAID` lên trước toàn bộ các trạng thái khác, rồi mới xét thời điểm và ID.

**Thứ tự các biểu thức rất quan trọng.** 

```sql
ORDER BY priority ASC, ordered_at DESC, order_id DESC
```

nghĩa là **ưu tiên trạng thái trước**, rồi mới mới nhất **bên trong cùng mức ưu tiên**. Nếu đổi thành `ORDER BY ordered_at DESC, priority ASC, order_id DESC`, thời điểm lại là tiêu chí quan trọng hơn trạng thái. Hai cách trả lời hai yêu cầu khác nhau.

### 10.1. Ưu tiên hàng đầy đủ thông tin

Trong dữ liệu nhập từ nhiều nguồn, một ứng dụng có thể muốn chọn dòng có cột quan trọng **không `NULL`** trước rồi mới xét thời gian:

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY
        CASE WHEN amount IS NULL THEN 1 ELSE 0 END,
        ordered_at DESC,
        order_id DESC
) AS rn
```

Cách này có ý nghĩa “**ưu tiên đơn có số tiền đã biết**”, **không** phải “đơn mới nhất bất kể số tiền”. Với khách Em, có một đơn 112 tiền `NULL` nhưng cũ hơn, nên hai quy tắc đều chọn 114 trong dữ liệu mẫu; trên dữ liệu khác, chúng có thể chọn đơn khác nhau.

## 11. Giá trị NULL trong tiêu chí xếp hạng

Với truy vấn “đơn có tiền lớn nhất mỗi khách”, `amount` có thể `NULL`:

```sql
WITH most_expensive AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.amount,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.amount DESC NULLS LAST, o.order_id DESC
        ) AS rn
    FROM orders_demo AS o
)
SELECT customer_id, order_id, amount
FROM most_expensive
WHERE rn = 1
ORDER BY customer_id;
```

Kết quả:

| customer_id | order_id | amount |
|---:|---:|---:|
| 1 | 103 | 150.000 |
| 2 | 104 | 200.000 |
| 3 | 108 | 110.000 |
| 4 | 111 | 70.000 |
| 5 | 114 | 40.000 |

Trong PostgreSQL, nếu viết `ORDER BY amount DESC` mà **không có `NULLS LAST`**, `NULL` mặc định có thể đứng **trước** giá trị đã biết khi sắp giảm dần. Khi đó đơn 112 của Em có thể bị chọn là “giá trị lớn nhất” chỉ vì số tiền chưa xác định.

Do đó, với các câu hỏi chọn lớn nhất/nhỏ nhất, hãy xác định:

1. `NULL` được **bỏ qua hoàn toàn** hay vẫn tham gia xếp hạng?
2. Nếu tham gia, `NULL` phải ở **đầu hay cuối**?
3. Nếu một nhóm **chỉ có `NULL`**, kết quả nên chọn một hàng có `NULL` hay không trả hàng?

### 11.1. Loại NULL khỏi tập xếp hạng

Nếu nghiệp vụ chỉ xem những số tiền đã biết:

```sql
WITH ranked_known_amounts AS (
    SELECT
        customer_id,
        order_id,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY amount DESC, order_id DESC
        ) AS rn
    FROM orders_demo
    WHERE amount IS NOT NULL
)
SELECT customer_id, order_id, amount
FROM ranked_known_amounts
WHERE rn = 1
ORDER BY customer_id;
```

Truy vấn này không xếp hạng những đơn có `amount = NULL`. Nếu một khách **chỉ** có đơn với số tiền chưa biết, khách đó **không có ứng viên** và sẽ biến mất khỏi kết quả bắt đầu từ bảng đơn. Muốn giữ khách với trạng thái “chưa có tiền hợp lệ”, dùng `LEFT JOIN` từ bảng khách như mục 9.

**Cú pháp `NULLS FIRST/LAST` không được hỗ trợ giống nhau ở mọi DBMS.** Một giải pháp dễ chuyển phương ngữ hơn là:

```sql
ORDER BY
    CASE WHEN amount IS NULL THEN 1 ELSE 0 END ASC,
    amount DESC,
    order_id DESC
```

Hãy dùng cùng quy tắc xử lý `NULL` trong mọi truy vấn cùng nghiệp vụ, nếu không màn hình và báo cáo có thể chọn các hàng khác nhau.

## 12. FIRST_VALUE và MAX không tự trả về toàn bộ hàng đầu

Người mới học có thể nghĩ “muốn đơn mới nhất thì dùng `MAX(ordered_at)`”. Nhưng:

```sql
SELECT customer_id, MAX(ordered_at) AS newest_time
FROM orders_demo
GROUP BY customer_id;
```

chỉ trả **thời điểm mới nhất**, không cung cấp một **hàng đơn duy nhất**. Nếu khách có hai đơn cùng thời điểm, nối ngược lại để lấy đơn:

```sql
SELECT o.*
FROM orders_demo AS o
JOIN (
    SELECT customer_id, MAX(ordered_at) AS newest_time
    FROM orders_demo
    GROUP BY customer_id
) AS m
    ON m.customer_id = o.customer_id
   AND m.newest_time = o.ordered_at;
```

thì sẽ trả **cả hai đơn cùng thời điểm mới nhất** của từng khách trong dữ liệu mẫu, không phải đúng một hàng. Đó là kết quả hợp lệ nếu yêu cầu là **giữ mọi đơn đồng thời điểm**; còn nếu chỉ cần một đơn, phải có quy tắc phân định thêm.

### 12.1. FIRST_VALUE trả một giá trị, không loại hàng

`FIRST_VALUE` là hàm cửa sổ lấy giá trị của hàng đầu trong cửa sổ:

```sql
SELECT
    customer_id,
    order_id,
    FIRST_VALUE(order_id) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC, order_id DESC
    ) AS latest_order_id
FROM orders_demo
ORDER BY customer_id, order_id;
```

Kết quả vẫn có **14 hàng**, bởi `FIRST_VALUE` **không làm giảm số hàng**. Nó chỉ lặp `latest_order_id` của nhóm trên mỗi hàng đơn thuộc nhóm. Ví dụ khách An có cả ba hàng đơn, và cột `latest_order_id` đều là 103.

Nếu chỉ cần một hàng mỗi khách, `ROW_NUMBER` và lọc `rn = 1` (hoặc một cấu trúc chọn top khác) thường rõ hơn. `FIRST_VALUE` hữu ích khi muốn **giữ toàn bộ các hàng chi tiết** và hiển thị giá trị của hàng đầu bên cạnh chúng.

### 12.2. Đừng kết hợp MAX và một cột khác tùy ý

Truy vấn kiểu:

```sql
-- Không đáp ứng mục tiêu "hàng mới nhất" trong PostgreSQL:
SELECT customer_id, MAX(ordered_at), order_id
FROM orders_demo
GROUP BY customer_id;
```

không hợp lệ trong PostgreSQL vì `order_id` không được nhóm hay tổng hợp. Dùng `MAX(order_id)` thêm vào cũng **không bảo đảm nó thuộc hàng có `MAX(ordered_at)`** trên dữ liệu tổng quát. Hai phép `MAX` độc lập có thể lấy giá trị từ **hai hàng khác nhau**.

Nếu yêu cầu thực sự là “lấy cả hàng đứng đầu theo nhiều tiêu chí”, hãy **xếp hạng hàng trước khi lọc**, thay vì ghép ngẫu nhiên các hàm tổng hợp.

## 13. PostgreSQL: DISTINCT ON — cách ngắn để lấy một hàng mỗi nhóm

PostgreSQL có cú pháp `DISTINCT ON`, tiện khi cần **một hàng duy nhất theo khóa nhóm** và có quy tắc sắp xếp cụ thể:

```sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    ordered_at,
    status
FROM orders_demo
ORDER BY customer_id, ordered_at DESC, order_id DESC;
```

Kết quả chọn **103, 106, 109, 111, 114** — giống truy vấn `ROW_NUMBER = 1` ở mục 4.

Giải thích:

- `DISTINCT ON (customer_id)` giữ **hàng đầu** trong mỗi tập cùng `customer_id`.
- `ORDER BY customer_id, ordered_at DESC, order_id DESC` quyết định hàng nào đứng đầu mỗi tập.
- `order_id DESC` đảm bảo hai hàng cùng thời điểm được phân định bằng ID.

### 13.1. Điều kiện dùng DISTINCT ON an toàn

PostgreSQL yêu cầu các biểu thức của `DISTINCT ON` phải khớp với các biểu thức đầu tiên bên trái của `ORDER BY`. Ví dụ:

```sql
SELECT DISTINCT ON (customer_id) ...
ORDER BY customer_id, ordered_at DESC, order_id DESC;
```

Không nên bỏ `ORDER BY` rồi mong hàng được giữ sẽ luôn là mới nhất: nếu không chỉ định thứ tự phù hợp, “hàng đầu” của mỗi nhóm **không được xác định theo ý nghĩa nghiệp vụ**.

`DISTINCT ON` **không phải cú pháp SQL tiêu chuẩn được hỗ trợ rộng rãi** trong MySQL, SQL Server và SQLite. Với code cần dễ chuyển hệ quản trị, `ROW_NUMBER` trong CTE thường là cách biểu đạt phổ biến hơn.

### 13.2. DISTINCT ON và nhiều hàng đồng hạng

`DISTINCT ON` **chỉ giữ một hàng mỗi nhóm**, không giữ tất cả đơn cùng thời điểm cao nhất. Nếu muốn giữ **mọi hàng đồng hạng theo thời điểm**, dùng `RANK = 1` hoặc một kỹ thuật khác có ngữ nghĩa đồng hạng rõ ràng.

## 14. PostgreSQL: LEFT JOIN LATERAL với ORDER BY ... LIMIT 1

Một cách tiếp cận khác: với **mỗi khách**, chạy một truy vấn nguồn chỉ lấy đơn mới nhất của khách đó. PostgreSQL hỗ trợ `LATERAL`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    latest.order_id,
    latest.ordered_at,
    latest.status
FROM customers_demo AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.ordered_at,
        o.status
    FROM orders_demo AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS latest ON TRUE
ORDER BY c.customer_id;
```

Kết quả:

- An → 103.
- Binh → 106.
- Chi → 109.
- Dung → 111.
- Em → 114.
- Giang → `NULL` ở các cột đơn.

**Điểm khác với `LIMIT 1` toàn bảng:** truy vấn `LATERAL` tham chiếu `c.customer_id` của **hàng khách hiện tại**, nên mỗi khách có tập đơn riêng để chọn `LIMIT 1`.

### 14.1. Khi nào dùng LATERAL?

`ROW_NUMBER` thường phù hợp để xếp hạng nhiều hàng trong một tập kết quả. `LEFT JOIN LATERAL` có thể hữu ích khi:

- Truy vấn ngoài chỉ chọn **một số khách cụ thể**.
- Có chỉ mục hỗ trợ tìm đơn theo `customer_id` rồi theo thứ tự giảm dần.
- Muốn giữ cả khách không có đơn.
- Muốn lấy một hàng hoặc một số lượng nhỏ hàng tương quan mà không cần xếp hạng toàn bộ các đơn.

Ví dụ chỉ mục PostgreSQL:

```sql
CREATE INDEX idx_orders_customer_time_id
ON orders_demo (customer_id, ordered_at DESC, order_id DESC);
```

Một chỉ mục phù hợp có thể giúp DBMS tìm đơn đầu của từng khách mà không cần sắp xếp nhiều hàng tương quan. Nhưng không có kết luận **`LATERAL` luôn nhanh hơn `ROW_NUMBER`**; với số khách lớn, kích thước bảng và độ chọn lọc khác nhau, kế hoạch tốt nhất có thể khác.

### 14.2. LATERAL lấy Top 2

Chỉ đổi `LIMIT 1` thành `LIMIT 2`:

```sql
SELECT c.customer_id, c.customer_name, top_orders.order_id
FROM customers_demo AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM orders_demo AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 2
) AS top_orders ON TRUE
ORDER BY c.customer_id, top_orders.order_id DESC;
```

Khách có ít nhất hai đơn đóng góp hai hàng; khách Giang vẫn có **một hàng với `order_id = NULL`** vì đây là `LEFT JOIN LATERAL`. Nếu chỉ muốn các đơn thực và loại nhóm rỗng, dùng `JOIN LATERAL` thích hợp hoặc lọc theo nhu cầu, không nhầm hàng được bảo toàn với một đơn thật.

## 15. SQL Server, MySQL, SQLite và Oracle

Ý tưởng `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` được hỗ trợ rộng rãi trong các DBMS hiện đại, nhưng cách viết CTE, lấy Top 1 và điều khiển `NULL` có thể khác.

| DBMS | Hàm cửa sổ | Cách chọn một hàng đầu mỗi nhóm khác | Lưu ý |
|---|---|---|---|
| **PostgreSQL** | `ROW_NUMBER`, `RANK`, `DENSE_RANK` | `DISTINCT ON`, `LATERAL ... LIMIT 1` | `NULLS FIRST/LAST`; chỉ mục và cú pháp mảng khác hệ khác |
| **SQL Server** | `ROW_NUMBER() OVER(...)` | `CROSS APPLY`/`OUTER APPLY` + `TOP (1)` | CTE thường viết `;WITH` nếu trước có lệnh; không dùng `LIMIT` |
| **MySQL 8.0+** | `ROW_NUMBER`/`RANK`/`DENSE_RANK` | CTE/derived table; một số cách nối tương quan theo phiên bản | Không có `DISTINCT ON` PostgreSQL; cú pháp `NULLS LAST` không giống PostgreSQL |
| **SQLite 3.25.0+** | Hàm cửa sổ | CTE/derived table; correlated subquery khi cần | Hỗ trợ window từ 3.25.0; cú pháp và hiệu năng theo phiên bản |
| **Oracle Database** | Hàm cửa sổ phân tích | `ROW_NUMBER` trong inline view/CTE, `FETCH FIRST` trong phạm vi phù hợp | `ROWNUM` không thay thế trực tiếp Top N mỗi nhóm; có quy tắc xử lý `NULL` riêng |

### 15.1. SQL Server: ROW_NUMBER và OUTER APPLY

Viết xếp hạng bằng CTE:

```sql
-- SQL Server
;WITH ranked_orders AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.ordered_at,
        o.status,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM dbo.orders_demo AS o
)
SELECT customer_id, order_id, ordered_at, status
FROM ranked_orders
WHERE rn = 1
ORDER BY customer_id;
```

`;WITH` nhấn mạnh việc kết thúc câu lệnh trước trong một batch SQL Server. `ROW_NUMBER` phải có `ORDER BY` trong cửa sổ; thêm khóa duy nhất để tránh thứ tự đồng hạng không xác định.

SQL Server có cách gần giống `LEFT JOIN LATERAL`:

```sql
-- SQL Server
SELECT
    c.customer_id,
    c.customer_name,
    latest.order_id,
    latest.status
FROM dbo.customers_demo AS c
OUTER APPLY (
    SELECT TOP (1)
        o.order_id,
        o.status
    FROM dbo.orders_demo AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
) AS latest
ORDER BY c.customer_id;
```

`OUTER APPLY` giữ khách không có đơn như `LEFT JOIN LATERAL`; `CROSS APPLY` chỉ giữ khách có hàng con phù hợp. `TOP (1)` được áp dụng **trong truy vấn tương quan của từng khách**, không phải giới hạn toàn bảng.

### 15.2. MySQL 8.0+: CTE và ROW_NUMBER

```sql
-- MySQL 8.0+
WITH ranked_orders AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM orders_demo AS o
)
SELECT customer_id, order_id, ordered_at
FROM ranked_orders
WHERE rn = 1
ORDER BY customer_id;
```

Ý tưởng giống PostgreSQL. Tuy nhiên, không sao chép `DISTINCT ON` hoặc `NULLS LAST` của PostgreSQL vào MySQL. Khi cần bảo đảm `NULL` ở cuối thứ tự giảm dần, có thể dùng:

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY
        (amount IS NULL) ASC,
        amount DESC,
        order_id DESC
) AS rn
```

Biểu thức `(amount IS NULL)` nhận giá trị logic có thể sắp xếp; `FALSE` trước `TRUE` trong cách biểu diễn số tương ứng của MySQL. Khi chuyển sang DBMS khác, dùng `CASE WHEN amount IS NULL THEN 1 ELSE 0 END` để biểu đạt rõ quy tắc.

### 15.3. SQLite: ROW_NUMBER trong CTE

Trên SQLite có hỗ trợ window functions:

```sql
-- SQLite 3.25.0+
WITH ranked_orders AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM orders_demo
)
SELECT customer_id, order_id, ordered_at
FROM ranked_orders
WHERE rn <= 2
ORDER BY customer_id, rn;
```

SQLite không yêu cầu kiểu dữ liệu thời gian hệt PostgreSQL: dữ liệu ngày giờ có thể được lưu theo quy ước văn bản ISO-8601, số Julian hoặc Unix timestamp. Nếu sắp chuỗi thời gian, phải **chuẩn hóa định dạng và múi giờ** để thứ tự từ điển khớp thứ tự thời gian mong muốn. Một chỉ mục vẫn hữu ích tùy kế hoạch thực thi.

### 15.4. Oracle Database: analytic ROW_NUMBER

```sql
-- Oracle
SELECT customer_id, order_id, ordered_at
FROM (
    SELECT
        o.customer_id,
        o.order_id,
        o.ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM orders_demo o
)
WHERE rn = 1
ORDER BY customer_id;
```

Oracle gọi `ROW_NUMBER` là hàm phân tích (*analytic function*), cùng ý tưởng cửa sổ. Lấy `ROWNUM <= 1` ở cấp truy vấn ngoài không tự biến thành “một hàng mỗi khách”; nó thường giới hạn **toàn bộ tập hàng**. Muốn chia nhóm phải dùng `PARTITION BY` hoặc một cấu trúc tương quan tương đương.

### 15.5. QUALIFY trong các hệ có hỗ trợ

Một số hệ quản trị/phân tích như BigQuery, Snowflake hay DuckDB có mệnh đề `QUALIFY` để **lọc theo kết quả hàm cửa sổ** trực tiếp, tránh cần CTE chỉ để lọc `rn`:

```sql
-- Cú pháp minh họa trên hệ hỗ trợ QUALIFY;
-- không dùng nguyên văn trên PostgreSQL.
SELECT
    customer_id,
    order_id,
    ordered_at
FROM orders_demo
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at DESC, order_id DESC
) = 1;
```

`QUALIFY` không có mặt đồng nhất ở mọi DBMS/phiên bản. Vì mục tiêu bài học là kỹ thuật dễ di chuyển, cách **CTE/derived table + `WHERE rn = 1` ở ngoài** vẫn là lựa chọn nền tảng.

## 16. Hiệu năng và thiết kế chỉ mục

Chọn hàng đầu mỗi nhóm thường liên quan **sắp xếp theo khóa nhóm và thứ tự trong nhóm**. Với dữ liệu lớn, chi phí có thể đáng kể.

### 16.1. Chỉ mục phù hợp với PARTITION BY và ORDER BY

Với truy vấn:

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at DESC, order_id DESC
)
```

một chỉ mục hữu ích trên PostgreSQL có thể là:

```sql
CREATE INDEX idx_orders_customer_time_id
ON orders_demo (customer_id, ordered_at DESC, order_id DESC);
```

Khóa chỉ mục bắt đầu bằng `customer_id`, sau đó là thứ tự muốn đọc các đơn của mỗi khách. Tùy kế hoạch và mức chọn lọc, DBMS có thể tận dụng chỉ mục để giảm thao tác sắp xếp hoặc tìm nhanh hàng đầu.

**Không có bảo đảm** mọi truy vấn `ROW_NUMBER` luôn dùng chỉ mục hoặc luôn nhanh hơn khi thêm chỉ mục; chỉ mục cũng làm tăng chi phí ghi và dung lượng. Nên kiểm tra `EXPLAIN` và đo trên dữ liệu đại diện.

### 16.2. Khi chỉ cần một số nhóm nhỏ

Nếu ứng dụng chỉ cần đơn mới nhất cho **mười khách đang xem**, `LATERAL ... LIMIT 1` hoặc `OUTER APPLY TOP (1)` có thể khai thác chỉ mục từng khách. Nếu cần top 1 của **toàn bộ hàng triệu khách**, kế hoạch tốt nhất có thể khác. Không tối ưu theo cảm tính chỉ vì hai câu lệnh có độ dài khác nhau.

### 16.3. Hạn chế các cột không cần thiết

Trong CTE xếp hạng, chỉ cần chọn những cột cần lọc và hiển thị; `SELECT *` trên bảng rộng có thể làm tăng lượng dữ liệu phải vận chuyển qua các bước xử lý. Nếu cần số liệu sau khi chọn hàng, có thể tách rõ các bước theo grain.

### 16.4. Kết quả ổn định và đọc đồng thời

Ngay cả khi `ORDER BY` có khóa duy nhất, kết quả nhiều câu truy vấn liên tiếp có thể thay đổi do **dữ liệu mới, sửa timestamp hoặc xóa bản ghi** trong lúc chạy. Khi xuất báo cáo cần một ảnh chụp nhất quán, cần dùng transaction và mức cô lập phù hợp với DBMS và yêu cầu ứng dụng.

Đừng dùng `ROW_NUMBER` để cấp **ID vĩnh viễn** cho bản ghi: số thứ tự cửa sổ phụ thuộc tập dữ liệu, điều kiện lọc và thứ tự, nên sẽ đổi khi dữ liệu biến động. Dùng khóa chính thực sự để định danh.

## 17. Các lỗi thường gặp

### Lỗi 1 — Dùng LIMIT 1 cho toàn bảng

`ORDER BY ordered_at DESC LIMIT 1` chỉ lấy một đơn toàn bộ bảng. Muốn một đơn mỗi khách, phải chia nhóm bằng `PARTITION BY customer_id`, hoặc dùng truy vấn tương quan cho từng khách.

### Lỗi 2 — Quên PARTITION BY

`ROW_NUMBER() OVER (ORDER BY ordered_at DESC)` đánh số trên **một cửa sổ toàn bộ tập**, không bắt đầu lại ở mỗi khách. Khi lọc `rn = 1` chỉ còn một hàng toàn bảng.

### Lỗi 3 — Chỉ ORDER BY thời gian khi có các thời điểm trùng

`ROW_NUMBER` vẫn đánh số các hàng đồng thời điểm nhưng **không bảo đảm bản ghi nào nhận số 1**. Cần thêm khóa phụ duy nhất theo nhóm, chẳng hạn `order_id DESC`.

### Lỗi 4 — Thêm khóa duy nhất vào RANK rồi mất đồng hạng

Nếu muốn **mọi đơn cùng thời điểm mới nhất**, dùng `RANK ORDER BY ordered_at DESC`. Khi thêm `order_id DESC` vào cửa sổ `RANK`, các hàng có cùng thời điểm không còn đồng hạng, làm kết quả `RANK = 1` chỉ còn một hàng mỗi khách.

### Lỗi 5 — Đặt ROW_NUMBER trong WHERE cùng cấp

`WHERE ROW_NUMBER() OVER (...) = 1` không hợp lệ trong PostgreSQL và nhiều DBMS. Hãy tính `rn` trong CTE/derived table, rồi lọc ở truy vấn ngoài, hoặc dùng `QUALIFY` trên DBMS có hỗ trợ.

### Lỗi 6 — Nhầm ORDER BY của cửa sổ với ORDER BY kết quả

`ORDER BY` trong `OVER(...)` xác định thứ hạng trong nhóm, không bảo đảm thứ tự hiển thị cuối. Thêm `ORDER BY` cuối nếu cần kết quả ổn định.

### Lỗi 7 — Lọc trạng thái ở sai giai đoạn

“Đơn PAID mới nhất” yêu cầu lọc `PAID` **trước** khi xếp hạng; “đơn mới nhất nếu nó là PAID” yêu cầu xếp hạng **trước**, rồi kiểm tra trạng thái. Trên dữ liệu mẫu, khách Chi tạo phản ví dụ.

### Lỗi 8 — Dùng WHERE rn = 1 sau LEFT JOIN làm mất nhóm rỗng

Hàng khách không có đơn có `rn = NULL`; `WHERE rn = 1` sẽ loại hàng đó. Nếu muốn giữ mọi khách, đưa `rn = 1` vào điều kiện `ON` hoặc chuẩn bị trước một bảng top 1 rồi `LEFT JOIN`.

### Lỗi 9 — Giả định RANK <= N luôn trả tối đa N hàng

Các hàng đồng hạng cùng số `RANK`, nên `RANK <= 2` có thể trả **ba hoặc nhiều hơn hai** hàng của một nhóm. Chọn `ROW_NUMBER <= N` nếu yêu cầu số hàng tối đa N; chọn `RANK`/`DENSE_RANK` nếu muốn giữ đồng hạng theo quy tắc được nêu rõ.

### Lỗi 10 — Hiểu MAX(timestamp) tự xác định một hàng duy nhất

`MAX(ordered_at)` chỉ cho thời điểm lớn nhất. Nhiều đơn có thể cùng thời điểm đó; nối ngược lại có thể trả nhiều hàng. `MAX(order_id)` cũng không nhất thiết cùng hàng với `MAX(ordered_at)` nếu xét trên dữ liệu tổng quát.

### Lỗi 11 — Để NULL đứng đầu khi muốn giá trị lớn nhất

Trên PostgreSQL, `ORDER BY amount DESC` có mặc định `NULL` ở đầu. Cần `NULLS LAST` hoặc biểu thức `CASE` rõ ràng, hoặc lọc `amount IS NOT NULL` trước khi xếp hạng.

### Lỗi 12 — Nghĩ DISTINCT tự chọn đúng đơn mới nhất

`SELECT DISTINCT customer_id, order_id, ordered_at` chỉ loại các hàng trùng trên toàn bộ cột, không chọn top 1 theo khách. `DISTINCT ON` của PostgreSQL là một cú pháp khác, đòi hỏi `ORDER BY` đúng quy tắc.

### Lỗi 13 — Coi ROW_NUMBER là ID lưu trữ ổn định

Số thứ tự xếp hạng thay đổi khi dữ liệu được thêm/sửa/xóa; nó phù hợp để **chọn hàng trong kết quả truy vấn**, không làm khóa chính thay thế `order_id`.

### Lỗi 14 — Chọn “hàng đầu” mà không xác định tiêu chí nghiệp vụ

“Đơn tốt nhất”, “bản ghi mới nhất” hoặc “sản phẩm đứng đầu” cần định nghĩa **độ ưu tiên** và **cách xử lý đồng hạng**. SQL không thể suy ra rằng trạng thái `PAID` hay số tiền lớn hơn quan trọng hơn thời điểm nếu người viết không nói rõ.

## 18. Bài tập thực hành

Sử dụng đúng `customers_demo` và `orders_demo` ở mục 2. Mỗi bài có mục tiêu và kết quả mong đợi để tự kiểm tra bằng SQL.

### Bài 1 — Đơn mới nhất mỗi khách

Viết truy vấn trả **tối đa một đơn mỗi khách có đơn**, ưu tiên thời điểm mới nhất và dùng `order_id DESC` phân định nếu trùng:

```sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM orders_demo
)
SELECT customer_id, order_id
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
```

**Đáp án:** `(1,103)`, `(2,106)`, `(3,109)`, `(4,111)`, `(5,114)`.

### Bài 2 — Hai đơn mới nhất mỗi khách

Đổi điều kiện `rn = 1` thành `rn <= 2`. Dự đoán số hàng và các ID.

**Đáp án:** 10 hàng. Theo khách lần lượt: **103,102**; **106,105**; **109,107**; **111,110**; **114,113**.

### Bài 3 — Mọi đơn cùng thời điểm mới nhất

Viết `RANK() OVER (PARTITION BY customer_id ORDER BY ordered_at DESC)` và lọc `time_rank = 1`.

**Đáp án:** mỗi khách từ 1 đến 5 có hai đơn đồng thời điểm mới nhất, nên kết quả là **10 hàng**. Giải thích vì sao không nên đưa `order_id` vào `ORDER BY` của `RANK` trong câu hỏi này.

### Bài 4 — Chỉ đơn PAID mới nhất

Xếp hạng **sau khi lọc `status = 'PAID'`**. Dự đoán đơn của khách Chi.

**Đáp án:** `1→103, 2→106, 3→107, 4→111, 5→114`. Chi nhận **107** vì 109 có trạng thái `CANCELLED`.

### Bài 5 — Đơn mới nhất nếu nó PAID

Xếp hạng **mọi đơn** rồi lọc `rn = 1 AND status = 'PAID'` ở ngoài.

**Đáp án:** `1→103, 2→106, 4→111, 5→114`; khách Chi không xuất hiện do đơn mới nhất 109 là `CANCELLED`. So sánh với bài 4.

### Bài 6 — Bao gồm khách chưa có đơn

Từ `customers_demo`, `LEFT JOIN` CTE đã có `ROW_NUMBER` để lấy một đơn mới nhất cho **mọi khách**. Đặt `rn = 1` trong `ON`.

**Đáp án:** **6 hàng**; khách Giang có `latest_order_id = NULL`, không được xem là có một đơn thật.

### Bài 7 — Đơn có số tiền lớn nhất mỗi khách

Xếp `amount DESC NULLS LAST, order_id DESC` rồi lấy `rn = 1`.

**Đáp án:** `1→103` (150.000), `2→104` (200.000), `3→108` (110.000), `4→111` (70.000), `5→114` (40.000). Nếu bỏ `NULLS LAST` trên PostgreSQL, khách Em có nguy cơ chọn hàng số tiền `NULL`.

### Bài 8 — So sánh ROW_NUMBER, RANK, DENSE_RANK

Với khách Em có tiền `40.000, 40.000, NULL`, dùng ba hàm theo mẫu ở mục 7.1.

**Đáp án:** `ROW_NUMBER` theo tiền và ID cho `114→1, 113→2, 112→3`; `RANK` theo tiền cho `114→1, 113→1, 112→3`; `DENSE_RANK` cho `114→1, 113→1, 112→2`.

### Bài 9 — Ưu tiên trạng thái rồi đến thời gian

Viết `ROW_NUMBER` với:

```sql
ORDER BY
    CASE status
        WHEN 'PAID' THEN 1
        WHEN 'NEW' THEN 2
        WHEN 'CANCELLED' THEN 3
        ELSE 4
    END,
    ordered_at DESC,
    order_id DESC
```

**Đáp án:** khách Chi nhận **107 PAID** thay vì **109 CANCELLED**. Giải thích vì sao danh sách biểu thức `ORDER BY` thể hiện **thứ tự ưu tiên nghiệp vụ**.

### Bài 10 — PostgreSQL DISTINCT ON

Viết lại bài 1 bằng:

```sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM orders_demo
ORDER BY customer_id, ordered_at DESC, order_id DESC;
```

**Đáp án:** chọn cùng các ID **103, 106, 109, 111, 114**. Phân biệt `DISTINCT ON` với `SELECT DISTINCT` thông thường và ghi nhận đây là cú pháp PostgreSQL.

### Bài 11 — Đơn mới nhất bằng LATERAL

Viết `LEFT JOIN LATERAL` từ `customers_demo` tới truy vấn con `orders_demo` của từng khách, sắp theo `ordered_at DESC, order_id DESC` và `LIMIT 1`.

**Đáp án:** 6 hàng gồm 5 khách có đơn như bài 1 và Giang với thông tin đơn `NULL`. Nếu đổi thành `JOIN LATERAL`, khách Giang sẽ biến mất.

### Bài 12 — Top 2 tiền cao nhất, giữ mọi đồng giá

So sánh:

```sql
-- Một phần của CTE:
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY amount DESC NULLS LAST, order_id DESC
) AS row_no,

RANK() OVER (
    PARTITION BY customer_id
    ORDER BY amount DESC NULLS LAST
) AS sales_rank
```

Với khách Binh có `200.000, 50.000, 50.000`, `row_no <= 2` giữ **104 và 106**, còn `sales_rank <= 2` giữ **104, 105 và 106**.

### Bài 13 — Mỗi tháng của từng khách

Yêu cầu: lấy **đơn mới nhất của mỗi khách trong từng tháng**, không gộp tháng 1 và tháng 2. Với PostgreSQL:

```sql
WITH ranked_months AS (
    SELECT
        o.customer_id,
        DATE_TRUNC('month', o.ordered_at)::DATE AS month_start,
        o.order_id,
        ROW_NUMBER() OVER (
            PARTITION BY
                o.customer_id,
                DATE_TRUNC('month', o.ordered_at)::DATE
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM orders_demo AS o
)
SELECT customer_id, month_start, order_id
FROM ranked_months
WHERE rn = 1
ORDER BY customer_id, month_start;
```

**Đáp án:** khách Binh có **hai hàng**: tháng 1 → đơn **104**, tháng 2 → đơn **106**. Các khách còn lại có đơn trong đúng một tháng từ bộ dữ liệu mẫu, nên có một hàng mỗi khách có đơn. Nếu chỉ `PARTITION BY customer_id`, khách Binh sẽ mất hàng tháng 1 vì hai tháng bị xếp chung.

### Bài 14 — Tìm lỗi ổn định kết quả

Một truy vấn viết:

```sql
SELECT customer_id, order_id,
       ROW_NUMBER() OVER (
           PARTITION BY customer_id
           ORDER BY ordered_at DESC
       ) AS rn
FROM orders_demo;
```

Hãy giải thích hai điểm:

1. Vì sao không biết chắc đơn **102** hay **103** của An nhận `rn = 1`?
2. Vì sao thứ tự các hàng **cuối cùng** cũng chưa được bảo đảm?

**Đáp án:** `ordered_at` không phân định được các đơn trùng thời điểm, và truy vấn không có `ORDER BY` cuối. Bổ sung `order_id DESC` trong `OVER` để xác định thứ hạng, thêm `ORDER BY customer_id, rn` ngoài cùng để hiển thị ổn định.

## 19. Bảng ghi nhớ nhanh

| Mục tiêu | Công cụ | Lưu ý |
|---|---|---|
| Một hàng đầu mỗi nhóm | `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` rồi `WHERE rn = 1` | Khóa phụ duy nhất để phân định |
| N hàng đầu mỗi nhóm | `ROW_NUMBER` rồi `WHERE rn <= N` | Tối đa N hàng mỗi nhóm |
| Mọi hàng đồng hạng ở vị trí cao nhất | `RANK() ... = 1` | Không đưa khóa duy nhất vào tiêu chí hạng nếu cần giữ đồng hạng |
| N thứ hạng đầu theo cách có khoảng nhảy | `RANK() <= N` | Có thể hơn N hàng |
| N mức giá trị/thứ hạng liên tiếp | `DENSE_RANK() <= N` | Có thể hơn N hàng |
| Chỉ đơn PAID mới nhất | Lọc `PAID` **trước** cửa sổ | Không giống lọc sau khi chọn mới nhất |
| Mọi khách, cả người chưa có đơn | Xếp hạng đơn rồi `LEFT JOIN` khách, `rn = 1` trong `ON` | Không dùng `WHERE rn = 1` sau left join |
| Một hàng mỗi nhóm trong PostgreSQL | `DISTINCT ON (key) ... ORDER BY key, priority, unique_id` | Cú pháp đặc thù PostgreSQL |
| Top 1 tương quan trong PostgreSQL | `LEFT JOIN LATERAL (... ORDER BY ... LIMIT 1)` | Hữu ích khi có chỉ mục phù hợp |
| Top 1 tương quan trong SQL Server | `OUTER APPLY (SELECT TOP (1) ... ORDER BY ...)` | Giữ cả nhóm không có hàng |
| Xếp `NULL` cuối khi lấy giá trị lớn | `NULLS LAST` hoặc `CASE WHEN col IS NULL ...` | Cú pháp/mặc định phụ thuộc DBMS |
| Xem giá trị của hàng đầu nhưng giữ tất cả hàng | `FIRST_VALUE(...) OVER (...)` | Không làm giảm số hàng |
| Chỉ lấy top 1 của toàn bảng | `ORDER BY ... LIMIT 1`/`TOP (1)` | Không có nghĩa top 1 mỗi nhóm |

## Kết luận

Để **lấy các hàng đầu mỗi nhóm với thứ tự xác định**, hãy bắt đầu bằng việc xác định **khóa nhóm**, **tiêu chí ưu tiên** và **quy tắc đồng hạng**:

- `PARTITION BY` chia tập hàng thành những nhóm độc lập.
- `ORDER BY` trong cửa sổ quyết định hàng nào xếp trước **trong từng nhóm**; bổ sung khóa phụ **duy nhất** nếu cần một hàng được chọn ổn định.
- `ROW_NUMBER` và `WHERE rn = 1`/`rn <= N` chọn **tối đa một hoặc N hàng mỗi nhóm**.
- `RANK` và `DENSE_RANK` dùng khi muốn giữ **những hàng cùng thứ hạng**, với quy tắc đếm hạng khác nhau.
- CTE hoặc derived table giúp lọc theo số thứ tự ở **cấp truy vấn ngoài**; `ORDER BY` cuối vẫn cần thiết nếu muốn thứ tự hiển thị ổn định.
- `LEFT JOIN` từ bảng danh mục/khách giúp giữ những nhóm **không có bản ghi liên quan**.
- Lọc **trước** hay **sau** khi xếp hạng thay đổi ý nghĩa nghiệp vụ; việc xử lý `NULL` cũng phải được định nghĩa rõ.

Phương pháp `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` là kỹ thuật nền tảng và tương đối dễ chuyển phương ngữ. PostgreSQL còn có `DISTINCT ON` và `LATERAL`; SQL Server có `OUTER APPLY`; các hệ phân tích có thể hỗ trợ `QUALIFY`. Dù dùng cách nào, nguyên tắc vẫn là **mô tả rõ “hàng đầu” theo thứ tự nào, đồng hạng thì giữ hay phân định, và mỗi nhóm cần có bao nhiêu hàng**. Khi ba điều đó được xác định tường minh, kết quả sẽ dễ kiểm chứng và ít phụ thuộc vào sự tình cờ của kế hoạch thực thi.
