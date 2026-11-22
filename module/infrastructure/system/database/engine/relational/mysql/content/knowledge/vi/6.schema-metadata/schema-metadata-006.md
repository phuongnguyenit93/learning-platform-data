# SHOW CREATE TABLE, SHOW INDEX và SHOW TABLE STATUS

Khi làm việc với MySQL, biết tên bảng và các cột là chưa đủ để hiểu cấu trúc thật sự của một bảng. Một bảng còn có kiểu dữ liệu, giá trị mặc định, khóa chính, khóa ngoại, ràng buộc, chỉ mục, storage engine, collation và nhiều tùy chọn lưu trữ khác. Những thông tin này ảnh hưởng trực tiếp đến tính toàn vẹn dữ liệu, cách truy vấn được thực thi và khả năng vận hành cơ sở dữ liệu.

MySQL cung cấp ba lệnh thường dùng để kiểm tra nhanh metadata của bảng:

- **SHOW CREATE TABLE** hiển thị câu lệnh DDL mô tả cách bảng được định nghĩa.
- **SHOW INDEX** hiển thị các chỉ mục của bảng và những thuộc tính của từng key part.
- **SHOW TABLE STATUS** hiển thị thông tin tổng quan về bảng và storage engine.

Ba lệnh này bổ trợ cho nhau. Khi điều tra một truy vấn chậm, có thể dùng SHOW CREATE TABLE để hiểu cấu trúc và ràng buộc, SHOW INDEX để kiểm tra các chỉ mục hiện có, rồi dùng SHOW TABLE STATUS để xem engine, ước lượng kích thước và một số thống kê lưu trữ. Kết quả cần được đọc đúng giới hạn: metadata mô tả cấu trúc và trạng thái quan sát được, không tự chứng minh một kế hoạch truy vấn là tối ưu.

Bài viết tập trung vào MySQL 8.x với InnoDB là storage engine phổ biến.

## 1. Chuẩn bị một bảng để thực hành

Giả sử hệ thống bán hàng có bảng khách hàng và bảng đơn hàng:

~~~sql
CREATE DATABASE IF NOT EXISTS shop;
USE shop;

CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email       VARCHAR(255) NOT NULL,
    full_name   VARCHAR(150) NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE orders (
    order_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status      VARCHAR(30) NOT NULL,
    total       DECIMAL(13, 2) NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (customer_id, created_at),
    KEY idx_orders_status_created (status, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
~~~

Ví dụ này có các thành phần cần kiểm tra:

- Khóa chính tự tăng cho mỗi bảng.
- Ràng buộc UNIQUE bảo đảm email không trùng.
- Khóa ngoại liên kết đơn hàng với khách hàng.
- Hai chỉ mục ghép phục vụ các mẫu truy vấn khác nhau.
- DECIMAL lưu giá trị tiền tệ với độ chính xác thập phân.
- utf8mb4 và collation xác định cách lưu, so sánh và sắp xếp chuỗi.

Sau khi tạo bảng, ta có thể dùng ba lệnh SHOW để xem MySQL đang ghi nhận cấu trúc và thông tin lưu trữ như thế nào.

## 2. SHOW CREATE TABLE: xem định nghĩa DDL của bảng

### 2.1. Cú pháp và cách dùng

SHOW CREATE TABLE trả về câu lệnh CREATE TABLE mà MySQL dùng để mô tả bảng hiện tại.

~~~sql
SHOW CREATE TABLE orders;
~~~

Nếu chưa chọn database mặc định, chỉ rõ schema:

~~~sql
SHOW CREATE TABLE shop.orders;
~~~

Trong MySQL client, có thể dùng \G để trình bày kết quả theo chiều dọc, giúp đọc DDL dài dễ hơn:

~~~sql
SHOW CREATE TABLE shop.orders\G
~~~

Kết quả thường có hai cột:

| Cột | Ý nghĩa |
|---|---|
| Table | Tên bảng |
| Create Table | Câu lệnh DDL mô tả cấu trúc bảng |

Giá trị Create Table có thể gồm tên cột, kiểu dữ liệu, NULL/NOT NULL, DEFAULT, AUTO_INCREMENT, khóa chính, chỉ mục, ràng buộc, engine, charset, collation, comment, partition và các tùy chọn liên quan nếu có.

### 2.2. Đọc các thành phần trong kết quả

Ví dụ rút gọn về hình dạng kết quả:

~~~sql
CREATE TABLE orders (
  order_id bigint unsigned NOT NULL AUTO_INCREMENT,
  customer_id bigint unsigned NOT NULL,
  status varchar(30) NOT NULL,
  total decimal(13,2) NOT NULL,
  created_at datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (order_id),
  KEY idx_orders_customer_created (customer_id,created_at),
  KEY idx_orders_status_created (status,created_at),
  CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES customers (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;
~~~

Đây là ví dụ minh họa nội dung chính; định dạng thực tế có thể khác theo phiên bản, cấu hình và thuộc tính bảng.

Khi đọc DDL, nên kiểm tra lần lượt:

1. **Cột và kiểu dữ liệu:** có đúng kiểu, độ dài, precision và scale cần thiết không?
2. **NULL và DEFAULT:** cột nào bắt buộc, cột nào có giá trị mặc định, có dùng biểu thức mặc định hay không?
3. **Khóa chính:** bảng có khóa chính phù hợp và ổn định không?
4. **UNIQUE và khóa ngoại:** các quy tắc nghiệp vụ và quan hệ có được thể hiện trong schema không?
5. **Chỉ mục:** tên, thứ tự cột và loại index có phù hợp với truy vấn không?
6. **Engine:** bảng có dùng InnoDB như dự kiến không?
7. **Charset và collation:** chuỗi có dùng bộ ký tự và quy tắc so sánh phù hợp không?
8. **Tùy chọn khác:** comment, row format, partition, generated column hoặc các thuộc tính đặc biệt có được khai báo đúng không?

### 2.3. SHOW CREATE TABLE không phải bản sao nguyên văn script ban đầu

MySQL có thể chuẩn hóa cách biểu diễn DDL khi trả kết quả. Vì vậy, SHOW CREATE TABLE hữu ích để biết định nghĩa mà server đang áp dụng, nhưng không nhất thiết khôi phục đúng từng ký tự của file migration hoặc script đã dùng ban đầu.

Một số điểm cần lưu ý:

- Khoảng trắng, cách viết hoa/thường và cách hiển thị identifier có thể khác.
- Giá trị mặc định hoặc thuộc tính có thể được thể hiện theo cách chuẩn hóa của server.
- Một số tùy chọn ngầm định có thể được biểu diễn trong kết quả.
- DDL phụ thuộc phiên bản server; câu lệnh tạo lại trên phiên bản khác có thể cần điều chỉnh.

Do đó, hãy dùng kết quả để kiểm tra cấu trúc hiện tại và hỗ trợ tạo migration có kiểm soát. Nếu cần lưu lịch sử thay đổi schema, hãy quản lý migration trong hệ thống version control thay vì coi đầu ra SHOW là lịch sử thay đổi.

### 2.4. Quyền truy cập và phạm vi metadata

Người dùng cần có quyền phù hợp để xem metadata của đối tượng. Trong môi trường nhiều schema, kết quả quan sát được có thể bị giới hạn bởi quyền của tài khoản hiện tại. Nếu không thấy đối tượng hoặc không lấy được định nghĩa, hãy kiểm tra database mặc định, tên schema, tên bảng và quyền truy cập.

Không nên dùng tài khoản root chỉ để đọc cấu trúc bảng trong ứng dụng hoặc công cụ nội bộ. Hãy cấp quyền quản trị schema hoặc quyền đọc metadata cần thiết theo vai trò vận hành.

## 3. SHOW INDEX: kiểm tra các chỉ mục

### 3.1. Cú pháp

Để xem tất cả chỉ mục của một bảng:

~~~sql
SHOW INDEX FROM orders;
~~~

Chỉ rõ database:

~~~sql
SHOW INDEX FROM orders FROM shop;
~~~

SHOW KEYS là tên đồng nghĩa thường gặp:

~~~sql
SHOW KEYS FROM shop.orders;
~~~

Có thể lọc kết quả theo tên index hoặc thuộc tính khác bằng mệnh đề WHERE:

~~~sql
SHOW INDEX FROM shop.orders
WHERE Key_name = 'idx_orders_customer_created';
~~~

### 3.2. Các cột quan trọng trong kết quả

SHOW INDEX trả về một hàng cho mỗi key part của chỉ mục. Với index ghép gồm nhiều cột, một index sẽ xuất hiện trên nhiều hàng.

| Cột | Ý nghĩa |
|---|---|
| Table | Tên bảng |
| Non_unique | 0 nếu index được khai báo unique; 1 nếu index cho phép giá trị trùng |
| Key_name | Tên chỉ mục; PRIMARY là khóa chính |
| Seq_in_index | Vị trí của key part trong chỉ mục, bắt đầu từ 1 |
| Column_name | Tên cột của key part; có thể NULL với key part dựa trên biểu thức |
| Collation | Hướng sắp xếp key part, thường là A hoặc D; có thể NULL nếu không áp dụng |
| Cardinality | Ước lượng số giá trị phân biệt của index hoặc key prefix |
| Sub_part | Độ dài prefix được đánh chỉ mục nếu có |
| Null | Cho biết key part có thể chứa NULL hay không |
| Index_type | Loại chỉ mục, chẳng hạn BTREE |
| Comment | Thông tin bổ sung của index |
| Index_comment | Comment do người tạo index khai báo |
| Visible | Cho biết index có hiển thị với optimizer hay không trong các phiên bản hỗ trợ invisible index |
| Expression | Biểu thức được dùng làm key part với functional index trong các phiên bản hỗ trợ |

Không phải mọi phiên bản đều trả về chính xác cùng tập cột. Hãy xem tài liệu của phiên bản MySQL đang vận hành khi viết script tự động đọc kết quả.

Với unique index trên cột cho phép NULL, MySQL vẫn có thể chấp nhận nhiều hàng có giá trị NULL. Vì vậy, Non_unique = 0 mô tả thuộc tính unique của index, nhưng khi kiểm tra quy tắc dữ liệu cần xem thêm khả năng NULL của các cột.

### 3.3. Đọc một index đơn

Với khóa chính:

~~~sql
SHOW INDEX FROM shop.orders
WHERE Key_name = 'PRIMARY';
~~~

Với chỉ mục ghép:

~~~sql
SHOW INDEX FROM shop.orders
WHERE Key_name = 'idx_orders_customer_created';
~~~

Nếu index gồm (customer_id, created_at), kết quả sẽ có hai key part:

| Seq_in_index | Column_name |
|---:|---|
| 1 | customer_id |
| 2 | created_at |

Thứ tự này có ý nghĩa. B-tree index ghép thường hỗ trợ hiệu quả các điều kiện bắt đầu từ cột bên trái, gọi là quy tắc leftmost prefix. Index (customer_id, created_at) có thể hỗ trợ lọc theo customer_id, hoặc lọc theo customer_id kết hợp điều kiện thời gian. Nó thường không thay thế một index chỉ có created_at cho truy vấn chỉ lọc theo created_at.

Ví dụ:

~~~sql
-- Có thể tận dụng leftmost prefix của index
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42;

-- Có thể dùng cả hai key part
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01';

-- Không thể chỉ dựa vào leftmost prefix để kết luận index trên sẽ phù hợp
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2026-01-01';
~~~

Optimizer vẫn quyết định kế hoạch dựa trên thống kê và chi phí. Quy tắc leftmost prefix giúp hiểu khả năng cấu trúc của index, không bảo đảm index luôn được chọn.

### 3.4. Cardinality là giá trị ước lượng

Cardinality thường là ước lượng số giá trị phân biệt của index hoặc key prefix. InnoDB dùng thống kê chỉ mục để optimizer ước lượng độ chọn lọc và chi phí kế hoạch.

Không nên coi cardinality là số đếm chính xác tại thời điểm truy vấn. Giá trị có thể thay đổi sau khi dữ liệu biến động hoặc sau khi thống kê được cập nhật. Nếu nghi ngờ thống kê cũ, có thể xem xét:

~~~sql
ANALYZE TABLE shop.orders;
~~~

ANALYZE TABLE cập nhật thống kê của bảng và chỉ mục theo cơ chế của storage engine. Đây là thao tác quản trị có tác động đến hoạt động server, nên cần cân nhắc tải và môi trường trước khi chạy trên hệ thống sản xuất.

### 3.5. Prefix index, functional index và invisible index

Sub_part cho biết độ dài prefix được lập chỉ mục trong những trường hợp có dùng prefix index. Ví dụ, với cột chuỗi dài, một index có thể chỉ lập chỉ mục một phần đầu của giá trị:

~~~sql
CREATE INDEX idx_customer_email_prefix
ON customers (email(32));
~~~

Prefix index có thể giảm kích thước index nhưng không lưu toàn bộ giá trị cột trong key part. Nó không phù hợp cho mọi truy vấn. Nếu tạo unique prefix index, tính duy nhất được kiểm tra trên phần prefix được lập chỉ mục; cách này không thay thế ràng buộc UNIQUE trên toàn bộ giá trị trong mọi trường hợp.

MySQL 8.0.13 trở lên hỗ trợ functional key parts. Ví dụ:

~~~sql
CREATE INDEX idx_customer_email_lower
ON customers ((LOWER(email)));
~~~

Trong kết quả SHOW INDEX, cột Expression có thể cho biết biểu thức được lập chỉ mục. Cú pháp và khả năng hỗ trợ phụ thuộc phiên bản.

MySQL 8.0 cũng hỗ trợ invisible index. Một index invisible vẫn được duy trì khi dữ liệu thay đổi nhưng optimizer bỏ qua nó theo mặc định. Thuộc tính Visible trong kết quả SHOW INDEX giúp kiểm tra trạng thái này. Invisible index có thể hỗ trợ thử nghiệm tác động của việc bỏ một index trước khi xóa hẳn, nhưng cần kiểm tra mọi workload trước khi quyết định.

### 3.6. SHOW INDEX không cho biết index có thực sự được dùng

Lệnh này mô tả index tồn tại và thuộc tính của nó. Nó không cho biết câu truy vấn cụ thể có chọn index đó hay không, cũng không đo được số hàng thực tế phải đọc.

Để kiểm tra kế hoạch truy vấn:

~~~sql
EXPLAIN
SELECT order_id, status, created_at
FROM shop.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
~~~

Trong MySQL 8.0.18 trở lên, EXPLAIN ANALYZE thực thi câu SELECT và bổ sung số liệu thực tế về iterator. Chỉ dùng khi có thể chấp nhận truy vấn chạy thật trên dữ liệu hiện tại và tạo tải tương ứng.

## 4. SHOW TABLE STATUS: xem trạng thái tổng quan của bảng

### 4.1. Cú pháp

Xem các bảng trong database hiện tại:

~~~sql
SHOW TABLE STATUS;
~~~

Chỉ định database và lọc theo tên:

~~~sql
SHOW TABLE STATUS FROM shop LIKE 'orders';
~~~

Hoặc dùng mệnh đề WHERE:

~~~sql
SHOW TABLE STATUS FROM shop
WHERE Name IN ('customers', 'orders');
~~~

Mệnh đề LIKE hỗ trợ ký tự đại diện % và _. Ví dụ LIKE 'order%' tìm tên bắt đầu bằng order.

### 4.2. Các cột thường gặp

Kết quả SHOW TABLE STATUS trả một hàng cho mỗi bảng được liệt kê. Các cột thường gặp gồm:

| Cột | Ý nghĩa |
|---|---|
| Name | Tên bảng |
| Engine | Storage engine của bảng, ví dụ InnoDB |
| Version | Trường phiên bản định dạng nội bộ mang tính tương thích; thường không phải thông tin cần dùng trong ứng dụng |
| Row_format | Định dạng hàng do engine báo cáo, ví dụ Dynamic hoặc Compact |
| Rows | Số hàng; với InnoDB thường là ước lượng |
| Avg_row_length | Độ dài hàng trung bình ước lượng, tính bằng byte |
| Data_length | Kích thước dữ liệu theo cách engine báo cáo, tính bằng byte |
| Max_data_length | Kích thước dữ liệu tối đa theo cách engine báo cáo |
| Index_length | Kích thước chỉ mục theo cách engine báo cáo, tính bằng byte |
| Data_free | Dung lượng trống được engine báo cáo; cách diễn giải phụ thuộc engine và tablespace |
| Auto_increment | Giá trị AUTO_INCREMENT kế tiếp được báo cáo nếu bảng có thuộc tính này |
| Create_time | Thời điểm tạo bảng nếu engine cung cấp |
| Update_time | Thời điểm cập nhật dữ liệu gần nhất nếu engine cung cấp; có thể NULL hoặc không đáng tin cậy với InnoDB |
| Check_time | Thời điểm kiểm tra bảng nếu engine hỗ trợ |
| Collation | Collation mặc định của bảng |
| Checksum | Checksum nếu engine hỗ trợ |
| Create_options | Các tùy chọn tạo bảng bổ sung |
| Comment | Comment của bảng |

Tập cột và giá trị cụ thể có thể khác giữa storage engine và phiên bản MySQL. SHOW TABLE STATUS chủ yếu hữu ích cho kiểm tra tổng quan; không nên xem tất cả trường là số liệu chính xác hoặc có ý nghĩa giống nhau ở mọi engine.

### 4.3. Diễn giải các trường kích thước và số hàng

Với InnoDB, Rows thường là ước lượng thống kê chứ không phải kết quả đếm chính xác. Nếu cần số hàng chính xác, hãy chạy:

~~~sql
SELECT COUNT(*) FROM shop.orders;
~~~

Trên bảng lớn, COUNT(*) vẫn cần thực hiện công việc đọc dữ liệu phù hợp với kế hoạch và trạng thái transaction. Đừng chạy truy vấn đếm liên tục trên bảng lớn chỉ để thay thế việc theo dõi thống kê.

Data_length và Index_length giúp quan sát quy mô dữ liệu và chỉ mục, nhưng cách engine tính và báo cáo có thể khác nhau. Với InnoDB, dữ liệu bảng được tổ chức trong clustered index; vì vậy Data_length có quan hệ với kích thước clustered index, còn Index_length chủ yếu phản ánh các chỉ mục phụ theo cách engine báo cáo.

Data_free không đồng nghĩa dung lượng ổ đĩa có thể thu hồi ngay. Nó có thể biểu diễn không gian trống trong tablespace hoặc extent mà engine quản lý. Với tablespace dùng chung, giá trị có thể phản ánh phạm vi rộng hơn một bảng đơn lẻ. Không nên lấy Data_free làm số dung lượng chắc chắn có thể trả lại cho hệ điều hành.

Update_time cũng cần thận trọng. Với InnoDB, trường này có thể không được cập nhật hoặc trả về NULL tùy phiên bản và cách lưu trữ. Không dùng nó làm nguồn duy nhất để xác định lần cuối bảng có thay đổi dữ liệu.

### 4.4. Kiểm tra engine và collation

Một truy vấn nhanh:

~~~sql
SHOW TABLE STATUS FROM shop LIKE 'orders'\G
~~~

Hãy kiểm tra ít nhất:

- Engine có đúng là InnoDB hay không.
- Collation có phù hợp với quy tắc so sánh chuỗi của ứng dụng hay không.
- Rows có hợp lý ở mức ước lượng so với quy mô dự kiến không.
- Data_length và Index_length có thay đổi bất thường giữa các lần theo dõi không.
- Create_options và Comment có chứa thông tin cần kiểm tra không.

Nếu muốn kiểm tra một bảng dùng engine khác, hãy cân nhắc đặc tính của engine đó trước khi diễn giải kích thước, row count hoặc data_free.

## 5. Dùng ba lệnh cùng nhau trong một lần kiểm tra

Giả sử truy vấn liệt kê đơn hàng theo khách hàng đang chậm:

~~~sql
SELECT order_id, status, total, created_at
FROM shop.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
~~~

Một quy trình kiểm tra có thể đi theo các bước:

**Bước 1: Xác minh định nghĩa bảng**

~~~sql
SHOW CREATE TABLE shop.orders\G
~~~

Kiểm tra kiểu dữ liệu customer_id, khóa chính, engine và các ràng buộc. Xác nhận bảng có khai báo index ghép phù hợp với điều kiện lọc và thứ tự thời gian hay không.

**Bước 2: Xác minh index**

~~~sql
SHOW INDEX FROM shop.orders;
~~~

Kiểm tra index có chứa customer_id ở vị trí đầu và created_at ở vị trí tiếp theo hay không. Kiểm tra index có visible không, key part có đúng thứ tự không và cardinality có vẻ hợp lý không.

**Bước 3: Xem thông tin bảng**

~~~sql
SHOW TABLE STATUS FROM shop LIKE 'orders'\G
~~~

Kiểm tra engine, số hàng ước lượng, kích thước dữ liệu và index. Nếu bảng lớn hơn nhiều so với dự tính hoặc thống kê có dấu hiệu cũ, cần điều tra thêm.

**Bước 4: Kiểm tra kế hoạch truy vấn**

~~~sql
EXPLAIN
SELECT order_id, status, total, created_at
FROM shop.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
~~~

Đọc key, type, rows, filtered, Extra trong kết quả EXPLAIN dạng bảng. Với định dạng JSON, kiểm tra phần used_key_parts, ước lượng hàng và chi phí. Không có một giá trị type hay key đơn lẻ nào đủ để kết luận hiệu năng; cần xét số hàng thực tế, độ chọn lọc và dữ liệu trả về.

**Bước 5: Đo thực tế nếu cần**

~~~sql
EXPLAIN ANALYZE
SELECT order_id, status, total, created_at
FROM shop.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
~~~

EXPLAIN ANALYZE chạy câu SELECT, vì vậy hãy dùng trên môi trường và thời điểm phù hợp. So sánh số hàng ước lượng với số hàng thực tế, thời gian từng iterator và số vòng lặp để xác định công việc phát sinh ở đâu.

## 6. Đối chiếu với INFORMATION_SCHEMA

Các lệnh SHOW thuận tiện cho người vận hành kiểm tra nhanh. Khi cần truy vấn metadata theo cách có cấu trúc, tổng hợp nhiều bảng hoặc xuất báo cáo, INFORMATION_SCHEMA thường phù hợp hơn.

Một số bảng metadata hữu ích:

| Bảng | Thông tin |
|---|---|
| INFORMATION_SCHEMA.TABLES | Một hàng cho mỗi table hoặc view, gồm engine, row estimate, kích thước và thời gian |
| INFORMATION_SCHEMA.COLUMNS | Cột, kiểu dữ liệu, NULL, default, collation và thứ tự cột |
| INFORMATION_SCHEMA.STATISTICS | Các key part của index, thứ tự, cardinality và thuộc tính index |
| INFORMATION_SCHEMA.TABLE_CONSTRAINTS | Loại ràng buộc như PRIMARY KEY, UNIQUE, FOREIGN KEY và CHECK |
| INFORMATION_SCHEMA.KEY_COLUMN_USAGE | Cột tham gia key và quan hệ tham chiếu |
| INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS | Quy tắc tham chiếu của khóa ngoại |

Ví dụ lấy thông tin index qua INFORMATION_SCHEMA:

~~~sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    CARDINALITY,
    INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

Ví dụ lấy thông tin bảng:

~~~sql
SELECT
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    TABLE_COLLATION
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_TYPE = 'BASE TABLE';
~~~

INFORMATION_SCHEMA cho phép kết hợp metadata nhiều bảng trong một truy vấn. Tuy nhiên, các cột thống kê như TABLE_ROWS, DATA_LENGTH và INDEX_LENGTH vẫn có thể là ước lượng hoặc phụ thuộc engine; chuyển sang INFORMATION_SCHEMA không biến thống kê thành số đếm chính xác.

### 6.1. SHOW hay INFORMATION_SCHEMA?

| Nhu cầu | Cách phù hợp |
|---|---|
| Đọc nhanh DDL của một bảng | SHOW CREATE TABLE |
| Kiểm tra thứ tự và thuộc tính index | SHOW INDEX |
| Xem tổng quan engine và kích thước bảng | SHOW TABLE STATUS |
| Tổng hợp metadata của nhiều bảng | INFORMATION_SCHEMA |
| Tạo báo cáo schema có lọc và JOIN | INFORMATION_SCHEMA |
| Kiểm tra kế hoạch của một truy vấn | EXPLAIN hoặc EXPLAIN ANALYZE |
| Xác định truy vấn đang dùng index nào | EXPLAIN, Performance Schema hoặc công cụ giám sát phù hợp |

Không có một lệnh duy nhất thay thế được toàn bộ các cách kiểm tra trên. Hãy chọn công cụ theo câu hỏi cần trả lời.

## 7. Các giới hạn và lưu ý vận hành

### 7.1. Metadata phản ánh trạng thái hiện tại

SHOW CREATE TABLE mô tả cấu trúc hiện tại. Nếu schema thay đổi bằng migration, ALTER TABLE hoặc công cụ quản trị, kết quả sẽ phản ánh cấu trúc sau thay đổi. Nó không cho biết ai đã thay đổi hoặc thay đổi vào thời điểm nào.

Muốn truy vết lịch sử schema, cần dùng migration files, version control, audit log hoặc quy trình quản lý thay đổi phù hợp.

### 7.2. Cardinality và row count có thể là ước lượng

InnoDB dùng thống kê để ước lượng cardinality và số hàng. Các con số có thể không khớp hoàn toàn với dữ liệu hiện tại. Khi cần, có thể cập nhật thống kê bằng ANALYZE TABLE, sau đó kiểm tra lại kế hoạch và đo hiệu năng.

### 7.3. Kích thước không đồng nghĩa dung lượng có thể thu hồi

Các trường Data_length, Index_length và Data_free là số liệu engine báo cáo. Chúng không phải lúc nào cũng tương ứng trực tiếp với dung lượng file có thể xóa hoặc trả về hệ điều hành. Với InnoDB, cần xét tablespace, file-per-table, shared tablespace, undo tablespace và cách cấp phát extent.

### 7.4. Kết quả phụ thuộc quyền và phạm vi database

Nếu không thấy bảng, hãy kiểm tra:

- Đã chọn đúng database chưa?
- Có chỉ rõ schema trong câu lệnh không?
- Tên bảng có đúng không?
- Tài khoản có quyền xem đối tượng và metadata liên quan không?
- Bảng có thực sự là base table hay là view?

SHOW TABLE STATUS chủ yếu liệt kê trạng thái bảng; để kiểm tra view và metadata tổng hợp của table/view, hãy xem INFORMATION_SCHEMA.TABLES và các metadata view liên quan.

### 7.5. Không dùng SHOW INDEX để thay thế kiểm thử hiệu năng

Một index có mặt không bảo đảm optimizer dùng nó. Ngược lại, một truy vấn quét bảng không phải lúc nào cũng sai: nếu bảng nhỏ hoặc điều kiện chọn phần lớn hàng, table scan có thể rẻ hơn. Luôn đối chiếu metadata với kế hoạch và số liệu thực thi.

## 8. Ví dụ kiểm tra schema trước khi phát hành

Trước khi phát hành một phiên bản ứng dụng có migration mới, người phát triển có thể dùng quy trình sau trên môi trường kiểm thử:

1. Chạy migration tạo hoặc thay đổi bảng.
2. Dùng SHOW CREATE TABLE để xác minh kiểu dữ liệu, default, constraint, engine và collation đúng với thiết kế.
3. Dùng SHOW INDEX để xác minh index mới có đúng tên, thứ tự key part, unique và visibility.
4. Dùng SHOW TABLE STATUS để xác nhận bảng tồn tại và engine đúng như yêu cầu.
5. Chạy các truy vấn đại diện với EXPLAIN để xem optimizer có thể sử dụng index như dự kiến.
6. Chạy kiểm thử dữ liệu và transaction để xác minh ràng buộc hoạt động.
7. Lưu kết quả kiểm tra hoặc báo cáo migration cùng phiên bản ứng dụng.

Ví dụ một truy vấn kiểm tra nhanh sau migration:

~~~sql
SHOW CREATE TABLE shop.orders\G

SHOW INDEX FROM shop.orders;

SHOW TABLE STATUS FROM shop LIKE 'orders'\G
~~~

Các lệnh trên chỉ đọc metadata; chúng không thay thế test ghi dữ liệu, test rollback hoặc kiểm tra tương thích ứng dụng.

## 9. Những nhầm lẫn thường gặp

**“SHOW CREATE TABLE trả lại đúng nguyên văn file SQL đã tạo bảng.”** Không nhất thiết. MySQL có thể chuẩn hóa và bổ sung cách biểu diễn các thuộc tính.

**“SHOW INDEX cho biết truy vấn đang sử dụng index nào.”** Không. Nó liệt kê index hiện có; cần EXPLAIN để xem kế hoạch của truy vấn cụ thể.

**“Cardinality là số giá trị phân biệt chính xác.”** Không. Đây thường là ước lượng thống kê, đặc biệt với InnoDB.

**“Rows trong SHOW TABLE STATUS là số hàng chính xác.”** Không. Với InnoDB, đây thường là ước lượng. Dùng COUNT(*) nếu thực sự cần đếm chính xác và chấp nhận chi phí truy vấn.

**“Data_free là dung lượng ổ đĩa chắc chắn lấy lại được.”** Không. Nó phụ thuộc engine và cách quản lý tablespace.

**“Index có trong SHOW INDEX thì optimizer chắc chắn dùng.”** Không. Optimizer chọn kế hoạch theo thống kê và chi phí.

**“SHOW TABLE STATUS thay thế INFORMATION_SCHEMA.”** Không. SHOW phù hợp kiểm tra nhanh; INFORMATION_SCHEMA thuận tiện cho truy vấn, tổng hợp và báo cáo metadata.

## Kết luận

SHOW CREATE TABLE, SHOW INDEX và SHOW TABLE STATUS là ba công cụ nền tảng để kiểm tra schema và metadata trong MySQL. Lệnh đầu cho biết định nghĩa DDL hiện tại; lệnh thứ hai cho biết cấu trúc và thuộc tính index; lệnh thứ ba cung cấp thông tin tổng quan về engine, số hàng ước lượng và kích thước bảng.

Khi kiểm tra thiết kế hoặc điều tra truy vấn, hãy kết hợp cả ba lệnh với EXPLAIN, EXPLAIN ANALYZE và INFORMATION_SCHEMA khi cần. Luôn phân biệt cấu trúc được khai báo với thống kê ước lượng, và phân biệt index tồn tại với index thực sự được optimizer chọn. Cách đọc metadata đúng giúp kiểm soát schema, khóa, index, truy vấn và hoạt động vận hành MySQL có căn cứ hơn.
