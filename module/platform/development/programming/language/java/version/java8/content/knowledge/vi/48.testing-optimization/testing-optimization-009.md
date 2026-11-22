# Quan sát boxing, allocation, GC và common pool trong Java

## 1. Mục tiêu: đo đúng nơi JVM đang tiêu tốn tài nguyên

Khi tối ưu Java, thời gian chạy của một đoạn code chỉ là một phần bức tranh. Một request chậm có thể do CPU, cấp phát object quá nhiều, garbage collection (GC), thread chờ lock/I/O hoặc task bị xếp hàng trong ForkJoinPool. Cần quan sát các tín hiệu này cùng một workload để tìm đúng nguyên nhân.

Bài này hướng dẫn cách quan sát bốn nhóm:

- **Boxing:** chuyển giữa primitive (`int`, `long`, `double`) và wrapper (`Integer`, `Long`, `Double`), collection generic và primitive stream.
- **Allocation:** số byte/object được cấp phát, allocation rate, loại object và stack trace tạo object.
- **GC:** số lần collection, thời gian collection, heap occupancy, pause và dấu hiệu phân biệt allocation churn với memory leak.
- **Common pool:** parallelism, worker, active task, queue, work stealing và những API Java thường dùng pool này.

Các ví dụ code chạy độc lập, tương thích Java 8+ khi chỉ dùng API ứng dụng; riêng phép đo `ThreadMXBean.getCurrentThreadAllocatedBytes()` cần JDK 14+ và ví dụ quan sát đã được chạy trên JDK 24. JFR có sẵn trong các JDK hiện đại; JDK Mission Control (JMC) là công cụ phân tích recording được cài riêng. Bài chỉ dùng công cụ và API còn được hỗ trợ, không hướng dẫn flag GC cũ hoặc kỹ thuật tối ưu dựa trên implementation đã lỗi thời.

**Nguyên tắc:** đo trước, tạo giả thuyết, xác minh bằng profile, thay đổi một yếu tố, rồi đo lại trên cùng workload. Không tối ưu chỉ vì một dòng code trông có vẻ tốn allocation.

## 2. Phân biệt bốn loại tín hiệu

| Tín hiệu | Câu hỏi cần trả lời | Công cụ phù hợp |
| --- | --- | --- |
| Boxing | Có chuyển primitive thành wrapper trong vòng lặp hoặc pipeline không? | Code review, JFR allocation sample, profiler |
| Allocation | Class/method/thread nào cấp phát nhiều byte nhất? | JFR, JMC, ThreadMXBean, profiler |
| GC | GC xảy ra bao lâu một lần, pause bao lâu, heap còn lại sau collection ra sao? | GC unified logs, JFR, GC MXBeans |
| Common pool | Có bao nhiêu task đang chạy/chờ, pool có bị nghẽn hoặc bị block không? | ForkJoinPool metrics, JMX, JFR, thread dump |

Cần tách ba khái niệm bộ nhớ:

- **Allocation rate:** tốc độ cấp phát, ví dụ MB/s. Allocation cao có thể tạo nhiều GC dù object sống rất ngắn.
- **Heap occupancy:** lượng heap đang được sử dụng tại một thời điểm.
- **Retained/live set:** object còn reachable và tiếp tục được giữ sau GC. Đây là tín hiệu quan trọng khi tìm memory leak.

Allocation cao không tự chứng minh có memory leak. Ngược lại, heap occupancy tăng dần sau các lần GC và không giảm về mức ổn định có thể gợi ý object đang bị giữ lại ngoài dự kiến.

## 3. Quan sát boxing và unboxing

### 3.1. Boxing là gì?

Boxing chuyển primitive thành wrapper:

```java
int count = 42;
Integer boxed = count; // Autoboxing

Integer input = 100;
int value = input;     // Unboxing
```

Compiler thực hiện chuyển đổi tương đương với các phương thức như `Integer.valueOf(...)` và `intValue()`. Unboxing một reference `null` gây `NullPointerException`.

Boxing thường xuất hiện khi:

- Đưa số vào `List<Integer>`, `Map<Long, ...>` hoặc API generic.
- Gán primitive vào biến wrapper hoặc truyền vào tham số nhận wrapper.
- Dùng `Stream<Integer>` thay vì `IntStream`.
- Dùng `Optional<Integer>` khi `OptionalInt` phù hợp hơn.
- Truyền primitive qua varargs `Object...` hoặc API nhận `Object`.
- Dùng wrapper làm biến accumulator trong vòng lặp.

Ví dụ vòng lặp:

```java
// Có thể boxing/unboxing ở mỗi vòng lặp.
Integer total = 0;

for (int i = 0; i < 1_000_000; i++) {
    total += i;
}
```

Phép `+=` ở đây cần unbox `total`, cộng số nguyên, rồi box kết quả trở lại `Integer`. JIT có thể tối ưu một số allocation sau khi phân tích code, nhưng không nên mặc định rằng mọi wrapper tạm đều bị loại bỏ.

Nếu biến chỉ cần chứa số trong lúc tính toán, dùng primitive:

```java
int total = 0;

for (int i = 0; i < 1_000_000; i++) {
    total += i;
}

Integer result = total; // Chỉ box khi thật sự cần.
```

### 3.2. Wrapper cache và lỗi so sánh bằng ==

Một số wrapper có cache cho một miền giá trị. Với boxing các hằng số nguyên trong miền từ -128 đến 127, Java bảo đảm identity theo quy tắc boxing. Ngoài miền này, không được dựa vào việc hai wrapper có cùng reference hay không.

```java
Integer a = 127;
Integer b = 127;

Integer x = 1000;
Integer y = 1000;

System.out.println(a == b);       // true theo boxing guarantee
System.out.println(x.equals(y)); // true: cùng giá trị
// Không dùng x == y để so sánh số.
```

Dùng `equals()` để so sánh giá trị wrapper; dùng primitive khi không cần object identity. Cache implementation và phạm vi cache mở rộng có thể phụ thuộc runtime, nên đừng dùng `==` để suy ra chi phí allocation.

### 3.3. Primitive streams tránh wrapper trong pipeline số

`IntStream`, `LongStream` và `DoubleStream` là các specialization cho primitive. Khi xử lý phép toán số, ưu tiên chúng thay vì tạo `Stream<Integer>`/`Stream<Long>` nếu không cần object.

```java
int primitiveSum = IntStream.range(0, 1000).sum();

int boxedSum = IntStream.range(0, 1000)
    .boxed()
    .mapToInt(Integer::intValue)
    .sum();
```

Hai phép tính cho cùng kết quả, nhưng pipeline thứ hai chuyển phần tử thành `Integer` để đi qua `Stream<Integer>`. JIT có thể tối ưu một số trường hợp; hãy đo trên pipeline thực tế thay vì suy luận số object chỉ từ source code.

Dùng kiểu dữ liệu phù hợp với yêu cầu API:

| Nhu cầu | Ưu tiên xem xét |
| --- | --- |
| Biến đếm nội bộ | `int` hoặc `long` |
| Stream số nguyên | `IntStream` |
| Stream số dài | `LongStream` |
| Optional primitive | `OptionalInt`, `OptionalLong`, `OptionalDouble` |
| Collection generic bắt buộc | `List<Integer>`/`Map<Long, ...>` theo hợp đồng API |
| Counter đồng thời | `LongAdder` hoặc `AtomicLong` tùy semantics |

Không thay wrapper bằng primitive nếu nghiệp vụ cần `null`, generic type hoặc API contract. Tối ưu đúng là tránh boxing **không cần thiết**, không phải loại bỏ wrapper ở mọi nơi.

## 4. Đo allocation thay vì đếm object bằng mắt

### 4.1. Vì sao số lệnh new không bằng số object chắc chắn tồn tại trên heap?

JIT có thể inline method, loại bỏ allocation không quan sát được hoặc scalar-replace một object không thoát khỏi phạm vi sử dụng. Ngược lại, một dòng code ngắn có thể cấp phát nhiều object qua boxing, iterator, lambda capture, collection growth, formatter hoặc serialization.

Vì thế:

- Source code cho biết **nguy cơ** allocation.
- Allocation profiler cho biết **runtime thực tế** đang cấp phát ở đâu.
- Heap dump/retained-size analysis cho biết **object nào còn được giữ lại**.
- Benchmark cho biết **thay đổi có cải thiện workload hay không**.

### 4.2. Đo byte được cấp phát bởi thread với ThreadMXBean

HotSpot và một số JVM cung cấp extension `com.sun.management.ThreadMXBean`. `getCurrentThreadAllocatedBytes()` trả về **ước lượng** tổng byte heap đã được cấp phát bởi thread hiện tại. API này không phải chuẩn portable của mọi JVM; có thể không được hỗ trợ hoặc bị tắt.

Ví dụ dưới đây so sánh `int[]` và `Integer[]`. Mảng được giữ trong biến `volatile` để kết quả không bị loại bỏ như một phép tính không dùng đến. Các giá trị bắt đầu từ 1000 để tránh miền cache Integer mặc định trong lần chạy minh họa.

**BoxingAllocationDemo.java**

```java
import com.sun.management.ThreadMXBean;
import java.lang.management.ManagementFactory;
import java.util.stream.IntStream;

public class BoxingAllocationDemo {
    private static volatile Object sink;

    private static int[] primitiveArray(int size) {
        int[] values = new int[size];
        for (int i = 0; i < size; i++) {
            values[i] = 1000 + i;
        }
        return values;
    }

    private static Integer[] boxedArray(int size) {
        Integer[] values = new Integer[size];
        for (int i = 0; i < size; i++) {
            values[i] = Integer.valueOf(1000 + i);
        }
        return values;
    }

    public static void main(String[] args) {
        Integer smallA = 127;
        Integer smallB = 127;
        Integer largeA = 1000;
        Integer largeB = 1000;

        System.out.println(
            "smallCacheIdentity=" + (smallA == smallB)
        );
        System.out.println(
            "largeValueEquality=" + largeA.equals(largeB)
        );

        int primitiveSum = IntStream.range(0, 1000).sum();
        int boxedSum = IntStream.range(0, 1000)
            .boxed()
            .mapToInt(Integer::intValue)
            .sum();

        System.out.println("primitiveSum=" + primitiveSum);
        System.out.println("boxedStreamSum=" + boxedSum);

        ThreadMXBean bean =
            (ThreadMXBean) ManagementFactory.getThreadMXBean();

        if (!bean.isThreadAllocatedMemorySupported()) {
            System.out.println("allocationCounterSupported=false");
            return;
        }

        try {
            if (!bean.isThreadAllocatedMemoryEnabled()) {
                bean.setThreadAllocatedMemoryEnabled(true);
            }
        } catch (SecurityException denied) {
            System.out.println("allocationCounterSupported=false");
            return;
        }

        int size = 200_000;

        // Warm up class initialization and both allocation paths.
        sink = primitiveArray(1000);
        sink = boxedArray(1000);

        long beforePrimitive =
            bean.getCurrentThreadAllocatedBytes();

        sink = primitiveArray(size);

        long primitiveBytes =
            bean.getCurrentThreadAllocatedBytes() - beforePrimitive;

        long beforeBoxed =
            bean.getCurrentThreadAllocatedBytes();

        sink = boxedArray(size);

        long boxedBytes =
            bean.getCurrentThreadAllocatedBytes() - beforeBoxed;

        System.out.println("allocationCounterSupported=true");
        System.out.println(
            "primitiveBytesPositive=" + (primitiveBytes > 0)
        );
        System.out.println(
            "boxedBytesGreaterThanPrimitive=" +
            (boxedBytes > primitiveBytes)
        );
        System.out.println("primitiveBytes=" + primitiveBytes);
        System.out.println("boxedBytes=" + boxedBytes);
    }
}
```

Chạy bằng JDK 14+:

```bash
javac BoxingAllocationDemo.java
java BoxingAllocationDemo
```

Một lần chạy trên JDK 24 cho kết quả:

```text
smallCacheIdentity=true
largeValueEquality=true
primitiveSum=499500
boxedStreamSum=499500
allocationCounterSupported=true
primitiveBytesPositive=true
boxedBytesGreaterThanPrimitive=true
primitiveBytes=800408
boxedBytes=4000016
```

Số byte thay đổi theo JVM, JIT, cấu hình wrapper cache và môi trường. Đây là số liệu đo của một thread, không phải benchmark chuẩn và không đại diện cho allocation của toàn process. `getCurrentThreadAllocatedBytes()` cũng là số liệu ước lượng; không dùng một lần đo ngắn để kết luận hiệu năng production.

### 4.3. Đo allocation rate và tìm allocation site

Một con số tổng như MB/s cho biết mức áp lực allocation nhưng chưa cho biết **method nào** gây ra. Cần profile để tìm:

- Class nào tạo nhiều object nhất?
- Method/stack trace nào tạo nhiều byte?
- Allocation tập trung ở thread request, worker hay scheduler?
- Object sống ngắn hay được giữ lại?
- Allocation có tăng theo số request hay theo thời gian?
- Sau khi giảm allocation, GC pause và latency có thực sự giảm không?

JFR (Java Flight Recorder) ghi các event có timestamp. Event `jdk.ObjectAllocationSample` là **mẫu có trọng số**, không phải log của mọi object được tạo. Dùng JMC để xem allocation theo class, thread và stack trace; đối chiếu mẫu với source code.

JFR có thể chạy cùng ứng dụng:

```bash
java -XX:StartFlightRecording=filename=app.jfr,settings=profile com.example.Main
```

Hoặc bắt đầu recording cho JVM đang chạy:

```bash
jcmd <pid> JFR.start name=perf settings=profile duration=60s filename=perf.jfr
jfr summary perf.jfr
jfr print --events jdk.ObjectAllocationSample,jdk.GarbageCollection perf.jfr
```

Thay `<pid>` bằng process ID thật. `jcmd` và `jfr` nằm trong thư mục `bin` của JDK. JMC là công cụ riêng để mở recording và phân tích theo allocation, method, thread, lock và GC.

`default.jfc` phù hợp recording liên tục có overhead thấp nhưng không thu đầy đủ allocation profiling. `profile.jfc` thu nhiều dữ liệu hơn và có thể tạo thêm overhead. Hãy chọn template theo câu hỏi cần trả lời và thời lượng đo; thử nghiệm với workload gần production.

### 4.4. Dùng JMH cho microbenchmark

Không dùng vòng lặp `System.nanoTime()` tự viết để so sánh hai đoạn code nhỏ. JIT warmup, dead-code elimination, constant folding, escape analysis, GC và thứ tự chạy có thể làm kết quả sai lệch.

Dùng JMH với warmup, measurement iterations, forks và Blackhole phù hợp. Benchmark phải giữ đầu vào/đầu ra có ý nghĩa và gần workload thật. Kết quả microbenchmark không thay thế profiling ứng dụng đang chạy.

## 5. Quan sát Garbage Collection

### 5.1. GC count, time và heap usage

JVM cung cấp các bean quản lý:

- `GarbageCollectorMXBean.getCollectionCount()`: số lần collection mà collector báo cáo.
- `GarbageCollectorMXBean.getCollectionTime()`: thời gian collection tích lũy, tính bằng millisecond.
- `Runtime.totalMemory() - Runtime.freeMemory()`: ước lượng heap đang sử dụng trong vùng heap đã cấp cho JVM.
- `MemoryMXBean` và `MemoryPoolMXBean`: trạng thái heap/non-heap và từng memory pool.

`getCollectionCount()` hoặc `getCollectionTime()` có thể trả `-1` nếu JVM không hỗ trợ số liệu đó. Count/time là bộ đếm tích lũy từ lúc JVM chạy; delta giữa hai lần đọc giúp quan sát một khoảng workload.

### 5.2. Ví dụ 2 — GcObservationDemo.java

Ví dụ tạo một lượng object ngắn hạn rồi quan sát bộ đếm trước/sau. Chương trình **không gọi `System.gc()`** vì yêu cầu GC không đảm bảo collection sẽ xảy ra ngay và có thể làm sai phép đo.

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;

public class GcObservationDemo {
    static long total(
        List<GarbageCollectorMXBean> beans,
        boolean count
    ) {
        long total = 0;
        boolean available = false;

        for (GarbageCollectorMXBean bean : beans) {
            long value = count
                ? bean.getCollectionCount()
                : bean.getCollectionTime();

            if (value >= 0) {
                total += value;
                available = true;
            }
        }

        return available ? total : -1;
    }

    static long usedHeap() {
        Runtime runtime = Runtime.getRuntime();
        return runtime.totalMemory() - runtime.freeMemory();
    }

    public static void main(String[] args) {
        List<GarbageCollectorMXBean> collectors =
            ManagementFactory.getGarbageCollectorMXBeans();

        long countBefore = total(collectors, true);
        long timeBefore = total(collectors, false);
        long heapBefore = usedHeap();

        List<byte[]> temporary = new ArrayList<>();

        for (int i = 0; i < 64; i++) {
            temporary.add(new byte[256 * 1024]);

            if (temporary.size() == 8) {
                temporary.clear();
            }
        }

        temporary.clear();

        long countAfter = total(collectors, true);
        long timeAfter = total(collectors, false);
        long heapAfter = usedHeap();

        System.out.println(
            "collectorBeansAvailable=" + !collectors.isEmpty()
        );
        System.out.println(
            "gcCounterAvailable=" +
            (countBefore >= 0 && countAfter >= 0)
        );
        System.out.println(
            "gcTimeAvailable=" +
            (timeBefore >= 0 && timeAfter >= 0)
        );
        System.out.println(
            "heapUsageAvailable=" +
            (heapBefore >= 0 && heapAfter >= 0)
        );
        System.out.println(
            "gcCountDelta=" +
            (countBefore < 0 || countAfter < 0
                ? "unavailable"
                : countAfter - countBefore)
        );
        System.out.println(
            "gcTimeDeltaMs=" +
            (timeBefore < 0 || timeAfter < 0
                ? "unavailable"
                : timeAfter - timeBefore)
        );
    }
}
```

Chạy:

```bash
javac GcObservationDemo.java
java GcObservationDemo
```

Một lần chạy JDK 24:

```text
collectorBeansAvailable=true
gcCounterAvailable=true
gcTimeAvailable=true
heapUsageAvailable=true
gcCountDelta=0
gcTimeDeltaMs=0
```

Delta bằng 0 ở lần chạy này nghĩa là workload ngắn chưa kích hoạt collection trong khoảng đo. Nó **không** chứng minh GC không hoạt động hoặc không có allocation. Nếu collection xảy ra, delta sẽ phụ thuộc collector và workload.

### 5.3. Bật GC unified logging trên JDK hiện đại

Trên JDK 9+, unified logging cho phép thu GC log bằng `-Xlog`:

```bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags com.example.Main
```

Có thể bắt đầu với `gc*`, sau đó chỉ bật chi tiết bổ sung cần thiết. Log giúp quan sát collector, young/old collection, pause, heap trước/sau và các phase. Tránh thu mức debug quá chi tiết trong thời gian dài nếu chưa đánh giá dung lượng log và overhead.

### 5.4. Đọc GC theo xu hướng, không chỉ nhìn số lần

| Quan sát | Có thể gợi ý | Cần kiểm tra tiếp |
| --- | --- | --- |
| Allocation tăng, GC thường xuyên, heap sau GC ổn định | Nhiều object ngắn hạn | Allocation site, bytes/request, object lifetime |
| Old-gen sau GC tăng dần qua nhiều chu kỳ | Object được giữ lại | Heap dump, retained paths, cache/list/static reference |
| Pause dài hoặc p99 latency tăng cùng GC pause | GC ảnh hưởng latency | JFR GC phases, heap pressure, collector config |
| Heap còn thấp nhưng CPU cao | Có thể là CPU/lock/serialization | JFR execution samples, thread CPU, lock events |
| Heap occupancy cao nhưng không tăng theo thời gian | Có thể là workload ổn định | Live set sau GC, headroom và giới hạn heap |

Một GC count lớn không tự chứng minh cấu hình collector sai. Tương tự, GC pause ngắn không chứng minh ứng dụng không có memory leak. Cần xem allocation rate, live set sau collection, pause distribution và latency của request trong cùng khoảng thời gian.

Không gọi `System.gc()` để “làm sạch” trước mỗi phép đo. Lệnh này chỉ là yêu cầu; JVM có thể bỏ qua hoặc xử lý theo cấu hình, và forced collection làm thay đổi hành vi cần đo.

## 6. Quan sát common ForkJoinPool

### 6.1. Common pool là gì?

`ForkJoinPool.commonPool()` là pool dùng chung trong JVM, dựa trên work stealing. Worker có thể thực thi task được submit trực tiếp hoặc task được fork từ worker khác.

Các API thường gặp:

- `CompletableFuture.supplyAsync(...)`, `runAsync(...)` và các async stage **không truyền Executor** thường chạy trên `ForkJoinPool.commonPool()`.
- Parallel stream trong OpenJDK/HotSpot thường dùng fork/join execution; khi khởi chạy từ thread ngoài ForkJoinPool, common pool thường tham gia. Đừng coi thread name là hợp đồng của Stream API.
- `ForkJoinTask` không được submit vào pool riêng có thể dùng common pool.

Có một ngoại lệ cần biết: nếu common pool không hỗ trợ parallelism tối thiểu 2, các async method của `CompletableFuture` không truyền executor có thể dùng thread mới cho từng task. Vì vậy hãy đọc `getParallelism()` và quan sát runtime thực tế.

Các stage **không có hậu tố Async** của `CompletableFuture` có thể chạy trên thread hoàn tất stage trước đó hoặc thread gọi phương thức completion. Không suy rằng mọi callback đều chạy trên common pool.

### 6.2. Các metric quan trọng

| Metric | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| `getParallelism()` | Parallelism mục tiêu | Mức song song pool hướng tới |
| `getPoolSize()` | Số worker hiện có | Số thread pool đang duy trì |
| `getActiveThreadCount()` | Ước lượng worker đang chạy/steal task | Snapshot gần thời điểm đọc |
| `getRunningThreadCount()` | Ước lượng worker không bị block chờ join/synchronization | Không phải số CPU đang bận chính xác |
| `getQueuedTaskCount()` | Ước lượng task trong queue của worker | Không bao gồm submission chưa bắt đầu |
| `getQueuedSubmissionCount()` | Ước lượng submission bên ngoài đang chờ | Có thể tốn thời gian để ước lượng |
| `getStealCount()` | Ước lượng số task được thread khác submitter thực thi | Chỉ số work stealing, không phải throughput |
| `isQuiescent()` | Pool được xem là idle | Trạng thái có thể cập nhật trễ |

Các giá trị active, queued và steal là **ước lượng**, có thể thay đổi trong lúc đọc. `getStealCount()` có thể thấp hơn thực tế khi pool chưa quiescent. `getQueuedTaskCount()` không bao gồm submission bên ngoài chưa bắt đầu; xem `getQueuedSubmissionCount()` cho nhóm đó.

Đừng dùng một snapshot queue để khẳng định pool nghẽn. Hãy lấy mẫu theo thời gian và đối chiếu với task latency, throughput, CPU usage, thread dump và JFR.

### 6.3. Ví dụ 3 — quan sát CompletableFuture và parallel stream

**CommonPoolObservationDemo.java**

```java
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

public class CommonPoolObservationDemo {
    public static void main(String[] args) {
        ForkJoinPool pool = ForkJoinPool.commonPool();
        int taskCount = 200;

        AtomicInteger completed = new AtomicInteger();
        Set<String> workerNames = ConcurrentHashMap.newKeySet();

        CompletableFuture<?>[] futures =
            IntStream.range(0, taskCount)
                .mapToObj(i -> CompletableFuture.runAsync(() -> {
                    workerNames.add(
                        Thread.currentThread().getName()
                    );
                    completed.incrementAndGet();
                }))
                .toArray(CompletableFuture[]::new);

        CompletableFuture.allOf(futures).join();

        Set<String> streamThreads =
            IntStream.range(0, 1000)
                .parallel()
                .mapToObj(i -> Thread.currentThread().getName())
                .collect(
                    java.util.stream.Collectors.toSet()
                );

        boolean commonWorkerSeen = workerNames.stream()
            .anyMatch(name ->
                name.startsWith("ForkJoinPool.commonPool-worker-")
            );

        boolean streamCommonWorkerSeen = streamThreads.stream()
            .anyMatch(name ->
                name.startsWith("ForkJoinPool.commonPool-worker-")
            );

        System.out.println("tasksCompleted=" + completed.get());
        System.out.println("expectedTasks=" + taskCount);
        System.out.println(
            "commonPoolWorkerObserved=" + commonWorkerSeen
        );
        System.out.println(
            "parallelStreamWorkerObserved=" +
            streamCommonWorkerSeen
        );
        System.out.println(
            "parallelismPositive=" + (pool.getParallelism() > 0)
        );
        System.out.println(
            "activeCountNonNegative=" +
            (pool.getActiveThreadCount() >= 0)
        );
        System.out.println(
            "queuedTaskCountNonNegative=" +
            (pool.getQueuedTaskCount() >= 0)
        );
        System.out.println(
            "queuedSubmissionCountNonNegative=" +
            (pool.getQueuedSubmissionCount() >= 0)
        );
        System.out.println(
            "stealCountNonNegative=" + (pool.getStealCount() >= 0)
        );
    }
}
```

Chạy:

```bash
javac CommonPoolObservationDemo.java
java CommonPoolObservationDemo
```

Một lần chạy JDK 24:

```text
tasksCompleted=200
expectedTasks=200
commonPoolWorkerObserved=true
parallelStreamWorkerObserved=true
parallelismPositive=true
activeCountNonNegative=true
queuedTaskCountNonNegative=true
queuedSubmissionCountNonNegative=true
stealCountNonNegative=true
```

Tên worker chỉ được dùng để minh họa việc quan sát thread trong demo; ứng dụng production nên đo metric của pool và trace task, không parse tên thread như một API ổn định.

### 6.4. Khi common pool bị nghẽn

Các dấu hiệu cần điều tra:

- Queue submissions tăng liên tục và task latency cũng tăng.
- Worker active cao kéo dài nhưng throughput không tăng.
- Nhiều worker ở trạng thái blocked/parked do I/O hoặc lock.
- Một nhóm task chạy lâu khiến các task nhỏ phải chờ.
- CPU cao và JFR cho thấy hot methods hoặc allocation lớn.
- CPU thấp nhưng worker chờ socket/monitor, gợi ý bottleneck I/O hoặc synchronization.

Common pool phù hợp với nhiều tác vụ fork/join và CPU-bound nhỏ. Blocking I/O không được quản lý có thể làm giảm tiến độ; ForkJoinPool không bảo đảm bù đủ worker trong mọi tình huống blocked I/O hoặc unmanaged synchronization.

Với I/O có thời gian chờ dài, thường nên dùng Executor riêng để cô lập tải:

```java
ExecutorService ioExecutor =
    Executors.newFixedThreadPool(16);

try {
    CompletableFuture<String> response =
        CompletableFuture.supplyAsync(
            () -> callRemoteService(),
            ioExecutor
        );

    System.out.println(response.join());
} finally {
    ioExecutor.shutdown();
}
```

`callRemoteService()` là phương thức minh họa. Chọn kích thước pool theo giới hạn kết nối, latency và tải thực tế; thêm timeout, cancellation và giới hạn queue phù hợp. Không gọi `shutdown()` trên `ForkJoinPool.commonPool()` vì đây là pool toàn JVM và không bị tắt theo cách thông thường.

Nếu một fork/join task buộc phải block, có thể tìm hiểu `ForkJoinPool.ManagedBlocker`; với phần lớn ứng dụng service, executor riêng cho blocking work thường dễ quản lý hơn.

## 7. Kết hợp JFR, GC logs và common pool metrics

Một quy trình quan sát thực tế:

1. **Tạo baseline:** ghi lại throughput, p50/p95/p99 latency, CPU, heap, allocation rate và pool metrics.
2. **Tạo workload có thể lặp lại:** cùng số request, dữ liệu, concurrency và thời gian chạy.
3. **Bắt JFR:** dùng template phù hợp, quan sát `jdk.ObjectAllocationSample`, `jdk.GarbageCollection`, `jdk.GCPhasePause`, `jdk.ThreadPark`, `jdk.JavaMonitorWait`, `jdk.CPULoad` và `jdk.ThreadCPULoad` khi cần.
4. **Bật GC log:** dùng unified logging để xem collector và pause trong cùng khoảng thời gian.
5. **Lấy common pool snapshot định kỳ:** parallelism, active/running, queued tasks, queued submissions, steal count.
6. **Đối chiếu timeline:** allocation spike có đi trước GC pause không? GC pause có trùng p99 latency không? Queue tăng có trùng worker bị block không?
7. **Tìm stack trace:** xác định method tạo wrapper/object, giữ lock hoặc block.
8. **Thay một yếu tố:** primitive pipeline, giảm object trung gian, đổi task granularity hoặc tách blocking executor.
9. **Chạy lại cùng workload:** so throughput, latency, allocation rate, GC pause và pool queue; kiểm tra correctness và tải cực đại.

JFR cho biết nơi cấp phát và thời điểm xảy ra sự kiện; GC log cho biết collector đã làm gì; common pool metrics cho biết tình trạng task scheduling. Không công cụ đơn lẻ nào trả lời mọi câu hỏi.

### 7.1. Các event JFR thường hữu ích

| Event | Quan sát |
| --- | --- |
| `jdk.ObjectAllocationSample` | Class và stack trace allocation được lấy mẫu |
| `jdk.GarbageCollection` | Mỗi collection và thời lượng |
| `jdk.GCPhasePause` | Các phase pause của GC |
| `jdk.GCHeapSummary` | Heap usage quanh collection |
| `jdk.ThreadPark` | Thread bị park/chờ |
| `jdk.JavaMonitorWait` | Chờ monitor |
| `jdk.ThreadCPULoad` | CPU load theo thread |
| `jdk.CPULoad` | CPU load JVM và host |

JFR sampling không bảo đảm ghi mọi event hoặc mọi allocation. Một event không xuất hiện có thể do template không bật event, threshold hoặc sampling. Hãy kiểm tra recording settings trước khi kết luận không có hoạt động đó.

### 7.2. Dấu hiệu allocation pressure và memory leak

**Allocation pressure:** nhiều object ngắn hạn, allocation bytes/request cao, GC thường xuyên nhưng live set sau collection tương đối ổn định. Tập trung giảm object tạm, boxing không cần thiết, serialization lặp và collection trung gian.

**Memory leak/retention:** object vẫn reachable sau nhiều collection, live set tăng dần, cache/map/list tăng không giới hạn hoặc listener/reference không được giải phóng. Dùng heap dump và retained path để tìm reference giữ object; chỉ nhìn GC count không đủ kết luận.

## 8. Các lỗi thường gặp khi quan sát và tối ưu

1. **Dùng `==` so sánh Integer:** wrapper identity không phải giá trị số; dùng `equals()` hoặc unbox có kiểm soát.
2. **Boxing trong accumulator:** biến `Integer` cập nhật liên tục có thể tạo wrapper; dùng `int`/`long` khi phù hợp.
3. **Dùng Stream<Integer> cho phép toán số:** xem xét `IntStream`/`LongStream`.
4. **Giả định mọi boxing luôn cấp phát:** cache và JIT có thể thay đổi số object thực tế; đo runtime.
5. **Giả định mọi `new` luôn tồn tại trên heap:** JIT có thể loại allocation không escape; dùng profiler.
6. **Đo một lần rồi kết luận:** warmup, GC và JIT làm số liệu dao động; lặp lại và dùng JMH.
7. **Coi ThreadMXBean là API portable:** extension có thể không hỗ trợ hoặc bị tắt; kiểm tra capability.
8. **Đo allocation của một thread rồi suy ra toàn process:** đo thêm worker và dùng JFR.
9. **Coi allocation rate cao là memory leak:** phân biệt object ngắn hạn với retained live set.
10. **Coi heap used không giảm ngay là leak:** GC chưa chắc đã chạy; quan sát qua nhiều chu kỳ.
11. **Gọi `System.gc()` trước khi đo:** làm thay đổi workload và không bảo đảm collection.
12. **Chỉ nhìn tổng GC count:** xem pause time, live set, allocation rate và request latency.
13. **Bật JFR profile rồi bỏ qua overhead:** template profile thu nhiều dữ liệu hơn; đo thời lượng phù hợp.
14. **Coi allocation sample là thống kê mọi object:** event có trọng số và được lấy mẫu.
15. **Dùng `getQueuedTaskCount()` như số task toàn pool chính xác:** metric là ước lượng và không gồm external submissions chưa bắt đầu.
16. **Coi steal count là throughput:** đây là ước lượng work stealing, cần đo task completion và latency.
17. **Dùng common pool cho mọi I/O:** blocking có thể làm giảm tiến độ; tách executor phù hợp.
18. **Cho rằng mọi CompletableFuture callback chạy common pool:** non-async stage có thể chạy trên thread hoàn tất stage.
19. **Cho rằng parallel stream luôn dùng cùng thread:** scheduling phụ thuộc runtime và ngữ cảnh; không dựa vào thread name.
20. **Thay common pool global để sửa một thư viện:** có thể ảnh hưởng toàn JVM; dùng Executor tường minh khi cần cô lập.
21. **Tối ưu allocation nhưng làm code khó đọc:** chỉ thay đổi khi số đo chứng minh có lợi và correctness được giữ.
22. **Chỉ benchmark một máy dev:** kiểm tra trên JDK, CPU, heap và concurrency gần môi trường triển khai.

## 9. Checklist review performance

- Có wrapper trong vòng lặp số học hoặc accumulator không?
- Có dùng `Integer`/`Long` khi primitive đáp ứng được không?
- Có dùng primitive stream cho phép toán số không?
- Có so sánh wrapper bằng `equals()` thay vì `==` không?
- Allocation profiler đã xác định class/method tạo nhiều byte chưa?
- Đã phân biệt allocation rate và retained heap chưa?
- Số liệu ThreadMXBean có được kiểm tra capability và giới hạn theo thread không?
- JFR recording có bật event phù hợp với câu hỏi không?
- GC log có cùng time window với workload không?
- Có nhìn GC pause và heap sau collection không?
- Có kiểm tra heap dump/retained paths nếu nghi memory leak không?
- Common pool parallelism/active/queue/steal đã được lấy mẫu theo thời gian chưa?
- Đã kiểm tra blocking I/O và lock wait trong worker chưa?
- CompletableFuture async task có cần Executor riêng không?
- Task granularity có đủ lớn để bù scheduling overhead không?
- Đã benchmark bằng JMH hoặc workload tích hợp có thể lặp lại chưa?
- Đã so sánh throughput và p95/p99 latency trước/sau thay đổi chưa?
- Có giữ correctness, timeout, cancellation và back-pressure không?

## 10. Câu hỏi ôn tập

**1.** Boxing là gì?

**Đáp án:** Chuyển primitive thành wrapper object, ví dụ `int` thành `Integer`.

**2.** Unboxing `Integer null` gây ra điều gì?

**Đáp án:** `NullPointerException`.

**3.** Vì sao không dùng `==` để so sánh hai Integer?

**Đáp án:** `==` so sánh reference; cache có thể làm một số reference trùng nhau, nhưng identity ngoài miền được bảo đảm không nên giả định.

**4.** Primitive stream nào dành cho số nguyên?

**Đáp án:** `IntStream`.

**5.** Allocation rate khác retained heap thế nào?

**Đáp án:** Allocation rate là tốc độ tạo object; retained heap là lượng object còn được giữ lại.

**6.** JIT có thể làm gì với allocation không escape?

**Đáp án:** Có thể loại bỏ hoặc scalar-replace một số allocation; phải đo runtime.

**7.** ThreadMXBean đo gì?

**Đáp án:** Ước lượng byte heap được cấp phát bởi thread, nếu JVM hỗ trợ và measurement được bật.

**8.** `getCollectionCount()` có thể trả -1 không?

**Đáp án:** Có, nếu collector không hỗ trợ số liệu.

**9.** GC count bằng 0 trong một sample có nghĩa không có allocation không?

**Đáp án:** Không; allocation có thể xảy ra mà chưa cần collection.

**10.** Vì sao không gọi `System.gc()` trước mỗi phép đo?

**Đáp án:** Nó không bảo đảm collection và làm thay đổi hành vi cần quan sát.

**11.** JFR `ObjectAllocationSample` có ghi mọi object không?

**Đáp án:** Không, đây là event lấy mẫu có trọng số.

**12.** JMC dùng để làm gì?

**Đáp án:** Mở và phân tích JFR recording, allocation, method, thread, lock và GC.

**13.** GC count cao có chứng minh memory leak không?

**Đáp án:** Không; cần phân biệt allocation churn và object bị giữ lại sau GC.

**14.** `CompletableFuture.supplyAsync()` không truyền Executor thường dùng pool nào?

**Đáp án:** `ForkJoinPool.commonPool()`; nếu parallelism quá thấp, runtime có thể dùng thread mới theo policy API.

**15.** Parallel stream có API truyền Executor trực tiếp không?

**Đáp án:** Không có tham số Executor trên Stream API; cách thực thi phụ thuộc runtime/context.

**16.** `getQueuedTaskCount()` có chính xác tuyệt đối không?

**Đáp án:** Không, đây là ước lượng queue của worker và không bao gồm external submissions chưa bắt đầu.

**17.** `getStealCount()` cho biết gì?

**Đáp án:** Ước lượng số task được thread khác submitter thực thi; không phải throughput.

**18.** Vì sao blocking I/O có thể làm common pool chậm?

**Đáp án:** Worker bị chặn không thực thi task khác; pool không bảo đảm bù đủ thread cho mọi blocking/unmanaged synchronization.

**19.** Khi nào nên truyền Executor riêng cho CompletableFuture?

**Đáp án:** Khi cần cô lập workload, đặc biệt I/O blocking hoặc giới hạn tài nguyên riêng.

**20.** Cách xác nhận một tối ưu có hiệu quả?

**Đáp án:** Chạy cùng workload, so allocation, GC, pool metrics, throughput và p95/p99 latency, đồng thời kiểm tra correctness.

## 11. Tài liệu chính thức và công cụ

- [Oracle Java SE 25 — ThreadMXBean (com.sun.management)](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/ThreadMXBean.html): đo allocation bytes theo thread và kiểm tra capability.
- [Oracle Java SE 25 — Stream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): object streams và primitive specializations.
- [Oracle Java SE 25 — ForkJoinPool](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool, work stealing và monitoring metrics.
- [Oracle Java SE 25 — CompletableFuture](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html): async methods, common pool và overload nhận Executor.
- [Oracle Java SE 25 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): JFR, JMC và công cụ chẩn đoán.
- [Oracle Java SE 25 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html): allocation, GC, CPU, thread stalls và phân tích JFR.
- [Oracle Java SE 25 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/index.html): collector, heap và cách tiếp cận GC tuning.
- [Oracle Java SE 26 — Troubleshooting Memory Leaks](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html): GC logs và dấu hiệu retained memory.
- [OpenJDK JMH](https://github.com/openjdk/jmh): harness dành cho microbenchmark Java.

**Ghi nhớ:** Boxing là một nguồn allocation có thể tránh khi dùng primitive đúng chỗ, nhưng chỉ profiler mới cho biết JIT thực sự tạo bao nhiêu object. JFR và GC logs cho biết allocation site, collection và pause; common pool metrics cho biết tình trạng scheduling nhưng phần lớn chỉ là ước lượng. Đo cùng workload, liên kết các tín hiệu theo timeline và xác minh latency/throughput trước khi kết luận một thay đổi đã tối ưu.