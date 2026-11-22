# Storage engine là gì và vì sao ảnh hưởng đến hành vi SQL

MySQL có thể lưu và quản lý dữ liệu bằng nhiều storage engine. Storage engine là thành phần chịu trách nhiệm thực hiện các thao tác lưu trữ ở cấp bảng như đọc, ghi, quản lý index, khóa và phục hồi dữ liệu. Máy chủ MySQL cung cấp lớp SQL chung để ứng dụng gửi câu lệnh, còn storage engine quyết định nhiều đặc tính quan trọng của cách câu lệnh đó được thực thi.

Vì vậy, hai bảng có cùng cấu trúc và cùng được truy vấn bằng SQL giống nhau vẫn có thể khác nhau về khả năng rollback, khóa ngoại, mức độ đồng thời, cách khóa dữ liệu, phục hồi sau sự cố và hiệu năng. Trong MySQL Community Server 8.4, InnoDB là storage engine mặc định và là lựa chọn phù hợp cho phần lớn ứng dụng quan hệ cần transaction, ràng buộc toàn vẹn và khả năng phục hồi.

Bài học này thuộc module `DATABASE_MYSQL`, bao gồm thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền và vận hành cơ sở dữ liệu quan hệ. Hiểu storage engine giúp bạn dự đoán hành vi của SQL, chọn đúng đặc tính lưu trữ và tránh giả định rằng mọi bảng trong MySQL đều có cùng khả năng.

Sau bài học, bạn có thể:

- Giải thích storage engine làm gì trong kiến trúc MySQL.
- Kiểm tra engine đang có và engine của từng bảng.
- So sánh InnoDB với MyISAM, MEMORY, CSV và NDB ở mức tổng quan.
- Giải thích ảnh hưởng của engine tới transaction, khóa, khóa ngoại, index và phục hồi.
- Chỉ định engine khi tạo bảng và chuyển engine cho bảng hiện có.
- Chọn engine phù hợp dựa trên yêu cầu dữ liệu và tải công việc.

## 1. Storage engine trong kiến trúc MySQL

Khi ứng dụng gửi một câu SQL, máy chủ MySQL tiếp nhận kết nối, phân tích cú pháp, kiểm tra quyền, tối ưu truy vấn và điều phối việc thực thi. Khi cần đọc hoặc ghi dữ liệu của một bảng, máy chủ làm việc với storage engine gắn với bảng đó thông qua lớp giao tiếp lưu trữ.

```text
Ứng dụng / MySQL client
          |
          v
  MySQL Server layer
  - Kết nối và xác thực
  - Parser và SQL execution
  - Optimizer và privilege checks
          |
          v
   Storage engine interface
          |
    +-----+------+-------+
    |            |       |
    v            v       v
  InnoDB       MyISAM  MEMORY ...
    |            |       |
    v            v       v
  Data,        Data,   RAM-backed
  indexes,     indexes, table data
  logs         files
```

Storage engine thường gắn với từng bảng, không phải một lựa chọn duy nhất áp dụng bắt buộc cho toàn bộ máy chủ. Một database có thể chứa nhiều bảng dùng các engine khác nhau. Ví dụ, bảng nghiệp vụ có thể dùng InnoDB trong khi một bảng tạm phục vụ tác vụ đặc biệt dùng MEMORY.

Máy chủ vẫn cung cấp cú pháp SQL chung, nhưng engine có thể hỗ trợ hoặc không hỗ trợ một số tính năng. Engine cũng quyết định cách lưu dữ liệu, tổ chức index, cấp khóa, xử lý transaction và phục hồi khi tiến trình hoặc máy chủ gặp sự cố.

Không nên hiểu rằng storage engine tự thay thế parser hoặc optimizer. Optimizer của MySQL chọn cách thực thi truy vấn dựa trên thông tin như index, thống kê và khả năng mà engine cung cấp; engine thực hiện các thao tác đọc/ghi cụ thể theo mô hình lưu trữ của nó.

## 2. Kiểm tra storage engine trên máy chủ

### 2.1. Liệt kê engine được hỗ trợ

Đăng nhập vào MySQL và chạy:

```sql
SHOW ENGINES;
```

Kết quả có các cột quan trọng:

| Cột | Ý nghĩa |
| --- | --- |
| `Engine` | Tên storage engine |
| `Support` | Trạng thái hỗ trợ trên máy chủ hiện tại |
| `Comment` | Mô tả ngắn |
| `Transactions` | Engine có hỗ trợ transaction hay không |
| `XA` | Engine có hỗ trợ XA transaction hay không |
| `Savepoints` | Engine có hỗ trợ savepoint hay không |

Giá trị `Support` thường gặp gồm `DEFAULT` (engine mặc định), `YES` (được hỗ trợ), `NO` (không có hỗ trợ) và `DISABLED` (có trong bản build nhưng đang bị vô hiệu hóa). Danh sách thực tế phụ thuộc phiên bản, bản build và cấu hình máy chủ. Không giả định mọi engine đều có trên mọi bản cài đặt.

Có thể lọc thông tin bằng `INFORMATION_SCHEMA.ENGINES`:

```sql
SELECT
    ENGINE,
    SUPPORT,
    TRANSACTIONS,
    XA,
    SAVEPOINTS,
    COMMENT
FROM INFORMATION_SCHEMA.ENGINES
ORDER BY ENGINE;
```

### 2.2. Kiểm tra engine mặc định

```sql
SHOW VARIABLES LIKE 'default_storage_engine';
```

Trong MySQL 8.4, giá trị mặc định thường là `InnoDB`. Nếu câu `CREATE TABLE` không chỉ định `ENGINE`, MySQL dùng engine mặc định tại thời điểm tạo bảng.

Thay đổi engine mặc định chỉ ảnh hưởng đến các bảng được tạo sau đó mà không ghi rõ engine. Nó không tự chuyển đổi những bảng đã tồn tại.

### 2.3. Kiểm tra engine của bảng

Trong database hiện tại:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

Hoặc kiểm tra một bảng cụ thể:

```sql
SHOW TABLE STATUS LIKE 'orders'\G
SHOW CREATE TABLE orders\G
```

`SHOW CREATE TABLE` đặc biệt hữu ích vì nó cho biết định nghĩa bảng và tùy chọn `ENGINE` mà MySQL đang lưu.

Lưu ý: `TABLE_ROWS` trong `INFORMATION_SCHEMA.TABLES` và `SHOW TABLE STATUS` có thể chỉ là ước lượng đối với InnoDB. Nếu cần số hàng chính xác, hãy dùng `SELECT COUNT(*)` và cân nhắc chi phí quét dữ liệu trên bảng lớn.

## 3. Những storage engine thường gặp

Các engine dưới đây minh họa sự khác nhau về đặc tính lưu trữ. Trạng thái hỗ trợ cụ thể cần được xác nhận bằng `SHOW ENGINES` trên máy chủ thực tế.

| Engine | Transaction | Khóa và toàn vẹn | Lưu trữ và tình huống thường gặp |
| --- | --- | --- | --- |
| InnoDB | Có, hỗ trợ ACID và rollback | Khóa ở mức bản ghi/index, MVCC, hỗ trợ foreign key | Engine mặc định cho phần lớn bảng nghiệp vụ |
| MyISAM | Không | Khóa ở mức bảng, không thực thi foreign key | Hệ thống cũ hoặc tải đọc đặc thù; không phù hợp với dữ liệu cần transaction |
| MEMORY | Không | Khóa ở mức bảng; hỗ trợ index hash và B-tree | Dữ liệu bảng nằm trong RAM, phù hợp dữ liệu tạm có thể tạo lại |
| CSV | Không | Không có index thông thường, không hỗ trợ foreign key | Trao đổi dữ liệu dạng CSV trong một số trường hợp đơn giản |
| NDB | Có cơ chế transaction của NDB Cluster | Phân tán và sao chép theo kiến trúc NDB Cluster | Hệ thống MySQL NDB Cluster; không phải engine thay thế InnoDB trong cài đặt đơn máy thông thường |

### 3.1. InnoDB

InnoDB là lựa chọn mặc định cho ứng dụng giao dịch. Những đặc tính quan trọng:

- **Transaction và ACID:** hỗ trợ `START TRANSACTION`, `COMMIT`, `ROLLBACK` và savepoint. Thay đổi đã commit được bảo vệ theo cơ chế durability của InnoDB.
- **MVCC:** nhiều transaction có thể đọc các phiên bản dữ liệu nhất quán mà không phải chặn mọi thao tác ghi. Cơ chế này giúp tăng khả năng đồng thời.
- **Khóa ở mức bản ghi/index:** InnoDB có thể khóa các bản ghi hoặc phạm vi index cần thiết. Tùy isolation level và loại truy vấn, engine còn có record lock, gap lock hoặc next-key lock.
- **Foreign key:** hỗ trợ khai báo và thực thi ràng buộc tham chiếu giữa các bảng InnoDB.
- **Phục hồi:** sử dụng redo log, undo log và các cơ chế nội bộ để phục hồi sau khi máy chủ dừng bất thường.
- **Index:** sử dụng clustered index; dữ liệu của bảng được tổ chức theo khóa chính. Secondary index của InnoDB chứa giá trị khóa chính để tìm tới bản ghi.

Ví dụ tạo bảng nghiệp vụ:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uk_customers_email (email)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (customer_id, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
) ENGINE = InnoDB;
```

Trong ví dụ, `orders` tham chiếu `customers` bằng foreign key. Cả hai bảng đều dùng InnoDB, vì vậy MySQL có thể kiểm tra ràng buộc tham chiếu và phối hợp thay đổi trong transaction.

### 3.2. MyISAM

MyISAM là engine cũ vẫn có thể gặp trong hệ thống legacy. Engine này có thể phù hợp với một số tải đọc đặc thù, nhưng có những giới hạn quan trọng:

- Không hỗ trợ transaction. `ROLLBACK` không hoàn tác các thay đổi đã thực hiện trên bảng MyISAM.
- Dùng khóa ở mức bảng khi ghi, nên các thao tác ghi có thể làm các thao tác khác trên cùng bảng phải chờ.
- Không thực thi foreign key.
- Khả năng phục hồi sau sự cố không có các đảm bảo transaction như InnoDB; bảng có thể cần kiểm tra hoặc sửa chữa sau khi dừng bất thường.

Ví dụ tạo bảng MyISAM để quan sát khác biệt trong bài lab:

```sql
CREATE TABLE legacy_counter (
    id BIGINT NOT NULL AUTO_INCREMENT,
    label VARCHAR(80) NOT NULL,
    PRIMARY KEY (id)
) ENGINE = MyISAM;
```

Không chọn MyISAM chỉ vì một phép benchmark đơn lẻ cho thấy nó nhanh hơn trong một tình huống. Cần tính đến transaction, khóa, phục hồi, tính toàn vẹn và tải đồng thời của ứng dụng. Với bảng nghiệp vụ cần tính đúng đắn khi có nhiều thao tác cùng lúc, InnoDB thường là lựa chọn an toàn hơn.

### 3.3. MEMORY

MEMORY lưu các hàng dữ liệu trong RAM. Đặc tính này giúp truy cập nhanh trong một số tác vụ, nhưng dữ liệu bảng bị mất khi máy chủ khởi động lại. Định nghĩa bảng có thể vẫn còn, trong khi nội dung cần được tạo lại hoặc nạp lại.

```sql
CREATE TABLE session_lookup (
    session_key VARCHAR(64) NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    expires_at DATETIME NOT NULL,
    PRIMARY KEY (session_key),
    KEY idx_session_user (user_id)
) ENGINE = MEMORY;
```

MEMORY phù hợp với dữ liệu tạm, có thể tái tạo và có kích thước được kiểm soát. Không dùng nó làm nơi lưu dữ liệu duy nhất cần tồn tại qua lần khởi động lại. Cần theo dõi giới hạn bộ nhớ và cấu trúc index; MEMORY không hỗ trợ transaction như InnoDB.

### 3.4. CSV

CSV lưu dữ liệu theo định dạng văn bản phân tách bằng dấu phẩy. Engine này hữu ích trong một số quy trình trao đổi dữ liệu đơn giản, nhưng không có các tính năng index, transaction và ràng buộc như InnoDB.

```sql
CREATE TABLE import_preview (
    code VARCHAR(30),
    description VARCHAR(255),
    quantity INT
) ENGINE = CSV;
```

CSV không phải lựa chọn cho bảng nghiệp vụ cần truy vấn phức tạp hoặc truy cập đồng thời. Nếu mục tiêu chỉ là nhập/xuất CSV, các công cụ như `LOAD DATA` và `SELECT ... INTO OUTFILE` có thể phù hợp hơn tùy quyền và quy trình vận hành.

### 3.5. NDB Cluster

NDB là storage engine gắn với MySQL NDB Cluster, một kiến trúc cơ sở dữ liệu phân tán theo hướng shared-nothing. NDB được thiết kế cho cụm máy chủ với các node dữ liệu và cơ chế sao chép, phân phối dữ liệu riêng. Nó không giống một engine cục bộ có thể bật lên trong mọi cài đặt MySQL Community Server thông thường.

Nếu hệ thống yêu cầu NDB, cần thiết kế và vận hành cả cụm NDB Cluster, bao gồm topology, node quản lý, node dữ liệu, client node và đặc tính triển khai được hỗ trợ. Không chọn NDB chỉ bằng cách đổi `ENGINE=NDB` trong một máy MySQL đơn lẻ.

## 4. Storage engine ảnh hưởng tới transaction như thế nào?

Transaction gom nhiều thay đổi thành một đơn vị logic. Với InnoDB, bạn có thể commit toàn bộ thay đổi hoặc rollback chúng nếu có lỗi trước khi commit.

```sql
CREATE TABLE account_innodb (
    account_id BIGINT PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO account_innodb (account_id, balance)
VALUES (1, 1000.00), (2, 500.00);

START TRANSACTION;

UPDATE account_innodb
SET balance = balance - 100.00
WHERE account_id = 1;

UPDATE account_innodb
SET balance = balance + 100.00
WHERE account_id = 2;

ROLLBACK;

SELECT * FROM account_innodb ORDER BY account_id;
```

Sau `ROLLBACK`, số dư trở lại giá trị trước transaction. Nếu thay `ROLLBACK` bằng `COMMIT`, cả hai thay đổi sẽ được lưu như một đơn vị transaction của InnoDB.

So sánh với bảng MyISAM:

```sql
CREATE TABLE account_myisam (
    account_id BIGINT PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = MyISAM;

INSERT INTO account_myisam (account_id, balance)
VALUES (1, 1000.00), (2, 500.00);

START TRANSACTION;

UPDATE account_myisam
SET balance = balance - 100.00
WHERE account_id = 1;

ROLLBACK;

SELECT * FROM account_myisam ORDER BY account_id;
```

Thay đổi trên bảng MyISAM không được hoàn tác bởi `ROLLBACK`. Lệnh transaction vẫn có thể được máy chủ nhận, nhưng engine không có khả năng rollback dữ liệu của bảng. Đây là khác biệt ảnh hưởng trực tiếp đến tính đúng đắn của nghiệp vụ.

Lưu ý: các câu lệnh DDL như `CREATE TABLE`, `ALTER TABLE` và `DROP TABLE` có quy tắc implicit commit trong MySQL. Không dùng DDL để minh họa một transaction DML có thể rollback. Ví dụ transaction nên tập trung vào `INSERT`, `UPDATE` và `DELETE` trên các bảng transactional.

Nếu một transaction cập nhật nhiều bảng dùng engine khác nhau, không được giả định toàn bộ thay đổi có thể rollback nguyên tử. Thay đổi trên bảng không hỗ trợ transaction có thể vẫn tồn tại ngay cả khi transaction của InnoDB bị rollback. Với dữ liệu cần tính toàn vẹn xuyên nhiều bảng, hãy ưu tiên dùng cùng engine transactional như InnoDB.

## 5. Ảnh hưởng tới khóa và kiểm soát đồng thời

Storage engine quyết định cách bảo vệ dữ liệu khi nhiều session cùng đọc hoặc ghi.

### 5.1. InnoDB: khóa bản ghi và MVCC

InnoDB hỗ trợ nhiều transaction đồng thời. Các thao tác cập nhật thường khóa bản ghi/index liên quan thay vì khóa toàn bộ bảng. Truy vấn đọc thông thường có thể dùng consistent read dựa trên MVCC để quan sát snapshot phù hợp với isolation level.

Ví dụ dùng locking read:

```sql
START TRANSACTION;

SELECT balance
FROM account_innodb
WHERE account_id = 1
FOR UPDATE;

UPDATE account_innodb
SET balance = balance - 25.00
WHERE account_id = 1;

COMMIT;
```

`SELECT ... FOR UPDATE` lấy khóa cần thiết để transaction có thể cập nhật bản ghi một cách an toàn trước khi commit. Nếu session khác muốn cập nhật cùng bản ghi, nó có thể phải chờ khóa được giải phóng. Khóa thực tế phụ thuộc index, điều kiện truy vấn và isolation level; truy vấn theo range có thể liên quan đến gap lock hoặc next-key lock.

Để quan sát, mở hai kết nối MySQL:

| Session A | Session B |
| --- | --- |
| `START TRANSACTION;` | |
| `SELECT balance FROM account_innodb WHERE account_id = 1 FOR UPDATE;` | |
| | `UPDATE account_innodb SET balance = balance - 10 WHERE account_id = 1;` |
| `COMMIT;` | Session B có thể tiếp tục sau khi khóa được giải phóng |

### 5.2. MyISAM: khóa bảng

MyISAM sử dụng table-level locking. Khi có thao tác ghi, các thao tác khác trên bảng có thể phải đợi tùy loại khóa và trạng thái hàng đợi. Điều này có thể làm giảm khả năng ghi đồng thời khi nhiều client cùng cập nhật một bảng.

Khóa bảng có thể đơn giản và có chi phí quản lý thấp trong một số workload, nhưng nó không cung cấp mô hình transaction và row-level locking như InnoDB. Hãy xem xét số lượng writer, thời gian truy vấn và mức độ tranh chấp trước khi chọn engine.

## 6. Ảnh hưởng tới khóa ngoại và tính toàn vẹn dữ liệu

InnoDB hỗ trợ foreign key và kiểm tra ràng buộc tham chiếu khi insert, update hoặc delete. Ví dụ, bảng `orders` ở phần 3 không thể thêm một đơn hàng tham chiếu tới `customer_id` không tồn tại nếu ràng buộc đang được bật.

MyISAM không thực thi foreign key. Việc viết một định nghĩa có mệnh đề `FOREIGN KEY` trên engine không hỗ trợ không tạo ra cùng bảo đảm toàn vẹn như InnoDB; không dựa vào cú pháp xuất hiện trong DDL để kết luận ràng buộc đang được thực thi.

Kiểm tra định nghĩa và constraint:

```sql
SHOW CREATE TABLE orders\G

SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    REFERENCED_TABLE_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE()
  AND REFERENCED_TABLE_NAME IS NOT NULL;
```

Nếu ứng dụng cần bảo đảm quan hệ cha-con ở cấp database, hãy dùng InnoDB cho các bảng liên quan và khai báo foreign key rõ ràng. Kiểm tra cả kiểu dữ liệu, kích thước, signedness và index của các cột tham chiếu để thiết kế tương thích.

## 7. Ảnh hưởng tới index và kế hoạch thực thi

Storage engine quyết định cách index được tổ chức và truy cập. InnoDB dùng clustered index: dữ liệu hàng được lưu theo khóa chính. Nếu bảng không khai báo primary key phù hợp, InnoDB chọn một unique index thích hợp hoặc tạo row identifier nội bộ. Secondary index của InnoDB chứa khóa chính, do đó khóa chính dài có thể làm các secondary index lớn hơn.

Vì vậy, thiết kế primary key có tác động đến dung lượng và hiệu quả truy vấn. Khóa chính ổn định, ngắn gọn và phù hợp với cách truy cập thường có lợi cho bảng InnoDB. Đây không có nghĩa mọi bảng đều phải dùng một kiểu ID giống nhau; hãy chọn dựa trên yêu cầu định danh và workload.

Optimizer có thể chọn kế hoạch khác nhau giữa các engine do cách engine cung cấp index, thống kê và khả năng truy cập dữ liệu. Khi hiệu năng khác nhau, hãy kiểm tra cả:

- Engine thực tế của bảng.
- Index và thứ tự cột trong composite index.
- Thống kê bảng và phân bố dữ liệu.
- Điều kiện lọc, join, sort và số hàng ước lượng.
- Mức độ tranh chấp khóa và hoạt động I/O.

Ví dụ kiểm tra kế hoạch:

```sql
EXPLAIN
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 10
ORDER BY created_at DESC;
```

Không kết luận rằng một engine luôn nhanh hơn engine khác chỉ từ tên engine. Hãy đo trên dữ liệu và workload gần thực tế, xem `EXPLAIN`, theo dõi thời gian, số hàng đọc và mức độ đồng thời. Engine có transaction và constraint phù hợp có thể giảm chi phí sửa lỗi dữ liệu, dù một microbenchmark đơn giản không thể hiện lợi ích đó.

## 8. Ảnh hưởng tới phục hồi và độ bền dữ liệu

InnoDB sử dụng các cơ chế như redo log, undo log và crash recovery để đưa dữ liệu về trạng thái nhất quán sau sự cố. Khi máy chủ khởi động lại bất thường, InnoDB có thể phát lại những thay đổi đã ghi log cần thiết và rollback các transaction chưa hoàn tất.

MyISAM không cung cấp transaction và crash recovery cùng mức như InnoDB. Sau khi dừng bất thường, bảng có thể bị đánh dấu cần kiểm tra hoặc sửa chữa. Điều đó làm tăng rủi ro và công sức vận hành nếu dữ liệu quan trọng được lưu bằng MyISAM.

Độ bền thực tế còn phụ thuộc cấu hình log, hệ thống tệp, thiết bị lưu trữ và cách hệ điều hành xác nhận ghi dữ liệu. Không nên hiểu rằng chỉ cần chọn InnoDB là có thể bỏ qua backup. Mọi môi trường cần giữ dữ liệu vẫn phải có bản sao lưu được kiểm tra khôi phục và kế hoạch phục hồi phù hợp.

## 9. Chọn engine khi tạo hoặc chuyển bảng

### 9.1. Chỉ định engine khi tạo bảng

Nên ghi rõ engine trong DDL quan trọng để người đọc và môi trường triển khai hiểu rõ yêu cầu:

```sql
CREATE TABLE payment_transactions (
    transaction_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    reference_code VARCHAR(64) NOT NULL,
    amount DECIMAL(14, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (transaction_id),
    UNIQUE KEY uk_payment_reference (reference_code)
) ENGINE = InnoDB;
```

Để kiểm tra engine mặc định trước khi tạo bảng:

```sql
SHOW VARIABLES LIKE 'default_storage_engine';
```

Trong cấu hình máy chủ, có thể chỉ định engine mặc định trong section `[mysqld]` của option file:

```ini
[mysqld]
default_storage_engine=InnoDB
```

Đường dẫn option file phụ thuộc hệ điều hành và cách cài đặt. Sau khi thay đổi cấu hình tĩnh, hãy thực hiện quy trình restart phù hợp và xác minh lại biến. Dù InnoDB đã là mặc định trên MySQL 8.4, khai báo tường minh trong DDL giúp tránh phụ thuộc vào cấu hình khác biệt giữa các môi trường.

### 9.2. Chuyển engine của bảng hiện có

Có thể chuyển một bảng bằng `ALTER TABLE`:

```sql
ALTER TABLE legacy_counter ENGINE = InnoDB;
```

Thao tác này có thể dựng lại bảng, tạo lại index và cần thêm dung lượng tạm. Với bảng lớn, nó có thể tiêu tốn I/O, ảnh hưởng thời gian phản hồi hoặc khóa bảng trong một phần quy trình tùy phiên bản và loại thay đổi. Các ràng buộc hoặc tùy chọn không được engine đích hỗ trợ có thể làm thao tác thất bại hoặc thay đổi hành vi.

Trước khi chuyển engine:

1. Kiểm tra engine hiện tại, kích thước bảng, index, constraint, trigger và ứng dụng phụ thuộc.
2. Sao lưu dữ liệu và xác minh có thể khôi phục.
3. Kiểm tra khả năng tương thích của engine đích với các tính năng đang dùng.
4. Thử chuyển trên bản sao hoặc môi trường staging.
5. Lập cửa sổ bảo trì nếu cần, theo dõi dung lượng đĩa, thời gian và tải I/O.
6. Sau khi chuyển, xác minh `SHOW CREATE TABLE`, số bản ghi, index, foreign key và truy vấn quan trọng.

Không đổi engine trên production chỉ để thử nghiệm. Hãy xác định yêu cầu về transaction, khóa, toàn vẹn, phục hồi và tải trước khi lập kế hoạch chuyển đổi.

## 10. Chọn storage engine theo yêu cầu

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Đơn hàng, thanh toán, tài khoản, tồn kho | InnoDB | Transaction, foreign key, MVCC và crash recovery |
| Nhiều session đọc/ghi cùng lúc | InnoDB | Kiểm soát khóa ở mức bản ghi/index và MVCC |
| Bảng tạm trong RAM, dữ liệu có thể tạo lại | MEMORY | Truy cập dữ liệu RAM; cần chấp nhận mất dữ liệu khi restart |
| Trao đổi dữ liệu dạng CSV đơn giản | CSV hoặc công cụ import/export | Định dạng tệp dễ trao đổi, nhưng thiếu index và transaction |
| Hệ thống legacy chỉ đọc có yêu cầu đặc thù | Đánh giá MyISAM theo workload | Có thể giữ tương thích, nhưng cần chấp nhận giới hạn transaction và khóa |
| Cụm MySQL phân tán theo NDB Cluster | NDB | Kiến trúc cụm và cơ chế phân phối dữ liệu riêng |

Với ứng dụng quan hệ mới, hãy bắt đầu từ InnoDB trừ khi có yêu cầu kỹ thuật cụ thể chứng minh engine khác phù hợp hơn. Tối ưu hiệu năng thường bắt đầu từ schema, index, câu truy vấn, thống kê và tài nguyên máy chủ trước khi cân nhắc đổi engine.

## 11. Bài tập thực hành

1. Chạy `SHOW ENGINES` và ghi lại engine nào có trạng thái `DEFAULT`, `YES`, `NO` hoặc `DISABLED` trên máy của bạn.
2. Tạo hai bảng có cấu trúc tương tự, một bảng InnoDB và một bảng MyISAM. Kiểm tra kết quả bằng `SHOW CREATE TABLE`.
3. Chạy ví dụ transaction với InnoDB, sau đó chạy ví dụ tương tự với MyISAM. Giải thích vì sao `ROLLBACK` cho kết quả khác nhau.
4. Tạo hai bảng InnoDB có quan hệ cha-con bằng foreign key. Thử insert một giá trị khóa ngoại không tồn tại và ghi lại lỗi.
5. Tạo bảng MEMORY, chèn dữ liệu, kiểm tra dữ liệu rồi khởi động lại môi trường lab nếu có thể. Xác nhận định nghĩa và dữ liệu có vòng đời khác nhau.
6. Chạy `EXPLAIN` cho truy vấn trên bảng InnoDB. Thêm hoặc điều chỉnh index phù hợp rồi so sánh kế hoạch.
7. Chuyển một bảng thử nghiệm từ MyISAM sang InnoDB. Xác minh số hàng, index và engine sau khi chuyển.
8. Viết một đoạn giải thích lựa chọn engine cho bảng đơn hàng của ứng dụng bán hàng, nêu rõ yêu cầu transaction, foreign key, đồng thời và phục hồi.

## 12. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể giải thích vai trò của storage engine trong kiến trúc MySQL, xác định engine của một bảng, mô tả khác biệt chính giữa InnoDB và các engine phổ biến, chứng minh tác động của engine tới rollback và khóa ngoại, và lựa chọn được engine dựa trên yêu cầu nghiệp vụ. Bạn cũng cần biết cách chuyển engine có kiểm soát và xác minh kết quả sau chuyển đổi.
