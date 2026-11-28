# Cơ chế ghi sự kiện JFR và cách chọn cấu hình ghi theo mục tiêu quan sát

## 1. Mục tiêu và bối cảnh

Khi một ứng dụng Java chạy chậm, tăng bộ nhớ hoặc thỉnh thoảng xuất hiện độ trễ cao, chỉ đọc log thường không đủ để xác định nguyên nhân. Ta cần biết JVM đang làm gì trong khoảng thời gian sự cố: thread nào sử dụng CPU, phương thức nào xuất hiện nhiều trong stack, garbage collection kéo dài bao lâu, thread đang chờ lock hay I/O, lớp nào được nạp và thao tác nào tạo nhiều object.

**Java Flight Recorder (JFR)** là hệ thống ghi sự kiện và quan sát hiệu năng tích hợp trong JDK. JFR thu thập các sự kiện từ JVM, thư viện nền tảng và mã ứng dụng; dữ liệu được lưu thành tệp nhị phân **.jfr** hoặc cung cấp qua API stream. Các công cụ như **jfr** và **JDK Mission Control (JMC)** giúp lọc, tổng hợp và phân tích recording.

Bài **Cơ chế ghi sự kiện JFR và cách chọn cấu hình ghi theo mục tiêu quan sát**, thuộc chương **Lấy mẫu JFR** của lộ trình **JAVA_VERSION_JAVA25**, tập trung vào:

1. Phân biệt event-based recording, periodic sampling và duration events.
2. Hiểu event settings như enabled, period, threshold và stackTrace.
3. Chọn cấu hình **default.jfc**, **profile.jfc** hoặc tạo custom JFC theo mục tiêu.
4. Bắt đầu, kiểm tra, dump và dừng recording khi khởi động hoặc khi ứng dụng đang chạy.
5. Phân tích recording bằng lệnh **jfr**, JMC và API Java.
6. Hiểu các cải tiến JFR của Java 25: **JEP 518 Cooperative Sampling**, **JEP 509 CPU-Time Profiling (Experimental)** và **JEP 520 Method Timing & Tracing**.
7. Kiểm soát overhead, dung lượng, dữ liệu nhạy cảm và chất lượng mẫu.

**Phạm vi hiện hành:** JFR đã là một phần của các bản OpenJDK/JDK hiện đại và dùng được trong Java 25 mà không cần mở khóa tính năng thương mại cũ. Không dùng các hướng dẫn lịch sử yêu cầu **-XX:+UnlockCommercialFeatures** hoặc **-XX:+FlightRecorder**; đó không phải quy trình cần thiết cho JDK 25.

## 2. Mô hình hoạt động của JFR

JFR thu nhận các sự kiện có thời điểm, thời lượng và trường dữ liệu. Một event có thể được phát ra khi một việc xảy ra (ví dụ nạp class), theo chu kỳ (ví dụ lấy mẫu CPU load), hoặc trong một khoảng thời gian (ví dụ một lần garbage collection).

~~~mermaid
flowchart TD
    A["Ứng dụng và HotSpot JVM"] --> B["JFR event sources"]
    B --> C["Event settings: enabled / period / threshold / stackTrace"]
    C --> D["JFR recording"]
    D --> E["Repository và file .jfr"]
    E --> F["jfr CLI"]
    E --> G["JDK Mission Control"]
    D --> H["RecordingStream / EventStream API"]
    F --> I["Summary / views / filtered events"]
    G --> J["Timeline / flame graph / event analysis"]
~~~

Một recording có thể chứa nhiều loại event cùng lúc. Ví dụ, một lần ghi có thể chứa **jdk.ExecutionSample**, **jdk.GarbageCollection**, **jdk.ThreadPark**, **jdk.FileRead** và event nghiệp vụ do ứng dụng tự định nghĩa.

| Thành phần | Vai trò |
| --- | --- |
| **Event type** | Định nghĩa tên event, trường dữ liệu và metadata. |
| **Event instance** | Một lần event được ghi, kèm thời điểm, thread và các field tương ứng. |
| **Event setting** | Quy định event được bật hay tắt, tần suất, ngưỡng và stack trace. |
| **Recording** | Một phiên thu thập event với tập settings cụ thể. |
| **JFC configuration** | Tệp XML định nghĩa tập settings có thể tái sử dụng. |
| **Repository/chunk** | Nơi JFR lưu dữ liệu trong lúc recording; file cuối cùng thường có đuôi .jfr. |
| **Consumer** | Công cụ hoặc API đọc và phân tích dữ liệu recording. |

JFR là hệ thống event recording có thể dùng để profiling và monitoring. Nó không phải một log text thay thế Logback/SLF4J, cũng không phải metric backend thay thế Micrometer/Prometheus. Mỗi công cụ trả lời một nhóm câu hỏi khác nhau; có thể kết hợp chúng bằng timestamp, thread, trace ID hoặc các trường ngữ cảnh phù hợp.

## 3. Ba kiểu thu thập cần phân biệt

### 3.1. Event theo hành động

Event được phát khi một hành động cụ thể xảy ra. Ví dụ:

- **jdk.ClassLoad** khi JVM nạp lớp.
- **jdk.GarbageCollection** khi một chu kỳ GC diễn ra.
- **jdk.JavaMonitorEnter** khi thread chờ monitor.
- **jdk.FileRead** hoặc **jdk.SocketRead** khi có thao tác I/O tương ứng.

Nếu bật một event có tần suất cao, recording có thể tăng nhanh về số lượng và dung lượng. Nên chọn đúng nhóm event theo giả thuyết đang điều tra.

### 3.2. Periodic sampling

Sampling chụp trạng thái thực thi tại các thời điểm lấy mẫu. **jdk.ExecutionSample** là event quan trọng khi phân tích phương thức đang thực thi Java code. JFR lấy mẫu stack của thread theo chu kỳ, sau đó công cụ tổng hợp số mẫu để ước lượng nơi chương trình dành thời gian.

Sampling là thống kê. Một phương thức xuất hiện trong nhiều mẫu thường có khả năng chiếm nhiều thời gian thực thi, nhưng số mẫu không phải phép đo chính xác số lần gọi hoặc thời gian tuyệt đối của mọi lời gọi.

### 3.3. Duration events

Một số event có thời điểm bắt đầu và thời lượng, chẳng hạn GC pause, monitor wait hoặc file/socket operation. Setting **threshold** có thể bỏ qua những event ngắn hơn một ngưỡng, giúp tập trung vào các hoạt động có khả năng ảnh hưởng hiệu năng.

| Kiểu thu thập | Câu hỏi phù hợp | Rủi ro nếu cấu hình quá rộng |
| --- | --- | --- |
| Event theo hành động | Việc gì đã xảy ra? | Số event lớn khi hành động lặp lại liên tục. |
| Sampling | Stack/phương thức nào thường xuất hiện trong lúc thực thi? | Mẫu quá dày làm tăng overhead và dung lượng; mẫu quá thưa có thể bỏ lỡ đoạn ngắn. |
| Duration event | Một thao tác kéo dài bao lâu? | Không đặt threshold có thể thu nhiều event nhỏ không cần thiết. |

## 4. Các event lấy mẫu quan trọng

### 4.1. jdk.ExecutionSample

**jdk.ExecutionSample** ghi snapshot stack của thread đang thực thi Java code tại thời điểm lấy mẫu. Đây là lựa chọn thông dụng để tìm hot methods bằng sampling.

Điểm cần nhớ:

- Thread đang thực thi Java code có thể xuất hiện trong mẫu.
- Thread đang chờ I/O, ngủ hoặc chờ lock thường không được tính như một thread đang tiêu thụ CPU Java trong mẫu này.
- Khoảng lấy mẫu do cấu hình JFC/event setting quyết định; **default.jfc** và **profile.jfc** có thể dùng mức khác nhau.
- Mẫu stack chỉ cho biết trạng thái tại thời điểm lấy mẫu, không phải bản ghi đầy đủ mọi method invocation.

### 4.2. JEP 518 — Cooperative Sampling trong Java 25

JEP 518 thay đổi cơ chế JFR lấy mẫu stack để tăng độ ổn định. Thay vì dựa vào heuristic nguy hiểm khi parse stack tại vị trí bất kỳ, HotSpot ghi nhận yêu cầu lấy mẫu rồi xử lý stack tại **safepoint**, đồng thời điều chỉnh để giảm **safepoint bias**.

Lợi ích:

- Giảm rủi ro khi đọc stack ở vị trí mà metadata không đảm bảo hợp lệ.
- Giúp quá trình sampling ổn định hơn và có khả năng mở rộng tốt hơn.
- Giữ mục tiêu lấy mẫu thống kê mà không yêu cầu ứng dụng tự sửa mã nguồn.

JEP 518 cũng bổ sung event **jdk.SafepointLatency** để quan sát độ trễ thread đi tới safepoint. Event này hữu ích khi điều tra safepoint kéo dài hoặc thread mất nhiều thời gian mới phản hồi yêu cầu safepoint.

~~~bash
java -XX:StartFlightRecording:jdk.SafepointLatency#enabled=true,filename=safepoint.jfr -jar app.jar
jfr print --events jdk.SafepointLatency safepoint.jfr
~~~

**Cooperative sampling không có nghĩa mọi bias biến mất.** JEP 518 giảm rủi ro và cải thiện độ ổn định; sampling vẫn là phép đo thống kê, có thể có giới hạn ở một số vùng mã hoặc trạng thái thread.

### 4.3. JEP 509 — CPU-Time Profiling (Experimental)

Java 25 bổ sung event **jdk.CPUTimeSample** ở trạng thái **experimental**. Trên Linux có hỗ trợ, event này lấy mẫu dựa trên **CPU time** thay vì chỉ dựa vào thời gian thực đã trôi qua; nhờ vậy có thể phản ánh cả thời gian thread thực thi Java và native code.

Ví dụ bật event khi khởi chạy:

~~~bash
java -XX:StartFlightRecording:jdk.CPUTimeSample#enabled=true,filename=cpu-time.jfr -jar app.jar
jfr view cpu-time-hot-methods cpu-time.jfr
~~~

Event này:

- Không được bật mặc định trong cấu hình thông thường.
- Là tính năng experimental trong Java 25.
- Phụ thuộc Linux và hỗ trợ của kernel/JDK vendor; không giả định dùng được trên Windows hoặc macOS.
- Có thể cấu hình mức lấy mẫu/throttle để điều tiết số event.
- Có event **jdk.CPUTimeSamplesLost** để ghi nhận số mẫu bị mất.

Khi cần kiểm tra độ tin cậy, xem cả **jdk.CPUTimeSample** và **jdk.CPUTimeSamplesLost**. Không coi CPU-time profile experimental là thay thế mặc định cho ExecutionSample trên mọi nền tảng.

### 4.4. JEP 520 — Method Timing & Tracing

Java 25 có thêm **jdk.MethodTiming** và **jdk.MethodTrace** để đo thời gian và ghi dấu các lần gọi method thông qua instrumentation. Đây là cơ chế khác với sampling định kỳ:

- **ExecutionSample** lấy mẫu stack ở các thời điểm.
- **MethodTiming/MethodTrace** quan sát method invocation được chọn và có thể ghi thời lượng hoặc trace.

Method tracing có thể tạo rất nhiều dữ liệu nếu áp dụng cho toàn bộ ứng dụng. Chỉ bật cho class/method cụ thể bằng filter phù hợp, trong một khoảng ngắn và với workload kiểm thử. Khi câu hỏi là “phương thức nào tiêu thụ phần lớn CPU?”, bắt đầu bằng sampling thường hợp lý hơn; khi cần biết “một method cụ thể được gọi bao nhiêu lần và mỗi lần mất bao lâu?”, method timing/tracing có thể phù hợp.

## 5. Cấu hình JFC: default, profile và custom

JFR cung cấp hai cấu hình có sẵn trong **JAVA_HOME/lib/jfr**:

| Cấu hình | Mục tiêu | Đặc điểm |
| --- | --- | --- |
| **default.jfc** | Continuous recording và quan sát dài hạn. | Thu tập dữ liệu hữu ích với overhead thấp; phù hợp giữ recording liên tục trong production. |
| **profile.jfc** | Profiling ngắn hạn khi điều tra. | Thu nhiều thông tin hơn default; overhead và dung lượng có thể cao hơn. |
| **custom.jfc** | Mục tiêu riêng của hệ thống. | Chỉ bật event và setting cần thiết, dựa trên default/profile làm nền. |

**Lựa chọn thực tế:**

- Theo dõi thường xuyên, giữ vài giờ dữ liệu gần nhất: bắt đầu với **default**.
- Điều tra CPU, allocation, lock hoặc startup trong một khoảng ngắn: dùng **profile**.
- Cần một event đặc biệt hoặc thay period/threshold: tạo **custom JFC**.
- Không dùng một profile dày trong thời gian dài chỉ vì muốn có “nhiều dữ liệu hơn”; dữ liệu dư thừa làm tăng chi phí ghi và khó phân tích.

Nếu không chỉ định settings, JVM sử dụng **default.jfc** theo cấu hình mặc định của JFR. Không nên dùng cấu hình rỗng/thu tất cả event như lựa chọn production mặc định; có thể tạo recording rất lớn và tăng overhead đáng kể.

## 6. Hiểu bốn event settings chính

Mỗi event có thể được cấu hình bằng các setting sau:

| Setting | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **enabled** | Bật/tắt event. | true / false |
| **period** | Khoảng thời gian giữa các lần phát event định kỳ. | 10 ms, 1 s, everyChunk |
| **threshold** | Chỉ ghi event duration đạt hoặc vượt ngưỡng. | 10 ms, 100 ms |
| **stackTrace** | Có ghi stack trace tại vị trí event được commit hay không. | true / false |

**period** chỉ áp dụng cho event có tính định kỳ; không phải mọi event đều có thể lấy mẫu bằng period. **threshold** thường có ý nghĩa với event có thời lượng. Bật stack trace có thể giúp tìm nguồn gọi nhưng làm tăng dữ liệu và chi phí.

Ví dụ điều chỉnh một số setting ngay khi khởi động:

~~~bash
java -XX:StartFlightRecording:filename=focused.jfr,settings=profile,jdk.ExecutionSample#period=10ms,jdk.FileRead#enabled=true,jdk.FileRead#threshold=10ms -jar app.jar
~~~

Trong ví dụ, sampling period được đặt rõ ràng cho ExecutionSample; FileRead chỉ được bật và chỉ ghi các thao tác đạt threshold. Giá trị cụ thể cần được thử trên workload thật, không có một period tối ưu cho mọi ứng dụng.

## 7. Bắt đầu recording ngay khi ứng dụng khởi chạy

### 7.1. Profiling trong khoảng thời gian cố định

Đây là cách thuận tiện khi có thể khởi động lại ứng dụng trong môi trường test/staging:

~~~bash
java -XX:StartFlightRecording:filename=profile.jfr,settings=profile,duration=60s -jar app.jar
~~~

JVM bắt đầu recording khi khởi động, tự dừng sau 60 giây và ghi file **profile.jfr**. Với ứng dụng có startup chậm, có thể dùng **delay** để bắt đầu sau một khoảng:

~~~bash
java -XX:StartFlightRecording:filename=after-startup.jfr,settings=profile,delay=30s,duration=60s -jar app.jar
~~~

### 7.2. Continuous recording cho production

Với tiến trình chạy lâu, cấu hình default và giới hạn tuổi/dung lượng recording:

~~~bash
java -XX:StartFlightRecording:filename=continuous.jfr,settings=default,disk=true,maxage=6h,maxsize=500M,dumponexit=true -jar app.jar
~~~

Recording giữ dữ liệu trong một cửa sổ có giới hạn; khi vượt giới hạn, chunk cũ có thể bị loại để nhường chỗ cho dữ liệu mới. Khi JVM dừng, **dumponexit=true** giúp ghi recording ra file đã chỉ định.

Nếu chỉ cần ghi tạm trong bộ nhớ và dump khi có sự cố, có thể cân nhắc chế độ phù hợp với retention/disk settings; cần kiểm tra dung lượng repository và hành vi dump của đúng cấu hình. Đối với production, hãy đặt **maxage** hoặc **maxsize** để recording không tăng vô hạn.

## 8. Bắt đầu recording trên JVM đang chạy bằng jcmd

Không phải lúc nào cũng có thể restart production. Khi có quyền chẩn đoán phù hợp và jcmd cùng user/host có thể attach tới tiến trình:

~~~bash
# Liệt kê các JVM mà jcmd có thể quan sát
jcmd

# Bắt đầu recording profiling trong 2 phút
jcmd 12345 JFR.start name=incident settings=profile duration=2m filename=incident.jfr

# Kiểm tra recording đang chạy
jcmd 12345 JFR.check verbose=true

# Dump snapshot hiện có mà vẫn giữ recording chạy
jcmd 12345 JFR.dump name=incident filename=incident-snapshot.jfr

# Dừng recording và ghi file cuối
jcmd 12345 JFR.stop name=incident filename=incident-final.jfr
~~~

Thay **12345** bằng PID của JVM cần quan sát. Các lệnh dump và stop có mục tiêu khác nhau: dump lấy bản ghi tại thời điểm hiện tại; stop kết thúc recording. Nếu chỉ muốn chụp dữ liệu rồi tiếp tục theo dõi, dùng dump.

Với continuous recording, có thể khởi động recording mặc định:

~~~bash
jcmd 12345 JFR.start name=continuous settings=default maxage=6h maxsize=500M
~~~

Sau khi sự cố xảy ra, dump dữ liệu gần nhất:

~~~bash
jcmd 12345 JFR.dump name=continuous filename=incident-last-hours.jfr
~~~

**Lưu ý vận hành:** quyền attach, container PID namespace, user chạy JVM, quyền ghi file và chính sách bảo mật có thể ảnh hưởng khả năng dùng jcmd. Không attach tùy tiện vào tiến trình không thuộc quyền quản trị của bạn.

## 9. Tạo cấu hình custom bằng công cụ jfr configure

Từ các JDK hiện đại, nên dùng **jfr configure** để tạo JFC tùy chỉnh thay vì sửa trực tiếp file default/profile đi kèm JDK.

Ví dụ tạo cấu hình dựa trên profile, lấy mẫu ExecutionSample mỗi 10 ms và bật FileRead với threshold 10 ms:

~~~bash
jfr configure --input profile.jfc --output focused.jfc jdk.ExecutionSample#period=10ms jdk.FileRead#enabled=true jdk.FileRead#threshold=10ms
~~~

Kiểm tra cấu hình:

~~~bash
jfr configure --input focused.jfc --output verified.jfc --verbose
~~~

Sau đó dùng:

~~~bash
java -XX:StartFlightRecording:filename=focused.jfr,settings=focused.jfc,duration=60s -jar app.jar
~~~

Các option và event setting được truyền dưới dạng **name=value**. Để xem cú pháp chính xác của bản JDK đang cài:

~~~bash
jfr help configure
~~~

Có thể dùng **--interactive** để tạo cấu hình bằng câu hỏi. Nếu dự án có custom JFC, nên đưa file cấu hình đó vào version control, ghi rõ mục tiêu, owner, event được bật và lý do chọn period/threshold. Không chỉnh sửa file **default.jfc** hoặc **profile.jfc** trực tiếp trong thư mục JDK vì bản cập nhật JDK có thể thay chúng.

## 10. Tạo recording bằng Java API

Khi cần tự động ghi trong test, integration harness hoặc một công cụ nội bộ, dùng **jdk.jfr.Recording**:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public final class RecordingApiDemo {

    public static void main(String[] args) throws Exception {
        Configuration profile = Configuration.getConfiguration("profile");

        try (Recording recording = new Recording(profile)) {
            recording.setName("checkout-profile");
            recording.setMaxAge(Duration.ofMinutes(5));
            recording.setMaxSize(100L * 1024 * 1024);

            recording.enable("jdk.ExecutionSample")
                    .withPeriod(Duration.ofMillis(10));
            recording.enable("jdk.FileRead")
                    .withThreshold(Duration.ofMillis(10))
                    .withoutStackTrace();

            recording.start();

            runWorkload();

            recording.stop();
            recording.dump(Path.of("checkout-profile.jfr"));
        }
    }

    private static void runWorkload() {
        // Thay bằng workload kiểm thử thực tế.
    }
}
~~~

Ví dụ cấu hình event trước khi gọi **start()** để recording bắt đầu với một bộ settings nhất quán. **setMaxAge** và **setMaxSize** giới hạn dữ liệu được giữ trong repository; **dump** ghi dữ liệu ra file sau khi recording đã dừng.

Nếu dùng module system, module chứa code này cần khai báo **requires jdk.jfr;** trong module-info. Trên classpath, chỉ cần dùng JDK có module JFR.

### Tự định nghĩa application event

JFR không chỉ ghi sự kiện JVM. Ứng dụng có thể định nghĩa event để đưa dữ liệu nghiệp vụ vừa đủ vào cùng timeline:

~~~java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

public final class OrderEvents {

    @Name("com.example.OrderProcessed")
    @Label("Order Processed")
    @Category({"Application", "Orders"})
    static class OrderProcessed extends Event {
        @Label("Order Type")
        String orderType;

        @Label("Result")
        String result;
    }

    static void record(String orderType, String result) {
        OrderProcessed event = new OrderProcessed();
        if (event.isEnabled()) {
            event.orderType = orderType;
            event.result = result;
            event.commit();
        }
    }
}
~~~

Chỉ ghi các trường cần cho chẩn đoán, ví dụ loại nghiệp vụ hoặc trạng thái tổng quát. Tránh ghi access token, mật khẩu, nội dung request đầy đủ, dữ liệu cá nhân hoặc định danh khách hàng nếu không có cơ sở và chính sách lưu trữ phù hợp.

## 11. Đọc recording bằng công cụ jfr

JDK cung cấp công cụ **jfr** để xem metadata, thống kê, lọc event và tổng hợp dữ liệu:

~~~bash
# Thống kê recording: thời gian, dung lượng, số event
jfr summary profile.jfr

# Xem các hot methods từ sampling
jfr view hot-methods profile.jfr

# In riêng execution samples
jfr print --events jdk.ExecutionSample profile.jfr

# In một nhóm event GC
jfr print --categories GC profile.jfr

# Xem metadata event có trong recording
jfr metadata profile.jfr
~~~

Các view có sẵn phụ thuộc phiên bản JDK và loại event trong recording. Dùng:

~~~bash
jfr help view
jfr view all-views profile.jfr
jfr view types profile.jfr
~~~

Nếu cần output cho xử lý tự động:

~~~bash
jfr print --json --events jdk.ExecutionSample profile.jfr
~~~

**Không nên in toàn bộ event của một recording lớn ra terminal** nếu không cần thiết. Dùng filter theo event/category, stack depth và time range phù hợp để giảm output.

### Phân tích bằng JDK Mission Control

JMC cung cấp giao diện để xem timeline, hot methods, allocation, GC, thread states, locks và các event tùy chỉnh. Một quy trình thông dụng:

1. Mở file **.jfr** trong JMC.
2. Xem overview để biết thời lượng, số event và chất lượng dữ liệu.
3. Mở **Method Profiling/Hot Methods** để tìm stack xuất hiện nhiều.
4. Kiểm tra **Threads** để phân biệt thread chạy CPU với thread chờ lock/I/O.
5. Xem **Garbage Collections/Memory** nếu nghi ngờ allocation hoặc GC.
6. Chọn một khoảng thời gian cụ thể rồi đối chiếu event liên quan.

JMC là công cụ phân tích riêng, không phải thành phần bắt buộc phải chạy trong process production. Có thể dùng CLI **jfr** trong CI để kiểm tra file và JMC ở máy phân tích.

## 12. Event streaming khi cần quan sát liên tục trong code

**RecordingStream** cho phép nhận event trong cùng JVM mà không cần chờ tạo file rồi mới phân tích:

~~~java
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.consumer.RecordingStream;

public final class JfrStreamDemo {

    public static void main(String[] args) throws Exception {
        Configuration config = Configuration.getConfiguration("default");

        try (var stream = new RecordingStream(config)) {
            stream.enable("jdk.CPULoad")
                    .withPeriod(Duration.ofSeconds(1));
            stream.enable("jdk.GarbageCollection");

            stream.onEvent("jdk.CPULoad", event ->
                    System.out.println("CPU load event: " + event));
            stream.onEvent("jdk.GarbageCollection", event ->
                    System.out.println("GC event: " + event));

            stream.startAsync();
            Thread.sleep(10_000);
        }
    }
}
~~~

Trong ví dụ, stream sử dụng default configuration, tăng chu kỳ CPULoad lên một giây, đăng ký callback cho hai event và chạy bất đồng bộ trong mười giây. Khi rời try-with-resources, stream được đóng.

Callback nên xử lý ngắn gọn. Nếu callback thực hiện I/O chậm hoặc xử lý dữ liệu nặng, chính consumer có thể trở thành điểm nghẽn. Khi cần phân tích sâu, nên ghi recording ra file và xử lý ở một pipeline riêng.

**RecordingStream** phù hợp với công cụ quan sát hoặc integration test. Với thu thập từ JVM từ xa qua JMX, xem **RemoteRecordingStream** và module **jdk.management.jfr**; cần xác thực và phân quyền endpoint quản trị.

## 13. Chọn cấu hình theo mục tiêu quan sát

Không có một cấu hình tối ưu cho mọi tình huống. Bắt đầu từ câu hỏi cần trả lời:

| Mục tiêu | Cấu hình/nhóm event nên bắt đầu | Cách đọc kết quả |
| --- | --- | --- |
| Theo dõi dài hạn, cần dữ liệu gần thời điểm sự cố | **default.jfc**, continuous recording, maxage/maxsize | Dump recording sau sự cố, đối chiếu timeline và event gần thời điểm lỗi. |
| Tìm phương thức tiêu thụ CPU Java | **profile.jfc**, jdk.ExecutionSample | Hot methods, stack traces, sample distribution. |
| Tìm CPU time kể cả native code trên Linux | **jdk.CPUTimeSample** (experimental Java 25) | CPU-time hot methods và CPUTimeSamplesLost. |
| Điều tra safepoint latency | **jdk.SafepointLatency** | Stack và thời gian thread đạt safepoint. |
| Tìm GC pause hoặc allocation pressure | Event GC/allocation trong profile hoặc custom JFC | GC timeline, allocation by site/class. |
| Tìm thread contention | JavaMonitorEnter, ThreadPark, ThreadSleep và các event liên quan | Thread states, stack trace và thời lượng chờ. |
| Tìm I/O chậm | FileRead/FileWrite/SocketRead/SocketWrite với threshold hợp lý | Event duration, thread và stack trace. |
| Đo một method cụ thể | JEP 520 MethodTiming/MethodTrace với filter hẹp | Lần gọi, thời lượng và stack theo method mục tiêu. |
| Theo dõi logic nghiệp vụ riêng | Custom JFR Event | Ghép timeline nghiệp vụ với event JVM. |

### Một số câu hỏi giúp chọn nhanh

- Nếu chỉ biết ứng dụng chậm nhưng chưa biết nguyên nhân: bắt đầu với **profile.jfc** trong khoảng ngắn.
- Nếu sự cố hiếm và cần giữ dữ liệu trước khi xảy ra: bật **default.jfc** continuous recording có giới hạn retention.
- Nếu nghi CPU cao: xem ExecutionSample trước; chỉ thử CPUTimeSample khi chạy Linux và chấp nhận trạng thái experimental.
- Nếu CPU thấp nhưng request chậm: tập trung thread waiting, monitor, socket/file I/O, GC pause và dependency latency.
- Nếu đã xác định một method nghi vấn: cân nhắc MethodTiming/MethodTrace hoặc custom event với phạm vi hẹp.

## 14. Overhead, tần suất và chất lượng mẫu

### 14.1. Tần suất lấy mẫu

Sampling interval càng ngắn thì số mẫu càng nhiều, khả năng nhìn thấy đoạn thực thi ngắn càng cao, nhưng overhead và kích thước recording cũng có thể tăng. Interval quá dài có thể bỏ lỡ method chỉ chạy trong thời gian ngắn; interval quá ngắn có thể làm thay đổi chính workload đang đo.

Không nên diễn giải một lần sample như một lời gọi method. Để đọc kết quả:

- Xem tỷ lệ và số lượng sample trong cùng recording.
- Kiểm tra thời lượng recording và khoảng thời gian thực tế có workload.
- So sánh nhiều lần chạy có cùng điều kiện.
- Đọc stack và trạng thái thread, không chỉ nhìn một tên method ở đầu bảng.

### 14.2. Threshold và stack trace

Threshold giúp loại bỏ event duration quá ngắn. Nếu đặt quá cao, những thao tác quan trọng nhưng ngắn sẽ biến mất. Nếu đặt quá thấp hoặc bằng 0 cho event có tần suất rất lớn, recording có thể tăng nhanh.

Stack trace giúp xác định call site nhưng cũng làm tăng chi phí và dữ liệu. Với event chỉ cần tổng hợp số lượng/thời lượng, có thể tắt stack trace. Với event hiếm hoặc cần tìm caller, giữ stack trace có thể đáng giá.

### 14.3. Overhead không phải hằng số

JFR thường được thiết kế để dùng trong production, nhưng overhead phụ thuộc event settings, period, stack depth, recording duration, số thread, event rate và loại workload. **default.jfc** có mục tiêu overhead thấp cho continuous recording; **profile.jfc** thu nhiều dữ liệu hơn và có tác động lớn hơn. Hãy đo overhead trên staging với workload gần production trước khi bật cấu hình dày ở hệ thống quan trọng.

## 15. Bảo mật và quyền riêng tư của recording

File **.jfr** có thể chứa:

- Tên class, package, method và đường dẫn stack.
- Tên thread, host/process metadata và thông tin môi trường.
- Chuỗi hoặc trường do custom event của ứng dụng ghi.
- Dữ liệu có thể giúp suy ra cấu trúc nội bộ hoặc hành vi nghiệp vụ.

Do đó:

1. Hạn chế quyền đọc file recording; không đưa file production lên kho công khai.
2. Không ghi password, token, session cookie, secret hoặc nội dung request nhạy cảm vào custom event.
3. Dùng dữ liệu giả lập/ẩn danh trong training và profiling nếu có thể.
4. Giới hạn **maxage**, **maxsize**, thời gian lưu và quy trình xóa.
5. Khi chia sẻ file để hỗ trợ, lọc event hoặc scrub dữ liệu không cần thiết bằng công cụ JFR phù hợp.
6. Không bật path-to-GC-roots nếu không điều tra memory leak; tính năng này có thể tốn thời gian đáng kể.
7. Bảo vệ jcmd/JMX/remote recording bằng quyền hệ điều hành và xác thực phù hợp.

Ví dụ dùng công cụ scrub để tạo file đã lọc:

~~~bash
jfr scrub --exclude-events "com.example.SensitiveEvent" production.jfr production-scrubbed.jfr
~~~

Scrub giúp loại event theo bộ lọc; nó không tự bảo đảm mọi dữ liệu nhạy cảm trong event còn lại đã được ẩn danh. Hãy kiểm tra recording đầu ra trước khi chia sẻ.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không thấy file .jfr sau khi chạy | Recording chưa dừng, thiếu dumponexit hoặc đường dẫn không ghi được. | Dùng duration/filename rõ ràng, stop/dump đúng recording, kiểm tra quyền thư mục. |
| File có nhưng không có ExecutionSample | Profile không được bật hoặc workload không thực thi Java code trong khoảng ghi. | Kiểm tra settings, period, thời lượng và workload. |
| Không thấy thread đang chờ I/O trong ExecutionSample | ExecutionSample lấy mẫu thread thực thi Java code. | Xem event socket/file I/O, ThreadPark hoặc thread state. |
| Recording quá lớn | Bật quá nhiều event, sampling quá dày hoặc không giới hạn retention. | Chuyển về default, tăng period/threshold, giới hạn maxage/maxsize. |
| Profile không có stack trace | Event setting stackTrace đang tắt hoặc event không hỗ trợ stack như mong muốn. | Kiểm tra JFC và cấu hình stackTrace cho event đó. |
| CPUTimeSample không xuất hiện | Event experimental chưa bật, nền tảng không phải Linux hoặc runtime không hỗ trợ. | Xác minh JDK/vendor/kernel, bật event và kiểm tra metadata. |
| CPUTimeSamplesLost tăng | Bộ lấy mẫu mất mẫu dưới tải hoặc giới hạn hệ thống. | Xem throttle, tải CPU, kernel và độ tin cậy trước khi diễn giải profile. |
| jcmd không attach được | Sai PID, khác user, container namespace hoặc attach bị hạn chế. | Chạy đúng user/namespace, xác minh PID và chính sách attach. |
| JMC không mở được file | File chưa hoàn tất, hỏng hoặc JMC quá cũ. | Kiểm tra bằng jfr summary, cập nhật JMC tương thích. |
| Custom JFC không được áp dụng | Sai đường dẫn hoặc sai event setting name/value. | Dùng jfr configure --verbose, jfr help configure và log JFR. |
| Recording làm ứng dụng chậm rõ rệt | Cấu hình profile dày, stack trace nhiều hoặc event rate cao. | Thu hẹp event, tăng threshold/period, giảm thời lượng và đo lại. |
| Không tìm thấy method trong hot methods | Workload không gọi method hoặc thời lượng sampling quá ngắn. | Gửi workload đại diện và ghi lâu hơn; cân nhắc method timing có filter nếu phù hợp. |

### Quy trình điều tra nhanh

1. Ghi rõ câu hỏi cần trả lời: CPU, allocation, GC, lock, I/O hay method cụ thể.
2. Chọn **default** hay **profile** phù hợp; xác định duration và giới hạn dung lượng.
3. Kiểm tra recording có event mong muốn bằng **jfr summary** và **jfr print**.
4. Nếu thiếu dữ liệu, kiểm tra enabled/period/threshold/stackTrace và workload.
5. Nếu nghi overhead, so sánh với recording default hoặc giảm event rate.
6. Nếu dùng JDK 25 feature mới, xác nhận JDK vendor/platform và trạng thái stable/experimental.
7. Ghi lại JDK version, OS/CPU, JVM options, JFC file và thời điểm sự cố để tái hiện.

## 17. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập A — Ghi profile một ứng dụng nhỏ

1. Chạy một ứng dụng Java có vòng lặp CPU và một thao tác I/O.
2. Bắt đầu recording bằng **profile.jfc** trong 60 giây.
3. Mở file bằng JMC hoặc xem bằng **jfr summary**, **jfr view hot-methods** và **jfr print**.
4. Xác định hot method và event I/O tương ứng.

**Đạt:** giải thích được sự khác nhau giữa stack sample và duration event; không coi số mẫu là số lần gọi chính xác.

### Bài tập B — Continuous recording

Khởi chạy một tiến trình dài hạn với **default.jfc**, đặt maxage và maxsize. Dùng jcmd để check, dump snapshot rồi tiếp tục recording; cuối cùng stop và so sánh hai file.

**Đạt:** quản lý được vòng đời recording mà không phải restart ứng dụng.

### Bài tập C — Tạo custom JFC

Tạo cấu hình dựa trên **profile.jfc**, thay đổi period của ExecutionSample và threshold của FileRead. Chạy lại cùng workload, so dung lượng file và mức độ chi tiết.

**Đạt:** giải thích được ảnh hưởng của từng setting và không sửa file cấu hình gốc của JDK.

### Bài tập D — So sánh sampling và method timing

Dùng ExecutionSample để tìm hot methods. Sau khi chọn được một method cụ thể, tạo recording riêng có MethodTiming/MethodTrace và filter hẹp cho method đó.

**Đạt:** phân biệt thống kê sampling với dữ liệu invocation được instrument, giải thích overhead và phạm vi sử dụng.

### Bài tập E — CPU-time profiling trên Linux

Trên JDK 25/Linux hỗ trợ, bật **jdk.CPUTimeSample**, xem **cpu-time-hot-methods** và kiểm tra **jdk.CPUTimeSamplesLost**. So sánh với ExecutionSample trên cùng workload có cả Java và native code.

**Đạt:** ghi rõ tính năng experimental và giới hạn nền tảng; không áp dụng kết quả Linux cho Windows/macOS.

### Bài tập F — Custom application event

Tạo event **OrderProcessed** có các trường loại nghiệp vụ và kết quả tổng quát. Ghi event trong workload kiểm thử, mở file JFR và kiểm tra event xuất hiện cùng GC/ExecutionSample trên timeline.

**Đạt:** không ghi dữ liệu cá nhân hoặc secret; biết dùng event để liên kết hoạt động ứng dụng với hoạt động JVM.

### Câu hỏi tự kiểm tra

1. JFR khác log text và metric ở mục đích, cấu trúc dữ liệu như thế nào?
2. Event-based recording khác periodic sampling ở điểm nào?
3. Vì sao ExecutionSample không phản ánh trực tiếp thời gian thread chờ I/O?
4. default.jfc và profile.jfc phù hợp với hai tình huống nào?
5. Period, threshold và stackTrace tác động ra sao đến số lượng và chi phí event?
6. JEP 518 cải thiện stack sampling như thế nào và safepoint bias còn ý nghĩa gì?
7. jdk.CPUTimeSample của JDK 25 có giới hạn nào so với ExecutionSample?
8. Vì sao cần kiểm tra CPUTimeSamplesLost?
9. Khi nào MethodTiming/MethodTrace phù hợp hơn sampling?
10. Vì sao continuous recording cần maxage hoặc maxsize?
11. Khi nào dùng jcmd thay vì StartFlightRecording?
12. Vì sao không nên ghi token hoặc request body nhạy cảm vào custom JFR event?

## 18. Nguồn tham khảo chính thức

- [JFR Diagnostic Tools — Java SE 25](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): recording liên tục, recording theo thời gian và công cụ chẩn đoán.
- [The java Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): tùy chọn StartFlightRecording và cấu hình settings.
- [The jcmd Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): JFR.start, JFR.check, JFR.dump và JFR.stop.
- [The jfr Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): configure, summary, view, print, metadata và scrub.
- [JFR Configuration and Event Settings — Java SE 25](https://docs.oracle.com/en/java/javase/25/jfapi/configuration.html): enabled, period, threshold, stackTrace và JFC.
- [EventSettings — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): cấu hình event bằng Java API.
- [Recording — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html): tạo, chạy, dừng và dump recording.
- [RecordingStream — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): nhận event stream trong ứng dụng.
- [JEP 518 — JFR Cooperative Sampling](https://openjdk.org/jeps/518): cải thiện độ ổn định và khả năng lấy mẫu stack.
- [JEP 509 — JFR CPU-Time Profiling (Experimental)](https://openjdk.org/jeps/509): event lấy mẫu CPU time trong Java 25.
- [JEP 520 — JFR Method Timing & Tracing](https://openjdk.org/jeps/520): các event method timing/tracing mới.
- [What's New for JFR in JDK 25 — Inside Java](https://inside.java/2025/06/03/new-jfr-jdk25/): tổng quan các thay đổi JFR trong Java 25.

**Ghi chú tính hiện hành:** JFR, các cấu hình JFC, jcmd, jfr CLI và Recording API là các cơ chế được duy trì trong Java 25. JEP 518 và JEP 520 là cải tiến Java 25; riêng CPU-time profiling của JEP 509 vẫn là experimental và giới hạn Linux trong Java 25. Khi triển khai trên vendor JDK khác, xác minh event và khả năng hỗ trợ thực tế trước khi dựa vào tính năng experimental.

**Kết quả cần nộp:** một file JFR được tạo bằng default/profile hoặc custom JFC; lệnh start/check/dump/stop đã dùng; kết quả summary và hot-method/event filter; bảng giải thích lý do chọn từng setting; cùng ghi chú overhead, JDK/platform và dữ liệu nhạy cảm đã loại bỏ. Kết quả này chứng minh bạn biết chọn cấu hình ghi theo mục tiêu quan sát và đọc được dữ liệu JFR trong môi trường Java 25.
