# MySQL InnoDB: record lock, gap lock và next-key lock

MySQL InnoDB dùng khóa để điều phối các transaction cùng truy cập index và dữ liệu. Ngoài việc khóa một bản ghi cụ thể, InnoDB còn có thể khóa khoảng trống giữa các khóa index để ngăn transaction khác chèn bản ghi mới vào phạm vi mà transaction hiện tại đang bảo vệ.

Ba loại khóa cần phân biệt:

- **Record lock:** khóa một bản ghi trong index đang tồn tại.
- **Gap lock:** khóa khoảng trống giữa các bản ghi index, ngăn transaction khác chèn khóa mới vào khoảng đó.
- **Next-key lock:** kết hợp record lock với gap lock đứng ngay trước bản ghi.

Các cơ chế này giúp InnoDB bảo vệ locking read, UPDATE, DELETE và các truy vấn theo phạm vi, đặc biệt ở isolation level REPEATABLE READ. Hành vi thực tế phụ thuộc isolation level, index mà optimizer chọn, điều kiện truy vấn và phiên bản MySQL.

## 1. Khóa trong InnoDB gắn với index

Một điểm quan trọng thường gây nhầm lẫn là InnoDB không đơn giản khóa một hàng vật lý độc lập với index. **Record lock của InnoDB khóa một bản ghi trong index.**

Nếu bảng có clustered index, dữ liệu của hàng được tổ chức theo index đó. Thông thường, primary key là clustered index. Nếu không khai báo primary key, InnoDB chọn một unique index phù hợp hoặc tạo hidden clustered index.

Ví dụ:

~~~sql
CREATE TABLE employees (
    employee_id BIGINT NOT NULL,
    department_id BIGINT NOT NULL,
    salary DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (employee_id),
    KEY idx_department (department_id)
) ENGINE = InnoDB;
~~~

Bảng có:

- Clustered index trên employee_id.
- Secondary index trên department_id.

Khi truy vấn dùng secondary index, InnoDB có thể tìm entry trong secondary index rồi truy cập clustered index để lấy các cột còn lại. Với locking statement, engine có thể đặt lock trên các entry secondary index được truy cập và cả clustered index record tương ứng.

Vì vậy, cùng một hàng logic có thể liên quan đến nhiều index record. Đây là lý do lock wait hoặc deadlock đôi khi nhắc đến một index mà câu SQL không trực tiếp thể hiện.

Index được chọn trong execution plan cũng ảnh hưởng đến phạm vi khóa. Nếu truy vấn phải quét nhiều entry hơn cần thiết, nó có thể phải xử lý và khóa một phạm vi index rộng hơn.

## 2. Record lock: khóa một bản ghi index

Record lock là khóa trên một index record đang tồn tại. Nó ngăn transaction khác thực hiện thao tác xung đột trên bản ghi đó cho đến khi lock được giải phóng.

Giả sử có bảng:

~~~sql
CREATE TABLE accounts (
    account_id BIGINT NOT NULL,
    balance DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE = InnoDB;

INSERT INTO accounts (account_id, balance)
VALUES
    (10, 1000000),
    (20, 2000000),
    (30, 3000000);
~~~

Transaction T1 khóa tài khoản 20:

~~~sql
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id = 20
FOR UPDATE;
~~~

Vì account_id là primary key và điều kiện tìm kiếm là phép so sánh bằng trên toàn bộ unique key, InnoDB có thể dùng record lock trên index record tương ứng với tài khoản 20.

Transaction T2 vẫn có thể thao tác với tài khoản 10 nếu không có xung đột khác:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100000
WHERE account_id = 10;
~~~

Nhưng nếu T2 muốn cập nhật tài khoản 20:

~~~sql
UPDATE accounts
SET balance = balance - 50000
WHERE account_id = 20;
~~~

T2 có thể phải chờ T1 nhả lock.

Luồng xử lý:

~~~text
T1                                  T2
|                                   |
|-- SELECT account 20 FOR UPDATE   |
|-- Lấy record lock trên key 20    |
|                                   |
|                                   |-- UPDATE account 20
|                                   |-- Chờ lock
|                                   |
|-- COMMIT                          |
|-- Nhả lock                        |
|                                   |-- UPDATE tiếp tục
|                                   |-- COMMIT
~~~

Record lock phù hợp khi transaction cần bảo vệ một bản ghi đã tồn tại. Ví dụ:

- Cập nhật số dư tài khoản.
- Chuyển trạng thái đơn hàng.
- Sửa thông tin sản phẩm.
- Khóa một bản ghi để kiểm tra rồi cập nhật trong cùng transaction.

### Record lock không có nghĩa mọi SELECT đều khóa hàng

Một SELECT thông thường trong InnoDB thường là **consistent read** sử dụng MVCC. Nó đọc phiên bản phù hợp với snapshot và không cần đặt shared record lock trên từng hàng được đọc.

Muốn yêu cầu khóa tường minh, ứng dụng dùng locking read:

~~~sql
SELECT *
FROM accounts
WHERE account_id = 20
FOR UPDATE;
~~~

Hoặc:

~~~sql
SELECT *
FROM accounts
WHERE account_id = 20
FOR SHARE;
~~~

FOR UPDATE yêu cầu khóa phục vụ thao tác cập nhật; FOR SHARE yêu cầu khóa chia sẻ. Các khóa cụ thể và khả năng tương thích phụ thuộc engine.

## 3. Gap lock: khóa khoảng trống giữa các index record

Gap lock bảo vệ một khoảng trống trong index. Nó không khóa một record hiện có mà ngăn transaction khác chèn khóa mới vào khoảng đó.

Giả sử index có các giá trị:

~~~text
10        20        30
|---------|---------|
  gap       gap
~~~

Có thể hình dung các khoảng:

~~~text
(-infinity, 10)
(10, 20)
(20, 30)
(30, +infinity)
~~~

Nếu một transaction lấy gap lock trên khoảng (10, 20), transaction khác không thể INSERT một khóa có giá trị nằm trong khoảng này, chẳng hạn 15, trong thời gian lock còn hiệu lực.

Ví dụ tạo bảng:

~~~sql
CREATE TABLE measurements (
    measurement_id BIGINT NOT NULL,
    score INT NOT NULL,
    PRIMARY KEY (measurement_id),
    KEY idx_score (score)
) ENGINE = InnoDB;

INSERT INTO measurements (measurement_id, score)
VALUES
    (1, 10),
    (2, 20),
    (3, 30);
~~~

Ở REPEATABLE READ, một locking read trên một phạm vi index có thể lấy next-key/gap lock theo các entry được quét:

~~~sql
-- Transaction T1
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT *
FROM measurements
WHERE score > 10
  AND score < 20
FOR UPDATE;
~~~

Tùy điều kiện và execution plan, InnoDB có thể bảo vệ gap tương ứng trên index idx_score. Transaction khác chèn giá trị score = 15 có thể phải chờ:

~~~sql
-- Transaction T2
START TRANSACTION;

INSERT INTO measurements (measurement_id, score)
VALUES (4, 15);
~~~

Nếu INSERT cần đi vào gap đang bị khóa, T2 phải chờ cho đến khi T1 kết thúc hoặc lock được giải phóng.

### Gap lock bảo vệ khoảng trống, không bảo vệ một hàng hiện có

Đây là điểm khác biệt chính:

- Record lock khóa một index record đang tồn tại.
- Gap lock ngăn chèn một index record mới vào một khoảng.
- Gap lock không phải cơ chế khóa nội dung của một hàng hiện có.

Gap lock giúp ngăn phantom insert trong những truy vấn và isolation level cần bảo vệ phạm vi. Nó đặc biệt quan trọng khi transaction đọc một tập dữ liệu theo điều kiện range và cần bảo đảm không có hàng mới xuất hiện trong phạm vi đó trước khi transaction kết thúc.

### Gap lock có thể tồn tại ở khoảng không có hàng nào

Giả sử index có các khóa 10 và 20. Một truy vấn tìm giá trị nằm giữa hai khóa có thể không trả về hàng nào:

~~~sql
SELECT *
FROM measurements
WHERE score > 10
  AND score < 20
FOR UPDATE;
~~~

Dù kết quả rỗng, locking read ở REPEATABLE READ vẫn có thể cần bảo vệ gap tương ứng để transaction khác không chèn một giá trị làm thay đổi kết quả của lần đọc sau.

Đây là điểm quan trọng khi điều tra: ứng dụng có thể thấy SELECT trả về 0 dòng nhưng một transaction khác vẫn bị chặn khi INSERT vào vùng đó.

Phạm vi gap cụ thể phụ thuộc index được dùng và cách InnoDB thực hiện range scan. Không nên suy luận phạm vi khóa chỉ từ điều kiện WHERE mà chưa xem execution plan.

## 4. Next-key lock: kết hợp record lock và gap lock

Next-key lock là tổ hợp:

\[
\text{Next-key lock} = \text{Record lock} + \text{Gap lock trước record}
\]

Nói cách khác, nó khóa một index record và khoảng trống đứng ngay trước record đó.

Với index:

~~~text
10        20        30
|---------|---------|
~~~

Next-key lock trên record 20 có thể được hình dung là khoảng (10, 20]. Nó bao gồm:

- Gap (10, 20).
- Record có khóa 20.

Dấu ngoặc vuông ở phía phải biểu thị record 20 thuộc phạm vi khóa. Đây là cách mô hình hóa khái niệm; phạm vi lock thực tế phụ thuộc điều kiện truy vấn và các entry mà execution plan quét.

Next-key lock kết hợp hai mục đích:

1. Bảo vệ record hiện tại khỏi thao tác ghi xung đột.
2. Bảo vệ gap trước record khỏi INSERT tạo phantom trong khoảng đó.

Trong InnoDB, next-key locking là cơ chế quan trọng để thực hiện các locking read và thao tác ghi ở REPEATABLE READ.

### Ví dụ với range query

Giả sử truy vấn tìm các nhân viên có salary trong một khoảng:

~~~sql
START TRANSACTION;

SELECT employee_id, salary
FROM employees
WHERE salary >= 5000000
  AND salary < 10000000
FOR UPDATE;
~~~

Nếu có index trên salary, InnoDB có thể quét một vùng index và đặt next-key lock trên các record liên quan. Những gap nằm trong phạm vi được bảo vệ cũng có thể ngăn transaction khác chèn một mức lương mới vào khoảng đó.

Ví dụ T2 cố thêm một nhân viên có salary = 7000000:

~~~sql
INSERT INTO employees (employee_id, department_id, salary)
VALUES (100, 5, 7000000);
~~~

T2 có thể phải chờ T1 commit hoặc rollback nếu vị trí index cần chèn nằm trong gap bị khóa.

### Supremum pseudo-record

Trong InnoDB, next-key locking còn sử dụng một pseudo-record có tên **supremum** để biểu diễn phần cuối của index, sau khóa lớn nhất hiện có.

Ví dụ:

~~~text
10        20        30        supremum
|---------|---------|------------->
~~~

Gap trước supremum đại diện cho khoảng từ khóa lớn nhất đến dương vô cực. Khi range scan đi đến cuối index, lock trên supremum có thể bảo vệ khoảng cuối này.

Supremum không phải một hàng dữ liệu thực trong bảng. Nó là phần tử giả trong cấu trúc index được dùng để biểu diễn ranh giới cuối.

## 5. So sánh ba loại lock

| Đặc điểm | Record lock | Gap lock | Next-key lock |
|---|---|---|---|
| Đối tượng | Index record hiện có | Khoảng trống giữa các index record | Index record và gap đứng trước nó |
| Ngăn UPDATE record | Có, nếu xung đột | Không trực tiếp khóa record hiện có | Có |
| Ngăn INSERT vào gap | Không chỉ bằng record lock | Có | Có, trong gap được bảo vệ |
| Bảo vệ phantom | Không đủ nếu chỉ khóa record | Có thể bảo vệ phạm vi gap | Có thể bảo vệ record và gap |
| Thường gặp | Unique equality lookup trên record tồn tại | Range locking và một số tình huống kiểm tra khóa | Locking read/UPDATE/DELETE ở REPEATABLE READ |
| Phụ thuộc index | Có | Có | Có |

Một câu lệnh SQL có thể tạo nhiều lock thuộc các loại khác nhau trên nhiều index. Không nên gắn một câu SELECT FOR UPDATE với đúng một loại lock duy nhất.

## 6. Vì sao InnoDB cần gap lock và next-key lock?

Nếu database chỉ khóa các record hiện có, transaction khác vẫn có thể chèn một record mới vào giữa phạm vi mà transaction hiện tại đang đọc.

Giả sử T1 đọc các đơn hàng có status = 'PENDING' và cần bảo đảm không có đơn hàng mới nào xuất hiện trong phạm vi khóa cho đến khi transaction kết thúc.

Nếu T1 chỉ khóa các dòng hiện có, T2 có thể chèn một đơn hàng mới có status = 'PENDING'. Khi T1 đọc lại, nó có thể thấy thêm một hàng. Đây là phantom row.

Gap lock và next-key lock cho phép InnoDB bảo vệ cả khoảng khóa index, ngăn việc chèn các khóa mới vào phạm vi cần bảo vệ.

### Ví dụ phantom insert

~~~text
Ban đầu:
Index status có các khóa:
CANCELLED, PAID

T1:
SELECT ... WHERE status = 'PENDING' FOR UPDATE
Kết quả: 0 dòng

T2:
INSERT một dòng status = 'PENDING'

Nếu gap không được bảo vệ:
    T1 đọc lại có thể thấy một dòng mới.

Nếu gap được bảo vệ:
    INSERT của T2 phải chờ.
~~~

Ví dụ trên mô tả mục tiêu của phạm vi locking. Lock thực tế còn phụ thuộc index, predicate và isolation level. Nếu status không có index phù hợp, cách InnoDB quét và khóa có thể rộng hơn nhiều so với phạm vi logic mà ứng dụng mong muốn.

## 7. Unique index và trường hợp tìm kiếm bằng toàn bộ unique key

InnoDB có thể dùng record lock thay vì next-key lock trong một trường hợp quan trọng: truy vấn tìm kiếm bằng phép so sánh bằng trên toàn bộ unique index và tìm thấy record tương ứng.

Ví dụ:

~~~sql
SELECT *
FROM accounts
WHERE account_id = 20
FOR UPDATE;
~~~

Vì account_id là primary key và truy vấn tìm đúng một giá trị tồn tại, InnoDB chỉ cần khóa record tương ứng theo trường hợp unique lookup này; không cần khóa gap trước record để bảo vệ một range scan.

Ngược lại, truy vấn range:

~~~sql
SELECT *
FROM accounts
WHERE account_id >= 20
  AND account_id < 30
FOR UPDATE;
~~~

có thể cần next-key lock vì transaction đang bảo vệ một phạm vi.

Một số điểm cần chú ý:

- Phải dùng đầy đủ các cột của unique key.
- Nếu chỉ dùng một phần của composite unique index, truy vấn không còn là unique equality lookup đầy đủ.
- Nếu dùng một điều kiện range, next-key/gap locking có thể được áp dụng.
- Nếu truy vấn không tìm thấy record, phạm vi bảo vệ phụ thuộc isolation level và cách tìm kiếm; không nên suy rộng ngoại lệ unique lookup cho trường hợp mọi truy vấn đều trả về 0 dòng.

Ví dụ composite unique key:

~~~sql
CREATE TABLE reservations (
    room_id BIGINT NOT NULL,
    reservation_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL,
    UNIQUE KEY uq_room_date (room_id, reservation_date)
) ENGINE = InnoDB;
~~~

Truy vấn equality trên cả room_id và reservation_date có thể sử dụng unique lookup. Truy vấn chỉ lọc room_id hoặc lọc một khoảng reservation_date có phạm vi truy cập khác và có thể cần gap/next-key lock.

## 8. INSERT intention lock và quan hệ với gap lock

Khi INSERT một index record mới, InnoDB thường sử dụng **insert intention lock** trên gap nơi record mới sẽ được đặt.

Insert intention lock là một loại gap-related lock cho biết transaction dự định chèn vào một vị trí trong gap. Nó cho phép các transaction khác nhau chèn các khóa vào những vị trí khác nhau của cùng một gap mà không nhất thiết phải chờ nhau.

Ví dụ, index có các khóa 10 và 20:

~~~text
10 ---------------------- 20
       ^           ^
     insert 14   insert 17
~~~

Hai transaction chèn 14 và 17 có thể cùng tiến hành vì vị trí chèn khác nhau và không xung đột với nhau.

Nhưng nếu một transaction đang giữ gap lock trên (10,20), insert intention lock của transaction muốn chèn vào gap có thể phải chờ.

### Ví dụ INSERT bị chặn bởi gap lock

~~~sql
-- Transaction T1
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT *
FROM measurements
WHERE score > 10
  AND score < 20
FOR UPDATE;
~~~

Trong lúc T1 còn mở:

~~~sql
-- Transaction T2
START TRANSACTION;

INSERT INTO measurements (measurement_id, score)
VALUES (4, 15);
~~~

T2 có thể phải chờ vì vị trí score = 15 nằm trong gap đang được T1 bảo vệ.

### Gap lock có thể tương thích với gap lock khác

Một chi tiết dễ gây ngạc nhiên: gap lock thuần túy có tính chất **purely inhibitive**, nghĩa là mục đích của nó là ngăn INSERT vào gap. Các gap lock của nhiều transaction có thể cùng tồn tại, kể cả khi một số thông tin lock mode được hiển thị là shared hoặc exclusive.

Điều này khác với cách hiểu thông thường về shared/exclusive record lock. Không nên dùng bảng tương thích S/X của record lock để suy luận trực tiếp mọi tương tác gap lock.

Xung đột thường xuất hiện khi một transaction cần insert vào gap bị gap lock bảo vệ. Insert intention lock có thể phải chờ gap lock đang tồn tại.

## 9. Gap lock có thể dẫn đến deadlock như thế nào?

Do gap lock có thể cùng tồn tại giữa nhiều transaction, một tình huống deadlock có thể xảy ra khi hai transaction cùng khóa một gap rồi cùng cố INSERT.

Ví dụ khái quát:

~~~text
T1                                      T2
----------------------------------      ----------------------------------
BEGIN                                   BEGIN
Lấy gap lock trên cùng gap              Lấy gap lock trên cùng gap

INSERT key 15                           INSERT key 17
Cần insert intention lock                Cần insert intention lock
Chờ gap lock của T2                     Chờ gap lock của T1

T1 chờ T2                               T2 chờ T1
                 DEADLOCK
~~~

Database phát hiện chu trình chờ và chọn một transaction làm victim. Transaction còn lại có thể tiếp tục sau khi lock được giải phóng.

Đây là một lý do không nên giả định rằng gap lock chỉ làm INSERT bị chờ mà không thể tạo deadlock. Những transaction cùng bảo vệ một khoảng rồi chuyển sang INSERT có thể hình thành chu trình chờ.

Cách giảm nguy cơ:

- Tránh giữ transaction mở lâu trong lúc chờ thao tác khác.
- Thiết kế thứ tự truy cập và insert nhất quán.
- Xác định index/range mà locking statement đang bảo vệ.
- Dùng unique constraint để bảo vệ tính duy nhất thay vì tự kiểm tra rồi chèn nếu phù hợp.
- Xử lý deadlock bằng retry toàn bộ transaction có giới hạn.
- Chọn isolation level và locking strategy phù hợp với yêu cầu phantom protection.

## 10. Isolation level ảnh hưởng đến gap và next-key lock

InnoDB mặc định dùng REPEATABLE READ trong nhiều cấu hình MySQL. Gap lock và next-key lock có vai trò quan trọng ở mức này để ngăn phantom insert trong các locking read và thao tác ghi theo phạm vi.

### REPEATABLE READ

Ở REPEATABLE READ:

- SELECT thông thường thường là consistent read theo MVCC snapshot.
- SELECT ... FOR UPDATE và SELECT ... FOR SHARE là locking/current read.
- Range locking read và UPDATE/DELETE có thể sử dụng next-key lock.
- Gap lock giúp bảo vệ khoảng khóa và ngăn insert phantom trong phạm vi liên quan.

Ví dụ:

~~~sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT *
FROM measurements
WHERE score BETWEEN 10 AND 20
FOR UPDATE;

-- Các transaction khác có thể bị chặn khi chèn
-- khóa index vào gap đang được bảo vệ.

COMMIT;
~~~

### READ COMMITTED

Ở READ COMMITTED:

- Mỗi consistent read thường lấy snapshot mới ở cấp statement.
- Gap locking cho các search/index scan thông thường thường bị tắt.
- Record lock vẫn được dùng để bảo vệ các hàng cần cập nhật hoặc khóa.
- Gap lock vẫn có thể được sử dụng trong một số trường hợp đặc biệt, như kiểm tra foreign key và duplicate-key.

Do gap locking giảm đi, INSERT vào khoảng trống có thể ít bị chặn hơn. Đổi lại, phantom row có thể xuất hiện giữa các statement trong cùng transaction theo ngữ nghĩa của isolation level.

### Bảng so sánh

| Khía cạnh | REPEATABLE READ | READ COMMITTED |
|---|---|---|
| Consistent read | Snapshot thường ổn định trong transaction | Snapshot mới ở mỗi statement |
| Record lock cho thao tác ghi | Có | Có |
| Gap lock cho range scan thông thường | Có thể được dùng | Thường bị tắt |
| Next-key lock | Được dùng rộng rãi để bảo vệ range | Ít được dùng hơn trong search thông thường |
| Phantom insert | Được ngăn trong các phạm vi locking phù hợp | Có thể xuất hiện giữa các statement |
| Gap lock cho FK/duplicate check | Có | Vẫn có thể có |

Không nên hiểu bảng này là mọi truy vấn ở REPEATABLE READ đều lấy next-key lock hoặc mọi truy vấn READ COMMITTED đều chỉ có record lock. Loại truy vấn, index, constraint và đường truy cập thực tế vẫn quyết định lock cụ thể.

READ UNCOMMITTED và các trường hợp khác có semantics riêng. Hãy xem tài liệu phiên bản MySQL đang triển khai nếu ứng dụng dựa vào hành vi khóa cụ thể.

## 11. Consistent read và locking read không giống nhau

Một nguồn nhầm lẫn lớn là nghĩ rằng SELECT nào cũng lấy record/gap/next-key lock.

Trong InnoDB:

**Consistent read** là SELECT thông thường sử dụng MVCC. Nó đọc phiên bản dữ liệu phù hợp với snapshot và thông thường không đặt row lock lên các dòng được đọc.

Ví dụ:

~~~sql
START TRANSACTION;

SELECT *
FROM measurements
WHERE score BETWEEN 10 AND 20;

COMMIT;
~~~

**Locking read** là SELECT yêu cầu khóa:

~~~sql
START TRANSACTION;

SELECT *
FROM measurements
WHERE score BETWEEN 10 AND 20
FOR UPDATE;

COMMIT;
~~~

Hoặc khóa chia sẻ:

~~~sql
START TRANSACTION;

SELECT *
FROM measurements
WHERE score BETWEEN 10 AND 20
FOR SHARE;

COMMIT;
~~~

Locking read thường là current read: nó làm việc với dữ liệu hiện hành theo quy tắc của engine và lấy lock phù hợp. Trong khi đó, consistent read đọc snapshot và không giữ record lock theo cách tương tự.

Một số điểm cần nhớ:

- FOR UPDATE thường dùng khi transaction chuẩn bị thay đổi dữ liệu.
- FOR SHARE dùng khi cần đọc và giữ quyền chia sẻ trên dữ liệu.
- Locking read phải nằm trong transaction nếu muốn giữ lock qua nhiều statement.
- Nếu autocommit = 1, transaction của một statement có thể kết thúc ngay khi statement hoàn tất, làm lock được giải phóng ngay sau đó.
- Locking read không tự bảo vệ mọi bất biến nghiệp vụ nếu truy vấn không khóa đúng phạm vi.

## 12. UPDATE và DELETE cũng có thể lấy next-key lock

Gap và next-key lock không chỉ xuất hiện với SELECT FOR UPDATE. Các câu UPDATE và DELETE cũng có thể cần khóa các index record và phạm vi mà chúng truy cập.

Ví dụ:

~~~sql
UPDATE measurements
SET score = score + 1
WHERE score >= 10
  AND score < 20;
~~~

InnoDB phải tìm các record phù hợp và khóa tài nguyên cần thiết để cập nhật. Nếu sử dụng range scan ở REPEATABLE READ, các next-key lock có thể được áp dụng trên vùng index được quét.

Tương tự:

~~~sql
DELETE FROM measurements
WHERE score >= 10
  AND score < 20;
~~~

Câu DELETE cần bảo vệ các record bị xóa và có thể khóa phạm vi liên quan.

Một truy vấn có điều kiện WHERE rộng hoặc thiếu index phù hợp có thể khiến engine quét nhiều record hơn dự kiến. Điều này có thể tăng số lock, lock wait và deadlock.

Không nên chỉ nhìn vào số hàng bị thay đổi để ước lượng lock footprint. Cần xem index được quét và loại isolation đang hoạt động.

## 13. Index ảnh hưởng trực tiếp đến phạm vi khóa

InnoDB khóa index record và gap liên quan đến đường truy cập. Do đó, index là một phần quan trọng của thiết kế concurrency.

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 42
  AND status = 'PENDING'
FOR UPDATE;
~~~

Nếu bảng có index:

~~~sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);
~~~

Optimizer có thể tìm vùng khóa hẹp hơn theo customer_id và status.

Nếu chỉ có index trên customer_id, engine có thể phải đọc thêm nhiều entry của khách hàng rồi lọc status.

Nếu không có index phù hợp, engine có thể quét một phần lớn hoặc toàn bộ clustered index. Với locking statement, số record được truy cập và khóa có thể tăng đáng kể.

Điều đó có thể gây:

- Nhiều transaction phải chờ hơn.
- INSERT bị chặn do gap lock trên phạm vi rộng.
- Tăng thời gian giữ lock.
- Tăng xác suất deadlock.
- Tăng chi phí quản lý lock.

### Composite index và thứ tự cột

Index kết hợp nên phản ánh các điều kiện lọc quan trọng:

~~~sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at);
~~~

Với truy vấn:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 42
  AND status = 'PENDING'
  AND created_at >= '2026-01-01'
FOR UPDATE;
~~~

Index có thể giúp thu hẹp phạm vi scan hơn so với chỉ dùng một index đơn cột.

Thứ tự cột ảnh hưởng khả năng tận dụng B-tree index. Thường các cột được so sánh bằng được đặt trước cột range, nhưng cần dựa vào workload, cardinality và các truy vấn khác.

Không nên tạo index chỉ để giảm lock mà bỏ qua chi phí ghi. Mỗi index bổ sung cần được duy trì khi INSERT, UPDATE hoặc DELETE.

## 14. Locking read không tìm thấy dòng vẫn cần phân tích phạm vi

Một trường hợp dễ gây bất ngờ là truy vấn trả về 0 dòng nhưng transaction khác vẫn bị chặn khi INSERT.

Ví dụ ứng dụng kiểm tra một mã đặt chỗ chưa tồn tại:

~~~sql
START TRANSACTION;

SELECT *
FROM reservations
WHERE reservation_code = 'R-2026-100'
FOR UPDATE;
~~~

Nếu không có bản ghi phù hợp, ứng dụng có thể nghĩ rằng không có gì bị khóa. Nhưng với REPEATABLE READ, tùy index và cách tìm kiếm, InnoDB có thể đặt gap lock để bảo vệ vị trí mà khóa mới có thể được chèn.

Transaction khác thử:

~~~sql
INSERT INTO reservations (reservation_code, room_id)
VALUES ('R-2026-100', 10);
~~~

INSERT có thể phải chờ.

Điều này có thể hữu ích khi ứng dụng thực sự cần bảo vệ một khoảng trống, nhưng cũng có thể gây contention không mong muốn nếu code chỉ kiểm tra tồn tại trước khi INSERT.

Nếu mục tiêu là bảo đảm reservation_code duy nhất, nên khai báo UNIQUE constraint:

~~~sql
ALTER TABLE reservations
ADD CONSTRAINT uq_reservation_code
UNIQUE (reservation_code);
~~~

Sau đó thực hiện INSERT và xử lý duplicate-key theo quy tắc nghiệp vụ. Constraint là lớp bảo vệ tính duy nhất đáng tin cậy trước cạnh tranh.

## 15. Ví dụ đặt chỗ và bảo vệ khoảng thời gian

Giả sử hệ thống đặt phòng có bảng:

~~~sql
CREATE TABLE room_bookings (
    booking_id BIGINT NOT NULL,
    room_id BIGINT NOT NULL,
    start_at DATETIME NOT NULL,
    end_at DATETIME NOT NULL,
    PRIMARY KEY (booking_id),
    KEY idx_room_start (room_id, start_at)
) ENGINE = InnoDB;
~~~

Ứng dụng muốn kiểm tra phòng 10 có booking nào giao với khoảng thời gian yêu cầu không:

~~~sql
START TRANSACTION;

SELECT booking_id, start_at, end_at
FROM room_bookings
WHERE room_id = 10
  AND start_at < '2026-11-15 11:00:00'
  AND end_at > '2026-11-15 10:00:00'
FOR UPDATE;

-- Nếu không có booking xung đột, tạo booking mới.

COMMIT;
~~~

Truy vấn có thể dùng index trên (room_id, start_at) để tìm các booking ứng viên. Tuy nhiên, việc bảo vệ điều kiện không chồng lấn thời gian không đơn giản chỉ là khóa những dòng đã tìm thấy.

Nếu không có dòng nào giao nhau, hai transaction có thể cùng thấy kết quả rỗng rồi cùng INSERT hai booking chồng lấn. Gap lock chỉ bảo vệ phạm vi index mà engine thực sự quét; điều kiện overlap liên quan đến hai cột thời gian và không nhất thiết được biểu diễn hoàn toàn bởi một range liên tục trên index.

Các cách thiết kế có thể cân nhắc:

- Khóa một guard row theo room_id trước khi kiểm tra và tạo booking.
- Dùng một tài nguyên đại diện cho phòng/ngày/slot để tuần tự hóa việc đặt.
- Thiết kế mô hình slot cố định với unique constraint trên room_id và slot.
- Dùng isolation level và index phù hợp, sau khi kiểm chứng hành vi trên InnoDB.
- Kiểm tra lại bằng test đồng thời để bảo đảm hai booking không thể cùng commit nếu giao nhau.

Đây là ví dụ cho thấy gap/next-key lock là công cụ bảo vệ index range, nhưng không tự động diễn đạt mọi bất biến nghiệp vụ phức tạp.

## 16. Cách quan sát lock trong MySQL

Khi transaction bị chờ, cần xác định:

- Transaction nào đang giữ lock.
- Transaction nào đang yêu cầu lock.
- Bảng và index liên quan.
- Loại lock và lock mode.
- Record hoặc khoảng index bị khóa.
- SQL statement và transaction age.
- Isolation level và execution plan.

### 16.1. performance_schema.data_locks

MySQL 8 cung cấp thông tin lock trong performance_schema.data_locks.

Ví dụ:

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

Các cột hữu ích:

- OBJECT_NAME: bảng đang liên quan.
- INDEX_NAME: index được khóa.
- LOCK_TYPE: loại đối tượng khóa, ví dụ TABLE hoặc RECORD.
- LOCK_MODE: mode hiển thị, có thể chứa thông tin như X, S, GAP, REC_NOT_GAP hoặc INSERT_INTENTION.
- LOCK_STATUS: trạng thái GRANTED hoặc WAITING.
- LOCK_DATA: dữ liệu khóa nếu engine có thể cung cấp.

Ví dụ một số cách diễn giải:

| Lock mode hiển thị | Ý nghĩa khái quát |
|---|---|
| X,REC_NOT_GAP | Exclusive record lock, không khóa gap trước record |
| S,REC_NOT_GAP | Shared record lock, không khóa gap trước record |
| X,GAP | Gap lock theo cách hiển thị của InnoDB |
| S,GAP | Gap lock chia sẻ theo cách hiển thị của InnoDB |
| X | Có thể là next-key lock hoặc mode record tùy ngữ cảnh |
| X,GAP,INSERT_INTENTION | Insert intention lock trên gap |

Tên hiển thị và chi tiết có thể khác theo phiên bản. Cần kết hợp LOCK_MODE, INDEX_NAME, LOCK_DATA và transaction đang chạy để diễn giải chính xác.

### 16.2. performance_schema.data_lock_waits

Có thể kết hợp data_lock_waits với data_locks để tìm quan hệ giữa transaction đang chờ và transaction đang giữ lock:

~~~sql
SELECT
    w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
    req.OBJECT_SCHEMA AS waiting_schema,
    req.OBJECT_NAME AS waiting_table,
    req.INDEX_NAME AS waiting_index,
    req.LOCK_MODE AS waiting_lock_mode,
    w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx,
    blk.LOCK_MODE AS blocking_lock_mode,
    blk.LOCK_DATA AS blocking_lock_data
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
  ON req.ENGINE = w.ENGINE
 AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
  ON blk.ENGINE = w.ENGINE
 AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
~~~

Truy vấn này giúp nối yêu cầu lock với lock đang chặn. Cấu trúc bảng và cột cần kiểm tra theo phiên bản MySQL cụ thể.

### 16.3. SHOW ENGINE INNODB STATUS

Lệnh:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

cung cấp thông tin về trạng thái InnoDB, bao gồm phần TRANSACTIONS và LATEST DETECTED DEADLOCK.

Deadlock section thường cho biết:

- Các transaction tham gia deadlock.
- SQL statement liên quan.
- Lock đang giữ.
- Lock đang chờ.
- Transaction được chọn làm victim.

Đây là nguồn quan trọng để điều tra deadlock trong InnoDB. Nếu cần theo dõi liên tục, có thể dùng Performance Schema và các công cụ monitoring thay vì chỉ xem trạng thái tại một thời điểm.

## 17. Cách đọc execution plan để hiểu lock footprint

Vì lock gắn với index record và gap, execution plan có vai trò quan trọng.

Dùng EXPLAIN:

~~~sql
EXPLAIN
SELECT *
FROM measurements
WHERE score >= 10
  AND score < 20
FOR UPDATE;
~~~

Kiểm tra:

- key: index optimizer chọn.
- type: access type, chẳng hạn range, ref hoặc ALL.
- rows: số dòng ước lượng cần đọc.
- Extra: thông tin bổ sung về cách thực thi.

Nếu truy vấn sử dụng idx_score với range scan, phạm vi index được truy cập có thể tương đối hẹp. Nếu optimizer chọn full table scan, truy vấn có thể phải đọc nhiều record hơn và phạm vi khóa có thể rộng hơn.

Trên phiên bản MySQL hỗ trợ, có thể dùng:

~~~sql
EXPLAIN ANALYZE
SELECT *
FROM measurements
WHERE score >= 10
  AND score < 20;
~~~

EXPLAIN ANALYZE thực sự chạy truy vấn SELECT để thu thập số liệu thực tế. Với locking read hoặc truy vấn có tác dụng phụ, cần thực hiện trong môi trường kiểm thử và hiểu transaction context trước khi dùng.

Không nên kết luận lock footprint chỉ từ rows ước lượng. Cần kết hợp plan thực tế, data_locks, data_lock_waits và isolation level.

## 18. Giảm gap lock và lock contention như thế nào?

Có nhiều cách giảm phạm vi khóa không cần thiết.

### 18.1. Tạo index phù hợp

Nếu truy vấn thường xuyên lọc theo customer_id và status:

~~~sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);
~~~

Index giúp thu hẹp range scan, giảm số record engine cần truy cập.

### 18.2. Giữ transaction ngắn

Lock thường được giữ đến COMMIT hoặc ROLLBACK. Không nên giữ transaction trong lúc:

- Gọi HTTP API.
- Gửi email.
- Chờ người dùng xác nhận.
- Xử lý file lớn.
- Thực hiện tính toán không cần bảo vệ bằng lock.

### 18.3. Chọn isolation level phù hợp

Nếu ứng dụng không cần bảo vệ phantom bằng gap locking cho mọi truy vấn, có thể cân nhắc READ COMMITTED. Tuy nhiên, phải hiểu tác động đến tính nhất quán và các truy vấn phụ thuộc snapshot.

Không nên hạ isolation level chỉ để giảm blocking mà không xác định bất biến nghiệp vụ cần giữ.

### 18.4. Dùng unique constraint thay cho check-then-insert

Ví dụ bảo vệ mã đặt chỗ:

~~~sql
CREATE UNIQUE INDEX uq_reservation_code
ON reservations (reservation_code);
~~~

Ứng dụng thực hiện INSERT và xử lý duplicate-key thay vì chỉ SELECT kiểm tra rồi INSERT. Unique index là cơ chế cưỡng chế tính duy nhất ngay cả khi nhiều request cạnh tranh.

### 18.5. Dùng UPDATE có điều kiện

Với tồn kho:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 42
  AND available_quantity > 0;
~~~

Kiểm tra affected rows để xác định có giữ được một đơn vị hay không. Câu UPDATE nguyên tử giúp tránh khoảng trống giữa bước đọc và bước ghi.

### 18.6. Xem xét NOWAIT và SKIP LOCKED

MySQL 8 hỗ trợ các tùy chọn locking read:

~~~sql
SELECT *
FROM jobs
WHERE status = 'READY'
ORDER BY job_id
LIMIT 10
FOR UPDATE SKIP LOCKED;
~~~

SKIP LOCKED bỏ qua những record đang bị transaction khác khóa, phù hợp với mô hình nhiều worker cùng lấy việc từ một queue trong database.

NOWAIT khiến truy vấn thất bại ngay nếu lock không thể lấy lập tức:

~~~sql
SELECT *
FROM accounts
WHERE account_id = 20
FOR UPDATE NOWAIT;
~~~

Các tùy chọn này thay đổi hành vi chờ, không xóa nguyên nhân tranh chấp. SKIP LOCKED cũng có thể trả về một tập kết quả không nhất quán với góc nhìn thông thường, vì vậy chỉ nên dùng cho workload như hàng đợi hoặc phân phối công việc khi semantics phù hợp.

## 19. Những nhầm lẫn thường gặp

**“Record lock khóa một hàng vật lý độc lập với index.”**

Không. InnoDB khóa index record. Một hàng có thể liên quan đến clustered index và secondary index.

**“Gap lock khóa record nằm giữa khoảng.”**

Không. Gap lock bảo vệ khoảng trống, ngăn insert vào khoảng đó. Record lock mới khóa một index record hiện có.

**“Next-key lock chỉ là record lock.”**

Không. Next-key lock bao gồm record và gap ngay trước record đó.

**“SELECT thông thường luôn lấy record lock.”**

Không. SELECT consistent read thường dùng MVCC và không đặt shared row lock trên các dòng đọc. Locking read như FOR UPDATE hoặc FOR SHARE mới yêu cầu khóa tường minh.

**“SELECT FOR UPDATE chỉ khóa các hàng được trả về.”**

Không thể luôn kết luận như vậy. InnoDB có thể khóa các index record được scan và các khoảng liên quan theo isolation level, index và execution plan. Một truy vấn trả về ít dòng vẫn có thể tạo lock footprint lớn.

**“Gap lock chỉ tồn tại ở REPEATABLE READ.”**

Không hoàn toàn. Gap locking cho search/index scan thông thường thường bị tắt ở READ COMMITTED, nhưng gap lock vẫn có thể xuất hiện trong một số trường hợp như foreign key và duplicate-key checking.

**“Không tìm thấy hàng nghĩa là không có lock.”**

Không nhất thiết. Một locking range search có thể bảo vệ gap dù không trả về record nào.

**“Thêm index sẽ loại bỏ mọi deadlock.”**

Không. Index phù hợp có thể thu hẹp phạm vi scan, nhưng deadlock vẫn có thể xảy ra do thứ tự lấy lock, nhiều index, foreign key hoặc các transaction cập nhật cùng tài nguyên.

## 20. Quy trình điều tra lock wait trong InnoDB

Khi INSERT, UPDATE hoặc SELECT FOR UPDATE bị chờ, có thể tiến hành:

1. Xác định transaction đang chờ và transaction đang chặn.
2. Xem bảng, index, lock mode và lock data qua Performance Schema.
3. Kiểm tra isolation level của các transaction.
4. Thu thập câu SQL cùng tham số thực tế.
5. Chạy EXPLAIN để xác định index và range scan.
6. Kiểm tra có gap lock, next-key lock hoặc insert intention lock không.
7. Xem transaction có mở quá lâu hoặc thực hiện I/O ngoài database không.
8. Kiểm tra deadlock report nếu có chu trình chờ.
9. Đánh giá index, predicate và khả năng dùng unique lookup.
10. Thử điều chỉnh truy vấn hoặc isolation level trong môi trường kiểm thử và đo lại lock wait.

Khi đọc data_locks, cần chú ý INDEX_NAME và LOCK_MODE. Chỉ nhìn tên bảng không đủ để biết transaction đang khóa record hay gap. Với secondary index, cần kiểm tra cả index entry và clustered record liên quan.

## Kết luận

Record lock, gap lock và next-key lock là ba khái niệm nền tảng trong cơ chế locking của MySQL InnoDB. Record lock bảo vệ index record đang tồn tại. Gap lock bảo vệ khoảng trống để transaction khác không thể chèn khóa mới vào vùng đó. Next-key lock kết hợp record lock với gap lock phía trước record, giúp InnoDB bảo vệ phạm vi đọc và ngăn phantom insert trong những trường hợp cần thiết.

Ở REPEATABLE READ, next-key locking thường đóng vai trò quan trọng đối với locking read và thao tác ghi theo range. Ở READ COMMITTED, gap locking cho search thông thường giảm đi, nhưng vẫn có ngoại lệ liên quan đến foreign key và duplicate-key checking. Consistent read sử dụng MVCC có hành vi khác với locking read.

Khi điều tra blocking, hãy xác định index thực tế được quét, isolation level, loại lock và transaction đang giữ tài nguyên. Index phù hợp, transaction ngắn, unique constraint và UPDATE có điều kiện có thể giảm tranh chấp. Cần kiểm chứng bằng execution plan, Performance Schema và deadlock report thay vì suy luận chỉ từ câu SQL hoặc số dòng được trả về.
