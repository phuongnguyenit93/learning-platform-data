# INSERT một dòng, nhiều dòng và INSERT từ SELECT

Khi một ứng dụng tiếp nhận khách hàng mới, nhập danh sách sản phẩm hoặc tổng hợp dữ liệu đơn hàng sang bảng báo cáo, nó cần ghi dữ liệu vào MySQL theo cách đúng cấu trúc và có thể kiểm soát lỗi. MySQL cung cấp nhiều dạng `INSERT`: chèn một dòng bằng `VALUES`, chèn nhiều dòng trong cùng câu lệnh và chèn trực tiếp kết quả truy vấn bằng `INSERT ... SELECT`.

Chọn đúng dạng `INSERT` giúp giảm số lần round-trip đến server, giữ được tính nhất quán giữa các bảng và tránh ghi dữ liệu thiếu hoặc sai. Cần xác định rõ danh sách cột, giá trị mặc định, ràng buộc, khóa duy nhất, transaction và cách xử lý khi dữ liệu nguồn trùng lặp.

## 1. INSERT ghi dữ liệu vào bảng như thế nào?

`INSERT` thêm một hoặc nhiều hàng vào bảng. Cú pháp phổ biến:

```sql
INSERT INTO table_name (column_1, column_2, ...)
VALUES (value_1, value_2, ...);
```

Danh sách cột xác định vị trí và ý nghĩa của từng giá trị. Số lượng giá trị trong mỗi tuple phải khớp với số cột được liệt kê; thứ tự giá trị phải tương ứng thứ tự cột.

Ví dụ bảng khách hàng:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    note VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB;
```

Thêm một khách hàng:

```sql
INSERT INTO customers (email, full_name)
VALUES ('an@example.com', 'Nguyễn Văn An');
```

MySQL tự sinh `id`, dùng mặc định `ACTIVE` cho `status`, gán `NULL` cho `note` và dùng thời điểm hiện tại cho `created_at`.

### 1.1. Luôn liệt kê tên cột

Nên viết:

```sql
INSERT INTO customers (email, full_name, status)
VALUES ('binh@example.com', 'Trần Minh Bình', 'ACTIVE');
```

Hạn chế viết:

```sql
INSERT INTO customers
VALUES (NULL, 'binh@example.com', 'Trần Minh Bình', 'ACTIVE', NULL, DEFAULT);
```

Câu lệnh không có danh sách cột phụ thuộc thứ tự tất cả cột trong bảng. Khi schema thêm hoặc đổi cột, câu lệnh cũ có thể lỗi hoặc ghi nhầm dữ liệu. Liệt kê cột giúp SQL rõ ràng và ít phụ thuộc cấu trúc vật lý hơn.

### 1.2. Bỏ qua cột để dùng DEFAULT

Nếu không đưa một cột vào danh sách, MySQL dùng giá trị mặc định của cột đó nếu có. Ví dụ trên bỏ qua `status`, `note` và `created_at`.

Có thể chỉ định rõ `DEFAULT`:

```sql
INSERT INTO customers (email, full_name, status, note)
VALUES ('chi@example.com', 'Lê Thu Chi', DEFAULT, NULL);
```

`DEFAULT` yêu cầu MySQL dùng default được định nghĩa cho cột. `NULL` là giá trị NULL thực sự; nó không có nghĩa là dùng default.

Phân biệt:

| Cách ghi | Ý nghĩa |
|---|---|
| Bỏ cột khỏi danh sách INSERT | Dùng default của cột nếu có; nếu không, hành vi phụ thuộc nullability và SQL mode |
| Ghi `DEFAULT` | Yêu cầu dùng default của cột |
| Ghi `NULL` | Ghi SQL NULL nếu cột cho phép |
| Ghi `''` | Ghi chuỗi rỗng, khác NULL |

Trong chế độ strict, bỏ qua cột `NOT NULL` không có default thường khiến câu lệnh lỗi. Trong chế độ không strict, MySQL có thể dùng implicit default và phát cảnh báo; không nên dựa vào hành vi này cho dữ liệu nghiệp vụ.

### 1.3. Chèn một hàng chỉ với giá trị mặc định

Nếu mọi cột đều có thể nhận default hoặc được tự sinh, có thể viết:

```sql
INSERT INTO customers () VALUES ();
```

Câu lệnh tạo một hàng bằng các giá trị mặc định. Với schema ví dụ, cột `id` tự tăng, `status` nhận `ACTIVE`, `note` nhận NULL và `created_at` nhận thời điểm hiện tại; nhưng `email` và `full_name` là `NOT NULL` không có default nên câu lệnh này sẽ thất bại trong cấu hình strict thông thường. Ví dụ này minh họa cú pháp, không phải dữ liệu hợp lệ cho bảng `customers`.

### 1.4. Cú pháp INSERT ... SET của MySQL

MySQL còn hỗ trợ dạng mở rộng:

```sql
INSERT INTO customers
SET email = 'dung@example.com',
    full_name = 'Phạm Quốc Dũng',
    status = DEFAULT;
```

Dạng `INSERT ... SET` gán từng cột bằng tên, thuận tiện khi câu lệnh có ít cột hoặc được tạo từ các cặp tên/giá trị. Đây là cú pháp riêng của MySQL; `INSERT ... (columns) VALUES (...)` phổ biến và dễ chuyển đổi giữa các hệ quản trị hơn.

## 2. Giá trị AUTO_INCREMENT và ID vừa tạo

Với cột `AUTO_INCREMENT`, có thể bỏ cột ID khỏi danh sách INSERT để MySQL tự cấp:

```sql
INSERT INTO customers (email, full_name)
VALUES ('hoa@example.com', 'Nguyễn Thu Hoa');

SELECT LAST_INSERT_ID() AS customer_id;
```

`LAST_INSERT_ID()` trả ID tự tăng được tạo gần nhất trên connection hiện tại. Câu SELECT phải chạy trên cùng connection vật lý với câu INSERT. Không dùng `SELECT MAX(id)` để lấy ID vừa tạo vì một connection khác có thể insert xen giữa.

Với một câu INSERT nhiều hàng, `LAST_INSERT_ID()` trả ID tự tăng đầu tiên được tạo bởi câu lệnh đó, không trả toàn bộ danh sách ID. Không giả định các ID tiếp theo liên tục; rollback, insert lỗi, concurrency và cấu hình auto increment có thể tạo khoảng trống.

Trong Java JDBC, ưu tiên API generated keys của statement:

```java
String sql = "INSERT INTO customers (email, full_name) VALUES (?, ?)";

try (PreparedStatement statement = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {
    statement.setString(1, email);
    statement.setString(2, fullName);
    statement.executeUpdate();

    try (ResultSet keys = statement.getGeneratedKeys()) {
        if (keys.next()) {
            long customerId = keys.getLong(1);
        }
    }
}
```

Kiểm tra kết quả statement và xử lý trường hợp driver không trả generated key. Nếu transaction rollback, ID đã nhận không chứng minh hàng còn tồn tại.

### 2.1. Chèn giá trị AUTO_INCREMENT tường minh

MySQL cho phép cung cấp giá trị rõ ràng cho cột `AUTO_INCREMENT`:

```sql
INSERT INTO customers (id, email, full_name)
VALUES (5000, 'imported@example.com', 'Khách hàng nhập dữ liệu');
```

Chỉ làm điều này khi có lý do như phục hồi hoặc đồng bộ ID từ nguồn chuẩn. Giá trị explicit có thể ảnh hưởng giá trị tự tăng tiếp theo. Giá trị `0` thường được xử lý như yêu cầu cấp ID mới; nếu bật SQL mode `NO_AUTO_VALUE_ON_ZERO`, `0` được lưu như giá trị tường minh. Giá trị `NULL` trong cột AUTO_INCREMENT thường yêu cầu MySQL cấp giá trị mới.

## 3. INSERT nhiều dòng bằng một câu lệnh

Khi có nhiều hàng cùng cấu trúc, dùng một câu lệnh với nhiều tuple:

```sql
INSERT INTO customers (email, full_name, status)
VALUES
    ('lan@example.com', 'Vũ Ngọc Lan', 'ACTIVE'),
    ('minh@example.com', 'Đỗ Quang Minh', 'ACTIVE'),
    ('nam@example.com', 'Phan Hoàng Nam', 'PENDING');
```

Mỗi tuple phải có đúng số giá trị và cùng thứ tự cột. Câu lệnh này thường giảm số lần client gửi request đến server so với chạy ba câu INSERT riêng.

### 3.1. Lợi ích của multi-row INSERT

- Giảm round-trip giữa ứng dụng và MySQL.
- Giảm chi phí phân tích và thực thi lặp lại câu lệnh.
- Dễ gom một lô dữ liệu thành một đơn vị ghi.
- Có thể tăng thông lượng khi nạp dữ liệu vừa phải.

Tuy nhiên, một batch quá lớn có thể làm câu SQL rất dài, tiêu thụ bộ nhớ, tạo transaction lớn và tăng thời gian giữ lock. Hãy chọn kích thước batch theo kích thước hàng, giới hạn packet, latency, tài nguyên và khả năng rollback.

### 3.2. Mỗi tuple phải khớp danh sách cột

Ví dụ sai:

```sql
-- SAI: tuple thứ hai thiếu một giá trị.
INSERT INTO customers (email, full_name, status)
VALUES
    ('one@example.com', 'Người thứ nhất', 'ACTIVE'),
    ('two@example.com', 'Người thứ hai');
```

MySQL báo lỗi vì các tuple không có cùng số giá trị. Cũng cần bảo đảm thứ tự cột nhất quán; đảo `email` và `full_name` có thể tạo lỗi kiểu dữ liệu hoặc ghi sai nội dung.

### 3.3. Dùng DEFAULT riêng cho từng hàng

```sql
INSERT INTO customers (email, full_name, status, note)
VALUES
    ('one@example.com', 'Người thứ nhất', DEFAULT, NULL),
    ('two@example.com', 'Người thứ hai', 'PENDING', 'Chờ xác minh'),
    ('three@example.com', 'Người thứ ba', DEFAULT, 'Đăng ký tại cửa hàng');
```

Mỗi tuple có thể cung cấp giá trị khác nhau hoặc dùng `DEFAULT` cho một cột. Danh sách cột vẫn phải giống nhau giữa mọi tuple.

## 4. INSERT từ SELECT

`INSERT ... SELECT` chèn kết quả của một truy vấn vào bảng đích mà không cần ứng dụng đọc dữ liệu về rồi gửi lại từng hàng.

Cú pháp:

```sql
INSERT INTO target_table (target_col_1, target_col_2, ...)
SELECT source_expr_1, source_expr_2, ...
FROM source_table
WHERE condition;
```

Số cột và biểu thức trong SELECT phải tương ứng danh sách cột đích. Thứ tự rất quan trọng: biểu thức thứ nhất đi vào cột đích thứ nhất, biểu thức thứ hai đi vào cột thứ hai, v.v.

### 4.1. Sao chép dữ liệu có chọn lọc

Giả sử có bảng lưu khách hàng đã ngừng hoạt động:

```sql
CREATE TABLE inactive_customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    archived_at DATETIME NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;
```

Chèn khách hàng inactive từ bảng chính:

```sql
INSERT INTO inactive_customers (
    customer_id,
    email,
    full_name,
    archived_at
)
SELECT
    c.id,
    c.email,
    c.full_name,
    CURRENT_TIMESTAMP
FROM customers AS c
WHERE c.status = 'INACTIVE';
```

MySQL đọc các hàng thỏa điều kiện và chèn vào bảng đích. Nếu bảng đích có primary key hoặc unique key trùng, câu lệnh có thể lỗi trừ khi dùng chiến lược xử lý duplicate phù hợp.

### 4.2. Tổng hợp dữ liệu trước khi chèn

Có thể dùng JOIN, GROUP BY và biểu thức trong SELECT để tạo dữ liệu báo cáo:

```sql
CREATE TABLE customer_order_summary (
    customer_id BIGINT UNSIGNED NOT NULL,
    order_count BIGINT NOT NULL,
    total_amount DECIMAL(18,2) NOT NULL,
    calculated_at DATETIME NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;
```

Chèn kết quả tổng hợp:

```sql
INSERT INTO customer_order_summary (
    customer_id,
    order_count,
    total_amount,
    calculated_at
)
SELECT
    o.customer_id,
    COUNT(DISTINCT o.id),
    SUM(oi.quantity * oi.unit_price),
    CURRENT_TIMESTAMP
FROM orders AS o
INNER JOIN order_items AS oi
    ON oi.order_id = o.id
WHERE o.status = 'PAID'
GROUP BY o.customer_id;
```

Truy vấn tính tổng tiền theo khách hàng từ các đơn đã thanh toán. Vì mỗi đơn có nhiều dòng chi tiết, `COUNT(DISTINCT o.id)` đếm đơn duy nhất, còn `SUM` cộng tiền ở mức dòng chi tiết. Nếu nối thêm bảng một-nhiều khác, phải xem xét fan-out để tránh nhân tổng.

### 4.3. Chỉ chèn những hàng chưa tồn tại

Có thể lọc nguồn bằng `NOT EXISTS`:

```sql
INSERT INTO inactive_customers (
    customer_id,
    email,
    full_name,
    archived_at
)
SELECT
    c.id,
    c.email,
    c.full_name,
    CURRENT_TIMESTAMP
FROM customers AS c
WHERE c.status = 'INACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM inactive_customers AS a
      WHERE a.customer_id = c.id
  );
```

`NOT EXISTS` tránh chọn những khách hàng đã có trong bảng đích ở thời điểm truy vấn đọc. Tuy nhiên, hai job đồng thời vẫn có thể cùng thấy một ID chưa tồn tại rồi cùng cố insert. Primary key/unique key trên bảng đích vẫn là lớp bảo vệ cuối cùng; nếu cần chạy đồng thời an toàn, hãy thiết kế chiến lược duplicate/idempotency phù hợp.

### 4.4. INSERT ... SELECT từ cùng bảng

MySQL có thể đọc dữ liệu từ một bảng rồi chèn vào chính bảng đó nếu câu lệnh và cấu trúc phù hợp. Cần cẩn thận để tránh chọn lại các hàng vừa chèn hoặc tạo bản sao không giới hạn. Luôn có điều kiện xác định tập nguồn, ràng buộc unique phù hợp và thử trên dữ liệu nhỏ trước khi chạy batch lớn.

## 5. Chọn chiến lược khi gặp dữ liệu trùng

Khi insert một hàng có khóa chính hoặc unique key đã tồn tại, MySQL thường trả lỗi duplicate key. Có ba lựa chọn phổ biến, mỗi lựa chọn có ngữ nghĩa khác nhau.

### 5.1. Để lỗi duplicate xuất hiện

Đây thường là lựa chọn tốt khi trùng lặp là lỗi nghiệp vụ:

```sql
INSERT INTO customers (email, full_name)
VALUES ('an@example.com', 'Tên khác');
```

Nếu email đã tồn tại theo unique index, MySQL từ chối insert. Ứng dụng có thể trả thông báo “email đã được sử dụng” hoặc thực hiện quy trình nghiệp vụ riêng.

### 5.2. INSERT IGNORE

`INSERT IGNORE` yêu cầu MySQL bỏ qua một số lỗi có thể chuyển thành warning, trong đó có duplicate key:

```sql
INSERT IGNORE INTO customers (email, full_name)
VALUES
    ('existing@example.com', 'Không ghi đè tên cũ'),
    ('new@example.com', 'Khách hàng mới');
```

Hàng bị trùng có thể bị bỏ qua, hàng hợp lệ khác vẫn được chèn. Nhưng `IGNORE` có phạm vi rộng hơn duplicate key: một số lỗi dữ liệu như chuyển đổi hoặc giá trị ngoài miền có thể bị hạ thành warning và dữ liệu được điều chỉnh theo quy tắc MySQL. Vì vậy, không dùng `IGNORE` chỉ để “cho câu lệnh chạy qua” mà không kiểm tra cảnh báo.

Ngay sau câu lệnh, kiểm tra:

```sql
SHOW WARNINGS;
```

`SHOW WARNINGS` phản ánh warning của câu lệnh gần nhất trên cùng session; hãy chạy ngay sau INSERT trước khi câu lệnh khác thay thế danh sách warning. Trong ứng dụng, kiểm tra affected rows, warning count và log dữ liệu bị bỏ qua.

### 5.3. INSERT ... ON DUPLICATE KEY UPDATE

Nếu trùng khóa có nghĩa là cần cập nhật hàng hiện có, dùng upsert:

```sql
CREATE TABLE product_inventory (
    product_id BIGINT UNSIGNED NOT NULL,
    warehouse_id BIGINT UNSIGNED NOT NULL,
    available_quantity INT NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (product_id, warehouse_id)
) ENGINE=InnoDB;
```

Chèn mới hoặc cập nhật số lượng:

```sql
INSERT INTO product_inventory (
    product_id,
    warehouse_id,
    available_quantity,
    updated_at
)
VALUES (42, 3, 100, CURRENT_TIMESTAMP) AS incoming
ON DUPLICATE KEY UPDATE
    available_quantity = incoming.available_quantity,
    updated_at = incoming.updated_at;
```

Cú pháp row alias sau `VALUES` được hỗ trợ từ MySQL 8.0.19. Alias `incoming` đại diện cho hàng đang được đề nghị insert; trong nhánh duplicate, có thể dùng nó để tham chiếu giá trị mới.

Trước MySQL 8.0.19, nhiều ví dụ dùng `VALUES(column_name)` trong phần update. Cách dùng hàm `VALUES()` này bị deprecated từ MySQL 8.0.20; với phiên bản mới, ưu tiên row alias.

`ON DUPLICATE KEY UPDATE` được kích hoạt khi insert xung đột với bất kỳ PRIMARY KEY hoặc UNIQUE index nào. Nếu bảng có nhiều unique key, cần hiểu xung đột có thể xảy ra ở khóa nào; không giả định chỉ có một khóa nghiệp vụ duy nhất.

### 5.4. Phân biệt IGNORE, UPSERT và REPLACE

| Cách viết | Khi gặp duplicate | Hành vi |
|---|---|---|
| `INSERT` | Báo lỗi | Không âm thầm bỏ qua dữ liệu trùng |
| `INSERT IGNORE` | Bỏ qua hàng/lỗi có thể chuyển thành warning | Không cập nhật hàng cũ; phải kiểm tra warnings |
| `INSERT ... ON DUPLICATE KEY UPDATE` | Chạy nhánh UPDATE | Giữ hàng hiện tại và cập nhật cột theo chỉ định |
| `REPLACE INTO` | Xóa hàng xung đột rồi insert hàng mới | Có thể tác động FK, trigger, auto increment và cột không được cung cấp |

`REPLACE` không đơn giản là một dạng UPSERT. Với hàng xung đột, MySQL thực hiện hành vi xóa rồi chèn; các foreign key `ON DELETE`, trigger và cột bị bỏ khỏi INSERT có thể tạo tác động khác hẳn UPDATE. Không dùng `REPLACE` thay cho `ON DUPLICATE KEY UPDATE` nếu muốn giữ nguyên danh tính và quan hệ của hàng hiện có.

## 6. Affected rows và warning khi INSERT

Sau INSERT, ứng dụng thường cần biết câu lệnh đã tác động bao nhiêu hàng. Với `INSERT ... ON DUPLICATE KEY UPDATE`, số hàng affected theo quy tắc MySQL thông thường:

- `1` nếu một hàng được insert mới.
- `2` nếu một hàng hiện có được cập nhật.
- `0` nếu hàng hiện có được gán lại các giá trị đang có.

Nếu client dùng cờ `CLIENT_FOUND_ROWS`, trường hợp không đổi có thể được báo là `1`. Vì vậy, không diễn giải affected rows như một bộ trạng thái nghiệp vụ độc lập mà không xét connector và flags.

Với multi-row INSERT, affected rows là tổng số hàng được xử lý theo quy tắc của câu lệnh; `INSERT IGNORE` và upsert có thể tạo số liệu khác với số tuple đầu vào. Nếu cần biết chi tiết hàng nào được chèn, bỏ qua hay cập nhật, hãy dùng khóa nghiệp vụ, kết quả driver và quy trình đối soát thay vì chỉ nhìn một con số.

## 7. INSERT và transaction

Với InnoDB, INSERT là thao tác transactional. Có thể gom nhiều thao tác ghi thành một transaction để bảo đảm tất cả cùng commit hoặc rollback:

```sql
START TRANSACTION;

INSERT INTO orders (customer_id, status, created_at)
VALUES (120, 'NEW', CURRENT_TIMESTAMP);

SET @order_id = LAST_INSERT_ID();

INSERT INTO order_items (
    order_id,
    line_no,
    product_id,
    warehouse_id,
    quantity,
    unit_price,
    created_at
)
VALUES
    (@order_id, 1, 42, 3, 2, 150000.00, CURRENT_TIMESTAMP),
    (@order_id, 2, 57, 3, 1,  80000.00, CURRENT_TIMESTAMP);

COMMIT;
```

Nếu một câu lệnh thất bại, ứng dụng có thể rollback toàn transaction:

```sql
ROLLBACK;
```

Trong ví dụ thực tế, nên dùng prepared statement và biến cục bộ của ứng dụng; `@order_id` ở đây chỉ minh họa giá trị session được giữ giữa các câu lệnh trên cùng connection. Phải kiểm tra lỗi của từng thao tác và chỉ commit khi tất cả bước cần thiết thành công.

### 7.1. INSERT ... SELECT trong transaction

Có thể chạy INSERT SELECT cùng các thao tác khác trong transaction InnoDB:

```sql
START TRANSACTION;

INSERT INTO inactive_customers (
    customer_id,
    email,
    full_name,
    archived_at
)
SELECT
    id,
    email,
    full_name,
    CURRENT_TIMESTAMP
FROM customers
WHERE status = 'INACTIVE';

-- Kiểm tra số hàng và điều kiện nghiệp vụ tại đây.

COMMIT;
```

Nếu câu lệnh hoặc kiểm tra sau đó không đạt, rollback để hủy thay đổi transactional. DDL và một số lệnh quản trị có implicit commit; không đặt chúng xen giữa với kỳ vọng rollback toàn bộ transaction.

### 7.2. Atomicity và storage engine

Tính rollback của ví dụ phụ thuộc storage engine transactional như InnoDB. Với engine không transactional, `ROLLBACK` không thể hoàn tác các thay đổi đã ghi. Đối với hệ thống nghiệp vụ cần tính toàn vẹn, nên dùng InnoDB cho các bảng liên quan và giữ các thao tác trong cùng transaction/connection.

## 8. Kiểm tra dữ liệu trước khi INSERT ... SELECT

Trước khi nạp một lượng lớn dữ liệu, chạy SELECT tương ứng để xem nguồn:

```sql
SELECT
    c.id,
    c.email,
    c.full_name
FROM customers AS c
WHERE c.status = 'INACTIVE'
ORDER BY c.id
LIMIT 100;
```

Kiểm tra số lượng:

```sql
SELECT COUNT(*) AS source_rows
FROM customers
WHERE status = 'INACTIVE';
```

Kiểm tra duplicate theo khóa đích:

```sql
SELECT c.id, COUNT(*) AS occurrences
FROM customers AS c
WHERE c.status = 'INACTIVE'
GROUP BY c.id
HAVING COUNT(*) > 1;
```

Nếu bảng đích có unique key khác, cần kiểm tra xung đột theo từng unique key đó. Việc `SELECT` trước chỉ giúp xem dữ liệu ở thời điểm kiểm tra; một transaction khác vẫn có thể thay đổi nguồn hoặc chèn cùng khóa trước khi INSERT chạy. Constraint trên bảng đích vẫn là lớp bảo vệ cuối cùng.

## 9. INSERT từ SELECT và kiểu dữ liệu

Biểu thức SELECT được chuyển vào kiểu cột đích. Hãy bảo đảm kiểu và miền giá trị tương thích:

- Số nguyên không vượt phạm vi của cột đích.
- Giá trị decimal giữ đủ precision/scale.
- Chuỗi không bị cắt hoặc chuyển charset ngoài ý muốn.
- Ngày giờ đúng kiểu và timezone.
- SQL NULL chỉ được ghi vào cột cho phép NULL hoặc có logic thay thế rõ ràng.

Ví dụ chuyển đổi có chủ đích:

```sql
INSERT INTO monthly_revenue (month_start, total_amount)
SELECT
    CAST(DATE_FORMAT(o.created_at, '%Y-%m-01') AS DATE),
    CAST(SUM(oi.quantity * oi.unit_price) AS DECIMAL(18,2))
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.id
WHERE o.status = 'PAID'
GROUP BY DATE_FORMAT(o.created_at, '%Y-%m-01');
```

Việc CAST giúp thể hiện kiểu mong muốn. Tuy nhiên, phải kiểm tra cách biểu thức ngày giờ được chuyển đổi và precision phù hợp schema đích. Không dùng CAST để che dữ liệu nguồn không hợp lệ.

## 10. Hiệu năng của INSERT

### 10.1. Giảm round-trip bằng multi-row INSERT

Nếu ứng dụng có 500 hàng, gửi 500 câu INSERT riêng thường tốn nhiều round-trip hơn so với chia thành các batch multi-row. Chọn batch size dựa trên benchmark và giới hạn packet; không có một con số tối ưu cho mọi workload.

### 10.2. Index và constraint làm tăng chi phí ghi

Mỗi INSERT cần cập nhật index liên quan và kiểm tra constraint. Bảng có nhiều index, foreign key hoặc trigger có chi phí ghi cao hơn. Chỉ tạo index phục vụ truy vấn thực tế; không bỏ constraint để tăng tốc mà không có quy trình kiểm tra thay thế.

### 10.3. Kích thước packet

Multi-row INSERT lớn có thể vượt `max_allowed_packet` ở client hoặc server. Khi gặp lỗi packet quá lớn, giảm batch size và kiểm tra cấu hình client/server. Không tăng giới hạn vô hạn; batch phải phù hợp tài nguyên và thời gian xử lý.

### 10.4. Transaction quá lớn

Một transaction ghi hàng trăm nghìn hoặc hàng triệu dòng có thể giữ undo, lock và tài nguyên lâu, làm tăng replication lag hoặc gây áp lực purge. Có thể chia theo batch và commit từng phần nếu nghiệp vụ chấp nhận tính hoàn tất từng phần. Nếu cần tất cả hoặc không gì cả, phải giữ ranh giới transaction tương ứng hoặc thiết kế quy trình staging/đối soát.

## 11. Prepared statement khi INSERT từ ứng dụng

Không nối trực tiếp input người dùng vào câu SQL. Dùng parameter binding:

```java
String sql = "INSERT INTO customers (email, full_name, status) VALUES (?, ?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    statement.setString(2, fullName);
    statement.setString(3, status);
    int affectedRows = statement.executeUpdate();
}
```

Với nhiều hàng, có thể dùng JDBC batch:

```java
String sql = "INSERT INTO customers (email, full_name) VALUES (?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    for (Customer customer : customers) {
        statement.setString(1, customer.email());
        statement.setString(2, customer.fullName());
        statement.addBatch();
    }
    int[] results = statement.executeBatch();
}
```

Batch API có thể được driver tối ưu hoặc gửi theo nhiều statement tùy cấu hình; không giả định `executeBatch()` luôn tương đương một câu multi-row INSERT duy nhất. Nếu cần atomicity, quản lý transaction rõ ràng và xử lý `BatchUpdateException`.

## 12. Các lỗi thường gặp khi INSERT

| Lỗi/triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Column count doesn't match value count | Số giá trị không khớp danh sách cột | Kiểm tra từng tuple và thứ tự cột |
| Duplicate entry | Vi phạm PRIMARY KEY hoặc UNIQUE | Xác định chính sách lỗi, ignore hay upsert |
| Cannot be null | Ghi NULL hoặc bỏ cột NOT NULL không có default | Cung cấp giá trị hợp lệ hoặc thiết kế default đúng nghiệp vụ |
| Data too long / out of range | Giá trị vượt kích thước hoặc miền kiểu | Kiểm tra schema và dữ liệu nguồn, tránh phụ thuộc implicit truncation |
| Cannot add or update a child row | Giá trị FK không có parent | Nạp parent trước, kiểm tra khóa ngoại và dữ liệu nguồn |
| INSERT IGNORE không ghi đủ hàng | Hàng duplicate hoặc lỗi bị chuyển thành warning | Chạy SHOW WARNINGS, kiểm tra affected rows và đối soát nguồn/đích |
| LAST_INSERT_ID trả giá trị bất ngờ | Dùng khác connection hoặc insert trước đó không thành công | Lấy ID trên cùng connection ngay sau insert thành công |
| Batch quá lớn bị packet error | Câu lệnh vượt giới hạn packet | Giảm batch size, kiểm tra max_allowed_packet |
| INSERT SELECT tạo dữ liệu trùng | Nguồn có nhiều hàng hoặc job chạy đồng thời | Xác định grain, unique key và chiến lược idempotency |
| Rollback không hoàn tác dữ liệu | Bảng dùng engine không transactional hoặc transaction đã commit | Dùng InnoDB và kiểm tra ranh giới transaction |

## 13. Quy trình chọn dạng INSERT

| Nhu cầu | Dạng SQL nên cân nhắc |
|---|---|
| Tạo một bản ghi từ form | `INSERT ... (columns) VALUES (...)` |
| Tạo bản ghi dùng default | `INSERT ... () VALUES ()` nếu schema cho phép |
| Ghi một lô hàng cùng cấu trúc | Multi-row `INSERT ... VALUES (...), (...)` |
| Sao chép/lọc/tổng hợp dữ liệu trong server | `INSERT ... SELECT` |
| Bỏ qua hàng trùng có chủ đích | `INSERT IGNORE`, kèm kiểm tra warnings |
| Cập nhật khi khóa đã tồn tại | `INSERT ... ON DUPLICATE KEY UPDATE` |
| Bảo đảm nhiều bảng cùng ghi hoặc cùng hủy | Transaction InnoDB |
| Ghi dữ liệu động từ ứng dụng | Prepared statement / parameter binding |

Trước khi chạy trên production, hãy xác định khóa duy nhất, số hàng dự kiến, hành vi khi trùng, tác động trigger/FK, batch size và khả năng rollback.

## 14. Checklist an toàn trước và sau INSERT

**Trước khi ghi:**

- Danh sách cột có tường minh và đúng thứ tự không?
- Mỗi tuple có đúng số lượng giá trị không?
- Default, NULL và chuỗi rỗng có được phân biệt đúng không?
- Giá trị có đúng kiểu, precision, charset và miền dữ liệu không?
- Có thể vi phạm PRIMARY KEY, UNIQUE hoặc FOREIGN KEY không?
- Nếu dùng INSERT SELECT, đã chạy SELECT kiểm tra nguồn và grain chưa?
- Có nguy cơ fan-out làm tăng số hàng hoặc tổng tiền không?
- Chính sách duplicate là lỗi, bỏ qua hay cập nhật?
- Batch size và transaction có phù hợp tải hệ thống không?

**Sau khi ghi:**

- Kiểm tra affected rows và warnings.
- Lấy generated key trên đúng connection nếu cần.
- Đối soát số hàng nguồn và đích khi import.
- Commit chỉ khi mọi thao tác trong transaction thành công.
- Ghi log đủ để retry an toàn mà không tạo dữ liệu trùng.
- Theo dõi thời gian thực thi, lock wait, replication lag và tài nguyên nếu batch lớn.

## Kết luận

`INSERT ... VALUES` phù hợp tạo một hàng; multi-row `INSERT` giảm round-trip khi ghi nhiều hàng cùng cấu trúc; `INSERT ... SELECT` giúp lọc, biến đổi và tổng hợp dữ liệu ngay trong MySQL. Luôn liệt kê cột, hiểu rõ DEFAULT/NULL, kiểm tra unique và foreign key, chọn chính sách duplicate có chủ đích và quản lý transaction InnoDB. Với dữ liệu động, dùng prepared statement; với batch/import, kiểm tra warnings, affected rows, kích thước lô và kết quả đối soát. Những nguyên tắc này giúp thao tác ghi dữ liệu chính xác, có thể phục hồi và vận hành ổn định.
