# Đo CPU, RAM, I/O, disk latency và mạng từ hệ điều hành

Trong vận hành MySQL, câu truy vấn chậm có thể bắt nguồn từ CPU, áp lực bộ nhớ, thiết bị lưu trữ hoặc đường truyền mạng. Đo ở tầng hệ điều hành giúp xác định tài nguyên nào đang bị giới hạn, tiến trình hoặc thiết bị nào chịu tải, và hiện tượng đó có trùng với thời điểm MySQL chậm hay không. Đây là kỹ năng quan trọng bên cạnh việc đọc execution plan, index, transaction và các thống kê bên trong máy chủ cơ sở dữ liệu.

Bài học này trình bày cách thu thập và diễn giải các chỉ số CPU, RAM, I/O, độ trễ đĩa và mạng trên Linux, Windows, máy ảo và container. Mục tiêu là tạo được một phép đo có thể lặp lại, gắn đúng chỉ số với đúng máy chủ MySQL, rồi dùng bằng chứng để khoanh vùng nguyên nhân.

## 1. Phạm vi quan sát và nguyên tắc đo

### 1.1. Quan sát đúng lớp tài nguyên

Một máy chủ MySQL có nhiều lớp cần phân biệt:

- **Host**: CPU, RAM, thiết bị block, filesystem, NIC và kernel của máy vật lý hoặc máy ảo.
- **Process**: tiến trình **mysqld** hoặc **mariadbd**, gồm nhiều luồng thực thi.
- **Container/cgroup**: giới hạn CPU, RAM và I/O mà container được cấp. Tài nguyên host còn trống không có nghĩa container còn quota.
- **Storage backend**: volume cloud, SAN, RAID, LVM, thiết bị NVMe hoặc lớp lưu trữ mạng. Một đường dẫn như **/var/lib/mysql** có thể không tương ứng với một đĩa vật lý duy nhất.
- **Network path**: NIC của máy, virtual switch, firewall, load balancer, mạng liên vùng và máy khách. Đo tại máy chủ chỉ phản ánh một phần đường đi.

Không nên kết luận “MySQL thiếu CPU” chỉ vì CPU toàn máy cao. Một tiến trình khác có thể chiếm CPU. Tương tự, **%util** của một thiết bị không tự nó chứng minh đĩa đã bão hòa; thiết bị có khả năng xử lý song song lớn có thể đạt throughput cao khi vẫn còn năng lực.

### 1.2. Đo theo khoảng thời gian

Một phép đo hữu ích phải gắn với một cửa sổ thời gian cụ thể. Ghi lại:

1. Thời điểm bắt đầu và kết thúc, múi giờ, hostname và instance MySQL.
2. Tải ứng dụng trong cùng thời gian: số request, throughput, loại truy vấn, số kết nối và thời điểm bắt đầu sự cố.
3. Chỉ số tổng thể của host và chỉ số riêng của process, device hoặc interface.
4. Giá trị nền trong lúc hệ thống bình thường để so sánh với lúc có vấn đề.

Ưu tiên lấy mẫu theo chu kỳ 1–5 giây trong vài phút khi điều tra sự cố ngắn; dùng khoảng dài hơn cho xu hướng ngày hoặc tuần. Một mẫu đơn lẻ có thể bỏ lỡ spike. Với sự cố không liên tục, cần giữ lại lịch sử bằng **sar**, hệ thống giám sát hoặc agent metrics thay vì chỉ chạy lệnh sau khi sự cố đã kết thúc.

Các lệnh **vmstat**, **iostat** và một số tiện ích có dòng đầu tiên là số trung bình từ lúc khởi động hoặc từ lần khởi động công cụ. Khi phân tích tải hiện tại, hãy đọc các mẫu tiếp theo theo đúng chu kỳ; đừng nhầm dòng tổng hợp đầu tiên với một khoảng lấy mẫu một giây.

### 1.3. Xác định máy, tiến trình và thiết bị trước khi đo

Trên Linux, có thể bắt đầu bằng:

~~~bash
date --iso-8601=seconds
hostnamectl --static
uptime
nproc
lscpu
pgrep -a 'mysqld|mariadbd'
ps -eo pid,ppid,user,comm,args | grep -E '[m]ysqld|[m]ariadbd'
~~~

Nếu máy có nhiều instance, không chọn PID chỉ dựa trên tên tiến trình. Đối chiếu PID với service, command line, socket, port và thư mục dữ liệu. Ví dụ, với systemd:

~~~bash
systemctl status mysql
systemctl show mysql -p MainPID -p ControlGroup
~~~

Tên service có thể là **mysqld**, **mysql**, **mariadb** hoặc tên do đơn vị vận hành đặt. Nếu **MainPID** bằng 0 hoặc service khởi chạy qua supervisor/container, hãy xác định PID từ đúng môi trường chạy.

Tìm thiết bị và filesystem đang chứa dữ liệu, redo log, binary log và thư mục tạm:

~~~bash
findmnt -T /var/lib/mysql
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,ROTA,MODEL
df -hT
df -i
~~~

Thay **/var/lib/mysql** bằng **datadir** thực tế. Đường dẫn redo log, binary log, relay log và temporary directory có thể nằm trên các mount khác nhau. **findmnt** cho biết filesystem/mount; **lsblk** giúp lần theo thiết bị block. Với LVM, RAID, multipath hoặc cloud volume, tiếp tục đối chiếu lớp ánh xạ để không gán nhầm độ trễ của một volume cho thiết bị khác.

Trên Windows, xác định service và process trước:

~~~powershell
Get-CimInstance Win32_Service |
  Where-Object { $_.Name -match 'MySQL|MariaDB' } |
  Select-Object Name, State, StartName, ProcessId, PathName

Get-Process -Name mysqld -ErrorAction SilentlyContinue |
  Select-Object Id, CPU, WorkingSet64, PrivateMemorySize64, StartTime

Get-Volume
Get-Disk
Get-NetAdapter
~~~

**Get-Process** có thể trả về nhiều instance. Ghép **ProcessId** với service và command line tương ứng. Trên Windows, dùng **Get-Partition**, **Get-Volume** và đường dẫn **datadir** để xác định volume đang chứa dữ liệu.

## 2. Chuẩn bị công cụ và quyền truy cập

### 2.1. Linux

Các tiện ích thường dùng:

| Công cụ | Mục đích |
|---|---|
| **top**, **ps**, **lscpu**, **mpstat** | CPU, luồng và tiến trình |
| **free**, **vmstat**, **sar -r**, **pidstat** | RAM, swap, page fault |
| **iostat**, **pidstat -d**, **iotop**, **lsblk** | I/O theo thiết bị và tiến trình |
| **ip**, **ss**, **sar -n**, **nstat**, **ethtool** | NIC, TCP và lỗi mạng |

**mpstat**, **iostat**, **sar** và **pidstat** thường được cung cấp bởi gói **sysstat**; tên gói và cách cài đặt tùy bản phân phối. **vmstat**, **free** và **ps** thường nằm trong **procps** hoặc gói tương đương. **ss** thuộc bộ **iproute2**. **iotop** và **ethtool** có thể cần cài riêng.

Các lệnh đọc số liệu thường cần quyền người dùng thường. Để xem chi tiết process, thiết bị hoặc thống kê kernel, có thể cần **sudo**. Chỉ cấp quyền cần thiết và tuân thủ quy trình vận hành của môi trường production.

### 2.2. Windows

Windows có thể thu thập số liệu bằng Performance Monitor, Resource Monitor, Task Manager, PowerShell **Get-Counter** và các cmdlet **Get-***. Performance counter có tên instance thay đổi theo số process, adapter và disk. Hãy liệt kê counter khả dụng trên máy thay vì giả định mọi máy đều có cùng tên.

~~~powershell
Get-Counter -ListSet Processor
Get-Counter -ListSet Memory
Get-Counter -ListSet PhysicalDisk
Get-Counter -ListSet 'Network Interface'
Get-Counter -ListSet TCPv4
~~~

Tên counter có thể được bản địa hóa theo ngôn ngữ Windows. Khi một đường dẫn counter không tồn tại, hãy tìm tên tương ứng bằng **Get-Counter -ListSet** hoặc giao diện Performance Monitor.

## 3. Đo CPU

CPU ảnh hưởng đến khả năng thực thi truy vấn, xử lý biểu thức, join, sort, mã hóa, nén, checksum, quản lý kết nối và các luồng nền của InnoDB. Cần tách CPU toàn host khỏi CPU mà tiến trình MySQL thực sự sử dụng.

### 3.1. Chỉ số cần hiểu

- **user (%usr)**: CPU chạy mã ở user space, gồm phần lớn công việc của MySQL.
- **system (%sys)**: CPU chạy mã kernel, chẳng hạn xử lý I/O, network stack, filesystem và system call.
- **idle (%idle)**: CPU không bận.
- **iowait (%iowait)**: CPU rảnh trong khi hệ thống có I/O đang chờ. Đây không phải phần trăm thời gian đĩa bận và cũng không phải phép đo trực tiếp disk latency.
- **steal (%steal)**: thời gian máy ảo muốn chạy nhưng hypervisor cấp CPU cho máy ảo khác.
- **run queue**: số tác vụ runnable đang chờ CPU. Nếu kéo dài lớn hơn số CPU khả dụng, có thể có tranh chấp CPU.
- **load average**: trung bình số tác vụ runnable và một số tác vụ không ngắt được (thường đang chờ I/O) trong các cửa sổ 1, 5, 15 phút trên Linux. Load average không phải CPU utilization.

### 3.2. Thu thập trên Linux

Xem CPU từng lõi và tổng thể:

~~~bash
mpstat -P ALL 1 60
~~~

Các cột **%usr**, **%sys**, **%iowait**, **%steal**, **%idle** cho biết thời gian CPU được phân bổ theo trạng thái. Đừng chỉ nhìn dòng **all**: một lõi có thể bão hòa trong khi mức trung bình toàn máy còn thấp. Điều này thường gặp khi một luồng truy vấn hoặc một luồng nền trở thành điểm nghẽn.

Đo riêng process MySQL:

~~~bash
PID=$(pgrep -xo mysqld)
pidstat -u -p "$PID" 1 60
pidstat -w -p "$PID" 1 60
top -H -p "$PID"
~~~

Nếu process có tên **mariadbd**, thay tên trong lệnh tìm PID. Nếu có nhiều PID, chỉ định đúng PID thay vì dùng kết quả đầu tiên. **pidstat -u** cho mức sử dụng CPU của process; **pidstat -w** cho context switch; **top -H** hiển thị từng thread để nhận ra luồng nào đang bận. Khi cần so sánh chính xác, ghi lại số CPU khả dụng và cách công cụ chuẩn hóa phần trăm.

Trạng thái run queue và các tác vụ bị block có thể quan sát bằng:

~~~bash
vmstat 1 60
uptime
~~~

Trong **vmstat**, cột **r** là số tác vụ runnable và **b** là số tác vụ đang ở trạng thái block. So sánh **r** với số CPU được cấp cho process/container. **b** tăng cùng **wa** có thể gợi ý chờ I/O, nhưng vẫn cần đối chiếu với **iostat** và các chỉ số storage.

### 3.3. Diễn giải CPU

- **%usr** của host và process MySQL đều cao, run queue tăng, CPU idle thấp: MySQL hoặc workload có thể đang tiêu thụ CPU thực sự.
- **%usr** cao ở host nhưng thấp ở MySQL: tìm process khác bằng **top**, **ps** hoặc **pidstat**.
- **%sys** tăng mạnh: kiểm tra system call, network, filesystem, interrupt, context switch và driver.
- **%iowait** tăng cùng **await** của thiết bị: có bằng chứng mạnh hơn về chờ storage. Chỉ riêng **%iowait** chưa đủ để kết luận.
- **%steal** tăng: kiểm tra giới hạn hoặc tranh chấp ở hypervisor/cloud; tối ưu SQL có thể không giải quyết được.
- Load average cao nhưng CPU idle còn nhiều: kiểm tra tác vụ uninterruptible, I/O, quota container và số CPU thực tế được cấp.
- Một thread đạt gần 100% trong khi nhiều lõi khác rảnh: workload có thể bị giới hạn bởi một luồng hoặc một đoạn xử lý tuần tự.

CPU phần trăm của process trên Linux có thể vượt 100% khi process chạy đồng thời trên nhiều lõi, tùy cách hiển thị của công cụ. Đừng hiểu 180% là process dùng 180% toàn bộ máy; hãy đối chiếu với số lõi và quy ước của công cụ.

### 3.4. Thu thập CPU trên Windows

PowerShell có thể lấy mẫu counter trong một phút:

~~~powershell
Get-Counter -Counter @(
  '\Processor(_Total)\% Processor Time',
  '\System\Processor Queue Length',
  '\Process(mysqld)\% Processor Time'
) -SampleInterval 1 -MaxSamples 60
~~~

Nếu process instance không tên **mysqld** hoặc có hậu tố như **mysqld#1**, tìm instance chính xác bằng danh sách counter hoặc Task Manager. **Processor(_Total)\% Processor Time** là mức sử dụng tổng thể; **Processor(*)\% Processor Time** giúp phát hiện lõi nóng; **System\Processor Queue Length** hỗ trợ nhận biết hàng đợi CPU. Dùng cùng một khoảng lấy mẫu khi so sánh host và process.

## 4. Đo RAM và áp lực bộ nhớ

MySQL sử dụng RAM cho InnoDB buffer pool, per-connection buffers, table cache, Performance Schema, bộ nhớ cho truy vấn và các cấu trúc nội bộ khác. Hệ điều hành cũng cần RAM cho kernel, page cache, filesystem và process khác. Một máy có RAM gần đầy chưa chắc gặp vấn đề; cần xác định liệu hệ thống có thiếu bộ nhớ khả dụng, phải swap hoặc chịu áp lực reclaim hay không.

### 4.1. Các khái niệm quan trọng

- **MemTotal**: tổng RAM mà kernel nhận diện.
- **MemAvailable**: ước lượng RAM có thể cấp cho ứng dụng mà không cần swap đáng kể; hữu ích hơn **MemFree** khi đánh giá thiếu RAM.
- **RSS/Working Set**: các trang đang nằm trong RAM của process. RSS có thể bao gồm trang dùng chung.
- **VIRT/VSZ**: không gian địa chỉ ảo; không đồng nghĩa lượng RAM thực dùng.
- **Swap in/out**: dữ liệu được đưa từ swap vào RAM hoặc ghi từ RAM ra swap. Hoạt động swap liên tục có thể làm tăng độ trễ.
- **Major page fault**: cần đọc trang từ backing store; có thể gây chờ. Minor page fault không cần đọc dữ liệu từ đĩa.
- **Page cache**: RAM kernel dùng để cache dữ liệu filesystem. Phần này có thể được thu hồi khi ứng dụng cần RAM.

### 4.2. Thu thập trên Linux

~~~bash
free -h
cat /proc/meminfo
vmstat 1 60
sar -r ALL 1 60
~~~

Trong **free -h**, tập trung vào **available**, swap đã dùng và xu hướng thay đổi. Không kết luận thiếu RAM chỉ vì **free** thấp: Linux chủ động dùng RAM nhàn rỗi làm cache. Trong **vmstat**, theo dõi **si** và **so**; giá trị liên tục khác 0 trong lúc truy vấn chậm đáng được điều tra. Dòng đầu của **vmstat** thường là trung bình từ khi khởi động, nên đọc các dòng tiếp theo để xem tốc độ hiện tại.

Đo bộ nhớ và page fault của process:

Các lệnh dưới đây dùng biến **PID** đã xác định ở mục 3.2. Nếu mở shell mới, gán lại PID sau khi xác minh đúng instance MySQL.

~~~bash
pidstat -r -p "$PID" 1 60
ps -o pid,comm,rss,vsz,%mem --sort=-rss -p "$PID"
~~~

**pidstat -r** cung cấp page fault và một số chỉ số bộ nhớ theo process. **ps** cho RSS/VSZ tại thời điểm lấy mẫu; nó không thay thế chuỗi thời gian. Khi process có nhiều thread, bộ nhớ thường thuộc address space chung nên không cộng RSS của từng thread.

Kiểm tra dấu hiệu kernel kết thúc process vì thiếu RAM:

~~~bash
journalctl -k --since "30 minutes ago" |
  grep -Ei 'out of memory|oom-killer|killed process'
~~~

Trên hệ thống không dùng systemd, xem kernel log theo cơ chế logging của bản phân phối. Đối chiếu thời điểm OOM với restart của MySQL và cảnh báo từ service manager.

### 4.3. Phân biệt áp lực RAM với bộ nhớ cache

Một buffer pool lớn có thể làm RAM khả dụng giảm, nhưng nếu **MemAvailable** ổn định, không có swap-in/swap-out đáng kể và không có OOM thì chưa đủ bằng chứng để giảm buffer pool. Ngược lại, **MemAvailable** giảm liên tục, swap hoạt động, major fault tăng và độ trễ truy vấn cùng tăng cho thấy áp lực bộ nhớ cần được xử lý.

Cần xem cả mức tiêu thụ ngoài MySQL: agent backup, antivirus, exporter, log shipper, process ứng dụng cùng host hoặc container sidecar. Kiểm tra giới hạn cgroup vì process có thể bị OOM trong container dù host vẫn còn RAM.

### 4.4. Thu thập RAM trên Windows

~~~powershell
Get-Counter -Counter @(
  '\Memory\Available MBytes',
  '\Memory\Committed Bytes',
  '\Memory\Pages/sec',
  '\Process(mysqld)\Working Set - Private'
) -SampleInterval 1 -MaxSamples 60

Get-Process -Name mysqld -ErrorAction SilentlyContinue |
  Select-Object Id, WorkingSet64, PrivateMemorySize64, VirtualMemorySize64
~~~

**Available MBytes** giúp theo dõi RAM còn khả dụng; **Committed Bytes** phản ánh bộ nhớ đã commit; **Pages/sec** là hoạt động paging tổng thể, không chỉ riêng MySQL. Đọc thêm Resource Monitor và Event Viewer để xác định process, disk paging và sự kiện thiếu bộ nhớ. Với nhiều instance, chọn đúng process counter instance.

## 5. Đo I/O và độ trễ đĩa

MySQL phụ thuộc storage cho data page, redo log, undo, binary log, relay log, temporary file và các thao tác flush. Cần đo cả throughput, số thao tác I/O, hàng đợi và độ trễ. Một volume có throughput thấp không nhất thiết chậm; một volume có throughput cao cũng có thể đang chạm giới hạn IOPS hoặc latency.

### 5.1. Xác định thiết bị thật phía sau đường dẫn

Trước tiên tìm filesystem của **datadir**, redo log, binary log và thư mục tạm bằng **findmnt -T <đường-dẫn>**. Sau đó lần theo **lsblk**, LVM, RAID, device mapper hoặc volume cloud. Nếu data và log dùng thiết bị riêng, thu thập từng thiết bị. Nếu nhiều mount cùng nằm trên một volume, các số liệu có thể phản ánh tải tổng hợp.

~~~bash
findmnt -T /var/lib/mysql
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,ROTA,MODEL
df -hT /var/lib/mysql
~~~

**df -hT** kiểm tra dung lượng và loại filesystem; **df -i** kiểm tra inode. Hết dung lượng hoặc inode có thể gây lỗi ghi dù latency thấp. Kiểm tra log kernel khi có lỗi I/O, filesystem read-only, reset controller hoặc timeout thiết bị.

### 5.2. Đo theo thiết bị trên Linux

~~~bash
iostat -xz 1 60
sar -d 1 60
~~~

**iostat -xz** cung cấp thống kê mở rộng theo thiết bị. Các cột thường gặp:

| Chỉ số | Ý nghĩa |
|---|---|
| **r/s**, **w/s** | Số lần đọc/ghi mỗi giây (IOPS quan sát được) |
| **rkB/s**, **wkB/s** | Throughput đọc/ghi |
| **r_await**, **w_await** | Độ trễ trung bình mỗi thao tác đọc/ghi, gồm thời gian chờ hàng đợi và xử lý |
| **aqu-sz** | Độ dài hàng đợi I/O trung bình |
| **%util** | Tỷ lệ thời gian thiết bị có I/O đang được xử lý theo cách kernel thống kê |

Đọc **r_await** và **w_await** riêng để biết hướng đọc hay ghi bị ảnh hưởng. Với workload ghi redo log đồng bộ, latency ghi/flush có thể quan trọng hơn throughput tổng. Với truy vấn đọc nhiều, latency đọc và IOPS ngẫu nhiên thường cần quan sát.

**%util** gần 100% có thể là dấu hiệu thiết bị bận, nhưng không phải ngưỡng bão hòa phổ quát cho SSD/NVMe hoặc thiết bị có khả năng xử lý song song. Không dùng một con số **%util** để kết luận thay cho **await**, **aqu-sz**, throughput, giới hạn volume và xu hướng thời gian. **await** là trung bình; nó không cho biết p95/p99. Nếu cần tail latency, dùng telemetry của storage backend hoặc công cụ tracing phù hợp.

Đo I/O của process:

Dùng cùng biến **PID** đã xác minh ở mục 3.2; nếu máy có nhiều instance, chỉ định PID của đúng instance.

~~~bash
pidstat -d -p "$PID" 1 60
~~~

**pidstat -d** giúp xem lượng đọc/ghi theo process và độ trễ I/O được kernel quy cho tác vụ. Một số loại I/O được buffer hoặc thực hiện bất đồng bộ nên số liệu process không nhất thiết bằng tổng số liệu thiết bị. Có thể dùng **iotop -oPa** để quan sát process đang phát sinh I/O; công cụ này thường cần quyền cao và có overhead, vì vậy chỉ bật trong khoảng điều tra ngắn.

### 5.3. Đọc mẫu số liệu I/O

- **await** tăng và **aqu-sz** tăng cùng lúc: I/O phải chờ lâu hơn trong hàng đợi hoặc backend xử lý chậm.
- **r_await** tăng nhưng **w_await** ổn định: kiểm tra workload đọc, cache miss, random read và volume chứa data.
- **w_await** tăng cùng thời điểm commit chậm: kiểm tra redo log, binary log, fsync, volume chứa log và giới hạn ghi.
- Throughput gần giới hạn được công bố của volume, latency tăng khi tải tăng: có thể volume đã chạm giới hạn throughput.
- IOPS cao nhưng throughput thấp: có thể là nhiều thao tác nhỏ/ngẫu nhiên.
- Throughput cao nhưng IOPS thấp: có thể là thao tác tuần tự hoặc kích thước I/O lớn.
- **df** cho thấy filesystem gần đầy hoặc kernel log có lỗi I/O: xử lý dung lượng hoặc thiết bị trước khi tối ưu truy vấn.

Không suy ra độ trễ của một truy vấn từ **await** trung bình của cả thiết bị. Cần so sánh đúng khoảng thời gian, đúng volume và đúng loại I/O; workload khác trên cùng volume có thể làm nhiễu kết quả.

### 5.4. Đo storage trên Windows

Trong Performance Monitor, có thể theo dõi các counter thuộc **PhysicalDisk**:

- **Avg. Disk sec/Read** và **Avg. Disk sec/Write**: thời gian trung bình mỗi thao tác đọc/ghi, đơn vị giây. Nhân 1.000 để đổi sang mili giây.
- **Disk Reads/sec** và **Disk Writes/sec**: IOPS quan sát được.
- **Disk Read Bytes/sec** và **Disk Write Bytes/sec**: throughput.
- **Current Disk Queue Length**: số yêu cầu đang chờ hoặc xử lý tại thời điểm lấy mẫu.

PowerShell:

~~~powershell
Get-Counter -Counter @(
  '\PhysicalDisk(*)\Avg. Disk sec/Read',
  '\PhysicalDisk(*)\Avg. Disk sec/Write',
  '\PhysicalDisk(*)\Disk Reads/sec',
  '\PhysicalDisk(*)\Disk Writes/sec',
  '\PhysicalDisk(*)\Current Disk Queue Length'
) -SampleInterval 1 -MaxSamples 60
~~~

Chọn đúng disk instance chứa dữ liệu MySQL. Nếu volume nằm trên Storage Spaces, SAN hoặc cloud disk, đối chiếu thêm counter ở lớp volume/backend tương ứng. Queue length phải được diễn giải theo loại thiết bị, số luồng và khả năng song song; không áp dụng một ngưỡng chung cho mọi ổ.

Không chạy benchmark ghi trực tiếp lên volume dữ liệu MySQL đang hoạt động. Các công cụ như DiskSpd hoặc fio chỉ nên chạy theo kế hoạch kiểm thử riêng, trên volume thử nghiệm hoặc trong cửa sổ đã được phê duyệt, với kích thước và kiểu tải được kiểm soát.

## 6. Đo mạng

Kết nối MySQL có thể bị chậm do băng thông, packet loss, retransmission, RTT cao, hàng đợi socket, lỗi NIC hoặc vấn đề ở mạng trung gian. CPU và disk có thể bình thường trong khi client vẫn chờ vì đường truyền.

### 6.1. Chỉ số mạng cần theo dõi

- **Throughput**: byte/giây hoặc bit/giây theo chiều nhận và gửi.
- **Errors/drops**: frame hoặc packet lỗi/bị loại tại interface.
- **TCP retransmission**: segment phải gửi lại; có thể gợi ý mất gói hoặc nghẽn.
- **RTT**: thời gian khứ hồi trên kết nối TCP.
- **Socket queue**: dữ liệu đang chờ ứng dụng đọc hoặc đang chờ gửi.
- **Connection state**: số kết nối established, time-wait, số lần mở/đóng và tình trạng listen queue.

### 6.2. Thu thập trên Linux

Xem interface và counter:

~~~bash
ip -br link
ip -s link
sar -n DEV 1 60
~~~

**ip -s link** hiển thị byte, packet, error và drop tích lũy của từng interface. So sánh hai lần lấy mẫu để biết tốc độ tăng, vì counter tích lũy từ lúc khởi động không tự cho biết lỗi xảy ra trong phút hiện tại. **sar -n DEV** cho throughput và các counter theo chu kỳ.

Xem TCP và retransmission:

~~~bash
sar -n TCP,ETCP 1 60
nstat -az
ss -s
~~~

**nstat -az** hiển thị counter mạng của kernel; nhiều giá trị là bộ đếm tích lũy, cần lấy delta theo thời gian. **sar -n TCP,ETCP** hỗ trợ theo dõi hoạt động TCP và lỗi/retransmission tùy phiên bản **sysstat**.

Xem socket và trạng thái TCP:

~~~bash
ss -lntp
ss -tan
ss -ti state established
~~~

**ss -lntp** giúp xác định process đang listen trên port MySQL, thường là 3306 nhưng có thể khác. **ss -ti** cung cấp thông tin TCP chi tiết như RTT, retransmission, congestion window và trạng thái truyền dữ liệu cho các socket được chọn. Khi có nhiều kết nối, lọc theo endpoint hoặc port phù hợp để tránh đọc nhầm traffic khác.

Nếu cần thống kê NIC chi tiết:

~~~bash
ethtool -S eth0
ethtool eth0
~~~

Thay **eth0** bằng tên interface thật. Counter trong **ethtool -S** phụ thuộc driver và phần cứng; tên và ý nghĩa có thể khác nhau. Kiểm tra **rx_dropped**, **tx_dropped**, lỗi checksum, ring buffer và các counter liên quan theo tài liệu NIC.

### 6.3. Phân biệt vấn đề mạng với vấn đề máy chủ

- RX/TX tăng cao nhưng không có drop/retransmission: kiểm tra băng thông và giới hạn NIC/instance.
- Drop hoặc error tăng theo thời gian: kiểm tra NIC, driver, MTU, virtual switch và network path.
- TCP retransmission tăng cùng RTT: có thể mất gói hoặc nghẽn; cần đối chiếu cả hai đầu kết nối và thiết bị mạng.
- Socket receive queue tăng: ứng dụng phía máy chủ có thể không đọc dữ liệu đủ nhanh, hoặc process đang bận.
- Socket send queue tăng: dữ liệu gửi chưa được TCP/peer xác nhận đủ nhanh; kiểm tra đường truyền và client.
- Máy chủ MySQL có RTT thấp đến một số client nhưng cao đến client khác: điều tra tuyến mạng, vùng triển khai, VPN, NAT hoặc firewall riêng của client.

**ping** chỉ đo ICMP và có thể bị giới hạn hoặc ưu tiên khác TCP. Ping ổn định không chứng minh kết nối MySQL không mất gói. Hãy dùng TCP telemetry, socket và phép đo từ cả client lẫn server để kết luận.

### 6.4. Thu thập mạng trên Windows

~~~powershell
Get-NetAdapter |
  Select-Object Name, Status, LinkSpeed, InterfaceDescription

Get-NetAdapterStatistics

Get-Counter -Counter @(
  '\Network Interface(*)\Bytes Received/sec',
  '\Network Interface(*)\Bytes Sent/sec',
  '\Network Interface(*)\Packets Received Errors',
  '\Network Interface(*)\Packets Outbound Errors',
  '\TCPv4\Segments Retransmitted/sec',
  '\TCPv4\Connections Established'
) -SampleInterval 1 -MaxSamples 60
~~~

Chọn đúng interface đang mang traffic MySQL. Counter TCP là cấp hệ thống, có thể bao gồm các ứng dụng khác. Ghép với số liệu NIC, process, firewall và quan sát từ máy khách để xác định phạm vi ảnh hưởng.

## 7. Quan sát trong container và máy ảo

### 7.1. Cgroup giới hạn tài nguyên

Trong container, số CPU hoặc RAM nhìn thấy từ host không phản ánh quota mà process được phép dùng. Với cgroup v2, các file thường gặp gồm:

| File | Nội dung |
|---|---|
| **cpu.max** | Quota và chu kỳ CPU |
| **cpu.stat** | Thời gian CPU, số lần và thời gian bị throttling |
| **cpu.pressure** | Áp lực chờ CPU |
| **memory.current** | Bộ nhớ hiện đang dùng |
| **memory.max** | Giới hạn bộ nhớ |
| **memory.events** | Sự kiện vượt ngưỡng, reclaim hoặc OOM |
| **memory.pressure** | Áp lực bộ nhớ |
| **io.stat** | I/O theo thiết bị được cgroup tính |
| **io.pressure** | Áp lực chờ I/O |

Tìm cgroup của process:

~~~bash
cat /proc/"$PID"/cgroup
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/io.stat
~~~

Đường dẫn cgroup thực tế có thể nằm trong thư mục con; hãy ánh xạ dòng **0::...** trong **/proc/<pid>/cgroup** tới mount cgroup tương ứng. Không giả định mọi container đều dùng cgroup v2 hoặc mount tại cùng một đường dẫn.

Ví dụ **cpu.max** có hai số **50000 100000** nghĩa là quota 50.000 microsecond trong chu kỳ 100.000 microsecond, tương đương khoảng 0,5 CPU. Nếu **cpu.stat** cho thấy **nr_throttled** và **throttled_usec** tăng nhanh, process có thể bị giới hạn quota dù host còn CPU idle. **memory.max** bằng **max** thể hiện không đặt giới hạn cứng tại cgroup đó; giới hạn có thể tồn tại ở cấp cha hoặc orchestration.

Với Docker, **docker stats --no-stream** cung cấp ảnh chụp nhanh mức sử dụng container. Với Kubernetes, **kubectl top pod** cần metrics pipeline hoạt động và chỉ là một phần dữ liệu; kiểm tra resource requests/limits, throttling và node metrics khi cần.

### 7.2. Máy ảo và cloud

**%steal** tăng trên Linux guest gợi ý CPU bị hypervisor giữ lại. Storage và network của cloud thường có giới hạn theo loại instance, loại volume, kích thước volume, burst credit hoặc quota theo tài khoản. Khi latency tăng theo tải, so sánh số liệu guest với metric của nhà cung cấp: IOPS, throughput, queue, burst balance, throttled operations và network bandwidth.

Guest có thể thấy một thiết bị ảo duy nhất trong khi backend gồm nhiều tầng. Vì vậy, số liệu **iostat** trong guest cần được đối chiếu với metric volume cloud và host/hypervisor nếu nền tảng cung cấp. Một volume có **await** thấp trong guest không loại trừ độ trễ ở lớp mạng hoặc storage backend chưa được guest quan sát.

## 8. Ghép số liệu hệ điều hành với MySQL

Số liệu OS trả lời câu hỏi tài nguyên máy đang hoạt động thế nào. Số liệu MySQL giúp xác định hoạt động database nào diễn ra trong cùng khoảng thời gian. Hai nhóm phải được thu thập với timestamp tương thích.

Có thể chụp một số status cơ bản trước và sau cửa sổ đo:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Uptime',
  'Threads_connected',
  'Threads_running',
  'Connections',
  'Aborted_connects',
  'Queries',
  'Slow_queries',
  'Innodb_buffer_pool_reads',
  'Innodb_data_reads',
  'Innodb_data_writes',
  'Innodb_os_log_fsyncs'
);
~~~

Các biến status thường là counter tích lũy kể từ khi server khởi động hoặc được reset. Lấy hai snapshot và tính delta trong cùng cửa sổ, không so sánh trực tiếp tổng hiện tại giữa hai server có uptime khác nhau. Tên biến và mức độ sẵn có có thể thay đổi theo phiên bản; xác minh trên phiên bản đang chạy bằng **SHOW GLOBAL STATUS**.

Ví dụ cách ghép bằng chứng:

- **Threads_running** và throughput truy vấn tăng, CPU MySQL tăng, storage latency ổn định: xem execution plan, số hàng xử lý, join/sort, biểu thức và mức song song.
- **Innodb_buffer_pool_reads** tăng nhanh cùng read IOPS và **r_await**: workload có thể đang đọc từ storage nhiều hơn; kiểm tra working set, buffer pool, truy vấn và volume.
- Commit chậm cùng **w_await** hoặc flush latency tăng: điều tra redo log, binary log, fsync và backend lưu trữ.
- **Threads_connected** tăng nhưng CPU thấp, network RTT/retransmission cao: điều tra kết nối, client và đường truyền.
- MySQL process có CPU thấp nhưng container throttling tăng: điều tra quota và cấu hình resource limit.
- RAM host ổn định nhưng **memory.events** có **oom** hoặc **max** tăng: kiểm tra giới hạn cgroup và bộ nhớ cấp cho container.

Không nên dùng một status counter đơn lẻ để kết luận nguyên nhân. Hãy xem delta, tốc độ tăng, độ trễ quan sát được và loại workload trong cùng cửa sổ.

## 9. Quy trình điều tra khi MySQL chậm

Một quy trình ngắn, có thể lặp lại:

1. **Ghi nhận phạm vi**: hostname, instance, PID, service, container/VM, thời điểm và client bị ảnh hưởng.
2. **Xác định baseline**: so sánh CPU, RAM, I/O, network hiện tại với giờ bình thường có workload tương đương.
3. **Thu thập đồng bộ**: dùng cùng khoảng lấy mẫu cho **mpstat**, **vmstat**, **pidstat**, **iostat**, **sar** và status MySQL.
4. **Tìm điểm khác biệt**: chỉ số nào bắt đầu đổi cùng thời điểm latency truy vấn tăng?
5. **Khoanh vùng lớp**: host, process, cgroup, thiết bị, filesystem, NIC, client hay backend cloud.
6. **Kiểm tra giả thuyết**: thay đổi một yếu tố có kiểm soát hoặc đối chiếu với một instance không bị ảnh hưởng.
7. **Lưu bằng chứng**: giữ timestamp, command, output, cấu hình quota và trạng thái workload để người khác có thể tái hiện.

Ví dụ một lượt thu thập nhanh trên Linux:

~~~bash
PID=$(pgrep -xo mysqld)
date --iso-8601=seconds
hostnamectl --static
uptime
mpstat -P ALL 1 60
vmstat 1 60
pidstat -u -r -d -w -p "$PID" 1 60
iostat -xz 1 60
sar -n DEV,TCP,ETCP 1 60
~~~

Nếu MySQL chạy bằng **mariadbd**, thay lệnh tìm PID tương ứng. Nếu có nhiều instance, gán PID tường minh. Một số lệnh chạy tuần tự nên không có cùng thời điểm bắt đầu; với điều tra cần đồng bộ chặt, dùng công cụ giám sát tập trung hoặc chạy collector có timestamp chung. Lưu ý các lệnh có thể tạo output lớn; ghi vào thư mục chẩn đoán được phép và bảo vệ dữ liệu nhạy cảm.

### 9.1. Ví dụ diễn giải một sự cố

Giả sử thời gian phản hồi của ứng dụng tăng từ 30 ms lên 400 ms trong vài phút. Dữ liệu quan sát cho thấy:

- CPU tổng thể 45%, nhưng một lõi đạt gần 100%; **pidstat** cho thấy process MySQL dùng phần lớn CPU trên lõi đó.
- **MemAvailable** ổn định, không có swap-in/out đáng kể.
- **iostat** cho thấy **r_await** và **w_await** không đổi so với baseline.
- NIC không tăng drop hoặc retransmission; RTT giữa client và server ổn định.
- **Threads_running** và số truy vấn hoạt động tăng.

Bằng chứng hiện có nghiêng về nghẽn CPU trong workload MySQL. Bước tiếp theo là tìm nhóm truy vấn tăng, đọc execution plan, xem số hàng được đọc/xử lý, sort, temporary table và lock wait. Không nên nâng IOPS hoặc tăng RAM chỉ vì ứng dụng chậm khi các chỉ số đó không thay đổi.

Một tình huống khác: CPU idle còn cao, **MemAvailable** bình thường, nhưng **w_await** và hàng đợi thiết bị tăng đúng lúc commit chậm; status fsync cũng tăng nhanh. Khi đó cần tập trung vào volume chứa redo/binary log, giới hạn ghi, chính sách durability và workload ghi đồng thời. Phân tích này vẫn cần xác minh tại storage backend trước khi thay đổi cấu hình durability.

## 10. Những lỗi thường gặp khi đọc số liệu

- **Chỉ nhìn CPU trung bình**: bỏ lỡ một lõi bão hòa hoặc process khác chiếm tài nguyên.
- **Đồng nhất load average với CPU**: load có thể tăng do tác vụ chờ I/O.
- **Đồng nhất RAM đã dùng với RAM thiếu**: page cache có thể được thu hồi; xem **MemAvailable**, swap, pressure và OOM.
- **Dùng VIRT để kết luận RAM process**: VIRT là không gian địa chỉ ảo; xem RSS/working set và giới hạn cgroup.
- **Chỉ nhìn %util của đĩa**: cần xem latency, queue, IOPS, throughput và khả năng song song của thiết bị.
- **Lấy await làm p99**: **await** là trung bình; cần nguồn đo phân vị nếu điều tra tail latency.
- **Đo sai volume**: đường dẫn MySQL có thể qua LVM, RAID, network storage hoặc cloud volume.
- **Nhìn counter tích lũy như tốc độ**: lấy delta giữa hai timestamp để tính tốc độ và tỷ lệ lỗi.
- **Chỉ đo phía server**: độ trễ có thể nằm ở client, firewall, load balancer hoặc tuyến mạng.
- **Không tính quota container**: host còn CPU/RAM không chứng minh container còn tài nguyên.
- **So sánh các khoảng thời gian khác workload**: baseline phải tương đương về giờ, lưu lượng và loại truy vấn.
- **Chạy benchmark trên production không kiểm soát**: benchmark I/O có thể làm tăng latency cho dữ liệu thật và gây sự cố thứ cấp.

## 11. Checklist vận hành

Trước khi kết luận một sự cố tài nguyên, hãy xác nhận:

- [ ] Đúng hostname, PID, instance MySQL, container và service.
- [ ] Đã xác định mount/volume chứa data, redo log, binary log và temporary files.
- [ ] Có timestamp, múi giờ, thời lượng và chu kỳ lấy mẫu rõ ràng.
- [ ] CPU được xem theo từng lõi, process và quota cgroup.
- [ ] RAM được đánh giá bằng **MemAvailable**, swap, page fault, pressure và OOM.
- [ ] Storage có IOPS, throughput, read/write latency, queue và metric backend nếu có.
- [ ] Network có throughput, error/drop, retransmission, RTT và số liệu từ client.
- [ ] Status MySQL được lấy cùng cửa sổ và so sánh bằng delta.
- [ ] Các kết luận dựa trên thay đổi so với baseline, không dựa vào một ngưỡng chung.
- [ ] Output chẩn đoán được lưu ở nơi phù hợp, không chứa thông tin bí mật ngoài phạm vi cần thiết.

## 12. Bài thực hành

### Bài 1: Xác định đúng process và thiết bị

Trên một máy thử nghiệm có MySQL, xác định PID của **mysqld/mariadbd**, service tương ứng, đường dẫn **datadir**, filesystem và thiết bị block phía dưới. Ghi lại hostname, số CPU, RAM tổng và thời điểm đo.

**Kết quả cần có:** một bảng ánh xạ instance → PID → datadir → mount → thiết bị/volume.

### Bài 2: Lập baseline CPU và RAM

Chạy **mpstat -P ALL 1 60**, **vmstat 1 60** và **pidstat -u -r -p <PID> 1 60** trong một khoảng tải bình thường. Lưu output và xác định CPU lõi nóng nhất, run queue, **MemAvailable**, swap in/out và page fault.

**Kết quả cần có:** baseline CPU/RAM có timestamp và mô tả workload.

### Bài 3: Đo storage

Chạy **iostat -xz 1 60** và **pidstat -d -p <PID> 1 60**. Xác định thiết bị chứa data và log. So sánh read/write IOPS, throughput, **r_await**, **w_await**, **aqu-sz** và **%util**.

**Kết quả cần có:** giải thích được vì sao một thiết bị có **%util** cao chưa đủ chứng minh bão hòa, và vì sao cần xem latency cùng hàng đợi.

### Bài 4: Đo network

Chạy **ip -s link**, **sar -n DEV,TCP,ETCP 1 60**, **ss -s** và **nstat -az** trước/sau một cửa sổ tải. Tính delta counter drop/error/retransmission. Nếu có máy client thử nghiệm, đối chiếu RTT và counter ở hai đầu.

**Kết quả cần có:** phân biệt throughput tăng bình thường với dấu hiệu packet loss hoặc nghẽn.

### Bài 5: Phân tích một kịch bản

Giả lập hoặc dùng dữ liệu đã ghi nhận để phân tích một trong các tình huống: CPU một lõi bão hòa; RAM bị swap; disk write latency tăng; TCP retransmission tăng; hoặc container bị CPU throttling. Nêu giả thuyết, chỉ số ủng hộ, chỉ số chưa đủ bằng chứng và bước xác minh tiếp theo.

**Kết quả cần có:** một báo cáo ngắn gồm timeline, bằng chứng, kết luận có giới hạn và hành động tiếp theo.

## 13. Tiêu chí hoàn thành

Bạn hoàn thành bài học khi có thể xác định đúng process và volume của MySQL; thu thập CPU, RAM, I/O, disk latency và network theo một khoảng thời gian xác định; phân biệt số liệu host với process/container; giải thích được các chỉ số trung bình, counter tích lũy và quota; ghép số liệu OS với status MySQL; và trình bày một kết luận dựa trên baseline cùng bằng chứng từ nhiều lớp.

Việc đo lường chỉ giúp khoanh vùng. Sau khi xác định lớp tài nguyên bị giới hạn, cần tiếp tục kiểm tra truy vấn, transaction, cấu hình MySQL, hệ điều hành, storage backend hoặc network path tương ứng trước khi thay đổi production.

