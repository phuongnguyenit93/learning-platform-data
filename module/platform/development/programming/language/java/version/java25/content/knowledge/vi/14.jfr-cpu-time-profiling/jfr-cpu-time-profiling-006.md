# Đối chiếu dữ liệu CPU với mẫu thực thi, thông lượng và số liệu hệ điều hành

## 1. Vì sao một con số CPU chưa đủ để kết luận?

Khi một dịch vụ Java chậm đi, dashboard có thể hiển thị CPU của process ở mức 90%, JFR lại cho thấy một nhóm method xuất hiện nhiều trong stack samples, còn throughput giảm 30%. Ba tín hiệu này có liên quan nhưng không đo cùng một đại lượng. Nếu đọc chúng như những con số tương đương, nhóm phát triển dễ tối ưu nhầm method, tăng số thread trong khi CPU đã bão hòa, hoặc kết luận JVM dùng CPU thấp dù cả máy đang bị một tiến trình khác chiếm tài nguyên.

**CPU-time profiling** giúp xác định phần CPU thực sự được tiêu thụ trong lúc chương trình chạy. Trong Java 25, **JEP 509 — JFR CPU-Time Profiling (Experimental)** bổ sung event `jdk.CPUTimeSample` cho JDK Flight Recorder (JFR). Event này lấy mẫu theo khoảng CPU time trên Linux, nhờ đó profile phản ánh mức tiêu thụ CPU tốt hơn cách lấy mẫu theo thời gian trôi qua. Nó còn có thể quy trách nhiệm CPU tiêu thụ trong native code về Java method gọi vào native code.

Tuy nhiên, JEP 509 vẫn là **experimental và chỉ hỗ trợ Linux** trong Java 25. Nó không thay thế những event JFR dùng trên các nền tảng khác. Một cuộc điều tra tốt kết hợp:

- **CPU-time samples:** method và call path nào tiêu thụ CPU.
- **Execution samples:** thread đang thực thi Java code ở những thời điểm lấy mẫu theo thời gian.
- **JFR CPU-load events:** JVM và toàn máy đang dùng CPU ra sao.
- **Throughput/latency:** lượng công việc hoàn thành và thời gian người dùng chờ.
- **OS/process metrics:** CPU time, mức sử dụng từng core, tranh chấp và giới hạn CPU của máy/container.

Bài **Đối chiếu dữ liệu CPU với mẫu thực thi, thông lượng và số liệu hệ điều hành** thuộc chương **CPU-time profiling** của học phần **JAVA_VERSION_JAVA25**. Học phần khám phá các khả năng Java 25 còn áp dụng trong phát triển hiện đại như compact source files, module imports, flexible constructor bodies, `ScopedValue`, KDF API, AOT cache, JFR và đánh giá nâng cấp JDK. Bài này tập trung vào cách kết hợp các phép đo để tìm đúng bottleneck và xác nhận hiệu quả sau tối ưu.

### Sau bài học, bạn có thể

1. Phân biệt CPU time, wall-clock time, CPU utilization, throughput và latency.
2. Giải thích khác biệt giữa `jdk.ExecutionSample` và `jdk.CPUTimeSample`.
3. Bật CPU-time profiling JEP 509 trên Linux với JDK 25.
4. Dùng `jdk.CPULoad`, `jdk.ThreadCPULoad` và `jdk.CPUTimeSamplesLost` đúng mục đích.
5. Đọc số liệu process/machine từ hệ điều hành và đối chiếu với JFR.
6. Chuẩn hóa CPU time theo request hoàn thành để so sánh các phiên bản.
7. Phân biệt CPU-bound, I/O-bound, lock contention và host/container contention.
8. Thiết kế phép đo trước/sau tối ưu có cùng workload và điều kiện chạy.

> **Phạm vi Java 25:** JEP 509 đã được đưa vào JDK 25 nhưng vẫn mang trạng thái experimental và chỉ hoạt động trên Linux. Không cần `--enable-preview` hoặc `-XX:+UnlockExperimentalVMOptions` để bật event. Trên Windows/macOS, dùng các event JFR thông thường cùng số liệu hệ điều hành; không giả định `jdk.CPUTimeSample` có mặt.

## 2. Phân biệt các đại lượng trước khi đọc biểu đồ

### 2.1. CPU time và wall-clock time

**Wall-clock time** là thời gian thực trôi qua giữa hai mốc. **CPU time** là tổng thời gian CPU thực sự chạy các thread của process hoặc thread đang được đo.

Ví dụ một request mất 500 ms:

- Thread dành 20 ms chạy Java code.
- Thread chờ database 350 ms.
- Thread chờ network/connection pool 100 ms.
- Các hoạt động khác chiếm 30 ms.

Wall-clock latency vẫn là 500 ms, nhưng CPU time của phần xử lý chỉ khoảng 50 ms nếu tính trên các thread được đo. Tối ưu một vòng lặp giúp giảm 10 ms CPU có thể không làm request nhanh lên đáng kể nếu phần lớn 500 ms là chờ I/O.

Ngược lại, một tác vụ xử lý dữ liệu có thể mất 500 ms wall-clock và gần 500 ms CPU time trên một core. Khi đó, tối ưu thuật toán hoặc giảm allocation có thể tác động trực tiếp đến latency và năng lực xử lý.

### 2.2. CPU time có thể lớn hơn thời gian thực

CPU time cộng dồn trên nhiều thread. Nếu bốn thread chạy đồng thời trong một giây, process có thể tiêu thụ xấp xỉ bốn CPU-seconds trong một wall-clock second.

Các công thức cơ bản:

```text
Process CPU seconds = tổng CPU time của các thread trong khoảng đo

CPU cores consumed = Process CPU seconds / Wall-clock seconds

CPU utilization normalized (%)
  = Process CPU seconds
    / (Wall-clock seconds × số CPU cores khả dụng) × 100
```

Một số công cụ hệ điều hành hiển thị `%CPU` theo tổng một core, vì vậy process đa luồng có thể vượt 100%. Công cụ khác chuẩn hóa theo tổng số core và hiển thị 0–100%. Luôn kiểm tra cách công cụ định nghĩa phần trăm trước khi so sánh với dashboard khác.

Trong container, “số core khả dụng” cần xét CPU quota/cpuset của container, không nhất thiết là số core vật lý của host. Process có thể bị throttling dù máy chủ tổng thể vẫn còn CPU rảnh.

### 2.3. Throughput và latency

- **Throughput:** số request/job hoàn thành trong một đơn vị thời gian, ví dụ request/second.
- **Latency:** thời gian một request cần để hoàn tất; nên xem p50, p95 và p99, không chỉ trung bình.
- **CPU per request:** CPU time tiêu thụ để hoàn thành một request, tính trên cùng khoảng đo.

```text
CPU seconds per completed request
  = delta process CPU seconds / completed requests

Throughput
  = completed requests / wall-clock seconds
```

CPU per request thường hữu ích hơn CPU utilization đơn lẻ khi so sánh hai phiên bản. Nếu một phiên bản dùng ít CPU hơn cho mỗi request nhưng phục vụ gấp đôi request, tổng CPU utilization có thể vẫn tăng. Đó có thể là cải thiện hiệu quả, không phải hồi quy.

### 2.4. Ví dụ minh họa cách đọc

Giả sử hai phiên bản chạy cùng workload trong 60 giây:

| Chỉ số | Phiên bản A | Phiên bản B |
|---|---:|---:|
| Request hoàn thành | 6.000 | 8.400 |
| Throughput | 100 req/s | 140 req/s |
| Process CPU time | 30 CPU-s | 36 CPU-s |
| CPU time/request | 5 ms | 4,29 ms |
| p95 latency | 180 ms | 145 ms |

Phiên bản B dùng tổng CPU nhiều hơn trong khoảng đo vì phục vụ nhiều request hơn, nhưng CPU trên mỗi request thấp hơn và throughput cao hơn. Nếu chỉ nhìn tổng CPU time, ta có thể đánh giá sai.

**Quy tắc:** đọc CPU cùng lượng công việc hoàn thành và latency trong đúng cửa sổ đo.

## 3. JFR CPU-time profiling trong Java 25

### 3.1. JEP 509 bổ sung điều gì?

Trước JEP 509, JFR chủ yếu dùng execution sampler để lấy stack trace của các thread theo khoảng thời gian trôi qua. Cách này có ích trên nhiều hệ điều hành, nhưng có một số giới hạn:

- Chỉ lấy mẫu các thread đang chạy Java code; native code được gọi từ Java không được phản ánh đầy đủ.
- Mỗi chu kỳ chỉ lấy mẫu một phần thread.
- Việc lấy stack có thể thất bại mà profile thông thường không cho biết đầy đủ số mẫu bị mất.
- Khi workload ngắn hoặc biến động, profile có thể chưa đại diện.

JEP 509 bổ sung **CPU-time sampler** dùng CPU timer của Linux. Thay vì lấy mẫu sau mỗi khoảng wall-clock cố định, sampler lấy mẫu theo khoảng CPU time mà thread đã tiêu thụ. Event mới là `jdk.CPUTimeSample`.

Điểm khác biệt quan trọng là profile có thể phản ánh tốt hơn các đoạn code thực sự dùng CPU, kể cả khi đường gọi đi qua native code. Điều này đặc biệt hữu ích với xử lý nén, mã hóa, parsing, thư viện native hoặc FFM.

### 3.2. Giới hạn nền tảng và trạng thái experimental

| Thuộc tính | `jdk.CPUTimeSample` |
|---|---|
| Có trong | JDK 25 |
| Trạng thái | Experimental |
| Nền tảng | Linux |
| Mặc định | Không bật |
| Cơ chế | CPU-time sampling dựa trên timer của Linux |
| Native code | Có thể ghi nhận CPU tiêu thụ trong native path và quy về Java caller |
| Cấu hình | Event setting `enabled` và `throttle` |
| Preview flag | Không cần `--enable-preview` |
| `UnlockExperimentalVMOptions` | Không cần cho event này |

Đây là tính năng JDK 25 hiện có và hữu ích trên Linux, nhưng contract vẫn là experimental. Kiểm tra JDK vendor/build và event metadata của runtime thực tế trước khi đưa vào quy trình profiling lâu dài. Không giả định bản JDK cho Windows hoặc macOS sẽ có event này.

### 3.3. Hai event sampler không đo cùng một trục thời gian

`jdk.ExecutionSample` lấy mẫu theo thời gian thực trôi qua. `jdk.CPUTimeSample` lấy mẫu theo CPU time đã tiêu thụ. Có thể bật cả hai trong cùng recording để đối chiếu:

- Execution samples cho thấy những Java stack thường xuất hiện khi thread đang chạy.
- CPU-time samples nhấn mạnh các stack tiêu thụ CPU, kể cả CPU time trong native path.
- Sự khác nhau giữa hai profile có thể chỉ ra method có wall-clock span lớn nhưng phần CPU thực tế nhỏ.

Không diễn giải số mẫu từ hai event như thể cùng một đơn vị thời gian. Chúng có cách kích hoạt và ý nghĩa thống kê khác nhau.

### 3.4. Các event CPU liên quan

| Event | Dữ liệu | Cách dùng |
|---|---|---|
| `jdk.CPUTimeSample` | Stack sample theo CPU time | Tìm method/call path tiêu thụ CPU trên Linux |
| `jdk.CPUTimeSamplesLost` | Số CPU-time samples bị mất | Đánh giá chất lượng recording |
| `jdk.ExecutionSample` | Stack sample của thread đang chạy Java code | Profiling thông thường, đa nền tảng |
| `jdk.CPULoad` | CPU user/system của JVM và CPU tổng của máy | Đối chiếu JVM với host |
| `jdk.ThreadCPULoad` | CPU load user/system theo thread | Tìm thread có CPU load cao; đây là số liệu dựa trên method sampling |

`jdk.ThreadCPULoad` không phải phép đo chính xác số CPU nanoseconds đã tiêu thụ bởi từng thread. Oracle lưu ý số liệu này dựa trên method sampling và có thể thiếu chính xác khi sample count thấp. Dùng nó để nhận diện xu hướng, rồi kiểm chứng bằng OS counters hoặc `ThreadMXBean` khi phù hợp.

## 4. Bật JFR CPU-time profiling trên Linux

### 4.1. Bật khi khởi chạy ứng dụng

Ví dụ ghi 60 giây CPU-time profile:

```bash
java \
  -XX:StartFlightRecording=jdk.CPUTimeSample#enabled=true,jdk.CPUTimeSample#throttle=10ms,filename=cpu-time.jfr,duration=60s \
  -jar app.jar
```

Trong đó:

- `jdk.CPUTimeSample#enabled=true` bật event CPU-time.
- `jdk.CPUTimeSample#throttle=10ms` yêu cầu sampler phát sample theo mỗi khoảng CPU time đã cấu hình trên platform thread.
- `filename=cpu-time.jfr` đặt file recording.
- `duration=60s` giới hạn thời gian ghi.

Có thể đặt giới hạn tần suất tổng như `500/s` thay cho khoảng thời gian `10ms`. Tần suất cao hơn thường cho profile chi tiết hơn nhưng tăng số event và overhead. Bắt đầu bằng cấu hình vừa phải, sau đó điều chỉnh dựa trên chất lượng profile và chi phí đo.

### 4.2. Hiểu `throttle`

`throttle` có thể diễn đạt theo hai cách:

| Cấu hình | Ý nghĩa |
|---|---|
| `10ms` | Mỗi platform thread được lấy mẫu sau mỗi 10 ms CPU time tiêu thụ |
| `500/s` | Giới hạn tổng cộng khoảng 500 sample mỗi giây, phân phối trên các platform threads |

Mặc định của event là một giới hạn tổng theo giây; cấu hình `profile.jfc` đi kèm JDK sử dụng khoảng CPU-time riêng. Hãy đọc lại cấu hình đang chạy thay vì giả định profile template luôn bật CPU-time event.

Tăng tần suất không phải lúc nào cũng tốt. Với ứng dụng có nhiều thread và thời gian chạy ngắn, tần suất quá cao có thể tạo nhiều event, tăng kích thước file và chi phí xử lý. Hãy kiểm tra `jdk.CPUTimeSamplesLost` và overhead trong lần đo thử.

### 4.3. Bật recording cho JVM đang chạy bằng `jcmd`

Nếu không thể thay đổi command line của ứng dụng, tạo file cấu hình JFR:

Trong ví dụ, `profile.jfc` là file cấu hình có sẵn trong thư mục `JAVA_HOME/lib/jfr` của JDK. Hãy dùng đúng đường dẫn file đó hoặc đường dẫn tới file cấu hình profile đã sao chép vào workspace.

```bash
jfr configure \
  --input profile.jfc \
  --output cpu-profile.jfc \
  jdk.CPUTimeSample#enabled=true \
  jdk.CPUTimeSample#throttle=10ms
```

Sau đó khởi chạy recording trên JVM đang chạy:

```bash
jcmd <pid> JFR.start name=cpu-profile settings=cpu-profile.jfc duration=4m filename=cpu-time.jfr
jcmd <pid> JFR.check name=cpu-profile verbose=true
```

Thay `<pid>` bằng process ID của JVM cần đo. `jcmd` phải chạy trên cùng máy và cùng user hiệu lực với JVM. Kiểm tra help của JVM đích nếu command hoặc option khác nhau do vendor/build.

### 4.4. Kết thúc và đọc recording

Nếu recording có duration, JVM sẽ tự kết thúc theo thời gian đã cấu hình. Nếu cần dừng thủ công:

```bash
jcmd <pid> JFR.stop name=cpu-profile filename=cpu-time.jfr
```

Tóm tắt recording và xem profile hot methods:

```bash
jfr summary cpu-time.jfr
jfr view cpu-time-hot-methods cpu-time.jfr
jfr print --events jdk.CPUTimeSample,jdk.CPUTimeSamplesLost cpu-time.jfr
```

`jfr view cpu-time-hot-methods` tổng hợp các method nóng theo CPU-time samples. Có thể mở file `.jfr` trong JDK Mission Control (JMC) để xem flame graph và call tree. Flame graph thường hữu ích hơn danh sách method đơn lẻ vì nó cho biết call path nào đang tiêu thụ CPU.

### 4.5. Kiểm tra chất lượng CPU-time samples

Trong event `jdk.CPUTimeSample`, chú ý:

- `stackTrace`: stack trace của sample; có thể không có nếu sampler không lấy được stack.
- `eventThread`: thread được lấy mẫu.
- `samplingPeriod`: chu kỳ CPU-time tại thời điểm sample.
- `biased`: cho biết sample có thể chịu ảnh hưởng safepoint bias.
- `failed`: cho biết việc lấy stack thất bại trong event metadata tương ứng.

`jdk.CPUTimeSamplesLost` ghi số sample bị mất trong một vòng lấy mẫu. Nếu số sample bị mất đáng kể, profile có thể không phản ánh đầy đủ hoạt động CPU. Kiểm tra event này trước khi đưa ra kết luận về tỷ trọng method.

### 4.6. Không có `jdk.CPUTimeSample` trên Windows/macOS

Trên các nền tảng không hỗ trợ JEP 509, vẫn có thể dùng JFR:

```bash
java \
  -XX:StartFlightRecording=filename=execution.jfr,settings=profile,duration=60s \
  -jar app.jar
```

Phân tích các event `jdk.ExecutionSample`, `jdk.CPULoad`, `jdk.ThreadCPULoad` cùng số liệu process từ hệ điều hành. Đây là phương án profiling hiện hành trên các nền tảng đó; không cần tìm một cờ JVM để ép bật CPU-time sampler Linux.

## 5. Đọc CPU load và execution samples trong JFR

### 5.1. `jdk.CPULoad`: JVM so với toàn máy

Event `jdk.CPULoad` cung cấp ba trường quan trọng: `jvmUser` (CPU JVM ở user mode), `jvmSystem` (CPU JVM ở system/kernel mode) và `machineTotal` (CPU load tổng của máy).

Hãy xem ba đường này cùng một trục thời gian. Nếu `jvmUser` thấp nhưng `machineTotal` cao, một process khác hoặc workload khác trên host có thể đang tiêu thụ CPU. Nếu cả JVM và machine đều thấp nhưng latency cao, hãy kiểm tra I/O, dependency, lock, queue hoặc giới hạn tài nguyên khác.


### 5.2. `jdk.ThreadCPULoad`: tìm thread có CPU load cao

Event `jdk.ThreadCPULoad` cung cấp hai trường `user` và `system` theo thread. Đây là tín hiệu để xác định nhóm thread đang dùng CPU nhiều, ví dụ worker pool, request threads, GC hoặc compiler threads.

Cần hiểu giới hạn của event này: dữ liệu dựa trên method sampling. Khi số mẫu thấp, tỷ lệ theo thread có thể không chính xác. Thread chờ I/O, sleep, park hoặc lock không được method sampler lấy mẫu như thread đang chạy code. Vì thế:

- Dùng `jdk.ThreadCPULoad` để tìm xu hướng thread nóng.
- Dùng CPU-time profile trên Linux để xem call path tiêu thụ CPU.
- Dùng OS process counters để xác minh tổng CPU time.
- Không cộng phần trăm của các thread từ nhiều snapshot như thể đó là số CPU seconds chính xác.

### 5.3. `jdk.ExecutionSample`: profile Java code theo thời gian

`jdk.ExecutionSample` là event lấy mẫu stack của thread đang thực thi Java code. Nó hữu ích trên Windows, macOS và Linux, nhưng không tương đương CPU-time profiling:

- Sample được phát theo chu kỳ thời gian, không phải chu kỳ CPU time đã tiêu thụ.
- Thread đang chạy native code hoặc đang chờ không xuất hiện trong event này.
- Số sample của method là ước lượng thống kê về tần suất stack được quan sát, không phải phép đo chính xác số nanoseconds của method.

Một method có nhiều execution samples thường là nơi cần xem xét, nhưng hãy xác minh nó có thực sự tiêu thụ CPU hay chỉ nằm trên một call path có thời gian chờ dài. Dùng `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead`, `jdk.FileWrite`, `jdk.JavaMonitorWait`, `jdk.ThreadPark` và `jdk.ThreadSleep` để điều tra phần thời gian thread không chạy code.

### 5.4. Kết hợp CPU-time sample và execution sample

Trên Linux, bật cả hai event để so sánh profile theo CPU time với profile theo thời gian:

```bash
java \
  -XX:StartFlightRecording=jdk.CPUTimeSample#enabled=true,jdk.CPUTimeSample#throttle=10ms,filename=combined.jfr,duration=90s \
  -jar app.jar
```

Sau khi recording hoàn tất, dùng:

```bash
jfr view cpu-time-hot-methods combined.jfr
jfr print --events jdk.ExecutionSample,jdk.CPUTimeSample,jdk.CPUTimeSamplesLost combined.jfr
```

Ví dụ diễn giải:

- Method xuất hiện nhiều trong cả hai profile: có khả năng vừa thường xuyên chạy, vừa tiêu thụ CPU đáng kể.
- Method xuất hiện nhiều trong execution profile nhưng ít trong CPU-time profile: có thể có phần wall-clock span lớn nhưng phần CPU thực tế nhỏ.
- Method xuất hiện nhiều trong CPU-time profile nhưng không nổi bật trong execution profile: kiểm tra native path, cách lấy mẫu, khoảng recording và sai khác workload.
- Cả hai profile đều không có method nóng nhưng throughput giảm: kiểm tra lock, I/O, GC, scheduler, container throttling và dependency.

Đây là cách đọc xu hướng, không phải phép biến hai loại sample thành cùng một thước đo. Luôn giữ lại recording và metadata của workload để có thể đối chiếu.

### 5.5. JFR không tự cung cấp throughput nghiệp vụ

JFR có thể ghi sự kiện JVM và các custom events do ứng dụng phát ra, nhưng throughput HTTP/message/job thường phải lấy từ application metrics hoặc load generator. Ghi cùng thời điểm:

- Số request hoàn thành.
- Số request lỗi và timeout.
- p50/p95/p99 latency.
- Số request đang xử lý và queue depth.
- CPU time/process utilization.
- Tỷ lệ GC pause, allocation và lock wait.

Nếu có thể, thêm request count và latency histogram từ Micrometer/Prometheus hoặc công cụ load test. Khi so sánh, bảo đảm metric labels, cửa sổ thời gian và timezone đồng bộ với JFR.

## 6. Đối chiếu với số liệu hệ điều hành

### 6.1. Linux: process và từng thread

Dùng `pidstat` để theo dõi CPU của process theo từng khoảng:

```bash
pidstat -u -p <PID> 1
```

Có thể dùng `top` để quan sát tổng process và thread:

```bash
top -H -p <PID>
```

`pidstat`/`top` cho biết process đang dùng bao nhiêu CPU theo thời gian. Đây là số liệu tổng ở cấp process, không chỉ ra Java method nào tiêu thụ CPU. JFR bổ sung call stack và phân phối CPU theo method.

Khi chạy trong container, kiểm tra cả CPU quota và throttling của cgroup. Trên cgroup v2, `cpu.stat` có thể cung cấp `usage_usec`, `nr_throttled` và `throttled_usec`. Nếu `nr_throttled`/`throttled_usec` tăng trong khi throughput không tăng, container có thể đang chạm quota dù host còn CPU rảnh.

### 6.2. Windows: process CPU time và Performance Monitor

Trên Windows, JEP 509 CPU-time event không khả dụng. Có thể lấy tổng CPU time của process bằng PowerShell:

```powershell
$javaPid = 12345
$before = Get-Process -Id $javaPid

Start-Sleep -Seconds 60

$after = Get-Process -Id $javaPid
$cpuSeconds = $after.CPU - $before.CPU

"CPU seconds in interval: $cpuSeconds"
```

Thuộc tính `CPU` là tổng processor time tích lũy của process tính bằng giây. Lấy chênh lệch hai lần đọc để có CPU seconds trong khoảng đo. Nếu process khởi động lại trong lúc đo, cần bắt đầu một cửa sổ mới với PID mới.

Performance Monitor có thể theo dõi các counter như `Process(*)\% Processor Time` và `Processor(_Total)\% Processor Time`. Xác định đúng instance process khi có nhiều tiến trình Java. Task Manager phù hợp để quan sát nhanh; Performance Monitor phù hợp hơn khi cần lưu chuỗi số liệu theo thời gian.

### 6.3. Không nhầm CPU của JVM với CPU của host

Ví dụ một máy 8 core:

- JVM tiêu thụ trung bình 2 core.
- Một process backup tiêu thụ 5 core.
- Các process khác tiêu thụ phần còn lại.

JFR có thể cho thấy `jvmUser` không quá cao, trong khi `machineTotal` gần 100%. Nếu chỉ nhìn CPU toàn host, nhóm phát triển có thể kết luận ứng dụng Java đang CPU-bound. OS process metrics sẽ cho biết process nào đang tiêu thụ CPU; JFR sẽ cho biết JVM đang tiêu thụ CPU ở call path nào.

Ngược lại, process Java có thể chiếm 700% CPU trên máy 8 core, tương đương khoảng 7 core đang hoạt động. Cần phân biệt cách biểu diễn `%CPU` của công cụ trước khi so sánh với `jvmUser` hoặc dashboard container.

### 6.4. CPU time của process và CPU-time samples của method

Hai số liệu này trả lời hai câu hỏi khác nhau:

| Nguồn | Trả lời câu hỏi |
|---|---|
| OS process CPU time | JVM đã tiêu thụ tổng cộng bao nhiêu CPU time? |
| JFR `jdk.CPULoad` | CPU user/system của JVM và máy thay đổi thế nào? |
| JFR `jdk.CPUTimeSample` | Những Java call path nào được lấy mẫu theo CPU time? |
| JFR `jdk.ExecutionSample` | Những Java stack nào xuất hiện khi thread đang thực thi? |
| Application metrics | Bao nhiêu request/job đã hoàn thành và latency ra sao? |

Không cộng sample counts thành CPU seconds của process. Dùng OS counter để lấy tổng CPU time, JFR để phân tích cách CPU time được phân bố trong code.

## 7. Đo CPU time ở cấp thread bằng `ThreadMXBean`

### 7.1. Khi nào nên dùng?

`java.lang.management.ThreadMXBean` có thể đo CPU time tích lũy của **platform thread**. Phương pháp này hữu ích khi muốn đo một đoạn code kiểm soát được, chẳng hạn benchmark nội bộ hoặc một worker thread cụ thể.

CPU time trả về có độ chính xác biểu diễn nanosecond, nhưng không bảo đảm độ chính xác thực tế tới từng nanosecond. Việc bật đo CPU time cũng có thể có overhead tùy JVM.

### 7.2. Đo CPU time của thread hiện tại

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

public final class ThreadCpuMeasurement {

    public static void main(String[] args) {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();

        if (!bean.isCurrentThreadCpuTimeSupported()) {
            throw new UnsupportedOperationException(
                "JVM không hỗ trợ đo CPU time của thread hiện tại");
        }

        if (!bean.isThreadCpuTimeEnabled()) {
            bean.setThreadCpuTimeEnabled(true);
        }

        long cpuBefore = bean.getCurrentThreadCpuTime();
        long wallBefore = System.nanoTime();

        performWork();

        long wallNanos = System.nanoTime() - wallBefore;
        long cpuNanos = bean.getCurrentThreadCpuTime() - cpuBefore;

        System.out.printf("Wall time: %.3f ms%n", wallNanos / 1_000_000.0);
        System.out.printf("CPU time:  %.3f ms%n", cpuNanos / 1_000_000.0);
    }

    private static void performWork() {
        long value = 0;
        for (int i = 0; i < 20_000_000; i++) {
            value += (i * 31L) % 97;
        }
        if (value == Long.MIN_VALUE) {
            System.out.println(value);
        }
    }
}
```

Trong ví dụ, wall time là thời gian trôi qua; CPU time chỉ tính phần CPU mà thread hiện tại tiêu thụ. Nếu thread bị preempt hoặc chờ, wall time vẫn tăng nhưng CPU time không tăng tương ứng.

Bật thread CPU-time measurement một lần lúc khởi động hoặc trong môi trường benchmark. Không bật/tắt quanh từng request trong production vì việc điều khiển measurement cũng có thể tạo overhead và làm sai lệch phép đo.

### 7.3. Giới hạn với worker pool và virtual threads

`getCurrentThreadCpuTime()` chỉ đo thread hiện tại. Nếu method tạo thêm worker threads, CPU time của các worker không tự cộng vào số đo đó. Muốn đo tổng CPU của task nhiều thread, hãy lấy OS process CPU time hoặc đo các platform threads liên quan trong cùng cửa sổ.

Trong Java 25, `ThreadMXBean` quản lý platform threads và **không hỗ trợ đo virtual threads**. Không dùng API này để kết luận CPU time của từng virtual thread. Với ứng dụng dùng virtual threads, kết hợp JFR/OS process metrics và đo throughput/latency; kiểm tra cách runtime gắn stack và carrier threads trong recording.

### 7.4. Vì sao `ThreadMXBean` không thay thế JFR?

| `ThreadMXBean` | JFR |
|---|---|
| Đo CPU time tích lũy của platform thread | Ghi event theo thời gian, stack và trạng thái JVM |
| Không tự cung cấp method call tree | Có execution/CPU-time samples và stack traces |
| Hữu ích cho một đoạn code hoặc thread được kiểm soát | Hữu ích cho ứng dụng đang chạy và workload phức tạp |
| Không theo dõi virtual threads trong JDK 25 | Cung cấp recording có thể phân tích cùng các event JVM khác |

Dùng `ThreadMXBean` để đo CPU time ở phạm vi nhỏ khi cần. Dùng JFR để xác định call path, thread và bối cảnh của workload thực tế.


## 8. Ghép CPU với throughput và latency

### 8.1. Chọn cùng một cửa sổ đo

Để tính CPU time trên mỗi request, cần lấy hai đại lượng trong cùng khoảng thời gian:

1. Chênh lệch process CPU time giữa đầu và cuối cửa sổ.
2. Số request hoàn thành trong chính cửa sổ đó.

```text
CPU seconds/request
  = (process CPU time at end - process CPU time at start)
    / completed requests in the interval
```

Nếu process restart giữa hai lần đọc, hãy tách thành hai khoảng. Không dùng số request đã nhận thay cho số request hoàn thành; request còn nằm trong queue hoặc bị timeout không đại diện cho công việc đã hoàn tất.

Ví dụ:

| Chỉ số trong 60 giây | A | B |
|---|---:|---:|
| Process CPU time delta | 24 CPU-s | 30 CPU-s |
| Request hoàn thành | 4.000 | 6.000 |
| CPU time/request | 6 ms | 5 ms |
| Throughput | 66,7 req/s | 100 req/s |
| p95 latency | 240 ms | 170 ms |

B tiêu thụ tổng cộng nhiều CPU time hơn vì phục vụ nhiều request hơn, nhưng hiệu quả CPU trên mỗi request tốt hơn và latency cũng giảm. Đây là lý do phải chuẩn hóa CPU theo lượng công việc.

### 8.2. Đo đủ các chỉ số

Một bảng theo dõi tối thiểu nên có:

| Nhóm | Chỉ số | Nguồn |
|---|---|---|
| Khối lượng | Requests completed, jobs completed, errors | Application metrics/load generator |
| Latency | p50, p95, p99 | Histogram của ứng dụng hoặc load test |
| JVM CPU | `jvmUser`, `jvmSystem` | JFR `jdk.CPULoad` |
| Host CPU | Machine CPU, per-core CPU | JFR và OS |
| Process CPU | CPU time delta, CPU utilization | OS process counters |
| Method CPU | Hot methods, call tree, CPU-time samples | JFR/JMC |
| Thread | Thread CPU load, state, blocking | JFR |
| Container | CPU quota, throttled time | cgroup/container metrics |
| GC | GC pause, allocation rate | JFR |

Không nhất thiết mọi hệ thống phải có tất cả metric trong dashboard thường trực. Nhưng trong một lần benchmark hoặc điều tra hiệu năng, hãy thu đủ dữ liệu để không phải suy đoán từ một biểu đồ CPU duy nhất.

### 8.3. Cùng tải, cùng điều kiện

So sánh hai build cần giữ cố định:

- Cùng JDK vendor/build, JVM flags, heap, GC và container limit.
- Cùng máy hoặc loại instance, CPU quota và số core được cấp.
- Cùng dataset, payload, tỷ lệ cache hit và trạng thái dependency.
- Cùng concurrency, request mix và thời gian warmup.
- Cùng định nghĩa readiness, request hoàn thành và latency.

Nếu bản B chạy với concurrency gấp đôi bản A, không thể quy toàn bộ chênh lệch CPU cho thay đổi code. Hãy lưu cấu hình load test và command line của JVM cùng recording.

### 8.4. Không chỉ nhìn trung bình

Một thay đổi có thể làm CPU/request trung bình giảm nhưng p99 latency tăng vì một nhóm request bị lock hoặc queue. Ngược lại, throughput tăng có thể kéo CPU utilization lên nhưng p95 vẫn giảm.

Nên so sánh:

- Median và p95/p99 latency.
- Throughput trong steady-state.
- CPU seconds/request.
- Process CPU utilization và machine CPU.
- Queue depth, error rate và throttling.

Khi đo nhiều lần, báo cáo median của các lần chạy và khoảng biến động. Một lần chạy đơn lẻ dễ bị ảnh hưởng bởi JIT warmup, GC, background process hoặc filesystem cache.

## 9. Nhận diện bottleneck qua các tín hiệu kết hợp

### 9.1. CPU-bound

Dấu hiệu thường gặp:

- Process CPU time tăng nhanh; JVM user CPU cao.
- Throughput không tăng tương ứng khi thêm concurrency.
- CPU-time profile có một số method/call path chiếm phần lớn samples.
- CPU seconds/request cao.
- Máy hoặc container đã gần giới hạn CPU được cấp.

Hướng điều tra:

1. Mở CPU-time hot methods/flame graph trên Linux.
2. Tìm method có phần self CPU cao và call path dẫn đến nó.
3. Xác định thuật toán, vòng lặp, allocation hoặc thao tác native đang tốn CPU.
4. Tối ưu một điểm có tỷ trọng lớn.
5. Chạy lại cùng workload và so sánh CPU/request, throughput và latency.

### 9.2. I/O-bound hoặc chờ dependency

Dấu hiệu:

- Wall-clock latency cao nhưng CPU time/request thấp.
- JFR `jdk.CPULoad` của JVM không cao.
- JFR có `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead`, `jdk.FileWrite` hoặc thread park/wait.
- Throughput bị giới hạn bởi database, remote service, connection pool hoặc filesystem.

Trong trường hợp này, CPU-time profile có thể không có method nóng rõ ràng. Điều đó không có nghĩa ứng dụng không có bottleneck; phần lớn thời gian đang chờ. Hãy xem duration của I/O events, connection pool, queue và trace của dependency.

### 9.3. Lock contention hoặc thread coordination

Dấu hiệu:

- CPU không nhất thiết cao nhưng throughput giảm khi tăng concurrency.
- Nhiều thread chờ cùng monitor hoặc synchronizer.
- JFR ghi nhận `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark`.
- Một critical section hoặc lock dùng chung khiến nhiều worker không tiến triển.

Kiểm tra stack trace của các thread chờ và thread đang giữ lock. Nếu CPU cao đồng thời với lock contention, có thể còn có spin loop hoặc retry; cần phân biệt phần CPU thực thi với phần chờ lock.

### 9.4. Host contention hoặc CPU throttling

Dấu hiệu:

- `machineTotal` cao nhưng JVM/process CPU thấp.
- Process khác trên host chiếm CPU.
- Container CPU throttled time tăng.
- CPU utilization của container chạm quota, trong khi host còn core rảnh.
- Latency tăng dù CPU-time profile của JVM không chỉ ra một method nóng mới.

Hướng xử lý là xem OS process list, cgroup counters, CPU quota và noisy neighbors. Tối ưu Java method sẽ không giải quyết được tình trạng container bị giới hạn CPU hoặc host đang chạy workload khác.

### 9.5. Allocation và garbage collection

CPU có thể bị tiêu thụ bởi allocation rate cao, GC hoặc công việc nền của JVM. Kết hợp:

- CPU-time samples của application threads và JVM threads.
- `jdk.GarbageCollection`, `jdk.GCPhasePause`.
- `jdk.ObjectAllocationSample` hoặc các allocation events phù hợp.
- GC pause time, allocation rate, heap occupancy và throughput.

Nếu CPU-time profile cho thấy GC threads chiếm nhiều CPU, xem allocation pressure và cấu trúc object trước khi chỉ tăng heap. Tăng heap có thể giảm tần suất GC trong một số trường hợp, nhưng cũng có thể làm collection lâu hơn hoặc che giấu memory leak.

### 9.6. Native code và FFM

Với ứng dụng gọi native library, `jdk.ExecutionSample` có thể không phản ánh đầy đủ CPU tiêu thụ bên trong native code. JEP 509 được thiết kế để CPU-time profile trên Linux tính cả thời gian CPU trong native path và quy về Java caller phù hợp.

Nếu CPU-time profile cho thấy một Java wrapper nóng, hãy kiểm tra xem wrapper có gọi native library hay không. Trên nền tảng không hỗ trợ JEP 509, cần đối chiếu process CPU và profiler/diagnostic phù hợp với native component.

## 10. Đọc flame graph và call tree đúng cách

### 10.1. Width biểu thị tỷ trọng sample

Trong flame graph, chiều rộng của một frame biểu thị tỷ trọng samples được quy cho frame đó trong recording. Với CPU-time profile, chiều rộng giúp nhận ra các call path tiêu thụ CPU time nhiều hơn. Nó không phải thời gian wall-clock của method và cũng không mặc nhiên là số nanoseconds chính xác.

Một frame rộng có thể là:

- Method tự thực hiện nhiều tính toán.
- Method gọi một hàm con rất tốn CPU.
- Wrapper Java gọi vào native code.
- Một phần code xuất hiện trong nhiều đường xử lý nóng.

### 10.2. Self time và inclusive time

Phân biệt:

- **Self time:** CPU được quy cho phần thân method đó, không tính các method con.
- **Inclusive time:** CPU được quy cho method và toàn bộ call tree bên dưới.

Nếu một controller method có inclusive time lớn nhưng self time nhỏ, việc tối ưu controller có thể không giúp nhiều. Hãy đi xuống call tree để tìm method con thực sự tiêu thụ CPU.

### 10.3. Đừng tối ưu method chỉ vì nó có tên dễ thấy

Một method xuất hiện ở đầu stack có thể là nơi gọi tới code tốn CPU, không phải nơi thực hiện công việc nặng. Đọc call tree từ frame rộng xuống dưới, kiểm tra self time và đối chiếu với source code.

Ưu tiên những method:

- Có tỷ trọng CPU lớn.
- Nằm trên luồng request/job quan trọng.
- Có thể tối ưu mà không làm thay đổi semantics.
- Được tái hiện trong nhiều lần recording.

Không nên tối ưu một method chỉ chiếm tỷ lệ rất nhỏ nếu chưa xử lý bottleneck lớn hơn. Tăng tốc một phần nhỏ của tổng CPU sẽ chỉ đem lại cải thiện nhỏ cho toàn ứng dụng.

### 10.4. Kiểm tra sample bị mất và bias

Trước khi kết luận từ flame graph CPU-time:

- Kiểm tra `jdk.CPUTimeSamplesLost`.
- Kiểm tra event có stack trace null hoặc failed.
- Xem tỷ lệ sample có `biased=true`.
- Dùng recording đủ dài để có mẫu đại diện.
- So sánh nhiều lần hoặc nhiều khoảng tải.

Nếu sample loss cao hoặc recording quá ngắn, hãy giảm throttle rate, tăng thời gian ghi hoặc giảm lượng event không cần thiết. Mọi thay đổi sampling đều cần cân nhắc overhead và chất lượng dữ liệu.


## 11. Thiết kế phép đo trước và sau tối ưu

### 11.1. Chọn baseline có thể lặp lại

Trước khi sửa code, tạo một baseline:

- Ghi commit/build ID và JDK vendor/build.
- Ghi JVM flags, heap, GC, container CPU/memory limit.
- Lưu workload, dataset, concurrency và request mix.
- Ghi throughput, p50/p95/p99, CPU seconds/request và OS process CPU.
- Tạo JFR recording trong đúng cửa sổ tải.

Nếu ứng dụng có autoscaling, hãy đo một instance cố định trước để tách ảnh hưởng của scaling. Sau đó mới xác minh trong môi trường nhiều instance.

### 11.2. Chọn thời lượng recording và sampling rate

Một recording quá ngắn có thể không thu đủ mẫu để profile đại diện. Hãy chọn khoảng ghi đủ dài để đi qua các luồng quan trọng và nhiều chu kỳ request/GC. Với CPU-time profiling, điều chỉnh `throttle` theo mức chi tiết cần thiết:

| Mục tiêu | Cách chọn |
|---|---|
| Điều tra ngắn, có kiểm soát | Bắt đầu với khoảng CPU-time 10–20 ms |
| Profile cần nhiều chi tiết | Tăng tần suất từ từ và quan sát overhead |
| Theo dõi định kỳ | Chọn giới hạn sample rate thấp hơn, giữ recording vừa đủ dài |
| Recording có sample loss | Kiểm tra `jdk.CPUTimeSamplesLost`, giảm tải sampler hoặc điều chỉnh throttle |

Không chọn tần suất cao nhất ngay từ đầu. Nhiều sample hơn có thể làm file lớn, tăng CPU overhead và gây mất sample khi sampler không xử lý kịp.

### 11.3. Đo overhead của JFR

Oracle mô tả recording dùng `profile` settings mặc định có overhead dưới 2% với phần lớn ứng dụng, nhưng đó không phải cam kết cho mọi workload. CPU-time sampling, event settings và tần suất có thể thay đổi chi phí.

Hãy chạy một phép đo có và không có recording trong cùng điều kiện:

1. Chạy workload baseline không ghi JFR.
2. Chạy lại workload với recording mặc định.
3. Chạy lại với CPU-time event được bật trên Linux.
4. So sánh throughput, latency và process CPU time.

Nếu recording làm thay đổi đáng kể kết quả, giảm event không cần thiết hoặc throttle rate trước khi dùng số liệu đó để ra quyết định tối ưu.

### 11.4. Xác minh cải thiện sau thay đổi

Sau khi tối ưu:

- Dùng cùng workload và cùng điều kiện máy.
- Thu recording theo cùng cấu hình.
- So sánh hot methods và call tree.
- So sánh CPU seconds/request.
- So sánh throughput và p95/p99.
- Kiểm tra GC, lock, I/O và throttling có chuyển thành bottleneck mới hay không.

Một thay đổi tốt thường làm giảm CPU/request hoặc cải thiện throughput/latency ở cùng ngân sách tài nguyên. Nếu CPU time giảm nhưng latency tăng, cần tìm tác động khác như queueing, lock, I/O hoặc thay đổi concurrency.

## 12. Tình huống thực tế: cùng wall-clock, CPU time khác nhau

Giả sử hai worker xử lý HTTP:

- Worker A gọi 10 endpoint, mỗi endpoint mất khoảng 10 ms.
- Worker B gọi 1 endpoint, mất khoảng 100 ms.

Cả hai method có wall-clock duration gần 100 ms. Nhưng Worker A tạo nhiều request hơn, parse nhiều response hơn và thực hiện nhiều vòng xử lý. CPU time của Worker A có thể cao hơn đáng kể so với Worker B, vốn phần lớn thời gian chờ network.

Đây là loại tình huống mà CPU-time profile giúp tránh kết luận sai:

| Quan sát | Worker A | Worker B |
|---|---|---|
| Wall-clock duration | Khoảng 100 ms | Khoảng 100 ms |
| Số lần gọi endpoint | 10 | 1 |
| Thời gian chờ network | Nhiều lần chờ ngắn | Một lần chờ dài |
| CPU time | Có thể cao hơn | Có thể thấp hơn |
| Câu hỏi tối ưu | Giảm chi phí lặp, serialize/parse, tạo request | Giảm latency dependency hoặc tối ưu async flow |

Trong JFR execution profile, cả hai có thể có wall-clock span tương tự. Trên Linux, `jdk.CPUTimeSample` giúp profile thể hiện worker tiêu thụ nhiều CPU hơn. CPU-time hot-method view hoặc flame graph có thể làm rõ method nào thực sự dùng CPU, kể cả khi một phần xử lý đi qua native code.

Bài học là **latency không phải CPU time**. Một method có duration lớn không nhất thiết là nơi tiêu thụ CPU nhiều nhất.

## 13. Chẩn đoán khi số liệu không khớp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| JFR CPU thấp nhưng OS process CPU cao | Event chưa bật, recording thiếu mẫu, native path hoặc khác cửa sổ đo | Kiểm tra event settings, JFR metadata, OS counter và timestamp |
| `machineTotal` cao nhưng JVM CPU thấp | Process khác hoặc host contention | Xem process list, per-core CPU và host metrics |
| JFR có hot method nhưng CPU/request thấp | Workload ít, recording ngắn hoặc sample chưa đại diện | Tăng thời lượng, kiểm tra throughput và lặp lại |
| Throughput giảm nhưng CPU không tăng | I/O, lock, queue, dependency hoặc CPU quota | Kiểm tra socket/file events, monitor wait, queue và cgroup throttling |
| CPU tăng nhưng throughput không tăng | CPU-bound, retry, GC hoặc contention | Đọc CPU-time flame graph, GC events và lock events |
| `jdk.CPUTimeSamplesLost` có số lớn | Sampler bị mất sample | Điều chỉnh throttle, thời lượng hoặc tải recording |
| `jdk.CPUTimeSample` không xuất hiện | Không phải Linux, event chưa bật hoặc JDK/provider không hỗ trợ | Kiểm tra OS, JDK build và event metadata |
| Thread CPU load không khớp process CPU | `jdk.ThreadCPULoad` là sampling-based và có thể thiếu chính xác | Đối chiếu process counters và CPU-time profile |
| `ThreadMXBean` trả về `-1` | CPU-time measurement chưa bật, thread không còn sống hoặc là virtual thread | Kiểm tra support/enabled và loại thread |
| CPU process trên 100% | Công cụ tính theo một core, process chạy nhiều core | Chuẩn hóa theo số core/quota được cấp |
| CPU thấp trong container nhưng latency cao | Container throttling hoặc host scheduling | Kiểm tra cgroup `cpu.stat`, quota và host steal time |
| Flame graph tập trung vào wrapper | CPU nằm ở method con hoặc native path | Mở rộng call tree, so sánh CPU-time với execution profile |

### 13.1. Kiểm tra event metadata của recording

Dùng `jfr metadata` để xác minh event có trong file và xem fields:

```bash
jfr metadata --events jdk.CPUTimeSample,jdk.CPUTimeSamplesLost cpu-time.jfr
```

Dùng `jfr summary` để kiểm tra số lượng event. Nếu file không có CPU-time events, không diễn giải flame graph CPU-time từ file đó.

### 13.2. Kiểm tra command của JVM đang chạy

Dùng:

```bash
jcmd <pid> VM.command_line
jcmd <pid> JFR.check
jcmd <pid> JFR.check name=cpu-profile verbose=true
```

Xác minh command line, tên recording và event settings. Không thay đổi đồng thời JDK, JVM flags, heap, GC và workload khi đang chẩn đoán một chênh lệch hiệu năng.

## 14. Bài thực hành tổng hợp

### 14.1. Mục tiêu

Chạy một workload có cả CPU-bound và I/O-wait behavior, thu JFR recording, đối chiếu CPU time với throughput và số liệu OS, sau đó viết một kết luận có bằng chứng.

### 14.2. Chuẩn bị hai loại công việc

Tạo hai đường chạy:

- `cpu`: thực hiện vòng lặp tính toán có kết quả được sử dụng để tránh compiler loại bỏ.
- `wait`: chờ một khoảng thời gian mô phỏng dependency I/O.

Ví dụ đơn giản:

```java
public final class CpuVsWait {

    static long cpuWork(int rounds) {
        long result = 1;
        for (int i = 1; i <= rounds; i++) {
            result = result * 31 + (i % 97);
        }
        return result;
    }

    static void waitWork(long millis) throws InterruptedException {
        Thread.sleep(millis);
    }

    public static void main(String[] args) throws Exception {
        for (int i = 0; i < 100; i++) {
            long cpuResult = cpuWork(2_000_000);
            if (cpuResult == Long.MIN_VALUE) {
                System.out.println(cpuResult);
            }
            waitWork(10);
        }
    }
}
```

`Thread.sleep` chỉ mô phỏng thời gian chờ, không thay thế một phép đo network/database thực. Khi áp dụng cho dịch vụ, hãy dùng load generator gọi endpoint thực và ghi nhận request completion.

### 14.3. Thu recording trên Linux

```bash
java \
  -XX:StartFlightRecording:jdk.CPUTimeSample#enabled=true,jdk.CPUTimeSample#throttle=10ms,filename=cpu-vs-wait.jfr,duration=90s \
  CpuVsWait
```

Sau đó:

```bash
jfr summary cpu-vs-wait.jfr
jfr view cpu-time-hot-methods cpu-vs-wait.jfr
jfr print --events jdk.CPUTimeSample,jdk.CPUTimeSamplesLost,jdk.ExecutionSample cpu-vs-wait.jfr
```

Đồng thời dùng `pidstat` hoặc OS process counters để lấy CPU utilization/CPU time trong cùng cửa sổ.

### 14.4. Thu recording trên Windows/macOS

Dùng JFR profiling thông thường:

```bash
java \
  -XX:StartFlightRecording=filename=execution-vs-wait.jfr,settings=profile,duration=90s \
  CpuVsWait
```

Phân tích `jdk.ExecutionSample`, `jdk.CPULoad`, `jdk.ThreadCPULoad`, I/O và thread-stalling events. Đối chiếu với process CPU time của hệ điều hành.

### 14.5. Báo cáo kết quả

Ghi lại:

| Chỉ số | Giá trị đo |
|---|---|
| JDK vendor/build và OS | Ghi thực tế |
| CPU cores/quota | Ghi thực tế |
| Recording duration | Ghi thực tế |
| Completed operations | Ghi thực tế |
| Throughput | Ghi thực tế |
| p50/p95/p99 latency | Ghi thực tế |
| Process CPU seconds | Ghi thực tế |
| CPU seconds/operation | Ghi thực tế |
| JFR hot methods | Ghi method/call path |
| Sample lost | Ghi từ `jdk.CPUTimeSamplesLost` |
| Host CPU / throttling | Ghi từ OS/container |

Không điền số giả định vào báo cáo. Hãy phân biệt số đo trực tiếp từ OS, số liệu JFR và giá trị được tính bằng công thức. Ghi rõ recording nào dùng CPU-time sampler Linux và recording nào chỉ dùng execution sampling.

### 14.6. Tiêu chí nghiệm thu

- Có baseline và recording được lưu lại.
- Xác định rõ CPU-time sampler có khả dụng trên OS đang dùng hay không.
- Không nhầm wall-clock time với CPU time.
- Có throughput và latency trong cùng khoảng đo.
- Có số liệu process/host từ OS.
- Đọc được ít nhất một call path nóng hoặc giải thích được vì sao không có hot method.
- Kiểm tra sample loss và event settings.
- Kết luận nêu rõ bằng chứng, giới hạn và bước xác minh tiếp theo.

## 15. Tài liệu chính thức và phạm vi phiên bản

- [JEP 509 — JFR CPU-Time Profiling (Experimental)](https://openjdk.org/jeps/509): CPU-time sampling trên Linux, event `jdk.CPUTimeSample`, `throttle`, sample loss và trạng thái experimental.
- [JEP 518 — JFR Cooperative Sampling](https://openjdk.org/jeps/518): cơ chế cooperative stack sampling được JEP 509 sử dụng.
- [Oracle Java 25 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html): cách dùng `jdk.CPULoad`, `jdk.ThreadCPULoad`, execution sampling, I/O và monitor events.
- [Oracle Java 25 — The `jcmd` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`.
- [Oracle Java 25 — The `jfr` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `jfr summary`, `jfr print`, `jfr view`, `jfr metadata` và `jfr configure`.
- [Java SE 25 — `jdk.jfr` package](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html): cấu hình event settings và JFR API.
- [Java SE 25 — `ThreadMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html): CPU time của platform threads và giới hạn với virtual threads.
- [Oracle JDK 25 Release Notes](https://www.oracle.com/java/technologies/javase/25all-relnotes.html): xác nhận JFR CPU-Time Profiling là tính năng experimental của JDK 25.

*Phạm vi đối chiếu: 27/11/2026.* JEP 509 đã được đưa vào Java 25 nhưng vẫn experimental và Linux-only. Trên các nền tảng khác, dùng execution sampling, JFR CPU-load events, OS process metrics và throughput/latency. Không dùng sample count làm số CPU nanoseconds chính xác; hãy đối chiếu profile với process CPU time và lượng công việc hoàn thành.
