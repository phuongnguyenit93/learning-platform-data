# 10.7 Phân biệt thiếu carrier, tài nguyên bên ngoài bão hòa và tác vụ tốn CPU

## Mục tiêu và bản chất vấn đề

Một dịch vụ chạy hàng nghìn **virtual thread** vẫn có thể bị tăng p95/p99, timeout và throughput đứng yên. Cần phân biệt ba tình huống:

1. **Không có carrier sẵn sàng:** virtual thread đang cần chạy nhưng không được mount kịp lên platform thread do scheduler thiếu năng lực tiến triển hoặc nhiều carrier bị giữ trong blocking không thể unmount.
2. **Tài nguyên bên ngoài bão hòa:** tác vụ đã hoạt động và chờ connection pool, DB, HTTP downstream, rate limit, quota hay tài nguyên khác. Việc chờ có thể nhường carrier hoàn toàn; tăng số carrier không giải quyết giới hạn phía ngoài.
3. **Tác vụ tốn CPU:** công việc tính toán, serialize, nén, mã hóa, xử lý dữ liệu hoặc vòng lặp thực thi liên tục. Virtual thread vẫn cần CPU thật và không tạo thêm lõi xử lý.

**Yêu cầu chẩn đoán:** xác định *tác vụ chờ tại đâu*, *tài nguyên nào chạm giới hạn*, *CPU dùng cho việc gì*, rồi kiểm chứng bằng thay đổi có kiểm soát. Nhiều bottleneck có thể xảy ra đồng thời; không gán nguyên nhân chỉ dựa trên số virtual thread.

## 1. Cơ chế cần hiểu trước khi đo

Virtual thread (`java.lang.Thread`) do JVM lên lịch trên các **carrier** là platform thread. Khi một thao tác blocking được JVM hỗ trợ (ví dụ `Thread.sleep`, nhiều socket I/O của JDK) làm virtual thread **unmount**, carrier được trả về để chạy virtual thread khác. Virtual thread chờ trong connection pool hoặc chờ HTTP có thể tiêu tốn bộ nhớ/tài nguyên khác nhưng không nhất thiết chiếm carrier. Khi tác vụ sẵn sàng tiếp tục, nó lại cần được scheduler mount.

Tách ít nhất bốn trạng thái:

- **Mounted và chạy code:** cần carrier và có thể tiêu tốn CPU.
- **Chờ nhưng đã unmount:** đang đợi permit, I/O hay timer; carrier có thể phục vụ tác vụ khác.
- **Ready-to-run nhưng chưa được mount:** xếp hàng chờ scheduler; độ trễ ở đây gợi ý áp lực carrier/scheduler.
- **Pinned trong lúc blocking:** không thể unmount ở đoạn cụ thể, làm carrier bị giữ dù công việc không thực sự chạy CPU.

**Phiên bản JDK thay đổi cách diễn giải pinning.** Trên **JDK 21–23**, blocking khi giữ monitor bằng `synchronized` có thể pin carrier; native/foreign call cũng có thể pin. Từ **JDK 24**, JEP 491 loại bỏ pinning *do `synchronized`*; một số đường native/VM vẫn có thể pin. Vì vậy một stack chứa `synchronized` không tự chứng minh pinning trên JDK 24+. Scheduler parallelism thường lấy số CPU JVM nhìn thấy làm giá trị khởi đầu, nhưng **đây không phải giới hạn tổng virtual thread**. Virtual thread phù hợp với nhiều tác vụ chờ I/O; nó không khiến từng phép tính chạy nhanh hơn.

## 2. Bảng phân biệt ba điểm nghẽn

| Dữ liệu quan sát | Carrier thiếu/bị giữ | Bão hòa tài nguyên bên ngoài | CPU-bound |
| --- | --- | --- | --- |
| CPU tiến trình | Có thể thấp khi carrier bị pin và chờ, hoặc cao nếu carrier chạy code CPU dài | Thường thấp/vừa khi chờ DB/HTTP; có thể cao nếu retry/serialize kèm theo | Thường gần mức CPU thật được cấp, CPU samples tập trung ở hot code |
| Hàng đợi tăng | Virtual thread đã ready nhưng chờ scheduler/carrier | Pool pending, permit waiters, DB queue, HTTP queue, rate-limit | Công việc CPU tranh CPU; request đợi các bước tính toán hoàn tất |
| JFR/dump | `jdk.VirtualThreadPinned` dài/lặp lại nếu có pin; ready queue kéo dài, ít tiến triển | Stack chờ permit/JDBC/HTTP, pool active=max, downstream p95 cao, 429/503 | `jdk.ExecutionSample` dày tại thuật toán, nhiều thời gian tính toán thực |
| Kiểm chứng | Loại bỏ đúng đoạn gây pin hoặc đối chiếu JDK; đo lại độ trễ ready→run | Giảm admission/điều chỉnh pool hoặc capacity downstream có căn cứ | Giảm CPU concurrency/optimize, thử với giới hạn core tương ứng |
| Hướng khắc phục | Tránh blocking giữ carrier, rút ngắn critical section, sửa native path | Backpressure, timeout, concurrency limit, tối ưu DB/dịch vụ đích | Tối ưu workload, giới hạn song song CPU, tăng tài nguyên khi cần |

Đây là **mẫu tương quan**, không phải công thức suy luận một chỉ số. CPU thấp + p99 cao có thể do DB chậm, monitor contention hoặc pinned carrier; phải đi tiếp bằng metric tại đúng điểm chờ. CPU cao cũng có thể là GC/retry chứ chưa chắc do thuật toán nghiệp vụ.

## 3. Quy trình điều tra có bằng chứng

### Bước 1 — Đặt đường cơ sở

Ghi lại bản **JDK/build**, CPU JVM nhìn thấy, CPU quota/container, bộ nhớ/GC, arrival rate, throughput, in-flight, timeout/error, p50/p95/p99. So sánh cùng khoảng tải trước và sau suy giảm. Đừng nhìn số lượng virtual thread rồi quy ra số carrier cần có.

Instrument thời gian tại biên các bước:

- `T_wait_to_start`: từ lúc giao việc tới lúc thực sự bắt đầu hoặc tiếp tục chạy (nếu ứng dụng có đo).
- `T_wait_pool`: từ lúc xin permit/connection tới lúc được cấp.
- `T_downstream`: thời gian giữ connection và thực hiện JDBC/HTTP.
- `T_cpu`: phần tính toán của ứng dụng (cần CPU profiler/CPU-time để ước lượng), cộng các phần khác.

Có thể hình dung với request tuần tự: `T_total ≈ T_wait_to_start + T_wait_pool + T_downstream + T_cpu + T_other`. Với span song song/lồng nhau phải tránh cộng đúp. Theo định luật Little ở trạng thái tương đối ổn định, `L ≈ λ × W`: tăng thời gian chờ làm số request in-flight tăng; **nhiều virtual thread đang tồn tại không phải bằng chứng thiếu carrier**.

### Bước 2 — Hỏi CPU và hàng đợi cùng lúc

1. **CPU gần chạm quota**, profiler cho thấy ứng dụng tính toán liên tục → điều tra **CPU-bound** trước. Phân biệt CPU do logic nghiệp vụ, GC, encode/decode, retry và lock spin.
2. **CPU còn dư**, pool `active=max`, `pending>0`, acquire-time hoặc downstream p95 tăng → nghiêng về **external saturation**. Virtual thread chờ pool thường không cần giữ carrier.
3. **CPU còn dư**, pool/downstream không đầy, nhưng virtual thread ready chờ lâu; có pinning events/traces kéo dài hoặc scheduler queue tồn đọng → nghiêng về **carrier/scheduler bottleneck**.
4. **CPU cao đồng thời pool pending cao** → có thể cả hai. Dùng thời gian từng span và load sweep để tìm ngưỡng nào bị chạm trước, thay một yếu tố mỗi lần.

CPU 100% trong một công cụ có thể là **một lõi**, không phải 100% toàn bộ CPU quota. State `RUNNABLE`/`WAITING` đơn lẻ không nói được tác vụ đang chiếm carrier hay đã unmount.

### Bước 3 — Thu thập dump, JFR và số đo downstream

Dùng `jcmd` của đúng JVM/JDK đích; `<PID>` là placeholder được thay bằng PID thực tế:

~~~bash
jcmd <PID> Thread.dump_to_file -format=json vthreads.json
jcmd <PID> Thread.dump_to_file -format=text vthreads.txt
~~~

Các lệnh này dành cho JDK 21+ và giúp thấy virtual thread mà thread dump kiểu cũ có thể thiếu. Thu vài snapshot cách nhau một khoảng khi lỗi tái hiện; xem stack trùng lặp, nơi tác vụ chờ và sự tiến triển theo thời gian. Tùy JDK, dump không chứa đầy đủ lock/JNI metadata và không đại diện ảnh chụp nguyên tử tuyệt đối của toàn JVM.

Khởi động JFR trong khoảng tải bất thường:

~~~bash
jcmd <PID> JFR.start name=vt-triage settings=profile duration=60s filename=vt-triage.jfr
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-triage.jfr
~~~

Chỉ đọc file sau khi recording hoàn tất (hoặc dump thủ công). Mở bằng JDK Mission Control để phân tích `jdk.ExecutionSample`, sự kiện pinning/blocking, hot methods và thời điểm latency tăng. Trên **JDK 21**, `jdk.VirtualThreadPinned` thường bật mặc định với threshold **20 ms**. Không có event **không đồng nghĩa** scheduler khỏe: thao tác có thể dưới threshold, không thuộc kiểu pin được ghi, không bật trong cấu hình ghi hoặc nghẽn do nguyên nhân khác. `VirtualThreadSubmitFailed` là lỗi submit/unpark, không phải phép đo tổng queue.

**Chẩn đoán theo phiên bản:**

- **JDK 21–23:** có thể khởi động với `-Djdk.tracePinnedThreads=full` để thấy stack khi virtual thread blocking lúc pinned. Chỉ dùng khi cần, trong phạm vi test/diagnostic phù hợp.
- **JDK 24+:** `jdk.management.VirtualThreadSchedulerMXBean` cho biết `getParallelism()`, `getPoolSize()`, `getMountedVirtualThreadCount()` và `getQueuedVirtualThreadCount()`. Các số là ước lượng; nhìn xu hướng khi tải tăng, không xem một sample như kết luận. Interface này **chưa có ở Java 21**. Một số JDK mới có lệnh `jcmd <PID> Thread.vthread_scheduler`; xác minh bằng `jcmd <PID> help` trên phiên bản đang sử dụng.
- Trên mọi JDK: đo cùng lúc **pool idle/active/pending/acquire-timeout**, DB query duration/slow queries, HTTP duration/status/rate limit, CPU samples và GC. Scheduler thông thoáng không chứng minh downstream thông thoáng.

## 4. Phân tích ba sự cố điển hình

### A. Carrier bị pin trên JDK 21

Dịch vụ có nhiều virtual thread chạy `synchronized(lock) { blockingCall(); }` trong đường nóng, mỗi lần đợi vài trăm mili giây. CPU tiến trình chưa đầy, các tác vụ khác ready nhưng tiến triển chậm; JFR xuất hiện nhiều `jdk.VirtualThreadPinned` dài với stack ở vị trí blocking dưới monitor. **Kết luận có căn cứ:** carrier bị giữ lúc virtual thread lẽ ra nên nhường carrier.

Cách xử lý trên JDK 21: chuyển I/O/blocking ra ngoài vùng khóa nếu giữ nguyên được tính đúng đắn, rút ngắn vùng khóa, hoặc dùng `ReentrantLock` đúng cách khi phải đồng bộ mà vẫn cần unmount. **Không** thay tất cả `synchronized`: critical section ngắn không blocking thường không phải điểm nghẽn. Khi triển khai JDK 24+, monitor-related pinning đã thay đổi; phải đo lại, không suy diễn từ triệu chứng JDK 21. Các call native/VM còn phải kiểm tra riêng.

### B. Connection pool hoặc remote service bão hòa

Ứng dụng có **10 DB connection**. Mỗi request giữ connection trung bình **250 ms**. Nếu mọi transaction sử dụng một connection và không có giới hạn khác, trần gần đúng là **10 / 0,25 = 40 transaction/giây**. 10.000 virtual thread không làm mức này tăng lên 400/giây. Khi đến 120 request/giây, `active=10`, pool pending và acquire time tăng, request timeout; CPU phía ứng dụng có thể thấp vì các virtual thread chờ đã unmount.

Xác minh bằng pool metrics, DB query latency, locks, quota, transaction duration, số request hoàn thành. Sửa bằng cách giảm thời gian giữ connection, tối ưu query/transaction, giới hạn đồng thời, timeout và backpressure. **Chỉ tăng pool** khi DB thực sự chịu thêm tải; pool lớn hơn có thể làm DB chậm hơn. Với HTTP 429, cần giảm tốc độ/rate-limit/backoff thay vì bơm thêm request.

### C. Workload thật sự CPU-bound

Có **4 vCPU hữu dụng**, nhưng 500 virtual thread cùng nén hoặc mã hóa dữ liệu. Profiler thấy CPU time tập trung ở thuật toán, process dùng gần hết quota, throughput ít tăng khi tăng đồng thời 50→500; p99 có thể tệ hơn vì tranh CPU. **Kết luận:** nút thắt CPU. Virtual thread không tự time-slice phép tính CPU dài để tạo thêm năng lực xử lý.

Ưu tiên giảm work/request, profile/optimize hot path, cache/batch có kiểm chứng, giới hạn tác vụ CPU đồng thời gần năng lực CPU thật hoặc cấp thêm CPU. Nếu luồng vừa chờ DB vừa xử lý JSON lớn, hãy đo **hai pha** độc lập; bottleneck có thể dịch chuyển sau khi sửa DB.

## 5. Lab Java 21+: đối chiếu ba chế độ

Chạy cùng 12 virtual thread với ba kiểu công việc. `external` mô phỏng downstream chỉ có 2 chỗ hoạt động bằng `Semaphore`; `Thread.sleep` đại diện khoảng chờ I/O, không gọi DB thật. `cpu` bận tính toán khoảng 250 ms/task. `pin21` giữ 12 monitor **riêng biệt** khi sleep để minh họa pinning kiểu JDK 21 mà không nhầm với tranh chấp trên cùng lock. Mọi thời gian là kết quả thực nghiệm, không có một stdout định thời cố định.

Tạo file **`VirtualThreadBottleneckLab.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class VirtualThreadBottleneckLab {
    private static final int TASKS = 12;
    private static final int DURATION_MS = 250;
    private static final Semaphore EXTERNAL_SLOTS = new Semaphore(2);
    private static final AtomicInteger IN_EXTERNAL = new AtomicInteger();
    private static final AtomicInteger PEAK_EXTERNAL = new AtomicInteger();
    private static final AtomicLong PERMIT_WAIT_NS = new AtomicLong();
    private static final Object[] LOCKS = new Object[TASKS];
    private static volatile long resultSink;

    static {
        for (int i = 0; i < TASKS; i++) {
            LOCKS[i] = new Object();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1 ||
                !(args[0].equals("external") ||
                  args[0].equals("cpu") ||
                  args[0].equals("pin21"))) {
            System.out.println(
                    "Usage: java VirtualThreadBottleneckLab external|cpu|pin21");
            return;
        }

        String mode = args[0];
        long start = System.nanoTime();

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<?>> tasks = new ArrayList<>();
            for (int id = 0; id < TASKS; id++) {
                final int taskId = id;
                tasks.add(executor.submit(() -> {
                    switch (mode) {
                        case "external" -> externalWait();
                        case "cpu" -> compute();
                        case "pin21" -> pinOnJdk21(taskId);
                        default -> throw new IllegalArgumentException(mode);
                    }
                    return null;
                }));
            }
            for (Future<?> task : tasks) {
                task.get();
            }
        }

        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start);
        long avgPermitWaitMs = TimeUnit.NANOSECONDS.toMillis(
                PERMIT_WAIT_NS.get() / TASKS);
        System.out.printf(
                "mode=%s tasks=%d elapsedMs=%d peakExternal=%d avgPermitWaitMs=%d%n",
                mode, TASKS, elapsedMs, PEAK_EXTERNAL.get(), avgPermitWaitMs);
    }

    private static void externalWait() throws InterruptedException {
        long startWait = System.nanoTime();
        EXTERNAL_SLOTS.acquire();
        PERMIT_WAIT_NS.addAndGet(System.nanoTime() - startWait);
        try {
            int current = IN_EXTERNAL.incrementAndGet();
            PEAK_EXTERNAL.accumulateAndGet(current, Math::max);
            try {
                Thread.sleep(DURATION_MS);
            } finally {
                IN_EXTERNAL.decrementAndGet();
            }
        } finally {
            EXTERNAL_SLOTS.release();
        }
    }

    private static void compute() {
        long deadline = System.nanoTime()
                + TimeUnit.MILLISECONDS.toNanos(DURATION_MS);
        long v = 0x9E3779B97F4A7C15L;
        while (System.nanoTime() < deadline) {
            v ^= v << 13;
            v ^= v >>> 7;
            v ^= v << 17;
        }
        resultSink = v;
    }

    private static void pinOnJdk21(int id)
            throws InterruptedException {
        // Khóa riêng cho mỗi task để không tạo monitor contention giả.
        synchronized (LOCKS[id]) {
            Thread.sleep(DURATION_MS);
        }
    }
}
~~~

Biên dịch/chạy với **Java 21 trở lên**:

~~~bash
javac VirtualThreadBottleneckLab.java
java -Djdk.virtualThreadScheduler.parallelism=2 VirtualThreadBottleneckLab external
java -Djdk.virtualThreadScheduler.parallelism=2 VirtualThreadBottleneckLab cpu
java -Djdk.virtualThreadScheduler.parallelism=2 VirtualThreadBottleneckLab pin21
~~~

Dòng stdout có dạng `mode=... tasks=12 elapsedMs=... peakExternal=... avgPermitWaitMs=...`; **giá trị `elapsedMs` và `avgPermitWaitMs` thay đổi giữa lần chạy**. Cách đọc:

- `external`: `peakExternal` tối đa **2**, permit wait tăng khi slot bận. Với 12 tác vụ × 250 ms / 2 slot, thời gian thường gần **1,5 giây** cộng overhead, mặc dù đa số thời gian là chờ và carrier có thể rảnh.
- `cpu`: `peakExternal=0`, `avgPermitWaitMs=0`. Năng lực CPU thực của JVM/container quyết định mức song song hữu ích; đặt scheduler parallelism=2 chỉ để mô phỏng, **không phải gợi ý tuning production**.
- `pin21`: trên **JDK 21–23**, `Thread.sleep` bên trong `synchronized` có thể giữ carrier và kéo dài tổng thời gian khi chỉ có hai carrier; có thể thấy JFR pinning. Trên **JDK 24+**, `synchronized` không còn gây loại pinning này, vì vậy cùng chương trình có thể hoàn thành gần thời gian sleep đơn lẻ. `peakExternal` và permit wait đều bằng 0 ở chế độ này.

Đây là lab có mục đích minh họa: semaphore **mô phỏng** tài nguyên bên ngoài, `Thread.sleep` **mô phỏng** latency, CPU busy loop không thay cho benchmark chuẩn. Không dùng `pin21` để tạo tải trên production; không suy ra sửa bằng cách luôn tăng `jdk.virtualThreadScheduler.parallelism`.

## 6. Quyết định sửa và đo lại

| Chẩn đoán được xác nhận | Hành động trực tiếp | Tiêu chí sau sửa |
| --- | --- | --- |
| Carrier bị giữ trong pinning kéo dài | Di chuyển blocking khỏi monitor (đặc biệt JDK 21), chọn lock phù hợp, thay/giới hạn call native gây pin, đánh giá nâng JDK | Pinned duration/count giảm, ready queue tiến triển, throughput và p99 cải thiện cùng tải |
| External pool/downstream bão hòa | Giảm hold time, tối ưu query, cap concurrency, backpressure, timeout, điều chỉnh downstream capacity hợp lý | Pool pending/acquire time giảm, 429/5xx không tăng, p99/error giảm |
| CPU-bound | Profile code, giảm việc mỗi request, giới hạn concurrent CPU tasks, tăng CPU nếu cần | CPU time/request giảm hoặc CPU capacity đủ; throughput tăng mà p99/GC không xấu |

Thử với **mức tải nền → sát ngưỡng → trên ngưỡng**, đổi **một yếu tố mỗi lần**, ghi lại throughput, p50/p95/p99, error, CPU/GC, scheduler queue, pool queue và downstream duration. Khi tháo một điểm nghẽn, điểm nghẽn kế tiếp có thể lộ rõ; cần tiếp tục quan sát toàn pipeline.

## 7. Lỗi suy luận thường gặp

1. **“Có 20.000 virtual thread nên cần 20.000 carrier.”** Virtual thread chờ có thể đã unmount; số virtual thread đang sống không phải số carrier cần đồng thời.
2. **“CPU thấp chứng minh carrier bị pin.”** DB slow query, queue pool, HTTP timeout, lock cũng làm CPU thấp. Cần bằng chứng scheduler/pinning.
3. **“Không có `jdk.VirtualThreadPinned` thì không thể nghẽn carrier.”** Event có threshold/phạm vi; CPU hog và các vấn đề scheduler khác không bắt buộc tạo event.
4. **“Tăng virtual thread, pool hoặc scheduler parallelism luôn tăng throughput.”** Không thay đổi capacity downstream hay số lõi; có thể làm p99 tệ hơn do backlog.
5. **“Mọi `synchronized` đều pin.”** Cần xét có blocking không và xét JDK; JDK 24 loại bỏ monitor-related pinning.
6. **“Một thread dump đủ kết luận.”** Cần nhiều snapshot và chuỗi thời gian JFR/metrics; trạng thái WAITING/RUNNABLE riêng lẻ dễ gây hiểu nhầm.
7. **“Tăng connection pool là chữa DB chậm.”** DB quá tải có thể chậm hơn vì nhiều transaction/lock tranh chấp. Tăng sau khi kiểm tra năng lực DB.
8. **“Virtual thread thích hợp cho CPU jobs dài.”** Virtual thread chủ yếu giúp scale tác vụ I/O-bound; CPU jobs vẫn cần kiểm soát song song theo CPU budget.

## 8. Checklist hiện trường

- [ ] Có JDK build, CPU quota/effective cores, tải phát sinh và khoảng thời gian lỗi.
- [ ] Có request/s, in-flight, p50/p95/p99, error/timeout và process CPU/GC.
- [ ] Có số đo thời gian đợi pool/permit, thời gian giữ connection và latency/error downstream.
- [ ] Có dump chứa virtual thread và JFR CPU samples/pinning tương thích với JDK.
- [ ] Đã phân biệt **ready chờ carrier**, **unmounted chờ tài nguyên**, **mounted tiêu thụ CPU**.
- [ ] Đã xác nhận giả thuyết bằng thay đổi một giới hạn với cùng điều kiện tải, quan sát p99 và lỗi.
- [ ] Đã kiểm tra điểm nghẽn thứ hai sau khi xử lý điểm nghẽn đầu tiên.

### Tài liệu tham khảo chính thức

- Oracle Java 21 — Virtual Threads: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- OpenJDK JEP 444 — Virtual Threads: https://openjdk.org/jeps/444
- OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning: https://openjdk.org/jeps/491
- JDK 24 `VirtualThreadSchedulerMXBean`: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.management/jdk/management/VirtualThreadSchedulerMXBean.html

**Nguyên tắc kết luận:** xác định vị trí chờ, giới hạn thực và phép thử xác nhận; số virtual thread lớn hoặc latency cao chỉ là triệu chứng, không phải tên nguyên nhân.