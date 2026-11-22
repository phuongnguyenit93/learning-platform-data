# Phân biệt số liệu hệ điều hành với Java heap — đọc đúng các chỉ số bộ nhớ trên JVM

## 1. Vì sao phải tách số liệu hệ điều hành khỏi Java heap?

Khi giám sát một ứng dụng Java, ta thường nhìn thấy những câu như:

- “Máy có **32 GiB RAM**, tại sao JVM chỉ có **2 GiB heap**?”
- “`Runtime.freeMemory()` còn nhiều nhưng container bị **OOMKilled**.”
- “Bộ nhớ tiến trình tăng liên tục, trong khi `MemoryMXBean.getHeapMemoryUsage().getUsed()` gần như không đổi.”
- “Đã đặt `-Xmx512m`, tại sao process Java đôi lúc chiếm hơn 512 MiB?”
- “`getFreeMemorySize()` còn rất nhiều; có nghĩa Java có thể cấp phát hết số đó không?”

Những câu này **không thể giải thích bằng cách so sánh các con số cùng đơn vị byte như thể chúng đo cùng một đối tượng**. Có ít nhất bốn phạm vi riêng:

1. **Môi trường hệ điều hành (*operating environment*)**: lượng bộ nhớ tổng/còn trống mà JVM nhìn thấy từ OS, môi trường ảo hóa hoặc container.
2. **Java heap**: vùng JVM quản lý để cấp phát phần lớn Java objects và arrays; chịu tác động của `-Xms`, `-Xmx`, GC và các chính sách runtime.
3. **JVM non-heap / native**: các vùng như metaspace, code cache, thread stacks, NIO direct buffers và phần native do JVM hoặc libraries sử dụng. Không phải tất cả đều nằm trong báo cáo `MemoryMXBean.getNonHeapMemoryUsage()`.
4. **Bộ nhớ tiến trình mà OS kế toán**: resident set/RSS, commit, virtual address space và giới hạn cgroup/container là những khái niệm khác, không phải Java heap.

**Mục tiêu:** chọn đúng API cho câu hỏi cần hỏi, đọc đúng `used/committed/max`, không dùng RAM “còn trống” để suy ra heap “còn trống”, và phân biệt lỗi heap, native memory, container memory pressure bằng công cụ phù hợp.

**Phạm vi phiên bản:** `com.sun.management.OperatingSystemMXBean.getTotalMemorySize()` và `getFreeMemorySize()` có từ **Java 14** và **vẫn được dùng trong JDK hiện hành**. Các tên cũ `getTotalPhysicalMemorySize()`/`getFreePhysicalMemorySize()` đã **deprecated since Java 14**; bài ưu tiên tên mới. Mọi ví dụ chính biên dịch với **Java 17+**, không sử dụng API legacy.

## 2. Sơ đồ phạm vi bộ nhớ

```text
┌────────────────── OS / container operating environment ──────────────────┐
│ Tổng bộ nhớ OS/container thấy được   — getTotalMemorySize()               │
│ Bộ nhớ còn trống theo OS             — getFreeMemorySize()                │
│                                                                          │
│   ┌────────────────── Java PROCESS / JVM ────────────────────┐           │
│   │                                                         │           │
│   │  ┌────────── Managed Java heap ───────────────┐         │           │
│   │  │ Heap used       — MemoryMXBean heap.used     │         │           │
│   │  │ Heap committed  — heap.committed             │         │           │
│   │  │ Heap max        — heap.max / -Xmx             │         │           │
│   │  └─────────────────────────────────────────────┘         │           │
│   │                                                         │           │
│   │  JVM managed non-heap    — MemoryMXBean nonHeap          │           │
│   │  Direct/mapped NIO pools — BufferPoolMXBean              │           │
│   │  Thread stacks, JIT, GC, JNI/native libraries, etc.     │           │
│   │                                                         │           │
│   └─────────────────────────────────────────────────────────┘           │
│                                                                          │
│ Nhiều tiến trình khác, file cache, kernel memory, các giới hạn OS ...   │
└──────────────────────────────────────────────────────────────────────────┘
```

Sơ đồ chỉ minh họa **các lớp kế toán khác nhau**, không mô tả chính xác mọi cơ chế VM, RAM vật lý hay cách OS map trang nhớ. Đặc biệt, **không có một phép cộng đơn giản** `heap used + nonheap used + direct used = process RSS`, vì còn memory mapping, cấu trúc native, vùng dự trữ, chia sẻ trang nhớ và phạm vi đo khác nhau.

## 3. Bảng chọn API: muốn biết điều gì thì đọc ở đâu?

| Câu hỏi | API hiện hành | Đối tượng đo | Không nên hiểu thành |
| --- | --- | --- | --- |
| Môi trường chạy có tổng bao nhiêu bộ nhớ? | `com.sun.management.OperatingSystemMXBean.getTotalMemorySize()` | Memory tổng của operating environment | `-Xmx` hoặc dung lượng heap |
| Môi trường chạy còn bao nhiêu bộ nhớ trống? | `getFreeMemorySize()` | Free memory theo OS/environment | Dung lượng còn trống trong heap của JVM |
| Heap JVM đang dùng bao nhiêu? | `MemoryMXBean.getHeapMemoryUsage().getUsed()` | Heap used tại thời điểm quan sát | RSS của process |
| Heap JVM hiện đã committed bao nhiêu? | `getHeapMemoryUsage().getCommitted()` | Memory được đảm bảo cho quản lý heap | Chính xác bằng used hoặc bằng max |
| Heap tối đa là bao nhiêu? | `getHeapMemoryUsage().getMax()` | Max heap (hoặc `-1` nếu không xác định) | Tổng RAM OS/container |
| JVM non-heap được bean thống kê bao nhiêu? | `getNonHeapMemoryUsage()` | Memory được quản lý bởi non-heap memory pools | **Toàn bộ** native memory của process |
| Runtime hiện có bao nhiêu vùng heap chưa dùng? | `Runtime.getRuntime().freeMemory()` | Free trong tổng heap hiện có ở góc nhìn runtime | Free memory của OS |
| Tổng heap hiện có của Runtime? | `Runtime.getRuntime().totalMemory()` | Heap hiện có cho đối tượng JVM | Bộ nhớ OS tổng |
| Giới hạn heap của Runtime? | `Runtime.getRuntime().maxMemory()` | Max mà JVM cố sử dụng | RSS limit hoặc container memory quota |
| Ước lượng NIO direct buffer memory? | `BufferPoolMXBean.getMemoryUsed()` với pool `"direct"` | Memory của direct buffer pool | Mọi allocation native/direct |
| Memory process được OS ghi nhận? | Công cụ OS/container phù hợp; NMT hỗ trợ phân tích nội bộ JVM | RSS/working set/cgroup usage theo công cụ | `getHeapMemoryUsage().getUsed()` |
| Virtual memory đã commit cho process? | `OperatingSystemMXBean.getCommittedVirtualMemorySize()` | Committed virtual memory của process theo OS/JDK | **RSS** |

Các chỉ số trong bảng được trả về bằng **byte**, trừ các dữ liệu CPU và các trường có contract khác. Khi hiển thị MiB, chia cho `1024 * 1024`, không chia nhầm cho một triệu nếu đang gắn nhãn **MiB**.

## 4. Đọc memory của OS bằng `OperatingSystemMXBean`

### 4.1. Có hai interface cùng tên nhưng khác package

Trong Java chuẩn có:

```java
java.lang.management.OperatingSystemMXBean
```

Interface nền tảng này mô tả tên OS, kiến trúc, processors và system load average. Nó **không chứa** hai method `getTotalMemorySize()`/`getFreeMemorySize()`.

Trong module `jdk.management` có interface mở rộng:

```java
com.sun.management.OperatingSystemMXBean
```

Dù tên package bắt đầu bằng `com.sun`, đây là **API quản lý được tài liệu hóa của module JDK `jdk.management`**, không phải một mẹo truy cập `sun.*` nội bộ. Nó cung cấp memory/swap/process CPU metrics. Tuy vậy, để code có tính portable trên JVM không cung cấp extension này, nên kiểm tra `instanceof` trước khi cast.

### 4.2. Đọc lượng bộ nhớ OS/environment

```java
import java.lang.management.ManagementFactory;
import com.sun.management.OperatingSystemMXBean;

var basic = ManagementFactory.getOperatingSystemMXBean();

if (basic instanceof OperatingSystemMXBean os) {
    long total = os.getTotalMemorySize();
    long free = os.getFreeMemorySize();

    System.out.println("OS total bytes = " + total);
    System.out.println("OS free bytes = " + free);
} else {
    System.out.println("Extended OS memory metrics unavailable");
}
```

Đây là **trích đoạn** đặt trong một method; ví dụ đầy đủ trong mục 9 có imports/class/main. Khi dùng **named module**, cần khai báo module dependencies phù hợp như `requires java.management;` và `requires jdk.management;` (xem mục 12).

**Ý nghĩa chính xác:**

- `getTotalMemorySize()`: tổng bộ nhớ mà **môi trường vận hành JVM** cung cấp theo API. Môi trường đó có thể là **host native**, máy ảo hoặc **container-managed environment**, tùy hệ điều hành/JDK/cấu hình.
- `getFreeMemorySize()`: bộ nhớ **còn trống theo môi trường đó** tại thời điểm lấy mẫu. Nó **không** mô tả phần heap hiện chưa cấp phát.
- Các con số có thể đổi giữa hai lần đọc; **không phải snapshot nguyên tử** đồng thời với heap, GC và process metrics.

**Không khẳng định** giá trị này luôn bằng **RAM vật lý của host**. Trong container, các JDK có hỗ trợ container có thể báo bối cảnh tài nguyên khác máy chủ gốc. Đọc thêm giới hạn cgroup/metrics do orchestration công bố để biết memory quota thực tế.

### 4.3. API cũ từ Java 14 nên tránh

Từ Java 14, Oracle Javadoc đánh dấu các method lịch sử là deprecated:

| Method cũ (deprecated since 14) | Method thay thế hiện hành |
| --- | --- |
| `getTotalPhysicalMemorySize()` | `getTotalMemorySize()` |
| `getFreePhysicalMemorySize()` | `getFreeMemorySize()` |
| `getSystemCpuLoad()` | `getCpuLoad()` |

Bài nói về memory nên dùng **hai method mới**. Đừng sao chép ví dụ cũ với các method đã deprecated chỉ vì chúng vẫn biên dịch trên một vài phiên bản JDK. Việc đổi tên từ “PhysicalMemory” sang “Memory” cũng nhấn mạnh rằng môi trường OS ảo/container có thể có ý nghĩa khác với RAM trên host.

### 4.4. Một số số liệu khác thuộc OS/process

`com.sun.management.OperatingSystemMXBean` còn có:

- `getTotalSwapSpaceSize()`, `getFreeSwapSpaceSize()`: swap của operating environment.
- `getCommittedVirtualMemorySize()`: lượng virtual memory được cam kết cho process theo khái niệm API; có thể trả `-1` nếu không hỗ trợ.
- `getProcessCpuTime()`: thời gian CPU của process (nanoseconds, có thể `-1`).
- `getCpuLoad()`, `getProcessCpuLoad()`: **tải CPU**, không phải dung lượng bộ nhớ.

Đừng dùng `getCommittedVirtualMemorySize()` làm công thức thay cho **RSS** hoặc “heap committed”. **Virtual address space, virtual memory committed và resident memory** là ba khái niệm có quan hệ nhưng **không đồng nhất**.

## 5. Đọc Java heap đúng bằng `MemoryMXBean`

API chuẩn:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

MemoryUsage heap =
        ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();

long used = heap.getUsed();
long committed = heap.getCommitted();
long max = heap.getMax();
long init = heap.getInit();
```

Đây là **trích đoạn**, dùng được trên Java 17+ trong một method có imports phù hợp. `MemoryUsage` trả bốn giá trị mô tả JVM-managed heap tại thời điểm lấy mẫu.

### 5.1. `used`, `committed`, `max` và `init`

| Trường | Ý nghĩa | Cách đọc đúng |
| --- | --- | --- |
| `init` | Kích thước ban đầu JVM yêu cầu cho memory management; có thể `-1` | Không phải lượng đang dùng |
| `used` | Byte hiện đang sử dụng trong heap | Có thể chứa cả object chưa được GC dọn |
| `committed` | Byte đã committed/được đảm bảo cho memory management | `committed >= used` |
| `max` | Byte tối đa JVM được phép quản lý cho heap; có thể `-1` | Không bảo đảm JVM sẽ cấp phát được đến max nếu OS thiếu tài nguyên |

Theo contract `MemoryUsage`:

```text
0 <= used <= committed

Nếu max >= 0:
    committed <= max

Nếu init hoặc max không xác định:
    giá trị có thể là -1
```

**Ví dụ minh họa bằng số giả định:**

```text
heap.used       = 300 MiB
heap.committed  = 512 MiB
heap.max        = 1024 MiB

Phần chưa dùng bên trong heap committed ≈ 512 - 300 = 212 MiB.
Khoảng cách tới max về lý thuyết       ≈ 1024 - 300 = 724 MiB.
```

Không nên gọi `724 MiB` là “RAM hệ điều hành còn có thể cấp chắc chắn”. Giới hạn `max` là **trần heap do JVM đặt/diễn giải**, không phải bảo đảm cấp phát thực tế và không bao gồm native memory của process.

### 5.2. `used` có thể chứa garbage chưa được thu gom

`MemoryMXBean.getHeapMemoryUsage().getUsed()` đo phần bộ nhớ heap đang chiếm bởi objects, bao gồm **các objects không còn reachable nhưng chưa được GC thu gom**. Vì thế:

- Heap used tăng trước kỳ GC không chứng minh memory leak.
- Heap used giảm sau GC thường là bình thường.
- Để điều tra leak, so sánh các mẫu theo thời gian, GC history và **retained heap sau các kỳ GC phù hợp**, thay vì dựa vào một ảnh chụp.

**Không** tự gọi `System.gc()` sau mỗi lần đo để “sửa chỉ số”; `gc()` chỉ là yêu cầu gợi ý GC và có overhead, không bảo đảm dọn hết objects hay cung cấp phép đo duy nhất đúng.

### 5.3. Heap memory pools

Một JVM có thể có nhiều heap pools như các vùng của collector đang dùng. `ManagementFactory.getMemoryPoolMXBeans()` cho phép xem memory pool types, names và usage.

Tên pool như `G1 Eden Space`, `G1 Old Gen` hoặc các tên của GC khác **phụ thuộc implementation/collector/JDK**, không nên hardcode một danh sách. `getHeapMemoryUsage()` cung cấp tổng dùng/committed của heap theo bean, phù hợp với bước giám sát tổng quan.

## 6. `Runtime.totalMemory/freeMemory/maxMemory` là heap, không phải RAM OS

`java.lang.Runtime` có ba method lâu đời nhưng **vẫn được hỗ trợ**, không phải API legacy:

```java
Runtime rt = Runtime.getRuntime();

long total = rt.totalMemory();
long free = rt.freeMemory();
long max = rt.maxMemory();
```

Ý nghĩa:

- `totalMemory()`: tổng bộ nhớ **JVM đang có** cho objects hiện tại/tương lai, gần với khái niệm **heap hiện đang committed** trên các JVM phổ biến.
- `freeMemory()`: ước lượng memory còn trống **bên trong tổng bộ nhớ JVM đang có**; không phải phần RAM OS còn trống.
- `maxMemory()`: mức tối đa heap mà JVM sẽ **cố sử dụng**, thường chịu ảnh hưởng bởi `-Xmx`; không phải bộ nhớ của host/container.

Một cách ước lượng hay gặp:

```java
long currentlyUsedApprox =
        rt.totalMemory() - rt.freeMemory();
```

Kết quả đo ở **thời điểm khác** `MemoryMXBean.getHeapMemoryUsage().getUsed()` có thể không bằng tuyệt đối do sampling và collector. Không dùng equality tuyệt đối giữa các MXBean/Runtime calls làm assertion cross-JDK.

**Hai phép trừ không giống nhau:**

```text
rt.totalMemory() - rt.freeMemory()
    ≈ heap JVM đang dùng

os.getTotalMemorySize() - os.getFreeMemorySize()
    ≈ memory không còn được báo là free trong operating environment
```

Số thứ hai có thể chứa memory của **mọi process khác**, kernel và những vùng cache/accounting phụ thuộc hệ thống; **không thể quy cho heap Java đang dùng**.

### 6.1. `Runtime.freeMemory` không phải “heap còn lại tới `-Xmx`”

Nếu JVM chưa mở rộng heap đến `-Xmx`, `Runtime.freeMemory` chỉ phản ánh phần free trong **heap hiện tại**. JVM có thể còn khả năng tăng committed heap mà `freeMemory()` không biểu diễn trực tiếp.

Do đó cần nhìn đồng thời `heap.used`, `heap.committed`, `heap.max` để hiểu:

- Trạng thái hiện tại trong heap đang committed.
- Dung lượng heap có thể mở rộng về mặt cấu hình.
- Áp lực cấp phát/GC thực tế, **không** đơn giản lấy `OS free` để suy ra khả năng mở rộng.

### 6.2. `-Xms` và `-Xmx` điều chỉnh phạm vi heap

Ví dụ:

```bash
java -Xms64m -Xmx256m -cp . MemoryScopesDemo
```

`-Xms` chỉ định heap size ban đầu hoặc tối thiểu theo semantics của JVM; `-Xmx` đặt trần tối đa. Chúng **không đặt tổng kích thước của process bằng đúng con số đó**, vì non-heap và native memory vẫn hiện diện. Một collector/runtime có thể thay đổi committed heap theo nhu cầu và lựa chọn cấu hình.

Nếu `heap.max` trả `-1` (undefined), không chia `used / max`; nếu `Runtime.maxMemory()` trả `Long.MAX_VALUE` (không có giới hạn inherent theo contract), cũng không có nghĩa host có một lượng RAM vô hạn.

## 7. Non-heap, direct buffers và native memory của process

### 7.1. `MemoryMXBean.getNonHeapMemoryUsage()`

```java
MemoryUsage nonHeap =
        ManagementFactory.getMemoryMXBean().getNonHeapMemoryUsage();

System.out.println(nonHeap.getUsed());
```

Non-heap bao gồm **các memory pools do JVM quản lý** như nơi lưu class metadata và JIT compiled code theo implementation. Đây **không** phải phép đếm **tất cả byte native** mà tiến trình đã cấp phát. Các phần như stacks, allocator bookkeeping, third-party JNI libraries, mapped memory và một số vùng runtime khác có thể nằm ngoài nội dung bạn muốn cộng từ bean này.

**Không cộng máy móc** `heap.used + nonHeap.used` để tuyên bố “tổng RAM Java process”: đó chỉ là hai loại measurement ở hai phạm vi quản lý JVM.

### 7.2. `BufferPoolMXBean` cho NIO direct/mapped buffers

Java NIO có thể dùng **off-heap/direct buffers**. API hiện hành:

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
    System.out.println(pool.getName()
            + ": " + pool.getMemoryUsed());
}
```

Lấy pool tên `"direct"` có thể giúp theo dõi **ước lượng memory của direct buffer pool**; pool `"mapped"` có thể có nếu runtime cung cấp. `getMemoryUsed()` có thể trả `-1` khi không có ước lượng.

**Giới hạn:** `BufferPoolMXBean` thống kê buffer pools được JVM phơi bày, không đảm bảo bao trùm **mọi allocation ngoài heap**, đặc biệt native allocations qua JNI/thư viện C hoặc các cơ chế riêng.

### 7.3. Thread stacks, metaspace và JIT code

Một process Java có nhiều nguồn tiêu thụ bộ nhớ:

- Java heap cho objects/arrays.
- Metaspace/class metadata và code cache.
- Stack của thread và các cấu trúc quản lý thread.
- Direct/mapped buffers và native I/O.
- JVM GC/runtime structures.
- Memory do JNI/native libraries cấp phát.
- Memory mapping chia sẻ, các vùng dự trữ/commit tùy implementation.

Tổng memory mà OS báo cho process có thể lớn hơn `-Xmx` mà **không phải lỗi**. Giảm `-Xmx` có thể giải phóng một phần ngân sách tổng, nhưng không chứng minh nguyên nhân thật của native memory growth.

## 8. Không nhầm “bộ nhớ tiến trình” với “heap Java”

### 8.1. RSS / working set

**RSS (Resident Set Size)** trên hệ kiểu Unix và **working set** ở Windows là số liệu OS về trang bộ nhớ đang cư trú, với semantics phụ thuộc nền tảng/công cụ. Chúng:

- Không tương đương `MemoryMXBean.heap.used`.
- Có thể bao gồm code/shared libraries, heap committed đã resident, stacks, buffers, native allocations.
- Có thể được hệ điều hành điều chỉnh bởi paging, page cache, shared pages và memory reclaim.

`com.sun.management.OperatingSystemMXBean` **không cung cấp một method chuẩn chung gọi `getProcessRss()`**. Nếu cần RSS/working set, dùng **OS/process/container metrics** phù hợp, không đổi tên `getCommittedVirtualMemorySize()` thành “RSS”.

### 8.2. `getCommittedVirtualMemorySize()` không phải RSS

`getCommittedVirtualMemorySize()` ghi nhận memory **virtual đã được cam kết cho process** theo contract JDK/OS, có thể trả `-1` nếu không được hỗ trợ. Giá trị có thể lớn/nhỏ khác với RSS, vì **committed virtual, reserved virtual và resident physical** không phải cùng một đại lượng.

Không lấy `getCommittedVirtualMemorySize() - heap.used` làm “toàn bộ native used” — phép trừ này trộn các phạm vi bộ nhớ không tương đương.

### 8.3. CPU là trục riêng

`getProcessCpuLoad()` và `getCpuLoad()` phản ánh **tải CPU gần đây**; không nói process đã dùng bao nhiêu RAM. `getProcessCpuTime()` là **thời gian CPU tích lũy**, tính nanoseconds, không phải memory. Tránh nhập nhằng các metric khi xây dashboard.

## 9. Chương trình Java 17+ chạy được: xem OS, heap, non-heap và direct buffers

Ví dụ sử dụng:

- `MemoryMXBean`: `heap.used/committed/max` và `nonHeap.used`.
- `Runtime`: `total/free/max` của heap.
- `com.sun.management.OperatingSystemMXBean`: `os.total/free` và `process.committedVirtual` khi implementation có hỗ trợ.
- `BufferPoolMXBean`: ước lượng `"direct"` pool nếu tồn tại.
- Một vài **invariants** bất biến theo contract để kiểm tra tính hợp lệ thay vì giả định mọi máy có cùng RAM.

Tạo file **`MemoryScopesDemo.java`**:

```java
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

public class MemoryScopesDemo {
    private static String mib(long bytes) {
        return bytes < 0 ? "N/A"
                : (bytes / (1024L * 1024L)) + " MiB";
    }

    private static boolean valid(MemoryUsage usage) {
        return usage.getUsed() >= 0
                && usage.getCommitted() >= usage.getUsed()
                && (usage.getMax() < 0
                    || usage.getCommitted() <= usage.getMax());
    }

    public static void main(String[] args) {
        MemoryMXBean bean = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = bean.getHeapMemoryUsage();
        MemoryUsage nonHeap = bean.getNonHeapMemoryUsage();
        Runtime runtime = Runtime.getRuntime();

        System.out.println("heapInvariant=" + valid(heap));
        System.out.println("nonHeapInvariant=" + valid(nonHeap));
        System.out.println("runtimeFreeWithinTotal="
                + (runtime.freeMemory() >= 0
                && runtime.freeMemory() <= runtime.totalMemory()));

        System.out.println("heap.used=" + mib(heap.getUsed()));
        System.out.println("heap.committed=" + mib(heap.getCommitted()));
        System.out.println("heap.max=" + mib(heap.getMax()));
        System.out.println("nonHeap.used=" + mib(nonHeap.getUsed()));
        System.out.println("runtime.total=" + mib(runtime.totalMemory()));
        System.out.println("runtime.free=" + mib(runtime.freeMemory()));
        System.out.println("runtime.max=" + mib(runtime.maxMemory()));

        var basic = ManagementFactory.getOperatingSystemMXBean();

        if (basic instanceof OperatingSystemMXBean os) {
            System.out.println("extendedOsBean=true");
            long total = os.getTotalMemorySize();
            long free = os.getFreeMemorySize();

            System.out.println("os.total=" + mib(total));
            System.out.println("os.free=" + mib(free));
            System.out.println("osValuesNonNegative="
                    + (total >= 0 && free >= 0));
            System.out.println("process.committedVirtual="
                    + mib(os.getCommittedVirtualMemorySize()));
        } else {
            System.out.println("extendedOsBean=false");
            System.out.println("os.memory=unavailable via this bean");
        }

        BufferPoolMXBean direct =
                ManagementFactory
                .getPlatformMXBeans(BufferPoolMXBean.class)
                .stream()
                .filter(p -> p.getName().equals("direct"))
                .findFirst()
                .orElse(null);

        if (direct != null) {
            System.out.println("direct.pool.present=true");
            System.out.println("direct.pool.memory="
                    + mib(direct.getMemoryUsed()));
        } else {
            System.out.println("direct.pool.present=false");
        }

        System.out.println("heapAndOsAreDifferentScopes=true");
    }
}
```

### 9.1. Biên dịch và chạy

Dùng JDK 17+:

```bash
javac --release 17 MemoryScopesDemo.java
java -Xmx128m MemoryScopesDemo
```

Nếu project đã compile ra thư mục khác, thêm `-cp` tương ứng khi chạy. Trên JDK tiêu chuẩn, `com.sun.management.OperatingSystemMXBean` thuộc module `jdk.management`; với một **named module** cần thêm dependency trong `module-info.java` như mục 12.

### 9.2. Kết quả chạy thực tế (một mẫu, không phải số hằng)

Ví dụ đã biên dịch bằng `javac --release 17` và chạy trên **OpenJDK 24.0.2/Windows** với `-Xmx128m`:

```text
heapInvariant=true
nonHeapInvariant=true
runtimeFreeWithinTotal=true
heap.used=2 MiB
heap.committed=128 MiB
heap.max=128 MiB
nonHeap.used=1 MiB
runtime.total=128 MiB
runtime.free=124 MiB
runtime.max=128 MiB
extendedOsBean=true
os.total=130835 MiB
os.free=60201 MiB
osValuesNonNegative=true
process.committedVirtual=233 MiB
direct.pool.present=true
direct.pool.memory=0 MiB
heapAndOsAreDifferentScopes=true
```

**Đây là số đo một lần trên môi trường kiểm thử cụ thể, không phải output bắt buộc của mọi máy.** `os.total`, `os.free`, `heap.used`, `heap.committed`, `nonHeap.used`, `runtime.free`, `direct.pool.memory` và `process.committedVirtual` đều có thể khác giữa OS/JDK, cấu hình container, GC và hai lần chạy. Giá trị MiB dùng phép chia nguyên nên một lượng bytes nhỏ hơn 1 MiB có thể được hiển thị thành `0 MiB`, **không có nghĩa bộ nhớ tuyệt đối bằng 0**.

Các dòng bất biến `heapInvariant=true` và `nonHeapInvariant=true` thể hiện quan hệ được `MemoryUsage` cam kết. `runtimeFreeWithinTotal=true` được xác minh trên runtime này; với công cụ giám sát thực tế, hãy đọc từng metric một lần trong cùng sampling window để giảm biến động do các calls xảy ra nối tiếp.

### 9.3. Chạy với trần heap khác

```bash
java -Xmx256m MemoryScopesDemo
```

Trong lượt chạy đã kiểm chứng với `-Xmx256m` (cùng JDK/host):

```text
heapInvariant=true
nonHeapInvariant=true
runtimeFreeWithinTotal=true
heap.used=2 MiB
heap.committed=256 MiB
heap.max=256 MiB
nonHeap.used=1 MiB
runtime.total=256 MiB
runtime.free=252 MiB
runtime.max=256 MiB
extendedOsBean=true
os.total=130835 MiB
os.free=60176 MiB
osValuesNonNegative=true
process.committedVirtual=364 MiB
direct.pool.present=true
direct.pool.memory=0 MiB
heapAndOsAreDifferentScopes=true
```

**So sánh chính xác trong hai mẫu:** khi `-Xmx` đổi từ 128 lên 256 MiB, `heap.max` đổi tương ứng, nhưng `os.total` **vẫn là 130835 MiB**. `os.free` cũng thay đổi (60201 → 60176 MiB) do trạng thái OS tại thời điểm sampling; đó không phải “JVM đã tự động sử dụng 25 MiB heap”.

`process.committedVirtual` thay đổi từ 233 tới 364 MiB, **không phải** phép đo RSS hay chính xác một lần cấp phát Java objects. Không được suy diễn leak từ hai startup snapshots.

### 9.4. Test với `-Xms` nhỏ hơn `-Xmx`

Để quan sát trường hợp heap **đang committed ít hơn max**, thử:

```bash
java -Xms32m -Xmx256m MemoryScopesDemo
```

Giá trị `heap.committed` có thể thấp hơn `heap.max` tùy JDK/GC. Không giả định sẽ đúng `32 MiB` tuyệt đối trên mọi collector, vì runtime có quyền thực thi các chính sách quản lý heap theo contract. Bài không đưa stdout cố định cho lần chạy này.

### 9.5. Vì sao dùng `instanceof` cho OS extension?

`ManagementFactory.getOperatingSystemMXBean()` có kiểu trả về cơ bản là `java.lang.management.OperatingSystemMXBean`. Trên JDK thông dụng nó cũng triển khai `com.sun.management.OperatingSystemMXBean`, nhưng không nên cast vô điều kiện khi viết công cụ hướng đến JVM khác nhau. `instanceof` + pattern variable (Java 16+) giúp tránh `ClassCastException` và cho đường xử lý không có extension.

## 10. Ba tình huống thực tế để đọc đúng số liệu

### 10.1. OS memory thấp, Java heap used thấp

**Quan sát:**

```text
os.free rất thấp
heap.used còn thấp hơn -Xmx nhiều
```

Chưa thể kết luận JVM memory leak hoặc GC cần chạy. OS memory có thể chịu ảnh hưởng của process khác, cache, memory cgroup hoặc native usage. Các bước:

1. Xem `heap.used/committed/max` và GC trend.
2. Xem OS/process metrics hoặc cgroup memory usage cho **đúng PID/container**.
3. Xem direct buffers, thread count, metaspace, native memory nếu nghi process Java.
4. Đối chiếu nguồn cấp phát ngoài heap, không chỉ gọi `System.gc()`.
5. Kiểm tra liệu OS metric đang mô tả host, VM hay container.

### 10.2. Process RSS tăng nhưng heap gần như không đổi

**Khả năng:**

- Direct buffers, native allocations qua JNI/libraries.
- Metaspace, code cache, thread stacks, GC structures.
- Memory mappings hoặc working-set behavior do OS.
- JVM committed/reserved memory tăng dù heap used chưa tăng tương ứng.

**Không nên:** kết luận ngay rằng heap dump sẽ xác định mọi native leak. Heap dump tập trung vào Java heap, không đo toàn bộ native allocations. Cần phối hợp process metrics, buffer pool, JFR/GC data và NMT khi phù hợp.

### 10.3. `-Xmx` chưa tới trần nhưng container bị OOMKilled

`-Xmx` giới hạn **heap**; container memory accounting còn bao gồm các loại memory/process khác theo cgroup/OS. Native memory, direct buffers, page cache bị tính vào quota trong các chính sách nhất định, hoặc các tiến trình khác trong cùng container có thể gây áp lực.

Một process còn khả năng tăng heap **về mặt cấu hình** không có nghĩa container còn đủ memory để cấp trang. `OutOfMemoryError: Java heap space` và việc container bị hệ điều hành **kill** là hai đường lỗi khác nhau; trường hợp kill có thể không còn cơ hội ghi Java exception stack trace.

## 11. Phân biệt các loại sự cố hết bộ nhớ

| Triệu chứng | Khu vực nghi ngờ | Nguồn kiểm tra |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | Heap allocation không đáp ứng | `heap.used/max`, GC logs, heap dump |
| `OutOfMemoryError: Direct buffer memory` | Giới hạn/cấp phát direct buffers | `BufferPoolMXBean`, direct memory policy |
| Metaspace OOM | Class metadata / metaspace | Non-heap pool, class loading, NMT |
| Native thread creation failure | Thread stacks, OS resources/limits | Thread count, OS limits, native memory |
| Container OOMKilled | Memory limit của container/process accounting | Container/cgroup metrics và kernel/container events |
| RSS tăng mà heap ổn định | Native/mapped/buffer/thread hoặc OS accounting | Process RSS + NMT/BufferPool/OS |
| OS free thấp, Java heap nhỏ | Hệ thống tổng thể, không chỉ JVM | OS/container và các tiến trình khác |

Các thông báo OOM cụ thể có thể khác theo JVM/JDK/platform. Hãy dựa vào **exception/kernel reason thực tế** thay vì suy diễn một nguyên nhân chỉ từ chiều cao của cột “memory” trên dashboard.

## 12. Java module, portablity và môi trường container

### 12.1. Dùng `jdk.management` trong named module

Nếu chương trình được tổ chức thành một **named Java module** có `module-info.java`, và source import cả `MemoryMXBean` lẫn `com.sun.management.OperatingSystemMXBean`, khai báo:

```java
module example.metrics {
    requires java.management;
    requires jdk.management;
}
```

Đây là **module descriptor minh họa** cho một dự án modular. Demo đầy đủ ở mục 9 dùng classpath, không cần tạo descriptor khi chạy từ một file Java đơn giản bằng lệnh đã nêu.

`java.management` là nơi chứa `MemoryMXBean`/`MemoryUsage`/`BufferPoolMXBean`; `jdk.management` chứa extension `com.sun.management.OperatingSystemMXBean`. Nếu build một runtime image tối giản qua `jlink`, phải giữ các modules phù hợp; nếu chạy trên một JVM không triển khai JDK extension, code có import cụ thể có thể không portable ở mức biên dịch — cân nhắc thiết kế adapter cho từng runtime.

### 12.2. Đừng mặc định OS bean bằng “RAM host thật”

Oracle Javadoc mô tả operating environment có thể là OS native, virtualized environment hoặc container-managed environment. Điều đó quan trọng khi theo dõi:

- Pod/container có `memory limit` nhỏ hơn RAM node.
- JVM có thể sử dụng `-XX:MaxRAMPercentage`/ergonomics để chọn heap max theo tài nguyên được báo ở startup.
- Cgroup memory quota, current usage và event OOM do orchestrator cung cấp là nguồn độc lập cần đối chiếu.
- Khả năng container-awareness thay đổi theo JDK vendor, OS, runtime flags và mức hỗ trợ cgroup.

**Không so sánh thẳng** `getTotalMemorySize()` với một con số `kubectl top` rồi kết luận API sai; chúng có thể đo các đối tượng hoặc khoảng thời gian khác nhau. Cần ghi rõ **host/container/process/PID** trong metric labels.

### 12.3. Với container, đặt cả ngân sách heap và native

Một budget logic (không phải công thức cam kết):

```text
Container/OS memory budget
  ≥ Heap thực sự resident/committed khi chạy
  + Native allocations, direct buffers, stacks, metadata, JVM overhead
  + Các khoản memory khác được container tính trong quota
  + Safety headroom
```

Không dùng duy nhất `-Xmx = container memory limit` làm cấu hình an toàn tuyệt đối. Mức cần dành cho non-heap/native phụ thuộc tải, thread model, thư viện, GC và workload; theo dõi số liệu thật và thử dưới áp lực gần production.

## 13. Native Memory Tracking: khi heap không giải thích được process memory

Trên **HotSpot JVM**, Native Memory Tracking (**NMT**) là công cụ chẩn đoán **bộ nhớ nội bộ JVM**. Nó **tắt theo mặc định**, cần bật từ lúc khởi chạy JVM, ví dụ:

```bash
java -XX:NativeMemoryTracking=summary -Xmx256m -cp . MemoryScopesDemo
```

Đây là **lệnh bật NMT và chạy demo**, không tự tạo report sau khi process đã kết thúc. Khi muốn quan sát NMT trong một tiến trình **đang chạy**, dùng JDK `jcmd` với đúng PID và quyền attach phù hợp:

```bash
jcmd <pid> VM.native_memory summary
```

Dấu `<pid>` là **placeholder để thay bằng PID thực**, không dùng nguyên văn trong shell. Có thể lấy baseline rồi xem thay đổi theo thời gian:

```bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
```

**Lưu ý quan trọng:**

- NMT có overhead. Oracle tài liệu hóa chi phí khoảng **5–10%** cho tính năng này; cân nhắc khi bật ở production.
- NMT dùng cho HotSpot và phụ thuộc JVM implementation; không phải JVM nào cũng có command đó.
- NMT **không đếm đầy đủ mọi native allocation**, đặc biệt của thư viện native bên thứ ba và một số phần của JDK theo tài liệu VM.
- NMT có các mức `summary` và `detail`; `detail` nặng hơn và hữu ích khi cần nơi cấp phát.
- NMT `reserved`/`committed` không tự bằng **RSS**. Đừng so sánh chúng như hai số phải giống tuyệt đối.
- Cần tiến trình đang chạy và quyền attach, không nhất thiết có thể gọi vào một process trong container hoặc môi trường production bị khóa.

Đối với file Java demo chạy vài mili-giây, lệnh `jcmd` có thể đến **sau khi process đã kết thúc**; khi muốn tự thử NMT, hãy dùng một ứng dụng chạy đủ lâu hoặc môi trường test có thời gian quan sát thích hợp.

## 14. Thiết kế dashboard và alert theo đúng phạm vi

### 14.1. Đặt tên metric không nhập nhằng

Gợi ý tên có ý nghĩa:

| Metric label | Phạm vi đề xuất | Đơn vị |
| --- | --- | --- |
| `jvm_memory_heap_used_bytes` | `MemoryMXBean.heap.used` | bytes |
| `jvm_memory_heap_committed_bytes` | `MemoryMXBean.heap.committed` | bytes |
| `jvm_memory_heap_max_bytes` | `MemoryMXBean.heap.max` | bytes |
| `jvm_memory_nonheap_used_bytes` | `MemoryMXBean.nonHeap.used` | bytes |
| `jvm_buffer_direct_memory_used_bytes` | BufferPoolMXBean direct | bytes |
| `os_environment_memory_total_bytes` | OperatingSystemMXBean total | bytes |
| `os_environment_memory_free_bytes` | OperatingSystemMXBean free | bytes |
| `process_resident_memory_bytes` | OS/process resident metric, **không** từ `MemoryMXBean` | bytes |
| `container_memory_usage_bytes` | Container/cgroup usage metric | bytes |

Tên ở đây là **quy ước minh họa**, không khẳng định một exporter cụ thể đã triển khai y hệt những tên này. Khi dùng Micrometer, Prometheus exporter hay JMX exporter, hãy đối chiếu **tên/label và semantics thực tế**.

### 14.2. Các tỷ lệ hữu ích và giới hạn

**Heap used / max**:

```text
heapUsedRatio = heap.used / heap.max
```

Chỉ tính khi `heap.max > 0` và metric hợp lệ. Đây là mức dùng so với **trần heap**, không phải mức sử dụng RAM hệ điều hành.

**Heap used / committed**:

```text
heapCommittedUsageRatio = heap.used / heap.committed
```

Chỉ tính khi `committed > 0`. Phản ánh độ đầy vùng heap **đã committed** ở thời điểm đo, không nói GC có thể reclaim bao nhiêu object.

**OS free / total**:

```text
osFreeRatio = os.free / os.total
```

Chỉ tính khi `os.total > 0`. Thường dùng như chỉ báo điều kiện **operating environment**, nhưng “free” của OS không nhất thiết là toàn bộ memory mà ứng dụng cấp phát được hoặc một thước đo capacity duy nhất.

**Đừng đưa tất cả thành một “memory percent”**. Một chart phần trăm heap và một chart phần trăm OS/container có thể cùng ở mức 80% nhưng **không đo một thứ**.

### 14.3. Quan sát theo thời gian thay vì một snapshot

Khi điều tra:

- Thu thập cùng PID/container, cùng tag phiên bản JDK/GC.
- Ghi lại timestamps, interval và đơn vị bytes.
- Xem heap used **trước/sau các kỳ GC**, committed và max.
- So sánh process RSS/container usage với direct/mapped buffer metrics hoặc NMT.
- Kiểm tra dấu hiệu tăng dài hạn, không chỉ một đỉnh ngắn.
- Không ép GC chỉ để cải thiện biểu đồ nếu chưa xác định bottleneck.
- Đánh dấu thời điểm deploy, thay đổi `-Xmx`/`-Xms`, thay đổi số threads hoặc native library.

Một lần đọc `MemoryMXBean` và một lần đọc `OperatingSystemMXBean` **không phải một snapshot có cùng đồng hồ/atomicity**. Với dashboard, ghi timestamps và chấp nhận sai số do sampling.

## 15. Những ngộ nhận cần tránh

### Ngộ nhận 1 — `Runtime.freeMemory()` là RAM còn trống của máy

**Sai.** Nó ước lượng free memory bên trong vùng JVM hiện có cho objects. Muốn biết memory OS/environment, dùng `OperatingSystemMXBean.getFreeMemorySize()` hoặc OS/container metrics.

### Ngộ nhận 2 — `-Xmx256m` nghĩa là Java process không vượt 256 MiB

**Sai.** `-Xmx` là trần **heap**, còn process có non-heap và native memory, thread stacks, direct buffers.

### Ngộ nhận 3 — `heap.used` bằng RSS

**Sai.** RSS bao gồm nhiều vùng khác ngoài heap, với semantics OS khác.

### Ngộ nhận 4 — `heap.committed` là số object sống trong heap

**Sai.** `used` đo dung lượng đang dùng; `committed` là memory được đảm bảo cho quản lý heap. Object chưa được GC dọn vẫn có thể nằm trong used.

### Ngộ nhận 5 — `heap.max` là memory sẽ chắc chắn cấp được

**Sai.** `max` là giới hạn quản lý; OS/container có thể thiếu tài nguyên, nên việc cấp phát vẫn thất bại trước khi đạt max.

### Ngộ nhận 6 — `getTotalMemorySize()` luôn là RAM vật lý host

**Sai.** Javadoc nói **operating environment** có thể native, virtualized hoặc container-managed.

### Ngộ nhận 7 — `getCommittedVirtualMemorySize()` bằng RSS hoặc native used

**Sai.** Virtual memory commit không đồng nhất với memory resident hay native allocations.

### Ngộ nhận 8 — `MemoryMXBean.getNonHeapMemoryUsage()` đo mọi native memory

**Sai.** Nó chỉ thống kê các JVM non-heap memory pools; native libraries, stacks và direct buffers cần các nguồn đo bổ sung.

### Ngộ nhận 9 — Heap used tăng trước GC là memory leak

**Không đủ kết luận.** Cần quan sát GC và dữ liệu retained theo thời gian.

### Ngộ nhận 10 — OS free thấp là lỗi do Java heap

**Không nhất thiết.** Có thể là process khác, cache, container quotas hoặc native allocations.

### Ngộ nhận 11 — Có thể dùng `getTotalPhysicalMemorySize()` như API mới nhất

**Không nên.** Tên cũ đã deprecated từ Java 14; dùng `getTotalMemorySize()`.

### Ngộ nhận 12 — BufferPoolMXBean đo toàn bộ native memory

**Sai.** Nó chỉ phản ánh các buffer pools JVM cung cấp, thường có direct/mapped; không thay NMT/OS metrics.

### Ngộ nhận 13 — NMT cho biết chính xác toàn bộ RSS

**Sai.** NMT quan sát phần memory của HotSpot JVM nội bộ mà nó theo dõi, không đủ cho mọi allocation bên thứ ba hay resident pages.

### Ngộ nhận 14 — CPU load và memory usage có thể đổi chỗ trong dashboard

**Sai.** `getCpuLoad()` là tỷ lệ CPU; `getTotalMemorySize()` là byte. Đơn vị và ý nghĩa không tương đương.

## 16. Bài tập tự đánh giá

**Câu 1.** `Runtime.freeMemory()` là free heap hay free OS memory?

**Đáp án:** Free bên trong vùng memory JVM đang có cho objects, không phải free memory của OS.

**Câu 2.** `heap.used = 300 MiB`, `heap.committed = 512 MiB`, `heap.max = 1024 MiB`. Phần chưa dùng trong heap committed gần bao nhiêu?

**Đáp án:** Khoảng **212 MiB**. Chưa thể khẳng định có thể cấp tất cả 724 MiB đến max do giới hạn OS/GC/native.

**Câu 3.** Vì sao Java process có thể dùng 900 MiB RAM khi `-Xmx512m`?

**Đáp án:** Heap không phải toàn bộ process. Có thêm non-heap, stacks, direct/native allocations, memory mappings và overhead.

**Câu 4.** Nếu `getHeapMemoryUsage().getMax() == -1`, có nên tính `used / max`?

**Đáp án:** Không. `-1` nghĩa là không xác định; tỷ lệ phải được bỏ hoặc đánh dấu unavailable.

**Câu 5.** Có nên dùng `getTotalPhysicalMemorySize()` trên code mới Java 17+?

**Đáp án:** Không nên. API này deprecated từ Java 14; dùng `getTotalMemorySize()`.

**Câu 6.** Một container bị OOMKilled nhưng heap used thấp. Cần xem gì?

**Đáp án:** Container memory limit/current usage và process/native memory, direct buffers, thread stacks, các tiến trình cùng container; không chỉ heap.

**Câu 7.** `BufferPoolMXBean.getMemoryUsed()` là gì?

**Đáp án:** Ước lượng memory của buffer pool như direct/mapped, **không** là tổng native memory toàn process. Có thể trả `-1` nếu không có ước lượng.

**Câu 8.** `getCommittedVirtualMemorySize()` có phải RSS không?

**Đáp án:** Không. Committed virtual memory và resident physical memory là hai metrics khác.

**Câu 9.** Muốn xem HotSpot native memory tổng hợp theo subsystem, có thể dùng công cụ nào?

**Đáp án:** Bật `-XX:NativeMemoryTracking=summary` ngay khi chạy JVM, rồi dùng `jcmd <pid> VM.native_memory summary` vào một tiến trình còn chạy và có quyền attach. NMT không đo đầy đủ mọi native allocations.

**Câu 10.** Cùng host, chạy `-Xmx128m` rồi `-Xmx256m`, vì sao `heap.max` đổi còn `os.total` có thể vẫn giống?

**Đáp án:** `-Xmx` là giới hạn **JVM heap**, không thay đổi tổng memory của môi trường OS.

**Câu 11.** `heap.used` tăng rồi giảm mạnh sau GC có đồng nghĩa memory leak không?

**Đáp án:** Không. Used có thể bao gồm objects chưa được GC thu hồi; cần quan sát retained usage và xu hướng dài hạn.

**Câu 12.** Đã có `nonHeap.used` thì có cần xem direct/native memory không?

**Đáp án:** Có, nếu vấn đề liên quan process/container memory; non-heap bean không nhất thiết bao hàm các vùng native đó.

## 17. Checklist đo bộ nhớ Java không nhầm phạm vi

- [ ] Xác định cần **OS/environment**, **container**, **process RSS**, **heap**, **non-heap** hay **direct buffers**.
- [ ] Dùng `getTotalMemorySize/getFreeMemorySize` từ `com.sun.management.OperatingSystemMXBean` thay cho các tên deprecated từ Java 14.
- [ ] Dùng `MemoryMXBean.getHeapMemoryUsage()` cho heap used/committed/max.
- [ ] Không gọi `Runtime.freeMemory()` là RAM OS còn trống.
- [ ] Nhớ `-Xmx` giới hạn heap, **không** giới hạn toàn bộ process.
- [ ] Kiểm tra `MemoryUsage.max == -1` và API có thể trả unavailable.
- [ ] Đơn vị gốc là bytes; nếu hiển thị MiB chia `1024²` và ghi đúng nhãn.
- [ ] Không suy ra process RSS từ `getCommittedVirtualMemorySize`.
- [ ] Phân biệt `nonHeap.used` với mọi native allocations; xem `BufferPoolMXBean` hoặc NMT/OS khi cần.
- [ ] Với container, kiểm tra limit/current OOM events của cgroup/monitoring platform.
- [ ] Thu thập sample theo thời gian và cùng PID/container, xem GC và thay đổi load.
- [ ] Với HotSpot, chỉ bật NMT khi cần và tính tới chi phí; không coi NMT bằng toàn bộ RSS.
- [ ] Nếu dùng named module, khai báo `requires java.management; requires jdk.management;` khi cần extension.
- [ ] Không hardcode heap max hoặc OS total trong tests; xác nhận invariants và semantics thay vì con số của một host.
- [ ] Chọn threshold alert riêng cho heap, process/container và native; không gộp thành một số “memory percentage”.

## 18. Tài liệu chính thức còn áp dụng

1. [Oracle Java SE 26 — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap, non-heap và `getHeapMemoryUsage/getNonHeapMemoryUsage`.
2. [Oracle Java SE 26 — `MemoryUsage`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryUsage.html): nghĩa chính xác của `init/used/committed/max` và giá trị `-1`.
3. [Oracle Java SE 27 — `com.sun.management.OperatingSystemMXBean`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): operating environment, `getTotalMemorySize`/`getFreeMemorySize` (since 14), những method deprecated và process metrics.
4. [Oracle Java SE 21 — `OperatingSystemMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): hỗ trợ tương thích trên Java LTS, host/VM/container.
5. [Oracle Java SE 25 — `BufferPoolMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): direct/mapped pool memory usage.
6. [Oracle Java SE 25 — `Runtime`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html): `totalMemory/freeMemory/maxMemory`.
7. [Oracle Java SE 25 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/25/vm/native-memory-tracking.html): cấu hình NMT, `jcmd`, overhead và phạm vi không bao phủ.
8. [Oracle Java SE 17 — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): đối chiếu API với Java 17+.
