# OperatingSystemMXBean mở rộng trong mô-đun jdk.management

## 1. Mục tiêu: quan sát CPU và tài nguyên hệ điều hành của JVM bằng API hiện hành

Trong một dịch vụ Java, các câu hỏi vận hành thường gặp gồm:

- JVM đang chạy trên môi trường nào và được cung cấp bao nhiêu bộ xử lý?
- Mức sử dụng CPU gần đây của **môi trường chạy** khác mức sử dụng CPU của **riêng tiến trình JVM** như thế nào?
- Hệ điều hành hoặc container báo bao nhiêu bộ nhớ tổng và bộ nhớ còn trống?
- Swap space còn bao nhiêu, tiến trình đã tiêu thụ bao nhiêu CPU time?
- Giá trị nào có thể **không được hỗ trợ** và phải hiển thị là N/A?
- Khi chạy trong container hoặc máy ảo, các số đo có nhất thiết đại diện cho toàn bộ máy chủ vật lý không?

Java Management Extensions (JMX) có giao diện tiêu chuẩn `java.lang.management.OperatingSystemMXBean` để đọc thông tin cơ bản. **JDK** mở rộng giao diện đó bằng `com.sun.management.OperatingSystemMXBean` thuộc mô-đun **`jdk.management`**, bổ sung những số liệu tài nguyên hữu ích cho theo dõi hệ thống.

Điểm quan trọng: có **hai giao diện cùng tên đơn giản** nhưng ở **hai package và module khác nhau**. API mở rộng là **API công khai, được tài liệu JDK mô tả**, không đồng nghĩa với các lớp nội bộ `sun.*`. Tuy nhiên, vì nó là **JDK-specific extension**, không nên giả định mọi Java runtime tối giản hoặc mọi triển khai JVM đều có cùng mô-đun và hỗ trợ mọi số đo.

Bài học tập trung vào cách sử dụng **còn áp dụng trên Java 17, 21, 25 và các bản hiện đại**. Những phương thức đã bị deprecated được chỉ rõ **để tránh gọi trong mã mới**, không dùng làm ví dụ chính.

## 2. Phân biệt giao diện chuẩn và giao diện mở rộng

| Nội dung | API Java chuẩn | API mở rộng JDK |
| --- | --- | --- |
| Tên đầy đủ | `java.lang.management.OperatingSystemMXBean` | `com.sun.management.OperatingSystemMXBean` |
| Module | `java.management` | `jdk.management` |
| Vai trò | Tên OS, kiến trúc, version, processor count, load average | Thêm CPU usage, CPU time, bộ nhớ, swap và committed virtual memory |
| Quan hệ | Interface nền tảng của MXBean | **Kế thừa** interface tiêu chuẩn |
| Tính portable | Định nghĩa bởi Java SE | Phụ thuộc JDK/triển khai/nền tảng |
| Cách lấy | `ManagementFactory.getOperatingSystemMXBean()` | Kiểm tra kiểu rồi cast, hoặc lấy platform bean theo interface mở rộng |

Ví dụ về quan hệ kế thừa:

~~~text
java.management
  java.lang.management.OperatingSystemMXBean
       |
       +-- jdk.management
             com.sun.management.OperatingSystemMXBean
                  |
                  +-- com.sun.management.UnixOperatingSystemMXBean
                      (giao diện tùy chọn trên nền tảng Unix)
~~~

`ManagementFactory.getOperatingSystemMXBean()` trả về kiểu giao diện **chuẩn** ở thời điểm biên dịch. Để gọi phương thức bổ sung như `getProcessCpuLoad()`, cần một tham chiếu được khai báo theo **giao diện mở rộng**.

Mô-đun `jdk.management` **exports package `com.sun.management`** và có phụ thuộc `requires transitive java.management`. Vì đây là một package được xuất công khai, code sử dụng bình thường **không cần `--add-exports` hoặc truy cập reflection vào lớp nội bộ JVM**.

### API cơ bản có gì?

Interface tiêu chuẩn định nghĩa:

- `getName()`: tên OS của môi trường JVM đang chạy.
- `getArch()`: kiến trúc OS.
- `getVersion()`: phiên bản OS.
- `getAvailableProcessors()`: số processor **có sẵn cho JVM**, ít nhất 1; giá trị có thể thay đổi trong khi JVM chạy.
- `getSystemLoadAverage()`: load average gần đây (thường là trung bình 1 phút); trả số âm nếu nền tảng không hỗ trợ.

**Load average không phải CPU percentage.** Số load average có thể lớn hơn 1 và phản ánh cơ chế hàng đợi/runnable của OS; không được nhân 100 rồi gọi đó là phần trăm CPU. Cũng không được giả định nó khả dụng trên Windows.

## 3. Lấy MXBean mở rộng một cách an toàn

Cách dễ đọc, xử lý được tình huống implementation không có extension:

~~~java
import java.lang.management.ManagementFactory;
import com.sun.management.OperatingSystemMXBean;

java.lang.management.OperatingSystemMXBean standard =
        ManagementFactory.getOperatingSystemMXBean();

if (standard instanceof OperatingSystemMXBean extended) {
    double cpuLoad = extended.getCpuLoad();
    long totalMemory = extended.getTotalMemorySize();
    // Xử lý số đo; luôn kiểm tra giá trị không khả dụng khi cần.
} else {
    // Runtime hiện tại không cung cấp extension như mong đợi.
}
~~~

Đây là **mảnh mã tích hợp**, không phải class hoàn chỉnh. Dùng `instanceof` pattern matching trên Java 17+. Dòng khai báo `java.lang.management.OperatingSystemMXBean` viết **tên đầy đủ** để tránh nhầm giao diện chuẩn với `com.sun.management.OperatingSystemMXBean`.

Không nên viết:

~~~java
OperatingSystemMXBean extended =
    (OperatingSystemMXBean) ManagementFactory.getOperatingSystemMXBean();
~~~

rồi mặc định cast **luôn đúng** trên bất kỳ runtime Java nào. Trên các JDK thông dụng, implementation thực tế hỗ trợ extension, nhưng code thư viện muốn portable nên **kiểm tra `instanceof` hoặc kết quả API lấy bean tương ứng**.

Một cách khác khi biết runtime hỗ trợ platform interface này:

~~~java
com.sun.management.OperatingSystemMXBean os =
        ManagementFactory.getPlatformMXBean(
            com.sun.management.OperatingSystemMXBean.class);
if (os != null) {
    System.out.println(os.getProcessCpuTime());
}
~~~

Đây cũng là **mảnh mã**. `ManagementFactory.getPlatformMXBean(Class)` cho một MXBean đơn; trên runtime không có implementation phù hợp, cần xử lý trường hợp không lấy được bean thay vì coi dữ liệu chắc chắn tồn tại.

**ObjectName chuẩn trong platform MBeanServer** là:

~~~text
java.lang:type=OperatingSystem
~~~

`extended.getObjectName()` trả về tên đối tượng JMX này; đó **không** phải tên hệ điều hành và **không** phải tên một process cụ thể.

## 4. Bảng các phép đo mở rộng đang được khuyến nghị

Các phương thức dưới đây là những API công khai của `com.sun.management.OperatingSystemMXBean` trong JDK hiện hành:

| Phương thức | Kiểu / đơn vị | Ý nghĩa | Điều cần kiểm tra |
| --- | --- | --- | --- |
| `getCpuLoad()` | `double`, tỷ lệ [0,1] | CPU usage gần đây của môi trường hoạt động | Giá trị âm = không có số đo; thời gian lấy mẫu không cố định |
| `getProcessCpuLoad()` | `double`, tỷ lệ [0,1] | CPU usage gần đây của tiến trình JVM | Giá trị âm = không có số đo; gồm cả JVM internal threads |
| `getProcessCpuTime()` | `long`, nanosecond | CPU time tích lũy của tiến trình JVM | `-1` khi không hỗ trợ; precision khác accuracy |
| `getTotalMemorySize()` | `long`, byte | Tổng dung lượng bộ nhớ theo môi trường OS/JVM | Không đồng nghĩa với max heap hay luôn là host physical RAM |
| `getFreeMemorySize()` | `long`, byte | Dung lượng bộ nhớ còn trống của môi trường | Không phải `Runtime.freeMemory()` |
| `getTotalSwapSpaceSize()` | `long`, byte | Dung lượng swap tổng | 0 có thể hợp lệ; không tự kết luận lỗi |
| `getFreeSwapSpaceSize()` | `long`, byte | Swap còn trống | Đánh giá cùng total swap và đặc thù OS |
| `getCommittedVirtualMemorySize()` | `long`, byte | Bộ nhớ ảo đã commit/được bảo đảm cho tiến trình | `-1` nếu không hỗ trợ; **không phải RSS** |

Ngoài ra, các phương thức **kế thừa** từ giao diện chuẩn như `getAvailableProcessors()`, `getName()`, `getArch()`, `getSystemLoadAverage()` vẫn gọi được qua interface mở rộng.

**Ba tên cũ không nên dùng cho code mới** (đều deprecated từ Java 14):

| Tên không còn khuyến nghị | Phương thức thay thế hiện hành |
| --- | --- |
| `getSystemCpuLoad()` | **`getCpuLoad()`** |
| `getFreePhysicalMemorySize()` | **`getFreeMemorySize()`** |
| `getTotalPhysicalMemorySize()` | **`getTotalMemorySize()`** |

Việc thay tên nhấn mạnh rằng môi trường đo có thể là **OS native, máy ảo hoặc container**, không nhất thiết là toàn bộ bộ nhớ vật lý của máy chủ. Tài liệu JDK hiện đại vẫn mô tả các phương thức thay thế kể trên; không nên đưa những tên deprecated vào đoạn code mẫu chính.

## 5. Hiểu đúng CPU usage: 0..1 không phải phần trăm đã nhân 100

### 5.1. `getCpuLoad()`

Phương thức trả về mức CPU usage **gần đây** của môi trường mà JVM hoạt động:

- `0.0`: CPU đang rảnh trong khoảng quan sát.
- `1.0`: toàn bộ năng lực CPU được đo đang bận.
- `0.25`: tương ứng 25% mức sử dụng theo cách chuẩn hóa của metric.
- **Giá trị âm**: không có số đo khả dụng theo implementation.

Nếu muốn hiển thị phần trăm:

~~~java
double load = os.getCpuLoad();
String display = load < 0
        ? "N/A"
        : String.format(java.util.Locale.ROOT,
                        "%.1f%%", load * 100.0);
~~~

Đây là **mảnh code** trong một phương thức có biến `os` kiểu extension bean. Với dashboard thực, nên kiểm tra `Double.isFinite(load)` và `load <= 1.0` để phát hiện giá trị bất thường.

**Không lấy mẫu một lần rồi gọi là “CPU tại đúng mili giây này”.** Tài liệu mô tả CPU load là **recent CPU usage** và khoảng thời gian quan sát do implementation quyết định; lần gọi đầu có thể chưa có cửa sổ quan sát xác định.

### 5.2. `getProcessCpuLoad()`

Phương thức trả tỷ lệ CPU usage gần đây của **tiến trình JVM**, bao gồm:

- Application threads.
- JVM internal threads (GC, JIT, runtime services...).
- Mức CPU của **cả process**, không phải của một `Thread` duy nhất.

Giá trị được chuẩn hóa theo năng lực CPU của môi trường. Vì thế **không** cộng tỷ lệ này với `getCpuLoad()` rồi coi đó là CPU usage tổng; hai metric có **phạm vi khác nhau**.

Một nguyên tắc hiển thị:

~~~java
double processLoad = os.getProcessCpuLoad();
if (processLoad < 0) {
    System.out.println("JVM CPU: N/A");
} else {
    System.out.printf(java.util.Locale.ROOT,
            "JVM CPU: %.1f%%%n", processLoad * 100.0);
}
~~~

Đây là **mảnh code**. Output số phần trăm thay đổi theo workload, số CPUs, JDK và container; không có stdout số cố định đáng tin cho ví dụ này.

### 5.3. Những người gọi khác có thể ảnh hưởng khoảng quan sát

Javadoc lưu ý nhiều callers của `getCpuLoad()` hoặc `getProcessCpuLoad()` **có thể ảnh hưởng khoảng thời gian tính toán và giá trị quan sát**. Ví dụ một agent APM, Java Mission Control hoặc dashboard cũng thăm dò bean, khi đó không nên tưởng số đo luôn độc lập với lịch polling của code bạn.

Không gọi CPU-load getter trong **vòng lặp tight loop** hàng trăm nghìn lần/giây để “lấy kết quả chính xác hơn”; vừa lãng phí việc gọi hệ thống vừa có thể tạo các khoảng đo rất ngắn, nhiễu hoặc khó hiểu. Chọn chu kỳ thăm dò phù hợp với mục đích, chẳng hạn vài giây cho dashboard vận hành.

## 6. CPU time là giá trị tích lũy, không phải CPU percentage

`getProcessCpuTime()` trả **CPU time của process JVM**, đơn vị **nanosecond**.

CPU time là tổng khoảng thời gian CPU phục vụ các threads của process; nó **không phải wall-clock elapsed time**. Trong JVM có nhiều threads cùng chạy trên nhiều CPU cores, lượng CPU time tăng trong một giây wall-clock **có thể lớn hơn một giây CPU**.

Ví dụ:

~~~java
long cpuTimeNs = os.getProcessCpuTime();
if (cpuTimeNs < 0) {
    System.out.println("CPU time unavailable");
} else {
    double seconds = cpuTimeNs / 1_000_000_000.0;
    System.out.println("Process CPU seconds: " + seconds);
}
~~~

Đây là **mảnh code**; số giây được in tùy thời gian chạy và workload.

Tài liệu nêu thời gian trả về có **độ phân giải nanosecond**, nhưng **độ chính xác thực tế không nhất thiết đến từng nanosecond**. Không dùng nó như đồng hồ độ chính xác nano để đo độ trễ của một lời gọi đơn lẻ.

### So sánh hai mẫu CPU time

Giả sử hai mẫu được lấy tại thời điểm `t0`, `t1`, với thời gian CPU `cpu0`, `cpu1`:

~~~text
deltaCpuNs = cpu1 - cpu0
deltaWallNs = wall1 - wall0

averageCpuCoreEquivalent = deltaCpuNs / deltaWallNs
~~~

Tỷ lệ này có thể **lớn hơn 1** nếu tiến trình sử dụng nhiều cores đồng thời. Để ước lượng phần năng lực CPU được cấp, đôi khi người ta chia thêm cho số CPUs có sẵn, nhưng cách chuẩn hóa/quotas/container settings có thể thay đổi. **Đừng tự khẳng định phép tính từ CPU time chính xác bằng `getProcessCpuLoad()`**: API đó có quy tắc lấy mẫu và chuẩn hóa implementation-specific.

Mã kiểu sau chỉ mang ý nghĩa **ước lượng**:

~~~java
long cpuBefore = os.getProcessCpuTime();
long wallBefore = System.nanoTime();

// Công việc diễn ra tại đây; tránh sửa biến của producer/consumer.
Thread.sleep(200);

long wallAfter = System.nanoTime();
long cpuAfter = os.getProcessCpuTime();

if (cpuBefore >= 0 && cpuAfter >= cpuBefore
        && wallAfter > wallBefore) {
    double coreEquivalent =
            (cpuAfter - cpuBefore) /
            (double) (wallAfter - wallBefore);
    System.out.printf(java.util.Locale.ROOT,
            "Approx. CPU cores: %.3f%n", coreEquivalent);
}
~~~

Đây là **mảnh code trong phương thức khai báo `throws InterruptedException`**. `System.nanoTime()` được dùng để đo chênh lệch wall time, không phải để lấy timestamp UTC. Nếu CPU time không khả dụng hoặc thời gian đo quá ngắn, không tự ghi kết quả giả.

## 7. Total/free memory: bộ nhớ môi trường khác Java heap

Phương thức hiện hành:

~~~java
long totalBytes = os.getTotalMemorySize();
long freeBytes = os.getFreeMemorySize();
~~~

Nó cho thông tin về bộ nhớ được báo từ **môi trường hoạt động của JVM**. Trong container/máy ảo, môi trường đó có thể có hạn mức riêng, không phải toàn bộ RAM vật lý của host.

**Không nhầm với bộ nhớ heap Java:**

| Câu hỏi | Nên dùng |
| --- | --- |
| Môi trường OS/container báo tổng/free memory ra sao? | `OperatingSystemMXBean.getTotalMemorySize()/getFreeMemorySize()` |
| JVM hiện dùng/cam kết bao nhiêu Java heap? | `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage()` |
| Heap được JVM khai báo tối đa bao nhiêu? | `MemoryUsage.getMax()` hoặc `Runtime.maxMemory()`, theo ngữ cảnh |
| Bộ nhớ off-heap, direct buffers, metaspace? | Các `MemoryPoolMXBean`/`BufferPoolMXBean` phù hợp, kết hợp công cụ quan sát |
| Process resident set size (RSS) chính xác? | **Không** được cung cấp trực tiếp bởi `getCommittedVirtualMemorySize()`; cần metric OS/agent phù hợp |

Ví dụ hai giá trị có thể **khác nhau rất nhiều**:

- `getTotalMemorySize()` đo bộ nhớ của môi trường OS/container.
- `getHeapMemoryUsage().getMax()` đo giới hạn heap.
- `getCommittedVirtualMemorySize()` liên quan committed virtual memory của **tiến trình**.
- RSS phản ánh các trang bộ nhớ thực cư trú theo cơ chế OS.

**Không cộng/trừ tùy ý** các giá trị này để suy ra “RAM thật còn lại” hay “đã dùng bao nhiêu heap”. Phải hiểu phạm vi riêng của từng metric.

### MiB và MB không giống nhau

Các getter bộ nhớ trả về **byte**. Đổi ra MiB:

~~~java
double mib = totalBytes / (1024.0 * 1024.0);
~~~

`MiB = 2^20 bytes`, trong khi `MB = 10^6 bytes`. Khi báo cáo/chốt ngưỡng, cần nhất quán đơn vị. **Không gán byte vào `int`**, vì bộ nhớ thực tế có thể vượt 2 GiB; giữ kiểu `long`.

Không nên tính “% memory used” bằng `(total-free)/total` nếu chưa kiểm tra **total > 0**, giá trị không khả dụng và cách OS định nghĩa free/cached/available; đó chỉ là một proxy theo loại metric, không thay cho thông số memory pressure chính thức.

## 8. Swap và committed virtual memory

### 8.1. Swap space

~~~java
long totalSwap = os.getTotalSwapSpaceSize();
long freeSwap = os.getFreeSwapSpaceSize();
~~~

Hai getter trả byte. Trên một máy/VM/container **không có swap được cấu hình**, tổng swap có thể là **0**, và điều này không tự động là lỗi API.

Một cách diễn giải thận trọng:

- `totalSwap = 0`: hệ điều hành báo không có swap theo phạm vi metric này.
- `freeSwap = totalSwap`: không có swap đã dùng theo số đo được cung cấp, nếu phạm vi/điều kiện hệ thống phù hợp.
- `freeSwap < totalSwap`: có sự khác biệt giữa tổng và free, nhưng không nên gán toàn bộ chênh lệch đó cho **riêng JVM**.

**Không dùng swap total/free như số liệu trực tiếp về Java heap hoặc CPU.** Hệ điều hành có thể swap dữ liệu của các tiến trình khác; cách thể hiện trong container cũng tùy platform.

### 8.2. Committed virtual memory

~~~java
long committedBytes = os.getCommittedVirtualMemorySize();
if (committedBytes < 0) {
    // Không hỗ trợ trên môi trường hiện tại.
}
~~~

Theo Javadoc, đây là **lượng virtual memory được bảo đảm sẵn cho tiến trình**, tính bằng byte, hoặc `-1` nếu operation không được hỗ trợ.

Không nên suy ra:

- Đây là **Java heap đã sử dụng**.
- Đây là **RSS (resident set size)**.
- Đây là **lượng bộ nhớ vật lý thật đang chiếm**.
- Đây là **mức bộ nhớ còn có thể cấp phát** cho ứng dụng.

Một process có thể có nhiều vùng địa chỉ ảo được map/commit mà không đồng nhất với số trang vật lý đang cư trú. Muốn phân tích OOM/native memory pressure, cần ghép nhiều số liệu đúng phạm vi.

## 9. Ví dụ Java 17+ chạy độc lập: kiểm tra MXBean và khả năng có dữ liệu

Đo số liệu hệ thống thì giá trị CPU/memory **không thể có stdout cố định giữa các máy**. Vì vậy chương trình dưới đây chủ yếu in:

- MXBean chuẩn có tồn tại không.
- Package/module của interface mở rộng.
- ObjectName của bean.
- Các **trạng thái có số đo/không có số đo**.
- Một vài kiểm tra sanity, thay vì cố định CPU/RAM bằng những số giả.

Ví dụ đã được **biên dịch với target Java 17** và chạy thử trên **Azul OpenJDK 24.0.2/Windows**.

Tạo file **`ExtendedOsMxBeanDemo.java`** (UTF-8):

~~~java
import java.lang.management.ManagementFactory;
import com.sun.management.OperatingSystemMXBean;

public class ExtendedOsMxBeanDemo {
    private static String bytesStatus(long value) {
        return value < 0 ? "unavailable" : "available";
    }

    private static String loadStatus(double value) {
        if (value < 0) return "unavailable";
        return Double.isFinite(value) && value <= 1.0
                ? "available" : "unexpected";
    }

    public static void main(String[] args) {
        java.lang.management.OperatingSystemMXBean standard =
                ManagementFactory.getOperatingSystemMXBean();
        System.out.println("standard-bean=" + (standard != null));
        System.out.println("extension-module=" +
                OperatingSystemMXBean.class.getModule().getName());

        if (!(standard instanceof OperatingSystemMXBean os)) {
            System.out.println("extended-bean=false");
            return;
        }

        System.out.println("extended-bean=true");
        System.out.println("object-name=" + os.getObjectName());
        System.out.println("processors-positive=" +
                (os.getAvailableProcessors() >= 1));

        long total = os.getTotalMemorySize();
        long free = os.getFreeMemorySize();
        System.out.println("total-memory-status=" +
                bytesStatus(total));
        System.out.println("free-memory-status=" +
                bytesStatus(free));
        System.out.println("free-not-greater-than-total=" +
                (total >= 0 && free >= 0 && free <= total));

        System.out.println("system-cpu-load-status=" +
                loadStatus(os.getCpuLoad()));
        System.out.println("process-cpu-load-status=" +
                loadStatus(os.getProcessCpuLoad()));
        System.out.println("process-cpu-time-status=" +
                bytesStatus(os.getProcessCpuTime()));
        System.out.println("swap-total-status=" +
                bytesStatus(os.getTotalSwapSpaceSize()));
        System.out.println("swap-free-status=" +
                bytesStatus(os.getFreeSwapSpaceSize()));
        System.out.println("committed-virtual-memory-status=" +
                bytesStatus(os.getCommittedVirtualMemorySize()));

        double average = os.getSystemLoadAverage();
        System.out.println("one-minute-load-average-status=" +
                (average < 0 ? "unavailable" : "available"));
    }
}
~~~

Lệnh biên dịch và chạy bằng JDK 17+:

~~~bash
javac --release 17 --add-modules jdk.management -encoding UTF-8 ExtendedOsMxBeanDemo.java
java --add-modules jdk.management ExtendedOsMxBeanDemo
~~~

Lệnh này **đã chạy thành công** với OpenJDK 24, target Java 17 và module được chỉ rõ. Tùy runtime, nhiều môi trường classpath có thể tự resolve module, nhưng chỉ định `--add-modules jdk.management` giúp bài học rõ ràng và tránh dựa vào module roots mặc định.

**Stdout đã quan sát trên Azul OpenJDK 24.0.2/Windows:**

~~~text
standard-bean=true
extension-module=jdk.management
extended-bean=true
object-name=java.lang:type=OperatingSystem
processors-positive=true
total-memory-status=available
free-memory-status=available
free-not-greater-than-total=true
system-cpu-load-status=available
process-cpu-load-status=available
process-cpu-time-status=available
swap-total-status=available
swap-free-status=available
committed-virtual-memory-status=available
one-minute-load-average-status=unavailable
~~~

**Đây là đầu ra kiểm chứng của máy thử nghiệm, KHÔNG phải kết quả cố định cho mọi OS/JDK.** Chẳng hạn:

- `getSystemLoadAverage()` trên Windows thử nghiệm trả số âm, nên dòng cuối ghi `unavailable`; trên Linux có thể là `available`.
- Hai CPU load getters có thể trả số âm khi chưa đủ dữ liệu hoặc hệ thống không hỗ trợ phép đo.
- `free-not-greater-than-total=true` chỉ là một **sanity check** theo hai giá trị đọc liên tiếp, không phải một invariant tuyệt đối. Các số đo **không được lấy từ một snapshot nguyên tử**, nên thay đổi giữa hai lời gọi có thể khiến so sánh không đúng trong một số môi trường.
- Runtime không triển khai `com.sun.management.OperatingSystemMXBean` có thể in `extended-bean=false` rồi kết thúc.
- Vì chương trình biên dịch **trực tiếp** với module JDK-specific, một runtime thiếu module này sẽ không tải được code; việc kiểm tra `instanceof` chỉ giúp xử lý thiếu *implementation*, không thể thay cho việc có module cần thiết lúc runtime.

### Giải thích các dòng quan trọng

`OperatingSystemMXBean.class.getModule().getName()` trả `jdk.management`, chứng minh interface mở rộng đến từ module đúng.

`os.getObjectName()` cho object name JMX tiêu chuẩn `java.lang:type=OperatingSystem`. Dùng object name này trong platform MBeanServer khi làm công cụ monitoring/JMX.

`bytesStatus` chuyển giá trị âm thành nhãn không khả dụng trong demo. Với getter có hợp đồng riêng (chẳng hạn `getProcessCpuTime`/`getCommittedVirtualMemorySize` quy định `-1`), code production nên dựa vào **tài liệu riêng của từng phép đo**, không giả định mọi getter đều có sentinel đồng nhất.

`loadStatus` xử lý tỷ lệ CPU load âm/không hữu hạn/ngoài [0,1]. Nếu triển khai cung cấp giá trị âm, không hiển thị phần trăm âm hoặc coi `-1` là “-100% CPU”.

Chương trình chỉ đọc thông tin, không thiết lập JMX remote agent, không tự bật cổng mạng và không cần quyền ghi file.

## 10. Cách in giá trị thô để xuất metrics

Bài demo dùng trạng thái cho stdout dễ đối chiếu. Trong ứng dụng vận hành, cần lấy **số thật**:

~~~java
static String toMiB(long bytes) {
    if (bytes < 0) return "N/A";
    return String.format(java.util.Locale.ROOT,
            "%.2f MiB", bytes / (1024.0 * 1024.0));
}

static String toPercent(double ratio) {
    if (!Double.isFinite(ratio) || ratio < 0 || ratio > 1) {
        return "N/A";
    }
    return String.format(java.util.Locale.ROOT,
            "%.1f%%", ratio * 100.0);
}
~~~

Đây là **hai phương thức hỗ trợ**, có thể đặt trong cùng class với main. Kết quả là chuỗi cho người đọc; nếu gửi đến telemetry system, nên giữ **giá trị số nguyên byte hoặc tỷ lệ 0..1** và gắn nhãn đơn vị qua schema của hệ thống metric.

Ví dụ dùng:

~~~java
System.out.println("os-memory=" +
        toMiB(os.getTotalMemorySize()));
System.out.println("free-memory=" +
        toMiB(os.getFreeMemorySize()));
System.out.println("cpu-load=" +
        toPercent(os.getCpuLoad()));
System.out.println("jvm-cpu-load=" +
        toPercent(os.getProcessCpuLoad()));
~~~

Mảnh này giả định `os` là bean mở rộng và hai hàm helper đã được khai báo. **Các con số được in thay đổi theo thời gian**, vì vậy không cung cấp “stdout chính xác” giả cho phần này.

### Không đọc sai đơn vị

- CPU load `0.5` nghĩa là **50% theo metric CPU ratio**, không phải 0.5%.
- Memory getter trả **bytes**, không phải KiB/MiB/MB.
- Process CPU time trả **nanoseconds**, không phải milliseconds.
- Load average **không phải CPU percentage**; không nhân 100.
- `getAvailableProcessors()` là số processor có sẵn cho JVM, không nhất thiết là số core vật lý toàn máy.
- Committed virtual memory không phải RSS, không phải Java heap used.

Khi xây dashboard, nên thêm `source=jvm`, `scope=process/environment` và đơn vị rõ ràng. Không sử dụng một nhãn mơ hồ như `memory` cho mọi loại bộ nhớ.

## 11. Tạo monitoring loop: lấy mẫu thay vì chụp một lần

Một bản báo cáo đơn lẻ mô tả **thời điểm được lấy**, không cho biết xu hướng. Để phát hiện CPU tăng hoặc memory pressure, cần quan sát nhiều mẫu theo thời gian.

Mẫu tổ chức:

~~~java
for (int i = 0; i < 5; i++) {
    double processLoad = os.getProcessCpuLoad();
    long freeMemory = os.getFreeMemorySize();

    // Gửi số liệu kèm timestamp, source và đơn vị.
    // Không ghi số âm như phần trăm CPU hợp lệ.
    if (processLoad >= 0 && Double.isFinite(processLoad)) {
        exportCpuRatio(processLoad);
    }
    if (freeMemory >= 0) {
        exportFreeMemoryBytes(freeMemory);
    }

    Thread.sleep(1000);
}
~~~

Đây là **mảnh mã minh họa**:

- `os` là bean đã lấy.
- `exportCpuRatio/exportFreeMemoryBytes` là hàm của hệ thống metrics, không có sẵn trong JDK.
- Phương thức bao quanh cần xử lý hoặc khai báo `InterruptedException`.
- Giá trị 1 giây chỉ là chu kỳ minh họa; chọn tần suất đo dựa trên nhu cầu và chi phí thực tế.

Điều cần thiết kế:

1. **Timestamp rõ ràng**: ghi thời gian lấy mẫu, đừng cho rằng các getters cùng một thời điểm nguyên tử.
2. **Hạn chế tần suất**: polling nhanh vô hạn tạo overhead và nhiễu.
3. **Giá trị không khả dụng**: lưu N/A/missing sample theo hợp đồng, không tự thay bằng 0.
4. **Khác scope**: process CPU load so với environment CPU load là hai series khác nhau.
5. **Startup**: một vài mẫu đầu có thể chưa đủ thông tin; đừng alert từ một mẫu đầu duy nhất.
6. **Biến động cấu hình**: `getAvailableProcessors()` và limit container có thể thay đổi khi ứng dụng chạy.
7. **An toàn luồng**: nếu nhiều consumers cùng gọi CPU metrics, có thể ảnh hưởng cửa sổ quan sát.
8. **Giám sát dài hạn**: cần dùng telemetry pipeline phù hợp, retention và quyền truy cập thay vì tự in thông tin chi tiết lên console công khai.

### Alert nên có quy tắc ổn định

Không tạo alert “CPU high” chỉ vì `getProcessCpuLoad() > 0.8` **một lần duy nhất**. Nên dùng nhiều mẫu, duration và workload context; có thể phối hợp với JVM GC, request latency, queue depth và container metrics.

CPU cao không đồng nghĩa JVM thiếu heap; swap cao không chứng minh ứng dụng Java là nguyên nhân. Đọc các số đo trong bối cảnh.

## 12. JVM trong container hoặc máy ảo: không mặc định số liệu là toàn host

Javadoc mô tả operating environment có thể là:

- Native operating system.
- Virtualized operating system environment.
- Container-managed environment.

Điều này đặc biệt quan trọng với Docker, Kubernetes hoặc PaaS. Nếu process có CPU quota hay memory limit riêng, việc lấy số liệu từ runtime/JDK cần được diễn giải theo **giới hạn mà JVM và hệ điều hành cung cấp**.

Một số nguyên tắc:

- **Không đồng nhất** `getTotalMemorySize()` với dung lượng RAM vật lý của node.
- **Không đồng nhất** `getAvailableProcessors()` với số hardware cores trên máy chủ.
- **Không so sánh** trực tiếp CPU ratio của app trong container với CPU ratio của node mà không kiểm tra scopes/quota.
- **Không khẳng định** mọi JDK/vendor/cgroup version hỗ trợ container metrics theo cùng cách; cách báo cáo phụ thuộc runtime, hệ điều hành, cgroup configuration và tùy chọn JVM.
- Khi điều tra OOMKilled, CPU throttling hoặc limit container, hãy ghép thêm **metrics do container runtime/orchestrator cung cấp**; OperatingSystemMXBean không phải API bao phủ toàn bộ cgroup.
- Khi phân phối custom runtime qua `jlink`, bảo đảm `jdk.management` có mặt nếu app cần API mở rộng.

Một phương thức `getTotalMemorySize()` có thể trả giá trị hợp lệ theo Java API nhưng **không mang ý nghĩa mà người quản trị nghĩ tới** nếu đang lấy số host memory thay vì container memory hoặc ngược lại. Dashboard cần ghi rõ phạm vi quan sát.

## 13. So sánh với các API metrics khác trong Java

| Nhu cầu | API phù hợp | Vì sao |
| --- | --- | --- |
| Tên OS, kiến trúc, processor count, load average | `java.lang.management.OperatingSystemMXBean` | Giao diện tiêu chuẩn, ít phụ thuộc JDK |
| CPU ratio JVM/process, CPU ratio environment | **`com.sun.management.OperatingSystemMXBean`** | Phần mở rộng của `jdk.management` |
| Process CPU time tích lũy | `getProcessCpuTime()` hoặc API khác phù hợp | Theo dõi tích lũy CPU process |
| Heap used/committed/max | `MemoryMXBean.getHeapMemoryUsage()` | Phạm vi là **heap JVM** |
| GC count và GC time | `GarbageCollectorMXBean` | Chẩn đoán GC |
| Threads JVM và deadlock | `ThreadMXBean` | Phân tích threads |
| Direct/mapped buffer pools | `BufferPoolMXBean` | Bộ nhớ buffer liên quan NIO |
| Số file descriptors mở trên Unix | `com.sun.management.UnixOperatingSystemMXBean` | Extension platform-specific; không có trên mọi OS |
| Cgroup, node CPU, RSS, IO throttling chi tiết | OS/container monitoring tools hoặc agent phù hợp | Những số liệu không được mọi MXBean cung cấp trực tiếp |

Đừng bắt `OperatingSystemMXBean` trả lời một câu hỏi ngoài chức năng của nó. Ví dụ để tìm heap leak, hãy xem `MemoryMXBean` và GC/allocation, không chỉ nhìn `getFreeMemorySize()`.

### UnixOperatingSystemMXBean chỉ là mở rộng có điều kiện

Trên những nền tảng hỗ trợ, `UnixOperatingSystemMXBean` có `getOpenFileDescriptorCount()` và `getMaxFileDescriptorCount()`. Khi dùng, cần guard:

~~~java
if (os instanceof com.sun.management.UnixOperatingSystemMXBean unix) {
    System.out.println("open-fd=" +
            unix.getOpenFileDescriptorCount());
}
~~~

Đây là **mảnh code**. Không áp dụng cast này vô điều kiện trên Windows. Số file descriptors do OS/JDK báo khác các khái niệm connection count hay Java stream count.

## 14. Dùng module trong ứng dụng modular hoặc runtime tùy chỉnh

### 14.1. Ứng dụng có module-info.java

Nếu ứng dụng là một Java module:

~~~java
module com.example.monitor {
    requires jdk.management;
}
~~~

Đây là **mảnh file `module-info.java`**, giả định có mã nguồn module `com.example.monitor`. Vì `jdk.management` phụ thuộc bắc cầu `java.management`, code trong module có thể dùng `ManagementFactory` và extension; khai báo `requires java.management` thêm chỉ khi muốn thể hiện dependency trực tiếp theo quy ước của dự án.

Không thêm `opens com.example.monitor to jdk.management` theo thói quen: đọc các getters công khai của MXBean **không yêu cầu mở package ứng dụng để reflection**.

### 14.2. App classpath và --add-modules

Với demo ở mục 9, lệnh rõ ràng:

~~~bash
javac --release 17 --add-modules jdk.management ExtendedOsMxBeanDemo.java
java --add-modules jdk.management ExtendedOsMxBeanDemo
~~~

Trên một JDK đầy đủ, thường có thể không cần `--add-modules` khi module nằm trong default roots của runtime classpath, nhưng khai báo tường minh làm rõ dependency. Không giải quyết lỗi thiếu module bằng `--add-exports java.base/sun...`: đó là hướng truy cập **internal API**, không cần thiết.

### 14.3. Runtime tạo bởi jlink

Nếu ứng dụng được đóng cùng runtime image tối giản, phải kiểm tra module có trong image:

~~~bash
jlink --add-modules java.base,jdk.management \
      --output monitor-runtime
~~~

Đây là **lệnh minh họa**, cần chạy bằng một JDK có `jlink`, với đủ modules và filesystem permissions. `jlink` tự liên kết các dependencies bắc cầu của root modules. Nếu không cắt native launcher, có thể kiểm tra:

~~~bash
monitor-runtime/bin/java --list-modules
~~~

Trong runtime đã được rút gọn mạnh hoặc đã `--strip-native-commands`, lệnh `bin/java` có thể vắng mặt; cần xem file `release`/toolchain build và thực thi app image để xác minh.

**Không nên khẳng định app chạy được với mọi “JRE” tối giản:** nếu runtime không có `jdk.management`, import class của extension có thể dẫn đến `ClassNotFoundException` hoặc lỗi liên kết class/module, trước khi code kịp kiểm tra `instanceof`. Hãy xác định dependency module ở **bước build/package**, không chỉ ở runtime.

## 15. JMX, công cụ giám sát và bảo mật

Platform MXBeans được đăng ký trong **platform MBeanServer**, có thể lấy bằng:

~~~java
javax.management.MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();
~~~

Đây là mảnh code với import `ManagementFactory`. ObjectName liên quan OperatingSystemMXBean là:

~~~text
java.lang:type=OperatingSystem
~~~

Các công cụ JMX/JConsole/Java Mission Control hoặc agent quan sát có thể đọc metadata/attributes theo cơ chế quản lý Java phù hợp.

**Quan trọng:** gọi `ManagementFactory.getOperatingSystemMXBean()` trong **cùng process** không tự động mở cổng remote JMX. Truy cập JMX từ một máy khác là câu chuyện **cấu hình remote connector**, kết nối mạng và bảo mật riêng.

Khi bật monitoring từ xa:

- Chỉ cấp quyền truy cập cho quản trị viên/agent được phép.
- Bật xác thực và mã hóa (TLS) theo hướng dẫn JDK và chính sách hạ tầng; không mở JMX RMI port công khai chỉ để nhìn CPU.
- Kiểm soát firewall, network policy, credentials, certificate và quyền của người dùng.
- Hạn chế ghi ra log công khai các thông tin OS/version/architecture, đường dẫn nội bộ và metadata chẩn đoán không cần thiết.
- Đánh giá tần suất polling và chi phí lưu/giữ số liệu theo chính sách.

Với nhu cầu chỉ đọc CPU/memory của **chính JVM**, trực tiếp gọi MXBean trong process thường đơn giản và ít bề mặt tấn công hơn việc bật một remote management endpoint.

## 16. Các lỗi phổ biến cần tránh

| Hiểu nhầm hoặc lỗi | Vì sao không đúng | Cách sửa |
| --- | --- | --- |
| Chỉ import `java.lang.management.OperatingSystemMXBean` rồi gọi `getCpuLoad()` | API chuẩn không định nghĩa phương thức mở rộng | Dùng `com.sun.management.OperatingSystemMXBean` từ `jdk.management` |
| Cast trực tiếp sang extension không kiểm tra | Runtime khác có thể không triển khai extension | `instanceof` hoặc lấy bean có kiểm tra |
| Dùng tên cũ cho CPU load | Các tên cũ đã deprecated từ Java 14 | Dùng **`getCpuLoad()`** |
| Dùng tên cũ cho total/free physical memory | Các tên cũ đã deprecated từ Java 14 | Dùng **`getTotalMemorySize()/getFreeMemorySize()`** |
| CPU `0.5` hiển thị “0.5%” | 0.5 là tỷ lệ | Nhân 100 để hiển thị 50% |
| CPU `-1` hiển thị “-100%” | Số âm nghĩa là không có phép đo | Hiển thị N/A/missing |
| `getSystemLoadAverage() = -1` là sự cố JVM | Nhiều OS không cung cấp chỉ số load average | Xử lý thiếu dữ liệu, không phát lỗi giả |
| Một lần gọi CPU load là thời điểm tức thời chính xác | Đây là recent usage với khoảng quan sát riêng | Lấy mẫu có chu kỳ và diễn giải như chuỗi thời gian |
| CPU time nanoseconds bị xem là milliseconds | Lệch đơn vị 10^6 lần | Lưu theo ns; đổi đơn vị có chủ đích |
| Lấy process CPU load làm CPU của một Java thread | Phạm vi process gồm nhiều threads | Dùng ThreadMXBean hoặc profiler nếu cần theo thread |
| Đọc free memory rồi gọi đó là free Java heap | OS/environment memory khác JVM heap | Dùng MemoryMXBean cho heap |
| Đọc committed virtual memory rồi gọi là RSS | Virtual commit khác resident memory | Dùng OS metrics nếu cần RSS |
| Coi total memory luôn bằng host RAM | JVM có thể chạy trong container/VM | Ghi rõ phạm vi và đối chiếu cgroup/OS |
| Lấy swap delta rồi khẳng định JVM dùng từng đó | Swap metric có phạm vi environment, không riêng process | Dùng process/container metrics phù hợp |
| Chia `(total-free)/total` mà không kiểm tra | Có thể gặp total không hợp lệ/0 và lệch snapshot | Validate mỗi giá trị và ý nghĩa của metric |
| Mở remote JMX không có xác thực/mã hóa | Rò rỉ monitoring data và tăng bề mặt tấn công | TLS/auth/network controls |
| Bỏ module jdk.management khỏi jlink image | Code có dependency vào interface này | Đảm bảo module được link vào runtime |
| Gọi getter liên tục để tăng “độ chính xác” | Polling nhanh có thể tạo overhead và nhiễu | Chọn chu kỳ có mục đích |

## 17. Quy trình đo và kiểm chứng trong production

### Bước 1 — Đặt câu hỏi rõ

Ví dụ: “JVM có bị CPU throttling ở tải cao?” hoặc “Môi trường container báo bao nhiêu memory free?”. Không nên bắt đầu bằng một dashboard có mọi getter nhưng không có phạm vi giải thích.

### Bước 2 — Chọn metric có đúng scope

- Chọn `getProcessCpuLoad()` nếu quan sát CPU của riêng JVM.
- Chọn `getCpuLoad()` nếu quan sát CPU của môi trường.
- Chọn `getProcessCpuTime()` cho CPU time tích lũy.
- Chọn `getTotalMemorySize()/getFreeMemorySize()` cho environment memory.
- Chọn `MemoryMXBean` cho heap.
- Chọn container/OS agent cho RSS/cgroup throttling nếu cần.

### Bước 3 — Kiểm tra availability

Mọi metric CPU ratio âm phải coi là **không có số đo**, không thay bằng 0. Với `getProcessCpuTime()` và `getCommittedVirtualMemorySize()`, xử lý `-1` theo Javadoc. Với các phép đo khác, xem hợp đồng tương ứng của JDK đang triển khai.

### Bước 4 — Quy định đơn vị và tần suất

Ghi rõ CPU ratio 0..1 hay percent 0..100, memory bytes hay MiB, CPU time ns hay seconds; chọn chu kỳ polling phù hợp.

### Bước 5 — Test trên máy đích

Thử trong JDK/vendor, OS, container, CPU quota và cấu hình memory limit thực tế. Đặc biệt test giá trị `getSystemLoadAverage` khi không hỗ trợ; tránh dùng bản ghi thử trên Linux để suy ra chắc chắn Windows cũng trả cùng dữ liệu.

### Bước 6 — Quan sát cùng số liệu khác

Kết hợp request latency, throughput, GC pause, heap usage, CPU throttling, queue depth và OS/container metrics để tránh kết luận sai nguyên nhân.

### Bước 7 — Vận hành bảo mật

Tránh xuất thông tin hệ thống không cần thiết; bảo vệ JMX remote endpoint và metrics store; định nghĩa alert/retention phù hợp.

## 18. Bài tập thực hành và đáp án

### Bài 1 — Chọn đúng interface

**Yêu cầu:** gọi `getProcessCpuLoad()`. Giao diện chuẩn `java.lang.management.OperatingSystemMXBean` có phương thức này không?

**Đáp án:** không. Nó thuộc **`com.sun.management.OperatingSystemMXBean`** trong `jdk.management`. Có thể lấy bean chuẩn rồi kiểm tra `instanceof`, hoặc lấy platform bean theo interface mở rộng.

### Bài 2 — Quy đổi CPU ratio

`getProcessCpuLoad()` trả `0.125`. Dashboard cần phần trăm.

**Đáp án:** `0.125 × 100 = 12.5%`. Nếu getter trả số âm, hiển thị N/A; không tự chuyển thành số âm phần trăm.

### Bài 3 — Phân biệt CPU load và load average

`getSystemLoadAverage()` trả `2.5`. Điều đó có phải “250% CPU usage” không?

**Đáp án:** không. Load average phản ánh mức tải/hàng đợi theo OS và không phải tỷ lệ 0..1 như `getCpuLoad()`. Cần diễn giải với số processor và đặc thù OS.

### Bài 4 — Process CPU time

Hai mẫu `getProcessCpuTime()` cách nhau 1 giây wall-clock có delta CPU time là 2 giây.

**Đáp án:** có thể hợp lệ nếu nhiều threads chạy trên nhiều cores. CPU time tích lũy không phải thời gian wall-clock của một thread.

### Bài 5 — OS memory và heap

`getTotalMemorySize()` báo 8 GiB nhưng Java heap max là 1 GiB. Kết quả có sai không?

**Đáp án:** không nhất thiết. Hai metric có **phạm vi khác nhau**: memory environment so với heap max; còn native memory, metaspace, page cache và các tiến trình khác.

### Bài 6 — Một MXBean trong container

Một service trong Kubernetes cần biết chính xác cgroup memory pressure và CPU throttling. `OperatingSystemMXBean` có đủ toàn bộ dữ liệu không?

**Đáp án:** không bảo đảm. Dùng nó để có góc nhìn hệ điều hành/JVM, kết hợp metrics của container runtime/cgroup/orchestrator cho yêu cầu cụ thể.

### Bài 7 — Giá trị không khả dụng

`getSystemLoadAverage()` trên Windows trả `-1`, `getProcessCpuLoad()` lúc khởi động cũng có thể âm.

**Đáp án:** phải lưu **N/A/missing**, không ghi thành 0 và không tạo alert lỗi chỉ từ một mẫu thiếu dữ liệu.

### Bài 8 — App image thiếu module

Một ứng dụng modular `requires jdk.management` được chạy trong runtime tối giản không chứa module đó.

**Đáp án:** runtime cần được xây lại với `jdk.management` và các dependencies. Không cố dùng `--add-exports` để thay thế module thiếu.

### Bài 9 — Kiểm chứng trên JDK hiện hành

Biên dịch/chạy `ExtendedOsMxBeanDemo.java` với lệnh ở mục 9. Quan sát:

- Module name là `jdk.management`.
- ObjectName là `java.lang:type=OperatingSystem`.
- Processors ít nhất 1.
- Những dòng `*-status` phản ánh dữ liệu thực, không mặc định mọi OS đều có đủ.
- Thử in các giá trị raw theo mục 10 và giải thích vì sao **không có stdout chung** cho CPU/memory.

## 19. Checklist kiến thức

1. Phân biệt **giao diện chuẩn** và **giao diện mở rộng** dù cùng tên.
2. Biết package `com.sun.management` nằm trong module `jdk.management`.
3. Chỉ dùng các getter hiện hành thay vì tên deprecated từ Java 14.
4. Biết `getCpuLoad/getProcessCpuLoad` trả **tỷ lệ 0..1 hoặc số âm**, không phải percent trực tiếp.
5. Biết `getProcessCpuTime` trả **ns**, không phải thời gian wall-clock.
6. Biết `getSystemLoadAverage` là load average, **không phải CPU percentage**.
7. Biết total/free memory khác Java heap và có thể phụ thuộc container.
8. Biết swap metrics không chỉ áp dụng riêng cho JVM.
9. Biết committed virtual memory không tương đương RSS.
10. Biết xử lý missing metrics theo Javadoc, không tự thay bằng 0.
11. Biết mô-đun phải được đóng vào runtime `jlink` nếu ứng dụng phụ thuộc extension.
12. Biết bảo vệ JMX nếu sử dụng monitoring từ xa.
13. Biết chạy thử trên JDK/OS/container thực tế và không dự đoán stdout số liệu động.

## 20. Tài liệu chính thức hiện còn áp dụng

- [Oracle JDK 25 — com.sun.management.OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): nguồn chuẩn cho CPU ratio, CPU time, total/free memory, swap, committed virtual memory và các phương thức đã deprecated từ Java 14.
- [Oracle JDK 17 — com.sun.management.OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): kiểm tra tên API và khả năng dùng trên Java 17+.
- [Oracle JDK 25 — java.lang.management.OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html): interface chuẩn, OS name/arch/version, availableProcessors và system load average.
- [Oracle JDK 25 — Module jdk.management](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/module-summary.html): xác định mô-đun chứa `com.sun.management` và phụ thuộc bắc cầu `java.management`.
- [Oracle JDK 25 — ManagementFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ManagementFactory.html): `getOperatingSystemMXBean`, `getPlatformMXBean` và platform MBeanServer.
- [Oracle JDK 25 — MemoryMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryMXBean.html): số liệu heap/non-heap của JVM, phân biệt với OS memory.
- [Oracle JDK 25 — UnixOperatingSystemMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/UnixOperatingSystemMXBean.html): file descriptor count trên nền tảng phù hợp.
- [Oracle JDK 17 — Monitoring and Management Using JMX](https://docs.oracle.com/en/java/javase/17/management/monitoring-and-management-using-jmx-technology.html): cách giám sát và yêu cầu xác thực/mã hóa khi bật remote JMX.
