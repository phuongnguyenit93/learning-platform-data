# Giới hạn I/O, hạn mức tăng tốc và cơ chế điều tiết của dịch vụ đám mây

Khi cơ sở dữ liệu chạy trên hạ tầng đám mây, hiệu năng lưu trữ chịu ảnh hưởng của nhiều giới hạn cùng lúc. Một volume có thể được cấp một mức IOPS và throughput nhất định, máy ảo có thể có giới hạn băng thông lưu trữ tổng, còn dịch vụ cơ sở dữ liệu được quản lý có thể áp dụng giới hạn theo service tier hoặc cấu hình instance. Một số loại lưu trữ cho phép tăng tốc tạm thời bằng credit hoặc burst; khi hạn mức này cạn, hiệu năng có thể giảm về mức cơ sở. Nếu workload vượt giới hạn ở bất kỳ lớp nào, nền tảng có thể xếp hàng hoặc điều tiết I/O.

Hiện tượng thường thấy là truy vấn ban đầu chạy nhanh rồi chậm dần, độ trễ đọc/ghi tăng, hàng đợi I/O kéo dài hoặc throughput dừng ở một mức dù ứng dụng tiếp tục gửi thêm yêu cầu. Nếu chỉ nhìn dung lượng đĩa hoặc IOPS được quảng cáo cho volume, nhóm vận hành có thể bỏ sót giới hạn ở máy ảo, service tier, loại request hoặc vùng lưu trữ tạm.

Bài học thuộc chương **Lưu trữ và tài nguyên** của module DATABASE_PERFORMANCE. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, điều tra I/O trên đám mây phải kết hợp số liệu ở database, volume, máy ảo và dịch vụ, sau đó xác định giới hạn thực sự đang chi phối workload.

## 1. Các đại lượng cơ bản của I/O

Trước khi đọc metric của nhà cung cấp, cần phân biệt các đại lượng:

| Đại lượng | Ý nghĩa | Đơn vị thường gặp |
| --- | --- | --- |
| IOPS | Số thao tác đọc/ghi hoàn tất trong một giây | operations/second |
| Throughput | Lượng dữ liệu đọc/ghi trong một giây | MB/s, MiB/s, GB/s |
| Latency | Thời gian hoàn thành một thao tác I/O | microsecond, millisecond |
| Queue depth | Số yêu cầu I/O đang chờ hoặc đang được xử lý | số request |
| I/O size | Kích thước dữ liệu của mỗi thao tác | KiB, MiB |
| Read/write mix | Tỷ lệ thao tác đọc và ghi | phần trăm |

IOPS và throughput liên hệ với kích thước I/O:

\[
\text{Throughput} \approx \text{IOPS} \times \text{Average I/O size}
\]

Và:

\[
\text{IOPS} \approx \frac{\text{Throughput}}{\text{Average I/O size}}
\]

Các công thức này là quan hệ gần đúng khi đo cùng một tập request và cùng cách quy đổi đơn vị. Chúng giúp hiểu vì sao hai workload có IOPS giống nhau nhưng throughput khác nhau.

### Ví dụ kích thước I/O

Nếu hệ thống thực hiện 12.000 I/O mỗi giây, mỗi I/O trung bình 8 KiB:

\[
12.000 \times 8\text{ KiB} = 96.000\text{ KiB/s}
\]

Tương đương khoảng 93,75 MiB/s. Nếu mỗi thao tác có kích thước 256 KiB và vẫn thực hiện 5.000 IOPS:

\[
5.000 \times 256\text{ KiB} = 1.280.000\text{ KiB/s}
\]

Tương đương khoảng 1.250 MiB/s. Đây là lý do workload OLTP với nhiều I/O nhỏ thường bị giới hạn bởi IOPS, trong khi quét tuần tự, backup hoặc ETL có thể chạm giới hạn throughput trước.

### Latency và queue depth

Latency phản ánh thời gian một request phải chờ để hoàn tất. Khi thiết bị hoặc dịch vụ lưu trữ gần bão hòa, request mới có thể phải xếp hàng, khiến latency tăng nhanh.

Trong trạng thái ổn định và khi queue đang được sử dụng, có thể dùng quan hệ gần đúng:

\[
\text{Outstanding I/O} \approx \text{IOPS} \times \text{Average latency (seconds)}
\]

Ví dụ, để duy trì 8.000 IOPS ở latency trung bình 2 ms, hệ thống cần khoảng:

\[
8.000 \times 0,002 = 16
\]

request đang outstanding. Đây là cách ước lượng concurrency I/O, không phải chỉ tiêu queue depth tối ưu cho mọi workload. Queue sâu hơn có thể tăng throughput ở một số thiết bị nhưng cũng có thể làm latency xấu đi.

## 2. Các lớp giới hạn I/O trong hạ tầng đám mây

Một yêu cầu đọc hoặc ghi của database đi qua nhiều lớp. Mỗi lớp có thể có giới hạn riêng:

1. **Database engine:** số worker, số request đồng thời, log writer, checkpoint, buffer pool và cơ chế flush.
2. **Dịch vụ cơ sở dữ liệu:** service tier, compute size, giới hạn data I/O, log I/O hoặc throughput do nền tảng quy định.
3. **Máy ảo hoặc instance:** băng thông lưu trữ tổng, IOPS tổng, giới hạn theo số vCPU hoặc loại instance.
4. **Volume hoặc disk:** IOPS, throughput, kích thước I/O tối đa và chính sách burst.
5. **Lớp lưu trữ hoặc mạng:** giới hạn nội bộ, tuyến truy cập, vùng sẵn sàng và chính sách của dịch vụ.
6. **Quota và tài khoản:** giới hạn số volume, tổng dung lượng, số IOPS có thể provision hoặc giới hạn API quản trị.

Hiệu năng hữu dụng thường bị chi phối bởi giới hạn thấp nhất trên đường đi:

\[
\text{Effective I/O capacity} \leq \min(C_1, C_2, \ldots, C_n)
\]

Trong đó mỗi \(C_i\) là giới hạn áp dụng cho đúng loại I/O và đơn vị đo. Không phải mọi giới hạn đều có cùng đơn vị hoặc có thể so sánh trực tiếp; cần quy đổi và xác định chúng áp dụng cho volume, instance, database hay tài khoản.

### Giới hạn theo volume

Volume có thể được cấp mức IOPS và throughput riêng. Một volume lớn hơn có thể có hiệu năng cao hơn nếu chính sách của loại disk gắn hiệu năng với dung lượng. Một số loại cho phép provision IOPS hoặc throughput độc lập với dung lượng trong phạm vi cấu hình.

### Giới hạn theo instance

Ngay cả khi volume có khả năng cung cấp nhiều IOPS, máy ảo gắn volume có thể không truyền được toàn bộ lưu lượng đó. Instance có thể có mức tối đa tổng hợp cho tất cả volume, giới hạn theo chiều đọc/ghi hoặc giới hạn băng thông. Nhiều volume cùng gắn vào một instance vẫn chia sẻ giới hạn tổng này.

### Giới hạn theo service tier

Managed database thường gắn hiệu năng với compute tier, storage tier hoặc một cấu hình dịch vụ. Có thể có giới hạn riêng cho data I/O, transaction log, temporary storage hoặc tổng băng thông. Tăng dung lượng storage không nhất thiết tăng giới hạn I/O của service tier.

### Quota quản trị và giới hạn runtime

Quota cho phép tạo tài nguyên hoặc provision hiệu năng là giới hạn quản trị. Throttling là hành vi điều tiết request khi tài nguyên đang chạy chạm một giới hạn runtime. Tăng quota tài khoản không tự động tăng IOPS của một volume hoặc instance hiện có; phải kiểm tra loại giới hạn nào đang bị chạm.

## 3. Burst và hạn mức tăng tốc hoạt động thế nào?

Burst cho phép một tài nguyên vượt mức hiệu năng cơ sở trong thời gian có điều kiện. Cơ chế cụ thể tùy loại disk và nhà cung cấp. Hai mô hình phổ biến là credit-based burst và burst được cấp theo cấu hình hoặc nhu cầu.

### 3.1. Credit-based burst

Trong mô hình credit, tài nguyên có một mức hiệu năng cơ sở. Khi workload sử dụng thấp hơn mức cơ sở, hệ thống có thể tích lũy credit. Khi workload vượt mức cơ sở, tài nguyên tiêu thụ credit để đạt hiệu năng cao hơn. Khi credit cạn, hiệu năng quay về mức cơ sở hoặc mức giới hạn thấp hơn được định nghĩa.

~~~text
Hiệu năng
  ^
  |        Burst capacity
  |  ------------------------------
  |  |                            |
  |  |   Credit còn đủ             | Credit cạn
  |  |   I/O được tăng tốc         | trở về baseline
  |  |                            |
  |--+----------------------------+----------> Thời gian
       Credit giảm dần khi tải cao
~~~

Điểm cần nhớ:

- Credit không phải năng lực duy trì vô hạn.
- Thời gian burst phụ thuộc số credit có sẵn và mức tiêu thụ vượt baseline.
- Workload chạy lâu ở mức cao có thể làm credit cạn.
- Sau khi cạn, latency có thể tăng và throughput giảm dù cấu hình volume không thay đổi.
- Một khoảng tải thấp có thể giúp phục hồi credit nếu loại tài nguyên đó tích lũy credit khi không dùng hết baseline.

### 3.2. Burst theo cấu hình hoặc on-demand

Một số nền tảng cho phép cấu hình mức burst, trả phí cho hiệu năng vượt baseline hoặc sử dụng cơ chế tăng tốc không dựa trên credit tích lũy theo cùng cách. Trong trường hợp này, cần kiểm tra giới hạn thời gian, giá, mức tối đa và điều kiện áp dụng. Không được giả định mọi dịch vụ có một bucket credit.

### 3.3. Burst không phải baseline

Burst phù hợp với workload có đỉnh tải ngắn, ví dụ:

- Khởi động dịch vụ sau thời gian ít hoạt động.
- Báo cáo chạy theo lịch trong thời gian ngắn.
- Một đợt ingest hoặc đồng bộ dữ liệu có thể dự đoán.
- Checkpoint hoặc backup có đỉnh I/O ngắn.

Nếu workload cần IOPS hoặc throughput cao liên tục, cấu hình dựa vào burst sẽ tạo hiệu năng không ổn định. Cần provision mức cơ sở đủ cho tải duy trì, hoặc chọn loại storage/service tier có khả năng cung cấp hiệu năng liên tục phù hợp.

## 4. Cơ chế điều tiết (throttling)

Throttling là hành vi nền tảng giới hạn tốc độ request khi một tài nguyên đạt ngưỡng. Tùy dịch vụ, hệ thống có thể:

- Xếp request vào hàng đợi.
- Giảm tốc độ hoàn tất I/O.
- Từ chối hoặc trì hoãn một số request.
- Giới hạn throughput hoặc IOPS về mức baseline.
- Áp dụng giới hạn theo volume, instance, tenant hoặc service tier.

Trong workload database, throttling thường biểu hiện qua latency tăng, queue depth tăng và throughput không tăng dù số request gửi vào tăng. CPU database có thể vẫn thấp vì truy vấn đang chờ I/O.

### Dấu hiệu điển hình

- IOPS hoặc MB/s đạt một mức trần lặp lại.
- Read/write latency tăng mạnh khi tải tăng.
- Queue length hoặc outstanding requests tăng.
- Burst balance hoặc credit percentage giảm về gần 0.
- Chỉ số IOPS consumed hoặc bandwidth consumed đạt gần 100%.
- Metric throttled operations hoặc throttled bytes tăng nếu dịch vụ cung cấp.
- Database ghi nhận nhiều wait liên quan I/O hoặc log flush.

Một mức throughput phẳng không tự động chứng minh throttling. Có thể ứng dụng không gửi thêm request, database bị giới hạn bởi CPU, concurrency hoặc transaction serialization. Phải đối chiếu offered load, completed I/O, queue và metric của nền tảng.

## 5. I/O của database khác nhau theo loại công việc

Không nên gom mọi I/O thành một con số tổng. Các thành phần database có đặc điểm truy cập khác nhau:

| Loại I/O | Mẫu truy cập thường gặp | Tác động khi bị giới hạn |
| --- | --- | --- |
| Data file | Đọc trang ngẫu nhiên, scan tuần tự, ghi dirty page | Query đọc chậm, buffer miss, checkpoint chậm |
| Transaction log/WAL/redo | Ghi tuần tự, flush theo commit hoặc batch | Commit latency tăng, throughput ghi giảm |
| Temporary storage | Sort/hash spill, temporary table, workfile | Query lớn chậm, temp I/O tăng |
| Backup/export | Đọc tuần tự lượng dữ liệu lớn | Backup kéo dài, cạnh tranh với query |
| Replication | Đọc log, gửi và áp dụng dữ liệu | Replication lag tăng |
| Checkpoint/flush | Ghi nhiều trang bẩn trong một khoảng thời gian | I/O burst, latency ghi biến động |

Một workload OLTP có thể nhạy với latency của log flush dù throughput tổng không cao. Một báo cáo có thể nhạy với throughput đọc và temp I/O. Một hệ thống ghi hàng loạt có thể chạm giới hạn write IOPS hoặc bandwidth. Hãy xác định loại I/O đang chậm trước khi thay đổi storage.

### Logical read và physical read

Logical read thường là đọc trang đã có trong buffer cache; physical read cần lấy trang từ lớp lưu trữ hoặc cache thấp hơn. Một query có logical reads rất lớn có thể tiêu tốn CPU và bộ nhớ dù physical I/O thấp. Ngược lại, physical reads có thể bị chậm do storage latency hoặc throttling.

Vì vậy, cần xem cả số trang được truy cập, cache hit, physical reads, bytes và thời gian chờ. Tăng IOPS không sửa được một truy vấn đọc hàng triệu trang do thiếu điều kiện lọc hoặc index phù hợp.

## 6. Các kiểu hiệu năng lưu trữ trên dịch vụ đám mây

Tên SKU và chính sách thay đổi theo nhà cung cấp, region và thời điểm. Các ví dụ sau minh họa cách phân loại; trước khi triển khai cần kiểm tra tài liệu và giới hạn hiện hành của đúng loại tài nguyên.

### AWS EBS và dịch vụ database dùng EBS

EBS có các họ volume với đặc tính khác nhau. Một số loại SSD provisioned cho phép cấu hình IOPS và throughput; một số loại hiệu năng thay đổi theo dung lượng hoặc có cơ chế burst. Với volume dùng credit, metric BurstBalance có thể giúp quan sát phần credit còn lại. Các metric như VolumeReadOps, VolumeWriteOps, VolumeReadBytes, VolumeWriteBytes và VolumeQueueLength hỗ trợ phân tích hoạt động I/O.

Phải kiểm tra cả giới hạn của EBS volume lẫn băng thông EBS của EC2 instance. Nếu instance đạt giới hạn tổng, tăng IOPS volume có thể không làm throughput database tăng. Với managed database, cần xem thêm cấu hình storage, compute class và metric do dịch vụ cung cấp.

### Azure Managed Disks và Azure database services

Managed Disks có các tier với mức IOPS/throughput khác nhau; một số loại hỗ trợ bursting theo kích thước, credit hoặc cơ chế burst được cung cấp. Các metric như Disk IOPS Consumed Percentage, Disk Bandwidth Consumed Percentage và Burst Credits Percentage có thể giúp nhận diện giới hạn khi được hỗ trợ.

Máy ảo có giới hạn I/O tổng và giới hạn theo disk. Azure database services có thể hiển thị các chỉ số data I/O, log I/O hoặc giới hạn theo service objective. Cần xác định metric đang nói về disk, VM hay database service; các lớp này không thể thay thế cho nhau.

### Google Cloud Persistent Disk và dịch vụ database

Hiệu năng Persistent Disk phụ thuộc loại disk, dung lượng provision và giới hạn của VM. Một số loại có mức hiệu năng tăng theo dung lượng hoặc số vCPU trong giới hạn nhất định; một số cấu hình có cơ chế burst. VM cũng có giới hạn IOPS và throughput tổng hợp.

Theo dõi read/write operations, bytes, latency và giới hạn hiệu năng của VM cùng disk. Với managed database, xem metric và giới hạn của đúng dịch vụ thay vì suy luận trực tiếp từ thông số Persistent Disk của một VM tự quản lý.

### Không suy diễn metric giữa các nền tảng

Một metric có tên gần giống nhau có thể có cách tính, chu kỳ lấy mẫu hoặc phạm vi khác nhau. Hãy đọc định nghĩa metric, đơn vị, aggregation period và resource dimension. Không so sánh trực tiếp hai con số IOPS nếu một bên tính request ở volume, bên kia tính ở instance hoặc database service.

## 7. Cách nhận biết giới hạn đang bị chạm

Một phương pháp hiệu quả là so sánh tải được gửi vào với I/O thực tế hoàn tất và các giới hạn đã provision.

### Bước 1: xác định offered load

Đo số request database tạo ra, read/write ratio, kích thước I/O, số transaction, commit rate và số query đồng thời. Nếu ứng dụng không tạo đủ tải, không thể kết luận storage đang đạt giới hạn chỉ từ throughput thấp.

### Bước 2: xác định completed I/O

Thu thập IOPS đọc/ghi, throughput đọc/ghi, latency trung bình và percentile nếu có, queue depth, số request outstanding và thời gian chờ I/O trong database.

### Bước 3: so sánh với mọi giới hạn

Lập bảng giới hạn:

| Lớp | Giới hạn cần xác định | Số liệu đối chiếu |
| --- | --- | --- |
| Volume | IOPS và throughput tối đa/baseline/burst | IOPS, bytes/s, burst balance |
| VM/instance | IOPS và bandwidth tổng | Tổng I/O của các volume, metric instance |
| Database service | Data I/O, log I/O, storage tier hoặc service tier | Metric và quota của database |
| Workload | CPU, worker, concurrency, log flush | Query waits, CPU, transaction rate |
| Tài khoản/dịch vụ | Quota provision và policy | Quota usage, service limit |

### Bước 4: quan sát thời gian

Burst credit có thể làm hiệu năng tốt trong một khoảng đầu rồi giảm. Hãy xem chuỗi thời gian đủ dài để thấy credit depletion và thời điểm throughput chạm baseline. Một ảnh chụp tại thời điểm tải thấp có thể bỏ qua vấn đề.

### Bước 5: xác định điểm bão hòa

Tăng offered load trong môi trường kiểm thử theo từng mức. Ghi nhận thời điểm throughput ngừng tăng, latency và queue tăng, hoặc metric throttling xuất hiện. Đây là cách tìm điểm bão hòa thực tế của cấu hình.

## 8. Đo I/O từ bên trong database

Metric cloud cho biết tài nguyên lưu trữ đang hoạt động thế nào; database metric cho biết workload nào tạo ra hoạt động đó. Cần kết hợp hai phía.

### PostgreSQL

Có thể bắt đầu từ thống kê database và query:

~~~sql
SELECT
    datname,
    blks_read,
    blks_hit,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY blks_read DESC;
~~~

Nếu bật pg_stat_statements và track_io_timing phù hợp, có thể xem truy vấn có nhiều block read, block write hoặc thời gian I/O cao. Trên các phiên bản hỗ trợ, pg_stat_io cung cấp thêm góc nhìn theo backend/object/context. Số liệu là thống kê tích lũy hoặc theo loại operation; cần lấy delta theo thời gian và đối chiếu với metric cloud.

### SQL Server

sys.dm_io_virtual_file_stats cung cấp số liệu I/O theo file database:

~~~sql
SELECT
    DB_NAME(vfs.database_id) AS database_name,
    mf.name AS file_name,
    vfs.num_of_reads,
    vfs.num_of_writes,
    vfs.io_stall_read_ms,
    vfs.io_stall_write_ms,
    vfs.size_on_disk_bytes
FROM sys.dm_io_virtual_file_stats(NULL, NULL) AS vfs
JOIN sys.master_files AS mf
  ON mf.database_id = vfs.database_id
 AND mf.file_id = vfs.file_id;
~~~

Lấy mẫu hai lần để tính delta và thời gian trung bình gần đúng cho mỗi thao tác. Kết hợp wait statistics như PAGEIOLATCH, WRITELOG và các wait liên quan I/O; không xem một wait đơn lẻ là kết luận nếu chưa so với workload và thời gian chờ tổng.

### MySQL InnoDB

Performance Schema có thể thống kê I/O theo file nếu instrumentation được bật. Các status counters như Innodb_data_reads, Innodb_data_writes, Innodb_data_read và Innodb_data_written cũng giúp xem hoạt động đọc/ghi. Cần lấy delta trong cùng khoảng thời gian và phân biệt data file, redo log, temporary file.

### Oracle

Các view như V$IOSTAT_FILE, V$FILESTAT và V$SYSTEM_EVENT giúp xem số lần đọc/ghi, bytes và thời gian chờ theo file hoặc sự kiện. Cần phân biệt data file, control file, redo log và temporary tablespace.

Các truy vấn trên là điểm bắt đầu và có thể cần điều chỉnh theo phiên bản, quyền và cấu hình. Một số managed database hạn chế quyền truy cập view hoặc chỉ cung cấp metric đã tổng hợp.

## 9. Phân biệt storage throttling với các nút thắt khác

Latency tăng không đồng nghĩa storage đã throttle. Các nguyên nhân khác có thể tạo triệu chứng tương tự:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| CPU cao, I/O thấp | Query tốn CPU, join/sort hoặc expression nặng | Actual execution plan, CPU time |
| CPU thấp, I/O wait cao | Storage latency hoặc queue | Cloud I/O latency, queue, DB wait |
| Throughput thấp, queue thấp | Workload không phát đủ request hoặc thiếu concurrency | Offered load, active sessions, worker |
| Throughput phẳng, queue tăng | Chạm giới hạn IOPS/bandwidth hoặc service tier | Provisioned caps, throttling metrics |
| Commit chậm, data read bình thường | Log flush hoặc write latency | Log I/O, WRITELOG, redo/WAL metrics |
| Query chậm, temp I/O cao | Sort/hash spill do thiếu memory | Execution plan, temp file, memory grant |
| I/O tăng nhưng cloud disk chưa bão hòa | Database đọc quá nhiều trang hoặc cache miss | Logical/physical reads, query plan |
| Replication lag tăng | Nút thắt log transport/apply hoặc storage | Replication metrics và log I/O |

Hãy tìm nguyên nhân tại đúng lớp. Nếu query plan đọc quá nhiều trang, nâng storage tier có thể làm query nhanh hơn một phần nhưng vẫn giữ nguyên lãng phí I/O và chi phí.

## 10. Thiết kế workload phù hợp với giới hạn I/O

### Giảm lượng I/O không cần thiết

- Thiết kế chỉ mục theo điều kiện lọc, join và thứ tự truy cập.
- Tránh full scan lặp lại trên tập dữ liệu lớn khi workload chỉ cần một phần nhỏ.
- Chọn cột cần thiết thay vì đọc toàn bộ hàng rộng.
- Tránh join fanout và aggregate trên tập dữ liệu đã bị nhân bản.
- Dùng partition pruning khi truy vấn có điều kiện trên partition key.
- Tối ưu cache hit cho working set được truy cập lặp lại.

### Tách các loại I/O khi kiến trúc cho phép

Một số triển khai tách data, transaction log và temporary storage thành volume hoặc tier riêng. Điều này có thể giúp cô lập workload và tận dụng giới hạn riêng, nhưng chỉ hiệu quả khi nền tảng thực sự cấp giới hạn độc lập. Nếu mọi volume vẫn chia sẻ một instance bandwidth cap, việc tách volume không làm tăng tổng năng lực của instance.

Với managed database, nhà cung cấp có thể quản lý bố trí file nội bộ. Không phải dịch vụ nào cũng cho phép người dùng tự tách data/log/temp; hãy sử dụng các lựa chọn storage hoặc service tier được hỗ trợ.

### Kiểm soát concurrency

Nhiều truy vấn đồng thời có thể đẩy queue depth và IOPS lên cao. Giới hạn concurrency cho batch, backup hoặc báo cáo có thể giữ latency ổn định cho OLTP. Dùng queue ở ứng dụng, semaphore hoặc scheduler để dàn tải.

Không nên giảm concurrency đến mức làm lãng phí năng lực storage. Hãy đo throughput và latency theo từng mức để tìm điểm cân bằng.

### Điều chỉnh kích thước I/O

I/O nhỏ tăng số request cần xử lý; I/O lớn tăng throughput mỗi request nhưng có thể đọc dư dữ liệu hoặc tăng latency cho thao tác nhỏ. Cách database gom, tách hoặc phát hành I/O phụ thuộc engine và hệ điều hành. Không thay đổi block size hoặc tham số đọc trước khi hiểu workload và giới hạn của nền tảng.

## 11. Chọn cấu hình storage và compute

Khi workload cần hiệu năng liên tục, chọn storage dựa trên baseline IOPS, throughput và latency ở tải duy trì. Đừng lấy mức burst tối đa làm giả định cho toàn bộ thời gian.

### Khi nên tăng hiệu năng volume

- Volume chạm IOPS hoặc throughput provisioned.
- Instance và database service còn dư giới hạn.
- Workload thực sự cần nhiều I/O hơn và không thể giảm lượng đọc/ghi đáng kể.
- Chi phí provision thêm hiệu năng phù hợp với SLA.

### Khi nên tăng kích thước instance hoặc service tier

- Tổng I/O của nhiều volume chạm giới hạn instance.
- Database service đạt giới hạn data/log I/O gắn với compute tier.
- CPU, memory hoặc số worker cũng đang gần bão hòa.
- Tăng hiệu năng volume riêng lẻ không làm throughput tăng.

### Khi nên đổi loại storage

- Workload cần latency thấp và ổn định.
- Tải ghi hoặc đọc liên tục vượt khả năng của loại burst-based.
- Loại volume hiện tại không cho phép provision IOPS/throughput cần thiết.
- Yêu cầu durability, replication hoặc multi-attach khác với loại đang dùng.

### Khi nên dùng nhiều volume

Striping hoặc phân phối dữ liệu qua nhiều volume có thể tăng tổng IOPS/throughput trong một số kiến trúc tự quản lý. Tuy nhiên, tổng năng lực vẫn bị chặn bởi giới hạn instance, controller, filesystem hoặc dịch vụ. Cần đánh giá độ phức tạp vận hành, khả năng mở rộng, snapshot/backup và hành vi khi một thành phần lỗi.

## 12. Theo dõi burst, throttling và giới hạn dịch vụ

Metric nên được nhóm theo ba lớp:

### Lớp storage

- IOPS đọc/ghi.
- Throughput đọc/ghi.
- Latency đọc/ghi.
- Queue depth hoặc outstanding I/O.
- Burst balance, credit balance hoặc burst percentage nếu có.
- IOPS/bandwidth consumed percentage.
- Throttled operations hoặc throttled bytes nếu dịch vụ cung cấp.

### Lớp instance và database

- Giới hạn băng thông lưu trữ của VM/instance.
- CPU, memory, active sessions và worker.
- Data I/O và log I/O.
- Buffer cache hit, physical reads và writes.
- Wait events liên quan đọc, ghi, log flush và checkpoint.
- Temp I/O, backup I/O và replication lag.

### Lớp ứng dụng

- Offered request rate và completed request rate.
- Transaction rate và commit latency.
- p50/p95/p99 của truy vấn.
- Timeout, retry và connection pool wait.
- Batch size và số tác vụ chạy đồng thời.

### Cảnh báo nên dựa trên xu hướng

Một cấu hình cảnh báo có thể bao gồm:

- Burst balance giảm nhanh trong khi tải duy trì trên baseline.
- IOPS hoặc bandwidth consumed duy trì gần ngưỡng tối đa.
- Queue depth và p95/p99 latency cùng tăng.
- Throughput phẳng dù offered load tiếp tục tăng.
- Database I/O wait tăng đồng thời với cloud storage latency.
- Dung lượng storage hoặc quota provision gần giới hạn.

Không đặt ngưỡng giống nhau cho mọi workload. Một hệ thống OLTP có thể cần cảnh báo khi latency tăng dù throughput thấp; một hệ thống backup có thể chấp nhận latency cao hơn nhưng cần hoàn tất trong cửa sổ thời gian.

## 13. Ví dụ: hiệu năng giảm khi credit burst cạn

Một database nhỏ dùng volume có cơ chế credit-based burst. Trong giờ đầu, báo cáo và batch ingest chạy nhanh. Sau một thời gian, tốc độ ghi giảm rõ rệt dù CPU còn thấp.

Điều tra:

1. So sánh write IOPS, write throughput và write latency theo thời gian.
2. Quan sát credit/burst balance có giảm dần về 0 hay không.
3. Kiểm tra throughput sau thời điểm balance cạn có ổn định quanh baseline không.
4. Xác minh instance bandwidth và service tier chưa chạm giới hạn khác.
5. Đối chiếu thời gian chậm với batch ingest, checkpoint hoặc backup.

Nếu credit depletion trùng với thời điểm throughput giảm và các lớp khác còn dư, burst policy là nguyên nhân có bằng chứng. Giải pháp có thể là provision hiệu năng duy trì cao hơn, chọn loại storage phù hợp hoặc dàn batch vào thời gian có tải thấp.

Không nên chỉ tăng burst credit nếu workload cần hiệu năng cao liên tục. Hãy tính dung lượng và chi phí cho baseline đủ đáp ứng tải duy trì.

## 14. Ví dụ: volume còn dư nhưng instance đã chạm giới hạn

Một database tự quản lý gắn bốn volume dữ liệu. Mỗi volume được provision đủ IOPS, nhưng tổng throughput của máy ảo đạt giới hạn băng thông lưu trữ. Tăng IOPS của một volume không làm tổng throughput tăng.

Quy trình xác minh:

1. Đo read/write bytes và IOPS trên từng volume.
2. Cộng tổng lưu lượng đồng thời và so với giới hạn instance.
3. Kiểm tra metric instance-level bandwidth hoặc I/O consumed.
4. Quan sát queue và latency ở nhiều volume trong cùng khoảng thời gian.
5. Xác định có thể giảm I/O bằng query/index/cache hay cần tăng cỡ instance.

Nếu nhiều volume cùng chậm ở một thời điểm và tổng băng thông chạm trần instance, nút thắt nằm ở lớp compute/storage bandwidth. Có thể cần instance có giới hạn cao hơn, tách workload sang instance khác hoặc giảm tổng I/O.

## 15. Quy trình kiểm chứng trước và sau điều chỉnh

Trước khi thay đổi, ghi nhận baseline trong điều kiện tải đại diện:

| Chỉ số | Mục đích |
| --- | --- |
| Offered và completed IOPS | Biết workload gửi bao nhiêu và storage hoàn tất bao nhiêu |
| Read/write throughput | Xác định giới hạn băng thông |
| Read/write latency p50/p95/p99 | Đánh giá độ trễ thực tế |
| Queue depth | Nhận diện request đang xếp hàng |
| Burst balance/credit | Xác định khả năng tăng tốc còn lại |
| Volume và instance cap | Xác định giới hạn ở từng lớp |
| Database I/O waits | Gắn I/O chậm với truy vấn và file |
| CPU, memory, cache hit | Loại trừ các nút thắt khác |
| Temp, log, backup, replication I/O | Phân biệt loại I/O gây áp lực |
| Transaction/query latency | Đánh giá tác động tới người dùng |

Sau điều chỉnh:

1. Dùng cùng workload, tập dữ liệu và read/write mix để so sánh.
2. Chạy đủ lâu để quan sát cả giai đoạn burst và trạng thái sau khi burst kết thúc.
3. Đo ở nhiều mức concurrency, bao gồm tải giờ cao điểm.
4. Kiểm tra giới hạn volume, instance và database service cùng lúc.
5. So sánh latency, queue, throughput, throttling và credit balance.
6. Đối chiếu query plan, logical/physical reads, log flush và temp I/O.
7. Kiểm tra chi phí provision, compute tier và lưu trữ.
8. Xác nhận durability, backup, replication và yêu cầu SLA vẫn được đáp ứng.

Nếu chỉ benchmark trong vài phút đầu, kết quả có thể phản ánh burst thay vì năng lực duy trì. Bài kiểm thử phải đủ dài để thể hiện trạng thái ổn định của workload.

## 16. Nguyên tắc cần ghi nhớ

- IOPS đếm số thao tác mỗi giây; throughput đo lượng dữ liệu mỗi giây; latency đo thời gian hoàn tất; queue depth phản ánh yêu cầu đang chờ hoặc đang xử lý.
- Kích thước I/O quyết định mối quan hệ giữa IOPS và throughput; OLTP và scan tuần tự có thể chạm các giới hạn khác nhau.
- Volume, VM/instance, database service tier và quota có thể có giới hạn độc lập.
- Hiệu năng hữu dụng bị giới hạn bởi lớp thấp nhất trên đường I/O đang hoạt động.
- Credit-based burst dùng credit tích lũy để vượt baseline trong thời gian có hạn; khi credit cạn, hiệu năng có thể trở về baseline.
- Burst theo cấu hình hoặc on-demand có chính sách và chi phí riêng; không giả định mọi dịch vụ dùng credit.
- Throttling thường thể hiện qua throughput phẳng, queue và latency tăng, hoặc metric consumed/throttled đạt ngưỡng.
- Data file, transaction log, temporary storage, backup và replication có mẫu I/O khác nhau.
- Phải kết hợp metric cloud với wait, execution plan và thống kê nội bộ database.
- Ưu tiên giảm I/O không cần thiết, kiểm soát concurrency và xác định đúng lớp giới hạn trước khi nâng storage hoặc compute tier.
- Benchmark phải kéo dài đủ để quan sát cả burst lẫn hiệu năng duy trì, sau đó kiểm tra SLA và chi phí.

Tối ưu I/O trên dịch vụ đám mây đòi hỏi hiểu toàn bộ đường đi từ truy vấn đến storage. Khi phân biệt IOPS, throughput, latency và queue depth, nhận diện được giới hạn theo volume, instance và service tier, đồng thời theo dõi credit cùng metric throttling, nhóm vận hành có thể xác định chính xác nút thắt. Mọi thay đổi về storage, compute hoặc concurrency cần được kiểm chứng bằng workload đại diện trong cả giai đoạn tăng tốc và trạng thái tải duy trì.
