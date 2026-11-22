# GTID sai lệch, server UUID trùng và clone môi trường không đúng

Bài học này thuộc module **DATABASE_MYSQL**. Khi dựng replica, phục hồi từ backup, sao chép data directory hoặc tạo môi trường staging từ production, MySQL cần phân biệt rõ từng máy chủ và lịch sử transaction của chúng. Các lỗi thường gặp gồm GTID giữa source và replica không khớp, replica có transaction lạ, binary log cần thiết đã bị purge, hai máy chủ dùng cùng server UUID hoặc một bản clone vô tình tham gia lại topology production.

Những tình huống này liên quan trực tiếp tới tính nhất quán dữ liệu. Không nên sửa bằng cách xóa file, đặt lại GTID hoặc reset binary log theo cảm tính. Trước tiên cần xác định máy chủ nào là nguồn dữ liệu có thẩm quyền, so sánh tập GTID, kiểm tra danh tính từng node và xác định mục đích của bản clone: dựng replica mới hay tạo môi trường độc lập.

## 1. GTID và danh tính máy chủ trong MySQL

GTID (Global Transaction Identifier) định danh một transaction đã được ghi vào binary log. Một GTID có dạng:

~~~text
source_uuid:transaction_number
~~~

Ví dụ:

~~~text
24bc7850-2c16-11ef-a1c4-0242ac120002:125
~~~

Phần UUID xác định nguồn đã tạo transaction; phần số là số thứ tự transaction trong chuỗi GTID của nguồn đó. GTID giúp MySQL xác định transaction nào đã được thực thi, transaction nào còn cần truyền và tránh áp dụng cùng một GTID lần nữa trong replication.

Một máy chủ MySQL có hai định danh cần phân biệt:

- **server_id:** số nguyên cấu hình trong file cấu hình hoặc lúc khởi động. Nó phải duy nhất trong topology replication.
- **server_uuid:** UUID do MySQL tạo và lưu trong file auto.cnf của data directory. Nó được dùng làm thành phần nguồn của GTID và phải duy nhất giữa các instance tham gia topology.

server_id và server_uuid không thay thế cho nhau. Đổi server_id không tự làm server_uuid thay đổi; ngược lại, tạo UUID mới không làm server_id trở nên duy nhất.

### 1.1. Các tập GTID quan trọng

MySQL cung cấp một số biến và trường trạng thái:

| Tên | Ý nghĩa |
|---|---|
| GTID_EXECUTED | Tập GTID mà instance đã thực thi |
| GTID_PURGED | Tập GTID đã thực thi nhưng binary log chứa các transaction đó đã bị purge khỏi instance |
| Retrieved_Gtid_Set | Trên replica, tập GTID đã được receiver thread lấy từ source |
| Executed_Gtid_Set | Trên replica, tập GTID đã được applier thực thi |
| GTID_SUBSET(set1, set2) | Trả về 1 nếu set1 là tập con của set2 |
| GTID_SUBTRACT(set1, set2) | Trả về các GTID có trong set1 nhưng không có trong set2 |

Kiểm tra biến trên từng instance:

~~~sql
SELECT
    @@GLOBAL.server_id AS server_id,
    @@GLOBAL.server_uuid AS server_uuid,
    @@GLOBAL.gtid_mode AS gtid_mode,
    @@GLOBAL.enforce_gtid_consistency AS enforce_gtid_consistency,
    @@GLOBAL.log_bin AS log_bin,
    @@GLOBAL.gtid_executed AS gtid_executed,
    @@GLOBAL.gtid_purged AS gtid_purged;
~~~

GTID_EXECUTED là lịch sử transaction đã thực thi. GTID_PURGED là một tập con của lịch sử đó, không phải một tập GTID có thể tùy ý đặt để đánh dấu rằng replica đã có dữ liệu. Gán GTID không tương ứng với dữ liệu thật có thể làm replication bỏ qua transaction mà instance chưa thực sự áp dụng.

## 2. Nhận diện GTID sai lệch

Trong topology đơn giản, giả sử source có tập GTID S và replica có tập GTID R. Có ba trường hợp cần phân biệt:

1. **Replica thiếu transaction:** một số GTID có trên source nhưng chưa có trong GTID_EXECUTED của replica.
2. **Replica có transaction thừa (errant transaction):** một số GTID có trên replica nhưng không có trên source.
3. **Hai bên có lịch sử phân nhánh:** mỗi bên có một phần GTID riêng, không bên nào là tập con hoàn toàn của bên còn lại.

Ví dụ:

~~~text
Source:
  uuid-A:1-120

Replica:
  uuid-A:1-100
~~~

Replica thiếu các transaction 101 đến 120. Nếu source còn binary log chứa các GTID đó và replication hoạt động bình thường, replica có thể nhận và áp dụng phần còn thiếu.

Ví dụ khác:

~~~text
Source:
  uuid-A:1-120

Replica:
  uuid-A:1-120
  uuid-B:1
~~~

Replica có thêm GTID uuid-B:1. Đây có thể là transaction được ghi trực tiếp trên replica khi nó không nên nhận ghi, hoặc được tạo từ một lịch sử dữ liệu khác. Đây là dấu hiệu errant transaction cần điều tra.

### 2.1. Kiểm tra trạng thái asynchronous replication

Trên MySQL 8.0.22 trở lên, dùng:

~~~sql
SHOW REPLICA STATUS\G
~~~

Các phiên bản cũ hơn dùng tên lệnh:

~~~sql
SHOW SLAVE STATUS\G
~~~

Những trường cần đọc:

- Replica_IO_Running và Replica_SQL_Running: trạng thái receiver và applier thread.
- Last_IO_Errno, Last_IO_Error: lỗi khi kết nối hoặc nhận binary log.
- Last_SQL_Errno, Last_SQL_Error: lỗi khi áp dụng transaction.
- Retrieved_Gtid_Set: GTID đã nhận từ source.
- Executed_Gtid_Set: GTID đã thực thi tại replica.
- Auto_Position: trạng thái sử dụng GTID auto-position.
- Seconds_Behind_Source: ước lượng độ trễ; NULL không đồng nghĩa replica đã đồng bộ.

Tên trường có thể khác ở phiên bản cũ, ví dụ Slave_IO_Running hoặc Seconds_Behind_Master. Hãy dùng tên phù hợp với phiên bản đang chạy.

Không kết luận replica đồng bộ chỉ vì hai thread đều Yes. Cần so sánh GTID set, kiểm tra lỗi gần nhất và xác minh transaction đã được thực thi.

### 2.2. So sánh GTID set bằng hàm MySQL

Ví dụ tập GTID giả định của source và replica:

~~~sql
SET @source_gtids =
  '24bc7850-2c16-11ef-a1c4-0242ac120002:1-120';

SET @replica_gtids =
  '24bc7850-2c16-11ef-a1c4-0242ac120002:1-100';

SELECT
    GTID_SUBSET(@replica_gtids, @source_gtids)
        AS replica_is_subset_of_source,
    GTID_SUBTRACT(@source_gtids, @replica_gtids)
        AS missing_on_replica,
    GTID_SUBTRACT(@replica_gtids, @source_gtids)
        AS extra_on_replica;
~~~

Kết quả mong đợi:

- replica_is_subset_of_source bằng 1.
- missing_on_replica chứa dải GTID 101-120.
- extra_on_replica là tập rỗng.

Trong production, lấy tập GTID thực tế từ từng server và đưa vào phép so sánh. Không dùng chuỗi ví dụ này để thay thế dữ liệu thật.

Nếu GTID set rất lớn, kết quả có thể dài. Hãy lưu kết quả kiểm tra vào incident record có kiểm soát và tránh gửi dữ liệu nhạy cảm không cần thiết.

### 2.3. Retrieved khác Executed

Một replica có thể đã nhận GTID từ source nhưng chưa thực thi hết. Khi đó Retrieved_Gtid_Set lớn hơn Executed_Gtid_Set. Đây là trạng thái có thể xảy ra khi applier đang xử lý backlog.

Không dùng Retrieved_Gtid_Set làm bằng chứng transaction đã được áp dụng vào bảng. Để xác nhận hoàn tất, cần đợi applier xử lý và kiểm tra Executed_Gtid_Set.

Có thể dùng hàm chờ:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET(
    '24bc7850-2c16-11ef-a1c4-0242ac120002:1-120',
    30
) AS wait_result;
~~~

Hàm trả về 0 khi tập GTID yêu cầu đã được thực thi, 1 khi hết timeout và NULL nếu có lỗi. Timeout tính bằng giây. Dùng GTID set thực tế của điểm cần chờ, không sao chép chuỗi ví dụ.

## 3. Nguyên nhân thường gặp của GTID divergence

### 3.1. Ghi trực tiếp trên replica

Một replica được thiết kế chỉ đọc nhưng ứng dụng, tài khoản vận hành hoặc job nền vẫn ghi dữ liệu. Transaction đó tạo GTID riêng từ UUID của replica. Khi so sánh với source, GTID này trở thành transaction thừa.

Kiểm tra:

- Ứng dụng có kết nối nhầm endpoint replica không.
- Có tài khoản quản trị hoặc job chạy DML trực tiếp trên replica không.
- Có session nào tạm tắt read_only/super_read_only không.
- Có tác vụ migration hoặc maintenance được chạy trên một node riêng không.

Các biến liên quan:

~~~sql
SELECT
    @@GLOBAL.read_only,
    @@GLOBAL.super_read_only,
    @@GLOBAL.server_uuid,
    @@GLOBAL.gtid_executed;
~~~

read_only và super_read_only giúp hạn chế ghi ngoài luồng, nhưng không thay thế phân quyền và quy trình vận hành. Một số tài khoản đặc quyền có thể vượt qua read_only tùy phiên bản và quyền. Cần giới hạn tài khoản ghi và giám sát thay đổi cấu hình.

### 3.2. Khởi tạo replica từ backup không đúng điểm

Replica được restore từ backup nhưng GTID metadata không khớp với dữ liệu trong backup. Ví dụ, backup chứa dữ liệu đến một thời điểm nhưng GTID_PURGED được khai báo sai hoặc GTID_EXECUTED được bổ sung thủ công không phản ánh transaction đã có trong data.

Khi bật auto-position, source và replica trao đổi GTID set để xác định transaction còn thiếu. Nếu metadata tuyên bố replica đã có một GTID nhưng dữ liệu không có transaction tương ứng, source sẽ không gửi lại GTID đó và dữ liệu có thể thiếu mà không được tự động sửa.

Vì vậy, backup phải giữ đúng metadata GTID và thông tin binary log/position tương ứng. Dùng công cụ backup có hỗ trợ ghi nhận GTID nhất quán; không tự dựng GTID set từ một giá trị ước lượng.

### 3.3. Source đã purge binary log mà replica còn cần

Nếu source đã xóa binary log chứa GTID mà replica chưa nhận, source không thể gửi lại các transaction đó. Replica có thể báo lỗi rằng source đã purge binary log chứa GTID cần thiết.

Kiểm tra GTID_PURGED ở source và tập còn thiếu trên replica. Nếu các GTID cần thiết không còn trong binary log của source, hướng phục hồi thông thường là tạo lại replica từ backup/clone mới có lịch sử GTID phù hợp, sau đó kết nối lại bằng auto-position.

Không giả mạo GTID_PURGED trên replica để bỏ qua lỗi. Làm vậy chỉ thay đổi metadata về lịch sử transaction, không khôi phục dữ liệu bị thiếu.

### 3.4. Dùng nhiều nguồn hoặc promote/failover không đúng quy trình

Trong topology có nhiều source, multi-source replication hoặc sau failover, mỗi nguồn có thể đóng góp GTID từ UUID khác nhau. Nếu promote một replica có lịch sử riêng rồi tiếp tục ghi ở hai nhánh, tập GTID có thể phân kỳ.

Trước khi failover:

- Chọn duy nhất một writer authoritative.
- Đảm bảo node được promote đã áp dụng các transaction cần thiết.
- Chặn writer cũ để tránh split-brain.
- Xác định rõ cách các replica còn lại chuyển source.
- Kiểm tra GTID set trước và sau khi chuyển vai trò.

Không để source cũ và source mới cùng nhận ghi trong khi chưa có kiến trúc multi-writer được thiết kế và kiểm chứng.

## 4. Phân tích GTID set có thiếu hay có transaction thừa

Khi điều tra, thu thập các giá trị sau từ source và replica:

~~~sql
SELECT @@GLOBAL.server_uuid,
       @@GLOBAL.server_id,
       @@GLOBAL.gtid_executed,
       @@GLOBAL.gtid_purged;
~~~

Trên replica, lưu thêm kết quả SHOW REPLICA STATUS. Sau đó so sánh:

- GTID có ở source nhưng thiếu ở replica: replica chưa nhận/chưa thực thi hoặc đã mất binary log cần thiết.
- GTID có ở replica nhưng không có ở source: nghi ngờ errant transaction hoặc source đã được thay thế bằng một nhánh khác.
- Cả hai phía đều có GTID riêng: cần xác định lịch sử phân nhánh và node nào là authoritative.
- GTID set bằng nhau nhưng dữ liệu khác nhau: GTID metadata không đủ để chứng minh dữ liệu đồng nhất; cần kiểm tra dữ liệu bằng checksum/row comparison hoặc công cụ xác minh phù hợp.

### 4.1. Ví dụ kiểm tra errant GTID

Giả sử source và replica:

~~~sql
SET @source_gtids =
  '24bc7850-2c16-11ef-a1c4-0242ac120002:1-120';

SET @replica_gtids =
  '24bc7850-2c16-11ef-a1c4-0242ac120002:1-120,
   6c7b1b60-2c16-11ef-a1c4-0242ac120002:1';

SELECT GTID_SUBTRACT(@replica_gtids, @source_gtids)
       AS errant_gtids;
~~~

Nếu kết quả chứa UUID thứ hai, replica đã thực thi ít nhất một GTID không nằm trong lịch sử source đang so sánh. Cần điều tra transaction đó được tạo bởi session nào, ở thời điểm nào và có thay đổi dữ liệu gì.

Có thể kiểm tra lịch sử transaction trong Performance Schema nếu instrumentation và history còn dữ liệu, nhưng history có thể bị giới hạn hoặc mất sau restart. Không giả định Performance Schema luôn lưu toàn bộ lịch sử.

## 5. Khắc phục replica thiếu GTID

Nếu replica chỉ thiếu transaction và source vẫn giữ đầy đủ binary log:

1. Kiểm tra kết nối receiver và trạng thái applier.
2. Đọc Last_IO_Error và Last_SQL_Error.
3. Xác nhận source chưa purge GTID cần thiết.
4. Kiểm tra không có errant GTID làm phức tạp lịch sử.
5. Khắc phục lỗi kết nối, quyền replication hoặc lỗi áp dụng cụ thể.
6. Cho replica tiếp tục nhận và áp dụng transaction.
7. Chờ tới GTID set mục tiêu bằng WAIT_FOR_EXECUTED_GTID_SET.
8. So sánh GTID set lại sau khi hoàn tất.

Nếu applier dừng do một transaction lỗi, không tự bỏ qua transaction chỉ để thread chuyển sang Yes. Cần hiểu lỗi dữ liệu hoặc schema ở replica, đối chiếu source và sửa theo một quy trình nhất quán. Bỏ qua sự kiện có thể khiến dữ liệu replica khác source vĩnh viễn.

### 5.1. Cấu hình GTID auto-position

Với MySQL 8.0.23 trở lên, lệnh cấu hình source dùng tên mới:

Nếu replica đang có channel chạy, dừng replication trước khi thay đổi cấu hình:

~~~sql
STOP REPLICA;
~~~

~~~sql
CHANGE REPLICATION SOURCE TO
    SOURCE_HOST = 'source.example.net',
    SOURCE_PORT = 3306,
    SOURCE_USER = 'repl_user',
    SOURCE_AUTO_POSITION = 1;
~~~

Thông tin xác thực cần được cấu hình bằng quy trình bảo mật của tổ chức; không đưa mật khẩu thật vào tài liệu, log hoặc lịch sử shell. Trên phiên bản cũ, tên lệnh là CHANGE MASTER TO và tùy chọn là MASTER_AUTO_POSITION = 1.

Sau đó:

~~~sql
START REPLICA;
SHOW REPLICA STATUS\G
~~~

Lệnh này chỉ thiết lập cơ chế kết nối và auto-position. Nó không tự sửa dữ liệu thiếu, errant GTID, UUID trùng hoặc binary log đã bị purge.

## 6. Khắc phục khi source đã purge GTID replica cần

Nếu source không còn binary log cần thiết, replica không thể bắt kịp chỉ bằng cách restart thread.

Quy trình thường dùng:

1. Dừng replication trên replica lỗi để tránh thử lại liên tục.
2. Ghi lại GTID_EXECUTED, GTID_PURGED, Retrieved_Gtid_Set, Executed_Gtid_Set và lỗi.
3. Xác nhận source hiện tại là nguồn dữ liệu authoritative.
4. Tạo backup/clone mới từ source hoặc một bản sao đã đồng bộ đầy đủ.
5. Bảo đảm backup ghi nhận đúng GTID state.
6. Khôi phục lên replica đích với server_id và server_uuid riêng.
7. Kiểm tra GTID_PURGED/GTID_EXECUTED của bản restore.
8. Cấu hình replication bằng auto-position.
9. Chờ replica bắt kịp và xác minh dữ liệu.

Thời gian retention binary log phải đủ dài để bao phủ sự cố, thời gian phát hiện, sửa chữa và bắt kịp replica. Có thể kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW BINARY LOGS;
~~~

Tên biến và câu lệnh hiển thị binary log cần đối chiếu phiên bản. Với bản cũ có thể gặp expire_logs_days. Không purge log thủ công khi chưa xác minh mọi replica và backup cần chúng.

## 7. Errant transaction: vì sao không được xóa GTID tùy tiện?

Errant transaction là transaction đã thực thi trên một node nhưng không thuộc lịch sử của source mà node đó phải theo. Đây là dấu hiệu lịch sử dữ liệu có thể đã phân nhánh.

Ví dụ, một quản trị viên chạy UPDATE trực tiếp trên replica. GTID mới được ghi nhận trong GTID_EXECUTED của replica. Khi source tiếp tục replication, auto-position không yêu cầu source gửi lại GTID đã có. Nhưng transaction trên replica có thể thay đổi dữ liệu theo cách source không có.

Không nên:

- Xóa thủ công auto.cnf để “làm mất” GTID của transaction.
- Gán lại GTID_PURGED để ép hai tập trông giống nhau.
- Chạy RESET MASTER hoặc lệnh reset binary log trên node đang giữ dữ liệu cần bảo toàn.
- Bỏ qua transaction lỗi mà không đối chiếu dữ liệu.
- Đưa replica có errant GTID trở lại production chỉ vì replication thread đã chạy.

Hướng xử lý phụ thuộc dữ liệu:

- Nếu node không có dữ liệu độc lập cần giữ, dựng lại node từ nguồn authoritative là cách rõ ràng và an toàn hơn.
- Nếu transaction thừa chứa thay đổi nghiệp vụ cần giữ, phải đối soát và áp dụng thay đổi đó lên source theo một migration/DML có kiểm soát; sau đó dựng lại replica hoặc đồng bộ theo kế hoạch.
- Nếu source đã được promote và lịch sử cũ cần hợp nhất, cần lập kế hoạch failover/rejoin theo topology, tránh tự sửa GTID metadata.

GTID là lịch sử transaction, không phải công cụ để hợp nhất hai bộ dữ liệu phân kỳ.

## 8. Server UUID trùng sau khi clone data directory

MySQL lưu server UUID trong file auto.cnf ở data directory. Nếu sao chép toàn bộ data directory bằng thao tác filesystem, file này có thể được sao chép cùng. Khi source và clone cùng khởi động với một UUID, replication có thể dừng vì hai instance có cùng server UUID.

Một lỗi thường gặp có nội dung tương tự:

~~~text
The slave I/O thread stops because master and slave have equal
MySQL server UUIDs; these UUIDs must be different for replication to work.
~~~

Tên thread trong thông báo có thể dùng thuật ngữ cũ. Ý nghĩa vẫn là source và replica đang có cùng server_uuid.

### 8.1. Kiểm tra UUID và server_id

Trên từng instance:

~~~sql
SELECT
    @@hostname AS hostname,
    @@port AS port,
    @@server_id AS server_id,
    @@server_uuid AS server_uuid;
~~~

Hai node trong cùng topology replication cần server_id khác nhau và server_uuid khác nhau. Không chỉ so sánh hostname hoặc IP: hai máy có hostname khác nhau vẫn có thể giữ UUID trùng nếu cùng được tạo từ một bản sao data directory.

### 8.2. Vì sao đổi server_id không đủ?

GTID chứa UUID nguồn, không chứa server_id. Nếu hai node có cùng server_uuid, chỉ đổi server_id không làm cho GTID identity trở nên riêng biệt.

Với bản clone được tạo bằng cách copy data directory, cần kiểm tra auto.cnf. Nếu UUID bị trùng, dừng instance clone và thực hiện quy trình cấp UUID mới cho đúng node clone. Không xóa hoặc sửa auto.cnf trên instance đang chạy.

### 8.3. Tạo UUID mới cho clone thủ công

Với bản sao data directory độc lập, quy trình khái quát:

1. Cô lập clone khỏi mạng production và dừng MySQL trên clone.
2. Xác nhận đúng data directory của clone; không thao tác nhầm source.
3. Sao lưu file auto.cnf hiện tại để phục vụ điều tra.
4. Xóa file auto.cnf trên clone khi mysqld đã dừng hoàn toàn.
5. Đặt server_id mới, duy nhất trong topology, trong cấu hình của clone.
6. Khởi động clone; MySQL sẽ tạo server UUID mới nếu không có auto.cnf hợp lệ.
7. Đọc lại server_uuid và server_id qua SQL.
8. Chỉ kết nối clone vào topology sau khi xác nhận danh tính mới và GTID state phù hợp.

Ví dụ kiểm tra sau khởi động:

~~~sql
SELECT @@GLOBAL.server_id, @@GLOBAL.server_uuid;
~~~

Không tự tạo UUID bằng cách sửa nội dung file auto.cnf khi server đang chạy. Cũng không xóa auto.cnf trên source để sửa lỗi của replica; thao tác phải nhắm chính xác vào instance clone.

Nếu dùng công cụ clone/backup chuyên dụng, hãy đọc quy trình của công cụ và phiên bản MySQL để biết cách xử lý danh tính instance. Dù công cụ có xử lý một số metadata tự động, vẫn phải xác minh server_uuid và server_id sau khi clone.

## 9. Clone để dựng replica và clone làm môi trường độc lập

Hai mục tiêu clone có yêu cầu khác nhau.

| Nội dung | Clone để dựng replica | Clone thành dev/test độc lập |
|---|---|---|
| Dữ liệu | Cần nhất quán với source | Có thể dùng snapshot được che/mask dữ liệu |
| GTID history | Phải giữ chính xác metadata GTID của backup | Phải quyết định có giữ lịch sử hay chuyển thành môi trường độc lập |
| server_uuid | Phải riêng biệt với source và các replica khác | Phải riêng biệt, không dùng UUID production |
| server_id | Duy nhất trong topology replication | Dùng ID riêng, không trùng nếu có kết nối replication |
| Replication channel | Cấu hình để kết nối source dự kiến | Không tự động kết nối production |
| Network | Cho phép kết nối source và các endpoint cần thiết | Cô lập hoặc allowlist chặt chẽ |
| Credentials | Dùng tài khoản replication được giới hạn | Thay/loại bỏ secret production |
| Group Replication | Chỉ tham gia nhóm khi đã cấu hình đúng identity và topology | Không tham gia cluster production |

### 9.1. Clone để dựng replica mới

Khi clone để thay một replica hoặc mở rộng topology:

- Giữ GTID metadata đi cùng backup.
- Cấp server_uuid và server_id riêng cho recipient.
- Bảo đảm GTID mode và enforce_gtid_consistency tương thích với topology.
- Cấu hình source bằng GTID auto-position khi toàn bộ điều kiện đã đáp ứng.
- Kiểm tra source còn binary log cần thiết nếu không dùng backup mới nhất.
- Không reset GTID history chỉ để loại bỏ UUID cũ; làm vậy có thể phá khả năng auto-position.
- Xác minh replica đã bắt kịp trước khi nhận traffic đọc.

Một bản clone từ source có thể chứa dữ liệu đến GTID nhất định. Khi restore, GTID state phải phản ánh đúng dữ liệu đó để source chỉ gửi transaction còn thiếu.

### 9.2. Clone thành dev/test độc lập

Một bản clone production đưa vào dev/test cần được cô lập trước khi mở ứng dụng hoặc cho phép network traffic:

1. Chặn kết nối tới source, replica và Group Replication production.
2. Tắt tự khởi động replication ở lần boot đầu nếu cấu hình được sao chép có channel production.
3. Đặt server_id riêng và cấp server_uuid mới nếu UUID được copy.
4. Kiểm tra các replication channel và chỉ xóa cấu hình channel khi đã xác nhận môi trường này không cần tiếp tục vai trò replica.
5. Kiểm tra group_replication_start_on_boot và cấu hình group replication; không để clone tự tham gia cluster production.
6. Thay hostname, port, endpoint, tài khoản ứng dụng và secret.
7. Mask dữ liệu cá nhân/nhạy cảm theo chính sách môi trường.
8. Kiểm tra event scheduler, cron/job, webhook, email/SMS, queue consumer và tích hợp bên ngoài để tránh clone phát sinh hành động thật.
9. Xác minh ứng dụng chỉ kết nối tới database dev/test.

Có thể dùng tùy chọn khởi động skip_replica_start để ngăn replica tự khởi động thread trong giai đoạn cô lập. Tên tùy chọn và hành vi cần kiểm tra theo phiên bản MySQL. Đây là biện pháp phòng ngừa khi khởi động, không thay thế việc rà soát channel và network.

Nếu clone độc lập không còn cần replication metadata, có thể cân nhắc STOP REPLICA rồi RESET REPLICA ALL trên đúng instance sau khi đã ghi lại cấu hình và xác nhận không cần dùng lại channel. Lệnh này xóa thông tin kết nối/relay log của replica nhưng không xóa GTID_EXECUTED và không biến dữ liệu thành một lịch sử GTID mới. Trên phiên bản cũ, tên lệnh là STOP SLAVE và RESET SLAVE ALL. Không nhầm thao tác này với việc reset GTID hoặc binary log.

## 10. Group Replication và UUID trùng

Group Replication dùng danh tính thành viên và trao đổi transaction giữa các node. UUID trùng hoặc server_id không duy nhất có thể khiến member không thể tham gia nhóm hoặc gây xung đột danh tính.

Kiểm tra:

~~~sql
SELECT MEMBER_ID, MEMBER_HOST, MEMBER_PORT,
       MEMBER_STATE, MEMBER_ROLE
FROM performance_schema.replication_group_members;
~~~

Trên từng node, kiểm tra:

~~~sql
SELECT @@GLOBAL.server_id,
       @@GLOBAL.server_uuid,
       @@GLOBAL.group_replication_group_name,
       @@GLOBAL.group_replication_local_address,
       @@GLOBAL.group_replication_start_on_boot;
~~~

Trước khi thêm một node clone vào nhóm:

- Cấp server_uuid và server_id riêng.
- Đặt group_replication_local_address riêng, không trùng địa chỉ thành viên khác.
- Xác nhận group_replication_group_name đúng nhóm dự định tham gia.
- Kiểm tra seed list và endpoint network.
- Kiểm tra recovery credentials và TLS.
- Dùng MySQL Shell/AdminAPI hoặc quy trình quản trị cụm đã được phê duyệt để thêm member.
- Chờ member đạt ONLINE và xác minh quorum trước khi chuyển sang thao tác tiếp theo.

Không copy nguyên cấu hình Group Replication từ source sang clone rồi khởi động đồng thời. Clone có thể vô tình kết nối vào production group với danh tính hoặc địa chỉ trùng.

## 11. Các lệnh reset nguy hiểm và hiểu lầm thường gặp

Một số lệnh có tác động lớn tới replication metadata hoặc binary log:

| Lệnh | Tác động khái quát | Điều cần nhớ |
|---|---|---|
| RESET REPLICA | Xóa relay log và trạng thái relay/replica tương ứng | Không xóa GTID_EXECUTED |
| RESET REPLICA ALL | Ngoài reset trạng thái, xóa cấu hình connection/channel | Không phải lệnh reset GTID history; bản cũ dùng RESET SLAVE ALL |
| RESET MASTER trên phiên bản cũ | Xóa binary logs và reset một phần trạng thái GTID/binlog | Có thể phá lịch sử cần cho replica và backup |
| RESET BINARY LOGS AND GTIDS trên MySQL 8.4 | Lệnh reset binary log và GTID tương ứng của phiên bản mới | Thao tác phá hủy; không dùng như bước sửa lỗi thông thường |
| SET GLOBAL gtid_purged | Thay đổi metadata GTID đã purge theo các điều kiện nghiêm ngặt | Không làm dữ liệu thật xuất hiện trên server |

Không chạy các lệnh reset chỉ vì GTID set đang khác nhau. Trước khi dùng, phải xác định rõ mục đích, phiên bản MySQL, backup, trạng thái mọi replica và tác động tới khả năng phục hồi. Với lỗi GTID divergence, dựng lại replica từ nguồn authoritative thường an toàn hơn việc cố chỉnh metadata cho hai tập trông giống nhau.

## 12. Quy trình điều tra và phục hồi tổng thể

Khi phát hiện GTID mismatch, UUID trùng hoặc clone sai:

### Bước 1 — Cô lập và bảo toàn bằng chứng

- Xác định node nào có thể đang ghi sai.
- Nếu clone có nguy cơ kết nối production, cô lập network trước.
- Không xóa file, reset GTID hoặc thay đổi source/replica role khi chưa ghi lại trạng thái.
- Lưu error log, SHOW REPLICA STATUS, server_id, server_uuid và GTID sets.

### Bước 2 — Xác định nguồn dữ liệu authoritative

- Xác định writer hợp lệ tại thời điểm sự cố.
- Xem xét failover, split-brain hoặc ghi trực tiếp trên replica.
- So sánh GTID và dữ liệu ở các node liên quan.
- Không chọn node authoritative chỉ dựa trên số GTID lớn hơn; GTID lớn hơn không có nghĩa dữ liệu đúng hơn.

### Bước 3 — Phân loại sự cố

- Replica chỉ thiếu GTID và source còn binlog.
- Source đã purge GTID replica cần.
- Replica có errant GTID.
- GTID metadata không khớp với dữ liệu backup.
- server_uuid trùng do copy data directory.
- server_id trùng hoặc clone tự tham gia replication/cluster.
- GTID giống nhau nhưng dữ liệu thực tế khác nhau.

### Bước 4 — Chọn cách phục hồi

- Với replica thiếu GTID: sửa receiver/applier và chờ áp dụng.
- Với binlog đã purge: dựng lại replica từ backup/clone mới.
- Với errant transaction: đối soát và xử lý dữ liệu, sau đó dựng lại node nếu cần.
- Với UUID trùng: cô lập clone, cấp danh tính mới và kiểm tra GTID state.
- Với clone dev/test: tắt kết nối production, rà soát channel/cluster, credentials và các tác vụ bên ngoài.
- Với Group Replication: dùng quy trình member recovery và quorum phù hợp, không bootstrap nhóm mới tùy tiện.

### Bước 5 — Xác minh sau phục hồi

- server_id và server_uuid duy nhất.
- GTID mode và cấu hình consistency phù hợp.
- GTID set được so sánh theo hướng mong đợi.
- Receiver/applier hoặc Group Replication member hoạt động ổn định.
- Không còn Last_IO_Error/Last_SQL_Error.
- Replica đã thực thi tới GTID mục tiêu.
- Dữ liệu quan trọng được đối chiếu.
- Clone dev/test không thể ghi hoặc phát message tới production.
- Backup và binary log retention đáp ứng yêu cầu phục hồi tiếp theo.

## 13. Ví dụ: dựng lại replica sau khi binary log đã bị purge

Giả sử replica R bị offline quá lâu. Source S đã purge một phần binary log mà R cần. R không thể tiếp tục bắt kịp.

Quy trình hợp lý:

1. Trên R, ghi lại server_uuid, server_id, GTID_EXECUTED và lỗi replication.
2. Trên S, xác nhận GTID_PURGED và xác định các transaction không còn trong binary log.
3. Dừng replication ở R và đánh dấu node không phục vụ traffic.
4. Tạo backup nhất quán mới từ S hoặc một node đã đồng bộ đầy đủ.
5. Restore backup lên R theo quy trình được hỗ trợ.
6. Cấp server_id mới nếu node đã được thay thế; xác nhận server_uuid khác S và mọi replica khác.
7. Kiểm tra GTID_EXECUTED/GTID_PURGED từ backup, không tự đặt lại.
8. Cấu hình SOURCE_AUTO_POSITION = 1 và START REPLICA.
9. Chờ tới khi GTID_EXECUTED của R bao phủ GTID mục tiêu.
10. Chạy kiểm tra dữ liệu và chỉ đưa R vào pool đọc khi đã ổn định.

Nếu dùng bản backup cũ hơn source hiện tại, source vẫn phải giữ binary log chứa mọi transaction sau điểm backup. Nếu không, phải lấy backup mới hơn. Đây là lý do cần retention đủ dài và quy trình backup có GTID metadata chính xác.

## 14. Checklist GTID, UUID và clone

- [ ] Đã ghi lại server_id và server_uuid trên từng node.
- [ ] Đã xác nhận không có hai instance dùng cùng server_uuid.
- [ ] Đã xác nhận server_id duy nhất trong topology replication.
- [ ] Đã kiểm tra gtid_mode, enforce_gtid_consistency và log_bin.
- [ ] Đã lưu GTID_EXECUTED và GTID_PURGED của source/replica.
- [ ] Đã phân biệt Retrieved_Gtid_Set với Executed_Gtid_Set.
- [ ] Đã dùng GTID_SUBSET và GTID_SUBTRACT để tìm GTID thiếu/thừa.
- [ ] Đã xác định source authoritative trước khi phục hồi.
- [ ] Đã kiểm tra source còn binary log mà replica cần.
- [ ] Đã điều tra errant transaction trước khi thay đổi GTID metadata.
- [ ] Đã không dùng RESET MASTER hoặc SET GLOBAL gtid_purged để che divergence.
- [ ] Đã cô lập clone trước khi khởi động hoặc kết nối network.
- [ ] Đã kiểm tra auto.cnf trên bản clone tạo bằng copy data directory.
- [ ] Đã cấp server_id và server_uuid mới cho clone.
- [ ] Đã rà soát replication channels và Group Replication startup.
- [ ] Đã thay credentials, endpoint và các tích hợp production trong môi trường dev/test.
- [ ] Đã xác minh GTID, replication, dữ liệu và trạng thái member sau phục hồi.

## 15. Tự kiểm tra

1. GTID có cấu trúc như thế nào và UUID trong GTID liên quan gì tới server_uuid?
2. server_id khác server_uuid ở điểm nào? Vì sao cần kiểm tra cả hai?
3. GTID_EXECUTED và GTID_PURGED biểu diễn điều gì?
4. Retrieved_Gtid_Set khác Executed_Gtid_Set như thế nào?
5. Dùng GTID_SUBTRACT để tìm GTID thiếu ở replica và errant GTID ra sao?
6. Vì sao replica có thể bị divergence dù cả receiver và applier thread đều báo Yes?
7. Điều gì xảy ra khi source đã purge binary log mà replica còn cần?
8. Vì sao đổi server_id không sửa được lỗi duplicate server_uuid?
9. Vì sao phải dừng clone trước khi xóa auto.cnf để tạo UUID mới?
10. Clone dùng làm replica khác clone dùng cho dev/test ở những yêu cầu GTID, replication channel và network nào?
11. Vì sao RESET REPLICA ALL không tương đương reset GTID_EXECUTED?
12. Hãy lập runbook phục hồi một replica có errant GTID và một clone dev/test đang vô tình kết nối vào Group Replication production.

GTID phản ánh lịch sử transaction; server_uuid và server_id xác định danh tính instance trong topology. Khi các giá trị này sai lệch, hãy bảo toàn trạng thái, tìm nguồn dữ liệu authoritative và phân loại sự cố trước khi sửa. Dựng lại replica từ backup có GTID metadata đúng thường an toàn hơn việc chỉnh sửa lịch sử GTID bằng tay; còn clone độc lập phải được cô lập và cấp danh tính riêng trước khi kết nối vào bất kỳ mạng production nào.
