# 16.1 Điều khiển Recording và Configuration qua API jdk.jfr

## Mục tiêu học tập và phạm vi

Java Flight Recorder (**JFR**) là cơ chế ghi sự kiện chẩn đoán của JVM và ứng dụng Java. Ngoài cách điều khiển bằng lệnh `jcmd` hay cờ khởi động, Java cung cấp module chuẩn **`jdk.jfr`** để chương trình **chọn cấu hình, bắt đầu, dừng, xuất và quản lý vòng đời bản ghi** ngay trong tiến trình của nó.

Sau bài này, bạn có thể:

- Phân biệt vai trò **`Configuration`**, **`Recording`**, **`EventSettings`** và **`FlightRecorder`**; không nhầm file cấu hình `.jfc` với bản ghi `.jfr`.
- Tạo một recording từ preset `default`, `profile` hoặc tệp `.jfc` riêng, rồi tinh chỉnh một event cụ thể.
- Sử dụng đúng `start()`, `scheduleStart()`, `stop()`, `dump()`, `setDestination()` và `close()`; phân biệt các trạng thái vòng đời.
- Thiết lập retention `setToDisk()`, `setMaxAge()`, `setMaxSize()`, thời lượng và vị trí tệp với ý thức về chi phí/giới hạn.
- Viết chương trình Java 17+ tự ghi sự kiện, tạo file `.jfr`, đọc lại kết quả và xử lý các lỗi thường gặp.
- Đưa JFR vào quy trình chẩn đoán có giới hạn tài nguyên, quyền truy cập và khả năng kiểm chứng.

**Giới hạn kỹ thuật:** ví dụ dùng API có mặt từ JDK 17 và được biên dịch với `javac --release 17`; một lần chạy kiểm thử thực tế dùng HotSpot JDK 24. Tham số event và preset có thể khác theo bản JDK/implementation. JFR phải có sẵn trong JVM; `FlightRecorder.isAvailable()` cho biết khả năng sử dụng trong tiến trình hiện tại. Mọi kết luận về thời gian chạy/CPU cần đo trong workload thật.

## 1. Kiến trúc của việc điều khiển JFR bằng Java

Các lớp quan trọng:

| API | Nhiệm vụ | Dùng khi nào |
| --- | --- | --- |
| `jdk.jfr.Configuration` | Chứa metadata và bản đồ các event settings của một preset hoặc tệp `.jfc` | Nạp cấu hình `default`, `profile` hay `custom.jfc` |
| `jdk.jfr.Recording` | Một đối tượng quản lý một lần ghi; cấu hình, start, stop, dump, close | Điều khiển phiên ghi bằng logic ứng dụng |
| `jdk.jfr.EventSettings` | Chỉnh cài đặt một event trong recording, dùng fluent API | `enable`, `withThreshold`, `withPeriod`, `withStackTrace` |
| `jdk.jfr.FlightRecorder` | Thông tin/điều khiển mức JVM, như `isAvailable()`, danh sách event types và recordings | Kiểm tra JVM và introspection |
| `jdk.jfr.RecordingState` | Enum các trạng thái của `Recording` | Bảo đảm gọi phương thức hợp lệ theo vòng đời |
| `jdk.jfr.Event`, `@Name`, `@Label` | Định nghĩa một loại JFR event của ứng dụng | Ghi điểm mốc nghiệp vụ/đoạn xử lý |
| `jdk.jfr.consumer.RecordingFile` | Đọc các sự kiện đã ghi từ file `.jfr` | Kiểm tra, phân tích sau khi xuất file |

**Cấu hình** chỉ là mô tả loại sự kiện và cách thu. **Recording** là phiên đo đang/chưa chạy, có ID, trạng thái, giới hạn và dữ liệu riêng. Một `Configuration` có thể được dùng để tạo nhiều `Recording`. File `.jfc` là XML cấu hình, còn file `.jfr` là kết quả ghi nhị phân và phải được xem bằng công cụ hỗ trợ.

Sơ đồ điều khiển:

~~~text
Configuration.getConfiguration("default") / "profile"
                  hoặc
           Configuration.create(pathToJfc)
                         |
                         v
                  new Recording(config)
                         |
              chỉnh settings/retention
                         |
                      start()
                         |
                 JVM phát JFR events
                         |
           dump() khi đang chạy (snapshot)
                         |
                      stop()
                         |
             dump() khi STOPPED + toDisk
                         |
                      close()
                         |
              đọc file .jfr bằng JMC
        hoặc jfr / RecordingFile
~~~

Có thể dùng `jcmd <pid> JFR.start` từ bên ngoài hoặc dùng `new Recording(...)` từ trong ứng dụng; cả hai điều khiển cơ chế JFR của **cùng JVM**, nhưng đối tượng Java `Recording` chỉ được ứng dụng sở hữu vòng đời qua API. JFR không phải thư viện bên thứ ba cần thêm dependency Maven trong JDK chuẩn có module `jdk.jfr`.

## 2. Nạp cấu hình bằng `Configuration`

### 2.1 Chọn preset tích hợp

~~~java
import jdk.jfr.Configuration;

Configuration lowOverhead = Configuration.getConfiguration("default");
Configuration profiling = Configuration.getConfiguration("profile");
~~~

Hai lệnh trên là **đoạn mã trong phương thức** có xử lý/khai báo `throws Exception`; không phải chương trình Java độc lập. `getConfiguration(String)` đọc preset theo tên và có thể ném `IOException`, `ParseException`. `default` thường phù hợp ghi nền với chi phí thấp hơn; `profile` thường tăng lượng dữ liệu phục vụ profiling trong cửa sổ giới hạn. Đừng suy luận chắc chắn sự kiện nào được bật chỉ từ tên preset: kiểm tra bản JDK thực tế.

Có thể liệt kê những preset JVM cung cấp:

~~~java
for (Configuration c : Configuration.getConfigurations()) {
    System.out.println(c.getName() + " - " + c.getLabel());
}
~~~

Đây cũng là **snippet** đặt trong phương thức Java; số lượng/tên preset không nên hard-code. Ngoài `getName()`, một `Configuration` cung cấp `getLabel()`, `getDescription()`, `getProvider()`, `getContents()` và `getSettings()` để kiểm tra xuất xứ/cài đặt.

### 2.2 Đọc tệp `.jfc` riêng

~~~java
import java.nio.file.Path;
import jdk.jfr.Configuration;

Configuration custom = Configuration.create(Path.of("custom.jfc"));
~~~

`Configuration.create(Path)` phân tích tệp cấu hình JFR; cần đường dẫn hợp lệ, tệp có quyền đọc và nội dung XML đúng định dạng. Nếu không đọc/parse được, chương trình có thể nhận `IOException` hoặc `ParseException`; nên xử lý để công cụ chẩn đoán không làm hỏng logic nghiệp vụ.

Đừng sửa trực tiếp `default.jfc` hoặc `profile.jfc` nằm trong JDK. Khi cần sửa, tạo bản `custom.jfc` riêng bằng JMC hoặc công cụ `jfr configure`, lưu kèm ứng dụng/phiên bản JDK được kiểm thử.

### 2.3 `getSettings()` là bản đồ mô tả, không phải điều khiển trực tiếp

Mỗi setting có khóa dạng:

~~~text
<event-name>#<setting-name> = <value>

jdk.JavaMonitorEnter#enabled = true
jdk.JavaMonitorEnter#threshold = 5 ms
jdk.ExecutionSample#period = 20 ms
~~~

Đây là ví dụ cú pháp, không khẳng định mọi event đều có mọi setting. Mức event là tên đủ điều kiện như `jdk.JavaMonitorEnter`; phần sau `#` là `enabled`, `threshold`, `stackTrace`, `period` hoặc setting được loại event đó hỗ trợ.

**Bẫy quan trọng:** sửa nội dung `Configuration.getSettings()` **không tự làm thay đổi** `Configuration` ban đầu; sửa bản `Recording.getSettings()` **không tự áp dụng** vào recording. Muốn tạo cài đặt mới, hãy lấy bản copy map, thay giá trị và dùng `new Recording(map)` hoặc `recording.setSettings(map)`. `setSettings(...)` **thay thế toàn bộ** tập settings hiện tại; nếu truyền map chỉ có một khóa, có thể làm mất các thiết lập khác của preset.

Trong trường hợp chỉ sửa một event, API `Recording.enable(...)` và `EventSettings` thường rõ ràng hơn.

## 3. Ba cách tạo `Recording` và ý nghĩa khác nhau

~~~java
import java.util.Map;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

Recording empty = new Recording();              // Chưa có event settings từ preset.
Recording fromPreset = new Recording(
        Configuration.getConfiguration("default"));
Recording fromMap = new Recording(Map.of(
        "jdk.CPULoad#enabled", "true",
        "jdk.CPULoad#period", "1 s"));
~~~

Đây là **snippet minh họa**; mỗi đối tượng `Recording` cần được quản lý và `close()` sau khi dùng, tốt nhất bằng `try-with-resources`.

- `new Recording()` không tự có một bộ settings mặc định giống `default.jfc`; chọn preset cụ thể sẽ dễ dự đoán dữ liệu hơn.
- `new Recording(Configuration)` khởi tạo settings từ template có thể kiểm chứng.
- `new Recording(Map<String,String>)` cho phép chỉ định bản đồ cài đặt ngay từ đầu; tránh bỏ sót các event quan trọng khi tự tạo map quá tối giản.

Một JVM có thể có nhiều recordings. Mỗi recording có `getId()` riêng, còn `setName(...)` đặt tên phục vụ thao tác/quan sát; tên không phải ID duy nhất toàn JVM. Nhiều recording có thể cùng ghi một loại event, và cơ chế JFR/instrumentation vẫn sử dụng tài nguyên JVM; đừng giả định chi phí hoàn toàn độc lập giữa các phiên.

## 4. Vòng đời của `Recording`: NEW → RUNNING → STOPPED → CLOSED

| Trạng thái | Đặc điểm | Hành động thường dùng |
| --- | --- | --- |
| `NEW` | Đã tạo đối tượng, chưa bắt đầu thu | Chọn settings, retention, tên, đường dẫn; `start()` |
| `DELAYED` | Đã gọi `scheduleStart(delay)`, chờ thời điểm bắt đầu | Đợi JVM chuyển sang RUNNING; tránh đóng trước lịch |
| `RUNNING` | Đang ghi các event theo settings của recording | Kiểm tra state/timestamp, `dump(path)` snapshot, hoặc `stop()` |
| `STOPPED` | Đã dừng ghi; không thể khởi động lại recording này | `dump(path)` nếu recording được ghi ra disk repository; `close()` |
| `CLOSED` | Đã giải phóng dữ liệu gắn với recording | Không thể dump/restart; tạo recording mới nếu cần |

Cách điều khiển thông dụng:

~~~java
try (Recording recording = new Recording(
        Configuration.getConfiguration("default"))) {
    recording.setName("payment-diagnostics");
    recording.start();
    // Thực hiện workload cần đo.
    recording.stop();
    recording.dump(Path.of("payment-diagnostics.jfr"));
}
~~~

Ví dụ này là **snippet** dùng `Path`, `Recording`, `Configuration` trong một phương thức xử lý exception; ví dụ Java độc lập đầy đủ nằm ở phần 7.

Hành vi cần nhớ:

1. `start()` bắt đầu recording từ trạng thái thích hợp. Gọi `start()` lần thứ hai lên recording đã dừng **không restart được**; tạo đối tượng mới để ghi phiên khác.
2. `scheduleStart(Duration.ofSeconds(10))` đặt lịch bắt đầu sau khoảng trễ. Đối tượng có thể ở `DELAYED`; nếu `close()` trước lúc bắt đầu, phiên đo không ghi được dữ liệu mong đợi.
3. `stop()` kết thúc thu. Nếu recording có `setDestination(path)`, khi stop thành công JFR **ghi file và tự đóng** recording; không gọi thêm `dump()` sau đó.
4. `dump(path)` ghi snapshot ra tệp. Nó có thể hoạt động **khi RUNNING**, hoặc khi `STOPPED` mà recording đã ghi vào disk repository (`setToDisk(true)`). Sau `CLOSED`, dữ liệu đã bị giải phóng nên không thể dump.
5. `close()` giải phóng dữ liệu và tài nguyên recording; nếu chưa dump/ghi bằng destination, dữ liệu có thể không còn để truy xuất. `try-with-resources` giúp dọn tài nguyên ngay cả khi có exception.

**Khác nhau giữa `stop()` và `close()`:** `stop()` chỉ kết thúc việc ghi (trừ trường hợp tự đóng do destination); `close()` giải phóng dữ liệu của recording. Đừng đóng ngay sau `stop()` mà chưa lưu file nếu cần điều tra sau này.

### 4.1 Hai chiến lược xuất file: chọn một cho rõ

**A. Xuất chủ động bằng `dump()`:** không đặt destination, ghi xong gọi `stop()`, sau đó `dump(...)` rồi `close()`. Đây là cách của ví dụ chạy được. Nếu đang RUNNING và muốn snapshot để điều tra mà tiếp tục thu, có thể gọi `dump(...)` mà không stop.

**B. Xuất tự động tại lúc stop:**

~~~java
try (Recording recording = new Recording(
        Configuration.getConfiguration("default"))) {
    recording.setDestination(Path.of("automatic-at-stop.jfr"));
    recording.start();
    // Workload nằm ở đây.
    recording.stop();  // JFR ghi tới destination và tự đóng recording.
}
~~~

Đoạn này là snippet, không độc lập. Không trộn hai phương án theo cách `setDestination(...)` rồi `stop()` rồi `dump()`: trong tình huống destination được ghi thành công, đối tượng đã `CLOSED` nên dump sau stop là sai vòng đời.

### 4.2 Đo theo thời lượng và lịch

- `recording.setDuration(Duration.ofMinutes(1))` cho phép JFR tự dừng sau khoảng thời gian ghi; phải giữ recording còn sống đủ lâu. Việc chỉ `setDuration(...)` không tự bảo đảm đã có file lưu nếu bạn không đặt destination/dump đúng lúc.
- `recording.scheduleStart(Duration.ofSeconds(10))` lập lịch bắt đầu trong tương lai; dùng khi muốn đo cửa sổ có chủ đích.
- `recording.getStartTime()`, `getStopTime()`, `getState()` cho metadata vòng đời; các thời điểm có thể `null` trước khi sự kiện tương ứng diễn ra.
- Không dùng sleep tùy tiện trong đường xử lý request chỉ để chờ `setDuration`; nếu ghi bất đồng bộ, thiết kế ownership và phối hợp lúc dừng/đóng theo vòng đời ứng dụng.

## 5. Quản lý repository, retention và dung lượng

Một `Recording` có thể ghi qua disk repository hoặc bị giới hạn vào bộ đệm trong bộ nhớ:

| Phương thức | Ý nghĩa | Cẩn trọng |
| --- | --- | --- |
| `setToDisk(true)` | Cho phép JVM flush dữ liệu recording vào disk repository; đây cũng là chế độ mặc định nếu không đổi | Cần đủ dung lượng disk, kiểm soát retention |
| `setToDisk(false)` | Dữ liệu bị giới hạn bởi memory buffers, phù hợp trường hợp đặc biệt ngắn hạn | Có thể mất dữ liệu cũ; stop rồi dump không giống chế độ to-disk |
| `setMaxAge(Duration)` | Chỉ giữ dữ liệu gần đây trong khoảng thời gian chỉ định, ở disk repository | Hết hạn sẽ bị loại; không bảo đảm có lịch sử xa hơn |
| `setMaxSize(long bytes)` | Giới hạn dung lượng giữ trên disk repository | Khi vượt, JVM loại chunk cũ; đơn vị là **byte** |
| `setDestination(Path)` | Ghi ra file **khi stop** và tự close sau khi ghi thành công | Đường dẫn phải ghi được, không dump lại sau auto-close |
| `setDumpOnExit(true)` | Yêu cầu dump khi JVM kết thúc | Không thay cho kế hoạch quản lý file, path và lỗi khi thoát bất thường |
| `getSize()` | Số byte recording trong disk repository tại thời điểm JVM đã flush | Có thể bằng 0 với recording chỉ dùng memory hoặc chưa flush; không phải kích thước heap |
| `dump(Path)` | Ghi snapshot ra file theo state hợp lệ | Có I/O và cần đường dẫn hợp lệ; tránh request đồng thời ghi cùng tên file |

Ví dụ cấu hình retention thực tế:

~~~java
recording.setName("api-observation");
recording.setToDisk(true);
recording.setMaxAge(Duration.ofMinutes(5));
recording.setMaxSize(64L * 1024 * 1024);  // 64 MiB
~~~

Đây là **snippet** dùng trên recording trước khi chạy. Với 5 phút và 64 MiB, phần dữ liệu có thể bị loại khi **một trong hai giới hạn** khiến cần dọn các chunk cũ. Bản ghi không nhất thiết giữ được đủ 5 phút nếu event rate cao.

`setDumpOnExit(true)` chỉ có ý nghĩa trong các điều kiện JVM thoát và cơ chế dump có thể thực thi; không nên dựa vào nó khi process bị kill cưỡng bức, OOM kill hoặc crash nặng. Cấu hình đường dẫn, ghi nhận quyền truy cập và xem xét dữ liệu nhạy cảm trong event trước khi tự động lưu file vào nơi dùng chung.

## 6. Điều chỉnh sự kiện bằng `EventSettings` và `setSettings`

### 6.1 Chỉ bật/tắt đúng event cần quan sát

~~~java
recording.enable("jdk.JavaMonitorEnter")
        .withThreshold(Duration.ofMillis(5))
        .withStackTrace();

recording.enable("jdk.CPULoad")
        .withPeriod(Duration.ofSeconds(1));

recording.disable("jdk.JavaExceptionThrow");
~~~

Đây là **snippets** với `Duration` và `recording` có sẵn. `enable(String)`/`disable(String)` nhận tên event; `enable(Class<? extends Event>)` dành cho event class, thích hợp khi một event được nạp bởi nhiều class loader và bạn cần chọn chính xác class. Phương thức `enable` trả `EventSettings` để nối các lời gọi.

Các mức cài đặt:

- **`enabled`**: thu hoặc bỏ một loại event. Khi ghi nhiều recordings, chi phí JVM có thể vẫn chịu ảnh hưởng của những recording khác có bật event đó.
- **`withThreshold(Duration)` / `withoutThreshold()`**: dùng với event có duration/threshold phù hợp. Giảm threshold có thể tăng lượng event và overhead rất mạnh.
- **`withPeriod(Duration)`**: dùng với event hỗ trợ periodic/sampling, như `jdk.CPULoad`. Không áp cho mọi event.
- **`withStackTrace()` / `withoutStackTrace()`**: quyết định có yêu cầu stack của event phù hợp; tăng thông tin chẩn đoán nhưng có chi phí.
- **`with(String name, String value)`**: dùng khi event có setting cụ thể không có convenience method; tên và value phải đúng định dạng mà event chấp nhận.

Đừng đoán mọi event đều có `threshold`, `period` hay `stackTrace`. Có thể hỏi chính JVM đang chạy:

~~~java
import jdk.jfr.EventType;
import jdk.jfr.FlightRecorder;
import jdk.jfr.SettingDescriptor;

for (EventType type : FlightRecorder.getFlightRecorder().getEventTypes()) {
    if (type.getName().equals("jdk.JavaMonitorEnter")) {
        for (SettingDescriptor setting : type.getSettingDescriptors()) {
            System.out.println(setting.getName()
                    + " = " + setting.getDefaultValue());
        }
    }
}
~~~

Đoạn trên thuộc một phương thức có khai báo exception nếu cần; chỉ in setting descriptors của event tồn tại trên JVM hiện tại. Nếu danh sách rỗng, kiểm tra tên event, trạng thái khởi tạo/đăng ký và implementation. Event names và settings có thể tiến hóa giữa các JDK.

### 6.2 Giữ nguyên preset khi chỉ muốn ghi đè vài khóa

Khi cần chỉnh nhiều khóa một cách nhất quán, hãy **sao chép toàn bộ map của preset** rồi sửa trước khi khởi tạo:

~~~java
import java.util.HashMap;
import java.util.Map;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

Configuration original = Configuration.getConfiguration("default");
Map<String, String> tuned = new HashMap<>(original.getSettings());
tuned.put("jdk.JavaMonitorEnter#enabled", "true");
tuned.put("jdk.JavaMonitorEnter#threshold", "5 ms");

try (Recording recording = new Recording(tuned)) {
    // Sử dụng recording theo vòng đời ở phần 4.
}
~~~

Đây là snippet, cần đặt trong phương thức `throws Exception` hoặc bắt ngoại lệ. Ví dụ Java độc lập đầy đủ và stdout kiểm chứng ở phần 8. `new Recording(tuned)` nhận toàn bộ settings, bao gồm các khóa default không bị đổi.

Nếu đã tạo recording và cần cập nhật cả map:

~~~java
Map<String, String> merged = new HashMap<>(recording.getSettings());
merged.put("jdk.JavaMonitorEnter#threshold", "5 ms");
recording.setSettings(merged);
~~~

**Lưu ý:** `setSettings(merged)` thay **toàn bộ** settings của recording. Không truyền chỉ `Map.of("jdk.JavaMonitorEnter#threshold", "5 ms")` rồi kỳ vọng những setting mặc định còn lại nguyên vẹn. Khi muốn chỉnh một event, `recording.enable(...).withThreshold(...)` thường ít gây sai hơn.

### 6.3 Event có tên trùng giữa class loaders

`Recording.enable("my.app.WorkEvent")` áp dụng cho mọi event khớp tên đó. Một ứng dụng plugin có thể nạp nhiều class cùng `@Name` qua nhiều class loader; khi cần chọn một định nghĩa cụ thể, sử dụng `enable(MyEvent.class)` hoặc event type ID theo metadata hiện tại của JVM. Đừng đem event ID từ lần chạy/JVM khác sang vì ID không ổn định giữa các JVM.

## 7. Ví dụ Java 17+ hoàn chỉnh: cấu hình → Recording → file `.jfr` → kiểm chứng

Ví dụ tự tạo 3 event hoạt động của ứng dụng. Nó chọn `default` theo mặc định, có thể chọn `profile` hoặc tệp custom bằng đối số CLI, sau đó ghi file và đọc lại bằng `RecordingFile`.

Lưu tệp đúng tên **RecordingApiDemo.java**:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;

public final class RecordingApiDemo {
    @Name("training.WorkUnit")
    @Label("Work unit")
    @Category({"Training", "Diagnostics"})
    static final class WorkUnit extends Event {
        @Label("Task")
        String task;

        @Label("Items")
        int items;
    }

    public static void main(String[] args) throws Exception {
        if (!FlightRecorder.isAvailable()) {
            System.out.println("JFR_UNAVAILABLE");
            return;
        }

        String choice = args.length == 0 ? "default" : args[0];
        Configuration configuration = choice.endsWith(".jfc")
                ? Configuration.create(Path.of(choice))
                : Configuration.getConfiguration(choice);
        Path output = Path.of("programmatic.jfr");

        try (Recording recording = new Recording(configuration)) {
            recording.setName("learning-api");
            recording.setToDisk(true);
            recording.setMaxAge(Duration.ofMinutes(5));
            recording.setMaxSize(64L * 1024 * 1024);
            recording.enable(WorkUnit.class)
                    .withoutThreshold()
                    .withStackTrace();

            recording.start();
            for (int i = 1; i <= 3; i++) {
                WorkUnit event = new WorkUnit();
                event.task = "batch-" + i;
                event.items = i * 10;
                event.begin();
                Thread.sleep(12);
                event.end();
                if (event.shouldCommit()) {
                    event.commit();
                }
            }
            recording.stop();
            recording.dump(output);
            System.out.println("state=" + recording.getState());
        }

        long count = RecordingFile.readAllEvents(output).stream()
                .filter(e -> e.getEventType().getName()
                        .equals("training.WorkUnit"))
                .count();
        System.out.println("workEvents=" + count);
    }
}
~~~

Biên dịch và chạy ở thư mục có quyền ghi:

~~~sh
javac --release 17 RecordingApiDemo.java
java RecordingApiDemo
jfr summary programmatic.jfr
jfr print --events training.WorkUnit programmatic.jfr
~~~

**Stdout do chính chương trình Java in** (khi JFR khả dụng và file tạo thành công):

~~~text
state=STOPPED
workEvents=3
~~~

Trong file, ba event có tên `training.WorkUnit`, trường `task` lần lượt `batch-1`, `batch-2`, `batch-3` và `items` lần lượt 10, 20, 30. Thời điểm, duration và stack trace phụ thuộc runtime; không hard-code các giá trị đó. Mỗi sự kiện dùng `begin()` và `end()` để đo duration; `shouldCommit()` kiểm tra event có thỏa điều kiện và enabled/threshold tại lúc đó hay không; `commit()` thực sự gửi event cho JFR.

Ví dụ đã được biên dịch bằng `javac --release 17` và chạy trên HotSpot JDK 24. Cả `java RecordingApiDemo default` và `java RecordingApiDemo profile` đều in hai dòng ở trên và file `.jfr` có đúng 3 event `training.WorkUnit`. Nếu JFR không khả dụng, nhánh `JFR_UNAVAILABLE` là kết quả hợp lệ khác; nếu thiếu quyền ghi/không có preset/tệp cấu hình, chương trình ném exception thay vì in hai dòng thành công.

### 7.1 Vì sao chỉ chỉnh event riêng mà không tạo map mới?

`new Recording(configuration)` giữ settings nền của `default`/`profile`. `recording.enable(WorkUnit.class).withoutThreshold().withStackTrace()` chỉ điều chỉnh loại event ứng dụng cần cho thí nghiệm. Vì vậy không vô tình xóa các event GC/CPU/thread của preset như khi gọi `setSettings` với map bị thiếu.

### 7.2 Dùng cấu hình `profile` hoặc custom `.jfc`

~~~sh
# Chọn profile tích hợp:
java RecordingApiDemo profile

# Tạo một .jfc riêng dựa trên default, tăng thông tin contention:
jfr configure --input default.jfc --output custom.jfc 'jdk.JavaMonitorEnter#enabled=true' 'jdk.JavaMonitorEnter#threshold=5ms'

# Nạp tệp vừa tạo qua Configuration.create(Path):
java RecordingApiDemo custom.jfc
~~~

Mỗi lần chạy sẽ ghi tới đường dẫn `programmatic.jfr` cố định trong ví dụ. Nếu muốn lưu nhiều kết quả để so sánh, hãy copy/đổi tên file đã ghi trước lần chạy tiếp theo hoặc sửa chương trình để đặt tên kết quả riêng. Cấu hình `custom.jfc` của JDK cần có file ở working directory tương ứng; đường dẫn tương đối không tự đồng bộ giữa container/host.

Lệnh `jfr configure` và việc nạp custom file đã được kiểm tra trên JDK 24. Nếu công cụ/phiên bản JDK khác, kiểm tra `jfr help configure`, nội dung `custom.jfc` và danh sách preset trước khi chạy.

### 7.3 Tại sao `RecordingFile.readAllEvents` chỉ thích hợp demo nhỏ?

Hàm này đưa mọi event của file vào bộ nhớ Java; file production có thể rất lớn. Khi phân tích recording lớn, dùng JMC, `jfr print` với filters hoặc mở `RecordingFile` và đọc tuần tự qua `hasMoreEvents()`/`readEvent()` rồi xử lý và đóng file. `RecordingFile` là **consumer**, không phải công cụ điều khiển lifecycle của `Recording` đang ghi.

## 8. Ví dụ hoàn chỉnh thứ hai: tinh chỉnh preset bằng map

Ví dụ dưới đây xác nhận rằng map được sao chép và truyền vào `Recording` có đúng cài đặt mong muốn, đồng thời không chỉnh sửa bản preset chuẩn.

Lưu tên **RecordingSettingsDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public final class RecordingSettingsDemo {
    public static void main(String[] args) throws Exception {
        Configuration original = Configuration.getConfiguration("default");
        Map<String, String> tuned = new HashMap<>(original.getSettings());
        tuned.put("jdk.JavaMonitorEnter#enabled", "true");
        tuned.put("jdk.JavaMonitorEnter#threshold", "5 ms");

        try (Recording recording = new Recording(tuned)) {
            System.out.println("name=" + original.getName());
            System.out.println("lockEnabled="
                    + recording.getSettings().get(
                            "jdk.JavaMonitorEnter#enabled"));
            System.out.println("lockThreshold="
                    + recording.getSettings().get(
                            "jdk.JavaMonitorEnter#threshold"));
        }
    }
}
~~~

Chạy:

~~~sh
javac --release 17 RecordingSettingsDemo.java
java RecordingSettingsDemo
~~~

Stdout (đã kiểm chứng):

~~~text
name=default
lockEnabled=true
lockThreshold=5 ms
~~~

Chương trình thứ hai **không start recording** và **không tạo file `.jfr`**, vì mục tiêu của nó chỉ là kiểm tra cấu hình. Tạo `Recording` và đọc settings không đồng nghĩa JVM đã ghi event. Để thực sự thu, phải `start()`, sinh workload, `stop()` và dump trước `close()`.

## 9. Những giới hạn cần biết khi điều khiển qua API

### 9.1 Cấu hình có thể khác nhau giữa recordings, nhưng JVM là tài nguyên chung

Mỗi recording có bộ settings và retention riêng. Tuy nhiên JFR vận hành bên trong một JVM: CPU cho event recording, bộ đệm, disk I/O, instrumentation và chi phí stack capture vẫn tác động lên workload. Nếu recording A bật stack trace cho event tần suất cao, recording B không có quyền “cách ly” ứng dụng khỏi overhead của A. Nên đặt ownership rõ ràng, tránh mở nhiều recordings trùng mục tiêu, đồng bộ tên/timestamp và đóng mọi recording không còn cần.

### 9.2 `Configuration` không phải tệp dữ liệu và không tự bắt đầu recording

`Configuration.getConfiguration("default")` chỉ đọc settings. `new Recording(configuration)` chỉ tạo đối tượng `NEW`. `recording.start()` mới thực sự cho phép thu. Ngay cả khi đã `start()`, thiếu event mục tiêu có thể do chưa xảy ra, event disabled, threshold cao, recording quá ngắn hoặc nguồn event chưa đăng ký. Không xem file `.jfr` rỗng event mục tiêu là bằng chứng lỗi không tồn tại.

### 9.3 Sự kiện custom và sự kiện JVM không có cùng đặc điểm

`Event` do ứng dụng tạo có thể chứa trường nghiệp vụ và duration do code xác định. `jdk.ExecutionSample` là lấy mẫu; `jdk.ObjectAllocationSample` cũng là sampling (kèm trọng số/semantics liên quan). `jdk.JavaMonitorEnter` ghi contention theo ngưỡng; `jdk.GarbageCollection` ghi các sự kiện GC. Đếm các event này không thể thay thế trực tiếp cho số lần gọi method, tổng byte cấp phát hay toàn bộ thời gian CPU. Phải đọc ý nghĩa event và cài đặt JDK cụ thể.

### 9.4 Đo trong code: quyền và dữ liệu nhạy cảm

Bản ghi có thể chứa tên thread, đường dẫn file, stack trace, argument/configuration hệ thống và trường custom của ứng dụng. Không nhét token, mật khẩu, payload cá nhân hoặc thông tin bí mật vào field JFR event. Chỉ cấp quyền khởi động/dump/đọc file cho người hoặc cơ chế vận hành đáng tin; tránh mở endpoint tự do cho khách hàng chọn bất kỳ path trên filesystem.

Ở service production, nên ràng buộc duration, maxsize/maxage, thư mục lưu, quyền truy cập và lưu dấu thời gian/PID/JDK/settings cho mỗi lần ghi. Cần kế hoạch dọn file cũ và cân nhắc tác động I/O; việc tích hợp API không khiến recording “miễn phí” về hiệu năng.

### 9.5 Xử lý lỗi mà không làm hỏng luồng nghiệp vụ

Các lỗi có thể gặp:

| Lỗi/dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `FlightRecorder.isAvailable() == false` | JVM không cung cấp hoặc vô hiệu hóa JFR | Bỏ qua tính năng chẩn đoán, thông báo rõ lý do |
| `IOException` hoặc `ParseException` lúc load `Configuration` | Preset/tệp `.jfc` không tồn tại, không đọc được, XML sai | Kiểm tra path/JDK; không tiếp tục với preset tưởng tượng |
| `IllegalStateException` khi start/stop/dump sai | Recording đã RUNNING/STOPPED/CLOSED hoặc gọi sai state | Kiểm tra `getState()` và thiết kế lifecycle duy nhất |
| `IOException` lúc `dump` | Đường dẫn không ghi được, thiếu disk, recording đã đóng, state không hợp lệ | Chọn output hợp lệ, bảo đảm quyền/dung lượng, log lỗi |
| File có ít hoặc không có event cần tìm | Chưa xảy ra sự kiện, threshold cao, recording quá ngắn, event không được bật | Đọc `getSettings()`, chạy workload đại diện, kiểm `jfr summary` |
| File quá lớn / latency tăng khi bật JFR | Event nhiều, stack trace nặng, retention chưa giới hạn | Thu ngắn hơn, chỉnh event/threshold, đặt `maxAge`/`maxSize` |
| Đã gọi `stop()` nhưng không có file | Chưa `dump(...)` hoặc chưa `setDestination(...)` | Dump khi STOPPED + toDisk trước khi close, hoặc đặt destination trước stop |
| `getSize() == 0` nhưng app có event | Recording dùng memory-only hoặc buffer chưa flush vào repository | Không xem getSize là số event; xem chế độ `isToDisk()`, dump và kiểm file |

Trong ứng dụng thật, có thể phân biệt lỗi chẩn đoán với lỗi nghiệp vụ: tính năng ghi JFR thường được quản lý riêng, không nên khiến request chính thất bại chỉ vì không ghi được file. Nhưng nếu chính thao tác “xuất recording” là yêu cầu của người vận hành, phải báo lỗi rõ ràng; không âm thầm nhận là đã dump thành công.

## 10. So sánh điều khiển JFR trong code với các cách khác

| Cách | Ưu điểm | Giới hạn và phạm vi |
| --- | --- | --- |
| `-XX:StartFlightRecording=...` khi tạo process | Ghi được startup và cấu hình hạ tầng ngoài code | Muốn thay đổi có thể phải đổi JVM flags/restart |
| `jcmd <pid> JFR.start/check/dump/stop` | Điều khiển từ bên ngoài khi JVM đang chạy và attach được | Cần quyền/PID/namespace phù hợp, thao tác ngoài ứng dụng |
| `jdk.jfr.Recording` | Tích hợp logic bắt đầu/dừng/xuất theo tình huống ứng dụng | Cần quản lý lifecycle, retention, quyền, lỗi I/O trong code |
| `jdk.jfr.consumer.RecordingStream` | Xử lý sự kiện trực tuyến qua callback | Là API consumer/streaming, không đồng nhất với vòng đời file `Recording` |
| `jdk.jfr.consumer.RecordingFile` | Đọc file `.jfr` sau khi thu | Không dùng để start/stop recording |

Ví dụ nghiệp vụ hợp lý: sau khi bộ giám sát nội bộ phát hiện tăng latency, chương trình kích hoạt **một** `Recording` trong 60 giây, thu event lock/CPU phù hợp, lưu file có tên duy nhất, rồi đóng. Nhưng API không tự biết “khi nào latency bất thường”: bạn phải có số liệu và trigger đáng tin, giới hạn tần suất kích hoạt để tránh vòng lặp recording.

## 11. Kịch bản triển khai có kiểm soát

Nếu muốn tích hợp trong service có nhiều request, hãy tách **diagnostic controller/service** khỏi handler nghiệp vụ nóng. Một thiết kế đơn giản:

1. Khởi tạo khi quản trị viên hoặc bộ giám sát hợp lệ yêu cầu; kiểm tra `FlightRecorder.isAvailable()`.
2. Chọn `Configuration` đúng nhu cầu và kiểm tra event settings trên JVM hiện tại.
3. Chặn yêu cầu trùng lặp hoặc đặt giới hạn số recording đồng thời; đặt tên/ID, thời gian bắt đầu, duration, maxage/maxsize và thư mục ghi được.
4. Gọi `start()` rồi tiếp tục xử lý workload; không giữ request HTTP chờ recording dài nếu không cần.
5. Khi cần snapshot, gọi `dump(path)` khi RUNNING; khi kết thúc, `stop()` rồi `dump(path)` nếu chọn chủ động, hoặc dùng `setDestination` trước stop cho luồng tự động.
6. `close()` trong `finally`/`try-with-resources`, lưu metadata recording (không lưu dữ liệu nhạy cảm), đối chiếu file thực sự tồn tại/đọc được bằng `jfr summary` hoặc JMC.
7. Thu dọn file cũ theo chính sách retention; so profile với mốc metric bên ngoài (CPU, GC, latency và workload) trước khi kết luận.

**Đừng tùy tiện lập lịch `setDuration` rồi đóng đối tượng ở cuối phương thức ngay lập tức.** Việc quản lý bất đồng bộ phải giữ `Recording` còn sống cho đến khi đã hoàn tất ghi và dump. Trong code ví dụ ở phần 7, toàn bộ vòng đời được đặt trong một `try-with-resources` đồng bộ để dễ quan sát.

## 12. Bài tập tư duy và đáp án

**Bài A — phân biệt cấu hình và recording.** Ứng dụng gọi `Configuration.getConfiguration("profile")` rồi `new Recording(config)` nhưng không gọi `start()`. JFR đã ghi chưa?

**Đáp án:** Chưa. Đối tượng ở `NEW`; muốn ghi phải `start()` và sinh event trong cửa sổ đã bật.

**Bài B — ghi mất dữ liệu.** Bạn gọi `start()` → `stop()` → `close()`, sau đó mới `dump(Path.of("x.jfr"))`. Kết quả?

**Đáp án:** Sai vòng đời. `close()` giải phóng dữ liệu recording, không còn dump được. Đối với recording to-disk, hãy dump sau stop nhưng **trước close**, hoặc đặt destination để tự ghi lúc stop.

**Bài C — ghi tự động.** Bạn đã `setDestination(Path.of("x.jfr"))` trước start, sau đó `stop()` thành công. Có cần gọi `dump()` nữa?

**Đáp án:** Không. Destination được ghi khi stop và recording tự đóng khi sao chép thành công. Gọi dump tiếp là lỗi.

**Bài D — đổi một setting.** Tại sao `recording.setSettings(Map.of("jdk.JavaMonitorEnter#threshold", "5 ms"))` dễ gây lỗi hơn `recording.enable("jdk.JavaMonitorEnter").withThreshold(Duration.ofMillis(5))`?

**Đáp án:** `setSettings` thay toàn bộ map; những setting khác của preset có thể bị mất. Fluent API chỉ chỉnh event đang nhắm tới. Nếu phải setSettings, sao chép map gốc rồi merge.

**Bài E — tệp không có CPU sample.** `jdk.ExecutionSample` không xuất hiện trong recording 80 ms. Có chứng minh không có CPU work không?

**Đáp án:** Không. Sampling phụ thuộc enabled/period/workload và thời lượng. Kiểm tra cài đặt, mở cửa sổ đo đủ dài và đối chiếu CPU thật.

**Bài F — kết quả ổn định.** Với chương trình `RecordingApiDemo` ở phần 7, dòng `workEvents=3` xác nhận điều gì?

**Đáp án:** Đúng ba event custom có tên `training.WorkUnit` đã được đọc từ file kết quả. Nó **không** có nghĩa chỉ có ba event trong toàn bộ recording, cũng không chứng minh chi phí/overhead JFR bằng 0. Các event JVM khác có thể tồn tại.

**Bài G — ghi nền dài hạn.** Bạn có thể ghi vô hạn vào disk repository vì `setToDisk(true)` đã được bật không?

**Đáp án:** Không nên. Nếu không đặt giới hạn dung lượng/tuổi dữ liệu, repository có thể phát triển; dùng `setMaxSize` và `setMaxAge` theo ngân sách dung lượng/khả năng chẩn đoán.

## 13. Ghi nhớ vận hành

- **`Configuration`** mô tả event settings; **`Recording`** sở hữu một phiên ghi và vòng đời; **`EventSettings`** tinh chỉnh một loại event; **`RecordingFile`** đọc kết quả đã xuất.
- Vòng đời cơ bản: **tạo → cấu hình → start → workload → stop → dump → close**; có thể dump snapshot khi đang RUNNING.
- Chọn **một** chiến lược xuất: `dump` chủ động, hoặc `setDestination` tự ghi khi stop. Tôn trọng state vì STOPPED không restart được và CLOSED không còn dữ liệu.
- `getSettings()` không phải cầu nối tự động để chỉnh cấu hình; `setSettings` thay toàn bộ map, nên merge đầy đủ hoặc dùng `enable(...).with...`.
- Giới hạn duration/dung lượng/tuổi dữ liệu, bảo vệ quyền và nội dung file, kiểm chứng sự kiện thực sự được thu trước khi phân tích.
- Dù dùng API ngay trong service, **JFR vẫn là công cụ đo có overhead**; cần workload đại diện và kết quả trước/sau để kết luận đúng.

### Tài liệu tham khảo

- Oracle Java 21 API, `Recording`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html
- Oracle Java 21 API, `Configuration`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Configuration.html
- Oracle Java 21 API, `EventSettings`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html
- Oracle Java 21 API, `FlightRecorder`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/FlightRecorder.html
- Oracle Java 21 API, package `jdk.jfr` (event settings): https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle Java 21 API, `RecordingFile`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html
- Oracle Java 21, lệnh `jfr`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
