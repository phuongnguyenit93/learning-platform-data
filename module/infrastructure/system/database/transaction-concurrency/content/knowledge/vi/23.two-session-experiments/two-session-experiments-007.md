# Đối chiếu SELECT thường với SELECT kèm khóa

Khi hai transaction cùng truy cập một hàng, câu `SELECT` thông thường và câu `SELECT` yêu cầu khóa có thể quan sát dữ liệu và ảnh hưởng đến transaction khác theo những cách rất khác nhau. `SELECT` thường thường phục vụ việc đọc một phiên bản nhất quán; `SELECT ... FOR UPDATE` hoặc locking read tương đương vừa đọc vừa xin quyền khóa trên hàng để bảo vệ một quyết định cập nhật tiếp theo.

Sự khác biệt này đặc biệt rõ trong cơ sở dữ liệu dùng MVCC. Một truy vấn đọc snapshot thông thường có thể đọc phiên bản đã commit mà không phải chờ transaction đang giữ khóa ghi. Ngược lại, locking read thường phải chờ khóa không tương thích và sau đó đọc theo ngữ nghĩa của loại locking read mà hệ quản trị cung cấp. Một số hệ quản trị mặc định dùng khóa chia sẻ cho `SELECT` ở mức `READ COMMITTED`; một số cấu hình lại dùng row versioning. Vì vậy, không thể kết luận rằng mọi `SELECT` đều không khóa hoặc mọi `SELECT` đều chặn writer.

Bài này dùng hai phiên kết nối độc lập để so sánh trực tiếp: một phiên đọc, một phiên cập nhật; sau đó đảo vai trò để quan sát blocking. Các kết quả phải được diễn giải cùng hệ quản trị, isolation level, autocommit và loại câu lệnh đang chạy.

## 1. Hai loại SELECT khác nhau ở mục tiêu

### SELECT thường: đọc dữ liệu theo ngữ nghĩa isolation

Một câu lệnh như:

```sql
SELECT balance
FROM accounts
WHERE id = 10;
```

chỉ yêu cầu đọc dữ liệu. Trong hệ thống MVCC, database có thể trả về phiên bản phù hợp với snapshot của transaction. Nếu một transaction khác đang cập nhật hàng nhưng chưa commit, truy vấn thường có thể đọc phiên bản đã commit trước đó thay vì chờ transaction ghi hoàn tất.

Ở các chế độ locking-based `READ COMMITTED`, database có thể lấy shared lock trong lúc đọc để tránh đọc dữ liệu chưa commit, rồi nhả khóa khi statement kết thúc. Khi đó, câu `SELECT` thường có thể chặn writer trong một khoảng thời gian ngắn. Ở SQL Server bật `READ_COMMITTED_SNAPSHOT`, cùng mức isolation `READ COMMITTED` lại dùng row versioning cho truy vấn đọc thông thường.

Vì vậy, `SELECT` thường không mang một hành vi khóa thống nhất giữa các engine hoặc cấu hình.

### SELECT kèm khóa: đọc và yêu cầu bảo vệ hàng

Một locking read thường dùng cú pháp:

```sql
SELECT balance
FROM accounts
WHERE id = 10
FOR UPDATE;
```

Ý định là lấy khóa cập nhật/độc quyền tương ứng trên hàng được chọn để transaction có thể kiểm tra rồi sửa hàng mà không để một transaction khác đồng thời thực hiện thay đổi không tương thích.

Một số hệ quản trị còn hỗ trợ khóa chia sẻ:

```sql
SELECT balance
FROM accounts
WHERE id = 10
FOR SHARE;
```

Khóa chia sẻ cho phép các locking reader tương thích cùng đọc, nhưng thường khiến writer phải chờ. `FOR UPDATE` thường xung đột với cả locking reader và writer khác trên cùng hàng. Tên cú pháp và ma trận tương thích chính xác phụ thuộc hệ quản trị.

### So sánh ở mức khái niệm

| Đặc điểm | `SELECT` thường | `SELECT` kèm khóa |
|---|---|---|
| Mục tiêu | Đọc phiên bản dữ liệu theo isolation level | Đọc và lấy khóa trên tài nguyên được chọn |
| Có thể đọc phiên bản cũ đã commit? | Có trong các mô hình snapshot/MVCC | Thường locking read đọc theo ngữ nghĩa current read hoặc phải xử lý xung đột; chi tiết tùy engine |
| Có thể chặn writer? | Có hoặc không, tùy engine/cấu hình | Thường có thể chặn writer trên tài nguyên đã khóa |
| Có thể bị writer chặn? | Có trong locking-based read hoặc khi cần tài nguyên khác | Có nếu khóa không tương thích đang được giữ |
| Khóa thường được giữ đến đâu? | Có thể chỉ trong statement hoặc không cần row lock lâu dài | Thường đến commit/rollback trong transaction; có ngoại lệ theo engine |
| Phù hợp | Báo cáo, đọc thông thường, truy vấn không cần giữ quyền cập nhật | Đọc rồi cập nhật, claim tài nguyên, kiểm tra điều kiện cần được bảo vệ |

## 2. Chuẩn bị dữ liệu cho thí nghiệm hai phiên

Dùng một bảng nhỏ để quan sát dễ dàng. Câu lệnh tạo bảng có thể điều chỉnh kiểu dữ liệu theo hệ quản trị:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
);

INSERT INTO accounts (id, balance)
VALUES (10, 1000.00);
```

Mở hai connection độc lập, gọi là **Phiên A** và **Phiên B**. Không chạy hai cửa sổ query trên cùng một connection nếu công cụ SQL đang tái sử dụng session.

Trước khi thử, ghi lại:

- Tên và phiên bản database.
- Isolation level của từng session.
- `autocommit` đang bật hay tắt.
- Engine/table type có hỗ trợ MVCC hoặc row versioning không.
- Các câu lệnh có dùng locking read hay hint đặc biệt không.

Đảm bảo dữ liệu ban đầu là `balance = 1000.00`. Sau mỗi thí nghiệm, kết thúc transaction và khôi phục dữ liệu để lần sau không bị ảnh hưởng.

## 3. Thí nghiệm A: SELECT thường khi transaction khác đang UPDATE chưa commit

Thí nghiệm này trả lời: **một truy vấn đọc thông thường có phải chờ transaction đang sửa hàng hay không?**

### Phiên A: cập nhật nhưng chưa commit

```sql
BEGIN;

UPDATE accounts
SET balance = 900.00
WHERE id = 10;

-- Chưa COMMIT hoặc ROLLBACK.
```

Phiên A đang giữ quyền ghi trên hàng `id = 10`. Giá trị mới `900.00` chưa được commit.

### Phiên B: chạy SELECT thường

```sql
SELECT balance
FROM accounts
WHERE id = 10;
```

Kết quả có thể khác nhau:

| Cấu hình/engine | Hành vi thường gặp của Phiên B |
|---|---|
| PostgreSQL ở `READ COMMITTED` | Đọc phiên bản đã commit trước đó (`1000.00`), không chờ khóa ghi của A. |
| MySQL InnoDB với consistent read ở `READ COMMITTED` hoặc `REPEATABLE READ` | Đọc phiên bản phù hợp snapshot (`1000.00` trong tình huống này), thường không chờ khóa ghi của A. |
| SQL Server `READ COMMITTED` dùng locking truyền thống | Có thể chờ shared lock vì A đang giữ exclusive lock; sau khi A commit, B đọc giá trị mới. |
| SQL Server `READ_COMMITTED_SNAPSHOT ON` | Truy vấn thường đọc row version đã commit, thường trả `1000.00` mà không chờ A. |

Không có một kết quả duy nhất áp dụng cho mọi database. Điều cần quan sát là B có bị chặn hay không và giá trị B nhận được thuộc phiên bản nào.

### Phiên A kết thúc transaction

Nếu B đang chờ, chạy ở Phiên A:

```sql
COMMIT;
```

hoặc để kiểm tra trường hợp rollback:

```sql
ROLLBACK;
```

Nếu A commit, giá trị mới trở thành `900.00`. Nếu A rollback, thay đổi bị hủy và giá trị vẫn là `1000.00`. Một truy vấn snapshot đọc trước đó có thể vẫn giữ kết quả cũ trong transaction hiện tại, tùy isolation level.

### Cách diễn giải

Nếu B trả về `1000.00` trong khi A chưa commit, B đã đọc phiên bản cũ đã commit. Điều này không phải dirty read: B không nhìn thấy giá trị chưa commit `900.00`.

Nếu B chờ cho đến khi A kết thúc rồi trả `900.00`, hành vi đó phù hợp với một locking read thông thường ở chế độ locking-based `READ COMMITTED`. B đã không đọc dữ liệu chưa commit; nó chờ để lấy giá trị được phép đọc sau khi khóa được nhả.

## 4. Thí nghiệm B: SELECT thường có giữ khóa chặn UPDATE không?

Thí nghiệm A cho thấy writer đang giữ khóa có thể ảnh hưởng đến reader. Thí nghiệm B đảo chiều: reader chạy trước, sau đó writer muốn cập nhật.

### Phiên B: mở transaction và đọc thường

```sql
BEGIN;

SELECT balance
FROM accounts
WHERE id = 10;

-- Giữ transaction mở, chưa COMMIT.
```

### Phiên A: thử cập nhật cùng hàng

```sql
UPDATE accounts
SET balance = balance - 50.00
WHERE id = 10;
```

Kết quả phụ thuộc cấu hình:

- Với PostgreSQL MVCC hoặc MySQL InnoDB consistent read thông thường, câu `SELECT` không giữ khóa hàng ngăn writer theo cách của `FOR UPDATE`; câu `UPDATE` thường có thể tiếp tục và lấy khóa ghi.
- Với SQL Server locking-based `READ COMMITTED`, shared lock của câu đọc thông thường thường được nhả khi statement kết thúc. Vì vậy, việc B còn mở transaction không nhất thiết làm A phải chờ.
- Với SQL Server `REPEATABLE READ` dùng locking, shared lock có thể được giữ đến hết transaction và chặn A cập nhật hàng đó.
- Với SQL Server `SNAPSHOT` hoặc `READ_COMMITTED_SNAPSHOT`, đọc thông thường dùng row versioning; writer thường không bị chặn bởi shared row lock từ truy vấn đọc đó.

Nếu câu UPDATE chạy thành công trong khi transaction B vẫn mở, điều đó cho thấy câu `SELECT` đã không giữ khóa loại trừ writer trong tình huống đó. Nếu A chờ, kiểm tra isolation level và chế độ đọc đang sử dụng.

### Kết thúc Phiên B

```sql
COMMIT;
```

Nếu A đang chờ vì shared lock, sau khi B commit, A có thể tiếp tục. Đừng dùng một kết quả của SQL Server locking `REPEATABLE READ` để kết luận PostgreSQL hoặc MySQL InnoDB cũng giữ khóa đọc đến commit.

## 5. Thí nghiệm C: SELECT FOR UPDATE rồi thử UPDATE ở phiên khác

Đây là thí nghiệm thể hiện rõ mục đích của locking read: reader chủ động lấy khóa để bảo vệ hàng trong khi đưa ra quyết định.

### Phiên A: lấy khóa cập nhật

Trong PostgreSQL hoặc MySQL InnoDB, có thể dùng:

```sql
BEGIN;

SELECT balance
FROM accounts
WHERE id = 10
FOR UPDATE;

-- Giữ transaction mở.
```

Phiên A đã yêu cầu khóa ghi tương ứng trên hàng được chọn. Khóa thường được giữ đến khi transaction kết thúc.

### Phiên B: thử cập nhật cùng hàng

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 50.00
WHERE id = 10;
```

Phiên B thường phải chờ vì A đang giữ khóa không tương thích. Trong lúc B chờ, quay lại Phiên A và kết thúc:

```sql
COMMIT;
```

Sau khi A commit và nhả khóa, B có thể tiếp tục cập nhật rồi commit. Nếu A rollback, B tiếp tục trên trạng thái đã commit trước đó.

### Quan sát điều gì?

- Bị chặn tại câu `UPDATE` của B, không phải tại câu `SELECT` của A.
- B chỉ tiếp tục sau khi A commit/rollback hoặc sau khi timeout/deadlock được xử lý.
- Nếu A giữ transaction mở lâu, B và các transaction khác cũng phải chờ.

Thí nghiệm này cho thấy locking read có chi phí blocking. Dùng nó khi cần bảo vệ một quyết định cập nhật; không dùng cho mọi truy vấn chỉ vì muốn “đọc dữ liệu mới nhất”.

## 6. Thí nghiệm D: SELECT FOR UPDATE có phải đọc phiên bản mới nhất không?

Trong nhiều engine MVCC, locking read được xử lý như một **current read** thay vì consistent snapshot read. Nó có thể phải chờ transaction đang ghi rồi lấy khóa trên phiên bản mới nhất mà engine cho phép tại isolation level hiện tại.

Ví dụ với PostgreSQL ở `READ COMMITTED`:

1. Phiên A cập nhật hàng nhưng chưa commit.
2. Phiên B chạy `SELECT ... FOR UPDATE` trên cùng hàng và phải chờ.
3. Phiên A commit.
4. Phiên B tiếp tục, khóa phiên bản hàng đã cập nhật và trả giá trị phù hợp sau khi kiểm tra lại điều kiện truy vấn.

Ở `REPEATABLE READ` hoặc `SERIALIZABLE`, nếu hàng đã thay đổi kể từ snapshot của transaction B, hệ quản trị có thể trả lỗi serialization thay vì âm thầm chuyển sang phiên bản mới. Cần rollback và bắt đầu transaction mới khi nhận lỗi đó.

Với MySQL InnoDB, locking read như `FOR UPDATE`/`FOR SHARE` là current read; consistent read thông thường dùng snapshot. Sự khác nhau này rất quan trọng khi transaction ở `REPEATABLE READ`: một `SELECT` thường có thể vẫn nhìn thấy snapshot cũ, trong khi locking read có thể thấy dữ liệu hiện tại theo quy tắc khóa của InnoDB.

Không áp dụng máy móc kết luận của một engine cho engine khác. Hãy kiểm tra tài liệu về current read, snapshot read, locking read và hành vi sau khi chờ khóa của đúng phiên bản database.

## 7. SELECT thường và SELECT khóa trong PostgreSQL

PostgreSQL dùng MVCC cho truy vấn đọc thông thường. Ở mức `READ COMMITTED`, mỗi statement đọc snapshot được thiết lập khi statement bắt đầu. Một truy vấn thường không cần lấy row-level lock chỉ để đọc.

Các locking clause phổ biến:

| Cú pháp | Ý nghĩa khái quát |
|---|---|
| `FOR UPDATE` | Lấy khóa mạnh trên các hàng được chọn, xung đột với thao tác cập nhật/xóa và locking read không tương thích. |
| `FOR NO KEY UPDATE` | Khóa cập nhật yếu hơn `FOR UPDATE` trong trường hợp không thay đổi khóa được tham chiếu; vẫn chặn các cập nhật/xóa không tương thích. |
| `FOR SHARE` | Lấy khóa chia sẻ trên hàng, cho phép locking reader tương thích nhưng chặn một số cập nhật/xóa. |
| `FOR KEY SHARE` | Khóa nhẹ hơn, chủ yếu bảo vệ khóa được tham chiếu khỏi thay đổi/xóa theo quy tắc tương thích của PostgreSQL. |

Ví dụ:

```sql
BEGIN;

SELECT id, balance
FROM accounts
WHERE id = 10
FOR UPDATE;

UPDATE accounts
SET balance = balance - 50
WHERE id = 10;

COMMIT;
```

`SELECT FOR UPDATE` không chặn một `SELECT` thường đọc snapshot theo cùng cách nó chặn một writer. Một reader thông thường vẫn có thể đọc phiên bản đã commit phù hợp với snapshot của nó trong khi transaction A giữ row lock.

Ở `READ COMMITTED`, nếu locking statement phải chờ một updater, PostgreSQL có thể khóa phiên bản mới hơn sau khi updater commit và đánh giá lại điều kiện `WHERE` trên phiên bản đó. Ở `REPEATABLE READ`/`SERIALIZABLE`, một thay đổi sau snapshot có thể làm statement thất bại với serialization error.

`NOWAIT` làm locking read trả lỗi ngay nếu khóa không thể lấy tức thì; `SKIP LOCKED` bỏ qua hàng đang bị khóa. Ví dụ:

```sql
SELECT id
FROM jobs
WHERE status = 'READY'
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

Đây là mẫu hữu ích để nhiều worker claim các job khác nhau. `SKIP LOCKED` cố ý bỏ qua một phần hàng, nên không phù hợp để tính tổng hoặc xác nhận toàn bộ tập dữ liệu.

## 8. SELECT thường và locking read trong MySQL InnoDB

InnoDB kết hợp MVCC với row-level locking. Một `SELECT` thường là consistent nonlocking read trong các isolation level hỗ trợ snapshot. Ở `REPEATABLE READ`, các consistent read trong transaction thường dùng cùng snapshot được thiết lập bởi lần đọc đầu tiên; ở `READ COMMITTED`, mỗi consistent read thường lấy snapshot mới cho statement.

Các locking read:

```sql
SELECT *
FROM accounts
WHERE id = 10
FOR UPDATE;
```

```sql
SELECT *
FROM accounts
WHERE id = 10
FOR SHARE;
```

`FOR UPDATE` lấy exclusive locks trên các index records mà truy vấn quét; `FOR SHARE` lấy shared locks. Phạm vi khóa có thể gồm record lock, gap lock hoặc next-key lock tùy predicate, index và isolation level. Do đó, câu locking read theo khoảng có thể chặn insert vào khoảng index ngay cả khi hàng mới chưa tồn tại.

Ví dụ một truy vấn phạm vi:

```sql
START TRANSACTION;

SELECT id, balance
FROM accounts
WHERE id BETWEEN 10 AND 20
FOR UPDATE;
```

Với InnoDB `REPEATABLE READ`, các next-key locks có thể bảo vệ các record và gap trong phạm vi index được quét. Nếu truy vấn dùng index phù hợp, phạm vi khóa thường hẹp hơn; nếu thiếu index hoặc optimizer chọn kế hoạch quét rộng, phạm vi khóa có thể lớn hơn mong đợi.

Trong autocommit mode, locking read không giữ khóa qua một chuỗi xử lý dài nếu statement tự kết thúc transaction ngay sau khi chạy. Muốn đọc rồi cập nhật trong cùng phạm vi bảo vệ, hãy mở transaction tường minh, chạy locking read, kiểm tra, cập nhật rồi commit.

## 9. SELECT thường và khóa trong SQL Server

SQL Server không dùng cú pháp `SELECT ... FOR UPDATE`. Hành vi đọc phụ thuộc isolation level và các tùy chọn row versioning của database.

### READ COMMITTED với locking

Khi `READ_COMMITTED_SNAPSHOT` tắt, `READ COMMITTED` truyền thống dùng shared locks để ngăn dirty read. Shared lock của truy vấn đọc thông thường thường được giữ trong thời gian statement và nhả khi statement hoàn tất. Vì vậy, một transaction mở vẫn có thể không giữ shared row lock sau khi câu `SELECT` kết thúc.

### READ_COMMITTED_SNAPSHOT

Khi bật:

```sql
ALTER DATABASE YourDatabase
SET READ_COMMITTED_SNAPSHOT ON;
```

Truy vấn `READ COMMITTED` thông thường dùng row versioning để đọc phiên bản nhất quán ở cấp statement thay vì dùng shared locks trên hàng để đọc. Writer vẫn cần khóa ghi; reader thường không chặn writer theo kiểu shared-lock blocking.

Thay đổi tùy chọn database cần quyền phù hợp và phải được cân nhắc vận hành trước khi bật. Đây không phải câu lệnh thử nghiệm nên chạy tùy tiện trên production.

### UPDLOCK và HOLDLOCK

Để đọc hàng với ý định cập nhật, SQL Server có thể dùng hint:

```sql
BEGIN TRANSACTION;

SELECT balance
FROM dbo.accounts WITH (UPDLOCK)
WHERE id = 10;

UPDATE dbo.accounts
SET balance = balance - 50
WHERE id = 10;

COMMIT TRANSACTION;
```

`UPDLOCK` yêu cầu update lock trong lúc đọc và thường giữ đến hết transaction. Nó giúp giảm conversion deadlock khi nhiều transaction cùng đọc rồi muốn cập nhật cùng hàng.

`HOLDLOCK` yêu cầu semantics tương đương `SERIALIZABLE` cho tham chiếu bảng đó trong statement, giữ các khóa phạm vi cần thiết đến cuối transaction. Kết hợp hint phải dựa trên bất biến cần bảo vệ; không thêm `HOLDLOCK` cho mọi truy vấn vì có thể mở rộng phạm vi blocking.

`ROWLOCK` chỉ là hint yêu cầu ưu tiên khóa hàng; nó không bảo đảm tuyệt đối engine sẽ chỉ dùng row locks. SQL Server có thể chọn khóa trang/bảng hoặc escalation theo điều kiện nội bộ.

## 10. Phạm vi khóa: hàng được trả về và hàng không tồn tại

Một locking read thường bảo vệ những hàng hoặc index range mà execution plan truy cập. Nó không tự động bảo vệ mọi điều kiện nghiệp vụ trong câu truy vấn.

Ví dụ:

```sql
SELECT id
FROM reservations
WHERE event_id = 100
  AND seat_no = 'A10'
FOR UPDATE;
```

Nếu chưa có hàng `A10`, một row lock thông thường không thể khóa một hàng chưa tồn tại. Một transaction khác vẫn có thể insert hàng đó, trừ khi engine/isolation level dùng range/gap/predicate lock phù hợp hoặc có unique constraint bảo vệ.

Nếu bất biến là “mỗi ghế chỉ được đặt một lần”, nên có:

```sql
ALTER TABLE reservations
ADD CONSTRAINT uq_reservation_seat
UNIQUE (event_id, seat_no);
```

Unique constraint là lớp bảo vệ cuối cùng cho tính duy nhất khi insert đồng thời. Locking read có thể giúp phối hợp các thao tác trên hàng đã tồn tại, nhưng không thay thế constraint.

Với điều kiện dạng khoảng hoặc predicate, cần kiểm tra:

- Engine có gap lock, next-key lock hoặc predicate lock không?
- Isolation level nào bật các khóa đó?
- Truy vấn dùng index nào và khóa khoảng nào?
- Có thể diễn đạt bất biến bằng unique/exclusion constraint không?
- Có cần `SERIALIZABLE` hoặc hàng điều phối chung không?

## 11. Đọc snapshot và đọc có khóa có thể trả kết quả khác nhau

Một transaction có thể thực hiện cả consistent read và locking read. Trong một số engine, hai kiểu đọc này không nhất thiết nhìn cùng một phiên bản.

Ví dụ khái niệm với MySQL InnoDB `REPEATABLE READ`:

```text
T1: BEGIN
T1: SELECT balance thường -> 1000 (snapshot S)

T2: UPDATE balance = 900
T2: COMMIT

T1: SELECT balance thường -> vẫn 1000 theo snapshot S
T1: SELECT balance FOR UPDATE -> current read có thể thấy 900
```

Đây là đặc điểm cần hiểu khi một transaction kết hợp consistent read với locking read. Đừng tính toán bất biến bằng cách lấy một phần dữ liệu từ snapshot cũ và phần khác từ current read mới mà không có quy tắc rõ ràng. Kết quả trộn thời điểm có thể tạo ra một trạng thái quan sát không nhất quán đối với nghiệp vụ.

PostgreSQL và SQL Server có semantics khác nhau tùy isolation level. Ở PostgreSQL, `READ COMMITTED` tạo snapshot mới cho từng statement; locking read có quy tắc chờ và kiểm tra lại hàng. Ở mức snapshot cố định, thay đổi sau snapshot có thể dẫn đến lỗi serialization. SQL Server có `SNAPSHOT` và `READ_COMMITTED_SNAPSHOT` với quy tắc row versioning riêng.

## 12. Khi nào nên dùng SELECT kèm khóa?

Locking read hữu ích khi ứng dụng cần đọc một trạng thái rồi đưa ra quyết định mà trạng thái đó không được thay đổi bởi transaction khác trước khi hoàn tất thao tác.

Các trường hợp điển hình:

- Nhận một job từ bảng queue để chỉ một worker claim hàng đó.
- Đọc số dư hoặc hạn mức trước khi cập nhật, khi cần giữ hàng trong transaction.
- Chuyển trạng thái một đơn hàng sau khi xác minh trạng thái nguồn.
- Cập nhật một tài nguyên khan hiếm mà nhiều transaction có thể tranh chấp.
- Đọc hàng cấu hình cần giữ ổn định trong lúc ghi dữ liệu phụ thuộc.

Ví dụ claim job:

```sql
BEGIN;

SELECT id
FROM jobs
WHERE status = 'READY'
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 1;

UPDATE jobs
SET status = 'RUNNING',
    claimed_at = CURRENT_TIMESTAMP
WHERE id = :jobId
  AND status = 'READY';

COMMIT;
```

Trong ứng dụng thực tế, phải kiểm tra row count của `UPDATE` và xử lý trường hợp không có job. Cú pháp `SKIP LOCKED` và vị trí `LIMIT` phụ thuộc engine.

Không cần locking read nếu chỉ hiển thị dữ liệu, xây dựng báo cáo hoặc đọc một snapshot nhất quán mà không có hành động ghi cần bảo vệ. Dùng khóa không cần thiết làm tăng blocking, deadlock và thời gian giữ connection.

## 13. SELECT thường vẫn có thể bị chặn bởi những tài nguyên khác

Không nên hiểu rằng MVCC làm mọi truy vấn đọc luôn không chờ. Một `SELECT` thường vẫn có thể chờ:

- Khóa metadata/schema khi có DDL hoặc thay đổi cấu trúc.
- Khóa trên bảng hoặc tài nguyên được lấy qua hint/locking clause.
- Latch hoặc tài nguyên nội bộ của engine.
- I/O, buffer pool, CPU, connection pool hoặc hàng đợi thực thi.
- Transaction khác đang giữ khóa cần thiết trong locking-based isolation.

Ngược lại, một locking read không nhất thiết chặn mọi reader. Một truy vấn đọc snapshot thông thường có thể vẫn đọc phiên bản cũ đã commit trong khi locking reader giữ khóa hàng, tùy engine.

Khi quan sát một câu `SELECT` bị chậm, cần xác định nó đang chờ lock, I/O, CPU, connection pool hay một tài nguyên khác. Thời gian chạy dài tự nó không chứng minh có lock contention.

## 14. Quan sát blocking trong hai phiên

Để thí nghiệm có giá trị, hãy ghi lại thời điểm và session đang chờ. Không chỉ nhìn vào việc cửa sổ query “đứng im”.

### Thông tin cần ghi

| Trường | Ý nghĩa |
|---|---|
| Session/connection ID | Xác định Phiên A và Phiên B trong database. |
| SQL đang chạy | Câu `SELECT`, `UPDATE` hoặc locking read nào đang chờ. |
| Isolation level | Xác định semantics đọc và khóa. |
| Lock mode | Shared, update, exclusive, key/range hoặc mode riêng của engine. |
| Resource | Hàng, key index, page, table hoặc predicate/range. |
| Blocking session | Session nào đang giữ tài nguyên làm session khác chờ. |
| Wait duration | Thời gian đã chờ và timeout nếu có. |

### PostgreSQL

Có thể kết hợp `pg_stat_activity` và `pg_locks`:

```sql
SELECT pid, state, wait_event_type, wait_event,
       pg_blocking_pids(pid) AS blocking_pids,
       query
FROM pg_stat_activity
WHERE datname = current_database();
```

`wait_event_type = 'Lock'` và `blocking_pids` giúp xác định session bị chặn. Không phải mọi lock trong `pg_locks` đều là row lock trực tiếp; PostgreSQL MVCC thường dùng tuple metadata và transaction ID waits, vì vậy cần diễn giải theo tài liệu hệ thống.

### MySQL InnoDB

Trên phiên bản hỗ trợ Performance Schema, có thể xem:

```sql
SELECT * FROM performance_schema.data_locks;
SELECT * FROM performance_schema.data_lock_waits;
```

Các bảng này cung cấp thông tin lock và quan hệ giữa request đang chờ với lock đang được giữ. `SHOW ENGINE INNODB STATUS` cũng hữu ích khi điều tra deadlock gần nhất.

### SQL Server

Có thể xem `sys.dm_exec_requests` để biết `blocking_session_id`, `wait_type`, `wait_time` và SQL đang chạy; kết hợp `sys.dm_tran_locks` để xem lock resource và mode. Cần quyền xem DMV phù hợp.

Công cụ và cột có thể thay đổi theo phiên bản. Thí nghiệm nên dùng một database thử nghiệm, không bật/tắt isolation hoặc row-versioning options tùy tiện trên hệ thống production.

## 15. Cách tổ chức thí nghiệm để kết quả lặp lại được

Một test concurrency tốt cần điều khiển thứ tự giữa hai session. Dùng hai cửa sổ kết nối độc lập và thực hiện đúng các bước:

1. Reset `accounts.balance` về giá trị ban đầu.
2. Ghi nhận isolation level và autocommit của cả hai session.
3. Chạy lệnh ở Phiên A và dừng trước commit.
4. Chạy lệnh tương ứng ở Phiên B.
5. Ghi nhận B trả kết quả ngay, chờ hay nhận lỗi.
6. Quan sát wait/blocking bằng công cụ của engine.
7. Kết thúc transaction ở A bằng commit hoặc rollback.
8. Ghi nhận B tiếp tục như thế nào và giá trị cuối cùng.
9. Kết thúc B và reset dữ liệu trước thí nghiệm tiếp theo.

Không dùng một câu `SELECT` khác trên chính Phiên B để “kiểm tra” khi câu lệnh đầu đang bị chặn, vì connection đó có thể chỉ thực thi tuần tự một statement tại một thời điểm. Dùng connection thứ ba để quan sát nếu cần.

Tránh chỉ dùng `sleep` trong test tự động để đoán thứ tự. Trong integration test, dùng barrier/latch ở tầng ứng dụng hoặc tín hiệu đồng bộ rõ ràng để bảo đảm Phiên A đã lấy khóa trước khi Phiên B chạy. Sau đó xác nhận blocking bằng wait metadata hoặc timeout có kiểm soát.

## 16. Những hiểu lầm thường gặp

- **“SELECT thường không bao giờ lấy khóa.”** Không đúng. Một số engine dùng shared lock cho `READ COMMITTED`; schema/metadata lock cũng có thể xuất hiện.
- **“SELECT thường luôn chặn UPDATE.”** Không đúng. MVCC hoặc row-versioning có thể cho reader đọc phiên bản đã commit mà không chặn writer.
- **“SELECT FOR UPDATE khóa toàn bộ bảng.”** Thông thường nó khóa các hàng/index resources được truy vấn chọn hoặc quét theo semantics của engine; không mặc định khóa cả bảng.
- **“FOR UPDATE luôn đọc phiên bản mới nhất trong mọi isolation level.”** Không đúng. Snapshot cố định có thể dẫn đến serialization error hoặc quy tắc khác sau khi chờ.
- **“Mở transaction là đủ để giữ khóa đọc.”** Không đúng. Một SELECT thường có thể nhả shared lock ngay khi statement kết thúc; cần locking read hoặc isolation semantics phù hợp.
- **“Khóa hàng đã tồn tại bảo vệ cả hàng chưa được insert.”** Không đúng nói chung. Muốn bảo vệ khoảng/predicate cần range/gap/predicate lock, unique/exclusion constraint hoặc Serializable.
- **“Dùng FOR UPDATE cho mọi SELECT sẽ an toàn hơn.”** Không đúng. Khóa không cần thiết làm giảm throughput và tăng deadlock.
- **“Nếu SELECT không bị chặn thì database không dùng khóa.”** Không đúng. Có thể truy vấn đang đọc row version trong khi writer vẫn dùng khóa ghi.
- **“Hai engine cùng tên READ COMMITTED có hành vi giống hệt nhau.”** Không đúng. SQL Server có thể dùng locking hoặc RCSI; PostgreSQL và InnoDB có semantics riêng.

## 17. Quy trình chọn SELECT thường hay SELECT kèm khóa

Khi viết một truy vấn đọc, hãy xác định mục đích trước:

1. Chỉ cần hiển thị hoặc phân tích dữ liệu nhất quán? Dùng `SELECT` thường theo isolation level phù hợp.
2. Đọc xong sẽ cập nhật chính hàng đó và cần ngăn writer khác thay đổi trước khi commit? Cân nhắc locking read.
3. Nhiều transaction cùng đọc rồi cập nhật? Nếu chắc chắn sẽ ghi, cân nhắc xin khóa cập nhật ngay từ đầu để tránh conversion deadlock.
4. Cần bảo vệ một khoảng hoặc điều kiện “chưa có hàng”? Kiểm tra range/predicate locking, unique/exclusion constraint hoặc Serializable; khóa một hàng không tồn tại là không đủ.
5. Cần worker claim các hàng khác nhau? Cân nhắc `SKIP LOCKED` nếu engine hỗ trợ và việc bỏ qua hàng đang khóa phù hợp nghiệp vụ.
6. Muốn thất bại nhanh khi tài nguyên bận? Cân nhắc `NOWAIT` hoặc lock timeout theo hỗ trợ của engine.
7. Các bước đọc/ghi có nằm trong cùng transaction không? Nếu autocommit kết thúc ngay sau locking read, khóa có thể được nhả trước khi ứng dụng cập nhật.
8. Đã kiểm tra hành vi trên đúng engine, isolation level và execution plan chưa? Không suy luận chỉ từ tên SQL.

## 18. Kết luận

`SELECT` thường đọc dữ liệu theo isolation level và có thể dùng MVCC/row versioning để tránh chờ writer; trong cấu hình locking-based, nó cũng có thể lấy shared lock trong thời gian statement. `SELECT` kèm khóa chủ động xin quyền bảo vệ các hàng hoặc phạm vi được truy cập, thường để đọc rồi cập nhật trong cùng transaction. Nó có thể phải chờ transaction khác và làm writer hoặc locking reader khác chờ đến khi commit/rollback.

Thí nghiệm hai phiên giúp quan sát trực tiếp sự khác biệt: khi A cập nhật chưa commit, B có thể đọc phiên bản cũ bằng SELECT thường hoặc chờ tùy engine; khi A giữ `FOR UPDATE`, B thường phải chờ nếu muốn cập nhật cùng hàng. Kết quả cụ thể phụ thuộc PostgreSQL, MySQL InnoDB, SQL Server, isolation level, row-versioning options, index và autocommit. Hãy chọn locking read khi cần bảo vệ quyết định cập nhật, dùng constraint hoặc Serializable cho bất biến rộng hơn, giữ transaction ngắn và xác nhận hành vi bằng công cụ quan sát blocking của hệ quản trị đang chạy.
