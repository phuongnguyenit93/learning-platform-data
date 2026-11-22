# Tái hiện sự cố và thu thập thông tin JDK, hệ điều hành, tải trong Java 17

Khi ứng dụng Java gặp lỗi chỉ trên một máy, chỉ dưới tải cao hoặc chỉ xuất hiện sau vài giờ chạy, log lỗi thường chưa đủ để tìm nguyên nhân. Muốn chẩn đoán có căn cứ, cần **tái hiện sự cố theo một kịch bản có thể lặp lại** và thu thập dữ liệu của đúng tiến trình đang gặp vấn đề: bản JDK thực tế, tùy chọn JVM, hệ điều hành, giới hạn tài nguyên, đặc điểm tải và bản ghi Java Flight Recorder (JFR).

Quy trình tổng quát:

1. Mô tả triệu chứng và ghi lại điều kiện tái hiện.
2. Xác định đúng PID và JDK mà tiến trình đang dùng.
3. Thu thập thông tin OS, CPU, memory, container và tải ứng dụng.
4. Ghi timeline có timestamp thống nhất.
5. Thu JFR, thread dump, GC log hoặc dữ liệu bổ sung phù hợp.
6. Đóng gói bằng chứng để có thể phân tích và so sánh với lần tái hiện tiếp theo.

Bài này dùng công cụ có sẵn trong JDK 17 như `java`, `jcmd`, `jfr` và JFR. Các lệnh hệ điều hành được chia theo Linux và Windows. Mục tiêu là tạo bộ thông tin đủ để người khác hiểu môi trường, tải và thời điểm sự cố mà không phải đoán.

## 1. Tái hiện sự cố có nghĩa là gì?

Tái hiện sự cố là chạy lại ứng dụng với các điều kiện đủ gần để lỗi xuất hiện theo cách có thể quan sát và ghi nhận. Một báo cáo như “server đôi lúc chậm” chưa phải kịch bản tái hiện. Cần chuyển nó thành điều kiện có thể đo được.

Ví dụ, thay vì chỉ ghi:

```text
Ứng dụng thỉnh thoảng phản hồi chậm.
```

Hãy mô tả cụ thể:

```text
- Ứng dụng: billing-service, build 2.8.4.
- Runtime: Eclipse Temurin JDK 17.0.x, Linux x86_64.
- Sự cố: p99 latency tăng từ khoảng 180 ms lên hơn 4 s.
- Điều kiện: 350 request/second, khoảng 220 request đồng thời.
- Thời điểm: sau 12–18 phút chạy tải liên tục.
- Tác động: request đọc hóa đơn chậm; timeout database tăng.
- Cách chạy lại: cùng bộ dữ liệu kiểm thử, cùng cấu hình pool, cùng profile tải trong 20 phút.
- Dấu hiệu đi kèm: CPU process cao, số thread tăng, GC pause gần thời điểm latency tăng.
```

Mô tả này giúp người khác dựng lại tải và biết cần quan sát CPU, thread, GC hay database.

### 1.1. Phân biệt triệu chứng, nguyên nhân và điều kiện kích hoạt

| Khái niệm | Ví dụ |
|---|---|
| Triệu chứng | Request trả về chậm, process thoát, `OutOfMemoryError` |
| Điều kiện kích hoạt | Tải tăng, payload lớn, cache lạnh, một node cụ thể |
| Nguyên nhân giả thuyết | Thread pool cạn, lock contention, GC pressure, I/O chậm |
| Bằng chứng cần thu | JFR, thread dump, GC log, OS metrics, request rate |
| Kết quả tái hiện | Sự cố xuất hiện lại với cùng điều kiện, hoặc không xuất hiện sau một thay đổi có kiểm soát |

Đừng ghi giả thuyết thành kết luận khi chưa có bằng chứng. CPU cao có thể là nguyên nhân của latency, nhưng cũng có thể là hệ quả của retry storm hoặc workload bất thường.

### 1.2. Ghi rõ expected và actual behavior

Mỗi kịch bản nên có hai phần:

- **Expected:** hệ thống được kỳ vọng làm gì, trong giới hạn nào.
- **Actual:** điều gì đã xảy ra, ở thời điểm nào, trên node nào và với mức độ bao nhiêu.

Ví dụ:

```text
Expected:
  p95 latency < 500 ms ở tải 300 request/second.

Actual:
  p95 = 2.1 s, p99 = 6.8 s từ 10:42:15Z đến 10:45:30Z.
  Node app-03 có CPU process trung bình 92%.
  Request timeout tăng từ 0.1% lên 8%.
```

Dùng cùng đơn vị đo, cùng cửa sổ thời gian và cùng định nghĩa percentile trong các lần so sánh.

## 2. Tạo kịch bản tái hiện có thể lặp lại

Một kịch bản tốt kiểm soát những biến có ảnh hưởng đến kết quả. Không nhất thiết phải tái tạo toàn bộ production ngay từ đầu; nên bắt đầu với trường hợp nhỏ nhất vẫn làm lỗi xuất hiện.

### 2.1. Ghi lại đầu vào và trạng thái ban đầu

Thu thập:

- Payload hoặc tập dữ liệu đầu vào đã làm lỗi xuất hiện.
- Số lượng bản ghi, kích thước payload và phân bố dữ liệu.
- Cấu hình ứng dụng, thread pool, connection pool, cache và timeout.
- Trạng thái cache: cold hay warm.
- Trạng thái database, queue và dịch vụ phụ thuộc.
- Seed ngẫu nhiên nếu chương trình hoặc test dùng random.
- Thời điểm, timezone và locale nếu logic phụ thuộc lịch.
- Số lần chạy trước khi lỗi xuất hiện và thời gian từ lúc khởi động đến lúc lỗi.

Nếu dữ liệu chứa thông tin cá nhân, token hoặc bí mật, tạo bộ dữ liệu đã ẩn danh nhưng vẫn giữ đặc điểm kích thước và phân bố cần thiết. Không sao chép nguyên dữ liệu production vào môi trường chia sẻ chỉ để tái hiện.

### 2.2. Giữ cố định một yếu tố khi so sánh

Khi thử nghiệm một thay đổi, chỉ thay một yếu tố có liên quan trong mỗi lần chạy:

- Cùng build, đổi số worker.
- Cùng tải, đổi giới hạn heap.
- Cùng cấu hình JVM, đổi JDK patch version.
- Cùng dữ liệu, đổi cấu hình cache.

Nếu thay đồng thời JDK, heap, thread pool và database, kết quả tốt hơn hoặc xấu hơn không cho biết thay đổi nào tạo ra khác biệt.

### 2.3. Phân biệt lỗi tái hiện ổn định và lỗi gián đoạn

- **Lỗi tái hiện ổn định:** xuất hiện sau cùng một đầu vào hoặc chuỗi thao tác. Hãy giảm kịch bản thành test nhỏ, ghi stack trace và đầu vào tối thiểu.
- **Lỗi phụ thuộc tải:** chỉ xuất hiện khi concurrency, throughput hoặc queue depth đủ lớn. Hãy dùng công cụ tạo tải và ghi profile tải.
- **Lỗi phụ thuộc thời gian:** xuất hiện sau một thời gian chạy, sau chu kỳ batch, khi cache đầy hoặc token hết hạn. Cần ghi thời gian chạy và trạng thái tích lũy.
- **Lỗi môi trường:** chỉ xảy ra trên một OS, container, filesystem, kiến trúc CPU hoặc JDK build. Hãy so sánh môi trường thực tế thay vì chỉ so sánh source code.

### 2.4. Mô tả profile tải

Một profile tải không chỉ là “gửi 500 request”. Hãy ghi:

| Thuộc tính | Ví dụ |
|---|---|
| Warm-up | 2 phút ở 50 request/second |
| Steady load | 10 phút ở 250 request/second |
| Burst | Tăng lên 500 request/second trong 60 giây |
| Concurrency | 100, 200 hoặc 400 request đồng thời |
| Payload | Trung vị 4 KB, p95 80 KB |
| Mix thao tác | 70% read, 20% update, 10% report |
| Think time | 100 ms giữa thao tác của một virtual user |
| Đo lường | Throughput, p50/p95/p99 latency, error rate, queue depth |

Dùng cùng profile tải cho lần baseline và lần có sự cố. Nếu công cụ tạo tải tự trở thành nút nghẽn, kết quả đo không còn phản ánh riêng ứng dụng Java.

## 3. Xác định đúng tiến trình Java

Trước khi thu thập thông tin, phải xác định **PID của đúng tiến trình đang chạy ứng dụng**. Một máy có thể có nhiều JDK, nhiều service Java và nhiều tiến trình trong container.

### 3.1. Tìm tiến trình bằng jcmd

Trong thư mục bin của JDK:

```bash
jcmd -l
```

Lệnh liệt kê các tiến trình Java mà công cụ attach có thể nhận diện, thường gồm PID và tên class hoặc JAR chính.

Ví dụ:

```text
18420 com.example.billing.Main
20731 org.apache.catalina.startup.Bootstrap
```

Chọn PID của service cần chẩn đoán. Đừng nhầm PID của tiến trình tạo tải, agent hoặc một service khác.

Nếu `jcmd -l` không thấy process, có thể do process chạy dưới user khác, nằm trong container/PID namespace khác, attach mechanism bị vô hiệu hóa, thiếu quyền hoặc process đã kết thúc.

### 3.2. Kiểm tra PID trên Linux

```bash
ps -ef | grep '[j]ava'
ps -p 18420 -o pid,ppid,user,etime,%cpu,%mem,rss,vsz,args
```

`ps` cho biết user, thời gian chạy, CPU, bộ nhớ và command line. Command line có thể chứa password hoặc token truyền bằng tham số; hãy che dữ liệu nhạy cảm trước khi chia sẻ.

### 3.3. Kiểm tra PID trên Windows PowerShell

```powershell
$javaPid = 18420

Get-CimInstance Win32_Process -Filter "ProcessId = $javaPid" |
    Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine

Get-Process -Id $javaPid |
    Select-Object Id, ProcessName, CPU, WorkingSet64, VirtualMemorySize64,
                  Threads, Handles, StartTime
```

`WorkingSet64` là lượng bộ nhớ vật lý process đang sử dụng theo góc nhìn Windows; `VirtualMemorySize64` là không gian bộ nhớ ảo. Chúng không tương đương heap đã dùng trong JVM.

## 4. Thu thập đúng phiên bản JDK của process

Chạy `java -version` trong terminal chỉ cho biết Java launcher tìm được qua `PATH`. Nó có thể khác JDK đang chạy service, nhất là khi service được khởi động bởi systemd, Windows Service, container hoặc script riêng.

### 4.1. Kiểm tra launcher trong môi trường hiện tại

Linux/macOS:

```bash
command -v java
command -v jcmd
command -v jfr
java -version
javac -version
```

Windows PowerShell:

```powershell
Get-Command java, javac, jcmd, jfr -ErrorAction SilentlyContinue |
    Select-Object Name, Source

java -version
javac -version
```

Ghi lại cả đường dẫn executable. Hai máy cùng báo “Java 17” vẫn có thể khác vendor, patch release, build hoặc tùy chọn JVM.

### 4.2. Kiểm tra phiên bản từ process đang chạy

Dùng PID đã xác định:

```bash
jcmd 18420 VM.version
jcmd 18420 VM.command_line
jcmd 18420 VM.flags
```

Ý nghĩa:

- `VM.version`: phiên bản VM thực tế.
- `VM.command_line`: lệnh khởi chạy và đối số JVM/application mà VM nhận được.
- `VM.flags`: các cờ VM đang có hiệu lực, gồm nhiều cờ mặc định và cờ được đặt rõ ràng.

Đây là dữ liệu đáng tin cậy hơn việc chỉ hỏi shell đang dùng Java nào.

### 4.3. Thu thập system properties của JVM

```bash
jcmd 18420 VM.system_properties
```

Các property hữu ích để xác định môi trường gồm:

- `java.version`, `java.runtime.version`.
- `java.vendor`, `java.vm.name`, `java.vm.version`.
- `java.home`, `java.class.path`.
- `os.name`, `os.version`, `os.arch`.
- `user.timezone`, `file.encoding`.
- `user.dir`.

Tuy nhiên, `VM.system_properties` có thể chứa property do ứng dụng tự đặt, bao gồm URL nội bộ, đường dẫn, username hoặc bí mật. Không chia sẻ nguyên output khi chưa xem và che các giá trị nhạy cảm.

### 4.4. Thu thập thông tin từ bên trong ứng dụng

Nếu có thể thêm endpoint chẩn đoán hoặc log lúc khởi động, có thể ghi các thông tin chọn lọc:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;

public final class RuntimeInfo {
    public static void print() {
        RuntimeMXBean runtime =
                ManagementFactory.getRuntimeMXBean();

        System.out.println("java.version="
                + System.getProperty("java.version"));
        System.out.println("java.runtime.version="
                + System.getProperty("java.runtime.version"));
        System.out.println("java.vendor="
                + System.getProperty("java.vendor"));
        System.out.println("java.vm.name="
                + System.getProperty("java.vm.name"));
        System.out.println("java.vm.version="
                + System.getProperty("java.vm.version"));

        System.out.println("os.name="
                + System.getProperty("os.name"));
        System.out.println("os.version="
                + System.getProperty("os.version"));
        System.out.println("os.arch="
                + System.getProperty("os.arch"));

        System.out.println("processors="
                + Runtime.getRuntime().availableProcessors());
        System.out.println("jvm.startTime="
                + runtime.getStartTime());
        System.out.println("jvm.uptimeMillis="
                + runtime.getUptime());
        System.out.println("jvm.inputArguments="
                + runtime.getInputArguments());
    }
}
```

`RuntimeMXBean.getInputArguments()` hữu ích để ghi lại đối số JVM, nhưng có thể chứa giá trị nhạy cảm. Với endpoint công khai, chỉ trả property đã allow-list và không trả command line đầy đủ.

### 4.5. Đừng nhầm JDK version với source/target version

Một ứng dụng có thể được biên dịch bằng `--release 17` nhưng chạy trên một JDK 17 patch khác hoặc runtime khác nếu cấu hình triển khai cho phép. Khi báo cáo sự cố, nên ghi riêng:

- JDK/compiler dùng để build.
- JDK runtime thực tế của process.
- Phiên bản ứng dụng/build commit.
- JVM flags và module/class path có liên quan.

## 5. Thu thập thông tin hệ điều hành

JDK, JVM và OS cùng ảnh hưởng tới cách ứng dụng dùng CPU, memory, thread, file descriptor, network và filesystem. Chỉ ghi “Linux” hoặc “Windows” là chưa đủ.

### 5.1. Linux: thông tin hệ thống cơ bản

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
uname -a
cat /etc/os-release
lscpu
free -h
uptime
df -h
```

| Lệnh | Thông tin |
|---|---|
| `date -u` | Thời gian UTC để đồng bộ timeline |
| `uname -a` | Kernel, hostname, kiến trúc |
| `/etc/os-release` | Distribution và phiên bản |
| `lscpu` | CPU model, core, thread, kiến trúc |
| `free -h` | Memory tổng, đã dùng, khả dụng, swap |
| `uptime` | Uptime và load average |
| `df -h` | Dung lượng filesystem và mount point |

Nếu `lscpu` không có, có thể dùng `cat /proc/cpuinfo`; output dài hơn và cần lọc phù hợp.

### 5.2. Linux: quan sát tải trong một khoảng thời gian

```bash
vmstat 1 10
pidstat -p 18420 1 10
iostat -xz 1 10
```

- `vmstat` cung cấp CPU, run queue, memory, swap và I/O ở cấp hệ thống.
- `pidstat` cung cấp CPU và một số thống kê process theo chu kỳ.
- `iostat` cho biết hoạt động thiết bị lưu trữ, latency và utilization.

`pidstat` và `iostat` thường thuộc gói `sysstat`. Nếu môi trường không cài, ghi rõ công cụ không có thay vì âm thầm bỏ qua dữ liệu.

Để xem thống kê theo thread:

```bash
pidstat -t -p 18420 1 10
```

### 5.3. Linux: giới hạn process

```bash
cat /proc/18420/status
cat /proc/18420/limits
ls /proc/18420/fd | wc -l
```

`/proc/<pid>/status` cung cấp thông tin process như số thread, trạng thái, memory và bộ đếm. `/proc/<pid>/limits` hiển thị giới hạn tài nguyên như open files và process count. Số file descriptor mở có thể gợi ý rò rỉ socket hoặc file handle; đây chỉ là snapshot tại thời điểm thu thập.

### 5.4. Windows: thông tin hệ thống cơ bản

Trong PowerShell:

```powershell
Get-Date -Format o
Get-TimeZone

Get-ComputerInfo |
    Select-Object WindowsProductName, WindowsVersion,
                  OsBuildNumber, OsArchitecture, CsSystemType

Get-CimInstance Win32_Processor |
    Select-Object Name, NumberOfCores, NumberOfLogicalProcessors

Get-CimInstance Win32_OperatingSystem |
    Select-Object Caption, Version, BuildNumber,
                  TotalVisibleMemorySize, FreePhysicalMemory
```

Các lệnh này ghi lại thời gian, timezone, phiên bản/build Windows, kiến trúc, CPU và bộ nhớ hệ thống.

### 5.5. Windows: quan sát tải và process

```powershell
$javaPid = 18420

Get-Process -Id $javaPid |
    Select-Object Id, ProcessName, CPU, WorkingSet64,
                  VirtualMemorySize64, Threads, Handles, StartTime

Get-Counter -Counter @(
    '\Processor(_Total)\% Processor Time',
    '\Memory\Available MBytes'
) -SampleInterval 1 -MaxSamples 10
```

`Get-Process` cung cấp snapshot process. `Get-Counter` lấy mẫu bộ đếm hiệu năng theo thời gian. Tên counter có thể khác trên Windows đã bản địa hóa; nếu counter không tồn tại, ghi lại tên phù hợp trên máy đó.

### 5.6. Hệ điều hành và kiến trúc CPU

Cần ghi rõ kiến trúc CPU và số logical processor, kernel/OS build, bộ nhớ vật lý, swap/page file, filesystem và mount liên quan, giới hạn process và quyền của user chạy Java, môi trường ảo hóa hoặc container nếu có.

Không giả định hai máy “cùng 8 core” có hiệu năng giống nhau. CPU model, quota, clock behavior, virtualization và workload khác nhau có thể tạo ra kết quả khác biệt.

## 6. Thu thập giới hạn container và tài nguyên thực tế

Trong container, số CPU và memory mà JVM nhìn thấy có thể bị giới hạn bởi cgroup hoặc runtime. Thông tin phần cứng host không nhất thiết là tài nguyên được cấp cho container.

### 6.1. Docker và Kubernetes

Nếu có quyền truy cập Docker:

```bash
docker stats --no-stream <container>
docker inspect <container>
```

`docker stats` cho biết snapshot CPU, memory, network và block I/O. `docker inspect` có thể chứa cấu hình nhạy cảm; lọc output trước khi chia sẻ.

Với Kubernetes:

```bash
kubectl top pod -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
```

`kubectl top` phụ thuộc Metrics Server. `describe` cung cấp requests/limits, trạng thái restart, event và node placement. Không đưa token hoặc kubeconfig vào evidence bundle.

### 6.2. Cgroup v2 trên Linux

Trên nhiều hệ thống Linux hiện đại, cgroup v2 dùng các file như:

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
```

Ý nghĩa khái quát:

- `cpu.max`: quota và period CPU của cgroup.
- `cpu.stat`: thời gian CPU và thống kê throttling.
- `memory.max`: giới hạn memory.
- `memory.current`: memory hiện đang dùng.
- `memory.events`: số sự kiện như high/max/oom theo cgroup.

Đường dẫn cgroup thực tế có thể khác nếu process nằm trong cgroup con hoặc hệ thống dùng layout khác. Đọc `/proc/<pid>/cgroup` để xác định vị trí cgroup của process.

### 6.3. Cgroup v1 và giới hạn container

Cgroup v1 tách controller thành các hierarchy riêng. Đường dẫn thường nằm dưới `/sys/fs/cgroup/cpu`, `/sys/fs/cgroup/memory` hoặc mount tùy cấu hình. Không áp dụng tên file v2 như `cpu.max` cho v1.

Ghi rõ phiên bản cgroup và đường dẫn thực tế. Không so sánh số CPU host với quota container như thể chúng là cùng một đại lượng.

JVM 17 có khả năng nhận diện container resource limits trên nền tảng được hỗ trợ, nhưng cấu hình runtime, cgroup và môi trường triển khai vẫn cần được kiểm tra. Một process có thể nhìn thấy ít CPU hơn host, bị throttling dù host còn CPU rảnh hoặc bị OOM killer dừng do giới hạn container.

Khi điều tra memory pressure, ghi cả heap JVM lẫn memory container. Heap còn trống không có nghĩa container còn đủ memory cho metaspace, code cache, thread stack, direct buffer và native allocation.

## 7. Thu thập thông tin tải của ứng dụng

OS metrics cho biết máy đang bận đến đâu; application metrics cho biết người dùng và workload đang yêu cầu điều gì. Cần cả hai để phân biệt tải hợp lệ với bottleneck.

### 7.1. Throughput, concurrency và latency

Ghi ít nhất request/operation per second, số request đồng thời, p50/p95/p99 latency, error/timeout rate, số retry, kích thước request/response và tỷ lệ từng endpoint hoặc loại tác vụ.

Không chỉ dùng average latency. Average có thể vẫn thấp khi một tỷ lệ nhỏ request bị treo nhiều giây; p95/p99 thường làm lộ phần đuôi latency.

### 7.2. Queue và pool

| Thành phần | Số liệu nên thu |
|---|---|
| Executor | Active threads, pool size, queue size, rejected tasks |
| HTTP server | Active requests, connection count, pending requests |
| Database pool | Active/idle connections, waiters, acquisition timeout |
| Message broker | Consumer lag, queue depth, redelivery, processing rate |
| Cache | Hit/miss ratio, eviction, load latency |
| Scheduler | Task duration, lateness, số task pending |

Một thread pool đầy có thể khiến latency tăng dù CPU không cao, vì thread đang chờ database, network, lock hoặc queue.

### 7.3. CPU và memory của JVM

Thu thập CPU process và CPU hệ thống, heap used/committed/max, GC count và pause time, allocation rate nếu có, số thread và trạng thái thread, metaspace/direct buffer/native memory khi liên quan, class loading/unloading nếu có dấu hiệu tăng metaspace.

`Runtime.getRuntime().availableProcessors()` cho biết số processor JVM nhận diện; nó không phải phép đo CPU đang sử dụng. So sánh với quota container và OS metrics để hiểu giới hạn thực tế.

### 7.4. Ghi rõ cửa sổ đo và nguồn metric

Một metric “CPU = 90%” không đủ nếu không biết CPU của process hay toàn máy, đo trong bao lâu, trung bình hay peak, có bao nhiêu core được cấp và có CPU throttling không. Gắn timestamp UTC và interval vào mỗi file metric. Dùng cùng interval trong baseline và reproduction để so sánh.

## 8. Dùng jcmd để thu thập trạng thái JVM

`jcmd` là công cụ chẩn đoán đi kèm JDK. Nó gửi diagnostic command tới JVM đang chạy. Dùng JDK tools cùng môi trường và quyền user phù hợp với process đích.

### 8.1. Xác nhận phiên bản và lệnh khởi chạy

```bash
jcmd 18420 VM.version
jcmd 18420 VM.command_line
jcmd 18420 VM.flags
jcmd 18420 VM.system_properties
```

`VM.system_properties` có thể lộ thông tin bí mật. Chỉ lưu bản đã rà soát trong gói chia sẻ.

### 8.2. Lấy thread dump

```bash
jcmd 18420 Thread.print -l
```

Thread dump cho biết stack trace và trạng thái thread tại một thời điểm. Nó hữu ích khi nhiều thread BLOCKED trên cùng monitor, thread pool không còn worker rảnh, nhiều thread WAITING/PARKED, có dấu hiệu deadlock hoặc thread bị kẹt trong I/O/dịch vụ ngoài.

Một thread dump là snapshot, không phải timeline. Với lỗi intermittent, có thể thu vài snapshot cách nhau một khoảng ngắn và so sánh stack/state; JFR bổ sung dữ liệu theo thời gian.

### 8.3. Xem heap summary

```bash
jcmd 18420 GC.heap_info
```

Lệnh này cung cấp thông tin tổng quan heap tại thời điểm lấy mẫu. Nó không thay thế heap profiler và không cho biết đầy đủ object nào đang giữ memory.

`GC.class_histogram` có thể hữu ích khi cần biết loại object nào chiếm nhiều heap, nhưng có thể tốn thời gian hoặc gây ảnh hưởng do phải quan sát heap ở safepoint. Chỉ dùng khi có lý do và đã cân nhắc tác động trên hệ thống đang phục vụ tải.

Không tự động tạo heap dump trong mọi incident. Heap dump có thể rất lớn, tạo I/O đáng kể và chứa dữ liệu nhạy cảm của ứng dụng.

### 8.4. Native Memory Tracking

Nếu JVM được khởi chạy với Native Memory Tracking, có thể lấy summary:

```bash
jcmd 18420 VM.native_memory summary
```

NMT phải được bật từ lúc khởi động, ví dụ:

```bash
-XX:NativeMemoryTracking=summary
```

Không thể bật NMT đầy đủ hồi tố cho process đang chạy mà chưa khởi động với tùy chọn này. NMT có overhead; chỉ bật khi cần điều tra native memory và có kế hoạch đo tác động.

## 9. Java Flight Recorder trong JDK 17

**Java Flight Recorder (JFR)** là hệ thống ghi sự kiện hiệu năng và runtime của JVM. Nó thu các sự kiện có timestamp như CPU sampling, GC, thread scheduling, lock contention, allocation sampling và I/O.

JFR được tích hợp trong JDK 17, có thể dùng cho chẩn đoán production với cấu hình phù hợp. Không cần bật cờ mở khóa thương mại cũ để dùng JFR trong Java 17.

JFR có hai phần chính: **Recording** là tập sự kiện được ghi trong một khoảng thời gian; **Event** là sự kiện có timestamp, trường dữ liệu và đôi khi có stack trace.

JFR có thể giúp trả lời CPU được dùng bởi thread/code path nào, GC xảy ra lúc nào, thread bị park hoặc chờ monitor ở đâu, allocation pressure có tăng bất thường không và I/O file/socket có độ trễ bất thường không.

### 9.1. JFR khác log ứng dụng

| Log ứng dụng | JFR |
|---|---|
| Ghi sự kiện nghiệp vụ do ứng dụng chủ động log | Ghi sự kiện JVM và runtime |
| Thường có request ID, business context nếu ứng dụng thêm | Có timestamp, thread, stack và runtime metrics tùy event |
| Hữu ích để biết người dùng thực hiện thao tác gì | Hữu ích để biết JVM đang làm gì trong cùng khoảng thời gian |
| Có thể thiếu nếu code không ghi | Không tự hiểu ý nghĩa nghiệp vụ của request |

Hai nguồn dữ liệu bổ sung cho nhau. Giữ request ID/correlation ID trong application logs và ghi timestamp UTC để đối chiếu với JFR.

### 9.2. default và profile settings

JFR cung cấp các cấu hình recording phổ biến:

- `default`: cấu hình có overhead thấp hơn, phù hợp cho ghi nhận dài hơn hoặc quan sát liên tục.
- `profile`: thu nhiều chi tiết hơn, hữu ích khi điều tra trong khoảng thời gian ngắn; có thể tạo thêm overhead và dữ liệu lớn hơn.

Không nên mặc định dùng profile trong mọi process mãi mãi. Chọn settings theo câu hỏi cần trả lời, thời lượng ghi và ngân sách overhead.

## 10. Bắt đầu JFR từ JVM đang chạy bằng jcmd

Đây là cách thuận tiện khi sự cố đã xuất hiện hoặc cần bật recording trên process đang hoạt động.

### 10.1. Kiểm tra recording hiện có

```bash
jcmd 18420 JFR.check
```

Lệnh hiển thị các recording đang hoạt động và trạng thái của chúng.

### 10.2. Bắt đầu recording ngắn

```bash
jcmd 18420 JFR.start name=incident settings=profile duration=10m filename=/var/tmp/incident.jfr
```

| Tham số | Ý nghĩa |
|---|---|
| `name=incident` | Tên recording để tham chiếu bằng jcmd |
| `settings=profile` | Dùng cấu hình profile của JFR |
| `duration=10m` | Tự dừng recording sau 10 phút |
| `filename=...` | Đường dẫn file ghi kết quả khi recording kết thúc |

Đường dẫn phải ghi được bởi user chạy JVM. Trên Windows, dùng đường dẫn phù hợp, ví dụ `C:/temp/incident.jfr`.

### 10.3. Kiểm tra recording đã bắt đầu

```bash
jcmd 18420 JFR.check
```

Nếu recording không xuất hiện, kiểm tra thông báo từ jcmd, quyền attach, dung lượng đĩa và đường dẫn file.

### 10.4. Dump trước khi recording tự kết thúc

Nếu recording vẫn đang chạy và muốn lấy snapshot tại thời điểm incident:

```bash
jcmd 18420 JFR.dump name=incident filename=/var/tmp/incident-now.jfr
```

Dump tạo file recording tại thời điểm gọi; recording gốc vẫn có thể tiếp tục chạy.

Sau khi đã thu đủ dữ liệu, dừng recording:

```bash
jcmd 18420 JFR.stop name=incident
```

Nếu recording được cấu hình tự dừng theo duration, không cần chờ hết thời gian nếu đã có đủ dữ liệu; dừng có chủ đích giúp giảm thời gian thu thập và kích thước file.

### 10.5. Recording dài hạn với rolling data

Đối với process cần quan sát lâu hơn, có thể dùng disk recording với giới hạn tuổi và kích thước:

```bash
jcmd 18420 JFR.start name=continuous settings=default disk=true maxage=2h maxsize=512m dumponexit=true
```

Khi sự cố xảy ra:

```bash
jcmd 18420 JFR.dump name=continuous filename=/var/tmp/incident-window.jfr
```

Recording liên tục vẫn chạy sau khi dump. Khi không còn cần thiết:

```bash
jcmd 18420 JFR.stop name=continuous
```

`maxage` và `maxsize` giới hạn tuổi và kích thước dữ liệu recording giữ lại; hữu ích để tránh file tăng vô hạn. Hãy chọn giới hạn phù hợp với tốc độ phát sinh event và dung lượng ổ đĩa.

## 11. Bắt đầu JFR ngay khi JVM khởi động

Nếu sự cố xuất hiện trong giai đoạn startup hoặc trước khi operator có thể attach, cấu hình recording qua JVM argument.

```bash
java \
  -XX:StartFlightRecording=name=startup,settings=profile,duration=10m,filename=/var/tmp/startup.jfr \
  -jar application.jar
```

JFR bắt đầu từ giai đoạn khởi động VM theo cấu hình. Cách này phù hợp với lỗi xảy ra sớm, startup latency, class loading hoặc race condition chỉ xuất hiện khi khởi tạo.

Có thể dùng settings mặc định nếu muốn giảm chi tiết và overhead:

```bash
java -XX:StartFlightRecording=name=baseline,settings=default,dumponexit=true \
     -jar application.jar
```

Với `dumponexit=true`, recording được dump khi JVM thoát bình thường. Đừng dựa vào nó như bảo đảm file sẽ được tạo nếu process bị kill cưỡng bức hoặc máy mất điện.

### 11.1. Chọn cách ghi theo loại sự cố

| Sự cố | Cách ghi phù hợp |
|---|---|
| Lỗi xảy ra ngay khi startup | `-XX:StartFlightRecording` |
| Lỗi đã xuất hiện trên process đang chạy | `jcmd JFR.start` |
| Lỗi hiếm, cần lưu cửa sổ gần đây | Continuous disk recording với `maxage`/`maxsize` |
| Chỉ cần điều tra trong 5–10 phút | Recording ngắn với `settings=profile` |
| Cần baseline ít chi tiết trong thời gian dài | `settings=default` |

### 11.2. Không restart trước khi thu bằng chứng nếu chưa cần

Restart có thể làm mất thread state tại thời điểm kẹt, heap state, recording, queue/connection state và bối cảnh trước khi sự cố xảy ra.

Nếu process vẫn an toàn để quan sát, hãy thu snapshot cần thiết trước khi restart. Nếu hệ thống đang gây tác động nghiêm trọng hoặc có rủi ro dữ liệu, ưu tiên quy trình vận hành và phục hồi đã được tổ chức phê duyệt.

## 12. Đọc và phân tích file JFR

Sau khi có file `.jfr`, JDK cung cấp lệnh `jfr` để xem summary và in event.

### 12.1. Xem tổng quan recording

```bash
jfr summary /var/tmp/incident.jfr
```

Summary cho biết thời gian bắt đầu/kết thúc, tổng thời lượng và số lượng event theo loại. Dùng summary để xác nhận file có dữ liệu và biết recording bao phủ khoảng thời gian nào.

### 12.2. In event liên quan CPU và GC

```bash
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad,jdk.ExecutionSample,jdk.GarbageCollection,jdk.GCHeapSummary /var/tmp/incident.jfr
```

Các event có thể giúp xác định CPU load, stack được lấy mẫu, thời gian GC và heap summary quanh GC. Event cụ thể có mặt hay không phụ thuộc settings và runtime. Nếu không thấy event, kiểm tra recording configuration thay vì kết luận rằng sự kiện không xảy ra.

### 12.3. Xem stack của execution samples

```bash
jfr print --events jdk.ExecutionSample --stack-depth 64 /var/tmp/incident.jfr
```

Execution samples là dữ liệu lấy mẫu, không phải trace mọi lời gọi method. Một method xuất hiện nhiều trong sample có thể đang tiêu tốn CPU, nhưng cần đọc stack context và đối chiếu với tải trước khi kết luận.

### 12.4. Xem lock, thread và I/O

```bash
jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark,jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite /var/tmp/incident.jfr
```

Các event này hữu ích khi ứng dụng không dùng CPU nhiều nhưng vẫn chậm:

- `jdk.JavaMonitorEnter`: thời gian chờ monitor contention.
- `jdk.ThreadPark`: thread park, thường liên quan lock, synchronizer hoặc executor.
- `jdk.SocketRead`/`jdk.SocketWrite`: hoạt động socket.
- `jdk.FileRead`/`jdk.FileWrite`: hoạt động file I/O.

Không phải mọi lần đọc/ghi đều được ghi trong mọi cấu hình. Event có threshold và setting riêng; kiểm tra recording configuration nếu dữ liệu cần thiết không xuất hiện.

### 12.5. Xem allocation sample

```bash
jfr print --events jdk.ObjectAllocationSample /var/tmp/incident.jfr
```

Allocation sample có thể gợi ý code path tạo nhiều object. Đây là dữ liệu lấy mẫu, không phải danh sách chính xác mọi allocation. Dùng nó để định hướng điều tra và đối chiếu với heap/GC metrics.

### 12.6. Dùng Java Mission Control

Java Mission Control (JMC) có thể mở file JFR và trình bày dữ liệu qua các trang như JVM overview, threads, memory, garbage collections, locks và I/O. Đây là công cụ phân tích trực quan; file gốc vẫn là recording JFR.

Khi chia sẻ kết quả, lưu cả file recording và ghi rõ JDK/JMC version được dùng để phân tích. Nếu người nhận không có JMC, `jfr summary` và `jfr print` vẫn giúp trích xuất thông tin dạng text.

## 13. Thu GC log và kết hợp với JFR

JFR ghi nhiều sự kiện GC, nhưng GC log vẫn hữu ích khi cần chuỗi log chi tiết và dễ đưa vào hệ thống log tập trung.

Java 17 dùng unified logging:

```bash
-Xlog:gc*,safepoint:file=/var/log/app/gc.log:time,uptime,level,tags:filecount=5,filesize=20m
```

Ý nghĩa:

- `gc*`: nhóm log liên quan garbage collection.
- `safepoint`: thông tin safepoint.
- `time,uptime,level,tags`: các trường được ghi trong log.
- `filecount=5`: giữ tối đa 5 file xoay vòng.
- `filesize=20m`: kích thước mục tiêu mỗi file trước khi rotate.

Đặt argument này trong danh sách JVM options của process. Xác nhận đường dẫn log tồn tại và user chạy JVM có quyền ghi.

### 13.1. Đọc GC log cùng timeline

Đối chiếu thời điểm latency tăng, GC pause bắt đầu/kết thúc, heap occupancy trước/sau GC, tần suất GC, safepoint duration và allocation rate.

Một lần GC dài trùng thời điểm latency tăng là bằng chứng đáng chú ý, nhưng cần xem toàn bộ chuỗi và tải. Không phải mọi latency spike đều do GC.

### 13.2. Heap và native memory là hai phạm vi khác nhau

Heap chỉ là một phần memory của process. Tổng memory còn có thể gồm metaspace, code cache, thread stacks, direct buffers, JNI/native allocations, JIT/compiler và memory-mapped files.

Nếu container bị OOM trong khi heap chưa đạt `-Xmx`, hãy xem OS/cgroup memory và native memory thay vì chỉ tăng heap.

## 14. Chọn bằng chứng theo triệu chứng

Không phải incident nào cũng cần mọi loại recording. Bắt đầu từ triệu chứng và chọn dữ liệu phù hợp.

| Triệu chứng | Dữ liệu nên ưu tiên | Câu hỏi cần trả lời |
|---|---|---|
| CPU process cao | JFR execution samples, thread CPU, OS per-process CPU | Thread/code path nào dùng CPU? |
| CPU thấp nhưng latency cao | Thread dump, ThreadPark, JavaMonitorEnter, socket/file I/O | Thread đang chờ lock, network hay disk? |
| Latency tăng theo thời gian | JFR, GC log, heap/queue metrics | Có GC pressure, queue buildup hay memory leak? |
| OOM heap | JFR allocation, heap metrics, heap dump nếu cần | Object nào tăng và ai giữ reference? |
| Container bị OOM kill | Cgroup memory events, container stats, heap/native metrics | Tổng process memory vượt limit ở đâu? |
| Thread count tăng | JFR thread events, thread dump, pool metrics | Thread được tạo ở đâu và vì sao không kết thúc? |
| Startup chậm | Startup JFR, class loading, application startup logs | Thời gian nằm ở class loading, I/O hay initialization? |
| Database timeout | Application metrics, pool wait, socket events, thread dump | Chờ connection, query hay network? |
| File I/O chậm | JFR file events, iostat, filesystem metrics | Độ trễ ở JVM, filesystem hay thiết bị? |

Heap dump có thể cần thiết khi điều tra retained objects hoặc leak, nhưng thường có kích thước lớn và ảnh hưởng vận hành. Chỉ tạo khi có kế hoạch lưu trữ, phân tích và bảo vệ dữ liệu.

## 15. Tạo timeline thống nhất

Để ghép JFR, application log, GC log và OS metrics, timestamp phải có thể đối chiếu.

### 15.1. Dùng UTC cho mốc sự cố

Ghi thời gian theo ISO-8601 UTC:

```text
2026-11-15T10:42:15.123Z
```

Nếu log ứng dụng dùng local time, ghi kèm timezone/offset và xác nhận đồng hồ host được đồng bộ. Không so sánh hai timestamp local từ hai máy mà bỏ qua timezone hoặc clock skew.

### 15.2. Ghi marker ở đầu và cuối kịch bản

```text
10:30:00Z - service restarted
10:32:00Z - warm-up begins
10:34:00Z - steady load begins (250 req/s)
10:42:15Z - p99 latency exceeds threshold
10:42:20Z - JFR dump requested
10:43:00Z - thread dump captured
10:45:00Z - load stopped
10:46:00Z - JFR recording stopped
```

Marker giúp người phân tích tìm đúng khoảng thời gian trong recording. Nếu có thể, log incident ID/correlation ID chung ở application log và hệ thống theo dõi.

### 15.3. Ghi thời điểm lấy snapshot

Ví dụ trên Linux:

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
jcmd 18420 Thread.print -l > thread-18420.txt
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

Trên PowerShell:

```powershell
Get-Date -Format o
jcmd 18420 Thread.print -l | Out-File -Encoding utf8 thread-18420.txt
Get-Date -Format o
```

Ghi lại command, PID, host/container và user thực hiện. Một thread dump không có timestamp và PID rất khó ghép với JFR.

## 16. Đóng gói evidence bundle

Một gói thông tin có cấu trúc giúp người khác phân tích mà không cần hỏi lại từng chi tiết.

Ví dụ:

```text
incident-2026-11-15/
├── README.md
├── reproduction/
│   ├── scenario.md
│   ├── input-sample-redacted.json
│   └── load-profile.csv
├── jdk/
│   ├── java-version.txt
│   ├── vm-version.txt
│   ├── vm-command-line-redacted.txt
│   └── vm-flags.txt
├── os/
│   ├── os-release.txt
│   ├── cpu-memory.txt
│   ├── process-snapshot.txt
│   └── cgroup-limits.txt
├── application/
│   ├── application.log
│   └── metrics.csv
├── jfr/
│   ├── incident.jfr
│   └── jfr-summary.txt
├── gc/
│   └── gc.log
└── threads/
    ├── thread-before.txt
    └── thread-during.txt
```

Không phải incident nào cũng cần đủ mọi file. Chỉ giữ bằng chứng liên quan và ghi rõ file nào không thu được.

### 16.1. README của evidence bundle

Có thể dùng mẫu:

```text
Incident ID:
Service / version / commit:
Host / container / pod:
PID:
JDK vendor / runtime version:
OS / kernel / architecture:
JVM flags:
Heap settings:
Container CPU / memory limits:
Start time (UTC):
Incident window (UTC):
Reproduction steps:
Load profile:
Expected behavior:
Actual behavior:
Error rate / p95 / p99:
Files collected:
Known limitations:
Sensitive fields redacted:
```

README là mục lục và ngữ cảnh cho dữ liệu thô. Không nhúng token, password hoặc secret vào README.

### 16.2. Kiểm tra dung lượng và checksum

Linux:

```bash
ls -lh incident.jfr
sha256sum incident.jfr
```

Windows PowerShell:

```powershell
Get-Item .\incident.jfr |
    Select-Object Name, Length, LastWriteTimeUtc

Get-FileHash .\incident.jfr -Algorithm SHA256
```

Checksum giúp xác nhận tính toàn vẹn của file khi chuyển qua hệ thống lưu trữ; nó không làm nội dung file được mã hóa hoặc bảo mật.

## 17. Lỗi thường gặp khi thu JFR và chẩn đoán

### 17.1. jcmd không attach được

Nguyên nhân có thể: chạy dưới user khác, PID không thuộc namespace mà lệnh đang thấy, process đã kết thúc, attach mechanism bị vô hiệu hóa hoặc dùng công cụ từ môi trường không tương thích.

Cách xử lý:

1. Xác nhận PID và user.
2. Chạy `jcmd -l` trong cùng host/container.
3. Dùng JDK tools phù hợp với runtime của process.
4. Nếu attach không khả thi, cân nhắc startup recording qua JVM option ở lần khởi động kế tiếp.

Không cố bật attach mechanism bằng cách thay đổi tùy tiện trên production đang chạy.

### 17.2. Không tìm thấy file JFR

Kiểm tra đường dẫn tuyệt đối hay tương đối, quyền ghi của user chạy JVM, dung lượng đĩa, trạng thái recording và thông báo của lệnh `JFR.dump`/`JFR.stop`. Dùng đường dẫn tuyệt đối để tránh nhầm working directory của process với thư mục terminal hiện tại.

### 17.3. File JFR có nhưng thiếu event cần thiết

Có thể recording dùng settings không bật event mong muốn hoặc event có threshold. Kiểm tra cấu hình recording, dùng profile settings trong cửa sổ có kiểm soát hoặc tạo cấu hình tùy chỉnh dựa trên JFR configuration.

Đừng kết luận “không có lock contention” chỉ vì không thấy event trong recording không bật event phù hợp.

### 17.4. Recording làm tăng overhead

Nếu recording quá dài, settings quá chi tiết hoặc stack trace được thu với tần suất cao, có thể tăng CPU, I/O và dung lượng.

Cách giảm tác động:

- Dùng `default` cho quan sát dài hạn.
- Dùng `profile` trong cửa sổ điều tra ngắn.
- Giới hạn `duration`, `maxage`, `maxsize`.
- Chỉ bật event chi tiết khi câu hỏi chẩn đoán cần nó.
- Theo dõi CPU và disk trong lúc recording.

Không có một con số overhead đúng cho mọi ứng dụng; phụ thuộc event, tải và phần cứng. Đo trên môi trường gần production nếu cần đánh giá tác động.

### 17.5. JFR hoặc log chứa dữ liệu nhạy cảm

Recording và diagnostic output có thể chứa stack trace, tên class nội bộ, đường dẫn, hostname, endpoint, thông tin socket/I/O, tên thread và property/command line do ứng dụng đặt.

Giới hạn quyền truy cập, lưu trữ an toàn, đặt thời hạn giữ dữ liệu và redact trước khi gửi ra ngoài. Không đăng file JFR production lên nơi công khai.

## 18. Ví dụ quy trình: điều tra latency tăng dưới tải

Giả sử một Java 17 service có latency tăng sau vài phút tải liên tục.

### Bước 1 — Ghi baseline

```text
JDK: vendor + runtime version + VM version
OS: distribution/build + kernel + architecture
CPU: model + logical processors
Memory: host/container limit
JVM: command line + flags + Xms/Xmx
Application: build + config + dependency versions
Load: request rate + concurrency + payload distribution
Metrics: p50/p95/p99 + error rate + queue depth
```

### Bước 2 — Khởi động với profile tải cố định

```text
Warm-up: 2 phút, 50 req/s
Steady: 15 phút, 250 req/s
Burst: 1 phút, 400 req/s
Payload: cùng bộ dữ liệu đã ẩn danh
```

### Bước 3 — Khi latency vượt ngưỡng, đánh dấu timestamp

Ghi incident marker bằng UTC và ghi lại request rate, concurrency, p95/p99, error rate.

### Bước 4 — Thu JFR

Nếu chưa có recording:

```bash
jcmd 18420 JFR.start name=latency-incident settings=profile duration=10m filename=/var/tmp/latency-incident.jfr
```

Nếu recording liên tục đã chạy, dump cửa sổ hiện tại:

```bash
jcmd 18420 JFR.dump name=continuous filename=/var/tmp/latency-window.jfr
```

### Bước 5 — Thu thread dump và JVM snapshot

```bash
jcmd 18420 Thread.print -l > /var/tmp/threads-1.txt
jcmd 18420 GC.heap_info > /var/tmp/heap-info.txt
jcmd 18420 VM.flags > /var/tmp/vm-flags.txt
```

Nếu latency tiếp tục tăng, có thể lấy thêm một thread dump sau vài giây để so sánh thread có đang chờ cùng một vị trí hay không.

### Bước 6 — Thu OS và container load

Linux:

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
uptime
vmstat 1 10
pidstat -p 18420 1 10
free -h
```

Container: ghi CPU/memory quota, throttling và memory events theo cgroup/runtime đang dùng.

### Bước 7 — Phân tích JFR

```bash
jfr summary /var/tmp/latency-incident.jfr

jfr print --events jdk.ExecutionSample,jdk.CPULoad,jdk.GarbageCollection,jdk.GCHeapSummary /var/tmp/latency-incident.jfr

jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark,jdk.SocketRead,jdk.SocketWrite /var/tmp/latency-incident.jfr
```

Đối chiếu timestamp với application metrics:

- Execution samples tập trung vào một đoạn code CPU-bound?
- Thread chủ yếu park hoặc chờ monitor?
- Socket read/write có duration tăng?
- GC pause có trùng latency spike?
- Queue depth có tăng trước khi latency tăng?

### Bước 8 — Tạo giả thuyết và tái hiện có kiểm soát

Nếu JFR cho thấy nhiều thread chờ monitor cùng một lock:

1. Xác định lock owner và stack trace.
2. Kiểm tra thread dump tại cùng thời điểm.
3. Dựng kịch bản concurrency tương tự.
4. Thay một yếu tố như critical section hoặc số worker.
5. So sánh latency và JFR trước/sau.

Không sửa code chỉ dựa vào một event riêng lẻ. Hãy tìm bằng chứng liên kết giữa tải, thread state, stack và triệu chứng.

## 19. Mẫu lệnh thu thập nhanh

Các lệnh sau là điểm bắt đầu cho một incident. Thay PID, đường dẫn và thời lượng theo môi trường.

### 19.1. Linux: JDK và JVM

```bash
PID=18420

date -u +"%Y-%m-%dT%H:%M:%SZ"
jcmd -l
jcmd "$PID" VM.version
jcmd "$PID" VM.command_line
jcmd "$PID" VM.flags
jcmd "$PID" VM.system_properties
```

Rà soát output system properties và command line để loại bỏ secret trước khi chia sẻ.

### 19.2. Linux: OS và tải

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
uname -a
cat /etc/os-release
lscpu
free -h
uptime
vmstat 1 10
pidstat -p 18420 1 10
df -h
cat /proc/18420/status
cat /proc/18420/limits
```

Nếu cần disk I/O và công cụ có sẵn:

```bash
iostat -xz 1 10
```

### 19.3. Linux: JFR và thread dump

```bash
jcmd 18420 JFR.check
jcmd 18420 JFR.start name=incident settings=profile duration=10m filename=/var/tmp/incident.jfr
jcmd 18420 Thread.print -l > /var/tmp/thread-dump.txt
```

Sau khi recording kết thúc:

```bash
jfr summary /var/tmp/incident.jfr
```

### 19.4. Windows PowerShell: JDK và OS

```powershell
$javaPid = 18420

Get-Date -Format o
Get-Command java, jcmd, jfr | Select-Object Name, Source
java -version

jcmd $javaPid VM.version
jcmd $javaPid VM.command_line
jcmd $javaPid VM.flags

Get-ComputerInfo |
    Select-Object WindowsProductName, WindowsVersion,
                  OsBuildNumber, OsArchitecture

Get-Process -Id $javaPid |
    Select-Object Id, CPU, WorkingSet64, Threads, Handles, StartTime
```

`VM.command_line` và một số property có thể chứa secret. Xem lại output trước khi gửi.

### 19.5. Windows PowerShell: JFR và thread dump

```powershell
$javaPid = 18420

jcmd $javaPid JFR.check
jcmd $javaPid JFR.start name=incident settings=profile duration=10m filename=C:/temp/incident.jfr
jcmd $javaPid Thread.print -l |
    Out-File -Encoding utf8 C:/temp/thread-dump.txt

jfr summary C:/temp/incident.jfr
```

Đảm bảo thư mục `C:/temp` tồn tại và user chạy JVM có quyền ghi file. Nếu process chạy trong service account, quyền filesystem của service account mới là điều quyết định.

## 20. Những điều không nên làm khi tái hiện và thu thập dữ liệu

- Không thay nhiều biến cấu hình trong cùng một lần chạy rồi kết luận nguyên nhân.
- Không chỉ ghi `java -version` của shell mà bỏ qua JDK thực tế của process.
- Không dùng một snapshot CPU hoặc heap để kết luận về cả khoảng thời gian dài.
- Không chỉ nhìn average latency khi vấn đề nằm ở p95/p99.
- Không giả định số CPU host bằng số CPU JVM/container được phép dùng.
- Không dùng `readAllBytes` hoặc heap dump lớn trên process đang chịu áp lực mà chưa đánh giá tác động.
- Không bật event JFR chi tiết vô thời hạn nếu chưa biết overhead và dung lượng.
- Không restart process trước khi thu snapshot cần thiết nếu việc quan sát vẫn an toàn.
- Không gửi nguyên command line, system properties, logs, heap dump hoặc JFR ra ngoài khi chưa rà soát dữ liệu nhạy cảm.
- Không coi JFR là bằng chứng duy nhất; ghép nó với application logs, metrics và OS data.

## 21. Ghi nhớ

- Tái hiện sự cố cần có **đầu vào, điều kiện, tải, expected behavior và actual behavior** rõ ràng.
- Xác định đúng PID và runtime của process; `java -version` trong shell có thể không phải JDK đang chạy service.
- Thu thập JDK vendor/build, VM version, command line, flags và system properties có chọn lọc.
- Ghi OS/kernel, CPU, memory, process limits, filesystem và container quotas.
- Đo tải bằng throughput, concurrency, p50/p95/p99, error rate, queue depth và pool metrics.
- Dùng `jcmd` để lấy VM info, thread dump, heap summary và điều khiển JFR.
- JFR có thể khởi động bằng `jcmd JFR.start` hoặc từ startup bằng `-XX:StartFlightRecording`.
- Dùng `default` cho ghi nhận ít chi tiết hơn và `profile` cho cửa sổ điều tra ngắn khi cần nhiều event.
- JFR và GC log không thay thế application log; hãy đồng bộ timeline UTC để đối chiếu.
- JFR, thread dump, command line và system properties có thể chứa dữ liệu nhạy cảm; kiểm soát quyền truy cập và redact trước khi chia sẻ.

## Tài liệu tham khảo chính thức cho Java 17

- [Java SE 17 — `jcmd` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html).
- [Java SE 17 — `jfr` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html).
- [Java SE 17 — `java` launcher and VM options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Oracle Java 17 — JDK Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api-programmers-guide.pdf).
- [Oracle Java 17 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html).
- [JEP 328 — Flight Recorder](https://openjdk.org/jeps/328).
- [JEP 331 — Low-Overhead Heap Profiling](https://openjdk.org/jeps/331).

