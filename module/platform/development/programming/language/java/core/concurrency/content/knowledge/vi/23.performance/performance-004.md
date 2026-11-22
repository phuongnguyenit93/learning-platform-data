# CPU saturation so với I/O wait trong Java Concurrency

## 1. Vì sao phải phân biệt?

Khi chương trình Java xử lý chậm, tăng số thread thường là phản xạ đầu tiên. Nhưng một ứng dụng có thể chậm vì **CPU không còn đủ thời gian thực thi**, vì **thread đang chờ dữ liệu hoặc tài nguyên I/O**, hoặc vì **lock, queue, GC, scheduler và giới hạn hệ thống**. Những tình huống này có triệu chứng gần giống nhau nhưng hướng xử lý khác nhau.

Bài học tập trung vào Java Concurrency và cách đối chiếu **JVM + hệ điều hành + số liệu của workload**, không sử dụng cơ chế concurrency riêng của Spring.

Sau bài này, bạn có thể:
- Phân biệt CPU utilization, CPU saturation, wall-clock time, thread CPU time và I/O wait.
- Hiểu chính xác ý nghĩa `%wa` trên Linux và lý do nó không đo mọi kiểu thread “đang chờ I/O”.
- Đọc kết hợp `vmstat`, `mpstat`, `pidstat`, `iostat`, thread dump và Java Flight Recorder (JFR).
- Chọn chiến lược executor, giới hạn concurrency và cách tối ưu khác nhau cho workload CPU-bound và I/O-bound.
- Phân biệt hiện tượng chờ I/O với contention, thread pool starvation, GC, CPU throttling và thời gian nằm trong hàng đợi.

## 2. Các đại lượng không được đánh đồng

### 2.1. CPU utilization: CPU bận bao nhiêu?

**CPU utilization** mô tả tỷ lệ thời gian CPU làm việc trong cửa sổ quan sát. Nó là thước đo **mức sử dụng**, chưa tự nói rằng CPU đang quá tải. Một CPU chạy 95% nhưng tất cả request vẫn đạt latency mục tiêu có thể đang làm việc hữu ích. Ngược lại, hệ thống 16 logical CPU có tổng mức dùng 7% nhưng một thread xử lý tuần tự đã ghim chặt **một core** gần 100%, khiến một request cụ thể không thể nhanh hơn nhờ thêm thread.

Khi xem phần trăm CPU, phải hỏi:
- Đó là **một logical CPU**, **tổng máy**, **process Java**, hay **từng OS thread**?
- Công cụ báo 100% cho **một core** hay cho **toàn bộ máy**? Ví dụ `top` trên Linux thường có thể hiển thị process đa luồng vượt 100% tùy chế độ quy đổi.
- JVM chạy trong container có CPU quota/cpuset/affinity khác với số CPU vật lý của host không?
- CPU busy dành cho mã ứng dụng, GC, kernel, mã native hay một tiến trình khác?

### 2.2. CPU saturation: nhu cầu CPU vượt năng lực phục vụ

**CPU saturation** là tình trạng lượng công việc sẵn sàng chạy cần nhiều CPU hơn khả năng cấp phát trong khoảng thời gian liên quan. Một số task phải chờ được scheduler cấp thời gian CPU; queue/CPU pressure tăng. Dấu hiệu thường gặp:

1. CPU hữu dụng gần mức trần trên nhiều core liên quan hoặc đụng CPU quota.
2. Số thread/process runnable lớn và kéo dài so với năng lực CPU khả dụng; run queue hoặc CPU pressure cao.
3. Tăng thêm task/thread làm throughput tăng rất ít hoặc đứng yên, trong khi latency và thời gian đợi scheduler tăng.
4. Nhiều thread Java đang thực hiện tính toán, vòng lặp, parsing, mã hóa, nén hoặc GC tiêu thụ CPU.

**CPU busy cao không đủ để kết luận saturation**; cần bằng chứng về nhu cầu đang chờ. **CPU busy tổng thể thấp không đủ để bác bỏ saturation** của một core, cpuset, quota container hoặc một hot thread.

### 2.3. Wall-clock time và thread CPU time

- **Wall time:** thời gian thực từ lúc bắt đầu đến khi kết thúc, gồm thời gian chạy, bị scheduler tạm ngưng, chờ khóa, sleep, chờ I/O, GC pause và các khoảng đợi khác.
- **Thread CPU time:** thời gian một OS/platform thread thực sự được CPU thực thi trong user/kernel mode, khi môi trường hỗ trợ số liệu đó. Trong Java có `ThreadMXBean.getCurrentThreadCpuTime()`.
- **Wall − CPU** *không thể* được gán hết cho I/O. Chênh lệch này còn gồm queue, monitor/lock, park, sleep, preemption, GC pause và scheduling.

Với một platform thread đo trong một khoảng, tỷ số `CPU time / wall time` gần 1 cho thấy phần lớn thời gian thread được chạy trên CPU; gần 0 cho thấy thread không dùng CPU nhiều trong khoảng đo. Đây là **dấu hiệu định hướng**, không phải bộ phân loại chính xác nguyên nhân đợi. Khi nhiều worker cùng chạy trên nhiều core, tổng CPU time của chúng có thể lớn hơn wall time của toàn batch.

### 2.4. Linux I/O wait: `%wa` đo gì?

Trên Linux, `wa` trong `vmstat` hay `%iowait` trong `mpstat`/`top` là cách hệ điều hành hạch toán phần **thời gian CPU idle trong khi có tác vụ I/O đang chờ** theo định nghĩa kernel/counter. Nó thường hữu ích khi điều tra **block/storage I/O**.

Nó **không phải**:
- “Phần trăm thời gian Java thread chờ I/O”.
- “Phần trăm request bị trễ vì mạng”.
- “Phần trăm disk đang bận”.
- Bộ đếm trực tiếp thời gian từng thread Java đang đợi socket, connection pool hay database.

`%wa` có thể gần **0% dù hàng nghìn thread đang chờ network**: CPU không nhất thiết idle theo điều kiện hạch toán iowait, và nhiều tình trạng chờ socket không được biểu diễn bằng chỉ số này. Nó cũng có thể thấp khi disk đang rất chậm nhưng CPU khác vẫn bận. Trên hệ nhiều core, hot task ở core khác, thời điểm lấy mẫu, hoạt động kernel và cách hạch toán khiến việc suy ra “ứng dụng không chờ I/O” từ `wa=0` là sai. Ngược lại, `%wa` cao là tín hiệu cần điều tra storage, không tự chứng minh disk là nguyên nhân cuối cùng.

**Quy tắc:** Muốn khẳng định một request Java đang đợi **điều gì**, cần đối chiếu latency/counter của hoạt động đó (file/socket/DB) với JVM traces, không chỉ nhìn `%wa`.

## 3. Mô hình phân loại bottleneck

| Tình huống | Hiện tượng nổi bật | Chỉ số cần ghép | Hướng xử lý |
|---|---|---|---|
| CPU-bound gần saturation | Core/quota đầy, runnable tăng, latency tăng khi tăng concurrency | CPU per-core/process/thread, run queue, CPU pressure, JFR CPU samples | Giảm CPU/task, tối ưu thuật toán, giới hạn worker, tăng CPU khi cần |
| Block/storage I/O chậm | File read/write/fsync có latency lớn, queue disk tăng; `wa` có thể cao | `iostat` latency/queue, JFR file events, filesystem metrics | Giảm I/O, batching, cache đúng, cải thiện storage |
| Network/remote I/O chậm | Socket read/connect hoặc backend response lâu; CPU Java có thể thấp | JFR socket events, timeout, network và backend metrics | Giới hạn in-flight, timeout, connection pool phù hợp, tối ưu backend |
| Lock contention | Nhiều thread đợi cùng monitor/lock, CPU có thể thấp | JFR monitor/park events, thread dump, lock profiling | Giảm shared mutable state, hạ phạm vi khóa, thay kiến trúc phối hợp |
| Thread pool starvation / queue dài | Task đợi trong queue, worker bận/chặn; tổng CPU có thể thấp | Active workers, queue length, task submit-to-start latency | Tách pool CPU/I/O, bounded queue, backpressure, tránh blocking join |
| GC / allocation pressure | CPU bị GC chiếm, pause tăng, throughput không tăng | JFR allocation/GC, heap/GC logs, process CPU | Giảm phân bổ, xem heap và GC theo chứng cứ |
| Container throttling | CPU ở mức quota, request chậm dù host còn core rảnh | cgroup CPU throttling, quota, CPU pressure | Điều chỉnh quota, giảm tải, giới hạn concurrency |

**Saturation là quan hệ giữa nhu cầu và công suất**, còn “CPU-bound/I/O-bound” mô tả **công việc mất thời gian chủ yếu vào đâu**. Có thể đồng thời tồn tại CPU saturation và I/O bottleneck ở các giai đoạn khác nhau của một pipeline.

## 4. Các trạng thái thread Java không tương đương trạng thái CPU/I/O

`Thread.State` có: `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED`.

- `RUNNABLE`: thread đang thực thi trong JVM **hoặc có thể đang thực thi/wait trong native code**; riêng trạng thái này **không chứng minh đang chiếm CPU**. Một thread đang ở native socket read vẫn có thể được trình bày là `RUNNABLE` trong thread dump của platform thread, tùy JDK/implementation.
- `BLOCKED`: thread chờ giành **intrinsic monitor** (`synchronized`). Nó không có nghĩa là Linux process ở trạng thái D hoặc đang đợi block-device I/O.
- `WAITING`/`TIMED_WAITING`: có thể đến từ `Object.wait()`, `LockSupport.park()`, condition, `Future.get()`, `Thread.sleep()` và các dạng phối hợp khác. Chúng **không mặc nhiên là I/O wait**.
- Với **virtual threads (Java 21+)**, thao tác blocking được hỗ trợ thường có thể khiến virtual thread unmount/park trong khi carrier phục vụ việc khác; số virtual thread chờ cao không tương đương số OS thread chờ tương ứng.

Do đó, thread dump cần **stack trace** và **mẫu qua thời gian**. Một ảnh chụp duy nhất ở `RUNNABLE` hoặc `WAITING` không đủ để kết luận phần lớn latency phát sinh từ đâu. Dùng JFR + hệ điều hành + metrics ứng dụng để tăng độ tin cậy.

## 5. Ví dụ runnable Java 17+: thấy rõ wall time khác CPU time

Ví dụ dưới đây thực hiện một phép tính thuần CPU, sau đó `sleep` để mô phỏng một khoảng chờ. **Sleep chỉ minh họa thời gian không dùng CPU; nó không tạo block-device I/O và không phải phép thử Linux `%iowait`.**

Lưu toàn bộ vào `CpuTimeVsWallTimeDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.Locale;

public class CpuTimeVsWallTimeDemo {
    private static volatile long observed;

    @FunctionalInterface
    interface CheckedTask {
        void run() throws Exception;
    }

    private static void measure(
            String label, CheckedTask task, ThreadMXBean bean) throws Exception {
        long cpuStart = bean.getCurrentThreadCpuTime();
        long wallStart = System.nanoTime();

        task.run();

        long wallNanos = System.nanoTime() - wallStart;
        long cpuNanos = bean.getCurrentThreadCpuTime() - cpuStart;
        double wallMillis = wallNanos / 1_000_000.0;
        double cpuMillis = cpuNanos / 1_000_000.0;
        double ratio = 100.0 * cpuNanos / wallNanos;

        System.out.printf(
            Locale.ROOT,
            "%s: wall=%.1f ms, cpu=%.1f ms, CPU/wall=%.1f%%%n",
            label, wallMillis, cpuMillis, ratio
        );
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();

        if (!bean.isCurrentThreadCpuTimeSupported()) {
            System.out.println("Thread CPU time không được hỗ trợ.");
            return;
        }
        if (!bean.isThreadCpuTimeEnabled()) {
            try {
                bean.setThreadCpuTimeEnabled(true);
            } catch (SecurityException | UnsupportedOperationException ex) {
                System.out.println("Không thể bật đo thread CPU time.");
                return;
            }
        }

        measure("Tính toán", () -> {
            long sum = 0;
            for (long i = 0; i < 40_000_000L; i++) {
                sum += (i * 31) ^ (i >>> 3);
            }
            observed = sum;
        }, bean);

        measure("Chờ giả lập", () -> Thread.sleep(400), bean);
        System.out.println("Đã hoàn thành hai pha đo.");
    }
}
```

Chạy bằng JDK 17+:

```bash
javac CpuTimeVsWallTimeDemo.java
java CpuTimeVsWallTimeDemo
```

Định dạng đầu ra (các giá trị thời gian và tỷ số **phụ thuộc máy, JIT, scheduling** nên không có số cố định):

```text
Tính toán: wall=<số> ms, cpu=<số> ms, CPU/wall=<số>%
Chờ giả lập: wall=<số> ms, cpu=<số> ms, CPU/wall=<số>%
Đã hoàn thành hai pha đo.
```

Trong pha tính toán, thread thường tiêu tốn phần lớn wall time vào CPU. Trong pha sleep, wall time xấp xỉ hoặc lớn hơn 400 ms còn CPU time thường rất nhỏ. Nếu thread bị preempt hoặc container bị throttling, pha CPU cũng có thể có `CPU/wall` thấp dù code chỉ tính toán. `ThreadMXBean` là công cụ quan sát, **không** tạo ra chỉ số `iowait`; thời gian CPU chỉ là một phần bằng chứng.

Trong benchmark thật, không dùng ví dụ này để so tốc độ giữa các JDK/máy: JIT warmup, độ tối ưu vòng lặp, tần số CPU và việc biên dịch lại code ảnh hưởng đáng kể. Dùng JMH cho microbenchmark tính toán khi thích hợp.

## 6. Đọc đúng số liệu Linux: từ máy tới tiến trình Java

Các lệnh dưới đây dành cho **Linux**; nhiều lệnh trong gói `sysstat` (`mpstat`, `pidstat`, `iostat`) có thể phải cài thêm. Lấy nhiều mẫu trong khoảng xảy ra sự cố, không kết luận từ một snapshot.

### 6.1. CPU per-core và run queue

```bash
vmstat 1
mpstat -P ALL 1
```

Cách đọc:
- `vmstat r`: số task ở trạng thái runnable (đang chạy hoặc đợi CPU). Nếu `r` liên tục cao tương quan với số CPU khả dụng và latency tăng, nghi ngờ CPU pressure; nhưng cần xét cpuset/quota và từng core.
- `vmstat b`: số task đang ở trạng thái uninterruptible sleep, thường gắn với một số hoạt động kernel/I/O; không được nhầm với Java `Thread.State.BLOCKED`.
- `us`, `sy`, `id`, `wa`: tỷ lệ CPU user, system, idle, iowait. Đừng cộng `wa` vào CPU “bận thực thi mã Java”.
- `mpstat -P ALL`: xem core nào đạt trần và core nào còn rảnh. Tổng trung bình thấp có thể giấu một core nóng.

Với `vmstat`, mẫu đầu thường là tổng trung bình từ lúc boot; hãy quan sát các mẫu tiếp theo. Cần cân nhắc môi trường ảo hóa, hypervisor steal time (`st`) và CPU quota.

### 6.2. Process và OS thread Java

```bash
pidstat -u -t -p <PID> 1
top -H -p <PID>
```

Thay `<PID>` bằng PID thực khi chạy. Cả process lẫn OS thread có thể được quan sát theo CPU. Nếu chỉ vài thread bận, xem stack ứng với chúng bằng:

```bash
jcmd <PID> Thread.print -l
```

Trong một số môi trường HotSpot/Linux, thread dump của platform thread hiển thị `nid=0x...` (native thread ID dạng hex). Có thể đối chiếu với TID hệ điều hành bằng chuyển đổi thập phân ↔ hex. Hãy lấy mẫu gần nhau về thời gian và nhớ rằng virtual threads không ánh xạ 1:1 với OS threads. Stack có thể thay đổi trong khoảng thu thập, vì vậy không khẳng định một thread “luôn” tiêu CPU chỉ từ một dump.

Ví dụ phân tích hợp lý: `pidstat` cho thấy cùng một OS thread liên tục ăn gần một core và JFR CPU samples tập trung vào `parseRecord()`. Khi ấy bottleneck nhiều khả năng là tính toán/parsing; cần đo và tối ưu phần nóng đó trước khi tăng worker.

### 6.3. Storage I/O

```bash
iostat -xz 1
pidstat -d -p <PID> 1
```

Quan sát đồng thời:
- `r/s`, `w/s`, lượng dữ liệu đọc/ghi: khối lượng I/O.
- `r_await`, `w_await` hoặc `await` (tùy phiên bản): thời gian trung bình yêu cầu I/O được xử lý, có thể bao gồm xếp hàng.
- `aqu-sz`/độ sâu hàng đợi và xu hướng latency: bằng chứng tắc nghẽn tài nguyên storage.
- `%util`: chỉ số bận của block device; **không** tự áp ngưỡng “100% = bão hòa” cho mọi SSD/NVMe đa hàng đợi.
- `pidstat -d`: lượng I/O process tạo ra; cần cẩn trọng với page cache, delayed write và I/O do tiến trình khác.

Chỉ số block device cao phải **khớp thời điểm** với latency file/DB hoặc JFR file read/write trước khi quy nguyên nhân. Một lệnh `read()` đọc từ page cache có thể hoàn thành nhanh, dù ứng dụng vẫn xử lý nhiều byte.

### 6.4. Network I/O

Khi thread Java đang chờ HTTP/DB/socket qua mạng, thu thập:
- **Client:** request latency, connect latency, read latency, timeout count, retries, số kết nối được thuê/đang chờ pool, số request in-flight.
- **Server/backend:** thời gian xử lý, queue, giới hạn connection, throttling/rate limit.
- **Hệ điều hành/mạng:** RTT, retransmission, packet drops, socket queues và DNS/TLS khi liên quan.
- **JFR:** `jdk.SocketRead`, `jdk.SocketWrite` hoặc các sự kiện tương ứng được bật trong cấu hình ghi.

Network wait **không nhất thiết làm `%wa` tăng**. Nhiều request chờ response dài nhưng CPU dùng thấp là điều bình thường; vẫn cần phân biệt “network chậm” với “backend đang xử lý chậm” và “connection pool đã hết”.

## 7. Dùng Java Flight Recorder để nối CPU và chờ I/O

JFR có sẵn trong JDK hiện đại và cung cấp CPU samples, GC events, monitor/park events và một số I/O events mà không phải tự thêm thư viện ứng dụng. Với JDK 17+, ví dụ bắt đầu ghi khoảng 60 giây:

```bash
jcmd <PID> JFR.start name=cpu-io settings=profile duration=60s filename=cpu-io.jfr
jfr summary cpu-io.jfr
```

Lệnh thứ hai chạy sau khi bản ghi đã hoàn tất và tệp xuất hiện. Đường dẫn `filename` và quyền ghi phụ thuộc môi trường của JVM. Có thể mở tệp bằng JDK Mission Control (JMC) để quan sát timeline và stack CPU samples.

Cần đối chiếu các nhóm sự kiện sau (tính khả dụng và việc bật event phụ thuộc JDK/JFR settings, threshold và sampling):
- **CPU/load/sampling:** `jdk.CPULoad`, `jdk.ThreadCPULoad`, `jdk.ExecutionSample` và native method sampling khi được thu thập. Tìm hot methods và phase tiêu CPU.
- **File/network I/O:** `jdk.FileRead`, `jdk.FileWrite`, `jdk.SocketRead`, `jdk.SocketWrite`. Xem duration, kích thước và stack nếu sự kiện được ghi.
- **Contended synchronization:** `jdk.JavaMonitorEnter`, `jdk.ThreadPark`. Xem thời gian đợi và code liên quan, không gán chúng thành storage I/O.
- **GC/heap:** các sự kiện GC pause, heap và allocation để tách hoạt động của bộ thu gom khỏi CPU ứng dụng.

Sự kiện dưới threshold hoặc chưa bật có thể **không xuất hiện**. “Không thấy SocketRead” không có nghĩa là không có hoạt động network. Kết hợp dấu vết JFR với metric client/backend và OS trong **cùng cửa sổ thời gian**.

### Cách đọc một timeline

Ví dụ một khoảng tăng latency 10 giây:
1. CPU per-core tăng tới trần; JFR execution samples dồn vào một phương thức xử lý dữ liệu; `r` tăng. Ưu tiên giả thuyết CPU saturation.
2. CPU thấp, mỗi request ngưng ở socket read 2 giây, backend cũng báo p95 2 giây; `wa` thấp. Ưu tiên điều tra remote latency.
3. CPU thấp, nhiều task đợi `CompletableFuture.join` hoặc condition trong worker pool; queue pool tăng. Ưu tiên điều tra mô hình phụ thuộc và starvation.
4. CPU host còn rảnh nhưng JVM process liên tục bị cgroup CPU throttling. Ưu tiên kiểm tra quota trước khi tăng số thread.

Đây là ví dụ về **cách tổng hợp chứng cứ**, không phải luật kết luận một chỉ số đơn lẻ.

## 8. Cùng một ứng dụng, ba kiểu “chờ” khác nhau

Giả sử pipeline Java gồm `read file → parse JSON → call API → aggregate`.

**Bước đọc file:** nếu phải lấy dữ liệu từ storage chậm, latency và block I/O có thể tăng. Nhưng dữ liệu đã ở page cache thì đọc file có thể nhanh mà vẫn hiện nhiều byte đọc ở tầng ứng dụng.

**Bước parse JSON:** phần lớn là CPU work. Nếu tăng worker vượt số core hữu dụng, throughput có thể đi ngang và latency tăng do cạnh tranh CPU, allocation và GC.

**Bước gọi API:** phần lớn wall time có thể là chờ response từ dịch vụ khác; CPU thấp và `wa` thấp không mâu thuẫn với latency cao. Bổ sung thread có thể tăng khả năng xử lý các request chờ đồng thời, nhưng không giải quyết dịch vụ đích đang bị quá tải và còn có thể đẩy nó vào quá tải nặng hơn.

Ngoài ra, một worker chờ lấy connection từ pool không đồng nghĩa đang chờ network socket thực tế; nó đang chờ **tài nguyên cục bộ có số lượng hữu hạn**. Mỗi dạng chờ cần metric đúng nguồn.

## 9. Chọn mức concurrency theo bottleneck

### 9.1. CPU-bound: giới hạn worker gần năng lực CPU thực tế

Với code thuần tính toán:
- Dùng executor hữu hạn, ví dụ `Executors.newFixedThreadPool(n)`, và thử `n` gần số CPU hữu dụng như một **điểm bắt đầu đo**, không xem đó là công thức tuyệt đối.
- Kiểm tra `Runtime.getRuntime().availableProcessors()` trên JDK đang chạy; với container phải xác minh CPU quota/cpuset và JDK có nhận đúng giới hạn đó không.
- Ưu tiên giảm thuật toán O(n²), cache hợp lý, giảm allocation/GC, tăng tính cục bộ bộ nhớ hoặc chia dữ liệu độc lập.
- Tránh để worker CPU chờ blocking I/O/lock lâu; nếu có nhiều phase khác nhau, cân nhắc tách executor để ngăn I/O chiếm hết worker CPU.
- Tăng số thread vượt khả năng core thường chỉ tăng contention và context switching, không tạo thêm CPU.

**Lưu ý:** CPU-bound không đương nhiên có thể chia vô hạn. Phần tuần tự, phụ thuộc kết quả, chia/gộp dữ liệu và memory bandwidth đều đặt giới hạn cho speedup (định luật Amdahl).

### 9.2. I/O-bound: giới hạn “in flight” bằng tài nguyên, không chỉ số core

Tác vụ dành phần lớn wall time để chờ có thể hưởng lợi từ nhiều thao tác chồng nhau. Ước lượng định hướng khi hệ thống ổn định theo Little's Law:

`L ≈ λ × W`

Trong đó `L` là số công việc đang ở trong hệ thống (in-flight), `λ` là throughput hoàn thành/giây và `W` là thời gian trung bình một công việc ở trong hệ thống (giây). Ví dụ mục tiêu **100 request/giây** với thời gian tồn tại trung bình **0,2 giây** gợi ý khoảng **20 request in-flight** ở trạng thái ổn định. Đây **không phải** lời khuyên tạo ngay 20 thread: cần tính cả phân phối latency, các tầng queue, client/backend limit, connection pool, memory và deadline.

Có thể dùng:
- Executor/queue hữu hạn và giới hạn bằng `Semaphore` cho tài nguyên hiếm (connection, API quota, file descriptor).
- Bất đồng bộ thực sự hoặc nonblocking I/O khi có lợi, nhưng không tự động suy rằng callback nghĩa là không có CPU work.
- **Virtual threads (Java 21+)** cho nhiều thao tác blocking I/O, với các API hỗ trợ. Virtual threads giúp giảm chi phí quản lý thread khi chờ; chúng **không** tạo thêm core, connection, bandwidth hay DB capacity. Vẫn đặt giới hạn concurrency theo downstream.
- Timeout, cancellation, bounded retries và backpressure để hàng đợi không tăng vô hạn.

**Không dùng queue dài như bằng chứng hệ thống xử lý tốt:** queue hấp thụ tải nhưng tăng thời gian end-to-end và nguy cơ hết bộ nhớ.

### 9.3. Workload hỗn hợp

Nếu vừa CPU-bound vừa I/O-bound, một pool chung có thể gặp trường hợp mọi worker bị chiếm bởi network blocking và task tính toán không được chạy. Tách phase, hạn chế số task chờ, hoặc dùng mô hình phối hợp tương ứng với phụ thuộc và chi phí mỗi phase. Tránh sinh một thread cho mỗi item không giới hạn khi tải đột biến.

Với `CompletableFuture`, lựa chọn executor của `supplyAsync`/`thenApplyAsync` có ý nghĩa lớn: việc chạy stage tính toán trên executor đang nghẽn I/O có thể làm tăng tail latency. Việc gọi `join()` trên worker trong một pool quá nhỏ có thể gây starvation/deadlock phụ thuộc; nên biểu diễn nhánh phụ thuộc bằng các stage kết hợp thay vì chặn worker chờ một task cùng pool.

## 10. Phân biệt hiện tượng dễ chẩn đoán nhầm

### 10.1. CPU cao nhưng throughput thấp

Không mặc nhiên nghĩa là cần nhiều thread. Có thể do:
- Nhiều lần retry hoặc spin loop làm việc vô ích.
- GC hoặc allocation churn chiếm CPU.
- Lock contention có spin; CAS liên tục thất bại.
- Quá nhiều worker và context switch.
- Tính toán thừa, serialization/parse lặp, hot code đơn luồng.

Kiểm tra JFR CPU samples, GC, CPU per-thread và throughput trước khi quyết định.

### 10.2. CPU thấp nhưng latency cao

Nghi ngờ chờ network, storage, connection pool, semaphore, monitor/condition, queue hoặc một stage tuần tự. Đo `submit → task start`, `task start → task end`, `remote request → remote response` riêng biệt. Một task có thể “chậm” 5 giây dù code của nó chỉ chạy 20 ms vì nằm trong hàng đợi 4,98 giây.

### 10.3. Linux load average cao nhưng CPU thấp

Load average trên Linux bao gồm những task runnable và một số task ở trạng thái uninterruptible sleep. Vì vậy nó không đơn thuần là “CPU utilization”. Quan sát `vmstat r/b`, `wa`, stack và disk metrics. Chỉ số load cao kèm nhiều task ở trạng thái D có thể chỉ ra một vấn đề I/O/kernel; không tự kết luận CPU saturation.

### 10.4. CPU host thấp nhưng Java bị nghẽn CPU

Trong container, CPU quota có thể làm process bị throttled dù host còn rảnh. Trên Linux cgroup v2 có thể xem `cpu.max` và `cpu.stat` trong cgroup thích hợp; `nr_throttled`/`throttled_usec` tăng liên quan tới CPU quota. Đặt số worker dựa vào **CPU được cấp** và hiệu năng thực tế, không theo tổng core của host.

### 10.5. Virtual threads chờ nhiều có phải I/O wait cao?

Không. Số lượng virtual thread lớn đang parked trong I/O có thể là hành vi bình thường. Kiểm tra latency, tình trạng carrier, CPU thực và downstream limits. Khi cần, xem JFR pinning events trên JDK hỗ trợ và phân tích đoạn blocking không hợp tác với cơ chế virtual thread; đừng quy mọi `WAITING` thành disk I/O.

## 11. Quy trình chẩn đoán thực hành có thể lặp lại

**Bước 1 — Đặt câu hỏi theo triệu chứng.** Chậm ở throughput, p95/p99 latency, thời gian startup hay một batch? Chỉ ra thời điểm, tải (requests/giây), concurrency thực tế và baseline khi bình thường.

**Bước 2 — Kiểm tra CPU/quota và runnable.** Đo per-core CPU, process/thread CPU, run queue hoặc CPU pressure. Nếu container, kiểm tra quota/throttling. Tìm xem ứng dụng thực sự thiếu CPU hay chỉ có một hot thread.

**Bước 3 — Chia thời gian request/task thành các pha.** Ít nhất đo queue wait, CPU/compute, file/network call, lock wait và giai đoạn tổng hợp. Đừng chỉ đo tổng thời gian end-to-end.

**Bước 4 — Đối chiếu JVM với OS.** Thu thập JFR và một vài thread dump trong thời gian xảy ra sự cố; đồng thời quan sát `vmstat`, `mpstat`, `pidstat`, `iostat` và metrics network/backend nếu liên quan. Dùng cùng trục thời gian.

**Bước 5 — Đặt giả thuyết có thể kiểm chứng.** Ví dụ:
- “Tăng worker từ 8 lên 16 không tăng throughput vì 8 core CPU đã bão hòa.”
- “CPU thấp vì 80% wall time request nằm ở socket read đến backend B.”
- “Queue task dài do 8 worker đang blocking ở một Future khác cùng pool.”

**Bước 6 — Chỉ thay đổi một biến có chủ đích.** Giảm số worker, giới hạn in-flight, cache/batch I/O, sửa thuật toán, thay kích thước connection pool hoặc tối ưu backend phù hợp giả thuyết. Đo lại throughput, p95/p99, error rate, CPU, queue, I/O latency. Quan sát cả ảnh hưởng lên downstream.

**Bước 7 — Kiểm tra dưới tải thật.** Môi trường dev với `Thread.sleep` không thay thế hệ thống thật. Thử steady load lẫn burst; theo dõi backpressure, memory, timeout và việc phục hồi sau lỗi.

## 12. Hai ví dụ chẩn đoán cụ thể

### Trường hợp A: xử lý 1 triệu bản ghi trên máy 4 CPU hữu dụng

Pool tăng từ 4 lên 32 thread, throughput từ 20.000 lên 20.500 bản ghi/giây nhưng p95 tăng 2 lần. Quan sát CPU gần trần, nhiều runnable task và JFR cho thấy phần lớn samples thuộc parsing/hashing.

Diễn giải: có bằng chứng nghiêng về **CPU saturation**. Hướng thử: giảm worker gần năng lực CPU, profile hot path, giảm allocation và chia batch tốt hơn. Chạy 32 worker không tạo ra 32 core. Con số chỉ là **tình huống giả định** để tập cách lập luận.

### Trường hợp B: gọi service từ Java với p95 khoảng 2 giây

CPU JVM thấp; request chờ remote socket read; `%wa` Linux gần 0; backend báo tăng thời gian xếp hàng. Dù tăng số task đồng thời, service đích chỉ xử lý một lượng nhất định và error rate bắt đầu tăng.

Diễn giải: đây là **remote wait/downstream bottleneck**, không có bằng chứng CPU Java bão hòa và cũng không cần `%wa` cao. Hướng thử: kiểm soát in-flight và timeout, kiểm tra remote queue, tối ưu hoặc scale backend. Thêm virtual threads chỉ làm rẻ việc chờ về phía Java, không tăng công suất backend.

## 13. Sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| “`%wa=0` ⇒ không chờ I/O” | `wa` không phải đồng hồ chờ socket/DB của Java | Đo JFR socket/file + latency client/backend |
| “Mọi `RUNNABLE` đều đang ăn CPU” | Trạng thái JVM không tương đương OS CPU time | Kết hợp per-thread CPU, JFR CPU samples và stack |
| “Mọi `WAITING` đều là disk I/O” | Có thể đang chờ monitor/condition/Future/sleep | Đọc stack, monitor/park events và mô hình phụ thuộc |
| “CPU 90% ⇒ chắc chắn saturation” | Không có bằng chứng queue/pressure hoặc SLA suy giảm | Đối chiếu runnable, pressure, throughput và latency |
| “CPU tổng thấp ⇒ không bị nghẽn CPU” | Có thể hot một core, quota hoặc affinity | Quan sát per-core và cgroup quota/throttling |
| “I/O-bound ⇒ tăng thread vô hạn” | Connection, backend, queue, heap đều có trần | Bounded concurrency, backpressure và deadline |
| “`sleep(500)` mô phỏng Linux I/O wait” | Sleep không tạo disk I/O | Dùng sleep để dạy wall/CPU; dùng disk workload + `iostat` để đo I/O |
| “`%util` disk gần 100 là chắc chắn bão hòa” | SSD/NVMe có nhiều hàng đợi, cách hạch toán khác nhau | Đánh giá latency, queue depth, throughput và giới hạn thiết bị |
| “Một thread dump đủ chỉ ra nguyên nhân” | Là ảnh chụp tại một thời điểm | Lấy mẫu theo thời gian và đối chiếu JFR/OS |
| “Tăng pool là sửa được latency” | Nếu bottleneck là CPU quota hoặc backend, tăng pool có thể làm xấu hơn | Chứng minh bottleneck rồi mới tối ưu |

## 14. Bài tập tự kiểm tra

**Bài 1.** Một Java service chạy trên máy 8 logical CPU. Tổng CPU khoảng 15%, nhưng một thread dùng gần 100% một core và các request qua một đoạn code tuần tự tăng latency. Có thể kết luận “CPU còn rảnh nên tăng thread” không? Hãy giải thích giới hạn của hot path và cách tìm nó trong JFR.

**Bài 2.** Bạn thấy `vmstat` báo `wa=1%`, `r` thấp, CPU process 10% và p95 của HTTP call 3 giây. Hãy liệt kê ít nhất ba loại số liệu cần xem trước khi kết luận do network/backend hoặc connection pool.

**Bài 3.** `iostat` cho thấy storage `await` tăng mạnh đồng thời JFR ghi các `FileRead` lâu. `%wa` cũng tăng. Giả thuyết ban đầu là gì? Bạn sẽ đo thêm gì để phân biệt storage chậm với page cache miss hoặc thiết bị bị một process khác gây tải?

**Bài 4.** Worker pool 4 thread, cả bốn task gọi `Future.get()` để đợi các task khác vừa submit **vào cùng pool**. CPU thấp, queue tăng. Đây có phải I/O wait không? Hãy sửa thiết kế bằng cách loại bỏ blocking dependency trong worker hoặc sắp xếp executor/phụ thuộc hợp lý.

**Đáp án định hướng:** (1) Một hot path tuần tự có thể bão hòa một core dù CPU tổng thấp; cần per-thread CPU và CPU samples. (2) Client timeout/connection-pool wait, JFR socket events và backend latency/queue, kèm network RTT/retransmissions khi cần. (3) Nghi ngờ storage I/O; đối chiếu file timing, I/O per-process, cache behavior, device latency/queue và tải từ tiến trình khác. (4) Đây là starvation do phụ thuộc task trong cùng pool; `Future.get()` bị chặn không chứng minh I/O và cần tổ chức lại graph/task.

## 15. Ghi nhớ để ra quyết định

- **CPU saturation:** nhu cầu công việc runnable vượt khả năng CPU; đọc utilization **cùng** run queue/pressure, per-core, quota và tác động throughput/latency.
- **I/O wait (`%wa` Linux):** chỉ số hạch toán CPU idle trong một số điều kiện I/O, đặc biệt hữu ích cho điều tra block storage; **không** đo mọi khoảng Java thread chờ network/DB.
- **Wall time ≠ CPU time:** phần chênh gồm nhiều loại chờ; xác định nguyên nhân bằng stack, JFR events, OS và metrics tài nguyên cụ thể.
- **Tối ưu đúng điểm nghẽn:** workload CPU-bound ưu tiên giảm CPU work và giới hạn worker; workload I/O-bound ưu tiên latency, giới hạn in-flight, tài nguyên backend, timeout và backpressure; workload hỗn hợp cần phân tách phase và đo thực tế.

Sự khác biệt quan trọng nhất trong vận hành Java concurrency là **CPU không đủ năng lực để chạy task** so với **task đang chờ một tài nguyên hoặc điều kiện khác**. Chỉ khi chỉ số, stack và thời gian thực cùng chỉ về một nguyên nhân, lựa chọn tăng thread, giảm thread hay tối ưu I/O mới có cơ sở.
