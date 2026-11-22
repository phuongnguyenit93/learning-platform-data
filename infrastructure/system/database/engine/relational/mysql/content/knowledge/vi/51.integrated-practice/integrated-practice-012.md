# Diễn tập restore/PITR sau cập nhật hoặc xóa nhầm

Một thao tác UPDATE hoặc DELETE nhầm có thể làm sai hàng nghìn bản ghi chỉ trong vài giây. Khi phát hiện, điều quan trọng là giữ lại lịch sử giao dịch, xác định mốc dữ liệu đúng cuối cùng và phục hồi theo cách có thể kiểm chứng. MySQL Point-in-Time Recovery (PITR) kết hợp một bản backup nhất quán với binary log để dựng lại trạng thái database tại một thời điểm hoặc vị trí giao dịch cụ thể.

PITR không đơn giản là restore backup mới nhất rồi chạy tất cả binary log. Nếu tiếp tục replay qua transaction gây hỏng dữ liệu, thao tác nhầm sẽ được thực hiện lại. Cần tìm chính xác transaction hoặc binlog position chứa thay đổi sai, dựng bản phục hồi trên instance cô lập, dừng replay trước transaction đó, rồi xác minh và đưa dữ liệu cần thiết trở lại hệ thống.

Bài thực hành này thuộc phạm vi làm chủ MySQL từ transaction, backup, binary log và replication đến xử lý sự cố vận hành. Mục tiêu là diễn tập trọn quy trình sau một thao tác cập nhật hoặc xóa nhầm: bảo toàn bằng chứng, xác định backup, phục hồi PITR, đối soát dữ liệu, chọn phương án merge và xác nhận RPO/RTO.

## 1. Mục tiêu và phạm vi diễn tập

Sau bài thực hành, người học cần có thể:

- Nhận biết phạm vi ảnh hưởng và bảo toàn binary log trước khi hết retention.
- Chọn backup nhất quán có metadata về GTID hoặc file/position.
- Xác định transaction gây hỏng dữ liệu từ binary log và audit log.
- Restore backup trên MySQL instance cô lập.
- Replay binary log đến ngay trước transaction phá hoại.
- Phục hồi một bảng, một nhóm hàng hoặc toàn bộ instance theo đúng tình huống.
- Đối soát dữ liệu phục hồi với trạng thái hiện tại và nghiệp vụ.
- Lập kế hoạch cutover, rollback và giám sát sau phục hồi.
- Đo thời gian phục hồi thực tế và so sánh với RPO/RTO.

### 1.1. Kịch bản mẫu

Một nhân viên vận hành chạy nhầm câu lệnh:

~~~sql
UPDATE customer
SET account_status = 'CLOSED';
~~~

Câu lệnh thiếu WHERE, làm tất cả tài khoản khách hàng chuyển sang CLOSED. Hệ thống phát hiện sau vài phút. Trong thời gian từ lúc backup đến lúc phát hiện, source vẫn nhận các giao dịch hợp lệ khác như tạo khách hàng mới, cập nhật địa chỉ và ghi đơn hàng.

Mục tiêu không phải đưa toàn bộ hệ thống về trạng thái trước sự cố rồi mất mọi giao dịch hợp lệ sau đó. Nhóm cần dựng một bản phục hồi tại thời điểm ngay trước transaction sai, sau đó chọn cách trích xuất và merge dữ liệu bị ảnh hưởng hoặc lập kế hoạch khôi phục toàn instance nếu phạm vi hỏng đủ lớn.

### 1.2. Phân biệt các mốc thời gian

| Mốc | Ý nghĩa |
|---|---|
| T_backup | Thời điểm nhất quán của backup được chọn |
| T_bad | Thời điểm transaction gây hỏng dữ liệu được commit |
| T_detect | Thời điểm nhóm phát hiện sự cố |
| T_stop | Thời điểm dừng hoặc giới hạn các ghi có thể làm sự cố lan rộng |
| T_recovery | Mốc PITR được chọn để dựng dữ liệu phục hồi |
| T_restore_done | Thời điểm instance phục hồi sẵn sàng để kiểm tra |

T_recovery thường phải nằm trước T_bad. T_detect có thể muộn hơn T_bad; khoảng thời gian này quyết định có bao nhiêu giao dịch hợp lệ đã phát sinh sau transaction sai và cần được giữ lại khi merge.

## 2. Kiến trúc backup và PITR

PITR cần ít nhất hai thành phần:

1. **Base backup:** bản sao database nhất quán tại một mốc đã biết.
2. **Binary log liên tục:** chuỗi sự kiện sau mốc backup, được lưu đủ lâu để replay đến mốc cần phục hồi.

~~~mermaid
flowchart LR
    A["Base backup tại T_backup"] --> B["Restore vào recovery instance"]
    C["Binary logs sau T_backup"] --> D["Chọn chuỗi log liên tục"]
    B --> E["Replay transaction hợp lệ"]
    D --> E
    E --> F["Dừng trước transaction gây hỏng"]
    F --> G["Đối soát dữ liệu phục hồi"]
    G --> H["Extract / merge / cutover"]
~~~

Nếu thiếu backup nhất quán, binary log không đủ để tái tạo toàn bộ trạng thái. Nếu thiếu một đoạn binary log giữa backup và mốc phục hồi, không thể replay liên tục qua khoảng trống đó chỉ bằng các file còn lại.

### 2.1. Chọn loại backup

| Loại backup | Đặc điểm | Điểm cần xác minh |
|---|---|---|
| Logical dump | Xuất schema và dữ liệu thành SQL; dễ chọn bảng hoặc dữ liệu | Thời gian restore, consistency, routines/events/triggers, charset và metadata binlog |
| Physical hot backup | Sao chép file InnoDB khi server vẫn hoạt động bằng công cụ phù hợp | Backup phải được prepare/recover theo công cụ; cần metadata GTID/binlog coordinate |
| MySQL Clone hoặc snapshot storage | Có thể tạo bản sao nhanh tùy nền tảng và phiên bản | Tính nhất quán, phạm vi snapshot, compatibility và vị trí binlog |
| Backup managed service | Nhà cung cấp quản lý snapshot và PITR | Retention, restore target, vùng/instance đích và thời gian restore thực tế |

Backup phải có metadata chỉ ra trạng thái replication/binlog tại snapshot. Tùy công cụ, thông tin có thể nằm trong output của mysqldump, metadata file của physical backup hoặc bản ghi từ dịch vụ backup. Không tự suy ra file/position bằng cách nhìn thời gian hoàn tất upload.

### 2.2. Logical backup với InnoDB

Với mysqldump, tùy chọn single-transaction tạo consistent snapshot cho các bảng transactional như InnoDB. DDL không nên chạy đồng thời trong lúc dump vì có thể làm snapshot không còn đáng tin cậy. Các bảng nontransactional không được bảo vệ bởi cùng cơ chế snapshot.

Ví dụ minh họa:

~~~bash
mysqldump \
  --single-transaction \
  --routines \
  --events \
  --triggers \
  --source-data=2 \
  --databases shopdb \
  > shopdb-full.sql
~~~

Tùy chọn source-data và tên tùy chọn ghi tọa độ binlog phụ thuộc phiên bản client. Một số phiên bản cũ dùng master-data. Hãy kiểm tra mysqldump --help và tài liệu đúng phiên bản đang chạy. Tọa độ được ghi trong dump cần được bảo toàn cùng file backup.

Nếu dump chứa nhiều database, account, routine hoặc event, xác định rõ phạm vi cần phục hồi. Quyền user MySQL và secret không nên được đưa vào bản chia sẻ không kiểm soát.

### 2.3. Physical backup

Với physical backup, dùng đúng quy trình backup/prepare/restore của công cụ. Ví dụ, Percona XtraBackup có metadata về binary log position và GTID trong các file metadata của backup. MySQL Enterprise Backup cũng cung cấp thông tin cần thiết theo định dạng của công cụ.

Không copy trực tiếp thư mục dữ liệu đang chạy rồi xem đó là một backup InnoDB nhất quán. Phải biết backup có crash-consistent hay application-consistent, công cụ đã flush/copy redo log như thế nào và bước prepare/restore cần thiết.

## 3. Ứng phó ngay khi phát hiện cập nhật hoặc xóa nhầm

### 3.1. Bảo toàn lịch sử trước khi điều tra sâu

Thực hiện theo runbook sự cố của tổ chức:

1. Ghi nhận thời điểm phát hiện, người báo cáo, database, bảng và thao tác nghi ngờ.
2. Hạn chế hoặc dừng luồng ghi gây hỏng thêm nếu có thể làm an toàn.
3. Bảo toàn binary log hiện có và log archive; tạm điều chỉnh quy trình purge nếu cần và được phép.
4. Lưu error log, audit log, general log hoặc query log liên quan.
5. Ghi GTID, binlog file/position, server UUID và trạng thái replication.
6. Tạo snapshot/backup bảo vệ trạng thái hiện tại trước các thao tác sửa chữa lớn.
7. Chỉ định một người điều phối và một bản timeline sự cố dùng chung.

Không chạy tiếp các câu lệnh sửa dữ liệu thử nghiệm trên production. Không restart hoặc reset replication chỉ để xóa thông báo lỗi trước khi lưu bằng chứng.

### 3.2. Hạn chế ghi mới như thế nào?

Việc dừng toàn bộ ghi có thể làm gián đoạn nghiệp vụ. Chọn mức hạn chế theo phạm vi ảnh hưởng:

- Nếu một bảng bị hỏng và ứng dụng có thể tạm ngừng thao tác liên quan, tắt riêng luồng ghi đó.
- Nếu câu lệnh sai vẫn đang chạy, hủy query/transaction theo quy trình và kiểm tra kết quả đã commit hay chưa.
- Nếu transaction đã commit, hủy query không thể hoàn tác dữ liệu; cần phục hồi bằng backup/PITR.
- Nếu dữ liệu tiếp tục bị thay đổi theo trạng thái sai, ngăn các job hoặc người dùng làm lan rộng trước khi merge.

Với InnoDB, một transaction đang mở có thể rollback khi bị hủy, nhưng câu lệnh đã commit không thể rollback bằng cách kill connection. DDL và một số thao tác có implicit commit cũng cần xử lý riêng.

### 3.3. Bảo toàn binary log

Trên source, thu thập:

~~~sql
SHOW BINARY LOGS;

SHOW BINARY LOG STATUS;

SHOW VARIABLES
WHERE Variable_name IN (
  'log_bin',
  'binlog_format',
  'binlog_row_image',
  'binlog_expire_logs_seconds',
  'gtid_mode',
  'server_id'
);
~~~

SHOW BINARY LOG STATUS có trên các phiên bản MySQL mới; các phiên bản trước có thể dùng SHOW MASTER STATUS. Xác minh cú pháp đúng với server đang chạy.

Sao chép các binary log cần thiết sang nơi lưu trữ an toàn, giữ nguyên tên file, thứ tự và checksum. Nếu dùng binary log archive, xác minh đoạn từ backup đến mốc sự cố không bị thiếu file. Không purge log trong lúc chưa xác định xong recovery point.

## 4. Xác định transaction gây hỏng

### 4.1. Kết hợp audit log và binary log

Audit log hoặc application log có thể cho biết ai gửi câu lệnh, từ host nào và qua ứng dụng nào. Binary log cho biết thay đổi đã được ghi vào lịch sử transaction. Dùng cả hai để đối chiếu:

- Timestamp và timezone của event.
- User, host, connection ID nếu log có.
- SQL text hoặc row changes.
- Transaction boundary và commit.
- GTID hoặc file/position.
- Bảng và khóa bị tác động.

Timestamp đơn lẻ không đủ để dừng chính xác vì nhiều transaction có thể cùng giây, timezone log có thể khác nhau và transaction có thể kéo dài. Ưu tiên GTID và binlog position; dùng thời gian để khoanh vùng.

### 4.2. Đọc binary log dạng dễ phân tích

Với row-based binary log, dùng mysqlbinlog để giải mã row event:

~~~bash
mysqlbinlog \
  --verbose \
  --base64-output=DECODE-ROWS \
  --start-position=4 \
  binlog.000245 \
  > binlog-decoded.txt
~~~

Kết quả verbose giúp nhìn các sự kiện Table_map, Update_rows hoặc Delete_rows cùng giá trị trước/sau tùy row image. Với statement-based logging, Query event có thể thể hiện trực tiếp câu SQL.

Đầu ra đã decode chỉ dùng để điều tra. Không đưa file decode này vào mysql để replay thay cho binary log gốc, vì các pseudo-SQL như BINLOG hoặc comment row event không phải script SQL thông thường có thể chạy lại. Khi phục hồi, dùng mysqlbinlog trên file gốc để tạo stream replay chuẩn.

### 4.3. Xác định transaction boundary

Một transaction có thể chứa nhiều event:

~~~text
GTID event
BEGIN
Table_map / Query / row events
...
XID (COMMIT)
~~~

Với row-based logging, một UPDATE lớn có thể được ghi thành nhiều row event trong cùng transaction. Cần xác định event đầu của transaction gây hỏng và vị trí commit của nó. Khi PITR đến trước transaction, điểm dừng phải loại toàn bộ transaction; không dừng giữa các row event.

Ghi lại:

- GTID của transaction gây hỏng nếu GTID bật.
- Tên binary log file chứa transaction.
- Position của event đầu transaction.
- Position của transaction tiếp theo hoặc mốc stop đã kiểm chứng.
- Các transaction hợp lệ trước và sau transaction sai.

### 4.4. Đối chiếu GTID

Nếu GTID được bật, ghi lại trên source:

~~~sql
SELECT
  @@GLOBAL.gtid_executed,
  @@GLOBAL.gtid_purged;
~~~

GTID giúp nhận diện transaction đã thực thi và transaction đã purge. Nó không tự cho biết transaction có gây hỏng nghiệp vụ hay không; cần xem nội dung event và dữ liệu bị tác động.

Nếu backup có GTID set tại snapshot, dùng nó để xác định phần binary log cần replay. Nếu không có metadata GTID/binlog coordinate nhất quán với backup, dừng lại để xác minh backup provenance; không đoán mốc bắt đầu từ tên file hoặc timestamp.

## 5. Chọn recovery point

Recovery point thường là vị trí ngay trước transaction sai, nhưng cần hiểu tác động đến các transaction hợp lệ sau đó.

### 5.1. PITR toàn instance

Phù hợp khi:

- Phạm vi hỏng rộng và cần đưa toàn instance về trạng thái trước sự cố.
- Có thể chấp nhận mất các giao dịch hợp lệ sau recovery point hoặc có cách phát lại chúng.
- Ứng dụng có kế hoạch cutover và xử lý dữ liệu phát sinh sau mốc phục hồi.

PITR toàn instance thường phục hồi toàn bộ database từ backup rồi replay log đến mốc đã chọn. Nó không tự giữ các transaction hợp lệ xảy ra sau mốc đó.

### 5.2. Phục hồi bảng hoặc nhóm hàng

Phù hợp khi chỉ một bảng hoặc một nhóm bản ghi bị tác động và hệ thống vẫn tiếp tục ghi các bảng khác. Quy trình thường là:

1. Restore toàn bộ backup vào instance cô lập.
2. Replay binary log đến trước transaction phá hoại.
3. Export bảng hoặc tập hàng cần khôi phục từ instance phục hồi.
4. So sánh với dữ liệu production hiện tại.
5. Merge dữ liệu theo khóa chính, foreign key và lịch sử hợp lệ sau sự cố.

Đây là cách phổ biến để cứu dữ liệu đã bị xóa hoặc cập nhật nhầm mà không đưa toàn hệ thống quay lui. Tuy nhiên, phục hồi riêng bảng không phải lúc nào cũng đơn giản: các bảng khác có thể tham chiếu đến nó, các transaction sau sự cố có thể phụ thuộc vào dữ liệu bị hỏng, và trigger có thể tạo side effect khi import.

### 5.3. Không bỏ qua transaction sau sự cố một cách mù quáng

Nếu dừng PITR trước transaction sai, tất cả transaction sau nó cũng chưa được replay. Một đơn hàng hợp lệ có thể được tạo sau khi giá sản phẩm bị cập nhật nhầm; một khách hàng mới có thể được tạo sau lệnh DELETE sai.

Để giữ dữ liệu hợp lệ sau T_bad, cần:

- Phục hồi bảng/row bị ảnh hưởng từ recovery instance.
- Giữ nguyên các thay đổi hợp lệ trên production hoặc trích xuất/replay chọn lọc theo logic nghiệp vụ.
- Đối chiếu quan hệ và khóa ngoại trước khi merge.
- Xử lý transaction phụ thuộc vào dữ liệu đã hỏng.

Không chỉ chạy tiếp binary log sau transaction sai nếu nó phụ thuộc trạng thái đã bị hỏng. Việc replay có thể tạo thêm sai lệch, duplicate key hoặc dữ liệu không còn hợp lệ.

## 6. Restore backup vào instance cô lập

### 6.1. Chuẩn bị recovery instance

Recovery instance cần:

- Phiên bản MySQL tương thích với backup và binlog.
- Dung lượng lưu trữ đủ cho restore, relay/temp và dữ liệu xuất.
- Network cô lập, không nhận traffic ứng dụng.
- Server ID và identity phù hợp, không gây xung đột topology.
- Tài khoản phục hồi có quyền tối thiểu cần thiết.
- Binary logging/GTID được cấu hình theo kế hoạch phục hồi.
- Không tự động join replication hoặc read pool trước khi xác minh.

Giữ instance phục hồi tách khỏi production để tránh ứng dụng ghi nhầm hoặc replica nhận sự kiện ngoài ý muốn. Đặt chế độ read-only/super_read_only nếu phù hợp với quy trình restore và công cụ cần dùng; một số bước restore hoặc replay có thể yêu cầu quyền đặc biệt.

### 6.2. Restore logical dump

Ví dụ khôi phục vào instance cô lập:

~~~bash
mysql \
  --host=recovery-db.internal \
  --user=recovery_admin \
  --password \
  < shopdb-full.sql
~~~

Nếu dump chứa nhiều database hoặc có câu lệnh tạo database/use, không truyền database đích một cách tùy tiện. Xác minh trước nội dung đầu/cuối của dump và nơi nó sẽ ghi.

Sau restore:

~~~sql
SELECT VERSION();
SHOW DATABASES;
SHOW TABLE STATUS FROM shopdb;
~~~

Kiểm tra bảng, view, trigger, routine, event, charset, collation, constraint và số hàng quan trọng. Đảm bảo restore không bị lỗi giữa chừng; một lệnh import trả lỗi không được xem là backup đã phục hồi đầy đủ.

### 6.3. Restore physical backup

Với physical backup, thực hiện bước prepare/apply redo theo tài liệu của công cụ rồi restore vào datadir hoặc instance đích. Xác minh quyền sở hữu file, cấu hình InnoDB, keyring/encryption và plugin cần thiết.

Không khởi động hai mysqld cùng dùng một datadir. Không thay server UUID hoặc GTID metadata tùy tiện để ép instance tham gia topology; việc đó có thể phá vỡ lịch sử replication.

### 6.4. Kiểm tra mốc backup

Sau restore, xác định chính xác:

- GTID set đã có trong backup, nếu có.
- Binlog file và position tại snapshot.
- Timestamp/metadata của backup.
- Danh sách binary log archive bắt đầu từ mốc đó.
- Các khoảng trống hoặc file hỏng trong chuỗi log.

Nếu backup được tạo trên source trong lúc transaction đang hoạt động, metadata của công cụ phải chỉ ra snapshot consistent point. Không tự dùng thời điểm file backup hoàn tất để thay cho mốc transaction nhất quán.

## 7. Replay binary log đến trước transaction gây hỏng

### 7.1. Kiểm tra chuỗi file

Liệt kê các file từ mốc backup đến file chứa transaction sai. Xác minh tên, thứ tự, kích thước và checksum. Nếu có một file thiếu hoặc không đọc được, phải tìm bản archive khác hoặc chọn backup/recovery point khác.

Trên source, SHOW BINARY LOGS chỉ liệt kê file còn trên source tại thời điểm truy vấn. Các file đã được archive phải được đối chiếu riêng với manifest lưu trữ.

### 7.2. Xác định start position

Lấy start file/position từ metadata backup. Nếu backup cung cấp GTID set, xác định binlog tương ứng và kiểm tra chuỗi giao dịch. Không mặc định mọi backup bắt đầu từ position 4; position thực tế phải lấy từ metadata của backup.

### 7.3. Tạo stream replay đến stop position

Giả sử:

- Backup được chụp tại file binlog.000240, position 987654.
- Transaction sai bắt đầu trong binlog.000245 tại position 456789.
- Các file binlog.000241 đến binlog.000244 cần replay đầy đủ.

Truyền start position trên file đầu và stop position trên file cuối trong cùng lệnh. mysqlbinlog áp dụng start-position cho file đầu tiên và stop-position cho file cuối cùng trong danh sách:

~~~bash
mysqlbinlog \
  --start-position=987654 \
  --stop-position=456789 \
  binlog.000240 \
  binlog.000241 \
  binlog.000242 \
  binlog.000243 \
  binlog.000244 \
  binlog.000245 \
  > replay.sql
~~~

Các position trên chỉ là số minh họa. Phải thay bằng mốc được xác minh từ metadata và phân tích event. Stop position phải trỏ đến vị trí bắt đầu của event đầu transaction gây hỏng để event đó và toàn bộ phần sau không được đưa vào stream. Kiểm tra đầu ra để chắc chắn transaction gây hỏng không xuất hiện và transaction hợp lệ trước đó đã hoàn tất. Nếu start và stop nằm trong cùng một file, cả hai option áp dụng cho file đó.

### 7.4. Kiểm tra stream trước khi áp dụng

Trước khi chạy vào recovery instance:

- Đọc header và cuối file replay.
- Xác nhận đúng source, database và chuỗi file.
- Xác nhận GTID của transaction sai không xuất hiện.
- Kiểm tra không dừng giữa transaction.
- Xác nhận không có câu lệnh ghi ngoài phạm vi dự kiến.
- Ghi checksum và lưu stream đã tạo cùng log thực thi.

Không sửa thủ công một GTID event hoặc row event trong file replay. Nếu cần bỏ transaction hoặc chỉnh dữ liệu, thực hiện trên bản phục hồi bằng quy trình có thể kiểm tra và ghi lại rõ ràng.

### 7.5. Áp dụng stream trên recovery instance

~~~bash
mysql \
  --host=recovery-db.internal \
  --user=recovery_admin \
  --password \
  --binary-mode=1 \
  < replay.sql
~~~

Chạy theo thứ tự file và đoạn đã xác minh. Theo dõi stdout/stderr và exit code. Nếu một câu lệnh lỗi, dừng lại và điều tra; không bỏ qua lỗi rồi tiếp tục như thể replay thành công.

Không áp dụng stream này lên production source. Mục tiêu là tạo một bản phục hồi có thể đọc/đối soát, không ghi đè dữ liệu production trong giai đoạn điều tra.

### 7.6. Dùng thời gian khi không xác định được position

mysqlbinlog hỗ trợ giới hạn theo thời gian bằng các option start-datetime và stop-datetime. Cách này có thể hữu ích để khoanh vùng, nhưng thời gian không chính xác bằng transaction position:

- Nhiều transaction có thể cùng timestamp.
- Timestamp trong log có thể chịu ảnh hưởng timezone và đồng hồ.
- Một transaction có thể kéo dài qua khoảng thời gian đã chọn.
- Có thể vô tình đưa một phần transaction vào stream nếu không kiểm tra boundary.

Nếu phải dùng thời gian, giải mã stream, xác định transaction boundary và kiểm tra lại bằng GTID/position trước khi áp dụng. Không dùng timestamp gần đúng làm bằng chứng duy nhất cho một recovery point quan trọng.

## 8. Đối soát và trích xuất dữ liệu

### 8.1. Kiểm tra bản phục hồi

Sau replay, so sánh dữ liệu trên recovery instance với expected state:

- Số hàng tổng và số hàng theo nhóm.
- Các khóa chính/unique.
- Trạng thái nghiệp vụ quan trọng.
- Foreign key và quan hệ giữa các bảng.
- Tổng tiền, số dư, tồn kho hoặc các invariant nghiệp vụ.
- Timestamp/version của bản ghi.
- Trigger, generated column và dữ liệu phụ thuộc.

Ví dụ kiểm tra số lượng trạng thái tài khoản:

~~~sql
SELECT account_status, COUNT(*) AS row_count
FROM shopdb.customer
GROUP BY account_status
ORDER BY account_status;
~~~

Kiểm tra các bản ghi bị đóng hàng loạt:

~~~sql
SELECT COUNT(*) AS closed_count
FROM shopdb.customer
WHERE account_status = 'CLOSED';
~~~

Không chỉ so sánh tổng số hàng. Một tập dữ liệu có cùng số hàng vẫn có thể chứa sai khóa, sai trạng thái hoặc sai quan hệ.

### 8.2. Trích xuất bảng hoặc tập hàng

Nếu chỉ cần phục hồi một nhóm hàng, export từ recovery instance vào staging schema hoặc file trung gian. Không import trực tiếp vào bảng production trước khi xem xét:

- Hàng có được cập nhật hợp lệ sau T_bad không?
- Có row mới được tạo sau backup không?
- Khóa chính có xung đột với dữ liệu hiện tại không?
- Foreign key có tham chiếu đến hàng đã thay đổi không?
- Có cần giữ các cột do hệ thống tạo như version, updated_at, audit fields?
- Có trigger sẽ phát sinh side effect khi INSERT/UPDATE không?

Một bảng có thể chứa dữ liệu mới hợp lệ được tạo sau transaction phá hoại. Không thay toàn bộ bảng production bằng bản cũ nếu điều đó sẽ xóa các hàng hợp lệ mới.

### 8.3. So sánh trước khi merge

Đưa dữ liệu recovery vào staging schema trên môi trường đích hoặc một database trung gian. Viết câu truy vấn liệt kê:

- Hàng có trong recovery nhưng thiếu ở production.
- Hàng có ở cả hai nhưng khác giá trị.
- Hàng chỉ có ở production.
- Hàng có quan hệ phụ thuộc bị ảnh hưởng.

Ví dụ đối chiếu theo primary key:

~~~sql
SELECT r.customer_id
FROM recovery_db.customer AS r
LEFT JOIN production_stage.customer AS p
  ON p.customer_id = r.customer_id
WHERE p.customer_id IS NULL;
~~~

Đối với bảng lớn, dùng checksum theo chunk hoặc công cụ so sánh dữ liệu đã được phê duyệt. Đảm bảo so sánh cùng collation, kiểu dữ liệu và phạm vi dữ liệu.

### 8.4. Merge có kiểm soát

Lập script merge rõ ràng, có điều kiện theo primary key và version/timestamp nếu có. Chạy thử trên staging copy, ghi số hàng insert/update/delete và kiểm tra invariant sau merge.

Nếu cần phục hồi một cột bị UPDATE nhầm, không nhất thiết ghi đè cả row từ backup. Có thể chỉ khôi phục cột bị tác động cho những hàng xác định, đồng thời giữ các cột đã được cập nhật hợp lệ sau sự cố. Tuy nhiên, cách này chỉ đúng khi có thể xác định chính xác phạm vi và quan hệ nghiệp vụ.

Với thao tác DELETE nhầm, phục hồi hàng từ backup có thể xung đột với foreign key hoặc bản ghi thay thế đã được tạo sau đó. Cần quyết định rõ có khôi phục nguyên ID, tạo ID mới hay giữ tombstone theo nghiệp vụ.

## 9. Kế hoạch cutover và rollback

### 9.1. Trước cutover

- Xác định chính xác bảng/row và script merge.
- Chụp backup/snapshot trạng thái production ngay trước thay đổi.
- Kiểm tra script trên bản sao staging.
- Đặt thời gian bảo trì hoặc hạn chế ghi liên quan nếu cần.
- Xác định các service, job, trigger và consumer có thể ghi vào dữ liệu.
- Chuẩn bị truy vấn xác minh và tiêu chí dừng.
- Chỉ định người phê duyệt và người thực hiện.

### 9.2. Trong cutover

1. Hạn chế ghi vào phạm vi dữ liệu sẽ merge.
2. Chạy pre-check và lưu kết quả.
3. Thực hiện merge theo batch có giới hạn nếu bảng lớn.
4. Kiểm tra affected rows sau từng batch.
5. Chạy post-check và invariant.
6. Mở lại luồng ghi khi kết quả đạt tiêu chí.

Nếu script có thể chạy lại, thiết kế idempotent hoặc có checkpoint theo batch. Không chạy lại toàn bộ script sau timeout nếu chưa xác định batch nào đã commit.

### 9.3. Rollback merge

Trước khi chạy, phải biết cách hoàn tác:

- Có snapshot trước merge để phục hồi.
- Có bảng audit/staging lưu giá trị trước và sau.
- Có transaction rollback nếu toàn bộ merge nằm trong một transaction hợp lý.
- Với batch đã commit, có script đảo ngược dựa trên snapshot/checkpoint.

Transaction rất lớn có thể tạo undo log, lock và replication lag; cân nhắc chia batch nhưng phải giữ khả năng phục hồi. Không giả định rollback của ứng dụng có thể đảo ngược một script đã commit hoặc trigger side effect bên ngoài database.

## 10. RPO, RTO và tính khả thi của PITR

RPO (Recovery Point Objective) là lượng dữ liệu tối đa tổ chức chấp nhận mất tính theo thời gian. RTO (Recovery Time Objective) là thời gian tối đa cho phép để khôi phục dịch vụ.

Ví dụ:

- Backup full mỗi ngày.
- Binary log được archive liên tục.
- Phát hiện thao tác nhầm sau 4 phút.
- Restore backup mất 35 phút.
- Replay binary log đến trước transaction sai mất 12 phút.
- Đối soát và merge mất 20 phút.

Tổng thời gian ước lượng là 67 phút, chưa tính phê duyệt và cutover. Nếu RTO là 60 phút, quy trình hiện tại chưa đạt; cần tối ưu restore, chuẩn bị recovery instance, tăng tốc replay hoặc dùng snapshot/clone phù hợp hơn.

RPO không chỉ là tần suất backup. Nếu binary log được lưu liên tục và đầy đủ, có thể phục hồi gần thời điểm sự cố; nếu binlog bị thiếu hoặc purge, RPO thực tế có thể quay về mốc backup gần nhất.

Ghi số đo thực tế sau mỗi lần diễn tập:

| Chỉ số | Kết quả diễn tập |
|---|---|
| Backup age tại thời điểm sự cố | Ghi thời gian |
| Khoảng binlog cần replay | Ghi thời lượng và dung lượng |
| Restore duration | Ghi thời gian thực |
| Replay duration | Ghi thời gian thực |
| Data validation duration | Ghi thời gian thực |
| Merge/cutover duration | Ghi thời gian thực |
| RPO thực tế | Chênh lệch dữ liệu tối đa |
| RTO thực tế | Từ lúc bắt đầu xử lý đến khi dịch vụ đạt điều kiện phục hồi |

## 11. Những lỗi thường gặp khi PITR

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Restore thành công nhưng thiếu dữ liệu | Backup không bao phủ bảng/schema hoặc backup không nhất quán | Kiểm tra scope, metadata và loại storage engine |
| Replay báo thiếu binlog | Retention ngắn, archive thiếu file | Tìm bản archive đầy đủ hoặc chọn backup khác |
| Replay dừng vì duplicate key | Replay sai mốc, dữ liệu backup đã chứa transaction hoặc log bị áp dụng lặp | Xác minh coordinate và GTID trước khi chạy lại |
| Replay có lỗi schema | DDL không được replay hoặc restore sai phiên bản | Kiểm tra DDL, migration và thứ tự event |
| Dữ liệu vẫn sai sau PITR | Stop point nằm sau transaction hỏng hoặc transaction phụ thuộc đã được replay | Xác minh GTID/position và nội dung transaction |
| Mất giao dịch hợp lệ sau phục hồi | Chọn PITR toàn instance trước T_bad rồi cutover trực tiếp | Merge có chọn lọc hoặc replay/reconcile các giao dịch hợp lệ |
| Import bị chậm hoặc đầy disk | Recovery instance thiếu I/O/dung lượng | Tính lại tài nguyên, temp và log trước khi retry |
| Không thể khởi động physical restore | Chưa prepare, quyền file, cấu hình/plugin/encryption không phù hợp | Theo đúng quy trình công cụ backup |
| Ứng dụng đọc dữ liệu cũ | Replica/cache chưa được đồng bộ sau cutover | Xác minh replication, cache invalidation và read routing |

## 12. Những thao tác cần tránh

- Không restore backup trực tiếp đè lên production trong khi chưa có phương án cutover và rollback.
- Không purge binary log trong lúc xác định recovery point.
- Không replay binary log vượt qua transaction gây hỏng.
- Không dừng replay giữa transaction.
- Không dùng timestamp gần đúng làm mốc cuối cùng khi có thể xác định GTID/position.
- Không áp dụng file mysqlbinlog đã decode row event như SQL replay stream.
- Không merge nguyên bảng cũ nếu production đã có dữ liệu hợp lệ phát sinh sau sự cố.
- Không bỏ qua lỗi import/replay hoặc xem exit code lỗi là thành công.
- Không bật replica/read endpoint trước khi kiểm tra dữ liệu và lag.
- Không chỉnh GTID_PURGED hoặc binlog position để làm trạng thái hiển thị có vẻ đồng bộ.

## 13. Bài diễn tập end-to-end

### Chuẩn bị môi trường

Tạo một MySQL test instance với InnoDB và binary logging bật. Chuẩn bị database mẫu:

~~~sql
CREATE DATABASE recovery_lab;
USE recovery_lab;

CREATE TABLE customer (
  customer_id BIGINT PRIMARY KEY,
  full_name VARCHAR(120) NOT NULL,
  account_status VARCHAR(20) NOT NULL,
  updated_at TIMESTAMP(6) NOT NULL
    DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE = InnoDB;

CREATE TABLE orders (
  order_id BIGINT PRIMARY KEY,
  customer_id BIGINT NOT NULL,
  total_amount DECIMAL(12,2) NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES customer(customer_id)
) ENGINE = InnoDB;

INSERT INTO customer (customer_id, full_name, account_status)
VALUES
  (1, 'An Nguyen', 'ACTIVE'),
  (2, 'Binh Tran', 'ACTIVE'),
  (3, 'Chi Le', 'ACTIVE');

INSERT INTO orders (order_id, customer_id, total_amount)
VALUES (1001, 1, 250.00);
~~~

Tạo một full backup nhất quán và lưu metadata binlog/GTID cùng backup. Tiếp tục thực hiện một số giao dịch hợp lệ sau backup, ví dụ thêm order hoặc cập nhật địa chỉ nếu đã bổ sung cột. Sau đó thực hiện thao tác nhầm:

~~~sql
UPDATE customer
SET account_status = 'CLOSED';
~~~

Tiếp tục tạo một giao dịch hợp lệ sau thao tác nhầm để kiểm tra khả năng giữ lại dữ liệu sau sự cố. Ghi lại thời điểm, GTID hoặc position của transaction sai và transaction hợp lệ sau đó.

### Nhiệm vụ

1. Thu thập SHOW BINARY LOGS, SHOW BINARY LOG STATUS và GTID set.
2. Dùng mysqlbinlog decode để xác định transaction sai và transaction kế tiếp.
3. Restore full backup vào recovery instance cô lập.
4. Replay binary log từ metadata backup đến ngay trước transaction sai.
5. Xác minh toàn bộ customer trở lại ACTIVE ở recovery instance.
6. Xác định order hợp lệ được tạo sau transaction sai có còn ở recovery instance hay không.
7. So sánh với production và lập kế hoạch merge để phục hồi customer mà vẫn giữ order hợp lệ.
8. Chạy script merge trên staging copy, kiểm tra foreign key và invariant.
9. Đo thời gian restore, replay, validation và merge.
10. Viết lại runbook, bổ sung retention/alert nếu quy trình chưa đạt RPO/RTO.

### Tiêu chí hoàn thành

- Recovery instance được dựng từ backup đã xác minh.
- Binary log được replay liên tục từ đúng mốc backup.
- Transaction gây hỏng không được áp dụng.
- Transaction boundary được bảo toàn.
- Dữ liệu cần khôi phục được xác minh bằng truy vấn và invariant.
- Giao dịch hợp lệ sau sự cố được nhận diện và có kế hoạch giữ lại.
- Script merge có pre-check, post-check và rollback.
- RPO/RTO thực tế được ghi nhận.

## 14. Checklist vận hành

### Chuẩn bị trước sự cố

- [ ] Backup full được tạo theo lịch và có metadata nhất quán.
- [ ] Binary log được bật và retention phù hợp.
- [ ] Binary log archive có checksum và kiểm tra chuỗi file.
- [ ] Backup được restore thử định kỳ.
- [ ] Runbook PITR ghi rõ người thực hiện, người phê duyệt và recovery target.
- [ ] Recovery instance hoặc tài nguyên dự phòng có thể cấp phát trong RTO.
- [ ] Có dashboard cho dung lượng binlog, backup age và thời gian restore.

### Khi xảy ra sự cố

- [ ] Ghi timeline và transaction nghi ngờ.
- [ ] Bảo toàn binlog và audit/application log.
- [ ] Hạn chế ghi gây hỏng thêm.
- [ ] Chọn backup nhất quán và xác định recovery point.
- [ ] Restore trên instance cô lập.
- [ ] Replay đến trước transaction gây hỏng.
- [ ] Đối soát và merge theo phạm vi.
- [ ] Kiểm tra replication, cache và read routing sau cutover.

### Sau sự cố

- [ ] Xác nhận dữ liệu và invariant nghiệp vụ.
- [ ] Lưu bằng chứng, checksum, log replay và script merge.
- [ ] Ghi RPO/RTO thực tế và điểm nghẽn.
- [ ] Điều chỉnh retention, alert và quyền chạy migration/DDL.
- [ ] Cập nhật quy trình xác nhận câu lệnh nguy hiểm và review thao tác.
- [ ] Lên lịch diễn tập lại sau khi thay đổi backup hoặc kiến trúc.

## 15. Câu hỏi tự kiểm tra

1. PITR cần hai thành phần nào và vì sao backup riêng lẻ không đủ để phục hồi đến một thời điểm tùy ý?
2. Vì sao backup cần lưu kèm GTID hoặc binlog file/position?
3. --single-transaction của mysqldump bảo vệ loại bảng nào và giới hạn gì khi DDL chạy đồng thời?
4. Vì sao cần bảo toàn binary log ngay khi phát hiện thao tác nhầm?
5. Làm thế nào xác định transaction gây hỏng trong row-based binary log?
6. Vì sao stop position phải nằm ở ranh giới transaction?
7. Khi phục hồi bảng, tại sao không thể đơn giản thay toàn bộ bảng production bằng bản trước sự cố?
8. Transactional consistency của backup khác thời điểm file backup hoàn tất như thế nào?
9. RPO và RTO được đo ra sao trong một cuộc diễn tập PITR?
10. Những điều kiện nào phải đạt trước khi đưa dữ liệu phục hồi vào production?

PITR thành công không chỉ là làm cho mysqld khởi động hoặc replay không báo lỗi. Nhóm phải chứng minh backup có mốc nhất quán, binary log liên tục, transaction gây hỏng đã bị loại khỏi replay, dữ liệu được đối soát và các giao dịch hợp lệ sau sự cố được xử lý có chủ đích. Diễn tập định kỳ với số đo RPO/RTO thực tế là cách xác nhận quy trình có thể dùng được khi production gặp sự cố.
