# Khóa mã hóa binary log và khả năng đọc log sau sự cố

Binary log lưu lại các sự kiện làm thay đổi dữ liệu MySQL. Nó là đầu vào quan trọng cho replication và point-in-time recovery (PITR), nhưng cũng có thể chứa câu lệnh SQL, giá trị hàng hoặc dữ liệu nghiệp vụ nhạy cảm. Vì vậy, bảo vệ binary log cần tính đến cả nơi lưu trữ, khóa giải mã và khả năng đọc lại khi máy chủ gặp sự cố.

MySQL hỗ trợ mã hóa binary log và relay log khi lưu trên đĩa thông qua keyring. Cấu hình này giúp bảo vệ file log nếu ổ đĩa, volume hoặc bản sao file bị truy cập trái phép. Khi mã hóa được bật, máy chủ cần keyring chứa khóa thích hợp để mở các file log. Nếu chỉ giữ file log mà làm mất keyring hoặc khóa liên quan, dữ liệu trong log có thể không còn đọc được để phục hồi.

Mã hóa binary log không thay thế TLS cho kết nối replication hoặc kết nối quản trị. Mã hóa file bảo vệ dữ liệu ở trạng thái lưu trữ; TLS bảo vệ dữ liệu khi truyền qua mạng. Một quy trình PITR đáng tin cậy phải bảo vệ cả hai lớp và kiểm thử việc đọc log trên một máy chủ phục hồi độc lập.

## 1. Binary log chứa gì và vì sao phải bảo vệ?

Binary log ghi nhận các sự kiện thay đổi dữ liệu và một số thay đổi cấu trúc. Tùy `binlog_format`, sự kiện có thể biểu diễn câu lệnh SQL hoặc thay đổi ở mức hàng:

- Với `STATEMENT`, log ghi câu lệnh được thực thi. Câu lệnh có thể chứa giá trị literal, điều kiện truy vấn hoặc dữ liệu nhạy cảm được ứng dụng đưa vào SQL.
- Với `ROW`, log ghi các sự kiện thay đổi hàng. Các giá trị trước/sau có thể xuất hiện tùy `binlog_row_image` và loại sự kiện.
- Với `MIXED`, MySQL chọn cách ghi theo quy tắc của phiên bản và câu lệnh.

Binary log còn được dùng để đồng bộ replica và phát lại giao dịch sau khi khôi phục một bản backup. Relay log trên replica lưu các sự kiện nhận từ source trước khi SQL thread áp dụng chúng. Do đó, cả binary log và relay log đều cần được đưa vào chính sách bảo vệ dữ liệu.

Các rủi ro thường gặp gồm:

1. Người có quyền đọc filesystem lấy được bản sao log và trích xuất dữ liệu nhạy cảm.
2. Backup hoặc snapshot chứa file log bị thất lạc, chia sẻ sai quyền hoặc bị đánh cắp.
3. Máy chủ hỏng cùng với keyring, khiến log còn nguyên nhưng không thể giải mã.
4. Khóa bị thay thế hoặc xóa trong quá trình xoay vòng, khiến máy chủ phục hồi không thể mở log cũ.
5. Quản trị viên đọc log trên một máy chủ tạm thời rồi ghi bản SQL đã giải mã vào thư mục không được bảo vệ.

Mã hóa at rest giảm rủi ro đọc file log trực tiếp. Nó không ngăn người có quyền SQL phù hợp yêu cầu MySQL xuất nội dung log, không che dữ liệu đã được phát lại vào database, và không bảo vệ file SQL đã giải mã được xuất ra ngoài.

## 2. Điều kiện và cơ chế mã hóa

Tính năng `binlog_encryption` được giới thiệu trong MySQL 8.0.14. Cần kiểm tra phiên bản MySQL Server và tài liệu tương ứng trước khi triển khai. Máy chủ phải có keyring component hoặc keyring plugin phù hợp với phiên bản được cấu hình và hoạt động bình thường. Keyring quản lý các khóa mà MySQL dùng để bảo vệ thông tin khóa của các file log.

Trước khi bật mã hóa, xác định rõ:

- Phiên bản MySQL và cách cài đặt keyring được phiên bản đó hỗ trợ.
- Backend keyring đang dùng: file cục bộ, component/plugin phù hợp hoặc dịch vụ quản lý khóa bên ngoài.
- Vị trí lưu trữ keyring, danh tính được phép truy cập và cách khôi phục backend khi máy chủ thay thế.
- Các file binary log, relay log, backup và bản sao log hiện có.
- Quy trình sao lưu, phục hồi và xoay khóa của backend keyring.

Keyring phải sẵn sàng khi MySQL cần mở file log đã mã hóa. Vì thế, cấu hình keyring và khả năng truy cập khóa là một phần của cấu hình khởi động và phục hồi máy chủ. Chỉ bật `binlog_encryption` mà chưa chuẩn bị keyring sẽ dẫn tới lỗi khởi tạo hoặc lỗi truy cập log tùy phiên bản và trạng thái máy chủ.

Về khái quát, MySQL dùng khóa do keyring quản lý để bảo vệ khóa mã hóa của từng file log. Khi đọc file, MySQL lấy thông tin khóa cần thiết từ keyring và giải mã nội dung trong tiến trình máy chủ. Cơ chế chi tiết, cách lưu metadata và yêu cầu backend phụ thuộc phiên bản MySQL; không tự chỉnh sửa header hoặc nội dung file log bằng công cụ bên ngoài.

## 3. Bật mã hóa binary log và relay log

Sau khi keyring đã được cài đặt và kiểm tra, bật mã hóa bằng cấu hình máy chủ. Ví dụ:

```ini
[mysqld]
binlog_encryption=ON
```

Hoặc, trên phiên bản hỗ trợ biến động và câu lệnh `SET PERSIST`, có thể bật và lưu cấu hình qua SQL:

```sql
SET PERSIST binlog_encryption = ON;
```

Nếu chỉ dùng `SET GLOBAL`, thay đổi có thể mất sau khi MySQL khởi động lại. Hãy bảo đảm chính sách được lưu trong file cấu hình hoặc cơ chế persistence phù hợp với cách quản lý cấu hình của tổ chức. Quyền cần thiết để thay đổi biến hệ thống có thể khác theo phiên bản và chính sách phân quyền.

`binlog_encryption=ON` yêu cầu MySQL mã hóa các binary log và relay log theo cơ chế được hỗ trợ. Thiết lập này cần được áp dụng trên từng máy chủ. Bật trên source không tự động làm relay log trên replica được mã hóa; replica cũng cần cấu hình riêng để bảo vệ các file log lưu cục bộ.

Sau khi bật, kiểm tra cấu hình:

```sql
SHOW GLOBAL VARIABLES LIKE 'binlog_encryption';
SHOW BINARY LOGS;
```

Ở các phiên bản hỗ trợ, kết quả `SHOW BINARY LOGS` có cột `Encrypted` để cho biết file tương ứng đã được mã hóa hay chưa. Hãy kiểm tra từng file thay vì chỉ nhìn biến cấu hình. File đã tồn tại trước khi bật mã hóa có thể vẫn ở trạng thái không mã hóa; đừng giả định bật biến sẽ tự biến mọi bản log lịch sử thành file mã hóa. Cần dựa vào cột trạng thái của phiên bản đang chạy và chính sách retention để xử lý các file cũ.

Nếu cần tạo file binary log mới sau khi bật chính sách, có thể xoay log theo quy trình vận hành:

```sql
FLUSH BINARY LOGS;
SHOW BINARY LOGS;
```

Lệnh này tạo file log mới; nó không tự mã hóa lại những file cũ. Trước khi xóa file cũ, xác nhận replica đã đọc xong, backup/PITR không còn phụ thuộc và bản lưu cần thiết đã được bảo vệ. Với relay log, không tự xóa file đang được replica sử dụng; dùng quy trình quản trị replication phù hợp phiên bản.

## 4. Phân biệt mã hóa file log và mã hóa khi truyền

Có hai đường đi riêng của dữ liệu log:

| Tình huống | Cơ chế bảo vệ cần có |
|---|---|
| Binary log được lưu trên đĩa của source | `binlog_encryption` cùng keyring hoạt động |
| Relay log được lưu trên đĩa của replica | Bật `binlog_encryption` trên replica và bảo đảm keyring tại replica |
| Replica nhận sự kiện qua mạng | TLS cho kết nối replication |
| Quản trị viên tải log qua mạng bằng `mysqlbinlog` | TLS cho kết nối client tới máy chủ cung cấp log |
| File log đã giải mã được ghi ra file SQL hoặc kho trung gian | Mã hóa storage, phân quyền và retention cho file xuất |

Ví dụ, source bật `binlog_encryption=ON` sẽ bảo vệ binary log lưu tại source. Nếu replica nhận log qua kết nối không có TLS, dữ liệu vẫn có thể bị quan sát trên mạng. Nếu replica không bật mã hóa, relay log tại replica có thể vẫn lưu dưới dạng không mã hóa. Do đó, hãy cấu hình TLS replication và mã hóa log cục bộ trên từng máy chủ theo yêu cầu bảo mật.

## 5. Đọc binary log đã mã hóa bằng mysqlbinlog

`mysqlbinlog` có thể đọc file binary log thông thường trực tiếp từ filesystem. Với file đã được mã hóa bằng `binlog_encryption`, không nên giả định chế độ đọc file cục bộ có thể tự giải mã nội dung: công cụ không thay thế keyring và tiến trình MySQL trong việc mở file được mã hóa.

Quy trình phù hợp là dùng `mysqlbinlog --read-from-remote-server` để kết nối tới một MySQL Server có thể truy cập keyring và đọc file log. Máy chủ giải mã log rồi cung cấp sự kiện cho client qua giao thức replication. Ví dụ:

```bash
mysqlbinlog \
  --read-from-remote-server \
  --host=127.0.0.1 \
  --port=3306 \
  --user=binlog_reader \
  --password \
  mysql-bin.000123
```

`--password` yêu cầu nhập mật khẩu tương tác. Tài khoản đọc log cần quyền replication phù hợp với phiên bản MySQL và chính sách bảo mật; hãy cấp quyền tối thiểu cần thiết, giới hạn host nguồn và không dùng tài khoản ứng dụng hoặc `root` chỉ để thuận tiện. Nếu kết nối qua mạng, cấu hình TLS và xác minh chứng thư máy chủ theo chính sách của client.

Để giới hạn phạm vi đọc, có thể dùng mốc thời gian hoặc vị trí sự kiện:

```bash
mysqlbinlog \
  --read-from-remote-server \
  --host=127.0.0.1 \
  --user=binlog_reader \
  --password \
  --start-position=4 \
  --stop-position=84520 \
  mysql-bin.000123
```

Các vị trí trên chỉ là ví dụ. Phải xác định vị trí bắt đầu/kết thúc từ log thực tế và hiểu ranh giới transaction. Không cắt giữa một transaction rồi áp dụng một phần sự kiện của transaction đó. Khi cần phục hồi chính xác, ưu tiên phân tích sự kiện và GTID/position trước khi phát lại.

Nếu cần lưu kết quả đã giải mã để kiểm tra, hãy ghi vào thư mục giới hạn quyền truy cập, được mã hóa và có retention rõ ràng. Nội dung do `mysqlbinlog` xuất ra có thể chứa dữ liệu nhạy cảm. Không đưa file SQL đã giải mã vào ticket, repository, log ứng dụng hoặc thư mục dùng chung không được bảo vệ.

## 6. Đọc log khi máy chủ nguồn gặp sự cố

Tình huống khó nhất xảy ra khi source bị hỏng hoặc không thể khởi động, trong khi binary log đã được mã hóa. Lúc này, file log đơn lẻ chưa đủ để phục hồi; cần cả keyring có đúng khóa đã dùng để mã hóa file.

Một quy trình phục hồi tổng quát như sau:

1. **Bảo toàn bằng chứng và file:** giữ nguyên binary log, file index, backup dữ liệu, metadata backup và log vận hành. Không xóa, đổi tên tùy tiện hoặc ghi đè các file log gốc.
2. **Khôi phục keyring:** lấy bản keyring hoặc khôi phục quyền truy cập tới backend quản lý khóa. Phải có đúng key material/định danh khóa mà file log cần; tạo keyring mới rỗng không thể giải mã log cũ.
3. **Dựng máy chủ phục hồi:** chuẩn bị phiên bản MySQL tương thích, cấu hình keyring đúng cách và khôi phục backup dữ liệu cùng các file cần thiết vào môi trường cô lập. Bảo đảm MySQL khởi động được và mở được các file log mã hóa.
4. **Xác minh log:** dùng `SHOW BINARY LOGS` và `mysqlbinlog --read-from-remote-server` kết nối tới máy chủ phục hồi. Kiểm tra có thể đọc các file cần cho PITR và các mốc log liên tục.
5. **Chọn mốc phục hồi:** xác định backup cơ sở, GTID hoặc binary log position và thời điểm dừng. Tách giao dịch lỗi khỏi các giao dịch hợp lệ sau đó.
6. **Phát lại trong môi trường cô lập:** áp dụng các sự kiện tới mốc đã chọn trên instance phục hồi. Không phát lại trực tiếp vào hệ thống production đang hoạt động.
7. **Kiểm tra và chuyển dịch vụ:** đối chiếu dữ liệu nghiệp vụ, tính toàn vẹn và quyền truy cập; chỉ chuyển traffic sau khi quy trình phục hồi được xác nhận.

Nếu source vẫn có thể khởi động trong chế độ phục hồi, có thể dùng chính server đó để cung cấp log sau khi keyring hoạt động. Nếu source không thể khởi động, thường cần dựng một instance phục hồi từ backup và keyring, sau đó đưa các file log liên quan vào phạm vi mà instance phục hồi có thể đọc theo quy trình MySQL. Cách bố trí file, đường dẫn log và khả năng tương thích phải được thử trước trong môi trường diễn tập.

Nếu keyring bị mất vĩnh viễn, bị hỏng không thể khôi phục hoặc không còn quyền truy cập khóa ngoài, file log đã mã hóa có thể không giải mã được. Không có câu lệnh SQL nào tái tạo lại khóa đã mất từ ciphertext. Khi đó, khả năng PITR có thể bị giới hạn ở mốc backup gần nhất còn khôi phục được; cần ghi nhận rõ phần dữ liệu không thể phục hồi.

## 7. Bảo vệ và sao lưu keyring

Keyring là một phần thiết yếu của chiến lược backup. Không coi việc sao lưu `datadir` là đã sao lưu đầy đủ khóa mã hóa. Tùy backend, keyring có thể nằm ngoài `datadir`, ở file riêng, component được cấu hình qua manifest hoặc dịch vụ quản lý khóa bên ngoài.

Một kế hoạch bảo vệ keyring nên có:

- **Bản sao an toàn:** sao lưu dữ liệu keyring theo cơ chế được backend hỗ trợ; mã hóa bản sao và giới hạn người có thể đọc/khôi phục.
- **Cấu hình khôi phục:** lưu cấu hình component/plugin, đường dẫn, endpoint, định danh key, chứng thư hoặc thông tin kết nối cần thiết. Bảo vệ các secret này trong secret manager.
- **Miền lỗi độc lập:** giữ bản sao keyring và thông tin khôi phục ở miền lỗi khác với máy chủ và backup dữ liệu chính.
- **Kiểm tra quyền:** bảo đảm host phục hồi và tài khoản dịch vụ có thể truy cập keyring theo nguyên tắc quyền tối thiểu.
- **Diễn tập:** khôi phục keyring trên host thử nghiệm và chứng minh MySQL có thể mở log đã mã hóa.
- **Quản lý vòng đời:** ghi lại thay đổi key, thời điểm xoay, người thực hiện và trạng thái backup sau mỗi lần xoay.

Với keyring file cục bộ, không tự ý sao chép file đang được ghi nếu backend không bảo đảm thao tác đó an toàn. Dùng phương pháp export/backup hoặc quy trình dừng dịch vụ được tài liệu backend quy định. Với keyring bên ngoài, backup cần bao gồm cả quyền truy cập, định danh key và khả năng kết nối dịch vụ khi phục hồi tại vùng khác.

Không lưu keyring duy nhất cùng nơi với binary log. Người có thể lấy cả file log lẫn khóa giải mã sẽ vượt qua lớp bảo vệ at rest. Ngược lại, cất khóa ở nơi quá khó truy cập trong sự cố cũng có thể làm RTO vượt mục tiêu. Cần cân bằng bảo vệ và khả năng khôi phục bằng quy trình cấp quyền khẩn cấp có kiểm soát.

## 8. Xoay binary log master key

Xoay khóa định kỳ giúp quản lý vòng đời khóa và đáp ứng chính sách bảo mật. Với MySQL hỗ trợ binary log encryption, thao tác xoay binary log master key được thực hiện bằng:

```sql
ALTER INSTANCE ROTATE BINLOG MASTER KEY;
```

Lệnh này yêu cầu MySQL xoay master key dùng cho mã hóa binary log. Thao tác yêu cầu keyring sẵn sàng và quyền quản trị tương ứng; tên quyền động và điều kiện cấp quyền cần xác minh theo phiên bản. Thực hiện theo lịch thay đổi đã kiểm soát, theo dõi error log và xác nhận server tiếp tục đọc được các file log cũ lẫn file mới.

Xoay khóa không phải là backup keyring. Trước khi xoay, bảo đảm backend keyring có bản sao phục hồi hợp lệ và quy trình khôi phục đã được thử. Sau khi xoay, sao lưu trạng thái keyring mới theo hướng dẫn backend và thử đọc một file log được tạo trước cũng như sau lần xoay. Không xóa key cũ theo cách thủ công; MySQL/backend cần giữ những khóa còn cần để mở file log cũ.

Nếu `binlog_encryption` bị tắt, các file đã được mã hóa vẫn có thể tiếp tục phụ thuộc keyring để đọc. Việc tắt biến không phải thao tác giải mã lịch sử. Vì vậy, không được xóa keyring chỉ vì cấu hình hiện tại đang hiển thị `OFF`. Trước khi loại bỏ khóa, xác định mọi file log, relay log, backup và bản sao lưu còn phụ thuộc vào khóa đó.

## 9. Kết hợp binary log encryption với PITR

PITR cần một bản backup cơ sở và chuỗi binary log liên tục từ mốc backup tới thời điểm cần phục hồi. Khi log được mã hóa, keyring trở thành một điều kiện bổ sung để đọc chuỗi sự kiện.

Quy trình PITR tham khảo:

1. Chọn full backup gần nhất trước sự cố; kiểm tra backup và metadata về GTID hoặc binary log coordinate.
2. Khôi phục backup trên máy chủ cô lập, kèm cấu hình và keyring cần thiết.
3. Khởi động MySQL và xác nhận server đọc được các log mã hóa.
4. Dùng `mysqlbinlog --read-from-remote-server` để đọc log theo thứ tự, lưu kết quả trung gian trong vùng bảo vệ nếu cần phân tích.
5. Xác định transaction gây lỗi hoặc mốc thời gian cần dừng; ưu tiên vị trí/GTID chính xác hơn timestamp gần đúng.
6. Phát lại sự kiện hợp lệ tới mốc phục hồi trên instance đích.
7. Kiểm tra dữ liệu, đối chiếu nghiệp vụ và đo RPO/RTO thực tế.

Ví dụ đọc một khoảng log từ máy chủ phục hồi:

```bash
mysqlbinlog \
  --read-from-remote-server \
  --host=recovery-db.internal \
  --user=binlog_reader \
  --password \
  --start-datetime="2026-11-19 08:00:00" \
  --stop-datetime="2026-11-19 08:25:00" \
  mysql-bin.000123 mysql-bin.000124 \
  > /secure/recovery/replay-window.sql
```

Mốc thời gian trong ví dụ chỉ minh họa. Phải kiểm tra múi giờ của server và timestamp trong log. Nếu nhiều giao dịch xảy ra sát mốc dừng, `--stop-datetime` có thể không diễn đạt ranh giới transaction chính xác như mong muốn. Hãy đọc nội dung sự kiện, xác định position/GTID và kiểm tra file đầu ra trước khi áp dụng.

Khi đã xác minh file SQL, có thể phát lại vào instance phục hồi bằng tài khoản có quyền cần thiết:

```bash
mysql \
  --host=recovery-target.internal \
  --user=recovery_admin \
  --password \
  < /secure/recovery/replay-window.sql
```

Đây là ví dụ minh họa; bảo đảm instance đích đã được khôi phục từ đúng backup, không có ứng dụng ghi dữ liệu ngoài dự kiến và file replay chỉ chứa các sự kiện hợp lệ. Nếu phải loại bỏ một giao dịch lỗi ở giữa chuỗi, hãy xây dựng phạm vi phát lại chính xác theo transaction và position thay vì chạy toàn bộ file một cách máy móc.

Giữ binary log đủ lâu cho cửa sổ PITR đã cam kết. Không purge log khi replica còn cần chúng hoặc khi backup gần nhất vẫn phụ thuộc vào chúng. Theo dõi tính liên tục của file, dung lượng, thời hạn lưu và khả năng truy cập keyring trên host phục hồi.

## 10. Kiểm tra và xử lý sự cố

Một số kiểm tra cơ bản:

```sql
SHOW GLOBAL VARIABLES LIKE 'binlog_encryption';
SHOW BINARY LOGS;
SHOW GLOBAL VARIABLES LIKE 'log_bin';
```

`SHOW BINARY LOGS` giúp kiểm tra danh sách file và, trên phiên bản hỗ trợ, trạng thái mã hóa của từng file. Có thể kiểm tra thông tin replication trên replica bằng:

```sql
SHOW REPLICA STATUS\G
```

Kết quả giúp xác định relay log hiện tại và trạng thái replica. Tên cột, quyền và cú pháp có thể khác ở các phiên bản cũ; hãy dùng câu lệnh tương ứng phiên bản đang chạy.

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| MySQL không mở được binary log đã mã hóa | Keyring chưa được nạp, backend không truy cập được hoặc thiếu key cần thiết | Kiểm tra error log, cấu hình keyring, quyền truy cập và khả năng kết nối backend trước khi thao tác với file log. |
| `mysqlbinlog` đọc trực tiếp file mã hóa thất bại | Công cụ đang cố đọc file encrypted từ filesystem mà không có cơ chế giải mã của mysqld | Kết nối tới MySQL Server có keyring bằng `--read-from-remote-server`. |
| Bật mã hóa nhưng một số file vẫn báo không mã hóa | File đã tồn tại trước khi bật hoặc chưa được tạo lại theo chính sách | Kiểm tra trạng thái từng file; giữ file cũ theo retention và chỉ xóa khi không còn phụ thuộc. |
| Replica có relay log không mã hóa | `binlog_encryption` chưa được bật trên replica hoặc file relay log được tạo trước khi bật | Cấu hình riêng trên replica, kiểm tra file mới và xử lý log cũ theo quy trình replication. |
| Khôi phục từ backup nhưng không đọc được log | Backup thiếu keyring hoặc không còn quyền tới keyring bên ngoài | Khôi phục đúng keyring/định danh khóa và cấu hình backend; diễn tập để xác minh trước khi cần thực tế. |
| Xoay master key báo lỗi | Keyring không sẵn sàng, thiếu quyền hoặc backend gặp sự cố | Dừng thay đổi tiếp theo, kiểm tra error log và backend; không xóa key cũ hoặc tự sửa file log. |
| Đọc log được nhưng file SQL trung gian bị lộ | File đã giải mã nằm ngoài vùng lưu trữ bảo vệ | Hạn chế quyền, mã hóa storage, kiểm soát retention và xóa an toàn theo chính sách. |

Khi điều tra lỗi, giữ bản sao file gốc và metadata trước khi thử sửa. Không dùng hex editor, script tự giải mã hoặc đổi tên file để vượt qua lỗi keyring; các thao tác này có thể phá hỏng bằng chứng và làm mất khả năng phục hồi.

## 11. Tình huống thực hành

Một hệ thống đơn hàng chạy MySQL 8.0.36. Nhóm vận hành bật binary log để hỗ trợ replica và PITR. Chính sách bảo mật yêu cầu file log trên source và relay log trên replica phải được mã hóa khi lưu. Nhóm cũng cần bảo đảm có thể đọc log sau khi source bị mất máy.

**Bước 1 — Chuẩn bị keyring.** Chọn backend keyring được hỗ trợ cho phiên bản MySQL, cấu hình để keyring sẵn sàng khi server khởi động và lưu hướng dẫn khôi phục ở kho bí mật. Xác nhận host phục hồi có thể được cấp quyền truy cập cùng keyring hoặc bản sao tương ứng.

**Bước 2 — Bật mã hóa trên từng máy chủ.** Cấu hình `binlog_encryption=ON` trên source và từng replica. Kiểm tra biến hệ thống, xoay log nếu cần và xác nhận trạng thái mã hóa của file mới bằng `SHOW BINARY LOGS` ở nơi có hỗ trợ cột `Encrypted`.

**Bước 3 — Bảo vệ replication.** Cấu hình TLS cho kết nối replication. Kiểm tra source, replica và relay log để xác nhận chính sách at rest và in transit đều được áp dụng.

**Bước 4 — Sao lưu đủ thành phần.** Backup database, binary log, metadata GTID/position, cấu hình MySQL và keyring theo phương thức được backend hỗ trợ. Bản sao keyring được lưu trong miền lỗi độc lập và chỉ nhóm phục hồi được cấp quyền.

**Bước 5 — Diễn tập mất source.** Dựng host phục hồi cô lập, khôi phục backup và keyring, khởi động MySQL rồi dùng `mysqlbinlog --read-from-remote-server` để đọc log. Phát lại tới một mốc thử, xác minh dữ liệu và đo thời gian phục hồi.

**Bước 6 — Diễn tập mất keyring.** Thử quy trình khôi phục keyring từ bản sao được bảo vệ. Xác nhận server đọc được file log cũ và file log mới. Ghi nhận người có quyền cấp quyền khẩn cấp, thời gian cần để lấy khóa và các bước phụ thuộc dịch vụ bên ngoài.

Nếu bài diễn tập không thể đọc file log sau khi khôi phục keyring, chưa được xem quy trình PITR là đạt. Cần giải quyết phụ thuộc khóa, phiên bản hoặc phạm vi backup trước khi đưa chính sách vào production.

## 12. Checklist trước khi đưa vào production

- [ ] Phiên bản MySQL hỗ trợ `binlog_encryption` và keyring đã được cấu hình theo tài liệu tương ứng.
- [ ] Keyring sẵn sàng trước khi MySQL mở các file log được mã hóa.
- [ ] `binlog_encryption=ON` được cấu hình trên source và từng replica cần bảo vệ log cục bộ.
- [ ] Đã kiểm tra trạng thái mã hóa của các file mới và xác định file lịch sử chưa mã hóa.
- [ ] Kết nối replication và kết nối đọc log từ xa sử dụng TLS theo chính sách.
- [ ] Keyring, cấu hình backend và thông tin truy cập được backup ở miền lỗi độc lập.
- [ ] Có quy trình xoay binary log master key và xác minh khả năng đọc log cũ sau khi xoay.
- [ ] Không xóa khóa còn cần cho binary log, relay log, backup hoặc bản sao lưu lịch sử.
- [ ] `mysqlbinlog --read-from-remote-server` đã được thử trên host phục hồi có keyring.
- [ ] Đã diễn tập khôi phục sau sự cố source và sự cố mất quyền truy cập keyring.
- [ ] File SQL đã giải mã được bảo vệ bằng phân quyền, mã hóa storage và retention phù hợp.
- [ ] Retention binary log đáp ứng replica và cửa sổ PITR; đã đo RPO/RTO trong restore drill.

Khả năng đọc binary log sau sự cố phụ thuộc đồng thời vào file log, phiên bản MySQL tương thích, keyring và quy trình truy cập khóa. Bảo vệ từng thành phần, sao lưu chúng ở miền lỗi độc lập và diễn tập đọc log đã mã hóa là điều kiện để PITR tiếp tục hoạt động khi máy chủ nguồn không còn sẵn sàng.
