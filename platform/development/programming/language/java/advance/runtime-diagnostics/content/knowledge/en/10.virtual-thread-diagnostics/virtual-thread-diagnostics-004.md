# 10.4. Giới hạn ThreadMXBean và các công cụ chỉ quan sát platform thread

## Mục tiêu học

Sau bài này, bạn có thể:

- Phân biệt **platform thread**, **virtual thread** và **carrier thread** khi đọc số liệu quan sát JVM.
- Giải thích vì sao `ThreadMXBean`, JMX và một số API/công cụ thread truyền thống không hiển thị toàn bộ virtual thread.
- Tránh kết luận sai về số request, trạng thái treo, CPU hoặc deadlock từ những số liệu chỉ dành cho platform thread.
- Chọn thread dump, JDK Flight Recorder (JFR), chỉ số ứng dụng và công cụ theo phiên bản JDK khi điều tra hệ thống sử dụng virtual thread.

**Phạm vi phiên bản:** Virtual thread chính thức xuất hiện từ **Java 21**. Các API và ví dụ chính dưới đây chạy với Java 21+. Tiện ích chẩn đoán ra đời ở JDK mới hơn được đánh dấu riêng.

## 1. Nguồn gốc giới hạn quan sát

**Platform thread** thường ánh xạ một-một với luồng hệ điều hành (OS thread). **Virtual thread** vẫn là một đối tượng `java.lang.Thread`, có ID riêng, nhưng JVM lập lịch nó trên các platform thread gọi là **carrier**. Khi virtual thread thực hiện thao tác blocking tương thích, nó có thể tạm ngừng (*unmount*) để carrier phục vụ virtual thread khác, rồi tiếp tục (*mount*) trên một carrier khi sẵn sàng.

Ba đại lượng khác nhau cần tách biệt:

1. **Số platform thread:** tập luồng hệ điều hành/JVM, bao gồm carrier và nhiều platform thread khác.
2. **Số virtual thread đang sống:** các tác vụ logic đang thực thi hoặc đang chờ; con số này có thể rất lớn.
3. **Số carrier đang bận:** các platform thread hiện được dùng để chạy virtual thread; không thể hiện mọi virtual thread đang unmount.

Ví dụ, một dịch vụ có hàng chục nghìn virtual thread đang chờ I/O nhưng `ThreadMXBean.getThreadCount()` chỉ trả vài chục. Điều này có thể hoàn toàn bình thường: phép đếm **chỉ gồm platform thread**. Không được kết luận dịch vụ chỉ có vài chục request đang hoạt động.

Virtual thread không giúp một phép tính CPU chạy nhanh hơn. Giá trị chủ yếu của nó là tăng khả năng xử lý đồng thời những tác vụ thường xuyên chờ I/O.

## 2. Hợp đồng thật sự của ThreadMXBean

`java.lang.management.ThreadMXBean` được lấy qua `ManagementFactory.getThreadMXBean()` hoặc JMX ObjectName `java.lang:type=Threading`. Theo Javadoc Java 21, MXBean này chỉ hỗ trợ giám sát và quản lý **platform thread**; virtual thread không thuộc phạm vi của nó.

| Nhóm phương thức | Dữ liệu phản ánh | Điều không được suy ra |
|---|---|---|
| `getThreadCount()`, `getPeakThreadCount()`, `getDaemonThreadCount()` | Số platform thread hiện tại, mức đỉnh và số daemon | Không phải số virtual thread hoặc request |
| `getTotalStartedThreadCount()` | Tổng platform thread đã được tạo và khởi động | Không phản ánh số virtual thread đã tạo |
| `getAllThreadIds()` | ID của các platform thread còn sống | Không liệt kê ID virtual thread |
| `getThreadInfo(id)`, `getThreadInfo(ids, ...)` | `ThreadInfo` của platform thread | Với ID virtual thread, trả `null`; thread đã chết hoặc không tồn tại cũng có thể cho `null` |
| `dumpAllThreads(...)` | Stack và thông tin đồng bộ của platform thread | Tên “All” không có nghĩa chứa toàn bộ virtual thread |
| `getThreadCpuTime(id)`, `getThreadUserTime(id)` | CPU của platform thread nếu được hỗ trợ/đã bật | Với ID virtual thread trả `-1`, không có nghĩa dùng 0 CPU |
| `getCurrentThreadCpuTime()`, `getCurrentThreadUserTime()` | CPU của thread hiện tại nếu là platform thread | Gọi từ virtual thread không trả CPU của riêng virtual thread (thường `-1` nếu JVM hỗ trợ phép đo) |
| `findMonitorDeadlockedThreads()`, `findDeadlockedThreads()` | Chu trình deadlock giữa các platform thread theo kiểu khóa API hỗ trợ | **Không phát hiện** chu trình có virtual thread |

Cần hiểu các chi tiết:

- `ThreadInfo` là mô hình snapshot của `ThreadMXBean`, không phải bản ghi của mọi `Thread` Java.
- `isThreadCpuTimeSupported()` và `isThreadCpuTimeEnabled()` chỉ mô tả khả năng/bật tắt đo CPU của **platform thread**. Bật tính năng không làm API hỗ trợ virtual thread.
- Tùy JVM và phương thức, thiếu khả năng đo CPU có thể dẫn đến `UnsupportedOperationException`; dữ liệu không hợp lệ hoặc không áp dụng có thể trả `-1`. Kiểm tra cả khả năng hỗ trợ lẫn giá trị nhận được.
- `findDeadlockedThreads() == null` chỉ là “không tìm thấy chu trình **trong phạm vi API**”, không chứng minh mọi virtual thread đều không kẹt.
- Lấy CPU/stack của **carrier** không phải lấy CPU/stack lịch sử của virtual thread mà carrier từng chạy. Virtual thread có thể đổi carrier và có thể unmount khi đang chờ.

## 3. Ví dụ Java 21+: một virtual thread sống nhưng “vắng mặt” trong MXBean

Ta tạo một platform thread và một virtual thread cùng chờ trên `CountDownLatch`. `ready` xác nhận hai tác vụ đã khởi động; `release` giữ chúng sống cho tới khi đo xong.

Tạo tệp **`ThreadMxBeanScopeDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;

public class ThreadMxBeanScopeDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        Runnable work = () -> {
            ready.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread platform = Thread.ofPlatform().name("platform-demo").start(work);
        Thread virtual = Thread.ofVirtual().name("virtual-demo").start(work);

        try {
            ready.await();
            ThreadMXBean bean = ManagementFactory.getThreadMXBean();
            long[] ids = bean.getAllThreadIds();

            System.out.println("platform.isVirtual=" + platform.isVirtual());
            System.out.println("virtual.isVirtual=" + virtual.isVirtual());
            System.out.println("MXBean has platform="
                    + Arrays.stream(ids).anyMatch(id -> id == platform.threadId()));
            System.out.println("MXBean has virtual="
                    + Arrays.stream(ids).anyMatch(id -> id == virtual.threadId()));
            System.out.println("ThreadInfo(platform) != null="
                    + (bean.getThreadInfo(platform.threadId()) != null));
            System.out.println("ThreadInfo(virtual) == null="
                    + (bean.getThreadInfo(virtual.threadId()) == null));
            System.out.println("getAllStackTraces has virtual="
                    + Thread.getAllStackTraces().containsKey(virtual));
        } finally {
            release.countDown();
            platform.join();
            virtual.join();
        }
    }
}
```

Biên dịch/chạy bằng JDK 21 trở lên:

```bash
javac ThreadMxBeanScopeDemo.java
java ThreadMxBeanScopeDemo
```

Đầu ra chính xác của ví dụ:

```text
platform.isVirtual=false
virtual.isVirtual=true
MXBean has platform=true
MXBean has virtual=false
ThreadInfo(platform) != null=true
ThreadInfo(virtual) == null=true
getAllStackTraces has virtual=false
```

**Giải thích:** cả hai `Thread` đều đang sống. `ThreadMXBean` nhìn thấy platform thread, nhưng không liệt kê ID của virtual thread và không trả `ThreadInfo` cho virtual thread. Dòng cuối xác nhận `Thread.getAllStackTraces()` cũng chỉ liệt kê platform thread. “Không có trong danh sách” thể hiện **giới hạn API**, không phải thread chưa khởi động hay đã chết.

Nếu đã có tham chiếu đến một virtual thread cụ thể, `virtual.getStackTrace()` có thể giúp đọc stack khi nó còn hoạt động. Phương thức đó **không** cung cấp cách liệt kê toàn bộ virtual thread của JVM và kết quả là ảnh chụp tại một thời điểm.

## 4. Công cụ nào chỉ nhìn platform thread, công cụ nào có hỗ trợ virtual thread?

| API / công cụ | Phạm vi quan sát | Sử dụng phù hợp |
|---|---|---|
| JMX `java.lang:type=Threading`, dashboard lấy số từ `ThreadMXBean` | Platform thread theo hợp đồng Java API | Đặt tên metric `platform_threads`, không gọi là tổng request hay tổng thread logic |
| `Thread.getAllStackTraces()`, `Thread.activeCount()`, `Thread.enumerate()`, `ThreadGroup.activeCount()/enumerate()` | Cơ chế liệt kê truyền thống không bao gồm virtual thread | Dùng khi cần tìm platform thread, không dùng đếm virtual thread |
| Công cụ OS như `top -H`, `ps -L` và native thread view | OS thread/carrier; không liệt kê từng virtual thread | Xem tải CPU và số OS thread, rồi đối chiếu dữ liệu JVM/ứng dụng |
| Thread dump HotSpot truyền thống, `jstack`, `jcmd <PID> Thread.print` | Chủ yếu platform thread; tùy phiên bản có thể thấy một số virtual thread **đang mount**, nhưng không bao quát virtual thread đã unmount | Phân tích carrier, native frame, stack và lock của platform thread |
| `jcmd <PID> Thread.dump_to_file` trên JDK hỗ trợ | Dump được thiết kế để quan sát virtual thread, xuất text/JSON | Ưu tiên khi cần stack virtual thread; kiểm tra mức bao phủ/chi tiết thực tế theo JDK |
| JDK Flight Recorder (JFR), JDK Mission Control | Event liên quan vòng đời, pinning hoặc lỗi lập lịch virtual thread | Điều tra theo dòng thời gian, phối hợp với dump/metrics |

**Lưu ý:** `Thread.dump_to_file` và dump HotSpot truyền thống không giống nhau. Tài liệu Java 21 mô tả `Thread.dump_to_file` có thể hiển thị virtual thread nhưng thiếu một số chi tiết địa chỉ, khóa, JNI và heap so với dump truyền thống. Các phiên bản JDK thay đổi cách trình bày/độ bao phủ dữ liệu, vì vậy không suy luận “không xuất hiện trong một file dump” thành “không tồn tại”. Kiểm tra `java -version` và `jcmd <PID> help` trước khi chẩn đoán.

## 5. Chẩn đoán hệ thống dùng virtual thread

### 5.1. Tác vụ đang chờ/hang: lấy dump có hỗ trợ virtual thread

Trên JDK 21+ hỗ trợ lệnh và với quyền truy cập JVM phù hợp:

```bash
jcmd -l
jcmd <PID> Thread.dump_to_file -format=text threads.txt
jcmd <PID> Thread.dump_to_file -format=json threads.json
```

Thay `<PID>` bằng PID thực. Hai lệnh dump là **hai định dạng lựa chọn**, không bắt buộc chạy cả hai. Text tiện đọc nhanh; JSON tiện công cụ phân tích. Tìm tên thread, trạng thái, stack tại chỗ chờ I/O, lock hoặc dependency. Nếu bản JDK không cung cấp đủ thông tin lock trong loại dump này, bổ sung dump truyền thống, JFR và dữ liệu ứng dụng.

Tên virtual thread nên mang ý nghĩa loại công việc (chẳng hạn prefix `http-request-`), đồng thời log/trace cần correlation ID nghiệp vụ. Thread ID không thay thế được request/trace ID, nhất là khi task đi qua nhiều dịch vụ.

### 5.2. Vấn đề theo thời gian: JFR

Những JFR event liên quan gồm:

- `jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd`: bắt đầu và kết thúc. Trên JDK 21 **tắt mặc định**; bật có chủ đích vì hệ thống có thể tạo rất nhiều virtual thread.
- `jdk.VirtualThreadPinned`: báo pinning vượt ngưỡng cấu hình; trên JDK 21 ngưỡng mặc định **20 ms**. Cơ chế pinning thay đổi ở một số bản JDK mới, cần đối chiếu phiên bản.
- `jdk.VirtualThreadSubmitFailed`: lỗi khởi động/đưa virtual thread trở lại lịch chạy, có thể liên quan tài nguyên.

Sau khi đã ghi được tệp `recording.jfr`, dùng:

```bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed recording.jfr
```

Event chỉ có khi cấu hình recording thu thập nó; **không có event** chưa đủ chứng minh không có vấn đề. Cần ghép với latency, timeout, I/O, pool kết nối và lỗi từ downstream.

### 5.3. Bổ sung metrics của tác vụ và scheduler

Khi ứng dụng xử lý request bằng virtual thread, các số nên đo từ **vòng đời tác vụ**: số request/task đang xử lý (tăng lúc bắt đầu, giảm trong `finally`), tốc độ bắt đầu/kết thúc, latency p95/p99, lỗi, timeout, mức chờ I/O và pool kết nối. Những số đó trả lời đúng câu hỏi “có bao nhiêu công việc” hơn `ThreadMXBean.getThreadCount()`.

**Từ JDK 24:** `jdk.management.VirtualThreadSchedulerMXBean` và các lệnh `jcmd Thread.vthread_scheduler`, `Thread.vthread_pollers` được giới thiệu để quan sát scheduler và I/O poller. MXBean có các số **ước lượng** như virtual thread đang mount, đang đợi lên lịch, pool size và parallelism. Chúng **không phải** bộ đếm tổng virtual thread đang sống, và không có sẵn trong Java 21. Không đưa các API/lệnh này vào chương trình yêu cầu biên dịch với JDK 21.

## 6. Tình huống thực tế và cách suy luận

**A. `threadCount = 45` nhưng có vài nghìn request đang chờ.**  
Kết luận sai: “chỉ 45 request hoạt động”. `threadCount` chỉ gồm platform thread; đối chiếu metric in-flight request, I/O và dump/JFR virtual-thread-aware.

**B. `getThreadInfo(virtualId) == null`.**  
Kết luận sai: “virtual thread đã chết”. API trả `null` cho ID virtual thread kể cả lúc thread còn sống. Khi có tham chiếu `Thread`, kiểm tra `isAlive()`/`getState()`; muốn điều tra toàn JVM, dùng công cụ hỗ trợ virtual thread.

**C. `getThreadCpuTime(virtualId) == -1`.**  
Kết luận sai: “thread dùng 0 ns CPU”. `-1` là không có dữ liệu hợp lệ qua API này. Dùng CPU JVM/process hoặc profiler có khả năng quan sát virtual thread; không gán toàn bộ CPU một carrier cho một virtual thread.

**D. `findDeadlockedThreads()` trả `null` nhưng dịch vụ vẫn treo.**  
Kết luận sai: “chắc chắn không deadlock”. API bỏ qua chu trình có virtual thread. Điều tra dependency chéo, điểm chờ lock/I/O, timeout, JFR và dump; mức chi tiết khóa tùy phiên bản JDK.

**E. `jstack` không thấy một virtual thread đã unmount.**  
Kết luận sai: “tác vụ không tồn tại”. Virtual thread đang chờ có thể không chiếm carrier. Sử dụng dump/JFR có hỗ trợ virtual thread, log và trace tương ứng.

## 7. Checklist thiết kế monitoring

1. Ghi rõ **đối tượng được đếm**. Metric từ `ThreadMXBean` là platform-thread metric.
2. Kiểm tra **phiên bản JDK** và năng lực của lệnh/API thực tế; nhất là scheduler MXBean từ JDK 24.
3. Phân biệt **0**, **`-1` / `null`** và **nằm ngoài phạm vi API**.
4. Theo dõi in-flight task, latency, timeout, lỗi và chờ downstream từ tầng ứng dụng.
5. Kết hợp stack/CPU carrier với virtual-thread dump, JFR và correlation ID.
6. Thu thập đủ để chẩn đoán nhưng cân nhắc overhead của dump lớn và JFR start/end event với số lượng tác vụ rất cao.

### Câu hỏi tự kiểm tra

- Vì sao `getThreadCount()` có thể rất nhỏ so với số virtual thread đang chờ I/O?
- Vì sao `getThreadInfo(virtualId) == null` không đủ để kết luận virtual thread đã kết thúc?
- Vì sao `getThreadCpuTime(virtualId) == -1` không có nghĩa là 0 CPU?
- Vì sao kết quả “không có deadlock” từ `ThreadMXBean` không loại trừ deadlock liên quan virtual thread?
- Nếu thread dump truyền thống và dump hỗ trợ virtual thread khác nhau, bạn sẽ phối hợp chúng với những metric/JFR event nào?

## Tài liệu chính thức

- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): hợp đồng platform-thread-only.
- [Java SE 21 — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `isVirtual()`, `threadId()`, `getAllStackTraces()`.
- [Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): carrier, JFR, thread dump.
- [Java SE 24 — VirtualThreadSchedulerMXBean](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.management/jdk/management/VirtualThreadSchedulerMXBean.html): chức năng scheduler từ Java 24.
