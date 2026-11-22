# 10.2. Vì sao số platform thread không đại diện cho tổng số virtual thread

Trong ứng dụng Java trước đây, người vận hành thường lấy số lượng thread từ `ThreadMXBean`, JConsole, `top -H` hoặc thread dump rồi suy luận mức độ đồng thời: “JVM chỉ có 80 threads thì chắc chỉ có khoảng 80 công việc đang chạy hoặc chờ.” Suy luận này **không đúng** khi ứng dụng sử dụng **virtual threads**.

Một JVM có thể có **hàng nghìn virtual threads đang sống, phần lớn chờ I/O**, nhưng chỉ cần một số lượng **platform carrier threads** tương đối nhỏ để thực thi đoạn mã Java khi các virtual threads sẵn sàng chạy. Ngược lại, platform thread count còn bao gồm HTTP workers, JVM service threads và các threads khác, không phải mọi platform thread đều là carrier. Vì vậy, **không tồn tại công thức đơn giản để đổi “số platform threads” thành “tổng số virtual threads”.**

Bài học này thuộc **10. Virtual thread**, tập trung đúng câu hỏi: **vì sao đếm platform threads không phản ánh tổng số virtual threads, và phải quan sát hai loại thread như thế nào để chẩn đoán chính xác?**

> **Yêu cầu phiên bản:** Virtual threads trở thành tính năng chính thức từ **JDK 21 (JEP 444)**. Các API `Thread.ofVirtual()`, `Thread.isVirtual()` và `Executors.newVirtualThreadPerTaskExecutor()` trong bài dùng **JDK 21+**, **không biên dịch trên Java 17**. Java 19/20 từng cung cấp virtual threads dưới dạng preview với điều kiện khác; không xem đó là API Java 17.

## 1. Hai loại Java thread, hai mô hình quản lý

Từ Java 21, một đối tượng `java.lang.Thread` có thể là **platform thread** hoặc **virtual thread**.

| Khía cạnh | Platform thread | Virtual thread |
| --- | --- | --- |
| Đơn vị Java | Một `Thread` | Một `Thread`, vẫn có identity/stack/exception |
| Ánh xạ OS | Thường gắn một OS thread trong suốt vòng đời | **Không** giữ một OS thread cố định cho toàn vòng đời |
| Ai lập lịch? | OS lập lịch OS thread | JVM lập lịch virtual thread lên platform **carrier**; OS lập lịch carrier |
| Khi chờ I/O được JDK hỗ trợ | Platform/OS thread có thể phải chờ | JVM thường **suspend/unmount** virtual thread, giải phóng carrier |
| Chi phí khởi tạo/stack | Tương đối cao, OS stack/tài nguyên native | Nhẹ hơn, stack có thể tăng/giảm theo nhu cầu |
| Phù hợp nhất | Tác vụ đa dạng, threads cần sống lâu | Rất nhiều tác vụ concurrent, chủ yếu **đợi I/O** |
| Số lượng thường dùng | Bị giới hạn thực tế bởi OS threads và tài nguyên | Có thể lớn hơn platform thread count nhiều lần |
| Khả năng tăng CPU | Không làm số core tăng | **Không** làm CPU work nhanh hơn hoặc tạo thêm cores |

Virtual thread không phải “thread giả” về mặt ngữ nghĩa chương trình. Nó là một `Thread` thật trong Java: có `Thread.currentThread()`, interrupt, `join`, `ThreadLocal`, stack trace, uncaught exception handler và các quy tắc đồng bộ phù hợp. Khác biệt chủ yếu nằm ở **cách JVM gắn việc thực thi đó với OS threads**.

### 1.1. Platform threads: thường một Java thread tương ứng một OS thread

Ví dụ truyền thống:

~~~java
Thread platform = Thread.ofPlatform()
        .name("platform-worker")
        .start(() -> doWork());
~~~

Đây là **đoạn minh họa, không phải chương trình độc lập**; `doWork()` là logic ứng dụng. Khi `platform-worker` tồn tại, nó thường chiếm một OS thread; khi gọi blocking I/O, thread đó có thể bị OS cho chờ, nhưng nền tảng OS thread vẫn gắn với platform thread.

Một thread pool dùng platform threads có thể giữ nhiều worker chờ task. Pool size 100 không có nghĩa đang xử lý 100 requests thành công: một số có thể idle, một số bị block và một số đang chạy.

### 1.2. Virtual threads: một Java thread không phải một OS thread

Ví dụ từ Java 21:

~~~java
Thread virtual = Thread.ofVirtual()
        .name("request-42")
        .start(() -> doWork());
~~~

Cũng là đoạn minh họa; JDK 21+ mới có `Thread.ofVirtual()`. Virtual thread có thể được **mount** lên một carrier platform thread khi cần thực thi, sau đó **unmount** khi chờ một hoạt động mà runtime hỗ trợ, để carrier chuyển sang chạy virtual thread khác.

`Thread.currentThread()` trong virtual thread trả về **virtual thread đó**, không phải carrier. Java code thường **không có API chuẩn để biết “carrier thread hiện tại của tôi là ai”**; không nên cố đồng nhất virtual-thread ID với OS/native thread ID.

## 2. Mount, unmount và carrier: lý do cốt lõi của chênh lệch số lượng

Mô hình khái niệm:

~~~text
JVM logical work:
  VT-1  ─── chạy ── chờ HTTP ─────────── resume ── kết thúc
  VT-2  ── chạy ── chờ DB ──────────────────────── resume
  VT-3  ───────────── chạy ── chờ queue ───────── resume
  VT-4  ───────────────────── chạy ── xong
  ...
  VT-1000 ── chờ I/O / timer / signal

JVM scheduler:
  carrier-P1 ── VT-1 ── VT-3 ── VT-41 ── ...
  carrier-P2 ── VT-2 ── VT-4 ── VT-19 ── ...
  carrier-P3 ── VT-8 ── VT-7 ── VT-55 ── ...
  ...

Operating system:
  các carrier-P* là các OS threads được OS lập lịch lên CPU cores
~~~

Sơ đồ **minh họa**, không khẳng định một virtual thread có affinity cố định với carrier. Một virtual thread có thể chạy trên **các carrier khác nhau ở những lần được lên lịch khác nhau**. Một carrier có thể phục vụ **nhiều** virtual threads theo thời gian.

**Mount:** JVM gắn execution của virtual thread đang sẵn sàng với một carrier. Code Java tiếp tục chạy trên OS thread mà carrier sử dụng.

**Unmount:** Khi virtual thread thực hiện một blocking operation hỗ trợ việc tạm dừng, JVM lưu trạng thái thực thi phù hợp và ngắt việc gắn carrier, để carrier có thể chạy virtual thread khác. Khi điều kiện hoàn tất, virtual thread trở lại trạng thái có thể được lập lịch.

**Parked/waiting virtual thread vẫn sống:** nó có thể chưa hoàn thành, đang đợi socket, `CountDownLatch`, sleep hoặc I/O, nhưng **không chiếm carrier trong toàn bộ khoảng chờ** nếu hoạt động đó được hỗ trợ unmount và không bị pinning.

Vì vậy cùng lúc có thể có:
- 2.000 virtual threads đang sống theo logic ứng dụng;
- phần lớn đang đợi remote I/O;
- vài chục platform threads trong JVM, bao gồm carrier và nhiều threads phục vụ mục đích khác;
- chỉ một số ít virtual threads thực sự chạy code tại một thời điểm.

Đây **không phải phép đo thực tế** và không có tỷ lệ mặc định “1 platform = 100 virtual”; tỷ lệ thay đổi theo tải, JDK, OS, kiểu chờ, scheduler, tài nguyên, cấu hình và mã ứng dụng.

### 2.1. Vì sao “virtual thread đang chờ” không làm OS thread count tăng từng chiếc?

Với platform thread truyền thống, mỗi thread chờ vẫn thường có OS thread tương ứng. Với virtual thread, một thao tác chờ I/O/timer được runtime hỗ trợ có thể làm virtual thread **unmounted**, nên OS thread cũ có thể phục vụ công việc khác. Có nhiều virtual threads “đang sống” nhưng chúng **không cùng chiếm OS threads**.

Không phải mọi chỗ chờ đều tự unmount. Có những tình huống **pinning** hoặc native/foreign blocking, thư viện không tương thích hoặc code CPU-bound khiến carrier bị chiếm lâu; chúng làm giảm khả năng mở rộng. Cần xét phiên bản JDK ở phần 9.

### 2.2. Vì sao số carrier cũng không bằng số virtual threads RUNNABLE?

Scheduler có chính sách parallelism, số processors và tình trạng hiện tại. Số carrier đang chạy có thể nhỏ hơn số virtual threads đang sẵn sàng, vì CPU cores hữu hạn. Số platform threads quan sát ở OS còn gồm compiler/GC/JVM service/background threads và platform threads riêng của ứng dụng.

Không thể dùng cách đếm platform threads rồi:
- trừ đi vài thread JVM để lấy số carrier;
- nhân với một hệ số để suy virtual count;
- coi số carrier là số requests đang xử lý;
- suy từ carrier count rằng không có queue hoặc không có blocking.

**Carrier count, virtual-live count, task-inflight count và số cores là các đại lượng khác nhau.**

## 3. Cần phân biệt bốn phép đếm thường bị trộn

| Đại lượng | Câu hỏi nó trả lời | Giới hạn |
| --- | --- | --- |
| **Live platform threads** | Bao nhiêu platform threads JVM hiện có? | Không bao gồm virtual threads |
| **Live virtual threads** | Bao nhiêu virtual `Thread` chưa kết thúc tại thời điểm đo? | Không nhất thiết bằng request đang chạy, CPU-bound hay đang mount |
| **Active/in-flight tasks hoặc requests** | Bao nhiêu công việc nghiệp vụ chưa hoàn thành? | Một request có thể dùng nhiều tasks/threads, hoặc không dùng thread riêng |
| **OS native threads** | Kernel có bao nhiêu threads của process? | Không liệt kê từng virtual thread không mount như OS thread |
| **Carrier pool size/parallelism** | Scheduler đang có bao nhiêu carrier hoặc nhắm mục tiêu chạy song song? | Không đếm total virtual threads và còn phụ thuộc version/config |

### 3.1. Ví dụ số học để thấy vì sao không thể quy đổi

Giả sử **mang tính minh họa**:
- 1.000 requests đã bắt đầu, mỗi request sử dụng một virtual thread.
- 950 virtual threads đang đợi I/O/timer; 50 virtual threads còn lại ở trạng thái sẵn sàng hoặc đang thực thi.
- JVM có 24 platform threads (bao gồm carriers, GC/compiler và background).

Bạn **không thể** suy số virtual threads là 24, cũng không thể nhân 24 với một hằng số để ra 1.000. Nếu request cũ hoàn tất và request mới bắt đầu, số virtual threads thay đổi độc lập với số platform threads trong một khoảng thời gian.

Ngay cả khi `platform_count=24` giữa hai snapshots, số virtual có thể từ 100 lên 5.000 rồi xuống 200 mà không có tăng tương xứng ở OS thread count. Điều đó có thể bình thường cho workload I/O-bound. Nhưng nếu 5.000 virtual threads đều chờ một dependency không hồi đáp, hệ thống có thể **nghẽn nghiêm trọng** dù carrier ít và CPU thấp.

### 3.2. Tổng “đã tạo từ lúc khởi động” khác “đang sống”

- **Started total** là bộ đếm tích lũy, chỉ tăng.
- **Live** là số đang tồn tại/chưa kết thúc, có thể tăng/giảm.
- **Runnable/scheduled** là số đang sẵn sàng hoặc đang chạy theo scheduler.
- **Mounted** là số đang gắn lên carrier ở một thời điểm.
- **Blocked/waiting** là trạng thái chờ; có thể unmount hoặc bị pin.

Nếu một service nhận 1 triệu requests/ngày, tổng số virtual threads đã tạo có thể 1 triệu, trong khi live tại bất kỳ snapshot nào chỉ vài nghìn. Không được trộn **total started** với **current live** khi so biểu đồ.

## 4. Điểm mù quan trọng của `ThreadMXBean`

Tài liệu **Java SE 21** quy định rõ `java.lang.management.ThreadMXBean` quản lý/giám sát **platform threads**, **không** hỗ trợ giám sát hoặc quản lý virtual threads. Điều này áp dụng ngay cả khi code tạo rất nhiều virtual threads.

| API Java Management | Ý nghĩa trong Java 21+ | Có đếm/liệt kê virtual threads không? |
| --- | --- | --- |
| `getThreadCount()` | Số **live platform threads** hiện tại | **Không** |
| `getPeakThreadCount()` | Đỉnh số live platform threads | **Không** |
| `getTotalStartedThreadCount()` | Tổng platform threads đã start từ lúc JVM khởi động | **Không** |
| `getDaemonThreadCount()` | Live daemon **platform threads** | **Không** |
| `getAllThreadIds()` | IDs của live **platform threads** | **Không** |
| `dumpAllThreads(...)` | Stack và lock info của các **platform threads** | **Không** |
| `getThreadInfo(virtualId)` | Tìm `ThreadInfo` theo Java ID | **`null`** với virtual thread |
| `findDeadlockedThreads()` | Tìm chu trình deadlock trong phạm vi các platform threads/synchronizers mà API hỗ trợ | **Không** bao quát mọi deadlock của virtual threads |

Đây không phải bug của MXBean hay dấu hiệu virtual threads chưa được khởi tạo. Đây là **phạm vi chính thức của API**. Vì vậy biểu đồ “JVM Thread Count” trên một hệ thống metrics dựa vào `java.lang:type=Threading` thường phản ánh **platform threads**; muốn biết tổng số virtual threads/requests cần instrument khác.

### 4.1. Code minh họa cách đọc đúng tên metric

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();

int platformLive = bean.getThreadCount();
int platformPeak = bean.getPeakThreadCount();
long platformStarted = bean.getTotalStartedThreadCount();
~~~

Đây là đoạn **minh họa**, cần imports `java.lang.management.ManagementFactory` và `ThreadMXBean`, không phải file Java độc lập. Đặt tên `platformLive` thay vì `allThreads` để ngăn nhầm phạm vi.

Nếu có một virtual thread `vt` đang sống:

~~~java
boolean isVirtual = vt.isVirtual();
long javaId = vt.threadId();
ThreadInfo missingFromMxBean = bean.getThreadInfo(javaId);
// missingFromMxBean == null cho virtual thread theo contract Java 21.
~~~

Đây cũng là đoạn minh họa, cần import `java.lang.management.ThreadInfo` và biến `vt`. Lưu ý `getThreadInfo(id) == null` còn có thể xảy ra nếu platform thread đã chết/ID không có; **không thể** dùng mỗi `null` để kết luận một ID lạ chắc là virtual thread. Trong ví dụ đã giữ tham chiếu `vt` và xác nhận `vt.isVirtual()`.

### 4.2. `ThreadGroup.activeCount()` cũng không giải quyết được

Trong Java 21, virtual threads thuộc nhóm thread đặc biệt nhưng **không được tính trong `ThreadGroup.activeCount()` và không được liệt kê bởi `ThreadGroup.enumerate()`**. Vì thế các mẹo cũ như lấy `Thread.activeCount()`/`ThreadGroup.enumerate` không trở thành bộ đếm virtual threads toàn JVM.

**Không suy số virtual thread** từ:
- `ThreadMXBean.getThreadCount()`;
- `Thread.activeCount()`/`ThreadGroup.activeCount()`;
- `ThreadGroup.enumerate(...)`;
- `ps -L`/`top -H` hoặc danh sách OS threads;
- thread dump truyền thống chỉ cho platform threads.

Mỗi công cụ có phạm vi riêng; một metric không đề cập virtual threads không nên được đặt tên `total_java_threads`.

## 5. Chương trình Java 21+ chạy độc lập: 200 virtual threads và phép đếm platform

Chương trình này cố ý tạo **200 virtual threads**; mỗi thread báo đã bắt đầu rồi **đợi một `CountDownLatch`** để còn sống trong thời gian main lấy mẫu. Chúng không chạy vòng CPU nóng và cũng không tạo 200 platform threads thủ công.

Trong lúc đó:
- `Thread.isVirtual()` xác nhận từng thread là virtual.
- `Thread.isAlive()` xác nhận số virtual threads trong tập **do demo giữ tham chiếu**.
- `ThreadMXBean.getThreadInfo(vt.threadId())` kiểm tra chính thức virtual threads **không có ThreadInfo qua MXBean**.
- `ThreadMXBean.getThreadCount()` đo **số platform threads**, được in trên **stderr** vì kết quả phụ thuộc JVM/OS.
- Cuối cùng `release.countDown()` cho threads kết thúc; main `join` để dọn dẹp.

**Đây chỉ là đếm 200 virtual threads do chương trình tạo**, không phải API để thống kê mọi virtual thread của toàn bộ JVM trong ứng dụng production.

Lưu tệp **VirtualVsPlatformCountDemo.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class VirtualVsPlatformCountDemo {
    private static final int TASKS = 200;

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        int platformBefore = bean.getThreadCount();

        CountDownLatch started = new CountDownLatch(TASKS);
        CountDownLatch release = new CountDownLatch(1);
        List<Thread> virtuals = new ArrayList<>(TASKS);

        try {
            for (int i = 0; i < TASKS; i++) {
                Thread vt = Thread.ofVirtual()
                        .name("demo-vt-" + i)
                        .start(() -> {
                            started.countDown();
                            try {
                                release.await();
                            } catch (InterruptedException ex) {
                                Thread.currentThread().interrupt();
                            }
                        });
                virtuals.add(vt);
            }

            if (!started.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Not all virtual threads started");
            }

            long alive = virtuals.stream()
                    .filter(Thread::isAlive).count();
            boolean allVirtual = virtuals.stream()
                    .allMatch(Thread::isVirtual);
            long exposedViaMxBean = virtuals.stream()
                    .filter(t -> bean.getThreadInfo(t.threadId()) != null)
                    .count();

            System.out.println("virtual_started=" + TASKS);
            System.out.println("virtual_alive=" + alive);
            System.out.println("all_virtual=" + allVirtual);
            System.out.println(
                    "virtual_entries_in_thread_mxbean=" + exposedViaMxBean);

            // Dynamic numbers: carrier and platform counts vary by runtime.
            int platformDuring = bean.getThreadCount();
            System.err.printf(
                    "platform_before=%d platform_during=%d%n",
                    platformBefore, platformDuring);
        } finally {
            release.countDown();
            for (Thread vt : virtuals) {
                vt.join();
            }
        }
    }
}
~~~

Biên dịch/chạy bằng **JDK 21 trở lên**:

~~~bash
java -version
javac VirtualVsPlatformCountDemo.java
java VirtualVsPlatformCountDemo
~~~

**Stdout chính xác khi chương trình chạy thành công trong điều kiện scheduling bình thường:**

~~~text
virtual_started=200
virtual_alive=200
all_virtual=true
virtual_entries_in_thread_mxbean=0
~~~

**Stderr có một dòng với các số phụ thuộc môi trường**, ví dụ **minh họa, không phải số cố định**:

~~~text
platform_before=7 platform_during=15
~~~

Bạn có thể nhận số lớn hơn hoặc nhỏ hơn; không cần và không được ép đúng `7` hay `15`. OS/JVM có thể có GC/compiler/background threads khác và scheduler có thể thay đổi số carriers. Hai dòng output trên hai stream stdout/stderr cũng có thể được terminal hiển thị xen kẽ theo thứ tự khác nhau.

**Giải thích kết quả:**
1. `started.await(...)` chỉ trở về thành công khi cả 200 virtual threads đã chạy tới `started.countDown()`. Chúng không thể kết thúc trước khi main release latch (trừ trường hợp tác động bên ngoài đặc biệt).
2. Vì `release` chưa được mở, cả 200 threads vẫn sống; `all_virtual=true` vì được tạo bằng `Thread.ofVirtual()`.
3. `virtual_entries_in_thread_mxbean=0` là **thiết kế API Java 21**: `ThreadMXBean` không quản lý virtual threads, dù các thread đó sống và có Java thread IDs.
4. `platform_during` là snapshot của **live platform threads**, không có nghĩa “chỉ có bao nhiêu requests” hay “đã chuyển 200 virtual thành bấy nhiêu OS threads”.
5. `release.countDown()` và `join()` giúp không để lại virtual threads treo sau khi demo kết thúc.

**Giới hạn và an toàn:** ví dụ tạo 200 tasks có giới hạn, không gây áp lực heap/CPU mạnh. Nếu JVM quá tải đến mức không start đủ virtual threads trong 15 giây, nó ném exception thay vì in bốn dòng trên. `join()` chờ virtual threads kết thúc; với demo chỉ đợi latch đã release, đây là cleanup hợp lệ. Production không nên tạo và giữ hàng triệu virtual threads tùy tiện vì **mỗi virtual thread vẫn dùng heap/stack/context và công việc phía sau vẫn dùng tài nguyên thật**.

### 5.1. Vì sao chỉ đếm `virtuals.size()` trong demo?

Ứng dụng tạo virtual threads nhưng không có API `ThreadMXBean` tương đương để liệt kê tất cả. Việc giữ `List<Thread>` cho 200 tasks chỉ phục vụ **demo** và có thể làm giữ tham chiếu lâu hơn cần thiết. Trong production, không nên giữ toàn bộ references vào từng virtual thread chỉ để tạo một counter; dùng **application metrics** có tăng/giảm đúng lifecycle, hoặc JFR/diagnostic snapshots khi cần điều tra.

### 5.2. Cách tạo virtual thread per task bằng executor

Cách thường dùng hơn cho workload Java 21:

~~~java
try (var executor = java.util.concurrent.Executors
        .newVirtualThreadPerTaskExecutor()) {
    var future = executor.submit(() ->
            Thread.currentThread().isVirtual());
    System.out.println(future.get()); // true trên Java 21+
}
~~~

Đây là **đoạn code minh họa trong một method có `throws Exception`**, không phải chương trình độc lập. Mỗi task được executor này thực thi bằng **một virtual thread mới**, không bằng “pool 200 virtual threads tái sử dụng”. `try-with-resources` đóng executor và đợi nhiệm vụ theo contract Java 21; không nên tạo một executor mới cho từng request trong production khi có thể quản lý lifecycle tập trung.

**Virtual threads không phải tài nguyên cần pooling theo kiểu platform threads.** Với nhu cầu chặn quá nhiều DB calls, đặt giới hạn ở **DB/HTTP/resource concurrency** (pool connections, semaphore, rate limit, bulkhead), không pool virtual threads để tiết kiệm số virtual threads rồi biến chúng thành bottleneck giả.

## 6. Vì sao thread dumps truyền thống nhìn thiếu virtual threads?

Công cụ quan sát cũng có “phạm vi” giống metrics. Ở các JDK có virtual threads:

| Nguồn quan sát | Thấy gì? | Điều không nên suy |
| --- | --- | --- |
| `ThreadMXBean.dumpAllThreads(...)` | Platform threads | Đây là toàn bộ virtual + platform |
| `jcmd PID Thread.print` / dump HotSpot truyền thống | Platform threads; trên JDK mới có thể hiện **mounted virtual threads** | Những virtual threads đang unmounted/waiting đều được liệt kê |
| `jcmd PID Thread.dump_to_file -format=json FILE` | Bản dump hỗ trợ **cả virtual và platform threads** | Là số đếm liên tục hoặc snapshot hoàn toàn nhất quán |
| `jcmd PID Thread.dump_to_file -format=text FILE` | Dump text hỗ trợ hai loại | Có mọi chi tiết native/monitor của dump truyền thống |
| `ps -L`, `top -H`, OS task list | Native/OS threads | Có một OS thread cho mỗi virtual thread |
| JFR virtual-thread events | Lifecycle và sự kiện hỗ trợ tùy config/JDK | Mọi event luôn bật, luôn đầy đủ hay miễn phí |
| App/trace metrics | Live/in-flight requests/tasks do ứng dụng instrument | Trùng 1:1 với mọi virtual threads trong JVM |

**Từ JDK 21**, công cụ `jcmd` có lệnh `Thread.dump_to_file` để tạo dump text/JSON có virtual threads. Bản dump này có các trường khác với dump HotSpot truyền thống; chi tiết locks/monitor và hình thức output **thay đổi theo JDK**. Vì vậy không nên tự lấy một bản `Thread.print` và khẳng định “chỉ có N Java threads”.

Ví dụ (PID và file là **giá trị minh họa**, cần quyền attach và đường dẫn đích hợp lệ):

~~~bash
jcmd -l
jcmd 12345 help Thread.dump_to_file
jcmd 12345 Thread.dump_to_file -format=json /tmp/threads.json
jcmd 12345 Thread.dump_to_file -format=text /tmp/threads.txt
~~~

Trên Windows, thay đường dẫn cho phù hợp. `Thread.dump_to_file` có thể ghi rất nhiều dữ liệu khi hàng chục nghìn virtual threads đang sống; cần đủ disk, đường dẫn không công khai, retention và kiểm soát tần suất. Nếu lệnh không có, kiểm tra **phiên bản JDK/công cụ** thực tế qua `jcmd 12345 help` thay vì suy tên tùy tiện.

**Chú ý khác biệt phiên bản:** trên JDK 21, `Thread.print` truyền thống không phải cách đáng tin để liệt kê mọi virtual thread; các JDK mới hơn có thể thể hiện virtual threads **đang mounted** trong HotSpot dump. Nhưng **unmounted virtual threads** không thể được suy đếm từ riêng danh sách OS/carrier threads.

### 6.1. Khi nào đọc JSON dump?

Với virtual-thread-per-task, JSON dump giúp:
- nhóm theo thread names/stacks và đường gọi nghiệp vụ;
- thấy nhiều virtual threads đợi ở cùng dependency/queue;
- tìm pattern của stalled work;
- đối chiếu timestamp và trace IDs từ logs;
- phân biệt pressure do nguồn I/O với scheduling/pinning.

**Không dùng một snapshot để khẳng định deadlock**, không kết luận mọi virtual threads trong snapshot đều chạy CPU. Các dump lớn có chi phí thu thập và xử lý; ưu tiên chỉ tạo khi có mục tiêu chẩn đoán rõ.

## 7. Instrument đúng: đo virtual tasks thay vì đo platform threads

### 7.1. Đặt tên metric đúng đối tượng

Một dashboard tốt nên tách các nhóm:

| Metric gợi ý | Ý nghĩa | Nguồn |
| --- | --- | --- |
| `jvm.platform.threads.live` | Live platform threads | `ThreadMXBean.getThreadCount()` |
| `app.virtual.tasks.started_total` | Task virtual đã bắt đầu (cumulative) | Counter ở application boundary |
| `app.virtual.tasks.completed_total` | Task virtual đã kết thúc | Counter increment trong `finally` |
| `app.virtual.tasks.inflight` | Task virtual đã bắt đầu nhưng chưa kết thúc | Gauge/counter lifecycle |
| `app.requests.inflight` | Requests nghiệp vụ chưa hoàn tất | Request lifecycle instrumentation |
| `app.requests.duration`, `timeout_total` | Latency và lỗi thật | Server/application telemetry |
| `dependency.connections.active/pending` | Áp lực DB/HTTP resources | Driver/client/pool metrics |
| `process.cpu`, `container.memory`, `gc.pauses` | Tài nguyên thật | JVM/OS/container metrics |

Tên trong bảng **mang tính khuyến nghị**, không phải auto-generated metrics có sẵn trong mọi framework. Phân biệt tasks với requests: một request có thể sinh nhiều virtual tasks hoặc một virtual thread có thể thực thi nhiều bước trong một request. Khi dùng executor per task, đếm **at submission**, **at start**, và **at completion** có thể khác nhau; phải xác định contract.

### 7.2. Ví dụ instrument task lifecycle

Đoạn sau **minh họa**, giả định có `executor`, `Runnable work`, `LongAdder started/completed` và `AtomicInteger inflight`:

~~~java
executor.submit(() -> {
    started.increment();
    inflight.incrementAndGet();
    try {
        work.run();
    } finally {
        completed.increment();
        inflight.decrementAndGet();
    }
});
~~~

Trong trường hợp **một virtual thread mới cho mỗi task** mà executor tạo, counter này đo công việc đã **bắt đầu chạy**, không đo các task mới submit nhưng chưa đến `Runnable`. Nó cũng không tính virtual threads do thư viện khác tạo ngoài wrapper. Nếu task bị reject trước khi Runnable chạy, counter `started` không tăng; metric `submitted/rejected` cần đo ở ranh giới submit riêng.

**Nguyên tắc đo:**
- Counter tổng số bắt đầu/kết thúc khác gauge hiện tại; không gộp chúng.
- `inflight` tăng ở đầu try/finally và giảm ở finally ngay cả khi có exception/cancellation được thực thi trong Runnable.
- Khi quá trình JVM bị kill, counter in-memory và future cleanup không đủ để tính kết quả bền vững; metrics cần hệ thống thu thập phù hợp.
- Đặt labels theo service/route/outcome có cardinality được kiểm soát; không đưa mỗi `threadId`/`requestId` thành một metric label.

### 7.3. Không có “virtual thread count toàn JVM” tự động từ `ThreadMXBean`

Nếu cần tổng live virtual thread **ở một thời điểm**, phương án thực tế là:
- instrumentation phạm vi ứng dụng (khi kiểm soát các điểm tạo);
- JFR lifecycle events được cấu hình có chủ đích nếu cần quan sát rộng hơn;
- `Thread.dump_to_file` snapshot khi điều tra;
- công cụ/APIs quản lý scheduler hoặc telemetry có hỗ trợ **đúng phiên bản JDK**.

Không tạo một thread registry giữ tham chiếu mạnh mãi mãi chỉ để đếm: sẽ làm tốn heap và cản GC. Cũng không ghi một log cho mỗi virtual-thread start/end ở tải lớn nếu có thể dùng metrics, vì hàng triệu log events có thể trở thành bottleneck.

## 8. Khi OS metrics và Java metrics có vẻ “mâu thuẫn”

### Tình huống A — CPU thấp, 10.000 virtual tasks in-flight

Nếu nhiều virtual threads đang chờ remote API, CPU vẫn có thể thấp và platform thread count ít. Nhưng hệ thống có thể **đang chịu sự cố latency**: request inflight, timeouts, connection pending và memory tăng. Chẩn đoán bằng traces/dependency metrics, không chỉ CPU và platform count.

### Tình huống B — Chỉ 32 platform threads nhưng throughput lớn

Với workload nhiều I/O waits ngắn, carrier được tái sử dụng giữa nhiều virtual threads, nên throughput có thể tốt dù platform count nhỏ hơn concurrency. Đây là lợi ích scalability, không phải “JVM quên đếm requests”.

### Tình huống C — 2.000 virtual threads RUNNABLE và CPU 100%

Virtual threads **không tự làm tác vụ CPU-bound nhanh hơn**. Với số core hữu hạn, nhiều virtual threads sẵn sàng chạy sẽ tranh scheduler/CPU; cần giới hạn concurrency của CPU work, tối ưu thuật toán, profiler/JFR. Tạo thêm virtual threads không tạo thêm CPU cores.

### Tình huống D — Virtual count tăng mãi trong khi platform count ổn định

Có thể là **resource leak/liveness issue**: rất nhiều virtual threads đang đợi một response không có timeout, connection pool hay latch không được hoàn tất. Platform count phẳng không chứng minh ứng dụng ổn định; cần đo request age, dependency timeouts, inflight virtual tasks, memory và dump virtual stacks.

### Tình huống E — Platform count tăng khi tải tăng

Không có nghĩa có từng platform cho mỗi virtual. Scheduler có thể điều chỉnh carrier availability hoặc runtime có các platform threads khác do GC, JIT, networking và app. Cần phân biệt nền tảng, thread names, stack và version trước khi kết luận pinning/cấu hình sai.

### Tình huống F — `ThreadMXBean.dumpAllThreads` thấy ít threads, `Thread.dump_to_file` rất lớn

Điều này **phù hợp với đặc tả**: MXBean chỉ trả platform threads, dump hỗ trợ virtual threads liệt kê thêm những virtual còn sống. Cần so **cùng PID/start time và snapshot time**, không coi hai công cụ sai vì số khác nhau.

## 9. Pinning và thay đổi theo phiên bản JDK

**Pinning** là trường hợp virtual thread không thể unmount khỏi carrier trong một blocking operation nhất định. Điều này có thể làm giảm scalability vì carrier bị giữ trong lúc virtual thread chờ.

**JDK 21–23:** tài liệu Java 21 nêu các tình huống pinning đáng chú ý:
- Virtual thread thực hiện blocking operation khi đang ở trong `synchronized` block/method.
- Virtual thread ở native/foreign function call.

Điều này **không làm code sai về kết quả**, nhưng nếu nhiều virtual threads pin carrier lâu, số carrier hữu dụng giảm và tasks khác bị chậm.

**Từ JDK 24 (JEP 491):** cơ chế monitor đã được cải tiến để **virtual thread có thể unmount khi blocking trong synchronized code**, loại bỏ nguyên nhân pinning phổ biến do Java monitor. **Native/foreign blocking vẫn cần xem xét**, và khả năng hành vi cụ thể phụ thuộc JDK build. Vì vậy không lặp vô điều kiện lời khuyên “mọi `synchronized` đều pin virtual threads” cho JDK 24+.

| Phiên bản | Điểm cần nhớ |
| --- | --- |
| Java 17 | Chưa có virtual threads API chính thức |
| Java 19/20 | Virtual threads ở giai đoạn preview (không phải mặc định như JDK 21) |
| Java 21 | Virtual threads chính thức; monitor pinning có thể ảnh hưởng khả năng unmount |
| Java 24+ | JEP 491 cải thiện `synchronized` không pin theo cơ chế cũ; vẫn phải kiểm tra native/foreign và runtime |
| Các bản mới hơn | Công cụ dump/JFR/scheduler diagnostics có thể thay đổi, đọc tài liệu đúng version |

### 9.1. Dấu hiệu nghi pinning hoặc scheduler pressure

- Throughput kém dù có rất nhiều virtual threads.
- Nhiều virtual threads cùng stack trong native/blocking path.
- Traces cho thấy dependency chậm; CPU không cao nhưng carrier bị giữ.
- JFR có events thích hợp, ví dụ trên JDK 21 `jdk.VirtualThreadPinned` khi vượt ngưỡng cấu hình, hoặc `jdk.VirtualThreadSubmitFailed`.
- Một số diagnostics `jcmd` cho virtual-thread scheduler/pollers chỉ khả dụng tùy JDK; kiểm tra qua `jcmd PID help`, không giả định JDK 21 có mọi command đời mới.

**Không coi việc không thấy pinned event là bằng chứng không có vấn đề**: events phải được hỗ trợ và bật, ngưỡng phải phù hợp; một dạng saturation có thể đến từ CPU, DB connections, bad timeout hoặc memory mà không liên quan pinning.

### 9.2. Virtual threads không loại bỏ mọi ràng buộc tài nguyên

Dù virtual threads rẻ hơn OS threads:
- Mỗi virtual thread vẫn dùng heap và có stack/context/ThreadLocal.
- Nhiều requests có thể gây **hàng nghìn DB connections pending**, làm nghẽn downstream.
- Các native calls, monitors tùy JDK, JDBC drivers hoặc frameworks có thể có bottleneck riêng.
- CPU-bound code không tăng tốc chỉ nhờ dùng nhiều virtual threads.
- Concurrency cần **backpressure/rate limit/bulkhead** tại resource thực tế.

**Đừng pool virtual threads để “kiềm chế số virtual”**: nếu mục tiêu là không có hơn 50 DB transactions đồng thời, giới hạn DB/transaction concurrency bằng semaphore/connection pool thay vì chỉ giữ 50 virtual workers. Virtual thread per task được thiết kế để tạo mới theo công việc.

## 10. JFR và dấu vết virtual-thread lifecycle

Java Flight Recorder (JFR) có các events liên quan virtual threads; trên JDK 21, tài liệu Oracle mô tả:
- `jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd`: lifecycle events, **mặc định không bật**.
- `jdk.VirtualThreadPinned`: thông báo pinning vượt threshold cấu hình, JDK 21 mặc định có ngưỡng 20 ms trong tài liệu.
- `jdk.VirtualThreadSubmitFailed`: JVM không thể schedule/start/unpark virtual thread đúng cách vì lý do tài nguyên.

Cấu hình và tính sẵn có thay đổi theo phiên bản. Khi events được thu:

~~~bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed recording.jfr
~~~

`recording.jfr` là tên file đã thu được, **không phải file được lệnh này tự tạo**. Không bật mọi start/end event trong production traffic cực lớn mà chưa tính event volume/overhead; ưu tiên mục đích chẩn đoán, sampling/retention phù hợp.

**Phạm vi dữ liệu:** JFR start/end cho thấy lifecycle, không đương nhiên tạo một “gauge live” chính xác nếu recording bắt đầu khi ứng dụng đã có virtual threads sống, hoặc bị mất/sampled events. Nếu cần live count chuẩn cho business scope, instrument từ trước tại các điểm tạo và kết thúc công việc.

## 11. Sai lầm phổ biến khi đếm platform và virtual threads

1. **“`ThreadMXBean.getThreadCount()` đếm tất cả Java threads.”** Trên Java 21+, nó chỉ đếm platform threads.
2. **“`getPeakThreadCount()` cho biết đỉnh số virtual threads.”** Đây vẫn là peak **platform** threads.
3. **“`getTotalStartedThreadCount()` kể cả virtual đã tạo.”** Không; đó là cumulative **platform** started count.
4. **“`getAllThreadIds()` liệt kê mọi `Thread` object.”** Virtual IDs bị loại khỏi MXBean result.
5. **“`getThreadInfo(id)==null` chứng minh thread không tồn tại.”** Có thể là ID của virtual thread đang sống.
6. **“`Thread.activeCount()`/`ThreadGroup.enumerate()` đầy đủ hơn MXBean.”** Chúng cũng không cung cấp tổng virtual threads.
7. **“OS có 32 threads nên chỉ 32 requests đồng thời.”** Hàng nghìn virtual tasks có thể đang sống và chờ I/O.
8. **“Có 10.000 virtual threads thì cần 10.000 CPU cores.”** Chờ I/O không dùng CPU liên tục, nhưng CPU work vẫn bị số core giới hạn.
9. **“1 virtual thread luôn cố định trên 1 carrier.”** JVM có thể remount lên carrier khác, không duy trì affinity.
10. **“Virtual thread chờ I/O luôn nhả carrier.”** Không tuyệt đối, cần xem pinning, native operations và JDK support.
11. **“`Thread.print` nhìn ít virtual nghĩa ứng dụng không tạo.”** Dump truyền thống có phạm vi khác `Thread.dump_to_file`.
12. **“Một snapshot virtual count là throughput.”** Live, started total, active tasks và completed requests là metrics khác.
13. **“Platform count tăng là bằng chứng virtual thread leak.”** Platform tăng có thể do nguồn khác; cần đúng attribution.
14. **“Platform count không đổi nghĩa không có leak.”** Virtual threads có thể chất đống ở waiting/latch/future.
15. **“Virtual threads là threads miễn phí.”** Có heap/stack, allocation, context và tài nguyên downstream.
16. **“Vì JDK 21 `synchronized` pin nên JDK 24+ cũng y như vậy.”** JEP 491 đã thay đổi cơ chế.
17. **“Bật JFR VirtualThreadStart/End cho mọi request là không có chi phí.”** Events có volume lớn, cần chính sách.
18. **“Thread ID có thể dùng làm metric label không giới hạn.”** Mỗi task có ID mới, cardinality sẽ bùng nổ.
19. **“Thấy ít carrier nên scheduler tốt.”** Có thể vẫn có latency, CPU starvation, pinning hoặc dependency quá tải.
20. **“Tăng virtual count là tăng thông lượng vô hạn.”** Cần giới hạn bởi CPU, network, DB, rate limits và backpressure.

## 12. Cách điều tra đúng khi số thread từ hai công cụ không khớp

Giả sử dashboard ghi `jvm_threads_live=38`, còn ứng dụng báo `virtual_tasks_inflight=4800`:

**Bước 1 — Xác minh nguồn của hai metric.** Nếu `jvm_threads_live` dùng `ThreadMXBean.getThreadCount`, tên đúng phải diễn đạt phạm vi **platform**. `virtual_tasks_inflight` có thể đếm application tasks, không phải mọi virtual threads.

**Bước 2 — Xác minh JVM và phiên bản.** Java 17 không có virtual-thread APIs chính thức, Java 21 trở lên có; đọc JVM vendor/build. Các cách dump và pinning thay đổi theo JDK.

**Bước 3 — Tìm workload.** 4.800 tasks đang chờ DB/HTTP, CPU work hay latch/future? Bao nhiêu request đã quá deadline? Nếu phần lớn chờ I/O và healthy, số virtual lớn có thể bình thường.

**Bước 4 — Lấy số liệu từ cùng khoảng thời gian.** Platform live (MXBean), app in-flight, DB connections pending, request p99, throughput, error rate, GC/heap, CPU. Đừng so một “peak” với một snapshot.

**Bước 5 — Thu dump có virtual threads nếu cần.** Dùng `jcmd PID Thread.dump_to_file -format=json` đúng JDK, path an toàn, đủ disk. Nhóm theo stack/dependency, không đọc file lớn bằng mắt từng dòng.

**Bước 6 — Kiểm tra scheduler/pinning theo version.** JFR và các commands hỗ trợ thực tế, OS CPU theo thread, pool saturation, native blocking. Không quy mọi hiện tượng cho carrier count.

**Bước 7 — Tìm bottleneck nghiệp vụ.** Metrics/trace cho biết requests kết thúc hay đứng. Một virtual thread chờ 1 ms trong I/O là bình thường; 4.800 virtual threads chờ 60 giây trên future không bao giờ complete là sự cố.

**Bước 8 — Khắc phục theo nguyên nhân.** Cải thiện deadline/cancellation, giới hạn resource concurrency, sửa blocking/native path, giảm ThreadLocal payload, giải quyết connection pool leak. Không cố “khớp” virtual count với platform count bằng cấu hình scheduler.

**Bước 9 — Đo sau sửa.** Request throughput, p95/p99, in-flight, oldest wait, memory/CPU và error rate mới là mục tiêu chính; tổng virtual threads không cần bằng tổng platform threads.

### Bảng bằng chứng và mức kết luận

| Quan sát | Có thể nói | Chưa thể nói |
| --- | --- | --- |
| MXBean báo 40 platform threads, app có 2.000 virtual tasks | Hai nguồn đo phạm vi khác nhau | 1.960 virtual threads bị “mất” |
| OS có 30 native threads | Process có khoảng đó OS threads tại snapshot | Chỉ có 30 Java logical threads |
| Virtual dump có 5.000 waiting | Nhiều logical threads còn sống và chờ | Chắc chắn deadlock hoặc chắc chắn khỏe |
| Virtual in-flight tăng, completions đứng | Công việc có dấu hiệu không tiến triển | Root cause chỉ là carrier thiếu |
| CPU 100%, nhiều virtual tasks ready | CPU có thể là bottleneck | Tăng số virtual threads sẽ tăng tốc |
| JFR pinned event xuất hiện trên JDK 21 | Có pinning vượt ngưỡng ở cấu hình recording | Mọi chậm trễ đều do pinning |
| JDK 24+ synchronized waits | Cơ chế JEP 491 khác JDK 21 | Mọi native blocking đều an toàn, không pin |

## 13. Checklist triển khai và giám sát

**Khi phát triển ứng dụng:**
- [ ] Dùng JDK 21+ khi chạy API virtual threads ổn định; kiểm tra phiên bản library/framework.
- [ ] Sử dụng virtual threads cho các tasks có nhiều waiting, đặc biệt synchronous I/O; không kỳ vọng chúng tăng tốc CPU-bound work.
- [ ] Dùng `Thread.ofVirtual()` hoặc `Executors.newVirtualThreadPerTaskExecutor()` theo lifecycle hợp lý.
- [ ] Không pool virtual threads như platform threads; giới hạn concurrency ở resource thật.
- [ ] Đặt timeout, cancellation, backpressure và error handling cho các waits.
- [ ] Không giữ ThreadLocal payload lớn trên hàng triệu virtual threads.
- [ ] Đọc cảnh báo pinning đúng JDK 21/24+; không áp đặt lời khuyên cũ cho version mới.

**Khi thiết kế observability:**
- [ ] Đặt tên metric `platform_thread_count` cho dữ liệu `ThreadMXBean`.
- [ ] Instrument virtual tasks started/completed/inflight với vòng đời chính xác.
- [ ] Phân biệt task started, submitted, currently alive và business requests in-flight.
- [ ] Thu latency, timeout, backlog, downstream saturation, CPU/GC/memory bên cạnh thread metrics.
- [ ] Dùng JFR events hoặc `Thread.dump_to_file` khi cần quan sát virtual threads.
- [ ] Giới hạn metric label cardinality và dung lượng dump/JFR.
- [ ] Không dùng OS thread list, `ThreadGroup.activeCount` hay `ThreadMXBean.dumpAllThreads` làm tổng virtual thread count.
- [ ] Kiểm tra logging/traces có correlation ID để nối từng virtual task với nghiệp vụ.
- [ ] Kiểm tra diagnostics JDK hỗ trợ thực sự trước khi đưa lệnh vào playbook.

**Khi thấy một biểu đồ “JVM thread count” thấp:**
- [ ] Nguồn là MXBean/platform-only hay app-specific virtual metrics?
- [ ] Có bao nhiêu virtual tasks đang sống và bao nhiêu requests đang inflight?
- [ ] Phần lớn virtual threads đang chờ I/O hợp lệ hay chờ dependency quá hạn?
- [ ] Số lượng completed requests có tăng, p99 có trong SLO không?
- [ ] Platform/cpu/GC/native resource có nghẽn không?
- [ ] Có pinning/native blocking hay queue saturation ở version JDK đó không?

**Ghi nhớ cuối:** Một platform thread thường là đơn vị OS thực thi; một virtual thread là **đơn vị công việc đồng thời do JVM quản lý** có thể mount/unmount trên nhiều carriers. `ThreadMXBean` và OS tools **đếm platform/native**, không đếm mọi virtual logical threads. Vì vậy, **số platform threads không đại diện cho tổng virtual threads** — cần theo dõi riêng application virtual tasks, tiến độ nghiệp vụ, resource metrics và dùng virtual-aware dump/JFR khi điều tra.

### Tài liệu tham khảo chính thức

1. Oracle Java SE 21, *Virtual Threads*: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
2. Oracle Java SE 21, *ThreadMXBean*: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html
3. Oracle Java SE 21, *ThreadGroup*: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadGroup.html
4. Oracle JDK 21, *jcmd*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
5. Oracle JDK 24, *Significant Changes in JDK 24* (JEP 491): https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html
6. OpenJDK, *JEP 444: Virtual Threads*: https://openjdk.org/jeps/444
7. OpenJDK, *JEP 491: Synchronize Virtual Threads without Pinning*: https://openjdk.org/jeps/491

Các con số trong ví dụ so sánh và stderr được đánh dấu **minh họa**, không phải cam kết về mọi OS/JVM. Luôn kiểm tra JDK version và phạm vi metric trước khi kết luận điều gì từ thread counts.