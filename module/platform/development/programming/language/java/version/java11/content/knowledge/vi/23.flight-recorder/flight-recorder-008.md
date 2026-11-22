# Thu bản ghi từ tiến trình đang chạy bằng Java Flight Recorder (Java 11+)

**Chủ đề cha: Flight Recorder.** Khi một ứng dụng Java đang chạy bị tăng CPU, độ trễ bất thường, dừng vì GC hoặc có thread chờ lâu, việc khởi động lại tiến trình để gắn profiler có thể làm biến mất hiện tượng cần điều tra. **Java Flight Recorder (JFR)** cho phép bắt đầu ghi các sự kiện chẩn đoán ngay trong **JVM đang hoạt động**, không cần biên dịch lại ứng dụng hoặc thêm đoạn mã trước khi khởi chạy.

Với JDK 11+, quy trình tiêu chuẩn là xác định đúng PID, dùng `jcmd <PID> JFR.start`, xác minh bằng `JFR.check`, xuất file `.jfr` bằng `JFR.dump` và kết thúc bằng `JFR.stop`. Các API trong bài tiếp tục được hỗ trợ ở các JDK hiện đại; không dựa vào tùy chọn thương mại hoặc cơ chế legacy của những JDK trước đây.

## 1. JFR ghi dữ liệu gì và không ghi gì?

Flight Recorder là hệ thống **event recording** được tích hợp vào JVM. Tùy cấu hình, bản ghi có thể chứa:

- CPU samples và call stacks để tìm đoạn mã tiêu tốn thời gian xử lý.
- Các sự kiện garbage collection, thời gian GC pause, heap usage.
- Thread activity, thread parking, synchronization và monitor contention.
- Những thao tác I/O, socket, file, class loading hoặc compilation khi loại event tương ứng được bật.
- Những sự kiện nghiệp vụ do ứng dụng định nghĩa bằng `jdk.jfr.Event`.

JFR **không phải** bản sao toàn bộ heap như `.hprof`, cũng không phải trình theo dõi mọi method invocation theo từng dòng. JFR chỉ ghi **những event đã bật** trong một khoảng thời gian, với sampling/threshold/period/stack-trace settings tương ứng. Không thể kết luận rằng một event chưa từng xảy ra chỉ vì nó vắng mặt trong file.

Ba thực thể cần phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **JVM target** | Tiến trình đang chạy cần chẩn đoán, xác định bằng PID |
| **Recording** | Phiên thu sự kiện sống trong JVM, có tên/ID, settings, thời lượng và retention |
| **Dump file `.jfr`** | File nhị phân đã xuất để đọc bằng `jfr`, JMC hoặc JFR API |

Sơ đồ:

```text
JVM đang chạy (PID)
     |
     +-- jcmd PID JFR.start ---> Recording đang RUNNING
                                   |
                                   +-- thu CPU/GC/thread/custom events
                                   +-- retention trong buffers/repository
                                   |
     +-- jcmd PID JFR.check ------+  xem trạng thái
                                   |
     +-- jcmd PID JFR.dump -------+----> incident.jfr
                                   |       |
                                   |       +-- jfr summary
                                   |       +-- jfr print
                                   |       +-- JDK Mission Control
                                   |
                                   +-- vẫn RUNNING sau dump!
                                   |
     +-- jcmd PID JFR.stop -------+---> Recording kết thúc
```

**Điểm dễ nhầm nhất:** `JFR.dump` **không dừng** recording; nó lưu dữ liệu hiện có ra file, còn thu tiếp. `JFR.stop` mới kết thúc recording đang chạy.

## 2. Điều kiện cần để attach vào JVM đang chạy

Cần **JDK có `jcmd`**, JVM hỗ trợ JFR và quyền của hệ điều hành cho phép attach.

1. **JDK:** dùng `jcmd` từ JDK phù hợp với runtime đích; image runtime tối giản có thể không chứa tool này.
2. **Cùng môi trường:** jcmd hoạt động như công cụ local; thường phải chạy trên cùng máy và không gian tiến trình phù hợp với JVM target.
3. **Đúng danh tính OS:** user/group thực thi công cụ phải có quyền tương ứng với user/group của Java process. Tránh chạy lệnh đặc quyền hoặc thay đổi bảo mật chỉ để thu dữ liệu khi chưa được duyệt.
4. **Attach mechanism:** nếu JVM bị chặn attach bằng chính sách, cấu hình như `-XX:+DisableAttachMechanism` hoặc hạn chế container/OS, lệnh có thể thất bại.
5. **Đường dẫn writable:** vị trí ghi `.jfr` được hiểu từ **filesystem mà JVM target nhìn thấy**, không nhất thiết là filesystem của laptop người vận hành.
6. **Dung lượng trống:** phải đủ cho repository/snapshots, đồng thời có retention và giới hạn nguồn lực cho production.

**Không cần `-XX:+UnlockCommercialFeatures`** khi sử dụng JFR tích hợp trên OpenJDK/Oracle JDK 11 trở lên. Những hướng dẫn yêu cầu kích hoạt JFR thương mại của các đời Java cũ là kiến thức không nên áp dụng cho hệ thống mới.

### Xác định đúng PID

```bash
java -version
jcmd -l
```

Ví dụ minh họa output (PID và lớp ứng dụng thay đổi mỗi môi trường):

```text
12345 com.example.orders.Application
67890 jdk.jcmd/sun.tools.jcmd.JCmd -l
```

Ở những ví dụ tiếp theo, **12345 là PID giả định**, phải thay bằng PID thật. Không dùng `jcmd 0 JFR.start ...` để thử hàng loạt: một số diagnostic commands có thể tác động tới nhiều JVM, không phù hợp với quy trình điều tra một service.

Xem thông tin trước khi bắt đầu:

```bash
jcmd 12345 VM.command_line
jcmd 12345 help
jcmd 12345 help JFR.start
```

Các lệnh này giúp kiểm tra bạn đang chọn đúng JVM và xem các diagnostic commands được JVM target hỗ trợ. Không suy rằng mọi option trên JDK mới đều có trên một build JDK 11 khác.

## 3. Ghi nhanh 60 giây rồi tự xuất file

Đây là cách phù hợp khi incident đang diễn ra và người vận hành muốn thu một cửa sổ ngắn.

```bash
jcmd 12345 JFR.start name=incident60 settings=profile duration=60s filename=/var/tmp/incident60.jfr
jcmd 12345 JFR.check
```

Giải thích:

- `name=incident60` đặt tên phiên, giúp phân biệt khi có nhiều recordings.
- `settings=profile` sử dụng profile sự kiện phong phú, tiện chẩn đoán ngắn hạn nhưng overhead cao hơn `default`.
- `duration=60s` giới hạn thời lượng. Khi hết thời gian, recording dừng và cố gắng xuất kết quả tới file đã chọn.
- `filename=/var/tmp/incident60.jfr` là đường dẫn file **ở phía JVM target**; thư mục phải tồn tại và target JVM có quyền ghi.
- `JFR.check` xem trạng thái trước khi phiên kết thúc; sau 60 giây, recording có thể đã không còn RUNNING.

Đợi đủ thời lượng, sau đó kiểm tra:

```bash
jfr summary /var/tmp/incident60.jfr
```

Không có output thống nhất cho mọi ứng dụng vì số lượng/types của events phụ thuộc workload, settings và JDK. Nếu file không tồn tại, kiểm tra kết quả lệnh start, elapsed time, quyền truy cập thư mục và disk quota; đừng kết luận ngay rằng JFR đã hỏng.

**Quan trọng:** hiện tượng cần điều tra phải xảy ra **trong thời gian recording**. Một phiên bắt đầu lúc 15:02 không tự khôi phục các CPU stacks đã không được ghi lúc 15:00.

## 4. Thu liên tục và dump khi có sự cố

Với incident khó tái hiện hoặc xảy ra vào giờ không định trước, cách hữu ích là để một recording nhẹ chạy liên tục với retention có hạn.

```bash
jcmd 12345 JFR.start name=rolling settings=default disk=true maxage=2h maxsize=256m
jcmd 12345 JFR.check name=rolling
```

| Tùy chọn | Tác dụng |
| --- | --- |
| `settings=default` | Event preset nhẹ hơn profile, phù hợp hơn cho ghi liên tục |
| `disk=true` | Sử dụng JFR repository trên đĩa khi đang ghi |
| `maxage=2h` | Giới hạn tuổi dữ liệu được giữ; không bảo đảm luôn giữ đủ 2 giờ nếu chạm giới hạn khác |
| `maxsize=256m` | Giới hạn lượng dữ liệu recording giữ trong repository |
| Không có `duration` | Chạy cho đến khi được dừng hoặc JVM kết thúc |
| Không có `filename` | Chưa chốt file output; có thể chủ động dump khi cần |

Khi nhận alert:

```bash
jcmd 12345 JFR.dump name=rolling filename=/var/tmp/rolling-first.jfr
jcmd 12345 JFR.check name=rolling
```

Nếu JVM vẫn chạy và không có lỗi, `JFR.check` tiếp tục hiển thị `rolling` đang hoạt động. Đây là **snapshot**, không phải hành động dừng. Bạn có thể tiếp tục lấy ảnh chụp thứ hai:

```bash
jcmd 12345 JFR.dump name=rolling filename=/var/tmp/rolling-second.jfr
```

Hai file có thể chứa dữ liệu **chồng lắp theo thời gian** vì recording vẫn giữ lịch sử. Không hiểu “dump lần một” là thao tác xóa buffer cũ hay bắt đầu recording mới.

Khi đã thu đủ và muốn kết thúc:

```bash
jcmd 12345 JFR.stop name=rolling
jcmd 12345 JFR.check
```

Nếu cần giữ dữ liệu cuối cùng, hãy **dump trước khi stop** để chắc chắn có file. Không tự ý dừng recording tên `rolling` do hệ thống giám sát khác đang quản lý.

### Repository và file đã xuất là hai loại dung lượng

`maxsize`/`maxage` ràng buộc dữ liệu ghi giữ trong repository của recording; **không tự xóa những tệp `.jfr` đã dump**. Nhiều snapshots cần chính sách đặt tên, quản lý bản sao và thời hạn lưu riêng. Khi hệ thống có lượng event lớn, `maxsize` có thể khiến lịch sử được giữ ngắn hơn `maxage`.

## 5. Phân biệt bốn lệnh jcmd cốt lõi

| Diagnostic command | Mục đích | Recording có tiếp tục chạy? |
| --- | --- | --- |
| `JFR.start` | Bắt đầu phiên thu mới | Có, nếu start thành công |
| `JFR.check` | Liệt kê/kiểm tra các phiên, có thể kèm event settings | Không thay đổi |
| `JFR.dump` | Xuất nội dung hiện có thành file `.jfr` | **Có**, dump không tự dừng |
| `JFR.stop` | Kết thúc phiên thu | **Không** |

Khi có nhiều recording, chỉ rõ `name` để không nhắm nhầm. Những ví dụ chọn một recording cụ thể bằng tên, không dựa vào việc tên được JVM tự sinh khi bỏ option.

Kiểm tra các tùy chọn ngay trên JDK target:

```bash
jcmd 12345 help JFR.start
jcmd 12345 help JFR.check
jcmd 12345 help JFR.dump
jcmd 12345 help JFR.stop
```

Các bản JDK mới bổ sung những khả năng như xem sự kiện ngay trên JVM hoặc thu theo khoảng thời gian chi tiết. Trên Java 11, workflow **start/check/dump/stop** là nền tảng ổn định; chỉ dùng các option mở rộng sau khi đã kiểm tra phiên bản.

## 6. Chọn cấu hình default, profile và event tùy chỉnh

JDK cung cấp các mẫu cấu hình `default.jfc` và `profile.jfc` trong `JAVA_HOME/lib/jfr`.

**`settings=default`:** lựa chọn thường phù hợp cho recording dài hạn; ưu tiên overhead thấp hơn và tập event vừa đủ. **`settings=profile`:** thu nhiều thông tin phân tích hơn, thích hợp khi cần hotspot/stack samples trong cửa sổ ngắn.

Đừng gán một số overhead tuyệt đối cho mọi ứng dụng. Chi phí phụ thuộc lưu lượng, CPU, loại event, độ sâu stack, settings, repository I/O và nhiều recordings chạy đồng thời. Cần đo thực nghiệm theo workload thực tế.

Nếu file không có thông tin đang tìm, trước khi kết luận “không có GC”, “không có contention”, hãy xem cấu hình:

```bash
jcmd 12345 JFR.check name=rolling verbose=true
```

`verbose=true` thường in nhiều thiết lập từng loại event. Một event có thể chưa được bật, bị threshold lọc, hoặc nằm ngoài khoảng thời gian đã giữ. Có thể tạo một `.jfc` cấu hình riêng rồi bắt đầu recording:

```bash
jcmd 12345 JFR.start name=focused settings=/opt/app/jfr/focused.jfc duration=90s filename=/var/tmp/focused.jfr
```

Lệnh này giả định file `/opt/app/jfr/focused.jfc` **thực sự tồn tại trong môi trường JVM target** và hợp lệ. Không chỉnh sửa bản `default.jfc`/`profile.jfc` dùng chung của JDK để thay đổi tùy tiện trên production.

## 7. Ví dụ Java 11: một JVM sống để thực hành attach

Đây là ứng dụng Java nhỏ tạo **custom JFR events** và duy trì tiến trình trong lúc người học mở terminal thứ hai. Nó không cần thư viện bên ngoài.

### Tệp `JfrLiveTarget.java`

```java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

public class JfrLiveTarget {
    @Name("demo.LivePulse")
    @Label("Demo Pulse")
    @Category({"Training", "JFR"})
    static final class LivePulse extends Event {
        @Label("Sequence")
        long sequence;

        @Label("Checksum")
        long checksum;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("PID: " + ProcessHandle.current().pid());
        System.out.println("Use Ctrl+C to stop this demo.");

        long sequence = 0;
        while (true) {
            LivePulse pulse = new LivePulse();
            pulse.sequence = ++sequence;
            pulse.begin();

            long sum = 0;
            for (int i = 0; i < 20000; i++) {
                sum += (i * 17L) ^ sequence;
            }

            pulse.checksum = sum;
            pulse.end();
            pulse.commit();

            if (sequence % 20 == 0) {
                System.out.println("pulses: " + sequence);
            }
            Thread.sleep(100);
        }
    }
}
```

Biên dịch/chạy trong **terminal A**:

```bash
javac --release 11 -encoding UTF-8 JfrLiveTarget.java
java JfrLiveTarget
```

Stdout minh họa, với PID khác nhau theo môi trường:

```text
PID: <PID-cua-tien-trinh>
Use Ctrl+C to stop this demo.
pulses: 20
pulses: 40
...
```

Giữ chương trình đang chạy, mở **terminal B** trong cùng môi trường có quyền attach. Thay PID=12345 bằng số thực tế.

```bash
jcmd 12345 JFR.start name=lab settings=profile duration=30s filename=/var/tmp/lab.jfr
jcmd 12345 JFR.check name=lab
```

Sau khi recording đủ 30 giây và ghi tệp:

```bash
jfr summary /var/tmp/lab.jfr
jfr print --events demo.LivePulse /var/tmp/lab.jfr
```

Nếu không thấy `demo.LivePulse`, kiểm tra window thu, tên event, output của `JFR.check verbose=true` và cấu hình `.jfc`. Số events và thời điểm không cố định vì thread scheduler và cấu hình runtime. Nếu chương trình bị chặn mở attach trong sandbox, hãy dùng môi trường JDK có quyền phù hợp, không sửa chính sách hệ thống ngoài phạm vi được phép.

**Lưu ý:** `ProcessHandle.current().pid()` có từ Java 9 và dùng được trong Java 11. `@Name("demo.LivePulse")` giúp lọc event theo tên, còn `Event.commit()` không đồng nghĩa mọi lần gọi đều được giữ khi không có recording hoặc event bị disable.

## 8. Đọc file .jfr bằng jfr command

Công cụ `jfr` nằm trong thư mục `bin` của JDK phù hợp.

### 8.1. Tóm tắt nội dung

```bash
jfr summary /var/tmp/lab.jfr
```

Summary có thể hiển thị cửa sổ thời gian, thời lượng, số lượng event, kích thước lưu theo loại event. File trống events có thể vẫn là một file hợp lệ; phân biệt file không có event mong đợi với file sai định dạng/không đọc được.

### 8.2. Lọc theo event

```bash
jfr print --events demo.LivePulse /var/tmp/lab.jfr
jfr print --events jdk.CPULoad /var/tmp/lab.jfr
jfr print --events jdk.GarbageCollection /var/tmp/lab.jfr
```

Không có stdout cố định: timestamps, event count, thread và stack frames phụ thuộc workload. Có thể dùng output có cấu trúc khi cần xử lý bằng script, nhưng phải lưu ý file JFR có thể rất lớn và chứa metadata nhạy cảm.

### 8.3. Dùng JDK Mission Control

**JDK Mission Control (JMC)** cung cấp giao diện phân tích timeline/GC/CPU/thread/memory từ file JFR. Nó có thể được cài riêng, **không nên mặc định JDK bất kỳ đều đã bao gồm ứng dụng JMC**. Khi file được dump trong server/container, cần chuyển file qua một kênh được phép tới máy phân tích và giữ đúng quyền bảo mật.

Lời khuyên: bắt đầu bằng timeline và câu hỏi điều tra cụ thể. Ví dụ CPU cao nên đối chiếu CPU samples, host usage và workload; GC spikes nên xem pause, heap và allocation, không chỉ nhìn một sample duy nhất rồi kết luận memory leak.

## 9. Phân tích file bằng API consumer Java 11

Module `jdk.jfr.consumer` cung cấp `RecordingFile` và `RecordedEvent`. Đọc **lần lượt từng event** phù hợp hơn với file lớn so với gom toàn bộ events vào một list.

### Tệp `JfrReadEvents.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrReadEvents {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java JfrReadEvents <file.jfr>");
        }
        Path file = Path.of(args[0]);
        if (!Files.isRegularFile(file)) {
            throw new IllegalArgumentException("File not found");
        }

        long all = 0;
        long pulse = 0;
        long gc = 0;

        try (RecordingFile reader = new RecordingFile(file)) {
            while (reader.hasMoreEvents()) {
                RecordedEvent event = reader.readEvent();
                all++;
                String type = event.getEventType().getName();
                if ("demo.LivePulse".equals(type)) {
                    pulse++;
                }
                if ("jdk.GarbageCollection".equals(type)) {
                    gc++;
                }
            }
        }

        System.out.println("parsed: true");
        System.out.println("events: " + all);
        System.out.println("demo pulses: " + pulse);
        System.out.println("GC events: " + gc);
    }
}
```

```bash
javac --release 11 -encoding UTF-8 JfrReadEvents.java
java JfrReadEvents /var/tmp/lab.jfr
```

Mã có thể biên dịch trên JDK 11+. Các con số thay đổi theo file; chỉ in `parsed: true` khi hoàn tất việc đọc không có exception. Việc dùng `try-with-resources` đóng file dù đọc thất bại. Khi nhận file từ nguồn ngoài, vẫn phải hạn chế size, CPU/time và tài nguyên của parser.

## 10. API JFR trong chính ứng dụng: dump không cần dừng

`jcmd` là công cụ để **gắn từ bên ngoài** vào JVM đã chạy. Nếu bạn kiểm soát mã của ứng dụng, Java 11 còn có `jdk.jfr.Recording` để khởi tạo, dump, stop và close một recording **ngay trong tiến trình**.

Dưới đây là một demo tự đủ: tạo 10 custom events, xuất file khi recording vẫn ở trạng thái `RUNNING` rồi đọc lại để xác nhận.

### Tệp `JfrSelfCapture.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.RecordingState;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrSelfCapture {
    @Name("demo.InProcess")
    @Label("In-Process Event")
    static final class CustomEvent extends Event {
        long value;
    }

    public static void main(String[] args) throws Exception {
        Path file = Path.of("self-capture.jfr");

        try (Recording recording =
                new Recording(Configuration.getConfiguration("default"))) {
            recording.enable(CustomEvent.class);
            recording.setName("self-capture");
            recording.setToDisk(true);
            recording.start();

            for (int i = 0; i < 10; i++) {
                CustomEvent event = new CustomEvent();
                event.value = i;
                event.commit();
            }

            // Dump được gọi trong trạng thái RUNNING.
            recording.dump(file);
            System.out.println("file exists: "
                    + Files.isRegularFile(file));
            System.out.println("still running: "
                    + (recording.getState() == RecordingState.RUNNING));

            recording.stop();
        }

        long count = 0;
        try (RecordingFile reader = new RecordingFile(file)) {
            while (reader.hasMoreEvents()) {
                RecordedEvent event = reader.readEvent();
                if ("demo.InProcess".equals(
                        event.getEventType().getName())) {
                    count++;
                }
            }
        }
        System.out.println("custom events: " + count);
    }
}
```

```bash
javac --release 11 -encoding UTF-8 JfrSelfCapture.java
java JfrSelfCapture
```

Stdout mong đợi khi JFR sẵn có và thư mục hiện tại writable:

```text
file exists: true
still running: true
custom events: 10
```

Điểm đặc biệt: `recording.dump(file)` không tự stop phiên; sau dump, trạng thái vẫn `RUNNING`. `recording.stop()` dừng, còn `close()` (qua `try-with-resources`) giải phóng tài nguyên. `recording.enable(CustomEvent.class)` bật đúng loại event thay vì chỉ giả định template mặc định thu nó.

**Giới hạn:** API in-process chỉ làm việc khi code đã được tích hợp/triển khai. Nó không thay thế `jcmd` trong tình huống bạn cần attach từ ngoài vào một JVM không thể sửa/restart. Không cho một endpoint HTTP công khai điều khiển recording mà thiếu xác thực và giới hạn.

## 11. Chạy trong Docker hoặc Kubernetes

Trong container, ba câu hỏi thường gây nhầm là: **PID nào? tool có ở đâu? file nằm ở đâu?**

Ví dụ minh họa cho Docker:

```bash
docker exec -it my-java-container jcmd -l
docker exec -it my-java-container jcmd 1 help JFR.start
```

**PID 1 chỉ là giả định**, đúng khi Java thật sự là PID 1 bên trong container; kiểm tra bằng `jcmd -l` hoặc công cụ OS. Nếu image là JRE/runtime image tối giản, có thể không có `jcmd`. Khi đó cần một image debug/JDK cùng namespace có quyền phù hợp hoặc một giải pháp thu đã được thiết kế sẵn.

Nếu một tệp được tạo ở `/tmp/incident.jfr` bên trong container, nó không tự xuất hiện ở host tại `/tmp/incident.jfr`. Ví dụ chuyển file qua quyền được cấp:

```bash
docker cp my-java-container:/tmp/incident.jfr ./incident.jfr
```

Với Kubernetes, workflow tương tự dùng `kubectl exec` và `kubectl cp` theo pod/container đúng; lệnh copy có thể phụ thuộc tiện ích `tar` hoặc chính sách RBAC. Trước khi sửa image, mount host volume hay attach tới pod production, kiểm tra quyền được cấp và quy định vận hành.

**Không cung cấp JFR control công khai qua Internet.** `jcmd` là công cụ local; nếu có giải pháp quản lý từ xa khác như JMX, cần xác thực, mã hóa kênh và phân quyền riêng.

## 12. Quy tắc vận hành production

Một recording có thể chứa thông tin nhạy cảm: tên class/method, tên thread, đường dẫn file, system properties, lệnh khởi động, endpoint hoặc fields custom event. Vì vậy:

- Chỉ vận hành với quyền có lý do rõ ràng; không chia sẻ file `.jfr` trên kho public.
- Đặt file vào thư mục được bảo vệ với quyền truy cập tối thiểu và chính sách giữ/xóa.
- Không ghi password, token, dữ liệu cá nhân hoặc khóa mật mã vào custom JFR events.
- Theo dõi dung lượng repository và các dump files riêng; `maxsize` không thay retention file đã xuất.
- Dùng `duration` cho capture ngắn; với ghi liên tục chọn `settings=default` và giới hạn `maxage/maxsize`.
- Tránh bật `path-to-gc-roots=true` trong mọi recording theo thói quen: tra đường đến GC roots có thể gây pause/chi phí lớn; chỉ bật khi điều tra memory leak có kế hoạch.
- Có thể tăng overhead khi bật event frequency cao, stack traces dày, nhiều phiên đồng thời hoặc I/O disk chậm.
- Nếu cần phản hồi nhanh từ application, so sánh CPU/latency/GC trước, trong và sau lúc thu.

**Sự kiện trong JFR không phải kết luận tự động.** Thấy GC pause lớn chưa chứng minh thiết kế heap sai; thấy allocation stack nhiều chưa chứng minh memory leak; cần đối chiếu hiện tượng, thời gian và metrics vận hành.

## 13. Cách xử lý các lỗi phổ biến

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng khắc phục |
| --- | --- | --- |
| `jcmd` không tồn tại | Runtime image không kèm JDK tool | Dùng JDK phù hợp/thiết bị debug được duyệt |
| `jcmd -l` không thấy tiến trình | Khác namespace/user hoặc attach bị chặn | Xác định PID đúng môi trường; kiểm tra user/permissions |
| Lệnh attach báo lỗi | JVM không hỗ trợ, `DisableAttachMechanism` hoặc OS policy | Tuân thủ policy; không bypass bảo mật |
| `JFR.start` không được nhận | JVM target không hỗ trợ diagnostic command này | `jcmd PID help`, kiểm tra JDK build |
| Start thành công nhưng không có file ngay | `duration` chưa hết hoặc chưa dump/stop | Đợi đủ thời hạn, hoặc chủ động `JFR.dump` |
| Dump báo không ghi file được | Path không writable, thư mục không có, đầy disk | Dùng filesystem writable của JVM target |
| Không có event mong muốn | Event bị disable, threshold cao hoặc ngoài cửa sổ | `JFR.check verbose=true` và xem settings |
| CPU samples ít | App idle, time window ngắn, sampling không phù hợp | Bắt lúc workload xảy ra, chọn profile |
| File .jfr rất lớn | Không có quota/retention hoặc dump nhiều lần | maxage/maxsize cho repository, policy xóa snapshots |
| Không biết recording còn chạy không | Nhầm dump với stop | Dùng `JFR.check` để xác minh |
| File trong pod không thấy trên laptop | Khác filesystem | Copy qua kênh được cấp quyền |
| Tool đọc không hiểu event mới | Khác phiên bản tool/file | Dùng JDK/JMC phù hợp phiên bản |

Một số lỗi chỉ xuất hiện sau khi chuyển vào container hoặc tăng bảo mật hệ điều hành, không phải do bản thân JFR. Không tắt cơ chế attach bảo vệ hoặc thay user đặc quyền tùy tiện chỉ để làm cho demo chạy.

## 14. Các tình huống và đáp án ngắn

**A.** Một ứng dụng đang chạy gặp CPU spike, cần thu 2 phút, ghi file khi hết thời hạn. Lệnh nào?

```bash
jcmd 12345 JFR.start name=cpu-spike settings=profile duration=120s filename=/var/tmp/cpu-spike.jfr
```

**B.** Có recording `rolling` đang chạy và bạn muốn lấy file mà không ngừng giám sát. Dùng `JFR.dump` hay `JFR.stop`? — **Dump**.

**C.** Sau `JFR.start duration=60s filename=...`, chưa thấy file khi mới 5 giây. Có phải thất bại? — **Không nhất thiết**; file có thể chỉ được ghi khi hoàn tất recording hoặc khi dump.

**D.** Gọi `JFR.dump` hai lần có nhận hai khoảng liên tiếp không trùng lặp không? — **Không bảo đảm**; các snapshots có thể chồng khoảng thời gian vì lịch sử recording vẫn được giữ.

**E.** `jfr summary` không thấy một loại event. Có thể chắc chắn event đó không xảy ra không? — **Không**; kiểm tra settings, threshold, retention và thời điểm.

**F.** Cùng một lệnh `jcmd` chạy trên host nhưng app ở container không thấy PID. Có chứng minh app không chạy không? — **Không**; có thể khác PID namespace.

**G.** Có cần restart Java 11 để bật JFR sau khi service đã chạy không? — **Không** nếu JVM hỗ trợ và attach được: dùng `jcmd PID JFR.start`.

**H.** `maxsize=256m` có dọn những file `.jfr` đã dump ra /var/tmp không? — **Không**; các file đã xuất cần retention riêng.

**I.** Có nên dùng `settings=profile` mãi trên production vì JFR “không có overhead” không? — **Không**; đo overhead và chọn config theo mục tiêu.

**J.** Một recording không có dữ liệu trước khi nó bắt đầu có thể dựng lại các stack CPU của ngày hôm qua không? — **Không**; chỉ recording đã thu từ trước mới có lịch sử tương ứng.

## 15. Checklist thực hiện hoàn chỉnh

- [ ] Chọn đúng PID/main class/JVM và kiểm tra `jcmd -l`.
- [ ] Có quyền attach được cấp; `jcmd PID help JFR.start` khả dụng.
- [ ] Đường dẫn file nằm ở filesystem target, writable, đủ dung lượng.
- [ ] Cấu hình đúng mục tiêu: `default` cho dài hạn, `profile` cho incident ngắn.
- [ ] Ghi trong khoảng thời gian **có workload/sự cố**.
- [ ] Dùng `JFR.check` xác minh ID, tên và trạng thái recording.
- [ ] Dùng `JFR.dump` khi cần snapshot mà vẫn muốn tiếp tục thu.
- [ ] Chỉ `JFR.stop` khi thật sự muốn kết thúc recording tương ứng.
- [ ] Xác nhận file `.jfr` đọc được bằng `jfr summary` hoặc JMC.
- [ ] Bảo vệ dữ liệu nhạy cảm, ghi nhận owner và retention.
- [ ] Dọn snapshots theo chính sách và không quên recording đang chạy.

## 16. Tóm tắt câu lệnh quan trọng

```bash
# Liệt kê JVM:
jcmd -l

# Kiểm tra hỗ trợ JFR:
jcmd 12345 help JFR.start

# Capture ngắn 60 giây:
jcmd 12345 JFR.start name=short settings=profile duration=60s filename=/var/tmp/short.jfr

# Capture dài hạn có retention:
jcmd 12345 JFR.start name=rolling settings=default disk=true maxage=2h maxsize=256m

# Xem recording:
jcmd 12345 JFR.check

# Xuất snapshot; recording VẪN CHẠY:
jcmd 12345 JFR.dump name=rolling filename=/var/tmp/rolling.jfr

# Kết thúc phiên:
jcmd 12345 JFR.stop name=rolling

# Đọc tệp đã xuất:
jfr summary /var/tmp/rolling.jfr
jfr print --events jdk.CPULoad /var/tmp/rolling.jfr
```

**Bốn thao tác cốt lõi:** `JFR.start` → `JFR.check` → `JFR.dump` → `JFR.stop`. Khi file quan trọng, **dump trước khi stop**, rồi xác minh kết quả được lưu.

## Tài liệu chính thức

- [Java SE 11 — Diagnostic Tools: JFR cho JVM đang chạy](https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html).
- [Java SE 11 — jcmd](https://docs.oracle.com/en/java/javase/11/tools/jcmd.html).
- [Java SE 11 — java launcher, JFR options](https://docs.oracle.com/en/java/javase/11/tools/java.html).
- [Java SE 11 — jdk.jfr.Recording API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html).
- [Java SE 11 — jdk.jfr.Configuration](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Configuration.html).
- [Java SE 11 — jdk.jfr.consumer.RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
- [Java SE 11 — jdk.jfr.Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html).
- [Java SE 25 — jcmd JFR.start, check, dump, stop](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html).
- [Java SE 21 — jfr command: print và summary](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- [OpenJDK JEP 328 — Flight Recorder tích hợp trong OpenJDK](https://openjdk.org/jeps/328).
