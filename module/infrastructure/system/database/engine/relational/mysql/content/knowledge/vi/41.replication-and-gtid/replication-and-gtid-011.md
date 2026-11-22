# Parallel applier, dependency tracking và giữ thứ tự commit theo phiên bản

Replication song song cho phép replica áp dụng nhiều transaction cùng lúc, qua đó giảm độ trễ khi tải ghi trên source tăng. Để làm đúng, MySQL cần biết transaction nào độc lập, cần bao nhiêu applier worker và có phải giữ thứ tự commit như source hay không. Cơ chế dependency tracking tạo thông tin phụ thuộc trong binary log; logical clock dùng thông tin đó để phân phối transaction; commit-order preservation quyết định thứ tự mà thay đổi trở nên nhìn thấy trên replica.

Bài học này thuộc chương **Replication và GTID** của module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời, người học còn thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Replication song song giúp mở rộng năng lực đọc và duy trì bản sao cập nhật; phần này tập trung vào parallel applier, dependency tracking và các thay đổi tên biến/câu lệnh qua các phiên bản MySQL.

## 1. Luồng replication song song

Trong replication dựa trên binary log, source ghi transaction vào binlog. Replica có luồng nhận log và luồng áp dụng log:

- **Receiver thread** kết nối source và lấy các event binlog.
- **Relay log** lưu event đã nhận trên replica.
- **Coordinator thread** đọc relay log, phân tích dependency và phân phối transaction cho các worker.
- **Applier worker** thực thi transaction trên replica.

Mô hình khái quát:

~~~text
Source
  |
  | Binary log + dependency metadata
  v
Replica receiver
  |
  v
Relay log
  |
  v
Coordinator
  |             |              |
  v             v              v
Worker 1      Worker 2       Worker 3
  |             |              |
  +-------------+--------------+
                |
                v
       Commit theo chính sách
       preserve_commit_order
~~~

Coordinator không thể tùy ý chạy mọi transaction cùng lúc. Nếu hai transaction cập nhật cùng một hàng hoặc có quan hệ phụ thuộc, replica phải giữ quan hệ đó để dữ liệu cuối cùng đúng như source. Các transaction độc lập có thể được áp dụng đồng thời.

Số worker lớn không tự động làm replication nhanh hơn. Hiệu quả phụ thuộc vào mức độ độc lập của transaction, thông tin dependency source ghi vào binlog, CPU, I/O, dung lượng relay log và khả năng xử lý của storage engine.

## 2. Logical clock và dependency metadata

Khi dùng logical-clock scheduling, MySQL dựa vào metadata trong transaction event để xác định transaction nào có thể chạy song song. Hai trường quan trọng là:

- **sequence_number:** số thứ tự của transaction trong luồng binlog.
- **last_committed:** sequence number của transaction gần nhất được xác định có xung đột với transaction hiện tại.

Những transaction có dependency đã được đáp ứng có thể được phân phối cho các worker chạy đồng thời. Transaction phụ thuộc vào một transaction trước đó phải chờ cho đến khi dependency được hoàn tất theo quy tắc applier.

Metadata này không thay đổi thứ tự logic mà source đã tạo ra. Nó giúp replica nhận diện phần công việc có thể thực hiện song song mà vẫn bảo toàn quan hệ phụ thuộc. Logical clock là cơ chế lập lịch; độ chính xác và mức độ song song phụ thuộc vào cách source tính dependency.

## 3. Ba chế độ dependency tracking trên source

Từ MySQL 8.0.1, biến cấu hình binlog_transaction_dependency_tracking cho phép source ghi thông tin phụ thuộc theo các chế độ sau.

### COMMIT_ORDER

COMMIT_ORDER xem xét khoảng thời gian commit của hai transaction trên source. Nếu khoảng thời gian của transaction trước chồng lấp với transaction sau, MySQL có thể coi chúng độc lập vì chúng không giữ khóa hàng cùng lúc theo cách tạo xung đột. Thông tin group commit vì vậy tạo cơ hội cho replica áp dụng nhiều transaction song song.

Ưu điểm là cơ chế tương đối bảo thủ và không cần phân tích khóa của từng hàng. Hạn chế là mức song song có thể thấp nếu workload commit theo từng transaction nhỏ hoặc ít có group commit.

### WRITESET

WRITESET dùng write set của transaction để nhận diện các khóa hàng đã được ghi. Nếu hai transaction ghi vào những hàng khác nhau và không có dependency đã biết, source có thể đánh dấu chúng độc lập dù chúng không nằm trong cùng một nhóm commit.

Write set được xây dựng từ các khóa unique của hàng InnoDB, gồm khóa chính và các khóa unique phù hợp. Thiết kế bảng có PRIMARY KEY hoặc UNIQUE KEY ổn định giúp nhận diện xung đột hiệu quả hơn. Với write set rỗng hoặc một phần, bảng không có khóa chính/unique, hay thao tác trên bảng cha trong quan hệ khóa ngoại, source có thể quay về cách tính COMMIT_ORDER để bảo toàn dependency.

### WRITESET_SESSION

WRITESET_SESSION kết hợp phát hiện xung đột từ write set với việc giữ thứ tự transaction trong cùng một session trên source. Cơ chế này hữu ích khi ứng dụng dựa vào thứ tự các transaction nối tiếp trong một kết nối, chẳng hạn transaction sau đọc kết quả do transaction trước ghi.

### So sánh

| Chế độ | Cách xác định dependency | Đặc điểm |
|---|---|---|
| COMMIT_ORDER | Dựa trên thứ tự/group commit | Bảo thủ, ít phụ thuộc cấu trúc khóa |
| WRITESET | So sánh write set của transaction | Có thể phát hiện nhiều transaction độc lập hơn |
| WRITESET_SESSION | Write set và thứ tự trong cùng session | Giữ thêm quan hệ thứ tự của session |

WRITESET không có nghĩa là mọi transaction sẽ được chạy song song. Nếu nhiều transaction cùng cập nhật một khóa, chúng vẫn phụ thuộc. Các ràng buộc dữ liệu, thao tác DDL, transaction dài và giới hạn tài nguyên cũng có thể làm giảm mức song song.

## 4. Điều kiện để WRITESET hoạt động hiệu quả

Dependency tracking theo writeset được cấu hình trên **source**, nơi transaction được ghi vào binary log. Ví dụ dưới đây dùng tên biến của MySQL 8.0.26–8.0.28; từ 8.0.29, replica_parallel_type đã deprecated và LOGICAL_CLOCK là mặc định, vì vậy không nên thêm biến đó vào cấu hình mới:

~~~ini
[mysqld]
binlog_format=ROW
replica_parallel_type=LOGICAL_CLOCK
binlog_transaction_dependency_tracking=WRITESET
binlog_transaction_dependency_history_size=25000
~~~

- **binlog_transaction_dependency_tracking:** chọn COMMIT_ORDER, WRITESET hoặc WRITESET_SESSION.
- **binlog_transaction_dependency_history_size:** giới hạn lịch sử write set mà source giữ để so sánh dependency. Lịch sử lớn hơn có thể giúp nhận diện xung đột qua khoảng transaction rộng hơn, đổi lại tốn thêm bộ nhớ.

Trong MySQL 8.0, transaction_write_set_extraction mặc định dùng XXHASH64; giá trị này đủ để WRITESET hoạt động và không được đặt thành OFF. Biến transaction_write_set_extraction đã deprecated từ MySQL 8.0.26 và bị loại bỏ từ MySQL 8.3.0, vì vậy không đưa nó vào cấu hình mới. Trên MySQL 8.4, cơ chế writeset được quản lý nội bộ.

Các biến và giá trị mặc định có thể khác theo phiên bản. Kiểm tra tài liệu đúng bản MySQL và giá trị runtime trước khi thay đổi:

~~~sql
SHOW VARIABLES LIKE 'binlog_transaction_dependency_tracking';
SHOW VARIABLES LIKE 'transaction_write_set_extraction';
SHOW VARIABLES LIKE 'binlog_transaction_dependency_history_size';
~~~

Nhóm lệnh kiểm tra biến dependency ở trên áp dụng cho các phiên bản còn cung cấp những biến đó. MySQL 8.3 trở lên không còn transaction_write_set_extraction; MySQL 8.4 trở lên cũng không còn binlog_transaction_dependency_tracking.

Nếu dùng WRITESET mà không có thông tin khóa đủ tốt, lợi ích song song sẽ hạn chế. Hãy kiểm tra schema, đặc biệt là khóa chính và khóa unique của các bảng ghi nhiều. Không thêm một khóa unique chỉ để tăng song song nếu nó không phản ánh đúng quy tắc dữ liệu của ứng dụng.

Row-based binary logging là lựa chọn thông dụng cho replication hiện đại và giúp thể hiện thay đổi hàng rõ ràng. Hãy kiểm tra binlog_format trên source; nếu đang dùng STATEMENT hoặc MIXED, cần đọc tài liệu phiên bản để xác nhận chế độ dependency có sử dụng writeset như mong đợi hay không.

Từ MySQL 8.3.0, writeset chỉ được dùng để kiểm tra xung đột khi binlog_format=ROW; MIXED không còn được hỗ trợ cho phần kiểm tra dependency bằng writeset. Cấu hình ROW vì vậy là yêu cầu cần kiểm tra khi dùng WRITESET trên các bản phát hành mới.

MySQL 8.4 đã loại bỏ biến binlog_transaction_dependency_tracking. Khi source có replica dùng parallel applier, MySQL 8.4 tự sử dụng writeset để tạo dependency metadata, tương đương hành vi WRITESET trên các phiên bản trước.

## 5. Cấu hình parallel applier trên replica

Trên replica, các tên biến mới dùng tiền tố replica từ MySQL 8.0.26. Ví dụ dưới đây thể hiện cấu hình rõ ràng cho MySQL 8.0.26–8.0.28; từ 8.0.29, replica_parallel_type đã deprecated và LOGICAL_CLOCK là mặc định:

~~~ini
[mysqld]
replica_parallel_workers=8
replica_parallel_type=LOGICAL_CLOCK
replica_preserve_commit_order=ON
~~~

- **replica_parallel_workers:** số applier worker. Giá trị 0 tắt multi-threaded applier và dùng một luồng áp dụng tuần tự; từ MySQL 8.0.30, đặt giá trị 0 đã deprecated, nên đặt 1 khi cần áp dụng tuần tự. Số worker lớn hơn 1 cho phép nhiều transaction độc lập được xử lý đồng thời.
- **replica_parallel_type=LOGICAL_CLOCK:** dùng dependency metadata trong binlog để lập lịch transaction.
- **replica_preserve_commit_order=ON:** giữ thứ tự commit trên replica theo thứ tự commit của source trong khi vẫn cho phép worker thực thi song song.

Một lựa chọn lập lịch cũ hơn là **DATABASE**. Chế độ này có thể áp dụng đồng thời transaction thuộc các database khác nhau, nhưng chỉ phù hợp khi các database được cập nhật độc lập và không có ràng buộc chéo giữa chúng. LOGICAL_CLOCK dựa trên dependency metadata nên phù hợp hơn với workload cần parallel apply trong cùng database. Từ MySQL 8.0.29, replica_parallel_type và cách lập lịch DATABASE đã deprecated; LOGICAL_CLOCK là hướng được giữ lại.

Chọn số worker theo CPU, I/O, kích thước transaction và mức độ song song thực tế. Bắt đầu bằng số worker vừa phải, đo lag và tài nguyên, rồi điều chỉnh. Tăng worker quá cao có thể làm tăng chuyển ngữ cảnh, tranh chấp khóa, áp lực I/O và bộ nhớ mà không cải thiện tốc độ áp dụng.

Một số phiên bản có giá trị mặc định khác nhau cho số worker và kiểu parallel applier. Không dựa vào mặc định của phiên bản khác hoặc một bài hướng dẫn cũ; hãy đọc giá trị đang chạy:

~~~sql
SHOW VARIABLES LIKE 'replica_parallel_workers';
SHOW VARIABLES LIKE 'replica_parallel_type';
SHOW VARIABLES LIKE 'replica_preserve_commit_order';
~~~

Tên biến trong cấu hình phải phù hợp phiên bản server. Với MySQL cũ, các biến tương ứng dùng tiền tố slave, ví dụ slave_parallel_workers, slave_parallel_type và slave_preserve_commit_order.

## 6. Giữ thứ tự commit với replica_preserve_commit_order

Worker có thể bắt đầu và thực thi transaction theo lịch song song. Tuy nhiên, nếu transaction sau commit trước transaction trước đó, một truy vấn đọc trên replica có thể quan sát trạng thái trung gian khác với thứ tự commit trên source.

Khi replica_preserve_commit_order=ON, MySQL điều phối commit để transaction trở nên có hiệu lực theo đúng thứ tự commit của source. Transaction vẫn có thể thực thi đồng thời; worker nào hoàn tất sớm có thể phải chờ đến lượt commit. Vì vậy, commit-order preservation tăng tính nhất quán quan sát được nhưng có thể giảm throughput khi transaction trước đó chạy lâu.

Thiết lập này phù hợp khi ứng dụng đọc replica và cần nhìn thấy thứ tự thay đổi tương ứng với source, hoặc khi replica được dùng làm nguồn cho một replica tiếp theo. Đổi lại, phải chấp nhận khả năng worker chờ commit và mức song song thực tế thấp hơn.

Để dùng commit-order preservation, cấu hình applier theo LOGICAL_CLOCK. Nếu tắt preserve commit order, hãy đánh giá kỹ hành vi đọc trên replica và tác động tới topology downstream; không xem đó là tối ưu hiệu năng vô điều kiện.

## 7. Khác biệt cú pháp theo phiên bản MySQL

MySQL đã đổi một số tên từ slave/master sang replica/source. Các tên mới được giới thiệu theo từng phiên bản, vì vậy script vận hành phải khớp với phiên bản server và client.

| Phiên bản | Tên lệnh/biến cần lưu ý |
|---|---|
| MySQL 5.7 | Dùng slave_parallel_workers, slave_parallel_type và slave_preserve_commit_order. Chưa có writeset dependency tracking như MySQL 8.0. |
| MySQL 8.0.1 trở lên | Có binlog_transaction_dependency_tracking với COMMIT_ORDER, WRITESET và WRITESET_SESSION cho đến trước MySQL 8.4. |
| MySQL 8.0.22 trở lên | Có các tên lệnh replica mới như SHOW REPLICA STATUS, START REPLICA và STOP REPLICA; tên cũ được giữ tương thích trong giai đoạn chuyển đổi tùy phiên bản. |
| MySQL 8.0.23 trở lên | Dùng CHANGE REPLICATION SOURCE TO thay cho CHANGE MASTER TO trong cú pháp mới. |
| MySQL 8.0.26 trở lên | Các biến applier dùng tiền tố replica thay cho slave, ví dụ replica_parallel_workers. |
| MySQL 8.0.27 trở lên | Mặc định replica_parallel_workers=4, replica_parallel_type=LOGICAL_CLOCK và replica_preserve_commit_order=ON. Trước 8.0.27, các mặc định tương ứng là 0, DATABASE và OFF. |
| MySQL 8.0.29 trở lên | replica_parallel_type bị deprecated; không chọn DATABASE cho cấu hình mới. |
| MySQL 8.0.30 trở lên | Đặt replica_parallel_workers=0 bị deprecated; dùng 1 để chạy một worker tuần tự. |
| MySQL 8.0.35 / 8.2 | binlog_transaction_dependency_tracking bị deprecated. |
| MySQL 8.3 trở lên | transaction_write_set_extraction đã bị loại bỏ; writeset chỉ được dùng để kiểm tra xung đột khi binlog_format=ROW. |
| MySQL 8.4 trở lên | binlog_transaction_dependency_tracking bị loại bỏ; source tự dùng WRITESET khi có replica chạy parallel applier. |

Ví dụ kiểm tra trạng thái theo cú pháp mới:

~~~sql
SHOW REPLICA STATUS\G
~~~

Ở phiên bản cũ, dùng SHOW SLAVE STATUS\G. Tương tự, các thao tác điều khiển mới dùng START REPLICA và STOP REPLICA; bản cũ dùng START SLAVE và STOP SLAVE.

Không thay tên biến một cách máy móc trong file cấu hình mà chưa kiểm tra phiên bản. Với môi trường có nhiều phiên bản, duy trì cấu hình riêng theo nhóm phiên bản hoặc dùng automation có bước phát hiện phiên bản và chọn cú pháp tương ứng.

## 8. GTID và parallel apply giải quyết hai vấn đề khác nhau

GTID định danh transaction; dependency tracking xác định quan hệ thực thi giữa các transaction. Hai cơ chế bổ sung cho nhau nhưng không thay thế nhau.

- **GTID:** cho biết transaction nào đã được thực thi, hỗ trợ tự động định vị replication và đối chiếu tập transaction.
- **Dependency metadata:** cho biết transaction nào có thể áp dụng song song.
- **Parallel applier:** dùng metadata để phân phối transaction tới worker.
- **Commit-order preservation:** điều phối thời điểm commit trên replica để giữ thứ tự của source.

Trong MySQL 8.0.23 trở lên, cú pháp cấu hình source với GTID auto-position có dạng:

~~~sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'db-source.example.internal',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl_user',
  SOURCE_PASSWORD = 'replace-with-secret',
  SOURCE_AUTO_POSITION = 1;
~~~

Đây là ví dụ cú pháp; thông tin xác thực phải được quản lý an toàn và không lưu mật khẩu thật trong tài liệu hoặc lịch sử shell. GTID mode phải được bật và cấu hình nhất quán ở các máy chủ liên quan. Trên phiên bản cũ, cú pháp tương ứng là CHANGE MASTER TO với MASTER_AUTO_POSITION=1.

Các thiết lập nền tảng thường dùng trên cả source và replica:

~~~ini
[mysqld]
gtid_mode=ON
enforce_gtid_consistency=ON
~~~

Với topology đang chạy, bật GTID cần thực hiện theo lộ trình chuyển đổi phù hợp, kiểm tra mọi transaction và ứng dụng có tương thích hay không. Không bật trực tiếp hai biến trên một máy chủ đang phục vụ rồi giả định toàn topology đã sẵn sàng.

Kiểm tra trạng thái GTID:

~~~sql
SELECT @@GLOBAL.gtid_mode;
SELECT @@GLOBAL.gtid_executed;
SELECT @@GLOBAL.gtid_purged;
~~~

GTID giúp replica nhận biết transaction còn thiếu, nhưng không tự quyết định transaction nào độc lập. Muốn tăng song song, source vẫn cần ghi dependency metadata phù hợp và replica cần cấu hình logical-clock applier.

## 9. Kiểm tra hoạt động của worker

Trên replica, xem trạng thái replication:

~~~sql
SHOW REPLICA STATUS\G
~~~

Các trường cần quan sát tùy phiên bản gồm trạng thái receiver/applier, lỗi SQL, file relay log, GTID đã nhận và đã thực thi, cùng Seconds_Behind_Source. Trường lag là chỉ báo hữu ích nhưng không nên dùng một mình để kết luận replica khỏe hay đã bắt kịp; hãy đối chiếu worker, relay log, lỗi và tốc độ tăng log.

Performance Schema cung cấp thông tin theo từng worker:

~~~sql
SELECT
  CHANNEL_NAME,
  WORKER_ID,
  THREAD_ID,
  SERVICE_STATE,
  LAST_APPLIED_TRANSACTION
FROM performance_schema.replication_applier_status_by_worker
ORDER BY CHANNEL_NAME, WORKER_ID;
~~~

Kiểm tra coordinator:

~~~sql
SELECT
  CHANNEL_NAME,
  THREAD_ID,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE
FROM performance_schema.replication_applier_status_by_coordinator;
~~~

Tên cột có thể khác giữa các phiên bản. Dùng DESCRIBE performance_schema.replication_applier_status_by_worker nếu cần xác minh schema trên server đang chạy.

Các dấu hiệu cần theo dõi:

- Nhiều worker cùng có transaction đang được áp dụng cho thấy có hoạt động song song, nhưng chưa đủ chứng minh throughput tốt.
- Worker thường xuyên chờ commit có thể là hệ quả của preserve commit order hoặc transaction trước đó chậm.
- Relay log tăng liên tục trong khi source ổn định cho thấy replica không theo kịp tốc độ sinh transaction.
- Một worker có lỗi có thể làm coordinator dừng tiến trình áp dụng và gây lag toàn channel.
- CPU cao nhưng throughput thấp có thể do tranh chấp khóa, transaction lớn hoặc workload phụ thuộc mạnh.

## 10. Thực nghiệm dependency và thứ tự commit

Có thể kiểm tra trên môi trường thử nghiệm bằng hai nhóm transaction:

**Nhóm A – độc lập:** hai transaction cập nhật hai hàng có khóa chính khác nhau và không tác động tới cùng tài nguyên nghiệp vụ. Với WRITESET, source có thể nhận diện write set không xung đột và cho phép replica chạy chúng song song.

**Nhóm B – xung đột:** hai transaction cập nhật cùng một hàng hoặc cùng khóa unique. Dependency tracking phải giữ quan hệ cần thiết; replica không được áp dụng chúng theo cách làm sai kết quả.

Quy trình thực nghiệm:

1. Dùng một source và một replica thử nghiệm có cấu hình tương thích.
2. Tạo bảng InnoDB với PRIMARY KEY và dữ liệu mẫu.
3. Bật GTID, binary log và dependency tracking trên source theo phiên bản.
4. Cấu hình replica với nhiều worker, LOGICAL_CLOCK và preserve commit order.
5. Phát workload gồm transaction độc lập và transaction xung đột.
6. Quan sát worker, relay log, trạng thái GTID và độ trễ.
7. So sánh kết quả cuối trên source và replica; kiểm tra thứ tự commit khi đọc các thay đổi liên quan.
8. Thử lại với COMMIT_ORDER để so sánh mức song song và tài nguyên.

Không đo hiệu năng bằng một lần chạy duy nhất. Lặp lại workload với dữ liệu và thời gian chạy đủ lớn, giữ điều kiện phần cứng tương đương và theo dõi cả throughput lẫn lag.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Tăng worker nhưng lag không giảm | Transaction phụ thuộc nhiều, I/O hoặc CPU là nút thắt | Xem worker, thời gian transaction và tài nguyên hệ thống |
| WRITESET không tăng song song | Bảng thiếu khóa phù hợp, workload ghi cùng khóa hoặc lịch sử dependency ngắn | Kiểm tra PRIMARY KEY/UNIQUE KEY và cấu hình writeset |
| Worker chờ lâu trước khi commit | Transaction trước chưa hoàn tất hoặc preserve commit order buộc chờ | Xem worker status và transaction chậm |
| Replica dừng áp dụng | Lỗi SQL, dữ liệu lệch hoặc event không tương thích | Đọc lỗi coordinator/worker và đối chiếu source |
| Biến replica_* không nhận diện | Server phiên bản cũ dùng slave_* | Xác định phiên bản rồi dùng tên biến phù hợp |
| SHOW REPLICA STATUS không chạy | Server cũ chỉ hỗ trợ SHOW SLAVE STATUS | Dùng cú pháp tương thích phiên bản |
| GTID báo transaction đã tồn tại hoặc thiếu | Trạng thái GTID nền và chuỗi log không khớp | Đối chiếu GTID set, backup metadata và log; không tự bỏ qua transaction |

Khi điều tra lỗi, giữ nguyên relay log và log liên quan trước khi purge hoặc reset. Không dùng RESET REPLICA hoặc thao tác xóa relay log để che lỗi nếu chưa hiểu trạng thái GTID và dữ liệu đã áp dụng.

## 12. Nguyên tắc vận hành

- Cấu hình dependency tracking ở source và parallel applier ở replica; không nhầm hai vai trò.
- Dùng LOGICAL_CLOCK khi muốn replica khai thác dependency metadata trong binlog.
- Chọn COMMIT_ORDER khi cần cách lập lịch bảo thủ; cân nhắc WRITESET hoặc WRITESET_SESSION khi workload và schema cho phép.
- Duy trì PRIMARY KEY hoặc UNIQUE KEY phù hợp trên các bảng ghi nhiều để writeset nhận diện xung đột tốt.
- Bắt đầu với số worker vừa phải và đo hiệu năng trước khi tăng.
- Bật preserve commit order khi cần giữ thứ tự commit quan sát được như source; đánh giá chi phí chờ commit.
- GTID hỗ trợ định danh và định vị transaction; dependency tracking mới mô tả quan hệ song song.
- Dùng đúng tên biến và câu lệnh theo phiên bản MySQL; kiểm tra giá trị runtime thay vì giả định mặc định.
- Theo dõi worker, coordinator, relay log, lỗi và độ trễ cùng nhau.

Replication song song chỉ an toàn khi dependency được mô tả đúng và replica tuân thủ các quan hệ đó. Khi kết hợp writeset phù hợp, logical clock, số worker hợp lý và chính sách commit order rõ ràng, replica có thể tăng tốc độ áp dụng mà vẫn giữ kết quả dữ liệu đúng với source.

## Tài liệu tham khảo

- [MySQL 8.0: Binary Logging Options and Variables](https://dev.mysql.com/doc/refman/8.0/en/replication-options-binary-log.html)
- [MySQL 8.0: Replica Server Options and Variables](https://dev.mysql.com/doc/refman/8.0/en/replication-options-replica.html)
- [MySQL 8.4: Những thay đổi từ MySQL 8.0](https://dev.mysql.com/doc/refman/8.4/en/mysql-nutshell.html)
- [MySQL 8.4: Các tùy chọn và biến được thêm, deprecated hoặc loại bỏ](https://dev.mysql.com/doc/refman/8.4/en/added-deprecated-removed.html)
- [MySQL 8.3 Release Notes: Giới hạn writeset conflict checking cho row-based logging](https://dev.mysql.com/doc/relnotes/mysql/8.4/en/news-8-3-0.html)

