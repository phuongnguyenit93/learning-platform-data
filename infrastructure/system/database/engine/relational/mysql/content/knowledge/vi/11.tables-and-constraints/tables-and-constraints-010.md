# DEFAULT expression, invisible column và điều kiện phiên bản

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành. Khi thiết kế hoặc mở rộng bảng, hai tính năng hữu ích nhưng phụ thuộc phiên bản là biểu thức DEFAULT và invisible column. Biểu thức DEFAULT cho phép tính giá trị mặc định khi chèn hàng; invisible column cho phép lưu một cột mà các câu lệnh dùng danh sách cột ngầm không nhìn thấy.

Hai tính năng này giúp giảm mã khởi tạo ở ứng dụng và hỗ trợ thay đổi schema tương thích hơn. Tuy nhiên, chúng có quy tắc riêng về phiên bản, cú pháp, cách INSERT/SELECT hoạt động và khả năng tương thích giữa các môi trường. Cần kiểm tra phiên bản MySQL thực tế trước khi dùng trong migration.

## 1. DEFAULT trong thiết kế bảng

DEFAULT xác định giá trị được dùng khi câu INSERT không cung cấp giá trị cho một cột hoặc khi câu lệnh yêu cầu rõ từ khóa DEFAULT. Nó giúp biểu diễn giá trị khởi tạo có ý nghĩa ngay ở schema.

Ví dụ:

~~~sql
CREATE TABLE tasks (
    task_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    retry_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (task_id)
) ENGINE=InnoDB;
~~~

Khi chèn hàng mà bỏ qua status, retry_count và created_at, MySQL áp dụng các giá trị mặc định tương ứng. Điều này giúp mọi client có cùng quy tắc khởi tạo dữ liệu, kể cả script quản trị hoặc tác vụ nền không đi qua cùng một lớp ứng dụng.

DEFAULT không thay thế validation nghiệp vụ. Ví dụ, status mặc định là PENDING không có nghĩa mọi chuyển trạng thái sau đó đều hợp lệ; ứng dụng vẫn phải kiểm soát luồng nghiệp vụ.

## 2. Literal default và expression default

### 2.1. Literal default

Literal default là giá trị cố định được khai báo trực tiếp:

~~~sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_name VARCHAR(200) NOT NULL,
    active TINYINT(1) NOT NULL DEFAULT 1,
    currency_code CHAR(3) NOT NULL DEFAULT 'VND',
    description VARCHAR(500) NULL DEFAULT NULL,
    PRIMARY KEY (product_id)
) ENGINE=InnoDB;
~~~

Các ví dụ 1, 'VND' và NULL là giá trị cố định. Mỗi hàng bỏ qua cột tương ứng nhận cùng giá trị đã khai báo.

### 2.2. Expression default

Expression default là biểu thức được đánh giá khi cần tạo giá trị mặc định. MySQL hỗ trợ biểu thức DEFAULT từ **MySQL 8.0.13**. Biểu thức phải được đặt trong dấu ngoặc đơn:

~~~sql
CREATE TABLE documents (
    document_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(36) NOT NULL DEFAULT (UUID()),
    title VARCHAR(200) NOT NULL,
    review_due DATE NOT NULL DEFAULT (CURRENT_DATE + INTERVAL 30 DAY),
    PRIMARY KEY (document_id),
    UNIQUE KEY uq_documents_public_id (public_id)
) ENGINE=InnoDB;
~~~

Trong ví dụ, UUID() tạo mã định danh khi cần giá trị mặc định; biểu thức ngày tính ngày đến hạn từ ngày hiện tại. Mỗi lần chèn hàng mà bỏ qua cột tương ứng, MySQL đánh giá biểu thức để lấy giá trị.

Biểu thức DEFAULT phải được đặt trong ngoặc, kể cả khi nó chỉ gồm một lời gọi hàm hoặc một phép tính. Cách viết này giúp phân biệt expression default với literal default và tránh nhầm lẫn khi đọc DDL.

### 2.3. Biểu thức được phép và giới hạn

Expression default có thể dùng literal, toán tử, dấu ngoặc và các built-in function được MySQL cho phép. Biểu thức không được tham chiếu giá trị của cột khác và không được chứa các thành phần như:

- Subquery.
- Stored function hoặc loadable function.
- Biến hệ thống, biến người dùng hoặc tham số routine.
- Tham chiếu cột của hàng đang được chèn.

Ví dụ sau không hợp lệ vì default của end_date tham chiếu cột start_date:

~~~sql
-- Không hợp lệ
CREATE TABLE subscriptions (
    start_date DATE NOT NULL,
    end_date DATE DEFAULT (start_date + INTERVAL 1 YEAR)
);
~~~

Nếu giá trị cần tính từ các cột khác trong cùng hàng, hãy cân nhắc generated column hoặc tính toán trong câu INSERT/UPDATE. DEFAULT chỉ tạo giá trị thay thế khi cột không được cung cấp; nó không phải cơ chế tính lại cột mỗi khi dữ liệu liên quan thay đổi.

Không thể dùng subquery để lấy giá trị mặc định từ bảng khác. Nếu cần cấp mã hoặc giá trị phụ thuộc dữ liệu bên ngoài, hãy thực hiện bằng transaction ở tầng ứng dụng hoặc logic lưu trữ được thiết kế phù hợp.

### 2.4. Default expression cho BLOB, TEXT, GEOMETRY và JSON

Từ MySQL 8.0.13, các kiểu BLOB, TEXT, GEOMETRY và JSON có thể dùng default expression; với các kiểu này, giá trị mặc định phải được viết dưới dạng biểu thức trong ngoặc, ngay cả khi giá trị là literal:

~~~sql
CREATE TABLE article_content (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    body TEXT NOT NULL DEFAULT (''),
    metadata JSON NOT NULL DEFAULT (JSON_OBJECT()),
    PRIMARY KEY (article_id)
) ENGINE=InnoDB;
~~~

Trong MySQL trước 8.0.13, không dựa vào cú pháp default expression này. Nếu cần hỗ trợ MySQL 5.7 hoặc môi trường cũ hơn, hãy khởi tạo giá trị trong câu INSERT hoặc tầng ứng dụng theo một quy tắc thống nhất.

### 2.5. CURRENT_TIMESTAMP và cột thời gian

MySQL đã hỗ trợ cách khai báo CURRENT_TIMESTAMP cho cột TIMESTAMP và DATETIME từ trước khi có expression default tổng quát:

~~~sql
CREATE TABLE audit_events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id)
) ENGINE=InnoDB;
~~~

CURRENT_TIMESTAMP trong DEFAULT đặt thời điểm khởi tạo khi chèn hàng. ON UPDATE CURRENT_TIMESTAMP cập nhật thời điểm khi hàng thay đổi theo quy tắc của cột. Hai chức năng này khác nhau: DEFAULT không tự cập nhật mỗi khi UPDATE; ON UPDATE mới định nghĩa hành vi cập nhật tự động.

Có thể chỉ định độ chính xác phần giây, ví dụ CURRENT_TIMESTAMP(3). Cần chọn precision nhất quán giữa schema, driver và nghiệp vụ.

## 3. DEFAULT được áp dụng khi nào?

### 3.1. Bỏ qua cột trong INSERT

Khi cột không xuất hiện trong danh sách INSERT, MySQL sử dụng default của cột nếu có:

~~~sql
INSERT INTO tasks (title)
VALUES ('Import customers');
~~~

Hàng mới nhận status PENDING, retry_count 0 và created_at theo CURRENT_TIMESTAMP. Đây là cách dùng phổ biến và dễ đọc nhất.

### 3.2. Dùng từ khóa DEFAULT tường minh

Có thể yêu cầu MySQL dùng default cho một cột cụ thể:

~~~sql
INSERT INTO tasks (title, status, retry_count)
VALUES ('Rebuild search index', DEFAULT, DEFAULT);
~~~

DEFAULT ở vị trí giá trị yêu cầu áp dụng default của cột tương ứng. Cách này hữu ích khi câu INSERT có danh sách cột đầy đủ nhưng muốn một vài cột nhận giá trị do schema quy định.

### 3.3. Truyền NULL tường minh không giống bỏ qua cột

Nếu cột cho phép NULL, truyền NULL sẽ lưu NULL thay vì tự động chạy default:

~~~sql
CREATE TABLE profiles (
    profile_id BIGINT NOT NULL,
    nickname VARCHAR(100) NULL DEFAULT 'Guest',
    PRIMARY KEY (profile_id)
);

INSERT INTO profiles (profile_id)
VALUES (1);

INSERT INTO profiles (profile_id, nickname)
VALUES (2, NULL);
~~~

Hàng thứ nhất nhận nickname Guest vì cột bị bỏ qua. Hàng thứ hai nhận NULL vì client đã cung cấp NULL tường minh. Muốn hàng thứ hai dùng default, hãy truyền DEFAULT thay vì NULL.

Với cột NOT NULL, truyền NULL thường gây lỗi trong strict SQL mode. Không dựa vào việc MySQL tự ép NULL thành giá trị ngầm định ở chế độ không strict; hành vi này có thể tạo warning và dữ liệu không như mong đợi.

### 3.4. DEFAULT trong UPDATE

Có thể đặt lại một cột về default:

~~~sql
UPDATE tasks
SET retry_count = DEFAULT
WHERE task_id = 10;
~~~

DEFAULT trong UPDATE áp dụng giá trị mặc định của cột tại thời điểm câu lệnh chạy. Nếu default là expression, MySQL đánh giá expression để có giá trị áp dụng. Đây là thao tác đặt lại giá trị cột; không phải cập nhật tất cả cột trong hàng.

### 3.5. Cột không khai báo DEFAULT

Nếu cột bị bỏ qua và không có default tường minh, MySQL áp dụng quy tắc implicit default theo kiểu dữ liệu và khả năng NULL. Với cột NOT NULL trong strict mode, thiếu giá trị thường làm INSERT thất bại. Thiết kế schema nên khai báo rõ DEFAULT cho các cột thực sự có giá trị khởi tạo hợp lệ, và NOT NULL cho dữ liệu bắt buộc.

## 4. DEFAULT expression và generated column

Hai tính năng có mục đích khác nhau:

| Đặc điểm | DEFAULT expression | Generated column |
|---|---|---|
| Khi tính | Khi INSERT bỏ qua cột hoặc chỉ định DEFAULT; khi UPDATE đặt DEFAULT | Khi đọc hoặc lưu giá trị generated theo định nghĩa cột |
| Phụ thuộc cột khác | Không | Có thể tham chiếu các cột cùng hàng theo quy tắc generated column |
| Có thể nhập giá trị tùy ý | Có thể cung cấp giá trị tường minh khi INSERT/UPDATE | Không thể gán giá trị trực tiếp cho generated column |
| Mục đích | Giá trị khởi tạo hoặc giá trị thay thế | Giá trị dẫn xuất từ dữ liệu khác trong cùng hàng |

Ví dụ generated column:

~~~sql
CREATE TABLE order_lines (
    quantity INT NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    line_total DECIMAL(14,2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
~~~

line_total được tính từ quantity và unit_price. Nếu muốn tạo giá trị mặc định cho một cột độc lập như retry_count, dùng DEFAULT. Nếu cần tính từ cột khác, cân nhắc generated column hoặc biểu thức trong DML.

## 5. Invisible column là gì?

Invisible column là cột vẫn tồn tại trong bảng và lưu dữ liệu bình thường, nhưng không xuất hiện trong các câu lệnh dựa trên danh sách cột ngầm. Tính năng này được hỗ trợ từ **MySQL 8.0.23**.

Ví dụ:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    internal_note VARCHAR(500) NULL INVISIBLE,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;
~~~

internal_note là cột invisible. Cột vẫn có thể được đọc và ghi khi tham chiếu tên tường minh, đồng thời có thể tham gia index theo quy tắc MySQL. Từ khóa INVISIBLE không xóa cột và không làm dữ liệu biến mất.

### 5.1. SELECT * bỏ qua invisible column

~~~sql
SELECT *
FROM customers;
~~~

Kết quả không chứa internal_note. Muốn đọc cột này, phải gọi tên rõ ràng:

~~~sql
SELECT customer_id, full_name, internal_note
FROM customers;
~~~

Điều này hữu ích khi thêm một cột phục vụ nội bộ hoặc migration mà muốn giữ nguyên hình dạng kết quả của các câu SELECT * hiện có.

Invisible column không phải cơ chế bảo mật. Người có quyền SELECT trên bảng vẫn có thể truy cập cột nếu biết tên; quyền truy cập dữ liệu vẫn do privilege MySQL quyết định. Nếu cần giới hạn dữ liệu, dùng quyền ở cấp column, view hoặc cơ chế bảo mật phù hợp.

### 5.2. INSERT không chỉ định danh sách cột

Invisible column không được đưa vào danh sách cột ngầm của các câu lệnh INSERT không ghi tên cột. Ví dụ, với bảng customers ở trên:

~~~sql
INSERT INTO customers
VALUES (1001, 'Nguyen An');
~~~

Hai giá trị tương ứng với hai cột visible là customer_id và full_name; internal_note được bỏ qua và nhận NULL vì cột cho phép NULL. Nếu invisible column là NOT NULL, hãy cung cấp DEFAULT phù hợp để các câu INSERT ngầm vẫn hoạt động.

Có thể ghi rõ invisible column khi cần:

~~~sql
INSERT INTO customers
    (customer_id, full_name, internal_note)
VALUES
    (1002, 'Tran Binh', 'Imported from legacy system');
~~~

Trong ứng dụng mới, vẫn nên ghi danh sách cột tường minh trong INSERT. Cách này dễ đọc, không phụ thuộc thứ tự vật lý của cột và giảm lỗi khi schema thay đổi.

### 5.3. UPDATE và các câu lệnh khác

Invisible column vẫn có thể được tham chiếu tường minh trong SELECT, WHERE, ORDER BY, JOIN, UPDATE và các biểu thức SQL thông thường:

~~~sql
UPDATE customers
SET internal_note = 'Verified'
WHERE customer_id = 1002;

SELECT customer_id, full_name
FROM customers
WHERE internal_note = 'Verified';
~~~

Invisible column vẫn có thể được lập index và tham gia ràng buộc theo các quy tắc của loại cột và index đó. Invisible chỉ ảnh hưởng việc cột có được đưa vào danh sách ngầm hay không; nó không biến cột thành một đối tượng riêng hoặc loại bỏ khả năng truy vấn tường minh.

## 6. Tạo và thay đổi invisible column

### 6.1. Tạo mới

Khai báo INVISIBLE trong CREATE TABLE:

~~~sql
CREATE TABLE event_log (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(100) NOT NULL,
    payload JSON NULL,
    source_system VARCHAR(50) NOT NULL DEFAULT 'web' INVISIBLE,
    PRIMARY KEY (event_id)
) ENGINE=InnoDB;
~~~

source_system không xuất hiện trong SELECT * và INSERT không chỉ định danh sách cột. Nếu muốn ghi nguồn, ứng dụng cần chỉ định source_system tường minh; nếu không, default web được dùng.

### 6.2. Thêm invisible column vào bảng hiện có

~~~sql
ALTER TABLE event_log
  ADD COLUMN migration_tag VARCHAR(40) NULL INVISIBLE;
~~~

Cột mới có thể được thêm mà không làm tăng số cột visible trong kết quả SELECT *. Đây là cách hữu ích khi triển khai schema trước, sau đó cập nhật ứng dụng để đọc/ghi cột mới.

### 6.3. Chuyển đổi visible và invisible

Từ MySQL 8.0.23, có thể thay đổi visibility:

~~~sql
ALTER TABLE event_log
  ALTER COLUMN migration_tag SET VISIBLE;

ALTER TABLE event_log
  ALTER COLUMN migration_tag SET INVISIBLE;
~~~

Khi chuyển thành VISIBLE, cột xuất hiện trong SELECT * và các danh sách cột ngầm. Hình dạng kết quả của ứng dụng dùng SELECT * có thể thay đổi. Khi chuyển thành INVISIBLE, cột bị loại khỏi các danh sách ngầm nhưng dữ liệu vẫn được giữ.

Có thể dùng MODIFY COLUMN với thuộc tính INVISIBLE/VISIBLE khi cần thay đổi đồng thời định nghĩa cột, nhưng phải khai báo lại đầy đủ kiểu dữ liệu, NULL/NOT NULL, DEFAULT, comment và các thuộc tính khác.

### 6.4. Giới hạn cần biết

- Một bảng phải có ít nhất một cột visible.
- Cột invisible vẫn cần tên duy nhất trong bảng.
- Cột invisible không phải là cột bí mật; metadata và câu truy vấn tường minh vẫn có thể tiết lộ nó.
- Một số công cụ ORM, schema diff hoặc ETL có thể không xử lý visibility như mong đợi nếu phiên bản cũ không nhận diện thuộc tính này.
- Cần xác minh hành vi của câu lệnh import/export và công cụ quản trị đang dùng, không chỉ kiểm tra SELECT *.

## 7. Kiểm tra metadata của DEFAULT và visibility

### 7.1. SHOW CREATE TABLE

Đây là cách tổng quát để xem định nghĩa cột:

~~~sql
SHOW CREATE TABLE customers;
~~~

Kết quả thể hiện DEFAULT expression, thuộc tính INVISIBLE, index, constraint và các thuộc tính khác. Hãy lưu kết quả trước và sau migration để so sánh.

### 7.2. INFORMATION_SCHEMA.COLUMNS

Có thể truy vấn metadata cột:

~~~sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA,
    GENERATION_EXPRESSION
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers'
ORDER BY ORDINAL_POSITION;
~~~

EXTRA có thể chứa thuộc tính như auto_increment, DEFAULT_GENERATED, INVISIBLE hoặc thông tin generated column tùy loại cột và phiên bản. Kiểm tra EXTRA để phát hiện cột invisible:

~~~sql
SELECT COLUMN_NAME, EXTRA
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers'
  AND EXTRA LIKE '%INVISIBLE%';
~~~

COLUMN_DEFAULT thể hiện giá trị mặc định trong metadata; với biểu thức mặc định, cách biểu diễn phụ thuộc phiên bản. Dùng SHOW CREATE TABLE để xác minh cú pháp đầy đủ, không chỉ dựa vào một trường metadata.

### 7.3. Kiểm tra phiên bản server

~~~sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS distribution;
~~~

Không chỉ dựa vào phiên bản client hoặc phiên bản Connector/J. Tính năng DDL phải được server thực thi hỗ trợ. Nếu môi trường có nhiều node hoặc replica, kiểm tra phiên bản và khả năng tương thích trên tất cả node liên quan.

## 8. Điều kiện phiên bản và tương thích

Các mốc cần nhớ:

| Tính năng | Phiên bản MySQL | Ghi chú |
|---|---|---|
| Literal DEFAULT | Có từ các phiên bản MySQL cũ | Giá trị mặc định cố định |
| CURRENT_TIMESTAMP cho TIMESTAMP/DATETIME | Có từ các phiên bản cũ | Cơ chế mặc định thời gian đặc biệt |
| Expression default tổng quát | MySQL 8.0.13+ | Biểu thức phải đặt trong ngoặc; có các giới hạn về thành phần biểu thức |
| Default expression cho BLOB/TEXT/GEOMETRY/JSON | MySQL 8.0.13+ | Phải viết default dưới dạng expression, kể cả literal |
| Invisible column | MySQL 8.0.23+ | Ẩn khỏi danh sách cột ngầm như SELECT * |

MySQL 5.7 không hỗ trợ expression default tổng quát và invisible column. Nếu ứng dụng phải chạy đồng thời trên MySQL 5.7 và 8.0, migration dùng các tính năng mới sẽ không thể chạy nguyên trạng trên node 5.7.

Trước khi triển khai, kiểm tra:

1. Phiên bản server chính xác và các tính năng được hỗ trợ.
2. Phiên bản MySQL trên replica, môi trường restore và môi trường CI.
3. ORM, migration tool, schema introspection và code generator có hiểu invisible column hay không.
4. Driver và ứng dụng có dựa vào SELECT * hoặc INSERT không ghi danh sách cột hay không.
5. Logical dump/restore có giữ lại DEFAULT expression và thuộc tính INVISIBLE khi nhập vào server đích hay không.

Không giả định một migration chạy được trên development 8.0.36 sẽ tự chạy được trên production 8.0.22 hoặc replica cũ hơn.

## 9. Kết hợp DEFAULT expression với invisible column

Hai tính năng có thể phối hợp để thêm một thuộc tính nội bộ mà không làm thay đổi kết quả của các câu SELECT * và INSERT dùng danh sách ngầm:

~~~sql
ALTER TABLE customers
  ADD COLUMN source_system VARCHAR(40)
    NOT NULL
    DEFAULT ('legacy')
    INVISIBLE;
~~~

Với server hỗ trợ expression default và invisible column, cột mới:

- Không xuất hiện trong SELECT *.
- Không nằm trong danh sách cột ngầm của INSERT không ghi danh sách cột.
- Nhận giá trị legacy khi INSERT bỏ qua cột.
- Có thể được truy cập bằng tên source_system trong câu SQL tường minh.

Ví dụ:

~~~sql
INSERT INTO customers (customer_id, full_name)
VALUES (2001, 'Le Chi');

SELECT customer_id, full_name, source_system
FROM customers
WHERE customer_id = 2001;
~~~

Hàng mới nhận source_system = legacy. Ứng dụng có thể được triển khai dần để ghi nguồn thực tế, sau đó chuyển cột thành visible nếu cần. Đừng dùng invisible column để né việc cập nhật hợp đồng dữ liệu lâu dài; hãy ghi rõ thời điểm và điều kiện chuyển cột sang visible.

## 10. Ứng dụng, ORM và hợp đồng dữ liệu

### 10.1. Tránh SELECT *

Ứng dụng nên liệt kê cột cần đọc:

~~~sql
SELECT customer_id, full_name, created_at
FROM customers;
~~~

SELECT * làm hợp đồng dữ liệu phụ thuộc toàn bộ cột visible tại thời điểm chạy. Thêm cột visible có thể làm thay đổi thứ tự và số lượng trường trả về; cột invisible tránh thay đổi đó đối với danh sách ngầm nhưng không làm SELECT * trở thành thiết kế bền vững.

### 10.2. Tránh INSERT không có danh sách cột

Không nên dựa vào:

~~~sql
INSERT INTO customers
VALUES (2002, 'Pham Dung');
~~~

Hãy viết:

~~~sql
INSERT INTO customers (customer_id, full_name)
VALUES (2002, 'Pham Dung');
~~~

Danh sách cột tường minh giúp migration thêm, sắp xếp hoặc thay đổi visibility của cột dễ kiểm soát hơn. Nó cũng làm rõ cột nào được cung cấp và cột nào nhận DEFAULT.

### 10.3. ORM và ánh xạ entity

ORM thường đọc metadata schema để tạo entity hoặc mapping. Nếu ORM không hiểu invisible column, nó có thể:

- Sinh SELECT * và không ánh xạ cột invisible.
- Sinh INSERT theo danh sách cột hoặc theo vị trí không như dự kiến.
- Báo schema drift vì metadata có thêm cột.
- Không giữ thuộc tính INVISIBLE khi tạo migration ngược.

Kiểm tra phiên bản ORM và cách nó introspect INFORMATION_SCHEMA. Với entity quan trọng, khai báo rõ danh sách cột và thử integration test trên đúng phiên bản MySQL mục tiêu.

DEFAULT expression cũng có thể không được ORM mô hình hóa đầy đủ. Một số ORM có thể đọc COLUMN_DEFAULT như văn bản hoặc không biết cách sinh DDL expression. Kiểm tra migration được tạo ra thay vì giả định annotation mặc định của ORM tương đương hoàn toàn với DDL MySQL.

### 10.4. Invisible không thay thế phân quyền

Invisible column không ẩn dữ liệu khỏi người có quyền. Nếu cột chứa dữ liệu nhạy cảm, hãy cấp quyền SELECT ở cấp cột, dùng view chỉ xuất các cột được phép hoặc áp dụng thiết kế bảo mật thích hợp. Không dùng INVISIBLE như biện pháp bảo vệ thông tin.

## 11. Triển khai migration an toàn

### 11.1. Trước khi thay đổi

- Xác nhận phiên bản MySQL hỗ trợ expression default hoặc invisible column.
- Chụp SHOW CREATE TABLE và metadata liên quan.
- Kiểm tra câu lệnh ứng dụng đang dùng SELECT *, INSERT không có danh sách cột và công cụ ETL.
- Xác định default expression có sử dụng hàm không xác định hoặc có yêu cầu tương thích replication hay không.
- Kiểm tra cột mới có cần NOT NULL, DEFAULT, index hoặc constraint không.
- Thử DDL trên bản sao dữ liệu có phiên bản gần production.

### 11.2. Thêm cột invisible theo giai đoạn

Một quy trình triển khai ứng dụng theo giai đoạn có thể là:

1. Thêm cột invisible có kiểu, NULL/NOT NULL và DEFAULT phù hợp.
2. Xác minh SELECT * và các INSERT hiện tại vẫn hoạt động như dự kiến.
3. Triển khai ứng dụng mới để ghi/đọc cột bằng tên tường minh.
4. Đối chiếu dữ liệu cột mới và theo dõi lỗi ứng dụng.
5. Khi mọi client đã sẵn sàng, quyết định giữ invisible hoặc chuyển sang visible.

Không cho rằng thêm cột invisible luôn là instant hoặc không có lock. Thuật toán DDL phụ thuộc phiên bản, storage engine, kiểu thay đổi và cấu trúc bảng. Xem kế hoạch ALTER TABLE, tài liệu phiên bản và thử trên staging.

### 11.3. Thay đổi DEFAULT

Để cập nhật default của cột, có thể dùng:

~~~sql
ALTER TABLE tasks
  ALTER COLUMN retry_count SET DEFAULT (1 + 1);
~~~

Lệnh thay đổi giá trị mặc định dùng cho các lần INSERT/UPDATE đặt DEFAULT sau đó; nó không tự cập nhật giá trị retry_count của các hàng đã tồn tại. Nếu muốn backfill dữ liệu cũ, phải chạy UPDATE riêng với điều kiện rõ ràng và kiểm tra số hàng bị tác động.

Để bỏ default:

~~~sql
ALTER TABLE tasks
  ALTER COLUMN retry_count DROP DEFAULT;
~~~

Trước khi bỏ default, kiểm tra mọi client có bỏ qua cột này khi INSERT hay không. Nếu cột NOT NULL và không có default, các INSERT thiếu cột có thể bắt đầu thất bại trong strict mode.

### 11.4. Rollback

DDL MySQL thường gây implicit commit; không kỳ vọng ROLLBACK của transaction sẽ hoàn tác CREATE/ALTER TABLE. Lập migration ngược có chủ đích:

- Nếu thêm cột mới, có thể DROP COLUMN sau khi xác nhận ứng dụng không còn phụ thuộc.
- Nếu chuyển visibility, có thể đổi lại VISIBLE/INVISIBLE theo hợp đồng dữ liệu.
- Nếu thay default, đặt lại default cũ từ DDL đã lưu.
- Nếu dữ liệu đã được ghi vào cột mới, không xóa cột trước khi quyết định dữ liệu cần giữ hay chuyển đi đâu.

Backup và kiểm tra restore vẫn cần thiết đối với thay đổi có thể ảnh hưởng dữ liệu. Rollback schema không nhất thiết hoàn tác dữ liệu đã ghi sau migration.

## 12. Bài thực hành: DEFAULT expression và invisible column

Thực hiện trong MySQL lab với **MySQL 8.0.23 trở lên** để dùng cả hai tính năng. Không thực hiện trên database production.

**Bước 1 — Xác nhận phiên bản.**

~~~sql
SELECT VERSION() AS mysql_version;
~~~

Nếu server thấp hơn 8.0.23, không chạy phần invisible column; có thể thực hành riêng DEFAULT expression từ 8.0.13.

**Bước 2 — Tạo bảng lab.**

~~~sql
CREATE TABLE lab_feature_flags (
    flag_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    flag_name VARCHAR(100) NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    audit_token CHAR(36) NOT NULL DEFAULT (UUID()) INVISIBLE,
    PRIMARY KEY (flag_id),
    UNIQUE KEY uq_lab_audit_token (audit_token)
) ENGINE=InnoDB;
~~~

**Bước 3 — Kiểm tra SELECT *.**

~~~sql
INSERT INTO lab_feature_flags (flag_name)
VALUES ('new-checkout');

SELECT * FROM lab_feature_flags;

SELECT flag_id, flag_name, enabled, created_at, audit_token
FROM lab_feature_flags;
~~~

Truy vấn đầu không hiển thị audit_token. Truy vấn thứ hai đọc cột invisible bằng tên tường minh.

**Bước 4 — Kiểm tra default expression.**

~~~sql
INSERT INTO lab_feature_flags (flag_name, enabled)
VALUES ('new-search', DEFAULT);

SELECT flag_name, enabled, audit_token
FROM lab_feature_flags;
~~~

Quan sát enabled nhận 0 và audit_token được sinh tự động nếu không được cung cấp.

**Bước 5 — Kiểm tra INSERT không liệt kê cột.**

~~~sql
INSERT INTO lab_feature_flags
VALUES (DEFAULT, 'legacy-import', DEFAULT, DEFAULT);
~~~

Giá trị chỉ ứng với các cột visible theo thứ tự của chúng. audit_token invisible được bỏ qua và nhận default expression. Sau đó truy vấn rõ audit_token để kiểm tra.

**Bước 6 — Chuyển visibility.**

~~~sql
ALTER TABLE lab_feature_flags
  ALTER COLUMN audit_token SET VISIBLE;

SELECT * FROM lab_feature_flags;
~~~

Quan sát audit_token xuất hiện trong SELECT *. Đổi lại invisible:

~~~sql
ALTER TABLE lab_feature_flags
  ALTER COLUMN audit_token SET INVISIBLE;
~~~

**Bước 7 — Kiểm tra metadata.**

~~~sql
SHOW CREATE TABLE lab_feature_flags;

SELECT COLUMN_NAME, COLUMN_DEFAULT, EXTRA
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'lab_feature_flags'
ORDER BY ORDINAL_POSITION;
~~~

Xác định default expression và thuộc tính INVISIBLE trong kết quả.

**Bước 8 — Dọn lab.**

~~~sql
DROP TABLE lab_feature_flags;
~~~

Chỉ xóa bảng lab vừa tạo sau khi đã quan sát xong kết quả.

**Kết quả cần đạt:** tạo được expression default, hiểu thời điểm MySQL áp dụng default, phân biệt NULL với bỏ qua cột, chứng minh invisible column bị loại khỏi SELECT * và INSERT ngầm, đồng thời xác minh được metadata cùng điều kiện phiên bản.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Server báo lỗi cú pháp ở DEFAULT (expression) | MySQL thấp hơn 8.0.13 hoặc biểu thức không hợp lệ | Kiểm tra VERSION(), cú pháp ngoặc và giới hạn expression default |
| DEFAULT expression tham chiếu cột khác và bị từ chối | Default expression không được đọc giá trị cột cùng hàng | Dùng generated column hoặc tính giá trị trong DML |
| DEFAULT không chạy khi client truyền NULL | NULL tường minh là giá trị được cung cấp, không phải bỏ qua cột | Bỏ cột khỏi INSERT hoặc truyền DEFAULT |
| BLOB/TEXT/JSON không nhận default literal | Kiểu này yêu cầu default được viết dưới dạng expression trên phiên bản hỗ trợ | Dùng DEFAULT ('literal') trên MySQL 8.0.13+ hoặc khởi tạo ở ứng dụng |
| Cột invisible không xuất hiện trong SELECT * | Đây là hành vi dự kiến | Gọi tên cột tường minh nếu cần đọc |
| INSERT không có danh sách cột không ghi invisible column | Invisible column bị loại khỏi danh sách cột ngầm | Dùng DEFAULT/NULL phù hợp hoặc chỉ định cột tường minh |
| ALTER COLUMN SET INVISIBLE báo lỗi | Server thấp hơn 8.0.23 hoặc bảng không còn cột visible | Kiểm tra phiên bản và bảo đảm còn ít nhất một cột visible |
| ORM không đọc hoặc ghi cột invisible | ORM/schema introspection chưa hỗ trợ visibility | Kiểm tra phiên bản ORM, mapping và generated SQL |
| Ứng dụng nhận thêm trường sau khi chuyển VISIBLE | SELECT * bắt đầu trả cột mới | Đánh giá hợp đồng dữ liệu và triển khai client tương thích trước khi đổi visibility |

## 14. Nguyên tắc cần ghi nhớ

- Literal DEFAULT là giá trị cố định; expression default được đánh giá khi cột cần nhận giá trị mặc định.
- Expression default được hỗ trợ từ MySQL 8.0.13 và biểu thức phải đặt trong ngoặc.
- Expression default không được tham chiếu cột khác, subquery, biến hoặc stored function.
- BLOB, TEXT, GEOMETRY và JSON cần default expression được viết trong ngoặc trên phiên bản hỗ trợ.
- DEFAULT chỉ được áp dụng khi bỏ qua cột hoặc yêu cầu DEFAULT; NULL tường minh không tự chuyển thành default.
- Generated column phù hợp với giá trị dẫn xuất từ cột khác; DEFAULT phù hợp với giá trị khởi tạo.
- Invisible column được hỗ trợ từ MySQL 8.0.23, vẫn lưu dữ liệu và vẫn truy cập được bằng tên tường minh.
- SELECT * và các danh sách cột ngầm bỏ qua invisible column; INSERT tường minh vẫn có thể ghi cột đó.
- Invisible không phải bảo mật; dùng privilege hoặc view để kiểm soát truy cập dữ liệu.
- Kiểm tra server, replica, ORM, migration tool và ứng dụng trước khi dùng tính năng phụ thuộc phiên bản.
- DDL có implicit commit; chuẩn bị migration ngược và backup thay vì dựa vào ROLLBACK.

DEFAULT expression và invisible column là công cụ hữu ích để tiến hóa schema, nhưng chỉ an toàn khi mọi client hiểu cùng một hợp đồng dữ liệu. Hãy xác minh phiên bản MySQL, khai báo default có ý nghĩa, dùng danh sách cột tường minh và thử migration trên môi trường tương đương production trước khi triển khai.
