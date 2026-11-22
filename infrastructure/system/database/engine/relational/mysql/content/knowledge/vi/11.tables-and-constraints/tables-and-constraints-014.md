# RENAME TABLE, đổi tên nguyên tử và các phụ thuộc cần kiểm tra

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Dùng RENAME TABLE và ALTER TABLE ... RENAME để đổi tên bảng.
- Đổi tên nhiều bảng trong một câu lệnh và hiểu thứ tự từ trái sang phải.
- Phân biệt atomic rename, atomic DDL khi server crash và transaction có thể ROLLBACK.
- Hoán đổi bảng cũ/mới theo mô hình blue/green.
- Hiểu metadata lock và lý do lệnh rename có thể phải chờ transaction khác.
- Kiểm tra ảnh hưởng đến foreign key, view, trigger, stored program, quyền truy cập và ứng dụng.
- Lập kế hoạch trước, xác minh sau và chuẩn bị phương án phục hồi.

Đổi tên bảng có vẻ chỉ là thay một định danh. Trong hệ thống đang chạy, tên bảng còn xuất hiện trong foreign key, view, trigger, stored procedure, quyền truy cập, mã ứng dụng, báo cáo, job định kỳ và công cụ vận hành. Một câu lệnh RENAME TABLE có thể hoàn tất rất nhanh nhưng vẫn làm ứng dụng lỗi nếu các phụ thuộc chưa được kiểm tra.

Bài học tập trung vào MySQL với InnoDB, đồng thời chỉ ra những giới hạn cần biết khi dùng storage engine khác hoặc di chuyển bảng giữa các database.

## 1. RENAME TABLE dùng để làm gì?

RENAME TABLE thay đổi tên một hoặc nhiều bảng. Dữ liệu và cấu trúc của bảng được giữ cùng đối tượng bảng; thao tác này không phải câu lệnh sao chép từng hàng sang một bảng mới.

Cú pháp cơ bản:

~~~sql
RENAME TABLE old_table TO new_table;
~~~

Có thể chỉ rõ database:

~~~sql
RENAME TABLE shop.orders TO shop.sales_orders;
~~~

Câu lệnh một bảng tương đương với:

~~~sql
ALTER TABLE shop.orders RENAME TO sales_orders;
~~~

RENAME TABLE có ưu điểm là có thể đổi tên nhiều bảng trong một câu lệnh. ALTER TABLE ... RENAME phù hợp khi chỉ cần đổi tên một bảng hoặc khi muốn kết hợp với các thay đổi ALTER TABLE khác theo cú pháp phiên bản MySQL đang dùng hỗ trợ.

Phân biệt các nhu cầu:

| Nhu cầu | Câu lệnh/cách làm |
|---|---|
| Đổi tên bảng | RENAME TABLE hoặc ALTER TABLE ... RENAME |
| Đổi tên cột | ALTER TABLE ... RENAME COLUMN |
| Đổi tên index | ALTER TABLE ... RENAME INDEX |
| Chuyển bảng sang database khác | RENAME TABLE db_old.t TO db_new.t |
| Đổi tên database | MySQL không có một câu lệnh RENAME DATABASE tổng quát |
| Đổi tên bảng tạm TEMPORARY | Dùng ALTER TABLE; RENAME TABLE không áp dụng cho TEMPORARY table |

Đổi tên bảng không tự sửa mọi câu SQL trong ứng dụng. MySQL có thể cập nhật một số metadata quan hệ, nhưng tên được viết trong view, stored program, event, trigger body hoặc mã ứng dụng vẫn cần được rà soát.

## 2. Đổi tên một bảng

Giả sử bảng hiện tại là shop.customer_old và muốn đổi thành shop.customer:

~~~sql
RENAME TABLE shop.customer_old TO shop.customer;
~~~

Nếu đang chọn đúng database bằng USE, có thể bỏ tiền tố database:

~~~sql
USE shop;

RENAME TABLE customer_old TO customer;
~~~

Tên database và bảng nên được đặt nhất quán. Nếu tên chứa từ khóa hoặc ký tự đặc biệt, cần dùng dấu nháy ngược để quote identifier. Trong ví dụ thực hành, ưu tiên tên không phải từ khóa để tránh nhầm lẫn.

Trước khi chạy, xác nhận bảng nguồn tồn tại và tên đích chưa bị chiếm:

~~~sql
SHOW TABLES FROM shop LIKE 'customer_old';
SHOW TABLES FROM shop LIKE 'customer';
~~~

Có thể kiểm tra metadata:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME IN ('customer_old', 'customer');
~~~

Nếu tên đích đã tồn tại, câu lệnh rename thông thường thất bại. Không nên xóa bảng đích chỉ để giải phóng tên nếu chưa xác định đó là bảng nào và dữ liệu có cần giữ hay không.

## 3. Đổi tên nhiều bảng trong một câu lệnh

RENAME TABLE cho phép nhiều cặp tên trong cùng một câu lệnh:

~~~sql
RENAME TABLE
    shop.customer_old TO shop.customer,
    shop.order_old TO shop.sales_order,
    shop.order_item_old TO shop.sales_order_item;
~~~

Các thao tác được xử lý từ trái sang phải. Khi câu lệnh gặp lỗi, MySQL không áp dụng một phần các thay đổi của câu lệnh rename đó.

Điều này hữu ích khi một lần phát hành cần đổi tên đồng bộ một nhóm bảng. Ví dụ, ứng dụng mới chỉ được triển khai khi cả bảng đơn hàng và bảng chi tiết đều có tên mới.

### 3.1. Hoán đổi hai tên bảng

Giả sử có hai bảng:

- shop.current_data: bảng đang được ứng dụng sử dụng.
- shop.next_data: bảng mới đã được chuẩn bị.

Muốn đổi tên để current_data nhận nội dung của next_data, cần giải phóng tên đích trước. Dùng một tên trung gian chưa tồn tại:

~~~sql
RENAME TABLE
    shop.current_data TO shop.swap_temp,
    shop.next_data TO shop.current_data,
    shop.swap_temp TO shop.next_data;
~~~

Vì các bước chạy từ trái sang phải:

1. current_data được đổi thành swap_temp.
2. next_data được đổi thành current_data.
3. swap_temp được đổi thành next_data.

Sau câu lệnh, tên current_data trỏ đến đối tượng bảng vốn mang tên next_data trước khi hoán đổi. Tên next_data trỏ đến bảng cũ.

Tên trung gian phải chưa tồn tại. Hãy dùng tên có quy ước rõ, tránh một tên tạm có thể bị job hoặc migration khác tạo ra cùng lúc.

### 3.2. Thay bảng production bằng bảng đã chuẩn bị

Một mẫu thường gặp là đổi bảng live sang tên backup rồi đưa bảng candidate vào tên live:

~~~sql
RENAME TABLE
    shop.orders TO shop.orders_before_release,
    shop.orders_candidate TO shop.orders;
~~~

Cả hai thay đổi nằm trong một câu lệnh. Ứng dụng không phải quan sát trạng thái trung gian trong đó orders không tồn tại giữa hai lệnh riêng biệt.

Tuy nhiên, đây mới chỉ là thao tác đổi tên. Trước khi thực hiện, phải xác nhận:

- orders_candidate có đúng cấu trúc, index, constraint và dữ liệu.
- Dữ liệu mới đã được đồng bộ đến thời điểm cutover.
- Các transaction ghi đang chạy đã được xử lý theo kế hoạch.
- Foreign key tham chiếu đến orders đã được phân tích.
- View, trigger, quyền truy cập và ứng dụng tương thích với bảng mới.
- Có kế hoạch xử lý dữ liệu phát sinh sau cutover nếu cần quay lại bảng cũ.

Một bảng orders_before_release vẫn nằm trên cùng MySQL instance và cùng miền lỗi lưu trữ. Nó không thay thế backup độc lập.

## 4. Hiểu đúng tính nguyên tử của RENAME TABLE

Từ “atomic” thường được dùng cho nhiều bảo đảm khác nhau. Cần tách ba khái niệm.

### 4.1. Tính nguyên tử của câu lệnh rename

Với một câu lệnh RENAME TABLE nhiều cặp tên, MySQL thực hiện chuỗi đổi tên theo thứ tự. Nếu một thao tác trong câu lệnh gặp lỗi, câu lệnh thất bại và không để lại một phần thay đổi của chuỗi rename.

Trong điều kiện khóa bảng phù hợp, thao tác rename diễn ra nguyên tử: session khác không truy cập được các bảng trong khi quá trình đổi tên đang thực hiện. Client có thể quan sát trạng thái trước câu lệnh hoặc trạng thái sau khi câu lệnh hoàn tất, không quan sát từng bước trung gian của cùng câu lệnh.

Điều này hữu ích cho đổi tên nhóm bảng hoặc cutover bảng cũ/mới. Nó không có nghĩa mọi truy vấn đang chạy sẽ tự động thành công; truy vấn có thể phải chờ metadata lock hoặc nhận lỗi nếu ứng dụng gọi tên cũ sau khi rename hoàn tất.

### 4.2. Atomic DDL khi server crash

MySQL 8.x hỗ trợ atomic DDL cho các thao tác và storage engine được hỗ trợ. Với RENAME TABLE, tính nguyên tử khi server dừng bất thường chỉ được bảo đảm khi tất cả bảng được nêu trong câu lệnh dùng storage engine hỗ trợ atomic DDL. Trong MySQL 8.4, InnoDB là storage engine hỗ trợ atomic DDL cho bảng.

Ví dụ, một câu lệnh đổi tên nhiều bảng đều dùng InnoDB có thể được phục hồi như một thao tác hoàn tất hoặc được rollback trong quá trình crash recovery. Nếu câu lệnh chứa bảng thuộc engine không hỗ trợ atomic DDL, không được giả định có cùng bảo đảm crash-safe cho toàn bộ thao tác.

Kiểm tra engine của các bảng trước khi dựa vào atomic DDL:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME IN (
      'orders',
      'orders_candidate',
      'orders_before_release'
  );
~~~

Atomic DDL là thuộc tính của thao tác DDL và storage engine, không phải lời hứa rằng mọi engine, mọi phiên bản MySQL và mọi hệ thống lưu trữ đều có cùng hành vi. Hãy xác nhận đúng phiên bản server đang vận hành.

### 4.3. Atomic DDL không phải transactional DDL

RENAME TABLE gây implicit commit. Nếu session đang có transaction mở, MySQL kết thúc transaction đó trước khi thực hiện câu lệnh DDL. Không thể đặt RENAME TABLE trong một transaction rồi dùng ROLLBACK để khôi phục tên cũ.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE shop.orders
SET order_status = 'review'
WHERE order_id = 1001;

RENAME TABLE shop.orders TO shop.orders_old;

ROLLBACK;
~~~

Không được kỳ vọng ROLLBACK sẽ hoàn tác việc đổi tên bảng. Transaction trước đó cũng đã bị implicit commit trước khi RENAME TABLE chạy.

Nếu cần đổi lại tên, phải thực hiện một câu lệnh RENAME TABLE mới sau khi xác minh trạng thái:

~~~sql
RENAME TABLE shop.orders_old TO shop.orders;
~~~

Câu lệnh đổi tên ngược chỉ khôi phục tên. Nó không hoàn tác các dữ liệu đã được ghi vào bảng, các thay đổi ứng dụng, hoặc các tác động nghiệp vụ xảy ra sau lần cutover đầu tiên.

## 5. Metadata lock và thời gian chờ

MySQL sử dụng metadata locking (MDL) để bảo vệ định nghĩa bảng và các database object khi nhiều session cùng hoạt động.

Một transaction đã truy cập bảng có thể giữ metadata lock đến khi transaction kết thúc. Vì vậy, RENAME TABLE có thể phải chờ một transaction khác COMMIT hoặc ROLLBACK trước khi lấy được lock cần thiết.

Ví dụ session A:

~~~sql
START TRANSACTION;

SELECT *
FROM shop.orders
WHERE order_id = 1001;

-- Transaction vẫn mở, chưa COMMIT hoặc ROLLBACK.
~~~

Trong lúc đó, session B chạy:

~~~sql
RENAME TABLE shop.orders TO shop.orders_old;
~~~

Session B có thể chờ metadata lock do session A đang giữ. Một transaction đọc cũng có thể giữ MDL; không chỉ transaction UPDATE mới gây chặn DDL.

### 5.1. Tác động trong giờ cao điểm

Nếu rename chờ lâu:

- Migration hoặc release pipeline có thể bị treo.
- Các truy vấn mới cần metadata lock có thể xếp hàng phía sau yêu cầu DDL đang chờ.
- Connection pool có thể tăng số request chờ.
- Latency ứng dụng có thể tăng dù bản thân thao tác rename chỉ là thay đổi metadata.

Do đó, một lệnh rename rất ngắn vẫn có thể gây gián đoạn nếu trước đó có transaction mở lâu.

Trước khi triển khai:

- Kiểm tra transaction đang mở và thời gian tồn tại của chúng.
- Xử lý transaction bị treo hoặc session bỏ quên transaction.
- Chọn thời điểm tải thấp nếu nghiệp vụ yêu cầu.
- Đặt thời gian chờ phù hợp và chuẩn bị cách hủy migration nếu không thể lấy lock.
- Không chạy nhiều migration đổi tên có quan hệ phụ thuộc cùng lúc.

### 5.2. Kiểm tra metadata lock

MySQL 8.x có thể quan sát metadata lock qua Performance Schema:

~~~sql
SELECT
    ml.OBJECT_SCHEMA,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS,
    th.PROCESSLIST_ID,
    th.PROCESSLIST_USER,
    th.PROCESSLIST_TIME,
    th.PROCESSLIST_STATE,
    th.PROCESSLIST_INFO
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS th
    ON th.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.OBJECT_TYPE = 'TABLE'
  AND ml.OBJECT_SCHEMA = 'shop'
ORDER BY
    ml.LOCK_STATUS,
    ml.OBJECT_NAME;
~~~

Tập trung vào LOCK_STATUS = 'PENDING' để tìm yêu cầu đang chờ. Các hàng GRANTED cho biết lock đã được cấp. Cần có quyền đọc Performance Schema phù hợp.

Cũng có thể kiểm tra session:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Không vội KILL một session chỉ vì nó xuất hiện trong danh sách. Trước tiên xác định transaction thuộc ứng dụng nào, có đang xử lý nghiệp vụ quan trọng không và tác động của việc hủy.

### 5.3. Thứ tự lấy metadata lock

Trong RENAME TABLE nhiều cặp, MySQL lấy metadata lock theo thứ tự tên bảng. Khi nhiều session chạy các thao tác đồng thời, thứ tự lấy lock có thể ảnh hưởng kết quả chờ hoặc thứ tự thao tác.

Đây là lý do không nên để nhiều deployment tự ý rename cùng một nhóm bảng. Hãy điều phối migration theo một luồng duy nhất và kiểm soát các transaction có thể giữ lock trên các bảng liên quan.

## 6. Foreign key và tên constraint sau khi đổi bảng

Foreign key là phụ thuộc quan trọng nhất cần kiểm tra khi đổi tên bảng.

InnoDB quản lý quan hệ tham chiếu trong metadata. Khi một bảng được đổi tên, các foreign key tham chiếu đến bảng đó được cập nhật để phản ánh tên mới, trừ trường hợp phát sinh xung đột tên constraint. Nếu có xung đột, RENAME TABLE thất bại.

Ví dụ bảng order_item tham chiếu sales_order:

~~~sql
CREATE TABLE shop.sales_order (
    order_id BIGINT UNSIGNED NOT NULL,
    order_no VARCHAR(40) NOT NULL,
    PRIMARY KEY (order_id),
    UNIQUE KEY uq_sales_order_no (order_no)
) ENGINE = InnoDB;

CREATE TABLE shop.order_item (
    order_item_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (order_item_id),
    KEY idx_order_item_order (order_id),
    CONSTRAINT fk_order_item_sales_order
        FOREIGN KEY (order_id)
        REFERENCES shop.sales_order (order_id)
) ENGINE = InnoDB;
~~~

Đổi tên bảng cha:

~~~sql
RENAME TABLE shop.sales_order TO shop.customer_order;
~~~

Sau khi rename, kiểm tra định nghĩa bảng con:

~~~sql
SHOW CREATE TABLE shop.order_item;
~~~

Có thể truy vấn metadata:

~~~sql
SELECT
    CONSTRAINT_SCHEMA,
    TABLE_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_SCHEMA,
    REFERENCED_TABLE_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = 'shop'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
~~~

### 6.1. Tên foreign key tự sinh

MySQL tự điều chỉnh một số tên constraint theo quy tắc:

- Tên foreign key được tạo nội bộ hoặc tên do người dùng đặt bắt đầu bằng tiền tố tên bảng cũ + '_ibfk_' có thể được đổi để phản ánh tên bảng mới.
- Các foreign key trỏ đến bảng được đổi tên cũng được cập nhật.
- Nếu tên constraint mới bị trùng với một constraint đã tồn tại, thao tác rename có thể thất bại. Khi đó cần xử lý bằng cách DROP và tạo lại foreign key có tên rõ ràng.

Với constraint được đặt tên theo quy ước khác, đừng suy đoán tên sẽ tự thay đổi. Kiểm tra SHOW CREATE TABLE trước và sau migration.

### 6.2. CHECK constraint

Các CHECK constraint có tên bắt đầu bằng tiền tố tên bảng + '_chk_' cũng được MySQL điều chỉnh theo tên bảng mới trong trường hợp được nhận diện là tên nội bộ hoặc theo quy ước đó.

Kiểm tra bằng:

~~~sql
SHOW CREATE TABLE shop.customer_order;
~~~

Không viết script phụ thuộc vào một tên constraint được tự sinh. Nên đặt tên constraint có ý nghĩa, lưu định nghĩa trong migration và xác minh metadata sau khi đổi tên.

### 6.3. Lưu ý đặc biệt khi hoán đổi bảng

Đây là điểm rất quan trọng với blue/green table swap.

Giả sử order_item có foreign key trỏ đến orders. Khi chạy:

~~~sql
RENAME TABLE
    shop.orders TO shop.orders_old,
    shop.orders_candidate TO shop.orders;
~~~

Foreign key đang trỏ đến đối tượng bảng orders cũ sẽ được cập nhật để tham chiếu orders_old. MySQL theo dõi đối tượng được tham chiếu và cập nhật metadata khi bảng được đổi tên. Nó không tự hiểu rằng ứng dụng muốn chuyển toàn bộ quan hệ sang đối tượng orders_candidate mới.

Do đó, sau swap, order_item có thể vẫn tham chiếu đến bảng cũ mang tên orders_old. Nếu muốn các hàng con tham chiếu đến bảng mới, phải thiết kế migration foreign key riêng, có thể bao gồm:

1. Xác định tất cả bảng con đang tham chiếu orders.
2. Chuẩn bị khóa và dữ liệu tương thích ở bảng mới.
3. Lập kế hoạch DROP/ADD lại các foreign key theo đúng thứ tự.
4. Kiểm tra dữ liệu mồ côi trước khi tạo lại constraint.
5. Thực hiện cutover và xác minh metadata sau đó.

Không tắt foreign_key_checks chỉ để làm cho swap chạy qua. Việc bật lại foreign_key_checks không tự quét và xác nhận toàn bộ dữ liệu đã ghi khi kiểm tra bị tắt.

## 7. View, trigger và stored program

### 7.1. View

View lưu định nghĩa truy vấn tham chiếu đến các bảng hoặc view khác. Nếu một bảng được đổi tên hoặc thay đổi theo cách làm mất đối tượng được view tham chiếu, view có thể trở nên không hợp lệ.

Kiểm tra định nghĩa:

~~~sql
SHOW CREATE VIEW shop.v_order_summary;
~~~

MySQL cung cấp CHECK TABLE để kiểm tra view có bị invalid hay không:

~~~sql
CHECK TABLE shop.v_order_summary;
~~~

Tìm view trong metadata:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    VIEW_DEFINITION
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = 'shop';
~~~

Không chỉ dựa vào việc câu lệnh RENAME TABLE thành công. Hãy chạy lại các truy vấn đọc view, kiểm tra view lồng nhau và view được ứng dụng sử dụng.

Nếu cần đổi định nghĩa view, hãy lưu CREATE OR REPLACE VIEW trong migration để có thể triển khai lặp lại và review.

### 7.2. Trigger

Trigger gắn với một bảng cụ thể. Khi đổi tên bảng trong cùng schema, cần kiểm tra trigger vẫn gắn với bảng đúng và trigger body có còn tham chiếu đến các bảng liên quan hợp lệ hay không.

Xem trigger:

~~~sql
SHOW TRIGGERS FROM shop;
~~~

Hoặc truy vấn:

~~~sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_OBJECT_SCHEMA,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    EVENT_MANIPULATION,
    ACTION_STATEMENT
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE EVENT_OBJECT_SCHEMA = 'shop'
ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME;
~~~

Lưu ý: nếu di chuyển một bảng có trigger sang database khác bằng RENAME TABLE, MySQL từ chối thao tác với lỗi ER_TRG_IN_WRONG_SCHEMA. Cần xử lý trigger và kế hoạch chuyển schema riêng.

Trigger name thuộc namespace của schema. Khi tạo bảng candidate có trigger, phải bảo đảm tên trigger không xung đột với trigger hiện có. Trong table swap, kiểm tra cả trigger đang gắn với bảng cũ và bảng mới.

### 7.3. Stored procedure, function và event

Các stored program hoặc event có thể chứa SQL tham chiếu đến tên bảng. Đừng giả định MySQL sẽ sửa mọi chuỗi SQL trong thân procedure, function hoặc event khi đổi tên bảng.

Kiểm tra định nghĩa:

~~~sql
SHOW CREATE PROCEDURE shop.recalculate_order;
SHOW CREATE FUNCTION shop.order_total;
SHOW CREATE EVENT shop.refresh_order_summary;
~~~

Có thể tìm một số tham chiếu trong metadata:

~~~sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'shop';

SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    STATUS,
    EVENT_DEFINITION
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'shop';
~~~

Các định nghĩa có thể cần quyền phù hợp để xem đầy đủ. Hãy kiểm tra source migration, repository và cấu hình triển khai để tìm SQL động, tên bảng được ghép từ chuỗi hoặc tên được lưu trong cấu hình.

## 8. Quyền truy cập không tự chuyển theo tên mới

RENAME TABLE yêu cầu quyền:

- ALTER và DROP trên bảng gốc.
- CREATE và INSERT trên tên bảng đích.

Nếu di chuyển sang database khác, quyền cần có ở các database tương ứng.

Một điểm dễ bỏ sót: các quyền được GRANT trực tiếp cho tên bảng hoặc view cũ không tự chuyển sang tên mới. Cần cấp lại quyền trên tên mới.

Ví dụ xem quyền hiện tại:

~~~sql
SHOW GRANTS FOR 'app_reader'@'10.%';
~~~

Cấp lại quyền đọc cho bảng mới:

~~~sql
GRANT SELECT
ON shop.customer_order
TO 'app_reader'@'10.%';
~~~

Ví dụ cấp quyền cho tài khoản ứng dụng:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON shop.orders
TO 'shop_runtime'@'10.%';
~~~

Các tài khoản, host và quyền trong ví dụ chỉ minh họa. Hãy lấy đúng account từ môi trường triển khai.

Nếu dùng quyền ở cấp database thay vì table-level, phạm vi quyền có thể vẫn bao phủ tên mới. Tuy vậy, phải xác minh bằng SHOW GRANTS và đăng nhập thử bằng đúng tài khoản runtime. Không kiểm tra chỉ bằng tài khoản quản trị vì tài khoản đó có thể nhìn thấy bảng dù ứng dụng không có quyền.

## 9. Di chuyển bảng sang database khác

RENAME TABLE có thể chuyển một bảng giữa hai database:

~~~sql
RENAME TABLE
    shop.orders TO shop_archive.orders;
~~~

Database đích phải tồn tại và tài khoản cần có quyền tương ứng.

Một số giới hạn cần nhớ:

- Nếu bảng có trigger, việc chuyển sang database khác bị từ chối với lỗi ER_TRG_IN_WRONG_SCHEMA.
- View có thể được đổi tên trong cùng database, nhưng không thể chuyển sang database khác bằng RENAME TABLE.
- Nếu database đích nằm trên filesystem khác, kết quả phụ thuộc nền tảng và thao tác filesystem của hệ điều hành.
- Quyền được cấp riêng cho tên bảng cũ không tự chuyển sang tên mới.
- Phải kiểm tra foreign key, view, routine, event và code ứng dụng có tham chiếu đến schema cũ.

Không xem việc chuyển toàn bộ bảng từ database A sang database B bằng nhiều RENAME TABLE là một lệnh đổi tên database thực sự. Database cũ vẫn tồn tại, chỉ còn không có các bảng đã chuyển. Các object khác và cấu hình liên quan vẫn cần được xử lý riêng.

## 10. Case sensitivity của tên bảng

Cách MySQL so sánh tên database và table phụ thuộc hệ điều hành và biến lower_case_table_names.

Kiểm tra:

~~~sql
SELECT
    @@lower_case_table_names AS lower_case_table_names,
    @@lower_case_file_system AS lower_case_file_system;
~~~

Giá trị thường gặp:

| Giá trị lower_case_table_names | Hành vi |
|---:|---|
| 0 | Lưu tên theo chữ hoa/thường khai báo và so sánh có phân biệt hoa/thường |
| 1 | Lưu tên chữ thường và so sánh không phân biệt hoa/thường |
| 2 | Lưu theo kiểu chữ khai báo nhưng so sánh chữ thường; chỉ phù hợp filesystem không phân biệt hoa/thường |

Mặc định thường là 1 trên Windows, 0 trên Linux/Unix và 2 trên macOS, nhưng cần kiểm tra giá trị thực tế. Biến này được quyết định khi khởi tạo MySQL server và không thể tùy ý đổi sau đó.

Để tránh lỗi khi triển khai giữa Windows và Linux, nên dùng tên bảng chữ thường nhất quán. Ví dụ, luôn dùng orders và order_item thay vì lúc gọi Orders, lúc gọi orders.

## 11. Quy trình triển khai rename an toàn

Một migration đổi tên bảng nên được quản lý như một thay đổi API nội bộ của database. Tên bảng được ứng dụng và các database object sử dụng; đổi tên có thể phá vỡ tương thích nếu code cũ vẫn còn chạy.

### Bước 1: Kiểm kê phụ thuộc

Ghi nhận:

- SHOW CREATE TABLE của bảng nguồn và bảng đích.
- Storage engine của tất cả bảng trong câu lệnh.
- Foreign key đi vào và đi ra.
- View, trigger, procedure, function và event liên quan.
- Table-level grants.
- Tất cả repository, service, job, dashboard, ETL và script sử dụng tên bảng.
- Transaction dài, connection pool và prepared statement đang hoạt động.

Truy vấn tìm foreign key tham chiếu đến bảng:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    CONSTRAINT_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_SCHEMA,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE REFERENCED_TABLE_SCHEMA = 'shop'
  AND REFERENCED_TABLE_NAME = 'orders';
~~~

Truy vấn tìm trigger trên bảng:

~~~sql
SELECT
    TRIGGER_NAME,
    EVENT_OBJECT_TABLE,
    ACTION_STATEMENT
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE EVENT_OBJECT_SCHEMA = 'shop'
  AND EVENT_OBJECT_TABLE = 'orders';
~~~

### Bước 2: Chuẩn bị ứng dụng tương thích

Nếu ứng dụng đang chạy nhiều phiên bản, hãy triển khai code có thể làm việc trong giai đoạn chuyển đổi. Một số chiến lược:

- Tạo một phiên bản ứng dụng có thể đọc tên mới và cũ trong thời gian migration.
- Dùng một lớp repository/configuration tập trung tên bảng.
- Cập nhật view hoặc lớp tương thích nếu phù hợp với kiến trúc.
- Đồng bộ các worker, scheduler, batch job và consumer trước khi cutover.

Không đổi tên bảng khi vẫn còn một phiên bản ứng dụng chắc chắn truy vấn tên cũ mà không có lớp tương thích.

### Bước 3: Kiểm tra metadata lock và trạng thái vận hành

Xác định transaction đang giữ lock. Chờ hoặc xử lý các transaction đó theo quy trình vận hành.

Xác nhận:

- Có backup phù hợp với mức độ rủi ro.
- Replica và replication filter đã được kiểm tra.
- Không có migration khác đang sửa cùng nhóm bảng.
- Đã xác định thời gian chờ tối đa và người phụ trách.
- Đã có câu lệnh kiểm chứng sau khi đổi tên.

### Bước 4: Chạy một câu lệnh RENAME TABLE

Ví dụ:

~~~sql
RENAME TABLE
    shop.orders TO shop.orders_legacy,
    shop.orders_next TO shop.orders;
~~~

Không tách thành hai lệnh độc lập nếu mục tiêu là tránh khoảng thời gian tên orders không tồn tại. Câu lệnh nhiều cặp giúp các bước đổi tên diễn ra cùng một thao tác.

### Bước 5: Xác minh ngay sau rename

Kiểm tra bảng:

~~~sql
SHOW TABLES FROM shop LIKE 'orders';
SHOW TABLES FROM shop LIKE 'orders_legacy';

SHOW CREATE TABLE shop.orders;
SHOW INDEX FROM shop.orders;
~~~

Kiểm tra số hàng và dữ liệu quan trọng:

~~~sql
SELECT COUNT(*) AS row_count
FROM shop.orders;

SELECT order_status, COUNT(*) AS row_count
FROM shop.orders
GROUP BY order_status;
~~~

Kiểm tra foreign key:

~~~sql
SELECT
    TABLE_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = 'shop'
  AND REFERENCED_TABLE_NAME IS NOT NULL;
~~~

Kiểm tra view:

~~~sql
CHECK TABLE shop.v_order_summary;
~~~

Kiểm tra quyền bằng đúng tài khoản ứng dụng, không chỉ bằng tài khoản DBA. Chạy smoke test các luồng đọc/ghi quan trọng và theo dõi lỗi ứng dụng, slow query, replica lag cùng log MySQL.

### Bước 6: Hoàn tất phụ thuộc

Sau khi bảng đã có tên mới:

- Cập nhật hoặc tạo lại view.
- Cập nhật stored procedure, function và event.
- Kiểm tra trigger và trigger body.
- Tạo lại table-level grants.
- Triển khai code chỉ dùng tên mới.
- Cập nhật migration tiếp theo, tài liệu vận hành và dashboard.
- Giữ bảng cũ trong thời hạn rollback đã định, rồi mới xóa khi được xác nhận.

Không DROP bảng cũ ngay sau cutover. Chờ đến khi xác nhận dữ liệu, quan hệ và ứng dụng đã hoạt động đúng.

## 12. Blue/green table swap và giới hạn rollback

Blue/green table swap là kỹ thuật chuẩn bị một bảng mới trước, sau đó đổi tên để bảng mới nhận tên production. Nó hữu ích khi muốn giảm thời gian cutover sau một quá trình chuẩn bị dữ liệu dài.

Một quy trình khái quát:

~~~mermaid
flowchart TD
    A[Tạo orders_candidate] --> B[Copy và đồng bộ dữ liệu]
    B --> C[Kiểm tra cấu trúc, index, constraint và dữ liệu]
    C --> D[Kiểm tra FK, view, trigger và quyền]
    D --> E[Chặn hoặc điều phối ghi trong cutover]
    E --> F[RENAME TABLE trong một câu lệnh]
    F --> G[Smoke test và xác minh quan hệ]
    G --> H{Kết quả đạt?}
    H -->|Có| I[Theo dõi rồi kết thúc thời gian giữ bảng cũ]
    H -->|Không| J[Đánh giá rollback hoặc roll forward]
~~~

### 12.1. Bảng candidate phải sẵn sàng trước cutover

Bảng candidate cần có:

- Schema tương thích với ứng dụng.
- Index và constraint cần thiết.
- Dữ liệu đã được sao chép và đồng bộ.
- Trigger phù hợp.
- Các phụ thuộc FK được lên kế hoạch.
- Quyền truy cập sẽ được cấp cho tên production sau swap.

Nếu dữ liệu vẫn đang được ghi vào bảng cũ trong khi copy, cần có cơ chế đồng bộ thay đổi: tạm dừng ghi, dual-write có kiểm soát, change capture hoặc một chiến lược khác đã được kiểm thử. Chỉ copy một lần rồi rename có thể làm mất các cập nhật phát sinh sau thời điểm copy.

### 12.2. Rollback không đơn giản là đổi tên ngược

Giả sử đã chạy:

~~~sql
RENAME TABLE
    shop.orders TO shop.orders_old,
    shop.orders_candidate TO shop.orders;
~~~

Sau đó ứng dụng tiếp tục ghi vào shop.orders mới. Nếu đổi tên ngược ngay:

~~~sql
RENAME TABLE
    shop.orders TO shop.orders_failed,
    shop.orders_old TO shop.orders;
~~~

Các bản ghi mới ghi vào orders sau cutover sẽ nằm trong orders_failed. Chúng không tự xuất hiện trong orders_old.

Do đó, rollback bằng rename chỉ an toàn khi đã xác định cách bảo toàn hoặc đồng bộ các ghi phát sinh sau cutover. Có thể cần:

- Tạm dừng ghi trước khi rollback.
- Đối chiếu và chuyển các thay đổi mới sang bảng cũ.
- Chạy migration bù hoặc roll forward.
- Dùng log thay đổi/CDC để phát lại các giao dịch cần thiết.

Nếu dữ liệu đã phát sinh và không thể đảo ngược an toàn, roll forward thường phù hợp hơn việc đổi tên ngược một cách máy móc.

### 12.3. Không dùng bảng cũ làm backup duy nhất

Bảng orders_old vẫn nằm trong cùng instance, cùng ổ đĩa hoặc cùng cụm lưu trữ. Nếu instance hoặc storage gặp sự cố, cả hai bảng có thể cùng bị ảnh hưởng.

Với thay đổi có rủi ro, hãy có backup độc lập và xác nhận khả năng restore. Backup cần phù hợp RPO/RTO và phải được kiểm tra phục hồi theo quy trình vận hành.

## 13. Lỗi thường gặp và cách xử lý

| Tình huống | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Table already exists | Tên đích đã được sử dụng | SHOW TABLES, kiểm tra object đích |
| Table doesn't exist | Sai schema, sai tên hoặc sai chữ hoa/thường | SHOW TABLES, kiểm tra @@lower_case_table_names |
| Access denied | Thiếu ALTER/DROP trên bảng nguồn hoặc CREATE/INSERT trên đích | SHOW GRANTS |
| Lock wait / metadata lock timeout | Transaction khác đang giữ MDL | performance_schema.metadata_locks, SHOW FULL PROCESSLIST |
| Trigger in wrong schema | Di chuyển bảng có trigger sang database khác | INFORMATION_SCHEMA.TRIGGERS |
| Foreign key constraint name conflict | Tên FK sau khi đổi bị trùng | SHOW CREATE TABLE các bảng liên quan |
| View không hoạt động | View tham chiếu đến tên bảng cũ hoặc object bị invalid | CHECK TABLE, SHOW CREATE VIEW |
| Ứng dụng báo table not found | Code, worker hoặc job vẫn gọi tên cũ | Tìm kiếm SQL trong repository và log |
| Ứng dụng mất quyền | Table-level grants chưa được cấp lại cho tên mới | SHOW GRANTS và thử bằng runtime account |
| Replica lỗi sau deploy | Schema, replication filter hoặc migration không đồng nhất | SHOW REPLICA STATUS, log replica |

Không xử lý lỗi bằng cách xóa object hoặc tắt constraint ngay lập tức. Hãy xác định object nào đang được ứng dụng sử dụng và phụ thuộc nào sẽ bị tác động.

## 14. Checklist trước và sau khi đổi tên

### Trước khi chạy

- [ ] Đúng server, database và bảng nguồn.
- [ ] Tên đích và tên trung gian chưa bị chiếm.
- [ ] Đã xác định engine của mọi bảng trong câu lệnh.
- [ ] Đã kiểm tra transaction và metadata lock.
- [ ] Đã kiểm kê foreign key đi vào và đi ra.
- [ ] Đã kiểm tra view, trigger, routine, function và event.
- [ ] Đã kiểm tra table-level grants.
- [ ] Ứng dụng và worker đã tương thích với tên mới.
- [ ] Đã có kế hoạch đồng bộ dữ liệu và xử lý rollback.
- [ ] Đã có backup phù hợp với rủi ro.

### Sau khi chạy

- [ ] Tên cũ và tên mới đúng trạng thái mong đợi.
- [ ] SHOW CREATE TABLE và index đúng.
- [ ] Foreign key tham chiếu đúng đối tượng.
- [ ] CHECK constraint còn nguyên.
- [ ] View và trigger hoạt động đúng.
- [ ] Quyền runtime được xác minh.
- [ ] Smoke test đọc/ghi thành công.
- [ ] Replica theo kịp và không có lỗi replication.
- [ ] Dashboard, log, job và script đã dùng tên mới.
- [ ] Bảng cũ chỉ được xóa sau khi hết thời hạn rollback.

## 15. Bài tập thực hành

### Bài 1: Đổi tên một bảng

Tạo bảng customer_old trong database thực hành. Chèn vài hàng, đổi tên thành customer bằng RENAME TABLE. Xác nhận dữ liệu, index và AUTO_INCREMENT vẫn tồn tại.

### Bài 2: Đổi tên nhiều bảng

Tạo hai bảng orders_old và order_items_old. Dùng một câu lệnh RENAME TABLE để đổi cả hai tên. Sau đó thử tạo xung đột ở tên đích trên môi trường thực hành và quan sát rằng câu lệnh thất bại không để lại một phần rename.

### Bài 3: Hoán đổi bảng

Tạo orders_live và orders_candidate với dữ liệu khác nhau. Dùng tên trung gian để hoán đổi. Kiểm tra tên nào trỏ đến dữ liệu nào sau câu lệnh.

### Bài 4: Quan sát metadata lock

Mở transaction ở session A và SELECT một bảng nhưng chưa kết thúc transaction. Từ session B thử RENAME TABLE. Quan sát trạng thái chờ trong process list và Performance Schema. Kết thúc transaction A và quan sát rename tiếp tục.

### Bài 5: Kiểm tra foreign key

Tạo bảng cha và bảng con có FK. Đổi tên bảng cha, sau đó xem SHOW CREATE TABLE của bảng con và INFORMATION_SCHEMA.KEY_COLUMN_USAGE. Ghi nhận tên bảng được tham chiếu sau rename.

### Bài 6: Kiểm tra view và quyền

Tạo view trên bảng thử nghiệm và cấp SELECT trực tiếp cho một tài khoản trên bảng đó. Đổi tên bảng, chạy CHECK TABLE trên view, sau đó kiểm tra quyền của tài khoản và cấp lại quyền cho tên mới khi cần.

### Bài 7: Lập kế hoạch blue/green

Viết kế hoạch thay orders bằng orders_candidate. Liệt kê tất cả FK, view, trigger, table-level grants và consumer ứng dụng. Xác định cách đồng bộ dữ liệu trong lúc copy và cách bảo toàn các giao dịch sau cutover nếu phải rollback.

## Kết luận

RENAME TABLE là công cụ mạnh để đổi tên một hoặc nhiều bảng trong một thao tác. Khi dùng đúng điều kiện, nó giúp tránh trạng thái trung gian và hỗ trợ blue/green table swap. Tuy nhiên, atomic rename không thay thế transaction rollback, backup hoặc quy trình triển khai ứng dụng.

Trước khi đổi tên, hãy kiểm tra metadata lock, storage engine, foreign key, view, trigger, stored program, quyền truy cập và mọi consumer của tên bảng. Sau khi đổi tên, xác minh lại các quan hệ và quyền bằng metadata cùng tài khoản ứng dụng thực tế. Một lần cutover chỉ hoàn tất khi cả database lẫn các thành phần sử dụng nó đều hoạt động theo tên mới.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — RENAME TABLE Statement: https://dev.mysql.com/doc/refman/8.4/en/rename-table.html
- MySQL 8.4 Reference Manual — Atomic Data Definition Statement Support: https://dev.mysql.com/doc/refman/8.4/en/atomic-ddl.html
- MySQL 8.4 Reference Manual — Statements That Cause an Implicit Commit: https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html
- MySQL 8.4 Reference Manual — Metadata Locking: https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html
- MySQL 8.4 Reference Manual — MySQL 8.4 FAQ: Views: https://dev.mysql.com/doc/refman/8.4/en/faqs-views.html
- MySQL 8.4 Reference Manual — Identifier Case Sensitivity: https://dev.mysql.com/doc/refman/8.4/en/identifier-case-sensitivity.html

