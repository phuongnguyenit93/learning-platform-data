# Epsilon GC không thu hồi bộ nhớ và mục đích kiểm thử có kiểm soát trong Java 11

**Chủ đề cha:** Epsilon và phép đo  
**Đề bài:** GC không thu hồi và mục đích kiểm thử có kiểm soát  
**Phạm vi:** JEP 318, cơ chế no-op garbage collector của HotSpot, cấp phát và cạn Java heap, cờ chạy JVM trong Java 11, phân biệt allocation rate với live set, thử nghiệm allocation budget, đo tác động GC, xử lý OutOfMemoryError trong tiến trình riêng, giới hạn thực nghiệm và so sánh với GC có thu hồi. Chỉ trình bày **kiến thức vẫn còn áp dụng hiện nay**; không khuyên sử dụng cờ/collector lỗi thời hoặc coi Epsilon là GC mặc định để vận hành production.

**Epsilon GC** (JEP 318, xuất hiện từ Java 11) là **garbage collector không thực hiện thu hồi** (*no-op garbage collector*). Nó hỗ trợ JVM **cấp phát object trên Java heap**, nhưng **không đánh dấu/thu gom và tái sử dụng vùng heap của object đã không còn được tham chiếu**. Khi đã sử dụng hết ngân sách cấp phát của heap, JVM có thể phát sinh `OutOfMemoryError` và **chấm dứt tiến trình**. Vì vậy Epsilon chủ yếu là công cụ để **thử nghiệm, đo lường, nghiên cứu runtime và kiểm chứng ngân sách bộ nhớ trong điều kiện kiểm soát**, không phải lựa chọn GC thông thường cho dịch vụ Java sống lâu.

Điểm cốt lõi: **“Không GC” không có nghĩa “không dùng bộ nhớ”**. Epsilon vẫn có allocator, heap bookkeeping, thread-local allocation buffers và hoạt động JVM thông thường; nó chỉ bỏ đi cơ chế *reclamation* của Java heap. Đây chính là lý do Epsilon có ích để cô lập một phần chi phí GC trong phép thử, đồng thời nguy hiểm nếu chạy trên workload có phát sinh rác lâu dài.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khác biệt giữa **allocation**, **object reachability**, **heap reclamation** và **process termination**.
2. Phân biệt Epsilon với G1 và các collector thực sự thu gom rác.
3. Bật Epsilon đúng cú pháp trên **HotSpot Java 11**: `-XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC`, đặt `-Xms`/`-Xmx` có chủ đích.
4. Hiểu vì sao `System.gc()` không thể biến Epsilon thành collector có thu hồi và vì sao bỏ reference cũng không giải phóng heap cho vòng cấp phát tiếp theo.
5. Tạo phép thử **có giới hạn heap và số vòng lặp**; tách trường hợp cố tình cạn bộ nhớ vào Java **child process**, không làm hỏng dịch vụ/test runner chính.
6. Đọc thông tin collector và heap qua `ManagementFactory`/`MemoryMXBean`/`GarbageCollectorMXBean`, kiểm tra GC log với `-Xlog:gc=info`.
7. So sánh cùng workload dưới G1 và Epsilon, nhưng **không suy diễn** “Epsilon luôn nhanh nhất”.
8. Phân biệt tổng cấp phát với **live set**, phát hiện allocation pressure với xác nhận memory leak thực sự.
9. Thiết kế phép thử performance, footprint và OOME có giới hạn thời gian/tài nguyên, bao gồm CI, subprocess exit code và cleanup.
10. Nhận diện các trường hợp **không nên dùng Epsilon**: service dài hạn, runtime có vòng đời không giới hạn, job không có allocation budget, workload phụ thuộc cleanup theo GC.

## 2. Epsilon “không thu hồi” nghĩa là gì?

Một GC thu gom như G1 có thể tìm những object không còn reachable từ GC roots rồi thu hồi vùng nhớ của chúng để cấp phát cho object mới. Epsilon **không làm điều đó**.

Ví dụ, với chương trình:

```java
byte[] previous = new byte[1024 * 1024];
previous = null;
byte[] next = new byte[1024 * 1024];
```

Đây là trích đoạn, không phải class runnable. Sau `previous = null`, object đầu tiên có thể không còn reachable, nhưng **Epsilon không lấy lại 1 MiB đã cấp phát**. Object thứ hai cần **thêm** dung lượng heap. Nếu lặp lại đủ nhiều lần, ứng dụng có thể hết heap dù tại một thời điểm chỉ giữ reference đến một object nhỏ.

Điều này khác cơ bản với “ứng dụng bị memory leak”: một chương trình có thể **không giữ references cũ** nhưng vẫn hết heap dưới Epsilon vì đó là **thiết kế chủ động của collector**. Không được kết luận “memory leak” chỉ từ đồ thị heap tăng khi chạy Epsilon.

### 2.1 Luồng xử lý bộ nhớ

```text
Application: new Object()/new byte[]
               |
               v
         Epsilon allocator
               |
      Có chỗ trống trong heap?
          /               \
        Có                 Không
         |                   |
  Trả object mới        Heap exhausted
         |                   |
  Reference mất              v
         |              OutOfMemoryError /
         v              process termination
  Không có reclamation        |
         |                   v
  Chỗ cấp phát không    Kết thúc run,
  được tái sử dụng      heap trả lại cho OS
  trong cùng JVM        khi tiến trình kết thúc
```

Heap của Epsilon vẫn có **dung lượng hữu hạn** do JVM và `-Xmx`/ergonomics quyết định. Epsilon không “chuyển object sang stack” và không cấp phát mãi ra native RAM vượt vô hạn. Những phép đo GC trong bài áp dụng với **Java heap**, không phải mọi nguồn sử dụng memory của JVM.

### 2.2 Bảng phân biệt

| Thuộc tính | Epsilon GC | Collector có thu hồi, ví dụ G1 |
|---|---|---|
| Cấp phát object trên heap | Có | Có |
| Nhận diện/thu hồi object không còn reachable | **Không** | Có |
| Heap allocation sau khi bỏ reference | Vẫn tăng theo allocation budget | Có thể tái sử dụng vùng đã reclaim |
| Stop-the-world do **chu kỳ thu gom rác** | Không có chu kỳ thu gom thông thường | Có thể có pause/pha GC tùy collector |
| `System.gc()` để lấy lại heap | **Không giúp reclaim** | Có thể yêu cầu GC, không đảm bảo hành vi/thời điểm tuyệt đối |
| GC pressure khi app sống lâu | Dẫn đến cạn heap nếu tiếp tục cấp phát | GC cố gắng lấy lại vùng có thể thu hồi |
| Trường hợp phổ biến | Phép đo/kiểm thử, job rất ngắn đã chứng minh footprint | Dịch vụ, batch dài, workload chung |
| Khi hết heap | Có thể kết thúc JVM do OOME | Có thể OOME nếu không còn chỗ cho object sống hoặc heap quá nhỏ |
| Kết luận “nhanh hơn” | Không thể kết luận nếu chưa đo | Không thể kết luận nếu chưa đo |

Epsilon bỏ đi chi phí **thu hồi**, nhưng không bảo đảm loại bỏ mọi safepoint, cấp phát, memory commit, synchronization, JIT hoặc hệ quả hiệu năng khác. Không gọi nó là “garbage collector hiệu quả nhất cho mọi ứng dụng”.

## 3. Nguồn gốc và trạng thái hỗ trợ

**JEP 318 — Epsilon: A No-Op Garbage Collector** được tích hợp từ **JDK 11** với mục tiêu cung cấp cơ chế GC tối giản, xử lý cấp phát nhưng không reclaim memory. Trong HotSpot Java 11, Epsilon được đánh dấu **experimental**; phải chủ động mở khóa các tùy chọn thử nghiệm mới bật được. Đây **không phải** một tính năng đã lỗi thời chỉ vì mang nhãn experimental: nó vẫn có ích trong các quy trình kiểm thử và nghiên cứu JVM hiện nay, nhưng **không có ý định là lựa chọn production GC chung**.

Trên một số bản JDK hiện đại, Epsilon vẫn được cung cấp và vẫn gắn với cờ thử nghiệm. Tuy nhiên, collector availability, startup warnings và hành vi cờ **phụ thuộc phiên bản/vendor/VM**; phải kiểm tra chính JVM mục tiêu. Không mặc định OpenJ9, HotSpot và GraalVM/native runtime hiểu mọi cờ giống nhau.

### 3.1 Lệnh bật Epsilon trên HotSpot Java 11

```bash
javac --release 11 -encoding UTF-8 EpsilonNoReclaimDemo.java

java -Xms32m -Xmx32m \
  -XX:+UnlockExperimentalVMOptions \
  -XX:+UseEpsilonGC \
  EpsilonNoReclaimDemo
```

Dấu `\` ở cuối dòng là cú pháp **shell kiểu Bash**; với Windows PowerShell nên chạy cùng lệnh trên **một dòng**, hoặc dùng backtick continuation của PowerShell đúng chỗ. Bốn demo trong bài có lệnh một dòng để dễ copy trên nhiều môi trường.

Ý nghĩa:

- `-XX:+UnlockExperimentalVMOptions` mở các tùy chọn HotSpot experimental. **Đặt trước** `-XX:+UseEpsilonGC` để JVM xử lý flag đúng.
- `-XX:+UseEpsilonGC` chọn no-op collector.
- `-Xms32m` thiết lập initial heap 32 MiB.
- `-Xmx32m` giới hạn maximum heap 32 MiB; dùng mức nhỏ cho demo trong **tiến trình test riêng**.
- `-Xms` bằng `-Xmx` giúp tránh biến thiên do heap resize và làm phép đo dễ kiểm soát hơn; đổi lại commit/footprint ban đầu có thể tăng.
- `--release 11` chỉ bảo đảm API/classfile **tương thích Java 11** khi biên dịch, không biến JDK runtime hiện tại thành Java 11.

**Không sử dụng cấu hình này cho dịch vụ đang phục vụ người dùng**: 32 MiB chỉ là ví dụ kỹ thuật, và Epsilon sẽ không thu gom object dù bạn tăng `-Xmx` lên hàng GB.

### 3.2 Xác nhận JVM đã dùng đúng collector

Có thể bật GC log:

```bash
java -Xms32m -Xmx32m -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -Xlog:gc=info -version
```

Với HotSpot hỗ trợ, log startup có thông tin kiểu **`Using Epsilon`**; output khác giữa các JDK/vendor và có thể in thêm cảnh báo/đề xuất liên quan memory pre-touch, heap sizing. Trong Java code, kiểm tra `ManagementFactory.getGarbageCollectorMXBeans()` và tên collector; đây là cách demo 1 và 2 dùng để phát hiện Epsilon khi thử nghiệm.

**Đừng bật hai collector đối nghịch trong cùng lệnh** (ví dụ Epsilon và G1) rồi giả định JVM sẽ tự tạo hybrid mode. Hãy chạy **hai tiến trình riêng** với flags riêng nếu muốn so sánh.

### 3.3 Tên flag theo vendor

Trên HotSpot, dùng `-XX:+UseEpsilonGC`. Một số VM khác, ví dụ Eclipse OpenJ9, có chính sách **no-GC** của riêng mình (`-Xgcpolicy:nogc` hoặc tùy chọn tương thích do vendor công bố). Chúng có thể cùng mục tiêu nhưng **không phải tên flag bảo đảm liên thông**. Bài này kiểm chứng HotSpot có Epsilon; nếu VM từ chối flag, xác nhận VM vendor trước, không dùng một flag tình cờ được ghi trên blog cho môi trường khác.

## 4. Các trường hợp sử dụng còn phù hợp

### 4.1 Baseline hiệu năng khi bỏ phần chi phí GC

Để đánh giá GC overhead, có thể chạy một workload có giới hạn allocation dưới GC chuẩn và dưới Epsilon với:

- Cùng binary/app version/JDK build và hardware.
- Cùng input dataset, số thao tác, phân bố object sizes.
- Cùng `-Xms`/`-Xmx` và startup flags khác nếu hợp lý.
- Warm-up, JIT compilation, pinning/thermal conditions, số threads có kiểm soát.
- Đo throughput/latency/CPU/allocations/heap/GC logs.
- Bảo đảm workload Epsilon **không chạm ngưỡng cạn heap**, vì như thế so sánh thất bại.

Mục tiêu là tìm một **điểm tham chiếu không có reclamation GC**, không phải quảng cáo “độ trễ bằng không” cho mọi thành phần JVM. Epsilon có thể khác G1 cả về allocator, barriers và heuristics, nên **hiệu số runtime không thể diễn dịch hoàn toàn là thời gian pause của G1**. Nếu cần microbenchmark đáng tin, dùng framework được bảo trì như **JMH** và nhiều fork/repetition, không dựa vào một `System.nanoTime` duy nhất.

### 4.2 Thử ngân sách cấp phát và sức ép bộ nhớ

Epsilon giúp biến một dạng câu hỏi từ “GC có kịp dọn không?” thành “đoạn chương trình đã yêu cầu bao nhiêu allocation trước khi hoàn thành?”. Ví dụ một batch phải xử lý trong **allocation budget** đã được kiểm soát. Nếu một phiên bản code bất ngờ tạo quá nhiều temporary objects, nó có thể vượt ngưỡng đã đặt.

Đây là kiểm thử **allocation pressure**, không phải đo live memory chính xác. Nếu ứng dụng chỉ giữ 1 MiB state nhưng mỗi lần thực hiện cấp phát 100 MiB rồi bỏ hết, Epsilon vẫn tính vào heap budget, trong khi một GC thu hồi có thể xử lý được nhờ tái sử dụng vùng nhớ.

Có thể chạy hai kịch bản:

1. **Positive:** job giới hạn N thao tác và heap đủ lớn, phải hoàn tất với mã thoát 0.
2. **Negative:** job bị cấp phát vượt heap trong child process, kỳ vọng Epsilon dừng không thành công; ghi nhận đây là phép thử được **chủ động thiết kế**, không phải lỗi bất ngờ của hệ thống.

### 4.3 Test hành vi của JVM/GC integration

JEP 318 còn phục vụ phát triển và kiểm thử các thành phần JVM/GC interface: allocator, khởi tạo heap, ranh giới allocation, logging/monitoring và một số đường lỗi. Đây là công việc cho engineer JVM/tooling, không phải chức năng cần đưa vào code nghiệp vụ bình thường.

### 4.4 Job rất ngắn và footprint đã chứng minh

Có thể tồn tại batch/command-line job chỉ chạy vài mili giây/giây, allocation ít, **toàn bộ quá trình** đã được đo là nằm trong heap budget, không cần thu hồi trước khi process exit. Khi JVM kết thúc, hệ điều hành lấy lại vùng nhớ của tiến trình. Trong trường hợp cực kỳ đặc thù đó Epsilon **có thể** đáng thử, nhưng phải đánh giá rủi ro OOME/latency/host capacity và có phương án fallback. **Không** khuyên bật Epsilon theo mặc định cho server, request processor, worker nhận job liên tục hoặc ứng dụng chạy không giới hạn thời gian.

## 5. Những hiểu lầm quan trọng

| Hiểu lầm | Sự thật |
|---|---|
| “No-op” nghĩa không cần heap | Epsilon vẫn quản lý allocation trên heap |
| Object mất reference sẽ được dùng lại | **Không có reclamation** |
| `System.gc()` có thể cứu Epsilon | Không làm Epsilon thu gom rác |
| Epsilon là công cụ kiểm tra memory leak chuẩn | Nó ghi nhận **tổng cấp phát**, không phân biệt rác với live objects |
| Chỉ có một object sống thì không OOME | Có thể OOME do từng object đã cấp phát trước đó |
| Không có GC pause nghĩa không có pause nào | JIT, safepoints, OS scheduling, I/O vẫn có |
| Epsilon luôn nhanh hơn G1 | Phải benchmark cùng workload, Epsilon cũng có chi phí allocator/commit |
| Có thể catch OOME rồi chạy tiếp bình thường | Không an toàn; JVM có thể **chủ động kết thúc** |
| `-Xmx` là giới hạn tổng RAM process | `-Xmx` chủ yếu giới hạn Java heap, không phải toàn bộ RSS/native memory |
| Flags luôn giống nhau trên mọi JVM | HotSpot/OpenJ9/vendor khác nhau |
| Heap chưa đầy nghĩa không có memory pressure | Native memory, thread stack, direct buffers và các giới hạn khác vẫn tồn tại |
| Bật Epsilon 24/7 là cách tắt overhead GC | Với allocation không giới hạn, heap chắc chắn cạn |
| Không có GC thì reference/cleanup hoạt động hệt GC khác | Nhiều xử lý phụ thuộc reclamation/reference processing không xảy ra theo lịch thông thường |

## 6. Demo 1 — Bỏ tham chiếu nhưng heap không được thu hồi

Chương trình này sử dụng Epsilon với heap 32 MiB. Nó tạo 160 mảng, mỗi mảng 64 KiB, tương đương **10 MiB allocations**. Biến static volatile `latest` chỉ giữ mảng mới nhất để JIT không loại bỏ toàn bộ việc cấp phát như dead code. Những mảng cũ không còn được chương trình giữ, nhưng Epsilon không thu hồi chúng. Sau đó gọi `System.gc()` và xem heap used không giảm.

Bài test **không giữ một list 160 mảng**; vì vậy việc heap tăng không do một collection trong app giữ lại. Nó minh họa trực tiếp sự khác nhau giữa *không reachable* và *được thu hồi*.

Lưu thành **`EpsilonNoReclaimDemo.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;

public class EpsilonNoReclaimDemo {
    static volatile byte[] latest;

    static long usedHeap() {
        return ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getUsed();
    }

    static boolean epsilonSelected() {
        List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();
        return collectors.stream().anyMatch(
                bean -> bean.getName().toLowerCase(
                        java.util.Locale.ROOT).contains("epsilon"));
    }

    public static void main(String[] args) {
        boolean epsilon = epsilonSelected();
        long before = usedHeap();
        for (int i = 0; i < 160; i++) {
            byte[] block = new byte[64 * 1024];
            block[0] = (byte) i;
            latest = block; // only the most recent block remains reachable
        }
        long afterAllocations = usedHeap();
        System.gc(); // cannot make Epsilon reclaim unreachable objects
        long afterExplicitRequest = usedHeap();

        System.out.println("epsilon-selected=" + epsilon);
        System.out.println("used-increased-over-8MiB="
                + (afterAllocations - before >= 8L * 1024 * 1024));
        System.out.println("explicit-request-did-not-reclaim="
                + (afterExplicitRequest >= afterAllocations));
        System.out.println("last-block-length=" + latest.length);

        if (epsilon && (afterAllocations - before < 8L * 1024 * 1024
                || afterExplicitRequest < afterAllocations)) {
            throw new AssertionError("Unexpected Epsilon heap behavior");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 11 -encoding UTF-8 EpsilonNoReclaimDemo.java
java -Xms32m -Xmx32m -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC EpsilonNoReclaimDemo
```

**Stdout đã kiểm chứng trên một bản OpenJDK hỗ trợ Epsilon** (biên dịch Java 11-compatible):

```text
epsilon-selected=true
used-increased-over-8MiB=true
explicit-request-did-not-reclaim=true
last-block-length=65536
```

Giải thích:

1. `epsilon-selected=true`: `GarbageCollectorMXBean` chứa collector tên Epsilon. Kết quả phụ thuộc VM/vendor; demo này dành cho HotSpot có Epsilon.
2. `used-increased-over-8MiB=true`: 160 lần cấp mảng 64 KiB tương đương 10 MiB; measurement thấy used heap tăng hơn 8 MiB, dù app chỉ giữ mảng cuối.
3. `explicit-request-did-not-reclaim=true`: sau `System.gc()`, heap used không giảm; đây là hành vi mong đợi của no-op GC.
4. `last-block-length=65536` xác nhận mảng cuối còn reachable, giúp trình biên dịch không có cớ bỏ toàn bộ kết quả cấp phát.

**Không biến một lần đo thành định luật byte-for-byte:** `MemoryMXBean.getHeapMemoryUsage().getUsed()` là phép đo dùng cho quan sát; khác biệt có thể đến từ JVM overhead, allocator/TLAB, chế độ compiler và JDK/vendor. Kiểm thử đáng tin nên tập trung vào hướng thay đổi và contract, không assert “used tăng đúng 10.485.760 byte”. Cũng đừng suy ra GC bình thường sẽ lập tức giảm `getUsed` ngay khi `System.gc()` được gọi: nhiều collector có chính sách và thời điểm riêng.

## 7. Demo 2 — Dừng trước ngân sách an toàn, không cố chạm OOME

Trong một công cụ benchmark có giới hạn, giải pháp an toàn hơn việc cố làm JVM hết heap là **dừng sớm theo high-water mark**. Demo dùng:

- Heap tối đa 32 MiB, initial 32 MiB.
- Vòng lặp **tối đa 1.000** lần cấp mảng **256 KiB**.
- Ngưỡng mềm là 60% `maxMemory()`.
- Trước mỗi allocation kiểm tra `used + BLOCK_BYTES + 4 MiB reserve >= soft ceiling`; nếu tới ngưỡng thì ngừng.
- Giữ `latest` để xác nhận có object thật được tạo, nhưng không giữ mảng trước đó.
- Không cố catch OOME hay chủ động restart cùng heap đã cạn.

Lưu thành **`EpsilonBudgetGuardDemo.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;

public class EpsilonBudgetGuardDemo {
    static volatile byte[] latest;
    private static final int BLOCK_BYTES = 256 * 1024;
    private static final long RESERVE_BYTES = 4L * 1024 * 1024;

    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        long maxHeap = Runtime.getRuntime().maxMemory();
        int completed = 0;
        boolean budgetStopped = false;

        for (int i = 0; i < 1000; i++) {
            long used = memory.getHeapMemoryUsage().getUsed();
            long softCeiling = (maxHeap * 60L) / 100L;
            if (used + BLOCK_BYTES + RESERVE_BYTES >= softCeiling) {
                budgetStopped = true;
                break;
            }
            byte[] block = new byte[BLOCK_BYTES];
            block[0] = (byte) i;
            latest = block; // intentionally discard the previous block
            completed++;
        }

        boolean epsilon = ManagementFactory.getGarbageCollectorMXBeans()
                .stream().anyMatch(bean -> bean.getName().toLowerCase(
                        java.util.Locale.ROOT).contains("epsilon"));
        long after = memory.getHeapMemoryUsage().getUsed();
        System.out.println("epsilon-selected=" + epsilon);
        System.out.println("budget-stopped=" + budgetStopped);
        System.out.println("processed-positive=" + (completed > 0));
        System.out.println("processed-under-1000=" + (completed < 1000));
        System.out.println("heap-under-max=" + (after < maxHeap));
        System.out.println("still-reachable=" + (latest != null));

        if (!epsilon || !budgetStopped || completed <= 0
                || completed >= 1000 || after >= maxHeap
                || latest == null) {
            throw new AssertionError("Expected bounded Epsilon allocation");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 11 -encoding UTF-8 EpsilonBudgetGuardDemo.java
java -Xms32m -Xmx32m -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC EpsilonBudgetGuardDemo
```

**Stdout đã kiểm chứng:**

```text
epsilon-selected=true
budget-stopped=true
processed-positive=true
processed-under-1000=true
heap-under-max=true
still-reachable=true
```

Ý nghĩa: `budget-stopped=true` cho thấy **một phép kiểm tra budget mềm** dừng job trước 1.000 allocations. `heap-under-max=true` xác nhận tại thời điểm đo nó chưa dùng hết heap. Đây **không phải** một memory guard tuyệt đối đủ dùng cho mọi ứng dụng: JVM có thể cấp phát thêm giữa hai lần đo, nhiều threads cùng allocate, metadata và runtime allocations vẫn tốn chỗ. Với production/CI, hãy có **heap reserve đáng kể, giới hạn số thao tác, watchdog timeout và isolation**, thay vì chỉ tin một điều kiện `MemoryMXBean` rồi nghĩ không thể OOME.

Mức 60% và 4 MiB reserve chỉ là thông số test có chủ đích, không phải công thức chuẩn cho mọi heap và hệ điều hành. Với batch thật, tính **worst-case allocations + safety margin**, đo trên JDK/JVM đúng phiên bản deployment và giữ một phương án fallback.

## 8. Demo 3 — Cùng một workload có thể hoàn tất với G1 nhưng Epsilon dừng vì heap cạn

Đây là phần minh họa rõ nhất về **không thu hồi**. Chương trình chỉ giữ reference đến **một mảng cuối cùng**, nhưng trong vòng đời nó tạo tối đa 1.024 mảng kích thước 256 KiB — tổng lượng yêu cầu cấp phát lý thuyết khoảng **256 MiB**, vượt `-Xmx32m` nếu không được reclaim.

- Khi chạy với **G1** và 32 MiB heap, các mảng cũ không còn reachable và collector có thể thu hồi chúng để hoàn tất 1.024 vòng. Kết quả test thực tế: chương trình in `probe-completed=true`, exit code 0.
- Khi chạy với **Epsilon** và 32 MiB heap, allocation tích lũy làm cạn heap, JVM kết thúc với `OutOfMemoryError: Java heap space`. Kết quả test thực tế: tiến trình Epsilon kết thúc với **exit code khác 0**.
- Số lần cấp phát thực hiện được trước khi lỗi, dòng cảnh báo, exit code cụ thể và thời điểm OOME **có thể khác nhau** theo JVM/version/startup/flags. Không assert đúng iteration N hoặc đúng mã thoát 3.

Lưu thành **`EpsilonExhaustionProbe.java`**:

```java
public class EpsilonExhaustionProbe {
    static volatile byte[] latest;

    public static void main(String[] args) {
        System.out.println("probe-started=true");
        for (int i = 0; i < 1024; i++) {
            byte[] block = new byte[256 * 1024];
            block[0] = (byte) i;
            latest = block;
        }
        System.out.println("probe-completed=true");
    }
}
```

Biên dịch:

```bash
javac --release 11 -encoding UTF-8 EpsilonExhaustionProbe.java
```

**Chỉ chạy trong child process/CI runner được cô lập**, không chạy trong JVM của service. Lệnh dưới đây chạy hai phép thử riêng với heap 32 MiB:

```powershell
# PowerShell: mỗi lệnh java mở một JVM riêng, không tái sử dụng heap.
java -Xms32m -Xmx32m -XX:+UseG1GC EpsilonExhaustionProbe
$g1Exit = $LASTEXITCODE

java -Xms32m -Xmx32m -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC EpsilonExhaustionProbe
$epsilonExit = $LASTEXITCODE

Write-Output ("g1-exit-zero=" + ($g1Exit -eq 0))
Write-Output ("epsilon-exit-nonzero=" + ($epsilonExit -ne 0))
```

**Output cốt lõi đã kiểm chứng:**

```text
probe-started=true
probe-completed=true
probe-started=true
Terminating due to java.lang.OutOfMemoryError: Java heap space
g1-exit-zero=True
epsilon-exit-nonzero=True
```

Các dòng `Terminating due to...` là **stderr/console từ HotSpot** trong môi trường kiểm thử, không được code Java in ra; wording có thể thay đổi. Hai dòng boolean cuối phản ánh exit code độc lập của hai JVM. Trên Bash/Linux, dùng `$?` ngay sau từng lệnh `java` để lấy exit status tương ứng; PowerShell dùng `$LASTEXITCODE`.

### 8.1 Vì sao không thử/catch OOME trong cùng tiến trình?

HotSpot Epsilon có thể đặt `ExitOnOutOfMemoryError` theo mặc định hoặc có hành vi kết thúc JVM khi cạn heap. Vì vậy một đoạn:

```java
try {
    // Allocation không giới hạn...
} catch (OutOfMemoryError error) {
    // Không được dựa vào đây để phục hồi và tiếp tục service.
}
```

chỉ là **trích đoạn cảnh báo**, không phải cách giải quyết. Kể cả JVM có ném exception cho Java bắt được, việc tiếp tục một tiến trình gần hết memory cũng có rủi ro (logging, exception handling, thread, cleanup còn cần cấp phát). Đặt phép thử cạn heap trong **process tách biệt**, giới hạn `-Xmx`/thời gian/OS resources, coi **exit code** là kết quả. Không dùng `-XX:+CrashOnOutOfMemoryError` cho demo đơn giản và tránh tạo heap dump cỡ lớn nếu không thật sự cần.

### 8.2 Kiểm soát rủi ro của phép thử negative

1. Không chạy trên production host hoặc cùng JVM chứa dữ liệu đang xử lý.
2. Dùng heap nhỏ có giới hạn; tránh cấp phát native/direct buffers hoặc tạo hàng nghìn threads.
3. Số lần cấp phát **có trần** (1.024) thay vì vòng lặp vô hạn.
4. Dùng runner có timeout/cancel, resource quota và quyền file tối thiểu.
5. Không tái sử dụng kết quả log OOME như bằng chứng bug memory leak.
6. Không dựa vào thông điệp lỗi chính xác cho automation; kiểm tra status và dấu hiệu JVM Epsilon thích hợp.
7. Không làm phép thử cạn heap chạy song song quá nhiều child processes, vì cộng dồn vẫn có thể gây áp lực RAM toàn máy.

## 9. Demo 4 — Cùng code đo workload dưới Epsilon và G1

Khi mục tiêu là so sánh chi phí GC, cần bảo đảm hai collector thực hiện **cùng một công việc**. Demo tạo 400 mảng để warm up đường code, sau đó đo 1.000 allocations mảng 4 KiB. Mảng được gán cho biến `volatile latest` để việc tạo đối tượng có tác dụng quan sát được; cộng checksum làm sanity check. Nó đọc số lần GC hoàn tất qua `GarbageCollectorMXBean.getCollectionCount()` và thời gian bằng `System.nanoTime()`.

**Đây là harness minh họa cách kiểm chứng workload**, **không phải benchmark production đáng tin**: 400 allocations không phải warm-up chuẩn JMH, một vòng timing có thể bị ảnh hưởng của JIT, scheduler, power management, CPU cache và JVM startup. Đừng công bố tỉ lệ performance từ một phép chạy.

Lưu thành **`EpsilonCompareWorkloadDemo.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.Locale;

public class EpsilonCompareWorkloadDemo {
    static volatile byte[] latest;

    static long allocate(int iterations) {
        long checksum = 0L;
        for (int i = 0; i < iterations; i++) {
            byte[] block = new byte[4096];
            block[0] = (byte) (i & 127);
            latest = block;
            checksum += block[0];
        }
        return checksum;
    }

    static long completedCollections() {
        long total = 0L;
        for (GarbageCollectorMXBean bean
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            if (bean.getCollectionCount() >= 0) {
                total += bean.getCollectionCount();
            }
        }
        return total;
    }

    public static void main(String[] args) {
        boolean epsilon = ManagementFactory.getGarbageCollectorMXBeans()
                .stream().anyMatch(bean -> bean.getName()
                        .toLowerCase(Locale.ROOT).contains("epsilon"));

        allocate(400); // warm up this invocation path, not a calibrated JMH warmup
        long beforeGcCount = completedCollections();
        long start = System.nanoTime();
        long checksum = allocate(1000);
        long elapsedNanos = System.nanoTime() - start;
        long afterGcCount = completedCollections();

        System.out.println("epsilon-selected=" + epsilon);
        System.out.println("iterations=1000");
        System.out.println("checksum=" + checksum);
        System.out.println("elapsed-positive=" + (elapsedNanos > 0));
        System.out.println("gc-count-did-not-increase="
                + (afterGcCount == beforeGcCount));
        System.out.println("last-block-bytes=" + latest.length);

        if (checksum != 62252L || elapsedNanos <= 0
                || latest.length != 4096) {
            throw new AssertionError("Invalid workload result");
        }
        if (epsilon && afterGcCount != beforeGcCount) {
            throw new AssertionError("Epsilon unexpectedly collected");
        }
    }
}
```

Biên dịch:

```bash
javac --release 11 -encoding UTF-8 EpsilonCompareWorkloadDemo.java
```

Chạy hai JVM riêng:

```bash
java -Xms32m -Xmx32m -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC EpsilonCompareWorkloadDemo
java -Xms32m -Xmx32m -XX:+UseG1GC EpsilonCompareWorkloadDemo
```

**Stdout đã kiểm chứng, thứ tự Epsilon trước rồi G1:**

```text
epsilon-selected=true
iterations=1000
checksum=62252
elapsed-positive=true
gc-count-did-not-increase=true
last-block-bytes=4096
epsilon-selected=false
iterations=1000
checksum=62252
elapsed-positive=true
gc-count-did-not-increase=true
last-block-bytes=4096
```

Kết quả này minh họa một bẫy trong đọc số liệu: **G1 cũng có thể có `gc-count-did-not-increase=true`** với một workload nhỏ không gây áp lực cần thu gom. Vì vậy “cả hai không ghi nhận GC cycle trong đúng khoảng đo” **không** cho phép kết luận Epsilon tốt hơn về độ trễ. Phải chọn workload/đo lường phù hợp và dùng nhiều fork/trial.

`checksum=62252` bảo đảm phép tính trong demo đúng với 1.000 iterations. Dòng `elapsed-positive=true` chỉ xác nhận thời gian đo dương, **không ghi số nanosecond biến động thành oracle cố định**; số thực cần được thu bởi framework đo chuẩn trên môi trường mục tiêu.

## 10. Phép đo hiệu năng có kiểm soát: cần ghi lại những gì?

Trước khi so sánh, xác định câu hỏi: “latency do GC pause?”, “CPU spent in GC?”, “heap allocation budget?”, “file/serialization chậm?” hay “live heap memory leak?”. Epsilon giúp trả lời một số câu hỏi, nhưng **không đồng nhất** chúng.

### 10.1 Các đại lượng nên tách riêng

| Chỉ số | Ghi nhận bằng gì | Giới hạn |
|---|---|---|
| Heap maximum | `Runtime.getRuntime().maxMemory()` | Không bằng RSS hay RAM máy |
| Heap used tại mốc | `MemoryMXBean.getHeapMemoryUsage().getUsed()` | Một snapshot; có overhead, không chỉ live objects |
| GC collection count | `GarbageCollectorMXBean.getCollectionCount()` | Có thể -1 khi không hỗ trợ, khác theo collector |
| GC collection time | `getCollectionTime()` hoặc GC logs | Không thay thế toàn bộ latency/performance |
| Total allocation rate | JFR `jdk.ObjectAllocation*` phù hợp hoặc profiler | Event availability/sampling/overhead phụ thuộc JDK/config |
| Wall-clock time | `System.nanoTime()`/JMH | Chịu ảnh hưởng warm-up, JIT, scheduling |
| Throughput | Số request/work items trên giây | Phải đảm bảo same input và correctness |
| Tail latency | p95/p99 của nhiều samples | Không suy từ average một lần chạy |
| CPU utilization | OS/process metrics | Không tự chỉ riêng GC cost |
| RSS/native memory | OS/JVM native-memory tooling | Không phản ánh chỉ Java heap |
| Peak allocation budget | Epsilon + bộ dữ liệu/boundary test | Không chứng minh live-set size hay leak |
| Object lifetime | Profiling/reachability analysis | Epsilon không thu hồi nên không tự phân loại |

**Heap maximum** `-Xmx` không giới hạn native direct buffer memory, metaspace, code cache, stack memory, JNI/native allocations và các loại RSS khác. Một chương trình Epsilon có thể gặp vấn đề native memory trước khi Java heap hết. Với môi trường container, phải xét **memory limit container** bên cạnh heap flags.

### 10.2 Thiết kế phép thử lặp lại được

1. Ghi chính xác `java -version`, `javac -version`, vendor, CPU, OS, số cores, memory quota, commit/branch và input dataset.
2. Dùng cùng JVM build, heap bound, hardware và binary cho các phép so sánh; thay **một yếu tố có chủ đích** như GC.
3. Không chạy thêm benchmark khác làm tranh CPU/RAM/IO nếu cần so sánh công bằng.
4. Tách phase JVM startup, class loading, JIT warm-up và measured steady-state.
5. Chạy nhiều fork/repetition, báo median/percentiles/variance, không một lần snapshot.
6. Đảm bảo **kết quả tính toán** giống nhau; checksum trong demo giúp kiểm tra tối thiểu nhưng không thay thế assertion nghiệp vụ.
7. Ngăn dead-code elimination: nếu tạo object chỉ để đo mà không bao giờ dùng, JIT có thể tối ưu allocation đi; sử dụng observable sink/blackhole đúng cách.
8. Theo dõi số events/heap used/GC count và code path cả hai bên; Epsilon không có reclaimed events, G1 có thể không thu gom nếu bài test quá nhỏ.
9. Gắn timeout, giới hạn heap/resource và logic xác nhận result; OOME test dùng subprocess.
10. Giữ báo cáo của run complete tách khỏi run partial/fail; không gộp nhanh/chậm của các quá trình đã bị kill vào benchmark thành công.

### 10.3 Pre-touch và heap commit

Epsilon có thể gợi ý `-Xms` bằng `-Xmx` hoặc `-XX:+AlwaysPreTouch` để tránh gián đoạn do heap resize/commit khi đo, nhưng **không phải tất cả phép thử cần bật các cờ này**. Pre-touch có thể **tăng thời gian startup và RSS commit**; nó thay đổi chính điều được đo. Nếu benchmark tính cả startup, phải giữ flags nhất quán và báo rõ. Đừng chạy pre-touch với `-Xmx` khổng lồ trên máy chia sẻ chỉ để “tối ưu”.

### 10.4 GC logs và JFR

Dùng `-Xlog:gc=info` xác nhận collector và các thông tin GC. Với GC bình thường có thể thấy các chu kỳ thu gom khi workload đủ áp lực; với Epsilon bạn sẽ thấy startup collector nhưng **không có chu kỳ reclamation**. Không dùng việc thiếu GC log làm bằng chứng rằng app không allocate: allocation vẫn diễn ra, như demo 1.

JFR có thể hỗ trợ đọc allocation events và GC events để phân tích, nhưng cần cấu hình event types, threshold/period phù hợp; không khẳng định bộ event JFR hay sampling giống nhau giữa các vendor/JDK. Nếu test cần chính xác lượng bytes cấp phát, dùng profiler/measurement methodology đã xác minh; Epsilon chỉ là một phương tiện hỗ trợ chứ không phải phép đếm hoàn hảo cho mọi object.

## 11. Epsilon và memory leak: hai câu hỏi khác nhau

Memory leak ở Java thường là **giữ reference ngoài ý muốn** khiến live-set không giảm dù GC có khả năng thu hồi. Epsilon lại **không thu hồi object không còn reachable** ngay cả khi ứng dụng viết đúng. Vì vậy, dưới Epsilon:

```text
Memory used increase
  = cumulative allocations
    + allocator/JVM overhead
    - no recovered Java-heap memory
```

Đó chỉ là một mô hình trực quan, **không** là công thức đo bytes tuyệt đối. Nếu dùng Epsilon để thử xem code có tạo nhiều temporary objects hay không, bạn đang đo **allocation behavior**, không phải chứng minh toàn bộ objects là live hoặc retained.

Cách phân biệt trong thực tế:

- **Allocation pressure:** đo bytes/objects được cấp phát theo request hoặc unit of work, hotspot allocation rate, profiling; Epsilon có thể làm tín hiệu heap pressure rõ hơn.
- **Retained memory/leak:** chạy với collector có thu hồi, dùng heap dump/dominator tree/object reference analysis, đo live set sau chu kỳ thích hợp.
- **Native leak:** dùng OS metrics/native memory tracking hoặc công cụ tương ứng; `-Xmx` và Epsilon không tự phát hiện trực tiếp.
- **Resource leak:** file descriptors, sockets, threads, direct buffers không nhất thiết hiện thành Java heap OOME theo cùng một đường; dùng resource tracking và close rõ ràng.

Không được đề xuất chạy Epsilon nhiều ngày để “chờ thấy leak”; ứng dụng đủ cấp phát bình thường cũng sẽ hết heap. Đó là **kết quả không có thông tin phân loại memory leak**.

## 12. Tác động đến reference processing và cleanup

Với GC thu hồi, một số xử lý liên quan `WeakReference`, `SoftReference`, `PhantomReference` hoặc công việc cleanup có thể được kích hoạt khi collector xác định reachability phù hợp. **Epsilon không có chu kỳ thu gom thông thường** nên đừng giả định các tiến trình cleanup phụ thuộc GC sẽ diễn ra đúng lúc hoặc diễn ra trước khi JVM exit.

Hệ quả thực tế:

- Không đặt logic correctness dựa trên `System.gc()` hay sự kiện “object chết” dưới Epsilon.
- Đóng file/socket/stream trực tiếp bằng `AutoCloseable`/`try-with-resources` thay vì chờ GC cleanup.
- Với direct/native memory, phải tuân thủ contract của API quản lý vòng đời và đóng tài nguyên có thể đóng; việc không có GC còn có thể gây áp lực native memory không phản ánh đầy đủ qua Java heap.
- Không dùng finalization làm cơ chế chủ đạo — đây là hướng thiết kế không còn được khuyến nghị trên Java hiện đại.
- Nếu job chỉ tồn tại ngắn, đừng suy rằng toàn bộ cleanup hooks/finalizers/cleaners chắc chắn đã chạy trước khi OS thu hồi address space khi process kết thúc.

**Không cần hiểu mọi chi tiết reference processing để sử dụng Epsilon trong phép thử**, nhưng phải biết sự phụ thuộc vào GC của thư viện có thể làm phép thử không đại diện cho production GC.

## 13. Khi nào KHÔNG dùng Epsilon?

| Workload | Vì sao không phù hợp |
|---|---|
| HTTP server chạy liên tục | Mỗi request thường tạo temporary objects; heap chỉ tăng |
| Queue/consumer chạy không giới hạn | Không có lifetime/allocation budget đảm bảo |
| Batch nhiều giờ với input biến thiên | Có thể vượt dự tính về allocation |
| Workload có native memory lớn không kiểm soát | `-Xmx` không quản lý toàn RSS |
| Service cần tự phục hồi OOME | Epsilon có thể chấm dứt tiến trình |
| Ứng dụng dựa vào reference processing tự dọn resource | Không có GC reclamation theo kỳ vọng |
| Benchmark mà Epsilon bị OOME | Kết quả không so sánh công bằng với GC khác |
| Memory leak diagnosis chỉ dựa vào heap growth | Heap growth dưới Epsilon là hành vi tất yếu |
| Production yêu cầu availability cao | Không có cơ chế reclaim để đối phó allocation lâu dài |
| Hệ thống nhiều JVM cùng host không quota | Nhiều run có thể cộng áp lực RAM và I/O |

**Ngoại lệ có kiểm chứng** là job ngắn với allocation upper bound và observability/rollback đã đủ; ngay cả vậy, hãy coi Epsilon là quyết định workload-specific chứ không là best practice mặc định.

## 14. Ma trận kiểm thử an toàn

| Ca kiểm thử | Điều cần đo/xác nhận |
|---|---|
| JVM nhận Epsilon flags | Startup thành công và chọn đúng collector |
| Sai vendor/JVM không có Epsilon | Fail rõ, không tự bỏ flags và báo chạy đúng |
| Bỏ experimental unlock | JVM có thể từ chối experimental flag |
| G1 baseline | Chạy riêng với `-XX:+UseG1GC` |
| 160 × 64KiB allocations | Epsilon heap used tăng đáng kể |
| Mất references cũ | Không làm Epsilon reclaim |
| `System.gc()` | Không giúp Epsilon lấy lại heap |
| Soft budget guard | Dừng trước 60% + reserve trong fixture |
| Child job 1.024 × 256KiB với G1 | Hoàn tất trên JVM thử nghiệm |
| Cùng job với Epsilon heap32m | Kết thúc không thành công do heap cạn |
| Checksum/logic workload | Hai GC cho kết quả giống nhau khi hoàn tất |
| GC MXBean | Epsilon selected và count không tăng trong test |
| JIT dead-code elimination | Có observable use để giữ allocations |
| Warm-up/steady-state | Phân biệt startup/JIT với workload |
| Input lớn hơn budget | Report failure, không đánh dấu success |
| Run timeout | Kill/cleanup child nếu vượt thời gian |
| Parallel test | Có giới hạn số JVM và tổng memory |
| Môi trường container | Heap + RSS + native memory trong giới hạn |
| Khác vendor/JDK | Kiểm tra flag support/GC logs thực tế |
| Production safety | Không bật Epsilon trên service thường |

**Chú ý:** Các output boolean của demo là kết quả thực tế trên một OpenJDK tương thích, không phải cam kết mọi HotSpot update có đúng cùng chuỗi cảnh báo hoặc số byte được tính. Kiểm tra cả run bình thường và run OOME trong CI với resource quota; không cần tạo heap dump khổng lồ khi chỉ cần exit status.

## 15. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai hoặc nguy hiểm | Cách đúng |
|---|---|---|
| Dùng `-XX:+UseEpsilonGC` mà không unlock experimental | JVM có thể từ chối flag | Mở `UnlockExperimentalVMOptions` trước |
| Kết hợp Epsilon với collector khác trong một process | Lựa chọn collector không hợp lệ | Chạy benchmark ở hai JVM riêng |
| Epsilon chạy với heap quá lớn trên máy chung | Có thể tiêu thụ nhiều RAM trước lỗi | `-Xmx`/container quota phù hợp |
| Giả định Epsilon không có allocator overhead | Sai mô hình | Đo allocations/commit/JIT riêng |
| Coi `System.gc()` là giải pháp reclaim | Epsilon không thu hồi | Dùng GC có reclamation nếu cần |
| Dùng Epsilon đo memory leak bằng used-heap slope | Không phân biệt live/unreachable | Dùng heap profiler/GC bình thường |
| Benchmark mà workload OOME | Kết quả không còn so sánh | Tăng budget hoặc rút workload, ghi rõ |
| Catch OOME và tiếp tục nghiệp vụ | JVM có thể chết hoặc thiếu memory để phục hồi | Negative test trong subprocess |
| Giả định `-Xmx` chặn toàn bộ RSS | Bỏ sót native/thread/code/meta | OS quota và memory metrics |
| Cấp phát object không dùng trong microbenchmark | JIT có thể tối ưu loại bỏ | Observable sink/benchmark harness |
| Chỉ chạy một vòng rồi công bố hơn kém | Noise lớn | Repetition, warm-up, JMH |
| Tin đúng số GC count bằng 0 sẽ chứng minh không allocation | GC count không phải allocation count | Đo allocation/used-heap |
| Không ghi runtime version/vendor | Flag/performance biến đổi | Lưu metadata thử nghiệm |
| Dùng System.nanoTime một lần làm perf oracle | Bị ảnh hưởng JIT/scheduler | Nhiều runs và phân bố kết quả |
| Phụ thuộc cleanup do GC | Không chạy khi no-op | Explicit close/lifecycle |
| Dùng cờ GC dành cho VM vendor khác | Không portable | Xem vendor runtime docs |
| Dùng GC log format của bản cũ làm contract | Logging thay đổi | `-Xlog` + kiểm tra version |
| Không có timeout/quota cho OOME test | Có thể ảnh hưởng máy/test runner | Child process, heap nhỏ, trần iterations |
| Dùng Epsilon như lựa chọn mặc định cho production | Hết heap dù app không leak | Collector có thu hồi và capacity planning |

## 16. Bài tập có đáp án

**Bài 1 — nguyên tắc.** Một chương trình liên tục `new byte[1_000_000]`, rồi bỏ reference ngay. Với Epsilon, nó có thể chạy vô hạn nếu live set chỉ 1 MiB không?  
**Đáp án:** không. Allocation budget tích lũy và Epsilon không reclaim, nên với heap hữu hạn sớm muộn có thể OOME.

**Bài 2 — cờ chạy.** Chọn flags tối thiểu để bật Epsilon HotSpot Java 11.  
**Đáp án:** `-XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC`; thêm `-Xms`/`-Xmx` rõ ràng cho test.

**Bài 3 — bỏ reference.** `list.clear()` hoặc `obj=null` có khiến Epsilon trả vùng nhớ đó cho JVM allocator không?  
**Đáp án:** không. Chúng có thể bỏ references; Epsilon không thực hiện heap reclamation.

**Bài 4 — System.gc.** Gọi `System.gc()` dưới Epsilon có bảo đảm giảm used heap không?  
**Đáp án:** không; Epsilon là no-op collector.

**Bài 5 — phân biệt leak.** Sau 10.000 requests, used heap của Epsilon tăng. Đây có phải bằng chứng chắc chắn service leak?  
**Đáp án:** không. Tăng do tổng allocations ngay cả khi objects đã unreachable; cần phân tích retained live set bằng GC/profiler khác.

**Bài 6 — baseline.** Một workload hoàn tất G1 nhưng cạn heap với Epsilon. Có được kết luận G1 nhanh hơn không?  
**Đáp án:** không. Run Epsilon thất bại không có dữ liệu hoàn tất để so tốc độ; cần điều chỉnh budget hoặc workload hợp lệ.

**Bài 7 — OOME.** Vì sao test intentionally exhausting heap phải chạy child JVM?  
**Đáp án:** Epsilon có thể terminate process; cần cô lập khỏi runner và nghiệp vụ, kiểm soát exit status, timeout, quota.

**Bài 8 — RSS.** `-Xmx32m` có nghĩa toàn JVM chỉ dùng 32 MiB RAM không?  
**Đáp án:** không. Metaspace, stacks, native buffers và runtime overhead nằm ngoài Java heap.

**Bài 9 — so sánh.** Chạy Epsilon và G1 ở hai JDK/vendor khác nhau rồi so latency có công bằng không?  
**Đáp án:** không đủ. Cần cố định JVM version/build, hardware, workload, heap, startup và các biến khác.

**Bài 10 — code không dùng kết quả.** Vì sao `new byte[4096]` trong một tight loop có thể không tốt cho benchmark?  
**Đáp án:** JIT có thể tối ưu object không có observable use; cần blackhole/sink đúng cách và JMH.

**Bài 11 — thời gian.** `gc-count-did-not-increase=true` trên G1 trong 1.000 iterations có nghĩa G1 đã tắt reclaim?  
**Đáp án:** không. Workload có thể chưa đủ áp lực để G1 chạy một GC cycle trong khoảng đo.

**Bài 12 — job ngắn.** Khi nào Epsilon có thể được cân nhắc cho job nhỏ?  
**Đáp án:** khi đã đo được worst-case allocation footprint, job kết thúc nhanh, có heap/reserve/quota/isolation và phương án quay lại GC thường.

**Bài 13 — flags.** Dùng `-XX:+UseNoGC` từ hướng dẫn OpenJ9 cho HotSpot mà không kiểm tra có ổn không?  
**Đáp án:** không. Phải phân biệt vendor, xác nhận flags được hỗ trợ; với HotSpot dùng `UseEpsilonGC`.

**Bài 14 — kiểm thử.** Vì sao phải ghi `java -version` và GC log trong báo cáo?  
**Đáp án:** vì flags, hành vi và hiệu năng phụ thuộc runtime/vendor; dữ liệu không đủ metadata khó tái lập.

**Bài 15 — cleanup.** Có thể dựa vào finalizer/GC-triggered cleanup dưới Epsilon để đóng file không?  
**Đáp án:** không. Dùng `AutoCloseable`/try-with-resources và quản lý vòng đời trực tiếp.

**Bài 16 — kiểm soát budget.** Vì sao dùng một guard `used < maxHeap` không đủ đảm bảo app không OOME?  
**Đáp án:** check không atomic với allocations của JVM/threads, có overhead và buffer; phải có reserve, quota, hạn mức công việc, watchdog và isolation.

## 17. Nguồn chính thức và tài liệu còn áp dụng

- [OpenJDK JEP 318 — Epsilon: A No-Op Garbage Collector](https://openjdk.org/jeps/318): mục tiêu, thiết kế allocator không thu hồi, use cases và rủi ro khi heap cạn.
- [Oracle JDK 11 Release Notes — JEP 318](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html): xác nhận Epsilon là collector experimental được giới thiệu trong JDK 11.
- [Oracle Java SE 11 — java command and advanced GC options](https://docs.oracle.com/en/java/javase/11/tools/java.html): `-Xms`, `-Xmx`, `-XX` flags và `-Xlog`/unified logging.
- [Java SE 11 — ManagementFactory](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/ManagementFactory.html): xem GC beans và memory beans.
- [Java SE 11 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): collection counts và GC time.
- [Java SE 11 — MemoryMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryMXBean.html): Java heap usage snapshot và cách diễn giải.
- [Java SE 11 — Runtime](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Runtime.html): `maxMemory`, total/free memory và xử lý heap.
- [OpenJDK JDK 11 HotSpot source — Epsilon experimental flag](https://github.com/openjdk/jdk11u/blob/master/src/hotspot/share/gc/shared/gc_globals.hpp): `UseEpsilonGC` là HotSpot experimental option.
- [Eclipse OpenJ9 — nogc policy](https://eclipse.dev/openj9/docs/xgcpolicy/): đối chiếu sự khác biệt VM/flag, không nhầm với Epsilon HotSpot.
- [OpenJDK JMH](https://github.com/openjdk/jmh): công cụ benchmark Java đáng dùng khi cần phép đo có warm-up, forks và thống kê.

**Kết luận:** Epsilon GC **cấp phát nhưng không thu hồi**. Trong Java 11, bật bằng hai HotSpot experimental flags, chỉ dùng có chủ đích cho benchmark, allocation budget/memory-pressure tests và một số job cực ngắn đã được kiểm chứng. Nó **không phải phương án phát hiện memory leak trực tiếp, không thể cứu bằng `System.gc()` và không phù hợp service dài hạn**. Để thử nghiệm an toàn, đặt heap nhỏ có giới hạn, sinh workload hữu hạn, đo bộ nhớ/GC/correctness, so sánh các JVM riêng biệt và chạy ca OOME chỉ trong child process có timeout/quota.