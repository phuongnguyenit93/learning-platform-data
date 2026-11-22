# Đo CPU trong ứng dụng Java

Bài học thuộc nhóm **Performance tooling** với đề bài **Đo CPU**. Mục tiêu là xác định ứng dụng Java thực sự tiêu thụ bao nhiêu thời gian CPU, thread nào đang dùng CPU và method nào tạo ra phần tải lớn nhất. Sau đó dùng số đo để chọn điểm cần tối ưu và kiểm tra lại kết quả.

Không có một con số CPU duy nhất trả lời mọi câu hỏi. CPU time, wall-clock time, CPU utilization, sampling profile và benchmark là các phép đo khác nhau. Chọn sai phép đo có thể khiến một ứng dụng đang chờ I/O bị hiểu nhầm là chậm vì CPU, hoặc khiến một method có nhiều lần gọi nhưng mỗi lần rất ngắn bị hiểu nhầm là điểm nóng.

Các ví dụ Java được biên dịch với target Java 17 và chạy trên Zulu/OpenJDK 24.0.2, Windows 11. Bài thực hành đo CPU time của từng platform thread và cả JVM process, sau đó ghi JFR để xác định method nóng.

## 1. Trước tiên, xác định câu hỏi cần đo

Chọn công cụ theo câu hỏi:

| Câu hỏi | Số liệu/công cụ phù hợp |
|---|---|
| Process Java đã dùng bao nhiêu CPU trong 10 giây? | Process CPU time, Task Manager, `Get-Process`, `OperatingSystemMXBean` |
| Thread nào dùng CPU nhiều nhất? | `ThreadMXBean`, JFR `jdk.ThreadCPULoad`, OS thread monitor |
| Method nào tạo tải CPU? | JFR execution samples, JDK Mission Control, async-profiler, `perf` |
| Một thuật toán chạy nhanh hơn thuật toán khác không? | JMH benchmark |
| JVM hay cả máy đang bận CPU? | JFR `jdk.CPULoad`, OS metrics |
| Request chậm vì CPU hay đang chờ? | CPU profile kết hợp JFR I/O, lock, park, sleep và latency |
| CPU tăng sau một lần release? | So sánh profile, throughput và CPU time trước/sau trên cùng workload |

Đo utilization để biết mức tải, dùng profiler để tìm code path nóng, và dùng benchmark để so sánh một đoạn code trong môi trường có kiểm soát. Những công cụ này bổ sung cho nhau.

## 2. Phân biệt CPU time, wall time và CPU utilization

**Wall-clock time** là thời gian trôi qua từ lúc bắt đầu đến lúc kết thúc một thao tác. Nó bao gồm thời gian thread chạy, ngủ, chờ lock, chờ mạng, chờ đĩa và chờ scheduler.

**CPU time** là tổng thời gian CPU thực sự chạy một process hoặc thread. Khi một process có nhiều thread chạy song song, CPU time có thể tăng nhanh hơn wall time.

**CPU utilization** là tỷ lệ CPU time tiêu thụ trong một khoảng wall-clock time. Đây là tốc độ tiêu thụ CPU, không phải tổng CPU time kể từ lúc process khởi động.

Ví dụ bốn thread chạy CPU-bound song song trong ba giây:

- Wall time có thể xấp xỉ 3 giây.
- Mỗi thread có thể tiêu thụ gần 3 giây CPU.
- Tổng CPU time của bốn thread có thể xấp xỉ 12 giây.
- Process có thể sử dụng tương đương bốn logical CPU trong khoảng đó.

Một thread ngủ ba giây có wall time ba giây nhưng CPU time gần bằng không. Đây là lý do `System.nanoTime()` không thể thay cho phép đo CPU time.

## 3. Hiểu hai cách biểu diễn phần trăm CPU

Có hai cách thường gặp để biểu diễn tải của process:

1. **CPU core equivalent:** 100% tương đương một logical CPU chạy đầy đủ. Một process dùng bốn CPU song song có thể hiển thị khoảng 400%.
2. **Phần trăm tổng năng lực máy:** 100% tương đương toàn bộ logical processor mà hệ thống tính vào mẫu số. Một process dùng bốn CPU trên máy có 28 logical processor tương đương khoảng 14,3% tổng năng lực.

Công thức từ CPU time và wall time:

~~~text
coreEquivalentPercent = deltaProcessCpuTime / deltaWallTime * 100

machineCapacityPercent =
    coreEquivalentPercent / availableProcessors
~~~

Tất cả thời gian trong phép chia phải dùng cùng đơn vị. Kết quả thứ hai đã là phần trăm của toàn bộ năng lực máy vì giá trị thứ nhất đã ở đơn vị phần trăm; không nhân thêm 100.

Một số dashboard chuẩn hóa phần trăm theo toàn máy, một số khác tính 100% cho một CPU. Vì vậy không so sánh trực tiếp hai biểu đồ khi chưa biết mẫu số của chúng. Trong container, hãy dùng số CPU mà JVM thực sự nhìn thấy hoặc quota CPU được cấp cho container; không mặc định lấy số core vật lý của host.

## 4. Đo elapsed time đúng cách

Dùng `System.nanoTime()` để đo khoảng thời gian:

~~~java
long start = System.nanoTime();

performOperation();

long elapsedNanos = System.nanoTime() - start;
System.out.printf("elapsedMs=%.3f%n", elapsedNanos / 1_000_000.0);
~~~

`System.nanoTime()` là đồng hồ monotonic phù hợp để đo thời lượng. Nó không phải CPU clock và không cho biết thread đã chạy bao lâu.

Tránh dùng `System.currentTimeMillis()` để đo các thao tác ngắn hoặc benchmark. Đồng hồ lịch có thể thay đổi theo đồng bộ thời gian và có độ phân giải không phù hợp cho nhiều phép đo nhỏ.

Nếu một request mất 2 giây nhưng CPU time chỉ 30 ms, hãy điều tra phần thời gian còn lại: network, database, lock, queue, file I/O hoặc scheduler. Tối ưu vòng lặp CPU có thể không cải thiện latency trong tình huống đó.

## 5. Đo CPU time của một thread bằng `ThreadMXBean`

`ManagementFactory.getThreadMXBean()` trả về `ThreadMXBean`. Trên JVM hỗ trợ, interface này đo CPU time của platform thread hiện tại hoặc một platform thread khác.

Ví dụ đo CPU time của thread đang chạy:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();

if (!bean.isCurrentThreadCpuTimeSupported()) {
    throw new UnsupportedOperationException("Current-thread CPU time is not supported");
}

if (!bean.isThreadCpuTimeEnabled()) {
    bean.setThreadCpuTimeEnabled(true);
}

long cpuStart = bean.getCurrentThreadCpuTime();

performCpuWork();

long cpuNanos = bean.getCurrentThreadCpuTime() - cpuStart;
System.out.printf("threadCpuMs=%.3f%n", cpuNanos / 1_000_000.0);
~~~

Lưu ý:

- Kiểm tra `isThreadCpuTimeSupported()` hoặc `isCurrentThreadCpuTimeSupported()` trước khi dùng.
- CPU time measurement có thể bị tắt mặc định; bật bằng `setThreadCpuTimeEnabled(true)` khi JVM hỗ trợ.
- `getThreadCpuTime()` trả `-1` nếu thread không còn sống, measurement chưa bật hoặc phép đo không khả dụng.
- API báo độ chính xác ở mức nanosecond nhưng không bảo đảm độ chính xác thực tế đến từng nanosecond.
- Bật CPU-time measurement có thể có chi phí trên một số JVM.
- `ThreadMXBean` quản lý platform threads; API này không đo CPU time của virtual threads.

Để đo một thread pool, hãy lấy CPU time bên trong từng task khi task bắt đầu và kết thúc. Đừng chờ task kết thúc rồi mới gọi `getThreadCpuTime(threadId)`, vì thread có thể đã kết thúc và khi đó API trả `-1`.

## 6. Đo CPU time của cả JVM process

HotSpot cung cấp platform extension `com.sun.management.OperatingSystemMXBean`. Có thể lấy CPU time tích lũy của process:

~~~java
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.ManagementFactory;

var standardBean = ManagementFactory.getOperatingSystemMXBean();

if (standardBean instanceof OperatingSystemMXBean processBean) {
    long processCpuNanos = processBean.getProcessCpuTime();
    System.out.println("processCpuNanos=" + processCpuNanos);
}
~~~

`getProcessCpuTime()` trả tổng CPU time process đã sử dụng tính bằng nanosecond; trả `-1` nếu nền tảng không hỗ trợ. Số liệu bao gồm các thread ứng dụng và thread nội bộ JVM. Đây là API thuộc platform extension trong module `jdk.management`, vì vậy nên kiểm tra `instanceof` thay vì giả định mọi Java runtime đều cung cấp implementation giống nhau.

Extension này cũng có:

- `getProcessCpuLoad()`: mức CPU usage gần đây của JVM process, trong khoảng từ 0.0 đến 1.0 khi có dữ liệu.
- `getCpuLoad()`: mức CPU usage gần đây của toàn bộ operating environment, trong khoảng từ 0.0 đến 1.0 khi có dữ liệu.
- `getAvailableProcessors()`: số processor mà JVM nhìn thấy.

Khoảng thời gian quan sát của các giá trị load phụ thuộc implementation. Lần gọi đầu có thể chưa có một khoảng đo xác định; giá trị âm cho biết dữ liệu chưa có hoặc không khả dụng. Khi cần tự kiểm soát khoảng đo, lấy hai mẫu `getProcessCpuTime()` và `System.nanoTime()` rồi tính delta.

## 7. Bài thực hành: đo bốn CPU worker và một thread ngủ

Ví dụ dưới đây chạy bốn worker CPU-bound trong ba giây và một thread chỉ ngủ ba giây. Chương trình đo CPU time từng worker, thread ngủ, toàn JVM process và wall time. Sau phần đo, nó giữ một đoạn CPU-bound thêm 15 giây để có thể attach JFR từ terminal thứ hai.

Tạo file `CpuMeasurementDemo.java`:

~~~java
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class CpuMeasurementDemo {
    private static volatile long blackhole;

    private CpuMeasurementDemo() {
    }

    public static void main(String[] args) throws Exception {
        int processors = Runtime.getRuntime().availableProcessors();
        int workerCount = Math.min(4, processors);
        long phaseNanos = TimeUnit.SECONDS.toNanos(3);

        ThreadMXBean threadBean = ManagementFactory.getThreadMXBean();
        if (!threadBean.isThreadCpuTimeSupported()) {
            throw new UnsupportedOperationException(
                    "Thread CPU time is not supported");
        }
        if (!threadBean.isThreadCpuTimeEnabled()) {
            threadBean.setThreadCpuTimeEnabled(true);
        }

        var standardBean = ManagementFactory.getOperatingSystemMXBean();
        OperatingSystemMXBean processBean =
                standardBean instanceof OperatingSystemMXBean extension
                        ? extension : null;

        ExecutorService pool =
                Executors.newFixedThreadPool(workerCount + 1);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Long>> cpuWorkers = new ArrayList<>();

        for (int i = 0; i < workerCount; i++) {
            cpuWorkers.add(pool.submit(() -> {
                start.await();
                long cpuStart = threadBean.getCurrentThreadCpuTime();
                long wallDeadline = System.nanoTime() + phaseNanos;
                long value = 0x1234abcdL;

                while (System.nanoTime() < wallDeadline) {
                    value = value * 1664525L + 1013904223L;
                    value ^= value >>> 13;
                }

                blackhole ^= value;
                return threadBean.getCurrentThreadCpuTime() - cpuStart;
            }));
        }

        Future<Long> sleeper = pool.submit(() -> {
            start.await();
            long cpuStart = threadBean.getCurrentThreadCpuTime();
            Thread.sleep(TimeUnit.NANOSECONDS.toMillis(phaseNanos));
            return threadBean.getCurrentThreadCpuTime() - cpuStart;
        });

        long processCpuStart = processBean == null
                ? -1 : processBean.getProcessCpuTime();
        long wallStart = System.nanoTime();
        start.countDown();

        long totalWorkerCpu = 0;
        for (int i = 0; i < cpuWorkers.size(); i++) {
            long cpu = cpuWorkers.get(i).get();
            totalWorkerCpu += cpu;
            System.out.printf(Locale.ROOT, "WORKER_%d_CPU_MS=%.1f%n",
                    i + 1, cpu / 1_000_000.0);
        }

        long sleeperCpu = sleeper.get();
        long wallElapsed = System.nanoTime() - wallStart;
        long processCpuEnd = processBean == null
                ? -1 : processBean.getProcessCpuTime();

        pool.shutdown();
        pool.awaitTermination(5, TimeUnit.SECONDS);

        System.out.printf(Locale.ROOT, "AVAILABLE_PROCESSORS=%d%n", processors);
        System.out.printf(Locale.ROOT, "WORKER_COUNT=%d%n", workerCount);
        System.out.printf(Locale.ROOT, "SLEEPER_CPU_MS=%.1f%n",
                sleeperCpu / 1_000_000.0);
        System.out.printf(Locale.ROOT, "TOTAL_WORKER_CPU_MS=%.1f%n",
                totalWorkerCpu / 1_000_000.0);
        System.out.printf(Locale.ROOT, "WALL_TIME_MS=%.1f%n",
                wallElapsed / 1_000_000.0);

        if (processCpuStart >= 0 && processCpuEnd >= processCpuStart) {
            long processCpu = processCpuEnd - processCpuStart;
            double coreEquivalent =
                    processCpu * 100.0 / wallElapsed;
            double machineCapacity =
                    coreEquivalent / processors;

            System.out.printf(Locale.ROOT, "PROCESS_CPU_TIME_MS=%.1f%n",
                    processCpu / 1_000_000.0);
            System.out.printf(Locale.ROOT,
                    "CPU_CORE_EQUIVALENT_PERCENT=%.1f%n", coreEquivalent);
            System.out.printf(Locale.ROOT,
                    "MACHINE_CAPACITY_PERCENT=%.1f%n", machineCapacity);
        } else {
            System.out.println("PROCESS_CPU_TIME=UNAVAILABLE");
        }

        System.out.println(
                "PROFILE_PHASE_READY pid=" + ProcessHandle.current().pid());

        long profileDeadline =
                System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
        long profileValue = 7;
        while (System.nanoTime() < profileDeadline) {
            profileValue =
                    profileValue * 6364136223846793005L
                            + 1442695040888963407L;
            profileValue ^= profileValue >>> 17;
        }
        blackhole ^= profileValue;
        System.out.println("PROFILE_PHASE_DONE");
    }
}
~~~

Biên dịch target Java 17:

Windows PowerShell:

~~~powershell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror CpuMeasurementDemo.java
~~~

Linux/macOS:

~~~sh
javac --release 17 -encoding UTF-8 -Xlint:all -Werror CpuMeasurementDemo.java
~~~

Chạy:

~~~text
java CpuMeasurementDemo
~~~

Chương trình in CPU time từng worker, CPU time của thread ngủ, wall time và CPU time toàn process. Khi thấy dòng `PROFILE_PHASE_READY`, chuyển sang terminal thứ hai để ghi JFR.

## 8. Đọc kết quả đo và hiểu CPU core equivalent

Một lần chạy thực tế trên Windows 11 với Zulu JDK 24.0.2 và 28 logical processors cho kết quả gần như sau:

~~~text
WORKER_1_CPU_MS=2937.5
WORKER_2_CPU_MS=2937.5
WORKER_3_CPU_MS=2906.3
WORKER_4_CPU_MS=2984.4
AVAILABLE_PROCESSORS=28
WORKER_COUNT=4
SLEEPER_CPU_MS=0.0
TOTAL_WORKER_CPU_MS=11765.6
WALL_TIME_MS=3009.0
PROCESS_CPU_TIME_MS=13687.5
CPU_CORE_EQUIVALENT_PERCENT=454.9
MACHINE_CAPACITY_PERCENT=16.2
PROFILE_PHASE_READY pid=79676
~~~

Các con số thời gian và PID thay đổi theo máy. Cách đọc:

- Mỗi worker dùng gần ba giây CPU trong khoảng ba giây elapsed.
- Bốn worker cộng lại dùng khoảng 11,8 giây CPU.
- Thread ngủ có CPU time gần bằng không dù wall time cũng gần ba giây.
- Process CPU time cao hơn tổng worker CPU vì JVM còn có JIT compiler, GC và các thread nội bộ.
- `454,9%` tương đương khoảng 4,55 logical CPU chạy liên tục.
- `16,2%` là tỷ lệ trên tổng năng lực 28 logical processors mà JVM báo cáo.

Kết quả minh họa sự khác nhau giữa tổng CPU time và elapsed time. Nó không phải benchmark tốc độ của thuật toán và không dùng để so sánh hai CPU khác nhau.

## 9. Đo process CPU trên Windows bằng PowerShell

`Get-Process` có thuộc tính `CPU` là tổng thời gian processor mà process đã dùng tính bằng giây. Lấy hai mẫu cách nhau một khoảng thời gian:

~~~powershell
$javaPid = 12345
$process = Get-Process -Id $javaPid
$cpuStart = $process.CPU

$watch = [Diagnostics.Stopwatch]::StartNew()
Start-Sleep -Seconds 5
$process.Refresh()
$watch.Stop()

$cpuSeconds = $process.CPU - $cpuStart
$coreEquivalentPercent = 100 * $cpuSeconds / $watch.Elapsed.TotalSeconds
$machineCapacityPercent =
    $coreEquivalentPercent / [Environment]::ProcessorCount

"CPU core equivalent: {0:N1}%" -f $coreEquivalentPercent
"Machine capacity: {0:N1}%" -f $machineCapacityPercent
~~~

Thay `12345` bằng PID của JVM. Nếu process kết thúc trong lúc lấy mẫu, cần tìm lại PID và bắt đầu một khoảng đo mới. `Get-Process.CPU` là CPU time tích lũy, không phải utilization tức thời.

Trong Windows Task Manager, tab Details có thể hiển thị CPU và CPU time; Resource Monitor và Performance Monitor cung cấp thêm số liệu theo process. Đảm bảo chọn đúng instance `java.exe` khi có nhiều JVM chạy đồng thời.

## 10. Đo process và thread trên Linux/macOS

Trên Linux, `pidstat` từ gói sysstat có thể hiển thị CPU theo process và thread:

~~~sh
pidstat -u -t -p "$JAVA_PID" 1
~~~

`top` có thể hiển thị từng thread:

~~~sh
top -H -p "$JAVA_PID"
~~~

Trên macOS, Activity Monitor giúp xác định process tiêu thụ CPU; Instruments Time Profiler cho phép lấy call tree theo thời gian CPU.

Các công cụ hệ điều hành rất hữu ích để trả lời process nào đang bận. Chúng không luôn biết tên Java method. Khi cần liên hệ CPU với Java call stack, chuyển sang JFR, JMC hoặc async-profiler.

## 11. Dùng Linux `perf` để đo và lấy call stack

`perf stat` đo các counter trong một khoảng thời gian:

~~~sh
perf stat -p "$JAVA_PID" -- sleep 10
~~~

Tùy CPU và kernel, có thể thu thập cycles, instructions, cache misses, context switches và các counter khác. Không phải hardware counter nào cũng có trên mọi máy.

Lấy sample call stack trong 30 giây:

~~~sh
perf record -F 99 -g -p "$JAVA_PID" -- sleep 30
perf report
~~~

`perf` có thể cho thấy Java, native và kernel frames nếu symbol/unwind configuration phù hợp. Quyền truy cập `perf_event` bị giới hạn trên một số kernel hoặc container; kiểm tra `perf_event_paranoid`, kernel policy và quyền của user trước khi profiling.

Với Java, async-profiler thường giúp ánh xạ Java stack và native stack thuận tiện hơn khi cần flame graph.

## 12. Dùng Java Flight Recorder để tìm CPU hotspot

Java Flight Recorder (JFR) ghi lại event của JVM và ứng dụng trong một khoảng thời gian. Để lấy CPU profile từ một process đang chạy, dùng `jcmd`.

Sau khi chương trình mẫu in `PROFILE_PHASE_READY pid=...`, chạy ở terminal thứ hai:

~~~text
jcmd <pid> JFR.start name=cpu settings=profile duration=8s filename=cpu-profile.jfr
~~~

Kiểm tra recording:

~~~text
jcmd <pid> JFR.check name=cpu
~~~

Khi recording kết thúc, đọc tổng quan:

~~~text
jfr summary cpu-profile.jfr
~~~

In các event CPU quan trọng:

~~~text
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad,jdk.ExecutionSample cpu-profile.jfr
~~~

- `jdk.CPULoad` cho biết CPU load của JVM và toàn máy theo thời gian.
- `jdk.ThreadCPULoad` cho biết thread nào đang tiêu thụ CPU dựa trên method sampling.
- `jdk.ExecutionSample` chứa stack sample của code đang thực thi.
- `jdk.NativeMethodSample` có thể cung cấp sample ở native code.

Kết quả kiểm thử trên JDK 24 đã ghi được `jdk.ExecutionSample` và `jdk.ThreadCPULoad`; stack sample trỏ vào vòng lặp trong `CpuMeasurementDemo`. Số sample và thứ tự method thay đổi theo thời lượng recording và workload.

Nếu process khởi động với recording sẵn, có thể dùng:

~~~text
java -XX:StartFlightRecording=name=cpu,settings=profile,duration=30s,filename=cpu.jfr -jar app.jar
~~~

Với recording liên tục, cấu hình `default` thường phù hợp hơn. Dùng `profile` trong một khoảng ngắn khi cần method sampling và dữ liệu chi tiết hơn. Đo overhead trên workload thật trước khi áp dụng cho môi trường nhạy cảm về latency.

## 13. Phân tích CPU profile bằng JDK Mission Control

JDK Mission Control (JMC) mở file `.jfr` và cung cấp các view để điều tra:

- **Hot Methods:** method có nhiều execution samples.
- **Call Tree:** call stack dẫn đến các method nóng.
- **Threads:** CPU load và trạng thái từng thread.
- **Automated Analysis:** các dấu hiệu hiệu năng và cấu hình đáng chú ý.
- **JVM Internals:** compiler, GC, allocation, class loading và các sự kiện JVM.

Trong Hot Methods, method có nhiều sample là nơi ứng dụng dành nhiều thời gian CPU tương đối. Mở Call Tree để xem method đó được gọi từ đâu và đường gọi nào dẫn đến hotspot.

Đừng coi tỷ lệ sample là thời gian CPU chính xác tuyệt đối. Đây là phương pháp lấy mẫu. Sample count thấp làm kết luận kém tin cậy; hãy ghi lâu hơn trên workload đại diện hoặc tăng mức profiling khi cần.

## 14. CPU sampling khác wall-clock sampling

CPU profiler lấy sample từ thread đang thực sự chạy trên CPU. Thread đang ngủ, chờ lock hoặc chờ I/O thường không xuất hiện trong CPU profile.

Wall-clock profiler lấy sample theo đồng hồ thời gian, có thể ghi cả thread đang chạy, ngủ hoặc blocked. Vì vậy:

- CPU profile trả lời: code nào đang tiêu thụ CPU?
- Wall-clock profile trả lời: thread đang ở đâu trong toàn bộ thời gian quan sát?

Nếu request chậm nhưng CPU usage thấp, wall-clock profile có thể cho thấy thời gian chờ network, lock hoặc queue. Nếu CPU usage cao, CPU profile thường giúp tìm method nóng nhanh hơn.

## 15. Dùng async-profiler và flame graph

async-profiler là sampling profiler bên ngoài JDK, hỗ trợ CPU, allocation, wall-clock, lock contention và các event khác. Nó có thể lấy stack Java, native, JVM và kernel trên các môi trường được hỗ trợ.

Một lệnh CPU profile trong 30 giây:

~~~text
asprof -d 30 -f cpu-profile.html <pid>
~~~

Tạo wall-clock profile:

~~~text
asprof -e wall -d 30 -f wall-profile.html <pid>
~~~

Mở file HTML trong browser để xem flame graph. Trong flame graph, chiều ngang biểu diễn tỷ lệ sample trong các call stack; một frame rộng cho biết nhánh đó chiếm tỷ lệ lớn trong tập sample. Trục dọc là call stack, không phải timeline.

CPU profile tập trung vào thời gian thread chạy trên CPU. Wall-clock profile có thể hiển thị cả sleeping và blocked threads. Chọn đúng mode theo câu hỏi; không dùng wall-clock graph để kết luận method đó tiêu thụ nhiều CPU.

async-profiler là công cụ cài riêng, không phải lệnh của JDK. Cú pháp, quyền attach, hỗ trợ OS và yêu cầu kernel phụ thuộc bản phát hành. Trên Linux, `perf_events` có thể bị hạn chế bởi kernel policy; kiểm tra hướng dẫn cài đặt của phiên bản đang dùng.

## 16. Chọn profiler theo tình huống

| Công cụ | Phù hợp nhất cho | Giới hạn chính |
|---|---|---|
| JFR + JMC | CPU load, method samples, thread, GC, lock và I/O trong JVM | Sample có tính thống kê; cấu hình recording ảnh hưởng overhead |
| `jcmd` | Bắt đầu/dừng JFR trên JVM đang chạy và lấy metadata | Không tự tạo flame graph hay benchmark |
| async-profiler | CPU/native stack, flame graph, allocation và wall-clock | Cần cài riêng, quyền attach và hỗ trợ nền tảng |
| Linux `perf` | Process CPU, hardware counters và kernel/native profiling | Phụ thuộc kernel, perf events và symbol |
| Windows Task Manager/PerfMon | Process CPU và tải toàn máy | Không tự ánh xạ sang Java method |
| macOS Instruments | CPU sampling và call tree trên macOS | Phụ thuộc môi trường Apple tooling |
| JMH | So sánh hiệu năng của một operation/algorithm | Không thay thế production profiler |

Bắt đầu bằng công cụ sẵn có và ít xâm lấn. Chỉ cài profiler bổ sung khi cần call stack, native frame hoặc loại event mà công cụ hiện tại không cung cấp.

## 17. JMH: benchmark CPU cho một đoạn code

Java Microbenchmark Harness (JMH) là framework của OpenJDK để benchmark code chạy trên JVM. Dùng JMH khi cần so sánh hai cách triển khai hoặc đo throughput/latency của một operation.

JMH khác profiler:

- JMH trả lời một operation chạy nhanh/chậm thế nào trong benchmark.
- Profiler trả lời ứng dụng dành CPU ở đâu trong workload.
- OS monitor trả lời process đang dùng bao nhiêu CPU trên máy.

Không dùng `System.nanoTime()` trong một vòng lặp thủ công để kết luận một method nhanh hơn method khác. JVM có warmup, JIT compilation, dead-code elimination, constant folding, loop optimization, GC và scheduler; benchmark tự viết rất dễ đo nhầm những yếu tố này.

## 18. Tạo JMH project và chạy benchmark

JMH khuyến nghị tạo project benchmark độc lập bằng Maven archetype:

~~~text
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DgroupId=org.sample -DartifactId=cpu-bench -Dversion=1.0
~~~

Sau khi project được tạo:

~~~text
cd cpu-bench
mvn clean verify
java -jar target/benchmarks.jar -wi 5 -i 5 -f 3
~~~

- `-wi 5`: năm warmup iterations.
- `-i 5`: năm measurement iterations.
- `-f 3`: chạy ba fork JVM độc lập.

Các tham số này chỉ là điểm khởi đầu. Điều chỉnh theo thời lượng benchmark, độ ổn định, chi phí khởi động và độ biến thiên của workload. Giữ JMH project tách biệt với ứng dụng giúp harness và annotation processor được cấu hình đúng. Chạy benchmark trực tiếp trong IDE thường làm môi trường khó kiểm soát hơn.

## 19. Ví dụ JMH benchmark

Trong project JMH, tạo class benchmark:

~~~java
package org.sample;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.annotations.Mode;

@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
public class SumBenchmark {
    @Param({"1000", "100000"})
    public int size;

    private int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];
        for (int i = 0; i < values.length; i++) {
            values[i] = i;
        }
    }

    @Benchmark
    public long sum() {
        long result = 0;
        for (int value : values) {
            result += value;
        }
        return result;
    }
}
~~~

JMH sẽ gọi benchmark method qua harness được sinh bởi annotation processor. Giá trị trả về giúp kết quả được sử dụng, giảm nguy cơ dead-code elimination. Nếu benchmark không trả kết quả, có thể dùng `Blackhole` theo hướng dẫn JMH.

`@State(Scope.Thread)` cấp state riêng cho mỗi benchmark thread. Nếu muốn đo contention hoặc throughput khi nhiều thread chia sẻ state, chọn scope và số thread phù hợp với câu hỏi. Đừng thay scope chỉ để tăng throughput mà không mô tả workload thực tế.

Kết quả `Mode.Throughput` là số operation mỗi giây; `Mode.AverageTime` đo thời gian trung bình mỗi operation. Chúng không phải CPU utilization.

## 20. Cách đọc JMH và profiler cùng nhau

Một quy trình hiệu quả:

1. Dùng load test hoặc production metrics xác định endpoint/task chậm.
2. Dùng JFR hoặc async-profiler tìm method và call path tiêu thụ CPU.
3. Tách phần logic đáng nghi thành benchmark JMH.
4. So sánh các cách triển khai bằng cùng input, JDK, fork và warmup.
5. Đưa thay đổi vào ứng dụng và chạy lại workload end-to-end.
6. Xác nhận throughput, latency percentile và CPU usage cùng cải thiện.

JMH có thể cho thấy một hàm nhanh hơn trong isolation nhưng ứng dụng tổng thể không cải thiện vì bottleneck nằm ở network, lock, database hoặc phần khác của code. Luôn xác minh lại trên workload thực tế.

## 21. Nhận diện các dạng CPU bottleneck

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| CPU process cao, nhiều `ExecutionSample` trong một method | Hot loop hoặc thuật toán tốn CPU |
| Một thread gần 100% một core, các core khác rảnh | Đường xử lý tuần tự hoặc một lock/worker giới hạn song song |
| Nhiều thread cùng dùng CPU nhưng throughput không tăng | Contention, cache pressure, oversubscription hoặc đồng bộ |
| CPU cao trong GC threads | Allocation rate, heap pressure hoặc GC work |
| CPU cao trong JIT compiler threads | Warmup, compilation storm hoặc nhiều class/method mới |
| CPU thấp nhưng latency cao | I/O, network, database, lock, queue hoặc scheduler wait |
| CPU toàn máy cao nhưng JVM CPU thấp | Process khác đang chiếm CPU |
| CPU tăng nhưng request rate không tăng | Work lặp lại, retry, spin loop hoặc xử lý thừa |

Đừng kết luận CPU bottleneck chỉ từ một biểu đồ utilization. Ghép CPU samples với thread state, GC, I/O events, request rate và latency để hiểu nguyên nhân.

## 22. Phân biệt CPU-bound với lock/I/O-bound trong JFR

Nếu `jdk.CPULoad` cao và thread có nhiều `jdk.ThreadCPULoad` hoặc `jdk.ExecutionSample`, hãy mở Hot Methods và Call Tree để tìm code path nóng.

Nếu thread ít được sample nhưng request vẫn chậm, xem các event:

- `jdk.SocketRead` và `jdk.SocketWrite`.
- `jdk.FileRead` và `jdk.FileWrite`.
- `jdk.JavaMonitorEnter` và `jdk.JavaMonitorWait`.
- `jdk.ThreadPark` và `jdk.ThreadSleep`.
- GC pause và các event liên quan đến allocation.

Nhiều event duration mặc định chỉ được ghi khi vượt ngưỡng. Event ngắn có thể không xuất hiện trong recording. Có thể hạ threshold để điều tra, nhưng threshold thấp hơn tạo nhiều event hơn và có thể tăng overhead. Hãy ghi ngắn, theo dõi tác động và chỉ bật event cần thiết.

## 23. Quy trình đo CPU có thể lặp lại

Trước khi đo:

- Chọn một workload đại diện và ghi rõ input, concurrency, request rate.
- Dùng cùng JDK vendor/version, JVM flags, heap, OS image và dependency.
- Warm up ứng dụng để JIT đạt trạng thái gần ổn định nếu mục tiêu là steady-state.
- Tránh chạy các benchmark nặng khác trên cùng máy.
- Ghi số processor mà JVM nhìn thấy và giới hạn CPU của container.
- Chạy nhiều lần để đánh giá độ biến thiên.

Trong khi đo:

- Ghi wall time, process CPU time, throughput và latency.
- Dùng JFR profile ngắn để tìm hot method.
- Ghi lại timestamp, PID, JDK, build ID và profile settings.
- Không bật heap statistics hoặc event chi tiết không liên quan khi đang đo latency nhạy cảm.

Sau khi tối ưu:

- Lặp lại cùng workload và điều kiện.
- So sánh cả CPU time/operation, throughput và latency percentile.
- Kiểm tra memory allocation, GC và lock contention để phát hiện trade-off.
- Giữ file JFR và kết quả benchmark cùng metadata để người khác tái lập.

## 24. Những lỗi đo CPU thường gặp

### Dùng wall time như CPU time

Một thread ngủ hoặc chờ network vẫn làm wall time tăng. Dùng `ThreadMXBean` hoặc process CPU time để đo CPU.

### Coi 100% là toàn bộ máy trên mọi công cụ

Một số công cụ hiển thị 100% cho một logical CPU; công cụ khác chuẩn hóa theo toàn máy. Xác định mẫu số trước khi so sánh.

### Đo một lần rồi kết luận

CPU load biến động theo scheduler, JIT, GC và background process. Lặp lại trong workload tương đương và xem xu hướng.

### Benchmark một method bằng vòng lặp tự viết

JIT có thể tối ưu hoặc loại bỏ phép tính. Dùng JMH với warmup, measurement, forks và output được sử dụng.

### Chỉ nhìn method có nhiều lần gọi

Số lần gọi không đồng nghĩa CPU time lớn. Một method được gọi nhiều lần nhưng rất nhanh có thể không phải hotspot. Dùng sample/call tree để xác định nhánh chiếm CPU.

### Dùng CPU profile để kết luận thời gian chờ

CPU profile thường chỉ sample thread đang chạy. Dùng wall-clock profile hoặc JFR I/O/lock/park events để điều tra thời gian chờ.

### Tăng số thread để chữa CPU bottleneck

Thêm thread có thể tăng throughput khi có khả năng song song, nhưng cũng có thể làm context switch, contention và CPU saturation tăng. Đo lại sau mỗi thay đổi.

### Bỏ qua GC và JIT

GC và compiler threads cũng dùng CPU của process. Kiểm tra JFR events để phân biệt CPU của ứng dụng với chi phí runtime.

## 25. Troubleshooting khi phép đo không hợp lệ

**CPU time trả `-1`:** kiểm tra JVM có hỗ trợ measurement không, đã bật thread CPU time chưa, thread còn sống không và API đang được gọi trên platform thread hay virtual thread.

**Process CPU time trả `-1`:** platform không hỗ trợ `getProcessCpuTime()`. Dùng OS process metrics hoặc JFR.

**CPU percentage vượt 100%:** có thể công cụ đang dùng quy ước 100% cho một logical CPU. Chuyển sang phần trăm tổng năng lực bằng cách chia cho số processor cùng mẫu số.

**JFR không có `jdk.ExecutionSample`:** kiểm tra template, thời lượng recording, workload có thực sự chạy CPU-bound không và event settings. Dùng `profile` cho recording ngắn có chủ đích; `default` phù hợp hơn cho continuous recording.

**JFR có quá ít sample:** tăng thời lượng recording hoặc tạo workload đại diện lâu hơn. Không suy luận method nóng từ vài sample.

**CPU toàn máy cao nhưng JVM thấp:** dùng Task Manager, `top` hoặc OS process monitor để tìm process khác.

**CPU thấp nhưng request chậm:** kiểm tra socket/file I/O, monitor wait, thread park, database và external service.

**JMH kết quả dao động:** kiểm tra warmup/forks, background load, thermal throttling, power mode, JDK version, GC và input. Tăng số iteration chỉ khi cần thêm dữ liệu; trước tiên phải loại bỏ nguyên nhân làm môi trường không ổn định.

## 26. Checklist đo CPU

- [ ] Đã xác định cần đo process, thread, method, benchmark hay toàn máy.
- [ ] Đã phân biệt CPU time với wall-clock time.
- [ ] Đã ghi rõ quy ước phần trăm CPU và số processor làm mẫu số.
- [ ] Dùng `System.nanoTime()` cho elapsed time.
- [ ] Kiểm tra khả năng hỗ trợ và trạng thái của `ThreadMXBean`.
- [ ] Kiểm tra platform extension trước khi dùng `getProcessCpuTime()`.
- [ ] Dùng JFR hoặc profiler sampling để tìm hot method.
- [ ] Dùng JMH cho microbenchmark thay vì vòng lặp `nanoTime()` tự viết.
- [ ] Đã warm up JVM và giữ workload đại diện.
- [ ] Đã xem GC, JIT, lock và I/O khi giải thích CPU.
- [ ] Đã lặp lại phép đo và ghi metadata.
- [ ] Đã kiểm tra lại end-to-end sau khi tối ưu.
- [ ] Không dùng sample count như CPU time tuyệt đối.
- [ ] Không chia sẻ recording chứa thông tin nội bộ hoặc dữ liệu nhạy cảm nếu chưa được phép.

## 27. Tài liệu tham khảo

- Oracle Java SE 24 — `ThreadMXBean`: https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle Java SE 24 — `com.sun.management.OperatingSystemMXBean`: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html
- Oracle JDK 24 — Troubleshoot Performance Issues Using Flight Recorder: https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle JDK 24 — Diagnostic Tools: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- OpenJDK — Java Microbenchmark Harness (JMH): https://github.com/openjdk/jmh
- OpenJDK — JMH project: https://openjdk.org/projects/code-tools/jmh/
- async-profiler — Getting Started: https://github.com/async-profiler/async-profiler/blob/master/docs/GettingStarted.md
- async-profiler — Profiling Modes: https://github.com/async-profiler/async-profiler/blob/master/docs/ProfilingModes.md
- Linux `perf` documentation: https://perf.wiki.kernel.org/

Đo CPU có ý nghĩa khi gắn số liệu với câu hỏi. CPU time cho biết process/thread đã chạy bao lâu; CPU utilization cho biết tốc độ dùng CPU trong một khoảng; JFR và profiler tìm method nóng; JMH so sánh các operation trong môi trường kiểm soát. Kết hợp các phép đo này với throughput, latency, GC, lock và I/O để xác định đúng bottleneck trước khi tối ưu.