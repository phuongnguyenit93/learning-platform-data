# Tái hiện đọc bẩn, đọc không lặp lại và bóng ma bằng hai phiên SQL Server

Thực nghiệm hai phiên giúp nhìn thấy trực tiếp cách mức cô lập giao dịch điều khiển những gì một câu truy vấn có thể đọc khi giao dịch khác đang ghi. Trong SQL Server, có thể tái hiện ba hiện tượng thường gặp:

- **Đọc bẩn (dirty read):** đọc giá trị mà giao dịch ghi chưa commit; giao dịch ghi sau đó có thể rollback.
- **Đọc không lặp lại (non-repeatable read):** cùng một hàng được đọc hai lần trong một transaction nhưng nhận hai giá trị khác nhau vì giao dịch khác đã commit cập nhật ở giữa.
- **Đọc bóng ma (phantom read):** cùng một điều kiện truy vấn được chạy hai lần nhưng tập hàng hoặc số lượng hàng thay đổi vì giao dịch khác đã chèn hoặc xóa hàng phù hợp ở giữa.

Các ví dụ dưới đây dùng SQL Server Management Studio (SSMS) hoặc công cụ SQL tương đương. Mở **hai query window riêng**, kết nối cùng một SQL Server instance và cùng một database. Chạy phần chuẩn bị một lần, sau đó thực hiện từng bài theo đúng thứ tự. Trong mỗi bài, Session A giữ transaction và có `WAITFOR`; hãy chạy câu lệnh ở Session B trong lúc Session A đang chờ.

## 1. Chuẩn bị môi trường thực nghiệm

Chọn một database thử nghiệm mà bạn có quyền tạo bảng. Ví dụ:

```sql
USE YourTestDatabase;
GO

-- Bảng dùng cho dirty read và non-repeatable read.
IF OBJECT_ID(N'dbo.IsolationLabAccount', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.IsolationLabAccount
    (
        AccountId INT NOT NULL
            CONSTRAINT PK_IsolationLabAccount PRIMARY KEY,
        Balance DECIMAL(12, 2) NOT NULL
    );
END;
GO

IF NOT EXISTS
(
    SELECT 1
    FROM dbo.IsolationLabAccount
    WHERE AccountId = 1
)
BEGIN
    INSERT INTO dbo.IsolationLabAccount (AccountId, Balance)
    VALUES (1, 1000.00);
END;
GO

-- Bảng dùng cho phantom read.
IF OBJECT_ID(N'dbo.IsolationLabSlot', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.IsolationLabSlot
    (
        SlotId INT IDENTITY(1, 1) NOT NULL
            CONSTRAINT PK_IsolationLabSlot PRIMARY KEY,
        RoomId INT NOT NULL,
        SlotNo INT NOT NULL,
        Label NVARCHAR(50) NULL
    );
END;
GO

IF NOT EXISTS
(
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.IsolationLabSlot')
      AND name = N'IX_IsolationLabSlot_Room_Slot'
)
BEGIN
    CREATE INDEX IX_IsolationLabSlot_Room_Slot
        ON dbo.IsolationLabSlot (RoomId, SlotNo);
END;
GO

IF NOT EXISTS
(
    SELECT 1
    FROM dbo.IsolationLabSlot
    WHERE RoomId = 1 AND SlotNo = 10
)
    INSERT INTO dbo.IsolationLabSlot (RoomId, SlotNo, Label)
    VALUES (1, 10, N'Ghế 10');

IF NOT EXISTS
(
    SELECT 1
    FROM dbo.IsolationLabSlot
    WHERE RoomId = 1 AND SlotNo = 20
)
    INSERT INTO dbo.IsolationLabSlot (RoomId, SlotNo, Label)
    VALUES (1, 20, N'Ghế 20');
GO

-- Kiểm tra cấu hình isolation của database đang dùng.
SELECT
    name,
    is_read_committed_snapshot_on,
    snapshot_isolation_state_desc
FROM sys.databases
WHERE database_id = DB_ID();
GO
```

Thay `YourTestDatabase` bằng tên database thử nghiệm. Bảng `IsolationLabSlot` có chỉ mục `(RoomId, SlotNo)` để SQL Server có thể tìm một khoảng khóa cụ thể trong bài phantom. Chỉ mục này đặc biệt quan trọng khi quan sát `SERIALIZABLE` và key-range lock.

Kết quả kiểm tra cấu hình:

- `is_read_committed_snapshot_on = 0`: `READ COMMITTED` thường dùng shared lock khi đọc.
- `is_read_committed_snapshot_on = 1`: `READ COMMITTED` dùng row versioning ở mức statement (RCSI).
- `snapshot_isolation_state_desc = ON`: có thể dùng mức `SNAPSHOT` nếu tài khoản và session đáp ứng các điều kiện.

Không bật hoặc tắt các tùy chọn isolation ở database dùng chung chỉ để làm bài thực hành. Các lệnh thay đổi cấu hình database được nêu ở phần tùy chọn; chỉ chạy trong database thử nghiệm và khi được phép.

## 2. Quy tắc chạy hai phiên

Trong mỗi bài:

1. Dán và chạy script **Session A** trước. Script A mở transaction, thực hiện lần đọc hoặc ghi đầu tiên rồi chờ 20 giây bằng `WAITFOR DELAY`.
2. Trong lúc A đang chờ, chuyển sang cửa sổ **Session B** và chạy script B.
3. Quan sát B chạy ngay hay phải chờ, sau đó quay lại A để xem kết quả lần đọc tiếp theo.
4. Nếu không kịp chạy B trong 20 giây, chạy lại A. Có thể tăng khoảng `WAITFOR` lên 30 hoặc 60 giây.

Mỗi cửa sổ phải là một connection riêng. Hai tab dùng cùng một connection không tạo ra hai transaction session độc lập. Cũng cần chạy cả hai cửa sổ trên cùng database và cùng SQL Server instance.

## 3. Thí nghiệm 1: tái hiện dirty read

Mục tiêu là để Session B đọc một giá trị chưa commit của Session A. Sau đó A rollback, chứng minh giá trị B đã đọc chưa từng trở thành dữ liệu đã commit.

Trước khi bắt đầu, bảo đảm số dư ban đầu là `1000.00`:

```sql
UPDATE dbo.IsolationLabAccount
SET Balance = 1000.00
WHERE AccountId = 1;
```

### Session A — ghi nhưng chưa commit

Chạy trong cửa sổ A:

```sql
USE YourTestDatabase;
GO
SET NOCOUNT ON;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

BEGIN TRANSACTION;

UPDATE dbo.IsolationLabAccount
SET Balance = 500.00
WHERE AccountId = 1;

SELECT N'Session A: giá trị chưa commit' AS Message,
       AccountId, Balance
FROM dbo.IsolationLabAccount
WHERE AccountId = 1;

-- Chuyển sang Session B trong khoảng chờ này.
WAITFOR DELAY '00:00:20';

ROLLBACK TRANSACTION;

SELECT N'Session A: giá trị sau ROLLBACK' AS Message,
       AccountId, Balance
FROM dbo.IsolationLabAccount
WHERE AccountId = 1;
```

Trong 20 giây, A đang giữ transaction mở và giá trị `500.00` chưa commit. A sẽ rollback sau khi hết thời gian chờ.

### Session B — đọc bằng READ UNCOMMITTED

Chạy trong cửa sổ B khi A đang `WAITFOR`:

```sql
USE YourTestDatabase;
GO
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

SELECT N'Session B: đọc trong khi A chưa commit' AS Message,
       AccountId, Balance
FROM dbo.IsolationLabAccount
WHERE AccountId = 1;
```

**Kết quả mong đợi:**

- B có thể đọc được `500.00` ngay cả khi A chưa commit.
- Sau đó A chạy `ROLLBACK`; giá trị đã lưu trở về `1000.00`.
- B đã đọc một giá trị không bao giờ được commit. Đây là dirty read.

Để so sánh, chạy lại phần A nhưng ở Session B dùng `READ COMMITTED`:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT AccountId, Balance
FROM dbo.IsolationLabAccount
WHERE AccountId = 1;
```

Với `READ COMMITTED` dùng locking (RCSI tắt), B sẽ chờ A kết thúc transaction. Khi A rollback, B đọc được `1000.00`. Nếu RCSI bật, B đọc phiên bản đã commit trước đó mà không cần chờ khóa ghi, cũng không thấy `500.00`.

`READ UNCOMMITTED` cũng có thể được áp dụng cho một truy vấn bằng table hint `WITH (NOLOCK)`, nhưng `NOLOCK` không có nghĩa là truy vấn không bao giờ chờ: nó vẫn có thể cần schema-stability lock và có thể đọc kết quả không nhất quán khi dữ liệu đang được di chuyển hoặc thay đổi cấu trúc. Không dùng nó cho dữ liệu tài chính hoặc quyết định nghiệp vụ cần chính xác.

## 4. Thí nghiệm 2: tái hiện non-repeatable read

Mục tiêu là để Session A đọc cùng một hàng hai lần trong một transaction nhưng nhận giá trị khác nhau vì Session B đã commit cập nhật giữa hai lần đọc.

Đặt lại dữ liệu trước thí nghiệm:

```sql
UPDATE dbo.IsolationLabAccount
SET Balance = 1000.00
WHERE AccountId = 1;
```

### Session A — đọc hai lần ở READ COMMITTED

```sql
USE YourTestDatabase;
GO
SET NOCOUNT ON;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

BEGIN TRANSACTION;

SELECT N'Đọc lần 1' AS ReadStep,
       AccountId, Balance
FROM dbo.IsolationLabAccount
WHERE AccountId = 1;

WAITFOR DELAY '00:00:20';

SELECT N'Đọc lần 2' AS ReadStep,
       AccountId, Balance
FROM dbo.IsolationLabAccount
WHERE AccountId = 1;

COMMIT TRANSACTION;
```

### Session B — cập nhật và commit trong lúc A chờ

```sql
USE YourTestDatabase;
GO
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

BEGIN TRANSACTION;

UPDATE dbo.IsolationLabAccount
SET Balance = 900.00
WHERE AccountId = 1;

COMMIT TRANSACTION;
```

Chạy B trong khi A đang chờ. B có thể cập nhật và commit vì shared lock của câu `SELECT` đầu tiên trong locking `READ COMMITTED` đã được giải phóng khi statement kết thúc. Khi A chạy câu `SELECT` thứ hai, A thấy `900.00`.

Kết quả mong đợi:

| Phiên | Lần đọc | Giá trị |
|---|---|---:|
| A | SELECT lần 1 | 1000.00 |
| B | UPDATE rồi COMMIT | 900.00 |
| A | SELECT lần 2 | 900.00 |

Hai lần đọc cùng hàng trong một transaction cho kết quả khác nhau. Đó là non-repeatable read.

### Đối chiếu với REPEATABLE READ

Đặt lại số dư về `1000.00`, rồi chạy lại A với:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

Session B vẫn chạy câu `UPDATE` như trên. Lần này, shared lock của A được giữ đến khi transaction kết thúc. B phải chờ để cập nhật hàng. Lần đọc thứ hai của A vẫn là `1000.00`; sau khi A commit, B mới tiếp tục và commit `900.00`.

`REPEATABLE READ` ngăn thay đổi các hàng đã được A đọc trong transaction, nhưng như thí nghiệm tiếp theo cho thấy, nó chưa ngăn mọi hàng mới xuất hiện trong điều kiện truy vấn.

## 5. Thí nghiệm 3: tái hiện phantom read ở REPEATABLE READ

Phantom read xảy ra khi một truy vấn theo điều kiện trả về một tập hàng khác ở lần chạy sau. Hàng mới có thể được chèn, hoặc hàng cũ có thể được cập nhật để bắt đầu/thôi thỏa điều kiện.

Trong thí nghiệm này, Session A đếm các ghế có `RoomId = 1` và `SlotNo` từ 10 đến 20. Ban đầu chỉ có hai hàng: ghế 10 và ghế 20. Session B chèn ghế 15 vào khoảng đó.

Chuẩn bị lại dữ liệu trước thí nghiệm:

```sql
DELETE FROM dbo.IsolationLabSlot
WHERE RoomId = 1 AND SlotNo = 15;

SELECT SlotId, RoomId, SlotNo, Label
FROM dbo.IsolationLabSlot
WHERE RoomId = 1 AND SlotNo BETWEEN 10 AND 20
ORDER BY SlotNo;
```

Kết quả ban đầu có hai hàng.

### Session A — đọc phạm vi hai lần ở REPEATABLE READ

```sql
USE YourTestDatabase;
GO
SET NOCOUNT ON;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

BEGIN TRANSACTION;

SELECT N'Lần đọc 1' AS ReadStep,
       COUNT_BIG(*) AS SlotCount
FROM dbo.IsolationLabSlot
     WITH (INDEX(IX_IsolationLabSlot_Room_Slot))
WHERE RoomId = 1
  AND SlotNo BETWEEN 10 AND 20;

WAITFOR DELAY '00:00:20';

SELECT N'Lần đọc 2' AS ReadStep,
       COUNT_BIG(*) AS SlotCount
FROM dbo.IsolationLabSlot
     WITH (INDEX(IX_IsolationLabSlot_Room_Slot))
WHERE RoomId = 1
  AND SlotNo BETWEEN 10 AND 20;

COMMIT TRANSACTION;
```

### Session B — chèn một hàng thỏa điều kiện

Chạy trong lúc A đang chờ:

```sql
USE YourTestDatabase;
GO

INSERT INTO dbo.IsolationLabSlot (RoomId, SlotNo, Label)
VALUES (1, 15, N'Ghế 15');
```

Ở `REPEATABLE READ`, A giữ khóa chia sẻ trên các hàng đã đọc, nhưng không khóa toàn bộ khoảng giữa chúng. Vì vậy B có thể chèn hàng mới với `SlotNo = 15` và commit. Lần đếm thứ hai của A trả về 3 thay vì 2.

Đây là phantom read: truy vấn giống nhau trong cùng transaction trả về tập hàng/số lượng khác nhau do một hàng mới đã trở thành thành viên của tập kết quả.

## 6. Ngăn phantom bằng SERIALIZABLE và key-range lock

SQL Server `SERIALIZABLE` giữ các khóa cần thiết để bảo vệ cả khoảng khóa được truy vấn. Với chỉ mục `(RoomId, SlotNo)`, truy vấn phạm vi trong Session A có thể lấy key-range lock để ngăn transaction khác chèn một khóa mới vào khoảng đó trước khi A kết thúc.

Xóa hàng 15 trước khi chạy lại:

```sql
DELETE FROM dbo.IsolationLabSlot
WHERE RoomId = 1 AND SlotNo = 15;
```

### Session A — truy vấn phạm vi ở SERIALIZABLE

```sql
USE YourTestDatabase;
GO
SET NOCOUNT ON;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

BEGIN TRANSACTION;

SELECT N'Lần đọc 1' AS ReadStep,
       COUNT_BIG(*) AS SlotCount
FROM dbo.IsolationLabSlot
     WITH (INDEX(IX_IsolationLabSlot_Room_Slot))
WHERE RoomId = 1
  AND SlotNo BETWEEN 10 AND 20;

WAITFOR DELAY '00:00:20';

SELECT N'Lần đọc 2' AS ReadStep,
       COUNT_BIG(*) AS SlotCount
FROM dbo.IsolationLabSlot
     WITH (INDEX(IX_IsolationLabSlot_Room_Slot))
WHERE RoomId = 1
  AND SlotNo BETWEEN 10 AND 20;

COMMIT TRANSACTION;
```

### Session B — thử chèn ghế 15

```sql
USE YourTestDatabase;
GO

INSERT INTO dbo.IsolationLabSlot (RoomId, SlotNo, Label)
VALUES (1, 15, N'Ghế 15');
```

Chạy B trong lúc A đang `WAITFOR`. Lần này, câu `INSERT` của B sẽ phải chờ key-range lock do A giữ. A đọc lần hai vẫn thấy hai hàng và commit. Sau khi A commit, B mới có thể hoàn tất insert. Truy vấn chạy sau đó sẽ thấy ba hàng.

Điểm khác biệt:

| Isolation level của A | B chèn `SlotNo = 15` | Lần đọc thứ hai của A |
|---|---|---:|
| `REPEATABLE READ` | Có thể hoàn tất trước khi A commit | 3 — phantom xuất hiện |
| `SERIALIZABLE` | Bị chặn cho đến khi A kết thúc | 2 — không có phantom trong transaction A |

Key-range lock phụ thuộc kế hoạch truy vấn và chỉ mục. Bài thực hành dùng `INDEX(IX_IsolationLabSlot_Room_Slot)` để SQL Server truy cập đúng chỉ mục phạm vi. Trong hệ thống thực tế, không nên thêm index hint tùy tiện; hãy kiểm tra execution plan và lock behavior với schema, statistics và dữ liệu thực tế.

## 7. SNAPSHOT và READ_COMMITTED_SNAPSHOT trong SQL Server

SQL Server còn có cơ chế row versioning. Hai chế độ thường bị nhầm lẫn:

- **READ_COMMITTED_SNAPSHOT (RCSI):** khi database bật tùy chọn này, `READ COMMITTED` đọc phiên bản nhất quán ở cấp statement. Hai câu `SELECT` riêng trong cùng transaction có thể nhận hai snapshot khác nhau; do đó non-repeatable read và phantom vẫn có thể xuất hiện giữa các statement.
- **SNAPSHOT isolation:** mỗi transaction đọc theo một snapshot nhất quán ở cấp transaction. Các thay đổi được transaction khác commit sau snapshot không xuất hiện trong những lần đọc tiếp theo của transaction hiện tại. Dirty read, non-repeatable read và phantom read theo định nghĩa thông thường không xuất hiện trong snapshot đó.

`SNAPSHOT` cần database bật `ALLOW_SNAPSHOT_ISOLATION`. Trong database thử nghiệm, người có quyền phù hợp có thể bật bằng:

```sql
ALTER DATABASE YourTestDatabase
SET ALLOW_SNAPSHOT_ISOLATION ON;
```

Đây là thay đổi cấu hình cấp database. Chỉ chạy khi được phép và trong môi trường thử nghiệm; không bật trên database dùng chung mà chưa đánh giá ảnh hưởng.

### Thử non-repeatable read dưới SNAPSHOT

Sau khi `ALLOW_SNAPSHOT_ISOLATION` đã ở trạng thái `ON`, đặt lại số dư về `1000.00`.

Session A:

```sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
BEGIN TRANSACTION;

SELECT N'Lần đọc 1' AS ReadStep, Balance
FROM dbo.IsolationLabAccount
WHERE AccountId = 1;

WAITFOR DELAY '00:00:20';

SELECT N'Lần đọc 2' AS ReadStep, Balance
FROM dbo.IsolationLabAccount
WHERE AccountId = 1;

COMMIT TRANSACTION;
```

Session B, chạy trong lúc A chờ:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
BEGIN TRANSACTION;

UPDATE dbo.IsolationLabAccount
SET Balance = 900.00
WHERE AccountId = 1;

COMMIT TRANSACTION;
```

A sẽ thấy cùng giá trị trong cả hai lần đọc vì transaction tiếp tục đọc snapshot của nó. B có thể cập nhật và commit mà không phải chờ shared lock đọc của A như trong locking `READ COMMITTED`.

Snapshot isolation không đồng nghĩa serializable. Hai transaction có thể đọc cùng một snapshot rồi cập nhật các hàng khác nhau, dẫn đến write skew nếu bất biến nghiệp vụ phụ thuộc nhiều hàng. Khi hai transaction cùng cập nhật một hàng đã thay đổi kể từ snapshot của mình, SQL Server có thể hủy một transaction bằng lỗi update conflict (thường là lỗi 3960). Hãy chọn `SERIALIZABLE` hoặc cơ chế bảo vệ bất biến phù hợp khi cần tính tuần tự hóa mạnh.

## 8. Ma trận hiện tượng theo isolation level trong SQL Server

Bảng sau mô tả hành vi khái quát khi dùng các isolation level chuẩn của SQL Server:

| Isolation level | Dirty read | Non-repeatable read | Phantom read |
|---|---:|---:|---:|
| `READ UNCOMMITTED` | Có thể | Có thể | Có thể |
| `READ COMMITTED` (locking hoặc RCSI) | Không | Có thể | Có thể |
| `REPEATABLE READ` | Không | Không | Có thể |
| `SERIALIZABLE` | Không | Không | Không |
| `SNAPSHOT` | Không | Không trong snapshot transaction | Không trong snapshot transaction |

Lưu ý về RCSI: nó thay đổi cách `READ COMMITTED` đọc dữ liệu từ shared lock sang statement-level row versioning, nhưng không biến `READ COMMITTED` thành `SNAPSHOT`. Mỗi statement có snapshot riêng, vì vậy hai câu truy vấn trong cùng transaction vẫn có thể thấy hai trạng thái đã commit khác nhau.

## 9. Cách đọc kết quả và phân biệt ba hiện tượng

| Hiện tượng | Hai phiên làm gì? | Dấu hiệu cần quan sát |
|---|---|---|
| Dirty read | A cập nhật nhưng chưa commit; B đọc ở `READ UNCOMMITTED` | B thấy giá trị mới của A; A rollback khiến giá trị đó biến mất |
| Non-repeatable read | A đọc một hàng hai lần; B cập nhật và commit giữa hai lần | Giá trị của cùng khóa chính khác nhau ở hai lần đọc |
| Phantom read | A chạy cùng truy vấn phạm vi hai lần; B chèn hàng thỏa điều kiện | Tập hàng hoặc `COUNT(*)` thay đổi ở lần đọc thứ hai |

Đừng nhầm non-repeatable read với phantom read:

- Non-repeatable read thường nói về **một hàng đã được đọc** nhưng giá trị của hàng đó thay đổi.
- Phantom read nói về **tập hàng thỏa một predicate** thay đổi; một hàng mới xuất hiện hoặc một hàng cũ bắt đầu/thôi thỏa điều kiện.

## 10. Những nguyên nhân khiến thí nghiệm không cho kết quả như mong đợi

- **Chạy B quá muộn:** `WAITFOR` của A đã kết thúc, transaction đã commit/rollback. Hãy chạy lại A và thực hiện B trong khoảng chờ.
- **Hai cửa sổ dùng cùng connection:** mở hai query window với hai session riêng và xác nhận `@@SPID` khác nhau:

  ```sql
  SELECT @@SPID AS SessionId, DB_NAME() AS DatabaseName;
  ```

- **Hai session khác database:** xác nhận `DB_NAME()` giống nhau ở cả A và B.
- **Dữ liệu đã bị thay đổi từ bài trước:** đặt lại số dư hoặc xóa hàng ghế 15 trước mỗi lượt thử.
- **Transaction cũ còn mở:** kiểm tra cửa sổ Messages/Results, chạy `COMMIT` hoặc `ROLLBACK` phù hợp trước khi bắt đầu bài mới.
- **RCSI đang bật:** `READ COMMITTED` vẫn không đọc bẩn, nhưng cách nó tránh chờ khóa khác với locking `READ COMMITTED`. Kiểm tra `is_read_committed_snapshot_on`.
- **Không có chỉ mục phạm vi:** `SERIALIZABLE` vẫn phải bảo vệ predicate, nhưng kiểu và phạm vi khóa có thể khác. Dùng đúng index trong bài lab để quan sát key-range behavior dễ hơn.
- **B dùng hint hoặc isolation khác:** bảo đảm B không vô tình chạy `READ UNCOMMITTED`, `NOLOCK` hoặc một transaction cũ.
- **Query bị timeout/cancel:** tăng `WAITFOR` hoặc thời hạn query ở công cụ, nhưng không để transaction thử nghiệm mở lâu hơn cần thiết.

Có thể xem session hiện tại bằng:

```sql
SELECT
    @@SPID AS SessionId,
    DB_NAME() AS DatabaseName,
    SESSIONPROPERTY('ANSI_NULLS') AS AnsiNulls;
```

Khi cần điều tra lock, DBA có thể dùng DMV như `sys.dm_tran_locks`, `sys.dm_exec_requests` và `sys.dm_os_waiting_tasks`. Việc đọc DMV cần quyền phù hợp và nên giới hạn vào đúng session của bài lab.

## 11. Dọn dẹp sau thực nghiệm

Nếu chỉ muốn đưa dữ liệu về trạng thái ban đầu:

```sql
UPDATE dbo.IsolationLabAccount
SET Balance = 1000.00
WHERE AccountId = 1;

DELETE FROM dbo.IsolationLabSlot
WHERE RoomId = 1 AND SlotNo = 15;
```

Nếu không cần giữ các bảng thực nghiệm, có thể xóa chúng trong database thử nghiệm:

```sql
DROP TABLE IF EXISTS dbo.IsolationLabSlot;
DROP TABLE IF EXISTS dbo.IsolationLabAccount;
```

Không chạy lệnh `DROP TABLE` nếu các bảng này đang được dùng cho mục đích khác.

## 12. Những điểm cần nhớ

- SQL Server `READ UNCOMMITTED` cho phép dirty read; `READ COMMITTED` ngăn dirty read.
- `READ COMMITTED` không bảo đảm một hàng giữ nguyên giá trị giữa hai statement trong cùng transaction.
- `REPEATABLE READ` giữ khóa chia sẻ trên các hàng đã đọc đến cuối transaction, nhưng không bảo vệ toàn bộ khoảng khóa nên phantom vẫn có thể xuất hiện.
- `SERIALIZABLE` bảo vệ predicate bằng khóa phạm vi phù hợp, ngăn chèn hoặc thay đổi hàng làm xuất hiện phantom trong transaction.
- `READ_COMMITTED_SNAPSHOT` dùng snapshot ở cấp statement; nó không cung cấp snapshot cố định cho toàn transaction.
- `SNAPSHOT` dùng row versioning ở cấp transaction và cần `ALLOW_SNAPSHOT_ISOLATION ON`.
- Snapshot isolation ngăn các hiện tượng đọc nêu trên trong snapshot nhưng không tương đương serializable; vẫn có thể có write skew.
- Muốn thí nghiệm hai phiên có ý nghĩa, phải dùng hai connection, cùng database và chạy Session B trong lúc Session A đang giữ transaction mở.
- Chỉ bật tùy chọn isolation cấp database trong môi trường thử nghiệm được phép.

Thực nghiệm hai phiên giúp biến tên gọi isolation level thành hành vi có thể quan sát. Hãy bắt đầu với `READ UNCOMMITTED` để thấy dirty read, dùng `READ COMMITTED` để thấy non-repeatable read, rồi so sánh `REPEATABLE READ` và `SERIALIZABLE` để thấy phantom read được cho phép hay bị ngăn bằng key-range lock. Cuối cùng, đối chiếu RCSI và `SNAPSHOT` để hiểu row versioning thay đổi cách đọc như thế nào trong SQL Server.
