# Mở rộng tài nguyên một máy và giới hạn của đường ghi

Khi tải cơ sở dữ liệu tăng, cách trực tiếp nhất thường là tăng tài nguyên cho máy chủ đang chạy DBMS: thêm CPU, RAM, dung lượng và năng lực I/O của storage, hoặc dùng một instance có cấu hình lớn hơn. Cách mở rộng này thường được gọi là scale-up hay vertical scaling. Nó có thể tăng khả năng xử lý mà không cần thay đổi ngay mô hình ứng dụng, phân vùng dữ liệu hoặc cách định tuyến truy vấn.

Tuy nhiên, một máy chủ không thể tăng tài nguyên vô hạn. Một truy vấn chỉ tăng tốc đến mức mà các phần việc của nó có thể chạy song song; nhiều transaction vẫn phải phối hợp qua khóa, cấu trúc index và nhật ký giao dịch; mọi thao tác ghi bền vững phải đi qua đường ghi của storage. Khi một thành phần đã bão hòa hoặc một điểm nóng buộc nhiều session chờ cùng nhau, thêm CPU hay RAM có thể không làm throughput ghi tăng tương ứng.

Trong chương **Mở rộng hệ thống**, bài học này phân tích cách mở rộng tài nguyên trên một máy và giới hạn của đường ghi. Nội dung gắn với mục tiêu của module **DATABASE_PERFORMANCE**: rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Ta sẽ đánh giá CPU, bộ nhớ, NUMA, storage và network; hiểu các giới hạn do phần việc tuần tự, log flush, hot row, index page và write amplification; sau đó xây dựng quy trình capacity planning và benchmark để xác định thời điểm scale-up còn hiệu quả.

Một quyết định scale-up tốt phải trả lời được ba câu hỏi: tài nguyên nào đang giới hạn workload, tăng tài nguyên đó có làm tăng năng lực xử lý thực tế hay không, và hệ thống sẽ chạm giới hạn tiếp theo ở đâu.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt scale-up với scale-out và xác định khi nào mở rộng một máy là phù hợp.
- Đánh giá CPU, RAM, memory bandwidth, NUMA, storage IOPS/throughput/latency và network.
- Giải thích vì sao tăng số core không làm mọi truy vấn hoặc transaction nhanh hơn theo tỷ lệ tương ứng.
- Dùng Amdahl's Law và queueing để hiểu lợi ích giảm dần khi tăng tài nguyên.
- Nhận diện giới hạn của đường ghi: log generation, log flush, group commit, hot row, index contention và checkpoint.
- Phân biệt dung lượng lưu trữ với năng lực ghi bền vững.
- Hiểu write amplification do index, page split, WAL/redo và checkpoint.
- Lập baseline để đo throughput, latency, utilization và queueing trước khi scale.
- Xây dựng capacity plan có headroom, tăng trưởng và ngưỡng cảnh báo.
- Xác minh hiệu quả scale-up bằng workload đại diện và theo dõi bottleneck mới.

## 1. Scale-up trên một máy là gì?

### 1.1. Tăng tài nguyên tại cùng một node

Scale-up là tăng năng lực của máy đang chạy DBMS hoặc chuyển sang một máy/instance lớn hơn. Những thành phần thường được mở rộng:

- **CPU:** thêm core/vCPU, tăng xung nhịp hoặc dùng thế hệ CPU mới.
- **RAM:** tăng dung lượng để mở rộng buffer cache, working set và vùng xử lý truy vấn.
- **Memory bandwidth:** tăng số kênh RAM hoặc dùng nền tảng có băng thông bộ nhớ cao hơn.
- **Storage:** tăng IOPS, throughput, dung lượng, giảm latency hoặc dùng thiết bị có khả năng flush tốt hơn.
- **Network:** tăng băng thông, cải thiện NIC hoặc giảm hop giữa ứng dụng và DBMS.
- **I/O path:** cải thiện controller, queue, filesystem, virtualization và cấu hình cache/flush.

Scale-up thường giữ nguyên endpoint database, transaction boundary và phần lớn logic ứng dụng. Vì vậy, nó có thể là bước mở rộng ít thay đổi kiến trúc hơn so với phân tán dữ liệu.

### 1.2. Scale-up khác scale-out

| Tiêu chí | Scale-up | Scale-out |
|---|---|---|
| Cách tăng năng lực | Tăng tài nguyên của một node | Thêm node và phân phối workload/dữ liệu |
| Thay đổi ứng dụng | Thường ít hơn | Có thể cần routing, partitioning hoặc replication |
| Giới hạn | Trần phần cứng/instance và điểm nghẽn nội bộ | Network, coordination, consistency và phân phối dữ liệu |
| Dữ liệu ghi | Có thể tiếp tục tập trung trên một node | Phải xác định node chịu trách nhiệm ghi và cách đồng bộ |
| Vận hành | Ít node hơn nhưng node lớn và có thể đắt | Nhiều thành phần và cơ chế điều phối hơn |
| Phù hợp | Workload tập trung, còn dư khả năng mở rộng dọc | Đã chạm trần node hoặc cần phân phối tải/dữ liệu |

Scale-out không tự động loại bỏ giới hạn ghi. Nếu mọi transaction vẫn phải ghi vào cùng một primary hoặc cùng một partition nóng, thêm read replica hoặc thêm application server không làm đường ghi đó tăng năng lực tương ứng.

### 1.3. Khi nào nên scale-up?

Scale-up đáng cân nhắc khi:
- CPU, memory hoặc storage trên node hiện tại đã gần bão hòa.
- Workload có thể hưởng lợi từ tài nguyên bổ sung.
- DBMS và nền tảng hỗ trợ cấu hình lớn hơn.
- Chi phí thay đổi ứng dụng để scale-out cao.
- Dữ liệu và transaction cần duy trì một điểm điều phối nhất quán.
- Vẫn còn headroom trong giới hạn instance, licensing và hạ tầng.

Không nên scale-up chỉ vì server utilization cao trong một khoảng ngắn. Cần xem xu hướng, p95/p99, queueing, throughput và loại tài nguyên thực sự bị giới hạn.

## 2. CPU: thêm core không đồng nghĩa tăng tốc tuyến tính

### 2.1. Các loại công việc dùng CPU

DBMS dùng CPU cho:
- Parse, optimize và execute SQL.
- Predicate evaluation, expression và function.
- Join, sort, aggregate và window operations.
- Kiểm tra constraint, trigger và transaction metadata.
- Mã hóa, nén, checksum và xử lý protocol.
- Background tasks như checkpoint, vacuum, purge hoặc compression tùy engine.

Nếu workload CPU-bound và có đủ phần việc độc lập, thêm core có thể tăng throughput. Nếu truy vấn chủ yếu chờ storage, lock hoặc log flush, thêm core có thể không cải thiện đáng kể.

### 2.2. Phần tuần tự giới hạn speedup

Một số bước của query plan hoặc transaction phải phối hợp theo thứ tự. Amdahl's Law mô tả giới hạn lý tưởng khi chỉ một phần công việc có thể song song:

~~~text
speedup <= 1 / (s + (1 - s) / P)
~~~

Trong đó:
- **s** là tỷ lệ công việc không thể song song.
- **P** là số worker/core tham gia phần song song.

Ví dụ nếu 20% công việc phải thực hiện tuần tự, tăng số worker rất lớn vẫn không thể làm toàn bộ công việc nhanh hơn vô hạn. Công thức chưa tính overhead tạo worker, đồng bộ, memory contention, I/O và data skew; hiệu quả thực tế thường thấp hơn.

### 2.3. Frequency, core count và hiệu năng đơn luồng

Một truy vấn OLTP ngắn có thể phụ thuộc nhiều vào latency của một luồng xử lý hơn là tổng số core. Máy có nhiều core nhưng xung nhịp thấp hơn có thể không cải thiện latency đơn truy vấn như mong đợi.

Khi so sánh hai cấu hình CPU, xem:
- Single-thread performance.
- Số core và logical CPU được DBMS thực sự sử dụng.
- CPU quota/vCPU trong môi trường ảo hóa.
- Memory bandwidth và NUMA topology.
- Hiệu năng dưới tải liên tục, không chỉ turbo frequency ngắn hạn.
- Licensing theo core hoặc socket nếu có.

### 2.4. CPU saturation và runnable queue

CPU utilization cao chỉ là một phần tín hiệu. Hãy đo cùng lúc:
- CPU utilization theo process và theo core.
- Runnable queue hoặc CPU pressure.
- Context switching.
- DB worker/thread scheduling waits.
- Throughput và p95/p99 latency.
- CPU time so với elapsed time của truy vấn.

Nếu CPU đạt mức cao kéo dài, runnable queue tăng và throughput không tăng dù concurrency tăng, node có thể đã chạm giới hạn CPU. Nếu CPU thấp nhưng latency cao, hãy điều tra I/O, lock, memory grant, worker pool hoặc network.

### 2.5. Không cấp quá nhiều worker

Tăng DOP hoặc số worker cho mỗi query có thể làm một báo cáo nhanh hơn khi chạy riêng. Nhưng nhiều query song song cùng lúc có thể tạo oversubscription, context switching và tranh chấp memory. Scale-up CPU nên được đánh giá cùng chính sách parallelism và concurrency.

## 3. RAM, buffer cache và giới hạn memory bandwidth

### 3.1. RAM giúp giảm đọc storage

Buffer cache giữ các page dữ liệu và index thường được truy cập. Nếu working set quan trọng nằm trong RAM, DBMS có thể giảm physical reads và phục vụ nhiều truy vấn từ memory.

Tăng RAM có thể giúp khi:
- Working set lớn hơn cache hiện tại.
- Cache eviction cao và truy vấn lặp lại cùng dữ liệu.
- Physical reads tạo latency đáng kể.
- DBMS cần thêm memory cho sort/hash hoặc workload đồng thời.

Nhưng tăng RAM không làm một query có predicate kém chọn lọc trở nên hiệu quả. Nếu truy vấn đọc toàn bộ bảng, CPU hoặc memory bandwidth có thể trở thành giới hạn tiếp theo.

### 3.2. Cache hit ratio không đủ để quyết định

Một cache hit ratio cao không chứng minh hệ thống tối ưu. Cache có thể phục vụ rất nhiều logical reads do query đọc lặp lại cùng page. Một query có logical reads cực lớn vẫn gây CPU và memory bandwidth pressure dù không có physical I/O.

Cần xem:
- Logical reads/buffer gets.
- Physical reads và bytes đọc.
- Buffer cache hit theo workload.
- Page eviction và memory pressure.
- Rows examined so với rows returned.
- CPU time trên mỗi request.

### 3.3. Memory bandwidth

CPU cần đọc/ghi dữ liệu trong RAM khi xử lý page, hash table, sort buffer và metadata. Khi nhiều core cùng truy cập memory, memory bandwidth có thể bão hòa trước khi CPU utilization đạt tối đa.

Dấu hiệu có thể gồm throughput không tăng khi thêm core, memory controller utilization cao hoặc hiệu năng giảm dưới workload scan/hash lớn. Khả năng quan sát phụ thuộc phần cứng và hệ điều hành.

### 3.4. Memory grant và concurrency

Sort/hash operations cần vùng nhớ tạm. Tăng RAM có thể cho phép DBMS cấp grant lớn hơn hoặc giữ cache lớn hơn, nhưng tổng memory tiêu thụ còn phụ thuộc số truy vấn đồng thời và số operator/worker.

Một query được cấp nhiều memory có thể giảm spill nhưng làm query khác chờ grant. Không đặt memory limit chỉ theo một benchmark đơn truy vấn; phải thử concurrency và bảo đảm RAM cho OS, DBMS background processes và connection workload.

### 3.5. NUMA và locality

Máy nhiều socket thường có kiến trúc Non-Uniform Memory Access (NUMA). CPU truy cập RAM cục bộ nhanh hơn RAM thuộc node khác. Khi worker và memory page phân bố không phù hợp, truy cập remote memory có thể tăng latency hoặc giảm bandwidth hiệu dụng.

Khi scale-up sang máy nhiều socket:
- Xác định số NUMA nodes và memory channels.
- Kiểm tra DBMS có nhận diện NUMA và cấu hình affinity phù hợp không.
- Theo dõi CPU/memory usage theo node.
- Tránh ép affinity thủ công nếu chưa có số liệu.
- Benchmark workload song song với kích thước working set thực tế.

## 4. Storage: dung lượng, IOPS, throughput và latency

### 4.1. Bốn thuộc tính khác nhau

Storage cần được đánh giá theo ít nhất bốn chiều:

| Thuộc tính | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| Capacity | Tổng dung lượng có thể lưu | Có đủ chỗ cho data, index, log, temp và tăng trưởng không? |
| IOPS | Số thao tác I/O mỗi giây | Có phục vụ đủ các request nhỏ/ngẫu nhiên không? |
| Throughput | Bytes truyền mỗi giây | Có đủ băng thông cho scan, backup và bulk load không? |
| Latency | Thời gian hoàn tất một thao tác I/O | Commit flush hoặc page read có phải chờ lâu không? |

Tăng dung lượng không tự tăng IOPS hoặc giảm latency. Một volume lớn có thể vẫn có giới hạn throughput/IOPS theo tier, số disk, queue hoặc quota của cloud provider.

### 4.2. Random I/O và sequential I/O

Index lookup có thể tạo nhiều random reads nhỏ. Table scan và log append thường có access pattern khác, có thể tận dụng sequential throughput hoặc read-ahead.

Không thể chỉ so sánh MB/s:
- Workload random nhỏ có thể bị giới hạn IOPS/latency.
- Scan lớn có thể bị giới hạn bandwidth.
- Commit log có thể nhạy với durable flush latency.
- Checkpoint có thể tạo nhiều data page writes và cạnh tranh với log.

Đo theo loại I/O và volume thực tế mà DBMS sử dụng.

### 4.3. Queue depth và điểm bão hòa

Queue depth cho biết số request I/O đang chờ hoặc được xử lý. Tăng queue có thể cải thiện utilization của thiết bị đến một điểm. Khi queue quá dài, latency tăng và request phải chờ lâu hơn.

Hãy theo dõi IOPS, throughput, average/p95/p99 latency, queue depth và outstanding requests. Nếu thêm worker chỉ làm queue dài hơn mà throughput không tăng, storage đã gần hoặc vượt vùng hiệu quả.

### 4.4. Durable flush và cache semantics

Transaction log cần được ghi bền vững theo cấu hình durability. DBMS có thể yêu cầu fsync hoặc cơ chế tương đương để bảo đảm dữ liệu log đã đi qua các tầng cache cần thiết.

Một storage controller hoặc virtualized layer có write-back cache nhưng không bảo đảm battery/flash-backed protection hoặc flush semantics đúng có thể làm durability suy yếu. Khi chọn storage, xác minh:
- Hành vi flush/FUA theo nền tảng.
- Cache protection và power-loss protection.
- Durability guarantees của cloud block storage.
- Latency p95/p99 của synchronous write.
- Tính nhất quán của metric từ guest OS và storage provider.

Không tắt fsync hoặc giảm durability để bù cho storage chậm. Cần chọn storage phù hợp với yêu cầu phục hồi.

## 5. Đường ghi trên một máy và các giới hạn khó mở rộng

### 5.1. Các bước chính của write path

Một transaction ghi thường phải:
1. Tìm và khóa dữ liệu cần thay đổi.
2. Đọc page vào buffer nếu chưa có.
3. Thay đổi page trong memory.
4. Tạo log record cho thay đổi.
5. Khi commit, bảo đảm log cần thiết được flush theo durability mode.
6. Trả commit acknowledgement.
7. Ghi dirty data page xuống data file sau đó qua background writer/checkpoint.

Chi tiết khác nhau giữa DBMS, nhưng nguyên tắc WAL/redo phổ biến là log cần thiết phải được ghi trước data page tương ứng. Vì vậy, commit latency có thể bị giới hạn bởi log flush ngay cả khi data page chưa được ghi xuống file bảng.

### 5.2. Log stream và durable flush

Nhiều transaction có thể tạo log records đồng thời, nhưng engine phải duy trì thứ tự log cần thiết và xác định điểm commit bền vững. Các transaction thường chia sẻ một hoặc một số log streams; khả năng mở rộng của đường log phụ thuộc engine, cấu hình và storage.

Nếu mỗi transaction nhỏ đều phải chờ flush, storage latency có thể giới hạn commits/s. Group commit cho phép nhiều transaction chia sẻ một lần flush, nhưng không loại bỏ chi phí durable I/O hoặc mọi coordination.

Khi scale-up CPU, log flush có thể vẫn là nút thắt. Khi scale-up storage, hot row hoặc log coordination có thể trở thành giới hạn tiếp theo.

### 5.3. Hot row và lock contention

Ví dụ nhiều session cùng cập nhật một counter:

~~~sql
UPDATE inventory_summary
SET total_reserved = total_reserved + 1
WHERE product_id = 101;
~~~

Nếu một product_id nhận phần lớn traffic, nhiều transaction tranh chấp cùng row hoặc index entry. Thêm CPU không cho phép mọi transaction cập nhật cùng trạng thái đồng thời mà bỏ qua thứ tự và isolation.

Có thể đánh giá:
- Lock wait duration và blocking chains.
- Deadlocks và retry.
- Hot key distribution.
- Transaction duration.
- Rows/updates per key.
- Wait events liên quan latch/mutex hoặc page contention.

Giải pháp có thể gồm rút ngắn transaction, giảm thao tác cập nhật lặp, batch, sharded counters hoặc thay đổi data model. Mỗi cách có trade-off về consistency và chi phí đọc/tổng hợp.

### 5.4. Index page contention và write amplification

Mỗi index cần được duy trì khi dữ liệu thay đổi. Một INSERT có thể ghi table page, nhiều index leaf pages, log records và metadata. UPDATE cột nằm trong index có thể phải thay đổi index entry. Index rộng hoặc nhiều index làm tăng bytes ghi và cache pressure.

Với khóa tăng tuần tự, nhiều INSERT có thể tập trung vào leaf page cuối của B-tree. Tùy engine và cấu trúc index, đây có thể là điểm nóng về latch hoặc page split. Với key phân tán ngẫu nhiên, hot end có thể giảm nhưng random I/O và page locality có thể xấu đi.

Không có một kiểu key tốt cho mọi workload. Đo page split, insert contention, log bytes và storage I/O trước khi thay đổi fill factor, key order hoặc partitioning.

### 5.5. Checkpoint và dirty page flushing

Dirty pages được ghi xuống data files theo lịch của DBMS. Checkpoint giúp giới hạn công việc crash recovery và quản lý dirty buffers. Nếu nhiều page được flush trong một khoảng ngắn, data I/O có thể cạnh tranh với log flush và query reads.

Khi scale-up storage, hãy đo cả log write latency lẫn data write throughput. Một thiết bị có thể phục vụ tốt log flush nhưng bị giới hạn bởi checkpoint bursts, hoặc ngược lại.

### 5.6. Transaction size và commit frequency

Transaction rất nhỏ tạo nhiều commit và coordination. Transaction quá lớn tạo nhiều log, giữ lock lâu, tăng rollback cost và có thể làm log retention hoặc recovery phức tạp hơn.

Tìm kích thước transaction phù hợp:
- Gom các thao tác thuộc cùng đơn vị nghiệp vụ.
- Không giữ transaction trong lúc gọi dịch vụ bên ngoài.
- Batch với kích thước được benchmark.
- Chia batch lớn chỉ khi nghiệp vụ chấp nhận trạng thái trung gian.
- Dùng idempotency/retry khi chia lô hoặc xử lý lỗi giữa chừng.

## 6. Network và khoảng cách đến ứng dụng

### 6.1. CPU/storage nhanh hơn không xóa RTT

Nếu ứng dụng ở xa DBMS và gửi nhiều SQL tuần tự, mỗi round trip vẫn tạo độ trễ. Scale-up máy DB không làm giảm khoảng cách mạng hoặc số lần ứng dụng phải chờ phản hồi.

Đo riêng:
- Connection pool wait.
- TCP/TLS setup nếu có.
- Network RTT và retransmission.
- DB execution/wait.
- Result transfer và driver decoding.

### 6.2. Connection pool và giới hạn session

Tăng số kết nối không đồng nghĩa tăng năng lực DBMS. Nếu DBMS đã bão hòa CPU, memory hoặc I/O, thêm session có thể làm queueing và context switching tăng.

Pool nên được định cỡ theo throughput, thời gian giữ connection và capacity test. Nếu request chờ pool nhưng DBMS còn dư capacity, có thể cần điều chỉnh pool; nếu DBMS đã bão hòa, tăng pool thường chỉ đẩy hàng đợi sâu hơn.

### 6.3. Khi nào network là bottleneck?

Nếu DB execution time thấp nhưng API latency cao, số query mỗi request lớn, RTT cao hoặc result set lớn, network/application path có thể là nút thắt. Giảm round trips, N+1, payload và connection setup có thể đem lại lợi ích mà scale-up DB không giải quyết.

## 7. Diminishing returns và điểm nghẽn dịch chuyển

### 7.1. Bottleneck dịch chuyển

Khi tăng một tài nguyên, bottleneck có thể chuyển sang thành phần khác:

| Sau khi tăng | Bottleneck cũ được giảm | Bottleneck có thể xuất hiện tiếp |
|---|---|---|
| Thêm CPU | Runnable queue, CPU execution | Storage, log flush, lock, memory bandwidth |
| Thêm RAM | Physical reads, cache eviction | CPU, logical reads, storage writes |
| Storage nhanh hơn | I/O latency hoặc throughput | CPU, log serialization, hot row |
| Tăng DOP | Thời gian scan/aggregate đơn query | CPU contention, memory grant, temp I/O |
| Tăng connection pool | Pool wait ở ứng dụng | DB session contention, worker, locks |
| Tăng network bandwidth | Truyền result lớn | RTT, số round trips, DB execution |

Sau mỗi thay đổi, phải đo lại toàn hệ thống. Đừng tiếp tục scale cùng một chiều nếu bottleneck đã chuyển.

### 7.2. Diminishing returns

Lợi ích giảm dần xuất hiện khi phần tài nguyên mới không còn là giới hạn chính. Ví dụ tăng RAM từ 64 GB lên 128 GB có thể giảm physical reads mạnh nếu working set trước đó không vừa cache. Tăng tiếp lên 256 GB có thể ít tác dụng nếu workload đã chủ yếu cache-hit và CPU đang bão hòa.

Tương tự, thêm core có thể giúp throughput đến khi storage, log flush hoặc lock contention giới hạn. Tăng tài nguyên sau điểm đó làm chi phí tăng nhanh hơn lợi ích.

### 7.3. Capacity không đồng nghĩa performance

Dung lượng disk tăng giúp lưu thêm dữ liệu và tránh hết chỗ, nhưng không nhất thiết tăng tốc truy vấn. RAM lớn hơn có thể cải thiện cache nhưng không sửa query đọc quá nhiều dòng. CPU nhiều hơn không giải quyết hot row. Cần xác định mục tiêu: tăng dung lượng, tăng throughput, giảm latency hay tăng headroom.

## 8. Quy trình xác định tài nguyên cần scale

### Bước 1: Xác định workload và SLA

Ghi loại workload, transaction mix, throughput mục tiêu, p95/p99 latency, giờ cao điểm, batch window, RPO/RTO và mức tăng trưởng dự kiến.

### Bước 2: Thu baseline

Thu ít nhất:
- CPU utilization, runnable queue và CPU time.
- RAM, buffer cache, memory pressure và spill.
- Storage IOPS, throughput, latency, queue depth theo volume.
- Log bytes/s, flushes/s và log flush latency.
- Dirty pages, checkpoint duration và write rate.
- Active sessions, connection pool wait, lock/latch waits.
- Query fingerprint, actual plan, rows read/returned.
- Network RTT, bytes, retransmission và result fetch time.

### Bước 3: Phân loại bottleneck

Dùng dấu hiệu kết hợp, không dựa vào một metric:
- CPU-bound: CPU cao, runnable queue tăng, query CPU time lớn.
- Memory-bound: pressure, cache eviction, grant wait hoặc spill.
- I/O-bound: storage latency/queue cao, physical I/O lớn.
- Log-bound: commit wait và synchronous flush latency cao.
- Lock-bound: blocking/hot key/lock waits cao.
- Network-bound: DB time thấp nhưng application latency và RTT/fetch time cao.

### Bước 4: Ước lượng hiệu quả của scale-up

Ước lượng tài nguyên bổ sung có thể giảm phần chi phí nào. Ví dụ:
- Thêm RAM có đủ đưa working set nóng vào cache không?
- Thêm CPU có tăng phần việc song song không?
- Storage mới có giảm durable flush latency hay chỉ tăng capacity?
- Thêm network bandwidth có giải quyết bottleneck nếu workload thực ra bị RTT-bound không?

### Bước 5: Kiểm tra giới hạn nền tảng

Xác minh trần vCPU, RAM, IOPS, throughput, network bandwidth, instance family, NUMA, licensing và khả năng mở rộng nóng/lạnh. Với cloud, kiểm tra burst credits, quota, shared tenancy và giới hạn theo volume/instance.

### Bước 6: Thử trên môi trường đại diện

Dùng cùng dữ liệu, DBMS version, schema, index, statistics, parameter mix, cache state và durability settings. Chạy workload đọc/ghi hỗn hợp ở nhiều mức concurrency.

### Bước 7: So sánh trước và sau

So sánh throughput, p50/p95/p99, CPU, memory, I/O, log flush, lock waits và chi phí vận hành. Kiểm tra query không mục tiêu để phát hiện regression.

### Bước 8: Xác định bottleneck mới

Sau scale-up, quay lại bước phân loại. Không mặc định tài nguyên vừa tăng sẽ tiếp tục là bottleneck chính.

## 9. Ví dụ: scale-up không tăng được commits/s

Một hệ thống xử lý đơn hàng chạy trên một DB node. Khi tải tăng, đội vận hành chuyển instance từ 16 vCPU/64 GB RAM sang 32 vCPU/128 GB RAM. CPU utilization giảm từ 95% xuống 55%, nhưng commits/s chỉ tăng nhẹ và p99 commit latency gần như không đổi.

Một hướng điều tra:

1. Đo commit latency và wait events liên quan log flush.
2. Kiểm tra log bytes/s, flushes/s và bytes mỗi flush.
3. Đo durable write latency của volume chứa transaction log.
4. Xem group commit có gom được nhiều transaction không.
5. Kiểm tra checkpoint có tạo data I/O cạnh tranh không.
6. Phân tích lock waits và hot rows trong bảng inventory/counter.
7. Kiểm tra số index được cập nhật mỗi transaction và log bytes/transaction.
8. Đo transaction duration, commits/s và batch size.
9. Benchmark storage có durable flush latency thấp hơn trong cùng semantics.
10. Thử batch vừa phải hoặc giảm cập nhật hot row nếu nghiệp vụ cho phép.

Nếu log flush latency vẫn cao, thêm CPU không giải quyết nút thắt. Nếu storage flush đã nhanh nhưng hot row wait lớn, cần thay đổi transaction/data access pattern. Nếu group commit thấp do ứng dụng commit từng request rất nhỏ và tải phân tán, cần đo cách driver/DBMS thực hiện flush và xem batching có phù hợp hay không.

Không giảm durability để làm số commits/s đẹp hơn. Cần giữ cùng yêu cầu durability khi so sánh cấu hình production.

## 10. Capacity planning và headroom

### 10.1. Dự báo tăng trưởng

Capacity plan nên xem:
- Tăng trưởng số dòng và dung lượng data/index.
- Tăng trưởng log bytes/ngày và tốc độ cao điểm.
- Tăng trưởng query/transaction rate.
- Working set và tỷ lệ cache.
- Backup, archive, temp và maintenance space.
- Replication lag và log retention.
- Thời gian phục hồi khi database lớn hơn.

Dung lượng cần thiết không chỉ là kích thước file data hiện tại. Phải tính index, WAL/redo, temp, backup staging, free space cho maintenance và headroom.

### 10.2. Headroom

Không vận hành liên tục ở sát giới hạn CPU, RAM, IOPS hoặc bandwidth. Headroom giúp hấp thụ burst, checkpoint, backup, failover và tăng trưởng ngắn hạn.

Ngưỡng headroom cần dựa trên workload và SLA, không dùng một tỷ lệ cố định cho mọi hệ thống. Theo dõi cả mức sử dụng và độ trễ/queueing; utilization thấp nhưng latency cao vẫn có thể là vấn đề.

### 10.3. Cost per transaction

Khi so sánh instance, xem chi phí trên mỗi transaction thành công hoặc trên một đơn vị workload, không chỉ giá instance hoặc throughput tối đa. Cấu hình lớn hơn có thể có hiệu năng cao hơn nhưng tỷ lệ cost/performance xấu hơn nếu bottleneck nằm ở log flush hoặc hot row.

Tính cả:
- License theo core.
- Storage tier và provisioned IOPS.
- Network transfer.
- Backup và replication.
- Downtime/migration.
- Chi phí vận hành và năng lực đội ngũ.

### 10.4. Trần tăng trưởng dọc

Mỗi nền tảng có trần instance, socket, RAM, storage attachment, IOPS, bandwidth hoặc quota. Nếu workload dự kiến vượt trần trong thời hạn cần thiết, nên chuẩn bị phương án scale-out hoặc phân tách workload trước khi đến thời điểm quá tải.

## 11. Khi nào cần cân nhắc scale-out hoặc thay đổi kiến trúc?

Scale-up phù hợp khi bottleneck có thể giải quyết bằng tài nguyên của node. Nhưng cần cân nhắc hướng khác khi:
- Đã đạt giới hạn instance/CPU/RAM/storage.
- Write path bị giới hạn bởi một primary hoặc hot partition.
- Một workload báo cáo gây ảnh hưởng OLTP kéo dài.
- Cần availability/fault isolation cao hơn một node.
- Dữ liệu và traffic có thể phân vùng theo tenant/key.
- Read workload có thể phục vụ từ replica hoặc analytical store.
- Chi phí node lớn tăng nhanh hơn lợi ích.

Các lựa chọn có thể gồm:
- Read replicas để phân phối đọc, có cân nhắc replication lag.
- Partitioning/sharding để phân phối dữ liệu và một phần write workload.
- Tách OLTP và analytics.
- Queue/stream để hấp thụ burst và xử lý bất đồng bộ khi semantics cho phép.
- Cache cho dữ liệu đọc nhiều và chấp nhận consistency model phù hợp.
- Thiết kế write aggregation hoặc sharded counters cho hot keys.

Scale-out có chi phí về routing, transaction phân tán, uniqueness, consistency, rebalancing và vận hành. Không nên chuyển sang kiến trúc phân tán chỉ vì một metric đơn lẻ cao; cần dự báo giới hạn và chứng minh scale-up không còn phù hợp.

## 12. Những sai lầm thường gặp

**Thấy CPU cao thì mua thêm CPU ngay.** CPU có thể cao do query đọc quá nhiều, plan sai hoặc parallelism quá mức. Sửa workload có thể rẻ hơn.

**Thấy cache hit ratio cao thì không cần RAM hoặc tối ưu đọc.** Logical reads và memory bandwidth vẫn có thể rất lớn dù physical reads thấp.

**Tăng dung lượng disk để giải quyết I/O chậm.** Capacity, IOPS, throughput và latency là các thuộc tính khác nhau.

**Tăng connection pool để tăng throughput.** Nếu DBMS đã bão hòa, thêm session chỉ làm queue và contention tăng.

**Tăng DOP cho mọi truy vấn.** Phần tuần tự, worker contention và storage saturation có thể làm workload chậm hơn.

**Cho rằng thêm core sẽ tăng commits/s theo tỷ lệ.** Commit có thể bị giới hạn bởi log flush, group commit, lock hoặc hot index page.

**Tắt fsync hoặc giảm durability để benchmark.** Kết quả không đại diện cho semantics production và có thể làm mất dữ liệu khi sự cố.

**Chỉ benchmark một query chạy đơn lẻ.** Cấu hình tốt cho một báo cáo có thể làm API OLTP chậm khi chạy đồng thời.

**Không đo bottleneck mới sau scale-up.** Tài nguyên được tăng có thể không còn là giới hạn chính.

**Đợi đến khi hết headroom mới lập kế hoạch.** Migration hoặc scale-out cần thời gian thiết kế, kiểm thử và chuyển đổi.

## 13. Checklist mở rộng tài nguyên một máy

- [ ] Đã xác định mục tiêu là latency, throughput, capacity hay headroom chưa?
- [ ] Đã có baseline workload và SLA p95/p99 chưa?
- [ ] Đã đo CPU utilization, runnable queue và CPU time chưa?
- [ ] Đã xác minh vCPU/core thực tế, quota và NUMA topology chưa?
- [ ] Đã đo buffer cache, logical reads, physical reads và memory pressure chưa?
- [ ] Đã kiểm tra memory bandwidth và memory grant/spill chưa?
- [ ] Đã đo storage capacity, IOPS, throughput, latency và queue depth riêng từng volume chưa?
- [ ] Đã đo durable log flush latency, log bytes và group commit chưa?
- [ ] Đã kiểm tra checkpoint, dirty page writes và write amplification chưa?
- [ ] Đã phân tích lock waits, hot rows, index page contention và transaction duration chưa?
- [ ] Đã đo network RTT, bandwidth, pool wait và result transfer chưa?
- [ ] Đã benchmark workload hỗn hợp với cùng durability và dữ liệu đại diện chưa?
- [ ] Đã so sánh throughput, p50/p95/p99 và cost per transaction chưa?
- [ ] Đã xác định bottleneck mới sau khi tăng tài nguyên chưa?
- [ ] Đã dự báo tăng trưởng, headroom, quota và trần instance chưa?
- [ ] Đã xác định điều kiện cần chuyển sang scale-out hoặc tách workload chưa?
- [ ] Đã có kế hoạch triển khai, theo dõi và rollback chưa?

## Kết luận

Scale-up tăng CPU, RAM, memory bandwidth, storage hoặc network trên một node và thường là bước mở rộng trực tiếp khi workload còn tận dụng được tài nguyên mới. Nhưng hiệu quả bị giới hạn bởi phần việc tuần tự, queueing, NUMA, memory bandwidth, I/O saturation, log flush, hot row, index contention và checkpoint. Đặc biệt, đường ghi phải bảo đảm thứ tự log và durability; thêm core không loại bỏ được coordination hoặc durable I/O.

Hãy xác định bottleneck bằng số liệu trước khi tăng tài nguyên, đo riêng CPU, memory, storage, log, lock và network, rồi benchmark workload hỗn hợp với cùng semantics durability. Sau mỗi lần scale-up, tìm bottleneck mới và cập nhật capacity plan, headroom cùng cost per transaction. Khi đã chạm trần node hoặc giới hạn ghi tập trung, hãy đánh giá scale-out và thay đổi kiến trúc dựa trên semantics dữ liệu, consistency, availability và chi phí vận hành.

