# AUTO-INC lock, innodb_autoinc_lock_mode và cấp khóa đồng thời

Cột AUTO_INCREMENT giúp MySQL tự cấp giá trị định danh khi INSERT. Khi nhiều transaction cùng thêm hàng vào một bảng, InnoDB phải phối hợp việc cấp số để tránh trùng giá trị và đáp ứng yêu cầu về tính xác định của replication. Cơ chế liên quan được gọi là AUTO-INC lock; hành vi khóa phụ thuộc vào biến innodb_autoinc_lock_mode.

InnoDB có ba chế độ:

- 0 (traditional): dùng AUTO-INC table lock cho mọi câu lệnh insert-like cần cấp giá trị tự động; khóa được giữ đến hết statement.
- 1 (consecutive): dùng AUTO-INC table lock cho bulk insert; simple insert chỉ giữ cơ chế đồng bộ cấp số trong thời gian cần thiết.
- 2 (interleaved): không dùng AUTO-INC table lock ở cấp statement; nhiều câu lệnh có thể cấp số xen kẽ.

MySQL 8.0 và 8.4 mặc định dùng mode 2. Chế độ này tăng khả năng đồng thời và phù hợp với row-based replication. Nếu dùng statement-based replication, mode 2 không bảo đảm thứ tự cấp AUTO_INCREMENT có thể tái tạo giống hệt ở replica.

Bài học thuộc phạm vi DATABASE_MYSQL: hiểu cơ chế khóa của InnoDB, dự đoán hành vi INSERT đồng thời, chọn cấu hình phù hợp với replication, và thiết kế khóa định danh không phụ thuộc vào giả định ID liên tục.

## 1. AUTO_INCREMENT và nhu cầu đồng bộ khi ghi đồng thời

Một cột AUTO_INCREMENT yêu cầu storage engine cấp giá trị mới khi INSERT không cung cấp giá trị tường minh phù hợp.

~~~sql
CREATE TABLE event_log_demo (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(40) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (event_id)
) ENGINE = InnoDB;

INSERT INTO event_log_demo (event_type)
VALUES ('LOGIN'), ('LOGOUT'), ('PURCHASE');
~~~

InnoDB cấp một giá trị event_id cho mỗi hàng. Khi chỉ có một session ghi dữ liệu, việc cấp số có vẻ đơn giản. Nhưng nếu nhiều session cùng INSERT, chúng phải phối hợp để không nhận cùng một giá trị.

Ví dụ hai transaction cùng ghi:

~~~sql
-- Session A
INSERT INTO event_log_demo (event_type)
VALUES ('A-1'), ('A-2'), ('A-3');

-- Session B
INSERT INTO event_log_demo (event_type)
VALUES ('B-1');
~~~

Tùy innodb_autoinc_lock_mode và loại statement, ID của Session B có thể phải chờ Session A hoàn tất, hoặc có thể được cấp xen giữa dãy ID của Session A.

AUTO-INC lock là một cơ chế nội bộ đặc biệt của InnoDB để điều phối việc cấp giá trị AUTO_INCREMENT. Nó khác với row lock dùng để bảo vệ một hàng dữ liệu, và khác metadata lock dùng để bảo vệ định nghĩa bảng.

## 2. AUTO-INC lock là gì?

AUTO-INC lock là khóa cấp bảng đặc biệt mà InnoDB dùng trong một số kiểu INSERT vào bảng có cột AUTO_INCREMENT.

Mục tiêu của khóa là điều phối việc cấp số giữa các statement đồng thời. Khóa này không đồng nghĩa toàn bộ bảng bị khóa cho mọi thao tác:

- SELECT thông thường vẫn có thể đọc theo quy tắc MVCC.
- UPDATE một hàng không cần cấp AUTO_INCREMENT không nhất thiết phải chờ AUTO-INC lock.
- Các statement insert-like khác cần cấp số có thể phải chờ tùy chế độ.
- Row lock vẫn được dùng riêng để bảo vệ dữ liệu hàng và constraint.

Điểm quan trọng là thời gian giữ AUTO-INC lock khác nhau giữa các chế độ. Với mode 0 và bulk insert ở mode 1, khóa cấp bảng được giữ đến khi statement kết thúc, không phải đến khi transaction COMMIT. Transaction vẫn có thể giữ row lock và các khóa khác tới COMMIT/ROLLBACK.

Không nên gọi AUTO-INC lock là table lock thông thường. Đây là một loại khóa nội bộ chuyên cho việc cấp AUTO_INCREMENT.

## 3. Simple insert và bulk insert

InnoDB phân biệt loại statement dựa trên việc số hàng cần chèn có thể xác định trước hay không.

### 3.1. Simple insert

Simple insert là loại statement mà số hàng dự kiến có thể biết trước khi statement bắt đầu xử lý. Ví dụ:

~~~sql
INSERT INTO event_log_demo (event_type)
VALUES ('LOGIN');

INSERT INTO event_log_demo (event_type)
VALUES ('LOGIN'), ('LOGOUT'), ('PURCHASE');

REPLACE INTO event_log_demo (event_id, event_type)
VALUES (10, 'REPLACED');
~~~

Với INSERT ... VALUES nhiều hàng, InnoDB có thể biết trước số hàng trong danh sách và có thể cấp trước một dải giá trị.

### 3.2. Bulk insert

Bulk insert là loại statement mà số hàng cần chèn không thể xác định trước một cách đơn giản tại thời điểm bắt đầu. Ví dụ:

~~~sql
INSERT INTO event_log_demo (event_type)
SELECT source_event_type
FROM incoming_event;

REPLACE INTO event_log_demo (event_id, event_type)
SELECT source_id, source_type
FROM legacy_event;

LOAD DATA INFILE '/var/lib/mysql-files/events.csv'
INTO TABLE event_log_demo
FIELDS TERMINATED BY ','
LINES TERMINATED BY '\n'
(event_type);
~~~

Với INSERT ... SELECT hoặc LOAD DATA, số hàng thực tế phụ thuộc vào kết quả đọc hoặc dữ liệu nhập. Vì vậy, cơ chế cấp số khác với simple insert.

### 3.3. Mixed-mode insert

Một statement có thể vừa cung cấp giá trị AUTO_INCREMENT tường minh cho một số hàng, vừa yêu cầu MySQL tự cấp cho các hàng khác.

~~~sql
INSERT INTO event_log_demo (event_id, event_type)
VALUES
    (NULL, 'AUTO-1'),
    (5000, 'EXPLICIT-5000'),
    (NULL, 'AUTO-2');
~~~

Đây là dạng mixed-mode insert. Việc cấp trước giá trị có thể dự trù nhiều hơn số giá trị cuối cùng thực sự dùng, dẫn tới khoảng trống trong dãy. Không dựa vào giả định rằng mọi ID được cấp đều xuất hiện trong bảng.

## 4. Ba chế độ innodb_autoinc_lock_mode

Biến innodb_autoinc_lock_mode điều khiển chiến lược khóa AUTO_INCREMENT của InnoDB.

| Giá trị | Tên | Hành vi chính |
|---:|---|---|
| 0 | traditional | AUTO-INC table lock cho mọi insert-like statement cần cấp số; giữ đến hết statement |
| 1 | consecutive | Simple insert dùng cơ chế cấp số ngắn; bulk insert dùng AUTO-INC table lock đến hết statement |
| 2 | interleaved | Không dùng AUTO-INC table lock cấp statement; các statement có thể cấp số xen kẽ |

Giá trị là cấu hình toàn cục của server và được xác định khi MySQL khởi động. Kiểm tra giá trị hiện tại:

~~~sql
SELECT @@GLOBAL.innodb_autoinc_lock_mode;
~~~

Hoặc:

~~~sql
SHOW VARIABLES LIKE 'innodb_autoinc_lock_mode';
~~~

Không nhầm giá trị này với autocommit hoặc transaction isolation level. innodb_autoinc_lock_mode điều khiển cách cấp ID tự động; nó không quyết định khi nào transaction commit và không thay thế row locking.

## 5. Mode 0: traditional

Ở mode 0, InnoDB dùng AUTO-INC table lock cho tất cả insert-like statement cần tạo giá trị AUTO_INCREMENT. Khóa được giữ đến hết statement.

~~~ini
[mysqld]
innodb_autoinc_lock_mode = 0
~~~

Đặc điểm:

- Các statement insert-like cần cấp ID trên cùng bảng được tuần tự hóa trong phạm vi statement.
- Giá trị do một statement cấp có tính liên tiếp theo quy tắc của mode truyền thống.
- Một INSERT khác cần cấp ID phải chờ statement đang giữ AUTO-INC lock kết thúc.
- Khả năng đồng thời thấp hơn, đặc biệt khi bulk insert chạy lâu.

Mode 0 có thể hữu ích trong môi trường cũ phụ thuộc vào thứ tự cấp số xác định với statement-based replication. Với hệ thống mới, thường không cần chọn mode 0 nếu đã dùng row-based replication và không có yêu cầu tương thích đặc biệt.

AUTO-INC lock vẫn chỉ là khóa cấp số. Các transaction có thể còn giữ row lock sau khi statement kết thúc cho tới khi COMMIT hoặc ROLLBACK.

## 6. Mode 1: consecutive

Mode 1 là chế độ thường được dùng trước MySQL 8.0. Nó cố gắng duy trì dãy ID liên tiếp cho mỗi statement nhưng cho phép simple insert đồng thời hơn.

~~~ini
[mysqld]
innodb_autoinc_lock_mode = 1
~~~

### 6.1. Simple insert ở mode 1

Với simple insert, số hàng cần chèn đã biết. InnoDB có thể cấp trước một khối ID bằng cơ chế đồng bộ ngắn, rồi nhả cơ chế đó mà không giữ AUTO-INC table lock đến hết statement.

Vì vậy, nhiều simple insert có thể tiến triển đồng thời hơn mode 0.

Ví dụ:

~~~sql
INSERT INTO event_log_demo (event_type)
VALUES ('A-1'), ('A-2'), ('A-3');
~~~

InnoDB có thể cấp một dải ba giá trị cho statement A. Statement B có thể cấp dải tiếp theo trong lúc A tiếp tục xử lý các bước còn lại, tùy lịch thực thi.

### 6.2. Bulk insert ở mode 1

Với bulk insert, InnoDB không biết trước chính xác số hàng cần cấp. Nó dùng AUTO-INC table lock và giữ khóa đến hết statement để bảo đảm các giá trị được cấp cho statement không bị xen bởi statement insert-like khác.

Ví dụ:

~~~sql
INSERT INTO event_log_demo (event_type)
SELECT event_type
FROM staging_event;
~~~

Trong lúc statement bulk này giữ AUTO-INC lock, một simple insert khác cần cấp AUTO_INCREMENT cho cùng bảng phải chờ đến khi statement bulk kết thúc.

Mode 1 là sự cân bằng giữa tính liên tiếp của ID theo statement và concurrency. Tuy nhiên, bulk insert dài vẫn có thể làm các insert khác chờ.

## 7. Mode 2: interleaved

Mode 2 không dùng AUTO-INC table lock cấp statement. Nhiều insert-like statement có thể cùng cấp giá trị AUTO_INCREMENT và các giá trị có thể xen kẽ.

~~~ini
[mysqld]
innodb_autoinc_lock_mode = 2
~~~

Ví dụ hai statement:

~~~sql
-- Session A
INSERT INTO event_log_demo (event_type)
SELECT event_type
FROM staging_event_a;

-- Session B
INSERT INTO event_log_demo (event_type)
VALUES ('B-1'), ('B-2');
~~~

Trong mode 2, ID của Session B có thể xuất hiện giữa các ID mà Session A nhận. Không có bảo đảm rằng các ID được tạo bởi một statement sẽ tạo thành một dải liên tiếp khi nhiều statement chạy đồng thời.

Ưu điểm:
- Giảm tuần tự hóa do AUTO-INC table lock.
- Tăng concurrency cho insert workload.
- Phù hợp với row-based replication.
- Là mặc định từ MySQL 8.0.

Giới hạn:
- Không bảo đảm dãy ID liên tiếp theo statement.
- Không an toàn cho statement-based replication khi cần tái tạo chính xác thứ tự cấp số.
- Không được dùng AUTO_INCREMENT như một số thứ tự nghiệp vụ không có khoảng trống.

Mode 2 không có nghĩa các ID bị trùng. InnoDB vẫn phối hợp bộ đếm để cấp giá trị duy nhất. Khác biệt nằm ở việc các statement có thể xen kẽ thứ tự cấp số.

## 8. So sánh mode 0, 1 và 2 theo loại statement

| Loại statement | Mode 0 | Mode 1 | Mode 2 |
|---|---|---|---|
| Simple INSERT ... VALUES | AUTO-INC lock đến hết statement | Cấp khối ID bằng cơ chế ngắn; không giữ table lock suốt statement | Có thể cấp xen kẽ |
| Multi-row INSERT ... VALUES | AUTO-INC lock đến hết statement | Simple insert; cấp số đã biết trước | Có thể cấp xen kẽ với statement khác |
| INSERT ... SELECT | AUTO-INC lock đến hết statement | AUTO-INC lock đến hết statement | Không có table lock cấp statement |
| REPLACE ... SELECT | AUTO-INC lock đến hết statement | AUTO-INC lock đến hết statement | Không có table lock cấp statement |
| LOAD DATA | AUTO-INC lock đến hết statement | AUTO-INC lock đến hết statement | Không có table lock cấp statement |

Bảng mô tả hành vi chính của InnoDB khi statement cần cấp AUTO_INCREMENT. Các chi tiết còn phụ thuộc dữ liệu đầu vào, giá trị tường minh, duplicate, rollback và các điều kiện của statement.

## 9. Ví dụ hai session: quan sát việc cấp số xen kẽ

Tạo bảng và nguồn dữ liệu:

~~~sql
CREATE TABLE auto_inc_target (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    label VARCHAR(40) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE auto_inc_source_a (
    label VARCHAR(40) NOT NULL
) ENGINE = InnoDB;

INSERT INTO auto_inc_source_a(label)
VALUES
    ('A-01'), ('A-02'), ('A-03'), ('A-04'), ('A-05'),
    ('A-06'), ('A-07'), ('A-08'), ('A-09'), ('A-10');
~~~

### 9.1. Session A

Chạy bulk insert:

~~~sql
INSERT INTO auto_inc_target(label)
SELECT label
FROM auto_inc_source_a;
~~~

Trên bảng lớn, statement này có thể chạy đủ lâu để Session B thực hiện một INSERT khác trong lúc A đang xử lý.

### 9.2. Session B

~~~sql
INSERT INTO auto_inc_target(label)
VALUES ('B-01');
~~~

### 9.3. Quan sát kết quả

~~~sql
SELECT id, label
FROM auto_inc_target
ORDER BY id;
~~~

- Mode 0: B cần chờ AUTO-INC lock của A kết thúc; các ID do A cấp được giữ liên tiếp theo statement.
- Mode 1: A là bulk insert nên giữ AUTO-INC lock đến hết statement; B chờ.
- Mode 2: B có thể được cấp ID trong khi A vẫn đang chạy; hàng B có thể nằm giữa dãy ID của A.

Thứ tự thực tế phụ thuộc timing và lịch chạy của server. Không dùng một kết quả cụ thể của lab làm bảo đảm cho mọi lần chạy. Mục tiêu là quan sát khả năng xen kẽ và thời gian chờ, không phải ép ra một dãy ID cố định.

Để thử lại với mode khác, cần thay cấu hình server và khởi động lại MySQL. Không thể đổi biến này bằng SET SESSION.

## 10. AUTO-INC lock được giữ đến statement hay transaction?

Đây là điểm dễ nhầm.

Trong mode 0, và trong bulk insert ở mode 1, AUTO-INC table lock được giữ đến hết statement. Khi statement hoàn tất, khóa AUTO-INC được nhả ngay cả khi transaction vẫn chưa COMMIT.

Ví dụ:

~~~sql
START TRANSACTION;

INSERT INTO event_log_demo(event_type)
VALUES ('A-1'), ('A-2');

-- Statement INSERT đã kết thúc.
-- Transaction vẫn đang mở.

-- Các thao tác khác của transaction A tiếp tục ở đây.

COMMIT;
~~~

Sau khi INSERT kết thúc, AUTO-INC lock cấp statement không nhất thiết còn giữ đến COMMIT. Tuy nhiên, transaction vẫn có thể giữ row lock, foreign key lock hoặc các khóa khác tới khi kết thúc.

Vì vậy, nếu một session khác chờ insert, hãy xác định nó đang chờ AUTO-INC lock hay một loại lock khác. Không kết luận mọi INSERT chờ đều do transaction trước chưa commit.

## 11. AUTO_INCREMENT có thể có khoảng trống

AUTO_INCREMENT tạo định danh tăng dần, không tạo dãy số liên tục không có khoảng trống.

Các nguyên nhân phổ biến:
- Transaction INSERT được ROLLBACK sau khi ID đã được cấp.
- Statement gặp lỗi sau khi một số ID đã được cấp.
- INSERT IGNORE bỏ qua hàng duplicate.
- INSERT ... ON DUPLICATE KEY UPDATE đi vào nhánh UPDATE nhưng đã tiêu thụ giá trị AUTO_INCREMENT.
- REPLACE hoặc mixed-mode insert cấp giá trị rồi thay đổi luồng xử lý.
- Hàng đã được INSERT sau đó bị DELETE.
- Bulk insert dự trù giá trị nhiều hơn số hàng cuối cùng được thêm.
- Server restart hoặc phục hồi theo quy tắc bộ đếm của phiên bản cũ.

Ví dụ:

~~~sql
START TRANSACTION;

INSERT INTO event_log_demo(event_type)
VALUES ('WILL_ROLLBACK');

ROLLBACK;

INSERT INTO event_log_demo(event_type)
VALUES ('AFTER_ROLLBACK');

SELECT *
FROM event_log_demo
ORDER BY event_id;
~~~

ID đã cấp cho hàng bị rollback thường không được tái sử dụng ngay. Khoảng trống là bình thường.

Không dùng COUNT(*) để suy ra ID tiếp theo; không giả định MAX(id)+1 luôn là cách an toàn để tự cấp ID. Hãy để InnoDB quản lý AUTO_INCREMENT.

### 11.1. AUTO_INCREMENT không phải số hóa đơn liên tục

Nếu nghiệp vụ yêu cầu số hóa đơn liên tục, có quy tắc pháp lý hoặc kiểm toán riêng, AUTO_INCREMENT không phải công cụ bảo đảm dãy không có khoảng trống.

Một số định danh kỹ thuật:
- Dùng để nhận diện hàng.
- Có thể có khoảng trống.
- Không bảo đảm phản ánh thứ tự commit.
- Không nên mang ý nghĩa nghiệp vụ bên ngoài.

Nếu cần cấp số nghiệp vụ tuần tự, phải thiết kế bộ cấp số riêng với transaction/locking và quy tắc xử lý hủy số. Việc ép AUTO_INCREMENT không có khoảng trống thường làm giảm concurrency và vẫn không giải quyết mọi trường hợp rollback hoặc xóa dữ liệu.

## 12. Thứ tự ID không phải thứ tự commit

Giả sử:
- Transaction A được cấp ID 100 nhưng xử lý lâu.
- Transaction B được cấp ID 101 và commit trước.
- Transaction A commit sau.

Khi đọc bảng, ID 101 có thể đã xuất hiện trước ID 100. Giá trị ID phản ánh thời điểm cấp số tương đối, không phải thứ tự commit hoặc thời điểm sự kiện chắc chắn.

Nếu cần thứ tự nghiệp vụ:
- Lưu created_at/occurred_at riêng.
- Dùng sequence hoặc event timestamp theo yêu cầu.
- Khi sắp xếp có thể thêm khóa duy nhất làm tie-breaker.
- Không dùng MAX(id) như watermark commit trong môi trường ghi đồng thời.

Trong hệ thống phân tán, thứ tự commit còn phức tạp hơn vì có replication, retry và nhiều nguồn ghi.

## 13. Ảnh hưởng tới replication và binary log

AUTO-INC lock mode liên quan tới khả năng tái tạo kết quả trên replica khi binary log dùng statement format.

### 13.1. Statement-based replication

Statement-based replication ghi câu SQL vào binary log. Replica thực thi lại statement đó. Nếu hai statement đồng thời nhận ID xen kẽ khác nhau trên source và replica, kết quả có thể khác.

Với mode 2, việc cấp ID có thể xen kẽ theo lịch chạy. Statement-based replication không thể bảo đảm tái tạo chính xác thứ tự cấp số đó.

Nếu dùng statement-based replication, chọn mode 0 hoặc mode 1 để giữ hành vi cấp ID xác định theo statement theo yêu cầu của InnoDB.

### 13.2. Row-based replication

Row-based replication ghi các thay đổi hàng thực tế vào binary log. Replica áp dụng giá trị hàng đã được ghi, không cần tự tái diễn giải cùng một lịch cấp AUTO_INCREMENT.

Vì vậy, mode 2 phù hợp với row-based replication. MySQL 8.0 mặc định dùng binlog_format=ROW và innodb_autoinc_lock_mode=2.

Kiểm tra cấu hình:

~~~sql
SELECT
    @@GLOBAL.binlog_format AS binlog_format,
    @@GLOBAL.innodb_autoinc_lock_mode AS autoinc_lock_mode;
~~~

Nếu dùng MIXED, server có thể chọn row format cho một số statement không an toàn với statement logging. Hãy kiểm tra quy tắc của phiên bản và workload cụ thể, không chỉ dựa vào tên MIXED.

### 13.3. Không thay đổi lock mode độc lập với replication

Trước khi chọn mode:
1. Kiểm tra binlog_format.
2. Xác định có statement-based replication hay không.
3. Kiểm tra topology và công cụ replication.
4. Đánh giá workload simple insert/bulk insert.
5. Thử trên môi trường staging.
6. Theo dõi lock wait và throughput sau thay đổi.

Đừng giảm lock mode chỉ vì muốn INSERT nhanh hơn nếu binary log đang dùng statement format.

## 14. AUTO_INCREMENT trong môi trường nhiều nguồn ghi

MySQL có các biến:
- auto_increment_increment: khoảng cách giữa các giá trị được cấp.
- auto_increment_offset: điểm bắt đầu/độ lệch của dãy.

Kiểm tra:

~~~sql
SELECT
    @@GLOBAL.auto_increment_increment,
    @@GLOBAL.auto_increment_offset,
    @@SESSION.auto_increment_increment,
    @@SESSION.auto_increment_offset;
~~~

Ví dụ với hai nguồn ghi cần tránh cấp cùng ID trong mô hình multi-primary cũ:

Node A:
~~~sql
SET SESSION auto_increment_increment = 2;
SET SESSION auto_increment_offset = 1;
~~~

Node B:
~~~sql
SET SESSION auto_increment_increment = 2;
SET SESSION auto_increment_offset = 2;
~~~

Một node có thể cấp dãy lẻ, node kia dãy chẵn. Cấu hình thực tế cần được thiết kế đồng nhất trên toàn topology và có đủ số offset khác nhau.

Hai biến này không thay thế unique key và không tự giải quyết mọi xung đột phân tán. Với kiến trúc hiện đại, có thể cân nhắc UUID/UUIDv7, ULID hoặc khóa phân vùng phù hợp thay vì dựa vào ID số dùng chung giữa nhiều writer.

## 15. Cấp ID tường minh và bộ đếm AUTO_INCREMENT

Có thể cung cấp giá trị tường minh cho cột AUTO_INCREMENT:

~~~sql
INSERT INTO event_log_demo(event_id, event_type)
VALUES (10000, 'IMPORTED');
~~~

Nếu giá trị tường minh lớn hơn bộ đếm hiện tại, bộ đếm có thể được điều chỉnh để các giá trị tự cấp tiếp theo không đụng vào giá trị đã dùng. Nếu giá trị nhỏ hơn và không xung đột, nó có thể được chèn mà không làm giảm bộ đếm.

Để yêu cầu MySQL tự cấp, thường bỏ cột AUTO_INCREMENT khỏi danh sách INSERT hoặc truyền NULL. Giá trị 0 cũng thường được xem như yêu cầu cấp tự động, trừ khi bật SQL mode NO_AUTO_VALUE_ON_ZERO.

Không tự tính giá trị mới bằng MAX(id)+1:

~~~sql
-- Không an toàn khi có nhiều writer:
SELECT MAX(event_id) + 1
FROM event_log_demo;
~~~

Hai session có thể đọc cùng một MAX rồi cùng thử INSERT giá trị kế tiếp. Dùng AUTO_INCREMENT và unique constraint để server điều phối.


### Điều kiện khai báo cột AUTO_INCREMENT

Một bảng chỉ có một cột AUTO_INCREMENT. Cột này phải dùng kiểu số nguyên và phải là cột đầu tiên trong một index; nếu nằm trong index ghép, nó phải đứng ở vị trí đầu tiên. Index không bắt buộc phải là PRIMARY KEY hoặc UNIQUE, nhưng trong thiết kế thông thường nên dùng khóa chính hoặc khóa duy nhất để bảo đảm ý nghĩa định danh của hàng.

~~~sql
CREATE TABLE invoice_records (
    invoice_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    description VARCHAR(200) NOT NULL,
    PRIMARY KEY (invoice_id)
) ENGINE = InnoDB;
~~~

Có thể xác minh định nghĩa và index bằng:

~~~sql
SHOW CREATE TABLE invoice_records;
SHOW INDEX FROM invoice_records;
~~~

Giá trị truyền vào cũng chịu ảnh hưởng của SQL mode:

- Bỏ cột AUTO_INCREMENT khỏi danh sách INSERT hoặc truyền NULL: MySQL cấp giá trị tự động.
- Truyền 0: thông thường cũng yêu cầu cấp số tự động.
- Khi bật NO_AUTO_VALUE_ON_ZERO, giá trị 0 được xem là giá trị tường minh thay vì yêu cầu sinh số.
- Truyền một giá trị dương tường minh: MySQL dùng giá trị đó nếu không vi phạm khóa; nếu nó lớn hơn bộ đếm hiện tại, các giá trị tự cấp sau đó sẽ tiếp tục từ mức phù hợp.

Kiểm tra SQL mode của connection trước khi dựa vào hành vi của giá trị 0:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

### Lấy khóa vừa tạo bằng LAST_INSERT_ID()

Sau một INSERT tạo giá trị AUTO_INCREMENT, LAST_INSERT_ID() trả về giá trị tự động đầu tiên được tạo bởi statement gần nhất trên chính connection hiện tại.

~~~sql
INSERT INTO event_log_demo (event_type)
VALUES ('LOGIN');

SELECT LAST_INSERT_ID();
~~~

Giá trị này có phạm vi theo connection. Một session khác INSERT đồng thời không làm thay đổi kết quả LAST_INSERT_ID() của session hiện tại; vì vậy ứng dụng phải lấy generated key trên cùng connection đã thực hiện INSERT.

Với một INSERT nhiều hàng, LAST_INSERT_ID() chỉ trả về ID đầu tiên được tạo, không trả về danh sách tất cả ID. Đặc biệt ở mode 2, các statement đồng thời có thể xen kẽ giá trị, nên không suy ra toàn bộ ID của một batch bằng cách cộng liên tiếp từ ID đầu tiên. Khi cần lấy tất cả khóa mới, hãy dùng API generated-keys của driver/connector hoặc truy vấn theo một khóa nghiệp vụ duy nhất được chèn cùng batch.

## 16. Cấu hình và kiểm tra innodb_autoinc_lock_mode

### 16.1. Đọc giá trị hiện tại

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_autoinc_lock_mode';
~~~

Hoặc:

~~~sql
SELECT @@GLOBAL.innodb_autoinc_lock_mode;
~~~

Biến này có phạm vi GLOBAL, không phải biến SESSION. Nó được cấu hình khi khởi động server; không dùng SET SESSION để thay đổi riêng một connection.

### 16.2. Cấu hình trong file server

Ví dụ cấu hình:

~~~ini
[mysqld]
innodb_autoinc_lock_mode = 2
~~~

Trên Linux, cấu hình thường nằm trong file cấu hình MySQL như my.cnf hoặc một file được include. Trên Windows, vị trí phụ thuộc cách cài đặt và file my.ini. Sau khi thay đổi, cần khởi động lại MySQL theo quy trình vận hành.

Không chỉnh trực tiếp cấu hình production mà chưa:
- Kiểm tra replication format.
- Đánh giá tác động lên insert workload.
- Có cửa sổ triển khai và phương án quay lại.
- Kiểm tra phiên bản và giá trị mặc định hiện tại.

### 16.3. Kiểm tra binlog format và phiên bản

~~~sql
SELECT
    VERSION() AS mysql_version,
    @@GLOBAL.innodb_autoinc_lock_mode AS autoinc_lock_mode,
    @@GLOBAL.binlog_format AS binlog_format;
~~~

MySQL 8.0/8.4 mặc định mode 2. Các phiên bản trước, đặc biệt MySQL 5.7, có mặc định mode 1. Luôn đọc giá trị runtime thay vì suy luận từ tài liệu của một phiên bản khác.

## 17. Quan sát khóa AUTO-INC khi có chờ

Trong môi trường hỗ trợ Performance Schema, có thể kiểm tra data_locks để tìm lock mode AUTO_INC:

~~~sql
SELECT
    ENGINE_TRANSACTION_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    THREAD_ID
FROM performance_schema.data_locks
WHERE LOCK_MODE LIKE '%AUTO_INC%';
~~~

Tên cột và mức chi tiết phụ thuộc phiên bản MySQL. Nếu không thấy kết quả, điều đó không chứng minh chắc chắn rằng không có chờ; có thể statement kết thúc quá nhanh hoặc instrumentation không hiển thị theo cách mong đợi.

Có thể xem trạng thái InnoDB:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Và các transaction đang hoạt động:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Khi chẩn đoán, phân biệt:
- Chờ AUTO-INC lock.
- Chờ record lock hoặc gap/next-key lock.
- Chờ metadata lock.
- Chờ I/O hoặc tài nguyên khác.

Không phải mọi INSERT chậm đều do innodb_autoinc_lock_mode.

## 18. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| AUTO_INCREMENT luôn tăng liên tục | Có thể có khoảng trống do rollback, delete, duplicate hoặc preallocation |
| ID lớn hơn nghĩa là commit sau | ID phản ánh cấp số, không phải thứ tự commit |
| Mode 2 có thể tạo ID trùng | InnoDB vẫn điều phối bộ đếm; mode 2 cho phép xen kẽ, không bỏ bảo đảm duy nhất |
| Mode 0 khóa toàn bộ bảng cho mọi thao tác | AUTO-INC lock là khóa đặc biệt cho việc cấp số, không phải table lock tổng quát |
| AUTO-INC lock được giữ đến COMMIT | Trong các trường hợp dùng table lock, khóa được giữ đến hết statement |
| Mode 1 không khóa bảng | Bulk insert ở mode 1 vẫn dùng AUTO-INC table lock |
| Mode 2 an toàn với statement-based replication | Interleaving có thể làm kết quả cấp số không tái tạo xác định |
| autoinc_lock_mode là session variable | Đây là cấu hình GLOBAL, xác định ở cấp server |
| Có thể dùng MAX(id)+1 để cấp ID | Không an toàn khi có writer đồng thời |
| AUTO_INCREMENT phù hợp cho số hóa đơn liên tục | Không bảo đảm gapless hoặc thứ tự nghiệp vụ |
| Bật mode 0 sẽ loại bỏ mọi khoảng trống | Mode 0 không ngăn rollback, delete hoặc mọi nguyên nhân mất số |
| INSERT ON DUPLICATE KEY UPDATE không tiêu thụ ID nếu update | Có thể tiêu thụ giá trị AUTO_INCREMENT dù cuối cùng cập nhật hàng hiện có |

## 19. Quy trình chọn chế độ phù hợp

Khi đánh giá innodb_autoinc_lock_mode:

1. Xác định MySQL version và storage engine của bảng.
2. Kiểm tra giá trị innodb_autoinc_lock_mode hiện tại.
3. Kiểm tra binlog_format và topology replication.
4. Phân loại workload: simple INSERT, multi-row INSERT, INSERT ... SELECT, LOAD DATA.
5. Đo tần suất bulk insert và thời gian mỗi statement.
6. Kiểm tra có session chờ AUTO-INC lock hay không.
7. Đánh giá yêu cầu statement-based replication.
8. Nếu dùng row-based replication và cần concurrency cao, mode 2 thường là lựa chọn phù hợp.
9. Nếu dùng statement-based replication, cân nhắc mode 0 hoặc 1 theo workload.
10. Không thay đổi cấu hình khi chưa thử trên staging và lên kế hoạch restart.
11. Theo dõi throughput, lock wait, deadlock và replication lag sau triển khai.
12. Xác nhận ứng dụng không giả định ID liên tục hoặc thứ tự commit.

## 20. Bài tập thực hành

### Bài 1: Quan sát ID sau rollback

Tạo bảng AUTO_INCREMENT, INSERT một hàng trong transaction rồi ROLLBACK. INSERT thêm hàng mới và quan sát ID. Giải thích vì sao ID đã cấp có thể không được tái sử dụng.

### Bài 2: So sánh simple insert và bulk insert

Tạo bảng nguồn và bảng đích. Chạy multi-row INSERT ... VALUES và INSERT ... SELECT. Phân loại từng statement theo simple insert hay bulk insert.

### Bài 3: Hai session ở mode 0

Cấu hình innodb_autoinc_lock_mode=0 trên môi trường lab rồi restart. Cho Session A chạy bulk insert đủ lâu, Session B chạy simple insert vào cùng bảng. Quan sát B phải chờ statement A kết thúc.

### Bài 4: Hai session ở mode 1

Lặp lại thử nghiệm với mode 1. Thử cả hai trường hợp:
- A và B đều simple insert.
- A là bulk insert, B là simple insert.

Ghi nhận khác biệt về khả năng đồng thời.

### Bài 5: Hai session ở mode 2

Cấu hình mode 2 và lặp lại bulk insert cùng simple insert. Quan sát khả năng ID của hai statement xen kẽ. Không kỳ vọng một thứ tự ID cố định qua mọi lần chạy.

### Bài 6: Statement-based và row-based replication

Trên topology thử nghiệm, kiểm tra binlog_format. So sánh yêu cầu của mode 0/1 với mode 2. Không thay đổi cấu hình production để thử nghiệm.

### Bài 7: AUTO_INCREMENT và unique phụ

Tạo bảng có AUTO_INCREMENT PRIMARY KEY và một UNIQUE phụ. Thử INSERT ON DUPLICATE KEY UPDATE với khóa phụ đã tồn tại. Quan sát ID có thể bị tiêu thụ dù nhánh UPDATE được thực hiện.

### Bài 8: Increment và offset

Thiết lập auto_increment_increment=2, offset=1 ở một session; offset=2 ở session khác trên môi trường lab phù hợp. Quan sát dãy ID. Giải thích vì sao cấu hình này không thay thế unique constraint.

### Bài 9: Đọc lock instrumentation

Chạy hai session với bulk insert và simple insert. Kiểm tra performance_schema.data_locks và SHOW ENGINE INNODB STATUS trong lúc có chờ. Phân biệt AUTO-INC lock với record lock.

### Bài 10: Thiết kế khóa nghiệp vụ

Đề xuất schema cho số hóa đơn cần quản lý theo năm và chi nhánh. Giải thích vì sao không nên dựa vào AUTO_INCREMENT để bảo đảm số hóa đơn liên tục; đề xuất transaction/allocator riêng nếu quy định nghiệp vụ bắt buộc.

## 21. Checklist trước khi triển khai

- [ ] Đã xác định cột AUTO_INCREMENT và unique key của bảng.
- [ ] Đã hiểu AUTO-INC lock khác row lock và metadata lock.
- [ ] Đã phân loại simple insert, bulk insert và mixed-mode insert.
- [ ] Đã hiểu mode 0, mode 1 và mode 2.
- [ ] Đã biết mode 1 vẫn dùng table lock cho bulk insert.
- [ ] Đã biết mode 2 cho phép cấp số xen kẽ.
- [ ] Đã kiểm tra MySQL version và giá trị mặc định runtime.
- [ ] Đã kiểm tra binlog_format và yêu cầu replication.
- [ ] Đã hiểu mode 2 không phù hợp với statement-based replication cần tính xác định.
- [ ] Đã hiểu AUTO-INC lock trong các trường hợp table lock được giữ đến hết statement.
- [ ] Đã chấp nhận ID có khoảng trống sau rollback, duplicate hoặc delete.
- [ ] Không dùng MAX(id)+1 để tự cấp ID.
- [ ] Không coi ID là thứ tự commit hoặc số nghiệp vụ liên tục.
- [ ] Đã đánh giá auto_increment_increment và auto_increment_offset nếu có nhiều writer.
- [ ] Đã kiểm tra lock wait bằng Performance Schema/InnoDB Status.
- [ ] Đã thử cấu hình trên staging trước khi restart production.
- [ ] Đã theo dõi throughput, lock wait và replication lag sau thay đổi.

## 22. Kết luận

AUTO-INC lock điều phối việc cấp giá trị AUTO_INCREMENT khi nhiều statement cùng ghi vào một bảng InnoDB. innodb_autoinc_lock_mode quyết định mức tuần tự hóa: mode 0 khóa đến hết mọi insert-like statement cần cấp số; mode 1 giữ table lock cho bulk insert nhưng cho simple insert cấp số bằng cơ chế ngắn hơn; mode 2 cho phép các statement cấp số xen kẽ và tăng concurrency.

MySQL 8.0/8.4 mặc định mode 2, phù hợp với row-based replication. Nếu dùng statement-based replication, cần mode 0 hoặc 1 để giữ hành vi cấp số xác định. Dù chọn chế độ nào, AUTO_INCREMENT vẫn có thể có khoảng trống và không phản ánh thứ tự commit. Hãy dùng ID như khóa kỹ thuật, kiểm tra replication format, đo lock wait và thiết kế bộ cấp số riêng nếu nghiệp vụ thật sự yêu cầu số tuần tự liên tục.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – InnoDB AUTO_INCREMENT Handling](https://dev.mysql.com/doc/refman/8.4/en/innodb-auto-increment-handling.html)
- [MySQL 8.4 Reference Manual – InnoDB AUTO_INCREMENT Lock Modes](https://dev.mysql.com/doc/refman/8.4/en/innodb-auto-increment-handling.html#innodb-auto-increment-lock-modes)
- [MySQL 8.4 Reference Manual – AUTO_INCREMENT Handling in InnoDB](https://dev.mysql.com/doc/refman/8.4/en/innodb-auto-increment-handling.html)
- [MySQL 8.4 Reference Manual – Replication Formats](https://dev.mysql.com/doc/refman/8.4/en/replication-formats.html)
- [MySQL 8.4 Reference Manual – Binary Log Formats](https://dev.mysql.com/doc/refman/8.4/en/binary-log-formats.html)
- [MySQL 8.4 Reference Manual – Performance Schema data_locks](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-data-locks-table.html)
- [MySQL 8.4 Reference Manual – InnoDB Transaction and Locking Information](https://dev.mysql.com/doc/refman/8.4/en/innodb-information-schema-examples.html)
- [MySQL 8.4 Reference Manual – System Variables](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)

