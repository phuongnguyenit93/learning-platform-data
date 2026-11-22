# Concurrency overhead trong Java: context switch, contention và scheduling

> **Phạm vi:** cơ chế và chi phí của lập trình đồng thời trong Java nói chung (JVM, Java threads, Java concurrency API và hệ điều hành). Nội dung không đi vào phần tích hợp concurrency riêng của Spring.

## 1. Mục tiêu và bức tranh tổng thể

Sau bài này, bạn có thể:
- Giải thích vì sao tăng số lượng thread không đồng nghĩa tăng tốc độ xử lý.
- Phân biệt chi phí **context switch**, **contention** (tranh chấp tài nguyên) và **scheduling** (lập lịch), đồng thời nhận ra chúng thường khuếch đại lẫn nhau.
- Phân biệt thread đang chạy, sẵn sàng chạy, chờ khóa và chờ I/O; đọc đúng các trạng thái Java.
- Đo, kiểm chứng nút thắt rồi chọn cách giảm overhead phù hợp, thay vì tùy tiện tăng pool hoặc đổi cơ chế đồng bộ.

**Concurrency** cho phép nhiều công việc cùng tiến triển theo thời gian; **parallelism** nghĩa là thực sự có nhiều công việc chạy cùng lúc trên các tài nguyên tính toán khác nhau. Ví dụ máy có 2 lõi CPU khả dụng mà chương trình tạo 100 thread chạy tính toán liên tục thì tại một thời điểm chỉ có số luồng tương ứng tài nguyên CPU đang chạy; số còn lại phải đợi lượt. Thêm thread có thể tăng overhead mà không tăng lượng CPU.

Một tác vụ có thể tiêu tốn thời gian vào: thực thi mã hữu ích, đợi được xếp lịch, tranh chấp khóa/tài nguyên, đồng bộ dữ liệu, đợi I/O và các chi phí JVM khác. Các giai đoạn có thể chồng lấn giữa các thread, nên không cộng các con số đo của mọi thread một cách máy móc để suy ra wall-clock latency. Hai thước đo cơ bản:

- **Throughput:** số công việc hoàn thành trên mỗi đơn vị thời gian (ví dụ yêu cầu/giây).
- **Latency:** thời gian một công việc từ lúc đến đến lúc hoàn thành; quan tâm thêm p95/p99, không chỉ trung bình.

Một thay đổi tốt cho throughput có thể làm tail latency xấu đi nếu hàng đợi dài lên hoặc một số thread bị đói CPU.

## 2. Context switch: chuyển CPU giữa các luồng

**Context switch** trong ngữ cảnh này chủ yếu là hệ điều hành ngừng thực thi một thread và tiếp tục một thread khác, thường phải lưu/khôi phục trạng thái thực thi như thanh ghi, stack pointer và thông tin lập lịch. Với **platform thread** trong Java (cách sử dụng thông thường ở Java 17), JVM ánh xạ thread Java đến thread hệ điều hành. Đây là sự kiện ở tầng OS; nó không đồng nghĩa với lệnh gọi `Thread.yield()`, một thao tác synchronized hay mọi lần Java đổi trạng thái thread.

Tình huống thường làm thread nhường hoặc mất CPU:
1. **Tự nguyện (voluntary):** đi vào chờ I/O, chờ điều kiện/khóa, ngủ, hoặc cơ chế chờ khiến OS có thể chạy thread khác.
2. **Không tự nguyện (involuntary / preemption):** hết phần CPU được cấp theo chính sách, bị thread khác ưu tiên hơn, hoặc OS cần phân phối CPU.
3. **Di chuyển CPU (migration):** một thread được chạy ở lõi khác; việc này có thể làm giảm lợi ích của cache đã được làm nóng. Migration và context switch là hai sự kiện khác nhau.

Chi phí của switch không chỉ là số chu kỳ lưu/khôi phục thanh ghi. Sự gián đoạn có thể ảnh hưởng cache và locality; chuyển đổi giữa những không gian địa chỉ khác nhau còn có các hệ quả quản lý bộ nhớ tùy CPU/OS. Chi phí thực tế **không có hằng số nanosecond chung cho mọi máy**; nó phụ thuộc phần cứng, tải, loại thread, cache và đường đi của kernel.

**Ví dụ:** 8 thread CPU-bound tranh nhau 2 lõi, mỗi thread chỉ thực hiện một việc tính toán dài. Lập lịch phải luân phiên quyền chạy; khi tăng lên 80 thread, tổng phần tính toán hữu ích không tự nhiên tăng lên 10 lần. Nhiều thời gian hơn có thể mất vào lập lịch, chuyển ngữ cảnh và mất locality.

Không phải mọi context switch đều có hại: nếu một thread đang chờ I/O, chuyển CPU cho việc khác là cơ chế giữ tài nguyên bận một cách hữu ích. Vấn đề là **switch dư thừa so với lượng công việc có ích**, nhất là khi các task quá nhỏ hoặc số thread chạy được vượt quá năng lực CPU.

### Trạng thái Java không phải đồng hồ CPU của OS

| `Thread.State` | Ý nghĩa chính trong Java | Cách đọc khi chẩn đoán |
|---|---|---|
| `RUNNABLE` | Đang chạy **hoặc** sẵn sàng chạy ở JVM; có thể đang đợi lượt CPU từ OS | Không suy ra thread chắc chắn đang dùng CPU |
| `BLOCKED` | Chờ vào/re-enter **intrinsic monitor** (`synchronized`) | Gợi ý tranh chấp monitor |
| `WAITING` | Đợi vô thời hạn (ví dụ `Object.wait`, `Thread.join`, `LockSupport.park`) | Không đồng nghĩa deadlock |
| `TIMED_WAITING` | Đợi có thời hạn (`sleep`, timed wait/park/join) | Có thể là hành vi chủ đích |
| `NEW` / `TERMINATED` | Chưa chạy / đã xong | Không trực tiếp phản ánh tải hiện tại |

Đặc biệt, một thread đang đợi `ReentrantLock` có thể ở `WAITING` do `LockSupport.park`, **không** ở `BLOCKED`. Muốn kết luận nguyên nhân phải nhìn cả stack trace, lock owner, số liệu và lịch sử theo thời gian. Thread dump là ảnh chụp tại một thời điểm.

## 3. Contention: nhiều thread đòi cùng tài nguyên

**Contention** xuất hiện khi nhiều bên cùng cần một tài nguyên hữu hạn: monitor/lock, biến atomic thường xuyên cập nhật, một queue chung, connection pool, file, bộ nhớ/cache line hoặc thiết bị I/O. Khi tranh chấp, thread có thể:

- **Block/park:** nhường CPU rồi chờ được đánh thức; giảm CPU lãng phí nhưng có chi phí wake-up và được xếp lịch lại.
- **Spin/retry:** liên tục kiểm tra hoặc thử lại (ví dụ vòng CAS thất bại); tránh một số lần park ở trường hợp chờ ngắn nhưng đốt CPU, gây traffic bộ nhớ và có thể làm chậm thread đang giữ tài nguyên.
- **Nối hàng:** độ trễ tăng theo số bên đến và thời gian mỗi bên giữ tài nguyên. Dù từng critical section ngắn, tổng lưu lượng tới hotspot đủ cao vẫn làm tắc nghẽn.

Các kiểu tranh chấp trong Java:

1. **Monitor:** `synchronized` bảo vệ tính nhất quán; nếu nhiều thread cần cùng monitor, phần mã được bảo vệ phải đi lần lượt. `Object.wait()` tạm nhả monitor tương ứng khi đợi; `Thread.sleep()` **không** tự nhả monitor đang giữ.
2. **Explicit lock:** `ReentrantLock`, `ReadWriteLock` hoặc các đồng bộ dựa trên AQS có cơ chế riêng để quản lý người đợi; không giả định chúng luôn nhanh hơn `synchronized`. Chế độ fairness có thể giúp chính sách chờ dễ dự đoán hơn trong một số tải, nhưng thường có trade-off với throughput.
3. **Atomic/CAS:** `AtomicLong.incrementAndGet()` tránh khóa monitor nhưng cập nhật một ô nhớ nóng gây cạnh tranh và retry/cache coherence. “Lock-free” **không** có nghĩa “không contention” hoặc luôn nhanh.
4. **False sharing:** hai giá trị logic độc lập nhưng nằm trên cùng cache line và bị các lõi ghi thường xuyên; cache line vẫn phải trao đổi quyền sở hữu. Đây không phải tranh chấp cùng một khóa. Cần đo thực tế trước khi dùng padding/`@Contended`.
5. **Tài nguyên ngoài CPU:** thread tranh connection pool hoặc hàng đợi cũng có thể tăng latency; tăng số thread không tạo ra thêm database connections.

**Ví dụ nút thắt:** 16 worker cùng vào `synchronized (sharedLock)` để cập nhật một cấu trúc chung. Chỉ một worker chạy critical section tại một thời điểm; worker còn lại có thể bị block hoặc thức dậy rồi lại tranh khóa. Kết quả có cả **contention** lẫn **wake-up/scheduling overhead**.

Giảm contention bằng cách thu nhỏ **critical section**, làm công việc bên ngoài khóa, chia dữ liệu theo partition/key, dùng thread-confined/local state rồi gộp kết quả, hoặc chọn primitive phù hợp với tần suất đọc/ghi. Không tách khóa tùy tiện nếu invariant của dữ liệu yêu cầu thay đổi nhiều trường phải nguyên tử cùng nhau.

## 4. Scheduling: ai được chạy, khi nào và trên CPU nào?

Có ít nhất **hai tầng lập lịch** cần phân biệt:

- **Hệ điều hành:** quyết định platform thread nào được CPU chạy, ưu tiên, preemption và phân phối giữa các lõi. Chi tiết phụ thuộc OS và cấu hình; Java không cam kết một thứ tự thực thi cố định.
- **Ứng dụng / executor:** quyết định task được giao cho thread nào, task nào nằm trong queue, pool có bao nhiêu worker. `ExecutorService`/`ThreadPoolExecutor` quản lý tầng này; task được lấy khỏi queue **không bảo đảm** thread của nó lập tức có CPU.

Lưu ý:
- `Thread.yield()` chỉ là **gợi ý** cho scheduler, không bảo đảm nhường cho ai hoặc tạo fairness. Không dùng nó để sửa race condition.
- `Thread.setPriority()` không phải hợp đồng về latency, thứ tự hay quyền CPU giữa các hệ điều hành.
- CPU-bound workload thường cần lượng worker chạy tích cực xấp xỉ năng lực CPU đo được; tăng hàng chục thread chạy CPU trên ít lõi thường không có lợi. I/O-bound workload có thể cần concurrency lớn hơn do nhiều task chờ, nhưng phải tính giới hạn queue, bộ nhớ, pool kết nối và backpressure.
- Nhiều task cực nhỏ còn chịu chi phí tạo task, enqueue/dequeue, đồng bộ queue và wake-up; batch vừa phải đôi khi hiệu quả hơn task-per-item.
- Work stealing (ví dụ `ForkJoinPool`) hỗ trợ cân bằng task phân chia được; nó không giải quyết contention trên cùng một lock hoặc CPU bị oversubscribe.

### Thực tế của một pool

Giả sử có 4 CPU khả dụng, pool 32 worker và 1.000 task CPU-bound. 32 worker không thể đồng thời thực thi toàn bộ trên 4 CPU. Ngoài chờ lượt CPU, task còn chờ trong queue. Nếu chạy cùng pool với việc blocking dài, những task ngắn có thể bị chậm vì worker bị chiếm. Hãy đo queue wait, queue length, active workers, CPU saturation và p95/p99; chỉ điều chỉnh pool sau khi xác định bottleneck.

**Java 21+ (mở rộng):** virtual thread có thể unmount khỏi carrier thread khi nhiều thao tác blocking được hỗ trợ, giảm nhu cầu giữ một OS thread cho mỗi tác vụ đang chờ. Nhưng chúng vẫn được scheduler phân phối qua số carrier hữu hạn, **không** tạo thêm lõi CPU, không xóa contention trên state chung và không làm CPU-bound code tự động nhanh hơn. Ví dụ bên dưới vẫn chạy Java 17 trở lên và dùng platform thread.

## 5. Ba nguồn overhead liên hệ với nhau thế nào?

Một dòng xử lý thường gặp:

`Nhiều task đến → nhiều worker muốn cùng khóa → worker chờ/park → worker giữ khóa nhả khóa → OS đánh thức/xếp lịch worker kế tiếp → worker tranh khóa lại → kết quả chậm`.

Ở đây:
- **Contention** là nguyên nhân khiến task không thể tiến triển độc lập.
- **Scheduling** quyết định lúc nào thread được tiếp tục.
- **Context switching** có thể là một phần chi phí khi chuyển CPU giữa các thread.

Một trường hợp ngược lại: có 64 worker chạy các phép tính độc lập trên 4 lõi, không dùng khóa chung. Khi đó contention trên application lock có thể rất thấp, nhưng oversubscription và scheduling overhead vẫn cao. Cần xác định đúng hiện tượng thay vì gọi mọi vấn đề concurrency là “lock chậm”.

### Triệu chứng không tự chứng minh nguyên nhân

| Quan sát | Có thể là gì | Cần kiểm tra thêm |
|---|---|---|
| CPU cao, throughput không tăng khi thêm thread | CPU saturation, CAS retry, spin, cache contention | CPU profiling, số core thực dùng, hotspot atomic |
| Nhiều thread `BLOCKED` cùng monitor | Lock contention/critical section dài | Lock owner, stack, JFR monitor events |
| Nhiều thread `WAITING` | Worker nhàn rỗi, đợi queue/condition, hoặc chờ khóa kiểu park | Stack/queue metrics, loại wait, thời lượng |
| CPU thấp nhưng latency cao | Đợi I/O, queue, lock, cạn pool kết nối | Trace thời gian queue/I/O/lock, JFR |
| Context-switch rate tăng mạnh | Oversubscription, wake-up thường xuyên, blocking lặp | Voluntary/involuntary switch, CPU, throughput |
| p99 tăng khi throughput tăng | Hàng đợi/tail contention, GC hoặc các nút thắt khác | Queue wait, duration distribution, GC/JFR |

## 6. Thí nghiệm Java 17+: một điểm cập nhật chung

Ví dụ thực hành so sánh một `AtomicLong` (một điểm cập nhật atomic chung) và `LongAdder` (phân tán cập nhật khi có contention). Hai cách đều cần đếm chính xác sau khi worker kết thúc; kết quả **thời gian không cố định** và không mặc định `LongAdder` phải thắng trong mỗi lần chạy.

Tạo file **`OverheadLab.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public class OverheadLab {
    private static final int THREADS = 4;
    private static final int INCREMENTS_PER_THREAD = 100_000;

    @FunctionalInterface
    interface Work { void run(); }

    private static long timeConcurrent(Work work) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(THREADS);
        CountDownLatch start = new CountDownLatch(1);
        Thread[] workers = new Thread[THREADS];

        for (int i = 0; i < THREADS; i++) {
            workers[i] = new Thread(() -> {
                ready.countDown();
                try {
                    start.await();
                    work.run();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, "worker-" + i);
            workers[i].start();
        }

        ready.await();
        long begin = System.nanoTime();
        start.countDown();
        for (Thread worker : workers) worker.join();
        return System.nanoTime() - begin;
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicLong atomic = new AtomicLong();
        long atomicNs = timeConcurrent(() -> {
            for (int i = 0; i < INCREMENTS_PER_THREAD; i++) atomic.incrementAndGet();
        });

        LongAdder adder = new LongAdder();
        long adderNs = timeConcurrent(() -> {
            for (int i = 0; i < INCREMENTS_PER_THREAD; i++) adder.increment();
        });

        System.out.println("AtomicLong count=" + atomic.get());
        System.out.println("LongAdder count=" + adder.sum());
        System.out.printf("AtomicLong elapsed=%.2f ms%n", atomicNs / 1_000_000.0);
        System.out.printf("LongAdder elapsed=%.2f ms%n", adderNs / 1_000_000.0);
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 OverheadLab.java
java OverheadLab
```

Hai dòng kết quả đếm **chắc chắn** (nếu chương trình hoàn tất bình thường):

```text
AtomicLong count=400000
LongAdder count=400000
```

Hai dòng tiếp theo có dạng `AtomicLong elapsed=... ms` và `LongAdder elapsed=... ms`, với số thay đổi tùy máy/lần chạy. `CountDownLatch` cho các thread bắt đầu công việc gần cùng thời điểm; `join()` bảo đảm phép đếm cuối được đọc sau khi worker hoàn tất. `System.nanoTime()` đo khoảng elapsed, không đo riêng context-switch cost.

Cần hiểu giới hạn của thí nghiệm:

- `AtomicLong` có ngữ nghĩa đọc giá trị atomic trực tiếp; `LongAdder.sum()` **không** cung cấp snapshot nguyên tử khi đang có cập nhật đồng thời. Sau `join()`, dùng `sum()` để đọc tổng cuối là phù hợp.
- `LongAdder` có thêm chi phí và bộ nhớ; ở contention thấp `AtomicLong` có thể nhanh hơn. Cả hai không đại diện trực tiếp cho chi phí monitor `synchronized`.
- Benchmark micro rất dễ lệch vì warm-up/JIT, GC, độ ưu tiên, số lõi, nhiệt/CPU frequency, thứ tự phép đo và nhiễu hệ thống. Chạy `java OverheadLab` một lần **không đủ** để kết luận hiệu năng.
- Để so sánh đáng tin hơn: dùng **JMH** với warm-up, nhiều iteration/fork và môi trường tải kiểm soát; báo cả phân phối kết quả. Đo throughput/latency dưới tải thực tế mới quyết định tối ưu production.

**Bài thử mở rộng:** giữ cùng mã, chạy với `THREADS = 1, 2, 4, 8, 16` và cố định số phép tăng **trên mỗi thread**; khi đó tổng công việc tăng theo số thread, nên **không** được dùng thời gian toàn chương trình để so scalability trên khối lượng công việc cố định. Muốn so cùng lượng việc, chia một tổng phép tăng cố định cho số worker, kiểm tra số dư, warm-up và đo độc lập.

## 7. Quan sát overhead trong JVM và hệ điều hành

### Thread dump: biết đang đợi gì

Khi ứng dụng chạy đủ lâu, dùng PID Java thực tế:

```bash
jcmd <PID> Thread.print
```

Đọc nhóm stack có nhiều thread cùng đợi một monitor/lock, đối chiếu khóa đang được giữ, rồi chụp thêm vài lần cách nhau để phân biệt chờ dài với ảnh chụp tình cờ. `BLOCKED`/`WAITING` chỉ cho biết trạng thái ở thời điểm lấy dump; đừng suy ra tổng thời gian chờ chỉ từ một ảnh.

### ThreadMXBean: số đếm ở tầng Java

`java.lang.management.ManagementFactory.getThreadMXBean()` cho phép đọc dữ liệu thread. Trước khi bật contention monitoring, phải kiểm tra `isThreadContentionMonitoringSupported()`; nếu được hỗ trợ, `setThreadContentionMonitoringEnabled(true)` giúp ghi nhận `ThreadInfo.getBlockedTime()` và `getWaitedTime()` (có overhead đo đạc). `getBlockedCount()` đo số lần đợi **vào monitor**; nó không phải tổng số context switch hay tổng số lần CAS thất bại. Thời gian chờ có thể là `-1` khi monitoring chưa bật hoặc không được hỗ trợ. Không dùng thông tin quản trị thread để điều khiển đồng bộ của chính chương trình.

```java
// Đoạn mã minh họa đặt bên trong một method; không phải chương trình độc lập.
var mx = java.lang.management.ManagementFactory.getThreadMXBean();
if (mx.isThreadContentionMonitoringSupported()
        && !mx.isThreadContentionMonitoringEnabled()) {
    mx.setThreadContentionMonitoringEnabled(true);
}
var info = mx.getThreadInfo(Thread.currentThread().getId());
if (info != null) {
    System.out.println("monitor blocked count = " + info.getBlockedCount());
    System.out.println("monitor blocked time ms = " + info.getBlockedTime());
}
```

### Java Flight Recorder (JFR): tìm điểm chờ có ngữ cảnh

Chạy workload đủ lâu và ghi JFR (JDK 17+):

```bash
java -XX:StartFlightRecording=filename=overhead.jfr,settings=profile,dumponexit=true OverheadLab
jfr summary overhead.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark overhead.jfr
```

`jdk.JavaMonitorEnter` gợi ý tranh chấp monitor, `jdk.JavaMonitorWait` là chờ monitor, `jdk.ThreadPark` là parking; kiểm tra duration, stack trace và thread. **Không có event không chứng minh không có chờ:** các mẫu cấu hình JFR có thể có ngưỡng thời gian, tắt một số event, và workload quá ngắn có thể không tạo event hữu ích. Với sản phẩm thực, thiết kế phiên ghi đủ dài và xem bằng JDK Mission Control khi cần phân tích timeline.

### OS-level: đo context switch thật

Trên Linux, có thể dùng công cụ giám sát thread như:

```bash
pidstat -w -t -p <PID> 1
```

Nếu đã cài `sysstat`, theo dõi các chỉ số voluntary/involuntary context switch theo thread; đối chiếu CPU utilization, runnable queue và throughput. Trên hệ điều hành khác, dùng công cụ profiling/counters tương ứng. Chỉ nhìn tổng số context switch trên toàn máy không đủ để quy trách nhiệm cho process Java. Thread CPU time, Java blocked time, OS switch count và wall-clock latency **là các số đo khác nhau**, không thay thế cho nhau.

## 8. Phương pháp tối ưu theo nguyên nhân

**Bước 1 — Tạo baseline có tính so sánh.** Cố định input, tải, cấu hình JVM, số lõi khả dụng; ghi throughput, latency p50/p95/p99, CPU, GC, số active thread, queue length/wait và kết quả correctness. Đo nhiều lần trước khi kết luận.

**Bước 2 — Phân loại bottleneck.**
- **CPU đầy, nhiều runnable, ít chờ:** xem CPU profile, oversubscription, task quá nhỏ, CAS retry hoặc false sharing.
- **Nhiều thread chờ monitor/lock:** dùng JFR/dump để tìm lock owner, critical section và tần suất truy cập.
- **Nhiều thread chờ queue/I/O:** xem slow external calls, connection pool, năng lực downstream và backpressure.
- **Thread tạo/hủy liên tục:** kiểm tra model thực thi, worker reuse, task granularity.

**Bước 3 — Áp dụng thay đổi nhỏ, đo lại.**
- Rút ngắn critical section; chuyển tính toán/I/O ra ngoài lock khi an toàn; giảm lock granularity nếu invariant cho phép.
- Partition/shard state theo key; thread-local aggregation hoặc `LongAdder` cho thống kê cập nhật nhiều mà không cần snapshot nhất quán trong lúc cập nhật.
- Giới hạn runnable workers cho CPU-bound workload; tách pool theo bản chất blocking/CPU khi có căn cứ; dùng queue **có giới hạn** và cơ chế backpressure rõ ràng.
- Tránh thức dậy liên tục để polling; dùng blocking queue/condition với điều kiện đúng thay vì `sleep` và `yield` rải rác.
- Gộp thao tác nhỏ thành batch hợp lý; tránh tạo thread và futures cho từng phép toán quá nhỏ.
- Nếu cần bảo đảm thời gian chờ, đánh giá fairness/starvation có đo đạc. Fairness thường đánh đổi throughput; test cả tail latency.

**Bước 4 — Chứng minh cải thiện và giữ correctness.** Đo lại trên tải đại diện, đồng thời kiểm tra race, lost update, deadlock, starvation, thứ tự quan sát và yêu cầu visibility. Một cách “nhanh hơn” nhưng bỏ đồng bộ cần thiết là lỗi, không phải tối ưu.

## 9. Những nhầm lẫn hay gặp

1. **“Nhiều thread luôn nhanh hơn.”** Sai nếu CPU đã bão hòa, queue/lock bị tắc hoặc overhead chiếm ưu thế.
2. **“RUNNABLE nghĩa là thread đang dùng CPU.”** Sai: có thể đang sẵn sàng nhưng chưa được OS chạy.
3. **“BLOCKED là mọi kiểu chờ lock.”** Sai: Java `BLOCKED` mô tả chờ monitor; park từ các synchronizer khác có trạng thái khác.
4. **“Lock-free nghĩa là không tranh chấp.”** Sai: CAS retries và cache-coherence traffic vẫn có thể tốn nhiều CPU.
5. **“sleep/yield chữa race hoặc bảo đảm fairness.”** Sai: cần thiết kế synchronization, condition và lifecycle đúng.
6. **“CPU thấp thì concurrency không có vấn đề.”** Sai: thread có thể kẹt I/O, queue hoặc lock mà ít tiêu thụ CPU.
7. **“Thấy nhiều WAITING là deadlock.”** Sai: executor worker nhàn rỗi cũng thường WAITING; cần phân tích wait graph và tiến triển thực tế.
8. **“Đo wall-clock bằng nanoTime cho biết context switch.”** Sai: wall-clock gồm cả thời gian chạy, đợi, bị preempt và nhiễu.
9. **“Đổi synchronized sang ReentrantLock/AtomicLong sẽ tự nhanh.”** Sai: tính đúng đắn, fairness, contention pattern và tải mới quyết định.
10. **“Virtual thread xóa chi phí scheduling.”** Sai: vẫn có scheduling, carrier threads và tài nguyên chung.

## 10. Tự kiểm tra

**Tình huống A:** 8 CPU core, 8 thread xử lý phép tính độc lập đạt 100% CPU; nâng lên 64 thread làm p99 xấu đi mà throughput không tăng. **Giải thích:** CPU-bound oversubscription tăng thời gian chờ lượt và có thể tăng context switching/cache disruption. Thử giới hạn active worker quanh CPU khả dụng rồi đo lại.

**Tình huống B:** CPU chưa cao, 40 thread cùng `BLOCKED` trên một monitor, thread giữ monitor làm I/O. **Giải thích:** lock contention do critical section giữ quá lâu. Đưa I/O ra ngoài khóa khi giữ được invariant, hoặc thay kiến trúc chia sẻ dữ liệu rồi dùng JFR/trace xác minh.

**Tình huống C:** Một bộ đếm `AtomicLong` bị tăng từ rất nhiều worker, CPU cao dù không có thread `BLOCKED`. **Giải thích:** hotspot trên một ô nhớ atomic có thể làm CAS/cache coherence tốn chi phí. Cân nhắc `LongAdder` nếu semantics cho phép; kiểm tra độ chính xác và đo under load.

**Tình huống D:** 200 thread đều `WAITING` trong `BlockingQueue.take()` khi queue rỗng. **Giải thích:** đây thường là worker nhàn rỗi đợi công việc; trạng thái WAITING tự nó chưa chứng minh lỗi. Cần nhìn throughput, incoming workload và độ dài queue.

## Tài liệu tham khảo

- [Java SE 17: `Thread.State`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html) — định nghĩa trạng thái Java.
- [Java SE 17: `ThreadInfo`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html) — blocked/waited time, owner và monitor.
- [Java SE 17: `ThreadMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html) — kiểm tra/bật contention monitoring.
- [Java SE 17: `LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html) — đặc tính thống kê dưới contention.
- [JDK 17: lệnh `jfr`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html) — xem/summarize recording.
- [OpenJDK: Java Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/) — cấu hình và phân tích bản ghi.

**Ý chính cần nhớ:** xác định công việc nào thực sự dùng CPU, công việc nào đang đợi resource/queue, rồi đo context switching và contention trong điều kiện tải thực; tăng thread chỉ hữu ích khi có tài nguyên và sự độc lập đủ để chúng tiến triển.