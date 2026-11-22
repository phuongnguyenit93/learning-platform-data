# Xác định RPO/RTO và xây dựng kế hoạch kiểm chứng phục hồi

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt RPO, RTO, thời gian phát hiện sự cố và thời gian phục hồi dịch vụ.
- Chuyển yêu cầu nghiệp vụ thành mục tiêu phục hồi có thể đo lường cho từng hệ thống MySQL.
- Chọn chiến lược sao lưu, lưu binary log và phục hồi theo thời điểm phù hợp với RPO/RTO.
- Tính thời gian phục hồi dự kiến từ các bước và phụ thuộc thực tế.
- Thiết kế bài kiểm thử restore, diễn tập sự cố và tiêu chí nghiệm thu có bằng chứng.
- Duy trì kế hoạch phục hồi, người chịu trách nhiệm và quy trình cập nhật khi hệ thống thay đổi.

## 1. Vì sao cần xác định RPO và RTO?

Sao lưu chỉ có giá trị vận hành khi tổ chức biết mình cần khôi phục dữ liệu đến thời điểm nào và cần đưa dịch vụ trở lại trong bao lâu. Hai câu hỏi đó tương ứng với **Recovery Point Objective (RPO)** và **Recovery Time Objective (RTO)**.

- **RPO — mục tiêu điểm phục hồi:** lượng dữ liệu tối đa mà doanh nghiệp chấp nhận mất, tính theo thời gian trước thời điểm sự cố. RPO 15 phút nghĩa là khi phải phục hồi, dữ liệu có thể thiếu tối đa khoảng 15 phút giao dịch gần nhất.
- **RTO — mục tiêu thời gian phục hồi:** khoảng thời gian tối đa chấp nhận được để khôi phục dịch vụ về mức hoạt động đã xác định sau sự cố. RTO 2 giờ nghĩa là dịch vụ phải đạt tiêu chí hoạt động trong vòng 2 giờ kể từ mốc bắt đầu được quy định trong kế hoạch.

Hai mục tiêu này độc lập. Một hệ thống có thể phục hồi trong 10 phút nhưng mất dữ liệu của 6 giờ trước đó; RTO tốt không đồng nghĩa RPO tốt. Ngược lại, có thể giữ được dữ liệu gần như đến thời điểm sự cố nhưng mất cả ngày để dựng máy chủ và kiểm tra ứng dụng.

Ví dụ, một cửa hàng trực tuyến có thể đặt mục tiêu:

| Nhóm dịch vụ | RPO mục tiêu | RTO mục tiêu | Lý do |
|---|---:|---:|---|
| Đơn hàng và thanh toán | 5 phút | 1 giờ | Mất giao dịch ảnh hưởng trực tiếp đến khách hàng và đối soát |
| Tồn kho | 15 phút | 2 giờ | Cần khôi phục nhanh để tránh bán vượt tồn kho |
| Báo cáo nội bộ | 24 giờ | 1 ngày làm việc | Có thể tái tạo một phần từ dữ liệu giao dịch sau khi hệ thống chính ổn định |

Các con số trên chỉ minh họa cách phân nhóm. Chủ sở hữu nghiệp vụ, bộ phận vận hành, bảo mật và quản lý rủi ro phải thống nhất mục tiêu dựa trên tác động kinh doanh, nghĩa vụ pháp lý, chi phí và khả năng kỹ thuật.

## 2. Hiểu đúng các mốc thời gian

Để đo RPO/RTO, trước tiên cần thống nhất thời điểm bắt đầu và kết thúc. Một kế hoạch có thể dùng các mốc sau:

1. **T0 — sự cố bắt đầu:** dữ liệu bị xóa nhầm, đĩa hỏng, máy chủ mất kết nối hoặc dấu hiệu xâm nhập xuất hiện. Có sự cố chỉ được phát hiện sau một khoảng trễ.
2. **T1 — phát hiện và xác nhận:** hệ thống giám sát hoặc người vận hành phát hiện, phân loại mức độ và xác nhận cần phục hồi.
3. **T2 — quyết định và khởi động kế hoạch:** người có thẩm quyền tuyên bố sự cố, chọn phương án khôi phục và phân công vai trò.
4. **T3 — hạ tầng sẵn sàng:** máy chủ, lưu trữ, mạng, DNS, chứng chỉ và bí mật cần thiết đã sẵn sàng.
5. **T4 — dữ liệu được phục hồi:** bản sao lưu đã nạp, binary log đã phát lại đến điểm đích và các kiểm tra nhất quán ban đầu đã hoàn tất.
6. **T5 — ứng dụng được xác minh:** kiểm tra chức năng, dữ liệu, quyền, tích hợp và tải đại diện đạt yêu cầu.
7. **T6 — dịch vụ được đưa trở lại:** lưu lượng được chuyển về hệ thống phục hồi và các bên liên quan được thông báo.

Tổ chức có thể định nghĩa RTO từ T0 hoặc T1 đến T6. Điều quan trọng là phải ghi rõ mốc dùng để đo, vì thời gian phát hiện sự cố cũng có thể kéo dài và gây thiệt hại. RTO thường được theo dõi cùng thời gian phát hiện (MTTD) và thời gian khắc phục (MTTR), nhưng các chỉ số này không thay thế mục tiêu RTO.

RPO cũng phải có mốc tham chiếu rõ ràng. Khi sự cố xảy ra lúc 14:00 và bản phục hồi tốt nhất chứa giao dịch đã commit đến 13:54, độ trễ điểm phục hồi là 6 phút. Nếu RPO là 5 phút thì lần phục hồi đó không đạt, dù máy chủ đã hoạt động lại rất nhanh.

## 3. Chuyển yêu cầu nghiệp vụ thành mục tiêu có thể đo

Không nên chọn RPO/RTO chỉ vì công cụ backup có thể chạy mỗi giờ hoặc vì một máy chủ có thể restore trong 30 phút. Hãy bắt đầu từ tác động kinh doanh.

### 3.1. Xác định tác động khi dịch vụ ngừng

Với mỗi hệ thống MySQL, trao đổi với chủ sở hữu nghiệp vụ về:

- Chức năng nào ngừng hoạt động khi cơ sở dữ liệu không sẵn sàng?
- Bao nhiêu người dùng, đơn hàng, giao dịch hoặc quy trình nội bộ bị ảnh hưởng?
- Dữ liệu nào có thể tái tạo từ nguồn khác, dữ liệu nào không thể tái tạo?
- Mất dữ liệu trong 5 phút, 1 giờ hoặc 1 ngày gây hậu quả gì?
- Hệ thống phụ thuộc nào phải hoạt động trước khi ứng dụng có thể mở lại?
- Có thời hạn pháp lý, yêu cầu kiểm toán, đối soát hoặc cam kết hợp đồng nào không?

Một phân tích tác động kinh doanh (Business Impact Analysis — BIA) giúp phân loại dịch vụ theo mức độ ưu tiên và thời gian gián đoạn chấp nhận được. Đưa cả tác động tích lũy theo thời gian vào đánh giá: ngừng 10 phút có thể chấp nhận, nhưng ngừng 8 giờ có thể làm lỡ toàn bộ chu kỳ xử lý trong ngày.

### 3.2. Chọn RPO theo khả năng mất dữ liệu

Xác định loại dữ liệu và cách có thể phục hồi:

- Dữ liệu giao dịch đã commit cần được giữ đến thời điểm gần sự cố nhất.
- Dữ liệu có thể tính lại từ hệ thống nguồn có thể có RPO lớn hơn, nếu quy trình tái tạo được kiểm thử.
- Dữ liệu được đồng bộ từ hệ thống khác cần xác định nguồn nào là dữ liệu chuẩn và cách xử lý giao dịch đã gửi nhưng chưa nhận xác nhận.

RPO không đơn giản bằng tần suất chạy full backup. Với MySQL, một bản backup nền kết hợp việc lưu binary log liên tục có thể cho phép phục hồi đến thời điểm gần cuối cùng mà log đã được lưu an toàn. RPO thực tế phụ thuộc vào độ trễ tạo, truyền, xác nhận và bảo vệ các bản log đó.

Ví dụ: full backup chạy mỗi đêm, binary log được chuyển sang kho lưu trữ mỗi 2 phút. Nếu log chỉ được xác nhận đã lưu bền vững đến 13:56 khi sự cố xảy ra lúc 14:00, RPO thực tế xấp xỉ 4 phút, với điều kiện bản backup nền và toàn bộ chuỗi log cần thiết đều đọc được. Nếu việc chuyển log bị gián đoạn 20 phút, RPO đã vượt mục tiêu 5 phút dù lịch backup đêm vẫn chạy thành công.

### 3.3. Chọn RTO theo toàn bộ quy trình

RTO phải bao gồm tất cả bước cần thiết để người dùng sử dụng được dịch vụ, không chỉ thời gian chạy lệnh restore. Ví dụ, thời gian khôi phục có thể gồm:

| Công đoạn | Thời gian dự kiến |
|---|---:|
| Phát hiện, xác nhận và quyết định | 10 phút |
| Cấp máy chủ và cấu hình lưu trữ | 15 phút |
| Lấy backup và phục hồi dữ liệu | 25 phút |
| Phát lại binary log | 15 phút |
| Kiểm tra dữ liệu, quyền và ứng dụng | 20 phút |
| Chuyển lưu lượng và theo dõi | 10 phút |
| **Tổng dự kiến** | **95 phút** |

Nếu RTO là 90 phút thì phương án trên chưa đạt, kể cả khi mỗi công đoạn có vẻ nhanh. Cần giảm thời gian ở một hoặc nhiều bước, chuẩn bị hạ tầng sẵn, giảm lượng log phải phát lại, cải thiện tốc độ đọc backup hoặc rút gọn quy trình phê duyệt trong tình huống khẩn cấp. Cũng cần có biên dự phòng cho sự cố thứ cấp như thiếu dung lượng, lỗi quyền truy cập kho backup hoặc lỗi DNS.

## 4. Chọn kiến trúc backup phù hợp với mục tiêu

Không có một kiểu backup đáp ứng tốt mọi RPO/RTO. Hãy kết hợp các phương pháp và thử phục hồi từ chính các bản sao sẽ dùng khi xảy ra sự cố.

### 4.1. Logical backup

Logical backup xuất cấu trúc và dữ liệu thành câu lệnh SQL hoặc định dạng logic. Ví dụ thường gặp là `mysqldump`:

```bash
mysqldump --host=db-primary.example.internal \
  --user=backup_user --password \
  --single-transaction --routines --events --triggers \
  --databases sales_app > sales_app.sql
```

`--single-transaction` tạo snapshot nhất quán cho các bảng InnoDB trong một transaction; nó không bảo đảm snapshot nhất quán cho bảng không hỗ trợ transaction. Trong lúc dump, các thao tác DDL như `ALTER TABLE`, `DROP TABLE` hoặc `RENAME TABLE` có thể ảnh hưởng đến tính nhất quán và cần được kiểm soát. Các đối tượng như routine, event và trigger phải được đưa vào rõ ràng nếu cần phục hồi chúng.

Ưu điểm của logical backup là dễ di chuyển giữa một số phiên bản hoặc cấu trúc máy chủ và có thể phục hồi chọn lọc. Nhược điểm là restore thường chậm với dữ liệu lớn vì máy chủ phải thực thi nhiều câu lệnh SQL, tạo index và ghi từng hàng. Hãy đo thời gian trên kích thước dữ liệu thực tế.

### 4.2. Physical backup

Physical backup sao chép các tệp dữ liệu, tablespace, redo log và thành phần cần thiết của InnoDB theo quy trình nhất quán của công cụ. Công cụ có thể là MySQL Enterprise Backup hoặc Percona XtraBackup; cần tuân thủ tài liệu đúng phiên bản công cụ và MySQL Server.

Physical backup thường phục hồi nhanh hơn với cơ sở dữ liệu lớn vì tránh phải nạp lại từng câu lệnh SQL. Tuy nhiên, nó có yêu cầu tương thích phiên bản, cấu trúc lưu trữ và quy trình prepare/restore riêng. Không được tùy tiện sao chép thư mục dữ liệu đang chạy bằng lệnh copy thông thường rồi xem đó là bản backup nhất quán.

### 4.3. Full, incremental và snapshot

- **Full backup:** chứa toàn bộ dữ liệu thuộc phạm vi backup. Dễ hiểu và là điểm nền để phục hồi, nhưng có thể tốn thời gian và dung lượng.
- **Incremental backup:** chỉ lưu phần thay đổi kể từ một mốc backup trước đó. Tiết kiệm dung lượng và thời gian tạo, nhưng restore phải ghép đúng chuỗi full và incremental theo thứ tự.
- **Storage snapshot:** chụp trạng thái volume ở tầng lưu trữ. Có thể rất nhanh, nhưng chỉ an toàn nếu snapshot được phối hợp với trạng thái ghi của MySQL và có quy trình đảm bảo nhất quán.

Không suy ra RTO từ thời gian tạo snapshot. Cần đo thời gian gắn snapshot, khôi phục volume, chạy recovery của InnoDB, áp dụng binary log, kiểm tra và đưa dịch vụ trở lại.

### 4.4. Binary log và phục hồi theo thời điểm

Binary log ghi lại các thay đổi dữ liệu và cấu trúc theo cấu hình máy chủ. Khi kết hợp với một bản backup nền, binary log cho phép phục hồi đến một thời điểm hoặc vị trí xác định (point-in-time recovery — PITR), miễn là log cần thiết được lưu đầy đủ và không bị hỏng.

Kiểm tra cấu hình liên quan:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW BINARY LOGS;
SHOW BINARY LOG STATUS;
```

`SHOW BINARY LOG STATUS` có trên các phiên bản MySQL mới; với một số bản MySQL 8.0, có thể cần dùng `SHOW MASTER STATUS` theo phiên bản cụ thể. Hãy kiểm tra tài liệu phiên bản đang vận hành. `log_bin` phải bật để tạo binary log. `binlog_format=ROW` thường được ưu tiên cho khả năng ghi lại thay đổi hàng nhất quán trong nhiều tình huống replication và PITR.

Độ bền của commit và việc chuyển log cần được thiết kế đồng bộ. Với hệ thống ưu tiên độ bền giao dịch, thường đánh giá `sync_binlog=1` cùng `innodb_flush_log_at_trx_commit=1`; các thiết lập này có chi phí I/O và cần kiểm thử tải. Chúng không thay thế việc sao chép binary log ra một miền lỗi độc lập. Nếu chỉ có log trên cùng ổ đĩa với máy chủ, hỏng ổ đĩa có thể làm mất cả dữ liệu và log.

Ví dụ phát lại log sau khi đã restore backup nền:

```bash
mysqlbinlog --start-datetime="2026-11-19 12:00:00" \
  --stop-datetime="2026-11-19 13:42:00" \
  /backup/binlog/mysql-bin.000123 \
  /backup/binlog/mysql-bin.000124 \
  | mysql --host=recovery-db.example.internal \
          --user=recovery_user --password
```

Đây là minh họa cú pháp. Trước khi chạy, phải xác định chính xác file log, thứ tự, múi giờ và mốc dừng. Khi có thể, dùng vị trí log hoặc GTID đã ghi nhận để tránh sự mơ hồ của thời gian. Không phát lại log vượt qua thời điểm dữ liệu bị xóa nhầm hoặc bị hỏng. Hãy thử lệnh trên một máy phục hồi cô lập trước.

## 5. Replication không thay thế backup

Replication giúp duy trì bản sao dữ liệu trên máy chủ khác và có thể giảm thời gian chuyển dịch vụ khi máy chủ chính gặp lỗi hạ tầng. Tuy nhiên, thao tác sai có thể được sao chép sang replica: xóa nhầm bảng, cập nhật sai hàng hoặc dữ liệu độc hại có thể lan truyền. Replica cũng có thể dùng chung tài khoản, mạng, vùng lưu trữ hoặc quyền quản trị với primary.

Vì vậy:

- Duy trì backup độc lập với primary và replica.
- Lưu binary log cần thiết bên ngoài máy chủ nguồn.
- Bảo vệ kho backup bằng quyền riêng, mã hóa và cơ chế chống sửa/xóa ngoài ý muốn.
- Kiểm tra khả năng phục hồi khi cả primary lẫn replica đều không dùng được.
- Nếu dùng replica làm nguồn backup, đánh giá độ trễ replication và bảo đảm công cụ backup tạo snapshot nhất quán.

Replica có thể là một phần của chiến lược HA (High Availability); backup và PITR giải quyết khả năng quay về trạng thái dữ liệu trước đó. Hai mục tiêu này bổ sung cho nhau.

## 6. Tính RPO/RTO thực tế từ dữ liệu vận hành

Một mục tiêu chỉ đáng tin khi được đo thường xuyên. Hãy thu thập các thông số sau:

| Chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Tuổi của backup hợp lệ gần nhất | Thời gian từ thời điểm snapshot đến hiện tại | Ước lượng điểm nền và kiểm tra lịch backup |
| Độ trễ lưu binary log | Khoảng cách giữa log mới nhất trên nguồn và log đã lưu an toàn ở kho độc lập | Ước lượng phần dữ liệu có thể mất khi nguồn hỏng |
| Thời gian restore | Thời gian nạp backup vào máy phục hồi | Đánh giá tốc độ đọc, ghi và công cụ |
| Thời gian phát lại log | Thời gian áp dụng các thay đổi sau backup | Đánh giá lượng log và tốc độ thực thi |
| Thời gian kiểm chứng | Thời gian chạy kiểm tra dữ liệu và ứng dụng | Đảm bảo RTO bao gồm xác nhận chất lượng |
| Tỷ lệ bài test restore thành công | Số bài test đạt trên tổng số bài test | Đo độ tin cậy của quy trình, không chỉ của job backup |

Ví dụ một backup nền kết thúc lúc 01:00, binary log được lưu ngoài máy chủ liên tục và log đã xác nhận đến 13:57. Sự cố xảy ra lúc 14:00. Nếu backup và log đều đọc được, điểm phục hồi gần nhất là 13:57, nên RPO đo được khoảng 3 phút. Nếu restore backup mất 35 phút, phát lại log mất 12 phút, kiểm tra mất 15 phút và chuyển dịch vụ mất 8 phút, RTO đo được tối thiểu 70 phút, chưa tính thời gian phát hiện và quyết định nếu tổ chức tính chúng vào RTO.

Để có số liệu ổn định, hãy đo trên dữ liệu có kích thước tương đương production, phần cứng và mạng tương đương, đồng thời ghi lại tải I/O. Một bài test trên database 5 GB không dự báo đáng tin cậy thời gian phục hồi của database 5 TB.

## 7. Thiết kế quy trình phục hồi MySQL

Một runbook phục hồi cần mô tả trình tự rõ ràng để người trực có thể thực hiện khi áp lực cao.

### 7.1. Chuẩn bị trước sự cố

- Danh sách máy chủ, phiên bản MySQL, cấu hình InnoDB, đường dẫn dữ liệu và dung lượng dự kiến.
- Danh sách backup, manifest, checksum, thời điểm tạo, loại backup và chuỗi incremental liên quan.
- Vị trí binary log, thứ tự file, thông tin GTID hoặc vị trí log được ghi nhận tại thời điểm backup.
- Tài khoản phục hồi, quyền truy cập kho backup, khóa giải mã và quy trình lấy bí mật khẩn cấp.
- Hướng dẫn dựng máy chủ, cài đúng phiên bản tương thích, cấu hình mạng và lưu trữ.
- Danh sách ứng dụng, endpoint, DNS, proxy, chứng chỉ và dịch vụ phụ thuộc.
- Người quyết định phục hồi, người thực hiện, người xác minh dữ liệu và người phê duyệt mở lại lưu lượng.

Thông tin truy cập và khóa giải mã phải được bảo vệ. Runbook nên chỉ ra nơi lấy bí mật và ai được phép truy cập, không ghi mật khẩu hoặc private key trực tiếp trong tài liệu.

### 7.2. Trình tự phục hồi mẫu

1. **Khoanh vùng:** ngăn ghi thêm vào hệ thống bị lỗi; giữ lại log và bằng chứng cần điều tra. Nếu nghi ngờ xâm nhập, cô lập máy chủ và xác minh tính toàn vẹn của kho backup trước khi dùng.
2. **Chọn điểm phục hồi:** xác định thời điểm dữ liệu tốt cuối cùng, sự cố bắt đầu khi nào và có cần PITR trước một giao dịch cụ thể hay không.
3. **Dựng môi trường sạch:** tạo máy chủ phục hồi có phiên bản MySQL và cấu hình tương thích, đủ CPU, RAM, IOPS, dung lượng và quyền truy cập.
4. **Lấy backup và kiểm tra:** xác minh manifest, checksum, chữ ký hoặc metadata do hệ thống backup cung cấp; giải mã trong môi trường được kiểm soát.
5. **Restore backup nền:** thực hiện đúng quy trình của công cụ logical hoặc physical. Với physical backup, chạy bước prepare/recovery theo tài liệu công cụ.
6. **Phát lại binary log:** áp dụng các log liên tục từ sau mốc backup đến điểm đích đã chọn. Kiểm tra thứ tự, khoảng trống và tính liên tục của log/GTID.
7. **Kiểm tra MySQL:** xác nhận máy chủ khởi động, InnoDB hoàn tất recovery, database và bảng cần thiết có mặt, tài khoản và quyền đúng.
8. **Kiểm tra ứng dụng:** chạy truy vấn đại diện, kiểm tra transaction, đọc/ghi trong phạm vi kiểm soát, hàng đợi và tích hợp phụ thuộc.
9. **Chuyển dịch vụ:** chỉ chuyển endpoint hoặc lưu lượng sau khi người có trách nhiệm xác nhận dữ liệu và chức năng đạt tiêu chí.
10. **Theo dõi và ghi nhận:** theo dõi lỗi kết nối, độ trễ, lock, dung lượng và các giao dịch phát sinh; ghi lại mốc thời gian để tính RPO/RTO thực tế.

Nếu cần phục hồi sau khi người dùng xóa nhầm dữ liệu, không restore đè lên production ngay. Hãy phục hồi vào máy chủ cô lập, phát lại log đến trước thao tác xóa, trích xuất dữ liệu cần thiết, rồi lập kế hoạch nhập lại có kiểm soát. Cách này giảm nguy cơ ghi đè các giao dịch hợp lệ phát sinh sau thời điểm backup.

## 8. Kiểm chứng backup và phục hồi

Job backup báo `SUCCESS` chỉ chứng minh công cụ đã báo hoàn tất theo tiêu chí của nó. Nó không chứng minh bản backup có thể giải mã, restore, phát lại log và phục vụ ứng dụng. Cần kiểm chứng ở nhiều lớp.

### 8.1. Kiểm tra ngay sau khi tạo backup

- Xác nhận job hoàn tất và ghi nhận mã thoát, thời gian bắt đầu/kết thúc, kích thước và phạm vi dữ liệu.
- Kiểm tra manifest, checksum hoặc cơ chế xác minh tính toàn vẹn của công cụ.
- Xác nhận tệp đã được chuyển đến kho lưu trữ độc lập và có thể đọc bằng tài khoản phục hồi.
- Xác nhận binary log sau mốc backup đã được lưu đủ, liên tục và có thể giải mã/đọc.
- Kiểm tra retention: backup và log chưa bị xóa trước khi hết thời hạn cần thiết.

Checksum chỉ chứng minh nội dung tệp không đổi so với lúc tạo checksum; nó không chứng minh nội dung là backup đúng hoặc có thể phục hồi. Vì thế vẫn cần restore test.

### 8.2. Restore test định kỳ

Chạy phục hồi vào môi trường cô lập để tránh ảnh hưởng production. Bài test nên bao gồm:

1. Tải một bản backup thực tế từ kho lưu trữ, không dùng bản copy còn nằm trên máy backup.
2. Kiểm tra checksum và giải mã bằng đúng quy trình vận hành.
3. Restore trên máy chủ có phiên bản và cấu hình được hỗ trợ.
4. Phát lại binary log đến một thời điểm xác định.
5. Xác minh bảng, số lượng hàng, quan hệ dữ liệu và các đối tượng database cần thiết.
6. Khởi chạy ứng dụng hoặc một bộ truy vấn đại diện, kiểm tra quyền và transaction.
7. Đo thời gian từng bước, tính RPO/RTO và lưu bằng chứng.

Tần suất phụ thuộc vào mức độ quan trọng và tốc độ thay đổi hệ thống. Một dịch vụ quan trọng có thể cần restore test hàng tuần hoặc hàng tháng; hệ thống ít quan trọng có thể theo quý. Ngoài lịch định kỳ, phải kiểm thử sau thay đổi lớn như nâng cấp MySQL, thay công cụ backup, đổi mã hóa, chuyển kho lưu trữ hoặc thay đổi cấu trúc dữ liệu.

### 8.3. Kiểm tra tính đúng của dữ liệu

Chỉ thấy MySQL khởi động thành công chưa đủ. Hãy dùng các kiểm tra phù hợp với nghiệp vụ:

- Đếm hàng hoặc tổng hợp dữ liệu theo khoảng thời gian ở các bảng trọng yếu.
- Kiểm tra khóa ngoại logic, quan hệ giữa đơn hàng và thanh toán, số dư và bút toán đối ứng.
- So sánh checksum hoặc aggregate với nguồn chuẩn nếu có.
- Kiểm tra các đối tượng schema như view, trigger, procedure, event và tài khoản ứng dụng.
- Chạy một giao dịch thử có thể rollback hoặc trên dữ liệu kiểm thử, xác nhận đọc/ghi hoạt động đúng.

Đối với hệ thống tài chính, kiểm tra số dư tổng hợp hoặc đối soát giao dịch có thể quan trọng hơn chỉ so sánh số lượng hàng. Chủ sở hữu nghiệp vụ cần xác định các bất biến dữ liệu và tiêu chí chấp nhận.

## 9. Diễn tập và tiêu chí nghiệm thu

Restore test xác minh khả năng kỹ thuật của bản backup. Diễn tập phục hồi (recovery drill) kiểm tra toàn bộ con người, quy trình, quyền truy cập, hạ tầng và quyết định cần thiết để đưa dịch vụ trở lại.

### 9.1. Các kịch bản nên diễn tập

| Kịch bản | Mục tiêu kiểm chứng | Điểm cần chú ý |
|---|---|---|
| Xóa nhầm bảng hoặc hàng | PITR đến trước thao tác lỗi và trích xuất dữ liệu | Chọn đúng điểm dừng; giữ các giao dịch hợp lệ sau đó |
| Hỏng máy chủ hoặc volume | Phục hồi trên hạ tầng mới từ backup độc lập | Tốc độ cấp máy, dung lượng, quyền kho backup và binary log |
| Backup bị thiếu hoặc hỏng | Phát hiện bản không hợp lệ và chọn bản khác | Retention, checksum, bản sao độc lập và chuỗi incremental |
| Mất vùng hoặc tài khoản lưu trữ | Truy cập bản backup ở miền lỗi khác | DNS, mạng, khóa giải mã, quyền và chi phí lấy dữ liệu |
| Ransomware hoặc truy cập trái phép | Phục hồi từ bản sao không bị sửa/xóa | Tính bất biến, phân tách quyền, xác minh môi trường sạch |
| Nâng cấp hoặc migration lỗi | Khôi phục trước thay đổi và đánh giá mất dữ liệu | Khả năng tương thích phiên bản, schema và ứng dụng |

### 9.2. Tiêu chí nghiệm thu

Một bài diễn tập đạt yêu cầu khi:

- Phục hồi được từ bản backup lấy ở kho lưu trữ dự kiến.
- Phục hồi được đến điểm dữ liệu đáp ứng RPO đã phê duyệt.
- Dịch vụ đạt trạng thái hoạt động trong giới hạn RTO.
- Kiểm tra dữ liệu và ứng dụng đạt các tiêu chí nghiệp vụ đã thống nhất.
- Quyền truy cập, mã hóa, audit và giám sát hoạt động đúng.
- Các vai trò biết nhiệm vụ, có thể tìm runbook và thực hiện mà không phụ thuộc duy nhất vào một cá nhân.
- Bằng chứng và thời gian từng bước được ghi lại; sai lệch có chủ sở hữu và hạn xử lý.

Nếu bài test không đạt, ghi rõ nguyên nhân: thiếu quyền, khóa giải mã không truy cập được, log bị thiếu, dung lượng không đủ, thời gian restore vượt dự kiến hoặc kiểm tra nghiệp vụ thất bại. Tạo hành động khắc phục, đặt thời hạn và chạy lại bài test để xác nhận vấn đề đã được giải quyết.

## 10. Bảo vệ kho backup và khả năng phục hồi trước sự cố bảo mật

Kế hoạch RPO/RTO sẽ thất bại nếu kẻ tấn công hoặc lỗi vận hành có thể xóa cả dữ liệu chính lẫn backup. Thiết kế kho backup như một miền bảo mật riêng:

- Lưu ít nhất một bản sao ngoài máy chủ và ngoài miền lỗi chính; cân nhắc bản sao khác vùng hoặc khác tài khoản quản trị.
- Dùng quyền riêng cho tác vụ backup và restore. Tài khoản backup không nên có quyền xóa toàn bộ kho lưu trữ nếu không cần thiết.
- Bật mã hóa khi truyền và khi lưu. Quản lý khóa giải mã độc lập với máy chủ database và kiểm thử quy trình truy cập khẩn cấp.
- Dùng object lock, immutable storage hoặc cơ chế retention chống xóa khi phù hợp với nền tảng; kiểm tra cả quyền quản trị có thể thay đổi retention.
- Giám sát job backup, khoảng trống binary log, tuổi backup gần nhất, dung lượng và lỗi truy cập kho.
- Giữ một bản runbook và thông tin liên lạc có thể truy cập khi hệ thống danh tính hoặc tài liệu nội bộ chính bị gián đoạn.
- Xác minh backup sạch trước khi phục hồi sau sự cố bảo mật; không đưa máy chủ đã bị xâm nhập trở lại mạng sản xuất mà chưa xử lý nguyên nhân.

Quy tắc 3-2-1 (ba bản sao, hai loại phương tiện hoặc miền lưu trữ, một bản ngoài địa điểm) là một điểm khởi đầu hữu ích. Với rủi ro ransomware, nên bổ sung bản sao bất biến và tách quyền quản trị. Số lượng bản sao không tự bảo đảm khả năng phục hồi nếu tất cả dùng chung khóa, tài khoản hoặc đường xóa.

## 11. Ví dụ xây dựng kế hoạch cho dịch vụ đơn hàng

Một hệ thống MySQL lưu đơn hàng có các đặc điểm giả định:

- Database 1,2 TB, tăng khoảng 20 GB mỗi ngày.
- RPO được phê duyệt là 5 phút.
- RTO được phê duyệt là 90 phút.
- Full physical backup hằng ngày mất 45 phút.
- Binary log được chuyển sang kho độc lập mỗi phút; độ trễ cảnh báo khi vượt 2 phút.
- Thử nghiệm restore gần nhất mất 38 phút; phát lại log mất 18 phút; kiểm tra ứng dụng và chuyển endpoint mất 22 phút.

Tổng thời gian phục hồi đo được là 78 phút, còn 12 phút dự phòng so với RTO. Biên này khá hẹp. Cần xác định liệu thời gian phát hiện, phê duyệt và cấp hạ tầng đã được tính vào 78 phút chưa. Nếu chưa, kế hoạch chưa chứng minh đạt RTO 90 phút.

Để kiểm chứng RPO, không chỉ xem lịch chuyển log. Hệ thống cần ghi nhận vị trí hoặc GTID mới nhất trên nguồn và vị trí mới nhất đã lưu an toàn ở kho độc lập. Trong diễn tập, chọn một giao dịch thử đã commit, xác nhận nó có mặt sau restore nếu nằm trước điểm phục hồi, và xác nhận giao dịch sau điểm dừng không xuất hiện. Đo khoảng cách giữa thời điểm sự cố giả lập và giao dịch cuối cùng có thể phục hồi.

Kế hoạch hành động có thể gồm:

1. Tự động cảnh báo khi độ trễ lưu binary log vượt 2 phút và khi không có backup hợp lệ trong cửa sổ dự kiến.
2. Chuẩn bị sẵn cấu hình máy phục hồi và quyền truy cập kho backup để giảm thời gian cấp hạ tầng.
3. Tối ưu tốc độ đọc/ghi hoặc dùng phương án physical restore phù hợp để giảm thời gian nạp dữ liệu.
4. Đo lại thời gian phát lại log với tải đại diện và đặt ngưỡng lượng log tối đa.
5. Diễn tập cả kịch bản mất primary lẫn mất quyền truy cập tài khoản/kho lưu trữ chính.
6. Duy trì tối thiểu 10–15 phút biên dự phòng sau khi đã tính mọi mốc theo định nghĩa RTO của tổ chức.

## 12. Mẫu nội dung kế hoạch phục hồi

Mỗi hệ thống nên có một bản kế hoạch ngắn, được phê duyệt và liên kết tới runbook chi tiết. Có thể dùng mẫu sau:

| Trường | Nội dung cần điền |
|---|---|
| Tên dịch vụ / chủ sở hữu | Tên hệ thống, nhóm nghiệp vụ và người chịu trách nhiệm |
| Phạm vi dữ liệu | Schema, bảng, routine, event, trigger và phụ thuộc liên quan |
| Phiên bản MySQL | Phiên bản server, engine, cấu hình quan trọng và công cụ backup |
| RPO / RTO | Giá trị đã được chủ sở hữu nghiệp vụ phê duyệt, kèm mốc bắt đầu/kết thúc đo |
| Phương pháp backup | Logical/physical, full/incremental, snapshot và lịch chạy |
| Binary log / PITR | Vị trí lưu, cách xác định điểm phục hồi, retention và người chịu trách nhiệm |
| Kho lưu trữ | Vùng, tài khoản, quyền, mã hóa, retention và bản sao bất biến |
| Quy trình restore | Runbook, phiên bản tương thích, bước phát lại log và bước chuyển dịch vụ |
| Kiểm tra nghiệm thu | Truy vấn, bất biến nghiệp vụ, chức năng và tiêu chí bảo mật |
| Liên lạc khi sự cố | Người chỉ huy, người phục hồi, người xác minh và kênh liên lạc dự phòng |
| Lần test gần nhất | Ngày, kịch bản, RPO/RTO đo được, kết quả và các vấn đề còn mở |

Rà soát kế hoạch khi có thay đổi về kích thước dữ liệu, tốc độ tăng trưởng, phiên bản MySQL, topology, công cụ backup, mã hóa, nhà cung cấp lưu trữ hoặc yêu cầu nghiệp vụ. Một kế hoạch từng đạt RTO 1 giờ khi database 100 GB có thể không còn phù hợp khi database tăng lên 2 TB.

## 13. Câu hỏi tự kiểm tra

1. Một hệ thống restore trong 10 phút nhưng chỉ có backup của 6 giờ trước. RTO và RPO của phương án đó lần lượt phản ánh điều gì?
2. Vì sao lịch full backup mỗi đêm không đủ để chứng minh RPO 5 phút?
3. Binary log cần được bảo vệ như thế nào để hỗ trợ PITR khi máy chủ hoặc volume chính bị mất?
4. Vì sao replica không thể thay thế backup khi người vận hành chạy nhầm `DROP TABLE`?
5. Những công đoạn nào phải được tính vào RTO ngoài thời gian nạp dữ liệu?
6. Checksum thành công có chứng minh backup có thể phục hồi không? Cần thêm bước xác minh nào?
7. Hãy đề xuất một kịch bản diễn tập và các tiêu chí dữ liệu/nghiệp vụ để nghiệm thu.

## Kết luận

RPO xác định mức mất dữ liệu chấp nhận được; RTO xác định thời gian đưa dịch vụ trở lại theo một mốc đo rõ ràng. Với MySQL, cần phối hợp backup nền, binary log, quy trình PITR, hạ tầng phục hồi và kiểm tra nghiệp vụ để đạt hai mục tiêu này. Một kế hoạch chỉ được xem là đáng tin khi tổ chức thường xuyên lấy backup từ kho thực tế, restore trong môi trường cô lập, đo RPO/RTO, diễn tập vai trò và xử lý các sai lệch cho đến khi bài kiểm thử đạt yêu cầu.
