# IOPS, băng thông, độ trễ thiết bị và hàng đợi I/O

## 1. Vì sao hiệu năng lưu trữ không thể chỉ đo bằng dung lượng?

Một hệ quản trị cơ sở dữ liệu có thể có đủ dung lượng đĩa nhưng vẫn chậm khi đọc hoặc ghi. Truy vấn cần đọc nhiều trang ngẫu nhiên có thể bị giới hạn bởi số thao tác I/O mỗi giây; quét bảng lớn hoặc backup có thể bị giới hạn bởi băng thông; giao dịch commit có thể chậm vì phải chờ log flush; và khi quá nhiều yêu cầu cùng chờ thiết bị, độ trễ tăng mạnh dù IOPS danh nghĩa của storage vẫn cao.

Để phân tích nút thắt lưu trữ, cần xem đồng thời bốn đại lượng: **IOPS** (số thao tác đọc/ghi mỗi giây), **throughput/băng thông** (số byte truyền mỗi giây), **latency** (thời gian hoàn tất một yêu cầu I/O) và **queue depth** (số yêu cầu đang chờ hoặc đang được xử lý). Bốn đại lượng liên hệ với nhau nhưng không thay thế nhau. Một volume có IOPS cao chưa chắc đạt băng thông cao với kích thước block nhỏ; một volume đạt throughput lớn khi đọc tuần tự chưa chắc xử lý tốt truy cập ngẫu nhiên; và tăng queue depth có thể tăng throughput trong một khoảng tải nhưng cũng làm latency tăng.

Trong tối ưu hiệu năng cơ sở dữ liệu, phải nối số liệu storage với cách database truy cập dữ liệu: đọc trang ngẫu nhiên từ index, quét tuần tự, ghi transaction log, checkpoint, sort/hash spill, backup và replication. Bài học này trình bày cách đọc các chỉ số, hiểu quan hệ toán học giữa chúng, nhận diện thiết bị bão hòa và thiết kế phép đo sát workload thực tế.

## 2. Bốn đại lượng cốt lõi

### 2.1. IOPS — số thao tác I/O mỗi giây

IOPS (Input/Output Operations Per Second) là số yêu cầu đọc hoặc ghi hoàn tất trong một giây. Có thể tách thành:

- Read IOPS: số thao tác đọc mỗi giây.
- Write IOPS: số thao tác ghi mỗi giây.
- Total IOPS: tổng đọc và ghi theo cách đếm của công cụ hoặc nhà cung cấp.

IOPS mô tả số lần thực hiện thao tác, không trực tiếp mô tả lượng dữ liệu. Một I/O 4 KiB và một I/O 1 MiB đều có thể được tính là một thao tác, dù lượng byte chênh lệch 256 lần.

Ví dụ, một thiết bị hoàn tất 20.000 yêu cầu đọc mỗi giây với block 8 KiB có IOPS đọc là 20.000. Nếu block trung bình là 64 KiB và IOPS vẫn là 20.000, lượng dữ liệu truyền sẽ lớn hơn tám lần.

IOPS hữu ích khi workload gồm nhiều thao tác nhỏ, đặc biệt là truy cập ngẫu nhiên vào index và data page. Tuy nhiên, IOPS cần đi cùng kích thước I/O, read/write mix, latency và queue depth. Không thể so sánh hai kết quả benchmark chỉ bằng IOPS nếu block size hoặc tỷ lệ đọc/ghi khác nhau.

### 2.2. Throughput — băng thông dữ liệu

Throughput là lượng dữ liệu được truyền trong một đơn vị thời gian, thường biểu diễn bằng MB/s hoặc MiB/s. Công thức gần đúng:

\[
\text{Throughput (bytes/s)} = \text{IOPS} \times \text{I/O size (bytes)}
\]

Ví dụ với block trung bình 8 KiB:

\[
20.000 \times 8.192 = 163.840.000\text{ bytes/s}
\]

Tương đương khoảng 163,84 MB/s theo hệ thập phân hoặc 156,25 MiB/s theo hệ nhị phân. Nếu công cụ hiển thị MB/s và MiB/s khác nhau, cần kiểm tra quy ước đơn vị trước khi so sánh.

Throughput quan trọng với full table scan, sequential read, backup, restore, bulk load, checkpoint và truyền dữ liệu giữa các tầng lưu trữ. Một thiết bị có thể đạt throughput lớn với block lớn nhưng không đạt nhiều IOPS với block nhỏ.

### 2.3. Latency — độ trễ của một yêu cầu

Latency là thời gian từ lúc yêu cầu I/O được gửi tới lúc hoàn tất theo điểm đo của công cụ. Latency có thể bao gồm thời gian nằm trong hàng đợi, thời gian thiết bị xử lý và thời gian truyền qua các tầng driver, hypervisor hoặc network storage.

Các chỉ số thường gặp:

- Average latency: độ trễ trung bình.
- p50: một nửa yêu cầu hoàn tất trong thời gian này hoặc nhanh hơn.
- p95: 95% yêu cầu hoàn tất trong thời gian này hoặc nhanh hơn.
- p99/p99.9: biểu diễn phần đuôi chậm của phân bố.
- Read latency và write latency: cần tách riêng vì thiết bị và workload có thể xử lý hai loại khác nhau.

Average thấp không bảo đảm trải nghiệm tốt nếu p99 rất cao. Một số ít yêu cầu chờ lâu có thể làm truy vấn đồng bộ, checkpoint hoặc commit vượt SLO. Khi phân tích, cần đo histogram/percentile trong cùng cửa sổ thời gian và cùng loại I/O.

### 2.4. Queue depth — độ sâu hàng đợi

Queue depth là số yêu cầu I/O đang outstanding: đã được gửi nhưng chưa hoàn tất. Tùy công cụ, con số có thể gồm yêu cầu đang chờ ở lớp hệ điều hành, driver, controller hoặc thiết bị. Một số metric là queue depth hiện tại; một số là giá trị trung bình trong khoảng lấy mẫu.

Queue depth thấp có thể khiến thiết bị chưa khai thác hết khả năng xử lý song song. Queue depth quá cao có thể làm yêu cầu chờ lâu, tăng latency và gây head-of-line blocking. Mức phù hợp phụ thuộc thiết bị, loại I/O, số queue phần cứng, số worker và mục tiêu latency.

Không có một queue depth tối ưu dùng chung cho HDD, SSD SATA, NVMe, SAN hoặc cloud volume. Cần đo throughput và latency theo nhiều mức queue trong một workload đại diện, rồi chọn điểm đáp ứng SLO thay vì chọn mức có IOPS cực đại.

## 3. Quan hệ giữa IOPS, kích thước I/O, throughput và latency

### 3.1. Cùng IOPS nhưng throughput khác nhau

| IOPS | Kích thước I/O | Throughput xấp xỉ |
|---:|---:|---:|
| 20.000 | 4 KiB | 78,1 MiB/s |
| 20.000 | 8 KiB | 156,3 MiB/s |
| 20.000 | 16 KiB | 312,5 MiB/s |
| 20.000 | 64 KiB | 1.250 MiB/s |

Bảng giả định mọi I/O đều có cùng kích thước và IOPS là số thao tác hoàn tất mỗi giây. Trong hệ thống thực, kích thước I/O có thể thay đổi, read/write mix khác nhau và một yêu cầu database có thể được gộp hoặc tách thành nhiều yêu cầu ở tầng storage.

### 3.2. Cùng throughput nhưng IOPS khác nhau

Nếu throughput là 400 MiB/s:

- Với block 4 KiB, cần khoảng 102.400 IOPS.
- Với block 8 KiB, cần khoảng 51.200 IOPS.
- Với block 64 KiB, cần khoảng 6.400 IOPS.

Vì vậy, benchmark sequential 1 MiB không thể đại diện cho workload random 8 KiB của database. Một volume có throughput cao có thể vẫn không đáp ứng được nhiều thao tác nhỏ với latency thấp.

### 3.3. Little's Law và số yêu cầu outstanding

Trong một hệ thống ổn định, định luật Little mô tả quan hệ giữa số yêu cầu trung bình trong hệ thống, tốc độ hoàn tất và thời gian lưu lại:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số yêu cầu trung bình đang nằm trong hệ thống, bao gồm chờ và xử lý.
- \(\lambda\): throughput theo yêu cầu mỗi giây.
- \(W\): thời gian trung bình mỗi yêu cầu ở trong hệ thống, tính bằng giây.

Ví dụ, thiết bị hoàn tất 10.000 I/O/s và thời gian phản hồi trung bình là 2 ms (0,002 giây):

\[
L = 10.000 \times 0,002 = 20\text{ yêu cầu}
\]

Giá trị 20 là số yêu cầu trung bình đang outstanding theo ranh giới đo tương ứng. Nó không phải khuyến nghị đặt queue depth bằng 20 cho mọi workload. Nếu đo latency ở phía ứng dụng nhưng IOPS ở phía thiết bị, hai số có thể không cùng ranh giới và phép tính không còn trực tiếp áp dụng.

### 3.4. Tăng queue depth không làm thiết bị nhanh vô hạn

Khi queue depth tăng từ mức quá thấp, thiết bị có thể có thêm việc để xử lý song song, từ đó throughput tăng. Khi đã đạt giới hạn tài nguyên, thêm yêu cầu chủ yếu làm tăng thời gian chờ. Đường cong thường có dạng:

```text
Throughput
   ^                    _____________
   |                ___/
   |            ___/
   |         __/
   |      __/
   |_____/
   +----------------------------------> Queue depth
             vùng bão hòa

Latency
   ^                              ____
   |                         ____/
   |                    ____/
   |               ____/
   |          ____/
   |_________/
   +----------------------------------> Queue depth
```

Đây là hình minh họa. Thiết bị thực có thể có nhiều vùng plateau, giới hạn IOPS/throughput riêng, hoặc thay đổi theo read/write mix. Điểm vận hành tốt thường nằm trước vùng latency tăng dốc, không nhất thiết ở mức queue depth tạo ra throughput cao nhất.

## 4. Kích thước block và loại truy cập

### 4.1. Random I/O và sequential I/O

Random I/O truy cập các vùng không liền kề trong không gian địa chỉ. Nó thường xuất hiện khi index lookup, nested-loop lookup hoặc truy vấn lấy một số ít hàng nằm rải rác trên nhiều trang.

Sequential I/O truy cập các vùng liên tiếp hoặc có tính tuần tự. Nó thường xuất hiện khi full table scan, index scan theo thứ tự, backup hoặc đọc file log theo luồng.

Random I/O có thể bị giới hạn bởi IOPS và latency; sequential I/O thường tận dụng throughput và read-ahead tốt hơn. Đây là xu hướng, không phải quy tắc tuyệt đối: SSD/NVMe có thể xử lý random I/O tốt hơn HDD, còn SAN/cloud storage có đặc tính phụ thuộc backend và giới hạn dịch vụ.

### 4.2. Database page size không đồng nhất với storage block size

Database thường quản lý dữ liệu theo page, chẳng hạn page 8 KiB hoặc 16 KiB tùy engine. Hệ điều hành, filesystem và thiết bị có kích thước sector, block hoặc request size riêng. Một lần đọc database page có thể được filesystem cache đáp ứng, gộp với I/O kế cận, chia thành nhiều request hoặc chuyển thành request lớn hơn.

Do đó:

- Không mặc định một logical page read bằng đúng một physical I/O.
- Không suy ra IOPS thiết bị trực tiếp từ số logical reads trong database.
- Cần phân biệt buffer cache hit, physical read, read-ahead và storage request.
- Khi so sánh block size benchmark, hãy dùng kích thước gần với workload database nhưng cũng đo các luồng sequential lớn.

### 4.3. Read-ahead và prefetch

Khi database nhận thấy truy vấn đọc theo chuỗi trang, engine có thể yêu cầu đọc trước (read-ahead/prefetch). Cách này giúp giảm số lần chờ từng trang và tăng throughput. Tuy nhiên, read-ahead quá rộng có thể đọc dữ liệu không được dùng, gây áp lực cache và cạnh tranh với random read hoặc log flush.

Nếu scan lớn làm truy vấn ngẫu nhiên chậm đi, hãy kiểm tra read-ahead, buffer cache, scan concurrency và storage queue. Tối ưu truy vấn để tránh scan không cần thiết thường hiệu quả hơn chỉ tăng IOPS.

## 5. Read/write mix và đặc tính workload database

### 5.1. Đọc trang dữ liệu và index

Index lookup có thể tạo nhiều random read nhỏ nếu các trang không nằm trong buffer pool. Một truy vấn đọc ít hàng qua index thường cần latency thấp hơn throughput cực đại. Nếu truy vấn thực hiện hàng nghìn lookup riêng lẻ, tổng thời gian có thể bị chi phối bởi latency mỗi lần truy cập và khả năng song song.

Covering index, clustering phù hợp, partition pruning và cải thiện locality có thể giảm số lần phải đọc trang. Trước khi mua storage IOPS cao hơn, hãy xác định truy vấn có đọc quá nhiều trang do kế hoạch thực thi hay do dữ liệu không nằm trong cache.

### 5.2. Transaction log và redo log

Transaction log thường có luồng ghi tuần tự và có yêu cầu latency thấp ở bước flush khi commit đồng bộ. Một giao dịch có thể chờ log flush dù data page chưa được ghi xuống. Vì vậy, write latency của log volume có thể ảnh hưởng trực tiếp đến commit latency.

Đo riêng log write/flush nếu có thể. Nếu log và data file cùng dùng backend bão hòa, checkpoint hoặc bulk write có thể làm tăng hàng đợi của log. Tách volume logic chỉ hữu ích khi tách được tài nguyên thực sự như thiết bị, controller, queue hoặc giới hạn IOPS.

### 5.3. Checkpoint và dirty page writeback

Checkpoint và background writer ghi dirty page từ buffer pool xuống data files. Hoạt động này có thể tạo write burst hoặc writeback kéo dài. Nếu tốc độ ghi trang cạnh tranh với log flush, commit latency có thể tăng.

Theo dõi checkpoint duration, số trang ghi, dirty page, log flush latency và storage queue theo cùng mốc thời gian. Một đỉnh latency đồng thời với checkpoint là dấu hiệu cần điều tra, nhưng chưa đủ chứng minh checkpoint là nguyên nhân duy nhất.

### 5.4. Temp I/O và spill

Sort, hash join, hash aggregate hoặc các thao tác xử lý dữ liệu lớn có thể vượt ngân sách bộ nhớ và spill ra vùng tạm. Temp I/O thường tạo thêm đọc/ghi, có thể là tuần tự hoặc nhiều luồng tùy engine. Nếu temp files dùng chung storage với data/log, chúng có thể làm queue và latency của các workload khác tăng.

Kiểm tra memory grant, actual rows, sort/hash spill, temp file bytes và wait liên quan. Giảm dữ liệu trung gian, cải thiện thống kê hoặc truy vấn có thể giảm temp I/O và giải phóng năng lực storage.

### 5.5. Backup, restore và replication

Backup/restore có thể tạo luồng sequential throughput lớn; replication có thể đọc/ghi log và truyền dữ liệu qua mạng; CDC hoặc ETL có thể quét nhiều partition. Những tác vụ nền này cạnh tranh I/O với truy vấn trực tuyến.

Lập lịch backup, giới hạn tốc độ nếu engine hỗ trợ và phân bổ tài nguyên hợp lý. Không đánh giá storage chỉ trong lúc database idle; cần đo khi workload nền và truy vấn trực tuyến cùng chạy.

## 6. Thiết bị lưu trữ và giới hạn hiệu năng

### 6.1. HDD

HDD dùng cơ cấu cơ học với thời gian seek và rotational latency. Random I/O thường có latency cao hơn nhiều so với sequential I/O. Một ổ đĩa đơn có thể đạt throughput tuần tự tương đối tốt nhưng IOPS random thấp.

RAID, cache và nhiều spindle có thể tăng khả năng xử lý song song, nhưng read/write penalty, parity update và rebuild ảnh hưởng hiệu năng. Khi workload database có nhiều random read/write, cần xem IOPS, latency và queue của toàn bộ array thay vì thông số một ổ riêng lẻ.

### 6.2. SSD SATA và NVMe

SSD loại bỏ thời gian seek cơ học và thường cải thiện random IOPS cùng latency. SATA bị giới hạn bởi giao tiếp và controller; NVMe hỗ trợ nhiều queue và command outstanding, có thể tận dụng song song tốt hơn.

Tuy nhiên, SSD/NVMe vẫn có giới hạn về controller, NAND, garbage collection, write amplification, endurance, thermal throttling và cache. Khi thiết bị nóng hoặc ghi kéo dài, latency có thể tăng dù benchmark ngắn ban đầu rất tốt. Cần đo sustained workload, không chỉ burst IOPS.

### 6.3. SAN, NAS và network storage

Storage qua mạng bổ sung latency của network, switch, protocol, controller và backend array. Một yêu cầu có thể phải qua nhiều tầng queue. Băng thông network, RTT, packet loss, congestion và số client cùng truy cập đều ảnh hưởng kết quả.

Khi database chạy trên SAN/NAS, cần đối chiếu metric ở host, fabric/network và storage array. Host có thể báo queue cao vì array bận; array có thể báo latency thấp ở cache nhưng host vẫn chờ network hoặc multipath failover.

### 6.4. Cloud block volume và giới hạn theo tier

Cloud volume thường có giới hạn IOPS, throughput hoặc burst credit theo loại volume, dung lượng cấp phát và instance bandwidth. Một volume có thể đạt mức burst trong thời gian ngắn rồi giảm khi credit cạn; hoặc throughput bị giới hạn bởi instance dù volume còn dư năng lực.

Khi đo cloud storage, cần kiểm tra:

- IOPS và throughput provisioned của volume.
- Giới hạn IOPS/throughput của instance hoặc VM.
- Burst balance/credit nếu dịch vụ có cơ chế này.
- Queue depth, latency và throttling metric.
- Multi-attach hoặc volume sharing với workload khác.
- Vị trí availability zone, network path và loại cache.

Không chỉ dựa vào thông số tối đa trong bảng giá. Mức hiệu năng thực tế phụ thuộc kích thước block, read/write mix, queue, instance limit và thời gian duy trì tải.

## 7. Bão hòa I/O và các dấu hiệu thường gặp

Một thiết bị có thể bão hòa theo nhiều cách:

- Đạt giới hạn IOPS nhưng throughput vẫn thấp vì block nhỏ.
- Đạt giới hạn throughput nhưng IOPS chưa cao vì block lớn.
- Queue depth tăng liên tục và latency tăng theo.
- Storage throttling do vượt mức provisioned hoặc burst credit cạn.
- Write latency tăng do checkpoint, log flush hoặc cache destage.
- Một thiết bị/queue cụ thể bão hòa trong khi tổng hệ thống còn dư năng lực.

Các dấu hiệu cần đọc cùng nhau:

| Chỉ số | Dấu hiệu đáng chú ý | Cách diễn giải |
|---|---|---|
| IOPS | Chạm trần provisioned hoặc plateau | Có thể bị giới hạn số thao tác/giây |
| Throughput | Tiệm cận giới hạn MB/s | Có thể bị giới hạn băng thông hoặc block size lớn |
| Latency | p95/p99 tăng nhanh | Queueing, throttling hoặc backend chậm |
| Queue depth | Tăng kéo dài trong khi throughput không tăng | Yêu cầu tích tụ, thiết bị không theo kịp |
| Read/write split | Một phía có latency cao hơn rõ | Có thể có bất cân bằng read/write hoặc write penalty |
| Utilization | Cao liên tục | Gợi ý thiết bị bận, nhưng cách tính phụ thuộc thiết bị/driver |
| Throttling/credit | Có sự kiện throttle hoặc credit giảm | Volume/instance chạm giới hạn dịch vụ |

Không dùng một metric đơn lẻ để kết luận. Ví dụ, `%util=100` trên thiết bị đơn queue truyền thống có thể cho thấy thiết bị bận, nhưng trên NVMe nhiều queue, RAID hoặc thiết bị ảo, cách diễn giải khác. Ngược lại, `%util` thấp không chứng minh storage không phải nút thắt nếu request đang chờ network, hypervisor hoặc controller.

## 8. Đo ở hệ điều hành

### 8.1. Linux: iostat

`iostat -x 1` có thể hiển thị các chỉ số như `r/s`, `w/s`, `rkB/s`, `wkB/s`, `await`, `aqu-sz` và `%util` tùy phiên bản sysstat.

- `r/s`, `w/s`: số thao tác đọc/ghi mỗi giây theo thiết bị.
- `rkB/s`, `wkB/s`: throughput đọc/ghi.
- `await`: thời gian trung bình hoàn tất yêu cầu, thường gồm thời gian chờ và xử lý theo định nghĩa công cụ.
- `aqu-sz`: độ dài hàng đợi trung bình.
- `%util`: tỷ lệ thời gian thiết bị có ít nhất một I/O outstanding theo cách đo của công cụ; không phải lúc nào cũng là phần trăm công suất tối đa trên thiết bị song song cao.

Ví dụ cách đọc: nếu `w/s` ổn định, `wkB/s` tăng và `await` tăng mạnh, kích thước ghi hoặc áp lực write có thể đã tăng. Nếu `aqu-sz` cao kéo dài trong khi throughput plateau, hãy điều tra giới hạn IOPS/throughput hoặc backend.

Nên lấy mẫu theo khoảng thời gian đủ dài để thấy tải ổn định, đồng thời ghi timestamp để đối chiếu với database wait, checkpoint, backup và batch job.

### 8.2. Linux: phân biệt thiết bị và filesystem

Đo ở block device không luôn cho biết file nào tạo I/O. Cần ánh xạ filesystem, logical volume, device mapper, multipath và storage backend. Công cụ như `lsblk`, `findmnt`, `dmsetup` hoặc tiện ích của nhà cung cấp có thể giúp xác định đường đi.

Một database có thể đặt data, log và temp trên các mount khác nhau nhưng cùng một physical pool. Hãy xác minh tầng dưới cùng trước khi kết luận rằng tách mount đã tách được tài nguyên.

### 8.3. Windows: Performance Monitor

Trong Windows Performance Monitor, các counter thường dùng gồm:

- `PhysicalDisk\Disk Reads/sec` và `Disk Writes/sec`.
- `PhysicalDisk\Disk Read Bytes/sec` và `Disk Write Bytes/sec`.
- `PhysicalDisk\Avg. Disk sec/Read` và `Avg. Disk sec/Write`.
- `PhysicalDisk\Current Disk Queue Length` hoặc counter queue phù hợp.
- `PhysicalDisk\% Disk Time` và các counter theo volume nếu cần.

Các counter cần được đọc theo đúng instance disk/volume. `Avg. Disk sec/Read` và `Avg. Disk sec/Write` thường biểu diễn giây; chuyển sang ms bằng cách nhân 1.000. Queue length là số yêu cầu chờ/đang xử lý theo cách Windows và driver báo cáo, không nên so trực tiếp với queue depth của một công cụ khác nếu ranh giới đo khác nhau.

### 8.4. Công cụ benchmark

`fio` trên Linux và DiskSpd trên Windows có thể tạo workload kiểm tra IOPS, throughput, latency và queue depth. Chỉ chạy trên file thử nghiệm hoặc volume dành riêng, với dữ liệu có thể xóa; không trỏ benchmark ghi trực tiếp vào block device chứa database đang hoạt động.

Một ví dụ `fio` minh họa random read 8 KiB trên file thử nghiệm riêng:

```bash
fio --name=db-randread \
  --filename=/mnt/bench/fio-testfile \
  --size=10G --rw=randread --bs=8k \
  --ioengine=libaio --direct=1 \
  --iodepth=16 --numjobs=4 \
  --time_based --runtime=60 \
  --group_reporting
```

Đường dẫn phải là file thử nghiệm đã được chuẩn bị trên volume thử nghiệm; không dùng file database, log hoặc raw device. Thay `--rw=randread` bằng `randwrite` chỉ khi chấp nhận ghi đè nội dung file thử nghiệm. Tham số `ioengine` cần phù hợp kernel và phiên bản fio; có thể dùng engine khác theo môi trường.

Benchmark ngắn có thể chỉ đo cache hoặc burst credit. Hãy warm-up, chạy đủ lâu để đạt steady state, ghi latency histogram, và không tạo tải làm ảnh hưởng production. Một phép benchmark tổng hợp không thay thế phép đo workload database thật.

## 9. Đo từ bên trong hệ quản trị cơ sở dữ liệu

### 9.1. Logical I/O và physical I/O

Logical read là lần database yêu cầu một trang từ buffer manager. Trang có thể đã nằm trong buffer pool, nên không cần đọc storage. Physical read là thao tác đọc từ tầng lưu trữ theo định nghĩa của engine; có thể chịu ảnh hưởng read-ahead, OS cache và storage cache.

Vì vậy, logical reads cao không đồng nghĩa storage IOPS cao. Nếu một truy vấn có hàng triệu logical reads nhưng buffer hit gần như toàn bộ, nút thắt có thể là CPU, memory bandwidth hoặc số lần truy cập trang trong buffer pool. Nếu physical reads cao và latency tăng, storage có thể là yếu tố giới hạn.

### 9.2. PostgreSQL

Các view và thống kê PostgreSQL có thể giúp phân biệt I/O database với I/O hệ điều hành:

- `pg_stat_database`: số block được đọc và cache hit theo database.
- `pg_stat_io` (PostgreSQL 16 trở lên): thống kê I/O theo backend/object/context tùy phiên bản.
- `pg_stat_bgwriter` và các thống kê checkpoint liên quan phiên bản: theo dõi hoạt động ghi nền/checkpoint.
- `pg_stat_wal`: theo dõi lượng WAL và hoạt động ghi/sync WAL ở phiên bản hỗ trợ.
- Wait events: xác định backend đang chờ I/O, WAL hoặc lock.

Các bộ đếm thường là tích lũy từ lần reset hoặc khởi động. Hãy lấy snapshot đầu và cuối một cửa sổ đo, tính delta và đối chiếu cùng `iostat` hoặc metric storage. Tên cột thay đổi giữa các phiên bản; đọc tài liệu đúng phiên bản trước khi viết dashboard.

### 9.3. SQL Server

SQL Server cung cấp `sys.dm_io_virtual_file_stats` để xem số lần đọc/ghi, số byte và thời gian I/O tích lũy theo database file. DMV này thường được dùng bằng cách chụp hai snapshot và lấy delta để tính latency trung bình trong khoảng đo.

Wait statistics như `PAGEIOLATCH_*` có thể cho thấy session chờ page I/O; `WRITELOG` liên quan chờ log flush. Tuy nhiên, wait stats là thời gian chờ tích lũy và cần phân loại theo workload, không tự động chứng minh disk là nguyên nhân. So sánh với file-level I/O latency, OS counters và storage metrics.

### 9.4. MySQL/InnoDB

InnoDB status, Performance Schema và các bảng tổng hợp trong schema `sys` có thể cung cấp số liệu buffer pool, data file I/O, redo log và file wait. `Innodb_buffer_pool_read_requests` là yêu cầu đọc logic; `Innodb_buffer_pool_reads` phản ánh các lần phải đọc từ data file theo cách đếm của engine. Tỷ lệ giữa chúng giúp hiểu cache behavior nhưng không thay thế latency đo ở storage.

Các metric cần đối chiếu gồm data file read/write, redo log write/flush, fsync, pending I/O, buffer pool dirty pages và checkpoint. Tên metric và cách reset có thể khác giữa MySQL/MariaDB và phiên bản.

## 10. Tách workload theo data, log và temp

Một máy database thường có ít nhất ba nhóm I/O:

| Nhóm | Đặc tính thường gặp | Chỉ số cần ưu tiên |
|---|---|---|
| Data files | Random read/write, read-ahead, checkpoint | Read/write IOPS, throughput, latency, queue, cache hit |
| Transaction log | Ghi tuần tự, flush đồng bộ tại commit | Write latency, flush latency, throughput, queue và p99 |
| Temp/scratch | Sort/hash spill, temp table, work files | Throughput, IOPS, spill bytes, queue và cạnh tranh với data/log |

Phân tách file không tự động phân tách tài nguyên. Hãy kiểm tra chúng có nằm trên cùng physical device, RAID group, SAN pool, cloud volume backend hoặc instance bandwidth hay không.

Nếu log flush chậm trong lúc data checkpoint chạy, cần xem liệu hai nhóm dùng chung backend. Nếu temp spill làm truy vấn khác chậm, kiểm tra memory grant và kích thước dữ liệu trung gian trước khi tăng IOPS. Nếu data random read chậm, xem buffer cache, index access path và locality.

## 11. Đọc queue depth đúng cách

### 11.1. Queue ở nhiều tầng

Một yêu cầu I/O có thể đi qua nhiều queue:

1. Database I/O scheduler hoặc worker queue.
2. Hệ điều hành và block layer.
3. Device driver hoặc NVMe submission queue.
4. HBA/controller, RAID hoặc SAN queue.
5. Network queue nếu dùng remote storage.
6. Queue nội bộ của storage array hoặc cloud service.

Một metric queue tại host không nhất thiết phản ánh tổng số yêu cầu trong array. Một tầng có queue thấp nhưng tầng sau bị nghẽn vẫn có thể tạo latency cao.

### 11.2. Queue depth thấp chưa chắc tốt

Nếu queue depth gần bằng 0 và throughput thấp, thiết bị có thể đang thiếu yêu cầu để xử lý song song. Nguyên nhân có thể là workload tuần tự ít request outstanding, ứng dụng phát I/O đồng bộ từng bước, hoặc database bị giới hạn worker.

Không nên tăng queue depth bằng mọi giá. Tăng concurrency ở ứng dụng có thể làm nhiều transaction tranh chấp lock, tăng memory pressure và làm p99 xấu hơn. Cần phân biệt thiết bị chưa đủ việc với database không thể phát thêm I/O do phụ thuộc tuần tự.

### 11.3. Queue depth cao chưa chắc thiết bị là nguyên nhân gốc

Queue cao có thể là kết quả của việc database gửi quá nhiều I/O do scan lớn, thiếu cache, checkpoint burst hoặc temp spill. Tăng IOPS provisioned có thể giảm triệu chứng nhưng không loại bỏ công việc dư thừa.

Hãy tìm nguồn phát sinh yêu cầu: query plan, số physical reads, read-ahead, checkpoint, backup, index rebuild, ETL và concurrency. Giảm số yêu cầu không cần thiết có thể cải thiện latency cho toàn workload.

## 12. Bài toán latency: average, percentile và tail

### 12.1. Vì sao percentile quan trọng?

Giả sử 99% yêu cầu đọc hoàn tất trong 2 ms nhưng 1% mất 80 ms. Average có thể vẫn ở mức thấp, nhưng truy vấn phải chờ tất cả trang cần thiết có thể bị ảnh hưởng bởi yêu cầu chậm. Giao dịch có nhiều I/O nối tiếp còn có thể tích lũy latency.

Hãy thu thập histogram hoặc percentile riêng cho read/write, log/data/temp và từng volume. Không chỉ dùng average từ một khoảng dài vì nó có thể che các đợt spike ngắn.

### 12.2. Latency ở tầng database và tầng storage

Database wait time có thể bao gồm thời gian chờ worker, lock, scheduler hoặc I/O. Storage latency thường đo từ lúc request tới một tầng thiết bị hoặc provider đến lúc hoàn tất. Hai số không nhất thiết bằng nhau.

Ví dụ, một truy vấn chờ `PAGEIOLATCH` 20 ms có thể gồm thời gian chờ I/O trang, nhưng không nên đồng nhất trực tiếp với `Avg. Disk sec/Read` của toàn thiết bị. Cần so sánh cùng thời điểm, file và workload; phân biệt wait duration, request latency và queueing.

### 12.3. Tail latency và hàng đợi

Khi hệ thống tiến gần công suất tối đa, các yêu cầu đến trong lúc queue đã dài phải chờ lâu hơn. Một spike ở p99 có thể xuất hiện trước khi throughput tổng thể giảm. Đây là dấu hiệu quan trọng để điều chỉnh concurrency, batch size hoặc capacity trước khi người dùng thấy timeout hàng loạt.

## 13. Benchmark storage sát workload database

### 13.1. Xác định workload trước khi đo

Trước benchmark, mô tả workload mục tiêu:

- Tỷ lệ read/write.
- Random hay sequential.
- Block size phân bố như thế nào.
- Queue depth/concurrency thực tế.
- Số worker và số file.
- Thời lượng tải và yêu cầu steady state.
- Latency mục tiêu ở p95/p99.
- Có chạy cùng checkpoint, backup, replication hoặc temp I/O không.

Nếu database chủ yếu đọc random 8 KiB, benchmark chỉ dùng sequential 1 MiB sẽ không phản ánh nút thắt. Nếu hệ thống backup đọc tuần tự hàng trăm MiB/s, chỉ benchmark random 4 KiB cũng chưa đủ.

### 13.2. Ma trận benchmark

Một ma trận tối thiểu có thể gồm:

| Thử nghiệm | Pattern | Block size | Mục tiêu |
|---|---|---:|---|
| Random read | 100% read, random | 8 KiB hoặc gần page size | Đánh giá index/data lookup |
| Random write | 100% write, random | 8 KiB hoặc gần page size | Đánh giá write IOPS và latency |
| Mixed OLTP | 70/30 hoặc tỷ lệ thực tế | 8 KiB | Đánh giá read/write mix và queue |
| Sequential read | 100% read, sequential | 128 KiB–1 MiB | Đánh giá scan/backup throughput |
| Sequential write | 100% write, sequential | 128 KiB–1 MiB | Đánh giá bulk write/checkpoint |
| Log-like write | Ghi tuần tự, flush theo chu kỳ | Kích thước gần log record/batch thực tế | Đánh giá latency flush |

Các tỷ lệ và block size trong bảng là điểm bắt đầu minh họa. Hãy thay bằng phân bố đo từ workload thật và giới hạn của engine/storage.

### 13.3. Warm-up và steady state

Benchmark quá ngắn có thể đo cache, burst credit hoặc vùng SLC cache của SSD thay vì năng lực duy trì. Cần chạy warm-up, tải đủ lâu, quan sát khi throughput và latency ổn định, sau đó mới lấy cửa sổ đo. Với cloud volume có burst credit, cần đo cả khi credit còn và khi đã giảm theo chính sách dịch vụ.

Ghi nhận nhiệt độ/thermal throttling, cache hit, queue depth, latency histogram và storage throttling. Không so sánh hai kết quả nếu một lần chạy cold cache và lần khác warm cache mà không ghi rõ.

### 13.4. Không benchmark phá hoại trên production

Benchmark ghi có thể ghi đè dữ liệu, làm đầy volume, tạo log/WAL lớn và gây latency cho database. Chỉ dùng file thử nghiệm hoặc volume tách biệt có thể xóa; xác minh đường dẫn trước khi chạy. Không dùng raw device hoặc file database đang hoạt động làm đích ghi thử.

Nếu cần đo production, ưu tiên quan sát workload thật hoặc dùng công cụ kiểm thử có giới hạn I/O, thời gian và phạm vi được phê duyệt. Tránh chạy index rebuild, fio random write hoặc DiskSpd write nặng trong giờ phục vụ nếu chưa có cửa sổ và kế hoạch tác động.

## 14. Ví dụ chẩn đoán: IOPS cao nhưng truy vấn vẫn chậm

Giả sử dashboard báo volume đạt 90.000 IOPS, nhưng truy vấn lấy một số ít bản ghi qua index vẫn có p99 cao. IOPS lớn không đủ để kết luận volume còn dư năng lực.

### 14.1. Kiểm tra loại I/O

Đầu tiên tách read và write IOPS, block size, throughput và latency. Có thể 90.000 IOPS chủ yếu là read-ahead 128 KiB hoặc request nhỏ từ một workload khác; truy vấn mục tiêu lại chờ random read 8 KiB trên volume khác.

### 14.2. Kiểm tra cache và physical read

Đo logical reads, buffer cache hit và physical reads của truy vấn. Nếu logical reads lớn nhưng physical reads thấp, vấn đề có thể là CPU hoặc truy cập buffer page; nếu physical reads cao, xem storage latency và access path.

### 14.3. Kiểm tra queue và tail latency

Đọc p95/p99 read latency và queue depth theo volume, không chỉ IOPS tổng. Nếu IOPS plateau, queue tăng và p99 tăng, thiết bị hoặc backend có thể đang bão hòa. Nếu queue thấp nhưng database wait cao, xem scheduler, network path hoặc queue ở tầng khác.

### 14.4. Kiểm tra kế hoạch truy vấn

Đọc execution plan, số lần lookup, actual rows, index selectivity và số trang phải đọc. Một truy vấn cần hàng nghìn random lookups có thể được cải thiện bằng covering index, join strategy hoặc giảm số hàng trước khi truy cập bảng. Tăng IOPS chỉ xử lý phần chi phí storage, không loại bỏ số lần đọc không cần thiết.

## 15. Ví dụ chẩn đoán: throughput cao nhưng commit chậm

Một workload bulk load đạt throughput ghi 600 MiB/s, nhưng giao dịch OLTP có commit p99 tăng từ 5 ms lên 35 ms. Có thể bulk load đang chiếm băng thông hoặc làm tăng write queue; cũng có thể checkpoint và log flush dùng chung backend.

Quy trình điều tra:

1. Tách throughput của data file, transaction log và temp volume.
2. Đo write latency riêng cho log flush và data write.
3. Xem queue depth và p99 latency trong thời gian bulk load.
4. Đối chiếu checkpoint write rate, dirty pages và WAL/redo generation.
5. Kiểm tra bulk load có tạo index, sort hoặc temp spill lớn không.
6. Thử giới hạn tốc độ bulk load hoặc chuyển lịch chạy, rồi so sánh commit p99.
7. Xác nhận log và data có thực sự tách tài nguyên backend.

Nếu commit cải thiện khi giảm bulk load, có bằng chứng về tranh chấp I/O. Tuy nhiên, vẫn cần phân tích queue và wait để biết nút thắt nằm ở bandwidth, IOPS, flush latency hay lock. Không nên chỉ dựa vào throughput trung bình.

## 16. Các cách giảm nhu cầu I/O trước khi tăng storage

1. **Cải thiện access path:** tạo index phù hợp, tránh scan không cần thiết và giảm lookup lặp.
2. **Giảm số hàng:** lọc sớm, partition pruning và giới hạn dữ liệu trung gian trước join/sort.
3. **Giảm độ rộng hàng:** chỉ đọc cột cần thiết, cân nhắc covering index và tránh lấy LOB/JSON thừa.
4. **Tăng locality:** chọn clustering hoặc thứ tự lưu trữ phù hợp với truy vấn phổ biến khi engine hỗ trợ.
5. **Kiểm soát cache:** xác định buffer pool có đủ cho working set và tránh workload scan làm nhiễu cache.
6. **Giảm spill:** cải thiện thống kê, cardinality estimate, memory grant và truy vấn để giảm temp I/O.
7. **Điều tiết checkpoint/backup:** tránh write burst và cạnh tranh với workload trực tuyến.
8. **Giảm write amplification:** xem index trùng, trigger và cập nhật không cần thiết.
9. **Điều chỉnh concurrency:** tránh phát quá nhiều I/O outstanding khiến queue và p99 tăng.
10. **Tách tài nguyên đúng nghĩa:** đặt log, data, temp trên backend riêng khi có bằng chứng tranh chấp và kiến trúc storage hỗ trợ.

Sau khi giảm công việc I/O, đo lại để xác định storage có còn là nút thắt. Chỉ tăng IOPS/throughput provisioned hoặc chuyển tier khi số liệu chứng minh nhu cầu vượt năng lực hiện tại.

## 17. Quy trình phân tích nút thắt I/O

1. **Xác định phạm vi:** truy vấn, database, file, volume, host hay toàn cụm.
2. **Thu thập baseline:** IOPS read/write, throughput, latency p50/p95/p99, queue depth và utilization.
3. **Phân loại kích thước/pattern:** block size, random/sequential, read/write mix và burst/steady state.
4. **Đối chiếu database:** logical/physical reads, writes, log flush, checkpoint, temp spill và wait events.
5. **Đối chiếu OS/storage:** volume mapping, queue từng tầng, throttling, instance cap, network và backend metrics.
6. **Tìm nguồn phát sinh I/O:** query plan, scan, index lookup, backup, ETL, checkpoint, rebuild hoặc replication.
7. **Đặt giả thuyết cụ thể:** IOPS cap, throughput cap, tail latency, queue saturation, cache miss hoặc tranh chấp backend.
8. **Thay đổi một yếu tố:** giảm scan, điều tiết batch, tách workload, đổi storage tier hoặc điều chỉnh concurrency.
9. **Đo lại cùng workload:** cùng data, cache state, thời gian, concurrency và cửa sổ tải.
10. **Xác nhận SLO:** latency percentile, throughput, queue, error rate và hiệu năng truy vấn quan trọng đều đạt mục tiêu.

## 18. Những lỗi thường gặp

- **Chỉ nhìn IOPS:** bỏ qua block size, throughput, read/write mix và latency.
- **Chỉ nhìn MB/s:** không phát hiện workload random nhỏ đang chạm giới hạn IOPS.
- **Chỉ nhìn average latency:** che p95/p99 và các spike ngắn.
- **Tăng queue depth để tăng IOPS:** có thể chỉ làm queue và latency phình ra khi thiết bị đã bão hòa.
- **So sánh benchmark khác block size:** kết luận sai về năng lực giữa hai volume.
- **Dùng sequential benchmark để đại diện OLTP:** không phản ánh random lookup và log flush.
- **Nhầm logical reads với physical I/O:** cache hit có thể khiến database không truy cập storage.
- **Đọc `%util` như phần trăm công suất tuyệt đối:** cách tính không phản ánh đầy đủ thiết bị nhiều queue hoặc storage ảo.
- **Tách volume logic nhưng chung backend:** không loại bỏ tranh chấp vật lý.
- **Benchmark quá ngắn:** chỉ đo burst/cache và bỏ qua sustained performance.
- **Chạy benchmark ghi trên volume production:** có thể ghi đè dữ liệu hoặc làm gián đoạn workload.
- **Mua IOPS trước khi đọc execution plan:** trả thêm chi phí nhưng vẫn giữ nguyên số lần đọc không cần thiết.
- **Không phân biệt data/log/temp:** không tìm ra nhóm I/O đang làm p99 tăng.

## 19. Bài tập tự kiểm tra

**Bài 1.** Volume đạt 30.000 IOPS với block 4 KiB. Throughput lý thuyết xấp xỉ bao nhiêu MiB/s nếu mọi request có cùng kích thước?

*Gợi ý:* `30.000 × 4.096 / 1.048.576`, xấp xỉ 117,2 MiB/s.

**Bài 2.** Một thiết bị có throughput 500 MiB/s nhưng truy vấn OLTP vẫn chậm. Những phép đo nào cần bổ sung?

*Gợi ý:* Random read IOPS, block size, read/write latency p95/p99, queue depth, physical reads, cache hit và wait events; throughput lớn có thể đến từ sequential I/O khác.

**Bài 3.** IOPS không tăng thêm khi queue depth tăng từ 32 lên 128, nhưng p99 latency tăng gấp ba. Bạn kết luận gì?

*Gợi ý:* Thiết bị/backend có thể đã bão hòa; các yêu cầu thêm chủ yếu chờ. Cần giảm concurrency hoặc I/O dư thừa, xem throttling và giới hạn provisioned.

**Bài 4.** Database báo nhiều logical reads nhưng storage IOPS thấp. Vì sao hai số không mâu thuẫn?

*Gợi ý:* Nhiều logical read có thể được phục vụ từ buffer pool; chỉ một phần trở thành physical read.

**Bài 5.** Backup làm commit latency tăng. Những mối liên hệ nào cần kiểm tra?

*Gợi ý:* Backup throughput, read queue, data/log backend dùng chung, checkpoint, storage bandwidth, log flush latency và p99 commit theo thời gian.

**Bài 6.** Vì sao không nên chọn queue depth tối đa của benchmark làm cấu hình mặc định cho database?

*Gợi ý:* Benchmark tối đa hóa một metric có thể đẩy latency lên cao. Workload thực có concurrency, read/write mix và SLO khác; cần chọn điểm cân bằng throughput và percentile latency.

## 20. Ghi nhớ khi tối ưu

IOPS cho biết số thao tác mỗi giây; throughput cho biết lượng byte mỗi giây; latency cho biết thời gian hoàn tất; queue depth cho biết số yêu cầu đang outstanding. Kích thước I/O và loại truy cập quyết định mối quan hệ giữa các đại lượng này. Random I/O nhỏ thường nhạy với IOPS và latency; sequential I/O lớn thường nhạy với throughput; queue depth giúp khai thác song song nhưng quá cao có thể làm tail latency tăng.

Để chẩn đoán database, hãy đo read/write riêng, phân biệt data/log/temp, đối chiếu logical và physical I/O, xem latency percentile và queue ở cả database, hệ điều hành lẫn storage backend. Kiểm tra workload tạo ra yêu cầu trước khi tăng capacity. Một thay đổi chỉ được xác nhận khi giảm được công việc hoặc cải thiện SLO dưới workload đại diện mà không tạo nút thắt mới.
