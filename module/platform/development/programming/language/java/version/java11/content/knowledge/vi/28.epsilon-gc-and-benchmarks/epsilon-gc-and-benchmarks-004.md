# Java 11+ — Epsilon và phép đo: Dự trù heap theo lượng cấp phát tích lũy

## 1. Vấn đề: heap trống theo live set vẫn có thể đầy với Epsilon

**Epsilon GC** là bộ thu gom rác *no-op* của HotSpot, được đưa vào Java 11 bằng **JEP 318 — Epsilon: A No-Op Garbage Collector (Experimental)**. Epsilon có thể **cấp phát trên Java heap nhưng không thực hiện thu hồi object không còn được tham chiếu**. Trong mô hình này, mỗi byte heap đã bị dùng để tạo object **không được tái sử dụng nhờ garbage collection** trong cùng vòng đời process.

Do vậy, điều kiện để một tác vụ chạy xong với Epsilon **khác** điều kiện đủ heap cho collector có reclaim:

- Với **G1, ZGC, Parallel GC**: cần đủ chỗ cho **đối tượng sống, vùng dự phòng và allocation pressure**, trong khi GC có thể thu hồi object đã chết.
- Với **Epsilon**: cần đủ chỗ cho **tất cả Java-heap allocations thực sự xảy ra từ lúc JVM khởi chạy đến lúc kết thúc**, bất kể phần lớn object đã trở thành garbage.

Hình dung một dịch vụ xử lý 12.000 message. Mỗi message tạo mảng 4 KiB, nhưng ứng dụng chỉ giữ 64 mảng gần nhất trong ring buffer. Kết thúc, payload các mảng còn giữ chỉ **262.144 byte**; tuy nhiên **payload tích lũy đã cấp phát là 49.152.000 byte**, chưa tính headers, alignment và runtime allocations. Epsilon **không thu hồi** những mảng từng xuất hiện trong ring nhưng nay đã bị thay thế.

**Mục tiêu học tập:** lập ngân sách `-Xmx` theo lượng cấp phát tích lũy, hiểu khác biệt giữa **allocated**, **retained**, **used/committed**, biết kiểm chứng bằng một Java 11 program chạy thật, và dùng Epsilon đúng phạm vi **benchmark, short-lived bounded job, memory-budget test**, không dùng như GC mặc định cho server vô hạn thời gian.

## 2. Trạng thái hiện hành và cách bật Epsilon

Epsilon được thêm ở **JDK 11**, đến nay vẫn có trong các HotSpot builds hiện đại hỗ trợ tính năng này, nhưng là **experimental**. Đây không phải một GC bị xóa bỏ khỏi JDK mới, cũng không phải lựa chọn phổ thông cho ứng dụng production chạy lâu.

Bật Epsilon (trên JVM hỗ trợ):

```bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC \
  -Xms96m -Xmx96m -Xlog:gc=info \
  EpsilonBudgetDemo 12000
```

**Cờ unlock experimental phải đứng trước cờ Epsilon.** Trên Windows PowerShell, cùng lệnh có thể viết một dòng:

```powershell
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -Xms96m -Xmx96m -Xlog:gc=info EpsilonBudgetDemo 12000
```

Để có chương trình `EpsilonBudgetDemo`, cần tạo và biên dịch như mục 8. Đây không phải tên một class tích hợp trong JDK.

Cần phân biệt:

| Lựa chọn | Có reclaim Java heap? | Ý nghĩa |
| --- | --- | --- |
| **Epsilon GC** | **Không** | Đo cumulative allocations/benchmark bounded workloads. |
| **G1** | Có | Collector phổ thông cho nhiều server workloads. |
| **Generational ZGC** | Có | Collector thiên về GC pause ngắn và concurrent work. |
| **Heap dump** | Không phải GC | Snapshot retained objects tại một thời điểm. |
| **JFR allocation profiling** | Không phải GC | Ghi sự kiện để phân tích allocation hot spots. |
| **GraalVM Native Image `--gc=epsilon`** | No-op collector của native-image runtime | Là cờ **khi build native image**, không thay cho `-XX:+UseEpsilonGC` của HotSpot. |

**`-Xmx` là giới hạn Java heap**, không phải giới hạn tổng RAM/JVM process. Epsilon có thể khiến Java heap chạm `-Xmx` và ném `OutOfMemoryError` dù GC có reclaim có thể vận hành bình thường với chính kích thước heap đó.

## 3. Bốn đại lượng cần tách rạch ròi

| Đại lượng | Ký hiệu | Định nghĩa |
| --- | --- | --- |
| **Live set** | `L(t)` | Đối tượng vẫn còn reachable từ GC roots ở thời điểm `t`. |
| **Cumulative allocation** | `A(t)` | Tổng footprint các object **thực sự được cấp phát trên Java heap** trong khoảng thời gian đã chọn, kể cả object chết sớm. |
| **Heap used/occupancy** | `U(t)` | Bộ nhớ heap đã tiêu thụ theo chỉ số của JVM/collector; có thể cập nhật không phải từng byte. |
| **Heap max** | `H_max` | Giới hạn heap của JVM, chủ yếu do `-Xmx` chi phối. |

Với GC thông thường, `U(t)` **có thể giảm** sau collection vì vùng của object chết được dùng lại. Với Epsilon, **không có reclamation**, nên `U(t)` tiến gần **tổng footprint đã được tiêu thụ**; khi còn quá ít khoảng trống để cấp object mới, program dừng vì thiếu bộ nhớ.

Ví dụ với 12.000 mảng 4 KiB:

```text
Iterations                      12.000
Bytes of payload per array        4.096
Cumulative array payload     49.152.000 byte
References still kept                 64
Retained array payload          262.144 byte
```

**Cumulative payload** không phải **total actual heap bytes**: còn array header, object alignment, TLAB waste, ring buffer, runtime allocations, classloading, JIT và nhiều object khác. Đừng lấy `String.length()`, `byte[].length` hay `request payload size` làm số đo cuối cùng của heap footprint.

### Ví dụ minh họa sự khác nhau giữa hai collector

```text
Thời gian ------------------------------>

G1 / collector có reclaim:
Allocate → objects die → GC reclaims → allocate tiếp

Epsilon:
Allocate → objects die → NO RECLAIM → allocate tiếp
                                        |
                                        v
                               used gần giới hạn -Xmx
                                        |
                                        v
                              OutOfMemoryError / exit
```

Mặc dù `objects die` có thể đúng ở cả hai trường hợp (không còn Java references), **Epsilon không có cơ chế làm vùng heap trở lại available**. Gán `obj = null` không phải cách giảm `U(t)` với Epsilon.

## 4. Dự trù heap bằng công thức nào?

Một mô hình ngân sách có thể dùng:

```text
H_required ≈ H_baseline
           + A_total_after_baseline
           + H_extra_for_variance

H_target = (H_baseline + A_total_after_baseline)
           × (1 + margin_ratio)
```

Trong đó:

- `H_baseline`: heap đã dùng ở mốc bắt đầu đo, ví dụ sau khởi tạo JVM và framework. Nếu lập ngân sách **từ lúc JVM khởi động**, có thể gộp startup allocations vào `A_total` và không đếm lại.
- `A_total_after_baseline`: tất cả **Java-heap allocations** từ mốc đo đến khi **process kết thúc**, gồm background threads, libraries, retries, scheduler, logging, serialization và shutdown.
- `margin_ratio`: biên an toàn cho không chắc chắn, burst, variation giữa runs/JDK, TLAB/alignment, sai số ước lượng và tải lớn nhất.
- `H_target` là dự toán cần **kiểm chứng bằng test thật** chứ không phải một giới hạn JVM tự động thỏa mãn.

Nếu biết allocation rate theo thời gian:

```text
A_total(T) ≈ ∫ từ 0 đến T [allocation_rate(t)] dt

Nếu rate ổn định:
A_total ≈ rate_bytes_per_second × duration_seconds
```

**Không được dùng “live heap sau GC” làm `A_total`.** Live heap và allocation rate đo hai thứ khác nhau.

### 4.1. Ví dụ dự toán một job hữu hạn

Giả sử job chạy tối đa 180 giây:

- Java-heap allocation rate trung bình trong các pha quan trọng: **40 MiB/s**.
- Baseline heap trước các pha đó: **320 MiB**.
- Safety margin giả định: **25%**.

```text
A_work = 40 MiB/s × 180 s        = 7.200 MiB
H_base + A_work                 = 7.520 MiB
H_target = 7.520 MiB × 1,25     = 9.400 MiB
                                       ≈ 9,18 GiB
```

Kết quả **9.400 MiB** chỉ đúng trong **giả định minh họa**. Trên thực tế, nếu có burst allocation rate, retries, startup/termination work, nhiều threads không nằm trong số 40 MiB/s hoặc CI instrumentation làm tăng allocations, heap cần lớn hơn.

Không có quy tắc bắt buộc **safety margin 25%**. Dự án phải chọn margin dựa trên phân phối của workloads, rủi ro OOME và memory capacity. Nếu tổng cấp phát **không có upper bound hữu hạn**, không thể đảm bảo Epsilon chạy mãi với một `-Xmx` hữu hạn.

### 4.2. Dự toán theo loại object

```text
A_object_groups ≈ Σ_i (count_allocated_i × actual_footprint_i)
                + runtime/framework allocations
```

`count_allocated_i` là số **lần cấp phát**, không phải số instance còn trong collection/cache. `actual_footprint_i` là kích thước object trên heap đã gồm header, alignment, fields; đối với arrays, nó không chỉ là kích thước dữ liệu.

**Không hard-code mọi Java object header luôn 12 hoặc 16 byte**: layout và compressed references/class pointers có thể khác theo JDK/architecture; các JDK hiện đại còn có các thay đổi liên quan **compact object headers**. Dùng công cụ đo object layout phù hợp VM target khi cần ước tính chi tiết.

### 4.3. Dự toán theo request hoặc batch

```text
A_requests = N_requests × bytes_allocated_per_request

H_required ≈ startup + A_requests + A_background
           + A_retry + A_shutdown + margin
```

Ví dụ giả định: mỗi request cấp phát 500 KiB, job chạy 10.000 requests rồi kết thúc. Chỉ phần requests tạo khoảng **4.882,8125 MiB ≈ 4,77 GiB** allocations, dù mỗi request giải phóng mọi Java references ngay khi xử lý xong.

Nếu hai workers dùng cùng JVM, tổng allocations phải cộng cả hai, kể cả khi mỗi worker chỉ giữ một vài object ở cuối. Khi tasks bị retry, mỗi attempt cũng có thể tạo Java objects mới; chi phí allocations không biến mất chỉ vì một attempt thất bại.

## 5. “Cumulative” nên tính từ lúc nào?

Có hai cách đánh mốc hợp lệ, nhưng **không được trộn lẫn**:

**Từ JVM start:** tính startup/warmup, classloading, framework init, tất cả requests, background work và shutdown. Mô hình này phù hợp để dự đoán toàn bộ thời gian process trước OOME.

**Từ checkpoint sau warmup:** đo `H_baseline` ở checkpoint, cộng tất cả allocations **sau checkpoint**. Cần đảm bảo không quên việc JVM đã dùng một phần heap trước checkpoint và Epsilon không hề reclaim phần đó.

Một nguồn thiếu rất hay gặp: profiler đo allocation rate chỉ trong **business loop** nhưng bỏ qua:

- JVM bootstrap, application framework, dependency injection;
- Thread pools, executors, class loaders, JIT và management APIs;
- JSON encoding/decoding, object mapping, logging/metrics;
- Retries, exception paths, error reporting;
- Background timers, scheduled tasks, health checks;
- Input data có cardinality và độ dài thay đổi;
- Allocation trong cleanup, flush, shutdown hooks.

Epsilon không phân biệt “object của mình” với “object của framework” khi cấp phát Java heap. `-Xmx` phải đủ cho **mọi tác nhân trong process**.

## 6. TLB, TLAB, alignment và JIT làm dự toán khác lý thuyết

Độ chính xác từ một phép nhân `N × size` bị giới hạn:

- **Object/array headers:** Java arrays có header/length; footprint lớn hơn `array.length`.
- **Object alignment:** kích thước được làm tròn theo alignment của VM.
- **TLAB (Thread Local Allocation Buffer):** nhiều threads có vùng cấp phát riêng; slack/waste xuất hiện khi cấp phát blocks và không tái dùng phần trống.
- **Allocator/VM overhead:** class initialization, references, management API, string formatting, runtime allocations và thread metadata.
- **JIT optimization:** escape analysis/scalar replacement có thể loại bỏ allocations không escape; không thể đếm đơn thuần số lần xuất hiện từ khóa `new` trong source như số object vật lý.
- **Concurrency:** các threads còn tạo object phục vụ synchronization, collections, stack-trace metadata hoặc libraries, ảnh hưởng tổng allocations.
- **Heap usage counter resolution:** `getUsed()` và logging có thể cập nhật theo bước, không nhất thiết chính xác tới byte ngay tức thời trong Epsilon.

Một bài test nghiêm túc cần có **nguồn đo độc lập**: work counters, `MemoryMXBean`, Epsilon heap occupancy logs, và allocation profiler thích hợp. **Không** tự chế một con số header cố định rồi gọi đó là actual heap used trên mọi VM.

## 7. Java 11 APIs để đo heap ở checkpoint

Java có `MemoryMXBean`:

```java
MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
long used = memory.getHeapMemoryUsage().getUsed();
long committed = memory.getHeapMemoryUsage().getCommitted();
long max = memory.getHeapMemoryUsage().getMax();
```

Đây là **snippet** (phải import `java.lang.management.MemoryMXBean` và `ManagementFactory` và đặt trong method). Ba đại lượng:

| API | Diễn giải |
| --- | --- |
| `getUsed()` | Heap bytes JVM báo đang sử dụng theo ý nghĩa collector. |
| `getCommitted()` | Heap bytes đã commit; có thể lớn hơn used. |
| `getMax()` | Giới hạn heap nếu JVM cung cấp, thường liên quan `-Xmx`. |

**Đo before/after không tự cho ra toàn bộ object allocation bytes:**

- Mốc trước/sau có thể có các allocations khác chạy đồng thời.
- Lời gọi management API có thể tạo object.
- Collector có reclaim có thể chạy GC giữa hai checkpoint nên hiệu số âm hoặc nhỏ hơn actual cumulative allocation.
- Epsilon **không thu hồi**, do vậy hiệu số used thường liên quan hơn đến allocations, nhưng vẫn có TLAB/implementation details và counter granularity.
- Đối với request riêng lẻ trên server đa luồng, hiệu số **toàn process** không thể tự phân rã theo từng request.

`Runtime.getRuntime().totalMemory() - freeMemory()` cũng cung cấp một approximation của used heap, nhưng semantics/cập nhật có thể khác `MemoryMXBean` theo VM. Không trộn hai nguồn counter rồi xem chúng như đồng bộ tuyệt đối. Nên lưu lại JVM/version/flags và sử dụng một phương pháp đo nhất quán.

## 8. Ví dụ Java 11 hoàn chỉnh: EpsilonBudgetDemo.java

Ta tạo chương trình có ý nghĩa kiểm thử rõ:

1. Nhận số vòng lặp hợp lệ qua command line.
2. Trong mỗi vòng tạo một `byte[4096]`, ghi byte đầu và lưu vào ring `byte[64][]`.
3. Mảng cũ bị ghi đè trong ring không còn reachable qua ring.
4. Giữ ring cuối trong `volatile` field để kết quả còn được dùng.
5. Báo số vòng, cumulative payload bytes, số arrays còn giữ và retained payload.
6. Đọc `heap-used-before`/`after` từ `MemoryMXBean` và báo một boolean tăng/không tăng.

Không mở network, không ghi secret, không cần dependency ngoài JDK.

### 8.1. Mã nguồn đầy đủ

Lưu thành **`EpsilonBudgetDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;

public final class EpsilonBudgetDemo {
    private static final int ARRAY_BYTES = 4096;
    private static final int RETAIN = 64;
    private static volatile byte[][] retained;

    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: EpsilonBudgetDemo <iterations>");
        }
        int iterations = Integer.parseInt(args[0]);
        if (iterations <= 0 || iterations > 100000) {
            throw new IllegalArgumentException(
                    "iterations out of supported range");
        }

        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        long usedBefore = memory.getHeapMemoryUsage().getUsed();

        byte[][] ring = new byte[RETAIN][];
        for (int i = 0; i < iterations; i++) {
            byte[] data = new byte[ARRAY_BYTES];
            data[0] = (byte) i;
            ring[i % RETAIN] = data;
        }
        retained = ring;

        long usedAfter = memory.getHeapMemoryUsage().getUsed();
        int held = Math.min(RETAIN, iterations);
        long payload = Math.multiplyExact(
                (long) iterations, ARRAY_BYTES);
        long heldPayload = Math.multiplyExact(
                (long) held, ARRAY_BYTES);

        System.out.println("iterations=" + iterations);
        System.out.println("payload-bytes-cumulative=" + payload);
        System.out.println("retained-arrays=" + held);
        System.out.println("retained-payload-bytes=" + heldPayload);
        System.out.println("heap-used-before-bytes=" + usedBefore);
        System.out.println("heap-used-after-bytes=" + usedAfter);
        System.out.println("heap-used-increased=" +
                (usedAfter > usedBefore));
    }
}
```

**Giải thích thiết kế:**

- `Math.multiplyExact` để tính toán có kiểm tra overflow thay vì ngầm wrap về số âm.
- `byte[4096]` tạo đủ allocation pressure mà không cần file hoặc request thực.
- `ring[i % RETAIN]` chỉ giữ lại 64 references; các phần tử bị thay thế không còn reachable từ ring.
- `retained` được đặt `volatile` để ring escape ra field, giảm rủi ro test được tối ưu thành không làm gì.
- Bốn dòng đếm allocations/payload là deterministic với input tương ứng; **không** chốt cố định số `heap.used` cho mọi JDK.
- JVM còn có các object khác và có thể thay đổi object layout/JIT, vì vậy bộ đếm `iterations` không phải một allocation profiler toàn process.

### 8.2. Biên dịch và chạy bằng Epsilon

Cần JDK 11 trở lên có HotSpot Epsilon:

```bash
javac -encoding UTF-8 --release 11 EpsilonBudgetDemo.java
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC \
  -Xms96m -Xmx96m -Xlog:gc=info \
  EpsilonBudgetDemo 12000
```

**Dòng output tất định từ ứng dụng:**

```text
iterations=12000
payload-bytes-cumulative=49152000
retained-arrays=64
retained-payload-bytes=262144
```

Những dòng `heap-used-before-bytes`/`heap-used-after-bytes` là số đo thời điểm chạy; chúng có thể đổi qua mỗi phiên bản/OS/vòng lặp. Chỉ cần xác minh các giá trị này hợp lý và **không dự đoán bằng phép nhân `N*4096` rồi nói chắc chắn bằng đúng heap.used**.

### 8.3. Số đo thực tế từ một lần chạy

Đã biên dịch `javac -encoding UTF-8 --release 11` và chạy bằng **Azul OpenJDK 24.0.2**. Với Epsilon `-Xms96m -Xmx96m`, một lần chạy cho **stdout chính xác**:

```text
iterations=12000
payload-bytes-cumulative=49152000
retained-arrays=64
retained-payload-bytes=262144
heap-used-before-bytes=1887992
heap-used-after-bytes=53339568
heap-used-increased=true
```

**Đây là output quan sát ở đúng lần chạy đó, không phải expected exact output cho mọi máy.** `1887992` và `53339568` thay đổi khi JVM/provider/JIT/runtime allocations khác nhau. Các con số `iterations`, `payload-bytes-cumulative` và `retained-...` được suy ra trực tiếp từ mã nên ổn định khi chạy hết.

**Diễn giải mức tăng heap:**

```text
Heap used trước                 1.887.992 byte
Heap used sau                  53.339.568 byte
Heap used tăng                 51.451.576 byte
Tổng payload mảng              49.152.000 byte
Payload mảng còn giữ              262.144 byte
```

Mức tăng lớn hơn payload vì object headers, alignment, TLAB/VM overhead và allocations phụ trợ. Không diễn giải chênh lệch đúng bằng “header của mỗi byte[]” vì nó còn gồm allocations khác.

## 9. Đối chứng với G1: cùng workload, heap có thể được tái sử dụng

Dùng cùng Java source, heap limit 96 MiB, nhưng chọn collector có reclaim:

```bash
java -XX:+UseG1GC -Xms96m -Xmx96m -Xlog:gc=info \
  EpsilonBudgetDemo 12000
```

Một lần chạy trên cùng Azul OpenJDK 24.0.2 cho log và output:

```text
[0.006s][info][gc] Using G1
[0.046s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 48M->1M(96M) 0.684ms
iterations=12000
payload-bytes-cumulative=49152000
retained-arrays=64
retained-payload-bytes=262144
heap-used-before-bytes=2212632
heap-used-after-bytes=2867992
heap-used-increased=true
```

**Đây là log từ đúng một lần chạy**, không phải cam kết G1 luôn còn `2.867.992 byte`. Phần important là `GC(0) Pause Young ... 48M->1M` cho thấy collector đã thu hồi nhiều Java-heap objects khi không còn reachable. Cùng source và cùng payload, Epsilon không có pha reclaim đó.

**Không suy ra từ số heap.used cuối rằng G1 nhanh hơn hoặc throughput tốt hơn Epsilon.** Với collector có reclaim, CPU/pause/throughput cần benchmark riêng; Epsilon có thể làm giảm GC interference trong một job ngắn nhưng đánh đổi bằng memory consumption và rủi ro OOME.

## 10. Dự trù quá thấp: kiểm thử OutOfMemoryError có kiểm soát

Giảm từ heap 96 MiB xuống **16 MiB** nhưng giữ **12.000 mảng × 4096 byte**:

```bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC \
  -Xms16m -Xmx16m -Xlog:gc=info \
  EpsilonBudgetDemo 12000
```

Đây là một **expected-failure test** trong JVM riêng, không được làm trên production process. Tổng payload riêng mảng đã là **49.152.000 byte**, lớn hơn 16 MiB, chưa tính phí runtime; Epsilon không thu hồi nên không thể hoàn thành vòng lặp.

Trích kết quả thực quan sát:

```text
[0.006s][info][gc] Using Epsilon
...
[0.037s][info][gc] Heap: 16384K reserved, 16384K (100.00%) committed, 16375K (99.95%) used
Terminating due to java.lang.OutOfMemoryError: Java heap space
```

Trong lần thử đó JVM **kết thúc với exit code 3**. Con số **3 không được xem là API contract của Epsilon** trên mọi JDK/OS. Điều cần kiểm chứng ở CI là **exit code không bằng 0** và có bằng chứng phù hợp về heap exhaustion/expected OOME.

### 10.1. `ExitOnOutOfMemoryError`

Trên các HotSpot Epsilon builds đã kiểm tra, Epsilon **mặc định chọn hành vi kết thúc JVM khi OOME** nếu người dùng không cấu hình khác; cờ HotSpot liên quan là **`-XX:+ExitOnOutOfMemoryError`**. Chi tiết default/exit code cần kiểm tra trên VM/vendor thực tế. **Không** viết code `catch (OutOfMemoryError)` rồi giả định có thể phục hồi và tiếp tục cấp phát — khi Epsilon đã dùng hết heap, object chết vẫn không làm xuất hiện vùng free mới.

Nếu cần thử nghiệm OOME, chạy chương trình trong **process con** và để parent test runner đọc exit status/log. Một `OutOfMemoryError` được xử lý như “success test” trong đúng expected-failure case, **không** phải lỗi được phép bỏ qua trong một business application.

### 10.2. Vì sao `System.gc()` không cứu được Epsilon?

`System.gc()` là yêu cầu GC ở cấp Java API, không phải mệnh lệnh bắt buộc HotSpot phải reclaim một số byte. Epsilon là **no-op collector** và không có cơ chế reclaim heap dù các references đã biến mất. **Không** khắc phục OOME của Epsilon bằng `System.gc()`, ép full GC, gán các biến về `null` hoặc chờ thêm vài giây.

Nếu một workload phải chạy lâu dài và tiếp tục cấp phát, hãy dùng collector **có reclaim** (ví dụ G1/ZGC), điều chỉnh allocations hoặc chia job thành các process hữu hạn có kiểm soát thay vì cố sửa Epsilon thành GC bình thường.

## 11. Đọc GC logs Epsilon mà không hiểu sai

Ví dụ đã chạy:

```bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC \
  -Xms96m -Xmx96m -Xlog:gc=info \
  EpsilonBudgetDemo 12000
```

Trích những dòng thực quan sát:

```text
[0.006s][info][gc] Using Epsilon
[0.041s][info][gc] Heap: 98304K reserved, 98304K (100.00%) committed, 5234K (5.32%) used
[0.048s][info][gc] Heap: 98304K reserved, 98304K (100.00%) committed, 52089K (52.99%) used
```

Đây là **log heap occupancy progress**, **không phải** danh sách các GC collections reclaiming memory. Epsilon có thể ghi tiến độ dùng heap theo một số mức phần trăm; không nên đếm số dòng `Heap:` như số lần `System.gc()`/GC cycle hay số object được tạo.

Các dấu mốc cần quan sát:

- **`Using Epsilon`:** xác nhận đúng GC được chọn.
- **`reserved`, `committed`, `used`:** tách virtual reservation, commit và heap occupancy.
- **Tỷ lệ % used:** cho biết tiến gần giới hạn heap, không phải tỷ lệ object còn sống.
- **Log OOME:** dấu hiệu model cumulative allocation đã vượt budget.
- **Exit code:** xác nhận test/process thực sự thành công hay kết thúc bất thường.

**Một số flags riêng Epsilon** như `EpsilonPrintHeapSteps` và `EpsilonUpdateCountersStep` có trong nhiều HotSpot versions, nhưng chúng là **implementation-specific experimental settings**, cần kiểm tra runtime thực tế bằng `-XX:+PrintFlagsFinal`/tài liệu. Bài đo căn bản không cần những flags này, không khuyến nghị copy tuning options từ một build cũ sang mọi JDK.

## 12. Biến `-Xms`, `-Xmx`, `AlwaysPreTouch` trong benchmark

| Flag | Chức năng | Liên hệ Epsilon |
| --- | --- | --- |
| `-Xmx<size>` | Giới hạn heap tối đa. | Cần đủ cho **cumulative heap allocations**; thiếu sẽ OOME. |
| `-Xms<size>` | Dung lượng heap ban đầu/tối thiểu. | Có thể đặt bằng `-Xmx` để giảm biến động heap expansion khi benchmark. |
| `-XX:+AlwaysPreTouch` | Pre-touch committed heap pages khi startup. | Có thể ổn định chi phí page faults trong lúc chạy nhưng **tăng startup và memory pressure**. |
| `-Xlog:gc=info` | Đọc log GC/occupancy khi HotSpot hỗ trợ. | Xác nhận collector, theo dõi used; output phụ thuộc JDK. |
| `-XX:+UnlockExperimentalVMOptions` | Cho phép experimental VM flags. | Bắt buộc đứng trước `-XX:+UseEpsilonGC` trên các builds coi Epsilon experimental. |
| `-XX:+UseEpsilonGC` | Chọn Epsilon. | Không được bật đồng thời với một collector khác. |
| `-XX:+UseG1GC` | Chọn G1 để đối chứng. | Tái sử dụng vùng memory của các object chết sau GC. |

**`-Xms = -Xmx` không tự khiến Epsilon được phép reclaim**, và không phải lựa chọn tốt cho mọi container. Nó có thể làm **committed memory** cao hơn từ lúc startup, đặc biệt nếu kết hợp `AlwaysPreTouch`. Đừng đặt `-Xmx` bằng đúng RAM limit của container, vì JVM còn native/metaspace/direct memory ngoài heap.

## 13. Java heap khác với native/off-heap/container memory

Công thức Epsilon ở các mục trước chỉ tính **Java heap**. Tổng memory footprint của JVM còn có:

- Metaspace và loaded-class metadata;
- JIT code cache, compiler threads;
- Thread stacks, JNI/native libraries;
- DirectByteBuffer, mapped memory, native allocations;
- GC/JVM bookkeeping, allocator internals;
- OS page tables và các mappings khác.

| Chỉ số | Không được nhầm với |
| --- | --- |
| `heap.used` | Tổng memory cả JVM hoặc RSS. |
| `heap.committed` | Chính xác lượng resident physical RAM. |
| `heap.max`/`-Xmx` | Giới hạn toàn bộ cgroup/container. |
| `RSS` | Số byte object Java đang sống. |
| `container.memory.limit` | Heap limit cho phép đặt trọn bằng giá trị đó. |

Nếu container chỉ có 128 MiB, `-Xmx128m` có thể khiến process bị OOM-kill do off-heap/native memory dù Java heap chưa hết. **Cần dành dư RAM ngoài `-Xmx`**, điều chỉnh theo OS, thread count, direct buffers và runtime.

Ngược lại, Virtual memory **reserved** có thể rất lớn nhưng không tương đương RSS thực. Chỉ số `Heap: 98304K reserved, ... committed` trong demo xuất hiện vì đã cố tình đặt `-Xms96m -Xmx96m`.

## 14. Đo allocation rate có ý nghĩa khi nào?

Nếu chỉ có số liệu retained heap, khó dự đoán Epsilon runtime. Cần biết **allocation rate**:

```text
r(t) = Java-heap bytes allocated per second

A(T) = ∫ r(t) dt
```

Ví dụ với process xử lý 10.000 requests, phải đo allocation rate trong **toàn thời gian** hoặc allocation bytes per request. Nếu rate thay đổi theo burst, dùng **worst-case cumulative** cho toàn job; không chỉ trung bình của 30 giây tải nhẹ.

Nguồn dữ liệu hỗ trợ:

| Công cụ | Giá trị | Hạn chế |
| --- | --- | --- |
| App instrumentation | Đếm số batch/requests, đối tượng nghiệp vụ tạo ra. | Không bao trùm mọi framework/JDK allocation. |
| `MemoryMXBean` dưới Epsilon | Cho biết total heap usage trước/sau một workload. | Không phải per-request profiler chính xác; counters update có độ phân giải. |
| Epsilon GC logs | Heap occupancy tăng và pressure tới `-Xmx`. | Không đo retained set hoặc number of allocations. |
| JFR allocation-related events | Phân tích allocation sites, size distribution theo JDK/settings. | Có thể sampling; event schema khác theo JDK version. |
| JVMTI sampled allocation | Mẫu object allocations theo class/thread/stack. | Samples không phải mọi allocation; cần estimator phù hợp. |
| Heap dump | Object graph reachable tại thời điểm snapshot. | **Không** đo cumulative allocations. |
| OS/cgroup metrics | RSS, native memory pressure, OOMKill. | Không phân loại chính xác Java-heap object allocation. |

Nếu dùng Java 11, **không** lấy tên một JFR event mới từ JDK 25 rồi khẳng định nó có ở runtime Java 11; kiểm tra `jfr metadata`, recording settings và JDK build thật. JFR và JVMTI còn có overhead cần đo. Không yêu cầu công cụ đo số byte chính xác tới từng object nếu sampler chỉ cung cấp statistical samples.

## 15. Heap leak hay allocation pressure?

Dưới Epsilon, **heap occupancy tăng là bình thường**, không phải bằng chứng trực tiếp của leak.

**Allocation pressure:** rất nhiều object/byte được tạo, dù sống cực ngắn. Một batch với `ArrayList`/DTO/JSON objects có thể tạo nhiều trăm MB chỉ để xử lý vài MB input.

**Retained heap leak:** object vẫn reachable lâu hơn dự kiến, khiến collector có reclaim **cũng không thể giải phóng** chúng.

**Epsilon no-reclaim behavior:** object có chết cũng không được reclaim. Vì vậy cuối job heap.used lớn **không phân biệt** object còn sống hay đã chết.

Phương pháp điều tra leak đúng:

1. Chạy với G1/ZGC (collector có reclaim) cùng workload đại diện.
2. Xem sau GC cycles và xu hướng live set, có cần heap dump không.
3. Phân tích retained object graph/dominator tree và GC roots bằng công cụ tin cậy.
4. Phân biệt throughput/allocations từ retain path.
5. Dùng Epsilon chỉ làm phép thử **tổng cấp phát**, không làm công cụ leak diagnosis duy nhất.

Trong demo, Epsilon heap used ~53,3MB và retained array payload chỉ 256KiB là **ví dụ allocation churn**, không chứng minh có bug giữ references.

## 16. Phương pháp thiết lập ngân sách trên môi trường CI

### 16.1. Test không được vượt budget

```text
javac --release 11
       |
       v
Start a separate JVM
with Epsilon + fixed -Xmx
       |
       v
Run bounded workload (all inputs/threads)
       |
    +--+------------------+
    |                     |
exit=0                  nonzero/OOME
    |                     |
 PASS within budget        FAIL budget/runner
    |
    v
Record JDK/flags/input/used/log and repeat
```

Để test đáng tin:

- Mỗi test case ở **process riêng**, không đổi collector trong cùng JVM.
- Input, time limit, -Xmx, JDK vendor/version và các tùy chọn tracing/instrumentation cố định.
- Chạy cả **case worst-case**, không chỉ happy path.
- Tách CI test **OOME kỳ vọng** khỏi test “phải thành công”.
- Không làm test process chết ảnh hưởng test suite/process cha.
- Thu stdout, stderr, exit code, `Using Epsilon` và bộ nhớ OS/container.
- Có margin cho variation và lặp nhiều lần nếu kiểm tra regression nhạy.

### 16.2. Regression test có so sánh baseline

Ví dụ, phiên bản A với Epsilon 96MiB chạy được 12.000 items. Phiên bản B sau thay đổi JSON parser không chạy được hoặc used tăng đáng kể. Cần:

1. Chạy cả A/B trên cùng JDK/flags/input/điều kiện warmup.
2. So sánh **cumulative heap usage** hoặc threshold memory đạt được.
3. Phân tích allocation sites qua JFR/JVMTI nếu có dấu hiệu churn mới.
4. Kiểm tra source thay đổi object layout, instrumentation và thư viện.
5. Với service production, chạy lại trên collector có reclaim để xem tác động throughput/GC/latency thực.

Không để budget CI lớn đến mức mọi regression đều qua, cũng không đặt sát một lần đo ngẫu nhiên khiến test flaky.

### 16.3. Job đã giới hạn thời gian mà vẫn không nên dùng Epsilon?

Nếu job xử lý dữ liệu không tin cậy, retry không giới hạn hoặc phụ thuộc downstream có thể treo, **total allocation** có thể vượt dự toán. Lúc đó giải pháp an toàn thường là:

- Thiết kế **time/size/batch limits**;
- Giới hạn concurrency, số attempts và queue buffers;
- Dùng collector có reclaim;
- Dùng process lifecycle/restart có kiểm soát khi đúng yêu cầu;
- Đặt memory/CPU limits từ hạ tầng;
- Theo dõi OOMKill, exit code và không mất dữ liệu khi worker restart.

Một job “đáng lẽ chạy 2 giây” không phải bằng chứng nó sẽ không chạy 5 phút khi mạng lỗi.

## 17. Những sai lầm khi dự trù Epsilon

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| “Epsilon là GC thu hồi nhanh, nên heap nhỏ vẫn đủ.” | Không, **không reclaim**. |
| “Epsilon bị xóa và không còn áp dụng sau Java 11.” | Không: vẫn có trên HotSpot builds mới, nhưng là **experimental** và chỉ phù hợp use cases đặc biệt. |
| “`-XX:+UseEpsilonGC` luôn bật được không cần unlock.” | Với experimental Epsilon, phải có `-XX:+UnlockExperimentalVMOptions` **trước**. |
| “Heap chỉ cần đủ live set.” | Epsilon cần đủ **cumulative allocation footprint** toàn phiên. |
| “Reference đã bị gán null thì heap được trả lại.” | Không với Epsilon. |
| “`System.gc()` giúp thu hồi Epsilon.” | Không có reclaim hữu ích. |
| “Có `OutOfMemoryError` thì catch rồi retry.” | Không an toàn; bộ nhớ vẫn đầy, Epsilon có thể thoát process. |
| “`-XX:+ExitOnOutOfMemoryError`/exit code luôn giống mọi vendor.” | Kiểm tra VM target; trên HotSpot Epsilon đã kiểm thử, exit mặc định có thể bật khi OOME. |
| “12.000 × 4.096 chính xác bằng heap.used tăng.” | Chỉ là **payload**; headers, alignment, TLAB và allocations khác không được đếm. |
| “Có `new` trong source là JVM nhất định allocate object trên heap.” | JIT có thể loại bỏ một số allocations không escape. |
| “Đếm retained arrays là đo tổng allocations.” | Không: số references còn giữ khác tổng số mảng từng tạo. |
| “Epsilon used cứ tăng chứng minh ứng dụng leak.” | Đây là đúng mô hình không reclaim, leak phải kiểm tra retained graph với GC có reclaim. |
| “Heap.max bằng memory limit của container.” | Không: `-Xmx` chỉ Java heap, còn native/metaspace/direct/stacks. |
| “Đặt `-Xmx` bằng RAM container cho an toàn.” | Có thể dẫn tới OOMKill vì memory ngoài heap. |
| “Không GC pause nghĩa là không có JVM pause.” | JVM/OS còn JIT/safepoint/page faults/thread scheduling. |
| “Epsilon luôn nhanh hơn G1/ZGC trong sản phẩm thật.” | Phải benchmark; chi phí và khả năng OOME thay đổi tradeoff. |
| “JFR/heap dump tự trả tổng lifetime allocation chính xác.” | Sampling/snapshot có semantics riêng; cần hiểu cách đo. |
| “-Xms=-Xmx luôn tiết kiệm RAM.” | Có thể tăng committed footprint/startup; phù hợp một số benchmark, không universal. |
| “25% safety margin là chuẩn chung.” | Chỉ là **giả định ví dụ**; margin theo workload, risk và đo thật. |
| “Khi nâng JDK, object footprint luôn không đổi.” | Layout, JIT, allocation behavior có thể khác. |
| “Một lần chạy pass đủ chứng minh mọi input sẽ pass.” | Không: cần giới hạn workload và test worst case. |

## 18. Checklist triển khai

1. Xác định **use case**: Epsilon chỉ dành cho benchmark/memory pressure tests/bounded jobs đã phân tích rủi ro.
2. Xác minh JVM hỗ trợ Epsilon, bật `-XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC` đúng thứ tự.
3. Ghi **runtime JDK**: `javac --release 11` chỉ bảo đảm source/API Java 11, không thay collector của runtime hiện tại.
4. Chọn checkpoint đo rõ ràng, không double-count startup allocations.
5. Tính cumulative Java heap allocations của toàn process, không chỉ retained objects.
6. Đo allocations của tất cả threads/phases, kể cả framework, background, retries và shutdown.
7. Không lấy `array.length`/input size làm full object footprint: tính header, alignment, TLAB, runtime overhead.
8. Dùng `MemoryMXBean` và Epsilon occupancy logs để kiểm chứng ước lượng, chấp nhận VM-level counter granularity.
9. Cộng safety margin và test worst-case input/concurrency/job duration.
10. Đặt `-Xmx` theo heap budget, **để dư memory ngoài heap** cho container/JVM native.
11. Chạy benchmark/test trong process cô lập; với OOME case, parent nhận nonzero exit và log.
12. Không dùng `System.gc()` hay bắt `OutOfMemoryError` làm giải pháp thu hồi Epsilon.
13. Nếu ứng dụng chạy lâu và liên tục allocate, dùng GC có reclaim như G1/ZGC thay vì Epsilon.
14. Khi cần điều tra leak, dùng retained heap analysis trên GC có reclaim; Epsilon growth không chứng minh leak.
15. So sánh version A/B trên cùng runtime/flags/input, dùng profiler để xác định allocation hot spots khi cần.
16. Bảo vệ logs/profiler data; heap dumps/stack traces có thể chứa dữ liệu cá nhân hoặc bí mật.
17. Ghi vào báo cáo **JDK vendor/version, flags, -Xms/-Xmx, used peak, allocation volume, time window, exit status, giới hạn phép đo**.

## 19. Kết luận

**Epsilon không thu hồi Java heap**, nên dự trù theo **cumulative allocation footprint**, không theo live set cuối cùng. Ví dụ thực chạy đã chứng minh:

- Cấp phát tổng **49.152.000 byte payload** qua **12.000 mảng**.
- Chỉ còn giữ **262.144 byte payload** của 64 mảng.
- Với Epsilon 96 MiB, trong một lần chạy JDK 24, heap used tăng từ ~**1,89 MB** lên ~**53,34 MB**.
- Với Epsilon 16 MiB và cùng workload, JVM dừng vì **`OutOfMemoryError: Java heap space`**.
- Với G1, GC có thể reclaim các mảng đã chết, nên mức heap.used cuối trong test nhỏ hơn nhiều.

Điều cần ghi nhớ khi thiết kế là **tổng lượng cấp phát × toàn bộ vòng đời process**, cộng chi phí startup/runtime, TLAB/object layout và safety margin. Khi tổng allocation không thể bị giới hạn, **không chọn Epsilon làm collector cho dịch vụ cần chạy mãi**.

### Tài liệu chính thức và nguồn kiểm chứng

- [OpenJDK JEP 318 — Epsilon: A No-Op Garbage Collector (Java 11, Experimental)](https://openjdk.org/jeps/318)
- [Oracle Java 11 Release Notes — Epsilon, no-op semantics và use cases](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html)
- [Oracle Java 11 `java` command, `-Xmx`, experimental flags và Unified Logging](https://docs.oracle.com/en/java/javase/11/tools/java.html)
- [Oracle Java 11 — `java.lang.management.MemoryMXBean`](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Oracle Java 11 — HotSpot GC Tuning Guide, heap footprint và GC costs](https://docs.oracle.com/en/java/javase/11/gctuning/)
- [Oracle Java 25 — GC Tuning Guide, current reclaiming collector behavior](https://docs.oracle.com/en/java/javase/25/gctuning/)
- [OpenJDK HotSpot gc_globals.hpp — `UseEpsilonGC` still experimental](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/gc_globals.hpp)
- [Quarkus official Native Image reference — Native Image Epsilon semantics, distinct JVM flags](https://quarkus.io/guides/native-reference/)
