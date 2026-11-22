# Đọc và phân tích file JFR

**Java Flight Recorder (JFR)** ghi lại các sự kiện runtime của JVM thành file nhị phân có đuôi .jfr. Một recording có thể chứa thông tin về CPU sampling, garbage collection, cấp phát object, thread, lock contention, I/O, class loading, JVM flags và custom event do ứng dụng tự định nghĩa.

Đọc file JFR là quá trình tìm đúng khoảng thời gian và nhóm event liên quan tới vấn đề, sau đó đối chiếu timestamp, duration, thread, stack trace và các trường dữ liệu. Các công cụ chính:

- **jfr command-line tool:** xem tổng quan, lọc event, đọc metadata, tạo bảng phân tích và xuất JSON/XML.
- **JDK Mission Control (JMC):** giao diện đồ họa để lọc theo thời gian, duyệt event, xem stack trace, flame chart và phân tích tự động.
- **JFR Consumer API:** đọc event bằng Java code khi cần báo cáo hoặc xử lý tự động.

File JFR là dữ liệu nhị phân, không nên mở trực tiếp bằng text editor. Hãy bắt đầu bằng summary để hiểu recording trước khi lọc event.

## 1. JFR file lưu những gì?

Một recording gồm các chunk chứa metadata và event. Metadata mô tả tên event, nhãn, category, field, kiểu dữ liệu và đơn vị. Event lưu giá trị được ghi nhận trong khoảng thời gian recording.

Một event có thể chứa:

| Thành phần | Ý nghĩa |
|---|---|
| Event type | Tên loại sự kiện, ví dụ jdk.GarbageCollection |
| Start time | Thời điểm event bắt đầu |
| Duration | Thời lượng event nếu là event có thời gian |
| Event thread | Thread tạo hoặc commit event |
| Stack trace | Call stack tại thời điểm event được ghi |
| Fields | Các giá trị riêng của event như heap size, host, bytes, class hoặc request ID |

Có event dạng instant, ví dụ một số event ghi nhận thời điểm thread bắt đầu. Cũng có event dạng duration, ví dụ file read, socket read hoặc monitor contention. Khi phân tích latency, duration và timestamp thường quan trọng hơn số lượng event đơn thuần.

Một file có thể chứa nhiều chunk. Công cụ JFR sẽ đọc các chunk trong cùng recording. Dòng Chunks trong summary cho biết số chunk mà file chứa.

JFR không ghi mọi thao tác Java theo mặc định. Recording settings quyết định event nào được bật, sampling frequency, threshold và stack trace. Vì vậy, không thấy event trong file có thể có nghĩa là event chưa được bật, không vượt threshold, chưa xảy ra trong khoảng ghi hoặc không được sample.

## 2. Xác định đúng file và phiên bản công cụ

JFR command-line tool nằm trong thư mục bin của JDK.

Windows PowerShell:

~~~powershell
Get-Command jfr
where.exe jfr
jfr version
~~~

Linux/macOS:

~~~bash
command -v jfr
jfr version
~~~

Xác nhận file tồn tại và kích thước:

~~~powershell
Get-Item .\recording.jfr |
    Select-Object Name, Length, LastWriteTime
~~~

Linux/macOS:

~~~bash
ls -lh recording.jfr
file recording.jfr
~~~

Khi nhận file từ một máy khác, ghi nhận JDK đã tạo recording và JDK đang dùng để đọc. Ưu tiên công cụ cùng phiên bản hoặc mới hơn phiên bản nguồn; nếu gặp lỗi đọc metadata hay event type, hãy kiểm tra version trước khi kết luận file bị hỏng.

Không sửa trực tiếp file JFR gốc. Giữ bản gốc để có thể chạy lại phân tích hoặc so sánh kết quả.

## 3. Bước đầu tiên: jfr summary

Chạy:

~~~bash
jfr summary recording.jfr
~~~

Summary cung cấp:

- Version của định dạng recording.
- Số chunk.
- Thời điểm bắt đầu.
- Tổng duration.
- Danh sách event type.
- Số lượng event theo từng type.
- Dung lượng event được ghi trong file.

Ví dụ output rút gọn:

~~~text
Version: 2.1
Chunks: 1
Start: 2026-11-10 12:48:43 (UTC)
Duration: 1 s

Event Type                 Count  Size (bytes)
================================================
jdk.GarbageCollection          1            19
jdk.ThreadSleep                4            64
com.example.RequestEvent       4            84
jdk.ExecutionSample            0             0
~~~

Đây là ví dụ minh họa; số lượng thực tế phụ thuộc recording và settings.

### Cách đọc summary

**Start và Duration:** xác định khoảng thời gian mà recording bao phủ. Đối chiếu với thời điểm người dùng báo lỗi, deploy, spike CPU hoặc GC pause. Kiểm tra timezone khi so sánh với log ứng dụng và hệ thống.

**Event Type:** cho biết những loại event đã xuất hiện. Đây là bản đồ để chọn event cần xem tiếp.

**Count = 0:** event type có trong metadata nhưng không có event được ghi. Có thể recording không bật event đó, event không xảy ra, hoặc event không vượt threshold.

**Count lớn:** không tự động có nghĩa lỗi. Một event phổ biến như allocation sample hoặc thread event có thể có số lượng lớn trong workload bình thường. Cần xem duration, stack trace, thread và xu hướng.

Summary là bước định hướng, không thay thế phân tích chi tiết.

## 4. Xem danh sách event và metadata

Metadata mô tả event mà file có thể chứa.

Xem metadata của toàn bộ recording:

~~~bash
jfr metadata recording.jfr
~~~

Lọc theo event:

~~~bash
jfr metadata --events jdk.GarbageCollection recording.jfr
~~~

Hoặc xem metadata của custom event:

~~~bash
jfr metadata --events com.example.RequestEvent recording.jfr
~~~

Metadata có thể cho biết:

- Tên đầy đủ và label của event.
- Category và description.
- Các field của event.
- Kiểu dữ liệu và đơn vị timestamp/timespan.
- Stack trace hoặc thread field có sẵn hay không.

Khi không truyền file, jfr metadata dùng metadata từ JDK cài đặt hiện tại. Khi cần hiểu recording cụ thể, hãy truyền chính file đó để xem schema của event được lưu trong recording.

Tên event thường có tiền tố jdk. Custom event có thể dùng tên riêng theo package ứng dụng. Không giả định mọi JDK đều có cùng event type; kiểm tra metadata và JDK version thực tế.

## 5. In event bằng jfr print

jfr print hiển thị giá trị event theo dạng dễ đọc.

In tất cả event:

~~~bash
jfr print recording.jfr
~~~

Với file lớn, không nên in tất cả ngay từ đầu. Hãy lọc theo event type:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary recording.jfr
~~~

Lọc theo category:

~~~bash
jfr print --categories "GC,JVM,Java*" recording.jfr
~~~

In stack trace sâu hơn:

~~~bash
jfr print --events jdk.ExecutionSample --stack-depth 32 recording.jfr
~~~

Mặc định stack trace có độ sâu 5 frame. Tăng độ sâu khi cần xem caller chain; output sẽ dài hơn.

### Ví dụ event

Output của custom event có thể có dạng:

~~~text
com.example.RequestEvent {
  startTime = 12:48:43.100
  duration = 101 ms
  requestId = "REQ-1"
  durationMs = 7
  eventThread = "main"
  stackTrace = [
    com.example.JfrFileDemo.main(String[]) line: 36
  ]
}
~~~

Cách đọc:

- Event type là com.example.RequestEvent.
- Event bắt đầu ở timestamp được hiển thị.
- Duration là khoảng thời gian từ begin() đến end().
- requestId và durationMs là field do ứng dụng định nghĩa.
- eventThread cho biết thread commit event.
- stackTrace cho biết vị trí code tạo event.

Timestamp và duration là hai thông tin khác nhau. Một event có duration lớn có thể bắt đầu trước khi người dùng quan sát spike; hãy so sánh timestamp với event lân cận.

### Xuất JSON hoặc XML

JSON:

~~~bash
jfr print --json --events com.example.RequestEvent recording.jfr
~~~

XML:

~~~bash
jfr print --xml --events com.example.RequestEvent recording.jfr
~~~

JSON/XML phù hợp khi cần đưa event vào công cụ phân tích khác hoặc xử lý bằng script. Nên lọc event type trước khi xuất để hạn chế kích thước dữ liệu.

Text output hữu ích cho việc đọc thủ công. Không nên dựa vào định dạng text như một giao thức ổn định nếu xây dựng automation lâu dài; dùng Consumer API khi cần đọc event có cấu trúc.

## 6. Dùng jfr view để xem báo cáo dựng sẵn

JDK cung cấp các view tổng hợp dữ liệu recording thành bảng. Xem danh sách:

~~~bash
jfr help view
~~~

Hoặc xem tất cả view có thể dùng với file:

~~~bash
jfr view all-views recording.jfr
~~~

Xem tất cả event type trong recording:

~~~bash
jfr view all-events recording.jfr
~~~

Một số view hữu ích:

| View | Mục đích |
|---|---|
| gc | Tổng quan garbage collection |
| gc-pauses | Phân tích pause do GC |
| heap-configuration | Cấu hình heap |
| hot-methods | Method có hoạt động CPU nổi bật |
| allocation-by-class | Cấp phát theo class |
| allocation-by-site | Cấp phát theo vị trí code |
| allocation-by-thread | Cấp phát theo thread |
| contention-by-site | Lock contention theo vị trí |
| contention-by-thread | Lock contention theo thread |
| thread-count | Số thread theo thời gian |
| thread-cpu-load | CPU load theo thread |
| socket-reads-by-host | Socket read theo host |
| file-reads-by-path | File read theo đường dẫn |
| exception-by-type | Exception theo type |
| events-by-name | Số lượng event theo tên |

Ví dụ:

~~~bash
jfr view gc recording.jfr
jfr view gc-pauses recording.jfr
jfr view hot-methods recording.jfr
jfr view allocation-by-class recording.jfr
jfr view contention-by-site recording.jfr
jfr view thread-count recording.jfr
~~~

Tăng chiều rộng bảng:

~~~bash
jfr view --width 160 hot-methods recording.jfr
~~~

Hiển thị câu truy vấn tạo nên view:

~~~bash
jfr view --verbose allocation-by-class recording.jfr
~~~

Một view có thể báo không tìm thấy event nếu recording không có dữ liệu cần thiết. Ví dụ recording quá ngắn, settings không bật event, hoặc event chỉ xuất hiện khi workload có hoạt động tương ứng. Hãy quay lại summary và metadata để xác nhận trước khi kết luận.

Tên view và nội dung bảng phụ thuộc JDK. Chạy jfr help view trên đúng JDK đang sử dụng.

## 7. Các nhóm event quan trọng khi điều tra

### CPU và method profiling

Các event như jdk.ExecutionSample ghi nhận mẫu stack của thread đang thực thi tại những thời điểm lấy mẫu. Chúng giúp tìm method thường xuất hiện trong các sample.

Một sample không phải một lần gọi method. Nếu một method xuất hiện trong nhiều sample, đó là dấu hiệu nó chiếm nhiều thời gian CPU tương đối trong recording, không phải số lần gọi chính xác.

Xem:

~~~bash
jfr print --events jdk.ExecutionSample --stack-depth 32 recording.jfr
jfr view hot-methods recording.jfr
~~~

Trong JMC, xem hot methods hoặc flame graph để tìm call path có nhiều sample.

### Garbage collection và heap

Các event thường gặp:

- jdk.GarbageCollection.
- jdk.GCHeapSummary.
- jdk.GCPhasePause.
- jdk.GCPhaseConcurrent.
- Các event riêng của collector như G1 hoặc ZGC.

Xem:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary recording.jfr
jfr view gc recording.jfr
jfr view gc-pauses recording.jfr
~~~

Đối chiếu thời điểm GC bắt đầu, duration, loại collection, heap trước/sau và mức pause. Một lần GC lâu chưa đủ kết luận có vấn đề; hãy xem tần suất, tổng pause, allocation rate và workload cùng thời điểm.

### Object allocation và memory

Event jdk.ObjectAllocationSample là sampling event cho allocation. Nó giúp tìm class hoặc stack thường gắn với cấp phát đáng chú ý, nhưng không phải bản ghi chính xác của mọi object allocation.

Xem:

~~~bash
jfr print --events jdk.ObjectAllocationSample recording.jfr
jfr view allocation-by-class recording.jfr
jfr view allocation-by-site recording.jfr
jfr view allocation-by-thread recording.jfr
~~~

Nếu nghi ngờ memory leak, cần theo dõi xu hướng heap sau GC và kiểm tra object retention bằng heap dump hoặc các công cụ phù hợp. JFR allocation samples giúp tìm nơi cấp phát; chúng không thay thế heap dump khi cần xem object graph và GC roots.

### Thread, lock và parking

Một số event:

- jdk.ThreadStart và jdk.ThreadEnd.
- jdk.JavaMonitorEnter.
- jdk.JavaMonitorWait.
- jdk.ThreadPark.
- jdk.JavaMonitorInflate.

Xem:

~~~bash
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark recording.jfr
jfr view contention-by-site recording.jfr
jfr view contention-by-thread recording.jfr
~~~

Lock event thường phụ thuộc threshold. Một lần monitor wait ngắn có thể không được ghi nếu chưa vượt threshold. Đọc ActiveSetting hoặc metadata/settings để biết recording đang dùng cấu hình nào.

ThreadPark thường liên quan tới các synchronizer như LockSupport, ReentrantLock hoặc queue. Không đồng nhất mọi thread park với lỗi; cần xem thread state, stack trace và thời lượng chờ.

### File và network I/O

Các event có thể gồm:

- jdk.FileRead và jdk.FileWrite.
- jdk.SocketRead và jdk.SocketWrite.
- jdk.NetworkUtilization.

Xem:

~~~bash
jfr print --events jdk.FileRead,jdk.FileWrite recording.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite recording.jfr
jfr view socket-reads-by-host recording.jfr
jfr view file-reads-by-path recording.jfr
~~~

Các event này có thể giúp xác định thao tác I/O chậm, host có thời gian phản hồi lớn hoặc đường dẫn file được truy cập thường xuyên. Không phải mọi lần đọc/ghi đều xuất hiện; threshold và event settings ảnh hưởng dữ liệu.

### Exception và class loading

Xem exception:

~~~bash
jfr view exception-by-type recording.jfr
jfr view exception-by-message recording.jfr
jfr view exception-by-site recording.jfr
~~~

Xem class loading:

~~~bash
jfr view class-loaders recording.jfr
jfr view longest-class-loading recording.jfr
~~~

Exception event có thể được cấu hình chỉ ghi lỗi hoặc ghi tất cả. Nếu số lượng exception trong JFR thấp hơn log ứng dụng, hãy kiểm tra event setting và threshold trước khi so sánh.

## 8. Đọc event theo timeline

JFR hữu ích vì event có timestamp và có thể có duration. Khi phân tích sự cố, hãy chọn một khoảng thời gian có liên hệ với triệu chứng.

Một quy trình thực tế:

1. Ghi lại thời điểm spike CPU, latency, OOM hoặc GC pause từ monitoring/log.
2. Kiểm tra Start và Duration của file để biết recording có bao phủ thời điểm đó không.
3. Dùng summary để tìm event type có dữ liệu.
4. Chọn nhóm event phù hợp với triệu chứng.
5. Lọc event bằng jfr print hoặc view dựng sẵn.
6. Đối chiếu timestamp, duration, thread và stack trace.
7. So sánh event trước, trong và sau sự cố.
8. Kiểm tra giả thuyết bằng log, metrics hoặc recording khác.

Ví dụ khi request latency tăng:

- Nếu có GC pause trùng thời điểm, kiểm tra thời lượng pause và heap.
- Nếu có monitor contention, tìm thread và code site giữ lock.
- Nếu có socket read duration lớn, đối chiếu host và dịch vụ ngoài.
- Nếu CPU samples tập trung ở một call path, kiểm tra method và thuật toán.
- Nếu allocation samples tập trung ở một class, xem object churn và cache.

Các sự kiện đồng thời không tự chứng minh quan hệ nhân quả. Một GC pause có thể trùng với request chậm nhưng nguyên nhân ban đầu có thể là allocation spike hoặc workload thay đổi. Hãy kiểm tra chuỗi sự kiện và bằng chứng bổ sung.

## 9. Đọc file bằng JDK Mission Control

JDK Mission Control (JMC) là công cụ đồ họa để phân tích recording JFR. JMC được phân phối riêng trong nhiều môi trường JDK; nếu máy chưa có, cài bản phù hợp từ dự án OpenJDK Mission Control.

Quy trình:

1. Mở JMC.
2. Chọn File > Open File.
3. Chọn recording .jfr.
4. Chờ JMC đọc metadata và dựng các trang phân tích.
5. Bắt đầu từ Overview và Automated Analysis.
6. Mở Event Browser để lọc event theo type, time range, thread hoặc field.
7. Chọn event để xem fields và stack trace.
8. Dùng các view chuyên biệt như Threads, Memory, GC, Method Profiling hoặc I/O khi phù hợp.

### Overview và Automated Analysis

Overview giúp nắm thời gian recording, JVM, hệ điều hành, CPU, memory và các điểm nổi bật. Automated Analysis có thể đưa ra cảnh báo hoặc gợi ý dựa trên event được ghi.

Đây là điểm bắt đầu để hình thành giả thuyết. Không xem cảnh báo tự động là kết luận cuối cùng; hãy mở event và xác nhận bằng timestamp, duration và stack trace.

### Event Browser

Event Browser phù hợp khi cần lọc dữ liệu chi tiết:

- Chọn event type.
- Chọn khoảng thời gian.
- Lọc theo thread hoặc field.
- Sắp xếp theo timestamp/duration.
- Mở event để xem field và stack trace.

Nếu không thấy event, kiểm tra filter đang bật, time range và recording settings.

### Flame graph và method profiling

Flame graph tổng hợp stack samples để cho thấy call path nào chiếm nhiều sample. Trục ngang thể hiện tỷ trọng sample; chiều dọc biểu diễn call stack.

Một frame rộng cho biết frame đó xuất hiện trong nhiều sample tương đối. Không diễn giải độ rộng như số lần gọi method chính xác.

## 10. Ghi recording bằng jcmd để có file cần đọc

Nếu ứng dụng đã chạy và cho phép Attach, có thể bắt đầu recording từ xa bằng jcmd.

Liệt kê JVM:

~~~bash
jcmd -l
~~~

Xem lệnh hỗ trợ:

~~~bash
jcmd <pid> help JFR.start
jcmd <pid> help JFR.dump
jcmd <pid> help JFR.stop
~~~

Bắt đầu recording:

~~~bash
jcmd <pid> JFR.start name=Incident settings=profile filename=incident.jfr duration=60s
~~~

Kiểm tra recording:

~~~bash
jcmd <pid> JFR.check
~~~

Dump snapshot khi recording còn chạy:

~~~bash
jcmd <pid> JFR.dump name=Incident filename=incident-snapshot.jfr
~~~

Dừng recording:

~~~bash
jcmd <pid> JFR.stop name=Incident
~~~

Trong JDK 24, jcmd cho biết profile.jfc thu thập nhiều dữ liệu hơn default.jfc nhưng overhead cao hơn. default.jfc có overhead thấp hơn và phù hợp hơn với recording liên tục. Dùng profile trong khoảng thời gian ngắn khi cần thêm chi tiết, đồng thời đánh giá tác động lên workload.

Nếu muốn ghi ngay từ lúc JVM khởi động:

~~~bash
java -XX:StartFlightRecording=filename=app.jfr,duration=60s,settings=profile -jar app.jar
~~~

Các lệnh trên yêu cầu quyền attach phù hợp. Nếu JVM tắt Attach hoặc process nằm trong namespace khác, jcmd có thể không kết nối được. Xác nhận đúng PID, user và cấu hình runtime.

## 11. Tạo file JFR bằng Java Flight Recorder API

Ứng dụng có thể tự tạo recording bằng API trong module jdk.jfr. Custom event hữu ích khi cần ghi thông tin nghiệp vụ như request ID, order ID, batch name hoặc thời gian xử lý.

Ví dụ event:

~~~java
@Name("com.example.RequestEvent")
@Label("Request event")
@Category({"Demo", "Application"})
public static class RequestEvent extends Event {
    @Label("Request ID")
    public String requestId;

    @Label("Duration in milliseconds")
    public int durationMs;
}
~~~

Bật event trong Recording:

~~~java
recording.enable(RequestEvent.class)
         .withThreshold(Duration.ZERO)
         .withStackTrace();
~~~

Các bước cơ bản:

1. Tạo Recording với cấu hình phù hợp.
2. Enable event type và đặt threshold.
3. Start recording.
4. Tạo event, gọi begin(), gán field, gọi end() và commit().
5. Stop recording.
6. Dump ra file .jfr.

Không đưa dữ liệu nhạy cảm như password, token hoặc nội dung request đầy đủ vào custom event. Chỉ ghi field cần thiết cho chẩn đoán.

## 12. Ví dụ Java 17+ hoàn chỉnh: tạo và đọc file JFR

Ví dụ gồm hai chương trình. JfrFileDemo tạo file với bốn custom event. JfrReader mở file đó bằng RecordingFile, lọc event theo tên và tính thời gian trung bình.

Cấu trúc:

~~~text
jfr-file-demo/
└── src/
    └── com/
        └── example/
            ├── JfrFileDemo.java
            └── JfrReader.java
~~~

### JfrFileDemo.java

~~~java
package com.example;

import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class JfrFileDemo {
    @Name("com.example.RequestEvent")
    @Label("Request event")
    @Category({"Demo", "Application"})
    public static final class RequestEvent extends Event {
        @Label("Request ID")
        public String requestId;

        @Label("Duration in milliseconds")
        public int durationMs;
    }

    public static void main(String[] args) throws Exception {
        Path destination = Path.of(args[0]).toAbsolutePath();

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("profile"))) {
            recording.setName("JFR file analysis demo");
            recording.setToDisk(true);
            recording.enable(RequestEvent.class)
                     .withThreshold(Duration.ZERO)
                     .withStackTrace();

            recording.start();

            for (int i = 1; i <= 4; i++) {
                RequestEvent event = new RequestEvent();
                event.requestId = "REQ-" + i;
                event.durationMs = i * 7;

                event.begin();
                Thread.sleep(100);
                event.end();
                event.commit();
            }

            recording.stop();
            recording.dump(destination);

            System.out.println("Recording written: " + destination.getFileName());
            System.out.println("Custom events committed: 4");
        }
    }
}
~~~

### JfrReader.java

~~~java
package com.example;

import java.nio.file.Path;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrReader {
    private JfrReader() {
    }

    public static void main(String[] args) throws Exception {
        long count = 0;
        long totalDuration = 0;

        try (RecordingFile file = new RecordingFile(Path.of(args[0]))) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();

                if (event.getEventType().getName()
                        .equals("com.example.RequestEvent")) {
                    String requestId = event.getString("requestId");
                    int durationMs = event.getInt("durationMs");

                    System.out.printf(
                            "%s duration=%dms%n", requestId, durationMs);

                    count++;
                    totalDuration += durationMs;
                }
            }
        }

        System.out.println("Matched events=" + count);
        System.out.println(
                "Average duration=" +
                (count == 0 ? 0 : totalDuration / count) + "ms");
    }
}
~~~

### Biên dịch

Từ thư mục gốc jfr-file-demo:

~~~bash
mkdir -p build/classes

javac --release 17 \
    -d build/classes \
    src/com/example/JfrFileDemo.java \
    src/com/example/JfrReader.java
~~~

### Tạo recording

~~~bash
java -cp build/classes \
    com.example.JfrFileDemo sample.jfr
~~~

Output:

~~~text
Recording written: sample.jfr
Custom events committed: 4
~~~

### Đọc file bằng Java API

~~~bash
java -cp build/classes \
    com.example.JfrReader sample.jfr
~~~

Output chính xác:

~~~text
REQ-1 duration=7ms
REQ-2 duration=14ms
REQ-3 duration=21ms
REQ-4 duration=28ms
Matched events=4
Average duration=17ms
~~~

### Kiểm tra cùng file bằng CLI

~~~bash
jfr summary sample.jfr
jfr metadata --events com.example.RequestEvent sample.jfr
jfr print --events com.example.RequestEvent sample.jfr
jfr view events-by-name sample.jfr
~~~

Ví dụ này đã được biên dịch bằng javac --release 17 và chạy trên JDK 24.0.2. Các timestamp, dung lượng file và số event hệ thống có thể khác theo máy; bốn custom event và output của JfrReader được xác định bởi dữ liệu ví dụ.

## 13. Đọc file lớn bằng RecordingFile

Consumer API nằm trong module jdk.jfr, package jdk.jfr.consumer.

Các lớp quan trọng:

| API | Vai trò |
|---|---|
| RecordingFile | Mở file .jfr và đọc event tuần tự |
| RecordedEvent | Đại diện một event đã ghi |
| RecordedEvent.getEventType() | Lấy metadata/type của event |
| RecordedEvent.getStartTime() | Lấy timestamp bắt đầu |
| RecordedEvent.getDuration() | Lấy duration |
| RecordedEvent.getThread() | Lấy thread liên quan nếu có |
| RecordedEvent.getStackTrace() | Lấy stack trace nếu event có |
| RecordedEvent.getValue(name) | Lấy field theo tên |

Với file lớn, ưu tiên đọc tuần tự bằng hasMoreEvents() và readEvent() như ví dụ. Không gọi readAllEvents() một cách tùy tiện vì phương thức này tải toàn bộ event vào bộ nhớ và có thể gây áp lực heap.

Khi xử lý từng event:

- Lọc event type sớm để giảm công việc.
- Chỉ đọc field cần thiết.
- Tổng hợp số liệu thay vì giữ toàn bộ RecordedEvent trong collection.
- Đóng RecordingFile bằng try-with-resources.
- Xử lý IOException và lỗi schema khi đọc file từ JDK khác.
- Kiểm tra field có tồn tại trong event metadata trước khi giả định mọi recording đều có cùng schema.

Nếu cần export dữ liệu, hãy ghi ra CSV/JSON theo schema do ứng dụng kiểm soát và giữ lại timestamp, timezone, event type cùng đơn vị đo.

## 14. Lọc và scrub recording trước khi chia sẻ

JFR có thể chứa thông tin nhạy cảm: system property, environment variable, command line, tên process, đường dẫn file, host/địa chỉ mạng, class nội bộ, stack trace và field custom của ứng dụng.

Không gửi file .jfr nguyên bản lên ticket công khai hoặc dịch vụ không được phê duyệt.

jfr scrub tạo recording mới bằng cách include/exclude event type, category hoặc thread.

Ví dụ loại bỏ event về environment variable và initial system property:

~~~bash
jfr scrub --exclude-events InitialEnvironmentVariable,InitialSystemProperty recording.jfr recording-scrubbed.jfr
~~~

Chỉ giữ event socket:

~~~bash
jfr scrub --include-events "jdk.Socket*" recording.jfr socket-only.jfr
~~~

Chỉ giữ event từ thread có tên chứa main:

~~~bash
jfr scrub --include-threads main recording.jfr main-thread-only.jfr
~~~

Có thể lọc category:

~~~bash
jfr scrub --exclude-categories "JVM,OS" recording.jfr filtered.jfr
~~~

Sau khi scrub, kiểm tra file mới:

~~~bash
jfr summary recording-scrubbed.jfr
jfr print recording-scrubbed.jfr
~~~

**Scrub không phải công cụ xóa bí mật theo field.** Nó lọc event type/category/thread; các event được giữ lại vẫn có thể chứa token, URL, SQL, request data hoặc thông tin nhạy cảm khác. Cần kiểm tra metadata, event và field thực tế trước khi chia sẻ. Giữ nguyên file gốc ở nơi bảo mật.

## 15. Xử lý recording nhiều chunk hoặc file lớn

Summary cho biết số chunk trong file. Nếu file lớn, có thể dùng JMC hoặc lọc event để tránh xuất toàn bộ recording thành text.

Một số lệnh quản lý file:

~~~bash
jfr disassemble recording.jfr --output chunks/
~~~

Disassemble chia recording thành các file/chunk nhỏ hơn để xử lý riêng.

~~~bash
jfr assemble repository/ recording-assembled.jfr
~~~

Assemble tạo recording từ các chunk còn lại trong disk repository. Lệnh này hữu ích khi cần khôi phục recording từ repository sau sự cố hoặc khi thao tác với các chunk chưa được ghép thành file hoàn chỉnh.

Kiểm tra cú pháp trên JDK đang dùng:

~~~bash
jfr help disassemble
jfr help assemble
~~~

Không tự ghép file bằng cách nối byte hoặc đổi phần mở rộng. Hãy dùng công cụ JFR để duy trì cấu trúc chunk và metadata.

## 16. Các lỗi thường gặp khi đọc file JFR

### Không tìm thấy file

Kiểm tra working directory, đường dẫn tương đối/tuyệt đối và quyền đọc file. Nếu recording nằm trong container, xác định file đã được copy ra vị trí mà công cụ có thể truy cập.

### File không hợp lệ hoặc bị truncate

Recording có thể chưa được dump hoàn chỉnh, bị copy dở hoặc process bị dừng trong lúc ghi. Kiểm tra kích thước file, nguồn tạo và thử đọc bằng JDK tương thích. Nếu recording vẫn đang chạy, dùng JFR.dump để tạo snapshot hoàn chỉnh thay vì copy file đang được ghi trực tiếp.

### Summary không có event mong đợi

Kiểm tra recording duration, settings, event threshold và thời điểm workload. Event có thể chưa bật hoặc không xảy ra trong cửa sổ ghi.

### jfr print quá dài

Lọc theo event type hoặc category. Giảm stack depth nếu output lớn. Với file lớn, dùng jfr view hoặc JMC.

### jfr view báo No events found

View có thể yêu cầu event mà recording không chứa. Kiểm tra summary và metadata; nếu event không được bật, cần tạo recording mới với settings phù hợp.

### Không thấy stack trace

Event có thể không bật stack trace hoặc loại event đó không cung cấp stack. Kiểm tra recording settings và metadata. Khi cần, cấu hình event có stack trace trong lần ghi tiếp theo.

### JSON/XML không đọc được

Đảm bảo output không bị cắt bởi terminal/pipeline. Xuất trực tiếp ra file, kiểm tra exit code của jfr và dùng parser JSON/XML để xác nhận cấu trúc.

### File quá lớn

Giảm thời gian ghi, dùng default settings khi phù hợp, giới hạn maxage/maxsize, lọc event khi export hoặc dùng JMC để duyệt dữ liệu. Không giảm event settings đến mức bỏ mất dữ liệu cần điều tra.

## 17. Checklist phân tích một file JFR

- [ ] Xác nhận nguồn file, JDK version và thời điểm tạo.
- [ ] Giữ bản gốc và làm việc trên bản sao khi cần scrub.
- [ ] Chạy jfr summary để xem chunk, start, duration và event count.
- [ ] Xác nhận recording bao phủ đúng khoảng thời gian sự cố.
- [ ] Kiểm tra metadata và event settings.
- [ ] Chọn event type liên quan tới triệu chứng.
- [ ] Dùng jfr print hoặc jfr view để lọc dữ liệu.
- [ ] Đọc timestamp, duration, thread, stack trace và field.
- [ ] Đối chiếu CPU, GC, allocation, lock và I/O theo timeline.
- [ ] Dùng JMC khi cần lọc trực quan hoặc flame graph.
- [ ] Dùng RecordingFile cho xử lý tự động và file lớn.
- [ ] Không nhầm sampling event với số lần gọi chính xác.
- [ ] Không kết luận nhân quả chỉ từ các event trùng thời điểm.
- [ ] Rà soát dữ liệu nhạy cảm trước khi chia sẻ file.
- [ ] Lưu lại lệnh, version, filter và giả thuyết đã kiểm tra.

## 18. Các lệnh cần nhớ

~~~bash
# Check JFR tool version
jfr version

# Summary: start, duration, chunks, event counts
jfr summary recording.jfr

# Inspect event schema and fields
jfr metadata recording.jfr

# Print selected event types
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary recording.jfr

# Print deeper stack traces
jfr print --events jdk.ExecutionSample --stack-depth 32 recording.jfr

# Export JSON or XML
jfr print --json recording.jfr
jfr print --xml recording.jfr

# Predefined analysis views
jfr view gc recording.jfr
jfr view hot-methods recording.jfr
jfr view allocation-by-class recording.jfr
jfr view contention-by-site recording.jfr

# Filter event types into a new recording
jfr scrub --exclude-events InitialEnvironmentVariable,InitialSystemProperty recording.jfr filtered.jfr

# Live recording control
jcmd <pid> JFR.start name=Incident settings=profile filename=incident.jfr duration=60s
jcmd <pid> JFR.check
jcmd <pid> JFR.dump name=Incident filename=incident-snapshot.jfr
jcmd <pid> JFR.stop name=Incident
~~~

Đọc file JFR hiệu quả bắt đầu bằng summary, sau đó chọn event type và view phù hợp với triệu chứng. Hãy dùng timestamp, duration, thread và stack trace để kết nối CPU, GC, allocation, lock và I/O theo cùng timeline. JMC giúp khám phá trực quan; RecordingFile API phù hợp cho xử lý có cấu trúc. Luôn kiểm tra recording settings và bảo vệ file vì dữ liệu JFR có thể chứa thông tin nội bộ của ứng dụng.

## Tài liệu tham khảo

- [The jfr Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [The jcmd Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [JDK Flight Recorder API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/module-summary.html)
- [RecordingFile API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [RecordedEvent API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html)
- [OpenJDK Mission Control](https://github.com/openjdk/jmc)
