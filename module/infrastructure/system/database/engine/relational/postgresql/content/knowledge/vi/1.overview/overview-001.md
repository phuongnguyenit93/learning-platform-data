# PostgreSQL là gì và vai trò của hệ quản trị cơ sở dữ liệu quan hệ

Khi xây dựng một ứng dụng bán hàng, quản lý học viên hoặc xử lý thanh toán, lập trình viên không chỉ cần nơi lưu các bản ghi. Hệ thống còn phải trả lời những câu hỏi khó hơn: **Làm sao ngăn đơn hàng tham chiếu khách hàng không tồn tại? Làm sao hai người cùng cập nhật dữ liệu mà không phá hỏng kết quả? Điều gì xảy ra nếu máy chủ mất điện ngay lúc đang ghi giao dịch? Và làm sao tìm nhanh vài trăm bản ghi giữa hàng triệu hàng?**

**PostgreSQL** là một hệ quản trị cơ sở dữ liệu quan hệ mã nguồn mở, thường được gọi là **Postgres**. Nó cung cấp cơ chế lưu trữ có cấu trúc, ngôn ngữ truy vấn SQL, ràng buộc toàn vẹn, giao dịch, kiểm soát đồng thời, chỉ mục, phân quyền và các công cụ vận hành để giúp ứng dụng xử lý dữ liệu một cách đáng tin cậy.

Bài học giới thiệu PostgreSQL từ góc nhìn của người học **Database Engine Relational PostgreSQL**: hệ quản trị cơ sở dữ liệu quan hệ làm những gì, PostgreSQL vận hành theo mô hình nào, nó khác gì một tập tin dữ liệu hay thư viện thao tác SQL, và khi nào nên lựa chọn nó cho một hệ thống thực tế.

## 1. Ba khái niệm thường bị nhầm: dữ liệu, cơ sở dữ liệu và hệ quản trị

Trước khi tìm hiểu PostgreSQL, hãy phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Dữ liệu** | Các giá trị biểu diễn sự kiện hoặc thực thể | Khách hàng tên An, đơn hàng số 101 |
| **Cơ sở dữ liệu (database)** | Tập dữ liệu được tổ chức để truy cập và quản lý | Dữ liệu khách hàng, sản phẩm, đơn hàng của một ứng dụng |
| **Hệ quản trị CSDL (DBMS)** | Phần mềm quản lý việc lưu, đọc, sửa, bảo vệ, đảm bảo toàn vẹn dữ liệu | PostgreSQL |
| **RDBMS** | DBMS có mô hình quan hệ làm nền tảng | PostgreSQL, MySQL, SQL Server |
| **SQL** | Ngôn ngữ khai báo để định nghĩa, truy vấn và thay đổi dữ liệu quan hệ | `SELECT`, `INSERT`, `CREATE TABLE` |

**PostgreSQL không phải là một câu lệnh SQL hay chỉ là một tệp `.sql`.** Nó là một hệ thống phần mềm chạy trên máy chủ, nhận yêu cầu của ứng dụng, lập kế hoạch thực thi, truy cập dữ liệu và duy trì nhiều bảo đảm mà một tập tin văn bản thông thường không tự có.

Hình dung một ứng dụng:

~~~text
                    NGƯỜI DÙNG
                        |
                        v
              Ứng dụng web/mobile
                        |
                  SQL qua driver
                        |
                        v
               PostgreSQL Server
                /     |       \
        Truy vấn   Giao dịch   Phân quyền
           |          |          |
           +----------+----------+
                      |
                      v
             Các bảng và chỉ mục
                      |
                      v
                Lưu trữ bền vững
~~~

Người dùng không cần biết một hàng nằm ở trang đĩa nào. Ứng dụng mô tả dữ liệu cần lấy bằng SQL; PostgreSQL chịu trách nhiệm tìm, đọc, kiểm tra và trả kết quả theo quyền được cấp.

## 2. PostgreSQL là gì?

PostgreSQL là **hệ quản trị cơ sở dữ liệu quan hệ–đối tượng (*object-relational database management system*)** mã nguồn mở. Phần cốt lõi của nó tuân theo mô hình quan hệ và sử dụng SQL. Bên cạnh kiểu dữ liệu và tính năng quan hệ truyền thống, PostgreSQL còn hỗ trợ kiểu dữ liệu mở rộng, hàm, toán tử, extension và nhiều cơ chế tùy biến.

Những đặc điểm quan trọng:

- **Mã nguồn mở:** có thể sử dụng, nghiên cứu và phát triển theo giấy phép của dự án PostgreSQL.
- **Hoạt động theo mô hình máy khách–máy chủ:** nhiều ứng dụng/kết nối truy cập cùng một PostgreSQL server.
- **Sử dụng SQL:** tạo bảng, đặt ràng buộc, truy vấn nhiều bảng, tổng hợp, cập nhật và xóa dữ liệu.
- **Có giao dịch:** nhóm các thay đổi thành đơn vị có thể `COMMIT` hoặc `ROLLBACK`.
- **Có cơ chế đồng thời và khôi phục:** MVCC, khóa, WAL, cơ chế kiểm tra tính nhất quán.
- **Có chỉ mục và trình tối ưu truy vấn:** giúp lựa chọn cách đọc dữ liệu phù hợp.
- **Có phân quyền:** roles, đặc quyền trên database/schema/bảng và các đối tượng khác.
- **Có khả năng mở rộng:** nhiều loại dữ liệu, extension, hàm do người dùng định nghĩa và các công cụ trong hệ sinh thái.

PostgreSQL thường được dùng cho ứng dụng giao dịch trực tuyến, hệ thống nghiệp vụ doanh nghiệp, API web, dịch vụ phân tích, lưu dữ liệu địa lý và những hệ thống cần kiểm soát dữ liệu quan hệ chặt chẽ.

Không nên hiểu “PostgreSQL hỗ trợ nhiều tính năng” là “PostgreSQL tự động phù hợp mọi workload”. Cấu trúc dữ liệu, truy vấn, độ trễ yêu cầu, tải ghi, vận hành và nguồn lực đội ngũ vẫn quyết định lựa chọn công nghệ.

### 2.1. PostgreSQL và tên gọi Postgres

Hai tên **PostgreSQL** và **Postgres** thường được dùng để chỉ cùng hệ quản trị. PostgreSQL là tên dự án và sản phẩm; Postgres là cách gọi ngắn thông dụng.

Khi đọc tài liệu hoặc cấu hình, bạn có thể thấy tên:

~~~text
PostgreSQL server
postgres                 (tên chương trình server phổ biến)
psql                     (chương trình khách dòng lệnh)
postgresql.conf          (tệp cấu hình server)
pg_hba.conf              (cấu hình xác thực kết nối)
PGDATA                   (thư mục dữ liệu của một instance/cluster)
~~~

Các tên này liên quan đến nhiều thành phần khác nhau, không phải những tên đồng nghĩa của một câu SQL.

## 3. Mô hình quan hệ giải quyết vấn đề gì?

Trong mô hình quan hệ, dữ liệu được biểu diễn thành các **quan hệ**; khi triển khai SQL, chúng thường được tổ chức thành **bảng (table)** gồm **hàng (row)** và **cột (column)**.

Giả sử ứng dụng quản lý đặt hàng:

~~~text
customers
+-------------+-----------------+
| customer_id | customer_name   |
+-------------+-----------------+
|           1 | An              |
|           2 | Bình            |
+-------------+-----------------+

orders
+----------+-------------+---------+
| order_id | customer_id | status  |
+----------+-------------+---------+
|      101 |           1 | paid    |
|      102 |           1 | pending |
|      103 |           2 | paid    |
+----------+-------------+---------+
~~~

Ở đây:

- Mỗi hàng `customers` đại diện một khách hàng.
- Mỗi hàng `orders` đại diện một đơn hàng.
- `customer_id` trong `orders` xác định khách hàng sở hữu đơn.
- Một khách hàng có thể có **nhiều đơn**, trong khi mỗi đơn thuộc một khách hàng theo mô hình này.

Mối quan hệ đó có thể được bảo vệ bằng **foreign key** để ngăn ghi đơn hàng trỏ tới khách hàng không tồn tại.

~~~text
customers.customer_id
        |
        | 1 ---- N
        v
orders.customer_id
~~~

Mô hình quan hệ giúp dữ liệu được **tách thành những thực thể có ý nghĩa**, tránh lặp lại quá nhiều thông tin và cho phép kết hợp chúng bằng phép nối (`JOIN`).

### 3.1. Không phải “bảng” nào cũng là một file CSV

Một CSV cũng có hàng và cột, nhưng nó không tự có những cơ chế như:

- Ràng buộc khóa chính và khóa ngoại được engine kiểm tra.
- Giao dịch nhiều câu lệnh có thể rollback nhất quán.
- Kiểm soát truy cập đồng thời của nhiều người dùng.
- Chỉ mục chuyên dụng hỗ trợ tìm kiếm.
- Phân quyền cho từng người dùng hoặc đối tượng.
- Write-ahead log và quy trình khôi phục sau sự cố.

Có thể dùng CSV để xuất/nhập hoặc trao đổi dữ liệu, nhưng một hệ thống có nhiều luồng ghi đồng thời và quan hệ phức tạp thường cần nhiều hơn khả năng đọc/ghi một tệp.

## 4. Các thành phần cơ bản của dữ liệu quan hệ

### 4.1. Bảng, hàng, cột và kiểu dữ liệu

Bảng định nghĩa các cột và kiểu dữ liệu được chấp nhận:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Ý nghĩa:

| Thành phần | Tác dụng |
|---|---|
| `BIGINT` | Số nguyên có độ rộng lớn |
| `TEXT` | Chuỗi văn bản |
| `TIMESTAMPTZ` | Thời điểm có ngữ nghĩa múi giờ, được hiển thị theo timezone session |
| `NOT NULL` | Không cho phép giá trị `NULL` |
| `PRIMARY KEY` | Khóa chính xác định duy nhất hàng |
| `UNIQUE` | Không cho phép hai giá trị không-null trùng nhau theo quy tắc unique thông thường |
| `GENERATED ALWAYS AS IDENTITY` | PostgreSQL cấp giá trị nhận dạng qua cơ chế identity |
| `DEFAULT CURRENT_TIMESTAMP` | Giá trị mặc định là mốc thời gian hiện tại theo ngữ cảnh giao dịch |

PostgreSQL hỗ trợ nhiều kiểu khác như `BOOLEAN`, `NUMERIC`, `DATE`, `UUID`, `JSONB`, mảng, range, kiểu hình học và kiểu tự định nghĩa.

### 4.2. Khóa chính (primary key)

**Primary key** là một cột hoặc tập cột dùng để định danh duy nhất mỗi hàng. Trong PostgreSQL, ràng buộc primary key đồng thời yêu cầu không chứa `NULL` và tính duy nhất.

Ví dụ:

~~~sql
PRIMARY KEY (customer_id)
~~~

Không thể thêm một khách hàng với `customer_id` đã tồn tại vào cùng bảng nếu không sử dụng thao tác giải quyết xung đột phù hợp.

Khóa chính cũng được dùng thường xuyên trong các truy vấn tìm chính xác một bản ghi:

~~~sql
SELECT customer_name
FROM customers
WHERE customer_id = 1;
~~~

### 4.3. Khóa ngoại (foreign key)

Foreign key kiểm tra quan hệ giữa bảng con và bảng cha:

~~~sql
CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id),
    order_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Một đơn hàng không được tham chiếu đến một khách hàng không tồn tại, theo quy tắc ràng buộc và thời điểm kiểm tra được khai báo.

Điều này quan trọng vì nhiều ứng dụng có thể truy cập cùng cơ sở dữ liệu. Nếu mỗi ứng dụng tự kiểm tra bằng code mà bảng không có ràng buộc, một đường ghi khác có thể bỏ qua kiểm tra hoặc tạo ra dữ liệu không hợp lệ khi có truy cập đồng thời.

### 4.4. Các ràng buộc khác

Ví dụ một bảng sản phẩm:

~~~sql
CREATE TABLE products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    stock_qty INTEGER NOT NULL DEFAULT 0
        CHECK (stock_qty >= 0)
);
~~~

Các ràng buộc `CHECK` thể hiện quy tắc giá không âm và tồn kho không âm. `NUMERIC(12,2)` thích hợp cho ví dụ số tiền thập phân cần độ chính xác xác định; việc mô hình hóa tiền thực tế còn cần cân nhắc đơn vị tiền, quy tắc làm tròn và nhiều thuộc tính nghiệp vụ.

Không phải mọi quy tắc đều nên hoặc có thể biểu diễn chỉ bằng `CHECK`. Những quy tắc liên quan đến nhiều hàng, nhiều bảng hoặc trạng thái nghiệp vụ cần lựa chọn thiết kế transaction, foreign key, unique, exclusion constraint, trigger hoặc xử lý ứng dụng phù hợp.

## 5. SQL: ngôn ngữ làm việc với PostgreSQL

**SQL (Structured Query Language)** là ngôn ngữ khai báo: người viết mô tả dữ liệu muốn có hoặc thao tác cần thực hiện, thay vì chỉ định từng lần đọc trang đĩa.

Các nhóm câu lệnh cơ bản:

| Nhóm | Ví dụ | Mục đích |
|---|---|---|
| Định nghĩa dữ liệu (DDL) | `CREATE`, `ALTER`, `DROP` | Định nghĩa hoặc sửa cấu trúc |
| Thao tác dữ liệu (DML) | `INSERT`, `UPDATE`, `DELETE` | Thêm, sửa, xóa hàng |
| Truy vấn | `SELECT` | Đọc, lọc, nối, tổng hợp dữ liệu |
| Điều khiển giao dịch | `BEGIN`, `COMMIT`, `ROLLBACK` | Quản lý đơn vị thay đổi |
| Điều khiển truy cập | `GRANT`, `REVOKE` | Cấp hoặc thu hồi quyền |

Ví dụ:

~~~sql
-- Thêm khách hàng.
INSERT INTO customers (customer_name, email)
VALUES ('An', 'an@example.test');

-- Đọc danh sách.
SELECT customer_id, customer_name
FROM customers
ORDER BY customer_id;

-- Sửa email.
UPDATE customers
SET email = 'an.new@example.test'
WHERE customer_id = 1;

-- Xóa một hàng (chỉ thành công nếu các ràng buộc cho phép).
DELETE FROM customers
WHERE customer_id = 1;
~~~

`WHERE` rất quan trọng với `UPDATE` và `DELETE`. Bỏ `WHERE` có thể khiến mọi hàng trong bảng bị ảnh hưởng, nếu câu lệnh và quyền cho phép.

### 5.1. PostgreSQL triển khai SQL và bổ sung đặc điểm riêng

SQL có chuẩn chung, nhưng các RDBMS có những phần mở rộng, cú pháp và hành vi khác nhau. PostgreSQL cung cấp những tính năng như:

- `RETURNING` để nhận lại giá trị hàng vừa thêm/sửa/xóa.
- `INSERT ... ON CONFLICT` để xử lý tình huống vi phạm unique/exclusion arbiter phù hợp.
- Cú pháp ép kiểu `expression::type`.
- Các toán tử và hàm cho `JSONB`, mảng, range.
- `CREATE EXTENSION` để cài extension đã sẵn có trên server và được cho phép.

Không nên giả định một truy vấn viết cho MySQL, SQL Server hoặc SQLite luôn chạy nguyên xi trên PostgreSQL. Khác biệt có thể nằm ở kiểu dữ liệu, identity, phép nối chuỗi, cú pháp upsert, cách xử lý `NULL` hoặc hành vi DDL.

## 6. Kiến trúc client–server: ứng dụng nói chuyện với PostgreSQL ra sao?

Một ứng dụng thường kết nối đến PostgreSQL qua một **driver** hoặc chương trình khách.

~~~text
                 +------------------------+
                 |        Client          |
                 | Java / Python / Node   |
                 | psql / BI tool         |
                 +-----------+------------+
                             |
                     PostgreSQL protocol
                             |
                             v
                 +------------------------+
                 |   PostgreSQL server    |
                 |  xác thực kết nối      |
                 |  parse / plan / execute|
                 |  transaction / locks   |
                 +-----------+------------+
                             |
                 +-----------+------------+
                 |                        |
                 v                        v
           Bộ nhớ đệm               WAL + data files
           (shared buffers)          trên lưu trữ
~~~

Phía client gửi SQL và tham số; phía server kiểm tra quyền, phân tích câu lệnh, lập kế hoạch, thực thi rồi trả kết quả hoặc trạng thái lỗi.

PostgreSQL có kiến trúc truyền thống **một backend process phục vụ mỗi kết nối**. Vì vậy, tạo hàng nghìn kết nối độc lập không phải không có chi phí. Những ứng dụng có lưu lượng cao thường dùng **connection pool** để tái sử dụng kết nối và kiểm soát số phiên đang hoạt động.

### 6.1. Server, database, schema, table: bốn tầng khác nhau

Một PostgreSQL instance/cluster có thể phục vụ nhiều database. Mỗi database có nhiều schema; mỗi schema có thể chứa bảng, view, hàm và những đối tượng khác.

~~~text
PostgreSQL instance/cluster
|
+-- database: app_db
|      |
|      +-- schema: public
|      |      +-- table: customers
|      |
|      +-- schema: sales
|             +-- table: orders
|             +-- view: order_summary
|
+-- database: analytics_db
       |
       +-- schema: public
              +-- table: metrics
~~~

**Database** là ranh giới không gian tên và quản lý quan trọng. **Schema** là namespace bên trong một database. `public` là schema thường tồn tại mặc định, nhưng các schema khác giúp nhóm đối tượng và phân quyền.

Trong PostgreSQL, truy vấn SQL thông thường trong một kết nối truy cập dữ liệu thuộc database mà kết nối đó đang mở. Không thể mặc nhiên viết phép nối trực tiếp `app_db.sales.orders` với `analytics_db.public.metrics` như nối hai schema trong cùng một database. Nếu thật sự cần tích hợp cross-database, có những phương án riêng như FDW hoặc đồng bộ dữ liệu.

Một tên bảng đầy đủ bên trong database thường ở dạng:

~~~sql
SELECT *
FROM sales.orders;
~~~

`sales` là schema và `orders` là bảng.

### 6.2. search_path ảnh hưởng cách hiểu tên bảng

Khi viết:

~~~sql
SELECT * FROM orders;
~~~

PostgreSQL cần tìm tên `orders` trong các schema theo **`search_path`** hiện hành.

Kiểm tra:

~~~sql
SHOW search_path;
SELECT current_schema();
~~~

Để tránh mơ hồ trong ứng dụng có nhiều schema hoặc khi viết SQL dùng quyền cao, có thể dùng tên định danh đầy đủ `schema.table` hoặc quản lý `search_path` theo nguyên tắc rõ ràng. Điều này còn liên quan đến bảo mật đối với những đối tượng/hàm được phân giải qua namespace.

## 7. Vai trò thứ nhất: lưu trữ dữ liệu có cấu trúc

Một RDBMS giúp ứng dụng lưu dữ liệu theo một mô hình thống nhất. Mỗi bảng có kiểu cột, khóa và ràng buộc, nên việc ghi dữ liệu không chỉ là nối thêm văn bản vào cuối tệp.

Ví dụ PostgreSQL có thể từ chối:

~~~sql
INSERT INTO products
    (sku, product_name, unit_price, stock_qty)
VALUES
    ('BAD-001', 'Sản phẩm lỗi', -50000.00, 10);
~~~

Nếu bảng có `CHECK (unit_price >= 0)`, PostgreSQL không cho phép hàng vi phạm quy tắc này được lưu thành công.

Tương tự:

~~~sql
INSERT INTO customers (customer_name, email)
VALUES ('Bình', 'an@example.test');
~~~

có thể bị từ chối nếu đã tồn tại `email = 'an@example.test'` trong cột có ràng buộc `UNIQUE`.

Giá trị của engine là **quy tắc được áp dụng ở điểm ghi chung**, kể cả khi dữ liệu được gửi từ nhiều ứng dụng, một script quản trị hoặc một job nhập liệu.

### 7.1. PostgreSQL không thay thế thiết kế dữ liệu

Có RDBMS không đồng nghĩa mô hình tự nhiên trở nên tốt. Nếu gộp thông tin khách hàng, đơn hàng, hàng hóa và nhiều trạng thái vào một cột JSON tùy ý, hệ thống vẫn có thể gặp khó khăn với ràng buộc, truy vấn và bảo trì.

Lập trình viên cần xác định:

- Một thực thể được định danh bằng khóa nào?
- Các quan hệ một–nhiều, nhiều–nhiều được mô tả thế nào?
- Thuộc tính nào bắt buộc hoặc có thể `NULL`?
- Dữ liệu nào nên được chuẩn hóa thành bảng riêng?
- Những quy tắc nào phải được PostgreSQL thực thi?
- Các câu truy vấn quan trọng cần những index nào?

Hệ quản trị cung cấp công cụ; **mô hình dữ liệu phù hợp** vẫn là trách nhiệm thiết kế.

## 8. Vai trò thứ hai: truy vấn và kết hợp dữ liệu

Một lợi thế lớn của cơ sở dữ liệu quan hệ là **truy vấn kết hợp nhiều bảng** mà không phải lấy tất cả dữ liệu về ứng dụng rồi tự lắp ghép.

Giả sử có bảng khách hàng `customers` và đơn hàng `orders`. Muốn biết khách hàng nào có những đơn nào:

~~~sql
SELECT
    c.customer_name,
    o.order_id,
    o.order_status
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_name, o.order_id;
~~~

`JOIN` ghép các hàng theo điều kiện quan hệ. PostgreSQL sẽ lựa chọn phương án thực thi thích hợp, có thể là nested loop, hash join hoặc merge join tùy dữ liệu và truy vấn.

### 8.1. Lọc, sắp xếp và giới hạn

~~~sql
SELECT
    order_id,
    customer_id,
    created_at
FROM orders
WHERE order_status = 'paid'
ORDER BY created_at DESC
LIMIT 20;
~~~

Câu lệnh mô tả yêu cầu: tìm các đơn đã thanh toán, sắp theo ngày mới nhất và trả tối đa 20 hàng. Không có `ORDER BY`, thứ tự trả về của kết quả SQL **không được bảo đảm**.

### 8.2. Tổng hợp số liệu

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY order_count DESC;
~~~

`GROUP BY` gom hàng theo khách hàng; `COUNT(*)` tính số đơn; `HAVING` lọc các nhóm có ít nhất hai đơn.

Đây là những thao tác có thể diễn đạt gọn bằng SQL và được server thực hiện gần nơi lưu dữ liệu.

### 8.3. PostgreSQL có thể hỗ trợ truy vấn rất phức tạp

Ngoài những câu SQL cơ bản, PostgreSQL còn hỗ trợ:

- Common table expression với `WITH`.
- Window functions như `ROW_NUMBER()`, `RANK()`, `SUM() OVER (... )`.
- CTE đệ quy với `WITH RECURSIVE`.
- Subquery, set operations và các dạng tổng hợp.
- Views để tạo giao diện truy vấn có tên.
- Materialized views để lưu trước kết quả truy vấn và làm mới theo cơ chế phù hợp.

Nhưng một câu truy vấn viết được chưa chắc tối ưu. Vai trò của engine là lập kế hoạch và thực thi; lập trình viên vẫn cần mô hình dữ liệu, index và cách sử dụng tài nguyên phù hợp.

## 9. Vai trò thứ ba: quản lý giao dịch theo ACID

**Transaction (giao dịch)** là một nhóm thao tác SQL được PostgreSQL quản lý như một đơn vị nhất quán. Một giao dịch có thể được xác nhận bằng `COMMIT` hoặc bị hủy bằng `ROLLBACK`.

Ví dụ chuyển 100 đơn vị số dư giữa hai tài khoản:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Đây là ví dụ minh họa: trong hệ thống tiền tệ thật phải kiểm tra số hàng bị tác động, số dư, quyền giao dịch và các điều kiện đồng thời phù hợp. Nếu không, hai câu SQL đúng cú pháp vẫn có thể ghi dữ liệu sai nghiệp vụ.

Giao dịch có bốn nhóm tính chất thường được gọi là **ACID**:

| Chữ | Tên | Ý nghĩa thực hành |
|---|---|---|
| **A** | Atomicity — Tính nguyên tử | Các thay đổi của transaction được xác nhận như một đơn vị; khi rollback, thay đổi của transaction không được giữ lại |
| **C** | Consistency — Tính nhất quán | Các ràng buộc được khai báo được duy trì theo quy tắc của DBMS; tính đúng nghiệp vụ còn phụ thuộc logic ứng dụng |
| **I** | Isolation — Tính cô lập | Các transaction đồng thời nhìn thấy và tác động lên dữ liệu theo mức cô lập được chọn |
| **D** | Durability — Tính bền vững | Transaction được commit có cơ chế lưu trữ/khôi phục để tồn tại qua sự cố trong phạm vi bảo đảm và cấu hình hệ thống |

### 9.1. Vì sao cần rollback?

Ví dụ đặt hàng có hai bước:

1. Tạo đơn hàng.
2. Trừ tồn kho sản phẩm.

Nếu bước 2 thất bại, hệ thống không nên để lại một đơn đã xác nhận mà không trừ tồn kho theo quy tắc nghiệp vụ.

~~~sql
BEGIN;

-- Ví dụ giả định các bảng/khóa đã tồn tại.
INSERT INTO orders (customer_id, order_status)
VALUES (1, 'pending');

UPDATE products
SET stock_qty = stock_qty - 1
WHERE product_id = 1
  AND stock_qty >= 1;

-- Ứng dụng phải kiểm tra kết quả UPDATE trước khi quyết định.
-- Nếu đủ điều kiện nghiệp vụ:
COMMIT;

-- Nếu một bước quan trọng không đạt yêu cầu, dùng ROLLBACK.
~~~

**Điểm cần nhớ:** điều kiện `stock_qty >= 1` làm cho bước trừ tồn chỉ xảy ra khi hàng đáp ứng điều kiện; nhưng nếu `UPDATE` tác động **0 hàng**, PostgreSQL không tự suy ra “đơn hàng phải rollback”. Ứng dụng phải kiểm tra kết quả và điều khiển transaction.

### 9.2. PostgreSQL hỗ trợ DDL trong giao dịch

PostgreSQL cho phép nhiều thao tác DDL thông dụng như `CREATE TABLE` hoặc `ALTER TABLE` nằm trong transaction và được rollback nếu transaction rollback, với những ngoại lệ.

Ví dụ:

~~~sql
BEGIN;

CREATE TABLE temporary_design_demo (
    id BIGINT PRIMARY KEY
);

ROLLBACK;
~~~

Sau rollback, bảng vừa tạo không còn tồn tại như một thay đổi đã commit trong database.

Không phải mọi lệnh quản trị đều được phép trong transaction block. Chẳng hạn `CREATE DATABASE` và một số thao tác đặc biệt có các hạn chế riêng. Đừng suy luận rằng **mọi** lệnh DDL hay bảo trì của PostgreSQL đều chạy được trong `BEGIN ... COMMIT`.

## 10. Vai trò thứ tư: xử lý truy cập đồng thời bằng MVCC và khóa

Hãy tưởng tượng hai nhân viên cùng mở một hồ sơ khách hàng trong lúc nhân viên thứ ba sửa số điện thoại. Hệ thống cần quy tắc để tránh người đọc nhìn thấy dữ liệu bị ghi dở, đồng thời ngăn những cập nhật xung đột.

PostgreSQL dùng **MVCC — Multi-Version Concurrency Control**, tức kiểm soát đồng thời qua nhiều phiên bản dữ liệu.

Ý tưởng trực quan:

~~~text
Transaction A đọc hàng H
        |
        +--> nhìn một phiên bản phù hợp với snapshot của A

Transaction B cập nhật H
        |
        +--> tạo trạng thái/phiên bản mới theo quy tắc MVCC

Transaction A tiếp tục đọc
        |
        +--> điều gì được thấy tùy mức cô lập/snapshot
~~~

MVCC giúp nhiều thao tác đọc không nhất thiết phải chặn thao tác ghi thông thường, nhưng **không có nghĩa PostgreSQL không bao giờ dùng khóa**. Thao tác ghi vẫn có row-level locks; DDL có thể cần khóa trên quan hệ; một số câu SQL yêu cầu locking cụ thể.

### 10.1. Mức cô lập giao dịch

Trong PostgreSQL, những mức cô lập được biết đến gồm:

- **READ COMMITTED:** mặc định trong cấu hình thông thường; mỗi câu lệnh nhìn snapshot phù hợp khi bắt đầu câu lệnh.
- **REPEATABLE READ:** các câu truy vấn trong transaction dùng snapshot nhất quán theo quy tắc của mức cô lập; có thể phát sinh lỗi serialization với một số cạnh tranh.
- **SERIALIZABLE:** PostgreSQL phát hiện các xung đột có thể phá tính tuần tự và có thể hủy một transaction với lỗi cần retry.

PostgreSQL cũng chấp nhận tên `READ UNCOMMITTED`, nhưng thực thi tương đương `READ COMMITTED` trong PostgreSQL; không cung cấp đọc dữ liệu chưa commit theo cách nhiều người hình dung.

Dù chọn mức cô lập nào, một ứng dụng nhiều transaction vẫn cần kiểm soát **retry**, khóa hợp lý và xử lý các điều kiện nghiệp vụ. Không nên diễn giải MVCC là cơ chế tự động bảo đảm mọi tổ hợp đọc–ghi đồng thời đều đúng ý nghiệp vụ.

### 10.2. Tồn kho và cập nhật cạnh tranh

Một mẫu cập nhật tồn kho an toàn hơn so với “đọc số lượng, tính trong ứng dụng, ghi đè”:

~~~sql
UPDATE products
SET stock_qty = stock_qty - 2
WHERE product_id = 1
  AND stock_qty >= 2
RETURNING product_id, stock_qty;
~~~

Nếu không có hàng được trả về, không có cập nhật đáp ứng điều kiện. Ứng dụng phải xử lý kết quả này như hết hàng hoặc sản phẩm không tồn tại tùy logic.

`RETURNING` là tính năng thuận tiện của PostgreSQL: câu `UPDATE` có thể trả về giá trị hàng vừa thay đổi, giúp giảm một bước truy vấn riêng trong nhiều tình huống.

## 11. Vai trò thứ năm: ghi bền vững và phục hồi với WAL

Ghi dữ liệu ra đĩa không đơn giản là gọi một lệnh `save</BT> rồi luôn an toàn. Nếu máy chủ ngừng đột ngột giữa giao dịch, hệ thống cần biết những thay đổi nào đã được xác nhận và cách khôi phục trạng thái nhất quán.

PostgreSQL sử dụng **WAL — Write-Ahead Logging**. Theo nguyên tắc viết trước, những thông tin log cần thiết được ghi một cách thích hợp trước khi các thay đổi của trang dữ liệu được xem là bền vững theo cơ chế của engine.

~~~text
Ứng dụng ghi dữ liệu
       |
       v
Thay đổi trong bộ nhớ / buffer
       |
       +--> WAL records
       |
       v
COMMIT theo chính sách durability
       |
       v
Các trang dữ liệu được ghi xuống lưu trữ theo thời gian
       |
       v
Nếu restart sau sự cố:
   PostgreSQL dùng WAL để phục hồi trạng thái nhất quán
~~~

WAL phục vụ:

- **Crash recovery** sau ngừng hoạt động bất ngờ.
- Cơ chế duy trì tính bền vững của transaction.
- Nền tảng cho một số cơ chế sao chép và khôi phục theo thời điểm.
- Hỗ trợ các quá trình checkpoint/ghi dữ liệu của PostgreSQL.

Tuy nhiên, **WAL không phải bản sao lưu độc lập**. Nếu dữ liệu bị xóa hợp lệ nhưng sai nghiệp vụ, hoặc toàn bộ ổ lưu trữ bị mất, riêng những WAL hiện có có thể không đủ để khôi phục đúng mục tiêu. Hệ thống vận hành cần kế hoạch backup, retention và kiểm tra restore.

### 11.1. Độ bền phụ thuộc cấu hình và hạ tầng

Khả năng bền vững không nên được hiểu là “dữ liệu không thể mất trong mọi sự cố”. Những thiết lập như `synchronous_commit`, cấu hình lưu trữ, chất lượng thiết bị, vận hành và phạm vi sự cố ảnh hưởng tới bảo đảm thực tế.

Bên cạnh thiết kế transaction, người vận hành cần đảm bảo:

- Có backup độc lập và kiểm tra phục hồi.
- Đảm bảo dung lượng đĩa cho WAL và dữ liệu.
- Giám sát tình trạng máy chủ và hệ thống lưu trữ.
- Hiểu thời gian gián đoạn và mức mất dữ liệu tối đa chấp nhận được.

## 12. Vai trò thứ sáu: tối ưu truy vấn bằng planner và index

Khi bảng có hàng triệu hàng, đọc tuần tự mọi hàng cho từng truy vấn có thể không phù hợp. PostgreSQL sử dụng **query planner/optimizer** để ước lượng chi phí và chọn kế hoạch thực thi.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC);
~~~

Chỉ mục B-tree này có thể hữu ích cho truy vấn:

~~~sql
SELECT order_id, created_at, order_status
FROM orders
WHERE customer_id = 1
ORDER BY created_at DESC
LIMIT 20;
~~~

Nhưng PostgreSQL **không bắt buộc** dùng một chỉ mục chỉ vì nó tồn tại. Với bảng rất nhỏ, điều kiện chọn lọc thấp hoặc thống kê cụ thể, planner có thể chọn sequential scan.

### 12.1. Các loại index thường gặp

| Loại | Trường hợp sử dụng điển hình |
|---|---|
| **B-tree** | Bằng, khoảng giá trị, sắp xếp theo khóa phù hợp |
| **Hash** | Một số phép so sánh bằng trong trường hợp thích hợp |
| **GIN** | Tìm nhiều khóa/phần tử trong cấu trúc như mảng hoặc `JSONB`; cũng được dùng trong một số extension |
| **GiST** | Những cấu trúc/tìm kiếm đặc thù như hình học, range và extension phù hợp |
| **BRIN** | Tóm tắt vùng trang cho bảng rất lớn có tương quan vật lý với giá trị khóa |
| **SP-GiST** | Một số cách phân hoạch không gian/tập dữ liệu chuyên biệt |

Đây là định hướng chứ không phải quy tắc tuyệt đối. Loại index có dùng được hay không còn phụ thuộc toán tử, kiểu dữ liệu, operator class và đặc tính truy vấn.

### 12.2. EXPLAIN cho biết điều gì?

~~~sql
EXPLAIN
SELECT order_id, created_at
FROM orders
WHERE customer_id = 1;
~~~

`EXPLAIN` cho biết kế hoạch được PostgreSQL dự kiến sử dụng, như sequential scan, index scan, bitmap heap scan và ước lượng số hàng/chi phí.

Khi muốn đo việc thực thi thật:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE customer_id = 1;
~~~

**`ANALYZE` trong `EXPLAIN (ANALYZE)` thực sự chạy câu SQL**. Với truy vấn đọc trên bảng nhỏ điều này thường đơn giản, nhưng trên hệ thống thật cần chú ý tài nguyên; với câu DML, lệnh có thể **thực sự thay đổi dữ liệu** nếu không được tổ chức an toàn. Không xem `EXPLAIN ANALYZE UPDATE/DELETE` như một thao tác chỉ đọc.

### 12.3. VACUUM và ANALYZE có vai trò gì?

Do MVCC giữ các phiên bản hàng theo cơ chế của engine, PostgreSQL cần **VACUUM/autovacuum** để thu hồi khả năng tái sử dụng không gian của những tuple đã chết và hỗ trợ sức khỏe lưu trữ lâu dài. **ANALYZE** cập nhật thống kê để planner ước lượng và chọn kế hoạch.

Đây là công việc vận hành quan trọng nhưng không phải điều ứng dụng cần chạy sau từng câu `INSERT`. PostgreSQL có những tiến trình và cấu hình bảo trì tự động; khi tải dữ liệu lớn hoặc có vấn đề đặc biệt, người vận hành cần kiểm tra cấu hình và số liệu.

## 13. Vai trò thứ bảy: quản lý người dùng, quyền và chính sách truy cập

Không phải ứng dụng nào cũng được phép đọc toàn bộ bảng hoặc thay đổi mọi đối tượng. PostgreSQL sử dụng **roles** cho quản lý danh tính và phân quyền.

Ví dụ cú pháp quản trị trong môi trường thử nghiệm:

~~~sql
-- Chỉ quản trị viên có quyền phù hợp mới chạy được.
CREATE ROLE app_reader LOGIN PASSWORD 'use-a-strong-secret';

GRANT CONNECT ON DATABASE app_db TO app_reader;
GRANT USAGE ON SCHEMA sales TO app_reader;
GRANT SELECT ON sales.orders TO app_reader;
~~~

Điều này mô tả tài khoản ứng dụng có quyền kết nối database, sử dụng schema và đọc bảng cụ thể. Trong hệ thống thật, password phải do cơ chế quản lý bí mật bảo vệ, không dùng chuỗi ví dụ trong repository.

Các quyền thường gặp:

| Quyền | Tác dụng điển hình |
|---|---|
| `CONNECT` | Cho phép kết nối một database |
| `USAGE` trên schema | Cho phép giải quyết tên/tiếp cận đối tượng theo các quyền tiếp theo |
| `SELECT` | Đọc dữ liệu bảng/view |
| `INSERT`, `UPDATE`, `DELETE` | Thay đổi hàng |
| `CREATE` trên schema | Tạo đối tượng trong schema |
| `EXECUTE` | Gọi function/procedure phù hợp |

Các lệnh `GRANT` phải được xét với chủ sở hữu, quyền mặc định, role membership và chính sách từng database/schema. Không nên cấp `SUPERUSER` cho ứng dụng thông thường.

### 13.1. Row-Level Security (RLS)

PostgreSQL có tính năng **Row-Level Security** cho phép khai báo chính sách kiểm soát những hàng được nhìn thấy hoặc thay đổi trong một bảng, khi được bật và cấu hình đúng.

Đây có thể là công cụ hữu ích với ứng dụng nhiều tổ chức/tenant. Nhưng RLS không tự biết người dùng web là ai: kiến trúc ứng dụng vẫn cần truyền danh tính/ngữ cảnh đáng tin cậy, cấp quyền và kiểm soát việc bypass chính sách.

Cần hiểu đúng các ngoại lệ về chủ bảng, superuser và role có khả năng bypass RLS; không xem việc bật RLS là bảo đảm tuyệt đối nếu còn các đường truy cập quyền cao.

## 14. PostgreSQL có thể phục vụ nhiều kiểu dữ liệu

Dù trọng tâm là quan hệ, PostgreSQL không chỉ giới hạn ở cột số và văn bản thuần.

### 14.1. JSONB: dữ liệu bán cấu trúc

Ví dụ:

~~~sql
CREATE TABLE event_logs (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Ghi dữ liệu:

~~~sql
INSERT INTO event_logs (event_type, payload)
VALUES
(
    'order_created',
    '{"order_id": 101, "channel": "web", "items": 2}'::jsonb
);
~~~

Truy vấn thuộc tính:

~~~sql
SELECT
    event_id,
    payload ->> 'channel' AS channel
FROM event_logs
WHERE payload ->> 'channel' = 'web';
~~~

`JSONB` cho phép lưu và truy vấn tài liệu JSON dưới dạng nhị phân được PostgreSQL xử lý. Nó thuận tiện cho thuộc tính biến đổi, cấu trúc event hoặc dữ liệu tích hợp.

Nhưng nếu mọi quan hệ cốt lõi đều được đẩy vào JSON, hệ thống có thể khó duy trì foreign key, kiểm soát kiểu chặt chẽ và JOIN theo mô hình thông thường. **Sử dụng JSONB đúng chỗ** thường là kết hợp cột quan hệ cho thông tin lõi với JSONB cho phần linh hoạt, không phải xóa bỏ mô hình quan hệ.

### 14.2. UUID, array và range

PostgreSQL hỗ trợ:

- `UUID` cho định danh.
- Kiểu mảng như `INTEGER[]`.
- Kiểu range như `daterange` hay `tstzrange`.
- Một số kiểu và toán tử chuyên biệt cho tìm kiếm và xử lý dữ liệu.

Các kiểu này có thể giúp diễn đạt bài toán rõ hơn, nhưng cần lựa chọn theo truy vấn thực tế và khả năng duy trì ràng buộc.

### 14.3. Extension

PostgreSQL hỗ trợ cơ chế **extension**, ví dụ:

- **PostGIS:** bổ sung các chức năng không gian địa lý khi được cài đặt và cấp quyền.
- **pg_trgm:** hỗ trợ nhiều thao tác đối sánh văn bản dựa trên trigram, có thể kết hợp với index.
- Các extension khác tùy bản phân phối, nhà cung cấp và chính sách vận hành.

Không phải extension nào cũng có sẵn hoặc được phép cài trên mọi dịch vụ PostgreSQL. Khả năng sử dụng phụ thuộc phiên bản, gói đã triển khai, đặc quyền và chính sách hạ tầng.

## 15. Thực hành khởi đầu: từ schema đến truy vấn có quan hệ

Phần này xây một ví dụ có thể chạy tuần tự trong một **database thử nghiệm** PostgreSQL 12+ mà tài khoản của bạn được phép tạo schema và bảng. Không chạy trên schema production.

Để tránh phụ thuộc quyền tạo database hoặc tên bảng `public` đã có, ví dụ sử dụng schema riêng `pg_intro` trong **database bạn đang kết nối**.

### 15.1. Kiểm tra phiên bản và database hiện tại

Trong `psql` hoặc công cụ SQL:

~~~sql
SELECT version();
SELECT current_database();
SELECT current_user;
SELECT current_schema();
~~~

Nếu dùng `psql`, câu lệnh:

~~~text
\conninfo
~~~

giúp xem thông tin kết nối hiện tại. Đây là **meta-command của psql**, không phải SQL; đừng gửi `\conninfo` qua JDBC như một câu truy vấn server.

### 15.2. Tạo schema

~~~sql
CREATE SCHEMA IF NOT EXISTS pg_intro;
~~~

Để các câu SQL bên dưới rõ ràng, ta sử dụng tên bảng đầy đủ `pg_intro.table_name`. Vì vậy không cần thay đổi `search_path` của session.

### 15.3. Tạo bảng

~~~sql
CREATE TABLE pg_intro.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
);

CREATE TABLE pg_intro.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    stock_qty INTEGER NOT NULL DEFAULT 0
        CHECK (stock_qty >= 0)
);

CREATE TABLE pg_intro.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES pg_intro.customers(customer_id),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pg_intro.order_items (
    order_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES pg_intro.orders(order_id),
    product_id BIGINT NOT NULL
        REFERENCES pg_intro.products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0)
);
~~~

Mô hình gồm:

~~~text
customers (1) ----- (N) orders
                          |
                          | (1)
                          |
                          v
                  order_items (N)
                          |
                          | (N)
                          |
                  products (1)
~~~

Bảng `order_items` liên kết đơn hàng với các sản phẩm; mỗi dòng thể hiện một sản phẩm và số lượng trong đơn. Giá được lưu trên dòng đơn hàng để giữ **giá tại thời điểm giao dịch**, thay vì luôn phụ thuộc vào giá hiện tại trong `products`.

### 15.4. Thêm dữ liệu thử nghiệm

~~~sql
INSERT INTO pg_intro.customers (full_name, email)
VALUES
    ('An', 'an@example.test'),
    ('Bình', 'binh@example.test')
RETURNING customer_id, full_name;

INSERT INTO pg_intro.products
    (sku, product_name, unit_price, stock_qty)
VALUES
    ('BK-01', 'Notebook', 50000.00, 20),
    ('PN-02', 'Pen',      12000.00, 40)
RETURNING product_id, sku;

INSERT INTO pg_intro.orders (customer_id, status)
VALUES
    (1, 'paid'),
    (1, 'pending'),
    (2, 'paid')
RETURNING order_id, customer_id, status;

INSERT INTO pg_intro.order_items
    (order_id, product_id, quantity, unit_price)
VALUES
    (1, 1, 2, 50000.00),
    (1, 2, 3, 12000.00),
    (2, 2, 1, 12000.00),
    (3, 1, 1, 50000.00);
~~~

Các tham chiếu `1`, `2`, `3` ở phần `order_items` dựa trên giả định bảng mới tạo và chưa có lần chèn/xóa trước đó. Khi làm lại bài trên bảng đã có dữ liệu, **đừng giả định identity luôn bắt đầu lại từ 1**. Hãy dùng ID thực tế được trả về bởi `RETURNING` hoặc truy vấn theo khóa nghiệp vụ.

### 15.5. Truy vấn kết hợp dữ liệu

~~~sql
SELECT
    o.order_id,
    c.full_name AS customer_name,
    o.status,
    o.created_at
FROM pg_intro.orders AS o
JOIN pg_intro.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

Câu truy vấn kết hợp dữ liệu từ hai bảng theo quan hệ khóa ngoại.

### 15.6. Tính tổng tiền theo đơn

~~~sql
SELECT
    o.order_id,
    c.full_name,
    o.status,
    SUM(oi.quantity * oi.unit_price) AS total_amount
FROM pg_intro.orders AS o
JOIN pg_intro.customers AS c
    ON c.customer_id = o.customer_id
JOIN pg_intro.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    c.customer_id
ORDER BY o.order_id;
~~~

Kết quả kỳ vọng từ dữ liệu mẫu:

| order_id | full_name | status | total_amount |
|---:|---|---|---:|
| 1 | An | paid | 136000.00 |
| 2 | An | pending | 12000.00 |
| 3 | Bình | paid | 50000.00 |

Câu này dùng `JOIN`, `GROUP BY` và `SUM` để tạo báo cáo từ dữ liệu chi tiết. Với khóa chính phù hợp, PostgreSQL nhận biết một số quan hệ phụ thuộc hàm trong quá trình kiểm tra nhóm, nhưng khi muốn câu SQL dễ chuyển giữa các RDBMS hoặc khó phân tích hơn, nên nhóm những cột cần thiết theo ý nghĩa kết quả.

### 15.7. Xem dữ liệu của khách chưa có đơn

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count
FROM pg_intro.customers AS c
LEFT JOIN pg_intro.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

`LEFT JOIN` giữ hàng khách hàng ngay cả khi không có đơn phù hợp. Dùng `COUNT(o.order_id)` thay vì `COUNT(*)` giúp đếm số đơn thật trong trường hợp `LEFT JOIN` vẫn tạo một hàng với các cột của `orders` là `NULL`.

Đây là ví dụ cho thấy **độ đúng của phép tổng hợp phụ thuộc hiểu mô hình quan hệ**, không chỉ khả năng chạy được câu SQL.

## 16. Trải nghiệm giao dịch và rollback

Sau khi có dữ liệu mẫu, ta thử một thay đổi có thể hoàn tác.

~~~sql
BEGIN;

UPDATE pg_intro.products
SET stock_qty = stock_qty - 2
WHERE sku = 'BK-01'
  AND stock_qty >= 2
RETURNING sku, stock_qty;

-- Kiểm tra trong cùng transaction.
SELECT sku, stock_qty
FROM pg_intro.products
WHERE sku = 'BK-01';

ROLLBACK;
~~~

Nếu trước đó có 20 chiếc notebook, câu `UPDATE` tạm cho thấy 18. Sau `ROLLBACK`, khi kiểm tra lại bên ngoài transaction, số lượng vẫn là 20:

~~~sql
SELECT sku, stock_qty
FROM pg_intro.products
WHERE sku = 'BK-01';
~~~

Đó là ví dụ nhỏ của tính **nguyên tử**. Trong sản phẩm thực tế, transaction có thể gồm nhiều thao tác và cần quản lý lỗi, timeout và retry.

### 16.1. Khi nào dùng COMMIT?

Nếu quy tắc nghiệp vụ hợp lệ và bạn muốn giữ thay đổi:

~~~sql
BEGIN;

UPDATE pg_intro.products
SET stock_qty = stock_qty - 1
WHERE sku = 'PN-02'
  AND stock_qty >= 1
RETURNING sku, stock_qty;

-- Chỉ COMMIT khi điều kiện nghiệp vụ đã được kiểm tra.
COMMIT;
~~~

Câu ví dụ sẽ lưu thay đổi nếu hàng được cập nhật và transaction commit thành công. Nếu câu `UPDATE` không trả hàng, ứng dụng phải xử lý việc không có hàng phù hợp thay vì tự động giả định thành công.

**Tại ứng dụng Java/JDBC:** thường dùng `Connection#setAutoCommit(false)`, sau đó `commit()` hoặc `rollback()` theo kết quả các bước. Việc xử lý ngoại lệ phải đảm bảo không để connection trong trạng thái transaction lỗi hoặc bị giữ lâu ngoài ý muốn.

## 17. Tạo chỉ mục và quan sát kế hoạch

Bảng đơn hàng thường được tra cứu theo khách hàng và thời gian. Có thể thêm index:

~~~sql
CREATE INDEX idx_pg_intro_orders_customer_created
ON pg_intro.orders (customer_id, created_at DESC);
~~~

Sau đó:

~~~sql
EXPLAIN
SELECT order_id, created_at, status
FROM pg_intro.orders
WHERE customer_id = 1
ORDER BY created_at DESC;
~~~

Vì bài lab chỉ có vài hàng, PostgreSQL có thể chọn `Seq Scan` thay vì `Index Scan`. Điều đó không chứng minh index sai hoặc planner bị lỗi: trên bảng nhỏ, quét bảng có thể rẻ hơn đọc index.

Để đánh giá một chỉ mục có hiệu quả, cần:

1. Hiểu các điều kiện lọc/sắp xếp chính.
2. Xem lượng dữ liệu và phân bố giá trị.
3. Đọc `EXPLAIN` hoặc `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường an toàn.
4. Tính tới chi phí ghi, dung lượng và bảo trì index.

**Thêm index không phải là thao tác miễn phí**: khi `INSERT/UPDATE/DELETE`, PostgreSQL cũng phải duy trì cấu trúc chỉ mục liên quan.

## 18. Quan sát PostgreSQL bằng catalog và các view thống kê

Ngoài dữ liệu nghiệp vụ, PostgreSQL cung cấp **system catalogs** và **statistics views** để quan sát cấu trúc, hoạt động và hiệu năng.

Một số câu truy vấn đọc hữu ích:

~~~sql
-- Database hiện tại.
SELECT current_database();

-- Phiên bản server.
SHOW server_version;

-- Kích thước database hiện tại.
SELECT pg_size_pretty(pg_database_size(current_database()))
       AS database_size;

-- Kích thước tổng của bảng và index.
SELECT pg_size_pretty(
    pg_total_relation_size('pg_intro.orders')
) AS orders_total_size;
~~~

Khi bảng đã tồn tại, `pg_total_relation_size` cho biết tổng dung lượng quan hệ cùng index và các thành phần liên quan theo cách tính của PostgreSQL. Con số này **không phải** số byte dữ liệu nghiệp vụ thuần.

Xem hoạt động một số bảng người dùng:

~~~sql
SELECT
    schemaname,
    relname,
    seq_scan,
    idx_scan,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'pg_intro'
ORDER BY relname;
~~~

Các trường `n_live_tup` và `n_dead_tup` là **ước lượng thống kê**, không thay cho số đếm chính xác. Những con số thống kê cũng có chu kỳ cập nhật/reset; không nên coi là toàn bộ lịch sử server.

Xem một số phiên đang hoạt động:

~~~sql
SELECT
    pid,
    datname,
    usename,
    state,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database();
~~~

Thông tin nhìn thấy phụ thuộc đặc quyền của tài khoản. Không phải mọi tài khoản đều được xem toàn bộ nội dung truy vấn của phiên khác.

## 19. Công cụ làm việc với PostgreSQL

### 19.1. psql

**`psql`** là client dòng lệnh phổ biến của PostgreSQL. Một lệnh kết nối thường có dạng:

~~~bash
psql -h localhost -p 5432 -U app_user -d app_db
~~~

Trong đó:

| Tùy chọn | Ý nghĩa |
|---|---|
| `-h` | Host hoặc địa chỉ server |
| `-p` | Cổng kết nối, mặc định thông dụng là 5432 |
| `-U` | Tên role đăng nhập |
| `-d` | Tên database |

Các lệnh bắt đầu bằng dấu `\</BT> trong psql là **meta-command của client**:

~~~text
\l            Liệt kê database
\dn           Liệt kê schema
\dt           Liệt kê bảng trong phạm vi tìm kiếm
\d pg_intro.orders
              Mô tả cấu trúc bảng
\conninfo     Hiển thị kết nối hiện tại
\q            Thoát psql
~~~

Đây không phải câu SQL chuẩn có thể gửi nguyên văn qua mọi driver.

### 19.2. pgAdmin và công cụ đồ họa

**pgAdmin** là một công cụ đồ họa trong hệ sinh thái PostgreSQL để duyệt đối tượng, chạy SQL và thực hiện một số công việc quản trị. Các công cụ phổ biến khác có thể kết nối thông qua driver PostgreSQL.

Dù dùng GUI, người học vẫn nên hiểu SQL, transaction và quyền. Một thao tác “Save” trên màn hình quản trị có thể phát sinh `ALTER TABLE`, `UPDATE` hoặc các câu lệnh có tác động lớn.

### 19.3. Driver ứng dụng

Ứng dụng Java thường dùng **PostgreSQL JDBC Driver**; Python có thể sử dụng driver tương thích, và các ngôn ngữ khác có thư viện kết nối riêng.

Mẫu Java đơn giản:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class ReadCustomers {
    public static void main(String[] args) throws Exception {
        // Trong ứng dụng thật, lấy cấu hình và secret từ môi trường an toàn.
        String url = "jdbc:postgresql://localhost:5432/app_db";
        String user = "app_reader";
        String password = "replace-with-secret";

        String sql = """
            SELECT customer_id, full_name
            FROM pg_intro.customers
            WHERE customer_id = ?
            """;

        try (Connection conn = DriverManager.getConnection(
                    url, user, password);
             PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, 1L);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    System.out.println(
                        rs.getLong("customer_id") + ": "
                        + rs.getString("full_name")
                    );
                }
            }
        }
    }
}
~~~

Code minh họa cần driver JDBC có trên classpath và database, role, bảng tương ứng phải tồn tại. Không hard-code password thật trong mã nguồn sản phẩm; dùng secret manager và cấu hình môi trường.

**PreparedStatement** giúp truyền giá trị làm tham số tách khỏi cú pháp SQL. Nó không tự bảo đảm phân quyền hoặc ngăn mọi lỗi logic, nhưng là công cụ quan trọng để giảm nguy cơ SQL injection khi dùng đúng.

## 20. PostgreSQL hỗ trợ vận hành và phát triển hệ thống ra sao?

Một RDBMS trong sản xuất không chỉ cần chạy câu `SELECT`. Nhiều vấn đề vận hành xuất hiện theo thời gian.

### 20.1. Sao lưu và phục hồi

PostgreSQL có các phương pháp backup ở mức logic hoặc vật lý, ví dụ:

- `pg_dump` để xuất dữ liệu và cấu trúc ở mức logic.
- Các phương án backup vật lý và quản lý WAL thích hợp.
- Cơ chế **Point-In-Time Recovery (PITR)** khi triển khai chuỗi backup và WAL archive phù hợp.

Không nên xem việc chạy một lệnh dump là đủ cho mọi mục tiêu khôi phục. Cần đặt **RPO** (mức mất dữ liệu tối đa chấp nhận) và **RTO** (thời gian phục hồi mục tiêu), sau đó kiểm tra khả năng restore.

### 20.2. Replication và tính sẵn sàng

PostgreSQL hỗ trợ nhiều cơ chế sao chép dữ liệu, gồm **streaming/physical replication** và **logical replication** trong các cấu hình phù hợp.

Replication giúp triển khai replica phục vụ các mục tiêu như dự phòng, phân phối tải đọc hoặc tích hợp dữ liệu, nhưng không tự thay thế backup. Một lỗi xóa dữ liệu hợp lệ có thể được sao chép sang replica.

Để có **high availability**, còn cần công cụ/phương án phát hiện lỗi, chuyển vai trò, điều phối kết nối, xử lý split-brain và thử nghiệm tình huống failover. Không nên khẳng định chỉ bật replication là có một cụm HA hoàn chỉnh.

### 20.3. Nâng cấp và thay đổi lược đồ

Trong vòng đời dài, ứng dụng sẽ thêm cột, tạo index, đổi ràng buộc hoặc nâng phiên bản PostgreSQL. Các thay đổi này có thể có chi phí khóa, I/O và rủi ro tương thích.

Nguyên tắc chung:

- Dùng migration được quản lý phiên bản.
- Kiểm tra dữ liệu hiện tại trước khi thêm constraint.
- Ước lượng dung lượng/thời gian khi tạo index hoặc sửa kiểu cột.
- Cân nhắc các chiến lược hạn chế chặn ghi khi được hỗ trợ.
- Kiểm tra ứng dụng và công cụ kết nối sau nâng cấp.
- Có kế hoạch backup/rollback tương ứng với loại thay đổi.

### 20.4. Theo dõi hệ thống

Các chỉ số thực tế thường cần theo dõi:

| Nhóm | Ví dụ |
|---|---|
| Kết nối | Số backend connection, pool utilization |
| Giao dịch | Tốc độ commit/rollback, transaction dài |
| Truy vấn | Độ trễ, truy vấn chậm, kế hoạch thực thi |
| Khóa | Phiên đang chờ, deadlock |
| Lưu trữ | Dung lượng bảng/index, WAL, ổ đĩa trống |
| Bảo trì | VACUUM/autovacuum, dead tuples, statistics |
| Replication | Độ trễ replica, tình trạng WAL retention |
| Backup | Kết quả backup, thời gian restore, khả năng phục hồi |

Không có hệ quản trị nào tự loại bỏ nhu cầu giám sát và bảo trì. PostgreSQL có cơ chế tự động hữu ích, nhưng ứng dụng lớn vẫn cần người vận hành hiểu các dấu hiệu bất thường.

## 21. Khi nào PostgreSQL là lựa chọn phù hợp?

PostgreSQL thường là ứng viên mạnh khi hệ thống có những nhu cầu sau:

### 21.1. Dữ liệu có quan hệ rõ ràng

Ví dụ khách hàng–đơn hàng–chi tiết đơn–sản phẩm. Primary key, foreign key, unique và transaction giúp thực thi các quan hệ.

### 21.2. Quy tắc toàn vẹn quan trọng

Hệ thống thanh toán, kho hàng, lịch hẹn hoặc quản lý nhân sự thường cần tránh dữ liệu sai từ nhiều nguồn cập nhật. PostgreSQL có các ràng buộc và cơ chế giao dịch hữu ích cho yêu cầu này.

### 21.3. Truy vấn đa dạng

Hệ thống vừa phục vụ giao dịch theo khóa, vừa cần báo cáo tổng hợp, lọc theo nhiều tiêu chí và JOIN nhiều bảng có thể tận dụng khả năng SQL của PostgreSQL.

### 21.4. Cần phần mở rộng đặc thù

Ứng dụng xử lý dữ liệu địa lý có thể sử dụng PostGIS; ứng dụng chứa dữ liệu JSON linh hoạt có thể dùng JSONB; hệ thống cần phân tích dữ liệu thời gian có thể khai thác các khả năng range, aggregate và extension phù hợp.

### 21.5. Muốn kiểm soát quyền và triển khai

Tổ chức có thể vận hành PostgreSQL trên hạ tầng riêng hoặc sử dụng dịch vụ PostgreSQL được quản lý, tùy yêu cầu về chi phí, tuân thủ, backup, phiên bản và nguồn lực đội ngũ.

**Không nên chọn chỉ vì “PostgreSQL nổi tiếng là mạnh”.** Hãy xác định chức năng, độ tin cậy, quy mô, kỹ năng nhóm và cách vận hành cần thiết.

## 22. Khi nào cần cân nhắc giải pháp khác hoặc kết hợp công nghệ?

PostgreSQL không nhất thiết là thành phần duy nhất trong mọi kiến trúc:

- Với dữ liệu dạng file lớn như video/hình ảnh, **object storage** thường thích hợp cho nội dung file, còn PostgreSQL lưu metadata và liên kết.
- Với cache có thời hạn truy cập rất thấp, có thể thêm hệ thống cache chuyên dụng; PostgreSQL vẫn lưu dữ liệu nguồn.
- Với log/sự kiện lưu lượng cực lớn và chủ yếu dùng tổng hợp phân tích, có thể cân nhắc warehouse hoặc engine phân tích chuyên biệt, tùy yêu cầu.
- Với hệ thống tìm kiếm văn bản hoặc vector quy mô đặc thù, PostgreSQL có các khả năng/extension phù hợp cho nhiều bài toán, nhưng cần đo so với hệ thống tìm kiếm chuyên dụng nếu yêu cầu khác biệt.
- Với hệ thống nhúng rất nhỏ, không cần server riêng, một database nhúng như SQLite có thể phù hợp hơn về cách triển khai.
- Với ứng dụng phân tán nhiều vùng địa lý cần ghi đồng thời với yêu cầu đặc biệt, cần phân tích kỹ kiến trúc chứ không mặc định một server PostgreSQL đơn lẻ giải quyết được mọi nhu cầu.

Một kiến trúc hiện đại thường sử dụng **PostgreSQL làm nguồn dữ liệu giao dịch cốt lõi** và kết hợp cache, search, analytics hoặc object storage khi thật sự cần.

### 22.1. PostgreSQL so với NoSQL: không phải đối lập tuyệt đối

“Relational SQL” và “NoSQL” không đơn giản là “cứng nhắc” so với “linh hoạt”.

| Câu hỏi | PostgreSQL quan hệ | Một số hệ NoSQL |
|---|---|---|
| Mô hình dữ liệu | Bảng, khóa, quan hệ, có thể kết hợp JSONB | Tài liệu, key-value, wide-column, graph... tùy engine |
| Truy vấn | SQL, JOIN, aggregate và nhiều phép toán | API/ngôn ngữ tùy hệ |
| Ràng buộc | PK, FK, CHECK, UNIQUE và các cơ chế mở rộng | Khác nhau theo hệ |
| Giao dịch | Hỗ trợ transaction mạnh theo cơ chế PostgreSQL | Khác nhau theo sản phẩm; không được coi tất cả NoSQL đều thiếu transaction |
| Phân tán | Có replication và giải pháp mở rộng phù hợp | Một số hệ được thiết kế phân tán ngang ngay từ đầu |
| Điểm cần cân nhắc | Thiết kế schema, truy vấn, khóa, VACUUM, vận hành | Mô hình nhất quán, truy vấn, phân vùng dữ liệu, giới hạn từng hệ |

Việc lựa chọn phải dựa trên **workload thực tế và yêu cầu nhất quán**, không dựa vào nhãn công nghệ.

## 23. Những hiểu lầm thường gặp về PostgreSQL

### 23.1. “PostgreSQL chỉ là nơi lưu bảng”

Chưa đủ. PostgreSQL còn chịu trách nhiệm transaction, bảo vệ ràng buộc, concurrency, index, planner, quyền, backup/replication và nhiều hoạt động server khác.

### 23.2. “Biết SQL là đã biết vận hành PostgreSQL”

SQL là nền tảng rất quan trọng, nhưng vận hành còn bao gồm cấu hình kết nối, khóa, MVCC/VACUUM, WAL, sao lưu, quyền và quan sát hiệu năng.

### 23.3. “RDBMS không lưu được JSON”

Sai. PostgreSQL có `JSON` và `JSONB`, cùng những hàm/toán tử truy vấn tương ứng. Hỗ trợ JSON không xóa bỏ vai trò của mô hình quan hệ.

### 23.4. “Có PRIMARY KEY và FOREIGN KEY là đủ bảo đảm mọi nghiệp vụ đúng”

Không. Constraint giúp bảo vệ các quy tắc khai báo được. Luồng nghiệp vụ còn cần transaction, kiểm tra quyền, xử lý cạnh tranh và điều kiện logic.

### 23.5. “Mọi truy vấn có index đều nhanh”

Sai. Planner cân nhắc chi phí, thống kê, tính chọn lọc và số hàng phải đọc. Một index có thể không được dùng hoặc giúp rất ít nếu điều kiện không phù hợp.

### 23.6. “Dùng transaction thì không bao giờ cần retry”

Sai. Truy cập đồng thời có thể gặp deadlock, serialization failure, timeout hoặc các lỗi khác. Ứng dụng cần phân loại lỗi và có retry an toàn khi phù hợp.

### 23.7. “MVCC nghĩa là không có khóa”

Sai. MVCC cho phép quản lý phiên bản và đọc nhất quán, nhưng các thao tác ghi, DDL và câu lệnh khóa tường minh vẫn sử dụng lock.

### 23.8. “WAL tương đương backup”

Sai. WAL hỗ trợ recovery và một số cơ chế replication/PITR, nhưng backup độc lập và kiểm tra restore vẫn cần thiết.

### 23.9. “PostgreSQL tự tạo chỉ mục cho mọi khóa ngoại”

PostgreSQL tạo chỉ mục để duy trì khóa chính và unique constraint theo cơ chế phù hợp, nhưng **không mặc định tạo index cho cột tham chiếu của mọi foreign key**. Khi bảng con lớn hoặc có thao tác trên bảng cha, cần đánh giá index riêng trên cột FK theo workload.

### 23.10. “Có thể dùng cú pháp MySQL trong PostgreSQL mà không thay đổi”

Không phải lúc nào cũng đúng. Cú pháp identity, upsert, boolean, kiểu ngày giờ, câu lệnh quản trị và nhiều chi tiết khác nhau. Khi chuyển hệ, cần rà soát SQL và migration.

### 23.11. “PostgreSQL không cần người quản trị nếu chạy bằng dịch vụ cloud”

Managed service có thể quản lý một phần hạ tầng, nhưng khách hàng vẫn cần thiết kế schema, tối ưu truy vấn, đặt quyền, cấu hình backup/retention phù hợp và giám sát ứng dụng.

## 24. Tư duy thiết kế PostgreSQL cho một ứng dụng mới

Giả sử bạn đang thiết kế hệ thống đặt hàng. Trước khi tạo bảng, hãy tự trả lời:

1. **Dữ liệu cốt lõi là gì?** Khách, sản phẩm, đơn, chi tiết đơn, thanh toán.
2. **Một hàng là một thực thể/sự kiện nào?** Mỗi đơn một hàng, mỗi dòng sản phẩm trong đơn một hàng.
3. **Khóa chính/khóa ngoại ra sao?** Định danh duy nhất và quan hệ giữa các bảng.
4. **Thuộc tính nào bắt buộc?** Không để `NULL` ở dữ liệu nghiệp vụ phải có.
5. **Quy tắc nào cần DBMS thực thi?** Unique SKU, giá không âm, FK hợp lệ.
6. **Những thao tác nào là một transaction?** Tạo đơn, trừ tồn, ghi thanh toán theo quy trình.
7. **Các đường truy vấn chính là gì?** Tìm đơn theo khách, theo trạng thái, theo thời gian.
8. **Có bao nhiêu client đồng thời?** Nhu cầu pool, timeout, khóa, retry.
9. **Ai được đọc/sửa dữ liệu?** Vai trò ứng dụng và quyền tối thiểu.
10. **Dữ liệu được sao lưu và khôi phục thế nào?** Backup, WAL, RPO/RTO.
11. **Khi dữ liệu tăng, bạn sẽ theo dõi điều gì?** Index, độ trễ, VACUUM, kích thước, lưu trữ.
12. **Khi thay đổi schema, làm sao tránh sự cố?** Migration có thử nghiệm và kế hoạch triển khai.

Những câu hỏi này kết nối chức năng của RDBMS với yêu cầu thực tế thay vì bắt đầu bằng một lệnh `CREATE TABLE` tùy hứng.

## 25. Bài tập vận dụng

### Bài 1 — Phân biệt database và DBMS

Một nhóm lưu danh sách khách hàng trong CSV, rồi chuyển sang PostgreSQL. Hãy nêu ít nhất bốn khả năng mới mà PostgreSQL cung cấp ngoài việc lưu các hàng dữ liệu.

**Gợi ý:** PK/FK, transaction, index, concurrent access, phân quyền, phục hồi, SQL query planner.

### Bài 2 — Xác định quan hệ

Một cửa hàng có các thực thể `customers`, `orders`, `order_items`, `products`. Hãy xác định quan hệ một–nhiều và cột FK tương ứng.

**Gợi ý:** Mỗi customer có nhiều order; mỗi order có nhiều order_item; mỗi product có thể xuất hiện trong nhiều order_item.

### Bài 3 — Chọn ràng buộc

Bạn cần ngăn sản phẩm có `unit_price < 0`, ngăn hai sản phẩm có cùng SKU và không cho đơn hàng tham chiếu khách hàng không tồn tại. Hãy chọn constraint thích hợp cho từng yêu cầu.

**Gợi ý:** `CHECK`, `UNIQUE`, `FOREIGN KEY`.

### Bài 4 — Viết truy vấn JOIN

Viết câu SQL lấy tên khách và ID đơn từ hai bảng `pg_intro.customers`, `pg_intro.orders`.

**Đáp án gợi ý:**

~~~sql
SELECT c.full_name, o.order_id
FROM pg_intro.customers AS c
JOIN pg_intro.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY o.order_id;
~~~

### Bài 5 — Dự đoán kết quả của ROLLBACK

Tồn kho notebook là 20. Transaction giảm 5, sau đó chạy `ROLLBACK`. Kết quả cuối cùng là gì? Vì sao?

**Gợi ý:** Nếu chỉ có thay đổi này trong giao dịch và không có thay đổi cạnh tranh làm sai giả định, lượng tồn kho đã commit vẫn là 20; transaction không được xác nhận.

### Bài 6 — Hiểu truy cập đồng thời

Hai transaction cùng cập nhật một hàng tồn kho. Vì sao câu chuyện này không thể được giải quyết chỉ bằng “đọc giá trị trong ứng dụng rồi ghi đè”?

**Gợi ý:** Có nguy cơ lost update hoặc kiểm tra tồn kho trên giá trị đã cũ. Dùng điều kiện cập nhật atomically, transaction/locking và xử lý cạnh tranh.

### Bài 7 — Index có phải luôn được dùng không?

Bạn tạo index trên `customer_id` của bảng chỉ có 10 hàng. `EXPLAIN` vẫn báo sequential scan. Có phải index lỗi?

**Gợi ý:** Chưa chắc. Planner có thể chọn quét bảng vì chi phí nhỏ hơn; kiểm tra workload, phân bố dữ liệu và số đo thực.

### Bài 8 — WAL và backup

Máy chủ có WAL và streaming replica. Bạn có thể bỏ toàn bộ backup không?

**Gợi ý:** Không. Sai sót dữ liệu hợp lệ có thể lan sang replica; cần backup và thử khả năng phục hồi với mục tiêu RPO/RTO.

### Bài 9 — Chọn PostgreSQL cho ứng dụng

Một hệ thống quản lý kho cần transaction, ràng buộc FK, báo cáo SQL, nhiều người dùng truy cập đồng thời. Nêu vì sao PostgreSQL là ứng viên hợp lý, và hai yêu cầu cần hỏi thêm trước khi quyết định.

**Gợi ý:** Quy mô tải/độ trễ, yêu cầu HA/backup, đội ngũ vận hành, tích hợp, chi phí.

### Bài 10 — Schema và database

Trong cùng database có hai schema `sales` và `hr`, đều có bảng `employees`. Làm thế nào truy vấn đúng một trong hai bảng?

**Gợi ý:**

~~~sql
SELECT * FROM hr.employees;
SELECT * FROM sales.employees;
~~~

Dùng tên định danh schema khi cần để tránh phụ thuộc `search_path`.

## 26. Ghi nhớ nhanh

| Câu hỏi | Trả lời |
|---|---|
| PostgreSQL là gì? | Hệ quản trị cơ sở dữ liệu quan hệ–đối tượng mã nguồn mở |
| RDBMS làm việc với dữ liệu theo mô hình nào? | Quan hệ/bảng, hàng, cột, khóa và ràng buộc |
| SQL có vai trò gì? | Định nghĩa, truy vấn và thao tác dữ liệu |
| Primary key dùng làm gì? | Định danh duy nhất hàng |
| Foreign key dùng làm gì? | Bảo vệ quan hệ tham chiếu đã khai báo |
| Transaction giúp gì? | Gom các thao tác thành đơn vị có thể commit/rollback |
| ACID gồm gì? | Atomicity, Consistency, Isolation, Durability |
| MVCC là gì? | Cơ chế quản lý nhiều phiên bản cho đồng thời và snapshot |
| WAL là gì? | Write-Ahead Logging, nền tảng cho recovery/durability |
| Index giúp gì? | Tạo đường truy cập phù hợp cho nhiều mẫu tìm kiếm |
| EXPLAIN cho biết gì? | Kế hoạch truy vấn được planner dự kiến |
| VACUUM cần làm gì? | Xử lý các tuple đã chết và bảo trì khả năng tái sử dụng không gian, hỗ trợ vận hành MVCC |
| Schema khác database ra sao? | Schema là namespace trong một database |
| psql là gì? | Client dòng lệnh của PostgreSQL |
| PostgreSQL có lưu JSON không? | Có, gồm `JSON` và `JSONB` |
| Có nên dùng superuser cho ứng dụng không? | Không; ưu tiên quyền tối thiểu |
| Replica có thay backup không? | Không |
| PostgreSQL có giải quyết toàn bộ logic nghiệp vụ không? | Không; cần thiết kế dữ liệu, transaction và phân quyền đúng |

---

## Kết luận

**PostgreSQL là nền tảng phần mềm giúp lưu trữ và xử lý dữ liệu quan hệ có kiểm soát**, chứ không chỉ là nơi chứa những bảng có hàng và cột. Nó cung cấp SQL để truy vấn và kết hợp dữ liệu, ràng buộc để bảo vệ tính toàn vẹn, transaction ACID để quản lý thay đổi, MVCC và khóa để xử lý truy cập đồng thời, WAL để hỗ trợ khôi phục, chỉ mục và planner để tối ưu cách đọc dữ liệu, cùng cơ chế phân quyền và vận hành cho hệ thống dài hạn.

Với người học PostgreSQL, bước khởi đầu quan trọng nhất là hiểu **mỗi thành phần giải quyết vấn đề nào**. Bảng và quan hệ mô tả miền nghiệp vụ; ràng buộc bảo vệ các quy tắc cơ bản; giao dịch xử lý thay đổi nhiều bước; chỉ mục hỗ trợ truy vấn; và các công cụ backup, thống kê, bảo mật giúp vận hành khi dữ liệu lớn dần. Nắm được bức tranh đó, bạn có thể tiếp tục học PostgreSQL ở mức sâu hơn mà không nhầm một câu SQL chạy được với một hệ thống dữ liệu đã được thiết kế đúng và vận hành an toàn.
