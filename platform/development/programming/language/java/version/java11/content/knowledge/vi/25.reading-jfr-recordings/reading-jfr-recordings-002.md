# RecordedEvent và thông tin thời điểm, thời lượng trong JFR (Java 11+)

**Chủ đề cha: Đọc bản ghi JFR.** Khi đọc file Java Flight Recorder (JFR), điều hữu ích không chỉ là biết “có bao nhiêu sự kiện”, mà còn phải hiểu **sự kiện xảy ra lúc nào, kết thúc lúc nào, kéo dài bao lâu**. API `jdk.jfr.consumer.RecordedEvent` hỗ trợ trực tiếp ba thao tác này:

- `getStartTime()` trả `java.time.Instant` biểu diễn thời điểm bắt đầu.
- `getEndTime()` trả `java.time.Instant` biểu diễn thời điểm kết thúc.
- `getDuration()` trả `java.time.Duration` biểu diễn khoảng thời gian tồn tại của sự kiện.

Các API trên có từ JFR được cung cấp trong JDK và **vẫn được hỗ trợ trong Java hiện đại**, bao gồm Java 11 trở lên. Bài này dùng ví dụ chạy được trên **JDK 11+**, không dùng phương pháp chẩn đoán thuộc các phiên bản JDK lỗi thời. Ta sẽ phân biệt sự kiện tức thời và sự kiện có thời lượng, đọc `.jfr` bằng `RecordingFile`, tính số liệu thời gian đúng đơn vị, định dạng theo múi giờ, kiểm tra event fields có annotation thời gian riêng, và tránh kết luận sai khi phân tích hiệu năng production.

## 1. Một RecordedEvent đại diện cho điều gì?

JFR ghi một tập **events có cấu trúc**. Mỗi sự kiện mô tả một lần xuất hiện của một hiện tượng, chẳng hạn:

- Một GC pause hoặc một pha xử lý có thời lượng.
- Một lần thread bị block/park hoặc chờ monitor.
- Một thời điểm lấy mẫu CPU, trạng thái heap, compiler event.
- Một custom event do ứng dụng khai báo bằng `jdk.jfr.Event`.

Khi đọc file `.jfr`, mỗi event được biểu diễn bởi một object `RecordedEvent`. Nó kế thừa `RecordedObject` để hỗ trợ truy cập các trường đã ghi.

```text
File .jfr
   |
   v
RecordingFile.hasMoreEvents()
   |
   v
RecordingFile.readEvent()
   |
   v
RecordedEvent
   |
   +-- getEventType().getName() --> "jdk.GarbageCollection" / "demo.Work"
   +-- getStartTime() ---------> Instant
   +-- getEndTime() -----------> Instant
   +-- getDuration() ----------> Duration
   +-- getThread() ------------> RecordedThread hoặc null
   +-- getStackTrace() --------> RecordedStackTrace hoặc null
   +-- getValue("field") ------> dữ liệu riêng từng loại event
```

**Quan trọng:** `RecordedEvent` chỉ là **dữ liệu đã thu**, không phải một đối tượng còn sống có thể gọi `begin()`/`end()` để thay đổi thời gian. `begin()`, `end()` và `commit()` thuộc lớp `jdk.jfr.Event` ở phía **tạo sự kiện**. `RecordedEvent` dùng ở phía **đọc bản ghi**.

## 2. Ba phương thức thời gian và kiểu trả về

| Phương thức | Kiểu Java | Ý nghĩa | Có thể `null` không? |
| --- | --- | --- | --- |
| `getStartTime()` | `Instant` | Thời điểm bắt đầu event | Không, theo Javadoc |
| `getEndTime()` | `Instant` | Thời điểm kết thúc event | Không, theo Javadoc |
| `getDuration()` | `Duration` | Thời lượng event, độ phân giải biểu diễn theo nanosecond | Không, theo Javadoc |

Ba đối tượng thời gian thuộc **`java.time`**, không phải `java.util.Date`. Không cần chuyển về `Date`, `Calendar` hay `System.currentTimeMillis()` để thao tác thông thường.

Đoạn code đọc một `RecordedEvent event` đã có:

```java
Instant start = event.getStartTime();
Instant end = event.getEndTime();
Duration elapsed = event.getDuration();

System.out.println("start (UTC): " + start);
System.out.println("end   (UTC): " + end);
System.out.println("duration ms: " + elapsed.toMillis());
```

**Đây là đoạn minh họa**, chưa phải chương trình độc lập. Cần `import java.time.Instant;`, `import java.time.Duration;` và biến `event` từ `RecordingFile`.

### Instant và Duration khác nhau

- **`Instant`** là một **điểm trên dòng thời gian**, ví dụ `2026-11-07T08:15:30Z`. Nó không tự mang múi giờ địa phương của người đọc.
- **`Duration`** là một **lượng thời gian**, ví dụ 15 ms, 2.5 giây, 1 phút. Nó không phải timestamp.
- **`LocalDateTime`** không có offset/time zone, nên không thích hợp thay thế `Instant` khi lưu thời điểm thực của event.
- **`Period`** biểu diễn lịch tháng/ngày, không phải loại cần dùng cho latency sự kiện.

Ví dụ:

```text
Bắt đầu 2026-11-07T08:15:30.000Z
Kết thúc 2026-11-07T08:15:30.250Z
Thời lượng = PT0.25S = 250 ms
```

Trong phân tích, nên giữ `Instant`/`Duration` đến lúc hiển thị. Chỉ định dạng thành chuỗi theo timezone khi người dùng thực sự cần đọc.

## 3. Event tức thời và event có thời lượng

Javadoc Java 11 quy định: nếu một event là **instant event**, `getStartTime()` và `getEndTime()` trả cùng thời điểm.

| Loại | Cách hiểu | Quan hệ start/end | Duration thường gặp |
| --- | --- | --- | --- |
| **Instant event** | Đánh dấu một thời điểm, ví dụ một sự kiện trạng thái/sampling | `start.equals(end)` | `Duration.ZERO` |
| **Duration event** | Theo dõi một hoạt động có khoảng bắt đầu–kết thúc | `end` không trước `start` | Thường dương; có thể rất nhỏ hoặc 0 |
| **Event bị threshold lọc** | Không được ghi vào file | Không có `RecordedEvent` để đọc | Không kết luận được từ dữ liệu vắng mặt |
| **Event không được bật** | Không ghi | Không có bản ghi | Không chứng minh hoạt động không xảy ra |

Với custom event của ứng dụng:

```java
WorkEvent e = new WorkEvent();
e.begin();
// Xử lý công việc.
e.end();
e.commit();
```

thường tạo một **duration event**. Ngược lại:

```java
MarkerEvent e = new MarkerEvent();
e.commit();
```

tạo một **instant event**. Hai đoạn này minh họa phần phát event, cần khai báo các class `WorkEvent`/`MarkerEvent` kế thừa `jdk.jfr.Event`.

Theo Javadoc `Event`, nếu đã gọi `begin()` nhưng chưa gọi `end()` thì `commit()` tự kết thúc thời gian. Tuy nhiên, dùng `begin() → try/finally → end() → commit()` thường dễ đọc hơn khi đo một tác vụ có ranh giới rõ ràng.

### Duration.ZERO không đồng nghĩa “không có tác vụ”

Nếu `getDuration().isZero()` thì có thể là instant event, hoặc một duration event quá ngắn so với độ phân giải thực tế được ghi. Không chỉ dựa vào duration=0 để kết luận tác vụ “không chạy”. Cần xem **event type** và semantics của chính loại sự kiện.

## 4. Phép tính thời gian nào là đúng?

Giả sử đã có:

```java
Instant start = event.getStartTime();
Instant end = event.getEndTime();
Duration duration = event.getDuration();
```

Những thao tác hữu ích:

```java
boolean validOrder = !end.isBefore(start);
boolean slow = duration.compareTo(Duration.ofMillis(100)) > 0;
long wholeMillis = duration.toMillis();
double milliseconds =
        duration.getSeconds() * 1_000.0 + duration.getNano() / 1_000_000.0;
```

Đây là **đoạn minh họa**, cần import `java.time.Duration`/`Instant`.

**Những điểm cần nhớ:**

1. `Duration.toMillis()` trả **số mili-giây nguyên**, bỏ phần lẻ. Duration 1.9 ms sẽ cho `1`, không phải `1.9`.
2. `Duration.toNanos()` có thể **overflow** nếu duration rất lớn; không giả định nó luôn nằm trong `long` ở mọi dữ liệu.
3. `getDuration()` trả một `Duration` biểu diễn đơn vị ở độ phân giải nanosecond, **không bảo đảm đồng hồ thực đo chính xác từng nanosecond**.
4. So sánh threshold nên dùng `Duration.compareTo(...)`, không chuyển sớm sang `toMillis()` khiến thông tin dưới 1 ms biến mất.
5. Khi chỉ cần thời lượng của event, ưu tiên **`event.getDuration()`**. Không tự lấy `System.currentTimeMillis()` lúc đọc file rồi trừ timestamp của event; phép trừ đó là “tuổi của event”, không phải thời lượng xử lý.

### Có phải Duration.between(start, end) luôn trùng từng nano?

Với một event thông thường, `getDuration()` liên quan đến khoảng `start → end`. Nhưng dữ liệu từ hệ thống ghi hiệu năng có thể trải qua phép chuyển đổi clock/tick/timestamp. Đối với các phân tích cần độ chính xác nhỏ nhất, **không nên bắt buộc hai biểu thức dưới đây bằng nhau từng nanosecond** trên mọi JDK/provider/JFR recording:

```java
event.getDuration();
Duration.between(event.getStartTime(), event.getEndTime());
```

Chúng có thể rất gần nhau. Nếu muốn đánh giá duration theo sự kiện đã ghi, **dùng chính `getDuration()`**. Nếu muốn vẽ timeline bằng các điểm thời gian, dùng `getStartTime()`/`getEndTime()`. Không biến sai khác do phép quy đổi thời gian thành kết luận sai về hiệu năng.

## 5. Ví dụ độc lập: ghi và đọc chính hai loại event

Chương trình sau chạy trong **một JVM**: ghi một timed event, ghi một instant event, dừng recording, dump ra file, rồi dùng `RecordingFile` đọc lại và kiểm tra hợp đồng các phương thức thời gian.

### Tệp `JfrRecordedEventTimesDemo.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;

import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrRecordedEventTimesDemo {

    @Name("demo.TimedWork")
    static final class TimedWork extends Event {
        long jobId;
    }

    @Name("demo.InstantMarker")
    static final class InstantMarker extends Event {
        String label;
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("jfr-time-example-");
        Path file = dir.resolve("events.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(TimedWork.class)
                    .withThreshold(Duration.ZERO);
            recording.enable(InstantMarker.class)
                    .withThreshold(Duration.ZERO);
            recording.start();

            TimedWork work = new TimedWork();
            work.jobId = 42L;
            work.begin();
            Thread.sleep(30);
            work.end();
            work.commit();

            InstantMarker marker = new InstantMarker();
            marker.label = "after-job";
            marker.commit();

            recording.stop();
            recording.dump(file);
        }

        int workCount = 0;
        int markerCount = 0;
        boolean validOrder = true;
        boolean validDuration = true;
        boolean instantSameTime = true;
        boolean instantZeroDuration = true;

        try (RecordingFile reader = new RecordingFile(file)) {
            while (reader.hasMoreEvents()) {
                RecordedEvent event = reader.readEvent();
                String type = event.getEventType().getName();

                if ("demo.TimedWork".equals(type)) {
                    workCount++;
                    Instant start = event.getStartTime();
                    Instant end = event.getEndTime();
                    Duration duration = event.getDuration();

                    validOrder &= !end.isBefore(start);
                    validDuration &= !duration.isNegative();
                } else if ("demo.InstantMarker".equals(type)) {
                    markerCount++;
                    instantSameTime &=
                            event.getStartTime().equals(event.getEndTime());
                    instantZeroDuration &= event.getDuration().isZero();
                }
            }
        }

        if (workCount != 1 || markerCount != 1
                || !validOrder || !validDuration
                || !instantSameTime || !instantZeroDuration) {
            throw new AssertionError("Recorded event timing mismatch");
        }

        System.out.println("timed events: " + workCount);
        System.out.println("instant events: " + markerCount);
        System.out.println("timed chronological: " + validOrder);
        System.out.println("timed duration nonnegative: " + validDuration);
        System.out.println("instant same start/end: " + instantSameTime);
        System.out.println("instant zero duration: " + instantZeroDuration);
    }
}
```

Chạy trên JDK 11+ có module `jdk.jfr`:

```bash
javac --release 11 -encoding UTF-8 JfrRecordedEventTimesDemo.java
java JfrRecordedEventTimesDemo
```

Stdout mong đợi khi JFR và filesystem hoạt động bình thường:

```text
timed events: 1
instant events: 1
timed chronological: true
timed duration nonnegative: true
instant same start/end: true
instant zero duration: true
```

**Giải thích:**

- `Thread.sleep(30)` tạo một khoảng thời gian có thể quan sát, nhưng **không cam kết chính xác 30 ms** do scheduling, GC và môi trường. Vì thế chương trình không assertion duration bằng 30 ms.
- `recording.enable(...).withThreshold(Duration.ZERO)` bật riêng hai custom event types và bỏ ngưỡng lọc duration cho bài test.
- `recording.stop()` rồi `recording.dump(file)` tạo một file ở **thư mục tạm** được cấp bởi OS; đường dẫn thay đổi nên không in ra stdout cố định.
- `RecordedEvent.getEventType().getName()` giúp lọc đúng event; có thể file còn chứa JVM events khác.
- `try-with-resources` đóng `Recording` và `RecordingFile`. File thực hành có thể được xóa theo chính sách sau khi kiểm tra.
- Đây là test trên JDK thông thường; môi trường bị vô hiệu hóa JFR, thiếu module hoặc hạn chế ghi tệp cần được cấu hình lại có quyền, không sửa API để “cho qua”.

**Nhớ:** `Event.begin()/end()/commit()` dùng khi **phát sự kiện**, còn `RecordedEvent.getStartTime()/getEndTime()/getDuration()` dùng khi **đọc**.

## 6. Đọc tệp JFR bất kỳ bằng RecordingFile

Với bản ghi đã được thu, ví dụ:

```bash
jcmd 12345 JFR.start name=incident settings=profile duration=60s filename=/var/tmp/incident.jfr
```

Sau khi recording hoàn tất, dùng `jdk.jfr.consumer.RecordingFile` đọc lần lượt các events.

### Tệp `JfrTimelineReader.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrTimelineReader {
    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ISO_OFFSET_DATE_TIME;

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java JfrTimelineReader file.jfr eventType");
        }

        Path path = Path.of(args[0]);
        String wantedType = args[1];

        if (!Files.isRegularFile(path)) {
            throw new IllegalArgumentException("Not a regular JFR file");
        }

        ZoneId displayZone = ZoneId.of("Asia/Ho_Chi_Minh");
        long count = 0;
        Instant earliest = null;
        Instant latest = null;
        Duration longest = Duration.ZERO;

        try (RecordingFile reader = new RecordingFile(path)) {
            while (reader.hasMoreEvents()) {
                RecordedEvent event = reader.readEvent();
                if (!wantedType.equals(event.getEventType().getName())) {
                    continue;
                }

                Instant start = event.getStartTime();
                Instant end = event.getEndTime();
                Duration duration = event.getDuration();

                if (earliest == null || start.isBefore(earliest)) {
                    earliest = start;
                }
                if (latest == null || end.isAfter(latest)) {
                    latest = end;
                }
                if (duration.compareTo(longest) > 0) {
                    longest = duration;
                }

                if (count < 5) {
                    System.out.println("start=" +
                            FORMAT.format(start.atZone(displayZone))
                            + " duration=" + duration);
                }
                count++;
            }
        }

        System.out.println("events matched: " + count);
        if (count > 0) {
            System.out.println("earliest UTC: " + earliest);
            System.out.println("latest UTC: " + latest);
            System.out.println("longest duration: " + longest);
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 JfrTimelineReader.java
java JfrTimelineReader /var/tmp/incident.jfr jdk.GarbageCollection
```

Output phụ thuộc bản ghi, JVM, timezone và loại event; **không có số liệu cố định**. Nếu muốn dùng custom type trong ví dụ mục trước, trỏ đúng file ở thư mục tạm hoặc sửa demo lưu về đường dẫn dễ chỉ định.

**Tại sao `count < 5` không phải “5 events đầu tiên theo thời điểm”?** Đây là **5 events đầu tiên theo thứ tự reader cung cấp**, không hứa đã được sắp theo `getStartTime()` ở mọi tình huống hoặc phiên bản. Cần biểu đồ timeline được sắp chính xác, hãy thu thập/ngoại sắp các mốc có kiểm soát rồi sort theo `Instant`, hoặc dùng công cụ phân tích chuyên dụng.

**Tại sao giữ min/max?** `earliest` và `latest` cho biết khoảng phủ của **những events khớp bộ lọc**, không phải thời điểm bắt đầu/kết thúc toàn recording. Nếu loại event đó chỉ xuất hiện vài lần, khoảng này có thể rất hẹp dù recording kéo dài hàng phút.

### Không gom toàn bộ file vào heap khi không cần

`RecordingFile.readAllEvents(path)` tồn tại và tiện cho file nhỏ, nhưng Oracle ghi rõ không dành cho file lớn. Với file hàng trăm MB hoặc nhiều triệu events, nên dùng:

```java
try (RecordingFile reader = new RecordingFile(path)) {
    while (reader.hasMoreEvents()) {
        RecordedEvent event = reader.readEvent();
        // Xử lý từng event rồi bỏ tham chiếu.
    }
}
```

Đây là **đoạn minh họa**, biến `path` phải là `Path` hợp lệ. Cách đọc tuần tự giúp tránh tạo một `List<RecordedEvent>` lớn trong ứng dụng của người phân tích.

## 7. Múi giờ: Instant của JFR không phải LocalDateTime

Thời điểm event được cung cấp dưới dạng `Instant`. Khi in bằng `toString()`, thường xuất hiện dạng ISO 8601 có ký hiệu `Z`, tức là mốc UTC. Người vận hành ở Việt Nam có thể muốn hiển thị giờ địa phương **UTC+07:00**:

```java
Instant instant = event.getStartTime();
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

String text = DateTimeFormatter.ISO_OFFSET_DATE_TIME
        .format(instant.atZone(zone));
```

Đây là đoạn minh họa với import `java.time.Instant`, `ZoneId` và `DateTimeFormatter`.

**Phân biệt:**

| Kiểu/giá trị | Có thông tin múi giờ? | Dùng cho |
| --- | --- | --- |
| `Instant` | Mốc tuyệt đối, không mang địa điểm cụ thể | Lưu và so sánh thời điểm event |
| `ZonedDateTime` | Có `ZoneId` và quy tắc offset | Hiển thị theo múi giờ yêu cầu |
| `OffsetDateTime` | Có offset cụ thể | Trao đổi timestamp có offset |
| `LocalDateTime` | Không có offset/zone | Lịch địa phương, không đủ để định danh mốc tuyệt đối |
| `Duration` | Không phải timestamp | Đo thời lượng |

Ví dụ cố định, độc lập với timezone mặc định của máy:

```java
import java.time.Instant;
import java.time.ZoneId;

public class JfrZoneExample {
    public static void main(String[] args) {
        Instant time = Instant.parse("2026-11-07T08:30:00Z");

        System.out.println(time);
        System.out.println(time.atZone(
                ZoneId.of("Asia/Ho_Chi_Minh")).toLocalTime());
    }
}
```

```bash
javac --release 11 -encoding UTF-8 JfrZoneExample.java
java JfrZoneExample
```

```text
2026-11-07T08:30:00Z
15:30
```

Nội dung hiển thị sẽ đổi nếu dùng `ZoneId` khác, nhưng **Instant gốc vẫn cùng một mốc**. Không cộng tay 7 giờ vào một chuỗi để “đổi timestamp”, cũng không lấy timezone mặc định của máy phân tích làm bằng chứng máy ghi JFR dùng cùng timezone.

## 8. Thời gian event và những trường thời gian trong payload là hai việc khác nhau

`RecordedEvent.getDuration()` trả **thời lượng chính event**. Nhưng một event còn có thể mang **các field nghiệp vụ** như deadline, thời điểm gửi yêu cầu hoặc timeout do ứng dụng tự ghi.

Ví dụ một custom event có:

```text
Event timing: start=... end=... duration=35 ms
Payload field: requestBudgetMillis=750
Payload field: submittedAtEpochMillis=1700000000000
```

Trong trường hợp này:

- `getDuration()` là thời gian **event diễn ra**.
- `getDuration("requestBudgetMillis")` có thể chuyển một field được đánh dấu `@Timespan` thành `Duration`.
- `getInstant("submittedAtEpochMillis")` có thể chuyển một field được đánh dấu `@Timestamp` thành `Instant`.
- **750 ms là ngân sách/timeout nghiệp vụ**, không phải duration thực tế. Không được nhầm hai con số.

Lớp cơ sở `RecordedObject` cung cấp `getInstant(String)` và `getDuration(String)`. Chúng **khác** với hai phương thức không tham số trên `RecordedEvent`.

### Các annotation thời gian được Java 11 hỗ trợ

- `@Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)`: giá trị field kiểu số biểu diễn mili-giây từ Unix epoch.
- `@Timestamp(Timestamp.TICKS)`: số ticks theo cơ chế thời gian nội bộ của JFR; không tự đổi nó thành epoch millis.
- `@Timespan(Timespan.MILLISECONDS)`: giá trị field biểu diễn một khoảng thời gian bằng mili-giây.
- `@Timespan(Timespan.NANOSECONDS)`, `MICROSECONDS`, `SECONDS`: các đơn vị khác cho field dạng timespan.
- Với field thời gian có annotation, dùng getter có kiểu phù hợp để JFR chuyển về `Instant`/`Duration`.

**Không gắn annotation và getter một cách tùy tiện:** `getInstant("field")` yêu cầu trường có thông tin timestamp phù hợp; `getDuration("field")` yêu cầu field timespan phù hợp. Các field tên giống nhau ở hai loại event khác nhau có thể có kiểu/annotation/đơn vị khác nhau.

## 9. Ví dụ độc lập: @Timestamp và @Timespan trong payload

Chương trình sau tạo một **instant event** mang thêm hai trường: thời điểm nghiệp vụ cố định và timeout 750 ms. Ta đọc lại chính xác bằng getters có tên field để thấy rõ chúng **không phải** `getStartTime()/getDuration()` của event.

### Tệp `JfrAnnotatedTimeFields.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;

import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.Timestamp;
import jdk.jfr.Timespan;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrAnnotatedTimeFields {

    @Name("demo.BusinessTiming")
    static final class BusinessTiming extends Event {
        @Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)
        long submittedAtEpochMillis;

        @Timespan(Timespan.MILLISECONDS)
        long budgetMillis;
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("jfr-fields-");
        Path file = dir.resolve("fields.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(BusinessTiming.class)
                    .withThreshold(Duration.ZERO);
            recording.start();

            BusinessTiming event = new BusinessTiming();
            event.submittedAtEpochMillis = 1_700_000_000_000L;
            event.budgetMillis = 750L;
            event.commit();

            recording.stop();
            recording.dump(file);
        }

        int matched = 0;
        try (RecordingFile reader = new RecordingFile(file)) {
            while (reader.hasMoreEvents()) {
                RecordedEvent event = reader.readEvent();
                if (!"demo.BusinessTiming".equals(
                        event.getEventType().getName())) {
                    continue;
                }

                matched++;
                Instant businessTime =
                        event.getInstant("submittedAtEpochMillis");
                Duration budget = event.getDuration("budgetMillis");

                System.out.println("business instant: " + businessTime);
                System.out.println("budget ms: " + budget.toMillis());
                System.out.println("JFR event itself instantaneous: "
                        + event.getStartTime().equals(event.getEndTime()));
            }
        }

        if (matched != 1) {
            throw new AssertionError("Expected one business event");
        }
        System.out.println("matched events: " + matched);
    }
}
```

```bash
javac --release 11 -encoding UTF-8 JfrAnnotatedTimeFields.java
java JfrAnnotatedTimeFields
```

Stdout mong đợi trên JDK 11+ có JFR:

```text
business instant: 2023-11-14T22:13:20Z
budget ms: 750
JFR event itself instantaneous: true
matched events: 1
```

**Lý do output cố định:** con số `1_700_000_000_000L` được cố tình đặt thành một **mốc giả định phục vụ kiểm thử**, không phải thời điểm event được JFR thực sự ghi. `event.getStartTime()` vẫn là thời gian chạy chương trình tại máy; ở đây ta **không in** mốc đó để stdout ổn định. `budgetMillis = 750` là mức timeout do code gán, không phải thời lượng xử lý.

**Vì sao dùng hai getter có cùng tên “Duration”?**

```java
event.getDuration();                 // Thời lượng của chính JFR event.
event.getDuration("budgetMillis");   // Field @Timespan trong payload.
```

Một bên là metadata JFR, một bên là dữ liệu do application cung cấp. Cần chỉ rõ tên field và semantic của nó trước khi tính metrics.

## 10. Đọc các field một cách bền vững qua nhiều JDK

Các event có tên/type khác nhau có **schema riêng**. Một số trường của JDK events có thể thay đổi, bị loại bỏ hoặc khác về nội dung giữa các bản JDK. Oracle khuyến nghị kiểm tra sự tồn tại của field trước khi truy cập.

```java
if (event.hasField("duration")) {
    Object raw = event.getValue("duration");
    System.out.println("raw duration field: " + raw);
}

if (event.hasField("message")) {
    String message = event.getString("message");
    System.out.println(message);
}
```

Đây là đoạn minh họa; không phải mọi event đều có `duration` hay `message`. `hasField("name")` chỉ kiểm tra tên field; **không tự xác minh kiểu field**. Getter kiểu mạnh có thể ném `IllegalArgumentException` nếu field không tồn tại hoặc không chuyển đổi được như yêu cầu.

Khi viết một JFR parser dùng lâu dài:

1. Lọc bằng `event.getEventType().getName()`; không dùng `event.toString().contains(...)` để phân loại.
2. Với thông tin bắt đầu/kết thúc/thời lượng phổ quát, dùng **ba method của `RecordedEvent`** thay vì đoán tên field.
3. Chỉ lấy các business fields khi `hasField(...)` và khi schema phù hợp.
4. Dùng `event.getFields()` hoặc `event.getEventType().getFields()` để khám phá metadata nếu thật sự cần parser linh hoạt.
5. Không giả định `getThread()` và `getStackTrace()` luôn khác `null`; chúng có thể không được thu trong recording.
6. Không gộp một field timespan thành đồng hồ lịch nếu nó chỉ là duration.

### Ví dụ khác biệt giữa field và event metadata

| Biểu thức | Đọc gì? |
| --- | --- |
| `event.getStartTime()` | Mốc bắt đầu event, luôn có khi đọc một RecordedEvent hợp lệ |
| `event.getEndTime()` | Mốc kết thúc event |
| `event.getDuration()` | Thời lượng event |
| `event.getInstant("createdAt")` | Field timestamp tên `createdAt` nếu có annotation thích hợp |
| `event.getDuration("budget")` | Field timespan tên `budget` nếu có annotation thích hợp |
| `event.getLong("budget")` | Giá trị long thô của field, chưa chuyển theo unit |
| `event.hasField("budget")` | Có tồn tại field tên `budget` hay không |
| `event.getEventType().getName()` | Tên loại event, ví dụ `demo.BusinessTiming` |

Không nên chuyển timestamp raw bằng `Instant.ofEpochMilli(raw)` khi annotation báo `@Timestamp(TICKS)`; ticks có ý nghĩa và cơ chế quy đổi khác epoch millis. Dùng getter semantic `getInstant("field")` khi metadata được ghi đúng.

## 11. Thời điểm và thời lượng trong nhiều loại JDK events

Không phải mọi event có semantics “request latency”:

| Event ví dụ | Thời gian thường biểu diễn | Lưu ý phân tích |
| --- | --- | --- |
| `jdk.GarbageCollection` | Khoảng GC event được ghi nhận | Không đồng nghĩa toàn bộ ứng dụng stop-the-world trong đúng khoảng này |
| `jdk.GCPhasePause` | Một pha pause cụ thể | Xem loại GC và mối quan hệ với event khác |
| `jdk.JavaMonitorEnter` | Thời gian chờ vào monitor, khi được bật/qua threshold | Cần xem thread/stack/lock, không suy trực tiếp business latency |
| `jdk.ThreadPark` | Thời gian thread ở trạng thái park | Có thể do scheduler/concurrency bình thường |
| `jdk.SocketRead` / `jdk.SocketWrite` | Khoảng I/O được ghi nếu event bật | Không tự biểu diễn toàn bộ HTTP request/response |
| `jdk.CPULoad` | Event theo chu kỳ để lấy mẫu CPU | Là measurement/sampling, không phải một request kéo dài theo duration |
| Custom `demo.TimedWork` | Khoảng code gọi `begin/end` | Phụ thuộc việc ứng dụng đặt ranh giới đo đúng |

Tên event và trường cụ thể cần được kiểm chứng từ **file thực tế**, JDK version và event metadata. Không dùng thời lượng một event JDK làm bằng chứng duy nhất để kết luận về mọi tầng của request (DNS, TLS, queue, database, rendering).

Một sự kiện `ThreadPark` có thể kéo dài lâu nhưng không phải CPU đang làm việc; một event `CPULoad` có thể là measurement tức thời/periodic. **Duration của event có ý nghĩa dựa vào event type**, không phải một quy tắc kinh doanh cố định.

## 12. Threshold và sampling ảnh hưởng thế nào đến dữ liệu thời gian?

JFR có các setting phổ biến:

- **`enabled`:** event type có được phép ghi hay không.
- **`threshold`:** với duration events, mức tối thiểu mà event phải đạt để được ghi.
- **`period`:** chu kỳ emission của một số periodic events.
- **`stackTrace`:** có thu stack trace không.
- Các tùy chọn khác tùy event/JDK.

Ví dụ mã Java:

```java
recording.enable(TimedWork.class)
        .withThreshold(Duration.ofMillis(20));
```

**Đây là đoạn minh họa**, cần đối tượng `Recording recording` và event type `TimedWork`.

Khi đó những timed events dưới threshold có thể **không xuất hiện** trong recording. Điều này ảnh hưởng thống kê:

- Nếu chỉ thu các task dài hơn 20 ms, trung bình duration các **events nhìn thấy** sẽ lệch so với trung bình của **toàn bộ task thực tế**.
- Việc có 0 events trên 1 giây không chứng minh ứng dụng không làm việc trong giây đó.
- Không dùng count của các duration events có threshold như số request hoàn chỉnh nếu chưa biết sampling/configuration.
- Stack traces không có không có nghĩa event không hợp lệ; có thể stack capture đã tắt hoặc không áp dụng.

Khi phân tích production, hãy ghi nhận file JFR được thu bằng **settings nào**, trong **cửa sổ thời gian nào**, và các loại event nào đang bật. Thống kê chỉ có ý nghĩa khi xét đến chính sách thu.

## 13. Tính tổng, trung bình, min, max duration theo loại event

Một bài toán thường gặp: “Trong file JFR này, những event cùng type có thời lượng trung bình, dài nhất và ngắn nhất bao nhiêu?”

**Trước hết quyết định có tính cả instant events hay không.** Nếu trộn các event tức thời duration 0 với duration events, trung bình dễ bị kéo xuống nhưng không phản ánh latency xử lý.

### Tệp `JfrDurationStats.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;

import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrDurationStats {

    static double milliseconds(Duration value) {
        return value.getSeconds() * 1000.0
                + value.getNano() / 1_000_000.0;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java JfrDurationStats file.jfr type");
        }

        Path file = Path.of(args[0]);
        String type = args[1];
        if (!Files.isRegularFile(file)) {
            throw new IllegalArgumentException("Missing file");
        }

        long count = 0;
        Duration total = Duration.ZERO;
        Duration min = null;
        Duration max = null;
        Instant firstStart = null;
        Instant lastEnd = null;

        try (RecordingFile reader = new RecordingFile(file)) {
            while (reader.hasMoreEvents()) {
                RecordedEvent event = reader.readEvent();
                if (!type.equals(event.getEventType().getName())) {
                    continue;
                }

                Duration elapsed = event.getDuration();
                total = total.plus(elapsed);
                count++;

                if (min == null || elapsed.compareTo(min) < 0) {
                    min = elapsed;
                }
                if (max == null || elapsed.compareTo(max) > 0) {
                    max = elapsed;
                }

                Instant start = event.getStartTime();
                Instant end = event.getEndTime();
                if (firstStart == null || start.isBefore(firstStart)) {
                    firstStart = start;
                }
                if (lastEnd == null || end.isAfter(lastEnd)) {
                    lastEnd = end;
                }
            }
        }

        System.out.println("count: " + count);
        if (count != 0) {
            System.out.println("min: " + min);
            System.out.println("max: " + max);
            System.out.println("avg ms: " + milliseconds(total) / count);
            System.out.println("first start: " + firstStart);
            System.out.println("last end: " + lastEnd);
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 JfrDurationStats.java
java JfrDurationStats /var/tmp/incident.jfr jdk.ThreadPark
```

**Không thể đưa stdout cố định**: kết quả phụ thuộc file, số events, thresholds và workload. Bộ thống kê này giữ **O(1) trạng thái**, không tích lũy mọi `RecordedEvent` trong RAM.

**Giới hạn quan trọng:** cộng rất nhiều `Duration` có thể overflow nếu tổng lớn ngoài miền biểu diễn. Với file cực lớn hoặc phân tích dài hạn, cần kiểm soát số events/duration hoặc dùng chiến lược tích lũy phù hợp (ví dụ phân đoạn có giới hạn, số học được kiểm soát). Trung bình ở trên là **trung bình các events được thu**, không tự là trung bình của mọi thao tác nghiệp vụ.

### Vấn đề trùng thời gian

Hai events có thể **overlap**, ví dụ task A và task B chạy cùng lúc ở hai threads. Khi đó:

```text
Task A: |----------- 100 ms -----------|
Task B:       |------ 70 ms ------|
Wall-clock coverage: 100 ms
Sum of durations:   170 ms
```

Vì vậy, **tổng duration không phải elapsed wall-clock time** của cả recording. Nếu muốn tính thời gian bị chiếm dụng bởi một tài nguyên, cần hiểu tính song song và loại event; không tự cộng mọi duration rồi nói “ứng dụng đã dừng 170 ms”.

## 14. Cross-process timeline: đồng hồ và giới hạn độ chính xác

Thời điểm `Instant` tiện để đối chiếu JFR với log/metrics của service. Tuy nhiên, nếu so timestamps **giữa nhiều JVM hoặc nhiều host**, cần chú ý:

1. Đồng hồ hệ thống của các host có thể lệch dù đều trả timestamp theo UTC.
2. NTP/time synchronization có thể điều chỉnh clock; độ chính xác không phải tuyệt đối.
3. Mỗi file JFR có ranh giới thời gian riêng; event chỉ có mặt khi recording thực sự hoạt động.
4. File có thể được thu trong timezone khác nhưng `Instant` vẫn diễn đạt một mốc trên dòng thời gian; timezone chỉ ảnh hưởng **hiển thị**.
5. Hai threads chạy đồng thời có events trùng nhau; thứ tự đọc file không luôn tương ứng quan hệ nhân quả thực tế.
6. **Không suy latency client→server** bằng cách trừ `Instant` trên hai host khi chưa kiểm tra clock sync và bối cảnh đo.

Để đo thời lượng một thao tác **trong cùng tiến trình**, dùng event bắt đầu/kết thúc đúng scope, hoặc `System.nanoTime()` để đo elapsed trong ứng dụng. `System.currentTimeMillis()` dùng cho timestamp tương đối với epoch, không phải công cụ chuẩn cho các phép đo latency ngắn cần ổn định trước điều chỉnh wall-clock.

**Không so sánh trực tiếp ticks JFR giữa hai JVM.** Những trường `@Timestamp(TICKS)` cần được giải thích theo recording/runtime; không mang raw tick count sang máy khác rồi coi là Unix epoch.

## 15. Phân tích file lớn và xử lý dữ liệu không tin cậy

Một parser hiệu năng tốt không nhất thiết cần database hay giữ toàn bộ events:

```text
RecordingFile
     |
     v
hasMoreEvents + readEvent
     |
     v
Filter event type
     |
     +--> Count
     +--> Min/max Duration
     +--> Earliest/Latest Instant
     +--> Aggregate summaries
     |
     v
Discard event object
```

Gợi ý vận hành:

- Dùng `RecordingFile` trong `try-with-resources` để đóng file.
- Đặt giới hạn kích thước file, thời gian đọc và số events nếu file do bên ngoài cung cấp.
- Tránh in **toàn bộ** event payload với `toString()` trong production logs: có thể bao gồm đường dẫn, tên thread, class/method, socket endpoints hoặc custom data nhạy cảm.
- Không dùng `readAllEvents` với file lớn chỉ để tìm một event type.
- Nếu cần tính percentiles p95/p99, cân nhắc cấu trúc histogram/streaming quantile có giới hạn bộ nhớ thay vì lưu millions durations.
- Cần phân tích nhiều phiên bản JDK, kiểm tra metadata trường thay vì tin tất cả events đều có một field name/type cố định.
- File JFR từ nguồn không tin cậy có thể bị hỏng hoặc nhằm khai thác parser; Javadoc Oracle khuyến nghị chỉ đọc recording files từ nguồn đáng tin.

## 16. Những lỗi phổ biến khi đọc RecordedEvent

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Dùng `System.currentTimeMillis()` khi parse thay cho `getStartTime()` | Đó là thời điểm đang đọc, không phải khi event xảy ra | Lấy `event.getStartTime()` |
| Coi `getDuration()` trả `long` milliseconds | API trả `Duration` | So sánh/đổi đơn vị có chủ đích |
| In `Duration.toMillis()` rồi nghĩ chính xác mọi nano | Phần lẻ milli bị bỏ | Giữ `Duration` hoặc đổi sang `double` khi hiển thị |
| Xem instant event duration=0 là “không hề xảy ra” | Event điểm thời gian có duration 0 | Dựa vào event type/semantics |
| Gọi `end()` trên `RecordedEvent` | Lẫn API phát và đọc sự kiện | `Event.end()` khi tạo; RecordedEvent chỉ đọc |
| Trộn `getDuration()` với `getDuration("budget")` | Một bên là event timing, một bên là field @Timespan | Phân biệt metadata và payload |
| Đọc raw ticks như epoch milliseconds | Hai đơn vị khác | Dùng `getInstant(field)` nếu @Timestamp hợp lệ |
| Dùng `LocalDateTime` không timezone để so host | Mất offset và có thể lệch nhiều giờ | Giữ `Instant`; chỉ format bằng ZoneId khi hiển thị |
| Cộng toàn bộ durations để đo wall-clock elapsed | Events có thể overlap | Dùng start/end và mô hình đồng thời thích hợp |
| Coi danh sách events có thứ tự hoàn hảo theo startTime | Không có bảo đảm tuyệt đối cho mọi cách đọc/thiết lập | Sort rõ ràng nếu cần |
| File không có `jdk.ThreadPark` nghĩa không có park | Event có thể chưa bật hoặc bị threshold lọc | Kiểm tra settings + event types |
| Dùng `readAllEvents` cho file rất lớn | Có thể chiếm nhiều heap | Dùng `RecordingFile` streaming |
| Giả định `getThread()` luôn khác null | Thread có thể không được thu | Null-check |
| Giả định `getStackTrace()` luôn khác null | Stack trace có thể không được thu | Null-check |
| Log toàn event payload | Có thể lộ thông tin nhạy cảm | Chỉ in dữ liệu cần thiết, có kiểm soát |

## 17. Bài kiểm tra nhỏ về Java time (độc lập với JFR)

Để chắc chắn hiểu các kiểu thời gian trước khi xử lý file thật, chạy chương trình sau. Nó dùng các mốc giả định **cố định**, không đo JVM clock.

### Tệp `InstantDurationRegression.java`

```java
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;

public class InstantDurationRegression {
    static int checks;

    static void check(String name, boolean condition) {
        checks++;
        if (!condition) {
            throw new AssertionError(name);
        }
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-11-07T08:30:00Z");
        Instant end = start.plusMillis(125);
        Duration elapsed = Duration.between(start, end);

        check("positive duration", !elapsed.isNegative());
        check("duration millis", elapsed.toMillis() == 125);
        check("duration nanos", elapsed.toNanos() == 125_000_000L);
        check("ordered instants", end.isAfter(start));
        check("zero difference",
                Duration.between(start, start).isZero());
        check("timezone display", start.atZone(
                ZoneId.of("Asia/Ho_Chi_Minh"))
                .getHour() == 15);
        check("milli truncation",
                Duration.ofNanos(1_900_000L).toMillis() == 1);

        System.out.println("PASS: " + checks + " checks");
    }
}
```

```bash
javac --release 11 -encoding UTF-8 InstantDurationRegression.java
java InstantDurationRegression
```

```text
PASS: 7 checks
```

**Giải thích:** 7 kiểm tra về dấu, đơn vị, thứ tự, thời lượng bằng 0, timezone và tính mất phần lẻ khi chuyển nano → milli. Đây là **test toán học của `java.time`**, không phải bằng chứng bản ghi JFR có duration chính xác tới từng nano. Để kiểm tra dữ liệu JFR thật, dùng hai ví dụ tích hợp ở mục 5 và 9.

## 18. Checklist review một công cụ phân tích JFR

- **Đúng event type:** so sánh `getEventType().getName()` với loại cần phân tích.
- **Thời điểm:** giữ `getStartTime()/getEndTime()` dưới dạng `Instant` cho đến lúc hiển thị.
- **Thời lượng:** dùng `getDuration()` như `Duration`; so threshold trước khi làm tròn.
- **Phân biệt instant vs duration:** không coi duration=0 là lỗi hoặc loại bỏ không có lý do.
- **Schema:** đọc đúng các business timestamp/timespan fields, dùng `hasField` và annotation metadata thích hợp.
- **Timezone:** hiển thị bằng `ZoneId` được chọn rõ ràng, không trộn giờ server và client.
- **Thống kê:** không suy đoán “mọi giao dịch” từ một event type bị sampling/threshold.
- **Timeline:** earliest/latest chỉ trên events đã lọc; không giả định các sự kiện không overlap.
- **Dữ liệu lớn:** streaming reader, limits, retention và không log dữ liệu nhạy cảm.
- **Cross-host:** kiểm tra đồng bộ đồng hồ và scope của event trước khi so thời điểm.
- **Kiểm thử:** có các ca instant event, duration event, payload @Timestamp/@Timespan, event bị thiếu và file không hợp lệ.

## 19. Câu hỏi tự luyện

**1.** `getStartTime()` và `getEndTime()` trả về `long` milliseconds hay `Instant`?

**2.** `getDuration()` trả về `Duration` hay `long`? Có mặc định là milliseconds không?

**3.** Nếu event là instant event, `getStartTime()` và `getEndTime()` khác nhau không?

**4.** Nếu `getDuration().toMillis() == 0`, có chắc chắn là event chưa xảy ra không?

**5.** Một field `@Timespan(MILLISECONDS) long budgetMillis = 750` là duration của event hay ngân sách do ứng dụng lưu?

**6.** Có thể trừ `getStartTime()` từ timestamp lúc parser đang chạy để đo độ trễ của thao tác được ghi không?

**7.** Một `RecordedEvent` có event duration 25 ms, nhưng một field tên `budgetMillis` là 500 ms. Có mâu thuẫn không?

**8.** Nếu file không có `jdk.JavaMonitorEnter`, có thể chắc chắn không hề có contention không?

**9.** Muốn đổi UTC sang giờ Việt Nam, có nên cộng cứng 7 giờ vào dữ liệu lưu không?

**10.** Khi xử lý file nhiều triệu events, nên bắt đầu với `readAllEvents` hay `hasMoreEvents/readEvent`?

**Đáp án:**

1. **`Instant`** cho cả hai phương thức.
2. **`Duration`**, không phải số nguyên milliseconds; Javadoc nói độ phân giải theo nanosecond.
3. **Không**; với instant event hai mốc giống nhau.
4. **Không**; có thể là event tức thời hoặc một khoảng quá nhỏ khi làm tròn milliseconds.
5. **Ngân sách riêng** của application, không mặc định là event duration.
6. **Không**; đó là tuổi của event tới lúc phân tích. Dùng `getDuration()` để đo thời lượng event.
7. **Không**; 25 ms là elapsed thực của event, 500 ms là giới hạn do business field ghi.
8. **Không**; có thể event type chưa bật/threshold lọc.
9. **Không**; giữ `Instant` và định dạng bằng `ZoneId.of("Asia/Ho_Chi_Minh")`.
10. **Đọc tuần tự**, giới hạn tài nguyên và thống kê theo luồng.

## 20. Tổng kết

- **`RecordedEvent.getStartTime()` và `getEndTime()` → `Instant`**: hai mốc trên timeline; với instant event chúng bằng nhau.
- **`RecordedEvent.getDuration()` → `Duration`**: thời lượng event, không phải một số `long` millisecond.
- **`RecordedObject.getInstant(field)` và `getDuration(field)`** đọc **các field riêng** có annotation @Timestamp/@Timespan; không trộn với metadata của event.
- Với file JFR thật, dùng `RecordingFile` + `hasMoreEvents()` + `readEvent()`; lọc đúng event type.
- Với dữ liệu hiệu năng, **semantics của loại event, threshold, sampling, recording window và clock accuracy** quyết định cách diễn giải.
- Không lấy sum durations làm thời gian đồng hồ nếu events chồng lắp; không so timestamps giữa host thiếu clock sync; không coi kết quả dưới 1 ms là zero tuyệt đối.
- Các cơ chế này **còn phù hợp với Java 11 trở lên**, không cần API cũ hay công cụ thương mại legacy.

## Tài liệu chính thức

- [Java SE 11 — RecordedEvent: getStartTime, getEndTime, getDuration](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html).
- [Java SE 11 — RecordedObject: getInstant, getDuration(String), hasField](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html).
- [Java SE 11 — RecordingFile: hasMoreEvents, readEvent, readAllEvents](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
- [Java SE 11 — Event: begin, end, commit, shouldCommit](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html).
- [Java SE 11 — Recording và EventSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html).
- [Java SE 11 — @Timestamp và @Timespan](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Timestamp.html).
- [Java SE 11 — @Timespan](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Timespan.html).
- [Java SE 11 — jfr command](https://docs.oracle.com/en/java/javase/11/tools/jfr.html).
