# Point-in-time recovery từ bản sao nền và chuỗi binary log

Point-in-time recovery (PITR) khôi phục MySQL từ một bản sao nền nhất quán, sau đó phát lại các sự kiện trong binary log đến đúng thời điểm cần phục hồi. Bản sao nền đưa máy chủ về một trạng thái đã biết; binary log cung cấp các thay đổi xảy ra sau trạng thái đó. Muốn PITR thành công, phải có tọa độ bắt đầu chính xác, chuỗi log liên tục và điểm dừng được xác định rõ.

Bài học này thuộc chương **Binary log và PITR** của module **DATABASE_MYSQL**. Module giúp người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Người học thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. PITR là kỹ năng vận hành giúp giảm lượng dữ liệu mất khi xảy ra xóa nhầm, cập nhật sai hoặc sự cố cần quay về một thời điểm trước đó.

## 1. Binary log lưu những gì?

Binary log (binlog) ghi lại các sự kiện làm thay đổi dữ liệu hoặc cấu trúc database. MySQL dùng binlog cho replication và phục hồi theo thời điểm. Một chuỗi binlog thường gồm nhiều file được đánh số tuần tự, ví dụ:

~~~text
mysql-bin.000120
mysql-bin.000121
mysql-bin.000122
mysql-bin.index
~~~

File index ghi danh sách các binary log mà máy chủ quản lý. Mỗi file log chứa các event với vị trí byte, timestamp, thông tin transaction và dữ liệu cần thiết để tái tạo thay đổi. Khi file hiện tại đạt giới hạn hoặc được rotate, MySQL tạo file tiếp theo.

Các nhóm sự kiện thường gặp:

- **Format description và metadata:** mô tả định dạng binlog, phiên bản và thông tin event.
- **GTID event:** định danh transaction toàn cục khi GTID được bật.
- **Query event:** thường ghi các câu lệnh DDL và sự kiện theo statement.
- **Table map và row event:** mô tả bảng cùng các thay đổi hàng khi dùng row-based logging.
- **Xid/commit event:** đánh dấu kết thúc transaction đã commit.

Binlog không phải bản sao dữ liệu đầy đủ. Nó chỉ có ý nghĩa khi được áp dụng lên đúng trạng thái nền và theo đúng thứ tự. Một file bị thiếu, hỏng hoặc lấy từ một máy chủ không cùng chuỗi có thể làm gián đoạn PITR.

## 2. Bật và cấu hình binary log

Trên máy chủ cần hỗ trợ PITR, kiểm tra cấu hình hiện tại:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'server_id';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_do_db';
SHOW VARIABLES LIKE 'binlog_ignore_db';
SHOW BINARY LOGS;
~~~

Tên câu lệnh xem trạng thái log hiện tại phụ thuộc phiên bản. Trên nhiều bản MySQL 8.0 có thể dùng:

~~~sql
SHOW MASTER STATUS;
~~~

Trên MySQL 8.4, dùng tên mới:

~~~sql
SHOW BINARY LOG STATUS;
~~~

Kết quả cho biết file log hiện tại và vị trí byte tiếp theo, cùng thông tin GTID nếu được bật. Hãy ghi lại tọa độ này cùng bản backup có liên quan.

Một cấu hình ví dụ trong phần [mysqld] của file cấu hình:

~~~ini
[mysqld]
server_id=101
log_bin=/var/lib/mysql/mysql-bin
binlog_format=ROW
sync_binlog=1
binlog_expire_logs_seconds=1209600
~~~

Ý nghĩa:

- **server_id:** định danh số duy nhất của máy chủ trong topology replication. Giá trị phải khác 0 và không trùng với server khác trong topology.
- **log_bin:** bật binary log và xác định basename/đường dẫn log.
- **binlog_format=ROW:** ghi thay đổi ở mức hàng. Đây thường là lựa chọn phù hợp cho replication và PITR vì log phản ánh hàng thực tế bị thay đổi, tránh một số khác biệt do thực thi lại câu SQL.
- **sync_binlog=1:** yêu cầu đồng bộ binlog xuống storage sau mỗi transaction commit. Thiết lập này tăng độ bền của binlog khi hệ thống gặp sự cố, đổi lại có thể tăng chi phí I/O.
- **binlog_expire_logs_seconds:** thời gian MySQL tự động hết hạn log. Ví dụ trên là 14 ngày; phải điều chỉnh theo chu kỳ backup, yêu cầu PITR, dung lượng và thời gian lưu trữ bản sao log bên ngoài.

Nếu cấu hình **binlog_do_db** hoặc **binlog_ignore_db**, hãy kiểm tra quy tắc lọc có loại bỏ database cần phục hồi hay không. Sự kiện không được ghi vào binlog sẽ không thể được tái tạo bằng PITR. Nếu lấy backup từ replica và muốn dùng binlog của replica để phục hồi các thay đổi nhận từ source, cần đánh giá cấu hình **log_replica_updates**.

Nếu cần dùng GTID, cấu hình còn liên quan đến:

~~~ini
gtid_mode=ON
enforce_gtid_consistency=ON
~~~

Bật GTID trên hệ thống đang chạy cần thực hiện theo lộ trình chuyển đổi tương thích với topology replication và phiên bản MySQL; không chỉ thêm hai dòng cấu hình rồi khởi động lại một cách tùy tiện. GTID giúp định danh transaction xuyên các máy chủ và hỗ trợ đồng bộ replication, nhưng vẫn cần metadata backup và chuỗi binlog đầy đủ để PITR.

Sau khi thay đổi cấu hình, khởi động lại nếu biến yêu cầu restart, rồi xác minh lại các giá trị. Bảo vệ quyền truy cập file log vì binlog có thể chứa dữ liệu nghiệp vụ, câu lệnh và giá trị nhạy cảm.

## 3. Giữ chuỗi binary log liên tục

Một bản backup chỉ có thể phát lại đến thời điểm mà chuỗi binlog tương ứng còn đầy đủ. Cần quản lý cả file đang hoạt động, file đã rotate và bản lưu trữ ngoài máy chủ.

Kiểm tra các file log:

~~~sql
SHOW BINARY LOGS;
~~~

Có thể xem các biến liên quan đến retention:

~~~sql
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'sync_binlog';
~~~

Những nguyên tắc vận hành quan trọng:

1. Lưu trữ binlog ra hệ thống backup độc lập theo chu kỳ đủ ngắn để giảm nguy cơ mất log khi máy chủ hoặc ổ đĩa gặp sự cố.
2. Giữ các file từ điểm bắt đầu của bản backup đến thời điểm PITR mục tiêu, không chỉ file mới nhất.
3. Kiểm tra tính liên tục của tên file, kích thước và checksum sau khi truyền sang nơi lưu trữ.
4. Bảo vệ file index, metadata backup, tọa độ file/position hoặc GTID cùng các file log.
5. Đặt retention đủ dài để bao phủ thời gian phát hiện sự cố, quyết định phục hồi và thực hiện restore.
6. Theo dõi dung lượng ổ đĩa, tốc độ sinh log và lỗi ghi binlog.

Khi lưu trữ log từ máy chủ đang chạy, tránh copy file binlog hiện hành bằng lệnh copy thông thường vì file vẫn có thể đang được ghi. Dùng cơ chế thu thập log hỗ trợ MySQL hoặc rotate log để đóng file trước khi archive; giữ đúng thứ tự và xác minh file đã hoàn tất. Không sửa nội dung file log sau khi đã lưu trữ.

Không xóa file binlog trực tiếp bằng lệnh hệ điều hành. Dùng lệnh quản trị MySQL khi cần purge, và chỉ xóa những log chắc chắn không còn cần cho replica hay cho bất kỳ bản backup nào còn trong thời hạn phục hồi.

Ví dụ, lệnh sau xóa các binary log cũ hơn một thời điểm:

~~~sql
PURGE BINARY LOGS BEFORE '2026-11-01 00:00:00';
~~~

Hoặc xóa các file đứng trước file được chỉ định:

~~~sql
PURGE BINARY LOGS TO 'mysql-bin.000150';
~~~

Lệnh purge là thao tác không thể đảo ngược đối với các file bị xóa. Trước khi chạy, phải xác nhận replica đã đọc xong các file đó, mọi bản backup còn hiệu lực đã có log cần thiết ở kho lưu trữ và không có kế hoạch PITR nào cần chúng. Tránh dùng RESET MASTER hoặc lệnh reset tương đương để dọn log trong quy trình vận hành thông thường.

## 4. Ghi lại tọa độ của bản sao nền

Để phát lại đúng phần thay đổi sau backup, cần biết vị trí mà bản sao nền đại diện. Có hai cách định danh phổ biến:

- **File và position:** ví dụ file mysql-bin.000120, position 456789. Đây là tọa độ byte trong một file binlog.
- **GTID set:** tập các transaction đã được thực thi, ví dụ một chuỗi UUID và khoảng sequence. GTID thuận tiện để đối chiếu transaction giữa các máy chủ.

Tọa độ phải được ghi nhận tại cùng điểm nhất quán với bản backup. Position thường biểu thị vị trí byte kế tiếp cần đọc trong file log, vì vậy replay bắt đầu từ tọa độ do công cụ backup ghi nhận. Không lấy vị trí binlog sau khi backup kết thúc rồi mặc định đó là vị trí bắt đầu replay; các transaction xảy ra trong lúc backup có thể đã hoặc chưa nằm trong snapshot tùy phương pháp.

### Với mysqldump

Các client MySQL hỗ trợ tùy chọn ghi tọa độ nguồn vào dump. Tên tùy chọn thay đổi theo thế hệ client:

- Client mới dùng **--source-data**.
- Client cũ có thể dùng **--master-data**.

Ví dụ với client hỗ trợ tên mới:

~~~bash
mysqldump \
  --user=backup_user \
  --password \
  --single-transaction \
  --source-data=2 \
  --routines \
  --events \
  --databases appdb \
  > appdb.sql
~~~

Tùy chọn này ghi tọa độ nguồn vào file dump dưới dạng comment để người vận hành có thể tra cứu. Để đồng bộ tọa độ với snapshot, mysqldump có thể cần lấy global read lock trong thời gian ngắn ở đầu quá trình. Hành vi cụ thể phụ thuộc phiên bản client và tùy chọn đang dùng; hãy kiểm tra tài liệu đúng phiên bản.

### Với physical backup

Công cụ physical backup thường tạo file metadata riêng ghi lại tọa độ binlog hoặc GTID. Ví dụ, Percona XtraBackup có thể tạo file thông tin như **xtrabackup_binlog_info**. Lưu file này cùng bản backup, checksum và nhật ký thực thi.

Với GTID, có thể ghi nhận trạng thái:

~~~sql
SELECT @@GLOBAL.gtid_executed;
~~~

GTID set này cần được liên hệ với trạng thái nền của backup. Hãy sử dụng metadata do công cụ backup tạo ra thay vì tự lấy GTID ở một thời điểm tùy ý sau khi quá trình sao lưu đã hoàn tất.

## 5. Quy trình PITR tổng quát

Giả sử có bản full backup lúc 01:00, binlog được lưu liên tục và một thao tác xóa nhầm xảy ra lúc 10:42. Mục tiêu là phục hồi trạng thái đến ngay trước transaction xóa nhầm.

Quy trình thực hiện trên một máy chủ phục hồi riêng hoặc instance cô lập:

1. **Chọn bản nền:** xác định full backup gần nhất nhưng có trước sự cố, kiểm tra backup đã hoàn tất/prepare và đọc metadata tọa độ.
2. **Chuẩn bị instance:** dùng phiên bản MySQL tương thích, cài plugin cần thiết, cấu hình keyring nếu dữ liệu mã hóa và dành đủ dung lượng.
3. **Khôi phục bản nền:** với backup logic thì import dump; với physical backup thì làm theo quy trình prepare và copy-back của công cụ. Ví dụ import dump vào instance phục hồi:

   ~~~bash
   mysql --host=127.0.0.1 --user=restore_admin --password < appdb.sql
   ~~~

   Dùng tài khoản có quyền phù hợp và xác nhận dump chỉ chứa các database cần khôi phục.
4. **Khởi động cô lập:** ngăn ứng dụng và người dùng ghi vào instance phục hồi. Không để replication tự động chạy nếu chưa xác định rõ mục tiêu.
5. **Thu thập binlog:** lấy toàn bộ file từ tọa độ bắt đầu đến file chứa thời điểm cần phục hồi. Kiểm tra không thiếu file giữa chuỗi.
6. **Xác định điểm dừng:** tìm transaction gây sự cố và vị trí kết thúc của transaction hợp lệ cuối cùng trước đó.
7. **Phát lại log:** dùng mysqlbinlog bắt đầu sau tọa độ đã nằm trong backup và dừng ở ranh giới transaction mục tiêu.
8. **Kiểm tra dữ liệu:** xác nhận bản ghi, số lượng hàng, cấu trúc và các ràng buộc nghiệp vụ.
9. **Chuyển dịch vụ:** chỉ sau khi chủ sở hữu dữ liệu xác nhận kết quả, mới chuyển ứng dụng sang instance phục hồi hoặc trích xuất phần dữ liệu cần thiết.

Không thực hiện PITR trực tiếp trên máy chủ nguồn đang chứa dữ liệu cần điều tra. Giữ nguyên máy chủ gốc và các bản backup/log để có thể kiểm tra lại nếu mốc thời gian chọn ban đầu chưa chính xác.

## 6. Phát lại binlog bằng mysqlbinlog

Công cụ mysqlbinlog đọc file binary log và xuất các câu lệnh/event để client MySQL thực thi. Với file log lưu cục bộ, có thể phát lại từ một vị trí bắt đầu:

~~~bash
mysqlbinlog \
  --start-position=456789 \
  mysql-bin.000120 \
  mysql-bin.000121 \
  mysql-bin.000122 \
  | mysql --binary-mode=1 \
      --host=127.0.0.1 \
      --user=restore_admin \
      --password
~~~

Lệnh trên là ví dụ minh họa. Vị trí bắt đầu chỉ áp dụng cho file đầu tiên trong danh sách; các file tiếp theo được đọc từ đầu. Hãy thay bằng tọa độ thật ghi trong metadata backup. Mật khẩu được nhập tương tác.

Nếu điểm dừng nằm trong file cuối cùng, dùng cả start-position và stop-position:

~~~bash
mysqlbinlog \
  --start-position=456789 \
  --stop-position=987654 \
  mysql-bin.000120 \
  mysql-bin.000121 \
  | mysql --binary-mode=1 \
      --host=127.0.0.1 \
      --user=restore_admin \
      --password
~~~

Ở ví dụ này, stop-position là vị trí trong file cuối cùng được chỉ định. Hãy chọn vị trí sau khi transaction hợp lệ cuối cùng đã hoàn tất và trước transaction gây sự cố. Không cắt giữa các event của cùng một transaction.

Để xem nội dung binlog trước khi phát lại:

~~~bash
mysqlbinlog \
  --base64-output=DECODE-ROWS \
  -vv \
  mysql-bin.000121 \
  > binlog-inspect.txt
~~~

Với row-based logging, dữ liệu hàng thường được lưu dưới dạng event nhị phân. Tùy chọn decode giúp hiển thị thông tin thay đổi ở dạng chú thích để người vận hành điều tra. File kết quả này phục vụ kiểm tra; không coi các dòng chú thích đã giải mã là một bản dump SQL có thể chạy độc lập.

Nếu cần dừng theo thời gian, mysqlbinlog có tùy chọn stop-datetime. Tuy nhiên, thời gian hiển thị có thể bị ảnh hưởng bởi múi giờ và cách diễn giải timestamp. Khi xác định được vị trí event, ưu tiên file/position và ranh giới transaction vì chúng rõ ràng hơn mốc thời gian dạng đồng hồ.

## 7. Xác định transaction gây sự cố

Khi có thao tác xóa hoặc cập nhật nhầm, cần xác định chính xác event nào đã gây ra thay đổi. Không nên chỉ chọn một mốc giờ gần đúng rồi phát lại toàn bộ.

Các bước điều tra:

1. Ghi lại thời điểm phát hiện, tài khoản thực hiện, ứng dụng/host liên quan và loại dữ liệu bị ảnh hưởng.
2. Tìm trong audit log, application log hoặc lịch sử triển khai để thu hẹp khoảng thời gian.
3. Dùng mysqlbinlog để xem các file liên quan; với row event, dùng chế độ decode để xem bảng và giá trị hàng.
4. Đối chiếu GTID, timestamp, file và position để xác định transaction.
5. Xác định transaction hợp lệ cuối cùng trước transaction gây lỗi.
6. Chạy thử trên bản phục hồi tạm, kiểm tra dữ liệu và xác nhận điểm dừng.

Ví dụ về cách nhận diện trong output đã giải mã:

~~~text
# at 456789
# GTID ...
# Query ...
BEGIN
### UPDATE appdb.orders
### WHERE
###   @1=...
### SET
###   @1=...
COMMIT
~~~

Đây là dạng minh họa rút gọn; output thực tế phụ thuộc loại event và phiên bản. Với DDL, binlog thường hiển thị câu lệnh SQL. Với row event, nội dung có thể được hiển thị dưới dạng các cột đánh số, nên cần đối chiếu schema để hiểu cột nào đã đổi.

Một transaction có thể chứa nhiều event. Chỉ phát lại hoặc dừng ở ranh giới an toàn của transaction. Nếu một lệnh nghiệp vụ tạo nhiều transaction, hãy kiểm tra thứ tự và quan hệ phụ thuộc giữa chúng trước khi quyết định mốc phục hồi.

## 8. PITR với GTID

GTID gán định danh cho mỗi transaction đã commit. Trong binlog, GTID giúp theo dõi transaction nào thuộc nguồn nào và tránh nhầm lẫn chỉ dựa trên vị trí byte.

Kiểm tra GTID đã thực thi:

~~~sql
SELECT @@GLOBAL.gtid_executed;
SELECT @@GLOBAL.gtid_purged;
~~~

Khi restore backup có GTID, trạng thái GTID của instance phục hồi cần tương thích với metadata của bản backup. Binlog phát lại phải bắt đầu sau các transaction đã nằm trong bản nền. Nếu phát lại một transaction đã được thực thi, MySQL có thể báo lỗi GTID đã tồn tại hoặc từ chối tiếp tục tùy trạng thái và cách chạy.

GTID hữu ích cho việc đối chiếu chuỗi transaction và phục hồi replication. Tuy nhiên, để dừng PITR trước một transaction sai, vẫn phải xác định transaction mục tiêu và chọn ranh giới dừng phù hợp. Không tự loại bỏ GTID tùy tiện để làm cho lệnh import chạy tiếp; điều đó có thể che giấu một khoảng trống dữ liệu.

Trong môi trường GTID, hãy lưu lại GTID set tại điểm backup, xác minh log liên tục, rồi làm theo quy trình phục hồi GTID tương ứng với topology. Nếu cần bỏ qua một transaction, trước hết đánh giá tác động và phụ thuộc của transaction đó trên bản sao thử nghiệm.

## 9. Những lỗi PITR thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Không lưu tọa độ backup | Không biết vị trí bắt đầu replay | Ghi file/position hoặc GTID cùng metadata backup |
| Thiếu một file binlog ở giữa chuỗi | Không thể tái tạo toàn bộ thay đổi | Kiểm tra kho lưu trữ và phục hồi file còn thiếu từ bản sao khác |
| Bắt đầu replay từ đầu log | Chạy lại transaction đã có trong backup | Dùng tọa độ bắt đầu chính xác |
| Dừng sau transaction gây lỗi | Sự cố vẫn xuất hiện trong bản phục hồi | Chọn vị trí trước transaction sai |
| Dừng giữa transaction | Có thể tạo trạng thái không đầy đủ hoặc lệnh lỗi | Dừng ở ranh giới transaction đã xác minh |
| Dùng binlog của máy chủ khác | Sai thứ tự hoặc GTID không tương thích | Xác minh nguồn, server UUID, GTID và metadata |
| Dùng timestamp không xét múi giờ | Phục hồi lệch thời điểm | Đối chiếu event, file và position |
| Purge log quá sớm | Mất khả năng PITR cho bản backup cũ | Thiết kế retention theo RPO/RTO và thời gian lưu backup |
| Restore trên máy chủ đang nhận traffic | Người dùng ghi thêm dữ liệu trong lúc phục hồi | Cô lập instance và chỉ mở dịch vụ sau khi xác minh |

## 10. Thiết kế lịch backup và mục tiêu phục hồi

PITR là một chuỗi quy trình, không chỉ là một lệnh mysqlbinlog. Hãy thiết kế lịch backup theo mục tiêu nghiệp vụ:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất. Binlog cần được ghi và chuyển ra kho lưu trữ đủ thường xuyên để đáp ứng mục tiêu này.
- **RTO (Recovery Time Objective):** thời gian tối đa để dịch vụ hoạt động lại. Kích thước full backup, tốc độ restore, số lượng log cần phát lại và năng lực hạ tầng đều ảnh hưởng RTO.
- **Full backup:** tạo điểm nền định kỳ, chọn lịch theo tốc độ tăng dữ liệu và thời gian restore.
- **Incremental backup:** nếu công cụ physical backup hỗ trợ, dùng để giảm lượng dữ liệu copy; vẫn cần chuỗi incremental hợp lệ và bước prepare theo đúng thứ tự.
- **Binary log archive:** chuyển log sang nơi lưu trữ độc lập, xác minh checksum và khả năng đọc lại.
- **Retention:** giữ full backup và binlog dài hơn thời gian tối đa có thể phát hiện sự cố và quyết định phục hồi.
- **Restore drill:** diễn tập khôi phục trên môi trường cô lập, đo thời gian và ghi nhận lỗi.

Một hệ thống có full backup mỗi đêm nhưng chỉ giữ binlog vài giờ sẽ không thể phục hồi đến các thời điểm xa hơn khoảng log còn lưu. Ngược lại, giữ binlog nhiều tuần mà không có full backup hợp lệ có thể khiến thời gian phát lại quá dài. Cần cân bằng giữa tần suất backup, lượng log, dung lượng và RTO.

## 11. Checklist trước và sau khi PITR

**Trước khi chạy:**

- [ ] Chọn bản full backup trước thời điểm sự cố và kiểm tra trạng thái hoàn tất/prepare.
- [ ] Đọc file/position hoặc GTID set từ metadata backup.
- [ ] Thu thập chuỗi binlog liên tục từ tọa độ đó đến thời điểm mục tiêu.
- [ ] Xác định transaction gây lỗi và vị trí dừng trước transaction đó.
- [ ] Chuẩn bị instance tương thích, keyring/plugin và dung lượng.
- [ ] Cô lập ứng dụng, replication và mọi luồng ghi ngoài ý muốn.
- [ ] Giữ nguyên nguồn dữ liệu ban đầu để có thể điều tra lại.

**Sau khi chạy:**

- [ ] Kiểm tra log thực thi và mã thoát của mysqlbinlog/mysql client.
- [ ] Xác nhận GTID/file position cuối cùng phù hợp với điểm dừng.
- [ ] Đối chiếu bản ghi bị ảnh hưởng và các bảng liên quan.
- [ ] Kiểm tra constraint, trigger, routine, event và quyền truy cập cần thiết.
- [ ] Để chủ sở hữu dữ liệu xác nhận kết quả trước khi chuyển traffic.
- [ ] Lưu lại thời gian phục hồi, bản backup, chuỗi binlog và điểm dừng đã dùng.

## 12. Ghi nhớ

- Full backup là trạng thái nền; binlog cung cấp các thay đổi xảy ra sau tọa độ nền.
- Ghi tọa độ file/position hoặc GTID tại đúng điểm nhất quán của backup.
- Lưu chuỗi binlog liên tục ở nơi độc lập và không purge khi còn bản backup cần chúng.
- Phát lại bằng mysqlbinlog theo đúng thứ tự; bắt đầu sau phần đã có trong backup.
- Dừng trước transaction gây sự cố và ở ranh giới transaction hợp lệ.
- GTID giúp nhận diện transaction và đồng bộ replication; nó không thay thế việc chọn đúng điểm dừng.
- Thử PITR trên instance cô lập, kiểm tra dữ liệu và đo RTO trước khi chuyển ứng dụng.

PITR đáng tin cậy khi bản sao nền, metadata tọa độ và chuỗi binary log tạo thành một đường phục hồi liên tục. Hãy diễn tập cả quy trình từ restore đến phát lại log và xác minh dữ liệu; chỉ khi thực hiện được đầy đủ các bước đó, mục tiêu RPO/RTO mới có cơ sở thực tế.

