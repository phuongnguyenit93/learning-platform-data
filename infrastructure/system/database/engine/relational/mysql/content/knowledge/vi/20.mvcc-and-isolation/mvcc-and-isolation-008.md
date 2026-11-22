# Dirty read, nonrepeatable read, phantom và write skew

Khi nhiều connection cùng đọc và ghi dữ liệu, kết quả mà mỗi transaction nhìn thấy phụ thuộc vào mức cô lập (*isolation level*) và cách storage engine thực hiện đọc. Một transaction có thể đọc thay đổi chưa commit của transaction khác, đọc lại cùng hàng nhưng nhận giá trị mới, thấy thêm hàng thỏa điều kiện tìm kiếm, hoặc cùng một transaction khác làm vi phạm một quy tắc nghiệp vụ dù mỗi transaction riêng lẻ đều đã kiểm tra điều kiện hợp lệ.

Bốn hiện tượng cần nhận biết là **dirty read**, **nonrepeatable read**, **phantom read** và **write skew**. MySQL InnoDB dùng MVCC (Multi-Version Concurrency Control) kết hợp với khóa để điều khiển khả năng nhìn thấy dữ liệu và bảo vệ thao tác ghi. Mức cô lập quyết định cách các read view được tạo, cách locking read hoạt động và loại xung đột nào được ngăn chặn.

Bài học này thuộc module `DATABASE_MYSQL`, tập trung vào thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi và vận hành cơ sở dữ liệu quan hệ. Mục tiêu là hiểu các anomaly bằng lịch chạy của hai transaction, biết mức cô lập mặc định của InnoDB và chọn cách bảo vệ phù hợp với invariant nghiệp vụ.

Sau bài học, bạn có thể:

- Định nghĩa dirty read, nonrepeatable read, phantom read và write skew.
- Phân biệt consistent read (đọc theo snapshot) với locking/current read.
- Giải thích cách MVCC tạo read view và cách InnoDB dùng undo version.
- So sánh bốn isolation level của MySQL.
- Dự đoán kết quả khi hai session xen kẽ SELECT, UPDATE, INSERT, COMMIT và ROLLBACK.
- Hiểu vì sao InnoDB REPEATABLE READ ngăn phantom trong consistent reads nhưng không đồng nghĩa với SERIALIZABLE.
- Nhận biết write skew và bảo vệ invariant nhiều hàng bằng khóa, constraint hoặc SERIALIZABLE.
- Chọn chiến lược xử lý deadlock, lock wait và retry transaction.

## 1. Bốn hiện tượng cần phân biệt

| Hiện tượng | Điều xảy ra | Ví dụ ngắn |
| --- | --- | --- |
| Dirty read | Đọc thay đổi chưa commit của transaction khác | A trừ tiền nhưng chưa commit; B đã đọc số dư mới; A rollback |
| Nonrepeatable read | Đọc cùng một hàng hai lần trong một transaction nhưng nhận giá trị khác | A đọc số dư 500; B cập nhật thành 400 và commit; A đọc lại thấy 400 |
| Phantom read | Chạy lại cùng predicate và thấy thêm/bớt hàng thỏa điều kiện | A tìm đơn từ 100 đến 200; B chèn đơn 150 và commit; A chạy lại thấy hàng mới |
| Write skew | Hai transaction đọc cùng trạng thái rồi cập nhật các hàng khác nhau, khiến invariant chung bị vi phạm | Hai bác sĩ đều thấy còn người trực khác; mỗi người tự tắt trạng thái trực của mình; cuối cùng không ai trực |

Ba hiện tượng đầu mô tả các kiểu thay đổi trong dữ liệu đọc. Write skew là anomaly ở cấp quy tắc nghiệp vụ nhiều hàng; nó có thể xảy ra dù không có hai transaction ghi đè cùng một hàng.

## 2. MVCC và hai cách đọc trong InnoDB

InnoDB dùng MVCC để cho phép consistent read đọc một phiên bản dữ liệu phù hợp với read view mà không phải khóa mọi hàng đang đọc. Khi một transaction cập nhật hàng, InnoDB tạo phiên bản mới và giữ thông tin undo cần thiết để có thể dựng lại phiên bản cũ cho các read view còn cần nó.

Hai kiểu đọc quan trọng:

### 2.1. Consistent read — đọc theo snapshot

Một câu `SELECT` thông thường, không có `FOR UPDATE` hoặc `FOR SHARE`, thường là consistent nonlocking read đối với bảng InnoDB.

- Ở `REPEATABLE READ`, các consistent reads trong cùng transaction dùng cùng read view được thiết lập ở lần consistent read đầu tiên. Có thể tạo read view ngay khi bắt đầu bằng `START TRANSACTION WITH CONSISTENT SNAPSHOT`.
- Ở `READ COMMITTED`, mỗi consistent read tạo read view mới tại thời điểm bắt đầu câu lệnh. Vì vậy, hai câu SELECT trong cùng transaction có thể nhìn thấy các commit khác nhau.
- Ở `READ UNCOMMITTED`, consistent read thông thường có thể đọc phiên bản chưa commit; không có snapshot ổn định theo cách của RR/RC.

Snapshot không phải bản sao vật lý toàn bộ bảng. InnoDB dùng phiên bản hiện tại và undo records để trả về giá trị phù hợp với read view.

### 2.2. Locking read — đọc hiện trạng và khóa hàng

Các câu lệnh như:

```sql
SELECT ... FOR UPDATE;
SELECT ... FOR SHARE;
```

là locking reads. Chúng đọc phiên bản mới nhất phù hợp với điều kiện và đặt khóa theo quy tắc isolation level, index và access path. Đây là current read, khác với consistent snapshot read.

- `FOR UPDATE` lấy khóa độc quyền cần thiết cho thao tác cập nhật tiếp theo.
- `FOR SHARE` lấy khóa chia sẻ, cho phép các transaction khác đọc/khóa chia sẻ nhưng ngăn cập nhật xung đột cho tới khi transaction kết thúc.
- Trong InnoDB `REPEATABLE READ`, locking range reads có thể dùng next-key locks (record lock kết hợp gap lock) để chặn insert vào khoảng đã khóa.

Một transaction ở RR có thể đọc snapshot cũ bằng SELECT thường, nhưng sau đó dùng `SELECT ... FOR UPDATE` và nhìn thấy phiên bản mới hơn. Đừng trộn hai kiểu đọc mà không hiểu sự khác biệt.

## 3. Bốn isolation level của MySQL

MySQL hỗ trợ bốn mức cô lập chuẩn. Với InnoDB, mức mặc định là `REPEATABLE READ`.

| Isolation level | Dirty read | Nonrepeatable read | Phantom trong consistent reads | Đặc điểm chính của InnoDB |
| --- | --- | --- | --- | --- |
| `READ UNCOMMITTED` | Có thể | Có thể | Có thể | SELECT có thể thấy dữ liệu chưa commit |
| `READ COMMITTED` | Không | Có thể | Có thể | Mỗi consistent SELECT có snapshot mới; gap locking phần lớn tắt |
| `REPEATABLE READ` | Không | Không trong consistent reads cùng transaction | Không trong consistent reads cùng snapshot | Mặc định InnoDB; locking range read dùng next-key locking |
| `SERIALIZABLE` | Không | Không | Không trong lịch chạy được tuần tự hóa | Tăng khóa và giảm concurrency; có thể phát sinh deadlock |

Bảng này mô tả hiện tượng theo cách đọc thông thường và cơ chế InnoDB. Locking reads, DML và các loại lock có quy tắc riêng. `REPEATABLE READ` của InnoDB có bảo vệ phantom mạnh hơn cách mô tả đơn giản của nhiều hệ thống khác, nhưng vẫn không đồng nghĩa mọi lịch chạy đều tương đương SERIALIZABLE; write skew là ví dụ quan trọng.

## 4. Tạo dữ liệu lab cho hai session

Chạy phần chuẩn bị một lần trước khi mở hai connection A và B. Dùng bảng lab riêng; không thử các thao tác này trên dữ liệu production.

```sql
DROP TABLE IF EXISTS mvcc_demo_orders;
DROP TABLE IF EXISTS mvcc_demo_accounts;

CREATE TABLE mvcc_demo_accounts (
    account_id INT UNSIGNED NOT NULL,
    balance DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE = InnoDB;

INSERT INTO mvcc_demo_accounts (account_id, balance) VALUES
(1, 500.00),
(2, 800.00);

CREATE TABLE mvcc_demo_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_mvcc_demo_orders_amount (amount)
) ENGINE = InnoDB;

INSERT INTO mvcc_demo_orders (order_id, amount) VALUES
(101, 90.00),
(102, 120.00),
(103, 180.00),
(104, 250.00);
```

Kiểm tra engine và dữ liệu:

```sql
SELECT TABLE_NAME, ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('mvcc_demo_accounts', 'mvcc_demo_orders');

SELECT * FROM mvcc_demo_accounts ORDER BY account_id;
SELECT * FROM mvcc_demo_orders ORDER BY order_id;
```

Đảm bảo cả hai bảng dùng InnoDB. Trong các phần tiếp theo, “Session A” và “Session B” là hai connection vật lý riêng biệt tới cùng schema. Không mở hai tab dùng chung một connection rồi coi đó là hai session.

## 5. Dirty read — đọc dữ liệu chưa commit

Dirty read xảy ra khi một transaction nhìn thấy thay đổi của transaction khác trước khi thay đổi đó được commit. Nếu transaction ghi rollback, dữ liệu mà transaction đọc trước đó chưa từng trở thành dữ liệu đã commit.

Trong InnoDB, dirty read có thể xảy ra ở `READ UNCOMMITTED`. Các mức `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE` ngăn consistent SELECT đọc thay đổi chưa commit.

### 5.1. Lịch chạy hai session

Đưa cả hai session về `READ UNCOMMITTED` trước khi bắt đầu transaction.

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;

UPDATE mvcc_demo_accounts
SET balance = 100.00
WHERE account_id = 1;

-- Chưa COMMIT hoặc ROLLBACK.
```

**Session B:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;

SELECT account_id, balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
```

Session B có thể đọc `balance = 100.00` dù Session A chưa commit. Đây là dirty read.

Tiếp tục ở **Session A**:

```sql
ROLLBACK;
```

Session A hủy thay đổi. Nếu Session B đọc lại trong khi vẫn ở `READ UNCOMMITTED`, nó có thể thấy giá trị đã rollback là 500.00. Điều B từng đọc là một giá trị tạm thời chưa được commit.

Kết thúc **Session B**:

```sql
COMMIT;
```

### 5.2. Vì sao dirty read nguy hiểm?

Ứng dụng có thể dùng dữ liệu chưa commit để quyết định cấp hàng, gửi thông báo, tính hạn mức hoặc ghi một kết quả sang hệ thống khác. Nếu transaction nguồn rollback, hành động bên ngoài đã dựa trên dữ liệu không tồn tại trong database.

Với dữ liệu nghiệp vụ thông thường, tránh `READ UNCOMMITTED`. Mức này hiếm khi phù hợp với báo cáo cần độ tin cậy.

## 6. Nonrepeatable read — cùng một hàng nhưng giá trị thay đổi

Nonrepeatable read xảy ra khi một transaction đọc một hàng, transaction khác cập nhật và commit hàng đó, rồi transaction đầu đọc lại cùng hàng và nhận giá trị mới.

### 6.1. Tái hiện ở READ COMMITTED

Đặt cả hai session ở `READ COMMITTED`.

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
-- Kết quả ban đầu: 500.00
```

**Session B:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

UPDATE mvcc_demo_accounts
SET balance = 400.00
WHERE account_id = 1;

COMMIT;
```

Quay lại **Session A**:

```sql
SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
-- Kết quả mới: 400.00

COMMIT;
```

Ở READ COMMITTED, mỗi consistent SELECT tạo read view mới. Câu SELECT thứ hai của A bắt đầu sau khi B commit nên nhìn thấy 400.00. Một hàng đã được đọc trước đó không được bảo đảm giữ nguyên giá trị trong suốt transaction.

### 6.2. Cùng lịch chạy ở REPEATABLE READ

Khôi phục số dư trước bài thử bằng một câu lệnh chạy ngoài transaction, rồi đặt A ở RR và B ở RC hoặc RR:

```sql
UPDATE mvcc_demo_accounts
SET balance = 500.00
WHERE account_id = 1;
```

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
-- Giả sử kết quả là 500.00; read view được thiết lập.
```

**Session B:**

```sql
START TRANSACTION;

UPDATE mvcc_demo_accounts
SET balance = 350.00
WHERE account_id = 1;

COMMIT;
```

Quay lại **Session A**:

```sql
SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
-- Consistent read vẫn trả 500.00 trong snapshot của A.

COMMIT;
```

Ở InnoDB RR, các consistent reads trong transaction dùng cùng read view. B đã commit giá trị 350.00, nhưng snapshot của A vẫn nhìn phiên bản 500.00.

## 7. Consistent read khác locking/current read

Một điểm rất quan trọng: RR không có nghĩa mọi loại SELECT trong transaction đều luôn trả cùng một phiên bản.

Trong cùng transaction A ở RR:

```sql
-- Consistent read: đọc theo snapshot
SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;

-- Locking read: đọc phiên bản mới nhất phù hợp và khóa hàng
SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1
FOR UPDATE;
```

Nếu transaction khác đã commit cập nhật sau khi read view của A được tạo, câu SELECT thường có thể tiếp tục trả phiên bản snapshot cũ, trong khi `FOR UPDATE` có thể trả phiên bản mới nhất. Locking read là current read, không phải consistent snapshot read.

Điều này cũng liên quan đến `UPDATE` và `DELETE`: chúng phải xác định hàng hiện hành và khóa hàng phù hợp, không chỉ sửa một phiên bản cũ trong snapshot. Khi một transaction vừa đọc snapshot vừa thực hiện locking reads/DML, kết quả quan sát có thể bao gồm các thời điểm logic khác nhau. Hãy thiết kế luồng đọc/ghi rõ ràng, đặc biệt khi quyết định cập nhật dựa trên một điều kiện vừa được đọc.

Nếu muốn khóa hàng trước khi quyết định cập nhật:

```sql
START TRANSACTION;

SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1
FOR UPDATE;

-- Kiểm tra điều kiện trên giá trị vừa khóa, sau đó UPDATE.
UPDATE mvcc_demo_accounts
SET balance = balance - 50.00
WHERE account_id = 1
  AND balance >= 50.00;

COMMIT;
```

Khóa hàng giúp tránh transaction khác cập nhật cùng hàng trong khoảng thời gian quyết định và ghi. Vẫn phải kiểm tra update count và xử lý deadlock/timeout.

## 8. Phantom read — xuất hiện hàng mới thỏa predicate

Phantom read không phải là cùng một hàng đổi giá trị. Nó xảy ra khi một transaction chạy lại truy vấn theo một điều kiện tập hợp và thấy tập hàng thỏa điều kiện đã thay đổi, ví dụ một hàng mới được insert hoặc một hàng cũ được cập nhật để bắt đầu thỏa predicate.

### 8.1. Tái hiện phantom ở READ COMMITTED

Nếu chạy lại bài thực hành, xóa hàng được thêm từ lần trước trước khi mở transaction:

```sql
DELETE FROM mvcc_demo_orders
WHERE order_id = 105;
```

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT order_id, amount
FROM mvcc_demo_orders
WHERE amount BETWEEN 100.00 AND 200.00
ORDER BY amount, order_id;
-- Ban đầu: order 102 và 103.
```

**Session B:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

INSERT INTO mvcc_demo_orders (order_id, amount)
VALUES (105, 150.00);

COMMIT;
```

Quay lại **Session A**:

```sql
SELECT order_id, amount
FROM mvcc_demo_orders
WHERE amount BETWEEN 100.00 AND 200.00
ORDER BY amount, order_id;
-- Lần này có thêm order 105.

COMMIT;
```

Ở RC, câu SELECT thứ hai tạo read view mới nên thấy hàng 105 đã commit. Đây là phantom row đối với predicate `amount BETWEEN 100 AND 200`.

### 8.2. Consistent reads ở REPEATABLE READ

Ở InnoDB RR, nếu A dùng hai SELECT thông thường trong cùng transaction và read view đã được tạo ở câu đầu, câu thứ hai vẫn dùng snapshot đó. Hàng 105 được B commit sau thời điểm snapshot sẽ không xuất hiện trong consistent read thứ hai. Vì vậy, InnoDB RR ngăn phantom trong chuỗi consistent reads cùng read view.

Điều này không có nghĩa mọi thao tác trên khoảng đó đều không thể bị insert. Locking read và DML có quy tắc current read và khóa riêng.

### 8.3. Next-key locks bảo vệ locking range read

Ở InnoDB RR, một locking read theo khoảng có thể lấy next-key locks trên index. Next-key lock kết hợp khóa record với khóa gap trước record, ngăn transaction khác insert giá trị vào khoảng đang được bảo vệ.

Ví dụ trên **Session A**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT order_id, amount
FROM mvcc_demo_orders
WHERE amount BETWEEN 100.00 AND 200.00
FOR UPDATE;
```

Với index `idx_mvcc_demo_orders_amount`, InnoDB có thể khóa các index records và khoảng cần thiết cho điều kiện. Nếu **Session B** cố insert một hàng có `amount = 150.00`, câu INSERT có thể phải chờ A kết thúc transaction.

Sau khi A chạy:

```sql
COMMIT;
```

B mới có thể tiếp tục insert nếu không còn xung đột khác.

Phạm vi lock thực tế phụ thuộc index được chọn, predicate, access path và isolation level. Dùng `EXPLAIN` để hiểu đường truy cập; không giả định một truy vấn range luôn chỉ khóa đúng các hàng hiển thị.

Ở READ COMMITTED, InnoDB phần lớn tắt gap locking cho search/index scan thông thường (ngoại lệ gồm kiểm tra foreign key và duplicate-key). Do đó, locking reads ở RC thường không ngăn phantom insert theo cách RR next-key locking làm được.

## 9. Write skew — hai transaction ghi các hàng khác nhau nhưng phá invariant chung

Write skew là anomaly khó phát hiện hơn ba hiện tượng đọc cổ điển. Hai transaction cùng đọc một trạng thái nhất quán, mỗi transaction quyết định cập nhật một hàng riêng, và các hàng được cập nhật không xung đột trực tiếp. Cả hai có thể commit nhưng trạng thái tổng thể vi phạm quy tắc nghiệp vụ.

Ví dụ: một nhóm có hai bác sĩ đang trực. Quy tắc là luôn phải có ít nhất một bác sĩ trực. Mỗi transaction muốn cho một bác sĩ nghỉ trực và chỉ thực hiện nếu thấy còn ít nhất hai người trực.

Tạo bảng lab:

```sql
DROP TABLE IF EXISTS mvcc_demo_doctors;

CREATE TABLE mvcc_demo_doctors (
    doctor_id INT UNSIGNED NOT NULL,
    doctor_name VARCHAR(100) NOT NULL,
    on_call TINYINT(1) NOT NULL,
    PRIMARY KEY (doctor_id),
    KEY idx_mvcc_demo_doctors_on_call (on_call)
) ENGINE = InnoDB;

INSERT INTO mvcc_demo_doctors (doctor_id, doctor_name, on_call) VALUES
(1, 'An', 1),
(2, 'Binh', 1);
```

### 9.1. Lịch chạy gây write skew ở REPEATABLE READ

Đặt cả A và B ở RR.

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT COUNT(*) AS doctors_on_call
FROM mvcc_demo_doctors
WHERE on_call = 1;
-- Kết quả: 2. A quyết định doctor 1 có thể nghỉ.
```

**Session B:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT COUNT(*) AS doctors_on_call
FROM mvcc_demo_doctors
WHERE on_call = 1;
-- Cũng thấy 2 trong snapshot của B.
```

Sau đó A cập nhật hàng 1:

```sql
UPDATE mvcc_demo_doctors
SET on_call = 0
WHERE doctor_id = 1;

COMMIT;
```

B cập nhật hàng 2:

```sql
UPDATE mvcc_demo_doctors
SET on_call = 0
WHERE doctor_id = 2;

COMMIT;
```

Hai transaction ghi hai primary key khác nhau nên không nhất thiết phải chờ nhau. Cả hai có thể commit. Kết quả cuối:

```sql
SELECT doctor_id, doctor_name, on_call
FROM mvcc_demo_doctors
ORDER BY doctor_id;
```

| doctor_id | doctor_name | on_call |
| ---: | --- | ---: |
| 1 | An | 0 |
| 2 | Binh | 0 |

Invariant “luôn có ít nhất một bác sĩ trực” đã bị vi phạm. Không có dirty read; cả hai transaction đều đọc dữ liệu đã commit trong snapshot của mình. Không có nonrepeatable read trong các consistent reads; mỗi transaction chỉ đọc một lần. Vấn đề là hai quyết định độc lập dựa trên cùng một điều kiện tổng hợp nhưng ghi các hàng khác nhau.

### 9.2. Vì sao REPEATABLE READ không tự ngăn write skew?

RR bảo đảm consistent reads trong một transaction dùng cùng snapshot. Nó không tự khóa tất cả các hàng hoặc predicate mà ứng dụng đã đọc. Một câu `SELECT COUNT(*)` thông thường không khóa các bác sĩ đang trực để giữ invariant cho tới khi transaction kết thúc.

Khi A và B cập nhật các hàng khác nhau, InnoDB có thể cho cả hai tiếp tục vì không có xung đột ghi trên cùng record. MVCC cải thiện concurrency, nhưng snapshot repeatability không đồng nghĩa với tuần tự hóa mọi quyết định nghiệp vụ.

## 10. Cách ngăn write skew

Chọn cách bảo vệ dựa trên invariant. Nếu quy tắc có thể biểu diễn bằng constraint ở cấp hàng hoặc unique key, ưu tiên constraint. Với invariant cần xem nhiều hàng, phải tạo điểm đồng bộ mà các transaction cùng tranh chấp.

### 10.1. Khóa các hàng liên quan bằng SELECT FOR UPDATE

Trước khi quyết định cho một bác sĩ nghỉ, khóa các hàng hiện đang trực:

```sql
START TRANSACTION;

SELECT doctor_id
FROM mvcc_demo_doctors
WHERE on_call = 1
FOR UPDATE;

-- Ứng dụng đếm các hàng trả về.
-- Chỉ cập nhật một bác sĩ nếu sau thao tác vẫn còn ít nhất một người trực.

UPDATE mvcc_demo_doctors
SET on_call = 0
WHERE doctor_id = 1
  AND on_call = 1;

COMMIT;
```

Nếu hai transaction cùng khóa tập bác sĩ đang trực, một transaction phải chờ. Sau khi lấy được khóa, transaction cần đánh giá lại điều kiện bằng locking/current read và dữ liệu hiện hành. Không dựa vào một snapshot cũ được tạo trước lúc chờ khóa.

Kết quả và phạm vi khóa phụ thuộc index và predicate. Cần kiểm tra `EXPLAIN` và kiểm thử lịch chạy đồng thời thực tế.

### 10.2. Dùng guard row để tuần tự hóa quyết định

Một cách dễ kiểm soát là tạo một hàng guard cho mỗi nhóm trực. Mọi transaction thay đổi lịch trực phải khóa cùng hàng guard trước khi kiểm tra và cập nhật.

```sql
DROP TABLE IF EXISTS mvcc_demo_schedule_guard;

CREATE TABLE mvcc_demo_schedule_guard (
    team_id INT UNSIGNED NOT NULL,
    guard_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (team_id)
) ENGINE = InnoDB;

INSERT INTO mvcc_demo_schedule_guard (team_id) VALUES (1);
```

Mẫu transaction:

```sql
START TRANSACTION;

SELECT team_id
FROM mvcc_demo_schedule_guard
WHERE team_id = 1
FOR UPDATE;

-- Sau khi đã giữ guard lock, dùng current read để kiểm tra trạng thái hiện tại.
SELECT doctor_id
FROM mvcc_demo_doctors
WHERE on_call = 1
FOR UPDATE;

-- Ứng dụng kiểm tra số người trực và chỉ cập nhật nếu invariant vẫn đúng.
-- Ví dụ cập nhật một doctor cụ thể sau khi đã kiểm tra.

COMMIT;
```

Guard row biến các quyết định trên cùng team thành chuỗi tuần tự. Mọi code path có thể thay đổi invariant phải tuân thủ cùng giao thức; một đường ghi bỏ qua guard vẫn có thể phá quy tắc.

Điểm quan trọng: sau khi chờ guard lock, dùng locking/current read để kiểm tra dữ liệu hiện tại. Nếu transaction đã tạo một RR snapshot cũ trước khi chờ, một SELECT thường tiếp theo vẫn có thể đọc snapshot cũ.

### 10.3. Dùng SERIALIZABLE khi phù hợp

`SERIALIZABLE` yêu cầu lịch chạy tương đương một thứ tự tuần tự. Với InnoDB, mức này tăng locking; trong transaction tường minh, các SELECT thông thường được xử lý như shared locking reads theo quy tắc của MySQL. Điều này có thể ngăn write skew nhưng làm giảm concurrency và tăng khả năng deadlock/lock wait.

Chỉ dùng SERIALIZABLE cho transaction hoặc workload thực sự cần bảo đảm mạnh hơn, sau khi đo contention. Dù dùng mức này, ứng dụng vẫn phải xử lý deadlock và retry transaction đúng cách.

## 11. Đặt isolation level trong MySQL

Kiểm tra isolation level hiện tại:

```sql
SELECT
    @@session.transaction_isolation AS session_isolation,
    @@global.transaction_isolation AS global_isolation;
```

Đặt cho transaction kế tiếp trên connection hiện tại:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;
-- Các thao tác thuộc transaction này.
COMMIT;
```

Đặt mặc định cho các transaction tiếp theo trong session:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

Đặt mặc định cho connection mới:

```sql
SET GLOBAL TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

`SET GLOBAL` cần quyền quản trị phù hợp và không thay đổi isolation level của các session đang tồn tại. Hãy đặt isolation level trước khi bắt đầu transaction; không coi nó là một tùy chọn có thể đổi giữa transaction đang mở.

Với MySQL 8.x, tên biến hệ thống là `transaction_isolation`. Một số phiên bản cũ từng dùng tên `tx_isolation`; hãy kiểm tra phiên bản triển khai trước khi dùng script cấu hình tương thích nhiều phiên bản.

### 11.1. Tạo snapshot ngay khi bắt đầu

Ở RR, có thể yêu cầu tạo consistent snapshot ngay tại thời điểm bắt đầu:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;
```

Nếu không dùng `WITH CONSISTENT SNAPSHOT`, read view cho consistent reads ở RR thường được thiết lập khi transaction thực hiện consistent read đầu tiên. Cú pháp snapshot hữu ích khi muốn xác định rõ thời điểm bắt đầu snapshot cho một transaction đọc dài.

`WITH CONSISTENT SNAPSHOT` không biến locking reads thành snapshot reads; `FOR UPDATE` và `FOR SHARE` vẫn là locking/current reads. Tùy chọn này có ý nghĩa với InnoDB ở REPEATABLE READ; ở isolation level khác nó không tạo cùng bảo đảm snapshot.

## 12. Đọc bảng so sánh theo tình huống

| Mức cô lập | Cách consistent SELECT nhìn dữ liệu | Khi phù hợp |
| --- | --- | --- |
| READ UNCOMMITTED | Có thể đọc phiên bản chưa commit | Hiếm khi phù hợp với nghiệp vụ cần độ tin cậy |
| READ COMMITTED | Mỗi câu SELECT lấy snapshot mới | Báo cáo/ứng dụng chấp nhận dữ liệu thay đổi giữa các câu đọc |
| REPEATABLE READ | Các consistent SELECT dùng cùng snapshot trong transaction | Mặc định InnoDB; đọc nhất quán nhiều lần |
| SERIALIZABLE | Tăng khóa để lịch chạy tương đương tuần tự | Invariant phức tạp cần bảo đảm mạnh và chấp nhận giảm concurrency |

Không có isolation level nào thay thế hoàn toàn thiết kế dữ liệu và constraint. Hãy xác định anomaly nào có thể làm hỏng nghiệp vụ rồi chọn cơ chế cụ thể.

## 13. Deadlock, lock wait và retry

Khóa giúp ngăn xung đột nhưng có thể tạo deadlock. Ví dụ A khóa hàng 1 rồi chờ hàng 2; B khóa hàng 2 rồi chờ hàng 1. InnoDB phát hiện chu trình chờ và rollback một transaction làm nạn nhân.

Nguyên tắc xử lý:

- Giữ transaction ngắn và khóa ít hàng nhất có thể.
- Cập nhật nhiều hàng theo cùng một thứ tự khóa trong mọi code path.
- Tạo index phù hợp để tránh scan và khóa quá nhiều record/gap.
- Bắt lỗi deadlock và retry toàn bộ transaction với số lần giới hạn, có backoff.
- Với lock wait timeout, không giả định toàn transaction đã rollback; chủ động rollback nếu nghiệp vụ không thể tiếp tục.
- Bảo đảm thao tác có thể retry là idempotent hoặc có cơ chế chống thực hiện hai lần.

Có thể xem deadlock gần đây bằng:

```sql
SHOW ENGINE INNODB STATUS;
```

Phần `LATEST DETECTED DEADLOCK` thường chứa thông tin về transaction, statement và lock liên quan. Trong môi trường có nhiều deadlock, cần thu thập log và quan sát tần suất thay vì chỉ tăng timeout.

## 14. Kiểm tra access path và index

Isolation level không chỉ ảnh hưởng dữ liệu nhìn thấy; nó còn ảnh hưởng loại lock được lấy và phạm vi lock. Index có thể thu hẹp phạm vi record/gap cần kiểm tra.

Ví dụ truy vấn range:

```sql
EXPLAIN
SELECT order_id, amount
FROM mvcc_demo_orders
WHERE amount BETWEEN 100.00 AND 200.00
FOR UPDATE;
```

Kiểm tra:

- Index `idx_mvcc_demo_orders_amount` có được chọn không.
- Access type và số hàng ước lượng.
- Predicate có dùng range scan hay phải quét rộng.
- Isolation level đang áp dụng cho session.
- Loại lock và khoảng index có thể bị khóa theo access path.

`EXPLAIN` cho biết kế hoạch truy cập, không liệt kê đầy đủ mọi lock runtime. Để điều tra lock đang chờ, có thể xem `performance_schema.data_locks`, `performance_schema.data_lock_waits` và các bảng metadata liên quan nếu được bật/quyền truy cập cho phép.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng READ UNCOMMITTED cho dữ liệu nghiệp vụ | Đọc dữ liệu có thể rollback | Dùng RC/RR phù hợp |
| Nghĩ READ COMMITTED giữ cùng snapshot suốt transaction | Đọc lại có thể thấy commit mới | Chọn RR nếu cần snapshot lặp lại |
| Nghĩ RR khiến mọi loại SELECT trả cùng phiên bản | Locking read có thể thấy phiên bản mới | Phân biệt consistent read và current read |
| Nghĩ RR ngăn mọi phantom trong mọi thao tác | Locking read/DML có quy tắc khóa khác | Hiểu snapshot read, next-key lock và access path |
| Nghĩ RR đồng nghĩa SERIALIZABLE | Write skew vẫn có thể xảy ra | Bảo vệ invariant bằng khóa, guard row, constraint hoặc SERIALIZABLE |
| Dùng SELECT COUNT(*) rồi update hàng khác mà không khóa | Hai transaction có thể cùng vượt qua điều kiện | Tạo điểm đồng bộ và kiểm tra lại bằng current read |
| Dùng FOR UPDATE nhưng không có index phù hợp | Có thể khóa phạm vi rộng và giảm concurrency | Thiết kế index, kiểm tra EXPLAIN |
| Retry chỉ statement gây deadlock | Transaction có thể không còn trạng thái nhất quán | Retry toàn bộ transaction đã rollback |
| Cho rằng lock timeout luôn rollback toàn transaction | Các thay đổi trước đó có thể vẫn còn trong transaction | Chủ động rollback khi nghiệp vụ thất bại |

## 16. Bài tập thực hành

1. Dùng hai session tái hiện dirty read ở `READ UNCOMMITTED`. Rollback Session A và quan sát giá trị mà B đã đọc.
2. Tái hiện nonrepeatable read ở `READ COMMITTED`: A đọc một hàng hai lần, B cập nhật và commit ở giữa.
3. Lặp lại bài 2 ở `REPEATABLE READ` bằng consistent SELECT và giải thích vì sao kết quả giữ nguyên.
4. Trong transaction RR, so sánh SELECT thường với `SELECT ... FOR UPDATE` sau khi session khác đã commit cập nhật.
5. Tái hiện phantom ở `READ COMMITTED` bằng predicate `amount BETWEEN 100 AND 200` và một INSERT từ session khác.
6. Lặp lại với consistent SELECT ở RR. Sau đó thử locking range read `FOR UPDATE` và quan sát INSERT bị chặn bởi next-key lock.
7. Tái hiện write skew với hai bác sĩ trực. Xác nhận cả hai transaction có thể commit nhưng invariant bị phá.
8. Sửa write skew bằng cách khóa các hàng liên quan hoặc dùng guard row; bảo đảm kiểm tra lại bằng current read sau khi lấy khóa.
9. Thử cùng bài toán ở `SERIALIZABLE`, ghi nhận lock wait/deadlock và giải thích trade-off concurrency.
10. Chạy `EXPLAIN` cho locking range read trước và sau khi thêm index phù hợp. Quan sát tác động tới access path.
11. Tạo một lịch chạy deadlock bằng hai session khóa hai hàng theo thứ tự ngược nhau. Đọc `SHOW ENGINE INNODB STATUS` và thiết kế retry.

## 17. Checklist trước khi chọn isolation level

- [ ] Đã xác định dữ liệu nào không được phép đọc trước commit.
- [ ] Đã xác định một transaction có cần đọc lại cùng hàng với cùng giá trị hay không.
- [ ] Đã xác định predicate có cần ổn định tập hàng trong suốt transaction hay không.
- [ ] Đã rà soát invariant nghiệp vụ liên quan nhiều hàng, không chỉ từng hàng riêng lẻ.
- [ ] Đã phân biệt consistent snapshot read và locking/current read.
- [ ] Đã chọn isolation level dựa trên anomaly thực sự cần ngăn.
- [ ] Nếu dùng `FOR UPDATE`/`FOR SHARE`, đã kiểm tra index và phạm vi lock.
- [ ] Nếu dùng guard row hoặc khóa tập hàng, mọi code path cập nhật invariant đều tuân thủ cùng giao thức.
- [ ] Đã có xử lý deadlock, lock timeout và retry toàn transaction.
- [ ] Đã kiểm tra tác động tới concurrency, latency và lock contention bằng workload đại diện.
- [ ] Đã xác định cách xử lý request lặp hoặc kết quả commit không rõ do mất kết nối.

## 18. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể tái hiện và giải thích dirty read, nonrepeatable read, phantom read và write skew bằng hai session; phân biệt snapshot read với locking/current read; giải thích hành vi của bốn isolation level trong InnoDB; biết vì sao RR ngăn phantom trong consistent snapshot nhưng vẫn có thể cho write skew; và triển khai được cách bảo vệ invariant bằng `FOR UPDATE`, guard row hoặc SERIALIZABLE với xử lý deadlock/retry phù hợp.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — InnoDB Transaction Isolation Levels](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html)
- [MySQL 8.4 Reference Manual — Consistent Nonlocking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html)
- [MySQL 8.4 Reference Manual — Locking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html)
- [MySQL 8.4 Reference Manual — InnoDB Multi-Versioning](https://dev.mysql.com/doc/refman/8.4/en/innodb-multi-versioning.html)
- [MySQL 8.4 Reference Manual — InnoDB Locking](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html)
