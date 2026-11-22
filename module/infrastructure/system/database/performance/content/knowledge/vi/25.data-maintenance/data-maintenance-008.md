# Ảnh hưởng của sao lưu, kiểm tra dữ liệu và tác vụ nền đến tải chính

Trong chương **Bảo trì dữ liệu** của module **DATABASE_PERFORMANCE**, sao lưu, kiểm tra tính toàn vẹn và các tác vụ nền giúp bảo vệ dữ liệu, duy trì khả năng phục hồi và giữ database hoạt động ổn định. Tuy nhiên, những công việc này cùng sử dụng CPU, bộ nhớ, I/O, transaction log, network và các cấu trúc nội bộ với workload giao dịch chính. Một bản backup có thể làm tăng độ trễ đọc; kiểm tra toàn vẹn có thể quét lượng dữ liệu lớn; rebuild index có thể tạo nhiều log và I/O; vacuum hoặc purge có thể cạnh tranh với truy vấn đang chạy.

Vì vậy, bảo trì dữ liệu là một phần của bài toán tối ưu hiệu năng. Cần đo tải nền cùng tải ứng dụng, xác định tài nguyên dùng chung, đặt giới hạn và lịch chạy phù hợp, rồi kiểm chứng rằng SLO của workload chính vẫn được đáp ứng. Không thể đánh giá một tác vụ bảo trì chỉ bằng thời gian nó hoàn thành; cần xem cả tác động tới p95/p99, throughput, lock wait, log growth, replication lag và khả năng phục hồi.

## 1. Vì sao tác vụ bảo trì ảnh hưởng tới workload chính?

Database có nhiều nhóm công việc cùng chạy trên một tập tài nguyên:

- **Workload chính:** truy vấn và transaction từ ứng dụng, API, báo cáo tương tác.
- **Sao lưu và phục hồi:** đọc data file, ghi backup, đọc/ghi transaction log, kiểm tra backup và restore thử.
- **Kiểm tra dữ liệu:** kiểm tra cấu trúc page, index, constraint, quan hệ và tính hợp lệ nghiệp vụ.
- **Bảo trì storage:** vacuum, purge, compaction, checkpoint, index rebuild/reorganize và partition maintenance.
- **Bảo trì optimizer:** thu thập hoặc cập nhật statistics, phân tích phân bố dữ liệu.
- **Tác vụ vận hành:** replication, log shipping, archive, CDC, retention, export và đồng bộ dữ liệu.

Các công việc này có thể cùng tranh chấp:

| Tài nguyên | Tác vụ nền sử dụng | Ảnh hưởng có thể thấy ở workload chính |
|---|---|---|
| CPU | Nén backup, checksum, kiểm tra page, sort/build index, thống kê | Query CPU-bound chậm hơn, run queue tăng |
| Data I/O | Scan backup, consistency check, vacuum, index rebuild | Buffer read chậm, queue và I/O latency tăng |
| Log/WAL/redo | DML bảo trì, rebuild, purge, batch cleanup | Commit latency, log growth và archive backlog tăng |
| Memory | Buffer pool, cache, sort/hash, backup buffer | Cache churn, memory grant giảm, spill tăng |
| Network | Gửi backup, replication, archive và CDC | Application round trip hoặc replication lag tăng |
| Lock/latch | DDL, index maintenance, schema change, cleanup | Lock wait, blocking, deadlock hoặc thời gian chờ metadata |
| Storage capacity | Backup set, snapshot, temp, version store, log | Volume đầy, autogrowth, lỗi ghi hoặc giảm khả năng phục hồi |

Tác động phụ thuộc hệ quản trị, phiên bản, cách backup, storage topology, isolation level, concurrency và cấu hình tác vụ. Một số công cụ hỗ trợ online hoặc concurrent operation, nhưng “online” không có nghĩa là không dùng tài nguyên hay không cần khóa.

## 2. Phân biệt các loại công việc bảo trì

### 2.1. Sao lưu vật lý và sao lưu logic

**Sao lưu vật lý** thường sao chép data file, page, block hoặc snapshot của storage theo cơ chế nhất quán của database. Công cụ có thể kết hợp transaction log để tạo điểm phục hồi hợp lệ. Sao lưu vật lý thường phù hợp với database lớn và phục hồi toàn bộ instance/database.

**Sao lưu logic** xuất dữ liệu thành bảng, dòng, schema hoặc định dạng có thể nạp lại. Ví dụ `pg_dump`, export theo bảng hoặc công cụ dump của hệ quản trị. Sao lưu logic thường tiêu thụ CPU để đọc, chuyển đổi và serialize dữ liệu; khi restore, nó phải parse và insert lại dữ liệu, tạo index và kiểm tra constraint.

Hai loại có profile tải khác nhau. Logical dump có thể phát nhiều query đọc và sử dụng CPU của database/client; physical backup có thể đọc data file hoặc block liên tục và ghi lượng dữ liệu lớn ra đích. Cần benchmark công cụ và phương thức thực tế.

### 2.2. Full, incremental và differential backup

- **Full backup:** tạo bản sao đầy đủ theo phạm vi backup. Dễ hiểu khi quản lý chuỗi backup nhưng có thể đọc và truyền lượng dữ liệu lớn.
- **Incremental backup:** lưu phần thay đổi kể từ một mốc backup trước đó theo semantics của công cụ. Có thể giảm lượng dữ liệu mỗi lần chạy, nhưng restore thường cần ghép chuỗi nhiều phần.
- **Differential backup:** lưu thay đổi kể từ full backup gần nhất theo cách công cụ định nghĩa. Các lần differential sau có thể lớn dần cho tới lần full tiếp theo.
- **Transaction log/WAL/redo backup hoặc archive:** lưu các log cần thiết để phục hồi tới thời điểm hoặc vị trí mong muốn.

Không phải hệ quản trị nào cũng định nghĩa incremental/differential giống nhau. Cần đọc tài liệu của công cụ backup và xác minh chuỗi phụ thuộc. Backup nhỏ hơn không đồng nghĩa restore đơn giản hơn; số lượng file, manifest, log chain và thời gian áp dụng có thể làm RTO tăng.

### 2.3. Kiểm tra tính toàn vẹn

Kiểm tra dữ liệu có nhiều cấp:

- **Kiểm tra vật lý:** page/block, checksum, cấu trúc file và index.
- **Kiểm tra logic:** cấu trúc bảng, constraint, quan hệ khóa ngoại, kiểu dữ liệu và tính nhất quán giữa các cấu trúc.
- **Kiểm tra nghiệp vụ:** số dư, tổng tiền, số lượng, trạng thái và quy tắc domain.
- **Kiểm tra backup:** xác minh backup set đọc được, checksum hợp lệ và có thể restore.

Một phép kiểm tra checksum không chứng minh dữ liệu nghiệp vụ đúng. Ngược lại, tổng tiền khớp cũng không chứng minh mọi page hoặc index đều không hỏng. Hãy xác định rõ mục tiêu của từng loại kiểm tra.

### 2.4. Tác vụ nền định kỳ

Các tác vụ nền thường gặp:

- Thu thập statistics cho optimizer.
- Vacuum, purge hoặc cleanup phiên bản cũ.
- Rebuild/reorganize index và compaction.
- Checkpoint, log archive và log truncation theo chính sách.
- Xóa dữ liệu hết hạn, partition detach/drop và retention.
- Đồng bộ replica, CDC và search index.
- Reconcile dữ liệu dẫn xuất, materialized view hoặc summary table.

Mỗi tác vụ có thể giúp workload chính nhanh hơn trong dài hạn nhưng gây tải tức thời khi chạy. Ví dụ, cập nhật statistics có thể làm optimizer chọn plan mới; index rebuild có thể cải thiện access path nhưng tạo I/O, log và lock; vacuum giải phóng phiên bản cũ nhưng phải đọc/ghi page và cạnh tranh với query.

## 3. Đo tác động thay vì chỉ nhìn thời gian backup

Trước khi điều chỉnh lịch bảo trì, cần có baseline khi workload chính chạy một mình và khi chạy cùng tác vụ nền.

### 3.1. Chỉ số của workload chính

- Throughput: transaction/second, request/second và query executions.
- Latency: p50, p95, p99 theo endpoint hoặc nhóm truy vấn quan trọng.
- Tỷ lệ timeout, deadlock, lỗi và retry.
- Connection pool wait và thời gian chờ lấy connection.
- Lock wait, blocking chain và thời gian giữ transaction.
- Top query theo CPU, logical reads, physical reads và elapsed time.

### 3.2. Chỉ số của database và hệ điều hành

- CPU utilization theo core, run queue và system CPU.
- Memory pressure, buffer pool/cache hit, page eviction và spill.
- IOPS, throughput, request size, queue depth và p95/p99 I/O latency.
- Data/log/temp volume usage, autogrowth và tốc độ tăng log.
- Log flush latency, WAL/redo generation và archive backlog.
- Replication/CDC lag, queue backlog và tốc độ apply.
- Tác vụ nền đang chạy, thời gian chạy, số dòng/page xử lý và mức song song.

### 3.3. Đo theo cửa sổ thời gian đồng bộ

Để liên hệ nguyên nhân với triệu chứng, hãy ghi timestamp đồng bộ cho:

1. Thời điểm bắt đầu/kết thúc backup hoặc consistency check.
2. Thời điểm bắt đầu từng phase như scan, compression, upload và validation.
3. Throughput và p95/p99 của workload chính.
4. CPU, I/O, log, memory, lock và replication metrics.
5. Sự kiện checkpoint, autovacuum/purge, index maintenance và autogrowth.

Nếu p99 tăng đúng lúc backup bắt đầu và I/O queue tăng cùng thời điểm, đó là bằng chứng về cạnh tranh storage. Nếu CPU tăng nhưng I/O ổn định trong lúc nén backup, compression có thể đang chiếm CPU. Cần dùng nhiều tín hiệu cùng lúc để tránh kết luận từ tương quan đơn lẻ.

### 3.4. So sánh baseline và workload hỗn hợp

| Kịch bản | Mục tiêu đo |
|---|---|
| Workload chính, không có tác vụ nền | Baseline latency, throughput và tài nguyên |
| Chỉ chạy tác vụ nền | Profile CPU/I/O/log/network của tác vụ |
| Workload chính + tác vụ nền | Mức suy giảm SLO và tài nguyên cạnh tranh |
| Workload chính + nhiều tác vụ nền theo lịch | Tác động cộng dồn ở giờ bảo trì |
| Restore/maintenance recovery test | Năng lực phục hồi và tải khi tái tạo dữ liệu |

Đừng chỉ thử từng tác vụ riêng nếu production có thể chạy backup, statistics, purge và replication cùng lúc. Tác động tổng hợp có thể lớn hơn từng tác động riêng lẻ.

## 4. Sao lưu ảnh hưởng tới tải chính như thế nào?

### 4.1. Scan data file và cạnh tranh I/O

Backup phải đọc một lượng dữ liệu đáng kể. Nếu đọc trên cùng storage pool với database, các request backup có thể chiếm queue, băng thông và cache của thiết bị. Tác động thường rõ ở workload có nhiều random read hoặc log flush nhạy với latency.

Một backup sequential có thể đạt throughput cao nhưng làm p95 của random lookup tăng vì các request cùng chia sẻ controller, volume hoặc backend. Đặt backup trên một volume khác chỉ giúp khi volume đó thực sự có tài nguyên độc lập; hai volume trên cùng một storage pool có thể vẫn cạnh tranh.

### 4.2. Nén và mã hóa backup

Compression giảm bytes truyền và dung lượng lưu, nhưng dùng CPU. Nếu CPU là bottleneck, nén mạnh có thể làm query chậm hơn. Nếu network hoặc storage đích là bottleneck, compression có thể giảm thời gian tổng thể dù CPU tăng.

Encryption cũng tiêu thụ CPU và có thể làm tăng thời gian xử lý. Một số hệ thống hỗ trợ hardware acceleration hoặc offload; cần đo throughput nén/mã hóa, CPU và latency của workload chính.

Chọn mức compression dựa trên tài nguyên đang giới hạn:

- CPU còn nhiều, network chậm: nén có thể có lợi.
- CPU đã gần bão hòa, storage đích đủ nhanh: giảm compression hoặc chuyển tác vụ sang host khác có thể phù hợp.
- Cần bảo mật dữ liệu: mã hóa vẫn là yêu cầu bảo vệ; hãy sizing CPU và đường truyền tương ứng thay vì bỏ qua bảo mật.

### 4.3. Backup tới network hoặc object storage

Đẩy backup ra SAN, NAS hoặc object storage sử dụng network, client buffer và tài nguyên đích. Nếu đường truyền dùng chung với application hoặc replication, backup có thể làm tăng network latency, retransmission hoặc queue.

Theo dõi băng thông theo interface, packet loss, throughput upload, retry và thời gian hoàn tất. Có thể giới hạn tốc độ truyền, dùng cửa sổ riêng hoặc một backup proxy/host phù hợp. Cần kiểm tra cả đường upload và thời gian xác minh dữ liệu ở đích.

### 4.4. Snapshot backup và copy-on-write

Storage snapshot hoặc snapshot do database phối hợp có thể tạo điểm tham chiếu nhanh, giảm thời gian khóa hoặc dừng ghi. Tuy nhiên, snapshot không làm chi phí biến mất. Sau khi snapshot được tạo, các block bị thay đổi có thể cần copy-on-write hoặc redirect-on-write metadata; nếu snapshot được giữ lâu, dung lượng delta có thể tăng.

Với workload ghi cao, snapshot kéo dài có thể làm tăng dung lượng storage, metadata và write amplification. Nếu snapshot đầy hoặc backend đạt giới hạn, ghi của workload chính có thể bị ảnh hưởng. Hãy theo dõi snapshot age, delta growth, free space và latency trong suốt vòng đời snapshot.

Snapshot ở tầng storage cần được phối hợp với database để bảo đảm tính nhất quán. Một snapshot crash-consistent có thể tương đương trạng thái sau sự cố mất điện, nhưng không nhất thiết đủ cho mọi yêu cầu application-consistent nếu nhiều file hoặc volume liên quan. Dùng cơ chế quiesce/backup mode hoặc log chain theo hướng dẫn của engine.

### 4.5. Transaction log và backup chain

Backup log/WAL/redo hoặc archive log có thể tạo thêm đọc, ghi và network. Nếu log archive hoặc backup đích không theo kịp tốc độ phát sinh, archive backlog tăng và có thể làm đầy storage log hoặc vùng archive.

Theo dõi log generation rate, archive throughput, oldest unarchived log, replication lag và dung lượng còn trống. Đặt cảnh báo trước ngưỡng nguy hiểm; không xóa log thủ công khi chưa xác nhận backup/replication chain và chính sách phục hồi.

## 5. Sao lưu trên replica có thực sự giảm tải primary?

Chạy backup từ replica có thể giảm một phần I/O đọc trên primary, nhưng không phải lúc nào cũng miễn phí hoặc an toàn.

Các yếu tố cần xem:

- Replica vẫn phải nhận và apply log từ primary.
- Backup scan có thể cạnh tranh I/O với apply worker và query đọc.
- Một số loại backup hoặc công cụ vẫn cần metadata, checkpoint hay phối hợp với primary.
- Replica có thể bị lag hoặc phải giữ log lâu hơn khi backup tạo tải.
- Nếu replica được promote trong failover, backup đang chạy có thể ảnh hưởng thời gian chuyển vai trò hoặc tài nguyên phục vụ traffic mới.
- Backup từ replica cần bảo đảm điểm nhất quán và chuỗi log đủ để phục hồi theo RPO/RTO.

Chỉ chuyển backup sang replica sau khi đo cả primary và replica, kiểm tra tính nhất quán của backup và thử restore. Không coi replica là máy rảnh nếu nó đang phục vụ truy vấn đọc hoặc là thành phần dự phòng bắt buộc.

## 6. Kiểm tra tính toàn vẹn dữ liệu và tác động hiệu năng

### 6.1. Physical consistency check

Kiểm tra vật lý có thể quét page/block, xác minh checksum, cấu trúc index và metadata. Với database lớn, đây là công việc đọc nhiều dữ liệu và tiêu thụ CPU để xác minh. Nếu chạy trên primary trong giờ cao điểm, nó có thể cạnh tranh với truy vấn và backup.

Một số hệ quản trị cung cấp công cụ chuyên biệt:

- SQL Server: `DBCC CHECKDB` kiểm tra tính toàn vẹn logic và vật lý của database; có thể tạo tải đọc và sử dụng tempdb.
- Oracle: RMAN `VALIDATE` hoặc công cụ kiểm tra block phù hợp để xác minh backup/datafile; phạm vi và mức kiểm tra phụ thuộc lệnh.
- PostgreSQL: checksum page có thể được xác minh khi page được đọc nếu checksum được bật; extension `amcheck` có thể kiểm tra cấu trúc index B-tree ở phạm vi được hỗ trợ.
- MySQL: `CHECK TABLE` có semantics phụ thuộc storage engine; InnoDB còn có các cơ chế kiểm tra và phục hồi riêng.

Không chạy lệnh kiểm tra sửa chữa hoặc repair trên production khi chưa hiểu rõ tác động. Một số lệnh chỉ đọc, một số có thể khóa, thay đổi metadata hoặc ghi lại cấu trúc. Hãy đọc tài liệu đúng phiên bản và thực hiện restore/repair test trong môi trường phù hợp.

### 6.2. Logical validation

Logical validation kiểm tra quy tắc cấu trúc và quan hệ, ví dụ:

- Unique key không bị trùng.
- Foreign key không có bản ghi mồ côi.
- Trường bắt buộc không null.
- Giá trị số nằm trong miền hợp lệ.
- Số dòng, tổng số tiền và tổng số lượng khớp với nguồn.
- Các bảng dẫn xuất khớp với dữ liệu nguồn theo grain đã định nghĩa.

Một truy vấn validation có thể full scan hoặc aggregate nhiều bảng. Nếu kiểm tra trên primary, cần xem execution plan, index và số dòng đọc. Có thể chia kiểm tra theo partition, tenant hoặc khoảng khóa để giới hạn thời gian và tài nguyên, nhưng phải bảo đảm toàn bộ phạm vi được kiểm tra theo lịch.

### 6.3. Kiểm tra backup khác kiểm tra database nguồn

Database nguồn có thể đang hoạt động bình thường trong khi backup set bị thiếu file, sai manifest hoặc không thể restore. Ngược lại, checksum backup đúng không chứng minh mọi quy tắc nghiệp vụ trong dữ liệu nguồn đều đúng.

Quy trình bảo đảm cần bao gồm:

1. Kiểm tra trạng thái và checksum của backup set.
2. Xác minh các file và log cần thiết cho restore chain.
3. Thực hiện restore thử trong môi trường cô lập.
4. Chạy consistency check trên bản restore.
5. Kiểm tra ứng dụng có thể kết nối và đọc dữ liệu cần thiết.
6. Đo thời gian restore thực tế so với RTO.

Restore test thường cung cấp bằng chứng mạnh hơn việc chỉ thấy job backup báo thành công.

## 7. Tác động của vacuum, purge và cleanup phiên bản

Database dùng MVCC hoặc cơ chế lưu phiên bản thường cần cleanup để loại bỏ dữ liệu không còn được transaction nào cần. Nếu cleanup không theo kịp DML, dead tuple, undo history hoặc version store có thể tăng. Nhưng cleanup chạy quá mạnh cũng có thể cạnh tranh CPU và I/O với workload chính.

### 7.1. PostgreSQL VACUUM và autovacuum

`VACUUM` giúp đánh dấu không gian của tuple cũ có thể tái sử dụng và thực hiện một số công việc freeze/visibility maintenance. Autovacuum chạy nền theo ngưỡng và thống kê thay đổi.

Ví dụ chạy vacuum/analyze trên một bảng:

```sql
VACUUM (ANALYZE) public.orders;
```

Lệnh này có thể đọc/ghi page và tiêu thụ I/O/CPU; thông thường `VACUUM` không khóa đọc/ghi thông thường theo cách `VACUUM FULL` làm. `VACUUM FULL` rewrite bảng và cần khóa mạnh, vì vậy có tác động availability lớn hơn.

Theo dõi `n_dead_tup`, lần autovacuum gần nhất, thời lượng vacuum, transaction lâu và replication slot giữ xmin. Điều chỉnh ngưỡng autovacuum theo tốc độ thay đổi của từng bảng, không tắt autovacuum chỉ để giảm tải tức thời.

### 7.2. MySQL/InnoDB purge

InnoDB dùng undo log để hỗ trợ consistent read và rollback. Purge loại bỏ undo record không còn cần. Transaction dài có thể giữ read view cũ và ngăn purge tiến lên, làm history list length tăng.

Theo dõi transaction lâu, history list length, undo tablespace và tốc độ purge. Nếu purge backlog tăng, tìm transaction giữ snapshot lâu và workload DML tạo undo. Tăng worker purge hoặc dung lượng undo chỉ có ích khi phù hợp với bottleneck; nếu nguyên nhân là snapshot bị giữ, cần xử lý transaction đó.

### 7.3. SQL Server version cleanup

Khi dùng row versioning, các phiên bản cũ phải được giữ tới khi transaction snapshot liên quan không còn cần. Cleanup và version store sử dụng tài nguyên, thường liên quan `tempdb` hoặc persistent version store khi ADR được bật.

Theo dõi version store space, active snapshot transaction và tempdb I/O. Transaction snapshot dài có thể làm version store tăng. Đặt giới hạn thời gian transaction, điều tra session giữ snapshot và dự báo dung lượng tempdb/PVS theo workload.

### 7.4. Oracle undo

Oracle dùng undo để cung cấp read consistency và rollback. Tác vụ DML lớn, transaction dài và truy vấn cần snapshot cũ có thể làm nhu cầu undo tăng. Theo dõi undo generation, retention, dung lượng và lỗi snapshot too old.

Không giảm retention hoặc tái sử dụng undo chỉ để tiết kiệm storage khi truy vấn dài cần read consistency. Hãy sizing undo theo workload và thời gian truy vấn cần hỗ trợ.

## 8. Statistics và tác động của ANALYZE/UPDATE STATISTICS

Optimizer dùng statistics để ước lượng cardinality, selectivity và chi phí access path. Statistics cũ có thể làm chọn plan kém; cập nhật statistics có thể cải thiện plan nhưng cũng có thể khiến plan thay đổi và tạo biến động hiệu năng.

### 8.1. Chi phí thu thập statistics

Thu thập statistics có thể đọc sample hoặc scan dữ liệu, dùng CPU để tính histogram/cardinality và lưu metadata. Với bảng lớn hoặc nhiều index, công việc này có thể cạnh tranh I/O và CPU.

Các hệ quản trị có cách lấy mẫu và mức độ tự động khác nhau. PostgreSQL `ANALYZE`, MySQL `ANALYZE TABLE`, SQL Server `UPDATE STATISTICS` và Oracle `DBMS_STATS` không có semantics hoàn toàn giống nhau. Cần chọn sample, partition scope và lịch theo đặc điểm bảng.

### 8.2. Plan change sau cập nhật statistics

Sau khi statistics thay đổi, optimizer có thể chọn index scan thay table scan, đổi join order hoặc thay parallelism. Plan mới có thể tốt hơn cho phần lớn tham số nhưng kém hơn cho một số giá trị skew. Cần theo dõi query latency và plan regression sau đợt cập nhật lớn.

Đối với query quan trọng, lưu baseline plan/metrics và so sánh actual rows với estimated rows. Nếu plan regression xuất hiện, tìm nguyên nhân trong phân bố dữ liệu, parameter sensitivity, statistics sampling và thay đổi schema.

### 8.3. Chạy statistics có chọn lọc

Không nhất thiết analyze toàn bộ database sau mỗi lần nạp dữ liệu nhỏ. Xác định bảng/partition thay đổi đáng kể, mức skew và truy vấn phụ thuộc statistics. Có thể cập nhật theo phạm vi hoặc để cơ chế auto statistics xử lý nếu ngưỡng được cấu hình phù hợp.

Tuy nhiên, tránh trì hoãn quá lâu khi bảng có thay đổi lớn. Statistics stale có thể làm query plan sai và tăng tải nhiều hơn chi phí của lần analyze.

## 9. Index maintenance và rebuild

Index rebuild hoặc reorganize có thể xử lý fragmentation, cập nhật cấu trúc hoặc tạo lại index sau bulk load. Nhưng đây là công việc đọc/ghi lớn, có thể dùng temp space, transaction log và khóa.

### 9.1. Rebuild và reorganize không giống nhau

- **Rebuild:** tạo lại cấu trúc index; có thể đọc dữ liệu nguồn, sort key, ghi page mới và cập nhật metadata.
- **Reorganize/defragment:** điều chỉnh cấu trúc hiện tại theo cách ít xâm lấn hơn nhưng có thể kéo dài và không giải quyết mọi dạng fragmentation.
- **Create index:** tạo index mới, thường cần đọc bảng và sort dữ liệu.
- **Drop index:** giảm chi phí duy trì trong tương lai nhưng có thể làm query khác chậm và thay đổi constraint nếu index đang bảo vệ uniqueness.

Các tùy chọn online/concurrent phụ thuộc engine và loại index. Online rebuild vẫn dùng CPU, I/O, log và có thể cần khóa ngắn ở đầu/cuối hoặc metadata lock.

### 9.2. SQL Server

SQL Server hỗ trợ `ALTER INDEX ... REBUILD` và `REORGANIZE`; online operation tùy edition, phiên bản và loại index. Rebuild có thể tạo transaction log lớn và cần không gian bổ sung. Đo log growth, tempdb, blocking và thời gian hoàn tất; không chạy tất cả index theo một ngưỡng fragmentation cứng mà không xem workload.

### 9.3. PostgreSQL

PostgreSQL hỗ trợ `REINDEX` và `REINDEX CONCURRENTLY` cho các trường hợp được hỗ trợ. Concurrent reindex giảm mức chặn ghi trong phần lớn quá trình nhưng có thêm phase, thời gian và tài nguyên; không phải thao tác không tải. Theo dõi disk space, WAL, replication lag và tiến trình index build.

### 9.4. MySQL/InnoDB và Oracle

Trong InnoDB, thao tác `ALTER TABLE`/index có thể dùng online DDL ở một số trường hợp, nhưng mức độ online phụ thuộc thay đổi schema, phiên bản và tài nguyên. Có thể cần temporary table, rebuild clustered index hoặc metadata lock.

Oracle hỗ trợ nhiều phương thức online index rebuild và maintenance; vẫn cần tài nguyên cho đọc, sort, ghi, redo/undo và không gian. Hãy xem loại index, partition, parallel degree và giới hạn edition.

### 9.5. Chỉ rebuild khi có bằng chứng

Fragmentation không tự động làm mọi query chậm. Với SSD, tác động của vị trí page có thể khác HDD; với index ít được đọc, rebuild có thể không đem lại lợi ích. Hãy xem page density, logical/physical reads, scan pattern, index size, write overhead và query latency trước khi quyết định.

## 10. Checkpoint, log archive và tác vụ retention

Checkpoint ghi dirty page xuống storage để giới hạn recovery work. Tác vụ archive chuyển log tới vùng lưu trữ khác; retention xóa hoặc detach dữ liệu cũ. Các công việc này có thể tạo I/O burst hoặc tăng log/network.

### 10.1. Checkpoint và write burst

Checkpoint quá dồn có thể tạo nhiều write đồng thời, tăng queue và latency của data volume. Checkpoint quá thưa có thể làm thời gian phục hồi dài hoặc tăng áp lực log. Cần theo dõi checkpoint duration, dirty page, WAL/redo, write throughput và query p99.

### 10.2. Archive và log shipping

Nếu archive destination chậm hoặc network bị nghẽn, log backlog tăng. Một số hệ thống cần giữ log cho tới khi archive/replication xác nhận, nên vùng log có thể đầy nếu downstream không theo kịp.

Đặt cảnh báo theo tuổi log chưa archive, dung lượng log còn lại và tốc độ phát sinh. Không xóa archive hoặc transaction log bằng thao tác file system ngoài cơ chế quản lý của database.

### 10.3. Retention và xóa dữ liệu lớn

Một lệnh `DELETE` hàng triệu dòng có thể tạo nhiều log/undo, khóa nhiều row và làm cleanup nặng. Nếu dữ liệu được phân vùng theo thời gian, detach/drop partition có thể rẻ hơn xóa từng dòng, nhưng cần xác minh foreign key, index, replication và semantics retention.

Nếu phải xóa theo batch, dùng khóa/điều kiện ổn định, batch size đo được và checkpoint. Giữa các batch có thể cho workload chính tiếp tục chạy; tuy nhiên mỗi batch là transaction riêng và dữ liệu có thể thay đổi giữa các lần chạy.

## 11. Lập lịch và điều tiết tài nguyên

### 11.1. Chọn cửa sổ bảo trì

Chọn thời gian dựa trên traffic thực tế, không dựa trên giả định “ban đêm không có tải”. Xem giờ cao điểm theo múi giờ của người dùng, batch cuối ngày, đối soát, báo cáo, replication và lịch backup khác.

Lịch bảo trì nên tránh chồng các công việc có cùng bottleneck. Ví dụ, không nhất thiết chạy full backup, consistency check, index rebuild và ETL lớn cùng lúc trên một storage pool.

### 11.2. Giới hạn tốc độ và mức song song

Nhiều công cụ hỗ trợ throttle, max transfer rate, worker count hoặc parallel degree. Bắt đầu với mức thấp, quan sát SLO rồi tăng dần. Nếu p95/p99 tăng vượt ngưỡng, giảm tốc hoặc tạm dừng theo chính sách.

Điều tiết có thể thực hiện ở:

- Backup tool: giới hạn throughput hoặc số stream.
- Database scheduler/resource governor: giới hạn CPU, parallelism hoặc workload group nếu engine hỗ trợ.
- Job orchestrator: giới hạn số job chạy đồng thời và ưu tiên.
- Operating system/cgroup: giới hạn CPU hoặc I/O cho process phù hợp.
- Network QoS: giới hạn băng thông backup trên đường dùng chung.

Không phải mọi hệ quản trị đều hỗ trợ cùng khả năng. Một số tác vụ nội bộ như checkpoint hoặc autovacuum không thể bị giới hạn tùy ý bằng cách đặt CPU limit bên ngoài mà không gây hệ quả khác.

### 11.3. Ưu tiên workload chính

Nếu database hỗ trợ resource governance, có thể phân nhóm workload ứng dụng và maintenance để dành tài nguyên tối thiểu cho giao dịch chính. Cần thử nghiệm vì ưu tiên quá mạnh có thể làm maintenance không bao giờ hoàn thành, khiến backup hoặc cleanup backlog tích tụ.

Thiết kế tốt thường có quota tối đa và tối thiểu, lịch chạy, giới hạn concurrency và điều kiện dừng theo SLO. Mục tiêu là workload chính ổn định trong khi tác vụ nền vẫn hoàn thành trong cửa sổ vận hành.

### 11.4. Tạm dừng và tiếp tục

Một job dài nên có khả năng pause/resume hoặc chia thành bước có checkpoint. Nếu không thể pause an toàn, hãy xác định cách hủy và khởi động lại, chi phí rollback và trạng thái dở dang. Không kill process tùy tiện khi chưa biết database sẽ rollback, cleanup hoặc phục hồi như thế nào.

## 12. Chạy bảo trì trên replica hoặc môi trường phụ

Offload backup, report hoặc consistency check sang replica có thể giảm tải primary, nhưng phải kiểm tra các ràng buộc:

- Replica apply log có theo kịp không?
- Tác vụ scan có làm chậm apply worker hoặc query người dùng trên replica không?
- Backup có yêu cầu khóa hoặc metadata từ primary không?
- Snapshot/backup có bao gồm đủ log để phục hồi không?
- Replica có cần giữ vai trò failover và đạt RTO không?
- Khi replica lag, kết quả kiểm tra hoặc export có thể thiếu thay đổi mới không?

Có thể dùng một replica chuyên cho báo cáo/backup, nhưng cần capacity plan riêng. Nếu backup chiếm hết I/O của replica, thời gian catch-up sau failover hoặc sau sự cố có thể kéo dài.

Một phương án khác là restore backup gần nhất sang môi trường kiểm tra rồi chạy consistency check, test ứng dụng và truy vấn validation ở đó. Cách này giảm tải trên production nhưng tiêu tốn compute/storage riêng và chỉ kiểm tra được dữ liệu tại điểm backup đã restore.

## 13. Quản lý dung lượng backup, snapshot và temp

Tác vụ bảo trì có thể làm tăng dung lượng tạm hoặc giữ tài nguyên lâu hơn dự kiến:

- Full/incremental backup và archive log chiếm backup repository.
- Snapshot giữ block cũ trong khi production tiếp tục ghi.
- Index rebuild tạo index mới trước khi index cũ được loại bỏ.
- Sort/hash/consistency check dùng temp space.
- Long transaction giữ undo/version store hoặc dead tuple.
- Backup staging và restore test cần thêm data volume.

Định cỡ phải tính cả dung lượng nguồn và đích. Đặt cảnh báo theo free space, tốc độ tăng, snapshot age, backup retention và tốc độ xóa. Không chỉ cảnh báo khi volume đã gần đầy; cần đủ thời gian để mở rộng hoặc dọn theo chính sách.

## 14. Ví dụ chẩn đoán backup làm p99 tăng

Một database có p99 API đọc bình thường khoảng 120 ms. Khi full backup bắt đầu, p99 tăng lên 480 ms, throughput API giảm và `read latency` của volume data tăng. CPU database chỉ tăng nhẹ.

Quy trình điều tra:

1. Đối chiếu timestamp backup với p99, throughput và I/O queue.
2. Xác định backup đọc từ primary hay replica, dùng volume nào và có nén/mã hóa ở đâu.
3. Kiểm tra backup throughput, block size, số stream và storage pool dùng chung.
4. Xem query plan của API có random read nhiều hay cache miss tăng không.
5. Kiểm tra replica lag, log flush và network để loại trừ bottleneck khác.
6. Thử giới hạn backup throughput hoặc chuyển backup sang replica có đủ headroom.
7. Chạy lại với cùng workload và so p95/p99, backup duration, I/O queue và replication lag.

Nếu giảm backup rate làm p99 trở về gần baseline nhưng backup kéo dài hơn, có thể chấp nhận đánh đổi nếu vẫn đáp ứng backup window. Nếu backup không còn hoàn tất trong cửa sổ, cần thêm năng lực storage/network hoặc thay đổi chiến lược backup.

## 15. Ví dụ lập lịch consistency check và index maintenance

Một hệ thống có consistency check toàn database chạy cùng lúc với index rebuild và batch xóa dữ liệu cũ. Cả ba cùng đọc/ghi storage và tạo thêm log/temp, khiến workload chính chậm.

Có thể cải thiện bằng cách:

1. Tách consistency check sang bản restore/replica phù hợp nếu quy trình và yêu cầu kiểm tra cho phép.
2. Chạy index maintenance theo bảng/index có bằng chứng cần thiết, tránh rebuild toàn bộ theo lịch cố định.
3. Chia retention delete thành batch hoặc chuyển sang partition maintenance.
4. Không chồng backup, consistency scan và rebuild trên cùng backend nếu storage đang gần saturation.
5. Giới hạn parallelism và theo dõi p99/lock/log trong từng phase.
6. Đối soát rằng tất cả phạm vi dữ liệu đã được kiểm tra và retention vẫn hoàn thành đúng hạn.

Lịch mới cần được xác minh bằng thử nghiệm tải hỗn hợp. Tách job ra các ngày khác nhau có thể giảm peak nhưng phải bảo đảm chu kỳ kiểm tra vẫn đáp ứng yêu cầu vận hành.

## 16. Quy trình thiết kế lịch bảo trì có kiểm soát

1. **Liệt kê tác vụ:** backup, log archive, consistency check, statistics, vacuum/purge, index maintenance, retention và batch.
2. **Ghi yêu cầu:** tần suất, backup window, RPO/RTO, thời gian hoàn tất và mức độ ưu tiên.
3. **Xác định tài nguyên:** CPU, data/log/temp I/O, memory, network, lock và dung lượng.
4. **Đo baseline:** workload chính khi không chạy tác vụ nền.
5. **Đo từng tác vụ:** profile riêng với dữ liệu và cấu hình gần production.
6. **Đo tác động hỗn hợp:** chạy cùng workload chính và các job có khả năng chồng lịch.
7. **Tìm bottleneck:** dùng query plan, wait event, OS/storage metrics và log/replication metrics.
8. **Chọn cách điều tiết:** lịch, throttle, concurrency, resource group, replica hoặc staging.
9. **Đặt điều kiện dừng:** p95/p99, error rate, lock wait, free space, replication lag và log backlog.
10. **Kiểm tra phục hồi:** restore thử, consistency check và đo RTO/RPO.
11. **Tự động hóa và cảnh báo:** ghi trạng thái từng phase, checkpoint, retry và kết quả.
12. **Rà soát định kỳ:** cập nhật capacity và lịch khi dữ liệu, workload hoặc storage thay đổi.

## 17. Những sai lầm thường gặp

- **Cho rằng online backup không ảnh hưởng production:** backup vẫn đọc dữ liệu, dùng CPU/network và có thể cạnh tranh storage.
- **Chỉ đo thời gian backup:** bỏ qua p95/p99, throughput, log growth và replication lag.
- **Chạy nhiều tác vụ nặng cùng lúc:** scan, rebuild, consistency check và ETL có thể cùng bão hòa I/O.
- **Nén backup tối đa:** có thể chuyển bottleneck sang CPU và làm query chậm.
- **Giữ snapshot quá lâu:** delta block và dung lượng copy-on-write có thể tăng nhanh.
- **Backup từ replica mà không đo apply lag:** có thể làm replica không còn sẵn sàng cho failover.
- **Tin job backup thành công mà không restore thử:** file có thể thiếu thành phần hoặc chuỗi log không hợp lệ.
- **Chạy consistency check trên primary vào giờ cao điểm:** scan lớn có thể cạnh tranh I/O và memory.
- **Rebuild mọi index theo lịch cứng:** tốn log/I/O và có thể không đem lại lợi ích cho workload.
- **Tắt autovacuum/purge để giảm tải:** phiên bản cũ tích tụ và tạo chi phí lớn hơn về sau.
- **Xóa log/archive thủ công:** có thể phá backup chain hoặc khả năng phục hồi.
- **Không có điều kiện pause/throttle:** tác vụ nền có thể tiếp tục đẩy hệ thống qua điểm bão hòa.
- **Chỉ kiểm tra tổng số dòng:** sai lệch theo nhóm hoặc duplicate có thể bị che khuất.
- **Không tính dung lượng tạm:** rebuild, snapshot, temp và backup có thể làm đầy volume.

## 18. Checklist bảo trì không làm suy giảm tải chính

- [ ] Đã lập danh sách backup, consistency check và tác vụ nền đang chạy.
- [ ] Đã xác định RPO, RTO, backup window và thời gian hoàn thành bắt buộc.
- [ ] Đã đo baseline throughput, p95/p99, error rate và resource usage của workload chính.
- [ ] Đã đo CPU, data/log/temp I/O, network, memory và lock của từng tác vụ.
- [ ] Đã xác định volume/storage pool nào được dùng chung.
- [ ] Đã đánh giá compression, encryption, snapshot và copy-on-write impact.
- [ ] Đã kiểm tra backup chain, checksum và thực hiện restore test.
- [ ] Đã phân biệt physical, logical, integrity và business validation.
- [ ] Đã chọn lịch tránh chồng các tác vụ có cùng bottleneck.
- [ ] Đã đặt throttle, parallelism và concurrency phù hợp.
- [ ] Đã xác định ngưỡng pause/stop theo SLO, free space, log và replication lag.
- [ ] Đã kiểm tra vacuum/purge/version cleanup không bị transaction dài cản trở.
- [ ] Đã chỉ chạy index maintenance khi có số liệu chứng minh cần thiết.
- [ ] Đã có checkpoint, retry, trạng thái job và quy trình resume an toàn.
- [ ] Đã kiểm tra năng lực replica/failover sau khi offload tác vụ.
- [ ] Đã ghi nhận metric trước/sau và rà soát lịch theo tăng trưởng dữ liệu.

Sao lưu, kiểm tra dữ liệu và tác vụ nền là điều kiện để database có thể phục hồi và duy trì chất lượng dữ liệu, nhưng chúng tiêu thụ cùng tài nguyên với workload chính. Cách vận hành hiệu quả là đo từng phase và tải hỗn hợp, nhận diện bottleneck, điều tiết tốc độ/concurrency, chọn lịch phù hợp và kiểm tra khả năng restore thực tế. Khi bảo trì được đưa vào capacity plan cùng SLO, RPO và RTO, hệ thống có thể hoàn thành công việc nền mà vẫn giữ độ trễ và throughput của ứng dụng trong giới hạn chấp nhận được.
