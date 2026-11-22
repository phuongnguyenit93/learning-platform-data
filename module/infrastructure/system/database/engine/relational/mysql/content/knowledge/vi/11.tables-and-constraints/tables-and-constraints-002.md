# CREATE TABLE, DEFAULT, NOT NULL và biểu thức giá trị mặc định

## Mục tiêu

Sau bài này, bạn có thể:

- Tạo bảng bằng `CREATE TABLE` với kiểu dữ liệu, thuộc tính cột và tùy chọn bảng phù hợp.
- Phân biệt `NULL`, `NOT NULL`, `DEFAULT` và giá trị được ứng dụng truyền vào.
- Dự đoán MySQL xử lý cột bị bỏ qua, được gán `DEFAULT` hoặc được truyền `NULL` như thế nào.
- Khai báo giá trị mặc định dạng literal, `CURRENT_TIMESTAMP` và biểu thức mặc định.
- Hiểu tác động của SQL mode nghiêm ngặt khi thiếu giá trị hoặc truyền `NULL` vào cột `NOT NULL`.
- Kiểm tra DDL, metadata và cảnh báo để xác nhận cấu trúc bảng đúng như thiết kế.

## 1. Vai trò của CREATE TABLE trong thiết kế dữ liệu

`CREATE TABLE` định nghĩa cấu trúc lưu trữ cho một tập dữ liệu: tên và kiểu của từng cột, khả năng nhận `NULL`, giá trị mặc định, khóa, index, constraint, storage engine, charset và collation. Những quyết định này ảnh hưởng đến tính toàn vẹn dữ liệu, cách ứng dụng ghi bản ghi, truy vấn và khả năng thay đổi schema về sau.

Ví dụ, bảng đơn hàng có thể cần:

- Mã đơn hàng tự tăng và luôn có giá trị.
- Mã khách hàng bắt buộc.
- Trạng thái ban đầu là `PENDING` nếu ứng dụng không truyền trạng thái.
- Số tiền mặc định bằng 0 nhưng không được để `NULL`.
- Ghi nhận thời điểm tạo và cập nhật.
- Một cột ghi chú tùy chọn có thể để `NULL`.

Một thiết kế tốt diễn đạt được quy tắc dữ liệu ngay ở schema. Ứng dụng vẫn phải kiểm tra nghiệp vụ, nhưng database nên bảo vệ các điều kiện cơ bản để mọi client ghi dữ liệu đều tuân theo.

## 2. Cấu trúc cơ bản của CREATE TABLE

Cú pháp tổng quát:

```sql
CREATE TABLE [IF NOT EXISTS] table_name (
    column_name data_type [column_attributes],
    ...,
    [table_constraints]
)
[ENGINE = storage_engine]
[DEFAULT CHARACTER SET = charset_name]
[COLLATE = collation_name];
```

Một ví dụ:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(30) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email),
    KEY idx_customers_status (status)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
```

Trong ví dụ:

- `customer_id` là khóa chính tự tăng, không nhận `NULL`.
- `full_name` và `email` là dữ liệu bắt buộc.
- `phone` là dữ liệu tùy chọn.
- `status` nhận `ACTIVE` nếu lệnh `INSERT` không cung cấp giá trị cho cột này.
- `created_at` nhận thời điểm hiện tại khi tạo hàng nếu không được chỉ định.
- `UNIQUE KEY` bảo đảm email không trùng theo quy tắc collation của cột.
- `InnoDB` cung cấp transaction và các khả năng toàn vẹn dữ liệu phổ biến.
- `utf8mb4` hỗ trợ dữ liệu Unicode; collation quyết định cách so sánh chuỗi.

Collation `utf8mb4_0900_ai_ci` có trên MySQL 8.0. Nếu dùng phiên bản hoặc bản phân phối khác, hãy kiểm tra `SHOW COLLATION` và chọn collation được hỗ trợ.

### 2.1. IF NOT EXISTS không xác minh schema

`CREATE TABLE IF NOT EXISTS` không báo lỗi chỉ vì bảng đã tồn tại:

```sql
CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGINT NOT NULL PRIMARY KEY
);
```

Nếu bảng `customers` đã tồn tại nhưng có kiểu dữ liệu, index hoặc default khác, câu lệnh không tự sửa cấu trúc và cũng không xác nhận hai định nghĩa giống nhau. Vì vậy, migration không nên coi việc lệnh chạy thành công là bằng chứng schema đúng. Hãy kiểm tra bằng `SHOW CREATE TABLE` hoặc công cụ quản lý schema.

## 3. NULL và NOT NULL

### 3.1. NULL biểu thị điều gì?

`NULL` biểu thị giá trị chưa biết, không có hoặc chưa được cung cấp theo ngữ nghĩa của ứng dụng. Nó khác với:

- Chuỗi rỗng `''`.
- Số 0 `0`.
- Chuỗi `'0'`.
- Boolean `FALSE`.
- Một ngày giờ mặc định như `'0000-00-00'`.

Ví dụ:

```sql
CREATE TABLE customer_profiles (
    profile_id BIGINT NOT NULL PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL,
    middle_name VARCHAR(100) NULL,
    login_count INT NOT NULL DEFAULT 0
);
```

`middle_name` có thể không biết hoặc không có, vì vậy có thể để `NULL`. `login_count` luôn có một số nguyên; khi tạo bản ghi mà không cung cấp số lần đăng nhập, database dùng 0.

### 3.2. NOT NULL đặt ra điều kiện bắt buộc

Khai báo `NOT NULL` yêu cầu cột phải có giá trị khác `NULL` sau khi MySQL xử lý lệnh ghi. Ví dụ:

```sql
CREATE TABLE products (
    product_id BIGINT NOT NULL PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL,
    description TEXT NULL
);
```

`product_name` bắt buộc có giá trị; `description` có thể không có nội dung.

`NOT NULL` không tự bảo đảm chuỗi có nội dung có nghĩa. `product_name = ''` vẫn là một chuỗi không rỗng theo nghĩa SQL và có thể được lưu. Nếu cần cấm chuỗi chỉ chứa khoảng trắng, ứng dụng hoặc constraint phù hợp phải kiểm tra riêng.

### 3.3. So sánh NULL phải dùng IS NULL

Không dùng `= NULL` hoặc `<> NULL` để kiểm tra giá trị NULL:

```sql
-- Đúng
SELECT * FROM customer_profiles
WHERE middle_name IS NULL;

SELECT * FROM customer_profiles
WHERE middle_name IS NOT NULL;
```

SQL dùng logic ba giá trị: TRUE, FALSE và UNKNOWN. Phép so sánh thông thường với `NULL` cho kết quả UNKNOWN, nên `WHERE middle_name = NULL` không chọn các hàng có giá trị NULL.

## 4. DEFAULT có ý nghĩa gì?

`DEFAULT` khai báo giá trị MySQL sử dụng khi câu lệnh `INSERT` không cung cấp giá trị cho cột đó, hoặc khi câu lệnh chỉ định từ khóa `DEFAULT` cho cột.

Ví dụ:

```sql
CREATE TABLE tasks (
    task_id BIGINT NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    retry_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (task_id)
);
```

Các cách ghi sau có hành vi khác nhau:

```sql
-- Bỏ qua status và retry_count: MySQL dùng DEFAULT
INSERT INTO tasks (title)
VALUES ('Send welcome email');

-- Chỉ định rõ DEFAULT cho status
INSERT INTO tasks (title, status, retry_count)
VALUES ('Generate report', DEFAULT, DEFAULT);

-- Chỉ định giá trị cụ thể: DEFAULT không được dùng
INSERT INTO tasks (title, status, retry_count)
VALUES ('Import customers', 'RUNNING', 2);
```

Trong trường hợp đầu, `status` là `PENDING` và `retry_count` là 0. Trong trường hợp thứ hai, MySQL dùng default đã khai báo. Trường hợp thứ ba lưu các giá trị được truyền vào.

### 4.1. DEFAULT không thay thế NULL một cách tự động

Đây là điểm rất quan trọng:

```sql
INSERT INTO tasks (title, status)
VALUES ('Task A', DEFAULT);

INSERT INTO tasks (title, status)
VALUES ('Task B', NULL);
```

Lệnh đầu yêu cầu dùng giá trị mặc định. Lệnh thứ hai truyền `NULL` một cách tường minh. Với cột `status NOT NULL`, lệnh thứ hai bị từ chối trong chế độ SQL nghiêm ngặt; ở chế độ không nghiêm ngặt, MySQL có thể thay bằng giá trị mặc định ngầm định của kiểu và phát cảnh báo. Không nên dựa vào hành vi chuyển đổi ngầm này.

Với cột cho phép `NULL`, truyền `NULL` sẽ lưu `NULL`, không kích hoạt `DEFAULT`. Muốn dùng default, hãy bỏ cột khỏi danh sách insert hoặc dùng từ khóa `DEFAULT`.

### 4.2. DEFAULT khác với giá trị khởi tạo của ứng dụng

Nếu Java luôn gửi `status = 'PENDING'`, database không dùng default vì ứng dụng đã truyền giá trị. Nếu một batch import, script quản trị hoặc service khác bỏ qua cột, database mới dùng default. Khai báo default ở database tạo quy tắc chung cho mọi client, nhưng ứng dụng vẫn cần quyết định khi nào nên truyền giá trị cụ thể.

## 5. Giá trị mặc định dạng literal

### 5.1. Chuỗi và số

Giá trị mặc định đơn giản có thể khai báo trực tiếp:

```sql
CREATE TABLE inventory (
    item_id BIGINT NOT NULL AUTO_INCREMENT,
    item_name VARCHAR(150) NOT NULL,
    quantity INT UNSIGNED NOT NULL DEFAULT 0,
    item_status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE',
    unit_price DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (item_id)
);
```

- Chuỗi đặt trong dấu nháy đơn.
- Số được viết dưới dạng số literal, không cần dấu nháy.
- Giá trị boolean trong MySQL có thể viết `TRUE`/`FALSE`; chúng tương ứng với 1/0.
- Default phải tương thích với kiểu dữ liệu và miền giá trị của cột.

### 5.2. DEFAULT NULL

Với cột cho phép NULL, có thể khai báo rõ:

```sql
CREATE TABLE profiles (
    profile_id BIGINT NOT NULL PRIMARY KEY,
    nickname VARCHAR(80) NULL DEFAULT NULL
);
```

Trong nhiều trường hợp, cột nullable không khai báo default cũng có default ngầm định là `NULL`. Khai báo `DEFAULT NULL` tường minh có thể giúp người đọc DDL hiểu rõ ý định. Không khai báo `DEFAULT NULL` cho cột `NOT NULL`.

### 5.3. Cẩn thận với default ngầm định

Không khai báo `DEFAULT` không có nghĩa mọi cột đều có một giá trị mặc định hữu ích. Với cột `NOT NULL` không có default, nếu `INSERT` bỏ qua cột đó, kết quả phụ thuộc SQL mode:

- Với strict mode, câu lệnh thường bị từ chối vì cột không có default.
- Với non-strict mode, MySQL có thể chèn giá trị mặc định ngầm định theo kiểu dữ liệu và phát cảnh báo.

Giá trị ngầm định theo kiểu có thể là 0 cho kiểu số, chuỗi rỗng cho kiểu chuỗi hoặc giá trị zero-date trong một số cấu hình/ngữ cảnh. Những giá trị đó thường không đại diện đúng dữ liệu nghiệp vụ. Hãy khai báo default có chủ đích hoặc buộc ứng dụng cung cấp dữ liệu.

## 6. DEFAULT cho ngày giờ

MySQL hỗ trợ `CURRENT_TIMESTAMP` làm default cho cột `TIMESTAMP` và `DATETIME`:

```sql
CREATE TABLE audit_events (
    event_id BIGINT NOT NULL AUTO_INCREMENT,
    event_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id)
);
```

- `DEFAULT CURRENT_TIMESTAMP` gán thời điểm hiện tại khi insert nếu cột bị bỏ qua.
- `ON UPDATE CURRENT_TIMESTAMP` tự cập nhật thời điểm khi hàng được thay đổi theo quy tắc của MySQL.
- Hai thuộc tính này có thể khai báo precision phần lẻ giây, ví dụ `CURRENT_TIMESTAMP(6)` với cột `TIMESTAMP(6)` hoặc `DATETIME(6)`.

Ví dụ có microsecond:

```sql
CREATE TABLE api_requests (
    request_id BIGINT NOT NULL AUTO_INCREMENT,
    request_path VARCHAR(255) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (request_id)
);
```

`TIMESTAMP` được MySQL chuyển đổi giữa session timezone và UTC khi ghi/đọc. `DATETIME` lưu thành phần ngày giờ mà không tự chuyển đổi múi giờ. Vì vậy, `DEFAULT CURRENT_TIMESTAMP` trên `DATETIME` lưu giá trị giờ theo session tại thời điểm insert; cần có chính sách timezone rõ ràng để tránh dữ liệu lẫn múi giờ.

`ON UPDATE CURRENT_TIMESTAMP` không phải trigger tổng quát. Nó gắn hành vi cập nhật tự động cho cột thời gian khi hàng thay đổi. Nếu cần cập nhật theo điều kiện nghiệp vụ phức tạp, dùng logic ứng dụng hoặc trigger được thiết kế rõ ràng.

## 7. Biểu thức giá trị mặc định

### 7.1. Biểu thức default từ MySQL 8.0.13

Từ MySQL 8.0.13, có thể dùng biểu thức làm giá trị mặc định cho cột. Biểu thức phải được đặt trong ngoặc đơn, ngoại trừ cú pháp `CURRENT_TIMESTAMP` đặc biệt cho `TIMESTAMP`/`DATETIME`.

Ví dụ:

```sql
CREATE TABLE calculation_settings (
    setting_id BIGINT NOT NULL AUTO_INCREMENT,
    retry_limit INT NOT NULL DEFAULT (2 + 3),
    label VARCHAR(80) NOT NULL DEFAULT (LOWER('UNSET')),
    metadata JSON NOT NULL DEFAULT (JSON_OBJECT()),
    PRIMARY KEY (setting_id)
);
```

Khi insert mà bỏ qua các cột này, MySQL đánh giá biểu thức default theo quy tắc của biểu thức và kiểu cột. `retry_limit` nhận kết quả của `2 + 3`; `label` nhận chuỗi chữ thường; `metadata` nhận JSON object rỗng.

Biểu thức default giúp database tạo giá trị theo một quy tắc nhất quán. Tuy nhiên, không nên dùng biểu thức phức tạp để che giấu nghiệp vụ mà ứng dụng cần kiểm soát.

### 7.2. Những giới hạn của biểu thức default

Biểu thức default không phải một truy vấn tùy ý. Nó không được tham chiếu tới cột khác trong cùng hàng, không được chứa subquery, biến, parameter hoặc stored function/loadable function. Chỉ dùng biểu thức và built-in function được phiên bản MySQL hỗ trợ trong ngữ cảnh default.

Ví dụ sau không hợp lệ vì default của `total` tham chiếu cột khác:

```sql
-- Không hợp lệ: DEFAULT không thể tham chiếu unit_price hoặc quantity
CREATE TABLE order_lines_invalid (
    unit_price DECIMAL(12,2) NOT NULL,
    quantity INT NOT NULL,
    total DECIMAL(14,2) NOT NULL DEFAULT (unit_price * quantity)
);
```

Nếu một cột phải được tính từ các cột khác, hãy cân nhắc generated column:

```sql
CREATE TABLE order_lines (
    line_id BIGINT NOT NULL AUTO_INCREMENT,
    unit_price DECIMAL(12,2) NOT NULL,
    quantity INT NOT NULL,
    line_total DECIMAL(14,2)
        GENERATED ALWAYS AS (unit_price * quantity) STORED,
    PRIMARY KEY (line_id)
);
```

Generated column là giá trị được tính từ các cột khác theo định nghĩa schema; nó không phải default. Ứng dụng không ghi trực tiếp giá trị vào generated column theo cách ghi cột thông thường.

### 7.3. Default cho JSON, TEXT và BLOB

Với MySQL 8.0.13 trở lên, các kiểu như `JSON`, `TEXT` và `BLOB` có thể có default khi khai báo bằng biểu thức trong ngoặc đơn. Ví dụ:

```sql
CREATE TABLE documents (
    document_id BIGINT NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    attributes JSON NOT NULL DEFAULT (JSON_OBJECT()),
    content TEXT NOT NULL DEFAULT ('') ,
    PRIMARY KEY (document_id)
);
```

Các phiên bản MySQL cũ hơn không hỗ trợ expression default theo cách này. Nếu cần tương thích phiên bản cũ, hãy bỏ default của cột kiểu đó và để ứng dụng cung cấp giá trị rõ ràng khi insert, hoặc dùng cách thiết kế khác phù hợp với yêu cầu.

### 7.4. Kiểm tra tính tương thích phiên bản

Trước khi triển khai expression default, xác minh phiên bản:

```sql
SELECT VERSION();
```

Sau đó thử tạo bảng trong môi trường tương đương và kiểm tra DDL:

```sql
SHOW CREATE TABLE calculation_settings\G
```

MariaDB và các bản phân phối MySQL-compatible có thể có thời điểm hỗ trợ và giới hạn khác nhau. Không suy luận khả năng hỗ trợ chỉ từ việc một cú pháp chạy trên máy phát triển.

## 8. NOT NULL, DEFAULT và SQL mode

SQL mode ảnh hưởng cách MySQL xử lý dữ liệu thiếu hoặc không hợp lệ. Đặc biệt, strict mode giúp phát hiện sớm việc insert thiếu giá trị bắt buộc.

Kiểm tra mode:

```sql
SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode;
```

### 8.1. Bỏ qua cột NOT NULL không có DEFAULT

Giả sử:

```sql
CREATE TABLE employees (
    employee_id BIGINT NOT NULL AUTO_INCREMENT,
    employee_name VARCHAR(150) NOT NULL,
    department_code VARCHAR(20) NOT NULL,
    PRIMARY KEY (employee_id)
);
```

Lệnh sau không cung cấp `department_code`:

```sql
INSERT INTO employees (employee_name)
VALUES ('Nguyen An');
```

Với strict SQL mode, MySQL từ chối vì `department_code` không có default. Trong non-strict mode, server có thể sử dụng giá trị mặc định ngầm định theo kiểu và phát warning. Không nên dựa vào hành vi non-strict để điền dữ liệu nghiệp vụ.

### 8.2. Truyền NULL vào cột NOT NULL

```sql
INSERT INTO employees (employee_name, department_code)
VALUES ('Tran Binh', NULL);
```

Với strict mode, MySQL báo lỗi vì cột không nhận `NULL`. Trong non-strict mode, MySQL có thể thay bằng implicit default và phát warning. Nếu cột có default tường minh, điều đó không có nghĩa `NULL` tự động kích hoạt default.

### 8.3. Kiểm tra warning ngay sau câu lệnh

Sau một lệnh insert/update có thể phát cảnh báo, chạy ngay:

```sql
SHOW WARNINGS;
```

Đồng thời kiểm tra dữ liệu đã ghi:

```sql
SELECT employee_id, employee_name, department_code
FROM employees
ORDER BY employee_id DESC
LIMIT 5;
```

`INSERT IGNORE` có thể hạ một số lỗi thành warning và điều chỉnh dữ liệu để tiếp tục insert. Không dùng `IGNORE` như cách chữa lỗi `NOT NULL` hoặc dữ liệu không hợp lệ; cần hiểu rõ warning và kiểm tra bản ghi sau thao tác.

## 9. Ví dụ thiết kế bảng thực tế

Ví dụ một bảng đơn hàng có default rõ ràng:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    currency_code CHAR(3) NOT NULL DEFAULT 'VND',
    subtotal DECIMAL(19,2) NOT NULL DEFAULT 0.00,
    discount_amount DECIMAL(19,2) NOT NULL DEFAULT 0.00,
    note VARCHAR(500) NULL DEFAULT NULL,
    metadata JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (customer_id, created_at),
    KEY idx_orders_status_created (order_status, created_at)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
```

Thiết kế trên giả định MySQL 8.0.13 trở lên vì dùng expression default cho JSON. Nếu dùng phiên bản cũ, bỏ default JSON và yêu cầu ứng dụng gửi `JSON_OBJECT()` hoặc một JSON hợp lệ khi insert. Cần xác minh collation đích được hỗ trợ trên server.

Các insert minh họa:

```sql
-- Database cung cấp status, currency, số tiền mặc định, metadata và timestamp
INSERT INTO orders (customer_id)
VALUES (1001);

-- Ứng dụng ghi đè default bằng giá trị cụ thể
INSERT INTO orders (
    customer_id,
    order_status,
    currency_code,
    subtotal,
    metadata
)
VALUES (
    1002,
    'CONFIRMED',
    'USD',
    125.50,
    JSON_OBJECT('source', 'web')
);

-- Dùng DEFAULT tường minh cho một số cột
INSERT INTO orders (customer_id, order_status, subtotal)
VALUES (1003, DEFAULT, DEFAULT);
```

Kiểm tra:

```sql
SELECT
    order_id,
    customer_id,
    order_status,
    currency_code,
    subtotal,
    discount_amount,
    note,
    metadata,
    created_at,
    updated_at
FROM orders
ORDER BY order_id;
```

Lưu ý: default `VND` chỉ phù hợp nếu nghiệp vụ thực sự coi VND là currency mặc định. Nếu người dùng hoặc đơn hàng có thể dùng nhiều loại tiền, ứng dụng nên truyền currency rõ ràng thay vì dựa vào một default dễ gây sai nghiệp vụ.

## 10. Kiểm tra định nghĩa và metadata sau khi tạo bảng

### 10.1. SHOW CREATE TABLE

Lệnh quan trọng nhất để xem DDL MySQL thực tế:

```sql
SHOW CREATE TABLE orders\G
```

Hãy kiểm tra:

- Kiểu dữ liệu, độ dài, unsigned và precision/scale.
- `NULL`/`NOT NULL`.
- Giá trị `DEFAULT` và expression default.
- `AUTO_INCREMENT`.
- `ON UPDATE` cho cột ngày giờ.
- Primary key, unique key và index.
- Engine, charset và collation.

### 10.2. INFORMATION_SCHEMA.COLUMNS

```sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA,
    GENERATION_EXPRESSION,
    ORDINAL_POSITION
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
```

`IS_NULLABLE` cho biết cột có nhận NULL không. `COLUMN_DEFAULT` thể hiện default mà metadata công bố; cách biểu diễn expression default có thể khác theo phiên bản. `EXTRA` có thể cho biết `auto_increment`, `DEFAULT_GENERATED` hoặc thuộc tính bổ sung. `GENERATION_EXPRESSION` dùng cho generated column.

### 10.3. Kiểm tra engine và charset/collation

```sql
SELECT
    TABLE_NAME,
    ENGINE,
    TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders';
```

Metadata giúp kiểm tra schema thực tế sau khi migration. Không chỉ dựa vào file migration hoặc câu lệnh đã chạy; hãy kiểm tra server đang phục vụ ứng dụng.

## 11. Thay đổi DEFAULT và NOT NULL trên bảng đã có dữ liệu

### 11.1. Thêm hoặc đổi DEFAULT

Đổi default của cột:

```sql
ALTER TABLE orders
    ALTER COLUMN order_status SET DEFAULT 'PENDING';
```

Hoặc bỏ default:

```sql
ALTER TABLE orders
    ALTER COLUMN order_status DROP DEFAULT;
```

Thay đổi default không cập nhật giá trị của các hàng đã tồn tại. Nó ảnh hưởng các lần insert tiếp theo khi cột bị bỏ qua hoặc được chỉ định `DEFAULT`.

### 11.2. Đổi cột từ nullable sang NOT NULL

Trước khi thay đổi, tìm hàng đang có `NULL`:

```sql
SELECT COUNT(*) AS null_status_count
FROM orders
WHERE order_status IS NULL;
```

Nếu có dữ liệu NULL, cần quyết định giá trị thay thế theo nghiệp vụ và cập nhật có kiểm soát. Ví dụ chỉ khi quy tắc nghiệp vụ xác nhận trạng thái cũ phải được coi là `PENDING`:

```sql
UPDATE orders
SET order_status = 'PENDING'
WHERE order_status IS NULL;
```

Sau đó sửa định nghĩa cột với đầy đủ thuộc tính cần giữ:

```sql
ALTER TABLE orders
    MODIFY order_status VARCHAR(20)
        NOT NULL DEFAULT 'PENDING';
```

`MODIFY` yêu cầu khai báo lại kiểu và các thuộc tính quan trọng. Trước khi chạy, lấy `SHOW CREATE TABLE` để không vô tình làm mất comment, charset/collation riêng, default hoặc thuộc tính khác.

Với bảng lớn, `ALTER TABLE` có thể rebuild bảng hoặc giữ metadata lock trong một khoảng thời gian. Kiểm tra thuật toán DDL, khả năng online, dung lượng đĩa và thời gian khóa trên đúng phiên bản MySQL trước khi triển khai.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Đặt `NOT NULL` cho dữ liệu thực sự tùy chọn | Ứng dụng phải gửi giá trị giả hoặc insert thất bại | Xác định rõ nghiệp vụ có cho phép thiếu dữ liệu không |
| Dùng `DEFAULT 0` cho mọi số | 0 có thể bị nhầm với chưa biết/chưa tính | Chỉ dùng 0 khi đó là giá trị nghiệp vụ hợp lệ; nếu chưa biết, cân nhắc NULL |
| Nghĩ `DEFAULT` thay thế `NULL` | Insert truyền NULL không dùng default | Bỏ cột hoặc dùng từ khóa `DEFAULT` khi muốn lấy default |
| Dựa vào implicit default trong non-strict mode | Dữ liệu có thể nhận 0/chuỗi rỗng/zero-date ngoài ý muốn | Dùng strict mode, khai báo default tường minh và kiểm tra warning |
| Dùng double quote cho string default | Có thể lỗi khi `ANSI_QUOTES` bật | Dùng dấu nháy đơn cho string literal |
| Dùng expression default không kiểm tra phiên bản | DDL có thể không chạy trên server cũ | Xác minh MySQL 8.0.13+ và thử trên phiên bản triển khai |
| Dùng DEFAULT để tính từ cột khác | DDL không hợp lệ hoặc thiết kế sai mục đích | Dùng generated column hoặc logic ứng dụng |
| Dùng `IF NOT EXISTS` rồi cho rằng schema đã đúng | Bảng cũ có thể giữ định nghĩa khác | Kiểm tra `SHOW CREATE TABLE` và schema migration |
| Sửa NOT NULL mà không rà dữ liệu | DDL thất bại hoặc dữ liệu bị ép ngầm | Đếm NULL, xử lý dữ liệu và kiểm tra SQL mode trước |

## 13. Checklist trước khi tạo hoặc thay đổi bảng

- [ ] Tên bảng/cột rõ nghĩa, nhất quán và tránh từ khóa không cần thiết.
- [ ] Kiểu dữ liệu đủ miền giá trị, precision và scale.
- [ ] Cột bắt buộc dùng `NOT NULL`; cột thực sự tùy chọn dùng `NULL`.
- [ ] `DEFAULT` phản ánh giá trị nghiệp vụ hợp lệ, không phải giá trị giả để tránh lỗi.
- [ ] Phân biệt trường hợp bỏ cột, dùng `DEFAULT` và truyền `NULL`.
- [ ] Default ngày giờ phù hợp với chính sách timezone.
- [ ] Expression default được hỗ trợ bởi phiên bản MySQL mục tiêu.
- [ ] Không dùng default để tham chiếu cột khác; cân nhắc generated column khi cần.
- [ ] Có primary key, index và constraint theo nhu cầu truy vấn/toàn vẹn.
- [ ] Engine, charset và collation được chỉ định hoặc kiểm tra rõ ràng.
- [ ] Đã kiểm tra `SHOW CREATE TABLE`, `INFORMATION_SCHEMA` và warning sau migration.
- [ ] Đã đánh giá lock, dung lượng và khả năng online nếu thay đổi bảng lớn.

## 14. Kết luận

`CREATE TABLE` là nơi định nghĩa cấu trúc và một phần quy tắc dữ liệu của hệ thống. `NOT NULL` xác định cột bắt buộc có giá trị, còn `DEFAULT` cung cấp giá trị khi insert bỏ qua cột hoặc yêu cầu từ khóa `DEFAULT`. Truyền `NULL` là một hành động riêng và không tự kích hoạt default.

Hãy khai báo kiểu dữ liệu, nullability và default theo ngữ nghĩa nghiệp vụ. Dùng `CURRENT_TIMESTAMP` cho thời điểm tạo/cập nhật khi phù hợp; chỉ dùng expression default trên phiên bản hỗ trợ; kiểm tra SQL mode để tránh giá trị ngầm định ngoài ý muốn. Sau khi tạo hoặc thay đổi schema, xác minh bằng `SHOW CREATE TABLE` và metadata của chính MySQL Server.
