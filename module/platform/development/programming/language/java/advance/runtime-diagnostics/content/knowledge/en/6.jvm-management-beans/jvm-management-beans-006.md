# 6.6 — Kiểm tra khả năng hỗ trợ, trạng thái bật và giá trị không khả dụng của chỉ số MXBeans

## 1. Vì sao cần kiểm tra trước khi đọc chỉ số?

Platform MXBeans của Java giúp quan sát thread, heap, garbage collection (GC), JIT compilation và runtime qua `java.lang.management`. Nhưng **một getter tồn tại không có nghĩa một phép đo luôn được hỗ trợ, đang bật hoặc có giá trị** trên JVM hiện tại.

Ví dụ: `ThreadMXBean.getCurrentThreadCpuTime()` có thể trả `-1` khi monitoring đang tắt; `MemoryUsage.getMax()` có thể là `-1` vì giới hạn bộ nhớ không xác định; `MemoryPoolMXBean.getUsage()` có thể trả `null` khi pool không còn hợp lệ. Trái lại, `0` có thể là số liệu hợp lệ: 0 lần GC, 0 lần vượt threshold, 0 byte hoặc 0 thời gian được ghi nhận.

Mục tiêu của bài:

1. Kiểm tra **supported**: JVM có cung cấp phép đo này không?
2. Kiểm tra **enabled**: chức năng đo đã bật chưa (nếu API có trạng thái này)?
3. Kiểm tra **available**: mẫu vừa đọc có thực sự hợp lệ theo hợp đồng của method?
4. Phân biệt `0` hợp lệ với `-1`, giá trị âm đặc biệt, `null`, bean không tồn tại và ngoại lệ.
5. Thiết kế log, metrics và dashboard không biến “không biết” thành “bằng 0”.

> **Nguyên tắc:** Đọc capability và trạng thái trước; chỉ khi phù hợp mới đọc value; diễn giải sentinel theo **từng API cụ thể**. Không chuyển giá trị không khả dụng thành 0.

## 2. Mô hình trạng thái cho một phép đo

```text
Xác định JVM/MXBean cần hỏi
    |
    +-- Không có bean / attribute      → NOT_PRESENT
    +-- Lỗi kết nối hoặc quyền          → READ_ERROR
    |
    +-- Nếu API có is...Supported():
    |      false                        → UNSUPPORTED
    |      true                         → tiếp tục
    |
    +-- Nếu API có is...Enabled():
    |      false                        → DISABLED
    |      true                         → tiếp tục
    |
    +-- Đọc getter và áp hợp đồng API:
           null / -1 / negative N/A    → UNAVAILABLE hoặc UNDEFINED
           0 hoặc số hợp lệ            → AVAILABLE
```

Đây là **mô hình phân loại của ứng dụng chẩn đoán**, không phải enum Java cung cấp sẵn.

| Trạng thái | Ý nghĩa | Ví dụ | Điều cần làm |
| --- | --- | --- | --- |
| `UNSUPPORTED` | JVM không hỗ trợ chức năng đo | `isThreadContentionMonitoringSupported() == false` | Không gọi operation phụ thuộc; dùng nguồn khác |
| `DISABLED` | Có hỗ trợ nhưng monitoring/threshold đã tắt | `isThreadCpuTimeEnabled() == false` | Ghi trạng thái, không coi là giá trị 0 |
| `UNAVAILABLE` | Được phép đo nhưng không có mẫu có nghĩa tại điểm đọc | `getThreadCpuTime(id) == -1` khi thread đã kết thúc | Bỏ mẫu, giữ trạng thái và nguyên nhân nếu biết |
| `UNDEFINED` | Một thuộc tính không được runtime định nghĩa | `MemoryUsage.getMax() == -1` | Không tính tỷ lệ cần mẫu số đó |
| `AVAILABLE` | Getter trả giá trị hợp lệ | GC count `0` hoặc CPU time không âm | Lưu giá trị cùng đơn vị/timestamp |
| `NOT_PRESENT` | Bean/attribute không được công bố | `getCompilationMXBean() == null` | Xác minh interface/JDK/vendor; fallback |
| `READ_ERROR` | Không đọc được do quyền, mạng hoặc runtime | lỗi JMX connection, `SecurityException` | Báo lỗi thu thập, không tự gán unsupported |

**Không phải API nào cũng có đủ cả ba hàm supported/enabled/value.** Ví dụ compilation có `isCompilationTimeMonitoringSupported()` nhưng không có `isCompilationTimeMonitoringEnabled()` tương ứng; GC count có `-1` để biểu thị undefined thay vì boolean capability riêng. Không ép tất cả MXBeans vào một khuôn khiến tình trạng bị diễn giải sai.

### 2.1. Quy tắc lựa chọn hành động

1. Xác nhận đúng JVM instance, thời điểm và quyền truy cập.
2. Hỏi `is...Supported()` khi API có phương thức tương ứng.
3. Nếu có công tắc `enabled`, hỏi trạng thái rồi mới đọc.
4. Đọc getter, kiểm tra `null`/sentinel/miền giá trị theo Javadoc.
5. Ghi cả `value`, `unit`, `state`, `source` và mốc thời gian, hoặc ghi state không có value.
6. Xử lý ngoại lệ và race: thread/pool có thể kết thúc giữa check và read.

Một phép đo không hỗ trợ trên JVM A **không** nhất thiết là lỗi trên JVM B; ngược lại, biến động availability sau một lần deploy có thể là tín hiệu cần điều tra.

## 3. ThreadMXBean: kiểm tra CPU time đúng loại thread

Lấy bean chuẩn:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();
```

Đoạn trên là minh họa cần đặt trong method/class. Trên Java 17 có hai kiểm tra **khác nhau**:

- `isCurrentThreadCpuTimeSupported()`: CPU time measurement cho **thread đang gọi**.
- `isThreadCpuTimeSupported()`: CPU time measurement cho **các thread theo ID**. Nếu JVM hỗ trợ đo mọi thread thì cũng hỗ trợ thread hiện tại.

`isThreadCpuTimeEnabled()` cho biết tính năng có đang được bật; việc hỗ trợ và việc bật **độc lập**. Hàm `isThreadCpuTimeEnabled()` có thể ném `UnsupportedOperationException` khi JVM không hỗ trợ CPU time measurement cho cả current thread lẫn other threads, vì vậy không gọi trước capability checks.

### 3.1. Đọc thời gian CPU của thread hiện tại

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
boolean supported = bean.isCurrentThreadCpuTimeSupported();

if (!supported) {
    System.out.println("cpu=UNSUPPORTED");
} else if (!bean.isThreadCpuTimeEnabled()) {
    System.out.println("cpu=DISABLED");
} else {
    long nanos = bean.getCurrentThreadCpuTime();
    System.out.println(nanos < 0 ? "cpu=UNAVAILABLE"
                                 : "cpu=" + nanos + " ns");
}
```

Đây là snippet cần imports và method bao quanh. CPU time đo **thời gian CPU đã thực thi**, không phải tổng wall-clock latency. Giá trị biểu diễn bằng nanosecond nhưng **precision không đồng nghĩa accuracy ở mức nanosecond**.

`getThreadCpuTime(long id)` có thể trả `-1` vì thread không còn sống/không tồn tại, tính năng bị tắt hoặc không có mẫu; đồng thời có thể ném `UnsupportedOperationException` khi không hỗ trợ đo thread khác. Vì vậy một giá trị `-1` đơn lẻ **không xác định được nguyên nhân duy nhất**; cần đối chiếu support, enabled và lifecycle của thread.

### 3.2. Bật measurement có làm thay đổi JVM không?

Có. `setThreadCpuTimeEnabled(true)` có thể làm tăng chi phí đo trên một số JVM, cần quyền quản trị và là **thay đổi trạng thái**. Probe read-only không nên tự bật measurement chỉ vì muốn có số; phải có quyết định vận hành và cách ghi lại thời điểm bắt đầu đo.

Khi bật sau khi một thread đã chạy được một khoảng, JVM có thể chọn mốc bắt đầu đo khác nhau trong giới hạn hợp đồng API. Không khẳng định counter sau khi bật đại diện toàn bộ vòng đời thread.

## 4. Thread contention: supported, enabled và -1

`ThreadMXBean` còn cung cấp:

```java
bean.isThreadContentionMonitoringSupported();
bean.isThreadContentionMonitoringEnabled();
bean.setThreadContentionMonitoringEnabled(true);
```

Đoạn này liệt kê phương thức, không yêu cầu chạy setter. Java 17 quy định contention monitoring có thể không được JVM hỗ trợ và thường **mặc định tắt**.

- `isThreadContentionMonitoringSupported() == false` → `UNSUPPORTED`; gọi `isThreadContentionMonitoringEnabled()` có thể ném `UnsupportedOperationException`.
- `supported == true` nhưng `isThreadContentionMonitoringEnabled() == false` → `DISABLED`.
- Khi bật, `ThreadInfo.getBlockedTime()` và `getWaitedTime()` mới có thể phản ánh thời gian tích lũy, đơn vị **millisecond**.
- `ThreadInfo.getBlockedTime() == -1` hoặc `getWaitedTime() == -1` khi monitoring tắt **không có nghĩa** thời gian chờ âm hoặc “không có contention”.

`ThreadMXBean.isObjectMonitorUsageSupported()` và `isSynchronizerUsageSupported()` lại là hai capability **riêng** khi yêu cầu thông tin monitor và ownable synchronizer qua `getThreadInfo(...)`/`dumpAllThreads(...)`. Không suy từ CPU-time supported sang lock-info supported.

Một thread có thể kết thúc giữa lúc lấy ID và lấy `ThreadInfo`. `getThreadInfo(long id)` trả `null` khi thread không còn sống/không tồn tại; các overload nhận danh sách ID có thể trả array với phần tử `null` tương ứng. Đây là **race/lifecycle**, không chứng minh JVM thiếu ThreadMXBean.

## 5. MemoryPoolMXBean: ngưỡng hỗ trợ và ngưỡng đã bật

Mỗi memory pool có capability khác nhau. Các phương thức quan trọng:

- `isUsageThresholdSupported()` và `isCollectionUsageThresholdSupported()` kiểm tra hai loại threshold độc lập.
- `getUsageThreshold()`, `getCollectionUsageThreshold()` trả ngưỡng tính bằng **byte**, chỉ gọi khi loại tương ứng được hỗ trợ.
- `setUsageThreshold(...)`, `setCollectionUsageThreshold(...)` là thao tác **thay đổi cấu hình**.
- `getUsage()`, `getPeakUsage()` và `getCollectionUsage()` đọc snapshot bộ nhớ; cần kiểm tra null và tính hợp lệ của pool.

### 5.1. Threshold bằng 0 khác với usage bằng 0

Đối với loại threshold **được hỗ trợ**, `threshold > 0` cho biết cơ chế kiểm tra threshold đang bật; `threshold == 0` nghĩa là **tắt threshold checking**. Đây là quy tắc trong `MemoryPoolMXBean`, **không** được áp cho tất cả getter khác.

```java
if (!pool.isUsageThresholdSupported()) {
    System.out.println("threshold=UNSUPPORTED");
} else {
    long threshold = pool.getUsageThreshold();
    System.out.println(threshold == 0
        ? "threshold=DISABLED" : "threshold=ENABLED(" + threshold + " bytes)");
}
```

Đây là snippet cần một biến `MemoryPoolMXBean pool` và ngữ cảnh method. `getUsageThreshold()` trên pool không hỗ trợ có thể ném `UnsupportedOperationException`.

**`getUsageThresholdCount() == 0` không phải trạng thái disabled**: pool có thể bật threshold nhưng chưa từng vượt ngưỡng. Muốn biết chức năng đang bật hay không, đọc cấu hình threshold. Tương tự, một collection usage threshold có capability và giá trị riêng; không lấy support của usage threshold làm đại diện.

### 5.2. Pool hết hiệu lực và MemoryUsage thiếu trường

`pool.isValid()` cho biết pool còn tồn tại trong JVM. `pool.getUsage()` có thể trả `null` nếu pool không còn hợp lệ. Không gọi `usage.getUsed()` khi `usage == null`.

Một `MemoryUsage` có bốn trường:

| Trường | Đơn vị | Ý nghĩa trường hợp đặc biệt |
| --- | --- | --- |
| `getInit()` | byte | `-1` nếu giá trị initial không xác định |
| `getUsed()` | byte | Không âm; `0` có thể hợp lệ |
| `getCommitted()` | byte | Không âm, thông thường ≥ used |
| `getMax()` | byte | `-1` nếu maximum không xác định |

`max == -1` có nghĩa **UNDEFINED**, khác với heap max = 0; không tính `used/max` hoặc phần trăm `used` khi `max <= 0`. `max` cũng không mặc định là giới hạn container hay RSS của process.

```java
MemoryUsage usage = pool.getUsage();
if (usage == null) {
    System.out.println("poolUsage=UNAVAILABLE");
} else {
    long max = usage.getMax();
    System.out.println("poolMax=" +
        (max < 0 ? "UNDEFINED" : max + " bytes"));
}
```

Đoạn này cũng cần đặt trong method và import `MemoryUsage`; nó minh họa cách giữ thông tin undefined. `MemoryPoolMXBean.getUsage()` trả **ước lượng** tại thời điểm đọc, không chứng minh object retention hoặc memory leak.

## 6. GC, JIT và extension MXBeans: mỗi API có hợp đồng riêng

### 6.1. GarbageCollectorMXBean

`ManagementFactory.getGarbageCollectorMXBeans()` trả danh sách collectors JVM công bố. Với mỗi bean:

- `getCollectionCount()` trả counter tích lũy, hoặc **`-1`** nếu count không được định nghĩa.
- `getCollectionTime()` trả tổng thời gian thu gom xấp xỉ (millisecond), hoặc **`-1`** nếu undefined.

`0` có thể nghĩa là chưa có collection, hoặc thời gian đo rất ngắn. Cả `0` và `-1` đều có ý nghĩa khác nhau, đừng gộp. Số lượng/tên GC collector phụ thuộc JDK và GC algorithm; không hard-code một tên như `G1 Young Generation` vào logic đo lường chung.

```java
for (GarbageCollectorMXBean gc :
        ManagementFactory.getGarbageCollectorMXBeans()) {
    long count = gc.getCollectionCount();
    System.out.println(gc.getName() + " count=" +
        (count < 0 ? "UNAVAILABLE" : Long.toString(count)));
}
```

Đây là snippet cần imports và method bao quanh. Nếu danh sách bean rỗng, đó là trạng thái discovery, **không** tự phát counter `0` cho một collector tưởng tượng.

### 6.2. CompilationMXBean

`ManagementFactory.getCompilationMXBean()` có thể trả `null` khi JVM không có compilation system tương ứng. Nếu bean tồn tại, `isCompilationTimeMonitoringSupported()` cho biết có hỗ trợ đo compilation time không; gọi `getTotalCompilationTime()` khi unsupported có thể ném `UnsupportedOperationException`.

Không có hàm enabled chung tương đương `isThreadCpuTimeEnabled()` cho compilation time. `getTotalCompilationTime()` là thời gian tích lũy xấp xỉ của các compilation threads, millisecond; **không** phải số đo hiệu năng có thể so trực tiếp giữa mọi JVM vendor.

### 6.3. Extension của com.sun.management

`com.sun.management.OperatingSystemMXBean` là phần mở rộng trong module `jdk.management`. `getProcessCpuLoad()` trả số trong `[0.0, 1.0]` khi có mẫu, nhưng trả **số âm** nếu unavailable; `0.0` là giá trị hợp lệ. Không mặc định mọi JVM chỉ có giao diện chuẩn `java.lang.management.OperatingSystemMXBean` đều hỗ trợ extension này.

`com.sun.management.ThreadMXBean` mở rộng thêm allocated bytes per thread, với `isThreadAllocatedMemorySupported()`, `isThreadAllocatedMemoryEnabled()` và `getThreadAllocatedBytes(...)`. Đây là extension, nên phải kiểm tra interface/module, capability, enabled và sentinel theo method thực tế trước khi dùng.

**Không áp một “sentinel -1” chung cho mọi loại số:** CPU load dùng số thực âm, memory max dùng -1 undefined, GC count -1 undefined và thread CPU -1 có thể do disabled hoặc thread chết. Từng method có một hợp đồng riêng.

## 7. JMX từ xa: thiếu số đo không giống lỗi kết nối

Đọc MXBean cục bộ thông qua `ManagementFactory` khác với thu thập từ một JMX endpoint từ xa. Với JMX remote, trước cả capability còn cần kiểm tra:

```text
JMX endpoint → kết nối / authentication / quyền → MBean/attribute
                                                  |
                             supported → enabled → sample
```

| Phản hồi | Khả năng xảy ra | Phân loại hợp lý |
| --- | --- | --- |
| Timeout, TLS/credential failure | Không kết nối hoặc không xác thực được | `READ_ERROR` |
| `InstanceNotFoundException` | Sai ObjectName, bean không được đăng ký hoặc đã biến mất | `NOT_PRESENT` / lifecycle error |
| `AttributeNotFoundException` | Attribute không có trong interface/runtime được hỏi | `NOT_PRESENT`; kiểm tra MBeanInfo |
| `SecurityException` / authorization denied | Không có quyền đọc | `READ_ERROR`, không phải `UNSUPPORTED` |
| `UnsupportedOperationException` | Operation không được JVM hỗ trợ | `UNSUPPORTED` theo API contract |
| Getter trả sentinel được Javadoc mô tả | Mẫu thiếu/undefined hoặc đối tượng không còn | `UNAVAILABLE` / `UNDEFINED` |
| Getter trả `0` trong miền hợp lệ | Số đo bằng 0 | `AVAILABLE(0)` |

Capability/enable/value checks thường là các lệnh đọc **riêng**, không phải snapshot nguyên tử. Thread có thể chết hoặc pool bị thay đổi giữa các lần đọc; code cần có fallback và bắt lỗi đọc phù hợp.

Quyền bật monitoring thường cao hơn quyền đọc. Không đổi runtime flags, threshold hoặc trạng thái đo trong một exporter chỉ vì trước đó đọc được `-1`.

## 8. Java 17+: chương trình đầy đủ minh họa năm trạng thái

Chương trình này vừa kiểm tra **năm tình huống giả lập có kết quả cố định**, vừa đọc **MXBeans thật của JVM đang chạy** mà không thay đổi trạng thái monitoring.

Tạo file **`MxBeanCapabilityDemo.java`**:

```java
import java.lang.management.*;

public class MxBeanCapabilityDemo {
    static String classify(boolean supported, boolean enabled, Long value) {
        if (!supported) return "UNSUPPORTED";
        if (!enabled) return "DISABLED";
        if (value == null || value < 0) return "UNAVAILABLE";
        return "AVAILABLE(" + value + ")";
    }

    public static void main(String[] args) {
        System.out.println("fixture.unsupported=" + classify(false, false, -1L));
        System.out.println("fixture.disabled=" + classify(true, false, 0L));
        System.out.println("fixture.unavailable=" + classify(true, true, -1L));
        System.out.println("fixture.zero=" + classify(true, true, 0L));
        System.out.println("fixture.positive=" + classify(true, true, 42L));

        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        boolean cpuSupported = threads.isCurrentThreadCpuTimeSupported();
        boolean cpuEnabled = cpuSupported && threads.isThreadCpuTimeEnabled();
        Long cpuNs = cpuEnabled ? threads.getCurrentThreadCpuTime() : null;
        System.out.println("live.threadCpuNs=" +
            classify(cpuSupported, cpuEnabled, cpuNs));

        boolean contentionSupported = threads.isThreadContentionMonitoringSupported();
        boolean contentionEnabled = contentionSupported
            && threads.isThreadContentionMonitoringEnabled();
        System.out.println("live.contention=" +
            (contentionSupported ? (contentionEnabled ? "ENABLED" : "DISABLED")
                                 : "UNSUPPORTED"));

        CompilationMXBean compilation = ManagementFactory.getCompilationMXBean();
        boolean jitSupported = compilation != null
            && compilation.isCompilationTimeMonitoringSupported();
        Long jitMs = jitSupported ? compilation.getTotalCompilationTime() : null;
        System.out.println("live.jitTimeMs=" +
            classify(jitSupported, true, jitMs));

        MemoryUsage heap = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
        System.out.println("live.heapMax=" +
            (heap.getMax() < 0 ? "UNDEFINED" : heap.getMax() + " bytes"));

        for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
            boolean supported = pool.isUsageThresholdSupported();
            String state = !supported ? "UNSUPPORTED"
                : pool.getUsageThreshold() == 0 ? "DISABLED" : "ENABLED";
            System.out.println("live.pool[" + pool.getName() + "].threshold=" + state);
        }

        for (GarbageCollectorMXBean gc : ManagementFactory.getGarbageCollectorMXBeans()) {
            long count = gc.getCollectionCount();
            System.out.println("live.gc[" + gc.getName() + "].count=" +
                (count < 0 ? "UNAVAILABLE" : Long.toString(count)));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 MxBeanCapabilityDemo.java
java MxBeanCapabilityDemo
```

**Năm dòng stdout đầu chính xác và cố định:**

```text
fixture.unsupported=UNSUPPORTED
fixture.disabled=DISABLED
fixture.unavailable=UNAVAILABLE
fixture.zero=AVAILABLE(0)
fixture.positive=AVAILABLE(42)
```

Các dòng `live.*` được in **sau đó** và thay đổi theo JVM vendor, GC, trạng thái monitor và thời điểm lấy mẫu. Không hard-code các số CPU time, thời gian JIT, heap max, số pool hoặc tên collectors.

Giải thích các nhóm output:

- `live.threadCpuNs=AVAILABLE(n)`: CPU time current thread có hỗ trợ, đang bật, trả số nanosecond không âm tại thời điểm đọc.
- `live.threadCpuNs=DISABLED`: có capability nhưng monitoring đang tắt. Không có nghĩa CPU time thực sự bằng 0.
- `live.contention=DISABLED`: contention monitoring bị tắt; các `blockedTime`/`waitedTime` có thể là -1.
- `live.jitTimeMs=UNSUPPORTED`: compilation bean không có hoặc việc đo compilation time không hỗ trợ. Trong ứng dụng thật nên lưu riêng **NOT_PRESENT** nếu bean null.
- `live.heapMax=UNDEFINED`: maximum không được định nghĩa, không được tính phần trăm dùng bộ nhớ dựa trên max.
- `live.pool[...].threshold=UNSUPPORTED`: đúng pool đó không hỗ trợ usage threshold, dù pool khác có thể hỗ trợ.
- `live.gc[...].count=0`: giá trị 0 thực của bộ đếm, không phải missing.

Mã đã được biên dịch với `javac --release 17` và chạy thành công trên một JVM OpenJDK. Năm dòng fixture khớp đúng output ở trên. Mẫu này chỉ đọc và quan sát; không gọi `setThreadCpuTimeEnabled`, `setThreadContentionMonitoringEnabled` hoặc `setUsageThreshold`.

**Giới hạn helper `classify`:** nó dùng cho số nguyên không âm có sentinel âm. Những trường hợp khác như threshold = 0, `MemoryUsage.getMax() == -1` và JMX error cần xử lý bằng logic riêng theo hợp đồng API, không đưa tất cả vào một hàm tổng quát.

## 9. Thiết kế metrics: giữ trạng thái, đơn vị và instance

Một bản ghi quan sát nên giữ: tên chỉ số, nguồn API, timestamp, JVM instance (host/container/PID/start time), value khi có, unit và state.

```text
metric: jvm.thread.cpu.time
timestamp_utc: 2026-10-29T09:15:00Z
instance: orders-api/pod-abc/app
source: ThreadMXBean.getCurrentThreadCpuTime
state: AVAILABLE
value: 12345678
unit: ns
```

Đây là **bản ghi minh họa**, không phải output của demo. Nếu sample chưa có, hãy lưu state như `UNAVAILABLE` hoặc `READ_ERROR` và **không xuất value=0**. Trong Prometheus/exporter, có thể không xuất numeric sample khi thiếu nhưng xuất trạng thái health/availability riêng với bộ label có cardinality thấp.

### 9.1. Quy tắc dữ liệu số

- Giá trị `0` hợp lệ phải được giữ nguyên; đừng dùng điều kiện kiểu “falsy” để loại nó.
- `-1` hoặc giá trị âm sentinel phải xử lý **trước khi** tính trung bình, phần trăm, tốc độ hoặc percentile.
- Chỉ tính `used/max` khi `max > 0` và hai mẫu cùng ngữ nghĩa/đơn vị.
- CPU time nanosecond đổi sang second bằng `ns / 1_000_000_000.0` **sau khi** mẫu hợp lệ; CPU time khác wall-clock duration.
- Bộ đếm GC tích lũy chỉ tính rate bằng chênh lệch giữa hai mẫu hợp lệ cùng instance và cửa sổ thời gian. Sau restart có thể reset.
- Không nhét raw exception stack, user ID, thread ID hoặc tên request tùy ý vào label metrics; tránh số lượng time series tăng quá mức.
- Tách **scrape/read error** khỏi “runtime hợp lệ nhưng không hỗ trợ tính năng”; dashboard màu xanh cho giá trị 0 khi thực tế exporter bị lỗi sẽ gây sai lệch.

### 9.2. Bật measurement là thay đổi vận hành

Các setter `setThreadCpuTimeEnabled`, `setThreadContentionMonitoringEnabled`, `setUsageThreshold` hoặc `setCollectionUsageThreshold` có thể cần quyền và tăng overhead. Trước khi bật cần nêu rõ câu hỏi điều tra, thời điểm bắt đầu, tác động, cách kiểm chứng đã bật và phương án hoàn nguyên. Không mặc định các counter tích lũy chứa dữ liệu từ trước khi tính năng được bật.

## 10. Tình huống chẩn đoán thường gặp

### A. CPU time mọi thread đều được dashboard báo 0

Kiểm tra exporter có đang chuyển `getThreadCpuTime(id) == -1` thành zero không. Xác nhận support cho **any-thread** (khác current-thread), kiểm tra enabled, thread lifetime. Nếu số đo không có, hiển thị `DISABLED` hoặc `UNAVAILABLE`; đối chiếu metrics CPU process/JFR nếu cần điều tra tiếp.

### B. Memory threshold không bao giờ phát cảnh báo

Dò đúng pool và đúng loại threshold: `isUsageThresholdSupported` hay `isCollectionUsageThresholdSupported`. Nếu support false → UNSUPPORTED; nếu threshold = 0 → DISABLED. Nếu threshold > 0 → kiểm tra sự kiện crossing, listener, cửa sổ và quyền. **Count = 0 không chứng minh monitoring tắt.**

### C. Heap usage percent bỗng âm

Nếu `getMax() == -1`, phép chia `used / max` sinh tỷ lệ vô nghĩa. Báo `UNDEFINED` cho denominator; vẫn có thể báo `used` hoặc `committed` theo byte. Muốn báo phần trăm, chọn denominator đúng và được định nghĩa rõ, không tùy tiện dùng committed như max.

### D. GC counter luôn bằng 0 sau deploy

`0` có thể hoàn toàn hợp lệ nếu chưa có collection theo collector đó. Kiểm tra collector name và JVM uptime. Nếu count == -1 thì undefined, không phải zero. So rate qua restart cần nhận diện instance mới.

### E. Contention time -1 nhưng latency tăng

`getBlockedTime`/`getWaitedTime` bằng -1 khi contention monitoring tắt. Kiểm tra `isThreadContentionMonitoringSupported()` và `isThreadContentionMonitoringEnabled()`. Nếu cần bằng chứng ngay, có thể dùng thread dump hoặc JFR phù hợp, rồi quyết định bật monitoring theo quy trình vận hành.

### F. Sau nâng JDK, một metric biến mất

Kiểm tra runtime version, collector/pool names, MBean registration, extension `com.sun.management`, enabled state, JMX authorization và cách mapping attributes. Chỉ sau khi phân biệt NOT_PRESENT, UNSUPPORTED và READ_ERROR mới quyết định fallback hoặc cập nhật exporter.

## 11. Kiểm thử cách xử lý trạng thái

Tách logic phân loại khỏi phần gọi MXBean thật. Một unit test nên dùng fixture sau:

| supported | enabled | raw | Mong đợi |
| --- | --- | --- | --- |
| false | false | -1 | `UNSUPPORTED` |
| true | false | 0 | `DISABLED` |
| true | true | -1 | `UNAVAILABLE` |
| true | true | null | `UNAVAILABLE` |
| true | true | 0 | `AVAILABLE(0)` |
| true | true | 42 | `AVAILABLE(42)` |

Năm fixture với số Long được chạy trong demo; trường hợp `null` được xử lý bởi `value == null`. Với các API khác phải viết test riêng: threshold bằng 0 là DISABLED, heap max -1 là UNDEFINED, CPU load âm là UNAVAILABLE, remote read exception là READ_ERROR.

Integration tests nên kiểm tra hành vi khác biệt giữa JVM vendor/OS/GC collector, quyền đọc, pool invalid và thread chết. Không nên bắt buộc một giá trị `live.*` cố định hoặc giả định luôn có cùng tên memory pool. Cũng cần kiểm tra probe không tự gọi setter.

## 12. Sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Getter tồn tại thì đo được.” | Có capability optional. | Hỏi `is...Supported` trước khi gọi. |
| “Supported đồng nghĩa enabled.” | Measurement/threshold có trạng thái bật riêng. | Hỏi enabled hoặc threshold value. |
| “-1 có nghĩa không có hoạt động.” | -1 là sentinel unavailable/undefined. | Giữ state, không đổi thành 0. |
| “0 là metric missing.” | Có thể là số đo hợp lệ. | Giữ `AVAILABLE(0)`. |
| “Threshold count=0 là disabled.” | Có thể bật nhưng chưa crossing. | Đọc cấu hình threshold. |
| “Compilation bean không thể null.” | JVM có thể không cung cấp. | Kiểm tra null trước support. |
| “ThreadInfo luôn có object.” | Thread có thể đã kết thúc. | Kiểm tra null cho từng ID. |
| “MemoryUsage luôn có max dương.” | Max có thể undefined (-1). | Kiểm tra trước phép chia. |
| “JMX timeout = JVM không hỗ trợ.” | Là lỗi transport/quyền. | Gắn `READ_ERROR` riêng. |
| “CPU time là wall-clock latency.” | Hai khái niệm đo khác nhau. | Gắn unit và semantics. |
| “Mọi collector/VM có cùng MXBean extension.” | Tùy vendor/JDK/GC. | Discovery và fallback. |
| “Check và read là nguyên tử.” | Trạng thái đổi giữa hai lời gọi. | Chấp nhận race, xử lý ngoại lệ. |
| “Read-only probe có thể tự bật counter.” | Setter thay đổi trạng thái/overhead. | Chỉ bật khi được phép. |

## 13. Checklist đưa vào code giám sát

- [ ] Xác nhận đúng JVM instance, phiên runtime và nguồn MXBean.
- [ ] Kiểm tra bean/attribute có tồn tại và đọc được; tách lỗi transport/quyền.
- [ ] Kiểm tra `supported` khi API có capability check.
- [ ] Kiểm tra `enabled` hoặc threshold > 0 **nếu** API có khái niệm bật.
- [ ] Chỉ đọc getter phù hợp; xử lý `null`, `-1` và số âm sentinel theo Javadoc cụ thể.
- [ ] Giữ `0` là giá trị hợp lệ khi hợp đồng cho phép.
- [ ] Không tính phần trăm/rate nếu thiếu một mẫu hoặc denominator.
- [ ] Chú ý đơn vị ns/ms/byte và trạng thái counter tích lũy qua restart.
- [ ] Không tự bật measurement hoặc sửa threshold trong probe read-only.
- [ ] Thiết kế trạng thái availability có cardinality thấp cho metrics/dashboard.
- [ ] Kiểm thử fixture đủ trạng thái và test trên các JVM thật được hỗ trợ.
- [ ] Ghi lại timestamp và cách giải thích bất kỳ mẫu N/A nào.

## 14. Tài liệu chính thức Java SE 17

- [ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): CPU time, contention capability/enabled, thread info.
- [ThreadInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): blocked/waited time và sentinel -1.
- [MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): usage threshold và collection threshold, isValid, null usage.
- [MemoryUsage](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html): init/used/committed/max, undefined sentinel.
- [GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): GC count/time undefined.
- [CompilationMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/CompilationMXBean.html): optional JIT compilation time.
- [ManagementFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html): truy cập platform MXBeans.
- [com.sun.management.OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): process CPU load và giá trị âm khi không khả dụng.

**Điểm cần nhớ:** Thứ tự đọc số liệu MXBeans là **đúng bean và quyền → supported → enabled (khi có) → value hợp lệ → diễn giải theo đơn vị và thời gian**. Không có giá trị không đồng nghĩa bằng 0; một số 0 hợp lệ cũng không đồng nghĩa bị tắt. Trạng thái rõ ràng giúp dashboard phản ánh những gì JVM thực sự biết.