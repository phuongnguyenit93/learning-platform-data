# Thu thập CPU, memory, swap, disk và network bằng agent

## Mục tiêu bài học

Để vận hành máy ảo và workload trên đám mây, đội ngũ cần biết tài nguyên compute đang được sử dụng như thế nào. CPU có thể bị bão hòa, bộ nhớ có thể thiếu, swap có thể tăng, filesystem có thể đầy hoặc network interface có thể phát sinh lỗi. Nếu chỉ quan sát mức sử dụng CPU tổng thể, nhiều vấn đề quan trọng sẽ bị bỏ sót.

Agent giám sát chạy trên máy chủ hoặc node giúp thu thập các chỉ số hệ điều hành, chuẩn hóa dữ liệu, bổ sung thông tin nhận diện workload và gửi metric tới nền tảng monitoring tập trung.

Sau bài học này, bạn có thể:

- Giải thích luồng thu thập metric từ host tới hệ thống monitoring.
- Chọn metric CPU, memory, swap, disk và network phù hợp.
- Phân biệt counter, gauge và rate để đọc số liệu đúng.
- Cài đặt và cấu hình agent/collector với quyền tối thiểu.
- Thu thập metric trên Linux, Windows, VM và node Kubernetes.
- Thiết kế nhãn, chu kỳ thu thập, cảnh báo và kiểm tra chất lượng dữ liệu.

## 1. Vì sao cần agent giám sát?

Máy ảo và node compute có nhiều trạng thái không thể quan sát đầy đủ chỉ từ số liệu của ứng dụng. Ví dụ, API có thể phản hồi chậm vì CPU bị steal trên hypervisor, hệ thống bắt đầu swap, disk latency tăng hoặc network interface có packet drop. Nếu chỉ xem application latency, đội vận hành biết dịch vụ chậm nhưng chưa xác định được tầng tài nguyên gây ra vấn đề.

Agent giám sát (monitoring agent) là tiến trình hoặc dịch vụ chạy trên máy cần quan sát. Agent đọc số liệu từ hệ điều hành, bộ đếm hiệu năng hoặc API runtime rồi gửi metric về một collector/backend.

Các nhiệm vụ phổ biến:

- Đọc bộ đếm CPU, bộ nhớ, paging/swap, filesystem, block device và network interface.
- Chuẩn hóa đơn vị, tên metric và timestamp.
- Bổ sung metadata như hostname, instance ID, zone, môi trường và vai trò máy.
- Gửi metric theo giao thức được backend hỗ trợ.
- Buffer dữ liệu tạm thời khi kết nối gián đoạn, nếu agent có hỗ trợ.
- Báo trạng thái agent để phát hiện máy không còn gửi dữ liệu.

Agent không tự giải quyết mọi vấn đề quan sát. Metric cần được lưu trữ, truy vấn, hiển thị và liên kết với log/trace. Một hệ thống monitoring hoàn chỉnh thường gồm agent hoặc exporter, collector, pipeline vận chuyển, time-series backend, dashboard và alerting.

~~~mermaid
flowchart LR
    H["VM / host / node"] --> A["Agent hoặc exporter"]
    A --> C["Collector / telemetry pipeline"]
    C --> B["Metrics backend"]
    B --> D["Dashboard và truy vấn"]
    B --> E["Alerting / notification"]
    L["Application logs và traces"] --> C
    M["Cloud metadata / inventory"] --> C
~~~

Trong module compute, mục tiêu là quan sát tài nguyên nền tảng phục vụ workload: CPU, memory, swap, disk và network. Những metric này giúp xác định năng lực máy, phát hiện nghẽn tài nguyên, hỗ trợ sizing và đánh giá tác động khi mở rộng tải.

## 2. Agent, exporter và collector khác nhau thế nào?

Các công cụ monitoring có thể dùng nhiều tên gọi. Cần phân biệt vai trò thay vì chỉ dựa vào tên sản phẩm.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Agent | Tiến trình chạy trên host, thu thập và thường gửi telemetry | Cloud monitoring agent, OpenTelemetry Collector chạy dạng agent |
| Exporter | Cung cấp metric từ một hệ thống dưới định dạng mà collector có thể đọc | Prometheus Node Exporter |
| Collector | Nhận, xử lý, bổ sung metadata, lọc và chuyển tiếp telemetry | OpenTelemetry Collector, Prometheus |
| Backend | Lưu trữ và truy vấn metric theo thời gian | Prometheus-compatible backend, dịch vụ monitoring của cloud |
| Dashboard/alerting | Trình bày trạng thái và đánh giá điều kiện cảnh báo | Grafana hoặc giao diện monitoring của nhà cung cấp |

Một số mô hình thường gặp:

**Agent push:** agent thu thập metric rồi gửi đến endpoint tập trung. Mô hình này phù hợp khi host nằm sau firewall hoặc backend không thể chủ động truy cập vào host. Cần quản lý xác thực, chứng thư, retry và buffer.

**Exporter pull:** exporter mở endpoint metric; Prometheus hoặc collector chủ động scrape theo chu kỳ. Cần giới hạn địa chỉ có thể truy cập endpoint và bảo vệ endpoint nếu có dữ liệu nhạy cảm.

**Agent kết hợp collector:** agent đọc metric cục bộ, sau đó collector xử lý và gửi tới một hoặc nhiều backend. Cách này cho phép chuẩn hóa dữ liệu và thay đổi backend mà không phải cài một công cụ khác trên mọi máy.

Không có mô hình duy nhất phù hợp cho tất cả môi trường. Hãy chọn dựa trên mạng, quy mô, backend, yêu cầu bảo mật, khả năng quản lý phiên bản và mức độ tích hợp với nền tảng cloud.

## 3. Hiểu đúng các loại metric

Metric thường có timestamp, tên, giá trị, đơn vị và tập nhãn (labels/attributes). Trước khi tạo dashboard hoặc cảnh báo, cần biết loại dữ liệu đang quan sát.

- **Gauge:** giá trị tại một thời điểm, có thể tăng hoặc giảm. Ví dụ memory đang dùng, dung lượng filesystem còn trống, số kết nối hiện tại.
- **Counter:** bộ đếm tích lũy, thường chỉ tăng cho tới khi tiến trình hoặc máy khởi động lại. Ví dụ tổng byte đã truyền, tổng packet lỗi, tổng số lần context switch.
- **Rate:** tốc độ thay đổi của counter trong một khoảng thời gian. Ví dụ byte/giây hoặc packet lỗi/giây.
- **Histogram:** phân phối các phép đo theo bucket, thường dùng cho độ trễ hoặc kích thước; không phải dạng chính để biểu diễn các chỉ số host cơ bản nhưng có thể hữu ích cho workload.

Không so sánh counter thô giữa hai thời điểm như thể đó là tốc độ. Với counter, thường cần tính rate hoặc delta theo thời gian. Khi máy khởi động lại, counter có thể reset; hệ thống truy vấn phải xử lý reset đúng cách.

Đơn vị cần nhất quán:

| Loại dữ liệu | Đơn vị thường dùng |
|---|---|
| CPU time | Giây tích lũy hoặc phần trăm thời gian |
| CPU utilization | Phần trăm (%) |
| Memory | Byte, KiB, MiB hoặc GiB |
| Swap | Byte và byte/giây |
| Disk I/O | Byte/giây, operation/giây (IOPS), giây hoặc mili giây |
| Network | Byte/giây, packet/giây, số lỗi hoặc số drop |

Khi dashboard hiển thị phần trăm, hãy kiểm tra mẫu số. CPU 50% có thể là một nửa tổng công suất toàn máy hoặc mức trung bình của một tập core, tùy cách tính. Memory 80% có thể tính theo tổng RAM hoặc theo memory available. Không so sánh hai dashboard nếu định nghĩa metric khác nhau.

## 4. Thu thập CPU

CPU metric giúp trả lời: máy có đủ năng lực xử lý không, thời gian CPU được dùng cho công việc nào và workload có bị giới hạn bởi scheduler hoặc hypervisor không?

Các metric quan trọng:

| Metric | Ý nghĩa | Cách diễn giải |
|---|---|---|
| CPU utilization | Tỷ lệ thời gian CPU bận trong khoảng đo | Tăng kéo dài có thể cho thấy CPU pressure |
| User time | Thời gian chạy mã ở user space | Có thể tăng do ứng dụng tính toán |
| System time | Thời gian chạy kernel | Tăng có thể liên quan syscall, I/O hoặc xử lý mạng |
| I/O wait | Thời gian CPU nhàn rỗi trong khi hệ thống chờ I/O | Tăng có thể đi cùng disk latency hoặc I/O contention |
| Steal time | Thời gian vCPU sẵn sàng chạy nhưng hypervisor cấp CPU vật lý cho workload khác | Có thể phản ánh tranh chấp CPU ở host ảo hóa |
| Load average / run queue | Số lượng task runnable hoặc chờ uninterruptible theo cách tính của hệ điều hành | Cần so với số CPU và trạng thái workload |
| CPU throttling | Thời gian hoặc số lần container bị giới hạn CPU quota | Có thể giải thích latency dù node vẫn còn CPU |
| Context switches | Số lần chuyển ngữ cảnh | Tăng mạnh có thể đi cùng quá nhiều thread hoặc tranh chấp |

### 4.1. CPU utilization không nói lên toàn bộ câu chuyện

Một máy 16 vCPU có utilization trung bình 40% vẫn có thể có một core bão hòa nếu workload đơn luồng. Hãy xem theo từng CPU/core khi cần. Với VM, steal time có thể quan trọng vì guest thấy CPU chưa được cấp dù ứng dụng có việc để chạy.

Trong Linux, CPU time thường được đọc từ /proc/stat. Lệnh mpstat trong gói sysstat có thể hiển thị tỷ lệ user, system, iowait, steal và idle theo từng CPU:

~~~bash
# Tổng quan CPU và load
uptime
lscpu

# Theo dõi CPU theo từng core mỗi giây, lấy 5 mẫu
mpstat -P ALL 1 5

# Theo dõi run queue, swap và một số bộ đếm hệ thống
vmstat 1 5
~~~

Trên Windows, Performance Monitor (PerfMon) hoặc PowerShell Get-Counter có thể đọc bộ đếm như Processor(_Total)\% Processor Time, System\Processor Queue Length và bộ đếm theo từng processor.

~~~powershell
Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 5
Get-Counter '\System\Processor Queue Length' -SampleInterval 2 -MaxSamples 5
~~~

Tên counter có thể được bản địa hóa theo ngôn ngữ Windows. Agent Windows thường đọc các performance counter tương đương và xuất chúng thành metric.

### 4.2. CPU trong container

Container có thể bị giới hạn bằng CPU quota hoặc cpuset. Cần quan sát cả node CPU và container CPU:

- CPU usage của container.
- CPU limit/request.
- Throttled periods và throttled time.
- CPU usage theo Pod/container.
- Node allocatable và mức sử dụng tổng thể.

Nếu CPU của Pod chạm quota, container có thể bị throttling ngay cả khi node còn CPU rảnh ở core khác. Khi đó cần xem limit, cpuset, scheduler và mức song song của ứng dụng trước khi tăng vCPU cho cả node.

## 5. Thu thập memory

Memory metric giúp phát hiện áp lực RAM, rò rỉ bộ nhớ, cache lớn, giới hạn cgroup và nguy cơ bị hệ điều hành kết thúc tiến trình.

Các chỉ số nên thu thập:

| Metric | Ý nghĩa | Lưu ý |
|---|---|---|
| Total memory | Tổng RAM hệ thống nhìn thấy | Có thể khác dung lượng vật lý do firmware/hypervisor |
| Used memory | Bộ nhớ đang dùng theo định nghĩa của công cụ | Cần hiểu cách tính cache/buffer |
| Available memory | Ước tính RAM có thể cấp cho ứng dụng mà không cần swap mạnh | Thường hữu ích hơn chỉ nhìn free memory |
| Cached/buffer memory | Bộ nhớ dùng làm cache hoặc buffer có thể được thu hồi ở mức độ nhất định | Không mặc định là memory leak |
| Working set / resident memory | Trang bộ nhớ hiện đang resident của tiến trình hoặc workload | Có thể khác virtual memory size |
| Page faults | Số lần truy cập trang không có trong page table hoặc phải nạp lại | Cần phân biệt minor và major fault |
| Memory pressure / OOM | Tình trạng thiếu memory hoặc tiến trình bị kết thúc | Cần xem kernel log, cgroup và container events |

Linux dùng RAM trống để cache filesystem nhằm tăng tốc I/O. Vì vậy, free thấp không nhất thiết là vấn đề nếu available còn đủ và hệ thống không có paging/pressure bất thường.

Lệnh kiểm tra Linux:

~~~bash
free -h
cat /proc/meminfo
vmstat 1 5
ps -eo pid,comm,rss,vsz,%mem --sort=-rss | head
~~~

Trong đó:

- free -h hiển thị tổng, used, free, shared, buff/cache và available.
- /proc/meminfo cung cấp các trường chi tiết như MemAvailable, Cached, Buffers và SwapTotal.
- vmstat cho biết một số trạng thái memory, swap và run queue.
- RSS gần với số trang resident của process; VSZ là không gian địa chỉ ảo được ánh xạ và không đồng nghĩa với RAM thực đang chiếm.

Trên Windows, các counter hữu ích gồm Memory\Available MBytes, Memory\Committed Bytes, Memory\% Committed Bytes In Use, Process(*)\Working Set - Private và Memory\Pages/sec. Cần phân biệt committed memory với RAM resident; một tiến trình có thể commit nhiều bộ nhớ nhưng không giữ toàn bộ trong RAM cùng lúc.

### 5.1. Memory trong container và cgroup

Trong container, số liệu memory của host không cho biết một container riêng lẻ đang dùng bao nhiêu so với giới hạn của nó. Agent cần thu thập metric theo cgroup hoặc nguồn runtime tương ứng:

- Memory usage hiện tại.
- Memory limit và request.
- Working set hoặc usage sau khi loại trừ cache theo định nghĩa công cụ.
- OOM kill và memory events.
- Page fault hoặc memory pressure nếu có thể lấy.

Cần kiểm tra phiên bản cgroup và runtime. Cgroup v1 và v2 có file, counter và ngữ nghĩa khác nhau; agent nên hỗ trợ phiên bản đang dùng. Không so sánh memory.current, working set và RSS như thể chúng có cùng định nghĩa.

## 6. Thu thập swap và paging

Swap là vùng lưu trữ được hệ điều hành dùng làm backing store cho một số trang bộ nhớ không nằm trong RAM. Trên Linux, swap có thể là partition hoặc file. Windows sử dụng page file với cơ chế quản lý bộ nhớ ảo riêng.

Swap giúp hệ điều hành có thêm không gian quản lý bộ nhớ, nhưng hoạt động paging quá nhiều có thể làm tăng độ trễ do storage chậm hơn RAM.

Metric cần quan sát:

- Tổng dung lượng swap và dung lượng đang dùng.
- Tốc độ swap-in và swap-out.
- Số page-in/page-out.
- Major page faults.
- Memory pressure và OOM event.
- Page file usage trên Windows.

Một máy có swap usage khác 0 chưa chắc gặp sự cố. Hệ điều hành có thể giữ một số trang ít dùng trong swap dù áp lực hiện tại đã giảm. Tín hiệu đáng quan tâm hơn là swap-in/swap-out liên tục, major faults tăng, memory available thấp và latency ứng dụng xấu đi cùng lúc.

Linux:

~~~bash
# Dung lượng swap
swapon --show
free -h

# Theo dõi swap-in (si) và swap-out (so)
vmstat 1 10

# Thống kê paging và hoạt động bộ nhớ
sar -W 1 5
~~~

Windows có thể theo dõi Paging File(_Total)\% Usage, Memory\Pages Input/sec, Memory\Pages Output/sec và các counter liên quan. Tên và sự sẵn có phụ thuộc phiên bản OS.

Không nên cảnh báo chỉ vì swap usage vượt một ngưỡng cố định. Hãy kết hợp mức swap, tốc độ paging, memory available, OOM và hiệu năng workload. Nếu hệ thống không dùng swap theo thiết kế, cần phân biệt trạng thái cấu hình swap bằng 0 với agent không thu thập được metric.

## 7. Thu thập disk và filesystem

Disk có hai khía cạnh cần tách biệt:

- **Filesystem capacity:** dung lượng và inode còn trống trong filesystem được mount.
- **Block device performance:** tốc độ và độ trễ của thiết bị lưu trữ bên dưới.

Một filesystem còn nhiều dung lượng vẫn có thể chạy chậm do IOPS hoặc latency cao. Ngược lại, disk có throughput thấp nhưng không gây ảnh hưởng nếu workload chỉ đọc ít dữ liệu.

### 7.1. Dung lượng filesystem

Các metric quan trọng:

- Tổng dung lượng, dung lượng đã dùng và còn trống.
- Tỷ lệ sử dụng.
- Inode đã dùng và còn trống trên filesystem hỗ trợ inode.
- Mount point, filesystem type và trạng thái read-only.
- Dung lượng của volume được cấp phát so với dung lượng filesystem thực tế.

Linux:

~~~bash
# Dung lượng filesystem theo mount point
df -hT

# Inode
df -i

# Các block device, quan hệ partition và mount
lsblk -f

# Xác định filesystem đang mount
findmnt
~~~

Windows có thể thu thập dung lượng volume qua logical disk counter, WMI/CIM hoặc API hệ điều hành. Các counter thường dùng gồm LogicalDisk(*)\Free Megabytes và % Free Space.

Agent cần lọc các filesystem ảo hoặc tạm thời không cần giám sát, ví dụ một số tmpfs, overlay hoặc mount của runtime. Tuy nhiên, không lọc tất cả filesystem container một cách mù quáng vì có thể bỏ qua volume dữ liệu thật.

### 7.2. Hiệu năng block device

Metric thường dùng:

| Metric | Ý nghĩa |
|---|---|
| Read/write bytes per second | Throughput đọc/ghi |
| Read/write operations per second | IOPS |
| Average read/write latency | Thời gian hoàn tất I/O |
| I/O queue depth | Số request đang chờ hoặc đang xử lý |
| Device utilization | Mức độ thiết bị bận theo cách đo của OS |
| I/O errors/timeouts | Lỗi hoặc timeout ở tầng block device |

Linux:

~~~bash
# I/O theo thiết bị mỗi giây
iostat -xz 1 5

# Thống kê block device từ kernel
cat /proc/diskstats

# Tìm process đang tạo I/O (nếu sysstat/iotop được cài)
pidstat -d 1 5
~~~

Trên Windows, PerfMon có các counter như PhysicalDisk(*)\Disk Reads/sec, Disk Writes/sec, Disk Read Bytes/sec, Disk Write Bytes/sec, Avg. Disk sec/Read, Avg. Disk sec/Write và Current Disk Queue Length.

Một số nền tảng cloud cung cấp metric riêng của volume như IOPS, throughput, burst balance hoặc queue length. Metric từ host và metric của dịch vụ block storage có thể khác nhau do cache, virtualization và cách đo. Hãy đối chiếu cả hai khi điều tra disk bottleneck.

### 7.3. Inode và file handle

Filesystem có thể hết inode dù còn byte trống. Khi đó ứng dụng không tạo được file mới. Tương tự, một process có thể cạn file descriptor hoặc handle dù disk còn dung lượng.

Với workload tạo nhiều file nhỏ, hãy theo dõi inode usage. Với ứng dụng mở nhiều file/socket, theo dõi file descriptor, handle hoặc giới hạn process phù hợp. Đây không phải metric disk capacity thuần túy nhưng thường giúp giải thích lỗi ghi dữ liệu.

## 8. Thu thập network

Network metric giúp xác định máy có truyền dữ liệu đúng dự kiến, có packet loss hoặc lỗi interface hay không.

Các metric nên thu thập:

- Bytes received/sent.
- Packets received/sent.
- Receive/transmit errors.
- Receive/transmit drops.
- Interface state và tốc độ link khi có thể đọc.
- TCP retransmissions, connection count và socket state.
- DNS request/error hoặc network latency nếu agent và công cụ hỗ trợ.
- Flow log hoặc cloud network telemetry để hiểu kết nối giữa tài nguyên.

Linux:

~~~bash
# Interface, địa chỉ và trạng thái
ip -s link

# Socket và trạng thái kết nối
ss -s
ss -tan

# Counter interface
cat /proc/net/dev

# Thống kê TCP
nstat
~~~

Nếu có sar từ sysstat:

~~~bash
sar -n DEV 1 5
sar -n TCP,ETCP 1 5
~~~

Windows có thể dùng PerfMon counter như Network Interface(*)\Bytes Total/sec, Bytes Received/sec, Bytes Sent/sec, Packets Received Errors, Packets Outbound Errors và TCP connection counter. Tên counter phụ thuộc locale và phiên bản.

### 8.1. Throughput không đồng nghĩa với network health

Throughput thấp có thể là bình thường nếu ứng dụng không có traffic. Throughput cao có thể hợp lệ khi batch chạy. Packet drop, retransmission hoặc lỗi interface tăng mới là tín hiệu cần xem xét cùng tải.

Đối với cloud VM, băng thông thực tế có thể bị giới hạn theo loại instance, kích thước VM, số flow, placement hoặc chính sách nền tảng. Một số instance có cơ chế burst hoặc giới hạn theo tổng lưu lượng. Hãy so sánh metric guest với metric phía cloud provider khi cần xác định giới hạn nằm ở guest OS hay hạ tầng mạng.

### 8.2. Network trong container

Trên Kubernetes, metric network có thể xuất hiện ở nhiều lớp:

- Pod/container network bytes và packets.
- Node interface.
- Virtual interface hoặc bridge.
- CNI dataplane.
- Cloud NIC hoặc load balancer.

Không cộng tất cả các lớp lại như thể chúng là traffic độc lập; cùng một gói tin có thể được đếm ở nhiều điểm. Xác định điểm đo và chiều traffic trước khi lập dashboard.

## 9. Kiến trúc thu thập metric bằng agent

Một pipeline host metric cơ bản có các bước:

1. Agent đọc dữ liệu từ API hệ điều hành, /proc, sysfs, performance counter hoặc cgroup.
2. Receiver/scraper chuyển dữ liệu thành metric có kiểu, timestamp và đơn vị.
3. Processor lọc metric không cần thiết, đổi tên/đơn vị nếu cần và thêm resource attributes.
4. Exporter gửi metric tới backend bằng giao thức được hỗ trợ.
5. Backend lưu time series; dashboard và alerting truy vấn dữ liệu.

~~~mermaid
flowchart TD
    subgraph HOST["Linux / Windows / VM node"]
        OS["OS counters: CPU, memory, swap, disk, network"]
        CG["cgroup / container runtime"]
        AG["Agent: receiver + processor"]
        OS --> AG
        CG --> AG
    end
    AG -->|TLS / authenticated telemetry| COL["Central collector"]
    COL --> PROC["Filter, enrich, batch"]
    PROC --> MET["Metrics backend"]
    MET --> DASH["Dashboard"]
    MET --> ALERT["Alert rules"]
~~~

### 9.1. Chọn công cụ

Một số lựa chọn phổ biến:

| Công cụ | Cách dùng | Phù hợp khi |
|---|---|---|
| OpenTelemetry Collector | Dùng hostmetrics receiver và exporter để thu thập/chuyển metric | Muốn chuẩn hóa telemetry và có thể gửi tới nhiều backend |
| Prometheus Node Exporter | Export metric host qua HTTP endpoint để Prometheus scrape | Hệ thống dùng Prometheus và muốn quan sát Linux host |
| AWS CloudWatch Agent | Thu thập metric/log trên EC2 và máy chủ hỗ trợ | Dùng Amazon CloudWatch làm nền tảng giám sát |
| Azure Monitor Agent | Thu thập dữ liệu guest và chuyển tới Azure Monitor theo data collection rule | Quản lý VM bằng Azure Monitor |
| Google Cloud Ops Agent | Thu thập metric/log trên VM và gửi tới Cloud Monitoring/Logging | Dùng Google Cloud Operations suite |
| Windows Performance Counters | Nguồn counter gốc cho agent hoặc collector trên Windows | Cần quan sát Windows host và process |

Chọn một agent chuẩn cho mỗi mục đích và tránh cài nhiều agent cùng thu thập cùng một metric nếu không có lý do. Thu thập trùng làm tăng CPU, memory, network và chi phí lưu trữ; đôi khi tạo metric có tên và định nghĩa khác nhau gây nhầm lẫn.

### 9.2. Ví dụ OpenTelemetry Collector hostmetrics

Cấu hình khái niệm dưới đây minh họa việc thu thập CPU, load, memory, paging, disk, filesystem, network và process metrics rồi gửi qua OTLP. Cần dùng bản phân phối Collector có receiver hostmetrics và exporter otlp tương ứng; endpoint, chứng thư và scraper được hỗ trợ phải khớp với phiên bản triển khai.

~~~yaml
receivers:
  hostmetrics:
    collection_interval: 30s
    scrapers:
      cpu:
      load:
      memory:
      paging:
      disk:
      filesystem:
      network:
      processes:

processors:
  batch:
    timeout: 10s
  resourcedetection:
    detectors: [system]
    timeout: 2s

exporters:
  otlp:
    endpoint: metrics-gateway.internal.example:4317
    tls:
      insecure: false

service:
  pipelines:
    metrics:
      receivers: [hostmetrics]
      processors: [resourcedetection, batch]
      exporters: [otlp]
~~~

Trong cấu hình này:

- collection_interval đặt chu kỳ đọc metric là 30 giây.
- scrapers chọn nhóm dữ liệu cần thu thập.
- resourcedetection bổ sung metadata hệ thống nếu detector và môi trường hỗ trợ.
- batch gom metric trước khi gửi để giảm overhead.
- otlp gửi dữ liệu tới collector/backend qua TLS.

Đây là mẫu nền tảng, không phải cấu hình hoàn chỉnh cho mọi hệ điều hành. Trên Windows, một số scraper hoặc trường có thể khác Linux. Trong môi trường cloud, có thể cần detector riêng để thêm cloud provider, region, instance ID và account/project. Hãy kiểm tra schema của phiên bản Collector được triển khai trước khi rollout.

### 9.3. Ví dụ scrape Node Exporter

Nếu dùng Prometheus Node Exporter, Prometheus có thể scrape endpoint của exporter:

~~~yaml
scrape_configs:
  - job_name: linux-hosts
    scrape_interval: 30s
    static_configs:
      - targets:
          - vm-app-01.internal.example:9100
          - vm-app-02.internal.example:9100
~~~

Cần bảo vệ port exporter bằng firewall, mạng quản trị hoặc xác thực qua proxy/service mesh phù hợp. Không mở endpoint metrics cho Internet; endpoint có thể tiết lộ hostname, mount point, kernel, interface và thông tin vận hành.

## 10. Cài đặt và cấu hình agent an toàn

Quy trình triển khai agent nên được quản lý như một thay đổi hạ tầng:

1. Xác định hệ điều hành, kiến trúc CPU, phiên bản agent và nguồn package đáng tin cậy.
2. Kiểm tra chữ ký package hoặc checksum theo quy trình nhà cung cấp.
3. Triển khai thử trên một VM đại diện trước.
4. Cấp quyền đọc các counter cần thiết bằng service account riêng.
5. Cấu hình endpoint, TLS, certificate và xác thực.
6. Chỉ bật scraper/metric thực sự cần.
7. Cấu hình nhãn resource và loại bỏ dữ liệu có cardinality quá cao.
8. Thiết lập retry, batch và buffer phù hợp.
9. Bật service auto-start và kiểm tra health.
10. Rollout theo nhóm máy, theo dõi overhead và chất lượng dữ liệu.

Agent thường cần quyền đọc một số nguồn hệ điều hành. Không cấp quyền root/Administrator rộng nếu công cụ hỗ trợ chạy với capability hoặc quyền hẹp hơn. Nếu agent cần quyền cao để đọc metric kernel, giới hạn binary, package source, quyền sửa cấu hình và người có thể restart service.

Bảo vệ kết nối agent:

- Dùng TLS và xác thực client khi backend hỗ trợ.
- Lưu certificate/key trong kho bảo vệ với quyền đọc tối thiểu.
- Không ghi token hoặc credential vào command line, log hoặc image.
- Giới hạn egress từ host tới endpoint collector.
- Theo dõi agent version, trạng thái và lần gửi metric cuối.
- Có quy trình thu hồi certificate khi host bị hủy hoặc bị xâm phạm.

### 10.1. Quản lý agent bằng image và bootstrap

Trong cloud, agent có thể được cài sẵn trong custom image hoặc cài khi VM bootstrap. Cài trong image giúp máy khởi động với agent đã có, nhưng cần quy trình cập nhật image khi agent có bản vá mới. Cài lúc bootstrap giúp linh hoạt phiên bản nhưng phụ thuộc package repository, mạng và startup script.

Dù chọn cách nào, không đóng gói credential riêng của từng máy vào image. Khi VM khởi động, hãy tạo danh tính riêng hoặc lấy credential ngắn hạn qua instance identity/managed identity.

## 11. Nhãn và metadata cho metric

Metric chỉ hữu ích khi người vận hành biết nó thuộc máy, workload và môi trường nào. Resource attributes/labels thường nên có:

- service.name hoặc workload name.
- deployment.environment như dev, staging, production.
- host.name hoặc instance ID ổn định.
- Cloud provider, account/project, region và zone.
- Machine/instance type hoặc node pool.
- Operating system và kiến trúc.
- Cluster, namespace, node, Pod hoặc container khi phù hợp.
- Owner hoặc team chịu trách nhiệm.

Ví dụ một metric CPU có thể được gắn các thuộc tính: service=orders-api, environment=production, region=asia-southeast1, instance_id=vm-example, role=application.

Tránh đưa các giá trị có cardinality cao vào nhãn của mọi metric, ví dụ request ID, user ID, session ID, full command line, container ID thay đổi liên tục hoặc tên file ngẫu nhiên. Mỗi tổ hợp nhãn tạo một time series; cardinality tăng nhanh sẽ làm tăng chi phí lưu trữ, truy vấn và bộ nhớ backend.

Nhãn nên mô tả tài nguyên tương đối ổn định. Dữ liệu chi tiết theo request hoặc sự kiện nên nằm trong log/trace, nơi có cơ chế lưu trữ và truy vấn phù hợp.

## 12. Chu kỳ thu thập, overhead và lưu trữ

Chu kỳ scrape ảnh hưởng độ chi tiết, độ trễ phát hiện và chi phí. Thu thập mỗi giây giúp quan sát biến động ngắn nhưng tạo nhiều mẫu hơn và tăng overhead. Thu thập mỗi phút giảm dữ liệu nhưng có thể bỏ qua spike ngắn.

| Chu kỳ tham khảo | Trường hợp sử dụng | Đánh đổi |
|---|---|---|
| 5–10 giây | Workload nhạy độ trễ, điều tra sự cố hoặc metric cần phản ứng nhanh | Nhiều mẫu và chi phí cao hơn |
| 15–30 giây | Monitoring vận hành thông thường | Cân bằng độ chi tiết và chi phí |
| 60 giây trở lên | Capacity trend và workload ít biến động | Dữ liệu thưa hơn, khó thấy spike ngắn |

Đây là khoảng tham khảo, không phải chuẩn bắt buộc. Hãy chọn theo mục tiêu cảnh báo, backend, số lượng host và ngân sách.

Overhead phụ thuộc số scraper, số interface/filesystem, số process, chu kỳ thu thập, xử lý và exporter. Đo CPU/memory của chính agent trong giai đoạn thử nghiệm. Nếu agent chiếm tài nguyên đáng kể, giảm metric không cần thiết, tăng chu kỳ hoặc chuyển xử lý sang collector tập trung.

Với backend time-series, số lượng mẫu tăng theo số host nhân với số metric mỗi host, số chu kỳ mỗi ngày và số ngày lưu. Nhãn làm tăng số time series, vì vậy cần tính cả cardinality. Thiết kế retention theo mục đích: metric chi tiết giữ trong thời gian ngắn hơn, dữ liệu downsample/aggregate giữ lâu hơn để phân tích xu hướng.

## 13. Xây dựng dashboard cho CPU, memory, swap, disk và network

Dashboard nên giúp trả lời câu hỏi vận hành, không chỉ hiển thị thật nhiều biểu đồ.

Một bố cục gợi ý:

| Khu vực | Biểu đồ | Câu hỏi cần trả lời |
|---|---|---|
| CPU | Utilization theo core, user/system/iowait/steal, load, throttling | Máy có bão hòa hoặc bị giới hạn CPU không? |
| Memory | Available, used, cache, working set, OOM | Có áp lực RAM hoặc tăng trưởng bất thường không? |
| Swap | Used, swap-in/out rate, page faults | Hệ thống có paging liên tục không? |
| Disk | Filesystem used %, inode %, IOPS, throughput, latency, queue | Volume có đầy hoặc I/O bị nghẽn không? |
| Network | RX/TX throughput, packet errors/drops, retransmission | Interface có lỗi hoặc lưu lượng bất thường không? |
| Agent health | Last scrape, last export, agent process, queue/drop | Dữ liệu có đang được gửi đầy đủ không? |

Nên có dashboard tổng quan theo environment/cluster/role và dashboard chi tiết theo host. Khi chọn host từ bảng tổng quan, người vận hành cần đi sâu được tới CPU, memory, disk, network và các sự kiện deployment liên quan.

Một dashboard tốt thể hiện đơn vị rõ ràng, khoảng thời gian, nguồn metric, định nghĩa phần trăm và trạng thái thiếu dữ liệu. Nếu agent ngừng gửi metric, biểu đồ có thể trông giống như tài nguyên bằng 0; cần phân biệt no data với giá trị thực bằng 0.

## 14. Thiết kế cảnh báo có ngữ cảnh

Cảnh báo nên phát hiện tình trạng kéo dài hoặc kết hợp nhiều dấu hiệu, tránh gửi thông báo cho mọi spike ngắn.

Ví dụ các điều kiện có thể cân nhắc:

- CPU utilization cao liên tục trong vài phút, đồng thời run queue hoặc request latency tăng.
- Memory available thấp kéo dài và có major page fault hoặc OOM event.
- Swap-in/swap-out liên tục cùng memory pressure.
- Filesystem hoặc inode usage gần hết, có xu hướng sẽ đầy trước chu kỳ vận hành tiếp theo.
- Disk latency/queue tăng trong khi I/O throughput không tăng tương ứng.
- Network errors/drops tăng hoặc retransmission vượt baseline.
- Agent không gửi metric trong một khoảng thời gian dài hơn chu kỳ dự kiến.

Không dùng một ngưỡng chung cho mọi workload. Database, web server và batch worker có mẫu sử dụng khác nhau. Cảnh báo filesystem nên xét dung lượng tuyệt đối, tỷ lệ phần trăm và tốc độ tăng. Một volume 100 GiB còn 10% có thể sắp đầy nhanh hơn volume 10 TiB còn 5% tùy tốc độ ghi.

### Ví dụ PromQL minh họa

Nếu backend tương thích Prometheus và metric đã được chuẩn hóa theo tên tương ứng, có thể viết truy vấn theo ý tưởng:

~~~promql
# CPU busy trung bình trên các core
100 * (1 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])))

# Tỷ lệ filesystem đã dùng
100 * (1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"}
         / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"})

# Network receive rate theo interface
rate(node_network_receive_bytes_total[5m])
~~~

Tên metric và label phụ thuộc exporter. Cần loại bỏ filesystem ảo hoặc mount không liên quan theo môi trường thực tế, đồng thời xử lý filesystem có size bằng 0 hoặc không có avail phù hợp. Truy vấn CPU trên là trung bình theo tập CPU được chọn; với hệ thống có nhiều core, nên có thêm dashboard theo từng core để phát hiện một core bão hòa.

### Tránh cảnh báo giả và cảnh báo trùng

- Dùng for hoặc thời gian duy trì để lọc spike ngắn.
- Gộp alert theo host, workload và nguyên nhân.
- Thêm owner, runbook URL và severity vào alert.
- Tạo silence có thời hạn cho maintenance window.
- Cảnh báo agent health độc lập với host resource metrics.
- Không dùng nhãn biến động cao khiến mỗi instance phát sinh alert riêng không cần thiết.

## 15. Quan sát trong môi trường cloud

Metric trong guest OS và metric do cloud provider cung cấp có thể bổ sung cho nhau.

| Lớp quan sát | Ví dụ | Giá trị |
|---|---|---|
| Guest OS agent | CPU, memory, swap, filesystem, process, interface | Thấy trạng thái mà hệ điều hành khách nhìn thấy |
| Hypervisor/cloud host | CPU credit, host contention hoặc metric instance theo dịch vụ | Bổ sung góc nhìn hạ tầng do provider quản lý |
| Block storage service | IOPS, throughput, queue/burst metrics | Đối chiếu hiệu năng volume ở tầng dịch vụ |
| Network service | NIC, load balancer, flow logs, packet/drop metrics | Phân tích đường truyền và giới hạn dịch vụ |
| Container platform | Pod, node, cgroup, throttling và network | Liên kết tài nguyên host với workload được lập lịch |

Guest agent không thể luôn quan sát được mọi thông tin ở hypervisor hoặc storage service. Ngược lại, cloud provider metric có thể không cho biết một process cụ thể đang dùng RAM bao nhiêu. Kết hợp hai nguồn giúp khoanh vùng nhanh hơn.

### 15.1. Máy ảo

Trên VM, agent đọc số liệu guest OS. Gắn instance ID, instance type, region/zone, account/project và environment để đối chiếu với cloud metric. Khi VM bị thay thế bởi autoscaling, dùng ID ổn định của tài nguyên và nhãn logical service để theo dõi cả nhóm máy.

### 15.2. Container và Kubernetes

Có thể chạy agent dạng DaemonSet để mỗi node có collector host metric. Metric container cần đọc từ cgroup hoặc kubelet/runtime API phù hợp. Cần phân biệt:

- Node capacity và node allocatable.
- Pod request/limit.
- Container usage và throttling.
- Filesystem của host và ephemeral storage của container.
- Network của node và network của Pod.

Không chạy một host agent riêng trong mỗi container chỉ để đọc cùng một metric node. Thiết kế một agent per node thường giảm trùng lặp; metric cấp container được lấy từ runtime hoặc kubelet theo kiến trúc.

### 15.3. Serverless

Serverless thường không cho phép cài host agent lên máy vật lý hoặc runtime do nhà cung cấp quản lý. Dùng metric và log tích hợp của dịch vụ như invocation, duration, concurrency, memory allocation/usage khi được cung cấp, throttling, error và timeout. Nếu cần metric ứng dụng chi tiết, instrument mã bằng OpenTelemetry SDK hoặc cơ chế telemetry được dịch vụ hỗ trợ.

## 16. Kiểm tra chất lượng dữ liệu và sức khỏe agent

Agent hoạt động không có nghĩa dữ liệu đã đầy đủ và chính xác. Cần giám sát chính agent:

- Service/process có đang chạy không.
- Phiên bản agent và thời điểm cập nhật.
- Thời điểm scrape gần nhất.
- Thời điểm export thành công gần nhất.
- Số metric gửi, số lỗi export và số điểm bị drop.
- Kích thước queue/buffer và thời gian retry.
- CPU/memory agent sử dụng.
- Trạng thái chứng thư và kết nối backend.

Một số kiểm tra đối chiếu:

1. So sánh free, vmstat, iostat, ip -s link với dashboard cùng thời điểm.
2. Kiểm tra đơn vị và nhãn của metric.
3. Xác minh timestamp và đồng bộ thời gian.
4. Kiểm tra counter reset sau reboot.
5. Xác minh mỗi host chỉ có một nguồn metric chính cho cùng loại dữ liệu.
6. Kiểm tra dashboard thể hiện no data khi agent dừng.
7. Đối chiếu metric guest với cloud provider metric khi có chênh lệch.

Không coi thiếu dữ liệu là tài nguyên bằng 0. Alerting cần có rule phát hiện target/agent mất dữ liệu riêng.

## 17. Xử lý sự cố thu thập metric

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Host không có metric | Agent chưa chạy, scrape target sai hoặc host không được đăng ký | Kiểm tra service, endpoint và target discovery |
| Metric bị trễ | Queue đầy, mạng chậm, retry hoặc backend ingest chậm | Xem export errors, queue, network và backend |
| Metric luôn bằng 0 | Sai quyền, sai scraper, sai label hoặc không hỗ trợ OS | So sánh với công cụ hệ điều hành và kiểm tra log agent |
| Metric trùng | Cài nhiều agent hoặc scrape cùng exporter nhiều lần | Kiểm tra pipeline và target discovery |
| Filesystem tăng cardinality | Mỗi container/mount tạo series mới liên tục | Lọc mount tạm, chuẩn hóa nhãn và retention |
| Agent tiêu thụ CPU cao | Quá nhiều scraper, chu kỳ quá ngắn hoặc process scan nặng | Tắt metric không cần, tăng interval và đo lại |
| Export thất bại | TLS, certificate, DNS, firewall hoặc credential | Kiểm tra endpoint, trust chain và quyền |
| Chênh lệch host/cloud metric | Hai nguồn đo ở lớp khác nhau hoặc khác chu kỳ | Xác định định nghĩa, thời điểm và điểm đo |

Trên Linux có thể kiểm tra agent bằng systemd:

~~~bash
systemctl status otelcol
journalctl -u otelcol --since "15 minutes ago"
~~~

Tên service thay đổi theo cách cài đặt và bản phân phối. Trên Windows, kiểm tra Services, Event Viewer và log của agent. Không đưa token hoặc private key vào output khi chia sẻ log để hỗ trợ sự cố.

## 18. Bảo mật dữ liệu telemetry

Metric hạ tầng thường ít nhạy cảm hơn application payload nhưng vẫn có thể tiết lộ thông tin nội bộ: hostname, cấu trúc mạng, mount point, loại instance, mức tải, thời gian hoạt động và dấu hiệu của hệ thống quan trọng.

Các biện pháp bảo vệ:

- Chỉ cho phép agent gửi tới collector/backend được phê duyệt.
- Dùng TLS và xác thực agent.
- Giới hạn quyền truy cập dashboard, query và API metric.
- Tách tenant/project hoặc workspace giữa môi trường khi cần.
- Giới hạn nhãn có thể chứa username, command line hoặc thông tin nhạy cảm.
- Áp dụng retention và xóa dữ liệu theo chính sách.
- Audit thao tác thay đổi pipeline, alert rule và quyền truy cập.
- Không mở exporter endpoint công khai.

Agent có quyền đọc hệ thống là một thành phần đặc quyền. Hãy cập nhật agent, xác minh nguồn package, giới hạn quyền ghi cấu hình và giám sát việc thay đổi binary/service.

## 19. Quy trình triển khai agent theo từng giai đoạn

Một rollout an toàn có thể thực hiện như sau:

1. **Khảo sát:** lập danh sách OS, phiên bản, kiến trúc, nhóm VM/node và backend.
2. **Thiết kế metric:** chọn CPU, memory, swap, disk, network và metadata thực sự cần.
3. **Thử nghiệm:** triển khai trên một Linux VM, một Windows VM và một node/container representative nếu có.
4. **Đối chiếu:** so sánh metric agent với công cụ hệ điều hành và cloud provider.
5. **Đánh giá overhead:** đo CPU, memory, disk và network do agent tạo ra.
6. **Bảo mật:** xác minh TLS, credential, firewall và quyền agent.
7. **Mở rộng:** rollout theo environment/role/zone, có thể dừng ở từng nhóm.
8. **Quan sát:** kiểm tra coverage, missing data, duplicate series và export error.
9. **Chuẩn hóa:** cập nhật dashboard, alert rule, owner và runbook.
10. **Vận hành:** quản lý phiên bản agent, cập nhật định kỳ và gỡ agent khi host bị hủy.

Dùng automation/configuration management để đảm bảo cấu hình nhất quán. Với autoscaling group hoặc node pool, agent nên được cài qua image, bootstrap hoặc daemonset để máy mới tự tham gia monitoring. Cần có inventory hoặc service discovery để target mới được phát hiện và target đã hủy được loại bỏ.

## 20. Lỗi thường gặp và cách tránh

**Chỉ theo dõi CPU:** bỏ sót memory pressure, disk latency, inode exhaustion và packet drops. Dùng bộ metric nền tảng cho cả năm nhóm tài nguyên.

**Nhìn free memory để kết luận thiếu RAM:** Linux dùng RAM cho cache có thể thu hồi. Theo dõi available, paging, pressure và OOM cùng lúc.

**Cảnh báo chỉ dựa vào swap usage:** swap đã dùng có thể là trạng thái lịch sử. Quan sát swap-in/out rate và memory pressure.

**Chỉ xem filesystem usage:** volume còn chỗ vẫn có thể nghẽn IOPS hoặc latency. Theo dõi capacity và block device performance riêng.

**Nhìn throughput network mà bỏ qua errors/drops:** lưu lượng thấp không chứng minh interface khỏe. Thu thập packet error, drop và retransmission.

**Cộng metric từ nhiều lớp:** cùng một I/O hoặc packet có thể được đếm ở guest, container và cloud service. Xác định điểm đo trước khi tổng hợp.

**Cài nhiều agent trùng nhau:** làm tăng overhead và tạo metric trùng. Chuẩn hóa agent chuẩn cho từng nhóm host.

**Đặt scrape interval quá ngắn:** làm tăng tải agent, mạng và backend. Chọn interval theo mục tiêu phát hiện và ngân sách.

**Gắn nhãn có cardinality cao:** làm tăng số time series và chi phí. Chỉ dùng nhãn ổn định, có giá trị vận hành.

**Không giám sát chính agent:** host có thể mất metric mà dashboard không báo. Tạo alert riêng cho agent health và missing data.

**Mở endpoint metrics ra Internet:** lộ thông tin hệ thống và bề mặt tấn công. Giới hạn mạng, dùng TLS và xác thực.

## 21. Checklist thu thập metric hạ tầng

- [ ] Agent phù hợp với OS, kiến trúc và môi trường cloud.
- [ ] Có metric CPU tổng thể và theo core khi cần, gồm user/system/iowait/steal.
- [ ] Có memory available, usage, cache/working set và OOM signal.
- [ ] Có swap capacity, swap usage và paging rate.
- [ ] Có filesystem capacity, inode và block device performance.
- [ ] Có network throughput, packets, errors, drops và retransmission khi hỗ trợ.
- [ ] Container metric được đọc từ cgroup/runtime và tách khỏi host metric.
- [ ] Metric có timestamp, đơn vị và resource labels nhất quán.
- [ ] Scrape interval, retention và cardinality phù hợp ngân sách.
- [ ] Agent dùng quyền tối thiểu, TLS và credential được bảo vệ.
- [ ] Agent health, export error và missing data được giám sát.
- [ ] Đã đối chiếu metric với công cụ hệ điều hành và cloud provider.
- [ ] Đã đo overhead trước khi rollout rộng.
- [ ] Có dashboard, alert rule, owner và runbook cho từng nhóm tài nguyên.
- [ ] Có quy trình cập nhật, rollback và gỡ agent.

Thu thập CPU, memory, swap, disk và network bằng agent tạo nền tảng quan sát sức khỏe của máy ảo và node compute. Hãy chọn metric theo câu hỏi vận hành, hiểu rõ counter/gauge/rate, gắn metadata ổn định và kiểm tra số liệu với hệ điều hành. Một pipeline agent an toàn cần quyền tối thiểu, truyền dữ liệu được bảo vệ, theo dõi sức khỏe chính agent và được triển khai có kiểm soát. Khi kết hợp metric guest với metric dịch vụ cloud, đội ngũ có thể phát hiện nghẽn tài nguyên, lập kế hoạch sizing và xử lý sự cố nhanh hơn.
