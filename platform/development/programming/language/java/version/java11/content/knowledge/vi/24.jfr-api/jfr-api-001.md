# JFR API: Recording và điều khiển bản ghi bằng chương trình (Java 11 trở lên)

## 1. Java Flight Recorder giải quyết bài toán gì?

Trong một dịch vụ Java chạy lâu, một số vấn đề rất khó tái hiện ở môi trường phát triển: GC tạm dừng bất thường, CPU tăng đột ngột, lock contention, I/O chậm, allocation tăng hoặc một nghiệp vụ chỉ thỉnh thoảng thất bại. Việc thêm `System.out.println` cho từng dòng vừa tạo nhiễu vừa có thể làm thay đổi hành vi cần quan sát.

**Java Flight Recorder (JFR)** là cơ chế thu thập event chẩn đoán có sẵn trong các bản OpenJDK/Oracle JDK hiện đại. Nó ghi một dòng thời gian gồm những **event** có timestamp, duration, thread, stack trace và metadata khi event type hỗ trợ. File lưu kết quả thông thường có đuôi **`.jfr`**.

Ở Java 11, package **`jdk.jfr`** trong module **`jdk.jfr`** cung cấp public API để ứng dụng tự:

- tạo một bản ghi (`Recording`) và chọn cấu hình;
- bật hoặc tắt những event types cần quan sát;
- điều khiển bắt đầu ngay, lên lịch bắt đầu, tự dừng sau một khoảng thời gian;
- giới hạn thời gian và dung lượng dữ liệu giữ lại;
- xuất file `.jfr` trong lúc recording còn chạy hoặc sau khi đã dừng;
- tạo bản sao/snapshot để phân tích mà không cần dừng bản ghi gốc;
- đọc lại một file JFR bằng `jdk.jfr.consumer.RecordingFile`.

**Đề bài chính của chương này là `Recording` và vòng đời điều khiển recording qua Java code**, không phải triển khai một profiler khác hoặc hướng dẫn các công cụ JFR không tồn tại trong Java 11.

Một ví dụ ngắn:

```java
import jdk.jfr.Configuration;
import jdk.jfr.Recording;
import java.nio.file.Path;

try (Recording recording =
        new Recording(Configuration.getConfiguration("default"))) {
    recording.start();

    // Thực hiện đoạn công việc muốn quan sát.
    doBusinessWork();

    recording.stop();
    recording.dump(Path.of("workload.jfr"));
}
```

Đây là **đoạn mã trong phương thức** với `doBusinessWork()` là hàm của ứng dụng. Phần bên dưới có chương trình **độc lập, biên dịch và chạy được với `javac --release 11`**, tự tạo custom events, xuất nhiều recordings và đọc lại dữ liệu.

## 2. Phân biệt Recording, Event, EventSettings và file .jfr

| Thành phần | Java API | Vai trò |
| --- | --- | --- |
| **Recording** | `jdk.jfr.Recording` | Đại diện một bản ghi có cấu hình, trạng thái và dữ liệu riêng |
| **JFR runtime** | `jdk.jfr.FlightRecorder` | Dịch vụ quản lý Flight Recorder trong JVM |
| **Event** | `jdk.jfr.Event` | Một loại sự kiện được code của JVM hoặc ứng dụng phát ra |
| **Event type** | `jdk.jfr.EventType` | Metadata của một loại event: tên, fields, settings... |
| **Event settings** | `jdk.jfr.EventSettings` | Bật/tắt event, ngưỡng duration, stack trace, chu kỳ sampling/period |
| **Configuration** | `jdk.jfr.Configuration` | Tập settings có thể nạp từ cấu hình có sẵn hoặc file `.jfc` |
| **RecordedEvent** | `jdk.jfr.consumer.RecordedEvent` | Một event đã được ghi trong dữ liệu JFR |
| **RecordingFile** | `jdk.jfr.consumer.RecordingFile` | Đọc một file `.jfr` trên đĩa |
| **RecordingState** | `jdk.jfr.RecordingState` | Trạng thái vòng đời `NEW`, `DELAYED`, `RUNNING`, `STOPPED`, `CLOSED` |

Ví dụ, khi gọi:

```java
Recording recording = new Recording(
        Configuration.getConfiguration("default"));
recording.enable("jdk.CPULoad");
recording.start();
```

thì `recording` **không phải một `Event`**. Nó là bản ghi sẽ thu những event được bật theo settings. Các event JVM như `jdk.CPULoad` xuất hiện theo hoạt động và thời điểm sampling của runtime, không tự động sinh đúng một event khi `start()` được gọi.

Một JVM có thể có **nhiều `Recording` đồng thời** với các cấu hình khác nhau. JFR runtime là hạ tầng dùng chung; mỗi `Recording` có lựa chọn event, retention và vòng đời riêng. Không được suy diễn rằng `new Recording()` tạo một JVM mới hoặc rằng một event class chỉ thuộc một recording.

## 3. Module, yêu cầu môi trường và cách kiểm tra khả dụng

### 3.1. JFR API trên Java 11

Imports:

```java
import jdk.jfr.Recording;
import jdk.jfr.RecordingState;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.EventSettings;
import jdk.jfr.FlightRecorder;
import jdk.jfr.consumer.RecordingFile;
import jdk.jfr.consumer.RecordedEvent;
```

Để biên dịch chương trình trên **Java 11**, có thể chỉ rõ module:

```bash
javac --release 11 --add-modules jdk.jfr JfrRecordingDemo.java
java --add-modules jdk.jfr JfrRecordingDemo
```

Nếu ứng dụng chạy trong **named module**, `module-info.java` cần khai báo:

```java
module com.example.diagnostics {
    requires jdk.jfr;
}
```

`module-info.java` trên là **đoạn minh họa** cho module có tên; chương trình ví dụ ở phần 11 dùng **classpath thông thường** nên không cần file module descriptor.

`jdk.jfr` là module chuẩn được đưa vào JDK hỗ trợ Flight Recorder. Tuy nhiên, **một custom runtime image do `jlink` tạo hoặc provider/JVM không hỗ trợ JFR có thể thiếu khả năng tương ứng**. Vì vậy kiểm tra:

```java
if (!FlightRecorder.isAvailable()) {
    System.out.println("JFR is not available on this JVM");
    return;
}
```

`FlightRecorder.isAvailable()` là kiểm tra khả năng **hiện tại** của JVM; theo Javadoc, kết quả có thể thay đổi và không nên được cache như một chân lý vĩnh viễn. Nó **không chứng minh** ứng dụng đã có quyền ghi tới thư mục export hay recording sẽ tạo ra những event được kỳ vọng.

### 3.2. Không dùng sự khác biệt lịch sử như một bước bắt buộc

Một số tài liệu cũ nói phải bật các flag thương mại/experimental cho Flight Recorder. Đối với bài học **Java 11 trở lên**, không dùng các hướng dẫn legacy đó. Hãy xác minh JVM và module `jdk.jfr` thực tế được triển khai, rồi dùng public API.

Khi thao tác ngoài tiến trình, có thể dùng `jcmd` hoặc `jfr` CLI nếu JDK/công cụ có sẵn; nhưng bài này tập trung vào **điều khiển trực tiếp bên trong chương trình**, không cần shell profiler để bắt đầu.

## 4. Vòng đời chuẩn của một Recording

`Recording` triển khai `AutoCloseable`, nên hỗ trợ `try-with-resources`.

Các state:

```text
             new Recording(...)
                       |
                     NEW
                /              \
      start()  /                \ scheduleStart(delay)
              v                  v
           RUNNING             DELAYED
              |                  |
              |            hết delay / start()
              |                  v
              |                RUNNING
              |                  |
              +------------------+
                       |
              stop() / hết duration
                       v
                    STOPPED
                       |
                  close()
                       v
                    CLOSED
```

**Lưu ý đặc biệt:** Nếu `setDestination(path)` đã được cấu hình, `stop()` sẽ xuất dữ liệu tới destination và **tự đóng recording khi việc ghi thành công**. Khi ấy có thể quan sát trực tiếp chuyển từ `RUNNING` tới `CLOSED`, thay vì dừng ở `STOPPED` để chờ `dump`.

| State | Ý nghĩa | Hành động thường làm |
| --- | --- | --- |
| `NEW` | Vừa tạo, chưa bắt đầu | `setName`, `enable`, `setMaxAge`, `setMaxSize`, `setDestination`, `setDuration` |
| `DELAYED` | Đã gọi `scheduleStart`; chờ thời điểm bắt đầu | Quan sát state, chờ recording tự chuyển `RUNNING` |
| `RUNNING` | Đang thu data theo settings | Đọc trạng thái, `dump` snapshot, `copy(true)`, `stop` |
| `STOPPED` | Đã ngừng thu, dữ liệu còn được giữ để xuất | `dump`, phân tích snapshot, `close` |
| `CLOSED` | Đã giải phóng tài nguyên của Recording | Không restart; tạo `Recording` mới cho phiên mới |

### 4.1. `start()` không giống `new Recording()`

`new Recording(...)` tạo một đối tượng trong **`NEW`**. Chưa bắt đầu ghi. Với recording cần start ngay:

```java
Recording recording = new Recording();
System.out.println(recording.getState()); // NEW
recording.start();
System.out.println(recording.getState()); // RUNNING
```

Đoạn trên **không gọi `close()`** để đơn giản hóa diễn giải, nhưng trong code thực hãy bao đối tượng bằng `try-with-resources` hoặc `finally`. Không để recording không được đóng vì có thể giữ các chunk/resources lâu hơn dự kiến.

### 4.2. Không thể `start()` lại một Recording đã dừng

`Recording` không phải một nút toggle start/stop lặp vô hạn:

```text
NEW -> RUNNING -> STOPPED -> CLOSED
                  |
                  +-- không restart cùng Recording instance
```

Muốn ghi phiên thứ hai, tạo một `Recording` mới. Nếu code vô tình gọi `start()` khi đã chạy/đóng, hoặc `stop()` ngoài trạng thái hợp lệ, API có thể ném `IllegalStateException`.

**Không** chọn “cứ gọi `stop()` thật nhiều lần cho chắc”; xử lý state và lỗi đúng cách. `getState()` hữu ích để hiển thị, nhưng với nhiều threads điều khiển đồng thời, giữa lần kiểm tra và thao tác state có thể thay đổi. Cần **một nơi quản lý lifecycle** để tránh race.

### 4.3. `close()` không có nghĩa “lưu file cho tôi”

`close()` giải phóng dữ liệu/tài nguyên Recording. Khi chưa gọi `dump` và chưa đặt destination, gọi `close()` có thể khiến dữ liệu không còn khả dụng để xuất sau này.

**Thứ tự phù hợp khi muốn giữ file:**

```text
Recording.start()
    → thực hiện workload
Recording.stop()
Recording.dump(destination)
Recording.close()
```

Nếu đặt `setDestination` trước, JFR có thể tự ghi file và đóng ngay khi stop, nên không cần gọi `dump` lần thứ hai với object đã `CLOSED`.

## 5. Ba cách tạo Recording và cấu hình ban đầu

### 5.1. `new Recording()` — không có settings do caller cung cấp

```java
try (Recording r = new Recording()) {
    r.enable("jdk.CPULoad").withPeriod(Duration.ofSeconds(1));
    r.start();
    // ...
    r.stop();
}
```

Ở đây, constructor không lấy bộ settings `default.jfc`. **Đừng hiểu `new Recording()` tự tương đương `new Recording(Configuration.getConfiguration("default"))`**. Khi muốn danh mục event JVM do một JFR configuration đã thiết kế sẵn cung cấp, hãy truyền `Configuration` rõ ràng.

### 5.2. `new Recording(Configuration)` — từ cấu hình `.jfc`

```java
Configuration configuration =
        Configuration.getConfiguration("default");

try (Recording r = new Recording(configuration)) {
    r.setName("default-with-customized-events");
    r.start();
    // ...
    r.stop();
}
```

`Configuration.getConfiguration("default")` đọc một cấu hình JFR định sẵn. Tùy JVM/JDK có thể có cấu hình như `"profile"`, với mức chi tiết/overhead khác `"default"`. **Danh mục và tần suất cụ thể có thể thay đổi theo version**, không giả định mọi JDK phát ra cùng số lượng CPU/GC events.

Để liệt kê:

```java
for (Configuration c : Configuration.getConfigurations()) {
    System.out.println(c.getName());
}
```

Đây là **đoạn minh họa trong một phương thức**. Giá trị kết quả là dữ liệu cấu hình của JVM, không có stdout cố định.

Với cấu hình do tổ chức quản lý:

```java
Configuration custom =
        Configuration.create(Path.of("config/app-profiling.jfc"));
```

File `.jfc` phải tồn tại và đúng định dạng. Cần xử lý `IOException`, `ParseException`, rủi ro file không đáng tin và khác biệt settings khi mang giữa các phiên bản JDK.

### 5.3. `new Recording(Map<String,String>)` — danh sách setting trực tiếp

```java
Map<String, String> settings = new HashMap<>();
settings.put("jdk.CPULoad#enabled", "true");
settings.put("jdk.CPULoad#period", "1 s");

try (Recording recording = new Recording(settings)) {
    recording.start();
    // ...
}
```

Các imports `Map`/`HashMap` và phần business work không lặp lại trong snippet. Keys của settings có dạng phổ biến **`eventName#settingName`**, ví dụ `jdk.CPULoad#enabled` hoặc `jdk.FileWrite#threshold`.

Nên sử dụng `Recording.enable("jdk.CPULoad").withPeriod(...)` khi muốn cú pháp type-safe hơn và tránh sai định dạng chuỗi settings. Event names và settings hợp lệ thuộc khả năng **JDK thực tế**: không copy một setting `period` vào event không hỗ trợ periodic sampling.

## 6. Bật, tắt và điều chỉnh JFR events bằng `EventSettings`

### 6.1. Các thao tác cơ bản

```java
recording.enable("jdk.CPULoad")
        .withPeriod(Duration.ofSeconds(1));

recording.enable("jdk.FileRead")
        .withThreshold(Duration.ofMillis(10))
        .withStackTrace();

recording.disable("jdk.ExecutionSample");
```

Đây là **các dòng trong ngữ cảnh có biến `Recording recording`**, không phải chương trình độc lập. Chính sách cụ thể cần dựa vào mục tiêu chẩn đoán và settings được runtime hỗ trợ.

| API | Dùng làm gì? | Lưu ý |
| --- | --- | --- |
| `enable(String)` | Bật event theo tên | Có thể khớp nhiều event types cùng tên ở nhiều class loaders |
| `enable(Class<? extends Event>)` | Bật event class cụ thể do ứng dụng tạo | Tránh nhập sai tên |
| `disable(String/Class)` | Tắt event của recording | Không nhất thiết vô hiệu hóa cho **mọi Recording khác** trong JVM |
| `withThreshold(Duration)` | Chỉ thu event khi thời lượng đạt ngưỡng | Phù hợp event có duration |
| `withoutThreshold()` | Không dùng ngưỡng duration | Tiện để quan sát custom events rất ngắn |
| `withStackTrace()/withoutStackTrace()` | Bật/tắt stack trace nếu event hỗ trợ | Stack traces thêm chi phí và có thể chứa thông tin nhạy cảm |
| `withPeriod(Duration)` | Chỉ định chu kỳ cho periodic events | Không áp dụng cho mọi event |
| `with(name, value)` | Thiết lập một setting tùy tên | Đọc schema/metadata event type trước khi áp dụng |

### 6.2. Enabled không đồng nghĩa luôn có event trong file

Một event có thể không xuất hiện vì:

- JVM không phát event trong workload thử;
- loại event không tồn tại hoặc không được runtime hỗ trợ;
- event không được enabled cho recording muốn kiểm tra;
- duration thấp hơn threshold;
- sampling period chưa tới;
- buffers/retention khiến event cũ bị loại bỏ hoặc event bị drop;
- recording chưa `RUNNING`, đã `STOPPED` hoặc bị đóng;
- dump chỉ chứa khoảng thời gian trước khi event xuất hiện.

Ví dụ, `jdk.GarbageCollection` không có nghĩa mỗi ứng dụng test ngắn chắc chắn đã xảy ra GC. Để học và kiểm thử ổn định, bài dùng **custom event** do chương trình phát chủ động.

### 6.3. `getSettings()` trả dữ liệu settings, không phải một view có thể sửa trực tiếp

```java
Map<String,String> current = recording.getSettings();
current.put("jdk.CPULoad#period", "2 s");

// Cần set lại; sửa current thôi KHÔNG cập nhật recording.
recording.setSettings(current);
```

`setSettings(Map)` **thay thế toàn bộ settings của recording**, không tự merge với settings cũ. Ví dụ trên lấy `getSettings()` rồi thêm một key mới trước khi set lại để giữ các keys khác.

Một lỗi phổ biến:

```java
Map<String,String> map = new HashMap<>();
map.put("jdk.CPULoad#enabled", "true");
recording.setSettings(map);
```

Nếu recording ban đầu dùng `default.jfc`, dòng trên làm những settings không có trong `map` bị mất do **replace all**, có thể làm bộ dữ liệu ghi khác xa dự định. Khi muốn thêm một setting, ưu tiên `enable/disable` hoặc merge từ `getSettings()`.

### 6.4. Chọn settings trước `start()`

Oracle Javadoc khuyến nghị cấu hình các recording options và event settings **trước `start()`**, để ứng dụng có một điểm chuyển cấu hình nhất quán và tránh chi phí thay đổi settings khi đang ghi.

Một số settings/operations có thể thay đổi khi recording đang chạy, nhưng không có nghĩa mọi thao tác cấu hình đều hợp lệ ở mọi state. Xây rõ một **configuration phase** trước khi bắt đầu là cách đơn giản và bền vững.

## 7. Tạo custom JFR events trong code ứng dụng

Khi cần biết “nghiệp vụ X mất bao lâu” hoặc “request thuộc nhánh xử lý nào”, JFR cho phép định nghĩa event class:

```java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("demo.WorkUnit")
@Label("Work Unit")
public static class WorkUnit extends Event {
    @Label("Task ID")
    public int taskId;

    @Label("Result")
    public String result;
}
```

Đây là **nested class** đặt trong một class bao ngoài; chương trình hoàn chỉnh ở phần 11 có cấu trúc này.

- `@Name("demo.WorkUnit")`: tên event type để filter dữ liệu JFR. Dùng tên ổn định, tránh trùng với các sự kiện `jdk.*` của JVM.
- `@Label`: tên thân thiện để hiển thị.
- Public instance fields: dữ liệu bổ sung của event, ví dụ ID số và trạng thái không nhạy cảm.
- `Event`: superclass cung cấp `begin()`, `end()`, `commit()`, `shouldCommit()`.

Phát event:

```java
WorkUnit e = new WorkUnit();
e.taskId = 7;
e.result = "OK";

e.begin();
// Đo công việc muốn quan sát.
e.end();

if (e.shouldCommit()) {
    e.commit();
}
```

Nếu `begin()` đã được gọi mà quên `end()`, `commit()` có thể kết thúc timing tại thời điểm commit. Trong code có async work, phải hiểu duration đo khoảng nào; không coi thời gian đứng trong queue là tự được bao gồm nếu event chỉ `begin` khi worker bắt đầu.

### `shouldCommit()` và event threshold

`shouldCommit()` đánh giá event có bật và duration đạt threshold hay không. Dùng trước khi thu thập **những field tốn kém**:

```java
WorkUnit e = new WorkUnit();
e.begin();

performOperation();

e.end();
if (e.shouldCommit()) {
    e.result = buildSafeSummary();
    e.commit();
}
```

Đây là **snippet**: `performOperation`/`buildSafeSummary` là các hàm của ứng dụng. Ghi `String result` không chứa access tokens, password, raw request/response body hay PII không cần thiết. JFR có thể được dump và chia sẻ để điều tra nên phải coi trường event như **diagnostic data có bảo mật**.

### Có phải event luôn được ghi đúng một lần khi gọi `commit()`?

Không nên viết test nghiệp vụ phụ thuộc cứng rằng một call `commit` chắc chắn có đúng một event vĩnh viễn trong mọi recording: settings, thresholds, buffers, thời điểm start/stop, repository retention và failure có thể tác động.

Tuy vậy, với **fixture đơn giản, chạy ngắn, threshold tắt và provider hỗ trợ JFR**, custom events thường được ghi đầy đủ và có thể kiểm tra bằng `RecordingFile`. Chương trình bên dưới đã kiểm chứng ba event trong file cuối trên môi trường thử.

## 8. Giữ dữ liệu: `setToDisk`, `setMaxAge` và `setMaxSize`

### 8.1. `setToDisk(true)`

```java
recording.setToDisk(true);
```

Đây là mặc định theo Javadoc nếu không thiết lập khác. JFR ghi dữ liệu đến **disk repository** theo cơ chế chunk/buffering của JVM. Mức disk I/O và thời điểm flush không đồng nghĩa ghi đồng bộ mỗi event xuống file xuất cuối cùng.

`setToDisk(false)` dùng hướng lưu dữ liệu giới hạn ở memory buffers theo cơ chế runtime. Đừng coi lựa chọn này là “không dùng bộ nhớ”; cũng không phải một phép bảo đảm giữ toàn bộ lịch sử dài hạn.

### 8.2. `setMaxAge(Duration)`

```java
recording.setMaxAge(Duration.ofMinutes(5));
```

Đặt ngưỡng **tuổi dữ liệu giữ lại** trong repository. Khi vượt, JVM có thể loại những chunks cũ để chỉ giữ một cửa sổ dữ liệu gần đây. Không được suy ra giới hạn này đảm bảo chính xác từng event sau đúng 5 phút sẽ mất theo microsecond.

Giá trị `null` mang nghĩa không đặt giới hạn tuổi. Nếu không đặt cả maxAge và maxSize, một recording disk-backed chạy dài **có thể phát triển không giới hạn** tùy workload và không gian đĩa.

### 8.3. `setMaxSize(long)`

```java
recording.setMaxSize(16L * 1024 * 1024);
```

Giá trị là **byte**; ví dụ là **16 MiB**. Theo Javadoc, khi data vượt ngưỡng, JVM loại chunk cũ để nhường chỗ cho chunk mới. Không coi `maxSize` là một hard bound đối với **final exported `.jfr` trong mọi trường hợp**, bởi overhead/chunking và thời điểm flush có ảnh hưởng.

Giá trị `0` có nghĩa không có giới hạn size, số âm bị từ chối. Trong production, kết hợp retention với quota disk/repository, giám sát dung lượng và chính sách dọn snapshot files.

### 8.4. `getSize()` không phải kích thước file dump

`recording.getSize()` phản ánh số bytes của recording trong **disk repository**, được cập nhật khi buffers flush. Nếu recording không dùng disk repository, `getSize()` luôn trả **0** theo hợp đồng, ngay cả khi recording có hoạt động.

Không dùng `getSize() == 0` để khẳng định “không có JFR events” trong mọi trường hợp.

## 9. Xuất bản ghi: `dump(Path)`, `setDestination(Path)` và `copy(true)`

Đây là ba thao tác liên quan nhưng **không tương đương**.

### 9.1. `dump(Path)` khi recording vẫn `RUNNING`

```java
recording.start();
// Công việc đã phát ra vài event.
recording.dump(Path.of("live.jfr"));
System.out.println(recording.getState()); // RUNNING
```

`dump` tạo một file chứa dữ liệu bản ghi sẵn có. **Nó không tự stop recording gốc.** Phù hợp tình huống đang điều tra sự cố trong production: xuất snapshot để phân tích rồi tiếp tục quan sát.

`dump` cũng dùng được sau `stop()` khi dữ liệu recording vẫn còn và recording chưa bị đóng. Nếu muốn snapshot ở một thời điểm nào đó, hiểu rằng file phản ánh những event được giữ/flush trong cửa sổ lúc dump, không phải một phép chụp tất cả dữ liệu của JVM mãi mãi.

### 9.2. `setDestination(Path)`: ghi khi stop, có thể tự close

```java
recording.setDestination(Path.of("final.jfr"));
recording.start();
// ...
recording.stop();
// Với dump thành công, Recording đã được tự đóng.
```

Theo Javadoc, nếu đã đặt destination, khi recording dừng, dữ liệu sẽ được chép vào đó và recording **được tự động đóng khi export thành công**.

Vì thế:

- Không viết code mặc định rằng `stop()` luôn giữ recording ở `STOPPED` nếu đã gọi `setDestination`.
- Không gọi `dump` sau khi recording đã `CLOSED`.
- Không nhầm `setDestination` với `dump`: một cái **cấu hình địa điểm cho thao tác stop**, một cái **xuất dữ liệu ở thời điểm gọi**.
- Đặt destination trước khi stop; `setDestination` không hợp lệ nếu recording đã `STOPPED` hoặc `CLOSED`.

**Lưu ý đường dẫn và quyền:** thư mục phải tồn tại/được phép ghi; xử lý `IOException`/quyền I/O; không dùng path đến từ người dùng chưa được validate để ghi đè bất kỳ file nào.

### 9.3. `copy(true)`: tạo bản sao đã dừng

```java
try (Recording copy = recording.copy(true)) {
    copy.dump(Path.of("copy.jfr"));
}
```

`recording.copy(true)` tạo một recording bản sao với ID và tên riêng, **bản sao được dừng ngay**. Recording **gốc không bị stop** chỉ vì tạo copy.

Phù hợp khi muốn tạo một dataset ổn định để xuất/analyze trong lúc recording gốc tiếp tục chạy. Nhớ `close()` bản sao sau khi dùng. Ngoài ra `copy(false)` tạo clone theo cơ chế API mà không dừng nó ngay; thiết kế lifecycle/retention rõ ràng khi dùng.

### 9.4. `getStream(start, end)` và `getDumpOnExit()`

`recording.getStream(Instant start, Instant end)` tạo `InputStream` của dữ liệu recording trong một khoảng thời gian đã yêu cầu. Các event nằm hơi ngoài khoảng thời gian có thể được đưa vào do cơ chế chunks. Với recording không disk-backed, theo Javadoc có thể trả `null` thay vì stream.

Vì thế:

```java
try (InputStream in = recording.getStream(null, null)) {
    if (in != null) {
        // Chuyển dữ liệu .jfr sang nơi xử lý được phép.
    }
}
```

Đây là **snippet**, import `java.io.InputStream` và yêu cầu xử lý các ngoại lệ I/O. Nếu stream là null, try-with-resources Java chấp nhận resource null, nhưng nên kiểm tra rõ trước khi sử dụng.

`recording.setDumpOnExit(true)` là chính sách hỗ trợ dump khi JVM exit bình thường theo khả năng implementation; **không bảo đảm** sẽ có file khi process bị kill đột ngột, crash, mất điện hoặc không còn disk space. Không dùng thay `dump`/`stop` có kiểm soát trong quy trình shutdown.

## 10. Đọc file JFR: `RecordingFile` và `RecordedEvent`

### 10.1. `readAllEvents(path)`: tiện cho file nhỏ

```java
List<RecordedEvent> events = RecordingFile.readAllEvents(path);

long matches = events.stream()
        .filter(e -> "demo.WorkUnit".equals(
                e.getEventType().getName()))
        .count();
```

`RecordingFile.readAllEvents` đọc **toàn bộ events vào một `List`**. Oracle Javadoc khuyến nghị nó chỉ cho **trường hợp đơn giản/file nhỏ**, không dùng để load recording lớn vài GB vào bộ nhớ sản phẩm.

Mỗi `RecordedEvent` có:

- `getEventType().getName()`: tên event type, ví dụ `demo.WorkUnit`;
- `getStartTime()`, `getEndTime()`, `getDuration()` tùy metadata;
- `getThread()`, `getStackTrace()` khi event cung cấp;
- `getInt("taskId")`, `getString("result")` đối với fields được định nghĩa đúng trong event.

Không đoán field name tùy ý. Nếu JFR event của bản JDK khác có schema khác, API get field có thể báo lỗi. Với tool phân tích cần kiểm tra `EventType.getFields()` hoặc metadata file.

### 10.2. `RecordingFile` streaming iterator: an toàn hơn cho file lớn

```java
try (RecordingFile file = new RecordingFile(path)) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        if ("demo.WorkUnit".equals(event.getEventType().getName())) {
            System.out.println(event.getInt("taskId"));
        }
    }
}
```

Đây là code **trong phương thức** với `path` đã được khai báo. `RecordingFile` là file reader đóng được; việc lặp từng event giảm nhu cầu lưu tất cả objects đồng thời so với `readAllEvents`. Dù vậy, processing từng event có thể có chi phí CPU/memory riêng.

Javadoc yêu cầu **chỉ đọc JFR files từ nguồn tin cậy**. Không tự coi `.jfr` upload từ người lạ là dữ liệu vô hại; nó là binary file có parser và có thể chứa thông tin nhạy cảm.

### 10.3. Xác nhận event trước khi xây dashboard

Đừng chỉ nhìn `Files.size(file) > 0` rồi kết luận recording có event quan tâm. File có metadata/events khác. Cần filter đúng event name, kiểm tra thời gian, count và fields theo contract.

Ngược lại, trong bản ghi mặc định, có thể có hàng nghìn events JVM ngoài custom event. Đừng viết code đòi **tổng event count** phải bằng 3 khi test chỉ tạo ba `demo.WorkUnit` events; hãy lọc riêng sự kiện của ứng dụng.

## 11. Ví dụ hoàn chỉnh 1: tạo, điều khiển, dump, copy và đọc lại Recording

Chương trình sau đã được **biên dịch với `javac --release 11` và chạy trên JVM hỗ trợ `jdk.jfr`**. Nó chạy **offline**; không gọi Internet hay external services.

Mục tiêu:

1. Kiểm tra `FlightRecorder.isAvailable()`.
2. Tạo `Recording` bằng cấu hình `default`.
3. Tên recording, retention, disk mode và custom event settings được thiết lập **trước start**.
4. Phát hai custom events.
5. `dump` file snapshot khi recording vẫn `RUNNING`.
6. Tạo `copy(true)` và xuất bản sao.
7. Phát event thứ ba, `stop()` recording gốc và xuất file cuối.
8. Đọc lại files, đếm **chỉ các event `demo.WorkUnit`**.
9. `close` đúng cách và dọn files tạm.

### File `JfrRecordingDemo.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;

import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrRecordingDemo {
    @Name("demo.WorkUnit")
    @Label("Work Unit")
    public static class WorkUnit extends Event {
        @Label("Task ID")
        public int taskId;

        @Label("Result")
        public String result;
    }

    private static void recordTask(int id, String result) {
        WorkUnit event = new WorkUnit();
        event.taskId = id;
        event.result = result;

        event.begin();
        event.end();

        if (event.shouldCommit()) {
            event.commit();
        }
    }

    private static long countEvents(Path path) throws Exception {
        List<RecordedEvent> events =
                RecordingFile.readAllEvents(path);
        return events.stream()
                .filter(e -> "demo.WorkUnit"
                        .equals(e.getEventType().getName()))
                .count();
    }

    public static void main(String[] args) throws Exception {
        if (!FlightRecorder.isAvailable()) {
            System.out.println("jfrAvailable=false");
            return;
        }

        Path directory =
                Files.createTempDirectory("jfr-recording-demo-");
        Path live = directory.resolve("live.jfr");
        Path finalDump = directory.resolve("final.jfr");
        Path copyFile = directory.resolve("copy.jfr");

        try {
            try (Recording recording = new Recording(
                    Configuration.getConfiguration("default"))) {

                recording.setName("controlled-work-units");
                recording.setToDisk(true);
                recording.setMaxAge(Duration.ofMinutes(5));
                recording.setMaxSize(16L * 1024 * 1024);

                recording.enable(WorkUnit.class)
                        .withoutThreshold()
                        .withoutStackTrace();

                System.out.println(
                        "initial=" + recording.getState());

                recording.start();
                System.out.println(
                        "afterStart=" + recording.getState());

                recordTask(1, "OK");
                recordTask(2, "OK");

                // Xuất snapshot nhưng KHÔNG dừng recording gốc.
                recording.dump(live);
                System.out.println(
                        "afterLiveDump=" + recording.getState());
                System.out.println(
                        "liveEvents=" + countEvents(live));

                // Copy đã dừng; recording gốc vẫn RUNNING.
                try (Recording copy = recording.copy(true)) {
                    System.out.println(
                            "copyState=" + copy.getState());
                    copy.dump(copyFile);
                    System.out.println(
                            "copyEvents=" + countEvents(copyFile));
                }

                recordTask(3, "DONE");

                boolean stopped = recording.stop();
                System.out.println("stopReturned=" + stopped);
                System.out.println(
                        "afterStop=" + recording.getState());

                recording.dump(finalDump);
                System.out.println(
                        "finalEvents=" + countEvents(finalDump));
            }

            System.out.println("filesWritten=" +
                    (Files.size(live) > 0
                    && Files.size(finalDump) > 0
                    && Files.size(copyFile) > 0));
        } finally {
            Files.deleteIfExists(live);
            Files.deleteIfExists(finalDump);
            Files.deleteIfExists(copyFile);
            Files.deleteIfExists(directory);
        }
    }
}
```

### Biên dịch và chạy

```bash
javac --release 11 --add-modules jdk.jfr JfrRecordingDemo.java
java --add-modules jdk.jfr JfrRecordingDemo
```

**Kết quả đã được kiểm chứng ở môi trường thử:**

```text
initial=NEW
afterStart=RUNNING
afterLiveDump=RUNNING
liveEvents=2
copyState=STOPPED
copyEvents=2
stopReturned=true
afterStop=STOPPED
finalEvents=3
filesWritten=true
```

### Phân tích từng dòng

| Dòng | Ý nghĩa |
| --- | --- |
| `initial=NEW` | Constructor chưa bắt đầu thu event |
| `afterStart=RUNNING` | `start()` bắt đầu recording |
| `afterLiveDump=RUNNING` | `dump(live)` **không tự stop** |
| `liveEvents=2` | Snapshot đầu chứa hai custom events đã phát |
| `copyState=STOPPED` | `copy(true)` tạo bản sao đã dừng |
| `copyEvents=2` | Bản sao giữ dữ liệu của hai custom events lúc copy |
| `stopReturned=true` | `stop()` báo đã dừng thành công |
| `afterStop=STOPPED` | Recording gốc không đặt destination nên giữ data để dump |
| `finalEvents=3` | File cuối bao gồm event thứ ba |
| `filesWritten=true` | Ba file tạm đã được xuất và có kích thước lớn hơn 0 |

**Giới hạn tính quyết định:** Count 2/2/3 được kiểm chứng trong **fixture cụ thể** với custom events rất nhỏ và retention đủ rộng. Trên môi trường JFR bị giới hạn/khác provider hoặc under high load, event retention/drops có thể khác. Điều mang tính hợp đồng là vòng đời API và cách đếm events đúng schema, không phải cam kết mọi JVM luôn lưu 100% events trong mọi hoàn cảnh.

### Vì sao dùng `try-with-resources`?

`Recording.close()` giải phóng tài nguyên JFR. `copy(true)` tạo một Recording thứ hai, cũng cần đóng. Mẫu lồng hai khối `try` giúp bản ghi gốc và bản sao được đóng ngay cả khi đọc file hoặc xuất snapshot xảy ra lỗi. Khối `finally` dọn những file tạm; trong sản phẩm thật hãy thay bằng retention/export policy và **không xóa ngay file mà cần giữ để điều tra**.

## 12. Ví dụ hoàn chỉnh 2: `setDestination()` và `scheduleStart()` / `setDuration()`

Đây là một chương trình **khác, có `main` riêng**, kiểm chứng hai nhánh vòng đời mà ví dụ đầu chưa sử dụng.

### File `JfrLifecycleDemo.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import jdk.jfr.Configuration;
import jdk.jfr.Recording;
import jdk.jfr.RecordingState;

public final class JfrLifecycleDemo {
    public static void main(String[] args) throws Exception {
        Path file =
                Files.createTempFile("jfr-destination-", ".jfr");

        try {
            // Nhánh 1: destination được ghi khi stop, tự close.
            try (Recording r = new Recording(
                    Configuration.getConfiguration("default"))) {
                r.setDestination(file);
                r.start();

                System.out.println(
                        "destinationRunning=" + r.getState());

                r.stop();

                System.out.println(
                        "destinationAfterStop=" + r.getState());
                System.out.println(
                        "destinationIsFile=" + (Files.size(file) > 0));
            }

            // Nhánh 2: bắt đầu muộn, tự stop sau duration.
            try (Recording r = new Recording()) {
                r.setDuration(Duration.ofMillis(400));
                r.scheduleStart(Duration.ofMillis(250));

                System.out.println(
                        "scheduledState=" + r.getState());

                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(12);

                while (r.getState() != RecordingState.STOPPED
                        && System.nanoTime() < deadline) {
                    Thread.sleep(50);
                }

                System.out.println("autoStopped=" +
                        (r.getState() == RecordingState.STOPPED));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 11 --add-modules jdk.jfr JfrLifecycleDemo.java
java --add-modules jdk.jfr JfrLifecycleDemo
```

**Stdout đã kiểm chứng trong môi trường thử:**

```text
destinationRunning=RUNNING
destinationAfterStop=CLOSED
destinationIsFile=true
scheduledState=DELAYED
autoStopped=true
```

Giải thích:

- `setDestination(file)`: khi `stop()` ghi file thành công, `getState()` đã là **`CLOSED`**. Vì vậy đừng gọi `dump()` sau đó như một bước luôn hợp lệ.
- `scheduleStart(Duration.ofMillis(250))`: đưa recording mới vào **`DELAYED`**, rồi timer chuyển sang `RUNNING`.
- `setDuration(Duration.ofMillis(400))`: yêu cầu tự dừng sau duration kể từ lúc recording bắt đầu, không phải kể từ thời điểm `new Recording()`.
- Chương trình có deadline 12 giây để tránh chờ vô hạn nếu JFR scheduler bất thường. Vì lịch thread/JVM khởi tạo có thể thay đổi, đây là **thử nghiệm vòng đời**, không phải benchmark đo độ chính xác của scheduler tới millisecond.

**Trong production:** ưu tiên durations đủ dài để có dữ liệu chẩn đoán hữu ích, có khả năng xử lý `InterruptedException`, timestamp, I/O errors và policy khi tự dừng mà chưa export. Một recording **STOPPED** nhưng không có destination vẫn cần `dump` trước `close` nếu muốn lưu file.

## 13. `FlightRecorder`: quan sát Recording đang tồn tại trong JVM

`Recording` đại diện một bản ghi, còn `FlightRecorder` có chức năng quản lý và liệt kê recordings.

```java
import jdk.jfr.FlightRecorder;
import jdk.jfr.Recording;

FlightRecorder recorder = FlightRecorder.getFlightRecorder();

for (Recording r : recorder.getRecordings()) {
    System.out.println(
            r.getId() + " / " + r.getName() + " / " + r.getState());
}
```

Đây là **đoạn code trong phương thức**. `getRecordings()` trả danh sách recordings **đang tồn tại và chưa `CLOSED`** trong JVM hiện tại; không phải danh sách files `.jfr` trên đĩa và cũng không phải công cụ truy cập recordings của một JVM từ xa.

### `getId`, `getName`, `getStartTime`, `getStopTime`

```java
System.out.println(recording.getId());
System.out.println(recording.getName());
System.out.println(recording.getStartTime());
System.out.println(recording.getStopTime());
```

- `getId()`: ID riêng của recording trong JVM.
- `getName()`: tên đọc được; có thể đặt bằng `setName`, mặc định là chuỗi từ ID.
- `getStartTime()`: null nếu recording chưa bắt đầu.
- `getStopTime()`: null nếu recording chưa dừng.

Không dùng recording ID như một global unique identifier xuyên tiến trình hoặc sau restart. Muốn đối chiếu trong hệ thống tập trung, gắn thêm service/instance/version/timestamps vào metadata ngoài file theo chính sách.

### `FlightRecorder.takeSnapshot()`

API:

```java
try (Recording snapshot =
        FlightRecorder.getFlightRecorder().takeSnapshot()) {
    snapshot.dump(Path.of("all-available.jfr"));
}
```

Tạo **snapshot tổng hợp từ dữ liệu JFR đang có sẵn** ở JVM, không giống hoàn toàn `recording.copy(true)` của **một** Recording cụ thể. Dùng khi cần bức tranh chung, nhưng vẫn phải quản lý quyền, PII và dung lượng.

`FlightRecorder.getRecordings()` và `takeSnapshot()` không nên được gọi liên tục với tần suất cao để tạo hàng trăm files mà không có retention. Mỗi snapshot/clone đều có chi phí và có thể làm tăng I/O.

## 14. Điều khiển Recording trong ứng dụng dịch vụ

### 14.1. Một controller nên quản lý một lifecycle rõ ràng

Mẫu tối giản mang tính **thiết kế**:

```text
Admin request "start diagnostics"
   |
   +--> kiểm tra authorization của operator
   +--> kiểm tra không có recording do controller sở hữu đang RUNNING
   +--> tạo Recording mới từ safe settings
   +--> setMaxAge / setMaxSize / setName
   +--> start() và lưu handle trong controller

Admin request "snapshot diagnostics"
   |
   +--> xác minh recording thuộc về controller
   +--> validate export directory / file name
   +--> dump(path) hoặc copy(true)+dump(path)
   +--> trả metadata/path, không trả raw secrets

Admin request "stop diagnostics"
   |
   +--> stop() nếu state hợp lệ
   +--> dump(path) nếu chưa có setDestination và muốn giữ file
   +--> close()
   +--> giải phóng handle, cập nhật trạng thái controller
```

**Không đặt một endpoint không xác thực kiểu `POST /jfr/start` hay `GET /jfr/dump` công khai Internet**. JFR có thể chứa stack traces, class names, file paths, exception messages, user data trong custom fields và metadata về tiến trình. Việc kích hoạt profiling cũng tiêu thụ CPU/memory/disk; cần quyền quản trị, audit, rate limit, timeout và quota.

### 14.2. Tránh điều khiển cùng Recording từ nhiều threads thiếu đồng bộ

Ví dụ hai HTTP admin requests đồng thời:

- request A: `stop`;
- request B: `dump`;
- request C: `close`.

Nếu không có đồng bộ, `dump` có thể tới sau `close`, gây `IOException`/state errors hoặc mất dữ liệu muốn giữ. Hãy dùng một controller có serialized commands/lock hoặc executor chuyên trách cho lifecycle; tránh cấu trúc “check getState rồi thao tác” không atomic khi nhiều threads tranh chấp.

### 14.3. Đặt guardrails

Trước start, xác định:

- **Max duration** để không ghi vô hạn;
- **Max age/size** của repository;
- **Event allowlist** và thresholds/period, tránh thu mọi event cực chi tiết;
- **Export path** trong một thư mục quản lý riêng, tránh path traversal;
- **Quyền filesystem** chỉ dành cho user/service có thẩm quyền;
- **Giới hạn tần suất** start/snapshot và số recordings cùng lúc;
- **Dọn file** và thời gian lưu JFR sau điều tra;
- **Thông tin môi trường** cần kèm theo nhưng không chứa secrets;
- **Hành vi khi thiếu JFR**: degrade gracefully hoặc báo diagnostic capability unavailable.

## 15. Bản ghi liên tục, snapshot khi có sự cố và những giới hạn cần hiểu

### 15.1. Pattern “flight recorder” cho dịch vụ chạy lâu

Một mô hình phổ biến:

1. Khi service khởi động, tạo một recording cấu hình ít overhead.
2. Chọn `setMaxAge(Duration.ofMinutes(...))` và `setMaxSize(...)` hợp lý.
3. Bật các event JVM và custom event thực sự hữu ích.
4. `start()` ghi liên tục, giữ cửa sổ gần nhất trong repository.
5. Khi phát hiện một cảnh báo hợp lệ, `dump(snapshotPath)` ngay lúc recording **vẫn RUNNING**.
6. Tiếp tục thu dữ liệu cho tới khi shutdown hoặc theo policy.
7. Lúc kết thúc: stop/dump nếu cần, close, dọn file theo retention.

Điều này phù hợp hơn việc liên tục tạo recording mới cho từng request HTTP. Tuy nhiên, **không coi JFR là log nghiệp vụ bền vững**: event cũ có thể bị loại bỏ theo retention, một số event bị drop dưới tải cao, và dữ liệu JFR không phải transactional audit trail.

### 15.2. Pattern “thu trong một cửa sổ”

```java
try (Recording r = new Recording(
        Configuration.getConfiguration("default"))) {
    r.setDuration(Duration.ofSeconds(30));
    r.setMaxSize(64L * 1024 * 1024);
    r.start();

    // Ứng dụng tiếp tục chạy công việc.
    // Khi r tự STOPPED, dump trước khi close.
}
```

Đây chỉ là **snip thiết kế** — nếu không có đoạn chờ/`dump` trước khi rời try, recording sẽ bị đóng mà chưa lưu. Trong triển khai thật phải theo dõi `RecordingState.STOPPED`, dùng lifecycle callback/control flow phù hợp và xuất file trước khi close.

Nếu có yêu cầu “ghi 30 giây rồi lưu vào file”, đặt `setDestination(path)` **trước start** sẽ giúp export khi tự dừng, và theo Javadoc object có thể chuyển thẳng sang `CLOSED` sau khi ghi thành công.

### 15.3. Pattern snapshot theo ngữ cảnh

`recording.copy(true)` hữu ích khi cần sao chép “những gì đã thu đến thời điểm này” thành bản ghi có state ổn định để xuất/giới hạn maxAge/maxSize mà không stop gốc. Nhưng bản copy phải được đóng và không thể giữ tham chiếu vô thời hạn.

### 15.4. Không nhầm với JFR streaming APIs ở JDK mới hơn

Ở JDK mới hơn Java 11 có các streaming APIs thuộc `jdk.jfr.consumer` như `RecordingStream`. **Đó là một workflow khác** (nhận event liên tục), không phải thứ bắt buộc để giải quyết bài điều khiển recording ở Java 11.

Để bài **biên dịch được với `--release 11`**, các ví dụ chính dùng `Recording` và `RecordingFile` — đều có trong baseline Java 11 và tiếp tục hợp lệ ở các phiên bản hiện hành.

## 16. Xử lý ngoại lệ và tài nguyên đúng cách

### 16.1. Những loại lỗi có thể gặp

| Vấn đề | Triệu chứng | Cách xử lý |
| --- | --- | --- |
| JVM không hỗ trợ JFR | `FlightRecorder.isAvailable()` false, constructor lỗi | Kiểm tra JDK/runtime modules và khả năng JVM |
| Cấu hình tên `default` không có/không đọc được | `IOException` hoặc `ParseException` | Kiểm tra `Configuration.getConfigurations()` và JDK config |
| `start()` khi đã RUNNING/CLOSED | `IllegalStateException` | Quản lý state, không restart instance |
| `stop()` ngoài trạng thái hợp lệ | `IllegalStateException` | Dùng controller/lifecycle đúng |
| `scheduleStart` khi không còn NEW | `IllegalStateException` | Lên lịch từ recording mới |
| `setDestination` sau STOPPED/CLOSED | `IllegalStateException` | Cấu hình file trước khi start/stop |
| `dump` không tạo được file | `IOException`/security exception | Kiểm tra path, filesystem, quyền, quota |
| Đọc file `.jfr` sai/không tồn tại | `IOException`/`NoSuchFileException` | Kiểm tra file đã export xong và nguồn tin cậy |
| Một event type không xuất hiện | Sai tên/threshold/không có workload | Kiểm tra settings và event metadata |
| Recording giữ file/chunks quá lâu | Quên `close()` | `try-with-resources`; close cả bản copy/snapshot |
| Repository đầy đĩa | Retention không có hoặc export quá nhiều | Giới hạn age/size, dọn snapshots theo TTL |
| Đọc toàn bộ recording làm hết heap | `readAllEvents` với file lớn | Lặp streaming `RecordingFile.hasMoreEvents()/readEvent()` |
| Dữ liệu JFR chứa thông tin nhạy cảm | Export không kiểm soát | RBAC, mã hóa lưu trữ, giới hạn fields và quyền chia sẻ |

### 16.2. `dump()` trong `finally` có cần không?

Một pattern shutdown có thể cần giữ recordings kể cả khi workload ném exception:

```java
Recording r = new Recording(
        Configuration.getConfiguration("default"));
try {
    r.start();
    doBusinessWork();
} finally {
    try {
        if (r.getState() == RecordingState.RUNNING) {
            r.stop();
        }
        if (r.getState() == RecordingState.STOPPED) {
            r.dump(Path.of("failure.jfr"));
        }
    } finally {
        r.close();
    }
}
```

Đây là **đoạn minh họa** với `doBusinessWork()` do ứng dụng cung cấp, imports phù hợp và policy path đã kiểm tra. Nó không xử lý mọi ngoại lệ/auto-closed destination, cũng không bảo đảm export nếu JVM bị kill cứng.

Đặc biệt, **không che khuất exception nghiệp vụ gốc** bằng cách ném lỗi dump mới rồi đánh mất nguyên nhân. Production có thể ghi suppressed exception hoặc dùng cấu trúc error aggregation theo logger/exception policy.

### 16.3. Close sớm và auto-close do destination

Nếu đã đặt `setDestination`, `stop()` tự close khi export thành công; `try-with-resources` gọi `close` sau đó vẫn phù hợp với idiom resource management. Nhưng code sau stop **không được giả định `getState()==STOPPED`** trong nhánh này.

Nếu chưa setDestination, `stop()` giữ data để `dump`/`copy` và `close` giải phóng chúng. Đây là nguồn của hai kết quả khác nhau trong phần 11 và 12.

## 17. Bảo mật, overhead và quyền truy cập file JFR

### 17.1. JFR là nguồn dữ liệu chẩn đoán có thể nhạy cảm

Dữ liệu có thể bao gồm:

- tên method/class, stack traces;
- đường dẫn file I/O, exception messages;
- thread names, thời gian hoạt động;
- metadata môi trường runtime;
- custom fields do ứng dụng lựa chọn;
- thông tin về tải hệ thống, request IDs hoặc account identifiers nếu app đưa vào fields.

**Không** đưa access token, password, session cookies, raw credit card numbers hoặc dữ liệu khách hàng không cần thiết vào JFR event fields. Khi dump ra file, coi file như artifact nội bộ có policy phân quyền và thời gian lưu.

### 17.2. Không coi JFR là zero-overhead

JFR được thiết kế cho chẩn đoán với overhead tương đối thấp trong nhiều cấu hình, nhưng **không phải không có chi phí**. Overhead phụ thuộc:

- event types đã bật;
- độ dày của stack traces;
- thresholds và sampling periods;
- số lượng/độ lớn custom event fields;
- mức độ hot của code phát event;
- disk repository, flush và snapshot frequency;
- cấu hình JVM/GC, tốc độ I/O và provider.

Sử dụng `default` và chỉ mở thêm event cần thiết thường là điểm bắt đầu hợp lý. Với điều tra sâu, có thể dùng cấu hình `profile` trong khoảng thời gian giới hạn đã được đánh giá. Không bật tất cả events với threshold 0 rồi giả định hiệu năng production không bị ảnh hưởng.

### 17.3. Không dùng một file JFR làm nguồn sự thật pháp lý

JFR là telemetry/diagnostics, **không phải** immutable audit log: event có thể mất do retention/drops, không bảo đảm delivery exactly-once, không phải một giao dịch database và file có thể được chỉnh sửa/xóa nếu filesystem cho phép. Cần audit trail bảo vệ riêng nếu hệ thống yêu cầu compliance.

### 17.4. Bảo mật export API và paths

Nếu điều khiển JFR từ admin HTTP endpoint:

- Xác thực operator và phân quyền thao tác.
- Audit ai start, stop, dump và download.
- Không nhận raw absolute path do người dùng đưa rồi ghi file tùy ý.
- Dùng thư mục riêng, tên file được sinh an toàn và quota rõ.
- Giới hạn số snapshot/đồng thời để tránh disk flood.
- Mã hóa file lưu trữ khi chính sách yêu cầu, truyền qua kênh bảo mật.
- Xóa dữ liệu đúng TTL và kiểm soát bản sao sau khi tải xuống.

Một bản ghi JFR không chứa credential vẫn có thể tiết lộ cấu trúc hệ thống; cần xử lý theo security classification thực tế.

## 18. Chẩn đoán bằng công cụ JDK song song với API

Sau khi đã xuất file, có thể kiểm tra bằng JDK CLI tương thích:

```bash
jfr print --events demo.WorkUnit final.jfr
jfr summary final.jfr
```

`jfr print` hỗ trợ lọc event bằng `--events` theo tên event; `jfr summary` hiển thị thông tin tổng quan nếu phiên bản công cụ có subcommand đó. **Cần dùng file thực tế**: ví dụ `JfrRecordingDemo` tự xóa files khi kết thúc nên muốn chạy CLI phải sửa chính sách cleanup hoặc copy file ra một thư mục giữ lại.

Có thể phân tích với JDK Mission Control hoặc các công cụ JFR hiện hành tùy môi trường. Chúng không thay thế code lifecycle nếu ứng dụng cần tự start/stop/dump theo event nghiệp vụ.

`jcmd` có những lệnh quản lý JFR từ bên ngoài JVM như `JFR.start`, `JFR.stop` và `JFR.dump` tùy bản JDK; chủ đề này tập trung vào public `Recording` API được gọi **bên trong chính JVM**, nên không yêu cầu JMX/process-attach hay shell permissions để thực thi các ví dụ.

### Cách đối chiếu file và code

1. Chạy chương trình, giữ một file `.jfr`.
2. Mở file bằng `RecordingFile` hoặc CLI `jfr print`.
3. Filter `demo.WorkUnit` để chỉ thấy custom event.
4. Kiểm tra `taskId`/`result`, timestamp và duration.
5. Kiểm tra có những JVM events khác không nếu dùng `default.jfc`.
6. So sánh khoảng thời gian giữa `getStartTime()/getStopTime()` và timestamps của custom events.
7. Giữ log lỗi nếu I/O, parsing hoặc JFR không hỗ trợ xảy ra; không công khai raw dữ liệu nhạy cảm.

## 19. Những nhầm lẫn thường gặp

| Hiểu lầm | Điều đúng |
| --- | --- |
| `new Recording()` tự chạy ngay | Chưa; state `NEW` cho đến `start()` hoặc start theo lịch |
| `new Recording()` tương đương `new Recording(default)` | Không; constructor đầu không cung cấp predefined settings |
| `dump()` cũng là `stop()` | Không; có thể dump khi `RUNNING` và tiếp tục thu |
| `stop()` luôn lưu file `.jfr` | Không; phải `dump` hoặc đã set destination |
| `stop()` luôn để state `STOPPED` | Có destination export thành công thì recording có thể thành `CLOSED` |
| `close()` tự tạo file backup | Không; nó giải phóng dữ liệu/tài nguyên |
| Recording đã `STOPPED` có thể `start()` lại | Không; tạo Recording mới |
| `copy(true)` làm dừng recording gốc | Không; clone được stop, original tiếp tục nếu đang chạy |
| `setMaxSize` bảo đảm file export có đúng kích thước tối đa tuyệt đối | Không; retention theo disk chunks, thêm overhead/chunk granularity |
| `getSize()==0` nghĩa là không có events | Không; in-memory recording trả 0 theo contract |
| Event enabled nghĩa là nhất định đã phát event | Không; phụ thuộc workload, threshold, timing |
| `withoutThreshold()` áp dụng nghĩa là luôn có stack trace | Không; threshold và stackTrace là settings riêng |
| `withPeriod` dùng cho mọi event | Không; chỉ có ý nghĩa với periodic setting được event hỗ trợ |
| `getSettings().put(...)` cập nhật Recording trực tiếp | Không; phải `setSettings(...)` |
| `setSettings` merge với settings cũ | Không; nó **thay thế toàn bộ** |
| `readAllEvents` là cách lý tưởng cho file rất lớn | Không; nó load toàn bộ events vào memory |
| Total events trong `default.jfc` bằng số custom events tự phát | Không; JVM có thể có nhiều events khác |
| JFR là audit log bền vững không mất data | Không; retention/drops và không transactional |
| Dump file có thể cho mọi user download | Không; JFR có thể chứa diagnostic metadata nhạy cảm |
| `FlightRecorder.getRecordings()` liệt kê các JVM từ xa | Không; là recordings trong JVM hiện tại |
| `scheduleStart` gọi khi đã dừng vẫn hợp lệ | Không; chỉ từ `NEW` |
| `setDumpOnExit` chắc chắn cứu được dữ liệu khi JVM crash | Không bảo đảm nếu bị kill/crash/disk failure |
| `RecordingStream` bắt buộc để dùng Recording trên Java 11 | Không; `Recording`/`RecordingFile` đã đủ cho workflow này |
| Bản ghi càng nhiều events càng luôn tốt | Không; overhead, noise và rủi ro data disclosure tăng |
| JFR luôn hiện diện trong mọi custom runtime `jlink` | Không nhất thiết; cần kiểm tra module/JVM capability |

## 20. Câu hỏi tự luyện tập có đáp án

**1.** `new Recording(Configuration.getConfiguration("default"))` tạo một recording đang chạy chưa?

**Đáp án:** Chưa. State ban đầu là `NEW`; phải gọi `start()` hoặc `scheduleStart(...)` để bắt đầu thu.

**2.** Khi nào chọn `new Recording()`, khi nào chọn `new Recording(default)`?

**Đáp án:** `new Recording()` phù hợp khi bạn muốn tự xây settings; `new Recording(default)` nạp bộ JFR settings được định nghĩa sẵn của JVM rồi có thể tinh chỉnh.

**3.** Nếu recording đang `RUNNING`, `dump(path)` có dừng việc thu sự kiện không?

**Đáp án:** Không. Nó xuất dữ liệu hiện có và recording vẫn `RUNNING` nếu không có hành động/điều kiện khác làm thay đổi state.

**4.** `copy(true)` làm gì?

**Đáp án:** Tạo một clone với ID riêng rồi dừng clone ngay. Không tự dừng original; clone nên được `close` sau khi dump.

**5.** Sau `stop()` mà chưa đặt `setDestination`, muốn lưu file phải làm gì?

**Đáp án:** Gọi `dump(path)` khi recording còn giữ dữ liệu ở `STOPPED`, sau đó `close()`.

**6.** Vì sao `stop()` sau khi `setDestination(path)` có thể cho state `CLOSED`?

**Đáp án:** API tự chép dữ liệu đến destination và đóng recording sau export thành công.

**7.** `scheduleStart(Duration.ofSeconds(5))` gọi trên `STOPPED` có hợp lệ không?

**Đáp án:** Không. Theo API, chỉ gọi khi recording còn ở state `NEW`.

**8.** `setDuration(Duration.ofSeconds(30))` có đo 30 giây từ lúc constructor không?

**Đáp án:** Không. Nó là thời lượng bản ghi hoạt động sau khi bắt đầu, nên khác delay trước start.

**9.** Vì sao nên đặt `setMaxAge` và `setMaxSize`?

**Đáp án:** Để giới hạn lịch sử và dung lượng dữ liệu disk-backed được giữ lại, tránh repository tăng không kiểm soát khi ghi lâu.

**10.** `getSize()==0` có chứng minh recording không có event nào?

**Đáp án:** Không. Recording không dùng disk có thể trả 0 bất kể dữ liệu trong memory buffers; giá trị cập nhật theo flush.

**11.** `recording.enable("jdk.CPULoad")` có tự tạo một CPU event ngay không?

**Đáp án:** Không. Nó bật thu loại event; thời điểm/số lượng events phụ thuộc bộ phát và cấu hình sampling.

**12.** Với custom event rất ngắn, vì sao dùng `withoutThreshold()`?

**Đáp án:** Để không loại các events có duration nhỏ hơn ngưỡng, giúp fixture đơn giản quan sát được events chủ động phát.

**13.** Có thể thay đổi map do `getSettings()` trả về rồi coi là recording đã đổi ngay không?

**Đáp án:** Không. Cần `setSettings(map)`, và nhớ `setSettings` thay thế toàn bộ settings.

**14.** Tại sao `RecordingFile.readAllEvents(path)` không phù hợp file vài GB?

**Đáp án:** Nó materialize toàn bộ events vào `List` và gây áp lực heap. Sử dụng `RecordingFile` iterator cho file lớn.

**15.** Có thể đọc custom field `taskId` bằng `RecordedEvent.getInt("taskId")` khi event được định nghĩa như ví dụ không?

**Đáp án:** Có. Field name và kiểu phải trùng schema của `demo.WorkUnit`.

**16.** `Recording.close()` có cho phép start lại object đã closed không?

**Đáp án:** Không. Sau `CLOSED`, tài nguyên bị giải phóng; tạo recording mới.

**17.** Nếu cần ghi dữ liệu trong 30 giây rồi tự stop, API nào phù hợp?

**Đáp án:** `setDuration(Duration.ofSeconds(30))` trước `start()`; muốn tự xuất file khi dừng thì đặt `setDestination(path)` trước.

**18.** Khi muốn xem tất cả recordings trong cùng JVM, dùng API nào?

**Đáp án:** `FlightRecorder.getFlightRecorder().getRecordings()`; không phải phương thức để truy cập recordings ở JVM khác.

**19.** Vì sao phải xác thực admin endpoint có quyền dump file JFR?

**Đáp án:** File có thể chứa thông tin runtime/ứng dụng nhạy cảm và thao tác xuất/thu event tiêu thụ resources; cần authentication, authorization, audit và quota.

**20.** Có phải tất cả các build Java 11 đều chứa JFR runtime?

**Đáp án:** Không được giả định mọi custom image/JVM đều có module và khả năng này. Dùng `FlightRecorder.isAvailable()` và xử lý trạng thái không hỗ trợ.

**21.** `setToDisk(false)` có làm `getStream(start,end)` luôn cung cấp JFR stream không?

**Đáp án:** Không. Javadoc ghi stream có thể `null` khi recording không disk-backed.

**22.** `RecordingFile` có phải nơi quản lý live recording lifecycle không?

**Đáp án:** Không. `RecordingFile` đọc file đã export; `Recording` quản lý thu/dump/close trong JVM.

**23.** Hai recordings trong cùng JVM có thể khác enabled event settings không?

**Đáp án:** Có. Mỗi recording có settings riêng, dù hạ tầng JFR runtime chung. Đừng cho rằng disable một event ở recording A đồng nghĩa không recording B nào ghi nó.

**24.** `setDumpOnExit(true)` có phải giải pháp lưu JFR chắc chắn khi app mất điện không?

**Đáp án:** Không. Nó là chính sách dump khi JVM exit theo khả năng của runtime; crash/forced termination/disk failure có thể làm mất artifact.

## 21. Thực hành mở rộng

### Bài tập A: chỉ thu sự kiện nghiệp vụ

Đổi constructor trong chương trình 1 từ `new Recording(Configuration.getConfiguration("default"))` thành `new Recording()`, giữ `recording.enable(WorkUnit.class)`. Quan sát khác biệt tổng số events trong file, nhưng vẫn filter `demo.WorkUnit` để kiểm tra nghiệp vụ.

**Mục đích:** thấy sự khác nhau giữa event settings được khai báo tường minh với predefined JFR configuration. Không diễn giải kết quả trên một JVM duy nhất thành “danh sách events bắt buộc của mọi version”.

### Bài tập B: thay đổi threshold

Sửa:

```java
recording.enable(WorkUnit.class)
        .withThreshold(Duration.ofSeconds(1));
```

Trong fixture hiện tại `recordTask` có duration gần như tức thì, nên số custom events có thể về 0. Sau đó dùng `withoutThreshold()` để quan sát lại. Đừng thêm `Thread.sleep` dài vào code production chỉ để ép tạo JFR event; hãy dùng một fixture có work thật.

### Bài tập C: giữ file cuối thay vì xóa

Thay block cleanup của chương trình để chỉ xóa files theo chính sách được chọn. Đặt tên file gồm service và timestamp **không chứa secrets**. Dùng `jfr print --events demo.WorkUnit final.jfr` để xem event fields. Sau đó xóa artifact an toàn khi bài thực hành hoàn tất.

### Bài tập D: xuất snapshot theo cảnh báo

Mô phỏng một cảnh báo latency và gọi `recording.dump(snapshotPath)` khi recording còn `RUNNING`. Kiểm tra trạng thái trước/sau. Giữ số snapshot có giới hạn, tránh dump mỗi vài mili giây.

### Bài tập E: kiểm tra state/return value sau destination

Trong chương trình 2, thử gọi `r.dump(otherPath)` ngay sau `r.stop()` khi đã `setDestination(file)`. Quan sát điều kiện lỗi theo Javadoc/runtime rồi sửa code bằng cách chọn **một trong hai chiến lược export**. Chỉ chạy trong môi trường test.

## 22. Tài liệu chính thức còn hiệu lực

- [Oracle Java SE 11 — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): constructor, lifecycle, `start`, `stop`, `close`, `dump`, `copy`, `setDestination`, `setDuration`, `setMaxAge`, `setMaxSize` và các getters.
- [Oracle Java SE 25 — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html): xác nhận các thao tác Recording vẫn được hỗ trợ trên JDK hiện hành.
- [Oracle Java SE 11 — `RecordingState`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/RecordingState.html): `NEW`, `DELAYED`, `RUNNING`, `STOPPED`, `CLOSED`.
- [Oracle Java SE 11 — `Configuration`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Configuration.html): cấu hình `default`/`profile`, `getConfigurations` và đọc file `.jfc`.
- [Oracle Java SE 11 — `EventSettings`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): threshold, period, stack trace và custom settings.
- [Oracle Java SE 11 — `Event`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html): `begin`, `end`, `commit`, `shouldCommit`.
- [Oracle Java SE 11 — `FlightRecorder`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/FlightRecorder.html): `isAvailable`, `getRecordings`, `takeSnapshot` và quản lý recorder.
- [Oracle Java SE 11 — `RecordingFile`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): `readAllEvents`, `readEvent`, `hasMoreEvents`, cảnh báo chỉ đọc file từ nguồn tin cậy.
- [Oracle Java SE 11 — `RecordedEvent`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): truy xuất fields, duration, thread và metadata.
- [Oracle JDK 17 — `jfr` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): kiểm tra recordings bằng lệnh `jfr print`/`jfr summary` từ công cụ JDK, không cần một runtime API khác trong bài.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): đưa Flight Recorder vào OpenJDK 11 và mô tả cơ chế chẩn đoán vẫn hiện diện ở các bản mới.

**Tóm tắt thực hành:** tạo `Recording` → cấu hình events và retention → `start()`/`scheduleStart()` → phát/workload events → `dump()` khi cần snapshot → `stop()` → `dump()` nếu chưa tự export bằng `setDestination` → `close()`. JFR có thể điều khiển ngay bằng Java code; để triển khai lâu dài cần quản lý trạng thái, tránh mất dữ liệu do close sớm, tránh repository tăng không giới hạn và bảo vệ file `.jfr` như một diagnostic artifact nhạy cảm.