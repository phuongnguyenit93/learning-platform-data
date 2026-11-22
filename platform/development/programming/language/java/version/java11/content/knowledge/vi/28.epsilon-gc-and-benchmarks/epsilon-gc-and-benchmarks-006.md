# Epsilon và phép đo — Giới hạn khi suy rộng phép đo Epsilon sang collector sản xuất (Java 11+)

## Mục tiêu

**Epsilon GC** (OpenJDK **JEP 318**, có từ **Java 11**) là một *no-op garbage collector*. Nó cho phép cấp phát objects trong Java heap, nhưng **không thực hiện thu hồi các object không còn reachable**. Khi vùng heap khả dụng bị tiêu thụ hết, JVM không thể dựa vào Epsilon để reclaim memory; chương trình có thể kết thúc vì `OutOfMemoryError`.

Epsilon vẫn có ích trong **các phép thử có kiểm soát**: đối chứng không có công việc reclaim GC, thử giới hạn cấp phát, phát hiện regression về allocation và quan sát một số nguồn jitter không cần GC cycle. Nhưng **kết quả đo với Epsilon không thể suy rộng trực tiếp** thành tốc độ, P99 latency, CPU hoặc bộ nhớ của **G1, ZGC, Shenandoah, Parallel GC** trong production.

Bài học giải quyết trọng tâm đó, không chỉ giới thiệu cách bật Epsilon. Sau bài, bạn sẽ:

1. Phân biệt **allocation**, **reclamation**, **retained live set**, **cumulative allocated bytes**, **heap used**, RSS và max heap.
2. Hiểu Epsilon **loại bỏ GC reclamation**, không loại bỏ mọi chi phí cấp phát, JVM safepoint, JIT hoặc OS.
3. Biết **phép đo Epsilon hợp lệ để trả lời câu hỏi nào**, và những suy luận nào về collector production là vô căn cứ.
4. Không gọi `Time(G1) - Time(Epsilon)` là “thời gian GC” khi không có mô hình kiểm soát đầy đủ.
5. Có chương trình **Java 11 hoàn chỉnh** thử hai workloads: `bounded` và `churn`, trên Epsilon và G1, trong các JVM độc lập.
6. Giải thích vì sao cả Epsilon và G1 có thể chạy bài nhỏ với **0 collection**, trong khi Epsilon OOM ở bài churn và G1 thu hồi để hoàn thành.
7. Thiết kế benchmark nghiêm túc với correctness, cùng workload, JIT warmup, forks, samples, confidence intervals, JFR/GC logs và metrics end-to-end.
8. Đánh giá trade-off production về throughput, P95/P99/P99.9, pause, concurrent work, CPU quota, memory headroom và tính ổn định dài hạn.
9. Không dùng flags/collector đã lỗi thời, áp dụng đúng **Special Note** chỉ chọn kiến thức hiện còn giá trị.

**Giới hạn áp dụng:** Epsilon là **experimental collector** trên những HotSpot/OpenJDK builds có hỗ trợ, không phải lựa chọn mặc định cho dịch vụ chạy lâu. Mã dùng API và class-file target **Java 11**; bài cũng đề cập collector hiện đại để ngăn suy luận sai khi triển khai production.

---

## 1. Mô hình Epsilon: cấp phát mà không reclaim

Một chương trình tạo ba objects A/B/C:

```text
Ban đầu:
[ A ][ B ][ C ][                        free heap                      ]

Sau khi application không giữ reference tới A/B:

Collector production:
  A/B có thể được reclaim trong một GC cycle phù hợp.
  Vùng đó có thể tiếp tục phục vụ những allocations khác.

Epsilon:
  A/B có thể đã unreachable đối với application,
  nhưng Epsilon không reclaim chúng.
  [ A ][ B ][ C ][ D ][ E ][ ... ] --> cạn heap --> OutOfMemoryError
```

Điều quan trọng là phân biệt **đối tượng chết về mặt reachability** với **bộ nhớ đã thật sự được GC tái sử dụng**. Trong Epsilon, một object mất hết references nhưng vẫn làm tổng memory consumed của quá trình tăng lên khi các objects mới liên tục được cấp phát.

### Epsilon không phải “JVM không làm gì”

Epsilon vẫn chạy Java bytecode, JIT compilation, class initialization, allocation fast paths/TLAB nếu runtime sử dụng, JVM safepoints, synchronization và OS scheduling. Một số hoạt động bên trong JVM có thể cần tài nguyên dù không có chu kỳ thu hồi GC.

**Không nên tuyên bố:**

- Epsilon có “zero latency” hoặc “zero safepoint”.
- Mọi phép `new` trên Epsilon đều có overhead bằng 0.
- Heap used của Epsilon biểu diễn chính xác objects còn live.
- JVM sẽ chạy vô hạn nếu chỉ cần sống một ít objects.
- Kết quả Epsilon là lower bound toán học cho mọi collector trên mọi workload.
- Epsilon an toàn mặc định cho HTTP server, queue consumer hoặc service 24/7.

### Cách bật còn hợp lệ

Trên HotSpot hỗ trợ tính năng này:

```bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -version
```

`-XX:+UnlockExperimentalVMOptions` mở nhóm experimental options; `-XX:+UseEpsilonGC` chọn Epsilon. Đây **không phải** cờ thương mại lỗi thời. Nếu runtime không hỗ trợ, hãy xem `java -version`, build/vendor và thông báo flag thực tế, không giả định mọi JVM/Native Image đều dùng đúng các flags đó.

Trên **GraalVM Native Image**, `--gc=epsilon` là tùy chọn **build-time Native Image**, không phải cách bật HotSpot Epsilon trong bài này. Không gộp hai toolchains thành một phép đo.

## 2. Epsilon trả lời được những câu hỏi nào?

| Câu hỏi nghiên cứu | Epsilon có ích | Giới hạn khi suy ra collector production |
| --- | --- | --- |
| Workload **ngắn và có hạn mức** có vượt allocation budget không? | Chạy với heap giới hạn, xem nó có hoàn thành | G1/ZGC có footprint/metadata/headroom khác |
| Có jitter khi **không có reclamation GC** không? | Quan sát một nguồn đối chứng không chứa GC reclamation cycle | Jitter còn do JIT, safepoint, thread scheduling, OS |
| Refactor có làm tăng tổng allocation đáng kể không? | Budget regression test có thể phát hiện vượt giới hạn | Không phải profiler chính xác số bytes hay live set |
| Bounded workload có thể chạy không thu hồi memory không? | Kiểm tra tính khả thi dưới Epsilon | Không chứng minh service dài hạn sẽ ổn |
| Collector production có overhead gì khác khi đo cùng workload? | Đưa ra một **đối chứng** để hình thành giả thuyết | Chênh lệch tổng thời gian không chỉ là GC pause |
| GC pressure có liên quan đến hiệu năng thực tế? | Gợi ý điều gì nên đo tiếp | Phải đo G1/ZGC/Shenandoah trực tiếp và xem SLA |
| Kịch bản OOM khi không reclaim sẽ xảy ra thế nào? | Thử failure mode trong test process riêng | Không suy rằng code bị memory leak hoặc G1 cũng OOM |

**Diễn giải:** Epsilon là một đối chứng **negative control** đối với *reclamation*. Nó không phải bản sao nguyên vẹn của G1 sau khi “trừ đi các milliseconds dừng GC”.

## 3. Phép suy rộng phổ biến nhưng sai

Một phép tính trông hấp dẫn:

```text
elapsed_G1 = 110 ms
elapsed_Epsilon = 100 ms

Kết luận sai:
    GC overhead của G1 = 10 ms = 9,09%
```

Tại sao kết luận này chưa đủ bằng chứng?

**A. Allocation path khác nhau.** Collector có chính sách heap, TLAB, barriers và paths xử lý new object khác; giá của một reference store có thể khác ngay cả khi G1 chưa chạy GC collection nào.

**B. Bộ nhớ và CPU cache khác.** Epsilon không reclaim, có thể chạm nhiều pages hơn; G1 sử dụng vùng nhớ đã reclaim/compact, thay đổi locality, page faults, memory bandwidth.

**C. Concurrent work có thể làm app chậm gián tiếp.** ZGC/Shenandoah và G1 concurrent marking workers có thể cạnh tranh CPU, ảnh hưởng request latency dù pause rất ngắn. Đây không phải một đoạn STW time có thể cộng/trừ đơn giản.

**D. JIT profile khác.** JIT compilation, deoptimization và inlining xảy ra vào thời điểm không giống nhau; với một run ngắn, startup/jit noise có thể lớn hơn chênh lệch.

**E. Failure/success khác nhau.** Nếu Epsilon OOM trước khi hoàn thành, elapsed time của phần đã chạy không được đem chia cho số operation thành công của G1 để suy throughput.

**F. Giá của đo đạc khác.** Logging, JFR, agent và OS perf sampling có thể ảnh hưởng các runs, nhất là khi số events/threads của collector khác nhau.

Một mô hình định tính hợp lý hơn:

```text
Total response time ≈ business logic
                    + allocation/barrier work
                    + stop-the-world GC
                    + concurrent GC contention
                    + memory-pressure effects
                    + JIT / safepoints / OS / queueing
                    + interactions
```

Dấu cộng chỉ **liệt kê yếu tố**, không phải một decomposition đo được hoàn toàn độc lập. Vì các yếu tố tương tác, không có hằng số “Epsilon time + 3ms = ZGC time” áp dụng cho mọi ứng dụng.

## 4. Các metric không được đánh đồng

| Metric | Ý nghĩa và nguồn | Điều **không** thể kết luận từ nó |
| --- | --- | --- |
| **Requested payload bytes** | Từ kích thước arrays theo code và số lần tạo | Chính xác heap allocated bytes bao gồm headers/metadata |
| **Allocated bytes** | Profiler/JFR sampling/ThreadMXBean phù hợp | Objects còn live ở cuối |
| **Live set** | Objects reachable ở một điểm/mô hình GC | Heap used của Epsilon |
| **Heap used** | `MemoryMXBean.getHeapMemoryUsage().getUsed()` | Retained size chính xác hoặc memory leak |
| **Heap committed** | Bộ nhớ JVM cam kết cho heap | RSS toàn process |
| **RSS/container memory** | OS/cgroup metrics | Chỉ Java heap `-Xmx` |
| **GC collection count** | `GarbageCollectorMXBean.getCollectionCount()` | Pause time, CPU consumed hoặc P99 latency |
| **GC pause duration** | GC logs/JFR | Concurrent GC worker time |
| **Concurrent GC duration** | Logs/JFR | Stop-the-world time |
| **Allocation rate** | Bytes/s từ workload/profiling | Mức memory cần giữ suốt đời application |
| **Throughput** | Tasks/s hoặc requests/s hoàn thành | Chỉ elapsed time của một loop |
| **Application P99 latency** | Phân phối requests tại boundary thực | Một lần gọi microbenchmark |

### Cumulative allocations khác live set

Giả sử chương trình lặp lại:

```java
for (int i = 0; i < 100_000; i++) {
    byte[] data = new byte[8192];
    sink = data;
}
```

Đây là **mã minh họa**, cần định nghĩa `sink` trong class. Tổng payload đã yêu cầu cấp phát khoảng **781 MiB**, nhưng nếu ở mỗi vòng `sink` được thay bằng array mới, phần lớn arrays cũ không còn reachable qua `sink`. G1 có thể reclaim chúng; Epsilon không. Không được nói live set =781 MiB.

### Heap used dưới Epsilon không chứng minh leak

Vì không reclaim, heap used có thể tiếp tục tăng **ngay cả khi code không giữ references bất thường**. Một memory leak cần bằng chứng về **retained references/liveness**, ví dụ heap dump/object retention analysis hoặc các công cụ phù hợp.

### GC count không đồng nhất giữa collectors

Epsilon không có reclaim cycles, nên trong thí nghiệm số lần GC được báo **0**. G1 có thể báo 22 cycles khi thực hiện hàng trăm nghìn allocations. Điều đó **không** có nghĩa G1 chậm hơn 22 lần, cũng không nói collector nào có P99 pause thấp hơn trên production.

## 5. Compiler optimization khiến bài đo tưởng đúng thành sai

### Escape analysis và scalar replacement

Nếu code tạo một object rồi không để kết quả nào thoát khỏi scope, JIT có thể loại một số allocations:

```java
for (int i = 0; i < 100_000; i++) {
    byte[] ignored = new byte[8];
    ignored[0] = 1;
}
```

Đây **không phải benchmark hợp lệ**: `ignored` không được quan sát, có thể bị tối ưu. Người viết có thể tin rằng “Epsilon chịu được 100.000 arrays” trong khi chúng chưa bao giờ thực sự được cấp phát như mong đợi.

Trong chương trình phía dưới, mỗi array được **publish qua static volatile field**. Điều này tạo một đường observable escape và làm allocation không dễ bị loại khỏi vòng đo. **Tuy nhiên**, volatile publication thêm memory-ordering cost; kết quả vẫn không đo riêng chi phí `new byte[]` một cách thuần túy.

### JIT warmup

Một lượt `System.nanoTime()` dễ bị nhiễu bởi:

- Interpreter → JIT compilation (C1/C2).
- Class loading và class initialization.
- CPU frequency scaling và cache cold-start.
- OS thread scheduling/context switching.
- GC start/stop hoặc allocation buffer refill ở collector thật.

Vì vậy dùng **JMH** hoặc harness tương đương cho microbenchmark, đủ warmup, nhiều measurement iterations và nhiều JVM forks. JMH là **thư viện ngoài Java SE**; chương trình của bài chỉ là test minh họa quản lý bộ nhớ.

## 6. Thí nghiệm gồm hai modes khác mục đích

Chúng ta chủ ý **không trộn** hai loại phép đo:

**Bounded (thành công dưới cả hai collectors):**
- 1.000 arrays × 8 KiB.
- Cumulative requested array payload ≈ **7 MiB**, chưa kể overhead.
- Có thêm 16 arrays giữ lại × 256 KiB = **4 MiB**.
- Với heap 64 MiB trên runtime thử nghiệm, Epsilon và G1 đều hoàn thành.

**Churn (dùng để quan sát reclamation):**
- 100.000 arrays × 8 KiB.
- Cumulative requested payload ≈ **781 MiB**, lớn hơn nhiều lần heap 64 MiB.
- Chỉ giữ rất ít arrays từ vòng lặp (reference mới thay reference cũ).
- Với G1, allocations cũ được reclaim để chương trình hoàn thành.
- Với Epsilon, quá trình không reclaim và kết thúc vì OOME trong lần thử.

```text
Heap limit: 64 MiB trong từng JVM process riêng

               bounded          churn
Epsilon:       PASS             OOME (expected in the tested setup)
G1:            PASS             PASS (GC reclamation observed)

Chỉ kết luận:
- Bounded workload có thể hoàn thành trên cả hai.
- G1 reclaim được temporary objects trong churn.
- Epsilon không reclaim được nên dễ cạn heap.
- Không có tỉ lệ tốc độ P99/throughput production được suy ra.
```

**Không** dùng thời gian của một mode để so với mode khác. 1.000 iterations và 100.000 iterations là hai workloads khác nhau; một trường hợp còn **không hoàn thành**.

## 7. Java 11 runnable: EpsilonInferenceDemo.java

Chương trình dùng APIs **Java 11 chuẩn**, không cần database, network hay dependency ngoài:

- `GarbageCollectorMXBean` đọc reported collection count.
- `MemoryMXBean` lấy snapshot heap used.
- `System.nanoTime()` đo elapsed time chỉ của vòng allocation.
- `volatile published` làm references của arrays escape.
- `bounded` hoặc `churn` được chọn qua command-line argument.

### 7.1. Mã nguồn đầy đủ

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.util.ArrayList;
import java.util.List;

public final class EpsilonInferenceDemo {
    private static volatile byte[] published;

    private static long reportedCollections() {
        long total = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long value = bean.getCollectionCount();
            if (value > 0) {
                total += value;
            }
        }
        return total;
    }

    public static void main(String[] args) {
        if (args.length != 1
                || (!"bounded".equals(args[0])
                && !"churn".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Use: EpsilonInferenceDemo bounded|churn");
        }
        String mode = args[0];
        int iterations = "bounded".equals(mode) ? 1000 : 100000;
        int arrayBytes = 8192;

        List<byte[]> retained = new ArrayList<>();
        for (int i = 0; i < 16; i++) {
            retained.add(new byte[256 * 1024]);
        }

        long before = reportedCollections();
        long startNs = System.nanoTime();
        long checksum = 0;
        for (int i = 0; i < iterations; i++) {
            byte[] payload = new byte[arrayBytes];
            payload[0] = (byte) i;
            payload[arrayBytes - 1] = (byte) (i >>> 8);
            checksum += (payload[0] & 0xFF);
            published = payload; // Escape through a volatile field.
        }
        long elapsedNs = System.nanoTime() - startNs;
        long after = reportedCollections();
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        long heapUsedBytes = memory.getHeapMemoryUsage().getUsed();

        System.out.println("mode=" + mode);
        System.out.println("allocationsCompleted=" + iterations);
        System.out.println("requestedPayloadMiB="
                + ((long) iterations * arrayBytes / 1024 / 1024));
        System.out.println("retainedPayloadMiB="
                + (retained.size() * 256L * 1024 / 1024 / 1024));
        System.out.println("checksumPositive=" + (checksum > 0));
        System.out.println("reportedGCCountDelta=" + (after - before));
        System.out.println("heapUsedMiB=" + (heapUsedBytes / 1024 / 1024));
        System.out.println("elapsedMs=" + (elapsedNs / 1_000_000));
    }
}
```

**Một số điểm cần phân biệt:**

1. `requestedPayloadMiB` tính bằng **phép chia nguyên**; không tính array headers, alignment, metadata, JIT/runtime allocations.
2. `retainedPayloadMiB=4` là số byte payload của arrays giữ trong List theo source; **không phải live set hoặc RSS đo thực tế**.
3. `getCollectionCount()` có thể trả `-1` khi không có giá trị được định nghĩa; code bỏ qua, không coi nó là một “GC zero”.
4. `elapsedMs` không đo request end-to-end, không gồm startup và những query management APIs trước/sau loop.
5. Heap used sau workload có thể cao hoặc thấp tùy collector đã chạy GC gần lúc nào.
6. Trong `churn` dưới Epsilon, JVM có thể terminate **trước** khi in bất cứ dòng tổng kết nào.
7. Code không gọi `System.gc()`, vì yêu cầu GC thủ công sẽ làm nhiễu thử nghiệm; Epsilon dù sao cũng không reclaim.
8. Kích thước heap trong commands chỉ dùng để thử nghiệm ngắn, không phải cách sizing production.

### 7.2. Biên dịch

Lưu đúng tên `EpsilonInferenceDemo.java` và chạy:

```bash
java -version
javac --release 11 -encoding UTF-8 EpsilonInferenceDemo.java
```

**Mã đã biên dịch thành công bằng `javac --release 11` và chạy trên JDK hiện đại.** Nếu muốn cam kết runtime Java 11, CI cần thêm một lượt chạy **trên JDK 11 thật**; compile target 11 trên JDK mới không tự chứng minh điều đó.

## 8. Thực hiện bốn ca test tách biệt

**An toàn:** tạo bốn JVM processes riêng, mỗi process giới hạn `-Xms64m -Xmx64m`. Không chạy Epsilon churn bên trong process xử lý giao dịch production. Cần HotSpot có Epsilon support; chạy `java -version` trước và kiểm tra flags bằng câu lệnh phần 1.

### 8.1. Epsilon bounded

```bash
java -Xms64m -Xmx64m -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -Xlog:gc=info EpsilonInferenceDemo bounded
```

**Kết quả có thật của một lượt thử** (các timestamp/count/heap/elapsed có thể thay đổi):

```text
[0.006s][info][gc] Using Epsilon
mode=bounded
allocationsCompleted=1000
requestedPayloadMiB=7
retainedPayloadMiB=4
checksumPositive=true
reportedGCCountDelta=0
heapUsedMiB=14
elapsedMs=1
```

Ý nghĩa: đoạn bounded hoàn thành, bộ đếm collection báo 0. **Không** chứng minh Epsilon sẽ luôn hoàn thành một workload khác với heap 64 MiB.

### 8.2. G1 bounded

```bash
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc=info EpsilonInferenceDemo bounded
```

**Một lượt test thật**:

```text
[0.007s][info][gc] Using G1
mode=bounded
allocationsCompleted=1000
requestedPayloadMiB=7
retainedPayloadMiB=4
checksumPositive=true
reportedGCCountDelta=0
heapUsedMiB=14
elapsedMs=1
```

**Điểm rút ra:** cả Epsilon **và G1** đều không báo collection trong lượt bounded. Vì thế “không có GC cycle” không phải một khác biệt đo được trong lần thử này. Hai số `elapsedMs=1` tương tự nhau là quan sát **không đủ thống kê** để kết luận throughput/P99.

### 8.3. G1 churn

```bash
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc=info EpsilonInferenceDemo churn
```

Trong lượt thử, **các dòng do application in** (JVM còn in nhiều GC logs riêng):

```text
mode=churn
allocationsCompleted=100000
requestedPayloadMiB=781
retainedPayloadMiB=4
checksumPositive=true
reportedGCCountDelta=22
heapUsedMiB=15
elapsedMs=65
```

Đây là **một mẫu thực nghiệm**, không phải stdout bất biến. Số collections 22, heap used 15 MiB và elapsed 65 ms sẽ khác trên máy/JDK khác. Điều có thể nói: **G1 hoàn thành** workload đã yêu cầu cumulative payload lớn hơn heap nhiều lần, vì nó có khả năng reclaim arrays đã unreachable.

### 8.4. Epsilon churn — kiểm thử thất bại có chủ đích

```bash
java -Xms64m -Xmx64m -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -Xlog:gc=info EpsilonInferenceDemo churn
```

Trong phiên đã kiểm tra:

```text
[0.006s][info][gc] Using Epsilon
Terminating due to java.lang.OutOfMemoryError: Java heap space
```

Process kết thúc với **mã thoát khác 0** (lượt thử cụ thể là 3). Không lấy exit code 3 hoặc câu chữ exact của error làm contract chung cho mọi JVM: cách JVM báo failure/exit code có thể thay đổi. **Không so elapsed của quá trình thất bại với G1 churn thành công**.

### 8.5. Đọc ma trận kết quả

| Thí nghiệm | Workload | Epsilon | G1 | Kết luận hợp lệ |
| --- | --- | --- | --- | --- |
| Bounded | 1.000 arrays, payload ~7 MiB | PASS, 0 collection | PASS, 0 collection | Không cần reclaim để hoàn thành fixture |
| Churn | 100.000 arrays, payload ~781 MiB | OOME trong thử nghiệm | PASS, có collections | G1 reclaim được temporary arrays; Epsilon không |

**Không suy ra:** “G1 chậm hơn 22 lần”, “Epsilon có P99 bằng 0”, “G1 heap live set chỉ có 15 MiB”, “Epsilon production sẽ an toàn nếu test được 1 giây”.

## 9. Tại sao `heapUsedMiB` dưới Epsilon không đo live set?

Giả sử sau vòng churn bạn chỉ giữ:
- Một array cuối trong `published`.
- 16 arrays trong `retained`.
- Các objects cần thiết của JVM/ứng dụng.

Trong Epsilon, hàng nghìn arrays **trước** không còn reachable qua `published` nhưng **không được reclaim**. Vì vậy snapshot memory used có thể tăng mạnh dù business logic không giữ reference tới tất cả arrays ấy.

Ngược lại, G1 đã reclaim phần lớn arrays tạm, nên `heapUsedMiB` tại thời điểm đọc có thể thấp hơn nhiều. **Độ chênh không đo chính xác lượng memory leak.** Muốn biết live set/retained references, cần công cụ heap analysis phù hợp và xác nhận objects thật sự reachable.

Đừng nhầm:
- **Allocation churn:** nhiều objects tạo rồi chết nhanh.
- **Retained live set:** đối tượng còn reachable tại thời điểm đo.
- **Memory leak:** chương trình giữ reference ngoài ý muốn, khiến live set tăng.
- **GC backlog/headroom:** collector chưa reclaim hoặc không reclaim kịp trong một thời điểm.
- **Native memory:** direct buffers, thread stacks, metaspace, code cache, JNI — nằm ngoài `-Xmx`.

Một chương trình có allocation churn cao có thể OOM trên Epsilon nhưng rất ổn trên G1. Một memory leak thật cũng có thể chạy qua bài test 1 giây mà chỉ OOM sau hàng giờ.

## 10. Vì sao không thể suy throughput/P99 collector sản xuất từ Epsilon?

### Collector đổi nhiều biến cùng lúc

- **G1:** generational regions, concurrent marking, evacuation pauses, write barriers/remembered sets.
- **ZGC hiện đại:** concurrent marking/relocation, barriers và heap headroom; vẫn có các điểm coordination/pause ngắn. Từ **JDK 24**, mode ZGC không-generational đã bị loại bỏ; không dùng cờ `ZGenerational` chuyển tiếp như hướng dẫn hiện hành.
- **Shenandoah:** concurrent evacuation/forwarding trên những JDK builds hỗ trợ, với resource costs/fallbacks riêng.
- **Parallel/Serial GC:** hướng tới trade-off throughput/sự đơn giản khác và có STW collections.
- **Epsilon:** không reclaim, có thể OOM dù live set nhỏ.

Khi đổi collector, allocation paths, heap layout, JIT/CPU contention và memory footprint thay đổi. Nếu cần quyết định dùng G1 hay ZGC, cách đúng là **đo trực tiếp G1 và ZGC**, không lấy Epsilon rồi thêm một hằng số điều chỉnh.

### Các hiện tượng latency không do GC reclamation

Ngay cả dưới Epsilon, một JVM vẫn có thể gặp:
- JIT compilation/deoptimization/class loading.
- Safepoints vì lý do khác GC.
- OS scheduler, CPU frequency/thermal throttling.
- Lock contention, thread pool queueing, network/file I/O.
- Page faults, memory bandwidth/cache misses.
- Agents/profilers/tracing/logging overhead.
- Dependencies bên ngoài: DB, APIs và message brokers.

Vì thế một spike dưới Epsilon có thể giúp tìm **nguồn jitter không cần GC cycle**, nhưng nó không chứng minh mọi spike dưới G1 cũng cùng nguyên nhân.

### Concurrent GC duration khác pause

G1/ZGC/Shenandoah có những phases chạy **concurrent với mutators**. Duration 100 ms của concurrent GC không đồng nghĩa application dừng 100 ms. CPU competition có thể làm application chậm hơn mà không hiện thành STW pause tương ứng. Do đó khi đo tail latency cần cả GC logs/JFR, CPU quota và request measurements.

## 11. Thiết kế benchmark đúng cách

Một benchmark nghiêm túc cần đảm bảo **cùng công việc được hoàn thành thành công**:

1. **Nêu giả thuyết:** ví dụ “giảm allocation rate từ A xuống B làm giảm CPU/GC pause của service”, không chỉ “Epsilon chạy nhanh hơn”.
2. **Giữ workload bất biến:** payload, concurrency, request mix, data volume, business result, retries và errors.
3. **Cố định environment:** JDK vendor/build/version, OS, CPU quota, RAM/cgroup limits, network/storage conditions.
4. **Cố định heap policy trong phép so có ý nghĩa:** `-Xms/-Xmx`, nêu các options riêng của collector, không mặc định heap size như nhau là memory footprint như nhau.
5. **JIT warmup và nhiều forks:** dùng JMH cho microbenchmarks, hoặc harness đo services có kiểm soát.
6. **Nhiều measurement iterations:** đủ mẫu để ước lượng phân phối và confidence intervals.
7. **Ghi lại process success/error rate:** không bỏ failed requests hoặc OOME khỏi kết quả.
8. **Đo metrics phù hợp:** requests/s, P50/P95/P99/P99.9, GC pause, concurrent CPU, RSS, allocation rate.
9. **Xem GC log/JFR:** không chỉ dựa vào `GarbageCollectorMXBean.getCollectionCount()`.
10. **Kiểm tra trade-off:** low pause có thể tiêu tốn thêm CPU hoặc memory headroom, throughput không tự tăng.
11. **Test sustained load và spike:** không chỉ 1ms benchmark hoặc những phút đầu startup.
12. **Công bố phạm vi:** kết luận gắn chặt với workload, JDK và hardware đo được.

### So sánh collector trong ba nhóm

| Nhóm | Collector | Mục đích |
| --- | --- | --- |
| **Epsilon control** | Epsilon, chỉ bounded workload | Quan sát khi không có reclaim và kiểm tra allocation budget |
| **Production baseline** | Collector đang dùng như G1 | Đo thực tế trên load sản xuất mô phỏng |
| **Production candidate** | ZGC/Shenandoah hoặc collector khác được hỗ trợ | Kiểm thử có cải thiện SLO/tài nguyên hay không |

**Epsilon không thay cho baseline production.** Nếu Epsilon OOM dưới load lâu, điều đó chỉ nói nó không phù hợp workload đó. Đừng “sửa” bằng cách tăng `-Xmx` vô hạn: JVM còn native memory và process/container limits.

## 12. Đo bằng GC logs, JFR và metrics

### GC logs

Trên HotSpot Java 11+:

```bash
java -Xms512m -Xmx512m -XX:+UseG1GC -Xlog:gc=info -jar your-service.jar
```

`your-service.jar` là **tên minh họa**, không đi kèm bài. Production nên ghi logs vào file có rotation/retention và quản lý overhead.

`-Xlog:gc=info` giúp phân biệt:
- `Pause Young`/`Pause Remark`: những STW pauses.
- `Concurrent Mark` hoặc các phases tương ứng: GC work trong khi application có thể tiếp tục.
- `Full GC`, allocation stalls hoặc fallback: rủi ro long-tail cần quan sát.

**Không** cộng một concurrent phase duration như thể nó là thời gian stop-the-world.

### JDK Flight Recorder

Nếu service đang chạy, có thể dùng `jcmd`:

```bash
jcmd -l
jcmd 12345 JFR.start name=GcStudy settings=profile disk=true maxage=10m maxsize=64m
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=GcStudy filename=gc-study.jfr
jcmd 12345 JFR.stop name=GcStudy
```

PID là số **minh họa**, hãy dùng đúng JVM. `JFR.dump` xuất bản chụp **không dừng**; `JFR.stop` mới dừng. File JFR có thể chứa thông tin nhạy cảm về class/method/thread/path và custom events; phải phân quyền, lưu trữ và xóa theo retention.

Các phép phân tích:

```bash
jfr summary gc-study.jfr
jfr print --events jdk.GarbageCollection gc-study.jfr
```

Cần kiểm tra event types/threshold thực tế vì file không nhất thiết có mọi loại sự kiện. Kết hợp JFR với **metrics của request** để hiểu liệu pauses/tài nguyên JVM có liên hệ với tail latency thực tế.

### Resource metrics

Theo dõi:
- CPU usage tổng và **cgroup CPU throttling**.
- Heap used/committed/max, native RSS.
- Allocation rate, live set/reclaim.
- GC STW pause p99/max và count.
- Concurrent GC CPU, memory headroom, stalls.
- Request throughput, latency distribution, errors/timeouts.
- Tình trạng DB/network/queue và thread contention.

**Không xem `-Xmx` là giới hạn toàn bộ RSS**, vì JVM vẫn có metaspace, stacks, code cache và direct/native memory.

## 13. Điều gì xảy ra khi Epsilon OOME?

Trong thử nghiệm `churn` với heap 64 MiB, dòng:

```text
Terminating due to java.lang.OutOfMemoryError: Java heap space
```

là **failure có chủ đích**, không phải output “đạt” của application. Lệnh Epsilon chạy ở process riêng có memory limit để không ảnh hưởng service khác.

**Giải thích đúng:**
- 781 MiB là **tổng payload yêu cầu cấp phát**, không phải số bytes còn reachable.
- Epsilon không reclaim nên heap hữu hạn cạn trước khi hoàn tất.
- G1 đã reclaim được temporary arrays, nên thành công trong test tương ứng.
- Kết quả không chứng minh code có leak; cũng không bảo đảm code không leak khi chạy production lâu dài.
- Không có elapsed time thành công của Epsilon churn để so với G1 churn.
- Exit code, cách hiển thị OOME và vị trí process dừng có thể phụ thuộc JVM/vendor.

Một allocation-budget test dùng Epsilon có thể được đặt trong CI với **expected failure** khi vượt ngưỡng. Nhưng cần quy định rõ test data, JDK build, heap, timeout và xử lý subprocess exit code; không đặt test OOME bên trong một worker thread của service thật rồi cố tiếp tục giao dịch.

## 14. Sai lầm phổ biến

| Sai lầm | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| “Epsilon nhanh hơn 10% → GC chiếm 10%” | Khác allocator/barriers/JIT/CPU/cache | Dùng A/B control và đo collector thật |
| “Epsilon không reclaim nên là GC production tốt nhất” | OOME với allocation tích lũy | Dùng Epsilon chủ yếu cho thử nghiệm |
| “Epsilon OOM nghĩa là leak” | Unreachable objects vẫn chiếm heap | Phân tích live/retained references |
| “Epsilon heap used chính là live set” | Không reclaim | Dùng heap profiler/retention analysis |
| “G1 báo 0 GC thì G1 overhead bằng 0” | Barriers/allocator work vẫn tồn tại | Đo nhiều nguồn chi phí |
| “GC count 22 so với 0 là chậm hơn 22 lần” | Count không phải duration | Đo pause, CPU, throughput |
| “Xmx 64 MiB bằng RSS 64 MiB” | Ngoài heap còn native memory | Đo RSS/cgroup |
| “Epsilon latency bằng 0” | Còn safepoints/OS/JIT/I/O | Phân tích nguồn jitter khác |
| “Một lượt 1ms là benchmark đáng tin” | JIT/scheduler noise | Warmup, forks, repetitions |
| “Không có GC trong test nhỏ nghĩa production không cần GC” | Steady-state allocation khác | So sustained load |
| “GC logs không có pause thì code không có latency” | Nhiều nguyên nhân không GC | End-to-end traces/metrics |
| “So bounded với churn để xếp hạng collector” | Workload khác | Chỉ so cùng công việc hoàn thành |
| “Epsilon OOM thì throughput bằng 0 và G1 vô hạn” | Không cùng tiêu chí measurement | Báo feasibility/failure riêng |
| “Native Image `--gc=epsilon` như JVM flag” | Toolchains khác | Kiểm tra runtime/baseline |
| “Tăng heap vô hạn là cách dùng Epsilon bền vững” | Heap/resource hữu hạn | Bounded workload hoặc GC thật |
| “Dùng cờ CMS cũ trong JDK hiện đại” | CMS đã legacy/removed | Dùng collector được JDK hỗ trợ |
| “Chọn ZGC từ chênh lệch với Epsilon” | ZGC có concurrent/heap semantics riêng | Test ZGC trực tiếp |

## 15. Lộ trình triển khai kết quả nghiên cứu

### Nếu muốn giảm allocation

1. Dùng profiler/JFR để tìm classes/sites phát sinh allocation.
2. Đo trước/sau refactor trên **cùng collector production**.
3. Dùng Epsilon bounded như **một đối chứng phụ** khi muốn phát hiện allocation budget regression.
4. Không khẳng định heap Epsilon phản ánh memory leak.
5. Đánh giá CPU, code complexity và kết quả nghiệp vụ bên cạnh allocation rate.

### Nếu muốn giảm P99 pause

1. Thu GC logs/JFR của collector production.
2. Xác định pauses nào thực sự trùng request latency spikes.
3. Xem GC trigger, heap occupancy, live set và CPU quotas.
4. So G1 với ZGC/Shenandoah **nếu JVM hỗ trợ**, trên workload thực tế.
5. Kiểm tra cả throughput, CPU, RSS, stalls/fallback/OOM.
6. Epsilon chỉ là control để khám phá jitter ngoài reclamation, không phải dự báo trực tiếp P99.

### Nếu muốn kiểm tra memory budget

1. Xác định tổng allocations dự kiến theo thời gian sống của **bounded job**.
2. Chạy Epsilon trong subprocess có `-Xmx` chặn chặt.
3. Xem job hoàn thành không; kiểm tra dữ liệu đầu ra.
4. Chạy job bằng collector production để xác định footprint/behavior thực.
5. Theo dõi native RSS/cgroup limit để không bỏ sót memory ngoài heap.

### Nếu muốn viết báo cáo ra quyết định

Một báo cáo có thể có các trường:

```text
JDK: vendor + build + major version
Collectors: production baseline, candidate, Epsilon control
Workload: request mix, concurrency, allocations/live-set model
Resources: heap sizes, CPU/RAM quotas, native RSS
Warmup/runs: JVM forks, iterations, duration
Correctness: output match, successful operations, errors
Performance: throughput, P50/P95/P99/P99.9, confidence intervals
GC: pause distribution, concurrent CPU, allocation stalls/fallbacks
Epsilon: bounded success/failure ONLY, no production extrapolation
Conclusion: scope, uncertainty, next validation step
```

Đừng công bố “collector A luôn tốt hơn B” mà không ghi workload/resource/version. Với production, collector tốt là lựa chọn **đạt SLO trong ngân sách CPU/RAM/throughput và độ ổn định**, không phải collector thắng một vòng allocation demo.

## 16. Bài tập và đáp án

**Bài 1.** Epsilon có thu hồi objects unreachable không? **Không**; nó không implement GC reclamation.

**Bài 2.** Vì sao Epsilon không thích hợp mặc định cho service chạy dài? **Cumulative allocation sẽ dần cạn heap hữu hạn**.

**Bài 3.** Epsilon OOM có chứng minh memory leak không? **Không**; temporary objects không được reclaim cũng làm heap cạn.

**Bài 4.** Bounded test cả Epsilon và G1 có `GCCountDelta=0`. Có chứng minh G1 overhead bằng 0 không? **Không**; test chưa kích hoạt GC cycle, các overhead khác vẫn có thể tồn tại.

**Bài 5.** `heapUsed_Epsilon=60MiB` có bằng retained live set 60 MiB không? **Không**; còn unreachable objects chưa reclaim.

**Bài 6.** G1 có 22 collections trong test, Epsilon có 0. Collector nào có P99 latency tốt hơn trong production? **Không thể biết từ count**.

**Bài 7.** Chênh lệch `T_G1 - T_Epsilon` có đúng bằng GC pause time? **Không**; còn allocation/barriers/CPU/JIT/cache interactions.

**Bài 8.** Tại sao cần volatile publication trong fixture? Để arrays escape, tránh bị compiler tối ưu hết allocation; nhưng chính volatile cũng thêm overhead.

**Bài 9.** Requested payload 781 MiB có nghĩa live set 781 MiB? **Không**; có thể chỉ giữ array gần nhất và 4 MiB arrays cố ý.

**Bài 10.** G1 churn thành công, Epsilon churn OOM. Có thể xếp hạng throughput bằng elapsedMs của hai process không? **Không**, một bên chưa hoàn thành.

**Bài 11.** Một test 1ms có đủ để suy ra throughput production không? **Không**; cần benchmark có warmup/forks/repetitions.

**Bài 12.** Epsilon có loại bỏ mọi safepoint/JIT/OS jitter không? **Không**.

**Bài 13.** Trong Java 11 HotSpot có Epsilon support, cần cờ gì? `-XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC`.

**Bài 14.** Cờ `--gc=epsilon` là cách bật HotSpot Epsilon? **Không**, đó là tùy chọn của GraalVM Native Image toolchain.

**Bài 15.** Khi mục tiêu P99 API latency, cần đo gì? **Request latency distribution và error rate**, đồng thời GC logs/JFR/CPU/RSS/throughput.

**Bài 16.** G1 count 0 ở test ngắn thì các request dài có GC không? **Có thể**, cần workload/heap pressure khác.

**Bài 17.** ZGC hiện đại có còn non-generational mode ở JDK 25 không? **Không**, đã bị loại từ JDK 24.

**Bài 18.** Có nên chạy intentionally OOM Epsilon churn ở JVM production đang xử lý dữ liệu thật? **Không**, chỉ isolated test process.

**Bài 19.** Epsilon có thể là negative control cho dạng overhead nào? **Reclamation GC cycles**; không phải phép tách chính xác mọi overhead của collector khác.

**Bài 20.** Cách tốt nhất để chọn G1 hay ZGC/Shenandoah cho service thật? **Test trực tiếp các collectors được hỗ trợ trên workload production-like**, cùng resource constraints và SLO, đo nhiều lượt.

### Checklist cuối bài

1. Hiểu Epsilon là no-op experimental collector còn có ích trong testing?
2. Không coi Epsilon là production recommendation mặc định?
3. Phân biệt total allocations, live set, heap used, RSS?
4. Không kết luận OOM của Epsilon đồng nghĩa leak?
5. Không dùng GC count làm pause/CPU/throughput?
6. Có kiểm tra JIT escape analysis và benchmark elimination?
7. Có cùng workload, correctness và resource limits trước khi so tốc độ?
8. Đã tách bounded success với churn expected failure?
9. Có warmup/forks/repetitions/confidence interval?
10. Có GC logs/JFR và application P99/throughput/CPU/RSS?
11. Có phân biệt concurrent GC time và STW pause time?
12. Có xét container memory/native memory, heap headroom?
13. Có xác minh flags trên đúng JDK/vendor hiện hành?
14. Có test runtime JDK 11 thật nếu dự án yêu cầu baseline 11?
15. Có nói rõ **phạm vi**, không suy từ Epsilon thành universal collector ranking?

## Tài liệu tham khảo

- [OpenJDK JEP 318 — Epsilon: A No-Op Garbage Collector](https://openjdk.org/jeps/318): động cơ và giới hạn của no-op GC.
- [Oracle JDK 11 Release Notes — Epsilon](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html): Epsilon experimental từ Java 11, allocation nhưng không reclaim.
- [Oracle Java SE 25 — java command / advanced JVM options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): experimental VM options và flags.
- [Oracle Java SE 25 — GC Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/index.html): collector production, latency/throughput/footprint.
- [Oracle Java SE 11 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): collection count semantics.
- [Oracle Java SE 11 — MemoryMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap memory usage.
- [Oracle Java SE 11 — java tool](https://docs.oracle.com/en/java/javase/11/tools/java.html): `-Xlog:gc` và Java 11 runtime flags.
- [Oracle Java SE 11 — jcmd](https://docs.oracle.com/en/java/javase/11/tools/jcmd.html): JVM diagnostics/JFR.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR trên OpenJDK 11+.
- [OpenJDK JEP 490 — Remove Non-Generational ZGC](https://openjdk.org/jeps/490): xác định cờ/mode ZGC cũ không còn dùng.
- [OpenJDK JEP 379 — Shenandoah Production](https://openjdk.org/jeps/379): collector production có concurrent operations.
- [JMH — OpenJDK Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): thử nghiệm với warmup, forks và measurement iterations.
- [BellSoft Liberica — JVM Memory Configuration Guide (2025)](https://download.bell-sw.com/documentation/liberica-jdk/jvm-memory-configuration-liberica-jdk.pdf): xác nhận Epsilon còn experimental và nêu lưu ý production, tài liệu theo vendor.

**Kết luận:** Epsilon là **phép đối chứng hữu ích nhưng có giới hạn**, không phải một mô hình toán học của G1/ZGC/Shenandoah khi bỏ GC pause. Nó giúp thấy một workload có vượt allocation budget hay có jitter dù không có reclamation. Nhưng **không thể chuyển trực tiếp elapsed time, heap used, GC count của Epsilon thành throughput, live set, pause hoặc P99 production**. Khi lựa chọn collector, phải đo **trực tiếp collector thật** trên cùng workload hoàn thành, JDK/resources được kiểm soát, có dữ liệu thống kê và bằng chứng từ GC logs/JFR.