# Quan hệ giữa database, schema, table và tài khoản người dùng

Bài học thuộc chương **Schema và metadata** của module `DATABASE_MYSQL`. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Hiểu đúng quan hệ giữa database, schema, table và account giúp tổ chức dữ liệu hợp lý, đọc metadata chính xác và cấp quyền truy cập đúng phạm vi.

Sau bài này, bạn có thể mô tả cấu trúc logic của một MySQL Server, giải thích vì sao trong MySQL database và schema là hai tên gọi tương đương, phân biệt schema với table và account, xác định database mặc định của session, tra cứu cấu trúc qua INFORMATION_SCHEMA và thiết kế quyền cho tài khoản theo nguyên tắc đặc quyền tối thiểu.

## 1. Nhìn tổng thể cấu trúc logic của MySQL

Một MySQL Server (instance) quản lý nhiều database. Trong MySQL, **schema là từ đồng nghĩa với database**. Một database/schema chứa các đối tượng như bảng, view, stored procedure, function, trigger và event. Bảng chứa các cột và hàng dữ liệu; index và constraint mô tả cách truy cập, tính duy nhất và quan hệ giữa dữ liệu.

Tài khoản người dùng MySQL là danh tính dùng để xác thực kết nối tới Server. Tài khoản được định danh bằng cặp user và host, sau đó được cấp quyền trên toàn Server hoặc trên những database và đối tượng cụ thể.

Có thể hình dung mối quan hệ như sau:

~~~mermaid
flowchart TD
    S["MySQL Server / Instance"]
    S --> D1["Database / Schema: shop"]
    S --> D2["Database / Schema: analytics"]
    S --> D3["System schemas"]
    D1 --> T1["Table: customers"]
    D1 --> T2["Table: orders"]
    D1 --> V1["View: active_customers"]
    D1 --> R1["Stored routines, triggers, events"]
    T1 --> C1["Columns, indexes, constraints"]
    T2 --> C2["Columns, indexes, constraints"]
    U1["Account: 'shop_app'@'10.20.0.15'"] -. "GRANT trên shop.*" .-> D1
    U2["Account: 'reporter'@'10.20.0.0/24'"] -. "GRANT SELECT trên bảng" .-> T2
~~~

Sơ đồ thể hiện hai loại quan hệ khác nhau:

- Database chứa các đối tượng dữ liệu theo một namespace logic.
- Account tồn tại ở cấp Server và được cấp quyền lên các phạm vi. Account không phải là một đối tượng nằm bên trong database mà nó được phép truy cập.

Ví dụ, tài khoản `'shop_app'@'10.20.0.15'` có thể được cấp quyền trên database `shop`. Database `shop` không trở thành tài sản riêng của tài khoản này và tài khoản cũng không tự có quyền trên database khác.

## 2. Database và schema trong MySQL

Trong một số hệ quản trị cơ sở dữ liệu, database và schema có ý nghĩa khác nhau. Ví dụ, một schema có thể đại diện cho nhóm đối tượng do một người dùng sở hữu bên trong database. **MySQL không dùng cách phân biệt đó: schema và database là đồng nghĩa.**

Bạn có thể dùng cả hai cặp câu lệnh sau:

~~~sql
CREATE DATABASE shop;
CREATE SCHEMA analytics;

SHOW DATABASES;
SHOW SCHEMAS;

DROP DATABASE analytics;
-- Cú pháp tương đương nếu muốn xóa analytics:
-- DROP SCHEMA analytics;
~~~

Trong MySQL, `CREATE SCHEMA` và `CREATE DATABASE` là hai cách viết tương đương. Tương tự, `SHOW SCHEMAS` và `SHOW DATABASES` trả về danh sách database/schema mà tài khoản có quyền nhìn thấy.

Khi đọc tài liệu đa hệ quản trị, cần lưu ý ngữ cảnh:

| Hệ quản trị | Cách hiểu thường gặp |
|---|---|
| MySQL | Schema đồng nghĩa với database |
| PostgreSQL | Một database có thể chứa nhiều schema; schema là namespace bên trong database |
| SQL Server | Database có thể chứa nhiều schema; schema là namespace/nhóm đối tượng |
| Oracle Database | Schema là tập đối tượng thuộc một database user |

Không áp dụng máy móc khái niệm schema của PostgreSQL, SQL Server hoặc Oracle vào MySQL. Với MySQL, khi tài liệu nói `schema name` thì thường chính là tên database.

### Tạo database với charset và collation

Database có thể đặt bộ ký tự và collation mặc định để các bảng và cột mới kế thừa khi không khai báo riêng:

~~~sql
CREATE DATABASE shop
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
~~~

Ví dụ này phù hợp với các phiên bản MySQL hiện đại có collation `utf8mb4_0900_ai_ci`, chẳng hạn MySQL 8.0 và các dòng mới. Nếu bảo trì MySQL 5.7, hãy chọn collation có sẵn ở phiên bản đó, ví dụ `utf8mb4_unicode_ci`.

Kiểm tra cấu hình database:

~~~sql
SHOW CREATE DATABASE shop;

SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME = 'shop';
~~~

Charset và collation ở database là giá trị mặc định. Một bảng hoặc cột có thể khai báo charset/collation riêng, vì vậy khi kiểm tra dữ liệu thực tế, hãy xem cả metadata của table và column.

### Database không đồng nghĩa với một thư mục vật lý

Database/schema là cách tổ chức logic mà SQL nhìn thấy. Không nên suy luận rằng mỗi database luôn tương ứng với một thư mục có thể sao chép độc lập, hoặc mỗi table luôn có đúng một file trên đĩa. Cách lưu trữ phụ thuộc vào storage engine, tablespace, cấu hình máy chủ và phiên bản MySQL. Với InnoDB, dữ liệu và metadata được quản lý theo cơ chế lưu trữ của InnoDB; MySQL 8.0 sử dụng transactional data dictionary.

Khi backup hoặc di chuyển dữ liệu, dùng công cụ và quy trình backup/restore phù hợp như MySQL Shell dump utilities, mysqldump hoặc giải pháp backup vật lý được hỗ trợ. Không sao chép tùy tiện thư mục database trong lúc Server đang chạy.

## 3. Table là đối tượng nằm trong database/schema

Table là cấu trúc lưu dữ liệu theo hàng và cột. Trong MySQL, một table được xác định bằng tên database/schema và tên table:

~~~text
database_name.table_name
~~~

Ví dụ `shop.customers` là bảng `customers` thuộc database `shop`. Nếu có hai database `shop` và `archive`, chúng có thể cùng chứa một bảng tên `orders`:

~~~sql
shop.orders
archive.orders
~~~

Đây là hai bảng khác nhau. Tên table chỉ cần duy nhất trong phạm vi schema tương ứng, không nhất thiết duy nhất trên toàn Server.

Tạo một bảng ví dụ:

~~~sql
CREATE TABLE shop.customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
~~~

Trong ví dụ:

- `shop` là database/schema chứa bảng.
- `customers` là tên bảng.
- Các trường `customer_id`, `email`, `full_name` và `created_at` là cột.
- Mỗi bản ghi khách hàng là một hàng.
- Primary key định danh duy nhất một hàng.
- Unique key đảm bảo email không bị trùng.
- InnoDB là storage engine của bảng.

Để xem định nghĩa thực tế:

~~~sql
SHOW CREATE TABLE shop.customers;
~~~

Nếu đã chọn database mặc định bằng `USE shop`, có thể viết ngắn:

~~~sql
SHOW CREATE TABLE customers;
~~~

Tuy nhiên, khi viết script triển khai hoặc migration dùng nhiều database, tên đầy đủ `shop.customers` giúp tránh nhầm lẫn.

### Những đối tượng khác trong schema

Database không chỉ chứa table. Các đối tượng phổ biến gồm:

| Đối tượng | Vai trò |
|---|---|
| Base table | Lưu dữ liệu theo hàng và cột |
| View | Cung cấp một truy vấn được đặt tên như một bảng logic |
| Stored procedure | Gom các thao tác SQL thành thủ tục có thể gọi |
| Stored function | Trả về một giá trị và có thể dùng trong biểu thức SQL |
| Trigger | Tự thực thi khi một số thao tác xảy ra trên table |
| Event | Lập lịch thực thi câu lệnh theo thời gian |
| Index | Cấu trúc hỗ trợ tìm kiếm và sắp xếp; gắn với table |
| Constraint | Quy tắc như PRIMARY KEY, UNIQUE, FOREIGN KEY, CHECK |

Index và constraint là thành phần của table, không phải database độc lập. Trigger gắn với table; stored routine và event thuộc schema.

## 4. Account người dùng tồn tại ở cấp MySQL Server

Một account MySQL được viết theo dạng:

~~~sql
'user_name'@'host_name'
~~~

Ví dụ:

- `'shop_app'@'localhost'`: ứng dụng kết nối từ máy cục bộ.
- `'shop_app'@'10.20.0.15'`: ứng dụng kết nối từ địa chỉ IP cụ thể.
- `'reporter'@'10.20.0.0/24'`: tài khoản cho một mạng IPv4 được chỉ định.

Account được tạo trên Server bằng `CREATE USER`. Nó không cần được tạo bên trong một database cụ thể:

~~~sql
CREATE USER 'shop_app'@'10.20.0.15'
    IDENTIFIED BY 'replace_with_a_strong_password';
~~~

Ngay sau khi tạo, account có thể xác thực kết nối nếu cấu hình xác thực và host phù hợp, nhưng chưa tự có quyền đọc hoặc ghi database ứng dụng. Cần cấp quyền riêng:

~~~sql
GRANT SELECT, INSERT, UPDATE
    ON shop.*
    TO 'shop_app'@'10.20.0.15';
~~~

Câu lệnh trên cấp quyền trên tất cả table và đối tượng phù hợp trong database `shop` theo phạm vi của quyền được cấp. Nó không cấp quyền trên database `analytics`.

Một account có thể được cấp quyền trên nhiều database; nhiều account có thể cùng truy cập một database với các mức quyền khác nhau. Quan hệ account-database vì vậy là quan hệ phân quyền, không phải quan hệ chứa hoặc sở hữu.

### Phân biệt account, user và session

Trong giao tiếp hàng ngày, các từ user, account và connection thường được dùng lẫn nhau, nhưng cần phân biệt:

- **Account:** bản ghi xác thực và quyền của MySQL, định danh bởi cặp user-host.
- **Client identity:** tên user và thông tin host mà client dùng khi kết nối.
- **Session/connection:** phiên làm việc được tạo sau khi kết nối được chấp nhận. Mỗi session có trạng thái riêng, ví dụ database mặc định, transaction và biến session.
- **Database mặc định:** schema mà session đang dùng khi câu SQL không ghi rõ tên database.

Một account có thể mở nhiều session đồng thời. Mỗi session có thể chọn database mặc định khác nhau mà không làm thay đổi account hoặc quyền đã cấp.

## 5. Database mặc định và cách định danh table

Sau khi đăng nhập, session có thể chọn database mặc định:

~~~sql
USE shop;

SELECT DATABASE();
~~~

`DATABASE()` trả về tên database mặc định của session hiện tại. Nếu session chưa chọn database, kết quả là `NULL`.

Khi đã chọn `shop`, câu truy vấn có thể tham chiếu bảng bằng tên ngắn:

~~~sql
SELECT customer_id, email
FROM customers;
~~~

Hoặc tham chiếu đầy đủ, bất kể database mặc định hiện tại:

~~~sql
SELECT customer_id, email
FROM shop.customers;
~~~

Sự khác nhau nằm ở cách định danh, không phải quyền truy cập:

- `USE shop` chỉ chọn database mặc định cho session.
- `USE shop` không cấp thêm quyền cho account.
- Nếu account không có quyền cần thiết trên `shop`, chọn database mặc định không làm câu truy vấn được phép.
- Dùng tên đầy đủ `shop.customers` giúp tránh phụ thuộc vào database mặc định.

Một account có thể truy cập nhiều database được cấp quyền:

~~~sql
SELECT * FROM shop.customers;
SELECT * FROM analytics.monthly_sales;
~~~

Việc truy cập thành công hay không phụ thuộc vào quyền của account trên từng đối tượng. Database mặc định không phải là danh sách database duy nhất mà account có thể truy cập.

### SHOW DATABASES và khả năng nhìn thấy schema

Lệnh:

~~~sql
SHOW DATABASES;
~~~

không nhất thiết hiển thị mọi database trên Server. Tài khoản thông thường chỉ thấy các database mà nó có một số quyền, trừ khi có quyền toàn cục `SHOW DATABASES` hoặc thuộc trường hợp đặc biệt theo cấu hình quyền.

Vì vậy, không nhìn thấy một database trong `SHOW DATABASES` không đủ để kết luận database đó không tồn tại. Người quản trị cần kiểm tra quyền hiển thị và quyền truy cập.

## 6. Quyền được cấp theo phạm vi nào?

MySQL có nhiều cấp quyền. Có thể nhìn từ rộng đến hẹp:

| Phạm vi | Cú pháp GRANT | Phạm vi tác động |
|---|---|---|
| Toàn Server | `ON *.*` | Tất cả database và đối tượng tương ứng trên Server |
| Một database/schema | `ON shop.*` | Các đối tượng trong database shop |
| Một table/view | `ON shop.customers` | Một bảng hoặc view cụ thể |
| Một số column | `ON shop.customers (email, full_name)` | Các cột được chỉ định |
| Một stored routine | `ON PROCEDURE shop.rebuild_summary` | Một procedure cụ thể; function dùng từ khóa FUNCTION |

Ví dụ cấp quyền đọc toàn bộ database:

~~~sql
GRANT SELECT
    ON shop.*
    TO 'shop_reader'@'10.20.0.0/24';
~~~

Ví dụ chỉ cho phép đọc một bảng:

~~~sql
GRANT SELECT
    ON shop.orders
    TO 'support_agent'@'10.20.0.21';
~~~

Ví dụ giới hạn cột:

~~~sql
GRANT SELECT (customer_id, email, full_name)
    ON shop.customers
    TO 'support_agent'@'10.20.0.21';
~~~

Ví dụ chỉ cho phép gọi một procedure:

~~~sql
GRANT EXECUTE
    ON PROCEDURE shop.rebuild_daily_summary
    TO 'report_job'@'10.20.0.30';
~~~

Không nên cấp quyền toàn cục chỉ để giải quyết một lỗi truy cập trên một database. Quyền toàn cục có ảnh hưởng rộng hơn nhiều so với quyền database hoặc table.

### Quyền được cộng dồn

Các quyền từ nhiều phạm vi được kết hợp khi MySQL kiểm tra một thao tác. Ví dụ, account có `SELECT` toàn cục thì đã có quyền đọc mọi bảng theo phạm vi toàn cục; việc không cấp `SELECT` ở cấp database khác không tự động thu hồi quyền toàn cục đó.

MySQL 8.0 trở lên hỗ trợ partial revoke trong những trường hợp được cấu hình, nhưng đây là cơ chế quản trị chuyên biệt. Đối với cấu hình thông thường, hãy tránh cấp quyền quá rộng ngay từ đầu.

Ví dụ thiết kế quyền theo vai trò công việc:

| Loại account | Quyền phù hợp |
|---|---|
| Ứng dụng chạy nghiệp vụ | SELECT, INSERT, UPDATE trên database cần dùng; DELETE nếu thực sự cần |
| Nhân viên hỗ trợ | SELECT trên các bảng hoặc view cần tra cứu |
| Báo cáo | SELECT trên database báo cáo hoặc view đã giới hạn dữ liệu |
| Migration/deployment | CREATE, ALTER, INDEX và các quyền DDL cần thiết trong thời gian triển khai |
| DBA | Quyền quản trị toàn cục phù hợp với trách nhiệm vận hành |

Không dùng tài khoản DBA cho kết nối ứng dụng thường xuyên. Tách account ứng dụng khỏi account migration giúp giảm hậu quả nếu thông tin xác thực của ứng dụng bị lộ.

## 7. Ví dụ hoàn chỉnh: tạo schema, table và account ứng dụng

Giả sử xây dựng một ứng dụng cửa hàng. Server có database `shop` chứa khách hàng và đơn hàng. Ứng dụng kết nối từ máy `10.20.0.15`, chỉ cần đọc, thêm và cập nhật dữ liệu nghiệp vụ.

### Bước 1: tạo database

~~~sql
CREATE DATABASE shop
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
~~~

### Bước 2: tạo table

~~~sql
CREATE TABLE shop.customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB;

CREATE TABLE shop.orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_total DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY ix_orders_customer_created (customer_id, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES shop.customers (customer_id)
) ENGINE = InnoDB;
~~~

Hai table nằm trong cùng schema `shop`. Foreign key nối cột `orders.customer_id` với khóa chính của `customers.customer_id`.

### Bước 3: tạo account ứng dụng

~~~sql
CREATE USER 'shop_app'@'10.20.0.15'
    IDENTIFIED BY 'replace_with_a_strong_password';
~~~

### Bước 4: cấp quyền cần thiết

~~~sql
GRANT SELECT, INSERT, UPDATE
    ON shop.*
    TO 'shop_app'@'10.20.0.15';
~~~

Nếu ứng dụng cần xóa đơn hàng, hãy đánh giá yêu cầu nghiệp vụ và cấp `DELETE` riêng. Nếu ứng dụng không tạo bảng hoặc thay đổi schema trong lúc chạy, không cấp `CREATE`, `ALTER` hoặc `DROP` cho account runtime.

### Bước 5: xác minh quyền

~~~sql
SHOW GRANTS FOR 'shop_app'@'10.20.0.15';
~~~

Sau khi kết nối bằng account ứng dụng, kiểm tra danh tính và database mặc định:

~~~sql
SELECT
    USER() AS client_identity,
    CURRENT_USER() AS authenticated_account,
    DATABASE() AS default_database;
~~~

Nếu chưa chọn database, `DATABASE()` có thể là `NULL`. Chọn database và kiểm tra:

~~~sql
USE shop;

SELECT customer_id, email
FROM customers;
~~~

Account vẫn có thể truy vấn bảng bằng tên đầy đủ `shop.customers` ngay cả khi không chọn `shop` làm database mặc định, miễn là có quyền tương ứng.

## 8. Tra cứu schema và table qua INFORMATION_SCHEMA

MySQL cung cấp database hệ thống `INFORMATION_SCHEMA` để đọc metadata: database nào tồn tại, table nào thuộc database, cột có kiểu gì, index nào được định nghĩa và quyền nào được cấp.

`INFORMATION_SCHEMA` là giao diện metadata chỉ đọc. Các bảng trong đó được triển khai như view; không dùng INSERT, UPDATE hoặc DELETE để sửa metadata. Khả năng nhìn thấy metadata cũng bị giới hạn theo quyền của account hiện tại.

### Liệt kê database/schema

~~~sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
ORDER BY SCHEMA_NAME;
~~~

Tương đương trong phạm vi các database mà account có thể nhìn thấy:

~~~sql
SHOW DATABASES;
~~~

### Liệt kê table và view trong một schema

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE,
    ENGINE,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'shop'
ORDER BY TABLE_NAME;
~~~

`TABLE_TYPE` giúp phân biệt base table và view. Với InnoDB, `TABLE_ROWS` thường là giá trị ước lượng, không phải lúc nào cũng là số hàng chính xác. Nếu cần đếm chính xác, chạy `SELECT COUNT(*)` trên bảng và cân nhắc chi phí truy vấn.

### Xem cấu trúc cột

~~~sql
SELECT
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_KEY,
    EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'customers'
ORDER BY ORDINAL_POSITION;
~~~

Truy vấn cho biết thứ tự cột, kiểu dữ liệu, cho phép NULL hay không, giá trị mặc định và thuộc tính như AUTO_INCREMENT.

### Xem index

~~~sql
SELECT
    INDEX_NAME,
    COLUMN_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

Một index nhiều cột có nhiều dòng trong metadata. `SEQ_IN_INDEX` cho biết vị trí của cột bên trong index.

### Xem constraint

~~~sql
SELECT
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE,
    TABLE_SCHEMA,
    TABLE_NAME
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
WHERE TABLE_SCHEMA = 'shop'
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
~~~

Để xem các cột tham gia khóa ngoại:

~~~sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_SCHEMA,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'shop'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION;
~~~

### Xem quyền ở cấp schema và table

~~~sql
SELECT
    GRANTEE,
    TABLE_SCHEMA,
    PRIVILEGE_TYPE,
    IS_GRANTABLE
FROM INFORMATION_SCHEMA.SCHEMA_PRIVILEGES
WHERE TABLE_SCHEMA = 'shop'
ORDER BY GRANTEE, PRIVILEGE_TYPE;
~~~

~~~sql
SELECT
    GRANTEE,
    TABLE_SCHEMA,
    TABLE_NAME,
    PRIVILEGE_TYPE,
    IS_GRANTABLE
FROM INFORMATION_SCHEMA.TABLE_PRIVILEGES
WHERE TABLE_SCHEMA = 'shop'
ORDER BY GRANTEE, TABLE_NAME, PRIVILEGE_TYPE;
~~~

Metadata quyền có thể chỉ hiển thị các grant mà tài khoản hiện tại được phép nhìn thấy. Để kiểm tra đầy đủ một account cụ thể, người quản trị nên dùng:

~~~sql
SHOW GRANTS FOR 'shop_app'@'10.20.0.15';
~~~

### Phân biệt các schema hệ thống

Một MySQL Server thường có các schema hệ thống sau:

| Schema | Mục đích |
|---|---|
| `mysql` | Tài khoản, grant và các dữ liệu quản trị hệ thống |
| `information_schema` | Metadata về database, table, column, index, constraint và quyền |
| `performance_schema` | Số liệu runtime về hoạt động, instrument và hiệu năng |
| `sys` | Các view và helper phục vụ phân tích, chẩn đoán |

Không chỉnh sửa trực tiếp bảng hệ thống để cấp quyền hoặc thay đổi cấu trúc. Hãy dùng các câu lệnh như `CREATE USER`, `ALTER USER`, `GRANT` và `REVOKE`. Cũng không nhầm `INFORMATION_SCHEMA.TABLES` với table nghiệp vụ của ứng dụng: đây là metadata do MySQL cung cấp.

## 9. Những lỗi thiết kế và hiểu nhầm thường gặp

| Hiểu nhầm hoặc lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Coi schema là namespace bên trong database như PostgreSQL | Thiết kế tên đối tượng và migration sai mô hình MySQL | Nhớ rằng trong MySQL schema đồng nghĩa database |
| Nghĩ account được tạo bên trong database | Cấu hình quyền sai cấp | Tạo account trên Server rồi cấp quyền vào database/object |
| Nghĩ USE database cấp quyền | Vẫn gặp access denied khi truy vấn | Kiểm tra GRANT và account thực tế bằng CURRENT_USER() |
| Nghĩ SHOW DATABASES luôn hiển thị mọi database | Kết luận nhầm database không tồn tại | Kiểm tra quyền hiển thị và dùng account quản trị phù hợp |
| Dùng table name không kèm schema trong script nhiều database | Truy vấn nhầm bảng do default database khác nhau | Dùng tên đầy đủ database.table |
| Cấp ALL ON *.* cho account ứng dụng | Ứng dụng có quyền rộng trên toàn Server | Cấp quyền tối thiểu ở cấp schema, table hoặc column |
| Sửa trực tiếp mysql.user hoặc các grant table | Có thể làm hỏng metadata hoặc tạo trạng thái không nhất quán | Dùng CREATE USER, ALTER USER, GRANT và REVOKE |
| Coi TABLE_ROWS trong INFORMATION_SCHEMA là số chính xác | Báo cáo sai số hàng | Dùng COUNT(*) khi thực sự cần số chính xác |
| Coi database luôn là một thư mục vật lý có thể copy nóng | Backup/restore thiếu nhất quán | Dùng công cụ backup được hỗ trợ và quy trình phù hợp storage engine |

## 10. Checklist thiết kế và kiểm tra

Trước khi bàn giao một database cho ứng dụng hoặc nhóm vận hành, hãy xác nhận:

- [ ] Đã phân biệt database/schema theo đúng cách dùng của MySQL.
- [ ] Đã xác định các database nghiệp vụ và các table/view/routine thuộc từng schema.
- [ ] Đã chọn charset và collation mặc định phù hợp.
- [ ] Đã dùng tên đầy đủ database.table trong script cần chạy độc lập với default database.
- [ ] Đã tách account runtime khỏi account DBA hoặc migration.
- [ ] Mỗi account có host phù hợp với nơi kết nối thực tế.
- [ ] Quyền được cấp đúng phạm vi: global, schema, table, column hoặc routine.
- [ ] Đã kiểm tra bằng SHOW GRANTS và thử kết nối bằng chính account ứng dụng.
- [ ] Đã kiểm tra metadata bằng INFORMATION_SCHEMA.
- [ ] Đã biết database nào là hệ thống và không sửa trực tiếp metadata hệ thống.
- [ ] Đã có quy trình backup/restore phù hợp, không phụ thuộc vào việc copy thư mục database khi Server đang chạy.

## Tài liệu tham khảo chính thức

Các khái niệm và câu lệnh trong bài được đối chiếu với MySQL 9.7 Reference Manual tại ngày **19-11-2026**:

1. [MySQL Glossary — database và schema](https://dev.mysql.com/doc/refman/9.7/en/glossary.html): schema là từ đồng nghĩa với database trong MySQL.
2. [CREATE DATABASE Statement](https://dev.mysql.com/doc/refman/9.7/en/create-database.html): tạo database/schema, charset và collation mặc định.
3. [USE Statement](https://dev.mysql.com/doc/refman/9.7/en/use.html): chọn database mặc định cho session.
4. [CREATE TABLE Statement](https://dev.mysql.com/doc/refman/9.7/en/create-table.html): định nghĩa table, cột, index, constraint và storage engine.
5. [MySQL Account Names](https://dev.mysql.com/doc/refman/9.7/en/account-names.html): định danh account theo user và host.
6. [Privileges Provided by MySQL](https://dev.mysql.com/doc/refman/9.7/en/privileges-provided.html): loại quyền và phạm vi áp dụng.
7. [Access Control, Stage 2: Request Verification](https://dev.mysql.com/doc/refman/9.7/en/request-access.html): cách Server kiểm tra quyền khi account thực hiện request.
8. [GRANT Statement](https://dev.mysql.com/doc/refman/9.7/en/grant.html): cấp quyền ở cấp global, database, table, column và routine.
9. [INFORMATION_SCHEMA Introduction](https://dev.mysql.com/doc/refman/9.7/en/information-schema-introduction.html): mục đích và cách truy vấn metadata.
10. [The INFORMATION_SCHEMA SCHEMATA Table](https://dev.mysql.com/doc/refman/9.7/en/information-schema-schemata-table.html): danh sách schema/database và charset/collation mặc định.
11. [The INFORMATION_SCHEMA TABLES Table](https://dev.mysql.com/doc/refman/9.7/en/information-schema-tables-table.html): metadata table, view và storage engine.
12. [The INFORMATION_SCHEMA COLUMNS Table](https://dev.mysql.com/doc/refman/9.7/en/information-schema-columns-table.html): metadata của cột.
13. [The MySQL System Schema](https://dev.mysql.com/doc/refman/9.7/en/system-schema.html): vai trò của các schema hệ thống và data dictionary.

