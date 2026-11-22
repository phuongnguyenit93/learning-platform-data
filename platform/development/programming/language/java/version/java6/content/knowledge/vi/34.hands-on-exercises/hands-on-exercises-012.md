# Thực hành Java: Quan sát chỉ số bằng MXBean và phân tích khóa bằng ThreadMXBean

## 1. Bài toán: từ chỉ số JVM đến nguyên nhân tranh chấp khóa

Giả sử một dịch vụ Java bắt đầu chậm. Dashboard cho thấy số luồng tăng, heap usage nhích lên, thời gian xử lý request kéo dài. Chỉ nhìn một chỉ số “nhiều threads” không đủ kết luận CPU quá tải hoặc deadlock. Ta cần kết hợp hai lớp quan sát:

1. **MXBeans** cung cấp các chỉ số và trạng thái có cấu trúc của JVM hoặc ứng dụng: heap, class loading, runtime uptime, garbage collection, số platform threads và counters nghiệp vụ.
2. **ThreadMXBean** cho phép lấy snapshot của các **platform threads**, xem luồng nào `BLOCKED`, nó đang chờ object nào, ai sở hữu monitor, thread sở hữu đang làm gì ở stack, đồng thời phân biệt **object monitor** và **ownable synchronizer** như `ReentrantLock`.

Mục tiêu cuối là nối những câu hỏi:

~~~text
                     Service latency tăng
                              |
         +--------------------+--------------------+
         |                                         |
     MXBean metrics                           ThreadMXBean
         |                                         |
    Heap / classes / threads                ThreadInfo snapshots
    GC / uptime / CPU support                      |
    Application counters                       State, stack
         |                                    owner / waiting lock
         |                                         |
         +--------------------+--------------------+
                              |
                 Giả thuyết có căn cứ
                 - contention monitor
                 - ownable synchronizer
                 - lock owner đang chờ I/O
                 - queue/backpressure/DB latency
                              |
                    Kiểm chứng bằng
                metrics + JFR + application traces
~~~

Bài thực hành gồm **ba chương trình hoàn chỉnh**:

- **`JvmMxbeanMetricsDemo.java` (Java 17+):** đọc các platform MXBeans, đọc thuộc tính qua JMX `MBeanServer`/`CompositeData` và đăng ký/quan sát một MXBean ứng dụng tùy biến.
- **`ThreadLockInspectionDemo.java` (Java 21+):** tạo tranh chấp có thể giải phóng, chụp `ThreadInfo[]`, tìm `MonitorInfo`, `LockInfo`, vị trí monitor acquisition trên stack và thread owner, rồi dọn toàn bộ threads.
- **`VirtualSchedulerMxbeanDemo.java` (Java 24+):** theo dõi scheduler bằng `VirtualThreadSchedulerMXBean` hiện hành, đồng thời chứng minh virtual threads không nằm trong phạm vi `ThreadMXBean`.

Cả ba đã được thử nghiệm bằng **OpenJDK 24.0.2** tương ứng với `javac --release 17`, `--release 21` và `--release 24`. Bài chỉ sử dụng APIs **còn áp dụng tới Java SE 25**; không hướng dẫn cơ chế quản lý JVM đã bị loại bỏ.

## 2. MXBean là gì? Quan sát khác điều khiển như thế nào?

**JMX (Java Management Extensions)** cung cấp `MBeanServer`, `ObjectName`, interface management và khả năng kết nối quan sát. **MXBean** là một kiểu management bean có **quy tắc ánh xạ dữ liệu sang Open Types** để một client JMX không phải biết chính xác implementation class bên server.

Ví dụ, `MemoryMXBean.getHeapMemoryUsage()` trả một `MemoryUsage` khi gọi trực tiếp từ Java; nhưng cùng thuộc tính `HeapMemoryUsage` đọc qua `MBeanServer.getAttribute(...)` được biểu diễn dưới dạng `CompositeData`. Một client dùng typed proxy có thể nhận lại object Java theo mapping của MXBean.

### Phân biệt các vai trò

| Thành phần | Vai trò |
| --- | --- |
| `ManagementFactory` | Entry point lấy platform MXBeans trong JVM |
| `MemoryMXBean` | Heap/non-heap memory, GC notification support |
| `ThreadMXBean` | Metrics, snapshot và deadlock diagnostics của **platform threads** |
| `ClassLoadingMXBean` | Loaded/unloaded class counts |
| `RuntimeMXBean` | JVM name/vendor/version, uptime và start time |
| `OperatingSystemMXBean` | Available processors, OS name/load average khi hỗ trợ |
| `GarbageCollectorMXBean` | Số lần/thời gian GC do provider báo |
| `MemoryPoolMXBean` | Usage/threshold support theo từng memory pool |
| `MBeanServer` | Registry và đường truy cập thuộc tính/operation qua `ObjectName` |
| `JMX.newMXBeanProxy` | Typed proxy truy cập MXBean qua MBeanServerConnection |
| `ApplicationMetricsMXBean` | Interface tự định nghĩa cho các counters nghiệp vụ trong demo |
| `VirtualThreadSchedulerMXBean` | JDK 24+ extension cho **virtual-thread scheduler**, không phải mọi virtual thread stack |

**Không nhầm MXBean với một hệ thống monitoring hoàn chỉnh.** Một MXBean cung cấp chỉ số tại thời điểm đọc và có thể cho phép các operations quản trị, nhưng nó không tự ghi dữ liệu time-series, không tự lưu traces và không cung cấp alerting/SLO. Để quan sát liên tục cần exporter/collector, polling được giới hạn, storage và ngữ cảnh nghiệp vụ.

### Các module

- `java.lang.management.*` nằm trong module `java.management`;
- `javax.management.*` cũng nằm trong module `java.management`;
- `jdk.management.VirtualThreadSchedulerMXBean` là extension trong module `jdk.management`, **có từ Java 24**;
- `java.util.concurrent.locks.ReentrantLock` và `Thread` thuộc `java.base`.

Các ví dụ chạy với JDK thông thường qua classpath, không cần dependency ngoài. Nếu ứng dụng triển khai custom runtime bằng `jlink`, phải bảo đảm runtime chứa những modules cần thiết. Không giả định mọi JVM khác nhau đều hỗ trợ tất cả khả năng nâng cao.

## 3. Các platform MXBeans nên đo và ý nghĩa từng giá trị

### 3.1. Heap memory

~~~java
MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
MemoryUsage heap = memory.getHeapMemoryUsage();
long used = heap.getUsed();
long committed = heap.getCommitted();
long max = heap.getMax();
~~~

Đây là **snippet trong method**, cần import `MemoryMXBean`, `MemoryUsage`, `ManagementFactory`.

- `used`: bộ nhớ đang sử dụng, đo theo snapshot, không đồng nghĩa lượng memory leak.
- `committed`: memory đã được JVM cam kết có thể sử dụng; thường ≥ `used`.
- `max`: giới hạn tối đa nếu biết; **có thể bằng -1** nếu không xác định.
- `getNonHeapMemoryUsage()`: vùng non-heap theo JVM provider; không thay thế RSS/container memory.

Không tính `used/max` khi `max==-1`, và không coi `used` cao tại một thời điểm là lỗi. GC thường khiến usage theo thời gian dao động. Khi phân tích memory leak, cần trend sau GC, allocations, heap dump/JFR và các giới hạn container.

### 3.2. Runtime và class loading

~~~java
RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
ClassLoadingMXBean classes = ManagementFactory.getClassLoadingMXBean();
long uptimeMillis = runtime.getUptime();
int loaded = classes.getLoadedClassCount();
~~~

Đây là snippet trong method, cần imports. `RuntimeMXBean.getUptime` đo thời gian JVM đã chạy, không phải thời gian user request; `getLoadedClassCount` là số class hiện đang loaded, không phải số request hoặc số class load callbacks.

### 3.3. Garbage collection

~~~java
for (GarbageCollectorMXBean gc :
        ManagementFactory.getGarbageCollectorMXBeans()) {
    long collections = gc.getCollectionCount();
    long totalMillis = gc.getCollectionTime();
    // Giá trị -1 nghĩa là VM không định nghĩa được metric này.
}
~~~

Đây là snippet trong method, cần import `GarbageCollectorMXBean`. Danh sách collectors, tên và counters **phụ thuộc runtime/GC configuration**. `getCollectionCount`/`getCollectionTime` có thể trả -1 nếu số liệu không có; không hardcode một collector bắt buộc tồn tại.

### 3.4. ThreadMXBean: số luồng và CPU

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
int platformCount = bean.getThreadCount();
int peakPlatformCount = bean.getPeakThreadCount();
boolean supportsCpu = bean.isCurrentThreadCpuTimeSupported();
if (supportsCpu && bean.isThreadCpuTimeEnabled()) {
    long currentCpuNanos = bean.getCurrentThreadCpuTime();
}
~~~

Đây là snippet trong method. **ThreadMXBean theo contract Java SE 25 chỉ theo dõi platform threads.** Số lượng platform threads không đại diện cho tổng lượng virtual threads đang tồn tại. CPU time có **nanosecond precision, không có bảo đảm nanosecond accuracy**; provider có thể không hỗ trợ hoặc mặc định tắt. Tham số/điều kiện không phù hợp có thể trả **-1**; code phải kiểm capability và enabled state.

`ThreadMXBean` còn có khả năng theo dõi contention, nhưng **đừng tự bật trên production chỉ để chạy một biểu đồ** vì có overhead và ảnh hưởng chính sách toàn JVM.

### 3.5. OperatingSystemMXBean và provider-specific extensions

`java.lang.management.OperatingSystemMXBean.getAvailableProcessors()` là API chung. Một số metric CPU/memory chuyên sâu nằm trong JDK-specific `com.sun.management.OperatingSystemMXBean` và có thể khác theo VM/provider. Đừng cast không kiểm tra type rồi coi đó là Java API portable, và không dùng các method provider-specific đã deprecated để làm nền tảng bài học mới.

## 4. Đọc MXBean qua MBeanServer và Open Types

Có ba cách phổ biến:

1. **Direct**: `ManagementFactory.getMemoryMXBean()`.
2. **JMX attribute**: `MBeanServerConnection.getAttribute(ObjectName,attribute)`.
3. **Typed proxy**: `JMX.newMXBeanProxy(...)`, hoặc `ManagementFactory.newPlatformMXBeanProxy(...)` cho platform beans.

Ví dụ thuộc tính memory:

~~~java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName memoryName =
        new ObjectName(ManagementFactory.MEMORY_MXBEAN_NAME);
CompositeData cd = (CompositeData)
        server.getAttribute(memoryName, "HeapMemoryUsage");
long used = (Long) cd.get("used");
~~~

Đây là snippet trong method có imports `MBeanServer`, `ObjectName`, `CompositeData`. `ManagementFactory.MEMORY_MXBEAN_NAME` tương ứng `java.lang:type=Memory`. Các fields của Open Type như `used`, `committed`, `init` và `max` có kiểu và quy tắc tương ứng `MemoryUsage`.

**Không gửi toàn bộ dữ liệu JMX qua endpoint không xác thực.** MBeanServer chứa rất nhiều thông tin nội bộ JVM, và một số beans có operations có thể thay đổi trạng thái. Bài chỉ sử dụng MBeanServer **trong cùng JVM**; nó **không** bật một cổng JMX remote.

## 5. Tự tạo MXBean nghiệp vụ để bổ sung chỉ số JVM

Một service thực tế thường cần metrics như:
- Số jobs đã **được nhận**;
- Số jobs **bị từ chối** do overload;
- Số jobs **đã xử lý xong**;
- Queue capacity có cấu hình.

Có thể định nghĩa public management interface tên kết thúc bằng `MXBean` (hoặc dùng annotation `@MXBean`). MBeanServer sẽ ánh xạ các getters sang JMX attributes. Một implementation có thể sử dụng `AtomicLong` để đọc/ghi counters an toàn giữa threads.

**Đặc biệt:** các số `Accepted` và `Processed` có semantics khác nhau. Accepted là queue admission; Processed phải là outcome cuối cùng mà application định nghĩa. Một counter tự tăng không thay thế transactional acknowledgment.

Ví dụ 1 dưới đây đăng ký MXBean tùy chỉnh trên platform MBeanServer, đọc bằng **typed proxy** và **attribute lookup**, rồi **unregister trong finally** để không để lại resource quản trị thừa.

## 6. Chương trình 1 (Java 17+): chỉ số JVM + custom MXBean

**File `JvmMxbeanMetricsDemo.java` — toàn bộ source code:**

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.OperatingSystemMXBean;
import java.lang.management.RuntimeMXBean;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.JMX;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

public final class JvmMxbeanMetricsDemo {
    public interface ApplicationMetricsMXBean {
        int getQueueCapacity();
        long getAccepted();
        long getRejected();
        long getProcessed();
    }

    public static final class ApplicationMetrics implements ApplicationMetricsMXBean {
        private final int capacity;
        private final AtomicLong accepted = new AtomicLong();
        private final AtomicLong rejected = new AtomicLong();
        private final AtomicLong processed = new AtomicLong();

        public ApplicationMetrics(int capacity) {
            this.capacity = capacity;
        }

        @Override public int getQueueCapacity() { return capacity; }
        @Override public long getAccepted() { return accepted.get(); }
        @Override public long getRejected() { return rejected.get(); }
        @Override public long getProcessed() { return processed.get(); }

        public void accepted() { accepted.incrementAndGet(); }
        public void rejected() { rejected.incrementAndGet(); }
        public void processed() { processed.incrementAndGet(); }
    }

    public static void main(String[] args) throws Exception {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        ClassLoadingMXBean classes = ManagementFactory.getClassLoadingMXBean();
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        OperatingSystemMXBean os = ManagementFactory.getOperatingSystemMXBean();

        MemoryUsage heap = memory.getHeapMemoryUsage();
        System.out.println("heap usage available: "
                + (heap != null && heap.getUsed() >= 0));
        System.out.println("committed heap >= used: "
                + (heap != null && heap.getCommitted() >= heap.getUsed()));
        System.out.println("runtime uptime nonnegative: " + (runtime.getUptime() >= 0));
        System.out.println("loaded class count positive: "
                + (classes.getLoadedClassCount() > 0));
        System.out.println("platform thread count positive: "
                + (threads.getThreadCount() > 0));
        System.out.println("processors positive: "
                + (os.getAvailableProcessors() > 0));

        boolean cpuCapable = threads.isCurrentThreadCpuTimeSupported();
        boolean cpuEnabled = cpuCapable && threads.isThreadCpuTimeEnabled();
        long cpuNs = cpuEnabled ? threads.getCurrentThreadCpuTime() : -1;
        System.out.println("CPU feature gated before read: "
                + (!cpuEnabled || cpuNs >= 0));
        System.out.println("GC bean list available: "
                + (ManagementFactory.getGarbageCollectorMXBeans() != null));

        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName memoryName = new ObjectName(ManagementFactory.MEMORY_MXBEAN_NAME);
        System.out.println("platform memory MXBean registered: "
                + server.isRegistered(memoryName));
        CompositeData heapOpenData =
                (CompositeData) server.getAttribute(memoryName, "HeapMemoryUsage");
        System.out.println("JMX heap CompositeData used numeric: "
                + (heapOpenData.get("used") instanceof Long));

        ObjectName appName =
                new ObjectName("example.observability:type=ApplicationMetrics");
        ApplicationMetrics app = new ApplicationMetrics(2);
        server.registerMBean(app, appName);
        try {
            app.accepted();
            app.accepted();
            app.rejected();
            app.processed();
            app.processed();
            ApplicationMetricsMXBean proxy =
                    JMX.newMXBeanProxy(server, appName, ApplicationMetricsMXBean.class);
            System.out.println("application MXBean recognized: "
                    + JMX.isMXBeanInterface(ApplicationMetricsMXBean.class));
            System.out.println("application MXBean registered: "
                    + server.isRegistered(appName));
            System.out.println("proxy sees accepted=2: " + (proxy.getAccepted() == 2));
            System.out.println("proxy sees rejected=1: " + (proxy.getRejected() == 1));
            System.out.println("proxy sees processed=2: " + (proxy.getProcessed() == 2));
            System.out.println("JMX attribute capacity=2: "
                    + ((Integer) server.getAttribute(appName, "QueueCapacity") == 2));
        } finally {
            server.unregisterMBean(appName);
        }
        System.out.println("application MXBean unregistered: "
                + !server.isRegistered(appName));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file:

~~~bash
javac --release 17 JvmMxbeanMetricsDemo.java
java JvmMxbeanMetricsDemo
~~~

**Stdout chính xác** đã thử trên **OpenJDK 24.0.2** (biên dịch `--release 17`):

~~~text
heap usage available: true
committed heap >= used: true
runtime uptime nonnegative: true
loaded class count positive: true
platform thread count positive: true
processors positive: true
CPU feature gated before read: true
GC bean list available: true
platform memory MXBean registered: true
JMX heap CompositeData used numeric: true
application MXBean recognized: true
application MXBean registered: true
proxy sees accepted=2: true
proxy sees rejected=1: true
proxy sees processed=2: true
JMX attribute capacity=2: true
application MXBean unregistered: true
~~~

### Diễn giải kết quả mà không hardcode số liệu VM

- `heap usage available` và `committed heap >= used` xác nhận snapshot có giá trị hợp lệ mà **không hardcode** lượng heap vì mỗi máy/JDK khác nhau.
- `runtime uptime nonnegative`: thời gian JVM chạy là một số không âm, nhưng không có nghĩa ứng dụng khỏe mạnh.
- `loaded class count positive`: JVM đã load class, không cho biết có memory leak hay không.
- `platform thread count positive`: JVM đang có platform threads; **không bao gồm virtual-thread totals**.
- `processors positive`: CPU có sẵn >0, nhưng không suy ra tỷ lệ CPU utilization hay throughput.
- `CPU feature gated before read`: chương trình chỉ đọc CPU time nếu runtime hỗ trợ **và** chức năng đã bật; không tự ý thay policy JVM.
- `GC bean list available`: chỉ kiểm danh sách được cung cấp, **không giả** JVM buộc có một collector/tên collector cụ thể.
- `platform memory MXBean registered` và `JMX heap CompositeData used numeric` chứng minh access qua JMX khác direct Java call nhưng giữ dữ liệu theo MXBean mapping.
- `application MXBean recognized`: interface nested public có suffix MXBean đúng convention.
- Các dòng `proxy sees...` xác nhận typed JMX proxy đọc được counters mà application cập nhật bằng `AtomicLong`.
- `JMX attribute capacity=2` chứng minh accessor `getQueueCapacity()` được phơi qua JMX dưới tên thuộc tính `QueueCapacity`.
- `unregistered` chứng minh lifecycle kết thúc đúng, không giữ bean demo trong platform registry.

**Giới hạn:** đây là console demo synchronous, không mở JMX remote, không có monitoring backend. Trong production, không nên tạo/unregister MXBean mỗi request; thường đăng ký một bean ở application startup rồi hủy ở shutdown, exporters được quản lý bằng lifecycle rõ ràng.

## 7. ThreadMXBean: từ số lượng threads tới snapshot có khóa

Đọc tổng số platform threads:

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
int count = bean.getThreadCount();
int peak = bean.getPeakThreadCount();
long[] ids = bean.getAllThreadIds();
~~~

Đây là snippet trong method với imports đúng. `getPeakThreadCount` có thể được reset qua operation quản trị; tuyệt đối không coi đó là lịch sử đầy đủ qua JVM restarts. `getAllThreadIds` là snapshot platform-thread IDs, không chứa virtual thread IDs.

### Capability phải được kiểm tra trước khi yêu cầu ownership

~~~java
boolean monitors = bean.isObjectMonitorUsageSupported();
boolean ownables = bean.isSynchronizerUsageSupported();
if (monitors && ownables) {
    ThreadInfo[] sample = bean.getThreadInfo(
            new long[]{firstThreadId, secondThreadId}, true, true);
}
~~~

Đây là snippet trong method có hai IDs. Hai booleans trong `getThreadInfo(ids,true,true)` lần lượt là **lấy locked monitors** và **lấy locked ownable synchronizers**, **không phải** “bật trace và đếm số threads”. Nếu VM không hỗ trợ mà vẫn yêu cầu `true`, có thể nhận `UnsupportedOperationException`; chọn `false` cho phần không được hỗ trợ nếu muốn thu partial snapshot.

**Không dùng `getThreadInfo(threadId)` rồi kết luận thread không giữ khóa** chỉ vì `getLockedMonitors()`/`getLockedSynchronizers()` rỗng; overload đơn giản không yêu cầu lấy ownership arrays.

## 8. Đọc ThreadInfo: trạng thái, blocked object và owner

`ThreadInfo` là **snapshot quan sát**, không phải lock controller. Các trường quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `getThreadId()/getThreadName()` | ID/tên platform thread trong snapshot |
| `getThreadState()` | `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, v.v. |
| `getStackTrace()` | Current call stack tại thời điểm snapshot |
| `getLockInfo()` | Đối tượng thread **đang đợi**, nếu có |
| `getLockOwnerId()/getLockOwnerName()` | Chủ sở hữu của lock đang đợi, nếu biết; ID có thể -1 |
| `getLockedMonitors()` | Những object monitors thread **đang sở hữu** |
| `getLockedSynchronizers()` | Những ownable synchronizers thread **đang sở hữu** |
| `getBlockedCount()/getWaitedCount()` | Số sự kiện blocking/waiting theo management metrics |
| `getBlockedTime()/getWaitedTime()` | Accumulated elapsed time khi contention monitoring enabled; có thể -1 |
| `isInNative()/isDaemon()` | Metadata điều tra bổ sung |

**Khác biệt quan trọng:** khóa mà thread *đang chờ* và các khóa mà nó *đang giữ* là hai tập khác nhau. Một thread có thể giữ monitor A và ReentrantLock B, trong khi lại đang chờ một latch C.

### RUNNABLE, BLOCKED và WAITING không đồng nghĩa CPU usage

- `BLOCKED`: thường thread đang đợi vào monitor của `synchronized`.
- `WAITING`: có thể đợi `Object.wait`, `LockSupport.park`, `CountDownLatch.await` hoặc `Condition.await`.
- `TIMED_WAITING`: đang chờ có timeout, như timed wait/sleep/park.
- `RUNNABLE`: có thể thực thi Java hoặc đang trong native code/I/O theo provider; **không tự chứng minh CPU 100%**.

ReentrantLock thường làm contenders park nên chúng có thể ở `WAITING/TIMED_WAITING` thay vì `BLOCKED`. Chỉ đếm `Thread.State.BLOCKED` sẽ bỏ sót nhiều tình huống chờ lock.

## 9. MonitorInfo: object monitor đang giữ và vị trí acquisition trên stack

Khi một platform thread vào `synchronized(lock)`, nó sở hữu object monitor cho tới khi rời block hoặc method (trừ khi gọi `Object.wait` **trên chính monitor ấy** theo contract).

`ThreadInfo.getLockedMonitors()` trả `MonitorInfo[]`. `MonitorInfo extends LockInfo` và có thêm:

- `getLockedStackDepth()`: **index vào `ThreadInfo.getStackTrace()`** ở nơi monitor được chiếm; không phải số monitors đang giữ.
- `getLockedStackFrame()`: `StackTraceElement` tương ứng; có thể null nếu không có thông tin.
- `getClassName()` và `getIdentityHashCode()` kế thừa `LockInfo`.

~~~java
for (MonitorInfo monitor : ownerInfo.getLockedMonitors()) {
    int depth = monitor.getLockedStackDepth();
    StackTraceElement[] stack = ownerInfo.getStackTrace();
    if (depth >= 0 && depth < stack.length) {
        StackTraceElement acquisition = monitor.getLockedStackFrame();
        if (acquisition != null && acquisition.equals(stack[depth])) {
            System.out.println("Acquired monitor at " + acquisition);
        }
    }
}
~~~

Đây là snippet trong method có `ThreadInfo ownerInfo`. Nếu depth âm hoặc frame null, **không** index mảng. Giới hạn stack depth, provider và thời điểm snapshot đều có thể ảnh hưởng availability.

### Identity hash không phải ID duy nhất tuyệt đối

`LockInfo.getIdentityHashCode()` liên hệ `System.identityHashCode(object)`. Nó hữu ích để correlation **trong cùng JVM và snapshot**, nhưng hash có thể va chạm giữa objects và không bền vững qua restart. Không dùng nó làm khóa business, mật mã hoặc định danh duy nhất xuyên hệ thống.

## 10. LockInfo và ReentrantLock: không có acquisition stack frame

`ThreadInfo.getLockedSynchronizers()` trả `LockInfo[]` cho **ownable synchronizers** đang sở hữu; ví dụ internal AQS synchronizer của `ReentrantLock` hoặc `ReentrantReadWriteLock.WriteLock`.

- `LockInfo` cho **className** và **identityHashCode**.
- Nó **không** có `getLockedStackDepth()` hoặc `getLockedStackFrame()` như `MonitorInfo`.
- Tên class có thể là implementation-specific internal type; không hardcode `ReentrantLock$NonfairSync`.
- `ReentrantReadWriteLock.ReadLock` là shared, không nằm trong danh mục ownable synchronizer độc quyền theo contract này.
- Semaphore permits, latch, StampedLock hoặc custom synchronization mechanisms không được biểu diễn đầy đủ bởi mảng ownable synchronizers.

~~~java
for (LockInfo lock : ownerInfo.getLockedSynchronizers()) {
    System.out.println(lock.getClassName()
            + "@" + Integer.toHexString(lock.getIdentityHashCode()));
}
~~~

Đây là snippet trong method với `ThreadInfo ownerInfo`. **Đừng ép kiểu một `LockInfo` của ReentrantLock thành `MonitorInfo`** để gọi phương thức stack frame. Nếu muốn biết nơi gọi `ReentrantLock.lock()` ở thời điểm trước đó, cần instrumentation/tracing/JFR và application context, bởi current stack có thể đã ở method khác từ lâu.

## 11. Thực hành số 2: chẩn đoán monitor và ownable synchronizer

Hai platform threads được chủ động điều phối:

~~~text
"diagnostic-owner"
  acquires ReentrantLock DATABASE_LOCK
  enters synchronized(GATE)
  calls CountDownLatch.await()           <-- WAITING nhưng vẫn GIỮ hai locks
       |
       +--> ThreadMXBean snapshot
               lockedMonitors(): GATE
               lockedSynchronizers(): ReentrantLock sync
               MonitorInfo.lockedStackFrame(): holdBoth(...)

"diagnostic-contender"
  tries synchronized(GATE)
       |
       +--> BLOCKED
            getLockInfo(): GATE
            getLockOwnerId(): diagnostic-owner threadId
            getLockedMonitors(): KHÔNG có GATE (chưa acquire)
~~~

Bài dùng `Thread.ofPlatform()` và `Thread.threadId()` nên yêu cầu **Java 21+**; đây là cách tạo/định danh platform thread hiện hành. Không dùng `Thread.getId()` đã deprecated trong code mới.

**Không cố tình tạo deadlock vĩnh viễn.** Owner đợi latch trong synchronized block; main luôn `release.countDown()` ở `finally`, sau đó join hai threads, nên chương trình có đường dọn dẹp đáng tin cậy.

### File ThreadLockInspectionDemo.java — toàn bộ code

~~~java
import java.lang.management.LockInfo;
import java.lang.management.ManagementFactory;
import java.lang.management.MonitorInfo;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public final class ThreadLockInspectionDemo {
    private static final Object GATE = new Object();
    private static final ReentrantLock DATABASE_LOCK = new ReentrantLock();

    private static void holdBoth(CountDownLatch holding,
            CountDownLatch release) {
        DATABASE_LOCK.lock();
        try {
            synchronized (GATE) {
                holding.countDown();
                release.await();
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } finally {
            DATABASE_LOCK.unlock();
        }
    }

    private static boolean awaitBlocked(Thread thread)
            throws InterruptedException {
        for (int attempt = 0; attempt < 300; attempt++) {
            if (thread.getState() == Thread.State.BLOCKED) {
                return true;
            }
            Thread.sleep(10);
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        boolean monitorCapability = bean.isObjectMonitorUsageSupported();
        boolean syncCapability = bean.isSynchronizerUsageSupported();
        System.out.println("monitor ownership supported: " + monitorCapability);
        System.out.println("ownable synchronizer supported: " + syncCapability);
        if (!monitorCapability || !syncCapability) {
            System.out.println("lock detail unavailable; skipped: true");
            return;
        }

        CountDownLatch holding = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch contenderReady = new CountDownLatch(1);
        Thread owner = Thread.ofPlatform().name("diagnostic-owner")
                .unstarted(() -> holdBoth(holding, release));
        Thread contender = Thread.ofPlatform().name("diagnostic-contender")
                .unstarted(() -> {
                    contenderReady.countDown();
                    synchronized (GATE) {
                        // Enter only after owner releases the monitor.
                    }
                });
        try {
            owner.start();
            if (!holding.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Owner has not acquired locks");
            }
            contender.start();
            if (!contenderReady.await(5, TimeUnit.SECONDS)
                    || !awaitBlocked(contender)) {
                throw new IllegalStateException("Contender did not block");
            }
            long ownerId = owner.threadId();
            long contenderId = contender.threadId();
            ThreadInfo[] details = bean.getThreadInfo(
                    new long[]{ownerId, contenderId}, true, true);
            ThreadInfo holdingInfo = details[0];
            ThreadInfo blockedInfo = details[1];
            if (holdingInfo == null || blockedInfo == null) {
                throw new IllegalStateException("Thread terminated before snapshot");
            }

            MonitorInfo monitor = Arrays.stream(holdingInfo.getLockedMonitors())
                    .filter(m -> m.getClassName().equals(GATE.getClass().getName())
                            && m.getIdentityHashCode()
                            == System.identityHashCode(GATE))
                    .findFirst().orElseThrow();
            int depth = monitor.getLockedStackDepth();
            StackTraceElement[] stack = holdingInfo.getStackTrace();
            boolean frameMatch = depth >= 0 && depth < stack.length
                    && monitor.getLockedStackFrame().equals(stack[depth]);
            boolean hasOwnableLock = Arrays.stream(
                    holdingInfo.getLockedSynchronizers())
                    .map(LockInfo::getClassName)
                    .anyMatch(name -> name.contains("ReentrantLock"));

            System.out.println("platform workers visible: "
                    + (Arrays.stream(bean.getAllThreadIds()).anyMatch(id -> id == ownerId)
                    && Arrays.stream(bean.getAllThreadIds()).anyMatch(id -> id == contenderId)));
            System.out.println("lock owner is WAITING yet holds monitor: "
                    + (holdingInfo.getThreadState() == Thread.State.WAITING));
            System.out.println("target monitor found: " + (monitor != null));
            System.out.println("monitor acquisition frame matches stack: " + frameMatch);
            System.out.println("monitor acquired inside holdBoth: "
                    + "holdBoth".equals(monitor.getLockedStackFrame().getMethodName()));
            System.out.println("owner holds ReentrantLock synchronizer: " + hasOwnableLock);
            System.out.println("contender is BLOCKED on monitor: "
                    + (blockedInfo.getThreadState() == Thread.State.BLOCKED));
            System.out.println("contender owner id matches: "
                    + (blockedInfo.getLockOwnerId() == ownerId));
            System.out.println("contender lock identity matches monitor: "
                    + (blockedInfo.getLockInfo() != null
                    && blockedInfo.getLockInfo().getIdentityHashCode()
                            == System.identityHashCode(GATE)));
            System.out.println("contender has not acquired monitor: "
                    + Arrays.stream(blockedInfo.getLockedMonitors())
                    .noneMatch(m -> m.getIdentityHashCode()
                            == System.identityHashCode(GATE)));

            ThreadInfo shallow = bean.getThreadInfo(ownerId);
            System.out.println("basic snapshot omits lock ownership arrays: "
                    + (shallow != null
                    && shallow.getLockedMonitors().length == 0
                    && shallow.getLockedSynchronizers().length == 0));
            long[] deadlocked = bean.findDeadlockedThreads();
            System.out.println("our two threads not deadlocked: "
                    + (deadlocked == null
                    || (Arrays.stream(deadlocked).noneMatch(id -> id == ownerId)
                    && Arrays.stream(deadlocked).noneMatch(id -> id == contenderId))));
        } finally {
            release.countDown();
            owner.join(5000);
            contender.join(5000);
            if (owner.isAlive() || contender.isAlive()) {
                owner.interrupt();
                contender.interrupt();
                throw new IllegalStateException("Lock workers did not terminate");
            }
        }
        System.out.println("both workers terminated: true");
    }
}
~~~

Lệnh:

~~~bash
javac --release 21 ThreadLockInspectionDemo.java
java ThreadLockInspectionDemo
~~~

**Stdout chính xác** trên **OpenJDK 24.0.2**:

~~~text
monitor ownership supported: true
ownable synchronizer supported: true
platform workers visible: true
lock owner is WAITING yet holds monitor: true
target monitor found: true
monitor acquisition frame matches stack: true
monitor acquired inside holdBoth: true
owner holds ReentrantLock synchronizer: true
contender is BLOCKED on monitor: true
contender owner id matches: true
contender lock identity matches monitor: true
contender has not acquired monitor: true
basic snapshot omits lock ownership arrays: true
our two threads not deadlocked: true
both workers terminated: true
~~~

### Diễn giải kết quả

**`monitor ownership supported` / `ownable synchronizer supported`:** runtime đã thử nghiệm hỗ trợ cả hai khả năng. Nếu VM khác trả false, demo báo skipped và không bắt đầu workers; tool production có thể lấy partial snapshot bằng flags tương ứng.

**`platform workers visible`:** `getAllThreadIds()` cho thấy hai threads đang sống, vì cả hai được tạo bằng `Thread.ofPlatform`. Đây không phải API để liệt kê mọi virtual threads.

**`owner is WAITING yet holds monitor`:** owner đang đợi `CountDownLatch.await()` nhưng **chưa thoát synchronized block**, nên vẫn giữ monitor. Điều này khác `Object.wait()` **gọi trên đúng monitor**, vốn nhả monitor ấy khi chờ.

**`target monitor found` / `monitor acquisition frame matches stack`:** `MonitorInfo` chứa identity của `GATE` và frame ở method `holdBoth`. `getLockedStackDepth()` là vị trí trong mảng `holdingInfo.getStackTrace()`, **không** phải nested locking depth.

**`owner holds ReentrantLock synchronizer`:** ownable synchronizer của `ReentrantLock` xuất hiện trong `LockInfo[]`. Code chỉ kiểm class name có `ReentrantLock` vì tên implementation cụ thể phụ thuộc runtime. **LockInfo không có acquisition frame**, không dùng stack của `MonitorInfo` để nhận nhầm nơi `ReentrantLock.lock()` đã chạy.

**`contender is BLOCKED` / `owner id matches`:** contender chưa vào synchronized block vì `GATE` có owner. `getLockInfo()` của contender là lock **nó chờ**, `getLockedMonitors()` không chứa `GATE` vì contender **chưa sở hữu**.

**`basic snapshot omits lock ownership arrays`:** `getThreadInfo(ownerId)` không thu ownership arrays. Không đánh giá thread “không giữ lock” chỉ vì dữ liệu không được request.

**`our two threads not deadlocked`:** program tạo contention có thể tháo được, **không có vòng chờ A→B→A**. Dù `findDeadlockedThreads` có thể phát hiện deadlocks khác trong JVM, test chỉ kiểm hai thread ID do nó tạo.

**`both workers terminated`:** `finally` giải phóng latch và join threads. Không sinh thread bị treo hoặc tạo deadlock vĩnh viễn để minh họa.

## 12. Contention monitoring và CPU time: tùy chọn có chi phí

Ngoài trạng thái/stack, `ThreadMXBean` cung cấp:
- `getBlockedCount()` và `getWaitedCount()`;
- `getBlockedTime()` và `getWaitedTime()`;
- CPU time ở mỗi platform thread nếu runtime hỗ trợ.

**Phân biệt count và time:** blocked count là số lần thread bị block để vào monitor; blocked time là **tổng thời gian ước lượng** chỉ khi thread contention monitoring được bật. Khi disabled, `getBlockedTime()` trả **-1**. Đừng đưa -1 vào biểu đồ như “âm 1 ms”; đó là sentinel không có dữ liệu. `getWaitedTime()` cũng có sentinel tương tự.

Capability check trước khi đọc:

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
if (bean.isThreadContentionMonitoringSupported()) {
    boolean alreadyEnabled = bean.isThreadContentionMonitoringEnabled();
    // Chỉ thay đổi trạng thái nếu monitoring policy của JVM cho phép.
    // Trong công cụ production, ưu tiên không bật/tắt thay cho owner khác.
}
if (bean.isThreadCpuTimeSupported()
        && bean.isThreadCpuTimeEnabled()) {
    long cpuNanos = bean.getThreadCpuTime(targetPlatformThreadId);
    if (cpuNanos >= 0) {
        // Metric là thời gian CPU, không phải wall-clock duration.
    }
}
~~~

Đây là snippet trong method có biến `targetPlatformThreadId`. `setThreadContentionMonitoringEnabled(true)` có thể ảnh hưởng **toàn JVM**, làm tăng overhead và reset thống kê khi re-enabled; chỉ bật trong một controlled diagnostic window với quyền owner và khôi phục chính sách nếu bạn là thành phần duy nhất điều khiển state. Không biến monitoring tool thành nơi âm thầm thay cấu hình của các công cụ khác.

**CPU ≠ blocked duration:** thread chờ monitor có thể dùng rất ít CPU nhưng wall-clock latency tăng cao; do đó phải phân tích `ThreadInfo` và blocked time, không chỉ CPU counters.

## 13. Phân tích deadlock đúng giới hạn API

`ThreadMXBean.findMonitorDeadlockedThreads()` tìm deadlock cycles giữa **object monitors**. `findDeadlockedThreads()` mở rộng tới **object monitors và ownable synchronizers** khi capability phù hợp. Cả hai chỉ áp dụng trong phạm vi **platform threads** được quản lý bởi ThreadMXBean, không phát hiện mọi loại deadlock ở database, I/O, distributed locks, semaphore permits hoặc virtual threads.

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
if (bean.isSynchronizerUsageSupported()) {
    long[] deadlocked = bean.findDeadlockedThreads();
    if (deadlocked != null && deadlocked.length > 0) {
        boolean monitors = bean.isObjectMonitorUsageSupported();
        boolean synchronizers = bean.isSynchronizerUsageSupported();
        ThreadInfo[] details = bean.getThreadInfo(
                deadlocked, monitors, synchronizers);
        // Lưu/hiển thị thông tin owner, waiting lock và stack có giới hạn.
    }
}
~~~

Đây là snippet trong method có imports. `null` có thể có nghĩa **không có deadlock phát hiện**; một JVM khác không hỗ trợ capability có thể có hành vi khác nên phải kiểm API docs/provider. Không dùng `findDeadlockedThreads()==null` để khẳng định cả hệ thống hoàn toàn không gặp liveness issue.

**Đừng tạo deadlock không thể dọn** chỉ để học. Demo thứ hai dùng latch có `finally` để đóng an toàn. Nếu cần test `findDeadlockedThreads` bằng một vòng chờ thật, nên chạy **trong process con cô lập, có timeout/kill và log capture**, không tạo threads bị kẹt mãi trong ứng dụng đang phục vụ traffic.

### Nhìn owner và contention thành một chuỗi

~~~text
Contender BLOCKED on monitor M
  -> ThreadInfo.getLockInfo() identifies M
  -> ThreadInfo.getLockOwnerId() identifies owner P
  -> ThreadInfo of P:
       getLockedMonitors() includes M
       MonitorInfo.getLockedStackFrame() shows acquisition site
       getStackTrace() shows what P is currently doing
       getLockedSynchronizers() shows P's exclusive AQS locks
  -> Observe P's CPU/blocked time/JFR traces, not just one snapshot
~~~

Với ReentrantLock, contender thường `WAITING` do park; owner có thể được suy từ AQS/JMX information nếu runtime cung cấp, nhưng **không** giả rằng một `LockInfo` đang sở hữu có stack acquisition frame. Cần kết hợp logging/tracing hoặc instrumentation riêng nếu cần lịch sử ai lock tại dòng nào.

## 14. Sự thật quan trọng ở Java 21+: ThreadMXBean không đo virtual threads

Theo Java SE 25 Javadoc, **`java.lang.management.ThreadMXBean` chỉ theo dõi platform threads**. Cụ thể:
- `getThreadCount()/getPeakThreadCount()/getAllThreadIds()` liên quan platform threads.
- `getThreadInfo(new long[]{virtualThreadId},...)` trả **null** cho virtual thread ID.
- `dumpAllThreads(...)` không liệt kê virtual threads.
- Một `null` trong kết quả getThreadInfo còn có thể do thread kết thúc hoặc nonexistent, vì vậy phải biết thread kind/lifetime trước khi kết luận.
- Không vì thread MXBean count thấp mà khẳng định service có ít concurrent tasks khi app dùng virtual threads.

**API khác đang áp dụng hiện nay:** từ **JDK 24**, `jdk.management.VirtualThreadSchedulerMXBean` cho biết **scheduler's target parallelism**, kích thước platform-thread pool và ước lượng mounted/queued virtual threads. Đây là **scheduler aggregate**, **không** cung cấp stack/locked monitors của từng virtual thread qua `ThreadMXBean`.

### Điều kiện hỗ trợ và sentinel

| API JDK 24+ | Ý nghĩa |
| --- | --- |
| `getParallelism()` | Target parallelism scheduler, không phải total live virtual threads |
| `getPoolSize()` | Số platform threads của scheduler đã tạo và còn sống; có thể -1 nếu unknown |
| `getMountedVirtualThreadCount()` | Estimate số virtual threads đang mounted; có thể -1 nếu unknown |
| `getQueuedVirtualThreadCount()` | Estimate queued virtual threads; có thể -1 nếu unknown |
| `setParallelism(int)` | Operation **đổi cấu hình scheduler**, không nên gọi khi chỉ quan sát |

Các metrics này **ước lượng** và có thể overestimate, không phải transactionally consistent snapshot. Ứng dụng monitoring nên đọc chúng như gauges có timestamp, không dùng để quyết định quyền truy cập/lock synchronization.

## 15. Thực hành số 3: VirtualThreadSchedulerMXBean từ JDK 24

**File `VirtualSchedulerMxbeanDemo.java`**, yêu cầu JDK 24+ do import `jdk.management.VirtualThreadSchedulerMXBean`. Đây là API JDK hiện hành, nhưng **không có trên Java 17/21**.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import jdk.management.VirtualThreadSchedulerMXBean;

public final class VirtualSchedulerMxbeanDemo {
    public static void main(String[] args) throws Exception {
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        VirtualThreadSchedulerMXBean scheduler =
                ManagementFactory.getPlatformMXBean(
                        VirtualThreadSchedulerMXBean.class);
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName schedulerName =
                new ObjectName("jdk.management:type=VirtualThreadScheduler");
        System.out.println("virtual scheduler MXBean available: "
                + (scheduler != null));
        System.out.println("virtual scheduler JMX name registered: "
                + server.isRegistered(schedulerName));
        System.out.println("target parallelism positive: "
                + (scheduler != null && scheduler.getParallelism() > 0));
        System.out.println("pool size estimate valid: "
                + (scheduler != null && scheduler.getPoolSize() >= -1));
        System.out.println("mounted count estimate valid: "
                + (scheduler != null
                && scheduler.getMountedVirtualThreadCount() >= -1));
        System.out.println("queued count estimate valid: "
                + (scheduler != null
                && scheduler.getQueuedVirtualThreadCount() >= -1));

        CountDownLatch running = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        Thread virtual = Thread.ofVirtual().name("mxbean-virtual-sample")
                .unstarted(() -> {
                    running.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                    }
                });
        try {
            virtual.start();
            if (!running.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Virtual thread did not start");
            }
            long virtualId = virtual.threadId();
            ThreadInfo[] selected =
                    threads.getThreadInfo(new long[]{virtualId}, false, false);
            boolean inPlatformDump = Arrays.stream(
                    threads.dumpAllThreads(false, false, 8))
                    .anyMatch(t -> t.getThreadId() == virtualId);
            System.out.println("virtual thread running: " + virtual.isAlive());
            System.out.println("ThreadMXBean excludes virtual ID: "
                    + (selected.length == 1 && selected[0] == null));
            System.out.println("platform dump excludes virtual ID: "
                    + !inPlatformDump);
        } finally {
            release.countDown();
            virtual.join(5000);
            if (virtual.isAlive()) {
                virtual.interrupt();
                throw new IllegalStateException("Virtual thread stuck");
            }
        }
        System.out.println("virtual worker terminated: true");
    }
}
~~~

Lệnh:

~~~bash
javac --release 24 VirtualSchedulerMxbeanDemo.java
java VirtualSchedulerMxbeanDemo
~~~

**Stdout chính xác** đã kiểm thử trên OpenJDK 24.0.2:

~~~text
virtual scheduler MXBean available: true
virtual scheduler JMX name registered: true
target parallelism positive: true
pool size estimate valid: true
mounted count estimate valid: true
queued count estimate valid: true
virtual thread running: true
ThreadMXBean excludes virtual ID: true
platform dump excludes virtual ID: true
virtual worker terminated: true
~~~

**Đọc kết quả:** scheduler MXBean được đăng ký ở `jdk.management:type=VirtualThreadScheduler` và gauges có values hợp lệ. Program **không** thay đổi `setParallelism` hay JVM settings. Một virtual thread được giữ sống bằng latch, nhưng `ThreadMXBean.getThreadInfo` trả null và `dumpAllThreads` không liệt kê nó — **đúng theo phạm vi API**, không phải thiếu quyền hay do virtual thread đã chết.

Các giá trị `getPoolSize()`, `getMountedVirtualThreadCount()` và `getQueuedVirtualThreadCount()` có thể khác nhau theo workload, vì thế demo chỉ xác minh chúng không nhỏ hơn -1, **không hardcode** một số threads. Một implementation có thể trả -1 cho unknown; dashboard không nên gán -1 thành giá trị âm thực.

**Không dùng JDK 24 extension để suy ra mỗi virtual thread đang giữ ReentrantLock nào.** Scheduler MXBean quan sát mức scheduler. Để điều tra individual virtual threads, hãy dùng **JDK diagnostic commands hỗ trợ virtual-thread dumps**, JFR và application tracing thích hợp.

## 16. Quan sát sự cố theo quy trình: metric → thread dump → hypothesis

Một ví dụ điển hình:

**Tình huống:** `application.request_latency_p99` tăng, `ThreadMXBean.getThreadCount` tăng, heap usage vẫn ổn. Đừng vội kết luận “CPU quá tải” — có thể các platform threads đang chờ cùng một monitor và CPU thấp.

### Bước 1. Xác nhận tín hiệu và ngữ cảnh

Thu các gauges theo cùng timestamp:
- `RuntimeMXBean.getUptime` và JDK/build/version;
- `ThreadMXBean.getThreadCount/getPeakThreadCount`;
- `MemoryMXBean.getHeapMemoryUsage`;
- App MXBean `Accepted/Rejected/Processed/QueueCapacity`;
- CPU feature support/enabled và CPU metrics nếu có;
- JFR/GC metrics nếu hiện tượng trùng GC pause.

Nếu **Accepted tăng nhanh, Processed tăng chậm, Rejected tăng**, đó có thể là backlog/overload chứ không nhất thiết lock contention. Nếu counters bình thường nhưng nhiều threads bị BLOCKED, mới ưu tiên lock analysis.

### Bước 2. Chọn đúng platform-thread IDs

Trong incident có thể lấy `getAllThreadIds()` hoặc chọn IDs từ thread dump đã thu. Ưu tiên **một nhóm nghi vấn** thay vì quét toàn bộ JVM mỗi vài mili-giây. Gọi:

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
boolean monitor = bean.isObjectMonitorUsageSupported();
boolean ownable = bean.isSynchronizerUsageSupported();
ThreadInfo[] snapshots = bean.getThreadInfo(
        suspectedPlatformThreadIds, monitor, ownable);
~~~

Đây là snippet trong method có mảng `suspectedPlatformThreadIds`. `ThreadInfo[]` có thể chứa **null** nếu thread ID không tồn tại/đã kết thúc/virtual; handle nullable entries.

### Bước 3. Phân loại bị chặn và giữ khóa

Với từng snapshot:
- `getThreadState` là BLOCKED, WAITING hay TIMED_WAITING?
- `getLockInfo` chỉ ra blocker/lock đang chờ?
- `getLockOwnerId` có owner ID hay -1?
- Owner `getLockedMonitors` chứa object identity tương ứng?
- Nếu là monitor: `MonitorInfo.getLockedStackFrame` cho acquisition location?
- Owner `getLockedSynchronizers` cho biết có những exclusively owned AQS locks nào?
- Current stack của owner nằm ở I/O, latch, DB call, logging hoặc synchronized region?

**Không đánh đồng WAITING với không giữ khóa**; demo 2 cho owner đang WAITING mà sở hữu cả monitor và ownable synchronizer.

### Bước 4. Lặp snapshot và đo thời gian

Một snapshot là dữ liệu **thoáng qua**, không đủ xác định contention kéo dài. Có thể thu thêm 2–3 snapshots với khoảng cách hợp lý và giới hạn overhead, so:
- Số threads đợi cùng một lock;
- Owner giữ/nhả monitor;
- `getBlockedCount` tăng;
- `getBlockedTime` tăng khi contention monitoring được owner bật;
- Application request latency, queue wait và JFR lock events.

Không áp một threshold “blockedCount>0” là lỗi; một lần tranh monitor ngắn trong code đúng cũng có thể tăng counter. Tìm **thời gian, ảnh hưởng SLO và pattern**.

### Bước 5. Kết hợp JFR và thread dumps hiện đại

JFR hữu ích cho CPU samples, allocations, blocked events, GC và tình huống cần timeline. HotSpot `jcmd` có thể xuất thread dump để xem **nhiều virtual threads** (tùy JDK/options). `ThreadMXBean.dumpAllThreads` chỉ chụp platform threads; **hai nguồn dữ liệu không có cùng phạm vi**, vì thế không dùng số thread của chúng để đối chiếu tuyệt đối.

## 17. Lưu ý đọc lock metrics chính xác

### “Không có monitors” chưa chắc thread không giữ monitor

Khi gọi `ThreadMXBean.getThreadInfo(id)` hoặc overload không bật `lockedMonitors`, `ThreadInfo.getLockedMonitors()` trả mảng rỗng **cả khi thread đang giữ khóa**. Muốn biết ownership phải yêu cầu overload phù hợp và kiểm runtime capability.

### Contender có getLockInfo nhưng không có locked monitor đó

Một thread `BLOCKED` chờ monitor chưa acquire thì `getLockInfo()` mô tả đối tượng nó **đang đợi**, còn `getLockedMonitors()` chỉ mô tả những monitors **đang sở hữu**. Dùng mảng owned để tìm owner; dùng waiting lock/owner ID để nối quan hệ.

### Synchronizer có thể là implementation nội bộ của ReentrantLock

`LockInfo.getClassName()` có thể hiển thị internal AQS synchronizer, không đơn giản là `java.util.concurrent.locks.ReentrantLock`. Đừng hardcode tên internal class; lọc theo ngữ cảnh và theo contract.

### MonitorInfo có acquisition frame; LockInfo không có

`MonitorInfo.getLockedStackFrame()` cho stack frame liên quan khi monitor được acquire nếu JVM có thông tin. `LockInfo` của ownable synchronizer không có method ấy. Muốn biết ReentrantLock được gọi ở đâu trong quá khứ, cần telemetry instrumentation hoặc logging riêng chứ không gán bừa current top stack.

### Object.wait khác CountDownLatch.await trong synchronized

`Object.wait()` nhả monitor của chính object được wait (trong thời gian chờ), còn `CountDownLatch.await()` **không nhả monitor bên ngoài**. Code giữ monitor trong khi chờ một latch có thể gây contention lan rộng — đúng tình huống demo dùng để quan sát.

### JMX snapshot không phải synchronization control

`ThreadInfo` được thiết kế cho **monitoring**, không phải để ra quyết định “thread nào được phép acquire lock”. Thread state/owner có thể thay đổi ngay sau snapshot. Không dùng `getThreadState()==BLOCKED` làm signal liveness để điều khiển logic nghiệp vụ.

## 18. Chi phí quan sát và bảo mật

### Tránh full thread dumps quá thường xuyên

`ThreadMXBean.getThreadInfo(ids,true,true)` và `dumpAllThreads(true,true,maxDepth)` có chi phí phụ thuộc JVM và số platform threads. Nếu bật contention monitoring, overhead có thể tăng. Trên production:
- Chọn IDs nghi vấn hoặc sampling có cadence;
- Giới hạn stack depth khi không cần acquisition frame đầy đủ;
- Chụp full dump trong incident window;
- Đừng kích hoạt monitoring liên tục ở hot path mỗi request;
- Đo overhead của chính collector/JMX exporter.

### Cẩn trọng với remote JMX

Bài chỉ dùng **local MBeanServer**. Nếu triển khai remote access, có nguy cơ lộ class/method names, runtime arguments, heap/thread internals hoặc các operations thay đổi trạng thái:
- Giới hạn network, TLS, authentication, authorization và allowed operations;
- Không mở public JMX port bằng một cấu hình thiếu kiểm soát;
- Không log secrets hoặc raw payloads trong attributes;
- Dùng MBean ObjectName có domain phù hợp, không trùng beans của thư viện khác;
- Có lifecycle register/unregister;
- Xem security policy và audit trước khi expose các setters/operations.

### Export thành dashboards

Một dashboard không nên vẽ `getBlockedTime==-1` thành thời gian âm, hoặc chia `MemoryUsage.getMax()==-1`. Thiết kế biểu đồ với:
- Đồng nhất units (bytes, milliseconds, nanoseconds);
- Tags có cardinality giới hạn; tránh dùng thread ID làm metric label cho mọi thời điểm;
- Recording timestamp và build/runtime version;
- Các counters nghiệp vụ có định nghĩa success/failure rõ;
- Monotonic counters nếu không reset và gauges có thể dao động;
- Alert theo SLO/tín hiệu kéo dài, không theo một điểm sample.

## 19. Một số lỗi phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi mọi JMX bean là MXBean | Mapping types không giống | Xác định interface, Open Types |
| Thấy `HeapMemoryUsage` qua JMX mà cast `MemoryUsage` | Attribute là `CompositeData` | Cast CompositeData hoặc typed proxy |
| Hardcode heap usage/GC count trong test | Khác theo runtime | Kiểm invariants và sentinel |
| Chia cho `MemoryUsage.getMax()==-1` | Ratio sai | Guard unknown |
| Coi `getThreadCount` là tất cả virtual threads | Thiếu phạm vi | ThreadMXBean chỉ platform |
| Dùng `getThreadInfo(id)` để đo ownership | Không yêu cầu lock arrays | `getThreadInfo(ids,true,true)` |
| Không kiểm `isObjectMonitorUsageSupported` | UnsupportedOperationException | Capability check |
| Không kiểm `isSynchronizerUsageSupported` | UnsupportedOperationException | Capability check |
| Coi `WAITING` là không giữ monitor | Thread có thể chờ latch khi vẫn giữ monitor | Đọc getLockedMonitors |
| Coi `BLOCKED` là mọi ReentrantLock contention | AQS dùng park và WAITING | Phân biệt monitor/ownable lock |
| Nhầm `getLockInfo` là khóa đang sở hữu | Đây là khóa đang đợi | Đọc getLockedMonitors/getLockedSynchronizers |
| Ép `LockInfo` thành `MonitorInfo` | Ownable lock không có acquisition frame | Xem đúng contract |
| Không kiểm lockedStackDepth âm | ArrayIndexOutOfBoundsException | Guard depth/frame |
| Coi identityHashCode là ID duy nhất | Có va chạm, không bền qua restart | Correlation kèm context |
| Gọi `findDeadlockedThreads()==null` là không có mọi deadlock | Không bao phủ DB/I/O/virtual | JFR/app traces/other diagnostics |
| Dùng code tự tạo deadlock không có timeout | Treo JVM/CI | Isolated process hoặc controlled contention |
| Tự bật contention monitoring ở mọi service | Chi phí và policy race | Chỉ khi cần và có owner |
| Coi CPU nanoseconds là wall clock | Tính latency sai | Tách CPU và elapsed time |
| Coi `getBlockedTime==-1` là thời gian âm | Sentinel không có dữ liệu | Hiển thị unavailable |
| Hardcode tên ReentrantLock sync nội bộ | JVM implementation khác | Match có ngữ cảnh |
| Không handle null `ThreadInfo[]` | NPE do terminated/virtual IDs | Null checks |
| Tưởng scheduler MXBean là per-virtual stack profiler | Chỉ aggregate scheduler | JFR/jcmd |
| Compile JDK24 extension trên JDK17 | Không có package/API | Tách target `--release` |
| Đưa full thread dump vào API công khai | Lộ code/state nhạy cảm | AuthN/AuthZ, retention, redaction |
| Đăng ký custom MBean rồi không unregister | Resource/namespace leak | finally/shutdown lifecycle |
| Dùng MBeanServer snapshot để điều khiển threads | Race | Chỉ observability |
| Poll cả JVM mỗi 1ms | Overhead | Có budget và incident-triggered sampling |

## 20. Checklist thực hành/kiểm thử

| Kịch bản | Kỳ vọng |
| --- | --- |
| Heap usage read | used≥0, committed≥used |
| Memory max unknown | Chấp nhận -1 |
| ClassLoading bean | Loaded count dương |
| Runtime bean | Uptime không âm |
| OS bean | Available processors >0 |
| GC beans | Danh sách có thể thay đổi theo GC/JVM |
| CPU measurement disabled | Guard, không ép đọc hay bật bừa |
| Platform MBeanServer | Built-in memory bean đã đăng ký |
| JMX HeapMemoryUsage attribute | Mapped CompositeData |
| Custom MXBean interface | Public, tên kết thúc MXBean |
| Custom MXBean registration | ObjectName trong namespace riêng |
| Custom getter | Proxy và getAttribute trả số đã cập nhật |
| MXBean unregister | Không còn trong registry |
| Object monitor support | Capability được kiểm |
| Ownable sync support | Capability được kiểm |
| Platform owner/contender IDs | Có trong ThreadMXBean |
| Owner WAITING trong synchronized | Monitor vẫn owned |
| MonitorInfo | Đúng identity và lockedStackFrame |
| Stack depth | Index vào ThreadInfo stack |
| ReentrantLock | LockInfo trong owned synchronizers |
| Contender BLOCKED | getLockOwnerId trỏ owner |
| Contender chưa acquire monitor | Không xuất hiện trong owned monitors |
| Basic getThreadInfo(id) | Owned-lock arrays trống |
| Controlled contention | Không tạo deadlock cycle |
| Cleanup | Latch release, threads join thành công |
| findDeadlockedThreads | Xử lý null/unsupported, không overclaim |
| Virtual thread đang sống | ThreadMXBean getThreadInfo null |
| dumpAllThreads | Không liệt kê virtual ID |
| JDK24 VirtualThreadSchedulerMXBean | Scheduler gauges và ObjectName hợp lệ |
| Scheduler unknown estimate | Chấp nhận -1 |
| Thread snapshot nhiều lần | Không assume atomic business state |
| JMX remote | Không mở ngoài policy |
| Metrics backend | Có timestamp/units/sampling/cardinality |

## 21. Tự kiểm tra kiến thức

1. **MXBean dùng làm gì?** — Cung cấp interface quản lý/giám sát, hỗ trợ Open Type mapping.
2. **Lấy platform MBeanServer?** — `ManagementFactory.getPlatformMBeanServer()`.
3. **MemoryMXBean ObjectName là gì?** — `java.lang:type=Memory`.
4. **ThreadMXBean ObjectName?** — `java.lang:type=Threading`.
5. **`HeapMemoryUsage` qua MBeanServer có kiểu gì?** — `CompositeData`.
6. **Typed MXBean proxy được tạo bằng gì?** — `JMX.newMXBeanProxy`.
7. **Một custom MXBean cần gì?** — Public interface theo MXBean naming/annotation, compliant implementation và registerMBean.
8. **Có nên mở remote JMX mặc định?** — Không.
9. **Heap max có thể bằng -1 không?** — Có, unknown.
10. **GC collection time có thể -1 không?** — Có, unsupported.
11. **RuntimeMXBean uptime đo gì?** — JVM elapsed uptime.
12. **getLoadedClassCount là số requests không?** — Không.
13. **getThreadCount gồm virtual threads không?** — Không.
14. **ThreadMXBean theo dõi loại threads nào?** — Platform threads.
15. **Muốn nhận locked monitors từ ThreadInfo?** — Yêu cầu overload `getThreadInfo(ids,true,true)` với capability.
16. **getLockedMonitors trả kiểu gì?** — `MonitorInfo[]`.
17. **getLockedSynchronizers trả kiểu gì?** — `LockInfo[]`.
18. **getLockInfo của contender mô tả gì?** — Lock nó đang chờ, không phải đang giữ.
19. **getLockOwnerId có thể trả gì khi không biết owner?** — -1.
20. **MonitorInfo.getLockedStackDepth là gì?** — Index trong ThreadInfo.getStackTrace.
21. **LockInfo của ReentrantLock có getLockedStackFrame không?** — Không.
22. **Một thread WAITING có thể vẫn giữ monitor?** — Có.
23. **CountDownLatch.await có tự nhả synchronized monitor không?** — Không.
24. **Object.wait trên đúng monitor có nhả monitor khi chờ không?** — Có.
25. **BLOCKED và WAITING của AQS lock giống nhau không?** — Không.
26. **Thread state có phản ánh exact CPU usage không?** — Không.
27. **Blocked time -1 có nghĩa gì?** — Chưa bật/không có dữ liệu theo contract.
28. **Có nên bật contention monitoring không xin phép owner JVM?** — Không.
29. **Có thể suy từ một snapshot ra deadlock mọi hệ thống không?** — Không.
30. **Sao không tạo deadlock vô thời hạn trong test?** — JVM/CI có thể treo, không dọn.
31. **VirtualThreadSchedulerMXBean xuất hiện từ Java nào?** — Java 24.
32. **Nó có cho per-virtual stack không?** — Không.
33. **ThreadMXBean.getThreadInfo(virtualId) trả gì?** — Null.
34. **getQueuedVirtualThreadCount có thể -1 không?** — Có, unknown estimate.
35. **ThreadMXBean CPU time có cần support/enable flags không?** — Có.
36. **Custom MXBean getter có nên phơi secrets không?** — Không.
37. **Làm sao tránh MBean namespace collision?** — Domain/ObjectName riêng, register/unregister lifecycle.
38. **Làm sao đánh giá lock contention kéo dài?** — Lặp snapshot có giới hạn + metrics/JFR.
39. **Có thể dùng `isObjectMonitorUsageSupported` làm lock ownership proof không?** — Không, chỉ capability.
40. **Nếu thread đã chết giữa lúc lấy ID và snapshot?** — Handle null, không retry vô hạn.
41. **Có nên dùng MXBean để điều khiển việc acquire lock?** — Không.
42. **Tại sao phân biệt LockInfo và MonitorInfo?** — Chỉ MonitorInfo có acquisition stack location.
43. **Vì sao metric Count và Time khác nhau?** — Frequency vs duration; time cần bật monitoring.
44. **MemoryMXBean và RuntimeMXBean thay profiler được không?** — Không, chỉ metrics/snapshots.
45. **Khi nào xem JFR?** — Cần timeline/performance, locks, GC, allocations.
46. **Một custom MXBean có đủ làm alerting chưa?** — Chưa, cần collector/storage/alerts.
47. **Mục tiêu cuối khi thấy nhiều BLOCKED?** — Tìm lock owner và code path, xác định ảnh hưởng SLO và root cause.

## 22. Tài liệu chính thức còn áp dụng

- [Java SE 25 — ManagementFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ManagementFactory.html): các platform MXBeans, `getPlatformMBeanServer` và registered ObjectNames.
- [Java SE 25 — MemoryMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/nonheap usage và management.
- [Java SE 25 — MemoryUsage](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryUsage.html): used/committed/max và undefined -1.
- [Java SE 25 — RuntimeMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/RuntimeMXBean.html): uptime/start time và JVM identity.
- [Java SE 25 — ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): loaded/unloaded class counts.
- [Java SE 25 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): GC count/time.
- [Java SE 25 — ThreadMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html): platform threads, ownership capabilities, thread CPU/blocked time và deadlock detection.
- [Java SE 25 — ThreadInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadInfo.html): thread state, waiting lock/owner, owned locks và stack.
- [Java SE 25 — MonitorInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MonitorInfo.html): lockedStackDepth/lockedStackFrame.
- [Java SE 25 — LockInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/LockInfo.html): class identity của locks/ownable synchronizers.
- [Java SE 25 — JMX](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/JMX.html): `isMXBeanInterface` và `newMXBeanProxy`.
- [Java SE 25 — MBeanServer](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/MBeanServer.html): register/unregister, getAttribute.
- [Java SE 25 — Using the Platform MBean Server and Platform MXBeans](https://docs.oracle.com/en/java/javase/25/management/using-platform-mbean-server-and-platform-mxbeans.html): direct, proxy và indirect access.
- [Java SE 25 — VirtualThreadSchedulerMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/jdk/management/VirtualThreadSchedulerMXBean.html): JDK24+ scheduler parallelism/pool/mounted/queued virtual-thread estimates.
- [Java SE 25 — Thread](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): `Thread.ofPlatform`, `Thread.ofVirtual`, `threadId` và trạng thái.
- [Java SE 25 — java.lang.management package](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/package-summary.html): chuẩn MXBeans/Open Types.
- [Java SE 25 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html): event recording và runtime observability.
- [OpenJDK — JEP 444 Virtual Threads](https://openjdk.org/jeps/444): virtual threads chính thức từ Java 21.

**Kết luận:** Quan sát chỉ số JVM bằng `ManagementFactory` và JMX MXBeans cho biết heap, uptime, loaded classes, GC, số platform threads và counters nghiệp vụ; nhưng metrics tổng hợp không tự chỉ ra ai giữ khóa. Để phân tích contention, dùng `ThreadMXBean.getThreadInfo(ids,true,true)` sau capability checks, đọc **khóa đang chờ** bằng `getLockInfo/getLockOwnerId` và **khóa đang giữ** bằng `getLockedMonitors/getLockedSynchronizers`; với `MonitorInfo` có thể truy về acquisition stack frame. Mọi kết quả đều là snapshot chứ không phải synchronization control. Đặc biệt, `ThreadMXBean` không bao phủ virtual threads; JDK 24+ bổ sung `VirtualThreadSchedulerMXBean` cho scheduler aggregates. Muốn production-grade observability, cần ghép snapshots với metrics có units/timestamps, JFR, context-aware tracing, sampling, giới hạn overhead và bảo mật quyền truy cập JMX.