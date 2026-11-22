# SQL Server: đọc có khóa, READ_COMMITTED_SNAPSHOT và SNAPSHOT

SQL Server hỗ trợ cả đọc dựa trên khóa (locking reads) và đọc dựa trên phiên bản hàng (row-versioned reads). Ba cách thường cần phân biệt là READ COMMITTED dùng khóa, READ COMMITTED khi bật READ_COMMITTED_SNAPSHOT (RCSI), và SNAPSHOT isolation.

Cả ba đều cung cấp một cách đọc dữ liệu đã commit, nhưng chúng tạo ra phạm vi nhất quán và tương tác với thao tác ghi khác nhau:

- **READ COMMITTED dùng khóa:** truy vấn đọc lấy shared lock khi cần để tránh đọc dữ liệu chưa commit. Khóa đọc thường được giải phóng khi thao tác đọc hoàn tất; nó không tạo một snapshot ổn định cho cả transaction.
- **READ COMMITTED với RCSI:** truy vấn đọc thông thường lấy phiên bản hàng đã commit tại thời điểm bắt đầu statement. Mỗi statement có snapshot riêng.
- **SNAPSHOT:** các truy vấn trong cùng transaction đọc từ một snapshot nhất quán ở cấp transaction. Snapshot được xác lập khi transaction bắt đầu truy cập dữ liệu theo cơ chế của SQL Server.

RCSI và SNAPSHOT có thể giảm chặn giữa reader và writer, nhưng không loại bỏ khóa ghi, deadlock giữa writer, khóa schema hoặc mọi dạng xung đột. Chọn đúng chế độ cần dựa vào phạm vi nhất quán nghiệp vụ, hành vi ghi, chi phí version store và cách ứng dụng xử lý lỗi.

## 1. Hai cơ chế đọc: khóa và phiên bản hàng

### 1.1. Lock-based read

Trong mô hình khóa, database cấp các khóa tương thích với thao tác đang thực hiện. Với đọc ở mức READ COMMITTED, SQL Server thường dùng shared lock để ngăn truy vấn nhìn thấy dữ liệu chưa commit.

Ví dụ:

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

BEGIN TRANSACTION;

SELECT balance
FROM dbo.Account
WHERE AccountId = 10;

COMMIT TRANSACTION;
~~~

Khi câu SELECT đọc hàng, shared lock được dùng theo quy tắc của READ COMMITTED. Một giao dịch khác muốn cập nhật cùng hàng cần khóa ghi không tương thích nên có thể phải chờ trong khoảng khóa đọc đang được giữ.

Ở mức READ COMMITTED dựa trên khóa, shared lock thường được giải phóng sau khi thao tác đọc dữ liệu tương ứng hoàn tất, thay vì được giữ đến cuối transaction như REPEATABLE READ hoặc SERIALIZABLE. Vì vậy, nếu transaction chạy hai câu SELECT cách nhau một khoảng thời gian, câu thứ hai có thể thấy giá trị mới đã commit giữa hai câu.

### 1.2. Row-versioned read

SQL Server có thể lưu các phiên bản trước của hàng khi dữ liệu được cập nhật. Reader có thể lấy phiên bản phù hợp với snapshot thay vì chờ khóa ghi trên hàng hiện tại.

Ví dụ khái niệm:

~~~text
Hàng hiện tại: balance = 900
Phiên bản trước: balance = 1000

Reader có snapshot trước khi writer commit:
    đọc phiên bản 1000

Reader bắt đầu sau khi writer commit:
    đọc phiên bản 900
~~~

Writer vẫn phải lấy khóa cần thiết để thay đổi dữ liệu hiện tại. Row versioning chủ yếu thay đổi cách reader nhìn dữ liệu và giảm nhu cầu dùng shared lock trên hàng dữ liệu.

### 1.3. Hai cơ chế có thể cùng tồn tại

SQL Server không chuyển toàn bộ database sang một mô hình duy nhất. Cấu hình database và isolation level của session quyết định hành vi mặc định của truy vấn.

Ngay cả khi bật RCSI hoặc dùng SNAPSHOT, một truy vấn có thể yêu cầu khóa bằng table hint như UPDLOCK hoặc READCOMMITTEDLOCK. Các thao tác ghi cũng tiếp tục dùng khóa để bảo vệ thay đổi.

Vì vậy, cần xác định đồng thời:

- Isolation level của session/transaction.
- Database option READ_COMMITTED_SNAPSHOT.
- Database option ALLOW_SNAPSHOT_ISOLATION.
- Table hints và query hints.
- Loại thao tác: SELECT, UPDATE, DELETE, INSERT hay locking read.
- Execution plan và tài nguyên thực tế được truy cập.

## 2. READ COMMITTED mặc định dùng khóa

### 2.1. Shared lock khi đọc

Nếu READ_COMMITTED_SNAPSHOT đang OFF, READ COMMITTED thông thường dùng shared lock để bảo vệ việc đọc.

Một shared lock có thể tương thích với shared lock khác, vì vậy nhiều reader có thể đọc cùng hàng. Shared lock không tương thích với exclusive lock cần thiết cho thao tác ghi, nên reader và writer có thể chặn nhau.

Bảng tương thích đơn giản:

| Khóa đang giữ | Khóa mới S | Khóa mới X |
|---|---:|---:|
| S | Có thể cấp | Phải chờ |
| X | Phải chờ | Phải chờ |

SQL Server có nhiều loại khóa và cấp khóa hơn S/X cơ bản, bao gồm intent locks, update locks và key-range locks. Bảng chỉ minh họa nguyên tắc.

### 2.2. Reader có thể chặn writer

Giả sử T1 đọc một hàng trong lúc statement đang đọc:

~~~sql
-- Session A
BEGIN TRANSACTION;

SELECT balance
FROM dbo.Account
WHERE AccountId = 10;

-- Giả lập công việc tiếp theo trong transaction.
WAITFOR DELAY '00:00:05';

COMMIT TRANSACTION;
~~~

Session B muốn cập nhật hàng đó:

~~~sql
-- Session B
UPDATE dbo.Account
SET balance = balance + 100
WHERE AccountId = 10;
~~~

Với READ COMMITTED dựa trên khóa, nếu shared lock của A còn được giữ khi B yêu cầu khóa xung đột, B phải chờ. Thời gian và cấp độ khóa cụ thể phụ thuộc execution plan, cấu trúc index và cách statement thực hiện.

Không nên kết luận mọi SELECT giữ khóa hàng đến COMMIT ở READ COMMITTED. Đó là khác biệt quan trọng so với REPEATABLE READ và SERIALIZABLE.

### 2.3. Writer cũng có thể chặn reader

Nếu T1 đã cập nhật một hàng nhưng chưa commit, T2 đọc hàng đó theo READ COMMITTED dựa trên khóa phải chờ T1 kết thúc để tránh đọc dữ liệu chưa commit.

~~~sql
-- Session A
BEGIN TRANSACTION;

UPDATE dbo.Account
SET balance = 900
WHERE AccountId = 10;

-- Chưa COMMIT.
~~~

~~~sql
-- Session B
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM dbo.Account
WHERE AccountId = 10;
~~~

B có thể chờ A. Nếu A COMMIT, B đọc giá trị mới; nếu A ROLLBACK, B đọc giá trị cũ.

Đây là blocking giữa reader và writer. RCSI được thiết kế để thay đổi hành vi đọc READ COMMITTED này bằng cách đọc phiên bản đã commit.

### 2.4. READ COMMITTED không tạo snapshot ổn định qua nhiều statement

Một transaction có thể đọc cùng hàng hai lần và thấy hai giá trị khác nhau:

~~~sql
BEGIN TRANSACTION;

SELECT balance
FROM dbo.Account
WHERE AccountId = 10;

-- Transaction khác cập nhật và COMMIT.

SELECT balance
FROM dbo.Account
WHERE AccountId = 10;

COMMIT TRANSACTION;
~~~

Ở READ COMMITTED dùng khóa, shared lock của lần đọc đầu không nhất thiết được giữ đến lần đọc thứ hai. Transaction khác có thể cập nhật giữa hai câu. Lần đọc sau thấy giá trị mới đã commit.

Điều này ngăn dirty read nhưng vẫn cho phép non-repeatable read và phantom theo định nghĩa của READ COMMITTED.

## 3. Bật READ_COMMITTED_SNAPSHOT

### 3.1. RCSI là database option

RCSI không phải một isolation level mới mà session chọn bằng một câu SET riêng. Đây là tùy chọn ở cấp database.

Khi bật:

- Session ở READ COMMITTED dùng row versioning cho các truy vấn đọc thông thường.
- Mỗi statement đọc snapshot của dữ liệu đã commit tại thời điểm statement bắt đầu.
- Reader thông thường không cần shared lock trên các hàng dữ liệu được đọc.
- Các thao tác ghi vẫn sử dụng khóa để bảo vệ cập nhật.

Có thể kiểm tra trạng thái:

~~~sql
SELECT
    name,
    is_read_committed_snapshot_on,
    snapshot_isolation_state_desc,
    is_accelerated_database_recovery_on
FROM sys.databases
WHERE name = DB_NAME();
~~~

Các cột được hỗ trợ tùy phiên bản SQL Server. Nếu truy vấn metadata từ database khác, hãy thay DB_NAME() bằng tên database cần kiểm tra.

### 3.2. Bật RCSI

Lệnh cấu hình:

~~~sql
ALTER DATABASE YourDatabase
SET READ_COMMITTED_SNAPSHOT ON;
~~~

Việc thay đổi tùy chọn có thể cần chờ các kết nối hoặc transaction hiện tại. Trong cửa sổ bảo trì, DBA có thể dùng:

~~~sql
ALTER DATABASE YourDatabase
SET READ_COMMITTED_SNAPSHOT ON
WITH ROLLBACK IMMEDIATE;
~~~

WITH ROLLBACK IMMEDIATE có thể ngắt các session khác và rollback transaction đang hoạt động trong database. Đây là thao tác vận hành có ảnh hưởng lớn; cần lên lịch, thông báo và xác nhận các ứng dụng đã sẵn sàng.

Tắt RCSI dùng:

~~~sql
ALTER DATABASE YourDatabase
SET READ_COMMITTED_SNAPSHOT OFF;
~~~

Không nên bật/tắt tùy chọn trên production chỉ để thử một truy vấn. Hãy đánh giá version store, connection behavior và workload trước khi thay đổi.

### 3.3. Session vẫn dùng READ COMMITTED

Sau khi RCSI được bật, ứng dụng vẫn có thể chạy:

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
~~~

Khác biệt là READ COMMITTED của database đó dùng row versioning cho đọc thông thường. Không cần sửa mọi câu SELECT hoặc thay isolation level ở từng method.

Tuy nhiên, query hint có thể thay đổi hành vi một truy vấn cụ thể. Vì vậy, bật RCSI không bảo đảm mọi SELECT đều đọc phiên bản.

## 4. RCSI cung cấp nhất quán ở cấp statement

### 4.1. Snapshot tại thời điểm bắt đầu statement

Với RCSI, mỗi statement READ COMMITTED nhìn thấy dữ liệu đã commit trước thời điểm statement bắt đầu.

Ví dụ:

~~~text
t0: Session A bắt đầu SELECT.
t1: Session B UPDATE balance và COMMIT.
t2: Session A vẫn đang đọc các hàng còn lại.

Session A tiếp tục dùng snapshot được xác lập ở t0.
Statement kế tiếp của A có thể thấy dữ liệu B đã commit tại t1.
~~~

Một statement dài không nhìn thấy nửa dữ liệu trước commit và nửa dữ liệu sau commit chỉ vì writer commit giữa chừng. Nó đọc một ảnh nhất quán tại điểm bắt đầu statement.

### 4.2. Hai statement trong cùng transaction có thể thấy hai snapshot khác nhau

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

BEGIN TRANSACTION;

SELECT balance
FROM dbo.Account
WHERE AccountId = 10;

-- Một transaction khác cập nhật và COMMIT.

SELECT balance
FROM dbo.Account
WHERE AccountId = 10;

COMMIT TRANSACTION;
~~~

Nếu RCSI bật, câu SELECT thứ nhất có snapshot tại lúc nó bắt đầu. Câu thứ hai có snapshot mới tại lúc nó bắt đầu. Vì vậy, hai câu có thể thấy giá trị khác nhau dù nằm trong cùng transaction.

RCSI giải quyết blocking và dirty read ở cấp statement, nhưng không bảo đảm repeatable read qua nhiều statement.

### 4.3. Ví dụ đọc danh sách và đọc chi tiết

Một transaction đọc tổng số đơn hàng rồi đọc danh sách:

~~~sql
BEGIN TRANSACTION;

SELECT COUNT(*)
FROM dbo.Orders
WHERE CustomerId = 42;

SELECT OrderId, TotalAmount
FROM dbo.Orders
WHERE CustomerId = 42;

COMMIT TRANSACTION;
~~~

Với RCSI, nếu một đơn hàng mới được commit giữa hai câu SELECT, câu thứ hai có thể thấy đơn mới còn COUNT ở câu đầu không tính nó.

Nếu nghiệp vụ yêu cầu cả hai kết quả phải thuộc cùng một snapshot, RCSI không đủ. Có thể cân nhắc SNAPSHOT transaction hoặc thiết kế một câu truy vấn trả kết quả cần thiết trong một statement.

### 4.4. RCSI và phantom

RCSI bảo đảm mỗi statement đọc một snapshot nhất quán. Trong cùng một statement, hàng được thêm bởi transaction khác sau thời điểm snapshot không xuất hiện trong kết quả của statement đó.

Nhưng một statement sau trong cùng transaction có thể thấy hàng mới nếu hàng đã commit trước khi statement sau bắt đầu. Vì vậy, RCSI không ngăn phantom qua nhiều statement trong một transaction.

## 5. SNAPSHOT isolation

### 5.1. SNAPSHOT là isolation level ở cấp transaction

Để sử dụng SNAPSHOT, database phải cho phép:

~~~sql
ALTER DATABASE YourDatabase
SET ALLOW_SNAPSHOT_ISOLATION ON;
~~~

Sau đó session chọn isolation level:

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;

BEGIN TRANSACTION;

SELECT balance
FROM dbo.Account
WHERE AccountId = 10;

-- Các statement tiếp theo đọc cùng snapshot transaction.

COMMIT TRANSACTION;
~~~

Transaction SNAPSHOT nhìn dữ liệu đã commit tại thời điểm snapshot của transaction được xác lập. Các statement đọc trong cùng transaction dùng cùng góc nhìn lịch sử, ngay cả khi transaction khác commit thay đổi trong lúc nó đang chạy.

SQL Server xác lập mốc snapshot khi transaction bắt đầu truy cập dữ liệu theo cơ chế snapshot. Vì vậy, nên bắt đầu transaction và thực hiện các thao tác theo một ranh giới rõ ràng; không dựa vào việc chỉ gửi BEGIN TRAN đã lập tức cố định mọi phiên bản dữ liệu.

### 5.2. SNAPSHOT khác RCSI ở phạm vi thời gian

| Đặc điểm | READ COMMITTED + RCSI | SNAPSHOT |
|---|---|---|
| Phạm vi snapshot | Mỗi statement | Cả transaction |
| Hai SELECT trong cùng transaction | Có thể thấy commit mới giữa hai câu | Cùng góc nhìn snapshot |
| Dirty read | Không | Không |
| Reader/writer blocking trên hàng dữ liệu | Giảm mạnh cho SELECT thông thường | Giảm mạnh cho SELECT thông thường |
| Writer/writer conflict | Vẫn có thể chờ khóa | Có thể chờ và có update conflict |
| Cấu hình database | READ_COMMITTED_SNAPSHOT ON | ALLOW_SNAPSHOT_ISOLATION ON |
| Chọn ở session | READ COMMITTED | SNAPSHOT |

Có thể bật cả hai tùy chọn trong cùng database. Khi đó, session READ COMMITTED dùng RCSI, còn session chọn SNAPSHOT dùng snapshot cấp transaction.

### 5.3. SNAPSHOT không phải SERIALIZABLE

SNAPSHOT cung cấp một góc nhìn nhất quán, nhưng không tự bảo đảm mọi lịch thực thi tương đương với thứ tự tuần tự.

Một transaction có thể đọc một tập dữ liệu từ snapshot, sau đó transaction khác cập nhật một hàng khác trong cùng tập logic. Nếu hai transaction ghi các hàng khác nhau, có thể không có write-write conflict để SQL Server phát hiện, dù một bất biến liên hàng bị vi phạm.

Ví dụ:

- Phải luôn có ít nhất một bác sĩ trực.
- A đọc thấy bác sĩ 1 và bác sĩ 2 đều đang trực.
- B cũng đọc cùng snapshot.
- A cập nhật bác sĩ 1 thành OFF.
- B cập nhật bác sĩ 2 thành OFF.
- Hai transaction ghi hai hàng khác nhau và có thể cùng commit dưới SNAPSHOT.
- Kết quả không còn ai trực.

Đây là write skew. Nếu bất biến này phải được bảo vệ, cần constraint phù hợp, khóa một hàng đại diện, locking hints với phạm vi thích hợp hoặc SERIALIZABLE.

## 6. Xung đột cập nhật trong SNAPSHOT

### 6.1. Hai transaction sửa cùng hàng

SNAPSHOT không cho phép một transaction âm thầm ghi đè hàng mà transaction khác đã thay đổi sau snapshot của nó.

Ví dụ:

~~~text
Ban đầu: Account 10 có balance = 1000, version logic = V1

T1 SNAPSHOT đọc V1
T2 SNAPSHOT đọc V1

T1 cập nhật balance = 900 và COMMIT
T2 cố cập nhật balance = 800

T2 phát hiện hàng đã thay đổi kể từ snapshot
T2 nhận update conflict và transaction bị hủy
~~~

SQL Server thường báo lỗi 3960 cho update conflict trong SNAPSHOT. Ứng dụng phải rollback và nếu nghiệp vụ cho phép thì chạy lại toàn bộ transaction với snapshot mới.

### 6.2. First updater wins

Khi hai transaction SNAPSHOT cùng sửa một hàng dựa trên snapshot cũ, transaction cập nhật thành công trước có thể commit; transaction còn lại không được tiếp tục ghi dựa trên phiên bản đã lỗi thời.

Đây là cách tránh lost update trong trường hợp hai writer cùng sửa một hàng. Nó không có nghĩa mọi xung đột liên quan đến nhiều hàng hoặc predicate đều tự động được phát hiện.

### 6.3. Phân biệt update conflict với deadlock

- **Update conflict:** transaction SNAPSHOT cố sửa hàng đã được transaction khác thay đổi sau snapshot của nó. SQL Server có thể trả lỗi 3960.
- **Deadlock:** có chu trình chờ khóa. SQL Server thường chọn victim và trả lỗi 1205.
- **Lock timeout:** yêu cầu khóa chờ quá thời hạn được cấu hình, thường trả lỗi 1222.
- **Constraint violation:** dữ liệu vi phạm UNIQUE, FOREIGN KEY hoặc CHECK.

Các lỗi này có chính sách phục hồi khác nhau. Không nên bắt mọi lỗi rồi retry giống nhau.

### 6.4. Update conflict cần retry toàn transaction

Giả sử T2 đã đọc số dư, tính toán thêm một số giá trị rồi mới UPDATE. Khi nhận lỗi 3960, chỉ retry câu UPDATE cuối có thể sử dụng phép tính dựa trên snapshot cũ.

Luồng an toàn:

1. Rollback transaction bị xung đột.
2. Bắt đầu transaction SNAPSHOT mới.
3. Đọc lại dữ liệu.
4. Tính lại kết quả từ snapshot mới.
5. Thực hiện các thay đổi.
6. Commit.
7. Nếu lại xung đột, áp dụng retry có giới hạn.

Nếu thao tác có tác dụng phụ bên ngoài database, cần idempotency hoặc transactional outbox để retry không gửi email, thu tiền hay phát message lặp.

## 7. Locking hints trong SQL Server

Row versioning không loại bỏ nhu cầu đọc có khóa. SQL Server có table hints để yêu cầu một truy vấn sử dụng chế độ khóa cụ thể.

### 7.1. UPDLOCK

UPDLOCK yêu cầu update lock khi đọc các hàng được truy cập. Update lock tương thích với shared lock trong một số trường hợp nhưng không tương thích với update lock khác trên cùng tài nguyên.

Ví dụ:

~~~sql
BEGIN TRANSACTION;

SELECT Quantity
FROM dbo.Inventory WITH (UPDLOCK)
WHERE Sku = 'BOOK-01';

-- Kiểm tra và tính toán.
UPDATE dbo.Inventory
SET Quantity = Quantity - 1
WHERE Sku = 'BOOK-01';

COMMIT TRANSACTION;
~~~

UPDLOCK hữu ích cho mẫu read-then-update vì nó giảm nguy cơ hai transaction cùng lấy S rồi cùng nâng lên X trên một hàng. Update lock được giữ theo transaction thay vì chỉ trong thời gian đọc thông thường.

Nó cũng làm tăng blocking: transaction khác muốn lấy update/exclusive lock trên cùng tài nguyên phải chờ. Nếu giao dịch cần nhiều hàng, vẫn phải lấy chúng theo thứ tự ổn định để tránh deadlock.

### 7.2. HOLDLOCK

HOLDLOCK tương đương SERIALIZABLE cho table reference được chỉ định. Nó giữ khóa đọc đến cuối transaction và có thể dùng key-range locks để ngăn chèn phantom trong phạm vi đã đọc.

Ví dụ kiểm tra một mã chưa tồn tại rồi thêm:

~~~sql
BEGIN TRANSACTION;

IF NOT EXISTS (
    SELECT 1
    FROM dbo.Reservation WITH (UPDLOCK, HOLDLOCK)
    WHERE RoomId = 10
      AND StartTime = '2026-12-01T10:00:00'
)
BEGIN
    INSERT INTO dbo.Reservation (RoomId, StartTime)
    VALUES (10, '2026-12-01T10:00:00');
END;

COMMIT TRANSACTION;
~~~

Ví dụ chỉ minh họa ý tưởng bảo vệ predicate. Điều kiện thực tế về lịch đặt thường cần kiểm tra khoảng thời gian chồng lấn, index phù hợp và constraint bổ sung. Một truy vấn không có index thích hợp có thể khóa phạm vi rộng hơn dự kiến.

Nếu quy tắc có thể được biểu diễn bằng UNIQUE hoặc exclusion constraint phù hợp, constraint thường là lớp bảo vệ trực tiếp hơn.

### 7.3. READCOMMITTEDLOCK

Khi RCSI bật, truy vấn READ COMMITTED thông thường dùng row versioning. READCOMMITTEDLOCK yêu cầu truy vấn cụ thể dùng locking READ COMMITTED.

Ví dụ:

~~~sql
SELECT AccountId, Balance
FROM dbo.Account WITH (READCOMMITTEDLOCK)
WHERE AccountId = 10;
~~~

Hint này hữu ích khi một ứng dụng cần hành vi đọc có khóa cho một truy vấn cụ thể trong database đã bật RCSI.

Nó không biến cả transaction thành SERIALIZABLE và không giữ shared lock đến cuối transaction theo cách của REPEATABLE READ. Muốn giữ khóa hoặc bảo vệ phạm vi, cần chọn mức cô lập/hint tương ứng như UPDLOCK hoặc HOLDLOCK và hiểu tác động.

### 7.4. NOLOCK và READUNCOMMITTED

NOLOCK yêu cầu hành vi tương tự READ UNCOMMITTED cho bảng được tham chiếu. Nó có thể đọc dữ liệu chưa commit và trả kết quả không nhất quán.

Ví dụ:

~~~sql
SELECT *
FROM dbo.Account WITH (NOLOCK)
WHERE AccountId = 10;
~~~

Các rủi ro gồm:

- Dirty read: đọc thay đổi có thể rollback.
- Non-repeatable read.
- Phantom.
- Đọc thiếu hoặc lặp hàng trong một số tình huống truy cập đồng thời.
- Kết quả không phù hợp để tính số dư, tồn kho hoặc quyết định nghiệp vụ.

NOLOCK không có nghĩa “không lấy bất kỳ khóa nào”. SQL Server vẫn có thể lấy schema stability lock (Sch-S) khi biên dịch và thực thi. Truy vấn vẫn có thể bị chặn bởi schema modification lock (Sch-M).

NOLOCK/READUNCOMMITTED không phải cách sửa chung cho blocking. SQL Server cũng không cho phép dùng các hint này như cách hợp lệ để thay đổi hành vi đọc bảng mục tiêu của UPDATE/DELETE; hỗ trợ trên target table đã bị hạn chế và có thể bị loại bỏ trong tương lai.

### 7.5. READPAST

READPAST yêu cầu bỏ qua các hàng đang bị khóa thay vì chờ chúng trong những trường hợp được hỗ trợ. Nó thường được dùng trong mô hình queue để nhiều worker lấy các công việc khác nhau.

Ví dụ minh họa cho database đang dùng locking READ COMMITTED:

~~~sql
BEGIN TRANSACTION;

SELECT TOP (1) QueueId, Payload
FROM dbo.WorkQueue WITH (UPDLOCK, READPAST, ROWLOCK)
WHERE Status = 'READY'
ORDER BY CreatedAt, QueueId;

-- Đánh dấu hoặc xử lý hàng đã nhận trong transaction.

COMMIT TRANSACTION;
~~~

READPAST có giới hạn:

- Chủ yếu bỏ qua row-level locks; nó không bảo đảm bỏ qua page locks.
- Kết quả có thể không đầy đủ vì hàng đang khóa bị bỏ qua.
- Không phù hợp với truy vấn cần đọc toàn bộ tập dữ liệu chính xác.
- Hành vi phụ thuộc isolation level và RCSI.
- Khi RCSI bật và session ở READ COMMITTED, cần dùng locking semantics phù hợp; quy tắc kết hợp READPAST với READCOMMITTEDLOCK/UPDLOCK phải được kiểm tra theo phiên bản SQL Server và cú pháp table hints được hỗ trợ.

Không dùng READPAST để che giấu contention trong truy vấn nghiệp vụ cần đủ dữ liệu. Với queue, cần thêm lease/visibility timeout, trạng thái claim, retry và xử lý worker crash.

### 7.6. ROWLOCK, PAGLOCK và TABLOCK

Các hint này gợi ý mức granularity khóa:

- ROWLOCK: ưu tiên khóa hàng/key.
- PAGLOCK: ưu tiên khóa page.
- TABLOCK: khóa ở cấp bảng theo mode phù hợp.

Chúng không phải bảo đảm tuyệt đối rằng engine sẽ chỉ dùng đúng cấp khóa đó. SQL Server có thể chọn cấp khóa khác hoặc lock escalation theo điều kiện và cấu hình.

Không nên thêm ROWLOCK vào mọi truy vấn với kỳ vọng luôn tăng concurrency. Một lượng lớn row lock có thể tạo overhead và bộ nhớ lock lớn; page/table lock đôi khi hiệu quả hơn.

## 8. Khi nào RCSI vẫn có khóa?

### 8.1. Schema stability lock

Truy vấn đọc dưới RCSI vẫn có thể lấy Sch-S lock để bảo vệ metadata trong lúc biên dịch và thực thi. DDL cần Sch-M lock có thể chờ Sch-S, và ngược lại.

Vì vậy, một SELECT dùng row versioning vẫn có thể bị chặn bởi thao tác thay đổi schema.

### 8.2. Locking hints

Các hint như UPDLOCK, HOLDLOCK, READCOMMITTEDLOCK có thể yêu cầu khóa dữ liệu ngay cả khi RCSI bật.

Nếu một truy vấn RCSI có thời gian chờ khóa, hãy kiểm tra hint và isolation level trước khi kết luận row versioning không hoạt động.

### 8.3. DML vẫn khóa dữ liệu

UPDATE, DELETE và INSERT phải bảo vệ các thay đổi. SQL Server vẫn dùng exclusive/update locks, khóa index key và các khóa liên quan đến ràng buộc.

RCSI chủ yếu giảm xung đột reader-writer. Hai writer cùng sửa một hàng vẫn có thể chờ nhau. Deadlock giữa writer vẫn có thể xảy ra.

### 8.4. Key-range locks khi yêu cầu SERIALIZABLE

Nếu session dùng SERIALIZABLE hoặc truy vấn dùng HOLDLOCK, SQL Server có thể dùng key-range locks để bảo vệ predicate. Row versioning của database không tự vô hiệu hóa yêu cầu bảo vệ phạm vi do locking hint/isolation level đưa ra.

## 9. Row version store và chi phí vận hành

### 9.1. Phiên bản cũ phải được lưu

Khi một writer cập nhật hàng, SQL Server có thể cần lưu phiên bản trước để các reader đang dùng snapshot tiếp tục nhìn thấy dữ liệu đúng thời điểm.

Điều này tạo thêm chi phí:

- Dung lượng lưu phiên bản.
- Ghi thêm dữ liệu và log.
- CPU để tạo/tra cứu phiên bản.
- Công việc cleanup phiên bản không còn cần thiết.
- Áp lực lên tempdb hoặc persistent version store.

RCSI và SNAPSHOT giảm một số chi phí chờ khóa nhưng chuyển một phần chi phí sang quản lý phiên bản.

### 9.2. Version store trong tempdb

Trong nhiều cấu hình SQL Server truyền thống, row versions phục vụ RCSI/SNAPSHOT được lưu trong version store của tempdb.

Cần theo dõi dung lượng tempdb, tốc độ tăng version store, I/O và khả năng mở rộng file. Nếu tempdb đầy hoặc chịu áp lực I/O, các truy vấn dùng row versioning có thể bị ảnh hưởng.

### 9.3. Persistent Version Store khi bật ADR

Khi Accelerated Database Recovery (ADR) được bật, SQL Server sử dụng Persistent Version Store (PVS) trong database thay vì version store truyền thống trong tempdb cho các phiên bản thuộc cơ chế ADR. Điều này thay đổi nơi cần giám sát dung lượng và cleanup.

Không nên mặc định mọi phiên bản hàng đều nằm trong tempdb. Hãy kiểm tra ADR và kiến trúc phiên bản của phiên bản SQL Server đang triển khai.

### 9.4. Transaction SNAPSHOT dài giữ phiên bản lâu

Một transaction SNAPSHOT tồn tại lâu có thể vẫn cần các phiên bản cũ để duy trì góc nhìn nhất quán. Điều này trì hoãn việc dọn dẹp những version còn được transaction tham chiếu.

Ví dụ, một báo cáo mở transaction rồi xử lý dữ liệu trong 30 phút có thể giữ version store lớn hơn nhiều so với một truy vấn ngắn.

Hãy tránh giữ transaction SNAPSHOT mở trong khi:

- Chờ người dùng nhập liệu.
- Gọi dịch vụ HTTP bên ngoài.
- Chạy tác vụ CPU dài không cần database.
- Chờ queue hoặc semaphore.
- Xử lý file lớn.

### 9.5. Theo dõi version store

Có thể xem mức sử dụng version store theo database:

~~~sql
SELECT
    DB_NAME(database_id) AS database_name,
    reserved_page_count,
    reserved_space_kb
FROM sys.dm_tran_version_store_space_usage;
~~~

Có thể xem dung lượng version store trong tempdb:

~~~sql
SELECT
    version_store_reserved_page_count,
    version_store_reserved_page_count * 8.0 / 1024 AS version_store_mb
FROM tempdb.sys.dm_db_file_space_usage;
~~~

Các DMV và cột khả dụng phụ thuộc phiên bản/quyền. Nếu ADR dùng PVS, cần theo dõi không gian PVS trong database theo các DMV tương ứng, ví dụ thông tin persistent version store/ADR mà phiên bản cung cấp.

### 9.6. Tìm transaction snapshot đang hoạt động

Có thể xem các transaction đang giữ snapshot:

~~~sql
SELECT
    transaction_id,
    transaction_sequence_num,
    first_snapshot_sequence_num,
    elapsed_time_seconds,
    session_id,
    is_snapshot
FROM sys.dm_tran_active_snapshot_database_transactions;
~~~

Thông tin này giúp tìm transaction sống lâu có thể ngăn cleanup version store. Hãy kết hợp với sys.dm_exec_sessions, sys.dm_exec_requests và SQL text để xác định ứng dụng/luồng tạo transaction đó.

## 10. So sánh ba cách đọc bằng timeline

### 10.1. Lock-based READ COMMITTED

~~~text
T1: SELECT đọc hàng A và lấy S
T2: UPDATE A cần X -> chờ nếu S còn giữ
T1: đọc xong phần dữ liệu tương ứng, S được giải phóng
T2: tiếp tục UPDATE và COMMIT
~~~

Reader có thể chặn writer trong thời gian khóa đọc còn hiệu lực. Một statement sau của T1 có thể thấy dữ liệu T2 đã commit.

### 10.2. READ COMMITTED với RCSI

~~~text
T1: bắt đầu SELECT, snapshot S1
T2: UPDATE A và COMMIT
T1: tiếp tục SELECT, vẫn nhìn snapshot S1
T1: statement kết thúc

T1: bắt đầu SELECT thứ hai, snapshot S2
T1: có thể thấy thay đổi của T2
~~~

Reader thông thường không chờ writer trên row data vì đọc phiên bản. Hai statement khác nhau có thể thấy hai trạng thái commit khác nhau.

### 10.3. SNAPSHOT

~~~text
T1: bắt đầu transaction và xác lập snapshot S1
T1: SELECT A từ S1

T2: UPDATE A và COMMIT

T1: SELECT A lần nữa, vẫn đọc S1
T1: nếu cố UPDATE A đã bị T2 thay đổi, có thể nhận update conflict
~~~

Các statement đọc trong T1 có cùng góc nhìn. Nếu T1 ghi một hàng đã bị thay đổi sau snapshot, transaction có thể bị hủy.

## 11. Ví dụ lựa chọn theo nhu cầu nghiệp vụ

### 11.1. Dashboard cần đọc không chặn cập nhật

Một dashboard đọc số liệu thường xuyên trong khi API cập nhật dữ liệu. Nếu dashboard chấp nhận snapshot nhất quán tại thời điểm mỗi statement, RCSI có thể giảm blocking reader-writer.

Nếu dashboard chạy nhiều câu SELECT và cần mọi kết quả thuộc cùng một thời điểm, SNAPSHOT có thể phù hợp hơn. Cần cân nhắc transaction dài và version store.

### 11.2. Luồng đọc rồi cập nhật một hàng

Một ứng dụng đọc tồn kho, kiểm tra điều kiện rồi cập nhật:

~~~sql
BEGIN TRANSACTION;

SELECT Quantity
FROM dbo.Inventory
WHERE Sku = 'BOOK-01';

-- Kiểm tra và cập nhật.
UPDATE dbo.Inventory
SET Quantity = Quantity - 1
WHERE Sku = 'BOOK-01';

COMMIT TRANSACTION;
~~~

Nếu nhiều request chạy đồng thời, chỉ đọc bằng RCSI rồi cập nhật sau đó có thể không bảo vệ điều kiện theo cách ứng dụng kỳ vọng. Có thể dùng một UPDATE nguyên tử có điều kiện:

~~~sql
UPDATE dbo.Inventory
SET Quantity = Quantity - 1
WHERE Sku = 'BOOK-01'
  AND Quantity >= 1;
~~~

Hoặc dùng UPDLOCK trong transaction khi cần đọc và quyết định trên cùng hàng. Hãy chọn cách đơn giản nhất có thể diễn đạt bất biến trực tiếp.

### 11.3. Báo cáo cần nhiều câu SELECT cùng snapshot

Nếu nghiệp vụ yêu cầu các truy vấn chi tiết, tổng hợp và danh sách đều phản ánh cùng một trạng thái dữ liệu, SNAPSHOT transaction cung cấp góc nhìn nhất quán qua nhiều statement.

RCSI không bảo đảm điều này vì mỗi statement có snapshot riêng.

### 11.4. Queue worker lấy việc

Queue worker thường muốn claim một hàng mà worker khác đang xử lý sẽ bị bỏ qua. READPAST kết hợp locking hints có thể phù hợp trong mô hình queue của SQL Server.

Nhưng queue cần quản lý trạng thái claim và lease. Nếu worker chết sau khi claim, hàng phải có thể được xử lý lại sau thời hạn. READPAST chỉ là một phần của cơ chế phân phối việc.

### 11.5. Bất biến liên hàng

Nếu một quy tắc phụ thuộc nhiều hàng hoặc predicate, chẳng hạn giới hạn số người đăng ký, SNAPSHOT có thể không đủ vì write skew. Hãy xem xét:

- UNIQUE/filtered unique index nếu biểu diễn được.
- SERIALIZABLE khi cần bảo vệ predicate.
- UPDLOCK/HOLDLOCK trên phạm vi có index phù hợp.
- Guard row được mọi writer cập nhật.
- Thiết kế mô hình dữ liệu để biến quy tắc thành điều kiện trên một hàng.

## 12. Locking read với UPDLOCK và HOLDLOCK

### 12.1. Tránh hai giao dịch cùng đọc rồi nâng khóa

Một tình huống phổ biến:

~~~text
T1: SELECT hàng A với S
T2: SELECT hàng A với S
T1: muốn UPDATE, yêu cầu X và chờ T2
T2: muốn UPDATE, yêu cầu X và chờ T1
~~~

Hai shared lock ban đầu tương thích, nhưng hai yêu cầu nâng lên exclusive có thể tạo conversion deadlock.

Nếu transaction biết chắc sẽ cập nhật hàng, UPDLOCK có thể lấy update lock ngay ở bước đọc:

~~~sql
BEGIN TRANSACTION;

SELECT Quantity
FROM dbo.Inventory WITH (UPDLOCK)
WHERE Sku = 'BOOK-01';

UPDATE dbo.Inventory
SET Quantity = Quantity - 1
WHERE Sku = 'BOOK-01';

COMMIT TRANSACTION;
~~~

Hai transaction không thể cùng giữ U trên cùng tài nguyên theo cách tạo conversion deadlock đó; một transaction phải chờ ngay từ bước đọc.

### 12.2. Bảo vệ hàng chưa tồn tại

UPDLOCK trên một hàng chưa tồn tại không tự động tạo khóa hàng cho giá trị đó. Nếu quy tắc là “không có bản ghi nào trong phạm vi này”, cần bảo vệ predicate/range.

HOLDLOCK hoặc SERIALIZABLE có thể dùng key-range locks khi có access path thích hợp. UNIQUE constraint vẫn là lựa chọn tốt hơn cho tính duy nhất đơn giản.

### 12.3. Hạn chế của locking hints

Locking hints làm thay đổi concurrency. Chúng có thể:

- Tăng blocking.
- Tạo deadlock nếu thứ tự lấy khóa không thống nhất.
- Làm giảm lợi ích RCSI.
- Khiến một truy vấn khóa nhiều key/range hơn dự kiến nếu plan scan rộng.
- Tạo hành vi khó hiểu khi kết hợp nhiều hint.

Dùng hint ở phạm vi nhỏ, có lý do nghiệp vụ và kiểm thử dưới tải đồng thời.

## 13. Phân biệt row versioning isolation với cột rowversion

SQL Server có kiểu dữ liệu rowversion (trước đây thường gọi là timestamp). Nó là một giá trị nhị phân tăng theo database khi hàng có cột rowversion được INSERT/UPDATE.

Ví dụ:

~~~sql
CREATE TABLE dbo.Product (
    ProductId INT PRIMARY KEY,
    Price DECIMAL(12, 2) NOT NULL,
    RowVer ROWVERSION
);
~~~

Ứng dụng có thể dùng giá trị này để optimistic concurrency:

~~~sql
UPDATE dbo.Product
SET Price = 120.00
WHERE ProductId = 501
  AND RowVer = @ExpectedRowVer;
~~~

Nếu row count bằng 0, hàng có thể đã bị thay đổi hoặc không tồn tại.

Cột rowversion không phải cơ chế row version store của RCSI/SNAPSHOT:

| Khái niệm | Mục đích |
|---|---|
| Row versioning isolation | Lưu phiên bản dữ liệu để reader có snapshot |
| Cột rowversion | Token phát hiện hàng đã thay đổi giữa lần đọc và ghi |
| RCSI | Snapshot ở cấp statement cho READ COMMITTED |
| SNAPSHOT | Snapshot ở cấp transaction |

Một database có thể dùng RCSI/SNAPSHOT mà không có cột rowversion trong bảng. Ngược lại, bảng có cột rowversion không tự động bật row-versioned reads.

## 14. Các hạn chế và tương tác cần biết

### 14.1. RCSI không loại bỏ writer-writer blocking

Hai transaction cùng cập nhật một hàng vẫn phải phối hợp bằng khóa. Một transaction có thể chờ transaction kia commit/rollback.

RCSI giảm việc SELECT thông thường chặn UPDATE và UPDATE chặn SELECT, nhưng không biến ghi thành lock-free.

### 14.2. SNAPSHOT vẫn có thể deadlock

Mặc dù đọc snapshot không cần shared lock dữ liệu thông thường, transaction vẫn có thể lấy khóa cho UPDATE/DELETE, index maintenance, ràng buộc, schema và locking hints.

Hai writer cập nhật nhiều bảng theo thứ tự ngược nhau vẫn có thể tạo deadlock.

### 14.3. DDL và schema locks

SELECT dưới RCSI/SNAPSHOT vẫn cần schema stability lock. Một thao tác DDL cần schema modification lock có thể chờ truy vấn đang chạy.

### 14.4. Truy vấn dùng hint có thể không đọc version

Nếu query dùng READCOMMITTEDLOCK, UPDLOCK hoặc HOLDLOCK, nó có thể yêu cầu khóa thay vì hành vi row-versioned mặc định. Hãy xem plan và lock waits để xác nhận.

### 14.5. SNAPSHOT và constraint

SQL Server vẫn kiểm tra UNIQUE, FOREIGN KEY và CHECK theo semantics của constraint. Nhưng một bất biến nghiệp vụ phức tạp giữa nhiều hàng không tự động được bảo vệ chỉ vì transaction dùng SNAPSHOT.

### 14.6. Snapshot không thay thế optimistic version ở API

Một transaction SNAPSHOT bảo vệ góc nhìn bên trong database transaction. Nếu người dùng mở biểu mẫu trong 30 phút rồi gửi cập nhật ở một request mới, transaction mới không giữ snapshot từ lúc biểu mẫu được mở.

Nếu cần phát hiện dữ liệu đã thay đổi kể từ lần người dùng đọc, hãy dùng cột rowversion/ETag hoặc một token phiên bản nghiệp vụ ở API.

## 15. Chẩn đoán lock waits và row versioning

### 15.1. Xem isolation và cấu hình database

Có thể kiểm tra isolation level của session qua:

~~~sql
DBCC USEROPTIONS;
~~~

Có thể kiểm tra database options:

~~~sql
SELECT
    name,
    is_read_committed_snapshot_on,
    snapshot_isolation_state_desc
FROM sys.databases
WHERE name = DB_NAME();
~~~

Đừng chỉ nhìn connection string. Isolation level có thể được thay đổi trong session hoặc transaction; database option quyết định READ COMMITTED có dùng row versioning hay không.

### 15.2. Xem request đang chờ

~~~sql
SELECT
    session_id,
    blocking_session_id,
    wait_type,
    wait_time,
    wait_resource,
    status,
    command
FROM sys.dm_exec_requests
WHERE blocking_session_id <> 0;
~~~

Các wait type như LCK_M_S, LCK_M_U, LCK_M_X có thể cho thấy chờ khóa. Kết hợp session, SQL text và execution plan để xác định bên chặn.

Nếu RCSI bật mà truy vấn vẫn chờ LCK, hãy xem nó có dùng locking hint, đang thực hiện DML, chờ schema lock hay chờ tài nguyên khóa khác không.

### 15.3. Xem khóa đang được giữ

~~~sql
SELECT
    request_session_id,
    resource_type,
    resource_description,
    request_mode,
    request_status
FROM sys.dm_tran_locks
ORDER BY request_session_id, resource_type;
~~~

Cần kết hợp với request/session để hiểu resource và mode. Một khóa có thể là khóa intent, key, page, object hoặc application lock.

### 15.4. Xem transaction đang hoạt động

~~~sql
SELECT
    transaction_id,
    transaction_sequence_num,
    first_snapshot_sequence_num,
    elapsed_time_seconds,
    session_id,
    is_snapshot
FROM sys.dm_tran_active_snapshot_database_transactions;
~~~

Transaction tồn tại lâu có thể giữ version cần thiết. Tìm ứng dụng mở transaction quá lâu hoặc không kết thúc đúng cách.

### 15.5. Xem version store

Với tempdb version store:

~~~sql
SELECT
    version_store_reserved_page_count * 8.0 / 1024 AS version_store_mb
FROM tempdb.sys.dm_db_file_space_usage;
~~~

Với từng database:

~~~sql
SELECT
    DB_NAME(database_id) AS database_name,
    reserved_page_count,
    reserved_space_kb
FROM sys.dm_tran_version_store_space_usage;
~~~

Nếu dùng ADR/PVS, xem thêm các DMV liên quan PVS/ADR được hỗ trợ trong phiên bản đang chạy.

### 15.6. Đọc execution plan

Plan giúp biết truy vấn đọc hoặc khóa những index/key nào. Một scan rộng có thể:

- Tăng thời gian statement.
- Tăng số hàng bị khóa trong locking read.
- Tăng vùng key-range được bảo vệ ở SERIALIZABLE.
- Tăng công việc đọc phiên bản.
- Kéo dài thời gian transaction giữ khóa ghi.

RCSI không làm một truy vấn scan toàn bảng trở nên miễn phí. Nó giảm một số chờ khóa, nhưng CPU, I/O và version-store lookup vẫn tồn tại.

## 16. Chuyển từ locking READ COMMITTED sang RCSI

### 16.1. Lợi ích tiềm năng

RCSI có thể phù hợp khi:

- Workload có nhiều reader và writer cùng truy cập bảng.
- SELECT thông thường thường bị chặn bởi UPDATE.
- Reader không cần giữ shared lock đến cuối transaction.
- Mỗi statement chỉ cần một ảnh nhất quán riêng.
- Ứng dụng không dựa vào việc SELECT tự khóa để bảo vệ read-then-write.

RCSI thường giảm lock waits giữa reader/writer và cải thiện concurrency của workload đọc nhiều.

### 16.2. Rủi ro và việc cần kiểm tra

Trước khi bật:

- Xác định transaction nào dựa vào locking READ COMMITTED.
- Tìm SELECT rồi UPDATE mà thiếu atomic conditional UPDATE hoặc UPDLOCK.
- Kiểm tra code dùng NOLOCK/READPAST/READCOMMITTEDLOCK.
- Đo tempdb hoặc PVS capacity.
- Xác định transaction/statement dài.
- Kiểm tra trigger, stored procedure và batch.
- Đánh giá thay đổi hành vi của báo cáo nhiều statement.
- Kiểm tra test và monitoring sau khi bật.

Một số ứng dụng có thể đã dựa vào blocking để tuần tự hóa một phần thao tác. Khi RCSI loại bỏ shared lock của SELECT thông thường, race condition trong logic ứng dụng có thể lộ ra. Cần bảo vệ các bất biến bằng UPDATE nguyên tử, constraint hoặc locking hint có chủ đích.

### 16.3. Kế hoạch chuyển đổi

Một quy trình thực tế:

1. Đo baseline: lock waits, deadlocks, query latency, tempdb, throughput.
2. Liệt kê các transaction read-then-write và predicate checks.
3. Sửa các thao tác cần atomic conditional UPDATE hoặc explicit locking.
4. Kiểm tra truy vấn dùng hints có thể xung đột với RCSI.
5. Ước lượng version store và cấu hình tempdb/PVS.
6. Bật RCSI trong cửa sổ thay đổi có kế hoạch.
7. Chạy kiểm thử chức năng và tải đồng thời.
8. So sánh lock waits, CPU, I/O, version store, latency và deadlocks.
9. Theo dõi transaction dài và cleanup.
10. Chuẩn bị kế hoạch rollback cấu hình nếu có vấn đề.

### 16.4. Không chuyển mọi transaction sang SNAPSHOT theo mặc định

SNAPSHOT hữu ích khi cần transaction-level consistency, nhưng nó có update conflict và version retention dài hơn cho transaction kéo dài.

Nếu nhu cầu chỉ là giảm reader/writer blocking cho từng SELECT, RCSI có thể đơn giản hơn. Nếu cần nhiều statement nhìn cùng một trạng thái, SNAPSHOT đáng cân nhắc. Nếu cần bảo vệ predicate và bất biến liên hàng, SERIALIZABLE hoặc constraint/locking design có thể phù hợp hơn.

## 17. Ma trận chọn cơ chế

| Nhu cầu | Cơ chế nên xem xét | Lưu ý |
|---|---|---|
| Đọc đã commit, chấp nhận blocking ngắn | READ COMMITTED locking | Shared locks có thể chặn writer |
| Giảm reader/writer blocking, snapshot từng câu | READ COMMITTED + RCSI | Hai statement có thể thấy snapshot khác nhau |
| Nhiều statement cần cùng snapshot | SNAPSHOT | Transaction dài giữ version lâu; update conflict |
| Đọc rồi cập nhật cùng hàng | UPDLOCK hoặc atomic UPDATE | Tăng blocking có chủ đích |
| Bảo vệ khoảng/điều kiện không có hàng | SERIALIZABLE/HOLDLOCK hoặc constraint | Cần index và xử lý lock range |
| Queue worker bỏ qua hàng đang xử lý | READPAST với locking pattern | Có thể bỏ qua hàng; cần lease/recovery |
| Đọc dữ liệu không quan trọng, chấp nhận dirty read | READ UNCOMMITTED/NOLOCK chỉ trong trường hợp rất đặc biệt | Kết quả có thể sai; không phải giải pháp chung |
| Phát hiện client ghi dựa trên dữ liệu cũ | rowversion/ETag/optimistic concurrency | Khác row-versioned isolation |

## 18. Ví dụ: cùng một truy vấn dưới ba chế độ

### 18.1. READ COMMITTED locking

~~~sql
-- Session A
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
BEGIN TRANSACTION;

SELECT Balance
FROM dbo.Account
WHERE AccountId = 10;

WAITFOR DELAY '00:00:05';

COMMIT TRANSACTION;
~~~

~~~sql
-- Session B
UPDATE dbo.Account
SET Balance = Balance + 100
WHERE AccountId = 10;
~~~

Tùy thời điểm B chạy và thời gian khóa đọc còn được giữ, B có thể phải chờ. Nếu B commit trước câu SELECT thứ hai của A, lần đọc thứ hai có thể thấy giá trị mới.

### 18.2. READ COMMITTED với RCSI

Bật RCSI ở database, sau đó chạy cùng session A:

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
BEGIN TRANSACTION;

SELECT Balance
FROM dbo.Account
WHERE AccountId = 10;

WAITFOR DELAY '00:00:05';

SELECT Balance
FROM dbo.Account
WHERE AccountId = 10;

COMMIT TRANSACTION;
~~~

Nếu B cập nhật và commit trong lúc A chờ, câu SELECT đầu vẫn thấy snapshot tại lúc nó bắt đầu. Câu SELECT thứ hai có snapshot mới và có thể thấy Balance mới.

A không cần giữ shared row lock để đọc dữ liệu đã commit.

### 18.3. SNAPSHOT

Bật ALLOW_SNAPSHOT_ISOLATION ở database:

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
BEGIN TRANSACTION;

SELECT Balance
FROM dbo.Account
WHERE AccountId = 10;

WAITFOR DELAY '00:00:05';

SELECT Balance
FROM dbo.Account
WHERE AccountId = 10;

COMMIT TRANSACTION;
~~~

Hai SELECT trong A đọc cùng snapshot. Nếu B commit thay đổi giữa hai câu, A vẫn thấy giá trị cũ trong cả transaction.

Nếu A cố cập nhật hàng đã bị B thay đổi kể từ snapshot, A có thể nhận update conflict.

## 19. Những nhầm lẫn thường gặp

**“Bật RCSI nghĩa là database không còn khóa.”**

Sai. DML vẫn lấy khóa; schema locks và explicit locking hints vẫn tồn tại. RCSI chủ yếu giảm shared locks cho SELECT READ COMMITTED thông thường.

**“RCSI và SNAPSHOT giống nhau.”**

Sai. RCSI tạo snapshot riêng cho mỗi statement; SNAPSHOT giữ một snapshot xuyên suốt transaction.

**“SNAPSHOT tương đương SERIALIZABLE.”**

Sai. SNAPSHOT không tự ngăn mọi write skew hoặc predicate anomaly. SERIALIZABLE cung cấp bảo vệ mạnh hơn đối với lịch thực thi và có thể dùng key-range locks.

**“SELECT dưới RCSI không bao giờ bị chặn.”**

Sai. Nó vẫn có thể chờ schema modification lock, explicit locks hoặc tài nguyên khác; query hints có thể yêu cầu locking reads.

**“UPDLOCK chỉ khóa trong lúc SELECT.”**

Sai. Update lock được giữ theo transaction, giúp bảo vệ bước đọc rồi cập nhật nhưng làm tăng thời gian blocking.

**“NOLOCK không lấy bất kỳ khóa nào.”**

Sai. Nó vẫn có thể lấy schema stability lock và có thể bị Sch-M chặn. Nó cũng cho phép dirty/inconsistent reads.

**“READPAST luôn lấy hàng đầu tiên trong queue.”**

Sai. Nó có thể bỏ qua hàng bị khóa và chọn hàng tiếp theo theo plan/order; page locks và điều kiện khác vẫn ảnh hưởng. Cần thiết kế queue semantics rõ ràng.

**“Có cột rowversion thì đã bật SNAPSHOT.”**

Sai. rowversion là token trên hàng cho optimistic concurrency; nó không phải row version store của isolation.

**“RCSI giải quyết lost update trong mọi read-then-write.”**

Sai. RCSI chỉ thay đổi cách SELECT đọc. Dùng atomic conditional UPDATE, UPDLOCK hoặc cơ chế khác để bảo vệ quyết định cập nhật.

**“Snapshot transaction luôn có thể commit nếu chỉ ghi các hàng khác nhau.”**

Không chắc. Các ràng buộc và xung đột khác vẫn có thể làm transaction thất bại; đồng thời các bất biến liên hàng có thể bị write skew nếu không được bảo vệ.

**“Tăng tempdb là cách duy nhất xử lý version store.”**

Sai. Cần tìm transaction dài, workload tạo version lớn, cleanup, ADR/PVS và I/O. Tăng dung lượng có thể cần thiết nhưng không thay thế việc xử lý nguyên nhân.

## 20. Quy trình điều tra một truy vấn bị chặn trong SQL Server

Khi SELECT hoặc DML bị chậm do blocking, hãy làm theo trình tự:

1. Xác định session đang chờ, blocker và wait type trong sys.dm_exec_requests.
2. Xem isolation level của session bằng DBCC USEROPTIONS.
3. Kiểm tra database có bật RCSI và ALLOW_SNAPSHOT_ISOLATION không.
4. Đọc SQL text và table hints để tìm UPDLOCK, HOLDLOCK, READCOMMITTEDLOCK, NOLOCK hoặc READPAST.
5. Xem sys.dm_tran_locks để xác định resource type và lock mode.
6. Xem transaction age để tìm session giữ khóa lâu hoặc idle in transaction.
7. Đọc actual execution plan để xác định index seek/scan và số hàng truy cập.
8. Nếu dùng RCSI/SNAPSHOT, xem version store và active snapshot transactions.
9. Phân biệt lock wait, deadlock, update conflict và serialization/constraint error.
10. Sửa theo nhu cầu: RCSI, SNAPSHOT, atomic UPDATE, explicit locking, index hoặc transaction boundary.
11. Chạy lại test đồng thời và so sánh latency, blocking, deadlocks, tempdb/PVS và kết quả nghiệp vụ.

## 21. Checklist trước khi chọn RCSI hoặc SNAPSHOT

- Ứng dụng có cần một snapshot cho từng câu hay cho cả transaction?
- Có transaction đọc nhiều statement và yêu cầu dữ liệu nhất quán xuyên suốt không?
- Có luồng SELECT rồi UPDATE đang dựa vào shared lock không?
- Có thể chuyển logic thành một UPDATE có điều kiện nguyên tử không?
- Có bất biến liên hàng hoặc predicate cần SERIALIZABLE/constraint không?
- Có table hint nào buộc locking read hoặc thay đổi semantics không?
- Workload có transaction dài giữ snapshot không?
- tempdb hoặc PVS có đủ dung lượng và I/O không?
- Các writer có thể tạo update conflict hoặc deadlock không?
- Ứng dụng phân biệt lỗi 3960, 1205 và 1222 chưa?
- Retry có chạy lại toàn transaction và an toàn với tác dụng phụ không?
- Có monitoring cho lock waits, active snapshots và version store không?

SQL Server cung cấp nhiều lựa chọn đọc để cân bằng blocking và tính nhất quán. READ COMMITTED dựa trên khóa bảo vệ việc đọc bằng shared lock; RCSI thay các lần đọc READ COMMITTED thông thường bằng snapshot ở cấp statement; SNAPSHOT giữ một góc nhìn ổn định cho cả transaction. Khi chọn chế độ, hãy bắt đầu từ yêu cầu nhất quán của nghiệp vụ, rồi xem xét locking hints, hành vi ghi, update conflict và chi phí version store. Row versioning giúp reader và writer ít cản trở nhau hơn, nhưng mọi bất biến cần được bảo vệ rõ ràng bằng constraint, atomic update hoặc khóa có chủ đích.
