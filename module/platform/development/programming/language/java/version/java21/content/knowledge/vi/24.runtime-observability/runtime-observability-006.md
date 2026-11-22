# Giới hạn của ThreadMXBean khi quan sát virtual thread

Trong Java 21, `ThreadMXBean` của `java.lang.management` chỉ cung cấp khả năng giám sát và quản lý **platform thread**. Các virtual thread không được tính vào các chỉ số thread của bean và không xuất hiện trong kết quả lấy thông tin thread qua API này.

Điều này rất quan trọng khi ứng dụng chuyển sang mô hình thread-per-task. Một dịch vụ có thể tạo hàng chục nghìn virtual thread nhưng `ThreadMXBean.getThreadCount()` vẫn chỉ phản ánh số platform thread đang sống, chẳng hạn các carrier thread và những platform thread khác. Không thể dùng số liệu này để suy ra số request hoặc virtual thread đang hoạt động.

## 1. ThreadMXBean quan sát được gì?

`ManagementFactory.getThreadMXBean()` trả về bean quản lý thông tin thread của JVM. Trong Java 21, các thao tác của bean chỉ áp dụng cho platform thread.

| API | Thông tin | Giới hạn với virtual thread |
|---|---|---|
| `getThreadCount()` | Số platform thread đang sống | Không phải tổng số platform thread và virtual thread cộng lại |
| `getPeakThreadCount()` | Số platform thread sống cao nhất kể từ khi JVM bắt đầu hoặc lần reset gần nhất | Không phản ánh peak virtual thread |
| `getTotalStartedThreadCount()` | Tổng số platform thread đã được khởi chạy | Không dùng để đếm số virtual thread đã tạo |
| `getAllThreadIds()` | ID của các platform thread có thể quan sát | Không trả về danh sách ID virtual thread |
| `getThreadInfo(...)` | Stack, trạng thái và thông tin lock của platform thread | Không lấy được ThreadInfo của virtual thread |
| `getThreadCpuTime(...)`, `getThreadUserTime(...)` | CPU time của platform thread nếu JVM hỗ trợ | Không cung cấp CPU time theo từng virtual thread |
| `findDeadlockedThreads()` | Phát hiện deadlock trong phạm vi platform thread mà bean quản lý | Không phải công cụ phát hiện đầy đủ deadlock liên quan virtual thread |

Vì vậy, dashboard chỉ hiển thị `ThreadCount` từ `ThreadMXBean` có thể cho thấy số thread gần như ổn định dù lượng virtual thread của ứng dụng tăng mạnh.

## 2. Ví dụ đọc số liệu ThreadMXBean

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public class PlatformThreadMetrics {
    public static void main(String[] args) {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();

        System.out.println("Live platform threads: "
                + bean.getThreadCount());
        System.out.println("Peak platform threads: "
                + bean.getPeakThreadCount());
        System.out.println("Started platform threads: "
                + bean.getTotalStartedThreadCount());

        long[] ids = bean.getAllThreadIds();
        ThreadInfo[] infos = bean.getThreadInfo(ids, 32);

        for (ThreadInfo info : infos) {
            if (info != null) {
                System.out.println(info.getThreadName()
                        + " / " + info.getThreadState());
            }
        }
    }
}
```

Các giá trị in ra là dữ liệu platform thread. Không diễn giải `getThreadCount()` là số tác vụ đồng thời của ứng dụng khi các tác vụ được chạy bằng virtual thread.

## 3. Vì sao ThreadMXBean không quản lý virtual thread?

Virtual thread được thiết kế để có thể tạo với số lượng rất lớn, thường một virtual thread cho mỗi tác vụ. Chúng được JVM lập lịch lên một tập platform thread nhỏ hơn gọi là carrier thread. Một virtual thread có thể unmount khi chờ I/O rồi được mount lại trên carrier khác.

ThreadMXBean được xây dựng quanh các thao tác quản lý thread truyền thống như liệt kê thread, lấy CPU time, đọc lock state và kiểm tra deadlock. Nếu mở rộng mọi thao tác này cho số lượng virtual thread rất lớn, chi phí thu thập và lưu trữ thông tin có thể trở nên không phù hợp với mô hình lightweight thread.

JEP 444 xác định giới hạn này: ThreadMXBean chỉ hỗ trợ platform thread. Đây là giới hạn thiết kế có chủ đích, không phải lỗi cấu hình của ứng dụng hoặc do bean chưa được bật.

## 4. Các API liệt kê thread khác cũng không thay thế được

Không nên thay `ThreadMXBean` bằng `Thread.getAllStackTraces()` để tìm tất cả virtual thread. Trong Java 21, API này cũng chỉ trả về stack trace của các live platform thread.

```java
import java.util.Map;

Map<Thread, StackTraceElement[]> traces = Thread.getAllStackTraces();
System.out.println("Threads in snapshot: " + traces.size());
```

Snapshot trên không phải danh sách đầy đủ các virtual thread đang chạy. Tương tự, các công cụ dựa trên thread group hoặc thread dump truyền thống không nên được giả định là có thể liệt kê đầy đủ virtual thread.

Không có API Java 21 công khai tương đương `ThreadMXBean.getAllThreadIds()` để lấy một danh sách toàn cục mọi virtual thread. Nên chọn công cụ quan sát được thiết kế cho virtual thread thay vì cố tạo một danh sách toàn cục trong ứng dụng.

## 5. Dùng Java Flight Recorder để quan sát vòng đời virtual thread

Java Flight Recorder (JFR) trong Java 21 có các event dành cho virtual thread, gồm:

- `jdk.VirtualThreadStart`: ghi nhận virtual thread bắt đầu.
- `jdk.VirtualThreadEnd`: ghi nhận virtual thread kết thúc.
- `jdk.VirtualThreadPinned`: ghi nhận trường hợp virtual thread bị pin vào carrier đủ điều kiện theo cấu hình event.
- `jdk.VirtualThreadSubmitFailed`: ghi nhận trường hợp scheduler không thể submit virtual thread để thực thi.

Các event này giúp quan sát vòng đời và vấn đề thực thi mà ThreadMXBean không cung cấp. Việc bật event start/end có thể tạo lượng dữ liệu lớn trong ứng dụng tạo rất nhiều virtual thread; chỉ bật trong khoảng thời gian và mức chi tiết phù hợp.

Khởi chạy ứng dụng cùng JFR recording:

```bash
java -XX:StartFlightRecording=filename=virtual-threads.jfr,settings=profile,dumponexit=true -jar app.jar
```

Xem thông tin tổng quan recording và các event virtual thread:

```bash
jfr summary virtual-threads.jfr
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed virtual-threads.jfr
```

Khi cần phân tích sâu, kiểm tra cấu hình event trong recording và bật những event cần thiết trước khi tái hiện vấn đề. Không giả định mọi event đều được bật trong mọi JFR configuration.

## 6. Dùng jcmd để tạo thread dump có virtual thread

JDK 21 bổ sung định dạng JSON cho thread dump để hỗ trợ số lượng lớn virtual thread. Có thể dùng `jcmd` của đúng JDK để ghi dump từ tiến trình đang chạy:

```bash
jcmd <pid> Thread.dump_to_file -format=json virtual-threads.json
```

Định dạng JSON được thiết kế để biểu diễn thread dump có nhiều virtual thread. Nó phù hợp hơn thread dump truyền thống khi cần kiểm tra một ứng dụng dùng virtual thread-per-task.

Thread dump là snapshot tại một thời điểm. Nó hữu ích để xem stack và trạng thái của các thread trong lúc điều tra, nhưng không thay thế metrics theo thời gian hoặc JFR recording. Khi số virtual thread rất lớn, file dump có thể lớn và cần được bảo vệ vì stack trace có thể chứa dữ liệu nhạy cảm.

Không suy luận rằng một thread không xuất hiện trong dump truyền thống thì thread đó chắc chắn không tồn tại. Chọn định dạng dump phù hợp với runtime và phiên bản JDK.

## 7. Quan sát pinning và carrier thông qua JFR

ThreadMXBean không cho biết virtual thread nào bị pin hoặc thời gian pinning. Với Java 21, JFR event `jdk.VirtualThreadPinned` là công cụ phù hợp để tìm stack trace liên quan đến pinning.

```bash
jfr print --events jdk.VirtualThreadPinned virtual-threads.jfr
```

Đối chiếu event với stack trace để xác định đoạn `synchronized`, native method hoặc foreign call có thể đang giữ carrier trong lúc blocking. Cần đọc kết quả theo đúng phiên bản runtime: hành vi monitor pinning của Java 21 đã được thay đổi từ JDK 24 qua JEP 491.

Không dùng `ThreadMXBean.getThreadCount()` để ước tính số carrier đang bị pin. Bean không cung cấp trạng thái pinning của virtual thread; dùng JFR và đo throughput/latency trong cùng khoảng thời gian.

## 8. Đo số tác vụ đang hoạt động ở tầng ứng dụng

Khi cần biết có bao nhiêu request hoặc task đang được xử lý, nên đo tại ranh giới nghiệp vụ. Ví dụ dùng `LongAdder` để đếm số task đang chạy:

```java
import java.util.concurrent.atomic.LongAdder;

final class TaskMetrics {
    private final LongAdder inFlight = new LongAdder();

    void run(Runnable task) {
        inFlight.increment();
        try {
            task.run();
        } finally {
            inFlight.decrement();
        }
    }

    long inFlightCount() {
        return inFlight.sum();
    }
}
```

Có thể đặt bộ đếm quanh mỗi request, job hoặc tác vụ gửi vào virtual-thread executor. Trong hệ thống thực tế, bổ sung counter cho tổng request, lỗi, timeout, cancellation và histogram cho latency.

Đo ở tầng ứng dụng phản ánh điều mà hệ thống thực sự quan tâm: số request đang xử lý, số task chờ một dịch vụ phụ thuộc, số request bị giới hạn bởi semaphore và thời gian hoàn tất. Đây là các chỉ số mà thread count không thể đại diện chính xác.

## 9. Tránh metrics có cardinality quá cao

Không nên tạo một time series riêng cho mỗi virtual thread ID hoặc thread name nếu ứng dụng có thể tạo hàng trăm nghìn hoặc hàng triệu thread. Điều đó làm hệ thống metrics tốn bộ nhớ, tăng chi phí lưu trữ và truy vấn.

Thay vào đó, gắn metrics với nhóm công việc hoặc endpoint:

- Số request đang chạy theo route hoặc loại job.
- Tổng request thành công/thất bại.
- Latency p50, p95, p99.
- Số lần timeout, retry và cancellation.
- Số tác vụ đang chờ semaphore, connection pool hoặc dịch vụ bên ngoài.
- Số sự kiện virtual-thread pinned quan sát được qua JFR.

Có thể ghi thread name có cấu trúc để hỗ trợ log và thread dump, nhưng không dùng thread name hoặc thread ID làm nhãn metrics không giới hạn.

## 10. Giám sát platform thread vẫn có ích

Giới hạn với virtual thread không làm ThreadMXBean trở nên vô dụng. Nó vẫn hữu ích để quan sát platform thread của JVM, bao gồm carrier thread và các thread nền khác:

- Theo dõi số platform thread sống và peak count.
- Kiểm tra stack trace của platform thread bị block hoặc chạy lâu.
- Quan sát CPU time của platform thread nếu JVM hỗ trợ.
- Kiểm tra lock contention và deadlock trong phạm vi platform thread mà bean quản lý.
- Kết hợp với GC, memory, CPU và JFR để tìm nguyên nhân nghẽn ở cấp JVM.

Chỉ cần ghi rõ phạm vi của từng chỉ số. Ví dụ, số platform thread ổn định không chứng minh ứng dụng không có hàng chục nghìn virtual thread đang chờ I/O.

## 11. Bảng chọn công cụ theo câu hỏi

| Câu hỏi cần trả lời | Công cụ phù hợp | Giới hạn cần nhớ |
|---|---|---|
| Có bao nhiêu platform thread đang sống? | `ThreadMXBean.getThreadCount()` | Không bao gồm virtual thread |
| Stack của platform thread nào đang block? | `ThreadMXBean.getThreadInfo()` | Không lấy stack virtual thread |
| CPU time của platform thread là bao nhiêu? | `getThreadCpuTime()` / `getThreadUserTime()` | Không có CPU time theo từng virtual thread |
| Virtual thread bắt đầu/kết thúc khi nào? | JFR `jdk.VirtualThreadStart` / `jdk.VirtualThreadEnd` | Cần cấu hình event và kiểm soát lượng dữ liệu |
| Virtual thread có bị pin không? | JFR `jdk.VirtualThreadPinned` | Đọc theo phiên bản JDK và event threshold/configuration |
| Stack của nhiều virtual thread tại một thời điểm? | `jcmd Thread.dump_to_file -format=json` | Snapshot có thể rất lớn; bảo vệ file dump |
| Có bao nhiêu request đang xử lý? | Metrics tại tầng ứng dụng | Phải instrument theo task/request |
| Latency và lỗi của từng loại công việc? | Application metrics, tracing và logs | Tránh cardinality không giới hạn |

## 12. Quy trình quan sát ứng dụng Java 21 dùng virtual thread

1. Dùng ThreadMXBean để theo dõi platform thread, CPU time và lock state trong đúng phạm vi hỗ trợ.
2. Thêm metrics tại tầng request/task để đếm in-flight work, latency, lỗi, timeout và cancellation.
3. Bật JFR recording khi cần điều tra vòng đời virtual thread, pinning hoặc scheduler submission failure.
4. Dùng `jcmd Thread.dump_to_file -format=json` khi cần snapshot thread dump có virtual thread.
5. Đối chiếu JFR, dump, application metrics, CPU, heap và GC log trong cùng khoảng thời gian.
6. Khi chạy trên JDK khác Java 21, kiểm tra tài liệu runtime vì một số hành vi và công cụ chẩn đoán có thể thay đổi.

Không dùng một chỉ số thread count duy nhất để đánh giá khả năng mở rộng của ứng dụng virtual thread. Kết hợp số liệu runtime với các chỉ số nghiệp vụ để xác định chính xác nơi tác vụ đang chờ.

## 13. Biên dịch và chạy với Java 21

`ThreadMXBean`, JFR, `jcmd` và Virtual Threads đều có thể dùng trong môi trường Java 21 mà không cần bật Preview.

```bash
javac --release 21 -d out src/PlatformThreadMetrics.java
java -cp out PlatformThreadMetrics

# Với tiến trình ứng dụng đang chạy:
jcmd <pid> Thread.dump_to_file -format=json virtual-threads.json
```

Đảm bảo dùng công cụ `jcmd` cùng JDK tương thích với tiến trình mục tiêu và có quyền attach phù hợp. `--release 21` chỉ kiểm soát compiler/API mục tiêu, không quyết định JDK đang chạy ứng dụng.

## 14. Tài liệu tham khảo

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [Java SE 21 API — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [Java SE 21 API — ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html)
- [Java SE 21 — jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Java SE 21 — Java Flight Recorder Event Reference](https://docs.oracle.com/en/java/javase/21/docs/specs/jfr/jfr-event-reference.html)
