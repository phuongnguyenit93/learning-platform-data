# Phân biệt logical backup, physical backup, restore và recovery

Bài học này thuộc module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời, sao lưu và phục hồi là năng lực bảo vệ dữ liệu khi có lỗi thao tác, hỏng thiết bị, sự cố phần mềm hoặc gián đoạn dịch vụ. Người vận hành cũng cần biết đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài học tập trung phân biệt hai cách tạo bản sao lưu phổ biến và hai giai đoạn đưa hệ thống trở lại hoạt động.

## 1. Bốn khái niệm cần phân biệt

Các thuật ngữ thường xuất hiện cùng nhau nhưng mô tả những việc khác nhau:

| Khái niệm | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| **Logical backup** | Xuất cấu trúc và dữ liệu thành biểu diễn logic như câu lệnh SQL hoặc định dạng dump có thể nạp lại | Cần lưu những database, bảng, schema và đối tượng nào? |
| **Physical backup** | Sao lưu các tệp dữ liệu vật lý và thông tin cần thiết để khôi phục chúng, chẳng hạn tablespace và redo log theo cơ chế của công cụ | Cần lưu những tệp nào để dựng lại dữ liệu ở cấp máy chủ hoặc storage engine? |
| **Restore** | Đưa dữ liệu từ bản sao lưu trở lại một máy chủ hoặc môi trường đích | Làm thế nào để nạp lại bản sao lưu? |
| **Recovery** | Đưa dữ liệu đã restore về trạng thái nhất quán và mục tiêu mong muốn, có thể bằng cách áp dụng redo hoặc binary log | Cần phát lại những thay đổi nào để đạt đúng thời điểm cần khôi phục? |

Ví dụ: đội vận hành tạo một bản physical backup vào lúc 01:00. Một người vô tình xóa dữ liệu lúc 10:15. Đội vận hành restore bản backup lúc 01:00 lên máy chủ phục hồi, sau đó áp dụng binary log đến 10:14:59. Việc restore đưa dữ liệu nền trở lại; việc recovery phát lại các thay đổi hợp lệ sau thời điểm backup để đạt trạng thái ngay trước sự cố.

**Restore không đồng nghĩa với recovery.** Restore có thể chỉ đưa hệ thống về thời điểm tạo backup. Recovery có thể cần thêm redo log, binary log hoặc thao tác sửa chữa phù hợp để hoàn tất trạng thái nhất quán hay đạt một thời điểm cụ thể.

## 2. Logical backup

Logical backup đọc cấu trúc và dữ liệu qua MySQL rồi ghi chúng thành các lệnh hoặc bản ghi logic. Khi restore, MySQL thực thi nội dung dump để tạo lại database, bảng, index, dữ liệu và những đối tượng được đưa vào bản sao lưu.

Các công cụ thường dùng gồm:

- `mysqldump`: công cụ dòng lệnh quen thuộc, tạo dump dạng SQL.
- MySQL Shell dump utilities như `util.dumpInstance()`, `util.dumpSchemas()` và `util.dumpTables()`: hỗ trợ dump theo phạm vi, chia dữ liệu thành các phần và nạp song song bằng `util.loadDump()`.
- Công cụ ETL hoặc công cụ xuất dữ liệu chuyên biệt: phù hợp với nhu cầu di chuyển hoặc trích xuất một phần dữ liệu, nhưng cần xác định rõ chúng có bảo toàn đầy đủ cấu trúc và metadata cần thiết hay không.

### 2.1. Tạo logical backup bằng `mysqldump`

Ví dụ dump một database InnoDB:

~~~bash
mysqldump \
  --host=db01.example.net \
  --user=backup_user \
  --password \
  --default-character-set=utf8mb4 \
  --single-transaction \
  --routines \
  --events \
  --databases shop \
  > shop.sql
~~~

Giải thích các tùy chọn:

- `--password` yêu cầu nhập mật khẩu tương tác; tránh ghi mật khẩu trực tiếp vào câu lệnh hoặc script dễ bị lộ trong lịch sử và danh sách tiến trình.
- `--default-character-set=utf8mb4` đặt bộ ký tự cho kết nối dump.
- `--single-transaction` tạo consistent snapshot cho các bảng transactional như InnoDB mà không cần khóa đọc kéo dài trên toàn bộ quá trình dump.
- `--routines` đưa stored procedure và function vào dump.
- `--events` đưa Event Scheduler events vào dump.
- `--databases shop` dump database cùng các lệnh tạo/chọn database phù hợp khi nạp lại.

`mysqldump` mặc định có dump trigger, trừ khi dùng tùy chọn bỏ trigger. Dù vậy, cần kiểm tra nội dung dump và danh sách đối tượng sau khi restore để bảo đảm các đối tượng ứng dụng thực sự được mang theo.

`--single-transaction` có giới hạn quan trọng:

1. Snapshot nhất quán chỉ áp dụng cho các bảng hỗ trợ transaction, điển hình là InnoDB. Bảng MyISAM hoặc storage engine không transactional có thể thay đổi trong lúc dump và không có cùng bảo đảm snapshot.
2. Không nên chạy các thay đổi DDL như `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE` hoặc `TRUNCATE TABLE` trên những bảng đang được dump. Hãy phối hợp lịch dump với hoạt động triển khai schema.
3. Quyền của tài khoản dump phải đủ để đọc dữ liệu và metadata của những đối tượng được yêu cầu. Các tùy chọn hoặc tính năng đặc biệt có thể cần thêm quyền tùy phiên bản và cấu hình.

Với database lớn, `mysqldump` có thể tạo một tệp SQL lớn và thời gian restore lâu vì máy chủ phải thực thi lại nhiều câu lệnh. MySQL Shell dump utilities có thể chia dữ liệu thành nhiều chunk và nạp song song, nhưng cần kiểm tra khả năng tương thích phiên bản, quyền và định dạng dump trước khi đưa vào quy trình vận hành.

### 2.2. Restore logical backup

Với dump được tạo bằng `--databases shop`, có thể nạp lại bằng MySQL client:

~~~bash
mysql \
  --host=db-restore.example.net \
  --user=restore_user \
  --password \
  < shop.sql
~~~

Nếu dump chỉ chứa nội dung của một schema và không có lệnh tạo/chọn database, cần tạo database đích rồi chỉ định schema khi nạp:

~~~sql
CREATE DATABASE shop_restore
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

~~~bash
mysql --host=db-restore.example.net --user=restore_user \
  --password shop_restore < shop-data.sql
~~~

Không nên restore thẳng lên production trước khi xác minh phạm vi ghi đè. Một dump có thể chứa `DROP TABLE`, `CREATE TABLE`, `USE` hoặc các lệnh thay đổi đối tượng. Hãy đọc phần đầu và kiểm tra nội dung dump, thử restore trên môi trường cô lập, rồi mới lập kế hoạch chuyển đổi.

### 2.3. Điểm mạnh và giới hạn của logical backup

| Điểm mạnh | Giới hạn |
|---|---|
| Dễ kiểm tra vì dữ liệu và cấu trúc có dạng logic, thường là SQL | Restore có thể chậm với lượng dữ liệu lớn |
| Có thể dump một database, một số bảng hoặc một tập đối tượng | Cần bảo đảm đã chọn đủ view, trigger, routine, event và metadata liên quan |
| Thuận tiện khi di chuyển giữa môi trường hoặc phiên bản tương thích | Không phải lúc nào cũng giữ nguyên mọi thuộc tính vật lý, layout hoặc trạng thái nội bộ của máy chủ |
| Có thể chọn lọc, biến đổi dữ liệu trong quá trình xuất/nạp | Không tự động thay thế việc lưu binary log để phục hồi đến một thời điểm |

Logical backup phù hợp cho database nhỏ và vừa, di chuyển schema, sao lưu chọn lọc và những trường hợp cần khả năng đọc/kiểm tra nội dung. Với hệ thống lớn, cần đo thời gian dump và restore thực tế để xác định có đáp ứng RTO hay không.

## 3. Physical backup

Physical backup sao lưu dữ liệu ở dạng tệp mà MySQL và storage engine sử dụng. Với InnoDB, bộ backup thường phải xử lý tablespace, metadata và redo log để tạo ra một tập tệp có thể phục hồi nhất quán. Tùy công cụ và phương thức, bản backup có thể bao gồm toàn bộ instance hoặc một phạm vi vật lý được công cụ hỗ trợ.

Các lựa chọn phổ biến:

- **MySQL Enterprise Backup**: công cụ backup vật lý của MySQL Enterprise Edition.
- **Percona XtraBackup**: công cụ bên thứ ba thường dùng cho backup vật lý InnoDB; phải kiểm tra ma trận tương thích với phiên bản MySQL, Percona Server và định dạng dữ liệu đang vận hành.
- **Cold backup**: dừng MySQL sạch sẽ rồi sao chép đầy đủ các tệp dữ liệu cần thiết. Đây là cách sao chép ở cấp tệp đơn giản hơn, nhưng gây downtime trong thời gian thực hiện.

### 3.1. Hot backup và cold backup

Physical backup có thể được thực hiện khi máy chủ đang chạy hoặc sau khi máy chủ đã dừng, tùy công cụ:

- **Hot backup** diễn ra khi MySQL tiếp tục phục vụ truy vấn. Công cụ phải phối hợp với storage engine và redo log để xử lý những trang dữ liệu thay đổi trong lúc sao chép. Không thể coi việc sao chép tùy tiện thư mục data khi máy chủ đang chạy là hot backup hợp lệ.
- **Cold backup** yêu cầu dừng MySQL một cách có kiểm soát trước khi sao chép. Khi máy chủ đã dừng hoàn toàn, các tệp dữ liệu không còn bị tiến trình MySQL ghi tiếp. Cần bảo đảm đã sao chép đủ các tệp cần thiết và giữ lại cấu hình, keyring cùng metadata liên quan ở nơi an toàn.

Một bản sao thư mục data được tạo bằng cách copy thủ công khi MySQL vẫn đang chạy có thể chứa các tệp ở những thời điểm khác nhau. Các trang dữ liệu, redo log và metadata có thể không khớp nhau; kết quả có thể không khởi động được hoặc không nhất quán. Chỉ dùng quy trình sao chép online nếu công cụ được thiết kế để tạo backup nhất quán.

### 3.2. Quy trình vật lý tổng quát

Tên lệnh cụ thể khác nhau giữa MySQL Enterprise Backup, Percona XtraBackup và các công cụ khác. Tuy nhiên, một quy trình vật lý thường gồm các bước:

1. Kiểm tra phiên bản máy chủ, storage engine, dung lượng đích và ma trận tương thích của công cụ.
2. Chọn phạm vi backup, kiểu full hoặc incremental và vị trí lưu trữ.
3. Chạy công cụ backup theo chế độ được hỗ trợ; công cụ ghi lại metadata và xử lý các thay đổi phát sinh trong lúc sao chép.
4. Nếu công cụ yêu cầu, chạy bước prepare để áp dụng redo log và đưa tập backup về trạng thái nhất quán có thể restore.
5. Kiểm tra mã thoát, log, metadata, kích thước và tính toàn vẹn của bộ backup.
6. Chuyển bản backup sang nơi lưu trữ độc lập với máy chủ nguồn và bảo vệ bằng mã hóa, quyền truy cập phù hợp.
7. Thử restore trên máy chủ khác hoặc môi trường phục hồi định kỳ.

Không dùng các lệnh vật lý của một công cụ cho công cụ khác. Ví dụ, cú pháp backup, prepare và copy-back của Percona XtraBackup khác với quy trình restore của MySQL Enterprise Backup. Hãy theo đúng tài liệu của phiên bản công cụ đang triển khai.

### 3.3. Restore physical backup

Một quy trình restore vật lý điển hình có các bước:

1. Chuẩn bị máy chủ đích tương thích về phiên bản, kiến trúc, cấu hình và các thành phần cần thiết.
2. Dừng MySQL trên máy chủ đích trước khi thay thế data directory.
3. Đưa tập backup đã prepare vào vị trí mà công cụ yêu cầu; bảo đảm quyền sở hữu và quyền truy cập tệp đúng với tài khoản chạy MySQL.
4. Khôi phục các thành phần phụ trợ cần thiết như keyring hoặc khóa mã hóa, cấu hình tương ứng và những tệp nằm ngoài phạm vi backup.
5. Khởi động MySQL, theo dõi error log và để InnoDB hoàn tất crash recovery nếu cần.
6. Xác minh database, bảng, đối tượng, quyền và trạng thái ứng dụng trước khi chuyển traffic.

Physical restore thường phù hợp khi cần khôi phục nhanh một instance hoặc tập dữ liệu lớn. Nó có thể phụ thuộc chặt vào phiên bản MySQL, định dạng tệp, cấu hình và công cụ đã tạo backup. Restore một phần database có thể cần dựng bản backup lên instance tạm, sau đó xuất logic phần cần lấy sang hệ thống đích.

### 3.4. Những thành phần dễ bị bỏ sót

Data directory không nhất thiết chứa mọi thứ cần để vận hành lại hệ thống. Hãy kiểm kê riêng:

- Cấu hình máy chủ, chẳng hạn tệp cấu hình, tham số InnoDB, đường dẫn data và log.
- Keyring hoặc hệ thống quản lý khóa nếu database dùng tablespace hay dữ liệu được mã hóa. Có tệp dữ liệu mà mất khóa tương ứng vẫn có thể không đọc được dữ liệu.
- Binary log và metadata xác định vị trí log hoặc GTID tại thời điểm backup.
- Chứng thư TLS, cấu hình xác thực, plugin, component và các thành phần ngoài data directory.
- Tài khoản, role, grant và thông tin định danh cần thiết để ứng dụng kết nối.

Phạm vi thực tế phụ thuộc công cụ. Đọc manifest và tài liệu của công cụ để biết chính xác những gì đã được sao lưu; đừng mặc định rằng một bản physical backup tự chứa toàn bộ cấu hình vận hành.

## 4. So sánh logical backup và physical backup

| Tiêu chí | Logical backup | Physical backup |
|---|---|---|
| Đơn vị lưu | Cấu trúc và dữ liệu logic | Tệp dữ liệu, tablespace và thông tin vật lý liên quan |
| Cách restore | Thực thi dump hoặc nạp các chunk | Đưa tệp backup về vị trí phù hợp theo quy trình của công cụ |
| Tốc độ với dữ liệu lớn | Thường chậm hơn do phải đọc/xuất và thực thi lại dữ liệu | Thường nhanh hơn khi backup và restore ở cấp tệp |
| Khả năng chọn lọc | Thuận tiện cho schema, bảng hoặc đối tượng cụ thể | Thường hướng tới instance hoặc phạm vi vật lý mà công cụ hỗ trợ |
| Khả năng di chuyển | Thường linh hoạt hơn giữa các môi trường tương thích | Phụ thuộc phiên bản, storage engine, định dạng và công cụ |
| Kiểm tra nội dung | Có thể đọc và rà soát dump | Cần công cụ kiểm tra, metadata và thử restore |
| Yêu cầu vận hành | Cần đủ quyền đọc và nạp đối tượng | Cần hiểu data directory, engine, redo, quyền tệp và thành phần phụ trợ |

Không có một loại backup phù hợp cho mọi tình huống. Một chiến lược thực tế thường kết hợp physical backup để phục hồi nhanh hệ thống lớn, logical backup cho khả năng khôi phục chọn lọc hoặc di chuyển dữ liệu, và binary log để phục hồi đến thời điểm mong muốn.

## 5. Recovery và point-in-time recovery (PITR)

Một full backup chỉ phản ánh dữ liệu tại thời điểm bản backup được tạo. Nếu sự cố xảy ra sau đó, các giao dịch hợp lệ phát sinh giữa thời điểm backup và thời điểm sự cố có thể chưa nằm trong bản backup. MySQL binary log (binlog) ghi lại các sự kiện thay đổi dữ liệu và cấu trúc theo cấu hình máy chủ, cho phép phát lại những thay đổi sau khi restore.

**Point-in-time recovery (PITR)** là phục hồi dữ liệu đến một thời điểm xác định, thường là ngay trước một thao tác gây lỗi. Quy trình cơ bản:

1. Chọn full backup gần nhất đã kiểm tra và biết rõ metadata về binary log hoặc GTID tại thời điểm backup.
2. Restore full backup lên máy chủ phục hồi.
3. Xác định chuỗi binary log liên tục bắt đầu từ vị trí sau backup.
4. Dùng `mysqlbinlog` để đọc và phát lại các sự kiện đến thời điểm mục tiêu hoặc đến vị trí ngay trước sự cố.
5. Kiểm tra dữ liệu và ứng dụng; chỉ chuyển traffic khi đã xác nhận kết quả.

Ví dụ minh họa việc xem binary log:

~~~bash
mysqlbinlog --start-datetime="2026-11-19 01:00:00" \
            --stop-datetime="2026-11-19 10:14:59" \
            binlog.000120 binlog.000121 > replay.sql
~~~

Sau khi kiểm tra phạm vi sự kiện trong `replay.sql`, có thể phát lại vào máy chủ phục hồi:

~~~bash
mysql --host=db-restore.example.net \
      --user=recovery_user --password < replay.sql
~~~

Đây là ví dụ về cách giới hạn theo thời gian. Trong quy trình thật, cần dùng chính xác file, vị trí bắt đầu hoặc GTID được ghi nhận trong metadata của backup; chỉ định đủ các file binlog liên tiếp theo thứ tự; và xác minh múi giờ, thời điểm sự cố cùng độ chính xác của timestamp. Khi cần độ chính xác cao, giới hạn bằng log position hoặc GTID thường đáng tin cậy hơn chỉ dựa vào thời gian.

Không phát lại mù quáng toàn bộ binlog. Nếu sự cố là một câu lệnh `DROP TABLE` lúc 10:15, cần xác định ranh giới sự kiện và dừng trước thao tác đó. Có thể restore lên một instance riêng, xác minh dữ liệu cần giữ rồi mới quyết định cách đưa dữ liệu trở lại production.

### 5.1. Điều kiện để PITR hoạt động

- Binary logging phải được bật trước khi các thay đổi cần phục hồi xảy ra.
- Binlog phải được lưu giữ đủ lâu và sao chép ra nơi độc lập với máy chủ nguồn.
- Cần biết điểm bắt đầu phát lại của backup, thông qua file/position hoặc GTID metadata.
- Chuỗi log phải liên tục, đầy đủ và không bị mất hoặc hỏng.
- Phải kiểm soát chính xác điểm dừng để không phát lại thao tác gây lỗi.

Có thể kiểm tra binary logging và danh sách log bằng:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW BINARY LOGS;
~~~

Tên câu lệnh và cách hiển thị metadata có thể thay đổi theo phiên bản MySQL. Hãy dùng lệnh được phiên bản máy chủ hỗ trợ và lưu thông tin vị trí log cùng bản backup. Nếu chỉ lưu full backup mà không giữ binary log, khả năng phục hồi thường bị giới hạn ở thời điểm của backup đó.

## 6. Thiết kế chiến lược backup theo RPO và RTO

Hai chỉ số giúp biến yêu cầu kinh doanh thành lịch backup cụ thể:

- **RPO (Recovery Point Objective)**: mức mất dữ liệu tối đa mà tổ chức chấp nhận, thường biểu diễn bằng khoảng thời gian. RPO 15 phút nghĩa là mục tiêu không mất quá 15 phút dữ liệu.
- **RTO (Recovery Time Objective)**: thời gian tối đa chấp nhận để khôi phục dịch vụ. RTO 1 giờ nghĩa là cần đưa dịch vụ trở lại trong vòng một giờ.

Ví dụ, một ứng dụng bán hàng đặt RPO 5 phút và RTO 30 phút. Chỉ tạo logical dump mỗi đêm có thể không đáp ứng RPO, đồng thời restore toàn bộ dump có thể vượt RTO. Có thể cần physical full backup định kỳ, incremental backup theo công cụ hỗ trợ và sao chép binary log liên tục sang hệ thống độc lập. Sau đó phải diễn tập để đo thời gian restore và PITR thực tế.

Một lịch tham khảo cho hệ thống cần khả năng phục hồi tốt:

| Thành phần | Lịch tham khảo | Mục đích |
|---|---|---|
| Physical full backup | Hằng ngày hoặc theo cửa sổ phù hợp | Tạo điểm phục hồi nền cho toàn instance |
| Physical incremental backup | Theo chu kỳ trong ngày, nếu công cụ hỗ trợ | Giảm lượng dữ liệu phải sao lưu mỗi lần |
| Binary log | Thu thập và chuyển ra nơi khác liên tục | PITR và giảm khoảng mất dữ liệu |
| Logical backup | Theo lịch hoặc trước/sau thay đổi lớn | Khôi phục chọn lọc, kiểm tra và di chuyển dữ liệu |
| Restore drill | Định kỳ và sau thay đổi lớn của quy trình | Đo RTO, xác minh backup và hướng dẫn vận hành |

Lịch này chỉ là điểm bắt đầu. Cần điều chỉnh theo dung lượng, tốc độ thay đổi dữ liệu, chi phí lưu trữ, cửa sổ bảo trì, yêu cầu pháp lý và kết quả diễn tập.

### 6.1. Quy tắc lưu trữ và bảo vệ backup

Một chiến lược tốt cần bảo vệ cả bản backup lẫn khả năng truy cập nó:

1. Giữ nhiều bản sao trên các miền lỗi khác nhau; không để bản duy nhất trên cùng máy chủ hoặc cùng storage với dữ liệu gốc.
2. Dùng mã hóa khi truyền và khi lưu trữ, quản lý khóa tách biệt và kiểm soát người có quyền giải mã.
3. Hạn chế quyền đọc, ghi và xóa backup; cân nhắc kho lưu trữ bất biến hoặc cơ chế chống xóa ngoài ý muốn.
4. Theo dõi dung lượng, thời gian hoàn tất, mã thoát, lỗi công cụ và tuổi của bản backup gần nhất.
5. Đặt retention phù hợp, bảo đảm các binary log cần thiết còn tồn tại trong toàn bộ khoảng PITR dự kiến.
6. Sao lưu và thử phục hồi keyring, cấu hình và thông tin xác thực cần thiết cùng quy trình dữ liệu.

Replication giúp tăng tính sẵn sàng và phân tải đọc, nhưng không thay thế backup. Một lệnh xóa nhầm hoặc dữ liệu bị mã hóa độc hại có thể được truyền sang replica; backup độc lập và khả năng PITR vẫn cần thiết.

## 7. Quy trình xử lý một sự cố phục hồi

Giả sử ứng dụng phát hiện dữ liệu đơn hàng bị xóa nhầm lúc 10:15. Có full backup lúc 01:00 và binary log được lưu liên tục. Quy trình có thể thực hiện như sau:

1. **Khoanh vùng sự cố:** dừng hoặc hạn chế các tác vụ có thể tiếp tục ghi sai dữ liệu; ghi lại thời điểm phát hiện và khoảng thời gian thao tác lỗi có thể đã xảy ra.
2. **Bảo toàn bằng chứng:** giữ bản sao binlog, log ứng dụng và thông tin vận hành liên quan; tránh ghi đè lên các tệp cần điều tra.
3. **Chọn điểm phục hồi:** xác định backup gần nhất còn tốt, kiểm tra metadata và chuỗi binlog từ điểm backup đến trước sự cố.
4. **Restore vào môi trường cô lập:** không vội ghi đè production. Dựng một máy phục hồi tương thích và kiểm tra khả năng khởi động.
5. **Recovery đến thời điểm mục tiêu:** phát lại log đến ngay trước sự kiện gây lỗi, hoặc đến điểm phù hợp đã được xác nhận.
6. **Xác minh dữ liệu:** kiểm tra đơn hàng, khóa ngoại logic ở tầng ứng dụng, số lượng bản ghi, tổng tiền và các nghiệp vụ liên quan.
7. **Đưa dữ liệu trở lại dịch vụ:** chọn phương án chuyển đổi phù hợp, chẳng hạn phục hồi toàn instance hoặc trích xuất các bảng/bản ghi cần thiết từ máy phục hồi.
8. **Theo dõi sau phục hồi:** kiểm tra lỗi MySQL, độ trễ, kết nối, job nền và tính đúng đắn của dữ liệu sau khi mở lại traffic.
9. **Rút kinh nghiệm:** ghi lại thời gian thực tế, nguyên nhân, điểm thiếu trong backup và cập nhật runbook.

Việc phục hồi một phần dữ liệu vào production đang hoạt động có thể phức tạp do các bảng liên quan và giao dịch mới phát sinh. Hãy xác định rõ khóa chính, quan hệ dữ liệu, thứ tự nạp và cách xử lý xung đột trước khi merge dữ liệu từ máy phục hồi.

## 8. Kiểm tra một bản backup có thể sử dụng

Thông báo “backup completed” hoặc tệp có kích thước lớn chưa chứng minh rằng có thể restore. Một bản backup chỉ đáng tin khi có thể khôi phục và kiểm tra kết quả.

Checklist kiểm tra:

- [ ] Công cụ kết thúc thành công; log không có lỗi hoặc cảnh báo chưa được xử lý.
- [ ] Bản backup có metadata, manifest, checksum hoặc cơ chế xác minh toàn vẹn tương ứng với công cụ.
- [ ] Tệp backup đã được chuyển ra nơi lưu trữ độc lập và có thể đọc được.
- [ ] Binary log, GTID hoặc vị trí log cần thiết cho PITR được lưu giữ cùng thông tin tham chiếu.
- [ ] Khóa mã hóa, keyring, cấu hình và phiên bản công cụ cần thiết đã được bảo vệ.
- [ ] Restore thử trên môi trường cô lập hoàn tất trong thời gian mục tiêu.
- [ ] Database, bảng, index, routine, trigger, event và quyền cần thiết có mặt sau restore.
- [ ] Ứng dụng chạy được các luồng nghiệp vụ quan trọng trên dữ liệu đã phục hồi.
- [ ] Người vận hành biết nơi lấy backup, cách lấy khóa và cách thực hiện từng bước trong runbook.

Sau restore, có thể kiểm tra nhanh bằng SQL:

~~~sql
SHOW DATABASES;

USE shop;
SHOW FULL TABLES;

SELECT COUNT(*) AS order_count
FROM orders;

SHOW TRIGGERS FROM shop;
SHOW EVENTS FROM shop;
~~~

Các câu lệnh này chỉ là kiểm tra ban đầu. Số lượng bản ghi đúng chưa chắc dữ liệu đúng; cần thêm đối chiếu checksum, tổng hợp nghiệp vụ, tính nhất quán giữa các bảng và kiểm thử ứng dụng. Một lần restore thử thành công cũng cần được lặp lại định kỳ vì cấu hình, phiên bản và quy trình vận hành có thể thay đổi.

## 9. Tự kiểm tra

1. Một tệp `mysqldump` chứa câu lệnh SQL thuộc loại backup nào? Vì sao?
2. Vì sao không nên dùng thao tác copy thư mục data đang hoạt động như một physical hot backup?
3. `--single-transaction` có bảo đảm snapshot nhất quán cho bảng MyISAM không? Cần lưu ý gì với DDL trong lúc dump?
4. Khi restore physical backup, vì sao phải quan tâm phiên bản MySQL, quyền sở hữu tệp và keyring?
5. Nếu chỉ restore full backup lúc 01:00 mà không phát lại binary log, dữ liệu sau 01:00 có được khôi phục không?
6. Để phục hồi đến ngay trước một lệnh xóa nhầm lúc 10:15, cần những thông tin nào về backup và binlog?
7. Vì sao replica không thay thế được backup độc lập?
8. Hãy đề xuất một lịch backup đáp ứng RPO 15 phút và RTO 1 giờ, rồi nêu cách diễn tập để chứng minh lịch đó đáp ứng yêu cầu.

Khi trả lời, hãy phân biệt rõ bản sao lưu nền, thao tác đưa bản sao lưu trở lại máy chủ và bước phát lại log để đạt điểm phục hồi. Hãy dùng kết quả restore drill cùng số liệu thời gian thực tế để đánh giá RPO và RTO, thay vì chỉ dựa trên lịch chạy backup.
