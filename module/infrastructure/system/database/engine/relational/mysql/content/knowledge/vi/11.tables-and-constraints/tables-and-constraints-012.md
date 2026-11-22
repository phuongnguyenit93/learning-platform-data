# ALTER TABLE: thêm, đổi, xóa cột và ràng buộc

Schema của ứng dụng thay đổi cùng yêu cầu nghiệp vụ. Một bảng có thể cần thêm cột trạng thái, đổi kiểu dữ liệu, đặt giá trị mặc định, bổ sung khóa ngoại hoặc loại bỏ một ràng buộc cũ. Trong MySQL, lệnh ALTER TABLE thực hiện các thay đổi này trên cấu trúc bảng và có thể tác động đến dữ liệu hiện có, chỉ mục, khóa, thời gian khóa bảng và dung lượng lưu trữ.

Thay đổi schema vì thế cần được xem như một migration có kiểm soát. Trước khi chạy, phải hiểu định nghĩa hiện tại, dữ liệu đang có, các đối tượng phụ thuộc và khả năng hỗ trợ DDL online của phiên bản MySQL. Sau khi chạy, cần xác minh cấu trúc và dữ liệu thực tế.

Bài viết tập trung vào MySQL 8.x với InnoDB. Một số thuật toán ALTER TABLE và khả năng online DDL thay đổi theo phiên bản, storage engine, loại cột và cấu trúc bảng; luôn kiểm tra tài liệu đúng phiên bản triển khai.

## 1. ALTER TABLE thay đổi cấu trúc bảng

ALTER TABLE là câu lệnh DDL dùng để thêm, sửa, đổi tên hoặc xóa thành phần của bảng. Một câu lệnh có thể chứa một hoặc nhiều thao tác:

~~~sql
ALTER TABLE table_name
    alter_option,
    alter_option,
    ...;
~~~

Các nhóm thao tác thường gặp:

| Nhóm | Mục đích | Ví dụ |
|---|---|---|
| Thêm cột | Bổ sung thuộc tính mới | ADD COLUMN |
| Đổi cột | Đổi kiểu, NULL, DEFAULT hoặc thuộc tính | MODIFY COLUMN |
| Đổi tên cột | Giữ dữ liệu nhưng thay tên | RENAME COLUMN hoặc CHANGE COLUMN |
| Xóa cột | Loại bỏ dữ liệu và định nghĩa cột | DROP COLUMN |
| Thêm ràng buộc | Bảo đảm quy tắc dữ liệu | ADD CONSTRAINT |
| Xóa ràng buộc | Loại bỏ một quy tắc | DROP FOREIGN KEY, DROP CHECK, DROP PRIMARY KEY |
| Quản lý index | Thêm, xóa hoặc đổi tên index | ADD INDEX, DROP INDEX, RENAME INDEX |
| Đổi mặc định | Thay DEFAULT mà không đổi kiểu cột | ALTER COLUMN SET/DROP DEFAULT |

Trước khi thay đổi, kiểm tra cấu trúc hiện tại:

~~~sql
SHOW CREATE TABLE shop.customers\G
SHOW INDEX FROM shop.customers;
~~~

SHOW CREATE TABLE cho biết DDL mà server đang áp dụng. SHOW INDEX giúp kiểm tra các index hiện có và thứ tự key part. Hai lệnh này là điểm bắt đầu tốt để tránh thêm trùng hoặc xóa nhầm đối tượng.

## 2. Thêm cột bằng ADD COLUMN

### 2.1. Thêm cột mới

Cú pháp cơ bản:

~~~sql
ALTER TABLE customers
ADD COLUMN phone_number VARCHAR(30);
~~~

Cột mới được thêm vào cuối danh sách cột nếu không chỉ định vị trí. Với bảng có dữ liệu, các hàng hiện tại sẽ có giá trị NULL cho cột mới nếu cột cho phép NULL và không có giá trị mặc định khác.

Có thể khai báo đầy đủ kiểu, NULL, DEFAULT và comment:

~~~sql
ALTER TABLE customers
ADD COLUMN marketing_opt_in BOOLEAN NOT NULL DEFAULT FALSE
    COMMENT 'Khách hàng đồng ý nhận thông tin tiếp thị';
~~~

Trong MySQL, BOOLEAN là alias của TINYINT(1). Giá trị thường dùng là 0 và 1; nếu cần chỉ chấp nhận hai giá trị, có thể cân nhắc CHECK constraint ở phiên bản hỗ trợ thực thi.

### 2.2. Chọn vị trí cột

Có thể đặt cột ở đầu hoặc sau một cột khác:

~~~sql
ALTER TABLE customers
ADD COLUMN loyalty_code VARCHAR(40) AFTER email;

ALTER TABLE customers
ADD COLUMN external_ref VARCHAR(80) FIRST;
~~~

FIRST và AFTER chủ yếu ảnh hưởng thứ tự hiển thị trong metadata và kết quả SELECT *. Chúng không thay thế việc chỉ rõ danh sách cột trong truy vấn, và không tự làm truy vấn nhanh hơn. Ứng dụng nên truy vấn cột theo tên thay vì phụ thuộc thứ tự vật lý hoặc thứ tự SELECT *.

### 2.3. Thêm cột NOT NULL vào bảng đã có dữ liệu

Khi thêm cột NOT NULL, phải xác định giá trị cho các hàng hiện tại. Nếu không có DEFAULT phù hợp, thao tác có thể thất bại hoặc bị ảnh hưởng bởi SQL mode và khả năng hỗ trợ DDL của phiên bản.

Một cách triển khai thường dễ kiểm soát là thêm cột nullable trước:

~~~sql
ALTER TABLE customers
ADD COLUMN preferred_language VARCHAR(10) NULL;
~~~

Sau đó backfill dữ liệu theo quy tắc nghiệp vụ:

~~~sql
UPDATE customers
SET preferred_language = 'vi'
WHERE preferred_language IS NULL;
~~~

Khi đã xác minh không còn NULL, đổi cột thành NOT NULL:

~~~sql
ALTER TABLE customers
MODIFY COLUMN preferred_language VARCHAR(10) NOT NULL;
~~~

Với bảng lớn, không nên backfill toàn bộ trong một transaction dài. Hãy cập nhật theo lô dựa trên khóa chính, theo dõi lock, undo/redo, replication lag và tải hệ thống.

### 2.4. DEFAULT không tự thay dữ liệu cũ

DEFAULT được dùng khi INSERT không cung cấp giá trị cho cột (hoặc khi yêu cầu DEFAULT tường minh). Đổi DEFAULT không có nghĩa mọi hàng hiện có được cập nhật sang giá trị mới.

Ví dụ:

~~~sql
ALTER TABLE customers
ADD COLUMN account_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';
~~~

Các hàng cũ được xử lý theo quy tắc DDL và phiên bản MySQL. Trong nhiều trường hợp, giá trị mặc định được thể hiện khi đọc mà không cần ghi lại từng hàng, nhưng chi phí và khả năng instant phụ thuộc phiên bản cùng điều kiện bảng. Không nên suy luận rằng mọi thao tác thêm cột đều không rebuild bảng.

## 3. Đổi kiểu và thuộc tính bằng MODIFY COLUMN

MODIFY COLUMN thay đổi định nghĩa của cột nhưng giữ nguyên tên:

~~~sql
ALTER TABLE customers
MODIFY COLUMN full_name VARCHAR(200) NOT NULL;
~~~

Điểm quan trọng: MODIFY COLUMN yêu cầu khai báo lại đầy đủ các thuộc tính cần giữ, chẳng hạn kiểu dữ liệu, NULL/NOT NULL, DEFAULT, COMMENT, charset, collation và thuộc tính AUTO_INCREMENT nếu có. Không giả định các thuộc tính không viết ra sẽ tự động được giữ như mong muốn.

Ví dụ, nếu cột hiện tại là:

~~~sql
phone_number VARCHAR(30) NULL DEFAULT NULL
~~~

và muốn đổi sang bắt buộc nhập, cần ghi rõ:

~~~sql
ALTER TABLE customers
MODIFY COLUMN phone_number VARCHAR(30) NOT NULL;
~~~

Thao tác này chỉ thành công nếu dữ liệu hiện tại thỏa mãn định nghĩa mới. Nếu vẫn có NULL, phải xử lý chúng trước.

### 3.1. Tăng hoặc giảm độ dài chuỗi

Tăng độ dài VARCHAR thường ít rủi ro hơn giảm độ dài:

~~~sql
ALTER TABLE customers
MODIFY COLUMN full_name VARCHAR(200) NOT NULL;
~~~

Giảm độ dài:

~~~sql
ALTER TABLE customers
MODIFY COLUMN full_name VARCHAR(80) NOT NULL;
~~~

Trước khi giảm, hãy kiểm tra dữ liệu dài nhất:

~~~sql
SELECT
    MAX(CHAR_LENGTH(full_name)) AS max_characters,
    MAX(OCTET_LENGTH(full_name)) AS max_bytes
FROM customers;
~~~

CHAR_LENGTH đếm ký tự; OCTET_LENGTH đếm byte. Với utf8mb4, số byte có thể lớn hơn số ký tự. Dữ liệu vượt độ dài mới có thể làm DDL thất bại trong strict mode hoặc bị cắt và phát warning trong một số ngữ cảnh không strict. Không dựa vào việc MySQL tự cắt dữ liệu như một cách migration.

### 3.2. Đổi kiểu số

Ví dụ mở rộng INT sang BIGINT:

~~~sql
ALTER TABLE orders
MODIFY COLUMN order_number BIGINT UNSIGNED NOT NULL;
~~~

Trước khi đổi, cần xác minh:

- Giá trị hiện tại có nằm trong miền kiểu đích không?
- Kiểu signed/unsigned có tương thích với khóa ngoại và cột liên quan không?
- Index, generated column, view, trigger, routine hoặc ứng dụng có phụ thuộc kiểu cũ không?
- Connector có ánh xạ kiểu dữ liệu mới đúng không?

Đổi BIGINT UNSIGNED sang INT signed có thể làm mất khả năng biểu diễn các giá trị lớn hoặc số âm. Khi thay đổi kiểu của cột được tham chiếu bởi foreign key, cần xử lý quan hệ và thứ tự migration cẩn thận.

### 3.3. Đổi NULL và NOT NULL

Đổi từ nullable sang NOT NULL yêu cầu không còn hàng NULL:

~~~sql
SELECT COUNT(*) AS null_count
FROM customers
WHERE phone_number IS NULL;
~~~

Nếu kết quả lớn hơn 0, xác định cách xử lý từng nhóm dữ liệu rồi mới ALTER. Không tự gán chuỗi rỗng hoặc số 0 nếu chúng không có nghĩa tương đương NULL trong nghiệp vụ.

Đổi từ NOT NULL sang NULL:

~~~sql
ALTER TABLE customers
MODIFY COLUMN phone_number VARCHAR(30) NULL;
~~~

Thao tác này nới lỏng ràng buộc dữ liệu nhưng có thể làm ứng dụng cần xử lý thêm trường hợp NULL. Cần cập nhật validation và mapping ở tầng ứng dụng.

### 3.4. Đổi DEFAULT riêng biệt

Nếu chỉ cần đổi giá trị mặc định, có thể dùng ALTER COLUMN:

~~~sql
ALTER TABLE customers
ALTER COLUMN account_status SET DEFAULT 'PENDING';

ALTER TABLE customers
ALTER COLUMN account_status DROP DEFAULT;
~~~

Đổi DEFAULT không cập nhật các hàng hiện tại. Nếu muốn cập nhật dữ liệu cũ, thực hiện UPDATE riêng và đánh giá tác động transaction.

## 4. Đổi tên cột bằng RENAME COLUMN hoặc CHANGE COLUMN

### 4.1. RENAME COLUMN

MySQL 8.0 hỗ trợ RENAME COLUMN:

~~~sql
ALTER TABLE customers
RENAME COLUMN phone_number TO mobile_number;
~~~

Cú pháp này chỉ đổi tên cột, không yêu cầu khai báo lại kiểu dữ liệu.

### 4.2. CHANGE COLUMN

CHANGE COLUMN có thể đổi cả tên và định nghĩa:

~~~sql
ALTER TABLE customers
CHANGE COLUMN phone_number mobile_number VARCHAR(30) NULL;
~~~

CHANGE COLUMN phải khai báo tên mới và định nghĩa cột. Hãy ghi đầy đủ thuộc tính muốn giữ. Nếu bỏ sót DEFAULT, NULL, COMMENT hoặc charset/collation, định nghĩa sau migration có thể khác dự kiến.

### 4.3. Tác động đến ứng dụng và đối tượng phụ thuộc

Đổi tên cột có thể làm hỏng:

- SQL trong ứng dụng và báo cáo.
- View, trigger, stored procedure hoặc stored function.
- Job ETL, dashboard và script vận hành.
- ORM mapping, câu truy vấn native và migration tiếp theo.

MySQL có thể cập nhật một số metadata phụ thuộc trong các tình huống nhất định, nhưng không nên giả định mọi đoạn SQL động, ứng dụng hoặc công cụ bên ngoài đều được cập nhật. Với hệ thống đang chạy, chiến lược thêm cột mới, đồng bộ dữ liệu, chuyển ứng dụng và xóa cột cũ thường an toàn hơn đổi tên trực tiếp trong một bước.

## 5. Xóa cột bằng DROP COLUMN

Cú pháp:

~~~sql
ALTER TABLE customers
DROP COLUMN legacy_code;
~~~

DROP COLUMN loại bỏ định nghĩa cột và dữ liệu trong cột đó. Sau khi hoàn tất, không thể lấy lại dữ liệu chỉ bằng cách thêm cột cùng tên. Muốn khôi phục cần backup, snapshot hoặc nguồn dữ liệu khác.

Trước khi xóa, kiểm tra:

1. Ứng dụng còn đọc hoặc ghi cột không?
2. Có index, unique key, foreign key, CHECK, generated column hoặc biểu thức nào phụ thuộc cột không?
3. View, trigger, routine, báo cáo hoặc ETL có dùng cột không?
4. Có cần giữ dữ liệu để audit hoặc tương thích ngược không?
5. Backup và kế hoạch khôi phục đã được xác minh chưa?

Nếu cột thuộc index ghép, việc xóa có thể yêu cầu xử lý index đó. Nếu cột tham gia foreign key, phải xử lý constraint liên quan trước hoặc trong kế hoạch DDL phù hợp.

Không nên xóa cột ngay sau khi phát hành phiên bản ứng dụng mới. Hãy chờ các instance cũ, job nền và báo cáo đã ngừng sử dụng cột, sau đó mới thực hiện migration contract.

## 6. Thêm và xóa ràng buộc

Ràng buộc bảo vệ quy tắc dữ liệu ở database, kể cả khi có nhiều ứng dụng hoặc tiến trình cùng ghi vào bảng. MySQL với InnoDB hỗ trợ các ràng buộc phổ biến như PRIMARY KEY, UNIQUE, FOREIGN KEY và CHECK.

### 6.1. Thêm PRIMARY KEY

Nếu bảng chưa có khóa chính:

~~~sql
ALTER TABLE staging_orders
ADD CONSTRAINT pk_staging_orders PRIMARY KEY (staging_order_id);
~~~

Các cột của khóa chính phải NOT NULL. Bảng InnoDB chỉ có một PRIMARY KEY; khóa này được dùng làm clustered index. Nếu bảng chưa có primary key phù hợp, InnoDB có thể chọn unique index NOT NULL hoặc tạo hidden row ID nội bộ.

Trước khi thêm khóa chính, kiểm tra NULL và trùng lặp:

~~~sql
SELECT COUNT(*) AS null_keys
FROM staging_orders
WHERE staging_order_id IS NULL;

SELECT staging_order_id, COUNT(*) AS duplicate_count
FROM staging_orders
GROUP BY staging_order_id
HAVING COUNT(*) > 1;
~~~

Nếu có dữ liệu trùng hoặc NULL, phải giải quyết theo quy tắc nghiệp vụ trước. Thêm primary key trên bảng lớn cũng có thể cần xây dựng lại clustered index và tạo tải I/O đáng kể.

Xóa khóa chính:

~~~sql
ALTER TABLE staging_orders
DROP PRIMARY KEY;
~~~

Không thể xóa primary key nếu còn foreign key phụ thuộc hoặc cấu trúc khác yêu cầu khóa đó. Với InnoDB, bỏ primary key có thể khiến engine chọn clustered index khác hoặc tạo hidden row ID; đây thường không phải thay đổi nên thực hiện tùy tiện.

### 6.2. Thêm UNIQUE constraint

UNIQUE bảo đảm không có hai hàng trùng key theo quy tắc so sánh của index:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uq_customers_email UNIQUE (email);
~~~

Có thể tạo unique index trực tiếp:

~~~sql
ALTER TABLE customers
ADD UNIQUE INDEX uq_customers_email (email);
~~~

Trong MySQL, UNIQUE constraint được thực thi bằng unique index. Với cột cho phép NULL, unique index có thể chứa nhiều hàng có NULL vì NULL không được xem là bằng một giá trị NULL khác trong phép kiểm tra unique thông thường. Nếu nghiệp vụ yêu cầu mỗi hàng phải có email duy nhất và bắt buộc nhập, hãy kết hợp NOT NULL với UNIQUE.

Kiểm tra dữ liệu trước khi thêm:

~~~sql
SELECT email, COUNT(*) AS duplicate_count
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Collation của cột ảnh hưởng phép so sánh. Với collation không phân biệt hoa thường, hai email khác chữ hoa/thường có thể bị xem là trùng. Cần chọn collation phù hợp với quy tắc định danh của ứng dụng.

Xóa unique index:

~~~sql
ALTER TABLE customers
DROP INDEX uq_customers_email;
~~~

MySQL dùng DROP INDEX để xóa unique index được tạo từ UNIQUE constraint. Nếu có đối tượng phụ thuộc, xử lý theo quan hệ trước khi xóa.

### 6.3. Thêm FOREIGN KEY

Foreign key bảo đảm giá trị ở bảng con tham chiếu đến một hàng tồn tại ở bảng cha, hoặc là NULL nếu cột cho phép và quy tắc cho phép.

Ví dụ:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers (customer_id)
ON UPDATE RESTRICT
ON DELETE RESTRICT;
~~~

Trước khi thêm foreign key, kiểm tra:

- Hai bảng dùng storage engine hỗ trợ foreign key, thường là InnoDB.
- Cột con và cột được tham chiếu có kiểu tương thích; với số nguyên, kích thước và signed/unsigned phải phù hợp.
- Cột được tham chiếu có index phù hợp, thường là PRIMARY KEY hoặc UNIQUE KEY.
- Cột ở bảng con có index cần thiết; InnoDB có thể tự tạo index nếu chưa có index phù hợp.
- Không có hàng mồ côi ở bảng con.
- Charset và collation tương thích nếu khóa ngoại dùng cột chuỗi.

Tìm hàng mồ côi trước khi thêm:

~~~sql
SELECT o.order_id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

Nếu có hàng mồ côi, hãy quyết định sửa khóa, thêm bản ghi cha hợp lệ hoặc loại bỏ dữ liệu theo quy trình được phê duyệt. Không xóa hàng chỉ để migration chạy thành công.

### 6.4. ON DELETE và ON UPDATE

Các hành động tham chiếu xác định cách xử lý khi khóa cha bị thay đổi:

| Hành động | Ý nghĩa |
|---|---|
| RESTRICT | Từ chối thay đổi ở bảng cha nếu còn hàng con tham chiếu |
| NO ACTION | Trong InnoDB, hành vi tương đương RESTRICT |
| CASCADE | Lan truyền thao tác xóa hoặc cập nhật khóa sang hàng con |
| SET NULL | Đặt cột khóa ngoại ở hàng con thành NULL; cột con phải cho phép NULL |

Ví dụ:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers (customer_id)
ON DELETE CASCADE;
~~~

ON DELETE CASCADE có thể xóa nhiều hàng đơn hàng khi xóa một khách hàng. Chỉ dùng khi vòng đời dữ liệu thực sự yêu cầu điều đó; với dữ liệu tài chính hoặc audit, thường cần chính sách lưu trữ và xóa mềm riêng.

### 6.5. Xóa FOREIGN KEY

~~~sql
ALTER TABLE orders
DROP FOREIGN KEY fk_orders_customer;
~~~

DROP FOREIGN KEY xóa ràng buộc tham chiếu. Index hỗ trợ cột customer_id có thể vẫn còn sau khi bỏ foreign key vì index có thể phục vụ truy vấn khác. Nếu muốn xóa index, kiểm tra nó không còn cần thiết và không bị constraint khác sử dụng rồi mới DROP INDEX.

### 6.6. Thêm CHECK constraint

CHECK kiểm tra một biểu thức cho mỗi hàng khi INSERT hoặc UPDATE:

~~~sql
ALTER TABLE products
ADD CONSTRAINT chk_products_price
CHECK (price >= 0);
~~~

Ví dụ khác:

~~~sql
ALTER TABLE bookings
ADD CONSTRAINT chk_booking_period
CHECK (ends_at > starts_at);
~~~

MySQL bắt đầu thực thi CHECK constraint từ phiên bản 8.0.16. Các bản MySQL trước 8.0.16 có thể chấp nhận cú pháp CHECK nhưng bỏ qua việc thực thi constraint. Vì vậy, khi làm việc với phiên bản cũ, không được dựa vào CHECK để bảo vệ dữ liệu.

CHECK chỉ chấp nhận hàng khi biểu thức không FALSE; kết quả UNKNOWN do NULL không làm constraint thất bại. Nếu cột bắt buộc phải có giá trị, hãy kết hợp NOT NULL.

Xóa CHECK:

~~~sql
ALTER TABLE products
DROP CHECK chk_products_price;
~~~

Tên constraint nên rõ nghĩa và ổn định để migration có thể tham chiếu chính xác.

## 7. Thay đổi index liên quan đến cột

Thêm index:

~~~sql
ALTER TABLE orders
ADD INDEX idx_orders_status_created (status, created_at);
~~~

Thêm unique index:

~~~sql
ALTER TABLE customers
ADD UNIQUE INDEX uq_customers_external_ref (external_ref);
~~~

Đổi tên index:

~~~sql
ALTER TABLE orders
RENAME INDEX idx_orders_status_created
TO idx_orders_status_time;
~~~

Xóa index:

~~~sql
ALTER TABLE orders
DROP INDEX idx_orders_status_time;
~~~

Không nên xóa index chỉ vì không thấy nó trong một truy vấn. Hãy xem xét workload tổng thể, index usage, kế hoạch truy vấn, foreign key và chi phí ghi. Một index phụ có thể không được dùng bởi truy vấn đang kiểm tra nhưng vẫn phục vụ job hoặc báo cáo khác.

## 8. Thực hiện nhiều thay đổi trong một ALTER TABLE

MySQL cho phép kết hợp nhiều alter option trong một câu lệnh:

~~~sql
ALTER TABLE customers
    ADD COLUMN preferred_language VARCHAR(10) NULL,
    ADD COLUMN marketing_opt_in BOOLEAN NOT NULL DEFAULT FALSE,
    ADD INDEX idx_customers_created_at (created_at);
~~~

Gộp các thao tác có thể giúp tránh nhiều lần xử lý bảng, nhưng thuật toán DDL phải đáp ứng tất cả các thay đổi trong câu lệnh. Nếu một thao tác yêu cầu COPY, toàn bộ ALTER có thể phải dùng thuật toán tốn kém hơn.

Khi thay đổi có rủi ro hoặc yêu cầu thuật toán online khác nhau, tách thành nhiều migration giúp dễ kiểm soát, đo tác động và khôi phục. Không có quy tắc rằng một ALTER lớn luôn nhanh hơn nhiều ALTER nhỏ; cần dựa vào cấu trúc bảng, phiên bản và thử nghiệm.

## 9. ALGORITHM và LOCK trong DDL

### 9.1. Các thuật toán chính

ALTER TABLE có thể sử dụng các thuật toán:

| Algorithm | Ý nghĩa tổng quát |
|---|---|
| INSTANT | Thay đổi metadata trong các thao tác được hỗ trợ; tránh rebuild dữ liệu bảng |
| INPLACE | Storage engine thực hiện thay đổi mà không nhất thiết tạo bản sao bảng đầy đủ; vẫn có thể rebuild hoặc tạo index |
| COPY | Tạo bản sao bảng mới, sao chép dữ liệu rồi thay thế bảng cũ; thường tốn I/O và thời gian hơn |

Tên INPLACE không có nghĩa thao tác không ghi lại dữ liệu. Một số thao tác INPLACE vẫn rebuild clustered index hoặc tạo lại index. INSTANT cũng chỉ được hỗ trợ cho một tập thao tác và điều kiện cụ thể.

Ví dụ yêu cầu MySQL chỉ thực hiện nếu hỗ trợ INSTANT:

~~~sql
ALTER TABLE customers
ADD COLUMN profile_note VARCHAR(200) NULL,
ALGORITHM=INSTANT;
~~~

Nếu server không thể thực hiện bằng INSTANT, câu lệnh sẽ báo lỗi thay vì tự chuyển sang thuật toán khác. Đây là cách hữu ích để tránh vô tình chạy một thao tác COPY nặng trên bảng lớn.

### 9.2. LOCK

Tùy chọn LOCK kiểm soát mức độ cho phép truy cập đồng thời trong quá trình DDL:

| Lock | Ý nghĩa tổng quát |
|---|---|
| DEFAULT | Để MySQL chọn mức khóa phù hợp |
| NONE | Cho phép đọc và ghi đồng thời trong giai đoạn hỗ trợ online |
| SHARED | Cho phép đọc nhưng chặn ghi trong giai đoạn tương ứng |
| EXCLUSIVE | Chặn truy cập đồng thời theo mức khóa độc quyền |

Ví dụ:

~~~sql
ALTER TABLE orders
ADD INDEX idx_orders_created_at (created_at),
ALGORITHM=INPLACE,
LOCK=NONE;
~~~

Nếu thao tác hoặc engine không hỗ trợ tổ hợp yêu cầu, MySQL trả lỗi. Không nên bỏ tùy chọn rồi mặc định rằng DDL sẽ không khóa ứng dụng.

### 9.3. Online DDL vẫn cần metadata lock

Ngay cả khi DDL hỗ trợ LOCK=NONE, MySQL vẫn cần metadata lock ở các giai đoạn nhất định, đặc biệt khi bắt đầu và hoàn tất thay đổi. Một transaction dài đang giữ metadata lock trên bảng có thể khiến ALTER TABLE phải chờ. Khi DDL chờ metadata lock, các truy vấn tiếp theo cũng có thể bị xếp hàng phía sau.

Trước migration:

- Kiểm tra transaction dài và session đang giữ metadata lock.
- Tránh chạy DDL đúng giờ cao điểm.
- Đặt thời gian chờ phù hợp và theo dõi processlist.
- Chuẩn bị cách dừng hoặc hủy migration nếu thời gian chờ vượt ngưỡng vận hành.

Không nên hiểu “online” là hoàn toàn không gây ảnh hưởng. DDL vẫn tiêu thụ CPU, I/O, redo/undo, dung lượng tạm và có thể làm tăng replication lag.

## 10. DDL và transaction

ALTER TABLE là DDL và gây implicit commit trong MySQL. Không thể dựa vào ROLLBACK của transaction ứng dụng để hoàn tác một ALTER TABLE đã thực hiện.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE customers
SET account_status = 'ACTIVE'
WHERE customer_id = 42;

ALTER TABLE customers
ADD COLUMN source_channel VARCHAR(30) NULL;

ROLLBACK;
~~~

ALTER TABLE có thể commit transaction đang mở trước khi thực hiện. Vì vậy, UPDATE trước đó có thể đã được commit; ROLLBACK sau ALTER không hoàn tác được DDL và cũng không hoàn tác phần đã được implicit commit.

MySQL 8.0 hỗ trợ atomic DDL cho nhiều thao tác và storage engine được hỗ trợ: nếu server gặp sự cố trong lúc thực hiện, thao tác DDL được phục hồi theo trạng thái hoàn tất hoặc chưa hoàn tất một cách nhất quán. Atomic DDL không đồng nghĩa DDL có thể rollback bằng lệnh ROLLBACK của người dùng.

Hãy tách DDL và thay đổi dữ liệu backfill thành các bước migration riêng. Thiết kế rollback dưới dạng migration bù hoặc phục hồi backup/snapshot, không giả định transaction bao trùm có thể đảo ngược ALTER TABLE.

## 11. Chiến lược migration an toàn cho bảng đang hoạt động

Với bảng nhỏ và thay đổi đơn giản, một ALTER TABLE có thể đủ. Với bảng lớn hoặc ứng dụng không thể dừng, nên triển khai theo mô hình expand-migrate-contract.

### 11.1. Expand: mở rộng schema

Thêm cột mới theo cách tương thích ngược, thường cho phép NULL hoặc có DEFAULT an toàn:

~~~sql
ALTER TABLE customers
ADD COLUMN display_name VARCHAR(200) NULL;
~~~

Ứng dụng cũ vẫn hoạt động vì cột cũ chưa bị xóa và cột mới chưa bắt buộc.

### 11.2. Migrate: đồng bộ và backfill dữ liệu

Triển khai ứng dụng mới có thể đọc cả cột cũ lẫn cột mới, hoặc ghi đồng thời hai cột trong giai đoạn chuyển tiếp. Backfill theo lô:

~~~sql
UPDATE customers
SET display_name = full_name
WHERE customer_id > ?
  AND customer_id <= ?
  AND display_name IS NULL;
~~~

Sau mỗi lô, kiểm tra số hàng cập nhật và lỗi. Dùng khoảng khóa chính có giới hạn để tránh transaction quá lớn. Với dữ liệu thay đổi liên tục, cần xử lý đồng bộ các hàng được cập nhật trong lúc backfill.

### 11.3. Contract: bỏ cấu trúc cũ

Sau khi tất cả instance ứng dụng đã chuyển sang cột mới, xác nhận không còn truy vấn, job hoặc báo cáo phụ thuộc cột cũ. Khi đó mới xóa cột:

~~~sql
ALTER TABLE customers
DROP COLUMN full_name;
~~~

Giai đoạn contract có tính phá hủy. Cần có backup hoặc khả năng tái tạo dữ liệu trước khi thực hiện.

## 12. Ví dụ migration hoàn chỉnh: thêm và bắt buộc email

Giả sử bảng customers đang có cột email nullable và muốn bảo đảm mọi khách hàng đều có email duy nhất.

**Bước 1: Kiểm tra dữ liệu hiện tại**

~~~sql
SELECT COUNT(*) AS null_email_count
FROM customers
WHERE email IS NULL;

SELECT email, COUNT(*) AS duplicate_count
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

**Bước 2: Xử lý dữ liệu theo quy tắc nghiệp vụ**

Không tự tạo email giả để lấp dữ liệu thiếu nếu hệ thống chưa định nghĩa cách đó. Hãy yêu cầu bổ sung dữ liệu, đánh dấu trạng thái hoặc xử lý các bản ghi ngoại lệ.

**Bước 3: Thêm unique index**

~~~sql
ALTER TABLE customers
ADD UNIQUE INDEX uq_customers_email (email);
~~~

**Bước 4: Đổi cột thành NOT NULL**

~~~sql
ALTER TABLE customers
MODIFY COLUMN email VARCHAR(255) NOT NULL;
~~~

Trước khi chạy, xác minh lại định nghĩa cột ban đầu để giữ đúng charset, collation, comment và các thuộc tính khác. Cần cân nhắc thứ tự thao tác theo yêu cầu ứng dụng và khả năng DDL của phiên bản.

**Bước 5: Xác minh**

~~~sql
SHOW CREATE TABLE customers\G
SHOW INDEX FROM customers;

SELECT COUNT(*) AS null_email_count
FROM customers
WHERE email IS NULL;
~~~

Migration chỉ hoàn tất khi cấu trúc và dữ liệu đều thỏa mãn quy tắc mới.

## 13. Kiểm tra tác động và theo dõi sau ALTER TABLE

Trước và sau DDL, ghi nhận:

- Số hàng, kích thước bảng và index.
- Engine, charset, collation và định nghĩa cột.
- Thời gian thực thi và thời gian chờ metadata lock.
- CPU, I/O, dung lượng trống và temporary disk usage.
- Replication lag và trạng thái replica.
- Lỗi ứng dụng, timeout và số kết nối đang chờ.

Một số câu lệnh kiểm tra:

~~~sql
SHOW CREATE TABLE shop.orders\G
SHOW INDEX FROM shop.orders;
SHOW TABLE STATUS FROM shop LIKE 'orders'\G

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
~~~

Có thể quan sát process đang chạy:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Để điều tra metadata lock sâu hơn, dùng Performance Schema và các view phù hợp của sys schema nếu được bật. Quyền truy cập và cấu trúc view phụ thuộc phiên bản MySQL.

## 14. Những lỗi thường gặp

### 14.1. Data truncated hoặc out of range

Nguyên nhân thường là kiểu đích hẹp hơn dữ liệu hiện tại, precision không đủ, signed/unsigned không phù hợp hoặc chuỗi vượt độ dài. Kiểm tra dữ liệu trước khi ALTER, chuyển đổi theo lô nếu cần và xác minh SQL mode.

### 14.2. Cannot add or update a child row

Khi thêm foreign key, MySQL phát hiện hàng con tham chiếu đến hàng cha không tồn tại. Tìm orphan rows, sửa dữ liệu theo nghiệp vụ rồi thử lại.

### 14.3. Duplicate entry

Khi thêm PRIMARY KEY hoặc UNIQUE, dữ liệu hiện tại có giá trị trùng. Tìm nhóm trùng bằng GROUP BY, quyết định bản ghi nào cần hợp nhất hoặc sửa trước khi thêm constraint.

### 14.4. Lock wait hoặc metadata lock

DDL có thể chờ transaction khác. Kiểm tra processlist, transaction dài và metadata lock; chọn thời điểm triển khai phù hợp. Không kết thúc session tùy tiện nếu chưa hiểu transaction đó đang làm gì.

### 14.5. DDL chạy lâu hoặc đầy đĩa

Thao tác COPY hoặc rebuild index có thể tạo bản sao dữ liệu và cần thêm dung lượng tạm. Kiểm tra dung lượng, I/O, kích thước bảng, replication và cửa sổ bảo trì trước khi chạy. Với bảng rất lớn, đánh giá công cụ online schema change nếu DDL gốc không đáp ứng yêu cầu downtime.

## 15. Checklist trước khi phát hành migration

1. Đã đọc SHOW CREATE TABLE và xác nhận đúng schema đích.
2. Đã xác định cột, index, constraint và đối tượng phụ thuộc.
3. Đã đo số hàng, giá trị NULL, dữ liệu trùng và giá trị vượt miền.
4. Đã kiểm tra SQL mode, phiên bản MySQL và storage engine.
5. Đã xác định ALGORITHM/LOCK mà thao tác có thể dùng.
6. Đã thử trên bản sao dữ liệu có kích thước đại diện.
7. Đã dự tính thời gian, I/O, dung lượng tạm và replication lag.
8. Đã có backup hoặc snapshot và phương án phục hồi.
9. Đã triển khai ứng dụng theo thứ tự tương thích ngược khi cần.
10. Đã xác minh DDL, dữ liệu và truy vấn sau migration.

## 16. Những nhầm lẫn thường gặp

**“ALTER TABLE luôn chạy tức thời.”** Không. Tùy thao tác, MySQL có thể chỉ thay metadata, rebuild index hoặc sao chép toàn bộ bảng.

**“ALGORITHM=INPLACE có nghĩa không rebuild dữ liệu.”** Không. INPLACE vẫn có thể rebuild clustered index hoặc thực hiện công việc lớn bên trong storage engine.

**“LOCK=NONE có nghĩa không có khóa nào.”** Không. Online DDL vẫn cần metadata lock ở các giai đoạn nhất định và có thể chờ transaction dài.

**“Đổi DEFAULT sẽ cập nhật tất cả hàng cũ.”** Không. DEFAULT chủ yếu áp dụng cho lần INSERT sau; UPDATE dữ liệu cũ là thao tác riêng.

**“MODIFY COLUMN chỉ cần viết kiểu dữ liệu mới.”** Không. Phải khai báo lại các thuộc tính muốn giữ như NULL, DEFAULT, charset, collation và comment.

**“DROP COLUMN có thể rollback bằng ROLLBACK.”** Không. ALTER TABLE gây implicit commit; khôi phục dữ liệu cần backup hoặc migration bù.

**“Thêm CHECK luôn được thực thi trên mọi MySQL.”** Không. MySQL chỉ thực thi CHECK constraint từ 8.0.16.

**“Thêm FOREIGN KEY chỉ cần hai cột cùng tên.”** Không. Cần kiểu tương thích, index phù hợp, engine hỗ trợ và dữ liệu hiện tại không có hàng mồ côi.

## Kết luận

ALTER TABLE cho phép tiến hóa schema bằng cách thêm, đổi tên, sửa và xóa cột; đồng thời thêm hoặc loại bỏ PRIMARY KEY, UNIQUE, FOREIGN KEY, CHECK và index. Mỗi thay đổi đều cần xét dữ liệu hiện tại, kiểu đích, các đối tượng phụ thuộc và khả năng DDL của phiên bản MySQL.

Với bảng đang hoạt động, hãy ưu tiên migration tương thích ngược, backfill theo lô và chỉ xóa cấu trúc cũ sau khi ứng dụng đã chuyển hoàn toàn. Phân biệt INSTANT, INPLACE và COPY; hiểu rằng online DDL vẫn có metadata lock và ALTER TABLE không thể rollback bằng transaction thông thường. Kiểm tra trước và sau migration giúp bảo vệ tính toàn vẹn dữ liệu và duy trì hoạt động của hệ thống MySQL.
