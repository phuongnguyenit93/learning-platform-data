# Phân biệt số virtual thread với số platform thread trong metrics

## Mục tiêu

Từ Java 21, ứng dụng có thể tạo rất nhiều virtual thread để xử lý các tác vụ blocking I/O. Khi quan sát runtime, số virtual thread có thể lớn hơn nhiều so với số platform thread. Hai con số này mô tả những đối tượng và tài nguyên khác nhau, vì vậy không thể dùng metric platform thread để suy ra số virtual thread đang hoạt động.

Java Management API `ThreadMXBean` cung cấp các số liệu về **platform thread**. Virtual thread cần được quan sát bằng các cách khác, chẳng hạn instrument task do ứng dụng sở hữu, Java Flight Recorder (JFR) và thread dump hỗ trợ virtual thread. Bài học này giải thích phạm vi của từng nguồn dữ liệu, cách tạo metric có ý nghĩa và cách tránh diễn giải sai số liệu trong production.

## 1. Platform thread và virtual thread là hai lớp khác nhau

Platform thread là thread được JVM ánh xạ trực tiếp với thread của hệ điều hành. Virtual thread là thread được JVM quản lý và được lập lịch chạy trên platform thread, thường gọi là *carrier thread*.

Khi virtual thread thực hiện thao tác blocking được hỗ trợ, JVM có thể tạm tháo virtual thread khỏi carrier. Carrier thread sau đó có thể chạy virtual thread khác. Khi thao tác chờ hoàn tất, virtual thread được lập lịch tiếp tục thực thi.

Vì vậy, tại một thời điểm:

- Một ứng dụng có thể có hàng chục nghìn virtual thread đang sống hoặc chờ I/O.
- Chỉ một số lượng nhỏ hơn platform thread/carrier thread được dùng để thực thi chúng.
- Nhiều virtual thread có thể lần lượt sử dụng cùng một carrier thread.
- Số platform thread không cho biết có bao nhiêu virtual thread đang chờ, đang chạy hoặc đã hoàn tất.

Ví dụ, một service có 12.000 virtual thread đang xử lý request không có nghĩa JVM phải tạo 12.000 OS thread. Ngược lại, thấy 80 platform thread cũng không có nghĩa ứng dụng chỉ có 80 tác vụ đồng thời.

Khi đọc metrics, cũng cần phân biệt ba trạng thái:

- **Live virtual thread:** đã được start và chưa kết thúc; bao gồm cả thread đang chờ I/O hoặc đang chờ đồng bộ.
- **Mounted virtual thread:** hiện đang chạy trên một carrier platform thread.
- **Unmounted virtual thread:** vẫn còn sống nhưng tạm thời không chiếm carrier, chẳng hạn đang chờ một thao tác blocking được hỗ trợ.

Vì vậy, số live virtual thread không phải số thread đang dùng CPU. Số mounted virtual thread tại một thời điểm cũng không phải tổng số virtual thread đang sống.

## 2. `ThreadMXBean` đo platform thread

`java.lang.management.ThreadMXBean` là nguồn metric tiêu chuẩn cho thread trong JVM. Các phương thức đếm thread của bean này đo **platform thread**, không đếm virtual thread như từng thread độc lập.

Các số liệu thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| `getThreadCount()` | Số platform thread đang sống |
| `getPeakThreadCount()` | Số platform thread sống cao nhất kể từ khi JVM khởi động hoặc lần reset peak gần nhất |
| `getTotalStartedThreadCount()` | Tổng số platform thread đã được tạo và khởi chạy kể từ khi JVM khởi động |
| `getDaemonThreadCount()` | Số platform thread daemon đang sống |

Có thể đọc các số liệu này bằng `ManagementFactory`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

class PlatformThreadMetrics {
    public static void main(String[] args) {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();

        System.out.println("Live platform threads: " + bean.getThreadCount());
        System.out.println("Peak platform threads: " + bean.getPeakThreadCount());
        System.out.println("Total started platform threads: "
                + bean.getTotalStartedThreadCount());
        System.out.println("Live daemon platform threads: "
                + bean.getDaemonThreadCount());
    }
}
```

Các giá trị trên hữu ích để theo dõi worker pool, carrier và các thread hệ thống của JVM. Tuy nhiên, `getThreadCount()` không phải số lượng virtual thread đang sống và `getTotalStartedThreadCount()` không phải tổng số virtual thread đã được tạo.

## 3. Carrier thread cũng là platform thread

Virtual thread chạy trên carrier platform thread. Vì carrier là platform thread, chúng thuộc phạm vi đếm platform thread của `ThreadMXBean` khi đang sống. Nhưng `ThreadMXBean` không cung cấp một bộ đếm riêng cho biết trong tổng platform thread có bao nhiêu thread là carrier của virtual-thread scheduler.

Tổng platform thread của JVM còn có thể bao gồm:

- Platform thread do ứng dụng tự tạo.
- Worker thread của executor dùng platform thread.
- Carrier thread của virtual-thread scheduler.
- Thread phục vụ GC, JIT compiler, service và các hoạt động nội bộ khác của JVM.

Vì vậy, không lấy `getThreadCount()` làm số carrier thread. Nếu cần hiểu scheduler, phải kết hợp cấu hình scheduler, thread dump, JFR và dữ liệu runtime tương ứng.

Hai system property thường liên quan đến virtual-thread scheduler là:

| Property | Ý nghĩa |
|---|---|
| `jdk.virtualThreadScheduler.parallelism` | Mức parallelism mục tiêu của scheduler, tức số carrier thread được duy trì để thực thi virtual thread |
| `jdk.virtualThreadScheduler.maxPoolSize` | Giới hạn trên của số platform thread mà scheduler có thể dùng |

Các property này điều chỉnh scheduler, không đặt giới hạn tổng số virtual thread hoặc số task ứng dụng được phép submit. Không suy ra số virtual thread đang sống từ giá trị `parallelism`.

## 4. Không dùng API đếm platform thread để đếm virtual thread

Một số API thread quen thuộc có phạm vi platform thread. Khi đọc metric hoặc viết công cụ quan sát, cần hiểu chính xác phạm vi của API:

| API | Phạm vi quan sát trong Java 21 |
|---|---|
| `ThreadMXBean.getThreadCount()` | Platform thread đang sống |
| `ThreadMXBean.getPeakThreadCount()` | Peak platform thread |
| `ThreadMXBean.getTotalStartedThreadCount()` | Tổng platform thread đã start |
| `Thread.getAllStackTraces()` | Stack trace của các platform thread đang sống; không phải danh sách toàn bộ virtual thread |
| `Thread.activeCount()` | Thread trong thread group hiện tại và các group con; không phải bộ đếm virtual thread toàn JVM |
| `Thread.currentThread().isVirtual()` | Kiểm tra thread hiện tại có phải virtual thread hay không |

Ví dụ sau chỉ kiểm tra loại thread đang chạy đoạn code:

```java
class CurrentThreadKind {
    static void report() {
        Thread current = Thread.currentThread();
        System.out.println("Name: " + current.getName());
        System.out.println("Virtual: " + current.isVirtual());
    }
}
```

`isVirtual()` hữu ích khi log hoặc instrument một task cụ thể. Nó không cung cấp phép đếm toàn cục. Không nên gọi `Thread.getAllStackTraces()` hoặc duyệt thread group rồi coi kết quả là tổng virtual thread.

## 5. Metric platform thread từ JMX và thư viện metrics

Các hệ thống monitoring thường lấy metric thread từ `ThreadMXBean` thông qua JMX hoặc thư viện như Micrometer. Những metric có tên gần giống `jvm.threads.live`, `jvm.threads.peak` hoặc `jvm.threads.started.total` thường phản ánh số liệu platform thread nếu nguồn là `ThreadMXBean`.

Không chỉ dựa vào tên metric. Hãy kiểm tra tài liệu hoặc implementation của exporter để xác định:

- Metric lấy từ `ThreadMXBean` hay được instrument từ application task.
- Giá trị là gauge (số hiện tại), counter (tổng tích lũy) hay peak.
- Có bao gồm virtual thread hay không.
- Có bao gồm daemon thread và JVM internal thread hay không.
- Metric được lấy theo chu kỳ nào và có thể bỏ qua biến động ngắn hạn không.

Trong dashboard, nên ghi rõ scope, ví dụ `platform_threads_live` thay vì một tên mơ hồ như `threads`. Nếu metric framework chỉ xuất metric platform thread, đừng đổi nhãn của nó thành `virtual_threads` bằng cấu hình dashboard.

## 6. Instrument số task chạy trên virtual thread ở tầng ứng dụng

Java 21 không cung cấp một `ThreadMXBean` tương đương để lấy trực tiếp gauge toàn JVM về số virtual thread đang sống. Với workload do ứng dụng tạo bằng executor, có thể instrument vòng đời task để đo số task đang thực thi.

Ví dụ dùng `LongAdder` và `AtomicLong`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

class VirtualTaskMetrics {
    private static final LongAdder started = new LongAdder();
    private static final LongAdder completed = new LongAdder();
    private static final LongAdder failed = new LongAdder();
    private static final AtomicLong active = new AtomicLong();
    private static final AtomicLong peakActive = new AtomicLong();

    static <T> Callable<T> instrument(Callable<T> task) {
        return () -> {
            started.increment();
            long current = active.incrementAndGet();
            peakActive.accumulateAndGet(current, Math::max);

            try {
                return task.call();
            } catch (Exception | Error e) {
                failed.increment();
                throw e;
            } finally {
                active.decrementAndGet();
                completed.increment();
            }
        };
    }

    static long startedTotal() {
        return started.sum();
    }

    static long completedTotal() {
        return completed.sum();
    }

    static long failedTotal() {
        return failed.sum();
    }

    static long activeTasks() {
        return active.get();
    }

    static long peakActiveTasks() {
        return peakActive.get();
    }
}
```

Wrapper trên đo các task đã bắt đầu chạy qua `instrument()`, không đo mọi virtual thread trong JVM. Nếu ứng dụng có nhiều nguồn tạo virtual thread, cần instrument ở các ranh giới tương ứng hoặc dùng JFR để quan sát rộng hơn.

`active` là gauge của task đang nằm trong thân callable. `started`, `completed` và `failed` là counter tích lũy. `peakActive` giữ giá trị đồng thời cao nhất kể từ khi ứng dụng khởi động. Trong ví dụ, `failed` đếm exception thoát khỏi callable; một task bị đánh dấu cancelled trước khi bắt đầu sẽ không chạy wrapper và không làm tăng `started` hoặc `completed`.

Nếu cần phân biệt cancellation, timeout và lỗi nghiệp vụ, hãy instrument các trạng thái đó ở tầng quản lý `Future` hoặc request. Không suy ra số task đã thực sự dừng chỉ từ việc `Future.cancel(true)` trả về thành công; task có thể chưa phản ứng với interrupt.

## 7. Kết hợp instrument với virtual-thread-per-task executor

Một executor tạo virtual thread cho mỗi task có thể bọc công việc trước khi submit:

```java
import java.util.concurrent.Executors;

class InstrumentedVirtualExecutor {
    public static void main(String[] args) {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < 100; i++) {
                int taskId = i;
                executor.submit(VirtualTaskMetrics.instrument(() -> {
                    process(taskId);
                    return null;
                }));
            }
        }

        System.out.println("Started: " + VirtualTaskMetrics.startedTotal());
        System.out.println("Completed: " + VirtualTaskMetrics.completedTotal());
        System.out.println("Failed: " + VirtualTaskMetrics.failedTotal());
        System.out.println("Peak active: " + VirtualTaskMetrics.peakActiveTasks());
    }

    private static void process(int taskId) throws InterruptedException {
        Thread.sleep(50);
    }
}
```

Ví dụ minh họa metric của các task do executor này sở hữu. `activeTasks()` có thể được export định kỳ dưới dạng gauge trong lúc tải đang chạy; sau khi executor đóng và toàn bộ task kết thúc, giá trị thường trở về 0.

Lưu ý rằng executor đóng trong try-with-resources sẽ chờ task hoàn tất. Nếu muốn dashboard quan sát trong lúc chạy, hãy export metric qua registry hoặc endpoint metrics của ứng dụng thay vì chỉ in số liệu sau khi executor đóng.

## 8. Những giới hạn của application-level task metrics

Metric do ứng dụng instrument có ý nghĩa rõ ràng nhưng không đồng nhất với tổng virtual thread toàn JVM:

- Chỉ đếm task được bọc bởi instrumentation.
- Không tự đếm virtual thread do framework, thư viện hoặc thành phần khác tạo.
- Task đã submit nhưng chưa bắt đầu cần metric riêng nếu muốn đo số công việc chờ.
- Task bị cancel trước khi wrapper chạy sẽ không xuất hiện trong `started`/`completed`.
- Task đã nhận cancellation nhưng bỏ qua interrupt vẫn có thể còn hoạt động.
- Một virtual thread có thể chạy nhiều đoạn code trong cùng task; số task active không phải số thread đang mounted trên carrier.

Vì thế, nên đặt tên metric theo đúng đối tượng đo, chẳng hạn `application_virtual_tasks_active`, thay vì khẳng định đó là tổng `jvm_virtual_threads_live`.

## 9. Dùng JFR để quan sát vòng đời virtual thread

Java Flight Recorder có các event phục vụ quan sát virtual thread, trong đó:

| JFR event | Ý nghĩa |
|---|---|
| `jdk.VirtualThreadStart` | Virtual thread bắt đầu |
| `jdk.VirtualThreadEnd` | Virtual thread kết thúc |
| `jdk.VirtualThreadPinned` | Virtual thread bị pin vào carrier trong một khoảng thời gian |
| `jdk.VirtualThreadSubmitFailed` | Scheduler không thể submit virtual thread để thực thi |

Event start/end hữu ích để phân tích số lượng thread được tạo và kết thúc trong recording. Event pinned giúp điều tra trường hợp virtual thread không thể nhường carrier theo cơ chế bình thường. Event submit failed là tín hiệu cần điều tra scheduler hoặc áp lực tài nguyên.

Có thể bật các event bằng API JFR:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Recording;

class VirtualThreadRecording {
    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording()) {
            recording.enable("jdk.VirtualThreadStart");
            recording.enable("jdk.VirtualThreadEnd");
            recording.enable("jdk.VirtualThreadPinned")
                    .withThreshold(Duration.ofMillis(20));
            recording.enable("jdk.VirtualThreadSubmitFailed");

            recording.start();
            runWorkload();
            recording.stop();
            recording.dump(Path.of("virtual-threads.jfr"));
        }
    }

    private static void runWorkload() throws InterruptedException {
        try (var executor = java.util.concurrent.Executors
                .newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < 100; i++) {
                executor.submit(() -> {
                    Thread.sleep(100);
                    return null;
                });
            }
        }
    }
}
```

Các event start/end cho phép phân tích vòng đời trong khoảng recording. Tuy nhiên, chênh lệch giữa số start và end trong một recording bất kỳ không tự động bằng số virtual thread đang sống tại thời điểm kết thúc: có thể có thread được tạo trước khi recording bắt đầu hoặc kết thúc sau khi recording dừng.

Để tính live count từ event, cần một cửa sổ quan sát có baseline hợp lệ hoặc theo dõi đầy đủ vòng đời từ lúc bắt đầu. Với dashboard liên tục, application-level gauge thường phù hợp hơn cho task do ứng dụng quản lý; JFR phù hợp hơn cho điều tra chi tiết và đối chiếu hành vi runtime.

## 10. Kiểm tra thread dump có virtual thread

Thread dump truyền thống và các API đếm thread không phải lúc nào cũng thể hiện virtual thread. Trên JDK 21, dùng lệnh `jcmd` `Thread.dump_to_file` để tạo thread dump hỗ trợ virtual thread:

```bash
jcmd <pid> Thread.dump_to_file -format=json virtual-threads.json
```

Thay `<pid>` bằng process ID của JVM cần kiểm tra. Định dạng JSON hữu ích khi cần phân tích bằng công cụ hoặc script. Thread dump là snapshot phục vụ chẩn đoán, không phải metric liên tục; tạo dump quá thường xuyên hoặc dump rất lớn cũng có chi phí I/O và xử lý.

Khi điều tra, kết hợp thread dump với JFR và application metrics để trả lời:

- Có bao nhiêu virtual thread đang chờ hoặc đang thực thi tại thời điểm snapshot?
- Chúng đang chờ I/O, monitor, semaphore hay một dependency nào?
- Carrier/platform thread có đang bận, bị pin hoặc thiếu khả năng lập lịch không?
- Số task active có tương ứng với số request đang được xử lý không?

Không dùng một thread dump đơn lẻ để kết luận xu hướng dài hạn. Hãy lấy snapshot tại các thời điểm có tải bình thường và khi latency tăng để so sánh.

## 11. Quan sát pinning và scheduler pressure trên Java 21

Trên Java 21, một virtual thread có thể bị pin vào carrier trong một số tình huống, chẳng hạn blocking khi đang giữ monitor của `synchronized` hoặc khi thực hiện một số native/foreign call. Khi bị pin, virtual thread không thể nhường carrier như trường hợp blocking I/O thông thường.

JFR event `jdk.VirtualThreadPinned` giúp tìm các khoảng pin đủ dài theo threshold đã cấu hình. Khi điều tra, xem stack trace và call path để xác định đoạn code gây pinning; sau đó đánh giá có thể thu hẹp vùng `synchronized`, tránh blocking khi giữ monitor hoặc thay đổi cách gọi native hay không.

Đây là lưu ý theo phiên bản: JDK 24 đã thay đổi hành vi monitor để virtual thread không còn bị pin chỉ vì blocking trong `synchronized` như ở Java 21. Vì bài học thuộc runtime Java 21, cần giữ phân biệt này khi đọc dữ liệu; không áp dụng kết luận pinning của Java 21 cho mọi JDK mới hơn. Native/foreign code và các nguyên nhân pinning khác vẫn cần được đánh giá theo đúng phiên bản.

Không kết luận scheduler bị thiếu carrier chỉ vì số virtual thread lớn. Hãy kiểm tra event pinning, submit failure, CPU saturation, blocking call path và thời gian chờ thực tế. Số virtual thread đang sống cao có thể là trạng thái bình thường của một ứng dụng I/O-bound.

## 12. Thiết kế dashboard với metric có phạm vi rõ ràng

Một dashboard hữu ích nên tách metric platform thread khỏi metric task/virtual thread. Ví dụ:

| Metric gợi ý | Loại | Nguồn | Diễn giải |
|---|---|---|---|
| `jvm_platform_threads_live` | Gauge | `ThreadMXBean.getThreadCount()` | Platform thread đang sống |
| `jvm_platform_threads_peak` | Gauge | `ThreadMXBean.getPeakThreadCount()` | Peak platform thread |
| `jvm_platform_threads_started_total` | Counter | `ThreadMXBean.getTotalStartedThreadCount()` | Tổng platform thread đã start |
| `app_virtual_tasks_active` | Gauge | Application instrumentation | Task đã bắt đầu và chưa kết thúc trong phạm vi được instrument |
| `app_virtual_tasks_started_total` | Counter | Application instrumentation | Task được instrument đã bắt đầu |
| `app_virtual_tasks_completed_total` | Counter | Application instrumentation | Task được instrument đã thoát wrapper |
| `app_virtual_tasks_failed_total` | Counter | Application instrumentation | Task kết thúc bằng exception trong wrapper |
| `jfr_virtual_thread_pinned_events` | Counter/analysis | JFR | Số event pinning được ghi nhận trong cửa sổ quan sát |

Tên metric ở bảng là tên gợi ý, không phải tên bắt buộc của JDK. Khi tích hợp Micrometer, OpenTelemetry hoặc hệ thống monitoring khác, hãy giữ metadata mô tả scope và nguồn dữ liệu.

Không gắn thread ID, thread name, request ID hoặc user ID làm label metric. Các label có cardinality cao có thể làm hệ thống metrics tốn bộ nhớ và khó truy vấn. Dùng trace/log để điều tra từng request; dùng metric tổng hợp để quan sát xu hướng.

## 13. Cách đọc các tổ hợp metric thường gặp

| Quan sát | Diễn giải có thể | Cần kiểm tra thêm |
|---|---|---|
| Virtual task active tăng, platform thread gần ổn định | Nhiều task đang chờ I/O hoặc được multiplex trên carrier | Dependency latency, số task chờ, heap và timeout |
| Platform thread tăng mạnh, virtual task không tăng tương ứng | Có thể tạo nhiều platform thread, executor riêng hoặc thread hệ thống tăng | Thread dump, thread factory và pool configuration |
| Virtual task active cao, throughput không tăng | Dependency bão hòa, admission quá rộng hoặc task chờ lâu | Semaphore/connection pool wait, queue time, request p99 |
| Platform thread gần scheduler parallelism, pinning events tăng | Carrier có thể bị giữ bởi đoạn code pinning | JFR stack trace, synchronized/native call path trên Java 21 |
| Started tăng nhanh nhưng completed tăng chậm | Task đang tích tụ, bị block hoặc xử lý lâu | Active gauge, task duration, timeout và cancellation |
| JFR start/end nhiều nhưng application gauge thấp | Có thể có virtual thread do framework/thư viện tạo ngoài vùng instrument | JFR stack trace và ranh giới instrument |

Các tổ hợp này là tín hiệu điều tra, không phải kết luận tự động. Hãy đối chiếu cùng thời điểm với latency, throughput, CPU, heap và dependency metrics.

## 14. Checklist trước khi đưa metrics vào production

1. Metric thread hiện tại có ghi rõ platform thread hay virtual thread không?
2. Các metric `ThreadMXBean` có được đặt tên và mô tả đúng là platform thread không?
3. Có phân biệt carrier platform thread với toàn bộ platform thread của JVM không?
4. Virtual task metrics có định nghĩa rõ phạm vi task được instrument không?
5. Có tách submitted, started, active, completed, failed và cancellation request khi nghiệp vụ cần không?
6. JFR có bật đúng virtual-thread events cần quan sát không?
7. Thread dump có được tạo bằng công cụ hỗ trợ virtual thread khi cần snapshot không?
8. Pinning được diễn giải theo đúng phiên bản JDK đang chạy không?
9. Dashboard có tránh label cardinality cao như thread ID và request ID không?
10. Các metric thread có được đối chiếu với CPU, latency, throughput và dependency saturation không?

## Kết luận

`ThreadMXBean` trong Java 21 đo platform thread, bao gồm carrier thread khi chúng đang sống, nhưng không đếm virtual thread như các thread độc lập. Số platform thread vì thế không thể đại diện cho số virtual thread hoặc số task đồng thời. Hãy dùng application instrumentation để đo task thuộc quyền quản lý của ứng dụng, JFR để quan sát vòng đời và pinning của virtual thread, cùng `jcmd Thread.dump_to_file -format=json` để lấy snapshot khi điều tra. Luôn đặt tên metric theo đúng phạm vi, phân biệt scheduler carrier với tổng platform thread và diễn giải pinning theo phiên bản JDK thực tế.
