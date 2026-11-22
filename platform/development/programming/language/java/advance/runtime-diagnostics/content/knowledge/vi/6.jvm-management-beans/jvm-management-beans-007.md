# 6.7 OperatingSystemMXBean: tải CPU, thời gian CPU và bộ nhớ của môi trường

Một dịch vụ Java có thể báo latency tăng vọt dù heap còn trống, một pod có thể bị CPU throttling dù số liệu %CPU trông không cao, hoặc JVM có thể bị OOMKilled trong khi `MemoryMXBean` cho thấy heap chưa chạm `-Xmx`. Để phân biệt các hiện tượng này, cần quan sát **tài nguyên của môi trường chạy và toàn bộ tiến trình JVM**, không chỉ các đối tượng Java trên heap.

`OperatingSystemMXBean` cung cấp một phần thông tin như số CPU khả dụng, load average; ở JDK 17 có phần mở rộng `com.sun.management.OperatingSystemMXBean` cho **CPU load, CPU time của tiến trình, RAM/swap và virtual memory**. Tuy nhiên, dữ liệu phụ thuộc hệ điều hành, JDK implementation, container/cgroup và thời điểm lấy mẫu. Một giá trị `0.75` không nói toàn bộ hệ thống “bận 75% vì Java”; một giá trị `-1` thường có nghĩa **không hỗ trợ hoặc chưa có mẫu**, không phải tải CPU âm.

**Mục tiêu bài học:** lấy đúng bean, đọc đúng đơn vị/phạm vi, tính CPU utilization từ hai mẫu CPU time, phân biệt load average với CPU %, tách bộ nhớ môi trường khỏi Java heap và RSS, kiểm chứng giới hạn container, và ghép các số liệu thành bằng chứng cho sự cố JVM.

## 1. Hai interface cùng tên nhưng phạm vi khác nhau

Java 17 có hai interface liên quan:

1. **API chuẩn:** `java.lang.management.OperatingSystemMXBean`, nằm trong module `java.management`. Nó có các method `getName()`, `getArch()`, `getVersion()`, `getAvailableProcessors()`, `getSystemLoadAverage()` và `getObjectName()`.
2. **Phần mở rộng JDK:** `com.sun.management.OperatingSystemMXBean`, nằm trong module `jdk.management`, kế thừa interface chuẩn và bổ sung các số liệu CPU/physical memory/swap/virtual memory. Đây là API JDK-specific, không được đảm bảo trên mọi Java implementation hay runtime image tối giản.

Lấy interface chuẩn từ JVM **hiện tại**:

```java
java.lang.management.OperatingSystemMXBean standard =
        java.lang.management.ManagementFactory
                .getOperatingSystemMXBean();
```

Khi cần metric mở rộng, kiểm tra implementation thay vì ép kiểu mù quáng:

```java
if (standard instanceof com.sun.management.OperatingSystemMXBean extended) {
    // Có thể đọc getCpuLoad(), getProcessCpuTime(), getTotalMemorySize(), ...
} else {
    // JVM/runtime này không cung cấp extension được kỳ vọng.
}
```

Hai snippet trên minh họa bên trong method, chưa phải chương trình đầy đủ. Trên một bản HotSpot/OpenJDK 17 phổ biến, đối tượng trả về thường thực thi interface mở rộng; nhưng code có thể được chạy trong runtime khác hoặc custom `jlink` image, nên phải dự phòng.

### 1.1. ObjectName khi đọc qua JMX

Trong platform MBeanServer, operating-system bean có tên chuẩn:

```text
java.lang:type=OperatingSystem
```

`standard.getObjectName()` trả `ObjectName` này. Truy cập từ xa qua JMX phải có kết nối **đúng JVM** và quyền thích hợp; metadata của bean phản ánh môi trường mà JVM đó nhìn thấy, không tự động là toàn bộ cluster.

### 1.2. Bản đồ câu hỏi → phương pháp đo

| Câu hỏi | Method/nguồn | Phạm vi và giới hạn |
| --- | --- | --- |
| JVM nhìn thấy bao nhiêu CPU? | `getAvailableProcessors()` | Số processor khả dụng cho JVM, không nhất thiết bằng core vật lý của host |
| Máy/môi trường có hàng đợi chạy nhiều không? | `getSystemLoadAverage()` | Load average khoảng một phút; không phải %CPU |
| Môi trường đang dùng bao nhiêu CPU gần đây? | Extended `getCpuLoad()` | Tỉ lệ `[0,1]` của operating environment, có thể trả âm |
| Chính tiến trình Java dùng bao nhiêu CPU gần đây? | Extended `getProcessCpuLoad()` | Tỉ lệ `[0,1]`, gồm application threads và JVM internal threads |
| Tích lũy CPU time của JVM bao nhiêu? | Extended `getProcessCpuTime()` | **Nanoseconds CPU**, không phải wall elapsed hay UTC timestamp |
| Tổng/free memory mà môi trường báo là bao nhiêu? | Extended `getTotalMemorySize()` / `getFreeMemorySize()` | **Bytes**, có thể là container-aware theo JDK/nền tảng |
| Swap tổng/free bao nhiêu? | Extended `getTotalSwapSpaceSize()` / `getFreeSwapSpaceSize()` | **Bytes**, chính sách và mức hỗ trợ phụ thuộc OS/cgroup |
| Virtual memory đã commit của process? | Extended `getCommittedVirtualMemorySize()` | **Bytes**, không phải RSS/heap; có thể trả `-1` |
| Java heap thực sự sử dụng? | `MemoryMXBean`, `MemoryPoolMXBean` | **Không phải** nhiệm vụ chính của OperatingSystemMXBean |
| Container bị CPU throttle hay OOMKilled? | Cgroup/Kubernetes/OS metrics, sự kiện runtime | Không thể xác nhận nguyên nhân chỉ từ OperatingSystemMXBean |

## 2. Interface chuẩn: OS identity, available processors và load average

### 2.1. Tên OS, kiến trúc và phiên bản

- `getName()` tương đương giá trị system property `os.name`.
- `getArch()` tương đương `os.arch`.
- `getVersion()` tương đương `os.version`.

Các chuỗi có thể khác giữa Linux, Windows, macOS, bản VM/container, vendor JDK hoặc môi trường ảo hóa. `os.arch` mô tả kiến trúc mà JVM báo, không thay thế việc kiểm tra native library ABI/kiến trúc CPU khi gặp `UnsatisfiedLinkError`.

Không dùng `getName()` để đoán hệ điều hành có bao nhiêu RAM hoặc `getVersion()` để suy ra Linux kernel trên container mà không đối chiếu process/host metadata.

### 2.2. `getAvailableProcessors()` và ý nghĩa “khả dụng”

`getAvailableProcessors()` trả kiểu `int`, **ít nhất 1**, tương đương `Runtime.getRuntime().availableProcessors()`. Nó biểu diễn số processor JVM có thể sử dụng **theo góc nhìn JVM**, không phải bộ đếm số core vật lý tuyệt đối của máy. Giá trị có thể thay đổi khi JVM đang chạy.

Những yếu tố có thể ảnh hưởng:

- OS CPU affinity/cpuset, tài nguyên được cấp cho process;
- container CPU quota và cgroup, khả năng nhận diện container của JDK;
- cờ `-XX:ActiveProcessorCount` trên HotSpot;
- sự khác nhau giữa phiên bản JDK và thuật toán tính effective CPU count.

Ví dụ một node có 32 logical CPUs nhưng container giới hạn 2 CPU; JDK 17 nhận diện cgroup phù hợp có thể báo `getAvailableProcessors() == 2`. Một runtime khác hoặc cờ `-XX:-UseContainerSupport` có thể khiến JVM báo theo host. **Không mặc định** mọi CPU limit fractional (như `500m`) luôn được biểu diễn chính xác bằng một số nguyên từ API: `getAvailableProcessors()` vốn là `int`.

Giá trị này hữu ích khi đánh giá default parallelism, thread pools và GC behavior, nhưng không đại diện trực tiếp cho **CPU usage** hay cho biết CPU throttling.

### 2.3. `getSystemLoadAverage()` không phải CPU %

`getSystemLoadAverage()` trả kiểu `double`, mô tả **load average khoảng một phút gần nhất** theo cách tính của OS: bình quân những thực thể đang chạy/đợi được chạy. Nếu không có dữ liệu trên platform, method trả **số âm**.

Ví dụ trên một máy có 4 logical CPUs:

- Load average `0.5`: số thực thể runnable bình quân tương đối ít.
- Load average `4.0`: gần bằng số CPU khả dụng trong giả định đơn giản.
- Load average `8.0`: nhiều thực thể có thể phải đợi CPU, nhưng không chứng minh CPU % luôn 100%.

Load average **không giới hạn trong `[0,1]`**, không có đơn vị %, và cách OS tính có thể gồm các trạng thái khác nhau. Trên Linux, load average còn có thể chịu ảnh hưởng của tác vụ ở trạng thái uninterruptible sleep (thường liên quan I/O); vì vậy load cao không tự chứng minh CPU là bottleneck.

Nếu `getSystemLoadAverage() == -1` hoặc một giá trị âm khác, ghi “unavailable”, **đừng biến thành 0**. Nếu đang trong container, đối chiếu xem load average phản ánh host hay môi trường khác theo JDK/OS; không tự chia load average cho số CPU của pod để tuyên bố có một tỉ lệ CPU chính xác.

### 2.4. Mẫu chương trình Java 17+ dùng API chuẩn

Lưu file **`StandardOsProbe.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.OperatingSystemMXBean;

public class StandardOsProbe {
    public static void main(String[] args) {
        OperatingSystemMXBean os =
                ManagementFactory.getOperatingSystemMXBean();

        double average = os.getSystemLoadAverage();

        System.out.println("objectName=" + os.getObjectName());
        System.out.println("osName=" + os.getName());
        System.out.println("osArch=" + os.getArch());
        System.out.println("osVersion=" + os.getVersion());
        System.out.println("availableProcessors="
                + os.getAvailableProcessors());
        System.out.println("loadAverageAvailable=" + (average >= 0));
    }
}
```

Biên dịch/chạy:

```bash
javac StandardOsProbe.java
java StandardOsProbe
```

**Output phụ thuộc OS/JDK/container**, ví dụ minh họa (không phải stdout cố định):

```text
objectName=java.lang:type=OperatingSystem
osName=Linux
osArch=amd64
osVersion=6.x
availableProcessors=2
loadAverageAvailable=true
```

Chuỗi `osVersion=6.x` chỉ là cách ghi minh họa, không phải số phiên bản phải xuất hiện thật. Trên một môi trường khác `loadAverageAvailable=false` là hợp lệ. Khi cần dữ liệu đưa vào hệ thống metrics, giữ giá trị số thực, đơn vị, timestamp và nhãn instance; không chỉ ghi boolean.

## 3. Phần mở rộng `com.sun.management.OperatingSystemMXBean` trong JDK 17

Ở JDK 17, extension trong `jdk.management` có các nhóm method:

| Nhóm | Method | Đơn vị | Giá trị đặc biệt |
| --- | --- | --- | --- |
| CPU recent | `getCpuLoad()` | Phân số trong `[0,1]` | Âm khi không có dữ liệu |
| CPU recent của JVM | `getProcessCpuLoad()` | Phân số trong `[0,1]` | Âm khi không có dữ liệu |
| CPU time của JVM | `getProcessCpuTime()` | Nanoseconds | `-1` khi unsupported |
| Total/free memory | `getTotalMemorySize()` / `getFreeMemorySize()` | Bytes | Kiểm tra phạm vi và tính hợp lệ |
| Total/free swap | `getTotalSwapSpaceSize()` / `getFreeSwapSpaceSize()` | Bytes | Có thể không có swap |
| Committed virtual memory | `getCommittedVirtualMemorySize()` | Bytes | `-1` khi unsupported |

Các method `getSystemCpuLoad()`, `getTotalPhysicalMemorySize()` và `getFreePhysicalMemorySize()` là tên cũ, **đã deprecated từ Java 14**. Trên Java 17, ưu tiên tương ứng `getCpuLoad()`, `getTotalMemorySize()` và `getFreeMemorySize()`. Hai tên cũ không là lý do sửa code chạy đúng khi nâng JDK, nhưng viết mới nên dùng tên hiện hành.

**Đặc biệt:** `getCpuLoad()` nói về **operating environment**, có thể là host, môi trường ảo hóa hoặc container-managed theo implementation. Không gọi nó là “process CPU” — process có method riêng `getProcessCpuLoad()`.

### 3.1. Kiểm tra khả năng hỗ trợ

Với `ManagementFactory.getOperatingSystemMXBean()`, dùng `instanceof` như sau:

```java
java.lang.management.OperatingSystemMXBean standard =
        java.lang.management.ManagementFactory
                .getOperatingSystemMXBean();

if (standard instanceof com.sun.management.OperatingSystemMXBean os) {
    double processLoad = os.getProcessCpuLoad();
    if (processLoad >= 0.0) {
        // Chuyển thành phần trăm: processLoad * 100.0.
    } else {
        // Recent CPU load hiện không sẵn có.
    }
}
```

Đây là snippet đặt trong một method. **Không** dùng `(com.sun.management.OperatingSystemMXBean) standard` vô điều kiện trong thư viện muốn hỗ trợ nhiều JVM/vendor. `com.sun.management` là API có trên các JDK thông dụng nhưng không phải contract của interface chuẩn.

### 3.2. `getCpuLoad()`: mức dùng CPU gần đây của môi trường

`getCpuLoad()` trả tỉ lệ `[0.0, 1.0]` của mức dùng CPU *gần đây* trong operating environment. Theo contract:

- `0.0` biểu thị các CPU nhàn rỗi trong khoảng được quan sát;
- `1.0` biểu thị các CPU hoạt động toàn bộ thời gian quan sát;
- giá trị giữa 0 và 1 là tỉ lệ sử dụng trung gian;
- **giá trị âm** = recent CPU usage chưa có/không được hỗ trợ, không phải “CPU âm”.

Ví dụ `0.82` có thể được hiển thị là `82%` **CPU usage của operating environment**. Nó không cho biết tất cả 82% đó do tiến trình Java tạo ra, và không nhất thiết cùng phạm vi với hệ thống giám sát host: cgroup và cách implementation đọc CPU counters có thể khác.

“Recent” không có nghĩa tự động là **cửa sổ 1 phút** như load average. Kích thước cửa sổ, cách cập nhật mẫu và độ mịn phụ thuộc implementation. Nếu đọc ngay sau startup, kết quả âm hoặc chưa ổn định có thể xuất hiện; phải giữ sentinel thay vì ép thành 0%.

### 3.3. `getProcessCpuLoad()`: phần CPU gần đây do JVM sử dụng

`getProcessCpuLoad()` cũng trả `[0,1]` hoặc số âm khi unavailable. Nó tập trung vào **process JVM**, gồm cả:

- Java application threads;
- JVM internal/GC/JIT/runtime threads;
- các hoạt động native chạy trong process.

Ví dụ `getCpuLoad() = 0.90` và `getProcessCpuLoad() = 0.10` có thể gợi ý môi trường đang bận nhưng process Java chỉ dùng một phần. Để kết luận “CPU do process khác chiếm”, phải đối chiếu OS/container process metrics và đảm bảo hai số đo cùng thời điểm/cùng phạm vi. Nếu JVM là process duy nhất trong container nhưng kết quả khác nhau, có thể do phạm vi mẫu, CPU quota, throttling hoặc implementation; không suy ra có process ẩn.

Không lấy `getProcessCpuLoad()` và `getCpuLoad()` cộng với nhau, bởi process thường đã là một phần của tổng CPU môi trường. Không lấy hiệu của hai số để tính chính xác tải “các process khác” nếu chưa hiểu mẫu và denominator.

### 3.4. Bảng phân biệt ba metric dễ nhầm

| Metric | Đơn vị | Cửa sổ/kiểu | Có thể vượt 1? | Dùng để |
| --- | --- | --- | --- | --- |
| `getSystemLoadAverage()` | Số thực thể runnable trung bình | Khoảng 1 phút, OS-specific | **Có** | Dấu hiệu hàng đợi chạy/pressure |
| `getCpuLoad()` | Phân số CPU môi trường | Gần đây, implementation-specific | Không khi hợp lệ | Đánh giá CPU busy của operating environment |
| `getProcessCpuLoad()` | Phân số CPU của JVM process | Gần đây, implementation-specific | Không khi hợp lệ | Đánh giá phần CPU do JVM sử dụng |
| `getProcessCpuTime()` | Nanoseconds CPU tích lũy | Từ lúc process start | **Có, tăng liên tục** | Tính CPU cores trung bình qua hai mẫu |

Vì vậy “load = 4.2” có thể là một load average hợp lệ, nhưng **không phải** CPU load 420%. Nếu dashboard trộn hai metric cùng nhãn `cpu_load` mà không khai báo nguồn/đơn vị, kết luận về bottleneck sẽ sai.

## 4. `getProcessCpuTime()`: đồng hồ CPU time, không phải wall time

### 4.1. CPU time tích lũy là gì?

`getProcessCpuTime()` trả tổng **CPU time của tiến trình JVM** theo nanoseconds; trả `-1` nếu platform không hỗ trợ. Tài liệu Java 17 lưu ý giá trị có **nanosecond precision nhưng không nhất thiết nanosecond accuracy**.

CPU time khác với:

- **Wall elapsed time**: thời gian thực trôi qua giữa hai mốc (`System.nanoTime()` hoặc clock phù hợp).
- **Uptime**: thời gian từ khi JVM/process bắt đầu.
- **CPU load**: tỉ lệ hoạt động trong một khoảng quan sát.
- **Unix timestamp**: thời điểm tuyệt đối UTC; CPU time không chuyển thành timestamp bằng cách tự cộng vào epoch.

Nếu bốn CPU cores cùng chạy bốn JVM threads trong 1 giây wall time, process có thể tích lũy khoảng **4 CPU-seconds** (4 tỉ nanoseconds CPU), dù wall elapsed chỉ 1 giây. Vì thế số CPU time có thể tăng nhanh hơn wall time; đó không phải lỗi.

### 4.2. Lấy **hai mẫu** để tính core-equivalent utilization

Đặt:

- `cpu0`, `cpu1`: hai lần đọc `getProcessCpuTime()`, đơn vị **ns**;
- `wall0`, `wall1`: hai lần đọc `System.nanoTime()`, đơn vị **ns**;
- `N`: số CPU hiệu lực dùng làm denominator, xác định rõ theo mục tiêu đo.

Khi `cpu0/cpu1 >= 0`, cùng đời JVM và `wall1 > wall0`:

```text
deltaCpuNs  = cpu1 - cpu0
deltaWallNs = wall1 - wall0

averageCpuCores = deltaCpuNs / deltaWallNs
normalizedCpuFraction = averageCpuCores / N
normalizedCpuPercent = 100 * normalizedCpuFraction
```

**Ví dụ giả định:** trong 2 giây wall time, tiến trình tiêu thụ thêm 2 giây CPU time. Nó đã dùng **1 core-equivalent** trung bình. Nếu lấy `N=4`, utilization chuẩn hóa là **25%**; nếu giới hạn hiệu lực chỉ cho 2 cores thì cùng work là **50%** theo mẫu denominator đó.

Đây là **ước lượng**, không phải `getProcessCpuLoad()` được định nghĩa chắc chắn bằng công thức này trên mọi JDK. API `getProcessCpuLoad()` có cửa sổ và chuẩn hóa do implementation quyết định. Khi đối chiếu, dùng cùng định nghĩa core count, cgroup quota/CPU throttling, khoảng đo và time origin.

### 4.3. Lưu ý phép đo trong thực tế

- Lấy hai mẫu cách nhau đủ lâu để counters có dữ liệu có ý nghĩa (vài giây là mức tham khảo, tùy tải/độ phân giải), không spam mỗi vài micro giây.
- Không tính nếu bất kỳ CPU time nào `< 0` hoặc có giá trị đi lùi; có thể do unavailable, lỗi thu mẫu hoặc vô tình nối sang process khác.
- Không dùng `System.currentTimeMillis()` làm elapsed clock khi cần tránh clock step/slew; `System.nanoTime()` thích hợp cho hiệu số trong cùng JVM.
- `getAvailableProcessors()` có thể đổi khi runtime hoạt động. Nếu CPU count/cgroup quota thay đổi giữa hai mẫu, ghi dấu **configuration changed** thay vì chia vô tư bằng giá trị cuối.
- Việc đọc CPU và wall time không hoàn toàn đồng thời, tạo sai số. Với mục tiêu latency/CPU rất ngắn, nên dùng JFR/profiler hoặc OS counters phù hợp.
- Không ép mọi kết quả đo tự tính vào `[0,1]` trước khi kiểm tra; nếu cao bất thường có thể do denominator sai, sai đơn vị hoặc snapshot không đồng bộ.

### 4.4. Chương trình Java 17+ có stdout chính xác để kiểm tra công thức

Lưu file **`CpuTimeMathDemo.java`**:

```java
import java.util.Locale;

public class CpuTimeMathDemo {
    public static void main(String[] args) {
        long startWallNs = 1_000_000_000L;
        long endWallNs = 3_000_000_000L;
        long startCpuNs = 4_000_000_000L;
        long endCpuNs = 6_000_000_000L;
        int effectiveCpus = 4;

        long elapsedNs = endWallNs - startWallNs;
        long cpuUsedNs = endCpuNs - startCpuNs;

        double averageCores = (double) cpuUsedNs / elapsedNs;
        double normalizedPercent =
                100.0 * averageCores / effectiveCpus;

        System.out.println("wall_ms=" + elapsedNs / 1_000_000);
        System.out.println("cpu_ms=" + cpuUsedNs / 1_000_000);
        System.out.printf(Locale.ROOT, "average_cores=%.2f%n",
                averageCores);
        System.out.printf(Locale.ROOT, "cpu_percent_of_4=%.2f%%%n",
                normalizedPercent);
    }
}
```

Biên dịch/chạy bằng Java 17+:

```bash
javac CpuTimeMathDemo.java
java CpuTimeMathDemo
```

**Stdout chính xác:**

```text
wall_ms=2000
cpu_ms=2000
average_cores=1.00
cpu_percent_of_4=25.00%
```

Chương trình dùng số liệu cố định để chứng minh toán học, **không đo CPU thật của máy**. Nếu thay `effectiveCpus = 2` và giữ counters thì dòng phần trăm là `50.00%`. Khi dùng với metrics production, ghi rõ CPU count bạn chọn từ đâu và tại thời điểm nào.

## 5. Đọc CPU thực bằng chương trình Java 17+ chạy độc lập

Ví dụ tiếp theo đọc standard interface rồi extension (khi có) và tránh in giá trị CPU âm như phần trăm âm.

Lưu file **`OsMetricsSnapshot.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.OperatingSystemMXBean;
import java.util.Locale;

public class OsMetricsSnapshot {
    private static String percent(double fraction) {
        if (!Double.isFinite(fraction) || fraction < 0.0) {
            return "unavailable";
        }
        return String.format(Locale.ROOT, "%.1f%%",
                fraction * 100.0);
    }

    private static String bytes(long value) {
        return value < 0 ? "unavailable" : value + " bytes";
    }

    public static void main(String[] args) {
        OperatingSystemMXBean standard =
                ManagementFactory.getOperatingSystemMXBean();

        System.out.println("mxbean=" + standard.getObjectName());
        System.out.println("os=" + standard.getName());
        System.out.println("availableProcessors="
                + standard.getAvailableProcessors());

        double loadAverage = standard.getSystemLoadAverage();
        System.out.println("loadAverage1m="
                + (loadAverage < 0 ? "unavailable" : loadAverage));

        if (standard instanceof com.sun.management.OperatingSystemMXBean os) {
            System.out.println("environmentCpu="
                    + percent(os.getCpuLoad()));
            System.out.println("processCpu="
                    + percent(os.getProcessCpuLoad()));
            System.out.println("processCpuTimeNs="
                    + (os.getProcessCpuTime() < 0
                            ? "unavailable" : os.getProcessCpuTime()));
            System.out.println("totalMemory="
                    + bytes(os.getTotalMemorySize()));
            System.out.println("freeMemory="
                    + bytes(os.getFreeMemorySize()));
            System.out.println("totalSwap="
                    + bytes(os.getTotalSwapSpaceSize()));
            System.out.println("freeSwap="
                    + bytes(os.getFreeSwapSpaceSize()));
            System.out.println("committedVirtualMemory="
                    + bytes(os.getCommittedVirtualMemorySize()));
        } else {
            System.out.println("jdkExtension=unavailable");
        }
    }
}
```

Biên dịch/chạy bằng một JDK 17 có module `jdk.management`:

```bash
javac --add-modules jdk.management OsMetricsSnapshot.java
java --add-modules jdk.management OsMetricsSnapshot
```

**Output là dữ liệu sống, không cố định**. Ví dụ về hình dạng trên một JDK có extension:

```text
mxbean=java.lang:type=OperatingSystem
os=Linux
availableProcessors=2
loadAverage1m=1.75
environmentCpu=62.0%
processCpu=48.0%
processCpuTimeNs=3456000000
totalMemory=2147483648 bytes
freeMemory=1342177280 bytes
totalSwap=0 bytes
freeSwap=0 bytes
committedVirtualMemory=1073741824 bytes
```

Đây chỉ là **số liệu giả định** nhằm minh họa định dạng; không được so như output chính xác của một máy bất kỳ. Một lần chạy đầu có thể thấy `environmentCpu=unavailable`, `processCpu=unavailable`, hoặc giá trị thay đổi giữa các dòng do thời điểm đọc khác nhau.

**Giới hạn của demo:** `getProcessCpuTime()` được gọi hai lần trong biểu thức điều kiện, nên giá trị in có thể được đọc ở một thời điểm khác so với lần kiểm tra; nó vẫn là một số quan sát hợp lệ nếu method hỗ trợ. Trong hệ thống giám sát nghiêm túc, hãy đọc **mỗi counter đúng một lần vào biến** cho từng snapshot và gắn timestamp. Program được giữ đơn giản để minh họa API, không giả vờ các chỉ số được lấy atomically.

### 5.1. Một mẫu đúng vẫn chưa là xu hướng

`getCpuLoad()` và `getProcessCpuLoad()` báo “recent usage”; process CPU time là **counter tích lũy**; free RAM là **gauge**. Để phân tích thay đổi:

- Thu các mẫu theo chu kỳ thích hợp (ví dụ mỗi vài giây tùy tải và chi phí).
- Gắn timestamp UTC, instance/PID + JVM start, container ID và JDK version nếu cần.
- Ghi số âm dưới dạng unavailable/null riêng biệt, không biến thành 0.
- Với CPU time, tính **delta** trong cùng JVM instance; khởi tạo lại series khi process restart.
- Cùng một loại chỉ số nhưng thay denominator/cgroup limit phải được gắn mốc cấu hình.

Không so một phần trăm CPU ở thời điểm A với giá trị RAM ở thời điểm B rồi khẳng định quan hệ nhân quả nếu cửa sổ khác nhau.

## 6. Bộ nhớ môi trường không phải Java heap

### 6.1. `getTotalMemorySize()` và `getFreeMemorySize()`

Extension trả:

- `getTotalMemorySize()`: tổng memory mà **operating environment** báo, đơn vị **bytes**.
- `getFreeMemorySize()`: memory còn free trong operating environment, **bytes**.

Trên OpenJDK 17 chạy Linux container với cgroup được nhận diện, số liệu có thể phản ánh tài nguyên **container** thay vì RAM vật lý toàn host. Trên JVM khác, OS khác, hoặc khi container support tắt, chúng có thể phản ánh host/virtualized environment. Luôn kèm metadata JDK/cgroup khi giải thích.

**Không mặc định `total - free` bằng RSS của JVM.** Khoảng này có thể gồm memory của process khác, kernel/cache/cgroup accounting tùy nền tảng. “Free” không đồng nghĩa “reclaimable/available memory” như trường `MemAvailable` ở Linux; thuật ngữ và quy tắc đo thuộc hệ thống điều hành.

Nếu `total=2 GiB` và `free=0.5 GiB`, chỉ có thể nói môi trường báo **1.5 GiB không ở trạng thái free theo metric đó**, không thể kết luận Java heap đang dùng 1.5 GiB.

### 6.2. `getTotalSwapSpaceSize()` và `getFreeSwapSpaceSize()`

Swap bổ sung khả năng lưu các trang nhớ không hoạt động ra backing store trong những cấu hình hỗ trợ. Hai method trả số **bytes** tổng/free swap mà môi trường nhìn thấy.

- `totalSwap=0` có thể hoàn toàn hợp lệ trên container không có swap.
- `freeSwap < totalSwap` cho biết một phần swap đã dùng theo định nghĩa nguồn.
- Swap dùng nhiều không tự chứng minh Java heap leak; có thể có paging/OS pressure.
- Swap có thể bị giới hạn độc lập hoặc bị tắt ở container/cgroup.

Nếu có latency tăng bất thường đồng thời swap usage lên, kiểm tra page-fault, paging I/O, kernel memory pressure và container configuration. Không suy ra latency chỉ do swap khi chưa loại trừ CPU throttling, GC pause hoặc I/O của ứng dụng.

### 6.3. `getCommittedVirtualMemorySize()` khác heap, RSS và RAM

Method này trả tổng **committed virtual memory** bảo đảm có thể dùng cho process theo định nghĩa nền tảng, đơn vị bytes; trả `-1` khi không hỗ trợ. Nó **không phải**:

- Java heap hiện đang dùng (`MemoryMXBean.getHeapMemoryUsage().getUsed()`);
- heap max (`-Xmx`);
- RSS resident pages đang nằm trong RAM;
- trực tiếp là cgroup memory usage;
- OS total physical memory.

Trên Linux, virtual address space/commit, resident memory và cgroup accounting rất khác nhau. Một Java process có thể **reserve** địa chỉ lớn cho heap, metaspace, stack, direct buffer hoặc mapped file mà không resident toàn bộ. Vì vậy không dùng `getCommittedVirtualMemorySize()` làm biểu đồ “JVM memory used” nếu chưa nêu chính xác ý nghĩa.

### 6.4. Bản đồ các lớp bộ nhớ

```text
Host physical memory (RAM)
  ├── OS kernel + page cache + các process khác
  └── Container/cgroup memory accounting (nếu có)
        └── JVM process resident/native memory
              ├── Java heap (objects)
              ├── Metaspace / class metadata
              ├── Thread stacks
              ├── Direct/mapped buffers
              ├── JIT code cache
              ├── GC/JVM native structures
              ├── JNI/native allocations
              └── Thư viện và các trang được map
```

Đây là **sơ đồ khái niệm**, không phải mọi vùng nhớ đều được cộng trực tiếp không trùng lặp vào nhau hay luôn thuộc một cgroup giống nhau. Nhiệm vụ của OperatingSystemMXBean là cho góc nhìn OS/environment; `MemoryMXBean`, `MemoryPoolMXBean`, buffer-pool MXBeans, HotSpot Native Memory Tracking, OS `/proc/<pid>/status`/`smaps` và cgroup metrics bổ sung góc nhìn heap, native, RSS và quota.

### 6.5. Ví dụ bộ nhớ với số liệu cố định

Giả sử total memory của môi trường `2 GiB = 2,147,483,648 bytes`; free memory `512 MiB = 536,870,912 bytes`:

```text
total_memory = 2147483648 bytes
free_memory  =  536870912 bytes
non_free     = 1610612736 bytes  (= 1536 MiB, hoặc 1.5 GiB)
```

Giá trị `non_free` chỉ là **phép trừ hai gauge của môi trường** tại cùng mốc; không thể đổi nhãn thành `jvm_heap_used` hoặc `jvm_rss`.

Trong thực tế hai method có thể được đọc ở hai thời điểm hơi khác nhau. Nếu dùng để tính gauge phái sinh, lấy mẫu gần nhau, nhận diện độ lệch và hiểu rằng các chỉ số không phải một snapshot atomic.

## 7. Container, Kubernetes và giới hạn tài nguyên

### 7.1. Container-awareness trong JDK 17

JDK 17 HotSpot/OpenJDK thường có hỗ trợ nhận diện Linux containers (cgroups v1/v2) và dùng giới hạn cgroup phù hợp cho một số phép tính CPU/RAM. Tuy nhiên **đừng khẳng định mọi bản JDK 17 hay mọi vendor đều đọc cùng một giá trị**: từng update/vendor có thể thay đổi logic và cgroup configuration cũng quan trọng.

Các điểm cần kiểm tra:

- JDK vendor, update/build; HotSpot hay implementation khác;
- cgroup v1 hay v2, đường dẫn cgroup của đúng container;
- CPU quota/period, cpuset/affinity và CPU limit của Kubernetes;
- memory limit, swap limit, usage accounting của container;
- `-XX:+UseContainerSupport` hoặc `-XX:-UseContainerSupport` (khi được hỗ trợ);
- `-XX:ActiveProcessorCount=N` nếu được đặt;
- resource requests và limits do orchestrator thực sự áp dụng.

**Request không bằng limit.** Kubernetes CPU/memory *requests* phục vụ scheduling và các chính sách liên quan; *limits* có thể dẫn tới cgroup CPU throttling hoặc memory termination. Nhiều cluster dùng default LimitRange hoặc admission policy nên “manifest không có limit” chưa chắc container không bị giới hạn.

### 7.2. Vì sao “2 CPUs” không có nghĩa có 2 CPU vật lý riêng?

Container giới hạn 2 CPUs thường có **ngân sách thời gian CPU tương đương** hoặc affinity/cpuset; nó không nhất thiết được pin vào 2 cores không chia sẻ với ai. Một process có thể thấy `getAvailableProcessors()=2` nhưng bị throttled nếu dùng hết quota trong CFS period; trong khi CPU load có thể thấp trong cửa sổ lớn hơn do thời gian bị chặn chạy.

`getAvailableProcessors()` là số nguyên JVM nhận diện để chọn mức song song, **không phải metric xác nhận không bị throttling**. Khi latency tăng, xem `cpu.stat` của cgroup, CPU throttled periods/time, áp lực CPU node, tình trạng GC/JIT và scheduler. Không thể khẳng định bị throttled chỉ từ `getProcessCpuLoad()`.

### 7.3. Một số lệnh hỗ trợ chẩn đoán (đọc-only)

Trên host/tooling được phép:

```bash
# Java launcher chạy thử để xem JDK phát hiện resource nào.
java -XshowSettings:system -version

# Thông tin HotSpot của JVM đích, nếu jcmd có sẵn và đủ quyền.
jcmd 12345 VM.version
jcmd 12345 VM.info
jcmd 12345 VM.flags

# Nếu muốn xem giải thích chi tiết phát hiện container của
# MỘT tiến trình thử có kiểm soát, không thay đổi JVM production:
java '-Xlog:os+container=debug' -version
```

`12345` là PID minh họa. `java -XshowSettings:system -version` tạo một JVM **mới**, nên chỉ phản ánh JDK/env của lệnh đó; nó **không chứng minh** tiến trình production có cùng image, cgroup hay flags. `jcmd VM.info` có thể xuất nhiều metadata, cần xem mức tác động và kiểm soát nơi lưu. Trên Windows/macOS hoặc runtime không hỗ trợ `-XshowSettings:system`, kết quả khác.

Với Linux cgroup v2, các file như `cpu.max`, `cpu.stat`, `memory.max`, `memory.current` và `memory.events` có thể giúp đối chiếu quota, usage, throttling và OOM events. Với cgroup v1 tên file khác. Phải đọc **đúng cgroup membership của process**, không tự lấy một file cgroup ở root và coi là của pod.

### 7.4. Sai số giữa host và container

Một dashboard có thể báo host CPU usage 20%, nhưng pod CPU gần 100% **giới hạn được cấp**. Không có mâu thuẫn nếu hai metric dùng denominator khác. Tương tự host còn 100 GiB free không bảo đảm pod không chạm memory limit 1 GiB.

Khi báo cáo, luôn nêu:

- `scope = host / node / container / JVM process`;
- CPU denominator = host logical CPUs, quota cores, cpuset CPUs hay JVM availableProcessors;
- memory unit = bytes/MiB/GiB và giới hạn nào áp dụng;
- JDK build và cgroup version;
- time window/scrape interval;
- các sentinel unavailable và uncertainty.

## 8. Dùng OperatingSystemMXBean qua JMX

### 8.1. Platform MBeanServer trong cùng JVM

Có thể truy vấn thông qua standard management server. Ví dụ Java 17+ chạy độc lập, không cần extension:

Lưu file **`OsJmxLocalDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class OsJmxLocalDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name =
                new ObjectName("java.lang:type=OperatingSystem");

        Object processors =
                server.getAttribute(name, "AvailableProcessors");
        Object osName = server.getAttribute(name, "Name");

        System.out.println("registered="
                + server.isRegistered(name));
        System.out.println("processorsIsInteger="
                + (processors instanceof Integer));
        System.out.println("nameIsString="
                + (osName instanceof String));
    }
}
```

Biên dịch/chạy:

```bash
javac OsJmxLocalDemo.java
java OsJmxLocalDemo
```

**Stdout chính xác** trên JDK 17 với platform MBeanServer chuẩn:

```text
registered=true
processorsIsInteger=true
nameIsString=true
```

Đây là ví dụ đọc thuộc tính **trong JVM hiện tại**. Với extension, JMX có thể expose các thuộc tính bổ sung qua MBean tương ứng, nhưng danh sách thuộc tính chính xác phụ thuộc implementation. Nếu nối từ một tiến trình quản lý sang JVM khác, phải dùng `MBeanServerConnection` đã xác thực và kiểm tra server identity.

### 8.2. JMX từ xa và an toàn

Kết nối JMX từ xa cho phép thu các snapshot CPU/memory mà không sửa code ứng dụng, nhưng một cấu hình thiếu kiểm soát có thể làm lộ metadata hệ thống hoặc tạo đường truy cập quản trị nguy hiểm.

- Chỉ bật theo quy trình/permissions đã được phê duyệt.
- Dùng xác thực, TLS/network policy hoặc đường kết nối quản trị an toàn.
- Không công khai management port trên Internet.
- Không lấy `java.lang:type=OperatingSystem` của JVM A rồi gắn nhãn metrics cho pod B.
- Thu sampling interval hợp lý; `getSystemLoadAverage()` vốn là hint, còn CPU load gần đây không cần poll cực dày.

Không phải mọi JVM/JDK image cung cấp các attribute mở rộng giống nhau; collector cần phân biệt `unsupported` với giá trị zero.

## 9. Ghép CPU, memory, thread và GC theo bằng chứng

### 9.1. Khi process CPU cao

Nếu `getProcessCpuLoad()` tăng đồng thời latency tăng:

1. Xác minh scope (process/container) và thời gian.
2. Kiểm tra tải môi trường `getCpuLoad()`, effective CPUs và CPU quota.
3. Đo thêm `getProcessCpuTime()` qua hai snapshot để biết CPU-seconds/giây.
4. Xem `ThreadMXBean` CPU time từng thread (nếu được hỗ trợ, bật và được phép) hoặc JFR/profiler để tìm hotspot.
5. Kiểm tra GC/JIT/compilation/native threads vì process CPU bao gồm cả JVM internals.
6. Xem throttling, scheduler và traffic: không đổ lỗi cho ứng dụng chỉ vì process CPU cao.

Một request CPU-intensive có thể tạo process load cao mà thread count không lớn. Ngược lại, hàng nghìn thread blocked có thể gây latency cao trong khi process CPU thấp.

### 9.2. Khi CPU môi trường cao nhưng process CPU thấp

Nếu môi trường CPU gần 95% mà process JVM CPU gần 5%, khả năng đầu tiên là **tải đến từ các workload khác**, nhưng phải xác minh hai metric cùng phạm vi/cửa sổ. Nếu JVM chạy trong container riêng, sự chênh lệch có thể phản ánh host/container accounting, cạnh tranh CPU trên node hoặc độ trễ cập nhật counters. Kết hợp OS process metrics, cgroup metrics và CPU utilization của các pod khác.

Đặc biệt, không suy ra “đang có miner/process lạ” chỉ từ một cặp số liệu.

### 9.3. Khi CPU thấp nhưng latency cao

Vẫn có thể xảy ra:

- Chờ I/O mạng/disk/database, lock contention, park/blocking;
- CPU throttling làm tiến trình không nhận đủ CPU time trong quota window;
- GC stop-the-world pause, safepoint hoặc native blocking;
- downstream timeout và queueing ở nơi khác;
- deadlock/thread starvation.

Hãy dùng thread dumps, `ThreadMXBean`, JFR, GC logs, tracing, request metrics và OS I/O data. CPU thấp không có nghĩa JVM đang “khỏe”.

### 9.4. Khi container bị OOMKilled nhưng heap còn trống

OS/cgroup memory limit thường bao gồm nhiều vùng ngoài Java heap: direct buffers, metaspace, thread stacks, JIT code cache, GC/native/JNI memory, mapped pages và một số kernel/cache accounting. Chỉ số heap `used` có thể thấp hơn `-Xmx` nhưng **cgroup memory.current` vẫn chạm `memory.max`, dẫn đến OOM kill ở cấp OS.

Điều tra cần:

- container memory limit/current usage và `memory.events`/OOMKilled reason;
- `MemoryMXBean` heap và non-heap; `MemoryPoolMXBean` nếu cần;
- buffer pools, thread counts/stacks, JVM native memory tracking nếu đã bật;
- process RSS/`/proc/<pid>/status`/`smaps` nếu có quyền;
- output of GC logs/JFR nếu có;
- whether cgroup metric của `getTotalMemorySize()` phản ánh đúng limit.

Không dùng `getTotalMemorySize() - getFreeMemorySize()` làm giá trị “JVM native memory leak”; nó có phạm vi môi trường, không chỉ process.

### 9.5. Bảng quyết định nhanh

| Quan sát | Có thể nghĩ tới | Bước xác minh tiếp |
| --- | --- | --- |
| `processCpuLoad` cao, `cpuTime` tăng nhanh | JVM dùng nhiều CPU | JFR/profiler, thread CPU, GC/JIT, quota |
| `cpuLoad` cao, `processCpuLoad` thấp | Môi trường bận hơn JVM | Host/cgroup/process metrics, scope |
| Load average cao, CPU load không cao | Hàng đợi/I/O hoặc khác biệt thời gian | Run queue, I/O wait, OS-specific load semantics |
| CPU thấp, p99 cao | Waiting, lock/I/O, throttling hoặc pause | Thread dump, tracing, GC log, cpu.stat |
| Memory free thấp, heap ổn | Memory dùng ngoài heap hoặc workload khác | RSS, cgroup accounting, native memory |
| `getProcessCpuTime()=-1` | Counter unsupported | Bỏ tính delta, dùng metric khác |
| `getSystemLoadAverage()<0` | Load average unavailable | OS metrics thay thế, không báo 0 |
| JVM sees 1 CPU, host has 64 | Cgroup/affinity/flags hoặc JDK detection | `-XshowSettings:system`, `VM.info`, quota, `ActiveProcessorCount` |

## 10. Ví dụ phân tích sự cố với dữ liệu giả định

### Tình huống A — CPU throttling làm p99 tăng

Giả sử pod `checkout-1` có:

```text
node logical CPUs              = 32
container CPU limit            = 1 CPU
JVM getAvailableProcessors()   = 1
JVM getProcessCpuLoad()        = 0.95
JVM getCpuLoad()               = 0.97
p99 latency                    = tăng từ 80 ms lên 900 ms
cgroup cpu.stat nr_throttled   = tăng liên tục
```

Đây là **ví dụ mô phỏng**, không phải output thật. Các chỉ số gợi ý tiến trình đang dùng gần hết tài nguyên CPU được cấp và bị throttled. Để kết luận, cần so tỉ lệ throttled periods/time theo cửa sổ, request volume, GC pauses và thread CPU. Không kết luận bottleneck CPU chỉ từ `getProcessCpuLoad()=0.95` nếu thiếu bằng chứng về quota/throttling.

### Tình huống B — Host bận, JVM ít dùng CPU

Giả sử:

```text
operating-environment CPU load = 0.88
JVM process CPU load           = 0.08
JVM process CPU time delta     = 0.8 CPU-second / 10 seconds wall
JVM availableProcessors       = 2
```

Dữ liệu CPU time delta tương ứng **0.08 core-equivalent**, tức khoảng **4% của hai cores**, không nhất thiết bằng 8% `getProcessCpuLoad()` giả định vì sampling/denominator có thể khác. Đây cũng là một ví dụ về lý do **không đồng nhất** công thức tự tính với method “recent usage” nếu không cùng cửa sổ và định nghĩa. Cần xác minh các workload khác, cgroup scope và thời điểm thu thập.

### Tình huống C — OOMKilled khi Java heap còn nhiều khoảng trống

```text
container memory.max          = 1 GiB
MemoryMXBean heap used        = 300 MiB
MemoryMXBean heap max         = 600 MiB
container memory.current      = gần 1 GiB
container restart reason      = OOMKilled
```

Heap `300 MiB` không phủ nhận việc container chạm `1 GiB`. Sự chênh lệch có thể bao gồm native, stacks, direct buffers, file cache/mapped memory hoặc các khoản cgroup khác. Thu NMT/OS RSS/buffer-pool/thread metrics trước khi kết luận memory leak. Kiểm tra `Xmx`, max direct memory, số thread và limit cùng nhau.

### Tình huống D — Load average cao nhưng GC không phải nguyên nhân

Một Linux node có load average `12`, JVM có `getAvailableProcessors()=4` và process CPU chỉ 10%, trong lúc I/O latency tăng. Có thể một phần load average đến từ tác vụ chờ I/O hoặc node-wide contention; cần xem run queue, iowait, disk/network latency, thread stacks và tình trạng các process khác. Không tự suy diễn rằng 12/4 = CPU 300% hay rằng tăng GC threads là biện pháp sửa đúng.

## 11. Thiết kế telemetry từ MXBean

### 11.1. Các field và đơn vị nên ghi

Một sự kiện metric/snapshot nên có:

- `observed_at_utc`: timestamp UTC lúc lấy mẫu;
- `service`, `instance`, `jvm_pid` và `jvm_start_time` để phân biệt đời process;
- `os_name`, `os_arch`, `jdk_version`, `available_processors`;
- `system_load_average_1m` (numeric, null khi unavailable);
- `environment_cpu_load_fraction`, `process_cpu_load_fraction` (numeric `[0,1]` hoặc null);
- `process_cpu_time_ns` (monotonic-like counter trong một process; null khi unsupported);
- `total_memory_bytes`, `free_memory_bytes`, `total_swap_bytes`, `free_swap_bytes`;
- `committed_virtual_memory_bytes` (không thay RSS);
- `resource_scope` (host/container/unknown), `cpu_limit_cores` và `memory_limit_bytes` khi có evidence;
- `source_api`/JDK vendor/build nếu cần so khác bản triển khai.

Giữ nguyên đơn vị ở tên field để tránh nhầm milliseconds với nanoseconds, bytes với MiB hoặc phân số với %. Khi metric unavailable, lưu null và lý do riêng, không ép sentinel âm thành 0 (0 CPU usage là một giá trị đo hợp lệ).

### 11.2. Phân biệt gauge, counter và rate

| Loại metric | Ví dụ | Cách dùng |
| --- | --- | --- |
| Gauge | `getProcessCpuLoad()`, `getFreeMemorySize()` | Lấy giá trị tại sample time; xác minh scope/cửa sổ |
| Counter tích lũy | `getProcessCpuTime()` | Tính delta/rate giữa các mẫu cùng JVM; restart resets |
| Hint/OS average | `getSystemLoadAverage()` | Theo dõi xu hướng queue pressure, không biến thành %CPU |
| Configuration gauge | `getAvailableProcessors()`, `getTotalMemorySize()` | Theo dõi thay đổi quota/config và bối cảnh, không đo usage trực tiếp |

Prometheus/Grafana có thể làm tăng/giảm độ mịn qua scrape interval và query window. Đặt đúng nhãn và đơn vị trong dashboard; đừng lấy metric `processCpuTimeNs` rồi trình bày như “CPU percent” trước khi dùng phép đạo hàm và denominator đúng.

### 11.3. Chọn khoảng lấy mẫu vừa đủ

`getSystemLoadAverage()` bản chất là average cỡ một phút; poll mỗi 10 ms không tạo được “load average 10 ms”. `getCpuLoad()` và `getProcessCpuLoad()` cập nhật theo cơ chế implementation; poll quá dày có thể cho dữ liệu lặp/cũ hoặc unavailable. Với môi trường production, thu metrics qua chu kỳ chuẩn của nền tảng (thường ở mức vài giây hoặc hơn, tùy SLO) và cân đối số metric/labels.

Khi cần phân tích một spike kéo dài vài chục ms, cần JFR/profiler/CPU sampling chính xác hơn thay vì tăng tần suất MXBean vô hạn.

## 12. Lỗi thường gặp khi đọc OperatingSystemMXBean

1. **Import nhầm hai interface cùng tên.** Interface `java.lang.management` không khai báo `getCpuLoad()`, `getProcessCpuTime()`; extension `com.sun.management` mới có.
2. **Ép kiểu extension không kiểm tra.** JVM khác có thể không hỗ trợ và phát sinh `ClassCastException` hoặc lỗi module resolution.
3. **Nhầm load average với CPU utilization.** Load average có thể lớn hơn 1 và không là phần trăm.
4. **Đọc CPU load âm thành “-100%” hoặc 0%.** Số âm là sentinel unavailable.
5. **Nhầm process CPU time (ns) với uptime/wall time (ms).** CPU time có thể tăng nhanh hơn elapsed wall do đa lõi.
6. **Tính delta qua hai đời process.** Counter reset sau restart; PID/name có thể tái sử dụng.
7. **Không chuẩn hóa theo số CPU có ý nghĩa.** Host 64 cores khác container quota 1 CPU; so % không cùng denominator dẫn tới sai.
8. **Nhầm `getCpuLoad()` với `getProcessCpuLoad()`.** Một chỉ scope môi trường, một chỉ JVM.
9. **Tin vào nanosecond accuracy từ CPU time.** API nói precision, không đảm bảo accuracy tương ứng.
10. **Đồng nhất free memory của môi trường với free heap.** Heap là một phần của JVM process.
11. **Dùng committed virtual memory làm RSS.** Virtual commit không phải resident physical memory.
12. **Không biết JDK có container-awareness hay không.** Cgroup v1/v2, JDK update/vendor và flags thay đổi scope.
13. **Cho rằng CPU load thấp loại trừ throttling.** Cần cgroup counters và sampling interval.
14. **Cho rằng host RAM còn trống thì container không OOM.** Memory limit của pod có thể nhỏ hơn host rất nhiều.
15. **Chỉ xem một snapshot và suy ra trend.** CPU time cần hai mẫu; CPU load gần đây và load avg có cửa sổ khác nhau.
16. **Đọc metric sau khi OS/JVM đã thay đổi cấu hình mà không gắn mốc thời gian.** Có thể đổi available processors hoặc memory limit.
17. **Dùng một lệnh `java -version` ở máy debug để suy ra cgroup của production JVM.** Đó là tiến trình khác.
18. **Mở JMX không xác thực để “đọc thử”.** Metadata có thể nhạy cảm và management endpoint có thể mở bề mặt tấn công.
19. **Tạo label cardinality quá lớn từ PID hoặc request ID trong mọi metric.** Nên gắn instance/JVM lifecycle có kiểm soát.
20. **Coi API platform-specific là bảo đảm ổn định trên mọi Java distribution.** Cần kiểm tra khả dụng và fallback.

## 13. Checklist trước khi kết luận CPU/memory bottleneck

- [ ] Đang dùng interface chuẩn hay extension? Đã kiểm tra module/implementation?
- [ ] Có ghi đầy đủ đơn vị: fraction, CPU nanoseconds, bytes, load average?
- [ ] Mọi số âm sentinel đã được đánh dấu unavailable thay vì chuyển thành 0?
- [ ] Có phân biệt operating-environment CPU với JVM-process CPU?
- [ ] Có phân biệt “recent usage” với load average một phút?
- [ ] Delta CPU time có được đo từ **hai mẫu của cùng JVM** bằng wall elapsed clock thích hợp?
- [ ] Denominator CPU đã được xác minh theo quota/affinity/availableProcessors và thời điểm?
- [ ] Có xét cgroup v1/v2, JDK vendor/update, `UseContainerSupport` và `ActiveProcessorCount`?
- [ ] Total/free memory đang biểu diễn host/container nào? Không nhầm với heap/RSS?
- [ ] Có đối chiếu swap, memory.current/max, kernel accounting hoặc OOM events khi cần?
- [ ] Khi CPU/latency tăng, đã đối chiếu GC, thread stacks/JFR, I/O và CPU throttling?
- [ ] Có gắn UTC sample time, PID/start, container/node và nguồn telemetry?
- [ ] Đã tránh công khai JMX hoặc dữ liệu vận hành nội bộ khi không được phép?
- [ ] Kết luận phân biệt **điều API đo được** với **giả thuyết** cần chứng minh thêm?

## 14. Bài tập tự kiểm tra

**Bài 1 — CPU normalization.** Trong 5 giây wall elapsed, `getProcessCpuTime()` tăng 15 tỉ nanoseconds CPU. Tính average core-equivalents và tỉ lệ theo `N=6`. Đáp án: `15 / 5 = 3` cores trung bình, tương ứng **50% của 6 cores**. Nếu container thực chỉ cho 3 CPU cores, cùng work có thể tương ứng 100% theo denominator đó; phải nêu rõ nguồn của N.

**Bài 2 — Unavailable.** Một JVM trả `getSystemLoadAverage()=-1` và `getProcessCpuLoad()=-1` trong vài lần đọc đầu. Có thể kết luận tải bằng 0 không? **Không.** Phải ghi unavailable, kiểm tra OS/JDK và dùng metrics khác nếu cần.

**Bài 3 — Memory.** Container limit 1024 MiB, heap used 250 MiB nhưng pod OOMKilled. Có hợp lý không? **Có.** Heap chỉ là một phần của container accounting; điều tra native, thread stacks, direct buffers, metaspace, file cache, cgroup events và actual RSS.

**Bài 4 — Scope.** Host CPU 30%, pod JVM process CPU 90% theo dashboard khác. Hai số mâu thuẫn không? **Chưa chắc.** Dashboard có thể chuẩn hóa theo host 32 cores so với pod 2 cores và dùng sampling windows khác nhau; cần đối chiếu metric definition và time interval.

**Bài 5 — Load average.** `getSystemLoadAverage()=6.0` trên node có 4 CPUs, `getCpuLoad()=0.35`. Có thể tuyên bố CPU đang bận 150% không? **Không.** Load average là số thực thể runnable trung bình trong khoảng một phút theo OS, CPU load là phân số dùng CPU gần đây; thêm I/O/runqueue evidence.

## Tài liệu tham khảo

- Oracle Java SE 17, [`java.lang.management.OperatingSystemMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html): OS identity, available processors, load average và sentinel âm.
- Oracle Java SE 17, [`com.sun.management.OperatingSystemMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): `getCpuLoad`, `getProcessCpuLoad`, `getProcessCpuTime`, memory/swap và virtual memory; tên deprecated từ Java 14.
- Oracle Java SE 17, [`ManagementFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html): lấy platform MXBeans và MBeanServer.
- Oracle Java SE 17, [`MemoryMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html), [`ThreadMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): tách heap và CPU/thread diagnostics khỏi môi trường.
- Oracle Java SE 17, [`jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html), [`java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): xác minh VM settings, container và startup options.
- Red Hat Developer, [Java 17: What’s new in OpenJDK's container awareness](https://developers.redhat.com/articles/2022/04/19/java-17-whats-new-openjdks-container-awareness): cgroups, `UseContainerSupport`, `ActiveProcessorCount` và scope môi trường.
- Linux kernel documentation, [Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `cpu.stat`, `cpu.max`, `memory.current`, `memory.max`, `memory.events`.

**Kết luận:** `OperatingSystemMXBean` là cầu nối từ Java sang bối cảnh tài nguyên OS/container. Đọc nó đúng cách đòi hỏi ghi **scope + đơn vị + thời điểm mẫu + JVM identity + giới hạn cgroup**. Chỉ sau khi đối chiếu những điều đó với process CPU time, heap/RSS, CPU throttling, threads, JFR và sự kiện container, bạn mới có cơ sở khẳng định CPU hoặc bộ nhớ của môi trường là nguyên nhân của sự cố.