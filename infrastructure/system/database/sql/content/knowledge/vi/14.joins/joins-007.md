# Ghép nhiều bảng và xác định đường liên kết

Một đơn hàng có thể liên quan đến **khách hàng**, **nhân viên xử lý**, **phòng ban**, **các dòng hàng**, **sản phẩm**, **danh mục sản phẩm** và **các lần thanh toán**. Thông tin nằm ở nhiều bảng để giảm trùng lặp và bảo vệ quan hệ dữ liệu. Muốn tạo báo cáo hoàn chỉnh, ta phải đi qua các quan hệ đó bằng `JOIN`.

Khó khăn không chỉ là nhớ cú pháp `INNER JOIN` hay `LEFT JOIN`. Điều quan trọng hơn là **xác định đúng đường liên kết** (*join path*): bảng nào là điểm xuất phát, cột khóa nào nối hai bảng, cần đi qua bảng trung gian nào, và mỗi phép nối có thể làm **tăng hoặc giảm số dòng** như thế nào.

Ví dụ, từ một đơn hàng tới danh mục sản phẩm không có quan hệ trực tiếp:

~~~text
orders --> order_items --> products --> categories
~~~

Nếu bỏ qua `order_items` hoặc nối bằng hai cột tình cờ có cùng giá trị số, truy vấn có thể trả dữ liệu sai mà không báo lỗi. Nếu nối thêm cả bảng `payments` khi mỗi đơn có nhiều dòng hàng và nhiều lần thanh toán, kết quả có thể bị **nhân bản hàng**, khiến `COUNT` và `SUM` sai.

Bài này thuộc **Database SQL → Kết nối bảng**, tập trung vào tư duy lập sơ đồ quan hệ, xác định đường đi qua nhiều bảng, giữ đúng phạm vi kết quả và kiểm soát số lượng dòng phát sinh. Ví dụ thực hành dùng **PostgreSQL**; nguyên tắc thiết kế đường liên kết áp dụng rộng cho các hệ quản trị quan hệ.

## 1. Khái niệm: khóa, quan hệ và đường liên kết

Hãy hình dung mỗi bảng là **một nút** trong sơ đồ, mỗi quan hệ được định nghĩa bằng các cột khóa là **một cạnh**:

~~~text
departments
    ^ 1
    | N
employees
    ^ 1
    | N (orders.employee_id co the NULL)
    |
customers 1 <-- N orders 1 --> N order_items N --> 1 products N --> 1 categories
                    |
                    1
                    |
                    N
                 payments
~~~

Mũi tên thể hiện hướng **tham chiếu khóa ngoại** khi đọc từ bảng con tới bảng cha; ký hiệu `1` và `N` thể hiện số hàng có thể liên quan ở mỗi phía. Sơ đồ là quan hệ logic, không phải thứ tự SQL bắt buộc phải viết.

| Khái niệm | Ý nghĩa | Ví dụ trong bài |
| --- | --- | --- |
| **Khóa chính** (*primary key*) | Định danh duy nhất một hàng | `customers.customer_id` |
| **Khóa ngoại** (*foreign key*) | Giá trị của bảng con tham chiếu khóa ở bảng khác | `orders.customer_id` tham chiếu `customers.customer_id` |
| **Quan hệ 1–N** | Một hàng phía cha có thể liên quan nhiều hàng phía con | Một khách có nhiều đơn |
| **Bảng trung gian** (*junction/bridge table*) | Lưu các cặp liên kết trong quan hệ N–N | `order_items` nối `orders` và `products` |
| **Đường liên kết** (*join path*) | Chuỗi quan hệ phải đi qua để lấy đủ dữ liệu | `orders → order_items → products → categories` |
| **Độ hạt** (*grain*) | Một hàng kết quả đại diện cho điều gì | Một đơn, một dòng hàng, hay một lần thanh toán |

**Cùng tên cột không chứng minh hai cột có quan hệ.** Một phép nối đúng thường dựa trên mô hình nghiệp vụ và các khóa được khai báo, không phải chỉ dựa vào việc hai bảng đều có cột `id`.

## 2. Chuẩn bị hệ dữ liệu mẫu gồm tám bảng

Các ví dụ dưới đây được thiết kế để chạy trong **database PostgreSQL thực hành riêng**. Chỉ chạy đoạn khởi tạo **một lần**, khi chưa có các bảng tên `lab_j180_*`. Nếu bạn không có quyền tạo bảng, hãy dùng database/sandbox được cấp quyền; đừng chạy lệnh tạo bảng trên hệ thống sản xuất.

### 2.1. Tạo các bảng cha và bảng danh mục

~~~sql
CREATE TABLE lab_j180_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(80) NOT NULL
);

CREATE TABLE lab_j180_departments (
    department_id INTEGER PRIMARY KEY,
    department_name VARCHAR(80) NOT NULL
);

CREATE TABLE lab_j180_employees (
    employee_id INTEGER PRIMARY KEY,
    employee_name VARCHAR(80) NOT NULL,
    department_id INTEGER NOT NULL
        REFERENCES lab_j180_departments(department_id)
);

CREATE TABLE lab_j180_categories (
    category_id INTEGER PRIMARY KEY,
    category_name VARCHAR(80) NOT NULL
);

CREATE TABLE lab_j180_products (
    product_id INTEGER PRIMARY KEY,
    product_name VARCHAR(80) NOT NULL,
    category_id INTEGER NOT NULL
        REFERENCES lab_j180_categories(category_id)
);
~~~

### 2.2. Tạo đơn hàng, dòng hàng và lần thanh toán

~~~sql
CREATE TABLE lab_j180_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lab_j180_customers(customer_id),
    employee_id INTEGER
        REFERENCES lab_j180_employees(employee_id),
    order_status VARCHAR(12) NOT NULL
        CHECK (order_status IN ('NEW', 'PAID')),
    ordered_on DATE NOT NULL
);

CREATE TABLE lab_j180_order_items (
    order_id INTEGER NOT NULL
        REFERENCES lab_j180_orders(order_id),
    product_id INTEGER NOT NULL
        REFERENCES lab_j180_products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE lab_j180_payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES lab_j180_orders(order_id),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    payment_status VARCHAR(12) NOT NULL
        CHECK (payment_status IN ('SETTLED', 'PENDING'))
);
~~~

Trong bảng `lab_j180_orders`, cột `employee_id` **được phép `NULL`**: đơn có thể chưa được giao nhân viên. Các quan hệ khác trong dữ liệu mẫu được ràng buộc bằng khóa ngoại.

`lab_j180_order_items` có **khóa chính ghép** `(order_id, product_id)`. Với thiết kế đơn giản này, cùng một sản phẩm xuất hiện tối đa một dòng trong một đơn. Hệ thống thương mại thực tế có thể dùng `order_item_id` riêng nếu cần nhiều dòng cùng sản phẩm nhưng có cấu hình/giá hoặc chiết khấu khác nhau.

### 2.3. Chèn dữ liệu

~~~sql
INSERT INTO lab_j180_customers (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi'),
    (4, 'Dung');

INSERT INTO lab_j180_departments
    (department_id, department_name)
VALUES
    (10, 'Retail'),
    (20, 'Online'),
    (30, 'Logistics');

INSERT INTO lab_j180_employees
    (employee_id, employee_name, department_id)
VALUES
    (101, 'Mai', 10),
    (102, 'Nam', 20),
    (103, 'Linh', 20),
    (104, 'Phuong', 30);

INSERT INTO lab_j180_categories
    (category_id, category_name)
VALUES
    (1, 'Van phong pham'),
    (2, 'Phu kien'),
    (3, 'Dien tu');

INSERT INTO lab_j180_products
    (product_id, product_name, category_id)
VALUES
    (501, 'So tay', 1),
    (502, 'But', 1),
    (503, 'Ba lo', 2),
    (504, 'Chuot', 3);

INSERT INTO lab_j180_orders
    (order_id, customer_id, employee_id, order_status, ordered_on)
VALUES
    (1001, 1, 101,  'PAID', DATE '2026-10-01'),
    (1002, 1, 102,  'NEW',  DATE '2026-10-02'),
    (1003, 2, 102,  'PAID', DATE '2026-10-03'),
    (1004, 3, 103,  'PAID', DATE '2026-10-04'),
    (1005, 3, NULL, 'NEW',  DATE '2026-10-05');

INSERT INTO lab_j180_order_items
    (order_id, product_id, quantity, unit_price)
VALUES
    (1001, 501, 2, 100.00),
    (1001, 502, 3,  20.00),
    (1002, 503, 1, 300.00),
    (1003, 502, 5,  20.00),
    (1003, 503, 1, 300.00),
    (1004, 501, 1, 100.00);

INSERT INTO lab_j180_payments
    (payment_id, order_id, amount, payment_status)
VALUES
    (9001, 1001, 260.00, 'SETTLED'),
    (9002, 1003, 200.00, 'SETTLED'),
    (9003, 1003, 200.00, 'SETTLED'),
    (9004, 1004, 100.00, 'SETTLED');
~~~

Điểm quan trọng trong bộ dữ liệu:

- Có **4 khách hàng**, nhưng Dũng (ID 4) **chưa có đơn hàng**.
- Có **5 đơn hàng**. Đơn 1005 chưa giao nhân viên và chưa có dòng hàng.
- Có **6 dòng hàng**; đơn 1001 và 1003 mỗi đơn có hai dòng hàng.
- Có **4 lần thanh toán**; riêng đơn 1003 được thanh toán bằng **hai lần**.
- Sản phẩm Chuot (ID 504) chưa có dòng hàng bán nào.
- Nhân viên Phuong (ID 104) chưa được giao đơn.

Đọc tập đơn hàng làm mốc:

~~~sql
SELECT order_id, customer_id, employee_id, order_status
FROM lab_j180_orders
ORDER BY order_id;
~~~

| order_id | customer_id | employee_id | order_status |
| ---: | ---: | ---: | --- |
| 1001 | 1 | 101 | PAID |
| 1002 | 1 | 102 | NEW |
| 1003 | 2 | 102 | PAID |
| 1004 | 3 | 103 | PAID |
| 1005 | 3 | `NULL` | NEW |

## 3. Quy trình xác định đường liên kết trước khi viết JOIN

Giả sử yêu cầu: “Mỗi đơn hàng, hiển thị tên khách hàng, nhân viên xử lý và phòng ban của nhân viên”.

Đừng viết `JOIN` ngay. Trước hết:

1. **Chọn bảng gốc và độ hạt kết quả.** “Mỗi đơn hàng” → bảng gốc là `orders`, mục tiêu **một dòng cho mỗi đơn**.
2. **Liệt kê dữ liệu cần hiển thị.** `order_id` ở `orders`; `customer_name` ở `customers`; `employee_name` ở `employees`; `department_name` ở `departments`.
3. **Vẽ đường đi theo khóa đã biết.** `orders.customer_id → customers.customer_id`; `orders.employee_id → employees.employee_id`; `employees.department_id → departments.department_id`.
4. **Xác định các quan hệ bắt buộc/tùy chọn.** Mọi đơn có khách hàng; nhưng đơn 1005 chưa có nhân viên, nên muốn giữ đơn đó phải dùng `LEFT JOIN` tới nhân viên và phòng ban.
5. **Kiểm tra sự thay đổi số dòng theo mỗi phép nối.** Các đích `customers`, `employees` và `departments` được nối qua khóa chính duy nhất nên, nếu là `LEFT JOIN` hoặc có quan hệ bắt buộc hợp lệ, chúng không nhân bản một đơn.
6. **Chọn các cột cụ thể và đặt bí danh.** Viết rõ `o.customer_id = c.customer_id`, không dựa vào tên cột vô danh `id`.

Trong ví dụ này, đường liên kết gồm hai nhánh xuất phát từ `orders`:

~~~text
                   orders o
                  /        \
       customer_id          employee_id
             |                   |
             v                   v
       customers c           employees e
                                 |
                             department_id
                                 |
                                 v
                            departments d
~~~

Không nhất thiết phải đi theo **một chuỗi duy nhất**. Một truy vấn nhiều bảng thường là **một đồ thị liên kết nhỏ**, có nhiều nhánh từ bảng gốc.

## 4. JOIN bốn bảng để lấy dữ liệu của từng đơn

~~~sql
SELECT
    o.order_id,
    c.customer_name,
    e.employee_name,
    d.department_name,
    o.order_status
FROM lab_j180_orders AS o
JOIN lab_j180_customers AS c
    ON c.customer_id = o.customer_id
LEFT JOIN lab_j180_employees AS e
    ON e.employee_id = o.employee_id
LEFT JOIN lab_j180_departments AS d
    ON d.department_id = e.department_id
ORDER BY o.order_id;
~~~

Kết quả:

| order_id | customer_name | employee_name | department_name | order_status |
| ---: | --- | --- | --- | --- |
| 1001 | An | Mai | Retail | PAID |
| 1002 | An | Nam | Online | NEW |
| 1003 | Binh | Nam | Online | PAID |
| 1004 | Chi | Linh | Online | PAID |
| 1005 | Chi | `NULL` | `NULL` | NEW |

Giải thích từng nối:

- `orders o JOIN customers c`: mọi đơn trong dữ liệu mẫu có `customer_id` tham chiếu khách hàng hiện hữu, nên `INNER JOIN` là phù hợp khi chỉ xét các đơn hợp lệ.
- `LEFT JOIN employees e`: giữ cả đơn 1005, dù `employee_id IS NULL`.
- `LEFT JOIN departments d`: lấy phòng ban theo **nhân viên** được giao, không nối trực tiếp `orders` tới `departments` vì bảng đơn không có `department_id`.
- `ORDER BY o.order_id`: quy định rõ thứ tự hiển thị, tránh giả định thứ tự tự nhiên.

Các bí danh `o`, `c`, `e`, `d` chỉ có phạm vi trong truy vấn. Chúng giúp phân biệt những cột có tên giống nhau, ví dụ `customer_id` hoặc `department_id`.

### Vì sao nối phòng ban cũng cần LEFT JOIN?

Câu sau **khác ý nghĩa**:

~~~sql
SELECT o.order_id, e.employee_name, d.department_name
FROM lab_j180_orders AS o
LEFT JOIN lab_j180_employees AS e
    ON e.employee_id = o.employee_id
JOIN lab_j180_departments AS d
    ON d.department_id = e.department_id
ORDER BY o.order_id;
~~~

Với đơn 1005, phép nối đầu tạo hàng còn giữ đơn nhưng `e.department_id` là `NULL`. Phép `INNER JOIN departments` kế tiếp yêu cầu tìm một phòng ban khớp; không có phòng ban nào khớp với `NULL`, nên **đơn 1005 biến mất**.

Nếu yêu cầu là “các đơn đã có nhân viên và phòng ban”, kết quả này có thể đúng. Nếu yêu cầu là “mọi đơn kể cả chưa phân công”, phải duy trì nhánh nối tùy chọn bằng `LEFT JOIN` (hoặc cách diễn đạt tương đương phù hợp).

## 5. Mỗi JOIN có thể thay đổi số dòng như thế nào?

Một trong những bước quan trọng nhất khi ghép nhiều bảng là nhìn vào **bội số quan hệ** (*cardinality*).

| Đường nối | Quan hệ trong mô hình | Tác động khi bắt đầu từ bên trái |
| --- | --- | --- |
| `orders → customers` | N–1 | Mỗi đơn tìm tối đa một khách; không nhân hàng |
| `orders → employees` | N–1, có thể thiếu nhân viên | `LEFT JOIN` giữ đơn, điền `NULL` ở phía nhân viên nếu không khớp |
| `employees → departments` | N–1 | Mỗi nhân viên thuộc một phòng ban trong mẫu |
| `orders → order_items` | 1–N | Một đơn có thể xuất hiện **nhiều lần** trong kết quả |
| `order_items → products` | N–1 | Mỗi dòng hàng trỏ tới một sản phẩm |
| `products → categories` | N–1 | Mỗi sản phẩm thuộc một danh mục |
| `orders → payments` | 1–N | Một đơn có thể xuất hiện **nhiều lần** theo các khoản thanh toán |

### 5.1. Nối đơn hàng với dòng hàng

~~~sql
SELECT
    o.order_id,
    oi.product_id,
    oi.quantity,
    oi.unit_price
FROM lab_j180_orders AS o
JOIN lab_j180_order_items AS oi
    ON oi.order_id = o.order_id
ORDER BY o.order_id, oi.product_id;
~~~

| order_id | product_id | quantity | unit_price |
| ---: | ---: | ---: | ---: |
| 1001 | 501 | 2 | 100.00 |
| 1001 | 502 | 3 | 20.00 |
| 1002 | 503 | 1 | 300.00 |
| 1003 | 502 | 5 | 20.00 |
| 1003 | 503 | 1 | 300.00 |
| 1004 | 501 | 1 | 100.00 |

Từ **5 đơn** ban đầu, `INNER JOIN` với `order_items` trả **6 dòng**, không phải 5. Đơn 1001 xuất hiện hai lần và đơn 1003 xuất hiện hai lần vì mỗi đơn có hai sản phẩm. Đơn 1005 không có dòng hàng nên **không xuất hiện** trong `INNER JOIN`.

Điều này **không nhất thiết là lỗi**: nếu báo cáo yêu cầu “mỗi dòng đại diện một sản phẩm trong đơn”, sáu dòng là kết quả chính xác. Nhưng nếu báo cáo yêu cầu “mỗi dòng đại diện một đơn”, đã thay đổi độ hạt của kết quả và cần chú ý khi đếm/tổng hợp.

### 5.2. Giữ đơn không có dòng hàng bằng LEFT JOIN

~~~sql
SELECT
    o.order_id,
    oi.product_id,
    oi.quantity
FROM lab_j180_orders AS o
LEFT JOIN lab_j180_order_items AS oi
    ON oi.order_id = o.order_id
ORDER BY o.order_id, oi.product_id;
~~~

Kết quả có **7 dòng**: sáu dòng có sản phẩm và **một dòng cho đơn 1005** với `oi.product_id IS NULL` và `oi.quantity IS NULL`.

Không nên xem một hàng `LEFT JOIN` có cột bên phải `NULL` là một sản phẩm thật. Khi đếm số sản phẩm/dòng hàng, phải chọn biểu thức đếm phù hợp.

## 6. Đi qua bảng trung gian để tới sản phẩm và danh mục

Yêu cầu: “Liệt kê những sản phẩm trong từng đơn, kèm danh mục của sản phẩm”.

Đường nối:

~~~text
orders o
   | o.order_id = oi.order_id
   v
order_items oi
   | oi.product_id = p.product_id
   v
products p
   | p.category_id = cat.category_id
   v
categories cat
~~~

Truy vấn:

~~~sql
SELECT
    o.order_id,
    p.product_name,
    cat.category_name,
    oi.quantity,
    oi.unit_price,
    oi.quantity * oi.unit_price AS line_total
FROM lab_j180_orders AS o
JOIN lab_j180_order_items AS oi
    ON oi.order_id = o.order_id
JOIN lab_j180_products AS p
    ON p.product_id = oi.product_id
JOIN lab_j180_categories AS cat
    ON cat.category_id = p.category_id
ORDER BY o.order_id, p.product_id;
~~~

Kết quả:

| order_id | product_name | category_name | quantity | line_total |
| ---: | --- | --- | ---: | ---: |
| 1001 | So tay | Van phong pham | 2 | 200.00 |
| 1001 | But | Van phong pham | 3 | 60.00 |
| 1002 | Ba lo | Phu kien | 1 | 300.00 |
| 1003 | But | Van phong pham | 5 | 100.00 |
| 1003 | Ba lo | Phu kien | 1 | 300.00 |
| 1004 | So tay | Van phong pham | 1 | 100.00 |

Ở đây `oi.quantity * oi.unit_price` dùng **đơn giá đã lưu trong dòng hàng**, không lấy giá hiện tại từ bảng `products`. Đây là lựa chọn thông dụng cho dữ liệu giao dịch: giá tại thời điểm mua cần được giữ riêng nếu giá niêm yết thay đổi về sau.

### 6.1. Vì sao không nối orders trực tiếp với products bằng các ID giống nhau?

Các cột `orders.order_id` và `products.product_id` đều là số nguyên, nhưng **không đại diện cùng loại đối tượng**. Câu như:

~~~sql
-- SAI ve quan he: cac ID khong phai la khoa lien ket tuong ung.
SELECT o.order_id, p.product_name
FROM lab_j180_orders AS o
JOIN lab_j180_products AS p
    ON o.order_id = p.product_id;
~~~

có thể cho kết quả rỗng trong dữ liệu mẫu, hoặc tình cờ có hàng trùng ID nếu giá trị ngẫu nhiên bằng nhau. Nó **không trả lời** “sản phẩm nào trong đơn nào”. Đường đúng phải qua `order_items` vì bảng trung gian chứa **cả `order_id` và `product_id`**.

## 7. Quan hệ nhiều–nhiều và bảng nối

Một đơn có nhiều sản phẩm; cùng một sản phẩm có thể xuất hiện trong nhiều đơn. Vì vậy, ở mức mô hình nghiệp vụ, `orders` và `products` có quan hệ **N–N** (*many-to-many*).

~~~text
orders 1 ---- N order_items N ---- 1 products
~~~

`order_items` vừa là **bảng liên kết** vừa chứa thuộc tính của mối quan hệ (`quantity`, `unit_price`). Hai khóa ngoại của nó chỉ rõ từng dòng hàng liên quan đến đơn nào và sản phẩm nào.

### 7.1. Tìm khách hàng từng mua sản phẩm nào

Đường nối đi qua cả bảng đơn và bảng dòng hàng:

~~~sql
SELECT DISTINCT
    c.customer_id,
    c.customer_name,
    p.product_name
FROM lab_j180_customers AS c
JOIN lab_j180_orders AS o
    ON o.customer_id = c.customer_id
JOIN lab_j180_order_items AS oi
    ON oi.order_id = o.order_id
JOIN lab_j180_products AS p
    ON p.product_id = oi.product_id
ORDER BY c.customer_id, p.product_name;
~~~

Kết quả có những cặp khách hàng–sản phẩm:

| customer_id | customer_name | product_name |
| ---: | --- | --- |
| 1 | An | Ba lo |
| 1 | An | But |
| 1 | An | So tay |
| 2 | Binh | Ba lo |
| 2 | Binh | But |
| 3 | Chi | So tay |

`DISTINCT` có nghĩa **mỗi cặp giá trị trong danh sách SELECT chỉ hiện một lần**. Nó phù hợp nếu câu hỏi là “khách từng mua những loại sản phẩm nào?”, bất kể mua bao nhiêu lần. Nếu cần thống kê **số lần mua** hoặc **số lượng đã mua**, xóa trùng bằng `DISTINCT` có thể làm mất thông tin và phải chuyển sang cách tổng hợp tương ứng.

### 7.2. Tìm sản phẩm chưa có đơn hàng

Yêu cầu bắt đầu từ **mọi sản phẩm**, kể cả sản phẩm chưa bán. Vì vậy bảng gốc nên là `products` và dùng `LEFT JOIN` sang `order_items`:

~~~sql
SELECT
    p.product_id,
    p.product_name
FROM lab_j180_products AS p
LEFT JOIN lab_j180_order_items AS oi
    ON oi.product_id = p.product_id
WHERE oi.order_id IS NULL
ORDER BY p.product_id;
~~~

Kết quả là **Chuot (ID 504)**. Cột `oi.order_id` thuộc khóa chính ghép nên không thể `NULL` trên một dòng hàng thật; khi `LEFT JOIN` không khớp, nó trở thành `NULL` của phía phải. Dùng cột khóa không-null làm dấu hiệu thiếu hàng giúp tránh nhầm với một thuộc tính khác vốn được phép `NULL`.

Một cách biểu đạt khác là `NOT EXISTS`:

~~~sql
SELECT p.product_id, p.product_name
FROM lab_j180_products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_j180_order_items AS oi
    WHERE oi.product_id = p.product_id
)
ORDER BY p.product_id;
~~~

Hai câu có cùng ý nghĩa trên dữ liệu mẫu. `NOT EXISTS` thường diễn đạt tự nhiên bài toán “không tồn tại bản ghi liên quan”.

## 8. Xác định điểm bắt đầu: báo cáo đơn hàng khác báo cáo khách hàng

Nếu bắt đầu từ `orders`, danh sách **không thể tự sinh khách chưa có đơn**. Muốn thống kê mọi khách hàng, kể cả Dũng chưa mua gì, phải bắt đầu từ `customers`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count
FROM lab_j180_customers AS c
LEFT JOIN lab_j180_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

| customer_id | customer_name | order_count |
| ---: | --- | ---: |
| 1 | An | 2 |
| 2 | Binh | 1 |
| 3 | Chi | 2 |
| 4 | Dung | 0 |

Tại sao dùng `COUNT(o.order_id)` chứ không dùng `COUNT(*)`? Với `LEFT JOIN`, Dũng vẫn có **một hàng kết quả nối** chứa `o.order_id IS NULL`. `COUNT(*)` sẽ đếm hàng này thành 1, còn `COUNT(o.order_id)` bỏ qua `NULL` và cho đúng **0 đơn hàng**.

### 8.1. Nếu nối thêm order_items, số dòng lại thay đổi

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS counted_join_rows,
    COUNT(DISTINCT o.order_id) AS actual_order_count
FROM lab_j180_customers AS c
LEFT JOIN lab_j180_orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN lab_j180_order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

| customer_id | counted_join_rows | actual_order_count |
| ---: | ---: | ---: |
| 1 | 3 | 2 |
| 2 | 2 | 1 |
| 3 | 2 | 2 |
| 4 | 0 | 0 |

Giải thích:

- An có đơn 1001 với **hai dòng hàng** và đơn 1002 với **một dòng**, nên `COUNT(o.order_id) = 3` dù thực tế có **2 đơn**.
- Bình có một đơn 1003 với **hai dòng hàng**, nên `COUNT(o.order_id) = 2` dù thực tế chỉ có **1 đơn**.
- Chi có đơn 1004 với một dòng hàng và đơn 1005 không có hàng: phép `LEFT JOIN` vẫn giữ đơn 1005 một lần, nên hai cách đếm đều cho 2.
- Dũng không có đơn; `o.order_id` là `NULL` nên hai cách đếm đều cho 0.

`COUNT(DISTINCT o.order_id)` có thể sửa **phép đếm đơn** trong kiểu truy vấn này, nhưng không tự sửa được mọi phép tính khác; đặc biệt **`SUM` trên dữ liệu đã bị nhân hàng** có thể vẫn bị sai. Đừng xem `DISTINCT` là thuốc chữa chung cho một đường liên kết thiết kế sai.

## 9. Bẫy nhân hàng khi nối hai quan hệ 1–N độc lập

Đây là vấn đề quan trọng khi ghép **nhiều bảng**. Một đơn có nhiều dòng hàng và cũng có thể có nhiều khoản thanh toán:

~~~text
         order_items (nhieu dong)
                ^
                |
                1
              orders
                1
                |
                v
          payments (nhieu lan)
~~~

Giả sử nối cả hai bảng chi tiết vào cùng bảng đơn:

~~~sql
SELECT
    o.order_id,
    oi.product_id,
    p.payment_id,
    oi.quantity * oi.unit_price AS item_value,
    p.amount AS payment_value
FROM lab_j180_orders AS o
JOIN lab_j180_order_items AS oi
    ON oi.order_id = o.order_id
JOIN lab_j180_payments AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id, oi.product_id, p.payment_id;
~~~

Một phần kết quả:

| order_id | product_id | payment_id | item_value | payment_value |
| ---: | ---: | ---: | ---: | ---: |
| 1001 | 501 | 9001 | 200.00 | 260.00 |
| 1001 | 502 | 9001 | 60.00 | 260.00 |
| 1003 | 502 | 9002 | 100.00 | 200.00 |
| 1003 | 502 | 9003 | 100.00 | 200.00 |
| 1003 | 503 | 9002 | 300.00 | 200.00 |
| 1003 | 503 | 9003 | 300.00 | 200.00 |
| 1004 | 501 | 9004 | 100.00 | 100.00 |

Đơn 1003 có **2 dòng hàng × 2 lần thanh toán = 4 hàng sau JOIN**. Đơn 1001 có **2 dòng hàng × 1 lần thanh toán = 2 hàng**, khiến khoản thanh toán 260 xuất hiện hai lần.

Đây không phải lỗi cú pháp. Cả hai điều kiện `ON` đều nối đúng khóa ngoại; vấn đề nằm ở **độ hạt kết quả thay đổi** khi hai nhánh 1–N độc lập cùng được mở rộng.

### 9.1. Hậu quả khi cộng trực tiếp

Truy vấn sau dễ tạo báo cáo sai:

~~~sql
-- CO THE CONG TRUNG DO NHAN HANG GIUA CHI TIET VA THANH TOAN.
SELECT
    o.order_id,
    SUM(oi.quantity * oi.unit_price) AS item_total_wrong,
    SUM(p.amount) AS paid_total_wrong
FROM lab_j180_orders AS o
JOIN lab_j180_order_items AS oi
    ON oi.order_id = o.order_id
JOIN lab_j180_payments AS p
    ON p.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

| order_id | item_total_wrong | paid_total_wrong |
| ---: | ---: | ---: |
| 1001 | 260.00 | 520.00 |
| 1003 | 800.00 | 800.00 |
| 1004 | 100.00 | 100.00 |

Giá trị đúng phải là:

- Đơn 1001: **tổng dòng hàng 260**, **tổng thanh toán 260**.
- Đơn 1003: **tổng dòng hàng 400**, **tổng thanh toán 400**.
- Đơn 1004: **tổng dòng hàng 100**, **tổng thanh toán 100**.

Với đơn 1001, phần thanh toán bị nhân hai vì có hai dòng hàng; với đơn 1003, **cả hai tổng** đều bị nhân hai.

Lưu ý: `SUM(DISTINCT amount)` **không** là cách sửa đúng ở đây. Đơn 1003 có **hai lần thanh toán khác nhau cùng giá trị 200**; `SUM(DISTINCT p.amount)` sẽ chỉ cộng 200 một lần, làm mất một khoản thanh toán hợp lệ. Phải giải quyết ở **đường nối hoặc độ hạt**, không xóa các giá trị trùng bằng cảm tính.

## 10. Cách an toàn: tổng hợp riêng từng nhánh, rồi nối

Nếu báo cáo yêu cầu **mỗi đơn một dòng** với tổng dòng hàng và tổng thanh toán, trước tiên tạo **một dòng tổng hợp cho mỗi order_id** ở mỗi bảng con.

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total,
        COUNT(*) AS item_line_count
    FROM lab_j180_order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(amount) AS settled_total,
        COUNT(*) AS settled_payment_count
    FROM lab_j180_payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT
    o.order_id,
    c.customer_name,
    COALESCE(it.item_total, 0) AS item_total,
    COALESCE(pt.settled_total, 0) AS settled_total,
    COALESCE(it.item_line_count, 0) AS item_line_count,
    COALESCE(pt.settled_payment_count, 0) AS settled_payment_count
FROM lab_j180_orders AS o
JOIN lab_j180_customers AS c
    ON c.customer_id = o.customer_id
LEFT JOIN item_totals AS it
    ON it.order_id = o.order_id
LEFT JOIN payment_totals AS pt
    ON pt.order_id = o.order_id
ORDER BY o.order_id;
~~~

Kết quả:

| order_id | customer_name | item_total | settled_total | item_line_count | settled_payment_count |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1001 | An | 260.00 | 260.00 | 2 | 1 |
| 1002 | An | 300.00 | 0 | 1 | 0 |
| 1003 | Binh | 400.00 | 400.00 | 2 | 2 |
| 1004 | Chi | 100.00 | 100.00 | 1 | 1 |
| 1005 | Chi | 0 | 0 | 0 | 0 |

Ở truy vấn này:

1. `item_totals` có **tối đa một hàng cho mỗi `order_id`**.
2. `payment_totals` cũng có **tối đa một hàng cho mỗi `order_id`**, sau khi chỉ xét thanh toán `SETTLED`.
3. Nối hai bảng tổng hợp vào `orders` không nhân dòng hàng và khoản thanh toán với nhau nữa.
4. Dùng `LEFT JOIN` để giữ đơn chưa có dòng hàng hoặc thanh toán.
5. `COALESCE(..., 0)` là **quy ước hiển thị/tính toán**: khi không có hàng chi tiết, báo cáo xem tổng bằng 0. Nếu nghiệp vụ phân biệt “chưa có dữ liệu” với “số tiền thật sự bằng 0”, hãy giữ `NULL` hoặc thêm một cột trạng thái.

Sơ đồ độ hạt:

~~~text
order_items (6 dong)  --> GROUP BY order_id --> item_totals (4 don)
                                                        |
                                                        v
orders (5 don) ----------------------------------> 1 dong / don
                                                        ^
                                                        |
payments (4 lan) -----> GROUP BY order_id --> payment_totals (3 don)
~~~

Mô hình này áp dụng được cho những tình huống có hai hoặc nhiều nhánh chi tiết độc lập: đơn hàng–dòng hàng–thanh toán; học sinh–điểm–điểm danh; dự án–công việc–lần ghi công; khách hàng–giao dịch–liên hệ.

### 10.1. Vì sao không nhóm trực tiếp tất cả bảng rồi mong GROUP BY sửa được?

`GROUP BY o.order_id` sau khi đã JOIN hai bảng 1–N chỉ gom **những hàng đã bị nhân bản** vào một nhóm. Hàm `SUM` vẫn nhìn thấy các giá trị bị lặp. `GROUP BY` **không tự loại trùng ngữ nghĩa** của từng bản ghi chi tiết.

Cần trả lời: “Mỗi nhánh đang có **mấy dòng cho một khóa gốc**?” Nếu cả hai nhánh có nhiều dòng, hãy tổng hợp chúng riêng hoặc thiết kế phép nối trên đúng đơn vị dữ liệu cần đếm trước khi thực hiện phép tính cuối.

## 11. INNER JOIN, LEFT JOIN và vị trí điều kiện lọc

### 11.1. INNER JOIN chỉ giữ hàng có đối tác khớp

Yêu cầu “những khách hàng có đơn”, có thể dùng:

~~~sql
SELECT DISTINCT
    c.customer_id,
    c.customer_name
FROM lab_j180_customers AS c
JOIN lab_j180_orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

Kết quả là **An, Bình, Chi**. Dũng không có đơn nên bị loại.

Khi câu hỏi là “khách hàng **có ít nhất một** đơn”, `EXISTS` cũng là cách biểu đạt trực tiếp mà không tạo ra một hàng cho mỗi đơn:

~~~sql
SELECT c.customer_id, c.customer_name
FROM lab_j180_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_j180_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Hai cách trên cùng trả ba khách hàng trong dữ liệu mẫu.

### 11.2. LEFT JOIN giữ bảng gốc dù thiếu đối tác

Yêu cầu “tất cả khách hàng và mã đơn nếu có”:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM lab_j180_customers AS c
LEFT JOIN lab_j180_orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

Dũng xuất hiện **một lần với `o.order_id IS NULL`**. An và Chi xuất hiện hai lần vì có hai đơn; Bình một lần. Vì thế truy vấn trả **6 dòng** cho **4 khách hàng**.

`LEFT JOIN` không có nghĩa kết quả luôn đúng một hàng cho mỗi hàng bên trái; nếu phía phải có nhiều đối tác thì bên trái vẫn được lặp theo số đối tác.

### 11.3. Đặt điều kiện ở ON hay WHERE có thể đổi kết quả

Yêu cầu “mọi khách hàng, đếm số **đơn PAID** của từng người”:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count
FROM lab_j180_customers AS c
LEFT JOIN lab_j180_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Kết quả:

| customer_id | customer_name | paid_order_count |
| ---: | --- | ---: |
| 1 | An | 1 |
| 2 | Binh | 1 |
| 3 | Chi | 1 |
| 4 | Dung | 0 |

Nếu chuyển điều kiện `o.order_status = 'PAID'` xuống `WHERE`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count
FROM lab_j180_customers AS c
LEFT JOIN lab_j180_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Dũng **biến mất**, vì hàng không khớp có `o.order_status IS NULL`, khiến điều kiện `WHERE` không phải TRUE. Với yêu cầu giữ mọi khách, điều kiện về đơn PAID nên nằm ở `ON` hoặc trong một phép tổng hợp có điều kiện thích hợp.

## 12. Một đích dữ liệu có thể có nhiều đường liên kết

Trong mô hình lớn, có thể có **nhiều đường đi hợp lệ về mặt khóa** nhưng khác **ý nghĩa nghiệp vụ**. Ví dụ giả định một bảng `tickets` có hai khóa ngoại tới `employees`:

~~~text
tickets.created_by_employee_id --> employees.employee_id
tickets.assigned_to_employee_id --> employees.employee_id
~~~

Nếu muốn biết **người tạo** và **người phụ trách** một phiếu, phải tham chiếu bảng nhân viên qua **hai vai trò khác nhau**:

~~~sql
-- Vi du cau truc, khong chay neu chua co bang tickets/employees.
SELECT
    t.ticket_id,
    creator.employee_name AS creator_name,
    assignee.employee_name AS assignee_name
FROM tickets AS t
JOIN employees AS creator
    ON creator.employee_id = t.created_by_employee_id
LEFT JOIN employees AS assignee
    ON assignee.employee_id = t.assigned_to_employee_id;
~~~

Đoạn trên chỉ minh họa mô hình, **không thuộc bộ dữ liệu `lab_j180_*`**. Nó cho thấy cùng một bảng đích có thể được nối hai lần qua hai **khóa ngoại khác nhau**, và không được hoán đổi vai trò “người tạo” với “người được giao”.

Tương tự, hệ thống thương mại có thể có `billing_address_id` và `shipping_address_id`, đều tham chiếu một bảng địa chỉ. Một công cụ tự động gợi ý đường liên kết không thể biết bạn muốn **địa chỉ thanh toán** hay **địa chỉ giao hàng** nếu yêu cầu không làm rõ.

Quy trình tốt là ghi rõ **vai trò quan hệ** trong yêu cầu trước khi viết `JOIN`. Một đường liên kết “đúng khóa” vẫn có thể **sai mục tiêu nghiệp vụ**.

## 13. Khi khóa ngoại không được khai báo hoặc dữ liệu thiếu nhất quán

Khóa ngoại là bằng chứng tốt về quan hệ, nhưng không phải database nào cũng khai báo đầy đủ chúng. Hệ thống cũ hoặc hệ thống dữ liệu phân tích có thể chỉ có các cột tham chiếu **theo quy ước**.

Trước khi tự quyết định phép nối, hãy xác định:

1. **Định danh nghiệp vụ:** cột nào đại diện cho cùng đối tượng? `customer_id` trong hai bảng có chung hệ định danh hay là ID cục bộ khác nhau?
2. **Tính duy nhất:** cột đích có `PRIMARY KEY`/`UNIQUE` hoặc thật sự duy nhất theo quy tắc đã xác minh không?
3. **Khả năng thiếu quan hệ:** khóa nguồn có thể `NULL` hoặc trỏ tới hàng đã bị xóa không?
4. **Phạm vi khóa:** cột chỉ duy nhất **bên trong một công ty/tenant** hay duy nhất toàn database? Nếu khóa ghép là `(tenant_id, customer_id)`, chỉ nối bằng `customer_id` sẽ ghép nhầm giữa các tenant.
5. **Ý nghĩa thời gian:** dữ liệu là lịch sử tại ngày giao dịch hay trạng thái hiện hành? Kết nối với bảng giá hiện tại có thể làm sai báo cáo quá khứ.

### 13.1. Ví dụ khóa ghép không thể rút gọn

Giả sử mỗi tenant có các khách hàng `customer_id` bắt đầu lại từ 1:

~~~sql
-- Vi du minh hoa tren hai bang gia dinh.
SELECT
    o.tenant_id,
    o.order_id,
    c.customer_name
FROM tenant_orders AS o
JOIN tenant_customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id;
~~~

Nếu bỏ `c.tenant_id = o.tenant_id`, một đơn thuộc tenant A có thể ghép với khách ID trùng ở tenant B. Việc nhiều hàng được trả về không phải luôn biểu thị “khách có nhiều đơn”; đôi khi là dấu hiệu **đường nối thiếu một phần khóa**.

### 13.2. Kiểm tra metadata khóa ngoại ở PostgreSQL

Có thể xem các quan hệ được khai báo bằng một truy vấn metadata (ví dụ dưới dành cho các **khóa ngoại một cột** trong bộ dữ liệu mẫu):

~~~sql
SELECT
    tc.table_name AS child_table,
    kcu.column_name AS child_column,
    ccu.table_name AS parent_table,
    ccu.column_name AS parent_column
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON kcu.constraint_catalog = tc.constraint_catalog
   AND kcu.constraint_schema = tc.constraint_schema
   AND kcu.constraint_name = tc.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_catalog = tc.constraint_catalog
   AND ccu.constraint_schema = tc.constraint_schema
   AND ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = current_schema()
  AND tc.table_name IN (
      'lab_j180_orders',
      'lab_j180_employees',
      'lab_j180_products',
      'lab_j180_order_items',
      'lab_j180_payments'
  )
ORDER BY tc.table_name, kcu.column_name;
~~~

Với các bảng trong schema hiện tại được tạo theo mục 2, kết quả sẽ giúp thấy những cặp bảng và cột được khóa ngoại liên kết. `information_schema` còn phụ thuộc quyền truy cập của tài khoản. **Với khóa ngoại ghép nhiều cột**, cần đối chiếu đúng thứ tự từng cặp cột (hoặc dùng catalog của hệ quản trị); truy vấn minh họa trên không phải bản đồ FK ghép tổng quát.

Nếu bảng thực hành được tạo trong một schema khác với `current_schema()`, hãy thay điều kiện schema bằng tên thực tế. Lệnh `\d ten_bang` trong `psql` cũng có thể hiển thị ràng buộc, nhưng đó là **meta-command của `psql`**, không phải SQL chạy trong mọi trình quản lý database.

## 14. Chẩn đoán đường liên kết theo từng bước

Khi một câu `JOIN` nhiều bảng cho quá nhiều hoặc quá ít hàng, cách hiệu quả là **giữ nguyên câu hỏi nghiệp vụ rồi kiểm tra từng chặng**.

### Bước 1 — Xác nhận số hàng và khóa của bảng gốc

~~~sql
SELECT COUNT(*) AS order_count
FROM lab_j180_orders;
~~~

Kết quả **5**.

### Bước 2 — Nối một bảng N–1, kiểm tra số hàng

~~~sql
SELECT COUNT(*) AS joined_rows
FROM lab_j180_orders AS o
JOIN lab_j180_customers AS c
    ON c.customer_id = o.customer_id;
~~~

Kết quả vẫn **5** vì mỗi đơn có đúng một khách hiện hữu.

### Bước 3 — Mở rộng nhánh 1–N và kiểm tra độ hạt

~~~sql
SELECT
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT o.order_id) AS distinct_orders
FROM lab_j180_orders AS o
LEFT JOIN lab_j180_order_items AS oi
    ON oi.order_id = o.order_id;
~~~

Kết quả là **7 hàng sau JOIN**, nhưng chỉ **5 đơn phân biệt**.

### Bước 4 — Tìm khóa bị lặp trong tập kết quả

~~~sql
SELECT
    o.order_id,
    COUNT(*) AS joined_row_count
FROM lab_j180_orders AS o
LEFT JOIN lab_j180_order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

| order_id | joined_row_count |
| ---: | ---: |
| 1001 | 2 |
| 1002 | 1 |
| 1003 | 2 |
| 1004 | 1 |
| 1005 | 1 |

`COUNT(*) = 1` đối với đơn 1005 **không có nghĩa đơn đó có một sản phẩm**: đây là hàng giữ lại bởi `LEFT JOIN`. Muốn đếm dòng hàng thật, dùng `COUNT(oi.product_id)`.

### Bước 5 — Xem đúng từng cặp khóa nối

Trong `ON`, kiểm tra:

- Các cột có thuộc **đúng hai vai trò bảng**?
- Có đủ các cột của **khóa ghép** không?
- Có đang nối bằng **ID kỹ thuật** đúng nghĩa thay vì tên, ngày hoặc mô tả tình cờ giống nhau?
- Có đang áp dụng `WHERE` làm mất các dòng `NULL` từ `LEFT JOIN` không?
- Có vô tình nối hai nhánh 1–N vào cùng bảng gốc rồi cộng tiền trên tập đã nhân không?

Đừng sửa ngay bằng `SELECT DISTINCT *` khi kết quả có nhiều hàng. Trước tiên cần biết nhiều hàng là **đúng độ hạt** hay là một **sai lệch quan hệ**.

## 15. Hiệu năng: tối ưu JOIN sau khi đã đúng ngữ nghĩa

Khi đường liên kết đã được xác định đúng, bước tiếp theo mới là kiểm tra hiệu năng. Một vài nguyên tắc:

- Nối qua **khóa chính/khóa duy nhất** ở phía đích giúp đảm bảo tối đa một hàng cho mỗi khóa và thường có chỉ mục phục vụ tra cứu.
- Cột **khóa ngoại ở bảng con** không phải luôn được tạo chỉ mục tự động. PostgreSQL tự tạo chỉ mục cho `PRIMARY KEY`/`UNIQUE` nhưng **không tự tạo chỉ mục cho mọi khóa ngoại**.
- Khi lọc theo trạng thái hoặc ngày, chỉ mục phù hợp có thể giúp giảm dữ liệu phải đọc. Tuy nhiên, cần dựa vào khối lượng và phân bố dữ liệu, không lập mọi chỉ mục theo cảm tính.
- Bộ tối ưu SQL có thể thay đổi **thứ tự thực thi vật lý** của một số phép `INNER JOIN`. Thứ tự viết trong `FROM` mô tả quan hệ logic, không luôn là thứ tự quét bảng thực tế.
- Với `OUTER JOIN`, việc đổi thứ tự hoặc vị trí điều kiện có thể thay đổi ngữ nghĩa; không được tự ý biến nó thành `INNER JOIN` chỉ vì có thể nhanh hơn.

Trong PostgreSQL, có thể xem kế hoạch:

~~~sql
EXPLAIN
SELECT
    o.order_id,
    c.customer_name,
    e.employee_name
FROM lab_j180_orders AS o
JOIN lab_j180_customers AS c
    ON c.customer_id = o.customer_id
LEFT JOIN lab_j180_employees AS e
    ON e.employee_id = o.employee_id;
~~~

`EXPLAIN` cho biết phương thức truy cập và nối dự kiến như nested loop, hash join hoặc merge join tùy kế hoạch. Trên bộ dữ liệu chỉ vài hàng, quét bảng thường đủ nhanh; không nên suy luận cấu trúc chỉ mục tối ưu cho hệ thống sản xuất từ kết quả thử trên bảng nhỏ.

Ví dụ DDL sau **có thể** hữu ích cho một số truy vấn có cột khóa ngoại ở phía con, nhưng là thao tác thật nếu chạy:

~~~sql
CREATE INDEX lab_j180_orders_customer_idx
ON lab_j180_orders (customer_id);

CREATE INDEX lab_j180_order_items_product_idx
ON lab_j180_order_items (product_id);

CREATE INDEX lab_j180_payments_order_idx
ON lab_j180_payments (order_id);
~~~

Khóa chính ghép `(order_id, product_id)` của `order_items` đã có chỉ mục theo thứ tự khóa đó. Một chỉ mục bổ sung bắt đầu bằng `product_id` có thể phù hợp khi thường xuyên tìm các dòng hàng theo sản phẩm. Mỗi chỉ mục tăng chi phí lưu trữ và ghi dữ liệu; cần cân nhắc với tải thực tế.

## 16. Cú pháp JOIN trong các hệ quản trị SQL

Các hệ quản trị quan hệ phổ biến đều hỗ trợ `INNER JOIN` và `LEFT JOIN`, nhưng có một số khác biệt:

| Vấn đề | PostgreSQL | Các hệ khác |
| --- | --- | --- |
| Nối trong nhiều bảng | `JOIN ... ON ... JOIN ... ON ...` | Tương tự trong MySQL, SQL Server, SQLite, Oracle |
| `INNER JOIN` | Chỉ giữ cặp hàng khớp | Phổ biến, `INNER` thường có thể bỏ |
| `LEFT JOIN` | Giữ mọi hàng phía trái | Phổ biến |
| `RIGHT JOIN` / `FULL OUTER JOIN` | Có hỗ trợ | MySQL không hỗ trợ `FULL OUTER JOIN` trực tiếp; hỗ trợ tùy hệ/phiên bản ở nơi khác |
| `CROSS JOIN` | Tạo tích Descartes | Có ở nhiều hệ; cần chủ ý dùng |
| `USING (column_name)` | Hợp lệ nếu tên cột trùng ở hai phía | Có ở PostgreSQL/MySQL/SQLite và một số hệ; không được hỗ trợ tương tự trong SQL Server |
| `NATURAL JOIN` | Tự nối theo tất cả tên cột chung | Cú pháp có ở một số hệ nhưng dễ đổi nghĩa khi schema thêm cột |
| `LIMIT`, `TOP`, `FETCH` | PostgreSQL thường dùng `LIMIT`/`FETCH` | Chọn cú pháp phân trang theo hệ |

Ví dụ `USING` trên PostgreSQL khi hai bảng có chung tên cột `customer_id`:

~~~sql
SELECT o.order_id, c.customer_name
FROM lab_j180_orders AS o
JOIN lab_j180_customers AS c
    USING (customer_id)
ORDER BY o.order_id;
~~~

`USING (customer_id)` có ý nghĩa nối khi `o.customer_id = c.customer_id`. Nó có thể giúp viết ngắn khi tên cột hai bên giống nhau và quan hệ đúng rõ ràng, nhưng **`ON` thường dễ đọc hơn** trong truy vấn phức tạp, nhất là khi hai bên dùng tên cột khác nhau hoặc khóa ghép.

### Cẩn thận với JOIN không có điều kiện

~~~sql
-- Tich Descartes: moi khach hang ket hop moi san pham.
SELECT c.customer_name, p.product_name
FROM lab_j180_customers AS c
CROSS JOIN lab_j180_products AS p;
~~~

Bộ dữ liệu có 4 khách và 4 sản phẩm nên câu này trả **16 tổ hợp**. `CROSS JOIN` có thể hữu ích khi cần liệt kê mọi tổ hợp giả định; nhưng **không** có nghĩa khách nào đã mua sản phẩm nào. Để trả lời câu hỏi mua hàng, phải đi qua `orders` và `order_items` như mục 7.

Một `JOIN` thiếu điều kiện quan hệ, điều kiện luôn TRUE hoặc nối bằng cột không duy nhất có thể dẫn đến số hàng tăng rất mạnh. Với bảng lớn, đây vừa là lỗi báo cáo vừa là rủi ro hiệu năng.

## 17. Những lỗi thường gặp khi xác định đường liên kết

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Đơn hàng và sản phẩm được nối trực tiếp bằng `order_id = product_id` | Hai ID khác loại đối tượng, không có quan hệ nghiệp vụ | Đi qua `order_items` |
| Một đơn xuất hiện nhiều lần trong kết quả | Đã nối với bảng chi tiết 1–N | Xác định độ hạt, dùng tổng hợp hoặc đổi cấu trúc báo cáo nếu cần một hàng/đơn |
| `SUM` dòng hàng và thanh toán bị nhân đôi | Nối đồng thời hai nhánh 1–N | Tổng hợp mỗi nhánh theo `order_id` trước, rồi nối |
| `COUNT(o.order_id)` lớn hơn số đơn sau khi nối dòng hàng | Mỗi đơn bị lặp theo số dòng hàng | `COUNT(DISTINCT o.order_id)` cho đếm đơn hoặc tổng hợp trước |
| `COUNT(*)` trả 1 cho khách không có đơn trong `LEFT JOIN` | Hàng phía trái vẫn được giữ lại với cột phía phải NULL | Đếm cột khóa bên phải, ví dụ `COUNT(o.order_id)` |
| Khách chưa có đơn biến mất | Bắt đầu từ `orders` hoặc dùng `INNER JOIN` | Bắt đầu từ `customers` và dùng `LEFT JOIN` khi yêu cầu giữ mọi khách |
| Đơn chưa có nhân viên biến mất khi nối phòng ban | Sau `LEFT JOIN employees` lại dùng `INNER JOIN departments` | Giữ nhánh tùy chọn bằng `LEFT JOIN` tới phòng ban |
| `LEFT JOIN` trở thành bộ lọc gần giống `INNER JOIN` | Điều kiện ở bảng phải đặt trong `WHERE` | Xem lại điều kiện `ON` và mục tiêu giữ hàng |
| Các hàng ở hai tenant ghép nhầm nhau | Điều kiện thiếu thành phần `tenant_id` của khóa ghép | Nối trên toàn bộ khóa quan hệ |
| Nhầm người tạo và người được giao | Có hai khóa ngoại tới cùng một bảng | Dùng hai bí danh và nối qua đúng FK cho từng vai trò |
| `SELECT DISTINCT` làm mất dữ liệu cần đếm | Loại trùng ở tầng trình bày, che dấu bội số quan hệ | Xác định độ hạt và tổng hợp đúng khóa |
| Thứ tự kết quả thay đổi không dự đoán | SQL không hứa thứ tự hàng khi không `ORDER BY` | Thêm `ORDER BY` phù hợp |

## 18. Bài tập thực hành và đáp án

Các bài dùng nguyên các bảng `lab_j180_*` ở mục 2. Trước khi viết `JOIN`, hãy ghi rõ **mỗi dòng đầu ra đại diện cho gì** và phác ra **đường qua các bảng**.

### Bài 1 — Ba bảng theo một đường liên kết

**Yêu cầu:** lấy mã đơn, tên khách hàng và tên nhân viên của các đơn **đã có nhân viên**. Mỗi đơn một dòng, ID tăng dần.

**Đáp án:**

~~~sql
SELECT
    o.order_id,
    c.customer_name,
    e.employee_name
FROM lab_j180_orders AS o
JOIN lab_j180_customers AS c
    ON c.customer_id = o.customer_id
JOIN lab_j180_employees AS e
    ON e.employee_id = o.employee_id
ORDER BY o.order_id;
~~~

Đường đi `customers ← orders → employees`. Kết quả các đơn **1001, 1002, 1003, 1004**; đơn 1005 chưa có nhân viên nên bị loại.

### Bài 2 — Giữ đơn chưa phân công

**Yêu cầu:** liệt kê **mọi đơn**, kèm tên nhân viên và phòng ban nếu có.

**Đáp án:**

~~~sql
SELECT
    o.order_id,
    e.employee_name,
    d.department_name
FROM lab_j180_orders AS o
LEFT JOIN lab_j180_employees AS e
    ON e.employee_id = o.employee_id
LEFT JOIN lab_j180_departments AS d
    ON d.department_id = e.department_id
ORDER BY o.order_id;
~~~

Đơn **1005** vẫn xuất hiện với hai giá trị `NULL`. Nếu thay phép nối thứ hai thành `INNER JOIN`, đơn này sẽ biến mất.

### Bài 3 — Đường nối tới danh mục sản phẩm

**Yêu cầu:** hiển thị mã đơn, tên sản phẩm và tên danh mục. Mỗi dòng kết quả đại diện một dòng hàng của đơn.

**Đáp án:**

~~~sql
SELECT
    oi.order_id,
    p.product_name,
    cat.category_name
FROM lab_j180_order_items AS oi
JOIN lab_j180_products AS p
    ON p.product_id = oi.product_id
JOIN lab_j180_categories AS cat
    ON cat.category_id = p.category_id
ORDER BY oi.order_id, p.product_id;
~~~

Kết quả có **6 dòng** theo số dòng hàng. Đường nối `order_items → products → categories` đã đủ vì câu hỏi không cần thông tin của bảng `orders`; không phải cứ có thể nối thêm bảng thì phải nối.

### Bài 4 — Đếm đơn của mọi khách, kể cả người chưa mua

**Đáp án:**

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count
FROM lab_j180_customers AS c
LEFT JOIN lab_j180_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Kết quả: **An 2, Bình 1, Chi 2, Dũng 0**. Bắt đầu từ bảng `customers` để không làm mất người chưa có đơn.

### Bài 5 — Vì sao đếm bị tăng sau JOIN?

Cho truy vấn:

~~~sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count
FROM lab_j180_customers AS c
JOIN lab_j180_orders AS o
    ON o.customer_id = c.customer_id
JOIN lab_j180_order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

**Câu hỏi:** An thực tế có 2 đơn nhưng vì sao `order_count` thành 3? Sửa thế nào nếu cần đếm đơn?

**Đáp án:** đơn 1001 của An có 2 dòng hàng, đơn 1002 có 1 dòng; mỗi dòng của kết quả `JOIN` đóng góp một lần cho `COUNT(o.order_id)`. Trong phép nối này có thể dùng `COUNT(DISTINCT o.order_id)` để đếm đơn phân biệt. Nếu còn cần giữ khách chưa mua, chuyển bảng gốc thành `customers` với `LEFT JOIN` thích hợp.

### Bài 6 — Tính giá trị đơn hàng mà không nhân thanh toán

**Yêu cầu:** một dòng trên mỗi đơn, tổng giá trị dòng hàng và tổng số tiền đã thanh toán. Đơn không có chi tiết/thanh toán vẫn được giữ.

**Đáp án:**

~~~sql
WITH items AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM lab_j180_order_items
    GROUP BY order_id
),
paid AS (
    SELECT
        order_id,
        SUM(amount) AS paid_total
    FROM lab_j180_payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.item_total, 0) AS item_total,
    COALESCE(p.paid_total, 0) AS paid_total
FROM lab_j180_orders AS o
LEFT JOIN items AS i
    ON i.order_id = o.order_id
LEFT JOIN paid AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id;
~~~

Hai tập `items` và `paid` đều có **một hàng trên mỗi đơn** sau khi tổng hợp, nên không sinh phép nhân chéo các chi tiết. Các cặp tổng theo đơn 1001–1005 là **(260,260), (300,0), (400,400), (100,100), (0,0)**.

### Bài 7 — Tìm sản phẩm chưa từng xuất hiện trong đơn

**Đáp án:**

~~~sql
SELECT p.product_id, p.product_name
FROM lab_j180_products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_j180_order_items AS oi
    WHERE oi.product_id = p.product_id
)
ORDER BY p.product_id;
~~~

Kết quả **504 – Chuot**. Nếu dùng `INNER JOIN` từ `products` sang `order_items`, sản phẩm chưa bán sẽ không có dòng khớp và không thể xuất hiện trong tập kết quả.

### Bài 8 — Tổng hợp theo phòng ban nhân viên xử lý

**Yêu cầu:** đếm số đơn được giao cho từng phòng ban, chỉ xét đơn có nhân viên. Đừng đếm dòng sản phẩm.

**Đáp án:**

~~~sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(o.order_id) AS assigned_orders
FROM lab_j180_departments AS d
LEFT JOIN lab_j180_employees AS e
    ON e.department_id = d.department_id
LEFT JOIN lab_j180_orders AS o
    ON o.employee_id = e.employee_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
~~~

Kết quả: **Retail 1, Online 3, Logistics 0**. Mỗi đơn nối tới tối đa một nhân viên và mỗi nhân viên thuộc một phòng ban, nên ở đây `COUNT(o.order_id)` đếm số đơn được giao mà không bị nhân dòng hàng.

### Bài 9 — Đường liên kết và điều kiện LEFT JOIN

**Yêu cầu:** thống kê **mọi khách hàng** và số đơn `PAID`, kể cả người chỉ có đơn NEW hoặc chưa có đơn.

**Đáp án:**

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_count
FROM lab_j180_customers AS c
LEFT JOIN lab_j180_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Kết quả **An 1, Bình 1, Chi 1, Dũng 0**. Điều kiện trạng thái đặt trong `ON` giúp giữ hàng khách hàng ngay cả khi không có đơn PAID để nối.

### Bài 10 — Nhận diện JOIN sai đường

Một người viết:

~~~sql
SELECT o.order_id, cat.category_name
FROM lab_j180_orders AS o
JOIN lab_j180_categories AS cat
    ON o.order_id = cat.category_id;
~~~

**Câu hỏi:** vấn đề là gì và muốn lấy danh mục của từng dòng hàng cần sửa ra sao?

**Đáp án:** `order_id` và `category_id` không phải hai khóa liên kết; dù tình cờ bằng số nhau cũng không chứng minh một đơn thuộc danh mục đó. Đi đúng đường **orders → order_items → products → categories**:

~~~sql
SELECT
    o.order_id,
    cat.category_name
FROM lab_j180_orders AS o
JOIN lab_j180_order_items AS oi
    ON oi.order_id = o.order_id
JOIN lab_j180_products AS p
    ON p.product_id = oi.product_id
JOIN lab_j180_categories AS cat
    ON cat.category_id = p.category_id
ORDER BY o.order_id, cat.category_name;
~~~

Đơn 1001 có hai dòng hàng đều thuộc `Van phong pham`, nên tên danh mục xuất hiện **hai lần**. Nếu yêu cầu là “danh mục **phân biệt** của từng đơn”, có thể dùng `SELECT DISTINCT o.order_id, cat.category_name`; còn nếu muốn **số dòng hàng theo danh mục**, phải `GROUP BY` và đếm/tổng hợp có chủ đích.

## 19. Ghi nhớ khi ghép nhiều bảng

- **Xác định độ hạt trước:** một dòng là một đơn, một khách, một sản phẩm của đơn hay một khoản thanh toán?
- **Vẽ đường liên kết qua khóa thật:** có thể cần đi qua nhiều bảng trung gian; không nối hai ID chỉ vì cùng là số.
- **Đọc bội số quan hệ 1–1, N–1, 1–N, N–N:** một `JOIN` đúng vẫn có thể làm tăng số hàng.
- **Chọn `INNER JOIN` hay `LEFT JOIN` theo yêu cầu giữ hàng:** nếu dữ liệu tùy chọn, cần nghĩ cả những bước nối tiếp theo và vị trí điều kiện `ON`/`WHERE`.
- **Đặc biệt cảnh giác khi nối hai nhánh 1–N độc lập:** số dòng bị nhân khiến các phép `SUM`/`COUNT` dễ sai. Tổng hợp từng nhánh về cùng độ hạt rồi nối khi cần một hàng trên mỗi đối tượng.
- **Kiểm tra khóa ghép, vai trò quan hệ và dữ liệu thiếu:** đường nối có thể đúng về cú pháp nhưng sai tenant, sai người phụ trách, sai giá lịch sử hoặc sai ý nghĩa nghiệp vụ.
- **Kiểm tra số hàng theo từng chặng và viết `ORDER BY` khi cần thứ tự ổn định.** Không dùng `DISTINCT` để che một lỗi liên kết chưa hiểu.

Trước khi gửi một truy vấn nhiều bảng, hãy tự hỏi ba câu: **“Tôi muốn một dòng đại diện cho gì? Tôi đang đi qua những khóa nào để tới dữ liệu cần lấy? Mỗi nhánh có thể tạo bao nhiêu hàng cho một khóa gốc?”** Trả lời rõ ba câu này giúp bạn chọn được đường liên kết đúng, tránh nhân bản dữ liệu và tạo báo cáo đáng tin cậy.
