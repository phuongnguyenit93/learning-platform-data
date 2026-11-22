# Thử cùng một lịch thực thi dưới các mức cô lập

Cách dễ hiểu nhất về isolation level là chạy cùng một kịch bản trên hai session database, thay đổi duy nhất mức cô lập rồi quan sát kết quả. Một session giữ transaction mở; session còn lại đọc hoặc ghi cùng dữ liệu trong lúc transaction đầu chưa kết thúc. Bằng cách đó, ta thấy rõ khi nào một thao tác bị chặn, khi nào nó nhìn thấy phiên bản cũ, khi nào kết quả đọc thay đổi và khi nào database hủy transaction.

Bài thực nghiệm này dùng cú pháp **SQL Server** làm phòng lab chính để có thể quan sát READ UNCOMMITTED, READ COMMITTED, REPEATABLE READ, SERIALIZABLE và SNAPSHOT. Sau mỗi thí nghiệm có giải thích cách diễn giải kết quả và ghi chú khác biệt ở PostgreSQL, MySQL InnoDB và Oracle. Các mức cùng tên giữa các hệ quản trị không phải lúc nào cũng có cùng cách triển khai.

Mục tiêu không phải ghi nhớ một bảng lý thuyết. Mục tiêu là biết tổ chức hai session, dự đoán kết quả, chạy thử, giải thích vì sao kết quả xuất hiện và chọn cơ chế bảo vệ đúng cho invariant nghiệp vụ.

## 1. Chuẩn bị phòng lab hai session

Mở hai cửa sổ query độc lập, gọi là **Session A** và **Session B**. Mỗi cửa sổ phải dùng connection riêng đến cùng một database. Không chạy hai phần của một kịch bản trên cùng connection vì khi đó chúng không còn là hai transaction độc lập.

Trong SQL Server Management Studio có thể mở hai query window. Trong Azure Data Studio hoặc công cụ khác, mở hai tab kết nối riêng. Kiểm tra cả hai đang kết nối đúng database.

Các ví dụ dùng database hiện tại và schema dbo. Tạo bảng thử nghiệm một lần:

~~~sql
DROP TABLE IF EXISTS dbo.LabBooking;
DROP TABLE IF EXISTS dbo.LabAccount;
DROP TABLE IF EXISTS dbo.LabDoctorOnCall;
GO

CREATE TABLE dbo.LabAccount
(
    AccountId int NOT NULL PRIMARY KEY,
    Balance int NOT NULL
        CONSTRAINT CK_LabAccount_Balance CHECK (Balance >= 0)
);

INSERT INTO dbo.LabAccount(AccountId, Balance)
VALUES (1, 1000);

CREATE TABLE dbo.LabBooking
(
    BookingId int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    RoomId int NOT NULL,
    BookingStatus varchar(20) NOT NULL,
    Note varchar(100) NULL
);

CREATE INDEX IX_LabBooking_Room_Status
ON dbo.LabBooking(RoomId, BookingStatus);

CREATE TABLE dbo.LabDoctorOnCall
(
    ShiftId int NOT NULL,
    DoctorId int NOT NULL,
    IsOnCall bit NOT NULL,
    CONSTRAINT PK_LabDoctorOnCall
        PRIMARY KEY (ShiftId, DoctorId)
);

INSERT INTO dbo.LabDoctorOnCall(ShiftId, DoctorId, IsOnCall)
VALUES (10, 1, 1), (10, 2, 1);
GO
~~~

Bảng LabAccount phục vụ dirty read, non-repeatable read và lost update. LabBooking dùng để thử phantom. LabDoctorOnCall minh họa write skew: mỗi ca trực cần ít nhất một bác sĩ còn trực.

### 1.1. Quy tắc chạy hai session

Các đoạn có WAITFOR được dùng để tạo một khoảng thời gian cho session còn lại chạy. Khi thực hiện:

1. Chạy phần Session A trước.
2. Khi A đang chờ WAITFOR hoặc đang bị giữ trong transaction, chạy phần Session B.
3. Quan sát B trả kết quả ngay, chờ hay báo lỗi.
4. Đợi A và B hoàn tất trước khi chạy kịch bản tiếp theo.
5. Nếu một session bị lỗi, kiểm tra và kết thúc transaction còn mở trước khi tiếp tục.

Không chạy lại phần tạo bảng giữa hai session. Không đóng cửa sổ trong khi transaction còn mở trừ khi muốn chủ động thử hành vi mất kết nối và rollback.

### 1.2. Kiểm tra và kết thúc transaction còn mở

Trong SQL Server, có thể kiểm tra trạng thái transaction hiện tại:

~~~sql
SELECT @@TRANCOUNT AS OpenTransactionCount,
       XACT_STATE() AS TransactionState;
~~~

Nếu đang còn transaction do thí nghiệm trước, hãy rollback trước khi chạy tiếp:

~~~sql
IF XACT_STATE() <> 0
    ROLLBACK TRANSACTION;
~~~

Các giá trị XACT_STATE thường gặp:

- 1: transaction đang hoạt động và còn có thể commit.
- 0: không có transaction đang hoạt động.
- -1: transaction đang ở trạng thái không thể commit; cần rollback toàn bộ.

Isolation level được đặt trên connection và có thể tiếp tục áp dụng cho câu lệnh sau đó. Hãy đặt lại mức cần dùng ở đầu mỗi kịch bản. Khi dùng connection pool trong ứng dụng, phải bảo đảm trạng thái session được reset phù hợp trước khi connection được giao cho request khác.

## 2. Thí nghiệm 1: Dirty read với READ UNCOMMITTED

Dirty read xảy ra khi một transaction đọc thay đổi chưa commit của transaction khác. Nếu transaction ghi sau đó rollback, dữ liệu reader đã nhìn thấy thực ra chưa bao giờ trở thành trạng thái đã commit.

Đặt lại số dư trước khi thử:

~~~sql
UPDATE dbo.LabAccount
SET Balance = 1000
WHERE AccountId = 1;
~~~

### Session A — cập nhật nhưng chưa commit

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

BEGIN TRANSACTION;

UPDATE dbo.LabAccount
SET Balance = 900
WHERE AccountId = 1;

-- Giữ transaction mở trong 15 giây.
WAITFOR DELAY '00:00:15';

ROLLBACK TRANSACTION;
~~~

### Session B — đọc trong lúc A chưa kết thúc

Chạy B ngay sau khi A bắt đầu WAITFOR:

~~~sql
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

SELECT AccountId, Balance
FROM dbo.LabAccount
WHERE AccountId = 1;
~~~

**Kết quả mong đợi:** Session B có thể đọc Balance = 900 dù A chưa commit. Sau 15 giây, A rollback và số dư trở về 1000. Giá trị 900 mà B đã nhìn thấy là dữ liệu bẩn.

Bây giờ lặp lại cùng lịch chạy nhưng đổi Session B sang READ COMMITTED:

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT AccountId, Balance
FROM dbo.LabAccount
WHERE AccountId = 1;
~~~

Trong cấu hình SQL Server dùng locking READ COMMITTED, B phải chờ khóa ghi của A. Khi A rollback, B tiếp tục và đọc 1000. B không nhìn thấy 900.

Nếu database bật READ_COMMITTED_SNAPSHOT, READ COMMITTED thông thường dùng row versioning cho câu SELECT và có thể đọc phiên bản đã commit trước đó mà không chờ A. Kết quả vẫn không phải 900; B thường đọc 1000 từ phiên bản đã commit.

### Điều cần quan sát

| Session B | Hành vi khi A chưa kết thúc | Giá trị nhìn thấy |
|---|---|---:|
| READ UNCOMMITTED | Có thể đọc mà không chờ khóa ghi | 900 chưa commit |
| READ COMMITTED, locking | Chờ A commit/rollback | 1000 sau rollback |
| READ COMMITTED, RCSI | Đọc phiên bản đã commit, thường không chờ writer | 1000 |

READ UNCOMMITTED giảm blocking bằng cách chấp nhận đọc dữ liệu chưa commit. Điều đó có thể làm báo cáo, kiểm tra hạn mức hoặc quyết định nghiệp vụ dựa trên dữ liệu sẽ bị hủy.

Không dùng READ UNCOMMITTED hoặc NOLOCK chỉ để làm truy vấn nhanh hơn nếu kết quả cần chính xác. Dirty read không phải một cách đọc nhất quán.

## 3. Thí nghiệm 2: Non-repeatable read với READ COMMITTED

Non-repeatable read xảy ra khi cùng một transaction đọc lại một dòng nhưng nhận giá trị khác vì transaction khác đã commit cập nhật giữa hai lần đọc.

Đặt lại số dư:

~~~sql
UPDATE dbo.LabAccount
SET Balance = 1000
WHERE AccountId = 1;
~~~

### Session A — đọc hai lần trong một transaction

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

BEGIN TRANSACTION;

SELECT Balance AS FirstRead
FROM dbo.LabAccount
WHERE AccountId = 1;

WAITFOR DELAY '00:00:15';

SELECT Balance AS SecondRead
FROM dbo.LabAccount
WHERE AccountId = 1;

COMMIT TRANSACTION;
~~~

### Session B — cập nhật giữa hai lần đọc

Chạy B trong khoảng A đang WAITFOR:

~~~sql
UPDATE dbo.LabAccount
SET Balance = 1200
WHERE AccountId = 1;
~~~

Trong locking READ COMMITTED, shared lock của câu SELECT thông thường được giải phóng sau khi câu lệnh hoàn tất. Vì vậy, B có thể cập nhật và commit trong lúc A chờ. Câu SELECT thứ hai của A bắt đầu sau khi B commit và có thể trả về 1200.

A đã đọc 1000 rồi 1200 trong cùng transaction. Đây là non-repeatable read.

### Lặp lại với REPEATABLE READ

Đặt lại Balance = 1000. Đổi Session A:

~~~sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

BEGIN TRANSACTION;

SELECT Balance AS FirstRead
FROM dbo.LabAccount
WHERE AccountId = 1;

WAITFOR DELAY '00:00:15';

SELECT Balance AS SecondRead
FROM dbo.LabAccount
WHERE AccountId = 1;

COMMIT TRANSACTION;
~~~

Session B vẫn chạy UPDATE Balance = 1200 như trước. Trong REPEATABLE READ, A giữ shared lock trên dòng đã đọc đến khi transaction kết thúc. B phải chờ A commit. Lần đọc thứ hai của A vẫn là 1000; sau khi A commit, B mới có thể cập nhật.

### Lặp lại với SNAPSHOT

SQL Server phải bật hỗ trợ snapshot trước khi chạy thử. Quản trị viên có thể bật một lần khi không có yêu cầu khác về trạng thái database:

~~~sql
ALTER DATABASE CURRENT
SET ALLOW_SNAPSHOT_ISOLATION ON;
~~~

Sau khi cấu hình hoàn tất, đặt lại Balance = 1000. Session A:

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;

BEGIN TRANSACTION;

SELECT Balance AS FirstRead
FROM dbo.LabAccount
WHERE AccountId = 1;

WAITFOR DELAY '00:00:15';

SELECT Balance AS SecondRead
FROM dbo.LabAccount
WHERE AccountId = 1;

COMMIT TRANSACTION;
~~~

Session B cập nhật Balance = 1200 và commit trong lúc A chờ. SNAPSHOT giữ một transaction-level snapshot nên A tiếp tục đọc 1000, còn B có thể commit mà không phải chờ shared lock đọc thông thường của A.

### Kết quả so sánh

| Mức của A | Lần đọc đầu | Hành vi B khi UPDATE | Lần đọc thứ hai của A |
|---|---:|---|---:|
| READ COMMITTED, locking | 1000 | Có thể commit giữa hai câu SELECT | 1200 |
| REPEATABLE READ | 1000 | Chờ shared lock của A | 1000 |
| SNAPSHOT | 1000 | Có thể commit độc lập | 1000 |
| SERIALIZABLE | 1000 | UPDATE dòng đã đọc phải chờ A | 1000 |

REPEATABLE READ và SERIALIZABLE giữ khóa đọc theo cách locking. SNAPSHOT dùng phiên bản dữ liệu để giữ kết quả đọc ổn định. Kết quả đọc giống nhau trong ví dụ này nhưng cách phối hợp writer khác nhau.

## 4. Thí nghiệm 3: Phantom read và bảo vệ khoảng

Phantom read xảy ra khi tập dòng thỏa một predicate thay đổi giữa hai lần truy vấn. Ở đây Session A đếm booking đang mở của phòng 10; Session B chèn một booking mới cũng thuộc phòng đó.

Xóa dữ liệu thử cũ và xác nhận ban đầu không có booking:

~~~sql
DELETE FROM dbo.LabBooking
WHERE RoomId = 10;
~~~

### Session A — truy vấn một khoảng dữ liệu

Thử trước với READ COMMITTED:

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

BEGIN TRANSACTION;

SELECT COUNT(*) AS FirstCount
FROM dbo.LabBooking
WHERE RoomId = 10
  AND BookingStatus = 'OPEN';

WAITFOR DELAY '00:00:15';

SELECT COUNT(*) AS SecondCount
FROM dbo.LabBooking
WHERE RoomId = 10
  AND BookingStatus = 'OPEN';

COMMIT TRANSACTION;
~~~

### Session B — chèn dòng mới thỏa predicate

Chạy trong lúc A chờ:

~~~sql
INSERT INTO dbo.LabBooking(RoomId, BookingStatus, Note)
VALUES (10, 'OPEN', 'Inserted by Session B');
~~~

A thường đọc 0 ở lần đầu và 1 ở lần thứ hai. Tập kết quả đã xuất hiện một phantom row.

### Lặp lại với REPEATABLE READ

Xóa booking thử và chạy lại Session A ở REPEATABLE READ:

~~~sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

BEGIN TRANSACTION;

SELECT COUNT(*) AS FirstCount
FROM dbo.LabBooking
WHERE RoomId = 10
  AND BookingStatus = 'OPEN';

WAITFOR DELAY '00:00:15';

SELECT COUNT(*) AS SecondCount
FROM dbo.LabBooking
WHERE RoomId = 10
  AND BookingStatus = 'OPEN';

COMMIT TRANSACTION;
~~~

Session B lại INSERT một dòng OPEN cho RoomId = 10. REPEATABLE READ giữ khóa trên những dòng đã đọc, nhưng không bảo vệ toàn bộ khoảng nơi một dòng mới có thể xuất hiện. Nếu không có dòng phù hợp ban đầu, có thể không có key nào để khóa. INSERT của B có thể commit và lần SELECT thứ hai của A có thể thấy phantom.

Đây là khác biệt quan trọng giữa REPEATABLE READ và SERIALIZABLE trong SQL Server.

### Lặp lại với SERIALIZABLE

Xóa booking thử. Session A:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

BEGIN TRANSACTION;

SELECT COUNT(*) AS FirstCount
FROM dbo.LabBooking
WHERE RoomId = 10
  AND BookingStatus = 'OPEN';

WAITFOR DELAY '00:00:15';

SELECT COUNT(*) AS SecondCount
FROM dbo.LabBooking
WHERE RoomId = 10
  AND BookingStatus = 'OPEN';

COMMIT TRANSACTION;
~~~

Session B thử INSERT cùng predicate trong lúc A chờ. Với index IX_LabBooking_Room_Status và kế hoạch truy vấn phù hợp, SQL Server dùng key-range lock để bảo vệ vùng index liên quan. INSERT của B phải chờ A kết thúc. A đọc cùng số lượng ở hai lần; sau khi A commit, B mới tiếp tục.

Nếu không có index phù hợp, SQL Server vẫn phải bảo vệ predicate theo kế hoạch truy vấn thực tế, nhưng phạm vi khóa có thể rộng hơn và gây blocking nhiều hơn. Index giúp xác định khoảng rõ hơn; nó không thay thế isolation level.

### Lặp lại với SNAPSHOT

Xóa booking thử. Session A:

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;

BEGIN TRANSACTION;

SELECT COUNT(*) AS FirstCount
FROM dbo.LabBooking
WHERE RoomId = 10
  AND BookingStatus = 'OPEN';

WAITFOR DELAY '00:00:15';

SELECT COUNT(*) AS SecondCount
FROM dbo.LabBooking
WHERE RoomId = 10
  AND BookingStatus = 'OPEN';

COMMIT TRANSACTION;
~~~

Session B chạy trong lúc A chờ:

~~~sql
INSERT INTO dbo.LabBooking(RoomId, BookingStatus, Note)
VALUES (10, 'OPEN', 'Inserted during SNAPSHOT');
~~~

A đọc cùng số lượng ở hai lần vì cả transaction dùng một snapshot. Khác SERIALIZABLE, SNAPSHOT không khóa khoảng để chặn INSERT; nó cho B commit và A tiếp tục đọc snapshot cũ.

### Kết quả so sánh

| Mức của A | B INSERT dòng thỏa predicate | Lần đếm thứ hai của A |
|---|---|---:|
| READ COMMITTED | Có thể commit | Thấy phantom |
| REPEATABLE READ | Có thể commit vì không bảo vệ khoảng trống | Có thể thấy phantom |
| SNAPSHOT | Có thể commit | Không thấy phantom trong snapshot A |
| SERIALIZABLE | Bị chặn bởi key-range lock phù hợp | Không thấy phantom trước khi A kết thúc |

Phantom và non-repeatable read đều làm kết quả đọc thay đổi, nhưng phạm vi khác nhau. Non-repeatable read liên quan đến một dòng đã đọc; phantom liên quan đến tập dòng thỏa điều kiện truy vấn.

## 5. Thí nghiệm 4: Lost update khi ứng dụng ghi giá trị tuyệt đối

Lost update xảy ra khi hai transaction cùng đọc một giá trị cũ, tính toán độc lập rồi ghi giá trị tuyệt đối. Ghi sau có thể ghi đè kết quả của ghi trước.

Đặt Balance = 1000:

~~~sql
UPDATE dbo.LabAccount
SET Balance = 1000
WHERE AccountId = 1;
~~~

Giả sử hai khách hàng cùng rút tiền: A rút 100, B rút 200. Nếu cả hai đọc số dư 1000 rồi tính ở ứng dụng:

- A tính số dư mới là 900.
- B tính số dư mới là 800.
- Nếu A ghi 900 rồi B ghi 800, kết quả cuối là 800.
- Kết quả đúng nếu cả hai giao dịch đều được chấp nhận phải là 700.

### Session A — đọc và giữ transaction

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

BEGIN TRANSACTION;

SELECT Balance
FROM dbo.LabAccount
WHERE AccountId = 1;

-- Giả sử ứng dụng tính newBalance = 900.
WAITFOR DELAY '00:00:10';

UPDATE dbo.LabAccount
SET Balance = 900
WHERE AccountId = 1;

COMMIT TRANSACTION;
~~~

### Session B — đọc cùng giá trị trước khi A ghi

Trong lúc A chờ, chạy:

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

BEGIN TRANSACTION;

SELECT Balance
FROM dbo.LabAccount
WHERE AccountId = 1;

-- Giả sử ứng dụng tính newBalance = 800.
WAITFOR DELAY '00:00:15';

UPDATE dbo.LabAccount
SET Balance = 800
WHERE AccountId = 1;

COMMIT TRANSACTION;
~~~

Để lịch chạy đúng, B cần đọc 1000 trước khi A thực hiện UPDATE. A cập nhật và commit trước; sau đó B ghi giá trị 800 đã tính từ dữ liệu cũ. Kết quả cuối là 800, làm mất tác động của lần rút 100.

Trong môi trường thử nghiệm, điều chỉnh WAITFOR hoặc chạy từng câu theo từng bước để chắc chắn cả hai SELECT hoàn tất trước khi A UPDATE. Có thể bỏ WAITFOR trong phần UPDATE và tự chạy câu lệnh theo thứ tự.

### Cách sửa bằng phép cập nhật tương đối nguyên tử

Thay vì gửi giá trị tuyệt đối do ứng dụng tính, để database thực hiện phép trừ trên giá trị hiện hành:

~~~sql
UPDATE dbo.LabAccount
SET Balance = Balance - @amount
WHERE AccountId = 1
  AND Balance >= @amount;
~~~

Kiểm tra số dòng bị ảnh hưởng. Nếu là 1, khoản rút đã được chấp nhận; nếu là 0, số dư không đủ hoặc tài khoản không tồn tại.

Cách này loại bỏ lost update cho phép trừ đơn giản trên cùng dòng vì mỗi UPDATE tính trên phiên bản hiện hành sau khi phối hợp khóa. Nếu nghiệp vụ cần kiểm tra nhiều dòng hoặc nhiều điều kiện, cần thêm transaction, constraint hoặc isolation phù hợp.

## 6. Thí nghiệm 5: Write skew dưới SNAPSHOT

Snapshot isolation giúp các lần đọc ổn định và cho phép reader ít chặn writer, nhưng nó không đồng nghĩa SERIALIZABLE. Write skew có thể xảy ra khi hai transaction cùng đọc một invariant rồi cập nhật các dòng khác nhau.

Giả sử mỗi ca trực phải có ít nhất một bác sĩ. Ban đầu bác sĩ 1 và 2 đều trực:

~~~sql
SELECT *
FROM dbo.LabDoctorOnCall
WHERE ShiftId = 10;
~~~

Kết quả ban đầu có hai dòng IsOnCall = 1.

Bật SNAPSHOT nếu chưa bật:

~~~sql
ALTER DATABASE CURRENT
SET ALLOW_SNAPSHOT_ISOLATION ON;
~~~

### Session A

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;

BEGIN TRANSACTION;

SELECT COUNT(*) AS OnCallCount
FROM dbo.LabDoctorOnCall
WHERE ShiftId = 10
  AND IsOnCall = 1;

-- A quyết định bác sĩ 1 có thể nghỉ vì thấy còn 2 người.
WAITFOR DELAY '00:00:15';

UPDATE dbo.LabDoctorOnCall
SET IsOnCall = 0
WHERE ShiftId = 10
  AND DoctorId = 1;

COMMIT TRANSACTION;
~~~

### Session B

Chạy B trong khi A đang chờ:

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;

BEGIN TRANSACTION;

SELECT COUNT(*) AS OnCallCount
FROM dbo.LabDoctorOnCall
WHERE ShiftId = 10
  AND IsOnCall = 1;

-- B cũng thấy 2 người và quyết định bác sĩ 2 có thể nghỉ.
WAITFOR DELAY '00:00:20';

UPDATE dbo.LabDoctorOnCall
SET IsOnCall = 0
WHERE ShiftId = 10
  AND DoctorId = 2;

COMMIT TRANSACTION;
~~~

Cả hai transaction cập nhật các dòng khác nhau. SQL Server SNAPSHOT phát hiện xung đột ghi khi hai transaction cập nhật cùng một dòng, nhưng trong lịch này mỗi transaction ghi một dòng riêng. Do đó, cả hai có thể commit và kết quả là không còn bác sĩ nào trực.

Đây là write skew: mỗi quyết định hợp lệ trên snapshot riêng, nhưng tổng hợp các quyết định lại vi phạm invariant.

### Lặp lại với SERIALIZABLE

Khôi phục dữ liệu:

~~~sql
UPDATE dbo.LabDoctorOnCall
SET IsOnCall = 1
WHERE ShiftId = 10;
~~~

Chạy cùng lịch hai session nhưng đổi isolation level của cả hai thành SERIALIZABLE. Cả hai transaction đọc tập bác sĩ đang trực và giữ các khóa bảo vệ dữ liệu/range. Khi mỗi transaction muốn cập nhật một dòng mà transaction kia đang giữ khóa đọc, có thể hình thành deadlock. SQL Server chọn một transaction làm victim; transaction còn lại có thể hoàn tất. Sau đó phải chạy lại toàn bộ logic của transaction bị hủy để đọc lại số người còn trực.

Kết quả cụ thể phụ thuộc lịch chạy và execution plan, nhưng cả hai transaction không thể cùng commit một lịch vi phạm invariant như trên nếu SERIALIZABLE được áp dụng đúng cho mọi đường ghi.

Một cách khác là tạo dòng guard cho từng ShiftId và buộc mọi thao tác thay đổi trạng thái trực phải khóa dòng đó trước khi đếm và cập nhật. Guard row làm quy tắc tuần tự hóa rõ hơn; tất cả writer phải tuân thủ cùng giao thức.

## 7. Tổng hợp kết quả các thí nghiệm

Bảng dưới đây mô tả hành vi điển hình của SQL Server với locking READ COMMITTED mặc định và SNAPSHOT đã được bật. RCSI là tùy chọn riêng có thể thay đổi hành vi đọc của READ COMMITTED.

| Hiện tượng | READ UNCOMMITTED | READ COMMITTED | REPEATABLE READ | SNAPSHOT | SERIALIZABLE |
|---|---|---|---|---|---|
| Dirty read | Có thể | Không | Không | Không | Không |
| Non-repeatable read | Có thể | Có thể | Bị ngăn | Bị ngăn | Bị ngăn |
| Phantom read | Có thể | Có thể | Có thể | Bị ngăn trong snapshot | Bị ngăn bằng bảo vệ khoảng |
| Lost update với ghi giá trị tuyệt đối | Có thể | Có thể | Có thể bị deadlock khi nâng khóa | Xung đột nếu cùng dòng | Khóa/abort, cần xử lý |
| Write skew trên các dòng khác nhau | Có thể | Có thể | Có thể | Có thể | Bị ngăn nếu áp dụng đúng |
| Reader thông thường chặn writer | Thường không | Có thể, tùy RCSI | Có | Không với snapshot read | Có thể |
| Writer chặn reader thông thường | Thường không | Có thể, tùy RCSI | Có thể | Thường không | Có thể |

Không nên hiểu bảng như một cam kết cho mọi DBMS. Ví dụ PostgreSQL không cho dirty read ngay cả khi yêu cầu READ UNCOMMITTED; REPEATABLE READ của PostgreSQL ngăn phantom read; MySQL InnoDB có snapshot read và next-key locking; SQL Server có các tùy chọn row-versioning riêng.

## 8. Khác biệt khi chạy cùng lịch trên PostgreSQL

PostgreSQL dùng MVCC và có một số khác biệt quan trọng so với phòng lab SQL Server:

- READ UNCOMMITTED được chấp nhận về cú pháp nhưng hoạt động như READ COMMITTED. Thí nghiệm dirty read không thể quan sát giá trị chưa commit ở PostgreSQL.
- READ COMMITTED lấy snapshot mới cho mỗi câu lệnh. Non-repeatable read và phantom có thể xuất hiện khi transaction khác commit giữa hai câu lệnh.
- REPEATABLE READ dùng một snapshot cho toàn transaction và trong PostgreSQL ngăn cả non-repeatable read lẫn phantom read. Tuy nhiên, write skew vẫn có thể xảy ra.
- SERIALIZABLE dùng SSI và SIREAD predicate locks. Thay vì luôn chặn INSERT bằng range lock, PostgreSQL theo dõi phụ thuộc và có thể hủy một transaction với SQLSTATE 40001.
- Khi nhận 40001 hoặc deadlock 40P01, ứng dụng thường phải rollback và retry toàn bộ transaction.

Để thử PostgreSQL, cú pháp bắt đầu transaction:

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;
-- hoặc REPEATABLE READ / SERIALIZABLE

SELECT ...;

COMMIT;
~~~

Đối với write skew, chạy hai transaction SERIALIZABLE cùng đọc predicate rồi cập nhật hai dòng khác nhau. PostgreSQL có thể cho một transaction commit và hủy transaction còn lại với lỗi serialization failure. Không giả định transaction nào luôn là victim.

## 9. Khác biệt khi chạy cùng lịch trên MySQL InnoDB

InnoDB mặc định thường dùng REPEATABLE READ. Một SELECT thông thường là consistent read theo MVCC snapshot; locking read như SELECT ... FOR UPDATE có ngữ nghĩa khóa khác.

- READ UNCOMMITTED có thể cho phép dirty read.
- READ COMMITTED tạo snapshot mới cho mỗi consistent read statement.
- REPEATABLE READ giữ snapshot nhất quán cho consistent reads trong transaction.
- Locking reads và thao tác range ở REPEATABLE READ có thể dùng gap/next-key locks để ngăn insert vào khoảng được bảo vệ.
- SERIALIZABLE thay đổi cách đọc để phối hợp mạnh hơn với ghi; cần kiểm tra hành vi chính xác theo loại transaction và câu lệnh.

Ví dụ locking read:

~~~sql
START TRANSACTION;

SELECT *
FROM booking
WHERE room_id = 10
  AND booking_status = 'OPEN'
FOR UPDATE;

COMMIT;
~~~

Không nên nhầm SELECT thông thường với SELECT ... FOR UPDATE. Câu SELECT thông thường có thể đọc snapshot mà không khóa các dòng; locking read yêu cầu khóa để phối hợp cập nhật.

Khi có deadlock, InnoDB thường rollback toàn bộ transaction được chọn làm victim. Lock wait timeout mặc định thường rollback câu lệnh gây timeout, trừ khi cấu hình thay đổi hành vi; ứng dụng phải biết transaction còn ở trạng thái nào.

## 10. Khác biệt khi chạy cùng lịch trên Oracle

Oracle cung cấp statement-level read consistency ở READ COMMITTED: mỗi câu lệnh nhìn thấy dữ liệu đã commit tại thời điểm bắt đầu câu lệnh. Oracle không cho dirty read.

Ở SERIALIZABLE, transaction sử dụng snapshot ở cấp transaction và có thể nhận ORA-08177 khi một transaction khác thay đổi dữ liệu cần thiết kể từ snapshot. Ứng dụng cần rollback và retry toàn bộ transaction.

Oracle có cơ chế read consistency dựa trên undo để dựng phiên bản dữ liệu trước đó. Reader thường không chặn writer thông thường, nhưng DML vẫn phối hợp khóa trên các dòng bị cập nhật. SELECT ... FOR UPDATE khóa các dòng được chọn.

Không suy luận semantics của Oracle chỉ từ tên READ COMMITTED hoặc SERIALIZABLE. Hãy thử lại bằng hai session trên đúng phiên bản và cấu hình Oracle đang dùng.

## 11. Cách tổ chức một buổi thực nghiệm có thể lặp lại

Một thí nghiệm tốt phải kiểm soát được trạng thái ban đầu, thứ tự chạy và thời điểm commit.

### 11.1. Ghi lại giả thuyết trước khi chạy

Với mỗi kịch bản, ghi:

- Session A đọc hoặc ghi những dòng nào?
- Session A giữ transaction mở trong bao lâu?
- Session B thực hiện câu lệnh nào trong khoảng đó?
- Isolation level của từng session là gì?
- B dự kiến bị chặn, đọc phiên bản cũ, đọc phiên bản chưa commit hay commit bình thường?
- Kết quả cuối sau khi cả hai transaction kết thúc là gì?

Việc ghi dự đoán trước giúp phân biệt điều bạn hiểu với điều database thực sự làm.

### 11.2. Thay đổi một biến mỗi lần

Khi so sánh isolation level, giữ nguyên dữ liệu ban đầu, câu SQL, thứ tự thao tác, index và execution plan nếu có thể, thời gian chờ và cấu hình database. Chỉ thay đổi isolation level hoặc tùy chọn row-versioning cần khảo sát.

Nếu đồng thời đổi query, index và isolation level, sẽ khó biết nguyên nhân kết quả thay đổi.

### 11.3. Dùng thời gian chờ có kiểm soát

WAITFOR DELAY hữu ích trong SQL Server vì tạo cửa sổ cho session kia chạy. Nhưng delay quá ngắn có thể khiến session B đến sai thời điểm; delay quá dài làm transaction giữ khóa lâu và ảnh hưởng người khác.

Trong môi trường thử nghiệm:

- Dùng database riêng hoặc bảng có tiền tố Lab.
- Chọn delay đủ dài để chạy session còn lại.
- Không chạy kịch bản khi người khác đang dùng cùng bảng thử.
- Nếu một session bị kẹt, kiểm tra blocking và kết thúc transaction theo kế hoạch.
- Reset dữ liệu trước mỗi lần chạy.

Trong môi trường ứng dụng thật, không dùng WAITFOR hoặc sleep để điều phối transaction. Hãy dùng ranh giới transaction và giao thức nghiệp vụ.

## 12. Quan sát blocking và trạng thái transaction trong SQL Server

Khi Session B bị chờ, mở một query window thứ ba hoặc dùng một connection quản trị để xem request:

~~~sql
SELECT
    session_id,
    blocking_session_id,
    status,
    wait_type,
    wait_time,
    wait_resource,
    command
FROM sys.dm_exec_requests
WHERE blocking_session_id <> 0;
~~~

Để xem khóa đang được giữ hoặc yêu cầu:

~~~sql
SELECT
    request_session_id,
    resource_type,
    request_mode,
    request_status,
    resource_description
FROM sys.dm_tran_locks
WHERE resource_database_id = DB_ID();
~~~

Một số quan sát:

- Bị block không đồng nghĩa lỗi; đó có thể là hành vi đúng của REPEATABLE READ hoặc SERIALIZABLE.
- Wait type bắt đầu bằng LCK_M thường cho biết session đang chờ khóa.
- SERIALIZABLE với index range có thể tạo key-range lock.
- Deadlock khác blocking: database phát hiện chu trình chờ và chọn victim.
- SNAPSHOT có thể trả lỗi update conflict thay vì chờ khi hai transaction ghi cùng một dòng.

Không cần quyền quản trị cao nhất cho mọi truy vấn DMV, nhưng quyền xem trạng thái server phụ thuộc phiên bản SQL Server và cấu hình. Nếu truy vấn bị từ chối quyền, dùng tài khoản được cấp quyền giám sát phù hợp.

## 13. Các lỗi thực hành thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Session B không thấy dirty value | A đã commit/rollback trước khi B đọc hoặc B không dùng READ UNCOMMITTED | Chạy B trong khoảng A còn giữ transaction và kiểm tra isolation |
| Session B chờ lâu | A giữ khóa trên dòng hoặc khoảng B cần | Quan sát blocker; kết thúc transaction A theo lịch |
| Không thấy phantom dưới REPEATABLE READ | Dữ liệu ban đầu hoặc lịch chạy không đúng, hoặc đang dùng row-versioning/snapshot khác | Reset bảng và xác nhận B insert sau lần đọc đầu |
| SERIALIZABLE chặn INSERT quá rộng | Index không phù hợp hoặc query scan phạm vi lớn | Xem execution plan và thiết kế index |
| Hai transaction SNAPSHOT đều commit nhưng invariant sai | Write skew trên các dòng khác nhau | Dùng SERIALIZABLE, guard row hoặc constraint |
| SNAPSHOT báo update conflict | Transaction khác đã cập nhật cùng dòng sau snapshot | Rollback và retry toàn bộ transaction |
| Không tái hiện deadlock | Thứ tự thao tác không tạo chu trình chờ | Đồng bộ thời điểm đọc và ghi ở cả hai session |
| Lần chạy sau cho kết quả lạ | Dữ liệu hoặc isolation setting còn từ lần trước | Reset dữ liệu, rollback transaction mở và đặt lại isolation level |

## 14. Bài tập tự thực hành

Sau khi hoàn thành các thí nghiệm chính, thử thay đổi một chi tiết và dự đoán trước kết quả:

1. Trong thí nghiệm dirty read, thay ROLLBACK của A bằng COMMIT. B đọc giá trị nào và giá trị đó có trở thành dữ liệu chính thức không?
2. Trong thí nghiệm non-repeatable read, chạy A ở SNAPSHOT rồi cho B cập nhật hai lần. A có nhìn thấy lần cập nhật thứ hai không?
3. Trong thí nghiệm phantom, thêm một booking cho RoomId = 11 thay vì RoomId = 10. SERIALIZABLE của A có chặn INSERT không nếu index hỗ trợ phạm vi RoomId?
4. Trong thí nghiệm lost update, thay ghi giá trị tuyệt đối bằng phép trừ nguyên tử. Hai lần rút có còn làm mất cập nhật không?
5. Trong write skew, cho cả hai transaction cập nhật cùng một DoctorId. SNAPSHOT xử lý khác gì so với khi chúng cập nhật hai dòng riêng?
6. Trong SERIALIZABLE, thay COUNT bằng truy vấn có thêm điều kiện Status. Index nào giúp giới hạn key-range được bảo vệ?
7. Thử bật READ_COMMITTED_SNAPSHOT trong một database lab riêng và so sánh READ COMMITTED với locking READ COMMITTED. Reader có còn chờ writer không?
8. Tạo một transaction REPEATABLE READ mở lâu, cập nhật cùng bảng từ session khác rồi quan sát transaction age và dead tuple thống kê.

Với mỗi bài tập, hãy ghi lại cả kết quả query lẫn trạng thái transaction sau khi chạy. Một câu SELECT trả về cùng dữ liệu không có nghĩa hai isolation level đã dùng cùng một cơ chế; hãy quan sát thêm blocking, lock và lỗi serialization.

## 15. Checklist diễn giải kết quả

Khi đọc kết quả của một lịch hai session, hãy trả lời theo thứ tự:

- **Visibility:** Session B có nhìn thấy thay đổi chưa commit của A không?
- **Snapshot:** snapshot được lấy cho mỗi statement hay giữ đến hết transaction?
- **Locking:** reader có giữ shared/range lock không? Writer có phải chờ không?
- **Conflict detection:** database chặn, phát hiện deadlock, báo update conflict hay serialization failure?
- **Invariant:** sau khi cả hai session kết thúc, quy tắc nghiệp vụ có còn đúng không?
- **Recovery:** nếu transaction bị hủy, ứng dụng phải retry statement hay toàn bộ transaction?
- **Side effect:** có email, thanh toán hoặc message nào đã chạy ngoài database và cần idempotency không?

Đặc biệt, đừng đánh giá isolation chỉ bằng việc truy vấn có trả về cùng giá trị hay không. Có thể hai mức cho cùng kết quả nhưng một mức đạt được nhờ khóa và mức khác nhờ snapshot. Khi tải tăng, khác biệt về blocking, connection usage và retry sẽ ảnh hưởng rõ đến hệ thống.

## 16. Những nguyên tắc cần ghi nhớ

- Dùng hai connection độc lập để quan sát tương tác giữa hai transaction; cùng một connection không mô phỏng được hai session.
- READ UNCOMMITTED có thể đọc dữ liệu chưa commit; READ COMMITTED ngăn dirty read.
- READ COMMITTED thường cho snapshot mới ở mỗi câu lệnh, nên có thể xuất hiện non-repeatable read và phantom.
- REPEATABLE READ giữ kết quả đọc ổn định theo cơ chế của DBMS; SQL Server vẫn có thể thấy phantom, trong khi PostgreSQL REPEATABLE READ ngăn phantom bằng snapshot.
- SNAPSHOT dùng row versioning để giữ một snapshot transaction; nó không tự ngăn write skew trên các dòng khác nhau.
- SERIALIZABLE hướng tới việc ngăn lịch thực thi không thể sắp xếp thành một thứ tự tuần tự hợp lệ; cơ chế và các lỗi quan sát được phụ thuộc DBMS, vì vậy cần xác minh semantics của sản phẩm cụ thể.
- Cùng tên isolation level không bảo đảm cùng semantics giữa SQL Server, PostgreSQL, MySQL InnoDB và Oracle.
- Atomic UPDATE và constraint thường bảo vệ một invariant đơn giản tốt hơn mẫu SELECT rồi ghi giá trị tuyệt đối.
- Khi gặp deadlock, update conflict hoặc serialization failure, cần hiểu phạm vi rollback và retry toàn bộ logic phụ thuộc vào dữ liệu đã đọc.
- Dùng WAITFOR chỉ để đồng bộ phòng lab; transaction thật nên ngắn và không chờ người dùng hoặc dịch vụ ngoài.
- Ghi lại trạng thái ban đầu, lịch thao tác, isolation level, kết quả đọc, blocking và trạng thái cuối để thí nghiệm có thể lặp lại.

Thực nghiệm hai session biến các khái niệm isolation thành hành vi có thể quan sát. Cùng một lịch đọc và ghi có thể cho kết quả khác nhau khi snapshot, khóa và quy tắc phát hiện xung đột thay đổi. Khi bạn có thể dự đoán session nào sẽ chờ, session nào nhìn thấy phiên bản nào và transaction nào có thể bị hủy, việc chọn isolation level cho một nghiệp vụ thực tế sẽ có cơ sở rõ ràng hơn.

