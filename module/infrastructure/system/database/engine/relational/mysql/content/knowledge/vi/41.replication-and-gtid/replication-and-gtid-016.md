# Đối soát dữ liệu, resync và điều kiện tái tạo replica

Một replica có thể vẫn kết nối được với source nhưng dữ liệu đã không còn khớp. Nguyên nhân có thể là replication lag, applier dừng, transaction bị bỏ qua, ghi trực tiếp nhầm vào replica, thay đổi schema không đồng nhất hoặc replica đã mất các binary log cần thiết để bắt kịp source. Mỗi trường hợp đòi hỏi cách xử lý khác nhau.

Đối soát dữ liệu (data reconciliation) là quá trình xác định bản dữ liệu nào được xem là chuẩn, đo mức chênh lệch và quyết định cách đưa replica về trạng thái đúng. Resync là đồng bộ lại dữ liệu hoặc luồng replication. Rebuild là tạo lại replica từ một bản sao nhất quán của source hoặc từ backup đã xác minh. Bài học này đặt các thao tác đó trong phạm vi vận hành MySQL, nơi cần kết hợp hiểu biết về transaction, khóa, backup, GTID và kiểm soát truy cập.

## 1. Phân biệt lag, lỗi replication và data drift

Không phải mọi replica chậm đều bị sai dữ liệu vĩnh viễn. Trước khi sửa, cần phân biệt ba tình huống:

| Tình huống | Dấu hiệu | Ý nghĩa |
|---|---|---|
| Replication lag | Receiver và applier hoạt động, nhưng replica chưa áp dụng hết transaction mới | Dữ liệu có thể chỉ đang chậm; cần cho luồng replication bắt kịp |
| Replication stopped hoặc broken | Receiver hoặc applier dừng, có lỗi I/O hay SQL, relay log không tiến triển | Replica không tiếp tục nhận hoặc áp dụng được sự kiện |
| Data drift (dữ liệu lệch) | Luồng replication có thể đang chạy nhưng một số hàng, bảng hoặc schema khác source | Có thể đã có ghi ngoài luồng, transaction bị bỏ qua hoặc thay đổi không được sao chép |

Ví dụ, source đã ghi 10.000 đơn hàng mới trong khi replica mới áp dụng 9.800 đơn. Nếu 200 đơn còn lại vẫn có trong binlog và applier hoạt động, đây có thể chỉ là lag. Ngược lại, nếu receiver và applier đều báo đang chạy nhưng một đơn hàng có số tiền khác nhau giữa hai máy, cần điều tra data drift.

Một số nguyên nhân thường gặp:

- Ứng dụng hoặc người vận hành ghi trực tiếp vào replica.
- Tài khoản quản trị thay đổi dữ liệu trên replica để xử lý tạm thời nhưng không ghi nhận.
- Một transaction replication bị bỏ qua hoặc xử lý lỗi theo cách làm mất sự kiện.
- Bộ lọc replication khiến một schema hoặc bảng không được sao chép như dự kiến.
- Schema giữa source và replica khác nhau, khiến sự kiện không được áp dụng đúng.
- Replica bị gián đoạn lâu hơn thời gian lưu binlog trên source.
- Restore nhầm backup, sai thời điểm hoặc sai GTID baseline.
- Có nhiều nguồn ghi hoặc topology chuyển vai trò không hoàn tất, tạo ra transaction chỉ tồn tại ở một nhánh.

Không nên kết luận dữ liệu đã đồng nhất chỉ dựa trên việc hai thread replication đang chạy hoặc chỉ số lag bằng 0. Trạng thái luồng cho biết replication đang tiến triển; nó không chứng minh mọi hàng và schema đều giống source.

## 2. Xác định nguồn dữ liệu chuẩn và bảo toàn hiện trạng

Trước khi resync, phải xác định máy chủ nào là nguồn dữ liệu có thẩm quyền. Trong topology một source, source đang nhận ghi hợp lệ thường là điểm tham chiếu. Sau failover, source mới được chọn theo runbook mới là điểm ghi chuẩn. Nếu có split-brain hoặc nhiều máy cùng nhận ghi, không được tự chọn một máy dựa trên tên host; cần xác định transaction hợp lệ, thời điểm chuyển vai trò và dữ liệu đã được xác nhận với ứng dụng.

Thực hiện preflight theo trình tự:

1. Xác định source hiện tại, các replica liên quan, vai trò từng máy và endpoint mà ứng dụng đang sử dụng.
2. Kiểm tra có máy nào nhận ghi trực tiếp ngoài source hay không. Nếu phát hiện, hạn chế ghi mới theo quy trình sự cố và bảo toàn log.
3. Thu thập trạng thái replication, GTID, binary log, relay log, lỗi gần nhất và log máy chủ.
4. Ghi lại cấu hình replication filter, schema, phiên bản MySQL, engine bảng và các thay đổi gần đây.
5. Tạo backup hoặc snapshot có thể khôi phục trước khi sửa dữ liệu. Giữ lại bản sao hiện trạng để có thể phân tích transaction lệch.
6. Xác định cửa sổ bảo trì hoặc phương pháp tạo snapshot nhất quán để việc so sánh không bị nhiễu bởi các ghi đang diễn ra.

Nếu source vẫn nhận ghi trong khi đang so sánh từng bảng, kết quả ở hai máy có thể đại diện cho hai thời điểm khác nhau. Với bảng InnoDB, có thể sử dụng consistent snapshot hoặc công cụ checksum có cơ chế xử lý snapshot phù hợp. Nếu cần đối chiếu toàn bộ dữ liệu ở cùng một mốc, hãy phối hợp snapshot, khóa ghi hoặc quy trình backup nhất quán theo đúng công cụ và mức tải của hệ thống.

Không xóa relay log, reset trạng thái GTID, bỏ qua transaction lỗi hoặc chạy lệnh đồng bộ hai chiều trước khi đã thu thập hiện trạng. Các thao tác đó có thể làm mất bằng chứng cần thiết để tìm nguyên nhân.

## 3. Đối chiếu trạng thái replication

Trên replica, kiểm tra trạng thái bằng cú pháp phù hợp phiên bản:

~~~sql
SHOW REPLICA STATUS\G
~~~

Một số bản MySQL cũ sử dụng:

~~~sql
SHOW SLAVE STATUS\G
~~~

Các trường cần xem gồm:

| Trường | Câu hỏi cần trả lời |
|---|---|
| Replica_IO_Running | Receiver có đang lấy sự kiện từ source không? |
| Replica_SQL_Running | Applier có đang thực thi relay log không? |
| Seconds_Behind_Source | Replica đang chậm khoảng bao lâu theo chỉ số ước tính? |
| Last_IO_Error | Vì sao receiver gần nhất không thể tiếp tục? |
| Last_SQL_Error | Vì sao applier gần nhất không thể áp dụng sự kiện? |
| Source_Log_File và Read_Source_Log_Pos | Receiver đã đọc đến vị trí nào trong binlog? |
| Relay_Source_Log_File và Exec_Source_Log_Pos | Applier đã áp dụng đến vị trí source nào? |
| Retrieved_Gtid_Set | Những GTID nào đã được nhận? |
| Executed_Gtid_Set | Những GTID nào đã được thực thi trên máy chủ? |

Tên trường cụ thể có thể khác theo phiên bản và câu lệnh hiển thị. Hãy xem toàn bộ kết quả, không chỉ một trường lag. Nếu receiver và applier đều chạy nhưng Last_SQL_Error còn lưu lỗi cũ, cần xác định lỗi đó đã được xử lý hay chưa.

Trên source và replica, thu thập tập GTID đã thực thi:

~~~sql
SELECT @@GLOBAL.gtid_executed;
SELECT @@GLOBAL.gtid_purged;
~~~

Giả sử đã chép tập GTID của source và replica vào hai biến trong phiên kiểm tra, có thể so sánh bằng các hàm GTID:

~~~sql
SET @source_gtids = '3E11FA47-71CA-11E1-9E33-C80AA9429562:1-1200';
SET @replica_gtids = '3E11FA47-71CA-11E1-9E33-C80AA9429562:1-1180';

SELECT GTID_SUBTRACT(@source_gtids, @replica_gtids)
  AS transactions_missing_on_replica;

SELECT GTID_SUBTRACT(@replica_gtids, @source_gtids)
  AS transactions_extra_on_replica;
~~~

Chuỗi GTID ở trên chỉ minh họa cách đọc kết quả; phải thay bằng tập GTID thực tế của hệ thống. Nếu tập GTID source trừ tập GTID replica còn kết quả, replica chưa thực thi một số transaction đã có trên source. Nếu tập GTID replica trừ tập GTID source còn kết quả, replica có transaction không xuất hiện trong tập của source đang được so sánh. Đây có thể là transaction phát sinh ngoài luồng replication hoặc dấu vết của một topology trước đó; cần điều tra nguồn gốc trước khi loại bỏ.

GTID set phản ánh danh tính transaction, không phải checksum nội dung bảng. Hai máy có thể có tập GTID tương tự nhưng dữ liệu đã bị thay đổi ngoài luồng; ngược lại, các máy trong topology phức tạp có thể có tập GTID khác nhau vì nhận transaction từ nhiều source. Hãy diễn giải theo cấu trúc topology và lịch sử failover thực tế.

Khi cần chờ replica thực thi đến một tập GTID đã biết, MySQL cung cấp hàm:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET('3E11FA47-71CA-11E1-9E33-C80AA9429562:1-1200', 30);
~~~

Hàm chờ tối đa số giây được chỉ định để tập GTID được thực thi trên máy chủ hiện tại. Kết quả 0 nghĩa là đã chờ thành công; 1 nghĩa là hết thời gian chờ. Ứng dụng cần xử lý timeout, chẳng hạn đọc từ source hoặc báo lỗi phù hợp, thay vì giả định replica đã theo kịp.

## 4. Đối soát dữ liệu ở cấp schema, bảng và hàng

Đối soát nên bắt đầu từ phạm vi rộng rồi thu hẹp:

**Schema:** so sánh tên bảng, cột, kiểu dữ liệu, collation, index, constraint, trigger, view, routine và partition. Một replica có schema khác source có thể gặp lỗi khi áp dụng sự kiện hoặc trả kết quả khác dù một số hàng vẫn khớp.

**Bảng:** so sánh số hàng, min/max của khóa chính, tổng hợp theo phân vùng nghiệp vụ và checksum theo từng đoạn khóa. Số lượng hàng bằng nhau không chứng minh nội dung bằng nhau; hai bảng có thể có cùng số hàng nhưng giá trị khác.

**Hàng:** dùng khóa chính hoặc khóa duy nhất để xác định bản ghi thiếu, thừa hoặc khác giá trị. Với bảng không có khóa ổn định, việc ghép cặp hàng và đồng bộ có thể phức tạp, tốn tài nguyên và dễ tạo kết quả sai.

Các truy vấn tổng hợp có thể giúp khoanh vùng ban đầu:

~~~sql
SELECT
  COUNT(*) AS row_count,
  MIN(id) AS min_id,
  MAX(id) AS max_id
FROM app_db.orders;
~~~

Chạy cùng truy vấn trên source và replica trong một snapshot tương đương. Đây chỉ là phép kiểm tra sơ bộ; không dùng ba giá trị này làm bằng chứng dữ liệu hoàn toàn đồng nhất.

Với bảng lớn, checksum theo từng chunk thường hiệu quả hơn việc kéo toàn bộ bảng về máy khách. Percona Toolkit cung cấp công cụ như pt-table-checksum để so sánh checksum theo phạm vi và ghi nhận chênh lệch qua replication. Công cụ cần được cấu hình phù hợp với phiên bản MySQL, topology, replication filter và tải hệ thống. Hãy đọc kế hoạch chạy, chọn thời điểm ít tải và theo dõi tác động trước khi áp dụng cho toàn bộ bảng.

Khi checksum báo lệch, cần xác định chính xác chunk, khóa và cột bị khác. Không chạy đồng bộ mù quáng trên mọi bảng. Với bảng lớn, việc đọc và tính checksum cũng tạo tải I/O, CPU và có thể kéo dài transaction hoặc snapshot.

## 5. Chọn cách sửa: catch up, sửa có mục tiêu hay rebuild

Quyết định phụ thuộc vào nguyên nhân, mức độ lệch và khả năng lấy lại transaction:

| Điều kiện phát hiện | Hướng xử lý phù hợp |
|---|---|
| Chỉ lag, receiver/applier hoạt động và binlog cần thiết còn tồn tại | Cho replication tiếp tục; theo dõi đến khi GTID và dữ liệu bắt kịp |
| Receiver hoặc applier dừng do lỗi cấu hình/kết nối có thể khắc phục | Sửa nguyên nhân, sau đó khởi động thread theo runbook |
| Một số hàng lệch, source chuẩn rõ ràng, schema tương thích và phạm vi nhỏ | Sửa dữ liệu có mục tiêu từ source sang replica, rồi checksum lại |
| Nhiều bảng lệch, nguồn gốc transaction không rõ hoặc có nhiều ghi ngoài luồng | Dừng và điều tra; thường cần dựng lại replica từ bản sao nhất quán |
| Replica thiếu binlog cần thiết vì source đã purge | Không thể chỉ restart để lấy lại sự kiện; cần provision lại hoặc phục hồi từ backup phù hợp |
| Có errant transaction hoặc split-brain sau failover | Xác định nhánh dữ liệu chuẩn và lập kế hoạch dựng lại; không xóa GTID để che giấu chênh lệch |

### 5.1. Chỉ cần cho replication bắt kịp

Nếu dữ liệu không bị drift và source vẫn giữ binlog cần thiết, xử lý lỗi kết nối hoặc lỗi cấu hình rồi tiếp tục replication là phương án ít tác động nhất. Sau khi sửa nguyên nhân, kiểm tra trạng thái và khởi động receiver/applier nếu chúng đang dừng:

~~~sql
START REPLICA;
SHOW REPLICA STATUS\G
~~~

Không chạy START REPLICA liên tục khi chưa hiểu lỗi. Ví dụ, sai mật khẩu, thiếu quyền replication, source không còn binlog hoặc lỗi dữ liệu sẽ không tự biến mất sau mỗi lần khởi động.

### 5.2. Sửa chênh lệch có mục tiêu

Nếu chỉ một số hàng bị lệch và source được xác nhận là bản chuẩn, có thể đồng bộ các hàng đó theo hướng source sang replica. Trước khi sửa:

1. Backup dữ liệu replica và ghi lại khóa chính của các hàng lệch.
2. Ngăn ứng dụng hoặc người vận hành ghi trực tiếp vào replica trong thời gian sửa.
3. Xác định đầy đủ cột, quan hệ khóa ngoại, trigger và các bảng liên quan.
4. Chọn công cụ có thể giới hạn chính xác bảng, khóa và chiều đồng bộ.
5. Thực hiện trong cửa sổ kiểm soát, theo dõi số hàng thay đổi và lỗi.
6. Chạy lại checksum và kiểm tra nghiệp vụ sau khi sửa.

pt-table-sync là một công cụ trong Percona Toolkit có thể hỗ trợ đồng bộ hàng giữa các máy MySQL. Cần xác định rõ source là máy chuẩn, replica là máy đích và lựa chọn chế độ kiểm tra trước khi ghi. Không chạy lệnh đồng bộ hai chiều hoặc đảo chiều source/replica tùy tiện; thao tác sai hướng có thể ghi dữ liệu cũ đè lên dữ liệu đúng.

Nếu bảng có trigger, foreign key, cột tự tăng, dữ liệu nhạy cảm hoặc ứng dụng vẫn ghi, cần đánh giá tác dụng phụ trước khi đồng bộ. Với một số hệ thống, cách an toàn hơn là sửa bằng transaction SQL có kiểm soát sau khi đã xác minh từng hàng và có kế hoạch rollback.

### 5.3. Khi nào phải dựng lại replica?

Rebuild thường là lựa chọn phù hợp khi:

- Chênh lệch xuất hiện trên nhiều bảng hoặc không thể xác định đầy đủ phạm vi dữ liệu lệch.
- Replica có errant transaction không thể hợp nhất an toàn.
- Source đã xóa binlog mà replica cần để tiếp tục.
- Schema hoặc dữ liệu bị biến đổi không rõ nguồn gốc.
- Replica từng nhận ghi ngoài luồng và không có nhật ký đủ tin cậy để sửa từng hàng.
- Thời gian và rủi ro sửa từng chênh lệch lớn hơn việc tạo một replica mới từ bản sao nhất quán.

Rebuild có nghĩa là provision lại dữ liệu từ source hoặc backup đã xác minh, thiết lập lại tọa độ replication/GTID và cho replica bắt đầu theo luồng source chuẩn. Đây là thao tác có thể ghi đè dữ liệu replica; phải backup hoặc bảo toàn dữ liệu hiện trạng nếu còn cần điều tra.

## 6. Các phương pháp provision lại replica

### 6.1. Logical backup và restore

Với cơ sở dữ liệu nhỏ hoặc khi cần chuyển đổi có chọn lọc, có thể tạo logical dump rồi restore vào replica. Công cụ thường dùng là mysqldump. Cần chọn tùy chọn snapshot nhất quán phù hợp với engine và ghi nhận tọa độ binlog hoặc GTID tại thời điểm dump.

Ưu điểm là dễ quan sát, có thể chọn database/table và ít phụ thuộc định dạng tệp vật lý. Nhược điểm là restore có thể lâu, tiêu thụ CPU và I/O lớn, đồng thời cần chú ý charset, collation, routine, trigger, event, quyền và thứ tự tạo đối tượng.

Không lấy dump ở một thời điểm rồi gán một tọa độ replication tùy ý. Dữ liệu snapshot và tọa độ binlog/GTID phải đại diện cho cùng một mốc nhất quán; nếu không replica có thể thiếu hoặc áp dụng lặp transaction.

### 6.2. Physical backup

Với dữ liệu lớn, physical backup thường giảm thời gian provision vì lưu trữ dữ liệu ở định dạng gần với cách MySQL sử dụng trên đĩa. Có thể dùng MySQL Enterprise Backup, Percona XtraBackup hoặc cơ chế backup vật lý phù hợp với phiên bản và kiến trúc.

Backup phải được chuẩn bị/restore theo hướng dẫn của công cụ. Ghi nhận metadata như GTID set, binary log file/position hoặc thông tin tương đương do công cụ cung cấp. Sau khi restore, kiểm tra quyền sở hữu tệp, cấu hình instance, server_id duy nhất và dung lượng trước khi khởi động replication.

### 6.3. MySQL Clone Plugin

MySQL Clone Plugin có thể sao chép dữ liệu vật lý từ donor sang recipient trong các phiên bản hỗ trợ. Đây là lựa chọn thuận tiện để provision replica khi hai instance đáp ứng yêu cầu tương thích và cấu hình của plugin. Clone có thể thay thế dữ liệu trên recipient, vì vậy phải xác nhận đúng donor và recipient trước khi thực hiện.

Trước khi dùng Clone Plugin, kiểm tra phiên bản MySQL, plugin đã cài và quyền cần thiết, kết nối mạng, cấu hình TLS, dung lượng đĩa và các điều kiện tương thích. Clone là cách chuyển dữ liệu; vẫn cần thiết lập hoặc xác minh replication channel sau đó và kiểm tra GTID/trạng thái thực thi.

### 6.4. Chọn phương pháp theo quy mô

| Phương pháp | Phù hợp khi | Điểm cần kiểm soát |
|---|---|---|
| Logical dump/restore | Dữ liệu nhỏ, cần chọn lọc schema hoặc portability | Thời gian restore, snapshot nhất quán, đối tượng database và tọa độ replication |
| Physical backup | Dữ liệu lớn, cần khôi phục nhanh hơn logical restore | Tương thích phiên bản/công cụ, metadata backup, quyền tệp và GTID |
| Clone Plugin | Instance tương thích và cần provision trực tiếp từ donor | Recipient bị thay thế dữ liệu, plugin, quyền, mạng và trạng thái sau clone |

Không có một phương pháp tối ưu cho mọi hệ thống. Hãy chọn theo dung lượng dữ liệu, RTO, tải source, khả năng lưu trữ, phiên bản MySQL và năng lực vận hành.

## 7. Thiết lập lại replication bằng GTID auto-position

Sau khi dữ liệu đã được provision từ một snapshot nhất quán, cần cấu hình replica kết nối đến source đúng. Trong MySQL hiện đại, cú pháp dùng CHANGE REPLICATION SOURCE TO; một số phiên bản cũ sử dụng CHANGE MASTER TO.

Ví dụ cấu hình kết nối và bật tự định vị bằng GTID:

~~~sql
STOP REPLICA;

CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'mysql-source.internal',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl_user',
  SOURCE_AUTO_POSITION = 1;

START REPLICA;
SHOW REPLICA STATUS\G
~~~

Ví dụ trên minh họa các thuộc tính kết nối và lược tham số SOURCE_PASSWORD; khi triển khai cần bổ sung mật khẩu qua kênh cấu hình bí mật được tổ chức phê duyệt, không ghi mật khẩu thật vào tài liệu, shell history hoặc log. Cần cấu hình TLS và kiểm tra chứng chỉ khi kết nối qua mạng.

GTID auto-position cho phép replica thông báo tập GTID đã thực thi để source gửi các transaction còn thiếu. Cơ chế này yêu cầu GTID được bật và cấu hình phù hợp trên các máy liên quan. Nó không tự sửa dữ liệu đã drift và không thể lấy lại transaction nếu source đã purge binary log cần thiết.

Nếu replica chứa GTID ngoài luồng, không được xóa hoặc giả mạo tập GTID để ép hai máy có vẻ giống nhau. Hãy xác định transaction đó phát sinh từ đâu, có được ứng dụng xác nhận hay không và có cần hợp nhất dữ liệu không. Khi không thể chứng minh tính đúng đắn, provision lại replica từ source chuẩn thường an toàn hơn.

Một số lệnh reset thường bị hiểu nhầm:

- RESET REPLICA xóa relay log và đặt lại một số trạng thái replication; nó không xóa các hàng trong bảng InnoDB.
- RESET REPLICA ALL còn xóa thông tin kết nối source đã lưu.
- Các lệnh reset không thay thế việc restore dữ liệu và không giải quyết data drift.
- Không dùng lệnh reset GTID hoặc binlog như cách che giấu transaction lệch. Trước mọi thao tác reset, phải lưu lại trạng thái và làm theo runbook đúng phiên bản.

## 8. Quy trình resync/rebuild có thể kiểm chứng

Một quy trình có kiểm soát có thể chia thành các giai đoạn:

1. **Phát hiện:** cảnh báo lag, receiver/applier dừng, checksum mismatch hoặc truy vấn nghiệp vụ phát hiện dữ liệu khác.
2. **Cô lập thay đổi:** xác định source chuẩn và ngăn ghi ngoài luồng vào replica. Nếu nghi ngờ split-brain, fence máy chủ không được chọn.
3. **Thu thập bằng chứng:** lưu SHOW REPLICA STATUS, GTID set, lỗi, binlog/relay log metadata, schema và cấu hình filter.
4. **Backup hiện trạng:** tạo bản sao có thể khôi phục của replica và lưu dữ liệu phục vụ điều tra.
5. **Đánh giá phạm vi:** so sánh schema, bảng, chunk và hàng; xác định thiếu transaction, errant transaction hoặc dữ liệu drift.
6. **Chọn phương án:** catch up, sửa có mục tiêu hoặc rebuild từ donor/backup chuẩn.
7. **Thực hiện:** chạy theo chiều dữ liệu đã xác định, giới hạn quyền, theo dõi tài nguyên và lưu log thay đổi.
8. **Khôi phục replication:** cấu hình source, tài khoản, TLS, GTID auto-position hoặc tọa độ phù hợp rồi khởi động replica.
9. **Xác minh:** receiver/applier chạy, không có lỗi mới, GTID tiến triển và checksum ở phạm vi sửa đã khớp.
10. **Mở lại lưu lượng:** chỉ đưa replica trở lại pool đọc hoặc vai trò standby sau khi các kiểm tra và thử nghiệm nghiệp vụ đạt yêu cầu.

Trong quá trình sửa, giữ read_only và super_read_only trên replica khi phù hợp để ngăn ghi ngoài ý muốn. Chỉ mở ghi khi replica được promote thành source theo quy trình failover. Tài khoản replication chỉ nên có quyền cần thiết cho replication; tài khoản vận hành resync cần được cấp riêng và ghi nhận.

## 9. Kiểm tra sau khi đồng bộ

Không kết thúc công việc chỉ vì START REPLICA chạy thành công. Cần kiểm tra nhiều lớp:

**Luồng replication:** xác nhận receiver và applier đang hoạt động, lỗi I/O/SQL không xuất hiện lại, relay log được xử lý và lag giảm về mức mục tiêu.

**GTID:** xác nhận replica đã thực thi các GTID cần thiết từ source. Với topology đơn giản và đã loại bỏ ghi ngoài luồng, tập GTID thực thi cần phản ánh đúng lịch sử transaction của source. Với topology nhiều source hoặc có lịch sử failover, cần đối chiếu theo từng channel và ngữ cảnh.

**Dữ liệu:** chạy lại checksum cho các bảng/chunk đã sửa hoặc toàn bộ phạm vi theo kế hoạch. Kiểm tra các khóa chính, quan hệ khóa ngoại, số liệu tổng hợp nghiệp vụ và schema.

**Ứng dụng:** chạy các truy vấn đọc đại diện, kiểm tra read-after-write routing và xác nhận không có truy vấn ghi bị gửi nhầm đến replica.

**Vận hành:** xác nhận backup mới, binlog retention, cảnh báo lag, quyền truy cập và tài liệu runbook đã được cập nhật.

Một replica chỉ nên được đưa lại vào pool đọc khi dữ liệu cần thiết đã bắt kịp và ứng dụng chấp nhận độ trễ còn lại. Replica được chỉ định làm standby cần có trạng thái đủ tốt để đáp ứng RPO/RTO đã thống nhất.

## 10. Tình huống thực hành

Một hệ thống có source db-primary và replica db-read-01. Sau một đợt bảo trì, dashboard cho thấy receiver và applier đều chạy, nhưng checksum bảng orders khác nhau. Kiểm tra tiếp phát hiện một số hàng trên replica có trạng thái đơn hàng đã bị sửa trực tiếp bởi tài khoản vận hành. Tập GTID không cho thấy transaction nào bị thiếu từ source, nhưng cũng không chứng minh những thay đổi trực tiếp đó là hợp lệ.

Hãy lập kế hoạch xử lý:

1. Xác nhận db-primary là source chuẩn và kiểm tra ứng dụng không ghi sang máy khác.
2. Ngăn ghi trực tiếp lên db-read-01, lưu log và backup hiện trạng.
3. So sánh schema, xác định danh sách khóa chính bị lệch và phạm vi hàng bị ảnh hưởng.
4. Xác nhận các thay đổi trực tiếp trên replica không đại diện cho nghiệp vụ hợp lệ.
5. Nếu phạm vi nhỏ, sửa đúng các hàng từ source sang replica bằng công cụ hoặc transaction có kiểm soát; nếu phạm vi không đầy đủ hoặc không tin cậy, dựng lại replica từ snapshot chuẩn.
6. Khởi động hoặc xác minh replication theo GTID auto-position; theo dõi receiver, applier và lag.
7. Chạy lại checksum, truy vấn kiểm tra trạng thái đơn hàng và thử định tuyến đọc của ứng dụng trước khi mở lại replica.

Điểm quan trọng là tập GTID có thể cho biết transaction replication nào đã được thực thi, nhưng không tự phát hiện mọi thay đổi SQL được ghi trực tiếp trên replica khi binary logging hoặc luồng replication không phản ánh chúng theo cách mong đợi. Đối soát GTID phải đi cùng kiểm tra dữ liệu thực tế.

## 11. Câu hỏi tự kiểm tra

1. Replication lag khác data drift ở điểm nào? Vì sao trạng thái receiver/applier chạy không đủ để chứng minh dữ liệu giống nhau?
2. Khi GTID_SUBTRACT(source_gtids, replica_gtids) trả về tập không rỗng, điều đó cho biết điều gì?
3. Vì sao GTID set không thay thế checksum dữ liệu?
4. Khi nào có thể chỉ cần khởi động lại replication, khi nào nên sửa hàng có mục tiêu và khi nào phải rebuild?
5. Vì sao cần xác định source chuẩn và backup hiện trạng trước khi resync?
6. Logical backup, physical backup và Clone Plugin khác nhau ở điểm nào khi provision replica?
7. RESET REPLICA ALL có xóa dữ liệu bảng không? Nó tác động đến thông tin nào?
8. Sau rebuild, cần kiểm tra những điều kiện nào trước khi đưa replica trở lại pool đọc?

Đối soát và tái tạo replica là quy trình bảo toàn tính đúng đắn của dữ liệu. Cần chứng minh được nguồn dữ liệu chuẩn, thời điểm snapshot, phạm vi transaction đã nhận và áp dụng, hướng sửa dữ liệu, cùng kết quả xác minh sau đồng bộ. Khi những bằng chứng đó đầy đủ, replica mới đủ tin cậy để tiếp tục phục vụ đọc hoặc làm máy dự phòng.
