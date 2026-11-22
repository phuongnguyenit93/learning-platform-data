# Configuration và thiết lập sự kiện với JFR API trong Java 11

**Chủ đề cha:** JFR API  
**Đề bài:** Configuration và thiết lập sự kiện  
**Phạm vi:** `jdk.jfr.Configuration`, `jdk.jfr.Recording`, `jdk.jfr.EventSettings`, `jdk.jfr.EventType`, `jdk.jfr.SettingDescriptor`, event annotations, JFC và đọc file JFR. Chỉ sử dụng những API **có trên Java 11** và kiến thức còn áp dụng trên Java hiện đại; không dựa vào các API đời sau hoặc công cụ đã lỗi thời.

Java Flight Recorder (JFR) là bộ ghi sự kiện tích hợp vào JVM, phục vụ quan sát GC, CPU, scheduling, I/O, lock, allocation, thread và sự kiện ứng dụng tự định nghĩa. JFR không đơn giản là bật hết mọi event: người vận hành phải chọn **configuration** phù hợp và thiết lập cho từng event để cân bằng thông tin, overhead, kích thước tệp và dữ liệu nhạy cảm. Java 11 có **module `jdk.jfr`** chứa API chuẩn để thực hiện các việc này bằng Java.

Có hai cấp điều khiển không được nhầm:

1. **Event settings:** loại event nào bật/tắt, ngưỡng duration (`threshold`), có lưu stack trace không (`stackTrace`), chu kỳ của periodic event (`period`) và các setting tùy chỉnh.
2. **Recording options:** khi nào recording bắt đầu/kết thúc, lưu trong memory hay disk repository, mức dung lượng/thời hạn giữ lại, destination/dump.

`Configuration` là mô tả một tập event settings, thường đọc từ cấu hình dựng sẵn `default`/`profile` hoặc file `.jfc`. `Recording` là một phiên thu thập thực tế. `EventSettings` giúp override setting qua fluent API; `RecordingFile` cho phép đọc bản ghi `.jfr` để kiểm chứng.

## 1. Sau bài này bạn biết gì?

- Phân biệt `.jfc` (JFR configuration) và `.jfr` (dữ liệu recording).
- Lấy và khám phá cấu hình qua `Configuration.getConfiguration("default")`, `getConfiguration("profile")`, `getConfigurations()`, `getName/getLabel/getProvider/getContents/getSettings`.
- Tạo cấu hình bằng `Configuration.create(Reader)` và `Configuration.create(Path)` từ JFC hợp lệ.
- Dùng `new Recording(Configuration)` hoặc `new Recording(Map<String,String>)`; biết `setSettings(map)` **thay thế toàn bộ** map thay vì merge.
- Override `enabled`, `threshold`, `stackTrace`, `period` qua `Recording.enable/disable` và `EventSettings.with...`.
- Khai báo custom JFR event có `@Name`, `@Label`, `@Category`, `@Enabled`, `@Threshold`, `@StackTrace`.
- Chọn `isEnabled`, `begin/end`, `shouldCommit` và `commit` đúng mục đích để giảm overhead.
- Kiểm tra setting khả dụng qua `EventType.getSettingDescriptors()`, không suy đoán event nào cũng có `period`.
- Ghi ba sự kiện custom, lọc bằng threshold, dump thành `.jfr` và đọc lại chính xác bằng `RecordingFile`.
- Quản lý retention, quyền truy cập và data minimization khi vận hành JFR production.

## 2. Bắt đầu với module jdk.jfr

Trên Java 11, các lớp được dùng trong bài thuộc `jdk.jfr` và `jdk.jfr.consumer`. Khi muốn rõ ràng cả compile và runtime module resolution:

```bash
javac --release 11 --add-modules jdk.jfr -encoding UTF-8 JfrConfigurationDemo.java
java --add-modules jdk.jfr JfrConfigurationDemo
```

Trong một JDK đầy đủ, JFR có sẵn; tuy vậy một runtime image tùy biến có thể không chứa module. Nếu build cho bản Java 11, nên xác nhận runtime mục tiêu thực sự hỗ trợ JFR; không lấy một ví dụ mới chỉ chạy trên Java 17/21 rồi nhận nó có thể biên dịch với `--release 11`.

Để hiểu vòng đời, xem:

```text
Configuration.getConfiguration("default"/"profile")
                  hoặc Configuration.create(.jfc)
                           |
                           v
                  Map<String,String>
                         event settings
                           |
        +------------------+--------------------+
        |                                       |
   new Recording(config)            new Recording(settings)
        |                                       |
        +------------- override ----------------+
                enable/disable/with...
                           |
              recording options + start()
                           |
                     JFR events
               JVM + custom Event.commit()
                           |
                  stop() + dump(Path)
                           |
                    output.jfr
                           |
                 RecordingFile đọc
                           |
                  RecordedEvent
```

Chỉ có một `Configuration` chưa tạo bản ghi, và map `enabled=true` chưa đồng nghĩa event đã được commit. Recording phải được start và event phải thỏa các điều kiện thực tế.

## 3. Configuration: hai profile dựng sẵn

Java 11 JFR thường cung cấp hai template:

| Tên | Mục tiêu | Vận hành |
|---|---|---|
| `default` | Quan sát định kỳ, mức overhead thấp hơn | Thường phù hợp làm cấu hình nền sau khi benchmark |
| `profile` | Thu chi tiết phục vụ phân tích | Dùng khoảng thời gian giới hạn, theo dõi tài nguyên |

`profile` có thể thu dữ liệu dày hơn và tăng chi phí, không nên đặt vô hạn mọi nơi chỉ vì cần thêm thông tin. Không khẳng định số lượng event/setting của hai profile là cố định giữa tất cả vendor, bản cập nhật và module JDK.

```java
Configuration base = Configuration.getConfiguration("default");
Configuration profiling = Configuration.getConfiguration("profile");

System.out.println(base.getName());
System.out.println(profiling.getName());
```

Đây là **trích đoạn**, cần import `jdk.jfr.Configuration`, đặt trong method có xử lý `IOException`/`ParseException`.

### 3.1 Những phương thức của Configuration

| API | Kết quả |
|---|---|
| `getConfigurations()` | Danh sách các cấu hình dựng sẵn |
| `getConfiguration(name)` | Một configuration theo tên |
| `getName()` | Identifier, thường `default` hoặc `profile` |
| `getLabel()` | Nhãn đọc được |
| `getDescription()` | Mô tả cấu hình |
| `getProvider()` | Nhà cung cấp cấu hình |
| `getSettings()` | Map event setting key/value |
| `getContents()` | Nội dung text configuration, ví dụ XML JFC |
| `create(new StringReader(xml))` | Parse cấu hình từ `Reader` |
| `create(pathToJfc)` | Parse cấu hình từ file JFC |

`getContents` và `getSettings` không phải một: JFC có thể chứa thêm metadata và cấu trúc control để công cụ UI chỉnh cấu hình; map settings là representation dùng để thiết lập Recording. Parse từ Reader/Path có thể ném `IOException` hoặc `java.text.ParseException`. Với file không tin cậy, không nạp cấu hình tùy ý vào hệ thống sản xuất.

### 3.2 Không sửa default.jfc nằm trong JDK

Template đi kèm JDK có thể thay đổi khi update. Nếu muốn nhiều service dùng một chính sách sự kiện chung, tạo file JFC tùy chỉnh được version-control và kiểm thử, **không chỉnh trực tiếp** `default.jfc` hay `profile.jfc` tại thư mục JDK. Đặt quyền đọc cho service, kiểm soát thay đổi và rollback.

Một cách kiểm tra JFC trước triển khai: parse file qua `Configuration.create(Path)`, lấy `getSettings` và so sánh với yêu cầu cụ thể theo event names. Không yêu cầu toàn bộ nội dung JFC sau serialize phải byte-for-byte giống file gốc; nội dung người viết và control metadata có thể khác với map đã parse.

## 4. Cấu trúc event setting key/value

JFR dùng `Map<String,String>` với mẫu khóa:

```text
<event-name>#<setting-name> = <setting-value>
```

Ví dụ **minh họa những cặp setting**, không phải toàn văn XML JFC:

```properties
training.jfr.WorkEvent#enabled=true
training.jfr.WorkEvent#threshold=5 ms
training.jfr.WorkEvent#stackTrace=false
jdk.CPULoad#period=1 s
```

`event-name` là `EventType.getName()`, thường đến từ `@Name` hoặc fully qualified event class name. Nhãn `@Label` chỉ để hiển thị, không phải tên key. Với nhiều event trùng tên do classloader khác nhau, có thể dùng `<event-id>#<setting-name>`; `EventType.getId()` có phạm vi **JVM runtime hiện tại**, không nên lưu ID đó vĩnh viễn trong cấu hình cross-deployment.

### Bốn setting tiêu chuẩn

| Setting | Ý nghĩa | Giá trị ví dụ | Chú ý |
|---|---|---|---|
| `enabled` | Event có được ghi không | `true` / `false` | Recording phải chạy và event phải đáp ứng các filter khác |
| `threshold` | Thời lượng tối thiểu event phải đạt để được thu | `0 ms`, `10 ms`, `1 s` | Không phải thời gian chờ phát event |
| `stackTrace` | Gắn stack trace vào event | `true` / `false` | Tăng chi phí thu/lưu/đọc |
| `period` | Chu kỳ phát periodic event | `1 s`, `20 ms` | Chỉ có ý nghĩa cho event hỗ trợ periodic behavior |

**Không phải mọi event đều hỗ trợ đầy đủ bốn setting**. Ví dụ custom event ghi thủ công bằng `Event.commit()` thường có `enabled`, `threshold`, `stackTrace` nhưng không có `period`. `jdk.CPULoad` là periodic event có `period`. Tìm `EventType.getSettingDescriptors()` để biết hợp đồng thực.

Các đơn vị threshold/period Java 11 thông dụng gồm `ns`, `us`, `ms`, `s`, `m`, `h`, `d`. Giá trị threshold bằng không có thể được biểu diễn `0`, `0 ms` hoặc `0 s` tùy cách nhập/chuẩn hóa. Đừng dùng so chuỗi mà không xác định semantics thời gian.

## 5. Recording: đưa configuration vào phiên ghi

Có ba kiểu khởi tạo thường gặp:

```java
Recording empty = new Recording();
Recording fromConfig = new Recording(
        Configuration.getConfiguration("default"));
Recording fromMap = new Recording(
        Configuration.getConfiguration("profile").getSettings());
```

Đây là **trích đoạn**, phải đóng tất cả Recording sau khi sử dụng và xử lý checked exceptions. `Recording()` tạo recording không có settings thiết lập tường minh; **không** đồng nghĩa constructor này tự chọn toàn bộ default JFC. Nếu cần baseline cụ thể, dùng `new Recording(Configuration.getConfiguration("default"))`.

**Quy trình dễ quản lý:**

1. Tải base configuration hoặc một JFC tùy chỉnh.
2. Xác định những event thật sự cần ghi.
3. Override bằng `enable/disable/with...` hoặc map settings đã copy.
4. Cài đặt retention, destination, duration phù hợp.
5. `start()`, chạy workload có đo đạc.
6. `stop()` và `dump(Path)`/destination theo policy.
7. Dùng `try-with-resources` để `close()` dù có lỗi.

Oracle Java SE 11 khuyến nghị cấu hình settings **trước `start()`** để dữ liệu nhất quán và giảm chi phí chuyển trạng thái; việc thay settings giữa một recording đang chạy có thể hợp lệ nhưng sẽ tạo hai giai đoạn dữ liệu khác chính sách.

### 5.1 setSettings luôn thay thế toàn bộ map

`Recording.setSettings(Map)` **không merge tự động**:

```java
Configuration base = Configuration.getConfiguration("default");
Map<String, String> copied = new HashMap<>(base.getSettings());
copied.put("training.jfr.WorkEvent#enabled", "true");
copied.put("training.jfr.WorkEvent#threshold", "0 ms");

try (Recording recording = new Recording(base)) {
    recording.setSettings(copied);
    // Các setting trong base còn đó vì ta đã copy vào map.
}
```

Đây là trích đoạn, import `Map`, `HashMap`, `Recording`, `Configuration`. Nếu gọi `setSettings(Map.of("training.jfr.WorkEvent#enabled","true"))` thì map trả về có thể **chỉ còn entry đó**; settings còn lại trong Recording cũ bị thay thế.

Tương tự, `Configuration.getSettings()` trả map mà sửa nó **không thay đổi đối tượng Configuration gốc**. Muốn thay đổi recording, phải truyền map mới qua constructor/`setSettings` hoặc gọi `Recording.enable(...)`.

**Lỗi thứ tự:** `recording.enable(...).withThreshold(...)` rồi gọi `recording.setSettings(oldMap)` sẽ thay thế cả override fluent trước đó. Chọn một chiến lược rõ ràng hoặc thực hiện các overrides sau khi setSettings.

### 5.2 Recording options khác event settings

| Recording option | Ý nghĩa |
|---|---|
| `setName(String)` | Tên nhận diện phiên |
| `setToDisk(boolean)` | Dùng disk repository hay buffer trong memory |
| `setMaxAge(Duration)` | Giới hạn retention theo tuổi |
| `setMaxSize(long)` | Giới hạn dung lượng dữ liệu giữ lại |
| `setDuration(Duration)` | Thời gian ghi tự động |
| `setDestination(Path)` | Đường dẫn dump khi stop |
| `setDumpOnExit(boolean)` | Dump khi JVM exit theo cấu hình |
| `start()/stop()` | Bắt đầu/kết thúc ghi |
| `dump(Path)` | Xuất recording ra JFR file |
| `close()` | Giải phóng tài nguyên |

Các option này **không thay thế** `enabled/threshold/period/stackTrace` của từng event. `setMaxSize` không phải giới hạn size của một event field; `withThreshold` không quyết định file được giữ bao lâu.

## 6. EventSettings: API fluent của Java 11

`recording.enable(String)` hoặc `recording.enable(Class<? extends Event>)` trả `EventSettings`. Các phương thức thường dùng:

```java
recording.enable("jdk.CPULoad")
        .withPeriod(Duration.ofSeconds(2));

recording.enable(WorkEvent.class)
        .withoutThreshold()
        .withoutStackTrace();

recording.disable("jdk.FileWrite");
```

Đây là **trích đoạn**, `recording` đang tồn tại, `WorkEvent` là custom event và cần import `Duration`. `disable` tương tự `enable` nhưng đặt enabled=false. Tên string có thể khớp nhiều loại event trùng tên, trong khi overload dùng `Class` chỉ rõ event type.

| API | Công dụng |
|---|---|
| `with("name","value")` | Đặt một setting cụ thể theo key/value |
| `withThreshold(Duration)` | Ngưỡng duration |
| `withoutThreshold()` | Bỏ ngưỡng duration, có thể ghi là `0 s` |
| `withStackTrace()` | Bật stack trace |
| `withoutStackTrace()` | Tắt stack trace |
| `withPeriod(Duration)` | Đặt chu kỳ periodic event |

**`withPeriod` không tự lên lịch một custom event bình thường.** Một event cần có cơ chế periodic emission do JVM hoặc API phù hợp đăng ký. Dùng `withPeriod` trên loại event không có setting `period` sẽ không tự tạo source event mới.

**Threshold không phải timer:** Nếu một event mất 2 ms và threshold 100 ms, JFR bỏ event đó; nó không giữ event 98 ms rồi mới gửi. Với duration event, `begin/end` đo thời lượng; `shouldCommit()` giúp bỏ qua việc xây field tốn tài nguyên khi threshold không đạt.

### 6.1 Phân biệt stack trace JFR với exception stack

`withStackTrace` cấu hình stack trace gắn vào JFR event. Tắt stack trace của event không làm mất Java exception stack trong chương trình và cũng không ẩn event fields do ứng dụng ghi. Khi muốn bật stack trace để điều tra, cân nhắc chi phí CPU, dung lượng và thông tin file/class có thể nhạy cảm.

### 6.2 Nhiều recording song song

Một JVM có thể có nhiều Recording cùng chạy với nhu cầu event settings khác nhau; JFR phải tổng hợp điều kiện effective cho sự kiện. Vì vậy `Event.isEnabled()`/`shouldCommit()` có thể phản ánh nhu cầu của nhiều Recording, không chỉ map cục bộ của một instance `Recording`. Không coi `@Enabled(false)` là biện pháp chặn vĩnh viễn mọi việc thu event nếu một Recording khác được quyền enable.

## 7. Custom event và annotation defaults

Custom JFR event là class `extends jdk.jfr.Event`. Ví dụ:

```java
@Name("training.jfr.OrderEvent")
@Label("Order task")
@Category({"Business", "Orders"})
@Enabled(false)
@Threshold("10 ms")
@StackTrace(false)
static class OrderEvent extends Event {
    @Label("Request identifier")
    long requestId;
    @Label("Operation")
    String operation;
}
```

Đây là **trích đoạn class nested**; cần imports `jdk.jfr.*`. Metadata/default giải thích:

- `@Name`: định danh nhất quán được dùng cho event settings và công cụ.
- `@Label`: nhãn trình bày dễ đọc.
- `@Category`: nhóm phân cấp.
- `@Description`: mô tả event/field khi thêm annotation.
- `@Enabled(false)`: disabled theo default, Recording có thể override.
- `@Threshold("10 ms")`: thời gian chạy tối thiểu mặc định.
- `@StackTrace(false)`: mặc định không kèm stack trace.

Các annotation là **default**, không chắc là settings effective nếu recording override. Tên sự kiện nên có namespace ổn định như `myorg.orders.OrderEvent`; không dùng tên giao dịch/người dùng nhạy cảm làm `@Name`.

### 7.1 Commit theo cách tránh overhead không cần thiết

```java
OrderEvent event = new OrderEvent();
if (event.isEnabled()) {
    event.begin();
    // Chạy thao tác cần đo thời gian.
    event.end();

    if (event.shouldCommit()) {
        event.requestId = requestId;
        event.operation = operation;
        event.commit();
    }
}
```

Đây là **trích đoạn**, cần khai báo biến `requestId`, `operation`. Trong code thật, nếu exception xảy ra giữa `begin/end`, cân nhắc `try/finally` để kết thúc đo và ghi failure theo policy. Không đưa token, mật khẩu hay toàn bộ request body vào event fields.

`Event.isEnabled()` giúp tránh xây dữ liệu khi event disabled. `Event.shouldCommit()` còn kiểm tra threshold; khi không đạt, có thể tránh gán/serialize dữ liệu phụ. `commit()` mới là yêu cầu gửi event tới recorder; việc gọi nó khi không có recording hoạt động không ép JVM lưu file.

## 8. Demo chạy được 1 — Configuration, map overrides và EventSettings

Demo `JfrConfigurationDemo` dùng API Java 11 để:

1. Nạp `default` và `profile`, xác nhận name/settings/JFC contents.
2. Copy settings từ `default` sang một map mới, thêm `enabled=true`, `threshold=0 ms`, `stackTrace=false` cho `training.jfr.BusinessEvent`.
3. `setSettings` lên Recording và đọc lại map; kiểm tra base Configuration vẫn giữ nguyên.
4. `enable(...).withoutThreshold().withoutStackTrace()` và xem threshold được chuẩn hóa thành `0 s`.
5. Tạo một Recording khác và gọi `setSettings` với map chỉ có một key để chứng minh method này **thay thế** toàn bộ các setting cũ.

Lưu file **`JfrConfigurationDemo.java`**:

```java
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import java.util.HashMap;
import java.util.Map;

public class JfrConfigurationDemo {
    @Name("training.jfr.BusinessEvent")
    static class BusinessEvent extends Event {
        int code;
    }

    public static void main(String[] args) throws Exception {
        Configuration base = Configuration.getConfiguration("default");
        Configuration profile = Configuration.getConfiguration("profile");
        System.out.println("default-name=" + base.getName());
        System.out.println("profile-name=" + profile.getName());
        System.out.println("default-has-settings=" + !base.getSettings().isEmpty());
        System.out.println("default-has-jfc=" + base.getContents().contains("<configuration"));

        Map<String, String> patch = new HashMap<>(base.getSettings());
        patch.put("training.jfr.BusinessEvent#enabled", "true");
        patch.put("training.jfr.BusinessEvent#threshold", "0 ms");
        patch.put("training.jfr.BusinessEvent#stackTrace", "false");

        try (Recording recording = new Recording(base)) {
            recording.setSettings(patch);
            Map<String, String> actual = recording.getSettings();
            System.out.println("patched-enabled=" +
                    actual.get("training.jfr.BusinessEvent#enabled"));
            System.out.println("patched-threshold=" +
                    actual.get("training.jfr.BusinessEvent#threshold"));
            System.out.println("patched-stack=" +
                    actual.get("training.jfr.BusinessEvent#stackTrace"));
            System.out.println("base-unchanged=" +
                    !base.getSettings().containsKey(
                        "training.jfr.BusinessEvent#enabled"));
            recording.enable("training.jfr.BusinessEvent")
                    .withoutThreshold().withoutStackTrace();
            System.out.println("fluent-enabled=" +
                    recording.getSettings().get(
                        "training.jfr.BusinessEvent#enabled"));
            System.out.println("fluent-threshold=" +
                    recording.getSettings().get(
                        "training.jfr.BusinessEvent#threshold"));
            System.out.println("fluent-stack=" +
                    recording.getSettings().get(
                        "training.jfr.BusinessEvent#stackTrace"));
        }
        try (Recording replacement = new Recording(base)) {
            replacement.setSettings(
                    java.util.Collections.singletonMap(
                            "training.jfr.BusinessEvent#enabled", "true"));
            System.out.println("setSettings-replaces="
                    + (replacement.getSettings().size() == 1));
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 11 --add-modules jdk.jfr -encoding UTF-8 JfrConfigurationDemo.java
java --add-modules jdk.jfr JfrConfigurationDemo
```

**Stdout đã kiểm chứng:**

```text
default-name=default
profile-name=profile
default-has-settings=true
default-has-jfc=true
patched-enabled=true
patched-threshold=0 ms
patched-stack=false
base-unchanged=true
fluent-enabled=true
fluent-threshold=0 s
fluent-stack=false
setSettings-replaces=true
```

**Phân tích:** `base-unchanged=true` nhấn mạnh map copy không sửa Configuration gốc. `setSettings-replaces=true` chứng minh nếu truyền map chỉ một entry thì những settings khác **không được giữ tự động**. `fluent-threshold=0 s` cho thấy `withoutThreshold` có thể dùng biểu diễn thời lượng khác với `0 ms` do bạn đặt trước đó nhưng cùng nghĩa không lọc theo duration.

Demo chỉ kiểm tra cấu hình, **không** `start`/`dump`. Không kết luận JFR đã ghi event chỉ vì map trả đúng giá trị; demo tiếp theo mới kiểm tra file ghi thực tế.

## 9. Demo chạy được 2 — custom event, threshold và file .jfr

`JfrRecordedEventsDemo` định nghĩa `WorkEvent` với `@Name("training.jfr.WorkEvent")`, `@Label`, `@Category`, `@Threshold("0 ms")` và `@StackTrace(false)`. Hai Recording hoạt động tuần tự, để test rõ ràng và không bị tác động bởi việc nhiều recording cùng merge settings:

- **Recording A:** bật WorkEvent, `withoutThreshold().withoutStackTrace()`, bắt đầu ghi, `publish(1)`, `publish(2)`, `publish(3)`, dừng và dump. Đọc file bằng `RecordingFile`, lọc đúng event name, nhận chính xác 3 ID và không có stack trace.
- **Recording B:** bật cùng WorkEvent nhưng `withThreshold(Duration.ofHours(1))`; gửi một event ngắn; stop/dump rồi kiểm tra số WorkEvent bằng **0**, chứng minh threshold lọc event ngắn chứ không hẹn giờ gửi sau.

Lưu **`JfrRecordedEventsDemo.java`**:

```java
import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.Threshold;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

public class JfrRecordedEventsDemo {
    @Name("training.jfr.WorkEvent")
    @Label("Work item")
    @Category({"Learning", "JFR"})
    @Threshold("0 ms")
    @StackTrace(false)
    static class WorkEvent extends Event {
        @Label("Request ID")
        int requestId;
        @Label("Action")
        String action;
    }

    static List<RecordedEvent> ownEvents(Path file) throws Exception {
        List<RecordedEvent> found = new ArrayList<>();
        try (RecordingFile reader = new RecordingFile(file)) {
            while (reader.hasMoreEvents()) {
                RecordedEvent event = reader.readEvent();
                if ("training.jfr.WorkEvent".equals(
                        event.getEventType().getName())) {
                    found.add(event);
                }
            }
        }
        return found;
    }

    static void publish(int id) {
        WorkEvent event = new WorkEvent();
        event.requestId = id;
        event.action = "process";
        if (event.isEnabled()) {
            event.begin();
            event.end();
            if (event.shouldCommit()) {
                event.commit();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path first = Files.createTempFile("jfr-work-accepted-", ".jfr");
        Path second = Files.createTempFile("jfr-work-filtered-", ".jfr");
        try {
            try (Recording recording = new Recording(
                    Configuration.getConfiguration("default"))) {
                recording.setToDisk(true);
                recording.enable(WorkEvent.class)
                        .withoutThreshold()
                        .withoutStackTrace();
                recording.start();
                publish(1);
                publish(2);
                publish(3);
                recording.stop();
                recording.dump(first);
            }
            List<RecordedEvent> accepted = ownEvents(first);
            List<Integer> ids = new ArrayList<>();
            boolean noStacks = true;
            for (RecordedEvent event : accepted) {
                ids.add(event.getInt("requestId"));
                if (event.getStackTrace() != null) {
                    noStacks = false;
                }
            }
            System.out.println("accepted-count=" + accepted.size());
            System.out.println("accepted-ids=" + ids);
            System.out.println("accepted-no-stack=" + noStacks);

            try (Recording recording = new Recording(
                    Configuration.getConfiguration("default"))) {
                recording.enable(WorkEvent.class)
                        .withThreshold(Duration.ofHours(1))
                        .withoutStackTrace();
                recording.start();
                publish(4);
                recording.stop();
                recording.dump(second);
            }
            List<RecordedEvent> filtered = ownEvents(second);
            System.out.println("filtered-count=" + filtered.size());

            if (accepted.size() != 3 || !ids.equals(
                    java.util.Arrays.asList(1, 2, 3))
                    || !noStacks || !filtered.isEmpty()) {
                throw new AssertionError("JFR event settings mismatch");
            }
        } finally {
            Files.deleteIfExists(first);
            Files.deleteIfExists(second);
        }
    }
}
```

```bash
javac --release 11 --add-modules jdk.jfr -encoding UTF-8 JfrRecordedEventsDemo.java
java --add-modules jdk.jfr JfrRecordedEventsDemo
```

```text
accepted-count=3
accepted-ids=[1, 2, 3]
accepted-no-stack=true
filtered-count=0
```

### 9.1 Vì sao phải lọc theo event type?

JFR có thể ghi rất nhiều event của JVM do default configuration. Không được assert `RecordingFile` chỉ chứa đúng 3 bản ghi tổng cộng. Chương trình lọc bằng `event.getEventType().getName().equals("training.jfr.WorkEvent")` rồi đọc `event.getInt("requestId")`. Vì vậy expected count là cho **custom event**, không phải tất cả sự kiện hệ thống.

### 9.2 Đọc recording lớn

`RecordingFile.readAllEvents(Path)` thuận tiện cho file nhỏ, nhưng có thể nạp rất nhiều event lên heap. Đối với file lớn, dùng mẫu tuần tự:

```java
try (RecordingFile reader = new RecordingFile(path)) {
    while (reader.hasMoreEvents()) {
        RecordedEvent event = reader.readEvent();
        // Lọc event type rồi xử lý record.
    }
}
```

Đây là **trích đoạn**, cần `path` và imports JFR consumer. Javadoc Java 11 khuyến cáo chỉ đọc `.jfr` từ **nguồn đáng tin**. Files có thể chứa thread names, class/method/path, hostnames và custom fields nhạy cảm; hạn chế quyền đọc, lưu trữ và chia sẻ.

### 9.3 Vì sao không test threshold bằng sleep sát ngưỡng?

`Thread.sleep(10)` không đảm bảo một event luôn có duration chính xác 10 ms trên mọi hệ điều hành/scheduler. Dùng ngưỡng cách xa test event (ví dụ một giờ) hoặc benchmark có ràng buộc thời gian. Demo chọn `Duration.ofHours(1)` để event vài thao tác CPU ngắn không bị ghi, tránh test flaky.

## 10. Demo chạy được 3 — parse JFC, introspect và periodic setting

`JfrSettingsInspectionDemo` dùng đúng JDK 11 để:

1. Lấy `getContents()` từ `default`, parse lại bằng `Configuration.create(new StringReader(...))` và so sánh map settings.
2. Ghi nội dung JFC vào file tạm, parse bằng `Configuration.create(Path)` và xóa file.
3. Liệt kê `Configuration.getConfigurations()`.
4. Định nghĩa event `InspectedEvent` có `@Enabled(false)`, `@Threshold("15 ms")`, `@StackTrace(false)`.
5. Lấy `EventType.getEventType(InspectedEvent.class)`, đọc `SettingDescriptor.getName()`/`getDefaultValue()`.
6. Xác nhận custom event bình thường không có `period` trong metadata, trong khi `jdk.CPULoad` có thể cấu hình `period`.
7. Gọi `withPeriod(Duration.ofSeconds(2))` và in biểu diễn thời lượng mà JFR lưu trên runtime thử nghiệm.

Lưu **`JfrSettingsInspectionDemo.java`**:

```java
import jdk.jfr.Configuration;
import jdk.jfr.Enabled;
import jdk.jfr.Event;
import jdk.jfr.EventType;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.SettingDescriptor;
import jdk.jfr.StackTrace;
import jdk.jfr.Threshold;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

public class JfrSettingsInspectionDemo {
    @Name("training.jfr.InspectedEvent")
    @Enabled(false)
    @Threshold("15 ms")
    @StackTrace(false)
    static class InspectedEvent extends Event {
        int value;
    }

    static String defaultSetting(List<SettingDescriptor> descriptors,
                                 String name) {
        return descriptors.stream()
                .filter(d -> name.equals(d.getName()))
                .map(SettingDescriptor::getDefaultValue)
                .findFirst().orElse("<none>");
    }

    public static void main(String[] args) throws Exception {
        Configuration def = Configuration.getConfiguration("default");
        Configuration readAgain =
                Configuration.create(new StringReader(def.getContents()));

        Path file = Files.createTempFile("jfr-config-", ".jfc");
        boolean parsedFile;
        try {
            Files.write(file, def.getContents().getBytes(
                    StandardCharsets.UTF_8));
            Configuration fromFile = Configuration.create(file);
            parsedFile = !fromFile.getSettings().isEmpty();
        } finally {
            Files.deleteIfExists(file);
        }
        System.out.println("reader-settings-same="
                + readAgain.getSettings().equals(def.getSettings()));
        System.out.println("file-parse-has-settings=" + parsedFile);

        Set<String> names = Configuration.getConfigurations().stream()
                .map(Configuration::getName)
                .collect(Collectors.toSet());
        System.out.println("listed-default=" + names.contains("default"));
        System.out.println("listed-profile=" + names.contains("profile"));

        EventType type = EventType.getEventType(InspectedEvent.class);
        List<SettingDescriptor> descriptors = type.getSettingDescriptors();
        Set<String> settingNames = descriptors.stream()
                .map(SettingDescriptor::getName)
                .collect(Collectors.toSet());
        System.out.println("event-type=" + type.getName());
        System.out.println("has-enabled=" + settingNames.contains("enabled"));
        System.out.println("has-threshold="
                + settingNames.contains("threshold"));
        System.out.println("has-stackTrace="
                + settingNames.contains("stackTrace"));
        System.out.println("manual-event-has-period="
                + settingNames.contains("period"));
        System.out.println("default-enabled="
                + defaultSetting(descriptors, "enabled"));
        System.out.println("default-threshold="
                + defaultSetting(descriptors, "threshold"));
        System.out.println("default-stackTrace="
                + defaultSetting(descriptors, "stackTrace"));

        boolean cpuLoadExists =
                FlightRecorder.getFlightRecorder().getEventTypes().stream()
                .anyMatch(t -> "jdk.CPULoad".equals(t.getName()));
        System.out.println("jdk-cpuload-exists=" + cpuLoadExists);
        try (Recording recording = new Recording()) {
            recording.enable("jdk.CPULoad")
                    .withPeriod(Duration.ofSeconds(2));
            System.out.println("cpu-load-period="
                    + recording.getSettings().get("jdk.CPULoad#period"));
        }
    }
}
```

```bash
javac --release 11 --add-modules jdk.jfr -encoding UTF-8 JfrSettingsInspectionDemo.java
java --add-modules jdk.jfr JfrSettingsInspectionDemo
```

**Stdout đã kiểm chứng trên runtime thử nghiệm:**

```text
reader-settings-same=true
file-parse-has-settings=true
listed-default=true
listed-profile=true
event-type=training.jfr.InspectedEvent
has-enabled=true
has-threshold=true
has-stackTrace=true
manual-event-has-period=false
default-enabled=false
default-threshold=15 ms
default-stackTrace=false
jdk-cpuload-exists=true
cpu-load-period=2000000000 ns
```

**Điểm cần hiểu:** `@Enabled(false)`, `@Threshold("15 ms")` và `@StackTrace(false)` thiết lập **default metadata** của event class, không phải lời hứa rằng một Recording không thể override. `EventType.getSettingDescriptors()` cho biết những setting hỗ trợ và default; `Recording.getSettings()` cho biết map cấu hình của Recording, còn `Event.isEnabled()/shouldCommit()` phụ thuộc trạng thái thu thập đang hoạt động.

Một chi tiết quan trọng: trên runtime đã kiểm thử, `withPeriod(Duration.ofSeconds(2))` được JFR biểu diễn thành chuỗi **`"2000000000 ns"`**, không phải `"2 s"`. Hai giá trị đều là 2 giây; test portability không nên so đúng chuỗi hiển thị khi API không bảo đảm dạng textual duy nhất.

**Không dùng `withPeriod` để “tự động hóa” custom event thủ công.** Event chỉ commit khi application gọi `commit` (hoặc được đăng ký đúng cơ chế periodic riêng). Metadata `manual-event-has-period=false` trong stdout minh họa rõ điểm này.

## 11. Ghi nhận sự kiện và dữ liệu đo đúng nghĩa

### 11.1 Threshold cần duration thật

Một đoạn code như:

```java
WorkEvent e = new WorkEvent();
e.requestId = 42;
e.begin();
doWork();
e.end();
if (e.shouldCommit()) e.commit();
```

là **trích đoạn**, cần implement `doWork`. Nếu `doWork` diễn ra ngắn hơn threshold thì event không được ghi. Nếu cần đo một workflow async, phải xác định rõ đâu là mốc bắt đầu/kết thúc của công việc, không giả định thread đang chạy tương ứng toàn bộ workflow.

### 11.2 Periodic event khác duration event

`jdk.CPULoad` có thể phát theo chu kỳ; `jdk.JavaMonitorEnter` là event liên quan contention có threshold duration; `WorkEvent` là event ứng dụng theo lời gọi commit. Chúng có các cơ chế khác nhau. Không đặt `period` lên event không có scheduling và mong `Event.commit` tự được gọi mỗi giây.

### 11.3 Stack trace và privacy

Stack trace giúp tìm caller path của một event chậm, nhưng tăng data và overhead. Với event lưu ID hoặc nội dung business, bản thân custom fields có thể nhạy cảm ngay cả khi `stackTrace=false`. Không ghi password, token, raw request body, các giá trị nhạy cảm không cần thiết. Đặt quyền bảo vệ `.jfr` tương tự dữ liệu telemetry quan trọng.

### 11.4 Runtime concurrency

JFR có thể hoạt động với nhiều Recording. Khi hai recording có yêu cầu enabled/threshold khác nhau, JVM phải tổng hợp các điều kiện để thu event. Đừng giả định `Event.shouldCommit()` chỉ phản ánh một Recording bạn đang giữ. Nếu dữ liệu chứa bí mật, thiết kế **field minimization và access control**, không chỉ gắn `@Enabled(false)`.

## 12. SettingDefinition và SettingControl nâng cao

Java 11 cũng có `@SettingDefinition` và `SettingControl` để custom event định nghĩa setting riêng, ví dụ lọc một event theo category hoặc một pattern. `SettingControl` có:

- `getValue()`: trả default/current setting value hợp lệ; không được null.
- `setValue(String)`: nhận setting text, kiểm tra value và cập nhật state dùng để lọc event.
- `combine(Set<String>)`: tổng hợp yêu cầu từ **nhiều Recording** cùng chạy, không tạo side effect, không ném exception, trả giá trị cho phép mỗi Recording thu tối thiểu các event nó yêu cầu.

`@SettingDefinition` đặt trên một method trả `boolean` và nhận một subclass `SettingControl` làm tham số. Nếu method trả true, event được phép commit theo setting custom. Đây là kỹ thuật hạ tầng cho event filter chuyên biệt; nếu chỉ cần enabled/threshold/stackTrace, ưu tiên built-in settings để giảm code và chi phí.

**Không tạo setting tùy ý bằng `with("myFilter","...")` rồi suy rằng JFR biết filter đó.** Event class phải khai báo SettingDefinition/Control hợp lệ. Với filter sử dụng regex, validate pattern và đo hiệu năng; matcher tốn kém trong hot loop có thể làm overhead tăng mạnh.

## 13. Cấu hình file và công cụ CLI

JFR API hoạt động cùng các công cụ JDK 11. Những lệnh sau là **mẫu vận hành**, không phải phần stdout đã chạy trong ba demo:

```bash
# Dùng PID thật của JVM cần thu:
jcmd <PID> JFR.start name=diag settings=default duration=60s filename=diag.jfr
jcmd <PID> JFR.check
jcmd <PID> JFR.dump name=diag filename=diag-current.jfr

# Xem event từ recording file bằng tool JDK:
jfr print --events jdk.CPULoad diag.jfr
```

Thay `<PID>` bằng số thật. `jcmd` cần quyền attach thích hợp và `filename` phải được resolve tại môi trường của JVM bị attach. Nếu process chạy container/remote, phải chú ý volume/quyền file. `default` và `profile` là tên cấu hình được nhận diện bởi JFR; tùy setup, có thể dùng JFC tùy chỉnh.

Khi một ứng dụng vừa có JFR command-line recording vừa có Recording do Java API tạo, hai recording có thể hoạt động đồng thời; phải giám sát CPU/disk/retention và tránh giữ những event không được phép từ recording khác.

## 14. Kế hoạch vận hành thực tế

**Kịch bản A — giám sát dịch vụ lâu dài:** bắt đầu từ `default`, chọn period của CPU/GC phù hợp, đặt giới hạn size/age/duration hoặc cơ chế quay vòng dữ liệu, đo overhead thực tế, đảm bảo dung lượng repository.

**Kịch bản B — điều tra lỗi chậm:** bật event ứng dụng có threshold 100 ms và stack trace nếu cần, thu trong khoảng thời gian giới hạn, kiểm tra request ID/operation metadata, không giữ stack trace trên mọi event nhỏ nếu quá đắt.

**Kịch bản C — profiling theo sự cố:** có thể dùng `profile` trong cửa sổ đo ngắn, nhưng không bật vô hạn; so sánh baseline, p95/p99 latency, CPU, allocation và file size.

**Kịch bản D — tuân thủ bảo mật:** định nghĩa schema event hạn chế trường nhạy cảm, kiểm soát quyền file và retention, audit người có thể kích hoạt JFR/đọc dữ liệu, không gắn token/PII vào stack/event.

### 14.1 Tiêu chí quyết định setting

| Câu hỏi | Quyết định phù hợp |
|---|---|
| Có cần event này 24/7? | enabled mặc định và overhead budget |
| Event phát thường xuyên đến mức nào? | threshold, custom sampling hoặc period nếu event định kỳ |
| Có cần caller path? | stackTrace chỉ nơi cần |
| Ghi bao nhiêu dữ liệu? | recording maxAge/maxSize, size quota |
| Có dữ liệu nhạy cảm không? | schema redaction, quyền truy cập, retention |
| Cần phân tích tức thời? | Cân nhắc JDK baseline và API tương ứng; Java11 chủ yếu ví dụ Recording/RecordingFile |
| Có nhiều Recording cùng JVM không? | Kiểm tra effective setting và merge behavior |
| Cấu hình cần dùng chung nhiều app? | JFC riêng được version-control |

## 15. Ma trận QA

| Ca | Thiết lập | Điều phải kiểm tra |
|---|---|---|
| default | `getConfiguration("default")` | Tên và settings không rỗng |
| profile | `getConfiguration("profile")` | Có cấu hình trên runtime thử nghiệm |
| JFC Reader | `create(new StringReader(contents))` | Map tương thích bản gốc |
| JFC Path | Lưu file tạm `.jfc` rồi `create(path)` | Đọc hợp lệ và dọn file |
| Map patch | Copy base và put keys | Recording chứa override |
| No mutation | Sửa map copy | Configuration gốc không thay đổi |
| setSettings replace | Map một entry | Recording chỉ còn một explicit entry |
| Fluent | `enable(...).withoutThreshold()` | enabled và threshold tương ứng |
| enable class | `enable(CustomEvent.class)` | Event class được bật |
| Stack off | `withoutStackTrace()` | Event không kèm stack |
| Threshold short | `withThreshold(1h)` | Event cực ngắn bị lọc |
| Custom events | Commit ba event | IDs 1,2,3 đúng |
| JFR file | Dump và consume | Đọc đúng type, không đếm event khác |
| EventType | `getSettingDescriptors()` | Đúng tên setting |
| Annotation defaults | `@Enabled(false)`... | Default từ metadata chính xác |
| Manual event period | Custom event thường | Không tự có period |
| JVM periodic event | `jdk.CPULoad` | period được đặt đúng ý nghĩa |
| Multi Recording | Hai recording chồng thời gian | Không giả định isolation tuyệt đối |
| Runtime budget | setMaxAge/maxSize | Retention và dung lượng có quản lý |
| File privacy | Dump chứa fields | Quyền, retention, không lộ secret |
| Java11 API | Build `--release 11` | Không dùng class JDK14+ |

**Độ ổn định test:** không assert số lượng toàn bộ event JVM trong recording, không assert số byte file, không dựa vào chính xác `Thread.sleep` sát threshold và không hardcode chuỗi duration khi provider có thể canonicalize.

## 16. Những sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Nhầm `.jfc` với `.jfr` | Dùng sai parser | Configuration cho JFC; RecordingFile cho JFR |
| Dùng Recording() và nghĩ đã nạp default.jfc | Không chắc có base settings mong muốn | Dùng `new Recording(Configuration)` |
| Sửa map `Configuration.getSettings()` để đổi object gốc | Không đổi Configuration | Copy và truyền vào Recording |
| Gọi setSettings map một entry và nghĩ merge | Mất các event overrides cũ | Copy map toàn bộ rồi patch |
| Gọi setSettings cũ sau fluent enable | Ghi đè fluent setting | Kiểm soát thứ tự cấu hình |
| Dùng label thay event name | Key không khớp | `EventType.getName()` |
| Lưu ID event qua nhiều JVM | Không ổn định | Sử dụng name hoặc ID hiện tại |
| Xem threshold là timer | Không hiểu event bị lọc | Duration filter, không tạo periodic event |
| Xem period áp dụng mọi custom Event | Không có periodic hook | Kiểm tra descriptors và nguồn phát |
| Cố so bằng chuỗi `"2 s"` | Runtime có thể lưu `"2000000000 ns"` | So ý nghĩa thời lượng |
| Không cấu hình retention/size | Quá disk/heap budget | MaxAge, MaxSize, Duration, quota |
| Bật stackTrace mọi event | Overhead và volume lớn | Bật có chọn lọc |
| Giả định `@Enabled(false)` bảo vệ bí mật tuyệt đối | Recording khác có thể bật | Data minimization, file access controls |
| Ghi raw token vào custom event | Rò bí mật | Redact và review schema |
| Đếm tất cả event trong JFR để xác minh custom event | Sai vì JVM events khác | Lọc theo EventType name |
| `readAllEvents` với file nhiều GB | Tốn heap | RecordingFile đọc tuần tự |
| Không close Recording/RecordingFile | Rò tài nguyên | try-with-resources |
| Dùng `RecordingStream` trong code Java 11 | API đó có từ Java14 | Với Java11 dùng Recording/RecordingFile |
| Bật profile suốt ngày không đo | Latency/data volume cao | Profiling theo cửa sổ có giám sát |
| Cho phép caller bên ngoài chỉnh JFC tùy ý | Có thể bật thu dữ liệu nhạy cảm | Authn/authz, allowlist, audit |

## 17. Bài tập có đáp án

**1.** File `service.jfc` và `service.jfr` khác nhau như thế nào?  
**Đáp án:** JFC chứa configuration/settings XML; JFR chứa recorded events. Dùng `Configuration.create` cho JFC và `RecordingFile` cho JFR.

**2.** Sau `new Recording(Configuration.getConfiguration("default"))`, gọi `setSettings(Map.of("x#enabled","true"))` có merge không?  
**Đáp án:** không, nó thay thế map settings. `x` ở đây chỉ là tên event minh họa, cần tên event thực tế.

**3.** Có thể sửa map `config.getSettings()` và coi `config` đã thay đổi không?  
**Đáp án:** không; cần dùng map mới để tạo/cấu hình Recording.

**4.** `withThreshold(Duration.ofMillis(20))` trên event duration 3ms có tác dụng gì?  
**Đáp án:** event bị lọc, không chờ 17ms rồi ghi.

**5.** `withPeriod(Duration.ofSeconds(1))` có khiến custom event thường tự commit mỗi giây không?  
**Đáp án:** không; event phải hỗ trợ cơ chế periodic thực sự.

**6.** Sự kiện có `@Enabled(false)` có thể bật bằng `Recording.enable(MyEvent.class)` không?  
**Đáp án:** có; annotation là default, Recording có thể override.

**7.** Dùng API nào để khám phá event hỗ trợ `stackTrace`, `threshold` và `period`?  
**Đáp án:** `EventType.getSettingDescriptors()` và `SettingDescriptor.getName()`.

**8.** `@Name("training.jfr.WorkEvent")` và `@Label("Work")`: key enabled là gì?  
**Đáp án:** `training.jfr.WorkEvent#enabled`, không lấy label.

**9.** Với 100.000 events ghi vào file, vì sao không nên luôn `RecordingFile.readAllEvents`?  
**Đáp án:** có thể tiêu thụ nhiều heap; dùng `hasMoreEvents/readEvent` để đọc tuần tự.

**10.** Một service có hai recordings cùng chạy, một muốn event disabled và một muốn enabled. `Event.isEnabled()` có nhất thiết chỉ phản ánh recording thứ nhất không?  
**Đáp án:** không. JFR tổng hợp nhu cầu từ nhiều recording; cần xét effective setting.

**11.** Vì sao `cpu-load-period=2000000000 ns` không trái với `Duration.ofSeconds(2)`?  
**Đáp án:** cả hai cùng thời gian 2 giây. Không suy luận sai vì cách viết chuỗi khác.

**12.** Một recording có `stackTrace=false`. Có thể yên tâm rằng JFR file không chứa dữ liệu nhạy cảm?  
**Đáp án:** không. Custom fields, system events và metadata vẫn có thể nhạy cảm; cần schema và quyền file.

**13.** Bạn muốn cấu hình thống nhất nhiều deployments: sửa file `default.jfc` bên trong JDK?  
**Đáp án:** không. Tạo bản JFC riêng được version-control và phân phối theo policy.

**14.** Một snippet sử dụng `jdk.jfr.consumer.RecordingStream` muốn biên dịch với `--release 11`. Có phù hợp không?  
**Đáp án:** không. RecordingStream có từ Java 14; dùng APIs Java11 trong bài.

**15.** Tại sao cần `recording.close()` sau khi dump?  
**Đáp án:** để giải phóng resources JFR; dùng try-with-resources để đảm bảo cleanup cả khi có exception.

## 18. Nguồn chính thức còn áp dụng

- [Java SE 11 — Configuration](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Configuration.html): built-in/JFC config, map settings và contents.
- [Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): constructors, setSettings, enable/disable, start/stop, dump, retention.
- [Java SE 11 — EventSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): withThreshold, withPeriod, withStackTrace và with().
- [Java SE 11 — Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html): begin/end/isEnabled/shouldCommit/commit.
- [Java SE 11 — EventType](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventType.html): name, metadata, getSettingDescriptors.
- [Java SE 11 — SettingDescriptor](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/SettingDescriptor.html): default và tên setting.
- [Java SE 11 — jdk.jfr package](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html): cú pháp eventName#setting và cài đặt chuẩn.
- [Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc events từ file JFR.
- [Java SE 11 — SettingControl](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/SettingControl.html) và [SettingDefinition](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/SettingDefinition.html): settings tùy chỉnh.
- [Java SE 14 — RecordingStream](https://docs.oracle.com/en/java/javase/14/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): được giới thiệu Java14, không thuộc baseline Java11.
- [Java SE 11 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html): JFR CLI và các tùy chọn recording.
- [Dev.java — Configuring JFR](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/): phân cấp recording options/configuration/event settings.

**Kết luận:** `Configuration` chọn bộ event settings nền, `Recording` tạo phiên ghi và quản lý vòng đời, `EventSettings` override enabled/threshold/stackTrace/period, còn `EventType/SettingDescriptor` xác minh các setting thực sự được hỗ trợ. Trong Java 11, cách thực hành đáng tin là **copy map trước khi gọi setSettings**, đặt event settings trước `start`, chỉ thu thông tin cần thiết, thiết lập quota/retention và đọc file `.jfr` để kiểm chứng. Đừng nhầm threshold với period, map cấu hình với recording đang chạy hay việc JFR enabled với quyền thu dữ liệu nhạy cảm.