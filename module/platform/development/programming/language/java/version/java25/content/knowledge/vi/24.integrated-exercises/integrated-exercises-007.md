# Điều tra tình huống CPU cao hoặc yêu cầu chậm bằng các khả năng JFR của JDK 25

## 1. Tình huống và mục tiêu

Một dịch vụ Java xử lý báo cáo bắt đầu có biểu hiện bất thường sau khi phát hành phiên bản mới:

- CPU của một số replica tăng từ khoảng 30% lên gần 90%.
- Request p99 tăng từ 100 ms lên 600 ms.
- Throughput không tăng tương ứng với mức CPU.
- Một số request chậm nhưng không phải tất cả.

Nhóm vận hành cần xác định thời gian đang được dùng để chạy code, chờ lock, chờ I/O, chờ GC hay đợi công việc trong hàng đợi. Chỉ nhìn CPU hoặc thread dump tại một thời điểm không đủ để phân biệt các nguyên nhân này.

Bài thực hành sử dụng **Java Flight Recorder (JFR) của JDK 25** để thu thập bằng chứng trong lúc ứng dụng chạy, phân tích recording và đưa ra giả thuyết có thể kiểm chứng. Nội dung phù hợp với mục tiêu module **JAVA_VERSION_JAVA25**: sử dụng công cụ quan sát của JDK hiện đại để điều tra hiệu năng và đánh giá tác động khi nâng cấp JDK.

Sau bài này, bạn có thể:

1. Tạo recording có giới hạn thời gian trên JVM đang chạy bằng `jcmd`.
2. Chọn `default.jfc` hoặc `profile.jfc` đúng với mục đích.
3. Phân biệt CPU load, method sampling, CPU-time sampling và thời gian chờ.
4. Dùng các event lock, I/O, allocation và GC để phân loại bottleneck.
5. Dùng JEP 520 để đo hoặc truy vết một method đã xác định.
6. So sánh recording lúc bình thường và lúc có sự cố, rồi lập kế hoạch sửa có thể đo lại.

## 2. JFR trong JDK 25 và các tính năng cần biết

JFR là framework thu thập event và profiling được tích hợp trong HotSpot JVM. Một event có thể chứa timestamp, duration, thread, stack trace và các trường dữ liệu riêng. Recording được lưu thành file nhị phân `.jfr`; có thể phân tích bằng `jfr` CLI hoặc JDK Mission Control (JMC).

JDK 25 có ba cải tiến JFR quan trọng:

| JEP | Khả năng | Cách dùng trong điều tra |
|---|---|---|
| JEP 518 — JFR Cooperative Sampling | Cải thiện độ ổn định khi lấy stack mẫu và giảm safepoint bias | Là nền tảng cho việc lấy mẫu stack đáng tin cậy hơn |
| JEP 520 — JFR Method Timing & Tracing | Đo và truy vết các method được chọn bằng bytecode instrumentation | Điều tra một method đã nghi ngờ sau bước profiling tổng quát |
| JEP 509 — JFR CPU-Time Profiling | Event CPU-time sampling mới, bao gồm cả Java và native code | Nhánh thử nghiệm bổ sung khi điều tra CPU trên Linux |

**Phân biệt trạng thái:**

- JEP 518 và JEP 520 là các cải tiến được phát hành trong JDK 25.
- JEP 509 là tính năng **experimental**, chỉ hỗ trợ Linux. Không coi event CPU-time là baseline bắt buộc hoặc API ổn định cho mọi nền tảng.
- JFR recording và các event profiling thông thường vẫn dùng được trên Windows, Linux và macOS theo hỗ trợ của JDK.

Trong bài này, quy trình chính bắt đầu bằng các recording và event chuẩn. CPU-time profiling chỉ xuất hiện ở nhánh tùy chọn dành cho Linux.

## 3. Hiểu các khái niệm trước khi đọc recording

### CPU load không phải request latency

CPU load cho biết CPU đang bận đến mức nào trong một khoảng thời gian. Request latency đo thời gian người dùng chờ một request hoàn tất. Một dịch vụ có CPU thấp vẫn có thể có p99 rất cao nếu request phải chờ database, network, lock, thread pool hoặc một dịch vụ phụ thuộc.

### Method samples không phải phép đo CPU time chính xác

`jdk.ExecutionSample` lấy mẫu stack của các thread đang thực thi Java code. Khi một method xuất hiện nhiều trong stack samples, đó là dấu hiệu method hoặc các caller của nó tiêu thụ nhiều thời gian thực thi trong recording.

Sampling có sai số thống kê. Recording ngắn hoặc số sample ít có thể dẫn tới kết luận sai. Thread đang chờ I/O, ngủ hoặc chờ lock không được lấy mẫu như thread đang chạy code; vì vậy cần đọc cả stall events.

### CPU time khác wall-clock time

- **CPU time:** thời gian thread thực sự được CPU thực thi.
- **Wall-clock time:** thời gian trôi qua từ lúc bắt đầu đến khi hoàn tất, bao gồm cả thời gian chờ.

Một method có wall-clock time 400 ms nhưng CPU samples thấp có thể đang chờ I/O hoặc lock. Một method có nhiều CPU samples và wall-clock time cao có thể đang tính toán nặng.

### Event duration chỉ phản ánh phạm vi đã instrument

`jdk.SocketRead` đo thời gian ở thao tác socket được JVM quan sát. Nó không tự giải thích toàn bộ thời gian request, ví dụ thời gian request nằm trong queue trước khi thread bắt đầu xử lý. Cần kết hợp JFR với metric cấp ứng dụng như request p95/p99, queue depth, timeout và throughput.

## 4. Chuẩn bị hai cửa sổ quan sát có thể so sánh

Để tìm thay đổi do release mới, hãy thu hai recording:

- **Baseline:** khi ứng dụng khỏe mạnh, tải đại diện và p99 bình thường.
- **Incident:** khi CPU cao hoặc request chậm đang xảy ra.

Giữ điều kiện càng giống nhau càng tốt:

- Cùng JDK vendor, version, JVM flags và container limits.
- Cùng số replica và cấu hình thread pool.
- Cùng workload, tỉ lệ request, kích thước dữ liệu và dependency.
- Ghi timestamp bắt đầu/kết thúc, throughput, request p50/p95/p99, error rate và CPU.
- Recording phải bao trùm đúng khoảng có sự cố, tránh ghi sau khi tải đã tự hết.

Không so sánh một recording lúc warm-up với một recording lúc hệ thống đã ổn định rồi kết luận JDK làm CPU tăng. Cần kiểm soát JIT warm-up, cache, traffic mix và trạng thái dependency.

## 5. Bắt đầu recording trên JVM đang chạy bằng jcmd

`jcmd` là công cụ chẩn đoán chính để gửi diagnostic command đến một JVM đang chạy. Công cụ phải chạy trên cùng máy và với effective user/group phù hợp với tiến trình JVM.

Liệt kê tiến trình Java:

```powershell
jcmd -l
```

Giả sử PID của dịch vụ là `12345`. Tạo recording profiling trong hai phút:

```powershell
jcmd 12345 JFR.start name=Incident settings=profile duration=120s filename=incident.jfr
```

Kiểm tra recording đang chạy:

```powershell
jcmd 12345 JFR.check
```

Sau khi hết thời lượng, file `incident.jfr` được ghi ra đường dẫn đã chỉ định. Nếu cần chủ động dừng một recording không có duration, dùng:

```powershell
jcmd 12345 JFR.stop name=Incident filename=incident.jfr
```

Nếu recording vẫn đang chạy và bạn muốn chụp một bản dữ liệu tại thời điểm hiện tại nhưng tiếp tục thu thập, dùng `JFR.dump`:

```powershell
jcmd 12345 JFR.dump name=Incident filename=incident-snapshot.jfr
```

`JFR.dump` ghi dữ liệu ra file và recording tiếp tục chạy. Kiểm tra tên recording thực tế bằng `JFR.check` trước khi dump hoặc stop.

### Ghi recording khi khởi động ứng dụng

Với một tiến trình có thể khởi động lại có kiểm soát:

```powershell
java -XX:StartFlightRecording=settings=profile,duration=120s,filename=incident.jfr -jar application.jar
```

Cách này hữu ích khi sự cố xảy ra ngay lúc startup. Với JVM production đang chạy, ưu tiên attach bằng `jcmd` để không phải khởi động lại dịch vụ chỉ nhằm lấy recording.

## 6. Chọn cấu hình recording và kiểm soát overhead

JDK cung cấp hai cấu hình JFR dựng sẵn trong `JAVA_HOME/lib/jfr`:

| Cấu hình | Mục đích | Đặc điểm |
|---|---|---|
| `default.jfc` | Continuous recording và giám sát dài hạn | Ít dữ liệu hơn, overhead thấp |
| `profile.jfc` | Profiling ngắn khi cần nhiều chi tiết | Ghi nhiều event hơn và có overhead cao hơn |

Oracle khuyến nghị `default.jfc` cho recording liên tục và `profile.jfc` cho profiling trong thời gian ngắn. Recording profiling theo cấu hình mặc định có overhead dưới 2% trong phần lớn ứng dụng theo tài liệu Oracle; continuous recording tiêu chuẩn thường không tạo ảnh hưởng đo được. Tuy nhiên, overhead thực tế phụ thuộc workload, event được bật, stack trace và tần suất event. Hãy đo trên chính dịch vụ của bạn.

**Không bật Heap Statistics trong bài đo latency thông thường.** Tính năng này có thể kích hoạt một old GC ở đầu và cuối recording, làm tăng pause và ảnh hưởng phép đo. Chỉ dùng khi mục tiêu là điều tra live set hoặc memory leak và đã chấp nhận tác động.

Với phần lớn Java Application stall events, ngưỡng mặc định là khoảng 20 ms. Event ngắn hơn có thể không xuất hiện trong recording. Nếu đang nghi lock hoặc I/O ngắn, giảm threshold cho đúng event trong một recording ngắn; không hạ threshold cho toàn bộ event trên production trong thời gian dài.

## 7. Kiểm tra recording trước khi đi sâu

Bắt đầu bằng summary:

```powershell
jfr summary incident.jfr
```

Summary cho biết số lượng event, khoảng thời gian và dung lượng. Nếu file không có event trong khoảng sự cố, kiểm tra recording window, event settings, PID và đồng hồ hệ thống trước khi phân tích.

Liệt kê các view có sẵn trong JDK đang dùng:

```powershell
jfr view all-views incident.jfr
```

Xem danh sách event type có trong recording:

```powershell
jfr view all-events incident.jfr
```

Có thể dùng JMC để mở file `.jfr`. JMC là công cụ riêng, không nằm trong bộ cài JDK thông thường. Các trang Code, Threads, I/O, Memory và Garbage Collections giúp xem timeline, hot methods, call tree và event phân bố theo thread.

## 8. Nhánh A: CPU của JVM thực sự cao

Bắt đầu với `jdk.CPULoad`. Event này cho biết CPU usage của JVM và CPU usage toàn máy theo thời gian.

```powershell
jfr print --events jdk.CPULoad incident.jfr
```

Diễn giải:

- JVM CPU cao và machine CPU cao: JVM có thể là một nguồn tải CPU đáng kể.
- JVM CPU thấp nhưng machine CPU cao: có thể tiến trình khác trên host đang tiêu thụ CPU; kiểm tra thêm bằng Task Manager hoặc công cụ hệ điều hành.
- Cả hai thấp trong lúc p99 tăng: nhiều khả năng cần điều tra thời gian chờ, queueing hoặc dependency.

Tiếp theo xem `jdk.ThreadCPULoad` để tìm các thread có nhiều hoạt động thực thi:

```powershell
jfr print --events jdk.ThreadCPULoad incident.jfr
```

`jdk.ThreadCPULoad` dựa trên method sampling. Số sample ít không cho phép xếp hạng CPU chính xác tuyệt đối; hãy dùng nó để chọn thread cần xem stack tiếp theo.

Trong JMC, mở Code → Hot Methods hoặc Call Tree. Với CLI, thử view tổng hợp:

```powershell
jfr view hot-methods incident.jfr
jfr view thread-cpu-load incident.jfr
```

Nếu view không có trong bản JDK hoặc recording cụ thể, dùng `jfr view all-views` để xem các view được hỗ trợ hoặc in trực tiếp event type.

### Đọc stack để tìm điểm nóng thật sự

Một method xuất hiện ở nhiều stack không nhất thiết là nơi nên sửa đầu tiên. Ví dụ:

- `ReportService.buildReport` có nhiều sample vì thực hiện vòng lặp tính toán lớn.
- `HashMap.resize` có nhiều sample vì caller liên tục tạo hoặc mở rộng map.
- `StringLatin1.newString` có nhiều sample vì tầng trên tạo chuỗi trung gian quá nhiều.
- Một method thư viện xuất hiện nhiều có thể chỉ là nơi chi phí của caller được thực hiện.

Đi từ leaf method lên caller, kiểm tra call tree và tìm nguyên nhân làm operation đó được gọi quá nhiều hoặc xử lý quá nhiều dữ liệu.

## 9. Nhánh B: CPU cao nhưng muốn thấy CPU time rõ hơn trên Linux

JDK 25 bổ sung `jdk.CPUTimeSample` theo JEP 509. Event này dùng CPU-time sampling để lấy mẫu thread đang chạy Java code lẫn native code. Đây là tính năng **experimental và chỉ hỗ trợ Linux**.

Ví dụ bật event trong recording:

```bash
java -XX:StartFlightRecording:jdk.CPUTimeSample#enabled=true,filename=cpu-time.jfr -jar application.jar
```

Xem các method tiêu thụ CPU time:

```bash
jfr view cpu-time-hot-methods cpu-time.jfr
```

Event này có thể hữu ích khi workload đi qua native code, chẳng hạn một lời gọi FFM/JNI, mà Java execution samples không mô tả đầy đủ. Tuy nhiên, không dùng CPUTimeSample làm baseline cho Windows/macOS hoặc hệ thống không hỗ trợ Linux.

Một số field cần biết khi đọc event:

| Field/event | Ý nghĩa |
|---|---|
| `samplingPeriod` | Khoảng CPU time được tính cho sample |
| `biased` | Sample có bị safepoint-biased hay không |
| `failed` | Không lấy được stack trace cho sample |
| `jdk.CPUTimeSamplesLost` | Ghi nhận sample bị mất |

Nếu có nhiều sample bị mất, nhiều sample thất bại hoặc kết quả quá ít, hãy kéo dài cửa sổ recording và xác minh điều kiện runtime trước khi kết luận.

**Đừng nhầm `jdk.ExecutionSample` với `jdk.CPUTimeSample`.** ExecutionSample là method sampling tiêu chuẩn, dùng để tìm nơi thread đang thực thi Java code. CPUTimeSample là nhánh experimental để đo CPU time chính xác hơn trên Linux và bao gồm cả native code.

## 10. Nhánh C: request chậm nhưng CPU không cao

Nếu p99 tăng trong khi JVM CPU thấp, hãy tìm thread-stalling events:

| Event | Điều cần tìm |
|---|---|
| `jdk.SocketRead` | Thread chờ dữ liệu từ remote service/database/socket |
| `jdk.SocketWrite` | Thread chờ ghi dữ liệu ra socket |
| `jdk.FileRead` / `jdk.FileWrite` | Thread chờ đọc/ghi file |
| `jdk.JavaMonitorEnter` | Thread bị chặn khi vào synchronized monitor |
| `jdk.JavaMonitorWait` | Thread chờ trên monitor bằng wait/notify |
| `jdk.ThreadPark` | Thread bị park, thường liên quan tới synchronizer hoặc queue |
| `jdk.ThreadSleep` | Thread chủ động ngủ |
| `jdk.ThreadStart` / `jdk.ThreadEnd` | Tần suất tạo/kết thúc thread bất thường |

In các event chính:

```powershell
jfr print --events jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite incident.jfr
```

```powershell
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.ThreadSleep incident.jfr
```

Xem thời lượng, thread, stack trace, địa chỉ remote hoặc file path nếu có. Nhiều SocketRead kéo dài có thể chỉ ra dependency chậm; nhiều ThreadPark có thể chỉ ra thread đang chờ queue hoặc synchronizer.

Một request có thể chờ ở nhiều tầng. Nếu SocketRead chiếm phần lớn wall-clock time, CPU optimization ở method gọi socket sẽ không giải quyết nguyên nhân chính. Cần kiểm tra pool connection, timeout, query, remote service và network.

## 11. Điều tra lock contention

Nếu nhiều request chậm cùng đi qua một vùng code đồng bộ, hãy xem `jdk.JavaMonitorEnter` và `jdk.JavaMonitorWait`.

```powershell
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait incident.jfr
```

Trong JMC, mở Threads hoặc Synchronization để xem:

- Monitor/lock nào có nhiều contention.
- Thread nào chờ lâu nhất.
- Stack trace của thread đang chờ.
- Stack trace hoặc call path liên quan đến vùng đồng bộ.

Ví dụ, một cache dùng chung có thể khóa toàn bộ map trong lúc refresh. Khi traffic tăng, nhiều request cùng chờ một monitor; CPU không nhất thiết tăng cao vì các thread đang blocked.

Đối chiếu recording baseline và incident. Nếu cùng lock xuất hiện nhiều hơn rõ rệt trong incident, hãy kiểm tra critical section có làm I/O, serialize, log hoặc gọi callback bên trong synchronized block hay không.

Nếu nghi ngờ các lock ngắn hơn ngưỡng mặc định, tạo recording riêng ngắn với threshold thấp hơn:

```bash
jcmd 12345 JFR.start name=ShortLocks settings=profile duration=30s filename=short-locks.jfr jdk.JavaMonitorEnter#threshold=5ms
```

Giảm threshold làm tăng số event và có thể tăng overhead. Chỉ áp dụng trong cửa sổ ngắn, sau đó so sánh kết quả với recording profile thông thường.

## 12. Điều tra I/O và dependency bên ngoài

JFR ghi nhận thời gian chờ ở các thao tác file và socket mà JVM quan sát được. Dùng `jdk.SocketRead`/`jdk.SocketWrite` để xem host remote và thời lượng; dùng `jdk.FileRead`/`jdk.FileWrite` để xem file và thời gian thao tác.

Ví dụ:

```powershell
jfr print --events jdk.SocketRead,jdk.SocketWrite incident.jfr
jfr print --events jdk.FileRead,jdk.FileWrite incident.jfr
```

Hãy tổng hợp theo:

- Remote address hoặc file path.
- Số lần đọc/ghi.
- Tổng bytes.
- Tổng thời gian chờ và phân bố duration.
- Stack trace của caller.
- Thread thực hiện thao tác.

Nếu socket chờ lâu, kiểm tra database query duration, connection pool wait, DNS, remote service, timeout và retry. Nếu FileRead/FileWrite tăng, kiểm tra storage latency, file size, logging và cách serialize.

**Giới hạn:** JFR không tự cho biết một request nằm bao lâu trong hàng đợi trước khi code thực hiện socket hoặc file operation. Cần kết hợp queue depth, executor active count, rejected tasks và metric của dependency.

## 13. Điều tra GC pause và allocation pressure

Nếu request latency tăng trùng với GC pause, xem `jdk.GCPhasePause`:

```powershell
jfr print --events jdk.GCPhasePause incident.jfr
```

Tập trung vào tổng thời gian pause, pause lớn nhất, tần suất GC và mốc thời gian so với request p99. Nhiều collector làm phần lớn công việc concurrent; thời gian của cả GC cycle không đồng nghĩa với thời gian ứng dụng bị dừng.

Nếu allocation rate cao, xem các event:

```powershell
jfr print --events jdk.ObjectAllocationInNewTLAB,jdk.ObjectAllocationOutsideTLAB incident.jfr
jfr print --events jdk.ThreadAllocationStatistics incident.jfr
```

Dùng allocation-by-site hoặc allocation-by-thread trong JMC/`jfr view` để tìm class, call site hoặc thread tạo nhiều object. Sau đó kiểm tra object trung gian, boxing, string formatting, collection growth và serialization.

Không kết luận memory leak chỉ vì allocation rate cao. Allocation cao nhưng object sống ngắn là workload khác với live set tăng liên tục. Nếu cần phân tích live set hoặc đường đi tới GC roots, dùng một recording riêng cho mục tiêu memory leak; đừng bật Heap Statistics trong recording đo latency.

## 14. Dùng JEP 520 để đo một method đã xác định

Sau khi profiling tổng quát chỉ ra method nghi ngờ, JDK 25 cho phép dùng **JFR Method Timing & Tracing** (JEP 520).

### Method Timing

Ví dụ đo method `buildReport`:

```bash
java -XX:StartFlightRecording=method-timing='com.example.ReportService::buildReport',dumponexit=true,filename=method-timing.jfr -jar application.jar
```

Xem kết quả:

```bash
jfr view method-timing method-timing.jfr
```

View cho biết method được đo, số lần gọi, thời gian tối thiểu, trung bình và tối đa.

**Method Timing đo thời gian thực thi gần đúng, bao gồm cả thời gian chờ, không chỉ CPU time.** Nếu method có average 300 ms nhưng CPU samples thấp, hãy điều tra I/O, lock và dependency bên trong method.

### Method Trace

`jdk.MethodTrace` ghi nhận lời gọi của method đã chọn cùng stack trace. Chỉ bật cho method cụ thể trong cửa sổ ngắn vì instrumentation theo invocation có thể tạo nhiều event khi method được gọi với tần suất cao.

Ví dụ chỉ trace một method:

```bash
java -XX:StartFlightRecording=jdk.MethodTrace#filter='com.example.ReportService::buildReport',dumponexit=true,filename=method-trace.jfr -jar application.jar
jfr view jdk.MethodTrace method-trace.jfr
```

JEP 520 phù hợp để trả lời câu hỏi hẹp như “method này được gọi bao nhiêu lần và từ call path nào?” hoặc “thời gian của method này phân bố ra sao?”. Không bật trace mọi method trong toàn ứng dụng.

## 15. Bổ sung event cấp ứng dụng khi cần gắn JFR với route

JFR built-in events mô tả hoạt động JVM và các thao tác I/O/lock/GC. Chúng không tự động cung cấp p99 cho từng HTTP route. Nếu cần xem request nào chậm theo route template, có thể thêm custom JFR event ở tầng filter/interceptor.

Ví dụ event chỉ lưu route template và kết quả, không lưu URL đầy đủ, query string, token, payload hay thông tin cá nhân:

Nếu ứng dụng dùng named module, khai báo `requires jdk.jfr;` trong `module-info.java` để source có thể dùng JFR API.

```java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.StackTrace;
import jdk.jfr.Threshold;

@Name("com.example.HttpRequest")
@Label("HTTP Request")
@Category({"Application", "HTTP"})
@Threshold("20 ms")
@StackTrace(false)
final class HttpRequestEvent extends Event {
    @Label("Route")
    String route;

    @Label("Outcome")
    String outcome;
}
```

Cách dùng trong lớp bao quanh request handler:

```java
static <T> T observe(String route, java.util.concurrent.Callable<T> action)
        throws Exception {
    HttpRequestEvent event = new HttpRequestEvent();

    if (!event.isEnabled()) {
        return action.call();
    }

    event.route = route;
    event.begin();

    try {
        T result = action.call();
        event.outcome = "success";
        return result;
    } catch (Exception ex) {
        event.outcome = "error";
        throw ex;
    } finally {
        event.end();
        if (event.shouldCommit()) {
            event.commit();
        }
    }
}
```

Gọi event quanh phạm vi request mà bạn muốn đo. Nếu đặt event bên trong service method, thời gian ở filter, queue hoặc serialization bên ngoài method sẽ không được tính. Đặt threshold phù hợp để không ghi mọi request rất ngắn.

Với reactive hoặc asynchronous handler, method có thể trả về trước khi request hoàn tất. Khi đó cần bắt đầu/kết thúc event theo lifecycle của completion signal, không kết thúc ngay khi method trả về publisher hoặc future.

Custom event bổ sung chi phí cấp phát và ghi event. Hãy đo overhead, chỉ lưu field cần thiết và giới hạn quyền truy cập file recording. JFR có thể chứa stack trace, tên thread, địa chỉ socket, file path và thông tin môi trường; xử lý recording theo chính sách bảo vệ dữ liệu của hệ thống.

Trước khi chia sẻ recording, có thể loại bỏ các event chứa system properties và environment variables:

```powershell
jfr scrub --exclude-events jdk.InitialSystemProperty,jdk.InitialEnvironmentVariable incident.jfr incident-scrubbed.jfr
```

Lệnh này chỉ scrub các event được chỉ định. Vẫn cần kiểm tra recording đầu ra vì stack trace, socket address, file path hoặc custom event có thể chứa dữ liệu nhạy cảm khác.

## 16. Bài thực hành: phân tích hai recording

### Dữ liệu tình huống

Hai recording được lấy từ cùng một phiên bản dịch vụ, cùng cấu hình và workload tương đương:

| Chỉ số | Baseline | Incident |
|---|---:|---:|
| JVM CPU | 32% | 91% |
| Machine CPU | 48% | 94% |
| Request p99 | 95 ms | 620 ms |
| Throughput | 1.000 req/s | 1.030 req/s |
| GC pause tổng | 120 ms | 145 ms |
| SocketRead duration tổng | 4 s | 4,5 s |
| Thread samples của `ReportService.buildReport` | 8% | 54% |

Các số liệu trên là dữ liệu giả định để luyện cách đọc, không phải benchmark của JDK 25.

### Bước 1 — Xác định JVM có thực sự dùng CPU

JVM CPU và machine CPU đều tăng. Đây là dấu hiệu JVM đang tiêu thụ phần lớn CPU tăng thêm; cần xem ThreadCPULoad và Hot Methods để xác định thread/method.

### Bước 2 — Tìm method chiếm nhiều samples

`ReportService.buildReport` tăng từ 8% lên 54% samples. Mở Call Tree và kiểm tra method con. Giả sử call tree cho thấy một vòng lặp tính toán lại cùng dữ liệu cho mỗi item.

Đây là giả thuyết CPU-bound có bằng chứng. Trước khi sửa, kiểm tra kích thước report, số item và tỉ lệ request đi qua code path này.

### Bước 3 — Loại trừ GC và I/O là nguyên nhân chính

GC pause chỉ tăng nhẹ, không đủ giải thích p99 tăng hơn nửa giây. SocketRead duration cũng không tăng đáng kể. Các số liệu này không chứng minh GC/I/O hoàn toàn không liên quan, nhưng làm giảm khả năng chúng là nguyên nhân chính của spike.

### Bước 4 — Dùng Method Timing để đo phạm vi hẹp

Bật `method-timing` cho `ReportService::buildReport` trong một recording ngắn. So sánh số lần gọi và thời gian min/average/max giữa baseline và incident.

Nếu method timing tăng cùng với CPU samples, ưu tiên tối ưu thuật toán, giảm số lần lặp, cache kết quả có vòng đời phù hợp hoặc tránh tính toán trùng. Nếu method timing tăng nhưng CPU samples thấp, chuyển sang điều tra wait/lock/I/O bên trong method.

### Bước 5 — Thử lại và xác minh

Sau khi sửa:

1. Chạy cùng workload và cùng kích thước report.
2. Thu recording profile mới.
3. So sánh p99, throughput, JVM CPU và samples của method.
4. Kiểm tra kết quả nghiệp vụ không đổi.
5. Giữ lại baseline, incident và after-fix recordings cùng thông tin JDK/flags.

Không coi một lần chạy nhanh hơn là bằng chứng chắc chắn. Lặp lại đủ lần để tránh nhiễu do JIT warm-up, cache, CPU frequency và traffic mix.

## 17. Ma trận phân loại bottleneck

| Dấu hiệu | Giả thuyết ưu tiên | Bằng chứng JFR cần xem |
|---|---|---|
| JVM CPU cao, machine CPU cao, nhiều method samples | CPU-bound trong JVM | `jdk.CPULoad`, `jdk.ThreadCPULoad`, `jdk.ExecutionSample` |
| Machine CPU cao nhưng JVM CPU thấp | Tiến trình khác trên host | `jdk.CPULoad` kết hợp OS process metrics |
| Request p99 cao, CPU thấp, SocketRead dài | Network hoặc remote dependency | `jdk.SocketRead`, remote address, stack trace |
| Request p99 cao, JavaMonitorEnter tăng | Lock contention | `jdk.JavaMonitorEnter`, lock, waiting thread |
| ThreadPark tăng và executor queue tăng | Worker/thread đang chờ | `jdk.ThreadPark` và application queue metrics |
| GC pause tổng tăng, p99 spike cùng thời điểm | GC pause ảnh hưởng request | `jdk.GCPhasePause` và request latency timeline |
| Allocation events tăng, GC dày hơn | Allocation pressure | TLAB allocation, `jdk.ThreadAllocationStatistics` |
| Method Timing cao nhưng CPU samples thấp | Method dành nhiều thời gian chờ | `jdk.MethodTiming` kết hợp I/O/lock events |
| CPUTimeSample cho thấy native frames chiếm nhiều CPU trên Linux | Native code hoặc FFM/JNI | `jdk.CPUTimeSample`, `jdk.CPUTimeSamplesLost` |

Một sự cố có thể có nhiều bottleneck cùng lúc. Chẳng hạn allocation cao vừa tăng GC vừa làm CPU tăng; một lock contention có thể khiến throughput giảm và làm queue dài thêm.

## 18. Những sai lầm thường gặp khi dùng JFR

- **Chỉ nhìn Hot Methods:** bỏ sót thời gian chờ I/O, lock, park và GC.
- **Xem ExecutionSample là CPU-time chính xác:** method sampling là dữ liệu lấy mẫu, phụ thuộc số sample và thread đang thực thi.
- **Coi Method Timing là CPU time:** Method Timing tính cả thời gian chờ trong method.
- **Bật profile recording quá lâu:** profile thu nhiều event hơn default và có thể tăng overhead/dung lượng.
- **Giảm threshold mọi event:** event volume và overhead tăng; chỉ giảm threshold cho event cần điều tra trong cửa sổ ngắn.
- **Bật Heap Statistics khi đo p99:** có thể tạo thêm old GC và làm sai phép đo latency.
- **Dùng CPUTimeSample trên Windows/macOS:** JEP 509 trong JDK 25 chỉ hỗ trợ Linux và vẫn experimental.
- **Kết luận request p99 từ JFR samples:** p99 phải đến từ metric request; JFR cung cấp bằng chứng giải thích khoảng thời gian đó.
- **Đọc recording mà không xem event count:** event thiếu có thể do threshold, setting hoặc recording window, không nhất thiết vì bottleneck không tồn tại.
- **Chia sẻ file JFR không kiểm tra:** recording có thể chứa stack trace, socket address, file path và system properties.

## 19. Quy trình báo cáo sự cố dựa trên bằng chứng

Một báo cáo tốt cần trả lời:

1. Sự cố bắt đầu và kết thúc lúc nào? Recording bao phủ đúng khoảng đó không?
2. JVM CPU và machine CPU thay đổi ra sao?
3. Thread hoặc method nào tăng samples rõ nhất?
4. Thread quan trọng có chờ I/O, lock, park hoặc GC không?
5. Có event nào bị bỏ qua do threshold mặc định không?
6. Giả thuyết chính là gì, và bằng chứng nào ủng hộ/không ủng hộ?
7. Thay đổi code/config nào được đề xuất?
8. Sau thay đổi, p95/p99, throughput, CPU và JFR có cải thiện trong workload tương đương không?

Mẫu kết luận:

```text
Symptom:
  Request p99 tăng từ 95 ms lên 620 ms; JVM CPU tăng lên 91%.

Evidence:
  ReportService.buildReport chiếm 54% method samples.
  SocketRead và tổng GC pause không tăng đáng kể.
  Method Timing của buildReport tăng theo incident window.

Hypothesis:
  Tính toán report lặp lại theo từng item làm CPU-bound.

Action:
  Tối ưu vòng lặp và loại bỏ phép tính trùng.

Validation:
  Chạy lại cùng workload, so sánh p99, throughput, CPU và recording.
```

Ghi rõ giới hạn: đây là giả thuyết được hỗ trợ bởi dữ liệu trong cửa sổ quan sát. Nếu thay đổi không cải thiện, quay lại các nhánh lock, I/O, queueing và GC thay vì tiếp tục tối ưu method theo cảm tính.

## 20. Checklist thực hành JFR trên JDK 25

- [ ] Xác nhận đúng JDK 25 runtime, PID, vendor và JVM flags.
- [ ] Thu baseline và incident recording với workload tương đương.
- [ ] Dùng `jcmd PID JFR.start` với `settings=profile` cho recording ngắn.
- [ ] Dùng `default.jfc` cho continuous recording dài hạn.
- [ ] Kiểm tra recording bằng `JFR.check` và `jfr summary`.
- [ ] Xem `jdk.CPULoad` trước khi kết luận JVM có phải nguồn CPU cao.
- [ ] Xem `jdk.ThreadCPULoad` và `jdk.ExecutionSample` để tìm hot threads/methods.
- [ ] Kiểm tra SocketRead/Write, FileRead/Write, MonitorEnter/Wait, ThreadPark/Sleep.
- [ ] Kiểm tra `jdk.GCPhasePause` và allocation events khi có dấu hiệu GC pressure.
- [ ] Chỉ dùng JEP 520 Method Timing/Tracing cho method đã chọn và recording ngắn.
- [ ] Chỉ thử JEP 509 CPUTimeSample trên Linux và ghi rõ tính experimental.
- [ ] Hạ threshold từng event khi có lý do; theo dõi overhead.
- [ ] Không bật Heap Statistics trong recording đo latency thông thường.
- [ ] Kết hợp JFR với request p95/p99, throughput, queue depth và dependency metrics.
- [ ] Xử lý file JFR như dữ liệu vận hành nhạy cảm; scrub trước khi chia sẻ nếu cần.
- [ ] Đo lại sau khi sửa trên cùng workload và runtime.

### Tài liệu tham khảo chính thức

1. [Oracle Java SE 25 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
2. [Oracle Java SE 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html)
3. [Oracle Java SE 25 — The jfr Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html)
4. [Oracle Java SE 25 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html)
5. [Oracle Java SE 25 — JFR Event API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Event.html)
6. [Oracle Java SE 25 — JFR Package Settings and Configuration](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
7. [JEP 509 — JFR CPU-Time Profiling (Experimental)](https://openjdk.org/jeps/509)
8. [JEP 518 — JFR Cooperative Sampling](https://openjdk.org/jeps/518)
9. [JEP 520 — JFR Method Timing & Tracing](https://openjdk.org/jeps/520)
10. [Inside.java — What's New in JDK 25: JFR Method Timing, Tracing and CPU-Time Profiling](https://inside.java/2025/10/17/new-in-jdk-25-2-mins/)
11. [Oracle Java SE 25 — JFR API Programmer's Guide: Measuring Time](https://docs.oracle.com/en/java/javase/25/jfapi/measuring-time.html)
