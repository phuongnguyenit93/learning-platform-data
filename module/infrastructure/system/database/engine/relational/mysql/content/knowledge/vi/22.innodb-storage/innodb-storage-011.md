# Undo log, history list và các tác vụ purge

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành cơ sở dữ liệu quan hệ. Bên cạnh redo log phục vụ crash recovery, InnoDB dùng **undo log** để hoàn tác thay đổi chưa commit và cung cấp phiên bản dữ liệu cũ cho consistent read. Khi transaction sửa hoặc xóa dữ liệu, các phiên bản cũ có thể phải được giữ lại một thời gian. Những undo record không còn transaction nào cần sẽ được tiến trình **purge** dọn dẹp.

History list phản ánh lượng undo history đang chờ purge. Nếu một transaction giữ read view cũ quá lâu, purge không thể loại bỏ những phiên bản mà snapshot đó vẫn có thể cần. History list vì thế có thể tăng, undo tablespace phình to, truy vấn phải đi qua nhiều phiên bản hơn và áp lực I/O tăng. Muốn vận hành tốt InnoDB, cần hiểu vòng đời undo record, read view, history list, purge thread, cách theo dõi và cách xử lý nguyên nhân gây purge lag.

## 1. Undo log giải quyết vấn đề gì?

Một câu UPDATE không chỉ thay giá trị hiện tại của hàng. InnoDB còn cần giữ đủ thông tin để:

- Hoàn tác thay đổi nếu transaction rollback.
- Khôi phục trạng thái nhất quán khi một transaction khác cần đọc snapshot cũ.
- Duy trì lịch sử phiên bản cho đến khi không còn read view nào cần chúng.

Ví dụ, tài khoản có balance = 1000. Transaction A cập nhật balance thành 900. Một transaction đọc theo snapshot được tạo trước thay đổi vẫn phải nhìn thấy balance = 1000. InnoDB dùng undo information để dựng lại phiên bản cũ cho consistent read.

Undo log lưu thông tin cần thiết để đảo ngược thay đổi hoặc dựng lại phiên bản trước đó. Nó không phải bản sao đầy đủ của toàn bộ bảng và cũng không phải redo log.

### 1.1. Undo log và redo log khác nhau

| Thành phần | Mục đích chính | Câu hỏi được trả lời |
|---|---|---|
| Undo log | Rollback và dựng phiên bản cũ cho consistent read | Trước thay đổi này, hàng có giá trị gì? |
| Redo log | Crash recovery, phát lại thay đổi đã được ghi nhận để khôi phục trang dữ liệu | Những thay đổi nào cần được phát lại sau sự cố? |
| Binary log | Ghi các sự kiện thay đổi dữ liệu ở mức server để replication và point-in-time recovery | Những thay đổi logic nào đã được ghi vào binlog? |

Undo và redo phục vụ hai hướng khác nhau. Undo giúp quay về trạng thái trước thay đổi; redo giúp phát lại thay đổi cần thiết sau crash. InnoDB cũng phải bảo đảm các thay đổi undo có thể phục hồi sau crash, vì vậy undo page được bảo vệ bởi cơ chế redo phù hợp. Điều đó không biến undo log thành redo log.

### 1.2. Undo log không phải audit log

Undo history có mục tiêu kỹ thuật và chỉ được giữ đến khi không còn cần thiết cho rollback hoặc consistent read. Nó không phải lịch sử nghiệp vụ lâu dài để trả lời ai đã sửa dữ liệu vào tháng trước. Nếu cần audit trail, hãy thiết kế bảng audit hoặc hệ thống event riêng với thời hạn lưu và quyền truy cập phù hợp.

## 2. Hai loại undo record

InnoDB tạo các undo record khác nhau tùy thao tác:

| Loại | Vai trò | Vòng đời khái quát |
|---|---|---|
| Insert undo | Hoàn tác hàng được chèn nếu transaction rollback | Sau khi transaction commit, thông tin này không cần cho consistent read và có thể được giải phóng |
| Update undo | Hoàn tác UPDATE/DELETE và dựng phiên bản cũ cho consistent read | Có thể phải giữ sau commit cho đến khi purge xác định không còn read view nào cần |

### 2.1. Insert undo

Khi transaction INSERT một hàng, InnoDB ghi undo information đủ để xóa hàng đó nếu transaction rollback. Sau khi transaction commit, một consistent read mới không cần nhìn thấy trạng thái trước khi hàng được tạo theo cách dùng update version chain; vì vậy insert undo có thể được giải phóng theo vòng đời của transaction.

Điều này không có nghĩa hàng vừa insert có thể bị purge ngay sau commit. Hàng đã commit là dữ liệu hiện tại và vẫn tồn tại. Phần được giải phóng là undo information dùng để hoàn tác thao tác insert.

### 2.2. Update undo

Khi transaction UPDATE một hàng, InnoDB ghi undo information chứa dữ liệu cũ cần thiết để rollback và dựng phiên bản trước. Nếu transaction commit, phiên bản mới trở thành dữ liệu hiện tại, nhưng phiên bản cũ vẫn có thể cần cho read view được tạo trước commit.

Với DELETE, InnoDB thường đánh dấu bản ghi là delete-marked thay vì xóa vật lý ngay lập tức. Undo information giúp consistent read cũ tiếp tục nhìn thấy hàng trước khi xóa. Khi không còn read view nào cần phiên bản đó, purge có thể loại bỏ lịch sử cũ và dọn bản ghi đã đánh dấu xóa.

### 2.3. Một hàng có thể có chuỗi phiên bản

Giả sử balance ban đầu là 1000:

1. Transaction A đổi balance thành 900 và commit.
2. Transaction B đổi balance thành 800 và commit.
3. Một read view cũ được tạo trước cả hai lần cập nhật.

InnoDB có thể phải đi qua chuỗi phiên bản để dựng giá trị 1000 cho read view cũ. Phiên bản hiện tại là 800; undo chain chứa thông tin cần để lần ngược qua 900 rồi về 1000.

Minh họa khái niệm:

~~~text
Phiên bản hiện tại trên clustered index
balance = 800
       |
       | undo information
       v
Phiên bản trước
balance = 900
       |
       | undo information
       v
Phiên bản cũ hơn
balance = 1000
~~~

Đây là mô hình khái niệm của version chain. Cấu trúc vật lý và cách lưu từng trường trong record/undo page phức tạp hơn sơ đồ.

## 3. Undo record, rollback segment và undo tablespace

Undo record được lưu trong các undo log thuộc rollback segment. Rollback segment quản lý các undo log và được lưu trong undo tablespace hoặc system tablespace tùy cấu hình và phiên bản.

Các khái niệm cần phân biệt:

- **Undo record:** thông tin mô tả thay đổi cần đảo ngược hoặc phiên bản cũ cần dựng lại.
- **Undo log:** tập các undo record gắn với một transaction và loại thao tác.
- **Rollback segment:** cấu trúc InnoDB quản lý các undo log.
- **Undo tablespace:** tablespace dành cho undo data, có file vật lý riêng trong các cấu hình MySQL hiện đại.

Không nên gọi toàn bộ file undo tablespace là một undo log. Một tablespace có thể chứa nhiều rollback segment và undo log của nhiều transaction.

### 3.1. Transaction và rollback segment

Khi transaction thay đổi dữ liệu, InnoDB cấp phát và sử dụng undo log phù hợp. Một transaction có thể cần undo log cho thao tác insert và update. Undo log được quản lý trong rollback segment, hỗ trợ rollback và duy trì lịch sử phiên bản.

### 3.2. Undo tablespace

Undo tablespace là nơi lưu các rollback segment được cấu hình để nằm ngoài system tablespace. Tách undo data giúp quản lý dung lượng và vòng đời file undo thuận tiện hơn trong môi trường hỗ trợ tính năng này.

Undo tablespace vẫn là thành phần nội bộ quan trọng của InnoDB. Không xóa hoặc di chuyển file undo bằng thao tác filesystem khi MySQL đang quản lý chúng. Mọi thay đổi phải theo cơ chế quản trị tablespace mà phiên bản MySQL hỗ trợ.

### 3.3. Kiểm tra tablespace

Trên MySQL 8.0, có thể xem metadata tablespace:

~~~sql
SELECT
    SPACE,
    NAME,
    SPACE_TYPE,
    FILE_SIZE,
    ALLOCATED_SIZE,
    STATE
FROM information_schema.innodb_tablespaces
WHERE SPACE_TYPE = 'Undo';
~~~

Các cột và trạng thái hiển thị phụ thuộc phiên bản. Dùng kết quả để nhận diện undo tablespace và theo dõi kích thước file; không xem FILE_SIZE hoặc ALLOCATED_SIZE là lượng undo history còn cần thiết theo nghĩa logic.

## 4. MVCC và read view sử dụng undo như thế nào?

InnoDB dùng Multi-Version Concurrency Control (MVCC) để consistent read có thể đọc một snapshot mà không cần khóa mọi hàng đang được đọc. Read view xác định transaction nào đã commit tại thời điểm snapshot được tạo và transaction nào chưa commit hoặc không được snapshot nhìn thấy.

Khi hàng hiện tại đã bị một transaction khác cập nhật sau thời điểm snapshot, InnoDB có thể dùng undo chain để dựng phiên bản cũ phù hợp với read view.

### 4.1. Snapshot trong REPEATABLE READ

Với REPEATABLE READ mặc định của InnoDB, consistent read đầu tiên trong transaction thường tạo read view; các consistent read tiếp theo trong cùng transaction dùng lại snapshot đó. Snapshot có thể cần các phiên bản dữ liệu cũ cho đến khi transaction kết thúc.

Ví dụ:

~~~sql
-- Session A
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

Sau SELECT đầu tiên, read view của Session A được thiết lập. Trong khi A vẫn mở, Session B cập nhật balance và commit:

~~~sql
-- Session B
UPDATE accounts
SET balance = balance + 100
WHERE account_id = 1;
~~~

Nếu Session A đọc lại bằng consistent SELECT trong cùng transaction, nó tiếp tục thấy snapshot cũ. InnoDB phải giữ đủ undo history để có thể dựng giá trị đó.

### 4.2. Snapshot trong READ COMMITTED

Với READ COMMITTED, mỗi consistent read thông thường tạo snapshot mới cho từng statement. Vì vậy, một transaction dài ở READ COMMITTED không giữ cùng một read view xuyên suốt các câu SELECT như REPEATABLE READ; tuy nhiên, một statement đang chạy vẫn có thể cần snapshot trong thời gian thực thi.

Đổi isolation level chỉ để giảm history list có thể thay đổi kết quả nghiệp vụ. Hãy đánh giá semantics đọc trước khi đổi.

### 4.3. Locking read khác consistent read

SELECT ... FOR UPDATE và SELECT ... FOR SHARE là locking read. Chúng đọc dữ liệu hiện hành theo quy tắc locking của InnoDB và lấy khóa cần thiết; không nên xem chúng như consistent read dùng snapshot cũ thông thường.

Một transaction có thể vừa thực hiện consistent read, vừa thực hiện locking read. Vì vậy, khi điều tra read view giữ purge, cần xác định transaction có consistent read nào và thời điểm read view được tạo, không chỉ nhìn câu SQL hiện tại.

## 5. History list là gì?

Sau khi transaction cập nhật hoặc xóa dữ liệu commit, update undo có thể tiếp tục được giữ trong lịch sử để phục vụ các read view cũ. Các undo log đã commit và còn cần cho MVCC được liên kết trong history list. Purge thread sẽ xử lý các phần lịch sử này khi chúng không còn cần thiết.

**History list length** là chỉ số thể hiện độ dài của undo history đang chờ purge trong InnoDB. Nó không phải số hàng trong bảng, không phải số transaction đang mở và cũng không phải số byte chính xác của undo tablespace.

### 5.1. History list tăng khi nào?

History list có thể tăng khi:

- Workload có nhiều UPDATE hoặc DELETE được commit liên tục.
- Một transaction giữ read view cũ khiến purge không thể loại bỏ các phiên bản mới hơn mà snapshot vẫn có thể cần.
- Purge không xử lý kịp tốc độ phát sinh undo history.
- Một lượng lớn dữ liệu bị cập nhật hoặc xóa trong thời gian ngắn.

History list tăng trong một đợt ghi cao không tự động chứng minh có lỗi. Cần xem xu hướng theo thời gian, tốc độ purge và tuổi của transaction/read view lâu nhất.

### 5.2. History list không phải dung lượng file

History list length là chỉ số về undo history chưa purge, không cho biết chính xác file undo tablespace chiếm bao nhiêu dung lượng trên đĩa. File tablespace có thể giữ lại vùng đã cấp phát để tái sử dụng ngay cả sau khi purge giải phóng các undo page bên trong.

Vì vậy, history list giảm không đồng nghĩa kích thước file undo trên filesystem lập tức giảm. Ngược lại, file lớn không nhất thiết có nghĩa toàn bộ dữ liệu trong đó vẫn còn cần cho consistent read.

### 5.3. History list không phải số lượng giao dịch

Một transaction có thể tạo nhiều undo record và nhiều page; một số transaction khác tạo rất ít. Không thể suy ra số transaction cũ chỉ bằng cách nhìn history list length.

Không đặt ngưỡng cảnh báo dựa trên một con số cố định áp dụng cho mọi hệ thống. Hãy thiết lập baseline theo workload, dung lượng, tốc độ tăng/giảm và khả năng purge của server.

## 6. Purge làm nhiệm vụ gì?

Purge là nhóm tác vụ nền của InnoDB dọn dẹp undo history và dữ liệu đã được đánh dấu xóa khi không còn read view nào cần các phiên bản cũ đó.

Purge có thể:

- Loại bỏ update undo không còn cần cho consistent read.
- Dọn các phiên bản cũ trong version chain.
- Xóa vật lý các record đã được delete-marked khi đủ điều kiện.
- Thu hồi không gian bên trong cấu trúc InnoDB để tái sử dụng.

Purge không phải thao tác DELETE do ứng dụng gửi và không chạy như một câu SQL riêng trong transaction nghiệp vụ.

### 6.1. Vì sao không xóa phiên bản cũ ngay khi commit?

Một transaction khác có thể đã tạo read view trước khi thay đổi commit. Nếu InnoDB xóa ngay phiên bản cũ, transaction đọc snapshot sẽ không thể nhìn thấy dữ liệu đúng tại thời điểm snapshot.

Do đó, commit không đồng nghĩa undo history được giải phóng ngay. InnoDB phải chờ đến khi không còn read view nào có thể cần phiên bản đó.

### 6.2. Điều kiện purge được phép xóa

Một phiên bản chỉ có thể được purge khi không còn transaction/read view đang hoạt động cần phiên bản đó để dựng consistent read. Purge xét thứ tự và giới hạn an toàn của lịch sử transaction; nó không đơn giản xóa mọi undo record đã commit.

### 6.3. Purge và DELETE

Ví dụ:

~~~sql
DELETE FROM orders
WHERE created_at < '2024-01-01';
~~~

Với InnoDB, DELETE đánh dấu các record là đã xóa và ghi undo information. Sau khi transaction commit, các read view cũ vẫn có thể cần nhìn thấy những hàng đó. Khi không còn read view cần chúng, purge mới có thể dọn delete-marked record và undo history liên quan.

Điều này giải thích vì sao DELETE hàng triệu bản ghi không nhất thiết làm file dữ liệu giảm ngay. Purge giải phóng các record để InnoDB tái sử dụng không gian nội bộ; thu nhỏ file vật lý là vấn đề khác và phụ thuộc loại tablespace cũng như thao tác quản trị.

## 7. Read view lâu đời gây purge lag

Một nguyên nhân phổ biến khiến history list tăng là transaction giữ read view cũ trong thời gian dài.

Ví dụ:

1. Session A mở transaction REPEATABLE READ và chạy consistent SELECT, tạo snapshot.
2. Session A không commit/rollback và giữ connection mở.
3. Session B và các writer khác liên tục UPDATE/DELETE rồi commit.
4. Undo history của các thay đổi mới cần được giữ để Session A có thể dựng snapshot cũ.
5. Purge không thể đi qua ranh giới lịch sử mà read view cũ còn cần.
6. History list tăng dần dù purge thread vẫn hoạt động.

### 7.1. Transaction idle vẫn có thể giữ read view

Một transaction không chạy câu SQL trong thời điểm hiện tại vẫn có thể giữ snapshot được tạo bởi consistent read trước đó. Vì vậy, process list có thể cho thấy session đang Sleep nhưng transaction vẫn mở và giữ read view.

Đây là lý do không chỉ tìm query đang chạy lâu. Cần kiểm tra transaction đã mở bao lâu, có read view hay không và session có đang idle trong transaction.

### 7.2. Transaction lâu không phải lúc nào cũng giữ read view cũ

Một transaction chưa thực hiện consistent read có thể chưa tạo read view theo cách tương tự. Trong READ COMMITTED, snapshot thông thường được tạo theo từng statement thay vì giữ xuyên transaction. Vì thế, không kết luận chỉ từ tuổi transaction; hãy xem isolation level, loại read và trạng thái transaction.

### 7.3. Dấu hiệu của purge lag

- History list length tăng liên tục hoặc giảm rất chậm.
- Có transaction lâu đời, đặc biệt ở REPEATABLE READ, đã tạo consistent read.
- Undo tablespace tăng kích thước hoặc sử dụng dung lượng lớn.
- Các consistent read có thể phải đi qua nhiều version hơn.
- Purge không theo kịp lượng update/delete phát sinh.
- I/O và dung lượng lưu trữ tăng, thời gian truy vấn hoặc bảo trì có thể xấu đi.

Không phải mọi dấu hiệu đều xuất hiện cùng lúc. Cần đối chiếu history list, transaction lâu nhất, undo tablespace và workload ghi.

## 8. Purge thread và khả năng xử lý nền

InnoDB dùng purge thread để xử lý undo history. Số lượng purge thread có thể điều chỉnh bằng innodb_purge_threads trong các phiên bản hỗ trợ.

Kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'innodb_purge_threads';
SHOW VARIABLES LIKE 'innodb_purge_batch_size';
~~~

Purge thread làm việc nền, tách khỏi luồng request SQL của ứng dụng. Tăng số thread có thể giúp xử lý song song một số workload purge, nhưng không thể vượt qua ranh giới do read view cũ giữ lại. Nếu purge không được phép xóa phiên bản vì một transaction vẫn cần, tăng thread không giải quyết nguyên nhân.

### 8.1. Khi nào điều chỉnh purge thread?

Chỉ cân nhắc điều chỉnh sau khi:

- Đã xác nhận không có transaction/read view lâu đời chặn purge.
- History list vẫn tăng do tốc độ phát sinh undo vượt khả năng xử lý.
- CPU, I/O và workload cho thấy purge là nút thắt.
- Đã thử trên môi trường staging với tải tương tự.

Không tăng thread theo phản xạ. Nhiều thread hơn cũng có thể tăng tranh chấp tài nguyên hoặc I/O.

### 8.2. Purge batch size

innodb_purge_batch_size ảnh hưởng lượng công việc purge xử lý theo batch. Thay đổi nó có thể tác động đến độ mượt và hiệu suất của tác vụ nền. Hãy giữ cấu hình mặc định trừ khi có số liệu chứng minh cần điều chỉnh.

## 9. Theo dõi history list và transaction

### 9.1. SHOW ENGINE INNODB STATUS

Lệnh quan trọng để quan sát trạng thái InnoDB:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Tìm phần TRANSACTIONS và dòng có History list length. Cùng khu vực có thể cung cấp thông tin về:

- Transaction đang hoạt động.
- Transaction đang chờ khóa.
- Read view và transaction ID liên quan.
- Trạng thái purge và mốc transaction mà purge đã xử lý.
- Deadlock gần nhất.

Chụp số liệu theo chu kỳ để xem xu hướng. Một lần đọc đơn lẻ không cho biết history list đang tăng hay đã bắt đầu giảm.

### 9.2. Theo dõi bằng INNODB_METRICS

MySQL cung cấp metric trx_rseg_history_len trong INFORMATION_SCHEMA.INNODB_METRICS ở các phiên bản hỗ trợ:

~~~sql
SELECT
    NAME,
    COUNT,
    STATUS,
    COMMENT
FROM information_schema.innodb_metrics
WHERE NAME = 'trx_rseg_history_len';
~~~

Metric có thể cần được bật tùy cấu hình monitoring và phiên bản. Nếu không có hàng hoặc metric chưa hoạt động, dùng SHOW ENGINE INNODB STATUS và kiểm tra cấu hình metric thay vì tự suy ra giá trị bằng một công thức khác.

### 9.3. Tìm transaction lâu đời

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_isolation_level,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Tập trung vào transaction bắt đầu sớm, đặc biệt transaction vẫn mở và có thể giữ read view. trx_query có thể NULL nếu transaction hiện không chạy câu SQL; điều đó không chứng minh transaction không giữ snapshot.

### 9.4. Ghép với process list

Có thể tìm connection tương ứng:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Đối chiếu ID với trx_mysql_thread_id trong INNODB_TRX. Một connection ở trạng thái Sleep nhưng vẫn có transaction mở là dấu hiệu cần điều tra.

### 9.5. Theo dõi undo tablespace

~~~sql
SELECT
    NAME,
    SPACE_TYPE,
    FILE_SIZE,
    ALLOCATED_SIZE,
    STATE
FROM information_schema.innodb_tablespaces
WHERE SPACE_TYPE = 'Undo';
~~~

Theo dõi xu hướng dung lượng theo thời gian và đối chiếu với history list. Không kết luận purge bị kẹt chỉ vì file undo vẫn lớn; InnoDB có thể giữ không gian đã cấp phát để tái sử dụng.

## 10. Điều tra và xử lý một history list tăng bất thường

Khi history list tăng kéo dài, xử lý theo trình tự:

1. Ghi lại History list length tại nhiều thời điểm để xác định xu hướng.
2. Kiểm tra workload UPDATE/DELETE và các batch ghi lớn gần thời điểm tăng.
3. Liệt kê transaction bằng INFORMATION_SCHEMA.INNODB_TRX.
4. Đối chiếu tuổi transaction, isolation level, thread ID và process list.
5. Xác định session idle trong transaction hoặc consistent read lâu đời.
6. Kiểm tra undo tablespace và dung lượng đĩa.
7. Xác định purge có đang tiến triển hay bị chặn bởi read view.
8. Giải phóng transaction cũ theo quyết định nghiệp vụ; không kill session trước khi hiểu tác động rollback.
9. Theo dõi history list có giảm sau khi read view được giải phóng hay không.
10. Chỉ sau đó mới cân nhắc điều chỉnh purge thread hoặc cấu hình purge lag.

### 10.1. Xử lý transaction lâu đời

Nếu xác định một session giữ read view quá lâu:

- Liên hệ ứng dụng hoặc chủ sở hữu connection để hiểu transaction đang làm gì.
- Nếu transaction đã bị bỏ quên, kết thúc theo quy trình vận hành.
- Ưu tiên COMMIT hoặc ROLLBACK có kiểm soát nếu ứng dụng còn điều khiển được.
- Nếu phải KILL connection, chuẩn bị cho thời gian rollback và tác động lên workload.

Không KILL hàng loạt connection chỉ vì history list tăng. Rollback một transaction lớn cũng tiêu tốn I/O và thời gian; cần xác định session nào thực sự là nguyên nhân và có thể kết thúc an toàn.

### 10.2. Giảm tốc độ phát sinh undo

Nếu workload ghi lớn tạo undo nhanh hơn purge:

- Chia thao tác cập nhật/xóa lớn thành batch nhỏ nếu nghiệp vụ cho phép.
- Giữ transaction ngắn và commit thường xuyên theo ranh giới nghiệp vụ.
- Tối ưu index và điều kiện để tránh scan/update nhiều hàng không cần thiết.
- Tránh cập nhật cùng một hàng nhiều lần trong một transaction nếu có thể hợp nhất thao tác.
- Chạy công việc bảo trì vào thời điểm phù hợp với tải hệ thống.

Chia batch thành nhiều transaction làm thay đổi tính nguyên tử toàn bộ. Chỉ áp dụng nếu nghiệp vụ chấp nhận mỗi batch là một đơn vị commit độc lập và có cách tiếp tục an toàn khi lỗi giữa chừng.

## 11. Purge lag và các biến điều tiết

MySQL có các biến cấu hình liên quan đến purge lag:

- innodb_max_purge_lag: ngưỡng history list length mà khi vượt quá có thể khiến InnoDB trì hoãn một số thao tác DML để giúp purge bắt kịp.
- innodb_max_purge_lag_delay: giới hạn độ trễ tối đa áp dụng cho DML do cơ chế purge lag.

Kiểm tra giá trị:

~~~sql
SHOW VARIABLES LIKE 'innodb_max_purge_lag';
SHOW VARIABLES LIKE 'innodb_max_purge_lag_delay';
~~~

Các biến này điều tiết tốc độ phát sinh thêm undo bằng cách tạo delay; chúng không xóa history list ngay và không giải phóng read view cũ.

### 11.1. Không đặt ngưỡng tùy tiện

Một ngưỡng phù hợp phụ thuộc dung lượng, loại workload, khả năng I/O, tốc độ purge và mức trễ ứng dụng chấp nhận. Nếu đặt quá thấp, DML có thể bị trì hoãn thường xuyên; nếu đặt quá cao, history list có thể tích lũy lớn trước khi hệ thống điều tiết.

Hãy đo baseline và thử nghiệm trên staging. Không áp dụng cấu hình global trong production chỉ dựa trên một snapshot history list.

### 11.2. Throttle không thay thế xử lý nguyên nhân

Nếu một read view cũ chặn purge, việc làm chậm DML có thể giảm tốc độ tích lũy nhưng không làm phiên bản cũ trở nên có thể purge. Cần giải phóng transaction/read view giữ lâu trước.

## 12. Undo tablespace và truncate

Undo tablespace có thể giữ file lớn sau khi workload ghi cao kết thúc. Dọn history list và trả không gian bên trong tablespace để tái sử dụng là hai việc khác với thu nhỏ file vật lý.

Một số phiên bản MySQL hỗ trợ tự động truncate undo tablespace khi cấu hình và điều kiện cho phép. Các biến thường cần kiểm tra gồm:

~~~sql
SHOW VARIABLES LIKE 'innodb_undo_log_truncate';
SHOW VARIABLES LIKE 'innodb_max_undo_log_size';
SHOW VARIABLES LIKE 'innodb_undo_tablespaces';
~~~

Ý nghĩa và khả năng thay đổi của các biến phụ thuộc phiên bản MySQL. Trước khi dùng, kiểm tra tài liệu đúng phiên bản server và trạng thái tablespace.

### 12.1. Điều kiện tổng quát để truncate

Việc truncate không thể tùy tiện thực hiện trên undo tablespace vẫn đang được sử dụng cho transaction hoạt động. InnoDB cần chuyển hoặc chờ các rollback segment liên quan không còn active trong tablespace đó, rồi mới có thể thực hiện quy trình truncate an toàn.

Khi bật cơ chế tự động, InnoDB có thể chọn undo tablespace đủ điều kiện để truncate theo ngưỡng cấu hình. Không nên xóa file undo trực tiếp bằng filesystem hoặc tự thay tên file để giải phóng dung lượng.

### 12.2. Truncate không phải purge

| Hoạt động | Mục tiêu |
|---|---|
| Purge | Loại bỏ undo history và delete-marked record không còn cần cho MVCC |
| Reuse | Tái sử dụng không gian đã giải phóng bên trong tablespace |
| Truncate undo tablespace | Thu hồi không gian file undo khi tablespace đủ điều kiện |

Purge phải làm cho undo history không còn cần thiết trước. Truncate là bước quản lý dung lượng vật lý ở mức tablespace và có điều kiện riêng.

## 13. Ảnh hưởng của transaction lớn và DELETE hàng loạt

Một transaction sửa hoặc xóa hàng triệu bản ghi có thể tạo lượng undo rất lớn. Nếu transaction chưa commit, undo cần thiết để rollback vẫn được giữ. Sau commit, update undo vẫn có thể cần cho read view cũ; purge phải xử lý khối lượng lịch sử lớn trước khi thu hồi được.

### 13.1. Transaction lớn chưa commit

Trong lúc transaction còn mở:

- Undo cần thiết để rollback vẫn được giữ.
- Các khóa có thể tiếp tục được giữ.
- Rollback có thể mất thời gian nếu lượng thay đổi lớn.
- Transaction khác có thể bị block.

### 13.2. Sau khi transaction lớn commit

Sau commit, transaction không còn cần undo để rollback, nhưng các read view cũ có thể vẫn cần version history. Purge chỉ có thể loại bỏ phần lịch sử đã an toàn.

### 13.3. Xóa theo batch

Nếu nghiệp vụ cho phép, thay vì một DELETE rất lớn:

~~~sql
DELETE FROM audit_events
WHERE created_at < '2023-01-01'
ORDER BY event_id
LIMIT 1000;
~~~

Ứng dụng hoặc job có thể lặp từng batch, commit mỗi batch và dừng khi số hàng bị ảnh hưởng bằng 0. Cần xác định điều kiện lọc có index phù hợp và bảo đảm mỗi batch tiến triển.

Không chạy lặp vô hạn nếu batch không xóa được hàng do dữ liệu hoặc điều kiện không đổi. Ghi nhận số hàng xóa, thời gian mỗi batch và history list trong quá trình vận hành.

### 13.4. Trade-off của batch

Batch nhỏ giảm lượng undo và thời gian giữ khóa trong mỗi transaction, nhưng làm tăng số lần commit và có thể khiến công việc chạy lâu hơn. Batch lớn giảm overhead commit nhưng tạo transaction dài và undo lớn. Chọn kích thước dựa trên đo đạc, không có một con số tối ưu cho mọi bảng.

## 14. Các hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| Commit là undo log được xóa ngay | Update undo có thể vẫn cần cho read view cũ |
| History list length là số hàng đã xóa | Đây là chỉ số undo history chờ purge, không phải row count |
| History list giảm thì file undo giảm ngay | Tablespace có thể giữ vùng đã cấp phát để tái sử dụng |
| Một transaction Sleep không thể ảnh hưởng purge | Session idle trong transaction vẫn có thể giữ read view |
| Mọi transaction lâu đều giữ read view | Cần xem có consistent read và isolation level nào |
| Tăng innodb_purge_threads luôn chữa purge lag | Không thể purge phiên bản mà read view cũ còn cần |
| Undo log là audit log | Undo history có vòng đời kỹ thuật, không phải lưu vết nghiệp vụ dài hạn |
| DELETE xóa vật lý record ngay khi commit | InnoDB có thể cần purge delete-marked record sau đó |
| Tăng innodb_max_purge_lag làm purge nhanh hơn | Cơ chế này điều tiết DML, không trực tiếp tăng tốc purge |
| Có thể xóa file undo khi MySQL đang chạy | Undo tablespace do InnoDB quản lý; không xóa trực tiếp bằng filesystem |

## 15. Bài thực hành: quan sát undo history và purge

Thực hiện trên MySQL 8.0 với database lab riêng. Bài này tạo một bảng nhỏ và dùng hai session để quan sát read view giữ phiên bản cũ. Không thực hiện trên production.

### 15.1. Chuẩn bị bảng

Chạy một lần:

~~~sql
CREATE TABLE lab_undo_demo (
    id INT NOT NULL,
    value_text VARCHAR(100) NOT NULL,
    counter_value INT NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO lab_undo_demo (id, value_text, counter_value)
VALUES
    (1, 'initial', 0),
    (2, 'initial', 0);
~~~

### 15.2. Bước 1 — Session A tạo read view

Trong Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT *
FROM lab_undo_demo
WHERE id = 1;
~~~

SELECT đầu tiên tạo consistent read view. Giữ transaction A mở để snapshot vẫn còn hiệu lực.

### 15.3. Bước 2 — Session B cập nhật và commit

Trong Session B:

~~~sql
UPDATE lab_undo_demo
SET value_text = 'updated-1',
    counter_value = counter_value + 1
WHERE id = 1;

UPDATE lab_undo_demo
SET value_text = 'updated-2',
    counter_value = counter_value + 1
WHERE id = 2;
~~~

Với autocommit bật, mỗi UPDATE là một transaction riêng. Có thể gom chúng vào một transaction nếu muốn quan sát nhiều thay đổi cùng commit:

~~~sql
START TRANSACTION;

UPDATE lab_undo_demo
SET value_text = 'updated',
    counter_value = counter_value + 1;

COMMIT;
~~~

Không chạy cả hai cách cập nhật nếu muốn giữ kết quả đơn giản; chọn một cách và ghi lại thời điểm commit.

### 15.4. Bước 3 — Session A đọc lại snapshot

Quay lại Session A:

~~~sql
SELECT *
FROM lab_undo_demo
WHERE id = 1;
~~~

Trong REPEATABLE READ, Session A vẫn thấy phiên bản cũ của snapshot dù Session B đã commit thay đổi mới. Undo information cho phép dựng phiên bản cũ.

### 15.5. Bước 4 — Quan sát transaction và history list

Từ một session quản trị khác:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_isolation_level,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;

SHOW ENGINE INNODB STATUS\G
~~~

Tìm transaction A và ghi lại History list length. Do dữ liệu lab rất nhỏ, history list có thể không tăng đủ rõ để tạo biểu đồ; mục tiêu là xác nhận read view tồn tại và hiểu vì sao purge phải giữ lịch sử cần thiết.

### 15.6. Bước 5 — Kết thúc read view

Trong Session A:

~~~sql
COMMIT;
~~~

Hoặc dùng ROLLBACK nếu không muốn giữ thay đổi nào của Session A. Khi transaction kết thúc, read view được giải phóng. Purge có thể tiến thêm khi không còn read view khác cần các phiên bản cũ.

Kiểm tra lại:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

History list length có thể giảm theo nhịp purge nền, không nhất thiết về 0 ngay lập tức.

### 15.7. Bước 6 — Quan sát undo tablespace và metric

~~~sql
SELECT
    NAME,
    COUNT,
    STATUS
FROM information_schema.innodb_metrics
WHERE NAME = 'trx_rseg_history_len';

SELECT
    NAME,
    SPACE_TYPE,
    FILE_SIZE,
    ALLOCATED_SIZE
FROM information_schema.innodb_tablespaces
WHERE SPACE_TYPE = 'Undo';
~~~

Ghi lại số liệu và giải thích vì sao file undo có thể vẫn lớn dù history list đã giảm.

### 15.8. Bước 7 — Dọn bảng lab

Đảm bảo cả hai session đã kết thúc transaction, sau đó:

~~~sql
DROP TABLE lab_undo_demo;
~~~

Chỉ xóa bảng lab vừa tạo.

**Kết quả cần đạt:** giải thích được undo record dùng cho rollback và MVCC; quan sát read view cũ đọc phiên bản trước; tìm transaction lâu đời; đọc History list length; phân biệt purge với truncate undo tablespace.

## 16. Quy trình vận hành và cảnh báo

Một dashboard theo dõi undo/purge nên có các chỉ số và ngữ cảnh:

- History list length theo thời gian, tốc độ tăng và tốc độ giảm.
- Transaction lâu nhất và isolation level của nó.
- Số transaction đang mở, transaction idle trong connection pool.
- Số hàng được sửa bởi transaction lớn.
- Dung lượng undo tablespace và xu hướng tăng file.
- Tốc độ UPDATE/DELETE và các batch bảo trì.
- CPU/I/O của server và thời gian truy vấn consistent read.

### 16.1. Cảnh báo theo xu hướng

Đặt cảnh báo khi history list tăng liên tục qua nhiều chu kỳ, vượt baseline vận hành hoặc đi kèm undo tablespace tăng nhanh. Kết hợp với tuổi transaction lâu nhất để phân biệt:

- Purge bị chặn bởi read view cũ.
- Purge không theo kịp tốc độ phát sinh undo.
- File undo giữ dung lượng đã cấp phát nhưng history list không còn tăng.

### 16.2. Khi purge đã bắt kịp

Sau khi transaction giữ read view kết thúc, theo dõi history list giảm dần. Không ép truncate tablespace ngay khi thấy một giá trị thấp. Đánh giá cơ chế auto truncate, trạng thái undo tablespace và yêu cầu dung lượng trước khi thay đổi cấu hình.

### 16.3. Khi history list tiếp tục tăng

Nếu không có read view cũ nhưng history list vẫn tăng, kiểm tra lượng ghi, purge thread, I/O và các tác vụ DELETE/UPDATE lớn. Chỉ điều chỉnh purge thread hoặc purge lag sau khi có bằng chứng rằng năng lực xử lý nền là nút thắt.

## 17. Nguyên tắc cần ghi nhớ

- Undo log hỗ trợ rollback và dựng phiên bản cũ cho consistent read; redo log phục vụ crash recovery.
- Insert undo chủ yếu cần để rollback thao tác INSERT; update undo có thể cần sau commit cho MVCC.
- Undo record được quản lý trong undo log và rollback segment; undo tablespace là nơi lưu trữ các rollback segment được cấu hình tương ứng.
- InnoDB dùng read view để quyết định phiên bản nào một consistent read được phép nhìn thấy.
- REPEATABLE READ thường giữ cùng read view từ consistent read đầu tiên đến khi transaction kết thúc; READ COMMITTED tạo snapshot mới cho từng consistent read statement.
- History list length phản ánh undo history đang chờ purge; nó không phải số hàng, số transaction hay dung lượng file chính xác.
- Purge dọn undo history và delete-marked record chỉ khi không còn read view nào cần chúng.
- Transaction idle vẫn có thể giữ read view và chặn purge; cần điều tra tuổi transaction, isolation level và loại read.
- Tăng purge thread không thể vượt qua ranh giới do read view cũ giữ lại.
- innodb_max_purge_lag điều tiết DML khi history list vượt ngưỡng; nó không trực tiếp xóa undo history.
- Undo tablespace có thể giữ không gian đã cấp phát sau purge; truncate là thao tác quản lý file riêng và chỉ thực hiện khi đủ điều kiện.
- DELETE lớn và transaction dài tạo nhiều undo; batch chỉ phù hợp khi nghiệp vụ chấp nhận nhiều ranh giới commit.
- Theo dõi SHOW ENGINE INNODB STATUS, INFORMATION_SCHEMA.INNODB_TRX, INNODB_METRICS và metadata undo tablespace.
- Không xóa file undo trực tiếp bằng filesystem và không coi undo log là audit log.

Undo log, history list và purge là ba phần của cùng vòng đời phiên bản dữ liệu trong InnoDB. Khi transaction tạo read view quá lâu, purge phải giữ lại lịch sử mà snapshot còn cần. Bằng cách theo dõi history list cùng transaction lâu đời, tối ưu transaction và kiểm soát workload ghi, DBA có thể xử lý purge lag đúng nguyên nhân và duy trì hiệu năng ổn định.
