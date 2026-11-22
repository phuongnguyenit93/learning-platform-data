# Ảnh hưởng đến replication lag, dung lượng, redo và thời gian bảo trì

Thay đổi schema trên một bảng MySQL lớn có thể tác động tới toàn bộ hệ thống, kể cả khi ứng dụng chỉ thêm một cột hoặc một index. Tùy loại DDL và phiên bản MySQL, thao tác có thể chỉ cập nhật metadata, xây dựng lại cấu trúc bảng ngay tại chỗ hoặc tạo bảng trung gian rồi sao chép dữ liệu. Mỗi cách có chi phí khác nhau về thời gian khóa, CPU, I/O, dung lượng đĩa, redo/undo và binary log.

Trong topology replication, DDL còn được thực thi trên replica. Một thao tác hoàn tất nhanh ở primary nhưng mất nhiều thời gian trên replica có thể làm replication lag tăng, khiến truy vấn đọc trên replica trả dữ liệu cũ. Vì vậy, kế hoạch schema evolution cần dự đoán chi phí trên từng member, xác định thuật toán DDL, theo dõi backlog và có cách dừng hoặc khôi phục rõ ràng.

## 1. Vì sao một thay đổi schema có thể tốn nhiều tài nguyên?

`ALTER TABLE` không phải lúc nào cũng chỉ sửa một dòng metadata. MySQL có thể cần:

- Đọc toàn bộ bản ghi để chuyển đổi kiểu dữ liệu hoặc xây dựng lại clustered index.
- Tạo lại secondary index và cập nhật cấu trúc lưu trữ.
- Ghi các thay đổi phát sinh trong lúc DDL đang chạy vào online alter log.
- Ghi redo, undo và binary log cho phần công việc tương ứng.
- Dùng thêm file tạm hoặc bảng trung gian, trong khi bảng cũ vẫn tồn tại.
- Lấy metadata lock ở đầu và cuối thao tác để bảo đảm cấu trúc bảng không đổi giữa các bước quan trọng.

Chi phí phụ thuộc vào loại thay đổi, kích thước dữ liệu, số lượng index, row format, phiên bản MySQL, storage engine, tốc độ đĩa, tải ghi đồng thời và trạng thái replication. Hai bảng có cùng số dòng nhưng cấu trúc index hoặc kích thước bản ghi khác nhau có thể có thời gian thay đổi schema rất khác nhau.

Trước khi lên lịch, phân loại DDL theo cách thực hiện thực tế: `INSTANT`, `INPLACE` hay `COPY`. Tên thuật toán không phải lời bảo đảm tuyệt đối về mức độ online; cần xác nhận thao tác cụ thể được hỗ trợ trên đúng phiên bản và cấu trúc bảng.

## 2. Ba thuật toán DDL của InnoDB

### INSTANT — thay đổi metadata

`ALGORITHM=INSTANT` áp dụng cho những thay đổi được MySQL hỗ trợ bằng cách cập nhật metadata mà không phải xây dựng lại toàn bộ bảng. Ví dụ thường gặp là một số thao tác thêm hoặc bỏ cột trên các phiên bản MySQL 8.0 phù hợp.

```sql
ALTER TABLE sales.orders
  ADD COLUMN source_channel VARCHAR(32) NULL,
  ALGORITHM=INSTANT;
```

Đặc điểm:

- Thường hoàn tất rất nhanh, kể cả với bảng lớn, vì không cần quét và sao chép toàn bộ hàng.
- Hạn chế phát sinh I/O và dung lượng tạm so với thao tác rebuild.
- Vẫn cần metadata lock trong những thời điểm nhất định, nên có thể phải chờ transaction đang giữ metadata lock.
- Chỉ dùng được cho các thao tác và cấu trúc bảng được phiên bản đó hỗ trợ. Một số giới hạn thay đổi theo phiên bản, row format và lịch sử thay đổi bảng.

Khi chỉ định `ALGORITHM=INSTANT`, MySQL sẽ báo lỗi nếu thao tác không hỗ trợ instant thay vì tự chuyển sang thuật toán chậm hơn. Đây là cách tốt để ngăn một thay đổi dự kiến rất nhanh bất ngờ trở thành thao tác rebuild. Kiểm tra tài liệu của đúng phiên bản trước khi triển khai.

### INPLACE — thao tác trong cấu trúc InnoDB

`ALGORITHM=INPLACE` cho phép InnoDB thực hiện thay đổi mà không dùng quy trình `COPY` tổng quát tạo một bảng mới rồi sao chép toàn bộ dữ liệu. Tuy nhiên, **INPLACE không có nghĩa là không rebuild**. Một số thao tác vẫn phải xây dựng lại bảng hoặc index và có thể đọc/ghi lượng dữ liệu rất lớn.

Ví dụ tạo secondary index, nếu thao tác và bảng hỗ trợ online DDL:

```sql
ALTER TABLE sales.orders
  ADD INDEX idx_status_created (status, created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
```

`LOCK=NONE` yêu cầu cho phép DML đồng thời trong thời gian thao tác. Nếu MySQL không thể đáp ứng mức khóa đó cho thay đổi cụ thể, câu lệnh sẽ thất bại thay vì âm thầm dùng mức khóa chặt hơn. Dù vậy, DDL vẫn có thể cần metadata lock ngắn ở đầu hoặc cuối.

Với các online DDL cho phép DML đồng thời, InnoDB ghi nhận các thay đổi phát sinh trong lúc thao tác chạy vào online alter log rồi áp dụng chúng trước khi hoàn tất. Nếu lượng thay đổi vượt `innodb_online_alter_log_max_size`, DDL có thể thất bại. Tăng giới hạn có thể giảm nguy cơ vượt ngưỡng nhưng cũng làm tăng công việc phải xử lý ở giai đoạn cuối; không nên tăng biến này nếu chưa đo tải ghi và dung lượng.

### COPY — tạo bảng trung gian và sao chép dữ liệu

`ALGORITHM=COPY` tạo cấu trúc bảng trung gian, sao chép dữ liệu và index rồi chuyển đổi sang bảng mới. Đây thường là cách tốn tài nguyên nhất với bảng lớn.

Tác động có thể gồm:

- Đọc gần như toàn bộ bảng cũ và ghi lại bảng mới.
- Xây dựng lại các index trên bảng mới.
- Cần dung lượng đồng thời cho bảng cũ, bảng mới, index và file tạm.
- Tăng I/O, CPU và thời gian hoàn thành theo kích thước bảng.
- Giới hạn hoặc chặn một số thao tác ghi trong thời gian copy tùy mức khóa được hỗ trợ.
- Tạo một khoảng cutover cần metadata lock để đổi cấu trúc đang dùng.

Không coi `COPY` là lựa chọn an toàn chỉ vì bảng vẫn có thể đọc trong một phần thời gian. Hãy đánh giá tác động tới writer, reader, replica và dung lượng trước khi chạy.

### So sánh nhanh

| Thuật toán | Cách thực hiện | Tác động thường gặp | Điểm phải xác minh |
|---|---|---|---|
| `INSTANT` | Cập nhật metadata cho thao tác được hỗ trợ | Thời gian ngắn, ít I/O và dung lượng bổ sung | Phiên bản, loại thay đổi, row format, metadata lock |
| `INPLACE` | InnoDB xử lý thay đổi tại chỗ; một số thao tác vẫn rebuild | Có thể tốn CPU, I/O, redo và dung lượng đáng kể | Có rebuild hay không, hỗ trợ `LOCK=NONE`, online alter log |
| `COPY` | Tạo bảng trung gian và sao chép dữ liệu | Nhiều I/O, cần dung lượng lớn, có thể hạn chế ghi lâu | Thời gian copy, dung lượng đỉnh, khóa và cutover |

## 3. Metadata lock và thời gian chờ bảo trì

MySQL dùng metadata lock (MDL) để bảo vệ định nghĩa bảng, view, routine và các đối tượng liên quan khi câu lệnh đang sử dụng chúng. Một transaction truy cập bảng có thể giữ metadata lock cho tới khi transaction kết thúc. DDL cần lấy lock tương thích với thao tác thay đổi cấu trúc, thường cần quyền lock mạnh hơn ở thời điểm bắt đầu hoặc cutover.

Một tình huống dễ gây sự cố:

1. Transaction A mở và sử dụng bảng `sales.orders` nhưng không commit trong thời gian dài.
2. DDL B yêu cầu metadata lock độc quyền và phải chờ transaction A.
3. Các truy vấn C, D tiếp tục truy cập bảng có thể xếp hàng phía sau yêu cầu DDL đang chờ.
4. Một lệnh `ALTER TABLE` tưởng như chưa làm gì có thể tạo ra hàng đợi truy vấn và làm tăng thời gian phản hồi.

Vì vậy, thời gian bảo trì không chỉ là thời gian MySQL thực thi phần copy hoặc rebuild. Cần cộng cả thời gian chờ MDL, giai đoạn đồng bộ thay đổi phát sinh, cutover và xác minh sau thay đổi.

Kiểm tra các metadata lock đang tồn tại:

```sql
SELECT
  OBJECT_TYPE,
  OBJECT_SCHEMA,
  OBJECT_NAME,
  LOCK_TYPE,
  LOCK_DURATION,
  LOCK_STATUS,
  OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'sales'
  AND OBJECT_NAME = 'orders';
```

`LOCK_STATUS` cho biết lock đã được cấp hay đang chờ. Có thể liên kết `OWNER_THREAD_ID` với `performance_schema.threads` để tìm connection tương ứng:

```sql
SELECT
  ml.LOCK_STATUS,
  ml.LOCK_TYPE,
  ml.OWNER_THREAD_ID,
  th.PROCESSLIST_ID,
  th.PROCESSLIST_USER,
  th.PROCESSLIST_HOST,
  th.PROCESSLIST_TIME,
  th.PROCESSLIST_STATE,
  th.PROCESSLIST_INFO
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS th
  ON th.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.OBJECT_SCHEMA = 'sales'
  AND ml.OBJECT_NAME = 'orders';
```

Kiểm tra thêm `SHOW FULL PROCESSLIST` và các transaction đang mở. Trên hệ thống có schema `sys`, view `sys.schema_table_lock_waits` cũng hữu ích để xác định session đang chờ và session giữ lock.

Trước khi chạy DDL, có thể giới hạn thời gian chờ metadata lock trong session:

```sql
SET SESSION lock_wait_timeout = 30;
```

`lock_wait_timeout` điều khiển thời gian chờ metadata lock. Nó khác `innodb_lock_wait_timeout`, vốn điều khiển chờ row lock của InnoDB. Đặt timeout giúp DDL thất bại sớm khi đang có transaction giữ lock lâu, nhưng không làm thao tác DDL sau khi bắt đầu tự hoàn tất nhanh hơn.

Không `KILL` một session chỉ dựa trên thời gian chạy. Xác định đó là transaction nghiệp vụ, DDL đang chờ hay DDL đang copy; cân nhắc tác động rollback và phối hợp với người sở hữu workload trước khi kết thúc connection.

## 4. Ảnh hưởng đến replication lag

Khi bật binary logging, DDL được ghi vào binary log dưới dạng câu lệnh. DDL không biến thành row event chỉ vì `binlog_format=ROW`. Replica nhận sự kiện DDL và thực thi câu lệnh trên bảng cục bộ.

Điều này tạo ra hai nơi cần tính chi phí:

- Primary thực hiện thay đổi schema và chịu tải của DDL.
- Mỗi replica phải thực hiện DDL tương ứng, theo phiên bản và cấu trúc bảng của chính replica đó.

Nếu DDL trên replica mất nhiều thời gian, replication applier có thể không áp dụng được các transaction tiếp theo trong khoảng thời gian đó. Primary vẫn có thể tiếp tục nhận ghi, khiến relay log và backlog tăng. Truy vấn đọc trên replica có thể thấy dữ liệu cũ hoặc không sử dụng được trong thời gian schema change đang chạy.

Các nguyên nhân làm lag tăng:

1. Replica có I/O hoặc CPU thấp hơn primary nên rebuild kéo dài hơn.
2. Replica đang chạy truy vấn báo cáo hoặc backup làm cạnh tranh tài nguyên.
3. DDL tạo index hoặc rebuild bảng làm phát sinh nhiều I/O và redo.
4. DML tiếp tục phát sinh trên primary trong khi applier đang bận với DDL.
5. Các transaction lớn hoặc nhiều worker replication bị chặn bởi ranh giới thực thi DDL.
6. Phiên bản hoặc schema trên replica không tương thích với DDL, khiến applier dừng do lỗi thay vì chỉ tăng lag.

Trước khi chạy, kiểm tra tất cả replica và topology downstream. Một replica ở vùng khác hoặc có ổ đĩa chậm có thể trở thành nút thắt dù primary hoàn tất nhanh. Với chuỗi replication, lag ở một replica trung gian có thể lan tới các replica phía sau.

Kiểm tra trạng thái replication:

```sql
SHOW REPLICA STATUS\G
```

Theo dõi các trường như `Replica_IO_Running`, `Replica_SQL_Running`, `Seconds_Behind_Source`, `Last_SQL_Error`, `Retrieved_Gtid_Set` và `Executed_Gtid_Set`. `Seconds_Behind_Source` là chỉ báo hữu ích nhưng không phải phép đo đầy đủ trong mọi tình huống; có thể là `NULL` khi applier hoặc kết nối không ở trạng thái phù hợp. Kết hợp GTID, trạng thái worker và số liệu ứng dụng để xác định replica đã bắt kịp.

Trên MySQL 8.0, có thể xem trạng thái worker:

```sql
SELECT *
FROM performance_schema.replication_applier_status_by_worker;
```

Nếu dùng phiên bản cũ hơn, tên lệnh và cột trạng thái có thể khác. Hãy đối chiếu tài liệu đúng phiên bản.

### Không nhầm lag với lỗi replication

| Hiện tượng | Cách hiểu |
|---|---|
| `Replica_SQL_Running=Yes`, lag tăng | Applier vẫn chạy nhưng chưa bắt kịp workload hoặc DDL dài |
| `Replica_SQL_Running=No`, `Last_SQL_Error` có nội dung | Applier đã dừng vì lỗi; cần xử lý nguyên nhân, không chỉ chờ |
| `Replica_IO_Running=No` | Replica không nhận được log từ source; kiểm tra kết nối, quyền và trạng thái source |
| GTID đã nhận tăng nhưng GTID đã thực thi đứng yên | Transaction đang chờ hoặc applier bị chặn |
| Replica đọc được nhưng schema chưa đồng nhất | Kiểm tra DDL có bị trì hoãn, thất bại hoặc đã chạy thủ công ngoài luồng replication không |

Không promote một replica đang lag hoặc có schema chưa đồng nhất nếu chưa đánh giá các transaction còn thiếu và khả năng tương thích của ứng dụng.

## 5. Dung lượng đĩa cần dự trù

Với thao tác rebuild hoặc `COPY`, bảng cũ thường vẫn cần tồn tại trong khi MySQL tạo cấu trúc mới. Dung lượng đỉnh có thể gồm:

- Bảng InnoDB hiện tại.
- Bảng trung gian hoặc bản dựng lại.
- Secondary index được tạo lại.
- File tạm và vùng làm việc của DDL.
- Redo log, undo tablespace và binary log phát sinh trong thời gian thao tác.
- Relay log trên replica khi DDL hoặc các transaction tiếp theo đang chờ áp dụng.
- Dung lượng backup/snapshot hoặc bản sao do công cụ migration tạo ra.

Không lấy kích thước file `.ibd` hiện tại làm mức dung lượng cần có. Với rebuild, cần đủ chỗ cho bản cũ và bản mới cùng tồn tại, cộng thêm phần phát sinh và khoảng trống vận hành. Mức đỉnh cụ thể tùy thuật toán, file-per-table, tablespace, index, phiên bản và công cụ sử dụng.

Ước lượng kích thước dữ liệu và index của một bảng:

```sql
SELECT
  TABLE_SCHEMA,
  TABLE_NAME,
  ENGINE,
  TABLE_ROWS,
  ROUND(DATA_LENGTH / 1024 / 1024, 1) AS data_mb,
  ROUND(INDEX_LENGTH / 1024 / 1024, 1) AS index_mb,
  ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 1) AS total_mb
FROM information_schema.tables
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'orders';
```

Với InnoDB, `TABLE_ROWS` thường là ước lượng, không phải số đếm chính xác. `DATA_LENGTH` và `INDEX_LENGTH` giúp lập kế hoạch sơ bộ; cần kết hợp dung lượng filesystem, tablespace và lịch sử tăng trưởng thực tế.

Kiểm tra vị trí dữ liệu, file tạm và binary log:

```sql
SHOW VARIABLES LIKE 'datadir';
SHOW VARIABLES LIKE 'tmpdir';
SHOW VARIABLES LIKE 'innodb_data_home_dir';
SHOW VARIABLES LIKE 'log_bin_basename';
SHOW BINARY LOGS;
```

Các file có thể nằm trên nhiều filesystem hoặc volume khác nhau. Nhóm vận hành cần kiểm tra dung lượng trống ở từng mount point trên host, volume của datadir, tmpdir, redo/undo, binary log và relay log. Một thư mục tạm hết chỗ có thể làm DDL thất bại dù volume chứa bảng vẫn còn dung lượng.

Với công cụ online schema change, bảng shadow thường cần dung lượng gần với bảng gốc cộng index, trong khi bảng gốc vẫn phục vụ ứng dụng. Hãy cộng thêm dung lượng binlog, relay log và các bản sao giữ lại trong quá trình cutover.

## 6. Redo, undo và online alter log

### Redo log

Redo log giúp InnoDB phục hồi các thay đổi đã ghi. Các thao tác rebuild, tạo index và DML đồng thời có thể tạo tải ghi đáng kể lên storage và redo. Khi tốc độ phát sinh redo cao hơn khả năng checkpoint/flush, dung lượng redo và áp lực I/O có thể tăng, ảnh hưởng cả DDL lẫn workload ứng dụng.

Trên các phiên bản MySQL hỗ trợ `innodb_redo_log_capacity`, dung lượng redo được quản lý bằng biến này. Thay đổi dung lượng có thể giúp hấp thụ burst ở mức phù hợp, nhưng không làm giảm lượng công việc DDL phải thực hiện. Cần theo dõi redo, checkpoint, I/O latency và `Innodb_log_waits` thay vì tăng capacity để che một thao tác rebuild quá nặng.

### Undo và purge

Undo log hỗ trợ rollback và consistent read. Transaction dài đang hoạt động có thể giữ lại phiên bản hàng cũ, làm purge không giải phóng được undo history. Khi schema change chạy cùng workload ghi lớn hoặc transaction dài, history list length và dung lượng undo có thể tăng. Cần rà soát transaction mở lâu trước khi bảo trì và theo dõi `SHOW ENGINE INNODB STATUS\G` khi nghi ngờ áp lực undo/purge.

### Online alter log

Với thao tác online DDL cho phép DML đồng thời, InnoDB cần ghi nhận các thay đổi phát sinh trong lúc xây dựng index hoặc bảng. Online alter log có giới hạn bởi `innodb_online_alter_log_max_size`.

Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'innodb_online_alter_log_max_size';
```

Nếu tải ghi liên tục cao, online alter log có thể tăng nhanh và vượt giới hạn, khiến thao tác thất bại. Tăng giới hạn có thể giúp nhưng cần đánh giá dung lượng và thời gian áp dụng log ở cuối. Một lựa chọn khác là giảm tải ghi, chia nhỏ thay đổi, chọn thời điểm ít traffic hoặc dùng chiến lược migration phù hợp hơn.

### Binary log và relay log

DDL được ghi vào binary log để replica thực hiện. DML trong thời gian migration cũng tiếp tục tạo binary log. Nếu applier chậm, relay log tích lũy và cần thêm dung lượng. Không purge binary log chỉ để giải phóng đĩa khi replica hoặc quy trình PITR vẫn cần chúng; phải tuân thủ retention và xác nhận mọi consumer đã đọc xong.

## 7. Những thay đổi schema có chi phí khác nhau

Không thể dự đoán thuật toán chỉ từ tên `ALTER TABLE`. Cần kiểm tra khả năng hỗ trợ của đúng phiên bản và cấu trúc bảng.

| Thay đổi | Chi phí thường gặp | Lưu ý |
|---|---|---|
| Thêm cột nullable được hỗ trợ instant | Thấp | Vẫn cần MDL; kiểm tra giới hạn phiên bản và vị trí cột |
| Thêm secondary index | Thường cần quét bảng và xây index bằng INPLACE | Tốn I/O, CPU, dung lượng index; có thể cho phép DML đồng thời |
| Đổi kiểu cột | Có thể rebuild hoặc COPY | Phụ thuộc kiểu cũ/mới, độ dài, charset, signedness và phiên bản |
| Thay đổi primary key | Thường rebuild clustered index | Có thể phải xây lại toàn bộ bảng và secondary index |
| Đổi charset/collation | Có thể chuyển đổi dữ liệu và rebuild index | Kiểm tra ký tự không biểu diễn được và thay đổi thứ tự so sánh |
| Đổi tên cột hoặc bảng | Có thể là thao tác metadata trong trường hợp hỗ trợ | Ứng dụng, view, trigger, procedure và replica cần tương thích |
| Thêm/bỏ partition | Phụ thuộc thao tác và cấu trúc partition | Có thể di chuyển dữ liệu hoặc rebuild partition liên quan |

Ví dụ đổi kiểu dữ liệu:

```sql
ALTER TABLE sales.orders
  MODIFY COLUMN customer_note VARCHAR(500) NULL;
```

Không chạy ví dụ này với giả định nó luôn là instant hoặc inplace. MySQL có thể phải rebuild tùy định nghĩa cột hiện tại, phiên bản và điều kiện của bảng. Nếu cần giới hạn thuật toán, hãy chỉ định `ALGORITHM` và `LOCK` phù hợp sau khi xác nhận khả năng hỗ trợ trên môi trường thử nghiệm.

## 8. Atomic DDL không có nghĩa là rollback bằng transaction

MySQL 8.0 hỗ trợ atomic DDL cho nhiều thao tác với InnoDB. Điều này giúp thao tác DDL được phục hồi nhất quán khi server gặp sự cố trong quá trình thực hiện: metadata và thay đổi từ thao tác được xử lý như một đơn vị nguyên tử theo phạm vi hỗ trợ.

Tuy nhiên, DDL vẫn có quy tắc implicit commit. Không thể bọc một `ALTER TABLE` trong transaction ứng dụng rồi dùng `ROLLBACK` để khôi phục schema như với DML. Atomic DDL cũng không tự phục hồi logic ứng dụng nếu code mới đã triển khai nhưng schema change thất bại, hoặc nếu migration đã hoàn tất mà ứng dụng chưa tương thích.

Vì vậy, mỗi migration cần có kế hoạch forward-fix hoặc migration ngược khả thi. Với thay đổi phá hủy dữ liệu như drop column, thu hẹp kiểu, đổi charset hoặc xóa bảng, hãy sao lưu và xác nhận dữ liệu đã được chuyển sang cấu trúc mới trước khi chạy bước không thể đảo ngược.

## 9. Lập kế hoạch thay đổi schema an toàn

Một quy trình production nên bắt đầu bằng đánh giá, không bắt đầu bằng câu lệnh `ALTER TABLE`.

### Trước khi chạy

1. Ghi nhận phiên bản MySQL, engine, DDL chính xác, `SHOW CREATE TABLE`, kích thước bảng và index.
2. Xác định thuật toán có thể dùng: `INSTANT`, `INPLACE` hay `COPY`; kiểm tra `LOCK` được hỗ trợ.
3. Đánh giá MDL, transaction mở lâu, writer và query dài đang sử dụng bảng.
4. Ước lượng dung lượng đỉnh trên primary và tất cả replica, bao gồm datadir, tmpdir, redo/undo, binlog và relay log.
5. Chạy thử trên bản sao có kích thước, index, phiên bản và tải ghi gần production.
6. Đo thời gian, I/O, redo, dung lượng, replication lag và ảnh hưởng tới p95/p99 ứng dụng.
7. Xác định ngưỡng dừng: lag tối đa, dung lượng trống tối thiểu, latency tối đa và thời gian bảo trì tối đa.
8. Thông báo tới các nhóm ứng dụng và vận hành; chuẩn bị phương án forward-fix, rollback ứng dụng hoặc phục hồi backup.

### Trong khi chạy

- Theo dõi processlist, metadata lock và trạng thái DDL.
- Theo dõi CPU, IOPS, storage latency, dung lượng filesystem, redo và online alter log.
- Theo dõi replication receiver/applier và GTID trên từng replica.
- Quan sát thời gian phản hồi, timeout, lock wait và lỗi của ứng dụng.
- Không chạy nhiều DDL rebuild nặng đồng thời trên cùng storage hoặc topology nếu chưa thử tải.
- Dừng mở rộng thay đổi khi lag, dung lượng hoặc latency chạm ngưỡng đã đặt.

### Sau khi chạy

- Kiểm tra `SHOW CREATE TABLE` và metadata để xác nhận schema đúng.
- Kiểm tra index, constraint, default, nullability, charset và collation.
- Xác nhận replica đã áp dụng DDL và GTID đã bắt kịp.
- Chạy smoke test trên ứng dụng và truy vấn quan trọng.
- Đối soát dữ liệu, đặc biệt khi có backfill hoặc chuyển kiểu.
- Ghi lại thời gian thực tế, mức dung lượng đỉnh, lag cao nhất và sự cố để cải thiện lần bảo trì sau.

## 10. Expand-and-contract cho thay đổi cần tương thích ứng dụng

Với thay đổi có ảnh hưởng tới code, nên triển khai schema và ứng dụng theo nhiều bước để tránh yêu cầu tất cả thành phần chuyển đổi cùng một thời điểm.

Ví dụ đổi từ cột `full_name` sang `display_name`:

1. **Expand:** thêm `display_name` nullable hoặc có default phù hợp. Chọn thuật toán được hỗ trợ và xác nhận không gây rebuild ngoài dự kiến.
2. **Ứng dụng tương thích:** triển khai code có thể đọc cột cũ và mới; ghi cả hai cột trong giai đoạn chuyển tiếp nếu cần.
3. **Backfill:** cập nhật dữ liệu cũ theo chunk nhỏ, có checkpoint. Mỗi chunk tạo redo, undo và binlog nên phải điều tiết tốc độ để tránh tăng lag.
4. **Switch reads:** chuyển ứng dụng sang đọc `display_name`, kiểm tra số lượng NULL và đối chiếu giá trị giữa hai cột.
5. **Stop old writes:** sau khi tất cả phiên bản ứng dụng đã chuyển, dừng ghi `full_name`.
6. **Contract:** chỉ ở một đợt triển khai sau mới bỏ `full_name`, sau khi xác nhận không còn code, view, trigger, procedure hoặc job phụ thuộc.

Backfill theo chunk:

```sql
UPDATE customers
SET display_name = full_name
WHERE customer_id > 0
  AND customer_id <= 10000
  AND display_name IS NULL;
```

Ví dụ dùng khoảng khóa để minh họa. Trong thực tế, chọn chunk theo primary key, số hàng, thời gian chạy và tải hệ thống. Cập nhật một chunk rồi commit, lưu checkpoint và nghỉ/giảm tốc nếu replication lag hoặc I/O tăng. Không chạy một transaction cập nhật toàn bộ bảng lớn nếu không cần thiết.

## 11. Khi nào cân nhắc công cụ online schema change?

Nếu native online DDL không đáp ứng yêu cầu khóa hoặc thời gian, có thể đánh giá công cụ như `pt-online-schema-change` hoặc `gh-ost`. Các công cụ này thường tạo bảng shadow, sao chép dữ liệu theo chunk, đồng bộ thay đổi phát sinh rồi thực hiện cutover.

Chúng giảm thời gian khóa kéo dài trong một số trường hợp, nhưng không loại bỏ chi phí:

- Cần dung lượng cho bảng shadow và index, thường gần bằng bảng gốc.
- Sao chép và đồng bộ thay đổi làm tăng CPU, I/O, redo và binary log.
- Replica vẫn phải xử lý các thay đổi phát sinh; lag có thể tăng.
- Cutover vẫn cần metadata lock và có thể bị chặn bởi transaction dài.
- `pt-online-schema-change` dùng trigger để đồng bộ thay đổi nên cần đánh giá trigger sẵn có, foreign key và overhead ghi.
- `gh-ost` dựa vào binary log để theo dõi thay đổi và có yêu cầu cấu hình/phiên bản riêng; cần kiểm tra khả năng tương thích topology trước khi dùng.

Không chọn công cụ chỉ vì tên có chữ “online”. Chạy thử trên bản clone, kiểm tra điều kiện hỗ trợ, quyền, binlog format, foreign key, trigger, replica topology, dung lượng và quy trình cutover. Công cụ migration là một workload lớn khác trên database, cần giới hạn tốc độ và giám sát như DDL native.

## 12. Chẩn đoán các dấu hiệu bất thường

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `ALTER TABLE` đứng lâu trước khi bắt đầu | Đang chờ metadata lock từ transaction hoặc query khác | Kiểm tra `performance_schema.metadata_locks`, processlist và transaction mở lâu |
| Truy vấn ứng dụng xếp hàng khi DDL chờ | DDL đang chờ lock mạnh và các yêu cầu mới bị xếp sau | Xác định blocker; giới hạn `lock_wait_timeout`; lên lịch lại nếu cần |
| DDL chạy nhưng I/O tăng mạnh | Rebuild, tạo index, COPY hoặc backfill | Theo dõi storage latency, điều tiết workload và kiểm tra dung lượng |
| Filesystem gần đầy | Bảng trung gian, index, tmp file, redo/binlog hoặc relay log tăng | Xác định volume tăng; dừng theo ngưỡng đã định, không xóa file log còn cần |
| `DB_ONLINE_LOG_TOO_BIG` hoặc lỗi online alter log | DML đồng thời vượt `innodb_online_alter_log_max_size` | Giảm tải ghi, chia nhỏ thay đổi hoặc đánh giá lại giới hạn và thời điểm chạy |
| Replica lag tăng sau DDL | Applier đang thực thi DDL hoặc không đủ tốc độ bắt kịp | Theo dõi worker/GTID, giảm ghi nếu cần và chờ replica bắt kịp trước bước tiếp theo |
| Replica SQL thread dừng | DDL không tương thích hoặc lỗi thực thi trên replica | Đọc `Last_SQL_Error`, so sánh version/schema và xử lý theo runbook replication |
| Ứng dụng lỗi sau migration | Code và schema không tương thích, constraint/default thay đổi | Dừng rollout code, xác định forward-fix hoặc khôi phục ứng dụng tương thích |

Giữ lại câu lệnh DDL, thời điểm bắt đầu/kết thúc, log MySQL, trạng thái replication và số liệu dung lượng khi điều tra. Không xóa file tạm hoặc binary log bằng thao tác filesystem khi chưa xác định MySQL có còn sử dụng chúng hay không.

## 13. Tình huống thực hành

Một bảng `sales.orders` có hàng chục triệu dòng, đang được ghi liên tục và có ba replica phục vụ đọc. Nhóm phát triển cần thêm index trên `(status, created_at)` để cải thiện truy vấn dashboard. Yêu cầu là giữ thời gian gián đoạn thấp, không để replica lag vượt ngưỡng và không làm đầy volume.

**Bước 1 — Đo hiện trạng.** Thu thập `SHOW CREATE TABLE`, kích thước data/index, tốc độ ghi, transaction dài, dung lượng trống trên cả bốn máy chủ và replication lag hiện tại.

**Bước 2 — Kiểm tra thuật toán.** Xác nhận phiên bản và InnoDB hỗ trợ tạo secondary index với `ALGORITHM=INPLACE, LOCK=NONE`. Thử trên bản sao có dữ liệu và tải ghi tương đương. Xác định online alter log có đủ giới hạn và disk có đủ chỗ cho index mới.

**Bước 3 — Chọn cửa sổ.** Chọn thời điểm tải ghi thấp, đặt ngưỡng lag, I/O latency, dung lượng trống và metadata lock wait. Đặt `lock_wait_timeout` cho session chạy DDL để tránh chờ MDL không giới hạn.

**Bước 4 — Chạy trên primary.** Thực thi DDL với thuật toán và lock đã xác nhận. Theo dõi tiến độ, disk, redo, online alter log, processlist và ứng dụng. Không chạy DDL rebuild khác đồng thời.

**Bước 5 — Theo dõi replica.** Quan sát từng replica khi applier thực thi DDL. Nếu một replica lag vượt ngưỡng, giữ nguyên kế hoạch rollout tiếp theo, giảm tải ghi hoặc chờ member bắt kịp theo runbook.

**Bước 6 — Xác minh.** Kiểm tra index trong `SHOW CREATE TABLE`, chạy truy vấn và `EXPLAIN`, xác nhận GTID đã được áp dụng trên tất cả replica và theo dõi latency sau migration.

Nếu native online DDL không đáp ứng được giới hạn khóa hoặc dung lượng, đánh giá công cụ online schema change trên staging. Tính cả bảng shadow, trigger hoặc binlog capture, tải copy và cutover trước khi chọn phương án.

## 14. Checklist trước khi bảo trì schema

- [ ] Đã xác định chính xác DDL, phiên bản MySQL, engine và cấu trúc bảng.
- [ ] Đã xác nhận thao tác hỗ trợ `INSTANT`, `INPLACE` hay cần `COPY`.
- [ ] Đã hiểu `INPLACE` có thể vẫn rebuild bảng và `LOCK=NONE` vẫn cần MDL ở một số giai đoạn.
- [ ] Đã kiểm tra transaction mở lâu và metadata lock trước khi chạy.
- [ ] Đã ước lượng dung lượng đỉnh cho bảng cũ, bảng mới, index, tmp, redo/undo, binlog và relay log.
- [ ] Đã kiểm tra `innodb_online_alter_log_max_size` và tải DML đồng thời.
- [ ] Đã thử trên bản sao có kích thước, index, phiên bản và tải gần production.
- [ ] Đã kiểm tra tất cả replica, phiên bản và schema tương thích.
- [ ] Đã đặt ngưỡng dừng cho replication lag, disk, I/O, latency và thời gian chờ MDL.
- [ ] Có kế hoạch xử lý khi DDL thất bại và phương án forward-fix/khôi phục phù hợp.
- [ ] Đã kiểm tra schema, index, dữ liệu, ứng dụng và GTID sau thay đổi.
- [ ] Đã ghi nhận thời gian thực tế, lag cao nhất, dung lượng đỉnh và kết quả kiểm thử.

Schema evolution là một thay đổi vận hành trên dữ liệu đang sống. `INSTANT` có thể giảm đáng kể chi phí khi thao tác được hỗ trợ; `INPLACE` vẫn có thể rebuild và tiêu thụ nhiều tài nguyên; `COPY` thường cần nhiều dung lượng và thời gian hơn. Trong môi trường replication, phải tính cả thời gian applier chạy DDL trên từng replica. Đánh giá thuật toán, metadata lock, redo/undo, dung lượng và ngưỡng replication lag trước khi bảo trì giúp tránh biến một thay đổi schema thành sự cố hiệu năng hoặc gián đoạn dịch vụ.
