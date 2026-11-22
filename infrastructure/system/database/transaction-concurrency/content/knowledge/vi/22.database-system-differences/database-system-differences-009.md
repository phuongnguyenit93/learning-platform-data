# SQL Server: khóa cập nhật, gộp khóa và row versioning

SQL Server dùng nhiều cơ chế phối hợp để bảo vệ dữ liệu khi các transaction chạy đồng thời. Khóa (locks) điều phối những thao tác có thể xung đột; khóa cập nhật (update lock) giúp giảm một số deadlock do nhiều transaction cùng nâng cấp khóa đọc thành khóa ghi; lock escalation có thể gộp nhiều khóa nhỏ thành khóa ở phạm vi lớn hơn để kiểm soát chi phí quản lý khóa. Bên cạnh đó, row versioning cho phép một số truy vấn đọc phiên bản đã commit của hàng mà không phải chờ khóa ghi.

Các cơ chế này giải quyết những vấn đề khác nhau. Update lock không phải là một mức isolation riêng. Lock escalation không có nghĩa DBMS gộp dữ liệu. Row versioning không loại bỏ khóa của writer và cũng không tự biến mọi transaction thành SERIALIZABLE.

Để hiểu đúng hành vi SQL Server, cần phân biệt ba nhóm: cách SQL Server cấp và chuyển đổi lock; cách engine tăng phạm vi lock khi cần; và cách RCSI/SNAPSHOT dùng phiên bản hàng để phục vụ truy vấn đọc.

## 1. Những loại khóa quan trọng trong SQL Server

SQL Server có nhiều lock mode và lock resource. Những mode thường gặp gồm:

- **S (Shared)**: khóa chia sẻ, thường dùng khi đọc theo cơ chế locking read.
- **U (Update)**: khóa cập nhật, dùng khi đọc một tài nguyên với ý định có thể cập nhật sau đó.
- **X (Exclusive)**: khóa độc quyền, dùng khi sửa dữ liệu.
- **IS (Intent Shared)**: báo hiệu transaction dự định lấy khóa S ở cấp thấp hơn.
- **IX (Intent Exclusive)**: báo hiệu transaction dự định lấy khóa X ở cấp thấp hơn.
- **IU (Intent Update)**: báo hiệu ý định dùng update lock ở cấp thấp hơn trong một số trường hợp.

Khóa có thể áp dụng trên nhiều loại tài nguyên: key trong index, RID của heap row, page, HoBT (heap hoặc B-tree), table/object và một số tài nguyên khác.

### S, U và X khác nhau thế nào?

| Lock mode | Mục đích | Tương thích khái quát |
|---|---|---|
| S | Đọc dữ liệu bằng locking read | Có thể cùng tồn tại với S; tương thích với U |
| U | Đọc với ý định cập nhật sau đó | Có thể cùng tồn tại với S, nhưng chỉ một U trên cùng resource |
| X | Thay đổi dữ liệu | Không tương thích với S, U hoặc X trên cùng resource |

Đây là mô tả rút gọn để học các tình huống phổ biến. Ma trận tương thích đầy đủ phụ thuộc lock mode và resource; SQL Server còn dùng intent lock để phối hợp giữa cấp hàng/key, page và table.

### Intent lock

Khi transaction lấy khóa trên key hoặc row, SQL Server thường đặt intent lock ở cấp cha, chẳng hạn page hoặc table. Intent lock cho biết có khóa cấp thấp hơn đang được giữ hoặc dự định lấy.

Ví dụ, một transaction có X lock trên một key thường cần IX lock trên tài nguyên cha. Nhờ đó, transaction khác muốn lấy table lock có thể kiểm tra intent lock ở cấp table thay vì duyệt mọi key.

Intent lock không có nghĩa toàn bộ bảng đã bị khóa độc quyền. Nó mô tả ý định và sự tồn tại của khóa ở cấp thấp hơn.

## 2. Update lock (U) dùng để làm gì?

Một tình huống phổ biến là transaction đọc một hàng để quyết định cập nhật hàng đó. Nếu hai transaction cùng lấy S lock trên hàng rồi cùng muốn đổi S thành X, chúng có thể deadlock khi nâng cấp khóa.

Update lock được thiết kế để giảm tình huống này. U lock thể hiện rằng transaction đang đọc một tài nguyên với ý định có thể cập nhật. U tương thích với S, vì vậy các reader thông thường vẫn có thể đọc; nhưng trên cùng resource chỉ một transaction được giữ U lock tại một thời điểm. Khi transaction cần sửa dữ liệu, nó chuyển U thành X.

### Ví dụ hai transaction cùng nâng cấp S thành X

Giả sử cả A và B đều dùng locking read và giữ S lock cho đến khi transaction kết thúc, chẳng hạn ở REPEATABLE READ:

~~~text
Transaction A                    Transaction B
--------------                    --------------
BEGIN                             BEGIN
SELECT hàng 1                     SELECT hàng 1
Giữ S lock                        Giữ S lock
                                  Giữ S lock
Muốn UPDATE hàng 1                Muốn UPDATE hàng 1
Yêu cầu chuyển S -> X             Yêu cầu chuyển S -> X
Chờ B nhả S                       Chờ A nhả S
~~~

Mỗi transaction đang giữ S lock mà transaction kia cần được giải phóng trước khi nâng lên X. Vòng chờ có thể hình thành và SQL Server chọn một transaction làm deadlock victim.

Nếu đọc với UPDLOCK, một transaction lấy được U lock trước. Transaction thứ hai không thể lấy U lock cùng resource và phải chờ. Transaction đầu có thể chuyển U thành X, cập nhật và commit. Sau đó transaction còn lại tiếp tục.

~~~text
Transaction A                    Transaction B
--------------                    --------------
BEGIN                             BEGIN
SELECT WITH UPDLOCK                SELECT WITH UPDLOCK
Giữ U lock                        Chờ lấy U lock
UPDATE: U -> X
COMMIT
                                  Lấy được U lock
                                  Đọc trạng thái mới nhất
                                  UPDATE: U -> X
                                  COMMIT
~~~

Cách này làm cho ý định cập nhật được điều phối sớm hơn, giảm khả năng hai transaction cùng giữ S rồi cùng xin X trên một resource.

## 3. Dùng UPDLOCK trong T-SQL

Ví dụ SQL Server:

~~~sql
BEGIN TRANSACTION;

SELECT AccountId, Balance
FROM dbo.Accounts WITH (UPDLOCK)
WHERE AccountId = @AccountId;

-- Kiểm tra dữ liệu và quyết định cập nhật.

UPDATE dbo.Accounts
SET Balance = Balance - @Amount
WHERE AccountId = @AccountId;

COMMIT TRANSACTION;
~~~

UPDLOCK yêu cầu SQL Server dùng update lock cho các tài nguyên được đọc bởi table reference đó. Khóa được giữ đến khi transaction kết thúc, thay vì được giải phóng ngay sau statement như shared lock ở READ COMMITTED thông thường.

Một ví dụ kiểm tra số lượng rồi giữ hàng:

~~~sql
BEGIN TRANSACTION;

SELECT AvailableQuantity
FROM dbo.Inventory WITH (UPDLOCK)
WHERE ProductId = @ProductId;

-- Ứng dụng hoặc stored procedure kiểm tra số lượng.

UPDATE dbo.Inventory
SET AvailableQuantity = AvailableQuantity - @Quantity
WHERE ProductId = @ProductId
  AND AvailableQuantity >= @Quantity;

IF @@ROWCOUNT <> 1
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50001, 'Insufficient inventory or product not found', 1;
END;

COMMIT TRANSACTION;
~~~

Trong ví dụ thực tế, nếu có thể biểu diễn nghiệp vụ bằng một UPDATE có điều kiện thì thường nên ưu tiên câu UPDATE nguyên tử và kiểm tra @@ROWCOUNT. SELECT WITH (UPDLOCK) hữu ích khi cần đọc thêm trạng thái hoặc thực hiện nhiều quyết định trong cùng transaction.

### UPDLOCK không phải lựa chọn mặc định cho mọi SELECT

Không nên thêm UPDLOCK vào mọi truy vấn đọc. Nó có thể làm giảm khả năng đọc đồng thời vì chỉ một transaction có thể giữ U lock trên cùng resource. Với truy vấn chỉ đọc, shared lock hoặc row versioning thường phù hợp hơn tùy isolation level và cấu hình.

Dùng UPDLOCK khi transaction thực sự có ý định đọc rồi cập nhật cùng tài nguyên và cần điều phối ý định đó. Nếu chỉ cần cập nhật một giá trị theo phép toán nguyên tử, một câu UPDATE có điều kiện thường ngắn và rõ hơn.

## 4. Lock conversion và lock escalation là hai khái niệm khác nhau

**Lock conversion** là chuyển một lock đang giữ sang mode mạnh hơn hoặc khác, ví dụ U thành X, hay S thành X. Nó xảy ra khi transaction thay đổi mục đích truy cập từ đọc sang ghi.

**Lock escalation** là nâng nhiều khóa chi tiết lên một khóa ở phạm vi lớn hơn, thường từ nhiều row/key lock thành table lock hoặc partition-level lock tùy cấu hình. Mục tiêu là giảm số lượng lock cần quản lý.

| Khái niệm | Điều gì thay đổi? | Ví dụ |
|---|---|---|
| Lock conversion | Mode của khóa trên resource | U lock chuyển thành X lock |
| Lock escalation | Phạm vi/resource được khóa | Nhiều key lock được thay bằng table lock |
| Deadlock do conversion | Nhiều transaction chờ nhau khi nâng mode | A và B cùng giữ S rồi xin X |
| Tác động của escalation | Khóa rộng hơn có thể làm nhiều transaction khác phải chờ | Một UPDATE lớn khiến table lock được lấy |

Không nên gọi lock escalation là chuyển S thành X. Hai khái niệm có thể xuất hiện trong cùng một transaction nhưng giải quyết vấn đề khác nhau.

## 5. SQL Server lock escalation

Mỗi lock cần bộ nhớ và chi phí quản lý. Một câu lệnh cập nhật hàng trăm nghìn bản ghi có thể tạo rất nhiều key/row lock. Khi số lượng lock lớn hoặc áp lực bộ nhớ khóa tăng, SQL Server có thể escalation lên phạm vi lớn hơn.

Ví dụ:

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.Orders
SET ArchiveFlag = 1
WHERE CreatedAt < '2020-01-01';

COMMIT TRANSACTION;
~~~

Nếu điều kiện khớp rất nhiều hàng, SQL Server có thể ban đầu lấy nhiều khóa chi tiết, rồi chuyển sang table lock hoặc lock ở partition phù hợp. Khi table lock được lấy, transaction khác cần khóa xung đột trên các hàng trong bảng có thể phải chờ dù nó chỉ cập nhật một hàng khác.

Escalation là quyết định của engine dựa trên các điều kiện nội bộ, số lượng lock và áp lực tài nguyên. Không nên dựa vào một con số cố định để dự đoán chính xác thời điểm escalation trong mọi workload.

### Vì sao escalation tồn tại?

- Giảm số lượng lock object phải quản lý.
- Giảm bộ nhớ dành cho lock.
- Giảm chi phí theo dõi một lượng rất lớn khóa chi tiết.
- Cho phép engine kiểm soát tải khóa ở phạm vi lớn hơn.

Đổi lại, lock phạm vi rộng có thể làm giảm concurrency. Một transaction xử lý tập dữ liệu lớn có thể vô tình chặn các thao tác không liên quan về mặt nghiệp vụ nhưng cùng nằm trong table/partition được khóa.

### Partition-level escalation

Với bảng được partition và cấu hình phù hợp, SQL Server có thể escalation ở phạm vi partition thay vì toàn bảng. Có thể cấu hình LOCK_ESCALATION theo bảng, chẳng hạn AUTO để cho phép escalation ở mức partition khi điều kiện hỗ trợ.

Ví dụ:

~~~sql
ALTER TABLE dbo.LargeOrders
SET (LOCK_ESCALATION = AUTO);
~~~

Đây là lựa chọn cần đánh giá theo partitioning và workload thực tế. Partition-level escalation không bảo đảm mọi câu lệnh luôn chỉ khóa partition đang sửa; cần quan sát lock resource và hành vi của engine.

## 6. ROWLOCK có ngăn lock escalation không?

Không. Hint ROWLOCK yêu cầu SQL Server ưu tiên khóa ở mức row/key trong những trường hợp có thể, nhưng không phải cam kết tuyệt đối rằng không có page/table lock hoặc escalation.

Ví dụ:

~~~sql
SELECT OrderId, Status
FROM dbo.Orders WITH (ROWLOCK, UPDLOCK)
WHERE OrderId = @OrderId;
~~~

ROWLOCK có thể hữu ích khi muốn gợi ý granularity nhỏ hơn, nhưng dùng nó trên một truy vấn quét hàng trăm nghìn bản ghi có thể tạo ra rất nhiều khóa chi tiết, tăng memory và chi phí quản lý lock. Nó không thay thế index phù hợp hoặc chia batch.

Không nên thêm ROWLOCK chỉ để “sửa deadlock” mà chưa biết resource nào đang tranh chấp. Đọc deadlock graph và quan sát execution plan/lock resource trước khi quyết định.

### Khi nào nên chia batch?

Nếu một UPDATE tác động tới rất nhiều hàng, có thể chia thành các batch nhỏ nếu nghiệp vụ cho phép các batch commit độc lập:

~~~sql
WHILE 1 = 1
BEGIN
    UPDATE TOP (1000) dbo.Orders
    SET ArchiveFlag = 1
    WHERE ArchiveFlag = 0
      AND CreatedAt < '2020-01-01';

    IF @@ROWCOUNT = 0
        BREAK;
END;
~~~

Mẫu này chỉ minh họa cách chia số hàng mỗi statement. Trong production cần xác định thứ tự hoặc tập khóa ổn định, transaction boundary cho từng batch, index hỗ trợ điều kiện và cách resume. Nếu toàn bộ thay đổi bắt buộc nguyên tử, chia batch thành nhiều commit sẽ thay đổi ngữ nghĩa nghiệp vụ.

## 7. Row versioning là gì?

Row versioning là cơ chế SQL Server lưu các phiên bản trước của hàng để truy vấn đọc có thể xem dữ liệu đã commit tại một thời điểm nhất định mà không cần chờ writer giữ X lock trên hàng đó.

Khi transaction cập nhật một hàng, SQL Server tạo thông tin phiên bản cũ theo cơ chế version store. Một truy vấn đọc theo isolation level row-versioned có thể truy xuất phiên bản phù hợp với snapshot thay vì chờ hàng đang bị ghi.

Điều này giúp giảm reader-writer blocking. Tuy nhiên:

- Writer vẫn cần khóa để phối hợp với writer khác.
- Row versioning không tự ngăn hai transaction cập nhật cùng một hàng theo cách xung đột.
- Version store tiêu tốn dung lượng và cần cleanup.
- Transaction đọc lâu có thể khiến phiên bản cũ phải được giữ lâu hơn.
- Row versioning không đồng nghĩa với một transaction SERIALIZABLE.

SQL Server có hai chế độ quan trọng dựa trên row versioning: READ_COMMITTED_SNAPSHOT (RCSI) và SNAPSHOT isolation.

## 8. READ_COMMITTED_SNAPSHOT (RCSI)

Khi bật RCSI ở cấp database, isolation level READ COMMITTED dùng row versioning cho các truy vấn đọc. Mỗi statement đọc một snapshot nhất quán tại thời điểm bắt đầu statement đó.

Bật tùy chọn trong SQL Server:

~~~sql
ALTER DATABASE MyDatabase
SET READ_COMMITTED_SNAPSHOT ON;
~~~

Thao tác thay đổi database option này có yêu cầu về quyền và trạng thái kết nối. Trong môi trường triển khai, cần lên kế hoạch cho việc thay đổi cấu hình; một số cách chuyển đổi có thể cần quyền truy cập độc quyền hoặc chờ/đóng các kết nối đang hoạt động.

### RCSI thay đổi điều gì?

Không bật RCSI:

- READ COMMITTED thường dùng shared lock cho locking read.
- Reader có thể chờ writer đang giữ X lock.
- Writer có thể chờ reader đang giữ shared lock trong một số tình huống và isolation level.

Bật RCSI:

- Một SELECT READ COMMITTED thông thường đọc phiên bản đã commit phù hợp với thời điểm bắt đầu statement.
- Reader thường không cần S lock trên các hàng dữ liệu và ít chặn writer hơn.
- Writer vẫn lấy khóa ghi và có thể chặn writer khác.
- Các statement khác nhau trong cùng transaction có thể nhìn thấy snapshot khác nhau vì snapshot là theo statement.

Ví dụ:

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

BEGIN TRANSACTION;

SELECT Balance
FROM dbo.Accounts
WHERE AccountId = 1;

-- Một transaction khác có thể commit thay đổi ở đây.

SELECT Balance
FROM dbo.Accounts
WHERE AccountId = 1;

COMMIT TRANSACTION;
~~~

Với RCSI, hai SELECT có thể trả về hai giá trị khác nhau nếu transaction khác commit giữa hai statement. Đây là READ COMMITTED theo snapshot từng statement, không phải snapshot cố định cho toàn transaction.

### RCSI không loại bỏ khóa schema

Row versioning chủ yếu thay đổi cách đọc dữ liệu hàng. Truy vấn vẫn có thể lấy schema stability lock (Sch-S) khi compile/execute. DDL cần schema modification lock (Sch-M) vẫn có thể chặn hoặc bị chặn bởi truy vấn đang chạy.

Do đó, bật RCSI không có nghĩa mọi truy vấn đều không bao giờ chờ khóa. Nó chủ yếu giảm xung đột giữa reader và writer trên dữ liệu hàng.

## 9. SNAPSHOT isolation

SNAPSHOT isolation cung cấp một snapshot nhất quán ở cấp transaction. Các truy vấn đọc trong transaction nhìn dữ liệu đã commit tại thời điểm snapshot của transaction được thiết lập, kể cả khi transaction khác commit thay đổi sau đó.

Cần bật ALLOW_SNAPSHOT_ISOLATION ở cấp database:

~~~sql
ALTER DATABASE MyDatabase
SET ALLOW_SNAPSHOT_ISOLATION ON;
~~~

Sau đó chọn isolation level trong session:

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;

BEGIN TRANSACTION;

SELECT Balance
FROM dbo.Accounts
WHERE AccountId = 1;

-- Các statement tiếp theo tiếp tục đọc snapshot của transaction.

COMMIT TRANSACTION;
~~~

Khác với RCSI, snapshot không đổi giữa các statement của transaction. Điều này giúp tránh nonrepeatable read do transaction khác commit sau snapshot, nhưng có một hệ quả quan trọng khi ghi dữ liệu.

### Update conflict trong SNAPSHOT

Nếu transaction A bắt đầu snapshot, transaction B cập nhật một hàng rồi commit, sau đó A cố cập nhật chính hàng đó, SQL Server có thể hủy A với update conflict (thường error 3960).

Ví dụ:

~~~text
Transaction A (SNAPSHOT)          Transaction B
------------------------          -------------
BEGIN
SELECT Account 1 = 100
                                  BEGIN
                                  UPDATE Account 1 = 110
                                  COMMIT
UPDATE Account 1 = 120
Error 3960: update conflict
ROLLBACK
~~~

A không được phép ghi đè một cách mù quáng thay đổi đã commit sau snapshot của mình. Ứng dụng cần rollback transaction A và nếu nghiệp vụ cho phép thì chạy lại toàn bộ transaction trong transaction mới để đọc snapshot mới.

Không chỉ retry câu UPDATE cuối. Các quyết định nghiệp vụ trước đó dựa trên snapshot cũ và cần được tính lại.

## 10. RCSI và SNAPSHOT khác nhau thế nào?

| Tiêu chí | READ_COMMITTED_SNAPSHOT | SNAPSHOT |
|---|---|---|
| Cấu hình database | READ_COMMITTED_SNAPSHOT ON | ALLOW_SNAPSHOT_ISOLATION ON |
| Isolation level của session | READ COMMITTED | SNAPSHOT |
| Phạm vi snapshot | Mỗi statement | Toàn transaction |
| Hai SELECT trong một transaction | Có thể thấy hai snapshot khác nhau | Thấy cùng snapshot transaction |
| Reader-writer blocking | Giảm đáng kể cho truy vấn đọc thông thường | Giảm đáng kể cho truy vấn đọc thông thường |
| Writer-writer conflict | Vẫn cần khóa ghi; điều phối writer | Có thể phát sinh update conflict |
| Retry transaction | Không phải mọi lần đọc đều cần retry; vẫn xử lý lỗi ghi/lock | Update conflict thường yêu cầu rollback và retry toàn transaction |
| SERIALIZABLE? | Không | Không |

RCSI thường phù hợp khi workload có nhiều reader và muốn giảm blocking mà vẫn giữ semantics READ COMMITTED theo statement. SNAPSHOT phù hợp khi một transaction cần đọc nhất quán qua nhiều statement. Cả hai cần kiểm thử các bất biến nghiệp vụ và các đường ghi thực tế.

## 11. Row versioning không đồng nghĩa với rowversion data type

SQL Server còn có kiểu dữ liệu rowversion, trước đây từng được gọi bằng tên timestamp. Đây là một giá trị nhị phân 8 byte do database tạo và thay đổi khi hàng có cột rowversion được cập nhật.

Ví dụ:

~~~sql
CREATE TABLE dbo.Documents (
    DocumentId BIGINT PRIMARY KEY,
    Body NVARCHAR(MAX) NOT NULL,
    VersionToken ROWVERSION
);
~~~

Ứng dụng có thể đọc VersionToken rồi cập nhật có điều kiện:

~~~sql
UPDATE dbo.Documents
SET Body = @NewBody
WHERE DocumentId = @DocumentId
  AND VersionToken = @VersionRead;
~~~

Nếu @@ROWCOUNT = 0, hàng không tồn tại hoặc token đã thay đổi. Cách này là optimistic concurrency token ở cấp ứng dụng.

Cần phân biệt:

- **Row versioning isolation**: cơ chế lưu và đọc phiên bản hàng cũ cho RCSI/SNAPSHOT.
- **rowversion data type**: token nhị phân thay đổi khi hàng được cập nhật.
- **timestamp thời gian**: giá trị ngày giờ như datetime2/datetimeoffset.

rowversion không lưu ngày giờ, không phải timestamp lịch và không phải chính cơ chế version store của RCSI/SNAPSHOT. Nó cũng không tự đảm bảo thứ tự commit giữa các transaction.

## 12. Version store nằm ở đâu và cần theo dõi gì?

Trong cấu hình truyền thống, SQL Server lưu row version trong version store của tempdb. Với database dùng Accelerated Database Recovery (ADR), các phiên bản hàng phục vụ cơ chế liên quan có thể được lưu trong Persistent Version Store (PVS) của database thay vì chỉ dựa vào version store trong tempdb. Cách lưu trữ cụ thể phụ thuộc phiên bản SQL Server và cấu hình ADR.

Version store cần giữ các phiên bản còn có thể được transaction đang hoạt động tham chiếu. Transaction snapshot hoặc truy vấn kéo dài có thể khiến phiên bản cũ chưa được dọn dẹp.

Hệ quả vận hành:

- tempdb hoặc PVS có thể tăng dung lượng.
- Cleanup không thể xóa phiên bản vẫn cần cho snapshot đang hoạt động.
- Transaction đọc quá lâu có thể kéo dài vòng đời version.
- Bật row versioning có thêm chi phí ghi và lưu trữ.
- Cần theo dõi dung lượng, tốc độ tạo version và transaction lâu nhất.

Không nên chỉ bật RCSI/SNAPSHOT mà không theo dõi version store. Một workload nhiều transaction đọc lâu có thể làm tăng áp lực lưu trữ ngay cả khi lock wait giảm.

### Các chỉ số và công cụ quan sát

Tùy phiên bản, có thể dùng các DMV và view như:

- sys.dm_tran_version_store_space_usage để xem dung lượng version store theo database trong tempdb.
- sys.dm_db_file_space_usage để quan sát không gian tempdb, bao gồm version store.
- sys.dm_tran_active_snapshot_database_transactions để xem transaction snapshot đang hoạt động.
- sys.dm_tran_active_transactions và sys.dm_exec_requests để điều tra transaction/request kéo dài.
- sys.dm_tran_persistent_version_store_stats trên phiên bản hỗ trợ ADR/PVS để theo dõi persistent version store.

Quyền xem DMV phụ thuộc phiên bản và quyền server/database. Khi điều tra, kết hợp version store metrics với thời gian transaction, blocking và throughput; không kết luận chỉ từ một chỉ số dung lượng.

## 13. Row versioning có ngăn lost update không?

Không tự động trong mọi kiểu ứng dụng.

Giả sử hai client đọc balance = 100 theo RCSI. Client A tính 110, client B tính 120. Sau đó A ghi 110, B ghi 120. Nếu cả hai gửi giá trị tuyệt đối mà không có version check hoặc điều kiện phù hợp, một thay đổi có thể bị ghi đè. RCSI chỉ bảo đảm mỗi SELECT đọc phiên bản đã commit theo statement; nó không biết phép tính phía ứng dụng dựa trên giá trị cũ.

Nếu ý định là cộng thêm, hãy cập nhật nguyên tử:

~~~sql
UPDATE dbo.Accounts
SET Balance = Balance + @Delta
WHERE AccountId = @AccountId;
~~~

Nếu client sửa một tài liệu theo optimistic locking, dùng rowversion token:

~~~sql
UPDATE dbo.Documents
SET Body = @NewBody
WHERE DocumentId = @DocumentId
  AND VersionToken = @VersionRead;
~~~

Nếu cần đọc rồi quyết định cập nhật trong cùng transaction, cân nhắc UPDLOCK hoặc một cơ chế khóa phù hợp. Với SNAPSHOT, cần xử lý update conflict. Cách chọn phụ thuộc ý nghĩa nghiệp vụ và phạm vi dữ liệu cần bảo vệ.

## 14. SNAPSHOT không tương đương SERIALIZABLE

SNAPSHOT cung cấp một góc nhìn nhất quán của dữ liệu tại thời điểm transaction bắt đầu snapshot, nhưng nó không tự ngăn mọi write skew hoặc mọi phantom-related invariant.

Ví dụ, có hai nhân viên đang trực. Quy tắc là luôn phải còn ít nhất một người trực. A đọc thấy hai người rồi tắt trạng thái trực của người 1. B cũng đọc snapshot thấy hai người rồi tắt người 2. Vì A và B sửa hai hàng khác nhau, có thể không có update conflict trên cùng hàng; cả hai có thể commit và làm bất biến bị phá.

Đây là write skew. Nếu bất biến phụ thuộc predicate hoặc nhiều hàng, có thể cần:

- SERIALIZABLE để SQL Server dùng key-range locking phù hợp.
- Guard row mà mọi transaction cùng khóa.
- Một constraint hoặc mô hình dữ liệu biểu diễn trực tiếp quy tắc.
- Giao thức cập nhật nguyên tử bảo vệ invariant.

Ví dụ bật SERIALIZABLE cho transaction:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

BEGIN TRANSACTION;

SELECT EmployeeId
FROM dbo.OnCallRoster
WHERE IsOnCall = 1;

-- Kiểm tra quy tắc và cập nhật trong cùng transaction.

COMMIT TRANSACTION;
~~~

SQL Server có thể dùng key-range locks để bảo vệ predicate theo index access path. Một index phù hợp có thể giúp phạm vi khóa chính xác hơn, nhưng cần xem execution plan và lock resource thực tế.

## 15. Dùng HOLDLOCK và UPDLOCK cùng nhau khi nào?

HOLDLOCK áp dụng semantics SERIALIZABLE cho table reference được chỉ định trong statement. Nó có thể yêu cầu giữ khóa và bảo vệ khoảng key để ngăn phantom phù hợp với predicate. UPDLOCK yêu cầu update lock thay cho shared lock cho tài nguyên được đọc.

Ví dụ kiểm tra một booking chưa tồn tại rồi chuẩn bị tạo:

~~~sql
BEGIN TRANSACTION;

SELECT BookingId
FROM dbo.Bookings WITH (UPDLOCK, HOLDLOCK)
WHERE ResourceId = @ResourceId
  AND BookingDate = @BookingDate;

IF @@ROWCOUNT = 0
BEGIN
    INSERT INTO dbo.Bookings (ResourceId, BookingDate, Status)
    VALUES (@ResourceId, @BookingDate, 'ACTIVE');
END;

COMMIT TRANSACTION;
~~~

Ví dụ này minh họa mẫu khóa phạm vi khi cần bảo vệ predicate. Để bảo vệ uniqueness một cách chắc chắn, vẫn nên có UNIQUE constraint trên khóa nghiệp vụ nếu có thể:

~~~sql
CREATE UNIQUE INDEX UX_Bookings_Resource_Date
ON dbo.Bookings (ResourceId, BookingDate);
~~~

UPDLOCK/HOLDLOCK không thay thế constraint. Nếu hai transaction cùng kiểm tra một key chưa tồn tại, range lock và index access path ảnh hưởng cách chúng phối hợp. UNIQUE constraint là lớp bảo vệ cuối cùng cho quy tắc duy nhất, kể cả khi có đường ghi khác không tuân thủ giao thức ứng dụng.

Không thêm HOLDLOCK vào mọi query vì nó có thể giữ range lock lâu và giảm concurrency. Dùng khi logic thực sự cần bảo vệ predicate trong suốt transaction.

## 16. Khi nào dùng READCOMMITTEDLOCK?

Khi RCSI bật, READ COMMITTED thông thường dùng row versioning cho đọc. Nếu một truy vấn cần locking read theo semantics READ COMMITTED, có thể dùng hint READCOMMITTEDLOCK trên table reference:

~~~sql
SELECT OrderId, Status
FROM dbo.Orders WITH (READCOMMITTEDLOCK)
WHERE OrderId = @OrderId;
~~~

Hint này yêu cầu locking read thay cho row-versioned read ở table reference đó. Nó có thể cần thiết khi dùng một số lock-based pattern hoặc hint khác, nhưng cũng có thể đưa reader trở lại tình trạng chờ writer.

Không nhầm READCOMMITTEDLOCK với NOLOCK. READCOMMITTEDLOCK vẫn tuân thủ READ COMMITTED và không cho phép dirty read. NOLOCK tương đương READ UNCOMMITTED cho dữ liệu và có thể đọc dữ liệu chưa commit hoặc kết quả không nhất quán; nó cũng không loại bỏ mọi schema lock.

## 17. Cách quan sát lock, blocking và escalation

Khi một request chậm, cần xác định nó đang:

- Chờ một transaction khác giữ lock.
- Chờ tài nguyên nội bộ khác như latch.
- Đọc dữ liệu bằng row versioning.
- Bị block bởi schema modification.
- Chạy lâu do scan/sort/I/O mà không có lock wait đáng kể.
- Bị deadlock victim hoặc snapshot update conflict.

Các công cụ thường dùng:

### sys.dm_tran_locks

Xem các lock đang được giữ hoặc yêu cầu:

~~~sql
SELECT
    request_session_id,
    resource_type,
    resource_database_id,
    resource_associated_entity_id,
    request_mode,
    request_status
FROM sys.dm_tran_locks
WHERE resource_database_id = DB_ID();
~~~

### sys.dm_exec_requests

Quan sát request đang chạy, trạng thái chờ và blocker:

~~~sql
SELECT
    session_id,
    status,
    command,
    wait_type,
    wait_time,
    blocking_session_id,
    transaction_isolation_level
FROM sys.dm_exec_requests
WHERE session_id <> @@SPID;
~~~

### Extended Events

Dùng Extended Events để thu thập deadlock graph, lock escalation và các sự kiện phù hợp với phiên bản. Deadlock graph cho biết session, resource, lock mode và câu lệnh liên quan. Đây thường là bằng chứng tốt hơn việc chỉ nhìn error 1205 trong log ứng dụng.

Cần cấp quyền phù hợp cho DMV/XEvent và tránh thu thập quá rộng gây thêm overhead. Gắn application name, correlation id và session id để liên kết log ứng dụng với database.

## 18. Chọn cơ chế theo tình huống

| Tình huống | Cơ chế nên cân nhắc | Điểm cần lưu ý |
|---|---|---|
| Nhiều reader chặn writer và ngược lại | RCSI | Snapshot theo statement; version store tăng |
| Một transaction cần snapshot ổn định qua nhiều SELECT | SNAPSHOT | Update conflict; retry transaction; write skew vẫn có thể xảy ra |
| Đọc rồi cập nhật cùng hàng trong một transaction | UPDLOCK | U lock điều phối ý định cập nhật; không lạm dụng |
| Bảo vệ predicate hoặc key chưa tồn tại | SERIALIZABLE/HOLDLOCK và index phù hợp | Range lock có thể giảm concurrency |
| Một câu lệnh cập nhật quá nhiều hàng | Batch nếu nghiệp vụ cho phép | Mỗi batch commit riêng làm thay đổi atomicity |
| Lock escalation gây block diện rộng | Tối ưu index, batch, transaction scope, partition | ROWLOCK không phải bảo đảm cấm escalation |
| Client sửa dữ liệu dựa trên phiên bản đã đọc | rowversion token hoặc version column | Kiểm tra số hàng cập nhật và báo conflict |
| Nhiều writer cập nhật cùng một hàng | Atomic UPDATE, thiết kế lại hotspot, khóa phù hợp | RCSI không loại bỏ writer-writer contention |

## 19. Các ngộ nhận thường gặp

### UPDLOCK là khóa độc quyền

Không. U lock khác X lock. Nó cho phép shared lock tương thích trong một số trường hợp nhưng ngăn một transaction khác cùng lấy U trên cùng resource.

### RCSI làm database không còn lock

Không. Writer vẫn dùng khóa ghi; schema lock và nhiều loại resource lock vẫn tồn tại. RCSI chủ yếu giảm blocking giữa reader và writer trên dữ liệu hàng.

### SNAPSHOT luôn ngăn lost update và write skew

SNAPSHOT phát hiện một số update conflict trên cùng hàng, nhưng không tự bảo vệ mọi bất biến nhiều hàng. Write skew vẫn có thể xảy ra.

### Lock escalation luôn xảy ra ở một số hàng cố định

Không nên dựa vào một ngưỡng duy nhất. Escalation phụ thuộc số lượng khóa, áp lực bộ nhớ, cấu hình và cách engine xử lý workload.

### ROWLOCK bảo đảm chỉ có row lock

Không. Đây là hint về granularity, không phải cam kết tuyệt đối và không ngăn mọi escalation.

### rowversion là thời gian cập nhật

Không. rowversion là token nhị phân 8 byte, không phải ngày giờ và không phải row-version store dùng bởi RCSI/SNAPSHOT.

### Bật RCSI thì không cần index

Không. Index vẫn quan trọng để giảm scan, I/O và chi phí writer. Row versioning không làm một truy vấn quét toàn bảng trở nên rẻ.

## 20. Quy trình triển khai và kiểm chứng

1. **Đo baseline**: ghi nhận blocking, deadlock, query latency, throughput, tempdb và thời gian transaction.
2. **Phân loại workload**: xác định reader-writer blocking, writer-writer contention, conversion deadlock hay escalation.
3. **Chọn cơ chế đúng**: UPDLOCK cho read-then-update; RCSI cho đọc READ COMMITTED ít block; SNAPSHOT cho transaction snapshot; SERIALIZABLE cho predicate invariant.
4. **Kiểm tra index và plan**: xác nhận access path, số hàng quét, key-range lock và chi phí ghi.
5. **Kiểm tra transaction scope**: rút ngắn transaction, tránh gọi mạng khi giữ khóa.
6. **Kiểm thử hai session**: điều khiển lịch đọc/ghi, update conflict và lock wait bằng mốc đồng bộ.
7. **Bật cấu hình có kiểm soát**: RCSI hoặc ALLOW_SNAPSHOT_ISOLATION cần kế hoạch triển khai và rollback cấu hình.
8. **Theo dõi version store**: tempdb/PVS, transaction snapshot lâu và tốc độ cleanup.
9. **Xử lý retry**: phân loại error 3960, deadlock 1205 và các lỗi tạm thời khác; retry toàn bộ transaction phù hợp.
10. **Đối chiếu bất biến**: kiểm tra trạng thái cuối và kết quả nghiệp vụ sau commit/abort.
11. **Theo dõi sau triển khai**: so sánh blocking, deadlock, latency, throughput và dung lượng version store với baseline.

SQL Server kết hợp locking và row versioning để cân bằng tính nhất quán với khả năng chạy đồng thời. U lock giúp điều phối sớm các transaction có ý định cập nhật cùng tài nguyên; lock conversion đổi mode khi thao tác chuyển từ đọc sang ghi; lock escalation gộp nhiều khóa chi tiết thành phạm vi lớn hơn khi engine cần kiểm soát chi phí. RCSI và SNAPSHOT cho phép reader dùng phiên bản đã commit, nhưng writer vẫn cần khóa và các bất biến nhiều hàng vẫn cần cơ chế bảo vệ phù hợp. Chọn đúng cơ chế đòi hỏi hiểu phạm vi snapshot, lock mode, transaction boundary, version store và hành vi retry trên đúng cấu hình SQL Server đang vận hành.
