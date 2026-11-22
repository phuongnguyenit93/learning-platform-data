# 16.7 Đọc file JFR qua RecordingFile và truy cập trường của RecordedEvent

## 1. Mục tiêu và vấn đề cần giải quyết

Java Flight Recorder (JFR) lưu dữ liệu runtime vào tệp **`.jfr`**: sự kiện GC, CPU, thread, allocation, lock, I/O và những event mà ứng dụng tự định nghĩa. Có thể xem file bằng `jfr print` hoặc JDK Mission Control, nhưng khi cần **tự động lọc, tổng hợp, đối chiếu theo thời gian, xuất kết quả điều tra hoặc viết công cụ nội bộ**, ta cần đọc JFR ngay trong Java.

Gói `jdk.jfr.consumer` cung cấp hai lớp trung tâm:

- **`RecordingFile`:** mở tệp `.jfr` và lần lượt đọc từng event; triển khai `AutoCloseable` qua `Closeable` nên đặt trong `try-with-resources`.
- **`RecordedEvent`:** đại diện **một event đã được ghi** trong recording; cung cấp loại event, thời điểm, duration, thread, stack trace và khả năng truy cập các field theo tên.

Bài học này hướng dẫn cách đọc file, chọn đúng loại event, truy cập trường có kiểu, tự khám phá schema, xử lý field vắng mặt và tổng hợp dữ liệu hiệu quả. Các ví dụ chạy với **Java 17+**, kiểm thử trên JDK 21.

Sau bài này, bạn có thể:

1. Đọc tuần tự tệp `.jfr` bằng vòng `hasMoreEvents()` / `readEvent()`.
2. Lọc event bằng `event.getEventType().getName()` và phân biệt tên kỹ thuật với label.
3. Dùng `getString`, `getInt`, `getLong`, `getBoolean`, `getValue` và `hasField` đúng trường hợp.
4. Đọc `Instant`, `Duration`, `RecordedThread`, `RecordedStackTrace` và metadata `ValueDescriptor`.
5. Xử lý tệp lớn, khác phiên bản JDK hoặc có field thiếu mà không suy luận sai từ dữ liệu trống.

**Ranh giới quan trọng:** `RecordingFile` là API **đọc dữ liệu đã ghi trong file**. Nó không phải API để bắt đầu recording hoặc subscribe live events. Để tạo recording, dùng `jdk.jfr.Recording` hoặc công cụ `jcmd`; để tiêu thụ event trực tiếp theo luồng, JDK còn có API `RecordingStream`, nhưng đó là cơ chế khác.

## 2. Luồng dữ liệu từ JVM đến đối tượng Java

```text
JVM/application
  |
  |  JVM built-in events / custom Event.commit()
  v
JFR recording
  |
  |  dump / stop / ghi file
  v
recording.jfr
  |
  v
new RecordingFile(Path)
  |
  +-- hasMoreEvents() ? -- false --> kết thúc + close()
  |
  +-- true --> readEvent() --> RecordedEvent
                                |
                                +-- getEventType().getName()
                                +-- getStartTime(), getEndTime(), getDuration()
                                +-- hasField(), getString(), getLong(), ...
                                +-- getThread(), getStackTrace()
                                |
                                v
                         lọc / nhóm / tổng hợp / cảnh báo
```

Một file chứa **nhiều event types**, và mỗi event type có **schema field khác nhau**. Do đó, không viết một parser cố ép mọi `RecordedEvent` thành cấu trúc “duration + bytes + path + thread” cố định.

Ví dụ:

- `jdk.GarbageCollection` mô tả một sự kiện GC theo schema của JDK.
- `jdk.JavaMonitorEnter` mô tả lần chờ vào monitor.
- `jdk.FileRead` mô tả một lần đọc file.
- `demo.Request` có thể là event do ứng dụng định nghĩa với `endpoint`, `status`, `bytes`, `ok`.

Tất cả đều có thể xuất hiện dưới dạng `RecordedEvent`, nhưng những field nghiệp vụ như `status` **chỉ thuộc event type có khai báo nó**. Phải lọc theo type rồi mới đọc field tương ứng.

## 3. Bộ API cốt lõi

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `new RecordingFile(Path)` | Mở file JFR đã tồn tại | `IOException` nếu file lỗi/không hợp lệ; dùng nguồn đáng tin |
| `hasMoreEvents()` | Kiểm tra còn event chưa đọc | Dùng trước `readEvent()` |
| `readEvent()` | Đọc event kế tiếp | Có thể ném `EOFException` nếu gọi khi hết; cũng có `IOException` |
| `close()` | Giải phóng tài nguyên file | Dùng `try-with-resources` |
| `RecordingFile.readAllEvents(Path)` | Lấy danh sách mọi event cùng lúc | Chỉ phù hợp file nhỏ; dễ tốn RAM |
| `readEventTypes()` | Lấy metadata các event types trong file | Có type trong metadata không có nghĩa có instance khớp |
| `event.getEventType().getName()` | Tên kỹ thuật của event | Dùng tên đầy đủ để phân loại chính xác |
| `event.getStartTime()` / `getEndTime()` | Thời điểm dưới dạng `Instant` | Không phải độ dài chờ request |
| `event.getDuration()` | Thời lượng dưới dạng `Duration` | Không phải millisecond số nguyên |
| `event.hasField(name)` | Schema có field tên đó không? | Field có thể hiện diện nhưng giá trị `null` |
| `event.getValue(name)` | Giá trị tổng quát | Kiểu trả về phụ thuộc schema; tránh ép kiểu mù |
| `event.getString/getInt/getLong/...` | Đọc field theo kiểu | Sai tên hoặc kiểu có thể ném `IllegalArgumentException` |
| `event.getFields()` | Danh sách `ValueDescriptor` | Xem tên/kiểu field mà không hardcode |
| `event.getThread()` / `getStackTrace()` | Thông tin thread và stack được ghi | Có thể `null` nếu không được ghi |

### 3.1. Vòng đọc chuẩn

```java
// Fragment minh họa, cần imports, phương thức chứa đoạn mã và đường dẫn thật.
Path path = Path.of("recording.jfr");
try (RecordingFile file = new RecordingFile(path)) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        System.out.println(event.getEventType().getName());
    }
}
```

Đây là mẫu quan trọng nhất: **đọc từng event**, xử lý xong rồi chuyển sang event kế tiếp. `RecordingFile` quản lý tài nguyên parser/file và đóng đúng cách nếu exception xảy ra.

`readEvent()` không tự đảm bảo type nào đang đến: event A có thể là GC, event B là CPU, event C là event ứng dụng. Trước khi truy cập field đặc thù, lọc type.

### 3.2. Thứ tự và tính toàn vẹn

`RecordingFile` đọc các event từ file. Khi phân tích latency, dùng **timestamp trong event**, không dùng thứ tự dòng in hoặc thứ tự duyệt làm bằng chứng rằng hai event có quan hệ nhân quả. File có thể chứa nhiều thread, các event duration chồng nhau, cùng mốc timestamp và những event được thu theo chu kỳ.

Việc file có thể đọc thành công không chứng minh **đã thu đủ dữ liệu**. Event có thể bị tắt, bị lọc bởi threshold, có sampling, bị giới hạn thời gian ghi hoặc không có hoạt động tương ứng. Đọc được 0 event một type cần phân biệt “không xảy ra”, “không được ghi” và “đã lọc sai”.

## 4. Thực hành hoàn chỉnh: tạo file JFR rồi đọc lại

Để tránh phụ thuộc vào một file `.jfr` bên ngoài, ví dụ tự tạo ba custom events có field xác định, ghi ra `requests-demo.jfr`, rồi mở file bằng `RecordingFile`. Phần tạo recording chỉ phục vụ kiểm thử; **trọng tâm** là phương thức `inspect`.

Tạo **`JfrFileReadLab.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedStackTrace;
import jdk.jfr.consumer.RecordedThread;
import jdk.jfr.consumer.RecordingFile;

public final class JfrFileReadLab {
    @Name("demo.Request")
    public static final class RequestEvent extends Event {
        public String endpoint;
        public int status;
        public long bytes;
        public boolean ok;
    }

    private static void emit(String endpoint, int status, long bytes, boolean ok) {
        RequestEvent event = new RequestEvent();
        event.endpoint = endpoint;
        event.status = status;
        event.bytes = bytes;
        event.ok = ok;
        event.begin();
        event.end();
        event.commit();
    }

    private static void inspect(Path file) throws Exception {
        List<String> lines = new ArrayList<>();
        int count = 0;
        int successful = 0;
        long totalBytes = 0;

        try (RecordingFile input = new RecordingFile(file)) {
            while (input.hasMoreEvents()) {
                RecordedEvent event = input.readEvent();

                if (!"demo.Request".equals(event.getEventType().getName())) {
                    continue;
                }
                if (!event.hasField("endpoint") || !event.hasField("bytes")) {
                    throw new IllegalStateException("Missing expected JFR fields");
                }

                String endpoint = event.getString("endpoint");
                int status = event.getInt("status");
                long bytes = event.getLong("bytes");
                boolean ok = event.getBoolean("ok");

                if (event.getStartTime() == null
                        || event.getDuration().isNegative()) {
                    throw new IllegalStateException("Invalid event timing");
                }

                RecordedThread thread = event.getThread();
                if (thread != null) {
                    thread.getJavaName();
                }
                RecordedStackTrace trace = event.getStackTrace();
                if (trace != null) {
                    trace.getFrames();
                }

                count++;
                totalBytes += bytes;
                if (ok) {
                    successful++;
                }
                lines.add(endpoint + " status=" + status
                        + " bytes=" + bytes + " ok=" + ok);
            }
        }

        Collections.sort(lines);
        for (String line : lines) {
            System.out.println(line);
        }
        System.out.println("events=" + count
                + " totalBytes=" + totalBytes
                + " successful=" + successful);
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("requests-demo.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(RequestEvent.class)
                    .withThreshold(Duration.ZERO)
                    .withoutStackTrace();
            recording.start();
            emit("/orders", 200, 100L, true);
            emit("/reports", 503, 200L, false);
            emit("/orders", 200, 300L, true);
            recording.stop();
            recording.dump(output);
        }

        inspect(output);
    }
}
```

Biên dịch trên JDK 17 trở lên. Lệnh `--release 17` giúp xác minh mã sử dụng API Java 17:

```bash
javac --release 17 JfrFileReadLab.java
java JfrFileReadLab
```

**Stdout xác minh trên JDK 21:**

```text
/orders status=200 bytes=100 ok=true
/orders status=200 bytes=300 ok=true
/reports status=503 bytes=200 ok=false
events=3 totalBytes=600 successful=2
```

Chương trình chỉ in những event có tên `demo.Request` và sắp xếp chuỗi trước khi in, vì thế kết quả ví dụ không phụ thuộc vào thứ tự đọc event. Phần lớn hoạt động JFR/JVM có thể phát thêm các event type khác, nhưng vòng `if` lọc chúng. Mỗi lần chạy tạo/ghi lại file `requests-demo.jfr` trong thư mục chạy chương trình; hãy dùng thư mục thực hành riêng.

Giải thích phần đọc:

1. `new RecordingFile(file)` mở snapshot JFR; `try-with-resources` đảm bảo đóng parser.
2. `hasMoreEvents()` và `readEvent()` duyệt lần lượt những gì file đã ghi.
3. `getEventType().getName()` giữ đúng custom type `demo.Request`; không đọc field `endpoint` của một GC event khác.
4. `hasField(...)` xác nhận schema có field cần thiết trước khi đọc.
5. `getString("endpoint")`, `getInt("status")`, `getLong("bytes")`, `getBoolean("ok")` trả đúng kiểu Java. `totalBytes` là **tổng payload của event demo**, không phải số byte của file JFR.
6. `getStartTime()` và `getDuration()` được kiểm tra; giá trị thực thay đổi mỗi lần chạy nên chương trình không in chúng trong stdout cố định.
7. `getThread()` và `getStackTrace()` được xử lý an toàn với `null`. Ở đây `withoutStackTrace()` nhằm tiết kiệm dữ liệu; không kỳ vọng file có stack trace cho custom type này.
8. Số event, tổng byte và số lần `ok` là phép tổng hợp ứng dụng từ những field đã đọc, không phải counters được `RecordingFile` tự tính.

Chạy thêm các lệnh ngoài Java để tự đối chiếu:

```bash
jfr summary requests-demo.jfr
jfr print --events demo.Request requests-demo.jfr
```

`jfr summary` liệt kê các event types và count trong file; `jfr print` cho bản hiển thị thân thiện. Chúng có thể thêm metadata/timestamp thay đổi giữa các lần chạy, vì vậy không dùng output của công cụ này như transcript cố định.

## 5. Truy cập field của RecordedEvent đúng kiểu

`RecordedEvent` kế thừa các phương thức từ `RecordedObject`. Ngoài metadata chung của event, dữ liệu đặc thù được truy cập bằng **tên field trong schema**, không phải tên cột bạn tự đặt trong CSV.

### 5.1. Các getter thường gặp

| Kiểu dữ liệu trong event | Đọc bằng | Ví dụ |
| --- | --- | --- |
| `String` | `getString(name)` | `event.getString("endpoint")` |
| `boolean` | `getBoolean(name)` | `event.getBoolean("ok")` |
| `int` | `getInt(name)` | `event.getInt("status")` |
| `long` | `getLong(name)` | `event.getLong("bytes")` |
| `double` | `getDouble(name)` | Cho field double hoặc primitive widening phù hợp |
| Giá trị chung | `getValue(name)` | `Object raw = event.getValue("bytes")` |
| Event start/end | `getStartTime()` / `getEndTime()` | `Instant` |
| Event duration | `getDuration()` **không tham số** | `Duration` |
| Timespan field riêng có annotation phù hợp | `getDuration("fieldName")` | `Duration` của field đó |
| Timestamp field riêng có annotation phù hợp | `getInstant("fieldName")` | `Instant` của field đó |
| Field tham chiếu class | `getClass("fieldName")` | `RecordedClass`, không phải `java.lang.Class` |
| Field tham chiếu thread | `getThread("fieldName")` | `RecordedThread` |

**Không nhầm hai hàm cùng tên**:

- `event.getDuration()` trả thời lượng **của toàn bộ event** (từ start đến end).
- `event.getDuration("myDurationField")` đọc **một field timespan bên trong event** nếu schema khai báo nó theo cách JFR có thể đổi sang `Duration`.

Tương tự, `event.getThread()` là thread gắn với việc commit/record event, còn `event.getThread("sampledThread")` là một **field thread có tên riêng** nếu type ấy có field đó. Với sampling event, thread được lấy mẫu và thread ghi event có thể có ý nghĩa khác nhau.

### 5.2. Field không tồn tại và field có giá trị null

`hasField("x") == false` nghĩa là schema không chứa field `x`. Nó **không** có nghĩa “field bằng null” hoặc “giá trị là 0”. Nếu field tồn tại nhưng giá trị không được ghi hoặc là null, `hasField("x")` vẫn có thể trả `true`. Đọc field một cách phòng thủ:

```java
// Fragment trong nơi có RecordedEvent event.
if (event.hasField("endpoint")) {
    String endpoint = event.getString("endpoint");
    if (endpoint != null) {
        System.out.println(endpoint);
    }
}
```

Một phương thức typed getter có thể ném `IllegalArgumentException` khi tên field không tồn tại hoặc dữ liệu không phù hợp kiểu. `getInt("bytes")` có thể sai nếu field `bytes` thực tế là `long`; `getString("status")` không đổi int thành chuỗi giúp bạn. Muốn hiển thị linh hoạt nhiều event types, sử dụng `ValueDescriptor` và `getValue` rồi kiểm tra kiểu dữ liệu.

### 5.3. `getValue` và đường dẫn field lồng nhau

`event.getValue("field")` trả generic value; với dữ liệu phức tạp, nó có thể là `RecordedThread`, `RecordedClass`, `RecordedObject` hoặc kiểu khác mà JFR consumer hỗ trợ. Do đó, tránh ép mọi giá trị thành `String`.

`RecordedObject` cũng hỗ trợ đường dẫn lồng nhau qua dấu chấm, ví dụ `"thread.group.parent.name"` nếu field tree thật sự có những thành phần đó. Điều này hữu ích khi truy vấn nested metadata, nhưng **đường dẫn phải tồn tại** trong schema/giá trị thực:

```java
// Fragment minh họa cách bảo vệ một đường dẫn tùy biến.
String path = "thread.group.parent.name";
if (event.hasField(path)) {
    Object nested = event.getValue(path);
    System.out.println(nested);
}
```

Đừng suy luận rằng mọi `RecordedEvent` đều có field `thread`, `group` hoặc `parent` theo đúng chuỗi này. Nó là ví dụ về **cú pháp**, không phải schema của tất cả event. Field có thể không hiện diện hoặc có đối tượng trung gian null.

## 6. Khám phá schema với EventType và ValueDescriptor

Một tool phân tích JFR dùng lâu dài phải chịu được việc các JDK khác nhau có field mới, đổi tên hoặc không phát một số event. Cách an toàn là đọc metadata thay vì hardcode mọi schema.

- `event.getEventType()` trả `EventType` mô tả loại event.
- `event.getEventType().getName()` là tên đầy đủ, ví dụ `jdk.JavaMonitorEnter` hoặc `demo.Request`.
- `event.getEventType().getLabel()` là label dành cho con người, không phải khóa ổn định để filter.
- `event.getFields()` trả danh sách `ValueDescriptor`; mỗi descriptor có `getName()`, `getTypeName()`, cùng các annotation/metadata khác.
- `file.readEventTypes()` trả các `EventType` mà file có metadata; đây **không phải** danh sách event instances.

Ví dụ duyệt schema của một event:

```java
// Fragment minh họa, yêu cầu import jdk.jfr.ValueDescriptor.
for (ValueDescriptor descriptor : event.getFields()) {
    String fieldName = descriptor.getName();
    String fieldType = descriptor.getTypeName();
    Object value = event.getValue(fieldName);
    System.out.println(fieldName + " [" + fieldType + "] = " + value);
}
```

Đây là cách khám phá **field nào thực sự tồn tại**. Tuy vậy, in toàn bộ `toString()` của nested object/stack trace trên file lớn có thể rất dài. Trong ứng dụng thật, nên giới hạn số event và số field in, xử lý riêng giá trị phức tạp.

### 6.1. Công cụ đọc file bất kỳ: JfrInspect

Tạo **`JfrInspect.java`**. Chương trình lấy file và tên event type từ command line, duyệt toàn bộ file để đếm số event khớp, nhưng **chỉ in tối đa hai mẫu đầu tiên**; khi type là `demo.Request`, nó in hai field `endpoint` và `status` nếu metadata xác nhận sự tồn tại:

```java
import java.nio.file.Path;
import jdk.jfr.ValueDescriptor;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrInspect {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: java JfrInspect <file.jfr> <event-type>");
            System.exit(2);
        }
        String targetType = args[1];
        long matches = 0;

        try (RecordingFile file = new RecordingFile(Path.of(args[0]))) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                if (!targetType.equals(event.getEventType().getName())) {
                    continue;
                }

                matches++;
                if (matches <= 2) {
                    System.out.println("type=" + event.getEventType().getName());
                    System.out.println("start=" + event.getStartTime());
                    System.out.println("duration=" + event.getDuration());

                    for (ValueDescriptor field : event.getFields()) {
                        if (field.getName().equals("endpoint")
                                || field.getName().equals("status")) {
                            System.out.println(field.getName() + " ["
                                    + field.getTypeName() + "]="
                                    + event.getValue(field.getName()));
                        }
                    }
                }
            }
        }

        System.out.println("matched=" + matches);
    }
}
```

Biên dịch và đọc file do ví dụ trước tạo:

```bash
javac --release 17 JfrInspect.java
java JfrInspect requests-demo.jfr demo.Request
```

**Hình dạng output đã kiểm thử** (thời gian và duration thay đổi từng lần):

```text
type=demo.Request
start=<Instant thực tế của event thứ nhất>
duration=<Duration thực tế của event thứ nhất>
endpoint [java.lang.String]=/orders
status [int]=200
type=demo.Request
start=<Instant thực tế của event thứ hai>
duration=<Duration thực tế của event thứ hai>
endpoint [java.lang.String]=/reports
status [int]=503
matched=3
```

Trong transcript trên, những chỗ trong dấu `<...>` là **chỉ dẫn minh họa, không phải stdout nguyên văn**. Khi biên dịch/chạy, `Instant` có dạng ISO-8601 và `Duration` được in theo biểu diễn `PT...S` của Java. Vì trình đọc chỉ in hai event khớp đầu tiên, dòng `matched=3` vẫn đếm toàn bộ ba event.

Dùng cách tương tự cho file JFR khác, ví dụ:

```bash
java JfrInspect service.jfr jdk.JavaMonitorEnter
```

Đối với type này, ví dụ chỉ in tên, timestamp và duration vì chương trình cố tình không hardcode các field không thuộc schema demo. Muốn xem fields cụ thể, dùng `event.getFields()`, metadata từ `jfr metadata` hoặc JMC rồi thêm logic phù hợp. Không suy ra type “không có endpoint” nghĩa là file lỗi: `endpoint` chỉ tồn tại trong custom event demo.

### 6.2. Schema và format thay đổi theo JDK

Một giả định dễ hỏng là mỗi `jdk.FileRead` chắc chắn luôn có cùng field, cùng tên, cùng kiểu ở mọi JDK/vendor. Thực tế JDK có thể thay đổi hoặc bổ sung field. Công cụ robust nên:

1. Lọc bằng event type name xác định.
2. Kiểm tra field bắt buộc và kiểu qua `ValueDescriptor`.
3. Xử lý optional fields bằng `hasField` và `null`.
4. Ghi rõ JDK/version, recording name, loại event và schema được gặp.
5. Tránh tự ép kiểu hoặc dùng `toString()` làm định dạng lưu trữ chính thức.

Nếu đang tạo JSON/CSV, ánh xạ rõ ràng `RecordedThread`, `RecordedClass`, `Duration`, `Instant` và các nested fields; đừng để serializer tự xuất một object graph khổng lồ.

## 7. Thời gian, duration, đơn vị và ngữ cảnh

### 7.1. `Instant` khác `Duration`

`getStartTime()` và `getEndTime()` trả `java.time.Instant`: **mốc thời gian**. `getDuration()` trả `java.time.Duration`: **khoảng kéo dài**. Ví dụ một `jdk.JavaMonitorEnter` có thể bắt đầu lúc 10:00:02.123 và duration 24 ms; điều đó **không tự nói** toàn bộ HTTP request mất 24 ms hay request chậm vì đúng một event duy nhất.

```java
// Fragment minh họa một RecordedEvent đã đọc.
java.time.Instant start = event.getStartTime();
java.time.Instant end = event.getEndTime();
java.time.Duration duration = event.getDuration();
double milliseconds = duration.toNanos() / 1_000_000.0;
```

`duration.toMillis()` là `long` nên có thể làm mất phần lẻ của milli giây; dùng `toNanos()/1_000_000.0` khi cần trình bày số thập phân và khoảng thời gian nằm trong giới hạn. Với Duration cực lớn, `toNanos()` có thể overflow, khi ấy cần phép chuyển an toàn hơn. Không nhầm các trường timestamp/size/ratio có metadata unit khác nhau.

### 7.2. Không tự định nghĩa một tổng thời gian sai

Nếu event A và B chạy trên hai thread và chồng nhau, cộng duration(A)+duration(B) có thể **lớn hơn** thời gian đồng hồ thực giữa hai mốc. Nếu JFR thu các event bằng sampling/threshold, tổng duration của event được ghi cũng **không nhất thiết** là tổng thời gian toàn bộ hoạt động đã xảy ra.

Khi phân tích: lọc đúng event type, cửa sổ thời gian, thread/request correlation và đơn vị; trình bày rõ mẫu có bị lọc theo threshold/period hay không.

### 7.3. Time zone và đối chiếu log khác

`Instant` không gắn một time zone địa phương; nó mô tả một thời điểm tuyệt đối. Khi xuất báo cáo theo Việt Nam:

```java
// Fragment minh họa.
java.time.ZonedDateTime local = event.getStartTime()
        .atZone(java.time.ZoneId.of("Asia/Ho_Chi_Minh"));
```

Đối chiếu JFR với application log, APM và container logs bằng timestamp nhất quán, đồng thời lưu ý lệch đồng hồ khi thu nhiều máy. Không đổi `Instant` thành chuỗi local rồi làm mất offset/time zone nếu cần phân tích xuyên service.

## 8. Thread, stack trace và object lồng nhau

### 8.1. `RecordedThread`

`event.getThread()` trả `RecordedThread` nếu thông tin này có trong event. Để hiển thị tên Java thread:

```java
// Fragment minh họa, yêu cầu import RecordedThread.
RecordedThread thread = event.getThread();
String threadName = thread == null ? "(not recorded)"
        : thread.getJavaName();
System.out.println(threadName);
```

`getJavaName()` có thể trả `null` nếu không có Java thread name. `getJavaThreadId()` và `getOSThreadId()` là các ID khác nhau; không thay thế lẫn nhau khi join dữ liệu. Với JDK hỗ trợ virtual threads, `isVirtual()` mô tả loại thread đã ghi, nhưng không suy ra mọi event thuộc cùng một carrier OS thread.

Một event có thể chứa **field thread khác** (ví dụ sampled thread). Khi ấy dùng `event.getThread("fieldName")` nếu schema xác nhận field. Đừng mặc định `event.getThread()` luôn là thread đang bị sampling.

### 8.2. `RecordedStackTrace` và `RecordedFrame`

`getStackTrace()` có thể `null` khi stack collection bị tắt hoặc event không ghi stack. Nếu có:

```java
// Fragment minh họa, yêu cầu import RecordedStackTrace/RecordedFrame.
RecordedStackTrace stack = event.getStackTrace();
if (stack != null) {
    System.out.println("truncated=" + stack.isTruncated());
    for (var frame : stack.getFrames()) {
        System.out.println(frame.getMethod().getName()
                + ":" + frame.getLineNumber());
    }
}
```

- `getFrames()` trả danh sách `RecordedFrame`; `getLineNumber()` có thể là `-1` khi không có line number.
- `isTruncated()` cho biết stack có bị cắt do giới hạn độ sâu/kích thước hay không.
- `frame.getMethod()` trả `RecordedMethod`; nếu cần tên class khai báo method có thể xem `frame.getMethod().getType().getName()`.
- Frame event không phải distributed trace: nó là call stack ở thời điểm được thu theo semantics của event.

Bật stack chỉ ở những event cần để điều tra; trên sự kiện có tần suất lớn, stack trace làm tăng dữ liệu và overhead. Không thể phục hồi stack **không được ghi** bằng cách tăng `jfr print --stack-depth` ở bước đọc.

### 8.3. Các kiểu phức hợp

`event.getValue(name)` có thể trả primitive boxed value, `String`, `RecordedClass`, `RecordedThread`, `RecordedObject` hoặc các kiểu dữ liệu phù hợp schema. Khi làm bộ xuất CSV, phải **chọn cách serialize có kiểm soát**:

- `RecordedClass`: xuất tên class.
- `RecordedThread`: xuất tên/id thread nếu có.
- `RecordedStackTrace`: chỉ xuất số frame hoặc khung đầu liên quan khi được phép.
- `Instant`: xuất chuỗi ISO-8601 có offset/ngữ cảnh.
- `Duration`: xuất số cùng đơn vị, ví dụ nano/milli giây.
- Field `null`: dùng giá trị rỗng có ý nghĩa rõ ràng, không đổi thành số 0.

## 9. Chọn chiến lược đọc cho file nhỏ và file lớn

### 9.1. `readAllEvents(Path)` có tiện nhưng tốn bộ nhớ

```java
// Fragment minh họa: chỉ nên dùng khi file đủ nhỏ.
java.util.List<RecordedEvent> events =
        RecordingFile.readAllEvents(Path.of("small.jfr"));
System.out.println("events=" + events.size());
```

`readAllEvents` đọc tất cả event vào một `List`. Nó phù hợp script ngắn/file nhỏ cần nhiều lần duyệt. Với file lớn hàng trăm MB hoặc nhiều triệu events, giữ toàn bộ list trong heap có thể gây GC mạnh hoặc `OutOfMemoryError`. Kích thước object Java sau parse **không nhất thiết bằng** kích thước file JFR nén/nhị phân.

### 9.2. Streaming qua `RecordingFile`

Với file lớn, giữ một `long count`, một số aggregate nhỏ và chỉ lưu các event cần thiết; không đưa mọi `RecordedEvent` vào một `ArrayList`. Ví dụ:

```java
// Fragment minh họa bộ đếm không giữ tất cả event trong heap.
long count = 0;
try (RecordingFile file =
        new RecordingFile(Path.of("service.jfr"))) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        if ("jdk.JavaMonitorEnter".equals(
                event.getEventType().getName())) {
            count++;
        }
    }
}
System.out.println("monitorEvents=" + count);
```

Chỉ đếm event đã ghi, **không** suy ra có tổng cộng bao nhiêu lần contention trong ứng dụng vì event có thể bị lọc. Nếu cần percentiles, có thể sử dụng histogram có giới hạn hoặc thuật toán streaming quantile; tránh giữ mọi duration chỉ để tính p99 trên recording lớn.

`RecordingFile` là parser một chiều theo lượt đọc; để phân tích lại từ đầu, mở một `RecordingFile` mới. API này đọc file đã có; không dùng nó như cơ chế tail/chờ event live.

### 9.3. Quản lý tệp và lỗi I/O

Những lỗi cần nhận diện:

- `NoSuchFileException`: đường dẫn sai hoặc file chưa được tạo.
- `IOException`: file không hợp lệ, đọc thất bại hoặc định dạng không được parser hỗ trợ.
- `EOFException`: gọi `readEvent()` khi không còn event; vòng `hasMoreEvents()` tránh lỗi sử dụng API thông thường.
- `IllegalArgumentException`: đọc sai tên hoặc sai kiểu field.
- `SecurityException` hoặc lỗi quyền OS: tiến trình đọc không có quyền với file.

Đọc **file từ nguồn đáng tin cậy**; heap/recording có thể chứa thông tin thread, tên class, path, request metadata và dữ liệu nhạy cảm. Hạn chế quyền trên `.jfr`, xóa an toàn khi hết nhu cầu và không nhận upload tùy ý của người lạ vào parser nội bộ mà không có giới hạn tài nguyên.

Nếu dữ liệu không đầy đủ, hãy kiểm tra file có được dump/stop hoàn chỉnh chưa; recording có thể còn đang chạy, bị xoay vòng, hoặc mất các khoảng do retention setting. Không kết luận từ một file lỗi rằng ứng dụng không phát event.

## 10. Đối chiếu bằng CLI trước khi viết parser

Dùng công cụ đi kèm JDK để nắm event name và schema của file:

```bash
jfr summary service.jfr
jfr metadata service.jfr
jfr print --events jdk.JavaMonitorEnter service.jfr
```

- `jfr summary` cho biết event types và counts (tùy phiên bản đầu ra).
- `jfr metadata` cho metadata/type descriptions, hữu ích trước khi hardcode field.
- `jfr print --events` cho ví dụ thực về field value và stack (nếu có).
- Nếu dùng JDK Mission Control, chọn event type và xem fields/aggregation/stack, rồi đối chiếu với mã `RecordingFile` của bạn.

Một parser nên tự khai báo **điều kiện đầu vào**: JDK/build nào tạo file, file nằm trên máy nào, event type nào được bật, khoảng thời gian nào được ghi, liệu có threshold và sampling. Đây là bối cảnh cần để giải thích số liệu; file JFR không phải “toàn bộ lịch sử của JVM”.

## 11. Tình huống áp dụng: từ file đến chẩn đoán

### 11.1. Tìm file read chậm

Có thể lọc `jdk.FileRead`, đọc `getDuration()` và những field hiện diện như path/bytesRead theo schema thực tế. Giả sử bạn muốn các event đã ghi có duration ít nhất 20 ms:

```java
// Fragment minh họa trong vòng đọc RecordedEvent event.
if ("jdk.FileRead".equals(event.getEventType().getName())
        && event.getDuration().compareTo(
                java.time.Duration.ofMillis(20)) >= 0) {
    System.out.println(event.getStartTime()
            + " duration=" + event.getDuration());
}
```

**Đây là lọc phía consumer sau khi ghi file**. Nó khác setting `jdk.FileRead#threshold` áp dụng **lúc thu**: consumer chỉ có thể bỏ các event **đã tồn tại**, không thể phục hồi event mà recording trước đó không ghi.

Nếu path/bytes không có trong schema, đừng áp giả định; kiểm tra `getFields()`. Nếu stack trace null, không quy được caller chỉ bằng file hiện tại; cần recording mới với stack enabled cho event thích hợp.

### 11.2. Gom event theo thread

`event.getThread()` có thể trả thread thực hiện/commit event. Muốn thống kê event counts theo thread, dùng key dựa trên ID phù hợp, kèm tên để đọc dễ. Nhưng ID của Java thread, OS thread và JFR event thread là các khái niệm khác nhau; thread name có thể trùng hoặc thay đổi. Với event sampled thread, ưu tiên field thread được event type đó định nghĩa.

Một lần request thường có thể chạy trên nhiều thread hoặc virtual threads; **đếm theo thread không đồng nghĩa đếm theo request**. Muốn theo request cần correlation ID hay custom event payload do ứng dụng ghi.

### 11.3. Tính số lần custom operation lỗi

Với `demo.Request` của ví dụ, ta biết field `ok` là boolean và `status` là int, nên dùng getter typed rồi tổng hợp. Đây là thống kê **những custom events đã được commit/ghi**. Không dùng nó thay cho số request web server nếu ứng dụng không instrument mọi request hoặc recording có threshold/retention.

### 11.4. Kết hợp nhiều recording

Một service có thể tạo nhiều file, mỗi file có thời gian và cấu hình riêng. Để so sánh, nên lưu metadata nguồn: tên file, JVM identity, JDK version, khoảng start/end và cài đặt event. Không nối file rồi cộng duration/count mù quáng khi chúng chồng lấp cùng sự kiện hoặc được thu từ nhiều recording của cùng JVM.

Khi cần hợp nhất, chuẩn hóa time zones và xác định tiêu chí chống trùng theo mục tiêu phân tích; JFR event không mặc định mang unique request ID xuyên các file.

## 12. Những lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Gọi `getString("bytes")` cho field `long` | Getter typed không tự đổi number thành String | Dùng `getLong("bytes")` hoặc metadata + `getValue` |
| Gọi `getInt("status")` trên mọi event | Không phải type nào cũng có field `status` | Lọc `getEventType().getName()` trước |
| `hasField` true nên nghĩ value chắc chắn khác null | Schema tồn tại khác với giá trị được ghi | Kiểm tra `null` cho reference fields |
| `getStackTrace().getFrames()` trực tiếp | Stack có thể không được ghi | Kiểm tra `getStackTrace() != null` |
| `event.getDuration()` được dùng như giá trị ms nguyên | API trả `Duration` | Chuyển đơn vị tường minh, giữ độ chính xác |
| Dùng `readAllEvents` cho file khổng lồ | Giữ toàn bộ event trong RAM | Dùng vòng `RecordingFile` và aggregate nhỏ |
| In tất cả fields của mọi event | Có thể tạo output rất lớn, lộ metadata | Lọc type, số event, field cần thiết |
| Không đóng `RecordingFile` | Có thể giữ tài nguyên file/parser | `try-with-resources` |
| 0 event = không có sự cố | Event có thể disabled, threshold cao hoặc sai cửa sổ | Kiểm tra cấu hình thu và workload |
| Gộp time/duration của nhiều thread | Event có thể chồng lấp và không có quan hệ nhân quả | Dùng timestamp/correlation và phân tích riêng |
| Phụ thuộc vào field nội bộ cố định ở mọi JDK | Schema có thể khác | Dùng `getFields()`/`ValueDescriptor`, kiểm tra optional |
| Nhầm `RecordedThread` với `java.lang.Thread` sống | Object là bản ghi metadata, không phải live JVM thread | Dùng ID/name của metadata, không gọi API điều khiển thread |

## 13. Bài tự luyện

**Bài 1.** Vì sao `RecordingFile.readAllEvents(Path)` không phù hợp để đếm một loại event trong file JFR nhiều GB?

*Trả lời:* Nó trả toàn bộ event dưới dạng list trong heap; có nguy cơ sử dụng rất nhiều RAM. Với bài toán đếm, chỉ cần stream bằng `hasMoreEvents/readEvent` và tăng một biến `long`.

**Bài 2.** Bạn thấy `event.hasField("path") == true` nhưng `event.getString("path")` trả `null`. Hai kết quả có mâu thuẫn không?

*Trả lời:* Không. `hasField` xác nhận schema chứa field; giá trị của field có thể null.

**Bài 3.** Có thể gọi `event.getDuration("duration")` để đọc thời lượng của mọi event thay vì `event.getDuration()` không?

*Trả lời:* Không nên. `getDuration()` không tham số là API dành cho duration của event. Bản có tên field đọc một **timespan field** theo schema; không được tự mặc định tên field phù hợp trong mọi type.

**Bài 4.** Muốn xuất số byte đọc file từ `jdk.FileRead`, có thể luôn gọi `getLong("bytes")` không?

*Trả lời:* Không. Phải kiểm tra schema của JDK đang dùng để biết tên và kiểu field (có thể là `bytesRead` hoặc trường khác), rồi dùng getter phù hợp; code ví dụ chỉ chắc chắn về `bytes` của custom event `demo.Request`.

**Bài 5.** Sau khi file đã được ghi với `stackTrace=false`, có thể tăng `jfr print --stack-depth=100` để thấy call stack không?

*Trả lời:* Không. Công cụ chỉ hiển thị dữ liệu đã ghi; cần tạo recording mới bật stack trace cho event thích hợp.

**Bài 6.** `readEventTypes()` cho thấy event type `jdk.JavaMonitorEnter` nhưng vòng đọc không gặp instance nào. Có phải code hỏng?

*Trả lời:* Chưa chắc. Metadata có thể hiện diện dù số event thực tế là 0; cần xem `jfr summary`, cấu hình enabled/threshold, cửa sổ ghi, workload và filter type.

**Bài 7.** Hai event kéo dài 30 ms và 40 ms trên hai thread cùng thời điểm. Có thể nói ứng dụng đã dừng 70 ms không?

*Trả lời:* Không. Duration có thể chồng nhau, và hai event không mặc định là global stop-the-world. Phải hiểu semantics của từng type và timeline.

## 14. Checklist khi xây công cụ đọc JFR

- [ ] Chỉ chấp nhận file `.jfr` hợp lệ, nguồn và đường dẫn đáng tin; dùng `try-with-resources`.
- [ ] Dùng `hasMoreEvents()` trước `readEvent()`; hiểu `IOException`/`EOFException`.
- [ ] Lọc bằng **event type name**, không nhầm label hoặc tên class Java của parser.
- [ ] Dùng `hasField` và `getFields`/`ValueDescriptor` cho field không chắc chắn.
- [ ] Chọn đúng typed getter; phân biệt field vắng mặt, field null và số 0.
- [ ] Phân biệt `getDuration()` của event với `getDuration("field")`; luôn ghi đơn vị.
- [ ] Xử lý `RecordedThread` và `RecordedStackTrace` có thể null.
- [ ] Với file lớn, dùng streaming/aggregate có giới hạn, không giữ tất cả event.
- [ ] Đối chiếu bằng `jfr summary`, `jfr metadata` và `jfr print` khi schema không chắc chắn.
- [ ] Khi tổng hợp, lưu context về JDK, recording, time window, threshold, sampling, thread.
- [ ] Bảo vệ dữ liệu nhạy cảm; giới hạn log/export và không coi file JFR là dữ liệu công khai.

**Ghi nhớ:** `RecordingFile` trả về một chuỗi `RecordedEvent`. Muốn xử lý chính xác, hãy làm theo thứ tự **mở file → duyệt → nhận diện type → kiểm tra schema → đọc field đúng kiểu → tổng hợp → đóng file**. Một `RecordedEvent` là bằng chứng của **sự kiện đã được ghi**; hiểu được gì từ nó còn phụ thuộc định nghĩa event, cấu hình JFR và ngữ cảnh runtime.

## Tài liệu đối chiếu (JDK 21)

- Oracle, [`RecordingFile`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): `readEvent`, `hasMoreEvents`, `readEventTypes`, `readAllEvents` và đóng file.
- Oracle, [`RecordedEvent`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): timestamp, duration, thread, stack và event type.
- Oracle, [`RecordedObject`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): `hasField`, typed getters, `getValue` và nested fields.
- Oracle, [`RecordedThread`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedThread.html): Java/OS thread metadata.
- Oracle, [`RecordedStackTrace`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedStackTrace.html) và [`RecordedFrame`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedFrame.html): frame, line number và truncated stack.
- Oracle, [`ValueDescriptor`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/ValueDescriptor.html): field name, type và metadata.
- Oracle, [`Recording`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): tạo và dump recording.
- Oracle, [`jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): `summary`, `metadata`, `print`.