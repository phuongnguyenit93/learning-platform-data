# Undo purge, history list length và giao dịch kéo dài

Trong MySQL, hiệu năng của InnoDB phụ thuộc không chỉ vào truy vấn đang chạy mà còn vào lượng phiên bản dữ liệu cũ phải giữ lại cho các transaction đang mở. Khi một transaction giữ snapshot quá lâu, InnoDB không thể dọn một số undo log và bản ghi đã đánh dấu xóa. History list length vì thế tăng, purge bị chặn ở một mốc cũ, undo tablespace có thể phình to và các thao tác đọc/ghi phải xử lý thêm dữ liệu tồn đọng.

Bài học này giải thích vòng đời undo log, read view và purge; cách đọc history list length; cách tìm transaction giữ snapshot; cách phân biệt purge bị ghim bởi transaction với purge không theo kịp tải ghi; và cách xử lý an toàn trong production. Đây là một phần của năng lực làm chủ MySQL từ transaction, kiểm soát đồng thời đến tối ưu và vận hành cơ sở dữ liệu quan hệ.

## 1. Vì sao InnoDB phải giữ phiên bản dữ liệu cũ?

### 1.1. MVCC và consistent read

InnoDB dùng Multi-Version Concurrency Control (MVCC) để cho phép nhiều transaction đọc và ghi đồng thời. Một câu SELECT thông thường ở mức cô lập REPEATABLE READ hoặc READ COMMITTED thường là consistent nonlocking read: nó đọc dữ liệu theo một snapshot và không cần khóa các hàng mà nó đọc.

Nếu transaction khác cập nhật một hàng sau thời điểm snapshot được tạo, transaction đang đọc vẫn có thể cần nhìn thấy giá trị cũ. InnoDB dựng lại phiên bản đó từ undo log. Nhờ vậy, transaction đọc không phải chờ mọi transaction ghi hoàn tất chỉ để có kết quả nhất quán.

Mỗi bản ghi InnoDB có các trường quản lý phiên bản nội bộ. Trong số đó:

- **DB_TRX_ID** ghi transaction đã tạo hoặc cập nhật phiên bản hàng gần nhất.
- **DB_ROLL_PTR** trỏ đến undo record dùng để dựng lại phiên bản trước.
- **DB_ROW_ID** là row identifier nội bộ trong trường hợp InnoDB phải tự sinh clustered index.

Khi hàng bị DELETE, InnoDB trước hết đánh dấu hàng là đã xóa (delete-mark). Hàng và các index record tương ứng chưa nhất thiết biến mất vật lý ngay lập tức. Một transaction có snapshot cũ vẫn có thể cần đọc phiên bản trước khi xóa.

### 1.2. Undo log phục vụ hai mục đích

Undo log ghi thông tin cần thiết để đảo ngược thay đổi khi ROLLBACK và để tái tạo phiên bản cũ khi consistent read cần đến.

InnoDB phân biệt insert undo và update undo:

- **Insert undo** phục vụ rollback các hàng được thêm bởi transaction. Sau khi transaction commit, insert undo không còn cần cho consistent read và có thể được loại bỏ.
- **Update undo** phục vụ rollback và dựng lại phiên bản cũ cho consistent read. Sau commit, phần undo này vẫn có thể cần thiết cho đến khi không còn read view nào có thể nhìn thấy phiên bản cũ.

Undo log nằm trong undo log segment, thuộc rollback segment. Rollback segment được lưu trong undo tablespace hoặc global temporary tablespace tùy loại thao tác. Trong MySQL 8.0 trở lên, undo log thông thường được lưu trong các undo tablespace riêng được tạo khi khởi tạo instance; cấu hình cụ thể phụ thuộc phiên bản và cách triển khai.

### 1.3. Vì sao transaction chỉ đọc vẫn có thể làm purge bị chậm?

Một transaction chỉ đọc không tạo ra nhiều undo của chính nó, nhưng read view của nó có thể yêu cầu InnoDB giữ lại undo do transaction khác tạo ra.

Ví dụ:

1. Transaction A mở snapshot ở thời điểm T1 và đọc bảng orders.
2. Transaction B cập nhật một hàng trong orders rồi COMMIT ở thời điểm T2.
3. Transaction C tiếp tục cập nhật hoặc xóa dữ liệu và COMMIT.
4. Transaction A vẫn cần nhìn thấy trạng thái tại T1.
5. InnoDB phải giữ các phiên bản cũ mà snapshot của A có thể cần. Purge không thể dọn vượt qua mốc an toàn của read view đó.
6. Khi A kết thúc bằng COMMIT hoặc ROLLBACK, snapshot được giải phóng và purge có thể tiếp tục dọn phần history đã hết người tham chiếu.

Do đó, một kết nối đang ở trạng thái Sleep vẫn có thể là nguyên nhân làm history list tăng nếu transaction và read view của nó vẫn mở. Việc câu SELECT đã chạy xong không có nghĩa transaction đã kết thúc.

## 2. Read view và thời gian sống của snapshot

### 2.1. REPEATABLE READ

REPEATABLE READ là mức cô lập mặc định của InnoDB. Các consistent read trong cùng transaction sử dụng snapshot được thiết lập bởi lần consistent read đầu tiên. Có thể tạo snapshot ngay khi bắt đầu transaction bằng:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;

START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT COUNT(*) FROM orders;

-- Các câu SELECT tiếp theo vẫn đọc cùng snapshot.
-- Kết thúc transaction để giải phóng read view.
COMMIT;
~~~

Nếu ứng dụng mở transaction, thực hiện một SELECT, rồi giữ kết nối mở để chờ người dùng hoặc gọi một dịch vụ khác, read view có thể tồn tại trong suốt thời gian chờ đó. Transaction không cần đang chạy câu SQL mới có thể giữ snapshot cũ.

Nếu transaction bắt đầu bằng START TRANSACTION nhưng chưa thực hiện consistent read, thời điểm tạo read view có thể chưa trùng với thời điểm bắt đầu transaction. Vì vậy, tuổi transaction là chỉ báo quan trọng để tìm ứng viên, nhưng không phải lúc nào cũng chính xác bằng tuổi snapshot.

### 2.2. READ COMMITTED

Với READ COMMITTED, mỗi consistent read trong transaction tạo snapshot mới. Điều này thường làm giảm thời gian giữ một read view cũ so với REPEATABLE READ khi ứng dụng chạy nhiều SELECT trong một transaction dài.

Tuy nhiên, READ COMMITTED không tự giải quyết mọi vấn đề undo:

- Một câu SELECT chạy lâu vẫn giữ snapshot trong suốt thời gian câu lệnh cần đọc.
- Transaction ghi dài vẫn giữ undo cần thiết cho rollback cho đến khi kết thúc.
- Transaction vẫn có thể giữ row lock hoặc các tài nguyên khác.
- Kết quả giữa hai SELECT trong cùng transaction có thể khác nhau do snapshot được làm mới.

Chỉ thay đổi isolation level khi ngữ nghĩa nghiệp vụ cho phép. Không chuyển toàn bộ hệ thống sang READ COMMITTED chỉ để làm history list giảm mà chưa đánh giá tính nhất quán mà ứng dụng đang dựa vào.

### 2.3. Locking read khác consistent read

SELECT ... FOR UPDATE và SELECT ... FOR SHARE là locking read. Chúng đọc trạng thái phù hợp với cơ chế khóa hiện tại, không đơn giản là một consistent nonlocking read như SELECT thông thường.

Locking read có thể giữ row lock cho đến khi transaction kết thúc. Một transaction ghi hoặc locking read kéo dài có thể gây lock wait, chặn DML khác và giữ undo của chính transaction đó cho đến khi commit/rollback.

Cần phân biệt hai vấn đề:

- **Read view cũ** có thể ghim purge dù không giữ row lock.
- **Lock được giữ lâu** có thể chặn transaction khác dù không phải nguyên nhân trực tiếp của history list length.

Một transaction có thể gây cả hai vấn đề nếu nó vừa tạo read view cũ vừa thực hiện thao tác khóa/ghi.

### 2.4. Những tình huống thường tạo snapshot quá lâu

- Ứng dụng tắt autocommit hoặc dùng transaction wrapper nhưng không COMMIT/ROLLBACK trên mọi nhánh xử lý.
- Connection pool trả kết nối về pool khi transaction vẫn mở.
- Một câu SELECT hoàn tất nhưng ứng dụng giữ transaction để chờ thao tác người dùng.
- Một luồng đọc dữ liệu theo kiểu streaming hoặc cursor kéo dài trong khi client xử lý từng phần rất chậm.
- Job báo cáo chạy trong transaction lớn.
- Backup logic dùng mysqldump với tùy chọn --single-transaction trong thời gian dài khi hệ thống có nhiều DML.
- Một tiến trình batch thực hiện nhiều cập nhật trong một transaction rồi mới commit.
- Ứng dụng gặp exception hoặc timeout nhưng đường xử lý lỗi không đóng transaction.

Đặc biệt, một transaction chỉ đọc ở REPEATABLE READ cũng có thể giữ history list. Không nên chỉ tìm các transaction có trx_rows_modified lớn.

## 3. Purge hoạt động như thế nào?

### 3.1. Purge là bước dọn dẹp nền

Purge là công việc nền của InnoDB để xử lý undo log page trong history list sau khi các phiên bản cũ không còn cần cho MVCC hoặc rollback. Công việc này bao gồm loại bỏ các bản ghi đã delete-mark khỏi clustered index và secondary index, rồi giải phóng các undo log page đã xử lý.

DELETE không có nghĩa là hàng và mọi index record bị xóa vật lý ngay tại thời điểm câu lệnh kết thúc. Cần phân biệt:

1. DELETE đánh dấu hàng là đã xóa và ghi undo cần thiết.
2. Transaction commit.
3. Các read view cũ vẫn có thể cần phiên bản trước khi xóa.
4. Khi không còn read view nào cần phiên bản đó, purge có thể xử lý undo và loại bỏ record đã đánh dấu xóa.
5. Trang dữ liệu được giải phóng hoặc có thể được tái sử dụng bên trong tablespace.

UPDATE cũng có thể tạo phiên bản cũ và delete-mark secondary index record cũ khi giá trị cột index thay đổi. Vì vậy, tải UPDATE/DELETE lớn có thể tạo nhiều việc cho purge.

### 3.2. Purge thread và history list

Purge chạy theo lịch nền và sử dụng một hoặc nhiều purge thread. Các thread xử lý undo log page trong history list. Cấu hình số thread được điều khiển bởi biến **innodb_purge_threads**; đây là giới hạn số thread purge được phép dùng, hệ thống có thể tự điều chỉnh số thread thực tế.

Tải DML tập trung vào một bảng có thể khiến việc purge trên bảng đó bị giới hạn bởi một thread, dù cấu hình cho phép nhiều thread hơn. Tăng số purge thread không phải lúc nào cũng tăng thông lượng: các thread có thể tranh chấp trên cùng bảng và cạnh tranh CPU/I/O với thread ứng dụng.

Nếu DML phân tán trên nhiều bảng, tăng khả năng xử lý purge có thể hữu ích sau khi đo và thử nghiệm. Nếu DML tập trung vào một số bảng nóng, cần quan sát contention và hiệu quả thực tế trước khi thay đổi.

### 3.3. Khi nào purge không thể theo kịp?

Có hai nhóm nguyên nhân chính:

**Một read view cũ đang ghim mốc purge**

InnoDB phải giữ các phiên bản mà snapshot cũ có thể cần. Dù purge thread còn CPU và storage, nó không được phép dọn phần history nằm sau mốc an toàn đó. Tăng purge thread không giải quyết được nguyên nhân gốc; cần kết thúc transaction đang giữ snapshot.

**Thông lượng purge thấp hơn tốc độ tạo history**

Không có read view quá cũ nhưng workload UPDATE/DELETE vẫn tạo history nhanh hơn tốc độ purge xử lý. Có thể do DML rất lớn, nhiều thao tác trên cùng bảng, storage chậm, CPU thiếu hoặc cấu hình purge chưa phù hợp với workload.

Hai nhóm này có thể cùng xuất hiện. Trước khi chỉnh biến, cần xác định liệu purge bị ghim bởi read view hay chỉ đang thiếu năng lực xử lý.

## 4. History list length là gì?

### 4.1. Đọc đúng chỉ số

History list length là chỉ số độ dài history list do InnoDB duy trì và được hiển thị trong phần TRANSACTIONS của SHOW ENGINE INNODB STATUS. History list chứa undo log page của các transaction đã commit cần chờ purge xử lý.

Chỉ số này:

- Là chỉ báo về lượng history purge còn phải xử lý.
- Có thể tăng khi hệ thống ghi nhiều hoặc có transaction giữ read view cũ.
- Không phải số hàng đã xóa.
- Không phải số transaction đang mở.
- Không phải dung lượng undo tính bằng byte hoặc MB.
- Không có ánh xạ cố định từ một đơn vị history list sang một số hàng hay một kích thước file.

Hai hệ thống có history list length bằng nhau vẫn có thể có lượng undo bytes, số hàng bị ảnh hưởng và chi phí purge rất khác nhau. Vì vậy, hãy dùng chỉ số để theo dõi xu hướng và ghép với transaction, DML, I/O và kích thước undo tablespace.

### 4.2. Xem history list length bằng SHOW ENGINE INNODB STATUS

Chạy trong MySQL client:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Trong mysql CLI có thể dùng định dạng dọc:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Tìm phần TRANSACTIONS, ví dụ:

~~~text
------------
TRANSACTIONS
------------
Trx id counter 0 290328385
Purge done for trx's n:o < 0 290315608 undo n:o < 0 17
History list length 20
~~~

Các dòng có thể thay đổi theo phiên bản. Chú ý:

- **Trx id counter**: mốc transaction ID hiện tại.
- **Purge done for trx's n:o**: mốc transaction mà purge đã xử lý đến theo thông tin nội bộ được hiển thị.
- **History list length**: độ dài history list đang được báo cáo.

Nếu history list tăng trong nhiều lần lấy mẫu, hãy tìm transaction cũ và xem purge có bị ghim ở cùng một mốc hay không. Một ảnh chụp duy nhất không đủ để kết luận purge đang bị nghẽn.

### 4.3. Theo dõi bằng INNODB_METRICS

Có thể truy vấn metric tương ứng trong INFORMATION_SCHEMA.INNODB_METRICS:

~~~sql
SELECT
    NAME,
    COUNT,
    TYPE,
    STATUS,
    COMMENT
FROM INFORMATION_SCHEMA.INNODB_METRICS
WHERE NAME = 'trx_rseg_history_len';
~~~

Metric **trx_rseg_history_len** phản ánh độ dài history list. Kiểm tra cột TYPE và STATUS để hiểu cách metric được thu thập trên phiên bản đang chạy. Nếu metric bị tắt trong bảng metrics, có thể bật riêng counter này:

~~~sql
SET GLOBAL innodb_monitor_enable = trx_rseg_history_len;
~~~

Không cần bật toàn bộ InnoDB metrics chỉ để quan sát history list. Các counter có thể được bật/tắt/reset và trạng thái của chúng không nhất thiết được giữ sau restart; hãy kiểm tra lại sau nâng cấp hoặc khởi động lại.

### 4.4. Đánh giá xu hướng thay vì một ngưỡng cố định

Lấy mẫu định kỳ, ví dụ mỗi 30–60 giây, và ghi lại:

| Thời điểm | History list length | Transaction cũ nhất | Ghi chú tải |
|---|---:|---|---|
| T0 | 12.000 | 2 phút | Tải ghi bình thường |
| T1 | 18.000 | 15 phút | Job báo cáo bắt đầu |
| T2 | 31.000 | 16 phút | DML vẫn tăng |
| T3 | 32.000 | 16 phút | History gần như không giảm |
| T4 | 4.000 | Không còn transaction cũ | Purge bắt kịp |

Các số trên chỉ minh họa cách đọc xu hướng, không phải ngưỡng cảnh báo cho mọi hệ thống.

Một history list vài nghìn có thể là bình thường trong workload cụ thể; một giá trị thấp nhưng tăng liên tục cũng có thể báo hiệu xu hướng xấu. Hãy xác định baseline theo phiên bản MySQL, tốc độ DML, loại dữ liệu, dung lượng undo và SLA của ứng dụng.

Cần quan sát ít nhất ba yếu tố:

- **Mức hiện tại**: history list đang lớn đến đâu so với baseline.
- **Tốc độ tăng/giảm**: chỉ số có tiếp tục tăng hay đang được purge làm giảm.
- **Thời gian tồn tại**: backlog kéo dài bao lâu và có trùng với transaction cũ hay không.

Không đặt cảnh báo chỉ dựa trên một con số chung rồi tự động kill transaction khi chạm ngưỡng.

## 5. Tìm transaction kéo dài

### 5.1. Liệt kê transaction InnoDB đang hoạt động

INFORMATION_SCHEMA.INNODB_TRX cung cấp thông tin về transaction hiện đang chạy trong InnoDB, gồm thời điểm bắt đầu, trạng thái, isolation level, truy vấn hiện tại và số hàng đã khóa/thay đổi.

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
    trx_isolation_level,
    trx_is_read_only,
    trx_autocommit_non_locking,
    trx_rows_locked,
    trx_rows_modified,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Cách đọc các cột:

- **trx_started**: thời điểm transaction bắt đầu.
- **age_seconds**: tuổi transaction tính đến thời điểm truy vấn.
- **trx_state**: RUNNING, LOCK WAIT, ROLLING BACK hoặc COMMITTING.
- **trx_isolation_level**: mức cô lập của transaction.
- **trx_is_read_only**: transaction được đánh dấu read-only hay không.
- **trx_autocommit_non_locking**: thông tin về transaction autocommit chỉ đọc không khóa.
- **trx_rows_locked**: số hàng ước lượng đang bị khóa.
- **trx_rows_modified**: số hàng đã sửa/thêm.
- **trx_mysql_thread_id**: connection ID ở phía MySQL.
- **trx_query**: câu lệnh đang chạy; có thể NULL nếu hiện không có câu lệnh đang thực thi.

Không chỉ lọc transaction có trx_rows_modified lớn. Một transaction read-only có thể có trx_rows_modified bằng 0 nhưng vẫn giữ read view cũ.

Một số transaction read-only và nonlocking không được cấp transaction ID InnoDB theo cách giống transaction ghi. Vì vậy, không lọc bỏ các dòng chỉ vì trx_id không có giá trị thông thường. Hãy đọc các cột tuổi, isolation level, trạng thái read-only và connection ID.

Cần quyền PROCESS để truy vấn INFORMATION_SCHEMA.INNODB_TRX. Nếu tài khoản giám sát không có quyền, phối hợp với tài khoản vận hành có quyền phù hợp.

### 5.2. Ghép transaction với connection

Để biết user, host và trạng thái connection, ghép INNODB_TRX với Performance Schema threads:

~~~sql
SELECT
    it.trx_mysql_thread_id AS connection_id,
    th.processlist_user,
    th.processlist_host,
    th.processlist_db,
    th.processlist_command,
    th.processlist_time,
    it.trx_started,
    TIMESTAMPDIFF(SECOND, it.trx_started, NOW()) AS trx_age_seconds,
    it.trx_state,
    it.trx_isolation_level,
    it.trx_is_read_only,
    it.trx_autocommit_non_locking,
    it.trx_rows_locked,
    it.trx_rows_modified,
    it.trx_query
FROM information_schema.innodb_trx AS it
LEFT JOIN performance_schema.threads AS th
    ON th.processlist_id = it.trx_mysql_thread_id
ORDER BY it.trx_started;
~~~

Đặc biệt chú ý tổ hợp:

- **processlist_command = Sleep**
- **trx_age_seconds** lớn
- **trx_query IS NULL**
- **trx_isolation_level = REPEATABLE READ**
- **trx_rows_modified = 0** hoặc rất thấp

Đây là ứng viên transaction đã chạy SELECT, giữ snapshot rồi để connection nhàn rỗi. Tuy nhiên, hãy kiểm tra ứng dụng và transaction thực tế trước khi kết luận. Sleep chỉ mô tả trạng thái hiện tại của connection; nó không tự chứng minh transaction đang ghim purge.

### 5.3. Kiểm tra PROCESSLIST và lịch sử câu lệnh

Có thể xem nhanh các connection:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Hoặc dùng Performance Schema:

~~~sql
SELECT
    PROCESSLIST_ID,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE,
    PROCESSLIST_INFO
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
ORDER BY PROCESSLIST_TIME DESC;
~~~

PROCESSLIST_INFO thường chỉ cho biết câu lệnh hiện tại. Nếu connection đang Sleep, thông tin này có thể NULL dù transaction vẫn mở. Có thể xem events_statements_history hoặc log ứng dụng nếu Performance Schema đã cấu hình lưu lịch sử phù hợp, nhưng history trong bộ nhớ có giới hạn và có thể không còn câu lệnh cũ.

Khi đối chiếu INNODB_TRX và Performance Schema threads, hãy nhớ đây là các view của trạng thái nội bộ thay đổi liên tục. Hai nguồn có thể không hoàn toàn đồng bộ tại đúng một thời điểm; một transaction hoặc connection có thể kết thúc giữa lúc đọc các bảng.

### 5.4. Phân biệt transaction giữ snapshot với lock blocker

Một transaction read-only có thể ghim history list mà không giữ row lock. Vì vậy, truy vấn lock wait không nhất thiết chỉ ra transaction đang ghim purge.

Ngược lại, transaction có nhiều row lock và đang ở LOCK WAIT có thể gây nghẽn ứng dụng, nhưng chưa chắc là transaction giữ read view cũ nhất.

Để kiểm tra lock wait, có thể đọc Performance Schema data_locks và data_lock_waits hoặc view sys.innodb_lock_waits nếu có. Phân tích lock là nhánh điều tra riêng; không dùng danh sách blocker để thay thế việc đọc tuổi transaction và history list.

## 6. Phân loại nguyên nhân history list tăng

### 6.1. Có transaction cũ giữ read view

Dấu hiệu thường gặp:

- History list tăng trong khi một transaction cũ vẫn mở.
- Transaction có isolation level REPEATABLE READ và có thể đã chạy consistent read.
- Connection có thể đang Sleep và trx_query là NULL.
- Khi transaction kết thúc, history list bắt đầu giảm sau một khoảng thời gian purge xử lý.
- Tăng innodb_purge_threads không làm purge vượt qua read view đang ghim.

Cách xử lý là xác định chủ sở hữu transaction, kiểm tra nghiệp vụ, rồi kết thúc transaction theo cách phù hợp.

### 6.2. Không có read view cũ nhưng DML tạo history quá nhanh

Dấu hiệu thường gặp:

- Không thấy transaction cũ rõ ràng trong INNODB_TRX.
- History list vẫn tăng trong giờ cao điểm có nhiều UPDATE/DELETE.
- CPU, I/O hoặc purge thread chịu tải lớn.
- Khi giảm tải DML, history list bắt đầu giảm.
- DML tập trung trên một bảng nóng có thể giới hạn khả năng purge song song.

Kiểm tra tốc độ DML, kích thước transaction, số index phải cập nhật, latency storage và khả năng CPU. Không mặc định rằng purge bị lỗi chỉ vì history list cao.

### 6.3. Transaction ghi lớn và rollback segment phình to

Transaction ghi lớn có thể tạo rất nhiều undo trước khi commit. Khi transaction còn mở, undo cần thiết để rollback chưa thể được giải phóng. Nếu transaction bị rollback, InnoDB phải thực hiện công việc đảo ngược thay đổi; quá trình này có thể kéo dài tùy số hàng và lượng dữ liệu đã sửa.

Cần xem:

- trx_rows_modified và trx_rows_locked.
- trx_state có phải ROLLING BACK hay không.
- Thời gian transaction tồn tại.
- Dung lượng undo tablespace.
- CPU/I/O và tốc độ hoàn tất rollback.

Không nên kill một transaction ghi rất lớn rồi kỳ vọng tài nguyên được giải phóng ngay lập tức. Rollback có thể tiếp tục chạy và tạo thêm tải trong một khoảng thời gian.

### 6.4. Tải DML tập trung trên một bảng

Purge trên cùng một bảng nóng có thể không mở rộng tuyến tính theo số purge thread. Các index, record và page nóng có thể làm tăng contention. Nếu một bảng có nhiều UPDATE/DELETE, kiểm tra thiết kế index, phân bố khóa và cách batch dữ liệu.

Giảm lượng DML không cần thiết, dùng điều kiện lọc có index và chia batch có thể hiệu quả hơn việc tăng số thread purge một cách máy móc.

## 7. Tác động của purge lag đến hệ thống

History list tăng kéo dài có thể gây ra nhiều hệ quả:

- Undo tablespace tăng dung lượng vì các undo log chưa thể giải phóng.
- Nhiều phiên bản cũ phải được giữ lại để phục vụ consistent read.
- Secondary index record đã delete-mark tồn tại lâu hơn trước khi purge dọn.
- Truy vấn có thể phải đi qua nhiều phiên bản cũ hơn khi dựng lại hàng cho snapshot.
- Buffer pool và I/O phải phục vụ thêm dữ liệu cũ hoặc index page có record chưa được dọn.
- Bảng có thể giữ nhiều record đã đánh dấu xóa, làm tăng dung lượng và chi phí truy cập.
- Khi backlog kéo dài, hiệu năng DML và truy vấn có thể giảm, đặc biệt nếu purge cạnh tranh tài nguyên với workload chính.

Tuy vậy, history list cao không tự động chứng minh một câu SQL cụ thể đang chậm vì MVCC. Hãy so sánh query latency, rows examined, buffer pool, I/O, transaction wait và lịch sử DML trong cùng cửa sổ.

Cũng cần phân biệt dung lượng logic và dung lượng file:

- Purge giải phóng undo log page và dọn record cũ để các page có thể được tái sử dụng.
- File tablespace dữ liệu không nhất thiết giảm kích thước trên filesystem sau khi purge.
- Undo tablespace có cơ chế truncate riêng; việc HLL giảm không có nghĩa file undo đã lập tức thu nhỏ.

## 8. Quy trình điều tra khi history list tăng

### Bước 1: Xác nhận chỉ số và xu hướng

Lấy nhiều snapshot của:

~~~sql
SHOW ENGINE INNODB STATUS\G

SELECT NAME, COUNT, TYPE, STATUS, COMMENT
FROM information_schema.innodb_metrics
WHERE NAME = 'trx_rseg_history_len';
~~~

Ghi timestamp, HLL, purge watermark và trạng thái metric. Xác định chỉ số đang tăng, đứng yên hay giảm.

### Bước 2: Tìm transaction lâu nhất

~~~sql
SELECT
    trx_mysql_thread_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
    trx_state,
    trx_isolation_level,
    trx_is_read_only,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Tìm transaction cũ, kể cả read-only và transaction không có câu lệnh đang chạy.

### Bước 3: Xác định chủ sở hữu

Ghép connection ID với Performance Schema threads, host, user, database và command. Đối chiếu với application log, request ID, job scheduler, backup process và connection pool.

### Bước 4: Phân loại transaction

Hỏi các câu sau:

- Đây là transaction chỉ đọc hay có ghi?
- Có thể đã tạo consistent read view chưa?
- Có phải REPEATABLE READ hoặc START TRANSACTION WITH CONSISTENT SNAPSHOT không?
- Connection đang chạy query, Sleep hay chờ lock?
- Có đang backup/reporting hoặc stream dữ liệu không?
- Transaction có nhiều hàng sửa và có thể cần rollback lâu không?

### Bước 5: Đánh giá năng lực purge

Nếu không có read view cũ rõ ràng, kiểm tra CPU, storage latency, workload DML, số bảng nóng và cấu hình purge. So sánh thời điểm history list tăng với throughput UPDATE/DELETE và thời điểm tải giảm.

### Bước 6: Chọn hành động ít rủi ro nhất

- Nếu ứng dụng còn kiểm soát được session, yêu cầu session kết thúc transaction bằng COMMIT hoặc ROLLBACK phù hợp với nghiệp vụ.
- Nếu transaction không còn hợp lệ, phối hợp với chủ sở hữu ứng dụng để hủy công việc hoặc đóng connection.
- Nếu purge không theo kịp tải, giảm/batch DML, kiểm tra index và tài nguyên trước khi điều chỉnh purge.
- Theo dõi HLL sau hành động để xác nhận backlog thực sự bắt đầu giảm.

### Bước 7: Xác nhận phục hồi

Tiếp tục lấy mẫu HLL, transaction cũ, undo tablespace size, CPU/I/O và latency ứng dụng. Chỉ coi sự cố đã ổn định khi HLL có xu hướng giảm hoặc trở về baseline, không còn transaction cũ bất thường và workload không phát sinh lại backlog.

## 9. Xử lý transaction kéo dài an toàn

### 9.1. Ưu tiên kết thúc transaction từ ứng dụng

Nếu session vẫn do ứng dụng kiểm soát, cách tốt nhất là để chính session thực hiện COMMIT hoặc ROLLBACK theo logic nghiệp vụ. Việc này giúp ứng dụng nhận được trạng thái kết thúc rõ ràng và tránh để connection pool tái sử dụng session với transaction cũ.

Nếu transaction chỉ đọc và không có thay đổi cần commit, COMMIT thường là cách kết thúc read view. Nếu transaction đã ghi dữ liệu nhưng chưa hoàn tất nghiệp vụ, cần xác định chính xác nên commit hay rollback.

### 9.2. KILL QUERY không tương đương kết thúc transaction

KILL QUERY hủy câu lệnh hiện đang chạy trên connection. Nếu câu lệnh bị hủy nhưng connection vẫn còn transaction mở, read view và các tài nguyên transaction có thể vẫn tồn tại.

Khi mục tiêu là kết thúc một connection bị bỏ quên, KILL CONNECTION sẽ ngắt session và InnoDB xử lý rollback cho transaction chưa commit. Nhưng rollback transaction lớn có thể mất nhiều thời gian; trạng thái transaction có thể chuyển sang ROLLING BACK.

Ví dụ thao tác sau chỉ dùng khi đã xác định đúng connection và được người vận hành có thẩm quyền phê duyệt:

~~~sql
-- Kiểm tra lại connection ID và chủ sở hữu trước khi thực hiện.
KILL CONNECTION 12345;
~~~

Không sao chép ID từ một ảnh chụp cũ rồi kill sau nhiều phút. Connection ID có thể không còn thuộc session ban đầu. Hãy truy vấn lại INNODB_TRX và threads ngay trước khi thao tác.

### 9.3. Tránh kill hàng loạt theo tuổi transaction

Không nên tự động kill mọi transaction vượt quá một số phút cố định. Một số transaction dài có thể là backup, báo cáo hoặc tác vụ nghiệp vụ đã được thiết kế để chạy lâu. Kill sai có thể làm rollback rất lớn, làm gián đoạn công việc hoặc tạo thêm tải.

Chính sách tốt hơn là:

- Xác định owner và loại workload.
- Đặt timeout transaction phù hợp với SLA.
- Ghi log khi transaction mở và khi kết thúc.
- Có cơ chế cleanup khi ứng dụng lỗi.
- Cảnh báo theo tuổi transaction và HLL trend.
- Chỉ tự động hủy những loại công việc đã có quy tắc an toàn rõ ràng.

## 10. Giảm khả năng phát sinh history quá lớn từ ứng dụng

### 10.1. Giữ transaction ngắn

Mở transaction ngay trước thao tác cần tính nhất quán và kết thúc ngay sau khi hoàn tất. Không giữ transaction trong lúc chờ người dùng, gọi HTTP, tải file hoặc xử lý CPU lâu.

Mẫu xử lý:

~~~sql
START TRANSACTION;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 1001
  AND quantity > 0;

-- Thực hiện các thao tác DB cần nằm trong cùng giao dịch.

COMMIT;
~~~

Trong ứng dụng, cần bảo đảm mọi nhánh thành công đều commit và mọi nhánh lỗi đều rollback hoặc đóng connection theo cơ chế an toàn.

### 10.2. Batch DELETE và UPDATE

Một transaction xóa hàng triệu bản ghi có thể tạo lượng undo lớn và giữ tài nguyên lâu. Có thể chia công việc thành batch nhỏ, commit sau mỗi batch:

~~~sql
DELETE FROM audit_log
WHERE created_at < '2024-01-01'
ORDER BY created_at
LIMIT 5000;
~~~

Nếu autocommit đang bật, mỗi câu lệnh là một transaction riêng. Nếu đang ở trong transaction tường minh, hãy COMMIT sau mỗi batch theo thiết kế job.

Để batch ổn định, nên:

- Có index phù hợp cho điều kiện lọc và thứ tự xử lý.
- Dùng khóa định danh hoặc mốc thời gian để tiếp tục từ batch trước.
- Giới hạn số hàng mỗi batch theo latency và undo thực tế.
- Có khoảng nghỉ hoặc điều tiết tốc độ khi tải production tăng.
- Theo dõi HLL, replica lag, lock wait và I/O giữa các batch.

Không dùng LIMIT tùy tiện khi chưa có điều kiện lọc xác định; nếu không có index, mỗi batch vẫn có thể quét nhiều dữ liệu và làm tăng tải.

### 10.3. Thiết kế timeout và connection pool

Ứng dụng nên có:

- Transaction timeout theo loại nghiệp vụ.
- Query timeout và request deadline rõ ràng.
- Kiểm tra transaction trước khi trả connection về pool.
- Rollback khi exception hoặc request bị hủy.
- Không chia sẻ cùng một connection giữa các luồng xử lý đồng thời.
- Log connection ID, thời điểm bắt đầu transaction và correlation/request ID.
- Cảnh báo khi connection Sleep vẫn có transaction mở quá lâu.

Timeout ở tầng ứng dụng không luôn tự động kết thúc transaction phía MySQL. Cần xác minh driver và framework có gửi cancel/rollback hay chỉ ngừng chờ ở phía client.

### 10.4. Backup và báo cáo dài

mysqldump với --single-transaction tạo consistent snapshot để dump dữ liệu nhất quán mà không khóa toàn bộ bảng InnoDB trong suốt quá trình. Nếu dump kéo dài trong khi ứng dụng tiếp tục ghi nhiều, read view của backup có thể giữ undo cũ và làm HLL tăng.

Khi backup dài:

- Chọn thời điểm tải ghi thấp nếu phù hợp.
- Theo dõi transaction backup và HLL trong suốt quá trình.
- Ước lượng thời gian dump dựa trên dung lượng và tốc độ đọc thực tế.
- Cân nhắc chạy backup trên replica phù hợp với yêu cầu nhất quán và topology.
- Đảm bảo tiến trình backup kết thúc transaction khi hoàn tất hoặc bị hủy.
- Không để job retry tạo nhiều snapshot cùng lúc.

Chạy backup trên replica có thể giảm tác động đến primary, nhưng không loại bỏ chi phí purge ở replica đó. Cần theo dõi từng instance riêng.

## 11. Điều chỉnh cấu hình purge

Chỉ điều chỉnh sau khi đã xác định transaction cũ không còn là nguyên nhân chính và đã có số liệu cho thấy purge thực sự thiếu năng lực xử lý.

### 11.1. Kiểm tra cấu hình hiện tại

~~~sql
SELECT
    @@GLOBAL.innodb_purge_threads AS innodb_purge_threads,
    @@GLOBAL.innodb_max_purge_lag AS innodb_max_purge_lag,
    @@GLOBAL.innodb_max_purge_lag_delay AS innodb_max_purge_lag_delay,
    @@GLOBAL.innodb_purge_batch_size AS innodb_purge_batch_size,
    @@GLOBAL.innodb_undo_log_truncate AS innodb_undo_log_truncate,
    @@GLOBAL.innodb_max_undo_log_size AS innodb_max_undo_log_size;
~~~

Kiểm tra biến có tồn tại và có cùng phạm vi/ý nghĩa trên phiên bản MySQL đang vận hành. Không áp dụng nguyên xi cấu hình giữa các phiên bản hoặc managed database có giới hạn quyền quản trị.

### 11.2. innodb_purge_threads

Biến này xác định số purge thread tối đa được phép sử dụng. Tăng giá trị có thể cải thiện khả năng xử lý khi DML phân tán trên nhiều bảng và purge có thể song song hóa.

Cần thận trọng khi:

- DML tập trung trên một bảng nóng.
- Purge thread cạnh tranh CPU/I/O với thread ứng dụng.
- Storage đã bão hòa.
- History list bị ghim bởi một read view cũ.

Thay đổi số thread không giải phóng được undo mà một snapshot còn cần. Sau khi điều chỉnh, so sánh tốc độ giảm HLL, CPU, I/O và latency của workload.

### 11.3. innodb_max_purge_lag và innodb_max_purge_lag_delay

**innodb_max_purge_lag** đặt ngưỡng purge lag mong muốn. Khi vượt ngưỡng, InnoDB áp dụng độ trễ lên các thao tác INSERT, UPDATE và DELETE để tạo thời gian cho purge bắt kịp. Giá trị mặc định bằng 0 nghĩa là không đặt giới hạn purge lag và không áp dụng độ trễ theo cơ chế này.

**innodb_max_purge_lag_delay** đặt giới hạn tối đa cho thời gian trì hoãn, đơn vị microsecond. Nó giới hạn mức delay được tính khi ngưỡng purge lag bị vượt.

Đây là cơ chế điều tiết DML khi backlog đã lớn. Nó không phải công tắc để purge xóa nhanh một read view đang được transaction giữ. Ngưỡng cần được chọn theo kích thước transaction, đặc điểm dữ liệu, khả năng chịu độ trễ và SLA. Một giá trị phù hợp cho workload nhỏ có thể không phù hợp với workload ghi lớn.

### 11.4. innodb_purge_batch_size

Biến này điều khiển số undo log page được purge phân tích/xử lý trong một batch. Đây là tham số tuning chuyên sâu; đa số hệ thống không cần thay đổi giá trị mặc định.

Chỉ thử nghiệm khi đã có benchmark tái lập, theo dõi CPU/I/O và biết rõ giới hạn của purge. Không thay đổi đồng thời nhiều biến purge vì sẽ khó xác định biến nào tạo ra khác biệt.

## 12. Undo tablespace và việc thu hồi dung lượng

### 12.1. Purge và truncate là hai việc khác nhau

Purge xử lý undo log không còn cần thiết và giải phóng các rollback segment/page. Truncate undo tablespace là bước thu nhỏ file undo tablespace để trả dung lượng cho filesystem.

Một undo tablespace có thể còn file lớn sau khi history list đã giảm vì dung lượng được tái sử dụng bên trong tablespace. Vì vậy:

- HLL giảm không đồng nghĩa file undo lập tức nhỏ lại.
- File undo lớn không chứng minh vẫn còn transaction giữ snapshot.
- Cần xem cả trạng thái rollback segment và cơ chế truncate.

### 12.2. Tự động truncate undo tablespace

Trong MySQL 8.4, cơ chế tự động truncate được điều khiển bởi:

- **innodb_undo_log_truncate**: bật/tắt tự động truncate undo tablespace.
- **innodb_max_undo_log_size**: ngưỡng kích thước để undo tablespace được đánh dấu xử lý truncate.
- **innodb_purge_rseg_truncate_frequency**: tần suất purge kiểm tra undo tablespace có thể truncate.

Để tự động truncate, cần ít nhất hai undo tablespace đang hoạt động. Quy trình sẽ đưa rollback segment của một tablespace vào trạng thái không nhận transaction mới, chờ transaction đang dùng hoàn tất, để purge giải phóng undo log, truncate file rồi kích hoạt lại rollback segment.

Việc truncate có thể bị trì hoãn nếu còn transaction sử dụng rollback segment trong tablespace. Không xóa hoặc di chuyển file undo thủ công khi MySQL đang chạy.

Có thể xem file undo qua INFORMATION_SCHEMA.FILES:

~~~sql
SELECT
    TABLESPACE_NAME,
    FILE_NAME
FROM information_schema.files
WHERE FILE_TYPE = 'UNDO LOG';
~~~

Theo dõi trạng thái tablespace:

~~~sql
SELECT
    NAME,
    STATE
FROM information_schema.innodb_tablespaces
WHERE NAME LIKE 'innodb_undo_%';
~~~

Tên và trạng thái cụ thể phụ thuộc phiên bản và cấu hình. Tham khảo tài liệu phiên bản đang chạy trước khi dùng thao tác ALTER UNDO TABLESPACE hoặc DROP UNDO TABLESPACE.

### 12.3. Tránh nhầm undo tablespace với file dữ liệu bảng

Undo tablespace chứa undo log. File tablespace của bảng chứa clustered index, secondary index và dữ liệu của bảng. Purge có thể làm các page dữ liệu được tái sử dụng nhưng không nhất thiết thu nhỏ file .ibd trên filesystem.

Nếu cần thu hồi dung lượng vật lý của file bảng, đó là bài toán tái tổ chức/rebuild tablespace riêng, cần đánh giá dung lượng tạm, thời gian khóa, I/O và tác động production. Không chạy OPTIMIZE TABLE chỉ vì history list length đang cao.

## 13. Ví dụ thực hành hai session

### 13.1. Chuẩn bị bảng thử nghiệm

Chỉ thực hiện trên môi trường lab:

~~~sql
CREATE TABLE purge_lab (
    id BIGINT NOT NULL PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    updated_at DATETIME NOT NULL,
    KEY idx_status_updated (status, updated_at)
) ENGINE=InnoDB;

INSERT INTO purge_lab (id, status, updated_at)
VALUES
    (1, 'new', NOW()),
    (2, 'new', NOW()),
    (3, 'new', NOW());
~~~

### 13.2. Session A giữ snapshot

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;

START TRANSACTION;

SELECT id, status
FROM purge_lab
ORDER BY id;

-- Giữ transaction mở trong lúc chuyển sang Session B.
~~~

Lần SELECT đầu tiên tạo read view cho transaction A.

### 13.3. Session B cập nhật và commit

~~~sql
START TRANSACTION;

UPDATE purge_lab
SET status = 'processed',
    updated_at = NOW()
WHERE id IN (1, 2, 3);

COMMIT;
~~~

Session B đã commit nhưng Session A vẫn có thể nhìn thấy phiên bản cũ theo snapshot. Undo do UPDATE tạo ra vẫn có thể cần cho consistent read của Session A.

Có thể lặp lại nhiều lần cập nhật trong Session B và quan sát HLL ở một môi trường lab có tải phù hợp. Không tạo tải DML lớn trên production chỉ để kiểm tra ví dụ này.

### 13.4. Giải phóng read view

Quay lại Session A:

~~~sql
COMMIT;
~~~

Khi transaction A kết thúc, read view được giải phóng. Purge có thể xử lý phần history không còn cần thiết. Theo dõi history list qua nhiều snapshot để quan sát xu hướng giảm; không kỳ vọng mọi undo page biến mất ngay trong cùng một mili giây.

### 13.5. Quan sát transaction đang mở

Trong một session quản trị khác:

~~~sql
SELECT
    trx_mysql_thread_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
    trx_isolation_level,
    trx_is_read_only,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Tìm connection của Session A, xác nhận tuổi transaction và isolation level. Có thể kết thúc bằng COMMIT trong Session A và quan sát HLL sau đó.

## 14. Kịch bản vận hành và cách diễn giải

### Kịch bản A: HLL tăng, có một transaction REPEATABLE READ đang Sleep

**Quan sát**

- HLL tăng liên tục.
- INNODB_TRX có transaction bắt đầu từ lâu.
- Connection tương ứng có PROCESSLIST_COMMAND là Sleep.
- trx_query là NULL, trx_rows_modified bằng 0.
- Ứng dụng có thể đã trả connection về pool nhưng chưa commit.

**Phân tích**

Transaction có thể đang giữ read view từ một SELECT trước đó. Không có câu lệnh đang chạy không có nghĩa snapshot đã được giải phóng.

**Hành động**

Xác định request/job sở hữu connection, yêu cầu ứng dụng kết thúc transaction, sau đó theo dõi HLL và purge. Nếu phải KILL CONNECTION, xác minh connection ID và chấp nhận rằng transaction ghi có thể cần rollback.

### Kịch bản B: HLL tăng cùng job DELETE lớn

**Quan sát**

- HLL tăng trong thời gian job dọn dữ liệu.
- Transaction có trx_rows_modified rất lớn.
- Dung lượng undo tablespace tăng.
- CPU và I/O tăng theo batch.

**Phân tích**

Job tạo undo nhanh, transaction lớn giữ undo cho đến khi kết thúc. Sau commit, purge vẫn cần xử lý history, và một read view cũ khác có thể tiếp tục giữ phần undo này.

**Hành động**

Chia DELETE thành batch, commit giữa các batch, dùng index phù hợp và điều tiết tốc độ. Theo dõi HLL giữa các batch để tìm kích thước batch có thể duy trì.

### Kịch bản C: Không thấy transaction cũ nhưng HLL vẫn tăng

**Quan sát**

- INNODB_TRX không có transaction tuổi lớn rõ ràng.
- HLL tăng trong giờ cao điểm.
- DML cao và tập trung trên một số bảng.
- Storage latency hoặc CPU purge tăng.

**Phân tích**

Purge có thể đang thiếu thông lượng xử lý so với tốc độ tạo history. Cần xác nhận bằng nhiều mẫu và metric, không chỉ một snapshot transaction.

**Hành động**

Giảm DML không cần thiết, chia batch, kiểm tra index và storage. Sau đó thử điều chỉnh innodb_purge_threads trong môi trường có thể kiểm soát, đo cả HLL và latency ứng dụng.

### Kịch bản D: HLL giảm nhưng undo file vẫn lớn

**Quan sát**

- History list trở về gần baseline.
- Không còn transaction cũ bất thường.
- File undo tablespace vẫn chiếm dung lượng đáng kể.

**Phân tích**

Purge đã xử lý history, nhưng việc thu hồi file undo về filesystem là quy trình truncate riêng. Tablespace có thể giữ dung lượng để tái sử dụng.

**Hành động**

Kiểm tra innodb_undo_log_truncate, ngưỡng innodb_max_undo_log_size, số undo tablespace hoạt động và trạng thái rollback segment. Đợi cơ chế truncate hoàn tất theo điều kiện của phiên bản; không xóa file thủ công.

## 15. Checklist giám sát production

- [ ] Thu thập history list length định kỳ và lưu timestamp.
- [ ] Theo dõi tốc độ tăng/giảm HLL so với baseline của workload.
- [ ] Cảnh báo transaction có tuổi bất thường theo loại ứng dụng.
- [ ] Theo dõi transaction Sleep nhưng vẫn có transaction InnoDB mở.
- [ ] Ghi nhận isolation level, trx_rows_modified và trx_rows_locked.
- [ ] Theo dõi DML throughput và job DELETE/UPDATE hàng loạt.
- [ ] Theo dõi CPU, I/O latency và dung lượng undo tablespace.
- [ ] Phân biệt read view cũ với purge thiếu thông lượng.
- [ ] Có quy trình xác định owner trước khi kết thúc connection.
- [ ] Không tự động KILL theo một ngưỡng tuổi duy nhất.
- [ ] Kiểm tra rollback hoàn tất sau khi hủy transaction ghi.
- [ ] Đánh giá riêng việc purge và truncate undo tablespace.
- [ ] Kiểm tra cấu hình purge sau khi nâng cấp MySQL.
- [ ] Diễn tập runbook trong môi trường lab hoặc staging.

## 16. Bài thực hành

### Bài 1: Đọc history list

Chạy SHOW ENGINE INNODB STATUS nhiều lần trong một cửa sổ tải bình thường. Ghi HLL, purge watermark và timestamp. Xác định mức nền và độ dao động thường gặp.

**Kết quả cần có:** bảng thời gian và nhận xét HLL tăng, giảm hoặc ổn định.

### Bài 2: Tìm transaction lâu nhất

Truy vấn INFORMATION_SCHEMA.INNODB_TRX và ghép với PERFORMANCE_SCHEMA.THREADS. Tìm transaction cũ, transaction Sleep và transaction read-only.

**Kết quả cần có:** connection ID, user, host, tuổi transaction, isolation level, trạng thái và chủ sở hữu nghiệp vụ.

### Bài 3: Quan sát read view giữ undo

Dùng hai session trong bảng purge_lab. Session A giữ REPEATABLE READ snapshot; Session B cập nhật và commit. Quan sát kết quả SELECT ở A trước và sau khi kết thúc transaction.

**Kết quả cần có:** giải thích được vì sao transaction đọc có thể giữ phiên bản cũ do transaction khác tạo.

### Bài 4: Phân biệt purge lag với undo file size

Theo dõi HLL và dung lượng undo tablespace trong một môi trường lab. Quan sát sau khi transaction dài kết thúc.

**Kết quả cần có:** giải thích được vì sao HLL có thể giảm trước khi file undo thu nhỏ.

### Bài 5: Thiết kế batch cleanup

Thiết kế một job DELETE dữ liệu cũ theo batch có index, giới hạn số hàng và commit sau mỗi batch. Ghi rõ điều kiện dừng khi latency hoặc HLL tăng bất thường.

**Kết quả cần có:** kế hoạch batch, cách resume, tiêu chí điều tiết và cách xác nhận purge bắt kịp.

## 17. Tiêu chí hoàn thành

Bạn hoàn thành bài học khi có thể giải thích được MVCC, undo log, read view và purge; phân biệt insert undo với update undo; đọc history list length đúng bản chất; tìm transaction cũ kể cả connection Sleep và transaction chỉ đọc; phân biệt transaction ghim read view với purge thiếu thông lượng; và xây dựng được cách xử lý an toàn dựa trên bằng chứng.

Khi vận hành MySQL, mục tiêu không phải ép history list length về 0 bằng mọi giá. Mục tiêu là duy trì purge theo kịp workload, tránh transaction giữ snapshot lâu ngoài dự kiến, giữ undo trong giới hạn có thể quản lý và bảo đảm ứng dụng không phải chịu độ trễ bất thường.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — InnoDB Multi-Versioning](https://dev.mysql.com/doc/refman/8.4/en/innodb-multi-versioning.html)
- [MySQL 8.4 Reference Manual — Purge Configuration](https://dev.mysql.com/doc/refman/8.4/en/innodb-purge-configuration.html)
- [MySQL 8.4 Reference Manual — Consistent Nonlocking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html)
- [MySQL 8.4 Reference Manual — Transaction Isolation Levels](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html)
- [MySQL 8.4 Reference Manual — INFORMATION_SCHEMA INNODB_TRX](https://dev.mysql.com/doc/refman/8.4/en/information-schema-innodb-trx-table.html)
- [MySQL 8.4 Reference Manual — InnoDB Transaction and Locking Information](https://dev.mysql.com/doc/refman/8.4/en/innodb-information-schema-transactions.html)
- [MySQL 8.4 Reference Manual — INNODB_METRICS](https://dev.mysql.com/doc/refman/8.4/en/information-schema-innodb-metrics-table.html)
- [MySQL 8.4 Reference Manual — Undo Tablespaces](https://dev.mysql.com/doc/refman/8.4/en/innodb-undo-tablespaces.html)

