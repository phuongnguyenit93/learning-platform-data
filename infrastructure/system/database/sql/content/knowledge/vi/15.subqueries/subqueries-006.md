# Bảng dẫn xuất trong FROM và tên cột đầu ra

Trong **Database SQL**, một câu `SELECT` không nhất thiết chỉ đọc trực tiếp từ bảng vật lý. Ta có thể viết **một truy vấn con bên trong mệnh đề `FROM`**, rồi sử dụng tập kết quả đó như một bảng tạm về mặt logic trong truy vấn bên ngoài. Kết quả này thường được gọi là **bảng dẫn xuất (derived table)**, **bảng kết quả con** hoặc, trong một số tài liệu, *inline view*.

Bảng dẫn xuất đặc biệt hữu ích khi muốn làm việc theo hai giai đoạn: trước tiên lọc, tính toán hoặc tổng hợp dữ liệu; sau đó JOIN, lọc hoặc sắp xếp kết quả đã được đặt tên rõ ràng. Hai chủ đề quan trọng nhất của kỹ thuật này là **đặt bí danh cho bảng dẫn xuất** và **đặt tên các cột đầu ra để truy vấn bên ngoài có thể tham chiếu chính xác**.

Sau bài này, bạn có thể:

- Viết truy vấn con trong `FROM` và truy cập các cột của nó qua bí danh.
- Phân biệt **bí danh bảng** với **bí danh cột** và phạm vi hiển thị của từng tên.
- Đặt tên ổn định cho kết quả của phép tính, tổng hợp, `CASE` và hàm cửa sổ.
- Dùng bảng dẫn xuất để tổng hợp trước khi JOIN, lọc theo kết quả tính toán, chọn dòng mới nhất và tái sử dụng kết quả trung gian.
- Nhận biết giới hạn liên quan `ORDER BY`, `LIMIT`, `NULL`, truy vấn tương quan, `LATERAL` và khác biệt cú pháp giữa các DBMS.

## 1. Bảng dẫn xuất là gì?

Xét truy vấn:

```sql
SELECT
    order_id,
    quantity * unit_price AS line_amount
FROM order_items;
```

Truy vấn này trả về một tập dòng có hai cột tên `order_id` và `line_amount`. Nếu đưa toàn bộ `SELECT` đó vào `FROM` của câu SQL khác, nó trở thành **nguồn dữ liệu** cho truy vấn bên ngoài:

```sql
SELECT
    d.order_id,
    d.line_amount
FROM (
    SELECT
        order_id,
        quantity * unit_price AS line_amount
    FROM order_items
) AS d;
```

Đọc từ trong ra ngoài:

1. **Truy vấn con:** lấy `order_id` và tính `line_amount` bằng `quantity * unit_price`.
2. **Cặp dấu ngoặc `(...)`:** giới hạn phạm vi của truy vấn con được dùng như nguồn trong `FROM`.
3. **`AS d`:** đặt bí danh bảng dẫn xuất là `d`.
4. **Truy vấn ngoài:** dùng `d.order_id` và `d.line_amount` như các cột của một nguồn dữ liệu có tên `d`.

Sơ đồ:

```text
Bảng gốc order_items
    order_id | quantity | unit_price
                |
                | SELECT order_id,
                |        quantity * unit_price AS line_amount
                v
Bảng dẫn xuất d
    order_id | line_amount
                |
                | SELECT d.order_id, d.line_amount
                v
Kết quả cuối cùng
    order_id | line_amount
```

**Điểm cốt lõi:** bảng dẫn xuất là kết quả logic của một truy vấn, **không phải bảng vật lý được tạo bằng `CREATE TABLE`**. Bản thân câu SQL trên không tạo bảng `d` lâu dài, không tự tạo index mới cho `d` và không làm thay đổi dữ liệu gốc.

Một DBMS có thể thực thi bảng dẫn xuất bằng nhiều cách (hợp nhất vào truy vấn ngoài, materialize một phần hoặc dùng kế hoạch khác). Việc viết truy vấn con trong `FROM` **không tự bảo đảm** database sẽ lưu sẵn toàn bộ kết quả con trong một bảng tạm vật lý.

## 2. Cú pháp cơ bản và hai loại bí danh

Mẫu thường gặp:

```sql
SELECT
    alias_bang.cot_dau_ra
FROM (
    SELECT
        bieu_thuc AS cot_dau_ra
    FROM bang_goc
) AS alias_bang;
```

Có **hai vị trí đặt tên khác nhau**:

| Vị trí | Ví dụ | Vai trò |
| --- | --- | --- |
| Sau biểu thức trong `SELECT` bên trong | `quantity * unit_price AS line_amount` | Tên **cột đầu ra** của bảng dẫn xuất |
| Sau dấu ngoặc đóng của truy vấn con | `) AS d` | Tên **nguồn dữ liệu/bí danh bảng** để truy vấn ngoài tham chiếu |
| Trong `SELECT` bên ngoài | `d.line_amount AS amount_to_show` | Tên **cột của kết quả cuối cùng**, có thể khác tên bên trong |

Ví dụ:

```sql
SELECT
    calc.line_amount AS amount_to_show
FROM (
    SELECT quantity * unit_price AS line_amount
    FROM order_items
) AS calc;
```

Ở đây:

- `calc` là bí danh **bảng dẫn xuất**.
- `line_amount` là tên **cột do truy vấn con tạo ra**.
- `amount_to_show` là tên cột **đưa ra cho người gọi truy vấn ngoài**.

Đổi `amount_to_show` ở `SELECT` ngoài không tự đổi tên `line_amount` bên trong. Tương tự, đổi bí danh bảng `calc` thành `d` không đổi tên cột `line_amount`.

### Có thể bỏ AS không?

Nhiều DBMS chấp nhận:

```sql
SELECT d.line_amount
FROM (
    SELECT quantity * unit_price AS line_amount
    FROM order_items
) d;
```

Trong PostgreSQL và nhiều dialect khác, `AS` trước bí danh bảng là tùy chọn. Tuy nhiên, khác biệt theo DBMS vẫn tồn tại: **Oracle Database** ở nhiều phiên bản truyền thống không dùng `AS` trước bí danh bảng trong `FROM`; vì vậy dạng `) d` thường thuận tiện hơn khi viết inline view trên Oracle.

Đừng nhầm điều đó với `AS` dùng để đặt bí danh cột trong `SELECT` — đây là vị trí khác. Khi viết SQL cho một hệ cụ thể, hãy theo đúng quy tắc parser của hệ đó.

## 3. Vì sao truy vấn con trong FROM cần tên bảng?

Một câu `SELECT` trong `FROM` tạo ra một nguồn dữ liệu. Nếu cùng truy vấn còn có các bảng khác, DBMS cần biết cách phân biệt nguồn và truy cập cột:

```sql
SELECT
    o.order_id,
    o.customer_id,
    totals.order_total
FROM orders AS o
JOIN (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM order_items
    GROUP BY order_id
) AS totals
    ON totals.order_id = o.order_id;
```

Trong câu này:

- `o` đại diện bảng `orders`.
- `totals` đại diện kết quả đã tổng hợp từ `order_items`.
- `totals.order_id` là khóa JOIN **đầu ra của truy vấn con**, không phải tham chiếu trực tiếp tới `order_items` ở phạm vi ngoài.
- `totals.order_total` là cột được tạo bằng `SUM(...) AS order_total`.

**Nên luôn đặt một bí danh rõ nghĩa cho bảng dẫn xuất**, dù vài DBMS/phiên bản có thể cho phép bỏ tên.

Về mặt yêu cầu parser:

- **MySQL/MariaDB:** derived table trong `FROM` cần bí danh.
- **SQL Server:** derived table trong `FROM` cần correlation name (bí danh).
- **PostgreSQL:** trước phiên bản 16 cần bí danh; PostgreSQL 16 trở lên cho phép bỏ bí danh cho subquery trong `FROM` trong những trường hợp hỗ trợ.
- **SQLite/Oracle:** có các ngữ cảnh cho phép nguồn con không cần alias, nhưng nên viết alias để dễ đọc, thuận lợi cho JOIN và chuyển hệ.

Cú pháp và yêu cầu chính xác có thể phụ thuộc phiên bản; **không dựa vào việc một DBMS cho phép lược bí danh để bỏ thói quen đặt tên rõ ràng**.

## 4. Tên cột đầu ra quyết định truy vấn ngoài nhìn thấy gì

Bảng dẫn xuất **chỉ công bố những cột được chọn bởi `SELECT` bên trong**. Các cột của bảng nguồn không tự xuất hiện ở phạm vi ngoài.

Ví dụ:

```sql
SELECT
    d.order_id,
    d.line_amount
FROM (
    SELECT
        order_id,
        quantity * unit_price AS line_amount
    FROM order_items
) AS d;
```

Truy vấn ngoài truy cập được `d.order_id` và `d.line_amount`. Nó **không truy cập được `d.quantity`** vì `quantity` không nằm trong danh sách `SELECT` của bảng dẫn xuất:

```sql
-- SAI nếu derived table không SELECT quantity:
SELECT d.quantity
FROM (
    SELECT
        order_id,
        quantity * unit_price AS line_amount
    FROM order_items
) AS d;
```

Muốn truy cập `quantity` ở ngoài, thêm nó vào truy vấn bên trong:

```sql
SELECT d.order_id, d.quantity, d.line_amount
FROM (
    SELECT
        order_id,
        quantity,
        quantity * unit_price AS line_amount
    FROM order_items
) AS d;
```

### Cột đã đổi tên bên trong không còn tên cũ ở phạm vi ngoài

```sql
SELECT d.order_total
FROM (
    SELECT
        SUM(quantity * unit_price) AS order_total
    FROM order_items
) AS d;
```

Tên công bố là `order_total`. Không thể gọi `d.SUM` hay `d.quantity * d.unit_price` chỉ vì biểu thức bên trong dùng các cột đó. Truy vấn ngoài làm việc với **kết quả biểu thức đã chọn**, không được “nhìn xuyên” bảng dẫn xuất để tự lấy các nguồn chưa được xuất.

### Đặt tên cho các biểu thức không phải cột

Khi `SELECT` một phép toán mà không có alias:

```sql
SELECT quantity * unit_price
FROM order_items;
```

DBMS phải gán hoặc trình bày một tên nào đó cho cột kết quả; tên tự sinh có thể không thuận tiện, không giống nhau giữa DBMS và đôi khi không hợp lệ khi truy cập qua bảng dẫn xuất. Vì vậy, trong bảng dẫn xuất nên chủ động đặt tên:

```sql
SELECT d.line_amount
FROM (
    SELECT quantity * unit_price AS line_amount
    FROM order_items
) AS d;
```

Quy tắc này đặc biệt quan trọng với `COUNT(*)`, `SUM(...)`, `CASE`, `COALESCE(...)`, `ROW_NUMBER()` và các biểu thức chuỗi/ngày giờ.

## 5. Bí danh bảng và phạm vi tên (scope)

Câu SQL lồng nhau có **nhiều phạm vi tên**. Một bí danh khai báo trong truy vấn con dùng để phân biệt nguồn **bên trong**; tên bảng dẫn xuất được khai báo sau dấu ngoặc được dùng **ở phạm vi ngoài**.

Ví dụ:

```sql
SELECT
    t.order_id,
    t.order_total
FROM (
    SELECT
        i.order_id,
        SUM(i.quantity * i.unit_price) AS order_total
    FROM order_items AS i
    GROUP BY i.order_id
) AS t;
```

Các phạm vi:

| Tên | Có thể dùng ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `i` | Trong `SELECT` con, `GROUP BY` con và các điều kiện của truy vấn con | Bí danh của bảng gốc `order_items` |
| `t` | Trong `SELECT` ngoài, `WHERE` ngoài, `JOIN` ngoài... | Bí danh của kết quả truy vấn con |
| `t.order_total` | Ở truy vấn ngoài | Cột đã được truy vấn con công bố |
| `i.unit_price` | Không dùng ở truy vấn ngoài theo cách tham chiếu trực tiếp ở ví dụ | `i` nằm trong phạm vi bên trong |

Câu sau **không hợp lệ** nếu `i` chỉ được định nghĩa trong truy vấn con:

```sql
-- SAI: alias i không tồn tại trong phạm vi SELECT ngoài.
SELECT i.unit_price
FROM (
    SELECT i.order_id, SUM(i.quantity * i.unit_price) AS order_total
    FROM order_items AS i
    GROUP BY i.order_id
) AS t;
```

Cần lựa chọn một trong hai cách: **xuất cột cần thiết ở truy vấn con** nếu có ý nghĩa trong kết quả đã nhóm, hoặc **JOIN lại bảng nguồn ở truy vấn ngoài** nếu yêu cầu là xem dữ liệu chi tiết. Không thể vừa tổng hợp theo đơn hàng vừa tự lấy một `unit_price` bất kỳ nếu một đơn có nhiều dòng hàng và chưa định nghĩa cách chọn.

### Alias trong SELECT không phải luôn dùng được ở WHERE cùng cấp

Ví dụ nhiều DBMS không cho viết:

```sql
-- Không di động và thường lỗi: alias line_amount chưa có phạm vi
-- để được WHERE ở cùng cấp truy vấn sử dụng.
SELECT quantity * unit_price AS line_amount
FROM order_items
WHERE line_amount > 100;
```

Ta có thể dùng bảng dẫn xuất để biến alias thành cột **đã được công bố trước khi WHERE của truy vấn ngoài được xét về mặt logic**:

```sql
SELECT d.order_id, d.line_amount
FROM (
    SELECT
        order_id,
        quantity * unit_price AS line_amount
    FROM order_items
) AS d
WHERE d.line_amount > 100;
```

Đây là một trường hợp điển hình khiến bảng dẫn xuất dễ đọc: **tính ở trong, lọc theo tên kết quả ở ngoài**.

## 6. Tên cột trùng nhau và lỗi “ambiguous column”

Một bảng dẫn xuất có thể JOIN với bảng khác mà cả hai đều có cột cùng tên. Nếu viết `SELECT order_id` không ghi nguồn, DBMS có thể báo tên cột **không rõ ràng**:

```sql
-- Dễ lỗi ambiguous: cả o và t đều có order_id.
SELECT order_id, order_total
FROM orders AS o
JOIN (
    SELECT order_id, SUM(quantity * unit_price) AS order_total
    FROM order_items
    GROUP BY order_id
) AS t ON o.order_id = t.order_id;
```

Viết rõ:

```sql
SELECT
    o.order_id,
    t.order_total
FROM orders AS o
JOIN (
    SELECT order_id, SUM(quantity * unit_price) AS order_total
    FROM order_items
    GROUP BY order_id
) AS t ON o.order_id = t.order_id;
```

### Trùng tên ngay trong danh sách cột của bảng dẫn xuất

Giả sử truy vấn con xuất hai cột cùng tên:

```sql
SELECT
    c.customer_id AS id,
    o.order_id AS id
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.customer_id;
```

Khi dùng trực tiếp, một số client có thể hiển thị hai cột đều tên `id`. Nhưng đưa làm **derived table** và tham chiếu `d.id` sẽ mơ hồ; nhiều DBMS từ chối nguồn con có cột đầu ra trùng tên, hoặc hành vi phụ thuộc dialect.

Nên đặt tên **khác nhau và mô tả đúng ý nghĩa**:

```sql
SELECT
    d.customer_id,
    d.order_id
FROM (
    SELECT
        c.customer_id AS customer_id,
        o.order_id AS order_id
    FROM customers AS c
    JOIN orders AS o ON o.customer_id = c.customer_id
) AS d;
```

Trong thực tế, đừng dùng `SELECT *` để xây dựng “giao diện” bảng dẫn xuất lâu dài nếu bảng nguồn có thể được thêm cột trùng tên về sau.

## 7. Hai cách đặt tên cột đầu ra

### Cách 1 — Đặt AS ngay trong SELECT con

Đây là cách dễ đọc và di động nhất:

```sql
SELECT d.order_id, d.order_total
FROM (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM order_items
    GROUP BY order_id
) AS d;
```

Tên `order_total` nằm cạnh biểu thức tạo ra nó; người đọc biết ngay giá trị cột đến từ đâu.

### Cách 2 — Danh sách alias cột sau bí danh bảng

Một số DBMS hỗ trợ đặt tên theo **vị trí** ngay sau tên bảng dẫn xuất. Ví dụ **PostgreSQL**:

```sql
SELECT
    d.item_id,
    d.line_total
FROM (
    SELECT
        item_id,
        quantity * unit_price
    FROM order_items
) AS d(item_id, line_total);
```

Ở đây:

- Cột đầu tiên của `SELECT` con được công bố là `item_id`.
- Cột thứ hai được công bố là `line_total`.
- Truy vấn ngoài dùng `d.item_id` và `d.line_total`.

**Thứ tự trong danh sách alias là quan trọng**. Nếu viết `AS d(line_total, item_id)`, tên được gán **theo vị trí**, không theo nội dung hay kiểu dữ liệu; khi đó `d.line_total` chỉ cột thứ nhất, `d.item_id` chỉ cột thứ hai — sai ý nghĩa nghiệp vụ.

SQL Server cũng hỗ trợ danh sách tên cột cho derived table trong những cú pháp thích hợp. MySQL 8.0.14 trở lên có hỗ trợ danh sách tên cột cho derived table theo cú pháp của hệ. Nhưng **không mặc nhiên dùng cú pháp này trên SQLite, Oracle hoặc mọi phiên bản MariaDB**. Với SQL cần dễ chuyển DBMS, đặt alias **trực tiếp trong `SELECT` con** là lựa chọn dễ kiểm soát hơn.

### Nếu đặt tên cột cả trong lẫn ngoài?

Giả sử PostgreSQL:

```sql
SELECT d.new_name
FROM (
    SELECT quantity * unit_price AS old_name
    FROM order_items
) AS d(new_name);
```

Tên công bố ở mức bảng dẫn xuất là `new_name`; tên `old_name` trong SELECT con bị thay bằng danh sách alias cột áp dụng tại ranh giới bảng dẫn xuất. Khi có nhiều tầng lồng nhau, việc đổi tên quá nhiều lần có thể khiến SQL khó hiểu. Ưu tiên một quy ước đặt tên nhất quán và tránh đổi tên không cần thiết.

## 8. Thực hành PostgreSQL: chuẩn bị dữ liệu đầy đủ

Phần thực hành sử dụng **PostgreSQL** trong database riêng để học. Các bảng dùng tiền tố `sql194_` nhằm tránh nhầm với bảng nghiệp vụ. Chỉ chạy lệnh tạo/xóa khi các tên đó chưa được dùng trong database thực.

### 8.1. Tạo ba bảng

```sql
CREATE TABLE sql194_customers (
    customer_id   INTEGER PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
);

CREATE TABLE sql194_orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES sql194_customers(customer_id),
    status      VARCHAR(20) NOT NULL,
    ordered_at  TIMESTAMP NOT NULL
);

CREATE TABLE sql194_order_items (
    item_id    INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL
        REFERENCES sql194_orders(order_id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0)
);
```

Quan hệ:

```text
sql194_customers                  sql194_orders
customer_id (PK)  1 ──────── N   customer_id (FK)
                                  order_id (PK)
                                      |
                                      | 1
                                      |
                                      | N
                                  sql194_order_items
                                  item_id (PK)
                                  order_id (FK)
                                  quantity, unit_price
```

### 8.2. Chèn dữ liệu mẫu

```sql
INSERT INTO sql194_customers (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi'),
    (4, 'Dũng');

INSERT INTO sql194_orders
    (order_id, customer_id, status, ordered_at)
VALUES
    (101, 1, 'PAID',      TIMESTAMP '2026-03-01 09:00:00'),
    (102, 1, 'PENDING',   TIMESTAMP '2026-03-02 10:00:00'),
    (103, 2, 'PAID',      TIMESTAMP '2026-03-03 11:00:00'),
    (104, 3, 'PAID',      TIMESTAMP '2026-03-04 12:00:00'),
    (105, 3, 'CANCELLED', TIMESTAMP '2026-03-05 13:00:00');

INSERT INTO sql194_order_items
    (item_id, order_id, quantity, unit_price)
VALUES
    (1001, 101, 2, 100.00),
    (1002, 101, 1,  50.00),
    (1003, 102, 1,  80.00),
    (1004, 103, 3,  40.00),
    (1005, 104, 2,  70.00),
    (1006, 105, 1,  30.00);
```

Kiểm tra dữ liệu cơ bản:

```sql
SELECT COUNT(*) AS customer_rows FROM sql194_customers;
SELECT COUNT(*) AS order_rows FROM sql194_orders;
SELECT COUNT(*) AS item_rows FROM sql194_order_items;
```

Kết quả lần lượt là **4 khách hàng, 5 đơn hàng, 6 dòng hàng**. Khách hàng `Dũng` chưa có đơn hàng, giúp minh họa khi nào nên dùng `LEFT JOIN` ở truy vấn ngoài.

## 9. Tổng hợp trong FROM rồi JOIN với bảng khác

Bài toán: tính **tổng tiền từng đơn** bằng `SUM(quantity * unit_price)`, rồi nối với bảng đơn hàng để biết trạng thái và khách hàng.

### 9.1. Bước 1 — Tính tổng trong truy vấn con

```sql
SELECT
    i.order_id,
    SUM(i.quantity * i.unit_price) AS order_total
FROM sql194_order_items AS i
GROUP BY i.order_id
ORDER BY i.order_id;
```

Kết quả trung gian:

| order_id | order_total |
| ---: | ---: |
| 101 | 250.00 |
| 102 | 80.00 |
| 103 | 120.00 |
| 104 | 140.00 |
| 105 | 30.00 |

Đây là **một dòng trên mỗi order_id**. Tên `order_total` được tạo bằng alias ở SELECT con.

### 9.2. Bước 2 — Dùng kết quả đã nhóm như bảng dẫn xuất

```sql
SELECT
    o.order_id,
    o.customer_id,
    o.status,
    totals.order_total
FROM sql194_orders AS o
JOIN (
    SELECT
        i.order_id,
        SUM(i.quantity * i.unit_price) AS order_total
    FROM sql194_order_items AS i
    GROUP BY i.order_id
) AS totals
  ON totals.order_id = o.order_id
ORDER BY o.order_id;
```

Bí danh `totals` công bố hai cột: `order_id` và `order_total`. Truy vấn ngoài không cần tính lại biểu thức `quantity * unit_price` và không phải đưa các cột chi tiết vào `GROUP BY` của chính nó.

### Vì sao tổng hợp trước JOIN có thể hữu ích?

Nếu JOIN trực tiếp bảng đơn hàng với item, một đơn có nhiều dòng hàng sẽ xuất hiện nhiều lần. Tổng hợp theo `order_id` trước giúp mỗi đơn có **một dòng tổng tiền**, thuận tiện cho việc JOIN thêm khách hàng, trạng thái hoặc bảng khác. Tuy nhiên, tổng hợp trước **không tự đúng cho mọi bài toán**: nếu điều kiện lọc phải áp dụng trên từng item trước tổng hợp, cần đưa nó vào đúng truy vấn con.

**Chú ý với đơn không có item:** truy vấn con `GROUP BY order_id` chỉ tạo nhóm cho các order có ít nhất một item; nếu muốn vẫn giữ đơn không có item, dùng `LEFT JOIN` từ `sql194_orders` sang `totals` và quyết định xử lý `NULL` ở `order_total` theo quy tắc nghiệp vụ.

## 10. Bảng dẫn xuất để tổng hợp theo khách hàng

Yêu cầu: tính **số đơn PAID** và **tổng tiền của các đơn PAID** trên mỗi khách hàng, đồng thời vẫn hiển thị khách hàng chưa có đơn.

Ta có thể xây dựng một bảng dẫn xuất từ dữ liệu đơn hàng và tiền đơn, sau đó `LEFT JOIN` với khách hàng.

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(p.paid_order_count, 0) AS paid_order_count,
    COALESCE(p.paid_amount, 0) AS paid_amount
FROM sql194_customers AS c
LEFT JOIN (
    SELECT
        o.customer_id,
        COUNT(*) AS paid_order_count,
        SUM(t.order_total) AS paid_amount
    FROM sql194_orders AS o
    JOIN (
        SELECT
            i.order_id,
            SUM(i.quantity * i.unit_price) AS order_total
        FROM sql194_order_items AS i
        GROUP BY i.order_id
    ) AS t
      ON t.order_id = o.order_id
    WHERE o.status = 'PAID'
    GROUP BY o.customer_id
) AS p
  ON p.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Kết quả từ bộ dữ liệu:

| customer_id | customer_name | paid_order_count | paid_amount |
| ---: | --- | ---: | ---: |
| 1 | An | 1 | 250.00 |
| 2 | Bình | 1 | 120.00 |
| 3 | Chi | 1 | 140.00 |
| 4 | Dũng | 0 | 0.00 |

Giải thích từng tầng:

1. `t`: từ bảng dòng hàng, tính một số `order_total` trên mỗi `order_id`.
2. `p`: chỉ lấy các đơn `PAID`, nối với `t`, sau đó nhóm theo `customer_id` để tạo `paid_order_count` và `paid_amount`.
3. Truy vấn ngoài: `LEFT JOIN` `p` với tất cả `sql194_customers` để giữ khách hàng không có dòng tương ứng trong `p`.
4. `COALESCE` ngoài: chuyển số liệu `NULL` do thiếu nhóm `p` thành `0` **theo quy ước báo cáo**.

Ở ví dụ này, mọi đơn PAID đều có item. Nếu trong hệ thật có đơn PAID nhưng chưa có dòng item, `JOIN t` bên trong sẽ loại đơn đó khỏi `paid_order_count`. Nếu nghiệp vụ muốn **đếm mọi đơn PAID kể cả đơn rỗng**, cần dùng `LEFT JOIN` từ orders sang tổng tiền item và định nghĩa riêng cách tổng hợp tiền, thay vì mặc nhiên tái sử dụng câu trên.

### Tên cột đầu ra ở hai tầng

| Tầng | Bí danh bảng | Các cột được công bố |
| --- | --- | --- |
| Trong cùng | `t` | `order_id`, `order_total` |
| Ở giữa | `p` | `customer_id`, `paid_order_count`, `paid_amount` |
| Ngoài cùng | `c` và `p` | `c.customer_name`, `p.paid_amount`... |
| Kết quả cuối | — | `customer_id`, `customer_name`, `paid_order_count`, `paid_amount` |

Nếu sai tên ở một tầng, ví dụ gọi `p.order_total` trong truy vấn ngoài, SQL sẽ lỗi vì `p` **không công bố** cột đó; nó chỉ công bố tổng `paid_amount` và các cột được liệt kê trong `SELECT` của `p`.

## 11. Tính trước rồi lọc theo tên cột ở truy vấn ngoài

Một lợi ích thường gặp là **lọc theo kết quả biểu thức** mà không lặp lại công thức trong `WHERE` cùng cấp.

Ví dụ, tìm những dòng hàng có số tiền từ 100 trở lên:

```sql
SELECT
    d.item_id,
    d.order_id,
    d.line_amount
FROM (
    SELECT
        item_id,
        order_id,
        quantity * unit_price AS line_amount
    FROM sql194_order_items
) AS d
WHERE d.line_amount >= 100
ORDER BY d.item_id;
```

Kết quả từ bảng mẫu:

| item_id | order_id | line_amount |
| ---: | ---: | ---: |
| 1001 | 101 | 200.00 |
| 1004 | 103 | 120.00 |
| 1005 | 104 | 140.00 |

`WHERE d.line_amount >= 100` ở ngoài hoạt động vì `line_amount` đã là **tên cột đầu ra của bảng dẫn xuất `d`**.

### Điều kiện lọc bên trong và bên ngoài có thể khác ý nghĩa

So sánh hai bài toán:

**A. Chỉ cộng những item có tiền từng dòng từ 100 trở lên:**

```sql
SELECT
    order_id,
    SUM(line_amount) AS total_of_large_lines
FROM (
    SELECT
        order_id,
        quantity * unit_price AS line_amount
    FROM sql194_order_items
) AS d
WHERE line_amount >= 100
GROUP BY order_id;
```

**B. Cộng tất cả item, rồi chỉ lấy đơn có tổng tiền từ 100 trở lên:**

```sql
SELECT
    d.order_id,
    d.order_total
FROM (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM sql194_order_items
    GROUP BY order_id
) AS d
WHERE d.order_total >= 100;
```

Hai truy vấn **khác nhau**. Ở A, item giá thấp bị bỏ trước khi tổng hợp; ở B, tổng tiền đơn được tính từ tất cả item rồi mới lọc đơn. Với đơn 101, A chỉ cộng dòng 200 (bỏ 50), còn B có tổng 250.

Khi thiết kế bảng dẫn xuất, luôn hỏi: **điều kiện áp dụng cho dữ liệu chi tiết hay cho kết quả tổng hợp?**

## 12. Bảng dẫn xuất với GROUP BY, HAVING và DISTINCT

Truy vấn con trong `FROM` có thể chứa đầy đủ các mệnh đề SQL hợp lệ như `WHERE`, `GROUP BY`, `HAVING` và `DISTINCT`.

### Lọc nhóm bằng HAVING rồi cho truy vấn ngoài dùng

```sql
SELECT
    d.order_id,
    d.item_count,
    d.order_total
FROM (
    SELECT
        order_id,
        COUNT(*) AS item_count,
        SUM(quantity * unit_price) AS order_total
    FROM sql194_order_items
    GROUP BY order_id
    HAVING COUNT(*) >= 2
) AS d
ORDER BY d.order_id;
```

Kết quả: chỉ **order 101** có hai dòng item. Trong truy vấn ngoài, `item_count` và `order_total` là các cột thông thường của `d`; chúng không còn là các hàm `COUNT`/`SUM` cần tính lại ở mức ngoài.

### DISTINCT tạo một tập giá trị không trùng

```sql
SELECT
    d.customer_id
FROM (
    SELECT DISTINCT customer_id
    FROM sql194_orders
) AS d
ORDER BY d.customer_id;
```

Kết quả các mã khách có đơn: **1, 2, 3**. Khách 1 và 3 có nhiều đơn nhưng xuất hiện một lần vì `DISTINCT` đã được áp dụng ở truy vấn con.

**Không tự dùng DISTINCT để sửa JOIN sai.** Nếu một JOIN làm nhân dòng do điều kiện thiếu, `DISTINCT` ở truy vấn con có thể giấu triệu chứng chứ không sửa quan hệ. Trước tiên phải hiểu khóa nối và đơn vị dòng cần giữ.

### Khác nhau giữa WHERE ngoài và HAVING trong

`HAVING` chọn **nhóm** sau tổng hợp trong truy vấn con. `WHERE` ngoài lọc **dòng bảng dẫn xuất đã có**. Với một phép tổng hợp và biểu thức điều kiện tương ứng, hai dạng đôi khi cho kết quả như nhau; nhưng khi truy vấn con còn nhiều cột/nhóm hoặc bên ngoài có thêm JOIN, chọn vị trí đúng giúp diễn đạt rõ nghiệp vụ và tránh vô tình lọc dữ liệu ở giai đoạn khác.

## 13. Lấy một bản ghi mới nhất trong mỗi nhóm bằng ROW_NUMBER

Một trường hợp mạnh của bảng dẫn xuất: **truy vấn con tính hàm cửa sổ**, truy vấn ngoài lọc kết quả thứ hạng.

Yêu cầu: lấy **đơn hàng mới nhất của từng khách có đơn**, dựa trên `ordered_at`; khi thời gian trùng, dùng `order_id` làm khóa phụ.

```sql
-- PostgreSQL; ROW_NUMBER cũng có ở nhiều DBMS hiện đại.
SELECT
    ranked.customer_id,
    ranked.order_id,
    ranked.status,
    ranked.ordered_at
FROM (
    SELECT
        o.customer_id,
        o.order_id,
        o.status,
        o.ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS row_num
    FROM sql194_orders AS o
) AS ranked
WHERE ranked.row_num = 1
ORDER BY ranked.customer_id;
```

Kết quả từ dữ liệu mẫu:

| customer_id | order_id | status |
| ---: | ---: | --- |
| 1 | 102 | PENDING |
| 2 | 103 | PAID |
| 3 | 105 | CANCELLED |

Khách hàng 4 không có đơn nên **không tạo dòng** trong derived table `ranked`; muốn vẫn liệt kê khách 4, JOIN kết quả `ranked` với bảng khách hàng bằng `LEFT JOIN`.

**Vì sao cần bảng dẫn xuất ở đây?** Trong nhiều DBMS, không thể đặt trực tiếp `ROW_NUMBER()` trong `WHERE` của chính cấp truy vấn tính window function. Truy vấn con tính `row_num`, còn truy vấn ngoài xem đó là **cột kết quả** và lọc `row_num = 1`.

### Chọn thứ tự đủ xác định

Nếu hai đơn cùng `ordered_at`, chỉ `ORDER BY ordered_at DESC` có thể chọn một trong các dòng đồng hạng theo thứ tự không xác định. Thêm `order_id DESC` khi `order_id` duy nhất giúp chọn dòng có thứ tự ổn định cho cùng tập dữ liệu.

Không đánh đồng “mới nhất” với “ID lớn nhất” trừ khi thiết kế nghiệp vụ thực sự bảo đảm thứ tự ID phản ánh thời gian.

## 14. ORDER BY bên trong bảng dẫn xuất và thứ tự cuối cùng

Một hiểu lầm phổ biến: nếu truy vấn con đã có `ORDER BY`, truy vấn ngoài sẽ tự giữ nguyên thứ tự đó.

**Không nên dựa vào điều này.** SQL chỉ bảo đảm thứ tự trình bày của kết quả cuối khi có `ORDER BY` ở **cấp truy vấn ngoài cùng** phù hợp. Bộ tối ưu có thể hợp nhất hoặc thay đổi cách thực thi bảng dẫn xuất; thứ tự tình cờ của kết quả con không phải hợp đồng sắp xếp cho truy vấn ngoài.

Ví dụ:

```sql
-- Không nên kỳ vọng SELECT ngoài tự giữ thứ tự của subquery.
SELECT d.order_id, d.ordered_at
FROM (
    SELECT order_id, ordered_at
    FROM sql194_orders
    ORDER BY ordered_at DESC
) AS d;
```

Muốn sắp xếp kết quả cuối, viết rõ:

```sql
SELECT d.order_id, d.ordered_at
FROM (
    SELECT order_id, ordered_at
    FROM sql194_orders
) AS d
ORDER BY d.ordered_at DESC, d.order_id DESC;
```

### Khi ORDER BY bên trong thực sự quan trọng: LIMIT/FETCH

Truy vấn con có thể dùng `ORDER BY` cùng `LIMIT`/`FETCH` để **chọn trước một tập con**. Khi đó việc sắp xếp là một phần của quy tắc lựa chọn dòng, nhưng thứ tự trình bày ở ngoài vẫn cần `ORDER BY` riêng.

Ví dụ PostgreSQL: chọn **3 đơn gần nhất**, rồi JOIN khách hàng:

```sql
SELECT
    latest.order_id,
    latest.ordered_at,
    c.customer_name
FROM (
    SELECT
        order_id,
        customer_id,
        ordered_at
    FROM sql194_orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 3
) AS latest
JOIN sql194_customers AS c
  ON c.customer_id = latest.customer_id
ORDER BY latest.ordered_at DESC, latest.order_id DESC;
```

Truy vấn con quyết định **ba đơn nào** được chọn. `ORDER BY` ngoài quyết định **thứ tự hiển thị** ba đơn sau JOIN.

**Khác biệt dialect:** MySQL/MariaDB, PostgreSQL và SQLite hỗ trợ `LIMIT` theo cú pháp quen thuộc; SQL Server thường dùng `TOP` hoặc `OFFSET ... FETCH` với `ORDER BY`; Oracle dùng `FETCH FIRST ... ROWS ONLY` trên phiên bản hỗ trợ. Một số DBMS hạn chế `ORDER BY` bên trong derived table khi không đi kèm cấu trúc cho phép; do đó không sao chép nguyên query PostgreSQL sang SQL Server.

## 15. Bảng dẫn xuất, CTE và VIEW khác nhau ra sao?

Cùng một ý tưởng tổng hợp dòng hàng theo đơn có thể được diễn đạt bằng **derived table** hoặc **CTE (Common Table Expression)**.

### Bảng dẫn xuất trong FROM

```sql
SELECT o.order_id, totals.order_total
FROM sql194_orders AS o
JOIN (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM sql194_order_items
    GROUP BY order_id
) AS totals
  ON totals.order_id = o.order_id;
```

### CTE với WITH

```sql
WITH totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM sql194_order_items
    GROUP BY order_id
)
SELECT o.order_id, totals.order_total
FROM sql194_orders AS o
JOIN totals
  ON totals.order_id = o.order_id;
```

### VIEW đã lưu trong schema

```sql
-- PostgreSQL; chỉ minh họa khi cần một giao diện tái sử dụng:
CREATE VIEW sql194_order_totals_view AS
SELECT
    order_id,
    SUM(quantity * unit_price) AS order_total
FROM sql194_order_items
GROUP BY order_id;
```

View là **đối tượng database** có tên trong schema và tồn tại cho đến khi được thay đổi/xóa, còn derived table thường chỉ có hiệu lực trong **câu truy vấn chứa nó**.

| Đặc điểm | Derived table | CTE | VIEW thông thường |
| --- | --- | --- | --- |
| Nơi định nghĩa | Trong `FROM (SELECT ...)` | `WITH name AS (...)` | `CREATE VIEW name AS ...` |
| Phạm vi tên | Truy vấn/khối `FROM` bao quanh | Câu SQL chứa CTE, theo quy tắc phạm vi của engine | Đối tượng trong schema, có thể truy vấn sau này |
| Tái sử dụng tên nhiều lần trong cùng truy vấn | Thường phải lặp định nghĩa hoặc tổ chức lại | Có thể tham chiếu tên CTE nhiều lần nếu dialect hỗ trợ | Có |
| Tồn tại sau câu truy vấn | Không | Không | Có |
| Mặc nhiên lưu dữ liệu vật lý | Không được bảo đảm | Không được bảo đảm | View thông thường không; materialized view là loại khác |
| Thích hợp | Biến đổi nhỏ gắn ngay một JOIN | Truy vấn nhiều bước, nhiều nơi tham chiếu | Logic truy vấn dùng lại giữa ứng dụng/báo cáo |

**Không mặc định CTE sẽ nhanh hơn derived table** hoặc ngược lại. Bộ tối ưu có thể inline, materialize hoặc biến đổi chúng tùy DBMS, phiên bản, cấu trúc câu SQL và cấu hình. Khi truy vấn phức tạp, nên chọn cách viết **diễn đạt rõ ý nghĩa**, rồi xem execution plan trên dữ liệu thực tế.

## 16. Bảng dẫn xuất thông thường và truy vấn tương quan: LATERAL/APPLY

Một derived table thông thường trong `FROM` thường được viết như một nguồn có thể tự tính mà **không trực tiếp phụ thuộc vào một alias đã khai báo ở bảng khác cùng cấp FROM**.

Ví dụ ý tưởng:

```sql
-- Không di động và sẽ lỗi ở nhiều DBMS nếu thiếu LATERAL:
SELECT c.customer_id, recent.order_id
FROM sql194_customers AS c
JOIN (
    SELECT order_id
    FROM sql194_orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 1
) AS recent
  ON TRUE;
```

Ở đây truy vấn con cố tham chiếu `c.customer_id` từ bảng **đứng trước trong cùng mệnh đề `FROM`**. Trong PostgreSQL, điều đó cần cơ chế **`LATERAL`** (hoặc cách viết khác), chứ không phải derived table thông thường.

### PostgreSQL: LEFT JOIN LATERAL

```sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id,
    recent.ordered_at
FROM sql194_customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.ordered_at
    FROM sql194_orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS recent
  ON TRUE
ORDER BY c.customer_id;
```

Giải thích:

- `LATERAL` cho truy vấn con tham chiếu `c.customer_id` của dòng bên ngoài.
- Truy vấn con tìm **một đơn mới nhất** cho khách hàng đang xét.
- `LEFT JOIN LATERAL ... ON TRUE` giữ cả khách hàng không có đơn; các cột `recent` khi đó là `NULL`.
- Kết quả cho khách hàng 1, 2, 3 lần lượt là order 102, 103, 105; khách hàng 4 có `order_id = NULL`.

### Khác biệt giữa các DBMS

| DBMS | Cơ chế thường dùng cho nguồn con tham chiếu dòng bên ngoài |
| --- | --- |
| PostgreSQL | `LATERAL` trong `FROM`; có thể kết hợp `CROSS JOIN` hoặc `LEFT JOIN` |
| MySQL 8.0.14+ | Hỗ trợ lateral derived table trong các tình huống được quy định |
| MariaDB | Khả năng/cú pháp LATERAL khác MySQL theo phiên bản; cần kiểm tra tài liệu engine đang chạy |
| SQL Server | `CROSS APPLY` và `OUTER APPLY`; `TOP (1) ... ORDER BY` thường dùng cho lấy dòng mới nhất |
| Oracle Database | Có `LATERAL`/`CROSS APPLY`/`OUTER APPLY` trong các phiên bản hỗ trợ |
| SQLite | Không mặc nhiên hỗ trợ cú pháp `LATERAL` như PostgreSQL; thường dùng window function hoặc correlated scalar subquery |

**Không cần dùng LATERAL cho mọi bảng dẫn xuất.** Nếu truy vấn con đã tổng hợp **toàn bộ đơn hàng** thành một bảng `totals` độc lập, `JOIN (SELECT ... GROUP BY ...) AS totals` như các mục trước là hợp lý.

### Phương án không cần LATERAL

Kỹ thuật `ROW_NUMBER()` ở mục 13 tạo một derived table `ranked` độc lập rồi lọc `row_num = 1`. Nó cũng giải quyết bài toán “đơn mới nhất từng khách”, rất hữu ích khi DBMS không hỗ trợ lateral derived table hoặc khi bộ tối ưu phù hợp hơn với phép tính cửa sổ.

## 17. NULL, cột không xuất hiện và LEFT JOIN với bảng dẫn xuất

Có hai nguồn làm cột từ bảng dẫn xuất trở thành `NULL` ở truy vấn ngoài:

1. **Bản thân biểu thức con trả `NULL`**, ví dụ `SUM(...)` khi nhóm không có giá trị hợp lệ theo quy tắc aggregate.
2. **LEFT JOIN không có đối tác**, nên toàn bộ các cột từ derived table phía phải được điền `NULL`.

Ví dụ:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    totals.order_total
FROM sql194_customers AS c
LEFT JOIN (
    SELECT
        o.customer_id,
        SUM(i.quantity * i.unit_price) AS order_total
    FROM sql194_orders AS o
    JOIN sql194_order_items AS i
      ON i.order_id = o.order_id
    GROUP BY o.customer_id
) AS totals
  ON totals.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Khách hàng 4 không có đơn nên **không có dòng tương ứng trong `totals`**, và `totals.order_total` ở kết quả ngoài là `NULL`.

Nếu báo cáo quy ước người không có đơn có tổng bằng 0:

```sql
SELECT
    c.customer_id,
    COALESCE(totals.order_total, 0) AS order_total_to_show
FROM sql194_customers AS c
LEFT JOIN (
    SELECT
        o.customer_id,
        SUM(i.quantity * i.unit_price) AS order_total
    FROM sql194_orders AS o
    JOIN sql194_order_items AS i
      ON i.order_id = o.order_id
    GROUP BY o.customer_id
) AS totals
  ON totals.customer_id = c.customer_id
ORDER BY c.customer_id;
```

**`COALESCE` là lựa chọn nghiệp vụ**, không phải quy tắc tự động phải có sau mọi LEFT JOIN. Với doanh thu chưa xác định do thiếu đơn giá/số lượng, việc thay `NULL` bằng 0 có thể che giấu thiếu dữ liệu.

### Đếm sau LEFT JOIN: COUNT(*) và COUNT(cột) khác nhau

Nếu muốn đếm khách hàng có/không có nhóm tổng, không dùng `COUNT(*)` như số lượng nhóm phía phải mà không xét dòng giả do LEFT JOIN.

Ví dụ:

```sql
SELECT
    COUNT(*) AS all_customer_rows,
    COUNT(t.customer_id) AS customers_with_orders
FROM sql194_customers AS c
LEFT JOIN (
    SELECT customer_id
    FROM sql194_orders
    GROUP BY customer_id
) AS t
  ON t.customer_id = c.customer_id;
```

`all_customer_rows = 4`, `customers_with_orders = 3`. `COUNT(t.customer_id)` không tính khách hàng 4 vì cột ở phía `t` là `NULL` trong dòng LEFT JOIN không khớp.

## 18. Hiệu năng và cách bộ tối ưu xử lý derived table

Viết một derived table **không tương đương** với lệnh “tạo và lưu một bảng tạm trước, rồi mới SELECT ngoài”. Tùy DBMS và câu truy vấn, bộ tối ưu có thể:

- **Flatten/merge:** biến truy vấn con vào truy vấn ngoài để tối ưu chung.
- **Push down predicates:** đẩy một điều kiện `WHERE` từ ngoài vào trong khi vẫn bảo toàn ngữ nghĩa.
- **Materialize:** tính và lưu kết quả trung gian ở bộ nhớ/đĩa nếu có lợi hoặc cần thiết.
- Chọn kế hoạch JOIN/index khác nhau dựa trên số dòng ước tính, thứ tự JOIN, điều kiện lọc và thống kê.

Ví dụ:

```sql
SELECT d.order_id, d.order_total
FROM (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM sql194_order_items
    GROUP BY order_id
) AS d
WHERE d.order_total >= 100;
```

Ở đây `d.order_total` là kết quả **sau tổng hợp**. Không thể tùy tiện đẩy điều kiện `order_total >= 100` thành `WHERE quantity * unit_price >= 100` trước `GROUP BY` vì như vậy **đổi ý nghĩa**; một bộ tối ưu đúng phải giữ ngữ nghĩa tổng hợp dù lựa chọn cách thực thi nào.

### Index trên bảng gốc, không phải tự tạo trên alias d

Bảng dẫn xuất `d` không tồn tại như một bảng vật lý có tên trong schema nên câu:

```sql
-- SAI ý tưởng: d chỉ là alias của truy vấn, không phải bảng vật lý.
-- CREATE INDEX ix_d_order_total ON d(order_total);
```

không phải phương án tạo index cho derived table.

Thay vào đó, xem dữ liệu gốc và truy vấn sử dụng ra sao:

```sql
-- PostgreSQL: ví dụ index trên cột dùng để nhóm/JOIN.
CREATE INDEX ix_sql194_items_order_id
ON sql194_order_items(order_id);
```

Index này có thể có ích khi JOIN/tổng hợp theo `order_id` trên bảng lớn; với bảng mẫu 6 dòng, planner có thể chọn quét tuần tự. Có nên tạo index hay không phụ thuộc workload và các index đã tồn tại — chẳng hạn FK trên `order_id` trong PostgreSQL không tự sinh index phía con chỉ vì có khóa ngoại.

### EXPLAIN để xem thay vì đoán

```sql
-- PostgreSQL:
EXPLAIN
SELECT
    o.order_id,
    d.order_total
FROM sql194_orders AS o
JOIN (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM sql194_order_items
    GROUP BY order_id
) AS d ON d.order_id = o.order_id;
```

Kế hoạch có thể cho biết engine sử dụng hash aggregate, sort aggregate, hash join, nested loop, subquery scan hoặc các biến thể khác. **Không giả định có một “Subquery Scan” bắt buộc chỉ vì câu SQL chứa derived table**.

Khi cần đo thời gian, PostgreSQL có `EXPLAIN (ANALYZE, BUFFERS)`; lệnh với `ANALYZE` sẽ **thực thi truy vấn**, nên chỉ thực hiện các câu thử được phép trên môi trường phù hợp.

### Derived table lồng nhiều tầng chưa chắc tốt hơn

Lồng `SELECT` năm hoặc sáu lần chỉ để đặt một alias cho từng cột có thể khiến SQL khó đọc. Nếu biểu thức đủ đơn giản, có thể tính trực tiếp ở truy vấn ngoài. Khi có nhiều bước logic, CTE thường dễ quản lý và tái sử dụng tên hơn.

**Mục tiêu của derived table là làm rõ một giai đoạn biến đổi dữ liệu**, không phải tạo càng nhiều lớp càng tốt.

## 19. Các lỗi thường gặp với tên bảng và cột đầu ra

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Báo derived table thiếu alias | Dialect yêu cầu tên nguồn sau `(SELECT ...)` | Thêm `AS d` hoặc `d` theo DBMS |
| Báo cột `line_amount` không tồn tại | Truy vấn con chưa công bố `AS line_amount` | Đặt alias cột ngay trong SELECT con |
| Cố đọc `d.quantity` nhưng derived table chỉ có `order_total` | Cột nguồn không được đưa ra ở SELECT con | Xuất thêm cột nếu hợp nghĩa hoặc JOIN dữ liệu chi tiết đúng cấp |
| Báo `ambiguous column name` | Hai nguồn có cùng tên cột và SQL dùng tên không có prefix | Dùng `o.order_id`, `d.order_id` |
| Derived table có hai cột tên `id` | SELECT con đặt trùng alias hoặc dùng `SELECT *` từ nhiều bảng | Đặt tên khác nhau, mô tả rõ nghĩa |
| Danh sách alias cột cho kết quả sai | Alias sau tên bảng được gán **theo vị trí** | Giữ đúng thứ tự hoặc đặt `AS` trong SELECT con |
| Oracle báo lỗi khi dùng `) AS d` | Cú pháp bí danh bảng theo phiên bản/dialect Oracle | Dùng `) d` khi phù hợp |
| SQL Server báo lỗi `ORDER BY` bên trong derived table | Dialect hạn chế ORDER BY ở nguồn con nếu không có cơ chế TOP/FETCH hợp lệ | Đưa ORDER BY ra ngoài, hoặc dùng TOP/OFFSET FETCH đúng mục đích |
| Truy vấn ngoài WHERE theo alias SELECT cùng cấp bị lỗi | Alias không có phạm vi trong WHERE cùng cấp | Tính trong derived table, lọc alias ở ngoài |
| GROUP BY bên ngoài trả nhiều dòng bất ngờ | JOIN với bảng chi tiết làm nhân dòng | Xác định một dòng đại diện cho đơn/khách; tổng hợp đúng vị trí |
| Lọc `line_amount >= 100` làm sai tổng tiền đơn | Lọc từng item trước khi SUM thay vì lọc tổng sau SUM | Phân biệt điều kiện chi tiết và điều kiện nhóm |
| `LEFT JOIN` thành `INNER JOIN` ngoài ý muốn | `WHERE d.some_col = ...` loại dòng không có nhóm d | Đặt điều kiện phù hợp trong ON/subquery hoặc cho phép NULL có chủ đích |
| Dòng “mới nhất” thay đổi khi cùng timestamp | `ROW_NUMBER` thiếu tie-breaker | Thêm khóa duy nhất vào ORDER BY cửa sổ |
| Tin rằng ORDER BY trong subquery được giữ ở ngoài | Truy vấn ngoài không có ORDER BY riêng | Viết ORDER BY tại cấp kết quả cần hiển thị |
| Bảng dẫn xuất cố tham chiếu alias ở FROM ngang hàng | Thiếu `LATERAL` hoặc cơ chế tương ứng | Dùng LATERAL/APPLY hoặc window/CTE |
| Tin rằng truy vấn con luôn materialize | Bộ tối ưu có thể merge, pushdown, inline | Xem execution plan thay vì suy đoán từ cú pháp |

## 20. Khác biệt cú pháp giữa các hệ quản trị SQL

Dạng tổng quát `FROM (SELECT ...) alias` được hỗ trợ rộng rãi, nhưng một số chi tiết quan trọng:

| DBMS | Bí danh bảng dẫn xuất | Đặt tên cột | Lưu ý |
| --- | --- | --- | --- |
| **PostgreSQL** | `AS d` thông dụng; PostgreSQL 16+ nới yêu cầu alias trong một số tình huống | `SELECT expr AS x`; có `AS d(x, y)` | Hỗ trợ `LATERAL`, `LIMIT`, window function |
| **MySQL** | Alias bắt buộc cho derived table | Alias trong SELECT; danh sách tên cột sau alias ở phiên bản hỗ trợ | `LIMIT`, optimizer có thể merge/materialize derived table |
| **MariaDB** | Alias cho derived table theo cú pháp phiên bản | Ưu tiên alias trong SELECT | Tính năng LATERAL/alias-list khác MySQL; cần tra phiên bản |
| **SQL Server** | Correlation name bắt buộc, có thể dùng `AS d` | Alias trong SELECT và danh sách alias theo vị trí | `TOP`/`OFFSET FETCH`, `CROSS/OUTER APPLY`, hạn chế ORDER BY trong subquery FROM |
| **SQLite** | Alias thường được hỗ trợ, có thể không bắt buộc trong một số trường hợp | Ưu tiên `SELECT expr AS x` | Không giả định hỗ trợ danh sách alias cột ngay sau tên bảng như PostgreSQL |
| **Oracle Database** | Thường viết `) d` cho inline view; hỗ trợ AS trước alias bảng tùy phiên bản | Ưu tiên đặt alias trong SELECT con | `FETCH FIRST` ở phiên bản hỗ trợ, `LATERAL`/APPLY khi thích hợp |

### PostgreSQL

```sql
SELECT d.order_total
FROM (
    SELECT SUM(quantity * unit_price) AS order_total
    FROM sql194_order_items
) AS d;
```

### MySQL / MariaDB

```sql
-- MySQL / MariaDB: derived table cần alias.
SELECT d.order_total
FROM (
    SELECT SUM(quantity * unit_price) AS order_total
    FROM order_items
) AS d;
```

### SQL Server

```sql
-- SQL Server:
SELECT d.order_total
FROM (
    SELECT SUM(quantity * unit_price) AS order_total
    FROM dbo.order_items
) AS d;
```

Nếu cần lấy N dòng theo thời gian trong derived table, SQL Server thường viết `TOP (N)` cùng `ORDER BY` trong subquery hoặc dùng `OFFSET ... FETCH` đúng vị trí được phép.

### SQLite

```sql
-- SQLite:
SELECT d.order_total
FROM (
    SELECT SUM(quantity * unit_price) AS order_total
    FROM order_items
) AS d;
```

Cú pháp tổng hợp đơn giản này hoạt động khi `order_items` có các cột/giá trị phù hợp; SQLite có quy tắc linh hoạt về kiểu dữ liệu nên cần chú ý dữ liệu số nếu cột bị lưu bằng kiểu văn bản.

### Oracle Database

```sql
-- Oracle Database: bí danh bảng thường không viết AS.
SELECT d.order_total
FROM (
    SELECT SUM(quantity * unit_price) AS order_total
    FROM order_items
) d;
```

Oracle gọi kết quả của truy vấn con trong FROM là **inline view** trong nhiều tài liệu. Nó có cùng ý tưởng: cung cấp một nguồn dữ liệu kết quả để truy vấn ngoài dùng.

**Quy tắc liên hệ thực tế:** dù cú pháp có khác, **bí danh cột bên trong `SELECT` con** và **bí danh bảng ở ngay sau dấu ngoặc** vẫn là hai khái niệm riêng; đừng nhầm tên được công bố tại mỗi cấp.

## 21. Viết bảng dẫn xuất an toàn và dễ bảo trì

### Đặt tên ổn định, không phụ thuộc SELECT *

Trong các báo cáo/API, nên xuất **danh sách cột tường minh**:

```sql
SELECT
    d.customer_id,
    d.paid_order_count,
    d.paid_amount
FROM (
    SELECT
        customer_id,
        COUNT(*) AS paid_order_count,
        SUM(total_amount) AS paid_amount
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS d;
```

Khi bảng nguồn được thêm cột mới, tên các cột công bố ở `d` vẫn giữ theo danh sách trên. Nếu dùng `SELECT *` trong derived table từ nhiều bảng, việc thêm cột có thể làm phát sinh tên trùng hoặc thay đổi số lượng/thứ tự cột mà ứng dụng kỳ vọng.

### Không ghép dữ liệu người dùng trực tiếp vào SQL

Các giá trị lọc như trạng thái, ngày bắt đầu/kết thúc, ID khách hàng nên được **bind bằng prepared statement**. Ví dụ JDBC:

```java
String sql = """
    SELECT d.customer_id, d.paid_order_count
    FROM (
        SELECT customer_id, COUNT(*) AS paid_order_count
        FROM orders
        WHERE status = ?
        GROUP BY customer_id
    ) AS d
    WHERE d.paid_order_count >= ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "PAID");
    statement.setInt(2, 2);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(
                rs.getLong("customer_id") + ": "
                + rs.getLong("paid_order_count")
            );
        }
    }
}
```

Đoạn Java giả định `connection` đã kết nối và các lớp `PreparedStatement`, `ResultSet` được import từ `java.sql`. Prepared statement giúp **tách giá trị dữ liệu khỏi văn bản câu SQL**; nó không phải cơ chế dùng placeholder thay cho tên bảng hay tên cột.

Nếu ứng dụng cho phép chọn tên cột sắp xếp hoặc tên cột kết quả một cách động, phải dùng **allowlist** tên được phép và quote identifier theo dialect tương ứng. Không đưa tên alias, tên bảng hoặc mảnh `ORDER BY` do người dùng nhập thẳng vào SQL.

### Chọn tên mô tả đơn vị dòng

Một bí danh `totals` hay `per_order` thường dễ hiểu hơn `t1` trong truy vấn có nhiều tầng. Khi tổng hợp, tên cột nên cho biết:

- **Đơn vị**: `order_total`, `paid_order_count`, `customer_revenue`.
- **Phạm vi**: `latest_order_at`, `monthly_revenue`.
- **Quy tắc lọc**: `paid_amount` thay vì `amount` khi chỉ tính đơn PAID.

Một derived table tốt có thể được đọc như một nguồn dữ liệu độc lập: **mỗi dòng đại diện cho đối tượng gì**, **khóa của dòng là gì**, **các cột đã được đặt tên theo ý nghĩa nào**.

## 22. Bài tập thực hành

Các bài tập dùng bộ bảng `sql194_customers`, `sql194_orders`, `sql194_order_items` ở mục 8, trừ khi có ghi rõ bảng khác. Nếu bảng đã bị xóa, hãy tạo lại trước khi chạy.

### Bài 1 — Nhận diện bảng dẫn xuất và các cột công bố

Cho truy vấn:

```sql
SELECT d.order_id, d.value
FROM (
    SELECT order_id, quantity * unit_price AS value
    FROM sql194_order_items
) AS d;
```

Hãy chỉ ra: đâu là truy vấn con, đâu là bí danh bảng, đâu là bí danh cột? Có thể đổi `d.value` thành `d.quantity` mà không sửa `SELECT` con không? Vì sao?

### Bài 2 — Đổi tên cột phép tính

Viết một derived table trả các cột `item_id`, `order_id` và `line_total`, trong đó `line_total = quantity * unit_price`. Ở truy vấn ngoài, lọc `line_total > 100` rồi sắp theo `item_id` tăng dần.

### Bài 3 — Tổng tiền mỗi đơn

Từ `sql194_order_items`, tạo derived table chứa `order_id` và `order_total`. JOIN với `sql194_orders` để lấy `status`. Giải thích tại sao phải đặt alias cho `SUM(quantity * unit_price)`.

### Bài 4 — Phân biệt lọc item và lọc tổng

Cho order 101 có hai dòng tiền `200` và `50`. Kết quả khác nhau thế nào nếu:

1. Chỉ giữ dòng hàng có `line_amount >= 100` rồi SUM?
2. SUM toàn bộ dòng hàng của order trước, sau đó giữ đơn có `order_total >= 100`?

Viết hai truy vấn minh họa và nêu số tiền của order 101 trong từng trường hợp.

### Bài 5 — Giữ khách hàng chưa có đơn

Viết truy vấn hiển thị tất cả bốn khách hàng, cùng số đơn của từng khách. Dùng derived table tổng hợp `COUNT(*)` theo `customer_id` từ bảng `sql194_orders`, rồi `LEFT JOIN` ở ngoài. Khách hàng 4 cần hiển thị số đơn `0`.

### Bài 6 — Lấy đơn mới nhất trên từng khách

Dùng `ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY ordered_at DESC, order_id DESC)` trong derived table để lấy đúng một đơn mới nhất của mỗi khách có đơn. Kết quả gồm những `order_id` nào?

### Bài 7 — Phạm vi bí danh

Vì sao câu sau sai?

```sql
SELECT i.quantity
FROM (
    SELECT i.order_id, SUM(i.quantity) AS total_quantity
    FROM sql194_order_items AS i
    GROUP BY i.order_id
) AS d;
```

Viết phiên bản đúng nếu chỉ cần `order_id` và `total_quantity`.

### Bài 8 — Tên cột theo vị trí

Trên PostgreSQL, xét:

```sql
SELECT d.first_name, d.second_name
FROM (
    SELECT item_id, order_id
    FROM sql194_order_items
) AS d(first_name, second_name);
```

`d.first_name` và `d.second_name` thực ra chứa dữ liệu từ cột nào? Điều gì xảy ra với ý nghĩa khi hoán đổi hai alias trong danh sách `AS d(...)`?

### Bài 9 — ORDER BY và LIMIT

Viết truy vấn PostgreSQL lấy ba đơn mới nhất theo `ordered_at DESC, order_id DESC` bên trong derived table, JOIN với tên khách hàng rồi hiển thị **theo đúng thứ tự mới nhất trước**. Vì sao cần chú ý `ORDER BY` ở cả hai cấp khi dùng `LIMIT` bên trong?

### Bài 10 — Derived table hay LATERAL?

Một derived table trong `FROM` cố tham chiếu `c.customer_id` từ `sql194_customers AS c` ngay bên ngoài để lấy một đơn mới nhất của khách đang xét. Trên PostgreSQL, cần cú pháp nào để cho phép tham chiếu đó? Nêu một cách giải không dùng `LATERAL`.

### Bài 11 — So sánh SQL đa hệ

Bạn có SQL PostgreSQL:

```sql
SELECT d.total
FROM (
    SELECT SUM(quantity * unit_price) AS total
    FROM order_items
) AS d;
```

Hãy nêu điểm cần lưu ý khi chuyển sang Oracle Database và SQL Server: alias bảng sau derived table, cách viết `ORDER BY` nếu cần chọn N dòng trong truy vấn con, và sự khác nhau giữa cú pháp của các hệ.

### Gợi ý đáp án

**Bài 1:** `(SELECT order_id, quantity * unit_price AS value FROM sql194_order_items)` là truy vấn con; `d` là bí danh bảng; `value` là tên cột kết quả phép tính. `quantity` không được công bố nên không thể dùng `d.quantity`.

**Bài 2:**

```sql
SELECT d.item_id, d.order_id, d.line_total
FROM (
    SELECT
        item_id,
        order_id,
        quantity * unit_price AS line_total
    FROM sql194_order_items
) AS d
WHERE d.line_total > 100
ORDER BY d.item_id;
```

Kết quả `item_id = 1001, 1004, 1005`.

**Bài 3:**

```sql
SELECT o.order_id, o.status, d.order_total
FROM sql194_orders AS o
JOIN (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM sql194_order_items
    GROUP BY order_id
) AS d
  ON d.order_id = o.order_id
ORDER BY o.order_id;
```

Alias `order_total` giúp truy vấn ngoài dùng `d.order_total` thay vì tên biểu thức do DBMS tự sinh hoặc tên không hợp lệ.

**Bài 4:** Nếu lọc dòng trước khi SUM, order 101 còn **200.00**; nếu SUM trước, order 101 có **250.00**. Hai lệnh:

```sql
-- Tổng các dòng hàng có line_amount >= 100.
SELECT order_id, SUM(line_amount) AS sum_large_lines
FROM (
    SELECT order_id, quantity * unit_price AS line_amount
    FROM sql194_order_items
) AS d
WHERE line_amount >= 100
GROUP BY order_id;

-- Tổng toàn bộ dòng hàng rồi lọc đơn có tổng >= 100.
SELECT order_id, order_total
FROM (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM sql194_order_items
    GROUP BY order_id
) AS d
WHERE order_total >= 100;
```

**Bài 5:**

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(d.order_count, 0) AS order_count
FROM sql194_customers AS c
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM sql194_orders
    GROUP BY customer_id
) AS d ON d.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Số đơn lần lượt là **2, 1, 2, 0**.

**Bài 6:**

```sql
SELECT d.customer_id, d.order_id, d.ordered_at
FROM (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sql194_orders
) AS d
WHERE d.rn = 1
ORDER BY d.customer_id;
```

Các `order_id` là **102, 103, 105**.

**Bài 7:** Bí danh `i` chỉ tồn tại trong truy vấn con; truy vấn ngoài chỉ biết `d`. Phiên bản đúng:

```sql
SELECT d.order_id, d.total_quantity
FROM (
    SELECT i.order_id, SUM(i.quantity) AS total_quantity
    FROM sql194_order_items AS i
    GROUP BY i.order_id
) AS d;
```

**Bài 8:** `d.first_name` nhận giá trị `item_id`, `d.second_name` nhận giá trị `order_id`. Hoán đổi danh sách alias khiến hai tên gắn với cột nguồn ở vị trí ngược lại; SQL có thể vẫn chạy nhưng tên không còn đúng ý nghĩa.

**Bài 9:**

```sql
SELECT d.order_id, d.ordered_at, c.customer_name
FROM (
    SELECT order_id, customer_id, ordered_at
    FROM sql194_orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 3
) AS d
JOIN sql194_customers AS c ON c.customer_id = d.customer_id
ORDER BY d.ordered_at DESC, d.order_id DESC;
```

`ORDER BY` bên trong chọn đúng ba đơn mới nhất trước `LIMIT`; `ORDER BY` ngoài bảo đảm thứ tự hiển thị cuối.

**Bài 10:** Trên PostgreSQL có thể dùng `LEFT JOIN LATERAL (SELECT ... WHERE o.customer_id = c.customer_id ORDER BY ... LIMIT 1) AS latest ON TRUE`. Phương án không cần LATERAL là derived table dùng `ROW_NUMBER()` theo `customer_id` rồi lọc `rn = 1`.

**Bài 11:** SQL Server chấp nhận `AS d` cho bí danh derived table; Oracle truyền thống thường viết `) d` thay vì `) AS d`. SQL Server thường dùng `TOP` hoặc `OFFSET ... FETCH` để chọn N dòng theo thứ tự; Oracle hiện đại dùng `FETCH FIRST ... ROWS ONLY`; PostgreSQL dùng `LIMIT`. Cần xác minh phiên bản cụ thể.

## 23. Dọn dữ liệu thực hành

Sau khi hoàn thành bài tập, chỉ xóa các bảng dưới đây khi chắc chắn chúng **do chính bạn tạo** trong database thử nghiệm:

```sql
DROP TABLE sql194_order_items;
DROP TABLE sql194_orders;
DROP TABLE sql194_customers;
```

Xóa bảng con `sql194_order_items` trước `sql194_orders`, rồi mới xóa `sql194_customers` vì có khóa ngoại giữa các bảng. Không chạy các câu `DROP` trên bảng nghiệp vụ hoặc môi trường dùng chung.

## 24. Kết luận

**Bảng dẫn xuất trong `FROM` là một nguồn dữ liệu logic được tạo từ kết quả của truy vấn con.** Truy vấn bên ngoài chỉ làm việc với **những cột mà truy vấn con công bố**, thông qua **bí danh bảng** đặt sau dấu ngoặc. Tên cột đầu ra nên được chỉ định tường minh bằng `AS`, đặc biệt với phép tính, hàm tổng hợp, `CASE` và hàm cửa sổ.

Khi sử dụng thành thạo, bảng dẫn xuất giúp tách rõ các bước **lọc dữ liệu chi tiết → tính toán/tổng hợp → JOIN → lọc kết quả → sắp xếp hiển thị**. Để câu SQL đúng và dễ bảo trì, hãy kiểm tra **phạm vi tên**, **đơn vị mỗi dòng kết quả**, **vị trí áp dụng bộ lọc**, **các trường hợp `NULL` do JOIN**, và **cú pháp/khả năng tối ưu của DBMS đang dùng**.
