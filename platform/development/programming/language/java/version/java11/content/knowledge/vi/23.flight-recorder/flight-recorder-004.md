# Bắt đầu bản ghi JDK Flight Recorder bằng cấu hình launcher (Java 11+)

## 1. Bài toán: ghi nhận JVM ngay từ lúc ứng dụng khởi động

Khi một dịch vụ Java gặp vấn đề chỉ xảy ra lúc khởi động — thời gian warm-up dài, tranh chấp khóa, class loading, cấp phát nhiều đối tượng, garbage collection hoặc một thao tác chậm trước khi monitoring kịp kết nối — việc đợi ứng dụng chạy ổn định rồi mới bật profiler có thể làm mất dấu sự kiện cần quan sát.

**JDK Flight Recorder (JFR)** là cơ chế ghi lại **các sự kiện (events)** từ JVM, JDK và ứng dụng với chi phí tương đối thấp. JFR là một phần của OpenJDK/JDK hiện đại; nó được đưa vào OpenJDK ở **Java 11** (JEP 328). Cách khởi động bản ghi **ngay từ Java launcher** là truyền tùy chọn JVM:

~~~text
-XX:StartFlightRecording=tham_số=giá_trị,tham_số=giá_trị,...
~~~

Dấu hiệu cần nhớ: **tùy chọn phải được đưa cho JVM trước tên main class, trước `-jar` hoặc trước `-m`**. Đây là tùy chọn của **Java HotSpot JVM**, không phải tham số truyền vào `String[] args` của `main`.

Ví dụ tổng quát:

~~~bash
java -XX:StartFlightRecording=name=startup,settings=profile,duration=30s,filename=startup.jfr -jar app.jar
~~~

Lệnh trên **khởi động JVM cùng một recording** tên `startup`; dùng cấu hình sự kiện `profile`, tự ngừng sau khoảng 30 giây và ghi kết quả vào `startup.jfr`. Nó giả định `app.jar` là executable JAR hợp lệ, JVM tồn tại đủ lâu để recording chạy, và thư mục đích cho phép ghi. Nếu ứng dụng chấm dứt trước thời hạn mà không có `dumponexit`, **đừng mặc nhiên kỳ vọng sẽ có tệp hoàn chỉnh**.

### Tại sao nói “JDK Flight Recorder”, không phải profiler bên ngoài?

JFR tạo các bản ghi về hoạt động runtime (GC, thread, I/O, CPU samples, JVM events...) và các sự kiện tùy chỉnh được ứng dụng phát ra. Nó là **event recorder tích hợp trong JVM**, không cần tự thêm Java agent và không tự động là một **heap dump** hay “log toàn bộ method calls”.

Từ Java 11, JFR được cung cấp cho việc dùng production mà không cần dựa vào cơ chế bật commercial features cũ. **Không hướng dẫn dùng `-XX:+UnlockCommercialFeatures` hoặc `-XX:+FlightRecorder` như điều kiện bắt buộc để khởi động JFR.** Cách hiện hành là `-XX:StartFlightRecording`, `jcmd JFR.start` khi cần ghi sau lúc startup, hoặc API `jdk.jfr` cho ứng dụng chuyên biệt.

## 2. Quan hệ giữa launcher, JVM, recording và tệp `.jfr`

Một bản ghi JFR có **vòng đời riêng**: được cấu hình, có thể bị delay, đang chạy, dừng hoặc dump dữ liệu ra file. JVM có thể có nhiều recording độc lập. Khi truyền `-XX:StartFlightRecording`, launcher yêu cầu JVM **tạo/start recording khi quá trình khởi động diễn ra**, không cần code gọi `Recording.start()` trong ứng dụng.

~~~text
Terminal / Service manager / Container
               |
               | java -XX:StartFlightRecording=... -jar app.jar
               v
            Java launcher
               |
               v
            JVM startup
               |
               +--> JDK Flight Recorder
               |       |
               |       +--> cấu hình .jfc: những event nào được ghi?
               |       +--> buffer và repository tạm (khi cấu hình disk)
               |       +--> recording: tên, duration, delay, giới hạn dữ liệu
               |       +--> dump/stop --> startup.jfr (file nhị phân)
               |
               +--> main(...) của ứng dụng
                       |
                       +--> công việc JVM và application events
~~~

**Phân biệt hai file/thư mục:**

- **JFR repository:** nơi lưu các chunk dữ liệu **tạm** trong quá trình ghi, khi recording dùng disk.
- **`filename=...`:** tên file đầu ra `.jfr` khi recording được dump/stop theo chính sách. Đây **không phải** tên một log text được ghi nối thêm từng dòng trong suốt quá trình chạy.

Vì vậy khi dùng `dumponexit=true`, bạn thường không thấy file đích có nội dung đầy đủ **cho đến khi JVM thoát có kiểm soát**. Khi dùng `duration=...`, file được ghi lúc recording tự kết thúc; khi muốn lấy dữ liệu trong lúc recording còn chạy, dùng `jcmd <pid> JFR.dump ...`.

JFR file là **binary format**. Dùng `jfr summary`, `jfr print`, `jdk.jfr.consumer` hoặc công cụ như **JDK Mission Control** để đọc, không mở và chỉnh sửa như text log.

## 3. Cú pháp launcher chính xác

### 3.1. Đặt `-XX:StartFlightRecording` ở vị trí nào?

Với class trên classpath:

~~~bash
java -XX:StartFlightRecording=name=boot,settings=default,dumponexit=true,filename=boot.jfr -cp out com.example.Main
~~~

Với executable JAR:

~~~bash
java -XX:StartFlightRecording=name=boot,settings=default,dumponexit=true,filename=boot.jfr -jar app.jar
~~~

Với module có entry point:

~~~bash
java -XX:StartFlightRecording=name=boot,settings=default,dumponexit=true,filename=boot.jfr -m com.example.app/com.example.Main
~~~

Đây là **ba lệnh minh họa cho ba cách launch khác nhau**, không phải ba lệnh phải chạy nối tiếp. Chúng giả định class/JAR/module thực sự tồn tại.

### 3.2. Vị trí sai dễ gây nhầm lẫn

~~~bash
java -jar app.jar -XX:StartFlightRecording=name=boot
~~~

**Phản ví dụ:** tùy chọn nằm **sau `app.jar`**. Java launcher chuyển các token phía sau JAR thành **application arguments**, không coi chúng là JVM options. Kết quả: app có thể nhìn thấy chuỗi `-XX:StartFlightRecording=...` trong `args` nhưng JFR **không được kích hoạt theo ý định**.

Một điểm tương tự là khác biệt giữa `JAVA_OPTS`/`JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS` và đối số trực tiếp: các biến môi trường chỉ có hiệu lực nếu launcher hoặc wrapper nhận chúng đúng cách. Đặc biệt, **`JAVA_OPTS` không phải biến JVM tự động hiểu trong mọi môi trường**; nhiều shell scripts/wrappers tự đọc nó, nhiều ứng dụng thì không. Luôn kiểm lệnh Java cuối cùng thực chạy trong container/service manager.

### 3.3. Dấu `=` và dấu phẩy

Dạng được dùng trong ví dụ:

~~~text
-XX:StartFlightRecording=name=myrecording,settings=profile,delay=10s,duration=60s,filename=recordings/startup.jfr
~~~

- Một `-XX:StartFlightRecording=...` chứa nhiều cặp `key=value`.
- Các cặp được **phân cách bằng dấu phẩy**, không phải dấu cách.
- Đơn vị thời gian phổ biến: `s` (giây), `m` (phút), `h` (giờ), `d` (ngày) theo tham số.
- Dùng tên file/đường dẫn cụ thể và bảo đảm có quyền ghi.
- Tùy chọn `-XX:StartFlightRecording` có mặt từ Java 11 và tiếp tục được hỗ trợ; một số JDK mới cũng hiển thị dạng phân cách dấu hai chấm `-XX:StartFlightRecording:...`. Để viết mã/launcher phải chạy Java 11, dùng dạng `=` đã được tài liệu JDK 11 mô tả và kiểm thử.

**Đường dẫn có khoảng trắng:** quote **toàn bộ argument JVM** trong shell, không tách `filename=...` thành đối số riêng. Ví dụ trong PowerShell:

~~~powershell
java "-XX:StartFlightRecording=name=boot,filename=C:\Program Data\jfr\boot.jfr,dumponexit=true,settings=default" -jar app.jar
~~~

Lệnh này chỉ minh họa **cách quote**; cần tạo trước thư mục và cấp quyền tương ứng. Nếu đường dẫn có dấu phẩy, cần kiểm tra quy tắc escape/quoting của parser option JFR đang dùng, tránh mặc định đường dẫn nào cũng được phân tích đúng như một `filename`.

## 4. Các tham số quan trọng nhất của `StartFlightRecording`

| Tham số | Chức năng | Cách suy nghĩ khi chọn |
| --- | --- | --- |
| `name=<id>` | Đặt tên recording | Dễ quản lý bởi `jcmd JFR.check/dump/stop`, ví dụ `name=startup` |
| `settings=default` | Sử dụng cấu hình `default.jfc` | Ít overhead, phù hợp ghi liên tục hoặc baseline |
| `settings=profile` | Sử dụng cấu hình `profile.jfc` | Nhiều sự kiện/chi tiết hơn; dùng ngắn hạn để profiling |
| `settings=<file.jfc>` | Dùng event-settings file tùy biến | Khi cần kiểm soát event, threshold, stacktrace hoặc sample rate |
| `delay=10s` | Trì hoãn bắt đầu recording sau khi JVM khởi động | Tránh thời gian warm-up nếu mục tiêu nằm ở steady-state |
| `duration=60s` | Tự dừng recording sau khoảng thời gian | Phù hợp capturing một cửa sổ thời gian hữu hạn |
| `filename=path` | Đường dẫn file đầu ra lúc stop/dump | Phải có thư mục và quyền ghi; không tự là file log live |
| `dumponexit=true` | Dump khi JVM shutdown có kiểm soát | Phù hợp chương trình ngắn hoặc rolling recording dài hạn cần dữ liệu lúc thoát |
| `disk=true` | Ghi dữ liệu tạm xuống disk repository | Phù hợp recording dài và giới hạn retention trên disk |
| `maxage=1h` | Giữ tối đa dữ liệu có tuổi 1 giờ ở vùng disk | Hữu ích với continuous rolling capture, yêu cầu `disk=true` |
| `maxsize=128m` | Giới hạn kích thước dữ liệu được giữ trên disk | Chặn tăng dung lượng không giới hạn; yêu cầu `disk=true` |
| `path-to-gc-roots=true` | Thu thập đường dẫn tới GC roots tại cuối recording | Tốn kém; chỉ bật khi phân tích leak có chủ đích |

### `settings=default` và `settings=profile`

JDK chứa hai cấu hình được cung cấp sẵn dưới `<JAVA_HOME>/lib/jfr`:

- **`default.jfc`**: cân bằng dữ liệu và overhead, phù hợp recording chạy dài. Đây là lựa chọn mặc định khi không chỉ định `settings`.
- **`profile.jfc`**: bật nhiều sự kiện/thông tin phục vụ phân tích sâu hơn, chi phí thường cao hơn, nên giới hạn thời gian và kiểm tra trong môi trường tải thật.

**Không gán một tỷ lệ overhead duy nhất cho mọi ứng dụng.** JFR được thiết kế rất nhẹ, nhưng chi phí phụ thuộc workload, số events, stacktraces, allocation rate, cài đặt ngưỡng và số recording. Một custom JFC bật nhiều sự kiện có thể tốn tài nguyên đáng kể.

**Không sửa trực tiếp `default.jfc`/`profile.jfc` của JDK.** Nếu cần cấu hình riêng, tạo bản sao hoặc dùng công cụ hỗ trợ chỉnh cấu hình, lưu vào thư mục cấu hình ứng dụng rồi truyền `settings=/path/to/my.jfc`. Điều này giúp deployment tái lập khi nâng JDK.

### `duration`, `delay` và `dumponexit`

Ba tham số có ý nghĩa khác nhau:

~~~text
JVM start ─── delay=10s ─── Recording start ─── duration=30s ─── Stop + dump
     |
     └── nếu ứng dụng kết thúc sớm, recording có thể không kịp start/stop
~~~

- `delay` tính từ lúc launch tới thời điểm dự kiến bắt đầu recording.
- `duration` giới hạn **thời gian recording**, không phải tổng thời gian chạy ứng dụng.
- `dumponexit` là hành động khi JVM **thoát có kiểm soát** trong khi recording còn tồn tại; không bảo đảm xử lý `kill -9`, container bị OOM-kill, power failure hoặc crash nghiêm trọng.
- Với `duration=...` và `filename=...`, recording có thể hoàn tất/ghi file trước khi ứng dụng thoát. Với chương trình rất ngắn, nên dùng `dumponexit=true` nếu muốn chắc có một dump khi shutdown chuẩn.
- Với `delay`, nếu app kết thúc trước lúc delay hết, có thể chẳng có dữ liệu phù hợp để phân tích.

**Không nhầm `duration=60s` là “JVM sẽ dừng sau 60s”.** JVM/application tiếp tục chạy sau khi recording đã tự dừng nếu code còn hoạt động.

### `disk`, `maxage` và `maxsize`

Bản ghi chạy liên tục có thể tích lũy nhiều dữ liệu. Khi `disk=true`, JFR dùng repository để lưu các chunks tạm. `maxage` và `maxsize` giới hạn **lượng dữ liệu được giữ**, thông thường loại bỏ dữ liệu cũ khi vượt giới hạn để duy trì cửa sổ ghi gần nhất.

~~~bash
java -XX:StartFlightRecording=name=rolling,settings=default,disk=true,maxage=1h,maxsize=128m,dumponexit=true,filename=rolling.jfr -jar app.jar
~~~

**Minh họa production-like:** mỗi instance cần một đường dẫn riêng, phân quyền file và có chính sách retention/cleanup. Đây **không** là cơ chế đảm bảo file `rolling.jfr` luôn có trên disk khi JVM đang chạy; để lấy snapshot trước exit, dùng `JFR.dump`.

Lưu ý `maxsize` phải đáp ứng ràng buộc tối thiểu của chunk size/`maxchunksize` trong JVM thực tế. Nếu chọn quá nhỏ, launcher có thể từ chối. Không cần tùy chỉnh `-XX:FlightRecorderOptions` trong bài tập cơ bản; đây là nhóm tùy chọn bổ sung để quản lý buffer/repository, không thay thế `StartFlightRecording`.

## 5. Ba kịch bản khởi động recording phổ biến

### Kịch bản A — ghi một khoảng thời gian có giới hạn

Muốn ghi 60 giây, bắt đầu sau 20 giây warm-up:

~~~bash
java -XX:StartFlightRecording=name=profile-start,settings=profile,delay=20s,duration=60s,disk=true,filename=recordings/startup-60s.jfr -jar app.jar
~~~

Đây là **lệnh minh họa**: cần thư mục `recordings` tồn tại và app chạy ít nhất đến thời điểm recording kết thúc. Nếu dùng command line trong Windows, đổi slash/path theo cấu hình thực tế và quote chuỗi JVM option nếu đường dẫn có space.

Khi app vẫn chạy sau 80 giây, recording đã stop và file cuối đã được ghi, JVM **không bị tự dừng**. Nếu muốn snapshot sớm hơn, dùng `jcmd` để dump.

### Kịch bản B — ghi từ startup cho đến shutdown

Muốn quan sát cả vòng đời chương trình ngắn:

~~~bash
java -XX:StartFlightRecording=name=boot,settings=profile,disk=true,dumponexit=true,filename=recordings/boot.jfr -jar app.jar
~~~

Dùng `dumponexit=true` giúp lưu bản ghi khi JVM thoát bình thường/trong luồng shutdown có xử lý. Không nên dùng duy nhất tùy chọn này khi cần dữ liệu **dù tiến trình bị kill -9/crash**; hãy có giải pháp dump định kỳ, rolling repository và cơ chế thu thập file phù hợp.

### Kịch bản C — rolling recording chạy lâu, chỉ lấy khi gặp sự cố

~~~bash
java -XX:StartFlightRecording=name=rolling,settings=default,disk=true,maxage=2h,maxsize=256m -jar app.jar
~~~

Sau khi JVM chạy, lấy snapshot bằng:

~~~bash
jcmd <PID> JFR.check
jcmd <PID> JFR.dump name=rolling filename=recordings/incident.jfr
~~~

**`<PID>` trong hai lệnh trên là placeholder hướng dẫn**, thay bằng PID số của tiến trình Java thực tế; không copy nguyên `<PID>` vào shell vì nó có ý nghĩa đặc biệt trong nhiều shell. Lệnh `JFR.dump` lấy snapshot recording hiện tại **mà không nhất thiết dừng recording**. Kiểm tra output của `jcmd` để xác nhận đường dẫn file thực tế và quyền ghi.

Phải chạy `jcmd` trên **cùng máy/namespace tiến trình phù hợp** với JVM, với quyền attach thích hợp (thường cùng user). Container, sandbox, process isolation và policy JVM có thể giới hạn việc attach; không nên thiết kế quy trình bắt buộc attach từ bên ngoài nếu production không cho phép.

## 6. Ví dụ Java 11 chạy được để chứng minh launcher thật sự bắt đầu recording

Dưới đây là chương trình chạy hơn 3 giây, **không dùng API để tự start JFR**. Nó chỉ:

1. Kiểm tra hiện có recording object nào đã được launcher cấu hình thông qua `FlightRecorder.getFlightRecorder().getRecordings()`.
2. Tạo **8 application events** tên `demo.StartupPulse` bằng API `jdk.jfr.Event` của Java 11.
3. In hai dòng đơn giản để bạn có thể kiểm định chính xác, độc lập với log của JVM.

**Lưu ý:** `getRecordings()` có thể bao gồm recording **đang được lên lịch với delay**, chưa thực sự bắt đầu thu sự kiện. Dòng `recordingPresent=true` chứng minh có recording được đăng ký trong JVM, **không** chứng minh mọi sự kiện đã được ghi vào file; phải dùng `jfr summary/print` để xác minh.

### File `LauncherRecordingDemo.java`

~~~java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Label;
import jdk.jfr.Name;

public class LauncherRecordingDemo {
    @Name("demo.StartupPulse")
    @Label("Demo startup pulse")
    @Category({"Tutorial", "Startup"})
    static class StartupPulse extends Event {
        @Label("Step") int step;
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("recordingPresent="
                + !FlightRecorder.getFlightRecorder().getRecordings().isEmpty());
        for (int i = 1; i <= 8; i++) {
            StartupPulse pulse = new StartupPulse();
            pulse.step = i;
            pulse.begin();
            Thread.sleep(450);
            pulse.commit();
        }
        System.out.println("pulsesEmitted=8");
    }
}
~~~

**Code này biên dịch bằng Java 11.** `@Name` đặt tên event dùng trong `jfr print --events ...`; `@Label` và `@Category` cung cấp metadata phục vụ phân tích. `pulse.begin()`/`pulse.commit()` xác định khoảng thời gian của event. Mỗi vòng lặp đợi khoảng 450 ms, tổng 8 vòng lặp là khoảng 3,6 giây cộng overhead runtime.

Không in secret, token hoặc nội dung dữ liệu người dùng trong custom event. Các event trong bản ghi có thể chứa thông tin chẩn đoán nhạy cảm, ví dụ thread names, file paths, method names và stacktraces.

### Biên dịch

~~~bash
javac --release 11 LauncherRecordingDemo.java
~~~

Dùng JDK 11 trở lên có module `jdk.jfr`. Với các JDK thông thường, module này sẵn có và nằm trong tập module được cung cấp cho ứng dụng. Nếu chạy với custom `jlink` runtime image, cần bảo đảm module JFR và công cụ phân tích được đưa vào image thích hợp; không suy rằng mọi tối giản image có `jfr` binary.

### Chạy thử 1 — tự dump khi JVM thoát

~~~bash
java -XX:StartFlightRecording=name=boot,settings=profile,disk=true,dumponexit=true,filename=boot.jfr LauncherRecordingDemo
~~~

Khi JVM thoát có kiểm soát, kiểm:

~~~bash
jfr summary boot.jfr
jfr print --events demo.StartupPulse boot.jfr
~~~

**Hai dòng stdout do chương trình Java in, đã kiểm chứng với JDK 24 sau khi dùng `javac --release 11`:**

~~~text
recordingPresent=true
pulsesEmitted=8
~~~

**JFR launcher cũng có thể in log `[info][jfr,startup]`**, bao gồm PID, tên recording và hướng dẫn dùng `jcmd`. Các dòng đó **không nằm trong hai dòng stdout do ứng dụng chủ động in**; chúng có thể thay đổi theo phiên bản JDK, OS và cấu hình logging.

Trong lần test, file `boot.jfr` được tạo thành công và `jfr summary` liệt kê **`demo.StartupPulse` với 8 sự kiện**. Đây là kết quả được quan sát trong môi trường test **không phải bảo đảm số lượng event luôn bằng 8 nếu đổi cấu hình/timeout**.

### Chạy thử 2 — delay và duration

~~~bash
java -XX:StartFlightRecording=name=timed,settings=profile,disk=true,delay=1s,duration=2s,filename=timed.jfr LauncherRecordingDemo
~~~

Chương trình vẫn in:

~~~text
recordingPresent=true
pulsesEmitted=8
~~~

Nhưng vì recording chỉ bắt đầu **sau khoảng 1 giây** và kéo dài **khoảng 2 giây**, file `timed.jfr` **không nhất thiết chứa cả tám** `StartupPulse`. Trong môi trường kiểm thử JDK 24, `jfr summary timed.jfr` tìm thấy **4 sự kiện** `demo.StartupPulse`. Đây là **kết quả quan sát, không phải con số bắt buộc**: compiler, JVM, scheduler, thời gian khởi tạo JFR và thời điểm commit event có thể làm kết quả khác nhau.

~~~bash
jfr summary timed.jfr
jfr print --events demo.StartupPulse timed.jfr
~~~

**Tiêu chí PASS:** file `timed.jfr` tồn tại sau thời hạn ghi, `jfr summary` đọc được, và trong môi trường test không quá tải có các sự kiện tương ứng thời gian recording đã bật. Không assert đúng 4 events cho mọi lần chạy trên mọi JDK.

### Đọc phần nội dung của một event

`jfr print --events demo.StartupPulse timed.jfr` có thể trả định dạng tương tự (đã rút gọn, không phải output đầy đủ):

~~~text
demo.StartupPulse {
  startTime = ...
  step = 4
  eventThread = "main" (...)
  stackTrace = [...]
}
~~~

Các timestamp, Java thread IDs và stack trace line numbers có thể khác. Với câu hỏi “launcher có bật recording không?”, **tệp có thể đọc được và sự kiện xuất hiện** là bằng chứng tốt hơn chỉ nhìn vào flag được truyền.

## 7. Đọc và đánh giá bản ghi sau khi tạo file

JDK có công cụ **`jfr`** để xử lý offline recording file:

| Lệnh | Chức năng | Khi dùng |
| --- | --- | --- |
| `jfr summary recording.jfr` | Thống kê số lượng events và kích thước dữ liệu | Xác minh file hợp lệ, xem danh sách event types |
| `jfr print recording.jfr` | In tất cả event data dạng text | Chỉ dùng khi file nhỏ; output có thể rất dài |
| `jfr print --events demo.StartupPulse recording.jfr` | Lọc event theo tên | Xem custom events cụ thể |
| `jfr print --events jdk.CPULoad recording.jfr` | Lọc một event type của JVM nếu file có | Phân tích CPU load với sự kiện đã được bật |
| `jfr metadata recording.jfr` | Xem thông tin event types | Khi chưa biết fields/metadata của event |
| JDK Mission Control (JMC) | Phân tích/visualize event timeline, GC, threads, hotspots | Khi cần phân tích chuyên sâu |

**`jfr` là công cụ đọc file, không tự start một recording trong JVM đang chạy**. Để bắt đầu recording khi JVM chưa chạy, dùng **launcher** như đề bài. Với JVM đang chạy, dùng **`jcmd JFR.start`** nếu có quyền. Đừng nhầm tên hai công cụ.

`jfr summary` không bảo đảm mọi loại event đều có dữ liệu: điều đó phụ thuộc `settings`, thời gian recording, sampling thresholds và tải ứng dụng. Ví dụ một sự kiện GC có thể hoàn toàn không xuất hiện nếu app không có GC trong khoảng đã ghi.

### File không có trong thư mục hiện tại?

Hãy kiểm:

1. Command thực sự gọi `java -XX:StartFlightRecording=...` **trước** `-jar`/main class.
2. JVM đã chạy đủ lâu so với `delay` và `duration`.
3. `dumponexit=true` đã có nếu dựa vào việc dump khi shutdown.
4. Đường dẫn `filename` là tương đối so với **working directory của process**, không phải thư mục source file hoặc JAR.
5. Directory tồn tại, JVM user có quyền ghi và còn dung lượng.
6. JVM có thể ghi repository hoặc bị policy về disk quota/permissions giới hạn.
7. Không có nhiều tiến trình cùng ghi đè một tên file, và file đã được dump vào nơi khác.
8. File thật sự là `.jfr` hợp lệ: dùng `jfr summary` để kiểm.

Không có file ở đường dẫn dự kiến **không tự chứng minh JFR không ghi bất kỳ event nào**; có thể recording còn đang chạy trong repository tạm, hoặc `filename`/working directory khác. Cần phân biệt recording active với file đã được dump.

## 8. Kiểm recording đang chạy bằng `jcmd`

Sau khi một JVM được launch với recording `name=rolling`:

~~~bash
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=rolling filename=incident.jfr
~~~

**`12345` là PID ví dụ**, phải thay bằng PID Java đúng. `JFR.check` giúp thấy recording đang chạy hoặc đang được lên lịch cùng thông tin cấu hình; `JFR.dump` ghi snapshot từ recording hiện có. `JFR.dump` **không phải `JFR.stop`**: dump thường không tự dừng recording đang chạy.

Khi muốn dừng recording có tên:

~~~bash
jcmd 12345 JFR.stop name=rolling
~~~

Và khi JVM đã chạy **không có launcher JFR** mà bạn muốn bắt đầu mới:

~~~bash
jcmd 12345 JFR.start name=on-demand settings=profile duration=60s filename=on-demand.jfr
~~~

Các lệnh là **mẫu vận hành**, cần PID có thật, quyền attach và thư mục ghi phù hợp. Cần quan sát text kết quả của `jcmd` để biết tên/id recording thật sự; không tự giả định `name=...` trong command khác với tên đang chạy mà không kiểm.

### Launcher recording và jcmd recording khác gì?

| Tình huống | Cách làm | Đặc điểm |
| --- | --- | --- |
| Cần dữ liệu ngay từ quá trình startup | `-XX:StartFlightRecording=...` | Không đợi attach, hoạt động ngay theo launch config |
| JVM đã chạy và cần chẩn đoán mới | `jcmd <pid> JFR.start ...` | Có thể bỏ lỡ sự kiện trước lúc attach |
| Cần xác nhận recording còn tồn tại | `jcmd <pid> JFR.check` | Kiểm trạng thái |
| Cần snapshot mà không dừng recording | `jcmd <pid> JFR.dump ...` | Tạo file để phân tích |
| Muốn dừng một recording | `jcmd <pid> JFR.stop name=...` | Kết thúc recording theo command |
| Đã có file và cần xem thống kê | `jfr summary file.jfr` | Không cần attach JVM |

Tùy JVM/cấu hình, attach có thể bị tắt hoặc giới hạn bởi OS/container. Không coi `jcmd` là cơ chế có thể chạy từ bất kỳ máy nào đến mọi tiến trình Java. Với JFR launcher, bạn có thể cấu hình trước việc ghi dữ liệu ngay cả khi attach từ bên ngoài không được phép.

## 9. Chọn cấu hình khi vận hành thật

### Phân tích ngắn: ưu tiên `profile` với duration

Khi điều tra một đoạn ứng dụng cụ thể:

~~~bash
java -XX:StartFlightRecording=name=profile,settings=profile,delay=10s,duration=2m,filename=recordings/profile.jfr -jar app.jar
~~~

Dùng một cửa sổ thời gian vừa đủ để không tạo file quá lớn. Nếu chủ đề chỉ xuất hiện ở startup, đừng thêm `delay` làm bỏ lỡ sự kiện; thay bằng bắt đầu ngay hoặc kiểm kế hoạch start dựa trên tình huống.

### Quan sát dài hạn: ưu tiên `default`, giới hạn dữ liệu

~~~bash
java -XX:StartFlightRecording=name=service,settings=default,disk=true,maxage=2h,maxsize=256m -jar app.jar
~~~

Các giới hạn này thuộc **recording repository**, không phải chính sách retention của kho lưu trữ sự cố của công ty. Nếu có nhu cầu điều tra incident hồi cứu, cần định nghĩa cách lấy dump (theo trigger, lịch, operator) và xóa/luân chuyển file cuối theo thời hạn.

**Chi phí phụ thuộc workload.** `default` thường được thiết kế để có overhead thấp và có thể dùng liên tục, nhưng không bảo đảm luôn dưới một phần trăm cố định; phải thử dưới tải đại diện.

### Custom `.jfc`

Khi cần tùy chỉnh event/threshold:

~~~bash
java -XX:StartFlightRecording=name=custom,settings=conf/app-jfr.jfc,duration=90s,filename=recordings/custom.jfr -jar app.jar
~~~

Ví dụ giả định `conf/app-jfr.jfc` **đã tồn tại và có định dạng hợp lệ**. Nên tạo custom file từ `default.jfc` hoặc `profile.jfc` theo cấu hình được kiểm soát, không sửa file template của JDK. Một số tính năng `jfr configure` của bản JDK mới không có cùng CLI trên mọi Java 11 deployment; khi yêu cầu Java 11, dùng một `.jfc` tương thích và kiểm trước ở runtime mục tiêu.

**Không bật tất cả event types và mọi stack trace mặc định trong production.** Sự kiện có chu kỳ cao, allocation sampling quá dày hoặc dữ liệu nhạy cảm có thể tăng overhead và file size.

## 10. Bảo mật dữ liệu và quản lý file JFR

JFR không nên được coi là “chỉ có chỉ số vô hại”. Một recording có thể chứa class/package names, stack traces, đường dẫn file, thread names, system properties, thông tin môi trường và **payload của custom events**. Tùy loại sự kiện và policy thu thập, dữ liệu đủ nhạy cảm để lộ cấu trúc hệ thống hoặc chi tiết yêu cầu.

Nguyên tắc vận hành:

- Chỉ ghi vào thư mục có **quyền truy cập hạn chế**, không đặt file `.jfr` dưới web root/public static folder.
- Chỉ cấp quyền `jcmd`/diagnostic attach cho nhân sự/process được phép, không dùng quyền rộng chỉ vì cần xem CPU.
- Không đưa token, mật khẩu, cookie hoặc dữ liệu khách hàng vào fields của custom JFR events.
- Phân biệt **repository tạm** và **final dump file**; dọn cả hai theo policy và yêu cầu pháp lý.
- Kiểm **dung lượng disk**, quota, số recording đang hoạt động và số file tạo ra.
- Mỗi instance/pod nên có output path/name riêng, tránh nhiều JVM viết cùng `recording.jfr` khi chia sẻ volume.
- Nếu container có ephemeral filesystem, phải có kế hoạch copy/export file trước khi pod bị xóa.
- Không phụ thuộc hoàn toàn `dumponexit=true` cho bất kỳ tình huống kill đột ngột; dữ liệu có thể không kịp dump.
- Khi chia sẻ file để điều tra, sử dụng hệ thống trao đổi file được phê duyệt và đặt hạn sử dụng.

### Đặt đường dẫn an toàn

Trong shell:

~~~bash
mkdir -p recordings
java -XX:StartFlightRecording=name=boot,settings=default,dumponexit=true,filename=recordings/boot.jfr -jar app.jar
~~~

Lệnh `mkdir` tạo thư mục. `java` chạy với quyền của process hiện tại; nếu user không thể ghi vào thư mục hoặc volume bị mount read-only, JVM có thể báo lỗi khi khởi tạo/dump. Với container hoặc service manager, working directory thường khác shell development; dùng path tuyệt đối đã cấp quyền nếu cần tính dự đoán.

Nếu chạy nhiều replicas, đặt đường dẫn có instance ID hoặc PID/timestamp theo một quy ước được triển khai/test trên phiên bản JDK thực tế; không dùng một file duy nhất trên shared volume mà mong các bản ghi tự ghép vào nhau.

## 11. Những nhầm lẫn thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Đặt `-XX:StartFlightRecording` sau `-jar app.jar` | JVM không nhận là launcher flag | Đặt trước `-jar` hoặc class |
| Tưởng `-XX:StartFlightRecording` là code Java | Không biết debug từ đâu | Tách JVM launch args khỏi application args |
| Đặt `duration=5s`, app thoát sau 1s, không dùng `dumponexit` | Có thể không có file cuối | Đảm bảo app sống đủ lâu hoặc dùng `dumponexit` |
| Đặt `delay=10s` để phân tích lỗi xảy ra 3s đầu | Bỏ lỡ startup event | Ghi ngay hoặc chỉnh delay |
| Nghĩ `duration=30s` sẽ dừng JVM | App vẫn chạy | Duration chỉ dừng recording |
| Nghĩ `filename` là file log đang ghi realtime | Tìm file sai thời điểm | File dump/stop khác repository tạm |
| Dùng `profile` mãi trên service không đo overhead | Có thể tốn CPU/IO hơn cần thiết | `default` cho continuous, profile ngắn hạn |
| Không giới hạn `disk` retention | Repository có thể tăng lớn | `maxage`/`maxsize` và disk quota |
| Cấu hình `maxage`/`maxsize` nhưng `disk=false` | Giới hạn không có hiệu lực mong đợi | Bật `disk=true` khi cần rolling disk |
| Dùng `dumponexit` làm bảo đảm trong kill -9 | Crash/kill có thể không dump | Dùng snapshot/rolling/collector |
| Tưởng `JFR.dump` luôn dừng recording | Dễ tưởng sau dump không còn ghi | Phân biệt dump và stop |
| Tưởng `jfr summary` bắt đầu recording | Không bật JFR trong app | Dùng launcher hoặc `jcmd JFR.start` |
| Tưởng `recordingPresent=true` nghĩa mọi custom events được ghi | Recording có thể delayed/filters | Kiểm file bằng `jfr summary/print` |
| So sánh đúng 4 custom events sau `delay=1s` | Scheduler và timing khác | Assert sự kiện thuộc khoảng thu thập, không hardcode số |
| Dựa vào `JAVA_OPTS` trên mọi môi trường | Wrapper có thể không đọc biến đó | Kiểm lệnh launch thực tế |
| Không tạo thư mục output/không cấp quyền | Không có file JFR hoặc launcher/dump lỗi | Tạo và phân quyền trước |
| Lưu file JFR vào thư mục public | Lộ đường dẫn/stacktrace/custom data | Giới hạn truy cập, retention |
| Copy cờ `-XX:+UnlockCommercialFeatures` từ hướng dẫn cũ | Lỗi thời/không cần cho Java 11+ | Dùng `-XX:StartFlightRecording` hiện hành |
| Chỉ test `java -version` | Không xác nhận recording chạy | Chạy app có flag và kiểm file `.jfr` |
| Dùng một path cho nhiều container | File bị ghi đè/đụng nhau | Path/name riêng cho mỗi instance |

## 12. Quy trình chẩn đoán khi không tạo được recording

### Trường hợp A — không thấy bất kỳ ghi nhận JFR nào

1. Xác minh trình chạy thật là JVM có JFR và flags được truyền đúng vị trí.
2. Xem startup logs JVM nếu có; JFR thường ghi các message thông tin khi được bật.
3. Với app còn sống, chạy `jcmd PID JFR.check` để kiểm recording object.
4. Nếu không có recording, kiểm lại string `-XX:StartFlightRecording=...`, các dấu phẩy, `settings` và quyền user.
5. Đừng thêm hàng loạt old flags không còn cần thiết rồi chạy thử không kiểm soát.

### Trường hợp B — có recording nhưng file chưa có

1. Recording có còn **RUNNING**/scheduled không? File có thể chỉ xuất hiện khi stop hoặc dump.
2. Dùng `jcmd PID JFR.dump name=<ten> filename=<path>` nếu cần snapshot ngay.
3. Kiểm relative path từ working directory và quyền ghi.
4. Kiểm JVM đã tới hết duration, chưa bị kill đột ngột.
5. Kiểm file name có bị process khác ghi đè/di chuyển không.

### Trường hợp C — file có nhưng thiếu dữ liệu cần thiết

1. `settings=default` có bật đúng event type? Nếu không, dùng custom JFC hoặc `profile` có kiểm soát.
2. Có `delay` khiến event xảy ra trước khi recording start không?
3. Duration quá ngắn hoặc JFR sampling/threshold bỏ qua event?
4. Có event được commit thật và thuộc khoảng thời gian thu thập không?
5. `maxage`/`maxsize` có làm dữ liệu cũ bị loại khỏi rolling window không?
6. Dữ liệu có ở file khác do dump nhầm recording name không?

### Trường hợp D — file quá lớn hoặc overhead cao

1. Rút ngắn `duration` cho chẩn đoán chuyên sâu.
2. Dùng `settings=default` cho recording thường trực.
3. Điều chỉnh JFC để chỉ bật sự kiện thực sự cần.
4. Đặt `disk=true,maxage=...,maxsize=...` khi ghi dài.
5. Đo overhead thực tế trên workload đại diện.
6. Bảo đảm không lưu nhiều JFR dumps vô hạn trên volume.

**Không coi một lỗi JFR là lý do giảm kiểm soát an ninh của JVM/OS hoặc mở quyền ghi toàn filesystem.**

## 13. Checklist kiểm thử launcher recording trước khi dùng production

- [ ] **JDK/runtime:** xác định Java 11+ và provider/JVM thực tế hỗ trợ JFR.
- [ ] **Vị trí flag:** `-XX:StartFlightRecording=...` nằm trước main class/`-jar`/`-m`.
- [ ] **Cấu hình:** `name` dễ nhận diện, `settings=default`/`profile` theo nhu cầu.
- [ ] **Thời gian:** `delay` không làm lỡ lỗi cần chẩn đoán, `duration` phù hợp thời gian app chạy.
- [ ] **Dump:** có `filename` và chính sách `dumponexit` hoặc `duration`/`jcmd JFR.dump` thích hợp.
- [ ] **Dung lượng:** giới hạn repository với `disk=true,maxage,maxsize` khi recording chạy dài.
- [ ] **Directory:** path tồn tại, process có quyền ghi, đúng working directory/container mount.
- [ ] **File hợp lệ:** `jfr summary file.jfr` chạy thành công.
- [ ] **Sự kiện:** `jfr print --events ...` thấy đúng dữ liệu cần, không chỉ thấy file rỗng.
- [ ] **Trạng thái:** `jcmd PID JFR.check` xác nhận recording nếu app còn chạy và attach được.
- [ ] **Runtime behavior:** app không bị dừng bởi `duration`, chỉ recording dừng.
- [ ] **Đo overhead:** kiểm CPU/IO/storage dưới tải thật, đặc biệt với `profile` hoặc custom JFC.
- [ ] **Bảo mật:** hạn chế người đọc `.jfr`, không ghi secrets vào custom events.
- [ ] **Failure modes:** xác định kế hoạch nếu app crash, bị kill, pod restart hoặc file system đầy.
- [ ] **Tương thích:** ví dụ Java được biên dịch bằng `--release 11` và flag được kiểm trên JDK deployment, không dùng tùy chọn chỉ có trong JDK mới.
- [ ] **Thu thập sự cố:** có cách lấy bản dump từ từng instance mà không đè file của nhau.

**Tóm tắt:** Để bắt đầu JDK Flight Recorder ngay lúc khởi động Java 11+, đặt **`-XX:StartFlightRecording=...` trước `-jar`/main class**. Dùng `settings` chọn dữ liệu, `delay/duration` kiểm thời điểm và thời lượng, `filename/dumponexit` quyết định cách xuất file, `disk/maxage/maxsize` giới hạn lượng dữ liệu được giữ. **Kiểm chứng bằng file `.jfr` và event data thực tế**, không chỉ bằng tên flag hoặc một dòng log startup.

## Tài liệu chính thức và hiện hành

- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): tích hợp JFR vào OpenJDK 11.
- [Oracle Java SE 11 — The java Command](https://docs.oracle.com/en/java/javase/11/tools/java.html): cú pháp `-XX:StartFlightRecording`, `settings`, `delay`, `duration`, `filename`, `dumponexit` và các tùy chọn liên quan.
- [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): các cờ JFR còn được duy trì trên JDK hiện hành và bổ sung mới theo release.
- [Oracle Java SE 25 — Troubleshooting Guide, Flight Recorder](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshooting-guide.pdf): startup recordings, continuous recordings và `jcmd`.
- [Oracle Java SE 11 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html): JFR, `jcmd` và các diagnostic commands.
- [Oracle Java SE 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`.
- [Oracle Java SE 25 — The jfr Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `jfr summary`, `jfr print`, `jfr metadata`.
- [Oracle Java SE 11 — `jdk.jfr` API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html): `Event` và recording APIs trong JDK 11.
- [Oracle Java SE 24 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html): `default.jfc`, `profile.jfc` và custom configurations.

Kiến thức trong bài dựa trên **API và launcher options vẫn được sử dụng từ Java 11 đến các JDK hiện hành**. Không dùng các cờ thương mại/JFR legacy, không trình bày các lựa chọn chỉ có ở phiên bản mới như thể Java 11 đã hỗ trợ, và không coi JFR thay thế cơ chế logging/tracing/alerting phù hợp của hệ thống.