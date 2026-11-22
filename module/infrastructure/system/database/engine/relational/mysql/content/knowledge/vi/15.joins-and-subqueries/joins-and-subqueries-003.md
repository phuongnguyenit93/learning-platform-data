# CROSS JOIN, self join và nguy cơ nhân số dòng

`CROSS JOIN` tạo tích Descartes giữa hai tập hàng: mỗi hàng bên trái kết hợp với mọi hàng bên phải. Self join là phép nối một bảng với chính nó, thường dùng để biểu diễn quan hệ cùng loại như nhân viên và quản lý, danh mục cha-con hoặc so sánh các bản ghi trong cùng nhóm. Cả hai kỹ thuật đều hữu ích, nhưng nếu không kiểm soát số hàng và điều kiện nối, kết quả có thể tăng rất nhanh hoặc bị nhân bản ngoài ý muốn.

Trong module `DATABASE_MYSQL`, hiểu cardinality của join giúp viết truy vấn đúng, đọc `EXPLAIN`, chọn index và tránh báo cáo sai do đếm trùng. Bài học dùng MySQL 8.x và InnoDB.

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích tích Descartes và dự đoán số hàng của `CROSS JOIN`.
- Dùng `CROSS JOIN` để tạo mọi tổ hợp khi nghiệp vụ thực sự cần.
- Viết self join bằng alias để nối các hàng trong cùng một bảng.
- Phân biệt self join dạng cha-con, cùng nhóm và so sánh cặp bản ghi.
- Nhận diện nguyên nhân một join làm số hàng tăng ngoài dự kiến.
- Tránh đếm trùng khi một khóa nối khớp nhiều hàng ở cả hai phía.
- Dùng `EXPLAIN`, thống kê nhóm và index để kiểm tra cardinality.
- Biết khi nào cần recursive CTE thay cho chuỗi self join cố định.

## 1. CROSS JOIN tạo tích Descartes

`CROSS JOIN` kết hợp mỗi hàng của bảng thứ nhất với mọi hàng của bảng thứ hai. Nếu bảng A có (m) hàng và bảng B có (n) hàng, kết quả trước khi lọc có:

\[
m \times n
\]

hàng. Nếu một trong hai đầu vào không có hàng, kết quả cũng không có hàng.

Cú pháp:

```sql
SELECT column_list
FROM table_a
CROSS JOIN table_b;
```

Ví dụ nhỏ:

```sql
CREATE TABLE shirt_color (
    color_code VARCHAR(20) NOT NULL PRIMARY KEY
);

CREATE TABLE shirt_size (
    size_code VARCHAR(10) NOT NULL PRIMARY KEY
);

INSERT INTO shirt_color VALUES ('BLACK'), ('WHITE'), ('BLUE');
INSERT INTO shirt_size VALUES ('S'), ('M'), ('L'), ('XL');

SELECT c.color_code, s.size_code
FROM shirt_color AS c
CROSS JOIN shirt_size AS s
ORDER BY c.color_code, s.size_code;
```

Bảng màu có 3 hàng, bảng kích cỡ có 4 hàng nên kết quả có (3 \times 4 = 12) tổ hợp. Đây là hành vi mong muốn nếu cửa hàng cần tạo danh sách mọi biến thể màu-kích cỡ trước khi quyết định biến thể nào thực sự được bán.

### 1.1. CROSS JOIN có chủ đích

`CROSS JOIN` hữu ích khi cần tạo mọi tổ hợp giữa các tập nhỏ, độc lập:

- Màu sắc × kích cỡ để tạo ma trận biến thể sản phẩm.
- Ngày × khung giờ để tạo lịch dự kiến.
- Khu vực × loại báo cáo để tạo danh sách công việc cần chạy.
- Tham số thử nghiệm × kịch bản để tạo ma trận test.

Ví dụ tạo ma trận khu vực và kênh bán:

```sql
SELECT
    r.region_code,
    c.channel_code
FROM sales_region AS r
CROSS JOIN sales_channel AS c
ORDER BY r.region_code, c.channel_code;
```

Nếu có 20 khu vực và 8 kênh, truy vấn tạo 160 tổ hợp. Trước khi dùng trên tập lớn, hãy ước lượng tích số và xác định ứng dụng có thật sự cần mọi tổ hợp hay không.

### 1.2. CROSS JOIN rồi lọc bằng WHERE

Có thể lọc tích Descartes sau khi tạo quan hệ logic:

```sql
SELECT c.color_code, s.size_code
FROM shirt_color AS c
CROSS JOIN shirt_size AS s
WHERE c.color_code <> 'WHITE'
  AND s.size_code <> 'XL';
```

Truy vấn vẫn mô tả mọi tổ hợp màu-kích cỡ, sau đó loại các tổ hợp không cần. Với một quan hệ nối dựa trên khóa, hãy viết `INNER JOIN ... ON ...` để thể hiện điều kiện liên kết trực tiếp; không dùng `CROSS JOIN` như một cách viết vòng quanh join thiếu điều kiện.

## 2. Dự đoán và kiểm tra số hàng CROSS JOIN

Trước khi chạy một `CROSS JOIN` lớn, đếm số hàng của từng đầu vào:

```sql
SELECT COUNT(*) AS color_count FROM shirt_color;
SELECT COUNT(*) AS size_count FROM shirt_size;
```

Với hai tập độc lập, số hàng kết quả chưa lọc bằng tích hai số đếm. Có thể ước lượng trực tiếp:

```sql
SELECT
    (SELECT COUNT(*) FROM shirt_color) AS color_count,
    (SELECT COUNT(*) FROM shirt_size) AS size_count,
    (SELECT COUNT(*) FROM shirt_color)
      * (SELECT COUNT(*) FROM shirt_size) AS expected_combinations;
```

Với bảng lớn, tích có thể vượt xa khả năng xử lý hoặc giới hạn truyền kết quả của ứng dụng. Chẳng hạn 100.000 hàng kết hợp với 50.000 hàng tạo ra 5 tỷ cặp trước lọc. Ngay cả khi mỗi hàng kết quả chỉ có vài cột, chi phí CPU, I/O, bộ nhớ tạm, sort và network vẫn có thể rất lớn.

### 2.1. LIMIT không thay thế việc kiểm soát cardinality

Thêm `LIMIT 100` chỉ giới hạn số hàng trả về cho client:

```sql
SELECT c.color_code, s.size_code
FROM shirt_color AS c
CROSS JOIN shirt_size AS s
LIMIT 100;
```

Điều đó không làm cho thiết kế tích Descartes trở nên hợp lý nếu ứng dụng thực ra chỉ cần một quan hệ có điều kiện. Tùy kế hoạch thực thi và thứ tự xử lý, MySQL có thể dừng sớm khi đủ hàng cho một số truy vấn, nhưng `LIMIT` không đảm bảo loại bỏ chi phí của các bước join, sort hoặc lọc trước đó. Hãy giải quyết nguyên nhân cardinality trước.

### 2.2. CROSS JOIN với bảng rỗng

Nếu một phía rỗng, không có cặp nào:

```sql
SELECT c.color_code, s.size_code
FROM shirt_color AS c
CROSS JOIN shirt_size AS s
WHERE s.size_code = 'XXL';
```

Nếu không có kích cỡ `XXL`, kết quả rỗng. Đây là khác biệt giữa một truy vấn aggregate trên tập rỗng (có thể vẫn trả một hàng tổng hợp) và truy vấn lấy các cặp hàng trực tiếp.

## 3. Self join là gì?

Self join nối một bảng với chính nó. Trong câu lệnh, cần dùng alias khác nhau để phân biệt vai trò của mỗi lần xuất hiện:

```sql
SELECT ...
FROM employees AS employee
JOIN employees AS manager
  ON employee.manager_id = manager.employee_id;
```

Hai alias cùng tham chiếu bảng `employees`, nhưng một alias đại diện cho nhân viên và alias còn lại đại diện cho quản lý. Self join không tạo một loại bảng mới; nó chỉ dùng cùng bảng hai lần trong một truy vấn.

Self join thường dùng để:

- Tìm quản lý trực tiếp của mỗi nhân viên.
- Liệt kê các nhân viên cùng phòng ban.
- Tìm các cặp sản phẩm có cùng thuộc tính hoặc cặp bản ghi trùng lặp.
- So sánh một phiên bản bản ghi với phiên bản khác trong cùng bảng.
- Truy vấn quan hệ cha-con được lưu bằng khóa ngoại tự tham chiếu.

## 4. Ví dụ self join: nhân viên và quản lý

Một bảng nhân viên có thể lưu `manager_id` tham chiếu tới `employee_id` của một hàng khác trong cùng bảng. Người đứng đầu có thể không có quản lý nên `manager_id` cho phép `NULL`.

```sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    employee_name VARCHAR(120) NOT NULL,
    department_id BIGINT UNSIGNED NOT NULL,
    manager_id BIGINT UNSIGNED NULL,
    PRIMARY KEY (employee_id),
    KEY idx_employees_manager (manager_id),
    KEY idx_employees_department (department_id),
    CONSTRAINT fk_employees_manager
        FOREIGN KEY (manager_id)
        REFERENCES employees (employee_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

INSERT INTO employees
    (employee_id, employee_name, department_id, manager_id)
VALUES
    (1, 'Lan', 10, NULL),
    (2, 'Minh', 10, 1),
    (3, 'Huy', 10, 1),
    (4, 'Trang', 20, NULL),
    (5, 'Khanh', 20, 4),
    (6, 'Phuc', 20, 4),
    (7, 'An', 10, 2);
```

Trong dữ liệu mẫu, Lan và Trang là quản lý cấp cao; Minh và Huy báo cáo cho Lan; Khanh và Phuc báo cáo cho Trang; An báo cáo cho Minh.

### 4.1. INNER self join: chỉ lấy nhân viên có quản lý

```sql
SELECT
    e.employee_id,
    e.employee_name AS employee_name,
    m.employee_name AS manager_name
FROM employees AS e
INNER JOIN employees AS m
    ON m.employee_id = e.manager_id
ORDER BY e.employee_id;
```

`e` là nhân viên, `m` là quản lý. Điều kiện nối dùng khóa chính của alias quản lý để khớp với khóa ngoại `manager_id` của alias nhân viên. Vì là `INNER JOIN`, Lan và Trang bị loại khỏi kết quả do `manager_id` của họ là `NULL`.

### 4.2. LEFT self join: giữ cả nhân viên không có quản lý

Nếu muốn hiển thị cả người đứng đầu:

```sql
SELECT
    e.employee_id,
    e.employee_name AS employee_name,
    m.employee_name AS manager_name
FROM employees AS e
LEFT JOIN employees AS m
    ON m.employee_id = e.manager_id
ORDER BY e.employee_id;
```

Với `LEFT JOIN`, mọi nhân viên ở phía `e` đều xuất hiện. Nếu không có quản lý khớp, các cột từ alias `m` là `NULL`. Không nên đặt điều kiện `m.employee_name IS NOT NULL` trong `WHERE` nếu mục tiêu là giữ nhân viên không có quản lý, vì điều kiện đó loại các hàng null-extended và khiến kết quả có hành vi như inner join.

### 4.3. Đếm số nhân viên trực tiếp báo cáo cho mỗi quản lý

```sql
SELECT
    m.employee_id,
    m.employee_name AS manager_name,
    COUNT(e.employee_id) AS direct_report_count
FROM employees AS m
LEFT JOIN employees AS e
    ON e.manager_id = m.employee_id
GROUP BY m.employee_id, m.employee_name
ORDER BY m.employee_id;
```

Dùng `COUNT(e.employee_id)` vì cột này là khóa chính của bảng nhân viên phía phải. Quản lý không có nhân viên trực tiếp vẫn xuất hiện với số đếm 0. Nếu dùng `COUNT(*)`, hàng được tạo bởi `LEFT JOIN` cho người không có báo cáo sẽ bị đếm thành 1.

## 5. Self join để tìm các cặp trong cùng nhóm

Một trường hợp khác là tìm các nhân viên cùng phòng ban. Bảng `employees` được dùng hai lần, mỗi alias đại diện cho một thành viên của cặp:

```sql
SELECT
    e1.employee_id AS employee_1_id,
    e1.employee_name AS employee_1,
    e2.employee_id AS employee_2_id,
    e2.employee_name AS employee_2,
    e1.department_id
FROM employees AS e1
INNER JOIN employees AS e2
    ON e2.department_id = e1.department_id
   AND e1.employee_id < e2.employee_id
ORDER BY e1.department_id, e1.employee_id, e2.employee_id;
```

Điều kiện `e1.employee_id < e2.employee_id` có hai tác dụng:

- Loại cặp một nhân viên ghép với chính nó.
- Chỉ giữ một hướng của mỗi cặp, ví dụ `(Minh, Huy)` mà không trả thêm `(Huy, Minh)`.

Nếu một phòng ban có `k` nhân viên, số cặp không phân biệt thứ tự là:

\[
\frac{k(k-1)}{2}
\]

Với `k = 4`, kết quả có 6 cặp. Nếu dùng `e1.employee_id <> e2.employee_id`, mỗi cặp xuất hiện hai lần vì cả `(A, B)` và `(B, A)` đều được giữ.

### 5.1. Vì sao điều kiện nối chưa đủ có thể tạo nhiều dòng?

Nếu chỉ viết:

```sql
SELECT e1.employee_name, e2.employee_name
FROM employees AS e1
JOIN employees AS e2
    ON e1.department_id = e2.department_id;
```

mỗi nhân viên trong phòng ban sẽ ghép với mọi nhân viên khác trong cùng phòng, bao gồm chính họ. Phòng có `k` người tạo `k × k` hàng. Đây không phải lỗi cú pháp; đó là kết quả đúng của điều kiện nối đã viết, nhưng thường không phải điều người dùng mong muốn.

Nếu muốn các cặp khác nhau, thêm điều kiện loại chính nó và loại cặp đảo ngược như ví dụ trước. Nếu muốn so sánh có hướng, giữ `<>` có thể hợp lý, nhưng phải hiểu số hàng tăng gấp đôi.

## 6. Nguy cơ nhân số dòng trong JOIN

Số hàng sau join phụ thuộc số hàng khớp ở cả hai phía. Với một giá trị khóa nối cụ thể, nếu phía trái có `m` hàng và phía phải có `n` hàng cùng khóa, phép nối có thể tạo `m × n` hàng cho khóa đó.

Ví dụ, nếu một khách hàng có 3 đơn hàng và mỗi đơn hàng có 4 dòng hàng, nối khách hàng trực tiếp với cả đơn hàng và dòng hàng có thể tạo 12 hàng cho khách đó. Đây có thể là kết quả đúng ở cấp chi tiết, nhưng nếu sau đó cộng tổng tiền đơn hàng trên 12 hàng, mỗi đơn hàng sẽ bị lặp theo số dòng hàng.

### 6.1. Ví dụ nhân bản khi nối hai quan hệ nhiều hàng

```sql
CREATE TABLE customer_tag (
    customer_id BIGINT UNSIGNED NOT NULL,
    tag_name VARCHAR(40) NOT NULL,
    PRIMARY KEY (customer_id, tag_name)
) ENGINE=InnoDB;

CREATE TABLE customer_channel (
    customer_id BIGINT UNSIGNED NOT NULL,
    channel_name VARCHAR(40) NOT NULL,
    PRIMARY KEY (customer_id, channel_name)
) ENGINE=InnoDB;

INSERT INTO customer_tag VALUES
    (1, 'VIP'), (1, 'LOYAL'), (1, 'NEWSLETTER');

INSERT INTO customer_channel VALUES
    (1, 'WEB'), (1, 'MOBILE');
```

Nối hai bảng chỉ bằng `customer_id`:

```sql
SELECT t.customer_id, t.tag_name, c.channel_name
FROM customer_tag AS t
JOIN customer_channel AS c
    ON c.customer_id = t.customer_id
WHERE t.customer_id = 1;
```

Khách hàng 1 có 3 tag và 2 channel nên kết quả có 6 hàng. Mỗi tag xuất hiện với cả hai channel. Nếu mục tiêu là hiển thị mọi tổ hợp tag-channel thì đúng; nếu chỉ muốn lấy danh sách tag hoặc đếm tag, phép nối này làm tăng số hàng ngoài ý muốn.

### 6.2. Tránh cộng tổng bị nhân bản

Giả sử bảng `orders` lưu tổng tiền ở cấp đơn hàng, còn `order_items` có nhiều dòng cho mỗi đơn. Truy vấn sau có nguy cơ cộng tổng đơn hàng lặp lại:

```sql
SELECT
    o.customer_id,
    SUM(o.total_amount) AS total_amount
FROM orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id
GROUP BY o.customer_id;
```

Nếu một đơn có 3 dòng hàng, `o.total_amount` xuất hiện 3 lần sau join. Không giải quyết bằng `SUM(DISTINCT o.total_amount)` vì hai đơn khác nhau có thể có cùng tổng tiền; `DISTINCT` sẽ loại một giá trị hợp lệ.

Một cách là tổng hợp ở cấp đơn trước khi nối với quan hệ chi tiết, hoặc dùng `EXISTS` nếu chỉ cần kiểm tra đơn có dòng hàng:

```sql
SELECT
    o.customer_id,
    SUM(o.total_amount) AS total_amount
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM order_items AS i
    WHERE i.order_id = o.order_id
)
GROUP BY o.customer_id;
```

Nếu cần thống kê cả đơn không có dòng hàng, bỏ điều kiện `EXISTS` hoặc xử lý theo quy tắc nghiệp vụ. Nếu cần số liệu ở cấp dòng hàng, hãy tổng hợp `order_items` theo `order_id` trước rồi nối kết quả đã nhóm với `orders`.

### 6.3. Tổng hợp từng phía trước khi JOIN

Khi cần ghép nhiều bảng con độc lập, hãy cân nhắc aggregate từng bảng về đúng grain rồi mới nối:

```sql
WITH item_totals AS (
    SELECT order_id, SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id, SUM(paid_amount) AS paid_total
    FROM payments
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.total_amount,
    it.item_total,
    pt.paid_total
FROM orders AS o
LEFT JOIN item_totals AS it
    ON it.order_id = o.order_id
LEFT JOIN payment_totals AS pt
    ON pt.order_id = o.order_id;
```

Mỗi CTE có tối đa một hàng cho mỗi `order_id`, vì đã nhóm theo khóa đơn hàng. Khi nối vào `orders`, số hàng không bị nhân lên bởi nhiều dòng hàng hoặc nhiều khoản thanh toán độc lập. Cần xác định cách xử lý `NULL` và đơn không có item/payment ở phần hiển thị hoặc phép tính tiếp theo.

## 7. Phân biệt CROSS JOIN ngoài ý muốn với INNER JOIN thiếu điều kiện

Một lỗi phổ biến là liệt kê hai bảng trong `FROM` nhưng quên điều kiện nối:

```sql
-- Tạo tích Descartes; thường là lỗi nếu mục tiêu là nối theo khóa.
SELECT o.order_id, c.customer_name
FROM orders AS o, customers AS c;
```

Trong MySQL, cú pháp liệt kê bảng bằng dấu phẩy không có điều kiện liên kết tạo tích Descartes. Hãy viết rõ:

```sql
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id;
```

Viết `JOIN` tường minh giúp người review nhìn thấy điều kiện liên kết. Với `CROSS JOIN`, việc không có điều kiện nối là chủ đích nên cần được thể hiện rõ trong code và tài liệu.

### 7.1. Điều kiện nối không đầy đủ

Trong mô hình multi-tenant, một mã `project_id` có thể chỉ duy nhất trong từng tenant. Nếu khóa thực tế là `(tenant_id, project_id)` nhưng truy vấn chỉ nối theo `project_id`, hàng từ tenant khác có thể ghép nhầm hoặc nhân bản.

```sql
-- Thiếu một phần khóa ghép: có thể ghép nhầm tenant.
SELECT t.task_id, p.project_name
FROM project_task AS t
JOIN tenant_project AS p
    ON p.project_id = t.project_id;

-- Dùng đầy đủ các thành phần khóa.
SELECT t.task_id, p.project_name
FROM project_task AS t
JOIN tenant_project AS p
    ON p.tenant_id = t.tenant_id
   AND p.project_id = t.project_id;
```

Hãy nối theo toàn bộ khóa nghiệp vụ/khóa ngoại, không chỉ theo một cột trông có vẻ đủ duy nhất trong dữ liệu mẫu.

## 8. Self join với dữ liệu phân cấp

Mô hình `employees.manager_id` là adjacency list: mỗi hàng lưu ID của cha trực tiếp. Self join đơn giản lấy được một cấp quản lý. Nếu cần nhiều cấp cố định, có thể nối bảng nhiều lần:

```sql
SELECT
    e.employee_name AS employee_name,
    m.employee_name AS manager_name,
    d.employee_name AS department_head_name
FROM employees AS e
LEFT JOIN employees AS m
    ON m.employee_id = e.manager_id
LEFT JOIN employees AS d
    ON d.employee_id = m.manager_id;
```

Truy vấn trên đi lên tối đa hai cấp. Nó không tự tìm mọi cấp của cây. Nếu chiều sâu không cố định, MySQL 8.0 hỗ trợ recursive CTE:

```sql
WITH RECURSIVE employee_chain AS (
    SELECT
        employee_id,
        employee_name,
        manager_id,
        0 AS depth
    FROM employees
    WHERE employee_id = 7

    UNION ALL

    SELECT
        manager.employee_id,
        manager.employee_name,
        manager.manager_id,
        chain.depth + 1
    FROM employees AS manager
    JOIN employee_chain AS chain
        ON manager.employee_id = chain.manager_id
)
SELECT employee_id, employee_name, manager_id, depth
FROM employee_chain
ORDER BY depth;
```

CTE bắt đầu từ nhân viên 7 rồi đi ngược lên quản lý, dừng khi `manager_id` là `NULL` hoặc không còn hàng khớp. Dữ liệu phân cấp cần ngăn chu trình như một nhân viên tự quản lý chính mình hoặc A quản lý B, B quản lý A. Recursive CTE có giới hạn đệ quy và cần chiến lược phát hiện chu trình phù hợp nếu dữ liệu không được bảo đảm hợp lệ.

Nếu chỉ cần một cấp quan hệ, self join thường đơn giản và dễ tối ưu hơn. Dùng recursive CTE khi cần duyệt số cấp không cố định.

## 9. NULL trong điều kiện JOIN

Điều kiện nối thông thường dùng `=` không ghép hai giá trị `NULL`:

```sql
SELECT a.id, b.id
FROM table_a AS a
JOIN table_b AS b
    ON a.optional_code = b.optional_code;
```

Nếu cả `a.optional_code` và `b.optional_code` đều `NULL`, biểu thức so sánh cho `UNKNOWN`, không phải `TRUE`, nên hai hàng không khớp. Trong hầu hết quan hệ khóa ngoại, đây là hành vi mong muốn vì `NULL` biểu thị không có khóa tham chiếu.

Nếu nghiệp vụ thực sự muốn coi hai `NULL` là khớp, MySQL có toán tử null-safe equality `<=>`:

```sql
SELECT a.id, b.id
FROM table_a AS a
JOIN table_b AS b
    ON a.optional_code <=> b.optional_code;
```

Hãy thận trọng: nếu có `p` hàng null ở A và `q` hàng null ở B, `<=>` sẽ ghép chúng thành `p × q` cặp. Không dùng `<=>` để nối khóa tùy tiện nếu các hàng null không đại diện cho cùng một thực thể nghiệp vụ.

## 10. Index và kế hoạch thực thi

### 10.1. Index cho self join

Với self join nhân viên-quản lý:

```sql
ON m.employee_id = e.manager_id
```

`employee_id` là primary key, còn `manager_id` nên có index để tìm các nhân viên trực tiếp của một quản lý. Index `idx_employees_manager(manager_id)` trong ví dụ hỗ trợ truy vấn tìm cấp dưới và đếm báo cáo trực tiếp.

Với self join cùng phòng ban, index `(department_id, employee_id)` có thể hỗ trợ tìm các hàng cùng phòng và so sánh ID:

```sql
CREATE INDEX idx_employees_department_employee
ON employees (department_id, employee_id);
```

Không tạo index chỉ vì cột xuất hiện trong `ON`. Hãy xét selectivity, số hàng, tần suất truy vấn, chi phí ghi và index hiện có. Primary key hoặc index ghép có thể đã đáp ứng truy vấn.

### 10.2. Đọc EXPLAIN

Kiểm tra kế hoạch của self join:

```sql
EXPLAIN
SELECT
    e.employee_name,
    m.employee_name AS manager_name
FROM employees AS e
LEFT JOIN employees AS m
    ON m.employee_id = e.manager_id;
```

Kiểm tra kế hoạch của truy vấn tạo cặp cùng phòng:

```sql
EXPLAIN FORMAT=TREE
SELECT e1.employee_id, e2.employee_id
FROM employees AS e1
JOIN employees AS e2
    ON e2.department_id = e1.department_id
   AND e1.employee_id < e2.employee_id;
```

Quan sát:

- Bảng/alias nào được đọc trước.
- `key` hoặc access path nào được chọn.
- Số hàng ước lượng ở từng bước.
- Điều kiện nào được dùng làm join condition và điều kiện nào là filter.
- Có sort, materialization hoặc temporary table hay không.

Với MySQL 8.0.18 trở lên, `EXPLAIN ANALYZE` có thể cho biết số hàng và thời gian thực tế của từng iterator. Lệnh này thực sự chạy truy vấn; chỉ dùng với truy vấn đọc an toàn và dữ liệu lab/staging khi chưa hiểu chi phí.

## 11. Cách phát hiện join làm tăng số hàng ngoài dự kiến

Khi kết quả có nhiều hàng hơn dự tính, kiểm tra theo thứ tự:

1. Đếm số hàng ở từng bảng trước join.
2. Kiểm tra khóa nối có duy nhất ở phía mà bạn đang kỳ vọng là một-một hay không.
3. Đếm số hàng trên mỗi khóa ở cả hai phía.
4. Xác minh join condition có đầy đủ mọi thành phần của khóa ghép.
5. Kiểm tra điều kiện tự nối có loại cặp một hàng với chính nó hay chưa.
6. Kiểm tra có cần cặp có thứ tự hay chỉ một cặp không phân biệt thứ tự.
7. Xác định grain của kết quả: một hàng mỗi khách, mỗi đơn, mỗi dòng hàng hay mỗi cặp.
8. Tổng hợp dữ liệu ở đúng grain trước khi nối nếu nhiều bảng con độc lập.
9. Dùng `EXPLAIN` để xác nhận cardinality ước lượng và access path.

Ví dụ kiểm tra số hàng trên mỗi khóa:

```sql
SELECT customer_id, COUNT(*) AS rows_per_customer
FROM customer_tag
GROUP BY customer_id
ORDER BY rows_per_customer DESC;

SELECT customer_id, COUNT(*) AS rows_per_customer
FROM customer_channel
GROUP BY customer_id
ORDER BY rows_per_customer DESC;
```

Nếu một khách có 3 tag và 2 channel, join hai tập này theo `customer_id` tạo 6 tổ hợp. Đây là phép nhân theo cardinality của mỗi khóa, không phải lỗi ngẫu nhiên của MySQL.

## 12. CROSS JOIN và self join trong báo cáo

Trước khi đưa truy vấn vào báo cáo hoặc API, hãy xác định grain đầu ra. Ví dụ:

| Nhu cầu | Grain mong muốn | Cách làm phù hợp |
|---|---|---|
| Danh sách mọi màu-kích cỡ | Một hàng cho mỗi cặp màu-kích cỡ | `CROSS JOIN` hai tập nhỏ |
| Danh sách nhân viên và quản lý trực tiếp | Một hàng cho mỗi nhân viên | Self `LEFT JOIN` |
| Đếm số cấp dưới trực tiếp | Một hàng cho mỗi quản lý | Self `LEFT JOIN` + `COUNT(child.id)` |
| Các cặp nhân viên khác nhau cùng phòng | Một hàng cho mỗi cặp không thứ tự | Self join với `id < other_id` |
| Tìm mọi tổ hợp tag-channel của khách | Một hàng cho mỗi cặp tag-channel | Join hai tập theo customer; dự đoán tích số |
| Tổng tiền mỗi khách từ đơn hàng và dòng hàng | Một hàng cho mỗi khách | Aggregate đúng grain trước khi nối |

Nếu grain không được xác định trước, `COUNT`, `SUM`, `AVG` hoặc phân trang có thể cho kết quả sai dù cú pháp SQL hoàn toàn hợp lệ.

## 13. Bài thực hành

Thực hiện trong database lab riêng với các bảng `shirt_color`, `shirt_size`, `employees`, `customer_tag` và `customer_channel`:

1. Chạy `CROSS JOIN` màu và kích cỡ; xác nhận số hàng bằng tích hai số đếm đầu vào.
2. Thêm một kích cỡ mới và xác nhận số tổ hợp tăng đúng bằng số màu hiện có.
3. Thử `CROSS JOIN` với một tập đầu vào rỗng; xác nhận kết quả không có hàng.
4. Viết self `INNER JOIN` để lấy nhân viên và quản lý trực tiếp; giải thích vì sao người đứng đầu không xuất hiện.
5. Viết lại bằng `LEFT JOIN` để giữ người không có quản lý; đếm số báo cáo trực tiếp bằng `COUNT(employee_id)` phía con.
6. Tạo truy vấn self join liệt kê nhân viên cùng phòng; so sánh `<>` và `<` để quan sát cặp đảo chiều và số hàng.
7. Tính số cặp dự kiến trong mỗi phòng bằng `k * (k - 1) / 2`, rồi đối chiếu với truy vấn self join dùng `<`.
8. Nối `customer_tag` với `customer_channel` theo `customer_id`; giải thích vì sao một khách có 3 tag và 2 channel tạo 6 hàng.
9. Thử đếm tag sau khi nối channel; so sánh với đếm trực tiếp từ `customer_tag` và giải thích hiện tượng nhân bản.
10. Viết truy vấn tính tổng đơn hàng nhưng nối thêm `order_items`; sửa truy vấn bằng `EXISTS` hoặc aggregate CTE để tránh cộng lặp.
11. Dùng `EXPLAIN` và `EXPLAIN FORMAT=TREE` cho các truy vấn self join; kiểm tra index trên `manager_id` và `(department_id, employee_id)`.
12. Tạo một bảng có khóa ghép tenant-project; thử join thiếu `tenant_id`, sau đó thêm đầy đủ điều kiện và so sánh kết quả.
13. Thử nối hai cột nullable bằng `=` và `<=>`; tạo nhiều hàng `NULL` ở hai phía để quan sát nguy cơ nhân số dòng.

Bạn hoàn thành bài khi dự đoán được số hàng trước khi chạy join, viết được self join đúng vai trò alias và giải thích được nguyên nhân một truy vấn tổng hợp bị nhân bản dữ liệu.

## 14. Nguyên tắc cần ghi nhớ

- `CROSS JOIN` tạo mọi cặp hàng; số hàng chưa lọc bằng tích cardinality của hai đầu vào.
- Chỉ dùng `CROSS JOIN` khi mọi tổ hợp thực sự có ý nghĩa; đếm trước số hàng dự kiến.
- Self join dùng cùng bảng nhiều lần với alias khác nhau; alias thể hiện vai trò từng phía.
- Với quan hệ cha-con, `INNER JOIN` loại hàng không có cha; `LEFT JOIN` giữ hàng đó với cột phía cha là `NULL`.
- Dùng `COUNT(child.primary_key)` để đếm hàng con sau `LEFT JOIN`, tránh đếm hàng mở rộng bằng `COUNT(*)`.
- Self join theo nhóm có thể tạo `k * k` hàng; dùng `id < other_id` nếu cần mỗi cặp không thứ tự đúng một lần.
- Nếu hai phía đều có nhiều hàng cùng khóa, số kết quả theo khóa có thể là `m × n`.
- Nối theo đầy đủ khóa ghép; không giả định một cột thành phần là duy nhất nếu schema không bảo đảm.
- Aggregate từng bảng con về đúng grain trước khi nối nếu không muốn số liệu bị nhân bản.
- Kiểm tra index trên cột join và dùng `EXPLAIN` để hiểu cardinality/access path.
- Dùng recursive CTE cho cây có số cấp không cố định; self join nhiều lần chỉ phù hợp với độ sâu cố định.
- Toán tử `=` không ghép hai giá trị `NULL`; `<=>` có thể ghép nhiều hàng NULL thành tích số lớn, nên chỉ dùng khi nghiệp vụ yêu cầu.
