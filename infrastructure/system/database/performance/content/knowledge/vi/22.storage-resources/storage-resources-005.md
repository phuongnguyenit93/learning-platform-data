# Bố trí dữ liệu, nhật ký và vùng tạm theo đặc điểm tải

Hiệu năng cơ sở dữ liệu phụ thuộc đáng kể vào cách dữ liệu được bố trí trên thiết bị lưu trữ. Bảng và chỉ mục tạo ra phần lớn lượt đọc; transaction log hoặc WAL phục vụ độ bền và phục hồi; vùng tạm chứa kết quả trung gian của sort, hash, join và các phép tổng hợp; backup và archive phục vụ khôi phục cũng như vòng đời dữ liệu. Nếu các loại I/O này cạnh tranh trên cùng một tài nguyên, một workload có thể làm chậm workload khác dù CPU còn dư.

Trong phạm vi **DATABASE_PERFORMANCE**, việc tối ưu hiệu năng cơ sở dữ liệu cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Bố trí storage không chỉ là chọn ổ đĩa nhanh. Cần hiểu workload tạo ra kiểu I/O nào, yêu cầu latency và durability ra sao, dữ liệu nóng/lạnh thay đổi thế nào, và hệ quản trị dùng buffer, log, checkpoint cùng temporary files như thế nào.

Bài học này trình bày vai trò của data files, transaction log/WAL, vùng tạm và backup; cách đọc latency, IOPS, throughput và queue depth; cách phân bổ tài nguyên lưu trữ theo workload; các khác biệt giữa PostgreSQL, MySQL InnoDB và SQL Server; cùng quy trình benchmark và giám sát để xác nhận bố trí dữ liệu có cải thiện hiệu năng tổng thể.

## 1. Các loại dữ liệu và I/O trong một hệ quản trị

Một database không chỉ ghi dữ liệu bảng. Một hệ thống đang hoạt động có thể tạo ra nhiều luồng I/O khác nhau:

- **Data files:** chứa heap/table pages và các cấu trúc dữ liệu chính.
- **Index files:** chứa B-tree, hash, bitmap hoặc các cấu trúc chỉ mục khác.
- **Transaction log:** ghi nhận thay đổi để phục hồi và bảo đảm durability; ví dụ WAL trong PostgreSQL, redo log trong InnoDB, transaction log trong SQL Server.
- **Undo/version data:** phục vụ rollback và đọc nhất quán theo cơ chế MVCC hoặc locking của engine.
- **Temporary files / temp tablespace:** chứa dữ liệu trung gian khi sort, hash, join, materialize hoặc tạo bảng tạm.
- **System/catalog data:** metadata, schema, transaction state và các thông tin quản trị.
- **Backup và archive:** bản sao phục hồi, log archive và dữ liệu lịch sử được lưu theo retention.
- **Replication data:** log hoặc stream thay đổi được gửi và áp dụng trên replica.

Các nhóm này có đặc điểm truy cập khác nhau. Ví dụ, transaction log thường có luồng ghi tuần tự và nhạy với latency của commit. Data files có thể chịu đọc ngẫu nhiên từ index lookup, đọc tuần tự từ scan và ghi theo checkpoint. Temp files có thể tạo các đợt đọc/ghi lớn khi sort hoặc hash spill. Backup thường đọc lượng dữ liệu lớn tuần tự và có thể cạnh tranh băng thông với workload trực tuyến.

### Vì sao cần phân biệt các luồng I/O?

Nếu một máy chủ có đủ băng thông tổng nhưng log flush bị chậm, commit latency vẫn có thể tăng. Nếu temp spill dùng hết throughput, các truy vấn sort/hash có thể chậm và ảnh hưởng đến data read. Nếu backup chạy cùng lúc với giờ cao điểm, các lượt đọc tuần tự lớn có thể làm tăng queue depth và latency của I/O ngẫu nhiên.

Phân tích storage vì vậy cần trả lời hai câu hỏi:

1. Loại I/O nào đang tạo ra áp lực?
2. Loại I/O đó đang chia sẻ thiết bị, controller, network path hoặc storage pool với thành phần nào?

Chỉ nhìn tên thư mục hoặc mount point không đủ để kết luận hai nhóm dữ liệu có tài nguyên vật lý độc lập.

## 2. Đặc điểm tải quyết định cách bố trí

Trước khi chọn thiết bị hoặc tách data/log/temp, cần mô tả workload.

### OLTP: nhiều giao dịch nhỏ

Workload OLTP thường có:

- Nhiều index lookup và truy cập trang ngẫu nhiên.
- Nhiều transaction ngắn và commit thường xuyên.
- Ghi vào các bảng/index nóng.
- Yêu cầu latency thấp và ổn định.
- Nhiều phiên đồng thời có thể tranh cùng dữ liệu.

Đối với OLTP, độ trễ đọc/ghi nhỏ và khả năng xử lý I/O ngẫu nhiên thường quan trọng. Transaction log cần latency ghi ổn định để commit không bị kéo dài.

### OLAP và báo cáo: đọc lượng dữ liệu lớn

Workload phân tích có thể tạo ra:

- Sequential scan trên bảng hoặc partition lớn.
- Sort, hash join, hash aggregate và materialization.
- Temp I/O khi dữ liệu trung gian không vừa bộ nhớ.
- Đọc nhiều cột và nhiều trang liên tiếp.
- Các truy vấn dài, có thể chạy song song.

Với workload này, throughput tuần tự và khả năng duy trì băng thông quan trọng. Temp storage cũng cần đủ nhanh và đủ dung lượng để xử lý spill.

### Bulk load, ETL và bảo trì

Bulk load, index build, vacuum, reorganize, rebuild, backup và restore có thể tạo ra đợt I/O lớn. Những tác vụ này thường có thể lên lịch ngoài giờ cao điểm hoặc giới hạn tốc độ để tránh cạnh tranh với giao dịch trực tuyến.

### Workload hỗn hợp

Nhiều hệ thống vừa chạy OLTP vừa chạy báo cáo. Một truy vấn phân tích lớn có thể chiếm CPU, memory grant và storage bandwidth, làm p99 của giao dịch ngắn tăng lên. Có thể cần tách workload sang replica, read pool, warehouse hoặc storage tier riêng, nhưng quyết định phải dựa trên chi phí đồng bộ, độ trễ dữ liệu và vận hành.

## 3. Latency, IOPS, throughput và queue depth

Bốn chỉ số thường được nhắc cùng nhau nhưng mô tả những khía cạnh khác nhau.

- **Latency:** thời gian hoàn thành một yêu cầu I/O.
- **IOPS:** số thao tác đọc/ghi hoàn thành trong một giây.
- **Throughput:** lượng dữ liệu truyền trong một giây, thường tính MB/s hoặc GB/s.
- **Queue depth:** số yêu cầu I/O đang chờ hoặc đang được xử lý đồng thời tại một lớp trong stack.

### Latency

Latency thấp quan trọng với các thao tác nhỏ, đồng bộ và nằm trên đường critical path. Ví dụ, nếu commit cần chờ log flush, latency ghi log có thể ảnh hưởng trực tiếp đến thời gian ứng dụng nhận xác nhận.

Cần xem phân bố latency như p50, p95, p99 và p99.9. Trung bình thấp có thể che giấu một tỷ lệ nhỏ request cực chậm làm p99 của ứng dụng tăng.

### IOPS

IOPS biểu diễn số thao tác mỗi giây, nhưng không nói rõ mỗi thao tác đọc bao nhiêu byte. 100.000 IOPS với block 4 KB tương ứng lượng dữ liệu khác nhiều so với 100.000 IOPS với block 256 KB.

IOPS thường hữu ích khi đánh giá workload random I/O với kích thước block nhỏ, nhưng không nên dùng một con số IOPS duy nhất để mô tả mọi kiểu tải.

### Throughput

Throughput quan trọng với scan, backup, restore, bulk load và temp spill lớn. Một thiết bị có throughput tuần tự cao chưa chắc có latency tốt cho random write nhỏ.

### Queue depth

Queue depth cho biết mức độ yêu cầu đồng thời. Khi queue depth tăng, thiết bị có thể tận dụng song song nội bộ tốt hơn đến một mức nhất định. Nếu vượt khả năng xử lý, thời gian chờ và latency có thể tăng mạnh.

Queue depth thấp không tự động là tốt nếu workload cần concurrency để đạt throughput. Queue depth cao cũng không tự động là xấu nếu thiết bị được thiết kế để xử lý nhiều request đồng thời. Cần xem throughput và latency cùng lúc.

### Định luật Little trong quan sát I/O

Ở trạng thái ổn định, có thể dùng quan hệ khái quát:

~~~text
Số yêu cầu trung bình đang tồn tại
    = tốc độ hoàn thành yêu cầu × thời gian trung bình một yêu cầu
~~~

Nếu thiết bị hoàn thành 10.000 I/O mỗi giây và thời gian trung bình là 2 ms, số yêu cầu trung bình đang tồn tại xấp xỉ 20. Đây chỉ là cách diễn giải quan hệ giữa concurrency, throughput và latency; số liệu thực tế phải đo tại cùng một lớp trong stack.

## 4. I/O ngẫu nhiên và I/O tuần tự

### Random I/O

Random I/O truy cập các block ở vị trí phân tán. Index lookup, cập nhật các dòng ở nhiều trang và truy cập heap theo row identifier có thể tạo mẫu I/O này.

SSD/NVMe thường xử lý random I/O tốt hơn HDD, nhưng random access vẫn có chi phí về latency, queueing, cache miss và metadata. Trên storage mạng, latency round trip có thể trở thành yếu tố đáng kể.

### Sequential I/O

Sequential I/O đọc hoặc ghi các block liên tiếp. Table scan, backup, restore và một số thao tác bulk thường tạo mẫu này.

Sequential I/O có thể tận dụng prefetch, read-ahead và băng thông lớn. Một hệ thống có throughput tuần tự tốt có thể hoàn thành scan nhanh dù IOPS random không quá cao.

### Cùng một truy vấn có thể tạo cả hai kiểu

Ví dụ truy vấn dùng index để tìm các row identifier, rồi truy cập các heap page nằm rải rác. Bước index scan có thể có locality tương đối tốt, nhưng heap fetch có thể random. Nếu nhiều dòng được gom theo page hoặc dùng bitmap access, hệ quản trị có thể giảm số lần đọc trang lặp lại.

Vì vậy, không thể chỉ phân loại một workload là random hoặc sequential dựa trên câu SQL. Cần xem execution plan, buffers và thống kê thiết bị.

## 5. Bố trí data files, transaction log và temp

Một nguyên tắc thiết kế thường gặp là tách các luồng I/O có đặc điểm khác nhau khi chúng đang cạnh tranh đáng kể và khi có thể cung cấp tài nguyên độc lập.

~~~text
                 Database workload
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
       Data files     Transaction log   Temp files
          |              |              |
     Random/scan      Small sync writes  Sort/hash spill
     mixed reads      Commit critical   Burst read/write
          |              |              |
          v              v              v
      Data storage    Log storage      Temp storage
~~~

### Data storage

Chứa bảng và index. Tùy workload, cần cân bằng random read, sequential scan, random write, write amplification và dung lượng.

### Log storage

Transaction log/WAL thường cần độ trễ ghi ổn định và durability. Tách log khỏi data có thể giảm cạnh tranh khi hai luồng cùng hoạt động mạnh. Tuy nhiên, lợi ích chỉ rõ khi chúng thật sự có đường I/O hoặc giới hạn tài nguyên độc lập.

### Temp storage

Temp files có thể phát sinh từ sort, hash, join, aggregate hoặc bảng tạm. Tách temp có thể giảm cạnh tranh với data/log nếu temp I/O đáng kể. Nhưng nếu temp và data cùng nằm trên một storage pool hoặc cùng giới hạn throughput, việc đặt ở thư mục khác không tạo thêm năng lực vật lý.

### Backup và archive

Backup thường đọc tuần tự lượng dữ liệu lớn và ghi ra đích khác. Nếu backup đẩy băng thông hoặc queue depth của storage chính lên cao, hãy giới hạn tốc độ, dùng snapshot phù hợp hoặc gửi backup qua một luồng/đường lưu trữ khác.

### Không đồng nghĩa với bốn thư mục là bốn thiết bị

Trong môi trường ảo hóa và cloud, nhiều volume có thể nằm trên cùng storage pool hoặc dùng chung network path. Hai mount point khác nhau không chứng minh độc lập về IOPS, throughput hoặc failure domain.

Trước khi tách dữ liệu, cần hiểu topology thực tế: thiết bị vật lý, RAID group, controller, hypervisor datastore, cloud volume, storage account, network path và quota.

## 6. Transaction log/WAL cần latency ghi ổn định

Transaction log ghi lại thông tin cần thiết để khôi phục trạng thái nhất quán sau crash. Khi ứng dụng commit, hệ quản trị phải bảo đảm log tương ứng đã đạt mức durability được cấu hình trước khi xác nhận commit, trừ khi có chế độ bất đồng bộ được chủ động chọn.

### Log nằm trên đường commit

Với synchronous durability, commit có thể chờ log flush. Nếu log storage có latency tăng hoặc bị queueing, transaction ngắn cũng có thể chậm.

Các dấu hiệu cần quan sát:

- Commit latency tăng cùng log flush latency.
- Log write queue tăng.
- Throughput log đạt giới hạn thiết bị hoặc volume.
- Wait event liên quan log flush/sync tăng.
- Replication acknowledgment kéo dài nếu commit đồng bộ với replica.

### Log thường có mẫu ghi khác data

Transaction log thường được ghi theo chuỗi LSN hoặc vị trí log tăng dần. Luồng ghi có xu hướng tuần tự hơn so với cập nhật data pages ngẫu nhiên. Vì vậy, log storage cần ưu tiên latency ổn định, write throughput và durability.

Tuy nhiên, log có thể bị cạnh tranh bởi backup log, archive, replication hoặc checkpoint tùy kiến trúc. Không nên giả định log chỉ có một writer đơn giản.

### Không tắt durability để chữa storage chậm

Tắt fsync, giảm durability hoặc thay đổi chế độ commit có thể làm benchmark trông nhanh hơn nhưng thay đổi bảo đảm phục hồi và nguy cơ mất dữ liệu. Chỉ thay đổi các cấu hình này khi yêu cầu nghiệp vụ, kiến trúc và chính sách phục hồi cho phép; không dùng chúng như một cách tối ưu chung.

## 7. Data files, buffer pool và cache

Hệ quản trị thường dùng bộ nhớ để cache data/index pages. PostgreSQL có shared buffers; InnoDB có buffer pool; SQL Server có buffer pool và memory manager.

### Cache hit và physical read

Khi trang cần thiết đã ở trong buffer pool, truy vấn có thể tránh đọc từ storage. Cache hit cao có thể giảm physical I/O, nhưng không có nghĩa storage không quan trọng: cache miss, checkpoint, scan lớn và workload mới vẫn cần I/O.

Các chỉ số cần hiểu:

- Logical reads hoặc buffer accesses.
- Buffer/cache hit ratio.
- Physical reads.
- Read-ahead/prefetch.
- Dirty pages và writeback/checkpoint.
- Page eviction và memory pressure.

Hit ratio cao không tự động chứng minh hệ thống khỏe. Một truy vấn có thể đọc hàng triệu buffer đã cache nhưng vẫn tốn CPU và memory bandwidth. Hãy kết hợp số buffer được truy cập với thời gian và số dòng trả về.

### Database buffer pool và OS page cache

Cách sử dụng OS page cache khác nhau giữa engine và cấu hình. Một số hệ quản trị dựa nhiều vào buffer pool riêng; một số chế độ I/O có thể bypass hoặc giảm vai trò của page cache. Cần hiểu engine đang dùng buffered I/O, direct I/O hay cơ chế tương đương.

Không nên cộng đơn giản bộ nhớ database cache với OS cache nếu chúng có thể chứa cùng dữ liệu. Cũng không nên thay đổi cấu hình page cache hoặc direct I/O mà không đo tác động.

### Hot data và cold data

Dữ liệu được truy cập thường xuyên nên có cơ hội nằm trong cache; dữ liệu lịch sử ít truy cập có thể ở storage tier chậm hơn. Phân loại hot/cold giúp bố trí tài nguyên, nhưng cần tính đến truy vấn đột xuất, báo cáo cuối kỳ và backfill.

## 8. Checkpoint và ghi data pages

Data pages thường được ghi xuống storage theo cơ chế checkpoint hoặc background writer. Transaction log/WAL cho phép phục hồi thay đổi chưa được ghi đầy đủ vào data files sau crash, theo quy tắc của engine.

### Vì sao checkpoint quan trọng?

Checkpoint giúp giới hạn lượng log cần replay khi recovery và thúc đẩy dirty pages được ghi xuống data storage. Nếu checkpoint quá dồn dập, hệ thống có thể tạo write burst, làm data I/O tăng và ảnh hưởng truy vấn. Nếu checkpoint quá thưa, recovery có thể cần replay nhiều log hơn và log storage có thể tăng.

### Write burst và checkpoint smoothing

Một số engine phân tán công việc checkpoint trong một khoảng thời gian thay vì ghi tất cả dirty pages trong thời gian rất ngắn. Cấu hình checkpoint có thể ảnh hưởng đến:

- Tần suất checkpoint.
- Lượng WAL/log được sinh ra giữa các checkpoint.
- Tốc độ ghi data pages.
- Recovery time.
- Storage write throughput và latency.

Không điều chỉnh checkpoint chỉ để giảm một chỉ số riêng lẻ. Hãy xem write latency, checkpoint frequency, log generation, recovery objective và khả năng storage.

### PostgreSQL

PostgreSQL dùng WAL để bảo đảm durability và phục hồi. Checkpoint ghi các dirty data pages cần thiết xuống data files; WAL phải được flush trước các data page tương ứng theo write-ahead logging rule.

Các tham số như checkpoint_timeout, max_wal_size và checkpoint_completion_target ảnh hưởng lịch và phân bố checkpoint theo phiên bản. Tăng max_wal_size có thể làm checkpoint ít thường xuyên hơn nhưng cần dung lượng WAL và có thể tăng lượng log cần replay. Không áp dụng giá trị chung cho mọi workload.

Có thể quan sát checkpoint và WAL qua các thống kê hệ thống tương ứng với phiên bản, ví dụ pg_stat_bgwriter, pg_stat_wal hoặc các view I/O mới hơn.

### MySQL InnoDB

InnoDB dùng redo log và dirty page flushing. Checkpoint tiến lên khi các dirty pages được ghi xuống data files và redo log cũ có thể được tái sử dụng theo cơ chế engine. Nếu dirty page flushing không theo kịp, checkpoint age và áp lực redo có thể tăng.

Theo dõi redo log capacity, dirty pages, flush rates và các trạng thái InnoDB phù hợp với phiên bản. Thay đổi redo capacity hoặc flushing behavior cần benchmark cả crash recovery và workload ghi.

### SQL Server

SQL Server transaction log và checkpoint phối hợp để bảo đảm recovery. Checkpoint ghi dirty pages từ buffer pool xuống data files và tạo điểm phục hồi phù hợp. Database recovery model, log backup và log truncation ảnh hưởng dung lượng transaction log.

Theo dõi checkpoint activity, log flush waits, log growth, VLF và file I/O statistics. Cần phân biệt transaction log đầy do backup/truncation, transaction dài hay storage chậm; tăng kích thước file đơn thuần không xử lý mọi nguyên nhân.

## 9. Vùng tạm và temp spill

Sort, hash join, hash aggregate, DISTINCT, materialization và một số thao tác khác có thể cần lưu dữ liệu trung gian. Nếu dữ liệu không vừa bộ nhớ được cấp, hệ quản trị có thể ghi một phần xuống temp storage.

### Các nguyên nhân thường gặp

- Sort hàng triệu dòng trước ORDER BY hoặc merge join.
- Hash join có build side quá lớn hoặc memory grant không đủ.
- Hash aggregate có quá nhiều nhóm.
- DISTINCT hoặc GROUP BY cần cấu trúc trung gian lớn.
- Truy vấn tạo temporary table.
- Window function cần sắp xếp theo partition/order.
- Kế hoạch ước lượng sai cardinality dẫn đến cấp phát bộ nhớ không phù hợp.

### Temp spill có thể tạo I/O lớn

Một truy vấn có thể đọc bảng đầu vào một lần nhưng ghi và đọc dữ liệu trung gian nhiều lần. Temp I/O làm tăng latency, throughput storage và queue depth. Nếu temp nằm chung thiết bị với data/log, nó có thể làm các luồng khác chậm theo.

### Phân biệt temp spill và temp table chủ động

Temp table được ứng dụng tạo ra có thể là một phần thiết kế truy vấn. Temp spill là hệ quả của operator không thể giữ toàn bộ dữ liệu trung gian trong bộ nhớ. Cả hai có thể dùng cùng một vùng lưu trữ tùy engine, nhưng cách điều tra và biện pháp tối ưu khác nhau.

### Giảm temp I/O từ nguyên nhân gốc

Có thể xem xét:

- Giảm số dòng đầu vào bằng filter đúng và đẩy điều kiện lọc sớm khi ngữ nghĩa cho phép.
- Sửa cardinality estimation bằng thống kê phù hợp.
- Thiết kế index để cung cấp thứ tự và tránh Sort nếu tổng chi phí tốt hơn.
- Giảm độ rộng dòng trung gian bằng cách chỉ chọn cột cần thiết.
- Điều chỉnh memory grant hoặc work memory có kiểm soát.
- Chia truy vấn hoặc materialize có chủ đích khi có lợi.
- Tách temp storage nếu temp I/O đang cạnh tranh đáng kể và có tài nguyên độc lập.

Không phải mọi Sort hoặc Hash đều cần loại bỏ. Một operator dùng bộ nhớ nhưng không spill có thể là lựa chọn rẻ hơn so với nhiều index lookup.

## 10. Bố trí temp storage theo workload

Temp storage thường cần dung lượng dự phòng và throughput đủ cho các truy vấn phân tích, nhưng không nên để temp chiếm toàn bộ tài nguyên lưu trữ.

### Tách temp khỏi data/log khi nào?

Có thể cân nhắc khi:

- Temp read/write chiếm tỷ trọng lớn trong I/O.
- Sort/hash spill trùng thời điểm với workload OLTP.
- Data/log latency tăng tương quan với temp activity.
- Có volume hoặc thiết bị độc lập thực sự để đặt temp.
- Chi phí storage và vận hành thấp hơn lợi ích đo được.

Không cần tách nếu temp I/O không đáng kể, storage pool đã phân bổ QoS độc lập hoặc việc tách chỉ tạo thêm mount point trên cùng tài nguyên.

### Dung lượng temp

Temp cần đủ chỗ cho các truy vấn đồng thời và đợt spill lớn. Nếu temp đầy, truy vấn có thể lỗi hoặc hệ thống mất khả năng thực hiện các thao tác cần vùng tạm.

Không dự báo dung lượng chỉ bằng một truy vấn đơn lẻ. Hãy xem số truy vấn đồng thời, kích thước input, số operator spill và thời gian temp files tồn tại.

### Giới hạn và giám sát

Nên theo dõi:

- Temp space used và free.
- Temp file creation rate.
- Temp read/write bytes.
- Số truy vấn spill.
- Dung lượng tối đa trong giờ cao điểm.
- Query/session nào tạo temp nhiều nhất.
- Thời gian tồn tại và cleanup của temporary objects.

Có thể đặt quota hoặc giới hạn theo database/user/session nếu engine hỗ trợ, nhưng cần bảo đảm giới hạn không làm các truy vấn hợp lệ thất bại bất ngờ.

## 11. Tablespace, filegroup và storage pool

Tablespace hoặc filegroup là cơ chế logic để đặt các database object vào nhóm file hoặc vị trí lưu trữ nhất định. Chúng hữu ích để tổ chức dữ liệu, áp dụng chính sách backup, phân quyền, di chuyển và bố trí storage.

### Tablespace không tự tạo hiệu năng

Tạo hai tablespace ở hai thư mục khác nhau không bảo đảm I/O độc lập. Nếu hai thư mục cùng nằm trên một volume hoặc cùng storage pool, chúng vẫn chia sẻ băng thông và queue.

Cần xác minh mapping:

~~~text
Database object
      |
      v
Tablespace / Filegroup
      |
      v
File path / Volume
      |
      v
Storage pool / Controller / Network
      |
      v
Physical device or cloud service
~~~

### PostgreSQL tablespace

PostgreSQL tablespace cho phép đặt relation files ở các vị trí filesystem khác nhau. Có thể dùng tablespace để tổ chức dữ liệu/index hoặc đặt một nhóm object lên storage tier phù hợp. Tuy nhiên, WAL có vị trí và cơ chế riêng, không đơn giản chuyển WAL vào một tablespace.

Khi dùng tablespace, cần quản lý mount point, quyền truy cập, backup/restore, đường dẫn trên mọi node liên quan và khả năng khôi phục. Nếu mount bị mất, database có thể không truy cập được các relation đặt tại đó.

### SQL Server filegroup

SQL Server dùng filegroup để nhóm data files. Có thể đặt các filegroup trên storage tier khác nhau, tổ chức partition scheme hoặc áp dụng backup theo file/filegroup trong những kịch bản phù hợp. Transaction log được quản lý bằng log file riêng, không thuộc filegroup data.

### MySQL InnoDB

InnoDB quản lý tablespace như system tablespace, file-per-table tablespace, general tablespace và temporary tablespace tùy cấu hình. Cách đặt file và di chuyển object phụ thuộc engine/version. Không suy diễn rằng MySQL có cùng mô hình tablespace hoặc khả năng tách log/temp như PostgreSQL/SQL Server.

## 12. Ví dụ bố trí theo ba kiểu workload

### Trường hợp A: OLTP giao dịch nhỏ, commit thường xuyên

Đặc điểm:

- Nhiều transaction ngắn.
- Nhiều index lookup.
- Commit latency ảnh hưởng trực tiếp request.
- Data pages được cập nhật phân tán.
- Temp spill ít.

Ưu tiên:

- Storage log có latency ghi ổn định và durability phù hợp.
- Data storage có random I/O tốt.
- Buffer pool đủ cho tập dữ liệu nóng.
- Theo dõi log flush waits, data read latency và hot page contention.
- Tránh backup hoặc scan lớn cạnh tranh giờ cao điểm.

Nếu có volume độc lập, tách log khỏi data có thể giảm cạnh tranh. Cần đo trước và sau trên cùng tải.

### Trường hợp B: OLAP, báo cáo và tổng hợp lớn

Đặc điểm:

- Scan nhiều trang.
- Sort/hash lớn.
- Temp spill có thể đáng kể.
- Throughput tuần tự quan trọng.
- Một số truy vấn kéo dài.

Ưu tiên:

- Data storage có throughput tuần tự tốt.
- Temp storage đủ dung lượng và băng thông.
- Memory grant/work memory phù hợp với concurrency.
- Có thể dùng read replica hoặc warehouse để tách workload.
- Lên lịch báo cáo/backup nặng hoặc giới hạn resource group.

### Trường hợp C: Hệ thống hỗn hợp OLTP + ETL

Đặc điểm:

- OLTP cần latency ổn định.
- ETL tạo bulk read/write và log.
- Backup/checkpoint có thể trùng với batch load.
- Replica cần theo kịp log.

Ưu tiên:

- Xác định cửa sổ ETL và giới hạn tốc độ.
- Theo dõi log generation, checkpoint, replication lag và data I/O.
- Cân nhắc staging storage cho dữ liệu nạp lớn.
- Tách temp nếu ETL tạo spill đáng kể.
- Không chạy backup, index rebuild và bulk load đồng thời nếu chúng cùng bão hòa một storage pool.

## 13. Thiết bị lưu trữ và đặc tính nền tảng

### HDD

HDD có chi phí dung lượng thấp và có thể cung cấp throughput tuần tự tốt khi đọc/ghi liên tục, nhưng random I/O có latency cao do cơ chế cơ học. Thường phù hợp với archive, backup hoặc dữ liệu ít truy cập hơn là đường commit nhạy latency.

### SSD SATA

SSD SATA có latency và random I/O tốt hơn HDD, nhưng bị giới hạn bởi giao tiếp SATA và đặc tính controller. Phù hợp với nhiều workload database vừa phải tùy yêu cầu.

### NVMe SSD

NVMe thường cung cấp latency thấp, queue concurrency cao và throughput tốt. Tuy nhiên, hiệu năng phụ thuộc loại thiết bị, endurance, firmware, thermal throttling và giới hạn nền tảng. Không phải NVMe nào cũng có durability hoặc hiệu năng ghi bền như nhau.

### Network block storage và cloud volumes

Cloud volume thường có giới hạn IOPS, throughput, dung lượng và burst credit tùy loại dịch vụ. Một volume có thể đạt hiệu năng tối đa chỉ khi được provision đủ dung lượng hoặc mức IOPS tương ứng. Nhiều volume gắn vào cùng instance vẫn có thể bị giới hạn bởi network bandwidth hoặc instance-level cap.

Cần kiểm tra:

- Provisioned IOPS và throughput.
- Latency p95/p99.
- Burst balance hoặc credit nếu có.
- Queue length và throttling.
- Giới hạn instance, volume và storage account.
- Durability, replication và failure domain.
- Snapshot/backup traffic có chia sẻ băng thông không.

Không dựa vào thông số tối đa trong bảng sản phẩm mà bỏ qua giới hạn thực tế của instance và storage path.

### RAID và controller cache

RAID có thể tăng throughput, IOPS hoặc khả năng chịu lỗi tùy mức RAID, số ổ, controller và workload. Write cache của controller có thể cải thiện hiệu năng nếu có bảo vệ mất điện phù hợp. Cache không được bảo vệ có thể gây mất dữ liệu khi sự cố nguồn hoặc thiết bị.

Cần hiểu chính sách write-through/write-back, battery/flash-backed cache, rebuild behavior và ảnh hưởng khi một thành viên RAID lỗi. RAID không thay thế backup.

## 14. Dung lượng, tăng trưởng và headroom

Storage cần đủ dung lượng cho dữ liệu hiện tại, tăng trưởng, index, log, temp, backup và hoạt động bảo trì.

Một cách ước lượng sơ bộ:

~~~text
Dung lượng cần thiết
  = data files
  + index files
  + transaction log/WAL
  + temp headroom
  + backup/archive theo retention
  + khoảng trống cho tăng trưởng và bảo trì
~~~

Các thành phần có thể nằm trên storage khác nhau, nên không nhất thiết cộng tất cả vào một volume. Mục tiêu là bảo đảm mỗi resource có headroom phù hợp.

### Vì sao không nên chạy storage gần đầy?

Khi filesystem hoặc volume gần đầy:

- Database có thể không mở rộng data/log/temp file.
- Checkpoint hoặc log generation có thể thất bại.
- Temp query có thể lỗi giữa chừng.
- Backup hoặc restore không có chỗ ghi.
- Rebuild index hoặc maintenance cần dung lượng tạm có thể không chạy được.
- Một số filesystem và storage layer có thể giảm hiệu năng khi gần hết dung lượng.

Đặt cảnh báo theo cả dung lượng tuyệt đối, tốc độ tăng và thời gian dự kiến đến khi đầy. Một volume còn 20% free có thể vẫn nguy hiểm nếu tốc độ tăng đủ nhanh để lấp đầy trước khi nhóm vận hành xử lý.

### File growth và preallocation

Autogrowth tiện lợi nhưng nếu file tăng nhiều lần trong giờ cao điểm, thao tác mở rộng có thể gây pause hoặc phân mảnh tùy engine/filesystem. Pre-size file theo tăng trưởng dự kiến có thể giảm sự kiện growth thường xuyên.

Không cấp phát quá lớn mà không tính chi phí backup, restore, replication và khả năng sử dụng storage. Kích thước ban đầu và growth increment cần dựa trên số liệu.

### Log growth

Transaction log cần đủ chỗ cho workload bình thường, backup/truncation cadence và transaction dài. Log đầy có thể ngăn ghi mới. Tăng kích thước log chỉ giải quyết thiếu headroom ngắn hạn nếu nguyên nhân là transaction không kết thúc, log backup không chạy hoặc replica không theo kịp.

## 15. Backup, archive và dữ liệu lạnh

Backup và archive thường tạo I/O lớn nhưng có mục tiêu khác nhau.

- **Backup:** bản sao dùng để khôi phục database hoặc một phần dữ liệu.
- **Log archive:** lưu transaction log/WAL để point-in-time recovery hoặc replication.
- **Archive data:** dữ liệu lịch sử ít truy cập, được chuyển sang storage tier rẻ hơn.
- **Snapshot:** bản chụp storage hoặc database tại một thời điểm theo cơ chế nền tảng.

### Tách backup khỏi đường I/O chính

Nếu backup đọc toàn bộ data files trong giờ cao điểm, nó có thể cạnh tranh với truy vấn. Có thể:

- Lên lịch ngoài giờ cao điểm.
- Dùng backup từ replica nếu kiến trúc và consistency cho phép.
- Giới hạn throughput backup.
- Ghi backup ra storage đích khác.
- Dùng snapshot hoặc backup tool có cơ chế phù hợp.

Backup từ replica vẫn tiêu thụ tài nguyên trên replica và có thể ảnh hưởng query đọc hoặc replication. Cần đo thay vì giả định nó miễn phí.

### Archive và retention

Dữ liệu lạnh có thể được nén, chuyển sang object storage hoặc lưu trong bảng/partition riêng. Cần bảo đảm:

- Có thể tìm và khôi phục theo yêu cầu.
- Retention và legal hold được tuân thủ.
- Dữ liệu được mã hóa và quyền truy cập phù hợp.
- Backup của archive có chính sách rõ ràng.
- Chi phí truy xuất dữ liệu lạnh được tính vào RTO/RPO.

Không xóa dữ liệu production trước khi xác minh archive và khả năng khôi phục theo quy trình.

## 16. Filesystem, I/O scheduler và vận hành thiết bị

Database phụ thuộc cả thiết bị và lớp filesystem/OS.

Các yếu tố cần hiểu:

- Filesystem và mount options được hỗ trợ bởi vendor.
- Block size, alignment và sector size.
- I/O scheduler và cách kernel xếp hàng request.
- Direct I/O hay buffered I/O.
- TRIM/discard cho SSD.
- Multipath và failover cho SAN.
- Device mapper, LVM, RAID và virtualization layer.
- File permissions, ownership và mount persistence.

Không áp dụng một mount option hoặc scheduler từ một bài benchmark chung cho mọi hệ thống. Cấu hình sai có thể làm giảm durability, gây lỗi khôi phục hoặc khiến database không hỗ trợ.

### Direct I/O và buffered I/O

Buffered I/O dùng page cache của hệ điều hành; direct I/O có thể giảm double caching và thay đổi cách căn chỉnh/hoàn tất I/O. Engine có thể dùng cơ chế khác nhau theo platform và phiên bản.

Không bật/tắt direct I/O chỉ vì muốn tăng cache hit. Hãy xem tài liệu hệ quản trị, mức RAM, buffer pool, page cache và benchmark đại diện.

### Monitoring thiết bị

Ở tầng OS, có thể dùng công cụ như iostat, perfmon hoặc công cụ cloud monitoring để xem:

- Read/write IOPS.
- Read/write throughput.
- Average và percentile latency nếu nền tảng hỗ trợ.
- Queue depth.
- Utilization và throttling.
- Await/service time.
- Errors, retries và timeout.
- Free space và growth rate.

Các công cụ hiển thị chỉ số ở các lớp khác nhau. Ví dụ utilization 100% trên một thiết bị không nhất thiết có cùng ý nghĩa với volume cloud được cấp IOPS; cần hiểu định nghĩa của nền tảng.

## 17. Đọc dấu hiệu storage bottleneck

Không nên kết luận storage là nút thắt chỉ vì truy vấn chậm hoặc disk utilization cao. Hãy kết hợp database waits, execution plan và metrics của thiết bị.

### Dấu hiệu đọc data chậm

- Buffer miss hoặc physical read tăng.
- Read latency cao.
- Queue depth tăng cùng p95/p99 query latency.
- Scan lớn hoặc index lookup gây nhiều random read.
- CPU thấp trong khi query chờ I/O.
- Buffer cache churn cao.

Hướng điều tra:

1. Xác định query và node đọc nhiều.
2. Kiểm tra index và cardinality.
3. Xem có scan rộng hoặc random heap fetch không.
4. So sánh logical reads với physical reads.
5. Kiểm tra storage latency và queue.
6. Xem cache size, working set và concurrent scan.

### Dấu hiệu log bottleneck

- Commit latency tăng.
- Wait event log flush/sync tăng.
- Log write latency hoặc queue cao.
- Replication synchronous acknowledgment chậm.
- Transaction throughput giảm dù statement time thấp.

Hướng điều tra:

1. Đo commit latency riêng.
2. Xem WAL/log write rate.
3. Kiểm tra storage log và giới hạn IOPS/throughput.
4. Kiểm tra synchronous replication.
5. Xem transaction size và group commit.
6. So sánh khi workload batch/backup chạy và khi không chạy.

### Dấu hiệu temp bottleneck

- Temp bytes read/write tăng.
- Sort/hash spill xuất hiện trong plan.
- Temp volume latency/queue tăng.
- Truy vấn có GROUP BY, ORDER BY, DISTINCT hoặc hash join chậm.
- Các truy vấn khác cùng chậm khi báo cáo lớn chạy.

Hướng điều tra:

1. Xác định query tạo temp.
2. Xem estimated/actual rows và memory grant.
3. Giảm input rows hoặc row width nếu có thể.
4. Cải thiện thống kê/index/order.
5. Điều chỉnh memory có kiểm soát.
6. Cân nhắc tách temp storage nếu có tài nguyên độc lập.

### Dấu hiệu checkpoint hoặc writeback bottleneck

- Data write latency tăng theo chu kỳ.
- Checkpoint hoặc dirty page flushing tạo burst.
- WAL/log generation vượt tốc độ data flush.
- Write queue tăng và p99 giao dịch ghi xấu đi.

Cần xem checkpoint frequency, dirty page count, storage throughput, log capacity và workload đồng thời. Tăng log size có thể giảm checkpoint frequency nhưng không thay thế việc bảo đảm data storage có thể ghi bền vững.

## 18. Chỉ số theo hệ quản trị

Tên view và counter thay đổi theo phiên bản, nhưng có thể bắt đầu từ các nhóm sau.

### PostgreSQL

Các nguồn quan sát thường dùng:

- **pg_stat_activity:** trạng thái session, query và wait events.
- **pg_locks:** khóa và quan hệ chờ.
- **pg_stat_io** ở các phiên bản hỗ trợ: thống kê I/O theo backend/object/context.
- **pg_stat_bgwriter** và các thống kê checkpoint liên quan: hoạt động background writer/checkpoint theo phiên bản.
- **pg_stat_wal:** thống kê WAL generation và write/sync.
- **pg_stat_database:** số liệu database-level như block read/hit và temp files/bytes.
- **EXPLAIN (ANALYZE, BUFFERS):** số liệu truy cập buffer của truy vấn.

Ví dụ xem các cột tổng quan database:

~~~sql
SELECT
    datname,
    blks_read,
    blks_hit,
    temp_files,
    temp_bytes
FROM pg_stat_database
WHERE datname = current_database();
~~~

Đây là counter tích lũy từ lần reset thống kê gần nhất; cần lấy hai mẫu theo thời gian để tính tốc độ thay đổi. Không dùng một giá trị tổng tích lũy để kết luận workload hiện tại.

### MySQL InnoDB

Có thể bắt đầu với:

- **SHOW ENGINE INNODB STATUS:** trạng thái InnoDB, deadlock, buffer pool và I/O.
- **Performance Schema:** file I/O, waits, lock waits và statement metrics.
- **sys schema:** các view tổng hợp dễ đọc hơn.
- InnoDB buffer pool statistics.
- Redo log, checkpoint age và dirty page metrics theo phiên bản.
- Temporary table và sort metrics.

Cần phân biệt counter toàn server với counter theo session hoặc statement. Nếu có thể, liên kết query digest với file I/O và wait events.

### SQL Server

Có thể xem:

- **sys.dm_io_virtual_file_stats:** số liệu I/O theo database file.
- Wait statistics như **PAGEIOLATCH**, **WRITELOG** và các wait liên quan tempdb.
- **sys.dm_db_file_space_usage** và thông tin tempdb.
- Buffer cache và memory grants.
- Extended Events cho file I/O, spill, deadlock hoặc wait.
- Actual execution plan với sort/hash spill warnings.

Các DMV thường là counter tích lũy từ thời điểm khởi động hoặc reset; hãy lấy delta theo khoảng thời gian. Không so sánh trực tiếp hai server nếu thời gian uptime hoặc workload khác nhau.

## 19. Ví dụ phân tích một hệ thống OLTP có báo cáo

Một hệ thống quản lý đơn hàng chạy trên một storage pool. Trong giờ cao điểm:

- API ghi đơn có commit latency tăng từ 8 ms lên 70 ms.
- Truy vấn danh sách đơn cũng chậm.
- Một báo cáo tổng hợp theo ngày chạy trong cùng thời điểm.
- Execution plan báo cáo có HashAggregate và Sort spill.
- Storage metrics cho thấy temp write throughput và queue depth tăng.
- Log flush latency cũng tăng nhưng log volume không thay đổi nhiều.

### Giả thuyết

Báo cáo tạo temp I/O lớn và cạnh tranh storage bandwidth/queue với data và log. Log flush chậm có thể là hệ quả của contention trên storage pool, không nhất thiết log volume tăng.

### Cách kiểm chứng

1. Thu thập cùng mốc thời gian: query latency, temp bytes, log flush latency, data I/O và queue.
2. Chạy báo cáo riêng trong môi trường thử nghiệm để xác định temp footprint.
3. Kiểm tra cardinality và memory grant; xác định vì sao spill xảy ra.
4. Thử cải thiện query/index hoặc memory grant có kiểm soát.
5. Thử đặt temp trên volume có tài nguyên độc lập nếu nền tảng hỗ trợ.
6. Chạy lại workload hỗn hợp và so sánh p95/p99 của API cùng báo cáo.
7. Đo chi phí và failure mode của storage layout mới.

Nếu tách temp giúp báo cáo không còn làm log/data latency tăng, giả thuyết được củng cố. Nếu cả ba volume vẫn chia sẻ cùng giới hạn backend, việc tách thư mục có thể không cải thiện.

## 20. Quy trình thiết kế bố trí storage

Một quy trình có thể áp dụng:

1. **Phân loại workload:** OLTP, OLAP, ETL, backup, replication và retention.
2. **Phân loại I/O:** random read/write, sequential scan, synchronous log write, temp spill và backup stream.
3. **Đo baseline:** latency, IOPS, throughput, queue depth, CPU, memory và waits.
4. **Lập bản đồ storage:** database file, log, temp, backup đang nằm trên volume, pool và thiết bị nào.
5. **Xác định contention:** tìm luồng I/O nào cạnh tranh và tại thời điểm nào.
6. **Xác định mục tiêu:** latency commit, query p95/p99, throughput scan, temp capacity, recovery time.
7. **Đề xuất bố trí:** data/log/temp/backup theo khả năng độc lập tài nguyên và failure domain.
8. **Kiểm tra durability:** xác nhận write cache, replication, backup và recovery vẫn đáp ứng yêu cầu.
9. **Benchmark từng thay đổi:** thay đổi một yếu tố hoặc một nhóm có thể cô lập.
10. **Chạy workload hỗn hợp:** không chỉ đo từng loại tải riêng.
11. **Thử tình huống cao điểm:** backup, checkpoint, ETL và query đồng thời.
12. **Ghi lại baseline và vận hành:** dashboard, cảnh báo, dung lượng và kế hoạch tăng trưởng.

### Thay đổi một yếu tố có thể đo

Nếu cùng lúc chuyển log, temp, thay memory, đổi checkpoint và thêm index, rất khó xác định thay đổi nào tạo ra lợi ích. Khi có thể, thay từng yếu tố hoặc thiết kế thí nghiệm có nhóm đối chứng.

## 21. Benchmark storage phù hợp

Benchmark cần mô phỏng kích thước I/O, tỷ lệ đọc/ghi, queue depth, concurrency và durability tương tự database.

### Không chỉ chạy sequential throughput test

Một bài test ghi tuần tự lớn có thể đạt MB/s cao nhưng không mô phỏng commit nhỏ đồng bộ. Ngược lại, random 4 KB test không mô phỏng backup hoặc table scan.

Cần tạo các profile riêng:

| Profile | Mẫu I/O cần mô phỏng | Mục tiêu |
|---|---|---|
| Transaction log | Ghi tuần tự nhỏ, đồng bộ, latency nhạy | Commit latency |
| OLTP data | Random read/write, block nhỏ, concurrency | IOPS và latency |
| Analytics scan | Sequential read, block lớn | Throughput |
| Temp spill | Mixed read/write, file lớn, burst | Temp latency/throughput |
| Backup | Sequential read source và write destination | Thời gian backup, cạnh tranh |
| Restore | Sequential write/redo và random access sau đó | RTO và recovery |

### Kiểm soát điều kiện thử nghiệm

- Dùng cùng dữ liệu, query mix và concurrency.
- Đo cả warm-cache và cold/controlled-cache khi phù hợp.
- Không chạy benchmark ghi phá hủy trên volume production.
- Dành đủ thời gian để quan sát trạng thái ổn định, không chỉ burst ngắn.
- Ghi latency percentiles, IOPS, MB/s và queue depth.
- Kiểm tra throttling, burst credits và giới hạn instance.
- Đo khi workload hỗn hợp hoạt động.
- Thực hiện backup/restore test để xác nhận recovery.

### Đánh giá durability

Một benchmark ghi nhanh bằng cách bỏ qua flush hoặc dùng cache không được bảo vệ có thể không phản ánh khả năng ghi bền vững. Phải dùng cấu hình durability tương đương production và xác minh storage/controller cache có bảo vệ phù hợp.

## 22. Dung lượng và cảnh báo vận hành

Một dashboard storage nên theo dõi riêng từng nhóm file hoặc volume.

Các cảnh báo hữu ích:

- Free space dưới ngưỡng và thời gian dự kiến đến khi đầy.
- Data/log/temp growth bất thường.
- IOPS hoặc throughput chạm quota.
- Latency p95/p99 tăng kéo dài.
- Queue depth tăng cùng latency.
- Cloud burst credit giảm hoặc volume throttling.
- Temp space gần đầy.
- Transaction log/WAL tăng nhanh hoặc không được truncation/archive.
- Checkpoint backlog hoặc dirty pages tăng.
- Replication lag tăng.
- Backup duration vượt cửa sổ.
- Storage errors, timeout hoặc retry.

Cảnh báo nên kết hợp ngưỡng và xu hướng. Ví dụ, volume còn 30% free nhưng tăng 5% mỗi giờ có thể cần xử lý sớm hơn volume còn 10% nhưng gần như không tăng.

## 23. Những sai lầm thường gặp

- **Tách thư mục nhưng dùng chung storage pool:** không tạo được tài nguyên I/O độc lập.
- **Chỉ nhìn MB/s:** bỏ qua latency và IOPS của log hoặc OLTP.
- **Chỉ nhìn IOPS:** bỏ qua kích thước block, throughput và queueing.
- **Dùng một benchmark cho mọi file:** log, data, temp và backup có mẫu I/O khác nhau.
- **Đặt log trên storage nhanh nhưng không bảo đảm durability:** cache không bảo vệ có thể gây mất dữ liệu khi sự cố.
- **Để temp và data cạnh tranh không giám sát:** spill lớn có thể làm truy vấn OLTP chậm.
- **Tăng memory chỉ để tránh spill:** có thể gây memory pressure khi nhiều query đồng thời.
- **Tăng log size mà không tìm nguyên nhân:** transaction dài hoặc replication lag vẫn có thể làm log đầy.
- **Chạy backup, ETL và index rebuild cùng giờ cao điểm:** tạo I/O burst cạnh tranh.
- **Bỏ qua checkpoint:** write burst có thể làm latency tăng theo chu kỳ.
- **Chỉ xem cache hit ratio:** logical reads lớn vẫn tốn CPU và memory bandwidth.
- **Coi RAID là backup:** RAID không bảo vệ khỏi xóa nhầm, lỗi logic hoặc thảm họa site.
- **Không tính temp và backup vào capacity planning:** volume có thể đầy trong workload cao điểm.
- **So sánh volume cloud chỉ bằng thông số quảng cáo:** bỏ qua giới hạn instance, network và quota.
- **Thay nhiều cấu hình cùng lúc:** không xác định được nguyên nhân cải thiện hoặc suy giảm.

## 24. Checklist bố trí dữ liệu, log và temp

Trước khi triển khai hoặc thay đổi storage layout, hãy trả lời:

1. Workload chính là OLTP, OLAP, ETL hay hỗn hợp?
2. Data, index, log, temp, backup và archive hiện nằm trên volume/storage pool nào?
3. Những luồng I/O nào là random, sequential hoặc synchronous?
4. Latency p50/p95/p99, IOPS, throughput và queue depth hiện tại ra sao?
5. Commit latency có tương quan với log flush latency không?
6. Truy vấn nào tạo temp spill và lượng temp I/O là bao nhiêu?
7. Data scan, backup hoặc checkpoint có cạnh tranh với log không?
8. Các volume được tách có thật sự độc lập về thiết bị, pool và network path không?
9. Buffer pool/cache hit, physical reads và working set có được đo không?
10. Checkpoint và log generation có cân bằng với data write throughput không?
11. Dung lượng data/log/temp/backup có headroom và cảnh báo tăng trưởng không?
12. Durability, replication, backup và recovery có được giữ đúng yêu cầu không?
13. Benchmark có mô phỏng I/O pattern và concurrency thực tế không?
14. Đã đo workload hỗn hợp trước và sau thay đổi chưa?
15. Có runbook xử lý volume đầy, throttling, log backlog, temp exhaustion và storage failure không?

## Kết luận

Bố trí dữ liệu, nhật ký và vùng tạm cần phản ánh đặc điểm I/O của workload. Data files phục vụ đọc/ghi bảng và index; transaction log/WAL nằm trên đường durability của commit; temp storage nhận dữ liệu trung gian khi sort/hash spill; backup và archive tạo luồng đọc/ghi lớn theo chu kỳ. Mỗi loại có yêu cầu khác nhau về latency, IOPS, throughput, queue depth, dung lượng và độ bền.

Tách data, log và temp chỉ có ích khi giảm được cạnh tranh trên tài nguyên thật sự độc lập. Tablespace hoặc thư mục riêng không tự tạo thêm I/O capacity nếu vẫn dùng chung storage pool. Hãy đo từ execution plan đến database waits và thiết bị, hiểu checkpoint/cache/temp spill, tính headroom cho tăng trưởng và phục hồi, rồi benchmark workload hỗn hợp với durability tương đương production. Bố trí tốt là bố trí giảm được bottleneck đã đo, đồng thời giữ yêu cầu an toàn dữ liệu và khả năng vận hành.
