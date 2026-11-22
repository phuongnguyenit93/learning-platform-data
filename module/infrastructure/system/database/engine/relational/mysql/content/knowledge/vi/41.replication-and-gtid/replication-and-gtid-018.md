# Bảo vệ log còn cần cho replica và phát hiện giao dịch ngoài luồng

Trong module `DATABASE_MYSQL`, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài học này tập trung vào hai việc quan trọng khi vận hành replication có GTID: giữ binary log đủ lâu để replica còn có thể bắt kịp, và phát hiện transaction xuất hiện trên replica nhưng không thuộc lịch sử hợp lệ của source.

Một replica có thể dừng nhận log vì mất mạng, bảo trì hoặc lỗi máy chủ. Nếu source xóa binary log mà replica cần, replica không thể tự lấy lại các transaction đã mất khỏi nguồn đó. Tương tự, một thao tác ghi trực tiếp trên replica có thể tạo ra transaction ngoài luồng (errant transaction), làm các GTID giữa các máy chủ không còn đồng nhất. Cần quản lý retention, theo dõi tiến độ và kiểm tra GTID trước khi thay đổi topology hoặc failover.

## 1. Phân biệt binary log và relay log

Replication sử dụng hai loại log có vai trò khác nhau:

| Loại log | Được tạo ở đâu | Vai trò | Rủi ro khi mất hoặc xóa sớm |
|---|---|---|---|
| Binary log (binlog) | Source; cũng có thể có trên replica nếu bật `log_bin` | Ghi lại transaction để replica, công cụ CDC và quy trình PITR đọc lại. | Replica có thể không lấy được transaction còn thiếu; PITR có thể không đi tới được thời điểm cần phục hồi. |
| Relay log | Replica | Lưu các sự kiện đã nhận từ source, chờ applier thực thi. | Replica có thể mất các sự kiện đã nhận nhưng chưa áp dụng; phải khôi phục lại từ source nếu log nguồn còn tồn tại. |

Luồng replication cơ bản là source ghi transaction vào binary log, luồng receiver trên replica đọc log và ghi vào relay log, sau đó applier áp dụng sự kiện vào dữ liệu. Vì vậy, việc một transaction có trong relay log không có nghĩa nó đã được áp dụng vào bảng. Khi dùng GTID, có thể theo dõi riêng tập transaction đã nhận và tập transaction đã thực thi.

Trên replica, `SHOW REPLICA STATUS\G` cung cấp các thông tin như `Retrieved_Gtid_Set`, `Executed_Gtid_Set`, `Source_Log_File`, `Read_Source_Log_Pos`, `Relay_Source_Log_File` và `Exec_Source_Log_Pos`. Các trường này giúp xác định replica đang nhận đến đâu và applier đã xử lý đến đâu.

## 2. Lập chính sách giữ binary log

### Tính thời gian retention theo nhu cầu thực tế

Thời gian giữ binary log phải đủ dài cho tất cả đối tượng sử dụng log, bao gồm:

- Replica có thể bị ngắt kết nối trong thời gian bảo trì, lỗi mạng hoặc sự cố hạ tầng.
- Thời gian phát hiện replica bị tụt lại, xử lý nguyên nhân và đưa replica hoạt động trở lại.
- Thời gian cần để khôi phục hoặc dựng lại replica từ backup/clone nếu máy chủ bị mất.
- Replica có chủ đích chạy trễ (delayed replica).
- Công cụ CDC, hệ thống phân tích hoặc dịch vụ khác đọc binlog.
- Quy trình point-in-time recovery (PITR) cần log sau mốc backup.

Một cách lập kế hoạch là lấy khoảng gián đoạn tối đa dự kiến cộng với thời gian phát hiện, sửa chữa hoặc dựng lại replica, rồi cộng thêm biên an toàn. Nếu một replica có thể offline 3 ngày và cần thêm 1 ngày để khôi phục, kiểm tra và bắt kịp, retention 4 ngày sẽ không có khoảng dự phòng. Hệ thống cũng cần tính đến tốc độ phát sinh binlog và dung lượng lưu trữ để bảo đảm đủ chỗ cho cửa sổ retention đã chọn.

Không chọn retention chỉ dựa trên lịch backup hằng ngày. Một replica có thể offline lâu hơn một chu kỳ backup; một delayed replica còn cần log cũ có chủ đích; một quy trình PITR có thể cần nhiều ngày log sau bản backup đầy đủ.

### Cấu hình tự động hết hạn

Trên MySQL 8.0, `binlog_expire_logs_seconds` đặt thời gian tính bằng giây mà binary log được giữ trước khi đủ điều kiện hết hạn. Ví dụ sau đặt 14 ngày:

```sql
SET PERSIST binlog_expire_logs_seconds = 1209600;
```

`SET PERSIST` lưu giá trị cho các lần khởi động sau trên phiên bản hỗ trợ. Con số 14 ngày chỉ là ví dụ; hãy tính retention theo topology, tốc độ sinh log, thời gian khôi phục và yêu cầu PITR của hệ thống. Nếu đang dùng cấu hình cũ dựa trên `expire_logs_days`, hãy kiểm tra tài liệu phiên bản MySQL trước khi chuyển đổi.

Kiểm tra giá trị đang áp dụng và danh sách binary log:

```sql
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'log_bin';
SHOW BINARY LOGS;
```

Tự động hết hạn dựa trên tuổi log, không phải bằng chứng rằng mọi replica đã nhận xong các sự kiện trong file sắp bị xóa. Một replica offline lâu hơn retention vẫn có thể cần file đã hết hạn. Do đó, retention phải được đặt đủ rộng và phải có cảnh báo khi replica tiến gần giới hạn log còn sẵn.

### Xóa binary log thủ công

MySQL cho phép xóa log cũ bằng `PURGE BINARY LOGS`. Ví dụ:

```sql
PURGE BINARY LOGS TO 'mysql-bin.000120';
```

Lệnh trên xóa các binary log đứng trước file `mysql-bin.000120`; file được nêu làm mốc không bị xóa. Có thể dùng mốc thời gian:

```sql
PURGE BINARY LOGS BEFORE '2026-11-01 00:00:00';
```

Trước khi purge, cần xác minh tất cả replica đã nhận các transaction trong những file sắp xóa, các delayed replica không cần chúng nữa, và backup/PITR hoặc CDC không còn phụ thuộc vào chúng. Không dựa vào việc lệnh purge chạy thành công để kết luận replica đã an toàn. Việc purge thủ công không thay thế kiểm tra trạng thái replication.

Không xóa file binlog trực tiếp bằng thao tác trên hệ điều hành. Hãy dùng câu lệnh quản trị MySQL để máy chủ cập nhật đúng binary log index và metadata liên quan.

## 3. Theo dõi replica trước khi log hết hạn

Trên từng replica, kiểm tra trạng thái receiver và applier:

```sql
SHOW REPLICA STATUS\G
```

Các trường quan trọng:

| Trường | Ý nghĩa vận hành |
|---|---|
| `Replica_IO_Running` | Cho biết luồng nhận sự kiện từ source có đang chạy hay không. |
| `Replica_SQL_Running` | Cho biết luồng applier có đang chạy hay không. |
| `Source_Log_File`, `Read_Source_Log_Pos` | File và vị trí mà luồng nhận đang đọc từ source. |
| `Relay_Source_Log_File`, `Exec_Source_Log_Pos` | File nguồn và vị trí tương ứng với tiến độ áp dụng. |
| `Retrieved_Gtid_Set` | GTID đã được replica nhận. |
| `Executed_Gtid_Set` | GTID đã được thực thi trên replica. |
| `Last_IO_Error`, `Last_SQL_Error` | Lỗi ở luồng nhận hoặc luồng áp dụng. |
| `Seconds_Behind_Source` | Ước lượng độ trễ; có thể không phản ánh đầy đủ tình trạng khi luồng dừng hoặc thiếu dữ liệu thời gian. |

Không dùng riêng `Seconds_Behind_Source` để quyết định purge. Một replica có thể báo độ trễ thấp nhưng đang có lỗi, hoặc receiver đã dừng và không cập nhật số liệu theo cách người vận hành kỳ vọng. Hãy kiểm tra trạng thái hai luồng, GTID set, file/position và thông báo lỗi.

Trên source, theo dõi các binary log còn tồn tại:

```sql
SHOW BINARY LOGS;
SELECT @@GLOBAL.gtid_executed, @@GLOBAL.gtid_purged;
```

`gtid_executed` là tập GTID mà máy chủ đã thực thi. `gtid_purged` là tập GTID của các transaction đã được thực thi nhưng binary log tương ứng không còn được giữ trên máy chủ. Giá trị `gtid_purged` giúp nhận biết lịch sử đã bị purge; nó không chứa nội dung transaction và không thể thay thế các file binlog đã xóa.

Với GTID auto-position, replica yêu cầu source cung cấp những transaction mà replica chưa có. Nếu source đã purge binary log cần thiết và không còn cách cung cấp các transaction đó, replica không thể bắt kịp chỉ bằng cách thử kết nối lại. Khi đó thường phải dựng lại replica từ một backup hoặc clone mới có GTID state nhất quán, rồi cho replica tiếp tục nhận transaction mới.

## 4. Bảo vệ log trên replica trung gian và relay log

### Khi replica còn phục vụ replica phía sau

Trong topology nhiều tầng, một replica có thể đồng thời là source cho các replica khác. Máy chủ trung gian cần bật binary logging và `log_replica_updates=ON` để các transaction nhận từ upstream rồi áp dụng được ghi tiếp vào binary log của chính nó.

Ví dụ cấu hình cơ bản trên replica trung gian:

```ini
[mysqld]
server_id=102
log_bin=mysql-bin
log_replica_updates=ON
gtid_mode=ON
enforce_gtid_consistency=ON
```

Nếu `log_bin` tắt, máy chủ không có binary log để downstream đọc. Nếu `log_replica_updates` tắt, các transaction được áp dụng từ source không được ghi tiếp vào binary log của replica; downstream có thể không nhận được lịch sử transaction cần thiết từ máy chủ trung gian. Trên phiên bản cũ, tên biến tương ứng là `log_slave_updates`.

Máy chủ trung gian cũng cần retention đủ dài cho các replica phía sau. Việc source đầu tiên giữ log 30 ngày không giúp downstream nếu replica trung gian chỉ giữ log 1 ngày và một replica phía sau offline 3 ngày. Mỗi tầng cần chính sách riêng theo thời gian outage và khả năng dựng lại của các replica phụ thuộc vào nó.

### Quản lý relay log

MySQL quản lý vòng đời relay log qua cơ chế replication. `relay_log_purge` thường được bật để tự xóa các relay log đã được applier xử lý. Không tự xóa relay log bằng lệnh hệ điều hành, kể cả khi thấy nhiều file cũ trong thư mục dữ liệu. Nếu relay log đầy hoặc replica dừng áp dụng, hãy xử lý nguyên nhân như lỗi SQL, thiếu dung lượng, transaction bị khóa hoặc cấu hình applier.

Khi cần khôi phục sau lỗi máy chủ replica, làm theo quy trình recovery của MySQL và xác minh relay log, vị trí đã thực thi, GTID set và binary log còn trên source. Không xóa relay log để “làm sạch” rồi tự khởi động lại replication khi chưa hiểu transaction nào đã nhận nhưng chưa được áp dụng.

## 5. Giao dịch ngoài luồng (errant transaction) là gì?

Errant transaction là transaction có GTID xuất hiện trong lịch sử đã thực thi của một replica nhưng không thuộc tập transaction hợp lệ được kế thừa từ source hoặc topology được phê duyệt. Trường hợp phổ biến là quản trị viên hoặc ứng dụng ghi trực tiếp lên replica trong khi replica được kỳ vọng chỉ nhận dữ liệu qua replication.

Ví dụ:

1. Source có các transaction GTID do source tạo và truyền xuống replica.
2. Một quản trị viên tạm tắt chế độ chỉ đọc rồi chạy `UPDATE` trực tiếp trên replica.
3. Replica ghi transaction cục bộ với SID/UUID của chính replica vào GTID history.
4. Khi so sánh với source, GTID cục bộ này xuất hiện trong replica nhưng không có trong tập GTID của source.

Errant transaction có thể làm dữ liệu hai máy chủ khác nhau. Khi replica được promote thành source mới, transaction ngoài luồng có thể được truyền tiếp đến các replica khác hoặc tạo ra lịch sử GTID không đúng với ý định ban đầu. GTID auto-position không tự phát hiện ý nghĩa nghiệp vụ của transaction và không tự sửa dữ liệu bị lệch.

Nguồn thường gặp của errant transaction:

- Chạy `INSERT`, `UPDATE`, `DELETE` hoặc DDL trực tiếp trên replica bằng tài khoản quản trị.
- Tắt `read_only`/`super_read_only` để sửa lỗi rồi quên khôi phục.
- Chạy script bảo trì, event hoặc job cục bộ có thao tác ghi trên replica.
- Dùng replica làm môi trường kiểm thử hoặc báo cáo nhưng cho phép ghi dữ liệu.
- Thực hiện thao tác ghi thủ công trong quá trình chuẩn bị failover.

## 6. Phát hiện errant transaction bằng GTID set

### Thu thập GTID set từ source và replica

Trên source dự kiến, ghi lại UUID và tập GTID đã thực thi:

```sql
SELECT
    @@GLOBAL.server_uuid AS source_uuid,
    @@GLOBAL.gtid_executed AS source_gtid_executed;
```

Trên replica cần kiểm tra:

```sql
SELECT
    @@GLOBAL.server_uuid AS replica_uuid,
    @@GLOBAL.gtid_executed AS replica_gtid_executed,
    @@GLOBAL.gtid_purged AS replica_gtid_purged;
```

Trong mô hình một source và một replica, replica bình thường sẽ có tập GTID thực thi bao gồm các transaction hợp lệ mà source đã truyền xuống, có thể trễ một phần nếu applier chưa bắt kịp. Để tìm GTID có ở replica nhưng không có trong tập của source, sao chép giá trị `source_gtid_executed` từ source vào biến ở phiên kết nối replica:

```sql
SET @expected_source_gtids = 'SOURCE_GTID_EXECUTED_COPIED_FROM_SOURCE';

SELECT
    GTID_SUBTRACT(@@GLOBAL.gtid_executed, @expected_source_gtids)
        AS extra_gtids_on_replica,
    GTID_SUBTRACT(@expected_source_gtids, @@GLOBAL.gtid_executed)
        AS source_gtids_not_yet_executed;
```

Hai kết quả có ý nghĩa khác nhau:

- `extra_gtids_on_replica`: GTID đã thực thi trên replica nhưng không có trong tập GTID source được dùng làm chuẩn. Trong topology một source, đây là tập cần điều tra vì có thể chứa errant transaction.
- `source_gtids_not_yet_executed`: GTID có ở source nhưng replica chưa thực thi. Đây thường là transaction replica còn thiếu hoặc chưa áp dụng xong, không phải errant transaction.

`GTID_SUBTRACT(set1, set2)` trả về các GTID có trong `set1` nhưng không có trong `set2`. Vì vậy, thứ tự hai tham số rất quan trọng. Không kết luận errant transaction chỉ từ việc hai chuỗi GTID khác nhau; cần xác định tập transaction nào là lịch sử hợp lệ theo topology.

### Giới hạn khi diễn giải kết quả

Phép so sánh trên phù hợp với topology một source đã xác định. Với multi-source replication, nhiều channel, replication filter hoặc topology đã đổi source, tập GTID hợp lệ có thể bao gồm transaction từ nhiều SID. Khi đó, phải xây dựng tập GTID kỳ vọng từ toàn bộ nguồn/channel hợp lệ; so sánh replica với duy nhất một source có thể đánh dấu nhầm transaction hợp lệ là ngoài luồng.

GTID set cũng chỉ phản ánh transaction được ghi nhận trong lịch sử GTID. Thay đổi dữ liệu thực hiện khi tắt binary logging bằng `sql_log_bin=0` có thể không tạo GTID để phép so sánh phát hiện. Một số dạng data drift hoặc hỏng dữ liệu cũng không nhất thiết tạo ra GTID khác biệt. Vì vậy, kiểm tra GTID nên kết hợp với audit log, quyền tài khoản, kiểm tra dữ liệu nghiệp vụ và đối chiếu checksum khi cần.

## 7. Ngăn ngừa transaction ngoài luồng

Trên replica chỉ phục vụ đọc, bật chế độ chỉ đọc:

```sql
SET PERSIST read_only = ON;
SET PERSIST super_read_only = ON;
```

`super_read_only=ON` cũng bật `read_only` và chặn phần lớn thao tác ghi từ client, kể cả các tài khoản có quyền quản trị cao; replication applier vẫn có thể áp dụng transaction từ source. Người có quyền quản trị đủ cao vẫn có thể thay đổi cấu hình, nên đây là lớp bảo vệ quan trọng chứ không thay thế kiểm soát quyền và audit.

Các biện pháp vận hành khác:

1. Chỉ cấp quyền ghi trên source cho tài khoản ứng dụng; tách tài khoản quản trị khỏi tài khoản đọc báo cáo.
2. Hạn chế số người có thể tắt `read_only` hoặc `super_read_only`, và ghi nhận mọi thay đổi cấu hình.
3. Không chạy job nghiệp vụ, event hoặc script có thao tác ghi trên replica đọc.
4. Theo dõi thay đổi trạng thái read-only, thao tác quản trị và các lệnh có thể tạo transaction cục bộ.
5. Trước khi failover, kiểm tra GTID set của candidate và xác minh không có transaction ngoài luồng.
6. Sau khi thay đổi topology, cập nhật runbook để mọi thao tác ghi có chủ đích đều đi qua source mới.

Kiểm tra trạng thái hiện tại:

```sql
SHOW VARIABLES LIKE 'read_only';
SHOW VARIABLES LIKE 'super_read_only';
```

Nếu có yêu cầu bảo trì buộc phải ghi trực tiếp trên replica, cần có phê duyệt, ghi lại câu lệnh và phạm vi dữ liệu, xác định tác động GTID, rồi đưa replica về trạng thái chuẩn trước khi tiếp tục replication hoặc đưa vào danh sách candidate failover.

## 8. Xử lý khi phát hiện errant GTID

Khi `extra_gtids_on_replica` không rỗng, dừng việc promote replica cho đến khi hiểu rõ các transaction đó. Quy trình điều tra có thể gồm:

1. **Giữ bằng chứng.** Ghi lại `server_uuid`, `gtid_executed`, `gtid_purged`, trạng thái replication, binary log và thời điểm phát hiện. Tạo backup/clone phục vụ phân tích trước khi thay đổi trạng thái.
2. **Xác định transaction.** Nếu binary log còn tồn tại, dùng `mysqlbinlog` để xem các GTID liên quan và xác định câu lệnh hoặc dữ liệu đã thay đổi. Ví dụ:

   ```bash
   mysqlbinlog --include-gtids='REPLICA_UUID:120-122' mysql-bin.000045
   ```

   Thay UUID, khoảng GTID và tên file bằng giá trị thực tế. Không đưa dữ liệu nhạy cảm hoặc câu lệnh chứa bí mật vào báo cáo công khai.

3. **Xác định nguồn gốc.** Tìm tài khoản, job, event hoặc thao tác quản trị đã tạo transaction. Xác minh transaction đó có được phê duyệt hay là thao tác ngoài quy trình.
4. **Đánh giá dữ liệu.** Đối chiếu các bản ghi bị ảnh hưởng với source và yêu cầu nghiệp vụ. Một GTID khác biệt cho biết lịch sử transaction khác nhau; nó không tự cho biết thay đổi có đúng hay sai.
5. **Chọn cách phục hồi.** Nếu replica đã bị lệch và không thể chứng minh dữ liệu đúng, cách an toàn thường là dựng lại từ backup/clone nhất quán của source hợp lệ, giữ đúng GTID state theo hướng dẫn công cụ rồi nối lại bằng GTID auto-position. Nếu transaction là thay đổi hợp lệ cần giữ, hãy lập kế hoạch hợp nhất dữ liệu và topology có kiểm soát.
6. **Xác minh sau xử lý.** So sánh lại GTID set, kiểm tra dữ liệu nghiệp vụ, xác nhận replica bắt kịp và bật lại các cảnh báo giám sát.

Không xóa riêng một GTID khỏi `gtid_executed` bằng cách sửa metadata, không tùy tiện đặt `GTID_PURGED` và không dùng các lệnh reset binary log/GTID để che khác biệt. Những thao tác này có thể làm mất lịch sử cần thiết hoặc khiến topology không thể khôi phục đúng. Chỉ dùng quy trình GTID recovery được tài liệu MySQL hoặc công cụ quản trị topology hỗ trợ, sau khi đã có bản sao lưu và hiểu rõ hệ quả.

## 9. Quy trình vận hành định kỳ

Một quy trình quản lý log và GTID nên thực hiện theo chu kỳ:

1. **Kiểm kê topology.** Ghi nhận source, replica trung gian, downstream, delayed replica, channel và công cụ CDC/PITR đang tiêu thụ binlog.
2. **Đặt retention.** Tính thời gian outage tối đa, thời gian dựng lại và biên an toàn; kiểm tra dung lượng log phát sinh để dự báo dung lượng lưu trữ.
3. **Theo dõi sức khỏe.** Thu thập trạng thái receiver/applier, lỗi replication, GTID retrieved/executed, binary log hiện có và tuổi log cũ nhất còn giữ.
4. **Cảnh báo sớm.** Cảnh báo khi replica offline hoặc gần vượt cửa sổ retention; cảnh báo khi semi/async mode, GTID set hoặc trạng thái read-only thay đổi ngoài dự kiến.
5. **Rà soát trước purge.** Xác minh mọi replica và consumer đã qua mốc log sắp xóa; bảo đảm backup/PITR không còn cần log đó.
6. **Kiểm tra errant transaction.** So sánh GTID set theo topology hợp lệ sau các đợt bảo trì, thao tác ghi đặc biệt và trước mỗi lần failover.
7. **Diễn tập dựng lại.** Thử khôi phục một replica từ backup/clone và bắt kịp bằng binlog; ghi thời gian và các khoảng trống trong runbook.

## 10. Bài tập thực hành

Thiết lập một source và một replica có GTID trong môi trường thử nghiệm. Thực hiện các tình huống sau:

1. Ghi lại `@@GLOBAL.gtid_executed` và `@@GLOBAL.gtid_purged` trên source; ghi `Retrieved_Gtid_Set` và `Executed_Gtid_Set` trên replica.
2. Tạm dừng replication receiver trong môi trường thử nghiệm, tạo thêm transaction trên source và xác định replica cần những binary log nào để bắt kịp.
3. Kiểm tra `binlog_expire_logs_seconds`, `SHOW BINARY LOGS` và xây dựng cửa sổ retention đủ cho thời gian offline giả định cùng thời gian dựng lại.
4. Tạo một transaction cục bộ có kiểm soát trên replica trong môi trường thử nghiệm, sau đó so sánh GTID set bằng `GTID_SUBTRACT()` để tìm tập GTID chỉ có ở replica.
5. Khôi phục replica về trạng thái chỉ đọc, điều tra transaction ngoài luồng và lập phương án dựng lại hoặc hợp nhất dữ liệu.
6. Nếu có replica trung gian, kiểm tra `log_bin` và `log_replica_updates`, rồi xác minh downstream nhận được transaction hợp lệ.
7. Lập biên bản gồm retention, dung lượng log, GTID extra/missing, lỗi replication, cách xử lý và kết quả kiểm tra lại.

Sau bài tập, người học cần giải thích được vì sao source có thể purge log mà replica còn cần, vì sao `gtid_purged` không thay thế nội dung binary log, vì sao `Retrieved_Gtid_Set` khác `Executed_Gtid_Set`, và cách phân biệt transaction ngoài luồng với transaction replica chỉ đang áp dụng chậm. Đây là cơ sở để giữ topology MySQL có thể bắt kịp và giảm rủi ro khi failover.
