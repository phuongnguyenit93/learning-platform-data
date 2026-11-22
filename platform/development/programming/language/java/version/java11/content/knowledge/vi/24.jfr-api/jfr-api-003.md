# JFR API — start, stop, dump, copy và close của Recording (Java 11+)

## 1. Tổng quan: vì sao phải quản lý đúng vòng đời?

**JDK Flight Recorder (JFR)** là hệ thống thu thập sự kiện tích hợp trong JVM để chẩn đoán performance, GC, thread, allocation, I/O và các sự kiện ứng dụng. Từ Java 11, JFR là thành phần chuẩn của OpenJDK (JEP 328); Java cung cấp API **`jdk.jfr.Recording`** để điều khiển bản ghi ngay trong code mà không cần thao tác thủ công qua launcher.

Một recording có thể chạy trong nhiều phút hoặc nhiều giờ và bạn có thể **xuất các file `.jfr` tại những thời điểm khác nhau**. Điều quan trọng là phân biệt:

- **Recording object:** đối tượng JVM có state, configuration, buffers/repository và vòng đời.
- **File `.jfr`:** artifact nhị phân được tạo bằng `dump(Path)` hoặc khi một destination được xử lý tại thời điểm stop.
- **Events:** dữ liệu được recording thu theo các loại sự kiện đã bật, thời gian và threshold cụ thể.

Ví dụ một service giám sát liên tục nhưng phải lấy snapshot ngay khi có incident:

~~~text
new Recording --> start() --> RUNNING
                      |
                      +--> phát event A
                      |
                      +--> copy(true) -> COPY STOPPED -> copy.dump(snapshot.jfr)
                      |                           |
                      |                           +--> copy.close()
                      |
                      +--> phát event B -> original.dump(live.jfr)
                      |                        |
                      |                        +--> original vẫn RUNNING
                      |
                      +--> phát event C -> stop() -> STOPPED
                                              |
                                          dump(final.jfr)
                                              |
                                            close()
                                              |
                                            CLOSED
~~~

Năm phương thức của bài làm **năm việc khác nhau**:

| Phương thức | Ý nghĩa chính | Lưu ý |
| --- | --- | --- |
| `start()` | Bắt đầu thu events | Không thể khởi động lại một recording đã STOPPED |
| `stop()` | Ngừng thu events | Nếu không cấu hình destination, dữ liệu có thể còn để dump |
| `dump(Path)` | Xuất dữ liệu ra file | Gọi trên RUNNING **không tự dừng** recording |
| `copy(boolean stop)` | Tạo một recording mới từ recording gốc | Tham số `stop` chỉ quyết định trạng thái bản sao |
| `close()` | Giải phóng dữ liệu/tài nguyên | **Không phải** lệnh xuất file mặc định |

**Thông điệp chính:** `dump` không phải `stop`; `copy(true)` không dừng bản gốc; `close` làm mất cơ hội dump dữ liệu chưa xuất. Đây là cơ chế Java 11+ **vẫn còn áp dụng** trên JDK hiện đại.

## 2. Các API liên quan và phần việc của chúng

| API | Package | Công dụng |
| --- | --- | --- |
| `Recording` | `jdk.jfr` | Tạo/cấu hình/start/stop/dump/copy/close |
| `RecordingState` | `jdk.jfr` | Phản ánh state hiện tại |
| `Configuration` | `jdk.jfr` | Nạp `default`, `profile` hoặc cấu hình `.jfc` |
| `Event` | `jdk.jfr` | Lớp cơ sở của custom events |
| `EventSettings` | `jdk.jfr` | Enable, threshold và stacktrace event |
| `@Name`, `@Label` | `jdk.jfr` | Đặt tên và nhãn event |
| `FlightRecorder` | `jdk.jfr` | API cấp JVM cho recorder và danh sách recordings |
| `RecordingFile` | `jdk.jfr.consumer` | Đọc dữ liệu trong file `.jfr` |
| `RecordedEvent` | `jdk.jfr.consumer` | Một event đã ghi, có type, fields, timestamp |

Không nhầm `Recording.copy(boolean)` với `Files.copy(...)`: `copy(boolean)` trả về một **Recording mới**, chưa phải một file. Nếu muốn lưu snapshot, caller phải gọi `dump(Path)` trên bản sao rồi đóng nó.

### Cấu hình Recording cơ bản

~~~java
Configuration config = Configuration.getConfiguration("default");
try (Recording recording = new Recording(config)) {
    recording.setName("sample");
    recording.setToDisk(true);
    recording.start();
    // Thực hiện thao tác cần quan sát.
    recording.stop();
    recording.dump(Path.of("sample.jfr"));
}
~~~

Đây là **mã minh họa trong method** có imports và xử lý checked exceptions phù hợp, không phải toàn bộ chương trình. `try-with-resources` gọi `close()` khi block kết thúc. `new Recording()` cũng hợp lệ nhưng **không bật sẵn mọi event type**; nên chỉ định `Configuration` hoặc `enable(...)` theo nhu cầu.

JFR `default.jfc` và `profile.jfc` được JDK cung cấp:

- `default`: nhóm events được lựa chọn, thường phù hợp ghi dài hạn với overhead tương đối thấp.
- `profile`: thu thêm thông tin để phân tích sâu, có thể tăng overhead.

Không hứa một tỷ lệ overhead chung: còn tùy ứng dụng, provider, sampling, stacktraces và cấu hình event.

## 3. State machine: NEW → RUNNING → STOPPED → CLOSED

`recording.getState()` trả về enum `RecordingState`.

| Trạng thái | Ý nghĩa | Thao tác thường dùng |
| --- | --- | --- |
| **`NEW`** | Vừa tạo, chưa bắt đầu | Cấu hình, `start()` hoặc `scheduleStart(Duration)` |
| **`DELAYED`** | Đã lên lịch bắt đầu sau delay | Đợi thời điểm ghi hoặc `start()` theo hợp đồng |
| **`RUNNING`** | Đang thu events | `dump`, `copy`, `stop` hoặc `close` |
| **`STOPPED`** | Không còn thu, có thể giữ data disk | `dump` khi còn dữ liệu, sau đó `close` |
| **`CLOSED`** | Đã giải phóng tài nguyên/dữ liệu | Không mở lại, không dump được |

~~~text
                  scheduleStart(delay)
                 /                    \
NEW --------> DELAYED ---------------> RUNNING
 |              |                        |
 +---start()----+                        +--- dump(path) ---> RUNNING
                                         |
                                         +--- copy(true) ---> copy STOPPED
                                         |                     gốc RUNNING
                                         |
                                         +--- stop() ----------> STOPPED
                                         |                           |
                                         |                           +--- dump(path)
                                         |                           +--- close()
                                         |
                                         +--- close() --------------> CLOSED
~~~

**Đặc biệt:** nếu `setDestination(path)` đã được cấu hình, `stop()` sẽ ghi ra destination và **tự close sau khi ghi thành công**. Vì thế code nhìn thấy `CLOSED` ngay sau stop, không phải luôn `STOPPED`.

### Không restart một Recording đã dừng

~~~java
recording.start();  // NEW -> RUNNING
recording.stop();   // RUNNING -> STOPPED nếu không gắn destination
recording.start();  // Sai: IllegalStateException
~~~

Đây là **phản ví dụ**: lệnh cuối không hợp lệ. `stop()` trên recording chưa start hoặc đã stop cũng có thể phát sinh `IllegalStateException`. Không coi `stop` là thao tác được lặp vô hạn mà không kiểm state.

`scheduleStart(Duration.ofSeconds(5))` đưa recording ở `NEW` sang `DELAYED`. Event xảy ra trước lúc recording thực sự start sẽ không tự được ghi về sau. `DELAYED` không tương đương `RUNNING` khi gọi dump.

## 4. `start()`: thiết lập trước, ghi sau

Javadoc Java SE 11 khuyến nghị cấu hình **recording options và event settings trước `start()`** để thu dữ liệu với settings nhất quán và tối ưu áp dụng cấu hình.

~~~java
Recording r = new Recording(Configuration.getConfiguration("default"));
r.setName("incident-trace");
r.setToDisk(true);
r.enable("jdk.CPULoad");
r.start();
~~~

Đây là đoạn minh họa, phải được đặt trong vòng đời có `close` và xử lý exceptions. `setName` giúp phân biệt recordings trong công cụ quản lý; `setToDisk(true)` dùng disk repository để lưu dữ liệu phục vụ dump.

### Bật custom event đúng cách

~~~java
@Name("lesson.Step")
@Label("Lesson step")
static final class Step extends Event {
    @Label("Index") int index;
}
~~~

Đây là **class snippet** đặt trong một lớp Java bao ngoài. Để bật và lưu cả event rất ngắn:

~~~java
recording.enable(Step.class)
         .withThreshold(Duration.ZERO)
         .withoutStackTrace();
~~~

`withThreshold(Duration.ZERO)` cho phép thu sự kiện ngắn; `withoutStackTrace` không ghi stack trace cho event khi không cần. **`Event.commit()` không tự bảo đảm event đã xuất hiện trong file**, vì còn phụ thuộc settings, thời điểm recording đang chạy, threshold, retention và disk buffers.

### API nội bộ khác launcher

Dùng `Recording.start()` trong code có nghĩa recording bắt đầu **khi chương trình chạy tới dòng đó**. Nếu cần những events xuất hiện **trước `main`**, dùng launcher option `-XX:StartFlightRecording=...`. Nếu JVM đã chạy và operator có quyền attach, `jcmd PID JFR.start` là một cơ chế khác. Không đồng nhất vòng đời Recording object trong code với một command-line process.

## 5. `dump(Path)`: tạo file mà recording có thể tiếp tục chạy

`Recording.dump(Path destination)` ghi dữ liệu recording ra file `.jfr`. Nó **không tự chuyển một recording RUNNING thành STOPPED**.

~~~java
Path snapshotPath = Path.of("recordings/live.jfr");
// Đã tạo thư mục và cấp quyền ghi cho ứng dụng.
recording.dump(snapshotPath);
System.out.println(recording.getState()); // RUNNING, nếu trước dump là RUNNING.
~~~

Đây là **mã minh họa** trong chương trình đã tạo recording hợp lệ. Điểm khác biệt:

- `dump` khi `RUNNING`: xuất file, **tiếp tục thu**.
- `dump` khi `STOPPED` **và có dữ liệu disk repository**: vẫn có thể xuất file, trước `close`.
- `dump` khi `NEW`, `DELAYED`, `CLOSED` hoặc khi `STOPPED` nhưng không có data disk thích hợp: có thể ném `IOException`.
- `dump` có thể ném `IOException` vì path không tồn tại/không writable, disk full, lỗi I/O hoặc không đủ dữ liệu phù hợp.
- `dump` không giải phóng recording object; cần quản lý `stop/close` riêng.

**JFR repository khác final dump file.** Với `setToDisk(true)`, dữ liệu được flush tới repository JFR; `dump(Path)` tạo file nhị phân riêng dùng để đọc/chia sẻ theo chính sách. Đừng xem `filename` như một file log text append từng dòng.

### Chọn đường dẫn và xử lý sự cố

`Path.of("recordings/live.jfr")` là đường dẫn tương đối với **working directory của process**, không phải nhất thiết thư mục mã nguồn. Hãy tạo parent directory, cấp quyền ghi, kiểm dung lượng và đặt tên file riêng cho mỗi instance. Trong container, volume có thể read-only hoặc bị xóa khi pod dừng. Không ghi `.jfr` vào web-root/public directory.

Khi cần snapshot để chẩn đoán, **không cần `stop()` trước `dump`**, vì stop sẽ làm gián đoạn thu thập.

## 6. `copy(boolean stop)`: nhân recording object, không nhân file

Phương thức chuẩn là **`Recording.copy(boolean stop)`**. Nó tạo một recording mới, với **ID và tên mới**. `stop` là boolean quyết định liệu **bản sao** có dừng ngay hay không.

| Từ recording gốc RUNNING | Copy sau khi tạo | Gốc sau khi tạo |
| --- | --- | --- |
| `recording.copy(true)` | `STOPPED` | `RUNNING` |
| `recording.copy(false)` | `RUNNING` | `RUNNING` |

**Mẫu dùng đúng cho snapshot:**

~~~java
try (Recording snapshot = recording.copy(true)) {
    snapshot.dump(Path.of("recordings/incident.jfr"));
}
// Bản sao đã close, recording gốc vẫn có thể RUNNING.
~~~

Mẫu trên giả định recording gốc đang RUNNING với dữ liệu disk khả dụng. `copy(true)` chỉ tạo bản sao STOPPED; **không tự tạo `incident.jfr`**. `snapshot.dump(...)` mới ghi file. Bản sao có vòng đời riêng nên cần `close`, thường qua `try-with-resources`.

**Nếu dùng `copy(false)`:**

~~~java
try (Recording branch = recording.copy(false)) {
    // branch RUNNING; gốc cũng tiếp tục RUNNING.
    branch.stop();
    branch.dump(Path.of("recordings/branch.jfr"));
}
~~~

Đây là **mã minh họa**, cần chủ động stop/dump/close nhánh. Không tạo nhiều `copy(false)` rồi quên đóng: chúng có thể cùng thu event stream của JVM và giữ tài nguyên. `copy(false)` là một bản ghi tiếp tục chạy, **không phải snapshot đã kết thúc**.

### Sao chép không đồng nghĩa với isolation

Hai Recording có thể chứa cùng event xảy ra trong JVM nếu cả hai bật loại event đó trong cùng khoảng thời gian. Một bản sao không tự chỉ giữ dữ liệu của một user/tenant. Nếu cần correlation, dùng event fields không nhạy cảm; **không lưu token, mật khẩu hoặc payload riêng tư vào JFR**.

Sau copy, Javadoc cho phép giới hạn lượng dữ liệu bản sao bằng `setMaxAge(Duration)`/`setMaxSize(long)` theo nhu cầu. Không dựa vào chi tiết implementation của chunk repository; nếu cần **file snapshot bất biến**, hãy gọi `dump` và kiểm tệp.

## 7. `stop()`: ngừng thu nhưng chưa chắc giải phóng data

`Recording.stop()` chuyển một recording đang RUNNING sang **STOPPED** trong luồng không có destination tự động, và recording đó không thể start lại. Phương thức trả boolean, ví dụ đã test `stopReturned=true`.

~~~java
recording.stop();
System.out.println(recording.getState()); // STOPPED trong nhánh thông thường.
recording.dump(Path.of("recordings/final.jfr"));
~~~

Đoạn minh họa giả định recording có `setToDisk(true)` và file path hợp lệ. Sau stop, recording vẫn có thể **giữ dữ liệu đã ghi trong disk repository** để dump cho tới khi close.

**Sai lầm thường gặp:** gọi `stop()` rồi `close()` rồi mới `dump()`. Sau close, dữ liệu do recording object giữ đã được giải phóng; việc cố dump sau đó sẽ không thành công.

### `setDestination(Path)` làm thay đổi state sau stop

~~~java
try (Recording r = new Recording()) {
    r.setToDisk(true);
    r.setDestination(Path.of("auto.jfr"));
    r.start();
    // ...
    r.stop(); // Ghi auto.jfr và tự close nếu ghi thành công.
    System.out.println(r.getState()); // CLOSED.
}
~~~

Đây là đoạn minh họa có file path writable. **`setDestination` là chính sách cho lúc stop**, không phải `dump` ngay lập tức. Theo Java SE 11/25 Javadoc, khi có destination và việc ghi file thành công, recording **được tự động đóng**. Không gọi `r.dump(...)` sau stop trong trường hợp này: có thể đã CLOSED.

## 8. `close()`: giải phóng recording, không phải lệnh dump

`Recording` triển khai `Closeable` và `AutoCloseable`. Hãy ưu tiên:

~~~java
try (Recording r = new Recording(Configuration.getConfiguration("default"))) {
    r.setToDisk(true);
    r.start();
    // ...
    r.stop();
    r.dump(Path.of("final.jfr"));
} // tự gọi close()
~~~

Sau `close()` thành công:

- `getState()` là `CLOSED`.
- Recording không còn cho phép `start/stop/dump` trong vòng đời cũ.
- Các dữ liệu/buffers/repository resources do Recording giữ được giải phóng.
- **File đã dump thành công trước close vẫn tồn tại** như artifact độc lập.
- Nếu `close` được gọi lúc RUNNING, Recording bị đóng mà **không bảo đảm tự xuất file**.

Muốn ghi một phiên mới, tạo **Recording mới**. Không cố “mở lại” object đã đóng.

### Sơ đồ thứ tự an toàn

~~~text
Muốn dump cuối thủ công:
  NEW -> start -> RUNNING -> stop -> STOPPED -> dump -> close

Muốn lấy snapshot mà vẫn ghi:
  NEW -> start -> RUNNING -> dump -> RUNNING -> stop -> dump -> close

Muốn bản sao có snapshot:
  original RUNNING -> copy(true) -> copy STOPPED -> copy.dump -> copy.close
                   \-> original vẫn RUNNING

Muốn stop tự ghi file:
  setDestination(file) -> start -> stop -> ghi file -> auto-close (nếu thành công)
~~~

**Khi nào nên dùng mẫu nào?** Với chương trình ngắn, `stop -> dump -> close` rõ ràng. Với service liên tục, `dump` ngay lúc RUNNING hoặc `copy(true) -> dump -> close` là lựa chọn để không ngắt recording gốc. Khi yêu cầu tự ghi file một lần lúc dừng, `setDestination` có thể giảm thao tác nhưng **thay đổi lifecycle**.

## 9. Chương trình Java 11 hoàn chỉnh đã kiểm thử

Ví dụ sau tạo event tùy chỉnh `lesson.Step`, ghi events ở ba thời điểm và xuất **ba tệp**: `snapshot.jfr`, `live.jfr`, `final.jfr`. Chương trình **đã biên dịch thành công với `javac --release 11` và chạy trên JDK 24**, không cần thư viện ngoài.

Tạo file **RecordingLifecycleDemo.java**:

~~~java
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.RecordingState;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.stream.Collectors;

public class RecordingLifecycleDemo {
    @Name("lesson.Step")
    @Label("Lesson step")
    static final class Step extends Event {
        @Label("Index") int index;
    }

    private static void emit(int index) {
        Step e = new Step();
        e.index = index;
        e.commit();
    }

    private static String steps(Path path) throws Exception {
        List<RecordedEvent> events = RecordingFile.readAllEvents(path);
        return events.stream()
                .filter(e -> e.getEventType().getName().equals("lesson.Step"))
                .map(e -> Integer.toString(e.getInt("index")))
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) throws Exception {
        Path dir = Path.of(args[0]);
        Files.createDirectories(dir);
        Path snap = dir.resolve("snapshot.jfr");
        Path live = dir.resolve("live.jfr");
        Path ended = dir.resolve("final.jfr");

        Recording rec = new Recording(Configuration.getConfiguration("default"));
        try (Recording recording = rec) {
            recording.setName("primary");
            recording.setToDisk(true);
            recording.enable(Step.class).withThreshold(Duration.ZERO).withoutStackTrace();
            System.out.println("created=" + recording.getState());
            recording.start();
            System.out.println("started=" + recording.getState());

            emit(1);
            try (Recording copy = recording.copy(true)) {
                System.out.println("copyState=" + copy.getState());
                System.out.println("originalAfterCopy=" + recording.getState());
                copy.dump(snap);
                System.out.println("snapshotSteps=" + steps(snap));
            }

            emit(2);
            recording.dump(live);
            System.out.println("afterLiveDump=" + recording.getState());
            System.out.println("liveSteps=" + steps(live));

            emit(3);
            System.out.println("stopReturned=" + recording.stop());
            System.out.println("stopped=" + recording.getState());
            recording.dump(ended);
            System.out.println("finalSteps=" + steps(ended));
        }
        System.out.println("closed=" + rec.getState());
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac --release 11 RecordingLifecycleDemo.java
java RecordingLifecycleDemo recordings
~~~

Thư mục `recordings` được chương trình tạo nếu chưa tồn tại; khi chạy lặp lại nên dùng thư mục thử riêng để tránh đọc nhầm file cũ. Mã sử dụng `Path.of`, `jdk.jfr` và `jdk.jfr.consumer`, đều có trong Java 11.

**Stdout chính xác đã kiểm chứng:**

~~~text
created=NEW
started=RUNNING
copyState=STOPPED
originalAfterCopy=RUNNING
snapshotSteps=1
afterLiveDump=RUNNING
liveSteps=1,2
stopReturned=true
stopped=STOPPED
finalSteps=1,2,3
closed=CLOSED
~~~

**Diễn giải:**

1. `created=NEW`: object mới, chưa ghi.
2. `started=RUNNING`: start đã thành công.
3. `copyState=STOPPED`: copy(true) dừng bản sao.
4. `originalAfterCopy=RUNNING`: gốc không bị stop bởi copy.
5. `snapshotSteps=1`: file snapshot có event phát trước copy.
6. `afterLiveDump=RUNNING`: dump gốc khi RUNNING không dừng nó.
7. `liveSteps=1,2`: file live có hai events.
8. `stopReturned=true`, `stopped=STOPPED`: gốc được dừng nhưng chưa close.
9. `finalSteps=1,2,3`: file final có ba events, được dump **sau stop**.
10. `closed=CLOSED`: `try-with-resources` giải phóng Recording.

**Đối chiếu file bằng công cụ JDK:**

~~~bash
jfr summary recordings/snapshot.jfr
jfr summary recordings/live.jfr
jfr summary recordings/final.jfr
jfr print --events lesson.Step recordings/final.jfr
~~~

Phép thử đã tạo ba file JFR hợp lệ; `jfr summary` đếm số custom events `lesson.Step` lần lượt **1 / 2 / 3**. Kích thước files, thread IDs, timestamps và các event types khác không ổn định giữa môi trường — **không viết assertion dùng các giá trị đó làm hằng số**.

**Vì sao đọc file trong ví dụ dùng `RecordingFile.readAllEvents`?** File test rất nhỏ và dễ kiểm. Javadoc khuyến cáo **không dùng readAllEvents cho file lớn**, vì nó tải toàn bộ events vào danh sách trong RAM; production nên dùng streaming.

## 10. Các trường hợp biên đã chạy thử

Để xác nhận các semantics không được chương trình chính thể hiện, một chương trình `RecordingEdgesDemo` độc lập đã được chạy với target Java 11:

### Bản sao `copy(false)` tiếp tục RUNNING

~~~java
try (Recording copy = recording.copy(false)) {
    System.out.println(copy.getState());     // RUNNING khi gốc đang RUNNING.
    // Có thể tiếp tục phát custom events.
    copy.stop();
    copy.dump(Path.of("copyfalse.jfr"));
}
// Gốc vẫn RUNNING.
~~~

Đây là **mã minh họa trong context đã tạo recording gốc**. Trong test, bản sao ở `RUNNING` ngay sau copy, thành `STOPPED` sau stop; đóng bản sao **không làm dừng** recording gốc.

### Đóng recording đang chạy

~~~java
Recording r = new Recording();
r.start();
r.close();
System.out.println(r.getState()); // CLOSED.
~~~

Mã minh họa. Thực tế test cho thấy sau close ở RUNNING, state là `CLOSED` và `dump(...)` tiếp theo bị từ chối (phát sinh `IOException`).

### `setDestination` tự xuất file và close khi stop

~~~java
try (Recording r = new Recording()) {
    r.setToDisk(true);
    r.setDestination(Path.of("auto.jfr"));
    r.start();
    // ...
    r.stop();
    System.out.println(r.getState()); // CLOSED sau khi auto-dump thành công.
}
~~~

Đây là mã minh họa với đường dẫn writable, và cần event đã bật nếu muốn chứa data. Test xác nhận `auto.jfr` tồn tại và state thành `CLOSED`.

### `setToDisk(false)` rồi stop không tương đương khả năng dump

~~~java
try (Recording r = new Recording()) {
    r.setToDisk(false);
    r.start();
    // ...
    r.stop();
    r.dump(Path.of("memoryStopped.jfr")); // IOException trong test.
}
~~~

Đây là **phản ví dụ** cho trường hợp disk policy sai nhu cầu. Nếu muốn dump **sau stop**, hãy dùng `setToDisk(true)` và dump trước close.

**Output đã kiểm chứng của chương trình biên** (khác chương trình chính):

~~~text
copyFalse=RUNNING
originalStill=RUNNING
copyStopped=STOPPED
originalAfterCloneClose=RUNNING
closedWhileRunning=CLOSED
closedDumpAllowed=false
destStopReturned=true
destStopState=CLOSED
destFileExists=true
memoryStoppedDump=false
~~~

## 11. Đọc JFR files và giữ tài nguyên có giới hạn

Với file lớn, dùng streaming `RecordingFile`:

~~~java
try (RecordingFile file = new RecordingFile(Path.of("recordings/final.jfr"))) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        if ("lesson.Step".equals(event.getEventType().getName())) {
            System.out.println(event.getInt("index"));
        }
    }
}
~~~

Đây là **mã minh họa** cần imports và xử lý `IOException`. Cách đọc tuần tự phù hợp hơn so với load toàn bộ file vào RAM. Javadoc cũng khuyến nghị chỉ đọc **JFR files từ nguồn tin cậy**.

**Bảo mật:** file JFR có thể chứa class names, stack traces, file paths, system metadata và custom fields. Không cho phép HTTP client bất kỳ chỉ định raw output path rồi gọi `recording.dump(Path)` vì nguy cơ ghi file tùy ý. Cần authorization, giới hạn thư mục, kiểm tên file, disk quota, retention và phân quyền chỉ người cần thiết.

**Multi-instance:** không để nhiều JVM cùng ghi một path trên shared volume. Với containers, tính cả khả năng thư mục lưu tạm biến mất khi pod bị xóa. `setDumpOnExit(true)` không bảo đảm dump trên `kill -9`/OOM kill hoặc power failure, nên nếu cần forensic retention có thể chọn snapshots định kỳ.

## 12. Test matrix cho start/stop/dump/copy/close

| Bài kiểm tra | Điều kiện PASS |
| --- | --- |
| `new Recording(...)` | State `NEW` |
| `start()` | State `RUNNING` |
| `dump` lúc RUNNING | Có file hợp lệ, state vẫn RUNNING |
| `copy(true)` lúc gốc RUNNING | Copy STOPPED, gốc RUNNING |
| `copy(false)` lúc gốc RUNNING | Copy RUNNING, gốc RUNNING |
| Close copy | Gốc không bị close |
| `stop()` không destination | State STOPPED, không start lại |
| Dump sau stop với disk | File chứa events trước stop |
| Stop khi `setDestination` đã cấu hình | File được tạo và Recording auto-CLOSED sau thành công |
| Close khi RUNNING | State CLOSED, không dump nữa |
| Stop memory-only rồi dump | Không được xem như kịch bản disk-backed; test bắt IOException |
| `RecordingFile` | Parse file, thấy event name/fields đúng |
| Path không writable | Ghi nhận IOException và vẫn cleanup object |
| Không bật event | Không suy rằng API dump hỏng chỉ vì không có event type mong đợi |

Dùng `getState()` và nội dung file để QA, **không chỉ kiểm không có exception**. Việc `Event.commit()` được gọi không chứng minh event có trong file nếu threshold/state/timing/retention không phù hợp.

## 13. Những nhầm lẫn phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`dump()` tự stop recording.” | Dump trên RUNNING không dừng nó. |
| “`copy(true)` stop bản gốc.” | `true` chỉ stop bản sao. |
| “`copy(false)` đã chụp xong nên bỏ mặc.” | Nó tiếp tục RUNNING, cần stop/close. |
| “`copy` là sao chép file.” | Trả một Recording mới, cần dump để có file. |
| “`close()` lưu data ra file.” | Close giải phóng; dump trước nếu muốn lưu. |
| “Sau stop lúc nào cũng là STOPPED.” | `setDestination` có thể tự CLOSED. |
| “Sau stop dù memory-only vẫn dump được.” | Cần data disk hoặc dump khi vẫn RUNNING theo hợp đồng. |
| “Một Recording có thể start/stop nhiều chu kỳ.” | STOPPED không restart; dùng Recording mới. |
| “`new Recording()` mặc định bật mọi event.” | Cần configuration/enable phù hợp. |
| “Đọc mọi JFR events vào RAM luôn ổn.” | File lớn nên dùng `RecordingFile` streaming. |
| “JFR file chỉ có số liệu vô hại.” | Có thể có dữ liệu nhạy cảm, phân quyền phù hợp. |
| “Một copy tự tách events theo user.” | Recording theo JVM event types, không tự cô lập user. |

## 14. Checklist vận hành

- [ ] Dùng JDK 11+ có module `jdk.jfr`, có quyền truy cập repository.
- [ ] Cấu hình `Configuration`/`enable(...)`/threshold trước `start()`.
- [ ] Dùng `setToDisk(true)` nếu muốn dump **sau `stop()`**.
- [ ] Đặt tên/retention/dung lượng phù hợp với ứng dụng.
- [ ] `start()` khi state cho phép và có một owner quản lý lifecycle.
- [ ] `dump(Path)` khi RUNNING để lấy snapshot không gián đoạn.
- [ ] `copy(true)` rồi dump+close nếu muốn snapshot độc lập.
- [ ] `copy(false)` thì nhớ stop/dump/close bản sao.
- [ ] `stop()` một lần, không cố restart một recording đã stop.
- [ ] `setDestination` khác `dump`; sau stop có thể auto-close.
- [ ] `close()` được gọi, tốt nhất qua try-with-resources.
- [ ] Không dump sau close; không giả định file tồn tại nếu chưa xuất thành công.
- [ ] Kiểm file JFR và events thực tế qua `jfr summary` hoặc `RecordingFile`.
- [ ] Đọc file lớn tuần tự, giới hạn RAM/IO và retention.
- [ ] Bảo vệ nội dung JFR và output paths, không ghi secrets vào events.

**Tóm lại:** `start` mở recording; `dump` xuất file; `copy` nhân một Recording mới có vòng đời riêng; `stop` ngừng thu; `close` giải phóng dữ liệu và tài nguyên. Muốn dùng an toàn trên Java 11+, phải tách biệt **trạng thái**, **chính sách ghi disk**, **file đầu ra** và **quyền sở hữu Recording objects**.

## Tài liệu chính thức còn áp dụng

- [Oracle Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): `start()`, `stop()`, `dump(Path)`, `copy(boolean)`, `close()`, `setDestination` và `setToDisk`.
- [Oracle Java SE 25 — Recording](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html): những API và semantics còn được hỗ trợ.
- [Oracle Java SE 11 — RecordingState](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/RecordingState.html): trạng thái vòng đời.
- [Oracle Java SE 11 — Configuration](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Configuration.html): `default`/`profile`.
- [Oracle Java SE 11 — Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html): tạo event tùy chỉnh.
- [Oracle Java SE 11 — EventSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): threshold và stack trace.
- [Oracle Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc file JFR, readAllEvents và streaming.
- [Oracle Java SE 25 — RecordingFile](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): consumer API còn áp dụng.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR trong OpenJDK 11.
- [Oracle Java SE 25 — jfr tool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): summary, print, metadata.
- [Oracle Java SE 25 — jcmd tool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): quản lý JFR từ bên ngoài JVM.

Bài chỉ sử dụng **API Java 11+ hiện hành**, không dựa vào cờ commercial/JFR legacy và không giả định những khả năng chỉ có trong các JDK mới là sẵn có từ Java 11. Ví dụ được biên dịch và thực thi với target Java 11 trên JDK 24.