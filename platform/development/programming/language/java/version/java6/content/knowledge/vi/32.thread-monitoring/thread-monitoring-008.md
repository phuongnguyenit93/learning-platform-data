# Giới hạn ThreadMXBean đối với loại thread của JDK hiện đại

## 1. Tại sao cần phân biệt loại thread trước khi đọc ThreadMXBean?

Kể từ Java 21, ứng dụng có thể chạy cả **platform threads** lẫn **virtual threads** bằng API chuẩn `java.lang.Thread`. Một service dùng virtual threads có thể đồng thời thực hiện hàng nghìn tác vụ blocking I/O nhưng chỉ cần một số platform threads hữu hạn để chở chúng. Nếu dashboard chỉ dùng `ThreadMXBean.getThreadCount()` rồi gọi đó là “tổng số Java threads”, người vận hành sẽ thấy số liệu **không phản ánh lượng virtual threads thực tế**.

**Kết luận nền tảng trong Java SE 26:** `java.lang.management.ThreadMXBean` **chỉ giám sát và quản lý platform threads**, không hỗ trợ giám sát/quản lý **virtual threads**.

Điều này không phải bug của một JVM cụ thể, cũng không phải do virtual threads chưa được chạy. Đây là **phạm vi thiết kế được ghi thẳng trong API Javadoc hiện hành**.

Bài **“Giới hạn ThreadMXBean đối với loại thread của JDK hiện đại”** thuộc chủ đề **Theo dõi luồng**. Trọng tâm là hiểu những điều `ThreadMXBean` *không* đo được, tránh kết luận sai từ metrics và chọn đường quan sát thay thế khi ứng dụng dùng virtual threads.

Sau bài, bạn sẽ:
- Phân biệt platform, virtual và **carrier** threads.
- Hiểu chính xác những method `ThreadMXBean` loại trừ virtual threads.
- Biết khi nào nhận `null`, `-1` hoặc một thread dump không có virtual tasks.
- Biết vì sao `getThreadCount()` không phải số virtual tasks, và vì sao `getTotalStartedThreadCount()` không phải tổng virtual threads đã start.
- Không dùng `findDeadlockedThreads()` như công cụ chứng minh chương trình không có deadlock involving virtual threads.
- Tránh dùng CPU measurements của carrier để tính trực tiếp CPU của một virtual request.
- Quan sát virtual threads bằng **JFR, `jcmd Thread.dump_to_file`, application instrumentation**, và **`VirtualThreadSchedulerMXBean` từ JDK 24**.
- Nắm cập nhật JDK 24 về monitor pinning, tránh áp dụng mẹo workaround đã lỗi thời cho JDK hiện đại.
- Chạy **ba chương trình Java thực tế**: Java 17 baseline, Java 21 thử nghiệm 64 virtual tasks, JDK 24 scheduler MXBean read-only.

**Độ tin cậy:** Mã được biên dịch/chạy trên OpenJDK 24 với nguồn đặt đúng target version: `--release 17`, `--release 21` và `--release 24`. Kết quả thực tế là **12/12**, **78/78**, **10/10 assertions PASS**. Tất cả thí nghiệm dùng một JVM thử nghiệm độc lập, không mở JMX remote và không kết nối ra Internet.

## 2. Ba khái niệm: platform, virtual và carrier

### 2.1. Platform thread

Một `Thread` loại **platform** thường được ánh xạ một-một vào một OS thread trong suốt vòng đời. JVM/OS phải cấp stack và tài nguyên hệ điều hành để quản lý nó. Thread pools truyền thống, background workers và thread `main` thường là platform threads.

```java
Thread worker = Thread.ofPlatform()
        .name("platform-worker")
        .start(() -> {
            // Thực hiện công việc ngắn, có vòng đời rõ ràng.
        });
worker.join();
```

Đây là **snippet Java 21+** (vì dùng builder và `join()`), không phải file độc lập. Một platform thread còn sống sẽ thuộc phạm vi `ThreadMXBean`, miễn JVM cung cấp thông tin đó vào thời điểm đọc.

### 2.2. Virtual thread

Một `Thread` loại **virtual** là lightweight thread được JVM scheduling, không gắn 1:1 vào OS thread. Trong Java 21+:

```java
Thread worker = Thread.ofVirtual()
        .name("virtual-worker")
        .start(() -> {
            // Thực hiện tác vụ đồng bộ theo phong cách blocking code.
        });
worker.join();
```

Khi virtual thread chờ một số loại blocking I/O/synchronization hỗ trợ unmounting, JVM có thể **unmount** nó khỏi carrier platform thread. Carrier lúc đó phục vụ virtual thread khác. Do đó:
- `Thread.currentThread().isVirtual()` trả `true` bên trong virtual thread.
- `Thread.currentThread().threadId()` vẫn là một Java thread ID dương.
- Virtual thread vẫn có trạng thái, stack, exception, interruption và thread-local semantics tương ứng.
- Nhưng `ThreadMXBean` **không tự động nhìn thấy** virtual thread như một platform thread.

Đừng gọi virtual threads là “chỉ là future” hoặc “không phải Java Thread”: đó vẫn là instance của `Thread`.

### 2.3. Carrier platform thread

Carrier là **platform thread** đang mang/execute một virtual thread tại một thời điểm. Một carrier có thể phục vụ nhiều virtual threads theo thời gian.

```text
                     JVM scheduler
                          |
       +------------------+------------------+
       |                  |                  |
       v                  v                  v
 virtual A            virtual B          virtual C
  blocked              runnable           unmounted
       |                  |                  |
       +------------------+------------------+
                          |
                        mount
                          |
                  carrier platform P
                          |
                    OS/kernel thread
```

Carrier platform P có thể được tính trong `getThreadCount` và có CPU time được JVM/OS báo. Nhưng:
- Một carrier **không tương đương** một virtual request.
- CPU time carrier có thể chứa nhiều virtual tasks ở các thời điểm khác nhau, cộng thêm scheduling/runtime work.
- Không thể gán toàn bộ CPU time carrier cho virtual thread A chỉ vì A đã từng chạy trên nó.
- `getThreadInfo(P.id)` không phải hồ sơ đầy đủ của mọi virtual thread từng chạy trên P.

## 3. Bảng giới hạn chính xác theo Java SE 26

| `ThreadMXBean` method | Platform thread | Virtual thread |
| --- | --- | --- |
| `getThreadCount()` | Đếm live platform threads | **Không đếm** |
| `getPeakThreadCount()` | Peak platform count | **Không đếm** |
| `getTotalStartedThreadCount()` | Tổng platform threads đã start | **Không đếm** |
| `getDaemonThreadCount()` | Live daemon platform threads | **Không đếm** |
| `getAllThreadIds()` | Chứa live platform thread IDs | **Không chứa** virtual IDs |
| `getThreadInfo(id)` | Có thể trả `ThreadInfo` | **`null`** |
| `getThreadInfo(ids,depth)` | Phần tử tương ứng có thể có dữ liệu | **Phần tử `null`** |
| `dumpAllThreads(...)` | Dump platform threads | **Không đưa** virtual threads vào |
| `getThreadCpuTime(id)` | Có thể trả nanoseconds | **`-1`** nếu tính năng supported và enabled |
| `getThreadUserTime(id)` | Có thể trả nanoseconds | **`-1`** |
| `getCurrentThreadCpuTime()` gọi từ thread hiện tại | Có thể trả nanoseconds | **`-1`** khi current là virtual và tính năng supported |
| `getCurrentThreadUserTime()` gọi từ thread hiện tại | Có thể trả nanoseconds | **`-1`** trong virtual |
| `findMonitorDeadlockedThreads()` | Cycle dùng object monitors trên platform threads | Không tìm chu trình virtual |
| `findDeadlockedThreads()` | Cycle platform threads đợi monitors/ownable synchronizers | Không tìm chu trình virtual |
| `isThreadCpuTimeSupported()` | Hỏi capability đo **platform** CPU | Không phải feature flag cho virtual CPU |
| `isThreadContentionMonitoringSupported()` | Hỏi capability contention cho platform | Không tự hỗ trợ virtual |

**Luật quan trọng:** Một API không hỗ trợ virtual thread không đồng nghĩa virtual thread đang lỗi, đã chết hay “có CPU bằng 0”. Số liệu thiếu phải được đánh dấu **unsupported/not observed**, chứ không ép về zero.

## 4. Phiên bản JDK nào áp dụng phần nào?

| Phiên bản | API/cơ chế liên quan | Khi học/cài đặt |
| --- | --- | --- |
| Java 17 | `ThreadMXBean`, `ThreadInfo`, `ManagementFactory` | Có thể dùng baseline platform-monitoring |
| Java 21 | `Thread.ofVirtual` stable, `Thread.isVirtual()`, virtual-thread-per-task executor | So sánh trực tiếp platform vs virtual |
| JDK 24 | `jdk.management.VirtualThreadSchedulerMXBean`; `JEP 491` loại bỏ phần lớn pinning trong `synchronized` | Quan sát scheduler và không áp cách workaround đã lỗi thời |
| Java SE/JDK 26 | Javadoc và CLI/JFR hiện hành mô tả toàn bộ phạm vi | Dùng làm nguồn chuẩn của bài này |

**Chú ý build:**
- `javac --release 17` **không** hỗ trợ `Thread.ofVirtual()`.
- `javac --release 21` **không** hỗ trợ `jdk.management.VirtualThreadSchedulerMXBean` vốn có từ 24.
- Tách mã theo target version như ba files thực hành phía dưới.
- Đừng gọi Java 6 trong tên module học là runtime target Java 6: bài sử dụng kiến thức Java hiện đại theo Special Note và yêu cầu ví dụ runnable.

### 4.1. Gắn nhãn metrics theo loại thread

Nếu bạn định nghĩa metric:
```text
jvm_threads_live = ThreadMXBean.getThreadCount()
```

Tên này có thể gây hiểu nhầm trong hệ thống có virtual threads. Nên đặt một tên có ngữ nghĩa rõ hơn, ví dụ:
```text
jvm_platform_threads_live
jvm_platform_threads_peak
jvm_platform_threads_started_total
app_virtual_tasks_active
app_virtual_tasks_started_total
```

Đây là **các tên metric minh họa do ứng dụng tự thiết kế**, không phải hệ metric tiêu chuẩn tự được Java tạo. `app_virtual_tasks_active` cần instrumentation rõ lifecycle của task, không lấy trực tiếp từ `ThreadMXBean`.

## 5. Tại sao getThreadCount và TotalStarted không đếm virtual threads?

`getThreadCount()` đếm số live **platform** threads. Một ứng dụng có thể đang chạy:
- 20 platform worker/carrier threads.
- 25.000 virtual threads chờ HTTP/database.
- 100 application queues.

Khi đó việc `getThreadCount` trả một con số nhỏ so với 25.000 virtual tasks **không phải mâu thuẫn**. Nó đang đo một loại đối tượng khác.

Tương tự `getTotalStartedThreadCount` tích lũy platform threads đã start, không cộng từng virtual thread được tạo/start. Nếu bắt đầu 1.000 virtual threads, scheduler có thể tạo thêm một số carrier threads, nên total platform started có thể tăng **một phần**; không được dùng chênh lệch đó làm số virtual threads.

### 5.1. Các nguồn sai số khác ngoài loại thread

- `getAllThreadIds()` lấy một snapshot lúc t1.
- `getThreadCount()` lấy một snapshot lúc t2.
- Threads có thể start/finish giữa t1 và t2.
- `getPeakThreadCount()` có thể được một consumer khác reset bằng `resetPeakThreadCount()`.
- `getDaemonThreadCount()` chỉ là một tập con platform threads.
- `Thread.threadId()` chỉ duy nhất **trong vòng đời thread**; sau khi terminate ID có thể được tái sử dụng.

Không ép những con số lấy ở thời điểm khác nhau phải tuyệt đối bằng nhau. Và không dùng thread ID làm khóa nghiệp vụ dài hạn.

### 5.2. Những phép đo không nên làm

Không nên:

```java
int estimatedVirtualThreadCount = bean.getThreadCount();
```

Đây là **anti-pattern** (minh họa code sai). Biến có tên virtual nhưng giá trị là platform count.

Cũng không nên:

```java
long newVirtualTasks =
        bean.getTotalStartedThreadCount() - beforePlatformStarted;
```

Công thức này chỉ đo **platform thread starts** trong khoảng, không phải số virtual tasks. Hãy instrument virtual task lifecycle của ứng dụng.

## 6. getAllThreadIds không trả IDs virtual threads

Một virtual thread có Java ID hợp lệ:

```java
Thread v = Thread.ofVirtual().unstarted(() -> {
    // Task body.
});
long id = v.threadId();
```

Đây là snippet Java 21+. Khi `v` đang sống:
- `v.threadId()` có thể là số dương, distinct.
- `ThreadMXBean.getAllThreadIds()` vẫn không chứa `id`.
- Đây là behavior chuẩn, không phải lỗi JVM.

Lấy `getAllThreadIds()` rồi duyệt `getThreadInfo` chỉ cho bạn **platform thread inventory**. Nó không phải danh sách mọi `Thread` instances mà application sở hữu.

### 6.1. Đọc các arrays đúng alignment

```java
long[] ids = {platformId, virtualId, missingId};
ThreadInfo[] infos = bean.getThreadInfo(ids, 0);
```

Ở đây `platformId` là platform thread đang sống, `virtualId` là virtual thread đang sống và `missingId` là một ID dương không tồn tại. Khi đó:
- `infos.length == ids.length`.
- `infos[0]` có thể không null.
- `infos[1] == null`.
- `infos[2] == null`.
- Không xóa phần tử null rồi tiếp tục dùng cùng indexes để ghép vào IDs.

Nếu không biết ID thuộc loại thread nào, raw `getThreadInfo(id)==null` **không đủ** để kết luận nó là virtual; cũng có thể thread đã chết hoặc ID không tồn tại. Cần nguồn identity/lifecycle của ứng dụng để phân loại.

### 6.2. Java API khác cũng có giới hạn

`Thread.getAllStackTraces()` trên JDK hiện đại trả stack traces của live platform threads, **không cung cấp inventory virtual threads**. Code của bài kiểm thử trực tiếp một platform thread còn sống và 65 virtual threads còn sống: platform xuất hiện trong map, các virtuals không xuất hiện.

Đừng xem `Thread.getAllStackTraces` là “workaround” để biến ThreadMXBean thành virtual-thread-aware.

## 7. getThreadInfo trả null với virtual thread, kể cả nó còn sống

`ThreadInfo` là một **snapshot** của platform thread và các lock/stack details mà JVM có thể thu thập. Các overload `getThreadInfo` không chuyển virtual threads thành ThreadInfo.

Các trường hợp trả null:
1. ID không tồn tại.
2. Thread đã terminate.
3. ID thuộc virtual thread (dù nó đang sống).

Đây là ba trường hợp khác nhau, nhưng đều có thể dẫn tới cùng raw `null`.

### 7.1. Không có stack trong overload một đối số

```java
ThreadInfo tiny = bean.getThreadInfo(platformId);
```

Overload này tương đương `getThreadInfo(platformId, 0)`, nên stack trace của `tiny` rỗng ngay cả với platform thread.

Nếu muốn stack:
```java
ThreadInfo shortStack = bean.getThreadInfo(platformId, 5);
```

`maxDepth` giới hạn số frame, giảm overhead. Nếu dữ liệu null, không cast, không gọi getter. Depth âm ném `IllegalArgumentException`; ID không dương cũng không hợp lệ.

### 7.2. ThreadInfo không phải object điều khiển thread

Một `ThreadInfo` có thể chứa:
- `getThreadId()`, `getThreadName()` và `getThreadState()`.
- `getStackTrace()` có giới hạn.
- `getLockInfo()`, `getLockOwnerId()` và `getLockOwnerName()`.
- `getLockedMonitors()`/`getLockedSynchronizers()` nếu requested và supported.
- `getBlockedTime()`/`getWaitedTime()` trong điều kiện contention timing được bật.

Nó **không phải handle** dùng để gọi `interrupt`, `stop` hay thay priority. Snapshot có thể stale ngay sau khi được lấy; chỉ dùng để chẩn đoán.

### 7.3. JMX raw cũng có cùng giới hạn

Platform MBeanServer đăng ký Threading MXBean dưới:

```text
java.lang:type=Threading
```

Thông qua `MBeanServer.invoke(...)`, `ThreadInfo` được biểu diễn dưới Open Data dạng `CompositeData` khi có dữ liệu. Nhưng với virtual ID, raw invocation vẫn trả **null**. Một remote JMX client không “vượt qua” giới hạn này chỉ vì gọi qua MBeanServer thay vì typed Java interface.

## 8. dumpAllThreads không dump virtual threads

`ThreadMXBean.dumpAllThreads(...)` trả snapshots của live platform threads. Trên Java hiện đại, mọi overload — kể cả có tham số `maxDepth` — **không liệt kê các virtual threads**.

```java
ThreadInfo[] platformOnly = bean.dumpAllThreads(
        false, false, 4);
```

Đây là snippet cần `bean`. Hai tham số boolean yêu cầu có thu thập locked monitors/ownable synchronizers không; `4` giới hạn stack depth. `false,false` hữu ích khi bạn chỉ muốn một ảnh chụp bounded, không trả chi tiết locks.

**Không viết dashboard:** “đã dump all threads, không thấy virtual task nào ⇒ virtual tasks đã kết thúc”. Suy luận này sai vì nguồn dữ liệu không hỗ trợ loại thread đó.

### 8.1. Tại sao cần giới hạn chi phí?

- Stack traces có thể nhiều frames.
- Việc thu owned locks có thể tốn chi phí đáng kể.
- Số platform threads có thể lớn.
- Thread dumps có thể lộ class names, file paths, task names, lock objects.
- Một HTTP health endpoint công khai không nên lấy full dump mỗi request.

Đối với monitoring liên tục: count gauges nhẹ trước, chỉ dump bounded theo sự kiện đã được xác thực và có rate limit.

## 9. CPU time không có nghĩa cho từng virtual thread trong ThreadMXBean

`ThreadMXBean.getThreadCpuTime(id)` đo CPU time tích lũy của **platform thread** có ID đó, khi JVM hỗ trợ và measurement enabled. Giá trị đơn vị **nanoseconds**, có độ phân giải nanosecond nhưng **không hứa chính xác nanosecond**.

Với virtual thread:
- `getThreadCpuTime(virtualId)` trả `-1`.
- `getThreadUserTime(virtualId)` trả `-1`.
- Gọi `getCurrentThreadCpuTime()` **từ bên trong virtual thread** cũng trả `-1` khi feature được hỗ trợ.
- Gọi `getCurrentThreadUserTime()` từ virtual cũng trả `-1`.

Với platform thread còn sống và measurement enabled, CPU time thường không âm. Khi JVM **không hỗ trợ** capability, method có thể ném `UnsupportedOperationException` thay vì trả sentinel.

### 9.1. Kiểm tra capability trước

```java
boolean anyPlatformCpu =
        bean.isThreadCpuTimeSupported();

boolean currentPlatformCpu =
        bean.isCurrentThreadCpuTimeSupported();

if (anyPlatformCpu && bean.isThreadCpuTimeEnabled()) {
    long cpuNanos = bean.getThreadCpuTime(platformId);
    if (cpuNanos >= 0) {
        // Valid observation of this platform thread.
    }
}
```

Đây là snippet, cần `bean` và `platformId`. Trong JVM production **không bật/tắt `setThreadCpuTimeEnabled` theo từng request**; đó là cấu hình measurement chung và có chi phí.

### 9.2. Đừng biến `-1` thành 0

`-1` nghĩa không đo được, không hỗ trợ, không bật hoặc không áp dụng. `0` có thể là một phép đo thực sự hợp lệ. Với telemetry, phân biệt:
- `cpu_nanos_valid` hoặc metric missing.
- `thread_kind=platform`.
- `capability_supported`.
- `cpu_measurement_enabled`.

Không được xuất “virtual_cpu_nanos=0” chỉ vì ThreadMXBean trả -1.

### 9.3. Carrier CPU không phải virtual CPU

Giả sử carrier P đã chạy 100 virtual requests khác nhau. `getThreadCpuTime(P.id)` là CPU do **platform P** đã tiêu thụ, không phải tổng CPU của một request cụ thể, không phải lượng CPU do virtual A tiêu thụ.

Lấy một giá trị carrier CPU rồi gán vào request có ID virtual A sẽ gây lỗi quy kết nghiêm trọng. Nếu cần CPU profiling của virtual workloads:
- Dùng JFR/profiler hỗ trợ stack/callsite/virtual threads trên đúng JDK.
- Đo latency và request boundaries trong application.
- Dùng `OperatingSystemMXBean` hoặc process CPU counters để nắm CPU toàn tiến trình.
- Không giả định `ThreadMXBean` cung cấp per-virtual-thread CPU accounting.

## 10. Contention timing và lock information cũng là platform-only

`ThreadMXBean.isThreadContentionMonitoringSupported()` chỉ nói khả năng đo contention của **platform threads**. Nếu enabled, `ThreadInfo.getBlockedTime()` và `getWaitedTime()` trả **milliseconds**, không phải nanoseconds.

Phân biệt rõ:
- CPU time: nanoseconds.
- Blocked/waited time: milliseconds, có thể -1 nếu disabled.
- Wall-clock request latency: do instrumentation của ứng dụng đo.
- Scheduler queued/mounted estimates: không phải duration.
- Application active virtual tasks: một counter riêng, không phải ThreadMXBean.

Không cộng các đại lượng khác đơn vị. Một virtual thread đang chờ `ReentrantLock` không vì thế mà xuất hiện trong `ThreadInfo`.

### 10.1. Capability guards cần thiết

Các flags:
- `isObjectMonitorUsageSupported()`.
- `isSynchronizerUsageSupported()`.
- `isThreadContentionMonitoringSupported()`.
- `isThreadCpuTimeSupported()`.
- `isCurrentThreadCpuTimeSupported()`.

Không tự coi mọi VM đều hỗ trợ mọi loại lock/time. Nếu yêu cầu chi tiết monitor/synchronizer mà VM không hỗ trợ, một số overload có thể ném `UnsupportedOperationException`. Các tuỳ chọn enable/disable measurement làm thay đổi JVM-wide observation behavior; chỉ đổi có chủ đích từ cấu hình vận hành, không theo từng HTTP request.

## 11. Deadlock detection: điểm mù quan trọng với virtual threads

Hai method:
- `findMonitorDeadlockedThreads()`: chỉ tìm các chu trình **platform** threads chờ object monitors (kiểu `synchronized`).
- `findDeadlockedThreads()`: nếu VM hỗ trợ ownable synchronizers, tìm chu trình **platform** threads chờ monitors hoặc ownable synchronizers như `ReentrantLock`.

Cả hai đều nằm trong phạm vi **platform threads**. Vì vậy `findDeadlockedThreads()==null` **không chứng minh** ứng dụng có virtual threads không bị deadlock.

### 11.1. Ví dụ vòng khóa của virtual threads

```text
virtual A:
  owns ReentrantLock L1
  waits for ReentrantLock L2

virtual B:
  owns ReentrantLock L2
  waits for ReentrantLock L1

=> real waiting cycle exists
=> ThreadMXBean.findDeadlockedThreads does NOT list A or B
```

Trong chương trình thực hành Java 21, chúng ta tạo **chính vòng chờ này** bằng `lockInterruptibly()`. Khi hai virtual threads ở trạng thái `WAITING`, cả `getThreadInfo(A.id)` lẫn `getThreadInfo(B.id)` đều null; `findDeadlockedThreads()` và `findMonitorDeadlockedThreads()` không liệt kê cặp ID đó. Sau khi xác minh, chương trình interrupt cả hai để giải phóng locks.

**Đây là fixture kiểm thử cục bộ có cleanup. Không tạo deadlock tương tự trong hệ thống production hoặc dưới dạng `synchronized` không thể hủy bằng interrupt.**

### 11.2. Không lẫn deadlock với starvation

Ngoài deadlock trên object monitors/ownable synchronizers, ứng dụng có thể treo vì:
- Scheduler/task starvation.
- Chờ Future/CompletionStage mà không tiến triển.
- Hết connection pool/queue capacity.
- Remote I/O không có timeout.
- Semaphore không release.
- Virtual threads bị pin bởi native/foreign call.
- Circular waits giữa services.
- CPU-bound work làm thiếu khả năng phục vụ tasks.

Không có nghĩa `findDeadlockedThreads` phải phát hiện mọi trường hợp trên. Cần instrument operations, timeouts và traces.

## 12. Cập nhật JDK 24: không áp mẹo pinning cũ một cách máy móc

Trước đây một số hướng dẫn về virtual threads khuyên thay mọi `synchronized` bằng `ReentrantLock` vì monitor có thể gây carrier pinning. **Kể từ JDK 24, JEP 491 “Synchronize Virtual Threads without Pinning” cải thiện việc này**, cho phép virtual thread blocked trong nhiều tình huống `synchronized` nhường carrier.

Trên **JDK 26** hiện hành:
- Không nên khẳng định mọi khối `synchronized` đang làm pin virtual threads.
- `synchronized` vẫn có semantics đồng bộ phù hợp và không tự biến thành API lỗi thời.
- Pinning vẫn có thể xảy ra trong các tình huống liên quan **native methods** hoặc **foreign functions**, theo tài liệu Virtual Threads mới.
- Cần dùng JFR event `jdk.VirtualThreadPinned` và profiling của **đúng JDK triển khai**, không sửa hàng loạt locks chỉ từ một câu trích cũ.

**Tách hai câu hỏi:**
1. “Có pin carrier hay không?” — thay đổi theo JDK implementation và dạng blocking.
2. “ThreadMXBean có thấy virtual thread đó không?” — Java SE26 trả lời **không**, kể cả sau các cải tiến pinning.

JDK 24 giải quyết phần lớn pinning của `synchronized` nhưng **không biến ThreadMXBean thành virtual-thread monitor**.

## 13. Quan sát virtual threads bằng công cụ nào?

### 13.1. Application instrumentation: biết chính xác task mình sở hữu

Nếu cần biết số virtual tasks đang xử lý nghiệp vụ:
- Tăng một `AtomicInteger` khi task bắt đầu.
- Giảm trong `finally` khi task kết thúc/cancel.
- Dùng counter thứ hai cho tổng task đã start.
- Kết hợp queue depth, latency histograms, error rate, timeouts và downstream saturation.
- Đảm bảo instrumentation bao trùm mọi entry path của tasks cần đo.

Snippet Java 21+:

```java
AtomicInteger active = new AtomicInteger();
LongAdder started = new LongAdder();

try (ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor()) {
    executor.submit(() -> {
        started.increment();
        active.incrementAndGet();
        try {
            // Work with timeouts and normal cancellation.
        } finally {
            active.decrementAndGet();
        }
    }).get();
}
```

Đây là **snippet**; cần imports `java.util.concurrent.*`, `AtomicInteger` và `LongAdder`; không phải một file độc lập. `active` là số virtual tasks **do instrumentation này quản lý**, không phải mọi virtual threads tạo bởi thư viện khác trong JVM. `get()` chỉ giúp snippet kết thúc có xác định, production thường không chặn ngay sau mỗi submit.

**Tính ứng dụng:** Trong fixture, đúng **64 virtual tasks** đang sống và tăng gauge lên 64 trong khi `getAllThreadIds` không bao gồm ID của task nào trong số đó. Đây là cách thiết kế đúng: tách “virtual task gauge” khỏi “platform thread count”.

### 13.2. jcmd Thread.dump_to_file: cả platform và virtual

Theo Oracle JDK 26, lệnh hiện hành:

```bash
jcmd <pid> Thread.dump_to_file -format=json thread-dump.json
```

`<pid>` là placeholder **PID của JVM được phép chẩn đoán**, không chép nguyên văn dấu ngoặc vào lệnh thực tế. Lệnh cần quyền attach và có thể tạo file lớn chứa thông tin nhạy cảm.

Tính chất:
- Chứa thông tin về cả platform và virtual threads.
- Có thể xuất `-format=json` hoặc `-format=plain` theo `jcmd` man page hiện hành.
- **Không phải snapshot atomic nhất quán** của toàn JVM; dump không pause VM mà có timestamps theo thread.
- Có lock-related data, nhưng **không tự thực hiện deadlock detection**.
- Không có đầy đủ JNI/heap/object-address stats như một số dump truyền thống.
- Giao file diagnostics chỉ cho người có quyền, có retention và redaction phù hợp.

**Phân biệt:** `jcmd <pid> Thread.print` hiển thị platform threads và **mounted virtual threads**. Nó không liệt kê mọi virtual thread đang unmounted. Khi điều tra tình trạng hàng nghìn virtual tasks chờ I/O, `Thread.dump_to_file` thường đúng mục đích hơn.

### 13.3. JDK Flight Recorder (JFR)

JFR là lựa chọn quan trọng cho ứng dụng Java hiện đại, có những events liên quan virtual threads:

| Event | Công dụng | Ghi chú |
| --- | --- | --- |
| `jdk.VirtualThreadStart` | Virtual thread bắt đầu | Không bật mặc định; bật có chủ đích |
| `jdk.VirtualThreadEnd` | Virtual thread kết thúc | Không bật mặc định |
| `jdk.VirtualThreadPinned` | Pinning vượt ngưỡng | Trên JDK26 mặc định có ngưỡng (xem recording settings) |
| `jdk.VirtualThreadSubmitFailed` | Lỗi scheduling/unparking | Theo JDK guide, enabled mặc định |
| `jdk.SocketRead`, `jdk.ThreadSleep` | Những hoạt động có thể gắn với virtual threads | Tùy config và event thresholds |

Ví dụ vận hành (JDK hỗ trợ JFR):

```bash
java -XX:StartFlightRecording:dumponexit=true,filename=application.jfr YourMainClass
jfr print --events jdk.VirtualThreadPinned application.jfr
```

Đây là **các lệnh minh họa**, cần thay `YourMainClass` bằng ứng dụng thật và dùng quyền được phép. Để đếm start/end, phải cấu hình recording enable tương ứng; không giả định số liệu event mặc định là đầy đủ. Với JDK24+, pinning behavior của monitor đã được cải thiện, nên chỉ phân tích event trên đúng runtime.

### 13.4. VirtualThreadSchedulerMXBean từ JDK 24

`jdk.management.VirtualThreadSchedulerMXBean` thuộc module `jdk.management`, có từ **JDK 24**, với ObjectName:

```text
jdk.management:type=VirtualThreadScheduler
```

Nó cung cấp:

| Method | Nghĩa | Giới hạn |
| --- | --- | --- |
| `getParallelism()` | Mức parallelism mục tiêu của scheduler | Không phải số virtual threads |
| `getPoolSize()` | Số platform scheduler workers đã tạo và chưa terminate | Có thể `-1` nếu không biết |
| `getMountedVirtualThreadCount()` | Ước tính số virtual threads đang mounted | Có thể `-1`; estimate có thể cao |
| `getQueuedVirtualThreadCount()` | Ước tính số virtual tasks đang queue để start/resume | Có thể `-1`; không đo mọi live VTs |
| `setParallelism(int)` | Thay mức parallelism mục tiêu | **Thao tác write ảnh hưởng scheduler**, không dùng để quan sát |

**Điểm cần nhớ:** `getPoolSize()` là **platform thread worker count**, không phải virtual thread count. `mounted + queued` cũng không phải “tổng virtual threads sống”, vì những virtual threads đang blocked/unmounted ở I/O hoặc synchronization có thể không ở hai trạng thái đó. Các estimate không phải exact census.

Nếu chỉ muốn monitoring, dùng getters và **không gọi `setParallelism`**. Program Java24 phía dưới xác minh scheduler MXBean và raw JMX attributes trong JVM, không đổi scheduler.

## 14. Thiết kế một monitoring dashboard không hiểu sai thread kinds

Một dashboard đáng tin cần tách nguồn và ý nghĩa:

| Metric đề xuất | Nguồn | Ý nghĩa | Không được suy |
| --- | --- | --- | --- |
| `jvm_platform_threads_live` | `ThreadMXBean.getThreadCount()` | Platform threads còn sống | Không phải total virtual tasks |
| `jvm_platform_threads_started_total` | `getTotalStartedThreadCount()` | Platform thread starts kể từ JVM start | Không phải virtual starts |
| `jvm_platform_threads_peak` | `getPeakThreadCount()` | Đỉnh platform count | Không phải VTs peak |
| `app_virtual_tasks_active` | Application `AtomicInteger` | Tasks do app đo đang chạy/chờ | Không phải mọi VT bên ngoài scope |
| `app_virtual_tasks_started_total` | Application counter | Tasks bắt đầu do app quản lý | Không phải VM-wide |
| `virtual_scheduler_mounted_est` | SchedulerMXBean (24+) | Ước tính mounted VTs | Không phải total live VTs |
| `virtual_scheduler_queued_est` | SchedulerMXBean (24+) | Ước tính tasks waiting to schedule | Không phải application queue depth |
| `process_cpu_usage` | OS/process metrics | CPU toàn process | Không phải CPU riêng virtual thread |
| `http_request_duration` | HTTP instrumentation | Latency request | Không suy từ CPU thread |
| `executor_queue_depth` | Executor/queue metrics | Backlog công việc | Không suy từ peak threads |

### 14.1. Alert theo những triệu chứng thật

Ví dụ:
- `app_virtual_tasks_active` tăng + thời gian chờ downstream tăng → nghi I/O/resource bottleneck.
- `jvm_platform_threads_live` tăng liên tục + thread pool không giới hạn → nghi platform thread leak.
- `virtual_scheduler_queued_est` tăng bền vững + throughput giảm → nghi scheduling pressure, CPU saturation hoặc pinning/native delay; cần xác minh thêm.
- `getThreadCpuTime` của carrier tăng → nền tảng dùng CPU; dùng JFR/profiler để tìm callsites/virtual workloads, **không lập tức gán cho một virtual user**.
- Không phát hiện deadlock trong ThreadMXBean nhưng requests treo → dùng dump/JFR/trace để nhìn virtual wait cycles.

Giá trị cảnh báo phải được hiệu chuẩn theo tải, số core, JVM version và service objective. Không đặt cố định “nếu ThreadMXBean count thấp thì server khỏe”.

### 14.2. Version labels là quan trọng

Nếu một dashboard tập hợp services trên Java17, Java21 và Java26, cần biết:
- Java17 không có stable virtual-thread API.
- Java21 đã có virtual threads nhưng không có JDK24 scheduler MXBean.
- Java24+ scheduler metrics có thể xuất hiện.
- Các quy tắc pinning, providers và JVM diagnostic details đổi theo release.

Đặt `runtime_jdk_major` vào metadata nếu phù hợp. Khi graph thay đổi ở thời điểm nâng JDK, kiểm tra khả năng quan sát và cấu hình thay vì kết luận business traffic biến động.

## 15. Thí nghiệm Java 17: baseline ThreadMXBean còn áp dụng

Chương trình `PlatformOnly17.java` là ví dụ **Java 17** độc lập để chứng minh các phép đọc cơ bản:
- Không dùng virtual-thread API (vì Java17 chưa có stable API này).
- Lấy `ThreadMXBean` từ `ManagementFactory`.
- Đọc counts, peak và started.
- Lấy platform IDs, tra `ThreadInfo` có độ sâu zero và quan sát array alignment.
- Lấy dump có depth 2.
- Không thay metric settings, không reset peak và không mở remote JMX.

### 15.1. Toàn bộ file `PlatformOnly17.java`


```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;

public final class PlatformOnly17 {
    private static int passed;
    static void check(String label, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + label);
        System.out.println("PASS " + label);
        passed++;
    }

    public static void main(String[] args) {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        check("bean-present", bean != null);
        check("thread-count-positive", bean.getThreadCount() > 0);
        check("daemon-count-not-greater-than-total",
                bean.getDaemonThreadCount() <= bean.getThreadCount());
        check("started-count-positive",
                bean.getTotalStartedThreadCount() > 0);
        check("peak-count-at-least-current",
                bean.getPeakThreadCount() >= bean.getThreadCount());
        long[] ids = bean.getAllThreadIds();
        check("thread-ids-present", ids.length > 0);
        ThreadInfo[] infos = bean.getThreadInfo(ids, 0);
        check("batch-length-matches-ids",
                infos.length == ids.length);
        check("at-least-one-live-info",
                Arrays.stream(infos).anyMatch(i -> i != null));
        check("zero-depth-has-no-stack",
                Arrays.stream(infos).allMatch(
                    i -> i == null || i.getStackTrace().length == 0));
        check("bean-has-standard-objectname",
                bean.getObjectName().toString()
                        .equals("java.lang:type=Threading"));
        ThreadInfo[] bounded =
                bean.dumpAllThreads(false, false, 2);
        check("bounded-dump-has-live-threads",
                bounded.length > 0);
        check("dump-respects-max-depth",
                Arrays.stream(bounded).allMatch(
                    i -> i.getStackTrace().length <= 2));
        System.out.println("passed=" + passed);
    }
}
```

### 15.2. Biên dịch/chạy trên JDK 17+

```bash
javac --release 17 -encoding UTF-8 PlatformOnly17.java
java PlatformOnly17
```

Stdout đã xác minh trên OpenJDK 24:

```text
PASS bean-present
PASS thread-count-positive
PASS daemon-count-not-greater-than-total
PASS started-count-positive
PASS peak-count-at-least-current
PASS thread-ids-present
PASS batch-length-matches-ids
PASS at-least-one-live-info
PASS zero-depth-has-no-stack
PASS bean-has-standard-objectname
PASS bounded-dump-has-live-threads
PASS dump-respects-max-depth
passed=12
```

**QA:** `javac --release 17` PASS; chạy OpenJDK24 **12/12 PASS**. Số live platform threads cụ thể có thể khác giữa systems; test không hardcode một con số thread count.

## 16. Thí nghiệm Java 21: giới hạn thật với 65 virtual threads

Chương trình `ThreadTypeBoundaryDemo.java` tạo:
- **1 platform thread** `fixture-platform` còn sống.
- **1 virtual thread** `fixture-virtual` còn sống.
- **64 virtual threads** khác, tên `fixture-fleet-0` đến `fixture-fleet-63`, dùng `CountDownLatch` và một application `AtomicInteger`.
- Tổng cộng **65 virtual threads** sống đồng thời trong khoảng quan sát.

Kiểm chứng:
1. `trackedVirtualTasks.get()==64` trong khi các 64 IDs này không có trong `getAllThreadIds()`.
2. `ThreadMXBean.getThreadInfo(virtualId)` trả `null` dù `virtual.isAlive()==true`.
3. Array `getThreadInfo([platform,virtual,fleet,missing],0)` có 4 vị trí, với 3 null phía sau.
4. `dumpAllThreads(false,false,3)` có platform worker nhưng không có virtual workers.
5. `Thread.getAllStackTraces` chứa platform object nhưng không chứa virtual workers.
6. `MBeanServer.invoke` trả raw `CompositeData` cho platform và null cho virtual.
7. Khi CPU capability được hỗ trợ, `getThreadCpuTime(virtualId)` và `getThreadUserTime(virtualId)` là -1.
8. Ngay từ bên trong virtual thread, `getCurrentThreadCpuTime()` và `getCurrentThreadUserTime()` là -1.
9. Tạo vòng chờ thật của hai virtual threads với hai `ReentrantLock`; `ThreadMXBean` không phát hiện cặp ID này.
10. Dùng `lockInterruptibly()`, `interrupt()` và `join()` để dọn fixture vòng chờ.
11. Trả CPU measurement flag về trạng thái ban đầu nếu test tự bật.
12. Sau cleanup, tất cả virtual workers dừng và `trackedVirtualTasks==0`.

**Cảnh báo:** Đây là **chương trình thử nghiệm chạy trong JVM riêng**. Nó cố ý tạo một chu trình chờ (deadlock) có thể hủy bằng interrupt để chứng minh giới hạn quan sát của ThreadMXBean. Không chạy fixture dưới dạng production health check hoặc trong JVM đang phục vụ user traffic. Test không mở socket/remote JMX và không đụng dữ liệu riêng tư.

### 16.1. File đầy đủ `ThreadTypeBoundaryDemo.java`


```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.ReentrantLock;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

public final class ThreadTypeBoundaryDemo {
    private static int passed;

    static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + name);
        System.out.println("PASS " + name);
        passed++;
    }

    static boolean contains(long[] ids, long target) {
        for (long id : ids) if (id == target) return true;
        return false;
    }

    static boolean await(CountDownLatch latch) {
        try {
            return latch.await(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    static void holdUntil(CountDownLatch release) {
        try {
            if (!release.await(5, TimeUnit.SECONDS))
                throw new IllegalStateException("release timeout");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    static void waitUntilWaiting(Thread first, Thread second)
            throws Exception {
        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(4);
        while (System.nanoTime() < deadline) {
            if (first.getState() == Thread.State.WAITING
                    && second.getState() == Thread.State.WAITING)
                return;
            Thread.sleep(10);
        }
        throw new AssertionError(
                "virtual pair did not reach WAITING");
    }

    static void joinAll(List<Thread> threads) throws Exception {
        for (Thread t : threads) t.join(3_000);
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        check("threadmxbean-is-present", mx != null);
        check("threadmxbean-platform-name",
                mx.getObjectName().equals(
                        new ObjectName("java.lang:type=Threading")));
        check("caller-is-platform", !Thread.currentThread().isVirtual());
        check("platform-count-positive", mx.getThreadCount() >= 1);
        check("thread-counts-are-bounded",
                mx.getDaemonThreadCount() <= mx.getThreadCount());
        check("peak-at-least-current",
                mx.getPeakThreadCount() >= mx.getThreadCount());
        check("started-count-positive",
                mx.getTotalStartedThreadCount() > 0);
        check("java-management-module-name",
                ThreadMXBean.class.getModule().getName()
                        .equals("java.management"));

        boolean cpuAny = mx.isThreadCpuTimeSupported();
        boolean cpuCurrent = mx.isCurrentThreadCpuTimeSupported();
        boolean originallyEnabled = false;
        boolean changedCpuSetting = false;
        if (cpuAny || cpuCurrent) {
            originallyEnabled = mx.isThreadCpuTimeEnabled();
            if (!originallyEnabled) {
                mx.setThreadCpuTimeEnabled(true);
                changedCpuSetting = true;
            }
        }
        check("cpu-capability-implication",
                !cpuAny || cpuCurrent);

        CountDownLatch gate = new CountDownLatch(1);
        CountDownLatch platformReady = new CountDownLatch(1);
        CountDownLatch virtualReady = new CountDownLatch(1);
        AtomicBoolean inVirtual = new AtomicBoolean(false);
        AtomicLong virtualSelfCpu = new AtomicLong(Long.MIN_VALUE);
        AtomicLong virtualSelfUserCpu = new AtomicLong(Long.MIN_VALUE);

        Thread platform = Thread.ofPlatform()
                .name("fixture-platform")
                .daemon(true)
                .unstarted(() -> {
                    platformReady.countDown();
                    holdUntil(gate);
                });
        Thread virtual = Thread.ofVirtual()
                .name("fixture-virtual")
                .unstarted(() -> {
                    inVirtual.set(Thread.currentThread().isVirtual());
                    if (cpuCurrent) {
                        virtualSelfCpu.set(mx.getCurrentThreadCpuTime());
                        virtualSelfUserCpu.set(
                                mx.getCurrentThreadUserTime());
                    }
                    virtualReady.countDown();
                    holdUntil(gate);
                });
        List<Thread> fleet = new ArrayList<>();
        CountDownLatch fleetReady = new CountDownLatch(64);
        AtomicInteger trackedVirtualTasks = new AtomicInteger();
        for (int i = 0; i < 64; ++i) {
            Thread t = Thread.ofVirtual()
                    .name("fixture-fleet-" + i)
                    .unstarted(() -> {
                        trackedVirtualTasks.incrementAndGet();
                        try {
                            fleetReady.countDown();
                            holdUntil(gate);
                        } finally {
                            trackedVirtualTasks.decrementAndGet();
                        }
                    });
            fleet.add(t);
        }

        try {
            platform.start();
            virtual.start();
            fleet.forEach(Thread::start);
            check("platform-ready", await(platformReady));
            check("virtual-ready", await(virtualReady));
            check("virtual-fleet-ready", await(fleetReady));
            check("our-virtual-task-gauge-64",
                    trackedVirtualTasks.get() == 64);
            check("platform-worker-alive", platform.isAlive());
            check("virtual-worker-alive", virtual.isAlive());
            check("platform-flag-false", !platform.isVirtual());
            check("virtual-flag-true", virtual.isVirtual());
            check("inside-virtual-thread-flag-true",
                    inVirtual.get());
            check("all-fleet-are-virtual",
                    fleet.stream().allMatch(Thread::isVirtual));
            check("fleet-threads-still-alive",
                    fleet.stream().allMatch(Thread::isAlive));
            check("all-virtual-ids-positive",
                    fleet.stream().allMatch(t -> t.threadId() > 0));
            check("platform-and-virtual-id-distinct",
                    platform.threadId() != virtual.threadId());

            long[] ids = mx.getAllThreadIds();
            check("live-platform-is-enumerated",
                    contains(ids, platform.threadId()));
            check("one-live-virtual-is-absent",
                    !contains(ids, virtual.threadId()));
            check("whole-virtual-fleet-is-absent",
                    fleet.stream().noneMatch(
                            t -> contains(ids, t.threadId())));
            check("application-count-remains-64",
                    trackedVirtualTasks.get() == 64);
            check("mx-live-count-is-only-platform",
                    mx.getThreadCount() >= 1);

            check("platform-threadinfo-exists",
                    mx.getThreadInfo(platform.threadId()) != null);
            check("virtual-threadinfo-is-null",
                    mx.getThreadInfo(virtual.threadId()) == null);
            check("all-virtual-fleet-threadinfos-null",
                    fleet.stream().allMatch(
                            t -> mx.getThreadInfo(t.threadId()) == null));
            check("threadinfo-missing-id-null",
                    mx.getThreadInfo(Long.MAX_VALUE) == null);
            ThreadInfo[] parallel = mx.getThreadInfo(
                    new long[] {
                        platform.threadId(), virtual.threadId(),
                        fleet.get(0).threadId(), Long.MAX_VALUE
                    }, 0);
            check("batch-threadinfo-has-four-slots",
                    parallel.length == 4);
            check("batch-platform-info-nonnull",
                    parallel[0] != null);
            check("batch-virtual-slot-null",
                    parallel[1] == null);
            check("batch-fleet-slot-null",
                    parallel[2] == null);
            check("batch-missing-slot-null",
                    parallel[3] == null);
            check("batch-depth-zero-no-stack",
                    parallel[0].getStackTrace().length == 0);
            check("platform-info-correct-id",
                    parallel[0].getThreadId() == platform.threadId());

            ThreadInfo[] boundedDump =
                    mx.dumpAllThreads(false, false, 3);
            check("platform-in-bounded-dump",
                    Arrays.stream(boundedDump).anyMatch(
                        i -> i.getThreadId() == platform.threadId()));
            check("virtual-excluded-from-dump",
                    Arrays.stream(boundedDump).noneMatch(
                        i -> i.getThreadId() == virtual.threadId()));
            check("fleet-excluded-from-dump",
                    Arrays.stream(boundedDump).noneMatch(
                        i -> fleet.stream().anyMatch(
                            t -> t.threadId() == i.getThreadId())));
            check("all-dump-stacks-limited-to-three",
                    Arrays.stream(boundedDump).allMatch(
                        i -> i.getStackTrace().length <= 3));
            check("no-locked-monitor-collection-requested",
                    Arrays.stream(boundedDump).allMatch(
                        i -> i.getLockedMonitors().length == 0));
            check("no-locked-synchronizer-collection-requested",
                    Arrays.stream(boundedDump).allMatch(
                        i -> i.getLockedSynchronizers().length == 0));

            Map<Thread, StackTraceElement[]> javaStacks =
                    Thread.getAllStackTraces();
            check("ordinary-platform-stack-present",
                    javaStacks.containsKey(platform));
            check("java-stack-map-excludes-virtual",
                    !javaStacks.containsKey(virtual));
            check("java-stack-map-excludes-fleet",
                    fleet.stream().noneMatch(javaStacks::containsKey));

            MBeanServer server =
                    ManagementFactory.getPlatformMBeanServer();
            ObjectName name = new ObjectName("java.lang:type=Threading");
            check("platform-jmx-threading-registered",
                    server.isRegistered(name));
            check("platform-jmx-count-is-integer",
                    server.getAttribute(name, "ThreadCount")
                        instanceof Integer);
            check("platform-jmx-started-count-is-long",
                    server.getAttribute(name, "TotalStartedThreadCount")
                        instanceof Long);
            Object rawPlatform = server.invoke(name, "getThreadInfo",
                    new Object[] {platform.threadId(), 3},
                    new String[] {"long", "int"});
            check("jmx-platform-threadinfo-compositedata",
                    rawPlatform instanceof CompositeData);
            check("compositedata-from-platform-id",
                    ThreadInfo.from((CompositeData) rawPlatform)
                            .getThreadId() == platform.threadId());
            Object rawVirtual = server.invoke(name, "getThreadInfo",
                    new Object[] {virtual.threadId(), 3},
                    new String[] {"long", "int"});
            check("jmx-virtual-threadinfo-null",
                    rawVirtual == null);

            if (cpuAny) {
                check("cpu-monitoring-enabled-in-test",
                        mx.isThreadCpuTimeEnabled());
                check("platform-cpu-time-available",
                        mx.getThreadCpuTime(platform.threadId()) >= 0);
                check("platform-user-cpu-available",
                        mx.getThreadUserTime(platform.threadId()) >= 0);
                check("virtual-cpu-time-not-reported",
                        mx.getThreadCpuTime(virtual.threadId()) == -1);
                check("virtual-user-time-not-reported",
                        mx.getThreadUserTime(virtual.threadId()) == -1);
                check("fleet-cpu-time-not-reported",
                        fleet.stream().allMatch(
                            t -> mx.getThreadCpuTime(t.threadId()) == -1));
                check("cpu-time-for-missing-id-is-minus-one",
                        mx.getThreadCpuTime(Long.MAX_VALUE) == -1);
            }
            if (cpuCurrent) {
                check("virtual-self-cpu-time-minus-one",
                        virtualSelfCpu.get() == -1);
                check("virtual-self-user-cpu-time-minus-one",
                        virtualSelfUserCpu.get() == -1);
                check("current-platform-cpu-time-available",
                        mx.getCurrentThreadCpuTime() >= 0);
            }
            check("invalid-zero-id-rejected",
                    invalidZeroId(mx));
            check("invalid-stack-depth-rejected",
                    invalidDepth(mx, platform.threadId()));

            // A virtual-virtual ReentrantLock wait cycle is invisible
            // to ThreadMXBean, although each virtual thread is alive.
            if (mx.isSynchronizerUsageSupported()) {
                ReentrantLock left = new ReentrantLock();
                ReentrantLock right = new ReentrantLock();
                CountDownLatch leftHeld = new CountDownLatch(1);
                CountDownLatch rightHeld = new CountDownLatch(1);
                Thread first = Thread.ofVirtual()
                        .name("virtual-cycle-a")
                        .unstarted(() -> {
                            left.lock();
                            try {
                                leftHeld.countDown();
                                if (!await(rightHeld)) return;
                                try {
                                    right.lockInterruptibly();
                                    try { } finally { right.unlock(); }
                                } catch (InterruptedException expected) {
                                    Thread.currentThread().interrupt();
                                }
                            } finally {
                                left.unlock();
                            }
                        });
                Thread second = Thread.ofVirtual()
                        .name("virtual-cycle-b")
                        .unstarted(() -> {
                            right.lock();
                            try {
                                rightHeld.countDown();
                                if (!await(leftHeld)) return;
                                try {
                                    left.lockInterruptibly();
                                    try { } finally { left.unlock(); }
                                } catch (InterruptedException expected) {
                                    Thread.currentThread().interrupt();
                                }
                            } finally {
                                right.unlock();
                            }
                        });
                try {
                    first.start();
                    second.start();
                    check("virtual-cycle-left-held",
                            await(leftHeld));
                    check("virtual-cycle-right-held",
                            await(rightHeld));
                    waitUntilWaiting(first, second);
                    check("both-virtual-deadlock-threads-waiting",
                            first.getState() == Thread.State.WAITING
                            && second.getState() == Thread.State.WAITING);
                    check("virtual-cycle-threadinfos-null",
                            mx.getThreadInfo(first.threadId()) == null
                            && mx.getThreadInfo(second.threadId()) == null);
                    long[] deadlocked = mx.findDeadlockedThreads();
                    check("mxbean-deadlock-detector-excludes-virtual-pair",
                            deadlocked == null
                            || (!contains(deadlocked, first.threadId())
                               && !contains(deadlocked, second.threadId())));
                    long[] monitorOnly =
                            mx.findMonitorDeadlockedThreads();
                    check("monitor-only-also-excludes-virtual-pair",
                            monitorOnly == null
                            || (!contains(monitorOnly, first.threadId())
                               && !contains(monitorOnly, second.threadId())));
                } finally {
                    first.interrupt();
                    second.interrupt();
                    first.join(3_000);
                    second.join(3_000);
                }
                check("virtual-deadlock-fixture-cleaned",
                        !first.isAlive() && !second.isAlive());
            }
        } finally {
            gate.countDown();
            platform.join(3_000);
            virtual.join(3_000);
            joinAll(fleet);
            if (changedCpuSetting) {
                mx.setThreadCpuTimeEnabled(originallyEnabled);
            }
        }
        check("platform-worker-terminated", !platform.isAlive());
        check("virtual-worker-terminated", !virtual.isAlive());
        check("virtual-fleet-terminated",
                fleet.stream().noneMatch(Thread::isAlive));
        check("application-gauge-zero-after-cleanup",
                trackedVirtualTasks.get() == 0);
        check("platform-info-absent-after-termination",
                mx.getThreadInfo(platform.threadId()) == null);
        check("same-threadmxbean-instance",
                ManagementFactory.getThreadMXBean() == mx);
        System.out.println("passed=" + passed);
    }

    static boolean invalidZeroId(ThreadMXBean mx) {
        try {
            mx.getThreadInfo(0);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    static boolean invalidDepth(ThreadMXBean mx, long id) {
        try {
            mx.getThreadInfo(id, -1);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }
}
```

### 16.2. Biên dịch và chạy

```bash
javac --release 21 -encoding UTF-8 ThreadTypeBoundaryDemo.java
java ThreadTypeBoundaryDemo
```

Dùng JDK 21+ để có `Thread.ofVirtual`/`threadId`. Chương trình dùng module chuẩn `java.management` qua `ManagementFactory`. Nó được biên dịch với target Java21 và thực thi trên OpenJDK24.

### 16.3. Stdout chính xác đã xác minh

```text
PASS threadmxbean-is-present
PASS threadmxbean-platform-name
PASS caller-is-platform
PASS platform-count-positive
PASS thread-counts-are-bounded
PASS peak-at-least-current
PASS started-count-positive
PASS java-management-module-name
PASS cpu-capability-implication
PASS platform-ready
PASS virtual-ready
PASS virtual-fleet-ready
PASS our-virtual-task-gauge-64
PASS platform-worker-alive
PASS virtual-worker-alive
PASS platform-flag-false
PASS virtual-flag-true
PASS inside-virtual-thread-flag-true
PASS all-fleet-are-virtual
PASS fleet-threads-still-alive
PASS all-virtual-ids-positive
PASS platform-and-virtual-id-distinct
PASS live-platform-is-enumerated
PASS one-live-virtual-is-absent
PASS whole-virtual-fleet-is-absent
PASS application-count-remains-64
PASS mx-live-count-is-only-platform
PASS platform-threadinfo-exists
PASS virtual-threadinfo-is-null
PASS all-virtual-fleet-threadinfos-null
PASS threadinfo-missing-id-null
PASS batch-threadinfo-has-four-slots
PASS batch-platform-info-nonnull
PASS batch-virtual-slot-null
PASS batch-fleet-slot-null
PASS batch-missing-slot-null
PASS batch-depth-zero-no-stack
PASS platform-info-correct-id
PASS platform-in-bounded-dump
PASS virtual-excluded-from-dump
PASS fleet-excluded-from-dump
PASS all-dump-stacks-limited-to-three
PASS no-locked-monitor-collection-requested
PASS no-locked-synchronizer-collection-requested
PASS ordinary-platform-stack-present
PASS java-stack-map-excludes-virtual
PASS java-stack-map-excludes-fleet
PASS platform-jmx-threading-registered
PASS platform-jmx-count-is-integer
PASS platform-jmx-started-count-is-long
PASS jmx-platform-threadinfo-compositedata
PASS compositedata-from-platform-id
PASS jmx-virtual-threadinfo-null
PASS cpu-monitoring-enabled-in-test
PASS platform-cpu-time-available
PASS platform-user-cpu-available
PASS virtual-cpu-time-not-reported
PASS virtual-user-time-not-reported
PASS fleet-cpu-time-not-reported
PASS cpu-time-for-missing-id-is-minus-one
PASS virtual-self-cpu-time-minus-one
PASS virtual-self-user-cpu-time-minus-one
PASS current-platform-cpu-time-available
PASS invalid-zero-id-rejected
PASS invalid-stack-depth-rejected
PASS virtual-cycle-left-held
PASS virtual-cycle-right-held
PASS both-virtual-deadlock-threads-waiting
PASS virtual-cycle-threadinfos-null
PASS mxbean-deadlock-detector-excludes-virtual-pair
PASS monitor-only-also-excludes-virtual-pair
PASS virtual-deadlock-fixture-cleaned
PASS platform-worker-terminated
PASS virtual-worker-terminated
PASS virtual-fleet-terminated
PASS application-gauge-zero-after-cleanup
PASS platform-info-absent-after-termination
PASS same-threadmxbean-instance
passed=78
```

**QA:** **78/78 assertions PASS** trên OpenJDK 24. Trong JVM test đã kiểm tra, CPU time measurement và ownable synchronizer monitoring đều supported. Trên một provider/runtime không hỗ trợ chúng, mã có guard để bỏ qua một số nhánh; khi ấy **số lượng PASS có thể khác**. Không so số thread count, stack trace, CPU nanoseconds hoặc order của JVM internals với một trị số hardcoded.

### 16.4. Diễn giải một số assertions quan trọng

| Assertion | Ý nghĩa |
| --- | --- |
| `virtual-fleet-ready` | 64 virtual tasks đã vào trạng thái chờ |
| `our-virtual-task-gauge-64` | Application instrumentation thấy đủ tasks do nó tạo |
| `whole-virtual-fleet-is-absent` | ThreadMXBean không liệt kê 64 virtual IDs |
| `all-virtual-fleet-threadinfos-null` | ThreadInfo không áp virtual |
| `batch-virtual-slot-null` | Mảng kết quả giữ alignment và null |
| `fleet-excluded-from-dump` | `dumpAllThreads` không bao gồm virtual tasks |
| `java-stack-map-excludes-virtual` | `Thread.getAllStackTraces` không phải giải pháp thay thế |
| `jmx-virtual-threadinfo-null` | Raw JMX không đổi phạm vi MXBean |
| `virtual-cpu-time-not-reported` | Giá trị CPU của virtual ID là -1 |
| `virtual-self-cpu-time-minus-one` | Gọi current CPU time trong virtual cũng -1 |
| `virtual-cycle-threadinfos-null` | Vòng chờ virtual không xuất hiện trong ThreadInfo |
| `mxbean-deadlock-detector-excludes-virtual-pair` | Không phát hiện deadlock involving virtual |
| `virtual-deadlock-fixture-cleaned` | Interruptible locks giải phóng sau test |
| `application-gauge-zero-after-cleanup` | Không để metrics/task leaks sau test |

**Hạn chế:** Điều được xác minh ở đây là các **trường hợp cụ thể** của API và OpenJDK 24. Không thể từ một lần chạy suy rằng tất cả custom JVM providers, tất cả ứng dụng hoặc mọi loại synchronization đều có behavior timing y hệt nhau. Phạm vi platform-only là ràng buộc ở Java SE26 Javadoc, còn tính hỗ trợ CPU/ownable sync là tùy implementation.

## 17. JDK24+: thí nghiệm MXBean riêng cho scheduler virtual threads

`SchedulerReadOnly24.java` dùng **`jdk.management.VirtualThreadSchedulerMXBean`**. Khác với ThreadMXBean, nó cung cấp số đo scheduler-level (parallelism, pool, mounted/queued estimates).

Bài thử:
- Đọc `ManagementFactory.getPlatformMXBean(VirtualThreadSchedulerMXBean.class)`.
- Kiểm tra ObjectName `jdk.management:type=VirtualThreadScheduler`.
- Đọc `getParallelism()>0`.
- Kiểm tra `getPoolSize()>=-1`, mounted estimate >=-1, queued estimate >=-1.
- Xác nhận MBean được register trên platform JMX server và attributes dùng đúng boxed type.
- **Không gọi `setParallelism`** vì đó là thao tác thay đổi scheduler.
- Không suy `mounted+queued` là tổng live virtual threads.

### 17.1. File `SchedulerReadOnly24.java`


```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import jdk.management.VirtualThreadSchedulerMXBean;

public final class SchedulerReadOnly24 {
    private static int passed;
    static void check(String label, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + label);
        System.out.println("PASS " + label);
        passed++;
    }

    public static void main(String[] args) throws Exception {
        VirtualThreadSchedulerMXBean bean =
                ManagementFactory.getPlatformMXBean(
                        VirtualThreadSchedulerMXBean.class);
        check("scheduler-bean-present", bean != null);
        check("jdk-management-module",
                bean.getClass().getModule().isNamed());
        check("scheduler-objectname",
                bean.getObjectName().toString()
                        .equals("jdk.management:type=VirtualThreadScheduler"));
        check("scheduler-parallelism-positive",
                bean.getParallelism() > 0);
        check("scheduler-platform-pool-optional",
                bean.getPoolSize() >= -1);
        check("mounted-virtual-estimate-optional",
                bean.getMountedVirtualThreadCount() >= -1);
        check("queued-virtual-estimate-optional",
                bean.getQueuedVirtualThreadCount() >= -1);
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();
        ObjectName on = bean.getObjectName();
        check("scheduler-platform-jmx-registered",
                server.isRegistered(on));
        check("parallelism-jmx-attribute-is-integer",
                server.getAttribute(on, "Parallelism")
                        instanceof Integer);
        check("queued-estimate-jmx-attribute-is-long",
                server.getAttribute(on, "QueuedVirtualThreadCount")
                        instanceof Long);
        System.out.println("passed=" + passed);
    }
}
```

### 17.2. Biên dịch và chạy trên JDK24+

```bash
javac --release 24 --add-modules jdk.management -encoding UTF-8 SchedulerReadOnly24.java
java --add-modules jdk.management SchedulerReadOnly24
```

Stdout thực tế trên OpenJDK24:

```text
PASS scheduler-bean-present
PASS jdk-management-module
PASS scheduler-objectname
PASS scheduler-parallelism-positive
PASS scheduler-platform-pool-optional
PASS mounted-virtual-estimate-optional
PASS queued-virtual-estimate-optional
PASS scheduler-platform-jmx-registered
PASS parallelism-jmx-attribute-is-integer
PASS queued-estimate-jmx-attribute-is-long
passed=10
```

**QA:** 10/10 PASS. `getPoolSize()` và các estimates có thể trả sentinel -1 nếu không biết; mã kiểm tra đúng tính nullable-via-sentinel chứ không ép số dương. Tên JDK module `jdk.management` chỉ xuất hiện ở code JDK24+, không áp vào Java17/21 source.

## 18. Làm sao kiểm tra service thực khi MXBean ít dữ liệu?

### 18.1. Kịch bản A — “ThreadCount thấp nhưng requests treo”

Triệu chứng: dashboard báo 30 platform threads, service có 10.000 virtual tasks đợi downstream và response time tăng cao.

**Không kết luận:** chỉ có 30 requests đang được xử lý.

Hướng xử lý:
1. Xem `app_virtual_tasks_active` từ application instrumentation.
2. Xem HTTP/DB pool metrics, queue depth và timeouts.
3. Nếu dùng JDK24+, xem scheduler mounted/queued estimates.
4. Tạo `jcmd Thread.dump_to_file -format=json` khi được phép, parse states/stack traces của virtual threads.
5. Dùng JFR events để tìm blocking/callsites dài.
6. Điều chỉnh downstream pool/timeout/retries/rate limits dựa trên nguyên nhân, không dựa trên platform count.

### 18.2. Kịch bản B — “findDeadlockedThreads null nhưng app vẫn không tiến triển”

**Không kết luận:** không có deadlock.

Xử lý:
1. Kiểm tra liệu các tasks đợi nhau là platform hay virtual.
2. Nếu virtual, ThreadMXBean không phát hiện cycles của chúng.
3. Dùng full virtual thread dump, call graph/correlation IDs và JFR để xem waits.
4. Rà soát `ReentrantLock`, semaphores, futures, queues và remote requests.
5. Fix lock ordering/cancellation/timeouts; đừng “sửa” bằng reset metrics hoặc kill random thread.

### 18.3. Kịch bản C — “CPU carrier cao”

**Không kết luận:** một virtual request cụ thể đang dùng hết CPU.

Thực hiện:
1. Xác định process CPU cao, số cores và interval.
2. Xem CPU platform/carrier là triệu chứng, không phải per-request attribution.
3. Lấy JFR/profiler hỗ trợ virtual threads để tìm stack/callsites.
4. Xem tasks CPU-bound có đang được đưa vào virtual-thread workload không.
5. Giới hạn công việc CPU-bound bằng bounded executors và concurrency policy phù hợp.

### 18.4. Kịch bản D — “Pinning tăng sau nâng JDK?”

Không dựa vào tài liệu cũ rồi khẳng định `synchronized` luôn pin. Từ JDK24 JEP491 đã thay behavior monitor pinning. Xác minh:
1. Runtime JDK version.
2. Event `jdk.VirtualThreadPinned` và thresholds/recording config.
3. Native/foreign calls, I/O và synchronization patterns thực tế.
4. CPU/throughput/latency hiện trạng.
5. So sánh metrics trước–sau có kiểm soát; không rewrite all locks vô cớ.

## 19. Lỗi phổ biến và cách sửa

**1. Gọi `getThreadCount()` là tổng mọi Java threads.**  
Sai với ứng dụng có virtual threads. Đặt tên platform_count.

**2. Dùng `getTotalStartedThreadCount` đếm số virtual threads đã start.**  
Sai; chỉ đếm platform starts.

**3. Nghĩ virtual ID không nằm trong `getAllThreadIds` nghĩa virtual chưa start.**  
Sai: API cố ý không liệt kê virtual IDs.

**4. Thấy `getThreadInfo(virtualId)==null` rồi kết luận virtual chết.**  
Sai: có thể nó còn sống nhưng không thuộc loại thread được hỗ trợ.

**5. Dùng `Thread.getAllStackTraces` làm danh sách virtual threads.**  
Sai: API này không liệt kê virtual threads trong JDK hiện hành.

**6. Dump toàn bộ bằng `ThreadMXBean.dumpAllThreads` rồi nói không có virtual tasks.**  
Sai: đây là platform-only dump.

**7. Coi `getThreadCpuTime(virtualId)==-1` là CPU bằng 0.**  
Sai: -1 nghĩa không đo được/không áp dụng.

**8. Gọi `getCurrentThreadCpuTime` trong virtual và mong số liệu.**  
Theo Javadoc, không báo per-virtual CPU; trả -1 nếu supported.

**9. Gán CPU time carrier cho virtual request.**  
Carrier chạy nhiều virtual tasks theo thời gian, không có attribution trực tiếp.

**10. Coi `findDeadlockedThreads()==null` là bảo đảm không deadlock.**  
Sai: không phát hiện virtual cycles hoặc các dạng application waits khác.

**11. Coi `findMonitorDeadlockedThreads` tương đương `findDeadlockedThreads`.**  
Một method chỉ covers object monitors, method kia có thể covers ownable synchronizers, đều platform-only.

**12. Tạo deadlock `synchronized` để thử rồi interrupt nghĩ nó tự thoát.**  
Không an toàn; fixture thử nghiệm dùng `ReentrantLock.lockInterruptibly`.

**13. Không guard CPU/lock capability flags.**  
Có thể nhận UnsupportedOperationException.

**14. Bật `setThreadCpuTimeEnabled` và `setThreadContentionMonitoringEnabled` theo từng request.**  
Các thay đổi JVM-wide có chi phí và làm lệch monitoring consumers.

**15. Reset `getPeakThreadCount` bằng `resetPeakThreadCount` mỗi lần scrape.**  
Làm mất số liệu đỉnh của toàn process.

**16. Suy `RUNNABLE` luôn nghĩa CPU-bound.**  
Trạng thái Java không đồng nghĩa % CPU thực tế.

**17. Không đặt maxDepth/size limit khi thu ThreadInfo.**  
Làm chậm JVM và có thể lộ stack nội bộ.

**18. Log full thread dumps ở public endpoint.**  
Rò rỉ topology, class names, file paths hoặc thông tin khóa.

**19. Gọi `jcmd Thread.print` là full virtual thread inventory.**  
Nó chỉ bao gồm platform và mounted virtual threads.

**20. Coi `Thread.dump_to_file` là atomic snapshot.**  
Tài liệu JDK26 nói không pause VM, có timestamps theo thread.

**21. Nghĩ `Thread.dump_to_file` cũng phát hiện deadlock tự động.**  
Không; dump có lock data nhưng không thực hiện deadlock detection.

**22. Dùng scheduler `poolSize` như số virtual threads.**  
PoolSize là platform scheduler workers.

**23. Cộng `mounted+queued` để suy mọi virtual threads sống.**  
Blocked/unmounted virtual tasks có thể nằm ngoài hai estimates.

**24. Nghĩ `VirtualThreadSchedulerMXBean` tồn tại ở Java21.**  
API có từ JDK24; test đúng version.

**25. Gọi `setParallelism` để chỉ “đọc scheduler”.**  
Đó là thao tác làm thay đổi scheduler configuration.

**26. Sử dụng ví dụ `Thread.ofVirtual` trong `--release 17`.**  
Không biên dịch; target Java21+.

**27. Tiếp tục khẳng định mọi `synchronized` pin carrier trên JDK26.**  
JDK24 JEP491 đã giải quyết phần lớn các trường hợp monitor pinning.

**28. Cho rằng JFR event Start/End bật mặc định.**  
Không; cần bật bằng recording settings nếu muốn counts theo events.

**29. Tin mọi số liệu JFR/ThreadMXBean là 100% atomic.**  
Sampling, asynchronous events và snapshot races đều tồn tại.

**30. Không biết `ThreadMXBean` là JMX management interface có thể truy cập remotely.**  
Nếu mở JMX remote, phải bảo vệ auth/TLS/permissions.

**31. Coi số active virtual tasks của instrumentation là toàn JVM.**  
Counter chỉ biết tasks đi qua scope của application instrumentation đó.

**32. Không dọn virtual tasks/locks sau test.**  
Dễ để background tasks/leaks làm test không kết thúc hoặc gây load ngoài ý muốn.

## 20. Checklist vận hành & code review

- [ ] Xác định JDK version, VM provider và có virtual threads hay không.
- [ ] Đọc Javadoc hiện hành: ThreadMXBean là platform-only.
- [ ] Đặt tên metrics có `platform`/`virtual` rõ ràng.
- [ ] Không suy total virtual tasks từ `getThreadCount`/`getTotalStartedThreadCount`.
- [ ] Với virtual workflows, instrument lifecycle counters riêng.
- [ ] Sử dụng `Thread.currentThread().isVirtual()` cho classification Java21+.
- [ ] Khi lấy `ThreadInfo`, xử lý null (virtual/missing/terminated).
- [ ] Giữ đúng alignment của batch `getThreadInfo(ids,...)`.
- [ ] Dùng bounded `maxDepth` và rate limit thread dumps.
- [ ] Không coi `Thread.getAllStackTraces` là virtual-thread list.
- [ ] Không coi `ThreadMXBean.dumpAllThreads` là all-kind thread dump.
- [ ] Kiểm tra `isThreadCpuTimeSupported`/`isCurrentThreadCpuTimeSupported` và enabled.
- [ ] Giữ `-1` khác `0` trong CPU metrics.
- [ ] Không gán CPU carrier trực tiếp vào một virtual request.
- [ ] Với deadlocks involving virtual, không dựa vào `findDeadlockedThreads()==null`.
- [ ] Dùng JFR/`jcmd Thread.dump_to_file` khi cần virtual thread diagnostics.
- [ ] Phân biệt `jcmd Thread.print` với `Thread.dump_to_file`.
- [ ] Trên JDK24+, scheduler MXBean là số đo ước tính, không phải exact census.
- [ ] Không gọi `setParallelism` khi chỉ quan sát.
- [ ] Áp dụng JDK24 JEP491 khi đánh giá pinning `synchronized`.
- [ ] Không thu full stack dumps thường xuyên hoặc cho public health handler.
- [ ] Giới hạn JFR/diagnostic data retention và quyền truy cập.
- [ ] Theo dõi queue, downstream pools, request latency và errors.
- [ ] Có timeout/cancellation và cleanup trong virtual task lifecycle.
- [ ] Test đúng `javac --release 17/21/24` tương ứng với mỗi ví dụ.
- [ ] Giữ Special Note: chỉ sử dụng kiến thức còn áp dụng hiện nay.

## 21. Câu hỏi ôn tập

**1. `ThreadMXBean` quan sát loại thread nào trên Java SE26?**  
Chỉ platform threads.

**2. Virtual thread có phải Java Thread không?**  
Có, là instance của `Thread` nhưng JVM schedules nó lên carrier platform threads.

**3. Vì sao `getThreadCount()` nhỏ dù có nhiều virtual tasks?**  
Nó chỉ đếm live platform threads.

**4. `getTotalStartedThreadCount` có đếm virtual thread starts?**  
Không.

**5. `getAllThreadIds` có chứa virtual IDs?**  
Không.

**6. Virtual ID có hợp lệ và dương dù ThreadMXBean không liệt kê?**  
Có.

**7. `getThreadInfo(virtualId)` trả gì?**  
`null`, dù virtual còn sống.

**8. Có thể phân biệt virtual/missing/dead chỉ từ một `ThreadInfo==null`?**  
Không.

**9. `dumpAllThreads` chứa cả virtual threads?**  
Không, đây là platform-only API.

**10. `Thread.getAllStackTraces` có phải inventory virtual threads không?**  
Không.

**11. `getThreadCpuTime(virtualId)` có nghĩa là 0 khi trả -1?**  
Không, -1 là không đo được/không áp dụng.

**12. `getCurrentThreadCpuTime` bên trong virtual thread có trả CPU nanos cho virtual?**  
Không, trả -1 nếu capability supported.

**13. Vì sao carrier CPU không tương đương virtual task CPU?**  
Một carrier có thể chạy nhiều virtual tasks, không có per-task accounting qua ThreadMXBean.

**14. `findDeadlockedThreads` có phát hiện virtual-virtual ReentrantLock cycle không?**  
Không theo ThreadMXBean.

**15. `findMonitorDeadlockedThreads` khác `findDeadlockedThreads` thế nào?**  
Method đầu cho object monitors, method sau có thể cho cả ownable synchronizers; cả hai platform-only.

**16. Có thể dump cả platform và virtual threads bằng lệnh nào?**  
`jcmd <pid> Thread.dump_to_file -format=json filename.json`.

**17. `jcmd Thread.print` có hiển thị mọi virtual threads không?**  
Không, chỉ mounted virtual threads và platform threads.

**18. `Thread.dump_to_file` có atomic snapshot/deadlock detection không?**  
Không.

**19. JFR event nào hỗ trợ quan sát pinning?**  
`jdk.VirtualThreadPinned`.

**20. JFR VirtualThreadStart/End có bật mặc định không?**  
Không; bật qua recording settings.

**21. `VirtualThreadSchedulerMXBean` có từ JDK mấy?**  
JDK 24.

**22. Scheduler `getPoolSize()` có bằng số virtual threads còn sống không?**  
Không; nó đo platform worker pool.

**23. Scheduler mounted/queued là số chính xác toàn virtual threads không?**  
Không, là estimates và không bao gồm mọi trạng thái blocking.

**24. JEP 491 của JDK24 ảnh hưởng điều gì?**  
Giảm/loại bỏ phần lớn pinning virtual threads khi blocked trong `synchronized`.

**25. Có nên sửa mọi synchronized sang ReentrantLock trên JDK26 chỉ để tránh pinning không?**  
Không; xác minh bằng JFR/profiling trước, JEP491 đã thay behavior.

**26. Trong Java21 fixture, ứng dụng theo dõi được bao nhiêu virtual fleet tasks?**  
64; đó là custom application gauge, không phải ThreadMXBean.

**27. Tại sao bài có 3 files dùng Java17/21/24 riêng?**  
Để đúng API availability và compiler target tương ứng.

**28. Kết quả 78/78 PASS có chứng minh mọi JVM provider hỗ trợ CPU measurement không?**  
Không. Những nhánh CPU cần capability guard; JVM khác có thể bỏ qua.

## 22. Tài liệu chính thức và còn áp dụng

- [Oracle Java SE 26 — `ThreadMXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html): platform-only boundary, counts, IDs, CPU, dumps, deadlocks, capability flags.
- [Oracle Java SE 26 — `ThreadInfo`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadInfo.html): platform snapshots, nullability, lock and stack fields.
- [Oracle Java SE 26 — `ManagementFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html): local JMX platform MXBeans.
- [Oracle Java SE 26 — `Thread`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html): platform/virtual thread API, threadId, isVirtual, lifecycle.
- [Oracle Java SE 26 — `Executors`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor`.
- [Oracle Java SE 26 — `VirtualThreadSchedulerMXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/jdk/management/VirtualThreadSchedulerMXBean.html): JDK24+ scheduler metrics and estimates.
- [Oracle JDK 26 — `jcmd` tool](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html): `Thread.dump_to_file`, `Thread.print` and related commands.
- [Oracle JDK 26 — Virtual Threads Guide](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html): carrier scheduling, thread dumps, JFR events, pinning.
- [Oracle JDK24 — Significant Changes / JEP 491](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html): monitor synchronization without pinning, hiện hành trên JDK mới hơn.
- [Oracle Java SE 26 — `java.lang.management` package](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/package-summary.html): standard JVM management APIs.
- [Oracle Java SE 26 — `java.util.concurrent.locks.ReentrantLock`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): interruptible locking used by test fixture.
- [Oracle Java SE 26 — `javax.management.openmbean.CompositeData`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/CompositeData.html): raw JMX representations.

**Ghi nhớ:** Giới hạn căn bản của `ThreadMXBean` không phải “số virtual threads quá nhiều” mà là **nó được đặc tả chỉ quản lý platform threads**. Do đó counts, IDs, ThreadInfo, CPU, thread dumps và deadlock detection từ ThreadMXBean đều không thể dùng như một virtual-thread monitor. Hãy xây dashboard tách rõ loại thread; đo application virtual task lifecycle bằng instrumentation, dùng `jcmd`/JFR khi cần chi tiết và xem scheduler MXBean JDK24+ như số đo **scheduler**, không phải census toàn bộ virtual threads.
