# Comment, quy ước đặt tên và tài liệu hóa schema

Schema MySQL không chỉ là tập hợp bảng và cột. Khi hệ thống lớn dần, người phát triển và vận hành cần hiểu mỗi bảng lưu dữ liệu gì, mỗi cột có ý nghĩa và đơn vị nào, chỉ mục phục vụ truy vấn nào, các bảng liên hệ với nhau ra sao và ai chịu trách nhiệm về dữ liệu. Comment, quy ước đặt tên và tài liệu hóa schema giúp trả lời những câu hỏi đó ngay trong quá trình thiết kế và bảo trì database.

MySQL hỗ trợ comment như metadata cho bảng, cột và chỉ mục. Comment được lưu cùng định nghĩa đối tượng và có thể đọc lại qua `SHOW CREATE TABLE` hoặc `INFORMATION_SCHEMA`. Quy ước đặt tên tạo ra cách diễn đạt nhất quán; tài liệu schema kết hợp DDL, metadata, sơ đồ quan hệ và mô tả nghiệp vụ để người khác có thể hiểu, kiểm tra và thay đổi database an toàn.

## 1. Vì sao cần comment và quy ước đặt tên?

Tên `status`, `type`, `value` hoặc `code` thường không đủ để giải thích ý nghĩa nghiệp vụ. Một bảng `orders` có thể chứa trạng thái thanh toán, trạng thái giao hàng và trạng thái xử lý; nếu chỉ có cột `status`, người đọc phải tìm thêm code hoặc hỏi người viết schema mới hiểu được giá trị.

Một schema được tài liệu hóa tốt giúp:

- Người phát triển mới hiểu nhanh mô hình dữ liệu và quy tắc nghiệp vụ.
- Người viết SQL biết cột nào có thể lọc, nối bảng hoặc dùng làm khóa.
- Người vận hành nhận diện dữ liệu quan trọng khi backup, restore và xử lý sự cố.
- Nhóm phân tích hiểu ý nghĩa, đơn vị và giới hạn của dữ liệu.
- Các lần migration có cơ sở để đánh giá ảnh hưởng đến ứng dụng và báo cáo.

Comment nên bổ sung ý nghĩa mà tên đối tượng chưa thể hiện rõ. Tên tốt giúp nhận diện nhanh; comment giải thích ngữ nghĩa, đơn vị, quy tắc và các trường hợp đặc biệt.

## 2. Phân biệt comment trong SQL và comment của schema

SQL có cú pháp chú thích để người đọc hiểu câu lệnh:

```sql
-- Lấy các đơn hàng đang chờ xử lý
SELECT id, customer_id, status
FROM orders
WHERE status = 'pending';

# Đây cũng là comment một dòng trong MySQL
SELECT COUNT(*) FROM customers;

/* Comment nhiều dòng
   dùng để giải thích một đoạn SQL */
SELECT id, email
FROM customers;
```

Các comment `--`, `#` và `/* ... */` thuộc văn bản câu lệnh SQL. Chúng giúp người đọc source code hoặc migration nhưng không trở thành mô tả của bảng/cột trong metadata schema.

Ngược lại, từ khóa `COMMENT` trong DDL lưu mô tả của đối tượng database:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL COMMENT 'Email dùng để đăng nhập và liên hệ',
    PRIMARY KEY (id)
) ENGINE=InnoDB
  COMMENT='Thông tin khách hàng của hệ thống';
```

Comment này gắn với định nghĩa bảng và cột. Có thể đọc lại sau khi đóng kết nối hoặc từ một công cụ quản trị khác có quyền xem metadata.

## 3. Thêm comment cho bảng

Trong `CREATE TABLE`, dùng table option `COMMENT` để mô tả mục đích của bảng:

```sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_orders_customer_created_at (customer_id, created_at)
) ENGINE=InnoDB
  COMMENT='Đơn mua hàng do khách hàng tạo';
```

Comment bảng nên trả lời ngắn gọn: bảng đại diện cho thực thể hoặc sự kiện nào, dữ liệu thuộc miền nghiệp vụ nào và có điểm gì cần lưu ý. Không nên dùng comment bảng để chép lại toàn bộ tài liệu thiết kế hoặc ghi thông tin thay đổi theo thời gian như người trực ca hiện tại.

Có thể cập nhật comment của bảng đã tồn tại:

```sql
ALTER TABLE orders
COMMENT = 'Đơn mua hàng và trạng thái xử lý của khách hàng';
```

Việc thay đổi comment là một thay đổi DDL. Cần thực hiện qua migration được quản lý giống các thay đổi schema khác để lịch sử thay đổi có thể tái lập và review.

## 4. Thêm comment cho cột

Comment cột giải thích ý nghĩa nghiệp vụ, miền giá trị, đơn vị hoặc quy tắc diễn giải. Ví dụ:

```sql
CREATE TABLE products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Mã sản phẩm nội bộ',
    sku VARCHAR(64) NOT NULL COMMENT 'Mã hàng duy nhất do doanh nghiệp quản lý',
    name VARCHAR(200) NOT NULL COMMENT 'Tên hiển thị của sản phẩm',
    price DECIMAL(13, 2) NOT NULL COMMENT 'Giá bán theo đơn vị tiền tệ của cửa hàng',
    is_active BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Cho biết sản phẩm có được phép bán',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Thời điểm tạo bản ghi',
    PRIMARY KEY (id),
    UNIQUE KEY uq_products_sku (sku)
) ENGINE=InnoDB
  COMMENT='Danh mục sản phẩm được phép kinh doanh';
```

Một comment tốt cho cột `price` nên nêu đơn vị tiền tệ hoặc quy tắc xác định currency nếu hệ thống hỗ trợ nhiều loại tiền. Nếu giá được lưu theo đơn vị nhỏ nhất, chẳng hạn đồng hoặc cent, cần ghi rõ để tránh hiểu nhầm. Nếu giá có thể âm vì mục đích điều chỉnh, hoàn tiền hoặc bút toán, cũng cần mô tả quy tắc tương ứng.

Khi sửa comment cột bằng `ALTER TABLE ... MODIFY COLUMN`, cần khai báo lại đầy đủ kiểu dữ liệu và các thuộc tính của cột:

```sql
ALTER TABLE products
MODIFY COLUMN price DECIMAL(13, 2) NOT NULL
COMMENT 'Giá bán, tính theo VND';
```

Không bỏ sót `NOT NULL`, `DEFAULT`, `UNSIGNED`, `AUTO_INCREMENT` hoặc thuộc tính khác đang tồn tại khi dùng `MODIFY COLUMN`. Câu lệnh trên chỉ phù hợp nếu định nghĩa hiện tại đúng là `DECIMAL(13, 2) NOT NULL` và không có thuộc tính khác cần giữ.

## 5. Comment cho index và giới hạn của comment

MySQL cho phép gắn comment vào index để giải thích mục đích của chỉ mục:

```sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_orders_customer_created_at (customer_id, created_at)
        COMMENT 'Phục vụ lịch sử đơn hàng theo khách hàng và thời gian'
) ENGINE=InnoDB
  COMMENT='Đơn mua hàng của khách hàng';
```

Comment index nên giải thích workload hoặc mẫu truy vấn mà chỉ mục hỗ trợ. Tuy nhiên, comment không làm optimizer chọn index và cũng không bảo đảm truy vấn sẽ nhanh hơn. Cần kiểm tra truy vấn và kế hoạch thực thi bằng `EXPLAIN`.

Không phải mọi loại constraint đều có một trường comment độc lập như bảng hoặc cột. Với foreign key, check constraint và quy tắc nghiệp vụ, hãy đặt tên có ý nghĩa, ghi chú trong migration hoặc tài liệu schema, và dùng metadata để mô tả quan hệ có thể truy vấn được.

## 6. Đọc comment qua metadata của MySQL

### 6.1. Xem định nghĩa bảng

`SHOW CREATE TABLE` trả về câu lệnh DDL mà MySQL dùng để mô tả bảng, gồm cột, index, constraint, engine và comment:

```sql
SHOW CREATE TABLE orders\G
```

Đây là cách nhanh để kiểm tra schema thực tế trên server, đặc biệt khi cần so sánh với migration hoặc file DDL trong repository.

### 6.2. Xem comment bảng

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_COMMENT
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

`TABLE_COMMENT` chứa mô tả của bảng. `TABLE_TYPE` giúp phân biệt bảng vật lý với view trong kết quả metadata.

### 6.3. Xem comment cột

```sql
SELECT
    TABLE_NAME,
    ORDINAL_POSITION,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_KEY,
    EXTRA,
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

Truy vấn này có thể dùng để tạo data dictionary cơ bản. Ngoài comment, nó lấy kiểu dữ liệu, khả năng nhận `NULL`, giá trị mặc định, thông tin khóa và thuộc tính bổ sung.

### 6.4. Xem comment index

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    INDEX_TYPE,
    INDEX_COMMENT
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

`SEQ_IN_INDEX` cho biết thứ tự cột trong index ghép. Thứ tự này quan trọng khi đánh giá index có phù hợp với điều kiện lọc và sắp xếp của truy vấn hay không.

## 7. Quy ước đặt tên database, bảng và cột

Quy ước đặt tên nên thống nhất trong toàn bộ module. Một quy ước đơn giản, dễ đọc cho MySQL là dùng chữ thường và `snake_case`:

| Đối tượng | Quy ước gợi ý | Ví dụ |
| --- | --- | --- |
| Database/schema | Tên miền nghiệp vụ hoặc ứng dụng, chữ thường | `commerce` |
| Bảng | Danh từ rõ nghĩa, chọn nhất quán số ít hoặc số nhiều | `customers`, `orders`, `order_items` |
| Cột | Tên thuộc tính cụ thể, `snake_case` | `customer_id`, `created_at` |
| Khóa chính | Thống nhất một mẫu trong toàn hệ thống | `id` |
| Khóa ngoại | Tên thực thể được tham chiếu cộng `_id` | `customer_id` |
| Unique index | `uq_<table>_<columns>` | `uq_customers_email` |
| Secondary index | `idx_<table>_<columns>` | `idx_orders_customer_created_at` |
| Foreign key | `fk_<child_table>_<parent_table>` | `fk_orders_customers` |
| Check constraint | `chk_<table>_<rule>` | `chk_products_price_nonnegative` |

Đây là quy ước nhóm có thể điều chỉnh. Điều quan trọng là cùng một quy tắc được áp dụng nhất quán, tên phản ánh đúng chức năng và không tạo ra xung đột giữa các đối tượng.

### 7.1. Chọn số ít hay số nhiều cho tên bảng

Cả hai cách đều có thể sử dụng:

- Số nhiều: `customers`, `orders`, `order_items`.
- Số ít: `customer`, `order`, `order_item`.

Không có một lựa chọn bắt buộc cho mọi dự án. Chọn một kiểu làm chuẩn và không trộn lẫn tùy tiện. Ví dụ nếu bảng đang dùng số nhiều, hãy đặt `products`, `categories`, `payments` thay vì đột ngột thêm bảng `invoice` số ít mà không có lý do.

### 7.2. Đặt tên cột rõ ngữ nghĩa

Ưu tiên `created_at` hơn `date`, `unit_price` hơn `price2`, `payment_status` hơn `status` nếu bảng có nhiều trạng thái. Với khóa ngoại, tên cột nên chỉ ra thực thể đích như `customer_id`, `warehouse_id`.

Với boolean, có thể dùng tiền tố `is_`, `has_` hoặc `can_` như `is_active`, `has_discount`, `can_refund`. Với thời gian, thống nhất hậu tố như `_at` cho timestamp, `_date` cho ngày không có thời điểm, `_time` cho thời gian trong ngày. Nếu lưu thời điểm UTC, hãy ghi rõ quy ước đó trong tài liệu hoặc comment khi người đọc không thể suy ra từ hệ thống.

Không mã hóa kiểu dữ liệu vào tên cột như `str_customer_name` hoặc `int_quantity`; kiểu có thể thay đổi trong tương lai và thông tin này đã nằm trong metadata. Tránh viết tắt nội bộ khó hiểu, tên chung chung và tên dễ nhầm với từ khóa SQL.

### 7.3. Đặt tên index và constraint

Tên index nên cho biết bảng và các cột chính theo đúng thứ tự của index. Ví dụ:

```sql
CREATE INDEX idx_orders_customer_status_created_at
ON orders (customer_id, status, created_at);
```

Tên `idx_orders_customer_status_created_at` gợi ý index ghép theo `customer_id`, `status`, `created_at`. Tên này không thay thế việc hiểu leftmost prefix của index ghép; cột đầu tiên và thứ tự các cột vẫn quyết định nhiều dạng truy vấn có thể tận dụng index.

Constraint nên có tên ổn định để dễ đọc lỗi và quản lý migration:

```sql
CREATE TABLE order_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_order_items_orders
        FOREIGN KEY (order_id) REFERENCES orders (id),
    CONSTRAINT chk_order_items_quantity_positive
        CHECK (quantity > 0)
) ENGINE=InnoDB;
```

Trong MySQL, tên index cần duy nhất trong phạm vi bảng; tên foreign key constraint nên được đặt duy nhất trong schema để tránh xung đột và dễ quản lý giữa các phiên bản. Tên constraint không cần lặp lại toàn bộ câu mô tả nghiệp vụ; hãy giữ ngắn, ổn định và có thể nhận diện.

### 7.4. Tránh tên gây khó khăn khi vận hành

- Tránh dùng từ khóa SQL hoặc tên hàm làm identifier nếu không cần thiết; việc phải quote bằng backtick liên tục khiến SQL khó đọc.
- Tránh phân biệt tên chỉ bằng chữ hoa/chữ thường vì hành vi tên database/table có thể khác theo hệ điều hành và `lower_case_table_names`.
- Tránh tên quá dài, khó gõ hoặc chứa thông tin thay đổi như số phiên bản ứng dụng.
- Tránh tên viết tắt mà chỉ một người trong nhóm hiểu.
- Giữ tên ổn định; đổi tên cột/bảng có thể ảnh hưởng code, migration, view, trigger, báo cáo và pipeline dữ liệu.

MySQL có giới hạn độ dài identifier theo từng loại đối tượng; nhiều tên đối tượng phổ biến như database, table, column và index có giới hạn 64 ký tự. Hãy kiểm tra giới hạn cụ thể của đối tượng và phiên bản MySQL khi thiết kế naming convention.

## 8. Tài liệu hóa schema bằng nhiều lớp

Comment trong database hữu ích nhưng không thể thay thế toàn bộ tài liệu thiết kế. Nên kết hợp các lớp sau:

| Lớp tài liệu | Nội dung nên có | Nơi duy trì |
| --- | --- | --- |
| DDL/migration | Cấu trúc bảng, cột, index, constraint và thay đổi theo thời gian | Repository và công cụ migration |
| Comment metadata | Mô tả ngắn cho bảng, cột, index | MySQL schema |
| Data dictionary | Ý nghĩa cột, kiểu dữ liệu, đơn vị, nullable, default, nguồn dữ liệu | Tài liệu dự án hoặc catalog |
| ERD | Quan hệ giữa thực thể, cardinality và khóa | Tài liệu kiến trúc |
| Quy tắc nghiệp vụ | Vòng đời trạng thái, công thức tính, quy tắc lưu trữ | Tài liệu nghiệp vụ/domain |
| Vận hành và quản trị | Owner, phân loại dữ liệu, retention, backup, SLA | Runbook/catalog vận hành |

DDL và migration nên là nguồn sự thật có thể tái tạo schema. Tài liệu giải thích giúp con người hiểu thiết kế; nếu tài liệu và DDL lệch nhau, cần xác định nguồn có thẩm quyền và cập nhật lại phần còn lại.

## 9. Tạo data dictionary từ INFORMATION_SCHEMA

Có thể kết hợp metadata bảng và cột để tạo danh mục mô tả dữ liệu:

```sql
SELECT
    t.TABLE_NAME,
    t.TABLE_COMMENT,
    c.ORDINAL_POSITION,
    c.COLUMN_NAME,
    c.COLUMN_TYPE,
    c.IS_NULLABLE,
    c.COLUMN_DEFAULT,
    c.COLUMN_KEY,
    c.EXTRA,
    c.COLUMN_COMMENT
FROM INFORMATION_SCHEMA.TABLES AS t
JOIN INFORMATION_SCHEMA.COLUMNS AS c
  ON c.TABLE_SCHEMA = t.TABLE_SCHEMA
 AND c.TABLE_NAME = t.TABLE_NAME
WHERE t.TABLE_SCHEMA = DATABASE()
  AND t.TABLE_TYPE = 'BASE TABLE'
ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION;
```

Truy vấn tạo một dòng cho mỗi cột, kèm comment của bảng và comment của cột. Có thể xuất kết quả ra CSV hoặc đưa vào quy trình sinh tài liệu tự động. Người chạy cần có quyền xem metadata của các đối tượng liên quan.

Để tài liệu hóa khóa và quan hệ, có thể truy vấn `TABLE_CONSTRAINTS` và `KEY_COLUMN_USAGE`:

```sql
SELECT
    tc.TABLE_NAME,
    tc.CONSTRAINT_NAME,
    tc.CONSTRAINT_TYPE,
    kcu.COLUMN_NAME,
    kcu.ORDINAL_POSITION,
    kcu.REFERENCED_TABLE_NAME,
    kcu.REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS kcu
  ON kcu.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
 AND kcu.TABLE_NAME = tc.TABLE_NAME
 AND kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
ORDER BY tc.TABLE_NAME, tc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION;
```

Kết quả giúp nhận diện primary key, unique constraint, foreign key và cột được tham chiếu. Với check constraint, có thể bổ sung truy vấn `INFORMATION_SCHEMA.CHECK_CONSTRAINTS` và `TABLE_CONSTRAINTS` trên phiên bản hỗ trợ để lấy biểu thức kiểm tra.

## 10. Nguyên tắc viết comment tốt

Comment nên ngắn gọn nhưng đủ ngữ cảnh để người khác hiểu mà không cần đoán:

1. Giải thích ý nghĩa nghiệp vụ, không lặp lại nguyên văn tên cột.
2. Ghi rõ đơn vị đo, currency, timezone hoặc quy ước mã nếu dễ gây nhầm lẫn.
3. Mô tả miền giá trị, ý nghĩa `NULL`, giá trị mặc định và trạng thái đặc biệt khi cần.
4. Với index, giải thích mẫu truy vấn hoặc lý do tồn tại; tránh khẳng định hiệu năng nếu chưa đo.
5. Dùng ngôn ngữ thống nhất trong toàn schema, ưu tiên câu mô tả ngắn và cụ thể.
6. Cập nhật comment cùng migration khi thay đổi ý nghĩa hoặc kiểu dữ liệu.
7. Không đưa mật khẩu, token, dữ liệu cá nhân thật hoặc thông tin nhạy cảm vào comment.

Ví dụ chưa tốt:

```sql
email VARCHAR(254) COMMENT 'Email';
price DECIMAL(13, 2) COMMENT 'Giá';
status VARCHAR(20) COMMENT 'Trạng thái';
```

Ví dụ rõ nghĩa hơn:

```sql
email VARCHAR(254)
    COMMENT 'Địa chỉ email dùng để đăng nhập và nhận thông báo';
price DECIMAL(13, 2)
    COMMENT 'Giá niêm yết, tính theo VND, chưa gồm phí giao hàng';
status VARCHAR(20)
    COMMENT 'Trạng thái thanh toán: pending, paid, failed hoặc refunded';
```

Comment ví dụ cần khớp quy tắc thật của ứng dụng. Nếu trạng thái có thể thay đổi hoặc bổ sung, hãy duy trì danh mục giá trị ở tài liệu nghiệp vụ hoặc bảng tham chiếu phù hợp thay vì để comment trở thành danh sách lỗi thời.

## 11. Quy trình duy trì tài liệu khi schema thay đổi

Mỗi thay đổi schema nên đi cùng thay đổi tài liệu liên quan:

1. Tạo migration có thể review và tái chạy theo quy trình dự án.
2. Cập nhật DDL, comment bảng/cột/index và constraint nếu ngữ nghĩa thay đổi.
3. Đánh giá tác động tới ứng dụng, báo cáo, ETL, view, trigger và consumer dữ liệu.
4. Cập nhật data dictionary, ERD và quy tắc nghiệp vụ có liên quan.
5. Chạy migration trên môi trường kiểm thử và xác minh metadata bằng `SHOW CREATE TABLE`/`INFORMATION_SCHEMA`.
6. Review naming convention, độ dài identifier, khả năng tương thích và backward compatibility.
7. Triển khai theo quy trình release; ghi nhận phiên bản schema và tài liệu được cập nhật.

Không nên sửa schema thủ công trên production rồi quên cập nhật migration. Nếu có thay đổi khẩn cấp, hãy tạo migration đối ứng và cập nhật tài liệu ngay sau khi hệ thống ổn định.

## 12. Bài tập thực hành

1. Tạo bảng `customers` có table comment và ít nhất ba column comment giải thích ngữ nghĩa.
2. Tạo bảng `orders` với tên cột rõ nghĩa, khóa ngoại có tên và index ghép có comment.
3. Dùng `SHOW CREATE TABLE` để đọc lại comment và cấu trúc thực tế.
4. Truy vấn `INFORMATION_SCHEMA.TABLES`, `COLUMNS` và `STATISTICS` để tạo data dictionary đơn giản.
5. Truy vấn `TABLE_CONSTRAINTS` và `KEY_COLUMN_USAGE` để liệt kê quan hệ giữa các bảng.
6. Chọn một bảng trong schema lab và viết lại các tên cột chung chung như `status`, `type`, `value` thành tên cụ thể hơn; giải thích tác động của việc rename đến ứng dụng.
7. Tạo một migration chỉ thay đổi comment và kiểm tra rằng lịch sử migration phản ánh thay đổi đó.
8. Viết một ERD nhỏ cho `customers`, `orders` và `order_items`, rồi đối chiếu ERD với metadata MySQL.

## 13. Ghi nhớ

Comment trong SQL (`--`, `#`, `/* ... */`) chỉ chú thích câu lệnh; `COMMENT` trong DDL lưu metadata cho bảng, cột hoặc index. Có thể đọc lại mô tả qua `SHOW CREATE TABLE` và các cột `TABLE_COMMENT`, `COLUMN_COMMENT`, `INDEX_COMMENT` trong `INFORMATION_SCHEMA`.

Quy ước đặt tên nhất quán bằng chữ thường và `snake_case`, dùng tên có ngữ nghĩa cho bảng, cột, khóa, index và constraint. Tài liệu schema nên kết hợp DDL/migration, comment metadata, data dictionary, ERD, quy tắc nghiệp vụ và runbook vận hành. Khi schema thay đổi, hãy cập nhật tài liệu cùng migration và xác minh lại metadata trên MySQL để tài liệu luôn phản ánh cấu trúc thực tế.
