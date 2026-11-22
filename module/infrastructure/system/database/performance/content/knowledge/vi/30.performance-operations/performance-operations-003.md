# Dự báo dung lượng, tăng trưởng dữ liệu và giới hạn kết nối

Dung lượng cơ sở dữ liệu và số kết nối thường tăng dần theo số người dùng, giao dịch, lịch sử nghiệp vụ và các dịch vụ tích hợp. Nếu chỉ nhìn dung lượng còn trống hoặc số session hiện tại, đội vận hành có thể phát hiện quá muộn rằng volume sắp đầy, transaction log không thể tái sử dụng, connection pool xếp hàng hoặc DBMS đã chạm giới hạn session/worker. Khi đó, việc tăng tài nguyên gấp có thể tốn kém, gây gián đoạn và vẫn không xử lý được nút thắt thật sự.

Dự báo dung lượng và giới hạn kết nối cần dựa trên xu hướng đo được, mô hình tăng trưởng của dữ liệu, chính sách lưu giữ, workload và capacity của DBMS. Dung lượng phải tính cả data, index, transaction log, temporary space, backup và vùng trống cho maintenance. Kết nối phải tính theo số request đồng thời và thời gian giữ connection, tổng pool trên tất cả instance ứng dụng, cùng tài nguyên mà mỗi session tiêu thụ.

Trong chương **Vận hành hiệu năng**, bài học này trình bày cách dự báo dung lượng, tăng trưởng dữ liệu và giới hạn kết nối. Nội dung gắn với mục tiêu của module **DATABASE_PERFORMANCE**: rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Ta sẽ xây dựng baseline, ước lượng tốc độ tăng data/index/log, tính time-to-exhaustion, xác định headroom và retention, rồi lập ngân sách connection cho ứng dụng, pool, proxy và DBMS. Các quyết định được kiểm chứng bằng kịch bản tăng trưởng và tải đỉnh.

Một capacity plan hữu ích phải trả lời được: thành phần nào tăng nhanh nhất, còn bao lâu trước khi chạm ngưỡng, cần bao nhiêu headroom cho peak và maintenance, số connection nào DBMS có thể phục vụ an toàn, và thời điểm nào phải mở rộng hoặc thay đổi workload.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt dung lượng logic, dung lượng đã cấp phát, dung lượng sử dụng và dung lượng còn có thể mở rộng.
- Ước lượng tăng trưởng data, index, transaction log, temporary space và backup.
- Tính tốc độ tăng trưởng, thời gian đến ngưỡng đầy và nhu cầu capacity theo nhiều kịch bản.
- Đánh giá tác động của retention, archive, partition và replication tới dung lượng.
- Xác định headroom cho peak load, maintenance, backup, recovery và tăng trưởng bất thường.
- Phân biệt connection, session, request đang chạy, connection idle và worker.
- Ước lượng nhu cầu connection từ arrival rate và thời gian giữ connection.
- Tính tổng ngân sách pool khi ứng dụng có nhiều replica/service.
- Hiểu giới hạn connection/session/worker/memory của PostgreSQL, MySQL, SQL Server và Oracle.
- Chọn pool, proxy, queue và admission control để giữ concurrency trong capacity.
- Theo dõi xu hướng, cảnh báo time-to-exhaustion và kiểm chứng capacity plan.

## 1. Capacity của database gồm những gì?

### 1.1. Dung lượng logic và dung lượng vật lý

Cần phân biệt các khái niệm sau:

- **Logical data size:** lượng dữ liệu nghiệp vụ theo cách đo của DBMS hoặc ứng dụng, ví dụ số dòng và kích thước payload.
- **Allocated size:** dung lượng file/tablespace/volume mà DBMS đã cấp phát.
- **Used space:** phần không gian đang được page, segment, extent hoặc file sử dụng.
- **Free space inside files:** vùng trống còn có thể dùng trong các file đã cấp phát.
- **Filesystem/cloud volume free space:** dung lượng còn trống trên volume bên dưới.
- **Maximum provisioned capacity:** giới hạn tối đa mà storage service hoặc nền tảng cho phép mở rộng.

Các con số này không đồng nghĩa. Database file có thể đã cấp phát 2 TB nhưng chỉ chứa 1,4 TB dữ liệu đang dùng; filesystem vẫn có thể còn trống 500 GB. Ngược lại, DBMS có thể còn vùng trống nội bộ nhưng volume bên dưới đã gần đầy và không thể mở rộng file.

### 1.2. Các thành phần cần đưa vào dự báo

Capacity plan cần tính riêng:

| Thành phần | Nội dung |
|---|---|
| Data tables | Dữ liệu nghiệp vụ, row versions và page overhead |
| Indexes | B-tree, secondary, unique, partial hoặc expression indexes |
| Transaction log | WAL, redo log, binary/transaction log tùy DBMS |
| Temporary space | Sort, hash spill, temp tables, workfiles và temporary tablespaces |
| System/catalog | Metadata, system tables và internal structures |
| Backup | Full, incremental, differential, archive và staging |
| Replication | Log retention, replica backlog và bản sao dữ liệu |
| Maintenance headroom | Rebuild index, vacuum, compaction, reorganization và migration |
| Operational reserve | File growth, burst, recovery và sự cố kéo dài |

Không cộng đơn giản mọi thành phần nếu chúng nằm trên các volume khác nhau. Hãy lập capacity theo từng filesystem, volume, tablespace hoặc storage tier vì bottleneck có thể xuất hiện ở một volume riêng lẻ.

### 1.3. Dung lượng không phải hiệu năng

Volume còn nhiều chỗ trống không chứng minh I/O đủ nhanh. Ngược lại, IOPS và throughput cao không giúp hệ thống nếu log hoặc temp volume hết dung lượng.

Theo dõi riêng:
- Capacity và tốc độ tăng.
- IOPS, throughput, latency và queue depth.
- Data/log/temp allocation.
- Tỷ lệ sử dụng và khả năng autoextend.
- Giới hạn quota và mức provisioned.

Capacity planning trả lời “khi nào hết chỗ”; performance monitoring trả lời “đường đọc/ghi có đáp ứng tải không”. Hai việc cần phối hợp nhưng không thay thế nhau.

## 2. Đo tốc độ tăng trưởng dữ liệu

### 2.1. Bắt đầu từ dữ liệu thực tế

Thu lịch sử theo ngày hoặc tuần:
- Số dòng mới, cập nhật và xóa.
- Kích thước table và index.
- Dung lượng file/tablespace.
- Log bytes được tạo.
- Temporary space peak.
- Backup size và thời gian lưu backup.
- Replica lag và log retention.
- Số partition và kích thước mỗi partition.

Nên đo trên nhiều chu kỳ nghiệp vụ để bao gồm ngày cao điểm, cuối tháng, mùa vụ và batch lớn. Một ngày bình thường có thể không đại diện cho ngày chốt sổ hoặc chiến dịch bán hàng.

### 2.2. Ước lượng từ số dòng và kích thước trung bình

Mô hình đơn giản cho bảng tăng thêm:

~~~text
Data growth per period
  = New rows per period × Average stored bytes per row
~~~

Kích thước trung bình phải tính theo cách lưu trữ thực tế, bao gồm row/page overhead, alignment, compression và các cột variable-length nếu có. Không lấy độ dài JSON trung bình từ API rồi coi đó là kích thước vật lý của row.

Ví dụ minh họa: một bảng thêm 2 triệu dòng/ngày, kích thước lưu trữ trung bình 700 byte/dòng:

~~~text
2,000,000 × 700 bytes = 1.4 GB/day (xấp xỉ)
~~~

Đây mới là ước lượng data table. Index, log, free space, compression và overhead có thể làm dung lượng thực tế khác đáng kể.

### 2.3. Ước lượng từ xu hướng đo được

Nếu đã có số liệu theo thời gian, có thể dùng tốc độ tăng trung bình:

~~~text
Average growth rate
  = (Current size - Previous size) / Elapsed time
~~~

Với dữ liệu có mùa vụ, tính riêng tốc độ theo ngày trong tuần, tháng, mùa chiến dịch hoặc nhóm nghiệp vụ. Dùng moving average hoặc percentile của tốc độ tăng thay vì chỉ một trung bình dài hạn.

Nếu tăng trưởng có xu hướng tăng theo thời gian, mô hình tuyến tính có thể đánh giá thấp nhu cầu. Hãy so sánh:
- Linear growth: số bytes/ngày gần ổn định.
- Percentage growth: dữ liệu tăng theo tỷ lệ trên quy mô hiện tại.
- Step change: tăng đột biến sau khi onboard tenant, import hoặc thay đổi retention.
- Seasonal growth: tăng theo chu kỳ nghiệp vụ.

Không ngoại suy một vài ngày dữ liệu thành dự báo nhiều năm nếu mô hình kinh doanh có thể thay đổi.

### 2.4. Dự báo theo từng bảng và partition

Tổng database growth có thể che giấu bảng nào đang tăng nhanh. Phân rã theo:
- Bảng giao dịch nóng.
- Bảng lịch sử/audit.
- Bảng log nghiệp vụ.
- Bảng staging/ETL.
- Bảng reference tương đối ổn định.
- Partition theo ngày/tháng/tenant.

Cách này giúp đặt retention khác nhau và dự báo chính xác hơn. Một bảng audit có thể tăng nhanh hơn bảng nghiệp vụ chính dù ít truy vấn đọc.

### 2.5. Phân biệt update với growth vật lý

UPDATE không nhất thiết chỉ thay thế bytes cũ tại chỗ. Tùy DBMS và storage engine, update có thể tạo row version mới, page split, dead tuples hoặc log records. Delete cũng có thể chưa giải phóng ngay dung lượng file cho filesystem.

Vì vậy, số dòng không đổi không có nghĩa dung lượng không tăng. Theo dõi cả:
- Logical row count.
- Table/index allocated pages.
- Bloat hoặc fragmentation indicators theo DBMS.
- Dead row versions và vacuum/purge progress.
- Log bytes generated.
- Reusable space bên trong file so với space trả lại OS.

## 3. Dự báo index, log và temporary space

### 3.1. Index growth

Mỗi index lưu thêm key, row locator/primary key và cấu trúc page. Index growth phụ thuộc:
- Số dòng được thêm.
- Số index trên bảng.
- Độ rộng key và included columns.
- Tính duy nhất và phân bố key.
- Page fill, split và fragmentation.
- Compression và DBMS implementation.

Một thay đổi schema thêm index có thể tăng đáng kể storage và write amplification. Khi dự báo, đo index size theo từng index quan trọng, không dùng một tỷ lệ cố định cho mọi bảng.

### 3.2. Transaction log growth

Log volume phụ thuộc số thao tác ghi, loại dữ liệu thay đổi, index maintenance, transaction size, replication, backup/archive và cơ chế recovery.

Theo dõi:
- Log bytes/s và bytes/ngày.
- Log file allocated/used.
- Log backup hoặc archive rate.
- Long-running transactions.
- Replication slots/replica lag hoặc log shipping backlog.
- Checkpoint và log truncation/reuse.
- Peak log usage trong bulk load, index rebuild và migration.

Một database có data growth thấp vẫn có thể tạo log rất lớn nếu update/delete hàng loạt hoặc rebuild index thường xuyên.

### 3.3. Log retention và log không tái sử dụng

Transaction log có thể không được truncate/reuse khi:
- Có backup/archive chưa hoàn tất.
- Replica hoặc consumer chưa nhận log.
- Replication slot giữ WAL.
- Transaction lâu chưa kết thúc.
- Recovery/checkpoint chưa tiến đủ.
- Log shipping hoặc CDC consumer bị chậm.

Cơ chế cụ thể khác nhau theo DBMS. Khi log tăng bất thường, tìm lý do giữ log thay vì chỉ tăng file. Tăng dung lượng có thể giúp có thời gian xử lý, nhưng không loại bỏ nguyên nhân retention.

### 3.4. Temporary space

Sort, hash join, hash aggregate, materialization và temporary table có thể dùng temp space. Peak temp usage phụ thuộc query plan, memory grant, concurrency và kích thước dữ liệu.

Đo:
- Peak temp bytes theo workload.
- Spill count/bytes.
- Temp tablespace hoặc tempdb growth.
- Concurrent heavy queries.
- Dung lượng tạm trong batch, index build và maintenance.

Không dự báo temp chỉ theo data size. Một query có thể tạo dữ liệu trung gian lớn hơn nhiều so với kết quả cuối.

### 3.5. Backup và bản sao

Backup capacity phụ thuộc retention, compression, incremental chain, differential change rate, full backup cadence và thời gian lưu archive. Không giả định backup luôn bằng một tỷ lệ cố định của database.

Cần tính:
- Full backup size và frequency.
- Incremental/differential change rate.
- WAL/redo/archive log retention.
- Backup staging và restore workspace.
- Replica storage và snapshot retention.
- Thời gian giữ bản backup theo yêu cầu phục hồi.

Backup nằm trên cùng volume với data có thể cạnh tranh I/O và dung lượng. Tách storage có thể giảm tranh chấp nếu backend thực sự độc lập.

## 4. Retention, archive và lifecycle dữ liệu

### 4.1. Retention là đầu vào của capacity plan

Retention xác định dữ liệu nào còn phải nằm trong database hoạt động. Ví dụ:
- Giao dịch hiện tại giữ online 24 tháng.
- Audit giữ online 12 tháng, sau đó chuyển archive.
- Session/temporary business state chỉ giữ 30 ngày.
- Dữ liệu báo cáo tổng hợp giữ lâu hơn dữ liệu chi tiết.

Đây là ví dụ chính sách, không phải mặc định. Retention phải theo yêu cầu nghiệp vụ, pháp lý, audit, bảo mật và khả năng phục hồi của tổ chức.

### 4.2. Dự báo với retention cố định

Nếu dữ liệu mới mỗi ngày gần ổn định và chỉ giữ online R ngày, dung lượng dữ liệu hoạt động có thể tiến tới mức gần:

~~~text
Online rows ≈ Daily new rows × Retention days
~~~

Nếu tốc độ tăng thay đổi theo mùa vụ, dùng lịch sử theo chu kỳ và dự báo đỉnh. Retention chỉ giới hạn data nếu quá trình archive/purge thực sự hoàn thành và không bị giữ lại bởi transaction, replication hoặc backup requirements.

### 4.3. Partition giúp lifecycle rõ ràng hơn

Partition theo thời gian hoặc key có thể hỗ trợ:
- Xác định dung lượng theo kỳ.
- Archive/detach/drop dữ liệu cũ.
- Rebuild hoặc maintain từng partition.
- Giảm phạm vi scan khi query có predicate phù hợp.

Partition không tự giảm dung lượng. Nếu không có quy trình detach/drop/archive, tổng dữ liệu vẫn tăng. Cần kiểm tra global indexes, foreign keys, constraints và semantics khi xóa partition tùy DBMS.

### 4.4. Archive và truy vấn dữ liệu cũ

Chuyển dữ liệu sang archive có thể giảm footprint của primary database nhưng tạo yêu cầu mới:
- Archive storage và retention.
- Cơ chế tra cứu dữ liệu lịch sử.
- Khả năng khôi phục về online.
- Consistency giữa online và archive.
- Chi phí network và query.
- Chính sách mã hóa, access control và deletion.

Không archive dữ liệu chỉ để giảm dung lượng nếu ứng dụng vẫn cần truy vấn tức thời với SLA như dữ liệu online.

### 4.5. Xóa dữ liệu không đồng nghĩa trả dung lượng cho hệ điều hành

DELETE thường đánh dấu hoặc tạo phiên bản mới tùy engine; file có thể giữ nguyên kích thước và tái sử dụng không gian nội bộ. VACUUM, purge, shrink, compaction hoặc rebuild có semantics khác nhau và có thể gây I/O/locking.

Hãy phân biệt:
- Giảm số dòng logic.
- Tăng free space bên trong database file.
- Giảm allocated file size.
- Trả bytes về filesystem/cloud volume.

Chọn thao tác theo mục tiêu và đo ảnh hưởng lên workload.

## 5. Tính time-to-exhaustion và headroom

### 5.1. Tốc độ tăng và thời gian đến ngưỡng

Với growth rate gần ổn định:

~~~text
Time to threshold
  = (Usable capacity - Current usage) / Growth rate
~~~

Ví dụ minh họa: volume có 2 TB capacity, hiện dùng 1,4 TB và tăng trung bình 20 GB/ngày. Nếu toàn bộ 600 GB còn lại đều dùng được, thời gian đến đầy lý thuyết là 30 ngày. Thực tế cần trừ headroom, maintenance space và giới hạn autoextend.

### 5.2. Dùng usable capacity thay vì tổng capacity

Không nên dùng toàn bộ dung lượng volume làm ngân sách database. Trừ:
- Free space bắt buộc cho OS và service khác.
- Headroom cho datafile growth.
- Temp và log peak.
- Index rebuild hoặc migration workspace.
- Backup staging nếu cùng volume.
- Reserve cho sự cố hoặc burst.

Ví dụ:

~~~text
Usable DB capacity
  = Provisioned capacity
  - Operational reserve
  - Maintenance reserve
  - Other workloads
~~~

Nếu data, log và temp nằm trên volume riêng, tính riêng cho từng volume. Một volume log đầy có thể làm write workload dừng dù data volume còn nhiều chỗ.

### 5.3. Headroom theo workload

Headroom cần đủ cho:
- Peak insert/update rate.
- Checkpoint và log burst.
- Bulk load/ETL.
- Index rebuild hoặc online maintenance.
- Backup/restore.
- Replica lag hoặc log retention.
- Tăng trưởng bất thường và thời gian xử lý sự cố.

Không có một tỷ lệ headroom đúng cho mọi DBMS. Dựa trên lịch sử peak, thời gian cần để mở rộng storage, thời gian procurement và SLA.

### 5.4. Ba kịch bản dự báo

Lập tối thiểu ba kịch bản:

| Kịch bản | Giả định | Mục đích |
|---|---|---|
| Base | Tăng trưởng gần mức quan sát trung bình | Ngân sách vận hành thông thường |
| High | Tăng trưởng gần peak hoặc percentile cao | Chuẩn bị mùa vụ và campaign |
| Stress | Onboard tenant lớn, import, retention thay đổi hoặc replica chậm | Kiểm tra khả năng chịu sự kiện bất thường |

Ghi rõ giả định của từng kịch bản và thời gian dự báo. Nếu business plan dự kiến tăng gấp đôi số khách hàng, đưa yếu tố đó vào mô hình thay vì ngoại suy lịch sử đơn thuần.

### 5.5. Khi nào cần hành động?

Đặt ngưỡng theo lead time:
- Thời gian đặt/mở rộng storage.
- Thời gian chạy migration.
- Thời gian kiểm thử và phê duyệt.
- Khả năng autoextend và quota.
- Thời gian khắc phục log retention hoặc archive backlog.

Cảnh báo nên kích hoạt trước khi time-to-exhaustion ngắn hơn tổng lead time cộng safety margin. Một cảnh báo ở mức 95% capacity có thể quá muộn nếu việc mở rộng cần nhiều ngày.

## 6. Ví dụ dự báo data growth

Giả sử hệ thống có:
- 4 triệu đơn hàng mới mỗi ngày.
- Dữ liệu trung bình đo được của bảng orders là 600 byte/dòng.
- Index hiện tại có kích thước bằng khoảng 45% kích thước table trong môi trường đo.
- Tăng trưởng log trung bình 18 GB/ngày.
- Retention online 730 ngày.

Ước lượng data table mỗi ngày:

~~~text
4,000,000 × 600 bytes = 2.4 GB/day (xấp xỉ)
~~~

Dung lượng table lý thuyết sau 730 ngày, nếu tốc độ không đổi:

~~~text
2.4 GB/day × 730 days = 1,752 GB
~~~

Ước lượng index theo tỷ lệ quan sát 45%:

~~~text
1,752 GB × 45% = 788.4 GB
~~~

Đây chỉ là mô hình ban đầu. Cần bổ sung các bảng liên quan, row version/bloat, thay đổi index, log retention, temp peak, backup và headroom. Tỷ lệ index 45% lấy từ số liệu môi trường cụ thể, không phải quy tắc chung.

Nếu tăng trưởng đơn hàng tăng 20% theo năm hoặc có mùa vụ, cần mô hình theo từng giai đoạn. Nếu archive/purge không chạy đúng lịch, online footprint có thể vượt mức dự báo dù retention policy đã đặt.

## 7. Connection, session và concurrency là gì?

### 7.1. Phân biệt các khái niệm

- **Connection:** kênh giao tiếp client-server, thường dựa trên TCP hoặc cơ chế transport khác.
- **Session:** ngữ cảnh làm việc phía DBMS, có trạng thái như transaction, settings, temporary objects hoặc security context.
- **Request/query:** một thao tác được gửi qua connection.
- **Active session:** session đang thực thi hoặc chờ một tài nguyên.
- **Idle session:** session đã kết nối nhưng hiện không chạy request.
- **Worker/thread/process:** đơn vị thực thi nội bộ mà DBMS dùng để xử lý session hoặc query.

Một connection không nhất thiết tương ứng một worker đang tiêu thụ CPU liên tục. Nhưng session có thể giữ memory, state, locks, transaction snapshot và tài nguyên khác ngay cả khi idle hoặc đang chờ.

### 7.2. Active, idle và idle-in-transaction

Cần phân biệt:
- Idle: connection sẵn sàng nhưng không có request.
- Active: query đang thực thi hoặc chờ.
- Idle in transaction: transaction đã mở nhưng session đang không gửi lệnh tiếp theo.

Idle-in-transaction có thể giữ locks, snapshot hoặc ngăn cleanup/version cleanup, tùy DBMS và isolation. Một session idle đơn thuần thường ít tốn tài nguyên hơn, nhưng hàng nghìn session idle vẫn có overhead.

### 7.3. Số người dùng không bằng số connection cần thiết

Một hệ thống có 20.000 người dùng không nhất thiết cần 20.000 DB connections. Người dùng có thể không hoạt động cùng lúc; application server multiplex request qua pool. Ngược lại, một dịch vụ nội bộ với vài trăm client có thể tạo quá nhiều connection nếu mỗi worker thread mở một connection riêng.

Hãy dựa trên arrival rate, thời gian giữ connection, concurrency và SLA thay vì tổng số tài khoản người dùng.

## 8. Ước lượng nhu cầu connection

### 8.1. Little's Law

Trong trạng thái ổn định, Little's Law cho quan hệ:

~~~text
Average concurrent work
  = Arrival rate × Average time in system
~~~

Với DB connection, có thể dùng làm ước lượng ban đầu:

~~~text
Average busy connections
  ≈ Requests per second × Average connection hold time (seconds)
~~~

Ví dụ ứng dụng gửi 800 request DB/giây, mỗi request giữ connection trung bình 25 ms:

~~~text
800 × 0.025 = 20 busy connections (trung bình)
~~~

Con số 20 là nhu cầu trung bình theo giả định. Nó không phải pool size tối đa. Peak arrival rate, tail duration, transaction concurrency, burst và headroom có thể đòi hỏi nhiều hơn; ngược lại, query pipelining hoặc batch có thể thay đổi số request trên mỗi connection.

### 8.2. Thời gian giữ connection quan trọng hơn query execution đơn lẻ

Một connection có thể được giữ từ lúc lấy khỏi pool đến khi trả lại. Khoảng này có thể bao gồm:
- Thực thi nhiều SQL statements.
- Đọc toàn bộ result set.
- Mapping dữ liệu ở ứng dụng.
- Chờ lock hoặc network.
- Xử lý logic trong transaction.
- Gọi dịch vụ ngoài khi transaction chưa đóng.

Nếu query DB chỉ mất 5 ms nhưng ứng dụng giữ connection 200 ms để xử lý result hoặc gọi HTTP, pool demand cao hơn nhiều so với suy luận từ DB execution time. Rút ngắn connection hold time có thể giảm số connection cần thiết mà không cần tăng DB limit.

### 8.3. Peak và percentile

Dùng average để ước lượng tải nền; dùng peak/percentile để thiết kế capacity. Đo:
- Concurrent active connections theo thời gian.
- Connection acquisition wait p95/p99.
- Request arrival rate theo giây.
- Connection hold time distribution.
- Transaction duration.
- Burst và số request retry.

Không lấy peak một giây bất thường làm pool size vĩnh viễn nếu có thể hấp thụ burst bằng queue. Nhưng cũng không bỏ qua peak lặp lại vào giờ cao điểm.

### 8.4. Từ request rate đến connection demand

Nếu một API request tạo nhiều DB round trips nhưng giữ cùng connection, connection demand phụ thuộc thời gian giữ connection, không chỉ số statement. Nếu mỗi request mở nhiều connection song song, cần tính số connection trên mỗi API request.

Hãy vẽ luồng:
- API request rate.
- Số DB operations/request.
- Số connection/request.
- Connection hold duration.
- Tỷ lệ transaction/readonly.
- Pool queue và DB session count.

## 9. Ngân sách connection trên toàn hệ thống

### 9.1. Cộng tất cả application replicas

Một lỗi phổ biến là cấu hình pool max=50 trong từng instance nhưng quên ứng dụng có 20 replicas. Tổng khả năng mở connection có thể lên tới 1.000, chưa kể background jobs, admin tools, ETL, monitoring và replicas khác.

Công thức ngân sách:

~~~text
Potential application connections
  = Sum(max pool size of every application instance)
~~~

Ví dụ:
- 12 API replicas × pool max 30 = 360.
- 4 worker replicas × pool max 20 = 80.
- 2 reporting services × pool max 15 = 30.
- Tổng pool potential = 470 connections.

DBMS còn cần chỗ cho admin, monitoring, migration, replication và các dịch vụ khác. Không đặt tổng pool potential bằng đúng max connections của DBMS.

### 9.2. Dành reserved capacity

Ngân sách DB connections nên có các nhóm:
- API/OLTP pools.
- Background workers.
- Reporting/analytics.
- ETL/maintenance.
- Replication/CDC và internal service.
- Monitoring.
- Admin/break-glass access.
- Reserve cho failover hoặc tăng tải.

Một kết nối quản trị dự phòng có thể rất quan trọng khi pool ứng dụng chiếm gần hết giới hạn. Cách reserve phụ thuộc DBMS; một số hệ thống hỗ trợ reserved slots hoặc quyền đặc biệt.

### 9.3. Pool max và pool min

- **Maximum pool size:** giới hạn connection tối đa mà pool có thể tạo.
- **Minimum idle/size:** số connection giữ sẵn hoặc duy trì tối thiểu tùy pool.
- **Acquisition timeout:** thời gian chờ mượn connection.
- **Idle timeout:** thời gian đóng connection nhàn rỗi.
- **Max lifetime:** tuổi tối đa trước khi pool tái tạo connection.
- **Leak detection:** phát hiện connection không được trả về.

Pool min quá lớn nhân lên trên nhiều replicas có thể tạo hàng trăm session idle sau khi deploy. Pool max quá lớn có thể làm DBMS bão hòa khi mọi instance đồng thời tăng tải.

### 9.4. Pool size cần gắn với DB capacity

Pool không nên được chọn bằng số thread web hoặc số CPU một cách máy móc. Hãy benchmark DBMS với nhiều mức active connections để tìm vùng throughput ổn định và tail latency chấp nhận được.

Nếu tăng active connections nhưng throughput không tăng và latency/queueing tăng, DBMS đã đạt điểm bão hòa. Khi đó, giảm concurrency hoặc queue ở tầng ứng dụng có thể tốt hơn mở rộng pool.

## 10. Giới hạn connection và session trong DBMS

### 10.1. Các giới hạn khác nhau

DBMS có thể có nhiều giới hạn độc lập:
- Maximum client connections.
- Maximum sessions.
- Worker/thread/process capacity.
- Memory per connection/session.
- File descriptors/sockets.
- Query execution workers.
- Lock table hoặc internal metadata capacity.
- Licensing hoặc service tier limits.
- Connection limits ở proxy/load balancer.

Đạt một giới hạn có thể biểu hiện thành lỗi từ chối kết nối, session wait, worker starvation, memory pressure hoặc latency tăng. Tăng max connections không nhất thiết tăng khả năng xử lý.

### 10.2. PostgreSQL

PostgreSQL dùng backend process cho connection thông thường. Mỗi backend có overhead bộ nhớ và tài nguyên riêng; work_mem có thể được dùng bởi nhiều operator trong nhiều query và worker.

Các tham số liên quan:
- **max_connections:** giới hạn connection thông thường.
- **superuser_reserved_connections** hoặc cơ chế reserved connection phù hợp phiên bản.
- **work_mem:** bộ nhớ cho một số operation, có thể nhân theo operator/worker/session.
- **max_worker_processes, max_parallel_workers** và giới hạn parallel workers.
- **shared_buffers:** vùng shared buffer cache.

Ví dụ xem session:

~~~sql
SELECT state, count(*)
FROM pg_stat_activity
GROUP BY state
ORDER BY count(*) DESC;
~~~

Và xem tổng connection:

~~~sql
SELECT count(*) AS total_connections
FROM pg_stat_activity;
~~~

Tăng max_connections làm tăng tài nguyên cần chuẩn bị và không phải cách giải quyết mặc định cho pool wait. Với nhiều ứng dụng, PgBouncer hoặc pooler tương đương có thể giảm số backend connections. Transaction pooling có giới hạn với session state, temporary tables, prepared statements và session-level settings; kiểm tra compatibility trước khi dùng.

### 10.3. MySQL/InnoDB

MySQL có giới hạn max_connections; số connection thực tế còn chịu ảnh hưởng thread model, memory buffers, thread cache/pool và tài nguyên hệ điều hành.

Các điểm cần theo dõi:
- Threads_connected và Threads_running.
- Connection errors/aborted connections.
- Thread cache usage.
- Per-session buffers và memory.
- max_connections.
- Thread pool nếu edition/plugin hỗ trợ và được cấu hình.

Ví dụ:

~~~sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW VARIABLES LIKE 'max_connections';
~~~

Tăng max_connections có thể làm memory pressure tăng vì một số buffer được cấp theo session hoặc operation. Thread pool có thể giới hạn số thread hoạt động nhưng không làm mọi session biến mất; kiểm tra behavior theo phiên bản và distribution.

### 10.4. SQL Server

SQL Server quản lý connection, session và worker thread theo cơ chế riêng. Không nên coi max worker threads là cùng một khái niệm với số connection tối đa. Một số request có thể cần nhiều worker khi parallel; worker exhaustion có thể xảy ra dù số connection chưa chạm giới hạn mà ứng dụng dự kiến.

Theo dõi:
- Sessions và requests.
- Worker threads và runnable tasks.
- Thread pool waits như THREADPOOL khi phù hợp.
- Connection pool ở client.
- Resource Governor và workload groups nếu sử dụng.

Ví dụ xem session/request đang hoạt động:

~~~sql
SELECT
    COUNT(*) AS session_count
FROM sys.dm_exec_sessions
WHERE is_user_process = 1;

SELECT
    COUNT(*) AS request_count
FROM sys.dm_exec_requests;
~~~

Các DMV cần quyền phù hợp. Giới hạn worker và connection cần được xem cùng DOP, CPU và workload.

### 10.5. Oracle

Oracle phân biệt sessions, processes và dedicated/shared server architecture. Các tham số như SESSIONS, PROCESSES và giới hạn service/resource có vai trò khác nhau. Một session không nhất thiết luôn tương ứng một dedicated server process nếu dùng shared server.

Theo dõi:
- Session count và trạng thái.
- Process count.
- Service-level limits.
- Resource Manager consumer groups.
- Dedicated/shared server usage.
- Connection pool tại application tier.

Ví dụ xem session theo trạng thái:

~~~sql
SELECT status, COUNT(*)
FROM v$session
GROUP BY status;
~~~

Quyền xem dynamic performance views phụ thuộc cấu hình. Khi tăng session/process limit, phải tính memory, process overhead và OS limits.

### 10.6. Kiểm tra đúng phiên bản và service tier

Các giới hạn và metric thay đổi theo DBMS version, edition, cloud service tier và cấu hình. Đọc tài liệu đúng phiên bản và đo trên instance thực tế. Không sao chép con số max_connections từ một môi trường khác rồi coi đó là capacity an toàn.

## 11. Connection pool, proxy và admission control

### 11.1. Pooling giúp tái sử dụng và giới hạn concurrency

Connection pool:
- Tránh lặp TCP/TLS/authentication setup.
- Giới hạn số session backend.
- Cho request mượn connection trong thời gian cần thiết.
- Tạo queue ở application tier khi pool hết connection.

Pool queue là cơ chế bảo vệ nếu được cấu hình đúng. Acquisition timeout và queue limit phải phù hợp SLA; queue không giới hạn có thể giữ quá nhiều request chờ và gây memory/thread exhaustion ở ứng dụng.

### 11.2. Proxy/pooler ở giữa

Proxy có thể gom nhiều client connections thành ít DB backend connections hơn, hỗ trợ routing, failover và quản lý connection. Tuy nhiên, proxy thêm hop, queue và một điểm cần capacity planning.

Khi dùng proxy, đo riêng:
- Client-to-proxy connections.
- Proxy-to-DB backend connections.
- Queue wait ở proxy.
- Backend pool utilization.
- Failover/reconnect behavior.
- Session affinity và transaction semantics.

### 11.3. Session pooling và transaction pooling

Session pooling giữ backend connection cho một client session trong thời gian dài. Transaction pooling có thể trả backend connection về pool sau mỗi transaction, tăng khả năng multiplexing.

Transaction pooling chỉ an toàn khi ứng dụng không phụ thuộc vào session state tồn tại giữa các transaction. Cần kiểm tra:
- Temporary tables.
- Session variables/settings.
- Prepared statements.
- Advisory locks.
- Cursors.
- Temporary objects.
- Session-level role/schema changes.

Không bật transaction pooling mà chưa kiểm tra behavior driver/ORM và DBMS.

### 11.4. Admission control và queue

Khi DBMS đạt concurrency tối ưu, application layer có thể giới hạn số request được gửi đồng thời. Các request dư được queue có giới hạn, trả 429/503 hoặc xử lý bất đồng bộ theo semantics.

Admission control cần:
- Queue size và max wait.
- Timeout.
- Priority theo workload.
- Giới hạn cho query nặng/reporting.
- Circuit breaker và load shedding.
- Metrics cho rejected/queued requests.

Mục tiêu là giữ hệ thống trong vùng capacity có throughput ổn định và p95/p99 phù hợp.

## 12. Connection storm, retry và failover

### 12.1. Connection storm

Sau deploy, restart hoặc failover, nhiều application replicas có thể đồng thời tạo pool connections. DBMS nhận một burst authentication/handshake và session initialization, làm CPU/network tăng đúng lúc cần phục hồi.

Giảm rủi ro bằng:
- Staggered startup.
- Pool warm-up có giới hạn.
- Connection creation rate limit.
- Jitter cho reconnect.
- Max lifetime không đồng bộ toàn bộ pool.
- Backoff khi DBMS từ chối kết nối.

### 12.2. Retry storm

Khi request timeout, client retry ngay có thể tăng connection và query demand trong lúc DBMS đang quá tải. Retry phải có exponential backoff, jitter, retry budget và idempotency cho thao tác ghi.

Không retry mọi lỗi. Connection refused, serialization failure, deadlock, timeout và business constraint cần chính sách khác nhau.

### 12.3. Failover và capacity dự phòng

Khi primary failover sang node khác, node mới phải chịu toàn bộ workload. Nếu chỉ dự phòng đúng mức tải bình thường mà không có headroom, failover có thể làm node mới quá tải.

Capacity plan phải xét:
- Số connection được reconnect cùng lúc.
- Pool warm-up.
- Replica promotion và recovery.
- Cache cold start.
- Replication lag.
- Log replay.
- Storage/network capacity của node dự phòng.

### 12.4. Thời gian phục hồi connection

Sau failover, connection cũ có thể lỗi và pool phải tạo lại. Theo dõi:
- Connection validation failure.
- Reconnect rate.
- Authentication latency.
- Pool acquisition wait.
- Request retry và error rate.
- Thời gian tới khi throughput ổn định.

## 13. Theo dõi dung lượng và connection capacity

### 13.1. Dashboard dung lượng

Theo dõi theo database, tablespace, volume và thành phần:
- Used/allocated/free bytes.
- Data/index growth theo ngày/tuần.
- Log used/allocated và log generation rate.
- Temp peak và spill.
- Backup/archive size.
- Replica storage và lag.
- Autoextend status và quota.
- Forecast time-to-threshold.

Đường xu hướng cần hiển thị cả hiện tại và dự báo theo base/high/stress scenario.

### 13.2. Dashboard kết nối

Theo dõi:
- Total, active, idle và idle-in-transaction sessions.
- Connection pool active/idle/pending.
- Pool acquisition wait p50/p95/p99.
- DB session limit và worker usage.
- Connection creation/reconnect rate.
- Connection errors/timeouts.
- Transaction duration và long-running sessions.
- Queue depth/admission control rejections.

Đếm connection tổng không đủ. Cần biết session nào đang làm việc, session nào chờ tài nguyên và pool nào đang giữ connection quá lâu.

### 13.3. Cảnh báo có tính dự báo

Cảnh báo nên dựa trên cả:
- Tỷ lệ sử dụng hiện tại.
- Tốc độ tăng.
- Time-to-exhaustion.
- Lead time mở rộng.
- Headroom sau khi trừ maintenance reserve.

Ví dụ, volume mới dùng 75% nhưng tăng 3% mỗi ngày có thể nguy hiểm hơn volume dùng 90% nhưng không tăng trong nhiều tháng. Tương tự, connection utilization 60% có thể đáng lo nếu active connections tăng nhanh và pool wait p99 đang tăng.

### 13.4. Phân biệt capacity limit và performance bottleneck

- Hết dung lượng: file/volume không thể tăng hoặc ghi thêm.
- Storage saturation: còn dung lượng nhưng I/O latency/queue cao.
- Connection limit: DBMS từ chối connection mới.
- Pool saturation: ứng dụng chờ connection dù DBMS có thể còn session capacity.
- Worker exhaustion: session/request chờ worker.
- Memory pressure: session/query tăng làm RAM không đủ.

Mỗi tình trạng cần hướng xử lý khác nhau. Tăng max_connections không giải quyết storage full; tăng disk size không giải quyết worker starvation.

## 14. Quy trình lập capacity plan

### Bước 1: Xác định phạm vi và SLA

Ghi database, instance, volume, workload class, retention, peak period, RPO/RTO và thời hạn dự báo.

### Bước 2: Thu lịch sử

Thu ít nhất một chu kỳ nghiệp vụ đại diện nếu có thể. Ghi data/index/log/temp/backup growth, connection concurrency, pool wait và DB resource usage.

### Bước 3: Phân rã thành phần

Tách data theo bảng/partition, index theo object, log theo generation/retention, temp theo workload và backup theo policy. Tách volume để biết thành phần nào chạm ngưỡng trước.

### Bước 4: Xây dựng kịch bản

Tính base/high/stress. Ghi giả định về người dùng, transaction rate, row size, index growth, retention, replica lag và backup frequency.

### Bước 5: Tính time-to-exhaustion

Dùng usable capacity sau khi trừ headroom/reserve. Tính theo từng volume và thành phần có giới hạn riêng.

### Bước 6: Tính connection budget

Ước lượng active connection demand từ arrival rate × hold time. Cộng max pool của mọi replica/service, rồi trừ reserved capacity và các workload không thuộc application pool.

### Bước 7: Benchmark và kiểm tra giới hạn

Thử tải ở nhiều mức active connections, query mix và data size. Tìm điểm throughput chững lại, latency tăng nhanh hoặc worker/memory/I/O bão hòa.

### Bước 8: Xác định hành động và lead time

Có thể cần:
- Mở rộng volume/tier.
- Thay đổi retention/archive.
- Tối ưu index/log/temp.
- Giảm connection hold time.
- Điều chỉnh pool hoặc proxy.
- Giới hạn concurrency.
- Tách reporting workload.
- Mở rộng DB instance hoặc chuẩn bị scale-out.

### Bước 9: Gán owner và lịch rà soát

Capacity plan cần owner, ngày cập nhật, nguồn metric, giả định và điều kiện kích hoạt hành động. Rà soát sau thay đổi business, schema, retention, DBMS version hoặc traffic pattern.

## 15. Ví dụ: dự báo kết hợp dung lượng và connection

Một ứng dụng có 10 API replicas, mỗi replica có pool max 40. Có thêm 3 worker replicas với pool max 15. Reporting service có pool max 20.

Potential pool connections:

~~~text
API:       10 × 40 = 400
Workers:    3 × 15 =  45
Reporting:  1 × 20 =  20
Total:                465
~~~

DBMS có giới hạn 600 client connections. Nếu cần dành 40 cho admin/monitoring/replication và 60 làm reserve, ngân sách pool ứng dụng tối đa theo phép tính đơn giản chỉ còn 500. Pool potential 465 nằm dưới con số đó, nhưng vẫn cần benchmark vì 465 session đồng thời có thể vượt capacity CPU/memory/worker thực tế.

Đo workload cho thấy 900 DB requests/s, connection hold time trung bình 30 ms:

~~~text
Average busy connections
  ≈ 900 × 0.030 = 27
~~~

Average 27 không chứng minh pool max 465 là hợp lý. Cần xem peak arrival, p99 hold time, burst, transaction duration và số request song song trên một API. Có thể pool nhỏ hơn nhiều vẫn đáp ứng throughput, trong khi admission control bảo vệ DBMS.

Về storage, giả sử data/index tăng 28 GB/ngày, log generation 12 GB/ngày và online retention 365 ngày. Ước lượng data footprint:

~~~text
28 GB/day × 365 days = 10,220 GB
~~~

Log generation không nhất thiết phải giữ toàn bộ 12 GB/ngày × 365 ngày trên volume online; retention phụ thuộc backup, replication, recovery và archive policy. Cần tính log peak và lý do log chưa được reuse. Backup có thể nằm ở storage riêng với retention khác.

Ví dụ này cho thấy capacity data và connection demand là hai phép tính độc lập nhưng cùng cần dựa trên workload thực tế. Không lấy max pool làm số active connections trung bình và không lấy log generation làm dung lượng log cần giữ vĩnh viễn.

## 16. Những sai lầm thường gặp

**Dùng dung lượng database hiện tại để dự báo mà không đo growth rate.** Một bảng có thể tăng nhanh theo mùa vụ hoặc sau khi onboard tenant.

**Chỉ tính table data.** Index, log, temp, backup, archive và maintenance headroom đều cần capacity riêng.

**Cho rằng retention policy tự làm database nhỏ lại.** Nếu archive/purge job không chạy hoặc log bị giữ, dung lượng vẫn tăng.

**Dùng tổng volume capacity thay cho usable capacity.** Cần trừ reserve, quota, maintenance và các workload khác.

**Ngoại suy một ngày thành dự báo dài hạn.** Tăng trưởng có thể tuyến tính, theo tỷ lệ, theo mùa hoặc có step change.

**Pool max của một replica là tổng connection.** Phải nhân với mọi replicas và cộng background/reporting services.

**Đặt pool size bằng số thread hoặc người dùng.** Connection demand phụ thuộc arrival rate và hold time.

**Tăng max_connections khi pool wait cao.** Pool wait có thể do DBMS đã bão hòa; tăng giới hạn có thể làm tình hình xấu hơn.

**Đếm session nhưng bỏ qua worker và memory.** Session limit, worker limit và memory capacity là các giới hạn khác nhau.

**Bỏ qua idle-in-transaction.** Session này có thể giữ lock hoặc snapshot và làm cleanup chậm.

**Không tính connection storm khi deploy/failover.** Pool reconnect đồng loạt có thể làm DBMS quá tải trong giai đoạn phục hồi.

**Không dành connection quản trị.** Khi pool ứng dụng chiếm hết giới hạn, vận hành có thể không truy cập được để điều tra.

**Chỉ theo dõi phần trăm sử dụng.** Growth rate, queue, latency và time-to-exhaustion mới cho biết cần hành động khi nào.

## 17. Checklist dự báo dung lượng và giới hạn kết nối

- [ ] Đã phân biệt logical size, allocated size, used space và free space chưa?
- [ ] Đã đo data/index growth theo bảng và partition chưa?
- [ ] Đã theo dõi log generation, log retention và lý do log chưa được reuse chưa?
- [ ] Đã đo peak temporary space và spill chưa?
- [ ] Đã tính backup, archive, replica và maintenance workspace chưa?
- [ ] Đã xác định retention, archive và purge có thực sự hoàn thành không?
- [ ] Đã tính usable capacity sau khi trừ reserve và headroom chưa?
- [ ] Đã lập base/high/stress growth scenarios chưa?
- [ ] Đã tính time-to-exhaustion theo từng volume chưa?
- [ ] Đã xác định lead time mở rộng và ngưỡng cảnh báo sớm chưa?
- [ ] Đã phân biệt connection, session, active request và worker chưa?
- [ ] Đã đo arrival rate và connection hold time chưa?
- [ ] Đã tính tổng max pool trên tất cả application replicas/services chưa?
- [ ] Đã dành capacity cho admin, monitoring, replication và failover chưa?
- [ ] Đã benchmark DBMS ở nhiều mức active connections chưa?
- [ ] Đã kiểm tra max connections/session, worker, memory và OS limits chưa?
- [ ] Đã xem pool/proxy semantics và session state compatibility chưa?
- [ ] Đã theo dõi pool wait, idle-in-transaction, reconnect và connection storm chưa?
- [ ] Đã có owner, lịch rà soát và kế hoạch mở rộng chưa?

## Kết luận

Dự báo dung lượng cần tính data, index, log, temp, backup, replication và khoảng trống cho maintenance trên từng volume. Dùng số liệu tăng trưởng theo thời gian, retention và các kịch bản base/high/stress để tính time-to-exhaustion; luôn trừ headroom và lead time mở rộng trước khi đặt cảnh báo. Dung lượng logic, allocated space và năng lực I/O là các chỉ số khác nhau.

Dự báo kết nối cần dựa trên arrival rate, connection hold time, concurrency và tổng pool trên mọi application replicas. Connection limit của DBMS không phải capacity xử lý an toàn; worker, memory, CPU và lock contention có thể bão hòa trước. Hãy benchmark nhiều mức active connections, giữ reserve cho quản trị/failover, theo dõi pool wait và connection storm, rồi cập nhật capacity plan khi workload, retention hoặc kiến trúc thay đổi.

