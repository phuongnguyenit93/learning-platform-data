# Đánh giá chi phí trang trí với số lượng tác vụ rất nhỏ

## 1. Mục tiêu và cách hiểu đúng bài toán

Trong Spring Framework, `TaskDecorator` cho phép bọc một callback `Runnable` trước khi executor chạy nó. Cơ chế này thường được dùng để truyền ngữ cảnh từ thread nộp việc sang worker (correlation ID/MDC, observation/tracing context), đo thời gian hoặc dọn `ThreadLocal` sau khi task hoàn tất.

Với một tác vụ xử lý HTTP/JDBC mất hàng trăm mili-giây, chi phí tạo wrapper và chụp/khôi phục context có thể nhỏ so với thời gian I/O. Nhưng với nhiều tác vụ chỉ làm vài phép tính hoặc đọc một biến, thời gian lập lịch và trang trí có thể chiếm phần đáng kể của toàn bộ thời gian. Javadoc của Spring cho `ContextPropagatingTaskDecorator` cũng cảnh báo thao tác này có overhead, **không khuyến nghị khi ứng dụng chạy rất nhiều tác vụ cực nhỏ**.

Cụm “số lượng tác vụ rất nhỏ” còn nêu một vấn đề đo lường: nếu chỉ chạy **vài task** (ví dụ 5 hoặc 20), kết quả stopwatch sẽ bị chi phối bởi khởi tạo thread, JIT warm-up, GC và nhiễu hệ điều hành. Vì vậy cần tách **hai trường hợp**:

1. **Mỗi task rất ngắn** (*tiny task*), nhưng tổng số task có thể lớn: cần xem chi phí decorator được lặp lại bao nhiêu lần và tỉ trọng overhead.
2. **Tổng số task rất ít** (*small sample count*): chi phí tuyệt đối có thể không quan trọng, trong khi benchmark lại thiếu đủ mẫu để kết luận hơn/kém vài phần trăm.

Bài này trình bày cách phân loại chi phí, giữ đúng semantics context, tạo một chương trình Java 17 để quan sát và đo sơ bộ, cách dùng JMH khi cần số liệu tin cậy hơn, rồi đưa ra tiêu chí cấu hình Spring theo workload thật.

**Nguyên tắc:** không kết luận “TaskDecorator chậm” hay “overhead = X ns” nếu chưa biết task, context, JVM, executor, số mẫu, warm-up và phương pháp đo. Không có con số nano-giây cố định áp dụng cho mọi môi trường.

## 2. TaskDecorator thực thi ở đâu và phát sinh chi phí ở bước nào?

Một `TaskDecorator` của Spring có hợp đồng cơ bản:

```java
@FunctionalInterface
public interface TaskDecorator {
    Runnable decorate(Runnable runnable);
}
```

Đây là chữ ký API minh họa, không phải một source file độc lập. Spring có thể trao cho decorator callback thực thi đã được framework bọc sẵn, không nhất thiết chính `Runnable`/`Callable` người dùng truyền vào.

Ví dụ manual context propagation:

```java
TaskDecorator decorator = task -> {
    String capturedTrace = TRACE_ID.get();  // snapshot trên thread submit

    return () -> {
        String previous = TRACE_ID.get();   // context sẵn có của worker
        try {
            if (capturedTrace == null) {
                TRACE_ID.remove();
            } else {
                TRACE_ID.set(capturedTrace);
            }
            task.run();
        } finally {
            if (previous == null) {
                TRACE_ID.remove();
            } else {
                TRACE_ID.set(previous);
            }
        }
    };
};
```

Đây là snippet tích hợp với biến `TRACE_ID` kiểu `ThreadLocal<String>` được khai báo ở class ứng dụng; nó chưa phải chương trình chạy độc lập. Với một task, có thể xảy ra:

```text
THREAD NỘP VIỆC                      WORKER THREAD
────────────────────────────────────────────────────────────────
đọc TRACE_ID
tạo wrapper / capturedTrace
nộp vào executor
                 ---- queue / dispatch ---->
                                     đọc context cũ
                                     set context mới
                                     task.run()
                                     restore/remove context trong finally
                                     wrapper trả về
```

**Những chi phí khác nhau cần tách:**

| Công đoạn | Loại chi phí có thể phát sinh | Vị trí |
| --- | --- | --- |
| Chụp context khi nộp task | `ThreadLocal.get`, snapshot, sao chép map, cấp phát | Submitter |
| Tạo wrapper | Lambda/đối tượng giữ `Runnable` và context | Thường ở thời điểm decorate/submit |
| Đưa task vào executor | Kiểm tra pool/queue, lock/CAS, contention | Submitter và executor |
| Chuyển thread | Scheduler, context switch, cache locality | JVM/OS |
| Khôi phục context | `ThreadLocal.get/set/remove`, scope allocation | Worker |
| Chạy nghiệp vụ | CPU, I/O, lock, DB, HTTP | Worker |
| Dọn context | `finally` restore/remove, resource cleanup | Worker |
| Monitoring trong decorator | Timer, histogram, log tags, MDC | Worker/caller |
| GC | Bộ nhớ cấp phát từ wrapper/context snapshot | JVM |

Không phải tất cả khoản trên đều do decorator gây ra. **Executor scheduling và task queue tồn tại kể cả không dùng decorator**. Một phép benchmark phải phân biệt tổng chi phí async với **chi phí tăng thêm** khi bật decorator.

### Không nhầm TaskDecorator với logic gọi API

Decorating chỉ bọc callback để chạy thêm mã. Nó không tự làm cho `@Async` song song hơn, không tăng kích thước pool, không bảo đảm DB connection và cũng không biến task thành có thể hủy. Với `@Async`, lời gọi phải đi qua Spring-managed proxy; self-invocation `this.method()` có thể bỏ qua async interceptor, khiến bài test không còn đo executor dự định.

## 3. Mô hình chi phí: tuyệt đối và tương đối

Với một batch gồm N task, có thể viết mô hình tư duy:

```text
T_batch ≈ T_setup
        + T_submission_and_queue
        + T_worker_execution
        + T_context_capture_and_restore
        + T_metrics/logging
        + T_scheduler_and_GC
        + interaction/contension effects
```

Đây là **mô hình định tính**, không phải công thức đo từng thành phần cộng tuyến tính: các bước có thể chồng lấp giữa thread và chịu contention. Để so sánh một workload:

```text
ΔT_batch = T_batch(decorated) - T_batch(plain)

Tương đối (%) = ΔT_batch / T_batch(plain) × 100%
```

Cần cẩn thận khi dùng công thức trên:

- Nếu task rất ngắn, phần `T_context_capture_and_restore` lặp lại với mỗi task; tỉ trọng tương đối có thể tăng đáng kể.
- Nếu task chờ DB 200 ms, overhead của decorator có thể nhỏ xét theo latency, **nhưng** vẫn tiêu tốn CPU/allocations nếu số request mỗi giây rất lớn.
- Với **N=5**, sai khác một lần tạo thread hoặc JIT compilation có thể lớn hơn toàn bộ chi phí decorator. Tính ra “tăng 80%” từ một phép đo ngắn không chứng minh decorator làm chậm ổn định 80%.
- Nếu decorator ghi log đồng bộ cho từng task, chi phí có thể chủ yếu từ formatting/I/O của logger chứ không phải bản thân `ThreadLocal.set`. Đừng so một nhánh bật log với nhánh không log rồi chỉ đổ lỗi cho context propagation.
- Nếu task ngắn và queue đang bão hòa, queue waiting có thể lớn hơn nhiều execution time. Cần tách thời gian **chờ**, **được chạy**, và **toàn bộ từ submit tới complete**.

Ví dụ giả định để minh họa, **không phải số đo của Java/Spring**: một task chạy 5 µs, thêm 1 µs overhead thì tỉ trọng tăng khoảng 20%; một task chạy 50 ms thêm đúng 1 µs chỉ tăng khoảng 0,002%. Đây là phép tính minh họa cho ý tưởng “overhead cố định chiếm tỉ trọng lớn khi task ngắn”, **không** khẳng định chi phí thực tế luôn là 1 µs.

### Vì sao throughput và latency phải đo cùng nhau?

Decorator có thể gây thêm cấp phát trên **thread submit** nhưng kết quả cuối lại biểu hiện ở **GC pause**, hoặc làm tăng CPU worker khiến queue chờ dài ra. Đo một task đơn lẻ không đủ để biết hệ thống có bị giảm throughput ở tải cao hay không. Mặt khác, một throughput benchmark đạt mức cao không chứng minh latency p99 của các request quan trọng vẫn tốt.

## 4. Điều kiện đo công bằng trước khi viết benchmark

Để so sánh “không decorator”, “wrapper rất nhẹ” và “copy/restore context”, hãy đảm bảo cùng:

1. **Loại executor**: dùng một cấu hình thread pool cố định; không so `SimpleAsyncTaskExecutor` tạo thread mới với `ThreadPoolTaskExecutor` tái sử dụng thread rồi quy toàn bộ chênh lệch cho decorator.
2. **Độ dài task**: cùng loại công việc và side effect kiểm chứng được; tránh nhánh được JIT tối ưu bỏ hoàn toàn.
3. **Warm-up**: cho JIT và class loading xảy ra trước phần ghi nhận chính thức, hoặc dùng JMH.
4. **JVM/host**: cùng bản JDK, heap flags, cấu hình logging/tracing, CPU limit và mức tải nền.
5. **Số mẫu**: đo nhiều vòng, đổi thứ tự các mode để bớt thiên lệch do cache/JIT/CPU frequency.
6. **Điểm đo**: định nghĩa rõ đo từ lúc bắt đầu submit tới khi tất cả task hoàn tất, hay riêng thời gian decor/mỗi `run()`.
7. **Khả năng quan sát**: kiểm tra mọi task thực sự hoàn tất; dùng `CountDownLatch`/Future và timeout, không dùng `Thread.sleep(...)` đoán.
8. **Không mất task**: một queue đầy có thể reject task; nếu vô tình bỏ qua lỗi, mode “nhanh nhất” có thể chỉ là mode chạy thiếu công việc.
9. **Không đổi nghĩa**: khi tắt context propagation, task cần context có thể lỗi hoặc dùng nhầm context. Chỉ bỏ decorator nếu nghiệp vụ/trace vẫn đúng.
10. **Quản trị cấp phát**: nhớ rằng wrapper và snapshot có thể tạo object trên mỗi task; đếm allocations/GC nếu throughput cao.

**Tiêu chí giá trị của phép đo:** khác biệt phải lớn hơn mức nhiễu tự nhiên, lặp lại qua nhiều vòng/host và có giải thích về resource usage. Nếu không, kết luận đúng thường là **“chưa có bằng chứng chi phí đáng kể trong điều kiện đã đo”**, không phải “overhead bằng không”.

## 5. Ví dụ Java 17 độc lập: kiểm tra context đúng trước khi đo hiệu năng

Trước khi so sánh tốc độ, phải đảm bảo decorator **giữ đúng semantics**. Code dưới đây là một chương trình độc lập dùng JDK 17, không cần Maven hay Spring. Nó tạo ba mode:

- `PLAIN`: nộp `Runnable` gốc.
- `WRAPPED`: thêm đúng một wrapper gọi `original.run()`, không truyền context.
- `CONTEXT`: snapshot một `ThreadLocal<String>` trên submitter; set/restore trên worker.

**Lưu ý về mô hình:** đây là *analog* của TaskDecorator bằng JDK thuần. Nó không đo trực tiếp chi phí implementation `ContextPropagatingTaskDecorator` của Spring, Micrometer Context Propagation hay MDC thật. Mục tiêu là có một baseline minh bạch, lặp lại được.

Tạo tệp **`TinyTaskDecorationDemo.java`**:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class TinyTaskDecorationDemo {
    private static final ThreadLocal<String> TRACE = new ThreadLocal<>();

    enum Mode { PLAIN, WRAPPED, CONTEXT }

    private static void setTrace(String value) {
        if (value == null) {
            TRACE.remove();
        } else {
            TRACE.set(value);
        }
    }

    private static Runnable decorate(Runnable original, Mode mode) {
        return switch (mode) {
            case PLAIN -> original;
            case WRAPPED -> () -> original.run();
            case CONTEXT -> {
                String captured = TRACE.get(); // snapshot on submitter
                yield () -> {
                    String previous = TRACE.get(); // worker context
                    try {
                        setTrace(captured);
                        original.run();
                    } finally {
                        setTrace(previous); // no leak across reused workers
                    }
                };
            }
        };
    }

    private static void verifyContext() throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            setTrace("request-173");

            CompletableFuture<String> observed = new CompletableFuture<>();
            worker.execute(decorate(
                    () -> observed.complete(TRACE.get()), Mode.CONTEXT));

            // Chỉ đọc khi job thứ nhất đã hoàn thành giá trị.
            String value = observed.get(5, TimeUnit.SECONDS);

            CompletableFuture<Boolean> leaked = new CompletableFuture<>();
            worker.execute(() -> leaked.complete(TRACE.get() != null));

            // Single-thread executor đảm bảo job kiểm tra chạy sau
            // khi wrapper trước đó trả quyền về worker.
            System.out.println("workerTrace=" + value);
            System.out.println(
                    "contextLeaked=" + leaked.get(5, TimeUnit.SECONDS));
        } finally {
            setTrace(null);
            worker.shutdownNow();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not terminate");
            }
        }
    }

    private static long runBatch(Mode mode, int taskCount)
            throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch done = new CountDownLatch(taskCount);
        LongAdder completed = new LongAdder();
        setTrace("request-173");

        try {
            long start = System.nanoTime();

            for (int i = 0; i < taskCount; i++) {
                Runnable work = completed::increment;
                Runnable decorated = decorate(work, mode);
                pool.execute(() -> {
                    try {
                        decorated.run();
                    } finally {
                        // Báo hoàn tất sau khi decorator đã restore context.
                        done.countDown();
                    }
                });
            }

            if (!done.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Batch timed out: " + mode);
            }
            long elapsed = System.nanoTime() - start;

            if (completed.sum() != taskCount) {
                throw new IllegalStateException(
                        "Missing tasks: " + mode + "/" + taskCount);
            }
            return elapsed;
        } finally {
            setTrace(null);
            pool.shutdownNow();
            if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not terminate");
            }
        }
    }

    private static double medianMillis(long[] durations) {
        long[] copy = durations.clone();
        Arrays.sort(copy);
        return copy[copy.length / 2] / 1_000_000.0;
    }

    public static void main(String[] args) throws Exception {
        verifyContext();

        // 20 task: minh họa ít mẫu; 30.000 task: nhiều task ngắn.
        for (int n : new int[] { 20, 30_000 }) {
            long[][] measurements = new long[Mode.values().length][5];

            // Hai vòng warm-up + năm vòng đo; xoay thứ tự mode.
            for (int round = 0; round < 7; round++) {
                for (int offset = 0; offset < Mode.values().length; offset++) {
                    Mode mode = Mode.values()[
                            (round + offset) % Mode.values().length];
                    long elapsed = runBatch(mode, n);
                    if (round >= 2) {
                        measurements[mode.ordinal()][round - 2] = elapsed;
                    }
                }
            }

            System.out.println("taskCount=" + n);
            for (Mode mode : Mode.values()) {
                System.out.printf(Locale.ROOT,
                        "%s medianBatchMs=%.3f%n", mode,
                        medianMillis(measurements[mode.ordinal()]));
            }
        }

        System.out.println("allBatchesVerified=true");
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac --release 17 TinyTaskDecorationDemo.java
java TinyTaskDecorationDemo
```

**Các dòng output có thể dự đoán chính xác:**

```text
workerTrace=request-173
contextLeaked=false
taskCount=20
PLAIN medianBatchMs=...
WRAPPED medianBatchMs=...
CONTEXT medianBatchMs=...
taskCount=30000
PLAIN medianBatchMs=...
WRAPPED medianBatchMs=...
CONTEXT medianBatchMs=...
allBatchesVerified=true
```

Dấu `...` trong output trên **là ký hiệu mô tả giá trị thay đổi theo máy**, không phải stdout cố định để copy vào test. Mã thực tế sẽ in các số mili-giây, ví dụ theo format `%.3f`. **Không đưa ra số thời gian bịa đặt**; kết quả đúng phải lấy từ máy chạy, nhiều lượt đo và phân tích nhiễu.

### Vì sao bài demo có ý nghĩa?

- `verifyContext()` kiểm tra context ở worker thật bằng một pool 1 thread. Nó cũng kiểm tra worker không giữ `TRACE` sau khi decorator chạy xong.
- `PLAIN` là baseline không wrapper; `WRAPPED` cô lập ý tưởng “thêm một lớp `Runnable`”; `CONTEXT` cộng thêm `ThreadLocal.get/set/remove` và snapshot.
- `CountDownLatch` nằm **bên ngoài decorator** và chỉ đếm sau khi `decorated.run()` đã hoàn tất, nhờ đó phép đo bao gồm cả bước restore trong `finally`. Mọi mode đều dùng cùng một lớp wrapper báo hoàn tất để so sánh công bằng; `LongAdder` xác nhận số task đã chạy.
- `shutdownNow/awaitTermination` dọn pool sau mỗi batch; nếu task không chịu dừng hoặc môi trường quá tải, chương trình báo lỗi thay vì âm thầm bỏ thiếu công việc.
- Thử N=20 và N=30.000 để thấy nguy cơ suy luận từ ít mẫu. Dù N=30.000 lớn hơn, đây vẫn **không phải benchmark nanosecond chuyên nghiệp**.
- Xoay thứ tự chạy giúp giảm một phần thiên lệch do JIT, nhiệt độ CPU và cache; không thay thế thống kê/đo đạc chuyên nghiệp.
- Chu trình work cực ngắn nhằm nhấn mạnh overhead của scheduling và wrapper; workload I/O thật sẽ có kết quả khác.

### Điều demo chưa thể tách hoàn toàn

`runBatch` dùng một pool mới mỗi lượt nên thời gian còn bao gồm khởi tạo thread, đi qua queue, chờ scheduler, `LongAdder`/`CountDownLatch` và cấp phát từ mỗi `Runnable`. Chênh lệch giữa mode **không phải “số nanosecond riêng của decorator”**. Hơn nữa, worker có thể thực thi song song lúc main đang submit, nên tổng thời gian batch không bằng tổng thời gian của N task. Muốn đo chính xác mỗi operation, dùng JMH hoặc profiling sau khi xác định câu hỏi đo.

## 6. Cách diễn giải kết quả: tránh biến phép đo nhiễu thành quyết định kiến trúc

Đừng mặc định `CONTEXT` luôn chậm nhất trong mọi lần chạy. Nhiễu thread scheduling, JIT, GC, CPU throttling hoặc máy đang chạy ứng dụng khác có thể tạo kết quả không theo thứ tự dự đoán.

| Quan sát | Giải thích khả dĩ | Hành động kiểm chứng |
| --- | --- | --- |
| N=20 chênh vài mili-giây giữa mode | Phần lớn có thể do startup/scheduling/GC | Lặp nhiều batch, xem phân phối, không kết luận từ một lần |
| N lớn, CONTEXT chậm ổn định | Snapshot/restore/allocations có thể đáng kể | Profile allocation/CPU, thay workload task, kiểm JMH |
| WRAPPED xấp xỉ PLAIN | Wrapper đơn giản có thể đã được JIT tối ưu tốt | Không suy rộng sang MDC/Micrometer snapshot |
| Decorator bật làm p99 latency cao | Có thể do GC, contention, logging hoặc queue delay | Xem JFR, GC log, queue depth, worker busy |
| Throughput giảm nhưng average latency ít đổi | Bottleneck ở submitter hoặc tài nguyên xử lý | Đo CPU, submission time, saturation theo instance |
| Truyền context đúng ở test nhỏ, lỗi ở production | Có thể thiếu capture ở một đường submit hoặc cleanup | Test với async callback, cancellation, exception và nhiều thread |
| Tắt decorator tăng tốc nhưng mất trace | Thay đổi semantics vận hành | Giữ context tối thiểu hoặc dùng cơ chế tích hợp khác |

**Cách báo cáo kết quả có trách nhiệm:** ghi phiên bản JDK/Spring, CPU/vCPU, số worker, queue policy, N, số vòng, warm-up, GC, logging state; đưa median và p95 nếu có đủ số mẫu. Trình bày chênh lệch tuyệt đối **và** tương đối, cùng phạm vi sai số. Nếu khác biệt nhỏ hơn độ dao động giữa các lượt, viết “chưa xác nhận chênh lệch”.

Không dùng một lần benchmark như bằng chứng rằng ứng dụng sẽ nhanh hơn khi tắt correlation ID; mất khả năng truy vết có thể tạo chi phí vận hành lớn hơn phần tiết kiệm CPU.

## 7. Khi cần đo micro-overhead thật: JMH thay vì stopwatch thô

Java Microbenchmark Harness (**JMH**) của OpenJDK thiết kế để giảm sai lệch do JIT compilation, dead-code elimination, constant folding, warm-up, forking và cách đo sai. Nó phù hợp hơn khi cần so sánh overhead nhỏ của hai cách implement decorator.

Một thiết kế benchmark nên tách **ít nhất hai câu hỏi**:

### 7.1. Chi phí tạo wrapper/capture ở submitter

Đo chi phí chạy `decorate(original)`: capture context và tạo wrapper. Mục tiêu là phát hiện số allocation/task và thời gian chuẩn bị. Cần đảm bảo kết quả wrapper không bị tối ưu loại bỏ; trong JMH dùng `Blackhole.consume(wrapper)` hoặc chiến lược tương đương.

### 7.2. Chi phí chạy wrapper trên worker

Tạo wrapper trước hoặc thiết kế state để tách allocation khỏi execution; đo `wrapper.run()` có set/restore context và task logic cực ngắn. Cần đảm bảo mã nghiệp vụ không bị JIT tối ưu hết.

### 7.3. Chi phí end-to-end của Spring executor

JMH đơn luồng không thay thế việc đo **submit → queue → worker → completion** ở Spring. Với async dispatch có blocking, cần xem thread contention, queue, thực thi song song, pool saturation và timeout. Kết quả “10 ns/op” của một wrapper trong JMH không thể cộng thẳng vào p99 latency mà bỏ qua queue và CPU contention.

Để làm JMH đúng:

- Dùng fork JVM riêng, warm-up iterations và measurement iterations; không chỉ gọi method vài lần trong `main`.
- Cấu hình *state scope* (per-thread hoặc shared) đúng mục đích; lưu ý nếu dùng chung `ThreadLocal` hay counter có contention.
- Tránh loop tự viết quanh benchmark method nếu JMH đã đo operation. Có thể dùng `Blackhole` để giữ side effect quan sát được.
- Kiểm tra allocation bằng profiler hỗ trợ như JFR hoặc JMH GC profiler. Chạy dưới cùng Java version và cùng cấu hình host.
- Đổi task size: no-op/tiny CPU, một số thao tác thật, và task I/O được mock đúng độ trễ; không chỉ test mỗi no-op.
- Đo riêng “số tác vụ cực nhỏ” và “rất nhiều tác vụ nhỏ”; số lượng ít dễ làm overhead setup nổi bật nhưng thiếu ý nghĩa thống kê.
- Khi đo MDC/Micrometer, đăng ký đúng accessor và tạo context có kích thước tương đương production. Một context rỗng không phản ánh chi phí copy map có nhiều entry.

Tham khảo [OpenJDK JMH](https://github.com/openjdk/jmh) để tạo dự án benchmark. Không cần “bịa” con số JMH khi chưa thực sự chạy trong môi trường mục tiêu.

## 8. Cấu hình TaskDecorator trong Spring ThreadPoolTaskExecutor

Bên dưới là **class cấu hình tích hợp** vào Spring Framework 6.2 hoặc Spring Boot dùng `ThreadPoolTaskExecutor`. Nó minh họa cách chụp một correlation ID bằng `ThreadLocal` và khôi phục sau khi task hoàn tất.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class TinyTaskExecutorConfiguration {
    public static final ThreadLocal<String> CORRELATION_ID =
            new ThreadLocal<>();

    @Bean("contextAwareExecutor")
    public ThreadPoolTaskExecutor contextAwareExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("tiny-work-");

        executor.setTaskDecorator(task -> {
            String captured = CORRELATION_ID.get();

            return () -> {
                String previous = CORRELATION_ID.get();
                try {
                    if (captured == null) {
                        CORRELATION_ID.remove();
                    } else {
                        CORRELATION_ID.set(captured);
                    }
                    task.run();
                } finally {
                    if (previous == null) {
                        CORRELATION_ID.remove();
                    } else {
                        CORRELATION_ID.set(previous);
                    }
                }
            };
        });

        return executor;
    }
}
```

Đây là mã cấu hình **không chạy độc lập** nếu chỉ có JDK: cần dependency `spring-context` và application context. `ThreadLocal` static trong ví dụ phục vụ minh họa; hệ thống thật nên dùng cơ chế context có owner, lifecycle và chính sách dữ liệu rõ ràng, tránh phát tán context nhạy cảm ra ngoài đường xử lý cần thiết.

**Điểm quan trọng:**

- Chụp `CORRELATION_ID.get()` ở nơi decorate để có snapshot của submitter; set ở worker trước `task.run()` và restore trong `finally`.
- Việc capture/restore được thực hiện **mỗi task**; với rất nhiều task ngắn, chi phí cộng dồn có thể trở thành đáng kể.
- Dù `CORRELATION_ID` bằng `null`, ví dụ vẫn thêm wrapper và thực hiện get/remove; nếu hầu hết task không cần context, cân nhắc một chiến lược chọn lọc đã kiểm chứng semantics.
- `queueCapacity=64` và 4 worker chỉ là thông số minh họa; không phải khuyến nghị cho mọi dự án. Thực nghiệm thay đổi một biến mỗi lần và kiểm tra rejection.
- Nếu task bị reject khi submit, callback chưa được chạy; không dùng decorator như nơi bắt `TaskRejectedException` ở submitter.
- Nếu task được bọc bằng `FutureTask`, exception nghiệp vụ có thể nằm ở `Future.get()`, không đi qua `catch` trong decorator; quan sát lỗi phải thiết kế riêng.

### Bật ContextPropagatingTaskDecorator

Khi cần logging/observation context với Micrometer Context Propagation (Spring Framework 6.1+), có thể dùng:

```java
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

// Trong cấu hình bean executor đã tạo:
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
```

Snippet trên cần dependency **`io.micrometer:context-propagation`**, cấu hình `ThreadLocalAccessor`/context registry phù hợp và module Spring được hỗ trợ. Không mặc định nó tự sao chép mọi `ThreadLocal` hoặc thông tin bảo mật; việc truyền gì phụ thuộc các accessor đã đăng ký.

Spring Javadoc nêu trực tiếp: decorator này có **overhead** và không khuyến nghị cho ứng dụng xử lý rất nhiều tác vụ cực nhỏ. Lý do là snapshot/restore context được thực hiện lặp đi lặp lại, có thể tạo scope/đối tượng bổ sung. Nếu chỉ cần một correlation ID và đã có cách truyền rõ ràng bằng tham số, dùng toàn bộ context snapshot machinery có thể không đáng với chi phí — nhưng phải cân nhắc requirement tracing/observation.

### CompositeTaskDecorator và lớp bọc chồng nhau

Nếu dùng nhiều decorator (MDC, observation, custom timer, security context), mỗi lớp có thể làm thêm công việc và tạo wrapper. Không cộng các ước lượng overhead của từng decorator một cách máy móc: chúng có thể chia sẻ context hoặc tạo nested restoration. Hãy đo **tổng cấu hình thật**, kiểm tra thứ tự áp dụng, exception/cleanup và tránh copy trùng cùng một context.

## 9. Có thể tối ưu ở đâu nếu tác vụ quá nhỏ?

### 9.1. Gộp công việc thành batch phù hợp

Giả sử có 10.000 task, mỗi task chỉ cập nhật một giá trị rất nhỏ. Nếu mỗi task đều qua submit/queue/decorator, chi phí per-task lặp lại 10.000 lần. Gộp 100 thao tác thành một task có thể giảm số lần decorate/submit từ 10.000 xuống 100.

Nhưng batching không miễn phí:

- Task lớn hơn có thể tăng latency của từng phần việc, làm mất fairness.
- Cần giới hạn kích thước/thời gian batch, memory footprint và cơ chế retry.
- Một phần việc lỗi có thể khiến phải xử lý lại cả batch; phải có idempotency hoặc checkpoint.
- Với per-request context khác nhau, không được gộp nhiều tenant/user context rồi vô ý dùng một context chung.
- Tránh giữ lock/DB transaction quá dài khi gộp.

### 9.2. Truyền context tối thiểu

Chỉ chụp những giá trị cần thiết. Nếu task cần một correlation ID, truyền ID như tham số của command/DTO có thể rõ ràng hơn snapshot cả MDC map hoặc nhiều ThreadLocal accessors. Tuy nhiên, có những thư viện logging/trace cần context trong ThreadLocal; bỏ propagation khi nó là requirement nghiệp vụ/quan sát là sai. Tối ưu sau khi có baseline.

### 9.3. Tách loại executor theo yêu cầu

Một executor cho các task có tracing đầy đủ và một executor cho các phép tính rất ngắn không cần context có thể giảm overhead; nhưng phải kiểm tra rằng không có đường nào bypass context cần thiết. Không thiết kế việc tách này chỉ để đạt một điểm benchmark đẹp nếu nó tạo thêm concurrency và queue management phức tạp.

### 9.4. Tránh log từng task ở mức đồng bộ

Ghi log INFO cho từng task có thể tốn nhiều CPU/I/O hơn chính task cực nhỏ. Ưu tiên aggregate metrics hoặc sampling có kiểm soát; chú ý tag cardinality và dữ liệu nhạy cảm. Đừng bỏ log lỗi quan trọng hoặc tracing bắt buộc chỉ vì thử nghiệm cho thấy throughput tăng.

### 9.5. Chọn cách thực thi phù hợp

Không phải mọi thao tác 1–2 µs đều đáng được gửi qua executor. Nếu phép toán rất rẻ, không blocking và đang ở thread phù hợp, chạy trực tiếp có thể đơn giản hơn. Nhưng không đưa blocking I/O vào event-loop hoặc request thread chỉ để tránh decorator. Quyết định phải dựa trên latency, isolation, response behavior và công suất downstream.

## 10. Cẩn thận với virtual threads, pool và Spring @Async

Java 21+ có virtual threads, nhưng **Java 17 không có virtual threads**. Spring 6.1+ có hỗ trợ `SimpleAsyncTaskExecutor.setVirtualThreads(true)` trên JDK 21+. So sánh platform-thread pool với virtual-thread executor có thể làm thay đổi chi phí tạo thread, queue, context lookup và scheduling. Đó là **hai kiến trúc thực thi khác nhau**, không phải benchmark sạch để chỉ ra overhead của TaskDecorator.

Với `@Async`, đường đi thông thường là:

```text
Caller
  |
  v
Spring proxy (phải đi qua proxy để kích hoạt @Async)
  |
  v
Executor submit
  |
  +--> decorate actual callback
  |
  +--> queue / worker or virtual thread
            |
            v
        decorator wrapper
            |
            +--> set context
            +--> original callback.run()
            +--> restore context
```

Để đo thực tế, xác định executor bean cụ thể bằng `@Async("contextAwareExecutor")`, tên thread, active count và config. Không dùng một ứng dụng tự gọi `this.asyncMethod()` rồi suy luận decorator không có overhead: self-call thường không đi qua proxy nên không hề submit task theo cách dự định.

Chú ý: nếu task trả `CompletableFuture` hoặc có callback bên trong, decorator bao phủ **execution callback được nộp tới executor đó**, không tự bao trùm toàn bộ chuỗi asynchronous stages chạy trên executor khác hoặc common pool. Nếu chuỗi reactive/CompletionStage cần context tại nhiều ranh giới, phải thiết kế propagation ở từng ranh giới phù hợp.

## 11. Kiểm thử tính đúng đắn khi giảm overhead

Trước khi “tối ưu”, tạo các test:

| Test | Trường hợp | Điều cần kiểm chứng |
| --- | --- | --- |
| A | Context có giá trị khi submit | Worker thấy ID đúng |
| B | Submitter không có context | Worker không dùng context cũ còn sót |
| C | Nhiều request trên cùng worker | ID của request trước không rò sang request sau |
| D | Task ném RuntimeException | `finally` restore/remove vẫn chạy |
| E | Task bị hủy hoặc bị reject | Không kết luận task đã chạy; cleanup đúng tại nơi thực thi |
| F | `@Async` từ bean khác | Gọi thực sự đi qua proxy và executor có decorator |
| G | `CompletableFuture` stages | Context tại mỗi stage được xác định, không tự assume propagation |
| H | Task chậm hoặc lock contention | Decorator không giữ lock/ThreadLocal ngoài scope quá lâu |
| I | Bật logging/tracing thật | Correlation/observation vẫn đầy đủ sau tối ưu |
| J | N=20, N=30.000, task CPU/I/O khác nhau | Kết luận hiệu năng không dựa một trường hợp duy nhất |

Dùng `CountDownLatch` để đồng bộ thời điểm task bắt đầu/kết thúc và kiểm tra biến đếm hoàn tất. Test phải có timeout để không treo. Chỉ đo latency sau khi đã xác minh không mất task và không sai ngữ cảnh.

**Một lỗi nguy hiểm:** bật/tắt decorator tùy cờ context nhưng không có contract rõ; những tác vụ phát sinh từ thread background/HTTP khác nhau có thể bị mất trace hoặc kế thừa context nhầm. Thay đổi cấu hình nên được rollout có metric và kiểm thử regressions.

## 12. Đo production: phân biệt chi phí context với bottleneck khác

Các metric nên ghi nhận ở môi trường thật:

- **Throughput**: tasks/second, số task được chấp nhận/hoàn tất/rejected.
- **Queue**: độ sâu và thời gian chờ; đừng quy queue wait vào TaskDecorator.
- **Worker**: active thread count, pool size, CPU utilization, contention.
- **Latency**: p50/p95/p99 từ submit tới hoàn tất, và riêng thời gian callback.
- **GC/allocation**: allocations per task, GC pause, heap pressure.
- **Context correctness**: số request thiếu correlation ID, trace/span bị đứt, leakage giữa request.
- **Downstream**: JDBC connection pending, HTTP connection pool, 429/503 và retry.
- **Log/observation**: chi phí synchronous formatting/export và cardinality của metric tags.

Dùng JFR/async-profiler/JMH theo mức đo phù hợp. Trong Spring Boot, Micrometer/Actuator có thể cung cấp executor metrics khi binding/configuration đúng; tên metric cụ thể phụ thuộc phiên bản và registry, không mặc định mọi executor tự được instrument đầy đủ.

Một thử nghiệm production an toàn có thể so **hai nhóm traffic tương đương** với bật/tắt một tối ưu đã chứng minh giữ đúng semantics, theo dõi cả error rate/tracing completeness. Không giảm tracing của giao dịch tài chính/nhạy cảm chỉ để lấy benchmark tốt hơn mà chưa xem xét audit/security requirement.

## 13. Sai lầm thường gặp

**“Decorate chỉ tạo một lambda, overhead chắc chắn bằng không.”** Lambda có thể được tối ưu trong một vài bối cảnh, nhưng snapshot/restore, cấp phát wrapper, context accessor, MDC và metric còn chi phí thật. Đo workload.

**“Có 5 task thì mỗi task chậm 30%.”** Chưa chắc; 5 mẫu dễ bị nhiễu. Báo cáo time tuyệt đối và độ phân tán, thử nhiều vòng rồi mới kết luận.

**“Có 50.000 task nên TaskDecorator chắc chắn là bottleneck.”** Không mặc định; có thể bottleneck tại queue, LongAdder/lock, CPU, DB hoặc logging. Profile.

**“Tắt decorator để tăng tốc thì không ảnh hưởng tính đúng.”** Sai nếu business/logging/observability dựa trên context. Test về correlation ID, cleanup và security context trước.

**“ThreadLocal tự truyền sang thread pool.”** Không đúng; `ThreadLocal` thường là per-thread. Worker thread tái sử dụng có thể giữ giá trị cũ nếu không cleanup. `InheritableThreadLocal` cũng không phải giải pháp đáng tin cậy cho pooled workers.

**“ContextPropagatingTaskDecorator copy tất cả mọi thứ.”** Nó truyền các context được đăng ký và hỗ trợ bởi Micrometer accessors; không tự động truyền mọi đối tượng hoặc bảo đảm transaction/secret isolation.

**“Phép đo nanoTime 1 lần là JMH.”** Không. NanoTime hữu ích để đo elapsed trong một chương trình, nhưng benchmark micro-level cần warm-up/fork/statistics và tránh tối ưu hóa không chủ đích.

**“Dùng Thread.sleep(1) mô phỏng tiny task.”** `sleep` khiến task thuộc nhóm waiting/blocked, không phản ánh phép toán CPU ngắn; kết quả chủ yếu từ timer granularity và scheduling.

**“Bỏ decorator rồi vẫn thấy MDC ở worker, nghĩa là propagation ổn.”** Có thể worker đang **rò context cũ**. Test bằng request khác và kiểm tra `ThreadLocal.get()==null` sau cleanup.

**“@Async method đã được gọi nên decorator luôn chạy.”** Self-invocation, dùng sai executor bean, submit trực tiếp vào executor khác hoặc chạy `CompletableFuture.supplyAsync` trên common pool đều có thể bypass decorator đang đo.

**“Decorator catch được tất cả exception nên metrics lỗi luôn chính xác.”** Với Future-backed callback, lỗi có thể nằm trong Future và không thoát khỏi `Runnable.run()`. Quan sát lỗi ở Future/caller hoặc handler chuyên biệt; không đếm sai rồi dùng metric ấy để quyết định performance.

## 14. Quy trình quyết định và tài liệu tham khảo

Một quy trình ngắn, có bằng chứng:

1. **Xác định workload:** ít task thực sự hay rất nhiều task cực nhỏ? Workload là CPU, blocking I/O hay mixed?
2. **Xác định yêu cầu context:** cần MDC/tracing/security/transaction? Cái gì phải được truyền, cái gì tuyệt đối không được copy?
3. **Kiểm chứng correctness:** context đúng ở worker và không rò sau task, kể cả lỗi/cancel/rejection.
4. **Đo baseline:** executor và cấu hình thật không decorator; xác nhận task được hoàn tất, không bị silently discarded.
5. **Đo decorator nhẹ và decorator thực:** giữ cùng pool/task, warm-up, nhiều vòng, nhiều cỡ N và nhiều task sizes.
6. **Phân tích metric:** median/p95/p99, throughput, allocation/GC và queue, không chỉ % dựa một phép đo.
7. **Xác định tác nhân:** wrapper allocation, MDC copy, ContextSnapshot, logging/export, scheduling hay downstream.
8. **Chọn tối ưu:** batching, truyền context tối thiểu, sampling, executor tách biệt, hoặc giữ nguyên nếu overhead không có ý nghĩa.
9. **Kiểm thử regressions và rollout:** ngữ cảnh, trace completeness, behavior khi overload và khi exception phải còn đúng.
10. **Ghi lại điều kiện đo:** JDK/Spring, máy, thread count, warm-up, repetitions và kết quả có bất định.

### Tài liệu chính thức

1. [Spring Framework 6.2 – TaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/TaskDecorator.html): callback thực thi, context/monitoring và giới hạn nhìn thấy exception.
2. [Spring Framework 6.2 – ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): context propagation và cảnh báo overhead khi có nhiều tác vụ rất nhỏ.
3. [Spring Framework 6.2 – ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): cấu hình `setTaskDecorator` và tài nguyên pool/queue.
4. [Micrometer Context Propagation – Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html): `ThreadLocalAccessor`, `ContextSnapshot` và propagation qua ranh giới thread.
5. [OpenJDK – Java Microbenchmark Harness](https://github.com/openjdk/jmh): warm-up, fork, measurement và microbenchmark.
6. [Java SE 17 – ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): scope per-thread, `get/set/remove`.
7. [Java SE 17 – ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submission, worker lifecycle, shutdown và Future.

**Kết luận:** chi phí TaskDecorator phụ thuộc **số lần trang trí, độ ngắn của mỗi task và loại context phải chụp/khôi phục**. Nếu chỉ có rất ít task, phép đo cũng dễ nhiễu và overhead tuyệt đối có thể không đáng kể. Hãy giữ đúng semantics context trước, đo có baseline và đủ mẫu sau, rồi tối ưu có chọn lọc thay vì tắt tracing hoặc suy đoán từ một con số stopwatch.
