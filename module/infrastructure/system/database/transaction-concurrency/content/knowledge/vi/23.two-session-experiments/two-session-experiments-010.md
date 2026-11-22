# Kiểm chứng khóa trên hàng chưa tồn tại và điều kiện khoảng

Khi một transaction truy vấn một hàng chưa tồn tại, nhiều người cho rằng `SELECT ... FOR UPDATE` sẽ khóa vị trí mà hàng đó đáng lẽ phải nằm. Giả định này không đúng với mọi hệ quản trị cơ sở dữ liệu. Một row lock thường khóa hàng đã được tìm thấy; nếu kết quả truy vấn rỗng, không có hàng nào để khóa. Một số engine có thêm cơ chế khóa khoảng chỉ mục (gap lock), next-key lock hoặc key-range lock để ngăn transaction khác chèn hàng mới thỏa điều kiện. Cơ chế đó phụ thuộc DBMS, isolation level, index và execution plan.

Bài thực hành này dùng hai phiên database độc lập để kiểm chứng điều gì xảy ra khi một transaction đọc một khóa chưa tồn tại hoặc một khoảng chưa có hàng, trong lúc transaction khác cố chèn dữ liệu vào đó. Mục tiêu là quan sát trực tiếp ba kết quả khác nhau: thao tác chèn được phép tiếp tục, thao tác chèn phải chờ khóa khoảng, hoặc một transaction bị hủy do phát hiện xung đột Serializable.

Điểm cần giữ xuyên suốt các thí nghiệm: **khóa hàng hiện có, khóa khoảng chỉ mục và theo dõi predicate là những cơ chế khác nhau**. Không thể suy ra một cơ chế từ tên `FOR UPDATE` hoặc từ kết quả truy vấn rỗng.

## 1. Phân biệt hàng chưa tồn tại và khoảng dữ liệu

Giả sử bảng có khóa chính `id` với hai hàng:

| id | note |
|---:|---|
| 10 | mốc dưới |
| 20 | mốc trên |

Không có hàng mang `id = 15`. Cũng không có hàng nào trong khoảng mở `(10, 20)`.

Truy vấn tìm một khóa chính xác:

```sql
SELECT *
FROM range_lock_lab
WHERE id = 15
FOR UPDATE;
```

Truy vấn tìm một khoảng:

```sql
SELECT *
FROM range_lock_lab
WHERE id > 10
  AND id < 20
FOR UPDATE;
```

Cả hai đều có thể trả về 0 hàng. Nhưng chúng diễn đạt hai điều kiện khác nhau:

- Equality lookup hỏi liệu một khóa cụ thể có hàng hay không.
- Range lookup hỏi liệu có hàng nào trong một miền khóa hay không.

Nếu transaction chỉ khóa các hàng được trả về, kết quả rỗng đồng nghĩa không có row lock nào được lấy từ truy vấn đó. Nếu engine bảo vệ khoảng chỉ mục, nó có thể khóa khoảng chứa vị trí chèn `id = 15` dù hiện tại không có hàng mang ID đó.

### 1.1. Row lock

Row lock bảo vệ một hàng đã tồn tại. Nếu T1 khóa hàng `id = 10` bằng locking read, T2 muốn cập nhật hoặc xóa hàng đó có thể phải chờ cho đến khi T1 kết thúc.

```text
T1: khóa hàng id = 10
T2: UPDATE hàng id = 10 -> chờ
T1: COMMIT -> nhả khóa
T2: tiếp tục
```

Row lock không tự động có nghĩa là DBMS đã khóa mọi khóa có thể được chèn vào gần hàng đó.

### 1.2. Gap lock và next-key lock

Gap lock bảo vệ khoảng trống giữa các khóa chỉ mục để ngăn một số thao tác insert vào khoảng đó. InnoDB của MySQL có thể sử dụng gap lock cho các locking read và thao tác ghi phù hợp.

Next-key lock kết hợp khóa trên một index record với gap đứng ngay trước record đó. Nhờ vậy, engine có thể bảo vệ cả hàng hiện có lẫn khoảng giữa các giá trị chỉ mục.

```text
Index B-tree theo id:

... | 10 | -------- khoảng trống -------- | 20 | ...
                         ^
                    id = 15 có thể được chèn
```

### 1.3. Key-range lock

SQL Server dùng key-range lock ở isolation level `SERIALIZABLE` để bảo vệ phạm vi khóa chỉ mục được truy vấn. Một transaction khác muốn chèn khóa mới vào range đang được bảo vệ có thể phải chờ.

### 1.4. Predicate lock trong PostgreSQL Serializable

PostgreSQL dùng Serializable Snapshot Isolation (SSI). Các lần đọc có thể tạo SIREAD predicate lock để ghi nhận vùng dữ liệu đã đọc. Đây không phải khóa chặn thông thường như gap lock: thao tác insert không nhất thiết phải chờ; PostgreSQL theo dõi phụ thuộc đọc/ghi và có thể hủy một transaction nếu lịch có nguy cơ không tuần tự hóa.

Các cơ chế trên cùng hướng đến việc bảo vệ một điều kiện truy vấn trước thay đổi đồng thời, nhưng cách chúng hoạt động và kết quả quan sát được khác nhau.

## 2. Chuẩn bị môi trường thí nghiệm

Mỗi thí nghiệm cần hai phiên kết nối độc lập, gọi là **Session A** và **Session B**. Không chạy cả hai luồng trong cùng một connection hoặc cùng một ORM session vì khi đó không tạo được hai transaction cạnh tranh thật sự.

Tạo bảng kiểm thử và hai hàng biên. Cú pháp dưới đây gần với PostgreSQL và MySQL:

```sql
CREATE TABLE range_lock_lab (
    id   integer PRIMARY KEY,
    note varchar(100)
);

INSERT INTO range_lock_lab(id, note)
VALUES (10, 'lower boundary'),
       (20, 'upper boundary');
```

Trước mỗi lượt thử, xác nhận dữ liệu:

```sql
SELECT id, note
FROM range_lock_lab
ORDER BY id;
```

Kết quả ban đầu phải có `id = 10` và `id = 20`, không có `id = 15`.

### 2.1. Quy tắc phối hợp hai phiên

1. Mở Session A và Session B bằng hai connection riêng.
2. Chạy lệnh của Session A trước, giữ transaction mở ở đúng vị trí được chỉ dẫn.
3. Chạy lệnh của Session B trong khi A vẫn chưa commit hoặc rollback.
4. Quan sát B hoàn tất ngay, bị block hay nhận lỗi timeout.
5. Quay lại A và commit/rollback theo hướng dẫn.
6. Kiểm tra dữ liệu cuối cùng, rồi dọn bảng trước lượt tiếp theo.

Không để một transaction treo ngoài ý muốn. Một query đang chờ có thể giữ connection và lock, làm ảnh hưởng các lượt thử khác. Nếu cần dừng thí nghiệm, hủy query ở đúng phiên rồi rollback transaction.

### 2.2. Vì sao phải có hàng biên 10 và 20?

Hai hàng biên giúp engine có các index key bao quanh vị trí `15`. Với InnoDB và SQL Server, điều này làm rõ khoảng chỉ mục cần bảo vệ và giúp đọc lock diagnostics dễ hơn. Kết quả vẫn phụ thuộc index được dùng và kế hoạch truy vấn; vì vậy phải xác nhận execution plan thay vì chỉ dựa vào câu SQL.

## 3. Thí nghiệm 1: khóa một hàng đang tồn tại

Đây là thí nghiệm đối chứng để xác nhận hai session thật sự dùng cùng bảng và row lock hoạt động.

### Session A

```sql
BEGIN;

SELECT id, note
FROM range_lock_lab
WHERE id = 10
FOR UPDATE;

-- Giữ transaction mở, chưa COMMIT.
```

### Session B

```sql
BEGIN;

UPDATE range_lock_lab
SET note = 'updated by B'
WHERE id = 10;

-- Quan sát: thường phải chờ khóa do A giữ.
```

### Kết thúc

Quay lại Session A:

```sql
COMMIT;
```

Session B có thể tiếp tục. Sau đó commit B:

```sql
COMMIT;
```

Kết quả mong đợi là B bị chặn khi muốn sửa đúng hàng mà A đã khóa. Thí nghiệm này xác nhận row lock trên hàng tồn tại; nó chưa nói gì về việc khóa một hàng chưa tồn tại.

## 4. Thí nghiệm 2: PostgreSQL không khóa hàng chưa tồn tại bằng FOR UPDATE

PostgreSQL `SELECT ... FOR UPDATE` khóa các hàng được truy vấn tìm thấy. Nó không tạo gap lock tổng quát cho một khóa chưa tồn tại. Khi truy vấn trả 0 hàng, không có row lock nào được lấy từ kết quả đó để ngăn một insert mới.

Đặt lại dữ liệu trong một phiên không có transaction đang mở:

```sql
DELETE FROM range_lock_lab WHERE id = 15;
```

### Session A — Read Committed

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT id, note
FROM range_lock_lab
WHERE id = 15
FOR UPDATE;

-- Kết quả rỗng. Giữ transaction mở.
```

### Session B

```sql
BEGIN;

INSERT INTO range_lock_lab(id, note)
VALUES (15, 'inserted by B');

COMMIT;
```

Trong PostgreSQL, insert của B không phải chờ một row lock trên `id = 15` do A giữ, vì A không tìm thấy hàng đó. B có thể commit.

Quay lại A và chạy một statement mới:

```sql
SELECT id, note
FROM range_lock_lab
WHERE id = 15
FOR UPDATE;
```

Ở Read Committed, statement mới thường thấy hàng mà B đã commit trước khi statement bắt đầu. Sau đó:

```sql
COMMIT;
```

**Quan sát:** `FOR UPDATE` bảo vệ hàng tồn tại được tìm thấy; nó không khóa trước một hàng tương lai có cùng khóa chính.

### 4.1. Kiểm tra điều kiện khoảng trên PostgreSQL

Xóa `id = 15`, sau đó ở Session A:

```sql
BEGIN;

SELECT id
FROM range_lock_lab
WHERE id > 10
  AND id < 20
FOR UPDATE;

-- Không có hàng nào trong khoảng. Giữ transaction mở.
```

Session B:

```sql
BEGIN;

INSERT INTO range_lock_lab(id, note)
VALUES (15, 'inside the range');

COMMIT;
```

Insert có thể hoàn tất mà không phải chờ một gap lock do truy vấn A tạo ra. PostgreSQL không dùng gap lock kiểu InnoDB cho `SELECT FOR UPDATE` thông thường.

Điều đó không có nghĩa PostgreSQL không thể bảo vệ predicate. Nếu transaction cần semantics Serializable, dùng isolation level `SERIALIZABLE`; SSI theo dõi các phụ thuộc đọc/ghi và có thể abort một transaction khi có cấu trúc xung đột nguy hiểm.

## 5. Thí nghiệm 3: PostgreSQL Repeatable Read giữ snapshot nhưng không chặn insert

Thí nghiệm này phân biệt **không nhìn thấy hàng mới** với **ngăn hàng mới được chèn**. Hai điều đó không giống nhau.

Xóa `id = 15` trước khi bắt đầu.

### Session A

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT id
FROM range_lock_lab
WHERE id > 10
  AND id < 20;

-- Kết quả rỗng; snapshot của A được xác lập.
```

### Session B

```sql
BEGIN;

INSERT INTO range_lock_lab(id, note)
VALUES (15, 'inserted while A is open');

COMMIT;
```

Insert của B có thể commit vì truy vấn đọc thông thường của A không giữ gap lock. Quay lại A:

```sql
SELECT id
FROM range_lock_lab
WHERE id > 10
  AND id < 20;
```

Trong PostgreSQL Repeatable Read, A vẫn dùng snapshot transaction đã tạo trước khi B commit, nên lần đọc tiếp theo có thể vẫn trả kết quả rỗng. A không nhìn thấy hàng mới trong snapshot của mình, nhưng B vẫn đã chèn hàng đó thành công.

```text
Session A (Repeatable Read)       Session B
--------------------------------  ------------------------------
BEGIN; lấy snapshot S1
SELECT range -> rỗng
                                  INSERT id=15
                                  COMMIT
SELECT range trong S1 -> rỗng
COMMIT

Transaction mới của A:
SELECT range -> thấy id=15
```

Đây là ví dụ quan trọng: snapshot ổn định có thể che thay đổi mới khỏi transaction đang mở mà không khóa transaction chèn. Đừng kết luận rằng “A không thấy phantom nên A đã ngăn phantom bằng lock”.

## 6. PostgreSQL Serializable: theo dõi predicate, không chặn insert bằng gap lock

PostgreSQL Serializable sử dụng SSI. Một truy vấn đọc predicate có thể tạo SIREAD lock để ghi nhận vùng đã đọc. SIREAD không hoạt động như row/gap lock chặn thông thường; transaction ghi vào vùng đó có thể vẫn tiếp tục. PostgreSQL kiểm tra các phụ thuộc và hủy transaction nếu lịch có thể tạo kết quả không Serializable.

Một cặp thao tác đơn giản chỉ có một reader và một inserter đôi khi vẫn có thể được sắp xếp tuần tự hợp lệ: reader được xem như chạy trước inserter. Vì thế, không nên kỳ vọng mọi insert vào predicate đang được đọc đều tự động bị chặn hoặc luôn gây lỗi.

Để tạo tình huống xung đột rõ hơn, hai session cùng đọc một predicate rỗng rồi mỗi session chèn một hàng khác nhau thỏa predicate đó. Đây là mẫu có thể tạo hai phụ thuộc đọc-ghi ngược chiều.

Xóa `id = 15` và `id = 16` trước lượt thử.

### Session A

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT count(*)
FROM range_lock_lab
WHERE id > 10
  AND id < 20;

-- Kết quả 0. Chưa commit.
```

### Session B

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT count(*)
FROM range_lock_lab
WHERE id > 10
  AND id < 20;

-- Cũng thấy 0. Chưa commit.
```

### Tiếp tục A rồi B

Session A:

```sql
INSERT INTO range_lock_lab(id, note)
VALUES (15, 'inserted by A');

COMMIT;
```

Session B:

```sql
INSERT INTO range_lock_lab(id, note)
VALUES (16, 'inserted by B');

COMMIT;
```

Vì cả hai transaction đã đọc cùng predicate và mỗi bên ghi một hàng làm thay đổi predicate đó, PostgreSQL SSI có thể phát hiện cấu trúc phụ thuộc nguy hiểm và hủy một transaction với SQLSTATE `40001`. Transaction nào bị hủy và thời điểm phát hiện phụ thuộc lịch cụ thể; hãy ghi lại kết quả thực tế trên phiên bản đang chạy.

Nếu một transaction bị serialization failure, rollback và chạy lại **toàn bộ transaction**. Không chỉ retry câu `INSERT`, vì lần đọc `count(*)` và quyết định nghiệp vụ phải được tính lại trong transaction mới.

## 7. Thí nghiệm 4: MySQL InnoDB gap lock ở Repeatable Read

InnoDB có thể bảo vệ khoảng chỉ mục bằng gap lock hoặc next-key lock trong các locking read phù hợp. Ở cấu hình phổ biến, isolation mặc định là Repeatable Read. Tuy nhiên, kết quả phụ thuộc index và access path; hãy bảo đảm `id` là index được dùng.

Tạo bảng InnoDB và hai hàng biên:

```sql
CREATE TABLE range_lock_lab (
    id   INT NOT NULL,
    note VARCHAR(100),
    PRIMARY KEY (id)
) ENGINE = InnoDB;

INSERT INTO range_lock_lab(id, note)
VALUES (10, 'lower boundary'),
       (20, 'upper boundary');
```

### Session A — Repeatable Read

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT id, note
FROM range_lock_lab
WHERE id > 10
  AND id < 20
FOR UPDATE;

-- Kết quả rỗng. Giữ transaction mở.
```

Do đây là locking read trên index range, InnoDB có thể lấy gap/next-key lock bảo vệ khoảng giữa 10 và 20, dù không có hàng nào được trả về.

### Session B

```sql
START TRANSACTION;

INSERT INTO range_lock_lab(id, note)
VALUES (15, 'inserted by B');

-- Quan sát: insert có thể chờ A giải phóng gap lock.
```

Quay lại Session A:

```sql
COMMIT;
```

Sau khi A commit, Session B có thể tiếp tục và commit:

```sql
COMMIT;
```

**Quan sát:** với InnoDB, một locking read trên range có index phù hợp ở Repeatable Read có thể khóa khoảng trống và chặn insert vào khoảng đó. Đây là khác biệt quan trọng so với PostgreSQL `SELECT FOR UPDATE`.

### 7.1. SELECT thông thường không giống SELECT FOR UPDATE

Lặp lại thí nghiệm với Session A dùng consistent read thông thường:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT id, note
FROM range_lock_lab
WHERE id > 10
  AND id < 20;
```

Trong InnoDB, consistent read thông thường dùng read view và không lấy gap lock chỉ vì predicate đó được đọc. Session B có thể insert `id = 15` và commit. Session A vẫn có thể không nhìn thấy hàng mới trong snapshot Repeatable Read của mình.

Điều này nhấn mạnh hai khái niệm khác nhau: snapshot read ổn định và locking read bảo vệ range.

### 7.2. Thí nghiệm READ COMMITTED

Lặp lại locking read với Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT id
FROM range_lock_lab
WHERE id > 10
  AND id < 20
FOR UPDATE;
```

Ở InnoDB Read Committed, gap locking cho các tìm kiếm và scan thông thường phần lớn được tắt, ngoại trừ một số trường hợp như kiểm tra foreign key và duplicate key. Vì vậy, insert `id = 15` của B thường không bị gap lock từ truy vấn này chặn. Hãy xác nhận lock diagnostics vì các lock khác vẫn có thể phát sinh do constraint hoặc thao tác bổ sung.

## 8. Equality lookup trên khóa duy nhất và khóa chưa tồn tại

Một câu `WHERE id = 15` trên unique index khác với một range query về mặt access path. Khi hàng tồn tại và DBMS dùng unique lookup, lock thường có thể tập trung vào record đó. Khi hàng không tồn tại, InnoDB có thể bảo vệ gap nơi khóa đó sẽ được chèn trong một locking read, tùy isolation level và điều kiện tìm kiếm.

Thí nghiệm InnoDB:

Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT id
FROM range_lock_lab
WHERE id = 15
FOR UPDATE;

-- Nếu id=15 chưa tồn tại, kết quả rỗng.
```

Session B:

```sql
START TRANSACTION;
INSERT INTO range_lock_lab(id, note)
VALUES (15, 'exact key insert');
```

Trong trường hợp phù hợp, B có thể phải chờ gap lock mà A lấy trên vị trí của khóa 15. Sau khi A commit, B tiếp tục.

Không khái quát kết quả này sang mọi điều kiện hoặc mọi DBMS. Unique index, composite index, điều kiện bằng/range, isolation level và optimizer đều ảnh hưởng phạm vi khóa.

## 9. Thí nghiệm 5: SQL Server key-range lock ở Serializable

SQL Server có thể dùng key-range lock để ngăn insert vào phạm vi predicate khi transaction chạy ở `SERIALIZABLE`. Để quan sát rõ, tạo bảng có clustered primary key trên `id`:

```sql
CREATE TABLE dbo.range_lock_lab (
    id   int NOT NULL,
    note varchar(100) NULL,
    CONSTRAINT PK_range_lock_lab PRIMARY KEY CLUSTERED (id)
);

INSERT INTO dbo.range_lock_lab(id, note)
VALUES (10, 'lower boundary'),
       (20, 'upper boundary');
```

### Session A

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;

SELECT id, note
FROM dbo.range_lock_lab
WHERE id > 10
  AND id < 20;

-- Kết quả rỗng. Giữ transaction mở.
```

Với index và kế hoạch truy cập phù hợp, SQL Server có thể giữ key-range lock bảo vệ miền khóa giữa 10 và 20.

### Session B

```sql
BEGIN TRANSACTION;

INSERT INTO dbo.range_lock_lab(id, note)
VALUES (15, 'inserted by B');

-- Quan sát: lệnh INSERT có thể chờ key-range lock của A.
```

Quay lại Session A:

```sql
COMMIT TRANSACTION;
```

Session B có thể tiếp tục, sau đó:

```sql
COMMIT TRANSACTION;
```

### 9.1. So sánh với Repeatable Read

SQL Server Repeatable Read giữ khóa trên các hàng đã đọc để ngăn chúng bị sửa hoặc xóa trước khi transaction kết thúc, nhưng không bảo vệ toàn bộ khoảng để ngăn phantom như Serializable.

Lặp lại Session A ở Repeatable Read:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
BEGIN TRANSACTION;

SELECT id
FROM dbo.range_lock_lab
WHERE id > 10
  AND id < 20;
```

Session B có thể insert `id = 15` vì không có hàng kết quả nào cần giữ row lock và Repeatable Read không cung cấp cùng range protection như Serializable. Nếu A chạy lại query trước khi commit, nó có thể thấy hàng mới theo semantics Read Committed/Repeatable Read của SQL Server đối với phantom.

### 9.2. Kiểm tra kế hoạch và index

Key-range lock được thực hiện trên khóa chỉ mục. Nếu optimizer chọn scan rộng hoặc dùng index khác, phạm vi khóa có thể rộng hơn dự kiến. Hãy xem actual execution plan và xác nhận predicate được seek trên clustered primary key.

Không nên ép index trong production chỉ để làm cho một thí nghiệm cho kết quả mong muốn. Nếu cần dùng hint để cô lập một test, ghi rõ hint và so sánh với kế hoạch mà optimizer tự chọn.

## 10. Oracle: SELECT FOR UPDATE không tạo row lock cho kết quả rỗng

Oracle dùng multiversion read consistency và row-level locking. Một `SELECT ... FOR UPDATE` khóa các hàng mà truy vấn tìm thấy để cập nhật. Nếu truy vấn trả về 0 hàng, không có row nào được khóa bởi câu lệnh đó để ngăn một hàng tương lai được insert.

Tạo bảng và dữ liệu tương tự:

```sql
CREATE TABLE range_lock_lab (
    id   NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);

INSERT INTO range_lock_lab(id, note)
VALUES (10, 'lower boundary');

INSERT INTO range_lock_lab(id, note)
VALUES (20, 'upper boundary');

COMMIT;
```

Session A:

```sql
SELECT id, note
FROM range_lock_lab
WHERE id > 10
  AND id < 20
FOR UPDATE;

-- Kết quả rỗng; không có row lock trên một hàng không tồn tại.
```

Session B:

```sql
INSERT INTO range_lock_lab(id, note)
VALUES (15, 'inserted by B');

COMMIT;
```

Insert không bị chặn bởi row lock của một hàng kết quả rỗng. Nếu cần bảo vệ bất biến theo phòng/nhóm/khoảng, có thể dùng constraint phù hợp, khóa một hàng guard đã tồn tại hoặc transaction Serializable theo semantics Oracle. Không dùng một lần `SELECT FOR UPDATE` rỗng làm khóa cho khoảng dữ liệu.

## 11. Khi cần ngăn trùng một khóa, hãy dùng UNIQUE constraint

Một trường hợp phổ biến là ứng dụng muốn tạo người dùng nếu email chưa tồn tại. Cách dễ mắc race condition là:

```sql
SELECT user_id
FROM app_user
WHERE email = 'a@example.com';

-- Nếu không có hàng thì INSERT.
```

Hai session có thể cùng đọc thấy không có hàng, rồi cùng insert. Không nên dựa vào `SELECT FOR UPDATE` trên hàng chưa tồn tại để bảo vệ uniqueness nếu DBMS không khóa gap theo cách cần thiết.

Hãy để unique constraint là nguồn bảo đảm cuối cùng:

```sql
CREATE TABLE app_user (
    user_id bigint PRIMARY KEY,
    email   varchar(320) NOT NULL,
    CONSTRAINT uq_app_user_email UNIQUE (email)
);
```

Hai session cùng insert email giống nhau sẽ được DBMS điều phối qua unique index/constraint. Một thao tác có thể phải chờ transaction kia; cuối cùng chỉ một hàng có thể commit với khóa duy nhất đó. Transaction còn lại nhận lỗi unique violation hoặc kết quả tương ứng của câu lệnh upsert theo DBMS.

Đây là ví dụ quan trọng về việc không cần tự khóa một hàng chưa tồn tại để bảo vệ một quy tắc uniqueness. Constraint chuyên biệt thực hiện việc đó an toàn hơn.

## 12. Khi cần ngăn chồng lấn khoảng, uniqueness đơn giản chưa đủ

Một unique constraint trên `(room_id, starts_at)` chỉ ngăn hai reservation có cùng thời điểm bắt đầu. Nó không ngăn hai khoảng khác nhau nhưng giao nhau:

```text
Reservation A: 09:00 -------- 11:00
Reservation B:       10:00 -------- 12:00
                    ^ chồng lấn
```

Với PostgreSQL, có thể dùng exclusion constraint trên range:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_reservation (
    reservation_id bigint PRIMARY KEY,
    room_id        bigint NOT NULL,
    starts_at      timestamptz NOT NULL,
    ends_at        timestamptz NOT NULL,
    CONSTRAINT ck_reservation_time CHECK (ends_at > starts_at),
    CONSTRAINT ex_room_no_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            tstzrange(starts_at, ends_at, '[)') WITH &&
        )
);
```

Exclusion constraint bảo đảm hai hàng cùng phòng không có khoảng thời gian giao nhau theo operator đã khai báo. Đây là cơ chế DBMS hiểu trực tiếp và có thể kiểm tra dưới cạnh tranh.

Ở DBMS không có exclusion constraint tương đương, có thể khóa hàng guard đại diện cho `room_id` trước khi kiểm tra và insert. Mọi transaction đặt/hủy/sửa reservation của cùng phòng phải lấy cùng guard lock trong một transaction. Hoặc dùng Serializable nếu phạm vi predicate phức tạp và ứng dụng xử lý retry đúng cách.

## 13. Guard row: bảo vệ một khoảng logic bằng hàng luôn tồn tại

Nếu cần phối hợp mọi thay đổi của một tài nguyên logic, tạo hàng guard có khóa chính ổn định. Ví dụ:

```sql
CREATE TABLE room_guard (
    room_id bigint PRIMARY KEY
);
```

Mỗi transaction đặt chỗ cho phòng 8 phải khóa cùng hàng guard trước khi kiểm tra reservation:

```sql
BEGIN;

SELECT room_id
FROM room_guard
WHERE room_id = 8
FOR UPDATE;

SELECT count(*)
FROM room_reservation
WHERE room_id = 8
  AND starts_at < :requested_end
  AND ends_at > :requested_start;

-- Chỉ INSERT nếu không có reservation chồng lấn.

COMMIT;
```

T1 lấy guard lock trước. T2 phải chờ cùng hàng guard. Sau khi T1 commit, T2 mới lấy được lock và kiểm tra lại trạng thái theo snapshot phù hợp.

Guard row chỉ đúng nếu mọi đường ghi có thể ảnh hưởng bất biến đều tuân thủ giao thức. Một script quản trị hoặc job nền bỏ qua guard có thể phá quy tắc. Ngoài ra, hàng guard phải tồn tại; `SELECT FOR UPDATE` trên guard row chưa được tạo vẫn không khóa được hàng tương lai. Hãy tạo và duy trì guard row khi tạo tài nguyên.

### 13.1. Cẩn thận với snapshot khi dùng guard lock

Trong PostgreSQL Read Committed, mỗi statement thường có snapshot mới. Nếu transaction chờ guard lock rồi chạy câu đếm ở statement sau khi lấy được khóa, câu đếm có thể thấy commit vừa hoàn tất của transaction trước.

Ở Repeatable Read, snapshot được giữ ổn định trong transaction. Chỉ khóa guard mà không tạo xung đột ghi trên guard có thể khiến transaction đang chờ vẫn đọc snapshot cũ. Có thể dùng counter/version trên guard để các transaction cập nhật cùng hàng, hoặc dùng Serializable và xử lý serialization failure. Cần kiểm tra semantics của DBMS đích.

## 14. Quan sát khóa trong PostgreSQL

PostgreSQL cung cấp `pg_locks` để xem lock đang được giữ hoặc chờ. Với Serializable, SIREAD predicate locks có thể xuất hiện dưới mode `SIReadLock`.

```sql
SELECT
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name,
    page,
    tuple,
    virtualtransaction,
    pid
FROM pg_locks
WHERE relation = 'range_lock_lab'::regclass
ORDER BY pid, locktype, mode;
```

Trong một thí nghiệm Serializable, có thể lọc riêng:

```sql
SELECT
    mode,
    relation::regclass AS relation_name,
    page,
    tuple,
    pid
FROM pg_locks
WHERE mode = 'SIReadLock';
```

SIREAD có thể được ghi nhận ở các mức tuple/page/relation tùy truy vấn và cơ chế quản lý predicate lock. Nó không phải lock chờ thông thường; `granted` và wait graph cần được diễn giải theo semantics PostgreSQL.

Để tìm blocker/waiter:

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.query AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.query AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = p.blocker_pid;
```

Nếu Session B insert không chờ trong thí nghiệm PostgreSQL `FOR UPDATE` trên kết quả rỗng, đó là kết quả mong đợi. Đừng tìm một gap lock mà cơ chế này không tạo ra.

## 15. Quan sát gap lock trong MySQL InnoDB

MySQL 8.0 cung cấp `performance_schema.data_locks` và `data_lock_waits` để quan sát các lock liên quan đến InnoDB. Quyền đọc Performance Schema phụ thuộc cấu hình và quyền tài khoản.

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_NAME = 'range_lock_lab';
```

Để xem quan hệ chờ:

```sql
SELECT
    req.ENGINE_TRANSACTION_ID AS waiting_trx,
    req.INDEX_NAME,
    req.LOCK_MODE AS waiting_mode,
    req.LOCK_DATA AS waiting_data,
    blk.ENGINE_TRANSACTION_ID AS blocking_trx,
    blk.LOCK_MODE AS blocking_mode,
    blk.LOCK_DATA AS blocking_data
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
  ON req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
  ON blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
```

Hãy tìm lock trên index `PRIMARY` hoặc index được truy vấn dùng và quan sát lock mode/data tương ứng. Cách hiển thị chi tiết có thể thay đổi theo phiên bản. `SHOW ENGINE INNODB STATUS` cũng hữu ích để kiểm tra deadlock gần nhất.

## 16. Quan sát key-range lock trong SQL Server

SQL Server lưu lock hiện tại trong dynamic management view `sys.dm_tran_locks`. Cần quyền phù hợp, thường là `VIEW SERVER STATE` hoặc quyền tương ứng của phiên bản.

```sql
SELECT
    request_session_id,
    resource_type,
    request_mode,
    request_status,
    resource_description
FROM sys.dm_tran_locks
WHERE resource_database_id = DB_ID()
ORDER BY request_session_id, resource_type, request_mode;
```

Trong thí nghiệm Serializable, có thể thấy resource type `KEY` với các mode range như `RangeS-S`, `RangeS-U` hoặc mode khác tùy thao tác. Nếu Session B đang insert vào range bị khóa, trạng thái request có thể là `WAIT`.

Kết hợp với execution plan để xác nhận index và seek predicate. Nếu query scan cả index, SQL Server có thể phải bảo vệ phạm vi lớn hơn khoảng dự định.

## 17. Quan sát trong Oracle

Oracle cung cấp thông tin về session đang chờ, blocker và lock qua các view như `V$SESSION`, `V$LOCK`, `DBA_BLOCKERS` và `DBA_WAITERS` (quyền truy cập tùy môi trường).

Ví dụ xem session đang chờ:

```sql
SELECT
    sid,
    serial#,
    username,
    event,
    blocking_session,
    seconds_in_wait
FROM v$session
WHERE blocking_session IS NOT NULL;
```

Oracle row locks được quản lý ở cấp hàng đã tồn tại và transaction; một truy vấn `SELECT FOR UPDATE` rỗng không tạo row lock cho một hàng chưa tồn tại. Nếu cần bảo vệ một điều kiện khoảng hoặc bất biến tổng hợp, dùng constraint, guard row hoặc cơ chế transaction phù hợp thay vì giả định Oracle khóa gap như InnoDB.

## 18. Những yếu tố làm thay đổi kết quả thí nghiệm

Nếu kết quả thực tế khác dự đoán, hãy kiểm tra lần lượt các yếu tố sau:

### 18.1. Index được sử dụng

Range lock thường gắn với index access path. Nếu index không tồn tại hoặc optimizer không dùng index dự kiến, engine có thể scan rộng hơn hoặc bảo vệ phạm vi khác.

### 18.2. Equality hay range predicate

Tìm chính xác một khóa unique, tìm một khóa chưa tồn tại, tìm theo prefix của composite index và tìm một range không có cùng lock footprint. Với index `(tenant_id, id)`, predicate chỉ lọc `id` mà không lọc `tenant_id` có thể không định vị một dải hẹp.

### 18.3. Isolation level

InnoDB gap locking thay đổi đáng kể giữa Repeatable Read và Read Committed. SQL Server chỉ có key-range protection tương ứng khi dùng Serializable. PostgreSQL SSI chỉ áp dụng khi transaction chạy Serializable. Hãy đặt isolation rõ trong mỗi session thay vì dựa vào mặc định.

### 18.4. Loại câu lệnh

`SELECT` thông thường, `SELECT FOR UPDATE`, `UPDATE`, `DELETE` và `INSERT` có thể lấy lock khác nhau. Một truy vấn đọc snapshot không đồng nghĩa locking read.

### 18.5. Hàng đã tồn tại hay chưa

Nếu hàng tồn tại, row lock có thể bảo vệ nó. Nếu không tồn tại, cần xem engine có bảo vệ gap/range/predicate hay không. Luôn xác nhận trạng thái dữ liệu trước mỗi lượt thử.

### 18.6. Constraint và kiểm tra duy nhất

Một insert có thể chờ unique index hoặc foreign key check dù truy vấn trước đó không khóa hàng. Đừng nhầm việc insert chờ do constraint với gap lock được tạo bởi `SELECT FOR UPDATE`.

### 18.7. Lock timeout và statement timeout

Nếu Session B báo timeout, hãy xác định nó đang chờ lock nào. Timeout không chứng minh một range lock cụ thể nếu chưa xem lock diagnostics. Sau timeout, transaction có thể vẫn mở hoặc đã bị rollback một phần/toàn bộ tùy DBMS.

## 19. Ma trận kết quả cần ghi lại

Khi chạy các bài lab, ghi lại kết quả theo ma trận thay vì chỉ ghi “bị khóa” hoặc “không bị khóa”.

| DBMS/cấu hình | Truy vấn của A | Kết quả A | Hành vi insert B thường gặp | Cơ chế cần quan sát |
|---|---|---|---|---|
| PostgreSQL Read Committed | `SELECT ... FOR UPDATE` trên khóa/range rỗng | 0 hàng | B có thể insert và commit | Không có row lock cho hàng chưa tồn tại |
| PostgreSQL Repeatable Read | Đọc range rỗng trong snapshot | 0 hàng | B có thể insert; A tiếp tục không thấy hàng mới trong snapshot | Snapshot isolation, không phải gap lock |
| PostgreSQL Serializable | Đọc predicate | 0 hàng | Insert không nhất thiết chờ; một transaction có thể bị abort khi tạo dangerous structure | SIREAD/SSI và serialization failure |
| MySQL InnoDB Repeatable Read | Locking read trên index range | Có thể 0 hàng | Insert vào gap có thể chờ | Gap/next-key lock |
| MySQL InnoDB Read Committed | Locking read trên range | Có thể 0 hàng | Gap lock thường không chặn insert, trừ ngoại lệ constraint | Lock diagnostics và isolation setting |
| SQL Server Serializable | Đọc range có index | Có thể 0 hàng | Insert vào range có thể chờ | Key-range lock |
| SQL Server Repeatable Read | Đọc range | Có thể 0 hàng | Insert có thể tiếp tục và tạo phantom | Row/key lock trên hàng hiện có, không bảo vệ gap đầy đủ |
| Oracle | `SELECT FOR UPDATE` trên range rỗng | 0 hàng | Insert có thể tiếp tục | Không có row lock cho hàng chưa tồn tại |

Đây là kỳ vọng thường gặp, không phải cam kết cho mọi phiên bản và execution plan. Ghi rõ phiên bản, isolation level, index, câu SQL và lock diagnostics cùng kết quả.

## 20. Dùng hai session để kiểm chứng một bất biến nghiệp vụ

Thí nghiệm khóa chỉ có ý nghĩa khi liên hệ với quy tắc cần bảo vệ. Ví dụ, hệ thống đặt chỗ không cho hai reservation chồng lấn cùng phòng.

Giả sử hiện tại chưa có reservation nào cho phòng 8 trong khoảng 09:00–10:00.

### Session A

```sql
BEGIN;

SELECT count(*)
FROM reservation
WHERE room_id = 8
  AND starts_at < TIMESTAMP '2026-11-14 10:00:00'
  AND ends_at > TIMESTAMP '2026-11-14 09:00:00';

-- Kết quả 0. Giữ transaction mở.
```

### Session B

```sql
BEGIN;

INSERT INTO reservation(room_id, starts_at, ends_at)
VALUES (8,
        TIMESTAMP '2026-11-14 09:30:00',
        TIMESTAMP '2026-11-14 10:30:00');

COMMIT;
```

Nếu Session A chỉ dùng một consistent read không khóa, Session B có thể insert và commit. Session A không được phép suy luận rằng kết quả `count = 0` đã đặt chỗ cho khoảng thời gian đó.

Để bảo vệ bất biến, chọn một cơ chế có semantics rõ:

- PostgreSQL: exclusion constraint trên `room_id` và range thời gian.
- SQL Server: Serializable với key-range lock trên index phù hợp hoặc guard row.
- MySQL InnoDB: locking read trên index range ở isolation/configuration đã xác minh hoặc guard row.
- Oracle: guard row hoặc Serializable theo thiết kế và semantics Oracle.

Sau đó lặp lại thí nghiệm với hai session cùng kiểm tra và insert khoảng chồng lấn. Kết quả mong muốn là chỉ một reservation được commit, hoặc transaction còn lại bị chặn/abort và phải xử lý lại.

## 21. Khi nào nên dùng từng cơ chế?

| Yêu cầu | Cơ chế nên cân nhắc | Lý do |
|---|---|---|
| Khóa một hàng đang tồn tại để cập nhật | Row lock / `SELECT FOR UPDATE` | Có một hàng cụ thể để khóa |
| Bảo đảm một giá trị khóa không trùng | `UNIQUE` constraint/index | DBMS điều phối insert cạnh tranh trên unique key |
| Ngăn insert vào một khoảng chỉ mục trong transaction | Gap/next-key lock hoặc key-range lock theo DBMS | Bảo vệ range trước phantom |
| Bảo vệ predicate phức tạp ở PostgreSQL | `SERIALIZABLE` với SSI | Theo dõi phụ thuộc và abort lịch không tuần tự hóa |
| Ngăn các khoảng thời gian giao nhau | Exclusion constraint hoặc cơ chế guard/Serializable | Quy tắc dựa trên quan hệ giữa các khoảng, không phải equality đơn giản |
| Bảo vệ một tài nguyên logic luôn có hàng đại diện | Guard row | Tạo điểm đồng bộ ổn định |
| Đọc báo cáo không cần chặn writer | Snapshot/MVCC read phù hợp | Chấp nhận freshness theo isolation/replication semantics |

Không chọn lock chỉ dựa trên tên cú pháp. Hãy bắt đầu từ bất biến: điều gì không được phép xảy ra, những transaction nào có thể làm nó xảy ra, và DBMS đích có cơ chế nào bảo vệ chính xác điều kiện đó.

## 22. Những lỗi thường gặp khi làm thí nghiệm

- **Dùng một connection cho cả A và B.** Không tạo được hai transaction độc lập và không tái hiện cạnh tranh thật.
- **Commit A quá sớm.** B chạy sau khi khóa đã được nhả nên không quan sát được trạng thái chờ.
- **Không reset dữ liệu.** Hàng 15 còn từ lượt trước khiến truy vấn không còn trả rỗng.
- **Nhầm snapshot với lock.** A không nhìn thấy hàng mới không có nghĩa B đã bị chặn.
- **Không xác nhận index.** Lock range phụ thuộc index và access path; thiếu index có thể làm phạm vi khóa rộng hơn.
- **Dùng isolation mặc định không rõ.** Mỗi DBMS và session có thể dùng mức khác nhau.
- **Kết luận từ một lần chạy.** Lịch thực thi và optimizer có thể thay đổi; cần ghi lại cấu hình và lặp lại.
- **Nhầm insert chờ do unique/FK với gap lock.** Xem lock diagnostics và constraint liên quan.
- **Không rollback sau lỗi.** Một session có thể còn transaction aborted hoặc lock chưa giải phóng.
- **Dùng SELECT kiểm tra rồi INSERT như một bảo đảm.** Nếu không có constraint hoặc cơ chế đồng bộ, hai session có thể cùng thấy kết quả rỗng.
- **Cho rằng Serializable luôn block.** PostgreSQL SSI có thể để thao tác chạy rồi abort một transaction thay vì chặn insert bằng gap lock.

## 23. Quy trình thực hành và ghi nhận kết quả

Với mỗi DBMS, hãy làm theo trình tự:

1. Ghi phiên bản engine, isolation level và cấu hình liên quan.
2. Tạo bảng có primary key/index rõ ràng và hai hàng biên.
3. Xác nhận khóa hoặc khoảng cần thử hiện không có hàng.
4. Mở Session A, bắt đầu transaction và chạy truy vấn khóa/đọc predicate.
5. Giữ A mở, chạy insert hoặc update trong Session B.
6. Ghi lại B hoàn tất, chờ, timeout hay bị constraint từ chối.
7. Kiểm tra lock diagnostics để xác định tài nguyên thực sự gây chờ.
8. Commit/rollback A rồi quan sát B tiếp tục như thế nào.
9. Chạy lại với isolation level hoặc loại truy vấn khác.
10. Xác nhận dữ liệu cuối và dọn trạng thái trước lượt tiếp theo.

Nên lưu lại ít nhất các thông tin sau:

| Trường ghi nhận | Ví dụ |
|---|---|
| DBMS/version | PostgreSQL 17.x, MySQL 8.0.x, SQL Server 2022, Oracle 19c |
| Isolation | READ COMMITTED, REPEATABLE READ, SERIALIZABLE |
| Index | PRIMARY KEY trên `id`; index được optimizer dùng |
| Session A statement | Predicate, locking clause và thời điểm bắt đầu |
| Session B statement | INSERT/UPDATE và thời điểm bắt đầu |
| Kết quả B | Hoàn tất ngay, chờ, timeout, constraint error |
| Lock evidence | Lock type/mode, index key/range, blocker/waiter |
| Kết quả transaction | Commit, rollback, serialization failure |
| Dữ liệu cuối | Hàng nào tồn tại và giá trị nào được commit |

## 24. Những điểm cần ghi nhớ

- `SELECT FOR UPDATE` thường khóa các hàng được tìm thấy; kết quả rỗng không có row nào để khóa.
- Khóa một hàng hiện có không đồng nghĩa khóa vị trí của một hàng có thể được chèn sau này.
- InnoDB có thể dùng gap/next-key lock cho locking read trên index range ở Repeatable Read; Read Committed thường giảm gap locking, ngoại trừ một số trường hợp constraint.
- SQL Server Serializable có thể dùng key-range lock để ngăn insert tạo phantom trong predicate range.
- PostgreSQL không dùng gap lock cho `SELECT FOR UPDATE`; Serializable SSI theo dõi predicate và có thể abort transaction thay vì chặn insert.
- Oracle `SELECT FOR UPDATE` khóa hàng tìm thấy; kết quả rỗng không tạo row lock cho hàng chưa tồn tại.
- Snapshot ổn định và khóa khoảng là hai cơ chế khác nhau. Transaction có thể không nhìn thấy hàng mới dù transaction khác đã chèn thành công.
- Phạm vi khóa phụ thuộc isolation level, index, điều kiện equality/range và execution plan.
- Dùng `UNIQUE` cho uniqueness; dùng exclusion constraint, guard row, range lock hoặc Serializable cho bất biến khoảng phù hợp.
- Thực hành bằng hai session độc lập và kiểm tra lock diagnostics; không suy luận chỉ từ việc câu lệnh có chờ hay không.

Khi kiểm chứng khóa trên hàng chưa tồn tại, hãy quan sát đồng thời ba thứ: transaction A đã đọc predicate nào, transaction B có thể chèn gì, và DBMS thực sự bảo vệ row/index range/predicate nào. Cách tiếp cận này giúp phân biệt row lock với gap/next-key lock, key-range lock và SSI, đồng thời cho thấy vì sao một câu truy vấn rỗng không tự động bảo vệ bất biến nghiệp vụ.
