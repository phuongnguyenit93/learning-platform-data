# Flight Recorder: Mô hình sự kiện và bản ghi liên tục có chi phí kiểm soát được (Java 11)

## 1. Mục tiêu và phạm vi bài học

**JDK Flight Recorder (JFR)** là cơ chế thu thập các sự kiện (events) có cấu trúc từ JVM, thư viện Java và ứng dụng. Nó giúp điều tra CPU cao, GC pause, lock contention, độ trễ I/O và những sự cố chỉ xuất hiện ngắt quãng. Từ **Java 11**, JFR được tích hợp vào OpenJDK theo **JEP 328**, và các ý tưởng nền tảng của JFR tiếp tục được dùng trong JDK hiện đại.

Mục tiêu của bài **“Mô hình sự kiện và bản ghi liên tục có chi phí kiểm soát được”** gồm hai phần:

1. Hiểu **event model**: event type, event instance, timestamp, duration, thread, stack trace, fields, event settings, consumer.
2. Thiết kế **continuous recording**: ghi lâu dài với cấu hình nhẹ, rolling retention trên disk, giới hạn `maxage`/`maxsize`, dump snapshot khi cần, rồi phân tích mà không vượt ngân sách CPU, heap và storage.

Sau bài này, bạn biết vận hành bằng `jcmd`/`jfr`, tạo sự kiện riêng bằng `jdk.jfr.Event`, ghi/đọc file `.jfr` trên **Java 11**, phân tích điểm đánh đổi giữa `default` và `profile`, và kiểm thử overhead, tính riêng tư, retention.

**Điểm tương thích:** `jdk.jfr.Recording`, `Event`, `EventSettings` và `jdk.jfr.consumer.RecordingFile` khả dụng trong Java 11. `RecordingStream`/JFR Event Streaming được bổ sung từ **JDK 14 (JEP 349)**; không copy mã này vào dự án cần `javac --release 11`. Các cờ cho phiên bản JDK cũ yêu cầu “unlock commercial features” không phải hướng triển khai hiện hành cho JDK 11+.

## 2. Event, recording và dump không phải cùng một thứ

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Event type** | Schema định nghĩa một loại sự kiện | `jdk.CPULoad`, `jdk.JavaMonitorEnter`, `example.SyncOperation` |
| **Event instance** | Một lần xảy ra được ghi nhận | Một đợt GC, một lần socket read, một giao dịch ứng dụng |
| **Event field** | Dữ liệu có kiểu bên trong một event | `duration`, `eventThread`, mã hoạt động, số byte |
| **Event settings** | Quy tắc thu thập từng loại event | `enabled`, `threshold`, `period`, `stackTrace` |
| **Recording** | Phiên thu thập event theo cấu hình và retention | `name=service-continuous` |
| **JFR repository** | Bộ đệm/chunk phục vụ thu thập, có thể lưu trên disk | Những chunk gần đây trong rolling window |
| **Dump** | Xuất dữ liệu hiện còn giữ thành file `.jfr` | `incident.jfr` |
| **Consumer** | Công cụ đọc/phân tích sự kiện | `jfr print`, JDK Mission Control, `RecordingFile` |

Event JFR không giống một dòng `logger.info`. Nó chứa thông tin có cấu trúc và metadata để truy vấn theo loại sự kiện, thời gian, thread, duration và stack trace. Một file `.jfr` được export có thể chứa **rất nhiều event types**; không mặc định mọi dòng dữ liệu đều do code ứng dụng phát.

### Mô hình dữ liệu

```text
JVM / JDK / application
          |
   event instances
  (type + fields + time)
          |
 enabled? threshold? period?
          |
    JFR buffer/chunks
          |
   recording đang chạy
  + maxage / maxsize
          |
    JFR.dump snapshot
          |
       .jfr file
          |
  jfr / JMC / RecordingFile
```

**Continuous recording** nghĩa là một recording có thể hoạt động lâu dài, **không** có nghĩa phải nối vô hạn tất cả event vào một file khổng lồ. Khi dùng disk repository và retention, JFR loại bỏ chunk cũ để giữ lại cửa sổ lịch sử mới nhất.

## 3. Các loại event và cách đọc

Một event có thể có các trường:

- **Event type name**, do JDK định nghĩa hoặc do application khai báo bằng `@Name`.
- **Start time** và **duration** nếu đo một khoảng thời gian.
- **Thread** phát event và thông tin execution/stack trace nếu cấu hình thu thập.
- **Fields** tùy event: số byte, GC cause, operation code, thành phần I/O.
- **Metadata** như `@Label`, `@Description`, `@Category` và đơn vị đo, phục vụ công cụ phân tích.

Có các nhóm ý nghĩa:

| Kiểu | Ví dụ | Không nên suy luận |
| --- | --- | --- |
| **Instant** | Event ứng dụng `commit()` tại một thời điểm | Không nhất thiết đo duration hữu ích |
| **Duration** | Một lần monitor enter hoặc custom operation `begin()/end()` | Không phải mọi lần đều được ghi khi có threshold |
| **Periodic** | `jdk.CPULoad` theo chu kỳ | Không phải một event cho mỗi thao tác ứng dụng |
| **Sampled** | `jdk.ExecutionSample` | Số sample **không bằng** số method call thật |
| **JVM state** | GC, JVM information, thread events | Field/event availability phụ thuộc runtime và cài đặt |

Ví dụ những event JDK thường hữu ích:

| Event | Câu hỏi điều tra | Lưu ý |
| --- | --- | --- |
| `jdk.CPULoad` | CPU của JVM/máy có tăng? | Periodic statistics, không tự chỉ ra method nóng |
| `jdk.ExecutionSample` | Những stack nào thường xuất hiện khi lấy mẫu? | Sampling, không đếm lời gọi chính xác |
| `jdk.GarbageCollection` | Có nhiều GC hoặc khoảng GC chồng sự cố? | Đối chiếu thêm heap/GC events |
| `jdk.JavaMonitorEnter` | Lock contention gây chờ lâu? | Threshold có thể bỏ qua những lần chờ ngắn |
| `jdk.ThreadPark` | Thread chờ/park ở đâu? | Park không tự động là deadlock |
| `jdk.SocketRead`, `jdk.SocketWrite` | I/O mạng chậm hoặc nhiều byte? | Endpoint/stack có thể chứa metadata nhạy cảm |
| `jdk.FileRead`, `jdk.FileWrite` | File I/O bị nghẽn ở đâu? | Path file có thể là dữ liệu cần bảo vệ |
| `jdk.ObjectAllocationInNewTLAB` | Hoạt động allocation trong TLAB? | Không thay một phép đếm mọi object allocation |

Tập event, tên field và setting mặc định có thể thay đổi theo **JDK version, vendor và workload**. Trước khi viết query hoặc kết luận “không có vấn đề”, cần biết event đó có được enable và thực sự có trong file hay không.

### Cách giải thích event timeline

Giả sử request HTTP chậm ở 10:02. Một file JFR có các event `jdk.JavaMonitorEnter` gần thời điểm ấy, trong khi CPU không quá cao. Điều đó gợi ý **lock contention**, nhưng chưa chứng minh nguyên nhân của mọi request chậm. Phải đối chiếu duration, stack, các thread, các event GC/I/O liên quan và metrics/logs/traces.

**Không có event ≠ không có hoạt động**: event có thể disabled, thấp hơn threshold, ngoài sampling window, bị loại khỏi rolling retention, hoặc bị mất vì áp lực dữ liệu. JFR hỗ trợ phân tích thống kê/hiệu năng, **không phải kho audit “exactly once” cho mọi giao dịch**.

## 4. Recording liên tục và rolling retention

Khi một sự cố hiếm diễn ra, bật profiler *sau* sự cố thường đã muộn. Always-on recording giữ sẵn một đoạn lịch sử gần đây để có thể dump lúc alert xuất hiện.

Ví dụ một chính sách minh họa:

```text
Recording name: service-continuous
Event settings: default
Disk repository: true
Max age:        30 minutes
Max size:       256 MiB
Incident dump:  /var/secure-jfr/incident.jfr
```

Đây không phải thông số bắt buộc. Chọn theo dung lượng volume, chi phí có thể chấp nhận, thời gian cần truy hồi trước alert và tốc độ phát sự kiện của **ứng dụng thực**.

### `maxage` và `maxsize` kiểm soát điều gì?

- **`maxage=30m`:** dữ liệu đã giữ quá 30 phút trên disk repository được dọn theo cơ chế retention.
- **`maxsize=256m`:** giới hạn kích thước dữ liệu giữ trong repository; JFR loại chunk cũ để nhường chỗ cho chunk mới.
- Nếu event tăng đột biến và chạm `maxsize` sớm, lịch sử có thể chỉ còn **vài phút** dù `maxage=30m`.
- Nếu event rate thấp, chunk quá cũ vẫn bị dọn theo `maxage` mặc dù `maxsize` chưa chạm.
- Giới hạn phụ thuộc **chunk rotation**; không hiểu nó là trần đúng từng byte tại mọi thời điểm.
- Những file `.jfr` **đã dump ra nơi khác** có retention riêng; `maxsize` không xóa tự động các snapshot ấy.
- `maxage/maxsize` **không kiểm soát số event được tạo** và không đặt hard limit cho CPU/heap của mã instrument.

Với `disk=true`, recording ghi dữ liệu vào JFR disk repository để lưu lịch sử tương đối dài. Với `disk=false`, dữ liệu chủ yếu ở memory buffers với phạm vi giữ hữu hạn; không coi nó là một circular log trên disk có thể bảo tồn nhiều giờ. Các giới hạn `maxage/maxsize` được thiết kế cho dữ liệu disk repository.

### Chi phí kiểm soát được ≠ miễn phí

JFR có thiết kế **low overhead** và thích hợp cho nhiều workload production, nhưng overhead thay đổi theo settings và tải. Event frequency, thresholds, stack traces, field size, số concurrent recordings và tốc độ disk đều ảnh hưởng. Không nên báo một con số “JFR luôn tăng 1% CPU” như cam kết. Hãy đo tail latency và throughput dưới workload đại diện.

## 5. Vận hành JFR bằng `jcmd` trên Java 11

`jcmd` là công cụ JDK tương tác với JVM đang chạy; JDK 11 hỗ trợ các lệnh `JFR.start`, `JFR.check`, `JFR.dump` và `JFR.stop`. Chúng cần quyền OS và điều kiện attach phù hợp với process; `12345` bên dưới là **PID minh họa**, phải thay bằng PID thật.

### 5.1. Xác nhận JVM và cú pháp lệnh

```bash
jcmd -l
jcmd 12345 help JFR.start
```

`jcmd -l` hiển thị process mà người chạy có thể quan sát. Không giả định nó sẽ thấy mọi JVM trong container. `help JFR.start` lấy tham số mà **runtime thực** hỗ trợ; hữu ích khi nâng cấp vendor/JDK.

### 5.2. Bắt đầu rolling recording

```bash
jcmd 12345 JFR.start name=service-continuous settings=default disk=true maxage=30m maxsize=256m
```

**Ý nghĩa:**

- `name`: đặt tên để phân biệt nhiều recording.
- `settings=default`: sử dụng preset `default.jfc` của JDK.
- `disk=true`: bật disk repository.
- `maxage=30m`, `maxsize=256m`: retention cho dữ liệu gần đây.
- Không đặt `duration`: phiên có thể chạy cho đến khi được dừng chủ động hoặc JVM kết thúc.

Nếu tổ chức không cho attach production JVM, hãy dùng startup option mục 6 hoặc quy trình vận hành đã phê duyệt. Không nâng quyền tùy tiện.

### 5.3. Kiểm tra và dump trong lúc recording vẫn chạy

```bash
jcmd 12345 JFR.check name=service-continuous
jcmd 12345 JFR.dump name=service-continuous filename=/var/secure-jfr/incident.jfr
```

`JFR.dump` **xuất snapshot**, không đồng nghĩa phải stop recording đang chạy. Recording vẫn có thể tiếp tục giữ các chunk mới để bạn tìm những sự kiện sau incident. File dump do **JVM target** ghi theo path/quyền của chính tiến trình ấy; sử dụng đường dẫn tuyệt đối, thư mục không công khai và bảo đảm còn storage.

### 5.4. Dừng khi không còn cần

```bash
jcmd 12345 JFR.stop name=service-continuous
```

Khi stop, recording không thu thêm dữ liệu. Nếu muốn giữ bằng chứng, dump trước hoặc sử dụng chính sách xuất file khi dừng đúng theo tài liệu JDK. Không tạo nhiều recording cùng tên/khác settings mà không kiểm tra `JFR.check`; hiệu ứng tổng hợp có thể làm tăng dữ liệu/overhead.

## 6. Bật JFR từ lúc khởi động JVM

Java 11 hỗ trợ `-XX:StartFlightRecording`:

```bash
java -XX:StartFlightRecording=name=always-on,settings=default,disk=true,maxage=30m,maxsize=256m -jar service.jar
```

`service.jar` là JAR của ứng dụng thật, **không đi kèm bài học**. Cách startup phù hợp khi muốn thu event trong giai đoạn khởi động hoặc không thể dùng `jcmd` attach. JFR của Java 11 không cần các flag “unlock commercial” của những JDK cũ; đừng áp dụng hướng dẫn lỗi thời đó.

Với container/Kubernetes:

1. Đảm bảo `jdk.jfr` có mặt trong JDK image; custom `jlink` image có thể không chứa module.
2. Kiểm tra quyền tạo file/chunk repository và dump.
3. Chọn quota disk phù hợp và giám sát disk pressure.
4. Có cách giữ/export snapshot khi pod bị thay thế hoặc restart.
5. Bảo vệ quyền đọc và lưu giữ file; JFR có thể chứa dữ liệu vận hành nhạy cảm.
6. Kiểm tra ảnh hưởng lên CPU/latency theo resource limits thật, không chỉ laptop.

## 7. Preset `default`, `profile` và custom `.jfc`

| Preset | Khi nào dùng | Cần chú ý |
| --- | --- | --- |
| `default` | Always-on/continuous, tạo baseline ít overhead | Mỗi JDK có tập events/settings cụ thể, không coi bất biến |
| `profile` | Điều tra chuyên sâu trong khoảng thời gian ngắn | Có thể tăng event rate, stack traces và chi phí |
| Custom `.jfc` | Chọn đúng event/threshold/period/stack trace của hệ thống | Cần review settings sau mỗi lần nâng JDK |

Ví dụ recording chuyên sâu 2 phút:

```bash
jcmd 12345 JFR.start name=short-profile settings=profile duration=2m filename=/var/secure-jfr/profile.jfr
```

Đây là **ví dụ vận hành**, không phải lệnh để chạy nếu chưa có quyền và đường dẫn thực. Đừng để `profile` chạy mãi ở production nếu chưa đo mức tác động. Nhiều JDK chứa `default.jfc` và `profile.jfc` trong `$JAVA_HOME/lib/jfr`; cú pháp event settings có thể thay đổi theo JDK, nên kiểm tra file của runtime đang triển khai.

## 8. Các nút điều khiển chi phí ở cấp event

`jdk.jfr.EventSettings` cung cấp lựa chọn:

| Setting | Ý nghĩa | Ví dụ điều chỉnh |
| --- | --- | --- |
| `enabled` | Cho phép hoặc tắt event type | Bật khi dữ liệu có giá trị điều tra |
| `threshold` | Ngưỡng duration tối thiểu để event được ghi | Ghi lock wait trên 10 ms thay vì mọi lần |
| `period` | Chu kỳ event định kỳ nếu loại đó hỗ trợ | CPU load mỗi giây |
| `stackTrace` | Lưu stack trace khi phát event | Chỉ bật nếu cần xác định call site |

Ví dụ **trích đoạn Java 11**:

```java
recording.enable("jdk.CPULoad")
        .withPeriod(Duration.ofSeconds(1));

recording.enable("jdk.FileRead")
        .withThreshold(Duration.ofMillis(10))
        .withoutStackTrace();
```

Đoạn này cần instance `Recording recording` và `java.time.Duration`, không chạy độc lập. Không mọi event đều có ngữ nghĩa `period` hoặc `threshold`. Threshold 10 ms chỉ là minh họa, không phải giá trị khuyến nghị cho mọi workload.

### Những nhầm lẫn về overhead

- `threshold=0` có thể ghi nhiều event duration rất ngắn, gây tăng kích thước file.
- `period` thích hợp với **periodic event**, không tự nhiên biến mọi `Event.commit()` ở hot path thành việc sampling đúng thống kê.
- `stackTrace=false` tiết kiệm chi phí lưu stack, nhưng vẫn có overhead tạo và ghi event.
- `maxsize` chỉ quản lý **lượng dữ liệu giữ lại**, không giảm việc ghi/serialize event ngay từ đầu.
- Một event có field `String` lớn hoặc tạo `JSON` mỗi lần cũng có CPU/heap cost ngoài overhead JFR.

**Thứ tự điều chỉnh:** chọn loại event cần thiết → threshold/period hợp lý → stack trace chọn lọc → metadata fields nhỏ → rolling retention → benchmark và giám sát thực tế.

## 9. Chương trình Java 11 chạy độc lập: custom event, bounded recording, đọc lại `.jfr`

Mã dưới đây dùng `jdk.jfr.Event`/`Recording` để ghi 3 custom events, đặt chính sách giữ dữ liệu, stop và dump recording, sau đó dùng `jdk.jfr.consumer.RecordingFile` **đọc từng event**. Mã không dùng `RecordingStream` của JDK 14+ và không cần server/mạng.

Chương trình đã được kiểm tra **biên dịch bằng `javac --release 11` và chạy trên OpenJDK 24**, in đúng những giá trị nêu bên dưới. Tạo file **`JfrContinuousDemo.java`**:

```java
import jdk.jfr.*;
import jdk.jfr.consumer.*;
import java.nio.file.*;
import java.time.Duration;

public class JfrContinuousDemo {

    @Name("lesson.DemoOperation")
    @Label("Demo Operation")
    @Category({"Application", "Operations"})
    public static class OperationEvent extends Event {
        @Label("Operation")
        public String operation;

        @Label("Units")
        public int units;
    }

    public static void main(String[] args) throws Exception {
        if (!FlightRecorder.isAvailable()) {
            System.out.println("jfr_available=false");
            return;
        }

        Path dump = Files.createTempFile("jfr-lesson-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.setName("demo-bounded");
                recording.setToDisk(true);
                recording.setMaxAge(Duration.ofMinutes(5));
                recording.setMaxSize(32L * 1024 * 1024);

                recording.enable(OperationEvent.class)
                        .withoutThreshold()
                        .withoutStackTrace();

                recording.start();
                for (int i = 1; i <= 3; i++) {
                    OperationEvent event = new OperationEvent();
                    event.operation = "process";
                    event.units = i;
                    event.begin();
                    event.commit();
                }
                recording.stop();
                recording.dump(dump);
            }

            int found = 0;
            int sum = 0;
            try (RecordingFile events = new RecordingFile(dump)) {
                while (events.hasMoreEvents()) {
                    RecordedEvent e = events.readEvent();
                    if ("lesson.DemoOperation".equals(
                            e.getEventType().getName())) {
                        if (!"process".equals(e.getString("operation"))) {
                            throw new AssertionError("Operation mismatch");
                        }
                        found++;
                        sum += e.getInt("units");
                    }
                }
            }

            System.out.println("custom_events=" + found);
            System.out.println("units_sum=" + sum);
            System.out.println("verified=" + (found == 3 && sum == 6));
        } finally {
            Files.deleteIfExists(dump);
        }
    }
}
```

Lệnh biên dịch/chạy với JDK 11 có module JFR:

```bash
javac --release 11 -encoding UTF-8 JfrContinuousDemo.java
java JfrContinuousDemo
```

**Đầu ra dự kiến khi JFR khả dụng:**

```text
custom_events=3
units_sum=6
verified=true
```

**Giải thích từng thành phần:**

1. `@Name("lesson.DemoOperation")` tạo type name ổn định; `@Label`/`@Category` cung cấp metadata hiển thị.
2. `OperationEvent` có hai field: mã hoạt động cố định `"process"` và số `units`. Không ghi request body, bearer token hay dữ liệu cá nhân.
3. `recording.enable(OperationEvent.class)` chỉ bật event type của bài test; `withoutThreshold()` có chủ đích để event rất ngắn không bị lọc; `withoutStackTrace()` giảm dữ liệu không cần thiết.
4. `setToDisk(true)` và giới hạn `setMaxAge`/`setMaxSize` minh họa rolling retention; ví dụ chỉ chạy ngắn, không khẳng định đã benchmark một recording chạy dài ngày.
5. Mỗi `event.begin()/event.commit()` phát một event; ba `units` lần lượt 1, 2, 3.
6. `recording.stop()` kết thúc thu thập; `recording.dump(dump)` tạo snapshot file tạm.
7. `RecordingFile` đọc tuần tự; chỉ đếm loại event có tên `lesson.DemoOperation`. Một file có thể còn nhiều event JDK khác, nên không dùng tổng tất cả event để đối chiếu.
8. Tổng `1+2+3=6`; output không in timestamp hay đường dẫn biến đổi nên xác định.
9. `try-with-resources` đóng đối tượng Recording/RecordingFile; `Files.deleteIfExists` dọn file tạm của bài học. File incident thật cần retention an toàn chứ không xóa ngay.
10. `FlightRecorder.isAvailable()` kiểm tra khả dụng. Nếu một custom runtime thiếu hẳn module `jdk.jfr`, chương trình cần được chạy trên image có module; guard này không thay cơ chế đóng gói module.

**Lưu ý quan trọng:** `withoutThreshold()` ở demo nhằm kiểm tra đếm được đúng 3 event, **không** phải cấu hình nên dùng mặc định cho event high-frequency trong production. `setMaxSize(32 MiB)` quản lý repository, không giới hạn chính xác disk usage của các snapshot đã dump.

## 10. Phát custom event ở mã nghiệp vụ

Một custom event có thể dùng để ghi thời gian xử lý một operation với ngưỡng, chẳng hạn khi vượt 20 ms mới giữ event. Hãy thiết kế event **nhỏ**, schema ổn định và không chứa dữ liệu bí mật.

Ví dụ trích đoạn cho một lớp `MyOperationEvent extends Event` đã khai báo:

```java
MyOperationEvent event = new MyOperationEvent();
event.begin();
try {
    processRequest();
} finally {
    event.end();
    if (event.shouldCommit()) {
        event.operationCode = "sync";
        event.commit();
    }
}
```

Đây là **trích đoạn**, cần tự định nghĩa `MyOperationEvent`, `operationCode` và `processRequest()`; không phải chương trình đầy đủ. Lời gọi `shouldCommit()` giúp tránh thu thập field nặng nếu event đã bị tắt hoặc không vượt threshold. Nếu custom event disabled, đừng làm thay đổi nghiệp vụ `processRequest()`; JFR chỉ là instrumentation.

### `Event.isEnabled()` khác `shouldCommit()` thế nào?

- `isEnabled()` trả lời loại event có được enable cho thu thập tại thời điểm gọi không.
- `shouldCommit()` kiểm tra event hiện tại có thỏa điều kiện ghi (chẳng hạn duration threshold) không.
- Một event enabled vẫn có thể **không** được giữ lại do threshold.
- Đừng serialize toàn bộ payload để tính field rồi mới kiểm tra `shouldCommit()`; khi có dữ liệu tốn kém, nên đo thời gian trước, chỉ thu metadata có phép nếu cần và vẫn phải giữ code nghiệp vụ chính xác.

## 11. Phân tích snapshot bằng `jfr`, `RecordingFile` và JMC

Với file snapshot đã được xuất:

```bash
jfr summary /var/secure-jfr/incident.jfr
jfr print --events jdk.CPULoad /var/secure-jfr/incident.jfr
```

`jfr summary` cho tổng quan event types/counts của file, `jfr print` hiển thị từng event theo bộ lọc. Nếu file chứa custom event trong ví dụ:

```bash
jfr print --events lesson.DemoOperation /var/secure-jfr/incident.jfr
```

**Ví dụ JfrContinuousDemo tự xóa file tạm**, nên lệnh đọc trên phải trỏ vào một file bạn đã giữ lại từ quy trình khác. Không kỳ vọng có `lesson.DemoOperation` trong một recording chưa hề chạy code demo đó.

**JDK Mission Control (JMC)** hỗ trợ giao diện phân tích timeline CPU/GC/locks/I/O và các rule chẩn đoán. JMC là công cụ có thể được cài riêng; một JDK container không nhất thiết kèm GUI.

Đọc bằng API Java 11:

```java
try (RecordingFile file = new RecordingFile(pathToJfr)) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        if ("jdk.CPULoad".equals(event.getEventType().getName())) {
            // Xử lý những field có trong schema runtime thực.
        }
    }
}
```

Đây là **trích đoạn** cần `Path pathToJfr`, import `jdk.jfr.consumer.RecordingFile`/`RecordedEvent` và xử lý `IOException`. Không dùng `RecordingFile.readAllEvents(path)` cho file lớn: Javadoc Java 11 nói phương thức này dành cho trường hợp đơn giản, **không** thiết kế để đọc toàn bộ recording khổng lồ vào memory. Javadoc cũng khuyến nghị chỉ đọc file JFR từ **nguồn đáng tin**.

## 12. Chọn event theo vấn đề cần điều tra

| Nhu cầu | Event/setting gợi ý | Tránh |
| --- | --- | --- |
| Tìm CPU hot path | `jdk.ExecutionSample`, CPU load | Coi samples là số lần chạy method chính xác |
| GC gây gián đoạn | `jdk.GarbageCollection` và các GC events phù hợp | Kết luận từ mỗi một pause đơn lẻ |
| Thread chờ lock | `jdk.JavaMonitorEnter`, `jdk.ThreadPark` | Threshold=0 cho mọi event ở production mà chưa đo |
| File/network I/O chậm | `jdk.FileRead`, `jdk.SocketRead` | Thu mọi I/O cực nhỏ kèm stack trace |
| Business operation chậm | Custom duration event có operation code | Đưa JSON body, email hoặc token vào event |
| Sự cố hiếm | Always-on `default` với disk rolling | Chỉ bật `profile` sau khi dữ liệu cũ bị mất |
| Điều tra sâu tại thời điểm cụ thể | `profile`/custom recording ngắn | Bật vô hạn, không giới hạn file dump |

**Không có preset chung cho mọi workload.** Một dịch vụ backend I/O-bound và một tác vụ batch CPU-bound có thể cần event types, thresholds và thời gian giữ khác nhau.

### Ví dụ tính ngân sách retention

Giả sử `maxsize=256 MiB`, `maxage=30 phút`. Khi event volume đạt 32 MiB/phút trong lúc peak, repository có thể chỉ giữ cỡ **8 phút** gần nhất trước khi dọn chunk cũ, bất kể maxage đặt 30 phút. Đây là ước lượng khái niệm, **không** phải metric được JFR bảo đảm; thực tế còn phụ thuộc chunk sizes, buffers và runtime.

Muốn thực sự giữ đủ 30 phút, phải đo bytes/minute và chọn maxsize/volume margin phù hợp. Giới hạn `maxage` là **thời gian tối đa**, không phải bảo đảm tối thiểu.

## 13. Chi phí CPU, heap, disk và stack trace

Các yếu tố khiến overhead tăng:

- Commit custom event ở mỗi vòng lặp nóng, đặc biệt hàng trăm nghìn đến hàng triệu lần/giây.
- Đặt threshold quá thấp khiến nhiều event duration được giữ lại.
- Bật stack trace ở mọi event tần suất cao.
- Dùng `profile` hoặc sự kiện allocation chi tiết quá lâu.
- Tạo `String` khổng lồ, serialize JSON/request object mỗi lần ghi.
- Ghi nhiều bản dump lớn liên tục trong thời điểm disk đang quá tải.
- Mở nhiều recording có settings chung/khác nhau mà không đo tổng overhead.

**Chiến lược từng lớp:**

1. **Giảm event count:** chỉ enable loại cần thiết, dùng threshold/period phù hợp.
2. **Giảm event cost:** tắt stack trace nếu chỉ cần số liệu, schema field nhỏ, kiểm tra `isEnabled`/`shouldCommit` để tránh tính field đắt tiền.
3. **Giảm retained bytes:** đặt `maxage`/`maxsize` cho disk repository.
4. **Giảm exported bytes:** có rate limit và retention cho `.jfr` dumps.
5. **Đo tác động thật:** benchmark baseline vs default vs profile, quan tâm throughput và **p95/p99 latency**, CPU, memory, disk, GC.

Đừng hiểu `disk=true` là đồng bộ ghi một file bằng `fsync` cho **từng event**, và đừng dùng JFR thay cho transactional audit store. Một số event có thể bị thiếu do cấu hình, sampling, threshold, retention hoặc điều kiện tài nguyên.

## 14. Bảo vệ dữ liệu nhạy cảm trong JFR

Một `.jfr` có thể chứa tên class/method/stack trace, tên thread, đường dẫn file, địa chỉ network và thông tin môi trường. Nếu ứng dụng tự ghi `Authorization`, cookie, API key, email, phone hoặc request body vào custom event, các bí mật đó có thể được **xuất vào file snapshot** và sao chép tiếp vào máy phân tích, ticket hay storage.

Các nguyên tắc:

1. Dùng **allowlist field**: operation code từ enum, status code, elapsed duration, byte count (nếu được phép); không serialize object nghiệp vụ thô.
2. Không ghi token, khóa, mật khẩu, session ID, raw URL query hay payload chứa PII.
3. Không dùng bearer token làm correlation ID.
4. Phân quyền `jcmd`/file dump theo chính sách least privilege.
5. Lưu `.jfr` ở thư mục bảo vệ, encryption và retention phù hợp; không công khai URL file.
6. Bảo vệ khi chuyển file tới JMC/analyzer; kiểm tra hệ thống lưu trữ bản sao.
7. Khi đưa file cho bên khác, đánh giá những event/field và stack trace có thể tiết lộ bí mật.
8. Chỉ parse recording từ nguồn đáng tin, hạn chế dung lượng và CPU của công cụ tiêu thụ.

JFR không phải text log nên bí mật có thể khó nhìn thấy, **không** có nghĩa file an toàn để chia sẻ bừa bãi. Cần chính sách bảo mật tương đương những dữ liệu chẩn đoán nhạy cảm khác.

## 15. JFR khác metrics, logs và tracing như thế nào?

| Công cụ | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| Metrics | SLO, error rate, latency percentiles, throughput theo thời gian | Ít chi tiết call stack |
| Logs | Business event, mã lỗi, hoạt động nghiệp vụ đã chọn | Khó ghi đầy đủ JVM performance mà vẫn nhẹ |
| Distributed traces | Liên hệ các span/request xuyên nhiều dịch vụ | Không thay sampling CPU/GC/lock của JVM |
| **JFR** | Timeline JVM/JDK và custom events, stack sampling, contention, I/O | Không bảo đảm ghi đủ mọi transaction như audit |

JFR thường dùng để **giải thích** một spike do metrics báo. Ví dụ: metrics có latency tăng lúc 10:02; dump JFR khoảng trước/sau đó rồi đối chiếu `JavaMonitorEnter`, GC, CPU load, socket events và custom operation duration. Đừng kết luận từ một event riêng lẻ thiếu context.

## 16. Recording liên tục khác JFR Event Streaming của JDK 14+

Một số ví dụ online dùng:

```java
RecordingStream stream = new RecordingStream();
stream.enable("jdk.CPULoad");
stream.onEvent("jdk.CPULoad", event -> {
    // Xử lý event gần real-time.
});
stream.startAsync();
```

Đây là **trích đoạn chỉ áp dụng JDK 14+**, vì `RecordingStream` ra đời cùng **JEP 349 (JFR Event Streaming)**; không có trong Java 11, nên không biên dịch được khi `--release 11`.

**Java 11 vẫn ghi liên tục được** bằng `Recording`/`JFR.start`, rồi `JFR.dump` và `RecordingFile` để đọc snapshot. Không đồng nhất recording đang chạy lâu với callback stream tiêu thụ event trong real time. Nếu ứng dụng đã nâng JDK mới, Event Streaming là lựa chọn bổ sung cần đánh giá riêng theo mục tiêu và overhead.

## 17. Kịch bản kiểm thử trước production

Một kế hoạch thử nghiệm có cơ sở cần ít nhất ba baseline:

| Cấu hình | Thử nghiệm | Đo gì |
| --- | --- | --- |
| Không có recording | Tải sản xuất giả lập | CPU, p50/p95/p99, throughput, heap, disk |
| `default` + rolling limits | Ghi liên tục | Overhead tăng thêm, bytes/minute, lịch sử còn giữ |
| `profile`/custom 2–5 phút | Điều tra chi tiết | Event count, sampling, stack trace volume, tail latency |

Các bài test quan trọng:

- **Retention:** giữ recording lâu để chạm `maxage`/`maxsize`, dump và kiểm tra cửa sổ còn lại.
- **Burst:** custom event frequency tăng rất cao; quan sát CPU, disk, event volume.
- **Disk pressure:** volume gần đầy, đường dẫn dump thiếu quyền; có alert và xử lý rõ.
- **JVM restart/container replacement:** xác định khả năng mất repository và điều kiện export snapshots.
- **Concurrently running recordings:** mở nhiều recording và xác minh tổng overhead, không chỉ của từng phiên.
- **Custom runtime image:** `jdk.jfr` không có thì class/module có thể không load; test image thực tế.
- **Privacy:** inject secret sentinel vào request test và xác nhận **không** xuất hiện trong custom event schema/dump.
- **File lớn:** consumer phải đọc tuần tự, không cần giữ `List` chứa hàng triệu event.
- **Error paths:** tạo recording, stop, dump, cleanup đúng ngay cả khi exception.
- **Version upgrade:** đối chiếu event availability, settings, JFR file reader và JDK vendor.

Mỗi phép thử cần rõ **workload, thời gian warm-up, số lần lặp, số JVM, version JDK và nền tảng**, không chỉ một ảnh chụp CPU từ laptop. Không đưa số overhead của môi trường test thành SLA cho tất cả ứng dụng.

## 18. Lỗi thường gặp và sửa như thế nào

| Sai lầm | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| Gọi JFR là logger văn bản | Mất event schema và timeline | Phân tích `.jfr` theo type/time |
| Tin JFR luôn chỉ tiêu tốn một con số % cố định | Overhead phụ thuộc cài đặt/workload | Benchmark trước và sau |
| `maxsize` là giới hạn CPU | Maxsize là dung lượng retention | Điều chỉnh event frequency/stack/threshold |
| `maxage=30m` đảm bảo đủ 30m | Maxsize có thể loại chunk sớm | Đo retained window thật |
| `disk=false` vẫn lưu nhiều giờ | Memory buffer hữu hạn | Dùng disk rolling nếu cần lịch sử |
| Mọi event được ghi không bỏ sót | Threshold/sampling/retention loại dữ liệu | Không dùng làm audit exactly-once |
| Đặt `threshold=0` cho hot path | Event volume lớn | Threshold phù hợp mục tiêu |
| Dùng `period` cho mọi custom event | Không phải mọi event periodic | Hiểu loại event trước |
| Tắt stack trace là không tốn gì | Commit/field vẫn có overhead | Giảm rate và field cost |
| Không có `jdk.FileRead` nên chắc chắn không đọc file | Có thể disabled hoặc threshold lọc | Xem recording settings |
| Ghi request body/token trong event | File JFR có thể bị chia sẻ | Chỉ metadata không nhạy cảm |
| Dump một file mới mỗi giây | Gây storage/Disk I/O pressure | Giới hạn tần suất và retention dumps |
| `JFR.dump` đồng nghĩa `JFR.stop` | Dump không phải stop | Quản lý riêng |
| Đọc file cực lớn bằng `readAllEvents` | Tăng memory/OOME | `RecordingFile` đọc từng event |
| Java 11 hỗ trợ `RecordingStream` | API từ JDK 14 | Java 11 dùng `RecordingFile` |
| Custom `jlink` image không có `jdk.jfr` | Module bị loại khi đóng gói | Thêm module vào runtime nếu cần |
| Không kiểm soát file `.jfr` | Rò tên host/path/fields | Quyền truy cập và retention an toàn |

## 19. Bài luyện tập có đáp án

**Bài 1.** `settings=default`, `maxage=30m`, `maxsize=256m` nhưng file dump chỉ giữ 6 phút của một giờ hoạt động. Có sai không?

**Đáp án:** Không nhất thiết. Event rate cao có thể chạm maxsize trước khi maxage hết hạn; chunk cũ bị loại. Cần đo bytes/minute và dung lượng thực.

**Bài 2.** Muốn tìm method nào nóng CPU, có nên coi 200 `jdk.ExecutionSample` tương đương method chạy 200 lần?

**Đáp án:** Không. Đây là sampling. Dùng để nhận diện hotspot tương đối, kết hợp measurements khác; không biến samples thành counter chính xác.

**Bài 3.** `JFR.dump` có cần stop recording always-on không?

**Đáp án:** Không. Dump snapshot dữ liệu hiện giữ; có thể tiếp tục recording. `JFR.stop` là thao tác riêng.

**Bài 4.** Vì sao `jdk.FileRead` không xuất hiện, dù biết service đọc file?

**Đáp án:** Event có thể bị tắt, những lần đọc đều dưới threshold, file snapshot không bao phủ khoảng thời gian đó hoặc dữ liệu đã bị loại. Kiểm tra settings, period/threshold và retention.

**Bài 5.** Tăng `maxsize` từ 256m lên 1g có làm `event.commit()` trong hot loop rẻ hơn?

**Đáp án:** Không. Maxsize thay đổi lượng dữ liệu giữ trên disk, không giảm frequency/field/stacktrace work ở điểm phát.

**Bài 6.** Vì sao code mẫu `RecordingFile` duyệt từng event, không gọi `readAllEvents()`?

**Đáp án:** Đọc tuần tự tránh tải toàn bộ các event của file lớn vào heap; đây là hướng phù hợp cho consumer cần xử lý file lớn có kiểm soát.

**Bài 7.** Java 11 không tìm thấy class `RecordingStream`. Cần sửa thế nào?

**Đáp án:** Event Streaming chỉ từ JDK 14. Dùng `Recording`/`RecordingFile` trong Java 11, hoặc nâng JDK theo kế hoạch nếu cần streaming near-real-time.

**Bài 8.** Custom event muốn ghi body HTTP khi có lỗi để dễ debug. Có nên không?

**Đáp án:** Không mặc định. Body có thể chứa credentials/PII; file JFR còn được dump và chia sẻ. Ghi operation code, status, latency và dữ liệu được allowlist.

**Bài 9.** Trong chương trình demo, ba event có `units` = 1,2,3. Vì sao kết quả là `custom_events=3` và `units_sum=6`?

**Đáp án:** Vì đã enable đúng event type, bỏ threshold cho bài thử, chỉ filter type ấy rồi cộng 1+2+3; không phụ thuộc timestamp/file path.

## 20. Checklist triển khai

1. Đã xác định JDK/vendor và module `jdk.jfr` có mặt chưa?
2. Recording có mục tiêu rõ: CPU, GC, monitor contention, I/O hay custom latency?
3. Always-on có dùng event preset phù hợp (thường bắt đầu `default`)?
4. `profile` có deadline/owner rõ và không chạy vô hạn không?
5. Event settings có kiểm soát threshold, period, enabled, stackTrace?
6. Hot path có tránh serialize field không cần thiết, giới hạn volume?
7. `disk=true` khi cần history; `maxage` và `maxsize` đã đo bằng load thật?
8. Disk repository và dump directory có quota/quyền/retention riêng?
9. `JFR.check`/`JFR.dump` có được thử trên runtime target?
10. File `.jfr` có tránh secret/PII và được bảo vệ như artifact nhạy cảm?
11. Consumer có đọc tuần tự và chỉ file từ nguồn đáng tin?
12. Latency p95/p99, CPU, disk, heap có được so baseline với recording?
13. Có kế hoạch dump trước khi rolling window xóa dữ liệu sự cố?
14. Có xử lý container restart, disk full, JFR unavailable và cleanup?
15. Có tránh API từ JDK 14+ trong mã Java 11 và các option legacy?

## 21. Tóm tắt và nguồn chính thức

**Ghi nhớ:** JFR thu thập các **event có cấu trúc** có timestamp/field/optional stack trace; recording chọn những event cần ghi; chế độ **continuous rolling** với `maxage`/`maxsize` cho phép giữ phần lịch sử gần đây để dump khi sự cố. Muốn chi phí kiểm soát được, cần điều chỉnh **số event, chi phí mỗi event, retention, tần suất snapshot**, đồng thời benchmark và bảo vệ dữ liệu.

**Tài liệu Oracle/OpenJDK và hướng dẫn hiện hành:**

- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328) — tích hợp JFR vào OpenJDK 11, mục tiêu thu thập low-overhead.
- [Oracle Java SE 11 — `Recording`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html) — start/stop/dump, `setToDisk`, `setMaxAge`, `setMaxSize`.
- [Oracle Java SE 11 — `Event`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html) — `begin`, `end`, `commit`, `isEnabled`, `shouldCommit`.
- [Oracle Java SE 11 — `EventSettings`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html) — threshold, period, stack traces.
- [Oracle Java SE 11 — `RecordingFile`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html) — đọc file JFR tuần tự và lưu ý với file lớn.
- [Oracle Java SE 11 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html) — các lệnh `jcmd JFR.start/check/dump/stop`.
- [Oracle Java SE 11 — Java launcher](https://docs.oracle.com/en/java/javase/11/tools/java.html) — `-XX:StartFlightRecording` và các tham số startup.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349) — API Event Streaming từ JDK 14, không thuộc Java 11.
- [Dev.java — Introduction to JDK Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/intro/) — cơ chế events và khả năng always-on.
- [Dev.java — Configuring JDK Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/) — default/profile và cách lựa chọn settings.
