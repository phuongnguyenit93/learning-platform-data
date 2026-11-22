# Khóa duy nhất, khóa ngoại và kiểm tra tính toàn vẹn sau nạp

Khi nhập dữ liệu vào MySQL, việc câu lệnh nạp chạy hết mà không báo lỗi chưa chứng minh dữ liệu đúng. Khóa duy nhất bảo vệ các định danh không được trùng; khóa ngoại bảo vệ quan hệ giữa bảng cha và bảng con; các truy vấn kiểm tra sau nạp giúp phát hiện bản ghi trùng, bản ghi mồ côi, giá trị thiếu và chênh lệch số lượng. Một quy trình di chuyển dữ liệu đáng tin cậy phải xác minh dữ liệu trước khi nạp, áp dụng ràng buộc phù hợp và đối chiếu lại sau khi nạp.

Bài học này thuộc chương **Nhập xuất và di chuyển** của module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành, các ràng buộc toàn vẹn giúp bảo vệ chất lượng dữ liệu xuyên suốt quá trình import, migration và đồng bộ giữa hệ thống.

## 1. Vì sao phải kiểm tra tính toàn vẹn sau nạp?

Giả sử hệ thống thương mại điện tử có hai bảng:

- `customers`: lưu khách hàng, mỗi khách hàng có một mã nội bộ và email.
- `orders`: lưu đơn hàng, mỗi đơn hàng thuộc về một khách hàng.

Dữ liệu được nhập từ CSV hoặc hệ thống cũ có thể gặp các lỗi:

- Hai khách hàng có cùng email do file nguồn chứa bản ghi lặp.
- Một đơn hàng tham chiếu đến `customer_id` không tồn tại.
- Mã đơn hàng bị trùng giữa hai lần import.
- Giá trị khóa bị thiếu hoặc bị chuyển sai kiểu khi nạp.
- Bản ghi bị bỏ qua do lỗi chuyển đổi, `INSERT IGNORE` hoặc `LOAD DATA ... IGNORE`.
- Một lần nạp chạy lại tạo thêm dữ liệu trùng hoặc ghi đè nhầm dữ liệu đã có.

Các lỗi này có thể làm báo cáo sai, truy vấn join thiếu dữ liệu, vi phạm quy tắc nghiệp vụ hoặc khiến các thao tác cập nhật/xóa về sau thất bại. Ràng buộc ở database là lớp bảo vệ cuối cùng; kiểm tra ở file nguồn và ứng dụng không thay thế được ràng buộc đó.

## 2. Khóa chính, khóa duy nhất và khóa ngoại

Ba loại khóa có mục đích khác nhau:

| Loại khóa | Vai trò | Đặc điểm |
|---|---|---|
| PRIMARY KEY | Định danh duy nhất mỗi hàng | Mỗi bảng có tối đa một khóa chính; các cột khóa chính không được NULL |
| UNIQUE KEY | Ngăn hai hàng có cùng giá trị khóa | Một bảng có thể có nhiều unique key; MySQL cho phép nhiều giá trị NULL trong unique index |
| FOREIGN KEY | Giữ quan hệ giữa bảng con và bảng cha | Giá trị khác NULL ở cột tham chiếu phải khớp một khóa được tham chiếu |

Ví dụ, `customers.id` là khóa chính nội bộ; `customers.email` là khóa duy nhất theo nghiệp vụ; `orders.customer_id` là khóa ngoại trỏ tới khách hàng.

~~~sql
CREATE TABLE customers (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  email VARCHAR(254) NOT NULL,
  display_name VARCHAR(120) NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_customers_email UNIQUE (email)
) ENGINE=InnoDB;

CREATE TABLE orders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  order_no VARCHAR(40) NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  total_amount DECIMAL(12, 2) NOT NULL,
  import_batch_id VARCHAR(64) NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_orders_order_no UNIQUE (order_no),
  KEY idx_orders_customer_id (customer_id),
  CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES customers (id)
    ON UPDATE RESTRICT
    ON DELETE RESTRICT
) ENGINE=InnoDB;
~~~

Hai cột `customers.id` và `orders.customer_id` đều là `BIGINT UNSIGNED`. Kiểu dữ liệu của cột tham chiếu và cột được tham chiếu phải tương thích; với số nguyên, cần khớp kích thước và thuộc tính signed/unsigned. Với cột chuỗi, cần khớp charset và collation. Bảng cha và bảng con phải dùng storage engine hỗ trợ foreign key, thông thường là InnoDB.

Cột được tham chiếu nên là PRIMARY KEY hoặc UNIQUE KEY. InnoDB yêu cầu chỉ mục thích hợp ở cột được tham chiếu và cột khóa ngoại; nếu thiếu chỉ mục phía con, MySQL có thể tự tạo. Khai báo chỉ mục tường minh giúp tên và mục đích chỉ mục dễ quản lý hơn.

## 3. Chọn khóa duy nhất theo quy tắc nghiệp vụ

Một khóa duy nhất phải phản ánh điều gì thực sự không được phép trùng. Ví dụ:

- Email đăng nhập duy nhất trong toàn hệ thống.
- Mã hóa đơn duy nhất trong một công ty.
- Mã sản phẩm duy nhất trong một cửa hàng.
- Cặp `tenant_id, external_code` duy nhất trong từng tenant.

Nếu mã chỉ duy nhất trong phạm vi tenant, không tạo unique index riêng trên `external_code`. Hãy dùng khóa ghép:

~~~sql
CREATE TABLE external_records (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  tenant_id BIGINT UNSIGNED NOT NULL,
  external_code VARCHAR(80) NOT NULL,
  payload JSON NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_external_records_tenant_code
    UNIQUE (tenant_id, external_code)
) ENGINE=InnoDB;
~~~

Khóa ghép đảm bảo cùng một `external_code` có thể xuất hiện ở tenant khác nhau nhưng không lặp trong cùng tenant. Thứ tự cột trong index cũng ảnh hưởng khả năng sử dụng index cho truy vấn; hãy đặt cột theo quy tắc truy vấn và ràng buộc thực tế.

### NULL trong UNIQUE

MySQL cho phép nhiều hàng có giá trị NULL trong unique index vì NULL không được xem là bằng một giá trị NULL khác trong phép so sánh uniqueness. Với unique index nhiều cột, những hàng có NULL ở một thành phần cũng có thể cùng tồn tại dù các thành phần còn lại giống nhau.

Nếu nghiệp vụ yêu cầu mọi bản ghi phải có mã, email hoặc external key, hãy khai báo cột đó là `NOT NULL`. Không trông chờ UNIQUE tự động ngăn các giá trị thiếu.

~~~sql
-- Nếu email bắt buộc, khai báo NOT NULL
ALTER TABLE customers
  MODIFY email VARCHAR(254) NOT NULL;
~~~

Khi dùng `MODIFY`, khai báo lại đầy đủ các thuộc tính cần giữ của cột, chẳng hạn charset, collation, DEFAULT và COMMENT. Ví dụ trên giả định cột không có thuộc tính bổ sung cần bảo toàn; hãy kiểm tra `SHOW CREATE TABLE customers` trước khi chạy trên schema thực tế.

Trước khi đổi từ nullable sang `NOT NULL`, hãy kiểm tra và xử lý các hàng đang có NULL:

~~~sql
SELECT id
FROM customers
WHERE email IS NULL;
~~~

### Collation ảnh hưởng tính duy nhất

Unique index trên chuỗi tuân theo collation của cột. Với collation không phân biệt hoa/thường hoặc dấu, các giá trị như `Alice@example.com` và `alice@example.com` có thể được coi là bằng nhau. Một số collation cũng có quy tắc xử lý khoảng trắng cuối chuỗi.

Trước khi tạo unique index, kiểm tra charset/collation của cột:

~~~sql
SHOW FULL COLUMNS FROM customers;
~~~

Nếu quy tắc nghiệp vụ yêu cầu phân biệt hoa/thường hoặc dấu, hãy chọn collation phù hợp sau khi kiểm tra khả năng hỗ trợ của phiên bản MySQL. Đừng đổi collation chỉ để làm cho thao tác import thành công; việc đổi có thể làm thay đổi kết quả so sánh, sắp xếp và uniqueness của dữ liệu hiện có.

## 4. Chọn hành vi của khóa ngoại

Foreign key định nghĩa cách MySQL xử lý khi hàng cha được cập nhật hoặc xóa:

| Hành vi | Kết quả | Trường hợp sử dụng |
|---|---|---|
| RESTRICT | Từ chối xóa/cập nhật hàng cha nếu còn hàng con tham chiếu | Mặc định an toàn khi cần giữ lịch sử |
| NO ACTION | Với InnoDB, có hành vi tương đương RESTRICT | Khi muốn diễn đạt rõ không cho phép hành động |
| CASCADE | Lan truyền cập nhật/xóa xuống hàng con | Quan hệ phụ thuộc vòng đời chặt chẽ |
| SET NULL | Đặt cột khóa ngoại ở hàng con thành NULL | Quan hệ tùy chọn; cột con phải cho phép NULL |

Ví dụ, một đơn hàng cần giữ lịch sử nên thường không bị xóa theo khách hàng. Dùng `RESTRICT` giúp thao tác xóa khách hàng thất bại nếu vẫn còn đơn hàng tham chiếu. Nếu nghiệp vụ cho phép xóa các dòng chi tiết khi xóa đơn hàng, có thể cân nhắc `ON DELETE CASCADE` ở quan hệ giữa `order_items` và `orders`.

~~~sql
CREATE TABLE products (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  order_id BIGINT UNSIGNED NOT NULL,
  product_id BIGINT UNSIGNED NOT NULL,
  quantity INT UNSIGNED NOT NULL,
  PRIMARY KEY (id),
  KEY idx_order_items_order_id (order_id),
  KEY idx_order_items_product_id (product_id),
  CONSTRAINT fk_order_items_order
    FOREIGN KEY (order_id)
    REFERENCES orders (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_order_items_product
    FOREIGN KEY (product_id)
    REFERENCES products (id)
    ON DELETE RESTRICT
) ENGINE=InnoDB;
~~~

Dùng CASCADE có chủ đích vì một lệnh xóa ở bảng cha có thể xóa nhiều hàng con. Với dữ liệu tài chính, đơn hàng hoặc lịch sử kiểm toán, thường nên giữ bản ghi và dùng trạng thái hủy/ẩn thay vì xóa dây chuyền.

InnoDB kiểm tra foreign key ngay trong thao tác ghi; MySQL không hỗ trợ khai báo foreign key kiểu `DEFERRABLE` để trì hoãn kiểm tra đến cuối transaction. Khi import dữ liệu liên quan nhiều bảng, thứ tự nạp và trạng thái ràng buộc vì vậy rất quan trọng.

## 5. Thiết kế luồng nạp qua staging table

Với dữ liệu lớn hoặc đến từ nguồn không hoàn toàn tin cậy, nên nạp vào staging table trước. Staging table giữ dữ liệu gần với nguồn, sau đó thực hiện chuẩn hóa, kiểm tra và chuyển vào bảng chính.

Mô hình:

~~~text
CSV / hệ thống cũ
       |
       v
Staging tables
       |
       +--> Kiểm tra kiểu và giá trị bắt buộc
       |
       +--> Tìm khóa trùng
       |
       +--> Tìm khóa ngoại mồ côi
       |
       v
Bảng chính có PRIMARY / UNIQUE / FOREIGN KEY
       |
       v
Đối chiếu số lượng, tổng và quan hệ sau nạp
~~~

Ví dụ tạo staging table cho khách hàng:

~~~sql
CREATE TABLE stg_customers (
  source_id VARCHAR(40),
  email VARCHAR(254),
  display_name VARCHAR(120)
) ENGINE=InnoDB;

CREATE TABLE stg_orders (
  source_order_no VARCHAR(40),
  source_customer_id VARCHAR(40),
  total_amount_text VARCHAR(40),
  import_batch_id VARCHAR(64) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE stg_customer_id_map (
  source_id VARCHAR(40) NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (source_id),
  KEY idx_stg_customer_id_map_customer (customer_id)
) ENGINE=InnoDB;

CREATE TABLE stg_external_records (
  tenant_id BIGINT UNSIGNED,
  external_code VARCHAR(80)
) ENGINE=InnoDB;
~~~

Các cột ở staging có thể dùng kiểu chuỗi để giữ nguyên giá trị nhập vào, sau đó chuyển đổi có kiểm soát. Tuy nhiên, không nên để staging trở thành nơi lưu dữ liệu lâu dài không có quy trình quản lý. Gắn batch ID, thời điểm nạp và nguồn dữ liệu giúp truy vết từng lần migration.

## 6. Kiểm tra trước khi chuyển dữ liệu vào bảng chính

### Tìm giá trị bắt buộc bị thiếu

~~~sql
SELECT *
FROM stg_customers
WHERE email IS NULL
   OR TRIM(email) = ''
   OR display_name IS NULL
   OR TRIM(display_name) = '';
~~~

Với mã đơn hàng:

~~~sql
SELECT *
FROM stg_orders
WHERE source_order_no IS NULL
   OR TRIM(source_order_no) = '';
~~~

Hãy xác định rõ cách xử lý dữ liệu thiếu: từ chối batch, đưa hàng lỗi vào bảng quarantine để sửa, hoặc áp dụng giá trị mặc định nếu nghiệp vụ cho phép. Không tự điền chuỗi rỗng vào một định danh bắt buộc.

### Tìm khóa đơn bị trùng

~~~sql
SELECT
  email,
  COUNT(*) AS duplicate_count
FROM stg_customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Truy vấn nhóm theo collation của cột. Để kết quả khớp với unique index đích, staging nên dùng cùng charset và collation với cột đích; nếu không, phép GROUP BY ở staging có thể phân biệt hai chuỗi mà unique index ở bảng đích coi là bằng nhau.

Kiểm tra mã đơn hàng:

~~~sql
SELECT
  source_order_no,
  COUNT(*) AS duplicate_count
FROM stg_orders
WHERE source_order_no IS NOT NULL
GROUP BY source_order_no
HAVING COUNT(*) > 1;
~~~

### Tìm khóa ghép bị trùng

~~~sql
SELECT
  tenant_id,
  external_code,
  COUNT(*) AS duplicate_count
FROM stg_external_records
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
~~~

Nếu một thành phần của unique key có thể NULL, hãy kiểm tra riêng các hàng NULL theo quy tắc nghiệp vụ; unique index có thể cho phép nhiều hàng chứa NULL.

### Kiểm tra khóa ngoại mồ côi

Một đơn hàng chỉ hợp lệ nếu khách hàng được tham chiếu tồn tại. Nếu staging có mã khách hàng nguồn, hãy ánh xạ mã đó sang ID đích rồi kiểm tra quan hệ:

~~~sql
SELECT
  o.source_order_no,
  o.source_customer_id
FROM stg_orders AS o
LEFT JOIN stg_customer_id_map AS m
  ON m.source_id = o.source_customer_id
LEFT JOIN customers AS c
  ON c.id = m.customer_id
WHERE o.source_customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

Kết quả là các đơn hàng không tìm được khách hàng tương ứng. Cần sửa mapping, nạp khách hàng còn thiếu hoặc đưa các đơn hàng đó vào quarantine. Không tạo một customer giả chỉ để làm cho foreign key vượt qua kiểm tra.

### Kiểm tra giá trị và kiểu dữ liệu

Trước khi chuyển chuỗi sang số hoặc ngày, tìm các giá trị không chuyển đổi được và vượt miền hợp lệ. Ví dụ:

~~~sql
SELECT *
FROM stg_orders
WHERE total_amount_text IS NULL
   OR TRIM(total_amount_text) = ''
   OR total_amount_text NOT REGEXP '^[0-9]+([.][0-9]{1,2})?$';
~~~

Regex chỉ là ví dụ cho định dạng số thập phân không âm với tối đa hai chữ số sau dấu chấm. Điều chỉnh theo định dạng file nguồn, dấu phân cách thập phân và quy tắc tiền tệ. Sau khi chuyển kiểu, kiểm tra thêm giới hạn của cột đích và giá trị nghiệp vụ.

## 7. Nạp theo thứ tự cha trước, con sau

Nếu foreign key đang được bật, phải nạp hàng cha trước khi nạp hàng con. Với ví dụ này:

1. Nạp `customers`.
2. Tạo hoặc kiểm tra mapping từ mã khách hàng nguồn sang `customers.id`.
3. Nạp `orders` với `customer_id` hợp lệ.
4. Nạp `order_items` sau khi các đơn hàng đã tồn tại.

Ví dụ chuyển khách hàng đã kiểm tra vào bảng chính:

~~~sql
INSERT INTO customers (email, display_name)
SELECT email, display_name
FROM stg_customers;
~~~

Sau đó ánh xạ ID bằng khóa nghiệp vụ ổn định. Nếu email là duy nhất và đã được chuẩn hóa, có thể join staging với bảng chính:

~~~sql
INSERT INTO orders (order_no, customer_id, total_amount, import_batch_id)
SELECT
  s.source_order_no,
  c.id,
  CAST(s.total_amount_text AS DECIMAL(12, 2)),
  s.import_batch_id
FROM stg_orders AS s
JOIN stg_customer_id_map AS m
  ON m.source_id = s.source_customer_id
JOIN customers AS c
  ON c.id = m.customer_id;
~~~

Ví dụ này giả định mapping đã được xác minh duy nhất và dữ liệu đã qua kiểm tra. Nếu mapping có thể trả nhiều hàng cho một mã nguồn, join sẽ nhân bản bản ghi; phải kiểm tra cardinality trước khi insert.

Với migration lớn, chia thành batch theo khóa hoặc phạm vi dữ liệu. Ghi lại batch đã hoàn tất để có thể tiếp tục sau lỗi mà không nạp trùng. Dùng transaction cho từng batch khi kích thước và thời gian khóa cho phép. Tránh một transaction khổng lồ gây undo log lớn, giữ khóa lâu và làm tăng thời gian phục hồi.

## 8. Có nên tắt FOREIGN_KEY_CHECKS khi import?

MySQL cho phép tạm tắt kiểm tra foreign key trong session:

~~~sql
SET SESSION FOREIGN_KEY_CHECKS = 0;

-- Chạy các thao tác import đã được chuẩn bị.

SET SESSION FOREIGN_KEY_CHECKS = 1;
~~~

Cách này đôi khi hữu ích khi import dump có thứ tự bảng phức tạp hoặc khi công cụ cần nạp dữ liệu trước rồi tạo quan hệ. Tuy nhiên, phải hiểu giới hạn quan trọng:

**Bật lại FOREIGN_KEY_CHECKS không quét lại dữ liệu đã nạp để tìm hàng mồ côi.** Nếu nạp hàng con không có hàng cha trong lúc kiểm tra bị tắt, việc đặt biến về 1 không tự động phát hiện hoặc xóa các hàng sai đó.

Vì vậy:

- Ưu tiên giữ foreign key checks bật và nạp bảng theo thứ tự cha trước, con sau.
- Nếu buộc phải tắt, chỉ tắt trong session dành riêng cho batch import.
- Trước khi bật lại, chạy truy vấn anti-join cho mọi quan hệ cha-con.
- Sau khi bật lại, xác minh biến đã trở về 1.
- Không cho ứng dụng truy cập dữ liệu đang ở trạng thái chưa được xác minh.

~~~sql
SELECT @@SESSION.foreign_key_checks;
~~~

`FOREIGN_KEY_CHECKS` là biến có phạm vi session và global. Thay đổi session chỉ tác động kết nối hiện tại; thay đổi global ảnh hưởng các kết nối mới và cần quyền quản trị thích hợp. Trong quy trình import, dùng session riêng giúp giới hạn phạm vi ảnh hưởng.

Tương tự, `unique_checks=0` đôi khi được dùng để tối ưu bulk load InnoDB khi dữ liệu chắc chắn không có duplicate. Chỉ dùng khi đã kiểm tra dữ liệu và hiểu tác động; không dùng nó để bỏ qua lỗi khóa duy nhất. Với dữ liệu không chắc chắn, giữ kiểm tra unique bật để database từ chối bản ghi trùng.

## 9. Thêm ràng buộc sau khi nạp dữ liệu

Một số migration tạo bảng đích trước, nạp dữ liệu, kiểm tra rồi mới thêm unique key và foreign key. Cách này có thể giảm chi phí duy trì nhiều index trong lúc bulk load, nhưng chỉ an toàn nếu dữ liệu đã được kiểm tra đầy đủ và bảng chưa được ứng dụng sử dụng như dữ liệu hợp lệ.

Trước khi thêm unique key, tìm duplicate:

~~~sql
SELECT email, COUNT(*) AS n
FROM customers
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Nếu không có kết quả và cột đáp ứng quy tắc NULL, thêm constraint:

~~~sql
ALTER TABLE customers
  ADD CONSTRAINT uq_customers_email UNIQUE (email);
~~~

Trước khi thêm foreign key, tìm hàng mồ côi:

~~~sql
SELECT o.id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.id = o.customer_id
WHERE c.id IS NULL;
~~~

Nếu không có kết quả, thêm ràng buộc:

~~~sql
ALTER TABLE orders
  ADD CONSTRAINT fk_orders_customer
  FOREIGN KEY (customer_id)
  REFERENCES customers (id)
  ON UPDATE RESTRICT
  ON DELETE RESTRICT;
~~~

Nếu cột `customer_id` cho phép NULL, hàng có `customer_id IS NULL` không vi phạm foreign key. Nếu nghiệp vụ yêu cầu mỗi đơn hàng phải có khách hàng, cột phải được khai báo `NOT NULL` và dữ liệu NULL phải được xử lý trước.

Thao tác `ALTER TABLE` có thể cần xây dựng index, đọc toàn bộ dữ liệu hoặc lấy metadata lock. Hãy ước lượng dung lượng, thời gian, ảnh hưởng tới ghi và yêu cầu online DDL của phiên bản MySQL trước khi chạy trên bảng lớn. Tạo constraint thất bại khi dữ liệu hiện có vi phạm; không bỏ qua lỗi rồi coi migration là hoàn tất.

## 10. Kiểm tra tính toàn vẹn sau nạp

Sau khi nạp, chạy lại các truy vấn kiểm tra trên **bảng đích**, không chỉ trên staging.

### Kiểm tra duplicate trên unique key

~~~sql
SELECT email, COUNT(*) AS n
FROM customers
GROUP BY email
HAVING COUNT(*) > 1;

SELECT order_no, COUNT(*) AS n
FROM orders
GROUP BY order_no
HAVING COUNT(*) > 1;
~~~

Nếu unique index đã được tạo, các truy vấn này cũng giúp kiểm tra dữ liệu theo cách so sánh của cột đích. Nếu có khóa ghép, GROUP BY phải dùng đầy đủ các thành phần theo đúng thứ tự logic của quy tắc nghiệp vụ.

### Kiểm tra hàng mồ côi

~~~sql
SELECT
  o.id,
  o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

Kết quả phải rỗng. Lặp lại với mọi quan hệ foreign key, bao gồm cả quan hệ nhiều tầng như `order_items -> orders -> customers`.

### Kiểm tra giá trị bắt buộc và miền dữ liệu

~~~sql
SELECT COUNT(*) AS missing_email
FROM customers
WHERE email IS NULL OR TRIM(email) = '';

SELECT COUNT(*) AS invalid_total
FROM orders
WHERE total_amount < 0;
~~~

Kiểm tra theo quy tắc nghiệp vụ thực tế. Một số hệ thống cho phép đơn hàng hoàn tiền hoặc điều chỉnh âm; khi đó không nên áp dụng điều kiện `total_amount >= 0` một cách máy móc.

### Đối chiếu số lượng

So sánh số hàng theo batch, theo khoảng khóa hoặc theo ngày giữa nguồn và đích. Không chỉ so sánh tổng số toàn bảng vì hai tập dữ liệu có thể cùng số lượng nhưng chứa các bản ghi khác nhau.

Ví dụ:

~~~sql
SELECT COUNT(*) AS source_rows
FROM stg_orders;

SELECT COUNT(*) AS target_rows
FROM orders
WHERE import_batch_id = 'batch_2026_11_19';
~~~

Nếu cần kiểm tra sâu hơn, so sánh các tổng nghiệp vụ như tổng tiền, số đơn theo trạng thái và số khách hàng theo nhóm. Tổng hợp phải dùng cùng quy tắc lọc và cùng phạm vi batch.

### Kiểm tra metadata constraint

Xem định nghĩa bảng:

~~~sql
SHOW CREATE TABLE customers;
SHOW CREATE TABLE orders;
~~~

Kiểm tra các constraint đã được đăng ký:

~~~sql
SELECT
  tc.TABLE_NAME,
  tc.CONSTRAINT_NAME,
  tc.CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS AS tc
WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
  AND tc.TABLE_NAME IN ('customers', 'orders')
ORDER BY tc.TABLE_NAME, tc.CONSTRAINT_TYPE, tc.CONSTRAINT_NAME;
~~~

Xem các cột thuộc khóa ngoại:

~~~sql
SELECT
  kcu.TABLE_NAME,
  kcu.CONSTRAINT_NAME,
  kcu.COLUMN_NAME,
  kcu.REFERENCED_TABLE_NAME,
  kcu.REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE AS kcu
WHERE kcu.CONSTRAINT_SCHEMA = DATABASE()
  AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY kcu.TABLE_NAME, kcu.CONSTRAINT_NAME, kcu.ORDINAL_POSITION;
~~~

Đối chiếu cả tên constraint, cột con, cột cha và thứ tự cột trong khóa ghép. Chỉ thấy tên constraint tồn tại chưa đủ để xác nhận nó tham chiếu đúng bảng/cột dự kiến.

## 11. Xử lý dữ liệu lỗi và chạy lại migration an toàn

Không nên sửa dữ liệu lỗi bằng cách xóa hàng tùy tiện chỉ để import thành công. Mỗi loại lỗi cần một chính sách:

| Lỗi | Cách xử lý có kiểm soát |
|---|---|
| Email trùng | Xác định bản ghi chuẩn, hợp nhất hoặc sửa dữ liệu nguồn theo quy tắc nghiệp vụ |
| Mã nguồn không có mapping | Bổ sung mapping hoặc đưa bản ghi vào quarantine |
| Hàng con không có hàng cha | Nạp cha còn thiếu hoặc loại khỏi batch sau khi có quyết định nghiệp vụ |
| Giá trị không chuyển được kiểu | Giữ giá trị nguồn, ghi lỗi chuyển đổi và sửa mapping |
| Duplicate với dữ liệu đã tồn tại | Xác định import là insert mới, update hay bỏ qua theo chính sách rõ ràng |
| Batch chạy lại | Dùng batch ID, khóa idempotent và ghi nhận tiến độ để tránh nạp trùng |

Các lựa chọn `INSERT IGNORE` và `REPLACE` không phải cách xử lý lỗi chung. `INSERT IGNORE` có thể biến một số lỗi thành warning và bỏ qua hàng; `REPLACE` có thể xóa hàng xung đột rồi chèn hàng mới, kích hoạt hành vi xóa/cascade tùy cấu trúc. Nếu dùng `ON DUPLICATE KEY UPDATE`, phải xác định rõ unique key nào có thể xung đột và trường nào được phép cập nhật.

Sau mỗi lệnh import, kiểm tra ngay số hàng được thêm/cập nhật, warning và lỗi. Ví dụ:

~~~sql
SHOW WARNINGS;
~~~

Chạy lệnh này ngay sau câu lệnh cần kiểm tra vì câu lệnh SQL tiếp theo có thể thay đổi danh sách warning. Lưu log batch, số hàng đọc, số hàng nạp, số hàng bị loại và lý do để có thể đối chiếu.

## 12. Quy trình migration mẫu

Một quy trình thực tế cho hai bảng khách hàng và đơn hàng:

1. **Chụp trạng thái nguồn:** ghi thời điểm, phạm vi dữ liệu, số hàng và các tổng nghiệp vụ cần đối chiếu.
2. **Tạo staging:** giữ dữ liệu nguồn và metadata batch.
3. **Chuẩn hóa:** chuyển định dạng ngày, số, mã hóa ký tự và khóa nghiệp vụ theo quy tắc đã thống nhất.
4. **Kiểm tra unique:** phát hiện email, mã đơn và khóa ghép bị trùng.
5. **Kiểm tra quan hệ:** kiểm tra mapping khách hàng và các hàng con mồ côi.
6. **Nạp bảng cha:** nạp customers và xác minh khóa định danh.
7. **Nạp bảng con:** nạp orders, rồi order_items theo thứ tự phụ thuộc.
8. **Áp dụng constraint:** tạo hoặc xác minh PRIMARY KEY, UNIQUE KEY và FOREIGN KEY.
9. **Đối chiếu sau nạp:** kiểm tra duplicate, orphan, NULL, số lượng và tổng nghiệp vụ.
10. **Mở ứng dụng:** chỉ chuyển traffic sau khi batch được xác nhận hợp lệ và có phương án rollback/khôi phục.

Với migration cần giữ đồng bộ trong lúc ứng dụng vẫn ghi, cần có chiến lược chụp snapshot hoặc dual-write/change capture, xác định điểm cutover và đối chiếu phần thay đổi phát sinh sau snapshot. Chỉ chạy một lần export/import trong khi source tiếp tục nhận ghi sẽ không tạo ra bản sao nhất quán theo thời điểm.

## 13. Checklist kiểm tra

**Trước khi nạp**

- [ ] Xác định PRIMARY KEY, UNIQUE KEY và FOREIGN KEY theo quy tắc nghiệp vụ.
- [ ] Kiểm tra kiểu dữ liệu, signed/unsigned, charset và collation giữa các cột liên quan.
- [ ] Tìm giá trị NULL, rỗng, duplicate và dữ liệu sai định dạng trong staging.
- [ ] Kiểm tra mapping khóa cha-con và số lượng bản ghi mồ côi.
- [ ] Chọn thứ tự nạp, batch size và phương án chạy lại.
- [ ] Xác định có cần giữ constraint trong lúc import hay không.

**Sau khi nạp**

- [ ] Đối chiếu số hàng theo batch và tổng nghiệp vụ.
- [ ] Chạy lại duplicate check trên bảng đích.
- [ ] Chạy anti-join cho từng foreign key.
- [ ] Kiểm tra NOT NULL và các miền giá trị.
- [ ] Xác minh constraint bằng SHOW CREATE TABLE và information_schema.
- [ ] Đọc warning/error của lệnh import.
- [ ] Lưu kết quả kiểm tra và chỉ mở traffic sau khi dữ liệu được xác nhận.

## 14. Ghi nhớ

- PRIMARY KEY định danh hàng; UNIQUE KEY bảo vệ quy tắc không trùng; FOREIGN KEY bảo vệ quan hệ cha-con.
- UNIQUE trong MySQL cho phép nhiều NULL; dùng NOT NULL khi nghiệp vụ yêu cầu giá trị bắt buộc.
- Collation quyết định cách so sánh chuỗi và có thể làm hai chuỗi khác chữ hoa/thường được coi là trùng.
- Kiểu dữ liệu và thuộc tính của hai phía foreign key phải tương thích; nên có index phù hợp ở cả hai phía.
- Nạp bảng cha trước bảng con khi foreign key đang bật.
- Tắt FOREIGN_KEY_CHECKS không làm MySQL tự quét lại dữ liệu khi bật lại.
- Staging table giúp phát hiện lỗi trước khi đưa dữ liệu vào bảng chính.
- Kiểm tra sau nạp phải gồm duplicate, orphan, NULL, số lượng, tổng nghiệp vụ và metadata constraint.
- Không dùng IGNORE hoặc REPLACE để che lỗi nếu chưa hiểu chính sách dữ liệu.
- Một migration chỉ hoàn tất khi dữ liệu đã được đối chiếu và có thể truy vết theo batch.

Khóa và ràng buộc chỉ phát huy tác dụng khi được thiết kế theo quy tắc nghiệp vụ và được kiểm chứng trên dữ liệu thực tế. Hãy coi staging, kiểm tra trước nạp, áp dụng constraint và đối chiếu sau nạp là các bước bắt buộc trong một quy trình di chuyển dữ liệu có thể lặp lại và kiểm toán.

## Tài liệu tham khảo

- [MySQL 8.0 Reference Manual: InnoDB and FOREIGN KEY Constraints](https://dev.mysql.com/doc/refman/8.0/en/innodb-foreign-key-constraints.html)
- [MySQL 8.0 Reference Manual: CREATE TABLE and UNIQUE Constraints](https://dev.mysql.com/doc/refman/8.0/en/create-table.html)
- [MySQL 8.0 Reference Manual: Server SQL Modes and Data Conversion](https://dev.mysql.com/doc/refman/8.0/en/sql-mode.html)
- [MySQL 8.0 Reference Manual: FOREIGN_KEY_CHECKS](https://dev.mysql.com/doc/refman/8.0/en/server-system-variables.html#sysvar_foreign_key_checks)

