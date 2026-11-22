# Cho rằng REPEATABLE READ có hành vi giống nhau trên mọi hệ quản trị

Một lỗi thiết kế thường gặp là thấy ứng dụng đặt isolation level thành `REPEATABLE READ`, rồi giả định transaction sẽ có cùng cách đọc dữ liệu, khóa hàng và ngăn phantom trên mọi database. Tên isolation level giống nhau không có nghĩa cách triển khai giống nhau. MySQL InnoDB, PostgreSQL, SQL Server và Oracle dùng các cơ chế khác nhau để tạo tính nhất quán khi đọc và phối hợp ghi đồng thời.

Điểm khác biệt quan trọng nhất là **snapshot isolation và locking-based repeatable read không phải cùng một cơ chế**. Một hệ quản trị có thể giữ snapshot MVCC cho các lần đọc thông thường; hệ khác có thể giữ shared lock trên hàng đã đọc đến cuối transaction. Một số hệ bảo vệ range bằng next-key hoặc predicate lock; hệ khác cho phép phantom ở `REPEATABLE READ` và chỉ ngăn nó ở `SERIALIZABLE`.

Vì vậy, không thể chỉ dựa vào tên `REPEATABLE READ` để kết luận:

- Hai lần đọc cùng một predicate chắc chắn thấy cùng tập hàng.
- Một transaction đọc hàng sẽ chặn transaction khác cập nhật hàng đó.
- Phantom insert luôn bị ngăn.
- Không thể xảy ra write skew hoặc serialization anomaly.
- Mọi câu lệnh trong transaction đều đọc cùng một snapshot.

Bài này so sánh MySQL InnoDB, PostgreSQL, SQL Server và Oracle, giải thích các tình huống dễ nhầm và đưa ra cách kiểm chứng trên đúng engine đang chạy. Isolation level phải được hiểu theo tài liệu và hành vi cụ thể của từng hệ quản trị, không chỉ theo tên chuẩn SQL.

## 1. Tên isolation level không phải hợp đồng triển khai đầy đủ

SQL định nghĩa các mức cô lập dựa trên những hiện tượng đọc như dirty read, non-repeatable read và phantom read. Mô tả khái quát thường được trình bày như sau:

| Isolation level | Dirty read | Non-repeatable read | Phantom read |
|---|---|---|---|
| `READ UNCOMMITTED` | Có thể | Có thể | Có thể |
| `READ COMMITTED` | Không | Có thể | Có thể |
| `REPEATABLE READ` | Không | Không | Có thể theo mô tả tối thiểu của chuẩn |
| `SERIALIZABLE` | Không | Không | Không |

Bảng này mô tả các bảo đảm tối thiểu theo cách phân loại hiện tượng của chuẩn. Nó không mô tả đầy đủ mọi anomaly có thể xảy ra, cách database lấy khóa, snapshot được tạo lúc nào, hay cách xử lý khi hai transaction cùng ghi.

Hai hệ quản trị có thể cùng công bố `REPEATABLE READ` nhưng:

- Một hệ dùng MVCC snapshot ở cấp transaction cho consistent read.
- Một hệ dùng shared row lock và giữ đến cuối transaction.
- Một hệ ngăn phantom bằng next-key lock trong locking range read.
- Một hệ ngăn phantom trong snapshot read nhưng vẫn cho phép write skew.
- Một hệ không cung cấp isolation level tên `REPEATABLE READ`.

Do đó, khi chuyển ứng dụng giữa database, hãy so sánh **semantics của thao tác cụ thể**: plain `SELECT`, `SELECT ... FOR UPDATE`, `UPDATE`, range predicate, aggregate read, concurrent write và commit conflict.

## 2. Phân biệt các khái niệm dễ bị gọi chung là repeatable read

### Consistent read

Consistent read là thao tác đọc một phiên bản dữ liệu nhất quán theo snapshot hoặc read view. Trong database MVCC, reader có thể nhìn thấy phiên bản đã commit phù hợp với snapshot mà không cần chặn writer bằng shared row lock.

### Locking read

Locking read như `SELECT ... FOR UPDATE` hoặc `SELECT ... FOR SHARE` yêu cầu khóa để phối hợp với transaction ghi. Cách khóa hàng và khoảng phụ thuộc database, index, predicate và isolation level.

### Snapshot isolation

Snapshot isolation cho transaction đọc một snapshot nhất quán của dữ liệu. Nó ngăn một số hiện tượng đọc nhưng không tự động bảo đảm serializability. Hai transaction có thể đọc cùng một trạng thái rồi cập nhật các hàng khác nhau dựa trên cùng giả định; cả hai cùng commit và làm sai một bất biến tổng hợp. Hiện tượng này thường được gọi là write skew.

### Locking-based repeatable read

Một triển khai dùng shared lock giữ trên các hàng đã đọc có thể ngăn transaction khác sửa những hàng đó đến khi reader kết thúc. Nhưng nếu không khóa khoảng key, transaction khác vẫn có thể chèn hàng mới thỏa predicate đã đọc. Đây là lý do `REPEATABLE READ` kiểu lock-based vẫn có thể cho phantom.

## 3. So sánh tổng quan giữa các hệ quản trị

| Hệ quản trị | Mức `REPEATABLE READ` | Cách đọc/khóa nổi bật | Phantom và anomaly cần chú ý |
|---|---|---|---|
| MySQL InnoDB | Mức mặc định thường gặp | Consistent read dùng MVCC read view; locking read/DML dùng current read và record/next-key locking tùy access path | Plain consistent reads lặp lại snapshot; range locking reads ở `REPEATABLE READ` có thể dùng next-key lock; write skew vẫn cần được xem xét |
| PostgreSQL | Snapshot isolation | Plain reads dùng một transaction snapshot; không khóa row chỉ vì `SELECT` thông thường | Tài liệu PostgreSQL mô tả `REPEATABLE READ` ngăn phantom, nhưng vẫn có serialization anomaly như write skew |
| SQL Server | Locking-based repeatable read | Shared lock trên hàng đã đọc được giữ đến cuối transaction; writer có thể bị chặn | Phantom vẫn có thể xảy ra vì không khóa toàn bộ key range; `SERIALIZABLE` dùng key-range lock |
| Oracle Database | Không có mức tên `REPEATABLE READ` | `READ COMMITTED` dùng statement-level read consistency; `SERIALIZABLE` dùng transaction-level snapshot | Không nên ánh xạ trực tiếp tên `REPEATABLE READ`; serializable transaction có thể gặp `ORA-08177` khi ghi xung đột |

Đây là bản đồ định hướng. Chi tiết còn phụ thuộc phiên bản, cấu hình row versioning, kiểu truy vấn và transaction boundary. Không dùng bảng thay cho thử nghiệm trên môi trường đích.

## 4. MySQL InnoDB: REPEATABLE READ kết hợp MVCC và next-key locking

MySQL InnoDB thường dùng `REPEATABLE READ` làm isolation level mặc định. Tuy nhiên, cần tách hai loại thao tác đọc.

### Plain SELECT: consistent read theo read view

Trong transaction `REPEATABLE READ`, consistent read thường dùng read view được tạo ở lần consistent read đầu tiên. Những consistent read tiếp theo trong cùng transaction dùng lại snapshot đó.

```sql
-- Session A
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM accounts
WHERE id = 10;
-- Giả sử thấy 500.
```

```sql
-- Session B
UPDATE accounts
SET balance = 700
WHERE id = 10;
COMMIT;
```

```sql
-- Session A, vẫn trong transaction cũ
SELECT balance
FROM accounts
WHERE id = 10;
-- Consistent read thường vẫn thấy 500.
COMMIT;
```

Plain `SELECT` không lấy shared row lock chỉ vì transaction đang ở `REPEATABLE READ`. MVCC cho phép reader đọc phiên bản cũ trong khi writer cập nhật phiên bản mới.

### Locking read: current read

`SELECT ... FOR UPDATE` và `SELECT ... FOR SHARE` không đơn giản là đọc lại cùng read view. Chúng là locking/current reads, cần làm việc với trạng thái hiện tại và lấy khóa phù hợp.

```sql
-- Session A
START TRANSACTION;

SELECT balance
FROM accounts
WHERE id = 10
FOR UPDATE;
```

Nếu Session B đã cập nhật và commit hàng trước đó, locking read của A có thể thấy phiên bản hiện tại khác với phiên bản mà plain consistent read trước đó của A đã thấy. Việc trộn consistent read và current read trong cùng transaction có thể gây bất ngờ nếu ứng dụng giả định mọi câu `SELECT` đều đọc cùng snapshot.

### Range locking read và next-key lock

InnoDB có thể dùng next-key lock cho range scan ở `REPEATABLE READ`. Next-key lock kết hợp record lock với gap lock trên khoảng trước index record. Điều này giúp ngăn chèn key mới vào khoảng được bảo vệ.

```sql
START TRANSACTION;

SELECT id, amount
FROM orders
WHERE amount >= 100
  AND amount < 200
FOR UPDATE;
```

Phạm vi khóa phụ thuộc index được dùng và vùng scan. Unique equality lookup trên toàn bộ unique key có thể chỉ cần record lock khi tìm thấy hàng; range/non-unique lookup có thể khóa các khoảng rộng hơn. Không suy ra phạm vi khóa chỉ từ số hàng trả về.

### Write skew vẫn có thể xảy ra

Giả sử quy tắc nghiệp vụ là luôn có ít nhất một bác sĩ trực. Hai hàng biểu diễn hai bác sĩ, `on_call = TRUE`. Hai transaction cùng đọc số bác sĩ trực là 2, rồi mỗi transaction tắt một bác sĩ khác nhau:

```sql
-- T1: plain consistent read
SELECT COUNT(*)
FROM doctors
WHERE on_call = TRUE;

-- T2: plain consistent read
SELECT COUNT(*)
FROM doctors
WHERE on_call = TRUE;

-- T1 tắt bác sĩ 1
UPDATE doctors SET on_call = FALSE WHERE id = 1;

-- T2 tắt bác sĩ 2
UPDATE doctors SET on_call = FALSE WHERE id = 2;
```

Nếu cả hai transaction dựa trên cùng snapshot và chỉ ghi hai hàng khác nhau, một số lịch thực thi có thể cho cả hai commit, làm số bác sĩ trực bằng 0. Việc dùng `REPEATABLE READ` không tự biến mọi quy tắc tổng hợp thành một khóa duy nhất.

Để bảo vệ bất biến, có thể dùng một hàng điều phối được khóa, constraint phù hợp, thiết kế dữ liệu khác hoặc isolation `SERIALIZABLE` với xử lý retry. Chỉ thêm `FOR UPDATE` vào một câu đọc aggregate không phải lúc nào cũng khóa được mọi hàng tương lai thỏa predicate.

## 5. PostgreSQL: REPEATABLE READ là snapshot isolation

PostgreSQL triển khai `REPEATABLE READ` theo snapshot isolation. Snapshot của transaction được thiết lập ở câu lệnh đầu tiên không phải transaction-control statement; các câu đọc sau đó dùng cùng snapshot.

```sql
-- Session A
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM accounts
WHERE id = 10;
-- Giả sử thấy 500.
```

```sql
-- Session B
UPDATE accounts
SET balance = 700
WHERE id = 10;
COMMIT;
```

```sql
-- Session A
SELECT balance
FROM accounts
WHERE id = 10;
-- Vẫn thấy phiên bản trong snapshot của A.
COMMIT;
```

Plain `SELECT` không lấy row lock. Reader và writer thường không chặn nhau chỉ vì reader đang đọc hàng; MVCC cho phép đọc phiên bản phù hợp với snapshot.

### PostgreSQL REPEATABLE READ ngăn phantom read nhưng không phải SERIALIZABLE

Theo semantics PostgreSQL, cùng transaction snapshot ngăn một transaction thấy các hàng được transaction khác commit sau khi snapshot được thiết lập, kể cả hàng mới thỏa predicate. Vì thế PostgreSQL `REPEATABLE READ` ngăn phantom read theo định nghĩa hiện tượng chuẩn.

Tuy vậy, snapshot isolation vẫn có thể cho write skew hoặc anomaly khác không được mô tả chỉ bằng dirty/non-repeatable/phantom reads. Vì vậy, không được kết luận rằng PostgreSQL `REPEATABLE READ` tương đương `SERIALIZABLE`.

### Concurrent update cùng một hàng

Nếu transaction ở `REPEATABLE READ` cố cập nhật một hàng đã bị transaction khác thay đổi kể từ khi snapshot của nó bắt đầu, PostgreSQL thường hủy transaction với lỗi serialization (`SQLSTATE 40001`) thay vì âm thầm cập nhật dựa trên phiên bản cũ.

Ứng dụng phải rollback và retry toàn bộ transaction trong transaction mới. Retry riêng câu `UPDATE` trong transaction đã bị đánh dấu lỗi không có tác dụng.

### SERIALIZABLE dùng SSI

PostgreSQL `SERIALIZABLE` sử dụng Serializable Snapshot Isolation (SSI). Cơ chế này theo dõi dependency nguy hiểm giữa các transaction và có thể hủy một transaction để bảo đảm kết quả tương đương một thứ tự tuần tự. Nó không đơn giản khóa tất cả hàng được đọc bằng shared lock.

Predicate/SIREAD locks của SSI phục vụ phát hiện dependency; chúng không hoạt động giống row lock thông thường và không nhất thiết chặn writer ngay khi đọc. Transaction có thể bị serialization failure ở thời điểm statement hoặc commit, nên ứng dụng phải có retry toàn transaction.

## 6. SQL Server: REPEATABLE READ giữ shared lock trên hàng đã đọc

SQL Server `REPEATABLE READ` chủ yếu là locking-based. Khi transaction đọc một hàng, shared lock được giữ đến khi transaction kết thúc. Điều này ngăn transaction khác cập nhật hoặc xóa hàng đó trước khi reader commit/rollback.

```sql
-- Session A
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
BEGIN TRANSACTION;

SELECT balance
FROM dbo.accounts
WHERE id = 10;
-- Shared lock trên hàng đọc được giữ đến cuối transaction.
```

```sql
-- Session B
UPDATE dbo.accounts
SET balance = 700
WHERE id = 10;
-- Có thể phải chờ shared lock của A.
```

Khác với MVCC consistent read của MySQL/PostgreSQL, plain read trong SQL Server `REPEATABLE READ` có thể trực tiếp chặn writer trên hàng đã đọc. Điều này ảnh hưởng đến blocking và thời gian giữ khóa.

### Phantom vẫn có thể xuất hiện

`REPEATABLE READ` giữ khóa trên các hàng đã đọc nhưng không khóa toàn bộ key range. Transaction khác có thể chèn một hàng mới thỏa predicate giữa hai lần đọc.

```sql
-- Session A
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
BEGIN TRANSACTION;

SELECT id
FROM dbo.orders
WHERE status = 'PENDING';

-- Session B chèn một order PENDING mới và commit.

-- Session A đọc lại có thể thấy hàng mới.
SELECT id
FROM dbo.orders
WHERE status = 'PENDING';

COMMIT;
```

Muốn bảo vệ key range khỏi phantom, SQL Server dùng `SERIALIZABLE`, thường thông qua key-range locks khi access path và index cho phép. Điều kiện index và execution plan vẫn quan trọng vì chúng xác định range được khóa.

### Đừng nhầm REPEATABLE READ với SNAPSHOT hoặc RCSI

SQL Server có các lựa chọn row-versioning riêng:

- `READ_COMMITTED_SNAPSHOT` (RCSI) thay đổi hành vi `READ COMMITTED` để mỗi statement đọc một snapshot nhất quán thay vì dùng shared lock thông thường cho dữ liệu row-versioned.
- `SNAPSHOT` cung cấp snapshot ở cấp transaction; cần bật `ALLOW_SNAPSHOT_ISOLATION` cho database.
- `REPEATABLE READ` vẫn là mức locking-based; shared lock trên hàng đã đọc được giữ đến transaction end.

Ví dụ bật snapshot isolation ở database là thao tác quản trị cần được đánh giá và thực hiện theo quy trình vận hành:

```sql
ALTER DATABASE YourDatabase
SET ALLOW_SNAPSHOT_ISOLATION ON;
```

Sau đó session có thể dùng:

```sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
BEGIN TRANSACTION;
-- consistent snapshot ở cấp transaction
COMMIT;
```

Không dùng `REPEATABLE READ` như tên thay thế cho `SNAPSHOT`. Chúng có blocking và conflict behavior khác nhau.

## 7. Oracle: không có isolation level tên REPEATABLE READ

Oracle Database không cung cấp mức cô lập tên `REPEATABLE READ` theo bộ tên quen thuộc của MySQL/PostgreSQL/SQL Server. Hai mức thường dùng là:

- `READ COMMITTED`: mỗi câu SQL đọc một snapshot nhất quán tại thời điểm statement bắt đầu.
- `SERIALIZABLE`: transaction đọc theo snapshot được thiết lập ở đầu transaction và phải thỏa điều kiện serializable; xung đột ghi có thể dẫn đến `ORA-08177: cannot serialize access for this transaction`.

Oracle cũng hỗ trợ read-only transaction trong những trường hợp phù hợp. Không nên ánh xạ `READ COMMITTED` của Oracle sang `REPEATABLE READ` của hệ khác chỉ vì ứng dụng muốn đọc lặp lại cùng snapshot.

### READ COMMITTED: statement-level consistency

```sql
-- Transaction A
SELECT balance
FROM accounts
WHERE id = 10;

-- Transaction B cập nhật và commit.

-- Transaction A chạy câu SELECT mới và có thể thấy giá trị mới.
SELECT balance
FROM accounts
WHERE id = 10;
```

Mỗi statement có read-consistent view riêng. Reader thường không chặn writer chỉ vì thực hiện plain `SELECT`, nhờ multi-version read consistency.

### SERIALIZABLE: transaction-level consistency

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM accounts
WHERE id = 10;

-- Các câu đọc tiếp theo dùng transaction snapshot.
-- Ghi xung đột có thể khiến transaction nhận ORA-08177.

COMMIT;
```

Khi gặp `ORA-08177`, ứng dụng cần rollback và quyết định retry toàn bộ transaction theo chính sách. Không xử lý như một lock wait timeout thông thường.

## 8. Ví dụ phantom cho thấy cùng tên có hành vi khác

Giả sử có index trên `orders(status)` và Session A mở transaction, đọc tất cả đơn hàng `PENDING`. Session B chèn một đơn hàng `PENDING` mới rồi commit. Session A đọc lại cùng predicate.

| Hệ quản trị/mức | Hành vi plain read điển hình |
|---|---|
| MySQL InnoDB `REPEATABLE READ` | Consistent read thường dùng cùng read view, nên không thấy hàng commit sau snapshot. Locking range read có thể dùng next-key lock để chặn insert trong vùng khóa. |
| PostgreSQL `REPEATABLE READ` | Cùng transaction snapshot; không thấy hàng được commit sau khi snapshot được thiết lập. |
| SQL Server `REPEATABLE READ` | Shared lock giữ trên hàng đã đọc, nhưng phantom insert có thể xuất hiện vì key range chưa được khóa. |
| Oracle `READ COMMITTED` | Đây không phải mức RR; mỗi statement có snapshot mới nên câu SELECT sau có thể thấy hàng mới. Oracle `SERIALIZABLE` dùng transaction snapshot. |

Sự khác biệt này có thể làm test chạy tốt trên một engine nhưng thất bại hoặc block khác trên engine khác. Khi chuyển database, test phải kiểm tra đúng semantics mà nghiệp vụ cần, không chỉ kiểm tra tên cấu hình.

## 9. Ví dụ write skew: snapshot lặp lại không đồng nghĩa serializable

Xét quy tắc: trong mỗi ca phải có ít nhất một bác sĩ trực. Hai bác sĩ A và B đều đang trực. Hai transaction đồng thời:

1. Đọc số bác sĩ đang trực và thấy 2.
2. T1 quyết định tắt A vì B vẫn trực.
3. T2 quyết định tắt B vì A vẫn trực.
4. Cả hai cập nhật hai hàng khác nhau.

```text
T1                                      T2
--                                      --
SELECT COUNT(on_call) = 2               SELECT COUNT(on_call) = 2
UPDATE doctor A -> off                  UPDATE doctor B -> off
COMMIT                                  COMMIT

Kết quả: A=off, B=off
Vi phạm: không còn bác sĩ trực
```

Snapshot isolation có thể cho phép cả hai transaction commit vì chúng không ghi đè cùng một hàng. PostgreSQL `REPEATABLE READ` là ví dụ nổi bật của snapshot isolation vẫn cho write skew. InnoDB `REPEATABLE READ` cũng cần được đánh giá với kiểu consistent read và các câu ghi thực tế; không dựa vào snapshot lặp lại để bảo vệ một predicate tổng hợp.

Trong SQL Server lock-based `REPEATABLE READ`, shared lock trên các hàng đọc được có thể làm các transaction chặn nhau hoặc tạo deadlock khi nâng cấp khóa; nhưng phantom vẫn là vấn đề nếu predicate range không được khóa. Hành vi cuối cùng phụ thuộc access path, khóa và thứ tự cập nhật.

Các cách bảo vệ bất biến:

- Dùng một hàng guard/counter đại diện cho quy tắc và khóa nó trước khi quyết định.
- Dùng constraint hoặc schema biểu diễn bất biến trực tiếp nếu có thể.
- Khóa rõ ràng toàn bộ tập hàng cần xét bằng access path phù hợp.
- Dùng `SERIALIZABLE` và xử lý serialization/deadlock retry.
- Thiết kế thao tác nguyên tử để database kiểm tra điều kiện trong cùng câu lệnh.

Không chọn giải pháp chỉ dựa vào tên isolation level; kiểm thử lại với đúng engine.

## 10. Bảng so sánh chi tiết các hành vi

| Hành vi | MySQL InnoDB RR | PostgreSQL RR | SQL Server RR | Oracle |
|---|---|---|---|---|
| Cơ chế plain read | MVCC consistent read | MVCC snapshot | Shared locks trên hàng đọc | MVCC statement snapshot ở RC; transaction snapshot ở Serializable |
| Hai plain SELECT cùng transaction | Thường cùng read view | Cùng transaction snapshot | Đọc lại hàng đã khóa; không có transaction snapshot tổng quát | RC có thể thấy trạng thái mới giữa statements; Serializable giữ snapshot |
| Plain SELECT có chặn writer trên hàng đã đọc? | Thường không | Thường không | Có thể, shared lock được giữ | Thường không |
| Phantom trong plain repeatable read | Consistent snapshot không thấy commit sau snapshot | Không thấy commit sau snapshot | Có thể xuất hiện | Không có mức RR; RC statement snapshot có thể thấy ở câu sau |
| Range locking | Next-key/gap lock theo access path ở RR | Plain read không khóa range; SSI dùng predicate tracking ở Serializable | Key-range lock đầy đủ ở Serializable, không phải RR | Dùng cơ chế MVCC/locking riêng; không có tên RR |
| Concurrent update cùng hàng | Current read/lock conflict; kết quả phụ thuộc lịch và câu lệnh | Có thể serialization failure nếu hàng đã đổi sau snapshot | Thường chặn theo lock; có thể deadlock/timeout | Có thể chặn hoặc gặp serialization conflict ở Serializable |
| Write skew | Có thể nếu dựa trên snapshot read và ghi các hàng khác nhau | Có thể ở RR; Serializable SSI phát hiện | Cần phân tích lock/predicate; RR không khóa range đầy đủ | Serializable nhằm bảo đảm thứ tự tuần tự, có thể ORA-08177 |
| Retry cần thiết | Deadlock/timeout và conflict theo thao tác | `40001`, `40P01` | Deadlock victim `1205`, timeout theo chính sách | `ORA-08177` và lỗi tạm thời phù hợp |

Bảng là hướng dẫn so sánh, không phải thay thế tài liệu từng phiên bản. Đặc biệt, “plain read có chặn writer không” phải xét cấu hình row-versioning của SQL Server và kiểu statement cụ thể.

## 11. Isolation level không quyết định mọi thứ một mình

Ngay trong cùng một database, kết quả có thể đổi theo:

- **Autocommit:** mỗi statement có transaction riêng hay nhiều câu lệnh dùng chung transaction.
- **Loại read:** consistent read hay locking/current read.
- **Index:** equality lookup trên unique key hay range scan trên non-unique index.
- **Execution plan:** index scan, table scan, join order, predicate pushdown và sort.
- **Constraint/trigger:** foreign key, unique check, trigger hoặc cascade có thể lấy khóa bổ sung.
- **Session settings:** row versioning, timeout, lock hints và read-only mode.
- **Transaction boundary:** thời điểm snapshot được tạo và thời điểm commit/rollback.

Ví dụ trong InnoDB, plain `SELECT` ở `REPEATABLE READ` dùng read view, trong khi `SELECT ... FOR UPDATE` là current read. Trong SQL Server, bật RCSI làm `READ COMMITTED` có row-versioning semantics, nhưng không biến `REPEATABLE READ` thành `SNAPSHOT`. Trong PostgreSQL, `SERIALIZABLE` dùng SSI chứ không đơn giản giữ shared row locks cho mọi plain read.

## 12. Kiểm tra isolation level thực tế của session

Không dựa vào cấu hình mặc định hoặc cấu hình trong file application. Connection pool, transaction manager và câu lệnh session có thể thay đổi isolation level.

### MySQL

```sql
SELECT
    @@version AS server_version,
    @@session.transaction_isolation AS isolation_level,
    @@session.autocommit AS autocommit_mode,
    CONNECTION_ID() AS connection_id;
```

### PostgreSQL

```sql
SELECT
    version(),
    current_setting('transaction_isolation') AS isolation_level,
    current_setting('transaction_read_only') AS read_only,
    pg_backend_pid() AS backend_pid;
```

### SQL Server

```sql
SELECT
    @@VERSION AS server_version,
    SESSIONPROPERTY('TRANSACTION ISOLATION LEVEL') AS isolation_level_code,
    @@SPID AS session_id;
```

Có thể đối chiếu isolation level với DMV và session state phù hợp phiên bản. Nếu database bật `READ_COMMITTED_SNAPSHOT`, cũng cần kiểm tra cấu hình ở cấp database vì nó làm thay đổi hành vi `READ COMMITTED`.

### Oracle

Oracle không có session isolation setting tên `REPEATABLE READ`. Kiểm tra mức transaction đang dùng trong code và các lệnh `SET TRANSACTION`; xem session/database parameters liên quan đến read consistency nếu cần. Không dịch một cấu hình JDBC `TRANSACTION_REPEATABLE_READ` thành giả định Oracle hỗ trợ cùng semantics; driver/provider có thể từ chối hoặc ánh xạ theo khả năng database.

## 13. Kiểm thử cùng một kịch bản trên nhiều hệ quản trị

Một bài test portable cần định nghĩa **kết quả nghiệp vụ mong muốn**, rồi triển khai lịch thực thi và truy vấn quan sát riêng cho từng engine.

### Kịch bản A: non-repeatable read

1. T1 bắt đầu transaction và đọc `balance`.
2. T2 cập nhật cùng hàng rồi commit.
3. T1 đọc lại cùng hàng.
4. Ghi lại hai giá trị T1 quan sát được.

Kỳ vọng cần ghi theo engine và mức cô lập. PostgreSQL RR và InnoDB RR consistent reads thường giữ snapshot; SQL Server RR giữ shared lock nên T2 có thể chờ cho đến khi T1 kết thúc; Oracle READ COMMITTED có thể thấy giá trị mới ở statement thứ hai.

### Kịch bản B: phantom insert

1. T1 đọc `WHERE status = 'PENDING'`.
2. T2 chèn một hàng mới có `status = 'PENDING'` và commit.
3. T1 đọc lại predicate.

Ghi lại hàng mới có xuất hiện hay không, T2 có bị block không và index/range nào được dùng. SQL Server RR có thể cho phantom; SQL Server SERIALIZABLE dùng key-range locking. PostgreSQL RR và InnoDB RR plain consistent reads dùng snapshot; InnoDB locking range read có thể dùng next-key locks.

### Kịch bản C: write skew

1. T1 và T2 cùng đọc điều kiện tổng hợp.
2. Mỗi transaction cập nhật một hàng khác nhau.
3. Cả hai commit nếu database cho phép.
4. Kiểm tra bất biến tổng hợp sau commit.

Không chỉ kiểm tra exception. Nếu cả hai commit mà bất biến sai, test đã tìm thấy anomaly dù không có deadlock.

## 14. Lưu ý khi viết test hai session

Để so sánh công bằng:

1. Dùng cùng schema logic và fixture tương đương.
2. Ghi phiên bản chính xác của từng database.
3. Đặt isolation level rõ ràng ở từng connection.
4. Ghi autocommit và transaction boundary.
5. Dùng barrier thay vì `sleep()` để điều phối thứ tự.
6. Lưu query plan và index được chọn trên từng engine.
7. Ghi thời điểm bắt đầu/kết thúc và connection ID/PID.
8. Thu lock/wait telemetry bằng công cụ riêng của từng hệ quản trị.
9. Kiểm tra cả kết quả trả về lẫn trạng thái dữ liệu cuối.
10. Reset fixture giữa các lần chạy.

Không ép tất cả database dùng cùng một index hoặc cùng một hint nếu cấu trúc vật lý khác nhau. Mục tiêu là so sánh semantics nghiệp vụ, đồng thời ghi lại cách mỗi engine thực hiện.

## 15. Lỗi khi chuyển ứng dụng giữa các database

### Giả định plain SELECT luôn không chặn writer

Điều này thường đúng với MVCC consistent read của InnoDB/PostgreSQL và Oracle read consistency, nhưng SQL Server locking-based `REPEATABLE READ` có thể giữ shared lock trên hàng đã đọc. Một luồng đọc dài có thể làm writer chờ.

### Giả định REPEATABLE READ luôn khóa range

SQL Server `REPEATABLE READ` không tương đương `SERIALIZABLE`; phantom insert vẫn có thể xảy ra. InnoDB next-key locking phụ thuộc locking read/DML và access path; plain consistent read không lấy next-key lock chỉ vì ở RR.

### Giả định snapshot isolation là serializable

PostgreSQL RR giữ snapshot và ngăn phantom, nhưng write skew vẫn có thể xảy ra. Snapshot lặp lại không đủ để bảo vệ mọi bất biến tổng hợp.

### Ánh xạ tên isolation qua JDBC mà không kiểm tra driver

JDBC định nghĩa hằng `TRANSACTION_REPEATABLE_READ`, nhưng database/driver quyết định mức hỗ trợ và semantics thực tế. Một framework có thể gửi lệnh isolation tương ứng, từ chối hoặc ánh xạ khác theo dialect. Kiểm tra session setting sau khi transaction bắt đầu và chạy integration test trên database đích.

### Chỉ kiểm thử một engine trong CI

Nếu sản phẩm hỗ trợ nhiều database, một test pass trên MySQL không chứng minh PostgreSQL hoặc SQL Server có cùng behavior. Chạy test matrix với đúng engine/version và lưu kết quả riêng.

## 16. Chọn mức cô lập theo bất biến nghiệp vụ

Đừng chọn isolation level chỉ vì muốn “đọc ổn định”. Hãy xác định bất biến cần bảo vệ:

- Nếu chỉ cần đọc một snapshot nhất quán để tạo báo cáo, snapshot transaction hoặc read-only transaction có thể phù hợp.
- Nếu cập nhật một hàng dựa trên giá trị hiện tại, dùng atomic `UPDATE` với điều kiện trong SQL, optimistic version hoặc locking read phù hợp.
- Nếu cần ngăn insert vào một range, xác định predicate/index và cơ chế range locking của engine; `REPEATABLE READ` không có cùng semantics ở mọi nơi.
- Nếu cần bảo vệ quy tắc tổng hợp qua nhiều hàng, dùng constraint/guard row hoặc serializable semantics có retry thay vì chỉ dựa vào repeatable reads.
- Nếu chấp nhận eventual consistency, cân nhắc thiết kế nghiệp vụ theo event/version thay vì giữ transaction dài.

Isolation level cao hơn thường có chi phí contention, retry hoặc rollback khác nhau. `SERIALIZABLE` không phải lựa chọn miễn phí; cần đo throughput, tỷ lệ abort và latency dưới tải đại diện.

## 17. Bảng chọn cách bảo vệ theo tình huống

| Nhu cầu | Cơ chế nên đánh giá | Điều phải kiểm tra |
|---|---|---|
| Đọc cùng snapshot trong nhiều câu | Transaction-level snapshot/MVCC phù hợp | Snapshot bắt đầu lúc nào; transaction có giữ snapshot quá lâu không |
| Ngăn người khác sửa một hàng đang xử lý | `SELECT ... FOR UPDATE` hoặc cơ chế khóa tương ứng | Lock scope, wait, timeout và autocommit |
| Ngăn cập nhật dựa trên version cũ | Optimistic locking với `WHERE version = ?` | affected rows và retry/reload |
| Ngăn phantom trong range | Serializable/key-range/next-key/predicate protection theo engine | Index/access path và loại read |
| Bảo vệ invariant tổng hợp | Serializable hoặc guard/constraint/schema design | Write skew, serialization failure và retry toàn transaction |
| Tăng thông lượng đọc mà không chặn writer | MVCC/RCSI/snapshot phù hợp | Version store/undo retention và semantics snapshot |

Không có một câu lệnh SQL portable duy nhất cho tất cả các trường hợp. Cần chọn theo engine và xác minh bằng test đồng thời.

## 18. Quy trình rà soát trước khi tin vào REPEATABLE READ

1. Xác định database engine và phiên bản chính xác.
2. Đọc tài liệu isolation level của engine, không dựa vào tên trong JDBC.
3. Kiểm tra isolation level và autocommit thực tế trên connection được ứng dụng sử dụng.
4. Phân loại thao tác là plain consistent read, locking read hay DML.
5. Xác định snapshot được tạo ở thời điểm nào và tồn tại đến đâu.
6. Kiểm tra index/access path của predicate và range.
7. Xác định phantom có thể xảy ra trong loại read đang dùng không.
8. Kiểm tra write skew và các bất biến tổng hợp qua nhiều hàng.
9. Xác định lỗi có thể xảy ra: deadlock, lock timeout, serialization failure hoặc `ORA-08177`.
10. Thiết kế retry toàn transaction nếu engine có thể hủy transaction do xung đột.
11. Chạy test hai session có barrier và kiểm tra dữ liệu cuối.
12. Chạy lại test trên mọi database/version được hỗ trợ.

## 19. Tự kiểm tra

**Hai hệ quản trị cùng báo `REPEATABLE READ` có chắc cùng ngăn phantom không?**

Không. PostgreSQL dùng transaction snapshot và ngăn phantom trong RR; SQL Server RR giữ shared lock trên hàng đã đọc nhưng có thể cho insert phantom vì không khóa toàn bộ key range. InnoDB có consistent read snapshot và next-key locking cho một số locking range read. Cần kiểm tra loại read và engine.

**MySQL InnoDB plain SELECT và SELECT FOR UPDATE ở RR có cùng snapshot behavior không?**

Không. Plain SELECT thường là consistent read theo read view; `FOR UPDATE` là locking/current read và làm việc với dữ liệu hiện tại cùng khóa phù hợp.

**PostgreSQL REPEATABLE READ có đồng nghĩa SERIALIZABLE không?**

Không. PostgreSQL RR là snapshot isolation, ngăn phantom nhưng vẫn có thể xảy ra write skew/serialization anomaly. SERIALIZABLE dùng SSI để phát hiện dependency nguy hiểm và có thể hủy transaction.

**SQL Server REPEATABLE READ có ngăn phantom không?**

Không bảo đảm. Nó giữ shared lock trên các hàng đã đọc, nhưng phantom insert có thể xuất hiện. SERIALIZABLE dùng key-range locks để bảo vệ predicate range.

**Oracle có mức REPEATABLE READ không?**

Không có mức isolation mang tên đó. Oracle cung cấp READ COMMITTED với statement-level consistency và SERIALIZABLE với transaction-level snapshot, cùng read-only transaction trong trường hợp phù hợp.

**Vì sao write skew có thể xảy ra dù hai lần đọc đều lặp lại cùng snapshot?**

Vì hai transaction có thể đọc cùng điều kiện tổng hợp rồi ghi các hàng khác nhau. Không có xung đột ghi trực tiếp trên cùng hàng, nhưng kết hợp hai thay đổi có thể vi phạm bất biến.

**Khi JDBC đặt `TRANSACTION_REPEATABLE_READ`, có thể bỏ qua kiểm thử trên database đích không?**

Không. Hằng JDBC chỉ yêu cầu mức tương ứng mà driver/database hỗ trợ; semantics cụ thể và cấu hình session vẫn phụ thuộc engine. Cần kiểm tra cấu hình thực tế và chạy integration test.

`REPEATABLE READ` là tên một mức cô lập, không phải cam kết rằng mọi database dùng cùng thuật toán. Hãy xác định **snapshot hay lock, plain read hay locking read, row hay range, và anomaly nào còn có thể xảy ra** trên đúng engine. Khi chuyển database hoặc thay đổi driver, isolation level, index hay transaction boundary, hãy kiểm chứng lại bằng lịch hai session và bất biến nghiệp vụ; chỉ như vậy ứng dụng mới dựa trên semantics thực tế thay vì một giả định từ tên cấu hình.
