# Chu kỳ lấy mẫu và giá trị biểu thị không có số liệu trong Java System Metrics

> **Bối cảnh:** Java 14 → **Số liệu hệ thống**. Bài làm rõ chu kỳ lấy mẫu, khoảng thời gian quan sát của các số liệu CPU/OS, cách hiểu giá trị âm biểu thị không có dữ liệu và sự khác biệt giữa polling MXBean với sự kiện JFR định kỳ. `com.sun.management.OperatingSystemMXBean.getCpuLoad()` xuất hiện từ **Java 14**; toàn bộ API và ví dụ bên dưới vẫn phù hợp Java 17+ và JDK hiện hành, không dạy phương thức đã deprecated như giải pháp mới.

## 1. Mục tiêu

Sau khi học, bạn có thể:

1. Phân biệt **khoảng poll**, **cửa sổ đo nội bộ**, **event period** và **độ trễ callback**.
2. Đọc `getCpuLoad()`, `getProcessCpuLoad()`, `getSystemLoadAverage()`, `getProcessCpuTime()` mà không nhầm ý nghĩa và đơn vị.
3. Phân biệt **0.0 = CPU rảnh theo phép đo hợp lệ** với **giá trị âm = không có số liệu**.
4. Hiểu vì sao lần đầu gọi các CPU load APIs có khoảng quan sát **không xác định** và không cam kết nhận số đo hợp lệ ngay lập tức.
5. Nhận biết người gọi khác có thể ảnh hưởng cửa sổ đo của `getCpuLoad()`, dù ứng dụng tự poll một nhịp cố định.
6. Dùng timestamp, đồng hồ monotonic và trạng thái mẫu để xuất metrics đáng tin cậy.
7. Tính CPU utilization từ chênh lệch `getProcessCpuTime()`, loại bỏ các mẫu không hợp lệ.
8. Phân biệt JFR `jdk.CPULoad#period` với OS MXBean recent CPU usage và callback `RecordingStream.onEvent`.
9. Viết/chạy ba chương trình Java 17+ gồm live polling, phép phân loại mẫu có output cố định và JFR periodic streaming.
10. Thiết kế dashboard không biến unavailable thành zero, không hiển thị mẫu cũ như mẫu mới và có metric coverage.
11. Hiểu ảnh hưởng của container/OS/runtime image và áp dụng checklist test, xử lý sự cố.

**Nguyên tắc:** Tần suất chương trình **gọi** một API không nhất thiết là chu kỳ mà API **đo** dữ liệu. Và **missing không phải 0**.

## 2. Phân biệt nguồn và kiểu metric

Java cung cấp nhiều nguồn chẩn đoán:

| Nguồn | API | Giá trị | Ý nghĩa thời gian |
| --- | --- | --- | --- |
| OS MXBean chuẩn | `java.lang.management.OperatingSystemMXBean` | `getSystemLoadAverage()`, `getAvailableProcessors()` | Load average 1 phút, CPU hữu dụng nhìn từ JVM |
| OS MXBean mở rộng | `com.sun.management.OperatingSystemMXBean` | `getCpuLoad()`, `getProcessCpuLoad()` | Recent CPU load theo khoảng đo do implementation quyết định |
| OS MXBean mở rộng | `getProcessCpuTime()` | Counter CPU time tích lũy, đơn vị nanoseconds | Cần hai lần đo hợp lệ để tính một rate |
| JFR | `jdk.CPULoad` và `RecordingStream` | Periodic event CPU metrics | Event phát định kỳ, consumer nhận sau flush/dispatch |
| ThreadMXBean | `java.lang.management.ThreadMXBean` | CPU time theo platform thread | Counter có thể unavailable/disabled |
| Runtime/MemoryMXBean | `Runtime` và các memory beans | Heap/processor state | Snapshot, không đồng nghĩa recent CPU load |

### 2.1. Hai interfaces trùng tên

`ManagementFactory.getOperatingSystemMXBean()` trả interface chuẩn `java.lang.management.OperatingSystemMXBean` (module `java.management`). Với JDK có extension management, object còn implement `com.sun.management.OperatingSystemMXBean` (module `jdk.management`).

```java
java.lang.management.OperatingSystemMXBean base =
        java.lang.management.ManagementFactory
                .getOperatingSystemMXBean();

if (base instanceof com.sun.management.OperatingSystemMXBean os) {
    double cpu = os.getCpuLoad();
    // Xử lý theo miền giá trị và trạng thái availability.
}
```

Đây là đoạn minh họa bên trong method, không phải chương trình tự chạy. Kiểm tra `instanceof` giúp không giả định mọi JVM/remote implementation đều cung cấp extension.

### 2.2. Tên API còn áp dụng trong Java hiện hành

Theo Javadoc Java SE 25, các method sau có từ **Java 14** và tiếp tục hỗ trợ:

- `getCpuLoad()`: recent CPU usage của operating environment.
- `getTotalMemorySize()` và `getFreeMemorySize()`: các số liệu memory tương ứng.

Các tên lịch sử `getSystemCpuLoad()`, `getTotalPhysicalMemorySize()` và `getFreePhysicalMemorySize()` được **deprecated since Java 14**; trong code mới hãy dùng các method thay thế nêu trên. `getProcessCpuLoad()` và `getProcessCpuTime()` cũng vẫn là API được tài liệu hóa, không cần dùng tên cũ.

Bài tập trung vào chu kỳ và số liệu unavailable, không xem sự có mặt của một getter là bằng chứng OS lúc nào cũng có dữ liệu cho getter đó.

## 3. Bốn mốc thời gian không thể gộp làm một

Giả sử một monitor dự định đọc CPU mỗi giây:

```text
App poll:     t0         t1         t2         t3
              |----------|----------|----------|
              schedule ~1 giây, có thể trễ bởi scheduler

MXBean:       [recent observation windows]
              phụ thuộc implementation và caller trước đó

JFR producer:    E0          E1         E2
                 |  period do JFR cấu hình

JFR consumer:        C0             C1      C2
                      |  thêm đệm/flush/dispatch
```

1. **Polling interval:** Khoảng giữa các lần ứng dụng gọi một method; tự đặt qua `Thread.sleep()`, `ScheduledExecutorService` hoặc framework.
2. **Observation interval:** Khoảng mà `getCpuLoad()` và `getProcessCpuLoad()` dùng để tính recent usage. Javadoc ghi rõ **implementation-specific** và thường liên quan thời lượng kể từ lần gọi trước.
3. **Event period:** Setting `jdk.CPULoad#period` trong JFR, hoặc `withPeriod(Duration)`, điều chỉnh nhịp tạo periodic event.
4. **Callback/arrival latency:** Thời gian từ event được tạo đến lúc consumer nhận; chịu ảnh hưởng của flush, batch, thread scheduling và callback work.

**Không có hợp đồng:** `Thread.sleep(1000)` → method được gọi đúng cách nhau 1000 ms → MXBean đo đúng 1000 ms → JFR callback đúng mỗi 1000 ms. Đây là bốn khái niệm khác nhau.

### 3.1. Khoảng gọi thực tế cần được đo

`Thread.sleep(1000)` chỉ yêu cầu thread nghỉ tối thiểu khoảng một giây; nó có thể thức dậy muộn do scheduler, GC, CPU throttling. Để xem khoảng cách giữa hai lần lấy mẫu, dùng `System.nanoTime()`:

```java
long t0 = System.nanoTime();
// Đọc mẫu thứ nhất.

Thread.sleep(1000);

long t1 = System.nanoTime();
// Đọc mẫu thứ hai.

double actualSeconds = (t1 - t0) / 1_000_000_000.0;
```

Đây là đoạn minh họa trong một method `throws InterruptedException`. `actualSeconds` phản ánh khoảng do caller quan sát, **không** chứng minh MXBean cũng đo chính xác khoảng đó. `System.nanoTime()` phục vụ tính elapsed time; không phải Unix timestamp. Muốn gắn mốc lịch cho dashboard, dùng thêm `Instant.now()`.

## 4. `getCpuLoad()` — CPU usage của môi trường

Javadoc `com.sun.management.OperatingSystemMXBean.getCpuLoad()` Java SE 25 quy định:

- Trả một `double` trong **`[0.0,1.0]`** khi có dữ liệu hợp lệ.
- `0.0` nghĩa là CPUs nhàn rỗi trong recent period.
- `1.0` nghĩa là CPUs bận toàn bộ trong recent period.
- Giá trị trong khoảng thể hiện mức sử dụng tương đối.
- **Giá trị âm** nghĩa là CPU usage **không có số liệu**.
- Chu kỳ quan sát do **implementation quyết định**.
- Ở **lần gọi đầu tiên**, recent observation period **không xác định**.
- Các caller khác có thể ảnh hưởng observation interval và kết quả.

| Raw value | Diễn giải |
| ---: | --- |
| `0.0` | Hợp lệ: 0% CPU usage |
| `0.125` | Hợp lệ: 12,5% |
| `0.75` | Hợp lệ: 75% |
| `1.0` | Hợp lệ: 100% |
| `-1.0` | **UNAVAILABLE**, không phải -100% |
| `-0.01` | **UNAVAILABLE** vì Javadoc nói negative, không chỉ đúng `-1.0` |
| `NaN` hoặc `Infinity` | Không thuộc miền API công bố; nên phân loại **INVALID** |
| `1.1` | Vượt miền `[0,1]`, nên phân loại **INVALID** |

**Không đổi `-1.0` thành `0.0`.** Nếu bạn làm vậy, dashboard nói hệ thống không dùng CPU dù thực tế collector chưa đo được.

### 4.1. Lần đầu không có cam kết giá trị

Câu «first observation period is undefined» không đồng nghĩa lần đầu *luôn* trả -1. Có JVM trả negative trong lần đầu; có JVM có thể trả một ratio hợp lệ. Logic đúng là kiểm tra **giá trị thực tế của từng lần gọi** chứ không dựa vào chỉ số lần gọi.

Tương tự, «sau lần thứ hai chắc chắn có dữ liệu» cũng không phải bảo đảm. Nếu OS không hỗ trợ metric, một số mẫu hoặc tất cả mẫu có thể unavailable.

### 4.2. Caller khác có thể làm thay đổi cửa sổ

Ví dụ:

```text
Collector A: t=0.0s              t=1.0s
Collector B:         t=0.4s               t=1.4s
```

Nếu implementation dùng lần gọi gần nhất để xác định window, A không chắc luôn đo đúng 1.0 giây từ lần trước của **riêng A**. Java API Note cảnh báo các observers khác có thể tác động observation interval.

Một thiết kế vận hành tốt là có **một sampler chung** rồi chia sẻ giá trị đã được đánh dấu timestamp/status cho nhiều thành phần. Không để nhiều dashboard, library, autoscaler đọc cùng MXBean với polling nhịp rất ngắn và khác nhau nếu điều đó làm nhiễu phép đo.

## 5. `getProcessCpuLoad()` — recent usage của JVM process

`getProcessCpuLoad()` có miền kết quả tương tự:

- Ratio hợp lệ: `[0.0,1.0]`.
- Negative: unavailable.
- First observation period undefined.
- Recent observation interval implementation-specific.
- Có thể bị ảnh hưởng bởi caller khác.

Khác `getCpuLoad()` ở **scope**: metric chỉ CPU usage **của JVM process**, bao gồm application threads **và** các internal JVM threads như GC/JIT. Nó không phải metric CPU riêng của một Java thread.

Giả sử:

```text
overallCpuLoad = 0.80   -> 80%
processCpuLoad = 0.15   -> 15%
```

Có thể nghi ngờ phần đáng kể CPU load đến từ các processes khác, nhưng không suy ra chính xác «65% thuộc một process cụ thể». Scope, thời gian quan sát và container/VM accounting có thể khác nhau.

**Lưu ý làm tròn:** Raw process CPU `0.002` là 0,2%; ép về số nguyên `(int)(cpu*100)` sẽ in 0 nhưng không có nghĩa số liệu 0 tuyệt đối. Nên giữ raw double trong telemetry; làm tròn chỉ tại tầng hiển thị.

## 6. `getSystemLoadAverage()` — một phút nhưng không phải CPU %

`java.lang.management.OperatingSystemMXBean.getSystemLoadAverage()` trả **system load average của một phút**, liên quan số runnable entities đang chạy hoặc chờ processor. OS có thể dùng cơ chế làm mượt và công thức riêng.

- Nonnegative → có số liệu hợp lệ.
- Negative → không có số liệu.
- Giá trị **lớn hơn 1** hoàn toàn có thể hợp lệ.
- Gọi method mỗi 100 ms không biến nó thành «load average 100 ms».

```java
var bean = java.lang.management.ManagementFactory
        .getOperatingSystemMXBean();
double avg = bean.getSystemLoadAverage();
System.out.println(avg < 0 ? "UNAVAILABLE" : avg);
```

Đây là snippet trong method; stdout phụ thuộc OS.

Một load average `4.0` **không phải 400% CPU**. Dù bạn chia load average cho `availableProcessors()` để tạo chỉ báo mang tính tương đối, đó vẫn không phải `getCpuLoad()` theo Java API. Trong container, số processors khả dụng và scope của load average có thể khác nhau.

## 7. `getProcessCpuTime()` — counter CPU time, không phải CPU load

`com.sun.management.OperatingSystemMXBean.getProcessCpuTime()` trả CPU time tích lũy của JVM process tính bằng **nanoseconds** (đơn vị ns, độ chính xác không nhất thiết đến từng ns).

- Kết quả **`-1`** là sentinel **operation not supported**.
- Counter không phải CPU phần trăm; nó có thể tăng hơn một giây CPU time trong một giây wall time nếu nhiều threads chạy song song.
- Để suy ra usage, cần ít nhất hai mẫu hợp lệ từ **cùng process** và elapsed wall time hợp lệ.

Ví dụ toán học:

```text
wall:    0s       -> 1s          deltaWall = 1s
CPU:    10s       -> 12s         deltaCPU  = 2s

coreEquivalents = deltaCPU / deltaWall = 2 cores
normalizedCpu   = deltaCPU / (deltaWall * availableCPUs)
```

Với 4 CPUs: normalized CPU = `2/(1*4)=50%`. Với 2 CPUs: normalized CPU = `2/(1*2)=100%`. Đây là phép chuẩn hóa **do collector định nghĩa**, không phải con số mà mọi version của `getProcessCpuLoad()` bắt buộc phải khớp.

### 7.1. Khi nào không được tính delta?

Đừng lấy chênh lệch nếu:

1. Một trong hai CPU counters là `-1`.
2. Counter sau nhỏ hơn counter trước do reset, restart hoặc không cùng source.
3. `deltaWall <= 0`.
4. CPU count denominator bằng 0 hoặc không thể xác định cùng scope.
5. Đo qua thay đổi CPU quota/affinity lớn mà vẫn giả định số CPU luôn cố định.
6. Poll quá dày khiến counter chưa cập nhật theo độ phân giải thực tế.

Khi gặp điều kiện trên, trả **UNAVAILABLE/INVALID** với lý do, không dùng 0 để thay thế.

## 8. Sentinel phải đọc theo từng API, không có `-1` chung cho mọi metric

| API | Quy tắc unavailable theo tài liệu | Chú ý |
| --- | --- | --- |
| `getCpuLoad()` | **Bất kỳ giá trị âm** | `0.0` là idle hợp lệ |
| `getProcessCpuLoad()` | **Bất kỳ giá trị âm** | Không phải CPU của một Java thread |
| `getSystemLoadAverage()` | **Bất kỳ giá trị âm** | Load average có thể > 1 |
| `getProcessCpuTime()` | Chính xác **`-1`** | Counter CPU time ns |
| `getCommittedVirtualMemorySize()` | Chính xác **`-1`** khi không hỗ trợ | Byte count, không phải CPU load |
| `ThreadMXBean.getThreadCpuTime(id)` | **`-1`** khi thread không sống/không tồn tại, measurement disabled hoặc virtual thread theo JDK hiện hành | Phải kiểm tra khả năng hỗ trợ và enabled |
| `getFreeMemorySize()` / `getTotalMemorySize()` | Theo contract memory method tương ứng | Không tự suy ra negative CPU rule cho mọi memory getter |
| JFR `jdk.CPULoad` | Có thể **không có event trong khoảng quan sát** | Event vắng mặt khác với event có giá trị 0 |

**Ba trạng thái phân biệt:**

- **OK:** API trả dữ liệu đúng miền (kể cả 0).
- **UNAVAILABLE:** API trả sentinel mà tài liệu nói là thiếu dữ liệu.
- **INVALID:** API trả value ngoài miền chuẩn, chẳng hạn `NaN` hoặc CPU load > 1.

Ngoài ra ở tầng collector có thể có **STALE** (có mẫu cũ nhưng chưa có mẫu mới đúng hạn) và **NOT_SAMPLED** (collector chưa chạy hoặc task bị lỗi).

## 9. Ví dụ Java 17+ 1: poll MXBean ba lần, dữ liệu live

Chương trình hoàn chỉnh, đã được biên dịch bằng `javac --release 17` và chạy thử. Lưu file **`CpuSamplingDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.util.Locale;

public class CpuSamplingDemo {
    static String load(double value) {
        if (!Double.isFinite(value) || value < 0.0) {
            return "UNAVAILABLE";
        }
        if (value > 1.0) {
            return "OUT_OF_RANGE";
        }
        return String.format(Locale.ROOT, "%.1f%%", value * 100.0);
    }

    public static void main(String[] args) throws InterruptedException {
        var base = ManagementFactory.getOperatingSystemMXBean();

        if (!(base instanceof com.sun.management.OperatingSystemMXBean os)) {
            System.out.println("extended-mxbean=UNAVAILABLE");
            return;
        }

        for (int i = 1; i <= 3; i++) {
            double env = os.getCpuLoad();
            double proc = os.getProcessCpuLoad();
            double avg = base.getSystemLoadAverage();
            long cpuTime = os.getProcessCpuTime();

            System.out.println("sample=" + i
                    + " env=" + load(env)
                    + " process=" + load(proc)
                    + " load-average=" +
                    (Double.isFinite(avg) && avg >= 0.0
                            ? "AVAILABLE" : "UNAVAILABLE")
                    + " process-cpu-time=" +
                    (cpuTime >= 0 ? "AVAILABLE" : "UNAVAILABLE"));

            if (i < 3) Thread.sleep(1000);
        }
    }
}
```

Biên dịch/chạy với JDK 17+ có module `jdk.management`:

```bash
javac --release 17 CpuSamplingDemo.java
java CpuSamplingDemo
```

**Một stdout thực tế từ lần chạy thử** (không phải kết quả cố định):

```text
sample=1 env=UNAVAILABLE process=3.5% load-average=UNAVAILABLE process-cpu-time=AVAILABLE
sample=2 env=50.8% process=0.3% load-average=UNAVAILABLE process-cpu-time=AVAILABLE
sample=3 env=46.9% process=0.2% load-average=UNAVAILABLE process-cpu-time=AVAILABLE
```

**Giải thích code:**

1. `ManagementFactory` lấy bean chuẩn, `instanceof` bảo đảm extension tồn tại trước khi dùng.
2. `getCpuLoad()` và `getProcessCpuLoad()` lấy hai scopes khác nhau.
3. `load` hiển thị negative/non-finite là UNAVAILABLE và ngoài khoảng > 1 là OUT_OF_RANGE; trong hệ thống thực cần phân loại non-finite là INVALID như phần 8.
4. `getSystemLoadAverage()` chỉ kiểm tra nonnegative; không nhân 100 như CPU fraction.
5. `getProcessCpuTime()` dùng `>= 0` để quyết định counter có dữ liệu, không coi nó là percentage.
6. `Thread.sleep(1000)` đặt nhịp gọi gần một giây, không ràng buộc observation interval của MXBean.
7. Chương trình kết thúc hữu hạn sau ba samples; không tạo background scheduler còn chạy.

**Không thể hardcode stdout:** Mỗi OS/JDK/container và mức tải CPU khác nhau; ngay lần đầu một API cũng có thể trả giá trị hợp lệ hoặc unavailable. Điều có thể QA là code compile được, phân loại đúng miền giá trị và không in CPU âm thành phần trăm.

## 10. Ví dụ Java 17+ 2: dữ liệu giả lập có output chính xác

Đây là chương trình để unit-test logic «0 khác missing» và công thức counter delta **không phụ thuộc OS**.

Lưu file **`MetricSemanticsDemo.java`**:

```java
import java.util.Locale;

public class MetricSemanticsDemo {
    static String format(double v) {
        if (!Double.isFinite(v)) return "INVALID";
        if (v < 0) return "UNAVAILABLE";
        if (v > 1) return "INVALID";
        return String.format(Locale.ROOT, "%.1f%%", v * 100.0);
    }

    static String normalized(long cpuDeltaNs,
                             long wallDeltaNs, int cpus) {
        if (cpuDeltaNs < 0 || wallDeltaNs <= 0 || cpus <= 0) {
            return "UNAVAILABLE";
        }
        return format((double) cpuDeltaNs /
                      ((double) wallDeltaNs * cpus));
    }

    public static void main(String[] args) {
        System.out.println("negative=" + format(-1));
        System.out.println("idle=" + format(0));
        System.out.println("half=" + format(0.5));
        System.out.println("nan=" + format(Double.NaN));

        System.out.println("two-on-four=" +
                normalized(2_000_000_000L, 1_000_000_000L, 4));
        System.out.println("two-on-two=" +
                normalized(2_000_000_000L, 1_000_000_000L, 2));
        System.out.println("invalid-delta=" +
                normalized(-1L, 1_000_000_000L, 2));
    }
}
```

```bash
javac --release 17 MetricSemanticsDemo.java
java MetricSemanticsDemo
```

**Stdout chính xác** (đã kiểm thử trên JDK hiện hành với target Java 17):

```text
negative=UNAVAILABLE
idle=0.0%
half=50.0%
nan=INVALID
two-on-four=50.0%
two-on-two=100.0%
invalid-delta=UNAVAILABLE
```

**Cách diễn giải:**

- Negative = không có dữ liệu.
- 0 = phép đo hợp lệ, 0%.
- `NaN` không được hợp đồng CPU load quy định làm missing sentinel → INVALID.
- Delta 2 giây CPU trong 1 giây wall = 2 core-equivalents; chia cho bốn CPUs bằng 50%, chia cho hai bằng 100%.
- Không tính delta nếu giá trị CPU time là sentinel.

**Mẫu synthetic này chỉ kiểm tra công thức**, không xác minh phép đo thực trong container, không giả định CPU count không thể thay đổi. Trong code production cần lấy hai giá trị CPU time hợp lệ, wall elapsed đo bằng `System.nanoTime()`, tránh trộn samples trước/sau restart.

## 11. JFR periodic event: `period` riêng, không phải MXBean polling

JFR ghi sự kiện của JVM. Với loại `jdk.CPULoad` hỗ trợ periodic settings, có thể cấu hình:

```java
stream.enable("jdk.CPULoad")
      .withPeriod(java.time.Duration.ofSeconds(1));
```

Đây là snippet trong method có biến `stream` kiểu `RecordingStream`, không phải chương trình độc lập.

Tài liệu `jdk.jfr` Java SE 25 cho ví dụ tên setting **`jdk.CPULoad#period`** với giá trị **`"1 s"`**. Setting `period` điều khiển nhịp producer **phát loại event định kỳ**; nó không hứa mỗi giây callback `onEvent` chắc chắn chạy đúng một lần.

```text
JFR timer/periodic producer
       |
       +-- thu thập event
       |
       v
JFR buffer / flush / batch
       |
       v
EventStream consumer dispatch
       |
       v
onEvent(event)
```

**Tách các trường hợp:**

- Event bị disable → không có dữ liệu ghi.
- Recording vừa start, chạy quá ngắn → có thể chưa có event phù hợp.
- Event đã ghi nhưng chưa flush → callback có thể chưa thấy.
- Consumer chậm hoặc close sớm → thiếu callback quan sát được.
- OS không hỗ trợ một nguồn metrics → không mặc định có event hợp lệ.

Không có event **không** đồng nghĩa CPU 0%. Và JFR event with period **không** có cùng semantics với gọi `getCpuLoad()` qua MXBean.

### 11.1. `onFlush` không phải lệnh ép flush mỗi giây

Nếu đăng ký `stream.onFlush(action)`, callback đó được gọi theo cơ chế stream khi dữ liệu đã flush; nó **không** đặt lịch flush cho mỗi CPU sample, không đảm bảo `period=1s` tạo một batch 1s.

Độ trễ nhận event qua JFR gồm buffering, dispatch, callback scheduling. Một event có `getEndTime()` trước timestamp tại callback; khi phân tích event time, ưu tiên trường thời gian của `RecordedEvent` và giữ arrival time riêng nếu cần.

## 12. Ví dụ Java 17+ 3: quan sát JFR `jdk.CPULoad`

Lưu file **`JfrCpuPeriodDemo.java`**:

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import jdk.jfr.consumer.RecordingStream;

public class JfrCpuPeriodDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger seen = new AtomicInteger();

        try (var stream = new RecordingStream()) {
            stream.enable("jdk.CPULoad")
                  .withPeriod(Duration.ofSeconds(1));

            stream.onEvent("jdk.CPULoad", event -> {
                seen.incrementAndGet();

                double jvmUser = event.getDouble("jvmUser");
                double jvmSystem = event.getDouble("jvmSystem");
                double machine = event.getDouble("machineTotal");

                System.out.println("cpu-event jvmUser=" + jvmUser
                        + " jvmSystem=" + jvmSystem
                        + " machineTotal=" + machine);
            });

            stream.onError(Throwable::printStackTrace);
            stream.startAsync();

            Thread.sleep(3500);
            System.out.println("observed-so-far=" + seen.get());
        }
    }
}
```

Biên dịch/chạy trên JDK 17+ có module `jdk.jfr`:

```bash
javac --release 17 JfrCpuPeriodDemo.java
java JfrCpuPeriodDemo
```

**Một ví dụ stdout thực tế** (không phải output cố định):

```text
cpu-event jvmUser=0.0 jvmSystem=0.03625074028968811 machineTotal=0.4518463909626007
cpu-event jvmUser=0.0021144445054233074 jvmSystem=0.003700277768075466 machineTotal=0.47212493419647217
observed-so-far=2
```

**Giải thích:** `seen` là bộ đếm callback đã nhận tới lúc main đọc `seen.get()`; không nhất thiết bằng số events được tạo/ghi trong toàn bộ vòng đời recording. `startAsync()` chạy consumer ở thread riêng; `AtomicInteger` giúp chia sẻ count an toàn. `Thread.sleep(3500)` không hứa chính xác bao nhiêu lần callback. `try-with-resources` dừng stream khi rời block.

Ba field `jvmUser`, `jvmSystem` và `machineTotal` là các giá trị của event `jdk.CPULoad`. **Đừng áp đặt sentinel contract của MXBean `getCpuLoad()` cho mọi field JFR**: một event có schema riêng và sự vắng mặt của event không phải numeric zero. Kiểm tra event field metadata trên JDK đang chạy nếu xây collector lâu dài.

## 13. Đặt lịch polling đúng cách

Ví dụ đơn giản `Thread.sleep()` phù hợp demo ngắn. Trong service chạy dài hạn, có thể dùng `ScheduledExecutorService`:

```java
// Snippet đặt trong service có vòng đời quản lý rõ:
java.util.concurrent.ScheduledExecutorService scheduler =
        java.util.concurrent.Executors.newSingleThreadScheduledExecutor();

var task = scheduler.scheduleAtFixedRate(() -> {
    // Đọc MXBean, kiểm tra negative/invalid,
    // ghi timestamp thực tế và publish sample.
}, 0, 1, java.util.concurrent.TimeUnit.SECONDS);

// Khi service dừng:
task.cancel(false);
scheduler.shutdown();
```

**Đây chỉ là đoạn code minh họa**, không phải chương trình Java hoàn chỉnh. Trong code thật, xử lý exception trong task để một lần lỗi không làm lịch định kỳ bị dừng, giới hạn công việc và shutdown scheduler đúng vòng đời.

### 13.1. Fixed rate và fixed delay

- `scheduleAtFixedRate` cố bám lịch định sẵn. Nếu task chạy chậm, lần sau có thể khởi động muộn hoặc gần lần trước để bám lịch.
- `scheduleWithFixedDelay` đợi một delay sau khi task **kết thúc** rồi mới khởi chạy tiếp; start-to-start thường dài hơn delay.
- Cả hai **không** thay đổi internal observation interval của `getCpuLoad()`, chỉ thay nhịp gọi.

Việc tăng polling từ 1 giây xuống 1 ms **không bảo đảm chất lượng mẫu tăng**; có thể chỉ đọc các giá trị quá dày so với độ phân giải thật, làm nhiễu dữ liệu và tăng overhead.

### 13.2. Các mốc nên lưu với mỗi sample

Một collector nên ghi:

- **`Instant.now()`** tại thời điểm lấy để biểu diễn thời gian lịch.
- **`System.nanoTime()`** khi cần elapsed duration nội bộ cùng JVM.
- Giá trị raw và **status** đã được chuẩn hóa.
- Nguồn metric và unit (`ratio`, `ns`, `bytes`, `load-average`).
- Target poll period, và thực tế sample spacing nếu quan trọng.

Không dùng `System.nanoTime()` như timestamp Unix epoch hoặc so trực tiếp giữa JVM khác nhau.

## 14. Mô hình trạng thái: OK, UNAVAILABLE, INVALID, STALE

Một hệ thống telemetry có thể biểu diễn:

```text
MetricSample:
  name: "jvm.process.cpu.load"
  capturedAt: "2026-11-07T10:00:05Z"
  unit: "ratio"
  status: "OK"
  value: 0.42

Khi không có số liệu:
  status: "UNAVAILABLE"
  value: null
  reason: "negative CPU-load sentinel"
```

Đây là **mô hình dữ liệu minh họa**, không phải class Java chuẩn hay JSON bắt buộc.

Các trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| **OK** | Có một value đúng miền; **0.0 vẫn hợp lệ** |
| **UNAVAILABLE** | API báo không có số liệu, ví dụ CPU load negative |
| **INVALID** | API trả non-finite/out-of-range, hoặc phép tính delta sai |
| **STALE** | Từng có sample hợp lệ, nhưng chưa có sample mới đúng thời hạn |
| **NOT_SAMPLED** | Collector chưa chạy, task bị lỗi hoặc nguồn bị disable |
| **UNSUPPORTED** | Operation rõ ràng không được platform hỗ trợ, ví dụ counter CPU time = -1 |

Đừng gắn timestamp «bây giờ» cho một sample 30 giây trước rồi hiển thị như số đo mới. Tình trạng stale phải có cơ chế báo và thời điểm last success.

### 14.1. Sai lầm thay unavailable bằng zero

```java
double cpu = os.getCpuLoad();
if (cpu < 0) {
    cpu = 0.0; // SAI: tạo ra một số đo CPU idle giả.
}
```

Đúng hơn:

```java
double cpu = os.getCpuLoad();
if (!Double.isFinite(cpu) || cpu < 0 || cpu > 1) {
    // Không publish 0.0; publish trạng thái và lý do.
} else {
    // 0.0 và mọi giá trị [0,1] đều là hợp lệ.
}
```

Hai snippets giả định có biến `os` là extended OS MXBean và đặt bên trong method. Với số đo CPU âm, trạng thái **UNAVAILABLE**; non-finite hoặc ngoài khoảng được giữ riêng là **INVALID**, không trộn hết vào zero.

### 14.2. Một missing sample có thể làm trung bình sai

Giả sử ba mốc:

```text
t0: 20%   OK
t1: -1    UNAVAILABLE
t2: 40%   OK
```

Lấy trung bình `(20+0+40)/3=20%` sau khi biến -1 thành 0 là **sai**. Có thể tính average `(20+40)/2=30%` trên **hai mẫu OK**, đồng thời báo coverage **2/3 samples**, nhưng không được gọi đó là average chính xác của cả khoảng chưa đo nếu các trọng số thời gian cũng không được biết.

Với time series, có thể để gap/unavailable thay vì nối đường xuyên khoảng thiếu dữ liệu. Nếu ứng dụng nội suy để hiển thị, phải ghi chú «estimated», không giả vờ đã đo được.

## 15. Container, VM và scope OS có thể làm số liệu khác nhau

OS MXBean trả thông tin về **operating environment**. Môi trường đó có thể là hệ điều hành vật lý, VM hoặc container:

- **CPU quota:** Giới hạn lượng CPU time tổng cộng một container được sử dụng.
- **CPU cpuset/affinity:** Giới hạn logical CPUs process có thể chạy trên đó.
- **Available processors của JVM:** Số processors JVM dùng cho nhiều heuristics; có thể khác physical cores.
- **Host process khác:** Có thể góp CPU load ngoài JVM process.
- **OS/platform support:** Một số getters có thể không có dữ liệu, trả sentinel theo contract.

Vì vậy khi so sánh `getCpuLoad()` với `top` trên host, phải hỏi **hai nguồn có cùng scope không?** và **có cùng observation interval không?** Chênh lệch chưa chắc là bug.

Trên Linux cgroup v2, một số lệnh chẩn đoán:

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/memory.max
```

Các path phụ thuộc mount/cgroup version và quyền truy cập; chúng không nhất thiết tồn tại ở mọi container. Trên HotSpot có thể xem JVM hiểu system limits bằng:

```bash
java -XshowSettings:system -version
java -Xlog:os+container=debug -version
```

Đây là **lệnh chẩn đoán**, không phải stdout có định dạng bất biến. Không ép số đo từ host và container bằng nhau nếu scope khác nhau.

### 15.1. Điều tra khi lần đầu unavailable

Không đặt alarm chỉ vì một lần đầu `getCpuLoad()` trả negative. Javadoc cho biết initial period không xác định. Hãy retry theo nhịp phù hợp, vẫn lưu trạng thái, kiểm tra trong nhiều lần liên tiếp, nhưng **không hứa lần thứ hai chắc chắn available**.

Nếu lâu dài luôn unavailable, kiểm tra bean implementation, JDK version, OS support, cgroup visibility và external collectors đang poll cùng nguồn.

## 16. Checklist kiểm thử

### Unit tests cho phân loại raw value

```text
getCpuLoad = -1.0        => UNAVAILABLE
getCpuLoad = -0.001      => UNAVAILABLE
getCpuLoad = 0.0         => OK, 0%
getCpuLoad = 0.25        => OK, 25%
getCpuLoad = 1.0         => OK, 100%
getCpuLoad = 1.01        => INVALID
getCpuLoad = NaN         => INVALID
loadAverage = 4.0        => OK, không phải 400% CPU
processCpuTime = -1      => UNSUPPORTED
```

### Integration tests trên môi trường đích

1. Biên dịch bằng `javac --release 17` và chạy `CpuSamplingDemo` trên OS/JDK mục tiêu.
2. **Không assert một số phần trăm cố định**, chỉ kiểm tra miền hợp lệ/unavailable.
3. Chấp nhận sample đầu unavailable; không hardcode lần hai luôn OK.
4. Ghi khoảng cách thực tế giữa các polls bằng `System.nanoTime()`.
5. Kiểm tra module `jdk.management` khi chạy custom runtime image.
6. Với JFR, bật `jdk.CPULoad` và chạy đủ lâu với deadline hữu hạn; không assert N callbacks trong N giây.
7. Có `onError` để kiểm tra lỗi stream; phân biệt event không đến với event có giá trị CPU 0.
8. Thử stop/restart collector để xác minh STALE và NOT_SAMPLED.
9. Thử synthetic negatives, NaN, 0 và ranh giới 1.0; không cho NaN làm hỏng average.
10. Khi có cgroup, ghi nhận CPU quota/cpuset và OS scope để giải thích khác biệt.
11. Nếu tính counter delta, thử reset/negative/zero wall elapsed và processors thay đổi.
12. Theo dõi missing-sample ratio, collector error count và sample age trong dashboard.

## 17. Lỗi phổ biến

| Nhận định sai | Hành vi đúng |
| --- | --- |
| «Poll mỗi 1s nghĩa là JVM đo đúng 1s». | Observation period do implementation quyết định, có thể bị caller khác ảnh hưởng. |
| «Lần đầu luôn -1, lần hai luôn OK». | First period undefined; xử lý mỗi lần theo raw result. |
| «CPU 0.0 nghĩa là không có dữ liệu». | 0.0 là mẫu hợp lệ, CPU idle. |
| «Chỉ -1.0 mới unavailable». | Javadoc CPU load quy định **bất kỳ negative**. |
| «`getSystemLoadAverage=2` là CPU 200%». | Load average không phải CPU fraction. |
| «`getProcessCpuTime` trực tiếp là phần trăm CPU». | Đó là counter ns, phải lấy delta. |
| «`NaN` là sentinel của `getCpuLoad`». | Javadoc không quy định; coi là invalid. |
| «Mọi method memory đều dùng -1 sentinel». | Kiểm tra contract từng method, không suy rộng. |
| «`withPeriod(1s)` làm JFR callback chạy đúng mỗi giây». | Event producer period và callback timing khác nhau. |
| «Không có JFR event nghĩa CPU = 0». | Có thể event disable, chưa flush, stream đóng hoặc collector chưa bắt đầu. |
| «Thay missing bằng zero chỉ đổi cách trình bày». | Làm sai average, alarms và autoscaling. |
| «`getAvailableProcessors` là số physical cores». | Nó là số processors JVM thấy khả dụng, có thể bị container hạn chế. |
| «Tăng tần suất poll đến 1ms cho accuracy tốt hơn». | Có thể quá nhanh so với counter granularity, thêm overhead. |
| «Một giá trị cũ đủ dùng làm giá trị hiện tại». | Phải đánh dấu stale và last successful timestamp. |
| «Một JVM thread đại diện cả process CPU load». | Process metric gồm app threads, GC, JIT và JVM internal threads. |

## 18. Bài tập và đáp án

### Bài 1 — Negative và zero

`getCpuLoad()` lần lượt là `-1`, `0`, `0.5`. Hãy đổi thành trạng thái.

**Đáp án:** UNAVAILABLE, OK/0%, OK/50%. Không gán -1 là 0.

### Bài 2 — Lịch poll và khoảng đo

Dùng `Thread.sleep(1000)` rồi gọi `getCpuLoad()`; có đo chính xác 1 giây CPU gần nhất không?

**Đáp án:** Không có bảo đảm. Observation interval implementation-specific, scheduling và caller khác tác động được.

### Bài 3 — Lần đầu

Lần đầu `getProcessCpuLoad()` âm. Có phải chắc chắn lỗi Java?

**Đáp án:** Không. First recent observation period undefined; có thể unavailable hợp lệ.

### Bài 4 — Load average

`getSystemLoadAverage()=3.5` có thuộc miền hợp lệ không?

**Đáp án:** Có, nếu OS cung cấp load average. Nó không phải tỷ lệ `[0,1]` và không có nghĩa 350% CPU.

### Bài 5 — CPU time delta

Trong 1 giây wall time, CPU time tăng 2 giây; ngân sách 4 CPUs. Ratio là bao nhiêu?

**Đáp án:** `2/(1*4)=0.5` → 50% của bốn CPUs, theo công thức chuẩn hóa đã định nghĩa.

### Bài 6 — Counter unsupported

CPU time trả `-1`. Có được lấy chênh lệch với counter mẫu kế tiếp không?

**Đáp án:** Không. `-1` là sentinel unsupported; cặp mẫu không hợp lệ.

### Bài 7 — Hai collectors

A poll `getCpuLoad()` mỗi 1s, B poll mỗi 200ms. A có chắc được window đúng 1s?

**Đáp án:** Không. Javadoc cảnh báo callers khác có thể ảnh hưởng observation interval.

### Bài 8 — JFR

`jdk.CPULoad` được enable với period 1s, chương trình 3s nhận một callback. Các giây khác CPU có bằng 0 không?

**Đáp án:** Không. Callback qua JFR batching/flush; không nhận được event không phải sample numeric zero.

### Bài 9 — `NaN`

CPU metric trả `Double.NaN`. Nên ghi 0% hay unavailable chuẩn theo Javadoc?

**Đáp án:** Không. Đây là INVALID so với miền Javadoc; cần chẩn đoán.

### Bài 10 — Stale data

Collector lỗi 30s nhưng dashboard vẫn hiển thị «CPU 30% hiện tại» từ sample cũ.

**Đáp án:** Sai. Phải hiển thị last sample time và trạng thái STALE.

### Bài 11 — Average và coverage

Các mẫu là 20%, missing, 40%. Trung bình nào có thể báo?

**Đáp án:** Average 30% **trên hai mẫu hợp lệ** nếu cùng trọng số, kèm coverage 2/3; không coi đó là đo đầy đủ toàn giai đoạn.

### Bài 12 — Source scope

`getCpuLoad` trả 80%, `getProcessCpuLoad` trả 20%. Có thể chắc chắn 60% thuộc một process khác không?

**Đáp án:** Không. Cần so scope và window, có thể có nhiều processes khác hoặc chênh lệch môi trường đo.

### Bài 13 — Java 14 API

Trong code Java 17+ nên gọi `getCpuLoad()` hay `getSystemCpuLoad()`?

**Đáp án:** Dùng `getCpuLoad()` vì `getSystemCpuLoad()` đã deprecated since 14.

### Bài 14 — Giá trị ratio ngoài miền

Nếu `getCpuLoad()` trả `1.2`, nên clamp xuống 100% không?

**Đáp án:** Không nên che lỗi. Giá trị ngoài `[0,1]` nên được đánh dấu INVALID và xem lại provider/OS scope.

## 19. Checklist triển khai

1. Chọn **đúng source và scope**: OS environment, JVM process, platform thread, JFR event.
2. Ghi **unit** rõ ràng: CPU ratio, load average, CPU time ns hoặc memory bytes.
3. Xác định **poll interval** riêng, không tự đồng nhất với internal window.
4. Với JFR, cấu hình **event period** và kiểm tra delivery latency riêng.
5. Xử lý sentinel **theo API**, không có rule -1 cho mọi metric.
6. Tách **OK/UNAVAILABLE/INVALID/STALE/NOT_SAMPLED** khỏi giá trị.
7. Không xuất zero khi dữ liệu missing.
8. Theo dõi **sample coverage**, last success và scheduler jitter.
9. Dùng `System.nanoTime()` cho elapsed, `Instant.now()` cho timestamp.
10. Tránh nhiều caller polling cùng nguồn với nhịp quá dày.
11. Tính CPU rate từ counter chỉ khi cả hai mẫu hợp lệ và denominator được xác định.
12. Không clamp giá trị out-of-range mà không chẩn đoán.
13. Kiểm tra module và OS capabilities trong custom runtime/container.
14. Dùng integration test không hardcode CPU percent, không hardcode JFR event count.
15. Tối ưu cadence theo nhu cầu giám sát, không tối đa hóa tần suất mù quáng.
16. Chú thích rõ khi dashboard nội suy/giữ giá trị cũ.

## 20. Tài liệu chính thức còn áp dụng

1. [Java SE 25 — `com.sun.management.OperatingSystemMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): `getCpuLoad` Since 14, implementation-specific observation period, first invocation undefined, negative unavailable; `getProcessCpuLoad` và `getProcessCpuTime`; các method memory hiện hành.
2. [Java SE 17 — `com.sun.management.OperatingSystemMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): đối chiếu API khi biên dịch `--release 17`.
3. [Java SE 25 — `java.lang.management.OperatingSystemMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html): `getSystemLoadAverage()` và `getAvailableProcessors()`.
4. [Java SE 25 — `ThreadMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html): các trường hợp `getThreadCpuTime` không có dữ liệu.
5. [Java SE 25 — JFR package `jdk.jfr`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html): cấu hình periodic event `jdk.CPULoad#period`.
6. [Java SE 25 — `EventSettings`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): `withPeriod(Duration)`.
7. [Java SE 25 — `RecordingStream`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): streaming periodic events qua `onEvent`/`startAsync`.
8. [Java SE 25 — `EventStream`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): batch delivery, flush và callback lifecycle.
9. [Java SE 25 — `ScheduledExecutorService`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): fixed rate/fixed delay và scheduler caveats.
10. [Java SE 25 — `System.nanoTime`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()): đo thời gian monotonic.
11. [Java SE 25 — `java` launcher options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XshowSettings:system` và `-Xlog:os+container`.
12. [dev.java — Configure JFR](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/): JFR settings và event period.

**Ghi nhớ:** `getCpuLoad()` của Java 14+ cho recent CPU load theo **observation interval do implementation quyết định**, **không** được coi là đúng số giây giữa các lần polling. CPU load **âm là unavailable**, `0.0` mới là CPU 0% hợp lệ. `getProcessCpuLoad()` tương tự; `getSystemLoadAverage()` là 1-minute load average (không phải CPU%), `getProcessCpuTime()` là counter nanoseconds với `-1` unsupported. JFR có `period` riêng, callback có thể trễ. Hệ thống quan sát đúng luôn giữ **value + unit + timestamp + status**, không bịa số 0 cho missing sample.