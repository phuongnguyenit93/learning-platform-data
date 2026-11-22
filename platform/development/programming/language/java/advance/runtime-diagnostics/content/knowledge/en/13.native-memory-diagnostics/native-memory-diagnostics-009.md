# 13.9. Phân biệt lỗi tạo native thread, cấp phát trực tiếp thất bại và heap Java đầy

## Mục tiêu

Ba lỗi Java có thể cùng chứa chữ `OutOfMemoryError` nhưng chỉ đến **ba tài nguyên và bước cấp phát khác nhau**:

1. JVM không tạo được **native thread** mới.
2. JVM hoặc thư viện không cấp phát được **direct/off-heap buffer**.
3. JVM không cấp phát được **đối tượng trong Java heap**.

Vì thế, thấy `java.lang.OutOfMemoryError` không đủ để kết luận “heap thiếu, tăng `-Xmx`”. Cần đọc **toàn bộ detail message, stack trace, log JVM, bộ đếm và giới hạn hệ điều hành/container**. Bài tập trung vào **HotSpot JDK 17+**. Thông điệp chính xác, nhóm tài nguyên và cơ chế fail có thể khác theo vendor/JDK, hệ điều hành, collector và thư viện.

## 1. Các vùng tài nguyên khác nhau trong cùng một JVM

```text
Một tiến trình Java (trong giới hạn OS/container)
│
├── Java heap                    → Java objects/arrays, GC quản lý, -Xmx
│   └── DirectByteBuffer wrapper → object trên heap, nhưng payload nằm ngoài heap
│
├── Native / off-heap memory
│   ├── Native thread stacks     → stack và metadata phục vụ OS threads
│   ├── Direct buffer payload    → thường được cấp phát ngoài Java heap
│   ├── Metaspace / Code Cache / JVM internals / GC structures
│   └── JNI / native libraries / memory-mapped regions / phần khác
│
└── Các giới hạn độc lập
    ├── Java heap maximum (-Xmx)
    ├── Direct-buffer reservation limit (-XX:MaxDirectMemorySize)
    ├── OS task/thread quotas và per-thread stack (-Xss ảnh hưởng stack)
    └── Address space, RAM/swap, container memory và cgroup PID quotas
```

Một số khái niệm cần phân biệt:

- **Java heap used:** phần heap chứa đối tượng theo thống kê JVM; **heap committed** là bộ nhớ JVM đã cam kết cho heap, còn **heap max** là trần heap được báo. Ba số này không giống nhau.
- **Native memory:** vùng nhớ ngoài Java heap do JVM, OS, thư viện native hoặc các cơ chế cấp phát ngoài heap sử dụng; **không đồng nghĩa riêng với direct buffer**.
- **Thread stack:** các luồng nền tảng của JVM cần tài nguyên hệ điều hành và vùng stack; tăng số thread có thể tăng native memory hoặc chạm giới hạn task/PID dù heap không đầy.
- **Direct buffer:** đối tượng `java.nio.DirectByteBuffer` có wrapper trong Java heap, nhưng phần dữ liệu thông thường nằm trong native/off-heap memory. Việc nhìn thấy wrapper nhỏ trong heap dump không phản ánh đầy đủ chi phí payload.
- **Reserved, committed và RSS không đồng nhất:** reserved là vùng địa chỉ được dành, committed là mức JVM/OS cam kết theo cơ chế báo cáo, RSS là số trang thực sự resident mà OS ghi nhận tại thời điểm đo. Không cộng cơ học các giá trị reserved để khẳng định RSS.

Cùng một ứng dụng có thể gặp cả ba loại lỗi tại những thời điểm khác nhau. Xác định **thao tác cấp phát nào thất bại trước tiên** rồi mới quyết định cách xử lý.

## 2. Bảng nhận diện nhanh

| Dấu hiệu nổi bật | Tạo native thread thất bại | Direct buffer thất bại | Java heap đầy |
| --- | --- | --- | --- |
| Detail message thường gặp | `unable to create native thread`; có thể kèm `possibly out of memory or process/resource limits reached` | `Cannot reserve ... bytes of direct buffer memory (allocated: ..., limit: ...)` hoặc `Direct buffer memory` | `Java heap space` |
| Vị trí thường thấy trong stack | `Thread.start0`, `Thread.start`, executor tạo worker | `java.nio.Bits.reserveMemory`, `DirectByteBuffer`, `ByteBuffer.allocateDirect` hoặc thư viện NIO/netty | `new`, tạo array, collection, object deserialization; nhiều vị trí khác |
| Tài nguyên trực tiếp bị từ chối | Native thread/OS task và tài nguyên phụ trợ | Direct buffer reservation hoặc cấp phát native | Object/array trên Java heap |
| Bộ đếm cần xem | Số OS threads, Java live threads, `pids.max`/`pids.current`, NMT Thread, memory/address space | BufferPoolMXBean `direct`, direct allocated/capacity, `MaxDirectMemorySize`, RSS, NMT/OS | Heap used/max, GC log, heap sau GC, histogram/dump |
| Khắc phục điển hình sau khi có bằng chứng | Sửa thread growth/pool, giảm concurrency hợp lý; xem quota/stack | Giải phóng buffer/pool đúng vòng đời; chỉnh direct budget trong headroom | Giảm live set/cấp phát, sửa retention; xem `-Xmx` |
| Điều **không** suy được | “Tăng `-Xmx` sẽ tạo thêm thread” | “Java heap thấp thì direct không thể đầy” | “Cứ Java heap space là có memory leak” |

**Chi tiết quan trọng:** `OutOfMemoryError` là một `Error` do JVM/thư viện phát sinh, không phải tình huống kinh doanh bình thường để xử lý bằng cách bắt rồi tiếp tục vô hạn. Khi tiến trình đã cạn tài nguyên, đường xử lý lỗi và cả các lệnh chẩn đoán cũng có thể thất bại.

## 3. Loại A: Không tạo được native thread

### 3.1 Thông điệp, nguồn gốc và ví dụ

Một tình huống trên HotSpot/Linux có thể xuất hiện:

```text
java.lang.OutOfMemoryError: unable to create native thread:
possibly out of memory or process/resource limits reached
    at java.base/java.lang.Thread.start0(Native Method)
    at java.base/java.lang.Thread.start(Thread.java:...)
```

Hoặc log JVM/OS có thể cho thấy `pthread_create` thất bại, ví dụ `EAGAIN`. Đây là **minh họa dạng lỗi**, số dòng, văn bản và errno thực tế tùy nền tảng/JDK.

`Thread.start()` phải tạo một platform/native thread. Hệ điều hành có thể từ chối vì:

- **Số thread tăng quá nhiều**: mỗi request tạo thread mới; không giới hạn số worker; thread không kết thúc; `ExecutorService` được tạo liên tục mà không `shutdown()`; thread pool cấu hình lớn.
- **Giới hạn PID/task**: `RLIMIT_NPROC`, systemd `TasksMax`, cgroup `pids.max` hoặc giới hạn hệ thống khác. Trên Linux, cgroup PID controller đếm **tasks**, nên nhiều thread có thể làm chạm giới hạn ngay cả khi ít process.
- **Không đủ native memory/address space để tạo stack hoặc metadata**: hàng trăm/hàng nghìn thread có thể cùng giữ vùng stack riêng; các thành phần native khác cũng tranh tài nguyên.
- **Memory pressure hoặc giới hạn container**: process còn dư Java heap nhưng OS không thể cấp thêm tài nguyên native. Ngược lại, chỉ thấy `-Xss` lớn chưa đủ kết luận thiếu RAM vật lý vì stack reserved và resident khác nhau.

**Điểm chẩn đoán:** nếu heap dùng thấp nhưng `Thread.start()` fail, hãy kiểm tra quota thread/PID và native memory trước. Cũng cần phân biệt luồng Java ứng dụng với các luồng GC/JIT/native của JVM: số lượng trong `ThreadMXBean` không nhất thiết bằng tổng dòng `Threads` của OS.

### 3.2 Thu thập dữ liệu

Cho tiến trình ví dụ có PID `12345`:

```bash
jcmd 12345 Thread.print -l
jcmd 12345 VM.native_memory summary
```

- `Thread.print -l` ghi thread dump và lock information, giúp nhận diện rất nhiều thread cùng tên/cùng stack (ví dụ worker pool tăng vô hạn). Với hàng nghìn thread, output và chi phí có thể lớn.
- `VM.native_memory summary` chỉ có dữ liệu nếu **Native Memory Tracking (NMT) đã bật khi JVM khởi động**. Trong nhóm `Thread` xem lượng `reserved`, `committed` và số thread JVM hạch toán; không tự đồng nhất các giá trị này với RAM/RSS.
- Đừng vội dump cả heap chỉ để điều tra việc tạo native thread.

Trên **Linux**, kết hợp thông tin OS và cgroup (đường dẫn sau phù hợp **cgroup v2 phổ biến**, có thể khác trong container/v1):

```bash
cat /proc/12345/status
cat /proc/12345/limits
cat /proc/12345/cgroup
cat /sys/fs/cgroup/pids.current
cat /sys/fs/cgroup/pids.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
```

- `/proc/12345/status` có `Threads` và `VmRSS`; `limits` có giới hạn process/task liên quan.
- Nếu `pids.current` sát `pids.max`, ưu tiên xác minh quota. Giá trị `max` thường biểu thị không đặt giới hạn ở cấp cgroup đó, song có thể còn giới hạn cấp cha.
- Các file `/sys/fs/cgroup/...` phía trên mô tả cgroup mà đường dẫn đang trỏ tới. Trong host/container, hãy xác định **đúng cgroup của tiến trình đích** từ `/proc/12345/cgroup`; không lấy chỉ số của một cgroup khác để kết luận.
- Nếu hệ thống không có `/proc` hoặc cgroup v2, dùng công cụ tương đương của OS/Windows (ví dụ Process Explorer/PerfMon) thay vì áp dụng nguyên các lệnh Linux.

**Hướng sửa:** giới hạn tạo thread, dùng thread pool có kích thước và hàng đợi có chủ đích, đóng executor đúng vòng đời, tìm thread leak. Chỉ chỉnh quota sau khi biết ứng dụng cần concurrency đó. `-Xss` ảnh hưởng kích thước stack mỗi Java thread; giảm nó có thể giảm reservation nhưng tăng rủi ro `StackOverflowError` nếu stack call sâu. `-Xmx` không phải nút điều chỉnh trực tiếp cho lỗi này.

## 4. Loại B: Cấp phát direct buffer thất bại

### 4.1 Bản chất và thông điệp

Với `java.nio.ByteBuffer.allocateDirect(n)`, wrapper quản lý nằm trong Java heap nhưng payload thường được cấp ngoài heap. HotSpot có cơ chế quản lý budget direct buffer; khi không thể dành thêm capacity, đường `java.nio.Bits.reserveMemory` có thể ném:

```text
java.lang.OutOfMemoryError:
Cannot reserve 1048576 bytes of direct buffer memory
(allocated: 67108864, limit: 67108864)
    at java.base/java.nio.Bits.reserveMemory(Bits.java:...)
    at java.base/java.nio.DirectByteBuffer.<init>(DirectByteBuffer.java:...)
    at java.base/java.nio.ByteBuffer.allocateDirect(ByteBuffer.java:...)
```

Đây là **ví dụ thông điệp**, không phải stdout bảo đảm. `allocated/limit` là số liệu từ bộ đếm/quy tắc reservation của triển khai direct buffer; **không đồng nghĩa tổng RSS** của cả process. Một phiên bản hoặc thư viện có thể dùng thông điệp khác như `Direct buffer memory`, hoặc báo thất bại cấp phát native ở chỗ khác.

Hai nhóm nguyên nhân phải tách biệt:

1. **Chạm giới hạn direct budget** do `-XX:MaxDirectMemorySize` hoặc cấu hình mặc định của JVM, trong khi Java heap vẫn còn chỗ.
2. **Không thể lấy thêm native memory thực tế** do container/OS/address space/allocator, hoặc vì nguồn native khác đang chiếm nhiều tài nguyên. Một chương trình có thể fail native allocation ngay cả khi chưa đạt hạn mức reservation được cấu hình.

Những tình huống làm direct buffer tăng là I/O/Network, read/write channel, pooled buffer, tạo `allocateDirect` quá thường xuyên, thư viện giữ buffer trong cache/pool, hoặc wrapper còn reachable nên cleaner chưa giải phóng payload.

### 4.2 Direct memory cap và giải phóng

```bash
java -Xmx512m -XX:MaxDirectMemorySize=128m -jar app.jar
```

- `-XX:MaxDirectMemorySize=128m` đặt trần bộ nhớ direct buffer theo triển khai HotSpot/JDK tương ứng, **không phải trần tất cả native memory** (thread stacks, JNI allocations, metaspace, v.v.).
- Direct buffer có thể được dọn khi wrapper không còn reachable và cơ chế cleaner/reference processing hoạt động; **không bảo đảm sẽ được giải phóng ngay khi gán `null`**.
- Nhiều framework có buffer pooling, reference count hoặc cơ chế release riêng; phải đọc lifecycle của framework. Việc giữ một buffer trong pool có thể là chiến lược tái sử dụng hợp lệ, nhưng pool không giới hạn hoặc không release đúng cách có thể gây tăng chiếm dụng.
- `System.gc()` không phải phương thức giải phóng direct buffer đáng tin cậy để cứu một hệ thống đang hết tài nguyên; GC có thể bị trì hoãn hoặc cấu hình khác, và không sửa nguyên nhân giữ buffer.
- **Tăng `-XX:MaxDirectMemorySize`** chỉ hợp lý khi direct usage thực sự bị giới hạn, ứng dụng có nhu cầu chính đáng và OS/container còn đủ headroom. Tăng trần mà không điều tra buffer retention có thể đẩy lỗi từ direct budget sang OOM killer/thiếu native memory.

### 4.3 Đo trực tiếp bằng BufferPoolMXBean

JDK cung cấp `java.lang.management.BufferPoolMXBean`. Với pool tên `direct`:

- `getCount()`: số buffer trong pool được báo cáo, mang tính ước lượng.
- `getTotalCapacity()`: tổng capacity (byte) của các buffer được quản lý trong pool, mang tính ước lượng.
- `getMemoryUsed()`: ước lượng native memory dùng bởi pool; có thể khác capacity do alignment/allocator và **có thể trả `-1`** khi không đo được.

Những chỉ số này không bao phủ mọi allocation bằng JNI, native library, framework tự quản lý hay mọi loại off-heap memory. Cần so với `MaxDirectMemorySize`, log và RSS. Nếu pool direct tăng liên tục trong lúc heap ổn định, ưu tiên tìm những buffer bị giữ, pool không release hoặc mức concurrency I/O.

**Heap dump có thể hiển thị wrapper `DirectByteBuffer` và đường giữ tham chiếu**, nhưng phần payload nằm ngoài heap nên `shallow heap` không biểu thị đầy đủ dung lượng native. Heap dump cũng có thể làm thay đổi hiện trường; không dùng dung lượng file HPROF làm tổng direct memory.

## 5. Loại C: Java heap đầy

### 5.1 Dấu hiệu và nguyên nhân

Một mẫu lỗi:

```text
Exception in thread "worker" java.lang.OutOfMemoryError: Java heap space
    at com.example.Service.buildResult(Service.java:...)
```

Đây là minh họa vị trí stack, không phải mã/lỗi của một ứng dụng cụ thể. JVM không đủ chỗ trong **Java heap** để cấp phát object/array cần thiết (và không thể đáp ứng sau những cơ chế thu gom/mở rộng cho phép).

Nguyên nhân điển hình:

- Heap giới hạn quá thấp so với **live set** và tải hợp lệ.
- Memory leak theo nghĩa object vẫn bị giữ bởi GC roots: `static` cache không eviction, `ThreadLocal` không dọn, listener không unregister, collection tăng liên tục, session lâu không hết hạn.
- Burst cấp phát quá lớn: đọc toàn bộ file/response vào bộ nhớ, tạo cấu trúc trung gian lớn, số request đồng thời cao.
- GC nhiều nhưng thu hồi được rất ít vì phần lớn object vẫn reachable.

**Không phải mọi `OutOfMemoryError` liên quan heap đều có detail `Java heap space`**. Các lỗi `GC overhead limit exceeded`, `Requested array size exceeds VM limit`, `Metaspace` hoặc `Direct buffer memory` có ý nghĩa riêng. Ví dụ `Requested array size exceeds VM limit` có thể do kích thước mảng vượt giới hạn JVM, ngay cả khi heap còn nhiều bộ nhớ.

### 5.2 Đo Java heap và theo dõi GC

```bash
jcmd 12345 GC.heap_info
jcmd 12345 VM.flags
```

Có thể bật GC log ngay khi JVM khởi động:

```bash
java -Xms256m -Xmx512m \
  -Xlog:gc*=info:file=gc.log:time,uptime,level,tags \
  -jar app.jar
```

Khi phân tích, tìm **heap used sau GC**, tần suất GC, pause, tốc độ cấp phát, heap occupancy, object retention và thay đổi sau các đợt tải. Một lúc heap used cao chưa chứng minh leak; **live set tăng dai dẳng qua nhiều lần GC trong điều kiện tải ổn định** là bằng chứng đáng xem.

Nếu cần heap dump để truy vết root:

```bash
jcmd 12345 GC.heap_dump /tmp/java-heap.hprof
```

Lệnh này có chi phí CPU/I/O, cần dung lượng đĩa và trên HotSpot JDK 17 **mặc định yêu cầu Full GC** trừ khi chọn `-all`. Vì vậy nó có thể thay đổi hiện trường; lựa chọn dựa theo mục tiêu điều tra, và không mặc định chạy trên một tiến trình production đang cạn tài nguyên. Có thể dùng MAT để xem Dominator Tree, retained heap, path to GC roots.

Khi cần lưu dump vào lúc JVM ném OOME, có thể chuẩn bị trước:

```bash
java -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/tmp/oom.hprof \
  -jar app.jar
```

**Đừng khẳng định một file HPROF đủ giải thích mọi loại OOME**: heap dump mô tả Java heap và object graph, không phải thống kê toàn bộ native memory hay quota thread/PID. Việc tạo dump khi sự cố cũng cần tài nguyên và có thể thất bại.

## 6. Cách lấy số liệu NMT và giới hạn của nó

**Native Memory Tracking (NMT)** là công cụ của HotSpot giúp theo dõi bộ nhớ nội bộ JVM theo nhóm như `Java Heap`, `Thread`, `Class`, `Code`, `GC`. Cần bật khi **khởi động tiến trình**, không giả định có thể bật đầy đủ cho tiến trình đang chạy nếu trước đó tắt.

Ví dụ:

```bash
java -Xms256m -Xmx512m \
  -XX:MaxDirectMemorySize=128m \
  -XX:NativeMemoryTracking=summary \
  -jar app.jar
```

Sau đó chạy lệnh từ cùng môi trường có quyền attach:

```bash
jcmd 12345 VM.native_memory summary scale=MB
jcmd 12345 VM.native_memory baseline
```

Sau một khoảng workload, lấy delta:

```bash
jcmd 12345 VM.native_memory summary.diff scale=MB
```

- **`Thread` tăng** cùng số thread: xem stack reservations và các cấu trúc native; đồng thời đối chiếu OS task count/quota.
- **`Java Heap` trong NMT** chủ yếu cho biết phạm vi reserved/committed heap, **không thay thế `MemoryMXBean.getHeapMemoryUsage().getUsed()`** để xem object usage.
- **Các nhóm native khác tăng**: cần biết nhóm nào và đối chiếu với profiler, JNI, allocator, OS RSS, BufferPoolMXBean; đừng coi một nhóm NMT bất kỳ là direct buffer.
- **`reserved` lớn không có nghĩa cùng lượng RAM vật lý đã dùng**. `committed` cũng không bằng toàn bộ RSS của tiến trình.
- NMT **không theo dõi toàn bộ allocation của thư viện native/JNI bên thứ ba** và có overhead; kết hợp công cụ OS khi cần. Trong production, cân nhắc chi phí bật NMT.

Nếu lệnh báo NMT chưa bật, **đó là giới hạn quan sát**, không phải bằng chứng tiến trình không dùng native memory.

## 7. Java 17: chương trình chụp ba nhóm chỉ số mà không cố tình gây OOME

Ví dụ an toàn hơn việc tạo hàng nghìn thread hay cấp phát bộ nhớ đến khi crash là **quan sát các tín hiệu** trước/sau một direct-buffer allocation nhỏ. Tạo file **`MemoryFailureSignals.java`**:

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;
import java.nio.ByteBuffer;

public class MemoryFailureSignals {
    private static void snapshot() {
        MemoryUsage heap = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        System.out.printf("heap.used=%d heap.committed=%d heap.max=%d%n",
                heap.getUsed(), heap.getCommitted(), heap.getMax());
        System.out.printf("threads.live=%d threads.peak=%d threads.started=%d%n",
                threads.getThreadCount(),
                threads.getPeakThreadCount(),
                threads.getTotalStartedThreadCount());

        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
            if ("direct".equals(pool.getName())) {
                System.out.printf("direct.count=%d direct.capacity=%d direct.used=%d%n",
                        pool.getCount(), pool.getTotalCapacity(), pool.getMemoryUsed());
            }
        }
    }

    public static void main(String[] args) {
        System.out.println("BEFORE");
        snapshot();

        ByteBuffer buffer = ByteBuffer.allocateDirect(1024 * 1024);
        buffer.putInt(0, 42);

        System.out.println("AFTER");
        snapshot();
        System.out.println("sample.capacity=" + buffer.capacity());
        System.out.println("sample.value=" + buffer.getInt(0));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 MemoryFailureSignals.java
java -Xms64m -Xmx256m \
  -XX:MaxDirectMemorySize=64m \
  -XX:NativeMemoryTracking=summary \
  MemoryFailureSignals
```

Các dòng **chắc chắn theo logic ví dụ khi allocation thành công**:

```text
BEFORE
...
AFTER
...
sample.capacity=1048576
sample.value=42
```

`...` trong đoạn trên chỉ diễn đạt rằng có những dòng metric **biến động theo JVM/môi trường**, không phải output thực để sao chép. Giá trị `heap.used`, `heap.committed`, `heap.max`, `threads.live` và các chỉ số direct pool cần đọc từ lần chạy thật; `direct.used` có thể là `-1` nếu JVM không hỗ trợ ước lượng. Có thể có nhiều nền tảng JVM mà cách hiện metric không hoàn toàn giống HotSpot.

**Diễn giải:**

- `heap.used` và `heap.max` cho biết áp lực Java heap. Một direct-buffer payload 1 MiB không có nghĩa `heap.used` phải tăng thêm 1 MiB.
- `direct.capacity` và `direct.used` phản ánh buffer pool do JVM báo; sau khi tạo buffer mới, thường tăng tương ứng nếu buffer còn reachable. Giới hạn `MaxDirectMemorySize` áp dụng theo ngữ nghĩa JVM, không phải toàn bộ native RSS.
- `threads.live` là **số Java platform threads còn sống** do `ThreadMXBean` thấy; không coi nó là con số task/PID chính xác của OS.
- Để xác định **nguyên nhân OOME**, chụp metric định kỳ và ghép với **stack trace/detail message tại thời điểm lỗi**. Một lần snapshot không chứng minh memory leak.

Chương trình không chủ động làm cạn bộ nhớ và không tạo thread hàng loạt. Nếu môi trường đã quá hạn chế, bản thân `allocateDirect` 1 MiB vẫn có thể thất bại; đó là một dấu hiệu cần điều tra, không phải kết quả được ép sẵn.

## 8. Quy trình điều tra: đọc bằng chứng rồi mới chỉnh cấu hình

### Bước 1 — Chốt loại lỗi chính xác

Giữ **nguyên văn một vài dòng đầu và stack trace**, PID, timestamp, JVM vendor/version, cờ khởi động, workload, giới hạn container/OS. Phân nhánh theo detail message:

```text
Có OutOfMemoryError?
  |
  +-- "unable to create native thread"
  |      -> Thread count / task quota / native stacks / native headroom
  |
  +-- "Cannot reserve ... direct buffer memory" hoặc "Direct buffer memory"
  |      -> Direct pool / MaxDirectMemorySize / buffer lifecycle / native headroom
  |
  +-- "Java heap space"
  |      -> Heap used/limit / GC / live set / allocation / GC roots
  |
  +-- Thông điệp khác (Metaspace, array size, native allocation ...)
         -> Điều tra đúng vùng tài nguyên của thông điệp đó
```

Stack trace bổ sung nơi cấp phát thất bại; **không suy toàn bộ nguyên nhân chỉ từ tên method** nếu detail message đã có ngữ nghĩa rõ hơn.

### Bước 2 — Kiểm tra tài nguyên nền và container

- `-Xmx` và heap usage, `-XX:MaxDirectMemorySize`, số thread, `-Xss`, native NMT, RSS.
- Với Linux: process limits, `pids.current/pids.max` và `memory.current/memory.max` của **đúng cgroup**; nếu bị giới hạn ở cha, cần kiểm tra cây cgroup.
- **OS OOM killer là sự kiện khác với Java `OutOfMemoryError`**: một tiến trình bị `SIGKILL` có thể không in Java exception. Container thường báo exit code 137 khi nhận SIGKILL, nhưng **137 một mình không chứng minh OOM kill**; cần đối chiếu kernel log, Kubernetes event hoặc cgroup `memory.events`/`oom_kill`.

### Bước 3 — Đối chiếu tín hiệu và quyết định hướng sửa

| Tình huống | Bằng chứng cần thêm | Hướng xử lý sau khi xác minh |
| --- | --- | --- |
| Heap sau GC bình thường, thread count tăng liên tục, `pids.current` sát `pids.max` | Thread dump theo thời gian, stack/owner, cấu hình pool | Sửa tạo thread vô hạn/thiếu shutdown, giảm số worker hoặc điều chỉnh quota có cơ sở |
| Thread count không quá lớn nhưng `Thread.start` fail, native committed/RSS cao | Cgroup RAM, `/proc/PID/limits`, `-Xss`, NMT/OS usage | Xác định hạn mức stack/address space/native; dành headroom hoặc điều chỉnh phù hợp |
| `direct.capacity` sát mức limit, heap còn dư | Buffer pool/JMX theo thời gian, Netty/framework release, stack `allocateDirect` | Sửa lifecycle/pooling, kiểm soát concurrency, cân nhắc direct cap nếu đủ RAM |
| Direct reservation chưa sát cap nhưng OS hết memory | RSS/cgroup, NMT, native library stats, allocator | Điều tra phần native khác; tăng cap direct sẽ không giải quyết thiếu RAM |
| `Java heap space`, heap sau GC tăng qua nhiều cửa sổ tải ổn định | GC log, heap dump, retained heap, GC root | Sửa retention/leak hoặc mức sử dụng hợp lệ vượt cấu hình |
| Heap OOME khi batch dữ liệu rất lớn | Allocation profiling, số phần tử, payload size, concurrency | Stream/chunk dữ liệu, giảm buffering, kiểm soát kích thước batch; cân nhắc heap size |
| Process bị OOMKilled không có Java exception | Cgroup `oom_kill`/OS log, RSS, process limit | Cân đối toàn bộ RSS và giới hạn container, không quy ngay cho heap |

### Bước 4 — Đặt ngân sách bộ nhớ có khoảng dự phòng

Ví dụ container có **1 GiB memory limit** nhưng JVM được cấu hình `-Xmx768m`, direct cap `256m` và chạy vài trăm platform threads: đây là **cấu hình có nguy cơ thiếu headroom** cho thread stacks, metaspace, code cache, JIT, GC, thư viện native, page cache và hoạt động phụ trợ.

Tuy nhiên **không được cộng `768 + 256 + N × Xss` rồi gọi kết quả là RSS**: `-Xmx` là heap max, direct cap là hạn mức, stack có reserved/committed khác nhau, và một số cấp phát không trực tiếp resident. Phải đo thực tế dưới peak load rồi đặt headroom phù hợp môi trường.

Điều chỉnh cần theo đúng nút giới hạn:

- **Thread problem:** ưu tiên nguyên nhân tăng thread và quota/task; đừng tăng heap chỉ vì thông điệp có chữ `OutOfMemoryError`.
- **Direct problem:** quản lý direct buffers và reservation; tránh tăng direct cap vượt RAM thực.
- **Heap problem:** giảm live set hoặc sizing hợp lý; đừng giảm `-Xmx` mù quáng vì muốn “chừa native memory” khi heap đã thật sự quá nhỏ.

Sau khi sửa, chạy lại **cùng workload** và so sánh heap after-GC, thread growth, direct pool, RSS, cgroup pressure và các lỗi/pause.

## 9. Sai lầm thường gặp

1. **“Mọi `OutOfMemoryError` đều do Java heap đầy.”** Sai: native thread, direct buffer, metaspace và native allocator có thể thất bại độc lập.
2. **“Heap used chỉ 40% thì toàn bộ process vẫn dư 60% RAM.”** Sai: heap used không tính direct, native thread stacks và các vùng khác.
3. **“Tăng `-Xmx` sửa được `unable to create native thread`.”** Không có bảo đảm; trong container giới hạn, tăng heap còn có thể thu hẹp headroom native.
4. **“Giảm `-Xss` luôn an toàn và giải quyết hết lỗi thread.”** Sai: có thể chạm quota task, và stack nhỏ hơn có thể gây `StackOverflowError`.
5. **“DirectByteBuffer nằm trong heap nên tăng `-Xmx` là đủ.”** Wrapper ở heap nhưng payload ngoài heap; cần xem direct cap và native memory.
6. **“`-XX:MaxDirectMemorySize` là trần native memory toàn tiến trình.”** Sai: nó chỉ điều khiển một phạm vi direct-buffer reservation, không quản lý mọi JNI/native allocations.
7. **“Cứ gọi `System.gc()` để chữa direct buffer OOME.”** Không đáng tin cậy; không sửa buffer vẫn reachable hay pool quản lý sai.
8. **“Có nhiều object trong heap dump là leak.”** Chưa đủ: cần retained heap/path tới GC roots và xu hướng.
9. **“NMT summary là số RSS chính xác hoặc bao quát JNI.”** Sai: nguồn dữ liệu có phạm vi và semantics riêng.
10. **“Exit code 137 luôn là Java heap OOME.”** Sai: SIGKILL và OOM killer khác Java exception; cần OS/cgroup event.
11. **“Thấy `Threads` trong Java MXBean là biết chính xác OS task quota.”** Sai: còn native JVM threads và các task khác cùng cgroup.
12. **“Cứ tăng cả `-Xmx`, direct cap và thread pool cho chắc.”** Trong cùng memory limit, các khoản chi tiêu cạnh tranh nhau; phải đo trước, tăng có mục tiêu.

## 10. Câu hỏi tự kiểm tra

**Câu 1:** `heap.used` thấp, `Thread.start()` ném `unable to create native thread`, `pids.current` gần `pids.max`. Bước đầu cần làm gì?  
**Đáp án:** Điều tra số thread/tasks và quota, tìm thread pool/thread leak và xác định cgroup thật của tiến trình; tăng `-Xmx` không phải câu trả lời trực tiếp.

**Câu 2:** `ByteBuffer.allocateDirect` ném `Cannot reserve ... allocated: 134217728, limit: 134217728`. Điều này nói gì?  
**Đáp án:** Theo ngữ nghĩa của thông báo, direct-buffer reservation đang chạm giới hạn 128 MiB; kiểm tra buffer lifecycle, pool/concurrency và `MaxDirectMemorySize` trước khi tăng cap.

**Câu 3:** `OutOfMemoryError: Java heap space` nhưng RSS vẫn thấp hơn memory limit của container. Có mâu thuẫn không?  
**Đáp án:** Không. `-Xmx` là giới hạn heap riêng, có thể hết heap trước khi process chạm memory limit.

**Câu 4:** NMT báo `Thread reserved=1 GiB`. Có nghĩa ngay lập tức 1 GiB RAM vật lý đang resident?  
**Đáp án:** Không. Reserved virtual address không bằng RSS; cần xem committed, OS RSS và cgroup usage.

**Câu 5:** Direct buffer cap chỉ 256 MiB, OS báo process RSS cao. Có thể khẳng định direct buffer là thủ phạm?  
**Đáp án:** Không. Cần JMX direct pool, NMT/OS metrics và những native allocations khác; cap không phải mức đã dùng.

**Câu 6:** Container bị `OOMKilled` nhưng không thấy `java.lang.OutOfMemoryError`. Vì sao?  
**Đáp án:** Kernel/container có thể kill tiến trình từ bên ngoài khi cạn tài nguyên; Java không bắt buộc kịp tạo exception. Kiểm tra `memory.events`/system logs và cấu hình limit.

## Tài liệu tra cứu

- [Oracle JDK 17 — The `jcmd` Command (Thread.print, VM.native_memory, GC.heap_info)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle JDK 17 — The `java` Command (`-Xmx`, `-XX:MaxDirectMemorySize`, `-XX:NativeMemoryTracking`)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle JDK 17 — Troubleshoot Memory Leaks và Java OutOfMemoryError](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-memory-leaks.html)
- [Oracle JDK 17 — Diagnostic Tools và Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html)
- [Java SE 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)
- [Java SE 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html)
