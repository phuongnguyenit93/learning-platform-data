# Dung lượng trống, tăng trưởng tệp và tác động khi gần đầy đĩa

## Mục tiêu bài học

Một cơ sở dữ liệu có thể chậm hoặc ngừng ghi dù CPU và bộ nhớ vẫn còn dư. Nguyên nhân đôi khi rất đơn giản: volume chứa data file, WAL/redo log, temporary file hoặc backup sắp hết dung lượng. Khi hệ quản trị phải mở rộng tệp, ghi thêm trang, tạo index, spill dữ liệu tạm hoặc duy trì WAL nhưng thiết bị không còn chỗ, độ trễ có thể tăng đột ngột và các giao dịch có thể thất bại.

Trong chương **Lưu trữ và tài nguyên** của module **DATABASE_PERFORMANCE**, bài học này hướng dẫn cách quản lý dung lượng trống, theo dõi tăng trưởng tệp và nhận diện tác động khi đĩa gần đầy. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, quản lý dung lượng phải gắn với workload, kế hoạch bảo trì, WAL, temporary I/O, khả năng phục hồi và dự báo tăng trưởng.

Sau bài học, bạn có thể:

- Phân biệt dung lượng trống của filesystem/volume với dung lượng còn dùng được bên trong bảng hoặc tablespace.
- Xác định các nhóm tệp tiêu thụ dung lượng: data, index, WAL/redo, temporary, archive, backup và log.
- Giải thích vì sao mở rộng tệp hoặc gần đầy đĩa có thể gây tăng độ trễ và lỗi ghi.
- Dự báo thời gian còn lại trước khi chạm ngưỡng dung lượng an toàn.
- Theo dõi dung lượng database, tablespace, WAL, temp và filesystem bằng công cụ của hệ quản trị cùng hệ điều hành.
- Lập kế hoạch autogrowth, preallocation, bảo trì và mở rộng storage có kiểm soát.
- Kiểm chứng tác động của thay đổi bằng latency, throughput, I/O, dung lượng và khả năng phục hồi.

## 1. Dung lượng trống có nhiều lớp

Khi nói “database còn 100 GB”, cần làm rõ 100 GB đó là dung lượng trống ở đâu. Cơ sở dữ liệu sử dụng nhiều lớp lưu trữ và các lớp này không thay thế cho nhau.

| Lớp dung lượng | Ý nghĩa | Ví dụ cần theo dõi |
|---|---|---|
| Filesystem/volume | Dung lượng vật lý hoặc logical còn cấp phát được trên volume | Free bytes, quota, inode, thin-provisioned pool |
| Data file/tablespace | Dung lượng đã cấp cho bảng, index và metadata | File size, tablespace size, mức sử dụng trong database |
| Khoảng trống bên trong relation | Trang hoặc vùng đã cấp nhưng hiện có thể tái sử dụng | Dead tuples, free space, bloat và khả năng reuse |
| WAL/redo log | Nhật ký thay đổi phục vụ phục hồi và replication | WAL generation, segment đang giữ, archive backlog, log usage |
| Temporary storage | Không gian cho sort/hash spill, temporary table và thao tác trung gian | Temp files/bytes, temp tablespace, temp volume free |
| Backup/archive | Bản sao lưu, WAL archive và file xuất dữ liệu | Backup retention, archive backlog, tốc độ tăng và nơi lưu |

Một bảng có thể còn nhiều trang trống bên trong nhưng volume chứa file vẫn hết chỗ để mở rộng một relation khác. Ngược lại, volume có dung lượng trống lớn không có nghĩa tablespace hoặc quota của database được phép sử dụng toàn bộ dung lượng đó.

### 1.1. Free space trong bảng không phải free space của ổ đĩa

Khi xóa hoặc cập nhật dữ liệu, PostgreSQL có thể tái sử dụng một số không gian trong relation sau khi VACUUM xử lý các tuple không còn cần thiết. Tuy nhiên, VACUUM thông thường chủ yếu làm không gian có thể tái sử dụng bên trong bảng; nó không nhất thiết thu nhỏ file và trả dung lượng về filesystem.

Do đó, có thể xảy ra tình huống:

- `DELETE` xóa hàng triệu dòng.
- VACUUM dọn các phiên bản tuple cũ.
- Bảng có thêm không gian trống nội bộ để các lần INSERT sau tái sử dụng.
- Kích thước file trên filesystem gần như không giảm.

`VACUUM FULL` có thể viết lại bảng và trả không gian về filesystem, nhưng cần khóa mạnh và thêm dung lượng tạm thời để tạo bản sao mới. Không chạy VACUUM FULL trên bảng lớn khi volume gần đầy mà chưa tính đủ dung lượng và thời gian chặn.

### 1.2. Một database có thể sử dụng nhiều volume

Trong triển khai thực tế, data file, WAL, temporary tablespace, backup và archive có thể nằm trên các volume khác nhau. Mỗi volume có đặc tính IOPS, throughput, latency, quota và chính sách mở rộng riêng.

Ví dụ:

```text
Volume A: data files và index
Volume B: WAL / redo log
Volume C: temporary files / sort spill
Volume D: backup và WAL archive
```

Tách volume có thể giúp cô lập I/O hoặc quản lý dung lượng, nhưng không tự động tạo thêm năng lực lưu trữ. Nếu volume B đầy, database có thể không tiếp tục ghi WAL dù volume A còn nhiều chỗ. Nếu volume C đầy, các truy vấn cần temp file có thể lỗi dù data volume vẫn còn trống.

## 2. Những thành phần tiêu thụ dung lượng

### 2.1. Data và index

Dung lượng data file tăng khi thêm dòng, mở rộng bảng, lưu giá trị lớn hoặc tạo thêm partition. Index cũng tăng theo số dòng, độ rộng khóa, số index và mức phân mảnh/bloat.

Các yếu tố làm dung lượng tăng nhanh:

- Tăng trưởng người dùng, đơn hàng, sự kiện hoặc lịch sử giao dịch.
- Lưu payload JSON, văn bản, ảnh hoặc dữ liệu nhị phân trong database.
- Tạo thêm index để phục vụ truy vấn.
- Index có khóa rộng hoặc INCLUDE nhiều cột.
- Cập nhật/xóa thường xuyên làm phát sinh phiên bản tuple và bloat nếu bảo trì không theo kịp.
- Partition mới được tạo theo ngày/tháng nhưng partition cũ không được lưu trữ hoặc xóa theo chính sách.

Không chỉ theo dõi tổng kích thước database. Hãy xếp hạng các bảng và index lớn nhất, tốc độ tăng của từng đối tượng và nhóm dữ liệu có thể lưu trữ lạnh.

### 2.2. WAL và log giao dịch

WAL tăng theo hoạt động ghi, index maintenance, bulk load, checkpoint/FPI và các thao tác bảo trì. PostgreSQL tái sử dụng hoặc recycle WAL segment khi không còn cần thiết, nhưng WAL có thể bị giữ lại bởi:

- Replication slot chưa được consumer xử lý tới vị trí mới.
- Standby chậm hoặc ngừng nhận/apply WAL.
- WAL archiving bị lỗi hoặc archive destination đầy.
- Backup hoặc quy trình phục hồi đang yêu cầu giữ lại WAL.
- Cấu hình retention hoặc replication chưa phù hợp.

`max_wal_size` là ngưỡng mục tiêu có thể kích hoạt checkpoint, không phải giới hạn cứng của dung lượng WAL. Nếu WAL bị giữ bởi slot hoặc archive, thư mục `pg_wal` vẫn có thể tăng vượt ngưỡng. Không xóa WAL segment bằng tay để giải phóng dung lượng.

Các hệ quản trị khác có cơ chế log riêng. SQL Server dùng transaction log với trạng thái reuse phụ thuộc recovery model, log backup và transaction đang hoạt động. MySQL InnoDB quản lý redo/undo và binary log theo cấu hình. Cần theo dõi đúng loại log và nguyên nhân không thể truncate/reuse của engine đang dùng.

### 2.3. Temporary files và thao tác trung gian

Sort, hash join, hash aggregate, materialization và một số thao tác truy vấn có thể cần nhiều bộ nhớ. Khi vượt ngân sách bộ nhớ, engine có thể spill dữ liệu trung gian ra đĩa.

Trong PostgreSQL, temp file có thể xuất hiện khi sort hoặc hash không vừa bộ nhớ cho phép, hoặc khi ứng dụng tạo temporary table. Một truy vấn báo cáo lớn có thể tiêu thụ hàng chục hoặc hàng trăm GB temp dù data file không tăng tương ứng.

Temp usage thường có tính đột biến. Nếu chỉ đo tổng dung lượng database mà bỏ qua temp volume, hệ thống có thể hết đĩa ngay khi một báo cáo hoặc batch job chạy.

### 2.4. Backup, archive và log ứng dụng

Backup full, incremental, snapshot, WAL archive, dump, export và log ứng dụng có thể cùng ghi vào một volume. Một backup mới có thể tạm thời cần thêm dung lượng trước khi bản cũ được dọn theo retention.

Hãy phân biệt:

- Dung lượng backup đang lưu giữ theo retention.
- Dung lượng tạm trong lúc tạo hoặc nén backup.
- WAL archive đang chờ chuyển hoặc bị lỗi.
- Bản backup được sao chép sang staging trước khi đẩy lên object storage.
- Log ứng dụng, audit log và crash dump.

Không tính dung lượng backup theo kích thước database duy nhất. Nén, deduplication, snapshot copy-on-write và retention làm thay đổi mức dùng thực tế; cần dùng số liệu từ hệ thống backup và storage.

## 3. Tăng trưởng tệp và sự kiện autogrowth

Khi một bảng, index, log hoặc tablespace cần thêm không gian, hệ quản trị hoặc filesystem phải mở rộng tệp hay cấp phát thêm vùng lưu trữ. Quá trình này có thể gây thêm công việc metadata, cấp phát extent, khởi tạo vùng mới và cạnh tranh I/O.

### 3.1. Tăng trưởng theo bước nhỏ và theo bước lớn

Nếu file tăng theo các bước rất nhỏ, hệ thống có thể phải thực hiện nhiều lần mở rộng. Mỗi lần có thể tạo độ trễ, cập nhật metadata và làm gián đoạn đường ghi trong một khoảng ngắn tùy engine/storage.

Nếu bước tăng quá lớn, hệ thống có thể cấp phát nhiều dung lượng chưa cần dùng, gây áp lực lên volume, quota hoặc thin-provisioned storage. Một lần mở rộng lớn cũng có thể kéo dài nếu phải khởi tạo hoặc zero vùng mới.

Mục tiêu là chọn cách cấp phát phù hợp với tốc độ tăng trưởng và năng lực lưu trữ:

- Cấp phát trước dung lượng dự kiến cho workload ổn định và quan trọng.
- Đặt growth increment đủ lớn để tránh mở rộng liên tục nhưng không vượt quá reserve.
- Theo dõi thời gian và latency trong các sự kiện mở rộng.
- Kiểm tra cơ chế khởi tạo file của từng hệ quản trị và hệ điều hành.
- Không để autogrowth là kế hoạch capacity duy nhất.

### 3.2. Autogrowth khác với tăng dung lượng volume

Autogrowth mở rộng file hoặc vùng lưu trữ database trong giới hạn volume/quota hiện có. Nó không tự tạo thêm dung lượng vật lý nếu volume đã đầy.

Ví dụ, database file có thể được cấu hình tăng thêm 1 GB khi cần, nhưng nếu volume chỉ còn 200 MB thì thao tác tăng 1 GB sẽ thất bại hoặc không hoàn tất. Tương tự, volume cloud có thể được mở rộng theo yêu cầu, nhưng hệ điều hành và filesystem có thể cần thao tác resize riêng trước khi database sử dụng được phần dung lượng mới.

### 3.3. Cơ chế theo hệ quản trị

| Hệ quản trị | Cơ chế thường gặp | Điểm cần kiểm tra |
|---|---|---|
| PostgreSQL | Relation và tablespace file mở rộng khi cần; WAL segment được tạo/recycle theo cơ chế riêng | Filesystem free space, tablespace placement, `pg_wal`, temp file, archive và replication slot |
| SQL Server | Database data/log file có cấu hình autogrowth theo MB hoặc phần trăm | Growth increment, max size, volume free, log reuse wait và thời gian zero/init file |
| MySQL InnoDB | System tablespace hoặc file-per-table có thể autoextend tùy cấu hình; redo/undo và binary log quản lý riêng | `innodb_data_file_path`, tablespace, redo/undo, temp, binary log và filesystem |

Tên tham số và hành vi thay đổi theo phiên bản. Không áp dụng cấu hình autogrowth của SQL Server cho PostgreSQL hoặc giả định mọi tablespace InnoDB đều mở rộng theo cùng một cách.

### 3.4. Tác động của mở rộng file tới latency

Một sự kiện tăng trưởng file có thể làm tăng latency vì:

- Hệ điều hành phải cấp phát thêm block/extent và cập nhật metadata filesystem.
- Một số cấu hình phải zero hoặc khởi tạo vùng mới trước khi dùng.
- Storage backend phải cấp phát thêm dung lượng hoặc mở rộng thin-provisioned volume.
- I/O cấp phát cạnh tranh với đọc/ghi của workload đang chạy.
- Nhiều file tăng trưởng đồng thời tạo burst I/O.

Mức tác động phụ thuộc engine, filesystem, storage và cấu hình. Một số nền tảng hỗ trợ instant file initialization cho data file trong điều kiện cụ thể; log file có thể không được hưởng cùng cơ chế. Hãy kiểm tra tài liệu nền tảng và đo thời gian growth thực tế.

## 4. Điều gì xảy ra khi volume gần đầy?

Gần đầy đĩa không chỉ là vấn đề vận hành dung lượng. Nó có thể biến thành sự cố hiệu năng hoặc tính sẵn sàng.

### 4.1. Không thể mở rộng data file

Khi bảng hoặc index cần thêm trang nhưng filesystem không cấp phát được, câu lệnh ghi có thể thất bại với lỗi hết dung lượng. Transaction có thể bị hủy; ứng dụng phải xử lý lỗi và retry theo chính sách an toàn. Nếu lỗi xuất hiện trong thao tác bảo trì, CREATE INDEX, REINDEX hoặc VACUUM FULL có thể không hoàn tất.

### 4.2. WAL hoặc transaction log không thể tiếp tục ghi

Nếu volume chứa WAL/redo/transaction log hết chỗ, hệ quản trị có thể không ghi được log cần thiết cho transaction. Điều này có thể làm commit hoặc thao tác ghi thất bại, khiến database bị ảnh hưởng nghiêm trọng hơn so với việc chỉ thiếu chỗ trên volume chứa một bảng không hoạt động.

Trong PostgreSQL, WAL cần thiết cho phục hồi và commit; nếu không thể ghi WAL, hệ thống không thể tiếp tục xử lý ghi một cách bình thường. Với SQL Server, transaction log đầy có thể khiến các thao tác cần log không thể tiếp tục cho đến khi log được backup/truncate/reuse hoặc mở rộng theo đúng nguyên nhân. Với InnoDB, redo log và binary log cũng có vai trò riêng và cần được giám sát.

### 4.3. Không đủ chỗ cho temporary operation

Một truy vấn sort/hash đang chạy có thể cần tạo temp file. Nếu temp volume đầy, truy vấn có thể lỗi giữa chừng dù data volume còn dung lượng. Nhiều truy vấn đồng thời có thể cùng tạo temp, khiến dung lượng giảm nhanh hơn tốc độ cảnh báo thông thường.

Nếu workload có truy vấn báo cáo lớn, cần dự báo temp peak theo giờ cao điểm và cân nhắc giới hạn concurrency, tối ưu truy vấn, phân vùng dữ liệu hoặc phân bổ temp tablespace riêng.

### 4.4. Bảo trì không còn đủ không gian làm việc

Các thao tác có thể cần thêm dung lượng trong lúc thực hiện:

- Tạo index mới hoặc rebuild index.
- VACUUM FULL hoặc thao tác viết lại bảng.
- ALTER TABLE cần rewrite dữ liệu.
- Sort/hash lớn trong truy vấn và materialized view refresh.
- Backup staging, restore hoặc kiểm tra backup.
- Reorganization, compaction hoặc migration dữ liệu.

Nếu volume chỉ còn vừa đủ cho file hiện tại, thao tác bảo trì có thể thất bại vì không có khoảng trống cho bản sao hoặc dữ liệu tạm. Kế hoạch capacity cần tính cả dung lượng peak trong lúc bảo trì, không chỉ dung lượng cuối cùng.

### 4.5. Hiệu năng có thể suy giảm trước khi đĩa đạt 100%

Một số storage backend có latency tăng khi gần hết dung lượng hoặc khi pool thin provisioning bị áp lực. Filesystem có thể còn vài phần trăm free nhưng không đủ reserve cho growth burst, metadata, snapshot copy-on-write hoặc các file tạm.

Ngoài dung lượng byte, còn phải theo dõi inode, quota, giới hạn file, storage pool và mức sử dụng của volume cha. Vì vậy, ngưỡng cảnh báo nên dựa trên cả phần trăm free, số byte tuyệt đối và thời gian dự báo tới ngưỡng cạn.

## 5. Dự báo dung lượng và thiết lập ngưỡng an toàn

Quản lý dung lượng hiệu quả cần trả lời hai câu hỏi:

1. Với tốc độ tăng hiện tại, còn bao lâu trước khi chạm ngưỡng an toàn?
2. Cần giữ lại bao nhiêu dung lượng cho tăng trưởng, sự cố và bảo trì?

### 5.1. Tính tốc độ tăng trưởng

Với một volume, có thể ước lượng tốc độ tăng ròng:

\[
GrowthRate = \frac{Used_{t2} - Used_{t1}}{t2 - t1}
\]

Ví dụ, dung lượng đã dùng tăng từ 1.20 TB lên 1.27 TB trong 7 ngày:

\[
GrowthRate = \frac{70\ GB}{7\ days} = 10\ GB/day
\]

Nếu volume còn 300 GB và cần giữ reserve 100 GB, thời gian ước tính trước khi chạm reserve là:

\[
Runway = \frac{300 - 100}{10} = 20\ days
\]

Đây là phép dự báo tuyến tính. Nó có thể sai nếu có mùa cao điểm, batch import, retention cleanup, index build hoặc WAL backlog. Hãy dùng nhiều cửa sổ thời gian (ví dụ 7 ngày và 30 ngày), đồng thời xem tốc độ peak thay vì chỉ dùng trung bình dài hạn.

### 5.2. Tính reserve vận hành

Reserve nên bao gồm:

- Tăng trưởng dự kiến trong thời gian đội vận hành cần để phê duyệt và mở rộng storage.
- Peak temporary usage trong truy vấn hoặc batch job.
- Dung lượng bổ sung cho index build, table rewrite, VACUUM FULL hoặc restore nếu có trong kế hoạch.
- WAL/redo/archive backlog có thể phát sinh khi replica hoặc archive chậm.
- Khoảng an toàn cho biến động tăng trưởng và sự cố.

Một mô hình lập kế hoạch đơn giản:

\[
RequiredReserve = GrowthDuringResponseWindow + PeakTransientSpace + SafetyMargin
\]

Không có một tỷ lệ free space phù hợp cho mọi hệ thống. Volume tăng 5 GB/ngày có thể cần reserve khác với volume tăng 500 GB/ngày hoặc volume có temp spike lớn. Đặt ngưỡng cảnh báo theo runway và reserve thực tế.

### 5.3. Ngưỡng cảnh báo theo runway

Thay vì chỉ cảnh báo khi free space xuống dưới 10%, có thể dùng các mức vận hành:

| Trạng thái | Điều kiện minh họa | Hành động |
|---|---|---|
| Bình thường | Runway dài hơn thời gian xử lý mở rộng cộng reserve | Tiếp tục theo dõi xu hướng |
| Cảnh báo sớm | Runway tiến gần thời gian cần để phê duyệt/cấp thêm storage | Mở yêu cầu capacity, xác định volume tăng nhanh |
| Cảnh báo cao | Free space chạm reserve hoặc runway ngắn hơn thời gian mở rộng | Dừng workload không thiết yếu, chuẩn bị mở rộng hoặc dọn dữ liệu theo chính sách |
| Khẩn cấp | Growth operation hoặc ghi dữ liệu đã thất bại; free space rất thấp | Kích hoạt runbook sự cố, bảo vệ WAL/log và ưu tiên khôi phục khả năng ghi |

Các điều kiện trên là khung tham khảo. Ngưỡng thật phải dựa trên tốc độ tăng, thời gian cấp phát storage, RTO/RPO, dung lượng peak và cơ chế mở rộng của nền tảng.

## 6. Giám sát dung lượng trong PostgreSQL

Không một view duy nhất phản ánh toàn bộ dung lượng. Cần kết hợp kích thước database/tablespace, WAL, temporary files, replication và filesystem.

### 6.1. Kích thước database

```sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(datname) DESC;
```

Truy vấn này xếp hạng kích thước database trong cluster. Nó không cho biết filesystem còn bao nhiêu chỗ, cũng không bao gồm backup nằm ngoài data directory.

### 6.2. Kích thước bảng và index

```sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid)) AS table_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 20;
```

`pg_total_relation_size` bao gồm bảng, index và TOAST liên quan; `pg_relation_size` đo relation chính được chỉ định; `pg_indexes_size` tổng kích thước index của bảng. Đây là số liệu theo relation, không phải dung lượng trống của tablespace hay filesystem.

### 6.3. Kích thước tablespace

```sql
SELECT
    spcname,
    pg_size_pretty(pg_tablespace_size(oid)) AS tablespace_size
FROM pg_tablespace
ORDER BY pg_tablespace_size(oid) DESC;
```

Kích thước tablespace cho biết tổng dung lượng relation trong tablespace. Muốn biết volume còn trống, phải đối chiếu đường dẫn tablespace với filesystem/volume ở hệ điều hành. Tablespace có thể nằm trên mount riêng.

### 6.4. Temporary file theo database

```sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_written,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
```

`temp_files` và `temp_bytes` là bộ đếm tích lũy kể từ lần reset thống kê. Để đánh giá tốc độ phát sinh temp, hãy lấy hai snapshot theo khoảng thời gian và tính delta. Chỉ số này giúp nhận diện database tạo nhiều temp file, nhưng không cho biết toàn bộ dung lượng temp đang chiếm tại thời điểm hiện tại.

### 6.5. WAL directory

Trong các phiên bản PostgreSQL có hàm `pg_ls_waldir()`, có thể kiểm tra tổng số file và dung lượng file trong thư mục WAL:

```sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)) AS wal_directory_size
FROM pg_ls_waldir();
```

Hàm này cần quyền phù hợp. Dung lượng thư mục WAL hiện tại khác với `max_wal_size` và có thể tăng do replication slot, archive hoặc standby. Khi thấy WAL lớn, kiểm tra slot và archive trước khi nghĩ đến xóa file.

### 6.6. Replication slot và WAL retention

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    CASE
        WHEN restart_lsn IS NOT NULL THEN
            pg_size_pretty(
                pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
            )
        ELSE NULL
    END AS retained_wal_estimate
FROM pg_replication_slots
ORDER BY slot_name;
```

`retained_wal_estimate` là ước lượng khoảng WAL từ vị trí hiện tại đến `restart_lsn`, không phải phép đo chính xác dung lượng file riêng của slot. Nhiều slot có thể cùng giữ các segment chồng lấp. Hãy kết hợp với dung lượng `pg_wal`, trạng thái replica, archive và chính sách `max_slot_wal_keep_size` nếu phiên bản hỗ trợ.

### 6.7. Trạng thái archiving

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
```

Nếu `failed_count` tăng hoặc `last_archived_time` quá cũ so với tốc độ WAL, kiểm tra archive command, quyền ghi, dung lượng đích và kết nối tới kho lưu trữ. Archive backlog có thể góp phần giữ WAL và làm volume WAL tăng.

### 6.8. Kiểm tra filesystem ở hệ điều hành

Trên Linux:

```bash
df -hT
df -i
```

- `df -hT` cho biết dung lượng, filesystem type và phần trăm sử dụng của từng mount.
- `df -i` cho biết inode còn lại; volume có thể hết inode dù vẫn còn byte trống.

Trên Windows PowerShell, có thể dùng:

```powershell
Get-Volume | Select-Object DriveLetter, FileSystemLabel, Size, SizeRemaining
```

Kết quả hệ điều hành là nguồn quan trọng để xác nhận free space thực tế. Trong môi trường container, Kubernetes hoặc cloud volume, cần kiểm tra thêm quota, PVC, node filesystem, thin-provisioned pool và dung lượng vật lý của storage backend.

## 7. Quản lý dung lượng tạm và các thao tác bảo trì

### 7.1. Tách temp khỏi data khi cần

PostgreSQL hỗ trợ `temp_tablespaces` để chỉ định tablespace cho temporary objects và một số temp file. Đưa temp sang volume riêng có thể cô lập dung lượng và I/O khỏi data volume, nhưng chỉ có lợi khi volume temp đủ dung lượng và năng lực I/O.

Nếu volume temp đầy, truy vấn cần spill vẫn có thể thất bại. Tách volume không thay thế việc tối ưu sort/hash, giới hạn concurrency hoặc giám sát temp peak.

### 7.2. Tính dung lượng trước khi tạo hoặc rebuild index

Tạo index trên bảng lớn có thể cần dung lượng cho index mới, dữ liệu sort tạm và WAL. `CREATE INDEX CONCURRENTLY` giảm một số mức chặn ghi trong PostgreSQL nhưng thường cần thêm công việc và thời gian; nó không phải phương án tiết kiệm dung lượng.

Trước khi tạo index:

- Ước lượng kích thước index từ dữ liệu, kiểu khóa và số dòng.
- Kiểm tra volume chứa index và temp tablespace.
- Kiểm tra WAL generation, archive throughput và replication lag.
- Đánh giá có thể bỏ index cũ sau khi xác nhận index mới hay không.
- Lập kế hoạch rollback nếu build thất bại hoặc tạo index invalid.

### 7.3. VACUUM FULL và table rewrite

VACUUM FULL viết lại bảng để thu hồi không gian về filesystem, nhưng cần khóa `ACCESS EXCLUSIVE` và thêm dung lượng trong lúc tạo bản viết lại. Các thao tác rewrite bảng hoặc migration tương tự cũng có thể cần khoảng trống đáng kể.

Không chạy thao tác này khi volume gần đầy với giả định rằng nó sẽ “giải phóng chỗ trước”. Trong quá trình thực hiện, dung lượng có thể tăng trước khi file cũ được loại bỏ. Hãy tính peak space và thời gian chặn.

### 7.4. Backup và restore

Backup có thể cần dung lượng staging lớn, nhất là khi tạo dump, nén hoặc giữ cả bản cũ và bản mới. Restore thường cần một volume đủ lớn cho database đích trước khi có thể chuyển traffic. Hãy kiểm tra dung lượng của backup destination và data destination riêng biệt.

Kiểm thử restore định kỳ để biết dung lượng, thời gian và các bước thực tế. Một file backup tồn tại không bảo đảm có đủ dung lượng để khôi phục nó.

## 8. Xử lý khi volume gần đầy

Khi free space xuống dưới reserve, cần hành động theo thứ tự giảm rủi ro.

### Bước 1 — Xác định volume và thành phần đang tăng

Ghi nhận mount/drive, free bytes, inode, quota và tốc độ tăng. Xác định data, WAL/log, temp, archive, backup hay log ứng dụng đang chiếm chỗ. Không xóa file trước khi biết chủ sở hữu và vai trò của nó.

### Bước 2 — Kiểm tra các tiến trình có thể làm dung lượng tăng đột biến

Xem bulk load, index build, VACUUM FULL, backup, restore, batch job, truy vấn spill lớn, replication lag và archive backlog. Nếu cần, tạm dừng workload không thiết yếu theo runbook.

### Bước 3 — Bảo vệ WAL và transaction log

Không xóa WAL/redo/transaction log đang được hệ quản trị quản lý. Kiểm tra replication slot, archive failure, long-running transaction và backup. Xử lý đúng nguyên nhân giữ log; thao tác xóa thủ công có thể làm mất khả năng phục hồi hoặc phá replication.

### Bước 4 — Mở rộng storage hoặc chuyển dữ liệu theo quy trình

Nếu tăng trưởng là hợp lệ và volume không còn đủ reserve, mở rộng volume/filesystem hoặc thêm tablespace theo quy trình nền tảng. Xác nhận hệ điều hành nhìn thấy dung lượng mới và database có thể sử dụng trước khi tiếp tục workload lớn.

### Bước 5 — Dọn dữ liệu chỉ theo chính sách

Có thể dọn backup hết retention, archive đã được chuyển an toàn, log ứng dụng cũ hoặc dữ liệu staging không còn cần. Phải xác nhận bản backup còn hợp lệ và retention đáp ứng yêu cầu trước khi xóa.

### Bước 6 — Khôi phục workload theo từng phần

Sau khi có reserve, tiếp tục các job đã dừng theo thứ tự ưu tiên. Theo dõi growth rate, WAL, temp, I/O và latency để tránh lặp lại tình trạng đầy đĩa.

## 9. Phân biệt thiếu dung lượng với nút thắt I/O

Volume còn trống không có nghĩa storage nhanh. Ngược lại, volume gần đầy không nhất thiết chậm nếu storage vẫn đáp ứng đủ tải, nhưng rủi ro hết chỗ tăng lên. Cần theo dõi hai chiều độc lập:

| Chiều đánh giá | Chỉ số | Câu hỏi |
|---|---|---|
| Capacity | Free bytes, free %, inode, quota, runway | Còn bao lâu trước khi chạm reserve? |
| Performance | Read/write latency, IOPS, throughput, queue depth, utilization | Thiết bị có đáp ứng workload hiện tại không? |
| Database write path | WAL bytes, checkpoint, log flush, backend writes | Ghi database đang tạo tải ở thành phần nào? |
| Temporary I/O | Temp bytes/files, spill, temp volume latency | Truy vấn nào đang tiêu thụ không gian tạm? |
| Growth events | File growth count, duration, size increment | Mở rộng file có trùng thời điểm latency spike không? |

Nếu dung lượng còn nhiều nhưng latency cao, hãy điều tra I/O saturation, queue depth, storage tier, random/sequential pattern và workload cạnh tranh. Nếu latency tăng đúng lúc file growth, cần đo thời gian growth và cách storage cấp phát block.

## 10. Quy trình lập kế hoạch capacity

**Bước 1 — Lập bản đồ lưu trữ.** Liệt kê database, tablespace, data file, index, WAL/log, temp, archive, backup và volume tương ứng. Ghi rõ quota, kích thước tối đa và cơ chế mở rộng.

**Bước 2 — Lấy baseline.** Thu thập kích thước hiện tại, free bytes, inode, file growth, temp usage, WAL retention và tốc độ tăng theo thời gian.

**Bước 3 — Phân tích thành phần tăng nhanh.** Xếp hạng bảng/index, WAL, temp, backup và log. Tìm thay đổi workload, index mới, retention không chạy hoặc replica/archive bị chậm.

**Bước 4 — Dự báo theo nhiều cửa sổ.** Tính tăng trưởng 7 ngày, 30 ngày và peak theo mùa/batch. Dự báo runway tới reserve, không chỉ tới 0% free.

**Bước 5 — Tính transient peak.** Ước lượng dung lượng bổ sung cho index build, table rewrite, backup staging, temp spill, WAL backlog và hoạt động phục hồi.

**Bước 6 — Chọn cách tăng capacity.** Cân nhắc mở rộng volume, thêm tablespace, tách temp/WAL, archive dữ liệu cũ hoặc điều chỉnh retention. Đánh giá latency và năng lực I/O của storage mới.

**Bước 7 — Lập lịch và kiểm soát growth.** Pre-size các file quan trọng khi phù hợp; đặt growth increment và max size theo reserve; tránh để nhiều file cùng autogrow vào giờ cao điểm.

**Bước 8 — Kiểm tra phục hồi và bảo trì.** Bảo đảm có dung lượng để restore, reindex, vacuum/rewrite và archive; thử quy trình thay vì chỉ dựa trên ước lượng.

**Bước 9 — Cảnh báo theo runway.** Kết hợp free %, free bytes, growth rate, thời gian mở rộng và ngưỡng reserve. Cảnh báo khi runway ngắn hơn thời gian cần để xử lý.

**Bước 10 — Đánh giá sau thay đổi.** So sánh latency, throughput, I/O, growth events, WAL/temp và chi phí storage trước/sau. Cập nhật dự báo khi workload hoặc retention thay đổi.

## 11. Những nhầm lẫn thường gặp

- **“Database còn nhiều free space nghĩa là ổ đĩa còn trống.”** Dung lượng nội bộ relation, tablespace và filesystem là các lớp khác nhau.
- **“Xóa dòng sẽ làm file nhỏ lại.”** VACUUM thường giúp tái sử dụng không gian trong relation; file không nhất thiết được thu nhỏ.
- **“Autogrowth tự giải quyết hết dung lượng.”** Autogrowth cần volume còn đủ chỗ và có thể tạo latency spike.
- **“max_wal_size giới hạn cứng thư mục WAL.”** WAL có thể vượt ngưỡng do slot, archive hoặc tải ghi; cần điều tra retention.
- **“Volume data đầy là database duy nhất bị ảnh hưởng.”** WAL, temp, archive hoặc backup volume đầy cũng có thể làm workload thất bại.
- **“Còn 5% dung lượng là luôn an toàn.”** Số byte tuyệt đối, growth rate, peak transient và thời gian mở rộng mới quyết định reserve phù hợp.
- **“Tăng volume sẽ sửa mọi vấn đề lưu trữ.”** Tăng capacity không tự tăng IOPS, throughput hoặc giảm latency.
- **“Có thể xóa file WAL cũ bằng tay.”** Không xóa file log do database quản lý; xử lý slot, archive và retention bằng cơ chế chính thức.
- **“VACUUM FULL là cách dọn đĩa khi sắp đầy.”** Nó cần thêm dung lượng và khóa mạnh trong quá trình rewrite.
- **“Backup đã có thì restore chắc chắn được.”** Restore cần đủ dung lượng đích, staging và WAL liên quan.
- **“Chỉ cần xem free percentage.”** Cần xem byte tuyệt đối, inode, quota, thin provisioning và runway.

## 12. Checklist quản lý dung lượng và tăng trưởng

- [ ] Đã lập bản đồ data, index, WAL/log, temp, archive, backup và volume tương ứng.
- [ ] Đã phân biệt free space của filesystem với không gian có thể tái sử dụng trong bảng.
- [ ] Đã theo dõi free bytes, free %, inode, quota và storage pool.
- [ ] Đã đo growth rate theo nhiều cửa sổ và dự báo runway tới reserve.
- [ ] Đã tính dung lượng transient cho index build, table rewrite, temp spill, backup và restore.
- [ ] Đã kiểm tra autogrowth increment, max size, thời gian growth và cơ chế khởi tạo file.
- [ ] Đã theo dõi WAL/redo retention, replication slot, archive backlog và transaction dài.
- [ ] Đã theo dõi temp files/bytes và truy vấn có sort/hash spill lớn.
- [ ] Đã xác định chính sách retention cho data, backup, archive và application logs.
- [ ] Đã chuẩn bị dung lượng và runbook cho bảo trì, mở rộng và phục hồi.
- [ ] Đã đặt cảnh báo theo runway và reserve, không chỉ theo phần trăm free.
- [ ] Đã kiểm chứng hiệu năng storage và database sau khi mở rộng hoặc thay đổi cấu hình.

## Kết luận

Dung lượng trống cần được quản lý ở cấp volume, filesystem, tablespace, data/index, WAL/log và temporary storage. Tăng trưởng file có thể tạo thêm công việc cấp phát và I/O; khi volume gần đầy, database có thể không mở rộng được data file, ghi log, tạo temp file hoặc hoàn tất thao tác bảo trì. Một hệ thống cần reserve cho tăng trưởng bình thường lẫn nhu cầu tạm thời khi backup, index build, table rewrite và phục hồi.

Hãy đo tốc độ tăng, dự báo runway tới ngưỡng an toàn, theo dõi các thành phần đang giữ WAL và temp, rồi lập kế hoạch mở rộng trước khi thiếu chỗ. Phân biệt capacity với hiệu năng I/O: thêm dung lượng không tự làm storage nhanh hơn. Mọi thay đổi cần được xác nhận bằng latency, throughput, I/O, mức tăng trưởng và khả năng restore dưới điều kiện tải đại diện.
