# Epsilon và phép đo: So sánh footprint và chi phí quản lý trên dữ liệu đại diện (Java 11+)

> **Bối cảnh:** Epsilon GC (JEP 318) là bộ thu gom rác **no-op** của HotSpot: cấp phát bộ nhớ nhưng **không thu hồi object heap**. Nó là một công cụ thí nghiệm hữu ích để quan sát chi phí liên quan GC, kiểm tra ngân sách bộ nhớ và đặt một baseline có **0 hoạt động thu gom**, chứ không phải collector thay thế G1 cho server chạy lâu. Bài học chỉ sử dụng những cơ chế vẫn tồn tại trên Java 11 và OpenJDK hiện đại; do `UseEpsilonGC` vẫn là lựa chọn **experimental**, phải xác minh trên đúng JDK/vendor. Mọi phép đo footprint và CPU bên dưới đều phân biệt **quan sát thực tế** với **kết luận có thể suy ra**.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Giải thích Epsilon thực sự làm gì, tại sao nó không thu hồi memory, và hậu quả khi tổng lượng cấp phát vượt `-Xmx`.
2. Phân biệt **live-set footprint**, **heap used**, **heap committed**, **process RSS/working set** và **overhead của GC**.
3. Biết Epsilon là **baseline thí nghiệm**, không thể đọc `heap used` của Epsilon rồi cho rằng đó là “live objects”.
4. Thiết kế **dữ liệu và workload đại diện**: nhiều loại fields, graph references, lifetime ngắn/dài, phân bố kích cỡ và tỷ lệ giữ object.
5. Chạy cùng một chương trình Java dưới **G1** và **Epsilon** với các điều kiện kiểm soát được.
6. Đo elapsed time, process CPU time, GC collection count, GC-reported time và heap usage; hiểu giới hạn mỗi metric.
7. Không nhầm `getCollectionTime()` với **toàn bộ chi phí CPU + barriers + memory management** của collector.
8. Phân biệt **cùng một lượng công việc** với **cùng một trạng thái bộ nhớ sau workload**.
9. Giải thích tại sao Epsilon có thể trông “nhanh” trong một phiên ngắn nhưng thất bại ở tải dài hoặc heap hạn chế.
10. Xây quy trình đo có warm-up, nhiều process forks, phân vị và RSS/GC logs/JFR, tránh đưa ra kết luận từ một lượt chạy.
11. Nhận diện trường hợp nên dùng Epsilon để **test giới hạn tổng allocations**, và khi nào nên dùng heap dump/JFR/G1 để xem live retention.
12. Viết nhận xét so sánh công bằng: nguồn dữ liệu, JVM flags, JDK build, các metric, độ biến thiên, OOM và điều kiện dừng.

## 2. Epsilon hiện nay là gì?

### 2.1. Cơ chế no-op

Epsilon được đưa vào OpenJDK với **JEP 318 trong Java 11**. Cơ chế lõi rất khác G1:

~~~text
                  new Object / new byte[]
                           |
             +-------------+--------------+
             |                            |
          Epsilon                        G1
             |                            |
     Cấp phát trên heap             Cấp phát trên heap
             |                            |
     Không reclaim objects          Young/Mixed collections
             |                            |
     Heap used tích lũy             Objects không còn reachable
     lượng đã cấp phát              có thể được reclaim/reuse
             |                            |
     Hết không gian: OOME           GC tiếp tục đến khi không đủ
     và có thể JVM exit             space/live data quá lớn
~~~

Với Epsilon, khi một object không còn reachable, **heap space của nó không được trả lại để tái sử dụng trong cùng JVM**. Bộ thu gom không có các chu kỳ reclamation của G1/Serial/Parallel. Vì thế Epsilon hữu ích làm **đối chứng** cho một số loại overhead của collector, nhưng không phù hợp với workload tổng cấp phát vượt ngân sách heap.

### 2.2. Trạng thái hỗ trợ, không dùng hướng dẫn lỗi thời

- Trên Java 11, Epsilon là tính năng **experimental**.
- Mã nguồn OpenJDK hiện đại vẫn khai báo `UseEpsilonGC` là flag experimental, nhưng khả dụng thực tế phụ thuộc HotSpot build/vendor và hệ điều hành.
- Đối với HotSpot hỗ trợ Epsilon, khởi chạy bằng **`-XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC`**.
- Không mặc định có Epsilon trên mọi JVM implementation hoặc bản build tối giản.
- Đây không phải **mặc định của JDK**, không được dùng như một collector cho service production sống lâu.
- Không lẫn Epsilon của **HotSpot JVM** với tuỳ chọn `--gc=epsilon` của **GraalVM Native Image**; chúng thuộc runtime/build mode khác nhau.
- Epsilon không phải “bộ thu gom rác thế hệ mới, ít pause hơn mọi collector” mà là **cố tình bỏ thu hồi** để phục vụ thử nghiệm.

**Kiểm khả dụng trên chính JDK định sử dụng**:

~~~bash
java -version
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -Xms192m -Xmx192m -version
~~~

Nếu JVM từ chối flag, ghi nhận **không hỗ trợ** thay vì tự thay bằng tên flag từ JVM khác. Hai lệnh trên đã được chạy thành công với HotSpot OpenJDK 24.0.2 trong môi trường thử; đây không phải bằng chứng mọi bản Java 11/vendor đều có cùng implementation details.

## 3. Đặt đúng câu hỏi: “footprint” nào và “overhead” nào?

Một so sánh có ý nghĩa cần tối thiểu hai mục tiêu **tách riêng**:

1. **Memory footprint**: ứng dụng và JVM sử dụng bao nhiêu bộ nhớ để hoàn thành workload?
2. **Chi phí quản lý bộ nhớ**: chi phí GC/allocator/VM làm tăng CPU, pause, throughput hoặc latency như thế nào?

Không dùng một con số “RAM” để trả lời đồng thời hai câu hỏi.

| Đại lượng | Cách quan sát | Có ý nghĩa gì? | Không được suy ra |
| --- | --- | --- | --- |
| Live set/retained data | After-GC occupancy, heap dump/GC roots | Dữ liệu còn cần giữ | `heap.used` trong Epsilon = live set |
| `heap.used` | `MemoryMXBean.getHeapMemoryUsage().getUsed()` | Used heap tại snapshot | Tất cả used đều reachable |
| `heap.committed` | `MemoryUsage.getCommitted()` | Heap memory committed cho JVM | Bằng RSS hoặc live objects |
| `heap.max` / `-Xmx` | `MemoryUsage.getMax()` | Giới hạn tối đa Java heap | Bằng mức resident thực |
| `nonHeap.used` | `getNonHeapMemoryUsage()` | Một phần JVM non-heap quản lý | Đầy đủ mọi native memory |
| Process RSS/working set | OS monitor, cgroup tools | Các trang nhớ resident của process | Bằng Java heap used |
| Peak RSS | OS process monitor hoặc `/usr/bin/time -v` | Đỉnh resident toàn run (theo OS) | Bằng “GC metadata overhead” |
| GC collection count | `GarbageCollectorMXBean` | Số GC cycles do MXBean báo | Toàn bộ GC management operations |
| GC collection time | `getCollectionTime()` | **Ước lượng accumulated elapsed GC time** | Toàn bộ CPU cost của GC |
| Process CPU time | `OperatingSystemMXBean` HotSpot extension | CPU time tất cả process threads | Chỉ là thời gian GC |
| Elapsed time | `System.nanoTime()` | Thời gian wall-clock của đoạn đo | Độ trễ p99 từng request |
| Allocation rate | Thread allocated bytes, JFR/profiler | Tốc độ tạo objects/bytes | Số objects vẫn còn sống |
| GC pause p95/p99 | JFR/GC logs/tracing | GC stop-the-world duration | End-to-end request p99 |

**Định nghĩa cần ghi ở đầu mọi báo cáo:** “footprint = max RSS trong process run” hoặc “footprint = heap used sau pha làm việc”, và “management overhead = số/elapsed GC + process CPU + pause metrics”. Nếu không ghi, hai bên dễ so sánh hai đại lượng khác nhau.

## 4. Epsilon là baseline nào — và không phải baseline nào?

### 4.1. Có ích để quan sát

- **Không có GC reclamation cycles**: số GC collections trong một fixture bình thường sẽ là 0, giúp lập đối chứng.
- **Giới hạn tổng allocations**: với một phiên hữu hạn, biết tổng cấp phát có thể vượt heap hay không; nếu vượt Epsilon sẽ OOM thay vì tự reclaim.
- **Độ nhiễu từ GC pause**: không có young/full GC như G1, có thể cô lập một số ảnh hưởng GC; những safepoints và chi phí VM khác vẫn có thể xảy ra.
- **Thực nghiệm allocator/heap layout**: quan sát object allocation behavior khi không thu hồi các objects ngắn hạn.
- **Workload rất ngắn với tổng cấp phát biết trước**: trường hợp hiếm có thể đánh giá sự phù hợp, nhưng vẫn phải so với collector mặc định và giới hạn RAM.

### 4.2. Không thể kết luận trực tiếp

- Epsilon nhanh hơn trong một lượt chạy **không** chứng minh nhanh hơn trên production dài hạn.
- “0 GC time” **không** có nghĩa CPU quản lý bộ nhớ/allocator bằng 0.
- `heap.used` của Epsilon cao hơn G1 **không có nghĩa** Epsilon có nhiều live objects hơn; nó giữ cả những objects chết về mặt reachability.
- Khác biệt `heap.used` **không phải** toàn bộ GC metadata overhead hoặc phần trăm memory “lãng phí” của G1.
- Epsilon OOM **không chứng minh memory leak**: một stream xử lý objects ngắn hạn đủ lâu vẫn sẽ OOM vì không reclamation.
- Epsilon không mô phỏng fragmentation/reclamation behavior, evacuation và adaptive sizing của G1 nên không thay thế capacity test production.
- Epsilon có thể thất bại ở **warm-up** trước khi đo chính thức; phải tính allocations của cả vòng đời JVM.

## 5. “Dữ liệu đại diện” là gì?

Một bộ dữ liệu chỉ được gọi **đại diện** khi bảo tồn được những đặc trưng liên quan đến chi phí bộ nhớ và xử lý. Không đủ để tạo một mảng `int[100000]` rồi coi như đại diện cho một API xử lý JSON phức tạp.

### 5.1. Thành phần quan trọng

1. **Cấu trúc object graph**: map, list, các entities liên kết, nested records, indices, cache keys.
2. **Phân bố kích thước**: strings ngắn/dài, arrays nhỏ/lớn, payload percentiles, các giá trị ngoại lệ; đừng chỉ dùng kích cỡ trung bình.
3. **Kiểu dữ liệu**: `String`/UTF-8, byte arrays, primitive fields, nullable fields, collection overhead, boxing nếu có.
4. **Lifetime**: objects sống dưới 1 request, tồn tại qua một batch, hoặc sống trong cache/session suốt process.
5. **Tỷ lệ giữ tham chiếu**: retained objects, bounded cache size và eviction; ảnh hưởng live set.
6. **Cấp phát tạm**: deserialize/transform/serialize, buffers, temporary lists và string concatenations.
7. **Concurrency và burst**: số workers, in-flight requests, batch sizes, queues; ảnh hưởng peak allocation.
8. **Workload mix**: read-heavy, write-heavy, small/large requests, error paths.
9. **Warm-up/JIT/class loading**: tạo nhiều objects trước khi đo; với Epsilon phần đó không thể reclaimed.
10. **Resource envelope**: heap max, CPU quota, cgroup limits, JDK/OS, VM options và input entropy.

### 5.2. Bộ dữ liệu thử trong bài

Chúng ta cố ý dùng một **mẫu cấu trúc đại diện** cho ứng dụng xử lý đơn hàng, **không giả vờ đó là dữ liệu sản xuất**:

| Thành phần | Quy mô | Vai trò |
| --- | ---: | --- |
| `Order.id`, `amountCents` | 6.000 records | Primitive fields |
| `Order.sku` | Một chuỗi mỗi record | String object graph |
| `Order.labels` | 3 nhãn/record | Collection và short Strings |
| `Order.payload` | 1.024/1.152/1.280/1.408 byte | Phân bố kích thước byte arrays |
| `LinkedHashMap<Long,Order>` | 6.000 entries giữ đến cuối | **Retained graph** |
| `byte[20KiB]` | 8.192 operations | **Transient allocation** |
| UTF-8 serialized line | 8.192 operations | String/serialization churn |
| Checksum | Một giá trị cuối | Kiểm công việc có cùng kết quả |

Tổng dung lượng **payload tạm được yêu cầu**: `8.192 × 20.480 bytes = 160 MiB`. Đây là con số **chỉ tính payload của scratch byte arrays**, không bao gồm các arrays of references, headers/alignment, strings, map entries, UTF-8 encoding, compiler/runtime allocations.

**Bộ data này chỉ phù hợp để dạy phương pháp**. Khi làm production benchmark, phải thay kích cỡ/tỷ lệ/lifetime bằng phân bố từ dữ liệu đã ẩn danh và workloads có khả năng tái lập.

## 6. Thiết kế phép thử công bằng

### 6.1. Cùng code và cùng giới hạn tài nguyên

~~~text
        EpsilonFootprintLab.java  (cùng class files)
                        |
                  javac --release 11
                        |
            +-----------+-------------+
            |                         |
      Java HotSpot G1             Java HotSpot Epsilon
      -Xms256m -Xmx256m          -Xms256m -Xmx256m
      -XX:+UseG1GC               -XX:+UnlockExperimentalVMOptions
                                 -XX:+UseEpsilonGC
            |                         |
      6.000 orders               6.000 orders
      8.192 operations           8.192 operations
      160 MiB scratch            160 MiB scratch
            |                         |
      checksum A                 checksum A
      metrics A                  metrics B
            +------------+------------+
                         |
             Đối chiếu theo metric/đơn vị
~~~

**Điều kiện PASS đầu tiên**: số records, operations, requested bytes và checksum **trùng nhau**. Nếu khác, bạn đã đo hai workload khác nhau, không thể so collector.

### 6.2. Biến cần cố định

- JDK build/vendor, JVM flags ngoại trừ collector, bytecode/artifacts, OS, CPU limits, heap max, initial heap, timezone/config không liên quan.
- Dữ liệu được tạo với cùng input seed/record count/array sizes.
- Cùng số lượng operations, thread count và đồng bộ; không trộn batch sizes hoặc feature flags.
- Warm-up strategy và thời điểm bắt đầu/kết thúc đo được mô tả rõ.
- Không cho benchmark cùng lúc tranh CPU/disk hoặc chạy trên host đang tải nặng.
- Chạy **nhiều process JVM độc lập** (forks); nếu chỉ gọi nhiều vòng trong cùng process Epsilon, heap used của vòng trước tích lũy và làm vòng sau không tương đương.
- Có hai workload riêng khi cần: **churn nhỏ sống ngắn** và **retained graph lớn**; Epsilon phản ứng khác nhau do không reclaim.

### 6.3. Vì sao chọn `-Xms=-Xmx` trong demo?

Cố định cả hai ở 256 MiB giúp không bị chi phối quá nhiều bởi việc JVM **mở rộng committed heap** giữa hai lần chạy. Đây là một phép **kiểm soát biến số**, không phải hướng dẫn tuning production.

Hệ quả: `heap.committedMiB=256.0` ở cả hai bên không chứng minh process RSS của hai bên bằng nhau. Committed heap, touched memory pages, resident working set và Java heap used là **các khái niệm khác nhau**. Nếu muốn đo footprint của chính sách sizing động, chạy thêm một kịch bản **`-Xms` thấp** trên cả hai bên, không dùng kết quả của hai kịch bản thay thế nhau.

## 7. Chương trình Java hoàn chỉnh: EpsilonFootprintLab

Ví dụ dưới đây dùng các API có trong Java 11; phần quản lý CPU ở `com.sun.management.OperatingSystemMXBean` là extension có điều kiện và được kiểm `instanceof`. Nó:

1. Giữ 6.000 `Order` trong một `LinkedHashMap`.
2. Mỗi `Order` có primitive fields, String, list nhãn và một payload có kích thước biến thiên.
3. Thực hiện 8.192 operations, mỗi lần cấp phát buffer 20 KiB và tạo một dòng UTF-8.
4. Sử dụng `volatile escape` để các scratch allocations không bị JVM loại bỏ một cách hiển nhiên trong phép đo.
5. Ghi tổng số records/operations/checksum, heap used/committed, non-heap used, GC count/time, elapsed và process CPU.
6. Không dùng `System.gc()` vì Epsilon không reclaim và việc ép GC bên G1 sẽ làm kịch bản khác nhau.

Tạo file **`EpsilonFootprintLab.java`**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class EpsilonFootprintLab {
    private static final int RECORD_COUNT = 6_000;
    private static final int OPERATIONS = 8_192;
    private static final int SCRATCH_BYTES = 20 * 1_024;
    private static final long MIB = 1_024L * 1_024L;
    private static volatile Object escape;

    static final class Order {
        final long id;
        final long amountCents;
        final String sku;
        final List<String> labels;
        final byte[] payload;

        Order(int index) {
            this.id = index;
            this.amountCents = 10_000L + (index * 17L);
            this.sku = "sku-" + index;
            this.labels = Arrays.asList(
                    "channel-" + (index % 7),
                    "region-" + (index % 11),
                    "tier-" + (index % 5));
            this.payload = new byte[1_024 + (index % 4) * 128];
            this.payload[0] = (byte) (index & 127);
        }
    }

    private static long gcCount() {
        long total = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long value = bean.getCollectionCount();
            if (value >= 0) total += value;
        }
        return total;
    }

    private static long gcTimeMs() {
        long total = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long value = bean.getCollectionTime();
            if (value >= 0) total += value;
        }
        return total;
    }

    private static long processCpuTime() {
        java.lang.management.OperatingSystemMXBean bean =
                ManagementFactory.getOperatingSystemMXBean();
        if (bean instanceof com.sun.management.OperatingSystemMXBean) {
            return ((com.sun.management.OperatingSystemMXBean)
                    bean).getProcessCpuTime();
        }
        return -1;
    }

    public static void main(String[] args) throws Exception {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        long beforeCollections = gcCount();
        long beforeGcTime = gcTimeMs();
        long beforeCpu = processCpuTime();
        long started = System.nanoTime();

        Map<Long, Order> retained = new LinkedHashMap<>();
        for (int i = 0; i < RECORD_COUNT; i++) {
            Order order = new Order(i);
            retained.put(order.id, order);
        }

        long checksum = 0;
        for (int i = 0; i < OPERATIONS; i++) {
            Order order = retained.get((long) (i % RECORD_COUNT));
            byte[] transientBuffer = new byte[SCRATCH_BYTES];
            transientBuffer[0] = (byte) order.id;
            transientBuffer[SCRATCH_BYTES - 1] = (byte) (i >>> 3);
            byte[] encoded = (order.sku + ":" + order.amountCents
                    + ":" + i).getBytes(StandardCharsets.UTF_8);
            escape = transientBuffer;
            checksum += (transientBuffer[0] & 255)
                    + (transientBuffer[SCRATCH_BYTES - 1] & 255)
                    + (order.payload[0] & 255)
                    + encoded.length;
        }

        long elapsedNanos = System.nanoTime() - started;
        long afterCpu = processCpuTime();
        MemoryUsage heap = memory.getHeapMemoryUsage();
        MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();

        System.out.println("retained.records=" + retained.size());
        System.out.println("work.operations=" + OPERATIONS);
        System.out.println("work.scratchPayloadMiB="
                + ((long) OPERATIONS * SCRATCH_BYTES / MIB));
        System.out.println("work.checksum=" + checksum);
        System.out.printf(Locale.ROOT, "heap.usedMiB=%.1f%n",
                heap.getUsed() / (double) MIB);
        System.out.printf(Locale.ROOT, "heap.committedMiB=%.1f%n",
                heap.getCommitted() / (double) MIB);
        System.out.printf(Locale.ROOT, "nonHeap.usedMiB=%.1f%n",
                nonHeap.getUsed() / (double) MIB);
        System.out.println("gc.collections.delta="
                + (gcCount() - beforeCollections));
        System.out.println("gc.reportedTimeMs.delta="
                + (gcTimeMs() - beforeGcTime));
        System.out.printf(Locale.ROOT, "work.elapsedMs=%.1f%n",
                elapsedNanos / 1_000_000.0);
        if (beforeCpu >= 0 && afterCpu >= beforeCpu) {
            System.out.printf(Locale.ROOT, "processCpuMs.delta=%.1f%n",
                    (afterCpu - beforeCpu) / 1_000_000.0);
        } else {
            System.out.println("processCpuMs.delta=unavailable");
        }

        if (retained.size() != RECORD_COUNT || checksum <= 0) {
            throw new AssertionError("Dataset was not preserved");
        }
    }
}
~~~

### 7.1. Biên dịch

~~~bash
javac --release 11 EpsilonFootprintLab.java
~~~

Có thể biên dịch bằng chính JDK 11 với `javac EpsilonFootprintLab.java`. Nếu runtime không có HotSpot `jdk.management` extension, code vẫn dùng kiểm `instanceof` khi JVM đáp ứng lớp extension; với runtime thiếu hẳn package/module đó, cần thay metric process CPU bằng công cụ OS ngoài JVM và biên dịch trên JDK hỗ trợ tương ứng.

### 7.2. Chạy G1, giữ cùng heap

~~~bash
java -Xms256m -Xmx256m -XX:+UseG1GC EpsilonFootprintLab
~~~

### 7.3. Chạy Epsilon, giữ cùng heap

~~~bash
java -XX:+UnlockExperimentalVMOptions -Xms256m -Xmx256m -XX:+UseEpsilonGC EpsilonFootprintLab
~~~

**Thứ tự quan trọng:** đặt `-XX:+UnlockExperimentalVMOptions` **trước** `-XX:+UseEpsilonGC` để JVM chấp nhận experimental flag trong bản hỗ trợ.

### 7.4. Kiểm chứng lệnh bằng javac --release 11

Chương trình được biên dịch một lần rồi chạy **trên cùng JDK runtime** trong hai process riêng. Ví dụ dùng JDK HotSpot OpenJDK 24.0.2 để chạy bytecode Java 11. Điều này **kiểm chứng tương thích API/source Java 11**, không có nghĩa đã chạy cùng phép thử trên tất cả các JDK 11 vendors.

Không thêm các JDK flags khác chỉ bên Epsilon hoặc chỉ bên G1. Nếu cần `-Xlog`, ghi rõ do thêm instrumentation và chạy song song cùng mức phù hợp.

## 8. Stdout đã kiểm trên cùng một máy và JDK

### 8.1. G1, heap 256 MiB

~~~text
retained.records=6000
work.operations=8192
work.scratchPayloadMiB=160
work.checksum=2744255
heap.usedMiB=33.7
heap.committedMiB=256.0
nonHeap.usedMiB=4.0
gc.collections.delta=2
gc.reportedTimeMs.delta=3
work.elapsedMs=49.4
processCpuMs.delta=109.4
~~~

### 8.2. Epsilon, heap 256 MiB

~~~text
retained.records=6000
work.operations=8192
work.scratchPayloadMiB=160
work.checksum=2744255
heap.usedMiB=173.6
heap.committedMiB=256.0
nonHeap.usedMiB=3.9
gc.collections.delta=0
gc.reportedTimeMs.delta=0
work.elapsedMs=55.5
processCpuMs.delta=140.6
~~~

### 8.3. Thêm một lượt thử với G1, heap 96 MiB

~~~text
retained.records=6000
work.operations=8192
work.scratchPayloadMiB=160
work.checksum=2744255
heap.usedMiB=55.3
heap.committedMiB=96.0
nonHeap.usedMiB=4.0
gc.collections.delta=3
gc.reportedTimeMs.delta=7
work.elapsedMs=49.1
processCpuMs.delta=125.0
~~~

**Điều cần hiểu:** Đây là **ba stdout có thật của một lượt chạy trên một JVM HotSpot**, **không phải expected values cố định**. Các số `heap.used`, `nonHeap.used`, `gc.*`, `elapsedMs`, `processCpuMs` thay đổi theo JDK, CPU, OS, GC heuristics và JIT/scheduling. Những dòng `retained.records=6000`, `work.operations=8192`, `work.scratchPayloadMiB=160`, `work.checksum=2744255` là xác nhận **cùng logic fixture** và nên ổn định nếu mã/input không đổi.

**Đặc biệt:** Epsilon trong lượt thử này mất `55.5 ms`, còn G1 `49.4 ms`. Điều đó **không chứng minh Epsilon chậm hơn G1 trong mọi workload**, cũng như một lượt thử ngược lại không chứng minh nó luôn nhanh hơn. Single-run CPU time còn chứa code/JIT/runtime overhead, số lượng GC và các nền tảng không hoàn toàn độc lập.

## 9. Phân tích số liệu mà không nhầm khái niệm

Từ hai lượt chạy heap 256 MiB:

| Metric | G1 (đã chạy) | Epsilon (đã chạy) | Kết luận hợp lệ |
| --- | ---: | ---: | --- |
| Retained records | 6.000 | 6.000 | Cùng lượng dữ liệu được giữ sống |
| Operations | 8.192 | 8.192 | Cùng số thao tác |
| Scratch payload được yêu cầu | 160 MiB | 160 MiB | Cùng tổng byte payload tạm |
| Checksum | 2.744.255 | 2.744.255 | Kết quả xử lý tương đồng |
| Heap max | 256 MiB | 256 MiB | Cùng trần heap |
| Heap committed | 256.0 MiB | 256.0 MiB | Cùng mức committed vì `-Xms=-Xmx` |
| Heap used snapshot | 33.7 MiB | 173.6 MiB | Epsilon giữ cả allocations đã mất reachability |
| Non-heap used snapshot | 4.0 MiB | 3.9 MiB | Gần nhau trong lượt này, không phải mọi native memory |
| GC collections delta | 2 | 0 | Epsilon không có reclamation cycles |
| GC reported ms delta | 3 | 0 | Giá trị MXBean, không phải toàn bộ overhead |
| Elapsed work ms | 49.4 | 55.5 | **Một lượt**, chưa đủ suy ra nhanh/chậm |
| Process CPU ms delta | 109.4 | 140.6 | Gồm mọi thread/process work, không chỉ GC |

**Cảnh báo cách so sánh:** `173.6−33.7≈139.9 MiB` là chênh **heap used tại snapshot**; **không phải** “GC metadata của G1 tốn ít hơn Epsilon 140 MiB”, cũng không phải “Epsilon giữ thêm 140 MiB objects còn sống”. Phần lớn khác biệt đến từ việc G1 **đã tái sử dụng/reclaim** memory của các allocations không còn cần, còn Epsilon thì không.

### Ba bài học rút ra

1. **Cùng 160 MiB transient payload** có thể hoàn tất trên heap 96 MiB với G1 vì heap được **tái sử dụng**. Tổng bytes allocated trong cả run không đồng nghĩa peak retained bytes.
2. Epsilon không reclaim nên `heap.used` tiếp tục phản ánh **tổng chi phí allocations tích lũy** trong JVM, kể cả những objects đã chết.
3. **0 GC collections ≠ 0 total management overhead**, vì CPU của allocator, object initialization, heap commitment, safepoints và nền VM khác vẫn có chi phí.

## 10. “Chi phí quản lý” gồm những gì?

Một collector như G1 có thể phát sinh:

- **STW pauses** để thực hiện công việc GC;
- **Concurrent/background GC work** và CPU competition với threads ứng dụng;
- **Write/read barriers**, card/remembered-set updates, marking và reference processing;
- **Copy/evacuation** những live objects, promotion và region metadata;
- **Heap resizing/commit/uncommit**, theo GC heuristics;
- **Per-thread/per-heap accounting** liên quan allocator, safepoint coordination;
- **GC thread stacks/native memory** và auxiliary data structures.

Epsilon không làm công việc reclaim tương ứng nhưng vẫn có hoạt động quản lý **cấp phát**, tracking heap usage, VM runtime, exception handling, class metadata và memory commit. Không quảng bá Epsilon là “zero-overhead Java VM”.

### 10.1. Vì sao MXBean collection time chưa đầy đủ?

`GarbageCollectorMXBean.getCollectionTime()` trả **thời gian thu gom tích lũy xấp xỉ**, có thể `-1` nếu undefined. Với collector concurrent, cách tích lũy và mức bao phủ GC CPU khác nhau theo implementation. Nó không tự đo:

- Overhead của write barriers trong mutator;
- Tác động cache/memory bandwidth;
- GC threads concurrent CPU time độc lập ở mọi pha;
- Tác động indirect lên JIT/object layout/allocator;
- Request latency p99 hoặc pause max.

Vì thế **không lấy** chênh `work.elapsedMs` trừ `gc.reportedTimeMs` làm “chi phí thuần business logic”, hay suy `gc.reportedTimeMs=0` là “chi phí allocator bằng 0”.

### 10.2. Vì sao process CPU time không trừ ra được “GC CPU” trực tiếp?

`getProcessCpuTime()` là CPU time của **toàn JVM process**: threads ứng dụng, JIT/compiler, GC, class loading và nhiều thành phần runtime khác. Trong một lượt ngắn, JIT/OS scheduling có thể chi phối mạnh. Muốn ước lượng overhead chính xác hơn, cần nhiều forks/warmups, đo JFR/GC logs đúng loại và có metric CPU của GC threads khi công cụ hỗ trợ.

### 10.3. Epsilon không có pauses GC nhưng vẫn có latency

Epsilon tránh collection pauses, nhưng request vẫn có thể bị chậm vì scheduling, locks, I/O, memory page faults, JIT/safepoints, hoặc sắp cạn heap. Trong một workload ngắn, không nên quy toàn bộ p99 khác biệt cho GC.

## 11. Heap used, committed và resident footprint không giống nhau

~~~text
MemoryMXBean.getHeapMemoryUsage()
    used       -> byte trong Java heap đang được dùng
    committed  -> byte heap JVM đã committed
    max        -> giới hạn trên (có thể -1 nếu không xác định)

OS/process memory
    RSS / working set -> các trang resident ở RAM
    virtual memory    -> address space / commit theo semantics OS
    cgroup usage      -> memory được accounting trong container

JVM ngoài heap
    metaspace, code cache, thread stacks, direct buffers,
    JIT/GC native structures, JNI allocations...
~~~

Trong demo, cả hai dùng `-Xms256m -Xmx256m` nên committed là `256 MiB`. Chênh heap used không thể biến trực tiếp thành chênh RSS. Một process có heap committed 256 MiB có thể chỉ thực sự **touch** một phần trang memory; mặt khác OS còn đếm non-heap và các loại resident memory khác.

### 11.1. Đo RSS/peak RSS bên ngoài JVM

Trên Linux có GNU `/usr/bin/time`:

~~~bash
/usr/bin/time -v java -Xms256m -Xmx256m -XX:+UseG1GC EpsilonFootprintLab
/usr/bin/time -v java -XX:+UnlockExperimentalVMOptions -Xms256m -Xmx256m -XX:+UseEpsilonGC EpsilonFootprintLab
~~~

Đọc **Maximum resident set size** và **Elapsed (wall clock) time**, nhưng để benchmark CPU/latency chính xác hơn, tách startup/JIT/warm-up và dùng công cụ chuyên dụng.

**Lệnh tham khảo**, chưa được thử trên Linux trong lượt thí nghiệm Windows/PowerShell của bài. `/usr/bin/time -v` có thể không tồn tại trên mọi OS/distro. Trên Linux container, đọc thêm `/proc/<pid>/status` hoặc cgroup files tùy phiên bản để kiểm memory limit/pressure.

Trên Windows, với PID của Java process đang chạy:

~~~powershell
Get-Process -Id <PID> |
    Select-Object Id, ProcessName, WorkingSet64, PeakWorkingSet64, PrivateMemorySize64
~~~

**Lệnh minh họa**: phải dùng PID thật, không gõ literal `<PID>`; startup process cần tồn tại đủ lâu để quan sát. Các số này thuộc **process memory ở OS**, không nên coi bằng Java heap. `PeakWorkingSet64` phản ánh peak working set theo Windows, có thể không so trực tiếp với `Maximum resident set size` Linux.

### 11.2. Tránh chế độ pretouch khi bạn chưa định nghĩa footprint

Nếu bật `-XX:+AlwaysPreTouch`, JVM có thể touch nhiều trang heap ngay từ startup và làm **RSS tăng** kể cả khi `heap.used` nhỏ. Nó có thể hữu ích khi chủ đích đo latency sau startup, nhưng sẽ đổi định nghĩa footprint. Hãy hoặc bật ở **cả hai collector** và ghi rõ, hoặc không bật ở cả hai.

### 11.3. Memory limit trong container

Nếu cgroup limit quá thấp so với heap + native memory + OS overhead, container có thể bị OOM kill trước khi `MemoryMXBean` báo heap đạt max. Không tăng `-Xmx` để “cho Epsilon đỡ OOM” mà không xem memory limit/RSS và mục đích phép đo.

## 12. Tại sao Epsilon có thể OOM dù chương trình không leak?

Một chương trình xử lý từng request:

~~~java
for (int request = 0; request < totalRequests; request++) {
    byte[] buffer = new byte[1024 * 1024];
    process(buffer);
    // buffer không còn cần sau request.
}
~~~

**Đoạn minh họa**: `process` là method giả định, không phải ví dụ độc lập. Với collector reclaim, các buffers đã hết reachable có thể được thu hồi và heap reused. Với Epsilon, các vùng bộ nhớ cấp cho buffers **không được reclaim** dù reference đã biến mất, nên tổng allocations tích lũy cuối cùng có thể vượt `Xmx`.

### Mẫu OOM có kiểm soát

Nếu muốn xác nhận giới hạn, **chỉ chạy process test riêng**, không chạy service thật:

~~~bash
java -XX:+UnlockExperimentalVMOptions -Xms96m -Xmx96m -XX:+UseEpsilonGC EpsilonFootprintLab
~~~

Vì chương trình yêu cầu **160 MiB scratch payload** chưa tính object graph và runtime allocations, heap 96 MiB **không đủ cho Epsilon**. JVM có thể báo `OutOfMemoryError` và thậm chí kết thúc process theo chính sách của collector/runtime. **Không dự đoán một stack trace, mã lỗi hay stdout cố định**; kiểm exit status và logs của process thử. Lệnh 96 MiB Epsilon ở đây được đưa như **test gợi ý**, không nhận là đã chạy.

**Chú ý:** Epsilon có thể dùng chính sách fail/exit khi OOME. Không bao quanh bằng `catch (OutOfMemoryError)` rồi kỳ vọng luôn khôi phục được cả JVM và benchmark. Chạy ở sandbox/subprocess có memory quota, không dùng workload này cho JVM chứa dữ liệu quan trọng.

## 13. Epsilon không thay thế kiểm thử live-set leak

### Dấu hiệu khác nhau

| Dấu hiệu | G1/collector reclaim | Epsilon |
| --- | --- | --- |
| Temporary objects không còn reachable | Có thể reclaim | Không reclaim |
| Tăng heap used trong quá trình chạy | Có thể là churn hoặc retention | **Luôn** tích lũy allocations không reclaimed |
| Heap used giảm sau GC | Có thể | Không có collection để giảm |
| OOM sau nhiều requests | Có thể leak/insufficient heap/burst | Có thể đơn giản vì tổng allocations vượt Xmx |
| Dùng heap dump tìm GC roots | Phù hợp khi cần retained graph | Không dùng Epsilon heap used như live-set proxy |
| Xác minh “chưa vượt allocation budget” trong job ngắn | Cần metrics allocations | Có thể thử Epsilon budget test có kiểm soát |

### Khi muốn đo live set thật

1. Sử dụng collector reclaim bình thường, xác định sau-GC occupancy và workload baseline.
2. Theo dõi xu hướng qua nhiều GC cycles tại cùng tải.
3. Nếu nghi retained data không hợp lệ, dùng heap dump có kiểm soát để tìm dominators/GC roots.
4. Kết hợp allocation profiler/JFR để biết objects được tạo ở đâu, **khác** với ai đang giữ object sống.
5. Chỉ dùng Epsilon để thử **ngân sách tổng allocated bytes/hiệu năng không GC**, không dùng nó làm phép đo “bộ nhớ leak”.

## 14. Đo trong nhiều JVM forks, không chỉ nhiều vòng trong một process

Với G1, nhiều vòng workload có thể warm JIT và reuse heap. Với Epsilon, cùng số vòng đó sẽ làm **heap used tăng liên tục** vì không reclaim. Vì thế:

- Phép đo **một process** chỉ thích hợp minh họa, không chứng minh throughput/p99.
- Muốn thống kê ổn định, chạy **nhiều JVM processes độc lập**; mỗi process bắt đầu với heap mới.
- Nếu muốn warm-up trước measurement, phải tính memory đã tiêu trong warm-up của Epsilon vào tổng budget của fork.
- Warm-up bên Epsilon có thể không đủ headroom cho nhiều iterations; giảm workload **cho cả hai collector**, tăng heap **cả hai**, hoặc thiết kế benchmark single-shot trên số operations cố định.
- Đổi `-Xmx` riêng cho Epsilon để nó sống lâu hơn rồi tuyên bố “footprint như nhau” sẽ làm so sánh sai.
- Trong mỗi fork, xác nhận **checksum/operations/retained record count** trước khi so metric.
- Thống kê median, p90/p95, range, outliers, confidence interval phù hợp; loại bỏ các run thiếu dữ liệu/OOM có ghi rõ.

### Ví dụ kế hoạch chạy đúng

~~~text
JDK:       Cùng một OpenJDK HotSpot build
CPU:       Cùng quota / cùng máy, ít tải ngoài
Dataset:   6.000 orders, 8.192 operations
Heap:      Xms=Xmx=256 MiB
Modes:     G1 / Epsilon
Order:     Xen kẽ G1,Epsilon,Epsilon,G1 qua nhiều forks
Runs:      Ví dụ 10 JVM forks mỗi mode
Validation: checksum khớp; nonzero exits không bỏ qua
Metrics:   elapsed, processCPU, gc count/time, heap used,
           peak RSS, GC log pauses; thêm latency hist nếu có request
Report:    median/range và environment đầy đủ
~~~

Đây là **kế hoạch thí nghiệm**, không phải kết quả 10 forks đã đo. Các con số số-forks/khối lượng workload chỉ là tham số bạn chọn theo mục tiêu và thời gian/độ tin cậy.

### Khi nào nên dùng JMH?

Với microbenchmarks lặp lại, có thể dùng **OpenJDK JMH** để tránh nhiều bẫy JIT/dead-code elimination/warm-up. Tuy nhiên Epsilon có ngân sách cấp phát **không được reclaim**, nên cấu hình benchmark chạy lặp phải giới hạn tổng allocations trong mọi fork. JMH cũng không tự biến microbenchmark thành workload đại diện cho latency và memory footprint của một application hoàn chỉnh.

## 15. Thử phân bố dữ liệu, không chỉ một kích cỡ

Nếu production có 90% request nhỏ và 10% request lớn:

- Tạo hai nhóm dữ liệu với trọng số tương ứng;
- Ghi distribution payload p50/p95/p99 chứ không chỉ mean;
- Giữ tỷ lệ sessions/cache objects sống lâu;
- Đo requests/s tương đương, deadline/concurrency và retries;
- Thêm error paths có allocation khác success path;
- Nếu cần, thử riêng max payload/burst scenario;
- Đảm bảo input có tính tái lập (seed, fixture version/checksum).

**Một tập dữ liệu đại diện cho heap footprint cũng phải phản ánh retention**, không chỉ input records. Một chương trình chỉ đọc file rồi vứt objects sẽ khác một server giữ cache 3 giờ.

### Biến thiên kích cỡ và object headers

Ví dụ hai arrays có payload `1.024` và `1.408` byte không nhất thiết chỉ khác 384 byte heap footprint nếu xét object headers, alignment và collection references. Mọi con số payload bytes được yêu cầu trong demo chỉ là **lower bound về bytes của arrays đó**, không phải total process allocated bytes.

## 16. Phân tích dữ liệu sau khi ghi ra CSV

Bạn có thể tổng hợp từ nhiều forks thành bảng:

| fork | collector | xmxMiB | checksum | elapsedMs | cpuMs | gcCount | gcTimeMs | heapUsedMiB | peakRssMiB |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | G1 | 256 | 2744255 | 49.4 | 109.4 | 2 | 3 | 33.7 | *cần OS đo* |
| 1 | Epsilon | 256 | 2744255 | 55.5 | 140.6 | 0 | 0 | 173.6 | *cần OS đo* |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

**Dòng fork=1 là số từ thí nghiệm thực**, nhưng chưa đo peak RSS, nên để **cần OS đo** thay vì tự gán số ảo. Các lượt sau phải được chạy thật trước khi tính thống kê. Không nội suy RSS từ heap used.

Khi so median latency hay CPU:

- Dùng cùng tiêu chuẩn lọc outliers đã công bố;
- Không chọn riêng một run nhanh nhất;
- Report cả **OOM/failures** thay vì loại những run xấu;
- Phân biệt process CPU milliseconds với wall elapsed; CPU tổng nhiều threads có thể lớn hơn elapsed;
- Dùng JFR/GC logs nếu mục tiêu là pauses hoặc pha GC cụ thể;
- Nói rõ metric **không khả dụng** nếu OS/JMX không cung cấp, thay vì điền 0.

## 17. JFR/GC logs để bổ trợ CPU, pause và overhead

Trên Java 11+ dùng **Unified JVM Logging**:

~~~bash
java -Xms256m -Xmx256m -XX:+UseG1GC -Xlog:gc*=info EpsilonFootprintLab
java -XX:+UnlockExperimentalVMOptions -Xms256m -Xmx256m -XX:+UseEpsilonGC -Xlog:gc*=info EpsilonFootprintLab
~~~

**Lệnh minh họa**, chưa chạy riêng chế độ `-Xlog:gc*=info` trong bài. Tùy collector, Epsilon có thể in allocation/heap messages chứ không có GC collection pause; G1 có thể in Young GC pauses. Không áp dụng cú pháp logging thế hệ `-XX:+PrintGCDetails` của Java 8 như một phương pháp chủ đạo cho Java 11+.

### Dùng JFR khi cần timeline

~~~bash
java -Xms256m -Xmx256m -XX:+UseG1GC -XX:StartFlightRecording=filename=g1.jfr,duration=30s,settings=default EpsilonFootprintLab
~~~

**Đoạn minh họa:** trên JDK/HotSpot hiện đại, `-XX:StartFlightRecording=...` là cách thông dụng; tùy thời lượng chương trình rất ngắn, recording có thể không bao phủ đủ 30 giây trước khi JVM kết thúc. Trong thực nghiệm, đặt recording stop/dumponexit hợp lý hoặc tăng workload một cách **có kiểm soát**; không tuyên bố file output sẽ luôn có nếu lệnh trên chạy xong trong vài milliseconds.

Dữ liệu có thể quan tâm:

- `jdk.GarbageCollection`, `jdk.GCPhasePause` cho cycles/pauses;
- `jdk.CPULoad`, `jdk.ThreadCPULoad` và execution samples cho CPU;
- Allocation-related events theo configuration/JDK;
- `jdk.GCHeapSummary` cho heap snapshots khi có;
- P99 latency do application metrics hoặc custom duration events.

**Không mặc định mọi JFR event đang bật.** Và không dùng Epsilon để tạo baseline “không có mọi JVM safepoint” chỉ vì không thu gom.

## 18. Bốn kịch bản để giải thích kết quả trái ngược

### 18.1. Thời gian sống ngắn, churn lớn, live set nhỏ

Một service xử lý 10.000 requests/s, mỗi request tạo 100 KiB objects tạm. G1 có thể reuse memory rất hiệu quả; Epsilon sẽ tiêu thụ tích lũy và OOM nếu chạy đủ lâu. `heap.used` Epsilon cao **không phải leak**.

**Phù hợp:** dùng Epsilon cho một **run rất ngắn được định budget**, và dùng G1 production để đo throughput/p99.

### 18.2. Job cực ngắn, gần như không tạo garbage

Một batch xử lý vài trăm records, tổng allocations thấp hơn headroom rất nhiều và JVM kết thúc ngay sau job. Epsilon có thể là baseline đo chi phí **không GC reclamation**. Nhưng startup/JIT/I/O có thể vẫn chi phối; phải so bằng dữ liệu thực, không khẳng định lợi ích sẽ tồn tại.

### 18.3. Retained graph lớn, churn vừa

Ứng dụng giữ cache lớn và mỗi request tạo ít data tạm. G1 vẫn cần duy trì metadata/cycle behavior và có ít headroom cho workload; Epsilon có thể OOM sớm nếu total allocations tích lũy vượt max. Phải giới hạn lifetime/cache và đo sau-GC occupancy. **Không chọn collector dựa chỉ vào tỷ lệ retained heap.**

### 18.4. Nghi memory leak

`heap used` G1 sau GC tăng từ 2 → 3 → 4 GiB khi workload ổn định; Epsilon cũng tăng. Epsilon **không phân biệt** giữa leak và churn; cần heap dump/GC roots, allocation profiling và phân tích ownership. Nên điều tra retained graph thay vì gọi mọi byte do Epsilon giữ là leak.

## 19. Khi không nên dùng Epsilon

- Backend web/service chạy nhiều giờ hoặc vô thời hạn;
- Workload có tổng allocated bytes khó dự đoán;
- Benchmark bắt buộc nhiều iterations/forks không đủ heap;
- Hệ thống có memory limit chặt hoặc thiếu guardrail OOM;
- Cần đo **live set**, retained size, object reachability hoặc GC effectiveness;
- Muốn chọn collector cho production bằng kết luận một run;
- Muốn đo chính xác toàn GC management overhead chỉ bằng `getCollectionTime`;
- JVM vendor không cung cấp Epsilon hoặc experimental flags bị cấm;
- Môi trường nhiều ứng dụng quan trọng cùng process;
- Muốn tránh mọi JVM safepoint hay mọi loại latency chứ không chỉ GC reclamation;
- Cần kiểm throughput dài hạn với allocation churn.

### Quy tắc vận hành

**Chỉ bật Epsilon trong JVM chạy thử độc lập, dữ liệu đã chuẩn hóa, heap và thời gian giới hạn, với điều kiện dừng rõ ràng.** Khi chuyển sản phẩm sang collector thực, dùng load test với chính collector đó.

## 20. Kiểm chứng memory pressure mà không gây hại cho dịch vụ

Nếu dùng Epsilon để xác minh job có tổng allocations nằm dưới budget:

1. Chạy bản sao của job trong sandbox/subprocess;
2. Chỉ cấp dữ liệu ẩn danh và tải thử có giới hạn;
3. Chọn `-Xmx` phù hợp tài nguyên OS/container, có memory cap và timeout ngoài JVM;
4. Lưu stdout/stderr/exit code;
5. Không `catch (OutOfMemoryError)` rồi tiếp tục xử lý như thể JVM ổn;
6. Test success path và failure path; trả exit status fail cho CI khi OOM;
7. Không đọc “Epsilon OOM” như bằng chứng memory leak trong business code;
8. Xác nhận kết quả trên G1/collector sản xuất trước khi thay đổi production memory sizing.

**Đừng thử ép OOM trong một JVM production** để biết mức footprint. Heap dump/GC logs/JFR an toàn hơn khi cần thông tin trên service thật, nhưng cũng cần đánh giá overhead và bảo vệ artifact.

## 21. Những sai lầm dễ gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Epsilon = garbage collector nhanh nhất.” | No-op không reclaim; workload dài sẽ OOM | Coi là experimental benchmark baseline |
| “0 GC count nghĩa runtime không có overhead.” | Allocation/JIT/OS/safepoint vẫn tốn | Đo process CPU, elapsed, RSS và GC phases |
| “Epsilon heap used = live set.” | Chứa cả garbage đã mất reachability | Dùng after-GC occupancy/heap dump với GC reclaim |
| “Chênh heap used = GC metadata overhead.” | Phần lớn là khác biệt reclaim | Định nghĩa footprint và overhead riêng |
| “Heap committed bằng RSS.” | Commit khác resident page set | Đo RSS qua OS |
| “-Xms=-Xmx chứng minh RAM dùng bằng nhau.” | Chỉ cùng committed heap size | Đo peak RSS |
| “Một run đủ kết luận performance.” | JIT/CPU/scheduler noise cao | Forks, warmup, distributions |
| “CPU time là GC CPU.” | Gồm tất cả JVM threads | Kết hợp JFR/GC logs/CPU profile |
| “GC MXBean time là total GC overhead.” | Là elapsed approximation, không bao phủ mọi CPU/barriers | Ghi giới hạn metric |
| “G1 OOM còn Epsilon không OOM nếu heap cùng max.” | Epsilon không reclaim | Thử memory budget có giới hạn |
| “Epsilon OOM = leak.” | Tổng allocations có thể chỉ là churn | Phân biệt allocation và retention |
| “Số allocated bytes = array payload bytes.” | Headers, alignment, Strings, collections | Đo heap/thread allocations khi cần |
| “Bật Epsilon trên mọi JDK giống nhau.” | Experimental + vendor differences | Verify exact runtime flags |
| “--gc=epsilon dùng được trên HotSpot java.” | Là flag Native Image, không phải HotSpot | Dùng -XX:+UseEpsilonGC khi phù hợp |
| “G1 dùng heap 33.7 MiB tức chỉ còn 33.7 MiB live.” | Heap used tức thời có garbage | Xem after-GC trend |
| “Warm-up của Epsilon được GC sau mỗi vòng.” | Không reclaim | Chia budget cho toàn fork |
| “Tăng Xmx riêng Epsilon để kết quả đẹp hơn.” | Đổi biến thực nghiệm | Giữ resource envelope như nhau |
| “Không GC nghĩa không có OOME.” | Heap vẫn có hard max | Bounded total allocations |
| “Đo peak RSS bằng heap MXBean.” | Không cùng định nghĩa | OS monitor / cgroup |
| “Benchmark chưa ghi exit code nhưng vẫn PASS.” | OOM hoặc failure có thể bị che | Kiểm checksum, outputs, exit status |

## 22. Checklist QA phép đo

- [ ] Ghi rõ Java version/vendor/OS/CPU/cgroup/collector flags.
- [ ] Epsilon có thực sự được JVM chấp nhận ở mode experimental?
- [ ] Cùng class files, cùng record counts và operations?
- [ ] Có dataset distribution/retention phù hợp câu hỏi?
- [ ] Cùng `-Xms/-Xmx` và resource limits?
- [ ] Checksum business output trùng nhau và không bỏ qua OOM?
- [ ] Tách tổng scratch payload bytes khỏi **total allocated heap bytes**?
- [ ] Tách used, committed, max, non-heap, RSS/peak RSS?
- [ ] Có GC count/time và ghi rõ semantics MXBean?
- [ ] Có process CPU/elapsed với cùng measurement boundaries?
- [ ] Đã xét JIT/warm-up và GC work/CPU contention?
- [ ] Dùng nhiều independent JVM forks nếu muốn suy luận performance?
- [ ] Epsilon warm-up không làm heap tích lũy vượt budget?
- [ ] Có time series khi muốn phân tích heap behavior?
- [ ] Không coi single-run stdout là benchmark kết luận?
- [ ] Có benchmark production-like trên collector thật trước rollout?
- [ ] Ghi lại OOM, non-zero exits, timeout và lý do loại runs?
- [ ] File JFR/heap dump/log không chứa dữ liệu nhạy cảm công khai?

## 23. Ma trận test để tái lập

| Bài kiểm thử | Thiết kế | Điều kiện PASS |
| --- | --- | --- |
| Source compatibility | `javac --release 11` | Compile thành công |
| Same workload G1/Epsilon | 6.000 records, 8.192 operations | Checksum bằng nhau |
| Same requested payload | 8.192×20 KiB | In 160 MiB cả hai |
| G1 với 256 MiB | `-Xms256m -Xmx256m` | Process thành công |
| Epsilon với 256 MiB | Experimental flag đúng thứ tự | Process thành công |
| G1 với 96 MiB | Giữ code/input | Process thành công trong runtime thử |
| Epsilon bounded OOM | Heap quá nhỏ cho tổng cấp phát | Ghi lỗi/exit status, không chạy production |
| GC MXBean | Beans có hoặc thiếu count/time | Không crash với giá trị -1 |
| OS MXBean extension | Instance hỗ trợ/không | In số CPU hoặc unavailable |
| Stable deterministic outputs | G1 vs Epsilon | 6.000 / 8.192 / 160 / 2.744.255 |
| Runtime metrics | Multiple forks | Không assert fixed ms/heap numbers |
| RSS monitoring | Linux/Windows tool | Có measured peak RSS ngoài JVM |
| Native memory | Container memory metrics | Không đồng nhất với Java heap |
| Dataset retention | Giữ `LinkedHashMap` | Count cuối chính xác |
| Temporary churn | `volatile escape` | Buffer allocations không bị tối ưu bỏ một cách hiển nhiên |
| GC pause impact | GC logs/JFR khi được bật | Có time window và event settings |
| Load profile representative | Thay distribution/threads | Metadata đủ tái lập |
| Security | Dùng data ẩn danh | Không lộ PII/credentials |
| CI failure | Non-zero exit/OOM/timeout | Job báo thất bại, không giả pass |

**Không dùng bảng này làm khẳng định mọi JDK sẽ có kết quả GC count=2 hay Epsilon elapsed=55.5 ms.** Giá trị cố định chỉ thuộc logic fixture; performance metrics phụ thuộc môi trường.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao Epsilon không thu gom mà lại gọi là GC?

Vì nó là một implementation của giao diện collector trong HotSpot nhằm xử lý **allocation** nhưng **cố tình không reclamation**. Nó phục vụ thử nghiệm/kiểm tra ngân sách, không phải collector sản xuất thông thường.

**Câu 2.** Có nên gọi chênh 173.6−33.7 MiB là “140 MiB metadata của GC”?

**Không.** Đó là chênh heap used sau cùng workload, phần lớn vì Epsilon **không reclaim temporary allocations** còn G1 có thể làm vậy.

**Câu 3.** Cả hai heap committed 256 MiB thì RSS có bằng nhau?

**Không bắt buộc.** Committed khác resident, còn JVM có non-heap/native memory khác.

**Câu 4.** Tại sao Epsilon OOM có thể xảy ra dù retained records chỉ 6.000?

Vì Epsilon cũng giữ heap space cho **tất cả temporary buffers/Strings đã cấp phát** dù references không còn.

**Câu 5.** `GarbageCollectorMXBean.getCollectionTime()==0` có chứng minh tổng chi phí quản lý là 0?

**Không.** Nó chỉ nói về reported elapsed collection time, không bao phủ mọi CPU, allocator/barriers, safepoints hoặc OS overhead.

**Câu 6.** Epsilon mất 55.5 ms và G1 49.4 ms ở một lượt, có thể chọn G1 vì “nhanh hơn 12.3%” không?

**Không.** Một run quá ít để kết luận; cần forks và thống kê, đồng thời đo latency/CPU/footprint theo đúng mục tiêu.

**Câu 7.** Khi nào Epsilon có ích cho CI?

Khi chạy **job bounded** trong process độc lập để xác nhận ngân sách tổng allocation không vượt giới hạn đã định, với OOM/exit status được coi là failure.

**Câu 8.** Khi nào nên dùng heap dump thay vì Epsilon?

Khi cần biết **object nào đang giữ dữ liệu và qua reference nào**, tức retained graph và GC roots.

**Câu 9.** Muốn đo footprint production, vì sao cần RSS/cgroup?

Vì heap used không bao gồm mọi native memory, process code/cache/stacks và các trang resident thật ở OS.

**Câu 10.** Tại sao phải ghi JDK build và cờ experimental?

Epsilon không phải default/portable collector trên mọi JVM; flags, availability và behavior có thể khác giữa builds/versions.

**Câu 11.** Có thể chạy 1.000 lần cùng workload trong một JVM Epsilon như G1 không?

Chỉ khi **tổng allocations của toàn bộ 1.000 lần vẫn nằm trong heap**, vì Epsilon không reclaim giữa các vòng. Dùng independent forks nếu muốn so nhiều iterations.

**Câu 12.** Làm sao định nghĩa dataset đại diện khi không dùng dữ liệu sản xuất thô?

Dùng fixture đã ẩn danh hoặc sinh dữ liệu với **cùng schema, distribution, lifetime, workload mix, concurrency và retention policy** được mô tả rõ; tránh copy PII/credentials vào benchmark artifacts.

## 25. Tài liệu tham khảo chính thức/còn áp dụng

1. [OpenJDK JEP 318 — Epsilon: A No-Op Garbage Collector](https://openjdk.org/jeps/318): mô hình no-op GC, trường hợp dùng, giới hạn và OOME.
2. [Oracle Java 11 Release Notes — Epsilon](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html): xác nhận JEP 318 được đưa vào Java 11 như collector experimental.
3. [OpenJDK current source — UseEpsilonGC flag](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/gc_globals.hpp): flag experimental vẫn tồn tại trong mã nguồn OpenJDK hiện đại; không thay việc kiểm thực tế build.
4. [Oracle Java 11 — MemoryMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryMXBean.html): Java heap và non-heap snapshots.
5. [Oracle Java 11 — MemoryUsage](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryUsage.html): `used`, `committed`, `max`.
6. [Oracle Java 11 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): collections count/time, `-1` khi không hỗ trợ, collection elapsed time không bao trùm mọi overhead.
7. [Oracle Java 11 — OperatingSystemMXBean HotSpot extension](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): process CPU time và giới hạn availability.
8. [Oracle Java 11 — Monitoring and Management Guide](https://docs.oracle.com/en/java/javase/11/management/using-platform-mbean-server-and-platform-mxbeans.html): dùng platform MXBeans/JMX.
9. [Oracle JDK 27 — Introduction to Garbage Collection Tuning](https://docs.oracle.com/en/java/javase/27/gctuning/introduction-garbage-collection-tuning.html): quan hệ throughput/latency/footprint, overhead GC.
10. [Oracle JDK 26 — G1 GC Tuning](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html): G1 reclaim/GC CPU, trade-off pause/throughput.
11. [Oracle JDK 27 — java command / VM flags](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `-Xmx`, `-Xms` và logging/VM options cho runtime hiện đại.
12. [OpenJDK JMH](https://github.com/openjdk/jmh): benchmark harness cho Java với warm-up/forks, có giới hạn riêng khi đo no-op collector.
13. [GraalVM Native Image Memory Management](https://docs.oracle.com/en/graalvm/jdk/25/docs/reference-manual/native-image/optimizations-and-performance/MemoryManagement/): minh họa `--gc=epsilon` thuộc Native Image, **không phải** HotSpot `java` flags.

**Kết luận:** Epsilon là **công cụ đối chứng experimental no-op**, không phải lựa chọn GC mặc định để giảm chi phí quản lý lâu dài. So sánh tốt trên dữ liệu đại diện phải giữ **cùng code/input/heap/boundaries**, xác nhận checksum, ghi riêng **heap used/committed vs OS RSS**, **GC count/time vs process CPU/elapsed**, và có **nhiều forks cùng thống kê**. Chênh heap used giữa Epsilon và G1 chủ yếu phản ánh **Epsilon không reclaim temporary allocations** chứ không định lượng trực tiếp metadata overhead của collector. Hãy dùng Epsilon khi phép thử hữu hạn và có giới hạn OOM rõ ràng; dùng collector reclamation thực cùng profiling/GC logs/JFR và heap dump để đánh giá service production, memory retention và tail latency.