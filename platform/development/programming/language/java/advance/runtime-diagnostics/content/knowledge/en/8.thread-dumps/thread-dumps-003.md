# 8.3 Đọc tên thread, Java thread id, native id, trạng thái và các stack frame

**Thread dump** là ảnh chụp tại một thời điểm về các luồng và call stack mà JVM có thể quan sát. Khi một dịch vụ Java 17+ chậm, treo, tăng số thread hoặc có vẻ dùng CPU bất thường, thread dump giúp trả lời: thread nào đang làm gì; thread đang chờ monitor/condition/I/O hay đang chạy mã; luồng nào đang giữ khóa; và một stack frame cụ thể liên hệ tới đoạn mã nào.

Đọc một dump đúng cách đòi hỏi phân biệt ít nhất **bốn loại thông tin**: **tên thread** (nhãn do chương trình/JVM đặt), **Java thread ID** (định danh trong JVM), **native thread ID** (định danh luồng ở hệ điều hành, nếu triển khai thể hiện), **trạng thái và stack frames**. Trên HotSpot, trường `tid` ở header là địa chỉ cấu trúc thread nội bộ — **không phải** Java thread ID và cũng **không phải** native thread ID. Một sự nhầm lẫn nhỏ ở đây có thể khiến bạn theo dõi nhầm thread trong `top -H` hoặc kết luận rằng Java thread bị treo dù nó chỉ đang đợi việc trong thread pool.

Bài Knowledge này tập trung vào **đọc và diễn giải**, không mở rộng thành hướng dẫn toàn bộ các công cụ profiling. Các lệnh minh họa áp dụng cho HotSpot/OpenJDK 17 khi có đủ quyền. **Luôn xác nhận đúng PID, JVM start time và container namespace trước khi lấy dump**; dữ liệu có thể chứa đường dẫn nội bộ, tên task, endpoint, class name và thông tin nhạy cảm.

## 1. Mục tiêu đọc thread dump

Sau bài học, bạn cần:

- Tách header của một thread: tên, số thread kiểu `#n`, `daemon`, `prio`, `os_prio`, `tid`, `nid`, mô tả trạng thái, CPU/elapsed nếu có.
- Giải thích Java `Thread.State`: `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED` và giới hạn khi so với trạng thái scheduler của OS.
- Đọc các frame theo thứ tự **trên cùng là method gần hiện tại**, dưới là các caller; hiểu `Native Method`, `Unknown Source`, file/line number và frame từ Java library/framework.
- Nhận diện các dòng đồng bộ như `- waiting to lock`, `- locked`, `- parking to wait for`, `Locked ownable synchronizers`.
- Chuyển `nid` dạng hexadecimal sang native thread ID decimal trên Linux để đối chiếu `top -H` hoặc `ps -L`, đồng thời tránh nhầm `tid` và `Thread.getId()`.
- Dùng `ThreadMXBean` trong Java 17 để đọc Java thread ID/name/state/frame và biết API chuẩn này không cung cấp `nid`.
- Lấy nhiều dump có timestamp/instance identity, phân nhóm stack và kiểm chứng giả thuyết bằng metrics, JFR, GC log, OS counters thay vì chẩn đoán từ một dòng.

## 2. Thu được thread dump từ đâu?

### 2.1. Những cách phổ biến trên HotSpot/OpenJDK 17

Với PID ví dụ `12345` của đúng JVM cần điều tra:

```bash
# Liệt kê các JVM mà công cụ có thể nhìn thấy.
jcmd -l

# In Java thread dump, có cả thông tin khóa java.util.concurrent.
jcmd 12345 Thread.print -l

# Lệnh thay thế nếu JDK có jstack và thao tác được phê duyệt.
jstack -l 12345
```

Lệnh `jcmd 12345 Thread.print -l` là lựa chọn thông dụng; tham số `-l` yêu cầu thêm thông tin về các khóa `java.util.concurrent`. Theo tài liệu JDK 17, `Thread.print` có **impact mức Medium**, phụ thuộc số lượng threads. Đây không phải một phép “đọc file” miễn phí: JVM cần thu thập thông tin stack/lock, có thể làm chậm ứng dụng trong khoảng ngắn, nhất là khi có rất nhiều thread.

Một số hệ thống cho phép gửi tín hiệu `SIGQUIT` (Linux/Unix) để JVM in dump vào luồng output/log mà tiến trình quản lý. Ví dụ lệnh `kill -QUIT <pid>` có ý nghĩa đặc thù trên HotSpot/Linux; **chỉ dùng khi đã biết signal handling, nơi nhận output và quy trình vận hành**. Không xem `SIGQUIT` là thao tác portable trên mọi JVM/OS.

`jstack` có thể hữu ích nhưng tài liệu JDK 17 mô tả nó là công cụ experimental/unsupported. Đối với JVM đang chạy, ưu tiên `jcmd` và các khả năng management/JFR phù hợp với runtime thực. Không gọi dump liên tục trên toàn cluster.

### 2.2. Chụp đúng đối tượng và gắn mốc thời gian

Trước khi đọc nội dung:

1. Xác nhận service, hostname/node, pod/container ID, **PID đúng namespace**, JVM start/uptime, build version hoặc image digest.
2. Ghi timestamp UTC của thời điểm bắt đầu thu và các mốc cần thiết khi quá trình thu kết thúc.
3. Xác định command có được hỗ trợ bằng `jcmd <pid> help Thread.print` nếu môi trường có công cụ.
4. Chọn số mẫu theo độ dài sự cố và tác động cho phép: ví dụ ba dump cách nhau vài giây **khi đã được phép**, thay vì poll liên tục.
5. Lưu vào nơi có quyền hạn chế và có retention rõ ràng; đừng đẩy dump nguyên văn lên issue/chat công khai.

Ví dụ chuyển stdout của công cụ vào file **khi thư mục đích được cấp quyền an toàn trước đó**:

```bash
jcmd 12345 Thread.print -l > thread-20261029T081500Z.txt
```

Tên file ở trên chỉ là minh họa. Thao tác này ghi output vào filesystem **của nơi chạy công cụ**, không tự tạo file trong JVM target. Output có thể khác về header, timestamp, số thread và frame giữa các JDK/vendor. Chỉ chụp đúng PID; trên container, `jcmd -l` không bảo đảm nhìn thấy JVM ở namespace khác.

### 2.3. Thread dump khác stack trace của một exception

| Nguồn | Phạm vi | Trả lời được gì? |
| --- | --- | --- |
| Thread dump JVM | Nhiều thread đang sống tại lúc chụp, cộng dữ liệu JVM-specific | “Các thread đang ở đâu và chờ gì?” |
| Exception stack trace | Đường gọi tại thời điểm exception được ném/ghi lại | “Exception xuất hiện tại đâu và đi qua lời gọi nào?” |
| `Thread.currentThread().getStackTrace()` | Một thread đang gọi API | “Thread này hiện gọi đến đâu?” |
| `ThreadMXBean.getThreadInfo(...)` | Thread được chọn, stack depth tùy yêu cầu | Chẩn đoán bằng API quản lý, Java ID/state/locks |
| JFR/profiler | Chuỗi sự kiện hoặc samples theo thời gian | “CPU, lock, allocation và latency thay đổi ra sao?” |

Một exception ở 08:10 và thread dump ở 08:20 **không** thể được coi là cùng stack nếu không có bằng chứng liên hệ. Thread dump là **snapshot**, không phải lịch sử toàn bộ lời gọi của luồng.

## 3. Cấu trúc một mục thread dump HotSpot

Một ví dụ **tổng hợp minh họa** (giá trị hex, đường dẫn và thời gian không lấy từ JVM thực):

```text
"checkout-worker-7" #42 daemon prio=5 os_prio=0 cpu=220.12ms elapsed=31.01s
   tid=0x00007f1020032000 nid=0x2a3f waiting for monitor entry
   [0x00007f100abcc000]
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.PaymentService.charge(PaymentService.java:118)
    - waiting to lock <0x0000000700a01234> (a java.lang.Object)
    at com.example.CheckoutController.pay(CheckoutController.java:54)
    at java.base/java.lang.Thread.run(Thread.java:833)
```

Trong dump thật, header có thể nằm trên **một dòng** và có thứ tự/thuộc tính khác. Dòng `cpu=...`, `elapsed=...` hoặc mảng địa chỉ `[...]` phụ thuộc phiên bản và dạng đầu ra. **Không tạo parser production chỉ bằng một regex giả định mọi HotSpot/JDK đều in giống ví dụ**.

Đọc từ ngoài vào trong:

| Thành phần | Ví dụ | Diễn giải chính xác |
| --- | --- | --- |
| Tên | `"checkout-worker-7"` | Nhãn do Thread/Executor/JVM đặt; có thể trùng hoặc đổi |
| `#42` | `#42` | Số/ID được HotSpot biểu diễn trong header; thường dùng để nhận diện Java thread; xác minh theo phiên bản, không nhầm `tid` |
| `daemon` | `daemon` | Thread daemon; thiếu từ khóa thường nghĩa non-daemon trong format đó |
| `prio=5` | `prio=5` | Mức ưu tiên Java thread được báo; không phải số %CPU |
| `os_prio=0` | `os_prio=0` | Priority gắn với native/OS scheduling theo cách HotSpot báo |
| `cpu=220.12ms` | `cpu=...` | CPU time tích lũy hoặc thông tin CPU do runtime in; không là %CPU tức thời |
| `elapsed=31.01s` | `elapsed=...` | Thời gian tồn tại theo mốc runtime của thread, không phải duration request |
| `tid=0x...` | `0x00007f1020032000` | **Địa chỉ native VM thread structure** theo HotSpot; không phải Linux TID |
| `nid=0x2a3f` | `0x2a3f` | **Native thread ID**, thường là LWP/TID trên Linux, in dạng hex |
| `waiting for monitor entry` | chữ mô tả ở header | Trạng thái nội bộ/OS-related được implementation in, khác enum Java phía dưới |
| `java.lang.Thread.State: BLOCKED` | `BLOCKED` | Trạng thái ở mức Java VM, chờ vào `synchronized` monitor |
| `at ... (File.java:118)` | frame Java | Method hiện tại/caller và vị trí trong source khi có line info |
| `- waiting to lock <0x...>` | metadata monitor | Đang chờ khóa monitor của object có identity được in |

**Điểm dễ sai nhất:** trong header HotSpot, `tid=0x...` **không** được đưa cho `top -H` để tìm một Linux thread. Để đối chiếu OS native thread, hãy dùng **`nid`**, chuyển từ hex sang decimal khi cần. `Java Thread.getId()` là một lớp định danh khác.

## 4. Tên thread: hữu ích nhưng không phải khóa duy nhất

### 4.1. Tên được đặt như thế nào?

Trong Java:

```java
Thread current = Thread.currentThread();
String name = current.getName();
current.setName("checkout-worker-7"); // Chỉ minh họa, đổi tên thread hiện tại.
```

Tên thường được tạo bởi `ThreadFactory` của pool, framework, container, executor hoặc mã ứng dụng. Những mẫu hay gặp:

- `main`: thread chính khi Java launcher chạy `main`.
- `pool-3-thread-1`: kiểu tên thread từ một số `Executors.defaultThreadFactory`.
- `http-nio-8080-exec-12`: tên do một số servlet server đặt.
- `ForkJoinPool.commonPool-worker-2`: worker của fork-join pool.
- `Reference Handler`, `Finalizer`, `Common-Cleaner`: thread phục vụ JVM/Java runtime, tùy implementation và version.
- `GC Thread#...` hoặc `VM Thread`: có thể là **JVM internal/native threads**, không nhất thiết có `java.lang.Thread` object với Java ID thông thường.

Tên thread giúp khoanh vùng subsystem nhưng **không bảo đảm duy nhất**: một executor có thể tạo tên giống executor khác; nhiều đời JVM đều có thread `main`; thread name có thể được đổi. Khi tổng hợp nhiều dump, kết hợp **PID + JVM start + Java ID hoặc nid + timestamp**; với thread có thể kết thúc/tái tạo, các số ID có thể được reuse.

### 4.2. Đặt tên thread để dễ chẩn đoán

Nếu tự tạo thread trong ứng dụng:

```java
java.util.concurrent.ThreadFactory factory = task -> {
    Thread t = new Thread(task);
    t.setName("payment-worker-" + t.getId());
    return t;
};
```

Đoạn mã là snippet để tạo `ThreadFactory`, không phải chương trình đầy đủ. Cách dùng `Thread.getId()` trong tên chỉ là chiến lược tham khảo; Java 17 `getId()` trả Java thread ID, không phải `nid`. Khi framework có cơ chế đặt tên, ưu tiên cấu hình thread factory tập trung.

Không ghi secret, tenant identifier nhạy cảm hoặc payload người dùng vào tên thread: tên này có thể xuất hiện trong thread dump, JMX và log. Với thread pool, đừng đổi tên theo request rồi quên khôi phục; yêu cầu nối context nên được giải quyết bằng trace/request IDs và logging context thích hợp.

### 4.3. Thread “idle” có phải bất thường không?

Không. Một thread pool chờ queue sẽ có frame gần `ThreadPoolExecutor.getTask`, `LinkedBlockingQueue.take`, `LockSupport.park` và `WAITING`. Đó có thể là hành vi **bình thường**. Tên `http-nio-...` hoặc `pool-...` không cho biết request nào đang xử lý trừ khi call stack hoặc context bổ sung chứng minh được.

Đừng đánh đồng “có hàng trăm thread WAITING” với deadlock. Cần xem wait reason, lock ownership, queue length, request rate và liệu số lượng/stack có tăng bất thường theo thời gian hay không.

## 5. Java thread ID, native ID và `tid`: ba định danh khác nhau

### 5.1. Java thread ID

Trên Java 17:

```java
long javaThreadId = Thread.currentThread().getId();
```

`Thread.getId()` trả một số dương kiểu `long`, được tạo trong JVM cho thread; có thể được tái sử dụng **sau khi thread chấm dứt**. `ThreadMXBean` dùng Java thread IDs để truy vấn `ThreadInfo`. Tên method `ThreadInfo.getThreadId()` cũng biểu diễn Java thread ID.

Ví dụ để tìm thread tên `checkout-worker-7` trong API quản lý, nên lấy `ThreadInfo.getThreadId()`, không nhập `nid` hex vào `ThreadMXBean.getThreadInfo(long)` và mong thấy đúng thread.

Một số HotSpot thread-dump formats hiển thị `#42` tương ứng với Java thread number; **định dạng header không phải contract ổn định của Java SE**, nên khi phân tích dump từ vendor/JDK khác hãy xác minh schema thực. Đặc biệt, đừng đồng nhất `#42` với `tid=0x00007f...` chỉ vì hai trường nằm trên cùng header.

### 5.2. Native thread ID (`nid`)

Native ID là nhận diện của OS thread. Trong dump HotSpot trên Linux, `nid=0x2a3f` thường tương ứng TID/LWP **10815** ở dạng decimal. Mã kiểm tra phép đổi:

```text
0x2a3f = 2*4096 + 10*256 + 3*16 + 15 = 10815
```

Bash trên Linux có thể chuyển đổi:

```bash
printf '%d\n' 0x2a3f
```

Output chính xác:

```text
10815
```

Trên Linux, khi PID JVM là `12345`, đối chiếu thread của **đúng process**:

```bash
top -H -p 12345
ps -L -p 12345 -o pid,tid,stat,pcpu,comm
```

`top -H` hoặc `ps -L` có thể hiển thị native TID decimal; đối chiếu với `nid` **của cùng thời điểm, cùng PID namespace**. TID có thể bị recycle sau khi native thread kết thúc. CPU% từ `top` là kết quả của **khoảng đo của công cụ**, không trùng mốc với dump tức thời nếu thu cách nhau lâu.

Trên Windows, OS-native thread ID và công cụ hiển thị khác Linux; câu lệnh `ps -L`/`top -H` không áp dụng. Trên macOS, cách ánh xạ và tool khác. Không gọi mọi native ID ở mọi OS là “Linux LWP”.

### 5.3. `tid=0x...` là gì?

Trong nhiều dump HotSpot, `tid` là con trỏ/địa chỉ tới cấu trúc nội bộ của JVM đại diện cho Java thread (giá trị ở dạng hexadecimal). Nó **không** phải:

- giá trị Java `Thread.getId()`;
- native ID từ `nid`;
- PID của JVM process;
- chỉ số thread trong executor;
- timestamp hay địa chỉ object monitor đang chờ.

Do đó không đổi `tid` hex sang decimal rồi tìm trong `top -H`, không xem `tid` lớn là “thread đang tốn nhiều bộ nhớ”. Công cụ/phân tích dump ở phiên bản khác có thể dùng ký hiệu khác; cần phân biệt ý nghĩa theo format thực.

### 5.4. Bảng so sánh định danh

| Trường | Ví dụ | Phạm vi/nguồn | Dùng để nối với |
| --- | --- | --- | --- |
| Thread name | `"checkout-worker-7"` | Do ứng dụng/JVM đặt, không unique | Nhóm chức năng khi đọc stack |
| Java ID | `42` / `#42` trong một số dump | Java Thread / `ThreadMXBean` | `ThreadInfo.getThreadId()`, telemetry Java |
| Native ID | `nid=0x2a3f` | OS thread; hex trong HotSpot dump | Linux LWP/TID decimal `10815` |
| HotSpot `tid` | `0x00007f1020032000` | Địa chỉ cấu trúc thread HotSpot | Chỉ dùng trong ngữ cảnh VM/dump phù hợp |
| Process PID | `12345` | OS process (có thể đổi theo namespace) | `jcmd <pid>`, container/host process identity |
| Object monitor ID | `<0x0000000700a01234>` | Identity in cho Java object lock trong dump | Dòng `waiting to lock` / `locked` trong **cùng dump** |

Một API Java SE 17 như `ThreadMXBean` **không có method chuẩn trả native thread ID**. Để nối Java ID với OS TID, dựa vào dump HotSpot chứa cả thông tin hoặc công cụ JVMTI/JFR/native được phép và có mapping thích hợp.

### 5.5. Vì sao không nên dùng chỉ một ID qua nhiều dump?

- JVM restart: Java thread IDs có thể bắt đầu lại; PID hệ điều hành có thể bị reuse.
- Thread pool tăng/giảm: một worker cũ kết thúc, worker mới có tên giống hệt.
- Container: PID/TID nhìn từ host và trong container có thể khác; cùng số “1” ở hai PID namespaces không cùng process.
- Garbage collection/JVM internals: pointer và object identity in trong dump không phải global identifiers bất biến.
- File dump có thể được collector gửi trễ, thứ tự nhận khác thứ tự thu.

Khi cần đối chiếu dài hạn, sử dụng **timestamp UTC + JVM start/uptime + service/node/container identity + các ID phù hợp**.

## 6. Đọc `java.lang.Thread.State` chính xác

Java 17 định nghĩa sáu giá trị của enum `Thread.State`. Đây là **trạng thái VM**, không phải bảng trạng thái OS scheduler (Linux `R/S/D/T/Z`). Một thread chỉ có một enum state tại một thời điểm quan sát.

| Java state | Ý nghĩa | Frame/case thường thấy | Bẫy diễn giải |
| --- | --- | --- | --- |
| `NEW` | `Thread` đã tạo nhưng `start()` chưa gọi | Thread object trước khi chạy; thường không có trong dump live | Không kết luận “sắp chết” |
| `RUNNABLE` | Đang có thể thực thi trong JVM / native call | CPU work, event loop, socket read, native poll | **Không đồng nghĩa** đang chiếm CPU thật |
| `BLOCKED` | Đang chờ vào monitor của `synchronized` | `- waiting to lock`, entry vào synchronized method/block | Không bao hàm mọi dạng chờ lock |
| `WAITING` | Chờ vô thời hạn cho hành động của thread khác | `Object.wait()`, `Thread.join()`, `LockSupport.park()` | Có thể là worker idle bình thường |
| `TIMED_WAITING` | Chờ có timeout | `Thread.sleep`, timed `wait/join/park` | Không bảo đảm thread sẽ chạy ngay khi timeout |
| `TERMINATED` | Thread đã kết thúc | Thread object còn được tham chiếu; không thường có trong dump live | Không nghĩa JVM đã crash |

Trên thread dump JVM, dòng dạng `java.lang.Thread.State: ...` thể hiện enum Java; mô tả ở cuối header như `runnable`, `waiting on condition`, `in Object.wait()` hay `waiting for monitor entry` là mô tả implementation-specific. Không đối xử với chuỗi header đó như một enum Java thứ hai.

### 6.1. `RUNNABLE` không đồng nghĩa “đang dùng 100% CPU”

Ví dụ:

```text
"nio-worker" #26 ...
   java.lang.Thread.State: RUNNABLE
        at sun.nio.ch.EPoll.wait(Native Method)
        at sun.nio.ch.EPollSelectorImpl.doSelect(EPollSelectorImpl.java:...)
        at java.base/java.nio.channels.Selector.select(Selector.java:...)
```

Đây là **mẫu minh họa đã lược bớt line number**, không phải output cố định của Java 17. Một thread có state RUNNABLE nhưng đang ở native poll, chờ I/O readiness, có thể tiêu thụ rất ít CPU. Muốn phát hiện CPU hotspot, cần **CPU time theo thread qua hai mẫu, OS `top -H`/`ps -L` hoặc JFR/profiler**, chứ không đếm các dòng RUNNABLE.

Ngược lại, một thread CPU-bound chạy tính toán có thể hiển thị RUNNABLE với frame lặp lại ở mã tính toán. Nhưng **một** dump đặt frame đó ở top cũng chưa đủ kết luận CPU cao; quan sát mẫu liên tiếp và CPU metrics.

### 6.2. `BLOCKED` chỉ chờ `synchronized` monitor

Ví dụ:

```text
"request-17" #91 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.Cache.read(Cache.java:87)
        - waiting to lock <0x0000000700a00111> (a java.lang.Object)
        at com.example.Service.handle(Service.java:32)
```

Thread đang chờ acquire một Java monitor để vào đoạn `synchronized`. Cần tìm thread **đang giữ cùng monitor** `<0x0000000700a00111>`, thường có dòng `- locked <0x0000000700a00111>` hoặc thông tin owner trong dump đầy đủ/`ThreadInfo`.

Một `ReentrantLock.lock()` hoặc `Condition.await()` dùng `LockSupport.park` có thể hiện **WAITING** thay vì `BLOCKED`. Vì thế đếm số thread BLOCKED không đủ để phát hiện toàn bộ lock contention.

### 6.3. `WAITING` có nhiều lý do

Các mẫu phổ biến:

```text
java.lang.Thread.State: WAITING (on object monitor)
    at java.base/java.lang.Object.wait(Native Method)

java.lang.Thread.State: WAITING (parking)
    at java.base/jdk.internal.misc.Unsafe.park(Native Method)
    at java.base/java.util.concurrent.locks.LockSupport.park(...)

java.lang.Thread.State: WAITING
    at java.base/java.lang.Thread.join(Thread.java:...)
```

Đây là các **mảnh stack minh họa**; file/line và frame cụ thể thay đổi theo JDK. Ngữ nghĩa:

- `Object.wait`: thread thường đã **nhả monitor** tương ứng khi bước vào wait và cần được thông báo/đánh thức rồi giành lại monitor để đi tiếp.
- `LockSupport.park`: thread chờ permit hoặc một hành động từ cơ chế concurrency, thường ở queue/thread pool/lock.
- `Thread.join`: chờ một thread khác kết thúc.

Một thread `WAITING` trong `LinkedBlockingQueue.take` có thể là worker pool đang rảnh. Nếu thread đó giữ một resource khác trong khi chờ, vẫn có nguy cơ gián tiếp; phải đọc cả stack, locks và workload.

### 6.4. `TIMED_WAITING` là chờ có hạn, không phải tự động lỗi

Ví dụ:

```text
java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.base/java.lang.Thread.sleep(Native Method)
    at com.example.RetryLoop.backoff(RetryLoop.java:47)
```

Một retry thread sleep 500 ms là hành vi bình thường nếu đúng chính sách. Khi latency cao, xem có phải request thread vô tình sleep lâu, backoff lặp, timeout quá lớn hoặc hàng đợi bị tắc hay không. `sleep` **không nhả Java monitor đã giữ**; điều này khác `Object.wait()` và có thể gây lock contention nếu được gọi trong `synchronized`.

### 6.5. `NEW` và `TERMINATED` hiếm khi thấy trong dump JVM live

Java API `Thread.getState()` trên một Thread object có thể trả NEW trước `start`, hoặc TERMINATED sau khi chạy xong. Nhưng thread dump của **những thread đang sống/được JVM liệt kê** thường không hiển thị danh sách mọi Thread object chưa start hoặc đã chết. Đừng kết luận “JVM không có Thread.State.NEW” vì dump thiếu mục NEW.

### 6.6. Java state khác OS state

Linux thread có thể là running/runnable `R`, sleeping `S`, uninterruptible sleep `D` hoặc các trạng thái khác. Java RUNNABLE có thể đi với OS sleeping ở native I/O; Java WAITING có thể đi với OS `S`. Để đối chiếu:

1. Tìm `nid` (native TID) của **cùng thread** trong dump.
2. Đổi hex → decimal theo đúng platform.
3. Xem OS state/CPU trên đúng PID namespace và thời điểm.
4. Không vội ánh xạ một-một giữa Java state và OS state.

## 7. Đọc stack frames: từ dòng trên đến chuỗi lời gọi

### 7.1. Thứ tự stack frames

Một ví dụ:

```text
"http-worker-12" #64 ...
   java.lang.Thread.State: RUNNABLE
        at com.example.db.Client.read(Client.java:146)
        at com.example.order.OrderRepository.find(OrderRepository.java:77)
        at com.example.order.OrderService.get(OrderService.java:118)
        at com.example.web.OrderController.get(OrderController.java:41)
        at java.base/java.lang.Thread.run(Thread.java:833)
```

Dòng gần đầu `Client.read` là **frame gần điểm thread đang thực thi/được chụp nhất**; các dòng sau là **caller** sâu hơn. Không đọc từ dưới lên rồi kết luận `Thread.run` là đoạn mã gây chậm. Với nhiều framework, stack có thể có hàng chục/hàng trăm frame trong proxy/reflection/netty/servlet; phần quan trọng thường là nhóm frame ở vùng business code và các blocking primitives.

Ký hiệu chung:

```text
at [module/]package.Class.method(File.java:line)
```

- `package.Class.method`: tên class/method mà stack walker biết.
- `module/`: tên Java module khi format in kèm.
- `File.java:line`: dòng source nếu bytecode/build giữ line number metadata.
- `Native Method`: frame method native; không có line Java tương ứng.
- `Unknown Source`: không đủ thông tin file/line; không tự động là mã độc hay lỗi.
- `...` hoặc truncated frames: output có thể bị rút gọn do độ sâu/policy.
- `<init>`, `<clinit>`: constructor và static class initializer trong frame tương ứng.

Không xem line number là vị trí chắc chắn của **bottleneck**: nó là nơi thực thi tại snapshot, có thể nằm trong phương thức chờ do API/JVM or JIT. Muốn chứng minh hotspot CPU cần nhiều samples và CPU attribution.

### 7.2. Cùng frame xuất hiện ở nhiều thread nghĩa là gì?

Nếu 200 thread cùng hiện:

```text
at java.base/jdk.internal.misc.Unsafe.park(Native Method)
at java.base/java.util.concurrent.locks.LockSupport.park(...)
at java.base/java.util.concurrent.LinkedBlockingQueue.take(...)
at java.base/java.util.concurrent.ThreadPoolExecutor.getTask(...)
```

thì có thể chỉ là **thread pool idle**. Nếu 200 thread cùng hiện:

```text
at java.base/java.net.SocketInputStream.socketRead0(Native Method)
at com.example.client.InventoryClient.call(InventoryClient.java:88)
at com.example.web.CheckoutController.submit(CheckoutController.java:59)
```

thì có thể gợi ý **nhiều request cùng đợi downstream I/O**, cần kiểm tra timeout, connection pool, dependency latency, queue length và request metrics. Hai đoạn là mẫu cách đọc ý nghĩa, không nhất thiết là frame chính xác của mọi JDK17 (cơ chế socket implementation có thể khác).

Vì vậy hãy phân nhóm **stack signature** như 3–8 frame liên quan thay vì chỉ đếm top frame `Unsafe.park` hoặc `Thread.run`. Khi có hàng ngàn thread, phân tích theo group/đường gọi có giá trị hơn đọc tuần tự từng dòng.

### 7.3. Frame native và JIT

Thread dump `Thread.print` chủ yếu cung cấp Java stack; một số thread ở native call thể hiện `Native Method` nhưng không đưa toàn bộ stack C/C++ của JNI/OS. Với crash ở native, cần `hs_err_pid*.log`, native stack/core dump hoặc profiler native được phép.

Các tối ưu hóa JIT/inlining, `safepoint`, chạy trong JNI hoặc thiếu debug symbols có thể làm frame/line khác source gốc; không giả định JDK17 luôn thấy mọi frame chính xác như một lời gọi chưa tối ưu hóa. Dùng debug symbols/JFR/native tooling khi cần, không tự suy diễn từ `Unknown Source`.

### 7.4. Thread dump không lưu giá trị biến cục bộ

Một frame `OrderService.get(OrderService.java:118)` **không** cho biết đối tượng order ID là gì, SQL query string hay giá trị local variable. Nó cũng không đủ chứng minh mã đã thực thi các nhánh phía trên trong quá khứ. Đừng suy ra dữ liệu nhạy cảm từ tên thread, địa chỉ monitor hoặc frame; muốn context request có thể dùng log/tracing đã thiết kế, nhưng không dump toàn bộ request payload để “ghép cho nhanh”.

## 8. Dòng khóa và đồng bộ: `waiting to lock`, `locked`, `parking to wait for`

### 8.1. Monitor: chủ sở hữu và người chờ

Một nhóm thread minh họa:

```text
"lock-holder" #50 ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.base/java.lang.Thread.sleep(Native Method)
        at com.example.Cache.refresh(Cache.java:101)
        - locked <0x0000000700a01111> (a java.lang.Object)

"lock-waiter" #51 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.Cache.read(Cache.java:89)
        - waiting to lock <0x0000000700a01111> (a java.lang.Object)
```

Đây là **mẫu tổng hợp**, line numbers và formatting thay đổi theo JDK. Cùng monitor identity `<0x0000000700a01111>` gợi ý `lock-holder` đang nắm monitor mà `lock-waiter` phải chờ. Dù holder đang TIMED_WAITING trong `Thread.sleep`, nó **vẫn có thể đang giữ monitor**, vì `Thread.sleep` không nhả lock. Đây là lỗi thiết kế dễ gây latency hàng loạt.

Hãy xem method của holder nằm trong đoạn `synchronized` nào và có gọi I/O, sleep hoặc xử lý quá lâu không. Không chỉ nhìn “waiter BLOCKED” rồi sửa lock ở thread đó; nguyên nhân thường nằm ở **holder** hoặc cách chia phạm vi critical section.

### 8.2. `Object.wait` khác `Thread.sleep`

| Hành vi | Liên quan monitor | Thread state thường thấy |
| --- | --- | --- |
| Vào `synchronized` khi monitor bị giữ | Đang chờ acquire monitor | `BLOCKED` |
| `Object.wait()` khi sở hữu monitor | Nhả monitor được wait, chờ notify/interruption; sau đó cần reacquire | `WAITING` hoặc `TIMED_WAITING` |
| `Thread.sleep(...)` bên trong synchronized | **Không** tự nhả monitor đang giữ | `TIMED_WAITING` |
| `LockSupport.park(...)` | Chờ permit/đánh thức; không tự nhả mọi lock ứng dụng đang giữ | `WAITING` hoặc `TIMED_WAITING` |
| `ReentrantLock.lock()` khi phải chờ | Đồng bộ qua `AbstractQueuedSynchronizer`, không phải Java monitor `BLOCKED` theo nghĩa hẹp | Thường `WAITING (parking)` |

Đây là mô hình thường gặp, không phải lời hứa mọi frame sẽ có đúng chuỗi chữ. Quy tắc quan trọng: **trạng thái WAITING không chứng minh thread không giữ lock nào**.

### 8.3. “Locked ownable synchronizers”

Tham số `-l` thường thêm một khu vực về locks từ `java.util.concurrent`, ví dụ các `ReentrantLock` hoặc ownable synchronizers, khi JVM hỗ trợ:

```text
Locked ownable synchronizers:
    - <0x0000000700abc777> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
```

Đây là ví dụ định dạng của một lock mà thread đang sở hữu, không phải tất cả locks trong ứng dụng. Với code sử dụng `ReadWriteLock`, `StampedLock`, asynchronous lock hay custom synchronization, khả năng hiển thị có thể khác. Một dòng `- parking to wait for <0x...>` và vùng “Locked ownable synchronizers” cần được đọc theo **ngữ cảnh cơ chế khóa**, không chỉ so hex ID mà không hiểu ownership.

### 8.4. `ThreadInfo` có gì tương đương?

`java.lang.management.ThreadInfo` có:

- `getLockInfo()`, `getLockName()`: lock mà thread đang chờ;
- `getLockOwnerId()`, `getLockOwnerName()`: Java thread sở hữu lock nếu biết;
- `getLockedMonitors()`: Java monitors đang sở hữu;
- `getLockedSynchronizers()`: ownable synchronizers đang sở hữu;
- `getBlockedCount()`/`getWaitedCount()`;
- `getBlockedTime()`/`getWaitedTime()` khi contention monitoring được hỗ trợ và bật.

`getLockOwnerId() == -1` có thể nghĩa không có owner được nhận diện; **không** chứng minh chương trình không hề chờ. `getBlockedTime() == -1` có thể do contention monitoring chưa bật. Khi gọi `ThreadMXBean.dumpAllThreads(true, true)`, phải xác minh hỗ trợ `isObjectMonitorUsageSupported()` và `isSynchronizerUsageSupported()` trước, đồng thời cân nhắc chi phí chụp tất cả threads.

### 8.5. Deadlock cần chu trình chờ, không chỉ một thread BLOCKED

Một deadlock cổ điển: thread A giữ monitor L1 và chờ L2, thread B giữ L2 và chờ L1. Nếu chỉ có A BLOCKED chờ L2, ta chưa có bằng chứng deadlock; có thể B sẽ giải phóng L2 sau vài mili giây.

Trên HotSpot, full thread dump có thể in khu vực phát hiện “Java-level deadlock”. Trong Java:

- `ThreadMXBean.findMonitorDeadlockedThreads()` tìm deadlock qua **object monitors**;
- `ThreadMXBean.findDeadlockedThreads()` mở rộng tới **ownable synchronizers** theo mức hỗ trợ.

Các API này không tìm được mọi kiểu deadlock bên ngoài JVM như hai request chờ database/remote service hoặc ứng dụng bận chờ future vô hạn mà không tạo chu trình locks được JVM nhận diện. Một kết quả `null` **không** chứng minh không có starvation hoặc distributed deadlock.

## 9. Chương trình Java 17+ có stdout xác định: tên, ID, state và stack

Ví dụ chỉ dùng interface Java chuẩn và không attach JVM khác. Lưu file **`ThreadBasicsDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public class ThreadBasicsDemo {
    public static void main(String[] args) {
        Thread current = Thread.currentThread();
        current.setName("diagnostic-main");

        Thread notStarted =
                new Thread(() -> {}, "sample-worker");

        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        ThreadInfo info =
                mx.getThreadInfo(current.getId(), 8);

        System.out.println("current.name=" + info.getThreadName());
        System.out.println("current.id.positive="
                + (info.getThreadId() > 0));
        System.out.println("current.state=" + info.getThreadState());
        System.out.println("current.stack.present="
                + (info.getStackTrace().length > 0));
        System.out.println("new.name=" + notStarted.getName());
        System.out.println("new.state=" + notStarted.getState());
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac ThreadBasicsDemo.java
java ThreadBasicsDemo
```

**Stdout chính xác** của ví dụ tiêu chuẩn:

```text
current.name=diagnostic-main
current.id.positive=true
current.state=RUNNABLE
current.stack.present=true
new.name=sample-worker
new.state=NEW
```

Vì ví dụ tự đặt tên current thread, nó không phụ thuộc mặc định tên `main` của launcher. `getThreadInfo(current.getId(), 8)` chụp thread đang thực thi, nên trả Java ID/state và tối đa 8 stack frames. `notStarted` mới được tạo chứ chưa `start()`, nên là NEW; **nó không được kỳ vọng xuất hiện trong danh sách live threads của `ThreadMXBean.getAllThreadIds()`**.

Bài học chính: `ThreadInfo.getThreadId()` cùng loại ID với `Thread.getId()`, còn không hề có `getNativeThreadId()` trong interface quản lý chuẩn Java 17. `getStackTrace()` được trả về theo thứ tự top frame ở index 0, các caller bên dưới.

## 10. Chương trình Java 17+ có stdout xác định: chuyển native ID hex

Lưu file **`NativeIdMathDemo.java`**:

```java
public class NativeIdMathDemo {
    public static void main(String[] args) {
        String nidFromDump = "0x2a3f";
        long nativeTid = Long.parseLong(
                nidFromDump.substring(2), 16);

        long illustrativeJavaThreadId = 42L;

        System.out.println("nid.hex=" + nidFromDump);
        System.out.println("nid.decimal=" + nativeTid);
        System.out.println("java.id=" + illustrativeJavaThreadId);
        System.out.println("idsAreDifferent="
                + (nativeTid != illustrativeJavaThreadId));
    }
}
```

Chạy:

```bash
javac NativeIdMathDemo.java
java NativeIdMathDemo
```

**Stdout chính xác:**

```text
nid.hex=0x2a3f
nid.decimal=10815
java.id=42
idsAreDifferent=true
```

`illustrativeJavaThreadId` là một **số giả lập của ví dụ**, không phải ID thực của thread đang chạy chương trình. Mục đích: minh họa `nid` là native ID hex để so với OS, trong khi Java thread ID là một giá trị khác có nguồn khác. Khi parse dump thực, phải kiểm tra format input có `0x` hợp lệ và giới hạn số, không coi phép toán này là parser thread dump đầy đủ.

## 11. Chương trình Java 17+: đọc nhiều thread bằng `ThreadMXBean`

`ThreadMXBean` thuộc module `java.management`. Dùng nó khi muốn lấy dữ liệu Java thread theo cách lập trình thay vì parse toàn văn output HotSpot. Đoạn sau là snippet đặt trong một method:

```java
java.lang.management.ThreadMXBean mx =
        java.lang.management.ManagementFactory
                .getThreadMXBean();

long[] ids = mx.getAllThreadIds();
for (long id : ids) {
    java.lang.management.ThreadInfo info =
            mx.getThreadInfo(id, 10);
    if (info == null) {
        // Thread có thể đã kết thúc giữa hai lần đọc.
        continue;
    }
    System.out.println(info.getThreadId() + " "
            + info.getThreadName() + " "
            + info.getThreadState());
}
```

**Lưu ý:** code cố tình không in toàn bộ frames để giảm dữ liệu và bảo mật. `getAllThreadIds()` phản ánh một tập live threads ở thời điểm gọi; giữa việc lấy IDs và đọc `getThreadInfo`, thread có thể chấm dứt, nên `info == null` là tình huống bình thường.

Để lấy thông tin locks (chỉ trên VM hỗ trợ):

```java
boolean monitors = mx.isObjectMonitorUsageSupported();
boolean synchronizers = mx.isSynchronizerUsageSupported();

java.lang.management.ThreadInfo[] snapshot =
        mx.dumpAllThreads(monitors, synchronizers);

for (java.lang.management.ThreadInfo t : snapshot) {
    // Chỉ chọn thread thực sự liên quan và redact dữ liệu nhạy cảm.
    System.out.println(t.getThreadId() + " "
            + t.getThreadName() + " " + t.getThreadState());
}
```

Đây là snippet đặt trong method có `mx` được khai báo như trên. `dumpAllThreads` có thể tốn chi phí cao trên tiến trình có rất nhiều threads. Hãy đặt lịch/chọn phạm vi và chỉ ghi ra nguồn bảo mật. Nếu cần chặn stack quá sâu, Java 17 có overload `dumpAllThreads(boolean, boolean, int maxDepth)`; việc giới hạn depth giúp giảm thông tin nhưng có thể bỏ mất caller quyết định nguyên nhân.

### 11.1. ThreadMXBean không thay thế native/thread-dump tools

- Nó dùng **Java thread ID**, không trả native `nid` chuẩn.
- Nó trả Java stack traces, không mặc định đưa full C/C++ native frames.
- Nó có thể trả `-1` cho blocked/waited time khi contention monitoring không bật hoặc không hỗ trợ.
- Nó không bảo đảm lấy một ảnh chụp **hoàn toàn đồng thời** của mọi thread khi hệ thống chạy tiếp.
- API có thể gây overhead; việc bật thread CPU time hoặc contention monitoring là **thay đổi trạng thái quản lý** cần cân nhắc.

Nếu cần matching với Linux TID, HotSpot `nid` hoặc các công cụ native/OS có thể cần thiết. Nếu mục tiêu là so trạng thái ở mức Java và lock owner, `ThreadInfo` là giao diện rõ contract hơn text parsing.

## 12. Đối chiếu thread dump với CPU và OS threads

### 12.1. Nhận diện CPU hot thread từng bước

Giả sử số liệu `top -H` của một process Linux cho thấy native TID `10815` dùng nhiều CPU. Để xác định Java stack:

1. Xác nhận PID process và namespace; lấy thời điểm `top` đo CPU.
2. Đổi decimal TID `10815` sang hexadecimal: `0x2a3f`.
3. Trong **thread dump của cùng JVM**, tìm header có `nid=0x2a3f`.
4. Đọc Java state và các stack frames; ghi chú có phải application code, GC/JIT/native, hay I/O.
5. Lấy một vài dump ở thời điểm gần nhau **nếu tác động cho phép** hoặc dùng JFR/profiler, so stack signature.
6. Đối chiếu process CPU/time, request rate, GC pauses và container CPU quota.

Đừng so một snapshot `top` lúc 08:00 với dump 08:20 vì native thread ID có thể đã được tái sử dụng hoặc workload khác. Nếu không thấy Java thread tương ứng, native thread có thể là JVM internal/native thread, JNI worker hoặc thread đã biến mất giữa hai lần đo.

### 12.2. CPU time là counter tích lũy, không phải tốc độ tức thời

Một số HotSpot dumps có header `cpu=220.12ms elapsed=31.01s`. **Không** hiểu `cpu=220ms` là “thread sử dụng 220ms CPU trong 1 giây vừa qua” nếu format không nói vậy. Để tính tỉ lệ CPU theo thời gian, cần hai mẫu trong cùng đời thread với counter CPU time nhất quán:

```text
thread_cpu0_ns = 2_000_000_000
thread_cpu1_ns = 2_500_000_000
wall0_ns       = 10_000_000_000
wall1_ns       = 11_000_000_000

delta_thread_cpu_ns = 500_000_000
delta_wall_ns       = 1_000_000_000
one_core_fraction   = 0.50  (50% của một CPU core)
```

Đây là số liệu mô phỏng. `ThreadMXBean.getThreadCpuTime(javaThreadId)` có thể cho CPU time theo thread khi VM hỗ trợ và đã bật. Trước khi dùng, kiểm tra `isThreadCpuTimeSupported()` và `isThreadCpuTimeEnabled()`. Giá trị `-1` có thể chỉ unsupported/unavailable/thread không sống; không biến thành zero và không cộng qua hai đời JVM.

### 12.3. Ghép với OS state

Một native thread có Java `RUNNABLE` nhưng Linux `S` có thể đang chờ trong syscall native. Một Java `BLOCKED` chờ monitor có thể xuất hiện như OS sleeping. Sự khác nhau này không nhất thiết là lỗi của công cụ: hai tầng mô tả **khác ngữ nghĩa** và các mẫu được lấy ở thời điểm khác nhau.

Khi nghi CPU starvation hoặc throttling trên container, bổ sung cgroup `cpu.stat`, quota, scheduler run queue và host contention. Thread dump không hiển thị một bộ đếm “throttled CPU time” tiêu chuẩn cho mỗi Java thread.

## 13. Phương pháp đọc nhiều dump để tìm vấn đề thực

### 13.1. Không kết luận từ một snapshot

Một snapshot của thread `request-12` ở `Socket.read` chứng minh thread **đang chờ I/O tại lúc chụp**, không chứng minh dependency bị treo 30 giây. Nếu thread đó có mặt ở cùng stack sau 5 giây và 10 giây, đồng thời latency metrics tăng, giả thuyết I/O wait mới mạnh hơn.

Mỗi dump có giá trị vì nó là **bằng chứng tức thời**, nhưng dữ liệu động (CPU, lock contention, pool starvation) thường đòi hỏi so sánh. Chỉ chụp mẫu bổ sung khi có quyền và overhead chấp nhận được.

### 13.2. Một quy trình nhất quán

```text
1. Chốt JVM identity (pid + start + container/node)
2. Chốt khoảng sự cố và UTC timestamps
3. Chụp dump t0 (+ lock info khi cần)
4. Gắn snapshot CPU/latency/GC/threads gần t0
5. Chờ khoảng quan sát phù hợp, chụp t1/t2 nếu được phép
6. Chuẩn hóa header fields và nhóm stack signatures
7. So thay đổi state, lock owner, top user frames
8. Kiểm chứng bằng JFR/traces/OS metrics
9. Viết kết luận mức độ chắc chắn + bước khắc phục nhỏ nhất
```

Không so `tid`/`nid` giữa dump từ hai JVM khác nhau rồi coi là cùng thread. Nếu thấy PID giống nhưng JVM start thay đổi thì phải coi là một process generation mới.

### 13.3. Nhóm thread theo stack signature

Thay vì liệt kê từng thread, có thể nhóm:

| Nhóm | Dấu hiệu | Khả năng ban đầu | Bằng chứng tiếp theo |
| --- | --- | --- | --- |
| HTTP request blocked monitor | Nhiều `BLOCKED` cùng `waiting to lock <x>` | Lock holder/critical section quá lớn | Tìm owner và so nhiều dump |
| HTTP request native read | Nhiều `RUNNABLE` ở socket native read | Downstream I/O chậm | Tracing/timeout/network metrics |
| Pool workers WAITING | `LinkedBlockingQueue.take`/`park` | Idle pool, thường bình thường | Queue depth, active/idle counts |
| Pool workers BUSY | Nhiều frame application code lặp | CPU work hoặc concurrency issue | CPU time/JFR, request rate |
| Threads TIMED_WAITING sleep | `Thread.sleep` từ retry/backoff | Retry delay/periodic task | Retry count, deadline/timeout |
| Threads WAITING on future | `CompletableFuture.join`/`FutureTask.get` | Async dependency chưa hoàn tất | Completion chain, pool starvation |
| Multiple threads BLOCKED cyclically | Có vòng sở hữu/chờ monitor/synchronizer | Deadlock | Deadlock detector và owner chain |
| Many threads in native code | JNI/VM internal frames | Native wait/CPU hoặc runtime work | Native profiler, crash logs |

Các nhóm trên là **giả thuyết**, không phải danh sách lỗi chắc chắn. Ví dụ `CompletableFuture.join` trong một worker có thể chỉ là việc được thiết kế; trở thành starvation khi pool tasks đang đợi công việc cũng cần pool đó để chạy.

### 13.4. Phân tích thread “kẹt lâu”

Một thread giống nhau theo Java ID/name/nid xuất hiện ở cùng frame tại t0, t1, t2 chưa đủ chứng minh *nó không chạy*: nó có thể lặp loop đến cùng phương thức rất nhiều lần. Cần xem cumulative CPU delta, application event counters, lock ownership, request/trace ID và operation progress.

Ngược lại, nếu thread chờ một monitor và owner giữ lock suốt nhiều dump, trong khi request latency tăng, đây là bằng chứng mạnh hơn của lock contention kéo dài.

## 14. Ba tình huống thực hành

### Case A — CPU cao: tìm đúng thread từ native ID

**Bối cảnh:** JVM process Linux PID `12345`. `top -H` báo TID `10815` dùng CPU đáng kể.

**Bước đọc:**

1. Tính `10815` = `0x2a3f`.
2. Trong dump cùng JVM và thời điểm gần đó, tìm `nid=0x2a3f`.
3. Đọc Java state và stack; giả sử top frames là `calculateScore`, `applyRules` trong code ứng dụng.
4. Thu thêm các sample theo thời gian hoặc JFR CPU profiling. Nếu cùng code frame liên tục và CPU time tăng, có cơ sở tìm hotspot/algorithmic complexity.
5. Kiểm tra số requests, data size, thread pool size, GC/JIT load trước khi tối ưu.

**Lỗi thường gặp:** tìm `tid=0x2a3f` hoặc Java `#10815` thay vì `nid`; đọc `RUNNABLE` rồi khẳng định một thread chiếm 100% CPU.

### Case B — Latency tăng: BLOCKED chờ monitor

**Bối cảnh:** 60 request threads có `java.lang.Thread.State: BLOCKED` và `- waiting to lock <0x0000000700a01111>`.

**Bước đọc:**

1. Tìm **owner** của cùng monitor ID trong dump.
2. Xem owner đang thực thi frame nào; giả sử nó đang sleep trong một method `synchronized`.
3. Xác minh owner vẫn giữ monitor qua một số dump; kiểm tra thời điểm latency tăng.
4. Kết luận vấn đề nằm ở critical section dài/giữ khóa khi sleep/I/O nếu stack và source hỗ trợ.
5. Sửa bằng thu nhỏ phạm vi monitor hoặc bỏ blocking operation ra ngoài critical section, theo logic ứng dụng; kiểm thử concurrency sau thay đổi.

**Lỗi thường gặp:** chỉ đổi số request threads hay restart pod, làm tạm thời biến mất symptom nhưng không giải quyết lock contention.

### Case C — WAITING hàng loạt: pool idle hay starvation?

**Bối cảnh:** 200 threads có state WAITING và stack gần `LockSupport.park`/`LinkedBlockingQueue.take`.

**Bước đọc:**

1. Kiểm tra chúng là worker idle của pool nào, hay đang chờ future/lock?
2. Đọc **caller frame**: `ThreadPoolExecutor.getTask` thường là lấy task; `CompletableFuture.join` trong request worker gợi ý chờ completion.
3. Đối chiếu active tasks, queue size, submitted/completed counters và request latency.
4. Với starvation, tìm xem tất cả worker có đang chờ kết quả của các tasks cũng cần chạy trong **chính pool bị chiếm hết** không.
5. Không tự gọi “deadlock” nếu không có chu trình locks/logic được chứng minh.

**Lỗi thường gặp:** đếm mọi WAITING là lỗi nghiêm trọng; tăng số thread vô hạn mà không phân tích dependency graph.

## 15. Những lỗi diễn giải hay gặp

1. **Nhầm `tid` với `nid`.** HotSpot `tid` là địa chỉ cấu trúc JVM; `nid` là native thread ID.
2. **Dùng `nid` để gọi `ThreadMXBean.getThreadInfo`.** API này nhận Java thread ID.
3. **Cho rằng thread name unique.** Tên có thể trùng, đổi và lặp qua các lần restart.
4. **Cho rằng `RUNNABLE` = 100% CPU.** Thread có thể đang trong native I/O wait.
5. **Cho rằng `WAITING` = deadlock.** Pool idle và `Object.wait` hợp lệ cũng WAITING.
6. **Cho rằng `BLOCKED` bao gồm mọi loại lock.** `ReentrantLock` có thể hiện WAITING/parking.
7. **Xem dòng đầu tiên trong stack là nguyên nhân gốc.** Nó chỉ là vị trí tại snapshot; cần caller/context.
8. **Đọc stack theo thứ tự ngược.** `Thread.run` gần cuối là entry point, không phải nhất thiết dòng đang chạy.
9. **Bỏ qua `- waiting to lock` và `- locked`.** Hai dòng này quan trọng khi tìm chủ sở hữu monitor.
10. **Quên vùng `Locked ownable synchronizers`.** Có thể bỏ sót ReentrantLock/AQS.
11. **Nhầm hex monitor ID với Java thread ID.** ID monitor đại diện object lock trong snapshot.
12. **So Linux TID giữa host và container không kiểm tra namespace.** Dẫn đến mapping sai.
13. **Kết luận từ một dump cách xa sự cố.** Thread có thể đã đổi công việc hoặc kết thúc.
14. **Lấy quá nhiều dump trên JVM tải cao.** `Thread.print` có overhead và có thể làm tăng latency.
15. **Giả định `jcmd -l` không thấy process nghĩa là process không chạy.** Có thể do namespace/permission.
16. **Tin `cpu=...` trên header là CPU% một giây qua.** Đây không mặc định là rate.
17. **Cộng CPU time nanoseconds với epoch milliseconds hoặc uptime.** Khác đơn vị và gốc đo.
18. **Đọc `Unknown Source` như lỗi ứng dụng chắc chắn.** Có thể chỉ thiếu debug line metadata.
19. **Bỏ qua JVM/GC/JIT/native internal threads.** Chúng cũng có thể tiêu thụ CPU/ảnh hưởng ứng dụng.
20. **Không phân biệt exception stack trace với thread dump.** Một cái ở mốc lỗi, một cái ở mốc snapshot.
21. **Dùng `Thread.dumpStack()` mong dump toàn bộ JVM.** Method đó in stack của thread hiện tại, không phải mọi thread.
22. **Bật contention monitoring/CPU time theo thread không đánh giá chi phí.** Có thể làm thay đổi trạng thái quản lý.
23. **Đăng nguyên dump chứa endpoint, token trong thread names hoặc file paths lên chat.** Có rủi ro tiết lộ thông tin.
24. **Xem nhiều thread cùng một frame là chắc chắn bug.** Có thể là trạng thái steady-state của pool.
25. **Không gắn JVM start/PID khi ghép dumps.** PID/Java ID có thể bị reuse, đặc biệt sau restart.

## 16. Checklist kiểm tra khi đọc một thread entry

- [ ] Dump lấy từ đúng **JVM instance**, PID/container namespace, có timestamp UTC?
- [ ] Tên thread có ý nghĩa gì và có thể trùng không?
- [ ] Có phân biệt Java ID/`#n`, HotSpot `tid` và native `nid`?
- [ ] Nếu nối với Linux `top -H`, đã đổi đúng `nid` hex sang decimal và kiểm tra thời điểm?
- [ ] Có phân biệt **Java enum state** với mô tả header/OS state?
- [ ] `RUNNABLE` có thể đang chờ native I/O, cần kiểm tra CPU time không?
- [ ] `BLOCKED` đang chờ monitor nào? Có tìm được holder?
- [ ] `WAITING`/`TIMED_WAITING` đến từ queue, lock, join, future, sleep hay request path?
- [ ] Stack frames được đọc từ trên xuống dưới; đã thấy user-code frame/caller liên quan?
- [ ] Có dòng `waiting to lock`, `locked`, `parking to wait for` hoặc ownable synchronizers?
- [ ] Thông tin stack/line có thể thiếu, JIT/native có ảnh hưởng khả năng quan sát?
- [ ] Có lý do cần dump thứ hai/thứ ba, JFR/metrics/GC logs để chứng minh giả thuyết?
- [ ] Đã phân biệt monitor deadlock, lock contention, starvation và I/O wait?
- [ ] Đã giới hạn quyền truy cập dump và tránh chia sẻ dữ liệu nhạy cảm?
- [ ] Kết luận chỉ phát biểu điều được chứng minh bởi snapshot(s), không đoán nguyên nhân?

## 17. Bài tập tự kiểm tra

**Bài tập 1 — Header.** Trong một mục HotSpot có `"worker-2" #17 tid=0x00007f0000201000 nid=0x2a3f runnable`, hãy chỉ ra tên, Java thread number, native thread ID hex, ID decimal trên Linux, và giá trị nào là pointer nội bộ. Đáp án: tên `worker-2`; `#17` là thread number/Java ID theo dạng HotSpot minh họa; `nid=0x2a3f` tương ứng **10815**; `tid=0x00007f...` là địa chỉ cấu trúc VM, **không** đưa vào `top -H`. Cần đối chiếu format JDK thực khi xử lý production.

**Bài tập 2 — State.** Một thread `RUNNABLE` có top frame `EPoll.wait(Native Method)`. Có thể kết luận thread gây CPU 100% không? **Không**: có thể đang đợi I/O ở native syscall; cần CPU counters/JFR và nhiều mẫu.

**Bài tập 3 — Monitor.** Thread A hiện `- locked <0xAAA>` và sleep; thread B hiện `- waiting to lock <0xAAA>`. Ai nhiều khả năng đang giữ monitor, và bước xác minh tiếp? A giữ monitor; kiểm tra frame `synchronized` của A, thời lượng giữ lock và sự lặp qua các dump; không chỉ tăng số threads.

**Bài tập 4 — WAITING.** Một trăm threads ở `ThreadPoolExecutor.getTask`/`LinkedBlockingQueue.take` có phải deadlock không? **Không mặc định**. Nếu pool rảnh, đó là bình thường. Cần xem active tasks, queue depth, request latency và owner/lock cycles.

**Bài tập 5 — Thread MXBean.** `ThreadInfo.getThreadId()` có thể dùng làm Linux LWP ID không? **Không bảo đảm**. Java ID khác native ID; cần mapping từ `nid` hoặc native tooling phù hợp.

**Bài tập 6 — Đọc theo thời gian.** Một thread xuất hiện ở cùng frame `calculate()` trong ba dumps cách 5 giây. Có chắc nó bị kẹt không? **Chưa**; có thể chạy loop nhanh qua cùng function. Cần CPU delta, progress counters và trạng thái lock/request context.

## Tài liệu tham khảo

- Oracle Java SE 17, [Diagnostic Tools](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): cấu trúc thread dump, header, `tid`, `nid`, `Thread.State` và ví dụ.
- Oracle Java SE 17, [`jcmd` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print -l`, quyền, tác động và hỗ trợ theo JVM.
- Oracle Java SE 17, [`jstack` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstack.html): stack trace và `-l`, giới hạn công cụ.
- Oracle Java SE 17, [`Thread.State` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): sáu enum states của Java 17 và khác biệt với trạng thái OS.
- Oracle Java SE 17, [`ThreadMXBean` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): Java thread IDs, stack traces, locks, deadlocks, CPU/contended time.
- Oracle Java SE 17, [`ThreadInfo` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): thread name, state, Java ID, lock owner, frame và đồng bộ.
- Oracle Java SE 17, [`StackTraceElement` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackTraceElement.html): tên class/method, source file/line, native method.
- Oracle Java SE 17, [`Thread` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `getName()`, `getId()`, `getState()`, `getStackTrace()`.
- OpenJDK Java Operations, [How to Obtain a Thread Dump on Linux](https://ops.java/howto/articles/thread-dump-linux/): `jstack`, `jcmd` và `SIGQUIT`.

**Kết luận:** đọc thread dump đúng là kết nối **tên + Java ID + native ID + trạng thái + stack frames + locks** trong đúng vòng đời JVM. Một snapshot cho biết vị trí quan sát tại một thời điểm, không trực tiếp cho nguyên nhân, phần trăm CPU hay thời gian chờ. Chỉ sau khi đối chiếu nhiều ảnh chụp với CPU/GC/thread metrics, tracing và OS/container context, bạn mới có thể phân biệt worker đang rảnh, I/O wait, lock contention, starvation hoặc CPU hotspot một cách có căn cứ.