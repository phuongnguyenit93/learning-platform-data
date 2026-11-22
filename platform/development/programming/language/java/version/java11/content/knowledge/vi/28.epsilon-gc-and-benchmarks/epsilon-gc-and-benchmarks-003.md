# Chương trình ngắn hoặc lượng cấp phát có thể dự đoán (Epsilon và phép đo — Java 11)

**Epsilon GC** là bộ thu gom rác kiểu **no-op** có từ **Java 11** theo **JEP 318**. Khác G1 hay Serial GC, Epsilon **cấp phát Java heap nhưng không thực hiện collection để thu hồi những vùng dành cho các object đã chết**. Dù một object không còn reachable, heap đã dùng để cấp phát nó không được Epsilon tái sử dụng do GC. Khi không còn không gian heap đủ để cấp phát, JVM gặp `OutOfMemoryError`; một số HotSpot builds sẽ kết thúc process ngay.

Điều này nghe có vẻ bất lợi, nhưng có hai hoàn cảnh đáng cân nhắc:

1. **Chương trình rất ngắn**: chạy một tác vụ với dữ liệu có kích thước giới hạn, hoàn thành rồi **thoát process** trước khi hết heap.
2. **Workload có tổng lượng cấp phát dự đoán/đo được**: dùng Epsilon để **kiểm tra ngân sách lifetime allocation** hoặc tạo phép đối chứng trong profiling khi muốn loại trừ hoạt động thu gom rác.

**Mấu chốt:** với Epsilon, phải quan tâm **tổng heap bytes đã cấp phát từ lúc JVM bắt đầu**, chứ không chỉ lượng đối tượng đang còn sống (*live heap*) ở thời điểm hiện tại.

Ví dụ, một chương trình tạo tổng 100 MiB temporary arrays rồi không giữ tham chiếu có thể chạy trên G1 với `-Xmx32m` nhờ GC reclaim bộ nhớ, nhưng **không** thể mặc nhiên chạy trên Epsilon với cùng heap. Epsilon không tái sử dụng các vùng nhớ đã cấp phát, dù live set lúc kết thúc chỉ có vài KiB.

**Trạng thái hiện nay:** Epsilon là tính năng **experimental** của HotSpot/OpenJDK, không phải bộ GC mặc định được khuyến nghị cho ứng dụng dài hạn. Ví dụ trong bài đã biên dịch với `javac --release 11` và chạy trên JDK hiện đại với flags Epsilon vẫn được hỗ trợ. Không dùng cơ chế Java hoặc VM options đã legacy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích Epsilon no-op collector, cơ chế allocation và lý do không có memory reclamation.
2. Phân biệt **total/lifetime allocations**, **live set**, **heap used**, **heap committed** và process RSS.
3. Nhận diện workload thực sự phù hợp với Epsilon: CLI/batch/job ngắn có giới hạn input và thời gian sống.
4. Lý giải vì sao “sống ngắn” không bảo đảm “cấp phát ít”.
5. Bật Epsilon bằng `-XX:+UnlockExperimentalVMOptions` và `-XX:+UseEpsilonGC`.
6. Dùng `-Xms`, `-Xmx` và `-Xlog:gc` để kiểm soát và xác minh cấu hình chạy.
7. Ước lượng allocation budget gồm payload, object overhead, startup/framework allocations, TLAB slack và safety margin.
8. Biên dịch và chạy Java 11 demo hoàn tất với Epsilon, so sánh với G1.
9. Viết budget guard bằng `long` và `Math.multiplyExact`, hiểu vì sao chỉ là **ước lượng**.
10. Kiểm thử OOME có chủ đích trong subprocess cô lập mà không gây hỏng workload thật.
11. Phân biệt Epsilon dùng cho **phép đo/đối chứng GC** với công cụ profiler tìm allocation site/retained objects.
12. Biết các giới hạn: startup, page touching, concurrency, Cleaner, resource cleanup, container memory và JVM/vendor.

## 2. Cơ chế của Epsilon

```text
Java program
    |
    v
new byte[] / new Object / framework allocations
    |
    v
Epsilon cấp phát từ Java heap
    |
    +--> Object vẫn reachable -> chiếm vùng heap đã cấp phát
    |
    +--> Object không còn reachable -> vẫn KHÔNG reclaim
    |
    v
Các lần cấp phát tiếp theo tiêu tốn phần heap chưa dùng
    |
    +--> Còn chỗ -> chạy tiếp
    |
    +--> Hết chỗ -> OutOfMemoryError / JVM có thể kết thúc
```

Epsilon không có các chu kỳ đánh dấu/copy/compact như collector thực hiện thu gom. Nó **không phải một collector “pause cực thấp nhưng vẫn thu hồi”**; nó bỏ hẳn phần thu gom.

| Câu hỏi | Epsilon GC | Collector thu hồi rác như G1 |
| --- | --- | --- |
| Có cấp phát objects? | Có | Có |
| Có reclaim unreachable objects? | **Không** | **Có** |
| GC pause do collection? | Không thực hiện collection thông thường | Có thể xảy ra |
| Temporary object hết tham chiếu | Heap đã dùng vẫn không được tái sử dụng | Có thể được GC thu hồi |
| Tổng allocations vượt heap limit | Dễ OOME | Có thể tiếp tục chạy nếu nhiều objects chết kịp |
| Tính ngân sách bộ nhớ | **Lifetime allocation** cộng overhead/margin | Peak live set, allocation rate và collector policy |
| Phù hợp nhất | Short/bounded jobs, profiling/test | Phần lớn services, ứng dụng chạy lâu |
| Trạng thái | Experimental | G1 là collector thông dụng được hỗ trợ |

Đừng diễn giải “no GC pauses” thành “không có độ trễ”. JVM vẫn có startup, JIT, class loading, thread scheduling, page faults, TLAB effects, safepoints vì lý do khác và I/O. Việc bỏ collection có thể giúp một phép đo loại trừ **GC work**, nhưng không chứng minh Epsilon là lựa chọn tốt nhất cho mọi workload.

## 3. Vì sao chương trình ngắn có thể phù hợp?

Một **short-lived job** có lifecycle rõ:

```text
Process start -> tạo dữ liệu có giới hạn -> xử lý -> lưu kết quả -> exit
```

Ví dụ:
- CLI chuyển đổi một file nhỏ với giới hạn size.
- Tiện ích tạo báo cáo trên tối đa vài nghìn bản ghi.
- Job/command chạy một batch hữu hạn rồi kết thúc.
- Test fixture hoặc utility chạy một lần rồi thoát.
- Một tác vụ xử lý tách thành process riêng với giới hạn heap rõ và có watchdog.

Nếu **tổng allocation từ startup tới exit** nhỏ hơn heap budget với dự phòng, việc không thu gom trong thời gian rất ngắn có thể chấp nhận được. **Bộ nhớ process được hệ điều hành thu hồi khi process kết thúc**; không phải Epsilon tự chạy GC ở cuối.

### “Ngắn” không đồng nghĩa “ít cấp phát”

Một chương trình chạy chỉ 2 giây nhưng tạo hàng gigabyte temporary buffers vẫn có thể làm heap Epsilon 64 MiB đầy ngay. Ngược lại, một CLI chạy 10 giây nhưng tạo tổng 12 MiB Java objects có thể nằm trong heap 64 MiB, nếu startup/runtime overhead đủ nhỏ.

**Yếu tố quyết định không chỉ là thời gian tính bằng giây, mà là tốc độ cấp phát nhân vòng đời process cùng toàn bộ overhead**.

### Workload bounded cần giới hạn gì?

- Kích thước input/file/request tối đa.
- Số records/items tối đa.
- Size tối đa mỗi object/buffer.
- Thread/concurrency tối đa.
- Số batch mà **một JVM** được xử lý.
- Các nhánh lỗi/retry có thể phát sinh thêm allocations.
- Framework initialization, dependency graph và cache làm việc phía sau.
- JVM flags, JDK vendor/version, architecture và container memory limit.

Nếu program nhận input bất kỳ rồi không giới hạn allocations, **không** nên chọn Epsilon chỉ vì dữ liệu thường ngày “hay nhỏ”.

## 4. Phân biệt total allocation, live heap và RSS

| Chỉ số | Ý nghĩa | Với Epsilon |
| --- | --- | --- |
| **Logical payload bytes** | Tổng `array.length` hoặc bytes theo logic ứng dụng | Chỉ là một phần của heap footprint |
| **Actual Java allocations** | Java heap bytes dùng để tạo arrays/objects, có headers/alignment | Không được reclaim khi objects chết |
| **Live heap / live set** | Những objects còn reachable từ GC roots | Có thể rất nhỏ dù heap Epsilon sắp đầy |
| **Heap used** | Bộ nhớ heap JVM đang sử dụng theo counter | Thường tăng cùng cumulative allocation, có sai số/cập nhật theo bước |
| **Heap committed** | Dung lượng heap đã commit với OS | Không đồng nghĩa live heap |
| **`-Xmx`** | Maximum Java heap | Không phải memory limit toàn process |
| **RSS** | Physical memory của process/container | Còn gồm native memory, stacks, metaspace, code cache, direct buffers |

Không lấy `Runtime.totalMemory() - Runtime.freeMemory()` rồi xem đó là số **object sống**. Dưới Epsilon, used heap còn chứa vùng của những objects đã unreachable nhưng chưa thể reclaim. `System.gc()` **không làm Epsilon bắt đầu thu hồi chúng**.

### Bài toán ngân sách

```text
Total lifetime heap allocation
  ~= startup Java allocations
    + sum(application allocations in all stages)
    + framework/library Java allocations
    + allocations on all worker threads
    + object headers and alignment
    + allocator/TLAB slack and measurement overhead

Required usable heap
  > worst-case observed/predicted total lifetime consumption
    + safety reserve
```

Đây là **mô hình tư duy**, không phải công thức JVM đảm bảo từng byte. Array có `length=8192` bytes thường tiêu thụ **hơn 8192 bytes** trong heap vì còn header và alignment. Các giá trị cụ thể tùy compressed references, JVM, object alignment, TLAB behavior và JIT.

### Vì sao heap không “reset” sau mỗi batch?

Giả sử một process Epsilon xử lý 10 batch, mỗi batch tạo 8 MiB objects tạm và xóa hết reference trước batch kế. Theo logic ứng dụng, live set có thể nhỏ, nhưng lifetime allocations vẫn khoảng **80 MiB cộng overhead**. **Dọn List, đặt biến thành null hoặc kết thúc method không làm Epsilon reclaim heap**.

Nếu muốn mỗi batch bắt đầu một vùng heap mới theo cơ chế process lifetime, cần thiết kế **mỗi batch trong process mới** (cân nhắc startup/IPC overhead), hoặc dùng một GC có thu hồi bình thường cho process xử lý nhiều batches. Không tự mặc định restart process là giải pháp tối ưu: phải đo.

## 5. Bật Epsilon trên HotSpot/OpenJDK

Epsilon vẫn là **experimental**. Lệnh chọn collector:

```sh
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -Xmx64m -cp . Main
```

`Main` ở đây là **tên class minh họa đã compile**, không có file nguồn `Main.java` trong bài. `UnlockExperimentalVMOptions` phải có trước `UseEpsilonGC`.

Có thể kiểm tra chính xác JVM dùng collector nào bằng log:

```sh
java -Xms64m -Xmx64m -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -Xlog:gc -cp . Main
```

Một dòng log có thể là:

```text
[0.007s][info][gc] Using Epsilon
```

Timestamp chỉ **minh họa**; log trên JVM khác có thể thêm warnings hoặc thông tin heap occupancy. Khi chạy G1 để đối chứng:

```sh
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc -cp . Main
```

Log sẽ cho biết collector là G1 nếu runtime chấp nhận flag. Không dùng Epsilon/G1 đồng thời làm collector trong cùng một JVM.

### Các flags cần hiểu

| Flag | Vai trò | Lưu ý |
| --- | --- | --- |
| `-XX:+UnlockExperimentalVMOptions` | Mở quyền các VM options thử nghiệm | Cần cho Epsilon |
| `-XX:+UseEpsilonGC` | Chọn no-op GC | Không phải default |
| `-Xmx64m` | Maximum Java heap khoảng **64 MiB** | Không giới hạn RSS |
| `-Xms64m` | Initial heap khoảng 64 MiB | Khi bằng `-Xmx` có thể tránh heap resize |
| `-Xlog:gc` | Ghi collector name và các GC-related logs | Không phải allocation profiler |
| `-XX:+AlwaysPreTouch` | Touch heap pages ngay startup | Có thể tránh page faults về sau nhưng **tăng startup time** |

Với một chương trình **rất ngắn**, `AlwaysPreTouch` có thể tốn nhiều thời gian hơn lợi ích nó mang lại. Epsilon trong một số HotSpot builds có thể gợi ý thử option đó, nhưng **không áp dụng máy móc**. Phải đánh giá total startup-to-exit time, memory footprint và container constraint.

**Phân biệt runtime:** GraalVM **Native Image** cũng có no-op Epsilon GC với cách chọn khác, thường tại build time qua `--gc=epsilon`. Trong bài này chúng ta nói **HotSpot Java VM chạy bytecode**, không phải Native Image.

## 6. Ví dụ 1 — short job chạy thành công với Epsilon

Chương trình dưới đây tạo **1.500 arrays, mỗi array 8 KiB**, xử lý một byte và không cố tình giữ các arrays sau vòng lặp. `volatile` field tạo observable reference assignment để giảm khả năng JIT xóa việc cấp phát hoàn toàn trong ví dụ.

Tạo file **`EpsilonShortJob.java`**:

```java
public final class EpsilonShortJob {
    private static final int ITEMS = 1_500;
    private static final int BLOCK = 8 * 1024;
    private static volatile byte[] last;

    public static void main(String[] args) {
        long payload = 0L;
        long check = 0L;
        for (int i = 0; i < ITEMS; i++) {
            byte[] bytes = new byte[BLOCK];
            bytes[0] = (byte) i;
            last = bytes; // Observable escape discourages allocation elimination.
            payload += bytes.length;
            check += bytes[0] & 255;
        }
        last = null;

        System.out.println("Items processed: " + ITEMS);
        System.out.println("Array payload bytes: " + payload);
        System.out.println("Checksum: " + check);
        System.out.println("Kept array references: 0");
        System.out.println("Completed: true");
    }
}
```

Biên dịch và chạy:

```sh
javac --release 11 -encoding UTF-8 EpsilonShortJob.java
java -Xms64m -Xmx64m -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -Xlog:gc -cp . EpsilonShortJob
```

**Stdout của chương trình (không tính log JVM):**

```text
Items processed: 1500
Array payload bytes: 12288000
Checksum: 187290
Kept array references: 0
Completed: true
```

Đây là output **đã được kiểm chứng** bằng `javac --release 11` và một JDK 24 HotSpot-compatible có Epsilon. Các dòng log như `Using Epsilon` và `Heap: ... used` có thể khác về timestamp, mức heap và wording.

### Ý nghĩa kết quả

- `ITEMS × BLOCK = 1500 × 8192 = 12.288.000` byte **payload logic**, chưa có object headers.
- `Checksum: 187290` là phép tính deterministic từ các bytes đã ghi.
- `last = null` bỏ reference từ field; “Kept array references: 0” **không có nghĩa các allocations đã được Epsilon reclaim**.
- Chương trình hoàn thành vì **tổng lifetime allocation vừa trong heap 64 MiB** trên môi trường thử nghiệm.
- JVM vẫn có startup/runtime heap overhead ngoài 12.288.000 byte arrays.

Chạy đối chứng bằng G1:

```sh
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc -cp . EpsilonShortJob
```

**Năm dòng do Java code in ra là giống nhau** trên JVM đã thử. G1 có thể reclaim unreachable objects khi cần; Epsilon không reclaim. Không suy diễn về tốc độ chỉ từ việc hai chương trình đều hoàn tất.

## 7. Ví dụ 2 — guard ngân sách trước khi chạy bounded batch

Một batch hữu hạn cho phép tính trước **phần payload**. Bài này dùng giả định **64 bytes overhead trên mỗi array** và **16 MiB reserve**. Đây chỉ là **ước lượng minh họa**, không phải upper bound phổ quát của HotSpot/Java. Trong production phải đo worst-case và đưa tất cả framework allocations vào ngân sách.

Tạo file **`EpsilonBudgetJob.java`**:

```java
public final class EpsilonBudgetJob {
    private static volatile byte[] last;

    public static void main(String[] args) {
        final long count = 1_200L;
        final long blockSize = 4_096L;
        final long assumedOverheadPerArray = 64L;
        final long reserve = 16L * 1024 * 1024;
        long payload = Math.multiplyExact(count, blockSize);
        long estimate = Math.addExact(
                Math.multiplyExact(count, blockSize + assumedOverheadPerArray),
                reserve);
        long maxHeap = Runtime.getRuntime().maxMemory();
        boolean allowed = estimate < maxHeap;

        System.out.println("Planned payload bytes: " + payload);
        System.out.println("Estimated with reserve bytes: " + estimate);
        System.out.println("Estimate below max heap: " + allowed);
        if (!allowed) {
            throw new IllegalStateException("Budget exceeded; lower workload");
        }
        for (int i = 0; i < count; i++) {
            byte[] buffer = new byte[(int) blockSize];
            buffer[0] = (byte) i;
            last = buffer;
        }
        last = null;
        System.out.println("Batch completed: true");
    }
}
```

Chạy:

```sh
javac --release 11 -encoding UTF-8 EpsilonBudgetJob.java
java -Xms64m -Xmx64m -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -cp . EpsilonBudgetJob
```

**Stdout đã kiểm chứng:**

```text
Planned payload bytes: 4915200
Estimated with reserve bytes: 21769216
Estimate below max heap: true
Batch completed: true
```

Phép tính:
- `1200 × 4096 = 4.915.200` bytes payload.
- `1200 × (4096 + 64) = 4.992.000` bytes theo overhead giả định.
- `16 × 1.048.576 = 16.777.216` bytes reserve.
- Tổng estimate là **21.769.216 bytes**, dưới `-Xmx64m` trong môi trường được thử nghiệm.

**Tại sao `Math.multiplyExact`?** Với input lớn, phép nhân `int` dễ overflow gây check sai. `long` và `Math.multiplyExact` giúp phát hiện arithmetic overflow thay vì silently wrap. Với ứng dụng nhận tham số người dùng, vẫn phải validate `count > 0`, `blockSize > 0`, max count và range trước khi cấp phát.

### Guard này không đảm bảo không có OOME

`Runtime.getRuntime().maxMemory()` là thông tin về maximum heap chứ không phải “dung lượng trống hiện tại”. Biến `estimate` không biết toàn bộ:
- Startup allocations đã dùng.
- Objects được thư viện/framework tạo thêm trong vòng lặp.
- Parallel worker threads.
- TLAB slack, object alignment và JIT behavior.
- Error paths, string formatting, logging.
- Class loading hoặc cache initialization ở giữa batch.

Do đó, **guard là chốt chặn sơ bộ**, còn độ an toàn cần được chứng minh bằng **worst-case runtime test và safety margin**. Nếu không thể khống chế tổng lifetime allocations, một collector có reclaim thường là lựa chọn phù hợp hơn Epsilon.

## 8. Ví dụ 3 — cùng source nhưng Epsilon OOME, G1 hoàn tất

Ví dụ này dành riêng cho **lab/process test có chủ đích**. Nó tạo 4.096 arrays `byte[65536]` trong loop. Trong mỗi vòng, field `observer` được gán lại nên những arrays cũ không phải dữ liệu cần giữ mãi. Tuy vậy, tổng payload tạo ra **256 MiB**, lớn hơn heap `-Xmx64m`.

Tạo file **`EpsilonExhaustionDemo.java`**:

```java
public final class EpsilonExhaustionDemo {
    private static volatile byte[] observer;

    public static void main(String[] args) {
        System.out.println("Pressure test started");
        for (int i = 0; i < 4_096; i++) {
            byte[] bytes = new byte[64 * 1024];
            bytes[0] = (byte) i;
            observer = bytes;
        }
        observer = null;
        System.out.println("Pressure test completed");
    }
}
```

### 8.1. G1 hoàn tất trong phép thử

```sh
javac --release 11 -encoding UTF-8 EpsilonExhaustionDemo.java
java -Xms64m -Xmx64m -XX:+UseG1GC -cp . EpsilonExhaustionDemo
```

**Stdout kiểm chứng trong phép thử G1:**

```text
Pressure test started
Pressure test completed
```

G1 có thể thu hồi những arrays cũ khi không còn references, qua đó cấp phát tiếp trong heap 64 MiB dù **cumulative payload** lớn hơn 64 MiB.

### 8.2. Epsilon kết thúc vì hết heap

```sh
java -Xms64m -Xmx64m -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -cp . EpsilonExhaustionDemo
```

**Stdout của chương trình trước khi lỗi trong phép thử:**

```text
Pressure test started
```

Một thông báo JVM quan sát được:

```text
Terminating due to java.lang.OutOfMemoryError: Java heap space
```

Process kết thúc với **exit code khác 0**, **không** in `Pressure test completed`.

**Đừng bắt exact wording/count làm invariant:** thông báo OOME, vị trí kết thúc, JVM exit policy và overhead phụ thuộc version/vendor/options. Một số HotSpot Epsilon builds mặc định chọn **exit khi OOME**; không thiết kế phục hồi bằng cách giả định `catch (OutOfMemoryError)` luôn chạy được.

### Điều bài thử chứng minh

- Hai lần chạy dùng **cùng một mã Java**.
- G1 có cơ chế GC reclaim những mảng tạm nên trong thí nghiệm đã hoàn tất.
- Epsilon không reclaim nên hết heap trước khi xử lý hết 4.096 arrays.
- **Epsilon OOME không phải bằng chứng memory leak** — chương trình không cố tình giữ toàn bộ arrays, nhưng tổng cấp phát vẫn lớn.
- **Người dùng không nên chạy thử này trong service production**. Thử trong subprocess có `-Xmx` giới hạn, giám sát mã thoát và không gắn với dữ liệu quan trọng.

## 9. Cách đo đúng với Epsilon

### Những điều Epsilon giúp kiểm tra

1. **Tổng heap allocation áp lực tới đâu?** Ở mỗi phase dưới Epsilon, heap consumption thường tăng cùng cumulative allocations.
2. **Job có hoàn tất với heap budget hiện tại không?** Exit status/OOME là tín hiệu stress test.
3. **GC work chiếm tỷ lệ đáng kể trong workload hay không?** Dùng so sánh có kiểm soát với G1/collector khác.
4. **Tác vụ ngắn có lợi gì nếu không collection?** Đo tổng startup-to-exit time nhiều lượt, không chỉ đoạn loop.
5. **Chi phí startup/heap reservation có ảnh hưởng không?** So `-Xms`, `-Xmx`, `AlwaysPreTouch` trên một máy cố định.

### Epsilon không tự cung cấp những gì?

- **Allocation call stack** đầy đủ cho mọi object: cần JFR/JMC hoặc profiler phù hợp.
- **Retained size/GC root paths** của những objects sống lâu: cần heap dump/MAT và collector/measurement policy phù hợp.
- **Số bytes chính xác của Java objects** nếu chỉ cộng `array.length`: còn headers, alignment và các allocations khác.
- **Tốc độ chạy chính xác không chịu tác động JIT:** vẫn có warmup/compilation/safepoints.
- **Giới hạn RSS toàn process:** `-Xmx` chỉ là Java heap bound, còn native memory bên ngoài.
- **Chắc chắn không có mọi loại pause:** Epsilon không chạy GC collection, nhưng process vẫn có các điểm dừng vì lý do khác.

### Kế hoạch benchmark ít bias

| Yếu tố | Cách làm |
| --- | --- |
| JDK | Dùng cùng vendor/version và flags phù hợp |
| Input | Cùng dữ liệu, số items, concurrency |
| Heap | Ghi lại `-Xms`/`-Xmx`, container memory limit |
| Startup vs steady state | Đo riêng hoặc ghi rõ end-to-end |
| JIT | Warmup/đo nhiều lần; không dùng một lượt |
| GC logs | Xác nhận `Using Epsilon` hoặc `Using G1` |
| Epsilon budget | Phải đủ để chạy hết khi đo performance |
| OOME test | Tách riêng, kỳ vọng exit non-zero |
| Kết quả | Báo median, variance, RSS/heap và throughput/latency |
| Phân tích | Không suy ra kết quả từ vài dòng `Heap ... used` |

**Không so một lần chạy Epsilon “không GC” với một lần G1 “vừa GC” rồi tuyên bố cải thiện X%.** Để microbenchmark, dùng **JMH** với setup hợp lý, kết hợp JFR/profiler khi cần. Với CLI ngắn, đo startup-to-exit time vì startup có thể là phần lớn tổng thời gian.

## 10. Vòng đời, `Cleaner` và tài nguyên ngoài heap

Với Epsilon, không có collection để kích hoạt một số cơ chế cleanup phụ thuộc GC/reachability. Vì vậy:
- Không dựa vào finalization hoặc `Cleaner` chạy “sớm” để giải phóng file/socket/memory native.
- Không kỳ vọng `System.gc()` làm heap giảm.
- Không coi `WeakReference` hoặc soft caches là một bộ phận tự động “xả RAM” được Epsilon xử lý.
- Không dùng xóa references như giải pháp reset heap trong cùng process.
- Dùng `try-with-resources`, `close()` và quản lý lifecycle tường minh.

Snippet hợp lệ trong một method đã có `java.nio.file.Path path` và xử lý `IOException`:

```java
try (java.io.InputStream in = java.nio.file.Files.newInputStream(path)) {
    // Xử lý dữ liệu có giới hạn, sau block stream được đóng.
}
```

Đây không phải file Java chạy độc lập. Đóng resources đúng không phụ thuộc collector nào. Đến khi process exit, hệ điều hành sẽ thu hồi bộ nhớ của process, nhưng việc đóng/flush I/O và bảo đảm business transaction vẫn là trách nhiệm ứng dụng.

## 11. Sai lầm thường gặp

1. **“Epsilon thu gom rất nhanh.”** Sai: nó **không thu gom**.
2. **“Job ngắn chắc chắn chạy được.”** Sai nếu tổng allocations vượt heap.
3. **“Chỉ cần peak live set nhỏ là đủ.”** Sai: phải tính cumulative lifetime allocation.
4. **“Object không còn reference thì Epsilon reclaim.”** Sai.
5. **“`System.gc()` reset heap Epsilon.”** Sai.
6. **“Clear List giữa hai batches giúp giảm used heap.”** Không có GC reclaim.
7. **“`-Xmx` bằng giới hạn toàn process.”** Sai: native, stacks, metaspace còn riêng.
8. **“`array.length` là heap size của object.”** Chưa có header/alignment.
9. **“Reserve 16 MiB trong demo là chuẩn cho mọi JVM.”** Sai: chỉ minh họa.
10. **“Epsilon là collector được bật tự động trên Java 11.”** Sai: cần experimental flags.
11. **“Epsilon phù hợp với API server 24/7.”** Thường không: lifetime allocation không bounded.
12. **“Epsilon OOME chứng minh memory leak.”** Sai: temporary allocation cũng làm hết heap.
13. **“OOM có thể luôn catch để tiếp tục.”** Không: Epsilon có thể terminate JVM.
14. **“Bật `AlwaysPreTouch` chắc chắn làm job ngắn nhanh hơn.”** Không: startup overhead có thể lớn.
15. **“Một lần benchmark đủ kết luận Epsilon nhanh hơn.”** Sai: cần lặp và kiểm soát.
16. **“Dùng GC để đóng file/socket thay vì close.”** Sai: quản lý resources tường minh.
17. **“Lấy kết quả G1 rồi suy ra memory Epsilon cần bằng nhau.”** Sai: G1 reclaim còn Epsilon không.
18. **“Số batch biết trước luôn đủ để dự trù memory.”** Còn object graph, framework, parallel threads và error paths.
19. **“Có thể chạy vô hạn vì object tạm rất nhỏ.”** Tổng allocated bytes cuối cùng vẫn vượt giới hạn.
20. **“HotSpot `-XX:+UseEpsilonGC` chính là GraalVM Native Image `--gc=epsilon`.”** Hai môi trường khác nhau.

## 12. Bài tập thực hành

### Bài 1 — Chọn workload phù hợp

Với mỗi trường hợp, quyết định có nên thử Epsilon không và nêu điều kiện: CLI xử lý file 20 MB rồi thoát; batch 1.000 rows; service nhận HTTP requests suốt ngày; worker stream vô hạn; job chạy 2 giây nhưng tạo 5 GB arrays.

### Bài 2 — Cấp phát ngắn

Chạy `EpsilonShortJob.java` dưới Epsilon và G1. Vì sao cả hai in `Kept array references: 0` nhưng Epsilon vẫn dùng heap đã cấp phát? Nếu tăng `ITEMS` lên 10 lần, tình huống có thể thay đổi ra sao?

### Bài 3 — Tính budget

Một batch có 2.000 arrays `byte[4096]`. Tính payload. Thêm giả định overhead 64 bytes/array và reserve do bạn chọn; liệt kê ít nhất năm nguồn allocation chưa được tính và cách đo trên runtime thật.

### Bài 4 — Budget guard

Chạy `EpsilonBudgetJob.java` với `-Xmx64m`, thử một budget thấp trong môi trường test. Khi nào chương trình từ chối trước khi chạy? Vì sao guard vẫn không đảm bảo tránh OOM?

### Bài 5 — OOM đối chứng

Chạy `EpsilonExhaustionDemo.java` trong subprocess cô lập bằng G1/Epsilon. Quan sát exit code và console. Không bắt exact OOME wording; ghi JDK vendor, version, heap flags và kết quả.

### Bài 6 — Batch không reset

Giả sử cùng process Epsilon chạy 10 batches, mỗi batch tạo 8 MiB temporary arrays nhưng không giữ references. Tổng payload đã tạo khoảng bao nhiêu? Vì sao không thể dùng live set nhỏ để nói `-Xmx32m` đủ?

### Bài 7 — Kiểm thử startup

Đo chương trình ngắn với và không có `-XX:+AlwaysPreTouch`, `-Xms = -Xmx`; ghi CPU, RSS và total startup-to-exit latency nhiều lần. Khi nào pre-touch có ích và khi nào hại?

### Bài 8 — Epsilon có thay profiler không?

Nếu Epsilon OOME với heap 64 MiB, làm sao tìm phương thức tạo quá nhiều objects? Khi nào dùng JFR allocation flame graph, khi nào dùng heap dump/GC-root analysis?

### Checklist

- [ ] Nắm **JEP 318**, Epsilon no-op GC từ Java 11.
- [ ] Biết Epsilon **experimental**, chỉ bật chủ động.
- [ ] Phân biệt cumulative allocation với live set.
- [ ] Dự trù heap theo **toàn lifetime** của JVM, không theo peak live בלבד.
- [ ] Dùng `-Xmx`, `-Xms`, `-Xlog:gc` và hai experimental flags.
- [ ] Chạy được ba Java 11 demos và hiểu từng stdout/đường OOM.
- [ ] Không xem payload length là actual heap allocation.
- [ ] Giới hạn input, concurrency, số batch; đo worst-case và có margin.
- [ ] Không dùng Epsilon mặc định cho long-running services.
- [ ] Không trông đợi `System.gc()` hoặc `Cleaner` tự dọn tài nguyên.
- [ ] Benchmark với nhiều lượt chạy và đúng phạm vi.

## 13. Tài liệu chính thức và vẫn còn áp dụng

1. [JEP 318 — Epsilon: A No-Op Garbage Collector](https://openjdk.org/jeps/318): mục tiêu, cơ chế và use cases được thiết kế từ Java 11.
2. [Oracle Java 11 Release Notes](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html): xác nhận Epsilon là experimental no-op GC có từ JDK 11.
3. [Oracle Java 11 GC Tuning Guide](https://docs.oracle.com/en/java/javase/11/gctuning/): bối cảnh lựa chọn collector theo throughput, latency và footprint.
4. [Oracle Java 11 java command](https://docs.oracle.com/en/java/javase/11/tools/java.html): `-Xmx`, `-Xms`, `-Xlog` và VM options.
5. [Oracle Java 25 java command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): đối chiếu các JVM memory options trên JDK hiện đại.
6. [OpenJDK — HotSpot Epsilon GC source](https://github.com/openjdk/jdk/tree/master/src/hotspot/share/gc/epsilon): implementation và các tuning options có thể thay đổi theo JDK.
7. [Java SE 11 — Runtime](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Runtime.html): `maxMemory`, `totalMemory`, `freeMemory`; chú ý chúng không đo retained heap.
8. [OpenJDK JMH](https://github.com/openjdk/jmh): benchmark đúng phương pháp khi cần đánh giá chi phí GC/throughput.

**Kết luận:** Epsilon là lựa chọn có chủ đích cho **chương trình ngắn hoặc tổng cấp phát có giới hạn đáng tin cậy**, và một công cụ **đo/đối chứng hoạt động GC**. Vì không có reclamation, các objects dù đã mất tham chiếu vẫn tiêu tốn Java heap đến khi process thoát. Chọn `-Xmx` dựa trên **total lifetime allocations cùng overhead và safety margin**, giới hạn workload, kiểm thử worst-case, và không dùng Epsilon như giải pháp thay thế GC cho server chạy lâu.