# Tra cứu cột, giá trị mặc định, ràng buộc và generated column

Khi tiếp nhận một schema MySQL, bạn cần biết mỗi bảng có những cột nào, kiểu dữ liệu ra sao, cột nào được phép `NULL`, giá trị mặc định là gì và các ràng buộc nào đang bảo vệ dữ liệu. Với bảng có generated column, bạn còn cần biết cột đó được tính từ biểu thức nào và được lưu hay tính khi đọc.

MySQL cung cấp các lệnh như `DESCRIBE`, `SHOW FULL COLUMNS`, `SHOW CREATE TABLE` và các view trong `INFORMATION_SCHEMA` để tra cứu metadata. Biết chọn đúng nguồn giúp bạn kiểm tra cấu trúc, viết migration, tạo truy vấn và chẩn đoán lỗi dữ liệu mà không phải đoán từ tên cột.

## 1. Metadata của bảng và cột trong MySQL

Trong MySQL, schema và database được dùng gần như đồng nghĩa khi nói về namespace chứa bảng, view và các đối tượng liên quan. Metadata là dữ liệu mô tả cấu trúc và thuộc tính của những đối tượng đó.

Metadata của một cột có thể cho biết:

- Tên cột và vị trí của nó trong bảng.
- Kiểu dữ liệu đầy đủ, độ dài, precision, scale, charset và collation.
- Cột có cho phép `NULL` hay không.
- Giá trị mặc định và hành vi tự cập nhật.
- Cột có thuộc khóa chính, unique index hoặc chỉ mục khác không.
- Cột có phải `AUTO_INCREMENT`, invisible hay generated column không.
- Biểu thức tạo generated column và loại `VIRTUAL`/`STORED`.
- Comment được ghi trong định nghĩa cột.

Metadata về ràng buộc có thể cho biết tên constraint, loại constraint, các cột tham gia, bảng/cột được tham chiếu và quy tắc `ON UPDATE` hoặc `ON DELETE` của khóa ngoại.

Từ MySQL 8.0, data dictionary được quản lý trong MySQL Server và các giao diện SQL được hỗ trợ như `INFORMATION_SCHEMA`, `SHOW` và `DESCRIBE` là cách phù hợp để đọc metadata. Không nên truy vấn hoặc chỉnh sửa trực tiếp các cấu trúc nội bộ của data dictionary.

## 2. Khám phá nhanh cấu trúc bảng

Giả sử ứng dụng bán hàng có schema `shop` và bảng `order_items`. Một số lệnh thường dùng:

```sql
-- Liệt kê các cột và kiểu dữ liệu cơ bản.
DESCRIBE shop.order_items;

-- Hiển thị thêm collation, comment và thông tin đầy đủ hơn.
SHOW FULL COLUMNS FROM shop.order_items;

-- Xem toàn bộ DDL mà MySQL lưu cho bảng.
SHOW CREATE TABLE shop.order_items\G

-- Xem các chỉ mục.
SHOW INDEX FROM shop.order_items;
```

`DESCRIBE` (hoặc `DESC`) phù hợp để xem nhanh tên cột, kiểu, `NULL`, khóa, default và `Extra`. `SHOW FULL COLUMNS` bổ sung thông tin như collation, privileges và comment. `SHOW CREATE TABLE` thường là cách rõ nhất để kiểm tra DDL thực tế, bao gồm constraint, generated expression, engine, charset và các tùy chọn bảng.

Đừng nhầm `COLUMN_KEY` hoặc cột `Key` trong kết quả `DESCRIBE` với toàn bộ constraint. Những trường này chủ yếu tóm tắt vai trò chỉ mục của cột; để xem đầy đủ khóa ghép, khóa ngoại và CHECK constraint, hãy đọc DDL hoặc các view metadata tương ứng.

## 3. Tra cứu cột bằng INFORMATION_SCHEMA.COLUMNS

`INFORMATION_SCHEMA.COLUMNS` chứa một hàng cho mỗi cột trong các bảng và view mà tài khoản hiện tại có thể nhìn thấy.

### 3.1. Liệt kê cột của một bảng

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ORDINAL_POSITION,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_KEY,
    EXTRA,
    GENERATION_EXPRESSION,
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'order_items'
ORDER BY ORDINAL_POSITION;
```

Các cột metadata quan trọng:

| Trường | Ý nghĩa |
|---|---|
| `TABLE_SCHEMA`, `TABLE_NAME` | Schema và bảng chứa cột |
| `ORDINAL_POSITION` | Vị trí cột trong định nghĩa bảng, bắt đầu từ 1 |
| `COLUMN_NAME` | Tên cột |
| `DATA_TYPE` | Kiểu dữ liệu cơ sở, ví dụ `int`, `varchar`, `decimal` |
| `COLUMN_TYPE` | Kiểu đầy đủ hơn, có thể gồm độ dài, unsigned hoặc enum values |
| `IS_NULLABLE` | `YES` nếu cho phép NULL, `NO` nếu không |
| `COLUMN_DEFAULT` | Giá trị mặc định được metadata hiển thị; có thể là `NULL` |
| `COLUMN_KEY` | Tóm tắt vai trò khóa/chỉ mục như `PRI`, `UNI`, `MUL` |
| `EXTRA` | Thuộc tính bổ sung như `auto_increment`, `on update`, `VIRTUAL GENERATED` hoặc `STORED GENERATED` |
| `GENERATION_EXPRESSION` | Biểu thức dùng để tính generated column; rỗng với cột thường |
| `COLUMN_COMMENT` | Comment của cột |

`COLUMN_TYPE` hữu ích hơn `DATA_TYPE` khi cần biết `BIGINT UNSIGNED`, `DECIMAL(12,2)` hoặc danh sách giá trị của `ENUM`. Với cột chuỗi, xem thêm `CHARACTER_MAXIMUM_LENGTH`, `CHARACTER_SET_NAME` và `COLLATION_NAME`; với kiểu số/ngày giờ, xem `NUMERIC_PRECISION`, `NUMERIC_SCALE` và `DATETIME_PRECISION`.

### 3.2. Tìm một cột trong toàn schema

Ví dụ tìm các cột có tên chứa `price` trong schema `shop`:

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND COLUMN_NAME LIKE '%price%'
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

Truy vấn này hữu ích khi cần tìm nơi lưu giá tiền hoặc xác định một thay đổi có ảnh hưởng đến những bảng nào. Hãy lọc `TABLE_SCHEMA` để tránh trộn metadata từ các schema khác nhau.

### 3.3. Quyền xem metadata

Các view metadata chỉ hiển thị những đối tượng mà tài khoản có quyền nhìn thấy theo quy tắc của MySQL. Nếu một bảng không xuất hiện trong kết quả, có thể tên schema/bảng sai hoặc tài khoản không có quyền xem đối tượng đó. Khi điều tra production, dùng tài khoản đọc metadata được cấp quyền phù hợp thay vì mặc định dùng `root`.

## 4. Tra cứu giá trị mặc định

Giá trị mặc định (default value) được dùng khi câu lệnh `INSERT` không cung cấp giá trị cho cột, hoặc khi câu lệnh yêu cầu rõ `DEFAULT`. Nó giúp quy định trạng thái ban đầu của một hàng.

Ví dụ:

```sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    status VARCHAR(20) NOT NULL DEFAULT 'NEW',
    note VARCHAR(500) NULL DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Trong ví dụ:

- `status` nhận `'NEW'` nếu `INSERT` bỏ qua cột này.
- `note` cho phép `NULL` và có default tường minh là `NULL`.
- `created_at` được gán thời điểm tạo hàng nếu không cung cấp giá trị.
- `updated_at` được khởi tạo bằng thời điểm hiện tại và tự cập nhật theo quy tắc `ON UPDATE CURRENT_TIMESTAMP` khi hàng thay đổi theo điều kiện của MySQL.
- `id` được cấp giá trị tự tăng.

### 4.1. Phân biệt bỏ qua cột, DEFAULT và NULL

Ba cách viết sau không hoàn toàn giống nhau:

```sql
-- Bỏ cột status: MySQL dùng default của cột.
INSERT INTO orders (note) VALUES ('Gọi trước khi giao');

-- Yêu cầu rõ ràng dùng default.
INSERT INTO orders (status, note) VALUES (DEFAULT, 'Giao giờ hành chính');

-- Gán NULL tường minh: không dùng default.
INSERT INTO orders (status, note) VALUES ('NEW', NULL);
```

Nếu cột cho phép `NULL`, giá trị `NULL` được lưu như một giá trị rỗng theo ngữ nghĩa SQL. Nếu cột `NOT NULL`, truyền `NULL` thường gây lỗi. Giá trị default chỉ được dùng khi cột bị bỏ qua hoặc được chỉ định là `DEFAULT`.

Nếu cột `NOT NULL` không khai báo default và bị bỏ qua khi `INSERT`, kết quả còn phụ thuộc SQL mode. Trong strict mode, MySQL thường từ chối giá trị thiếu; trong chế độ không strict, MySQL có thể dùng implicit default theo kiểu dữ liệu và phát warning. Không dựa vào hành vi không strict để che thiếu sót của ứng dụng.

Kiểm tra SQL mode:

```sql
SELECT @@SESSION.sql_mode, @@GLOBAL.sql_mode;
```

### 4.2. Đọc default từ metadata

```sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
```

Lưu ý quan trọng: `COLUMN_DEFAULT` có thể là `NULL` khi cột được khai báo `DEFAULT NULL`, và cũng có thể là `NULL` khi không có mệnh đề `DEFAULT`. Vì vậy, chỉ nhìn `COLUMN_DEFAULT` chưa đủ để phân biệt hai trường hợp này. Hãy kiểm tra `SHOW CREATE TABLE` để xác nhận DDL gốc.

Với default là biểu thức hoặc hàm, cách biểu diễn trong metadata có thể khác theo phiên bản. `SHOW CREATE TABLE` là nguồn nên đối chiếu khi cần biết chính xác biểu thức, ví dụ default theo thời gian hoặc default expression được hỗ trợ ở phiên bản MySQL cụ thể.

### 4.3. Phân biệt DEFAULT với ON UPDATE

`DEFAULT CURRENT_TIMESTAMP` xác định giá trị ban đầu khi tạo hàng. `ON UPDATE CURRENT_TIMESTAMP` quy định tự cập nhật cột thời gian khi hàng thay đổi và thỏa điều kiện của MySQL. Đây là hai hành vi khác nhau; xem `EXTRA` trong metadata và DDL trong `SHOW CREATE TABLE` để nhận diện đầy đủ.

## 5. Tra cứu ràng buộc của bảng

Constraint là quy tắc được khai báo để bảo vệ tính hợp lệ và quan hệ của dữ liệu. MySQL thường dùng các loại sau:

| Loại | Mục đích | Ví dụ |
|---|---|---|
| `PRIMARY KEY` | Định danh duy nhất mỗi hàng và không cho phép NULL | `PRIMARY KEY (id)` |
| `UNIQUE` | Không cho phép giá trị khóa trùng nhau | `UNIQUE KEY uq_email (email)` |
| `FOREIGN KEY` | Bảo vệ quan hệ tham chiếu giữa bảng con và bảng cha | `FOREIGN KEY (product_id) REFERENCES products(id)` |
| `CHECK` | Kiểm tra biểu thức điều kiện trên hàng | `CHECK (quantity > 0)` |
| `NOT NULL` | Không cho phép cột nhận NULL | `quantity INT NOT NULL` |

`NOT NULL` được khai báo như thuộc tính cột và tra qua `IS_NULLABLE`; không phải lúc nào cũng xuất hiện như một hàng riêng trong `INFORMATION_SCHEMA.TABLE_CONSTRAINTS`. Default value cũng là thuộc tính cột, không phải constraint.

### 5.1. Liệt kê constraint bằng TABLE_CONSTRAINTS

```sql
SELECT
    CONSTRAINT_SCHEMA,
    TABLE_NAME,
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'order_items'
ORDER BY CONSTRAINT_TYPE, CONSTRAINT_NAME;
```

`CONSTRAINT_TYPE` thường trả về `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY` hoặc `CHECK`. Kết quả cho biết loại và tên constraint, nhưng để biết cột nào tham gia và thứ tự cột trong khóa ghép, cần kết hợp `KEY_COLUMN_USAGE`.

### 5.2. Tra cứu cột tham gia khóa và foreign key

```sql
SELECT
    CONSTRAINT_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION,
    REFERENCED_TABLE_SCHEMA,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'order_items'
ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION;
```

Với khóa ghép, `ORDINAL_POSITION` thể hiện thứ tự cột trong constraint. Các trường `REFERENCED_...` có giá trị đối với foreign key; chúng cho biết schema, bảng và cột được tham chiếu.

### 5.3. Tra cứu hành vi ON DELETE và ON UPDATE

```sql
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    REFERENCED_TABLE_NAME,
    UPDATE_RULE,
    DELETE_RULE
FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = 'shop'
  AND TABLE_NAME = 'order_items';
```

Các quy tắc thường gặp gồm `RESTRICT`, `CASCADE`, `SET NULL` và `NO ACTION`. Cần kiểm tra cả định nghĩa cột: `SET NULL` chỉ phù hợp khi cột khóa ngoại cho phép NULL. Không nên chọn `CASCADE` chỉ để tránh lỗi xóa; hãy xác định rõ vòng đời dữ liệu cha-con theo nghiệp vụ.

### 5.4. Tra cứu CHECK constraint

Với MySQL 8.0.16 trở lên, CHECK constraint được thực thi. Có thể đọc biểu thức bằng `INFORMATION_SCHEMA.CHECK_CONSTRAINTS`:

```sql
SELECT
    tc.TABLE_NAME,
    tc.CONSTRAINT_NAME,
    cc.CHECK_CLAUSE
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc
  ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
 AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
WHERE tc.TABLE_SCHEMA = 'shop'
  AND tc.TABLE_NAME = 'order_items'
  AND tc.CONSTRAINT_TYPE = 'CHECK';
```

Ở các phiên bản MySQL cũ hơn 8.0.16, cú pháp CHECK có thể được parser chấp nhận nhưng constraint không được thực thi như ở các phiên bản mới. Khi nâng cấp hoặc điều tra một schema cũ, hãy xác nhận phiên bản server và kiểm tra DDL thực tế; không giả định một CHECK constraint được viết trong file migration đồng nghĩa server đang enforce nó.

## 6. Generated column là gì?

Generated column là cột có giá trị được MySQL tính từ một biểu thức dựa trên các cột khác trong cùng hàng. Ứng dụng không trực tiếp quyết định giá trị của cột này khi `INSERT` hoặc `UPDATE`; MySQL tính theo biểu thức đã khai báo.

Ví dụ, mỗi dòng đơn hàng có số lượng và đơn giá. Tổng tiền dòng có thể được tính tự động:

```sql
CREATE TABLE order_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    line_total DECIMAL(20,2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_order_id (order_id),
    CHECK (quantity > 0),
    CHECK (unit_price >= 0)
) ENGINE=InnoDB;
```

Trong ví dụ, `line_total` được tính từ `quantity * unit_price`. Khi thêm hàng, ứng dụng chỉ cần truyền số lượng và đơn giá:

```sql
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES (9001, 42, 2, 125000.00);

SELECT quantity, unit_price, line_total
FROM order_items
WHERE order_id = 9001;
```

Giá trị `line_total` được MySQL tính. Không truyền một giá trị tùy ý vào generated column; trong các câu lệnh ghi, cột generated chỉ có thể được chỉ định `DEFAULT` theo cú pháp MySQL.

### 6.1. VIRTUAL và STORED

MySQL hỗ trợ hai kiểu generated column:

| Kiểu | Cách lưu | Đặc điểm |
|---|---|---|
| `VIRTUAL` | Không lưu giá trị trong phần dữ liệu hàng; biểu thức được tính khi cần đọc giá trị | Tiết kiệm dung lượng hàng, nhưng việc đọc có thể cần tính biểu thức |
| `STORED` | Giá trị được tính khi ghi/cập nhật hàng và lưu trong bảng | Tốn dung lượng lưu trữ hơn, nhưng đọc giá trị không cần tính lại biểu thức từ các cột nguồn |

Nếu không chỉ rõ loại, generated column mặc định là `VIRTUAL`. Cả hai kiểu đều có thể được lập chỉ mục trong các trường hợp MySQL hỗ trợ. Với InnoDB, secondary index trên virtual generated column lưu giá trị index đã tính, nên index có chi phí lưu trữ và cập nhật dù giá trị không được lưu trong phần dữ liệu hàng.

### 6.2. Khi nào nên dùng generated column?

- Khi giá trị luôn được suy ra từ dữ liệu cùng hàng và không nên bị ứng dụng ghi lệch.
- Khi muốn đặt tên cho biểu thức tính toán để truy vấn dễ đọc hơn.
- Khi muốn lập chỉ mục cho một biểu thức phù hợp thay vì lặp lại biểu thức ở nhiều truy vấn.
- Khi cần chuẩn hóa một phần dữ liệu, ví dụ lấy domain từ email hoặc tạo khóa tìm kiếm từ cột gốc, nếu biểu thức được hỗ trợ và có tính xác định.

Generated column không thay thế cột lưu dữ liệu nghiệp vụ do người dùng nhập. Nếu giá trị cần giữ lại tại thời điểm giao dịch dù các cột nguồn có thể thay đổi sau này, hãy lưu snapshot vào một cột thường thay vì tính lại tự động.

### 6.3. Giới hạn biểu thức

Biểu thức generated column phải tuân theo các giới hạn của MySQL. Nó thường chỉ được tham chiếu cột của cùng hàng và không được dùng subquery, biến hoặc hàm không xác định mà MySQL cấm trong generated expression. Không thể dùng generated column để đọc một bảng khác hoặc gọi một dịch vụ bên ngoài.

Nếu một biểu thức phụ thuộc thời gian hiện tại như `NOW()` hoặc phụ thuộc dữ liệu ngoài hàng, đó thường không phải biểu thức phù hợp cho generated column. Hãy dùng cột thường được ứng dụng cập nhật hoặc một quy trình tổng hợp riêng.

## 7. Tra cứu generated column trong metadata

### 7.1. Tìm tất cả generated column trong schema

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_TYPE,
    EXTRA,
    GENERATION_EXPRESSION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND GENERATION_EXPRESSION <> ''
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

`GENERATION_EXPRESSION` cho biết biểu thức tính. `EXTRA` thường thể hiện `VIRTUAL GENERATED` hoặc `STORED GENERATED`. Hãy kiểm tra `SHOW CREATE TABLE` để xem đầy đủ kiểu, nullability, index và các thuộc tính khác.

### 7.2. Xem định nghĩa của một generated column

```sql
SHOW CREATE TABLE shop.order_items\G
```

Đầu ra có thể chứa định nghĩa tương tự:

```sql
`line_total` decimal(20,2)
  GENERATED ALWAYS AS ((`quantity` * `unit_price`)) STORED
```

Đây là cách xác minh biểu thức và kiểu lưu trữ. Metadata `EXTRA` chỉ cho biết trạng thái bổ sung; không đủ để tái tạo biểu thức.

### 7.3. Kiểm tra index trên generated column

```sql
SHOW INDEX FROM shop.order_items;
```

Đối chiếu `Column_name`, `Key_name` và thứ tự cột trong index. Nếu truy vấn lọc theo generated column nhưng không có index phù hợp, MySQL có thể phải tính biểu thức cho nhiều hàng. Tuy nhiên, thêm index cũng làm tăng chi phí ghi và dung lượng; hãy kiểm tra kế hoạch thực thi trước khi quyết định.

## 8. Một quy trình tra cứu metadata hoàn chỉnh

Giả sử bạn nhận một ứng dụng cũ và cần biết vì sao cột `line_total` không thể được cập nhật trực tiếp, đồng thời muốn xác minh `status` có default hay không.

1. **Xác nhận đúng schema và bảng:** kiểm tra `DATABASE()` và dùng tên schema tường minh trong các lệnh.
2. **Xem DDL đầy đủ:** chạy `SHOW CREATE TABLE shop.order_items` để biết constraint, default, generated expression và engine.
3. **Liệt kê metadata cột:** truy vấn `INFORMATION_SCHEMA.COLUMNS` để xem kiểu, nullability, default, `EXTRA` và generation expression.
4. **Xác định constraint:** truy vấn `TABLE_CONSTRAINTS` và `KEY_COLUMN_USAGE`; với CHECK, xem `CHECK_CONSTRAINTS` nếu phiên bản hỗ trợ.
5. **Đối chiếu chỉ mục:** dùng `SHOW INDEX` để biết cột nào đang được index và thứ tự trong index ghép.
6. **Kiểm tra hành vi thực tế:** thử `INSERT`/`UPDATE` trên môi trường phát triển và xem lỗi hoặc warning; không thử ghi tùy tiện lên production.
7. **Ghi kết quả vào migration/tài liệu:** ghi rõ giả định phiên bản, constraint và thay đổi dự kiến để lần sau có thể kiểm tra lại.

Ví dụ truy vấn tổng hợp một số metadata cột quan trọng:

```sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_KEY,
    EXTRA,
    GENERATION_EXPRESSION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'order_items'
ORDER BY ORDINAL_POSITION;
```

Sau đó dùng `SHOW CREATE TABLE` làm bằng chứng cuối cùng về DDL đang có trên server. Nếu file migration trong Git khác kết quả trên server, cần điều tra lịch sử triển khai và schema drift trước khi chạy migration tiếp theo.

## 9. Những sai lầm thường gặp

- **Chỉ dùng DESCRIBE để kết luận toàn bộ cấu trúc:** lệnh này tiện xem nhanh nhưng không thay thế `SHOW CREATE TABLE` và các view constraint.
- **Coi `COLUMN_DEFAULT IS NULL` là chắc chắn không có default:** metadata có thể trả NULL cho cả trường hợp `DEFAULT NULL` và không có mệnh đề default.
- **Nhầm `COLUMN_KEY` với danh sách đầy đủ constraint:** hãy dùng `TABLE_CONSTRAINTS`, `KEY_COLUMN_USAGE` và `SHOW CREATE TABLE`.
- **Coi mọi CHECK đều được thực thi:** MySQL trước 8.0.16 không enforce CHECK như các phiên bản mới.
- **Ghi giá trị trực tiếp vào generated column:** giá trị phải được tính theo biểu thức; ứng dụng nên ghi các cột nguồn.
- **Cho rằng VIRTUAL không bao giờ tốn dung lượng index:** secondary index trên virtual generated column vẫn cần lưu khóa index.
- **Không kiểm tra quyền metadata:** thiếu đối tượng trong kết quả có thể do tài khoản không có quyền nhìn thấy.
- **Sửa metadata nội bộ:** data dictionary phải được quản lý qua DDL và giao diện SQL hỗ trợ, không sửa các cấu trúc hệ thống bằng tay.

## 10. Checklist kiểm tra cột và constraint

- Tôi đã xác nhận đúng `TABLE_SCHEMA` và `TABLE_NAME` chưa?
- Tôi đã xem `SHOW CREATE TABLE` để biết DDL thực tế chưa?
- Kiểu dữ liệu đầy đủ, nullability, charset và collation có đúng yêu cầu không?
- Cột có default hay không? `COLUMN_DEFAULT` có cần đối chiếu vì giá trị NULL mơ hồ không?
- `DEFAULT` và `ON UPDATE` có bị nhầm lẫn không?
- Constraint nào đang tồn tại, các cột tham gia và thứ tự của khóa ghép là gì?
- Foreign key tham chiếu đến bảng/cột nào và dùng quy tắc xóa/cập nhật nào?
- CHECK constraint có được phiên bản MySQL hiện tại thực thi không?
- Generated column là VIRTUAL hay STORED, biểu thức là gì và có index không?
- Tài khoản hiện tại có đủ quyền nhìn thấy metadata cần tra cứu không?

## Kết luận

`DESCRIBE`, `SHOW FULL COLUMNS` và `SHOW CREATE TABLE` giúp khám phá cấu trúc nhanh; `INFORMATION_SCHEMA.COLUMNS` cung cấp metadata chi tiết về kiểu, nullability, default và generated expression; các view `TABLE_CONSTRAINTS`, `KEY_COLUMN_USAGE`, `REFERENTIAL_CONSTRAINTS` và `CHECK_CONSTRAINTS` giúp tra cứu ràng buộc. Khi phân tích schema, hãy kết hợp các nguồn này, chú ý khác biệt phiên bản và quyền metadata, đồng thời dùng DDL thực tế để xác minh. Hiểu đúng default, constraint và generated column giúp thiết kế dữ liệu nhất quán, viết migration an toàn và tránh cập nhật sai cấu trúc MySQL.
