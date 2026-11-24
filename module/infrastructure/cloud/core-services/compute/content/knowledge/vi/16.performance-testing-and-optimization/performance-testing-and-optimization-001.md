# Xác định mục tiêu latency, throughput và mức sử dụng tài nguyên

## Bối cảnh: đo hiệu năng theo kết quả và giới hạn của hệ thống

Một dịch vụ compute có thể chạy trên VM, container hoặc serverless. Dù mô hình triển khai khác nhau, người vận hành vẫn cần trả lời ba câu hỏi: mỗi yêu cầu mất bao lâu, hệ thống xử lý được bao nhiêu công việc trong một đơn vị thời gian và tài nguyên đang được sử dụng đến mức nào. Ba nhóm chỉ số này lần lượt là **latency**, **throughput** và **resource utilization**.

Các chỉ số có quan hệ với nhau. Khi tải tăng, throughput có thể tăng cho đến khi một tài nguyên hoặc dependency đạt giới hạn. Sau điểm đó, hàng đợi thường dài hơn, latency tăng và lỗi hoặc timeout xuất hiện. Một hệ thống có CPU utilization cao chưa chắc đã chậm; một hệ thống có CPU thấp vẫn có thể bị giới hạn bởi storage, network, lock hoặc dịch vụ phụ trợ.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, việc đặt mục tiêu hiệu năng giúp chọn đúng loại CPU/RAM, storage và network, xác định cấu hình VM/container/serverless, lập kế hoạch capacity và thiết kế các bài performance test có ý nghĩa. Mục tiêu phải gắn với workload và trải nghiệm cần cung cấp, thay vì chọn ngưỡng tài nguyên tùy ý.

## 1. Ba nhóm chỉ số cốt lõi

| Nhóm | Câu hỏi | Đơn vị thường gặp | Ví dụ |
|---|---|---|---|
| Latency | Một thao tác mất bao lâu? | ms, s | API hoàn tất trong 180 ms |
| Throughput | Bao nhiêu công việc được xử lý trong một đơn vị thời gian? | request/s, transaction/s, job/min, MiB/s | Dịch vụ xử lý 2.000 request/s |
| Resource utilization | Năng lực tài nguyên được dùng bao nhiêu? | %, cores, GiB, IOPS, MiB/s | CPU dùng 65%, RAM working set 7 GiB |

Nên đo cả ba nhóm cùng lúc. Throughput cao không tự chứng minh hệ thống tốt nếu latency quá lớn hoặc tỷ lệ lỗi cao. Utilization thấp không chứng minh hệ thống có nhiều capacity nếu workload bị chặn bởi một giới hạn khác. Latency trung bình thấp cũng có thể che giấu một nhóm nhỏ request rất chậm.

## 2. Latency: thời gian người dùng phải chờ

Latency là khoảng thời gian từ một mốc bắt đầu đến một mốc hoàn tất được định nghĩa. Với API, có thể đo từ lúc gateway nhận request đến khi gửi response; với tác vụ nền, đo từ lúc job được nhận đến lúc kết quả sẵn sàng. Phải thống nhất điểm bắt đầu và kết thúc trước khi so sánh các lần đo.

### 2.1. Các thành phần của latency

Một request có thể trải qua nhiều giai đoạn:

1. DNS lookup và thiết lập kết nối TCP/TLS (nếu client cần thực hiện).
2. Thời gian chờ ở load balancer, gateway hoặc queue.
3. Thời gian xử lý tại ứng dụng và lập lịch CPU.
4. Thời gian chờ database, cache, storage hoặc API bên ngoài.
5. Thời gian truyền response về client.

Latency end-to-end phản ánh tổng thời gian người dùng trải nghiệm. Server-side latency chỉ đo một phần đường đi và hữu ích để tách nguyên nhân. Ví dụ, API xử lý trong 80 ms nhưng client nhận kết quả sau 600 ms có thể do DNS, TLS, network hoặc một proxy nằm ngoài phạm vi đo của ứng dụng.

Không cộng các percentile của từng thành phần để suy ra percentile end-to-end. Với một request cụ thể, có thể cộng các khoảng thời gian tuần tự; nhưng p95 của database cộng p95 của API không nhất thiết bằng p95 của toàn request vì các phân phối và tương quan khác nhau. Hãy đo trực tiếp end-to-end và dùng trace để phân rã từng span.

### 2.2. Trung bình, median và percentile

Latency thường có phân phối lệch: phần lớn request nhanh, một số request chậm do cache miss, GC pause, retry, contention hoặc dependency. Vì vậy, chỉ dùng trung bình (mean) là chưa đủ.

| Thống kê | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Mean / average | Tổng latency chia số request | Theo dõi xu hướng tổng quát; nhạy với outlier |
| p50 / median | 50% request nhanh hơn hoặc bằng giá trị này | Đại diện trải nghiệm điển hình |
| p90 | 90% request nhanh hơn hoặc bằng | Quan sát phần đuôi tương đối chậm |
| p95 | 95% request nhanh hơn hoặc bằng | Theo dõi tail latency ở mức phổ biến |
| p99 | 99% request nhanh hơn hoặc bằng | Phát hiện trải nghiệm rất chậm ở nhóm nhỏ |
| p99.9 | 99,9% request nhanh hơn hoặc bằng | Hữu ích cho dịch vụ quy mô lớn hoặc yêu cầu nghiêm ngặt, cần đủ mẫu |

Ví dụ p95 = 250 ms nghĩa là khoảng 95% request trong population và cửa sổ đo hoàn tất trong không quá 250 ms; 5% còn lại chậm hơn. Nó không có nghĩa mọi người dùng đều thấy 250 ms.

### 2.3. Vì sao tail latency quan trọng?

Một trang web có thể cần gọi nhiều service song song. Nếu một request tổng hợp chờ tất cả service con, thời gian hoàn tất thường bị quyết định bởi service con chậm nhất. Dù từng service có p99 khá tốt, xác suất ít nhất một dependency chậm có thể tăng khi một request gọi nhiều dependency. Tail latency vì vậy có thể ảnh hưởng mạnh đến trải nghiệm tổng thể.

Các nguyên nhân thường gặp của tail latency:

- Hàng đợi tăng khi CPU, storage hoặc connection pool gần bão hòa.
- GC pause, page fault, memory reclaim hoặc OOM pressure.
- Cache miss, cold start hoặc tải image/container.
- Storage I/O chậm, queue depth cao hoặc volume bị throttling.
- Network retransmission, packet loss, DNS hoặc kết nối TLS.
- Lock contention, thread pool cạn, retry storm hoặc dependency chậm.

### 2.4. Đặt mục tiêu latency

Mục tiêu cần xác định loại request, điểm đo, percentile hoặc tỷ lệ dưới ngưỡng, và cửa sổ thời gian. Ví dụ:

- p50 API đọc: dưới 80 ms.
- p95 API đọc: dưới 250 ms.
- 99% request hợp lệ hoàn tất trong 500 ms.
- 95% job nền hoàn tất trong 2 phút kể từ lúc được nhận.

Đây chỉ là ví dụ minh họa. Mục tiêu thật phải dựa trên nhu cầu người dùng, độ phức tạp của thao tác, dependency, lịch sử đo và yêu cầu sản phẩm. Với latency, một SLO theo tỷ lệ request dưới ngưỡng thường dễ diễn giải hơn một con số percentile đơn lẻ khi tính error budget.

## 3. Throughput: lượng công việc hoàn tất

Throughput là tốc độ hệ thống hoàn thành công việc. Đơn vị cần phù hợp với workload:

- Web/API: request mỗi giây (RPS).
- Database: transaction mỗi giây (TPS), query/s hoặc operation/s.
- Queue/worker: job mỗi phút hoặc message/s.
- File/storage: MiB/s hoặc GiB/s.
- Streaming: event/s hoặc byte/s.
- Batch: số record hoặc file hoàn tất trong một khoảng thời gian.

Phân biệt **offered load** (lượng công việc được gửi vào) với **achieved throughput** (lượng công việc thực sự hoàn tất). Khi hệ thống quá tải, client có thể tiếp tục gửi 5.000 request/s nhưng server chỉ hoàn tất 2.000 request/s; phần còn lại chờ, timeout hoặc bị từ chối. Chỉ đo số request gửi đi sẽ đánh giá sai năng lực.

### 3.1. Throughput và goodput

Goodput là phần throughput hữu ích: công việc hợp lệ được hoàn tất đúng yêu cầu, sau khi loại bỏ retry trùng, response lỗi hoặc dữ liệu không dùng được theo định nghĩa nghiệp vụ.

Ví dụ, worker nhận 1.000 message/s nhưng 200 message/s bị retry nhiều lần và 50 message/s đi vào dead-letter queue. Throughput xử lý nội bộ có thể lớn, nhưng goodput thành công thấp hơn đáng kể. Với upload, byte truyền thành công và được xác minh checksum hữu ích hơn tổng byte gửi qua mạng.

Khi đặt mục tiêu throughput, cần ghi rõ:

- Đếm request được nhận, request hoàn tất hay transaction commit thành công?
- Retry được đếm riêng hay gộp theo công việc logic?
- Có tính request lỗi, bị hủy hoặc timeout không?
- Dữ liệu đo là trung bình trong cửa sổ nào hay peak ngắn hạn?
- Hệ thống cần duy trì tốc độ đó trong bao lâu?

### 3.2. Throughput và latency không thể tối ưu tách rời

Batching có thể tăng throughput bằng cách xử lý nhiều phần tử trong một lần gọi, nhưng thường làm tăng thời gian chờ để gom batch. Tăng concurrency có thể tận dụng CPU và I/O tốt hơn, nhưng nếu vượt khả năng phục vụ thì queue và latency tăng. Cache có thể giảm tải backend và latency, nhưng cần tính đến cache miss và tính nhất quán.

Mục tiêu nên đặt đồng thời, ví dụ: xử lý tối thiểu 1.500 request/s trong khi p95 dưới 250 ms và tỷ lệ lỗi dưới 0,1%. Một cấu hình chỉ đạt 2.000 request/s nhưng p95 tăng lên 3 giây không đáp ứng mục tiêu này.

## 4. Concurrency, queue và định luật Little

Concurrency là số công việc đang được xử lý hoặc đang tồn tại đồng thời trong hệ thống. Cần phân biệt số request đồng thời ở client, số request đang chạy trong ứng dụng và số request đang chờ trong queue.

Định luật Little mô tả quan hệ giữa số công việc trung bình trong hệ thống, throughput và thời gian lưu lại:

\[
L = \lambda W
\]

Trong đó:

- `L`: số công việc trung bình trong hệ thống (in-flight hoặc queued, tùy ranh giới đo).
- `λ`: throughput trung bình, tính bằng công việc/giây.
- `W`: thời gian trung bình một công việc ở trong hệ thống, tính bằng giây.

Ví dụ, API hoàn tất 200 request/s và thời gian trung bình từ lúc nhận đến lúc hoàn tất là 0,25 giây. Số request trung bình trong hệ thống là:

\[
L = 200\times0.25=50\text{ request}
\]

Nếu throughput giữ nguyên nhưng latency tăng lên 1 giây, số request trung bình trong hệ thống tăng lên khoảng 200. Hàng đợi lớn hơn tiêu thụ thêm memory và có thể làm timeout tăng theo.

Little's Law mô tả quan hệ trung bình trong điều kiện ổn định, không tự xác định capacity tối đa hoặc latency percentile. Khi hệ thống không ổn định, queue tăng liên tục và throughput không theo kịp offered load, cần xử lý như tình trạng quá tải.

## 5. Resource utilization: tài nguyên đang được dùng đến đâu?

Resource utilization là tỷ lệ hoặc mức sử dụng một tài nguyên so với năng lực được cấp. Tuy nhiên, utilization chỉ là một góc nhìn. Để biết tài nguyên có trở thành nút thắt hay không, cần xem thêm **saturation** (mức tranh chấp/hàng đợi) và **errors** (lỗi do cạn hoặc vượt giới hạn).

Ba tín hiệu thường được dùng cùng nhau:

- **Utilization:** phần năng lực đang được sử dụng, ví dụ CPU 70% hoặc volume dùng 80% dung lượng.
- **Saturation:** công việc phải chờ vì tài nguyên không đáp ứng ngay, ví dụ CPU run queue, disk queue hoặc thread pool đầy.
- **Errors:** thao tác thất bại do tài nguyên hoặc giới hạn, ví dụ OOM kill, disk full, throttling, packet drop hoặc request timeout.

Một CPU có utilization 90% nhưng không có run queue đáng kể và latency ổn định có thể vẫn phục vụ tốt. Ngược lại, CPU trung bình 40% nhưng một core đơn bị bão hòa có thể làm một luồng xử lý chậm. Do đó, không nên dùng một ngưỡng utilization chung cho mọi loại tài nguyên và workload.

## 6. Các chỉ số tài nguyên cần theo dõi

### 6.1. CPU

Các metric hữu ích:

- CPU utilization theo toàn máy, từng core và từng process/container.
- User, system, idle, iowait và steal time trên Linux.
- Run queue hoặc số thread runnable đang chờ CPU.
- CPU throttling của container khi chạm quota/limit.
- Context switch, interrupt rate và CPU frequency nếu cần phân tích sâu.

CPU utilization cao có thể là dấu hiệu workload đang tận dụng tốt tài nguyên. Nhưng run queue tăng, throttling kéo dài và latency cùng tăng cho thấy CPU có thể là bottleneck. Với VM, steal time cao cho biết vCPU phải chờ hypervisor cấp thời gian CPU; đây là tín hiệu có thể liên quan đến tranh chấp host hoặc đặc tính instance.

Container có thể được giới hạn CPU bằng quota. Nếu ứng dụng cần nhiều CPU ngắn hạn nhưng quota thấp, nó có thể bị throttling ngay cả khi node còn CPU idle. Cần xem cả usage và throttling, không chỉ CPU của node.

Ví dụ lệnh Linux:

```bash
# Tổng quan CPU và run queue theo thời gian
vmstat 1

# CPU theo từng core
mpstat -P ALL 1

# Process dùng CPU nhiều
top
```

Lệnh cần gói công cụ tương ứng (`sysstat` cho `mpstat`) và quyền phù hợp. Trên Windows, có thể theo dõi Processor\% Processor Time, Processor Queue Length và process-level CPU bằng Performance Monitor.

### 6.2. Memory

Không chỉ nhìn RAM đã dùng. Hệ điều hành có thể sử dụng RAM làm page cache; phần này có thể thu hồi khi ứng dụng cần. Các chỉ số nên quan sát:

- Working set hoặc resident set của ứng dụng.
- Available memory và memory pressure.
- Swap in/out, major page fault và page reclaim.
- OOM kill hoặc container memory limit exceeded.
- Heap, garbage collection và allocation rate với runtime managed.
- Cache hit/miss và memory used theo container/VM.

RAM gần đầy chưa chắc là sự cố nếu phần lớn là cache có thể thu hồi. Nhưng swap hoạt động mạnh, major page fault tăng, OOM kill hoặc latency GC kéo dài cho thấy áp lực bộ nhớ. Với container, memory limit có thể gây OOM kill dù host vẫn còn RAM; cần xem giới hạn ở đúng cgroup/container.

### 6.3. Storage và filesystem

Storage có thể giới hạn bởi IOPS, throughput, latency, queue depth hoặc dung lượng. Các metric cần theo dõi:

- Read/write IOPS và MiB/s.
- Read/write latency, đặc biệt p95/p99 nếu dịch vụ cung cấp.
- Queue depth và thời gian chờ I/O.
- Utilization của thiết bị hoặc giới hạn throughput/IOPS được provision.
- Dung lượng filesystem, inode và tốc độ tăng dữ liệu.
- Burst balance/credit hoặc throttling nếu loại volume có cơ chế burst.

Một volume có thể còn 70% dung lượng nhưng đã đạt giới hạn IOPS. Ngược lại, volume đầy có thể làm ứng dụng lỗi dù I/O latency vẫn thấp. Cần theo dõi cả performance và capacity.

Ví dụ lệnh Linux:

```bash
# I/O theo thiết bị, queue và latency
iostat -xz 1

# Dung lượng và inode của filesystem
df -h
df -i
```

### 6.4. Network

Metric network gồm throughput vào/ra, packet per second, RTT, packet loss, retransmission, connection error, socket state và bandwidth limit. Với VM cloud, cần kiểm tra giới hạn network theo loại instance, NIC, flow hoặc dịch vụ; một số instance có băng thông tối đa theo tải hoặc kích thước máy.

Throughput thấp không luôn có nghĩa network thiếu băng thông. Ứng dụng có thể bị giới hạn bởi request rate, TCP window, packet loss, connection setup, DNS hoặc server từ xa. Packet retransmission và RTT tăng có thể làm latency xấu đi dù interface chưa dùng hết bandwidth.

### 6.5. GPU và bộ tăng tốc

Với workload AI hoặc tính toán tăng tốc, theo dõi:

- GPU utilization và mức sử dụng từng compute engine.
- VRAM used/free và memory allocation peak.
- Memory bandwidth hoặc memory controller utilization nếu công cụ hỗ trợ.
- Power, temperature, clock và throttling.
- GPU queue, số job đang chờ và thời gian cấp GPU.
- PCIe/NVLink transfer và lỗi driver/runtime.

GPU utilization thấp có thể do data loader, CPU preprocessing, network hoặc storage không cung cấp dữ liệu đủ nhanh. VRAM đầy có thể giới hạn batch/context trước khi compute engine đạt mức sử dụng cao. Cần đo end-to-end throughput và latency của workload cùng metric GPU.

### 6.6. Tài nguyên ở container và serverless

Container: theo dõi request/limit, usage, CPU throttling, memory working set, OOM, restart, pending pod, node pressure và thời gian scheduling. Đặt request quá thấp có thể khiến scheduler dồn nhiều workload lên node; limit quá thấp gây throttling hoặc OOM.

Serverless: theo dõi invocation count, duration, concurrency, throttling, cold start, memory configured/used, timeout và retry. Concurrency limit có thể chặn request dù compute của dịch vụ khác vẫn còn. Cold start làm tăng latency của một nhóm invocation, vì vậy cần xem phân phối latency và tỷ lệ cold start thay vì chỉ nhìn average duration.

## 7. Xác định bottleneck từ mối quan hệ giữa các chỉ số

Không nên kết luận bottleneck chỉ từ một metric. Hãy tìm sự thay đổi đồng thời giữa latency, throughput, utilization, saturation và error.

| Dấu hiệu quan sát | Khả năng cần kiểm tra | Bằng chứng bổ sung |
|---|---|---|
| Throughput ngừng tăng, latency tăng, CPU run queue tăng | CPU-bound hoặc CPU quota thấp | Per-core usage, throttling, profile và CPU time/request |
| Latency tăng, memory pressure/swap/major fault tăng | Thiếu RAM hoặc working set tăng | OOM, GC pause, allocation, cache và page fault |
| Database latency tăng, disk queue/IOPS cao | Storage-bound | Read/write pattern, volume limit, DB wait event |
| Request timeout, retransmission/RTT tăng | Network hoặc dependency path | Packet loss, DNS, connection pool và trace |
| Node còn CPU nhưng pod pending | Scheduling constraint hoặc thiếu tài nguyên khác | Memory request, taint/toleration, affinity, GPU, IP và quota |
| GPU utilization thấp, data wait cao | Pipeline cấp dữ liệu là bottleneck | CPU loader, storage read, network và GPU queue |
| Error rate tăng khi concurrency chạm giới hạn | Thread/connection/concurrency cap | Pool exhaustion, 429, throttling và queue length |

Một cách điều tra thực tế:

1. Xác nhận latency/throughput của hành trình người dùng có thay đổi không.
2. Xác định endpoint, workload, region/zone và phiên bản bị ảnh hưởng.
3. So sánh resource utilization với saturation và errors cùng thời điểm.
4. Dùng trace để tìm span chậm; dùng log để tìm lỗi; dùng profile để tìm chi phí CPU/memory trong ứng dụng.
5. Kiểm tra dependency và giới hạn dịch vụ cloud, không chỉ tài nguyên VM.
6. Thử một thay đổi có giả thuyết rõ ràng, đo lại và so sánh với baseline.

## 8. Xác định profile workload trước khi đặt mục tiêu

Các workload khác nhau cần ưu tiên chỉ số khác nhau:

| Workload | Đặc điểm | Chỉ số thường quan trọng |
|---|---|---|
| Interactive API | Request ngắn, người dùng chờ response | p95/p99 latency, success rate, RPS, concurrency |
| Batch processing | Khối lượng lớn, có thể chạy theo lịch | Total completion time, records/s, CPU/GPU hours, cost/job |
| Queue worker | Xử lý bất đồng bộ, có backlog | Job/s, oldest message age, completion deadline, retry |
| Database | Random I/O, transaction và contention | TPS, query latency, IOPS, disk queue, connection pool |
| Streaming | Dòng event liên tục | Events/s, lag, processing latency, dropped events |
| AI inference | Prefill/decode, batch và KV cache | TTFT, tokens/s, p95 latency, VRAM, GPU utilization |
| File/object transfer | Truyền dữ liệu lớn | MiB/s, request latency, error/retry, egress |

Trước khi chọn mục tiêu, hãy mô tả workload bằng các thuộc tính:

- Request/job mix và tỷ trọng từng loại.
- Kích thước payload, record, file hoặc context.
- Arrival rate theo thời gian, peak và tính mùa vụ.
- Concurrency và thời gian xử lý trung bình.
- Tỷ lệ đọc/ghi, cache hit ratio và pattern truy cập.
- Dependency, retry, timeout và giới hạn bên ngoài.
- Mục tiêu latency, throughput, độ chính xác và thời gian hoàn tất.

Một benchmark chỉ gửi request nhỏ, cache nóng và một endpoint không đại diện cho hệ thống production có nhiều loại request và dependency. Workload profile giúp bài test phản ánh điều kiện thực tế.

## 9. Chuyển yêu cầu sản phẩm thành mục tiêu đo được

Mục tiêu hiệu năng nên có dạng có thể kiểm thử và xác minh. Thay vì ghi “API phải nhanh” hoặc “CPU không được quá cao”, hãy xác định population, tải, ngưỡng và khoảng thời gian.

Ví dụ mục tiêu cho một API production:

| Thuộc tính | Mục tiêu minh họa |
|---|---|
| Offered load | 1.500 request/s với request mix đại diện |
| Goodput | Ít nhất 1.490 request/s hoàn tất thành công |
| Latency | p95 dưới 250 ms, p99 dưới 600 ms |
| Error rate | Dưới 0,1% trong bài test ổn định |
| CPU | Không throttling kéo dài; CPU fleet còn capacity cho peak |
| Memory | Không OOM/swap thrashing; working set có headroom |
| Storage | p95 I/O latency và queue depth trong ngưỡng workload |
| Network | Không có packet loss/retransmission bất thường; bandwidth còn dự phòng |

Các con số chỉ minh họa cách viết mục tiêu. Không có một ngưỡng CPU hay RAM phù hợp cho mọi ứng dụng. Mục tiêu cần được thống nhất với product owner, đội vận hành và người chịu trách nhiệm dịch vụ.

### 9.1. Đặt mục tiêu theo tải bình thường và tải đỉnh

Một hệ thống có thể đáp ứng tải trung bình nhưng thất bại trong peak. Cần phân biệt:

- **Normal load:** tải thường gặp trong phần lớn thời gian.
- **Peak load:** mức tải cao nhất dự kiến trong hoạt động bình thường hoặc mùa vụ.
- **Burst load:** tải tăng đột ngột trong thời gian ngắn.
- **Growth scenario:** tải dự kiến sau khi số người dùng hoặc dữ liệu tăng.
- **Degraded mode:** mức dịch vụ tối thiểu chấp nhận được khi dependency hoặc một miền lỗi gặp sự cố.

Mục tiêu nên nêu thời gian duy trì peak và khả năng phục hồi sau burst. Một hệ thống có thể xử lý burst 2.000 RPS trong 30 giây nhưng chỉ duy trì 1.200 RPS trong một giờ; cả hai đặc tính cần được kiểm thử nếu đều quan trọng.

### 9.2. Đặt mục tiêu cho từng loại request

Request đọc cache và request ghi database có chi phí khác nhau. Gộp tất cả vào một latency percentile có thể che khuất lỗi của một luồng quan trọng. Có thể đặt mục tiêu riêng cho login, search, checkout hoặc upload; cần giữ một SLI tổng thể để phản ánh dịch vụ và các SLI chi tiết để điều tra.

Khi phân nhóm, tránh tạo quá nhiều loại metric hoặc label cardinality cao. Chỉ chia theo các luồng có ý nghĩa vận hành hoặc nghiệp vụ.

## 10. Capacity, saturation và headroom

Capacity là lượng công việc hệ thống có thể xử lý trong điều kiện đã xác định mà vẫn đáp ứng mục tiêu latency và error rate. Không nên định nghĩa capacity đơn thuần là thời điểm CPU đạt 100%. Bottleneck có thể xuất hiện ở connection pool, disk IOPS, network packet rate, memory hoặc downstream service trước khi CPU đầy.

### 10.1. Tìm điểm bão hòa

Khi tăng offered load theo từng bước, thường quan sát được ba vùng:

1. **Underutilized:** tài nguyên còn dư, throughput tăng gần theo tải và latency tương đối ổn định.
2. **Efficient operating region:** throughput tăng nhưng hàng đợi và latency bắt đầu nhạy hơn với tải; hệ thống vẫn đáp ứng mục tiêu.
3. **Saturation/overload:** throughput đạt plateau hoặc tăng rất ít, queue/latency tăng nhanh, throttling và lỗi xuất hiện.

Điểm bão hòa là nơi hệ thống không còn đáp ứng đồng thời mục tiêu throughput, latency và errors. Nên vận hành dưới điểm này để có khả năng hấp thụ biến động và lỗi thành phần.

### 10.2. Headroom

Headroom là phần capacity dự phòng để hấp thụ burst, tăng trưởng, sự cố một node/zone và thời gian scale-out. Headroom cần được tính theo từng tài nguyên và failure scenario. Ví dụ, nếu chạy ba replica và yêu cầu vẫn phục vụ khi mất một replica, hai replica còn lại phải đủ sức xử lý tải cần thiết.

Một cách ước lượng đơn giản:

```text
required_capacity = peak_demand / target_utilization
headroom = required_capacity - peak_demand
```

Ví dụ, workload dự kiến cần 60 đơn vị CPU capacity ở peak và đội vận hành muốn giữ utilization quanh 70% trong tình huống bình thường:

```text
required_capacity = 60 / 0.70 = 85.7 capacity units
headroom           = 85.7 - 60 = 25.7 units
```

Đây là phép sizing tuyến tính đơn giản. Thực tế cần tính khả năng mất node/zone, giới hạn instance, autoscaling delay, quota, workload không chia đều và overhead. Target utilization 70% ở ví dụ không phải khuyến nghị cố định.

### 10.3. Không dùng một ngưỡng utilization cho mọi tài nguyên

CPU có thể hoạt động hiệu quả ở mức cao nếu latency vẫn ổn định và còn khả năng xử lý burst. RAM cần đủ khoảng trống cho allocation đột biến và page cache; storage cần dư IOPS/throughput để tránh queue tăng; network cần dự phòng bandwidth và packet rate. GPU cần tính cả VRAM và compute utilization.

Ngưỡng cảnh báo nên kết hợp utilization với saturation và SLI. Ví dụ, CPU 85% kéo dài có thể là warning; CPU throttling kèm p95 latency vượt mục tiêu có thể cần page. Với filesystem, dung lượng 90% có thể cần cảnh báo sớm dù I/O latency vẫn bình thường vì tốc độ tăng dữ liệu có thể làm đầy volume trước kỳ bảo trì.

## 11. Ước lượng sơ bộ tài nguyên từ workload

Các phép tính dưới đây giúp có điểm bắt đầu trước benchmark. Chúng không thay thế đo tải thực tế vì cache, lock, batching, runtime và dependency làm hiệu năng phi tuyến.

### 11.1. Ước lượng CPU

Nếu mỗi request tiêu thụ trung bình `c` giây CPU và hệ thống cần xử lý `R` request mỗi giây:

\[
CPU\ cores\ (ideal) = R\times c
\]

Ví dụ, mỗi request dùng 5 ms CPU và mục tiêu là 1.000 request/s:

\[
1000\times0.005=5\text{ CPU cores}
\]

Đây là mức CPU time lý tưởng để xử lý tải đó, chưa tính overhead hệ điều hành, sidecar, background task, biến động request mix và headroom. Nếu muốn peak utilization khoảng 70% trong điều kiện đã định nghĩa, có thể ước lượng năng lực khoảng `5 / 0,7 = 7,14` core rồi làm tròn theo cấu hình instance phù hợp và kiểm thử.

### 11.2. Ước lượng concurrency

Dùng Little's Law, nếu hệ thống nhận 800 request/s và thời gian trung bình trong hệ thống là 0,15 giây:

\[
L=800\times0.15=120\text{ request}
\]

Ứng dụng cần khả năng quản lý khoảng 120 request đang in-flight trung bình ở mức tải đó. Peak concurrency có thể cao hơn; cần xem phân phối latency, burst và giới hạn thread/connection pool. Không nên tăng thread count vô hạn vì mỗi thread có overhead và có thể làm contention nặng hơn.

### 11.3. Ước lượng network throughput

Nếu response trung bình 10 KiB và goodput mục tiêu là 2.000 response/s:

\[
2000\times10\text{ KiB}=19.53\text{ MiB/s}
\]

Con số này mới tính payload response, chưa gồm request body, protocol overhead, TLS, retransmission, replication hoặc traffic giữa các service. Cần đo cả ingress và egress, đồng thời kiểm tra giới hạn NIC/instance và đường truyền.

### 11.4. Ước lượng memory

Với server xử lý request đồng thời, memory có thể gồm baseline runtime, working set cố định, cache, buffer và phần tăng theo số request in-flight. Có thể dùng mô hình sơ bộ:

```text
memory_required ~= baseline
                 + (memory_per_inflight_request x concurrency)
                 + cache_and_buffer
                 + operating_headroom
```

Ví dụ, baseline 1,5 GiB, mỗi request in-flight giữ trung bình 2 MiB, concurrency 200 và cache/buffer 1 GiB:

```text
1.5 GiB + (2 MiB x 200) + 1 GiB ~= 2.89 GiB
```

Đây chỉ là mô hình gần đúng; memory per request có thể thay đổi theo payload, runtime, object lifetime và GC. Hãy đo peak working set khi chạy tải đại diện, không chỉ nhìn RAM ngay sau khi khởi động.

## 12. Thiết kế bài performance test để đo đúng mục tiêu

Một bài test có giá trị phải tái tạo workload đủ gần production, tạo tải có kiểm soát và thu thập metric ở cả client lẫn server. Nếu load generator trở thành bottleneck, kết quả không phản ánh capacity của hệ thống đích.

### 12.1. Các kiểu kiểm thử tải

| Kiểu test | Cách tạo tải | Câu hỏi cần trả lời |
|---|---|---|
| Baseline | Tải thấp, ổn định | Hiệu năng nền và overhead ban đầu là bao nhiêu? |
| Load test | Tải dự kiến trong điều kiện bình thường/peak | Hệ thống có đáp ứng SLO ở tải mục tiêu không? |
| Stress test | Tăng tải vượt mức dự kiến | Điểm bão hòa và kiểu suy giảm là gì? |
| Spike test | Tăng/giảm tải đột ngột | Hệ thống phản ứng ra sao với burst và autoscaling? |
| Soak test | Duy trì tải trong thời gian dài | Có memory leak, queue tích tụ, connection leak hoặc degradation không? |
| Capacity test | Tăng tải từng bước để tìm giới hạn | Throughput tối đa còn đáp ứng latency/error target là bao nhiêu? |

Không nên chỉ chạy một bài test ngắn ở peak. Soak test có thể phát hiện memory leak hoặc storage growth; spike test kiểm tra scale-out và cold start; stress test giúp biết hệ thống suy giảm có kiểm soát hay sụp đổ đột ngột.

### 12.2. Chuẩn bị workload và môi trường

Trước khi chạy:

1. Chọn request mix, payload size, dữ liệu và dependency đại diện.
2. Chuẩn bị môi trường, cấu hình compute, storage, network và version giống production ở các yếu tố quan trọng.
3. Tách load generator khỏi hệ thống đích hoặc bảo đảm nó còn đủ CPU, memory và network.
4. Xác định cache state: cold, warm hay tỷ lệ thực tế; ghi rõ nếu benchmark chỉ đo cache nóng.
5. Đồng bộ thời gian và bật metrics/logs/traces cần thiết.
6. Đặt timeout, retry và rate limit theo hành vi ứng dụng thực tế.
7. Kiểm tra dữ liệu test không gây side effect hoặc làm ảnh hưởng người dùng thật.

Ghi lại instance type, số replica, image/container digest, runtime, region/zone, storage class, autoscaling policy và cấu hình dependency để có thể lặp lại phép đo.

### 12.3. Ramp-up, steady-state và ramp-down

Một bài test nên có giai đoạn tăng tải dần, giữ tải ổn định đủ lâu để quan sát và giảm tải có kiểm soát. Bỏ qua warm-up có thể khiến kết quả bị ảnh hưởng bởi JIT compilation, cache cold, autoscaler hoặc khởi tạo connection pool.

Ví dụ kịch bản:

| Giai đoạn | Tải | Thời lượng | Mục tiêu |
|---|---:|---:|---|
| Warm-up | 10% target | 3 phút | Khởi tạo connection, cache và runtime |
| Ramp-up | 10% lên 100% | 10 phút | Quan sát scaling và latency theo tải |
| Steady-state | 100% target | 20 phút | Xác minh SLO và utilization ở tải mục tiêu |
| Peak | 130% target | 5 phút | Đánh giá headroom và behavior khi burst |
| Ramp-down | Giảm dần về 0 | 3 phút | Quan sát drain, queue và scale-in |

Thời lượng thực tế phụ thuộc workload. Soak test cần dài hơn nhiều; bài test cold-start cần khởi tạo môi trường mới hoặc scale-to-zero theo cách được kiểm soát.

### 12.4. Closed-loop và open-loop load generation

Trong **closed-loop test**, mỗi virtual user gửi request rồi chờ response mới gửi request tiếp. Khi server chậm, tốc độ gửi tự giảm; điều này có thể che giấu mức offered load mà người dùng thực tế vẫn tạo ra.

Trong **open-loop test**, generator phát request theo arrival rate định trước, độc lập với response time. Mô hình này phù hợp để mô phỏng hệ thống nhận traffic liên tục và quan sát queue/latency khi server chậm. Cần giới hạn queue ở load generator để tránh chính công cụ tạo tải tích tụ request không kiểm soát.

Một vấn đề cần chú ý là **coordinated omission**: nếu load generator chỉ phát request mới sau khi request trước hoàn tất, nó có thể không ghi nhận các thời điểm đáng lẽ request mới được gửi trong lúc hệ thống đang chậm. Kết quả latency vì thế có thể lạc quan. Chọn công cụ và chế độ phát tải có khả năng ghi nhận đúng scheduled arrival time hoặc hiệu chỉnh coordinated omission.

### 12.5. Đo percentile đúng cách

Không lấy trung bình percentile của nhiều máy để tính percentile toàn fleet. Ví dụ p95 của VM A là 100 ms và VM B là 500 ms không có nghĩa p95 toàn hệ thống là 300 ms. Hãy gộp histogram bucket/count hoặc thu thập dữ liệu request ở điểm đo chung rồi tính percentile trên population cần đánh giá.

Với Prometheus histogram, truy vấn p95 tổng hợp có thể có dạng:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_request_duration_seconds_bucket{
      service="orders-api",
      environment="perf"
    }[5m])
  )
)
```

Truy vấn giả định ứng dụng xuất histogram `http_request_duration_seconds` và label phù hợp. Histogram bucket cần đủ độ phân giải quanh ngưỡng mục tiêu; nếu bucket quá thưa, percentile chỉ là ước lượng kém chính xác. Với native histogram hoặc hệ thống metrics khác, cú pháp có thể khác.

## 13. Baseline và cách đọc kết quả

Baseline là bộ kết quả đo trong cấu hình và điều kiện đã biết, dùng để so sánh sau thay đổi. Một baseline hữu ích lưu:

- Workload profile và offered load.
- Goodput, error rate và latency p50/p95/p99.
- CPU, memory, storage, network và saturation.
- Số replica/VM, cấu hình instance, image/runtime và dependency.
- Thời gian warm-up, steady-state và test duration.
- Phiên bản code/config, ngày chạy và môi trường.

Khi so sánh hai lần chạy, giữ các điều kiện tương đương. Nếu đổi đồng thời instance type, database, cache và request mix, sẽ khó xác định thay đổi nào tạo ra kết quả.

### 13.1. Đọc throughput curve

Vẽ achieved goodput theo offered load và latency theo offered load. Ở vùng đầu, goodput thường tăng gần tuyến tính. Gần saturation, đường goodput bắt đầu phẳng trong khi latency tăng nhanh. Điểm vận hành nên nằm trong vùng đáp ứng SLO, có headroom cho burst và lỗi thành phần.

### 13.2. Đọc utilization cùng latency

Ví dụ:

- CPU tăng từ 30% lên 75%, goodput tăng và p95 ổn định: hệ thống đang tận dụng thêm capacity.
- CPU giữ 95%, goodput không tăng, run queue và p99 tăng: có thể đã chạm giới hạn CPU.
- CPU chỉ 40%, nhưng disk queue và database latency tăng: nút thắt có thể ở storage/database.
- RAM tăng dần qua nhiều giờ và không giảm sau khi tải hạ: cần kiểm tra leak hoặc cache không có giới hạn.

Không nên kết luận chỉ từ biểu đồ trung bình. Hãy phân tích theo instance, endpoint, zone, container và dependency để phát hiện hotspot bị che bởi aggregate.

## 14. Công cụ quan sát và đo lường

| Phạm vi | Công cụ/nguồn dữ liệu thường gặp | Dùng để đo |
|---|---|---|
| Linux CPU/memory | `top`, `vmstat`, `mpstat`, `/proc`, cgroup metrics | CPU, run queue, memory pressure, process |
| Linux storage | `iostat`, `iotop`, filesystem metrics | IOPS, throughput, queue, latency, disk usage |
| Linux network | `ss`, `sar -n`, `ethtool`, flow logs | Socket, retransmission, packet, interface |
| Windows | Performance Monitor, Resource Monitor, Event Viewer | CPU, memory, disk, network, process |
| Container/Kubernetes | Metrics Server, Prometheus, kube-state-metrics, cAdvisor | Pod/node resource, throttling, restart, pending |
| Cloud VM | Provider monitoring, instance metrics, audit/event logs | CPU, network, disk, status check, throttling |
| Load testing | k6, JMeter, Gatling, Locust hoặc công cụ tương đương | Offered load, response time, errors, virtual users |
| Tracing | OpenTelemetry và tracing backend | Span latency, dependency, request path |

Công cụ cần được chọn theo nền tảng và chính sách tổ chức. Không phải mọi metric đều có sẵn mặc định; disk I/O, memory working set, process metrics hoặc application histogram có thể cần agent/instrumentation riêng.

## 15. Ví dụ thực hành: xác định mục tiêu cho API chạy trên VM

Giả sử một API đặt hàng hiện chạy trên hai VM sau load balancer. Workload dự kiến là 600 RPS bình thường và 1.200 RPS trong peak. Request mix gồm 70% đọc, 25% ghi và 5% truy vấn báo cáo.

### 15.1. Viết mục tiêu

- 1.200 RPS offered load trong 20 phút steady-state.
- Goodput tối thiểu 1.190 RPS.
- p95 latency dưới 250 ms; p99 dưới 600 ms.
- Error rate dưới 0,1%.
- Hệ thống còn đủ capacity khi một VM được drain để bảo trì.
- Không OOM, không CPU throttling kéo dài, không storage queue tăng liên tục.

### 15.2. Ước lượng ban đầu

Giả sử profiling cho thấy một request dùng trung bình 4 ms CPU:

\[
1200\times0.004=4.8\text{ cores}
\]

Nếu muốn giữ mức CPU quanh 70% ở peak, cần khoảng:

\[
4.8/0.70\approx6.86\text{ cores}
\]

Đây là ước lượng fleet-level. Nếu cần duy trì peak khi một trong hai VM bị drain, một VM còn lại phải đủ năng lực xử lý hoặc hệ thống phải có thêm replica. Không thể chia đôi số core lý tưởng rồi kết luận mỗi VM đủ; cần tính failure scenario và benchmark thực tế.

### 15.3. Chạy thử và điều chỉnh

1. Đo baseline ở 600 RPS và lưu latency, goodput cùng resource metrics.
2. Ramp lên 900, 1.200 và 1.400 RPS; giữ mỗi mức đủ lâu để ổn định.
3. Quan sát điểm goodput không tăng tương ứng hoặc p95/p99 vượt mục tiêu.
4. Kiểm tra CPU per-core, run queue, memory, disk, network và database connection.
5. Drain một VM rồi chạy lại 1.200 RPS để xác minh headroom và HA.
6. Thử soak test để phát hiện memory/queue tăng theo thời gian.
7. Chốt cấu hình và ngưỡng alert sau khi xác minh bằng nhiều lần chạy.

Nếu p95 vượt mục tiêu nhưng CPU thấp và trace chỉ ra database wait, tăng vCPU cho API có thể không giúp. Cần xử lý query, connection pool, index hoặc capacity database. Mỗi tối ưu phải gắn với bottleneck đã đo được.

## 16. Tối ưu theo vòng lặp đo lường

Tối ưu hiệu năng nên là một vòng lặp có giả thuyết và phép đo:

1. **Định nghĩa mục tiêu:** latency, goodput, error rate và resource guardrail.
2. **Đo baseline:** workload, cấu hình, version và môi trường được ghi lại.
3. **Xác định bottleneck:** dựa trên saturation, trace, profile và dependency metrics.
4. **Đặt giả thuyết:** ví dụ giảm query count sẽ giảm database wait và p95.
5. **Thay đổi một nhóm yếu tố có kiểm soát:** index, cache, batch size, instance type, concurrency hoặc storage tier.
6. **Chạy lại cùng workload:** so sánh goodput, latency distribution, errors và resource usage.
7. **Kiểm tra trade-off:** chi phí, độ phức tạp, tính nhất quán, độ bền và khả năng vận hành.
8. **Ghi nhận kết quả:** cập nhật baseline, cấu hình và quyết định triển khai.

Một thay đổi có thể giảm latency nhưng tăng CPU hoặc memory; đó có thể là trade-off tốt nếu còn headroom và chi phí phù hợp. Ngược lại, tăng throughput bằng cách tăng queue không giới hạn có thể làm thời gian chờ và memory tăng, khiến người dùng nhận kết quả muộn hơn.

### 16.1. Các hướng tối ưu thường gặp

| Bottleneck đã xác nhận | Hướng thử nghiệm | Rủi ro cần đo lại |
|---|---|---|
| CPU-bound | Tối ưu thuật toán, giảm serialization, tăng vCPU hoặc scale-out | Chi phí, contention và giới hạn dependency |
| Memory pressure | Giảm allocation, giới hạn cache, điều chỉnh heap hoặc tăng RAM | GC, cache hit và OOM |
| Storage-bound | Tối ưu query/I/O, provision IOPS, cache hoặc thay storage tier | Durability, cost và write amplification |
| Network-bound | Giảm payload, reuse connection, nén hoặc đặt service gần nhau | CPU compression, egress cost và TLS overhead |
| Queue/concurrency-bound | Điều chỉnh worker count, pool size, batch và backpressure | Dependency overload, tail latency và duplicate work |
| Cold-start-bound | Giữ warm capacity, giảm package/init hoặc chọn runtime khác | Chi phí idle và memory |

Không nên tăng concurrency vô hạn. Backpressure, queue limit và admission control giúp hệ thống từ chối sớm hoặc làm chậm producer khi capacity không đủ, thay vì để queue tăng đến mức gây lỗi dây chuyền.

## 17. Chi phí và hiệu năng trên mỗi đơn vị công việc

Khi chọn cấu hình cloud, cần xem hiệu năng cùng chi phí. Một instance lớn hơn có thể tăng throughput nhưng cũng tăng giá; nhiều instance nhỏ hơn có thể cải thiện khả năng scale và HA nhưng tăng overhead mạng, orchestration hoặc license.

Các chỉ số hiệu quả có thể dùng:

- Chi phí trên 1.000 request thành công.
- Chi phí trên một job hoặc một triệu record xử lý.
- Token/s trên mỗi GPU-hour hoặc chi phí trên một triệu token.
- MiB/s trên mỗi đơn vị chi phí storage/network.
- Throughput đạt được ở mức latency và error rate mục tiêu.

Không so sánh cấu hình chỉ bằng request/s nếu một cấu hình có error rate cao hoặc latency vượt mục tiêu. Chỉ tính goodput đạt điều kiện chất lượng đã đặt.

## 18. Những nhầm lẫn thường gặp

**Latency trung bình đại diện trải nghiệm của mọi người dùng.** Phân phối thường lệch và tail latency có thể rất lớn. Theo dõi p50, p95, p99 và tỷ lệ request dưới ngưỡng.

**Throughput là số request được gửi vào.** Offered load khác achieved throughput. Cần đo request/job hoàn tất thành công và phân biệt retry.

**CPU utilization cao luôn xấu.** CPU cao có thể là sử dụng hiệu quả; cần xem run queue, throttling, latency và goodput.

**CPU thấp nghĩa là còn nhiều capacity.** Storage, network, memory, lock hoặc dependency có thể đang bão hòa trước CPU.

**RAM used gần 100% đồng nghĩa thiếu RAM.** Page cache có thể thu hồi; cần xem available memory, swap, page fault, memory pressure và OOM.

**Tăng concurrency luôn tăng throughput.** Sau điểm bão hòa, concurrency cao có thể làm queue và latency tăng mà goodput không tăng.

**Có thể lấy trung bình p95/p99 của từng VM để ra percentile fleet.** Percentile không gộp tuyến tính; cần tổng hợp histogram hoặc dữ liệu request.

**Một lần benchmark đủ để chốt cấu hình.** Kết quả phụ thuộc warm-up, cache, request mix, load generator, thời lượng và dependency. Cần lặp lại và thử các failure scenario quan trọng.

**Một ngưỡng utilization áp dụng được cho mọi workload.** Mục tiêu phải dựa trên điểm saturation, SLO, burst, failure domain và autoscaling delay.

## 19. Checklist đặt mục tiêu và đo hiệu năng

### Trước khi đo

- [ ] Đã xác định hành trình người dùng và loại workload.
- [ ] Đã định nghĩa latency end-to-end và server-side, goodput và offered load.
- [ ] Đã chọn percentile/tỷ lệ dưới ngưỡng, throughput và error target.
- [ ] Đã mô tả request mix, payload, arrival rate, concurrency và dependency.
- [ ] Đã chọn môi trường, cấu hình và dữ liệu test đại diện.
- [ ] Load generator đủ capacity và không trở thành bottleneck.

### Trong khi đo

- [ ] Có warm-up, ramp-up, steady-state và ramp-down.
- [ ] Đo cả client-side và server-side latency.
- [ ] Thu thập p50/p95/p99, goodput, errors và offered load.
- [ ] Theo dõi CPU, memory, storage, network, GPU và saturation phù hợp.
- [ ] Phân biệt closed-loop/open-loop và xử lý coordinated omission.
- [ ] Kiểm tra autoscaling, queue, retry và dependency khi tăng tải.

### Sau khi đo

- [ ] Đã xác định điểm saturation và headroom trong failure scenario cần thiết.
- [ ] Kết quả được so sánh với baseline trong điều kiện tương đương.
- [ ] Bottleneck được xác nhận bằng metric, trace hoặc profile.
- [ ] Mỗi tối ưu có giả thuyết, kết quả và trade-off được ghi nhận.
- [ ] Cấu hình cuối đáp ứng latency, goodput, error và cost target.
- [ ] Dashboard, alert và capacity plan phản ánh cấu hình đã xác minh.

## Kết luận

Latency đo thời gian một thao tác hoàn tất; throughput đo lượng công việc hoàn tất trong một đơn vị thời gian; resource utilization cho biết tài nguyên đang được dùng đến đâu. Cần đọc chúng cùng concurrency, queue, saturation và errors để tìm điểm bão hòa. Mục tiêu hiệu năng nên gắn với workload thực tế, phân phối latency, goodput, tải bình thường/đỉnh và headroom trong failure scenario. Ước lượng từ CPU time, Little's Law, payload và memory giúp sizing ban đầu; benchmark có warm-up, ramp-up, steady-state, soak và stress mới xác minh được cấu hình. Khi đo baseline, xác định bottleneck và tối ưu theo từng giả thuyết, đội vận hành có thể cân bằng trải nghiệm người dùng, capacity và chi phí trên VM, container và serverless.
