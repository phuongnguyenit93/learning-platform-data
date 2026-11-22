# REPEATABLE READ và các khác biệt cần kiểm tra giữa hệ quản trị

**REPEATABLE READ** là một mức cô lập giao dịch nhằm bảo đảm các lần đọc lặp lại trong cùng giao dịch không tùy tiện quan sát những thay đổi đã commit của giao dịch khác đối với dữ liệu đã đọc. Tuy nhiên, mức bảo đảm cụ thể của REPEATABLE READ **khác nhau giữa các hệ quản trị cơ sở dữ liệu**. Có hệ dùng snapshot MVCC cho toàn giao dịch; có hệ dựa nhiều vào khóa và phạm vi khóa; có hệ hỗ trợ phantom prevention theo một cách khác.

Vì vậy, khi chuyển ứng dụng giữa PostgreSQL, MySQL/InnoDB, SQL Server hoặc Oracle, không nên chỉ thấy cùng tên REPEATABLE READ rồi mặc định hành vi giống nhau. Cần kiểm tra ít nhất: thời điểm tạo snapshot, khả năng đọc lại cùng một hàng, phantom, write skew, khóa ghi, hành vi cập nhật xung đột và cách ứng dụng nhận lỗi để retry.

## 1. REPEATABLE READ giải quyết vấn đề gì?

Xét hai giao dịch T1 và T2 cùng truy cập một tài khoản. Ban đầu số dư là 600:

~~~text
T2: BEGIN
T2: SELECT balance -> 600

T1: UPDATE accounts SET balance = 500 WHERE id = 'A'
T1: COMMIT

T2: SELECT balance lần thứ hai
~~~

Nếu lần đọc thứ hai của T2 trả về 500, T2 thấy một giá trị khác so với lần đọc đầu trong cùng giao dịch. Đây là hiện tượng **non-repeatable read**.

REPEATABLE READ hướng tới việc ngăn hiện tượng đó: trong cùng transaction, khi T2 đọc lại hàng A, nó tiếp tục nhìn thấy giá trị phù hợp với ảnh chụp hoặc khóa mà isolation implementation bảo vệ. Trong các hệ thống snapshot-based, kết quả thường là 600 nếu snapshot của T2 được tạo trước commit của T1.

Điểm quan trọng là **REPEATABLE READ nói về các lần đọc trong transaction**, không có nghĩa toàn bộ dữ liệu trong database đứng yên. Giao dịch khác vẫn có thể commit thay đổi; câu hỏi là T2 có được nhìn thấy thay đổi ấy trong phạm vi giao dịch hiện tại hay không.

## 2. Bốn hiện tượng thường dùng để so sánh isolation

Trước khi xét từng DBMS, cần phân biệt các bất thường đọc/ghi:

| Hiện tượng | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Dirty read** | Đọc thay đổi chưa commit của giao dịch khác | T2 đọc số dư mới do T1 ghi, rồi T1 rollback |
| **Non-repeatable read** | Đọc cùng một hàng hai lần và nhận hai giá trị khác do một commit chen giữa | T2 đọc A=600, T1 commit A=500, T2 đọc lại A=500 |
| **Phantom read** | Chạy lại truy vấn theo điều kiện và tập hàng phù hợp thay đổi | T2 đếm đơn hàng chưa xử lý, T1 thêm một đơn phù hợp, T2 đếm lại thấy thêm hàng |
| **Write skew** | Các giao dịch đọc cùng trạng thái nhất quán nhưng ghi các hàng khác nhau, khiến bất biến chung bị vi phạm | Hai nhân viên cùng thấy có người khác trực rồi mỗi người tự chuyển mình sang nghỉ |

Theo cách trình bày trong chuẩn SQL truyền thống, REPEATABLE READ ngăn dirty read và non-repeatable read, nhưng có thể cho phantom read. Tuy nhiên, tên mức cô lập trong tài liệu sản phẩm không đủ để dự đoán mọi hành vi; cần xem implementation cụ thể, đặc biệt với MVCC.

### Phantom khác non-repeatable read

Ví dụ T2 truy vấn các đơn hàng có trạng thái PENDING:

~~~sql
SELECT order_id
FROM orders
WHERE status = 'PENDING';
~~~

Sau đó T1 chèn một đơn hàng PENDING và commit. Khi T2 chạy lại cùng predicate, nó có thể thấy một hàng mới. Đây là phantom: tập kết quả thay đổi, mặc dù những hàng T2 đã đọc trước đó có thể vẫn giữ nguyên giá trị.

Non-repeatable read liên quan tới một hàng đã đọc bị thay đổi; phantom liên quan đến thành viên của tập kết quả theo điều kiện truy vấn.

## 3. Mô hình snapshot và khóa tạo nên khác biệt

Hai hướng triển khai phổ biến là:

**MVCC/snapshot:** DBMS duy trì nhiều phiên bản của hàng. Giao dịch đọc có thể thấy phiên bản phù hợp với snapshot thay vì chờ giao dịch ghi kết thúc. Khi snapshot cố định theo transaction, nhiều lần đọc trong giao dịch dùng cùng mốc dữ liệu.

**Locking:** DBMS sử dụng shared lock, exclusive lock hoặc khóa phạm vi để điều phối người đọc và người ghi. Khóa có thể được giữ đến khi transaction kết thúc để bảo đảm lần đọc sau vẫn thấy dữ liệu phù hợp. Việc khóa predicate/range còn có thể ngăn hàng mới xuất hiện trong phạm vi truy vấn.

~~~text
Transaction T2 đọc A
        |
        +-- Snapshot/MVCC:
        |      đọc phiên bản A phù hợp với snapshot
        |      T1 có thể ghi phiên bản mới song song
        |
        +-- Locking:
               giữ khóa đọc hoặc khóa phạm vi thích hợp
               T1 có thể phải chờ khi muốn sửa dữ liệu bị khóa
~~~

Hai mô hình có thể tạo trải nghiệm khác nhau về blocking, deadlock, lưu giữ phiên bản cũ và lỗi xung đột, dù cùng dùng nhãn REPEATABLE READ.

## 4. PostgreSQL: REPEATABLE READ dùng snapshot ổn định

PostgreSQL triển khai REPEATABLE READ bằng snapshot isolation. Các câu lệnh đọc thông thường trong cùng transaction nhìn dữ liệu theo một snapshot ổn định được xác lập ở lần cần snapshot đầu tiên. Một thay đổi do transaction khác commit sau snapshot đó thường không xuất hiện trong những lần đọc tiếp theo của transaction hiện tại.

Ví dụ:

~~~sql
-- Session T2
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM accounts
WHERE account_id = 'A';
-- Giả sử trả về 600 và snapshot được xác lập.

-- Trong session khác, T1 cập nhật A=500 rồi COMMIT.

SELECT balance
FROM accounts
WHERE account_id = 'A';
-- T2 tiếp tục nhìn phiên bản trong snapshot: 600.

COMMIT;
~~~

Ở đây, REPEATABLE READ không nhất thiết khóa hàng để ngăn T1 cập nhật. T1 có thể commit phiên bản mới, trong khi T2 tiếp tục đọc phiên bản cũ của mình.

### Phantom trong PostgreSQL REPEATABLE READ

Vì snapshot của transaction cố định, việc T1 chèn hàng mới và commit sau thời điểm snapshot được tạo cũng không làm hàng mới xuất hiện trong các truy vấn đọc thông thường của T2. Do đó, PostgreSQL REPEATABLE READ ngăn phantom theo nghĩa tập kết quả SELECT không thay đổi do các commit mới sau snapshot.

Điểm này mạnh hơn mức REPEATABLE READ tối thiểu được mô tả trong mô hình SQL cổ điển vốn có thể cho phantom.

### Nhưng snapshot isolation vẫn có thể cho write skew

REPEATABLE READ của PostgreSQL **không đồng nghĩa SERIALIZABLE**. Hai giao dịch có thể cùng đọc một snapshot và cập nhật các hàng khác nhau, tạo write skew nếu không có ràng buộc hoặc khóa bảo vệ bất biến nghiệp vụ.

Ví dụ, trong một nhóm luôn phải có ít nhất một người đang trực:

~~~text
Ban đầu: Alice = ON, Bob = ON

T1 đọc Alice=ON, Bob=ON
T2 đọc Alice=ON, Bob=ON

T1 ghi Alice=OFF
T2 ghi Bob=OFF

T1 COMMIT
T2 COMMIT

Kết quả: Alice=OFF, Bob=OFF
~~~

Hai transaction ghi hai hàng khác nhau nên không nhất thiết xung đột theo cách snapshot isolation phát hiện. Muốn bảo vệ bất biến này có thể cần SERIALIZABLE, khóa một hàng đại diện chung hoặc thiết kế ràng buộc dữ liệu phù hợp.

### Xung đột cập nhật trong PostgreSQL

Nếu T1 và T2 cùng cập nhật một hàng mà snapshot của T2 đã cũ, T2 có thể chờ T1 kết thúc rồi nhận lỗi serialization khi cố cập nhật hàng đã bị thay đổi kể từ snapshot. Ứng dụng cần có chiến lược retry toàn bộ transaction khi gặp lỗi serialization có thể retry.

PostgreSQL thường dùng SQLSTATE 40001 cho serialization failure. Không nên chỉ chạy lại riêng câu UPDATE: toàn bộ quyết định nghiệp vụ dựa trên snapshot cũ cần được thực thi lại trong transaction mới.

## 5. MySQL/InnoDB: consistent read và locking read

InnoDB sử dụng MVCC cho consistent read và các khóa cho locking read. Trong transaction REPEATABLE READ, các truy vấn đọc nhất quán thông thường thường dùng cùng read view được tạo ở lần consistent read đầu tiên.

Ví dụ:

~~~sql
-- MySQL/InnoDB
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 'A';
-- Lần consistent read đầu tiên xác lập read view.

-- Session khác cập nhật A=500 rồi COMMIT.

SELECT balance
FROM accounts
WHERE account_id = 'A';
-- Consistent read tiếp tục thấy phiên bản theo read view cũ.

COMMIT;
~~~

Điều này khiến một transaction InnoDB REPEATABLE READ có thể đọc lặp lại cùng phiên bản, tương tự snapshot behavior nhưng không được mặc định rằng mọi loại SELECT đều dùng cùng một đường đọc.

### Consistent read và locking read khác nhau

Một SELECT thông thường có thể là consistent nonlocking read. Nhưng các dạng như:

~~~sql
SELECT *
FROM accounts
WHERE account_id = 'A'
FOR UPDATE;
~~~

hoặc:

~~~sql
SELECT *
FROM accounts
WHERE account_id = 'A'
FOR SHARE;
~~~

là locking read. Chúng đọc theo quy tắc khóa hiện hành và có thể thấy kết quả mới nhất phù hợp sau khi chờ giao dịch khác, khác với consistent read dùng read view cũ.

Vì vậy, trong MySQL/InnoDB, không nên gom mọi SELECT vào một khái niệm “snapshot read” duy nhất. Hãy xác định truy vấn có FOR UPDATE/FOR SHARE hay không.

### Gap lock và next-key lock

Ở REPEATABLE READ, InnoDB có thể dùng **next-key lock** (kết hợp record lock với gap lock) trong một số locking read và thao tác tìm kiếm/cập nhật theo index để ngăn transaction khác chèn hàng vào khoảng khóa. Điều này giúp kiểm soát phantom đối với những đường truy cập phù hợp.

Phạm vi khóa phụ thuộc predicate, index, execution plan, loại truy vấn và cấu hình engine. Một truy vấn thiếu index phù hợp có thể khóa phạm vi rộng hơn dự kiến, làm giảm concurrency.

Consistent read thông thường không có nghĩa nó giữ khóa range để chặn insert. Khả năng truy vấn đọc thấy phantom cần được phân tích đúng loại read mà ứng dụng thực hiện.

### Cập nhật và retry

InnoDB có thể phát hiện deadlock và chọn một transaction làm nạn nhân; ứng dụng phải xử lý lỗi và retry toàn bộ transaction khi phù hợp. Lock wait timeout cũng có semantics riêng theo cấu hình và không nên xem như đồng nghĩa với serialization failure.

Do đó, một ứng dụng MySQL cần phân biệt:
- Consistent read từ snapshot.
- Locking read dùng current state và khóa.
- Lock wait timeout.
- Deadlock victim.
- Lỗi constraint hoặc lỗi ứng dụng.

## 6. SQL Server: REPEATABLE READ dùng shared lock được giữ đến hết transaction

SQL Server triển khai locking REPEATABLE READ bằng cách giữ shared lock trên các hàng đã đọc đến khi transaction kết thúc. Điều này ngăn transaction khác sửa hoặc xóa những hàng T2 đã đọc, nhưng không nhất thiết khóa toàn bộ phạm vi predicate để ngăn một hàng mới được chèn vào.

Ví dụ khái niệm:

~~~sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
BEGIN TRANSACTION;

SELECT balance
FROM dbo.Accounts
WHERE AccountId = 'A';

-- Transaction khác muốn UPDATE hàng A có thể phải chờ.

SELECT balance
FROM dbo.Accounts
WHERE AccountId = 'A';

COMMIT TRANSACTION;
~~~

Nếu T1 muốn thay đổi hàng A mà T2 đang giữ shared lock, T1 có thể phải chờ T2 commit/rollback. T2 đọc lại A vẫn thấy giá trị đã đọc trước đó.

### Phantom vẫn có thể xảy ra

REPEATABLE READ của SQL Server không giữ khóa range chỉ để ngăn hàng mới thỏa predicate xuất hiện. Ví dụ T2 truy vấn các đơn hàng PENDING; T1 insert một đơn PENDING và commit; khi T2 chạy lại truy vấn, hàng mới có thể xuất hiện.

Nếu cần ngăn phantom trong mô hình locking của SQL Server, SERIALIZABLE có thể dùng key-range lock để bảo vệ predicate theo index và execution plan phù hợp.

### READ_COMMITTED_SNAPSHOT và SNAPSHOT là lựa chọn khác

SQL Server còn có các cơ chế row-versioning:

- **READ_COMMITTED_SNAPSHOT (RCSI):** READ COMMITTED dùng row versioning với snapshot theo statement.
- **SNAPSHOT isolation:** transaction dùng snapshot ở cấp transaction, yêu cầu bật tùy chọn ALLOW_SNAPSHOT_ISOLATION cho database.

Không nên đồng nhất SNAPSHOT của SQL Server với nhãn REPEATABLE READ chỉ vì cả hai đều có thể đọc phiên bản cũ. Tên isolation level và cơ chế cấu hình của chúng khác nhau.

### Write conflict trong SNAPSHOT

SQL Server SNAPSHOT có kiểm tra xung đột cập nhật cùng hàng; một transaction có thể bị từ chối khi hàng đã được transaction khác sửa kể từ snapshot của nó. Tuy vậy, snapshot isolation vẫn có thể cho write skew trên các hàng khác nhau. SERIALIZABLE hoặc thiết kế khóa/ràng buộc bổ sung có thể cần thiết để bảo vệ bất biến liên hàng.

## 7. Oracle: tên mức cô lập và cơ chế khác

Oracle Database có mô hình MVCC và cung cấp các mức READ COMMITTED, SERIALIZABLE và READ ONLY trong ngữ cảnh giao dịch; nó không cung cấp một mức mang tên REPEATABLE READ theo cách JDBC/SQL thông thường mong đợi như PostgreSQL hay InnoDB.

Ở READ COMMITTED, Oracle bảo đảm statement-level read consistency: mỗi câu SQL đọc một ảnh nhất quán tại thời điểm câu lệnh bắt đầu. Hai câu SELECT trong cùng transaction có thể thấy hai snapshot khác nhau nếu có commit chen giữa.

Với SERIALIZABLE, transaction có snapshot nhất quán ở cấp transaction và các cập nhật xung đột có thể bị báo lỗi, ví dụ ORA-08177 trong các trường hợp không thể serialize theo quy tắc Oracle. READ ONLY transaction cũng cung cấp chế độ đọc nhất quán theo transaction nhưng không cho phép sửa dữ liệu.

Điểm rút ra khi chuyển ứng dụng từ DBMS hỗ trợ REPEATABLE READ sang Oracle là phải ánh xạ **ý nghĩa yêu cầu** sang mức/transaction mode Oracle hỗ trợ, không chỉ đổi chuỗi cấu hình theo tên. Nếu mục tiêu là nhiều truy vấn đọc cùng một snapshot, hãy đánh giá READ ONLY transaction hoặc SERIALIZABLE theo yêu cầu thực tế.

## 8. Bảng so sánh khái quát

Bảng sau nêu những khác biệt phổ biến ở các cấu hình mặc định/chuẩn. Đây không thay thế tài liệu phiên bản cụ thể, vì tùy chọn database, engine, isolation, hint và driver có thể làm thay đổi hành vi.

| DBMS | Có mức REPEATABLE READ cùng tên? | Mô hình thường dùng ở mức tương ứng | Phantom | Điểm cần kiểm tra |
| --- | --- | --- | --- | --- |
| **PostgreSQL** | Có | Snapshot isolation cấp transaction | SELECT thông thường không thấy hàng commit sau snapshot | Write skew; lỗi serialization khi cập nhật hàng thay đổi |
| **MySQL/InnoDB** | Có | MVCC consistent read; locking read dùng khóa | Consistent read có read view ổn định; locking read có thể dùng next-key/gap lock | Phân biệt consistent read với FOR UPDATE/FOR SHARE; index và gap lock |
| **SQL Server** | Có | Shared lock giữ đến transaction end | Có thể xảy ra; SERIALIZABLE dùng key-range lock phù hợp | RCSI và SNAPSHOT là các tùy chọn row-versioning riêng |
| **Oracle Database** | Không có tên REPEATABLE READ trong tập isolation phổ biến | READ COMMITTED theo statement; SERIALIZABLE/READ ONLY theo transaction | READ COMMITTED có thể thấy statement-level thay đổi; SERIALIZABLE dùng snapshot transaction | Ánh xạ mục tiêu đọc lặp lại sang transaction mode được hỗ trợ |

Không nên đọc cột “Phantom” một cách tách rời khỏi loại truy vấn. Với InnoDB, kết quả consistent read và locking read khác nhau; với SQL Server, predicate, index và key-range locks ảnh hưởng phantom; với PostgreSQL, snapshot cố định tạo hành vi khác mô hình khóa cổ điển.

## 9. JDBC: tên isolation level không phải một hợp đồng đồng nhất tuyệt đối

JDBC cung cấp các hằng số chuẩn:

~~~java
Connection.TRANSACTION_READ_UNCOMMITTED
Connection.TRANSACTION_READ_COMMITTED
Connection.TRANSACTION_REPEATABLE_READ
Connection.TRANSACTION_SERIALIZABLE
~~~

Ứng dụng có thể yêu cầu:

~~~java
connection.setTransactionIsolation(
    Connection.TRANSACTION_REPEATABLE_READ
);
~~~

Nhưng trước khi dùng, cần kiểm tra:
- Driver có hỗ trợ mức này không.
- DBMS có hỗ trợ tên/mức tương ứng không.
- Driver ánh xạ mức JDBC sang tính năng nào của DBMS.
- Cấu hình có được thực hiện trước khi transaction bắt đầu không.
- Framework transaction manager có đang sở hữu connection không.
- Có lỗi hoặc thay đổi ranh giới transaction khi yêu cầu mức không hỗ trợ không.

DatabaseMetaData có thể cung cấp thông tin về các mức cô lập được hỗ trợ:

~~~java
DatabaseMetaData metadata = connection.getMetaData();

boolean supportsRepeatableRead =
    metadata.supportsTransactionIsolationLevel(
        Connection.TRANSACTION_REPEATABLE_READ
    );
~~~

Đây là thông tin khả năng hỗ trợ, không phải mô tả đầy đủ tất cả hiện tượng và thuật toán cụ thể. Nếu cần một bảo đảm như “cùng snapshot qua toàn transaction” hoặc “ngăn phantom trên predicate này”, hãy viết kiểm thử tích hợp với DBMS thực tế và đọc tài liệu chính thức.

### Phân biệt lỗi serialization với deadlock

Một transaction có thể thất bại do:
- Serialization conflict.
- Deadlock.
- Lock wait timeout.
- Optimistic locking/version check.
- Constraint violation.
- Mất kết nối hoặc timeout phía client.

Không phải lỗi nào cũng được retry theo cùng cách. Ví dụ, serialization failure thường yêu cầu chạy lại **toàn bộ transaction** để mọi lần đọc và quyết định nghiệp vụ được lấy từ snapshot mới. Constraint violation do dữ liệu đầu vào không hợp lệ thường không nên retry vô hạn.

## 10. Spring: khai báo isolation nhưng phải xét propagation

Spring cho phép khai báo:

~~~java
@Transactional(isolation = Isolation.REPEATABLE_READ)
public Report loadReport() {
    // Các lần đọc cần tham gia cùng transaction được quản lý.
    return reportRepository.load();
}
~~~

Tuy nhiên, khi phương thức được gọi trong một transaction đã tồn tại với propagation REQUIRED, phương thức bên trong thường tham gia transaction ngoài. Isolation của transaction đã tồn tại có hiệu lực; khai báo REPEATABLE_READ bên trong không tự tạo snapshot mới hay ghi đè isolation đang chạy.

Một số lưu ý:
- Lời gọi phải thực sự đi qua transaction proxy/interceptor.
- Các repository phải dùng cùng transaction manager và tài nguyên được enlist.
- Nếu có nhiều datasource, một annotation không tự tạo transaction phân tán.
- REQUIRES_NEW có thể tạo transaction độc lập nhưng tiêu thụ thêm connection và thay đổi ranh giới commit.
- Read-only không tự thay thế isolation.
- Transaction dài giữ snapshot hoặc khóa lâu có thể ảnh hưởng hiệu năng.

## 11. Chọn mức nào cho từng nhu cầu?

| Nhu cầu | Lựa chọn để đánh giá | Cần lưu ý |
| --- | --- | --- |
| Chỉ cần mỗi câu lệnh đọc dữ liệu đã commit | READ COMMITTED | Nhiều câu SELECT có thể thấy thời điểm khác nhau |
| Đọc lại cùng hàng/đọc nhiều phần trong một snapshot | REPEATABLE READ hoặc snapshot transaction phù hợp | Cơ chế và phantom khác giữa DBMS |
| Chỉ cần khóa các hàng đã đọc để không bị sửa | Locking REPEATABLE READ ở hệ hỗ trợ | Có thể blocking; không chắc ngăn phantom |
| Ngăn phantom theo predicate | SERIALIZABLE hoặc khóa phạm vi phù hợp | Phụ thuộc index, DBMS và execution plan |
| Bảo vệ bất biến liên hàng trước write skew | SERIALIZABLE, khóa chung hoặc ràng buộc dữ liệu | Snapshot isolation đơn thuần có thể chưa đủ |
| Báo cáo đọc dài và chấp nhận dữ liệu tại một mốc | Snapshot/READ ONLY transaction | Giữ snapshot lâu có chi phí version retention |
| Ứng dụng cần chạy trên nhiều DBMS | Abstraction theo yêu cầu ngữ nghĩa và kiểm thử từng DB | Không chỉ ánh xạ một enum JDBC theo tên |

Đừng nâng mọi transaction lên SERIALIZABLE chỉ để tránh một lỗi báo cáo. Hãy xác định phạm vi nhất quán thực sự cần thiết, rồi chọn cơ chế và đo chi phí.

## 12. Cách kiểm chứng sự khác biệt trên DBMS mục tiêu

Khi có nghi ngờ giữa các hệ quản trị, hãy tạo hai session và thực hiện một lịch có kiểm soát:

1. Tạo hai hàng A, B và ghi giá trị ban đầu.
2. Mở T2 ở mức REPEATABLE READ.
3. Cho T2 đọc A hoặc chạy predicate truy vấn ban đầu.
4. Trong T1, thay đổi hoặc chèn dữ liệu liên quan rồi COMMIT.
5. Cho T2 đọc lại cùng hàng hoặc chạy lại predicate.
6. Quan sát giá trị, thời gian chờ và lỗi.
7. Lặp lại với SELECT thường, SELECT FOR UPDATE/FOR SHARE và SERIALIZABLE nếu DBMS hỗ trợ.
8. Reset dữ liệu giữa các lần để kết quả không phụ thuộc lần thử trước.

Khi so sánh, ghi rõ phiên bản DBMS, storage engine, isolation level, autocommit, index, cấu hình row versioning, driver và transaction manager. Không dùng H2 hoặc một database giả lập làm bằng chứng duy nhất cho hành vi PostgreSQL/MySQL/SQL Server/Oracle nếu mục tiêu là xác nhận semantics của hệ thống sản xuất.

### Kịch bản phantom cơ bản

~~~sql
-- T2: mở transaction REPEATABLE READ và truy vấn
SELECT order_id
FROM orders
WHERE status = 'PENDING';

-- T1: session khác
INSERT INTO orders(order_id, status)
VALUES (9001, 'PENDING');
COMMIT;

-- T2: truy vấn lại cùng predicate
SELECT order_id
FROM orders
WHERE status = 'PENDING';
~~~

Nếu hàng 9001 xuất hiện ở lần đọc thứ hai, implementation/loại đọc đó cho phép phantom trong kịch bản này. Nếu không xuất hiện, cần hiểu vì sao: snapshot cố định, key-range lock, predicate lock hoặc lý do khác. Quan sát một lần thử không đủ để suy ra toàn bộ semantics của mức cô lập.

## 13. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “REPEATABLE READ ở mọi DBMS giống nhau.” | Tên mức có thể cùng xuất hiện nhưng implementation, phantom và write skew khác nhau |
| “Không thấy non-repeatable read thì đã serializable.” | Không. Write skew vẫn có thể xảy ra dưới snapshot isolation |
| “REPEATABLE READ luôn khóa hàng.” | MVCC có thể cho đọc phiên bản cũ mà không khóa reader/writer theo cách khóa truyền thống |
| “REPEATABLE READ luôn ngăn phantom.” | SQL cổ điển cho phép phantom; một số implementation mạnh hơn, số khác cần SERIALIZABLE/range locking |
| “READ COMMITTED không dirty read nghĩa là báo cáo nhiều câu luôn nhất quán.” | Các statement có thể dùng snapshot khác nhau |
| “JDBC setTransactionIsolation bảo đảm cùng semantics trên mọi driver.” | JDBC cung cấp mức trừu tượng; cần xác minh mapping và khả năng hỗ trợ của driver/DBMS |
| “Spring annotation bên trong luôn ghi đè transaction ngoài.” | REQUIRED thường tham gia transaction hiện có; thuộc tính bên trong có thể không tạo hiệu lực mới |
| “Retry riêng câu SQL thất bại là đủ.” | Serialization failure thường yêu cầu retry toàn bộ transaction và logic đọc liên quan |
| “Snapshot cũ luôn là lỗi.” | Snapshot cũ là chủ đích của consistent read; cần xem yêu cầu freshness của nghiệp vụ |

## 14. Tự kiểm tra

**Câu 1.** T2 đọc A=600 trong transaction REPEATABLE READ. T1 commit A=500. T2 đọc lại A. Điều gì có thể xảy ra?

**Trả lời:** Trong PostgreSQL snapshot-based và MySQL/InnoDB consistent read theo read view, T2 thường tiếp tục thấy phiên bản cũ 600. Với locking REPEATABLE READ của SQL Server, T1 có thể phải chờ do shared lock của T2.

**Câu 2.** REPEATABLE READ có luôn ngăn phantom không?

**Trả lời:** Không thể kết luận chỉ từ tên. PostgreSQL transaction snapshot ngăn hàng commit sau snapshot xuất hiện trong SELECT thông thường; SQL Server locking REPEATABLE READ có thể cho phantom; InnoDB cần phân biệt consistent read với locking read và next-key lock.

**Câu 3.** PostgreSQL REPEATABLE READ có bảo vệ mọi quy tắc liên quan nhiều hàng không?

**Trả lời:** Không. Write skew vẫn có thể xảy ra. SERIALIZABLE hoặc ràng buộc/khóa phù hợp có thể cần thiết.

**Câu 4.** Trong MySQL/InnoDB, SELECT thường và SELECT FOR UPDATE có nhất thiết đọc theo cùng một read view không?

**Trả lời:** Không. SELECT thường là consistent read, còn FOR UPDATE là locking/current read có semantics khác.

**Câu 5.** Trong SQL Server, nếu muốn bảo vệ phạm vi truy vấn khỏi phantom theo mô hình khóa, mức nào cần được xem xét?

**Trả lời:** SERIALIZABLE với key-range locks khi predicate/index và execution plan cho phép bảo vệ phạm vi tương ứng.

**Câu 6.** Oracle không cung cấp tên REPEATABLE READ như PostgreSQL. Cần làm gì khi chuyển ứng dụng?

**Trả lời:** Xác định yêu cầu thực tế (đọc lại cùng snapshot, ngăn write skew, chỉ đọc hay cập nhật) rồi ánh xạ sang READ ONLY hoặc SERIALIZABLE phù hợp, sau đó kiểm thử trên Oracle.

## 15. Ghi nhớ

REPEATABLE READ là một lựa chọn cô lập hữu ích khi các lần đọc trong cùng transaction cần ổn định. Nhưng **mức ổn định được cung cấp phụ thuộc cơ chế của DBMS**: snapshot có thể giữ ảnh chụp đến cuối transaction; khóa có thể ngăn sửa hàng đã đọc nhưng không nhất thiết ngăn hàng mới xuất hiện; locking read và consistent read có thể khác nhau trong cùng một sản phẩm.

Khi thiết kế hoặc chuyển đổi hệ quản trị, đừng chỉ hỏi “DB có REPEATABLE READ không?”. Hãy hỏi rõ:
- Các SELECT trong cùng transaction dùng cùng snapshot hay không?
- Truy vấn có thể thấy phantom không?
- Read skew hoặc write skew có thể xảy ra không?
- Cập nhật trên hàng đã bị thay đổi sẽ chờ, bị từ chối hay được xử lý theo cách nào?
- Ứng dụng cần retry loại lỗi nào, và retry ở cấp câu lệnh hay toàn transaction?

**Chính câu trả lời cho các câu hỏi này, được xác nhận trên DBMS và phiên bản thực tế, mới là cơ sở để chọn isolation level phù hợp.**
