# Đo tác động của thread count và context switching trong Java

## 1. Mục tiêu và câu trả lời chính

**Thread count** là số thread hiện có hoặc được dùng để xử lý công việc; **context switching** là quá trình hệ điều hành ngừng thực thi một thread và tiếp tục thực thi thread khác trên CPU. Khi tăng số thread, ứng dụng có thể tận dụng thêm CPU hoặc che thời gian chờ I/O. Nhưng sau một ngưỡng, lợi ích giảm dần hoặc trở thành chi phí do tranh chấp CPU, đồng bộ, bộ nhớ, scheduler và các lần chuyển ngữ cảnh.

Không thể kết luận “nhiều thread hơn luôn nhanh hơn” hoặc “context switch nhiều nên ứng dụng chậm” chỉ từ một con số. Để đánh giá **tác động**, phải thay đổi thread count có kiểm soát, đo throughput/latency và quan sát thêm CPU, context switch, contention, GC, đặc tính công việc.

Bài này tập trung vào **Java concurrency ở mức JDK/JVM và hệ điều hành**, đặc biệt platform threads và ExecutorService. Không cần API hoặc cơ chế riêng của Spring.

Sau bài học, bạn có thể:

1. Giải thích lúc nào tăng thread count giúp CPU-bound và I/O-bound workload.
2. Thiết kế thí nghiệm thay đổi số thread mà giữ khối lượng công việc cố định.
3. Đo thời gian, throughput, CPU utilization và context switches bằng công cụ thích hợp.
4. Phân biệt OS context switch với số lần block/wait và các trạng thái thread của JVM.
5. Chọn kích thước thread pool dựa trên dữ liệu, phát hiện oversubscription và contention.

## 2. Cơ chế: vì sao số thread ảnh hưởng hiệu năng?

### 2.1. Thread count, concurrency và parallelism

- **Concurrency**: nhiều tác vụ có tiến trình chồng lấp về thời gian; có thể luân phiên trên một CPU.
- **Parallelism**: nhiều tác vụ thực thi **đồng thời thực sự** trên nhiều logical processors.
- **Platform thread** trong Java 17 đi với thread của hệ điều hành; hệ điều hành quyết định khi nào thread được chạy, bị tạm dừng và chuyển CPU.
- **Logical processors** bao gồm các CPU mà tiến trình được phép sử dụng; con số này có thể khác số lõi vật lý do SMT, affinity hoặc CPU quota trong container.

Ví dụ máy có quyền sử dụng bốn logical processors:

~~~text
4 CPU-bound threads:
CPU 1: [T1--------]
CPU 2: [T2--------]
CPU 3: [T3--------]
CPU 4: [T4--------]

8 CPU-bound threads:
CPU 1: [T1---][T5---][T1---] ...
CPU 2: [T2---][T6---][T2---] ...
CPU 3: [T3---][T7---][T3---] ...
CPU 4: [T4---][T8---][T4---] ...
~~~

Sơ đồ chỉ minh họa việc chia thời gian CPU. Scheduler thực tế có ưu tiên, hàng đợi runqueue, migration, interrupt và các biến động khác.

Nếu tất cả thread liên tục làm phép tính, tăng số thread từ 1 lên gần số logical processors có thể giảm **wall-clock time** của batch độc lập. Vượt quá mức đó thường không tăng khả năng tính toán; đôi khi còn làm chậm vì thread phải chia CPU, mất locality và tăng tranh chấp.

Nếu nhiều thread đang **chờ** đĩa, mạng, timer hoặc khóa, CPU có thể chạy thread khác trong lúc chờ. Vì thế một I/O-bound workload đôi khi cần nhiều thread hơn số core. Nhưng số kết nối, pool tài nguyên, thời gian chờ, memory footprint và giới hạn phía dịch vụ ngoài vẫn là ràng buộc quan trọng.

### 2.2. Context switch là gì?

**Context switch** (chuyển ngữ cảnh thread) xảy ra khi CPU chuyển từ một thread đang chạy sang thread khác. Hệ điều hành lưu/khôi phục trạng thái cần thiết (như registers, instruction pointer, stack/scheduling state), cập nhật scheduler và tiếp tục thực thi thread được chọn. Chi phí có thể gồm:

- Thời gian thực hiện lập lịch và chuyển trạng thái kernel.
- Mất cache/TLB locality hoặc phải làm nóng lại dữ liệu và instruction cache; mức độ phụ thuộc vào cặp thread, CPU và kiến trúc.
- CPU migration giữa các core làm thay đổi locality và tương tác với cache hierarchy.
- Tranh chấp đồng bộ và cache coherence có thể tăng khi có thêm thread cùng truy cập shared state.

Không phải mỗi context switch đều làm mất toàn bộ cache, cũng không có một **chi phí cố định bằng microsecond** áp dụng cho mọi máy.

Có hai nguyên nhân thường được hệ điều hành thống kê:

- **Voluntary context switch**: thread nhường CPU vì chờ tài nguyên/sự kiện, chẳng hạn chờ mutex, điều kiện hoặc I/O.
- **Involuntary context switch**: thread đang có thể chạy nhưng bị hệ điều hành ngừng thực thi, chẳng hạn hết time slice hoặc CPU bị ưu tiên cho thread khác.

Context switches tăng không tự động là lỗi. Một hệ thống I/O hiệu quả có thể tự nguyện ngủ/chờ rất nhiều; vấn đề xuất hiện khi mức chuyển ngữ cảnh hoặc tranh chấp làm giảm **kết quả hữu ích**.

### 2.3. Các trạng thái Java không phải bộ đếm OS context switch

Thread.State trong JVM gồm NEW, RUNNABLE, BLOCKED, WAITING, TIMED_WAITING, TERMINATED.

- **RUNNABLE** theo Java có thể chỉ là thread sẵn sàng chạy hoặc đang chạy native/JVM code; nó **không chứng minh** thread đang chiếm CPU.
- **BLOCKED** phản ánh chờ vào Java monitor (synchronized), không mô tả mọi trường hợp chờ.
- **WAITING/TIMED_WAITING** có thể do Object.wait(), LockSupport.park(), Thread.join() hoặc Thread.sleep(); không thể biến tổng số trạng thái này thành số OS context switches.
- ThreadMXBean cung cấp thread count, peak thread count, CPU time, blocked/waited statistics khi tính năng khả dụng. Nó **không** cung cấp bộ đếm tổng OS context switches chuẩn cho mọi JVM/OS.
- Thread dump cho biết một thời điểm; một dump thấy nhiều WAITING không đủ để kết luận có scheduler thrashing.

Vì vậy phải phối hợp **JVM telemetry** và **OS counters** khi phân tích context switching.

## 3. Cần đo những chỉ số nào?

| Chỉ số | Ý nghĩa | Cách hiểu |
|---|---|---|
| Wall-clock time | Thời gian từ bắt đầu đến hoàn thành công việc | Với batch giữ nguyên tổng việc, **càng thấp càng tốt** |
| Throughput | Item hoặc tác vụ hoàn thành/giây | Hữu ích với workload chạy liên tục; phải giữ cùng khối lượng tính toán mỗi item |
| Latency (p50/p95/p99) | Thời gian mỗi yêu cầu hoàn thành | Cần tính cả thời gian xếp hàng; throughput tăng có thể đi kèm tail latency xấu đi |
| CPU utilization / CPU time | CPU tiêu tốn khi xử lý | Phân biệt thiếu CPU, CPU bị chia quá nhiều, hoặc đang chờ |
| Số live / active / peak threads | Áp lực tài nguyên và mức song song | Không đồng nghĩa mọi thread đang chạy; nên đo cả kích thước pool, active tasks |
| Context switches/s | Hoạt động scheduler trên OS | Xét cùng throughput và CPU time; per-thread/per-process chính xác hơn số hệ thống |
| Voluntary / involuntary switches | Thread chủ động chờ so với bị preempt | Có thể gợi ý nhiều blocking hoặc oversubscription, không chứng minh nguyên nhân duy nhất |
| CPU migrations, runqueue / scheduling delay | Thread đổi core và thời gian chờ CPU | Hữu ích khi CPU bận cao hoặc latency tăng |
| Lock contention, monitor blocked time | Phần thời gian chờ đồng bộ | Nhiều thread cùng tranh khóa có thể giảm scaling |
| GC pauses, heap và allocation | Chi phí JVM khác ảnh hưởng latency | Tránh quy mọi đột biến vào context switch |

Đừng đo riêng “task/s” mà bỏ qua latency, hoặc lấy **thread count hiện tại** thay cho số thread đang làm việc. Khi báo cáo, nêu cụ thể CPU cores được phép, loại máy/JDK, Java flags, số thread, loại tải, thời lượng, số mẫu đo, median và độ phân tán.

## 4. Thí nghiệm Java 17+: cố định công việc, thay đổi số thread

Mục tiêu: dùng cùng một tập tác vụ và cùng một ExecutorService dạng fixed pool, chỉ thay đổi tham số số worker giữa các lần chạy. Hai loại tải đơn giản:

- **CPU**: mỗi task tính toán vòng lặp phụ thuộc dữ liệu và trả kết quả để JVM không dễ loại bỏ toàn bộ phép tính. Tổng số task × iterations **giữ nguyên** giữa các lần so sánh.
- **WAIT**: mỗi task Thread.sleep() một khoảng cố định để mô phỏng **thời gian chờ có thể overlap**. Đây chỉ là mô hình chờ, **không** đại diện cho hiệu năng network/database thật.

File **ThreadCountBenchmark.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ThreadCountBenchmark {
    enum Mode { CPU, WAIT }

    private static volatile long sink;

    private static long doWork(Mode mode, int work)
            throws InterruptedException {
        if (mode == Mode.WAIT) {
            Thread.sleep(work); // milliseconds; simulates waiting only
            return 1L;
        }

        long value = 0x9E3779B97F4A7C15L;
        for (int i = 0; i < work; i++) {
            value ^= value << 13;
            value ^= value >>> 7;
            value ^= value << 17;
        }
        return value;
    }

    private static long runBatch(
            ExecutorService pool, Mode mode, int tasks, int work
    ) throws Exception {
        List<Future<Long>> futures = new ArrayList<>(tasks);
        for (int i = 0; i < tasks; i++) {
            futures.add(pool.submit(() -> doWork(mode, work)));
        }

        long checksum = 0;
        for (Future<Long> future : futures) {
            checksum += future.get();
        }
        return checksum;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                    "Usage: java ThreadCountBenchmark "
                  + "cpu|wait threads tasks iterationsOrWaitMs");
        }

        Mode mode = switch (args[0].toLowerCase(Locale.ROOT)) {
            case "cpu" -> Mode.CPU;
            case "wait" -> Mode.WAIT;
            default -> throw new IllegalArgumentException("Mode: cpu|wait");
        };
        int threads = Integer.parseInt(args[1]);
        int tasks = Integer.parseInt(args[2]);
        int work = Integer.parseInt(args[3]);
        if (threads < 1 || tasks < 1 || work < 1) {
            throw new IllegalArgumentException(
                    "threads, tasks and work must be positive");
        }

        ExecutorService pool = Executors.newFixedThreadPool(threads);
        try {
            // Warm up the pool and JVM. This is not a full JMH warmup.
            int warmupTasks = Math.min(tasks, threads * 2);
            for (int i = 0; i < 3; i++) {
                sink = runBatch(pool, mode, warmupTasks, work);
            }

            long[] samples = new long[5];
            for (int i = 0; i < samples.length; i++) {
                long start = System.nanoTime();
                sink = runBatch(pool, mode, tasks, work);
                samples[i] = System.nanoTime() - start;
            }

            Arrays.sort(samples);
            double seconds = samples[2] / 1_000_000_000.0;
            System.out.printf(Locale.US,
                    "mode=%s threads=%d tasks=%d work=%d "
                  + "median_ms=%.1f tasks_per_sec=%.1f checksum=%d%n",
                    mode.name().toLowerCase(Locale.ROOT), threads,
                    tasks, work, seconds * 1_000.0, tasks / seconds, sink);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch:

~~~bash
javac ThreadCountBenchmark.java
~~~

Ví dụ chạy từ một terminal:

~~~bash
java ThreadCountBenchmark cpu 1 160 2000000
java ThreadCountBenchmark cpu 2 160 2000000
java ThreadCountBenchmark cpu 4 160 2000000
java ThreadCountBenchmark cpu 8 160 2000000
java ThreadCountBenchmark cpu 16 160 2000000

java ThreadCountBenchmark wait 1 160 20
java ThreadCountBenchmark wait 2 160 20
java ThreadCountBenchmark wait 4 160 20
java ThreadCountBenchmark wait 8 160 20
java ThreadCountBenchmark wait 16 160 20
~~~

Tham số tương ứng: **mode**, **số thread**, **số task**, **số lần lặp/tác vụ khi CPU** hoặc **milli-giây ngủ/tác vụ khi WAIT**. Mỗi lần chạy cùng mode giữ nguyên tasks và work; không so sánh trực tiếp task/s của CPU với task/s của WAIT vì đơn vị công việc khác nhau.

Output của chương trình gồm mode, threads, tasks, work, **median_ms**, **tasks_per_sec**, checksum. Thời gian/throughput phụ thuộc máy, scheduler và trạng thái JVM nên **không có stdout số đo cố định đáng tin để chép sẵn**. Checksum giúp buộc giá trị kết quả được quan sát và phát hiện khác biệt bất thường, nhưng không thay thế kiểm thử logic.

**Giải thích phép đo:**

1. ExecutorService tạo số worker cố định; task được gửi bằng submit(), lấy kết quả bằng Future.get(). Cả thời gian enqueue và chờ hoàn tất batch đều được tính.
2. Ba batch nhỏ làm nóng pool/JIT; năm batch đo dùng System.nanoTime(), lấy median để giảm ảnh hưởng của một mẫu nhiễu.
3. Với CPU, workload là phép tính độc lập; nếu có đủ CPU logic, nhóm ít thread có thể tăng tốc khi tăng thread count. Khi CPU đã bão hòa, tăng tiếp thường không giúp.
4. Với WAIT, các khoảng sleep có thể chồng nhau, nên tăng thread count thường giảm tổng wall time đáng kể khi pool còn nhỏ. Đây là minh họa **che thời gian chờ**, không chứng minh tăng thread luôn tốt cho I/O thực.
5. Thí nghiệm này là **benchmark minh họa**, còn chịu ảnh hưởng của startup, GC, OS scheduling, kích thước task, thread pool và JIT. Muốn công bố số liệu microbenchmark đáng tin cần dùng JMH và môi trường đo kiểm soát.

**Lưu ý về code:** Thread.sleep() có độ chính xác và granularity theo OS; kết quả WAIT không phải bội số toán học chính xác. Tạo pool ngoài vòng đo giúp giảm bias thread creation; nhưng mỗi tiến trình chạy vẫn có JVM startup và warmup riêng. CPU benchmark dùng các phép toán số nguyên lặp lại nên không mô phỏng cache contention, database, file I/O hoặc tải nghiệp vụ đầy đủ.

## 5. Quy trình so sánh có thể tái lập

### 5.1. Điều kiện thí nghiệm

Trước khi chạy, ghi lại:

- Java version (**java -version**) và JDK distribution; số logical processors JVM thấy qua Runtime.getRuntime().availableProcessors() (đây là con số chịu ảnh hưởng của cấu hình runtime/container).
- CPU model, số core/logical processors CPU được cấp, affinity/quota, loại máy vật lý hay VM/container.
- Heap/GC flags; máy có đang chạy tác vụ nặng khác hay không; nguồn điện/power profile và nhiệt độ khi có thể.
- Thread pool, số task, kích thước công việc, số lượt warmup/measure, chính sách lỗi.
- Với tải thật: thời gian chờ dịch vụ ngoài, số kết nối được phép, batch size, buffer/queue capacity và tốc độ đầu vào.

Giữ **tổng công việc và nguồn dữ liệu** như nhau khi thay đổi thread count. Nếu đo workload nhận yêu cầu liên tục, phải giữ **offered load** cố định và quan sát cả hàng đợi; chỉ so successful responses/s có thể che drop/reject.

### 5.2. Dãy thread count và cách chạy

Bắt đầu với **1, 2, 4, 8, 16** hoặc dãy quanh số CPU logic thực tế. Khi thấy throughput chững lại hoặc giảm, tinh chỉnh quanh điểm gãy (ví dụ 3, 4, 5, 6). Đừng mặc định một con số là tối ưu cho tất cả các chế độ.

Nên chạy mỗi cấu hình trong nhiều process invocation và đổi thứ tự các cấu hình giữa các lượt. Giữ nguyên JDK, JVM flags và dữ liệu; ghi median, p95/p99 nếu workload có requests độc lập, variance và số mẫu. Nếu công việc quá nhỏ, thời gian tạo Future/queue/scheduler chiếm tỷ lệ lớn: tăng độ dài mỗi task hoặc chuyển sang benchmark đại diện hơn.

Trong benchmark code trên, mỗi mẫu batch phải hoàn thành trước mẫu tiếp theo; code không cố tái tạo request arrival rate thực. Để đánh giá dịch vụ live, dùng workload generator độc lập, đo latency **từ lúc request đi vào hệ thống** (bao gồm queueing) và các lỗi/timeouts.

### 5.3. Tính speedup và efficiency

Với batch có **cùng tổng khối lượng công việc**:

~~~text
Speedup(p) = T(1) / T(p)
Efficiency(p) = Speedup(p) / p

T(p): wall-clock time khi dùng p thread
~~~

Ví dụ **minh họa toán học**, nếu T(1)=8 giây và T(4)=2,5 giây, speedup=3,2 và efficiency=0,8 (80%). Đây là ví dụ cách tính, không phải kết quả đo của chương trình trên.

Theo **Amdahl's law**, nếu tỷ lệ phần việc bắt buộc tuần tự là s và phần còn lại song song hóa được hoàn hảo:

~~~text
Speedup_ideal(p) = 1 / (s + (1 - s) / p)
~~~

Trong thực tế, đồng bộ, queue, bộ nhớ, cache và scheduling còn khiến speedup thấp hơn mô hình lý tưởng. Nếu một cấu hình có throughput cao hơn nhưng p99 latency tăng mạnh, nó có thể không đạt mục tiêu vận hành.

## 6. Đo context switching ở hệ điều hành

**Cần đo context switch thực qua OS**. Hầu hết giá trị JVM như Thread.State, thread dump hoặc blocked count là thông tin bổ trợ, không phải bộ đếm này.

### 6.1. Linux: pidstat hoặc perf

Nếu đã có gói sysstat, chạy tiến trình Java đủ lâu để lấy mẫu rồi quan sát (trong bash):

~~~bash
java ThreadCountBenchmark cpu 16 1000 2000000 &
pid=$!
pidstat -w -t -p "$pid" 1
wait "$pid"
~~~

**pidstat -w -t** hiển thị context switches tự nguyện và không tự nguyện mỗi giây theo process/thread khi OS và phiên bản công cụ hỗ trợ. Cần kết thúc pidstat sau khi tiến trình hoàn tất; nó có thể kết thúc khi PID không còn tồn tại hoặc cần ngắt thủ công. Nếu benchmark kết thúc quá nhanh, tăng tasks để quá trình tồn tại đủ nhiều interval; đừng làm thay đổi tasks giữa các thread count mà bạn đang so sánh.

Tùy quyền perf_event, có thể thu tổng các hardware/software counters cho một lệnh:

~~~bash
perf stat -e context-switches,cpu-migrations,task-clock \
  -- java ThreadCountBenchmark cpu 16 1000 2000000
~~~

**Context-switches** và **cpu-migrations** là số đếm; **task-clock** đo tổng thời gian CPU của các task được quan sát. Phân biệt chúng với elapsed time của cả tiến trình. Lặp lại từng cấu hình với cùng lệnh và điều kiện; overhead của công cụ và quyền OS có thể khác nhau. Trên một số máy perf bị giới hạn bởi perf_event_paranoid hoặc quyền hệ thống; không nên thay đổi bảo mật máy chỉ để chạy ví dụ.

Trên Linux, /proc/PID/task/TID/status cũng có các bộ đếm voluntary_ctxt_switches và nonvoluntary_ctxt_switches tùy kernel. Để đo biến thiên, cần lấy hai mẫu trong khi thread còn sống; **không cộng tùy tiện thread ID đã kết thúc** hoặc so snapshot khác nhau mà không xét vòng đời thread.

### 6.2. Windows: Performance Monitor

Dùng **Performance Monitor (perfmon)**, thêm các counters:

- **Thread → Context Switches/sec**, lọc các instance liên quan tiến trình java đang đo.
- **Process → Thread Count**, **Process → % Processor Time** và các chỉ số CPU/memory phù hợp.
- Theo dõi thêm Processor Information → % Processor Utility hoặc các counters khả dụng trên hệ thống để quan sát mức tải CPU.

Tên counters/instance có thể được dịch hoặc khác theo phiên bản Windows. Nhiều Java processes cùng chạy sẽ khiến nhận diện bằng tên "java" mơ hồ; xác định đúng **PID** và instance của tiến trình. Không lấy tổng counters của mọi thread hệ thống rồi gán cho một chương trình Java.

Có thể dùng **jps -l** hoặc Task Manager Details để tìm PID Java; đối chiếu thời điểm tiến trình chạy. Để đếm context switches theo thread trên Windows, dữ liệu ở Performance Monitor/WPA thường có ích hơn chỉ xem Task Manager thông thường.

### 6.3. JVM: JFR, jcmd, jstack, ThreadMXBean

Java Flight Recorder hỗ trợ nhìn thấy hoạt động JVM, contention, blocking và execution samples; **JFR không phải bộ đếm context switches OS một cách mặc định**.

Chạy benchmark với JFR được bật từ lúc khởi động:

~~~bash
java -XX:StartFlightRecording=filename=threads.jfr,settings=profile,dumponexit=true \
  ThreadCountBenchmark cpu 16 1000 2000000
jfr summary threads.jfr
jfr print --events jdk.ThreadPark,jdk.JavaMonitorEnter threads.jfr
~~~

Lệnh trên dùng cú pháp nối dòng của bash; trên Windows PowerShell, nhập lệnh **java** trên một dòng. Profile configuration và thresholds quyết định event nào được ghi; file không có JavaMonitorEnter không chứng minh tuyệt đối ứng dụng chưa từng tranh monitor. JFR có thể làm tăng overhead nhỏ, vì vậy khi đo định lượng so sánh phải dùng cùng cấu hình JFR hoặc đo riêng không profiling.

Các công cụ khác:

- **jcmd**: tìm PID và thu thread dumps/JFR khi tiến trình đang chạy; ví dụ jcmd PID Thread.print (PID thay bằng ID thực tế).
- **jstack PID**: snapshot các stack và trạng thái thread; hữu ích nhận diện WAITING, BLOCKED, vị trí lock hoặc stack nóng.
- **ThreadMXBean** qua java.lang.management.ManagementFactory: thống kê live/peak count, thời gian CPU thread khi được hỗ trợ/bật, blocked/waited counts; không phải OS context switches.
- **JFR CPU samples**: cho biết code được sample trong các thread, hỗ trợ xác định hotspot; riêng samples không cho biết bao nhiêu lần scheduler đã chuyển từ thread này sang thread khác.

Để quy nguyên nhân, nên so sánh hai dãy thời gian: (1) throughput/latency/CPU, (2) context-switches/s và contention. Một con số đơn lẻ, đặc biệt thu trong thời gian rất ngắn, dễ dẫn đến kết luận sai.

## 7. Diễn giải ba kiểu kết quả điển hình

### Trường hợp A: CPU-bound tăng tốc rồi chững

Giả sử trên máy có bốn logical processors được cấp, throughput tăng rõ từ 1→2→4 thread nhưng gần như không tăng ở 8→16 thread, CPU đã bận. Cách diễn giải hợp lý:

- Bốn worker có thể gần tận dụng năng lực tính toán đang được cấp.
- Tám hoặc mười sáu worker có thể cần chia time slice; throughput không tăng vì không có thêm CPU.
- Nếu context switches/s và CPU migrations tăng trong khi throughput ngang hoặc giảm, đây là bằng chứng **phù hợp với** oversubscription, nhưng cần kiểm tra thêm cache, lock contention và GC trước khi quy nguyên nhân hoàn toàn cho context switching.

Hành động: cân nhắc giới hạn fixed pool quanh vùng throughput tốt nhất và xác minh tail latency. Đừng chọn threads bằng số lõi vật lý một cách máy móc: SMT, quota, CPU affinity và workload thực có thể làm điểm tối ưu khác.

### Trường hợp B: WAIT workload tăng tốc với nhiều threads

Với nhiều task sleep 20ms, thêm worker cho phép các khoảng chờ chồng nhau. Dù context switches/s tăng, wall time vẫn có thể giảm rõ rệt. Đây là trường hợp **context switches tăng nhưng không đồng nghĩa hiệu năng xấu**.

Tuy nhiên trong I/O thực, số kết nối tới DB, response time, lock, memory, timeout và rate limit có thể bị bão hòa. Đừng suy từ mô hình sleep rằng 1000 platform threads luôn hơn 100. Đo success/error rate, latency, queue depth, CPU và giới hạn tài nguyên của downstream.

### Trường hợp C: Nhiều thread nhưng throughput giảm mạnh

Nếu tăng 8→32 thread làm CPU bận, switch/s tăng, latency xấu đi mà throughput giảm, có thể do:

- **Oversubscription**: quá nhiều runnable workers cạnh tranh CPU.
- **Lock contention**: synchronized/Lock biến critical section thành điểm tuần tự.
- **Memory bandwidth/cache contention**: nhiều thread đọc/ghi vùng dữ liệu chung, tăng misses hoặc cache-line bouncing.
- **Excessive allocation/GC**: mỗi task tạo nhiều object, làm GC chen vào giữa tiến trình.
- **Queueing/oversized pool**: số active requests vượt khả năng DB hoặc thiết bị, làm tăng retry/timeouts.

Một dấu hiệu chưa đủ để chọn nguyên nhân. Kiểm tra CPU time, blocked stacks, ThreadPark/JavaMonitorEnter, profile hotspot, GC logs và counters OS tương ứng.

## 8. Một thí nghiệm bổ sung: phát hiện contention

Khi benchmark CPU có kết quả bất thường, hãy so sánh **cùng tổng việc** theo hai dạng:

**Dạng A — dữ liệu độc lập**: mỗi task tính toán trên biến cục bộ rồi trả một kết quả. Không khóa shared mutable state trong vòng nóng.

**Dạng B — tranh chấp shared state**: nhiều task cập nhật cùng biến dưới synchronized hoặc cùng một Lock. Khi critical section chiếm phần lớn thời gian, nhiều thread có thể xếp hàng chờ và mất khả năng parallelism.

Mẫu đoạn code chỉ minh họa critical section, dùng như một phép thử **riêng**:

~~~java
private static final Object lock = new Object();
private static long sharedSum;

static void addWithLock(long value) {
    synchronized (lock) {
        sharedSum += value;
    }
}
~~~

Đây không phải toàn bộ chương trình benchmark. Nếu đưa synchronized vào mỗi vòng lặp, bạn đã **thay workload**: tăng số thao tác khóa và memory contention, vì vậy không thể tuyên bố slowdown hoàn toàn do OS context switches. So sánh lock acquisitions, lock hold time và JFR monitor events song song với context switches.

Một trường hợp khác là **false sharing**: các thread sửa những biến logic độc lập nhưng nằm cùng cache line, khiến cache coherence traffic tăng. Tình huống đó có thể làm scaling kém **ngay cả khi số context switches không đặc biệt cao**. Phân tích CPU/profile/cache metrics trước khi quy lỗi cho scheduler.

## 9. Chọn thread count thực tế

### CPU-bound pool

Điểm xuất phát hợp lý là số logical processors JVM được cấp:

~~~java
int cpuCount = Runtime.getRuntime().availableProcessors();
ExecutorService pool = Executors.newFixedThreadPool(cpuCount);
~~~

Đo quanh ngưỡng này thay vì coi nó là chân lý cố định. Nếu còn các CPU-heavy threads ngoài pool (GC, ứng dụng khác, dịch vụ chung), có thể cần ít worker hơn. Nếu bị giới hạn memory bandwidth hoặc critical section, tăng thread có thể dừng hiệu quả trước khi CPU cores được dùng hết.

### Blocking workload và ước lượng ban đầu

Một quy tắc **xấp xỉ để chọn điểm thử nghiệm** nếu tasks độc lập, cùng kiểu, CPU work và wait xen kẽ:

~~~text
Số threads thử ban đầu ≈ CPU được cấp × (1 + W/C)

W: thời gian task chờ (không dùng CPU)
C: thời gian task thực sự dùng CPU
~~~

Ví dụ W/C=3 và có 4 logical processors được cấp thì ước lượng khoảng 16 threads; vẫn phải đo thực nghiệm. Công thức này **không** thay thế giới hạn kết nối, queue capacity, downstream saturation, memory hoặc mức chồng lấp wait thực tế. Khi W/C không ổn định, chọn dãy thread count bằng load test sẽ đáng tin hơn.

### Queue hữu hạn và chính sách quá tải

Tăng thread count không sửa được bài toán producer đưa vào nhanh hơn service capacity. Với ThreadPoolExecutor, hãy cân nhắc:

- Pool size theo workload và CPU chứ không tăng vô hạn.
- Queue capacity có giới hạn để tránh tích lũy task không được phục vụ.
- Rejection/backpressure policy rõ ràng và metric cho rejected tasks.
- Kiểm soát thời gian chờ, timeout và cancellation để task chết không giữ tài nguyên mãi.
- Đo **queue wait time** và **execution time** riêng vì thời gian đợi hàng đợi thường làm p99 xấu đi trước khi CPU bị bão hòa.

**Lưu ý với Executors.newFixedThreadPool:** factory này dùng hàng đợi công việc về cơ bản không giới hạn. Ví dụ benchmark gửi batch hữu hạn nên phù hợp mục đích học; đối với đầu vào liên tục cần xem lại ThreadPoolExecutor cùng bounded queue và rejection policy thay vì áp dụng nguyên mẫu trong production.

### Virtual threads Java 21+

Java 21 có **virtual threads**, giúp chạy nhiều công việc chờ/block theo cách sử dụng ít platform threads hơn trong nhiều trường hợp. Chúng **không làm tăng số core** và không biến CPU-bound computation thành nhanh hơn chỉ nhờ mở rất nhiều virtual threads. Cũng cần xét pinning, carrier threads và giới hạn downstream khi đo. Benchmark ở mục 4 dùng **fixed platform-thread pool theo Java 17**, nên không dùng kết quả của nó để kết luận trực tiếp về virtual threads.

## 10. Các lỗi đo lường phổ biến và cách tránh

1. **Chỉ chạy một lần.** JVM warmup, JIT, GC, scheduler, thermal throttling và tác vụ nền khiến số liệu thay đổi. Hãy warmup và lặp nhiều lần; dùng median cùng độ phân tán.
2. **Vừa tăng threads vừa tăng tổng task.** Khi workload không cố định, throughput tăng có thể chỉ do tải tăng. So sánh cùng input hoặc cùng offered load.
3. **Lấy wall time thay CPU time.** Blocking task có thể có elapsed time lớn nhưng CPU time thấp. Đo cả hai; với platform threads, total CPU time còn có thể vượt wall time khi chạy song song trên nhiều core.
4. **Coi trạng thái RUNNABLE là đang chiếm CPU.** Thread có thể đang ở runqueue chờ lịch hoặc đang thực thi trong phần native. Dùng CPU counters/samples để phân biệt.
5. **Coi mỗi park()/sleep() tương đương đúng một switch.** Điều này không được bảo đảm; OS scheduling, timeout và chuyển trạng thái có thể phức tạp hơn.
6. **Dùng context-switches/s làm KPI duy nhất.** Một chương trình nhiều I/O wait có thể switch nhiều nhưng throughput tốt. Đánh giá số switch trên một **đơn vị công việc đã hoàn thành**, kết hợp latency, CPU và error rate.
7. **Không định nghĩa đơn vị task.** Một task tính 100 vòng lặp khác hoàn toàn task tính 2 triệu vòng; chia task quá nhỏ làm executor overhead thống trị.
8. **Không đo queue depth và p99.** Throughput nhìn ổn nhưng request đợi lâu trong queue dẫn đến timeout. Xem cả queue wait, latency và rejection.
9. **Chạy các dãy cấu hình trong điều kiện khác nhau.** VM bị chia CPU, laptop chuyển power mode, JDK flags khác hoặc dữ liệu cache khác sẽ làm kết luận thiếu tin cậy.
10. **Nhầm context switch với chuyển từ Java code sang native code hoặc JVM safepoint.** Đó là các cơ chế khác nhau; số đo OS không bằng số lời gọi native, số safepoint hoặc số lần garbage collection.

## 11. Checklist phân tích kết quả

Khi thread count tăng, hãy tự hỏi:

1. Throughput tăng, plateau hay giảm? Batch total work có giữ nguyên không?
2. Median và p95/p99 latency thay đổi thế nào, có tính cả queue wait không?
3. CPU có bão hòa số logical processors **được phép sử dụng** không?
4. Voluntary/involuntary switches, migrations và scheduler wait tăng theo hướng nào? **Số switch trên task hoàn thành** thay đổi ra sao?
5. Threads tăng có dẫn tới monitor/lock contention, IO wait, GC hoặc cache bottleneck không?
6. Kích thước pool/queue, số active workers và downstream capacity có hợp lý không?
7. Điểm tốt nhất có được tái lập qua nhiều lần đo và môi trường gần production không?

Ghi bảng kết quả theo cấu trúc:

| Threads | Median wall time | Tasks/s | CPU utilization | Voluntary switches/s | Involuntary switches/s | p99 latency (nếu đo request) | Nhận xét |
|---|---|---|---|---|---|---|---|
| 1, 2, 4, 8, ... | Từ benchmark | Từ benchmark | Từ OS | Từ OS | Từ OS | Từ load test | Dựa trên bằng chứng |

Bảng là **mẫu cấu trúc ghi nhận**, không phải kết quả giả lập; chỉ điền giá trị thật sau khi chạy và bảo đảm các công cụ thu trong khoảng thời gian so sánh được.

## 12. Kết luận và câu hỏi tự kiểm tra

**Tăng thread count** giúp khi nó mở thêm khả năng xử lý song song trên CPU còn trống hoặc giúp chồng lấp thời gian chờ. Khi vượt công suất CPU/IO/lock/memory thực tế, thêm thread có thể tăng scheduling, context switching, queue wait và giảm tốc độ xử lý hữu ích.

**Context switching** là một nguồn chi phí tiềm tàng, không phải nguyên nhân mặc định. Muốn chứng minh tác động, phải so sánh nhiều cấu hình trên **cùng workload**, ghi throughput/latency/CPU và dùng counters hệ điều hành để đo switch thực, sau đó kiểm tra contention/JVM nếu scaling kém.

Tự kiểm tra:

- CPU-bound workload có 8 threads trên quota 2 CPUs mà throughput không hơn 2 threads; có nên tăng 16? **Không có cơ sở chỉ từ thread count.** Hãy kiểm tra CPU saturation, switch rate, queueing, lock và workload.
- Vì sao 16 sleeping tasks có thể hoàn thành nhanh hơn 1 worker mà CPU utilization vẫn thấp? **Các khoảng chờ có thể overlap**; đây là concurrency khi chờ, không nhất thiết là parallel CPU execution.
- ThreadMXBean.getThreadCount() có cho OS context switch count không? **Không.** Dùng công cụ OS như pidstat/perf/Performance Monitor.
- Context switches/s tăng 3 lần nhưng tasks/s tăng 5 lần có chắc xấu? **Không.** Cần xem latency, CPU, error rate và switch/task; raw switches/s riêng lẻ không đủ kết luận.
- Khi đo ứng dụng thật, vì sao cần p99 latency và queue depth? **Vì throughput tốt có thể che đợi lâu và quá tải trước điểm xử lý**.

**Tài liệu tham khảo (JDK):** [Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html), [Thread.State](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html), [ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html), [ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html), [JFR](https://docs.oracle.com/en/java/javase/21/jfapi/).
