# PRIMARY, UNIQUE và secondary index trong InnoDB

InnoDB sử dụng B-tree để tổ chức dữ liệu và tìm hàng. `PRIMARY KEY` xác định khóa chính của bảng, `UNIQUE` bảo đảm một hoặc nhiều cột có giá trị duy nhất theo quy tắc so sánh của MySQL, còn secondary index hỗ trợ tìm kiếm và sắp xếp theo các cột khác. Ba khái niệm này có liên quan nhưng phục vụ những mục đích khác nhau.

Trong InnoDB, primary key thường chính là clustered index: các hàng dữ liệu nằm ở các trang lá của B-tree khóa chính. Mỗi secondary index là một B-tree riêng và lưu thêm khóa chính để định vị hàng tương ứng. Vì vậy, lựa chọn primary key ảnh hưởng tới kích thước và chi phí của mọi secondary index; còn việc tạo quá nhiều index làm tăng dung lượng và chi phí ghi.

Trong module `DATABASE_MYSQL`, thiết kế index cần bắt đầu từ ràng buộc dữ liệu và truy vấn thực tế. Một unique index có thể vừa bảo vệ tính duy nhất vừa phục vụ truy vấn; một secondary index không unique có thể cải thiện tốc độ đọc nhưng không thay thế được ràng buộc nghiệp vụ. Bài học tập trung vào MySQL 8.0 trở lên và InnoDB.

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt `PRIMARY KEY`, `UNIQUE KEY` và secondary index không unique.
- Giải thích clustered index và cách secondary index định vị hàng trong InnoDB.
- Tạo khóa chính đơn cột, khóa ghép, unique index và index thường.
- Hiểu `NULL`, collation và quy tắc so sánh ảnh hưởng tới tính duy nhất.
- Giải thích vì sao unique index trên nhiều cột chỉ bảo đảm duy nhất cho cả tổ hợp.
- Hiểu leftmost prefix của composite index và chọn thứ tự cột phù hợp.
- Nhận biết prefix index và giới hạn của unique prefix index.
- Dùng index để hỗ trợ truy vấn, covering access và khóa ngoại.
- Kiểm tra index bằng `SHOW INDEX`, `INFORMATION_SCHEMA` và `EXPLAIN`.
- Cân nhắc chi phí ghi, dung lượng, trùng lặp index và thay đổi schema.

## 1. Ba loại index thường gặp

| Loại | Vai trò chính | Quy tắc duy nhất | Số lượng trong một bảng |
|---|---|---|---|
| `PRIMARY KEY` | Định danh hàng và làm clustered index của InnoDB | Luôn duy nhất, không nhận `NULL` | Tối đa một |
| `UNIQUE KEY` | Bảo vệ tính duy nhất của một cột hoặc tổ hợp cột | Duy nhất theo quy tắc so sánh; cột nullable có thể có nhiều `NULL` | Có thể có nhiều |
| Secondary index thường | Hỗ trợ lọc, join, sắp xếp và covering access | Không bảo đảm duy nhất | Có thể có nhiều |

`PRIMARY KEY` và `UNIQUE KEY` đều tạo index. Trong MySQL, `UNIQUE KEY` và `UNIQUE INDEX` là hai cách khai báo index duy nhất; unique constraint được MySQL thực thi bằng unique index. Secondary index thường được tạo bằng `INDEX` hoặc `KEY`.

Ví dụ tổng hợp:

```sql
CREATE TABLE app_user (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    username VARCHAR(80) NOT NULL,
    display_name VARCHAR(160) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_user_email (email),
    UNIQUE KEY uq_user_username (username),
    KEY idx_user_status_created (status, created_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

Trong bảng này:

- `user_id` là primary key, xác định duy nhất từng hàng.
- `email` và `username` có unique index để ngăn hai tài khoản dùng cùng giá trị theo collation của cột.
- `(status, created_at)` là secondary index thường để hỗ trợ truy vấn theo trạng thái và thời điểm.
- `display_name` không có index vì ví dụ chưa đặt ra truy vấn cần tìm/sắp xếp theo cột này.

## 2. PRIMARY KEY trong InnoDB

Primary key là ràng buộc định danh hàng. Một bảng chỉ có một primary key; khóa đó có thể gồm một hoặc nhiều cột. Mọi cột thuộc primary key đều được xem là `NOT NULL`.

### 2.1. Primary key đơn cột

```sql
CREATE TABLE product (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_name VARCHAR(150) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE=InnoDB;
```

`product_id` là khóa duy nhất cho mỗi sản phẩm. `AUTO_INCREMENT` cấp giá trị số mới khi insert không cung cấp ID. Không nên giả định các ID sẽ liên tục tuyệt đối: rollback, xóa hàng, cache cấp ID hoặc các yếu tố vận hành khác có thể tạo khoảng trống.

### 2.2. Primary key ghép

Khi danh tính hàng được xác định bởi nhiều cột, có thể dùng composite primary key:

```sql
CREATE TABLE order_item (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_order_item_product (product_id)
) ENGINE=InnoDB;
```

`order_id` có thể lặp lại vì một đơn có nhiều dòng; `line_no` có thể lặp ở các đơn khác nhau. Cặp `(order_id, line_no)` mới là duy nhất.

Thứ tự cột trong primary key ghép có ý nghĩa đối với B-tree. Khóa `(order_id, line_no)` hỗ trợ tìm theo `order_id` hoặc theo cả hai cột; nó không cung cấp đường truy cập tương đương cho truy vấn chỉ lọc `line_no`.

### 2.3. InnoDB dùng primary key làm clustered index

Trong InnoDB, dữ liệu hàng được lưu trong các leaf page của clustered index, thường là primary key. Truy vấn theo primary key đi tới clustered B-tree để tìm hàng. Các secondary index lưu khóa secondary cùng giá trị primary key cần thiết để định vị hàng.

Nếu bảng không khai báo primary key, InnoDB chọn unique index đầu tiên mà mọi cột đều `NOT NULL` làm clustered index nếu có. Nếu không có khóa phù hợp, InnoDB tạo row ID nội bộ ẩn làm clustered index. Thiết kế bảng ứng dụng nên khai báo primary key tường minh để định danh hàng và quan hệ tham chiếu rõ ràng.

### 2.4. Primary key nên ổn định

Thay đổi primary key có thể làm thay đổi vị trí hàng trong clustered index và yêu cầu cập nhật các secondary index mang khóa đó. Nếu primary key được các bảng khác tham chiếu, migration còn ảnh hưởng tới foreign key, dữ liệu con và ứng dụng.

Ưu tiên khóa duy nhất, `NOT NULL`, ổn định và đủ hẹp. `BIGINT` thường phù hợp với ID nội bộ; khóa ghép tự nhiên vẫn hợp lý khi các thành phần nhỏ, ổn định và phản ánh đúng danh tính hàng. Không dùng một cột có thể đổi như email hoặc tên làm primary key chỉ vì hiện tại nó có vẻ duy nhất.

## 3. UNIQUE KEY và unique constraint

Unique index ngăn hai hàng có cùng giá trị trên toàn bộ các cột được index, theo quy tắc so sánh của kiểu dữ liệu và collation. Có thể khai báo unique index ngay khi tạo bảng:

```sql
CREATE TABLE customer (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    external_ref VARCHAR(60) NOT NULL,
    phone VARCHAR(30) NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (customer_id),
    CONSTRAINT uq_customer_email UNIQUE (email),
    UNIQUE KEY uq_customer_external_ref (external_ref),
    UNIQUE INDEX uq_customer_phone (phone)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

Các cách viết trên đều tạo unique index. Tên constraint/index giúp người vận hành nhận diện ràng buộc trong thông báo lỗi và metadata. Trong MySQL, unique constraint được thực thi bằng index; không có một cấu trúc unique constraint tách rời khỏi index như một số hệ quản trị khác.

Có thể thêm unique index sau khi tạo bảng bằng `ALTER TABLE`. Ví dụ với bảng import ban đầu chưa có ràng buộc:

```sql
CREATE TABLE customer_email_import (
    import_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    PRIMARY KEY (import_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

ALTER TABLE customer_email_import
ADD UNIQUE KEY uq_customer_email_import (email);
```

Nếu dữ liệu hiện có đã trùng theo quy tắc so sánh, lệnh tạo unique index sẽ thất bại. Cần tìm và xử lý dữ liệu trùng trước khi triển khai ràng buộc.

### 3.1. UNIQUE trên một cột

```sql
CREATE TABLE customer_email_registry (
    email VARCHAR(255) NOT NULL
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

CREATE UNIQUE INDEX uq_customer_email_registry
ON customer_email_registry (email);
```

Mỗi giá trị email khác `NULL` chỉ được xuất hiện tối đa một lần theo collation. Nếu cột `email` là `NOT NULL`, mọi hàng phải có email và email phải duy nhất.

### 3.2. UNIQUE trên nhiều cột

```sql
CREATE TABLE tenant_member (
    member_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    username VARCHAR(80) NOT NULL,
    full_name VARCHAR(160) NOT NULL,
    PRIMARY KEY (member_id),
    UNIQUE KEY uq_tenant_username (tenant_id, username)
) ENGINE=InnoDB;
```

Unique index này bảo đảm một `username` không được lặp trong cùng `tenant_id`. Cùng một username có thể xuất hiện ở hai tenant khác nhau:

| tenant_id | username | Hợp lệ? |
|---:|---|---|
| 10 | `alex` | Có |
| 10 | `sam` | Có |
| 20 | `alex` | Có |
| 10 | `alex` | Không, trùng tổ hợp `(10, 'alex')` |

Unique `(tenant_id, username)` không bảo đảm `tenant_id` duy nhất hoặc `username` duy nhất trên toàn bảng. Nó chỉ bảo đảm tính duy nhất của cả tuple.

### 3.3. UNIQUE và NULL

Trong MySQL, unique index cho phép nhiều hàng có `NULL` ở cột nullable vì `NULL` không được so sánh như một giá trị bằng `NULL` trong kiểm tra unique. Ví dụ:

```sql
CREATE TABLE contact_method (
    contact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    optional_phone VARCHAR(30) NULL,
    PRIMARY KEY (contact_id),
    UNIQUE KEY uq_optional_phone (optional_phone)
) ENGINE=InnoDB;

INSERT INTO contact_method (optional_phone)
VALUES (NULL), (NULL), ('0900000001');
```

Hai hàng `NULL` được phép; nhưng thêm một hàng có `'0900000001'` lần nữa sẽ vi phạm unique index.

Với unique index ghép, nếu bất kỳ thành phần nullable nào trong tổ hợp là `NULL`, MySQL có thể cho phép nhiều hàng có cùng các giá trị còn lại và `NULL` ở thành phần đó. Ví dụ, unique `(tenant_id, optional_code)` không ngăn nhiều hàng có cùng `tenant_id` và `optional_code IS NULL`.

Nếu nghiệp vụ yêu cầu bắt buộc có giá trị duy nhất, khai báo các cột đó `NOT NULL`. Không dùng unique index nullable như một cách bảo đảm mỗi hàng đều có mã định danh.

### 3.4. Unique index bảo vệ tính duy nhất khi ghi đồng thời

Không nên kiểm tra trùng bằng một câu `SELECT` rồi mới `INSERT` như thể hai thao tác luôn diễn ra tuần tự:

```sql
SELECT customer_id
FROM customer
WHERE email = 'new@example.com';

-- Nếu không có hàng, ứng dụng mới INSERT.
```

Hai request có thể cùng chạy `SELECT`, cùng thấy chưa có email rồi cùng thử insert. Unique index mới là lớp bảo vệ cuối cùng ở database: chỉ một hàng có giá trị đó được chấp nhận; request còn lại nhận lỗi duplicate key (thường là error 1062). Ứng dụng có thể kiểm tra kết quả trực tiếp bằng `INSERT` và xử lý lỗi unique violation theo nghiệp vụ.

Có thể dùng `INSERT ... ON DUPLICATE KEY UPDATE` khi quy tắc nghiệp vụ thật sự là cập nhật hàng xung đột. Lệnh này được kích hoạt bởi xung đột trên bất kỳ primary key hoặc unique index nào; nếu bảng có nhiều unique key, phải hiểu rõ hàng nào có thể xung đột và tránh thiết kế upsert mơ hồ. Không dùng upsert chỉ để che mọi lỗi duplicate.

### 3.5. UNIQUE phụ thuộc collation

Đối với cột chuỗi, so sánh unique tuân theo collation. Với collation không phân biệt hoa thường, hai chuỗi như `'Alice'` và `'alice'` có thể được xem là tương đương và không thể cùng tồn tại trong unique index. Collation accent-insensitive cũng có thể coi một số ký tự có/không dấu là tương đương.

Kiểm tra charset/collation của cột và chọn quy tắc so sánh theo nghiệp vụ:

```sql
SHOW FULL COLUMNS FROM customer;
```

Nếu mã định danh cần phân biệt byte hoặc hoa/thường, chọn collation phù hợp, ví dụ collation binary cho cột chuỗi hoặc dùng kiểu `BINARY` khi dữ liệu thực sự là byte. Không đổi collation chỉ để cho phép dữ liệu trùng về mặt hiển thị; cần xác định rõ quy tắc chuẩn hóa tên/mã trước khi tạo unique index.

## 4. Secondary index không unique

Secondary index thường tạo đường truy cập bổ sung tới hàng. Nó không ngăn giá trị lặp lại:

```sql
CREATE INDEX idx_customer_status
ON customer (status);
```

Nhiều khách hàng có thể có cùng `status`. Index giúp MySQL tìm nhanh các hàng có trạng thái cần lọc, nhưng không thay đổi tính hợp lệ của dữ liệu.

Ví dụ truy vấn:

```sql
SELECT customer_id, email
FROM customer
WHERE status = 'ACTIVE';
```

Nếu `status` có độ chọn lọc phù hợp và bảng đủ lớn, optimizer có thể dùng `idx_customer_status`. Nếu phần lớn hàng đều `ACTIVE`, table scan có thể rẻ hơn; có index không có nghĩa optimizer luôn phải dùng index.

### 4.1. Secondary index lưu primary key

Leaf entry của secondary index InnoDB chứa các cột index cùng các thành phần primary key cần để định vị hàng trong clustered index. Ví dụ, nếu primary key là `customer_id` và secondary index là `(status)`, entry có thể hiểu về mặt logic là `(status, customer_id)`.

Điều này giúp truy vấn chỉ cần `status` và `customer_id` có khả năng được phục vụ bằng covering index mà không cần đọc clustered record:

```sql
EXPLAIN
SELECT status, customer_id
FROM customer
WHERE status = 'ACTIVE';
```

Nếu truy vấn cần `email` mà `email` không nằm trong secondary entry, InnoDB có thể phải lookup clustered index để lấy cột đó:

```sql
SELECT status, customer_id, email
FROM customer
WHERE status = 'ACTIVE';
```

Đây là lý do độ rộng primary key ảnh hưởng tới dung lượng của mọi secondary index, kể cả index không unique.

### 4.2. Secondary index cũng có thể là composite

Tạo bảng đơn hàng dùng trong các ví dụ composite index tiếp theo:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB;

CREATE INDEX idx_order_status_created
ON orders (status, created_at);
```

Composite index hỗ trợ các truy vấn dựa trên thứ tự cột của index. `idx_order_status_created` có thể hỗ trợ lọc theo `status`, hoặc theo `status` kết hợp khoảng `created_at`; không thay thế trực tiếp index chỉ trên `created_at` khi truy vấn không có điều kiện phù hợp trên cột đầu tiên.

## 5. Composite index và leftmost prefix

Với index:

```sql
CREATE INDEX idx_tenant_status_created
ON orders (tenant_id, status, created_at);
```

Thứ tự key là `tenant_id` trước, rồi `status`, rồi `created_at`. B-tree được sắp theo tuple này. Vì vậy, các tiền tố bên trái thường có thể được dùng làm access path:

| Điều kiện truy vấn | Có thể dùng tiền tố index? |
|---|---|
| `tenant_id = 10` | Có |
| `tenant_id = 10 AND status = 'PAID'` | Có |
| `tenant_id = 10 AND status = 'PAID' AND created_at >= ...` | Có |
| `status = 'PAID'` | Không dùng được tiền tố trái theo cách tương đương |
| `created_at >= ...` | Không dùng được tiền tố trái theo cách tương đương |

Optimizer có thể chọn index khác, index skip scan trong một số trường hợp hoặc table scan; bảng trên mô tả nguyên tắc leftmost prefix cơ bản, không phải cam kết rằng mọi truy vấn có tiền tố sẽ luôn dùng index.

### 5.1. Thứ tự cột phải dựa trên truy vấn

Nếu workload thường truy vấn theo tenant rồi lọc status và khoảng ngày, `(tenant_id, status, created_at)` có thể phù hợp. Nếu workload thường tìm theo status trên toàn hệ thống, index đó không nhất thiết đáp ứng tốt truy vấn này.

Không áp dụng máy móc quy tắc “cột có độ chọn lọc cao nhất luôn đứng đầu”. Cần xét:

- Các điều kiện equality thường xuất hiện cùng nhau.
- Điều kiện range và cột sắp xếp.
- Truy vấn có phân vùng theo tenant hay không.
- Số lượng giá trị và phân phối dữ liệu.
- Các truy vấn khác có thể dùng tiền tố trái.
- Chi phí lưu trữ và cập nhật index.

### 5.2. Equality và range

Trong index `(tenant_id, status, created_at)`, điều kiện equality trên `tenant_id` và `status` thường cho phép đi tới vùng key phù hợp, sau đó dùng range trên `created_at`:

```sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
```

Điều kiện trên cột sau một range thường không tiếp tục thu hẹp range scan theo cùng cách như các cột equality trước đó, dù có thể vẫn được dùng làm index condition hoặc filter. Hãy xem `EXPLAIN` để biết phần nào thực sự được dùng làm access condition.

## 6. UNIQUE composite và NULL trong thực tế

Một unique index ghép thường dùng để diễn tả phạm vi duy nhất:

```sql
CREATE TABLE external_identity (
    identity_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    provider VARCHAR(30) NOT NULL,
    provider_user_id VARCHAR(120) NOT NULL,
    tenant_id BIGINT UNSIGNED NULL,
    PRIMARY KEY (identity_id),
    UNIQUE KEY uq_provider_user_tenant
        (provider, provider_user_id, tenant_id)
) ENGINE=InnoDB;
```

Nếu `tenant_id` được phép `NULL`, nhiều hàng cùng `provider`, `provider_user_id` và `tenant_id IS NULL` có thể tồn tại. Nếu nghiệp vụ yêu cầu mỗi provider user chỉ xuất hiện một lần khi tenant không được xác định, cần thiết kế ràng buộc rõ hơn, ví dụ tách các trường hợp global và tenant-scoped hoặc dùng cột biểu diễn giá trị chuẩn hóa có quy tắc `NOT NULL`.

Đừng dùng `COALESCE(tenant_id, 0)` trong truy vấn rồi giả định unique index trên `tenant_id` sẽ bảo đảm cùng ngữ nghĩa. Nếu cần chuẩn hóa `NULL` thành sentinel, phải bảo đảm sentinel không phải giá trị hợp lệ và biểu diễn nó bằng generated column/index hoặc schema phù hợp.

## 7. Prefix index

Prefix index chỉ lập chỉ mục một số ký tự đầu của cột chuỗi:

```sql
CREATE TABLE external_record (
    record_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    external_code VARCHAR(200) NOT NULL,
    description VARCHAR(200) NULL,
    PRIMARY KEY (record_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_external_code_prefix
ON external_record (external_code(20));
```

Prefix index có thể giảm kích thước index khi cột chuỗi dài và truy vấn phù hợp với tiền tố. Nó không chứa toàn bộ giá trị cột; nếu truy vấn cần so sánh đầy đủ, MySQL có thể phải kiểm tra lại hàng để xác nhận.

### 7.1. UNIQUE prefix không bảo đảm toàn bộ chuỗi duy nhất

```sql
CREATE UNIQUE INDEX uq_code_prefix
ON external_record (external_code(12));
```

Unique index này yêu cầu 12 ký tự đầu (theo đơn vị prefix của kiểu chuỗi) không trùng, không phải toàn bộ `external_code` duy nhất. Hai mã khác nhau nhưng có cùng prefix 12 ký tự sẽ bị từ chối.

Nếu nghiệp vụ yêu cầu toàn bộ mã duy nhất, dùng unique index trên toàn bộ cột khi giới hạn key length cho phép. Không rút prefix tùy tiện chỉ để làm index nhỏ hơn.

Với `TEXT`/`BLOB`, MySQL yêu cầu độ dài prefix khi tạo index. Độ dài prefix được tính theo ký tự đối với kiểu chuỗi và byte đối với kiểu binary; cần tính charset và giới hạn key length.

## 8. Index và khóa ngoại

InnoDB cần index để kiểm tra quan hệ foreign key. Cột được tham chiếu ở bảng cha phải được index theo yêu cầu của InnoDB; thông thường nên tham chiếu primary key hoặc unique key. Ở bảng con, InnoDB cần index có các cột foreign key ở vị trí đầu để kiểm tra và tìm các hàng liên quan; nếu chưa có index phù hợp, MySQL có thể tự tạo index.

Ví dụ:

```sql
CREATE TABLE department (
    department_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    department_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (department_id),
    UNIQUE KEY uq_department_name (department_name)
) ENGINE=InnoDB;

CREATE TABLE employee (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    department_id BIGINT UNSIGNED NOT NULL,
    employee_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (employee_id),
    KEY idx_employee_department (department_id),
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id)
        REFERENCES department (department_id)
) ENGINE=InnoDB;
```

`idx_employee_department` hỗ trợ join và kiểm tra hàng con khi cập nhật/xóa hàng cha. Không nên tạo thêm một index trùng hệt chỉ vì có foreign key; kiểm tra index đã có trước khi bổ sung.

Các cột tương ứng ở hai phía foreign key cần có kiểu tương thích. Với kiểu số, cần chú ý kích thước và signed/unsigned; với chuỗi, charset/collation cũng cần tương thích theo quy tắc của MySQL.

## 9. UNIQUE và xử lý dữ liệu trùng

Trước khi thêm unique index vào bảng đang có dữ liệu, hãy tìm các nhóm trùng:

```sql
SELECT email, COUNT(*) AS duplicate_count
FROM customer
GROUP BY email
HAVING COUNT(*) > 1;
```

Với unique composite:

```sql
SELECT tenant_id, username, COUNT(*) AS duplicate_count
FROM tenant_member
GROUP BY tenant_id, username
HAVING COUNT(*) > 1;
```

Lưu ý: `GROUP BY` gom `NULL` vào một nhóm, trong khi unique index cho phép nhiều `NULL`. Vì vậy, truy vấn tìm duplicate cần lọc các thành phần nullable theo đúng ngữ nghĩa unique của MySQL nếu muốn dự đoán chính xác việc tạo index có thất bại hay không.

Ví dụ chỉ tìm trùng với tất cả thành phần khác `NULL`:

```sql
CREATE TABLE optional_identity (
    identity_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NULL,
    optional_code VARCHAR(80) NULL,
    PRIMARY KEY (identity_id),
    UNIQUE KEY uq_optional_identity (tenant_id, optional_code)
) ENGINE=InnoDB;

SELECT tenant_id, optional_code, COUNT(*) AS duplicate_count
FROM optional_identity
WHERE tenant_id IS NOT NULL
  AND optional_code IS NOT NULL
GROUP BY tenant_id, optional_code
HAVING COUNT(*) > 1;
```

Nếu unique index ghép có nhiều cột nullable, hãy kiểm tra các nhóm có bất kỳ thành phần `NULL` riêng biệt; các nhóm đó không nhất thiết là duplicate theo quy tắc unique index.

Khi tạo unique index bị lỗi duplicate key, không nên xóa tùy tiện một hàng. Hãy xác định bản ghi chuẩn, hợp nhất dữ liệu tham chiếu, xử lý lịch sử và đảm bảo ứng dụng không tiếp tục tạo duplicate trong lúc migration. Với bảng đang ghi liên tục, cần kế hoạch triển khai có kiểm soát để tránh race giữa bước dọn dữ liệu và bước tạo unique index.

## 10. Dùng index để truy vấn và đọc EXPLAIN

Index được thiết kế để hỗ trợ access path. Ví dụ:

```sql
EXPLAIN
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

Khi đọc `EXPLAIN`, chú ý:

- `possible_keys`: index optimizer xem là ứng viên.
- `key`: index thực tế được chọn; `NULL` có nghĩa không chọn index.
- `key_len`: độ dài phần key được sử dụng theo cách truy cập đã chọn, không phải tổng kích thước index.
- `rows`: số hàng ước lượng phải đọc; với InnoDB có thể là ước lượng.
- `filtered`: tỷ lệ hàng ước tính còn lại sau điều kiện lọc.
- `Extra`: thông tin như `Using index`, `Using index condition`, `Using filesort` hoặc `Using temporary`.

### 10.1. Covering index

Nếu index chứa mọi cột truy vấn cần, MySQL có thể đọc dữ liệu từ index mà không cần lookup thêm clustered record. Trong `EXPLAIN`, `Using index` thường cho biết truy vấn được phục vụ bằng covering index.

### 10.2. Index Condition Pushdown

`Using index condition` là dấu hiệu điều kiện được đẩy xuống storage engine để kiểm tra trên index entry trước khi đọc row đầy đủ. Nó không đồng nghĩa với covering index. Một truy vấn có thể dùng index condition nhưng vẫn cần lookup clustered record.

### 10.3. EXPLAIN ANALYZE

MySQL 8.0.18 trở lên hỗ trợ `EXPLAIN ANALYZE` cho truy vấn đọc, thực thi truy vấn và báo số hàng/thời gian thực tế của iterator. Ví dụ:

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

Lệnh này thực sự chạy statement. Chỉ dùng trên truy vấn đọc có phạm vi được kiểm soát và dữ liệu lab/staging khi chưa biết chi phí. So sánh ước lượng với thực tế để nhận ra thống kê sai, độ chọn lọc khác dự kiến hoặc lượng hàng trung gian lớn.

## 11. Tạo, xem và xóa index

Tạo index:

```sql
CREATE INDEX idx_orders_created_at
ON orders (created_at);

CREATE UNIQUE INDEX uq_orders_external_ref
ON orders (external_ref);
```

Hoặc dùng `ALTER TABLE`:

```sql
ALTER TABLE orders
ADD INDEX idx_orders_total_amount (total_amount);
```

Xem index:

```sql
SHOW INDEX FROM orders;
SHOW CREATE TABLE orders\G
```

Có thể đọc metadata index có cấu trúc bằng `INFORMATION_SCHEMA.STATISTICS`:

```sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART,
    COLLATION
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

`NON_UNIQUE = 0` biểu thị index duy nhất; `SEQ_IN_INDEX` cho thứ tự cột; `SUB_PART` cho biết prefix length nếu index chỉ lập chỉ mục một phần cột. Metadata này mô tả index được khai báo, không nhất thiết hiển thị mọi chi tiết vật lý của phần primary key InnoDB mang ngầm trong secondary entry.

Xóa secondary hoặc unique index:

```sql
ALTER TABLE orders DROP INDEX idx_orders_created_at;
```

Xóa primary key dùng cú pháp riêng:

```sql
ALTER TABLE orders DROP PRIMARY KEY;
```

Không chạy lệnh xóa primary key nếu chưa có kế hoạch thay thế. InnoDB vẫn cần clustered index; khi xóa PK, nó phải chọn một unique `NOT NULL` index khác hoặc tạo hidden row ID. Thao tác thay primary key có thể tốn kém và ảnh hưởng toàn bộ secondary index.

### 11.1. Thay đổi index trên bảng lớn

Tạo/xóa index có thể cần đọc và xây dựng lại cấu trúc index, sử dụng I/O, CPU, dung lượng tạm và metadata lock. Nhiều thao tác hỗ trợ online DDL hoặc `ALGORITHM`/`LOCK` khác nhau tùy loại thay đổi, engine và phiên bản. Không giả định mọi `ALTER TABLE` đều không khóa hoặc hoàn toàn tức thời.

Trước khi thay đổi production:

1. Kiểm tra dung lượng trống và thời gian build trên bản sao dữ liệu đại diện.
2. Xác định thuật toán/lock mà phiên bản hỗ trợ.
3. Kiểm tra replication lag và tải I/O trong quá trình build.
4. Chuẩn bị cách theo dõi và kế hoạch rollback/khôi phục.
5. Xác minh truy vấn sau thay đổi bằng `EXPLAIN` và số liệu thực tế.

## 12. Chi phí và các index dư thừa

Mỗi index bổ sung tiêu tốn dung lượng và phải được cập nhật khi insert, delete hoặc thay đổi cột liên quan. Nhiều index có thể làm tăng thời gian ghi, redo/undo, I/O, thời gian backup và chi phí migration.

Không tạo index cho mọi cột. Cân nhắc:

- Truy vấn nào thực sự cần index?
- Index có đủ chọn lọc để giảm số hàng đọc không?
- Index ghép hiện có đã phục vụ tiền tố trái chưa?
- Có index nào trùng hoặc bị index khác bao phủ không?
- Index có được dùng trong workload thực tế không?
- Chi phí ghi tăng thêm có chấp nhận được không?

Ví dụ, nếu đã có index `(tenant_id, status, created_at)`, một index riêng `(tenant_id)` có thể dư thừa cho nhiều workload vì nó là tiền tố trái. Tuy nhiên, không được xóa chỉ dựa trên suy luận: index ngắn hơn có thể rẻ hơn cho truy vấn rất phổ biến, index có thể phục vụ foreign key hoặc có yêu cầu khác. Đo workload và kiểm tra constraint trước khi loại bỏ.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng UNIQUE nullable nhưng kỳ vọng chỉ có một NULL | Nhiều hàng NULL vẫn được chấp nhận | Đặt `NOT NULL` hoặc mô hình hóa trạng thái thiếu rõ ràng |
| Nghĩ UNIQUE `(a, b)` làm `a` hoặc `b` riêng lẻ duy nhất | Chỉ tổ hợp cả hai cột được bảo đảm | Tạo unique index riêng nếu nghiệp vụ yêu cầu |
| Nghĩ index `(a, b)` hỗ trợ truy vấn chỉ theo `b` như index `(b)` | Vi phạm leftmost prefix | Thiết kế index theo mẫu truy vấn thực tế |
| Tạo UNIQUE prefix cho mã dài | Chỉ prefix bị buộc duy nhất; có thể từ chối hai giá trị toàn phần khác nhau | Dùng unique index toàn cột nếu nghiệp vụ yêu cầu toàn chuỗi duy nhất |
| Bỏ qua collation | Hai chuỗi khác cách viết có thể được xem là bằng nhau | Chọn charset/collation theo quy tắc định danh |
| Tạo index mà không kiểm tra dữ liệu cũ | DDL thất bại do duplicate key | Tìm, xử lý duplicate và triển khai có kiểm soát |
| Tạo nhiều index trùng nhau | Tốn dung lượng và làm DML chậm | Đánh giá index prefix, workload và constraint trước khi xóa |
| Cho rằng optimizer luôn dùng index | Table scan có thể rẻ hơn với bảng nhỏ hoặc điều kiện ít chọn lọc | Đọc `EXPLAIN`, đo dữ liệu thực tế |
| Nhầm `Using index condition` với covering index | Đánh giá sai việc có lookup clustered row hay không | Phân biệt ICP và `Using index` |
| Thay primary key mà không tính secondary index | DDL tốn kém, ảnh hưởng khóa ngoại và ứng dụng | Lập kế hoạch migration toàn bộ quan hệ |

## 14. Quy trình thiết kế PRIMARY, UNIQUE và secondary index

Khi thiết kế một bảng, thực hiện theo trình tự:

1. Xác định danh tính của một hàng; chọn primary key duy nhất, `NOT NULL`, ổn định.
2. Liệt kê các quy tắc nghiệp vụ về giá trị không được trùng; chuyển chúng thành unique constraint/index.
3. Quyết định cột nào bắt buộc `NOT NULL`; không để unique nullable thay thế quy tắc bắt buộc có giá trị.
4. Xác định collation và cách chuẩn hóa chuỗi cho các mã định danh.
5. Liệt kê truy vấn lọc, join, sort và range phổ biến.
6. Thiết kế secondary/composite index theo thứ tự cột và leftmost prefix.
7. Tính tới việc primary key được mang theo trong secondary index.
8. Kiểm tra index phục vụ foreign key và tránh tạo bản trùng.
9. Xem xét chi phí DML, dung lượng và thời gian triển khai DDL.
10. Kiểm tra bằng `SHOW INDEX`, `EXPLAIN` và workload đại diện; chỉ giữ index có lý do rõ ràng.

## 15. Bài thực hành

Thực hiện trong database lab riêng với InnoDB:

1. Tạo bảng `app_user` với primary key `BIGINT AUTO_INCREMENT`, unique email, unique username và secondary index theo status/time.
2. Thử insert hai hàng cùng email; quan sát lỗi duplicate key.
3. Tạo unique index trên một cột nullable; insert nhiều `NULL` và một giá trị lặp để quan sát quy tắc.
4. Tạo unique composite `(tenant_id, username)`; xác nhận cùng username ở hai tenant hợp lệ nhưng trùng trong một tenant bị từ chối.
5. Tạo unique composite có cột nullable; thử các tổ hợp có `NULL` để xác nhận chúng không được kiểm tra như giá trị bằng nhau.
6. Đổi collation của cột thử nghiệm sang collation không phân biệt hoa thường; kiểm tra `'Alice'` và `'alice'` với unique index.
7. Tạo index `(tenant_id, status, created_at)`; thử các truy vấn có và không có tiền tố trái.
8. So sánh `EXPLAIN` cho truy vấn chỉ lấy các cột nằm trong secondary index với truy vấn cần thêm cột ngoài index.
9. Tạo prefix index và unique prefix index trong lab; thử hai chuỗi khác toàn phần nhưng trùng prefix.
10. Tạo bảng cha-con với foreign key; xem index phía con và kiểm tra index đã có có đáp ứng tiền tố foreign key không.
11. Dùng `SHOW INDEX` và `INFORMATION_SCHEMA.STATISTICS` để lập danh sách index của bảng.
12. Tạo hai index có tiền tố trùng nhau; đo workload rồi giải thích vì sao chưa thể xóa index chỉ dựa vào tên hoặc cấu trúc.
13. Chạy `EXPLAIN ANALYZE` trên truy vấn đọc trong lab và so sánh số hàng ước lượng với số hàng thực tế.
14. Viết đề xuất index cho một bảng đơn hàng: nêu primary key, unique rules, secondary index, truy vấn được hỗ trợ và chi phí ghi dự kiến.

Bạn hoàn thành bài khi có thể diễn đạt ràng buộc dữ liệu bằng PRIMARY/UNIQUE, chọn secondary index theo truy vấn, dự đoán được hành vi với NULL/collation và giải thích được chi phí mỗi index trong InnoDB.

## 16. Nguyên tắc cần ghi nhớ

- Một bảng chỉ có một `PRIMARY KEY`; khóa này luôn duy nhất và không nhận `NULL`.
- InnoDB thường dùng primary key làm clustered index; leaf page chứa dữ liệu hàng.
- `UNIQUE` tạo index duy nhất; có thể có nhiều unique index trên một bảng.
- Unique index nullable cho phép nhiều `NULL`; dùng `NOT NULL` nếu mọi hàng phải có giá trị.
- Unique composite bảo đảm duy nhất cho cả tổ hợp, không bảo đảm từng cột riêng lẻ.
- Collation quyết định cách so sánh chuỗi trong unique index.
- Secondary index thường không bảo đảm duy nhất và lưu kèm các thành phần primary key cần để định vị hàng.
- Composite index tuân theo leftmost prefix; thứ tự cột phải phù hợp truy vấn.
- Prefix index chỉ lưu một phần chuỗi; unique prefix chỉ bảo đảm prefix duy nhất.
- Index có thể hỗ trợ covering access, nhưng `Using index condition` không đồng nghĩa với covering index.
- InnoDB cần index phù hợp để kiểm tra foreign key; tránh tạo index trùng.
- Mỗi index tăng dung lượng và chi phí INSERT/UPDATE/DELETE; không index mọi cột.
- Dữ liệu duplicate hiện có có thể khiến tạo unique index thất bại.
- `EXPLAIN` cho biết access path ước lượng; `EXPLAIN ANALYZE` chạy truy vấn và đo thực tế.
- Đánh giá index dựa trên constraint, workload và phép đo, không chỉ dựa vào số lượng index.
