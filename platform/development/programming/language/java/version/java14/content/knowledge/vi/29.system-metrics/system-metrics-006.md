# Khác biệt tải CPU toàn môi trường với tải CPU của tiến trình Java

## 1. Kết luận ngắn: cùng là “CPU load”, nhưng không đo cùng một đối tượng

Trong ứng dụng Java, CPU có thể đang bận vì **nhiều tiến trình trên cùng môi trường thực thi**, trong khi bản thân **tiến trình JVM của ứng dụng** sử dụng rất ít CPU. Ngược lại, một JVM có thể tiêu thụ gần hết phần CPU mà nó được cấp trong container, dù tổng CPU của host vật lý chưa cao.

Bài học này phân biệt ba câu hỏi:

1. **Toàn môi trường đang bận tới đâu?** Dùng `com.sun.management.OperatingSystemMXBean.getCpuLoad()`: tải CPU gần đây của **operating environment** mà JVM nhìn thấy.
2. **Riêng tiến trình JVM đang dùng bao nhiêu CPU?** Dùng `com.sun.management.OperatingSystemMXBean.getProcessCpuLoad()`: tải CPU gần đây của **tiến trình JVM hiện tại**, bao gồm application threads **và** các luồng nội bộ JVM (như GC, JIT).
3. **Tiến trình đã tích lũy bao nhiêu CPU time?** Dùng `com.sun.management.OperatingSystemMXBean.getProcessCpuTime()`: tổng **nanosecond CPU time** của tiến trình, thích hợp lấy chênh lệch trong một khoảng đo có kiểm soát.

**Không được đồng nhất** những phép đo trên với `getSystemLoadAverage()`, với “100% của một core” trong một số công cụ OS, hoặc với các cgroup/container metrics vốn có **phạm vi và mẫu số khác nhau**.

| Câu hỏi | Phép đo | Bao gồm | Không nên suy ra |
| --- | --- | --- | --- |
| CPU của môi trường | `getCpuLoad()` | Các tác vụ tiêu thụ CPU trong môi trường JVM nhìn thấy | Không phải riêng JVM |
| CPU của JVM | `getProcessCpuLoad()` | Các threads của một tiến trình JVM, kể cả GC/JIT/internal | Không bao gồm toàn bộ các tiến trình khác |
| CPU time JVM | `getProcessCpuTime()` | Tổng thời gian CPU đã dùng, đơn vị nanosecond | Không phải phần trăm tức thời |
| Độ tải trung bình | `getSystemLoadAverage()` | Average số thực thể runnable/queued theo OS trong khoảng thời gian | Không phải CPU utilization 0–100% |
| Số processors khả dụng | `getAvailableProcessors()` | Số processors mà JVM được phép/được cấu hình sử dụng theo cách nó phát hiện | Không nhất thiết là số lõi vật lý của máy chủ |

**Ví dụ dễ hiểu:** nếu một máy có nhiều ứng dụng đang sử dụng CPU, `getCpuLoad()=0.80` có thể tương ứng môi trường bận khoảng **80%**, còn `getProcessCpuLoad()=0.05` phản ánh JVM hiện tại chỉ dùng khoảng **5%** theo phạm vi mà API báo cáo. Khoảng chênh **không tự chứng minh** ứng dụng Java bị lỗi: tải có thể đến từ tiến trình khác hoặc công việc của hệ điều hành.

Đây là ví dụ số liệu **giả định**, không phải giới hạn hay kết quả benchmark của mọi máy. Các mẫu đo có cửa sổ và ngữ nghĩa triển khai riêng; **không lấy 80%-5%=75% làm CPU của tiến trình khác** nếu chưa chứng minh phép đo cùng thời điểm, mẫu số và phạm vi.

### 1.1. Liên hệ đúng với Java 14 và Special Note

Trong `com.sun.management.OperatingSystemMXBean`, tên phương thức **`getCpuLoad()`** được bổ sung từ **Java 14**. Tên lịch sử **`getSystemCpuLoad()`** đã được đánh dấu **`@Deprecated(since="14")`**; Javadoc yêu cầu dùng **`getCpuLoad()`** thay thế. Các API `getProcessCpuLoad()` và `getProcessCpuTime()` vẫn còn được hỗ trợ.

Bài sử dụng **API vẫn còn áp dụng trên Java 17/25 và các JDK hiện đại**, tuyệt đối không giới thiệu `getSystemCpuLoad()` như phương pháp khuyến nghị. Kết quả demo được kiểm chứng với `javac --release 17` và JDK 24.0.2.

**Lưu ý về module:** `com.sun.management.OperatingSystemMXBean` thuộc module JDK **`jdk.management`**, là phần mở rộng quản lý của JDK; đừng nhầm nó với interface chuẩn `java.lang.management.OperatingSystemMXBean` thuộc module **`java.management`**. Interface chuẩn cung cấp `getAvailableProcessors()` và `getSystemLoadAverage()`, nhưng **không có cặp `getCpuLoad()`/`getProcessCpuLoad()`**.

## 2. Tải CPU toàn môi trường: `getCpuLoad()`

Chữ ký hiện hành:

```java
double environment = osBean.getCpuLoad();
```

Trong đó `osBean` là đối tượng `com.sun.management.OperatingSystemMXBean` được lấy qua `ManagementFactory` trên một JDK hỗ trợ extension.

Theo Oracle Javadoc:

- Kết quả **hợp lệ** là `double` trong đoạn **`[0.0, 1.0]`**. Có thể nhân 100 để hiển thị phần trăm.
- `0.0` mang ý nghĩa gần như các CPUs đều nhàn rỗi trong khoảng quan sát gần đây; `1.0` có nghĩa gần như toàn bộ CPU được đo đều bận.
- Tỷ lệ bao gồm việc CPU được sử dụng bởi **mọi công việc trong operating environment có hiệu lực**, không chỉ application code của JVM đang gọi.
- Nếu không lấy được CPU usage, API trả **giá trị âm** (thường biểu diễn là `-1.0`).
- Khoảng thời gian “gần đây” **phụ thuộc triển khai**, thường liên quan khoảng cách giữa các lần gọi; lần đầu gọi không có khoảng quan sát được định nghĩa rõ.
- Các công cụ/threads khác cũng đọc cùng MXBean có thể ảnh hưởng khoảng quan sát và giá trị trả về; Javadoc lưu ý vấn đề này.

**Bẫy về chữ “environment”:** môi trường có thể là hệ điều hành native trên host, một OS đã ảo hóa, hoặc môi trường được quản lý bởi **container**. Vì vậy, không viết nhãn dashboard “CPU toàn server vật lý” khi chỉ biết JVM trả `getCpuLoad()` trong một container. Cần xác định **phạm vi thực** từ cấu hình triển khai và đối chiếu OS/container metrics.

### 2.1. Cách đọc giá trị phần trăm

Ví dụ:

```java
double load = 0.65;
double percent = load * 100.0; // 65.0 (%)
```

Nếu máy có 8 logical processors và cùng một cách chuẩn hóa theo tất cả 8 processors, `65%` biểu diễn một mức tải tổng tương đương khoảng `5,2` core-equivalents trong cửa sổ giả định. Đây là cách diễn giải **mô hình hóa**, không phải cam kết thuật toán của mọi JVM/container.

**Không** gọi `getCpuLoad()` liên tục trong vòng lặp cực nhanh rồi mặc định mỗi giá trị là “một giây mới nhất”. Cửa sổ có thể không đổi, quá ngắn, bị cache hoặc chịu nhiễu do một observer khác. Nên có một lịch lấy mẫu có khoảng cách rõ, ghi timestamp và mô tả hệ đo đạc.

### 2.2. Không nhầm với CPU “idle” hoặc “throttled”

CPU usage cao thể hiện phần thời gian CPU đang thực hiện công việc. Nhưng **CPU throttling** bởi quota và **CPU pressure** là hiện tượng khác: ứng dụng có thể đang bị giới hạn không được chạy thêm dù nhu cầu CPU còn rất lớn.

Ví dụ container chỉ được dùng một phần core: ứng dụng có thể báo CPU usage không quá cao theo một denominator, nhưng latency tăng do quota hết trong mỗi chu kỳ. Để chẩn đoán, theo dõi thêm CPU throttling metrics của cgroup và thời gian đợi, không chỉ một tỷ lệ `getCpuLoad()`.

## 3. Tải CPU riêng tiến trình JVM: `getProcessCpuLoad()`

Chữ ký:

```java
double process = osBean.getProcessCpuLoad();
```

Đây là tỷ lệ CPU gần đây cho **chính tiến trình JVM đang chạy code đo**.

Bao gồm:

- Những luồng ứng dụng xử lý HTTP, các tác vụ batch, mã thuật toán.
- Các luồng nội bộ JVM như **garbage collector**, **JIT compiler**, VM management threads nếu tiêu thụ CPU.
- Các native threads chạy trong cùng tiến trình (trong phạm vi CPU time/process mà OS báo cáo).

Không bao gồm:

- Tiến trình cơ sở dữ liệu chạy riêng.
- Tiến trình reverse proxy/sidecar riêng.
- Một JVM khác, dù đang chạy trên cùng máy/container.
- CPU load của toàn node hay toàn host.

Cũng như `getCpuLoad()`, giá trị thường hợp lệ `0.0..1.0`, âm khi không lấy được, và cửa sổ quan sát **phụ thuộc triển khai**.

**Điểm không hiển nhiên:** khi `getProcessCpuLoad()` tăng, không thể khẳng định mã nghiệp vụ đang tốn CPU. Có thể phần tải đến từ GC, JIT compilation, logging, mã native, code thư viện hoặc processing ở lớp runtime. Muốn tách nguyên nhân, cần sử dụng **JFR / profiler / JMX GC metrics / thread CPU time** và kiểm tra thực tế.

### 3.1. Tỷ lệ tiến trình không giống một thread

Một JVM có thể có nhiều luồng thực sự chạy đồng thời trên nhiều CPU. Vì vậy:

- Mức sử dụng **một thread** khác mức sử dụng **toàn tiến trình**.
- Một tiến trình dùng hai core liên tục trong một khoảng thời gian có thể có **2 core-equivalents**.
- Tỷ lệ chuẩn hóa theo tổng CPU có thể nhỏ hơn 100% dù process đã chiếm hoàn toàn hai cores.
- Trong công cụ như `top`, phần trăm theo **một core làm mẫu số** có thể vượt 100% cho tiến trình nhiều luồng. Không dùng quy ước hiển thị của `top` để diễn giải trực tiếp `getProcessCpuLoad()`.

Nếu hệ thống có 8 processors và số liệu được chuẩn hóa trên cùng 8 CPUs, **một** core-equivalent tương ứng **12,5% dung lượng tổng**. Nếu ứng dụng chạy trong container quota chỉ 1 CPU hoặc dùng virtualization, mẫu số có thể khác. Không dùng 12,5% như hằng số cho mọi môi trường.

### 3.2. Tải JVM cao có thể do GC

Một tình huống thực tế:

```text
environmentCpuLoad: cao
processCpuLoad:     cao
app throughput:     giảm
GC time:            tăng
```

Khả năng JVM đang sử dụng CPU cho GC là **một giả thuyết cần kiểm tra**, chưa phải kết luận. Hãy thêm **GC logs, JFR allocation/GC events, thread-stack/profile** và xác nhận tác vụ nào thực sự tiêu thụ CPU.

Tương tự, `processCpuLoad` thấp nhưng request latency cao thường hướng sự chú ý đến **I/O, lock/queue waiting, throttling hoặc external dependencies** hơn là kết luận ngay ứng dụng “rất nhàn rỗi”.

## 4. CPU time của tiến trình: `getProcessCpuTime()`

Chữ ký:

```java
long totalCpuNs = osBean.getProcessCpuTime();
```

Phương thức trả **tổng thời gian CPU** mà tiến trình JVM đã sử dụng, **nanoseconds**, hoặc `-1` nếu nền tảng không hỗ trợ. Javadoc nêu giá trị có độ phân giải nanosecond nhưng không nhất thiết có độ chính xác ở mức nanosecond.

**Không** hiểu giá trị này là số nanosecond đã trôi qua từ lúc app khởi động. Nếu process chạy nhiều thread trên nhiều cores, tổng CPU time có thể tăng **nhanh hơn đồng hồ thực**. Ngược lại, nếu JVM chủ yếu chờ I/O, CPU time có thể tăng rất chậm dù wall-clock time trôi qua.

Để ước tính mức CPU sử dụng trong một khoảng:

\[
\text{core-equivalents} =
\frac{\Delta \text{process CPU time (ns)}}
     {\Delta \text{wall-clock time (ns)}}
\]

Khi đã chọn số logical processors **phù hợp cùng scope** là `N > 0`:

\[
\text{fraction of N-CPU capacity}
= \frac{\text{core-equivalents}}{N}
\]

\[
\text{percentage of N-CPU capacity}
=100 \times \frac{\Delta \mathrm{CPU}_{ns}}
                   {\Delta \mathrm{wall}_{ns}\times N}
\]

Đây là **công thức tự tính** từ CPU time, **không định nghĩa lại** thuật toán sampling nội bộ của `getProcessCpuLoad()`. Hai số không bắt buộc trùng nhau: khoảng đo có thể khác, sampling có thể được cached, số processors/CPU quota có thể thay đổi và môi trường container có mẫu số riêng.

### 4.1. Vì sao lấy **chênh lệch**, không chia giá trị tích lũy trực tiếp?

Một process đã chạy một giờ có thể tích lũy 3.600 CPU-seconds. Không thể suy ra CPU load “hiện tại” chỉ từ một con số kể từ lúc khởi động; phải biết **khoảng wall time tương ứng** hoặc lấy hai snapshot của cùng process:

```java
long wall1 = System.nanoTime();
long cpu1 = osBean.getProcessCpuTime();

// Đợi hoặc thực hiện workload có kiểm soát.

long cpu2 = osBean.getProcessCpuTime();
long wall2 = System.nanoTime();

long deltaCpu = cpu2 - cpu1;
long deltaWall = wall2 - wall1;
```

Đây là **snippet**, chưa có định nghĩa `osBean` và workload. Trong production cần kiểm tra `cpu1`/`cpu2` không âm, `cpu2>=cpu1` và `deltaWall>0`. Với `nanoTime()`, **chỉ tính chênh lệch trong cùng một JVM**; không so giá trị tuyệt đối giữa hai process/host.

Dùng `System.nanoTime()` cho **elapsed duration** thay vì `System.currentTimeMillis()` — đồng hồ wall clock có thể bị chỉnh bởi NTP hoặc quản trị viên.

### 4.2. Tính toán minh họa

Giả định:

- `deltaProcessCpuNs = 3_000_000_000 ns` = **3 CPU-seconds**.
- `deltaWallNs = 2_000_000_000 ns` = **2 wall-seconds**.

Khi đó:

\[
\text{core-equivalents} = 3/2 = 1.5
\]

Nếu hệ thống được phép sử dụng 4 logical processors và các quy ước có cùng scope:

\[
\text{capacity usage} = 100\times1.5/4 =37.5\%
\]

Nếu mẫu số là 8 logical processors:

\[
100\times1.5/8 = 18.75\%
\]

**Cùng một lượng CPU process thật, phần trăm khác nhau theo mẫu số**. Vì vậy, dashboard phải ghi nhãn rõ denominator, số processors/CPU limit và phạm vi.

## 5. Live demo Java 17+: đo hai CPU scopes từ MXBean

Để dùng interface mở rộng, Java cung cấp `ManagementFactory.getOperatingSystemMXBean()`. Trên JDK có `jdk.management`, đối tượng thường implement `com.sun.management.OperatingSystemMXBean`; nên kiểm tra `instanceof` nếu code cần chạy trên nhiều JVM implementations.

**Tệp `CpuScopeMonitor.java` — Java 17+:**

```java
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.ManagementFactory;
import java.util.Locale;

public class CpuScopeMonitor {
    static String percentage(double value) {
        if (!Double.isFinite(value) || value < 0.0 || value > 1.0) {
            return "unavailable";
        }
        return String.format(Locale.ROOT, "%.1f%%", value * 100.0);
    }

    static String cpuCoreEquivalents(long firstCpuNs, long secondCpuNs,
                                     long elapsedWallNs) {
        if (firstCpuNs < 0 || secondCpuNs < firstCpuNs ||
                elapsedWallNs <= 0) {
            return "unavailable";
        }
        double cores = (secondCpuNs - firstCpuNs) / (double) elapsedWallNs;
        return String.format(Locale.ROOT, "%.3f", cores);
    }

    public static void main(String[] args) throws InterruptedException {
        java.lang.management.OperatingSystemMXBean base =
                ManagementFactory.getOperatingSystemMXBean();

        System.out.println("availableProcessorsPositive=" +
                (base.getAvailableProcessors() >= 1));

        if (!(base instanceof OperatingSystemMXBean os)) {
            System.out.println("extendedMxBean=unavailable");
            return;
        }

        os.getCpuLoad(); // Warm up the first environment observation.
        os.getProcessCpuLoad(); // Warm up the first process observation.

        long startWall = System.nanoTime();
        long startCpu = os.getProcessCpuTime();

        Thread.sleep(500);

        double environment = os.getCpuLoad();
        double process = os.getProcessCpuLoad();
        long endCpu = os.getProcessCpuTime();
        long elapsedWall = System.nanoTime() - startWall;

        System.out.println("extendedMxBean=available");
        System.out.println("environmentCpuLoad=" + percentage(environment));
        System.out.println("processCpuLoad=" + percentage(process));
        System.out.println("processCpuCoreEquivalents=" +
                cpuCoreEquivalents(startCpu, endCpu, elapsedWall));

        double loadAverage = base.getSystemLoadAverage();
        System.out.println("loadAverageSupported=" +
                (Double.isFinite(loadAverage) && loadAverage >= 0.0));
        System.out.println("metricsAreDifferentScopes=true");
    }
}
```

**Lệnh kiểm chứng trên một JDK có `jdk.management`:**

```bash
javac --release 17 --add-modules jdk.management -encoding UTF-8 CpuScopeMonitor.java
java --add-modules jdk.management CpuScopeMonitor
```

**Một stdout thực sự quan sát được trên Windows / JDK 24.0.2:**

```text
availableProcessorsPositive=true
extendedMxBean=available
environmentCpuLoad=46.1%
processCpuLoad=0.5%
processCpuCoreEquivalents=0.135
loadAverageSupported=false
metricsAreDifferentScopes=true
```

**Không dùng đoạn stdout như expected-output cứng trong unit test!** Những số 46,1%; 0,5%; 0,135 là số liệu **động** của một lần đo. Trên lần chạy khác, CPU của môi trường, hoạt động Windows/JVM, sampling window và số core-equivalents sẽ thay đổi. `loadAverageSupported=false` trong lần đo này phù hợp với việc một số hệ điều hành không cung cấp load average; trên Linux có thể là `true`. Trên JVM không có extension `com.sun.management`, chương trình in `extendedMxBean=unavailable` và kết thúc sớm.

Dòng `metricsAreDifferentScopes=true` là **chú thích chủ ý do chương trình in**, không phải một kết quả phân loại nhân quả từ phép đo. Nó chỉ nhắc rằng API đã truy vấn hai đối tượng khác nhau.

### 5.1. Giải thích những điểm quan trọng

1. Import `com.sun.management.OperatingSystemMXBean` để lấy **cặp load methods** và CPU time extension.
2. Biến `base` dùng interface Java SE `java.lang.management.OperatingSystemMXBean` để nhận `getAvailableProcessors()` và `getSystemLoadAverage()`.
3. `instanceof OperatingSystemMXBean os` là pattern matching ổn định trên Java 17; tránh ép kiểu mù quáng nếu triển khai JVM không hỗ trợ extension.
4. Hai lần gọi đầu đến `getCpuLoad()` và `getProcessCpuLoad()` giúp **warm-up** bước quan sát đầu tiên. Chúng không bảo đảm các giá trị tiếp theo đã ổn định hay có cửa sổ chính xác 500 ms.
5. `Thread.sleep(500)` tạo khoảng thời gian wall-clock; độ dài thật có thể lớn hơn do thread scheduling. Chương trình dùng `System.nanoTime()` để đo elapsed thực tế.
6. `percentage(...)` đánh dấu `"unavailable"` nếu giá trị âm, `NaN`, vô hạn hoặc nằm ngoài đoạn `[0,1]`; không ép mọi giá trị bất hợp lệ về 0%.
7. `cpuCoreEquivalents(...)` dùng chênh lệch counter CPU process với wall time; chỉ trả một phép ước lượng riêng, không gọi nó là `getProcessCpuLoad()`.
8. `getSystemLoadAverage()` được kiểm tra hỗ trợ; nó **không** được chuyển thành phần trăm CPU.
9. `availableProcessorsPositive` kiểm tra theo hợp đồng API trả số CPUs ít nhất 1, nhưng không in một con số lõi vật lý cố định để tránh gây hiểu lầm trên container.

### 5.2. Vì sao hai dòng CPU có thể rất khác?

Trong lần thử, toàn môi trường khoảng **46,1%**, còn riêng JVM khoảng **0,5%** theo MXBean. Điều đó **phù hợp** với trường hợp máy có các tiến trình khác hoặc OS đang dùng CPU, còn chương trình demo hầu hết đang `sleep`. Tuy nhiên, vì môi trường đo và các cửa sổ sampling không hoàn toàn đồng nhất, **không lấy hiệu 45,6 điểm phần trăm làm số liệu chính xác của phần việc ngoài JVM**.

Trong một lần chạy khác, `-XX:ActiveProcessorCount`, container quota, hệ điều hành hoặc tiến trình chạy song song có thể thay đổi cách JVM nhìn số CPU khả dụng. Kết luận đúng cần dựa trên thêm dữ liệu cùng thời gian từ OS và cgroup.

### 5.3. Không dùng chuỗi exception làm chuẩn

Nếu `getCpuLoad()` hoặc `getProcessCpuLoad()` không lấy được dữ liệu, Javadoc mô tả **trả giá trị âm**. Vì vậy một hệ thống monitor nên:

- Đặt **metric unavailable** / không xuất sample thay vì đưa vào trung bình như một số âm.
- Đừng tự động biến `-1` thành **-100%** hoặc thành **0%**.
- Không lặp một giá trị cũ mãi như dữ liệu mới khi metric không còn lấy được.
- Có metric/health event báo sensor unavailable nếu dữ liệu này quan trọng cho alerting.

Các nguồn khác như OS process statistics, cgroup metrics hoặc monitoring agent có thể hỗ trợ đối chiếu, nhưng phải giữ metadata về scope và units.

## 6. Ví dụ có stdout tất định: từ CPU time sang phần trăm

Để tính đúng formula mà không phụ thuộc tải thực của máy, dùng dữ liệu giả định cố định và validate input. Đây là chương trình **độc lập** với MXBean, chỉ dùng Java SE.

**Tệp `CpuLoadMathDemo.java` — Java 17+:**

```java
import java.util.Locale;

public class CpuLoadMathDemo {
    static double coreEquivalents(long processCpuDeltaNs, long wallDeltaNs) {
        if (processCpuDeltaNs < 0 || wallDeltaNs <= 0) {
            throw new IllegalArgumentException("invalid deltas");
        }
        return processCpuDeltaNs / (double) wallDeltaNs;
    }

    static double percentOfCapacity(long processCpuDeltaNs,
                                    long wallDeltaNs, int availableCpus) {
        if (availableCpus <= 0) {
            throw new IllegalArgumentException("invalid CPU count");
        }
        return 100.0 * coreEquivalents(processCpuDeltaNs, wallDeltaNs)
                / availableCpus;
    }

    static String fractionPercent(double sample) {
        if (!Double.isFinite(sample) || sample < 0.0 || sample > 1.0) {
            return "unavailable";
        }
        return String.format(Locale.ROOT, "%.1f%%", sample * 100.0);
    }

    public static void main(String[] args) {
        long cpuNs = 3_000_000_000L;
        long wallNs = 2_000_000_000L;
        System.out.printf(Locale.ROOT, "usedCoreEquivalents=%.2f%n",
                coreEquivalents(cpuNs, wallNs));
        System.out.printf(Locale.ROOT, "capacityFourPercent=%.1f%%%n",
                percentOfCapacity(cpuNs, wallNs, 4));
        System.out.printf(Locale.ROOT, "capacityEightPercent=%.2f%%%n",
                percentOfCapacity(cpuNs, wallNs, 8));
        System.out.println("environmentExample=" + fractionPercent(0.80));
        System.out.println("processExample=" + fractionPercent(0.25));
        System.out.println("unsupportedSample=" + fractionPercent(-1.0));
        System.out.println("invalidSample=" + fractionPercent(Double.NaN));

        try {
            coreEquivalents(-1, 1_000_000_000L);
            System.out.println("negativeDelta=MISSED");
        } catch (IllegalArgumentException ex) {
            System.out.println("negativeDelta=REJECTED");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CpuLoadMathDemo.java
java CpuLoadMathDemo
```

**Stdout chính xác đã kiểm chứng:**

```text
usedCoreEquivalents=1.50
capacityFourPercent=37.5%
capacityEightPercent=18.75%
environmentExample=80.0%
processExample=25.0%
unsupportedSample=unavailable
invalidSample=unavailable
negativeDelta=REJECTED
```

Phân tích:

- **3 CPU-seconds trong 2 wall-seconds** = **1,5 core-equivalents**, có thể xảy ra khi tiến trình dùng nhiều luồng song song.
- Cùng 1,5 cores trên tổng 4 cores = **37,5%**; trên 8 cores = **18,75%**. Không có “phần trăm CPU” duy nhất nếu mẫu số chưa được định nghĩa.
- `environmentExample=80%` và `processExample=25%` là **hai số giả định** thể hiện khác scope. Chúng **không** được tạo từ phép trừ nhau.
- `-1.0` và `NaN` được biểu diễn thành `unavailable`, không làm sai dashboard.
- `negativeDelta` bị từ chối để không biến counter không hợp lệ thành tỷ lệ âm.

### 6.1. Một phép tính có thể vượt 100% theo denominator nhỏ

Nếu CPU time tăng 3 giây trong 1 giây wall-clock nhờ 3 cores làm việc đồng thời, `core-equivalents=3.0`. Nếu chia cho **2 CPUs** trong khi process thực tế được sử dụng 3 cores, kết quả là **150%**; điều đó cho thấy **mẫu số / phạm vi / giả thiết bị sai hoặc thay đổi**, chứ không có nghĩa `getProcessCpuLoad()` sẽ trả `1.5`.

Javadoc của `getProcessCpuLoad()` công bố **giá trị hợp lệ trong `[0,1]`**. Hàm tự tính từ CPU-time delta không bị API đó buộc vào cùng khoảng vì có thể đo không đồng bộ, sai denominator, cgroup quota thay đổi hoặc số CPUs thực sự khả dụng khác với giá trị được dùng để chia.

### 6.2. Thời gian CPU của thread không bằng thời gian CPU của process

Java còn có `java.lang.management.ThreadMXBean` với các API đo CPU time từng thread khi nền tảng hỗ trợ. Nó phù hợp để phân tích thread nóng, nhưng:

- Phải kiểm tra mức hỗ trợ và trạng thái enable của thread CPU time.
- Một thread chỉ là **một phần** của toàn tiến trình; luồng khác và GC/JIT vẫn dùng CPU.
- Không đồng nhất CPU time thread, CPU time process và elapsed wall time.
- Nếu thread biến mất trước khi đọc hoặc id bị tái sử dụng, phép đo cần xử lý lifecycle.

**Khi mục tiêu là CPU của tiến trình**, `getProcessCpuTime()` dễ phù hợp hơn một phép cộng tùy tiện từ vài thread IDs.

## 7. Bảng diễn giải thực tế theo hai phạm vi CPU

| Tải môi trường | Tải JVM | Giả thuyết có thể xem xét | Điều cần xác nhận |
| --- | --- | --- | --- |
| Cao | Thấp | Tiến trình khác, OS, sidecar hoặc hoạt động nền đang dùng CPU | Host/container process list, cgroup usage, OS counters |
| Cao | Cao | JVM cũng là một nguồn CPU lớn; có thể tranh chấp | App profile, JFR, GC time, thread CPU, quota |
| Thấp | Thấp | CPU chưa phải nút thắt trong cửa sổ quan sát | I/O latency, locks, queue, disk/network, external services |
| Thấp | Cao | Mẫu số/scope hoặc sampling window khác nhau; có thể thay đổi rất nhanh | Timestamp, interval, container quota, CPU count, agent metrics |
| Không có dữ liệu | Có dữ liệu | API environment metric chưa được hỗ trợ | Không suy số environment từ process |
| Có dữ liệu | Không có dữ liệu | Process metric chưa được hỗ trợ | Dùng process time delta hoặc OS metrics nếu sẵn |
| Tải thấp | Latency cao | CPU throttling/đợi I/O/lock hoặc dependency có vấn đề | Throttling stats, wall-clock tracing, queue waits |

**Một hàng là một giả thuyết, không phải chẩn đoán tự động.** Không thể quy kết “tải JVM thấp nghĩa là code tối ưu” hay “tải host cao nghĩa là JVM chắc chắn cần scale” chỉ từ hai con số.

### 7.1. Ví dụ một dịch vụ có Java và database

Giả sử trên một VM có:

```text
Java service JVM: getProcessCpuLoad() = 0.10
Operating environment: getCpuLoad() = 0.80
Database service: process riêng trên VM
```

Có thể database đang xử lý truy vấn nặng và là nguyên nhân của tải môi trường cao. Nhưng cũng có thể CPU được dùng bởi backup, antivirus, OS, một JVM khác. **Không xác định thủ phạm bằng phép trừ `0.80 - 0.10`**; xem per-process OS metrics cùng thời điểm.

### 7.2. Ví dụ trong container

Nếu một container được cấp quota tương đương 1 CPU và host có 16 logical processors, một ứng dụng có thể gần **100% quota** nhưng vẫn chỉ đóng góp phần nhỏ vào CPU tổng của host. Tỷ lệ “CPU 100%” trên dashboard container và tỷ lệ “CPU toàn host” không trực tiếp so sánh được.

Đừng giả định `getCpuLoad()` trên **mọi JDK/OS** luôn báo host, hoặc luôn báo container. Javadoc chỉ nói **operating environment**, bao gồm native, virtualized hoặc container-managed environment. Muốn gắn nhãn host/container phải **kiểm tra thực tế** triển khai JDK và đối chiếu với cgroup/container metrics.

### 7.3. Dấu hiệu cần đo thêm khi scale

Khi quyết định tăng replicas hoặc CPU quota:

- **Process CPU load** tăng và latency tăng có thể cho thấy JVM cần CPU hoặc đang GC quá nhiều.
- **Environment CPU load** tăng trong khi JVM thấp cho thấy nên tìm nguồn tải bên ngoài JVM trước.
- **CPU throttling tăng** có thể giải thích latency dù process CPU usage tính theo host không cao.
- **Queue length**, runnable threads, lock contention và request throughput giúp xác định áp lực chưa xử lý.
- **GC time / allocation rate** giúp phát hiện CPU bị JVM runtime tiêu tốn.
- **Limits/requests** và phân bố workload trên cluster quyết định cách scale phù hợp.

Khi xây alerting, không alert chỉ từ một lần trả về `getCpuLoad()`; dùng time series, nhiều mẫu hợp lệ, timestamp và quy tắc chuyển trạng thái rõ.

## 8. Trong container/Kubernetes: ba lớp phải phân biệt

Một ứng dụng Java trong container có thể thấy các lớp sau:

```text
Máy vật lý / VM host
  + CPU tổng của host và các process/containers trên host
  |
  +-- Container / cgroup
        + CPU quota, cpuset, scheduling, throttling
        + Có thể chứa nhiều process
        |
        +-- Tiến trình JVM đang chạy
              + user threads
              + JVM GC/JIT/native internal threads
```

**Ba scope này không tự đồng nhất.** Khi tự động hóa giám sát cần đặt nhãn **`scope=host|container|process`** rõ ràng. Với một process duy nhất trong một container, scope container vẫn có thể bao gồm thời gian chạy của các helper processes/sidecars nếu cấu hình cgroup cho phép; không suy ra bằng nhau mà thiếu bằng chứng.

### 8.1. Metrics cgroup v2 trên Linux

Theo Linux kernel documentation, cgroup v2 dùng các tệp như:

- **`cpu.stat`:** chứa `usage_usec` (tổng CPU usage tính bằng microseconds của các processes thuộc cgroup và descendant cgroups), cùng `user_usec`, `system_usec`.
- **`nr_periods`, `nr_throttled`, `throttled_usec`:** khi CPU controller và loại scheduling liên quan được bật, cho biết mức độ CPU quota/throttling.
- **`cpu.max`:** quota và period CPU cho cgroup; `max` biểu thị không có quota bandwidth từ cgroup đó.
- **`cpuset.cpus.effective`:** CPUs có hiệu lực theo cpuset.
- **`cpu.pressure`:** thông tin áp lực/đợi CPU, **khác** CPU utilization.

Ví dụ **minh họa trên Linux cgroup v2**, khi xác định được đường dẫn cgroup của tiến trình:

```bash
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpuset.cpus.effective
```

Các lệnh có thể đọc **cgroup khác với cgroup thực sự của JVM** nếu process không ở root cgroup đang mount. Trong sản phẩm thật, tìm **đường dẫn cgroup hiệu lực** của tiến trình qua cấu hình/mount namespace và `/proc/self/cgroup`; trong cgroup v1, tên file và semantics khác.

Không cố dùng công thức `usage_usec * 100` làm CPU%: cần **chênh lệch usage theo khoảng thời gian**, mẫu số tương ứng với quota/số CPU có hiệu lực và định nghĩa rõ ý nghĩa “100%”. `cpu.stat` có thể bao gồm **nhiều processes**, không phải riêng JVM.

### 8.2. JVM container awareness

HotSpot trên Linux có tính năng **UseContainerSupport** (bật mặc định trong các JDK có hỗ trợ). JVM có thể xác định tài nguyên khả dụng từ cấu hình container để chọn kích thước pools, heap ergonomics, processors.

Tùy chọn:

```bash
java -XX:ActiveProcessorCount=2 -jar your-app.jar
```

đặt số processors mà JVM sử dụng cho một số quyết định ergonomics và API phản ánh số CPUs khả dụng. Nó **không tự tạo CPU quota của OS**, không đồng nghĩa host thật chỉ có hai cores, và không phải công thức tính phần trăm CPU cho mọi dashboard.

Nếu chạy trong container:

- Ghi JDK vendor/build, OS, cgroup v1/v2 và phiên bản container runtime.
- Ghi CPU limits/quotas, cpuset, số CPUs khả dụng theo JVM và khả năng bị throttled.
- Đối chiếu `getCpuLoad()`/`getProcessCpuLoad()` với metrics agent/Prometheus/OS cùng khoảng.
- Nếu các phép đo khác nhau, kiểm tra **mẫu số và scope** trước khi kết luận một bên đo sai.
- Đừng lấy thông số JVM chỉ có ý nghĩa ergonomics để tự thay thế quyền/quota OS.

### 8.3. Vì sao container CPU% có thể vượt 100%?

Một số monitoring tools dùng một core làm **100%**; một container tiêu thụ hai core-equivalents có thể hiện **200%**. Một metric khác định nghĩa 100% là **100% quota** hoặc **100% của tất cả 8 processors**, nên cùng workload có phần trăm khác.

`getProcessCpuLoad()` của `com.sun.management.OperatingSystemMXBean` có hợp đồng `[0,1]` cho phạm vi của nó. **Không đổi đơn vị** từ tỷ lệ này thành “top-style % của một core” mà không nói rõ công thức và denominator.

## 9. `getSystemLoadAverage()` không phải CPU%

Interface chuẩn `java.lang.management.OperatingSystemMXBean` có:

```java
double loadAverage = base.getSystemLoadAverage();
```

Theo Javadoc, đây là **load average 1 phút**, liên quan số lượng thực thể có thể chạy, đang chạy hoặc chờ CPU theo mô hình của OS. Giá trị có thể **lớn hơn 1** và thậm chí lớn hơn số CPUs; không có hợp đồng `0..1` như CPU load fraction. Hệ điều hành có thể trả giá trị âm nếu không hỗ trợ.

**Đừng viết:**

```java
double cpuPercent = base.getSystemLoadAverage() * 100.0; // Sai ngữ nghĩa.
```

Đây là snippet cố ý sai; `base` là biến đã có. Nếu `getSystemLoadAverage()` trả `2.5`, điều đó **không phải 250% CPU utilization**. Load average phản ánh áp lực lượng việc trong một khoảng thời gian, không trực tiếp tỷ lệ CPU đang bận.

Trên Windows, JDK đã thử trả giá trị âm (bài demo in `loadAverageSupported=false`). Khi metric không có sẵn, báo unavailable, không đổi thành 0.

## 10. Kiểm chứng việc lấy mẫu, lịch đo và tính nhất quán

### 10.1. Khoảng quan sát không cố định theo ý người gọi

Javadoc của `getCpuLoad()` và `getProcessCpuLoad()` mô tả “recent CPU usage” với **observation period implementation-specific**. Điều đó có nghĩa:

- Không giả định mọi giá trị đại diện đúng một giây, 500 ms hoặc một phút.
- Không giả định hai phương thức có **cùng khoảng** đo.
- Không lấy dữ liệu `getCpuLoad()` lúc 10:00:00 trừ `getProcessCpuLoad()` lúc 10:01:00 rồi kết luận nguồn tải khác.
- Hai monitor agents gọi song song có thể ảnh hưởng quan sát, tùy implementation.
- Lần đầu có thể chưa có dữ liệu lịch sử hữu ích; nên có warm-up và xử lý unavailable.
- Không lấy một mẫu ngẫu nhiên rồi gắn nhãn “CPU nóng suốt ngày”.

Một hệ thống quan sát tốt sử dụng **monotonic sampling** khi tự tính chênh lệch và timestamp thống nhất cho dashboards; biểu đồ có nhãn **đối tượng, đơn vị, thời điểm và cửa sổ**.

### 10.2. Phát hiện dữ liệu không hợp lệ

Đối với CPU load fraction:

```java
static boolean validLoad(double x) {
    return Double.isFinite(x) && x >= 0.0 && x <= 1.0;
}
```

Đây là **method snippet** có thể đặt trong class Java. Khi false, mẫu không hợp lệ/không sẵn có theo contract, bỏ qua phép tính trung bình và ghi nhận lỗi measurement; không biến nó thành 0.

Đối với CPU time delta:

```java
static boolean validDelta(long cpuStart, long cpuEnd, long wallDelta) {
    return cpuStart >= 0 && cpuEnd >= cpuStart && wallDelta > 0;
}
```

Không chia khi `wallDelta==0` hoặc CPU time trả `-1`. Không so CPU time tích lũy của PID đã restart với PID cũ vì sẽ thấy counter “đột nhiên giảm” do lifecycle. Nếu wall interval quá ngắn, sai số/lượng CPU OS làm tròn có thể gây tỷ lệ nhiễu.

### 10.3. Đừng ép tỷ lệ thành số hợp lệ bằng `Math.max(0,...)`

Sai:

```java
double observed = Math.max(0.0, osBean.getCpuLoad());
```

Nếu API trả `-1` vì không hỗ trợ, biến `observed` sẽ là `0.0` — đồng nghĩa **“CPU nhàn rỗi”**. Trong alerting, điều đó khiến hệ thống coi lỗi sensor là hạ tải. Nên giữ trạng thái missing và báo lỗi theo chính sách.

### 10.4. Kiểm chứng bằng JFR, OS tools và workload

Trong môi trường Linux, một phép kiểm chứng có thể có ba pha:

1. **Baseline idle:** giữ workload thấp, lấy liên tiếp các mẫu từ MXBean và OS monitoring; xem process time delta nhỏ.
2. **Tăng CPU work của chính JVM:** chạy workload test có kiểm soát, dự kiến `getProcessCpuLoad()` và delta process CPU time tăng trong các cửa sổ phù hợp.
3. **Tăng CPU work ở tiến trình khác:** trên máy test được phép, chạy tiến trình ngoài JVM; tải môi trường có thể tăng trong khi JVM process CPU thấp, tùy quota/scheduling.

Không đo tải production bằng cách tự tạo các vòng lặp CPU vô hạn. Nếu cần load testing, dùng môi trường riêng, giới hạn thời lượng/tài nguyên và ghi rõ các mức tải.

Dùng tools như Linux `top`/`pidstat`, Windows Task Manager/Performance Monitor, JFR/Java Mission Control, container metrics, OS process accounting để đối chiếu. Các công cụ này có thể dùng **mẫu số và cửa sổ khác**, nên chuẩn hóa trước khi so sánh.

## 11. JFR và ThreadMXBean giúp tìm **nguyên nhân** chứ không thay tải môi trường

Khi `getProcessCpuLoad()` cao, bạn muốn biết **thread, phương thức, GC hay native library** nào dùng CPU.

- **JFR (Java Flight Recorder):** có các events liên quan CPU load, GC, thread, execution sampling và performance; phân tích theo cấu hình phù hợp JDK.
- **Java Mission Control / profiler:** giúp tìm hot methods, contention, allocation pressure.
- **`ThreadMXBean.getThreadCpuTime(...)`:** CPU time từng thread nếu nền tảng hỗ trợ và tính năng đã bật.
- **`GarbageCollectorMXBean`:** cung cấp GC count/time; kết hợp với JFR để xác định overhead.
- **Process / cgroup / host metrics:** xác minh phạm vi và tài nguyên xung quanh JVM.

**Đừng nói JFR `jdk.CPULoad` “chính là getCpuLoad() ở mọi JVM”** mà không kiểm chứng settings/semantics, sampling hoặc hệ thống metric mà bạn đang dùng. Các công cụ có thể cùng đo liên quan CPU nhưng phạm vi/hợp đồng và thời điểm khác nhau.

### 11.1. Nếu CPU JVM thấp nhưng response chậm

Xem xét:

- Chờ database, network, disk hoặc thread pool queue.
- Lock contention, nhiều thread `BLOCKED`/`WAITING`.
- CPU quota throttling, thiếu CPU entitlement cho container.
- GC stop-the-world pauses, mặc dù tính trung bình CPU process có thể không quá cao trong cửa sổ nào đó.
- External service latency và retry/backoff.
- Thermal throttling, VM steal time, host oversubscription.

Điều quan trọng là **latency end-to-end** không chỉ phụ thuộc CPU utilization. Thêm tracing/queue measurements và OS/container metrics trước khi kết luận.

## 12. Các lỗi phổ biến cần tránh

### Lỗi 1 — Dùng API đã deprecated từ Java 14

Dùng `getSystemCpuLoad()` trong code mới là không cần thiết; từ Java 14 dùng `getCpuLoad()`. Cách mới có cùng vai trò “recent CPU usage của operating environment”.

### Lỗi 2 — Đồng nhất `getCpuLoad()` với `getProcessCpuLoad()`

Một phép đo toàn môi trường, phép kia đo một tiến trình JVM. Không báo cáo cả hai dưới cùng metric key không có nhãn scope.

### Lỗi 3 — Gọi `getSystemLoadAverage()` là CPU load fraction

Load average có đơn vị/ngữ nghĩa khác và có thể lớn hơn 1. Không lấy giá trị này nhân 100 để thành CPU%.

### Lỗi 4 — Coi `getProcessCpuLoad()=0.02` nghĩa app không có lỗi CPU

Nó chỉ phản ánh tải process gần đây theo scope. Workload có thể có spikes ngắn, bị throttled hoặc đang chờ I/O; đồng thời một thread đang 100% của một core nhưng tỷ lệ trên toàn hệ thống vẫn thấp.

### Lỗi 5 — Trừ hai phần trăm để tìm CPU các tiến trình khác

`getCpuLoad()-getProcessCpuLoad()` không phải thuật toán phân bổ CPU chuẩn vì cửa sổ/scope/mẫu số khác nhau. Cần per-process OS counters cùng interval.

### Lỗi 6 — Coi 100% luôn là một core

Nhiều công cụ OS dùng core làm 100%, trong khi một số API chuẩn hóa theo tổng capacity. Ghi rõ quy tắc display và denominator.

### Lỗi 7 — Quên container và CPU quota

Nếu JVM ở trong container, operating environment có thể khác host; cgroup CPU quota và throttling là lớp quan trọng. Không dùng một kết quả MXBean duy nhất để định nghĩa host CPU.

### Lỗi 8 — Đọc `getProcessCpuTime()` rồi tưởng đó là wall time

CPU time tích lũy qua các threads có thể nhanh hơn hoặc chậm hơn wall-clock. Muốn load interval phải lấy chênh lệch CPU và chênh lệch monotonic wall time.

### Lỗi 9 — Chia delta process CPU time cho sai số CPUs

Dùng 16 cores của host khi JVM chỉ được 2 CPUs có thể tạo tỷ lệ “rất thấp” dù container đã bão hòa. Ngược lại dùng mẫu số 1 khi process dùng nhiều cores có thể tạo >100%. Đo đúng scope và quota.

### Lỗi 10 — Đọc metric quá nhanh rồi coi là realtime từng mili giây

Javadoc không quy định cửa sổ cố định như thế. Tốc độ gọi cao có thể tạo kết quả nhiễu/cached. Cần sampling policy phù hợp.

### Lỗi 11 — Coi giá trị âm là phần trăm CPU âm

Giá trị âm biểu thị không khả dụng; loại sample khỏi phép tính trung bình, không gắn nhãn `-100%`.

### Lỗi 12 — Ép `-1` thành 0

`Math.max(0, value)` biến “sensor unavailable” thành “system idle”, dẫn tới alert sai. Giữ missing state.

### Lỗi 13 — Chỉ đo application threads, bỏ qua GC/JIT

`getProcessCpuLoad()` là tiến trình JVM **bao gồm internal threads**, không phải riêng controller/service methods. Dùng profiling khi cần xác định nguồn CPU thật.

### Lỗi 14 — Giả định mọi JVM implement extension của Oracle/HotSpot

`com.sun.management.OperatingSystemMXBean` là JDK extension. Dùng `instanceof` và hỗ trợ fallback/unavailable trên runtime khác, không ép kiểu mù.

### Lỗi 15 — So process time trước và sau restart

Counter tích lũy thuộc một process lifetime. Khi PID/process đổi, các chênh lệch qua ranh giới restart không còn hợp lệ.

### Lỗi 16 — Dùng `System.currentTimeMillis()` cho CPU delta

Wall clock có thể bị điều chỉnh; `System.nanoTime()` phù hợp cho elapsed intervals trong cùng JVM.

### Lỗi 17 — Quên `getAvailableProcessors()` có thể đổi

Theo Javadoc, số processors khả dụng có thể thay đổi trong một JVM invocation. Khi quota/cpuset đổi, dashboard phải ghi nhận bối cảnh và tránh dùng denominator cũ vô hạn.

### Lỗi 18 — Cho rằng high CPU môi trường là nguyên nhân duy nhất của latency

Có thể là I/O, network, GC pauses, lock contention, throttling hoặc DB. Xác minh với tracing và các metrics bổ sung.

### Lỗi 19 — Dùng metric động làm expected-output cố định

Một test yêu cầu `environmentCpuLoad=46.1%` sẽ thất bại trên máy khỏe hơn hoặc thời điểm khác. Với unit test, dùng số liệu giả định và kiểm tra công thức; với integration test, chỉ kiểm tra type/range/unavailable handling.

### Lỗi 20 — Chỉ đo “%CPU” mà không ghi cấu hình môi trường

Thiếu OS/JDK, CPU count, host/container labels, quota và interval thì khó so sánh các biểu đồ hay xác định cải thiện do optimization.

## 13. Checklist đo lường trong ứng dụng và dashboard

- [ ] Đã xác định metric là **environment** hay **JVM process** hay **container**.
- [ ] Dùng `getCpuLoad()` hiện hành, không đưa `getSystemCpuLoad()` deprecated vào code mới.
- [ ] Dùng `getProcessCpuLoad()` khi cần CPU của tiến trình JVM.
- [ ] Dùng `getProcessCpuTime()` và `System.nanoTime()` nếu cần tự tính core-equivalents.
- [ ] Chuyển `[0,1]` thành phần trăm bằng `*100`; giá trị âm nghĩa unavailable.
- [ ] Không coi `getSystemLoadAverage()` là CPU percent.
- [ ] Có sampling interval, timestamp, labels và metadata OS/JDK/version.
- [ ] Có warm-up/handling cho lần đo đầu tiên và data gaps.
- [ ] Không lấy hiệu hai tải CPU để khẳng định tải của process khác.
- [ ] Đối với process, biết rằng JVM GC/JIT/native threads cũng dùng CPU.
- [ ] Nếu nằm trong container, xác minh cgroup version, quota, cpuset và throttling.
- [ ] Xác định denominator “100%” của biểu đồ và công cụ OS.
- [ ] Có logs/JFR/thread profiling khi CPU tăng bất thường.
- [ ] Kết hợp CPU với latency, throughput, queue, GC, I/O và error rate.
- [ ] Có giới hạn frequency monitoring, không tạo overhead quá mức.
- [ ] Unit test dùng số liệu synthetic, integration test không so CPU% động với hằng số.
- [ ] Các cảnh báo được xác nhận trên nhiều mẫu, không kích hoạt từ một lần đọc bất thường.
- [ ] Nếu APIs không được hỗ trợ, báo rõ unavailable và không báo CPU idle.
- [ ] Trong review, kiểm tra output có đủ scope, unit và denominator.
- [ ] Kết quả benchmark dùng cùng máy, cùng cấu hình tài nguyên và tải kiểm soát.

## 14. Bài tập thực hành

1. **Phân biệt:** `getCpuLoad()` và `getProcessCpuLoad()` đo đối tượng khác nhau như thế nào?
2. **Java 14:** tên lịch sử nào đã deprecated trong Java 14 và nên thay bằng tên nào?
3. **Giá trị:** nếu `getCpuLoad()=0.72`, hiển thị dưới dạng % là bao nhiêu? Có phải riêng JVM 72% không?
4. **Hai phạm vi:** environment 90%, process 5% có cho phép kết luận 85% là CPU của database không? Vì sao?
5. **Tiến trình:** nêu ít nhất ba loại threads/hoạt động nằm trong `getProcessCpuLoad()` ngoài business handler.
6. **Process time:** trong 2 giây wall time, JVM tích lũy 3 CPU-seconds. Nó sử dụng bao nhiêu core-equivalents?
7. **Denominator:** 1,5 core-equivalents tương ứng bao nhiêu % với 4 cores? Với 8 cores?
8. **API unavailable:** `getProcessCpuLoad()` trả `-1.0`. Dashboard phải làm gì?
9. **Load average:** vì sao `getSystemLoadAverage()=2.5` không tương đương 250% CPU utilization?
10. **Code:** chạy `CpuScopeMonitor.java` trên JDK17+ và giải thích vì sao stdout không nhất thiết giống mẫu.
11. **CPU sample:** tại sao các phép `getCpuLoad()`/`getProcessCpuLoad()` không được đảm bảo có cùng observation window?
12. **Container:** một JVM gần 100% CPU quota nhưng host còn nhàn. Số liệu có mâu thuẫn không?
13. **Linux cgroup:** `cpu.stat usage_usec` đo gì? Nó có mặc định chỉ đo một JVM không?
14. **Throttling:** metric nào giúp phân biệt application không dùng CPU vì hết quota với application không có việc?
15. **JMX:** interface nào có `getSystemLoadAverage()`, và extension nào có cặp CPU load methods?
16. **Latency:** nếu JVM process 2% nhưng request p99 tăng, cần điều tra những gì?
17. **Kiểm thử:** thiết kế một unit test cho formatter xử lý `-1`, `NaN`, `0`, `0.5` và `1.0`.
18. **Sampling:** nếu lấy `getProcessCpuTime()` của process A rồi so với process B sau restart, công thức có còn đúng không?
19. **CPU count:** cho biết tác động có thể có khi thay `-XX:ActiveProcessorCount=2` so với cgroup quota thật.
20. **Observability:** đề xuất dashboard hiển thị environment load, JVM process load, container usage, quota throttling, latency và GC, với nhãn scope.

**Đáp án định hướng:** (1) môi trường và tiến trình JVM; (2) `getSystemCpuLoad()` → `getCpuLoad()`; (3) 72%, không phải riêng JVM; (4) không thể trừ trực tiếp; (5) GC/JIT/VM/native threads; (6) 1,5; (7) 37,5% và 18,75%; (8) unavailable; (9) load average không phải phần trăm; (10) tải thay đổi động; (11) Javadoc implementation-specific; (12) không, mẫu số khác; (13) CPU của cgroup, có thể nhiều processes; (14) `nr_throttled`/`throttled_usec` cùng CPU pressure; (15) `java.lang.management.OperatingSystemMXBean` và `com.sun.management.OperatingSystemMXBean`; (16) I/O, lock, cgroup, external services, GC; (17) cần formatter có guard; (18) không; (19) thay JVM CPU ergonomics chứ không tự thay OS quota; (20) scope/interval/denominator rõ ràng.

## 15. Tài liệu chính thức, còn áp dụng

- **Oracle Java SE 17 Javadoc — `com.sun.management.OperatingSystemMXBean`:** `getCpuLoad()`, `getProcessCpuLoad()`, `getProcessCpuTime()`, `getSystemCpuLoad()` deprecated từ Java 14: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html
- **Oracle Java SE 25 Javadoc — `com.sun.management.OperatingSystemMXBean`:** các API còn hiện hành, phạm vi operating environment có thể native/VM/container, khoảng quan sát implementation-specific: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html
- **Oracle Java SE 25 Javadoc — `java.lang.management.OperatingSystemMXBean`:** `getAvailableProcessors()`, `getSystemLoadAverage()` không phải CPU usage fraction: https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html
- **Oracle Java SE 17 Management Guide — Platform MXBeans:** cách truy cập JDK-specific `com.sun.management` qua `ManagementFactory`: https://docs.oracle.com/en/java/javase/17/management/using-platform-mbean-server-and-platform-mxbeans.html
- **Oracle JDK 25 — The java Command:** `-XX:ActiveProcessorCount` và `UseContainerSupport`, ý nghĩa giới hạn JVM processors: https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **Linux kernel — cgroup v2 CPU Interface:** `cpu.stat`, `usage_usec`, `nr_throttled`, `throttled_usec`, `cpu.max`, `cpu.pressure` và các giới hạn phạm vi: https://docs.kernel.org/admin-guide/cgroup-v2.html
- **Oracle Java SE 17 Javadoc — `ThreadMXBean`:** CPU time từng thread (khác process time): https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- **Oracle Java SE 17 Javadoc — `ProcessHandle.Info`:** `totalCpuDuration()` là lựa chọn Java SE khác khi có hỗ trợ, nhưng cần kiểm tra `Optional` và vòng đời process: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessHandle.Info.html

**Ghi nhớ:** `getCpuLoad()` là CPU gần đây của **toàn operating environment**, `getProcessCpuLoad()` là CPU gần đây của **tiến trình JVM hiện tại**, và `getProcessCpuTime()` là **tổng CPU time tích lũy** chứ không phải một tỷ lệ. Cả hai CPU load fractions có giá trị hợp lệ **0..1** hoặc **âm nếu không khả dụng**; observation window phụ thuộc JDK/OS. **Không trừ hai số như thể có cùng mẫu số; không nhầm load average với CPU%; không dùng tên deprecated `getSystemCpuLoad()` trong code mới.** Trong môi trường container, bổ sung cgroup quota/throttling và OS metrics trước khi kết luận hệ thống bão hòa hoặc cần scale.