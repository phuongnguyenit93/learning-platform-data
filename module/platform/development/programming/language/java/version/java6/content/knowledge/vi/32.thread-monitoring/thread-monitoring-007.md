# Theo dõi luồng: Kiểm tra khả năng hỗ trợ trước khi yêu cầu dữ liệu

## Mục tiêu học tập

Các công cụ theo dõi luồng Java có thể đọc số luồng đang sống, thời gian CPU, thời gian bị chặn/chờ, stack trace, thông tin object monitors, ownable synchronizers và số byte bộ nhớ cấp phát theo luồng. Nhưng **không phải mọi JVM, mọi phiên bản, mọi nền tảng và mọi cấu hình runtime đều cung cấp đầy đủ những dữ liệu đó**.

Trong Java hiện đại, **java.lang.management.ThreadMXBean** là API chuẩn để giám sát **platform threads**. Những năng lực như CPU time, contention monitoring và lấy thông tin locks có **capability checks** riêng. Một số chỉ số cấp phát bộ nhớ theo luồng có thể lấy qua phần mở rộng **com.sun.management.ThreadMXBean**, nếu implementation cung cấp và tính năng được hỗ trợ/bật.

**Nguyên tắc của bài: kiểm tra khả năng hỗ trợ → kiểm tra trạng thái bật/tắt → chỉ gọi thao tác đọc phù hợp → xử lý giá trị thiếu và race conditions.** Không thử gọi API tốn kém rồi catch exception làm cách khám phá capability chính; cũng không tự ý bật tính năng giám sát toàn JVM mỗi khi một công cụ muốn xem dữ liệu.

Sau bài, bạn có thể:

1. Phân biệt các trạng thái **UNSUPPORTED**, **DISABLED**, **AVAILABLE**, **UNAVAILABLE** và **DENIED**.
2. Dùng **ManagementFactory.getThreadMXBean()** và hiểu phạm vi hỗ trợ platform threads.
3. Kiểm tra **isThreadCpuTimeSupported()** và **isCurrentThreadCpuTimeSupported()** theo nhu cầu đọc CPU của luồng bất kỳ hay luồng đang chạy.
4. Chỉ gọi **isThreadCpuTimeEnabled()** và **getCurrentThreadCpuTime()** khi capability cho phép; xử lý kết quả **-1**.
5. Kiểm tra **isThreadContentionMonitoringSupported()** và **isThreadContentionMonitoringEnabled()** trước khi diễn giải **getBlockedTime()/getWaitedTime()**.
6. Kiểm tra **isObjectMonitorUsageSupported()** và **isSynchronizerUsageSupported()** trước khi yêu cầu locked monitors và ownable synchronizers trong **getThreadInfo()/dumpAllThreads()**.
7. Chỉ dùng **findDeadlockedThreads()** khi biết VM hỗ trợ ownable synchronizer monitoring; phân biệt với **findMonitorDeadlockedThreads()**.
8. Phát hiện extension **com.sun.management.ThreadMXBean** và kiểm tra **isThreadAllocatedMemorySupported()/Enabled()** trước khi lấy allocated bytes.
9. Hiểu các giá trị thiếu, thread ID biến mất, thread dump quá lớn và giới hạn với **virtual threads** trong Java 21+.
10. Chạy chương trình **Java 17+** với fake probes bao phủ các nhánh supported/disabled/denied và một live probe không phụ thuộc máy.
11. Thiết kế metrics/diagnostic UI có phân loại missing data, không coi unsupported là 0.
12. Xác định khi nào bật capability có tác động toàn JVM, cần sự chấp thuận vận hành và cleanup.

**Phiên bản và giới hạn:** Ví dụ tương thích Java 17 trở lên, đã biên dịch bằng **javac --release 17** và chạy trên **OpenJDK 24.0.2**. API chuẩn thuộc module **java.management**; extension cấp phát thuộc module **jdk.management**. Phần mô tả về virtual threads dựa trên API hiện hành của Java SE 26. Bài chỉ áp dụng các kiến thức vẫn còn được hỗ trợ, không dựa vào hành vi lỗi thời hay giả định độc quyền của một bản JVM.

---

## 1. Theo dõi luồng là gì và vì sao phải hỏi capability trước?

Khi một ứng dụng chậm, chúng ta có thể cần biết:

- Hiện có bao nhiêu **platform threads**?
- Luồng nào tiêu thụ nhiều CPU?
- Luồng nào bị chặn trên **synchronized monitor**?
- Luồng nào đang giữ **java.util.concurrent locks**?
- Mức contention và thời gian chờ có tăng không?
- Thread nào cấp phát nhiều bytes trên heap?
- Có **deadlock** thực sự hay chỉ là nhiều luồng ở trạng thái WAITING hợp lệ?
- JVM hiện tại có hỗ trợ loại phép đo ta định yêu cầu không?

Không thể suy từ việc **ThreadMXBean object tồn tại** rằng mọi phương pháp đều dùng được.

~~~text
             Công cụ giám sát Java
                       │
                       ▼
          ManagementFactory.getThreadMXBean()
                       │
                       ▼
          Xác định dữ liệu cần lấy
                       │
                       ▼
            Hỏi is*Supported()
                 ┌─────┴─────┐
                 │           │
                false       true
                 │           │
                 ▼           ▼
          UNSUPPORTED   Nếu có cờ bật/tắt:
                         hỏi is*Enabled()
                             ┌─┴─┐
                          false  true
                            │     │
                            ▼     ▼
                         DISABLED  Đọc có giới hạn
                                      │
                              ┌───────┴────────┐
                              │                │
                         Giá trị hợp lệ     -1/null/lỗi
                              │                │
                              ▼                ▼
                           AVAILABLE      UNAVAILABLE/
                                           DENIED/
                                           UNSUPPORTED
~~~

Có hai loại capability khác nhau:

- **Support capability:** JVM biết thực hiện loại phép đo/quan sát đó không?
- **Runtime enablement:** Tính năng hỗ trợ nhưng hiện có bật thu thập dữ liệu hay không?

**Supported không đồng nghĩa Enabled.** Một API có thể trả giá trị **-1** khi phép đo đã bị tắt hoặc thread không còn sống. Dữ liệu không có không được thay bằng 0 rồi hiển thị trên dashboard như số đo thực.

### 1.1. Năm trạng thái phản hồi

| Trạng thái logic | Ý nghĩa | UI/monitoring nên làm |
| --- | --- | --- |
| **UNSUPPORTED** | JVM/provider không hỗ trợ capability hoặc thao tác được báo không hỗ trợ | Hiển thị tính năng không khả dụng, không thử tiếp vô hạn |
| **DISABLED** | Có hỗ trợ nhưng đang tắt | Báo cần cấu hình/cho phép riêng; không tự bật |
| **AVAILABLE** | Đã đọc được giá trị hợp lệ | Hiển thị giá trị với units, scope và thời điểm đo |
| **UNAVAILABLE** | Hỗ trợ/bật nhưng dữ liệu của thread cụ thể không có, bị chấm dứt, trả -1/null hoặc snapshot đổi | Không biến giá trị thiếu thành 0 |
| **DENIED** | Runtime/policy từ chối quyền | Báo access denied, không tự leo thang quyền |

Các trạng thái này là **application-level model** gợi ý, không phải enum sẵn có của ThreadMXBean. Một ứng dụng production có thể cần phân loại thêm **FAILED**, **STALE**, **PARTIAL** hoặc **TIMEOUT** với exception metadata nội bộ.

### 1.2. Vì sao không gọi thẳng rồi catch UnsupportedOperationException?

Một phản ví dụ:

~~~java
// PHẢN VÍ DỤ: chưa kiểm tra support.
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
long value = bean.getCurrentThreadCpuTime();
System.out.println(value);
~~~

Trong JVM không hỗ trợ, API có thể ném **UnsupportedOperationException**; trong JVM hỗ trợ nhưng bị tắt, có thể trả **-1**. Với thông tin locked synchronizers, việc yêu cầu khi không được hỗ trợ có thể ném exception ngay cả khi ứng dụng chỉ muốn một thread dump bình thường.

Hướng đúng là **capability-gating có chủ đích** và vẫn bắt exception hợp lý vì điều kiện runtime có thể thay đổi giữa lúc kiểm tra và đọc.

---

## 2. Các lớp và API liên quan

### 2.1. ThreadMXBean chuẩn

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();
~~~

**ThreadMXBean** là platform management interface của JVM. Nó cung cấp:

- Counts: **getThreadCount**, **getPeakThreadCount**, **getDaemonThreadCount**, **getTotalStartedThreadCount**.
- IDs: **getAllThreadIds**.
- Info: **getThreadInfo**, **dumpAllThreads**.
- CPU: **getThreadCpuTime**, **getThreadUserTime**, **getCurrentThreadCpuTime**, **getCurrentThreadUserTime**.
- Contention: support/enabled checks và ThreadInfo blocked/waited times.
- Synchronization: support checks cho object monitors/ownable synchronizers.
- Deadlock detection: **findMonitorDeadlockedThreads** và **findDeadlockedThreads**.

**JDK 26 Javadoc:** ThreadMXBean giám sát và quản lý **platform threads**, không hỗ trợ giám sát/quản lý **virtual threads**. Đừng lấy số Threads trong ThreadMXBean rồi kết luận đó là toàn bộ các tác vụ sử dụng virtual threads của ứng dụng.

### 2.2. ThreadInfo

~~~java
import java.lang.management.ThreadInfo;
~~~

**ThreadInfo** là một snapshot về platform thread ở một thời điểm:

- Thread ID, name, state và một số metadata.
- Stack trace nếu được yêu cầu.
- Lock mà thread đang chờ, lock owner, monitors và synchronizers theo capability.
- Số lần blocked/waited.
- Thời gian blocked/waited nếu VM hỗ trợ và contention monitoring đã bật.

Snapshot có thể cũ ngay sau khi trả về, và thread có thể kết thúc trước khi caller xử lý. Nó phục vụ **troubleshooting**, không phải một cơ chế synchronization control.

### 2.3. Phần mở rộng com.sun.management.ThreadMXBean

~~~java
// MẢNH MINH HỌA, yêu cầu module jdk.management.
ThreadMXBean base = ManagementFactory.getThreadMXBean();
if (base instanceof com.sun.management.ThreadMXBean extended) {
    // Tiếp tục hỏi extended.isThreadAllocatedMemorySupported().
}
~~~

Đây là **JDK management extension**, không phải phần phương pháp của interface java.lang.management.ThreadMXBean chuẩn. Extension khả dụng trên nhiều JDK implementations nhưng **không bắt buộc phải có trên mọi Java runtime tương thích chuẩn**. Phải kiểm tra kiểu bằng **instanceof** và khả năng hỗ trợ thực tế trước khi gọi allocated bytes.

**Lưu ý module:** Source Java 17+ có import/type reference tới **com.sun.management.ThreadMXBean** cần module **jdk.management** khi build/run trong môi trường modular hoặc khi cần explicit module resolution.

### 2.4. Vì sao cần hai tầng API?

~~~text
           java.lang.management.ThreadMXBean
                Java SE standard API
                        │
              Có trên runtime chuẩn
                        │
            Capability flags theo VM
                        │
                   instanceof ?
                        │
                        ▼
       com.sun.management.ThreadMXBean
               JDK-specific extension
                        │
         allocated-memory capabilities
~~~

Không cast trực tiếp sang com.sun.management.ThreadMXBean mà không kiểm tra nếu ứng dụng cần chạy trên nhiều implementations. Với runtime không có jdk.management module, một build phụ thuộc compile-time extension sẽ không portable; tách optional plugin/module hoặc sử dụng reflection đã được kiểm soát khi portability là yêu cầu cứng.

---

## 3. CPU time: supported, enabled, value

### 3.1. Có hai loại CPU support

**isThreadCpuTimeSupported()** hỏi khả năng đo CPU của một platform thread bất kỳ theo thread ID. **isCurrentThreadCpuTimeSupported()** hỏi khả năng đo CPU của platform thread hiện đang chạy phép gọi.

~~~java
// MẢNH MINH HỌA.
boolean anySupported = bean.isThreadCpuTimeSupported();
boolean currentSupported = bean.isCurrentThreadCpuTimeSupported();
~~~

Không đồng nhất hai cờ khi thiết kế provider chung. Một implementation có thể hỗ trợ phép đo CPU của current platform thread nhưng không hỗ trợ query các thread khác.

Đối với UI muốn xếp hạng CPU của **nhiều platform threads**, cần kiểm tra **isThreadCpuTimeSupported()**. Đối với instrumentation trong current platform thread, dùng **isCurrentThreadCpuTimeSupported()**.

### 3.2. Cờ enabled

~~~java
// MẢNH MINH HỌA: chỉ hỏi enablement sau support.
if (bean.isCurrentThreadCpuTimeSupported()) {
    if (bean.isThreadCpuTimeEnabled()) {
        long nanos = bean.getCurrentThreadCpuTime();
        if (nanos >= 0) {
            // Giá trị CPU time hợp lệ, đơn vị nanoseconds.
        }
    }
}
~~~

**isThreadCpuTimeEnabled()** có thể ném UnsupportedOperationException khi không có loại CPU measurement nào được hỗ trợ. Vì vậy **kiểm tra support trước khi gọi enabled**.

CPU time có **độ phân giải nanoseconds nhưng không nhất thiết chính xác đến từng nanosecond**. Đây là CPU thực dùng bởi thread, không phải wall-clock elapsed time.

### 3.3. Không dùng -1 làm 0

**getThreadCpuTime(long id)** có thể trả -1 nếu:

- Thread ID đại diện virtual thread.
- Thread không còn sống hoặc không tồn tại.
- CPU time measurement bị disabled.

Nó có thể ném **UnsupportedOperationException** khi JVM không hỗ trợ đo CPU cho các thread khác. ID không hợp lệ (≤0) có thể gây IllegalArgumentException.

Nếu thấy -1:

~~~text
CPU metric = UNAVAILABLE
Không phải:
CPU metric = 0 nanoseconds
~~~

Giá trị 0 có thể là một giá trị đo hợp lệ trong một tình huống; -1 là **sentinel missing**. Trên dashboard cần tách hai ý nghĩa này.

### 3.4. CPU current vs per-thread ID

~~~java
// MẢNH MINH HỌA nếu bean đã được kiểm tra current support/enabled.
long currentNanos = bean.getCurrentThreadCpuTime();
~~~

Trong Java 17-compatible code, có thể dùng **getAllThreadIds()** để lấy các IDs của platform threads đang sống rồi đọc CPU mỗi ID, nhưng cần nhớ danh sách IDs là **snapshot**, thread có thể kết thúc trước lúc đọc:

~~~java
// MẢNH MINH HỌA, chỉ khi isThreadCpuTimeSupported/Enabled đều true.
long[] ids = bean.getAllThreadIds();
for (long id : ids) {
    long cpuNanos = bean.getThreadCpuTime(id);
    if (cpuNanos >= 0) {
        // Giá trị hợp lệ tại thời điểm đo.
    } else {
        // Thread biến mất, disabled hoặc không có dữ liệu.
    }
}
~~~

Đối với per-thread CPU rates, thường đo hai lần và tính **delta CPU nanos / delta elapsed nanos**. Dùng cùng thread ID và xác định thread còn sống; thread IDs có thể được tái sử dụng sau khi thread kết thúc. Cần theo dõi lifecycle/identity khi thu mẫu liên tục.

### 3.5. Không tự bật CPU time trên production

~~~java
// MẢNH MINH HỌA quyền admin, KHÔNG chạy mặc định khi polling:
if (bean.isThreadCpuTimeSupported()
        || bean.isCurrentThreadCpuTimeSupported()) {
    bean.setThreadCpuTimeEnabled(true);
}
~~~

**setThreadCpuTimeEnabled** thay đổi cài đặt theo JVM. Một số JVMs có overhead đáng kể khi bật đo CPU. Việc một collector “muốn số liệu” không cho phép nó tự đổi global monitoring policy.

Nếu vận hành yêu cầu bật, cần:

- Cấu hình/authorization rõ.
- Baseline performance trước/sau.
- Audit thay đổi.
- Có kế hoạch restore prior state khi component sở hữu quyền thay đổi.
- Không vô tình tắt capability mà một collector khác đang dùng.
- Xử lý UnsupportedOperationException và quyền bị từ chối.

Code demo chính **không gọi setter bật/tắt**.

---

## 4. Contention monitoring: thời gian BLOCKED/WAITED

### 4.1. Hai capability checks

~~~java
// MẢNH MINH HỌA.
boolean supported = bean.isThreadContentionMonitoringSupported();
boolean enabled = supported
        && bean.isThreadContentionMonitoringEnabled();
~~~

Khi **supported=false**, không gọi phương thức enabled với giả định sẽ trả false; phương thức này có thể ném **UnsupportedOperationException**.

Khi **supported=true nhưng enabled=false**, JVM không thu thập elapsed time theo API contention. Mặc định tính năng này có thể đang **disabled**. Đó là một trạng thái **DISABLED**, không phải lỗi của ứng dụng và không có nghĩa không xảy ra contention.

### 4.2. ThreadInfo.getBlockedTime và getWaitedTime

**getBlockedTime()**: thời gian xấp xỉ (milliseconds) thread ở trạng thái BLOCKED, chờ lấy/re-enter một object monitor, kể từ khi contention monitoring được bật.

**getWaitedTime()**: thời gian xấp xỉ (milliseconds) thread ở WAITING/TIMED_WAITING, chờ notification/parking theo contract ThreadInfo, kể từ khi monitoring được bật.

~~~java
// MẢNH MINH HỌA với ThreadInfo info != null.
long blockedMs = info.getBlockedTime();
long waitedMs = info.getWaitedTime();

if (blockedMs < 0 || waitedMs < 0) {
    // Data unavailable hoặc contention monitoring disabled.
}
~~~

Nếu contention monitoring bị disabled, cả hai có thể trả **-1**. Một số VMs có thể ném UnsupportedOperationException cho phép đo không được hỗ trợ. Đừng tính tỷ lệ/chênh lệch dựa trên -1 như một số thời gian đo.

### 4.3. Count khác time

**getBlockedCount()** và **getWaitedCount()** ghi nhận số lần, khác với **getBlockedTime()/getWaitedTime()** đo thời gian. Hai loại chỉ số có đơn vị khác nhau:

| Thuộc tính | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| blockedCount | events | Số lần thread bị blocked vì monitor |
| waitedCount | events | Số lần thread waited |
| blockedTime | milliseconds | Tổng thời gian blocked có thu thập |
| waitedTime | milliseconds | Tổng thời gian waited có thu thập |

Nếu một thread blocked nhiều lần rất ngắn, blockedCount có thể cao nhưng blockedTime thấp. Ngược lại, một lần blocked lâu có thể khiến time cao nhưng count thấp.

### 4.4. Khi bật contention monitoring, điểm bắt đầu đo có thể đổi

**setThreadContentionMonitoringEnabled(true)** thay đổi cài đặt cho JVM; dữ liệu accumulated times chỉ được thu thập theo khoảng thời gian tính năng được bật. Nếu tắt rồi bật lại, các statistics thời gian có thể reset.

Vì vậy không gộp bừa blocked/waited times qua các giai đoạn enablement khác nhau và gọi chúng là lifetime totals. Khi làm dashboard, có thể gắn metric epoch hoặc quality flag.

### 4.5. Không tự kết luận có deadlock khi thấy BLOCKED/WAITING

Thread BLOCKED là một tín hiệu về lock acquisition; WAITING có thể là trạng thái bình thường khi consumer chờ item, worker chờ job hoặc thread chờ condition. Những trạng thái này **không đủ để khẳng định deadlock**.

Deadlock detection là API riêng, có giới hạn và chi phí; hãy kiểm tra khả năng hỗ trợ và phân biệt absence of detection với proof of absence.

---

## 5. Object monitors, ownable synchronizers và thread dump

### 5.1. Hai loại lock khác nhau

Object monitor thường liên quan **synchronized**. Ownable synchronizer thường liên quan các cơ chế như **ReentrantLock** dựa trên java.util.concurrent.locks.

**ThreadMXBean** có hai cờ:

~~~java
boolean monitors = bean.isObjectMonitorUsageSupported();
boolean synchronizers = bean.isSynchronizerUsageSupported();
~~~

Chúng trả lời VM có thể cung cấp thông tin **held object monitors** và **held ownable synchronizers** hay không. Không nhầm các cờ này với **isThreadContentionMonitoringSupported()**; khả năng đo thời gian contention khác khả năng liệt kê lock objects.

### 5.2. Trước khi yêu cầu locked monitors/synchronizers

~~~java
// MẢNH MINH HỌA, java.management, Java 17+.
boolean includeMonitors = bean.isObjectMonitorUsageSupported();
boolean includeSynchronizers = bean.isSynchronizerUsageSupported();

long[] ids = bean.getAllThreadIds();
if (ids.length > 0) {
    ThreadInfo[] information = bean.getThreadInfo(
            new long[]{ids[0]},
            includeMonitors,
            includeSynchronizers,
            0  // Không lấy stack frames, chỉ kiểm tra metadata.
    );

    if (information.length > 0 && information[0] != null) {
        // Có thông tin thread platform còn sống.
    }
}
~~~

Nếu **lockedMonitors=true** mà JVM không hỗ trợ object-monitor usage, hoặc **lockedSynchronizers=true** mà không hỗ trợ ownable synchronizers, method có thể ném UnsupportedOperationException.

**Cách tốt:** Có thể degrade riêng từng tính năng: hỗ trợ monitor nhưng không synchronizer thì chỉ yêu cầu monitor. Nếu chỉ cần state/stack, gọi với hai flags **false** thay vì ép lấy lock details chưa được hỗ trợ.

### 5.3. Stack trace depth là một resource budget

Một thread dump lớn có thể chứa nhiều stack frames, locks, method/class names, framework paths và business logic context. **dumpAllThreads** có thể tốn chi phí và lộ thông tin nội bộ, đặc biệt trên process có hàng trăm/hàng nghìn platform threads.

Dùng **maxDepth** hữu hạn trên APIs Java 10+ khi phù hợp:

~~~java
// MẢNH MINH HỌA.
int maxDepth = 8;
ThreadInfo[] infos = bean.dumpAllThreads(
        bean.isObjectMonitorUsageSupported(),
        bean.isSynchronizerUsageSupported(),
        maxDepth);
~~~

**Không gọi dumpAllThreads liên tục ở tần suất cao** chỉ để tính số lượng threads. Muốn chỉ số tổng, dùng **getThreadCount()** thay vì lập toàn bộ stack dumps.

Một implementation có thể không hỗ trợ một overload mới và ném UnsupportedOperationException theo default method contract; code product vẫn cần xử lý failure dù đã kiểm tra flags.

### 5.4. Thread ID snapshot và race

**getAllThreadIds()** trả IDs các platform threads đang sống khi JVM thu thập danh sách. Thread có thể kết thúc ngay sau đó. Khi gọi getThreadInfo:

- Một phần tử ThreadInfo có thể **null**.
- Không dereference ngay nếu chưa check.
- CPU/allocation của thread đã kết thúc có thể là **-1**.
- Không dùng một snapshot quá cũ để ra quyết định synchronization.
- Không gán nghĩa cố định cho thread ID qua nhiều lifecycle; ID có thể được tái sử dụng.

Do đó, **getThreadInfo() trả null không đồng nghĩa nền tảng không hỗ trợ ThreadMXBean**. Nó thường chỉ là dữ liệu của thread không còn khả dụng tại thời điểm đọc.

### 5.5. Deadlock detection

~~~java
// MẢNH MINH HỌA.
long[] monitorDeadlocks = bean.findMonitorDeadlockedThreads();

if (bean.isSynchronizerUsageSupported()) {
    long[] broaderDeadlocks = bean.findDeadlockedThreads();
}
~~~

**findMonitorDeadlockedThreads()** tìm chu trình deadlock giữa các platform threads trên object monitors. **findDeadlockedThreads()** có phạm vi gồm object monitors và ownable synchronizers; nếu JVM không hỗ trợ ownable synchronizer monitoring có thể ném UnsupportedOperationException.

- Kết quả **null** nghĩa là không tìm được chu trình deadlock trong phạm vi phép dò tại thời điểm đó.
- Không bảo đảm phát hiện mọi loại logical deadlock, network stall hoặc starvation.
- Các deadlocks liên quan **virtual threads** không được những phương thức này bảo đảm phát hiện theo JDK 26.
- Đây là thao tác chẩn đoán có thể tốn kém; không dùng polling cực nhanh.

**Deadlock detection không phải một thuật toán tự động giải khóa**. Tránh viết code production cố gắng stop/interrupt ngẫu nhiên các threads theo kết quả dò.

---

## 6. Per-thread allocated bytes: extension cần kiểm tra riêng

### 6.1. Không nằm trong interface Java SE chuẩn

**com.sun.management.ThreadMXBean** là một phần mở rộng hỗ trợ đo lượng heap bytes cấp phát theo thread trong những JVM implementations cung cấp nó. Đừng nhầm với **MemoryMXBean.getHeapMemoryUsage()** (sử dụng heap toàn JVM), cũng đừng hiểu allocated bytes là dung lượng object hiện vẫn còn sống sau GC.

Allocated bytes là **lượng đã cấp phát tích lũy**, không phải live heap size.

### 6.2. Chuỗi kiểm tra đúng

~~~java
// MẢNH MINH HỌA. Build/run cần module jdk.management.
ThreadMXBean bean = ManagementFactory.getThreadMXBean();

if (bean instanceof com.sun.management.ThreadMXBean ext) {
    if (ext.isThreadAllocatedMemorySupported()) {
        if (ext.isThreadAllocatedMemoryEnabled()) {
            long bytes = ext.getCurrentThreadAllocatedBytes();
            if (bytes >= 0) {
                // Data hợp lệ, đơn vị bytes.
            }
        }
    }
}
~~~

Thứ tự:

1. Extension type tồn tại không?
2. **isThreadAllocatedMemorySupported()** true không?
3. **isThreadAllocatedMemoryEnabled()** true không?
4. Đọc dữ liệu.
5. Xử lý **-1** và UnsupportedOperationException vẫn có thể phát sinh.

**Không gọi isThreadAllocatedMemoryEnabled() khi support=false**, vì nó có thể ném UnsupportedOperationException.

### 6.3. Phạm vi per-thread và sentinel

**getThreadAllocatedBytes(long id)** có thể trả -1 cho thread đã dừng, thread không tồn tại, virtual thread, hoặc capability bị disabled. **getCurrentThreadAllocatedBytes()** đo current thread, cho kết quả xấp xỉ khi được hỗ trợ/bật.

Một số methods của extension dùng default implementations và có thể ném UnsupportedOperationException. Vì vậy capability flags vẫn là bước đầu, **try/catch ở ranh giới đọc vẫn cần có**.

### 6.4. Chênh lệch allocated bytes

Nếu hai lần đo một platform thread:

~~~text
T0: allocated = 2500000 bytes
T1: allocated = 3100000 bytes

delta = 600000 bytes
~~~

Đây là một phép đo **cấp phát**, không có nghĩa heap usage tăng 600000 bytes. Nhiều objects có thể đã bị GC sau đó.

Để tính tốc độ cấp phát theo thread:

- Hai mẫu phải cùng thread identity/lifecycle.
- Không tính khi một giá trị là -1.
- Có khoảng thời gian elapsed chính xác.
- Xử lý counters reset và thread termination.
- Gắn units bytes/second.
- Đừng yêu cầu allocation details nếu security/overhead không cho phép.

---

## 7. Virtual threads: giới hạn đặc biệt trên Java 21+

### 7.1. ThreadMXBean chủ yếu nói về platform threads

Java 21 đưa virtual threads vào bản phát hành chính thức. Theo JDK 26, **ThreadMXBean không hỗ trợ monitoring/management virtual threads**; các methods:

- **getThreadCount** và **getAllThreadIds** phản ánh **platform threads**, không đếm đầy đủ virtual threads.
- **getThreadCpuTime(long id)** không trả CPU time của một virtual thread; có thể trả -1.
- **getThreadInfo(long id)** không đưa thông tin virtual thread.
- **findDeadlockedThreads** không phát hiện các deadlocks có virtual threads theo phạm vi mô tả.

Vì vậy, một server xử lý hàng trăm nghìn tasks bằng virtual threads có thể có ít platform threads; không được xem ThreadMXBean.getThreadCount() là tổng số application tasks.

### 7.2. Monitoring virtual threads nên theo use case

Với virtual-thread-heavy applications, cân nhắc:

- **Java Flight Recorder (JFR)** để phân tích event/scheduling/performance phù hợp runtime.
- Instrumentation ở tầng ứng dụng: số request/task đang xử lý, thời gian hoàn tất, queue depth và lỗi.
- JVM diagnostics/tools hiện hành hỗ trợ virtual threads theo phiên bản JDK.
- Bounded tracing/metrics, không tạo một MBean hoặc metric per virtual thread.
- Test riêng trên JDK 21+ theo khả năng thực sự của monitoring tooling.

**Đừng nói một JVM không có contention chỉ vì platform ThreadMXBean không thấy virtual-thread contention.** Nó không đo các đối tượng đó theo contract.

### 7.3. Tính tương thích Java 17+

Ví dụ runnable trong bài **không dùng virtual threads**, vì mục tiêu là bảo đảm source chạy được trên Java 17. Phần nội dung virtual threads là một lưu ý runtime hiện đại; nếu muốn code tạo virtual threads, cần target JDK21+ riêng và bộ kiểm thử khác.

---

## 8. Mẫu kiến trúc application-level: capability trước dữ liệu

Thay vì bắt UI tự gọi trực tiếp MXBean methods và tự đoán exception, tạo một tầng **ThreadDiagnosticService**:

~~~text
         Metrics UI / Diagnostics API
                      │
                      ▼
              DiagnosticService
                      │
                      ▼
               Capability layer
         supported? enabled? extension?
                      │
                      ▼
             Guarded metric probes
         CPU / contention / monitors /
               synchronizers / allocation
                      │
                      ▼
            Result{status, value,
                   unit, timestamp}
                      │
                      ▼
            Sanitize + present
~~~

Phần này không phải một library bắt buộc. Nó giúp:

- Phân biệt rõ trạng thái **UNSUPPORTED** và **DISABLED**.
- Không thực hiện methods không hỗ trợ.
- Không in -1 như một số đo.
- Giới hạn CPU/GC overhead, stack depth và thread sample size.
- Tránh UI phải có quyền thay đổi JVM monitoring flags.
- Thêm tests cho unsupported runtimes mà không cần thật sự thay JDK.

### 8.1. Một abstraction nhỏ cho dữ liệu số

~~~java
// MẢNH MINH HỌA, không phải file runnable độc lập.
interface MetricProbe {
    boolean supported();
    boolean enabled();
    long read();
}
~~~

Tầng business chỉ cần hiểu thứ tự:

~~~text
if !supported → UNSUPPORTED
else if !enabled → DISABLED
else if read() == -1 → UNAVAILABLE
else → AVAILABLE(value)
~~~

Hai ngoại lệ quan trọng:

1. **UnsupportedOperationException** có thể phát sinh giữa support check và read, ví dụ provider khác hoặc default method không hỗ trợ. Bắt và báo UNSUPPORTED thay vì crash.
2. **SecurityException** có thể biểu thị truy cập bị từ chối. Bắt riêng, trả DENIED; không tự xin quyền cao hơn.

Một production API có thể thêm mã lỗi transport/IO và raw cause lưu trong internal logs đã redacted.

### 8.2. Vì sao cần fake probes?

Không thể yêu cầu một máy CI luôn có CPU monitoring disabled hoặc JVM không hỗ trợ locks. Nếu unit test trực tiếp phụ thuộc capability flags của OpenJDK developer laptop, tests sẽ không portable.

Fake probe cho phép điều khiển:

- **supported=false** và xác minh **enabled/read không bị gọi**.
- supported=true, enabled=false và xác minh **read không bị gọi**.
- supported=true, enabled=true, read>=0 và status AVAILABLE.
- read=-1 và status UNAVAILABLE.
- read ném SecurityException và status DENIED.
- read ném UnsupportedOperationException sau khi supported=true và status UNSUPPORTED.

Đây là những trường hợp cần thiết để chứng minh code **không yêu cầu dữ liệu trước khi hỏi khả năng hỗ trợ**.

---

## 9. Chương trình Java 17+ hoàn chỉnh đã kiểm chứng

**Tên file duy nhất:** ThreadCapabilityFirstDemo.java

Ví dụ gồm hai phần:

**Phần deterministic:** Fake probes mô phỏng unsupported/disabled/value/-1/security/capability-change. Lấy chính số lần gọi enabled/read để kiểm tra không có API call sai thứ tự.

**Phần live:** Lấy platform ThreadMXBean thực. Đọc CPU, contention, monitors/synchronizers và optional allocated bytes **sau support/enabled checks**. Kết quả thực tùy JVM nên chương trình chỉ in **cờ kiểm tra trạng thái thuộc tập hợp enum hợp lệ**, không hardcode một capability được hỗ trợ hay số byte/CPU cụ thể.

**Chính sách an toàn:** Code **không gọi** setThreadCpuTimeEnabled, setThreadContentionMonitoringEnabled hay setThreadAllocatedMemoryEnabled; không in stack trace, thread names, allocation bytes hoặc thông tin process nhạy cảm.

### 9.1. Source đầy đủ

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.EnumSet;

public final class ThreadCapabilityFirstDemo {
    enum Result { UNSUPPORTED, DISABLED, AVAILABLE, UNAVAILABLE, DENIED }

    interface MetricProbe {
        boolean supported();
        boolean enabled();
        long read();
    }

    static final class Fake implements MetricProbe {
        final boolean support;
        final boolean enable;
        final long value;
        final RuntimeException failOnRead;
        int enableCalls;
        int readCalls;

        Fake(boolean support, boolean enable, long value,
             RuntimeException failOnRead) {
            this.support = support;
            this.enable = enable;
            this.value = value;
            this.failOnRead = failOnRead;
        }

        public boolean supported() { return support; }

        public boolean enabled() {
            enableCalls++;
            return enable;
        }

        public long read() {
            readCalls++;
            if (failOnRead != null) throw failOnRead;
            return value;
        }
    }

    static Result guardedRead(MetricProbe probe) {
        try {
            if (!probe.supported()) return Result.UNSUPPORTED;
            if (!probe.enabled()) return Result.DISABLED;
            long value = probe.read();
            return value >= 0 ? Result.AVAILABLE : Result.UNAVAILABLE;
        } catch (UnsupportedOperationException ex) {
            return Result.UNSUPPORTED;
        } catch (SecurityException ex) {
            return Result.DENIED;
        }
    }

    static Result currentCpuStatus(ThreadMXBean bean) {
        return guardedRead(new MetricProbe() {
            public boolean supported() {
                return bean.isCurrentThreadCpuTimeSupported();
            }
            public boolean enabled() {
                return bean.isThreadCpuTimeEnabled();
            }
            public long read() {
                // The main thread in this program is a platform thread.
                return bean.getCurrentThreadCpuTime();
            }
        });
    }

    static Result contentionStatus(ThreadMXBean bean) {
        return guardedRead(new MetricProbe() {
            public boolean supported() {
                return bean.isThreadContentionMonitoringSupported();
            }
            public boolean enabled() {
                return bean.isThreadContentionMonitoringEnabled();
            }
            public long read() {
                long[] ids = bean.getAllThreadIds();
                if (ids.length == 0) return -1;
                // A platform thread may finish between discovery and read.
                ThreadInfo info = bean.getThreadInfo(ids[0], 0);
                return info == null ? -1 : info.getBlockedTime();
            }
        });
    }

    static Result allocatedStatus(ThreadMXBean bean) {
        if (!(bean instanceof com.sun.management.ThreadMXBean ext)) {
            return Result.UNSUPPORTED;
        }
        return guardedRead(new MetricProbe() {
            public boolean supported() {
                return ext.isThreadAllocatedMemorySupported();
            }
            public boolean enabled() {
                return ext.isThreadAllocatedMemoryEnabled();
            }
            public long read() {
                // Extension method; safe only after supported/enabled gates.
                return ext.getCurrentThreadAllocatedBytes();
            }
        });
    }

    static Result monitorStatus(ThreadMXBean bean) {
        if (!bean.isObjectMonitorUsageSupported()) return Result.UNSUPPORTED;
        try {
            long[] ids = bean.getAllThreadIds();
            if (ids.length == 0) return Result.UNAVAILABLE;
            ThreadInfo[] info = bean.getThreadInfo(new long[] {ids[0]},
                    true, false, 0);
            return info.length > 0 && info[0] != null
                    ? Result.AVAILABLE : Result.UNAVAILABLE;
        } catch (UnsupportedOperationException ex) {
            return Result.UNSUPPORTED;
        } catch (SecurityException ex) {
            return Result.DENIED;
        }
    }

    static Result synchronizerStatus(ThreadMXBean bean) {
        if (!bean.isSynchronizerUsageSupported()) return Result.UNSUPPORTED;
        try {
            long[] ids = bean.getAllThreadIds();
            if (ids.length == 0) return Result.UNAVAILABLE;
            ThreadInfo[] info = bean.getThreadInfo(new long[] {ids[0]},
                    false, true, 0);
            return info.length > 0 && info[0] != null
                    ? Result.AVAILABLE : Result.UNAVAILABLE;
        } catch (UnsupportedOperationException ex) {
            return Result.UNSUPPORTED;
        } catch (SecurityException ex) {
            return Result.DENIED;
        }
    }

    static boolean known(Result value) {
        return EnumSet.allOf(Result.class).contains(value);
    }

    public static void main(String[] args) {
        Fake unsupported = new Fake(false, true, 5L, null);
        Fake disabled = new Fake(true, false, 5L, null);
        Fake supported = new Fake(true, true, 42L, null);
        Fake negative = new Fake(true, true, -1L, null);
        Fake denied = new Fake(true, true, 0L,
                new SecurityException("access denied"));
        Fake changed = new Fake(true, true, 0L,
                new UnsupportedOperationException("changed"));

        System.out.println("unsupported=" + guardedRead(unsupported));
        System.out.println("unsupportedEnabledNotCalled="
                + (unsupported.enableCalls == 0));
        System.out.println("unsupportedReadNotCalled="
                + (unsupported.readCalls == 0));
        System.out.println("disabled=" + guardedRead(disabled));
        System.out.println("disabledReadNotCalled=" + (disabled.readCalls == 0));
        System.out.println("available=" + guardedRead(supported));
        System.out.println("unavailableSentinel=" + guardedRead(negative));
        System.out.println("denied=" + guardedRead(denied));
        System.out.println("capabilityChangedMidRead=" + guardedRead(changed));

        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        Result cpu = currentCpuStatus(bean);
        Result contention = contentionStatus(bean);
        Result monitors = monitorStatus(bean);
        Result synchronizers = synchronizerStatus(bean);
        Result allocated = allocatedStatus(bean);
        System.out.println("liveCpuStatusRecognized=" + known(cpu));
        System.out.println("liveContentionStatusRecognized=" + known(contention));
        System.out.println("liveMonitorStatusRecognized=" + known(monitors));
        System.out.println("liveSynchronizerStatusRecognized="
                + known(synchronizers));
        System.out.println("liveAllocationStatusRecognized=" + known(allocated));
        System.out.println("globalMonitoringFlagsChanged=false");
    }
}
~~~

### 9.2. Biên dịch và chạy

Lưu source thành **ThreadCapabilityFirstDemo.java** trong một thư mục trống. Sử dụng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 --release 17 --add-modules jdk.management ThreadCapabilityFirstDemo.java
java --add-modules jdk.management ThreadCapabilityFirstDemo
~~~

**jdk.management** là module JDK chứa extension com.sun.management.ThreadMXBean; khi runtime thiếu module đó, ví dụ nguyên bản không phù hợp. Với một application cần portable qua nhiều Java SE distributions, hãy tách extension khỏi phần standard API để hỗ trợ graceful degradation.

Chương trình chỉ đọc thông tin JVM đang chạy. Không yêu cầu database, network, HTTP server, file monitoring configuration hay JMX remote connector.

### 9.3. Stdout chính xác đã kiểm chứng

~~~text
unsupported=UNSUPPORTED
unsupportedEnabledNotCalled=true
unsupportedReadNotCalled=true
disabled=DISABLED
disabledReadNotCalled=true
available=AVAILABLE
unavailableSentinel=UNAVAILABLE
denied=DENIED
capabilityChangedMidRead=UNSUPPORTED
liveCpuStatusRecognized=true
liveContentionStatusRecognized=true
liveMonitorStatusRecognized=true
liveSynchronizerStatusRecognized=true
liveAllocationStatusRecognized=true
globalMonitoringFlagsChanged=false
~~~

**Đã kiểm thử thực tế:** Source biên dịch bằng **javac 24.0.2 --release 17**, chạy trên OpenJDK 24.0.2 và so khớp **chính xác cả 15 dòng stdout**. Temporary Java files và compiled classes của lượt kiểm thử được dọn sau khi kết thúc.

### 9.4. Giải thích phần deterministic

**unsupported=UNSUPPORTED**: Fake báo supported=false. Phương thức guardedRead dừng ngay; hai dòng tiếp theo xác nhận **enabled() và read() đều chưa từng bị gọi**.

**disabled=DISABLED**: Fake báo supported=true nhưng enabled=false. Dòng disabledReadNotCalled=true chứng minh không cố lấy dữ liệu khi đang tắt.

**available=AVAILABLE**: Fake trả 42 (một giá trị số hợp lệ). Chương trình chỉ in status, không tiết lộ dữ liệu sample nào.

**unavailableSentinel=UNAVAILABLE**: Fake trả -1, status không phải AVAILABLE và không biến -1 thành 0.

**denied=DENIED**: Fake ném SecurityException khi đọc. Chương trình trả trạng thái truy cập bị từ chối, không tự cấp quyền.

**capabilityChangedMidRead=UNSUPPORTED**: Fake có support=true và enabled=true, nhưng read ném UnsupportedOperationException. Đây là một trường hợp mô phỏng sự khác biệt implementation/tính khả dụng giữa lúc kiểm tra và sử dụng. Boundary vẫn xử lý được.

### 9.5. Ý nghĩa phần live

Các dòng:

~~~text
liveCpuStatusRecognized=true
liveContentionStatusRecognized=true
liveMonitorStatusRecognized=true
liveSynchronizerStatusRecognized=true
liveAllocationStatusRecognized=true
globalMonitoringFlagsChanged=false
~~~

không có nghĩa **mọi capability đều AVAILABLE**. Chúng chỉ kiểm tra rằng mỗi thăm dò đã trả **một trạng thái hợp lệ trong enum**, bất kể VM hỗ trợ hay đang tắt. Code không in giá trị CPU/allocated bytes thật, giúp giữ output deterministic và không lộ chi tiết runtime.

Đó là chiến lược kiểm thử thích hợp cho **capability-dependent code**:

- Unit tests kiểm thử đầy đủ branches bằng fake probes.
- Integration smoke tests kiểm tra API thật không crash và status hợp lệ.
- Không bắt CI phải có một JVM luôn bật contention monitoring.
- Không thay đổi monitoring flags để ép test có một dữ liệu cụ thể.

### 9.6. Phạm vi của code demo

- Chỉ kiểm tra current CPU trên **main platform thread**, không đo CPU của virtual threads.
- ContentionStatus chọn một ID từ snapshot các platform threads; thread có thể kết thúc và trả UNAVAILABLE.
- MonitorStatus chỉ yêu cầu locked monitors khi isObjectMonitorUsageSupported=true.
- SynchronizerStatus chỉ yêu cầu locked synchronizers khi isSynchronizerUsageSupported=true.
- AllocatedStatus chỉ chạy nếu implementation hỗ trợ extension type và measurement supported/enabled.
- Không bật/tắt CPU/contended/allocated monitoring.
- Không lập full thread dump hoặc tìm deadlocks.
- Không in names/stack traces/lock owner IDs; tránh lộ thông tin vận hành.
- Không thực hiện performance benchmark để khẳng định monitoring overhead bằng 0.
- Các trạng thái là application-level abstraction, không phải enums được định nghĩa trong JDK.

---

## 10. Thiết kế UI/metric API không mất ngữ nghĩa

### 10.1. Dữ liệu nên có status và unit

Một response nội bộ có thể mang:

~~~text
feature=thread.cpu.current
status=AVAILABLE
value=1250000
unit=nanoseconds
observedAtEpochMillis=...
scope=platform-thread

feature=thread.contention.blocked
status=DISABLED
value=<absent>
unit=milliseconds

feature=thread.allocation.bytes
status=UNSUPPORTED
value=<absent>
unit=bytes
~~~

Đây là **format minh họa**, không phải output chương trình. Không trả value=0 thay cho absent; có thể dùng typed Optional, sealed result hoặc JSON null kèm status trong một API khác.

### 10.2. Không ép nhiều trạng thái thành một boolean

Một UI hiển thị “CPU monitoring unavailable” có thể che mất:

- VM thật sự không hỗ trợ.
- VM hỗ trợ nhưng đang disabled.
- Một thread đã kết thúc.
- Caller không có quyền.
- Capability đổi giữa check và read.
- Extension không được đóng gói vào runtime.

Các trường hợp này có hướng khắc phục khác nhau. Chỉ **DISABLED** có thể gợi ý cân nhắc bật monitoring theo policy; **DENIED** đòi cấp quyền đúng quy trình; **UNAVAILABLE** có thể chỉ cần lấy sample mới; **UNSUPPORTED** có thể yêu cầu dùng công cụ khác.

### 10.3. Zero vs missing vs stale

| Giá trị | Diễn giải đúng |
| --- | --- |
| 0 | Có thể là số đo bằng 0 nếu API trả hợp lệ |
| -1 | Sentinel của dữ liệu không có, thường không được sử dụng tính toán |
| null ThreadInfo | Thread có thể đã kết thúc, không có snapshot |
| UnsupportedOperationException | Operation/capability không được provider hỗ trợ |
| SecurityException | Truy cập bị cấm theo runtime/policy |
| Snapshot cũ | Có thể không phản ánh thread hiện tại |
| NaN trong công thức rate | Có thể thiếu mẫu số/đo dữ liệu không hợp lệ |

Đặc biệt, đừng lấy -1 CPU time rồi tính một **negative CPU utilization** và tạo cảnh báo sai.

### 10.4. Metric collection có overhead

Một công cụ đo 1000 threads mỗi vài milliseconds có thể gây chi phí CPU, allocations và overhead. CPU/contended monitoring khi bật cũng có thể ảnh hưởng runtime.

Nên xác định:

- Sampling frequency phù hợp SLA.
- Max threads được thu theo ưu tiên.
- Max stack depth.
- Khi nào dùng **getThreadCount** thay full dump.
- Budget cho JMX remote calls.
- Retry có bounded backoff.
- Rate limit cho yêu cầu thu dữ liệu từ người dùng.
- Giới hạn kích thước response và retention.
- Không log stack trace/lock identity ở mức công khai.

---

## 11. Xử lý quyền và thay đổi cờ monitoring

### 11.1. Getter là đọc, setter là thay đổi JVM behavior

Các methods **setThreadCpuTimeEnabled** và **setThreadContentionMonitoringEnabled** có side effects ảnh hưởng cơ chế theo dõi của JVM. Cơ chế allocated-memory extension cũng có setter enablement.

Một monitoring dashboard **readonly** nên mặc định chỉ đọc và báo status. Nếu người vận hành muốn bật tính năng:

1. Kiểm tra supported.
2. Xem trạng thái enabled trước đó.
3. Đánh giá overhead và mục đích đo.
4. Yêu cầu đúng quyền admin/approval.
5. Thay đổi qua một management operation có audit.
6. Kiểm tra trạng thái sau khi đổi.
7. Có kế hoạch revert khi quyền sở hữu thay đổi.
8. Không tự tắt measurement mà service/tool khác đang dùng.

### 11.2. Không coi UnsupportedOperationException là SecurityException

Unsupported nghĩa là VM/operation không có khả năng theo contract; Denied nghĩa là policy không cho phép truy cập. Khi triển khai, phải phân loại khác nhau; không tự bật quyền cao hơn khi gặp unsupported.

### 11.3. Thread dumps là dữ liệu nhạy cảm

Stack traces có thể chứa:

- Tên package/class/method của ứng dụng.
- Business flow và cấu trúc framework.
- Tên thread do application đặt, đôi khi chứa user/job IDs.
- Lock identities và nội dung chẩn đoán hạ tầng.

Một JMX endpoint để người lạ lấy thread dumps có thể làm lộ thông tin hệ thống. Remote JMX cần **TLS, authentication, authorization, network isolation** và audit. Không bật public JMX port hoặc cấp readwrite rộng chỉ vì muốn xem CPU usage.

### 11.4. Không sử dụng capability checks làm ACL

**isThreadCpuTimeSupported()** chỉ trả lời JVM có khả năng đo không; nó không cho biết principal nào được quyền xem CPU của thread hay được bật monitoring. Một application cần role-specific authorization ở JMX connector/gateway, và vẫn phải xử lý dữ liệu nhạy cảm trong results.

### 11.5. Không dump toàn hệ thống chỉ để hiển thị một chỉ số

Nếu UI chỉ cần thread count, dùng **getThreadCount**. Nếu UI cần deadlock detection, dùng API deadlock phù hợp và giới hạn tần suất. Nếu UI cần top CPU threads, cân nhắc sample có giới hạn, đúng support/enabled và không quét vô hạn.

**Đúng API cho đúng câu hỏi** giúp giảm chi phí và nguy cơ lộ dữ liệu.

---

## 12. Unit và integration testing

### 12.1. Test capability-gating

| Scenario | Fake inputs | Expected |
| --- | --- | --- |
| JVM/provider không hỗ trợ | supported=false | UNSUPPORTED |
| Không hỗ trợ → không được hỏi enabled | supported=false | enabledCalls=0 |
| Không hỗ trợ → không được đọc | supported=false | readCalls=0 |
| Hỗ trợ nhưng tắt | supported=true, enabled=false | DISABLED |
| Tắt → không được đọc | enabled=false | readCalls=0 |
| Hỗ trợ/bật, value=42 | read=42 | AVAILABLE |
| Hỗ trợ/bật, value=-1 | read=-1 | UNAVAILABLE |
| Access denied | read ném SecurityException | DENIED |
| Capability thay đổi | read ném UnsupportedOperationException | UNSUPPORTED |
| Actual JDK | capability flags tùy runtime | Status hợp lệ, không crash |
| Unchanged monitoring flags | không gọi setters | Không sửa config toàn JVM |

Các trường hợp deterministic ở bảng được minh họa bởi file runnable; những tests đo tác dụng global flag chưa được thực hiện bằng cách đọc/chỉnh flags trên máy production.

### 12.2. Test CPU time

- Current thread supported=true, enabled=true, đọc có thể >=0.
- Current thread supported=false: không gọi isEnabled/getCurrentThreadCpuTime.
- Any-thread support=false: không gọi getThreadCpuTime(id) khi chỉ có current support.
- Đưa thread ID đã terminate: kết quả có thể -1, không crash.
- Thread ID <=0: IllegalArgumentException khi trực tiếp gọi API; business layer nên validate trước.
- Hai samples hợp lệ cùng thread: delta không âm nếu không có reset/lifecycle anomaly.
- CPU nanos không được hiểu là wall elapsed nanos.
- Không hardcode con số CPU của máy CI.

### 12.3. Test contention

- Supported=false: không gọi enabled.
- Supported=true, enabled=false: không diễn giải blockedTime=-1 thành 0.
- Supported=true, enabled=true: giá trị >=0 hoặc unavailable theo runtime.
- Enable/disable/reenable: kiểm tra metric epoch/reset khi có quyền trong sandbox.
- Test blockedCount khác blockedTime.
- Test WAITING không tự bị coi là deadlock.
- Không bật contention chỉ để ép một unit test thành công.

### 12.4. Test monitors và synchronizers

| Capabilities | Lời gọi phù hợp |
| --- | --- |
| monitors=false, synchronizers=false | getThreadInfo(ids,false,false,depth) |
| monitors=true, synchronizers=false | getThreadInfo(ids,true,false,depth) |
| monitors=false, synchronizers=true | getThreadInfo(ids,false,true,depth) |
| monitors=true, synchronizers=true | getThreadInfo(ids,true,true,depth) |

Test negative path khi gọi flag=true mà support=false **trong môi trường fake hoặc JVM sandbox**; không cần bắt một runtime cụ thể phải thiếu capability.

### 12.5. Test allocated-memory extension

- JVM không có com.sun.management.ThreadMXBean instance: UNSUPPORTED.
- Instance có nhưng isThreadAllocatedMemorySupported=false: UNSUPPORTED.
- Supported=true nhưng enabled=false: DISABLED.
- Supported/enabled và bytes>=0: AVAILABLE.
- Return -1: UNAVAILABLE.
- Method ném UnsupportedOperationException: UNSUPPORTED.
- Virtual thread ID: không mong per-thread allocation measurement theo ThreadMXBean contract.
- Không nhầm bytes allocated với heap live size hoặc memory retained.

### 12.6. Test lỗi thread lifecycle

~~~text
T0: getAllThreadIds() có thread A
T1: thread A kết thúc
T2: getThreadInfo(A) == null
T3: getThreadCpuTime(A) == -1
~~~

Đây là một race hoàn toàn hợp lệ. Một monitoring system production phải **bỏ qua sample không còn hợp lệ hoặc lấy mẫu lại có giới hạn**, không log ERROR hàng nghìn lần một giây cho những threads bình thường kết thúc.

### 12.7. Test JVM portability

Chạy cùng unit tests trên Java 17, runtime deployed và Java 26 nếu tổ chức sử dụng. Không bắt tất cả JVMs có cùng CPU/monitor/synchronizer/allocated flags. Kiểm tra **status logic** và **contract**, thay vì assert rằng contention phải enabled by default.

Virtual threads cần test riêng trên JDK21+ bằng tooling có contract phù hợp; ThreadMXBean platform metrics không được coi là toàn bộ virtual tasks.

---

## 13. Lỗi phổ biến và cách xử lý

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi getCurrentThreadCpuTime ngay | Chưa check capability | isCurrentThreadCpuTimeSupported, enabled trước |
| isThreadCpuTimeEnabled ném UOE | Không có CPU support | Hỏi supported trước |
| CPU time = -1 | Disabled hoặc thread không còn tồn tại | Trả UNAVAILABLE, không hiển thị 0 |
| CPU time=0 bị coi lỗi | 0 có thể hợp lệ | Chỉ -1 là sentinel |
| Đọc blockedTime thành -1 | Contention disabled/unsupported | Kiểm tra flags, báo DISABLED/UNAVAILABLE |
| BlockedCount tăng → coi deadlock | BLOCKED không luôn deadlock | Dùng API deadlock phù hợp |
| getThreadInfo(...true...) ném UOE | Yêu cầu locked monitors không hỗ trợ | isObjectMonitorUsageSupported trước |
| Lock synchronizers missing | VM không support hoặc flag chưa phù hợp | isSynchronizerUsageSupported trước |
| findDeadlockedThreads ném UOE | Không hỗ trợ ownable synchronizers | Check support hoặc dùng monitor-only |
| getThreadInfo trả null | Thread kết thúc trước lúc đọc | Null-check |
| Stack dump quá lớn | Không giới hạn depth/size | Bounded maxDepth, sample rate |
| isThreadAllocatedMemoryEnabled ném UOE | Extension/capability không hỗ trợ | instance/type/support check |
| com.sun.management cast fail | Implementation không có extension | instanceof hoặc tách optional module |
| Allocated bytes âm | Disabled/thread dead/virtual | Trả UNAVAILABLE |
| Xem allocated bytes như heap usage | Khác khái niệm | Giải thích cumulative allocation vs live heap |
| Thread count thấp trên virtual-thread app | ThreadMXBean chỉ platform threads | Dùng JFR/application metrics phù hợp |
| Tự bật contention mỗi lần dashboard mở | Thay đổi toàn JVM, overhead | Admin policy, audit/approval |
| Catch mọi Exception rồi trả unsupported | Che programming bugs | Catch precise exceptions |
| Không xử lý SecurityException | Access denied path bị mất | DENIED, không leo thang |
| Test giả định mọi JVM bật CPU | Không portable | Fake probes, conditional integration |
| Test cố định số platform threads | Thay đổi theo OS/JVM | Kiểm tra status/invariants |
| In stack trace vào public logs | Lộ implementation details | Redaction và quyền truy cập |
| Poll dumpAllThreads liên tục | CPU/GC overhead | Throttle/limit depth |
| Suy CPU nanos là wall-clock | Khác đơn vị/ngữ nghĩa | CPU vs elapsed documentation |
| Thread ID không valid | ID <= 0 | Validate before call |
| Dùng cached thread IDs quá lâu | Thread có thể kết thúc/tái sử dụng ID | Fresh samples/lifecycle aware |
| Gọi extension trên JRE thiếu module | Module không tồn tại | Optional provider/graceful degradation |
| Dùng getters để thay đổi JVM settings | Read-only violation | Setter qua authorized operation |

---

## 14. Bài tập thực hành

1. Chạy file ThreadCapabilityFirstDemo.java và giải thích 15 dòng stdout.
2. Dùng Fake(supported=false), khẳng định enabledCalls và readCalls đều bằng 0.
3. Thêm Fake ném UnsupportedOperationException ngay trong supported(); kiểm tra guardedRead trả UNSUPPORTED.
4. Thêm Fake ném SecurityException trong enabled(); kiểm tra DENIED.
5. Thêm một status FAILED để phân biệt IOException từ JMX remote connector.
6. Tạo một result chứa status, units, observedAtEpochMillis và OptionalLong value.
7. So sánh isThreadCpuTimeSupported với isCurrentThreadCpuTimeSupported ở JDK của bạn.
8. In live CPU capability flags trong môi trường sandbox không chứa dữ liệu nhạy cảm.
9. Đo hai samples current CPU nanos khi chạy một thuật toán CPU-bound; so với elapsed nanos.
10. Xác nhận code không gọi setThreadCpuTimeEnabled trong lộ trình quan sát readonly.
11. Tạo một thread nền platform rồi cho nó kết thúc giữa getAllThreadIds và getThreadInfo; xử lý null.
12. Thử getThreadCpuTime với id <=0 trong unit test bắt IllegalArgumentException.
13. Chứng minh supported=true, enabled=false không có nghĩa không tồn tại contention.
14. Bật contention trong môi trường test được phép, lấy blocked/waited times rồi khôi phục policy đúng.
15. Viết sample rate-limited cho thread count, không dùng dumpAllThreads mỗi lần.
16. Tạo một monitor lock contention fixture với hai platform threads.
17. Kiểm tra isObjectMonitorUsageSupported trước khi getThreadInfo có lockedMonitors=true.
18. Kiểm tra isSynchronizerUsageSupported trước khi getThreadInfo có lockedSynchronizers=true.
19. Tạo một ReentrantLock contention fixture và diễn giải ownable synchronizer info khi VM hỗ trợ.
20. Viết test findMonitorDeadlockedThreads và findDeadlockedThreads chỉ trong sandbox, tránh deadlock process test runner vĩnh viễn.
21. Thêm fallback khi không hỗ trợ ownable synchronizer usage: không yêu cầu lockedSynchronizers.
22. Viết một live report chỉ gồm trạng thái support/enabled, không in thread stacks.
23. Đo allocated bytes với extension khi supported/enabled, phân biệt accumulated allocation và retained heap.
24. Tạo một version không dùng jdk.management module để đo only standard APIs.
25. Thử application Java 21+ có virtual threads và kiểm tra ThreadMXBean không bao phủ chúng.
26. Thiết kế JFR/application-level metrics cho virtual threads.
27. Viết performance test CPU overhead giữa monitoring off/on trong một VM riêng.
28. Đặt maxDepth=8 và maxThreads=100 cho thread dump được kiểm soát.
29. Viết schema API cho metric CPU chứa status và nanoseconds, không cho value=-1 như số đo.
30. Kiểm tra cross-JVM portability trên hai vendor runtimes hỗ trợ Java 17+.
31. Tạo security test observer role không được bật monitoring flags.
32. Soạn playbook khi CPU monitoring unsupported: dùng JFR/OS process metrics hoặc sampling ở tầng ứng dụng.
33. Thiết kế một diagnostic endpoint có rate limit/audit/redaction.
34. Mô phỏng thread termination rồi đọc lại status UNAVAILABLE.
35. Viết checklist xác định khi nào việc bật contention measurement được phép trong production.

---

## 15. Checklist trước khi triển khai production

- [ ] Mọi phép đo optional đều có supported check trước.
- [ ] Enabled checks chỉ được gọi khi JVM hỗ trợ capability tương ứng.
- [ ] Không đọc CPU nanos khi measurement disabled.
- [ ] isThreadCpuTimeSupported khác isCurrentThreadCpuTimeSupported theo use case.
- [ ] Không biến -1 thành 0 trong dashboards/alerts.
- [ ] Contention time có supported/enabled gating.
- [ ] getBlockedTime/getWaitedTime có kiểm tra sentinel và units milliseconds.
- [ ] Không lẫn blockedCount và blockedTime.
- [ ] Object monitors và ownable synchronizers được check riêng.
- [ ] Không yêu cầu lockedMonitors/lockedSynchronizers khi VM không hỗ trợ.
- [ ] Deadlock detection có scope và performance budget.
- [ ] Hiểu ThreadMXBean platform-only đối với virtual threads.
- [ ] Không dùng getThreadCount làm tổng số virtual tasks.
- [ ] Optional com.sun.management extension có instanceof/type/capability check.
- [ ] Không gọi allocated-memory enabled/read nếu unsupported.
- [ ] Không coi allocated bytes là retained heap.
- [ ] ThreadInfo null và CPU -1 do thread termination được xử lý.
- [ ] Không cache thread IDs vô thời hạn.
- [ ] Không dùng thread dump làm synchronization control.
- [ ] Có giới hạn maxDepth, threads, polling interval và response bytes.
- [ ] Monitoring flags không bị đổi trong read-only code path.
- [ ] Bật/tắt capability chỉ qua approved admin configuration.
- [ ] Có audit/overhead assessment khi thay đổi monitoring policy.
- [ ] SecurityException được phân loại riêng với UnsupportedOperationException.
- [ ] JMX remote có TLS, authentication, least privilege, network isolation.
- [ ] Không log raw stack traces/thread names khi privacy policy không cho phép.
- [ ] Unit tests dùng fake probes kiểm tra call ordering.
- [ ] Live integration tests không assume capability flags cố định.
- [ ] Có retries/backoff khi snapshot stale và bounded error handling.
- [ ] Metrics có status, units, scope, sample time và missing-data semantics.
- [ ] Version compatibility kiểm thử trên các JDKs được triển khai.
- [ ] Không sử dụng kiến thức/API đã lỗi thời cho code mới.

## Kết luận

**Kiểm tra khả năng hỗ trợ trước khi yêu cầu dữ liệu** là nguyên tắc thiết kế quan trọng với ThreadMXBean. Việc bean tồn tại không đồng nghĩa CPU monitoring, contention timing, lock usage hay allocated bytes luôn được hỗ trợ hoặc đang bật. Với mỗi phép đo, hãy xác minh **support → enablement → đọc dữ liệu → xử lý sentinel/exception**, và tách dữ liệu thiếu khỏi con số 0 thực sự.

Với lock details, kiểm tra **isObjectMonitorUsageSupported** và **isSynchronizerUsageSupported** trước khi yêu cầu monitor/synchronizer information. Với allocated bytes, kiểm tra extension type cùng support/enabled flags. Khi thread kết thúc giữa lúc lấy IDs và đọc ThreadInfo, null/-1 là tình huống hợp lệ. Trong môi trường có virtual threads, ThreadMXBean vẫn chỉ quan sát platform threads theo contract hiện hành.

Ví dụ Java 17+ trong bài đã chứng minh bằng **fake capability probes** rằng code không gọi enabled/read khi unsupported/disabled, và một lượt thăm dò JVM thật phân loại hợp lệ mà không đổi monitoring flags. Bộ kiểm thử đã chạy thành công trên OpenJDK 24.0.2 với **15 dòng stdout chính xác**.

**Tài liệu tham khảo hiện hành:**

- [ThreadMXBean — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [ThreadMXBean — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [ThreadInfo — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadInfo.html)
- [ManagementFactory — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html)
- [com.sun.management.ThreadMXBean — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/ThreadMXBean.html)
- [com.sun.management.ThreadMXBean — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/ThreadMXBean.html)
- [Thread — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html)
- [JDK Flight Recorder — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/module-summary.html)