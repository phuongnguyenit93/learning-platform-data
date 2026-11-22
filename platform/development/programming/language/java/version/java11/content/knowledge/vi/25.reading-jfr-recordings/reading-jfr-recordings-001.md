# Java 11+ — Đọc bản ghi JFR: `RecordingFile` và duyệt theo từng sự kiện

## 1. Mục tiêu: đọc dữ liệu JFR một cách có cấu trúc, không chỉ in log

**Java Flight Recorder (JFR)** lưu các sự kiện từ JVM và ứng dụng vào tệp nhị phân **`.jfr`**. Trong Java 11, module **`jdk.jfr`** cung cấp public API ở package **`jdk.jfr.consumer`** để đọc bản ghi đã lưu. Đối tượng trung tâm của bài này là **`RecordingFile`**; nó cho phép lần lượt đọc từng **`RecordedEvent`** mà không phải tự giải mã cấu trúc nhị phân JFR.

Một bài toán điển hình: ứng dụng vừa kết thúc một phiên ghi JFR. Bạn cần biết trong khoảng thời gian đó có bao nhiêu sự kiện loại `lesson.StageStep`, sự kiện nào có trường `stage`, tổng `units` theo từng stage, duration của sự kiện, và những loại khác có xuất hiện hay không. Thay vì đọc toàn bộ file thành một chuỗi text, hãy:

1. Mở đúng file `.jfr` từ nguồn tin cậy.
2. Dùng `RecordingFile.readEventTypes()` để khám phá **schema các loại sự kiện** khi cần.
3. Lặp `while (file.hasMoreEvents()) { RecordedEvent e = file.readEvent(); ... }`.
4. Xác định **tên event type** qua `e.getEventType().getName()`.
5. Chỉ lấy các fields mình cần với `hasField` và typed getters.
6. Lọc và tổng hợp dữ liệu theo type, thời gian, phase, thread hay nhu cầu nghiệp vụ.
7. Đóng file bằng **try-with-resources**; báo cáo kết quả kèm ngữ cảnh recording và giới hạn của dữ liệu.

**Điểm cốt lõi:** `RecordingFile` là API để đọc **các event đã được ghi**, không phải API thay đổi dữ liệu đang chạy của JVM. Nó khác `jdk.jfr.Recording` (dùng để **tạo/điều khiển phiên ghi**) và không phải một giao diện trực tiếp để subscribe mọi event trong một tiến trình đang sống.

Những API `RecordingFile`, `RecordedEvent` và `RecordedObject` được nêu dưới đây có trong **Java 11** và vẫn là nền tảng phù hợp trên các JDK hiện đại. Bài không sử dụng API cũ đã lỗi thời hoặc các method chỉ được bổ sung sau Java 11 rồi tuyên bố chúng có sẵn từ Java 11.

## 2. Các đối tượng liên quan và vòng đời một lần duyệt

| Đối tượng | Vai trò | Ví dụ sử dụng |
| --- | --- | --- |
| `Path` | Đường dẫn tệp nhị phân `.jfr` trên filesystem. | `Path.of("sample.jfr")` |
| `RecordingFile` | Consumer đọc lần lượt các event và metadata từ tệp. | `new RecordingFile(path)` |
| `EventType` | Mô tả tên, category, fields và metadata của **loại** event. | `event.getEventType()` |
| `RecordedEvent` | Một **bản ghi sự kiện**: type, thời gian và giá trị field. | `file.readEvent()` |
| `RecordedObject` | Lớp cha hỗ trợ lấy fields (kể cả đường dẫn nested trong một số trường hợp). | `event.hasField("units")` |
| `ValueDescriptor` | Mô tả một field: tên, kiểu dữ liệu, annotations. | `event.getEventType().getFields()` |
| `Instant` | Thời điểm bắt đầu/kết thúc event trên trục thời gian. | `event.getStartTime()` |
| `Duration` | Thời lượng của **một event**. | `event.getDuration()` |

Luồng xử lý:

```text
                 sample.jfr
                     |
                     v
           RecordingFile(Path)
                     |
           +---------+----------+
           |                    |
           v                    v
    readEventTypes()       hasMoreEvents()
      (schema)                  |
                                v
                             readEvent()
                                |
                                v
                     RecordedEvent.getEventType()
                                |
                                v
                       Lọc tên event type
                                |
                          +-----+------+
                          |            |
                     đúng loại      khác loại
                          |            |
                          v            v
                   hasField/getX    bỏ qua / đếm
                          |
                          v
                Tính toán, group, thống kê
                          |
                   Lặp event kế tiếp
                          |
                          v
                       close()
```

**Một loại sự kiện có thể xuất hiện nhiều lần.** `EventType` là mô tả schema; `RecordedEvent` là một occurrence có timestamp/payload. Nếu `readEventTypes()` có tên `lesson.StageStep`, điều đó **không** nói loại đó đã có bao nhiêu occurrence: muốn đếm hãy duyệt events hoặc dùng công cụ thống kê phù hợp.

## 3. API `RecordingFile` của Java 11 — hợp đồng chính xác

Đoạn tối giản sau là mẫu chuẩn của Java 11:

```java
Path path = Path.of("sample.jfr");
try (RecordingFile file = new RecordingFile(path)) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        System.out.println(event.getEventType().getName());
    }
}
```

Đây là **snippet**, cần import `java.nio.file.Path`, `jdk.jfr.consumer.RecordingFile` và `RecordedEvent`, đồng thời xử lý `IOException`. Chương trình tự tạo file mẫu và đọc lại ở mục 8.

| Method | Tác dụng | Điều phải nhớ |
| --- | --- | --- |
| `new RecordingFile(Path file)` | Mở bản ghi từ đường dẫn. | Có thể ném `IOException`, gồm trường hợp tệp sai định dạng/không đọc được. **Chỉ mở recording từ nguồn tin cậy** theo Javadoc Oracle. |
| `hasMoreEvents()` | `true` nếu còn event chưa được đọc. | Kết hợp với `readEvent()`; không tự mang theo event payload. |
| `readEvent()` | Trả về **event tiếp theo** dưới dạng `RecordedEvent`. | Nếu gọi khi đã hết event, có thể ném **`EOFException`**; có thể ném `IOException` do đọc tệp lỗi. |
| `readEventTypes()` | Danh sách `EventType` được định nghĩa trong recording. | Dùng khám phá metadata; **không** phải danh sách các occurrence. |
| `close()` | Giải phóng tài nguyên liên quan file. | Dùng try-with-resources thay cho quên đóng ở nhánh lỗi. |
| `RecordingFile.readAllEvents(Path)` | Static helper trả danh sách **tất cả** events. | Javadoc nói dành cho trường hợp đơn giản, **không phù hợp file lớn** vì nạp toàn bộ events vào list. |

Tại sao nên dùng `hasMoreEvents()` trước `readEvent()`? Vì nó biểu diễn đúng vòng đời iteration và tránh dùng **exception như điều kiện kết thúc bình thường**. Nếu code cần đọc đúng một event từ một file có thể rỗng, hãy kiểm tra `hasMoreEvents()` rồi mới gọi `readEvent()`.

### Đọc theo từng event không giống đọc theo từng byte

Không có lý do để sử dụng `InputStream.read(...)` rồi tự đoán ranh giới sự kiện JFR. Một event có thể chứa field lồng nhau, metadata được tham chiếu, timestamp, stack trace và các cấu trúc JFR khác. `RecordingFile` sẽ trả một **`RecordedEvent` có type/fields chuẩn**, không yêu cầu ứng dụng hiểu layout chunk/constant pool nội bộ của JFR.

**Không nên suy luận file chỉ có một event type** chỉ vì ứng dụng chủ động ghi một custom event. Runtime có thể có metadata hoặc các JDK events khác. Phải lọc bằng tên event cụ thể.

### Không đồng nghĩa “stream trực tiếp từ JVM”

`RecordingFile` là **reader của tệp đã tồn tại**. Code có thể duyệt tuần tự từ disk thay vì dựng list toàn bộ file, nhưng nó **không** có nghĩa là stream live events với một giao thức subscribe. Nếu cần tiêu thụ JFR từ một JVM đang hoạt động, cần xem khả năng streaming riêng được hỗ trợ ở JDK mục tiêu và bài toán vận hành. Trọng tâm Java 11 ở đây là **offline file consumption**.

## 4. Khám phá schema trước khi đọc giá trị

Một recording có thể chứa event types do **JDK**, thư viện hoặc chính ứng dụng định nghĩa. Ví dụ:

- `jdk.GarbageCollection`: event GC theo định nghĩa của runtime.
- `jdk.JavaMonitorEnter`: thông tin liên quan vào Java monitor (phụ thuộc cấu hình/threshold).
- `jdk.SocketRead` và `jdk.SocketWrite`: các event I/O theo settings của recording.
- `lesson.StageStep`: custom event của chương trình ví dụ.

Tên, fields và việc xuất hiện của các built-in event có thể thay đổi giữa các bản JDK, settings và workload. **Không tự viết code `event.getInt("bytes")` cho mọi loại event** mà chưa xác minh field có tồn tại, đúng type và đúng đơn vị.

Với Java 11:

```java
try (RecordingFile file = new RecordingFile(Path.of("sample.jfr"))) {
    for (EventType type : file.readEventTypes()) {
        System.out.println(type.getName());
    }
}
```

Snippet trên cần import `jdk.jfr.EventType`, `java.nio.file.Path` và `RecordingFile`, cùng xử lý `IOException`. Nó dùng để thấy **danh sách schema**, không phải print các event occurrences.

Để xem fields của một type:

```java
for (ValueDescriptor field : event.getEventType().getFields()) {
    String name = field.getName();
    String javaType = field.getTypeName();
    // Lưu tên và kiểu để kiểm tra tương thích.
}
```

Đây là đoạn nằm trong nơi đã có `RecordedEvent event`; cần import `jdk.jfr.ValueDescriptor`. Metadata có thể cho biết field kiểu `int`, `long`, `java.lang.String`, timestamp, timespan, thread object hoặc object structure khác.

Một cơ chế đọc ổn định nên áp dụng thứ tự:

1. Xác định `event.getEventType().getName()` đúng loại mình hỗ trợ.
2. Kiểm tra danh sách field names và các type cần thiết.
3. Chỉ sau đó gọi `event.getString("stage")`, `event.getInt("units")` hoặc getter tương ứng.
4. Khi version/schema không như mong đợi, báo lỗi có thể hành động được hoặc xử lý theo adapter tương thích, **không âm thầm coi field thiếu là số 0**.

**`hasField(name)` chỉ xác minh field tồn tại**. Nó không chứng minh field ấy luôn khác `null`, có đúng kiểu bạn kỳ vọng, hoặc giá trị không vi phạm logic nghiệp vụ. `getInt("units")` có thể ném `IllegalArgumentException` nếu field không tồn tại hoặc không thể chuyển hợp lệ sang `int`. Với field object lồng nhau, bất kỳ phần nào `null` đều có thể khiến việc truy cập nested path thất bại; phải kiểm tra.

## 5. Đọc đúng `RecordedEvent`: loại, timestamp, duration, thread và stack

| API của `RecordedEvent` | Trả về | Sử dụng |
| --- | --- | --- |
| `getEventType()` | `EventType` | Phân loại và kiểm tra schema. |
| `getStartTime()` | `Instant` | Đặt event trên timeline. |
| `getEndTime()` | `Instant` | Thời điểm kết thúc; với instant event thường bằng start. |
| `getDuration()` | `Duration` | Độ dài event theo ý nghĩa type. |
| `getThread()` | `RecordedThread` hoặc `null` | Xem thread commit event nếu đã được ghi. |
| `getStackTrace()` | `RecordedStackTrace` hoặc `null` | Phân tích call stack nếu recording bật/ghi stack. |
| `hasField(String)` | `boolean` | Kiểm tra field trước khi đọc. |
| `getInt/getLong/getString/getBoolean` | Giá trị typed | Đọc các fields đúng tên/kiểu. |
| `getValue(String)` | Giá trị tổng quát theo field | Khi cần object/nested field mà schema đã được xác minh. |

Cần hiểu đúng:

- `getStartTime()` và `getEndTime()` là **thời điểm** `Instant`, không phải số mili giây dùng trực tiếp để tính tổng.
- `getDuration()` là **elapsed event duration**, **không tự bằng CPU time**. Một event chờ file/socket/lock có thể có duration dài nhưng thời gian CPU rất nhỏ.
- Instant events có thể có `duration = Duration.ZERO`; điều đó không đồng nghĩa “event lỗi”.
- `getThread() == null` hoặc `getStackTrace() == null` là kết quả hợp lệ nếu recording không lưu thông tin đó. Không lấy null làm bằng chứng không có thread/call stack khi runtime thực thi.
- Events có thể được sampling, lọc threshold, tắt theo recording settings hoặc nằm ngoài cửa sổ chụp. **Count đã ghi ≠ số lần method nghiệp vụ thực sự chạy** trong mọi tình huống.
- Dữ liệu JFR còn có các annotations như `@Timestamp`, `@Timespan` và `@Unsigned`; chọn typed getter đúng, tránh tự cast một `Object` theo giả định không kiểm tra.

### Cẩn thận với đơn vị

`Duration` có thể đổi đơn vị:

```java
long millis = event.getDuration().toMillis();
long nanos = event.getDuration().toNanos();
```

Đây là đoạn minh họa nơi đã có `RecordedEvent event`. `toMillis()` bỏ phần nhỏ hơn một mili giây; nếu đang phân tích sự kiện ngắn, nên giữ đơn vị nanosecond hoặc thống kê độ phân giải phù hợp. Không chuyển mọi duration thành `int` rồi gây tràn.

Khi báo cáo:

- Nói rõ cửa sổ thời gian `Instant` (UTC hoặc timezone trình bày).
- Phân biệt **count**, **tổng duration**, **elapsed wall time của cả phiên**, **CPU samples**, **bytes đọc/ghi**.
- Tránh cộng duration của nhiều thread chạy song song rồi kết luận thành thời gian trôi qua thực tế.
- Nếu cần phân tích critical path, phải có correlation context như request ID/trace ID đã được ghi vào event hoặc được đối chiếu an toàn.

## 6. Lọc theo event type và thời gian

### 6.1. Tên type là khóa lọc đáng tin hơn ID cứng

Trong file nhiều loại sự kiện:

```java
while (file.hasMoreEvents()) {
    RecordedEvent event = file.readEvent();
    if (!"lesson.StageStep".equals(event.getEventType().getName())) {
        continue;
    }

    // Chỉ đến đây mới đọc field riêng của StageStep.
    String stage = event.getString("stage");
    int units = event.getInt("units");
    // Tổng hợp dữ liệu.
}
```

Snippet này nằm trong scope đã có `RecordingFile file`; cần bảo đảm `stage`/`units` tồn tại và có đúng kiểu. Đối tượng `EventType` có thể có numeric ID trong metadata, nhưng **đừng hard-code event ID** từ một recording để parse một recording khác: event type ID và metadata nội bộ có thể khác theo JDK, file hoặc cấu hình. **Tên type** là cơ sở lọc dễ kiểm tra hơn khi giao thức custom event quy định một tên ổn định.

### 6.2. Lọc thời gian bằng `Instant`

Nếu cần phân tích một khoảng thời gian cụ thể:

```java
Instant from = Instant.parse("2026-11-07T10:00:00Z");
Instant until = Instant.parse("2026-11-07T10:05:00Z");

while (file.hasMoreEvents()) {
    RecordedEvent event = file.readEvent();
    Instant start = event.getStartTime();
    if (start.isBefore(from) || !start.isBefore(until)) {
        continue;
    }
    // Event có start trong [from, until).
}
```

Đoạn này **chỉ minh họa filtering**, không chạy độc lập; cần import `Instant`, có `RecordingFile file` đã mở, và cửa sổ thời gian thay bằng thời điểm thực của recording. Ví dụ lọc **theo start time**; với event kéo dài vượt qua ranh giới, nếu mục tiêu là phát hiện **overlap**, hãy dùng điều kiện dựa trên cả start/end: `event.getEndTime().isAfter(from) && event.getStartTime().isBefore(until)`, và quyết định rõ trường hợp sự kiện instant nằm đúng biên.

**Đừng đoán thứ tự file luôn toàn cục tăng dần theo start time** rồi `break` khi gặp một event ngoài cửa sổ, trừ khi API/format/công cụ bảo đảm thứ tự đó trong tình huống của bạn. Duyệt đủ events trong file và lọc từng cái là lựa chọn an toàn, nhất là khi cần so sánh nhiều thread/chunks.

## 7. Tổng hợp trong lúc duyệt, tránh giữ toàn bộ events

Với file lớn, cách tiếp cận tốt là duy trì **thống kê tích lũy**:

```java
Map<String, Long> countByType = new TreeMap<>();

try (RecordingFile file = new RecordingFile(path)) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        String type = event.getEventType().getName();
        countByType.merge(type, 1L, Long::sum);
    }
}
```

Đây là snippet nằm trong method có `Path path` và import `Map`/`TreeMap`/`RecordingFile`/`RecordedEvent`; cần xử lý `IOException`. Bộ nhớ chỉ tăng theo **số lượng nhóm** (event types), không theo **tổng số occurrences**. Với nhóm động theo trường có cardinality cao (thread ID/request ID/URL), vẫn cần giới hạn key, quota và chính sách aggregate để tránh hàng triệu entries.

Khác với:

```java
List<RecordedEvent> all = RecordingFile.readAllEvents(path);
```

`readAllEvents` là API có thật trong Java 11, hữu ích với các file nhỏ và test ngắn, nhưng **Javadoc nói rõ không dành cho large files**. Khi đưa JFR vào pipeline phân tích có dữ liệu dài hoặc nhiều events, ưu tiên `RecordingFile` và `hasMoreEvents/readEvent` để tránh bắt buộc giữ tất cả trong RAM.

### Đếm occurrence khác với tính thời lượng và thống kê mẫu

Tổng số `RecordedEvent` được đọc chỉ là số **events thực sự được recording lưu**. Các built-in events như method sampling, allocation, periodic CPU samples có cơ chế thu thập khác custom events ghi mỗi lần. Khi hiển thị dashboard:

- Ghi **count of recorded events** thay vì “total method calls” nếu đang dùng samples.
- Với duration, công bố đơn vị và cách xử lý overlap.
- Với percentages, ghi rõ mẫu số, cửa sổ và event settings.
- Với custom event, ghi rõ `@Threshold`, `@Period`, việc `commit()` và có bật type trong `Recording` không.
- Nếu không có dữ liệu, nói “không có event được ghi trong cửa sổ này theo settings đã dùng”, **không** suy ra hoạt động đó chắc chắn không xảy ra.

## 8. Chương trình Java 11 hoàn chỉnh: sinh bản ghi thật rồi duyệt từng event

Để bài học có **đầu vào thật**, ví dụ viết một chương trình Java source duy nhất **`RecordingFileWalkDemo.java`** có hai chế độ:

- **`capture`:** tạo bản ghi JFR `sample.jfr` với ba event `lesson.StageStep` (load 5, transform 7, save 11) và một event `lesson.Marker` (done).
- **`inspect`:** mở đúng file đó bằng `RecordingFile`, đọc `readEventTypes()` để xác nhận schema, duyệt **từng event** qua `hasMoreEvents/readEvent`, lọc type, dùng `hasField`/typed getters, tổng hợp `units` theo stage và kiểm tra duration không âm.

Chương trình được thiết kế để **stdout xác định**, không phụ thuộc timestamps, kích thước file, ID nội bộ, thread ID hay các JDK events khác. `TreeMap` sắp xếp tên stage theo alphabet khi in; không suy luận đó là thứ tự phát sinh sự kiện.

**Bản ghi được tạo bằng API JFR chính thức trong chính JVM** — không phải list object giả rồi tuyên bố đã parse file JFR. Code không truy cập mạng, không ghi dữ liệu nhạy cảm, và chỉ ghi tệp mà người học chỉ định trong thư mục thử nghiệm.

### 8.1. Mã nguồn `RecordingFileWalkDemo.java`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import java.util.StringJoiner;
import java.util.TreeMap;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.EventType;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class RecordingFileWalkDemo {
    @Name("lesson.StageStep")
    @Label("Stage step")
    @Category({"Lesson", "Workflow"})
    public static class StageStep extends Event {
        @Label("Stage")
        public String stage;
        @Label("Units")
        public int units;
    }

    @Name("lesson.Marker")
    @Label("Marker")
    public static class Marker extends Event {
        @Label("Message")
        public String message;
    }

    private static void capture(Path output) throws IOException {
        try (Recording recording = new Recording()) {
            recording.enable(StageStep.class).withThreshold(Duration.ZERO)
                    .withoutStackTrace();
            recording.enable(Marker.class).withThreshold(Duration.ZERO)
                    .withoutStackTrace();
            recording.start();

            String[] stages = {"load", "transform", "save"};
            int[] amounts = {5, 7, 11};
            for (int i = 0; i < stages.length; i++) {
                StageStep e = new StageStep();
                e.stage = stages[i];
                e.units = amounts[i];
                e.begin();
                e.end();
                e.commit();
            }
            Marker m = new Marker();
            m.message = "done";
            m.commit();

            recording.stop();
            recording.dump(output);
        }
        System.out.println("recording-created=" + Files.isRegularFile(output));
    }

    private static void inspect(Path input) throws IOException {
        long stages = 0;
        long markers = 0;
        long totalUnits = 0;
        boolean fieldsOk = true;
        boolean durationOk = true;
        Map<String, Integer> totalsByStage = new TreeMap<>();

        try (RecordingFile file = new RecordingFile(input)) {
            boolean stageTypeFound = false;
            for (EventType type : file.readEventTypes()) {
                if ("lesson.StageStep".equals(type.getName())) {
                    stageTypeFound = type.getFields().stream()
                            .anyMatch(field -> "stage".equals(field.getName()))
                            && type.getFields().stream()
                            .anyMatch(field -> "units".equals(field.getName()));
                }
            }

            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                String name = event.getEventType().getName();
                if ("lesson.StageStep".equals(name)) {
                    fieldsOk &= event.hasField("stage")
                            && event.hasField("units");
                    String stage = event.getString("stage");
                    int units = event.getInt("units");
                    stages++;
                    totalUnits += units;
                    totalsByStage.merge(stage, units, Integer::sum);
                    durationOk &= !event.getDuration().isNegative();
                } else if ("lesson.Marker".equals(name)) {
                    markers++;
                }
            }

            StringJoiner joined = new StringJoiner(",");
            totalsByStage.forEach((name, units) ->
                    joined.add(name + ":" + units));
            System.out.println("stage-type-found=" + stageTypeFound);
            System.out.println("stage-events=" + stages);
            System.out.println("marker-events=" + markers);
            System.out.println("units-total=" + totalUnits);
            System.out.println("by-stage=" + joined);
            System.out.println("fields-present=" + fieldsOk);
            System.out.println("durations-nonnegative=" + durationOk);
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: capture|inspect <file.jfr>");
        }
        Path file = Path.of(args[1]);
        switch (args[0]) {
            case "capture":
                capture(file);
                break;
            case "inspect":
                inspect(file);
                break;
            default:
                throw new IllegalArgumentException("Unknown command");
        }
    }
}
```

### 8.2. Biên dịch và chạy

Dùng **JDK 11 trở lên**, có module `jdk.jfr` (cài đặt JDK hỗ trợ Flight Recorder). Cờ `--release 11` buộc compiler chỉ dùng cú pháp và public API tương thích Java 11.

```bash
javac -encoding UTF-8 --release 11 RecordingFileWalkDemo.java
java RecordingFileWalkDemo capture sample.jfr
java RecordingFileWalkDemo inspect sample.jfr
```

**Stdout đúng tám dòng đã được kiểm chứng:**

```text
recording-created=true
stage-type-found=true
stage-events=3
marker-events=1
units-total=23
by-stage=load:5,save:11,transform:7
fields-present=true
durations-nonnegative=true
```

Các dòng trong khối trên là output liên tiếp từ hai lần chạy: `capture` in dòng thứ nhất, `inspect` in bảy dòng tiếp theo.

### 8.3. Giải thích kết quả chính xác

1. **`recording-created=true`:** đường dẫn `sample.jfr` tồn tại dưới dạng regular file sau khi `Recording.stop()` và `dump(...)`. Đây là một **tệp JFR thật**, không phải file text.
2. **`stage-type-found=true`:** `readEventTypes()` tìm được `EventType` tên `lesson.StageStep`, có các fields `stage` và `units`. Điều đó kiểm chứng metadata được parser hiểu; nó chưa phải bộ đếm occurrences.
3. **`stage-events=3`:** vòng lặp đọc ba `RecordedEvent` đúng tên type `lesson.StageStep`; chỉ đếm loại đã lọc.
4. **`marker-events=1`:** event thứ hai, `lesson.Marker`, cũng có trong cùng recording; code lọc rõ ràng để không cộng field `units` không có ở Marker.
5. **`units-total=23`:** ba giá trị `5 + 7 + 11`, là dữ liệu ứng dụng do fixture tạo; không phải số byte JFR hoặc CPU utilization.
6. **`by-stage=load:5,save:11,transform:7`:** `TreeMap` sắp xếp theo **tên**, không phải timestamp. Thứ tự capture của fixture là load, transform, save.
7. **`fields-present=true`:** mỗi StageStep được đọc có hai field cần thiết. Code vẫn dùng typed getters dựa trên schema do fixture kiểm soát; khi đọc file bên ngoài cần kiểm tra **cả type** nếu schema có thể thay đổi.
8. **`durations-nonnegative=true`:** các StageStep không có duration âm. Bài test không khẳng định các công đoạn đã tiêu tốn một số milliseconds cố định; thời lượng có thể rất nhỏ hoặc bằng không.

Chương trình còn tạo `Marker.message="done"`, nhưng không in chuỗi này trong stdout vì ví dụ tập trung vào **tách và xử lý các loại event**. Người đọc có thể dùng công cụ `jfr print` để kiểm tra dữ liệu Marker.

### 8.4. Đối chiếu độc lập bằng CLI của JDK

Trong cùng thư mục có `sample.jfr`:

```bash
jfr summary sample.jfr
jfr print --events lesson.StageStep,lesson.Marker sample.jfr
```

Trong môi trường kiểm thử đã chạy:

- `jfr summary` cho **`lesson.StageStep`: 3** và **`lesson.Marker`: 1**.
- `jfr print` xuất ba `lesson.StageStep` với `stage=load/transform/save`, `units=5/7/11`, cùng một `lesson.Marker` với `message="done"`.

`jfr` có thể in thêm timestamp, duration, thread ID, stack metadata và fields hệ thống khác; đây là dữ liệu do runtime quyết định. File size và các event types nội bộ cũng thay đổi tùy JDK/OS/cấu hình, vì thế **không khóa cứng số byte file** làm assertion.

Để xem type layout và định dạng máy đọc được khi công cụ hỗ trợ, có thể dùng:

```bash
jfr metadata sample.jfr
jfr print --json --events lesson.StageStep sample.jfr
```

Lệnh `jfr print --json` là **bước xuất dữ liệu từ file JFR**, không chứng minh file gốc vốn là JSON.

## 9. Xây hàm phân tích có khả năng tái sử dụng

Sau khi hiểu demo, một pipeline thực tế có thể phân tách thành:

- **File validation:** kiểm tra đường dẫn nằm trong thư mục được phép, quyền truy cập, kích thước, nguồn gốc và định dạng có thể mở.
- **Reader:** tạo `RecordingFile` trong scope try-with-resources, không giữ reader sống lâu tùy tiện.
- **Schema adapter:** biết những event type names/field names mà phiên bản parser hỗ trợ, phát hiện field thiếu hoặc sai kiểu.
- **Filter:** xác định event type, time window, thread, duration/threshold và điều kiện nghiệp vụ.
- **Aggregator:** giữ state thống kê đủ nhỏ (count, sum, min/max, histogram hạn chế cardinality).
- **Reporter:** công bố kết quả, đơn vị, thời gian, recording settings và giới hạn dữ liệu.

Một API xử lý sự kiện do ứng dụng định nghĩa có thể lấy callback kiểu:

```java
interface EventVisitor {
    void accept(RecordedEvent event);
}
```

Đây là **định nghĩa minh họa**, không phải interface public của `jdk.jfr`; muốn dùng cần một lớp bao quản lý nguồn file và xử lý `IOException`. Ví dụ adapter:

```java
static void walk(Path path, EventVisitor visitor) throws IOException {
    try (RecordingFile f = new RecordingFile(path)) {
        while (f.hasMoreEvents()) {
            visitor.accept(f.readEvent());
        }
    }
}
```

Mã trên chỉ là snippet trong cùng class đã khai báo `EventVisitor` và import; `RecordingFile` vẫn được đóng dù callback ném runtime exception.

**Cẩn trọng với object lifetime:** không nên mặc định một `RecordedEvent` do bạn giữ trong list là snapshot tối ưu cho file vài gigabyte, dù nó là object Java đọc từ disk. Nếu cần giữ fields sau vòng lặp, ưu tiên tạo DTO nhỏ chứa đúng những trường cần thiết; bỏ các object graph/stack trace có cardinality cao để bảo vệ RAM.

## 10. Tương thích với recordings từ nhiều JDK và event schema khác nhau

Các bản ghi từ JDK khác nhau có thể khác:

- **Định dạng binary/version:** một reader quá cũ có thể không parse được file do JDK mới tạo.
- **Danh sách event types:** sự kiện JDK có thể được bổ sung, thay đổi hoặc không xuất hiện tùy cấu hình.
- **Tên/kiểu field:** một sự kiện có thể có thêm fields, một type thay đổi field/annotation hoặc có nested values khác.
- **Annotation timespan/timestamp:** dữ liệu raw có thể có unit/encoding khác; typed getters giúp diễn giải chính xác.
- **Stack/thread metadata:** có thể không được bật/ghi, kết quả `null` là bình thường.
- **Sampling/threshold:** cùng tên event nhưng số occurrence được ghi khác vì cấu hình recorder không giống nhau.

Nguyên tắc tương thích:

1. Xem version **JDK ghi file** và **JDK chạy reader**.
2. Xem `readEventTypes()` trước hoặc kiểm tra type cụ thể ngay trong vòng lặp.
3. Dựa vào **type name + field metadata**, không dùng số ID cố định.
4. Ưu tiên parse những fields cần và **bỏ qua field không biết** nếu protocol cho phép.
5. Với field bắt buộc bị thiếu/sai type, báo **unsupported schema** thay vì ngầm suy ra 0/null.
6. Viết integration tests với một bộ file từ những JDK versions được support trong sản phẩm.
7. Nếu công cụ cũ không đọc được file mới, thử **reader được cập nhật trong môi trường phân tích riêng**; không cần chỉnh JVM production chỉ để đọc.
8. Với `--release 11`, chỉ dùng API **có trong Java 11**, không copy các helper mới từ Javadoc JDK 21/25 mà không kiểm tra `@since`.

### Một kiểu validation field an toàn hơn

```java
EventType type = event.getEventType();
boolean unitsAsInt = type.getFields().stream()
        .anyMatch(f -> "units".equals(f.getName())
                   && "int".equals(f.getTypeName()));
if (!unitsAsInt) {
    throw new IllegalArgumentException(
            "Unsupported event schema: " + type.getName());
}
int units = event.getInt("units");
```

Đây là snippet dựa trên `RecordedEvent event`, cần import `EventType`. So với chỉ `hasField("units")`, nó kiểm tra **tên và type** ở schema trước khi đọc. Nếu data source dùng unsigned annotation, numeric widening hoặc field type khác, logic cần được thiết kế theo đặc tả sự kiện thay vì ép cast không kiểm chứng.

**Không coi một `EventType` có label “Units” giống field tên `units`.** GUI có thể hiển thị label thân thiện, nhưng API typed getters sử dụng **field name** chính xác.

## 11. Độ bền và hiệu năng khi duyệt file lớn

Một file `.jfr` có thể được ghi trong nhiều phút hoặc nhiều giờ, chứa nhiều chunks/events. Dù consumer loop không nạp toàn bộ events vào một `List`, ứng dụng vẫn có thể tốn CPU/RAM/disk I/O để giải mã metadata và đọc event payload.

Các điểm cần kiểm soát:

| Rủi ro | Cách thiết kế |
| --- | --- |
| `readAllEvents` trên file lớn | Dùng `RecordingFile` lặp từng event. |
| Lưu cả `RecordedEvent` vào list lớn | Tổng hợp ngay; chỉ giữ DTO nhỏ hoặc Top-N có giới hạn. |
| Cardinality cực cao của `Map<key,count>` | Chọn key phù hợp, giới hạn nhóm, làm windowing hoặc spill sang storage có quota. |
| Parse tệp không đáng tin | Không cho parser xử lý file từ nguồn không kiểm soát trong process có đặc quyền; cô lập/giới hạn tài nguyên. |
| File hỏng/cắt giữa chừng | Bắt lỗi I/O, không xuất báo cáo hoàn chỉnh từ dữ liệu nửa chừng mà không đánh dấu partial. |
| Event type/schema lạ | Bỏ qua an toàn nếu không liên quan hoặc báo schema không tương thích khi field bắt buộc thiếu. |
| Tính duration bị tràn khi cộng | Dùng `long` hoặc `Duration` có kiểm soát, nêu rõ đơn vị/giới hạn. |
| Logging mọi event | Chỉ log sample/anonymized summary, không vô tình in secret, đường dẫn, stack trace nhạy cảm. |
| So sánh recordings không tương đương | Ghi lại duration cửa sổ, workload, event settings, JDK/runtime, sampling rate. |
| Đọc tệp vẫn đang được ghi | Ưu tiên dump/snapshot hoàn chỉnh trước khi phân tích; kiểm chứng tệp/permissions. |

Dữ liệu JFR có thể chứa những thông tin như command-line args, tên máy/đường dẫn, stack frames, thread names, class names và **custom event fields**. Đừng tự động gửi nguyên file hoặc JSON event ra chat công khai, public issue tracker hoặc dịch vụ bên thứ ba không được phê duyệt.

### Một nguyên tắc “fail visibly”

Nếu lỗi đọc xảy ra **sau khi đã duyệt 50.000 events**, ứng dụng không nên âm thầm xuất `success=true` với thống kê từ 50.000 events đó và khiến người dùng tưởng đây là toàn bộ recording. Hãy:

- Báo file/source và loại lỗi đã làm sạch.
- Đánh dấu **partial/incomplete**, hoặc fail transaction báo cáo nếu yêu cầu thống kê đầy đủ.
- Không sửa/tái tạo file nhị phân gốc bằng cách đoán dữ liệu hỏng.
- Có thể retry bằng **bản ghi đã dump hoàn chỉnh** hoặc một reader phù hợp, nhưng không mặc định cùng thao tác sẽ thành công khi dữ liệu vốn hỏng.

## 12. Những tình huống lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân có thể | Hành động hợp lý |
| --- | --- | --- |
| `NoSuchFileException` khi mở | Sai đường dẫn, file chưa dump hoặc bị di chuyển. | Kiểm tra path và quyền truy cập, không đọc file khác theo suy đoán. |
| `IOException` khi tạo `RecordingFile` | Không phải JFR, file hỏng, reader không hiểu định dạng hoặc lỗi I/O. | Xác minh file từ nguồn tin cậy; thử `jfr summary` bằng reader tương thích. |
| `EOFException` từ `readEvent()` | Gọi khi không còn event. | Duyệt bằng `hasMoreEvents()` trước, không coi EOF là occurrence hợp lệ. |
| Không thấy custom event | Event không bật, không `commit`, threshold/sampling/recording window khác hoặc lọc sai tên. | Kiểm tra config ghi, `readEventTypes()` và `jfr summary`. |
| `hasField` báo false | Schema khác hoặc tên field không khớp. | Xem `EventType.getFields()`, không bịa giá trị mặc định. |
| `getInt/getString` ném exception | Getter không phù hợp field type hoặc name. | Kiểm tra `ValueDescriptor.getTypeName()` trước. |
| `getStackTrace() == null` | Stack trace bị tắt hoặc không được ghi cho event. | Kiểm tra recording setting, không suy luận “không có stack”. |
| Duration bằng 0 | Instant event hoặc độ dài quá ngắn/độ phân giải. | Xem semantics của event; không tự đánh dấu lỗi. |
| File rất lớn, chương trình hết RAM | Dùng `readAllEvents` hoặc giữ quá nhiều DTO/nhóm. | Dùng streaming iteration, giới hạn cardinality/bộ nhớ. |
| Báo `event count = 0` dù ứng dụng đã chạy | Recording không bật type, threshold, sampling hoặc time window. | Đối chiếu config và sự kiện cần chụp, không suy ra hoạt động không có. |
| Reader mới/GUI hiển thị khác reader cũ | JDK/JMC version hoặc event schema khác. | Đối chiếu metadata và bản công cụ, test với chính file đó. |
| Số liệu “CPU time” cao bất thường | Cộng elapsed durations của nhiều threads hoặc I/O waits. | Phân biệt wall time, blocked time, CPU samples. |
| Output thiếu một phần vì file bị cắt | I/O/chunk lỗi xảy ra sau vài events. | Báo incomplete; không khẳng định full scan thành công. |

## 13. Chiến lược kiểm thử consumer JFR

Đừng chỉ kiểm thử `new RecordingFile(...)` thành công. Cần xác minh cả **nội dung và ý nghĩa**:

| Test | Fixture | Kết quả mong đợi |
| --- | --- | --- |
| **File hợp lệ có một type** | Ghi vài custom events `lesson.StageStep`. | `hasMoreEvents/readEvent` duyệt đúng count/type. |
| **Nhiều type cùng file** | StageStep + Marker như mục 8. | Chỉ cộng `units` cho StageStep, Marker đếm riêng. |
| **Metadata** | `readEventTypes()` và fields của StageStep. | Có `stage` và `units` với type phù hợp. |
| **Tổng hợp** | StageStep load=5/transform=7/save=11. | Count=3, total=23, groups đúng. |
| **Timestamp/duration** | Events có `begin/end`. | Không giả định millis cố định; duration không âm. |
| **Event type lạ** | Recording chứa thêm JVM/custom event. | Bỏ qua an toàn, không phá thống kê đã lọc. |
| **Schema khác version** | File có field đổi tên/kiểu. | Adapter từ chối có thông báo hoặc dùng nhánh tương thích rõ. |
| **File trống/không có type cần** | Recording không có occurrences của type. | Đếm = 0 nhưng nêu settings có thể là nguyên nhân. |
| **File hỏng/truncated** | Bản copy thiếu byte/không phải JFR. | Báo `IOException` hoặc lỗi phù hợp; không xuất success sai. |
| **Large recording** | File nhiều chunks và hàng triệu occurrences. | Memory tăng theo nhóm/DTO có giới hạn, không tăng tuyến tính do giữ mọi event. |
| **Dữ liệu nhạy cảm** | Fixture có field cần che trước xuất. | Reporter không in raw secret/PII/stack dump ngoài chính sách. |
| **Phiên bản JDK** | Files từ các JDK được sản phẩm hỗ trợ. | Reader đúng schema hoặc báo không tương thích thay vì đoán. |

Mục 8 là **unit/integration test ở cấp API consumer**, vì nó vừa tạo **file JFR thật** vừa đọc bằng `RecordingFile`. Khi phát triển parser production, nên có thêm **golden files** từ các phiên bản JDK khác nhau và test đối chiếu bằng `jfr summary`/`jfr print`.

Lưu ý: dữ liệu test có thể thay đổi file size/timestamp giữa các lần chạy, nên **không** viết assertion so sánh toàn bộ file binary byte-for-byte hoặc `Instant.now()`. Kiểm tra những thuộc tính tất định: type, giá trị các fields, count, grouping, tính hợp lệ của duration và đường đọc thành công.

## 14. Các ngộ nhận quan trọng

| Ngộ nhận | Thực tế |
| --- | --- |
| “`RecordingFile` là cách ghi JFR.” | Nó **đọc** file; `Recording` mới là API điều khiển thu thập và dump. |
| “`readEventTypes()` trả mọi occurrences.” | Nó trả **metadata loại sự kiện**, không phải danh sách những lần xảy ra. |
| “`hasMoreEvents()` trả một event.” | Nó chỉ trả `boolean`, cần `readEvent()` để lấy occurrence. |
| “`readEvent()` có thể gọi vô hạn rồi trả `null`.” | Khi không còn event, Javadoc mô tả `EOFException`; nên kiểm tra `hasMoreEvents`. |
| “`readAllEvents` luôn tốt hơn vòng lặp.” | Nó có thể giữ mọi event trong RAM; Oracle chỉ khuyến nghị cho file nhỏ. |
| “Mỗi file JFR chỉ có một loại event.” | Một recording có thể chứa nhiều event types, gồm JVM và custom events. |
| “Event type ID của một file được giữ nguyên trong mọi file.” | Không nên hard-code numeric ID; dùng tên type/schema. |
| “`getDuration` đo chính xác CPU time.” | Không: thường là **elapsed duration** của event; chờ I/O/lock cũng có thể kéo dài. |
| “Không có event tức là không có hoạt động đó.” | Có thể do settings, sampling, threshold hoặc cửa sổ ghi. |
| “Có `getThread`/`getStackTrace` chắc chắn không null.” | Thông tin này có thể không được ghi. |
| “`hasField` true chứng minh field đúng kiểu.” | Cần kiểm tra field type/schema trước typed getter khi nguồn đa phiên bản. |
| “Truy cập `thread.group.parent.name` luôn an toàn.” | Nested object có thể null, dẫn đến lỗi; kiểm tra mỗi cấp theo schema. |
| “Reader sẽ luôn trả events sắp theo start time toàn cục.” | Không nên dựa vào giả định không được bảo đảm để dừng filter sớm. |
| “File `.jfc` là recording để `RecordingFile` đọc.” | Không: `.jfc` là **recording settings**, khác file `.jfr`. |
| “File `.jfr` là JSON.” | Không: đó là định dạng nhị phân; JSON chỉ là một dạng **xuất ra** qua công cụ. |
| “Có Java 11 thì tự động có GUI JMC.” | Không: JMC được phân phối riêng, không phải cửa sổ đi kèm mọi JDK 11. |
| “File JFR từ Internet có thể parse vô tư.” | Javadoc `RecordingFile` yêu cầu **nguồn tin cậy**; cần cách ly/giới hạn tài nguyên nếu phải xử lý nguồn không tin cậy. |
| “Đã parse một phần file thì báo đầy đủ được.” | Không: lỗi giữa chừng phải đánh dấu partial hoặc fail theo yêu cầu báo cáo. |
| “Các API mới trong tài liệu JDK 25 chắc chắn chạy trên Java 11.” | Không: phải đối chiếu Javadoc của đúng phiên bản và biên dịch `--release 11`. |

## 15. Checklist triển khai Java 11+ cho một bộ đọc `RecordingFile`

1. Chỉ nhận tệp **`.jfr`** hợp lệ từ nguồn được phép, kiểm tra quyền đọc và quota kích thước.
2. Dùng đúng module **`jdk.jfr`** và package **`jdk.jfr.consumer`**, không tự parse file nhị phân bằng `InputStream`/regex.
3. Tạo `RecordingFile` trong **try-with-resources** để đóng trong mọi trường hợp.
4. Nếu chưa biết schema, duyệt `readEventTypes()`; phân biệt metadata type với occurrences.
5. Duyệt tuần tự **`hasMoreEvents()` → `readEvent()`**, tránh đọc quá EOF.
6. Lọc `getEventType().getName()` trước khi đọc field riêng của một type.
7. Kiểm tra `hasField` và **ValueDescriptor type** nếu cần tương thích nhiều JDK.
8. Dùng `getStartTime/getEndTime/getDuration` đúng đơn vị/ý nghĩa; xử lý thread/stack trace có thể null.
9. Tổng hợp theo group có cardinality hạn chế; tránh `readAllEvents` hoặc giữ toàn bộ `RecordedEvent` của file lớn.
10. Tách occurrence count khỏi sampling estimates và CPU time; đọc recording settings/window trước khi kết luận.
11. Nếu file hỏng/reader lỗi, báo **incomplete/failed** có hành động tiếp theo; không xuất số liệu nửa chừng như full scan.
12. Thử cả file đa type, thiếu field, field sai kiểu, thời gian khác cửa sổ, file lớn và file có phiên bản khác.
13. Bảo vệ dữ liệu nhạy cảm: không log nguyên event, stack traces, command line, path, secrets hoặc thông tin người dùng tùy tiện.
14. Đối chiếu độc lập với **`jfr summary`**, `jfr print --events` và metadata khi cần.
15. Giữ code tương thích Java 11 bằng `javac --release 11`; chỉ lấy kiến thức/API còn đang áp dụng thay vì các cờ JFR thương mại cũ của JDK 8 hoặc API mới không có ở target.

### Nguồn tài liệu chính thức

- [Oracle Java SE 11 — `jdk.jfr.consumer.RecordingFile`, vòng lặp `hasMoreEvents/readEvent`, `readEventTypes` và `readAllEvents`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [Oracle Java SE 11 — `jdk.jfr.consumer.RecordedEvent` và các timestamps/durations](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html)
- [Oracle Java SE 11 — `jdk.jfr.consumer.RecordedObject`, `hasField` và các typed getters](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html)
- [Oracle Java SE 11 — `jdk.jfr.EventType` và thông tin loại sự kiện](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventType.html)
- [Oracle Java SE 11 — `jdk.jfr.ValueDescriptor` (field name/type)](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/ValueDescriptor.html)
- [Oracle Java SE 11 — `jdk.jfr.Recording`, `enable`/`start`/`stop`/`dump`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Oracle Java SE 11 — module `jdk.jfr`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/module-summary.html)
- [OpenJDK JEP 328 — Flight Recorder tích hợp OpenJDK 11](https://openjdk.org/jeps/328)
- [Oracle Java SE 25 — `RecordingFile` để kiểm tra API vẫn đang sử dụng](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
