# getFreeMemorySize() và getTotalMemorySize() — đọc số liệu bộ nhớ của môi trường hệ thống

## 1. Ý nghĩa và phạm vi của hai phương thức

Chủ đề **Số liệu hệ thống** của Java 14 giới thiệu hai API trong interface `com.sun.management.OperatingSystemMXBean`:

- **`long getFreeMemorySize()`**: trả về lượng bộ nhớ đang **trống** trong môi trường hệ điều hành mà JVM hoạt động; đơn vị **byte**.
- **`long getTotalMemorySize()`**: trả về **tổng lượng bộ nhớ** của môi trường đó; đơn vị **byte**.

Cả hai đều có **`Since: 14`** trong Javadoc, và vẫn tồn tại trong JDK 17, 25, 26. Interface nằm trong module **`jdk.management`** của JDK, là phần mở rộng **công khai được tài liệu hóa**, không phải class triển khai nội bộ cần reflection.

Cụm từ **“môi trường hệ thống”** rất quan trọng. JVM có thể chạy trên hệ điều hành vật lý, máy ảo hoặc container. Kết quả có thể mô tả tài nguyên được nhìn thấy trong môi trường đó, **không nhất thiết luôn là RAM vật lý của host**. Và đó **không phải các số liệu của Java heap**.

Hai phương thức thay cho những tên cũ `getFreePhysicalMemorySize()` và `getTotalPhysicalMemorySize()`, vốn đã **deprecated từ Java 14**. Chỉ dùng hai tên mới trong code hiện đại; các tên cũ được nhắc tới để nhận biết và thay thế, không phải kiến thức legacy cần học cách sử dụng.

### Mục tiêu bài học

1. Biết interface và module đúng, cách lấy platform MXBean bằng `ManagementFactory`.
2. Hiểu dữ liệu trả về là `long` theo **byte**, cách đổi sang MiB/GiB và tính tỷ lệ.
3. Phân biệt system memory, Java heap, process RSS, swap và virtual memory.
4. Hiểu ảnh hưởng của VM, container/cgroup và giới hạn tài nguyên.
5. Nhận diện dữ liệu live thay đổi theo thời gian, việc gọi hai method **không tạo snapshot nguyên tử**.
6. Viết, biên dịch và chạy chương trình Java 17+ có phần số mẫu xác định và số máy thật biến động.
7. Tránh sử dụng metric làm lời đảm bảo cấp phát thành công hoặc quyết định `-Xmx` mà không xét native memory.
8. Tổ chức đo đạc và cảnh báo production theo đơn vị, phạm vi và chính sách nhất quán.

## 2. Interface chính xác: com.sun.management không phải java.lang.management

Tên `OperatingSystemMXBean` xuất hiện trong hai package:

| Interface | Module | Vai trò |
|---|---|---|
| `java.lang.management.OperatingSystemMXBean` | `java.management` | API nền tảng: `getName`, `getArch`, `getVersion`, `getAvailableProcessors`, `getSystemLoadAverage` |
| **`com.sun.management.OperatingSystemMXBean`** | **`jdk.management`** | Phần mở rộng có **`getFreeMemorySize()`** và **`getTotalMemorySize()`**, cùng CPU/swap/virtual-memory metrics |
| `java.lang.management.MemoryMXBean` | `java.management` | Quan sát bộ nhớ **heap** và **non-heap** do JVM quản lý |

Nếu khai báo biến bằng interface cơ bản:

~~~java
java.lang.management.OperatingSystemMXBean basic =
        java.lang.management.ManagementFactory.getOperatingSystemMXBean();

// basic.getFreeMemorySize(); // Không biên dịch: interface cơ bản thiếu method này.
~~~

Đây là mảnh code minh họa, dòng sai đã được comment. Nguyên nhân là **kiểu compile-time** của `basic` không có member cần gọi. Đừng xử lý bằng cách phản chiếu nội bộ hoặc ép kiểu mù quáng.

### Cách lấy bean nên dùng

~~~java
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.ManagementFactory;

OperatingSystemMXBean os =
        ManagementFactory.getPlatformMXBean(
                OperatingSystemMXBean.class);
if (os != null) {
    long totalBytes = os.getTotalMemorySize();
    long freeBytes = os.getFreeMemorySize();
}
~~~

Đây là đoạn đặt trong phương thức Java. `getPlatformMXBean(Class<T>)` lấy trực tiếp interface platform-management bạn muốn và **có thể trả `null`** khi interface không có implementation phù hợp. Đây là cách phù hợp với ứng dụng JDK hiện đại có module `jdk.management`.

Cách thứ hai là `ManagementFactory.getOperatingSystemMXBean()` rồi kiểm tra:

~~~java
java.lang.management.OperatingSystemMXBean base =
        ManagementFactory.getOperatingSystemMXBean();

if (base instanceof com.sun.management.OperatingSystemMXBean ext) {
    long total = ext.getTotalMemorySize();
    long free = ext.getFreeMemorySize();
}
~~~

`instanceof` pattern có từ Java 16 và là tính năng ổn định trên Java 17. Kiểm tra này giúp tránh `ClassCastException` nếu ứng dụng chạy trên JVM không cung cấp extension tương ứng.

### Module `jdk.management` có sẵn không?

Trên JDK đầy đủ hỗ trợ interface, **có**. Nhưng một runtime tự tạo bằng `jlink` có thể cố ý loại module này. Với ứng dụng JPMS:

~~~java
module example.memory.monitor {
    requires java.management;
    requires jdk.management;
}
~~~

Đây là **module-info.java minh họa**; cần cấu trúc module, source packages và module path tương ứng mới biên dịch cả ứng dụng modular. Chương trình độc lập ở mục 6 chạy trên **classpath**, không cần file module-info.java. Không dùng `--add-opens` hoặc code truy cập class triển khai private để gọi extension công khai này.

## 3. Trả về `long`, luôn theo byte

Hai phương thức trả `long` là số byte; không trả MiB, GiB hoặc tỷ lệ phần trăm.

~~~java
long total = os.getTotalMemorySize();
long free  = os.getFreeMemorySize();
~~~

Nếu muốn hiển thị, hãy phân biệt:

| Đơn vị | Tương đương byte | Thích hợp khi |
|---|---:|---|
| Byte (B) | 1 | Lưu metric gốc hoặc payload JSON |
| KiB | 1.024 | Thông tin dung lượng nhỏ |
| MiB | 1.048.576 | Dashboard memory |
| GiB | 1.073.741.824 | Tổng memory |
| MB (thập phân) | 1.000.000 | Chỉ dùng khi nguồn định nghĩa theo MB |
| GB (thập phân) | 1.000.000.000 | Không nhầm với GiB |

Ví dụ:

~~~java
double totalMiB = total / (1024.0 * 1024.0);
double freeGiB  = free / (1024.0 * 1024.0 * 1024.0);
~~~

Dùng `1024.0` tạo phép chia dạng floating-point. Nếu viết `total / 1024 / 1024` toàn kiểu integer, phần thập phân bị mất trước khi format. Không đổi byte sang MiB rồi ghi nhãn `MB` tùy tiện.

### Tính phần bộ nhớ môi trường đã dùng

Nếu một cặp mẫu hợp lệ với `total > 0` và `0 <= free <= total`:

~~~text
usedBytes       = totalBytes - freeBytes
freePercent     = 100.0 * freeBytes / totalBytes
usedPercent     = 100.0 * usedBytes / totalBytes
totalMiB        = totalBytes / 1_048_576.0
usedGiB         = usedBytes / 1_073_741_824.0
~~~

Đây là **ước lượng mức không còn trống trong môi trường**, **không phải** process Java đã chiếm `usedBytes`. Hệ điều hành, tiến trình khác và caches có thể góp phần vào giá trị đó.

**Ví dụ số cố định:**

~~~text
total = 8 GiB
free = 2 GiB
used = 6 GiB
usedPercent = 75.0%
freePercent = 25.0%
~~~

Không nhầm các giá trị ví dụ với dung lượng máy đang học.

### Tránh overflow khi tính tỷ lệ

~~~java
double usedPct = (total - free) * 100.0 / total;
~~~

Nên chuyển sang double **trước phép nhân**. Viết `(total-free)*100/total` có thể nhân bằng `long` và overflow trước khi chia. Tính phần trăm chỉ khi **total dương và hai số hợp lệ**.

## 4. Tổng và trống của môi trường khác bộ nhớ JVM heap

Hãy phân biệt:

~~~java
// Hệ điều hành / VM / container được nhìn thấy:
long systemTotal = os.getTotalMemorySize();
long systemFree  = os.getFreeMemorySize();

// Bộ nhớ Java heap do JVM quản lý:
Runtime runtime = Runtime.getRuntime();
long heapCurrentTotal = runtime.totalMemory();
long heapFree = runtime.freeMemory();
long heapMaximum = runtime.maxMemory();
~~~

Các số của `Runtime` ở đây **không** mô tả tổng/trống RAM host. `Runtime.totalMemory()` là lượng heap hiện có cho objects; `Runtime.freeMemory()` là phần heap ước lượng còn trống; `Runtime.maxMemory()` phản ánh mức tối đa mà JVM sẽ cố gắng cấp cho heap.

Hoặc sử dụng `MemoryMXBean`:

~~~java
java.lang.management.MemoryUsage heap =
        java.lang.management.ManagementFactory
                .getMemoryMXBean()
                .getHeapMemoryUsage();

long heapUsed = heap.getUsed();
long heapCommitted = heap.getCommitted();
long heapMax = heap.getMax();
~~~

`heapUsed` là phần **heap JVM** đang sử dụng theo cách GC/JVM báo, không phải RSS của process; `heapCommitted` là memory JVM đã commit cho heap. Java còn có metaspace, code cache, native buffers, thread stacks, JIT/JNI, GC structures và nhiều phần ngoài heap.

### Bảng chọn đúng metric

| Câu hỏi | Metric/API phù hợp |
|---|---|
| Môi trường còn bao nhiêu memory? | `OperatingSystemMXBean.getFreeMemorySize()` |
| Tổng memory của môi trường là bao nhiêu? | `OperatingSystemMXBean.getTotalMemorySize()` |
| Java heap đang dùng bao nhiêu? | `MemoryMXBean.getHeapMemoryUsage().getUsed()` |
| Heap đã commit bao nhiêu? | `MemoryUsage.getCommitted()` |
| Giới hạn heap JVM? | `Runtime.maxMemory()` hoặc `MemoryUsage.getMax()` nếu có |
| Process Java đang chiếm bao nhiêu RSS? | Metric native/OS/process-level theo nền tảng |
| Máy còn bao nhiêu swap? | `getFreeSwapSpaceSize()` và `getTotalSwapSpaceSize()` |
| Virtual committed memory của process? | `getCommittedVirtualMemorySize()` |
| Container đang sử dụng bao nhiêu memory? | Container/cgroup metrics, đối chiếu MXBean |

### Vì sao không dùng free system memory để dự đoán OOM?

Một ứng dụng Java giới hạn `-Xmx512m` trên máy 16 GiB RAM vẫn có thể gặp `OutOfMemoryError` của heap dù memory OS còn trống nhiều. Ngược lại, quá nhiều native allocations/JNI/direct buffers có thể khiến JVM bị giới hạn bởi container hoặc OS khi heap chưa đầy. `getFreeMemorySize()` không giải quyết được tất cả giới hạn này.

**Không coi lượng memory còn trống của môi trường là lời bảo đảm cấp phát thành công**. Từ lúc đọc số đến lúc cấp phát, các tiến trình khác và JVM có thể tiếp tục tiêu thụ memory; đây là kiểu lỗi `time-of-check/time-of-use` nếu dựa hoàn toàn vào snapshot để quyết định cấp phát.

## 5. JVM có thể chạy trên host, máy ảo hoặc container

Javadoc `OperatingSystemMXBean` nêu rõ môi trường của JVM có thể là native OS, virtualized OS hoặc **container-managed environment**. Trên OpenJDK/HotSpot hỗ trợ và có bật container awareness, đặc biệt với Linux **cgroups**, các số liệu có thể phản ánh giới hạn container thay vì toàn bộ RAM của host.

Ví dụ:

~~~text
Host:              64 GiB RAM
Container limit:    4 GiB RAM
JVM chạy trong container với resource limits được nhận diện
~~~

Trong điều kiện JVM quan sát đúng container limit, `getTotalMemorySize()` **có thể** gần mức 4 GiB thay vì 64 GiB. Nhưng **đừng khẳng định tất cả JDK/OS/container đều trả đúng limit**: kết quả còn phụ thuộc JDK vendor/build, cấu hình container support, loại cgroup, tài nguyên được expose và hành vi của nền tảng.

### Sự khác nhau giữa host RAM và container memory

- **Host RAM:** toàn bộ vật lý của máy chủ.
- **VM memory:** bộ nhớ thấy được bởi guest OS của máy ảo.
- **Container limit:** hạn mức có thể áp dụng cho process group.
- **JVM heap max:** giới hạn do JVM/GC/`-Xmx` thiết lập.
- **Memory available:** một số hệ điều hành có khái niệm memory có thể thu hồi, khác chữ “free” theo cách định nghĩa của chỉ số cụ thể.

Đừng trộn các scope này vào một biểu đồ mà không gắn nhãn. Khi chạy Kubernetes hoặc Docker, so sánh với metric container/cgroup và cấu hình JDK, thay vì xem `getTotalMemorySize()` là host RAM hiển nhiên.

### Container awareness không thay thế điều chỉnh -Xmx

Ngay khi total phản ánh container limit, JVM vẫn cần memory ngoài heap. Nếu cấu hình heap gần bằng toàn bộ limit, process có thể bị OOM-kill vì direct buffers, stacks, class metadata, native code hoặc memory khác. Để lập ngân sách memory của container, hãy tính **heap + non-heap/native + memory dùng bởi process phụ và dư địa an toàn**.

## 6. Ví dụ Java 17+ hoàn chỉnh, đã biên dịch và chạy thử

Chương trình sau có **hai phần**: một ví dụ nhân tạo có số cố định 8 GiB/2 GiB để kiểm tra công thức, và một phần đọc **số live** trên máy đang chạy bằng `OperatingSystemMXBean`. Phần live kiểm tra phạm vi dữ liệu trước khi tính phần trăm, bởi các nguồn có thể thay đổi giữa hai lần đọc.

Lưu file **`SystemMemoryMetricsDemo.java`**:

~~~java
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.Locale;

public final class SystemMemoryMetricsDemo {
    private static final long MIB = 1024L * 1024L;
    private static final long GIB = 1024L * MIB;

    record MemorySample(long totalBytes, long freeBytes) {
        boolean valid() {
            return totalBytes > 0
                    && freeBytes >= 0
                    && freeBytes <= totalBytes;
        }

        long usedBytes() {
            if (!valid()) {
                throw new IllegalStateException("invalid sample");
            }
            return totalBytes - freeBytes;
        }

        double usedPercent() {
            return usedBytes() * 100.0 / totalBytes;
        }
    }

    public static void main(String[] args) {
        MemorySample example =
                new MemorySample(8L * GIB, 2L * GIB);

        System.out.printf(Locale.ROOT,
                "example.usedGiB=%.2f%n",
                example.usedBytes() / (double) GIB);
        System.out.printf(Locale.ROOT,
                "example.usedPercent=%.1f%%%n",
                example.usedPercent());

        OperatingSystemMXBean os =
                ManagementFactory.getPlatformMXBean(
                        OperatingSystemMXBean.class);
        if (os == null) {
            System.out.println("environment=not-supported");
            return;
        }

        long total = os.getTotalMemorySize();
        long free = os.getFreeMemorySize();
        MemorySample sample = new MemorySample(total, free);

        if (!sample.valid()) {
            System.out.println("environment=invalid-or-changing-sample");
            return;
        }

        System.out.println("environment=available");
        System.out.printf(Locale.ROOT,
                "environment.totalMiB=%.1f%n",
                total / (double) MIB);
        System.out.printf(Locale.ROOT,
                "environment.freeMiB=%.1f%n",
                free / (double) MIB);
        System.out.printf(Locale.ROOT,
                "environment.usedPercent=%.1f%%%n",
                sample.usedPercent());

        MemoryUsage heap = ManagementFactory
                .getMemoryMXBean()
                .getHeapMemoryUsage();
        System.out.printf(Locale.ROOT,
                "jvm.heapUsedMiB=%.1f%n",
                heap.getUsed() / (double) MIB);
    }
}
~~~

Chạy với JDK 17+ có module `jdk.management`:

~~~bash
javac --release 17 SystemMemoryMetricsDemo.java
java SystemMemoryMetricsDemo
~~~

Chương trình này **đã được biên dịch bằng `javac --release 17` và chạy thành công**. `record` là feature ổn định từ Java 16, không cần enable preview.

### Phần stdout luôn cố định

~~~text
example.usedGiB=6.00
example.usedPercent=75.0%
~~~

Vì dữ liệu nhân tạo `total=8 GiB, free=2 GiB` luôn giống nhau, hai dòng này không phụ thuộc OS hay thời điểm.

### Ví dụ stdout từ một lần chạy thật

~~~text
example.usedGiB=6.00
example.usedPercent=75.0%
environment=available
environment.totalMiB=130835.2
environment.freeMiB=57447.5
environment.usedPercent=56.1%
jvm.heapUsedMiB=0.0
~~~

**Chú ý:** Đây là **một lần chạy trên môi trường thử nghiệm**, không phải stdout có thể dự đoán chính xác ở mọi máy. Các dòng `environment.totalMiB`, `environment.freeMiB`, `environment.usedPercent` và `jvm.heapUsedMiB` thay đổi theo máy/JDK/container và lúc lấy mẫu. Nếu bean không được cung cấp, chương trình in `environment=not-supported` và dừng; nếu cặp số vi phạm điều kiện kiểm tra, chương trình in `environment=invalid-or-changing-sample` và dừng.

### Giải thích chi tiết chương trình

**1. Tạo `MemorySample` dữ liệu đủ nhỏ và bất biến**

`record MemorySample(long totalBytes, long freeBytes)` lưu hai số `long`. Hàm `valid()` chỉ chấp nhận `totalBytes > 0` và `0 <= freeBytes <= totalBytes`. Hàm `usedBytes()` từ chối tính với mẫu không hợp lệ. Đây là **phòng vệ** của chương trình, không phải tuyên bố rằng API phải trả sentinel âm khi unsupported.

**2. Dùng `Locale.ROOT` cho output có thể kiểm thử**

`System.out.printf(Locale.ROOT, ...)` giữ dấu thập phân `.`, tránh output dùng dấu phẩy thập phân trên hệ thống có locale khác. `%%` trong format string xuất ký tự phần trăm; `%n` xuống dòng phù hợp hệ thống.

**3. Lấy platform MXBean chính xác**

~~~java
OperatingSystemMXBean os =
        ManagementFactory.getPlatformMXBean(
                OperatingSystemMXBean.class);
~~~

Không dùng interface cơ bản rồi kỳ vọng có method mới, cũng không cần ép kiểu không kiểm tra.

**4. Tính toán trên snapshot hợp lệ**

~~~java
long total = os.getTotalMemorySize();
long free = os.getFreeMemorySize();
MemorySample sample = new MemorySample(total, free);
~~~

Hai phép đọc **không có đảm bảo snapshot atomic**. Nếu `free > total` hay total không dương, ví dụ không cố đưa một phần trăm sai lên màn hình; nó báo trạng thái bất thường.

**5. Phân biệt heap dùng với memory môi trường**

~~~java
MemoryUsage heap = ManagementFactory
        .getMemoryMXBean()
        .getHeapMemoryUsage();
~~~

Heap của riêng JVM có thể rất nhỏ dù số memory môi trường đang dùng là nhiều chục GiB vì những tiến trình và bộ đệm khác. Đây là mục đích của việc in `jvm.heapUsedMiB` cạnh các chỉ số `environment.*`.

### Vì sao không hard-code con số “RAM host” trong test?

Vì hai phương thức là API quan sát **hệ thống sống**. Một bài kiểm tra tốt cần phân biệt **phần tính toán thuần túy** (dữ liệu giả lập, output cố định) với **phần quan sát môi trường** (output biến động). Thử assert tổng memory hoặc free phải bằng một giá trị cụ thể sẽ khiến test không còn portable và dễ thất bại giả khi chạy CI/container.

## 7. Biện pháp phòng vệ và edge cases

### 7.1. Giá trị âm hoặc tổng bằng không

Hai method có Javadoc ngắn gọn “returns amount of ... in bytes”, **không ghi `-1` là sentinel cho unsupported như `getCommittedVirtualMemorySize()`**. Tuy vậy, chương trình vẫn nên kiểm tra `total > 0` và `0 <= free <= total` để xử lý dữ liệu từ môi trường không thông thường, sai nguồn, hoặc cặp mẫu bị lệch thời điểm.

Không báo metric sai nếu dữ liệu không hợp lệ; xuất trạng thái unavailable/inconsistent và thử đọc lại theo chính sách monitoring.

### 7.2. Thay đổi giữa hai phép đọc

~~~java
long total = os.getTotalMemorySize();
long free = os.getFreeMemorySize();
~~~

Đây là **hai quan sát**, không phải một giao dịch. Container limits có thể thay đổi, OS memory free thay đổi nhanh theo process khác; nếu phân tích cần tính chính xác thời gian, hãy đặt timestamp lấy mẫu, đọc gần nhau và kiểm tra sự hợp lệ.

### 7.3. Không vội “clamp” số bất thường

Nếu `free > total`, code không nên tự đổi thành `free=total` rồi báo `used=0` nếu chưa biết nguyên nhân. Việc này che giấu mismatch và có thể làm dashboard trông tốt giả. Có thể lấy mẫu lại và quan sát raw metrics cùng thông tin JVM/OS.

### 7.4. Hiểu đúng “free” và “available”

Các OS có nhiều cách đo: free pages, reclaimable cache, memory pressure, working set, host memory hay container memory. Hai API nói tới **free** của môi trường mà JVM quan sát; không có cam kết bằng một cột “Available” của Task Manager hay một field cụ thể trong `/proc/meminfo`.

### 7.5. Thiếu module `jdk.management`

Một runtime được `jlink` rút gọn có thể thiếu interface `com.sun.management.OperatingSystemMXBean`. Nếu ứng dụng có dependency bắt buộc tới nó, phải đóng module `jdk.management` vào runtime khi build. Một nhánh `if (os == null)` chỉ xử lý **bean không được triển khai khi class đã nạp được**; không tự chữa được việc runtime thiếu cả class/module lúc khởi chạy.

### 7.6. Không dùng memory free làm điều kiện đảm bảo cấp phát

Không viết:

~~~java
if (os.getFreeMemorySize() > bytesNeeded) {
    // KHÔNG được kết luận: new byte[(int) bytesNeeded] chắc chắn thành công.
}
~~~

Đây là code **chống-mẫu**. Lý do: `-Xmx`, loại allocation, process address space, giới hạn OS/container, memory native, fragmentation, các process khác và thay đổi theo thời gian đều có thể ảnh hưởng. Nếu cần giới hạn workload, dùng cơ chế quản lý tài nguyên/queue/circuit-breaker hợp lý kết hợp metric, không dựa duy nhất vào phép so sánh một snapshot.

## 8. Sampling và alert trong production

Hai chỉ số này phù hợp để quan sát sức khỏe và capacity, đặc biệt khi ghi **chuỗi thời gian** và kết hợp với heap/process/container metrics.

### Gợi ý metric naming (minh họa)

| Metric | Đơn vị | Nguồn |
|---|---|---|
| `environment_memory_total_bytes` | byte | `getTotalMemorySize()` |
| `environment_memory_free_bytes` | byte | `getFreeMemorySize()` |
| `environment_memory_used_bytes` | byte | `total-free` khi hợp lệ |
| `environment_memory_used_ratio` | 0 đến 1 | `(total-free)/total` |
| `jvm_heap_used_bytes` | byte | `MemoryMXBean.getHeapMemoryUsage().getUsed()` |
| `jvm_heap_committed_bytes` | byte | `MemoryMXBean.getHeapMemoryUsage().getCommitted()` |
| `jvm_nonheap_used_bytes` | byte | `MemoryMXBean.getNonHeapMemoryUsage().getUsed()` |

Đây là **tên đề xuất**, không phải một quy chuẩn bắt buộc của Micrometer/OpenTelemetry/Prometheus. Nếu ứng dụng đã có metrics exporter, kiểm tra semantic conventions và tránh xuất trùng cùng số với tên/labels khác.

### Metadata đi kèm mẫu

Khi gửi metric lên observability system, nên lưu hoặc label:

- JDK vendor/version/build.
- Tên OS/architecture, container hoặc VM và khả năng container awareness.
- Workload/process/container ID (theo chính sách telemetry).
- Timestamp và chu kỳ sampling.
- Đơn vị thô là **bytes**, không lẫn MiB với MB.
- Trạng thái thiếu MXBean hoặc mẫu không hợp lệ.

### Thiết kế threshold hợp lý

Ví dụ chỉ dựa `freePercent < 10%` để tự tắt ứng dụng có thể không phù hợp với OS/page cache hoặc container. Cảnh báo tốt nên dùng **nhiều mẫu liên tục**, xét memory pressure, cgroup current/limit, JVM heap, GC hoạt động và tác động nghiệp vụ. Không gọi `System.gc()` lặp liên tục chỉ vì OS báo free thấp; nó không giải phóng được memory thuộc process khác hoặc mọi native allocations của JVM.

### Tránh đọc quá dày

Không phải mỗi HTTP request đều cần tạo event/log mới từ `getFreeMemorySize()`. Đọc theo chu kỳ vừa đủ phục vụ dashboard và cảnh báo, ví dụ mỗi vài giây hoặc vài chục giây theo nhu cầu. Các giá trị OS thay đổi nhanh, nhưng tần suất thu thập quá cao cũng tạo overhead và nhiễu quan sát.

## 9. Các lỗi thường gặp khi áp dụng

| Sai lầm | Vì sao sai | Khắc phục |
|---|---|---|
| Import `java.lang.management.OperatingSystemMXBean` | Thiếu hai method Java 14 này | Dùng `com.sun.management.OperatingSystemMXBean` |
| Dùng `getFreePhysicalMemorySize()` | Đã deprecated từ Java 14 | Chuyển sang `getFreeMemorySize()` |
| Dùng `getTotalPhysicalMemorySize()` | Đã deprecated từ Java 14 | Chuyển sang `getTotalMemorySize()` |
| Giả định `com.sun.management` là reflection nội bộ | Đó là interface documented của JDK extension | Đọc Javadoc module `jdk.management` |
| Gọi `Runtime.freeMemory()` để đọc RAM trống hệ thống | Nó đo heap JVM | Dùng OS MXBean |
| Gọi `Runtime.totalMemory()` để đọc tổng RAM host | Nó đo heap hiện có | Dùng OS MXBean, xác định scope |
| Coi `getTotalMemorySize()` bằng `-Xmx` | Total memory môi trường khác heap max | Theo dõi `Runtime.maxMemory()` riêng |
| Coi `total-free` là memory của Java process | Có thể gồm OS/process khác/cache | Dùng process/JVM memory metrics |
| Gán đơn vị MiB nhưng in byte | Sai quy mô hơn một triệu lần | Chia `1_048_576.0` |
| Nhân `long used*100` trước khi chia | Có thể overflow | Nhân `100.0` |
| Chia percent cho `total=0` | Không hợp lệ | Kiểm tra total dương |
| Không kiểm tra `free > total` | Có thể tạo phần trăm âm | Đánh dấu mẫu invalid |
| Hard-code RAM 16 GiB trong unit test | Không portable | Dữ liệu mẫu cố định + live metric linh hoạt |
| Xem cgroup container là host memory | Phạm vi khác | Đối chiếu container/host scope |
| Xem mọi container đều có cùng semantics | Phụ thuộc JDK/OS/cgroup | Kiểm chứng trên target runtime |
| Chỉ nhìn một lần đọc để kết luận memory leak | Không có xu hướng | Quan sát heap/GC/process qua thời gian |
| Thiếu `jdk.management` trong image jlink | Class/API có thể không nạp được | Đóng module phù hợp khi build |
| In thiếu timestamp và unit | Khó diễn giải | Đặt metric names/labels rõ nghĩa |
| Dùng free memory để hứa allocation không OOM | Còn JVM/OS/native constraints | Resource budgeting và kiểm thử |

## 10. Checklist trước khi đưa vào ứng dụng thật

- [ ] Chọn đúng `com.sun.management.OperatingSystemMXBean`.
- [ ] Runtime có module `jdk.management` cùng `java.management` khi cần.
- [ ] Lấy bean bằng `ManagementFactory.getPlatformMXBean(...)` và xử lý trường hợp không có.
- [ ] Dùng hai tên mới có từ Java 14, không gọi phương thức tên cũ đã deprecated.
- [ ] Hiểu rõ đơn vị `long` theo byte.
- [ ] Ghi nhãn MiB/GiB đúng hệ số 1024; không nhầm MB/GB.
- [ ] Nếu tính tỷ lệ, xác thực `total>0`, `free>=0` và `free<=total`.
- [ ] Không dùng phép nhân integer có nguy cơ overflow.
- [ ] Biết môi trường đang là host, VM hoặc container.
- [ ] Đối chiếu cgroup/container limit và JDK/container awareness khi cần.
- [ ] Không coi hai lần gọi là một snapshot nguyên tử.
- [ ] Không coi `total-free` là RSS hay heap of process.
- [ ] Theo dõi riêng heap/nonheap/native/process memory khi chẩn đoán JVM.
- [ ] Không xem free memory là cam kết cấp phát thành công.
- [ ] Có timestamp, chu kỳ sampling, unit và trạng thái invalid/unavailable.
- [ ] Kiểm thử với JDK, OS, container và Java runtime image thực tế của sản phẩm.
- [ ] Có chính sách alert dựa trên nhiều mẫu/thông tin liên quan thay vì một số cố định.

## 11. Tự kiểm tra kiến thức

**Câu 1.** `getFreeMemorySize()` và `getTotalMemorySize()` được khai báo trên interface nào?

**Đáp án:** `com.sun.management.OperatingSystemMXBean` trong module `jdk.management`, không phải interface cơ bản cùng tên trong `java.lang.management`.

**Câu 2.** Hai method xuất hiện từ phiên bản Java nào?

**Đáp án:** **Java 14**, và vẫn còn trong Java 17/26. Các tên cũ có chữ `Physical` đã deprecated từ Java 14.

**Câu 3.** Cả hai trả đơn vị nào?

**Đáp án:** **Byte**, kiểu `long`. Muốn MiB phải chia `1_048_576.0`.

**Câu 4.** Với `total=8 GiB`, `free=2 GiB`, used và usedPercent là bao nhiêu?

**Đáp án:** `used=6 GiB`, `usedPercent=75.0%`.

**Câu 5.** `Runtime.getRuntime().freeMemory()` có bằng `os.getFreeMemorySize()` không?

**Đáp án:** Không. Runtime metric phản ánh bộ nhớ trống của JVM heap; OS MXBean metric phản ánh môi trường vận hành.

**Câu 6.** Nếu JVM trong container giới hạn 4 GiB trên host 64 GiB trả total gần 4 GiB thì API sai?

**Đáp án:** Không nhất thiết. OpenJDK có container awareness có thể xem limit container là tài nguyên môi trường. Cần xác minh JDK/OS/cgroup.

**Câu 7.** Vì sao `total-free` không phải RSS Java process?

**Đáp án:** Vì nó là tổng phần memory không free của môi trường, có thể gồm OS, process khác và caches.

**Câu 8.** Nếu `free > total`, có nên tự clamp free về total rồi báo 0% used?

**Đáp án:** Không nên che dữ liệu bất thường; hãy đánh dấu mẫu invalid, lấy lại và kiểm tra nguồn/điều kiện môi trường.

**Câu 9.** `getFreeMemorySize()` lớn có đảm bảo tạo được mảng Java cùng kích thước?

**Đáp án:** Không; còn `-Xmx`, native/OS/container limits, GC và biến động sau thời điểm đo.

**Câu 10.** Hai lần gọi getTotal/getFree có phải snapshot nguyên tử không?

**Đáp án:** Không có cam kết như vậy. Các số có thể đổi giữa hai lời gọi.

**Câu 11.** `ManagementFactory.getPlatformMXBean(...)` có thể trả `null` không?

**Đáp án:** Có, nếu platform MXBean interface không được triển khai. Ngoài ra nếu runtime thiếu cả `jdk.management` thì dependency code có thể không nạp được, nên cần tạo runtime đúng module.

**Câu 12.** `MemoryMXBean.getHeapMemoryUsage().getUsed()` có đo cùng thứ với `total-free` không?

**Đáp án:** Không. Nó đo JVM heap usage. Hai metric phải được đặt tên riêng và dùng đúng phạm vi.

**Câu 13.** Vì sao chương trình mẫu in `example.usedGiB=6.00` cố định nhưng `environment.totalMiB` biến đổi?

**Đáp án:** Hai dòng example lấy số giả lập, còn environment đọc memory của OS/VM/container thực tại thời điểm chạy.

**Câu 14.** Dùng hai API này để tự động đặt `-Xmx` dựa vào total có đủ không?

**Đáp án:** Không. JVM còn non-heap/native memory, giới hạn container, yêu cầu workload và dư địa an toàn. Cần resource budgeting và thử nghiệm đầy đủ.

## 12. Tài liệu tham khảo chính thức và tài liệu vận hành

- [Oracle Java SE 17 — com.sun.management.OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): hai method `Since: 14`, định nghĩa byte, môi trường native/virtual/container.
- [Oracle Java SE 26 — com.sun.management.OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): xác nhận cả hai vẫn được hỗ trợ, hai tên cũ đã deprecated.
- [Oracle Java SE 17 — ManagementFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html): lấy platform MXBeans và khả năng trả `null`.
- [Oracle Java SE 17 — java.lang.management.OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html): phân biệt interface cơ bản.
- [Oracle Java SE 17 — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/non-heap memory.
- [Oracle Java SE 17 — Runtime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `freeMemory()`, `totalMemory()`, `maxMemory()`.
- [Oracle Java SE 17 — MemoryUsage](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html): used/committed/max của heap.
- [Red Hat Developer — Java 17: OpenJDK container awareness](https://developers.redhat.com/articles/2022/04/19/java-17-whats-new-openjdks-container-awareness): cách OpenJDK quan sát giới hạn tài nguyên trong Linux container/cgroup.

**Tổng kết:** `getFreeMemorySize()` và `getTotalMemorySize()` của `com.sun.management.OperatingSystemMXBean` (Java 14+) đo **free/total memory của môi trường chạy JVM**, theo **byte**. Hãy đổi đơn vị chính xác, xác nhận phạm vi host/VM/container, lấy mẫu hợp lệ và **không nhầm với Java heap, `-Xmx`, process RSS hay cam kết allocation thành công**.