# Phân tích stack trace để xác định mã tiêu thụ CPU

Khi một ứng dụng Java dùng CPU cao, câu hỏi quan trọng không chỉ là thread nào đang bận mà còn là **method và call path nào thực sự tiêu thụ CPU**. Java Flight Recorder (JFR) có các event lấy mẫu stack để chỉ ra code đang chạy. Tuy nhiên, cần phân biệt thời gian CPU với thời gian trôi qua: một method chờ database 500 ms có thể có wall-clock duration lớn nhưng gần như không tiêu thụ CPU trong lúc chờ.

Java 25 bổ sung **JEP 509 — JFR CPU-Time Profiling (Experimental)**. Trên Linux, JFR có thể dùng CPU-time sampler để phát event `jdk.CPUTimeSample`, lấy mẫu theo lượng CPU time thread đã tiêu thụ và bao gồm cả lúc thực thi Java lẫn native code. Đây là lựa chọn hữu ích khi ứng dụng dùng JNI, thư viện native hoặc Foreign Function & Memory API. Tính năng này **vẫn là experimental trong tài liệu JDK 26 và chỉ dành cho Linux**; nó không thay thế phương pháp JFR stack sampling thông thường trên các nền tảng khác.

Bài thuộc chương **CPU-time profiling** của module **JAVA_VERSION_JAVA25**, tập trung vào đề bài **phân tích stack trace để xác định mã tiêu thụ CPU**. Bạn sẽ phân biệt `jdk.ExecutionSample`, `jdk.CPUTimeSample` và `jdk.ThreadCPULoad`, bật CPU-time profiling, đọc hot methods/call tree, kiểm tra mẫu bị mất hoặc bị lệch, rồi đối chiếu kết quả với workload thực tế. Nội dung ưu tiên JFR, JMC, `jcmd` và `jfr` hiện hành.

> **Điểm cần nhớ:** số lượng stack sample là bằng chứng thống kê, không phải số lần gọi method hay phép đo tuyệt đối cho từng instruction. CPU-time profiling giúp phân bổ CPU time chính xác hơn theo thread; vẫn cần xem sampling period, sample bị mất, native symbols, thread role và điều kiện workload trước khi quyết định tối ưu.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt CPU time, wall-clock time, CPU utilization và method execution samples.
2. Giải thích giới hạn của `jdk.ExecutionSample` khi thread thực thi native code hoặc đang chờ.
3. Nêu đúng trạng thái của JEP 509: experimental, Linux-only và không bật mặc định.
4. Giải thích `jdk.CPUTimeSample` lấy mẫu theo CPU time và bao gồm Java/native execution.
5. Bật CPU-time profiling bằng JVM option hoặc `jcmd`.
6. Đọc `jdk.CPUTimeSamplesLost`, `samplingPeriod`, `failed` và `biased` để đánh giá chất lượng recording.
7. Dùng `jfr view cpu-time-hot-methods`, `jfr print` và JMC để phân tích stack.
8. Phân biệt CPU-time samples với `jdk.CPULoad` và `jdk.ThreadCPULoad`.
9. Nhận diện hot method, self time, inclusive time, call tree và native frame.
10. Đối chiếu CPU profile với GC, lock, I/O, container CPU quota và OS metrics.
11. Chọn công cụ thay thế phù hợp khi chạy Windows, macOS hoặc môi trường không hỗ trợ JEP 509.
12. Thiết kế benchmark trước/sau tối ưu và báo cáo giới hạn của kết quả.

## 2. CPU time khác wall-clock time như thế nào?

**Wall-clock time** là khoảng thời gian thực tế trôi qua giữa hai mốc. **CPU time** là thời gian CPU thực sự chạy cho một thread hoặc process. Hai số đo có thể rất khác nhau.

Ví dụ một method gọi HTTP service và đợi response trong 400 ms:

- Wall-clock duration có thể gần 400 ms.
- CPU time của thread có thể chỉ vài millisecond vì phần lớn thời gian thread bị block/chờ.
- Nếu method parse JSON và tính toán trong 400 ms, CPU time có thể gần với wall-clock time hơn, tùy scheduling và thời gian chờ khác.

| Hoạt động | Wall-clock time | CPU time của thread | Cách điều tra |
|---|---:|---:|---|
| Sắp xếp một mảng lớn | Cao | Thường cao | CPU stack profiling |
| Chờ socket/database | Cao | Thấp trong lúc chờ | JFR SocketRead/trace DB |
| Chờ monitor/lock | Cao | Thấp trong lúc bị block | Monitor/park events |
| Tính toán trong native library | Cao | Có thể cao | CPU-time profiling, gồm native stack |
| Thread ngủ hoặc park | Cao | Gần như không tăng khi chờ | Thread/synchronization events |

CPU time của nhiều threads có thể cộng lại lớn hơn wall-clock duration. Ví dụ 8 threads cùng chạy CPU trong 1 giây có thể tích lũy gần 8 CPU-seconds nếu có đủ core và không bị throttling. Vì vậy, không lấy tổng CPU time chia cho wall-clock time rồi gọi đó là latency của một request.

### 2.1. CPU utilization không phải method profile

Các chỉ số cũng có phạm vi khác nhau:

- **Machine CPU utilization:** mức bận CPU của toàn máy hoặc container host.
- **JVM CPU utilization:** phần CPU mà process JVM đang dùng.
- **Thread CPU time/load:** CPU được tiêu thụ bởi từng thread.
- **Method profile:** stack trace nào xuất hiện trong các mẫu của thread.
- **Wall-clock latency:** thời gian từ lúc bắt đầu đến lúc hoàn thành một operation.

CPU utilization cao cho biết cần điều tra, nhưng không chỉ ra method nào gây ra. Stack profile giúp tìm call path; CPU load events giúp hiểu quy mô và phân bố tải.

## 3. Các cách lấy mẫu CPU trong JFR

Java 25 có hai hướng lấy mẫu stack cần phân biệt:

1. **Method/execution sampling:** JFR lấy mẫu thread đang thực thi Java code, thông qua event `jdk.ExecutionSample`.
2. **CPU-time sampling:** JEP 509 thêm event `jdk.CPUTimeSample` trên Linux, lấy mẫu theo CPU time thread đã sử dụng và bao gồm cả Java/native execution.

Ngoài ra, `jdk.CPULoad` và `jdk.ThreadCPULoad` cung cấp CPU load theo JVM/machine/thread, nhưng không thay thế stack trace.

| Event/cơ chế | Đo hoặc ghi gì? | Native code | Nền tảng |
|---|---|---|---|
| `jdk.ExecutionSample` | Stack sample của thread đang thực thi Java code | Không lấy mẫu phần thực thi native như CPUTimeSample | Các nền tảng HotSpot hỗ trợ JFR |
| `jdk.CPUTimeSample` | Stack sample theo CPU time đã tiêu thụ | Có, gồm Java và native execution | Linux, experimental |
| `jdk.CPUTimeSamplesLost` | Số sample CPU-time bị mất | Áp dụng cho CPU-time sampler | Linux, experimental |
| `jdk.ThreadCPULoad` | CPU load của từng thread theo chu kỳ | Không cung cấp stack trace để quy về method | Theo runtime/JFR hỗ trợ |
| `jdk.CPULoad` | CPU load của JVM và máy | Không cung cấp stack trace | Theo runtime/JFR hỗ trợ |

**Đừng nhầm CPUTimeSample với ThreadCPULoad:** event thứ nhất cho stack samples theo CPU time; event thứ hai cho biết thread nào dùng CPU nhiều hơn nhưng không chỉ ra call path cụ thể.

## 4. JEP 509 — JFR CPU-Time Profiling trong Java 25

JEP 509 đưa CPU-time profiling vào JFR dưới dạng **tính năng experimental**. Trên Linux, cơ chế này dùng CPU-time timer và signal `SIGPROF` để yêu cầu lấy mẫu thread theo lượng CPU time đã tiêu thụ. Khác với lấy mẫu theo khoảng thời gian trôi qua, sampler có thể tập trung vào thread thực sự đang sử dụng CPU.

### 4.1. Vì sao cần CPU-time profiling?

Với `jdk.ExecutionSample`, JFR chỉ lấy mẫu các thread đang chạy Java code. Điều đó phù hợp với nhiều ứng dụng thuần Java, nhưng có thể bỏ sót phần CPU tiêu thụ bên trong native code.

Ví dụ ứng dụng gọi một thư viện native qua JNI hoặc FFM:

~~~text
OrderService.process()
  -> NativeCrypto.encrypt()
      -> native library
          -> CPU-intensive native routine
~~~

Stack sample Java có thể thấy method Java gọi native entry point, nhưng không mô tả đầy đủ phần native routine đang chạy. `jdk.CPUTimeSample` có thể lấy mẫu cả native execution, giúp profile phản ánh tốt hơn phần CPU tiêu thụ trong các đoạn đó.

### 4.2. Trạng thái và phạm vi hỗ trợ

**Experimental · Linux only**

Các giới hạn phải hiểu trước khi bật:

- JEP 509 vẫn được Oracle Migration Guide của JDK 26 đánh dấu **experimental**.
- Chỉ hỗ trợ Linux; không dùng làm quy trình CPU profiling chung cho Windows/macOS.
- Event `jdk.CPUTimeSample` không được bật mặc định.
- Cơ chế dựa trên CPU-time sampler và `SIGPROF`, nên hành vi phụ thuộc Linux/JDK/runtime tương thích.
- Các sample có thể bị mất hoặc không lấy được stack; phải kiểm tra event chẩn đoán và chất lượng recording.
- Sampling period/throttle ảnh hưởng lượng event, độ chi tiết và overhead.

Experimental không có nghĩa tính năng đã bị deprecated hoặc legacy. Nó có nghĩa API/hành vi chưa có cùng mức cam kết ổn định như tính năng product; chỉ bật có chủ đích, xác minh trên JDK/platform đích và có phương án dự phòng.

### 4.3. JEP 518 liên quan thế nào?

**JEP 518 — JFR Cooperative Sampling** cải thiện cơ chế lấy mẫu stack của HotSpot: stack walking diễn ra tại safepoints trong khi giảm safepoint bias, giúp việc lấy mẫu an toàn và có khả năng mở rộng hơn.

JEP 509 và JEP 518 bổ sung cho nhau:

- JEP 518 cải thiện cách HotSpot walk stack an toàn.
- JEP 509 bổ sung CPU-time-based sampling trên Linux.
- `jdk.ExecutionSample` vẫn hữu ích cho profile Java execution đa nền tảng.
- `jdk.CPUTimeSample` mở rộng khả năng phân tích phần native execution và CPU time.

Không suy luận rằng JEP 518 tự biến `jdk.ExecutionSample` thành CPU-time profiler hoặc khiến JEP 509 trở thành tính năng cross-platform.

## 5. Hiểu event jdk.CPUTimeSample

Event `jdk.CPUTimeSample` ghi snapshot stack của thread từ CPU-time sampler. Trong JDK 25, các trường quan trọng gồm:

| Field | Ý nghĩa khi phân tích |
|---|---|
| `stackTrace` | Call stack được thu tại sample |
| `eventThread` | Thread được lấy mẫu |
| `samplingPeriod` | Khoảng CPU time tương ứng với sample |
| `failed` | Cho biết việc lấy stack trace có thất bại hay không |
| `biased` | Cho biết sample có bị safepoint-biased hay không |

Đọc các trường này để hiểu profile có đáng tin cậy không. Nếu nhiều sample có `failed=true` hoặc tỷ lệ sample `biased=true` đáng kể, cần xem lại runtime, recording và cách diễn giải trước khi kết luận.

### 5.1. Sampling period và throttle

Event có setting `throttle`. Tùy chọn này có thể giới hạn tốc độ phát event (ví dụ `500/s`) hoặc đặt chu kỳ theo CPU time (ví dụ `10ms`). Chu kỳ ngắn hơn thường tạo nhiều sample hơn, nhưng cũng tăng lượng dữ liệu và có thể tăng overhead.

Ví dụ cấu hình CPU-time period 10 ms:

~~~text
jdk.CPUTimeSample#enabled=true
jdk.CPUTimeSample#throttle=10ms
~~~

Một cấu hình khác có thể giới hạn tốc độ event:

~~~text
jdk.CPUTimeSample#enabled=true
jdk.CPUTimeSample#throttle=500/s
~~~

Không mặc định chọn throttle nhanh nhất. Bắt đầu với cấu hình phù hợp trong môi trường test, xem event volume và đo overhead rồi mới áp dụng cho production.

### 5.2. Event jdk.CPUTimeSamplesLost

`jdk.CPUTimeSamplesLost` ghi nhận CPU-time samples bị mất. Hãy xem field `lostSamples` và thread liên quan nếu có. Sample bị mất có thể khiến hot-method ranking không đầy đủ; recording có nhiều sample loss không nên được coi là một profile hoàn hảo.

Ngoài ra, event `jdk.CPUTimeSample` có field `failed` để chỉ ra trường hợp lấy stack không thành công. Phân biệt hai tình huống:

- **Lost samples:** sampler đã không ghi được một số sample.
- **Failed stack capture:** event sample được xử lý nhưng không lấy được stack trace mong muốn.

Không chỉ xem tổng số event rồi bỏ qua các dấu hiệu chất lượng này.

## 6. Bắt đầu CPU-time profiling trên Linux

### 6.1. Ghi khi khởi chạy ứng dụng

Trên Linux với JDK có hỗ trợ JEP 509:

~~~bash
java -XX:StartFlightRecording:settings=profile,filename=cpu-time.jfr,duration=60s,jdk.CPUTimeSample#enabled=true -jar app.jar
~~~

Có thể chỉ định throttle tường minh:

~~~bash
java -XX:StartFlightRecording:settings=profile,filename=cpu-time.jfr,duration=60s,jdk.CPUTimeSample#enabled=true,jdk.CPUTimeSample#throttle=10ms -jar app.jar
~~~

Các tham số:

- `settings=profile`: bật bộ event profile có nhiều dữ liệu hơn cấu hình default.
- `filename`: file recording output.
- `duration=60s`: giới hạn thời lượng recording.
- `jdk.CPUTimeSample#enabled=true`: bật event CPU-time sampling.
- `jdk.CPUTimeSample#throttle=10ms`: tùy chọn điều chỉnh chu kỳ theo CPU time.

JFR profile template thông thường không tự bật CPUTimeSample; cần bật event rõ ràng. Nếu chạy trên nền tảng không hỗ trợ, hãy dùng execution sampling tiêu chuẩn và xác minh event metadata/runtime thay vì cho rằng lệnh đã tạo được CPU-time samples.

### 6.2. Attach vào JVM đang chạy bằng jcmd

Liệt kê process:

~~~bash
jcmd -l
~~~

Bắt đầu recording:

~~~bash
jcmd <pid> JFR.start name=cpu-time settings=profile duration=60s filename=cpu-time.jfr jdk.CPUTimeSample#enabled=true jdk.CPUTimeSample#throttle=10ms
~~~

Kiểm tra recording:

~~~bash
jcmd <pid> JFR.check
~~~

Dump recording:

~~~bash
jcmd <pid> JFR.dump name=cpu-time filename=cpu-time-snapshot.jfr
~~~

Dừng recording:

~~~bash
jcmd <pid> JFR.stop name=cpu-time
~~~

`jcmd` phải chạy trên cùng máy và cùng effective user/group với JVM đích. Trong container, chạy trong đúng container/namespace hoặc dùng PID/attach mechanism phù hợp. Nếu attach không thành công, kiểm tra PID, quyền và JDK tools cùng runtime.

### 6.3. Xác nhận event có trong recording

Trước khi phân tích, xem summary:

~~~bash
jfr summary cpu-time.jfr
~~~

In CPU-time events:

~~~bash
jfr print --events jdk.CPUTimeSample,jdk.CPUTimeSamplesLost cpu-time.jfr
~~~

Xem metadata:

~~~bash
jfr metadata --events jdk.CPUTimeSample
~~~

Tạo bảng hot methods bằng view được cung cấp trong JDK 25:

~~~bash
jfr view cpu-time-hot-methods cpu-time.jfr
~~~

Nếu view không có hoặc event không xuất hiện, kiểm tra JDK build, OS, setting đã bật, thời lượng recording và workload. File `.jfr` được tạo thành công không có nghĩa CPUTimeSample đã được bật hoặc đã thu được sample.

## 7. Phân tích hot methods và stack trace

Một CPU-time profile hữu ích phải trả lời được ba câu hỏi:

1. Thread nào đang tiêu thụ CPU?
2. Method nào xuất hiện trong stack của các sample CPU-time?
3. Caller nào đưa execution vào method đó?

### 7.1. Hot methods

Hot methods là những method có tỷ trọng sample cao trong recording. Chúng là ứng viên điều tra, không tự động là lỗi.

Ví dụ bảng minh họa:

| Method | Tỷ trọng sample | Câu hỏi tiếp theo |
|---|---:|---|
| `com.example.crypto.NativeCipher.encrypt` | 34% | Native routine có làm nhiều việc hơn dự kiến? |
| `com.example.json.JsonEncoder.write` | 22% | Có serialize lặp hoặc tạo output trung gian? |
| `com.example.order.PriceCalculator.calculate` | 16% | Có thuật toán/vòng lặp tốn CPU? |
| `java.util.HashMap.getNode` | 9% | Có lookup lặp, hash collision hoặc key distribution bất thường? |
| `com.example.trace.ContextFormatter.format` | 6% | Logging/tracing có tạo nhiều chuỗi? |

Các tỷ lệ trên chỉ là ví dụ để minh họa cách đọc. Hãy dùng kết quả từ recording thật và ghi rõ cửa sổ thu thập, workload và số sample.

### 7.2. Self time và inclusive time

- **Self time:** phần thời gian/sample gắn trực tiếp với method đang xét, không cộng các method con.
- **Inclusive time:** phần thời gian/sample của method cùng các method được gọi bên dưới nó trong call tree.

Nếu method cha có inclusive time cao nhưng self time thấp, chi phí có thể nằm ở method con. Tối ưu method cha mà không tìm child hot method có thể không cải thiện CPU.

### 7.3. Đọc call tree từ leaf lên caller

Một stack minh họa:

~~~text
com.example.api.OrderController.handle
  com.example.order.OrderService.process
    com.example.crypto.CryptoService.encrypt
      com.example.nativecrypto.NativeBridge.invoke
        native library frame
~~~

Cách đọc:

1. Bắt đầu từ leaf frame có CPU samples đáng kể.
2. Xác định frame native hay Java.
3. Đi ngược lên caller để tìm operation nghiệp vụ khởi tạo công việc.
4. Xem method có nằm trên request path quan trọng hay background worker.
5. Đối chiếu với request rate, CPU load và latency.
6. Xác định liệu chi phí là thuật toán, serialization, native call hay thao tác lặp.

Đừng tối ưu một helper method chỉ vì nó xuất hiện trong nhiều stack; cần xem call path, tần suất operation và khả năng giảm tổng lượng công việc.

## 8. Khi nào dùng ExecutionSample, khi nào dùng CPUTimeSample?

Đây là quyết định trọng tâm của bài.

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Ứng dụng Java thuần, chạy đa nền tảng | `jdk.ExecutionSample` | Có sẵn trên các nền tảng HotSpot hỗ trợ JFR |
| CPU cao trong Java methods | `jdk.ExecutionSample` và `jdk.ThreadCPULoad` | Xác định hot stack và thread dùng CPU |
| Ứng dụng có JNI/FFM/native library | `jdk.CPUTimeSample` trên Linux | Có thể lấy mẫu cả native execution |
| Cần CPU-time profile thay vì method sampling theo thời gian | `jdk.CPUTimeSample` trên Linux | Sample được kích hoạt theo CPU time |
| Windows hoặc macOS | `jdk.ExecutionSample` và profiler phù hợp nền tảng | JEP 509 không hỗ trợ các hệ điều hành này |
| Cần CPU utilization tổng thể | `jdk.CPULoad` | Đo tải JVM và máy, không chỉ method |
| Cần biết thread nào tiêu thụ CPU | `jdk.ThreadCPULoad` | Theo dõi CPU load theo thread |

### 8.1. Không dùng ExecutionSample để kết luận native code không tốn CPU

Nếu application gọi native code nhiều, profile Java có thể thấy caller Java nhưng bỏ qua phần thực thi bên trong native library. Khi đó:

- CPU utilization của process có thể cao.
- Java execution samples có thể không giải thích hết CPU.
- CPUTimeSample trên Linux có thể cho thấy native frames và CPU-time distribution rõ hơn.

Đây là một trường hợp phù hợp để thử JEP 509, với điều kiện runtime hỗ trợ và recording có chất lượng đủ tốt.

### 8.2. Không dùng CPUTimeSample để phân tích I/O waiting

Một thread đợi socket hoặc database không tiêu thụ CPU liên tục trong thời gian chờ. CPU-time profile có thể không thể hiện phần wall-clock latency đó. Hãy dùng các event duration như `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead`, `jdk.FileWrite` và distributed traces để điều tra thời gian chờ.

## 9. CPU load events: nhìn từ process đến thread

### 9.1. jdk.CPULoad

`jdk.CPULoad` giúp theo dõi CPU usage của JVM và toàn máy. Khi CPU máy cao nhưng CPU JVM thấp, có thể process khác hoặc container/host workload khác đang tiêu thụ CPU.

### 9.2. jdk.ThreadCPULoad

`jdk.ThreadCPULoad` cung cấp CPU load theo thread. Nó giúp xếp hạng thread cần điều tra, nhưng không phải event stack sample. Kết hợp với `jdk.ExecutionSample` hoặc `jdk.CPUTimeSample` để tìm method trong thread đó.

### 9.3. ThreadMXBean khi cần đo một thread cụ thể

Java Management API cung cấp `ThreadMXBean` để đọc CPU time của thread nếu JVM hỗ trợ và đã bật tính năng này:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

public class ThreadCpuTimeExample {

    public static void main(String[] args) {
        ThreadMXBean bean =
                ManagementFactory.getThreadMXBean();

        if (!bean.isThreadCpuTimeSupported()) {
            System.out.println("Thread CPU time không được hỗ trợ");
            return;
        }

        if (!bean.isThreadCpuTimeEnabled()) {
            bean.setThreadCpuTimeEnabled(true);
        }

        long before = bean.getCurrentThreadCpuTime();

        doCpuWork();

        long after = bean.getCurrentThreadCpuTime();

        if (before >= 0 && after >= before) {
            long elapsedCpuNanos = after - before;
            System.out.println("CPU time (ns): " + elapsedCpuNanos);
        }
    }

    private static void doCpuWork() {
        long value = 0;
        for (int i = 0; i < 10_000_000; i++) {
            value += i;
        }
        if (value == Long.MIN_VALUE) {
            System.out.println(value);
        }
    }
}
~~~

Ví dụ này đo CPU time tích lũy của **thread hiện tại** trong khoảng gọi method. Nó không tự tạo stack profile hoặc phân bổ CPU time cho từng method con. Với đo lường production, cần xem chi phí bật CPU-time measurement trên JVM cụ thể và tránh thêm instrumentation làm thay đổi workload.

## 10. Native code và FFM: phân tích cả call path

Một ứng dụng Java hiện đại có thể gọi native code qua JNI hoặc FFM. Ví dụ:

- Thư viện mã hóa/giải mã native.
- Thư viện nén, xử lý ảnh hoặc âm thanh.
- Database client/native transport.
- Thư viện khoa học, tính toán số học hoặc machine learning.
- FFM downcall tới hàm C/C++.

Với các trường hợp này, CPUTimeSample có thể bổ sung góc nhìn về CPU time trong native execution.

### 10.1. Native frame có thể thiếu symbol

Nếu native library đã bị strip symbol hoặc thiếu debug symbols, stack có thể hiển thị địa chỉ/frame không đầy đủ. Điều đó không có nghĩa native code không tiêu thụ CPU.

Để cải thiện khả năng phân tích:

1. Dùng binary build có symbol phù hợp cho môi trường profiling.
2. Lưu build ID và phiên bản native library tương ứng với recording.
3. Kiểm tra JDK, kiến trúc CPU và native library version.
4. Dùng symbolization/toolchain phù hợp nền tảng.
5. Đối chiếu native stack với source/build metadata.

Không đưa file binary có symbol nhạy cảm ra ngoài tổ chức nếu chưa kiểm soát quyền chia sẻ.

### 10.2. Phân biệt native execution với thread đang chờ trong native

Không phải mọi thread nằm trong native frame đều đang tiêu thụ CPU. Một thread có thể ở trong native blocking call để chờ I/O. Hãy đọc state, CPU-time sampling và duration events; đừng kết luận dựa trên tên frame.

## 11. Đọc mẫu bị mất và mẫu bị lệch

CPU-time profiling là sampling. Độ tin cậy phụ thuộc số lượng sample, chất lượng stack và workload.

| Dấu hiệu | Ý nghĩa | Cách xử lý |
|---|---|---|
| `CPUTimeSamplesLost` có `lostSamples` lớn | Sampler mất nhiều mẫu | Giảm event volume/throttle, tăng cửa sổ thu và đo lại |
| `CPUTimeSample.failed=true` | Không lấy được stack trace | Kiểm runtime, native state và tỷ lệ failed |
| `CPUTimeSample.biased=true` | Sample có safepoint bias | Xem tỷ lệ và phân bố; tránh diễn giải quá mức |
| Rất ít sample | Recording quá ngắn hoặc workload ít CPU | Thu lâu hơn trong cùng workload |
| Native frames thiếu symbol | Thiếu symbol/debug metadata | Dùng native build có symbol và symbolization |
| Profile khác nhau nhiều giữa các lần chạy | Workload hoặc môi trường không ổn định | Cố định workload, CPU quota và runtime conditions |

### 11.1. Không biến sample count thành CPU seconds

Nếu một method có 500 sample, không thể tự động kết luận nó dùng 5 giây CPU chỉ bằng cách nhân số sample với một khoảng cố định. Hãy dùng view phân tích CPU-time của JFR và xem field `samplingPeriod`, throttle, lost samples cùng cách tool tổng hợp.

Nếu cần số đo tổng CPU time, đối chiếu với OS/container metrics hoặc ThreadMXBean ở phạm vi phù hợp. Stack profile dùng để quy nguyên nhân theo method/call path; số đo CPU tổng thể dùng để xác nhận quy mô.

## 12. Tìm nguyên nhân CPU cao theo quy trình

Một quy trình có thể lặp lại:

1. Ghi nhận thời điểm, mức CPU, số replica, request rate, latency và container CPU quota.
2. Xác định JVM hay process khác đang dùng CPU bằng `jdk.CPULoad` và OS metrics.
3. Xem thread nào tiêu thụ CPU qua `jdk.ThreadCPULoad`.
4. Trên nền tảng phù hợp, thu `jdk.ExecutionSample` hoặc `jdk.CPUTimeSample`.
5. Kiểm tra event volume, sampling period, lost samples, failed stacks và biased samples.
6. Mở hot methods/call tree và tìm leaf methods có tỷ trọng cao.
7. Đối chiếu native frames, GC, lock, socket/file I/O và thread role.
8. Chọn một giả thuyết cụ thể: thuật toán, loop, serialization, native call, contention hay workload.
9. Thay đổi một yếu tố, chạy lại cùng benchmark.
10. So sánh CPU time, throughput, latency và profile sau tối ưu.

~~~mermaid
flowchart TD
    A["CPU cao hoặc throughput giảm"] --> B["Đối chiếu machine/JVM CPU"]
    B --> C["Chọn thread có CPU load cao"]
    C --> D{"Có native execution đáng kể?"}
    D -- "Không / nền tảng khác" --> E["ExecutionSample + ThreadCPULoad"]
    D -- "Có và chạy Linux" --> F["CPUTimeSample (experimental)"]
    E --> G["Hot methods / call tree"]
    F --> H["Kiểm lost, failed, biased samples"]
    H --> G
    G --> I["Tìm leaf method và caller"]
    I --> J["Đối chiếu GC, lock, I/O, native symbols"]
    J --> K["Đưa giả thuyết và tối ưu một yếu tố"]
    K --> L["Benchmark và ghi JFR lại"]
~~~

## 13. Tình huống thực tế: service Java gọi native crypto

Một service mã hóa payload trước khi ghi vào storage. Sau một lần nâng cấp thư viện, CPU tăng nhưng Java method profile chỉ cho thấy một số method wrapper ngắn.

Điều tra theo thứ tự:

- `jdk.CPULoad` xác nhận JVM process dùng CPU cao.
- `jdk.ThreadCPULoad` cho thấy worker threads của request tiêu thụ phần lớn CPU.
- `jdk.ExecutionSample` cho thấy stack dừng chủ yếu ở Java native bridge.
- Trên Linux, bật `jdk.CPUTimeSample` để thu cả native frames.
- CPU-time hot methods cho thấy phần lớn sample nằm trong native encryption routine.
- Kiểm tra build ID/symbols để xác định hàm native cụ thể.
- Đối chiếu kích thước payload, cipher configuration và số lần mã hóa mỗi request.

Giả thuyết có thể là thư viện native mới dùng thuật toán hoặc đường xử lý tốn CPU hơn. Bước tiếp theo là benchmark thư viện độc lập với payload giống nhau và so sánh cấu hình cipher. Không vội tăng số worker threads; nếu bottleneck là CPU, tăng concurrency có thể làm contention hoặc throttling nặng hơn.

## 14. Tình huống thực tế: CPU profile cao nhưng request không chậm

Một service batch xử lý nhiều công việc song song. CPU-time profile cho thấy một method chiếm tỷ lệ lớn, nhưng latency từng request vẫn đạt mục tiêu.

Điều này không tự động là lỗi. Cần hỏi:

- Method có tạo throughput cần thiết không?
- CPU có đang gần quota hoặc gây throttling không?
- P99 latency và queue backlog có tăng không?
- Có thể giảm chi phí method mà không làm tăng memory/GC?
- CPU time/request có giảm sau tối ưu không?

Tối ưu CPU chỉ có giá trị khi nó cải thiện một mục tiêu đo được: giảm chi phí hạ tầng, tăng throughput, giảm throttling hoặc cải thiện latency. Một hot method có thể là phần tính toán chính của nghiệp vụ và không có cách loại bỏ đáng kể.

## 15. Benchmark trước và sau tối ưu

Để xác minh một thay đổi, cần cố định:

- Cùng JDK vendor/build, JVM flags và garbage collector.
- Cùng CPU model/architecture hoặc cùng loại instance/container.
- Cùng CPU quota, memory limit và số replica.
- Cùng dataset, payload, concurrency và request rate.
- Cùng thời lượng warmup và measurement.
- Cùng loại recording và sampling throttle.

### 15.1. Chỉ số nên so sánh

| Chỉ số | Trả lời câu hỏi |
|---|---|
| CPU seconds/process | Process dùng tổng CPU bao nhiêu? |
| CPU seconds/request | Chi phí CPU cho một request có giảm không? |
| CPU utilization | Process có bão hòa CPU không? |
| Throughput | Có xử lý được nhiều công việc hơn không? |
| P50/P95/P99 latency | Tail latency có cải thiện không? |
| Hot-method share | Call path nào chiếm tỷ trọng sample lớn? |
| Lost/failed/biased samples | Chất lượng profile có đủ tốt không? |
| Allocation/GC | Tối ưu CPU có làm tăng memory pressure không? |
| Container throttling | Cgroup có giới hạn CPU khiến kết quả méo không? |

### 15.2. Không tối ưu chỉ theo tỷ lệ hot method

Nếu method A chiếm 50% CPU trước tối ưu và 70% sau tối ưu, điều đó không nhất thiết có nghĩa A chậm hơn. Có thể các method khác đã nhanh hơn khiến tỷ lệ của A tăng. Hãy so **CPU time tuyệt đối hoặc CPU time/request**, không chỉ tỷ lệ phần trăm trong flame graph.

### 15.3. Lặp lại và xem nhiễu

Chạy nhiều lần, dùng median hoặc phân bố thay vì chỉ lấy một lần chạy. Nếu CPUTimeSample recording có nhiều sample loss, thay đổi throttle hoặc workload trước khi kết luận. Cũng cần theo dõi CPU frequency scaling, noisy neighbors, cgroup throttling và background jobs.

## 16. Overhead và an toàn khi profiling

CPU-time profiling tạo thêm công việc cho sampler và ghi event. Overhead phụ thuộc CPU load, số thread, throttle, stack depth, native frames và thời lượng recording.

Nguyên tắc vận hành:

- Bắt đầu bằng recording ngắn trên staging/canary.
- Dùng throttle vừa phải, tăng độ chi tiết chỉ khi cần.
- Kiểm tra recording size và sample loss.
- Đo overhead so với baseline không bật CPUTimeSample.
- Không chạy benchmark CPU-sensitive đồng thời với nhiều công cụ profiler khác nếu chưa đánh giá tác động.
- Giới hạn quyền truy cập file `.jfr` và thời hạn lưu.
- Không ghi token, password, request body hoặc dữ liệu bí mật vào custom events.
- Scrub các system properties/environment events nhạy cảm trước khi chia sẻ recording.

JFR thường có overhead thấp với cấu hình phù hợp, nhưng không được mặc định mọi event profile đều miễn phí. Đặc biệt, không dùng profile nặng liên tục nếu chỉ cần điều tra một incident ngắn.

## 17. Nếu không chạy Linux hoặc JEP 509 không có sẵn

Không phải mọi môi trường đều có thể bật CPUTimeSample. Các lựa chọn hiện hành:

| Môi trường | Cách phân tích |
|---|---|
| Linux + JDK hỗ trợ JEP 509 | `jdk.CPUTimeSample` + `jdk.CPUTimeSamplesLost` |
| Windows/macOS | `jdk.ExecutionSample`, `jdk.ThreadCPULoad`, JMC |
| Java-only workload | `jdk.ExecutionSample` thường đủ để tìm hot methods |
| Native-heavy workload trên nền tảng không hỗ trợ JEP 509 | Dùng profiler native/platform phù hợp, sau đó đối chiếu JFR và symbols |
| Cần đo CPU time của một thread trong code test | `ThreadMXBean` nếu JVM hỗ trợ |

Đừng bật tùy chọn experimental rồi cho rằng nó hoạt động trên mọi OS. Kiểm tra `java -version`, hệ điều hành, `jfr metadata` và recording thực tế trước khi phân tích.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có `jdk.CPUTimeSample` | Event chưa bật, JDK/platform không hỗ trợ hoặc workload không dùng CPU | Kiểm JDK, Linux, setting và `jfr summary` |
| Có event nhưng không có stack | Stack capture thất bại hoặc native state không walk được | Kiểm field `failed`, runtime và symbols |
| CPU cao nhưng ExecutionSample thấp | CPU tiêu thụ trong native code hoặc sampler thiếu dữ liệu | Trên Linux thử CPUTimeSample nếu được hỗ trợ |
| CPUTimeSample không có trên Windows | JEP 509 Linux-only | Dùng ExecutionSample và profiler phù hợp nền tảng |
| `CPUTimeSamplesLost` tăng | Event emission vượt khả năng ghi hoặc throttle quá cao | Giảm tốc độ sampling, rút ngắn recording, kiểm storage |
| Nhiều sample biased | Sample có safepoint bias | Kiểm tỷ lệ biased và không kết luận từ profile ngắn |
| Hot methods khác nhau giữa hai lần chạy | Workload, CPU quota hoặc scheduling khác nhau | Cố định workload và môi trường |
| Native frame chỉ có địa chỉ | Thiếu symbol/debug information | Lấy symbol đúng build và symbolization |
| CPU profile cao nhưng latency ổn định | Workload CPU-bound nhưng vẫn trong capacity | Đánh giá CPU cost/request và SLO trước khi tối ưu |
| CPU thấp nhưng latency cao | Thread chờ I/O/lock hoặc dependency | Dùng JFR duration events và tracing |
| JFR không attach được | Sai PID, quyền hoặc container namespace | Chạy `jcmd` đúng host/container và user |
| Recording quá lớn | Throttle quá nhanh, thời lượng dài hoặc nhiều stack events | Điều chỉnh throttle/duration và event settings |

## 19. Bài tập thực hành

**Bài 1 — CPU time và wall-clock:** viết một method tính toán CPU-bound và một method chờ socket. So sánh wall-clock duration với thread CPU time; giải thích sự khác nhau.

**Bài 2 — ExecutionSample:** tạo workload Java tính toán lặp. Ghi JFR profile, xem `jdk.ExecutionSample` và tìm hot methods bằng JMC.

**Bài 3 — ThreadCPULoad:** tạo nhiều worker threads với workload khác nhau. Xác định thread tiêu thụ CPU cao bằng `jdk.ThreadCPULoad`, sau đó xem stack samples của chúng.

**Bài 4 — CPUTimeSample:** trên Linux và JDK hỗ trợ JEP 509, bật `jdk.CPUTimeSample`. Dùng `jfr view cpu-time-hot-methods` để phân tích kết quả.

**Bài 5 — Native code:** gọi một native function có workload CPU đáng kể qua JNI hoặc FFM. So sánh stack quan sát được bằng ExecutionSample và CPUTimeSample.

**Bài 6 — Sample quality:** kiểm tra `samplingPeriod`, `failed`, `biased` và `CPUTimeSamplesLost`. Thử hai throttle khác nhau và giải thích tác động đến event volume.

**Bài 7 — Call tree:** chọn một hot method, xác định self time/inclusive time, leaf frame và caller. Đề xuất thay đổi có cơ sở.

**Bài 8 — Không nhầm I/O:** tạo một request chờ remote service. Đối chiếu CPU-time profile với SocketRead duration và giải thích vì sao request chậm không đồng nghĩa CPU cao.

**Bài 9 — Benchmark:** tối ưu một method CPU-bound, chạy cùng workload trước/sau và so CPU seconds/request, throughput, P99 latency cùng profile.

**Bài 10 — Nền tảng:** chạy thử trên Linux và một OS không hỗ trợ JEP 509. Ghi lại event nào khả dụng và chọn phương pháp thay thế.

## 20. Checklist hoàn thành

- [ ] Phân biệt CPU time, wall-clock duration và CPU utilization.
- [ ] Hiểu giới hạn của `jdk.ExecutionSample` đối với native execution.
- [ ] Nêu đúng JEP 509 là experimental và Linux-only trong JDK 25/26.
- [ ] Biết `jdk.CPUTimeSample` không bật mặc định.
- [ ] Biết `jdk.CPUTimeSamplesLost` và cách kiểm tra sample loss.
- [ ] Đọc `samplingPeriod`, `failed`, `biased` và stack trace.
- [ ] Biết cấu hình `jdk.CPUTimeSample#enabled` và `throttle`.
- [ ] Dùng `jfr view cpu-time-hot-methods` và `jfr print`.
- [ ] Phân biệt `jdk.ThreadCPULoad` với CPU-time stack samples.
- [ ] Biết dùng JEP 518 để hiểu cơ chế cooperative stack sampling.
- [ ] Đọc hot methods, self time, inclusive time và call tree.
- [ ] Kiểm tra native symbols khi ứng dụng gọi JNI/FFM.
- [ ] Đối chiếu CPU profile với GC, locks, I/O và container CPU quota.
- [ ] Đo overhead và lặp benchmark trước/sau tối ưu.
- [ ] Không xem sample count là invocation count hoặc CPU seconds tuyệt đối.
- [ ] Có phương án profiling phù hợp khi không chạy Linux.

## Tài liệu tham khảo chính thức

- [JEP 509 — JFR CPU-Time Profiling (Experimental)](https://openjdk.org/jeps/509): mục tiêu và phạm vi của CPU-time profiling trong JDK 25.
- [JEP 518 — JFR Cooperative Sampling](https://openjdk.org/jeps/518): cơ chế stack walking tại safepoint và giảm safepoint bias.
- [Oracle JDK 25 — Significant Changes](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): xác nhận CPU-time profiling trên Linux là experimental.
- [Oracle JDK 26 — Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/jdk-migration-guide.pdf): tiếp tục đánh dấu JFR CPU-time profiling là experimental trong JDK 26.
- [Oracle JDK 25 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html): cách đọc `jdk.CPULoad`, `jdk.ThreadCPULoad` và method samples.
- [Oracle JDK 25 — jcmd command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): bắt đầu, kiểm tra, dump và dừng JFR recording.
- [Oracle JDK 25 — jfr command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `jfr print`, `jfr view`, `jfr metadata` và `jfr summary`.
- [What's new for JFR in JDK 25 — JDK Flight Recorder maintainer](https://egahlin.github.io/2025/05/31/whats-new-in-jdk-25.html): ví dụ bật CPUTimeSample và phân biệt ExecutionSample/native sampling.
- [JDK 26–27: What's new in JFR — JDK Flight Recorder maintainer](https://egahlin.github.io/2026/05/26/whats-new-in-jdk-26-27.html): bối cảnh duy trì JFR sau JDK 25.
- [Java SE 26 — ThreadMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html): API đo CPU time của thread và giới hạn hỗ trợ.

## Kết luận

**CPU-time profiling giúp trả lời method và call path nào tiêu thụ CPU, đặc biệt khi một phần công việc chạy trong native code.** JFR thông thường với `jdk.ExecutionSample` vẫn là lựa chọn đa nền tảng cho Java execution; `jdk.ThreadCPULoad` và `jdk.CPULoad` giúp tìm thread/process có CPU cao. Trên Linux, JEP 509 bổ sung `jdk.CPUTimeSample` để lấy mẫu theo CPU time và quan sát cả Java/native execution.

JEP 509 vẫn là tính năng experimental trong tài liệu JDK 26, chỉ dành cho Linux và không bật mặc định. Hãy bật có chủ đích, kiểm tra lost/failed/biased samples, đọc hot methods cùng call tree và đối chiếu với workload, GC, I/O, native symbols và container quota. **Kết luận tối ưu chỉ đáng tin khi profile có chất lượng, phép đo được lặp lại và CPU cost/request hoặc mục tiêu hiệu năng thực sự cải thiện.**
