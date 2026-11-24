# Phân biệt chỉ số từ hypervisor, hệ điều hành và ứng dụng

Khi một máy ảo hoặc workload chạy chậm, các bảng điều khiển có thể đưa ra những con số khác nhau: nền tảng cloud báo CPU thấp, hệ điều hành thấy CPU gần bão hòa, còn ứng dụng ghi nhận độ trễ tăng. Những số liệu này không nhất thiết mâu thuẫn. Chúng được đo ở các lớp khác nhau, có phạm vi quan sát, cách tính và chu kỳ lấy mẫu khác nhau.

Để chẩn đoán đúng, cần hiểu ba lớp telemetry chính:

- **Lớp hypervisor/nền tảng:** quan sát tài nguyên ảo hóa, máy chủ vật lý và dịch vụ cloud cấp cho VM.
- **Lớp hệ điều hành khách:** quan sát CPU, RAM, disk, network và tiến trình bên trong VM.
- **Lớp ứng dụng:** quan sát request, giao dịch, hàng đợi, dependency và kết quả mà người dùng thực sự nhận được.

Không lớp nào có thể thay thế hoàn toàn hai lớp còn lại. Nền tảng giúp xác định giới hạn và tình trạng hạ tầng; hệ điều hành chỉ ra tài nguyên nào đang bận; ứng dụng cho biết tác động tới chức năng và trải nghiệm. Bài học này hướng dẫn cách đọc, đối chiếu và kết hợp các chỉ số đó để tìm nguyên nhân thay vì chỉ nhìn một dashboard.

## 1. Ba lớp quan sát và ranh giới đo lường

### Lớp hypervisor và nền tảng cloud

Hypervisor là lớp phần mềm ảo hóa phân chia tài nguyên máy chủ vật lý thành các máy ảo. Trong cloud public, người vận hành thường không truy cập trực tiếp hypervisor. Thay vào đó, nhà cung cấp công bố các metric ở cấp VM, host, virtual NIC, volume hoặc dịch vụ quản lý.

Các chỉ số ở lớp này có thể phản ánh:

- CPU time hoặc mức sử dụng vCPU được cấp cho VM.
- Giới hạn hiệu năng của loại máy, CPU credit hoặc throttling theo chính sách.
- Bộ nhớ được cấp phát, mức tiêu thụ ở host hoặc memory pressure nếu nhà cung cấp công bố.
- IOPS, throughput, latency và queue của block volume.
- Byte, packet, drop hoặc giới hạn băng thông của virtual NIC.
- Trạng thái VM, host maintenance, migration và sự kiện nền tảng.
- Quota, capacity và giới hạn dịch vụ.

Không phải cloud provider nào cũng công bố cùng một bộ metric. Một số metric chỉ xuất hiện khi bật monitoring nâng cao, cài guest agent hoặc chọn loại instance phù hợp. Một metric có tên “CPU utilization” cũng có thể có định nghĩa, chu kỳ và phạm vi khác nhau giữa các nền tảng.

### Lớp hệ điều hành khách (guest OS)

Guest OS là hệ điều hành chạy bên trong VM, chẳng hạn Linux hoặc Windows. Nó nhìn thấy CPU ảo, RAM mà VM được cấp, thiết bị block và network interface ảo.

Các metric thường gặp:

- CPU user, system, idle, iowait, steal và run queue.
- RAM total, available, cache, buffer, RSS và swap.
- Page fault, memory pressure và OOM kill.
- Disk read/write, I/O wait, queue depth, filesystem capacity và inode.
- Network bytes, packets, errors, drops, retransmission và connection state.
- Số tiến trình, thread, file descriptor, socket và service health.

Guest OS cho biết tài nguyên được nhìn từ bên trong máy đang được sử dụng như thế nào. Nó không luôn biết host vật lý đang chịu tải ra sao hoặc nhà cung cấp đang giới hạn tài nguyên ở lớp nào.

### Lớp ứng dụng

Ứng dụng nhìn thấy hoạt động nghiệp vụ và thời gian xử lý thực tế:

- Request rate, số giao dịch hoặc job hoàn thành.
- Error rate, timeout, retry và kết quả nghiệp vụ.
- Latency p50, p95, p99 và thời gian từng giai đoạn.
- Queue depth, số worker đang bận và thời gian chờ.
- Connection pool, cache hit ratio và database query latency.
- Thời gian gọi dịch vụ phụ thuộc và lỗi theo endpoint.
- Số phiên, người dùng đồng thời hoặc message đang chờ.

Metric ứng dụng cho biết người dùng có bị ảnh hưởng hay không. CPU có thể thấp nhưng ứng dụng vẫn chậm do database, DNS, lock, queue hoặc dịch vụ bên ngoài.

### Bản đồ quan sát

~~~mermaid
flowchart TB
    U["Người dùng / Client"] --> A["Ứng dụng"]
    A -->|Request, latency, error, queue| AM["Application metrics, logs, traces"]
    A -->|System calls, socket, file I/O| G["Guest OS"]
    G -->|CPU, RAM, disk, network, process| GM["OS metrics và logs"]
    G --> H["Hypervisor / Cloud platform"]
    H -->|vCPU scheduling, virtual NIC, volume, host| HM["Platform metrics và events"]
    AM --> O["Hệ thống observability"]
    GM --> O
    HM --> O
~~~

Sơ đồ thể hiện luồng quan sát khái quát. Metric của ứng dụng, guest và nền tảng thường được thu qua các đường khác nhau rồi hợp nhất trong hệ thống observability.

## 2. Metric là gì và cần đọc metadata nào?

Metric là một phép đo được ghi theo thời gian. Một chuỗi thời gian thường gồm tên metric, giá trị, timestamp và các nhãn mô tả phạm vi.

Ví dụ, CPU utilization của VM có thể có các nhãn:

- instance ID.
- region và availability zone.
- account/project/subscription.
- device hoặc interface.
- environment và service.
- image version hoặc deployment version.

Tên metric và giá trị số chưa đủ. Trước khi so sánh, cần biết đơn vị, loại phép đo, chu kỳ lấy mẫu, phạm vi và cách tổng hợp.

### Ba loại metric cơ bản

| Loại | Ý nghĩa | Ví dụ | Cách đọc |
|---|---|---|---|
| Gauge | Giá trị tại một thời điểm, có thể tăng hoặc giảm | RAM available, queue depth, số connection | Xem giá trị hiện tại, min/max và xu hướng |
| Counter | Tổng tích lũy, thường chỉ tăng và reset khi tiến trình khởi động lại | CPU seconds, số request, bytes sent | Tính tốc độ bằng delta theo thời gian, có xử lý reset |
| Histogram | Phân phối quan sát được chia thành bucket hoặc cấu trúc thống kê | Request duration, response size | Dùng để tính phân vị và xem đuôi phân phối |

Không lấy đạo hàm hoặc rate cho gauge theo cách dành cho counter. Ngược lại, không nên xem giá trị counter tích lũy như số request trong một phút.

### Đơn vị và phạm vi

Các ví dụ đơn vị:

- CPU: phần trăm, vCPU, CPU-seconds.
- RAM: byte, MiB/GiB, phần trăm.
- Disk: bytes/s, operations/s, milliseconds, queue depth.
- Network: bits/s, bytes/s, packets/s, errors.
- Application: requests/s, milliseconds, jobs, messages.

Cần phân biệt bit với byte, MiB với MB, GiB với GB và giá trị tức thời với trung bình theo khoảng thời gian. Một metric 80% được tổng hợp theo trung bình 5 phút có thể che khuất một đỉnh 100% kéo dài 20 giây.

### Nhãn và cardinality

Nhãn giúp lọc và nhóm metric. Ví dụ, lọc theo instance ID để tìm một VM hoặc nhóm theo service để so sánh các replica.

Tuy nhiên, không nên đưa giá trị có cardinality rất cao vào label như user ID, request ID, session ID hoặc URL chứa tham số tùy ý. Số chuỗi thời gian có thể tăng nhanh, làm tốn bộ nhớ và chi phí lưu trữ, đồng thời gây khó khăn cho truy vấn.

Dùng trace ID hoặc log field cho định danh từng request. Giữ metric label ở mức ổn định như service, endpoint template, region, environment và status class.

## 3. CPU: từ host scheduler đến tiến trình

CPU là ví dụ điển hình cho việc ba lớp có thể cho kết quả khác nhau.

### Metric ở lớp hypervisor/nền tảng

Tùy nhà cung cấp, có thể có:

- vCPU utilization hoặc CPU usage của VM.
- CPU credit balance và credit consumption đối với dòng máy burstable.
- CPU throttling hoặc giới hạn hiệu năng.
- CPU ready time hoặc scheduling delay ở một số nền tảng ảo hóa.
- Host maintenance hoặc migration event.

CPU ready là thời gian VM có việc cần chạy nhưng phải chờ hypervisor xếp lịch vCPU lên CPU vật lý. Metric này có ý nghĩa trong một số nền tảng như môi trường VMware, nhưng không phải chỉ số phổ biến được mọi public cloud công bố.

CPU credit của máy burstable phản ánh khả năng duy trì hiệu năng cao theo cơ chế tích lũy và tiêu thụ credit của loại máy. Khi credit thấp hoặc chạm giới hạn, hiệu năng có thể giảm theo chính sách. Không nên áp dụng mô hình credit cho mọi instance family.

### Metric CPU trong Linux

Linux thường chia thời gian CPU thành các nhóm:

- **user:** chạy mã ở user space.
- **system:** chạy kernel code.
- **idle:** CPU không có việc.
- **iowait:** CPU idle trong lúc hệ thống chờ I/O hoàn tất; đây không phải phép đo trực tiếp độ trễ disk.
- **steal:** thời gian guest muốn chạy nhưng hypervisor cấp CPU cho workload khác.
- **irq/softirq:** xử lý interrupt và soft interrupt.

Có thể quan sát bằng:

~~~sh
mpstat -P ALL 1
vmstat 1
top
pidstat -u 1
cat /proc/stat
~~~

Nếu steal time tăng, VM có thể đang chịu tranh chấp lịch CPU ở lớp ảo hóa. Nhưng metric này không được cung cấp hoặc diễn giải giống nhau trên mọi nền tảng. Một số môi trường che giấu hoặc không đo được steal time của guest.

### Metric CPU trong Windows

Windows có thể quan sát CPU ở nhiều phạm vi:

- Processor Time theo logical processor.
- Process/Thread CPU time.
- Processor Queue Length.
- Context switches.
- Hypervisor hoặc virtualization counters nếu host/guest và công cụ hỗ trợ.

Ví dụ PowerShell:

~~~powershell
Get-Counter '\Processor(_Total)\% Processor Time'
Get-Counter '\System\Processor Queue Length'
Get-Counter '\Process(*)\% Processor Time'
~~~

Tên counter có thể được bản địa hóa hoặc khác theo phiên bản Windows. Có thể dùng Performance Monitor để chọn đúng counter trên máy đích.

### Metric CPU ở lớp ứng dụng

Ứng dụng có thể đo:

- Request rate và thời gian xử lý.
- Worker busy/idle.
- Thread pool queue.
- Số task đang chạy.
- CPU time theo process hoặc runtime.
- GC CPU và pause time với ứng dụng JVM.
- Event loop lag với runtime bất đồng bộ.

Một service có CPU cao và request latency cao có thể bị giới hạn compute. Nhưng nếu CPU thấp, queue cao và latency tăng, nguyên nhân có thể là dependency chậm, lock contention hoặc thread pool không được cấp worker.

### Ví dụ đọc chéo CPU

| Nền tảng | Guest OS | Ứng dụng | Giả thuyết cần kiểm tra |
|---|---|---|---|
| CPU cao | CPU cao, run queue cao | Throughput giảm, latency tăng | Thiếu CPU hoặc code xử lý quá nặng |
| CPU thấp | Steal time hoặc throttling tăng | Latency tăng | Giới hạn/scheduling ở lớp ảo hóa hoặc CPU quota |
| CPU thấp | Iowait cao | Request chậm khi đọc dữ liệu | Disk hoặc filesystem đang chậm |
| CPU thấp | CPU thấp, queue tăng | Request chậm, dependency duration tăng | Database, network hoặc service phụ thuộc |
| CPU trung bình thấp | Một core 100% | Một endpoint chậm | Một luồng tuần tự hoặc hotspot đơn luồng |

Không resize CPU chỉ vì utilization cao trong một khoảng ngắn. Hãy xem run queue, throughput, latency, steal/throttle, số core bận và khả năng song song của ứng dụng.

## 4. Memory: bộ nhớ cấp phát, bộ nhớ khả dụng và working set

### Metric ở lớp nền tảng

Nền tảng có thể cung cấp dung lượng RAM cấu hình cho VM, mức sử dụng bộ nhớ host hoặc một số metric memory pressure. Tuy nhiên, nhiều public cloud không thể suy ra chính xác bộ nhớ bên trong guest nếu không có agent hoặc metric do hệ điều hành gửi lên.

Cần phân biệt:

- RAM được cấp cho VM.
- RAM host đang tiêu thụ để hỗ trợ VM.
- RAM guest đang dùng.
- Memory ballooning hoặc host swapping nếu nền tảng công bố.
- Bộ nhớ ứng dụng thực sự cần để giữ working set.

Không coi dung lượng RAM VM được cấu hình là metric mức sử dụng.

### Metric trong Linux

Một số lệnh hữu ích:

~~~sh
free -h
cat /proc/meminfo
vmstat 1
ps -eo pid,comm,rss,vsz --sort=-rss | head
~~~

Các khái niệm quan trọng:

- **Total:** tổng RAM guest nhìn thấy.
- **Available:** ước lượng bộ nhớ có thể cấp phát cho workload mới mà không cần swap đáng kể; thường hữu ích hơn chỉ nhìn free.
- **Cache/buffers:** bộ nhớ dùng làm cache dữ liệu và metadata, một phần có thể thu hồi.
- **RSS:** các trang bộ nhớ đang nằm trong RAM và được ánh xạ vào tiến trình.
- **VSZ:** không gian địa chỉ ảo, không đồng nghĩa RAM vật lý đang dùng.
- **Swap:** vùng lưu trữ dùng làm backing cho trang bộ nhớ bị đẩy khỏi RAM.
- **Page fault:** lỗi trang; minor fault không cần đọc từ disk, major fault cần I/O để nạp trang.
- **OOM kill:** kernel kết thúc tiến trình khi không thể đáp ứng cấp phát trong điều kiện memory pressure.

Memory utilization phần trăm có thể gây hiểu nhầm nếu coi cache có thể thu hồi là bộ nhớ bị chiếm cố định. Nên xem available, working set, swap activity, page fault và OOM cùng lúc.

### Metric trong Windows

Các counter thường dùng:

- Available MBytes.
- Committed Bytes và Commit Limit.
- Pages/sec hoặc page reads/writes.
- Process Working Set và Private Bytes.
- Pool Nonpaged Bytes và Paged Bytes.

Ví dụ:

~~~powershell
Get-Counter '\Memory\Available MBytes'
Get-Counter '\Memory\Committed Bytes'
Get-Counter '\Memory\Pages/sec'
Get-Counter '\Process(*)\Working Set - Private'
~~~

Pages/sec không tự động có nghĩa máy thiếu RAM; cần kết hợp với page reads, available memory, disk activity và tác động ứng dụng.

### Metric memory ở lớp ứng dụng

Ứng dụng/runtime có thể cung cấp:

- Heap used, committed và maximum.
- Garbage collection count, pause và allocation rate.
- Native/direct memory.
- Cache size và eviction.
- Object count hoặc số session.
- Memory theo worker hoặc process.
- OOM, allocation failure và memory leak indicators.

Với JVM, heap used thấp không chứng minh toàn bộ process memory thấp. Native memory, thread stacks, metaspace, direct buffer và thư viện native vẫn tiêu thụ RAM.

### Ví dụ đọc chéo memory

Nếu cloud dashboard cho thấy VM có 32 GiB RAM, Linux báo available còn 1 GiB, process RSS tăng đều và ứng dụng có OOM, có thể là thiếu RAM hoặc memory leak. Nếu Linux báo available thấp nhưng phần lớn là page cache có thể thu hồi, ứng dụng không có OOM và latency ổn định, chưa đủ bằng chứng để tăng RAM.

Nếu guest có available memory lớn nhưng ứng dụng báo allocation failure, cần kiểm tra giới hạn container/cgroup, heap cap, process address space hoặc giới hạn runtime trước khi tăng kích thước VM.

## 5. Storage: volume, thiết bị block, filesystem và thao tác ứng dụng

Storage cũng có nhiều lớp đo lường.

### Lớp nền tảng hoặc volume service

Metric có thể gồm:

- Read/write IOPS.
- Read/write throughput.
- Latency.
- Queue length hoặc outstanding operations.
- Burst balance/credit nếu loại volume có cơ chế burst.
- Throttling hoặc giới hạn provisioned performance.
- Volume status và attach/detach events.

Metric volume thường đo ở dịch vụ lưu trữ hoặc đường đi ảo hóa. Nó có thể không bao gồm toàn bộ thời gian ứng dụng chờ filesystem, lock hoặc xử lý đồng bộ.

### Lớp guest OS

Trên Linux:

~~~sh
iostat -xz 1
lsblk
df -hT
df -i
pidstat -d 1
~~~

Các chỉ số cần hiểu:

- Read/write throughput và operations/s.
- Await hoặc latency trung bình theo cách công cụ định nghĩa.
- Queue depth.
- Utilization của thiết bị.
- I/O wait CPU.
- Filesystem capacity và inode.
- Process I/O bytes.

%util của thiết bị trong một số môi trường NVMe hoặc thiết bị song song không thể diễn giải đơn giản như “100% nghĩa là đạt trần hiệu năng”. Cần xem latency, queue, IOPS và giới hạn thực tế của thiết bị.

Trên Windows, có thể dùng Performance Monitor với các counter như Disk Reads/sec, Disk Writes/sec, Avg. Disk sec/Read, Avg. Disk sec/Write và Current Disk Queue Length.

### Lớp ứng dụng

Ứng dụng có thể đo:

- Database query latency.
- Transaction commit time.
- File read/write duration.
- Cache hit ratio.
- Log flush duration.
- Queue persistence latency.
- Số lần retry hoặc timeout khi truy cập storage.

Một volume có latency thấp nhưng database query chậm có thể do lock, query plan, connection pool hoặc xử lý ứng dụng. Ngược lại, database có query latency tăng cùng lúc volume queue và latency tăng có thể gợi ý nút thắt storage.

### Đọc chéo storage

| Nền tảng/volume | Guest OS | Ứng dụng | Hướng điều tra |
|---|---|---|---|
| IOPS chạm giới hạn | Queue và await tăng | Query latency tăng | Volume throughput/IOPS không đủ hoặc burst cạn |
| Volume latency thấp | Filesystem đầy hoặc hết inode | Upload lỗi | Capacity/inode và quyền truy cập |
| Volume bình thường | Iowait cao ở thiết bị khác | Request chậm | Kiểm tra swap, local disk, log disk hoặc mount khác |
| Volume bình thường | Disk I/O thấp | Database chậm | Lock, query plan, connection pool, CPU hoặc network |

## 6. Network: virtual NIC, TCP stack và request

### Metric ở lớp nền tảng

Nền tảng có thể cung cấp:

- Bytes và packets in/out.
- Packet drop hoặc error.
- Băng thông virtual NIC.
- Network performance limit/throttling.
- Flow logs hoặc network security events.
- Trạng thái load balancer và interface.

Một số metric chỉ đếm traffic ở interface; chúng không cho biết request đã được ứng dụng xử lý hay chưa. Flow log thường mô tả luồng mạng và policy, không thay thế metric latency ở ứng dụng.

### Metric trong guest OS

Trên Linux:

~~~sh
ip -s link
sar -n DEV 1
sar -n TCP,ETCP 1
ss -s
nstat
~~~

Có thể theo dõi:

- RX/TX bytes và packets.
- Interface errors và drops.
- TCP retransmissions.
- Connection resets.
- Listen queue overflow.
- Socket count và connection states.
- DNS lookup time nếu agent hoặc ứng dụng đo.

Trên Windows có thể dùng Performance Monitor với Network Interface counters, TCPv4/TCPv6 và công cụ như Get-NetAdapterStatistics.

### Metric ở lớp ứng dụng

Các metric hữu ích:

- Request rate.
- Connection establishment time.
- DNS resolution duration.
- TLS handshake duration.
- Time to first byte.
- Request duration.
- Upstream/dependency latency.
- Timeout, retry và status code.

Network bytes cao không nhất thiết là sự cố; đó có thể là tải hợp lệ. Cần so với baseline, throughput công việc và error/latency.

### Ví dụ đọc chéo network

Nếu cloud NIC không có drop nhưng Linux báo TCP retransmission tăng, có thể vấn đề nằm ở đường đi xa hơn interface hoặc ở phía peer. Nếu Linux không có retransmission nhưng ứng dụng timeout, hãy kiểm tra DNS, TLS, connection pool, server xử lý chậm hoặc deadline quá ngắn.

Nếu bytes/sec đạt giới hạn network của machine type, latency và queue tăng cùng lúc, có thể cần loại máy có băng thông cao hơn hoặc giảm traffic. Nếu chỉ một endpoint chậm trong khi các endpoint khác bình thường, hãy điều tra dependency cụ thể thay vì resize NIC.

## 7. Metric ứng dụng: RED, USE và các tín hiệu vàng

### RED cho dịch vụ request-driven

RED là cách quan sát dịch vụ qua ba nhóm:

- **Rate:** số request được xử lý trong một đơn vị thời gian.
- **Errors:** số hoặc tỷ lệ request lỗi.
- **Duration:** thời gian xử lý request, thường theo phân vị.

Ví dụ metric:

~~~text
http_server_requests_total
http_server_request_duration_seconds_bucket
http_server_request_duration_seconds_count
http_server_request_duration_seconds_sum
~~~

Tên metric cụ thể phụ thuộc instrumentation. Với Prometheus histogram, có thể tính p95 từ bucket:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(http_server_request_duration_seconds_bucket[5m])
  )
)
~~~

Không lấy trung bình các giá trị p95 của nhiều instance để tạo p95 toàn cụm. Cần tổng hợp histogram bucket hoặc dữ liệu phân phối theo cách đúng.

### USE cho tài nguyên

USE là phương pháp nhìn tài nguyên qua:

- **Utilization:** phần tài nguyên đang bận.
- **Saturation:** mức công việc phải chờ hoặc xếp hàng.
- **Errors:** lỗi khi sử dụng tài nguyên.

Ví dụ:
- CPU utilization, run queue và throttling.
- Disk utilization, queue depth và I/O errors.
- Network utilization, packet queue/drop.
- Connection pool utilization, waiters và acquisition errors.

USE hữu ích cho CPU, disk, network và pool. RED hữu ích cho dịch vụ xử lý request. Kết hợp hai cách giúp nối tài nguyên với tác động dịch vụ.

### Bốn tín hiệu vàng

Một cách khác là theo dõi latency, traffic, errors và saturation. Đây là các tín hiệu giúp phát hiện dịch vụ đang chậm, tải thay đổi, lỗi tăng hoặc tài nguyên bị bão hòa.

Không chỉ theo dõi HTTP status 5xx. Một request có thể trả 200 nhưng kết quả nghiệp vụ sai hoặc quá chậm. Cần metric domain như giao dịch hoàn tất, job thất bại, số message tồn đọng và tỷ lệ xử lý đúng.

## 8. Vì sao metric ba lớp có thể khác nhau?

Chênh lệch thường xuất phát từ ranh giới đo lường chứ không phải hệ thống telemetry bị lỗi.

### Khác phạm vi

- Hypervisor đo tài nguyên được cấp hoặc tiêu thụ ở host.
- Guest OS đo thời gian và tài nguyên mà kernel guest nhìn thấy.
- Process đo CPU/RAM được quy cho một tiến trình.
- Ứng dụng đo thời gian nghiệp vụ, có thể bao gồm cả thời gian chờ network hoặc dependency.

Một ứng dụng chờ database 500 ms có thể có CPU gần 0 trong thời gian đó, trong khi người dùng vẫn thấy request mất 500 ms.

### Khác chu kỳ lấy mẫu và tổng hợp

Nền tảng có thể lấy mẫu mỗi phút, guest agent mỗi 10 giây và Prometheus scrape mỗi 15 giây. Khi hệ thống có burst ngắn, các biểu đồ có thể cho giá trị khác nhau.

Ngoài ra, một dashboard có thể hiển thị average, dashboard khác hiển thị max hoặc percentile. Luôn kiểm tra aggregation period và statistic.

### Khác định nghĩa và đơn vị

Ví dụ:

- CPU usage có thể là phần trăm vCPU, CPU time hoặc phần trăm trên tổng logical processor.
- Memory usage có thể là resident, working set, committed hoặc host consumed.
- Disk latency có thể là latency tại volume service hoặc thời gian hoàn tất I/O ở guest.
- Network throughput có thể tính byte ở interface, không bao gồm overhead hoặc traffic bị loại bỏ.

Không so sánh hai metric chỉ vì tên giống nhau. Đọc định nghĩa metric và đơn vị từ nguồn phát hành.

### Cache và buffering

Guest OS có thể ghi dữ liệu vào page cache rồi hoàn tất thao tác write đối với ứng dụng trước khi dữ liệu được flush xuống volume. Khi đó ứng dụng thấy write nhanh, nhưng volume metric xuất hiện trễ hơn.

Tương tự, đọc dữ liệu từ cache có thể làm ứng dụng nhanh dù volume không có nhiều read IOPS.

### Virtualization và contention

Guest có thể thấy CPU idle hoặc steal tùy cách hypervisor trình bày. Host có thể đang chịu tranh chấp tài nguyên, hoặc VM có thể bị giới hạn bởi CPU credit hay quota. Chỉ số ở lớp guest và provider cần được đọc cùng sự kiện nền tảng.

### Container và cgroup

Một container có thể bị giới hạn CPU/memory dù node VM còn nhiều tài nguyên. Node CPU utilization thấp không chứng minh pod có thể dùng thêm CPU nếu cgroup quota đã chạm giới hạn.

## 9. Container và Kubernetes: thêm một lớp quan sát

Trong môi trường container, cần phân biệt:

1. Hypervisor hoặc cloud VM.
2. Node OS.
3. Container runtime và cgroup.
4. Pod/container.
5. Ứng dụng.

Một metric node không đại diện cho một pod. Một pod có thể bị CPU throttling khi node còn CPU idle vì quota của container đã đạt giới hạn.

### CPU container

Các metric thường gặp:

- CPU usage theo thời gian.
- CPU request và limit.
- CFS throttled periods và throttled time trên Linux cgroup v1/v2.
- Run queue và node CPU pressure.

Cần xem tỷ lệ throttling cùng request latency. CPU usage thấp nhưng throttling cao có thể do giới hạn ngắn hạn hoặc cách tổng hợp metric.

### Memory container

Cần phân biệt:

- Container memory usage.
- Working set.
- RSS/anonymous memory.
- File cache.
- Memory request/limit.
- OOM events và restart count.

Cách exporter tính working set có thể loại trừ một phần cache hoặc metric không reclaimable tùy implementation. Không nên dùng một metric container memory duy nhất để kết luận toàn bộ RAM đang dùng.

### Storage và network container

Pod có thể dùng ephemeral storage, PVC, hostPath hoặc network file share. Node disk metric không chỉ ra pod nào gây I/O nếu không có metric theo cgroup hoặc container runtime.

Network metric có thể xuất hiện ở pod interface, node interface, CNI và cloud NIC. Cần xác định điểm đo để tránh cộng trùng traffic.

### Kiểm tra nhanh Kubernetes

~~~sh
kubectl top nodes
kubectl top pods -A
kubectl describe pod <pod-name> -n <namespace>
kubectl get events -A --sort-by=.lastTimestamp
~~~

`kubectl top` phụ thuộc Metrics Server và không thay thế hệ thống metric lịch sử. Dùng Prometheus, cloud monitoring hoặc nền tảng tương đương để xem xu hướng, throttling và phân vị.

## 10. Thu thập metric và hợp nhất telemetry

### Nguồn dữ liệu phổ biến

| Nguồn | Dữ liệu | Ví dụ công cụ |
|---|---|---|
| Cloud monitoring | VM, volume, NIC, load balancer, quota, event | Amazon CloudWatch, Azure Monitor, Google Cloud Monitoring |
| Guest OS | CPU, RAM, disk, network, process, service | Node Exporter, Windows Exporter, Telegraf, cloud agent |
| Application | Request, business transaction, queue, runtime | Prometheus client, OpenTelemetry SDK, APM agent |
| Logs | Sự kiện và thông tin chi tiết theo request/process | journald, Windows Event Log, Fluent Bit, cloud logging |
| Traces | Đường đi của request qua service và dependency | OpenTelemetry, Jaeger, Tempo, APM backend |
| Events | Deploy, restart, scale, maintenance, failover | Cloud audit/event service, Kubernetes events, CI/CD |

### Agent, exporter và collector

Agent/exporter thu metric từ hệ điều hành hoặc ứng dụng. OpenTelemetry Collector có thể nhận, xử lý, thêm resource attributes và gửi telemetry đến backend.

Một pipeline điển hình:

~~~mermaid
flowchart LR
    P["Cloud platform metrics"] --> C["Collector / ingestion"]
    G["OS exporter / agent"] --> C
    A["Application SDK"] --> C
    L["Logs and events"] --> C
    T["Traces"] --> C
    C --> M["Metrics backend"]
    C --> LG["Logs backend"]
    C --> TR["Trace backend"]
    M --> D["Dashboard và alert"]
    LG --> D
    TR --> D
~~~

Không nhất thiết mọi dữ liệu phải đi qua cùng một collector. Có thể dùng API của cloud provider cho metric nền tảng và agent riêng cho guest OS. Điều quan trọng là metadata nhận dạng có thể liên kết các nguồn.

### Gắn nhãn thống nhất

Nên có một tập resource attributes hoặc labels dùng chung:

- service.name.
- service.version.
- deployment.environment.
- cloud.provider.
- cloud.region.
- cloud.availability_zone.
- cloud.account.id hoặc project ID theo chính sách.
- host.id hoặc instance ID.
- k8s.cluster.name, namespace và pod nếu dùng Kubernetes.

Không dùng hostname làm định danh duy nhất nếu hostname có thể trùng hoặc thay đổi. Dùng instance ID hoặc resource ID ổn định, đồng thời lưu hostname như thuộc tính dễ đọc.

### Đồng bộ thời gian

Timestamp sai lệch khiến việc đối chiếu metric, log và trace trở nên khó khăn. Cần đồng bộ đồng hồ bằng NTP hoặc dịch vụ time synchronization phù hợp, giữ timezone nhất quán trong lưu trữ và hiển thị.

Khi điều tra, so timestamp của:
- Cloud metric.
- Guest OS metric.
- Application log/trace.
- Deployment event.
- VM restart hoặc host maintenance event.

Chú ý độ trễ ingest: thời điểm event xảy ra có thể khác thời điểm dữ liệu xuất hiện trên dashboard.

## 11. Xây dashboard theo câu hỏi vận hành

Một dashboard tốt nên trả lời câu hỏi cụ thể thay vì chỉ chứa thật nhiều biểu đồ.

### Dashboard nền tảng

Hiển thị theo VM hoặc nhóm VM:

- CPU utilization và giới hạn/credit nếu có.
- Memory metric nền tảng nếu có.
- Volume IOPS, throughput, latency và throttling.
- NIC bytes, packets, drops.
- VM state, maintenance và scaling events.
- Quota/capacity nếu liên quan.

### Dashboard hệ điều hành

Hiển thị:

- CPU user/system/idle/iowait/steal.
- Run queue và CPU throttling.
- RAM available, working set, swap và page fault.
- Process top CPU/memory.
- Disk await, queue, throughput và filesystem capacity.
- Network errors, retransmissions và socket states.
- Service state và restart.

### Dashboard ứng dụng

Hiển thị:

- Request rate, errors và p50/p95/p99 latency.
- Throughput nghiệp vụ và kết quả thành công.
- Queue depth và thời gian chờ.
- Dependency latency và error.
- Worker/thread pool saturation.
- Runtime heap, GC, cache và connection pool.
- Deployment version và lỗi theo phiên bản.

### Dashboard liên kết

Một dashboard liên kết nên có bộ lọc chung theo service, environment, region, instance ID và thời gian. Khi chọn một instance hoặc một deployment, người vận hành có thể đi từ latency ứng dụng xuống guest OS rồi tới metric volume/NIC/nền tảng.

Không gộp các metric có đơn vị hoặc ý nghĩa khác nhau vào cùng một biểu đồ chỉ để tiện quan sát. Có thể dùng panel tương ứng theo cùng trục thời gian và annotation cho deployment/maintenance.

## 12. Thiết kế cảnh báo dựa trên tác động

Cảnh báo nên giúp phát hiện vấn đề cần hành động, không chỉ báo mọi metric vượt ngưỡng.

### Cảnh báo hạ tầng

Ví dụ:

- CPU saturation kéo dài kèm run queue tăng.
- CPU credit sắp cạn trên máy burstable.
- Disk latency hoặc queue vượt baseline trong thời gian đủ dài.
- Volume throttling hoặc burst balance thấp.
- Filesystem/inode sắp đầy.
- Network errors hoặc packet drops tăng.
- VM hoặc volume chuyển sang trạng thái bất thường.

### Cảnh báo ứng dụng

Ví dụ:

- p95/p99 latency vượt SLO.
- Error rate tăng.
- Throughput giảm bất thường trong khi traffic còn đến.
- Queue age hoặc backlog tăng liên tục.
- Worker pool bão hòa.
- Dependency timeout hoặc connection pool cạn.

### Kết hợp nhiều điều kiện

Một cảnh báo CPU cao có thể chỉ là tải hợp lệ. Cảnh báo hữu ích hơn khi CPU cao đồng thời latency tăng hoặc throughput không đạt mục tiêu.

Ví dụ logic:

~~~text
IF cpu_utilization > 85% FOR 10 minutes
AND request_p95 > service_latency_slo
THEN alert = "Compute saturation affects service"
~~~

Ngưỡng 85% chỉ là ví dụ. Cần hiệu chỉnh theo workload, baseline và SLO.

### Missing data và alert fatigue

Metric không có dữ liệu có thể do exporter chết, network lỗi, VM dừng hoặc pipeline ingest gặp sự cố. Không mặc định missing data bằng zero. Tạo cảnh báo riêng cho telemetry stale hoặc target mất scrape.

Dùng thời gian duy trì, hysteresis hoặc cooldown để tránh cảnh báo bật/tắt liên tục. Phân loại severity theo tác động và chỉ định người nhận, runbook hoặc bước tiếp theo.

## 13. Quy trình chẩn đoán khi các lớp báo khác nhau

Một quy trình điều tra có thể thực hiện theo thứ tự:

1. Xác định triệu chứng người dùng: latency, lỗi, throughput hoặc job chậm.
2. Chọn service, instance, region và khoảng thời gian chính xác.
3. Đánh dấu deployment, restart, scale, maintenance và sự kiện liên quan.
4. Xem metric ứng dụng để xác định endpoint hoặc dependency bị ảnh hưởng.
5. Xem guest OS để tìm CPU, memory, disk, network hoặc process bottleneck.
6. Xem metric nền tảng để xác định throttling, quota, volume limit hoặc host event.
7. So timestamp, đơn vị, aggregation period và label giữa các nguồn.
8. Đặt giả thuyết có thể kiểm chứng.
9. Thử một thay đổi hoặc phép đo có phạm vi nhỏ.
10. Xác nhận tác động bằng metric ứng dụng và hạ tầng trước/sau.

### Ma trận triệu chứng

| Triệu chứng ứng dụng | Guest OS | Nền tảng | Giả thuyết và bước tiếp theo |
|---|---|---|---|
| Latency tăng, throughput giảm | CPU cao, run queue cao | vCPU gần giới hạn | Profile code, xem khả năng song song, cân nhắc thêm CPU |
| Latency tăng | CPU thấp, iowait cao | Volume latency/queue tăng | Kiểm tra IOPS, throughput, burst và pattern I/O |
| Latency tăng | Available RAM thấp, swap tăng | RAM VM cố định hoặc memory pressure | Xem process RSS, leak, heap và working set |
| Latency tăng | Steal hoặc throttling tăng | CPU credit/limit hoặc scheduling event | Kiểm tra loại máy, quota và host/platform event |
| Request timeout | Retransmission tăng | NIC drop hoặc network limit | Kiểm tra route, security policy, NIC limit và peer |
| Request timeout | CPU/RAM/Disk bình thường | Hạ tầng bình thường | Kiểm tra DNS, TLS, dependency, queue và connection pool |
| Chỉ một pod chậm | Node còn tài nguyên, pod throttled | VM bình thường | Kiểm tra cgroup CPU limit, request và scheduler |
| Database chậm | Disk guest bình thường | Volume bình thường | Kiểm tra lock, query plan, connection pool và replication |

Ma trận chỉ đưa ra giả thuyết ban đầu. Cần xác minh bằng log, trace, profile và phép đo bổ sung trước khi thay đổi cấu hình.

## 14. Ví dụ thực tế: API chậm dù cloud CPU thấp

Một dịch vụ API trên VM có metric nền tảng cho thấy CPU trung bình 35%. Dashboard ứng dụng lại báo p95 latency tăng từ 120 ms lên 900 ms. Nếu chỉ nhìn cloud CPU, nhóm vận hành có thể kết luận VM còn dư năng lực.

Khi kiểm tra sâu hơn:

- Guest OS báo iowait tăng trong cùng khoảng thời gian.
- iostat cho thấy await và queue của thiết bị dữ liệu tăng.
- Volume metric cho thấy throughput đã chạm giới hạn cấu hình trong giờ cao điểm.
- Trace cho thấy thời gian chủ yếu nằm ở thao tác đọc database.
- Request rate tăng gần gấp đôi sau một chiến dịch.

Nhóm xác định bottleneck ở đường lưu trữ/database. Việc tăng vCPU có thể không giải quyết được vấn đề. Họ kiểm tra query plan, cache, I/O pattern và giới hạn volume, sau đó thử cấu hình storage phù hợp hơn trong staging. Kết quả được đánh giá bằng query latency, API p95, throughput và chi phí trên mỗi request.

Ví dụ này cho thấy metric ứng dụng phát hiện tác động, guest OS khoanh vùng tài nguyên và metric nền tảng xác nhận giới hạn dịch vụ.

## 15. Ví dụ thực tế: VM CPU thấp nhưng workload bị throttling

Một pod chạy trên node Kubernetes có CPU usage trung bình thấp. Node OS chỉ dùng khoảng một nửa CPU, nhưng endpoint của pod có latency cao và thời gian xử lý không ổn định.

Metric container cho thấy:

- CPU limit của pod thấp.
- CFS throttled periods tăng.
- Một số thời điểm CPU usage chạm quota.
- Node vẫn còn CPU idle.

Nguyên nhân là giới hạn CPU của container, không phải thiếu CPU ở VM. Nhóm xem lại request/limit, concurrency và số worker; sau đó thử điều chỉnh quota và đo lại latency, throttling cùng mức sử dụng node.

Nếu chỉ tăng machine type, pod vẫn có thể bị giới hạn bởi CPU limit cũ. Phải kiểm tra đúng lớp áp dụng quota.

## 16. Chất lượng dữ liệu telemetry và giới hạn quan sát

### Scrape interval và retention

Scrape quá thưa có thể bỏ lỡ burst; scrape quá dày làm tăng tải agent, network và backend. Chọn interval theo mục tiêu phát hiện và chi phí. Dữ liệu raw có thể giữ trong thời gian ngắn, sau đó downsample hoặc aggregate để lưu xu hướng dài hạn.

### Histogram và percentile

Latency thường có phân phối lệch. Average có thể che khuất một nhóm request rất chậm. Dùng histogram hoặc summary phù hợp để tính p95/p99.

Nếu dùng summary tạo percentile tại từng instance, không thể gộp các percentile đó một cách chính xác thành percentile toàn cụm. Histogram bucket có thể tổng hợp trước khi tính quantile nếu bucket schema tương thích.

### Counter reset

Counter có thể reset khi process restart. Khi tính rate, dùng hàm xử lý counter reset của hệ thống query thay vì tự lấy hiệu đơn giản trên hai điểm nếu có khả năng reset.

### Missing và stale series

Một metric không xuất hiện có thể do:
- Agent/exporter không chạy.
- Target không scrape được.
- Label hoặc metric name thay đổi sau deploy.
- VM dừng hoặc bị thay thế.
- Pipeline ingest hoặc quota backend gặp lỗi.
- Metric chỉ được phát khi có sự kiện.

Dashboard cần phân biệt zero, null và stale. Alert phải kiểm tra telemetry health riêng.

### Sampling và overhead

Tracing có thể sampling một phần request để giảm chi phí. Log có thể bị lọc hoặc giới hạn tốc độ. Metric có thể aggregate trước khi gửi. Vì vậy, không phải mọi request đều có trace hoặc log chi tiết. Hãy hiểu sampling policy và giữ metric tổng hợp đủ tin cậy để phát hiện xu hướng.

## 17. Quy trình xây dựng observability cho workload compute

1. **Xác định SLO:** latency, availability, throughput hoặc thời gian hoàn thành job.
2. **Liệt kê tài nguyên:** VM, vCPU, RAM, volume, NIC, container, process và dependency.
3. **Chọn metric từng lớp:** provider, guest OS và application.
4. **Chuẩn hóa định danh:** instance ID, service, environment, region và version.
5. **Thiết lập đồng bộ thời gian:** NTP/time service và timestamp thống nhất.
6. **Triển khai collector:** cloud API, OS exporter, application instrumentation và log/trace agent.
7. **Xác minh đơn vị/semantics:** đọc định nghĩa, sample interval và aggregation.
8. **Xây dashboard theo câu hỏi:** tác động người dùng, tài nguyên, dependency và platform event.
9. **Định nghĩa alert:** gắn với SLO, saturation và telemetry health.
10. **Viết runbook:** mô tả cách đối chiếu ba lớp và các bước xác minh.
11. **Kiểm thử sự cố:** CPU saturation, memory pressure, disk throttling, packet loss và exporter failure.
12. **Tối ưu chi phí:** giảm label cardinality, scrape không cần thiết và retention quá dài.

### Tiêu chí nghiệm thu

Một hệ thống observability compute có thể được xem là đủ nền tảng khi:

- Có metric nền tảng cho VM, disk và NIC phù hợp.
- Có metric guest OS cho CPU, memory, storage và network.
- Có metric ứng dụng cho request, error, latency và workload queue.
- Các nguồn có thể liên kết theo instance/service/time.
- Dashboard thể hiện rõ đơn vị và aggregation.
- Alert phân biệt sự cố workload với lỗi telemetry.
- Có runbook điều tra khi ba lớp không khớp.
- Có kiểm tra cardinality, retention và chi phí.

## 18. Checklist đọc và đối chiếu metric

- [ ] Đã xác định metric đến từ hypervisor/cloud, guest OS hay application.
- [ ] Đã đọc định nghĩa, đơn vị và phạm vi của metric.
- [ ] Đã xác định metric là gauge, counter hay histogram.
- [ ] Đã kiểm tra sample interval và cách aggregation.
- [ ] Đã lọc cùng instance ID, region, service và time range.
- [ ] Đã đồng bộ timestamp hoặc tính đến ingest delay.
- [ ] CPU được xem cùng run queue, steal/throttling và application latency.
- [ ] Memory được xem cùng available, working set, swap, OOM và runtime heap.
- [ ] Storage được xem cùng IOPS, throughput, queue, filesystem và query latency.
- [ ] Network được xem cùng bytes, drops, retransmission, DNS/TLS và request timeout.
- [ ] Container quota/cgroup được kiểm tra khi node còn tài nguyên.
- [ ] Percentile được tổng hợp từ histogram đúng cách.
- [ ] Missing data được phân biệt với giá trị zero.
- [ ] Dashboard có deployment và platform event để đối chiếu.
- [ ] Alert gắn với SLO hoặc saturation và có runbook.
- [ ] Label không gây cardinality quá cao.
- [ ] Telemetry agent và backend được giám sát như một phần của hệ thống.

## Kết luận

Metric từ hypervisor/nền tảng, guest OS và ứng dụng mô tả các phần khác nhau của cùng một workload. Nền tảng cho biết giới hạn và trạng thái tài nguyên ảo hóa; hệ điều hành cho biết CPU, RAM, disk, network và tiến trình đang hoạt động ra sao; ứng dụng cho biết request và nghiệp vụ bị ảnh hưởng thế nào. Muốn chẩn đoán chính xác, cần đọc định nghĩa và đơn vị, căn chỉnh thời gian, liên kết theo instance/service, rồi đối chiếu các lớp bằng cùng một triệu chứng. Kết hợp RED cho dịch vụ, USE cho tài nguyên, metric nền tảng và trace/log giúp tìm bottleneck có bằng chứng, thiết kế cảnh báo theo SLO và tránh resize sai thành phần.
