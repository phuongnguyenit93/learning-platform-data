# Tạo, nạp và đặt lại dữ liệu mẫu có thể tái lập

Khi học SQL, bạn thường tạo vài bảng, thêm dữ liệu rồi thử các câu lệnh `SELECT`, `JOIN`, `UPDATE` hay `DELETE`. Sau nhiều lần thử, trạng thái các bảng đã thay đổi: có bản ghi bị xóa, một giá trị đã sửa, hoặc một đơn hàng được thêm vào. Lần sau chạy cùng một truy vấn, kết quả có thể khác dù câu SQL không sai.

Để học và kiểm thử hiệu quả, ta cần **dữ liệu mẫu có thể tái lập** (*reproducible seed data*): từ một môi trường thực hành được quy định, mỗi lần khởi tạo hoặc đặt lại đều tạo ra **cùng cấu trúc bảng, cùng các bản ghi và cùng kết quả mong đợi**. Nhờ đó, người học và người hướng dẫn có một điểm xuất phát chung để làm bài, so sánh kết quả và tái hiện lỗi.

Bài này xây dựng quy trình thực hành hoàn chỉnh trên **PostgreSQL**, sử dụng công cụ dòng lệnh **`psql`**. Ý tưởng có thể áp dụng cho các RDBMS khác, nhưng cú pháp giao dịch, lệnh nạp tệp và cách xóa dữ liệu có thể khác nhau.

## 1. Hiểu đúng về dữ liệu mẫu có thể tái lập

Một bộ dữ liệu thực hành ổn định cần bốn thành phần:

| Thành phần | Vai trò | Ví dụ trong bài |
|---|---|---|
| **Schema** | Quy định bảng, cột, khóa và ràng buộc | `customers`, `products`, `orders`, `order_items` |
| **Seed data** | Xác định những bản ghi được nạp ban đầu | Khách 1 là An; đơn 1002 có trạng thái `NEW` |
| **Reset** | Khôi phục môi trường sau khi dữ liệu bị thay đổi | Xóa đúng các bảng thực hành rồi tạo và nạp lại |
| **Verification** | Phát hiện khi trạng thái thực tế sai kỳ vọng | 3 khách, 3 đơn, tổng đơn đã thanh toán 450.000 |

**Tái lập** ở đây là tái lập *trạng thái logic* của dữ liệu, không yêu cầu các tệp vật lý của cơ sở dữ liệu phải giống nhau từng byte. Với cùng bộ script, người dùng phải nhận được cùng giá trị, khóa, quan hệ và kết quả của các truy vấn đã xác định.

Phân biệt ba việc dễ nhầm:

- **Seed lần đầu:** đưa dữ liệu vào các bảng đang trống.
- **Seed chạy lại không gây lỗi:** có thể dùng kỹ thuật như `INSERT ... ON CONFLICT DO NOTHING` để tránh trùng khóa; tuy nhiên cách này không tự sửa giá trị đã bị thay đổi, cũng không xóa hàng thừa.
- **Reset về trạng thái chuẩn:** xóa trạng thái cũ trong phạm vi thực hành, tái tạo schema và nạp toàn bộ dữ liệu mẫu để trở về điểm xuất phát xác định.

Chẳng hạn, nếu ai đó sửa giá sản phẩm từ 150.000 thành 1 đồng, chạy lại một `INSERT ... ON CONFLICT DO NOTHING` vẫn có thể giữ nguyên giá sai. Với bài tập cần dữ liệu chuẩn, reset rõ ràng và có bước kiểm tra đáng tin cậy hơn.

## 2. Chọn mô hình dữ liệu cho bài thực hành

Ta dùng cửa hàng nhỏ gồm bốn bảng:

```text
customers (khách hàng)               products (sản phẩm)
  customer_id PK                        product_id PK
       |                                     |
       | 1                                   | 1
       |                                     |
       | N                                   | N
   orders (đơn hàng) 1 --- N order_items (chi tiết đơn)
     order_id PK               PK: (order_id, product_id)
     customer_id FK            order_id FK, product_id FK
```

Một khách có thể có nhiều đơn. Mỗi đơn có nhiều dòng chi tiết; mỗi chi tiết chỉ một sản phẩm với số lượng và **đơn giá tại thời điểm mua**. Ta cần những dữ liệu cố định sau:

| Bảng | Số hàng ban đầu | Nội dung chính |
|---|---:|---|
| `customers` | 3 | An, Binh, Chi |
| `products` | 3 | Sách SQL, bàn phím, sổ tay |
| `orders` | 3 | Hai đơn `PAID`, một đơn `NEW` |
| `order_items` | 5 | Các sản phẩm được mua trong từng đơn |

Chọn **ID cố định**, **ngày cố định**, **số tiền chính xác** và một số trường hợp có ý nghĩa để luyện truy vấn. Ta tránh `NOW()`, `CURRENT_DATE`, `RANDOM()` hoặc dữ liệu lấy từ dịch vụ bên ngoài vì chúng có thể khiến kết quả thay đổi theo thời điểm hay môi trường.

## 3. Chuẩn bị PostgreSQL và cấu trúc tệp

Cần một PostgreSQL đang chạy cùng chương trình dòng lệnh `psql`. Người dùng phải có quyền tạo cơ sở dữ liệu hoặc được cấp sẵn database thực hành. Ví dụ dùng tên **`sql_practice`** để tránh nhầm với dữ liệu làm việc. **Mọi lệnh xóa bảng trong bài chỉ được chạy trên database thực hành riêng.**

Nếu bạn có quyền tạo database và các công cụ PostgreSQL đã nằm trong `PATH`, chạy **một lần**:

```bash
createdb sql_practice
```

Nếu cần tài khoản, host cụ thể, ví dụ:

```bash
createdb -h localhost -U postgres sql_practice
```

Thông tin tài khoản, mật khẩu và phương thức kết nối tùy bản cài đặt; đừng chạy lại `createdb` khi database đã tồn tại. Kiểm tra kết nối:

```bash
psql -X -d sql_practice -c "SELECT current_database(), current_user;"
```

Tạo thư mục dự án học tập như sau:

```text
sql-lab/
└── sql/
    ├── schema.sql    # Tạo bảng và ràng buộc
    ├── seed.sql      # Nạp dữ liệu mẫu cố định
    ├── verify.sql    # Kiểm tra dữ liệu chuẩn
    └── reset.sql     # Điều phối quy trình đặt lại
```

Bốn khối script bên dưới là **nội dung đầy đủ** của từng tệp. Lưu tệp UTF-8 với đúng tên. Các lệnh thực thi `-f sql/reset.sql` được chạy khi thư mục làm việc là `sql-lab/`.

## 4. Tạo `schema.sql`: định nghĩa bảng và ràng buộc

Lưu nội dung sau vào `sql/schema.sql`:

```sql
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    product_name VARCHAR(100) NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    stock_qty INTEGER NOT NULL CHECK (stock_qty >= 0)
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    ordered_at DATE NOT NULL,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE TABLE order_items (
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, product_id)
);
```

Giải thích:

- `PRIMARY KEY` định danh duy nhất mỗi hàng. Bảng `order_items` dùng khóa chính ghép (`order_id`, `product_id`), nghĩa là trong mô hình này một sản phẩm chỉ có một dòng trong cùng đơn.
- `REFERENCES` khai báo khóa ngoại: đơn phải tham chiếu khách có thật, chi tiết đơn phải tham chiếu đơn và sản phẩm có thật.
- `NOT NULL`, `UNIQUE` và `CHECK` chặn nhiều dữ liệu không hợp lệ ngay khi ghi.
- `NUMERIC(12, 2)` phù hợp biểu diễn tiền thập phân chính xác; `DATE` là ngày không kèm giờ và múi giờ.
- **Bảng cha được tạo trước bảng con**: `customers` và `products`, rồi `orders`, cuối cùng `order_items`.

Các ID trong ví dụ được khai báo tường minh để có thể tham chiếu ổn định sau mỗi lần đặt lại. Ứng dụng thật có thể dùng identity/sequence tự sinh, nhưng khi ấy cần kiểm soát cách reset sequence nếu bài tập đòi hỏi ID cụ thể.

## 5. Tạo `seed.sql`: nạp dữ liệu cố định

Lưu vào `sql/seed.sql`:

```sql
INSERT INTO customers (customer_id, full_name, email)
VALUES
    (1, 'An', 'an@example.com'),
    (2, 'Binh', 'binh@example.com'),
    (3, 'Chi', 'chi@example.com');

INSERT INTO products (product_id, sku, product_name, price, stock_qty)
VALUES
    (101, 'BOOK-SQL', 'SQL Book', 150000.00, 20),
    (102, 'KEYBOARD', 'Keyboard', 400000.00, 10),
    (103, 'NOTEBOOK', 'Notebook', 30000.00, 50);

INSERT INTO orders (order_id, customer_id, ordered_at, status)
VALUES
    (1001, 1, DATE '2025-01-15', 'PAID'),
    (1002, 2, DATE '2025-01-16', 'NEW'),
    (1003, 1, DATE '2025-01-17', 'PAID');

INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES
    (1001, 101, 1, 150000.00),
    (1001, 103, 2, 30000.00),
    (1002, 102, 1, 400000.00),
    (1003, 103, 3, 30000.00),
    (1003, 101, 1, 150000.00);
```

**Thứ tự nạp phụ thuộc quan hệ khóa ngoại:** phải có khách và sản phẩm trước khi thêm đơn, phải có đơn trước khi thêm chi tiết. Nếu chèn `order_items` cho mã đơn chưa tồn tại, lệnh sẽ thất bại.

Ngày trong script được ghi bằng `DATE '2025-01-15'` thay vì ngày hiện tại; giá tiền và trạng thái cũng là giá trị cố định. Không có lệnh sinh số ngẫu nhiên hoặc yêu cầu người học nhập tay, nên cùng script có thể tạo cùng trạng thái trên nhiều máy.

Từ seed trên, tiền của mỗi đơn được tính như sau:

| Mã đơn | Thành phần | Tổng tiền | Trạng thái |
|---:|---|---:|---|
| 1001 | 1 × 150.000 + 2 × 30.000 | 210.000 | `PAID` |
| 1002 | 1 × 400.000 | 400.000 | `NEW` |
| 1003 | 3 × 30.000 + 1 × 150.000 | 240.000 | `PAID` |

**Tổng tiền các đơn đã thanh toán lúc ban đầu là 450.000**; tổng cả ba đơn là 850.000. Những con số này sẽ trở thành kết quả mong đợi trong bước kiểm chứng.

## 6. Tạo `verify.sql`: kiểm chứng đúng trạng thái ban đầu

Không nên chỉ dựa vào thông báo “`INSERT 0 3`” của một lệnh đơn lẻ: thông báo ấy không chứng minh rằng toàn bộ các bảng đã nạp đủ và đúng dữ liệu. Một tệp kiểm chứng giúp phát hiện thay đổi hoặc lỗi khi nạp.

Lưu vào `sql/verify.sql`:

```sql
DO $verify$
BEGIN
    IF (SELECT COUNT(*) FROM customers) <> 3
       OR (SELECT COUNT(*) FROM products) <> 3
       OR (SELECT COUNT(*) FROM orders) <> 3
       OR (SELECT COUNT(*) FROM order_items) <> 5 THEN
        RAISE EXCEPTION 'Unexpected sample row counts';
    END IF;

    IF (SELECT price FROM products WHERE product_id = 101)
       IS DISTINCT FROM 150000.00 THEN
        RAISE EXCEPTION 'Product 101 must cost 150000';
    END IF;

    IF (SELECT status FROM orders WHERE order_id = 1002)
       IS DISTINCT FROM 'NEW' THEN
        RAISE EXCEPTION 'Order 1002 must have status NEW';
    END IF;

    IF (
        SELECT COALESCE(SUM(i.quantity * i.unit_price), 0)
        FROM orders AS o
        JOIN order_items AS i ON i.order_id = o.order_id
        WHERE o.status = 'PAID'
    ) <> 450000.00 THEN
        RAISE EXCEPTION 'Paid order total must be 450000';
    END IF;
END;
$verify$;

SELECT 'customers' AS table_name, COUNT(*) AS row_count FROM customers
UNION ALL
SELECT 'products', COUNT(*) FROM products
UNION ALL
SELECT 'orders', COUNT(*) FROM orders
UNION ALL
SELECT 'order_items', COUNT(*) FROM order_items
ORDER BY table_name;

SELECT
    o.order_id,
    o.status,
    SUM(i.quantity * i.unit_price) AS order_total
FROM orders AS o
JOIN order_items AS i ON i.order_id = o.order_id
GROUP BY o.order_id, o.status
ORDER BY o.order_id;
```

Trong PostgreSQL, khối `DO ... RAISE EXCEPTION` chủ động phát sinh lỗi nếu một bất biến không đúng. Khi chạy thông qua `psql -v ON_ERROR_STOP=1`, lỗi khiến công cụ dừng và trả mã thoát khác 0 cho shell hoặc CI. Các truy vấn `SELECT` bên dưới cung cấp kết quả để tự đối chiếu:

```text
 table_name  | row_count
-------------+----------
 customers   |        3
 order_items |        5
 orders      |        3
 products    |        3

 order_id | status | order_total
----------+--------+------------
 1001     | PAID   | 210000.00
 1002     | NEW    | 400000.00
 1003     | PAID   | 240000.00
```

Ở đây có kiểm tra **số hàng, giá sản phẩm, trạng thái đơn và tổng tiền**, vì số hàng đúng không đồng nghĩa nội dung đúng. Nếu bài học yêu cầu kiểm chứng tất cả ô dữ liệu, ta có thể bổ sung phép so sánh toàn bộ bộ dữ liệu mong đợi. Tệp mẫu tập trung vào vài bất biến dễ hiểu để người mới thấy rõ cách biến kỳ vọng thành kiểm tra tự động.

## 7. Tạo `reset.sql`: đặt lại trong một giao dịch

Lưu vào `sql/reset.sql`:

```sql
\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
    IF current_database() <> 'sql_practice' THEN
        RAISE EXCEPTION
            'Reset is allowed only in sql_practice, current database: %',
            current_database();
    END IF;
END;
$guard$;

SET LOCAL search_path TO public;

DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

\ir schema.sql
\ir seed.sql
\ir verify.sql

COMMIT;
```

Luồng thực thi:

```text
BEGIN
  └── Kiểm tra đúng database sql_practice
        └── Xóa bảng con trước, bảng cha sau
              └── Chạy schema.sql: tạo bảng và ràng buộc
                    └── Chạy seed.sql: nạp dữ liệu
                          └── Chạy verify.sql: kiểm chứng
                                ├── Đúng → COMMIT
                                └── Lỗi → dừng, rollback
```

Từng phần có ý nghĩa cụ thể:

1. **`BEGIN` và `COMMIT`:** PostgreSQL hỗ trợ `DROP TABLE`, `CREATE TABLE` và `INSERT` trong giao dịch. Khi script xảy ra lỗi trước `COMMIT`, `psql` dừng với `ON_ERROR_STOP`; khi kết nối kết thúc, giao dịch chưa xác nhận bị rollback. Nhờ đó giảm nguy cơ để lại trạng thái nửa chừng.
2. **Kiểm tra `current_database()`:** chỉ cho phép reset trong database có tên `sql_practice`. Đây là lớp bảo vệ bổ sung, **không biến lệnh xóa thành an toàn đối với dữ liệu thật** bên trong database đó.
3. **`SET LOCAL search_path TO public`:** xác định schema dùng cho các tên bảng không ghi rõ tiền tố trong phạm vi giao dịch. Tài khoản thực hành cần có quyền tạo và xóa các bảng tương ứng trong `public`.
4. **Xóa bảng con trước bảng cha:** tránh vi phạm phụ thuộc khóa ngoại. Không sử dụng `CASCADE`; nếu có đối tượng khác phụ thuộc các bảng này, thao tác phải báo lỗi thay vì âm thầm xóa thêm.
5. **`\ir`:** meta-command riêng của `psql`, đọc tệp theo đường dẫn tương đối với thư mục chứa `reset.sql`. Nó **không phải câu SQL chuẩn**, nên không thể dán toàn bộ tệp này vào mọi trình soạn thảo SQL và chờ nó tự chạy.
6. **Kiểm chứng trước `COMMIT`:** nếu số hàng, giá hoặc tổng thanh toán sai, các thay đổi trong lần reset không được xác nhận.

Việc xóa bảng và tạo lại schema là có chủ đích: nếu người học đã thêm hàng, sửa dữ liệu, thậm chí thay đổi cấu trúc bảng, lần reset vẫn tái tạo đúng tập bảng và ràng buộc chuẩn. Không chạy script trong cơ sở dữ liệu production hoặc nơi người khác cần giữ dữ liệu.

## 8. Chạy lần đầu và chứng minh khả năng tái lập

Từ thư mục `sql-lab/`, chạy:

```bash
psql -X -v ON_ERROR_STOP=1 -d sql_practice -f sql/reset.sql
```

Trong đó `-X` bỏ qua cấu hình khởi động `psqlrc` cục bộ, `-v ON_ERROR_STOP=1` dừng khi có lỗi và trả mã lỗi, `-d` chỉ định database, `-f` chỉ định tệp cần thực thi. Khi kết nối phải chỉ định host, cổng hoặc tài khoản, hãy thêm `-h`, `-p`, `-U` tương ứng.

Sau khi hoàn thành, có thể chạy tệp kiểm chứng một lần nữa:

```bash
psql -X -v ON_ERROR_STOP=1 -d sql_practice -f sql/verify.sql
```

**Bước thử nghiệm 1 — Làm thay đổi dữ liệu.** Trong database thực hành, chuyển đơn 1002 từ `NEW` sang `PAID`:

```bash
psql -X -v ON_ERROR_STOP=1 -d sql_practice -c "UPDATE orders SET status = 'PAID' WHERE order_id = 1002;"
```

Tổng tiền các đơn đã thanh toán lúc này thành **850.000**. Chạy lại `verify.sql` sẽ có lỗi, vì đơn 1002 không còn `NEW` và tổng đã thanh toán khác 450.000. Đây chính là điều ta muốn: kiểm chứng phải phát hiện khi dữ liệu sai trạng thái chuẩn.

**Bước thử nghiệm 2 — Khôi phục.** Chạy:

```bash
psql -X -v ON_ERROR_STOP=1 -d sql_practice -f sql/reset.sql
```

Lúc này đơn 1002 trở lại `NEW`, tổng các đơn `PAID` là **450.000**, số bản ghi đúng như ban đầu. Chạy **cùng lệnh reset thêm một lần**: kết quả tiếp tục không đổi. Đó là khả năng tái lập cần có trước mỗi buổi học hoặc lần chạy kiểm thử.

Nếu một dòng `INSERT` tham chiếu khóa ngoại không tồn tại, PostgreSQL sẽ báo lỗi. Lệnh `psql` với `ON_ERROR_STOP` dừng; do script mở giao dịch và chưa `COMMIT`, kết nối kết thúc sẽ rollback lần đặt lại thất bại. Hãy sửa dữ liệu nguồn rồi **chạy lại reset từ đầu**, không cố bỏ qua lỗi ở giữa script.

## 9. Thực hành truy vấn trên bộ dữ liệu mẫu

**Ví dụ 1 — Khách nào có đơn đã thanh toán?**

```sql
SELECT c.full_name, o.order_id, o.ordered_at
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY o.order_id;
```

Kết quả là hai đơn của **An**: 1001 và 1003.

**Ví dụ 2 — Tổng tiền của từng đơn:**

```sql
SELECT
    o.order_id,
    o.status,
    SUM(i.quantity * i.unit_price) AS total_amount
FROM orders AS o
JOIN order_items AS i ON i.order_id = o.order_id
GROUP BY o.order_id, o.status
ORDER BY o.order_id;
```

Ba đơn 1001, 1002, 1003 lần lượt có tổng tiền **210.000**, **400.000**, **240.000**.

**Ví dụ 3 — Khách đã thanh toán bao nhiêu?**

```sql
SELECT
    c.customer_id,
    c.full_name,
    SUM(i.quantity * i.unit_price) AS paid_amount
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.customer_id
JOIN order_items AS i ON i.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
```

Với seed ban đầu, khách **An** có tổng thanh toán **450.000**; các khách chưa có đơn `PAID` không hiện trong kết quả truy vấn này. Muốn giữ cả khách chưa thanh toán và hiện giá trị 0, bạn sẽ cần `LEFT JOIN` kết hợp xử lý `NULL`.

Sau khi thử các câu lệnh cập nhật, xóa hoặc chèn dữ liệu của riêng mình, chạy lại `reset.sql` để trở về cùng điểm xuất phát.

## 10. Những nguyên tắc quan trọng khi mở rộng bộ dữ liệu mẫu

### 10.1. Lưu script cùng mã nguồn và kiểm soát phiên bản

Đưa `schema.sql`, `seed.sql`, `verify.sql` và `reset.sql` vào Git. Mọi người cùng dùng một phiên bản của các tệp sẽ có cùng mô hình và dữ liệu. Khi sửa seed, hãy cập nhật các kỳ vọng kiểm chứng và ví dụ truy vấn tương ứng. Không phụ thuộc vào các thao tác thủ công từng người từng làm trong giao diện quản trị.

Ở dự án thật, **migration** như Flyway hoặc Liquibase quản lý quá trình **nâng cấp schema có dữ liệu cần giữ lại**. `reset.sql` của bài này dùng cho database học tập có thể xóa toàn bộ các bảng mẫu; không đưa nó vào quy trình triển khai hoặc migration production.

### 10.2. Loại bỏ các nguồn gây sai khác

| Nguồn sai khác | Cách khắc phục |
|---|---|
| `NOW()` hoặc `CURRENT_DATE` | Sử dụng mốc thời gian cố định trong seed |
| `RANDOM()`, ID ngẫu nhiên | Khai báo ID rõ ràng hoặc kiểm soát seed của bộ sinh ngẫu nhiên |
| Identity/sequence thay đổi sau mỗi lần nạp | Reset sequence theo quy tắc đã định nếu bài tập dựa trên ID |
| Nạp từ API hoặc tệp bên ngoài luôn thay đổi | Lưu fixture cố định trong repository |
| Truy vấn không có `ORDER BY` | Sắp xếp tường minh nếu thứ tự kết quả là một phần kỳ vọng |
| Khác phiên bản DBMS, múi giờ, collation | Ghi rõ phiên bản/cấu hình khi chúng ảnh hưởng cú pháp hay kết quả |
| Nhập dữ liệu thủ công | Đưa toàn bộ thao tác khởi tạo vào script để có thể chạy lại |

Đặc biệt, `SELECT * FROM orders` **không bảo đảm thứ tự hàng** nếu thiếu `ORDER BY`, dù dữ liệu đã được nạp theo thứ tự cố định.

### 10.3. Chọn chiến lược đặt lại phù hợp

| Cách đặt lại | Phù hợp khi | Lưu ý |
|---|---|---|
| **`DROP TABLE` → `CREATE TABLE` → `INSERT`** | Cần khôi phục cả cấu trúc và nội dung bài thực hành | Có tính phá hủy, chỉ dùng trên môi trường cô lập |
| **`DELETE` từ bảng con lên bảng cha rồi `INSERT`** | Muốn giữ nguyên schema và chỉ thay dữ liệu | Cần xét khóa ngoại, sequence và trigger |
| **`TRUNCATE` rồi nạp lại** | Cần xóa nhanh nhiều hàng trên DBMS hỗ trợ | Kiểm tra ngữ nghĩa khóa ngoại, giao dịch và `RESTART IDENTITY`; thận trọng với `CASCADE` |
| **`INSERT ... ON CONFLICT` / upsert** | Đồng bộ một phần dữ liệu mà không xóa dữ liệu khác | Không tự loại bỏ bản ghi thừa hoặc khôi phục toàn bộ |
| **Tạo database/container mới cho mỗi test** | Kiểm thử tích hợp cần cô lập mạnh | Phải chuẩn bị và hủy môi trường theo từng lượt chạy |

Không có một cách chung cho mọi hệ thống. Với bài thực hành nhỏ ở đây, quy trình **xóa đúng bốn bảng, tạo lại và nạp seed trong giao dịch** có tính minh bạch cao và dễ đối chiếu.

### 10.4. Cô lập người học và kiểm thử

Hai người không nên dùng chung một database mà cả hai có thể reset trong khi đang làm bài: lần reset của người này sẽ xóa dữ liệu người kia. Mỗi người nên có database riêng, hoặc hệ thống kiểm thử tạo môi trường độc lập cho mỗi lần chạy. Tài khoản thử nghiệm cần có quyền vừa đủ trong môi trường cô lập, không dùng kết nối production.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy `createdb` / `psql` | Chưa cài PostgreSQL CLI hoặc thiếu `PATH` | Cài client và kiểm tra biến môi trường |
| `connection refused` | Server chưa chạy, sai host/cổng | Kiểm tra dịch vụ và tùy chọn `-h`/`-p` |
| `password authentication failed` hoặc `permission denied` | Sai tài khoản/mật khẩu hoặc thiếu quyền | Dùng tài khoản được cấp quyền cho database thực hành |
| `database "sql_practice" does not exist` | Chưa tạo hoặc đang kết nối nhầm server | Tạo database và kiểm tra `current_database()` |
| `duplicate key value violates unique constraint` | Chạy seed trực tiếp nhiều lần | Chạy `reset.sql` để làm mới bảng trước khi seed |
| `violates foreign key constraint` | ID tham chiếu không tồn tại hoặc nạp sai thứ tự | Kiểm tra bảng cha và dữ liệu khóa ngoại |
| `\ir: ... No such file or directory` | Tên hoặc vị trí tệp sai | Để cả bốn tệp trong thư mục `sql/` đúng như cấu trúc ví dụ |
| `Unexpected sample row counts` / `Paid order total...` | Dữ liệu đã bị thay đổi hoặc seed không đúng | Đối chiếu script nguồn, chạy reset rồi kiểm chứng lại |
| `Reset is allowed only in sql_practice` | Đang kết nối database khác | Kiểm tra tham số `-d`; không bỏ bảo vệ khi chưa xác định đích |

Với mọi lỗi, hãy tìm **câu SQL đầu tiên gây lỗi**, đọc tên bảng, khóa hoặc ràng buộc trong thông báo, sửa nguyên nhân trong script rồi chạy lại reset từ đầu.

## 12. Bài tập tự thực hiện

1. Tạo bốn tệp như hướng dẫn. Chạy reset hai lần liên tiếp; đối chiếu số hàng, trạng thái và tổng tiền sau mỗi lần.
2. Dùng `INSERT` thêm khách số 4 và một đơn mới. Chạy `verify.sql` để thấy số hàng khác kỳ vọng; chạy reset và kiểm tra các hàng mới biến mất.
3. Đổi giá sản phẩm 101 thành `100.00`; xác nhận `verify.sql` báo sai giá; reset để phục hồi về `150000.00`.
4. Thử chèn một dòng `order_items` với `product_id` không tồn tại. Đọc lỗi và xác định ràng buộc `FOREIGN KEY` đã ngăn dữ liệu sai.
5. Gửi cho một bạn khác chỉ bốn tệp SQL và cách chạy. Họ có tự tạo được đúng kết quả mà không cần bạn nhập thủ công hay không?

Sau các bài tập thay đổi dữ liệu, chạy reset trước khi chuyển sang bài kế tiếp để cả nhóm luôn trở về cùng trạng thái khởi đầu.

## Kết luận

Một môi trường SQL thực hành đáng tin cậy cần **dữ liệu chuẩn có thể tái lập**, **quy trình đặt lại rõ ràng** và **bước kiểm chứng độc lập**. Với PostgreSQL, bốn tệp `schema.sql`, `seed.sql`, `verify.sql` và `reset.sql` đủ để tạo bảng, nạp dữ liệu, phát hiện sai khác và khôi phục sau mỗi lần thử nghiệm.

Khi mọi câu truy vấn đều bắt đầu từ cùng một trạng thái, người học dễ hiểu kết quả hơn; nhóm phát hiện lỗi nhanh hơn; bài kiểm thử cũng có đầu vào dự đoán được. Đây là nền tảng để tiến tới quản lý migration, fixture cho kiểm thử tích hợp và vận hành môi trường cơ sở dữ liệu nhiều người dùng.
