# Generated column dạng VIRTUAL/STORED và giới hạn biểu thức

Generated column (cột được sinh tự động) là cột có giá trị được MySQL tính từ biểu thức dựa trên các cột khác trong cùng hàng. Thay vì yêu cầu ứng dụng tự tính và ghi cùng một giá trị ở nhiều nơi, bạn khai báo biểu thức ngay trong định nghĩa bảng. MySQL tự tính lại giá trị khi dữ liệu nguồn thay đổi và cung cấp cột đó như một cột có thể truy vấn.

MySQL hỗ trợ hai cách lưu generated column: `VIRTUAL` và `STORED`. Cột `VIRTUAL` được tính khi cần đọc, còn cột `STORED` được tính khi hàng được ghi và lưu cùng dữ liệu hàng. Cả hai có thể được lập index trong các trường hợp được engine hỗ trợ. Vì vậy, quyết định không chỉ là “có lưu hay không”, mà còn liên quan đến CPU, dung lượng, index, tần suất đọc/ghi và giới hạn của biểu thức.

Bài học này thuộc module `DATABASE_MYSQL`, tập trung vào thiết kế bảng, ràng buộc, kiểu dữ liệu, truy vấn SQL, index, transaction, tối ưu truy vấn và vận hành cơ sở dữ liệu quan hệ. Generated column đặc biệt hữu ích khi cần biểu diễn giá trị dẫn xuất ổn định, chuẩn hóa một biểu thức truy vấn lặp lại hoặc lập index trên một thuộc tính được trích xuất từ JSON.

Sau bài học, bạn có thể:

- Giải thích generated column và sự khác nhau giữa `VIRTUAL` với `STORED`.
- Khai báo generated column trong `CREATE TABLE` và `ALTER TABLE`.
- Hiểu thời điểm MySQL tính giá trị và tác động của index.
- Dùng generated column để lập index trên biểu thức hoặc thuộc tính JSON.
- Nhận biết các biểu thức được phép và các giới hạn quan trọng.
- Kiểm tra định nghĩa, biểu thức sinh và index của generated column.
- Lựa chọn VIRTUAL/STORED dựa trên workload và lập kế hoạch thay đổi schema an toàn.

## 1. Generated column là gì?

Generated column là một cột mà giá trị của nó được xác định bởi một biểu thức khai báo trong schema. Biểu thức thường sử dụng các cột khác trong cùng hàng. MySQL tự duy trì giá trị dẫn xuất khi hàng được insert hoặc update.

Ví dụ, bảng đơn hàng có giá chưa thuế, số lượng và tổng dòng hàng:

```sql
CREATE TABLE order_lines (
    order_line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    unit_price DECIMAL(12, 2) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    line_total DECIMAL(22, 2)
        GENERATED ALWAYS AS (unit_price * quantity) STORED,
    PRIMARY KEY (order_line_id)
) ENGINE = InnoDB;

INSERT INTO order_lines (unit_price, quantity)
VALUES (125.50, 3);

SELECT unit_price, quantity, line_total
FROM order_lines;
```

Kết quả `line_total` được MySQL tính từ `unit_price * quantity`. Khi ứng dụng cập nhật `quantity` hoặc `unit_price`, MySQL tự tính lại generated column. Ứng dụng không cần tự gửi giá trị `line_total`.

Generated column khác với cột thông thường được ứng dụng tự cập nhật. Nếu ứng dụng lưu cả `unit_price`, `quantity` và `line_total` như ba cột độc lập, code phải bảo đảm chúng luôn nhất quán. Generated column chuyển quy tắc tính toán vào schema để MySQL duy trì nhất quán cho mọi câu lệnh ghi.

## 2. Cú pháp khai báo

Cú pháp tổng quát trong định nghĩa cột:

```sql
column_name data_type
    [GENERATED ALWAYS] AS (expression)
    [VIRTUAL | STORED]
    [NOT NULL | NULL]
    [UNIQUE [KEY] | [PRIMARY] KEY]
    [COMMENT 'description']
```

Trong đó:

- `GENERATED ALWAYS` là phần có thể ghi tường minh; từ khóa này có thể được lược bỏ trong cú pháp MySQL.
- `AS (expression)` khai báo biểu thức tạo giá trị.
- `VIRTUAL` chỉ định cột ảo, được tính khi đọc; đây là mặc định nếu không ghi `VIRTUAL` hoặc `STORED`.
- `STORED` yêu cầu MySQL tính giá trị khi ghi và lưu giá trị trong hàng.
- Kiểu dữ liệu được khai báo cho cột quyết định cách biểu diễn kết quả của biểu thức.

Ví dụ dùng mặc định `VIRTUAL`:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    price DECIMAL(12, 2) NOT NULL,
    tax_rate DECIMAL(5, 4) NOT NULL,
    price_with_tax DECIMAL(14, 2)
        AS (price * (1 + tax_rate)),
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
```

`price_with_tax` là `VIRTUAL` vì không chỉ định `STORED`. Nếu muốn lưu kết quả trong hàng, thêm từ khóa `STORED` sau biểu thức.

Khi chọn kiểu dữ liệu, hãy bảo đảm kiểu đó chứa được kết quả biểu thức. MySQL chuyển kết quả biểu thức sang kiểu đã khai báo; nếu kết quả vượt miền, bị làm tròn hoặc bị cắt, dữ liệu có thể không còn như mong đợi. Hãy dùng `CAST()` tường minh khi cần kiểm soát kiểu và scale, đồng thời kiểm tra SQL mode và warning/error khi ghi.

## 3. VIRTUAL và STORED khác nhau thế nào?

| Tiêu chí | `VIRTUAL` | `STORED` |
| --- | --- | --- |
| Thời điểm tính | Khi giá trị được đọc hoặc cần cho một thao tác | Khi hàng được insert hoặc update |
| Lưu trong phần dữ liệu hàng | Không | Có |
| Chi phí đọc | Có thể phải tính biểu thức khi đọc | Đọc giá trị đã tính và lưu |
| Chi phí ghi | Tính khi thao tác cần duy trì giá trị/index | Tính và ghi lại giá trị khi hàng thay đổi |
| Dung lượng hàng | Không chiếm chỗ lưu giá trị trong hàng | Chiếm dung lượng lưu trữ theo kiểu cột |
| Index | Có thể lập secondary index nếu engine hỗ trợ | Có thể lập index nếu engine hỗ trợ |
| Thay đổi dữ liệu nguồn | Giá trị được tính từ dữ liệu mới khi đọc | MySQL cập nhật giá trị lưu khi hàng thay đổi |

### 3.1. VIRTUAL

Với `VIRTUAL`, MySQL không lưu giá trị generated column trong phần dữ liệu hàng. Khi truy vấn cần giá trị, MySQL tính biểu thức dựa trên các cột nguồn. Cách này tiết kiệm dung lượng bảng và tránh lưu trùng giá trị có thể suy ra từ dữ liệu khác.

VIRTUAL phù hợp khi:

- Biểu thức đơn giản, chi phí tính toán thấp.
- Cột ít được đọc hoặc chỉ dùng trong một số truy vấn.
- Không cần lưu thêm một bản sao vật lý của giá trị dẫn xuất.
- Muốn giữ schema gọn nhưng vẫn có tên cột và kiểu dữ liệu rõ ràng.

Không nên mặc định VIRTUAL luôn nhanh hơn. Nếu truy vấn đọc rất nhiều hàng và phải tính biểu thức phức tạp liên tục, chi phí CPU có thể đáng kể.

### 3.2. STORED

Với `STORED`, MySQL tính biểu thức khi hàng được insert hoặc update rồi lưu kết quả trong hàng. Khi đọc, MySQL lấy giá trị đã lưu thay vì tính lại biểu thức từ đầu.

STORED phù hợp khi:

- Biểu thức có chi phí tính toán đáng kể và cột được đọc thường xuyên.
- Tải đọc lớn hơn nhiều so với tải ghi.
- Muốn lưu vật lý giá trị dẫn xuất để giảm chi phí tính lại khi đọc.
- Cần một generated column đáp ứng yêu cầu lưu trữ của tính năng khác có giới hạn đối với VIRTUAL.

Đổi lại, STORED làm tăng kích thước hàng và chi phí ghi. Khi cột nguồn thay đổi, MySQL phải tính lại và ghi giá trị generated column.

### 3.3. Index trên VIRTUAL không có nghĩa là hoàn toàn không lưu giá trị

InnoDB hỗ trợ secondary index trên generated column dạng `VIRTUAL`. Khi index được tạo, giá trị cần thiết được lưu trong cấu trúc index và được cập nhật khi dữ liệu nguồn thay đổi. Vì vậy, VIRTUAL không chiếm dung lượng giá trị trong clustered row, nhưng một index trên cột đó vẫn tiêu tốn dung lượng và làm tăng chi phí ghi.

Đây là điểm quan trọng khi tối ưu: nếu mục tiêu là lọc nhanh theo một biểu thức, bạn có thể dùng VIRTUAL generated column có index mà không nhất thiết phải chuyển sang STORED. Hãy đo workload đọc/ghi và dung lượng index để quyết định.

## 4. Tạo index trên generated column

Generated column có thể được lập index để truy vấn theo giá trị dẫn xuất mà không phải quét và tính biểu thức cho mọi hàng. InnoDB hỗ trợ secondary index trên generated columns, bao gồm dạng VIRTUAL.

Ví dụ chuẩn hóa email thành chữ thường để tìm kiếm:

```sql
CREATE TABLE app_users (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    email_normalized VARCHAR(255)
        GENERATED ALWAYS AS (LOWER(email)) VIRTUAL,
    PRIMARY KEY (user_id),
    UNIQUE KEY uk_app_users_email_normalized (email_normalized)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
```

Truy vấn:

```sql
SELECT user_id, email
FROM app_users
WHERE email_normalized = LOWER('User@example.com');
```

Index có thể giúp tìm theo `email_normalized`. Tuy nhiên, việc chuẩn hóa email còn phụ thuộc quy tắc nghiệp vụ và collation. `LOWER()` không tự giải quyết mọi quy tắc so sánh email; hãy quyết định chính sách chuẩn hóa ở cả ứng dụng và database.

Có thể tạo index sau khi bảng đã tồn tại:

```sql
CREATE INDEX idx_products_price_with_tax
ON products (price_with_tax);
```

Khi đánh giá, dùng `EXPLAIN` để xác nhận optimizer có chọn index trong truy vấn thực tế hay không:

```sql
EXPLAIN
SELECT product_id, price_with_tax
FROM products
WHERE price_with_tax >= 1000.00;
```

Index chỉ hữu ích khi điều kiện truy vấn và phân bố dữ liệu khiến optimizer chọn nó. Không tạo index cho mọi generated column; mỗi index cần dung lượng và làm tăng chi phí `INSERT`, `UPDATE`, `DELETE`.

## 5. Generated column và JSON

Một ứng dụng có thể lưu payload linh hoạt trong cột JSON nhưng vẫn cần lọc thường xuyên theo một vài thuộc tính. Generated column cho phép trích thuộc tính JSON thành một cột có kiểu rõ ràng và lập index trên đó.

Ví dụ:

```sql
CREATE TABLE event_log (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    payload JSON NOT NULL,
    event_type VARCHAR(50)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(payload, '$.type'))
        ) STORED,
    event_date DATE
        GENERATED ALWAYS AS (
            CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.eventDate')) AS DATE)
        ) VIRTUAL,
    PRIMARY KEY (event_id),
    KEY idx_event_log_type (event_type),
    KEY idx_event_log_date (event_date)
) ENGINE = InnoDB;
```

Thêm dữ liệu:

```sql
INSERT INTO event_log (payload) VALUES
('{"type":"ORDER_CREATED","eventDate":"2026-11-19","orderId":1001}'),
('{"type":"PAYMENT_RECEIVED","eventDate":"2026-11-20","orderId":1001}');
```

Truy vấn theo thuộc tính:

```sql
SELECT event_id, event_type, event_date
FROM event_log
WHERE event_type = 'ORDER_CREATED'
  AND event_date >= '2026-11-19';
```

Các lưu ý quan trọng:

- Đặt kiểu dữ liệu và độ dài phù hợp với giá trị JSON có thể xuất hiện.
- Dùng `JSON_UNQUOTE()` khi muốn lấy scalar dạng chuỗi, tránh giữ dấu ngoặc kép của giá trị JSON string.
- Nếu thuộc tính có thể vắng mặt hoặc sai kiểu, cần xác định kết quả `NULL`/ép kiểu và kiểm tra dữ liệu đầu vào.
- `CAST(... AS DATE)` chỉ phù hợp khi giá trị JSON có format ngày được quy định. Nếu dữ liệu không chuẩn, biểu thức có thể không cho kết quả mong muốn hoặc phát sinh lỗi tùy ngữ cảnh.
- Những thuộc tính thường xuyên lọc, join, sắp xếp hoặc cần constraint có thể nên là cột quan hệ thực sự thay vì chỉ nằm trong JSON.

## 6. Giới hạn biểu thức generated column

Không phải biểu thức SQL nào cũng được phép trong generated column. MySQL cần có khả năng tính lại giá trị một cách nhất quán từ dữ liệu của hàng.

### 6.1. Biểu thức phải dựa trên dữ liệu của cùng hàng

Generated column có thể tham chiếu các cột khác trong cùng bảng và dùng toán tử, literal cùng những hàm được phép. Nó không phải một truy vấn con có thể đọc bảng khác.

Ví dụ hợp lệ về mặt ý tưởng:

```sql
CREATE TABLE measurements (
    measurement_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    width_mm DECIMAL(10, 2) NOT NULL,
    height_mm DECIMAL(10, 2) NOT NULL,
    area_mm2 DECIMAL(20, 4)
        GENERATED ALWAYS AS (width_mm * height_mm) STORED,
    PRIMARY KEY (measurement_id)
) ENGINE = InnoDB;
```

Biểu thức `width_mm * height_mm` chỉ phụ thuộc các cột của cùng hàng.

### 6.2. Không dùng subquery hoặc tham chiếu bảng khác

Không thể dùng truy vấn con để tính giá trị generated column:

```sql
-- Không hợp lệ: biểu thức generated column không được chứa subquery
CREATE TABLE invalid_example (
    item_id BIGINT NOT NULL,
    category_name VARCHAR(100)
        AS ((SELECT name FROM categories WHERE categories.id = item_id))
);
```

Nếu giá trị cần lấy từ bảng khác, hãy dùng `JOIN` trong truy vấn, tạo view phù hợp hoặc duy trì một cột thông thường bằng logic nghiệp vụ/trigger có kiểm soát. Không dùng generated column để thay thế phép join.

### 6.3. Không dùng biến, tham số hoặc hàm không xác định

Biểu thức generated column không được phụ thuộc vào trạng thái bên ngoài hàng như:

- User variable hoặc system variable.
- Stored function hoặc loadable function.
- Subquery hoặc tham số của prepared statement.
- Hàm không xác định (nondeterministic) có thể trả kết quả khác nhau dù dữ liệu hàng không đổi, chẳng hạn `NOW()`, `RAND()` hoặc `UUID()`.

Ví dụ không hợp lệ:

```sql
-- Không hợp lệ: NOW() thay đổi theo thời điểm đánh giá
CREATE TABLE invalid_created_at (
    created_at DATETIME NOT NULL,
    age_in_seconds BIGINT AS (TIMESTAMPDIFF(SECOND, created_at, NOW()))
);
```

Nếu cần thời gian tạo, hãy lưu bằng cột thông thường có `DEFAULT CURRENT_TIMESTAMP`. Nếu cần thời gian hiện tại khi truy vấn, tính trong câu `SELECT` thay vì lưu thành generated column.

### 6.4. Không tham chiếu AUTO_INCREMENT column

Generated column không được tham chiếu cột `AUTO_INCREMENT`. Giá trị tự tăng được cấp trong quá trình insert, không phù hợp với các ràng buộc biểu thức generated column theo quy tắc của MySQL.

Nếu cần một mã dẫn xuất từ ID tự tăng, có thể tính trong câu truy vấn hoặc ở tầng ứng dụng sau khi ID đã được cấp. Không khai báo generated column dựa trên cột tự tăng.

### 6.5. Không gán giá trị trực tiếp cho generated column

Khi `INSERT` hoặc `UPDATE`, ứng dụng không thể tự đặt giá trị tùy ý cho generated column. Hãy bỏ cột đó khỏi danh sách ghi hoặc chỉ định từ khóa `DEFAULT` theo cú pháp hỗ trợ.

```sql
-- Đúng: chỉ ghi các cột nguồn
INSERT INTO order_lines (unit_price, quantity)
VALUES (80.00, 2);

-- Không hợp lệ: tự gán giá trị generated column
UPDATE order_lines
SET line_total = 100.00
WHERE order_line_id = 1;
```

Muốn thay đổi giá trị generated column, hãy cập nhật các cột nguồn trong biểu thức. MySQL tự tính lại kết quả.

### 6.6. Phụ thuộc thứ tự và các generated column khác

Một generated column có thể tham chiếu các generated column khác khi quan hệ phụ thuộc hợp lệ. Không tạo vòng tham chiếu và không tham chiếu cột được định nghĩa sau theo cách làm phụ thuộc không hợp lệ. Khi có nhiều lớp giá trị dẫn xuất, hãy khai báo theo thứ tự phụ thuộc rõ ràng hoặc gộp biểu thức nếu điều đó giúp schema dễ hiểu hơn.

Ví dụ:

```sql
CREATE TABLE product_dimensions (
    product_id BIGINT UNSIGNED NOT NULL,
    width_cm DECIMAL(8, 2) NOT NULL,
    height_cm DECIMAL(8, 2) NOT NULL,
    area_cm2 DECIMAL(16, 4)
        AS (width_cm * height_cm) STORED,
    area_m2 DECIMAL(16, 8)
        AS (area_cm2 / 10000) VIRTUAL,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
```

Khi thiết kế phụ thuộc nhiều tầng, cần thử DDL trên đúng phiên bản MySQL và tránh chuỗi công thức quá dài khó bảo trì.

## 7. Kiểu dữ liệu và chuyển đổi kết quả biểu thức

Kiểu dữ liệu của generated column là một phần của schema, không nên để kết quả biểu thức quyết định ngầm mà không xem xét miền giá trị.

Ví dụ với tiền:

```sql
CREATE TABLE invoice_lines (
    invoice_line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    unit_price DECIMAL(12, 2) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    discount_rate DECIMAL(5, 4) NOT NULL DEFAULT 0,
    line_total DECIMAL(22, 2)
        GENERATED ALWAYS AS (
            CAST(unit_price * quantity * (1 - discount_rate) AS DECIMAL(22, 2))
        ) STORED,
    PRIMARY KEY (invoice_line_id),
    CONSTRAINT chk_invoice_discount CHECK (discount_rate >= 0 AND discount_rate <= 1)
) ENGINE = InnoDB;
```

Ở đây, `CAST()` làm rõ scale mong muốn của kết quả. Tuy nhiên, phép tính tiền trong nghiệp vụ thật còn cần chính sách làm tròn, cách tính thuế, chiết khấu, tiền tệ và phân bổ chênh lệch. Generated column chỉ thực hiện biểu thức đã khai báo, không tự hiểu quy tắc kế toán.

Với chuỗi, hãy chỉ định độ dài đủ chứa kết quả. Với JSON, hãy xác định cách xử lý missing key, JSON `null`, scalar sai kiểu và dữ liệu không theo format. Với phép chia, cần xử lý mẫu số bằng 0 bằng biểu thức an toàn như `NULLIF(denominator, 0)` nếu `NULL` là kết quả nghiệp vụ chấp nhận được.

## 8. Index, optimizer và biểu thức truy vấn

Generated column thường được dùng để đưa một biểu thức lặp lại vào schema và index hóa giá trị của nó.

Ví dụ, ứng dụng thường tìm theo phần domain của email:

```sql
CREATE TABLE contacts (
    contact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    email_domain VARCHAR(255)
        GENERATED ALWAYS AS (SUBSTRING_INDEX(email, '@', -1)) VIRTUAL,
    PRIMARY KEY (contact_id),
    KEY idx_contacts_email_domain (email_domain)
) ENGINE = InnoDB;

SELECT contact_id, email
FROM contacts
WHERE email_domain = 'example.com';
```

Thay vì tính `SUBSTRING_INDEX()` cho mọi hàng trong truy vấn, MySQL có thể sử dụng index trên `email_domain` để tìm các giá trị phù hợp. Hãy xác nhận bằng `EXPLAIN` với dữ liệu đại diện.

### 8.1. So sánh generated column với functional index

MySQL 8.0.13 trở lên hỗ trợ functional key parts, cho phép tạo index trực tiếp trên biểu thức:

```sql
-- Nếu chọn functional index thay cho index trên generated column,
-- bỏ index cũ trước để tránh lưu hai index cho cùng một biểu thức.
DROP INDEX idx_contacts_email_domain ON contacts;

CREATE INDEX idx_contacts_email_domain_expr
ON contacts ((SUBSTRING_INDEX(email, '@', -1)));
```

Với functional index, truy vấn cũng nên dùng biểu thức tương ứng:

```sql
SELECT contact_id
FROM contacts
WHERE SUBSTRING_INDEX(email, '@', -1) = 'example.com';
```

Functional index được MySQL triển khai dựa trên cơ chế hidden virtual generated column. Dùng functional index khi chỉ cần index hóa biểu thức mà không cần đặt tên cột dẫn xuất trong schema. Dùng generated column tường minh khi muốn truy vấn, hiển thị, kiểm tra hoặc tái sử dụng giá trị dẫn xuất như một cột có tên.

Không tạo cả functional index và index generated column cho cùng biểu thức nếu không có lý do rõ ràng; chúng có thể trùng lặp dung lượng và chi phí ghi.

### 8.2. Optimizer có thể nhận diện biểu thức tương ứng

Trong một số trường hợp, optimizer có thể dùng index trên generated column khi truy vấn sử dụng biểu thức tương đương với biểu thức generated column. Việc khớp biểu thức có quy tắc về cấu trúc và kiểu kết quả; không nên giả định hai biểu thức chỉ “trông giống nhau” sẽ luôn dùng cùng index.

Viết truy vấn tham chiếu trực tiếp tên generated column thường rõ ràng và dễ kiểm soát nhất:

```sql
SELECT contact_id
FROM contacts
WHERE email_domain = 'example.com';
```

Kiểm tra `EXPLAIN` hoặc `EXPLAIN ANALYZE` trên phiên bản MySQL thực tế để xác nhận đường truy cập. `EXPLAIN ANALYZE` thực thi truy vấn, nên chỉ dùng khi có thể chấp nhận tải do truy vấn tạo ra.

## 9. Kiểm tra generated column trong schema

### 9.1. SHOW CREATE TABLE

```sql
SHOW CREATE TABLE order_lines\G
```

Kết quả hiển thị kiểu dữ liệu, biểu thức `GENERATED ALWAYS AS (...)`, chế độ `VIRTUAL` hoặc `STORED` và index liên quan.

### 9.2. INFORMATION_SCHEMA.COLUMNS

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    EXTRA,
    GENERATION_EXPRESSION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND GENERATION_EXPRESSION <> ''
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

`GENERATION_EXPRESSION` chứa biểu thức dùng để tạo cột. `EXTRA` thường cho biết `VIRTUAL GENERATED` hoặc `STORED GENERATED`. Dùng metadata này khi viết công cụ kiểm tra schema hoặc rà soát migration.

### 9.3. Kiểm tra index

```sql
SHOW INDEX FROM contacts;
```

Kết hợp với `EXPLAIN` để xem truy vấn có dùng index trên generated column hay không. Việc index tồn tại không bảo đảm optimizer sẽ chọn nó; độ chọn lọc, số hàng, thống kê và chi phí truy cập đều ảnh hưởng kế hoạch.

## 10. Thay đổi generated column bằng ALTER TABLE

Có thể thêm generated column vào bảng hiện có:

```sql
ALTER TABLE orders
ADD COLUMN order_year SMALLINT
    GENERATED ALWAYS AS (YEAR(placed_at)) VIRTUAL;
```

Sau đó tạo index:

```sql
CREATE INDEX idx_orders_order_year
ON orders (order_year);
```

Hoặc thay đổi biểu thức bằng cách sửa định nghĩa cột:

```sql
ALTER TABLE orders
MODIFY COLUMN order_year SMALLINT
    GENERATED ALWAYS AS (YEAR(placed_at)) STORED;
```

Việc chuyển từ VIRTUAL sang STORED hoặc ngược lại có thể yêu cầu rebuild bảng và tốn thời gian, I/O cùng dung lượng tạm. Khả năng online/in-place phụ thuộc engine, phiên bản và loại thay đổi; không giả định `ALTER TABLE` luôn tức thời hoặc không khóa.

Trước khi triển khai migration:

1. Kiểm tra số lượng hàng, kích thước bảng và index hiện tại.
2. Kiểm tra biểu thức trên dữ liệu thực, đặc biệt giá trị `NULL`, dữ liệu sai kiểu và giá trị biên.
3. Đánh giá thời gian tính lại generated column và xây index.
4. Dự trù dung lượng đĩa tạm, redo/undo log và tải I/O.
5. Thử trên bản sao dữ liệu có kích thước gần production.
6. Xác định thuật toán DDL và mức độ khóa được hỗ trợ cho đúng phiên bản MySQL.
7. Sau migration, xác minh `SHOW CREATE TABLE`, metadata, index, kết quả truy vấn và kế hoạch thực thi.

## 11. Những giới hạn cần ghi nhớ

| Giới hạn | Ý nghĩa thực tế |
| --- | --- |
| Không có subquery | Không thể đọc dữ liệu từ bảng khác trong biểu thức generated column |
| Không dùng stored function hoặc loadable function | Không gọi logic tùy biến bên ngoài tập biểu thức được MySQL cho phép |
| Không dùng biến hoặc parameter | Giá trị không được phụ thuộc trạng thái session hoặc tham số runtime |
| Không dùng hàm không xác định | Không dùng `NOW()`, `RAND()`, `UUID()` và các giá trị thay đổi theo thời điểm/ngữ cảnh |
| Không tham chiếu AUTO_INCREMENT | Biểu thức không thể phụ thuộc cột tự tăng |
| Không gán trực tiếp giá trị | INSERT/UPDATE phải thay đổi cột nguồn; generated value do MySQL tính |
| Không có DEFAULT tùy ý cho generated column | Giá trị được xác định bởi biểu thức, không phải giá trị default độc lập |
| Ràng buộc phụ thuộc engine | Index, foreign key và một số tính năng có giới hạn theo engine/loại generated column |
| Kiểu kết quả phải phù hợp | Giá trị biểu thức có thể bị chuyển kiểu, làm tròn hoặc vượt miền đã khai báo |

Generated column không phải nơi thích hợp cho mọi phép tính. Nếu biểu thức cần dữ liệu từ bảng khác, phụ thuộc thời gian hiện tại, cần gọi logic nghiệp vụ phức tạp hoặc phải truy cập trạng thái bên ngoài, hãy dùng truy vấn, view, logic ứng dụng hoặc một quy trình duy trì dữ liệu riêng.

Với foreign key, partitioning và các index đặc biệt, kiểm tra giới hạn cụ thể của phiên bản MySQL và storage engine trước khi thiết kế phụ thuộc vào generated column. Không suy rộng rằng mọi tính năng hỗ trợ trên cột thường đều hỗ trợ giống hệt trên generated column VIRTUAL và STORED.

## 12. Chọn VIRTUAL hay STORED theo workload

| Tình huống | Lựa chọn khởi đầu | Lý do |
| --- | --- | --- |
| Biểu thức đơn giản, ít đọc | VIRTUAL | Tránh lưu giá trị dẫn xuất không cần thiết |
| Biểu thức được đọc thường xuyên, chi phí tính toán cao | STORED | Tính khi ghi, giảm tính toán khi đọc |
| Cần index trên giá trị dẫn xuất | VIRTUAL hoặc STORED có index | InnoDB hỗ trợ secondary index trên virtual generated column |
| Cột JSON trích xuất dùng trong điều kiện lọc | VIRTUAL có index hoặc STORED có index | Chọn theo chi phí đọc/ghi và nhu cầu lưu giá trị |
| Bảng ghi rất nhiều, biểu thức phức tạp | Đo cả hai phương án | STORED làm tăng chi phí ghi; VIRTUAL có thể tăng CPU đọc/index maintenance |
| Giá trị cần tính từ bảng khác hoặc thời gian hiện tại | Không dùng generated column | Biểu thức không đáp ứng giới hạn phụ thuộc dữ liệu ổn định của cùng hàng |

Không chọn STORED chỉ vì muốn lập index. Nếu engine hỗ trợ index trên VIRTUAL và cột không cần giá trị trong clustered row, VIRTUAL có thể đáp ứng mục tiêu. Ngược lại, nếu truy vấn thường đọc giá trị trên lượng hàng lớn mà không thể dùng index phù hợp, STORED có thể giảm CPU.

Đo với dữ liệu gần thực tế:

- Tỷ lệ đọc/ghi.
- Chi phí tính biểu thức.
- Kích thước hàng và index.
- Số lượng hàng được lọc.
- Thời gian truy vấn và mức sử dụng CPU/I/O.
- Chi phí rebuild khi thay đổi biểu thức.

## 13. Bài tập thực hành

1. Tạo bảng `order_lines` với `line_total` dạng VIRTUAL, chèn dữ liệu và kiểm tra giá trị được tính.
2. Cập nhật `unit_price` và `quantity`; xác nhận generated column tự thay đổi mà không cần cập nhật trực tiếp nó.
3. Tạo một bảng tương đương với `line_total` dạng STORED. So sánh `SHOW CREATE TABLE` và metadata trong `INFORMATION_SCHEMA.COLUMNS`.
4. Tạo index trên một VIRTUAL generated column. Chạy `EXPLAIN` cho truy vấn lọc theo cột đó và ghi nhận index được chọn.
5. Tạo bảng `event_log` có payload JSON và generated column trích `event_type`. Thử insert JSON thiếu key, JSON null và giá trị sai kiểu; ghi nhận kết quả.
6. Tạo generated column dùng `NOW()` hoặc subquery trong môi trường lab và quan sát lỗi DDL. Giải thích vì sao biểu thức đó không phù hợp.
7. Thêm generated column vào bảng hiện có bằng `ALTER TABLE`. Ước lượng tác động tới thời gian, dung lượng và khóa trên bảng lớn.
8. Tạo functional index trên một biểu thức và so sánh với generated column có tên cùng index. Chọn một cách và giải thích vì sao.
9. Viết một truy vấn dùng `EXPLAIN` hoặc `EXPLAIN ANALYZE` để đánh giá lợi ích của index trên generated column bằng dữ liệu có phân bố phù hợp.

## 14. Checklist thiết kế và triển khai

- [ ] Biểu thức chỉ phụ thuộc dữ liệu được phép của cùng hàng.
- [ ] Biểu thức không dùng subquery, biến, parameter, stored/loadable function hoặc hàm không xác định.
- [ ] Không tham chiếu cột `AUTO_INCREMENT`.
- [ ] Kiểu dữ liệu và độ dài chứa được toàn bộ kết quả biểu thức.
- [ ] Quy tắc `NULL`, ép kiểu, làm tròn và charset/collation đã được xác định.
- [ ] Đã chọn VIRTUAL hoặc STORED theo tỷ lệ đọc/ghi và chi phí tính toán.
- [ ] Nếu cần index, đã kiểm tra engine hỗ trợ và đánh giá chi phí index maintenance.
- [ ] Truy vấn thực tế đã được kiểm tra bằng `EXPLAIN`.
- [ ] Các ràng buộc phụ thuộc như foreign key hoặc partitioning đã được kiểm tra theo phiên bản/engine.
- [ ] Migration đã được thử trên dữ liệu đại diện và có kế hoạch rollback/khôi phục.
- [ ] Sau triển khai đã xác minh DDL, metadata, index và kết quả truy vấn.

## 15. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể tạo và kiểm tra được generated column VIRTUAL/STORED, giải thích thời điểm tính và lưu giá trị, tạo index trên generated column phù hợp, dùng nó để truy vấn thuộc tính JSON, nhận biết giới hạn của biểu thức và chọn phương án dựa trên workload. Bạn cũng cần biết cách thay đổi generated column bằng migration có kiểm soát và xác minh kết quả sau triển khai.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — CREATE TABLE and Generated Columns](https://dev.mysql.com/doc/refman/8.4/en/create-table-generated-columns.html)
- [MySQL 8.4 Reference Manual — Secondary Indexes and Generated Columns](https://dev.mysql.com/doc/refman/8.4/en/create-table-secondary-indexes.html)
- [MySQL 8.4 Reference Manual — CREATE INDEX](https://dev.mysql.com/doc/refman/8.4/en/create-index.html)
- [MySQL 8.4 Reference Manual — JSON Functions](https://dev.mysql.com/doc/refman/8.4/en/json-functions.html)
