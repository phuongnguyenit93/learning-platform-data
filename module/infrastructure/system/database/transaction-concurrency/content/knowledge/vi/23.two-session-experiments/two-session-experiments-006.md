# Quan sát đọc ảnh chụp trong lúc phiên khác đang cập nhật

Khi hai phiên database cùng truy cập một hàng, phiên đang đọc có nhất thiết phải chờ phiên đang ghi không? Câu trả lời phụ thuộc vào cơ chế concurrency control, isolation level và loại câu lệnh đọc.

Với **MVCC (Multi-Version Concurrency Control)**, database giữ nhiều phiên bản của dữ liệu để một truy vấn có thể đọc phiên bản phù hợp với snapshot mà không cần chờ writer hoàn tất trong nhiều trường hợp. Một transaction khác vẫn có thể cập nhật và commit phiên bản mới trong lúc reader đang đọc phiên bản cũ.

Bài thực nghiệm này dùng hai phiên kết nối MySQL InnoDB để quan sát:

- Một consistent read tiếp tục thấy phiên bản cũ trong khi phiên khác đã cập nhật và commit.
- READ COMMITTED và REPEATABLE READ tạo snapshot với thời điểm khác nhau.
- Locking read đọc dữ liệu hiện hành và có thể cho kết quả khác với snapshot read trong cùng transaction.
- Một locking read có thể chặn writer, trong khi SELECT thông thường theo MVCC thường không chặn writer.
- Snapshot read không tự bảo vệ một quyết định ghi dựa trên dữ liệu cũ.

Mục tiêu là quan sát trực tiếp hành vi giữa hai phiên, sau đó liên hệ với cách PostgreSQL và SQL Server triển khai đọc phiên bản.

## 1. Snapshot read là gì?

Snapshot read là cách đọc dữ liệu theo một **read view (ảnh chụp logic)**. Read view xác định những thay đổi nào đã commit và được phép nhìn thấy tại một thời điểm nhất định.

Giả sử một hàng có số lượng là 100:

~~~text
Thời gian ----------------------------------------------------->

Database:
    Phiên bản V1: quantity = 100
    Phiên bản V2: quantity = 80

Session A                         Session B
---------                         ---------
Bắt đầu transaction
Đọc snapshot V1 = 100

                                  UPDATE quantity = 80
                                  COMMIT

Đọc lại theo snapshot
Vẫn thấy V1 = 100
~~~

Session B đã commit giá trị 80. Tuy nhiên, nếu Session A đang dùng snapshot cũ, một consistent read tiếp theo vẫn có thể trả về 100.

Điều này không có nghĩa database bỏ qua commit của B. Database đang thực hiện đúng quy tắc visibility của snapshot mà A sử dụng. Phiên bản 80 tồn tại và có thể được nhìn thấy bởi những snapshot mới hơn hoặc bởi một loại đọc khác.

Trong InnoDB, các phiên bản cũ được hỗ trợ bởi thông tin undo. Khi một transaction cần đọc snapshot cũ, InnoDB có thể dựng lại phiên bản phù hợp từ các thay đổi trước đó. Phiên bản cũ chỉ có thể được dọn dẹp khi không còn read view nào cần đến nó.

Snapshot read thường giúp reader không phải chờ writer chỉ vì writer đang giữ lock ghi trên cùng hàng. Đổi lại, reader có thể nhìn thấy dữ liệu cũ hơn trạng thái mới nhất đã commit.

## 2. Chuẩn bị dữ liệu thực nghiệm

Mở hai cửa sổ SQL độc lập, kết nối đến cùng một MySQL server và cùng database. Gọi chúng là:

- **Session A:** phiên quan sát snapshot.
- **Session B:** phiên cập nhật dữ liệu.

Chạy phần chuẩn bị một lần trước khi bắt đầu thử nghiệm:

~~~sql
DROP TABLE IF EXISTS snapshot_lab;

CREATE TABLE snapshot_lab (
    id INT NOT NULL PRIMARY KEY,
    quantity INT NOT NULL,
    version_no INT NOT NULL DEFAULT 0
) ENGINE = InnoDB;

INSERT INTO snapshot_lab (id, quantity, version_no)
VALUES (1, 100, 0);
~~~

Kiểm tra dữ liệu ban đầu:

~~~sql
SELECT *
FROM snapshot_lab
WHERE id = 1;
~~~

Kết quả:

| id | quantity | version_no |
|---:|---:|---:|
| 1 | 100 | 0 |

Đảm bảo cả hai session đang kết nối đúng database. Các ví dụ bên dưới giả định bảng chỉ có hàng id = 1 và chưa có transaction khác thay đổi hàng này.

## 3. Thực nghiệm 1: REPEATABLE READ giữ snapshot trong transaction

InnoDB thường dùng REPEATABLE READ làm isolation level mặc định. Ở mức này, các consistent read trong cùng transaction thường sử dụng cùng một read view.

### Bước 1: Session A bắt đầu transaction và tạo snapshot

Chạy trong Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;

START TRANSACTION;

SELECT quantity, version_no
FROM snapshot_lab
WHERE id = 1;
~~~

Kết quả:

| quantity | version_no |
|---:|---:|
| 100 | 0 |

Đây là consistent read đầu tiên của transaction. Trong InnoDB REPEATABLE READ, read view cho consistent read thường được tạo tại lần đọc này. Những consistent read tiếp theo trong transaction sẽ tiếp tục dùng snapshot đó.

Lưu ý: START TRANSACTION không nhất thiết đã tạo read view cho consistent read. Nếu cần tạo snapshot ngay khi bắt đầu transaction, InnoDB hỗ trợ START TRANSACTION WITH CONSISTENT SNAPSHOT ở REPEATABLE READ.

### Bước 2: Session B cập nhật và commit

Trong khi Session A vẫn mở transaction, chạy ở Session B:

~~~sql
START TRANSACTION;

UPDATE snapshot_lab
SET quantity = 80,
    version_no = version_no + 1
WHERE id = 1;

COMMIT;
~~~

Session B đã cập nhật và commit thành công. Kiểm tra ở Session B:

~~~sql
SELECT quantity, version_no
FROM snapshot_lab
WHERE id = 1;
~~~

Kết quả:

| quantity | version_no |
|---:|---:|
| 80 | 1 |

Giá trị mới đã được commit. Session B không cần chờ Session A kết thúc chỉ vì A đang thực hiện một SELECT consistent read thông thường.

### Bước 3: Session A đọc lại

Quay lại Session A, chạy cùng câu SELECT:

~~~sql
SELECT quantity, version_no
FROM snapshot_lab
WHERE id = 1;
~~~

Kết quả vẫn là:

| quantity | version_no |
|---:|---:|
| 100 | 0 |

Đây là quan sát quan trọng nhất của bài thực nghiệm: **Session A tiếp tục thấy phiên bản thuộc snapshot cũ, dù Session B đã commit phiên bản mới.**

Session A không đọc dirty data. Nó đọc phiên bản 100 đã commit và nhìn thấy được tại thời điểm tạo read view.

### Bước 4: Kết thúc transaction A

~~~sql
COMMIT;
~~~

Sau khi A kết thúc, một transaction mới sẽ tạo consistent read view mới và có thể nhìn thấy quantity = 80.

~~~sql
START TRANSACTION;

SELECT quantity, version_no
FROM snapshot_lab
WHERE id = 1;

COMMIT;
~~~

Kết quả:

| quantity | version_no |
|---:|---:|
| 80 | 1 |

Sự khác nhau giữa hai kết quả đến từ thời điểm snapshot được tạo.

## 4. Quan sát đồng thời: reader không khóa writer trong consistent read

Có thể lặp lại thử nghiệm trên và quan sát thời gian chờ.

Trong Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;

START TRANSACTION;

SELECT quantity
FROM snapshot_lab
WHERE id = 1;
~~~

Trong khi A vẫn mở transaction, Session B chạy:

~~~sql
UPDATE snapshot_lab
SET quantity = quantity + 1
WHERE id = 1;
~~~

Với một SELECT consistent read thông thường của InnoDB, UPDATE của B thường có thể hoàn tất mà không phải chờ A nhả shared row lock, bởi A không giữ shared record lock chỉ để đọc hàng.

Nếu B chạy trong autocommit mode, câu UPDATE được commit khi statement hoàn tất. Nếu B đang ở transaction tường minh, hãy COMMIT để hoàn tất.

Quay lại A:

~~~sql
SELECT quantity
FROM snapshot_lab
WHERE id = 1;
~~~

A vẫn thấy giá trị thuộc snapshot cũ. Sau khi A COMMIT và mở transaction mới, nó mới đọc được giá trị vừa cập nhật.

Đây là lợi ích chính của MVCC: reader và writer có thể tiến triển đồng thời trong nhiều tình huống. Tuy nhiên, nó không có nghĩa mọi thao tác đọc đều không khóa hoặc không thể bị chặn. Metadata lock, locking read, DDL, I/O và những tài nguyên khác vẫn có thể tạo ra chờ đợi.

## 5. Thực nghiệm 2: READ COMMITTED tạo snapshot mới cho mỗi statement

Ở READ COMMITTED, mỗi consistent read thường nhìn thấy dữ liệu đã commit trước khi statement đó bắt đầu. Vì thế, hai SELECT trong cùng transaction có thể trả về hai giá trị khác nhau nếu có transaction khác commit ở giữa.

Trước tiên, đặt lại dữ liệu từ một session không có transaction đang mở:

~~~sql
UPDATE snapshot_lab
SET quantity = 100,
    version_no = 0
WHERE id = 1;
~~~

### Bước 1: Session A đọc lần đầu

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;

SELECT quantity, version_no
FROM snapshot_lab
WHERE id = 1;
~~~

Kết quả:

| quantity | version_no |
|---:|---:|
| 100 | 0 |

### Bước 2: Session B cập nhật và commit

~~~sql
START TRANSACTION;

UPDATE snapshot_lab
SET quantity = 80,
    version_no = version_no + 1
WHERE id = 1;

COMMIT;
~~~

### Bước 3: Session A đọc lần thứ hai

~~~sql
SELECT quantity, version_no
FROM snapshot_lab
WHERE id = 1;
~~~

Kết quả:

| quantity | version_no |
|---:|---:|
| 80 | 1 |

Ở READ COMMITTED, statement thứ hai lấy read view mới nên nhìn thấy commit của Session B. Điều này khác với REPEATABLE READ, nơi consistent read trong cùng transaction thường tiếp tục dùng snapshot ban đầu.

### So sánh hai isolation level trong thử nghiệm

| Thời điểm | Session A ở REPEATABLE READ | Session A ở READ COMMITTED |
|---|---:|---:|
| SELECT đầu tiên | 100 | 100 |
| Session B cập nhật và commit | 80 trong database | 80 trong database |
| SELECT thứ hai của A | 100 | 80 |
| Transaction A kết thúc, transaction mới đọc | 80 | 80 |

Bảng này mô tả consistent read của InnoDB. Locking read như FOR UPDATE có quy tắc khác và không nên suy ra hành vi của nó từ bảng trên.

## 6. Snapshot được tạo lúc nào trong InnoDB?

Thời điểm tạo read view ảnh hưởng trực tiếp đến dữ liệu mà transaction nhìn thấy.

Ở REPEATABLE READ, read view cho consistent read thường được tạo tại consistent read đầu tiên. Các câu lệnh START TRANSACTION và SET TRANSACTION ISOLATION LEVEL thiết lập transaction, nhưng bản thân chúng không nhất thiết tạo read view.

Có thể quan sát bằng một biến thể của thử nghiệm:

1. Session A bắt đầu REPEATABLE READ transaction nhưng chưa chạy SELECT.
2. Session B cập nhật quantity từ 100 thành 80 và COMMIT.
3. Session A chạy SELECT lần đầu.
4. Session A nhìn thấy 80 vì read view được tạo sau khi B đã commit.

Ví dụ:

~~~sql
-- Session A
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

-- Chưa chạy SELECT consistent read.
~~~

~~~sql
-- Session B
UPDATE snapshot_lab
SET quantity = 80
WHERE id = 1;
~~~

~~~sql
-- Session A
SELECT quantity
FROM snapshot_lab
WHERE id = 1;
~~~

Kết quả là 80 nếu không có transaction khác thay đổi dữ liệu.

Có thể yêu cầu tạo consistent snapshot ngay khi bắt đầu transaction bằng:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;

START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT quantity
FROM snapshot_lab
WHERE id = 1;
~~~

Khi sử dụng WITH CONSISTENT SNAPSHOT, snapshot được thiết lập tại thời điểm bắt đầu transaction theo hỗ trợ của InnoDB. Tùy chọn này có ý nghĩa với REPEATABLE READ; không nên dựa vào nó để thay đổi semantics của isolation level khác.

## 7. Consistent read và locking read có thể thấy hai phiên bản khác nhau

InnoDB phân biệt hai cách đọc:

- **Consistent read:** SELECT thông thường dùng MVCC snapshot.
- **Current read:** locking read hoặc thao tác ghi làm việc với phiên bản hiện hành theo quy tắc của engine và lấy lock cần thiết.

Trong REPEATABLE READ, một transaction có thể thực hiện cả hai cách đọc và quan sát hai phiên bản khác nhau.

### Thực nghiệm

Đặt dữ liệu về trạng thái ban đầu:

~~~sql
UPDATE snapshot_lab
SET quantity = 100,
    version_no = 0
WHERE id = 1;
~~~

Trong Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;

START TRANSACTION;

-- Consistent read: tạo snapshot và đọc 100.
SELECT quantity, version_no
FROM snapshot_lab
WHERE id = 1;
~~~

Trong Session B:

~~~sql
UPDATE snapshot_lab
SET quantity = 80,
    version_no = 1
WHERE id = 1;
~~~

Sau đó Session B COMMIT.

Quay lại Session A:

~~~sql
-- Consistent read tiếp tục dùng snapshot cũ.
SELECT quantity, version_no
FROM snapshot_lab
WHERE id = 1;

-- Locking read đọc phiên bản hiện hành.
SELECT quantity, version_no
FROM snapshot_lab
WHERE id = 1
FOR UPDATE;
~~~

Trong InnoDB REPEATABLE READ, kết quả khái quát:

| Câu đọc ở Session A | quantity | version_no | Cách đọc |
|---|---:|---:|---|
| SELECT thông thường | 100 | 0 | Snapshot cũ |
| SELECT ... FOR UPDATE | 80 | 1 | Current read |

FOR UPDATE lấy lock trên dữ liệu được chọn theo quy tắc InnoDB. Nếu transaction khác đang giữ lock xung đột, câu lệnh có thể phải chờ.

Sau khi FOR UPDATE trả về 80, một SELECT thông thường tiếp theo trong cùng transaction A vẫn có thể thấy 100 vì nó tiếp tục dùng read view đã tạo trước đó. Điều này cho thấy snapshot read và current read là hai cơ chế visibility khác nhau.

Kết thúc transaction A:

~~~sql
COMMIT;
~~~

Không nên trộn hai cách đọc mà không hiểu semantics của engine. Nếu ứng dụng cần một quyết định ghi dựa trên dữ liệu hiện hành, hãy dùng locking read, UPDATE có điều kiện hoặc một chiến lược concurrency phù hợp.

## 8. Thực nghiệm 3: locking read có thể chặn writer

Thử nghiệm trước cho thấy consistent read thông thường không giữ shared row lock khiến writer phải chờ. Bây giờ hãy so sánh với locking read.

Đặt dữ liệu về quantity = 100.

Trong Session A:

~~~sql
START TRANSACTION;

SELECT quantity
FROM snapshot_lab
WHERE id = 1
FOR UPDATE;
~~~

A đã yêu cầu exclusive lock trên hàng được chọn.

Trong Session B:

~~~sql
START TRANSACTION;

UPDATE snapshot_lab
SET quantity = quantity - 10
WHERE id = 1;
~~~

UPDATE của B sẽ phải chờ vì A đang giữ lock xung đột trên hàng đó.

Quay lại Session A:

~~~sql
COMMIT;
~~~

Sau khi A commit và nhả lock, UPDATE của B có thể tiếp tục rồi commit.

Kết quả cuối cùng là quantity = 90 nếu không có thao tác khác xen vào.

### So sánh hai thử nghiệm

| Session A | Session B cập nhật cùng hàng | Hành vi thường thấy trong InnoDB |
|---|---|---|
| SELECT thông thường theo MVCC | UPDATE | B có thể cập nhật và commit mà không chờ shared row lock từ A |
| SELECT ... FOR UPDATE | UPDATE | B phải chờ lock của A |
| UPDATE | UPDATE | Hai writer có thể phải chờ nhau trên cùng record |
| SELECT ... FOR SHARE | UPDATE | Writer có thể phải chờ shared lock của A |

Đây là lý do không nên thêm FOR UPDATE vào mọi SELECT. Locking read có chi phí đồng bộ và có thể làm giảm khả năng chạy đồng thời.

## 9. Snapshot read không có nghĩa transaction có thể ghi an toàn dựa trên dữ liệu cũ

Snapshot read bảo vệ tính nhất quán của dữ liệu được nhìn thấy. Nó không tự động bảo đảm quyết định nghiệp vụ được tính từ snapshot cũ vẫn hợp lệ tại thời điểm ghi.

Giả sử quantity ban đầu là 10. Hai request cùng đọc 10:

- A muốn giảm 2, tính giá trị mới là 8.
- B muốn giảm 3, tính giá trị mới là 7.

Nếu A và B ghi các giá trị tuyệt đối dựa trên kết quả đã tính ở ứng dụng, một cập nhật có thể ghi đè cập nhật còn lại.

~~~text
Session A                         Session B
---------                         ---------
Đọc snapshot: 10                  Đọc snapshot: 10
Tính giá trị mới: 8               Tính giá trị mới: 7
UPDATE quantity = 8
COMMIT
                                  UPDATE quantity = 7
                                  COMMIT
~~~

Kết quả cuối có thể là 7 thay vì 5. Đây là lost update ở cấp logic ứng dụng.

Một cách tốt hơn cho thao tác giảm số lượng là đưa phép tính và điều kiện vào cùng UPDATE:

~~~sql
UPDATE snapshot_lab
SET quantity = quantity - 2,
    version_no = version_no + 1
WHERE id = 1
  AND quantity >= 2;
~~~

Database thực hiện phép trừ trên giá trị hiện hành và kiểm tra điều kiện trong cùng câu lệnh. Ứng dụng kiểm tra số dòng bị ảnh hưởng để xác định thao tác có thành công hay không.

Nếu ứng dụng cần bảo vệ một chỉnh sửa dựa trên đúng phiên bản đã đọc, có thể dùng optimistic locking:

~~~sql
UPDATE snapshot_lab
SET quantity = 8,
    version_no = version_no + 1
WHERE id = 1
  AND version_no = 0;
~~~

Nếu phiên khác đã tăng version lên 1, câu UPDATE không khớp và ảnh hưởng 0 dòng. Ứng dụng phải đọc lại, tính lại hoặc báo conflict.

Snapshot read và optimistic locking giải quyết hai vấn đề khác nhau: snapshot xác định phiên bản được đọc; version condition phát hiện dữ liệu đã thay đổi trước khi ghi.

## 10. Phantom read cũng có thể quan sát bằng hai session

Snapshot không chỉ áp dụng cho một hàng. Nó có thể áp dụng cho kết quả của một truy vấn theo phạm vi.

Đưa bảng về trạng thái có một hàng trước khi chạy thử nghiệm:

~~~sql
UPDATE snapshot_lab
SET quantity = 100,
    version_no = 0
WHERE id = 1;
~~~

Session A ở REPEATABLE READ:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT id, quantity
FROM snapshot_lab
WHERE id BETWEEN 1 AND 5;
~~~

Session B chèn một hàng mới:

~~~sql
INSERT INTO snapshot_lab (id, quantity, version_no)
VALUES (2, 50, 0);
~~~

Sau khi B commit, Session A chạy lại truy vấn:

~~~sql
SELECT id, quantity
FROM snapshot_lab
WHERE id BETWEEN 1 AND 5;
~~~

Với consistent read ở InnoDB REPEATABLE READ, A tiếp tục thấy kết quả thuộc snapshot ban đầu và không thấy hàng id = 2 vừa được commit sau snapshot.

Nếu A chạy truy vấn tương tự trong một transaction READ COMMITTED mới, statement có thể nhìn thấy hàng mới.

Hiện tượng một lần đọc sau nhìn thấy thêm hàng thỏa điều kiện được gọi là phantom read. Gap lock và next-key lock có vai trò trong các locking read và thao tác ghi theo phạm vi; consistent read dùng MVCC snapshot có semantics khác.

Không nên dùng ví dụ này để kết luận mọi SELECT ở REPEATABLE READ đều khóa khoảng trống. SELECT consistent read thông thường và SELECT ... FOR UPDATE có hành vi locking khác nhau.

## 11. Quan sát phiên bản và lock trong MySQL

Khi thực nghiệm, có thể dùng một số công cụ để xác nhận session đang hoạt động và lock nào đang tồn tại.

### 11.1. Kiểm tra transaction và session

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx;
~~~

Truy vấn này giúp xem transaction InnoDB đang hoạt động, thời điểm bắt đầu và câu SQL hiện tại nếu có.

### 11.2. Xem lock đang được giữ hoặc chờ

MySQL 8 cung cấp:

~~~sql
SELECT
    ENGINE_TRANSACTION_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks;
~~~

Có thể kết hợp với performance_schema.data_lock_waits để xem transaction nào đang chặn transaction nào.

Trong thử nghiệm consistent read thông thường, không nên mong đợi một shared row lock trên hàng chỉ vì A đã SELECT. Khi dùng FOR UPDATE, có thể quan sát lock được cấp trên record hoặc index liên quan.

Cấu trúc bảng Performance Schema và quyền truy cập phụ thuộc phiên bản MySQL và quyền user.

### 11.3. Xem trạng thái InnoDB

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Phần TRANSACTIONS cho biết transaction đang hoạt động và một số thông tin lock. Phần LATEST DETECTED DEADLOCK hữu ích khi thử nghiệm có tạo ra deadlock.

## 12. Khác biệt snapshot giữa MySQL, PostgreSQL và SQL Server

Tên isolation level giống nhau không có nghĩa mọi database đều tạo snapshot và xử lý locking read giống nhau.

| Database/chế độ | Thời điểm snapshot hoặc cách đọc | Điều cần nhớ |
|---|---|---|
| MySQL InnoDB REPEATABLE READ | Consistent read thường tạo read view ở lần đọc nhất quán đầu tiên và tái sử dụng trong transaction | Locking read là current read, có thể thấy phiên bản hiện hành |
| MySQL InnoDB READ COMMITTED | Mỗi consistent read thường lấy snapshot mới theo statement | Hai SELECT trong cùng transaction có thể thấy commit khác nhau |
| PostgreSQL READ COMMITTED | Mỗi statement nhìn thấy snapshot tại thời điểm statement bắt đầu | SELECT sau có thể thấy transaction vừa commit |
| PostgreSQL REPEATABLE READ | Transaction dùng snapshot ổn định được lấy từ statement đầu tiên phù hợp | Locking read có thể báo serialization failure nếu dòng đã bị transaction khác thay đổi sau snapshot |
| SQL Server READ COMMITTED mặc định | Thường dùng shared lock trong thời gian đọc theo cấu hình truyền thống | Không mặc định là snapshot read |
| SQL Server READ_COMMITTED_SNAPSHOT | Mỗi statement đọc row version theo snapshot ở đầu statement | Reader-writer blocking giảm đáng kể |
| SQL Server SNAPSHOT | Transaction đọc row version theo snapshot của transaction | Cần bật ALLOW_SNAPSHOT_ISOLATION |

### PostgreSQL

Ở READ COMMITTED, mỗi statement có snapshot riêng. Nếu Session A đọc 100, Session B cập nhật thành 80 và commit, câu SELECT tiếp theo của A có thể thấy 80.

Ở REPEATABLE READ, PostgreSQL giữ snapshot ổn định cho transaction. Tuy nhiên, locking read như SELECT FOR UPDATE có hành vi khác với InnoDB. Nếu dòng mục tiêu đã bị transaction khác thay đổi sau khi snapshot của A được tạo, PostgreSQL có thể hủy transaction A với serialization failure thay vì trả phiên bản mới như current read của InnoDB.

### SQL Server

SQL Server không mặc định dùng MVCC snapshot cho READ COMMITTED trong mọi cấu hình. Với cấu hình truyền thống, shared lock được dùng trong lúc đọc. Nếu bật READ_COMMITTED_SNAPSHOT, READ COMMITTED chuyển sang đọc phiên bản theo statement.

SNAPSHOT là isolation level riêng, cần bật ALLOW_SNAPSHOT_ISOLATION. Nó cung cấp snapshot ở cấp transaction và có quy tắc xử lý xung đột cập nhật riêng.

Khi chuyển một bài thực nghiệm từ MySQL sang database khác, cần kiểm tra cấu hình database và isolation level thực tế thay vì chỉ thay tên lệnh SQL.

## 13. Các yếu tố làm snapshot cũ tồn tại lâu

Snapshot cũ phải được database hỗ trợ cho đến khi transaction kết thúc. Transaction đọc kéo dài có thể làm tăng chi phí lưu giữ phiên bản.

Trong InnoDB, undo record có thể chưa được purge nếu còn read view cần phiên bản cũ. Hệ quả có thể gồm:

- History list dài hơn.
- Tăng công việc purge.
- Tăng dung lượng undo cần giữ.
- Tăng áp lực I/O hoặc chi phí dựng phiên bản cũ trong một số workload.

Trong PostgreSQL, transaction snapshot lâu có thể ngăn VACUUM loại bỏ một số tuple phiên bản cũ còn cần thiết. Điều này có thể góp phần gây table bloat và tăng công việc vacuum.

Với SQL Server row versioning, transaction snapshot dài có thể làm version store giữ phiên bản lâu hơn. Chi phí cụ thể phụ thuộc cấu hình và phiên bản SQL Server.

Do đó, MVCC giúp giảm blocking giữa reader và writer nhưng không khiến transaction đọc kéo dài trở nên miễn phí. Hãy giữ transaction đọc trong thời gian cần thiết và tránh để session nhàn rỗi nhưng vẫn mở transaction.

## 14. Các lỗi thường gặp khi thực hiện thí nghiệm

**Session B không cập nhật được vì đang bị chặn.**

Kiểm tra Session A có dùng SELECT ... FOR UPDATE hoặc FOR SHARE hay không. Một SELECT consistent read thông thường trong InnoDB thường không khóa hàng theo cách đó. Cũng cần kiểm tra có transaction khác đang giữ lock hoặc DDL/metadata lock hay không.

**Session A đọc được giá trị mới dù đang ở REPEATABLE READ.**

Kiểm tra A đã thực hiện consistent read đầu tiên trước khi B commit chưa. Nếu snapshot được tạo sau commit của B, A sẽ thấy giá trị mới. Kiểm tra câu đọc có phải SELECT thông thường hay là locking/current read.

**Hai SELECT trong cùng transaction trả kết quả khác nhau.**

Kiểm tra isolation level, loại SELECT và engine. Trong InnoDB REPEATABLE READ, hai consistent read thông thường thường dùng cùng snapshot, nhưng SELECT ... FOR UPDATE là current read. Trong READ COMMITTED, mỗi statement có snapshot mới.

**Session A bị treo khi chạy FOR UPDATE.**

Có thể transaction khác đang giữ lock xung đột. Xem transaction đang chặn qua Performance Schema và xác nhận transaction đó đã commit hoặc rollback chưa.

**Không tái hiện được phantom insert.**

Kiểm tra đang dùng consistent read hay locking read, isolation level, index và phạm vi truy vấn. Snapshot read có thể không nhìn thấy hàng mới mà không cần giữ gap lock; locking read ở InnoDB có thể dùng next-key/gap lock để bảo vệ range.

**Giá trị bị ghi đè sau khi đọc snapshot cũ.**

Snapshot chỉ quyết định dữ liệu được nhìn thấy. Nếu ứng dụng ghi một giá trị tuyệt đối tính từ dữ liệu cũ, nó có thể ghi đè thay đổi mới hơn. Dùng UPDATE nguyên tử, version condition hoặc locking read tùy nghiệp vụ.

## 15. Quy trình thực nghiệm hai phiên đầy đủ

Có thể dùng checklist sau để chạy lại và ghi kết quả:

### Thử nghiệm A — REPEATABLE READ

1. Đặt quantity = 100.
2. Session A đặt isolation level REPEATABLE READ.
3. Session A BEGIN và SELECT lần đầu, ghi nhận 100.
4. Session B UPDATE quantity = 80 và COMMIT.
5. Session B SELECT, xác nhận 80.
6. Session A SELECT lại, xác nhận vẫn 100.
7. Session A COMMIT.
8. Session A mở transaction mới và xác nhận 80.

### Thử nghiệm B — READ COMMITTED

1. Đặt quantity = 100.
2. Session A đặt isolation level READ COMMITTED.
3. Session A BEGIN và SELECT, ghi nhận 100.
4. Session B UPDATE quantity = 80 và COMMIT.
5. Session A SELECT lại, xác nhận 80.
6. Session A COMMIT.

### Thử nghiệm C — Locking read

1. Đặt quantity = 100.
2. Session A BEGIN và SELECT ... FOR UPDATE.
3. Session B UPDATE cùng hàng và quan sát trạng thái chờ.
4. Session A COMMIT.
5. Session B tiếp tục và commit.
6. Kiểm tra giá trị cuối cùng.

### Thử nghiệm D — Snapshot read so với current read

1. Đặt quantity = 100.
2. Session A ở REPEATABLE READ và SELECT thông thường để tạo snapshot.
3. Session B cập nhật quantity = 80 và COMMIT.
4. Session A SELECT thông thường, ghi nhận 100.
5. Session A SELECT ... FOR UPDATE, ghi nhận current value 80.
6. Session A SELECT thông thường thêm lần nữa, quan sát snapshot cũ.
7. Session A COMMIT.

Không chạy nhiều thử nghiệm chồng lên nhau. Trước mỗi lần thử, đưa dữ liệu về trạng thái đã biết và bảo đảm transaction của lần trước đã kết thúc ở cả hai session.

## 16. Bài tập mở rộng

Sau khi hoàn tất các thử nghiệm, có thể tự thay đổi một yếu tố và dự đoán kết quả trước khi chạy.

### Bài tập 1: Tạo snapshot trước hay sau commit?

Session A BEGIN nhưng chưa SELECT. Session B cập nhật và commit. Sau đó A mới SELECT.

- A ở REPEATABLE READ sẽ nhìn thấy phiên bản nào?
- Điều gì thay đổi nếu A dùng START TRANSACTION WITH CONSISTENT SNAPSHOT?

### Bài tập 2: So sánh consistent read với current read

A tạo snapshot rồi đọc 100. B cập nhật thành 80 và commit. A chạy SELECT thông thường rồi SELECT FOR UPDATE.

- Vì sao hai câu SELECT có thể trả kết quả khác nhau?
- Sau FOR UPDATE, SELECT thông thường tiếp theo có thay đổi snapshot không?

### Bài tập 3: Kiểm tra READ COMMITTED

A ở READ COMMITTED đọc hai lần, B commit giữa hai lần đọc.

- Vì sao hai kết quả khác nhau?
- Nếu A chạy một SELECT tổng hợp thay vì đọc một dòng, snapshot áp dụng cho toàn statement như thế nào?

### Bài tập 4: Thử UPDATE dựa trên giá trị cũ

A đọc quantity = 100. B cập nhật quantity = 80 và commit. A thực hiện UPDATE đặt quantity = 90 dựa trên phép tính ở ứng dụng.

- Kết quả cuối là gì?
- Thay đổi câu lệnh thành quantity = quantity - 10 thì khác ra sao?
- Thêm điều kiện version_no = 0 giúp phát hiện điều gì?

### Bài tập 5: So sánh với PostgreSQL

Lặp lại tình huống A đọc một dòng ở REPEATABLE READ, B cập nhật và commit, sau đó A chạy SELECT FOR UPDATE.

- Hành vi có giống InnoDB không?
- Nếu nhận SQLSTATE 40001, ứng dụng cần làm gì?

## Kết luận

Đọc ảnh chụp cho phép một transaction quan sát phiên bản dữ liệu nhất quán trong khi transaction khác vẫn có thể cập nhật và commit phiên bản mới. Với InnoDB REPEATABLE READ, các consistent read trong cùng transaction thường dùng một read view được tạo ở lần đọc nhất quán đầu tiên. Với READ COMMITTED, mỗi consistent read lấy snapshot mới nên câu SELECT sau có thể nhìn thấy commit vừa xảy ra.

Cần phân biệt snapshot read với locking/current read. SELECT thông thường theo MVCC thường không chặn writer trên cùng hàng, còn SELECT FOR UPDATE có thể lấy lock và khiến writer phải chờ. Trong InnoDB, hai loại đọc này thậm chí có thể nhìn thấy hai phiên bản khác nhau trong cùng transaction.

Snapshot không tự bảo vệ quyết định ghi dựa trên dữ liệu cũ. Khi cần cập nhật an toàn, hãy dùng UPDATE nguyên tử có điều kiện, optimistic version hoặc locking read phù hợp với bất biến nghiệp vụ. Khi thực nghiệm trên PostgreSQL hay SQL Server, phải kiểm tra semantics và cấu hình riêng của engine vì cùng tên isolation level không bảo đảm cùng hành vi.
