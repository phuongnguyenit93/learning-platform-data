# Điều tra sự cố compute từ log, metric và dấu hiệu hệ điều hành

Khi một workload compute chậm, không phản hồi hoặc dừng đột ngột, nguyên nhân có thể nằm ở ứng dụng, hệ điều hành, container runtime, máy ảo, hạ tầng cloud hoặc dependency bên ngoài. Một biểu đồ CPU cao chỉ cho biết có hoạt động xử lý nhiều; nó chưa chứng minh CPU là nguyên nhân gốc. Một log báo timeout cũng chưa nói rõ request bị chậm ở ứng dụng, mạng, storage hay dịch vụ đích.

Điều tra sự cố compute cần kết hợp ba nhóm bằng chứng: log cho biết sự kiện và trình tự xảy ra; metric cho thấy xu hướng và mức độ bất thường; dấu hiệu hệ điều hành cho biết tiến trình, bộ nhớ, I/O, scheduler, network stack và kernel đang hoạt động ra sao. Khi liên kết các nguồn theo cùng khoảng thời gian, instance, process, container, request và deployment version, đội vận hành có thể chuyển từ phỏng đoán sang giả thuyết có thể kiểm chứng.

Bài học này hướng dẫn quy trình điều tra có cấu trúc cho VM, container, Kubernetes và workload serverless. Nội dung đi từ xác định ảnh hưởng, dựng timeline, thu thập bằng chứng, đọc metric, phân tích dấu hiệu OS, kiểm tra thay đổi hạ tầng đến xác minh khắc phục và viết báo cáo. Sau bài học, bạn có thể:

- Phân loại sự cố compute theo CPU, memory, disk/I/O, network, process, kernel và capacity.
- Kết hợp log, metric, event và OS telemetry để dựng timeline có tương quan.
- Dùng các lệnh quan sát Linux và Windows để xác định tiến trình hoặc tài nguyên bất thường.
- Phân biệt CPU saturation, throttling, memory pressure, OOM, I/O wait và network failure.
- Điều tra sự cố trong VM, container, Kubernetes và serverless theo đúng lớp sở hữu.
- Xây dựng giả thuyết, kiểm chứng bằng bằng chứng và chọn biện pháp giảm thiểu an toàn.
- Bảo toàn dữ liệu điều tra, tránh hành động làm mất bằng chứng hoặc mở rộng ảnh hưởng.
- Xác minh service recovery, theo dõi tái phát và lập báo cáo nguyên nhân gốc.

## 1. Mục tiêu và nguyên tắc điều tra

Mục tiêu đầu tiên của incident response là khôi phục dịch vụ trong giới hạn rủi ro chấp nhận được. Tìm nguyên nhân gốc là mục tiêu tiếp theo, nhưng không nên trì hoãn biện pháp giảm thiểu cần thiết khi người dùng đang bị ảnh hưởng. Đồng thời, một hành động như reboot, xóa Pod, rotate log hoặc scale-in có thể làm mất bằng chứng quan trọng.

### Phân biệt triệu chứng, nguyên nhân trực tiếp và nguyên nhân gốc

- **Triệu chứng:** API trả 503, VM không SSH được, container restart liên tục hoặc job vượt deadline.
- **Nguyên nhân trực tiếp:** process bị OOM kill, filesystem hết dung lượng, CPU bị throttling hoặc connection pool cạn.
- **Nguyên nhân gốc:** memory leak, request/limit cấu hình sai, log tăng không giới hạn, rollout thay đổi concurrency hoặc autoscaler thiếu capacity.
- **Yếu tố góp phần:** thiếu alert, quota thấp, dependency chậm, node placement không cân bằng hoặc runbook không cập nhật.

Một sự cố có thể có nhiều nguyên nhân tương tác. Ví dụ, database chậm làm request giữ connection lâu; queue trong ứng dụng tăng; memory tăng; cuối cùng process bị OOM. Chỉ xử lý memory mà không xem dependency có thể khiến sự cố tái diễn.

### Nguyên tắc làm việc

1. Xác định ảnh hưởng và phạm vi trước khi thay đổi hệ thống.
2. Ghi nhận thời điểm, timezone, resource ID và phiên bản workload.
3. Thu thập bằng chứng từ nhiều lớp, ưu tiên nguồn có timestamp.
4. So sánh với baseline và workload khỏe mạnh tương đương.
5. Viết giả thuyết rõ ràng, nêu bằng chứng ủng hộ và bằng chứng phản bác.
6. Thực hiện một thay đổi giảm thiểu có thể kiểm soát rồi đo kết quả.
7. Kiểm tra SLO và các dependency sau khi phục hồi.
8. Ghi lại quyết định, tác động, owner và bước theo dõi.

~~~mermaid
flowchart TD
    A["Phát hiện cảnh báo / báo cáo sự cố"] --> B["Xác định ảnh hưởng và phạm vi"]
    B --> C["Ghi timeline, resource ID, deployment"]
    C --> D["Thu thập log + metric + OS signals"]
    D --> E["Đưa ra giả thuyết"]
    E --> F{"Có bằng chứng kiểm chứng?"}
    F -- "Chưa" --> D
    F -- "Có" --> G["Chọn mitigation có kiểm soát"]
    G --> H["Đo lại SLO và health"]
    H --> I{"Đã ổn định?"}
    I -- "Chưa" --> D
    I -- "Rồi" --> J["Theo dõi, RCA và action items"]
~~~

## 2. Xác định mức độ ảnh hưởng và phạm vi

Trước khi mở terminal, cần biết sự cố tác động tới ai và tài nguyên nào. Điều này giúp tránh điều tra một node đơn lẻ trong khi vấn đề thực tế là toàn region hoặc một dependency dùng chung.

### Các câu hỏi mở đầu

- Dịch vụ nào bị ảnh hưởng? API, worker, batch job, database proxy hay control plane?
- Bắt đầu lúc nào? Có mốc deploy, config change, scale event hoặc maintenance gần đó không?
- Ảnh hưởng toàn bộ hay chỉ một phần tenant, region, zone, node pool hoặc loại instance?
- Request lỗi, timeout, latency tăng hay throughput giảm?
- Pod/VM/process nào bị ảnh hưởng? Có pattern theo host, image, instance family hoặc zone không?
- Có dữ liệu mất, job trùng, request retry hoặc backlog tăng không?
- Sự cố còn tiếp diễn hay đã tự hồi phục?

### Xác định phạm vi theo lớp

| Lớp | Đối tượng cần kiểm tra | Dấu hiệu phạm vi |
|---|---|---|
| Ứng dụng | Endpoint, worker, process, thread pool | Một route hoặc một phiên bản lỗi |
| Container | Container ID, Pod, restart count | Pod trên một node hoặc image cụ thể |
| Node/VM | Instance ID, hostname, kernel | Nhiều workload trên cùng host |
| Cluster | Node pool, scheduler, control plane | Pod Pending hoặc nhiều node NotReady |
| Network | Subnet, route, firewall, DNS, endpoint | Một zone hoặc destination bị lỗi |
| Storage | Volume, filesystem, object store | Workload cùng mount hoặc cùng storage backend |
| Region/provider | Region, zone, quota, managed service | Nhiều ứng dụng hoặc account cùng bị ảnh hưởng |

### Đánh giá severity

Severity nên dựa trên tác động thực tế, không chỉ số lượng alert:

- Số người dùng hoặc tenant bị ảnh hưởng.
- Tỷ lệ request lỗi và mức vi phạm SLO.
- Dữ liệu có nguy cơ mất hoặc sai lệch không.
- Có ảnh hưởng bảo mật hoặc truy cập trái phép không.
- Có workaround hoặc vùng phục vụ thay thế không.
- Tốc độ tăng backlog và thời gian có thể duy trì trước khi cạn capacity.

Nếu có dấu hiệu xâm nhập, rò rỉ dữ liệu hoặc thay đổi quyền trái phép, cần kích hoạt quy trình security incident phù hợp song song với điều tra compute.

## 3. Dựng timeline và đồng bộ thời gian

Log và metric chỉ có thể liên kết đáng tin khi thời gian được chuẩn hóa. Một máy lệch đồng hồ vài phút có thể làm thứ tự sự kiện bị đảo, đặc biệt khi request đi qua nhiều dịch vụ.

### Ghi nhận mốc thời gian

Tối thiểu cần ghi:

- Thời điểm alert đầu tiên.
- Thời điểm người dùng bắt đầu báo lỗi.
- Request ID hoặc trace ID mẫu.
- Thời điểm deploy, restart, scale, patch hoặc thay đổi cấu hình.
- Thời điểm metric bắt đầu lệch baseline.
- Thời điểm mitigation và thời điểm dịch vụ phục hồi.

Ưu tiên lưu timestamp UTC và giữ timezone gốc nếu nguồn log không chuẩn hóa. Ghi rõ độ phân giải thời gian của từng nguồn: log theo mili giây, metric theo chu kỳ 1 phút, event theo thời gian ghi nhận hoặc thời gian xử lý.

### Kiểm tra clock trên Linux

~~~bash
date -u
timedatectl status
chronyc tracking
~~~

Nếu hệ thống dùng chrony, chronyc tracking có thể hiển thị trạng thái đồng bộ và offset. Tên dịch vụ đồng bộ thời gian khác nhau theo distro. Không tự thay đổi NTP configuration trong lúc điều tra nếu chưa có quyền và kế hoạch.

### Kiểm tra clock trên Windows

~~~powershell
Get-Date -Format 'yyyy-MM-ddTHH:mm:ss.fffK'
w32tm /query /status
~~~

Get-Date -Format o hiển thị thời gian local cùng UTC offset theo định dạng ISO 8601; ghi rõ timezone khi đưa mốc này vào timeline chung.

### Correlation ID

Request ID, trace ID, job ID, Pod UID, container ID và instance ID giúp liên kết log từ nhiều thành phần. Không dùng chỉ tên service chung nếu có nhiều replica. Với workload async, giữ correlation ID qua queue và worker để truy vết từ request ban đầu tới job cuối.

## 4. Thu thập bằng chứng trước khi thay đổi

Một số hành động khắc phục có thể xóa dấu vết: reboot làm mất process state và kernel ring buffer; xóa Pod làm mất filesystem tạm; rotate log có thể làm mất phần log chưa được ship; scale-in có thể loại node đang chứa bằng chứng.

### Bộ thông tin tối thiểu

- Incident ID, người điều phối và thời gian bắt đầu.
- Account/project/subscription, region, zone và resource ID.
- Hostname, OS version, kernel version, instance type.
- Application version, image digest, config version.
- Process ID, container ID, Pod UID hoặc function invocation ID.
- Log liên quan và khoảng thời gian truy vấn.
- Metric raw hoặc snapshot dashboard.
- Event của cloud provider, scheduler và hệ điều hành.
- Lệnh đã chạy, thời điểm chạy và output liên quan.
- Hành động thay đổi đã thực hiện và người phê duyệt.

### Bảo toàn dữ liệu

1. Export log và event theo khoảng thời gian có liên quan.
2. Ghi lại query, filter và nguồn lấy dữ liệu.
3. Chụp snapshot metric hoặc lưu truy vấn có thể tái lập.
4. Lưu output lệnh cùng hostname và timestamp.
5. Nếu cần memory dump hoặc packet capture, thực hiện theo quy trình bảo mật và quyền riêng tư.
6. Bảo vệ bằng chứng bằng quyền truy cập hạn chế và retention phù hợp.
7. Không đưa secret, token hoặc dữ liệu cá nhân vào báo cáo sự cố.

### Lệnh quan sát an toàn và lệnh có rủi ro

Các lệnh đọc trạng thái như top, free, df, journalctl, kubectl describe hoặc Get-WinEvent thường phù hợp cho bước đầu. Các lệnh kill process, reboot, truncate log, xóa file, flush firewall hoặc thay đổi route có thể làm gián đoạn dịch vụ và mất bằng chứng. Chỉ chạy hành động thay đổi khi có đánh giá tác động, người chịu trách nhiệm và phương án rollback.

## 5. Nguồn log cần thu thập

Không có một nguồn log duy nhất phản ánh toàn bộ sự cố compute. Cần kết hợp log ứng dụng, OS, runtime, orchestration và cloud control plane.

| Nguồn | Nội dung hữu ích | Câu hỏi điều tra |
|---|---|---|
| Application log | Error, timeout, exception, request ID | Code path nào lỗi? |
| System log | Service start/stop, daemon, driver, filesystem | OS hoặc service có thay đổi không? |
| Kernel log | OOM, device reset, filesystem, network driver | Kernel đã ghi nhận sự kiện gì? |
| Container runtime | Pull image, create/start/stop, runtime error | Container có khởi động hoặc bị kill không? |
| Kubernetes events | Scheduling, probe, eviction, volume mount | Pod bị ảnh hưởng vì lý do nào? |
| Cloud activity/audit | Create/update/stop, IAM, network, quota | Có thay đổi control plane nào? |
| Load balancer/API gateway | 4xx/5xx, target health, backend latency | Request có tới được backend không? |
| Network flow/firewall | Accept/deny, bytes, connection | Luồng nào bị chặn hoặc bất thường? |
| Storage service | Latency, throttling, capacity, error | Storage có bị nghẽn không? |
| Scheduler/job log | Queue, allocation, exit code, retry | Job chờ hay thất bại ở bước nào? |

### Log Linux

Các lệnh phổ biến:

~~~bash
journalctl -u my-service --since "2026-11-22 10:00:00 UTC" --until "2026-11-22 10:30:00 UTC"
journalctl -p warning..alert --since "1 hour ago"
journalctl -k --since "1 hour ago"
~~~

Trên hệ thống dùng rsyslog hoặc syslog-ng, có thể cần kiểm tra các file trong /var/log. Tên file phụ thuộc distro và cấu hình. Không giả định mọi Linux đều lưu cùng đường dẫn.

### Log Windows

~~~powershell
Get-WinEvent -FilterHashtable @{
  LogName = 'System'
  StartTime = (Get-Date).AddHours(-2)
} | Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, Message
~~~

Application, System và các log channel của service/driver có thể cung cấp bằng chứng khác nhau. Event ID cần được diễn giải theo provider và phiên bản Windows; không chỉ dựa vào số ID.

### Structured log

Log có cấu trúc nên chứa timestamp, severity, service, version, environment, instance/pod identity, request ID, operation, duration và error class. Dùng field riêng để lọc thay vì parse chuỗi message không nhất quán.

Không log password, access token, private key, session cookie hoặc payload nhạy cảm. Khi cần correlation, dùng identifier đã được phê duyệt và redaction.

## 6. Đọc metric: từ triệu chứng tới giả thuyết

Metric cho biết sự thay đổi theo thời gian. Cần so sánh cửa sổ sự cố với baseline trước đó, cùng khung giờ hoặc workload tương đương. Một mức CPU 80% có thể bình thường cho batch worker nhưng bất thường cho API vốn thường ở 20%.

### Golden signals

Với service request-driven, bốn nhóm tín hiệu thường dùng:

- **Latency:** thời gian xử lý request.
- **Traffic:** số request hoặc lượng công việc.
- **Errors:** tỷ lệ lỗi, timeout, retry và status code.
- **Saturation:** mức độ tài nguyên hoặc queue bị sử dụng tới giới hạn.

Với compute host, bổ sung CPU, memory, disk, network, process, file descriptor và kernel event.

### Metric cần so sánh

| Nhóm | Metric | Cách diễn giải |
|---|---|---|
| CPU | Utilization, load average, run queue, throttling, steal | CPU bận, chờ CPU hoặc bị hypervisor lấy thời gian |
| Memory | Used/available, working set, page fault, swap, OOM | Áp lực RAM, reclaim hoặc thiếu memory |
| Disk | Read/write latency, IOPS, throughput, queue depth, utilization | Storage chậm hoặc đạt giới hạn |
| Filesystem | Free bytes, inode usage, growth rate | Hết dung lượng hoặc inode |
| Network | Throughput, packet loss, retransmit, connection count | Nghẽn, mất gói hoặc cạn connection |
| Process | CPU, RSS, thread count, open files, restart | Process cụ thể bất thường |
| Container | CPU/memory usage, throttling, OOM, restart | Limit hoặc cgroup pressure |
| Platform | Node health, quota, capacity, provider event | Vấn đề hạ tầng hoặc giới hạn dịch vụ |
| Application | Queue age, pool usage, p95/p99, error rate | Bottleneck logic hoặc dependency |

### Rate, average và percentile

Average có thể che khuất request chậm. Hãy dùng p50/p95/p99 và histogram nếu cần đánh giá latency. Với counter như network bytes hoặc CPU time, thường cần xem rate/delta theo thời gian thay vì giá trị tích lũy.

Khi so sánh metric:

- Giữ cùng đơn vị và cùng aggregation window.
- Xác minh metric là host-level hay container-level.
- Kiểm tra sampling interval và missing data.
- Phân biệt peak tức thời với tình trạng kéo dài.
- Chú ý cardinality và label filters để không vô tình gộp nhiều instance.

## 7. Điều tra CPU: saturation, throttling và steal

CPU cao có nhiều nguyên nhân: traffic tăng, vòng lặp vô hạn, GC, retry storm, thread contention, batch chạy đồng thời hoặc workload khác tranh chấp CPU.

### Dấu hiệu trên Linux

~~~bash
uptime
top -H
ps -eo pid,ppid,comm,%cpu,%mem,stat,etime --sort=-%cpu | head -20
mpstat -P ALL 1 5
pidstat -u 1 5
vmstat 1 5
~~~

Diễn giải:

- Load average cao hơn số CPU khả dụng trong thời gian dài có thể cho thấy run queue hoặc task chờ I/O; load average không chỉ là CPU utilization.
- top -H hiển thị thread để tìm một thread chiếm CPU.
- mpstat giúp thấy core nào bận hoặc mất cân bằng.
- pidstat liên kết CPU với PID.
- vmstat hiển thị runnable process, blocked process và các trạng thái CPU.

Trong output CPU của Linux, các cột thường có user, system, idle, iowait, irq, softirq và steal. Tỷ lệ steal đáng kể trên VM có thể cho thấy hypervisor không cấp đủ CPU time như guest mong muốn; cần đối chiếu metric của nền tảng và loại instance.

### CPU throttling trong container

Container có CPU limit có thể bị throttling dù node còn CPU rảnh. Kiểm tra cgroup metrics hoặc container monitoring:

- CPU usage.
- CPU quota/period.
- Throttled periods.
- Throttled time.
- CPU request so với limit.

Nếu throttling tăng cùng p99 latency, có thể cần xem lại CPU limit, request, concurrency hoặc code path. Tăng replica đôi khi chỉ che triệu chứng và làm tăng chi phí.

### Dấu hiệu trên Windows

~~~powershell
Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 5
Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 Name, Id, CPU, WorkingSet64
Get-Counter '\System\Processor Queue Length' -SampleInterval 2 -MaxSamples 5
~~~

Tên counter có thể được bản địa hóa hoặc khác theo phiên bản. Dùng Performance Monitor để xác nhận counter khả dụng.

### Giả thuyết CPU thường gặp

| Dấu hiệu | Giả thuyết | Bằng chứng cần tìm |
|---|---|---|
| CPU và traffic cùng tăng | Tải hợp lệ tăng | Request rate, queue, số replica |
| CPU cao, traffic ổn định | Regression hoặc loop | Profile, deployment diff, hot stack |
| CPU cao và GC tăng | Allocation pressure | GC pause, allocation rate, heap |
| CPU host thấp nhưng container latency cao | Throttling hoặc lock contention | cgroup throttling, thread dump |
| Steal tăng trên một số VM | Host contention | Cloud metrics, instance placement, provider event |
| Một core 100%, core khác nhàn | Single-thread bottleneck | Thread profile, lock, serial section |

## 8. Điều tra memory: pressure, swap và OOM

Memory pressure có thể dẫn tới reclaim, swap, latency tăng, process bị OOM kill hoặc container restart. Phải phân biệt memory của host với memory của process/container.

### Dấu hiệu Linux

~~~bash
free -h
cat /proc/meminfo
vmstat 1 5
ps -eo pid,comm,rss,vsz,%mem --sort=-rss | head -20
journalctl -k --since "2 hours ago" | grep -i -E 'oom|out of memory|killed process'
~~~

Một số chỉ số cần chú ý:

- MemAvailable thường hữu ích hơn chỉ nhìn MemFree vì kernel dùng RAM cho cache có thể thu hồi.
- RSS ước lượng phần memory resident của process; không phải tổng memory riêng tuyệt đối do shared pages.
- Swap-in/swap-out tăng kéo dài có thể làm latency xấu.
- Major page fault có thể khiến process phải chờ đọc page từ storage.
- OOM log có thể cho biết process bị kill, cgroup hoặc memory constraint.

### OOM host và OOM container

Host OOM xảy ra khi kernel không thể đáp ứng memory allocation trên máy. Container OOM có thể do cgroup memory limit bị vượt dù host còn RAM. Trong Kubernetes, container bị OOMKilled thường có last termination reason tương ứng và Pod có thể restart.

Kiểm tra:

- Host memory pressure và kernel OOM messages.
- Container working set, RSS và memory limit.
- Pod status, lastState, restart count và events.
- Memory request/limit, QoS class và eviction events.
- Heap/GC, cache, buffer và memory leak trong ứng dụng.

Không tăng limit ngay nếu node không có allocatable memory. Việc tăng limit có thể khiến nhiều Pod cùng node tranh chấp và gây host-level OOM.

### Dấu hiệu Windows

~~~powershell
Get-Counter '\Memory\Available MBytes' -SampleInterval 2 -MaxSamples 5
Get-Counter '\Memory\Pages/sec' -SampleInterval 2 -MaxSamples 5
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 Name, Id, WorkingSet64, PrivateMemorySize64
~~~

Pages/sec có thể phản ánh paging activity nhưng không tự chứng minh thiếu RAM; cần xem cùng Available MBytes, hard faults, disk activity và ứng dụng.

### Điều tra memory leak

So sánh memory theo thời gian trong khi tải tương đương. Nếu RSS/working set tăng liên tục qua nhiều chu kỳ và không giảm sau khi workload kết thúc, có thể có leak hoặc cache không giới hạn. Dùng heap profile hoặc dump theo quy trình, cân nhắc dữ liệu nhạy cảm và chi phí pause.

## 9. Điều tra disk, filesystem và I/O

Storage chậm hoặc hết dung lượng có thể làm process treo, database lỗi, container không ghi được log hoặc node trở thành NotReady. Phải kiểm tra cả capacity lẫn latency.

### Linux

~~~bash
df -hT
df -i
lsblk -f
findmnt
iostat -xz 1 5
pidstat -d 1 5
~~~

Ý nghĩa:

- df -hT: dung lượng và filesystem type.
- df -i: inode đã dùng.
- lsblk/findmnt: thiết bị và mount point.
- iostat -xz: utilization, queue và latency thiết bị theo khả năng hệ thống.
- pidstat -d: process có I/O đọc/ghi đáng kể.

Nếu df báo đầy nhưng du không thấy file lớn, có thể file đã bị xóa khỏi directory nhưng process vẫn giữ file descriptor mở. Có thể dùng lsof +L1 để tìm file đã unlink còn được mở; chỉ đóng process hoặc restart theo kế hoạch vì có thể làm gián đoạn dịch vụ.

~~~bash
lsof +L1
du -xhd1 /var 2>/dev/null | sort -h
~~~

### Windows

~~~powershell
Get-Volume | Select-Object DriveLetter, FileSystem, Size, SizeRemaining
Get-PhysicalDisk | Select-Object FriendlyName, HealthStatus, OperationalStatus
Get-Counter '\PhysicalDisk(_Total)\Avg. Disk sec/Read' -SampleInterval 2 -MaxSamples 5
Get-Counter '\PhysicalDisk(_Total)\Avg. Disk sec/Write' -SampleInterval 2 -MaxSamples 5
~~~

### Phân biệt capacity và performance

- Free space thấp nhưng latency bình thường: vấn đề capacity có thể sắp xảy ra.
- Free space còn nhưng write latency tăng: có thể storage backend, queue hoặc burst credit bị giới hạn.
- IOPS cao và latency tăng: workload có thể vượt khả năng provisioned.
- Inode đầy nhưng byte còn: tạo file mới có thể thất bại.
- Filesystem read-only: xem kernel log, device error và mount state.

Không xóa file log hoặc dữ liệu tùy tiện để giải phóng dung lượng. Xác định file owner, retention và khả năng khôi phục trước khi dọn.

## 10. Điều tra network và connection

Network issue có thể biểu hiện như request timeout, DNS failure, connection reset, retransmission, packet loss hoặc throughput giảm. Một workload có CPU thấp và memory bình thường vẫn có thể không phản hồi vì đang chờ network.

### Linux

~~~bash
ip -s link
ss -s
ss -tanp
ip route
resolvectl status
sar -n DEV,TCP,ETCP 1 5
~~~

Các dấu hiệu:

- RX/TX error hoặc drop tăng trên interface.
- TCP retransmission và reset tăng.
- Nhiều socket ở SYN-SENT, TIME-WAIT hoặc CLOSE-WAIT bất thường.
- Connection count chạm giới hạn file descriptor hoặc connection pool.
- DNS resolver timeout hoặc trả địa chỉ không mong muốn.
- Route hoặc MTU không phù hợp sau thay đổi mạng.

### Windows

~~~powershell
Get-NetAdapterStatistics
Get-NetTCPConnection | Group-Object State | Select-Object Name, Count
Get-DnsClientServerAddress
Test-NetConnection example.internal -Port 443
~~~

Test-NetConnection là phép kiểm tra từ host tại thời điểm chạy; nó không chứng minh mọi client hoặc mọi đường mạng đều hoạt động.

### Kiểm tra theo lớp

1. DNS resolve đúng địa chỉ không?
2. Route và subnet có đường tới destination không?
3. Security group, firewall, NACL hoặc host firewall có chặn không?
4. TCP handshake có thành công không?
5. TLS handshake và certificate có hợp lệ không?
6. Backend có accept connection và còn capacity không?
7. Ứng dụng có pool/worker đủ để xử lý không?

Khi cần packet capture, giới hạn interface, host, port và thời gian. Capture có thể chứa payload hoặc thông tin nhạy cảm; cần quyền, mã hóa và retention phù hợp.

## 11. Process, thread, file descriptor và kernel signals

Một process có thể còn sống nhưng không tiến triển vì deadlock, blocked I/O, thread pool cạn hoặc file descriptor hết. Kiểm tra process state giúp phân biệt CPU busy với process đang chờ.

### Process state trên Linux

~~~bash
ps -eo pid,ppid,stat,wchan:24,etime,comm --sort=stat | head -40
ps -L -p <PID> -o pid,tid,stat,pcpu,comm
cat /proc/<PID>/status
ls /proc/<PID>/fd | wc -l
ulimit -n
~~~

Các state thường gặp:

- R: running hoặc runnable.
- S: interruptible sleep.
- D: uninterruptible sleep, thường chờ I/O hoặc kernel operation.
- Z: zombie, process đã kết thúc nhưng chưa được parent reap.
- T: stopped hoặc traced.

Nhiều process ở D state cùng một mount hoặc volume có thể chỉ ra I/O/kernel wait. Nhiều file descriptor gần giới hạn có thể gây lỗi mở socket/file. Thread dump của runtime có thể cho thấy lock contention, deadlock hoặc pool starvation.

### Kernel và driver

Kernel log có thể ghi nhận:

- OOM killer.
- Disk I/O error hoặc filesystem remount read-only.
- NIC reset, link down, queue timeout.
- GPU/accelerator driver reset hoặc device lost.
- Kernel panic, soft lockup, hung task.
- cgroup memory/CPU pressure.

Không nên kết luận từ một dòng log đơn lẻ. Liên kết timestamp với metric và workload version; xem sự kiện có lặp lại và có ảnh hưởng đúng resource hay không.

### Windows process và service

~~~powershell
Get-Process | Sort-Object CPU -Descending | Select-Object -First 20 Name, Id, CPU, WorkingSet64
Get-Service | Where-Object Status -ne 'Running'
Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).AddHours(-1)}
~~~

Kiểm tra service recovery, Windows Service Control Manager events, driver events và application-specific event channels. Một service stopped có thể là hệ quả của crash hoặc dependency fail, không nhất thiết là nguyên nhân gốc.

## 12. Điều tra container và cgroup

Container dùng chung kernel host nhưng có namespace và cgroup để cô lập process, network và tài nguyên. Metric host-level có thể bình thường trong khi một container đã chạm limit.

### Kiểm tra Docker

~~~bash
docker ps -a
docker inspect <container-id>
docker stats --no-stream
docker logs --since 1h <container-id>
docker events --since 1h
~~~

Xem:

- Exit code và OOMKilled.
- Restart policy và thời điểm restart.
- CPU/memory limit và usage.
- Mount, network mode và environment/config version.
- Image digest và thời điểm pull.
- Runtime event như die, oom, kill, restart.

### Cgroup signals

Trên cgroup v2, các file trong cgroup có thể cung cấp:

- cpu.stat: usage và throttling.
- memory.current: memory đang dùng.
- memory.max: giới hạn memory.
- memory.events: số lần high/max/oom/oom_kill.
- io.stat: I/O theo thiết bị.
- cpu.pressure, memory.pressure, io.pressure: pressure stall information nếu kernel hỗ trợ.

Đường dẫn cgroup phụ thuộc runtime và cách mount. Không đọc nhầm cgroup của host thay cho container.

### Pressure Stall Information (PSI)

PSI đo thời gian task bị trì hoãn do thiếu CPU, memory hoặc I/O. Nó hữu ích để phát hiện contention ngay cả khi utilization trung bình chưa đạt 100%. Có thể xem /proc/pressure/cpu, /proc/pressure/memory và /proc/pressure/io nếu kernel bật hỗ trợ.

PSI là tín hiệu bổ sung, cần kết hợp với application latency và cgroup metrics để hiểu workload nào chịu ảnh hưởng.

## 13. Điều tra Kubernetes workload

Kubernetes thêm lớp scheduler, kubelet, controller, CNI, CSI và admission. Khi Pod lỗi, cần xác định đó là lỗi ứng dụng, node, placement, volume, network hay control plane.

### Lệnh quan sát cơ bản

~~~bash
kubectl get pods -A -o wide
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --all-containers --since=1h
kubectl logs <pod-name> -n <namespace> --previous
kubectl get events -n <namespace> --sort-by=.lastTimestamp
kubectl describe node <node-name>
kubectl top nodes
kubectl top pods -A
~~~

### Pod states và event

| Dấu hiệu | Ý nghĩa có thể | Bằng chứng tiếp theo |
|---|---|---|
| Pending | Không schedule được hoặc chưa attach volume | Events, requests, affinity, taint, quota |
| ImagePullBackOff | Pull image thất bại | Registry auth, tag/digest, network, rate limit |
| CrashLoopBackOff | Container liên tục thoát | Previous logs, exit code, probe, OOM |
| OOMKilled | Container vượt memory limit hoặc bị OOM | Last state, cgroup, memory usage, kernel log |
| Evicted | Kubelet evict do node pressure | Node conditions, ephemeral storage, memory/disk |
| NotReady node | Kubelet/runtime/network/host issue | Node conditions, kubelet logs, provider events |
| ContainerCreating kéo dài | Mount, CNI, image pull hoặc runtime | Events, CSI/CNI logs, node status |

### Probe failure

Readiness failure loại Pod khỏi Service endpoints; liveness failure có thể khiến container restart. Startup probe bảo vệ ứng dụng khởi động lâu. Nếu probe quá nhạy hoặc endpoint health phụ thuộc database chậm, toàn bộ Pod có thể bị restart trong lúc hệ thống đang quá tải.

Kiểm tra probe events và thời gian startup. Tránh tăng failureThreshold chỉ để che một lỗi thật; cần xác định health endpoint đo điều gì và có nên phụ thuộc downstream hay không.

### Node pressure và eviction

Kubelet có thể đặt condition MemoryPressure, DiskPressure hoặc PIDPressure. Pod có thể bị evict khi node thiếu tài nguyên. Kiểm tra allocatable, requests, limits, ephemeral storage, image filesystem và log growth.

### Control plane và scheduler

Nếu nhiều Pod Pending trên nhiều node, kiểm tra scheduler events, API server availability, quota, admission webhook và node autoscaler. Nếu chỉ một node bị ảnh hưởng, ưu tiên điều tra kubelet, container runtime, disk và network của node đó.

## 14. Điều tra VM và sự kiện cloud provider

Guest OS chỉ nhìn thấy một phần trạng thái. Cloud control plane có thể ghi nhận stop/start, host maintenance, instance health check, volume detach, quota failure hoặc network change mà guest log không giải thích đầy đủ.

### Kết hợp guest và provider evidence

| Nguồn | Cần kiểm tra |
|---|---|
| Guest OS | CPU, memory, kernel, disk, network, service |
| VM/instance metrics | CPU credits, burst balance, network/disk throughput, status check |
| Activity/audit log | Start/stop/reboot, resize, attach/detach, policy/config update |
| Provider health/event | Maintenance, host issue, zone/region incident |
| Volume metrics | Latency, IOPS, throughput, queue, burst credits |
| Network service | Flow logs, route, firewall, load balancer health |
| Quota/capacity | Instance quota, IP, disk, accelerator availability |

### Ví dụ CPU credit hoặc burst limit

Một số instance family dùng mô hình CPU burst hoặc credit. Khi credit cạn, hiệu năng CPU có thể bị giới hạn dù metric utilization không diễn giải giống instance fixed-performance. Hãy kiểm tra metric credit/baseline theo đúng loại instance.

Tương tự, storage hoặc network có thể có burst balance. Khi burst credit cạn, latency/throughput thay đổi mà guest CPU vẫn thấp.

### Instance health check

Phân biệt system/host check với instance/guest check nếu provider cung cấp. Host check lỗi có thể chỉ ra vấn đề hạ tầng; guest check lỗi có thể do OS không phản hồi, network config hoặc resource exhaustion. Hành động recovery cần dựa trên loại lỗi và chính sách dịch vụ.

## 15. Điều tra serverless và managed compute

Serverless không cung cấp quyền truy cập trực tiếp vào host OS trong mọi trường hợp. Điều tra cần dựa vào invocation metrics, runtime logs, platform events và telemetry của dependency.

### Các tín hiệu cần xem

- Invocation count, success/error/throttle.
- Duration và timeout.
- Concurrent executions và concurrency limit.
- Cold start/init duration.
- Memory configured và memory usage nếu runtime cung cấp.
- CPU architecture/runtime version.
- Queue age, retry, DLQ count và event source lag.
- Downstream latency, connection error và quota.

### Dấu hiệu thường gặp

| Triệu chứng | Giả thuyết | Bằng chứng |
|---|---|---|
| Duration tăng | Dependency chậm hoặc xử lý input lớn | Trace, downstream latency, payload size |
| Throttling | Concurrency/quota hoặc account limit | Throttle metric, concurrency setting |
| Timeout | Code path lâu, network hoặc cold start | Phase timing, init duration, dependency |
| Memory error | Memory allocation vượt cấu hình | Max memory, runtime error, payload size |
| Retry tăng | Function lỗi hoặc ack/visibility sai | Invocation log, queue metric, DLQ |
| Cold start tăng | Scale-out, package lớn hoặc init chậm | Init duration, deployment size, runtime |

### Không có host metrics không có nghĩa không thể điều tra

Hãy instrument thời gian từng phase trong function, ghi correlation ID, model/version, input size theo cách không lộ dữ liệu và latency của dependency. Với queue-triggered function, theo dõi message age và retry để phân biệt xử lý chậm với message poison.

## 16. Liên kết log, metric và trace

Ba loại telemetry bổ sung cho nhau:

- Log ghi sự kiện rời rạc, lỗi và context.
- Metric cho thấy xu hướng, tỷ lệ và mức độ bão hòa.
- Trace cho thấy request đi qua các service/span nào và thời gian ở mỗi bước.

### Quy trình correlation

1. Chọn một request/job lỗi có timestamp và ID.
2. Tìm trace tương ứng và xác định span chậm nhất.
3. Tìm log theo trace ID, request ID hoặc job ID.
4. Đối chiếu metric của service, Pod, node và dependency trong cùng cửa sổ.
5. So sánh với request thành công cùng endpoint/input size.
6. Xác định thời điểm bất thường đầu tiên, không chỉ thời điểm alert.

### Ví dụ

API p99 tăng từ 200 ms lên 4 giây. Trace cho thấy span gọi object storage mất 3,5 giây. Log application không có CPU error; metric node bình thường nhưng storage read latency tăng trên cùng volume. Giả thuyết hợp lý là bottleneck storage, không phải CPU của API. Cần kiểm tra storage queue, IOPS, throttling, volume event và thay đổi gần đây.

## 17. Phương pháp xây dựng và kiểm chứng giả thuyết

Một giả thuyết tốt phải có thể bị bác bỏ. Tránh câu chung chung như “cloud bị chậm” hoặc “máy thiếu tài nguyên”.

Mẫu giả thuyết:

> Từ thời điểm T, workload X có p99 tăng vì resource Y bị giới hạn; bằng chứng dự kiến là metric M tăng và log/event E xuất hiện trên đúng instance/Pod. Nếu M không đổi hoặc workload khỏe mạnh cùng host cũng không bị ảnh hưởng, giả thuyết cần xem lại.

### Bảng giả thuyết

| Giả thuyết | Bằng chứng ủng hộ | Bằng chứng phản bác / cần kiểm tra |
|---|---|---|
| CPU saturation | Run queue, CPU usage và latency cùng tăng | Core idle, process chờ I/O, throttling không tăng |
| CPU throttling | Cgroup throttled time tăng | Không có limit hoặc throttling counter bằng 0 |
| Memory pressure | Available thấp, swap/PSI/OOM tăng | Memory ổn định, không có reclaim hoặc OOM |
| Disk bottleneck | I/O latency/queue tăng, process D state | Disk latency bình thường, lỗi ở network |
| Network issue | Retransmit, timeout, DNS hoặc flow deny | TCP ổn, downstream xử lý chậm |
| Dependency outage | Nhiều caller lỗi cùng destination | Chỉ một host/process lỗi |
| Bad deployment | Lỗi bắt đầu sau version/config change | Phiên bản cũ và mới cùng lỗi ở cùng thời điểm |
| Provider event | Health/maintenance event trùng timeline | Không có event, host metrics và peer không bị ảnh hưởng |

### Thí nghiệm có kiểm soát

Nếu có thể, thử nghiệm trên canary hoặc một replica:

- Chuyển traffic một phần sang phiên bản cũ.
- Giảm concurrency để xem queue/latency thay đổi.
- Chạy cùng workload trên node khác đã biết khỏe.
- Tạm dừng batch cạnh tranh theo change plan.
- So sánh volume hoặc instance family khác trong môi trường thử nghiệm.

Không thay đổi nhiều biến cùng lúc vì sẽ khó biết yếu tố nào tạo ra kết quả.

## 18. Các tình huống điều tra thực tế

### Tình huống A: CPU cao sau deploy

**Triệu chứng:** p95 API tăng, CPU của một nhóm Pod lên 95%, số request gần như không đổi.

**Bằng chứng cần lấy:**

- Deployment version và config change.
- CPU per container và per thread.
- Profile/hot stack.
- GC pause hoặc allocation rate.
- Retry count và request distribution.

**Giả thuyết:** bản mới tạo vòng retry hoặc serialization tốn CPU. Nếu CPU tăng cùng retry count và profile chỉ ra cùng code path, rollback canary hoặc giảm traffic là mitigation có cơ sở. Sau đó sửa retry/backoff và kiểm thử tải.

### Tình huống B: Container restart do OOM

**Triệu chứng:** Pod CrashLoopBackOff, last termination reason là OOMKilled.

**Bằng chứng cần lấy:**

- Previous container logs.
- Pod requests/limits và node allocatable.
- Container memory working set theo thời gian.
- Kernel/cgroup OOM events.
- Input size, concurrency và heap profile.

**Giả thuyết:** một batch lớn làm activation hoặc cache tăng vượt limit. Có thể giảm concurrency hoặc batch tạm thời; sau đó tối ưu memory, đặt limit/request dựa trên peak và xác minh node đủ capacity.

### Tình huống C: VM chậm nhưng CPU thấp

**Triệu chứng:** ứng dụng timeout, CPU 15%, memory còn nhiều.

**Bằng chứng cần lấy:**

- iostat, await, queue depth và device latency.
- Process D state và pidstat -d.
- Volume throughput/IOPS/credit metrics.
- Kernel disk errors và provider volume events.

**Giả thuyết:** volume bị throttling hoặc backend storage latency tăng. Tăng CPU không giải quyết; cần giảm I/O, điều chỉnh volume hoặc chuyển workload theo change plan.

### Tình huống D: Nhiều Pod Pending sau scale-out

**Triệu chứng:** HPA tăng replicas nhưng Pod không chạy.

**Bằng chứng cần lấy:**

- kubectl describe pod và scheduler events.
- Node allocatable, taint, affinity và topology.
- Node autoscaler logs, max node count và cloud quota.
- PVC zone binding và IP/subnet capacity.

**Giả thuyết:** node pool đạt max hoặc Pod yêu cầu GPU/zone không có capacity. Tăng max chỉ khi quota và budget cho phép; nếu constraint sai, sửa placement policy thay vì tạo thêm node không phù hợp.

### Tình huống E: Request timeout theo một zone

**Triệu chứng:** lỗi tập trung ở backend trong zone B; zone A bình thường.

**Bằng chứng cần lấy:**

- Load balancer target health theo zone.
- Flow log, route/firewall change và DNS response.
- Network retransmit/packet drop của node.
- Provider health event và dependency endpoint.

**Giả thuyết:** route hoặc network path của zone B có vấn đề. Có thể chuyển traffic khỏi target lỗi theo runbook, nhưng cần theo dõi capacity vùng còn lại và tránh overload.

## 19. Mitigation, recovery và xác minh

Mitigation là hành động giảm ảnh hưởng trong khi nguyên nhân gốc có thể chưa được sửa hoàn toàn. Chọn biện pháp nhỏ nhất có thể khôi phục SLO mà không làm tăng rủi ro.

### Các loại mitigation

- Rollback bản deploy hoặc config vừa thay đổi.
- Giảm traffic, rate limit hoặc bật backpressure.
- Scale-out nếu bottleneck thực sự là capacity và dependency còn chịu được.
- Chuyển traffic khỏi node/zone lỗi.
- Tạm dừng batch job cạnh tranh tài nguyên.
- Tăng storage capacity hoặc điều chỉnh throughput theo change process.
- Restart một process/Pod cụ thể khi đã thu thập bằng chứng và hiểu tác động.
- Failover theo runbook đã kiểm thử.

### Điều kiện trước khi restart/reboot

- Đã lưu log và metric cần thiết.
- Biết process có state local hoặc job đang chạy không.
- Có replica/capacity thay thế.
- Có kế hoạch drain và kiểm tra dữ liệu chưa flush.
- Có người chịu trách nhiệm và rollback.
- Đã cân nhắc việc restart có che mất nguyên nhân hay không.

### Xác minh phục hồi

Sau mitigation, kiểm tra:

- Error rate, p95/p99 và throughput trở về ngưỡng.
- CPU, memory, disk, network và queue không còn tăng bất thường.
- Pod/VM/process healthy và restart rate ổn định.
- Dependency và downstream không bị quá tải do traffic chuyển vùng.
- Job không mất, không xử lý trùng ngoài kiểm soát.
- Alert đã clear theo điều kiện ổn định, không chỉ tạm thời.
- Theo dõi đủ lâu để bao phủ chu kỳ tải liên quan.

## 20. Viết báo cáo sự cố và RCA

Root Cause Analysis (RCA) nên giải thích điều gì xảy ra, vì sao kiểm soát hiện tại không ngăn hoặc phát hiện sớm và hành động nào giảm nguy cơ tái diễn. Báo cáo tập trung vào hệ thống và điều kiện, không đổ lỗi cá nhân.

### Cấu trúc báo cáo

| Mục | Nội dung |
|---|---|
| Summary | Sự cố và ảnh hưởng chính |
| Impact | Người dùng, tenant, request, job, dữ liệu và SLO |
| Timeline | Detection, escalation, mitigation, recovery |
| Evidence | Log, metric, trace, OS/provider event và query |
| Root cause | Cơ chế kỹ thuật dẫn tới sự cố |
| Contributing factors | Thiếu guardrail, alert, capacity hoặc test |
| Mitigation | Hành động trong incident và tác động |
| Resolution | Sửa lỗi dài hạn và xác minh |
| Follow-up | Owner, due date, priority và trạng thái |

### Action item tốt

Action item nên có owner, thời hạn, kết quả kiểm chứng và mức ưu tiên. Ví dụ:

- Thêm alert khi cgroup memory pressure kéo dài trên ngưỡng đã benchmark.
- Giới hạn batch size và thêm test với input lớn nhất.
- Bổ sung dashboard storage latency theo volume.
- Cập nhật runbook điều tra CPU throttling.
- Thêm policy kiểm tra Pod request/limit trước deploy.

Tránh action item mơ hồ như “theo dõi hệ thống tốt hơn” hoặc “tăng hiệu năng”.

## 21. Checklist điều tra sự cố compute

- [ ] Xác định service, severity, phạm vi, thời điểm và người điều phối.
- [ ] Ghi region, zone, instance/node, Pod/container, process và version.
- [ ] Chuẩn hóa timestamp và correlation ID.
- [ ] Thu thập application, system, kernel, runtime, orchestration và cloud audit logs.
- [ ] Chụp metric CPU, memory, disk, network, process, queue và SLO.
- [ ] So sánh với baseline và workload khỏe mạnh tương đương.
- [ ] Kiểm tra CPU saturation, throttling, steal và run queue.
- [ ] Kiểm tra memory pressure, swap, page fault, cgroup và OOM.
- [ ] Kiểm tra disk latency, IOPS, throughput, free space và inode.
- [ ] Kiểm tra network drop, retransmit, DNS, route, firewall và connection state.
- [ ] Kiểm tra process/thread, file descriptor, kernel, driver và service events.
- [ ] Kiểm tra Pod events, probes, eviction, scheduler và node autoscaler nếu dùng Kubernetes.
- [ ] Kiểm tra VM health, quota, provider maintenance và storage/network events.
- [ ] Viết giả thuyết có bằng chứng ủng hộ và phản bác.
- [ ] Bảo toàn bằng chứng trước hành động thay đổi.
- [ ] Chọn mitigation có kiểm soát và theo dõi tác động.
- [ ] Xác minh SLO, dependency, queue và dữ liệu sau phục hồi.
- [ ] Viết RCA với owner, deadline và cách kiểm chứng action item.

## 22. Bài tập vận dụng

Một API xử lý hồ sơ chạy trên Kubernetes. Lúc 09:20 UTC, p99 latency tăng từ 300 ms lên 5 giây và tỷ lệ 5xx tăng. HPA tăng replicas từ 4 lên 12. Một số Pod mới Pending; các Pod đang chạy có memory working set tăng và hai container bị OOMKilled. CPU node chỉ khoảng 55%, nhưng cgroup CPU throttling tăng. Storage latency của volume cache cũng tăng từ 4 ms lên 80 ms. Một bản deploy mới được phát hành lúc 09:12 UTC.

1. Hãy dựng timeline và liệt kê nguồn log/metric cần thu thập.
2. Vì sao CPU node 55% không loại trừ khả năng CPU là một phần nguyên nhân?
3. Những giả thuyết nào giải thích đồng thời OOMKilled, throttling và storage latency?
4. Cần kiểm tra những gì để xác định Pod Pending do thiếu capacity hay constraint placement?
5. Đề xuất thứ tự mitigation an toàn và bằng chứng cần giữ trước mỗi thay đổi.
6. Nêu tiêu chí xác minh dịch vụ đã phục hồi và các action item phòng ngừa.

Gợi ý: đối chiếu deploy lúc 09:12 UTC với thời điểm latency bắt đầu tăng; xem diff image/config, request/limit, cache behavior và concurrency. CPU host có thể còn rảnh trong khi container bị quota throttling. Storage cache chậm có thể khiến request giữ buffer/connection lâu, làm memory tăng; batch hoặc concurrency mới cũng có thể làm OOM. Thu thập Pod previous logs/events, cgroup stats, node allocatable, scheduler events, PVC/volume metrics, application traces và cloud events. Mitigation có thể rollback canary hoặc giảm concurrency/batch sau khi export evidence; không scale thêm mù quáng khi storage là bottleneck. Xác minh p99/5xx, OOM/restart, throttling, storage latency, queue và downstream trở lại baseline.

## Kết luận

Điều tra sự cố compute hiệu quả dựa trên việc liên kết log, metric, trace, event và dấu hiệu hệ điều hành theo cùng timeline và resource identity. Hãy xác định ảnh hưởng trước, bảo toàn bằng chứng, phân loại bottleneck theo CPU, memory, disk, network, process hoặc platform, rồi kiểm chứng giả thuyết bằng dữ liệu. Mitigation cần có kiểm soát và được xác minh bằng SLO cùng trạng thái dependency. RCA sau sự cố phải chuyển bằng chứng thành hành động cụ thể để giảm khả năng tái diễn.
