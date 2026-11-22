# 2.3. Phân biệt thời gian thực trôi qua, CPU time và thời gian chờ

Một lời gọi Java mất 2 giây không có nghĩa CPU xử lý nó suốt 2 giây. Ngược lại, một process dùng 3 giây CPU trong 1 giây thực là điều có thể xảy ra khi nhiều thread chạy song song. Muốn chẩn đoán hiệu năng, cần xác định **đo thời gian gì, cho đối tượng nào, từ mốc nào đến mốc nào**, trước khi quy kết lỗi cho CPU, lock, I/O hoặc hệ thống bên ngoài.

Bài này nằm trong **2. Phương pháp đo**. Ba khái niệm cần phân biệt:

- **Elapsed time / wall-clock duration (thời gian thực trôi qua):** độ dài khoảng thời gian thực giữa hai sự kiện, bao gồm cả hoạt động và chờ đợi.
- **CPU time:** tổng thời lượng CPU thực thi một thread hoặc các thread của một process, tùy phạm vi được đo.
- **Waiting time (thời gian chờ):** thời lượng công việc hoặc thread chờ một điều kiện cụ thể như hàng đợi, lock, I/O, phản hồi từ dịch vụ khác hoặc được scheduler cấp CPU. **Không có một chỉ số Java duy nhất bao trùm mọi loại chờ.**

Mục tiêu là đọc số liệu đúng bản chất, chọn API Java 17+ phù hợp, tính toán đúng với nhiều core, hiểu giới hạn của thread state và biết khi nào cần đo riêng từng đoạn chờ.

## 1. Chỉ số trả lời những câu hỏi khác nhau

| Đại lượng | Câu hỏi | Phạm vi điển hình | Không thể suy ra trực tiếp |
| --- | --- | --- | --- |
| **Elapsed** | Người dùng/task đã phải chờ bao lâu từ start đến end? | Request, operation, method, thời gian quan sát | CPU đã dùng bao lâu |
| **Thread CPU** | Thread này thực sự dùng CPU bao nhiêu thời lượng? | Một platform thread trong một khoảng xác định | Toàn bộ thời gian xử lý request async hoặc tổng CPU process |
| **Process CPU** | Tất cả các thread của JVM dùng tổng bao nhiêu CPU? | Một JVM/process qua một cửa sổ | Latency của từng request hay CPU của riêng một thread |
| **Queue wait** | Công việc nằm chờ được xử lý bao lâu? | Từ enqueue đến dequeue/start | Thời gian làm việc của worker sau dequeue |
| **Lock/I/O/dependency wait** | Công việc bị giữ lại ở thao tác cụ thể bao lâu? | Monitor, lock, DB/HTTP, socket, filesystem | Toàn bộ phần chênh giữa elapsed và CPU |

**Ví dụ với một thread tuần tự:** một thao tác có elapsed 1.000 ms và thread CPU 120 ms. Có khoảng 880 ms mà thread **không tiêu thụ CPU** trong cửa sổ đó. Khoảng này có thể gồm chờ I/O, lock, sleep, preemption, safepoint/GC và chậm trễ scheduler. **Không được gọi 880 ms là “chờ database”** nếu chưa đo riêng database.

**Ví dụ với nhiều core:** bốn thread chạy trong cùng 1 giây, mỗi thread dùng 700 ms CPU. Tổng CPU của bốn thread là **2.800 ms**, còn elapsed cửa sổ vẫn là **1.000 ms**. Phép trừ 1.000 − 2.800 để tính waiting time hoàn toàn vô nghĩa vì CPU được cộng từ nhiều thread.

**Ví dụ với queue:** request vào queue 450 ms rồi worker tiêu tốn 50 ms CPU. End-to-end elapsed ít nhất khoảng 500 ms; việc đo CPU trên worker sau khi nhận request không thể nhìn thấy 450 ms đã chờ trước đó.

## 2. Elapsed: đồng hồ đo duration và đồng hồ ghi thời điểm

Trong cùng một JVM, **System.nanoTime()** thích hợp để đo khoảng thời gian:

~~~java
long startNanos = System.nanoTime();
// Công việc thực tế được đặt ở đây khi áp dụng phép đo.
long elapsedNanos = System.nanoTime() - startNanos;
double elapsedMillis = elapsedNanos / 1_000_000.0;
~~~

Đoạn trên là **mẫu mã minh họa cách bao phép đo**, không phải một chương trình hoàn chỉnh. `System.nanoTime()` trả số nanosecond từ gốc tùy ý của JVM/môi trường, hữu ích khi lấy **hiệu**, không phải timestamp lịch. Đơn vị nanosecond không bảo đảm độ chính xác hay độ phân giải tới một nanosecond. Elapsed đo được bao gồm thời gian thread ngủ, chờ I/O, bị tạm dừng, tranh CPU và GC/safepoint nếu chúng nằm giữa hai mốc.

Ngược lại, **System.currentTimeMillis()** và **Instant.now()** phù hợp để đánh dấu **lúc nào** trong log/trace. Đồng hồ hệ thống có thể bị điều chỉnh bởi NTP hoặc quản trị viên, nên phép trừ hai timestamp lịch có thể không ổn định khi đo duration ngắn. Khi cần đối chiếu timeline giữa JVM, container và service, lưu timestamp có timezone; khi cần đo duration trong một JVM, dùng nguồn monotonic.

Phải xác định điểm đo:
- **Client elapsed** có thể gồm mạng, DNS/TLS, gateway, retry, queue, server và downstream.
- **Controller/endpoint elapsed** chỉ gồm đoạn bên trong lớp đo đó, có thể không thấy request đã chờ trước khi dispatch.
- **Method elapsed** chỉ là start/end của method được instrument.
- **Trace span elapsed** là độ dài span; những span chạy song song chồng lấn nên không được cộng thành tổng elapsed tuần tự.

Ngay cả khi đo chính xác, duration của đoạn xử lý và duration nhìn từ client có thể khác đáng kể mà không có lỗi công cụ nào.

## 3. CPU time: xác định thread hay process

### 3.1. CPU time của một platform thread

Java cung cấp **java.lang.management.ThreadMXBean**:

- `isCurrentThreadCpuTimeSupported()`: JVM có hỗ trợ đo CPU của thread hiện tại không.
- `isThreadCpuTimeEnabled()` và `setThreadCpuTimeEnabled(true)`: kiểm tra và yêu cầu bật theo dõi nếu có hỗ trợ và quyền.
- `getCurrentThreadCpuTime()`: tổng CPU nanoseconds của current thread; có thể trả `-1` nếu không khả dụng.
- `getCurrentThreadUserTime()`: phần CPU time ở user mode, khác với CPU time toàn phần gồm cả thời gian system mode.

Lấy hiệu hai mẫu **của cùng một thread** tại hai mốc gần với điểm bắt đầu và kết thúc công việc sẽ có `threadCpuDelta`. Khoảng thread không được CPU thực thi, như lúc `Thread.sleep`, chờ monitor hoặc chờ I/O, thông thường không làm bộ đếm này tăng tương ứng.

**Quan hệ xấp xỉ cho cùng một thread và cùng khoảng đo:**

~~~text
elapsed ~= on-CPU time of the thread + off-CPU time of the thread
off-CPU ~= elapsed - threadCPU
~~~

Dấu `~=` nhấn mạnh khác biệt về độ phân giải, cách OS/JVM hạch toán và chi phí đọc bộ đếm. **Off-CPU không đồng nghĩa I/O wait**: còn gồm chờ monitor, sleep, park, scheduler không cấp CPU, CPU quota throttle, GC/safepoint, v.v.

CPU time đo mức tiêu thụ CPU, **không phải số lượng instruction hoặc tiến độ có ích**. Một vòng lặp lỗi có thể dùng CPU liên tục nhưng không hoàn thành request; ngược lại một thread chờ kết quả remote có CPU thấp nhưng elapsed lớn.

### 3.2. CPU time của toàn process

JVM có application workers, GC threads, JIT compiler, thread hệ thống và có thể nhiều tác vụ cùng lúc. **Process CPU** cộng lượng CPU các thread tiêu thụ nên **có thể lớn hơn elapsed** trên máy nhiều core.

Một phép diễn giải:

~~~text
average logical CPU cores used ≈ delta(process CPU seconds) / delta(elapsed seconds)
~~~

Nếu process tiêu thụ 2,4 giây CPU trong khoảng thực 1 giây, nó đã dùng trung bình khoảng **2,4 logical cores**. Chỉ số có thể được biểu diễn 240% khi lấy một core làm chuẩn; để diễn giải “% của năng lực được cấp” phải xét số CPU/quota thực sự sẵn có cho process/container.

Java 17 có `ProcessHandle.current().info().totalCpuDuration()` trả về `Optional<Duration>`: nếu OS hỗ trợ, lấy **hai snapshot của cùng process** rồi tính hiệu. Công cụ hệ điều hành/container cũng cung cấp process CPU, CPU quota và throttling; nên đối chiếu các lớp này khi nghi bị giới hạn CPU. Một process CPU tổng tích lũy từ khi khởi chạy không thể so trực tiếp với elapsed của một request riêng lẻ.

### 3.3. Không mặc định “CPU của request = CPU của worker”

Trong xử lý đồng bộ, nếu một request đi xuyên suốt cùng một thread và thread không thực thi việc khác xen kẽ, CPU delta của thread trong đoạn bao đo có thể đại diện tương đối tốt cho CPU của đoạn đó.

Nhưng một request async/reactive có thể chạy qua nhiều executor, callback hoặc thread khác. CPU time đọc từ thread nhận request chỉ là một phần, trong khi cùng thread cũng có thể tiếp tục xử lý các request khác. Muốn phân bổ CPU theo request cần tracing/profiling có context phù hợp, không lấy CPU toàn process trừ elapsed của request. Với virtual threads trên JDK mới hơn Java 17, cần kiểm tra công cụ đo vì bộ đếm CPU per-thread có thể không đại diện cho từng virtual thread theo cách mặc định của người dùng.

## 4. “Thời gian chờ” có nhiều loại và nhiều ranh giới

| Loại chờ | Ranh giới đo hữu ích | Nguồn bằng chứng |
| --- | --- | --- |
| **Queue wait** | enqueue → worker start | Queue timestamp, age, wait histogram |
| **Chờ monitor** | yêu cầu vào `synchronized` → có quyền vào monitor | Thread dump, Java monitor contention, JFR |
| **Chờ lock/condition/park** | bắt đầu acquire/park → acquire/unpark | Instrument lock, JFR park events, nhiều thread dump |
| **Chờ I/O/DB/HTTP** | bắt đầu gọi → nhận response/kết thúc | Trace span, JDBC/HTTP metrics, JFR I/O, timeout |
| **Chờ CPU scheduler** | thread đã sẵn sàng → được chạy | OS scheduler/run queue, CPU throttling, off-CPU profiling |
| **Tạm dừng JVM** | pause/safepoint start → end | GC/safepoint logs, JFR GC pause |

**Thread.State là ảnh chụp trạng thái, không phải thống kê thời gian chờ:**

- **RUNNABLE:** thread đang chạy hoặc có thể chạy; một số đường I/O native vẫn được biểu diễn là RUNNABLE. Không chứng minh CPU đang thực thi thread đó.
- **BLOCKED:** đợi vào hoặc reenter một **Java object monitor** để thực thi `synchronized`. Không bao trùm mọi loại lock hoặc socket I/O.
- **WAITING:** chờ vô thời hạn hành động của bên khác, ví dụ `Object.wait()`, `Thread.join()`, `LockSupport.park()`.
- **TIMED_WAITING:** chờ có thời hạn như `Thread.sleep()`, timed wait/join/park.
- **NEW/TERMINATED:** chưa chạy/đã kết thúc, không dùng để kết luận request có bottleneck.

Một thread pool rảnh có thể có phần lớn worker ở WAITING mà hệ thống hoàn toàn khỏe. Ngược lại một thread ở RUNNABLE có thể quay CPU hoặc bị kẹt ở native I/O. Chụp nhiều thread dump với timestamp và nhìn **progress counter, stack, lock owner và queue** trước khi gọi “treo” hay “deadlock”.

### ThreadMXBean có đo thời gian chờ không?

Khi JVM hỗ trợ thread contention monitoring và bật `setThreadContentionMonitoringEnabled(true)`, đối tượng **ThreadInfo** có thể cung cấp:
- `getBlockedTime()`: xấp xỉ thời gian thread chờ vào/reenter **monitor**.
- `getWaitedTime()`: xấp xỉ thời gian ở **WAITING/TIMED_WAITING** theo cơ chế theo dõi.

Các bộ đếm có thể báo `-1` nếu không hỗ trợ hoặc chưa bật, được tính tích lũy và phụ thuộc độ phân giải/overhead của JVM. Chúng **không phải** tổng thời gian chờ business request, không bao trùm mọi I/O, queue phía ngoài hoặc toàn bộ các loại lock. Bật theo dõi contention trong môi trường sản xuất cần cân nhắc overhead.

Nếu muốn khẳng định “chờ lấy DB connection 500 ms”, hãy instrument **enqueue/acquire start → acquired**, rồi đo riêng **query start → query end**. Đừng dùng `elapsed - threadCPU` để quy hết vào DB.

## 5. Chương trình Java 17+ chạy được: CPU work và sleep

Chương trình dưới đây đo hai công việc trên cùng **main thread**. Pha đầu tính tổng để tiêu CPU; pha sau ngủ 250 ms. Nó lấy duration từ `System.nanoTime()` và CPU từ `ThreadMXBean` khi công cụ cho phép.

Lưu toàn bộ mã trong tệp **TimeTypesDemo.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.Locale;

public class TimeTypesDemo {
    private static volatile long checksum;

    public static void main(String[] args) {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        boolean cpuAvailable = bean.isCurrentThreadCpuTimeSupported();

        if (cpuAvailable && !bean.isThreadCpuTimeEnabled()) {
            try {
                bean.setThreadCpuTimeEnabled(true);
            } catch (SecurityException | UnsupportedOperationException e) {
                cpuAvailable = false;
            }
        }
        cpuAvailable = cpuAvailable && bean.isThreadCpuTimeEnabled();

        measure("CPU work", bean, cpuAvailable, () -> {
            long sum = 0L;
            for (int i = 0; i < 10_000_000; i++) {
                sum += i % 7;
            }
            checksum = sum;
        });

        measure("Sleep", bean, cpuAvailable, () -> {
            try {
                Thread.sleep(250);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("sleep interrupted", e);
            }
        });

        System.out.println("checksum=" + checksum);
    }

    private static void measure(
            String label, ThreadMXBean bean,
            boolean cpuAvailable, Runnable task) {

        long cpuStart = cpuAvailable
                ? bean.getCurrentThreadCpuTime() : -1L;
        long wallStart = System.nanoTime();

        task.run();

        long elapsedNanos = System.nanoTime() - wallStart;
        long cpuEnd = cpuAvailable
                ? bean.getCurrentThreadCpuTime() : -1L;

        String cpuText = (cpuStart >= 0 && cpuEnd >= cpuStart)
                ? String.format(Locale.ROOT, "%.3f ms",
                        (cpuEnd - cpuStart) / 1_000_000.0)
                : "unavailable";

        System.out.printf(Locale.ROOT,
                "%s: elapsed=%.3f ms, threadCPU=%s%n",
                label, elapsedNanos / 1_000_000.0, cpuText);
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac TimeTypesDemo.java
java TimeTypesDemo
~~~

**Output cần diễn giải đúng:** hai dòng đầu bắt đầu bằng `CPU work:` và `Sleep:`, theo sau là elapsed thực đo và thread CPU thực đo. Các số đo phụ thuộc máy, scheduler, JIT và OS nên **không thể cung cấp stdout thời gian cố định**. Nếu CPU time không được hỗ trợ, chương trình in `threadCPU=unavailable`. Dòng cuối **luôn luôn** là:

~~~text
checksum=29999994
~~~

Với `Sleep`, elapsed thường khoảng 250 ms hoặc lớn hơn vì scheduler có thể đánh thức muộn; thread CPU tăng ít, cho thấy khoảng elapsed đó **không được dành cho tính toán trên main thread**. Với `CPU work`, CPU thường chiếm tỷ lệ lớn hơn trong elapsed, nhưng có thể thấp do bị tranh core hoặc throttling. Không lấy khác biệt giữa hai pha làm benchmark tốc độ phần cứng: JIT warm-up, xung CPU, thời điểm đo và runtime overhead đều ảnh hưởng.

**Giới hạn:** code này chỉ đo CPU của current thread, không cộng GC/JIT/worker khác; không đo trực tiếp lock wait, I/O wait hoặc queue. Việc đọc CPU trước/sau elapsed có sai lệch thời điểm nhỏ; những đoạn quá ngắn nên đo nhiều mẫu và chọn công cụ benchmark/profiler phù hợp. Đây là ví dụ **đo bản chất đại lượng**, không phải microbenchmark tin cậy để so hai hệ thống.

## 6. Phương pháp điều tra khi latency tăng

Một chiến lược hợp lý là đo **cùng cửa sổ thời gian** ở nhiều lớp rồi đối chiếu:

1. **End-to-end:** lấy elapsed p50/p95/p99, số lượng mẫu, loại request, success/error, deadline và trace ID. p99 cao có thể do một nhóm nhỏ request; chỉ nhìn trung bình sẽ bỏ sót.
2. **Các span xử lý:** tách queue wait, acquire connection, DB/HTTP call, lock, business logic và serialization. Nếu span chạy song song thì chúng chồng lấn, không cộng đơn giản thành tổng.
3. **Thread/JVM:** tìm thread CPU delta, stack/thread state ở nhiều thời điểm, sự kiện park/monitor/I/O và GC/safepoint. Một thread dump duy nhất không đo tổng thời gian chờ.
4. **Process/OS/container:** process CPU, CPU quota, throttling, run queue, disk/network latency, thread pool saturation. Host còn CPU rảnh không bảo đảm container có quota đủ.
5. **Dependencies:** DB latency, connection pool wait, HTTP downstream, retry và timeout. Một method có elapsed cao vì gọi mạng vẫn có thể dùng rất ít CPU.

Với JDK HotSpot và quyền attach phù hợp, có thể thu một thread dump và recording JFR bằng PID tương ứng:

~~~bash
jcmd 12345 Thread.print -l
jcmd 12345 JFR.start name=timing settings=profile duration=60s filename=timing.jfr
~~~

`12345` là PID ví dụ. `Thread.print -l` cho stack và lock snapshot, không báo một tỷ lệ thời gian chờ chính xác. JFR có thể cung cấp execution samples, park/monitor, I/O, GC theo event được bật và ngưỡng ghi; cần xem recording settings. Việc thu có overhead và file có thể chứa thông tin nhạy cảm, nên cân nhắc quyền/dung lượng và thu đúng thời điểm. Nếu process đã thoát, không thể attach vào PID cũ.

### Đọc dấu hiệu mà không kết luận quá mức

| Quan sát | Gợi ý ban đầu | Chứng cứ phải kiểm tra tiếp |
| --- | --- | --- |
| Elapsed request cao, CPU thread thấp | Có nhiều off-CPU hoặc chờ ngoài đoạn CPU đo | Queue, DB, lock, sleep, GC, scheduler, request có đổi thread không |
| Elapsed cao, CPU thread gần bằng elapsed | Đoạn trên thread có thể CPU-heavy | CPU profile/hot methods, số mẫu, contention, cơ hội tối ưu thuật toán |
| Process CPU cao, elapsed một request cao | JVM dùng nhiều CPU ở đâu đó | Thread nào đang tiêu CPU? GC/JIT hay request này? CPU quota? |
| Process CPU thấp, nhiều request timeout | Có thể đợi tài nguyên khác ngoài CPU | Pool, downstream, I/O, lock, saturation, quota throttling |
| Nhiều thread WAITING nhưng throughput ổn | Có thể worker idle bình thường | Queue/completion rate, stack và pool utilization |
| Process CPU 250% trong 1 giây | Có thể trung bình dùng 2,5 core | Logical cores/quota và OS accounting, không suy “wait âm” |
| p99 elapsed tăng nhưng CPU mỗi task ổn | Tail latency có thể đến từ chờ | Trace p99, queue age, dependency p99, I/O và lock evidence |

## 7. Tình huống phân biệt trước–sau

**A — Sleep và CPU:** code sleep 500 ms thường làm elapsed tăng thêm ít nhất xấp xỉ 500 ms trong khi CPU time rất thấp. Đây là **chờ có chủ đích**, không chứng tỏ CPU yếu. Đặc biệt, `Thread.sleep()` không tự giải phóng monitor đang giữ, nên sleep bên trong `synchronized` còn có thể gây lock contention cho thread khác.

**B — Chờ scheduler khác chờ database:** request chạy 80 ms CPU nhưng mất 300 ms elapsed vì process bị giới hạn CPU quota hoặc cạnh tranh core. Hiệu 220 ms off-CPU chưa đủ để gọi là DB wait. Kiểm tra cgroup CPU throttling, run queue, OS scheduler và CPU profile trước khi sửa SQL.

**C — Connection pool wait khác query time:** tổng request 900 ms, trong đó 500 ms chờ acquire connection và 250 ms thực thi SQL. Nếu chỉ đo SQL rồi gán toàn bộ 900 ms cho database engine là sai. Đặt một span riêng ở thao tác acquire, một span riêng ở query và đo request end-to-end.

**D — CPU process vượt elapsed:** bốn worker xử lý song song, tiêu tổng cộng 6 giây CPU trong một cửa sổ thực 2 giây; mức dùng trung bình khoảng 3 logical cores. Đây là số hợp lệ. Không trừ 6 giây khỏi elapsed 2 giây; muốn biết request chờ gì thì đo CPU/timeline của **đúng request và các thread liên quan**.

**E — Thread WAITING không hẳn treo:** worker đang đợi việc trong pool và không có backlog là tình trạng bình thường. Nếu completion counter dừng dù queue đầy, đồng thời nhiều snapshot cho thấy worker chờ cùng lock/dependency, lúc đó mới có chứng cứ về stall. Phân biệt “chờ bình thường” với “không có tiến độ”.

**F — GC làm elapsed cao mà app thread CPU thấp:** stop-the-world pause khiến ứng dụng không tiến triển, trong khi CPU của một application thread có thể hầu như không tăng; process CPU vẫn có thể cao do GC threads tiêu thụ CPU. Dùng GC logs/JFR để xác nhận pause, không quy ngay cho database.

## 8. Những lỗi đo và suy luận phổ biến

- **Lẫn thời điểm với thời lượng:** dùng `currentTimeMillis()` để microbenchmark; thời gian hệ thống có thể chỉnh, dùng `nanoTime()` cho duration.
- **Đặt start/end sai lớp:** đo method 100 ms rồi kết luận latency client 100 ms, bỏ qua queue, network và retry.
- **Coi elapsed = CPU:** bỏ qua I/O, sleep, lock, scheduling, GC/safepoint.
- **Coi elapsed − CPU = I/O wait:** thực chất hiệu cùng-thread chỉ xấp xỉ off-CPU; cần đo I/O span riêng.
- **Trừ process CPU nhiều thread khỏi wall một request:** hai phạm vi không tương thích.
- **Coi RUNNABLE là đang tiêu CPU:** state không chứng minh phần CPU nào được cấp.
- **Coi WAITING/BLOCKED là deadlock:** thread state đơn lẻ chỉ là snapshot; cần lock graph và kiểm tra tiến độ theo thời gian.
- **Coi ThreadInfo blocked/waited time là total wait của request:** bị giới hạn bởi cơ chế monitor/WAITING và việc bật monitoring.
- **Bỏ qua thread switching trong async:** CPU của một worker không đại diện toàn bộ request nhiều stage.
- **Cộng các span chạy song song:** hai nhánh 400 ms chồng lấn không nhất thiết tạo elapsed 800 ms; xác định critical path.
- **Đo một lần rồi kết luận:** JIT compilation, class loading, GC, CPU frequency và background load tạo dao động; dùng nhiều mẫu, cửa sổ rõ và baseline tương đương.
- **Không đo overhead đo lường:** log đồng bộ quá nhiều, profiler nặng và instrumentation có thể ảnh hưởng chính công việc đang đo.

## 9. Checklist cho một kết luận có bằng chứng

Một báo cáo đo thời gian nên trả lời được: **(1)** đâu là đối tượng và khoảng đo; **(2)** elapsed được ghi từ client/server/method/span nào; **(3)** dùng monotonic duration hay timestamp lịch; **(4)** CPU là per-thread hay process, có chuyển thread/chạy song song không; **(5)** loại waiting đã được instrument trực tiếp hay mới chỉ suy đoán; **(6)** có số liệu queue, lock, I/O, dependency, scheduler, CPU quota và GC không; **(7)** tải, cửa sổ đo và baseline có tương đương?

**Kết luận tốt:** “Từ 10:00–10:05, p95 elapsed của GET /orders là 920 ms; span chờ acquire DB connection p95 640 ms. CPU của worker thấp; nguồn trì hoãn đã xác nhận ở bước acquire, đang kiểm tra saturation của pool.”

**Kết luận chưa đủ căn cứ:** “Request 920 ms, CPU 80 ms, vậy DB wait 840 ms.” Phép trừ này không chỉ ra DB; nó có thể chứa nhiều loại chờ, scheduler và runtime pauses, thậm chí hai số liệu có thể khác phạm vi.

**Ghi nhớ:** **elapsed** trả lời “bao lâu đã trôi qua”; **thread/process CPU time** trả lời “CPU đã làm việc bao lâu”; **waiting time** chỉ có ý nghĩa khi chỉ rõ “chờ cái gì, đo từ đâu tới đâu”. Dùng các phép so sánh và phép trừ chỉ khi **đối tượng, cửa sổ và cách hạch toán** tương thích.