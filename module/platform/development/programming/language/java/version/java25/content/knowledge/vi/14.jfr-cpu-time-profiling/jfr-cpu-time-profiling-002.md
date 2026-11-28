# Phân biệt thời gian CPU, thời gian thực và trạng thái chờ của luồng

## 1. Vì sao cần phân biệt ba loại thời gian?

Một endpoint mất 800 ms để trả lời không có nghĩa ứng dụng đã dùng CPU trong 800 ms. Trong khoảng đó, luồng có thể chỉ chạy CPU một phần nhỏ rồi chờ database, socket, monitor lock, `park` hoặc scheduler. Nếu nhìn riêng thời gian phản hồi, ta dễ tối ưu nhầm phần code vốn không tiêu thụ CPU.

Trong Java 25, **JDK Flight Recorder (JFR)** cung cấp nhiều góc nhìn để điều tra vấn đề này. Đáng chú ý, **JEP 509 — JFR CPU-Time Profiling** bổ sung event `jdk.CPUTimeSample` để lấy mẫu stack theo thời gian CPU trên Linux. Tính năng này vẫn được đánh dấu **experimental** trong JDK 25 và tài liệu di chuyển JDK 26; nó chưa phải cơ chế portable cho mọi hệ điều hành. [JEP 509](https://openjdk.org/jeps/509) · [JDK 25 Significant Changes](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html) · [JDK 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/jdk-migration-guide.html)

Bài thuộc chương **CPU-time profiling** của module **JAVA_VERSION_JAVA25**, với đề bài **“Phân biệt thời gian CPU, thời gian thực và trạng thái chờ của luồng”**. Mục tiêu là chọn đúng công cụ và event cho từng câu hỏi, tránh coi mọi thời gian elapsed là CPU time hoặc coi phần chênh lệch giữa hai con số là thời gian chờ chính xác.

### Sau bài này, bạn có thể

1. Phân biệt elapsed/wall-clock time với CPU time của một luồng.
2. Hiểu phần thời gian một luồng không chạy CPU có thể gồm chờ I/O, lock, sleep, park và chờ được scheduler cấp CPU.
3. Dùng `ThreadMXBean` để đo CPU time tích lũy của platform thread khi JVM hỗ trợ.
4. Dùng JFR `jdk.CPUTimeSample` trên Linux để tìm method tiêu thụ CPU, kể cả khi stack có native frames.
5. Dùng các JFR duration events để tìm monitor contention, park, sleep và I/O wait.
6. Đọc kết quả sampling như một ước lượng thống kê, không diễn giải thành thời gian thực thi chính xác từng method.
7. Thiết kế quy trình profiling có kiểm soát overhead và kiểm tra sample bị mất.

## 2. Ba khái niệm cần tách riêng

### 2.1. Thời gian thực — elapsed time / wall-clock time

Là thời gian trôi qua giữa hai mốc quan sát. Ví dụ, một request bắt đầu lúc 10:00:00.000 và kết thúc lúc 10:00:00.800 thì elapsed time là 800 ms.

Thời gian này bao gồm mọi thứ xảy ra trong khoảng đó: thời gian chạy CPU, chờ I/O, chờ lock, sleep/park, chờ được scheduler cấp CPU và các khoảng tạm dừng liên quan đến JVM/OS.

Khi đo duration trong code, dùng `System.nanoTime()` vì đây là đồng hồ monotonic phù hợp để đo khoảng thời gian. Không dùng `System.currentTimeMillis()` để tính duration vì wall clock có thể được điều chỉnh.

### 2.2. CPU time — thời gian luồng thực sự được chạy trên CPU

CPU time là lượng thời gian CPU đã thực thi cho một luồng. Trên nền tảng có phân biệt user mode và system mode:

- **User CPU time:** CPU chạy mã ứng dụng ở user mode.
- **System CPU time:** CPU chạy phần công việc ở kernel/system mode được quy cho luồng.
- **Total thread CPU time:** tổng user và system CPU time.

CPU time không tăng khi luồng đang ngủ, parked, chờ monitor, chờ socket hoặc không được scheduler đưa lên CPU. Một luồng có thể mất 1 giây elapsed nhưng chỉ tiêu thụ 15 ms CPU.

### 2.3. Thời gian chờ — waiting / blocked time

Là phần elapsed time mà luồng không tiến hành công việc ứng dụng do đang chờ một điều kiện nào đó. Những nguyên nhân thường gặp:

- **Monitor contention:** chờ lấy intrinsic lock.
- **Object wait:** gọi `Object.wait()` và chờ notification/timeout.
- **Park:** chờ qua `LockSupport.park()` hoặc cơ chế đồng bộ dùng park.
- **Sleep:** chủ động nhường CPU trong khoảng thời gian.
- **I/O:** chờ đọc/ghi file hoặc socket.
- **Scheduler delay:** luồng runnable nhưng chưa được cấp CPU.

Các trạng thái này không hoàn toàn đồng nhất. Chẳng hạn, `Thread.State.RUNNABLE` không đảm bảo luồng đang chạy trên CPU tại đúng thời điểm quan sát; nó có thể đang chờ được scheduler cấp thời gian CPU hoặc đang thực hiện native operation.

### Bảng so sánh

| Đại lượng | Đo điều gì? | Bao gồm chờ I/O/lock? | Công cụ tiêu biểu |
| --- | --- | --- | --- |
| Elapsed/wall time | Thời gian trôi qua | Có | `System.nanoTime()`, request timer |
| Thread CPU time | CPU thực thi cho một luồng | Không | `ThreadMXBean` |
| CPU-time samples | Stack được lấy mẫu theo lượng CPU đã tiêu thụ | Không lấy mẫu lúc thread không chạy CPU | JFR `jdk.CPUTimeSample` |
| Wall-clock execution samples | Stack của luồng tại các thời điểm lấy mẫu theo thời gian thực | Thread đang chờ thường không được lấy mẫu như code đang chạy | JFR `jdk.ExecutionSample` |
| Wait/block duration events | Khoảng thời gian của một số thao tác chờ cụ thể | Có, theo loại event | JFR monitor, park, sleep, socket/file events |

**Không đồng nhất elapsed time trừ CPU time với wait time chính xác.** Phần chênh lệch còn có thể chứa scheduler delay, GC/safepoint pause, native work chưa được quy đúng, hoặc các trạng thái mà recording chưa thu event.

## 3. Quan hệ giữa CPU time và elapsed time

Với một platform thread được đo trong cùng một khoảng:

\[
CPU\ share(\%) = \frac{\Delta CPU\ time}{\Delta elapsed\ time} \times 100
\]

Ví dụ:

- Một thao tác mất 200 ms elapsed và tiêu thụ 180 ms CPU: thread dùng CPU gần như liên tục trong khoảng đó.
- Một thao tác mất 200 ms elapsed nhưng tiêu thụ 20 ms CPU: phần lớn thời gian luồng không chạy CPU; cần điều tra wait events, scheduler và các thành phần bên ngoài.

Với một luồng đơn, tỷ lệ này thường nằm trong khoảng 0–100% (sai số đo và cách lấy mẫu có thể ảnh hưởng kết quả). Với **nhiều luồng chạy song song**, tổng CPU time có thể lớn hơn elapsed time: hai luồng mỗi luồng dùng 100 ms CPU trong một khoảng 100 ms elapsed tạo ra tổng 200 ms CPU.

### Ví dụ: cùng thời gian phản hồi, mức tiêu thụ CPU khác nhau

| Request | Elapsed time | CPU time cộng trên các luồng | Diễn giải |
| --- | ---: | ---: | --- |
| A | 500 ms | 450 ms | Có khả năng CPU-bound |
| B | 500 ms | 35 ms | Nghiêng về I/O/lock/park hoặc scheduler wait |
| C | 500 ms | 700 ms | Nhiều luồng thực thi song song; tổng CPU vượt elapsed |

Các con số chỉ minh họa. Với request chạy bất đồng bộ qua nhiều executor, cần xác định rõ tập luồng liên quan và correlation ID; không thể chỉ đọc CPU time của luồng HTTP ban đầu rồi kết luận toàn bộ chi phí CPU của request.

## 4. Chọn công cụ theo câu hỏi

| Câu hỏi | Nên bắt đầu từ |
| --- | --- |
| Request/operation mất bao lâu từ đầu đến cuối? | Metrics/tracing hoặc elapsed timer |
| Một platform thread đã tiêu thụ bao nhiêu CPU? | `ThreadMXBean` |
| Method nào chiếm nhiều CPU trên Linux, kể cả native code? | JFR `jdk.CPUTimeSample` (JEP 509, experimental) |
| Stack nào thường được quan sát khi Java code đang chạy trên nhiều nền tảng? | JFR `jdk.ExecutionSample` |
| JVM và toàn máy đang sử dụng CPU thế nào? | JFR `jdk.CPULoad` |
| Luồng chờ monitor/park/sleep/socket/file bao lâu? | JFR duration events tương ứng |
| Một method có elapsed duration lớn dù không dùng nhiều CPU? | JFR `jdk.MethodTiming` (JEP 520) kết hợp wait events |

Không có một metric đơn lẻ trả lời được tất cả. Cách điều tra tốt là xác định elapsed time trước, sau đó xem CPU consumption và các event chờ để giải thích khoảng thời gian còn lại.

## 5. Đo CPU time tích lũy bằng ThreadMXBean

`java.lang.management.ThreadMXBean` cung cấp CPU time cho **platform threads** nếu JVM và hệ điều hành hỗ trợ. Có thể lấy bean qua `ManagementFactory.getThreadMXBean()`.

### Ví dụ đo CPU time của luồng hiện tại

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

public class ThreadCpuMeasurement {

    private static volatile long sink;

    public static void main(String[] args) {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();

        if (!bean.isCurrentThreadCpuTimeSupported()) {
            System.out.println("Current-thread CPU time is not supported");
            return;
        }

        if (!bean.isThreadCpuTimeEnabled()) {
            bean.setThreadCpuTimeEnabled(true);
        }

        long wallStart = System.nanoTime();
        long cpuStart = bean.getCurrentThreadCpuTime();

        doCpuWork();

        long cpuEnd = bean.getCurrentThreadCpuTime();
        long wallEnd = System.nanoTime();

        if (cpuStart < 0 || cpuEnd < 0) {
            System.out.println("CPU time is unavailable");
            return;
        }

        long wallNanos = wallEnd - wallStart;
        long cpuNanos = cpuEnd - cpuStart;

        double cpuShare = 100.0 * cpuNanos / wallNanos;

        System.out.printf("Elapsed: %.3f ms%n", wallNanos / 1_000_000.0);
        System.out.printf("CPU: %.3f ms%n", cpuNanos / 1_000_000.0);
        System.out.printf("CPU share: %.1f%%%n", cpuShare);
    }

    private static void doCpuWork() {
        long value = 0;
        for (long i = 0; i < 50_000_000L; i++) {
            value += (i * 31) % 97;
        }
        sink = value;
    }
}
~~~

Ví dụ dùng một vòng lặp CPU-bound để minh họa cách đọc chênh lệch hai bộ đếm. Kết quả cụ thể phụ thuộc CPU, JVM, JIT warm-up và tải máy; không dùng số chạy một lần làm benchmark.

### Những điều phải kiểm tra

- `isCurrentThreadCpuTimeSupported()` xác nhận khả năng đo CPU time của platform thread hiện tại.
- `isThreadCpuTimeSupported()` kiểm tra khả năng đo CPU time của các platform thread.
- `isThreadCpuTimeEnabled()` cho biết phép đo đã bật chưa.
- `setThreadCpuTimeEnabled(true)` có thể bật đo nếu JVM hỗ trợ; việc này có thể có overhead tùy implementation.
- `getCurrentThreadCpuTime()` trả về CPU time tích lũy của platform thread hiện tại, tính bằng nanosecond.
- Giá trị trả về có thể là `-1` nếu phép đo không khả dụng, bị tắt hoặc thread không phù hợp.

API bảo đảm độ chính xác biểu diễn theo nanosecond, nhưng không bảo đảm độ chính xác thực tế đến từng nanosecond. Không diễn giải số này như đồng hồ độ phân giải tuyệt đối.

### Đo thread khác

Có thể dùng `getThreadCpuTime(threadId)` cho một platform thread đang sống. Thread ID có thể được tái sử dụng sau khi thread kết thúc; chỉ so sánh các mốc đo trong vòng đời thread phù hợp. Nếu thread đã kết thúc, không tồn tại, là virtual thread hoặc CPU time không được bật, kết quả có thể là `-1`.

**Giới hạn quan trọng:** `ThreadMXBean` của Java 25 không hỗ trợ giám sát CPU time cho virtual threads. Nếu request được xử lý qua virtual threads hoặc nhiều carrier/executor, cần dùng JFR và telemetry theo request để hiểu chi phí tổng thể; không coi CPU time của thread HTTP ban đầu là tổng CPU time của request.

## 6. JFR profiling theo thời gian thực và theo CPU time

JFR có nhiều loại sampling event. Hai event dễ nhầm là:

| Event | Cách lấy mẫu | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| `jdk.ExecutionSample` | Theo chu kỳ elapsed/wall-clock sampling | Dùng được trên nhiều nền tảng; quan sát Java stack đang chạy | Có thể bỏ lỡ method ngắn hoặc thread ít được lấy mẫu; tập trung vào Java execution |
| `jdk.CPUTimeSample` | Theo lượng CPU time thread đã tiêu thụ | Linux-only; lấy mẫu theo CPU time và có thể thu stack cả khi thread chạy native | Experimental; cần bật riêng; không đo thời gian chờ; vẫn là sampling |

JFR CPU-time sampling của JEP 509 sử dụng cơ chế CPU timer trên Linux để lấy mẫu dựa theo CPU time thay vì chỉ dựa trên chu kỳ thời gian thực. Nó có thể ghi nhận stack khi thread thực thi Java code hoặc native code. Đây là lợi thế khi ứng dụng dành nhiều thời gian trong native libraries, JNI hoặc FFM.

**Sampling vẫn là thống kê.** Một profile cho biết method/call path nào nhận nhiều mẫu CPU, không phải bộ đếm chính xác số nanosecond cho từng lần gọi method. Chất lượng phụ thuộc thời lượng recording, sampling throttle, khả năng walk stack và số mẫu bị mất.

## 7. JEP 509 trong Java 25: CPU-time profiling trên Linux

JEP 509 thêm event `jdk.CPUTimeSample`. Trong Java 25:

- Tính năng **experimental** và chỉ áp dụng trên Linux.
- Event không bật mặc định; phải bật rõ ràng trong JFR recording.
- Không cần thêm `-XX:+UnlockExperimentalVMOptions` chỉ để bật event này.
- Tham số `throttle` có thể là chu kỳ CPU time (ví dụ `10ms`) hoặc giới hạn tốc độ phát event (ví dụ `500/s`).
- Event có thể báo sample thất bại hoặc bị lệch do safepoint; cần kiểm tra thống kê sample.
- Event `jdk.CPUTimeSamplesLost` ghi nhận số sample đã bị mất.

Tài liệu migration của JDK 26 vẫn ghi JFR CPU-time profiling là experimental. Vì vậy, hãy xem đây là một khả năng chẩn đoán có thể dùng có kiểm soát trên Linux, không phải API portable hoặc cam kết ổn định giống một Java SE API đã final.

### Bật CPU-time sampling khi khởi động

~~~bash
java -XX:StartFlightRecording:filename=cpu-time.jfr,settings=profile,jdk.CPUTimeSample#enabled=true,jdk.CPUTimeSample#throttle=500/s -jar app.jar
~~~

`500/s` là giới hạn tốc độ phát sample, phù hợp để bắt đầu thử nghiệm; nó không phải con số tối ưu cho mọi ứng dụng. Có thể đặt chu kỳ CPU time như `10ms` nếu cần cấu hình theo thời gian CPU của từng thread:

~~~bash
java -XX:StartFlightRecording:filename=cpu-time.jfr,settings=profile,jdk.CPUTimeSample#enabled=true,jdk.CPUTimeSample#throttle=10ms -jar app.jar
~~~

Với nhiều thread hoặc workload nhiều CPU, tốc độ sample cao làm tăng event volume, chi phí stack walking và nguy cơ mất mẫu. Hãy bắt đầu với tốc độ vừa phải, đo overhead và tăng dần nếu profile chưa đủ chi tiết.

### Xem hot methods và sample statistics

~~~bash
jfr view cpu-time-hot-methods cpu-time.jfr
jfr view cpu-time-statistics cpu-time.jfr
~~~

Có thể xem event thô:

~~~bash
jfr print --events jdk.CPUTimeSample,jdk.CPUTimeSamplesLost cpu-time.jfr
~~~

Khi phân tích, chú ý:

- **Successful samples:** số stack đã ghi nhận thành công.
- **Failed samples:** sample không lấy được stack trace.
- **Biased samples:** stack có thể phản ánh vị trí tại safepoint thay vì chính xác thời điểm timer yêu cầu.
- **Lost samples:** sample đã bị mất do giới hạn hàng đợi/buffer hoặc áp lực ghi dữ liệu.

Nếu tỷ lệ sample thất bại, biased hoặc lost cao, profile có thể chưa đại diện đủ cho workload. Giảm sampling rate, kéo dài recording hoặc điều tra điều kiện hệ thống trước khi đưa ra kết luận tối ưu code.

## 8. CPU load của JVM và CPU load của máy

JFR event `jdk.CPULoad` giúp phân biệt CPU của process JVM với mức sử dụng CPU tổng thể của máy. Event có các trường chính:

- `jvmUser`: CPU user mode của JVM.
- `jvmSystem`: CPU system mode của JVM.
- `machineTotal`: CPU tổng thể của máy.

Một số tình huống:

| JVM CPU | Machine CPU | Hướng điều tra |
| --- | --- | --- |
| Cao | Cao | JVM có thể đang tiêu thụ nhiều CPU; xem CPU-time profile |
| Thấp | Cao | Process khác hoặc workload khác trên host có thể đang dùng CPU |
| Thấp | Thấp | Có thể bottleneck nằm ở I/O, lock, dependency hoặc tải đầu vào thấp |
| Cao từng đợt | Thay đổi theo đợt | Đối chiếu workload, GC, thread activity và request bursts |

Không suy luận CPU-bound chỉ từ CPU machine cao. Cần tách process JVM khỏi các process khác và kiểm tra container CPU throttling nếu chạy trong container.

## 9. JFR duration events để tìm trạng thái chờ

CPU-time sample chỉ xuất hiện khi thread tiêu thụ CPU. Một thread chờ database hoặc lock có thể không tạo ra CPU samples đáng kể, dù request vẫn mất nhiều thời gian.

Các event sau giúp xác định một số nguyên nhân chờ:

| Event | Điều được ghi nhận | Câu hỏi điều tra |
| --- | --- | --- |
| `jdk.JavaMonitorEnter` | Chờ lấy intrinsic monitor | Có lock contention hoặc critical section quá dài không? |
| `jdk.JavaMonitorWait` | Chờ từ `Object.wait()` | Thread đang đợi notification/điều kiện nào? |
| `jdk.ThreadPark` | Thread bị park | Executor, synchronizer hoặc semaphore có làm thread chờ không? |
| `jdk.ThreadSleep` | Thread sleep | Có delay/polling không cần thiết không? |
| `jdk.SocketRead` / `jdk.SocketWrite` | Thời gian thao tác socket | Network hoặc remote service có chậm không? |
| `jdk.FileRead` / `jdk.FileWrite` | Thời gian thao tác file | Storage hoặc file access có phải bottleneck không? |

JFR event có threshold và throttle. Nếu threshold quá cao, các lần chờ ngắn có thể không xuất hiện trong recording. Nếu hạ threshold hoặc tắt throttle, số event và overhead có thể tăng mạnh. Cần điều chỉnh cho một recording chẩn đoán ngắn thay vì bật mọi event ở mức chi tiết cao liên tục.

### Lưu ý riêng cho JDK 25

Trong JDK 25, mặc định của `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead` và `jdk.FileWrite` đã được điều chỉnh: threshold 1 ms và rate limit 100 event/giây trong default configuration. Các Java Application duration events khác thường có ngưỡng mặc định cao hơn, ví dụ 20 ms. Hãy kiểm tra file `.jfc` đang dùng và cấu hình thực tế thay vì giả định mọi event có cùng threshold.
Thay đổi threshold/rate limit này được ghi trong [Consolidated JDK 25 Release Notes](https://www.oracle.com/java/technologies/javase/25all-relnotes.html) (JDK-8351594).

## 10. Phân biệt method elapsed time với method CPU time

JDK 25 còn có JEP 520 — JFR Method Timing & Tracing, cung cấp các event `jdk.MethodTiming` và `jdk.MethodTrace` qua bytecode instrumentation.

Đây là công cụ bổ trợ, nhưng không thay thế CPU-time sampling:

- `jdk.MethodTiming` đo **thời gian method đi từ entry đến exit**, bao gồm cả các khoảng delay/chờ nằm bên trong lời gọi method.
- `jdk.MethodTrace` ghi từng invocation và thông tin trace theo cấu hình.
- `jdk.CPUTimeSample` lấy mẫu stack dựa trên CPU time thread đã tiêu thụ.

Ví dụ, một method gọi database mất 400 ms elapsed nhưng chỉ có 8 ms CPU. `MethodTiming` có thể cho thấy method mất khoảng 400 ms; CPU-time profile sẽ không quy toàn bộ 400 ms đó thành CPU work. Hãy dùng wait/I/O events để giải thích khoảng thời gian còn lại.

JEP 520 hữu ích khi cần điều tra một số method cụ thể, nhưng instrumentation từng invocation có thể tạo overhead lớn nếu áp dụng quá rộng. Bắt đầu từ sampling để tìm khu vực đáng nghi, rồi chỉ bật method timing/tracing cho tập method nhỏ.

## 11. Quy trình recording JFR để điều tra CPU và wait

Có thể bắt đầu recording khi khởi động:

~~~bash
java -XX:StartFlightRecording:filename=performance.jfr,settings=profile,duration=120s -jar app.jar
~~~

Hoặc attach vào process đang chạy:

~~~bash
jcmd <pid> JFR.start name=performance settings=profile duration=120s filename=performance.jfr
~~~

Sau recording, xem tổng quan và các event cần thiết:

~~~bash
jfr summary performance.jfr
jfr print --events jdk.CPULoad,jdk.ExecutionSample,jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.ThreadSleep,jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite performance.jfr
~~~

Nếu đang trên Linux và cần CPU-time sampling, tạo recording với `jdk.CPUTimeSample#enabled=true` như phần 7. Đừng bật đồng thời mọi event và sampling rate cực cao ngay từ đầu; hãy mở rộng theo giả thuyết đang kiểm tra.

### Tạo cấu hình riêng cho wait events

Có thể tạo file JFC dựa trên profile hiện có rồi điều chỉnh threshold cho một số event cần xem kỹ:

~~~bash
jfr configure --input profile.jfc --output wait-investigation.jfc jdk.JavaMonitorEnter#threshold=5ms jdk.JavaMonitorWait#threshold=5ms jdk.ThreadPark#threshold=5ms
~~~

Sau đó:

~~~bash
java -XX:StartFlightRecording:settings=wait-investigation.jfc,filename=wait.jfr,duration=60s -jar app.jar
~~~

Threshold thấp hơn có thể thu được nhiều lần chờ ngắn hơn nhưng cũng tăng event volume và overhead. Dùng recording ngắn, có workload đại diện và so sánh với baseline không profiling nếu cần đánh giá ảnh hưởng của instrumentation.

## 12. Cách diễn giải một số mẫu kết quả

### Trường hợp A — CPU-bound

- Elapsed time cao.
- CPU time cao.
- CPU-time samples tập trung ở một số method/call paths.
- Wait events không chiếm phần lớn thời gian.

Hướng xử lý: xem hot methods, allocation, thuật toán, vòng lặp, serialization, regex hoặc native code. Dùng benchmark có kiểm soát để xác nhận cải thiện sau tối ưu.

### Trường hợp B — I/O-bound

- Elapsed time cao.
- CPU time thấp.
- Có nhiều `SocketRead`/`SocketWrite` hoặc `FileRead`/`FileWrite` duration.
- CPU-time profile không có nhiều sample ở code chờ.

Hướng xử lý: đo latency dependency, connection pool, network, batching, timeout, retry và backpressure. Tối ưu vòng lặp CPU có thể không cải thiện đáng kể.

### Trường hợp C — Lock contention

- Elapsed time của request tăng khi concurrency tăng.
- CPU time trên thread chờ không tăng tương ứng.
- Có `JavaMonitorEnter` hoặc `JavaMonitorWait` duration kéo dài.
- Stack trace cho thấy nhiều thread cùng chờ một lock.

Hướng xử lý: rút ngắn critical section, giảm chia sẻ mutable state, tránh giữ lock trong lúc I/O, cân nhắc cấu trúc đồng bộ khác.

### Trường hợp D — Park hoặc sleep

- Thread có nhiều thời gian elapsed nhưng ít CPU samples.
- `ThreadPark` hoặc `ThreadSleep` xuất hiện trong recording.

Hướng xử lý: xem executor queue, semaphore, rate limiter, polling interval và điều kiện đánh thức. Park không mặc định là lỗi; nó có thể là hành vi chờ đúng thiết kế.

### Trường hợp E — JVM CPU thấp, host CPU cao

- `jdk.CPULoad` cho thấy JVM dùng ít CPU nhưng machine total cao.
- Các process khác hoặc container khác trên node có thể đang tranh CPU.

Hướng xử lý: kiểm tra OS process list, cgroup/container throttling, CPU quota và mức co-tenancy. Đừng tối ưu code Java trước khi xác định đúng process tiêu thụ CPU.

## 13. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Request mất 1 giây nghĩa là dùng CPU 1 giây.” | Elapsed time có thể bao gồm nhiều thời gian chờ. |
| “Elapsed trừ CPU là thời gian I/O.” | Phần chênh lệch còn có scheduler delay, lock, park, GC/safepoint và các khoảng chưa được ghi event. |
| “Thread ở trạng thái RUNNABLE là đang chạy trên CPU.” | RUNNABLE không bảo đảm đang được scheduler cấp CPU tại đúng thời điểm quan sát. |
| “JFR CPU-time profile cho thời gian chính xác từng method.” | Đây là sampling; kết quả thống kê phụ thuộc sample count và sample loss. |
| “jdk.ExecutionSample và jdk.CPUTimeSample giống nhau.” | Một event lấy mẫu theo thời gian thực; event kia lấy mẫu theo CPU time trên Linux. |
| “CPU-time profiling hoạt động trên mọi OS.” | JEP 509 của JDK 25 là Linux-only và experimental. |
| “ThreadMXBean đo được virtual-thread CPU time.” | Java 25 ThreadMXBean hỗ trợ platform threads, không hỗ trợ virtual threads. |
| “Không thấy wait event nghĩa là không có chờ.” | Threshold, throttle và loại event có thể khiến khoảng chờ không được ghi nhận. |
| “MethodTiming là CPU time.” | MethodTiming phản ánh elapsed duration của method, gồm cả delay/chờ. |
| “Cứ tăng sample rate thì profile luôn tốt hơn.” | Sample rate cao tăng overhead, event volume và nguy cơ mất sample. |

## 14. Lưu ý khi ứng dụng dùng virtual threads

Java 25 hỗ trợ virtual threads như một phần của Java hiện đại, nhưng không phải công cụ đo CPU nào cũng quy chiếu trực tiếp tới virtual thread.

- `ThreadMXBean` không cung cấp CPU time cho virtual threads.
- Khi virtual thread bị park, nó có thể nhường carrier thread; CPU time của carrier không đồng nghĩa CPU time của riêng một request.
- JFR wait events và thread identity giúp quan sát các giai đoạn park/wait, nhưng cần đối chiếu với trace/correlation ID để theo dõi một request đi qua nhiều luồng.
- Với workload dùng nhiều virtual threads, không cộng CPU time của một carrier rồi gán cho một virtual thread cụ thể nếu không có dữ liệu liên kết phù hợp.
- JEP 509 CPU-time sampling cần được đánh giá trên đúng Linux/JDK build; không suy ra rằng mọi virtual-thread CPU usage đều được phân bổ chính xác theo task/request.

Nếu cần chi phí CPU theo request, kết hợp CPU profiling cấp JVM với tracing/metrics cấp ứng dụng và thiết kế context propagation. CPU profile trả lời “CPU đang chạy code nào”; trace trả lời “request nào đi qua thành phần nào và mất bao lâu”.

## 15. Overhead, độ tin cậy và an toàn dữ liệu

JFR profiling recording mặc định thường có overhead thấp, nhưng mức thực tế tùy workload và cấu hình. CPU-time sampling có thể tạo nhiều event trên máy nhiều core hoặc ứng dụng nhiều thread; method tracing, stack traces và threshold thấp cũng có thể tăng overhead.

Thực hành tốt:

1. Bắt đầu bằng recording ngắn với profile settings.
2. Chỉ bật `jdk.CPUTimeSample` khi chạy trên Linux và cần CPU-time profile.
3. Chọn throttle vừa phải, sau đó điều chỉnh theo chất lượng profile.
4. Theo dõi event loss, failed/biased samples và kích thước file recording.
5. Chỉ hạ threshold của wait events khi cần bắt các khoảng ngắn.
6. Không bật method tracing cho hàng trăm method nóng nếu chưa đo overhead.
7. Không bật heap statistics khi chỉ điều tra CPU/wait; tính năng này có thể gây thêm old GC và làm sai phép đo latency.
8. Bảo vệ file `.jfr` vì recording có thể chứa tên class, method, thread, socket/file path, system properties và stack traces.

Khi chia sẻ recording, dùng `jfr scrub` để lọc event/threads nhạy cảm theo yêu cầu. Không mặc định file JFR an toàn để công khai chỉ vì nó không chứa source code.

## 16. Bài thực hành: cùng một elapsed time nhưng CPU time khác nhau

### Bối cảnh

Bạn có một service với ba thao tác giả lập:

- Một thao tác tính toán CPU-bound.
- Một thao tác ngủ bằng `Thread.sleep`.
- Một thao tác chờ monitor do thread khác giữ lock.

Cả ba có thể mất vài trăm millisecond elapsed, nhưng CPU time và JFR wait events khác nhau.

### Nhiệm vụ

1. Tạo một tác vụ CPU-bound bằng vòng lặp tính toán và ghi nhận kết quả để tránh compiler loại bỏ công việc.
2. Tạo một tác vụ sleep trong khoảng thời gian cố định.
3. Tạo hai platform threads tranh cùng một monitor; giữ lock ở thread thứ nhất rồi cho thread thứ hai chờ.
4. Dùng `ThreadMXBean` đo CPU time của platform thread hiện tại trong một đoạn code đồng bộ.
5. Ghi JFR profile trong 60–120 giây với workload lặp lại.
6. Trên Linux/JDK 25, bật `jdk.CPUTimeSample` với throttle ban đầu `500/s`.
7. Xem `cpu-time-hot-methods` và đối chiếu hot method với tác vụ CPU-bound.
8. Xem `JavaMonitorEnter`, `ThreadSleep` và `ThreadPark` để nhận diện trạng thái chờ.
9. So sánh elapsed duration với CPU time; giải thích vì sao phần chênh lệch không tự động bằng thời gian I/O.
10. Kiểm tra event lost/failed/biased samples trước khi tin vào profile.

### Câu hỏi tự đánh giá

1. CPU time của một platform thread bao gồm những chế độ CPU nào?
2. Vì sao một request có thể mất 500 ms elapsed nhưng chỉ dùng 20 ms CPU?
3. Vì sao `System.nanoTime()` phù hợp để đo duration hơn `currentTimeMillis()`?
4. `ThreadMXBean.getThreadCpuTime` trả về gì và khi nào có thể trả `-1`?
5. Vì sao `ThreadMXBean` không đo CPU time cho virtual threads?
6. `jdk.ExecutionSample` khác `jdk.CPUTimeSample` ở cơ chế lấy mẫu nào?
7. JEP 509 giới hạn trên nền tảng nào và trạng thái của nó trong JDK 25 là gì?
8. `throttle=500/s` có tác dụng gì?
9. Vì sao phải xem `jdk.CPUTimeSamplesLost`?
10. Khi nào nên xem `JavaMonitorEnter` thay vì hot methods?
11. Vì sao `jdk.MethodTiming` không phải phép đo CPU time?
12. Vì sao không được kết luận elapsed trừ CPU bằng đúng thời gian chờ I/O?

## 17. Checklist điều tra CPU và wait states

- [ ] Đã xác định metric cần giải thích là elapsed, CPU time, throughput hay latency.
- [ ] Đã dùng monotonic clock để đo duration.
- [ ] Đã kiểm tra hỗ trợ và trạng thái bật CPU-time measurement của `ThreadMXBean`.
- [ ] Đã xác định thread được đo là platform thread hay virtual thread.
- [ ] Đã tạo JFR recording trong workload đại diện.
- [ ] Đã phân biệt `ExecutionSample` với `CPUTimeSample`.
- [ ] Nếu dùng JEP 509, đã xác nhận đang chạy Linux và chấp nhận trạng thái experimental.
- [ ] Đã chọn throttle và đánh giá overhead.
- [ ] Đã xem sample failure, bias và lost-sample events.
- [ ] Đã kiểm tra `CPULoad` để phân biệt CPU của JVM với toàn máy.
- [ ] Đã xem monitor, park, sleep và I/O duration events.
- [ ] Đã kiểm tra threshold/throttle thực tế của JFR recording.
- [ ] Không coi elapsed trừ CPU là wait time chính xác.
- [ ] Không nhầm MethodTiming wall-clock duration với CPU time.
- [ ] Đã bảo vệ recording trước khi chia sẻ.

**Tiêu chí hoàn thành:** người học có thể giải thích một request chậm do CPU-bound hay do chờ bằng cách đối chiếu elapsed time, CPU time và JFR wait events. Người học biết dùng JEP 509 trong phạm vi Linux/experimental của Java 25, kiểm tra chất lượng sampling và tránh diễn giải sai thời gian method hoặc phần chênh lệch CPU–wall time.

## 18. Tài liệu chính thức và tham khảo

- [JEP 509 — JFR CPU-Time Profiling (Experimental)](https://openjdk.org/jeps/509): CPU-time sampling trên Linux, event `jdk.CPUTimeSample` và giới hạn experimental.
- [Oracle JDK 25 — Significant Changes: Monitoring](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): trạng thái và phạm vi JFR CPU-Time Profiling, Cooperative Sampling, Method Timing & Tracing.
- [Java SE 25 — ThreadMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html): CPU time cho platform threads, khả năng hỗ trợ, bật/tắt và giới hạn virtual threads.
- [Oracle JDK 25 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html): CPU load, monitor wait, thread sleep/park, socket và file I/O events.
- [Java SE 25 — JFR Package](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html): cấu hình event, threshold, period, throttle và recording settings.
- [The jfr Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `jfr print`, `jfr view`, `jfr configure`, `jfr summary`.
- [JEP 518 — JFR Cooperative Sampling](https://openjdk.org/jeps/518): cải thiện độ ổn định của stack sampling và giảm safepoint bias.
- [JEP 520 — JFR Method Timing & Tracing](https://openjdk.org/jeps/520): đo và trace method qua bytecode instrumentation, bổ sung cho CPU sampling.
- [Inside Java — What's New for JFR in JDK 25](https://inside.java/2025/06/03/new-jfr-jdk25/): hướng dẫn JDK 25 về CPU-time sampling, method timing/tracing và các event mới.
- [JDK 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/jdk-migration-guide.pdf): kiểm tra trạng thái experimental của CPU-time profiling khi nâng JDK.

Khi áp dụng trên vendor hoặc JDK build khác nhau, kiểm tra event metadata và JFR configuration thực tế. JEP 509 của Java 25 là công cụ Linux-only, experimental; các event wait và ThreadMXBean có phạm vi hỗ trợ riêng. Không giả định mọi event hoặc mọi phép đo CPU đều có mặt và có cùng ngữ nghĩa trên mọi runtime.
