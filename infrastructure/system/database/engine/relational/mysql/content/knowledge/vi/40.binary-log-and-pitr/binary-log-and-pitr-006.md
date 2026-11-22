# Rotate, expire và PURGE BINARY LOGS theo nhu cầu phục hồi/replication

Binary log ghi lại các sự kiện làm thay đổi dữ liệu trên MySQL. Nó là đầu vào quan trọng cho replication và point-in-time recovery (PITR). Vì vậy, quản trị vòng đời binary log phải cân bằng ba mục tiêu: giữ đủ lịch sử để phục hồi, giữ đủ log cho mọi replica theo kịp nguồn và giới hạn dung lượng lưu trữ.

Bài học thuộc module **DATABASE_MYSQL**, tập trung vào vận hành cơ sở dữ liệu quan hệ: đọc trạng thái log, chủ động rotate, cấu hình thời hạn tự động xóa, purge thủ công và lập kế hoạch dựa trên nhu cầu phục hồi. Các ví dụ dùng MySQL 8.0; một số tên lệnh và biến có khác biệt theo phiên bản.

## 1. Vai trò của binary log trong phục hồi và replication

Binary log là chuỗi tệp chứa các sự kiện thay đổi dữ liệu được máy chủ ghi nhận. Tùy **binlog_format**, các sự kiện có thể biểu diễn câu lệnh SQL hoặc thay đổi hàng dữ liệu. Các truy vấn chỉ đọc như **SELECT** thông thường không được ghi vào binary log.

Binary log phục vụ hai mục tiêu chính:

- **Replication:** replica đọc các sự kiện từ nguồn, lưu vào relay log rồi áp dụng lên dữ liệu của replica.
- **PITR:** sau khi phục hồi một full backup, DBA phát lại các sự kiện phát sinh sau thời điểm backup để đưa dữ liệu đến một thời điểm mong muốn.

Binary log không phải bản backup đầy đủ. Nó chỉ có ý nghĩa phục hồi khi đi cùng một bản backup nền phù hợp và tập log liên tục kể từ thời điểm backup đó. Nếu thiếu một tệp ở giữa chuỗi, không thể giả định các tệp sau vẫn đủ để tái tạo trạng thái chính xác.

Một máy chủ có binary logging thường tạo các tệp dạng **mysql-bin.000001**, **mysql-bin.000002**... và một tệp chỉ mục **.index** liệt kê các binary log. Tên file và đường dẫn phụ thuộc cấu hình **log_bin** và **log_bin_index**.

Kiểm tra trạng thái:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'log_bin_basename';
SHOW VARIABLES LIKE 'log_bin_index';
SHOW VARIABLES LIKE 'max_binlog_size';
SHOW BINARY LOGS;
~~~

Để xem tệp đang được ghi:

~~~sql
-- MySQL 8.0
SHOW MASTER STATUS;

-- MySQL 8.4
SHOW BINARY LOG STATUS;
~~~

Trong MySQL 8.4, **SHOW BINARY LOG STATUS** là tên mới thay cho **SHOW MASTER STATUS**. Hãy dùng cú pháp được hỗ trợ bởi phiên bản máy chủ.

## 2. Rotate binary log là gì?

Rotate là đóng tệp binary log hiện tại và mở một tệp mới với số thứ tự tiếp theo. Việc rotate tạo ranh giới tệp rõ ràng để quản lý, sao chép, lưu trữ hoặc xử lý log. Rotate không xóa lịch sử và không làm mất các sự kiện đã ghi trong tệp cũ.

MySQL tự động rotate trong các trường hợp phổ biến:

- Máy chủ khởi động hoặc khởi động lại.
- Máy chủ thực hiện thao tác flush log.
- Kích thước tệp hiện tại vượt ngưỡng **max_binlog_size**.

Giá trị mặc định của **max_binlog_size** trong MySQL 8.0 là 1 GB. Đây là ngưỡng kích hoạt rotate, không phải giới hạn tuyệt đối. Một transaction được ghi nguyên khối vào binary log, không bị tách giữa nhiều tệp, nên một transaction lớn có thể làm tệp vượt ngưỡng.

Xem cấu hình:

~~~sql
SHOW VARIABLES LIKE 'max_binlog_size';
~~~

Thay đổi ngưỡng động cho máy chủ đang chạy:

~~~sql
SET GLOBAL max_binlog_size = 536870912;
~~~

Ví dụ trên đặt ngưỡng 512 MB. Muốn lưu qua lần khởi động tiếp theo, có thể dùng **SET PERSIST** nếu phiên bản và chính sách quản lý cấu hình cho phép:

~~~sql
SET PERSIST max_binlog_size = 536870912;
~~~

Không cần rotate quá thường xuyên chỉ để tạo nhiều tệp nhỏ. Mỗi lần rotate làm tăng số lượng file cần theo dõi, sao lưu và chuyển giao. Chọn ngưỡng theo tốc độ phát sinh log, khả năng lưu trữ và cách vận hành.

## 3. Chủ động rotate bằng FLUSH BINARY LOGS

DBA có thể yêu cầu MySQL đóng binary log hiện tại và mở tệp tiếp theo:

~~~sql
FLUSH BINARY LOGS;
~~~

Tài khoản thực hiện cần quyền **RELOAD**. Có thể dùng **FLUSH LOGS** để flush các log được hỗ trợ, nhưng **FLUSH BINARY LOGS** thể hiện rõ ý định chỉ rotate binary log.

Ví dụ kiểm tra trước và sau:

~~~sql
SHOW BINARY LOGS;
SHOW MASTER STATUS;

FLUSH BINARY LOGS;

SHOW BINARY LOGS;
SHOW MASTER STATUS;
~~~

Trong MySQL 8.4, thay **SHOW MASTER STATUS** bằng **SHOW BINARY LOG STATUS**.

Các tình huống phù hợp để rotate thủ công:

- Tạo ranh giới log trước một đợt sao lưu hoặc chuyển log sang kho lưu trữ.
- Tạo file mới để thuận tiện thu thập log theo từng khoảng vận hành.
- Kiểm tra quy trình backup binary log hoặc quy trình giám sát dung lượng.
- Phối hợp với một quy trình bảo trì đã được lập lịch.

Rotate không đồng nghĩa với purge. **FLUSH BINARY LOGS** không có nghĩa là tệp cũ được xóa ngay; việc xóa phụ thuộc thời hạn tự động, lệnh purge thủ công và các ràng buộc liên quan.

## 4. Cấu hình thời hạn tự động xóa

MySQL có thể tự động xóa các binary log đã hết thời hạn. Trong MySQL 8.0, biến được khuyến nghị là **binlog_expire_logs_seconds**.

~~~sql
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'binlog_expire_logs_auto_purge';
SHOW VARIABLES LIKE 'expire_logs_days';
~~~

**binlog_expire_logs_seconds** tính thời hạn theo giây. Giá trị mặc định trong MySQL 8.0 là 2.592.000 giây, tương đương 30 ngày, nếu không có cấu hình khác ghi đè. Ví dụ, đặt thời hạn 14 ngày:

~~~sql
SET PERSIST binlog_expire_logs_seconds = 1209600;
~~~

Việc xóa tự động có thể diễn ra khi máy chủ khởi động và khi binary log được flush. Vì vậy, không nên hiểu rằng file sẽ biến mất chính xác tại giây thứ 14 ngày; thời điểm thực tế còn phụ thuộc thời điểm MySQL thực hiện kiểm tra purge.

### Bật hoặc tắt automatic purge

Từ MySQL 8.0.29, biến **binlog_expire_logs_auto_purge** điều khiển việc tự động purge:

~~~sql
-- Bật cơ chế tự động purge theo thời hạn
SET PERSIST binlog_expire_logs_auto_purge = ON;

-- Tắt automatic purge
SET PERSIST binlog_expire_logs_auto_purge = OFF;
~~~

Khi biến này là **OFF**, MySQL không tự động purge theo thời hạn, nhưng lệnh **PURGE BINARY LOGS** thủ công vẫn có hiệu lực. Trên MySQL 8.0.28 trở xuống, biến này chưa có; cách tắt automatic purge là cấu hình **binlog_expire_logs_seconds = 0** theo quy tắc phiên bản.

### Biến expire_logs_days cũ

**expire_logs_days** là biến cũ, đã deprecated trong MySQL 8.0. Biến thay thế là **binlog_expire_logs_seconds**. Nếu cả hai biến có giá trị khác 0 khi khởi động, **binlog_expire_logs_seconds** được ưu tiên và MySQL phát cảnh báo. Tại runtime, không thể đặt cả hai thành giá trị khác 0 cùng lúc. Khi quản trị máy chủ cũ, cần kiểm tra cả hai để tránh hiểu nhầm giá trị retention đang có hiệu lực.

Không đặt thời hạn ngắn chỉ để giải quyết đầy đĩa. Trước khi giảm retention, tính lại thời gian cần cho PITR, độ trễ replica và thời gian gián đoạn tối đa có thể xảy ra.

## 5. PURGE BINARY LOGS thủ công

**PURGE BINARY LOGS** xóa các tệp binary log cũ và đồng thời cập nhật tệp chỉ mục **.index**. Đây là cách được MySQL hỗ trợ để xóa log theo tên hoặc thời điểm.

### Xóa theo tên tệp

~~~sql
PURGE BINARY LOGS TO 'mysql-bin.000125';
~~~

Lệnh trên xóa các binary log đứng trước **mysql-bin.000125**; tệp **mysql-bin.000125** được giữ lại và trở thành tệp đầu tiên còn trong danh sách.

### Xóa theo thời điểm

~~~sql
PURGE BINARY LOGS BEFORE '2026-11-01 00:00:00';
~~~

Lệnh trên xóa các tệp có thời điểm trước mốc chỉ định theo quy tắc của MySQL. Hãy kiểm tra danh sách file và thời điểm trước khi chạy; không suy ra rằng mọi file có tên số nhỏ đều đã an toàn để xóa.

Tài khoản thực hiện cần quyền **BINLOG_ADMIN** trong MySQL 8.0. Không xóa file binary log bằng thao tác filesystem như **rm** hoặc **Remove-Item**. Làm vậy có thể khiến tệp **.index** vẫn tham chiếu đến file đã mất, gây lỗi khi MySQL quản lý hoặc purge log tiếp theo.

**PURGE BINARY LOGS** không xóa tệp binary log hiện tại đang được ghi. Nếu tên file đích không tồn tại hoặc mốc thời gian không hợp lệ, lệnh có thể thất bại. Luôn kiểm tra bằng **SHOW BINARY LOGS** sau khi purge.

### Phân biệt PURGE với RESET

Không dùng lệnh reset để dọn log định kỳ. Trong MySQL 8.0, **RESET MASTER** xóa toàn bộ binary log và đặt lại lịch sử GTID; trong MySQL 8.4, lệnh thay thế là **RESET BINARY LOGS AND GTIDS**. Lệnh reset có phạm vi tác động rộng hơn purge, không dành cho bảo trì thông thường và không được dùng khi replica đang chạy. Chỉ cân nhắc trong quy trình khởi tạo lại một môi trường độc lập đã được kiểm soát, sau khi hiểu rõ ảnh hưởng đến GTID và replication.

## 6. Giữ binary log đủ lâu cho replica

Replica cần đọc binary log từ nguồn để bắt kịp dữ liệu. Nếu nguồn purge mất file mà replica chưa kịp đọc, replica có thể không tiếp tục replication được khi kết nối lại. Đây là rủi ro thường gặp khi replica bị dừng lâu, mạng gián đoạn hoặc tốc độ apply thấp.

Trước khi purge, kiểm tra trạng thái trên từng replica:

~~~sql
SHOW REPLICA STATUS\G
~~~

Đọc các thông tin như:

- **Source_Log_File**: file binary log nguồn mà I/O thread đang đọc.
- **Read_Source_Log_Pos**: vị trí đã đọc trong file nguồn.
- **Replica_IO_Running** và **Replica_SQL_Running**: trạng thái luồng nhận và luồng áp dụng.
- **Seconds_Behind_Source**: độ trễ ước tính của replica; giá trị **NULL** không có nghĩa replica đang đồng bộ tốt.
- Lỗi I/O và lỗi SQL gần nhất để phát hiện replica đang dừng hoặc không theo kịp.

Trên nguồn, xem danh sách file:

~~~sql
SHOW BINARY LOGS;
~~~

Quy trình chọn mốc purge an toàn:

1. Kiểm tra tất cả replica, bao gồm replica đang offline hoặc chỉ được bật theo lịch.
2. Xác định file nguồn sớm nhất mà mỗi replica còn cần đọc.
3. Tìm file sớm nhất trong số các replica đó.
4. Sao lưu các binary log dự định xóa nếu còn cần cho phục hồi hoặc điều tra.
5. Chỉ purge các file đứng trước file mục tiêu.
6. Theo dõi trạng thái replication sau khi purge.

Ví dụ, nếu replica chậm nhất còn cần **mysql-bin.000120**, chỉ có thể purge các file đứng trước file này:

~~~sql
PURGE BINARY LOGS TO 'mysql-bin.000120';
~~~

MySQL không xóa file đang được một replica đang kết nối sử dụng và các file mới hơn nó; cảnh báo có thể xuất hiện nếu một số file chưa thể xóa. Tuy nhiên, cơ chế này không bảo vệ một replica đang offline mà chưa đọc những file cũ. Khi replica đó kết nối lại, nếu log cần thiết đã bị purge, cần khởi tạo lại replica từ một backup phù hợp hoặc quy trình phục hồi khác.

Đừng dựa duy nhất vào **Seconds_Behind_Source** để quyết định purge. Hãy kiểm tra trạng thái luồng nhận, luồng áp dụng, file/position, thời gian offline tối đa và lịch vận hành thực tế của từng replica.

## 7. Giữ binary log đủ lâu cho PITR

PITR thường gồm hai phần:

1. Phục hồi full backup để đưa database về trạng thái tại thời điểm backup.
2. Phát lại các binary log sau thời điểm đó đến mốc phục hồi mong muốn.

Do đó, retention phải bao phủ toàn bộ khoảng thời gian cần phục hồi. Ví dụ, nếu full backup được tạo mỗi Chủ nhật và tổ chức muốn phục hồi bất kỳ thời điểm nào trong 21 ngày gần nhất, phải giữ log liên tục ít nhất từ thời điểm full backup cũ nhất còn được coi là hợp lệ, cộng thêm khoảng dự phòng vận hành.

Lập kế hoạch dung lượng theo tốc độ sinh log thực tế:

**Dung lượng dự kiến ≈ dung lượng binlog trung bình mỗi ngày × số ngày lưu × hệ số dự phòng**

Ví dụ, nếu hệ thống tạo trung bình 12 GB binlog/ngày và cần giữ 21 ngày, dung lượng cơ sở khoảng 252 GB trước khi cộng hệ số dự phòng. Hãy đo từ nhiều ngày có workload khác nhau; ngày chạy batch hoặc import lớn có thể tạo log cao hơn nhiều mức trung bình.

Ngoài retention trên máy chủ, cần xem xét sao chép binary log sang vị trí lưu trữ độc lập. Nếu ổ đĩa chứa data directory và binlog cùng hỏng, bản log tại chỗ có thể mất cùng dữ liệu. Có thể dùng **mysqlbinlog** để đọc và sao lưu binary log từ máy chủ nguồn; cần bảo vệ bản sao và kiểm tra khả năng đọc lại.

## 8. Dùng mysqlbinlog để xem và xử lý log

**mysqlbinlog** đọc binary log và chuyển các event sang dạng có thể kiểm tra hoặc phát lại. Ví dụ đọc một file:

~~~bash
mysqlbinlog mysql-bin.000120
~~~

Để xem chi tiết row event ở dạng dễ đọc:

~~~bash
mysqlbinlog --base64-output=DECODE-ROWS -vv mysql-bin.000120
~~~

Có thể lọc theo thời gian hoặc vị trí để điều tra:

~~~bash
mysqlbinlog --start-datetime="2026-11-18 08:00:00" --stop-datetime="2026-11-18 10:30:00" mysql-bin.000120
~~~

Để sao lưu binary log từ xa ở dạng nhị phân, **mysqlbinlog** hỗ trợ **--read-from-remote-server** và **--raw**. Khi đọc log mã hóa, cần đọc qua kết nối đến máy chủ thay vì mở trực tiếp file mã hóa trên filesystem. Bảo vệ kết nối bằng TLS và dùng tài khoản có quyền replication phù hợp.

Không chỉnh sửa hoặc xóa tùy tiện nội dung binary log. Nếu cần loại bỏ một transaction sai trong quá trình PITR, hãy phân tích event, chọn chính xác điểm dừng và thử phục hồi trên môi trường tách biệt trước khi thực hiện trên hệ thống thật.

## 9. Ví dụ phục hồi đến một thời điểm cụ thể

Giả sử có full backup lúc 01:00 ngày 18/11 và cần phục hồi database đến 10:30 cùng ngày, trước khi một thao tác xóa nhầm xảy ra.

**Bước 1: phục hồi full backup**

Phục hồi full backup vào máy chủ khôi phục riêng biệt theo hướng dẫn của công cụ tạo backup. Ghi nhận tên file và vị trí binary log hoặc GTID mà backup đã lưu lại.

**Bước 2: xác định file và vị trí cần phát lại**

Dùng **SHOW BINARY LOGS**, metadata backup và **mysqlbinlog** để xác định chuỗi log bắt đầu ngay sau điểm backup. Kiểm tra các event quanh thời điểm 10:30 để tìm transaction cần loại trừ.

**Bước 3: tạo bản xem trước**

~~~bash
mysqlbinlog --start-datetime="2026-11-18 01:00:00" --stop-datetime="2026-11-18 10:30:00" mysql-bin.000120 mysql-bin.000121
~~~

Đây là ví dụ minh họa; phải thay tên file, thời gian và điểm bắt đầu bằng metadata thực của backup. Nếu đã xác định được event position chính xác, ưu tiên dùng **--start-position** và **--stop-position** để kiểm soát ranh giới phát lại. Mốc thời gian chỉ là công cụ định vị ban đầu và cần kiểm tra event thực tế.

**Bước 4: phát lại trên máy chủ khôi phục**

~~~bash
mysqlbinlog --start-position=154 --stop-position=987654 mysql-bin.000120 | mysql --binary-mode -u restore_user -p
~~~

Nếu cần xử lý nhiều file, truyền chúng theo thứ tự trong cùng một lệnh **mysqlbinlog** và một kết nối **mysql**. Điều này giữ ngữ cảnh giữa các file, ví dụ khi có temporary table được tạo trong file trước và được sử dụng trong file sau.

Không sao chép nguyên ví dụ vị trí trên vào hệ thống thật. Vị trí phải trỏ đúng ranh giới event đã được xác minh; điểm dừng sai có thể phát lại transaction gây lỗi hoặc bỏ sót transaction hợp lệ.

**Bước 5: xác minh**

Kiểm tra bảng, số lượng dòng, dữ liệu nghiệp vụ và tính toàn vẹn tham chiếu. Chạy truy vấn kiểm tra ứng dụng trên máy chủ khôi phục trước khi quyết định chuyển dữ liệu trở lại production.

## 10. Các lỗi vận hành thường gặp

### Đĩa đầy do binary log tăng nhanh

Kiểm tra tốc độ sinh log, dung lượng file, retention, replica lag và tình trạng PITR. Nếu cần giải phóng dung lượng, xác định các file cũ nhất có thể xóa theo cả yêu cầu replica và backup. Purge theo mốc an toàn, sau đó điều chỉnh retention hoặc dung lượng lưu trữ. Không xóa file trực tiếp trên filesystem.

### Replica báo thiếu binary log

Thông báo lỗi thường cho biết replica yêu cầu một file nguồn không còn tồn tại. Kiểm tra file/position mà replica yêu cầu, danh sách file còn lại trên nguồn và backup có thể dùng để tái tạo replica. Nếu log cần thiết đã mất, cách khôi phục đáng tin cậy thường là tạo lại replica từ một backup nhất quán rồi cấu hình replication từ điểm tương ứng.

### Không thể purge một số file

Kiểm tra file đang được replica sử dụng, file hiện tại, trạng thái backup lock và quyền **BINLOG_ADMIN**. Từ MySQL 8.0.28, purge bị chặn khi **LOCK INSTANCE FOR BACKUP** đang có hiệu lực. Không xử lý bằng cách sửa file **.index** trong lúc máy chủ đang chạy.

### PITR không phát lại được log

Kiểm tra chuỗi file có liên tục không, file có bị mã hóa không, tài khoản đọc log có đủ quyền không và điểm bắt đầu có khớp metadata backup không. Xác nhận phiên bản **mysqlbinlog** tương thích với log. Nếu dùng event position, bảo đảm vị trí bắt đầu và kết thúc trùng ranh giới event hợp lệ.

### Retention tự động không như mong đợi

Kiểm tra **binlog_expire_logs_seconds**, **binlog_expire_logs_auto_purge** và biến cũ **expire_logs_days**. Việc xóa tự động được kiểm tra khi startup và khi flush log; file chưa nhất thiết bị xóa đúng thời điểm hết hạn. Nếu cần xóa ngay một tập file đã được xác nhận an toàn, dùng **PURGE BINARY LOGS**.

## 11. Quy trình vận hành đề xuất

**Theo dõi hằng ngày**

- Ghi nhận dung lượng binary log và tốc độ phát sinh theo ngày.
- Theo dõi replica lag, trạng thái I/O thread và SQL thread.
- Cảnh báo khi replica offline lâu hơn ngưỡng dự kiến.
- Theo dõi khoảng thời gian log còn lại so với backup cũ nhất cần phục hồi.

**Khi rotate hoặc purge**

- Xem danh sách log và trạng thái file hiện tại.
- Xác định các replica còn cần log.
- Xác định backup và cửa sổ PITR cần giữ.
- Sao lưu file trước khi purge nếu còn nhu cầu lưu trữ hoặc điều tra.
- Chạy purge theo tên file hoặc thời điểm, sau đó kiểm tra danh sách còn lại.
- Ghi nhận người thực hiện, mốc xóa và kết quả replication.

**Rà soát định kỳ**

- Thử phục hồi full backup và phát lại binlog đến một mốc xác định.
- Kiểm tra bản sao binlog ngoài máy chủ.
- Điều chỉnh retention theo RPO, RTO, lịch backup, replica lag và dung lượng.
- Kiểm tra quyền truy cập, mã hóa và chính sách lưu giữ log.

Checklist:

- [ ] Binary logging đã bật và đường dẫn lưu log đã được xác định.
- [ ] Đã biết cách xem file hiện tại và danh sách binary log.
- [ ] **max_binlog_size** phù hợp với tốc độ phát sinh và vận hành.
- [ ] **binlog_expire_logs_seconds** phản ánh đúng cửa sổ PITR.
- [ ] Đã kiểm tra **binlog_expire_logs_auto_purge** nếu phiên bản hỗ trợ.
- [ ] Mọi replica đã được kiểm tra trước khi purge.
- [ ] Đã tính đến replica offline và replica có lịch chạy riêng.
- [ ] Chỉ dùng **PURGE BINARY LOGS** để xóa log, không xóa file thủ công.
- [ ] Có bản sao binary log độc lập nếu yêu cầu phục hồi cần đến.
- [ ] Đã diễn tập phục hồi đến một thời điểm cụ thể.

## Kết luận

Rotate tạo tệp binary log mới để chia lịch sử thành các phần dễ quản lý. Expire tự động giới hạn thời gian lưu theo chính sách, còn **PURGE BINARY LOGS** cho phép DBA xóa các tệp đã xác định an toàn. Trước mọi thao tác purge, hãy kiểm tra đồng thời cửa sổ PITR và nhu cầu của tất cả replica. Một chính sách tốt cần dựa trên tốc độ phát sinh log, thời gian backup, replica lag, dung lượng lưu trữ và kết quả diễn tập phục hồi.

## Tài liệu tham khảo

- [MySQL 8.0 Reference Manual — The Binary Log](https://dev.mysql.com/doc/refman/8.0/en/binary-log.html)
- [MySQL 8.0 Reference Manual — Binary Logging Options and Variables](https://dev.mysql.com/doc/refman/8.0/en/replication-options-binary-log.html)
- [MySQL 8.0 Reference Manual — PURGE BINARY LOGS Statement](https://dev.mysql.com/doc/refman/8.0/en/purge-binary-logs.html)
- [MySQL 8.0 Reference Manual — Server Log Maintenance](https://dev.mysql.com/doc/refman/8.0/en/log-file-maintenance.html)
- [MySQL 8.0 Reference Manual — Point-in-Time Recovery Using Binary Log](https://dev.mysql.com/doc/refman/8.0/en/point-in-time-recovery-binlog.html)
- [MySQL 8.4 Reference Manual — RESET BINARY LOGS AND GTIDS](https://dev.mysql.com/doc/refman/8.4/en/reset-binary-logs-and-gtids.html)
