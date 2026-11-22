# Phân biệt `OutOfMemoryError` với tiến trình Java bị hệ điều hành chấm dứt vì thiếu bộ nhớ

**Chủ đề:** Bộ nhớ trong container — Java 10 trở lên.

Trong một Java service chạy trong Docker hoặc Kubernetes, câu “ứng dụng bị OOM” có thể chỉ **hai cơ chế hoàn toàn khác nhau**:

1. **`java.lang.OutOfMemoryError` (Java OOME):** JVM hoặc thư viện phát sinh một **`Error` của Java** khi một yêu cầu cấp phát tài nguyên không thực hiện được. Thông thường có thể xuất hiện stack trace và thông điệp như `Java heap space`, `Metaspace`, `Direct buffer memory` hoặc `unable to create native thread`. Tùy trường hợp, code có thể bắt được Error; JVM có thể tiếp tục hoặc tự thoát vì policy riêng.
2. **Tiến trình bị hệ điều hành chấm dứt (kernel/cgroup OOM kill):** Linux kernel chọn process làm nạn nhân khi thiếu bộ nhớ theo chính sách hệ thống hoặc cgroup. Kernel gửi **`SIGKILL`**, process bị hủy **bên ngoài cơ chế Java exception**. JVM không có cơ hội catch `OutOfMemoryError`, chạy `finally`/shutdown hook hoặc mặc định tạo Java heap dump từ chính sự kiện SIGKILL đó.

**Điểm nhận diện quan trọng:** Trong Kubernetes, một container có trạng thái kết thúc `reason: OOMKilled` là dấu hiệu hệ điều hành/runtime báo nó bị OOM kill. **Exit code 137** thường là `128 + 9` (signal 9 = `SIGKILL`), nhưng **137 một mình không chứng minh OOMKilled**: một người vận hành hoặc công cụ khác cũng có thể gửi `SIGKILL`. Ngược lại, một Java `OutOfMemoryError` **không bắt buộc** đi kèm trạng thái `OOMKilled` hoặc mã 137.

Bài giải thích cơ chế, dấu hiệu chẩn đoán, ảnh hưởng của `-Xmx`/native memory/cgroups, cách thu thập bằng chứng trong Kubernetes, các cờ JVM còn được hỗ trợ và cách xây budget an toàn. Sáu chương trình Java mẫu đã được biên dịch với `javac --release 10` và chạy trong môi trường thử riêng trên **OpenJDK 21**. Thử nghiệm gửi `SIGKILL` bên ngoài chỉ chứng minh **hành vi signal 9**, **không phải một cgroup OOM kill thực tế**; tài liệu Linux/Kubernetes được dùng để giải thích phần kernel.

## 1. Đặt hai nguyên nhân cạnh nhau

| Câu hỏi | `OutOfMemoryError` do Java/JVM | Kernel/cgroup OOM kill |
| --- | --- | --- |
| Ai phát hiện và quyết định? | JVM/Java runtime hoặc thư viện trong quá trình cấp phát | **Linux kernel**, dựa trên memory pressure/cgroup và chính sách OOM |
| Bản chất | Một `java.lang.OutOfMemoryError` thuộc hệ thống `Throwable` | **Tín hiệu `SIGKILL`** chấm dứt process |
| Có Java stack trace? | **Có thể có**, tùy nguồn Error, JVM/logging | **Không có Java OOME stack trace do chính SIGKILL tạo ra** |
| Java `catch (OutOfMemoryError)` có chạy? | Có thể, nếu luồng thực thi và VM chưa bị buộc thoát | **Không**; kernel không ném Java exception |
| `finally` và shutdown hooks | Có thể chạy theo control flow và chính sách thoát | **Không chạy do `SIGKILL`** |
| `-XX:+HeapDumpOnOutOfMemoryError` | Có thể tạo `.hprof` với **Java heap OOME đủ điều kiện** | **Không tự kích hoạt chỉ vì `SIGKILL`** |
| Exit code điển hình | Tùy app, uncaught Error, policy JVM; ví dụ 1/3 ở môi trường kiểm thử | Thường **137** nếu process bị SIGKILL trong quy ước shell/container |
| Kubernetes `reason` | Không bắt buộc là `OOMKilled` | Có thể được ghi **`OOMKilled`** khi container bị kernel OOM kill |
| Hướng điều tra | Heap, direct buffers, metaspace, thread/native allocations, GC, heap dump/logs | Cgroup memory usage/events, `OOMKilled` status, RSS/native/page cache, kernel logs |
| Có thể xảy ra đồng thời? | **Có** | **Có** — cùng một workload có thể lần lượt tạo Java OOME rồi bị kill |

**Không dùng một trường duy nhất để phân loại.** Kết luận tốt dựa trên nhiều bằng chứng được sắp theo thời gian: trạng thái container, exit code, log trước khi chết, dữ liệu cgroup và memory/GC diagnostics.

## 2. Java `OutOfMemoryError` là gì?

Theo Oracle Javadoc, `java.lang.OutOfMemoryError` kế thừa `VirtualMachineError`, được phát sinh khi JVM không thể cấp phát object vì không đủ memory và garbage collector không giải phóng đủ không gian. Các runtime còn có thể phát sinh những thông điệp OutOfMemoryError liên quan tài nguyên/native allocations ngoài Java heap.

~~~text
java.lang.Object
  -> java.lang.Throwable
     -> java.lang.Error
        -> java.lang.VirtualMachineError
           -> java.lang.OutOfMemoryError
~~~

Đặc điểm quan trọng:

- **`OutOfMemoryError` không phải checked exception**. Java không bắt buộc programmer khai báo hoặc catch nó.
- JVM có thể tạo `OutOfMemoryError` với stack trace không ghi được hoặc suppression bị vô hiệu để giảm yêu cầu cấp phát trong tình huống bộ nhớ cạn kiệt; **đừng mặc định stack trace lúc nào cũng đầy đủ**.
- `catch (OutOfMemoryError e)` là **cú pháp Java hợp lệ**, nhưng không phải chiến lược chữa cháy an toàn cho mọi ứng dụng. VM có thể không còn đủ tài nguyên để log hoặc xử lý nghiệp vụ nhất quán.
- Một OOME không tự có nghĩa **có memory leak**. Có thể chỉ là heap cấu hình quá nhỏ, một batch quá lớn, buffer native vượt limit, quá nhiều threads hoặc lỗi lập kế hoạch dung lượng.
- Một Java OOME có thể phát sinh **ngay cả khi container còn memory headroom**. Ví dụ `-Xmx32m` với yêu cầu cấp phát 128 MiB trên máy còn rất nhiều RAM.

### Những thông điệp OOME cần phân biệt

| Thông điệp hoặc loại tình huống | Phạm vi thường liên quan | Cách điều tra |
| --- | --- | --- |
| `Java heap space` | Không cấp phát được Java object/array trong giới hạn heap | Heap usage, `-Xmx`, allocation rate, retention, heap dump |
| `GC overhead limit exceeded` | Quá nhiều công sức GC với rất ít bộ nhớ được thu hồi, trong cấu hình collector hỗ trợ | GC log và live heap, leak/heap sizing; **không mặc định mọi GC đều phát sinh thông điệp này** |
| `Metaspace` | Class metadata / native metaspace | Số class/class loader, leak của loader, `MaxMetaspaceSize` nếu có |
| Direct buffer memory, hoặc `Cannot reserve ... direct buffer memory` | Giới hạn direct buffers/off-heap ByteBuffer | `MaxDirectMemorySize`, number/lifetime of buffers, native memory |
| `unable to create native thread` / thông điệp tương tự | OS thread creation, native stack, process/thread limits hoặc tài nguyên OS | Thread count, thread stack, cgroup pids, ulimit, native memory |
| `Requested array size exceeds VM limit` | Vượt giới hạn kích thước một Java array | Thu nhỏ data chunk; không đồng nhất với container memory limit |

**Không suy luận mọi OOME đều thuộc Java heap.** Với lỗi native thread có thể phải kiểm tra cả `pids.max`/OS thread limits, không chỉ `-Xmx`. Với direct memory, một ứng dụng có thể còn Java heap khả dụng nhưng vẫn gặp OutOfMemoryError.

## 3. Cơ chế Linux/cgroup OOM kill khác hẳn

Linux quản lý bộ nhớ theo process, trang ẩn danh, file-backed pages, page cache và các tài nguyên kernel. Trong container, một **memory cgroup** có thể áp giới hạn tổng bộ nhớ của nhóm process, trong khi Java heap chỉ là **một phần** sử dụng của JVM.

Với **cgroups v2**, các tệp tiêu biểu:

| Tệp | Ý nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| `memory.max` | Hard memory limit (hoặc `max` nếu không giới hạn) | Khi đến ngưỡng và không thể reclaim, **OOM killer có thể được kích hoạt** |
| `memory.current` | Memory hiện được tính cho cgroup | Không phải chỉ Java heap |
| `memory.peak` | Đỉnh memory usage ghi nhận, nếu kernel hỗ trợ | Dùng để tìm spike mà metric sampling bỏ sót |
| `memory.events` | Các bộ đếm sự kiện, có tính phân cấp | `oom` và `oom_kill` có ý nghĩa khác nhau |
| `memory.events.local` | Bộ đếm event ở cgroup hiện tại | Hữu ích khi cần tránh gộp toàn bộ subtree |
| `memory.stat` | Phân rã anon/file/kernel... | Giúp phân biệt nguồn tiêu thụ |
| `memory.swap.max` | Giới hạn swap cho cgroup trên hệ thống có hỗ trợ | Không đồng nhất với RAM hard limit |

**`memory.events` không phải một boolean**. Ví dụ `oom_kill 2` là **số lần process thuộc cgroup bị OOM killer chấm dứt**, không nói rằng pod đang sống vừa bị kill đúng hai lần, cũng không trực tiếp chỉ ra một Java allocation nào. Bộ đếm có thể là dữ liệu phân cấp; xem thêm `memory.events.local` nếu điều tra cgroup cụ thể.

**`oom` khác `oom_kill`:** counter `oom` ghi một số tình huống cấp phát đến giới hạn/khả năng thất bại; `oom_kill` ghi số process thực sự bị OOM killer kill. Không đọc hai counter như đồng nghĩa.

~~~text
Linux cgroup có memory.max = 512 MiB
                      |
JVM heap + non-heap + direct buffers + native memory
 + thread stacks + file cache được tính cho cgroup
                      |
             Vượt giới hạn?
                  /       \
               Chưa        Có
                |           |
          Tiếp tục chạy   Kernel thử reclaim
                            |
                    Không đủ để giảm dùng
                            |
                    OOM killer chọn nạn nhân
                            |
                       SIGKILL (9)
                            |
                Process biến mất, không có
                Java catch/finally để xử lý
~~~

Đây là **mô hình cơ chế phổ biến**, không phải khẳng định Linux kill ngay khoảnh khắc một lần ghi vượt `memory.max`. Theo tài liệu Kubernetes, memory limit được áp dụng **theo phản ứng** khi có memory pressure; kernel có thể reclaim trước khi kill, và một số trường hợp vượt tạm thời vẫn có thể diễn ra.

### Node-wide OOM và cgroup OOM

- **Cgroup OOM:** cgroup đang chịu hard memory limit có thể kích hoạt OOM killer; nạn nhân thuộc phạm vi cgroup theo quy tắc kernel.
- **System-wide OOM:** toàn node thiếu memory; kernel có thể chọn process dựa trên các yếu tố như mức tiêu thụ và `oom_score_adj`.
- **Kubernetes Evicted:** kubelet cũng có thể evict pod do node memory pressure, khác với một container được báo `OOMKilled` vì kernel kill.

**Không gộp mọi trường hợp pod biến mất thành “vượt container memory limit”.** Đọc `reason` và event thực tế; `OOMKilled` không tự cho bạn toàn bộ nguyên nhân gốc (quota container hay áp lực node, source of memory, thời điểm spike).

## 4. Vì sao `-Xmx` không phải giới hạn memory của container?

Một JVM sử dụng bộ nhớ ngoài Java heap:

~~~text
Container memory limit: 512 MiB
    |
    +-- Java heap (giới hạn riêng bởi -Xmx)
    +-- Metaspace/class metadata
    +-- Code cache/JIT compiler
    +-- Thread stacks và native runtime
    +-- Direct ByteBuffer / off-heap allocations
    +-- JVM native allocations / JNI libraries
    +-- Memory mappings / tài nguyên kernel/file cache được tính
    +-- Các process phụ nếu chung memory cgroup
~~~

**`-Xmx384m` không đồng nghĩa “process luôn chỉ dùng tối đa 384 MiB”.** Nó kiểm soát **giới hạn tối đa Java heap**. JVM vẫn cần bộ nhớ khác; container có thể bị kernel kill trước khi Java heap chạm `-Xmx` nếu non-heap/native/cache làm tổng memory vượt hard limit.

Ngược lại, `-Xmx32m` đặt thấp có thể làm một Java object allocation ném `OutOfMemoryError` **dù container limit là 512 MiB và cgroup vẫn còn room**.

### Một ví dụ budget

| Khoản mục | Giá trị giả định |
| --- | ---: |
| Container hard memory limit | 512 MiB |
| `-Xmx` | 384 MiB |
| Chênh lệch trên giấy | 128 MiB |
| Metaspace, code cache, thread stacks, direct/native, page cache... | **Phải đo** |
| “128 MiB chắc chắn đủ cho mọi ứng dụng” | **Không thể kết luận** |

Chênh lệch `512 - 384 = 128 MiB` là **budget lý thuyết còn lại trước các thành phần khác**, không phải memory headroom được kernel bảo đảm ở mọi thời điểm. Một ứng dụng dùng nhiều native threads hoặc direct buffers có thể cần đáng kể hơn. Hãy đo **peak** cùng GC/native/container metrics và đặt margin dựa trên workload.

### `Runtime.maxMemory()` không đo container limit

Các API `Runtime`:

- `Runtime.getRuntime().maxMemory()`: lượng memory tối đa JVM cố gắng cấp cho **Java heap**.
- `Runtime.getRuntime().totalMemory()`: tổng bộ nhớ heap hiện JVM cấp/committed theo hợp đồng API.
- `Runtime.getRuntime().freeMemory()`: vùng trống trong heap đã cấp/committed.
- Chúng **không phải** cách đọc `memory.max` hoặc toàn bộ RSS/container working set.

Nếu cần chi tiết heap/non-heap, dùng `MemoryMXBean`, GC metrics, JFR và Native Memory Tracking phù hợp; nếu cần kết luận kernel OOMKill, đọc **cgroup/container status**.

## 5. Chương trình chạy được 1 — OOME của Java heap vẫn có thể được catch

Tạo file **`HeapOomeCaughtDemo.java`**:

~~~java
public class HeapOomeCaughtDemo {
    public static void main(String[] args) {
        System.out.println("main-started=true");
        try {
            byte[] bytes = new byte[128 * 1024 * 1024];
            System.out.println("allocated=" + bytes.length);
        } catch (OutOfMemoryError error) {
            System.out.println("caught-java-error=true");
            System.out.println("heap-space-message=" +
                    "Java heap space".equals(error.getMessage()));
        }
        System.out.println("after-catch=true");
    }
}
~~~

**Biên dịch với Java 10 API:**

~~~bash
javac --release 10 HeapOomeCaughtDemo.java
~~~

**Chạy trong một tiến trình JVM thử nghiệm có heap 32 MiB:**

~~~bash
java -Xmx32m HeapOomeCaughtDemo
~~~

**Stdout đã kiểm thử trên OpenJDK 21:**

~~~text
main-started=true
caught-java-error=true
heap-space-message=true
after-catch=true
~~~

**Giải thích:**

1. Chương trình cố cấp phát array **128 MiB** trong Java heap bị giới hạn ở **32 MiB**.
2. JVM phát sinh `OutOfMemoryError` liên quan `Java heap space`.
3. Đoạn `catch` nhận được Java `Error`; đoạn code sau `catch` vẫn chạy, vì ví dụ không đặt chính sách JVM buộc thoát.
4. **Không có bằng chứng kernel OOM killer** từ thí nghiệm này. Đây là giới hạn **heap JVM**, không phải kiểm thử memory limit của Docker/Kubernetes.
5. Catch thành công **không có nghĩa ứng dụng production luôn phục hồi an toàn** sau bất kỳ OOME nào. Đây là demo trong process riêng với lỗi cấp phát dự đoán được.

**Quan trọng:** Đừng đưa đoạn tạo array 128 MiB vào service thật để “kiểm tra OOM”; chỉ chạy trong môi trường kiểm thử với heap nhỏ và kiểm soát.

### Phân biệt Java OOME và exit code

Trong ví dụ trên, vì error được catch và `main` kết thúc bình thường, JVM có thể trả **exit code 0**. Một uncaught OOME thường làm main thread thất bại và process có thể kết thúc nonzero, nhưng hành vi cuối phụ thuộc việc còn non-daemon threads hay policy JVM. **Không lấy riêng exit code bằng 0 để khẳng định chưa từng có `OutOfMemoryError`.**

## 6. Chương trình chạy được 2 — Direct memory OOME dù heap còn trống

Lỗi cấp phát **off-heap direct buffer** có thể tạo OOME riêng, không đồng nghĩa heap cạn. Tạo file **`DirectMemoryOomeDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

public class DirectMemoryOomeDemo {
    public static void main(String[] args) {
        List<ByteBuffer> keepAlive = new ArrayList<>();
        boolean caught = false;

        try {
            for (int i = 0; i < 3; i++) {
                keepAlive.add(
                        ByteBuffer.allocateDirect(8 * 1024 * 1024));
            }
        } catch (OutOfMemoryError error) {
            caught = true;
            System.out.println("direct-error-type=" +
                    error.getClass().getSimpleName());
        }

        System.out.println("direct-oom-caught=" + caught);
        System.out.println("buffers-kept=" + keepAlive.size());
        System.out.println("heap-still-allocatable=" +
                (new byte[1024]).length);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 10 DirectMemoryOomeDemo.java
java -Xmx64m -XX:MaxDirectMemorySize=16m DirectMemoryOomeDemo
~~~

**Stdout đã kiểm chứng với OpenJDK 21:**

~~~text
direct-error-type=OutOfMemoryError
direct-oom-caught=true
buffers-kept=2
heap-still-allocatable=1024
~~~

Ba yêu cầu buffer 8 MiB vượt giới hạn direct-buffer memory 16 MiB, vì hai buffer đầu còn được giữ trong `List`. Trên runtime kiểm thử, JVM ném `OutOfMemoryError` ở lần cấp phát thứ ba; code bắt được error và vẫn tạo được một Java array 1 KiB.

**Hai bài học quan trọng:**

- **Java heap còn đủ** không chứng minh mọi vùng memory native/direct đều đủ.
- Giới hạn `MaxDirectMemorySize` **khác** `-Xmx` và **khác** hard memory limit của cgroup. Thay đổi trực tiếp một giới hạn có thể thay kiểu lỗi nhưng chưa giải quyết áp lực tổng memory.

Không cố ý dùng giá trị `MaxDirectMemorySize` cực thấp trong production chỉ để “phòng OOMKilled” nếu chưa hiểu yêu cầu direct I/O của thư viện. Các framework networking có thể cần nhiều direct buffers và có chính sách pool riêng.

## 7. Chương trình chạy được 3 — Đọc `Runtime` đúng phạm vi

Lưu **`MemoryScopeDemo.java`**:

~~~java
public class MemoryScopeDemo {
    static final long MIB = 1024L * 1024L;

    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();
        long max = runtime.maxMemory();
        long committed = runtime.totalMemory();
        long free = runtime.freeMemory();

        System.out.println("heap-max-mib=" + max / MIB);
        System.out.println("heap-committed-not-above-max=" +
                (committed <= max));
        System.out.println("heap-free-not-above-committed=" +
                (free <= committed));
        System.out.println("heap-used-not-negative=" +
                (committed - free >= 0));
        System.out.println("this-is-container-limit=false");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 10 MemoryScopeDemo.java
java -Xmx64m MemoryScopeDemo
~~~

**Stdout ở OpenJDK 21 trong thí nghiệm:**

~~~text
heap-max-mib=64
heap-committed-not-above-max=true
heap-free-not-above-committed=true
heap-used-not-negative=true
this-is-container-limit=false
~~~

Kết quả minh họa **giới hạn heap JVM** với `-Xmx64m` và quan hệ các số heap. `heap-max-mib` có thể chịu alignment/ergonomics theo runtime; trong thử nghiệm đúng bằng 64. **Dòng `this-is-container-limit=false` là thông báo chủ động của chương trình**, không phải phép tự phát hiện cgroup. Nó nhắc rằng `Runtime.maxMemory()` không phải hard limit Linux cgroup.

Nếu muốn xem container limit trên Linux, phải đọc **cgroup** hoặc công cụ container orchestration, không dùng `Runtime.maxMemory()` rồi nhầm nó với `memory.max`.

## 8. OOME có thể làm JVM tự thoát vì cờ cấu hình

Một Java `OutOfMemoryError` bình thường vẫn là một `Error` theo flow Java, nhưng JVM có **các chính sách tùy chọn**.

### `-XX:+ExitOnOutOfMemoryError`

~~~bash
java -Xmx32m -XX:+ExitOnOutOfMemoryError HeapOomeCaughtDemo
~~~

Khi HotSpot nhận sự kiện OOME thuộc phạm vi cờ này, JVM **chủ động thoát**; chương trình không tiếp tục `after-catch=true` như trường hợp chỉ có `-Xmx32m`. Trong thử nghiệm OpenJDK 21, command kết thúc **exit code 3**, có:

~~~text
main-started=true
Terminating due to java.lang.OutOfMemoryError: Java heap space
~~~

và **không có dòng `after-catch=true`**.

Đừng dùng exit code 3 như một quy tắc portable cho mọi JDK; đây chỉ là số quan sát trong một test cụ thể. **Cờ do JVM tự thoát vì OOME không phải `SIGKILL` của kernel**.

### `-XX:+HeapDumpOnOutOfMemoryError`

~~~bash
java -Xmx32m -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=./dumps HeapOomeCaughtDemo
~~~

Khi được kích hoạt bởi một **Java heap exhaustion thuộc phạm vi hỗ trợ**, HotSpot tạo heap dump `.hprof` vào vị trí đã định. Với thử nghiệm không đặt `ExitOnOutOfMemoryError`, heap dump có thể được tạo ngay khi phát sinh OOME, **kể cả khi code sau đó bắt được Error**.

Trong thử nghiệm OpenJDK 21 với một chương trình tạo uncaught Java heap OOME, file `.hprof` được sinh thành công (khoảng 3,5 MB ở workload cực nhỏ). **Không hứa rằng mọi loại OutOfMemoryError đều tạo heap dump**: theo tài liệu Oracle `java`, `HeapDumpOnOutOfMemoryError` áp dụng cho **Java heap exhaustion do JVM phát sinh**, không áp dụng cho mọi native-thread error hay OOME do Java code tự `throw`.

**Đừng áp dụng `HeapDumpOnOutOfMemoryError` như công cụ duy nhất để bắt OOMKilled.** Khi kernel gửi `SIGKILL`, JVM không được thông báo bằng một Java OOME nên **không thể tự chạy heap-dump hook chỉ vì tín hiệu đó**.

### `-XX:+CrashOnOutOfMemoryError` và `-XX:OnOutOfMemoryError`

Những tùy chọn này thuộc nhóm xử lý khi JVM phát hiện OOME, nhưng có **tác dụng và giới hạn riêng**. `OnOutOfMemoryError` có thể chạy command khi **Java heap OOME do JVM phát sinh**; nó không tự động áp dụng mọi trường hợp native/thread resource exhaustion. `CrashOnOutOfMemoryError` chuyển một số tình huống thành VM fatal error và có thể sinh crash diagnostics.

**Không bật cờ crash hoặc command tùy ý trong production chỉ vì muốn tránh OOMKilled**, khi chưa xác định nhu cầu, quyền thực thi, rủi ro bảo mật và tác động tới thời gian phục hồi.

## 9. Chương trình chạy được 4 — Đọc bằng chứng thay vì suy luận từ exit code

Một utility nhỏ có thể biểu diễn cách phân loại **dựa trên nhiều bằng chứng**, không tự coi exit 137 là OOMKill.

Tạo **`OomEvidenceDemo.java`**:

~~~java
public class OomEvidenceDemo {
    static String diagnose(String reason, int exitCode,
                           boolean javaOomeSeen) {
        if ("OOMKilled".equals(reason)) {
            return "container-reported-oomkill";
        }
        if (javaOomeSeen) {
            return "java-oome-observed";
        }
        if (exitCode == 137) {
            return "sigkill-like-not-proof-of-oom";
        }
        return "insufficient-evidence";
    }

    public static void main(String[] args) {
        System.out.println("k8s-oom=" +
                diagnose("OOMKilled", 137, false));
        System.out.println("only-137=" +
                diagnose("Error", 137, false));
        System.out.println("java-stacktrace=" +
                diagnose("Error", 1, true));
        System.out.println("only-exit-one=" +
                diagnose("", 1, false));
    }
}
~~~

Lệnh:

~~~bash
javac --release 10 OomEvidenceDemo.java
java OomEvidenceDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
k8s-oom=container-reported-oomkill
only-137=sigkill-like-not-proof-of-oom
java-stacktrace=java-oome-observed
only-exit-one=insufficient-evidence
~~~

Hàm `diagnose` chỉ là **mô hình giải thích** dùng các bằng chứng được truyền vào, không tự truy cập Kubernetes và **không đủ làm thuật toán incident response hoàn chỉnh**.

Đặc biệt:

- `reason="OOMKilled"` là tín hiệu orchestrator báo container bị OOM kill; cần kiểm tra container đúng tên, đúng lần restart và thời gian.
- `exitCode==137` mà không có reason/host event chỉ nói đây là **mã thường gắn với SIGKILL**, không đủ xác nhận bộ nhớ là nguyên nhân.
- `javaOomeSeen=true` xác nhận đã **quan sát một Java OOME trong log**; nó không loại trừ có kill bên ngoài về sau.
- `exitCode==1` đơn độc có thể là uncaught exception, validation failure hoặc rất nhiều lỗi khác, không riêng OOME.

### Không gộp sự kiện theo thứ tự sai

Một tiến trình có thể ghi:

~~~text
12:00:01 java.lang.OutOfMemoryError: Java heap space
12:00:02 app handler ghi log hoặc container vẫn chạy
12:00:05 container memory usage tiếp tục tăng
12:00:06 Kubernetes báo OOMKilled, exit 137
~~~

Đây là **timeline giả định**, không phải log của test. Trường hợp này **cả hai sự kiện có thể đã xảy ra**, và chỉ đọc dòng cuối hoặc dòng đầu sẽ dẫn tới kết luận thiếu.

## 10. Chương trình chạy được 5 — Budget non-heap không phải “lấy Xmx bằng limit”

Tệp **`MemoryBudgetDemo.java`**:

~~~java
public class MemoryBudgetDemo {
    static long mib(long n) {
        return n * 1024 * 1024;
    }

    static long headroomMiB(long containerMiB, long xmxMiB) {
        if (containerMiB <= 0 || xmxMiB <= 0
                || xmxMiB > containerMiB) {
            throw new IllegalArgumentException();
        }
        return containerMiB - xmxMiB;
    }

    public static void main(String[] args) {
        System.out.println("container-mib=512");
        System.out.println("xmx-mib=384");
        System.out.println("nonheap-budget-mib=" +
                headroomMiB(512, 384));
        System.out.println("buffer-risk-if-no-headroom=" +
                (headroomMiB(512, 500) < 64));
        System.out.println("mib-512-bytes=" + mib(512));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 10 MemoryBudgetDemo.java
java MemoryBudgetDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
container-mib=512
xmx-mib=384
nonheap-budget-mib=128
buffer-risk-if-no-headroom=true
mib-512-bytes=536870912
~~~

Đây là **phép tính số học giả định**, không phải số memory được kernel đo. Nó cho thấy một `-Xmx500m` trong container `512MiB` chỉ để lại **12 MiB** trên giấy cho mọi thành phần khác, một cấu hình rất dễ rủi ro. Không tự kết luận “`-Xmx384m` luôn an toàn” chỉ vì còn 128 MiB; Java memory overhead phải được đo.

Lưu ý **MiB** (`1 MiB = 1.048.576 bytes`) khác với **MB** theo thập phân. Kubernetes resource syntax thường dùng `Mi`, `Gi`; hãy phân biệt unit khi tính budget.

## 11. Chương trình chạy được 6 — `SIGKILL` không chạy Java `finally`

Bộ thử nghiệm này cho thấy **process bị kết thúc từ bên ngoài JVM** khác Java `OutOfMemoryError`, nhưng **không tạo kernel/cgroup memory pressure** và **không mô phỏng được nguyên nhân OOMKill**.

Tạo file **`SigkillWitnessDemo.java`**:

~~~java
public class SigkillWitnessDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("started=true");
        System.out.flush();

        try {
            Thread.sleep(30000);
        } finally {
            System.out.println("finally-ran=true");
        }
    }
}
~~~

Biên dịch:

~~~bash
javac --release 10 SigkillWitnessDemo.java
~~~

Chỉ trong **terminal Linux có GNU coreutils `timeout`**, chạy trên **tiến trình thử nghiệm riêng**:

~~~bash
timeout -s KILL 1s java SigkillWitnessDemo
echo $?
~~~

**Thử nghiệm trên Linux với OpenJDK 21:** process in `started=true`, sau đó nhận `SIGKILL`; không thấy `finally-ran=true`. Shell báo **exit code 137** theo quy ước `128 + SIGKILL(9)`. Shell có thể đồng thời in thông báo `Killed`, cách trình bày tùy shell.

**Cảnh báo phạm vi:**

- Lệnh này **cố ý kill một process test** sau một giây, không chạy với PID của service thực.
- Nó **không gây thiếu bộ nhớ**, không tăng `memory.events: oom_kill` và **không chứng minh pod bị OOMKilled**.
- Nó chỉ minh họa rằng **SIGKILL** khiến JVM không xử lý `finally` hoặc shutdown logic thông thường.
- `timeout -s KILL` là utility bên ngoài Java, không phải API Java 10 và không có sẵn theo cùng cú pháp trên Windows.
- Không chạy thử nghiệm kernel OOM bằng cách cố cấp phát memory đến giới hạn của host/container dùng chung; điều đó có thể làm gián đoạn workload khác.

**Bài học:** `exit 137` phù hợp với một tiến trình bị `SIGKILL`, nhưng nguyên nhân có thể là kernel OOM, `kill -9`, công cụ timeout hoặc một controller khác. Để xác định **OOM**, cần chứng cứ độc lập.

## 12. Thu thập bằng chứng trong Kubernetes

Khi một pod restart không rõ nguyên nhân, hãy điều tra **container cụ thể** và **lần kết thúc cụ thể**.

### Bước 1 — Đọc trạng thái của pod/container

~~~bash
kubectl describe pod my-pod -n my-namespace
~~~

Tìm phần **Containers**, `Last State`, `Reason`, `Exit Code`, `Restart Count` và events.

Ví dụ minh họa:

~~~text
Last State:
  Terminated:
    Reason: OOMKilled
    Exit Code: 137
Restart Count: 3
~~~

Đây là **ví dụ cấu trúc trạng thái**, không phải output của một cluster đã được truy cập. Nếu có `Reason: OOMKilled`, orchestrator báo một container đã bị OOM-killed; **đừng chỉ lấy `RestartCount` rồi mặc định tất cả ba lần restart đều cùng nguyên nhân**.

Có thể xuất dữ liệu dưới dạng JSONPath (khi pod và containerStatuses được giữ trong API):

~~~bash
kubectl get pod my-pod -n my-namespace -o jsonpath='{range .status.containerStatuses[*]}{.name}{" reason="}{.lastState.terminated.reason}{" exit="}{.lastState.terminated.exitCode}{" restarts="}{.restartCount}{"\n"}{end}'
~~~

**Lưu ý:** `lastState.terminated` có thể vắng nếu container chưa từng restart; giá trị phụ thuộc pod đang được Kubernetes lưu. Nếu pod đã bị xóa và tạo mới với tên khác, cần tìm event/log lịch sử từ công cụ giám sát.

### Bước 2 — Đọc log của container **trước khi restart**

~~~bash
kubectl logs my-pod -n my-namespace -c my-container --previous
~~~

Nếu thấy Java stack trace `OutOfMemoryError`, đó là bằng chứng Java Error từng được ghi; nếu log đột ngột dừng và container `OOMKilled`, phù hợp với kill từ bên ngoài. Nhưng:

- **Không có `OutOfMemoryError` trong log không chứng minh heap chưa bao giờ bị cạn**. Log có thể chưa flush trước `SIGKILL`.
- **Không có heap dump không chứng minh không có memory pressure**. Kernel SIGKILL không phải Java heap OOME hook.
- `--previous` thường đọc log của **container instance trước** khi restart; với nhiều lần restart, không đảm bảo lấy được đầy đủ toàn bộ lịch sử.
- Phải đọc đúng tên container; một pod nhiều container có thể chỉ có **sidecar** bị kill, không phải JVM chính.

### Bước 3 — Quan sát memory limit/requests thực tế

~~~bash
kubectl describe pod my-pod -n my-namespace
kubectl top pod my-pod -n my-namespace --containers
~~~

Kubernetes **memory request** phục vụ resource scheduling; **memory limit** là hard limit được kernel cgroup thực thi trên Linux. `kubectl top` cho số liệu theo nhịp lấy mẫu; **không thay thế memory peak** khi spike ngắn dẫn tới kill.

**Một pod `OOMKilled` có thể có biểu đồ memory trung bình trông thấp** nếu spike xảy ra giữa hai điểm metric. Dùng `memory.peak`, telemetry độ phân giải cao và container runtime/kernel events khi có thể.

### Bước 4 — Phân biệt `Evicted`

Trong `kubectl describe pod`, một pod `Evicted` do node memory pressure được **kubelet quyết định loại bỏ**; khác với một container `Last State: OOMKilled` khi kernel giết process. Có thể cùng gây gián đoạn dịch vụ, nhưng điều tra nguyên nhân, QoS và resource policy khác nhau.

**Không viết runbook “cứ exit 137 thì tăng `-Xmx`”.** Nếu vấn đề là kernel memory limit, tăng heap có thể khiến tình huống **tệ hơn**.

## 13. Thu thập bằng chứng ở cgroups v2 trên Linux

Trong **Linux container có mount cgroups v2** tại đường dẫn điển hình `/sys/fs/cgroup`, có thể đọc:

~~~bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.events.local
cat /sys/fs/cgroup/memory.stat
~~~

**Không phải mọi file đều có** trên mọi kernel/cgroup mount; đặc biệt `memory.peak` phụ thuộc phiên bản kernel. Đường mount có thể khác trong container runtime; xác nhận qua mount/cgroup namespace hiện tại trước khi kết luận file không tồn tại có nghĩa không có limit.

Ví dụ `memory.max` có thể là:

~~~text
536870912
~~~

Nghĩa là giới hạn khoảng **512 MiB**. Nếu file chứa:

~~~text
max
~~~

thì **không áp memory.max hard limit ở cấp cgroup đang đọc**; vẫn có thể có giới hạn tại cgroup cha hoặc thiếu memory ở host. Đừng mặc định “max” đồng nghĩa không có mọi ràng buộc.

Ví dụ `memory.events` có thể chứa:

~~~text
low 0
high 10
max 4
oom 2
oom_kill 1
oom_group_kill 0
~~~

**Đây là dữ liệu giả định.** `oom_kill 1` là bằng chứng đã có một OOM kill được kernel ghi nhận trong phạm vi cgroup (theo quy tắc hierarchical/local), nhưng **không tự định danh process nào** hoặc chính xác lúc nào nếu không có metric theo thời gian. Nên so bộ đếm **trước/sau incident** hoặc dùng telemetry giám sát.

### Cgroups v1

Hệ thống cũ có thể dùng cgroups v1 với các file kiểu:

~~~text
memory.limit_in_bytes
memory.usage_in_bytes
memory.failcnt
memory.oom_control
~~~

Đường đầy đủ và mount layout tùy môi trường. `memory.failcnt` đếm sự kiện giới hạn, **không là số process OOMKilled**. Nếu đang dùng cgroups v1, đừng yêu cầu `memory.events` như v2 rồi kết luận container không có OOM telemetry.

**Mốc lịch sử còn quan trọng:** HotSpot Java 10 cải thiện container resource awareness trên Linux; hỗ trợ cgroups v2 xuất hiện ở các JDK sau và đã được backport vào một số dòng update. Với ứng dụng hiện nay, kiểm tra **JDK build và cgroup mode**, không mặc định Java 10 đời đầu đọc cgroups v2 đúng.

## 14. Các công cụ JVM còn hữu ích hiện nay

| Công cụ / flag | Dùng khi nào? | Không thể kết luận |
| --- | --- | --- |
| `-Xmx<size>` | Đặt maximum **Java heap** | Không đặt total process/container memory |
| `-XX:MaxRAMPercentage=<percent>` | Cấu hình heap ergonomic theo memory JVM phát hiện | Không giới hạn toàn bộ native memory |
| `-XX:+UseContainerSupport` | Container awareness trong **HotSpot Linux** | Không phải flag chạy giống nhau trên mọi OS |
| `-XshowSettings:system` | Xem giới hạn host/container trên Linux JVM có hỗ trợ | Không phải bằng chứng heap OOME hay kernel kill riêng |
| `-Xlog:os+container=info` / `trace` | Debug nhận diện cgroups/limits | Trace có overhead và output tùy JDK |
| `-XX:+HeapDumpOnOutOfMemoryError` | Java **heap** OOME đủ điều kiện | Không tự có heap dump khi kernel SIGKILL |
| `-XX:HeapDumpPath=<path>` | Kiểm soát vị trí file dump | Không bảo đảm dump thành công nếu không có chỗ ghi |
| `-XX:+ExitOnOutOfMemoryError` | Chính sách JVM tự thoát do OOME | Không giống OOMKilled/SIGKILL |
| `-XX:NativeMemoryTracking=summary` | Theo dõi nhóm native allocations do HotSpot NMT quản lý | Không bao phủ mọi native memory của mọi thư viện |
| `jcmd <pid> VM.native_memory summary` | Xem NMT từ process đang sống, khi bật NMT | Không thể attach vào process đã SIGKILL |
| `-Xlog:gc*` | Phân tích GC/heap pressure khi có log | Không giải thích mọi native/cgroup kill |
| `jcmd <pid> GC.heap_dump <file>` | Lấy heap dump chủ động nếu VM còn sống và có quyền | Có overhead và yêu cầu dung lượng; không áp dụng sau kill |
| Container `memory.current/peak/events` | Quan sát memory cgroup và OOM activity | Không thay thế Java heap analysis |
| Kubernetes `lastState.terminated.reason` | Xác định lý do runtime báo container kết thúc | Không tự nói được object/library gây tăng memory |

### Một cách đặt heap phù hợp

Ví dụ resource limit giả định `512Mi` và policy heap budget `60%`:

~~~bash
java -XX:MaxRAMPercentage=60 -jar app.jar
~~~

JVM HotSpot trên Linux khi nhận diện giới hạn container sẽ có xu hướng tính heap max theo tỷ lệ đó, subject to JVM ergonomics/giới hạn nhỏ. **Không giả định heap max chính xác bằng 307,2 MiB ở mọi JDK**; kiểm tra thực tế qua flags/runtime. Hoặc đặt explicit:

~~~bash
java -Xmx384m -jar app.jar
~~~

Trong cả hai trường hợp, **phần ngoài heap vẫn phải có budget** và có thể rất khác theo service.

### Native Memory Tracking

Có thể bật NMT (cần cân nhắc overhead):

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Khi process còn sống, một operator có quyền attach có thể chạy:

~~~bash
jcmd 12345 VM.native_memory summary
~~~

Đây là ví dụ với PID **12345** cần thay bằng PID thực. NMT giúp tìm các nhóm memory mà HotSpot theo dõi; **không phải bảng tổng chính xác toàn bộ bộ nhớ kernel tính vào cgroup**, và không thu được từ JVM đã bị SIGKILL. Khi chỉ thấy heap nhỏ mà container memory cao, NMT cùng memory.stat là hai nguồn **bổ sung**, không thay thế nhau.

## 15. Vì sao heap dump có thể thiếu khi Kubernetes báo `OOMKilled`?

Quy trình:

~~~text
JVM được chạy với -XX:+HeapDumpOnOutOfMemoryError
                  |
             Có Java heap OOME?
                /       \
              Có         Không
               |           |
        HotSpot có thể      |
        tạo .hprof theo     |
        điều kiện hỗ trợ    |
               |           |
               +-----------+
                  |
        Kernel cgroup OOM killer gửi SIGKILL?
                    |
                  Có
                    |
           Process dừng ngay lập tức
           Không chạy Java heap-dump hook
           chỉ vì SIGKILL xảy ra
~~~

Điều cần nhấn mạnh: **thiếu heap dump sau `OOMKilled` là điều thường có thể xảy ra**, bởi vì sự kiện fatal đến từ kernel chứ không phải OOME của JVM. Nếu trước `SIGKILL` JVM đã có **Java heap OOME**, dump **có thể** đã được tạo; vì vậy đừng nói “OOMKilled thì không bao giờ có heap dump”. Hai cơ chế có thể xuất hiện cùng một chuỗi sự kiện.

### Thư mục dump có thể là một phần vấn đề

Heap dump có thể rất lớn và chứa dữ liệu nhạy cảm. Trong container:

- Phải có **quyền ghi** tại `HeapDumpPath`.
- Nếu đường dump là file system/tmpfs tính vào memory cgroup, việc tạo dump có thể **làm tăng áp lực memory**.
- Nếu dump vào ephemeral disk, hãy kiểm tra **ephemeral storage quota**, không cho phép dump làm đầy node.
- Đặt giới hạn thời gian/lưu trữ và kiểm soát truy cập. `.hprof` có thể chứa strings, secrets hoặc dữ liệu khách hàng từ heap.
- Nếu cần phân tích sau khi process đã chết, hãy **xuất heap dump khỏi container** hoặc dùng cơ chế lưu trữ có kiểm soát trước khi pod bị thay thế.

Không bật heap dumps không giới hạn trong production mà không có kế hoạch bảo mật và dung lượng.

## 16. Decision tree khi một Java pod tự restart

~~~text
Pod/container bị restart hoặc process biến mất
                     |
                     v
      Xem lastState.terminated.reason
                     |
       +-------------+--------------+
       |                            |
    OOMKilled                     Khác / không rõ
       |                            |
       v                            v
  Điều tra kernel:             Đọc exit code,
  cgroup memory.max,           events và log.
  memory.events oom_kill,      Có Java OOME?
  node logs, native/RSS             |
       |                        +---+---+
       |                        |       |
       |                       Có      Không
       |                        |       |
       v                        v       v
  Phân tích tổng          Heap/direct/  Có SIGKILL
  memory của cgroup.      meta/thread    hay eviction/
  Không tăng Xmx          diagnostics.   shutdown?
  theo phản xạ.                         Cần thêm evidence.
~~~

**Nếu `reason=OOMKilled`:** kiểm tra container memory limit, memory usage/peak, memory events, các khoản JVM native, direct buffer và page cache. Java heap OOME logs có thể vắng hoàn toàn.

**Nếu log có `OutOfMemoryError: Java heap space` mà không có `OOMKilled`:** kiểm tra `-Xmx`, heap dump, GC logs, retention/leak, batch size. Tăng limit container **không tự tăng `-Xmx` đã đặt tường minh**; đồng thời cần xem JVM container-aware defaults.

**Nếu exit 137 mà reason trống/khác:** kiểm tra có `kill -9`, timeout operator, lệnh orchestration, host OOM, cgroup event và node logs. Không ghi “OOMKilled” chỉ dựa vào 137.

**Nếu `reason=Evicted`:** điều tra pod/node eviction pressure, QoS/requests và kubelet events; đây không phải cùng một trạng thái với `OOMKilled`.

**Nếu nhiều dấu hiệu cùng xuất hiện:** tạo timeline chính xác, xem cái nào xảy ra trước. Java OOME **có thể** đã xảy ra trước kernel kill; không buộc chọn một trong hai khi có bằng chứng cho cả hai.

## 17. Các kiểu sửa sai phổ biến

| Tình huống | Cách xử lý có cơ sở | Lỗi nên tránh |
| --- | --- | --- |
| Java heap OOME, container vẫn còn headroom | Phân tích heap dump/GC, retention, sizing, batch/queue | Tăng container limit mà quên `-Xmx` |
| Direct buffer OOME | Phân tích `MaxDirectMemorySize`, buffer pool, lifecycle, off-heap | Tăng `-Xmx` như phản xạ |
| Metaspace OOME | Phân tích class loader count, class metadata, leak; flags phù hợp | Chỉ phân tích Java object heap |
| Native thread OOME | Thread counts, stack size, pids/ulimit, memory native | Coi mọi thread failure là Java heap leak |
| Kubernetes `OOMKilled`, heap không đầy | Điều tra tổng memory cgroup, native/direct/threads, cache | Khẳng định JVM báo sai vì heap chưa chạm max |
| `OOMKilled`, `-Xmx` gần bằng limit | Giảm heap ratio hoặc tăng limit có căn cứ; đo native overhead | Đặt `-Xmx` bằng 100% limit |
| Exit 137 không có `OOMKilled` | Tìm nguồn SIGKILL, node/kube events | Gọi đó là OOM kill chắc chắn |
| Log có OOME nhưng process sau đó exit 137 | Đọc timeline/log và kernel events | Giả định chỉ có một nguyên nhân |
| Bật `HeapDumpOnOutOfMemoryError` nhưng không có dump | Xác định OOME đúng phạm vi hay SIGKILL, quyền/path/disk | Khẳng định không có memory pressure |
| Heapdump/GC logs bình thường trước kill | Xem direct/native, page cache, cgroup accounting và peak | Kết luận “không có vấn đề memory” |
| CPU/memory autoscaling liên tục | Theo dõi resource limits và sizing, tạo baseline đáng tin cậy | Dùng metrics sampling thưa như bằng chứng duy nhất |
| Pod `Evicted` | Điều tra kubelet memory pressure và QoS | Gắn nhãn `OOMKilled` sai |
| Container nhiều process | Xác định process nào bị kernel kill, PID1/supervisor behavior | Cho rằng mọi OOM event đều do JVM |
| OOME bị catch và log rồi app tiếp tục | Xem xét fail fast/restart policy, tính nhất quán trạng thái | Coi catch OOME là recovery đáng tin cậy |

### Nếu cần tăng `-Xmx`, hãy kiểm tra hai giới hạn

Giả sử container memory limit 512MiB, `-Xmx384m`. Tăng `-Xmx` lên 480MiB có thể giảm một kiểu Java heap OOME nhưng để lại quá ít khoảng trống cho non-heap và làm tăng nguy cơ **cgroup OOMKilled**. Ngược lại, giảm `-Xmx` quá thấp có thể tăng GC pressure và Java heap OOME dù container chưa đầy.

**Phương pháp tốt:** xác định nguyên nhân, đo peak heap/nonheap/native/container, thử nhiều cấu hình trên workload tương đương, rồi chọn mức heap và hard limit có margin rõ. Không có tỷ lệ `-Xmx / containerLimit` nào đúng cho mọi Java service.

## 18. Kiểm tra logging và chính sách khởi động JVM

Một cấu hình **minh họa** cho dịch vụ muốn ghi GC logs và heap dumps khi xảy ra Java heap OOME:

~~~bash
java -Xmx384m -Xlog:gc*:file=gc.log:time,level,tags -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=./dumps -jar app.jar
~~~

**Không sao chép nguyên vào production nếu chưa kiểm tra path, rotate/retention, dung lượng và bảo mật.** Logging GC có thể giúp xác định heap bị đầy/GC pressure, còn container metrics xác định tổng memory mà kernel nhìn thấy. Cả hai cần thiết khi phân biệt hai nguồn lỗi.

Khi cần dump tự động, hãy nhớ:

- `-XX:+HeapDumpOnOutOfMemoryError` **không bảo đảm dump khi `SIGKILL`**.
- Không phải mọi OOME đều do heap exhaustion; đặc biệt native thread/direct memory cần công cụ khác.
- Có thể không kịp flush log trước kill. Sử dụng log streaming/collector ổn định.
- Khi kernel kill, shutdown hook **không chạy**. Không đặt xử lý bắt buộc như commit dữ liệu trong shutdown hook rồi trông chờ OOM kill vẫn thực hiện.
- Với `-XX:+ExitOnOutOfMemoryError`, JVM tự thoát vì OOME và log/exit code có thể khác thông thường; cần tách khỏi container OOMKilled khi phân tích.

### Những thông số liên quan cần đọc

~~~bash
java -XX:+PrintFlagsFinal -version
java -XshowSettings:vm -version
~~~

Các lệnh này có thể in thông tin JVM nhưng **đừng mặc định cả danh sách flags ổn định giữa các JDK**. Khi nghi JVM nhận sai container memory limit trên Linux, dùng `java -XshowSettings:system -version` và `-Xlog:os+container=info` nếu runtime hỗ trợ. Cờ container detection trong HotSpot Linux không nhất thiết hợp lệ trên HotSpot Windows.

## 19. Checklist QA cho sự cố memory trong container

1. **Xác định đúng container** trong pod, không nhầm sidecar và Java process chính.
2. Ghi **timestamp và restart instance** tương ứng, tránh gộp events khác thời điểm.
3. Lấy `lastState.terminated.reason` và `exitCode`; nếu `OOMKilled`, ghi rõ đó là kết luận orchestrator.
4. **Không quy exit 137 mặc định là OOMKilled**; kiểm tra nguồn SIGKILL.
5. Lấy log `--previous` nếu có, không kết luận quá mạnh khi log vắng.
6. Tìm `java.lang.OutOfMemoryError`, loại message và stack trace nếu xuất hiện.
7. Kiểm tra JVM `-Xmx`, `MaxRAMPercentage` và `Runtime.maxMemory()`.
8. Kiểm tra `MaxDirectMemorySize`, metaspace, code cache, threads và native memory.
9. Kiểm tra `memory.max`, `memory.current`, `memory.peak` và `memory.events` của đúng cgroup.
10. Phân biệt counter `oom`, `oom_kill` và `oom_group_kill`.
11. Xem `memory.stat` để hiểu anon/file/kernel; page cache có thể được tính vào cgroup.
12. Có hard limit hay chỉ memory request? Mức request **không phải hard cap**.
13. Có node eviction hoặc pressure khác không? Đừng gộp `Evicted` với `OOMKilled`.
14. Kiểm tra Java heap dump được tạo hay không và **có thuộc đúng lần OOME** không.
15. Nếu không có dump, không loại trừ `SIGKILL` hoặc native memory pressure.
16. Xem GC logs và NMT đã bật nếu cần; NMT không bao phủ tất cả native allocations.
17. Tính tổng memory budget với **headroom cho non-heap**, không đặt `-Xmx` bằng container limit.
18. Kiểm tra peak memory và p95/p99, tránh chỉ tin metrics sampling thưa.
19. Nếu thay `-Xmx` hoặc container limit, chạy lại workload có đối chứng, không chỉ “hết lỗi trong một lần”.
20. Lưu thông tin JDK build, Linux kernel/cgroup version và container runtime để tái lập.
21. Không cố ý gây kernel OOM trên node production để thử runbook; dùng environment cô lập có safety limits.
22. Khi đã có đủ bằng chứng, ghi rõ “Java OOME”, “kernel/cgroup OOM kill”, “external SIGKILL khác” hoặc “chưa đủ bằng chứng” thay vì dùng một nhãn OOM mơ hồ.

## 20. Câu hỏi tự kiểm tra

1. `OutOfMemoryError` là `Throwable` của Java hay kernel signal?
2. Một `OutOfMemoryError: Java heap space` có thể xảy ra khi container chưa chạm memory limit không?
3. Nếu process nhận `SIGKILL`, `catch (OutOfMemoryError)` và `finally` có xử lý được không?
4. `exitCode=137` đã đủ chứng minh Kubernetes `OOMKilled` chưa?
5. `reason=OOMKilled` có khác `reason=Evicted` không?
6. `-Xmx` có giới hạn tổng native memory của process không?
7. Direct ByteBuffer có thể gây `OutOfMemoryError` dù Java heap còn trống không?
8. `Runtime.maxMemory()` là Java heap max hay memory.max của cgroup?
9. Tại sao `-XX:+HeapDumpOnOutOfMemoryError` có thể không tạo file khi process bị kernel kill?
10. Có phải mọi `OutOfMemoryError` đều tạo heap dump nếu bật flag không?
11. `-XX:+ExitOnOutOfMemoryError` có nghĩa JVM bị Linux SIGKILL không?
12. `memory.events oom_kill` đo những gì, có đồng nghĩa `oom` không?
13. Trong cgroups v2, `memory.max=max` có nghĩa không có bất kỳ giới hạn memory nào không?
14. Vì sao container `512Mi` và `-Xmx500m` có rủi ro?
15. Nếu heap dump nhỏ và ổn nhưng pod `OOMKilled`, cần tìm thêm ở đâu?
16. Nếu JVM báo heap OOME trong log rồi container có `exit 137`, có thể cả hai sự kiện cùng xảy ra không?
17. `kubectl top pod` có đủ để loại trừ một memory spike cực ngắn không?
18. Vì sao bắt OOME trong một chương trình thử nhỏ không đồng nghĩa production phục hồi an toàn?
19. Cgroups v1 và v2 có tên file memory event giống nhau không?
20. Lệnh `timeout -s KILL` chứng minh điều gì và **không** chứng minh điều gì?

**Đáp án:**

1. `OutOfMemoryError` là Java `Error`, không phải signal.
2. Có, nếu giới hạn Java heap hoặc tài nguyên JVM cụ thể nhỏ hơn memory còn lại của container.
3. Không; `SIGKILL` kết thúc process bên ngoài Java flow, không chạy Java cleanup hooks.
4. Chưa. 137 thường là SIGKILL, có nhiều nguyên nhân khác OOM.
5. Có; `OOMKilled` thường là kernel OOM kill, `Evicted` là kubelet eviction trong tình huống resource pressure.
6. Không. `-Xmx` chỉ giới hạn Java heap.
7. Có. Direct memory limit/native allocation khác Java heap.
8. Giới hạn Java heap, không phải cgroup `memory.max`.
9. Kernel kill không phát sinh Java heap OOME để trigger JVM hook; JVM mất quyền thực thi.
10. Không. Oracle giới hạn cơ chế đối với Java heap exhaustion thuộc phạm vi hỗ trợ.
11. Không. Đây là chính sách JVM tự thoát vì OOME, khác kernel SIGKILL.
12. `oom_kill` đếm process bị OOM killer kill, `oom` là những sự kiện áp lực/khả năng cấp phát lỗi; không đồng nghĩa.
13. Không. Cgroup cha và node-wide memory pressure vẫn có thể áp giới hạn.
14. Chỉ còn 12MiB lý thuyết cho mọi non-heap/native/file cache, dễ bị cgroup OOM kill.
15. Native/direct/metaspace/thread memory, file cache, cgroup stats, kernel logs và resource limits.
16. Có. Cần timeline, không ép chọn một.
17. Không; metrics sampling có thể bỏ qua peak ngắn.
18. Tài nguyên có thể còn rất ít và trạng thái service có thể không nhất quán; nên dùng chính sách fail/restart và tìm root cause.
19. Không. File giao diện khác nhau; phải xác định cgroups version đang sử dụng.
20. Chứng minh **external SIGKILL** không chạy `finally` và thường tạo exit 137; không chứng minh **memory limit bị vượt** hoặc kernel OOM killer được kích hoạt.

## 21. Nguồn chính thức còn áp dụng

- **Oracle Java SE 25 `OutOfMemoryError` — hợp đồng class và quan hệ `VirtualMachineError`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/OutOfMemoryError.html
- **Oracle Java SE 26 `OutOfMemoryError` — xác nhận API hiện hành:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/OutOfMemoryError.html
- **Oracle Java SE 25 `Runtime.maxMemory()/totalMemory()/freeMemory()`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html
- **Oracle JDK 25 `java` command — `-Xmx`, `MaxRAMPercentage`, `HeapDumpOnOutOfMemoryError`, `HeapDumpPath`, `ExitOnOutOfMemoryError`, `NativeMemoryTracking`:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **Oracle Java SE 25 Troubleshooting Guide — OutOfMemoryError, native memory, heap dumps:** https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshooting-guide.pdf
- **Linux kernel documentation — Control Group v2: `memory.max`, `memory.events`, `oom_kill`, `memory.stat`:** https://docs.kernel.org/admin-guide/cgroup-v2.html
- **Kubernetes documentation — Resource Management for Pods and Containers: requests, limits và reactive OOM killing:** https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
- **Kubernetes documentation — Debug Running Pods:** https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/
- **Kubernetes documentation — Pod Quality of Service Classes và OOM eviction:** https://kubernetes.io/docs/concepts/workloads/pods/pod-qos/
- **OpenJDK — Container resource detection, Java 10 cải tiến Linux container support:** https://bugs.openjdk.org/browse/JDK-8146115
- **OpenJDK — Native Memory Tracking (NMT) guide:** https://docs.oracle.com/en/java/javase/25/vm/native-memory-tracking.html

**Ghi nhớ:** **Java `OutOfMemoryError`** là một sự kiện cấp phát tài nguyên ở **JVM/Java**, có thể xuất hiện Java stack trace và (với heap OOME phù hợp) heap dump. **Kernel/cgroup OOM kill** là hành động **`SIGKILL` từ bên ngoài process**, không chạy Java catch/finally/shutdown hooks hoặc tự sinh heap dump. Trong Kubernetes, **`OOMKilled` là bằng chứng mạnh hơn exit 137**; riêng 137 không đủ xác định nguyên nhân. **`-Xmx` chỉ giới hạn Java heap, không giới hạn toàn bộ container memory**. Chẩn đoán đúng cần đối chiếu **log Java, container reason/exit code, cgroup memory events/peak, JVM heap/non-heap và timeline**; sau đó điều chỉnh memory budget, không tăng `-Xmx` theo phản xạ.