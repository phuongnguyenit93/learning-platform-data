# Lộ trình từ cơ sở dữ liệu đầu tiên đến vận hành an toàn với PostgreSQL

Một câu lệnh `CREATE DATABASE` có thể tạo cơ sở dữ liệu PostgreSQL trong vài giây, nhưng xây dựng được một hệ thống **đáng tin cậy khi có người dùng thật** là một hành trình dài hơn. Dữ liệu cần có ràng buộc, giao dịch cần đúng khi nhiều người thao tác đồng thời, ứng dụng cần kết nối và xử lý lỗi an toàn, quyền truy cập phải được giới hạn, còn bản sao lưu phải **khôi phục được** khi xảy ra sự cố.

Bài này cung cấp một **lộ trình học và triển khai PostgreSQL từ số không đến vận hành có kiểm soát**. Thay vì liệt kê tính năng rời rạc, mỗi giai đoạn có mục tiêu, ví dụ thực hành, bằng chứng hoàn thành và điều kiện để chuyển sang bước tiếp theo. Bộ dữ liệu mẫu là một cửa hàng đơn giản; cùng các nguyên tắc có thể áp dụng cho hệ thống học tập, quản lý đơn hàng, ứng dụng web hoặc dịch vụ Java kết nối PostgreSQL.

Các lệnh được minh họa theo PostgreSQL hiện đại, sử dụng `psql`, kiểu `IDENTITY`, `TIMESTAMPTZ`, `NUMERIC` và InnoDB **không liên quan**: PostgreSQL có bộ máy lưu trữ và MVCC riêng. Hãy thực hiện trên một instance và một database **thử nghiệm**. Tên host, tài khoản và mật khẩu trong ví dụ là chỗ giữ chỗ, không phải thông tin truy cập thật.

## 1. Bản đồ hành trình: từ “chạy được” đến “vận hành được”

Một hệ thống PostgreSQL nên tiến qua các mức trưởng thành sau:

~~~mermaid
flowchart TD
    A["1. Kết nối và hiểu cluster / database / schema"] --> B["2. Thiết kế bảng và ràng buộc"]
    B --> C["3. Nạp dữ liệu và truy vấn đúng"]
    C --> D["4. Giao dịch và đồng thời"]
    D --> E["5. Kết nối ứng dụng, migration và phân quyền"]
    E --> F["6. Giải thích kế hoạch và quan sát tải"]
    F --> G["7. Sao lưu, thử khôi phục, giám sát, ứng cứu"]
    G --> H["8. Vận hành production bằng quy trình"]
~~~

Mỗi bước phụ thuộc kết quả trước:

- Nếu **schema chưa giữ được tính toàn vẹn**, việc tạo API nhanh không giải quyết được dữ liệu sai.
- Nếu **giao dịch không nguyên tử**, nhiều câu lệnh thành công riêng lẻ vẫn có thể tạo đơn hàng thiếu dòng hoặc trừ tồn kho sai.
- Nếu **không tách quyền**, một lỗi SQL injection hoặc lộ credential có thể có phạm vi thiệt hại lớn.
- Nếu **không thử khôi phục**, một file backup tồn tại chưa đủ chứng minh có thể phục hồi dịch vụ.
- Nếu **không có quan sát và cảnh báo**, sự cố kết nối, khóa, đầy ổ đĩa hoặc autovacuum chậm có thể không được nhận biết cho đến khi ứng dụng dừng.

Mục tiêu cuối cùng là thiết lập được **đường đi kiểm chứng được** từ thao tác ghi dữ liệu đến khả năng vận hành, bảo vệ và phục hồi dữ liệu đó.

## 2. Những thành phần PostgreSQL cần biết trước khi tạo bảng

PostgreSQL sử dụng một số từ có ý nghĩa cụ thể:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Server/instance** | Tiến trình PostgreSQL phục vụ kết nối đến dữ liệu | Một dịch vụ PostgreSQL trên máy hoặc hệ thống managed |
| **Database cluster** | Tập các database do cùng một instance PostgreSQL quản lý; không đồng nghĩa cluster HA | Instance chứa `postgres` và `shop_learning` |
| **Database** | Đơn vị cơ sở dữ liệu có tên; mỗi kết nối làm việc trong một database | `shop_learning` |
| **Schema** | Không gian tên đối tượng trong một database | `sales` |
| **Table** | Tập hàng, cột và ràng buộc | `sales.orders` |
| **Role** | Định danh để quản lý đăng nhập, sở hữu và quyền | `shop_reader` |
| **Transaction** | Đơn vị thao tác nguyên tử, có thể `COMMIT` hoặc `ROLLBACK` | Tạo đơn và giảm tồn kho |
| **WAL** | Write-ahead log phục vụ tính bền vững và phục hồi | Thành phần nền của crash recovery và PITR |

**Một cluster PostgreSQL có thể chứa nhiều database; một database có thể chứa nhiều schema.** Không thể dùng câu `schema.table` để tham chiếu trực tiếp bảng của database khác trong PostgreSQL tiêu chuẩn như thể đó là một schema cùng database. Khi cần truy cập chéo database, phải dùng cơ chế phù hợp như `postgres_fdw` hoặc thiết kế tích hợp khác.

Tên `public` là schema thường có sẵn, nhưng ví dụ tạo schema `sales` riêng để tránh nhầm đối tượng ứng dụng với đối tượng mặc định và dễ quản lý quyền.

## 3. Chặng 1 — Cài đặt, kết nối và xác nhận đúng môi trường

Tùy hệ điều hành, PostgreSQL có thể được cài qua gói hệ thống, bộ cài chính thức, container, hoặc dùng dịch vụ managed. Cách cài đặt không thay đổi những quy tắc SQL căn bản, nhưng ảnh hưởng vị trí file dữ liệu, cách quản lý dịch vụ, TLS và chính sách backup.

Trước khi thao tác, cần có:

1. Địa chỉ host và cổng; mặc định thường là `5432` nhưng có thể được đổi.
2. Tên database có sẵn để kết nối, ví dụ `postgres`.
3. Role có đủ quyền tạo database cho môi trường thực hành.
4. Cách xác thực an toàn: mật khẩu được nhập qua prompt, secret manager hoặc phương thức do tổ chức quản lý.
5. Xác nhận đây là instance **development/lab**, không phải production.

Kết nối bằng `psql`:

~~~bash
psql -h 127.0.0.1 -p 5432 -U postgres -d postgres
~~~

Lệnh có thể hỏi mật khẩu. Không nên chèn mật khẩu trực tiếp vào lịch sử shell, URL hoặc file mã nguồn. Trong `psql`, kiểm tra:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS connected_role,
    current_setting('server_version') AS server_version,
    current_setting('TimeZone') AS session_timezone;
~~~

Lệnh meta của `psql`:

~~~text
\conninfo
\l
\du
~~~

Trong đó `\conninfo` cho biết kết nối hiện tại; `\l` liệt kê database; `\du` liệt kê role trong phạm vi quyền được phép xem. Những dòng bắt đầu bằng dấu `\` là **psql meta-command**, không phải câu SQL có thể gửi nguyên xi qua JDBC.

### 3.1. Tạo database thực hành

Khi đã kết nối đến database `postgres` bằng role có quyền `CREATEDB`:

~~~sql
CREATE DATABASE shop_learning
    WITH ENCODING 'UTF8';
~~~

`CREATE DATABASE` không được thực thi bên trong một transaction block tường minh. Sau khi tạo, kết nối đến database mới bằng lệnh `psql`:

~~~text
\connect shop_learning
~~~

Rồi kiểm tra:

~~~sql
SELECT current_database();
-- shop_learning
~~~

Nếu tên database đã tồn tại, câu lệnh tạo sẽ báo lỗi. Đừng chạy `DROP DATABASE` để “làm lại từ đầu” nếu chưa xác minh database đó thực sự chỉ là môi trường lab và không chứa dữ liệu cần giữ.

### 3.2. Phân biệt database với schema

Trong database `shop_learning`:

~~~sql
CREATE SCHEMA sales;

SELECT schema_name
FROM information_schema.schemata
WHERE schema_name = 'sales';
~~~

Mọi bảng trong bài sẽ mang tiền tố `sales.`, ví dụ `sales.customers`. Viết đầy đủ tên schema giúp tránh những bất ngờ do `search_path` trong các phiên hoặc role khác nhau.

**Dấu hiệu hoàn thành chặng 1:** kết nối được từ `psql`, xác nhận đúng database/role/version, tạo được database và schema thực hành mà không đụng đến dữ liệu sản xuất.

## 4. Chặng 2 — Thiết kế bảng, kiểu dữ liệu và ràng buộc

Giả sử cửa hàng cần quản lý khách hàng, sản phẩm, đơn hàng và dòng chi tiết. Các quan hệ:

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : places
    ORDERS ||--o{ ORDER_ITEMS : contains
    PRODUCTS ||--o{ ORDER_ITEMS : appears_in

    CUSTOMERS {
        bigint customer_id PK
        text email UK
        text full_name
    }
    PRODUCTS {
        bigint product_id PK
        text sku UK
        text product_name
        numeric list_price
        integer stock_qty
    }
    ORDERS {
        bigint order_id PK
        text order_no UK
        bigint customer_id FK
        timestamptz created_at
        text status
    }
    ORDER_ITEMS {
        bigint order_id PK,FK
        bigint product_id PK,FK
        integer quantity
        numeric unit_price
    }
~~~

Một khách có thể có nhiều đơn; mỗi đơn có nhiều dòng; một sản phẩm có thể xuất hiện trong nhiều đơn. Khóa chính tổng hợp `(order_id, product_id)` của `order_items` thể hiện giả định **một sản phẩm chỉ có một dòng trong mỗi đơn**.

### 4.1. Tạo khách hàng và sản phẩm

~~~sql
CREATE TABLE sales.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT customers_full_name_nonblank
        CHECK (length(btrim(full_name)) > 0)
);

CREATE TABLE sales.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    list_price NUMERIC(12, 2) NOT NULL,
    stock_qty INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT products_name_nonblank
        CHECK (length(btrim(product_name)) > 0),
    CONSTRAINT products_price_positive
        CHECK (list_price > 0),
    CONSTRAINT products_stock_nonnegative
        CHECK (stock_qty >= 0)
);
~~~

Những quyết định đáng chú ý:

- `GENERATED ALWAYS AS IDENTITY` tạo giá trị định danh bằng sequence do PostgreSQL quản lý; ứng dụng thông thường không cần tự cấp ID.
- `email` và `sku` là mã nghiệp vụ duy nhất; PostgreSQL áp dụng `UNIQUE` theo toán tử so sánh/collation liên quan.
- `NUMERIC(12,2)` phù hợp tiền có hai chữ số thập phân hơn `real`/`double precision` khi cần tính toán thập phân chính xác.
- `BOOLEAN` có hai giá trị logic `TRUE`, `FALSE` và khả năng `NULL` khi không có `NOT NULL`; ví dụ chủ động cấm `NULL`.
- `CHECK` giới hạn giá và số lượng. `NOT NULL` cần được khai báo riêng: trong PostgreSQL, một biểu thức `CHECK` đánh giá thành `UNKNOWN` do `NULL` không tự gây vi phạm.

### 4.2. Tạo đơn hàng và chi tiết

~~~sql
CREATE TABLE sales.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_no TEXT NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL
        REFERENCES sales.customers(customer_id)
        ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'NEW',
    CONSTRAINT orders_status_valid
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE TABLE sales.order_items (
    order_id BIGINT NOT NULL
        REFERENCES sales.orders(order_id)
        ON DELETE RESTRICT,
    product_id BIGINT NOT NULL
        REFERENCES sales.products(product_id)
        ON DELETE RESTRICT,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (order_id, product_id),
    CONSTRAINT items_quantity_positive
        CHECK (quantity > 0),
    CONSTRAINT items_price_positive
        CHECK (unit_price > 0)
);
~~~

`FOREIGN KEY` ngăn tạo đơn gắn với khách không tồn tại và ngăn dòng hàng tham chiếu sản phẩm không có trong bảng. `ON DELETE RESTRICT` giúp tránh vô tình xóa lịch sử đơn hàng khi xóa một khách hàng hoặc sản phẩm; ứng dụng có thể chọn “ngừng hoạt động” thay cho xóa vật lý khi cần giữ lịch sử.

**Giá chốt tại lúc đặt hàng** được lưu ở `order_items.unit_price`. Nếu sau này cửa hàng thay đổi `products.list_price`, các đơn cũ vẫn tính bằng đơn giá lịch sử.

### 4.3. Phân biệt khóa nghiệp vụ với khóa tham chiếu

| Loại | Ví dụ | Mục đích |
| --- | --- | --- |
| Primary key | `customer_id` | Nhận diện dòng và tham chiếu nội bộ ổn định |
| Unique business key | `email`, `sku`, `order_no` | Chặn mã nghiệp vụ trùng |
| Foreign key | `orders.customer_id` | Bảo vệ quan hệ giữa bảng con và cha |
| Composite key | `order_items(order_id, product_id)` | Chặn một sản phẩm lặp trong cùng đơn |
| Check constraint | `stock_qty >= 0` | Chặn trạng thái không hợp lệ trong từng dòng |

Trong PostgreSQL, **khóa ngoại không tự luôn tạo chỉ mục trên cột phía tham chiếu ở bảng con**. Index phục vụ `JOIN` và kiểm tra/xóa ở bảng cha có thể cần được tạo có chủ đích khi lượng dữ liệu lớn.

### 4.4. Xem cấu trúc vừa tạo

Trong `psql`:

~~~text
\dt sales.*
\d sales.customers
\d sales.order_items
~~~

Hoặc dùng truy vấn metadata:

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'sales'
ORDER BY table_name;
~~~

**Dấu hiệu hoàn thành chặng 2:** biết tại sao có bốn bảng thay vì một bảng rộng, chỉ ra được khóa chính/khóa ngoại và giải thích được những trường hợp `CHECK`, `UNIQUE`, `NOT NULL` từ chối dữ liệu sai.

## 5. Chặng 3 — Nạp dữ liệu mẫu và truy vấn có thể đối chiếu

Nạp dữ liệu theo thứ tự **bảng cha trước, bảng con sau**. Lệnh mẫu dùng email, SKU và số đơn để tìm khóa nội bộ, tránh phụ thuộc ID sequence có giá trị cụ thể.

### 5.1. Nạp khách hàng và sản phẩm

~~~sql
INSERT INTO sales.customers (email, full_name)
VALUES
    ('an@example.test', 'Nguyễn An'),
    ('binh@example.test', 'Trần Bình');

INSERT INTO sales.products
    (sku, product_name, list_price, stock_qty)
VALUES
    ('BOOK-SQL', 'Sách PostgreSQL', 150000.00, 40),
    ('PEN-BLUE', 'Bút xanh',        20000.00, 100),
    ('MOUSE-01', 'Chuột không dây', 280000.00, 15);
~~~

Tên miền `example.test` dùng cho dữ liệu minh họa. Không dùng email thật của khách hàng trong ví dụ được chia sẻ công khai.

### 5.2. Nạp hai đơn hàng

~~~sql
INSERT INTO sales.orders (order_no, customer_id, status)
SELECT v.order_no, c.customer_id, v.status
FROM (
    VALUES
        ('SO-001', 'an@example.test',   'PAID'),
        ('SO-002', 'binh@example.test', 'NEW')
) AS v(order_no, email, status)
JOIN sales.customers AS c
    ON c.email = v.email;
~~~

Với dữ liệu mẫu, cả hai email đều tồn tại. Trong quy trình nhập hàng loạt thực tế, cần đối chiếu số dòng input với số dòng chèn thành công; việc dùng `INNER JOIN` để tìm khóa có thể khiến dòng input không khớp bị loại khỏi kết quả `SELECT`, thay vì phát sinh lỗi khóa ngoại.

### 5.3. Nạp ba dòng chi tiết

~~~sql
INSERT INTO sales.order_items
    (order_id, product_id, quantity, unit_price)
SELECT
    o.order_id,
    p.product_id,
    v.quantity,
    v.unit_price
FROM (
    VALUES
        ('SO-001', 'BOOK-SQL', 2, 150000.00::numeric),
        ('SO-001', 'PEN-BLUE', 3,  20000.00::numeric),
        ('SO-002', 'MOUSE-01', 1, 280000.00::numeric)
) AS v(order_no, sku, quantity, unit_price)
JOIN sales.orders AS o ON o.order_no = v.order_no
JOIN sales.products AS p ON p.sku = v.sku;
~~~

Thành tiền:

| Đơn | Sản phẩm | Công thức | Tổng |
| --- | --- | --- | ---: |
| `SO-001` | Sách PostgreSQL | 2 × 150.000 | 300.000 |
| `SO-001` | Bút xanh | 3 × 20.000 | 60.000 |
| `SO-002` | Chuột không dây | 1 × 280.000 | 280.000 |

### 5.4. Kiểm tra dữ liệu bằng SELECT và JOIN

~~~sql
SELECT
    o.order_no,
    c.full_name,
    o.status,
    SUM(oi.quantity * oi.unit_price) AS order_total
FROM sales.orders AS o
JOIN sales.customers AS c
    ON c.customer_id = o.customer_id
JOIN sales.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY o.order_id, o.order_no, c.full_name, o.status
ORDER BY o.order_no;
~~~

Kết quả kỳ vọng:

| `order_no` | `full_name` | `status` | `order_total` |
| --- | --- | --- | ---: |
| `SO-001` | Nguyễn An | `PAID` | 360.000 |
| `SO-002` | Trần Bình | `NEW` | 280.000 |

Kiểm tra số dòng:

~~~sql
SELECT
    (SELECT count(*) FROM sales.customers) AS customers,
    (SELECT count(*) FROM sales.products) AS products,
    (SELECT count(*) FROM sales.orders) AS orders,
    (SELECT count(*) FROM sales.order_items) AS items;
-- Kỳ vọng: 2, 3, 2, 3 nếu chỉ nạp đúng bộ seed này.
~~~

Một điểm quan trọng khi học: **truy vấn cho ra kết quả không có nghĩa dữ liệu chắc chắn hợp lệ toàn diện**. Ràng buộc kiểm soát từng loại quy tắc; còn quy tắc nghiệp vụ như “đơn `PAID` phải có thanh toán khớp tổng tiền” cần một mô hình thanh toán và logic bổ sung.

### 5.5. Thử một lỗi ràng buộc trong transaction

~~~sql
BEGIN;

INSERT INTO sales.products
    (sku, product_name, list_price, stock_qty)
VALUES
    ('BOOK-SQL', 'Bản ghi mã trùng', 50000.00, 1);
-- ERROR 23505: unique_violation (mã SKU đã tồn tại).

ROLLBACK;
~~~

Vì PostgreSQL đặt transaction vào trạng thái **aborted** sau nhiều lỗi SQL, các câu lệnh tiếp theo trong transaction thường bị từ chối cho đến khi `ROLLBACK`. Nếu muốn bắt và xử lý lỗi tại một phần nhỏ của transaction, có thể dùng `SAVEPOINT`, rồi `ROLLBACK TO SAVEPOINT` trước khi tiếp tục.

**Dấu hiệu hoàn thành chặng 3:** nạp được dữ liệu mẫu, biết số dòng mong đợi, tính đúng tổng đơn hàng và giải thích được lỗi `23505` mà không làm hỏng session hoặc commit phần dữ liệu sai.

## 6. Chặng 4 — Giao dịch, MVCC và cập nhật đồng thời

PostgreSQL hỗ trợ giao dịch **ACID** và dùng **MVCC** (*multi-version concurrency control*) để nhiều thao tác đọc/ghi có thể hoạt động đồng thời theo mức cô lập. Cách người dùng nhìn thấy dữ liệu phụ thuộc vào thời điểm giao dịch, câu lệnh và isolation level.

Một tình huống điển hình là hai người cùng đặt mua sản phẩm cuối cùng. Nếu ứng dụng chỉ:

1. Đọc `stock_qty`.
2. Tự tính số tồn mới trong bộ nhớ.
3. Ghi đè giá trị mới.

thì hai luồng có thể cùng đọc một số cũ, gây **lost update** hoặc bán quá tồn kho nếu không có cơ chế đồng thời phù hợp.

### 6.1. Atomic UPDATE có điều kiện

Thay vì đọc rồi ghi đè:

~~~sql
BEGIN;

UPDATE sales.products
SET stock_qty = stock_qty - 2
WHERE sku = 'MOUSE-01'
  AND is_active = TRUE
  AND stock_qty >= 2
RETURNING product_id, stock_qty;

-- Chỉ khi trả về đúng một dòng mới được tiếp tục
-- tạo đơn và chi tiết đơn bằng cùng transaction.

ROLLBACK;
~~~

Với seed ban đầu, câu `UPDATE` trả một dòng với `stock_qty = 13`. `ROLLBACK` đưa tồn kho về 15 để bộ dữ liệu mẫu không đổi. Khi đưa vào ứng dụng, nếu `RETURNING` không trả dòng, phải dừng và rollback nghiệp vụ thay vì tiếp tục tạo đơn.

`UPDATE ... WHERE stock_qty >= 2` được thực hiện trong cơ chế khóa và kiểm tra điều kiện của PostgreSQL, giúp hai luồng không tự động trừ cùng một số tồn cũ như phép tính phía client.

### 6.2. Mỗi nghiệp vụ nhiều bước phải dùng một transaction

Ví dụ tạo đơn mới bao gồm:

~~~text
BEGIN
  kiểm tra yêu cầu và quyền nghiệp vụ
  trừ tồn kho có điều kiện
  thêm bản ghi orders
  thêm các dòng order_items
  ghi trạng thái/thanh toán nếu có
COMMIT khi tất cả bước hợp lệ

Nếu bất kỳ bước quan trọng nào lỗi:
  ROLLBACK
~~~

Không được thực hiện trừ tồn kho và thêm dòng hàng bằng các transaction autocommit rời nhau rồi mong dữ liệu vẫn nguyên tử. Với JDBC, ứng dụng thường gọi `setAutoCommit(false)` trên **một connection**, thực hiện các câu SQL và `commit()` hoặc `rollback()`.

### 6.3. Các mức cô lập nên nhận diện

PostgreSQL hỗ trợ các mức cô lập có tên trong tiêu chuẩn SQL, nhưng `READ UNCOMMITTED` có hành vi tương đương `READ COMMITTED`. `READ COMMITTED` là mức mặc định phổ biến; mỗi statement nhìn thấy một snapshot phù hợp khi statement bắt đầu. `REPEATABLE READ` giữ snapshot ổn định hơn trong transaction; `SERIALIZABLE` có thể buộc ứng dụng retry khi phát hiện cấu hình thao tác không thể được sắp xếp tuần tự an toàn.

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Các thao tác đọc/ghi nghiệp vụ tại đây.

ROLLBACK;
~~~

Lệnh trên chỉ minh họa thiết lập mức cô lập. Không nên bật `SERIALIZABLE` cho tất cả workload rồi bỏ qua khả năng nhận `SQLSTATE 40001` (*serialization_failure*). Khi xảy ra lỗi cần retry, **làm lại toàn bộ transaction** với giới hạn, backoff và cơ chế idempotency nếu nghiệp vụ có tác dụng ghi.

### 6.4. Tách deadlock, lỗi dữ liệu và mất kết nối

| SQLSTATE | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| `23505` | Trùng khóa duy nhất | Xử lý xung đột hoặc đối chiếu request ID, không retry mù |
| `23503` | Vi phạm khóa ngoại | Sửa dữ liệu tham chiếu hoặc trình tự nghiệp vụ |
| `23514` | Vi phạm CHECK | Sửa giá trị không hợp lệ |
| `40001` | Serialization failure | Rollback và retry toàn bộ transaction nếu an toàn |
| `40P01` | Deadlock detected | Rollback và retry toàn bộ transaction có giới hạn |
| `55P03` | Lock not available | Xem chính sách khóa/timeout, rollback khi cần |
| `57014` | Query canceled, có thể do statement timeout | Xác định nguyên nhân và trạng thái transaction |
| Nhóm `08xxx` | Lỗi kết nối/giao tiếp | Bỏ kết nối hỏng, phân tích trạng thái giao dịch |

Với lỗi mất phản hồi **ngay lúc COMMIT**, ứng dụng có thể không biết server đã commit hay chưa. Không tự động gửi một yêu cầu ghi mới với mã mới: hãy dùng **idempotency key** và đối chiếu kết quả bền vững trước khi kết luận thành công/thất bại.

**Dấu hiệu hoàn thành chặng 4:** có thể giải thích vì sao một nghiệp vụ phải rollback toàn bộ khi một bước thất bại; biết khi nào nên dùng cập nhật có điều kiện, khóa và retry thay vì chỉ kiểm tra input ở Java.

## 7. Chặng 5 — Kết nối ứng dụng và quản lý schema bằng migration

Một chương trình Java hoặc dịch vụ web không nên dùng role quản trị cấp cao chỉ để chạy `SELECT` và `INSERT`. Tối thiểu nên tách:

- Role **quản trị/migration** được phép thay đổi schema.
- Role **ứng dụng** chỉ có các quyền DML cần thiết.
- Role **báo cáo** chỉ có quyền `SELECT` trên các bảng hoặc view đã được phê duyệt.

### 7.1. Kết nối Java qua JDBC và connection pool

Ví dụ URL PostgreSQL JDBC:

~~~text
jdbc:postgresql://db.example.internal:5432/shop_learning
~~~

Trong ứng dụng, sử dụng một `DataSource` có connection pool được cấu hình phù hợp (ví dụ HikariCP). Không mở một TCP connection mới cho mọi câu SQL nếu workload cần phục vụ nhiều request. Những thông số cần cân nhắc gồm:

- Kích thước pool so với `max_connections`, số instance ứng dụng và tài nguyên database.
- Timeout khi lấy connection, timeout kết nối, timeout câu lệnh và deadline của API.
- TLS, secret rotation, hostname và quy tắc mạng.
- Việc trả connection về pool sau mỗi request, kể cả khi xảy ra exception.
- Tính toàn vẹn transaction: rollback trước khi đưa connection về pool nếu nghiệp vụ thất bại.

Một mẫu JDBC tối thiểu:

~~~java
try (Connection con = dataSource.getConnection()) {
    con.setAutoCommit(false);

    try (PreparedStatement ps = con.prepareStatement(
            "UPDATE sales.products " +
            "SET stock_qty = stock_qty - ? " +
            "WHERE sku = ? AND stock_qty >= ? " +
            "RETURNING product_id")) {

        ps.setInt(1, 2);
        ps.setString(2, "MOUSE-01");
        ps.setInt(3, 2);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new IllegalStateException("Không đủ hàng");
            }
        }
    }

    // Minh họa transaction: không lưu thay đổi thật.
    con.rollback();

} // Đóng connection / trả về pool theo DataSource.
~~~

`PreparedStatement` tách tham số khỏi cấu trúc SQL, giảm nguy cơ SQL injection so với nối chuỗi input trực tiếp vào câu lệnh. Nó không thay thế xác thực người dùng, phân quyền và kiểm tra nghiệp vụ.

Đối với một transaction nhiều bước, cần bắt lỗi để rollback rõ ràng. Ví dụ rút gọn trên chủ động rollback vì chỉ minh họa thao tác; với nghiệp vụ thật, mọi đường lỗi cần được quản lý và lỗi rollback phải được log thay vì bị nuốt.

### 7.2. Migration: quản lý thay đổi schema có phiên bản

Trong lúc phát triển, có thể sửa bảng bằng SQL thủ công. Nhưng khi nhiều môi trường cùng hoạt động, cần đưa DDL vào **migration có version** bằng công cụ như Flyway hoặc Liquibase, hoặc một quy trình tương đương.

Ví dụ thay đổi an toàn về mặt cú pháp:

~~~sql
ALTER TABLE sales.products
ADD COLUMN description TEXT;
~~~

Với PostgreSQL, nhiều DDL có thể chạy trong transaction và rollback khi thất bại. Tuy nhiên không nên suy ra mọi DDL đều được chạy trong một transaction: một số thao tác, chẳng hạn `CREATE INDEX CONCURRENTLY`, **không được thực hiện bên trong transaction block tường minh**.

Ví dụ khi bảng đơn hàng lớn và cần tăng khả năng truy vấn mà hạn chế chặn thao tác ghi:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_customer_created
ON sales.orders (customer_id, created_at DESC);
~~~

Lệnh `CONCURRENTLY` có những chi phí và điều kiện riêng, có thể kéo dài và cần theo dõi. Nếu thất bại, PostgreSQL có thể để lại index không hợp lệ cần xử lý có chủ đích. Không dùng nó như từ khóa bảo đảm “không khóa và không có rủi ro”.

Lộ trình migration đáng tin cậy:

1. Lưu thay đổi schema dưới version duy nhất trong repository.
2. Chạy thử trên dữ liệu đại diện, kiểm tra index, ràng buộc và tương thích code cũ/mới.
3. Thiết kế thay đổi nhiều bước theo hướng **expand → migrate data → switch code → contract** với các thay đổi không tương thích.
4. Đặt `lock_timeout`/`statement_timeout` thích hợp cho tác vụ đã đánh giá, không để DDL chờ khóa quá lâu mà ảnh hưởng dịch vụ.
5. Có backup/khả năng khôi phục được kiểm tra, kế hoạch giảm thiểu sự cố và giám sát sau triển khai.

Không chỉnh DDL trực tiếp trên production rồi quên cập nhật migration nguồn; những môi trường khác sẽ dần có schema khác nhau.

**Dấu hiệu hoàn thành chặng 5:** ứng dụng không dùng superuser; có DataSource, transaction boundary, prepared statements và một quy trình migration đã chạy thử trên staging.

## 8. Chặng 6 — Bảo vệ truy cập: role, GRANT, pg_hba.conf và TLS

PostgreSQL kiểm soát quyền qua **role** và **GRANT/REVOKE**. Việc một role có thể đăng nhập không có nghĩa role đó được đọc hoặc sửa mọi bảng.

### 8.1. Role chỉ đọc cho báo cáo

Thực hiện các câu SQL sau bởi role sở hữu database/schema hoặc có quyền quản lý phù hợp trong môi trường lab:

~~~sql
CREATE ROLE shop_reader LOGIN;

GRANT CONNECT ON DATABASE shop_learning TO shop_reader;
GRANT USAGE ON SCHEMA sales TO shop_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA sales TO shop_reader;
~~~

Trong `psql`, đặt mật khẩu qua prompt thay vì ghi plaintext trong file SQL:

~~~text
\password shop_reader
~~~

Lệnh `\password` là meta-command của `psql`. Trong môi trường có cơ chế xác thực khác, như IAM hoặc secret manager, không nhất thiết quản lý mật khẩu theo cách thủ công này. Tuy nhiên phải bảo đảm role đăng nhập được bằng phương thức đã cho phép.

Chỉ cấp quyền trên **các bảng hiện có** sẽ không tự áp dụng cho mọi bảng tạo sau này. Để role báo cáo đọc các bảng tương lai do **cùng role sở hữu bảng hiện tại** tạo, có thể cấu hình quyền mặc định. Khi kết nối bằng role tạo/sở hữu các bảng trong schema, chạy:

~~~sql
ALTER DEFAULT PRIVILEGES IN SCHEMA sales
GRANT SELECT ON TABLES TO shop_reader;
~~~

**Default privileges phụ thuộc role tạo object.** Nếu migration chạy bằng role khác với role vừa đặt default privileges, các bảng do role đó tạo sẽ không tự nhận quyền như mong muốn. Trong production, quyền nên được khai báo theo vai trò sở hữu đối tượng và quản lý bằng quy trình triển khai.

### 8.2. Quy tắc quyền tối thiểu

| Loại tài khoản | Quyền nên có | Không nên có theo mặc định |
| --- | --- | --- |
| App chỉ đọc | `CONNECT`, `USAGE` schema, `SELECT` phù hợp | Quyền sửa/xóa schema, superuser |
| App ghi dữ liệu | `SELECT`/`INSERT`/`UPDATE`/`DELETE` trên bảng cần thiết | `CREATE`/`DROP` tùy ý, quản lý role |
| Migration/owner | Quyền thay đổi đối tượng do mình sở hữu, cấp quyền cần thiết | Đăng nhập liên tục trong đường request của ứng dụng |
| Role quản trị hệ thống | Quyền vận hành được kiểm soát và audit | Dùng trực tiếp cho mọi request HTTP |

Một ứng dụng có quyền ghi chỉ nên có quyền cần cho đường nghiệp vụ của nó; nếu có nhiều dịch vụ, không nhất thiết dùng chung một credential.

### 8.3. pg_hba.conf, mạng và mã hóa

`pg_hba.conf` quyết định **kết nối từ địa chỉ nào, tới database nào, với role nào và phương thức xác thực nào** được phép. Các cấu hình xác thực như SCRAM-SHA-256 được sử dụng phổ biến; không nên mở kiểu `trust` cho mạng công khai hoặc cho toàn bộ người dùng.

Để kết nối từ xa an toàn:

- Giới hạn `listen_addresses` và firewall/security group ở những interface/subnet thực sự cần.
- Dùng TLS khi đi qua mạng không đáng tin cậy; ứng dụng cần xác thực chứng chỉ server nếu mô hình bảo mật yêu cầu.
- Lưu và luân chuyển credential trong secret manager hoặc cơ chế an toàn, không commit mật khẩu vào Git.
- Áp dụng least privilege, kiểm tra quyền sở hữu schema và `search_path`.
- Lưu log đăng nhập, thay đổi quyền và hoạt động quan trọng theo chính sách bảo mật.

Chỉ sửa file cấu hình rồi coi như đã an toàn là chưa đủ: cần xác nhận cấu hình đã được load/reload đúng cách, kết nối ngoài phạm vi bị từ chối và kết nối được phép dùng TLS/xác thực hợp lệ.

**Dấu hiệu hoàn thành chặng 6:** role báo cáo đọc được dữ liệu cần thiết nhưng không thể `UPDATE`; kết nối trái phép bị từ chối; tài khoản ứng dụng không có quyền cấp phát schema hoặc superuser.

## 9. Chặng 7 — Truy vấn nhanh và đo bằng EXPLAIN

PostgreSQL sử dụng **planner** để chọn cách truy cập dữ liệu. Khi bảng lớn lên, một truy vấn đúng có thể trở thành chậm do quét nhiều dòng, thiếu index, phép nối không phù hợp hoặc thống kê đã thay đổi.

Ví dụ lọc đơn hàng của một khách theo thời gian:

~~~sql
EXPLAIN
SELECT order_no, created_at, status
FROM sales.orders
WHERE customer_id = (
    SELECT customer_id
    FROM sales.customers
    WHERE email = 'an@example.test'
)
ORDER BY created_at DESC;
~~~

Ở bảng chỉ vài dòng, planner có thể chọn sequential scan vì đây là cách rẻ nhất. Điều đó **không phải lỗi**. Khi dữ liệu tăng, có thể xem xét index:

~~~sql
CREATE INDEX idx_orders_customer_created
ON sales.orders (customer_id, created_at DESC);
~~~

Nếu đã tạo index cùng tên ở mục migration trước đó, **không chạy lại lệnh tạo này**; đây là hai cách minh họa cùng một cấu trúc index, trong đó mục migration dùng `CONCURRENTLY`. Chọn đúng một cách theo trạng thái schema thực tế.

Để xem cả thời gian và số dòng thực tế, ở truy vấn `SELECT` được phép chạy:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_no, created_at, status
FROM sales.orders
ORDER BY created_at DESC;
~~~

Phân biệt:

- `EXPLAIN` chỉ cho thấy kế hoạch dự kiến, không thực thi truy vấn chỉ để thu thống kê runtime.
- `EXPLAIN (ANALYZE, BUFFERS)` **thực sự chạy truy vấn** và thu dữ liệu thực thi. Với câu ghi, nó cũng có thể ghi dữ liệu thật; không dùng bừa trên production.
- Số hàng ước tính và thực tế ở từng node có thể khác nhau. Sai lệch lớn gợi ý xem thống kê, phân bố dữ liệu và điều kiện truy vấn.
- Các phép quét toàn bảng không phải lúc nào cũng xấu, nhất là khi phần lớn dòng đều cần đọc.

Với bảng lớn, `ANALYZE` cập nhật thống kê cho planner:

~~~sql
ANALYZE sales.orders;
~~~

Autovacuum cũng có cơ chế autoanalyze. Không cần chạy `ANALYZE` thủ công sau mọi câu `INSERT`; dùng nó khi có lý do vận hành, chẳng hạn vừa nạp lượng dữ liệu lớn hoặc thấy ước tính bị lệch.

### 9.1. Index là công cụ, không phải càng nhiều càng tốt

Mỗi index tốn không gian và có chi phí duy trì khi `INSERT`, `UPDATE` hoặc `DELETE`. Lộ trình đúng là:

1. Xác định truy vấn chậm/quan trọng từ log hoặc metric.
2. Đo kế hoạch với dữ liệu đại diện.
3. Thiết kế index phục vụ điều kiện lọc, nối và thứ tự truy vấn.
4. Đo lại số hàng, buffer và thời gian.
5. Theo dõi ảnh hưởng đến tốc độ ghi, dung lượng và thời gian bảo trì.

Kết luận “tạo index chắc chắn nhanh hơn” từ một bảng chỉ ba đơn hàng không có giá trị đối với hệ thống thực.

**Dấu hiệu hoàn thành chặng 7:** đọc được kế hoạch `Seq Scan`, `Index Scan`/`Index Only Scan`, nhận ra thứ tự JOIN và số hàng ước tính; biết đo lại sau khi thay đổi SQL/index.

## 10. Chặng 8 — Hiểu VACUUM, thống kê và công việc bảo trì

PostgreSQL dùng MVCC: khi sửa hoặc xóa dòng, các phiên bản hàng cũ có thể phải được giữ một thời gian để phục vụ transaction còn cần nhìn thấy chúng. Dữ liệu cũ đã không còn cần thiết phải được dọn, nếu không sẽ gây tăng dung lượng và giảm hiệu quả truy vấn.

**VACUUM** giúp thu hồi không gian bên trong bảng cho các ghi tiếp theo và xử lý trạng thái phiên bản hàng cũ. **ANALYZE** cập nhật thống kê cho planner. PostgreSQL có **autovacuum** để thực hiện những công việc phù hợp theo chính sách; không nên tắt nó chỉ vì thấy hoạt động I/O.

Một số lệnh quan sát:

~~~sql
SHOW autovacuum;

SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'sales'
ORDER BY relname;
~~~

`n_live_tup` và `n_dead_tup` là **ước tính/thống kê**, không phải phép đếm chính xác từng dòng. Các trường `last_autovacuum` và `last_autoanalyze` giúp nhận diện thời điểm công việc tự động được ghi nhận, nhưng cần xét cùng tuổi transaction, tải hệ thống và dung lượng.

### 10.1. Vì sao transaction mở lâu gây rủi ro?

Một transaction đọc/ghi mở rất lâu có thể làm chậm việc loại bỏ những phiên bản hàng cũ mà các snapshot vẫn còn có khả năng cần đến. Hệ quả có thể là **bloat**, tải I/O, tăng lưu trữ và áp lực lên quá trình vacuum. Giữ transaction ngắn, không mở transaction rồi chờ người dùng hoặc gọi HTTP chậm.

Quan sát transaction đang tồn tại:

~~~sql
SELECT
    pid,
    usename,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Quyền xem chi tiết session khác có thể bị giới hạn tùy role; không cấp quyền theo dõi nhạy cảm chỉ để chạy ví dụ.

### 10.2. VACUUM khác VACUUM FULL

| Hoạt động | Đặc điểm | Lưu ý |
| --- | --- | --- |
| Autovacuum | Công việc tự động để quản lý phiên bản hàng cũ, thống kê và các nhiệm vụ bảo trì | Giám sát, điều chỉnh theo workload; đừng vô hiệu hóa tùy tiện |
| `VACUUM table` | Dọn phiên bản cũ và tạo không gian có thể tái sử dụng trong relation | Không cam kết file trên OS co lại tương ứng |
| `ANALYZE table` | Thu thập thống kê planner | Không phải lệnh dọn dữ liệu |
| `VACUUM (ANALYZE) table` | Kết hợp dọn dẹp và cập nhật thống kê | Có chi phí I/O |
| `VACUUM FULL table` | Viết lại bảng để thu gọn dung lượng vật lý trong những trường hợp phù hợp | Có khóa mạnh, yêu cầu không gian bổ sung và kế hoạch bảo trì |

Không dùng `VACUUM FULL` như một tác vụ mặc định hàng ngày trên bảng nóng: khóa và thời gian viết lại có thể ảnh hưởng dịch vụ nghiêm trọng. PostgreSQL còn có yêu cầu chống **transaction ID wraparound**, khiến công tác vacuum liên quan trực tiếp đến an toàn dữ liệu; theo dõi cảnh báo tuổi transaction và các thông số bảo trì phù hợp với môi trường.

**Dấu hiệu hoàn thành chặng 8:** biết vì sao bảng có thể lớn lên sau nhiều UPDATE/DELETE, theo dõi được autovacuum và transaction lâu, không coi VACUUM là công cụ xóa dữ liệu người dùng.

## 11. Chặng 9 — Sao lưu phải đi cùng thử khôi phục

Một bản sao lưu không được coi là bảo vệ đầy đủ nếu chưa biết **khôi phục tới đâu, trong bao lâu và đã thử khôi phục chưa**. Hai mục tiêu vận hành quan trọng:

- **RPO (Recovery Point Objective):** có thể mất tối đa bao nhiêu dữ liệu nếu xảy ra sự cố.
- **RTO (Recovery Time Objective):** dịch vụ cần được phục hồi trong bao lâu.

Ví dụ RPO 15 phút và RTO 1 giờ là yêu cầu nghiệp vụ; không thể bảo đảm các con số này chỉ bằng việc cấu hình cron chạy `pg_dump` mỗi ngày.

### 11.1. Backup logic bằng pg_dump

`pg_dump` có thể tạo bản sao lưu logic nhất quán của một database, ví dụ định dạng custom:

~~~bash
pg_dump \
  -h 127.0.0.1 -p 5432 -U postgres \
  -d shop_learning \
  -F c \
  -f shop_learning.dump
~~~

Với `-F c`, backup ở định dạng custom, phù hợp để dùng `pg_restore` lựa chọn đối tượng hoặc khôi phục bằng các tùy chọn. `pg_dump` chỉ sao lưu **database được chỉ định**; nó không tự thay thế toàn bộ cấu hình cluster, role toàn cục, tablespace hoặc cơ chế lưu WAL liên tục.

Có thể xem danh mục đối tượng trong dump:

~~~bash
pg_restore -l shop_learning.dump
~~~

**Không khôi phục đè trực tiếp database production để “kiểm tra backup”.** Tạo một database khác trên môi trường thử nghiệm:

~~~bash
createdb -h 127.0.0.1 -p 5432 -U postgres shop_restore_test

pg_restore \
  -h 127.0.0.1 -p 5432 -U postgres \
  -d shop_restore_test \
  --no-owner --no-privileges \
  --exit-on-error \
  shop_learning.dump
~~~

Sau đó kết nối vào `shop_restore_test` để kiểm tra số bảng, khóa ngoại, số hàng và các truy vấn nghiệp vụ. `--no-owner`/`--no-privileges` hữu ích khi phục hồi vào môi trường thử nghiệm không có các role gốc; môi trường thật cần chính sách sở hữu và cấp quyền đúng, không phải luôn bỏ qua quyền.

### 11.2. Kiểm tra sau phục hồi

~~~sql
SELECT
    (SELECT count(*) FROM sales.customers) AS customers,
    (SELECT count(*) FROM sales.products) AS products,
    (SELECT count(*) FROM sales.orders) AS orders,
    (SELECT count(*) FROM sales.order_items) AS items;
~~~

Với bộ seed của bài, kỳ vọng `2, 3, 2, 3`. Nếu source đã có thêm giao dịch sau khi tạo dump, hãy so với **trạng thái tại thời điểm dump**, không ép so với dữ liệu hiện tại sau nhiều ngày.

Kiểm tra thêm rằng ứng dụng có thể kết nối và thực hiện những câu truy vấn cần thiết, ràng buộc còn tồn tại, index được tạo đúng và các chức năng quan trọng chạy lại được. File backup có thể đọc được danh mục không đồng nghĩa mọi object và extension đã được phục hồi đủ để chạy ứng dụng.

### 11.3. PITR: base backup và chuỗi WAL

`pg_dump` là sao lưu logic tại một thời điểm. Để khôi phục **tới một thời điểm cụ thể** (point-in-time recovery, PITR), PostgreSQL cần một **base backup** phù hợp và **chuỗi WAL được lưu trữ liên tục** để replay tới mốc mục tiêu.

~~~mermaid
flowchart LR
    A["Base backup tại T0"] --> B["WAL archive T0 → T1"]
    B --> C["WAL archive T1 → T2"]
    C --> D["Restore base backup + replay WAL"]
    D --> E["Trạng thái dữ liệu tại T mục tiêu"]
~~~

`pg_basebackup`, `archive_mode`, `archive_command`, retention WAL, vị trí lưu archive và các tham số recovery phải được thiết kế theo phiên bản PostgreSQL và hạ tầng. Nếu thiếu một đoạn WAL cần thiết, không thể tự suy ra giao dịch đã mất chỉ từ base backup. Vì thế, cần có giám sát archive, kiểm thử PITR và tài liệu runbook trước khi tuyên bố đáp ứng RPO.

**Backup phải được bảo vệ:** mã hóa khi lưu và truyền nếu phù hợp, hạn chế người được đọc, lưu cách ly với máy chủ chính, có retention và kiểm tra khả năng đọc. Một backup trên cùng ổ đĩa bị hỏng với primary không đủ bảo vệ trước lỗi phần cứng hoặc ransomware.

**Dấu hiệu hoàn thành chặng 9:** có backup định kỳ và bằng chứng khôi phục thành công sang môi trường riêng; biết những dữ liệu và thời điểm mà quy trình có thể phục hồi.

## 12. Chặng 10 — Giám sát, cảnh báo và ứng cứu

Một dịch vụ an toàn cần biết tình trạng **trước khi ứng dụng báo lỗi hàng loạt**. Các nguồn quan sát thường gồm PostgreSQL system views, log, metrics của host, connection pool và monitoring của hạ tầng.

### 12.1. Các nhóm metric nên theo dõi

| Nhóm | Chỉ số hữu ích | Dấu hiệu cần điều tra |
| --- | --- | --- |
| Sẵn sàng | Kết nối thành công, latency, lỗi kết nối | Không kết nối được, tăng `08xxx`, pool cạn |
| Tài nguyên | CPU, RAM, disk usage, I/O latency | Ổ đĩa gần đầy, I/O kéo dài, swap |
| Giao dịch | Commit/rollback, thời gian transaction, số transaction mở lâu | Tăng rollback, giữ snapshot/khóa lâu |
| Truy vấn | Slow queries, số hàng đọc, thời gian và tần suất | Một endpoint đột ngột chậm |
| Khóa | Chờ khóa, deadlocks, thời gian chờ | Deadlock hoặc hàng đợi tăng |
| Dữ liệu | `n_dead_tup`, autovacuum, dung lượng bảng/index | Bloat, vacuum chậm, transaction ID age |
| Backup | Backup cuối cùng, restore test, WAL archive | Backup thất bại hoặc chuỗi WAL thiếu |
| Replica nếu có | Replay lag, receiver/apply trạng thái, replication slots | Replica bỏ xa hoặc giữ WAL quá nhiều |

### 12.2. Truy vấn quan sát đơn giản

Thông tin database hiện tại:

~~~sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

Những bộ đếm là **số tích lũy theo đời thống kê**, không phải số lỗi “trong một giây”. Để tính tốc độ, hệ thống giám sát phải lấy nhiều mẫu theo thời gian và xử lý reset bộ đếm.

Các session đang chờ:

~~~sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
~~~

Các trường `wait_event_type` và `wait_event` cần được đọc trong bối cảnh trạng thái session; `idle` không đồng nghĩa đang thực thi SQL. Không tự ý hủy backend hoặc chấm dứt session đang phục vụ giao dịch quan trọng mà chưa xác định tác động.

### 12.3. Thiết lập các ngưỡng cảnh báo có chủ đích

Ví dụ:

- Ổ đĩa chứa data hoặc WAL vượt ngưỡng dung lượng an toàn.
- Không có backup thành công trong khoảng thời gian chính sách cho phép.
- Kết quả restore test gần nhất đã quá cũ.
- Connection pool thường xuyên chờ hoặc PostgreSQL gần chạm giới hạn kết nối.
- Tăng deadlock, transaction dài hoặc replica lag kéo dài.
- `archive_command` liên tục thất bại, khiến WAL không được lưu đúng.

Không đặt một ngưỡng duy nhất cho mọi môi trường; hệ thống ghi dữ liệu lớn và hệ thống đọc báo cáo có cấu trúc tải rất khác nhau.

### 12.4. Runbook xử lý sự cố

Một runbook tối thiểu nên ghi:

1. **Triệu chứng và phạm vi**: tất cả endpoint hay một truy vấn, primary hay replica, bắt đầu từ khi nào?
2. **Trạng thái hiện tại**: kết nối, log, disk, transaction, locks, WAL và backup.
3. **Các thao tác an toàn đầu tiên**: dừng hoạt động gây quá tải khi cần, hạn chế retry, giữ chứng cứ log và xác nhận backup.
4. **Quyết định can thiệp**: rollback migration, tăng tài nguyên, chấm dứt session có đánh giá, failover hoặc restore theo phương án đã chuẩn bị.
5. **Xác nhận phục hồi**: truy vấn nghiệp vụ, độ trễ, số liệu và khả năng ghi trở lại.
6. **Báo cáo hậu kiểm**: nguyên nhân, tác động, những lỗ hổng giám sát và việc cần sửa.

**Dấu hiệu hoàn thành chặng 10:** có dashboard, cảnh báo được kiểm thử và một người khác trong nhóm có thể dựa vào runbook để chẩn đoán tình huống phổ biến.

## 13. Chặng 11 — Replication và khả năng sẵn sàng cao không thay backup

Khi một instance PostgreSQL không còn đủ đáp ứng yêu cầu sẵn sàng, có thể xây dựng **primary–standby** sử dụng physical streaming replication. Primary gửi WAL; standby nhận và replay thay đổi để có bản dữ liệu gần primary.

~~~mermaid
flowchart LR
    A["Ứng dụng ghi"] --> P["Primary PostgreSQL"]
    P -->|"WAL streaming"| S["Standby PostgreSQL"]
    B["Ứng dụng đọc"] --> S
    C["Backup + WAL archive"] -. "phục hồi độc lập" .-> P
~~~

Một vài nguyên tắc cần nhớ:

- Replication thông thường có thể **bất đồng bộ**; transaction đã commit ở primary chưa chắc đã tới standby trước khi primary mất.
- Standby có thể giúp giảm downtime và phân tải đọc trong thiết kế phù hợp, nhưng đọc từ replica có thể thấy dữ liệu cũ hơn.
- **Failover cần điều phối và fencing** để tránh hai primary cùng nhận ghi (*split brain*).
- Replication **không thay backup**: xóa nhầm hoặc cập nhật sai dữ liệu ở primary có thể được sao chép rất nhanh sang standby.
- Replication slot có thể khiến WAL được giữ lại nếu consumer chậm/ngừng; cần cảnh báo dung lượng và chính sách vận hành.
- Nếu dùng synchronous replication để tăng mức bảo đảm, phải hiểu rõ đánh đổi về latency, độ sẵn sàng khi standby mất kết nối và chính sách commit.

Thông tin trên primary:

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

Trên standby, có thể kiểm tra trạng thái nhận WAL qua `pg_stat_wal_receiver` và việc server có đang ở recovery mode bằng `pg_is_in_recovery()`. Đừng đọc một chỉ số lag rồi kết luận mọi transaction đã an toàn; cần định nghĩa rõ yêu cầu đọc sau ghi, RPO và quy trình failover.

**Dấu hiệu hoàn thành chặng 11:** phân biệt được backup, replication và failover; có kế hoạch chuyển vai trò và kiểm thử khả năng ứng dụng kết nối lại khi instance chính lỗi.

## 14. Lộ trình thực hành theo mốc

Bảng sau là một **kế hoạch học gợi ý**, không phải thời lượng cố định cho mọi người. Có thể hoàn thành nhanh hơn hoặc lâu hơn tùy kinh nghiệm và độ phức tạp của hệ thống.

| Chặng | Thực hành trọng tâm | Bằng chứng đạt yêu cầu |
| --- | --- | --- |
| **Nền tảng** | `psql`, cluster/database/schema, role, tạo bảng | Kết nối và tạo `shop_learning.sales`; mô tả đúng từng cấp |
| **Dữ liệu đúng** | `PRIMARY KEY`, `UNIQUE`, FK, `CHECK`, seed, `JOIN`/`GROUP BY` | Bốn bảng có ràng buộc; tính đúng hai tổng đơn mẫu |
| **Đồng thời** | `BEGIN`/`COMMIT`/`ROLLBACK`, atomic update, isolation | Thử cập nhật tồn kho có rollback, phân biệt lỗi có thể retry |
| **Tích hợp** | JDBC, pooling, prepared statements, migration | Ứng dụng dùng role riêng; schema có version |
| **Hiệu năng** | `EXPLAIN`, index, `ANALYZE`, thống kê | Có bản đo trước/sau cho truy vấn đã chọn |
| **Bảo mật** | `GRANT`/`REVOKE`, pg_hba.conf, TLS | Role báo cáo chỉ đọc; credential không nằm trong source |
| **Phục hồi** | `pg_dump`/`pg_restore`, backup policy, PITR | Khôi phục vào database riêng và đối chiếu thành công |
| **Vận hành** | Monitor, vacuum, locks, WAL, runbook | Có cảnh báo cơ bản, người khác đọc được runbook |
| **Sẵn sàng cao** | Primary–standby, replication, failover | Có bài diễn tập failover và hiểu RPO/RTO thực tế |

### 14.1. Bốn câu hỏi trước khi nâng môi trường

**Trước khi rời môi trường local:**

- Một người khác có thể khởi tạo database từ migration và seed, không cần cấu hình thủ công bí mật không?
- Dữ liệu nhập sai có bị ràng buộc chặn không?
- Ứng dụng có rollback cả nghiệp vụ khi một câu SQL trong chuỗi thất bại không?
- Đã tách credential ứng dụng khỏi tài khoản quản trị chưa?

**Trước khi cho staging nhận dữ liệu thực tế tương tự production:**

- Có migration tương thích với phiên bản ứng dụng đang chạy không?
- Các query nặng có được đo trên dữ liệu đủ đại diện không?
- Có backup, kiểm thử khôi phục và giới hạn quyền truy cập không?
- Dashboard đã hiển thị lỗi kết nối, khóa và dung lượng chưa?

**Trước khi go-live:**

- RPO/RTO đã được thống nhất với nghiệp vụ chưa?
- Đã thực hiện một lần restore test từ **backup thật** trên môi trường biệt lập chưa?
- Có kế hoạch rollback triển khai ứng dụng/migration và người chịu trách nhiệm không?
- Có cảnh báo ổ đĩa, replication (nếu dùng), backup, transaction dài và connection exhaustion không?

**Sau khi go-live:**

- Ai trực sự cố và ai được phép can thiệp database?
- Bao lâu kiểm tra backup, phục hồi và nâng version?
- Có bằng chứng theo dõi autovacuum, bloat, WAL archive và transaction ID age không?
- Có review định kỳ quyền role, schema migrations và các query chậm không?

## 15. Những lỗi tư duy dễ gặp trên con đường học PostgreSQL

| Hiểu nhầm | Điều cần nhớ |
| --- | --- |
| “Có database nghĩa là hệ thống đã sẵn sàng” | Khởi tạo mới là bước đầu; cần toàn vẹn dữ liệu, backup, bảo mật và quan sát |
| “PostgreSQL schema là một database khác” | Schema là không gian tên **bên trong** database |
| “Có `FOREIGN KEY` nên mọi nghiệp vụ đã đúng” | FK bảo vệ liên kết, không kiểm tra mọi quy tắc tổng tiền, tồn kho hay trạng thái |
| “`UNIQUE` và kiểm tra bằng SELECT là như nhau” | SELECT trước khi insert không loại bỏ race condition; UNIQUE được kiểm soát bởi database |
| “Một lần có SQL lỗi thì transaction tự trở lại bình thường” | Sau nhiều lỗi, transaction ở trạng thái aborted cho đến `ROLLBACK` hoặc xử lý savepoint |
| “Cứ thêm index là truy vấn nhanh hơn” | Index tốn không gian và chi phí ghi; phải đo bằng kế hoạch thực thi |
| “`EXPLAIN ANALYZE` chỉ xem metadata” | Nó thực thi truy vấn; với câu ghi có thể thay đổi dữ liệu |
| “Transaction lâu không ảnh hưởng ai” | Có thể giữ khóa, kéo dài tuổi snapshot và cản trở vacuum |
| “`VACUUM` luôn làm file nhỏ lại” | VACUUM thường tạo không gian tái sử dụng trong relation; `VACUUM FULL` có đánh đổi khóa và I/O |
| “Đã có file dump thì không cần restore test” | Chỉ thử khôi phục mới kiểm chứng khả năng phục hồi trên môi trường mục tiêu |
| “Có replica thì không cần backup” | Lỗi logic hoặc xóa nhầm có thể sao chép sang replica |
| “Role app dùng superuser cho dễ” | Khi lỗi hoặc lộ credential, phạm vi thiệt hại sẽ không cần thiết lớn |
| “Đặt mật khẩu là đủ bảo vệ kết nối” | Cần giới hạn mạng, phương thức xác thực, TLS, quyền và secret management |
| “SQL chạy đúng trên local thì production chắc chắn ổn” | Dữ liệu, concurrency, statistics và tài nguyên thực có thể khác lớn |

## 16. Bài tập tổng hợp tự đánh giá

### Bài 1 — Tạo một bảng liên kết mới

Thêm bảng `sales.payments` với `payment_id` là identity primary key, `order_id` tham chiếu đơn hàng, `paid_amount NUMERIC(12,2)` dương và `paid_at TIMESTAMPTZ` mặc định `now()`. Chọn xem nghiệp vụ cho phép **một hay nhiều** lần thanh toán trên một đơn; nếu chỉ một lần, khai báo `UNIQUE (order_id)`. Giải thích vì sao việc chọn này ảnh hưởng khả năng trả góp và hoàn tiền.

### Bài 2 — Phát hiện dữ liệu nhập sai

Thử chèn một sản phẩm có `stock_qty = -5`, một đơn tham chiếu `customer_id` không tồn tại và một dòng `order_items.quantity = 0`. Ghi SQLSTATE được trả về. Thực hiện trong môi trường thử nghiệm, dùng `ROLLBACK` sau khi gặp lỗi.

### Bài 3 — Giải thích transaction abort

Trong một transaction có hai lệnh DML, lệnh đầu hợp lệ, lệnh thứ hai vi phạm `UNIQUE`. Nếu gọi tiếp lệnh thứ ba ngay sau lỗi, PostgreSQL phản ứng ra sao? Khi nào cần `ROLLBACK` và khi nào dùng `SAVEPOINT`? Điều gì xảy ra nếu ứng dụng bỏ qua lỗi và cố `COMMIT`?

### Bài 4 — Lập quyền cho hai loại user

Tạo role chỉ đọc dữ liệu `sales` và role ứng dụng có quyền ghi vào một số bảng. Giải thích quyền `CONNECT` của database, `USAGE` trên schema và quyền `SELECT`/`INSERT` trên bảng khác nhau ở điểm nào. Xác nhận role chỉ đọc không được phép sửa `sales.products`.

### Bài 5 — Đo truy vấn trước và sau index

Tăng lượng dữ liệu trong **môi trường lab**, dùng `EXPLAIN (ANALYZE, BUFFERS)` cho truy vấn tra đơn theo `customer_id`. Thử một index phù hợp, đo lại số hàng, thời gian và buffer, đồng thời ghi nhận tác động đến việc chèn dữ liệu.

### Bài 6 — Thử tình huống mất dữ liệu

Tạo một bản `pg_dump`, phục hồi sang database mới, kiểm tra số dòng và truy vấn tính tổng đơn hàng. Viết runbook nêu: file backup nằm đâu, ai có quyền đọc, lệnh restore là gì, kết quả nào chứng minh thành công, và nếu file hỏng thì phương án dự phòng là gì.

### Bài 7 — Thiết kế vận hành tối thiểu

Với một dịch vụ Java dùng PostgreSQL, liệt kê:

- Mức giới hạn connection pool và timeout.
- Tín hiệu nhận biết query chậm, deadlock, disk gần đầy.
- Chính sách backup, retention và lịch kiểm thử khôi phục.
- Quy trình triển khai migration có khả năng kiểm soát tác động khóa.
- Các tiêu chí quyết định có cần standby và failover không.

Mục đích không phải chọn ngay các con số “chuẩn cho mọi hệ thống”, mà là giải thích **vì sao giá trị được chọn dựa trên workload, tài nguyên và yêu cầu nghiệp vụ**.

## 17. Kết luận: tiêu chuẩn của một PostgreSQL an toàn

Điểm khởi đầu là tạo một database, schema và vài bảng. Nhưng PostgreSQL chỉ thật sự trở thành nền tảng vận hành đáng tin cậy khi hệ thống được thiết kế theo nhiều lớp: **ràng buộc dữ liệu**, **giao dịch đúng**, **quyền tối thiểu**, **migration có kiểm soát**, **đo hiệu năng**, **vacuum và giám sát**, **backup được kiểm chứng bằng restore**, cùng **runbook xử lý sự cố**.

Một lộ trình học tốt không dừng ở việc ghi nhớ cú pháp `CREATE TABLE` hay `SELECT`. Nó giúp người học tự trả lời: “Nếu có hai request ghi cùng lúc thì chuyện gì xảy ra?”, “Nếu migration sai thì khôi phục ra sao?”, “Nếu primary mất thì dữ liệu nào có thể mất?”, và “Ai có thể đọc hoặc sửa dữ liệu này?”.

Khi có thể chứng minh những câu trả lời đó bằng ràng buộc, truy vấn, transaction, quyền và một lần khôi phục thực tế, cơ sở dữ liệu đã tiến xa hơn mức **chạy được trên máy cá nhân**: nó có nền tảng để **vận hành PostgreSQL an toàn, có thể quan sát và có khả năng phục hồi**.
