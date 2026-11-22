# InnoDB và các đặc tính phục vụ giao dịch

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành. InnoDB là storage engine được dùng mặc định trong MySQL hiện đại và là lựa chọn phổ biến cho ứng dụng cần transaction an toàn. Engine này kết hợp cấu trúc index, quản lý khóa, MVCC, redo/undo log và cơ chế phục hồi sau sự cố để bảo vệ dữ liệu khi nhiều phiên làm việc đồng thời.

Bài học tập trung vào cách InnoDB lưu trữ dữ liệu, thực hiện transaction, điều phối truy cập đồng thời và duy trì tính bền vững. Nắm được các cơ chế này giúp thiết kế bảng phù hợp, viết transaction ngắn gọn, xử lý deadlock và cấu hình máy chủ theo yêu cầu an toàn dữ liệu.

## 1. Vai trò của InnoDB

MySQL tách SQL layer khỏi storage engine. SQL layer tiếp nhận câu lệnh và xây dựng kế hoạch thực thi; storage engine thực hiện thao tác đọc, ghi, khóa và lưu trữ theo khả năng riêng. InnoDB cung cấp các tính năng quan trọng cho hệ thống giao dịch:

- Transaction tuân theo các thuộc tính ACID.
- Khóa ở mức hàng cùng các loại khóa phạm vi cần thiết để bảo vệ truy vấn.
- Multi-Version Concurrency Control (MVCC) cho consistent read.
- Primary key được tổ chức dưới dạng clustered index và secondary index dựa trên khóa chính.
- Foreign key và kiểm tra ràng buộc tham chiếu.
- Redo log, undo log, doublewrite và crash recovery.
- Buffer pool để cache page dữ liệu và index.

Kiểm tra engine của một bảng:

```sql
SELECT TABLE_SCHEMA, TABLE_NAME, ENGINE
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders';
```

Hoặc xem định nghĩa bảng:

```sql
SHOW CREATE TABLE orders;
```

Không nên giả định mọi bảng trong một schema đều dùng InnoDB. Một số bảng cũ có thể dùng engine khác; khả năng transaction, khóa và foreign key phụ thuộc engine thực tế của từng bảng.

## 2. ACID và transaction

Transaction gom một hoặc nhiều thao tác thành một đơn vị công việc. Với InnoDB, transaction giúp ứng dụng bảo vệ các thay đổi có quan hệ với nhau.

| Thuộc tính | Ý nghĩa | Ví dụ trong hệ thống bán hàng |
|---|---|---|
| Atomicity — Tính nguyên tử | Các thay đổi trong transaction được commit cùng nhau hoặc rollback | Trừ tồn kho và tạo đơn hàng phải cùng thành công |
| Consistency — Tính nhất quán | Transaction hợp lệ phải duy trì các ràng buộc dữ liệu | Số lượng tồn kho không được âm nếu có constraint phù hợp |
| Isolation — Tính cô lập | Các transaction đồng thời không được nhìn thấy trạng thái trung gian trái với mức cô lập đã chọn | Hai giao dịch không được ghi đè tùy tiện lên cùng số dư |
| Durability — Tính bền vững | Sau khi commit thành công, thay đổi được bảo vệ theo cấu hình durability | Đơn hàng đã xác nhận phải tồn tại sau khi máy chủ khởi động lại |

ACID là mục tiêu của transaction, nhưng Consistency còn phụ thuộc logic ứng dụng và constraint được khai báo. Ví dụ, InnoDB không thể tự hiểu quy tắc nghiệp vụ “mỗi khách chỉ được có tối đa ba đơn đang xử lý” nếu quy tắc đó chưa được mô hình hóa bằng constraint hoặc logic transaction phù hợp.

### 2.1. Autocommit

Mặc định, MySQL thường bật `autocommit`. Khi đó mỗi câu lệnh thành công tự tạo và commit transaction riêng nếu không có transaction tường minh đang mở.

```sql
SELECT @@autocommit;
```

Tắt autocommit cho session hiện tại:

```sql
SET autocommit = 0;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 501;

COMMIT;
```

Khi `autocommit = 0`, các câu lệnh tiếp theo có thể nằm trong transaction cho đến khi commit hoặc rollback. Hãy quản lý trạng thái này cẩn thận trong connection pool; khi trả kết nối về pool, ứng dụng cần bảo đảm transaction đã kết thúc và trạng thái session được khôi phục.

### 2.2. Transaction tường minh

Có thể bắt đầu transaction bằng `START TRANSACTION` hoặc `BEGIN`:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 250000
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 250000
WHERE account_id = 202;

COMMIT;
```

Nếu một thao tác không đáp ứng điều kiện nghiệp vụ, ứng dụng có thể hủy toàn bộ:

```sql
ROLLBACK;
```

Chỉ gọi `COMMIT` sau khi mọi bước bắt buộc hoàn tất. Nếu cập nhật số dư mà không kiểm tra số hàng bị ảnh hưởng hoặc không xác minh điều kiện đủ tiền, transaction vẫn có thể commit một kết quả sai về nghiệp vụ dù cú pháp SQL hợp lệ.

### 2.3. Savepoint

Savepoint đánh dấu một vị trí trong transaction để rollback một phần:

```sql
START TRANSACTION;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 9001;

SAVEPOINT after_order_update;

UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 501;

-- Nếu cần hủy riêng phần cập nhật kho:
ROLLBACK TO SAVEPOINT after_order_update;

-- Tiếp tục xử lý hoặc hủy toàn bộ transaction.
COMMIT;
```

`ROLLBACK TO SAVEPOINT` không kết thúc transaction. Savepoint hữu ích khi một phần quy trình có thể được thử lại hoặc hủy riêng, nhưng không thay thế việc thiết kế transaction rõ ràng. Savepoint bị giải phóng khi transaction kết thúc; có thể dùng `RELEASE SAVEPOINT` để bỏ một mốc không còn cần thiết.

### 2.4. DDL và ranh giới transaction

Không phải mọi câu SQL đều tham gia transaction như `INSERT`, `UPDATE` hoặc `DELETE`. Nhiều câu lệnh DDL, chẳng hạn `CREATE TABLE`, `ALTER TABLE` và `DROP TABLE`, gây implicit commit theo quy tắc MySQL. Không nên trộn thay đổi cấu trúc schema với transaction nghiệp vụ rồi kỳ vọng một `ROLLBACK` sẽ hoàn tác toàn bộ DDL. Trước khi chạy DDL trong môi trường dùng chung, cần kiểm tra quy tắc implicit commit và tác động khóa metadata.

## 3. Cấu trúc lưu trữ và index của InnoDB

### 3.1. Page và B-tree

InnoDB tổ chức dữ liệu theo page. Kích thước page mặc định thường là 16 KB, nhưng có thể được xác định khi khởi tạo instance và không phải cấu hình tùy ý thay đổi cho một bảng đang tồn tại. Các page được liên kết trong cấu trúc index B-tree để tìm kiếm theo khóa hiệu quả.

Page là đơn vị dữ liệu mà InnoDB quản lý trong buffer pool và đọc/ghi với storage. Truy vấn có thể cần một hoặc nhiều page tùy access path, kích thước bản ghi, độ phân mảnh và số hàng phải đọc.

### 3.2. Clustered index

Trong InnoDB, dữ liệu của bảng được lưu trong clustered index. Thông thường:

- Nếu bảng có `PRIMARY KEY`, primary key được dùng làm clustered index.
- Nếu không khai báo primary key, InnoDB chọn một `UNIQUE` index có các cột `NOT NULL` làm clustered index nếu có.
- Nếu không có cả hai, InnoDB tạo một clustered index ẩn với row ID nội bộ.

Do các hàng được tổ chức theo clustered key, tìm kiếm theo primary key thường đi trực tiếp đến bản ghi. Khóa chính nên ngắn, ổn định và có tính duy nhất. Thay đổi primary key có thể kéo theo cập nhật các secondary index vì khóa chính được lưu trong mỗi mục index phụ.

Ví dụ:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB;
```

### 3.3. Secondary index

Secondary index là B-tree riêng chứa các cột được lập index cùng giá trị primary key để định vị hàng trong clustered index. Khi truy vấn chỉ cần những cột đã có trong secondary index, InnoDB có thể dùng covering index và tránh đọc lại bản ghi đầy đủ.

Ví dụ:

```sql
CREATE INDEX ix_orders_customer_date
ON orders (customer_id, order_date);
```

Index ghép này có thể hỗ trợ truy vấn lọc theo `customer_id` và sắp xếp hoặc lọc tiếp theo `order_date` trong một số điều kiện. Quy tắc leftmost prefix có nghĩa truy vấn thường tận dụng phần đầu của index; index `(customer_id, order_date)` không tương đương index chỉ trên `order_date`.

Không tạo index cho mọi cột. Mỗi index chiếm dung lượng, tăng chi phí `INSERT`, `UPDATE`, `DELETE` và làm tăng công việc bảo trì. Hãy thiết kế index từ truy vấn thực tế, sau đó kiểm tra bằng `EXPLAIN` và số liệu vận hành.

### 3.4. Tablespace

InnoDB lưu page trong các tablespace. Các loại thường gặp:

| Tablespace | Vai trò |
|---|---|
| System tablespace | Lưu dữ liệu hệ thống InnoDB và có thể chứa dữ liệu người dùng tùy cấu hình |
| File-per-table tablespace | Mỗi bảng có tablespace riêng, thường là file `.ibd` |
| General tablespace | Một tablespace có thể chứa nhiều bảng được chỉ định |
| Undo tablespace | Lưu undo record phục vụ rollback và MVCC |
| Temporary tablespace | Phục vụ dữ liệu tạm thời của InnoDB |

Với cấu hình `innodb_file_per_table` được bật phổ biến, bảng InnoDB mới thường có file tablespace riêng. Xóa bảng có thể giải phóng file tablespace tương ứng, nhưng dung lượng của system tablespace không nhất thiết tự thu nhỏ sau khi dữ liệu bên trong bị xóa. Quản trị tablespace cần theo dõi dung lượng, đường dẫn và kế hoạch lưu trữ.

## 4. Buffer pool và đường đi của dữ liệu

Buffer pool là vùng RAM dùng để cache page dữ liệu và index. Khi cần một page, InnoDB tìm page trong buffer pool; nếu chưa có, engine đọc page từ tablespace. Page đã sửa được đánh dấu dirty và được ghi xuống đĩa bởi các luồng nền theo cơ chế checkpoint và flushing.

Các thành phần liên quan:

- **Free list:** các page chưa được sử dụng và có thể nhận dữ liệu mới.
- **LRU list:** quản lý các page cache theo chính sách gần đây được sử dụng, có điều chỉnh để tránh quét lớn làm đẩy hết page nóng ra khỏi cache.
- **Flush list:** theo dõi dirty page cần được ghi xuống storage.
- **Read-ahead:** có thể đọc trước page khi phát hiện truy cập tuần tự hoặc mẫu truy cập phù hợp.

Buffer pool giúp giảm I/O vật lý khi working set phù hợp với bộ nhớ. Tăng `innodb_buffer_pool_size` không phải giải pháp cho mọi truy vấn chậm: nếu truy vấn quét quá nhiều hàng, index không phù hợp hoặc CPU bị bão hòa, thêm RAM có thể không cải thiện đáng kể.

Xem cấu hình và một số trạng thái buffer pool:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool%';
```

Hãy so sánh các bộ đếm theo khoảng thời gian và lưu lượng thực tế, thay vì chỉ đọc một giá trị tức thời. Cũng cần để lại bộ nhớ cho hệ điều hành, connection, sort, temporary table và các dịch vụ khác trên máy.

## 5. Undo log và MVCC

### 5.1. Undo log

Undo log lưu thông tin cần thiết để hoàn tác thay đổi và tạo các phiên bản dữ liệu cũ cho consistent read. Khi transaction cập nhật một hàng, InnoDB ghi thông tin undo trước hoặc cùng quá trình cập nhật để có thể rollback nếu transaction không commit.

Undo record được tổ chức theo chuỗi phiên bản. Các consistent read sử dụng read view để xác định phiên bản nào có thể nhìn thấy. Khi không còn transaction nào cần phiên bản cũ, purge thread có thể dọn các undo record không còn cần thiết.

Transaction mở quá lâu có thể giữ read view cũ, khiến purge không dọn được một số phiên bản và undo history tăng lên. Vì vậy, không nên mở transaction rồi giữ kết nối nhàn rỗi trong thời gian dài.

### 5.2. MVCC và consistent read

MVCC cho phép các truy vấn đọc thông thường đọc một snapshot logic mà không nhất thiết khóa các hàng đang được transaction khác cập nhật. Trong InnoDB, consistent nonlocking read là hành vi mặc định của các truy vấn `SELECT` thông thường ở những mức cô lập hỗ trợ snapshot.

Ví dụ, transaction A đọc số dư tại một thời điểm; transaction B cập nhật và commit số dư. Transaction A có thể tiếp tục nhìn thấy phiên bản cũ theo read view của mình, tùy isolation level và thời điểm read view được tạo. Điều này giúp đọc và ghi đồng thời mà giảm xung đột.

MVCC không có nghĩa mọi truy vấn đọc đều không khóa. `SELECT ... FOR UPDATE` và `SELECT ... FOR SHARE` là locking read; chúng yêu cầu khóa để phối hợp với các thao tác ghi. Các thao tác `UPDATE` và `DELETE` cũng phải khóa bản ghi được tác động.

## 6. Isolation level

InnoDB hỗ trợ bốn mức cô lập SQL tiêu chuẩn. Mức mặc định của MySQL InnoDB thường là `REPEATABLE READ`.

| Isolation level | Đặc điểm khái quát | Điều cần lưu ý |
|---|---|---|
| `READ UNCOMMITTED` | Có thể đọc dữ liệu chưa commit của transaction khác | Có nguy cơ dirty read |
| `READ COMMITTED` | Mỗi consistent read tạo snapshot mới tại đầu câu lệnh | Cùng transaction có thể thấy dữ liệu commit mới giữa hai lần đọc |
| `REPEATABLE READ` | Các consistent read trong transaction thường dùng cùng read view được tạo ở lần đọc nhất quán đầu tiên | InnoDB dùng next-key locking cho một số locking read và thao tác phạm vi để ngăn phantom trong các trường hợp cần thiết |
| `SERIALIZABLE` | Tăng mức cô lập; trong transaction chưa commit, các SELECT thông thường có thể được chuyển thành locking read tùy autocommit | Mức đồng thời thấp hơn và có thể tăng chờ khóa |

Đặt isolation level cho session:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

Kiểm tra cấu hình:

```sql
SELECT @@transaction_isolation;
```

Chọn isolation level theo yêu cầu nghiệp vụ. Không hạ mức cô lập chỉ để giảm lock wait nếu chưa hiểu hiện tượng dữ liệu mà ứng dụng có thể quan sát. Với `READ COMMITTED`, mỗi consistent read có snapshot mới, nhưng locking read và thao tác ghi vẫn có thể giữ khóa.

## 7. Cơ chế khóa trong InnoDB

### 7.1. Record lock

Record lock khóa một bản ghi index cụ thể. `UPDATE`, `DELETE` hoặc locking read có thể đặt record lock trên những index record cần bảo vệ. Khóa hàng của InnoDB thực chất gắn với index record; điều kiện truy vấn và index được chọn ảnh hưởng phạm vi record cần khóa.

Ví dụ:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

COMMIT;
```

`FOR UPDATE` lấy khóa để transaction có thể kiểm tra rồi cập nhật hàng an toàn. Nếu không có index phù hợp, server có thể phải quét và khóa nhiều bản ghi hơn dự kiến, làm tăng tranh chấp.

### 7.2. Gap lock và next-key lock

Gap lock khóa khoảng trống giữa các bản ghi index, ngăn transaction khác chèn bản ghi vào khoảng đó. Next-key lock kết hợp record lock với gap lock trên khoảng liên quan. Các khóa phạm vi này giúp InnoDB bảo vệ điều kiện truy vấn trong một số thao tác locking read hoặc DML, đặc biệt dưới `REPEATABLE READ`.

Ví dụ, một transaction tìm các đơn hàng trong một khoảng khóa với `FOR UPDATE`; InnoDB có thể khóa các index record và khoảng liên quan để ngăn một transaction khác chèn hàng làm thay đổi tập kết quả đang được bảo vệ.

Phạm vi khóa thực tế phụ thuộc isolation level, loại truy vấn, index được dùng và tính duy nhất của điều kiện. Một phép tìm kiếm bằng unique index với điều kiện khớp duy nhất có thể chỉ cần record lock; truy vấn theo range có thể cần next-key lock. Không suy luận chính xác số hàng bị khóa chỉ từ câu SQL; hãy kiểm tra kế hoạch và trạng thái khóa khi cần.

### 7.3. Intention lock

Intention lock là khóa ở mức bảng cho biết transaction dự định lấy khóa ở mức hàng. Các loại thường gặp là intention shared (`IS`) và intention exclusive (`IX`). Chúng giúp InnoDB phối hợp khóa hàng với các thao tác cần khóa bảng, chẳng hạn `LOCK TABLES`, theo ma trận tương thích.

### 7.4. Insert intention và AUTO-INC lock

Insert intention lock là một dạng gap lock đặc biệt được dùng khi chèn bản ghi vào một vị trí trong index. Nó cho phép các transaction chèn vào những vị trí khác nhau trong cùng một khoảng mà không nhất thiết chặn nhau.

AUTO-INC lock liên quan đến việc cấp giá trị `AUTO_INCREMENT`. Hành vi khóa phụ thuộc chế độ `innodb_autoinc_lock_mode` và loại câu lệnh insert; không nên giả định mọi insert luôn khóa toàn bảng theo cùng một cách.

## 8. Deadlock và lock wait

### 8.1. Deadlock là gì?

Deadlock xảy ra khi các transaction giữ khóa mà transaction khác cần, tạo thành vòng chờ không thể tự tiến triển. Ví dụ:

- Transaction A khóa hàng tài khoản 10 rồi yêu cầu khóa tài khoản 20.
- Transaction B khóa hàng tài khoản 20 rồi yêu cầu khóa tài khoản 10.
- A chờ B và B chờ A, tạo vòng deadlock.

InnoDB phát hiện deadlock và chọn một transaction làm nạn nhân để rollback, cho phép transaction còn lại tiếp tục. Ứng dụng phải bắt lỗi deadlock và có thể retry toàn bộ transaction theo chính sách có giới hạn.

### 8.2. Ví dụ hai transaction tạo deadlock

Session A:

```sql
START TRANSACTION;
UPDATE accounts SET balance = balance - 10 WHERE account_id = 10;
-- Chờ một chút để Session B cập nhật hàng 20.
UPDATE accounts SET balance = balance + 10 WHERE account_id = 20;
```

Session B:

```sql
START TRANSACTION;
UPDATE accounts SET balance = balance - 20 WHERE account_id = 20;
-- Sau đó cập nhật hàng 10.
UPDATE accounts SET balance = balance + 20 WHERE account_id = 10;
```

Nếu mỗi session đã khóa hàng đầu tiên trước khi session kia cập nhật hàng đó, một trong hai thao tác tiếp theo có thể phát hiện deadlock. Đây là thí nghiệm chỉ nên thực hiện trên bảng lab.

### 8.3. Giảm deadlock

- Cập nhật nhiều hàng theo cùng một thứ tự ở mọi luồng nghiệp vụ, ví dụ luôn tăng dần theo primary key.
- Giữ transaction ngắn; không chờ thao tác mạng, nhập liệu hoặc xử lý ngoài database khi đang giữ khóa.
- Tạo index phù hợp để câu lệnh tìm đúng hàng và giảm phạm vi quét/khóa.
- Tránh cập nhật cùng một tập hàng theo thứ tự khác nhau giữa các luồng.
- Thiết kế retry ở tầng ứng dụng với số lần giới hạn, backoff và bảo đảm thao tác có tính idempotent phù hợp.

Deadlock không nhất thiết là lỗi cấu hình. Một hệ thống có ghi đồng thời có thể gặp deadlock; điều quan trọng là transaction được thiết kế để có thể rollback và retry an toàn.

### 8.4. Điều tra lock wait và deadlock

Xem transaction và lock đang chờ bằng các bảng Performance Schema, tùy phiên bản MySQL:

```sql
SELECT *
FROM performance_schema.data_lock_waits;

SELECT *
FROM performance_schema.data_locks;
```

Thông tin tổng quan về deadlock gần nhất có thể xem bằng:

```sql
SHOW ENGINE INNODB STATUS\G
```

Tìm phần `LATEST DETECTED DEADLOCK` để đọc transaction, câu lệnh và khóa liên quan. Nếu cần lưu thông tin deadlock vào error log, có thể xem xét `innodb_print_all_deadlocks`; bật theo nhu cầu điều tra và kiểm soát lượng log.

## 9. Foreign key và tính toàn vẹn tham chiếu

InnoDB hỗ trợ foreign key để ràng buộc quan hệ giữa bảng cha và bảng con. Khi chèn hoặc cập nhật khóa ngoại, giá trị tham chiếu phải khớp một khóa được hỗ trợ ở bảng cha; khi xóa hoặc sửa khóa ở bảng cha, hành vi phụ thuộc `ON DELETE` và `ON UPDATE`.

Ví dụ:

```sql
CREATE TABLE departments (
    department_id INT UNSIGNED NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (department_id)
) ENGINE=InnoDB;

CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    department_id INT UNSIGNED NULL,
    employee_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (employee_id),
    KEY ix_employees_department (department_id),
    CONSTRAINT fk_employees_department
      FOREIGN KEY (department_id)
      REFERENCES departments (department_id)
      ON UPDATE CASCADE
      ON DELETE SET NULL
) ENGINE=InnoDB;
```

Các hành vi phổ biến:

- `RESTRICT` hoặc `NO ACTION`: từ chối thao tác làm vi phạm tham chiếu; trong InnoDB, `NO ACTION` được xử lý như `RESTRICT`.
- `CASCADE`: lan truyền cập nhật hoặc xóa tới hàng con tương ứng.
- `SET NULL`: đặt cột khóa ngoại ở bảng con thành `NULL`; cột đó phải cho phép `NULL`.

Các cột liên quan phải có kiểu dữ liệu tương thích; với kiểu số, cần khớp thuộc tính như signed/unsigned. InnoDB cần index cho cột khóa ngoại ở bảng con và có thể tự tạo index nếu chưa có index phù hợp. Dù foreign key bảo vệ tính toàn vẹn, vẫn cần thiết kế quy tắc xóa/cập nhật cẩn thận để tránh cascade ngoài dự kiến.

## 10. Redo log, doublewrite và crash recovery

### 10.1. Redo log và write-ahead logging

Redo log ghi lại thông tin cần thiết để phục hồi thay đổi của page sau sự cố. Theo nguyên tắc write-ahead logging, log record phải được ghi bền vững theo quy tắc trước khi page dữ liệu tương ứng được xem là có thể ghi xuống vị trí cuối cùng. Nhờ đó, InnoDB không cần flush mọi page đã thay đổi ngay khi transaction commit.

Khi commit, InnoDB ghi redo log theo chính sách flush hiện hành. Dirty page có thể được ghi xuống tablespace sau đó bởi các luồng nền. Checkpoint đánh dấu tiến độ các thay đổi đã được ghi xuống storage, giúp giới hạn lượng redo cần xử lý khi crash recovery.

### 10.2. Doublewrite buffer

Doublewrite bảo vệ khỏi một số tình huống page bị ghi dở (torn page) khi hệ điều hành hoặc máy chủ gặp sự cố trong lúc ghi page. InnoDB ghi page vào vùng doublewrite trước, sau đó mới ghi đến vị trí tablespace cuối cùng. Khi phục hồi, bản page đầy đủ trong doublewrite có thể được dùng để sửa page bị ghi dở.

Doublewrite không phải backup và không bảo vệ khỏi xóa nhầm, lỗi logic ứng dụng hoặc mất toàn bộ thiết bị lưu trữ. Cần có backup độc lập và quy trình restore được kiểm thử.

### 10.3. Redo, undo và binary log

| Cơ chế | Mục đích | Phạm vi |
|---|---|---|
| Undo log | Rollback và cung cấp phiên bản cũ cho MVCC | InnoDB |
| Redo log | Phục hồi thay đổi page sau crash | InnoDB |
| Binary log | Ghi nhận thay đổi để replication và point-in-time recovery | MySQL Server |

Redo log không thay thế binary log. Nếu cần khôi phục đến một thời điểm cụ thể, quy trình thường kết hợp một bản backup phù hợp với binary log được lưu giữ đầy đủ sau thời điểm backup.

### 10.4. Cấu hình durability

Hai biến cấu hình thường cần xem xét:

```sql
SHOW GLOBAL VARIABLES WHERE Variable_name IN
  ('innodb_flush_log_at_trx_commit', 'sync_binlog');
```

`innodb_flush_log_at_trx_commit` điều khiển cách redo log được ghi và flush theo transaction:

| Giá trị | Hành vi khái quát |
|---|---|
| `1` | Ghi redo log và flush xuống storage ở mỗi lần commit; thường là lựa chọn ưu tiên durability cao |
| `2` | Ghi redo log vào file ở mỗi commit, nhưng flush xuống storage theo chu kỳ nền; mất điện hoặc lỗi hệ điều hành có thể làm mất các transaction gần nhất chưa được flush |
| `0` | Ghi và flush redo log theo chu kỳ nền; sự cố có thể làm mất các transaction gần nhất kể cả khi tiến trình MySQL gặp lỗi |

`sync_binlog=1` yêu cầu đồng bộ binary log sau mỗi transaction commit theo quy tắc của MySQL; giá trị lớn hơn hoặc `0` thay đổi tần suất đồng bộ và trade-off durability/hiệu năng. Độ bền vững cuối cùng còn phụ thuộc hệ điều hành, filesystem, controller và thiết bị lưu trữ có thực hiện đúng yêu cầu flush hay không.

Không hạ các giá trị durability trên production chỉ vì muốn tăng throughput. Hãy xác định RPO có thể chấp nhận, kiểm tra thiết bị lưu trữ và thử nghiệm phục hồi trước khi thay đổi.

## 11. Giới hạn và lưu ý vận hành InnoDB

- **Transaction dài:** giữ undo history và khóa lâu, cản trở purge hoặc làm transaction khác phải chờ.
- **Index dư thừa:** làm tăng dung lượng và chi phí ghi; cần rà soát dựa trên truy vấn thật.
- **Primary key quá rộng:** làm các secondary index lớn hơn vì mỗi mục index phụ mang khóa chính.
- **Không có index phù hợp:** có thể khiến câu lệnh quét nhiều hàng và khóa phạm vi rộng hơn.
- **Deadlock:** cần xử lý ở ứng dụng bằng rollback/retry an toàn, đồng thời thống nhất thứ tự cập nhật.
- **Buffer pool quá lớn:** có thể làm hệ điều hành thiếu RAM cho các hoạt động khác.
- **Durability cấu hình thấp:** có thể mất transaction gần nhất khi hệ điều hành hoặc máy chủ gặp sự cố.
- **Backup chưa được kiểm thử:** có backup nhưng không restore được vẫn là rủi ro vận hành.

InnoDB giúp bảo vệ transaction, nhưng không tự sửa logic nghiệp vụ, không ngăn mọi lỗi ứng dụng và không thay thế kế hoạch backup, giám sát cùng khôi phục thảm họa.

## 12. Bài thực hành: kiểm tra transaction và khóa InnoDB

Thực hiện trong database lab với hai session riêng biệt. Tạo bảng thử nghiệm:

```sql
CREATE TABLE lab_accounts (
    account_id INT NOT NULL,
    balance DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (account_id),
    CONSTRAINT chk_lab_balance CHECK (balance >= 0)
) ENGINE=InnoDB;

INSERT INTO lab_accounts (account_id, balance)
VALUES (1, 1000.00), (2, 500.00);
```

Ràng buộc `CHECK` được thực thi từ MySQL 8.0.16. Nếu dùng phiên bản cũ hơn, không dựa vào `CHECK` để bảo vệ số dư; cần kiểm tra phiên bản và áp dụng logic phù hợp.

**Bước 1 — Quan sát autocommit.** Chạy `SELECT @@autocommit;`. Thực hiện một `UPDATE` riêng lẻ và kiểm tra thay đổi từ session thứ hai để thấy hành vi commit mặc định.

**Bước 2 — Thử rollback.** Mở transaction, giảm số dư tài khoản 1, đọc lại trong cùng session rồi `ROLLBACK`. Kiểm tra từ session khác để xác nhận thay đổi đã bị hủy.

**Bước 3 — Thử locking read.** Session A chạy:

```sql
START TRANSACTION;
SELECT balance
FROM lab_accounts
WHERE account_id = 1
FOR UPDATE;
```

Session B thử cập nhật cùng hàng. Quan sát session B phải chờ cho đến khi session A commit hoặc rollback. Kết thúc session A bằng `ROLLBACK` để giữ dữ liệu ban đầu.

**Bước 4 — Quan sát isolation.** Chọn `READ COMMITTED` hoặc `REPEATABLE READ` cho hai session. Thực hiện lần lượt một truy vấn đọc ở session A, cập nhật và commit từ session B, rồi đọc lại ở A. Ghi nhận snapshot thay đổi theo isolation level và thời điểm tạo read view.

**Bước 5 — Xem trạng thái khóa.** Trong khi có session đang chờ, truy vấn `performance_schema.data_lock_waits` và `performance_schema.data_locks` nếu các bảng này khả dụng, hoặc dùng `SHOW ENGINE INNODB STATUS\G` để quan sát thông tin InnoDB.

**Bước 6 — Thử deadlock có kiểm soát.** Dùng hai hàng và hai session cập nhật theo thứ tự ngược nhau như ví dụ ở phần deadlock. Ghi lại lỗi deadlock, xác định transaction bị rollback và thực hiện retry thủ công sau khi đã kết thúc transaction còn lại.

**Bước 7 — Dọn dữ liệu lab.** Sau khi hoàn tất, rollback mọi transaction còn mở và xóa bảng thử nghiệm nếu không còn cần dùng:

```sql
DROP TABLE lab_accounts;
```

**Kết quả cần đạt:** giải thích được ACID, autocommit, commit/rollback, snapshot MVCC, khóa hàng và deadlock; biết tìm thông tin lock wait và phân biệt undo, redo, binary log.

## 13. Checklist khi thiết kế ứng dụng dùng InnoDB

1. Chọn InnoDB cho bảng nghiệp vụ cần transaction, foreign key và phục hồi sau sự cố.
2. Khai báo primary key ngắn, ổn định và xác định rõ quan hệ giữa các bảng.
3. Thiết kế secondary index dựa trên điều kiện lọc, join và sắp xếp của truy vấn thực tế.
4. Giữ transaction ngắn, kết thúc transaction ở mọi nhánh thành công hoặc lỗi.
5. Cập nhật nhiều hàng theo thứ tự nhất quán để giảm deadlock.
6. Chọn isolation level theo yêu cầu dữ liệu, không chỉ theo hiệu năng.
7. Theo dõi buffer pool, transaction dài, lock wait, deadlock và dung lượng tablespace.
8. Đặt chính sách redo/binlog durability theo RPO, rồi kiểm thử backup và restore.

Khi hiểu cách InnoDB tổ chức page, index, transaction, MVCC và log, bạn có thể thiết kế ứng dụng MySQL an toàn hơn trước truy cập đồng thời, xử lý lỗi transaction có chủ đích và đưa ra quyết định vận hành dựa trên yêu cầu dữ liệu thực tế.
