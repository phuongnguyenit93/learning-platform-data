# Truy vấn trường dữ liệu và metadata khi đọc bản ghi JFR (Java 11+)

## 1. Hai câu hỏi khác nhau: “sự kiện chứa gì?” và “trường đó có nghĩa gì?”

**Java Flight Recorder (JFR)** trong JDK cung cấp dữ liệu chẩn đoán và hiệu năng theo mô hình **event types** và **recorded events**. Từ Java 11, module công khai `jdk.jfr` cho phép đọc file `.jfr`, truy xuất từng event, lấy giá trị field và phân tích metadata mô tả schema. Các API cốt lõi này **vẫn có hiệu lực trên các JDK hiện đại**.

Khi xử lý một bản ghi, cần phân biệt:

- **Giá trị dữ liệu (data)**: event cụ thể có `rows=3`, `success=true`, `bytes=256`, được ghi vào thời điểm nào, có duration bao nhiêu.
- **Metadata/schema**: event type tên gì, mỗi field tên và kiểu gì, nhãn gì, có annotation `@Timespan` hay `@DataAmount`, một field có tồn tại trong **phiên bản recording đang đọc** hay không.
- **Settings metadata**: một event type có những loại setting nào (enabled, threshold, stackTrace...), **không đồng nghĩa** file ghi lại chính xác toàn bộ cấu hình runtime của mọi recording.
- **Kiểu dữ liệu phân tích**: field là `Class` hoặc `Thread` được lưu thành **metadata snapshot** đọc qua `RecordedClass`/`RecordedThread`, **không phải** object `Class<?>`/`Thread` sống của tiến trình đã ghi.

Ví dụ luồng dữ liệu:

```text
application/JVM                    file JFR              Java 11 reader
       |                               |                          |
  Event.commit() --> Recording.dump("trace.jfr")              |
                                       |                          |
                                       +--> RecordingFile(path) ---+
                                               |
                           +-------------------+------------------+
                           |                                      |
                   readEventTypes()                          readEvent()
                           |                                      |
                         EventType                          RecordedEvent
                           |                                      |
                  ValueDescriptor[]                    getString/getLong...
                    (schema/units)                     getDuration/getThread...
                           +-------------------+------------------+
                                               |
                                  phân tích dữ liệu có kiểm tra schema
```

**Điểm quan trọng:** một **`EventType`** mô tả **nhiều instances**; `RecordedEvent` là **một instance**. Một file `.jfr` có thể chứa nhiều event types, nhiều chunks, các events mặc định của JVM và events ứng dụng. Không nên lấy “event đầu tiên trong file” làm đại diện cho loại sự kiện mong muốn.

## 2. Các class/API quan trọng trong Java 11

| API | Thuộc package | Vai trò chính |
| --- | --- | --- |
| `RecordingFile` | `jdk.jfr.consumer` | Mở một file JFR đáng tin cậy, đọc sự kiện tuần tự và liệt kê event types |
| `RecordedEvent` | `jdk.jfr.consumer` | Một sự kiện đã ghi, chứa field values, thời gian, thread, stack trace (nếu có) |
| `RecordedObject` | `jdk.jfr.consumer` | Class cha cung cấp `getValue`, typed getters, `hasField` và truy vấn field lồng nhau |
| `EventType` | `jdk.jfr` | Metadata của event type: tên, label, category, field descriptors, setting descriptors |
| `ValueDescriptor` | `jdk.jfr` | Metadata một field: tên, type, label, description, annotations và cấu trúc nested |
| `SettingDescriptor` | `jdk.jfr` | Mô tả một setting type được event type hỗ trợ |
| `RecordedClass` | `jdk.jfr.consumer` | Mô tả class được ghi, như tên class và class loader; không phải `java.lang.Class` |
| `RecordedThread` | `jdk.jfr.consumer` | Mô tả thread được ghi, như Java thread name/id; không phải live `java.lang.Thread` |
| `RecordedStackTrace` | `jdk.jfr.consumer` | Stack trace được ghi nếu recording bật và event thực sự có stack |
| `Recording` | `jdk.jfr` | Bật event và dump ra `.jfr` trong ví dụ; **không phải API đọc file** |

**Phân biệt API đọc và ghi:**

```java
// API ghi: jdk.jfr.Recording.
try (Recording recording = new Recording()) {
    // enable event -> start -> commit -> stop/dump
}

// API đọc: jdk.jfr.consumer.RecordingFile.
try (RecordingFile file = new RecordingFile(path)) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        // Truy vấn field và metadata.
    }
}
```

Đây là **khung minh họa**, không phải chương trình độc lập: biến `path` và bước cấu hình recording cần được cung cấp. Bài runnable ở mục 7 sẽ tạo, dump và đọc lại một file JFR thật.

## 3. Mở file, liệt kê event types và lọc events

Mẫu đọc phổ biến trong Java 11:

```java
try (RecordingFile file = new RecordingFile(path)) {
    for (EventType type : file.readEventTypes()) {
        System.out.println(type.getName());
    }

    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        if (!event.getEventType().getName().equals("demo.QueryOperation")) {
            continue;
        }
        // Chỉ truy vấn các event cần thiết.
    }
}
```

Đây là **đoạn minh họa**, cần biến `path` kiểu `Path` và các import Java/JFR.

**`RecordingFile.readEventTypes()`** trả danh sách `EventType` có trong metadata của file. Dùng nó để **khám phá schema trước khi đọc field values**. Sự có mặt của một event type trong metadata **không bảo đảm** có ít nhất một event instance của type ấy trong file.

**`hasMoreEvents()`** và **`readEvent()`** đọc tuần tự toàn bộ events, không tự lọc theo type. Vì vậy, hãy lọc bằng `getEventType().getName()`, hoặc dùng các tiêu chí như thời gian/field value **sau khi** xác minh schema phù hợp.

**`RecordingFile.readAllEvents(path)`** tiện cho tệp nhỏ và thử nghiệm, nhưng nó tạo list trong bộ nhớ. Với tệp nhiều trăm MB/GB, lặp `hasMoreEvents()/readEvent()` thường có mức tiêu thụ RAM hợp lý hơn. Đây vẫn là đọc tuần tự: nếu cần truy vấn lặp đi lặp lại theo nhiều điều kiện trên dữ liệu rất lớn, cân nhắc chuyển đổi sang hệ thống phân tích/bảng có chỉ mục riêng.

**Không truyền đường dẫn thư mục repository cho `RecordingFile`** như thể nó là một file `.jfr`. Hãy tạo bản dump đã hoàn thành hoặc một file JFR hợp lệ. `RecordingFile` chỉ nhận file từ **nguồn đáng tin cậy**; input nhị phân không đáng tin có thể khiến parser gặp lỗi hoặc rủi ro an ninh.

## 4. Truy vấn metadata của event type

`RecordedEvent.getEventType()` trả `EventType` cho instance hiện tại. Ngoài ra, một `EventType` có thể lấy từ `RecordingFile.readEventTypes()`. Các phương thức thiết yếu:

| `EventType` API | Kết quả |
| --- | --- |
| `getName()` | Tên định danh event type, ví dụ `"demo.QueryOperation"` |
| `getLabel()` | Nhãn dễ đọc, có thể `null` |
| `getDescription()` | Mô tả dễ đọc, có thể `null` |
| `getCategoryNames()` | Danh sách tên category phân cấp |
| `getFields()` | Danh sách `ValueDescriptor` của các fields được type mô tả |
| `getField("rows")` | Một `ValueDescriptor`, hoặc `null` nếu không có field đó |
| `getAnnotationElements()` | Metadata annotations của event type |
| `getAnnotation(MyAnnotation.class)` | Annotation phù hợp nếu có |
| `getSettingDescriptors()` | Danh sách metadata của các settings event type hỗ trợ |
| `getId()` | ID event type trong JVM/recording context; **không dùng làm ID kinh doanh ổn định** |

Một cách truy vấn cẩn thận:

```java
EventType type = event.getEventType();
System.out.println("type=" + type.getName());

ValueDescriptor rows = type.getField("rows");
if (rows != null && "int".equals(rows.getTypeName())) {
    int n = event.getInt("rows");
    System.out.println("rows=" + n);
}
```

Đoạn này cần `event` kiểu `RecordedEvent`, các import `EventType` và `ValueDescriptor`.

**Tên định danh vs nhãn:** `@Name("demo.QueryOperation")` định danh type; `@Label("Query Operation")` hiển thị cho người dùng. `RecordedEvent.getEventType().getName()` trả **tên type**, không trả label. Với field `@Label("Row Count") int rows;`, getter vẫn dùng **`"rows"`** chứ không dùng `"Row Count"`.

**Thứ tự fields:** `getFields()` có thể gồm những fields chuẩn do JFR bổ sung như start time, duration, event thread và stack trace (tùy event type), **không chỉ** fields do subclass khai báo. Không dùng một index cứng (ví dụ field số 3) để suy ra `rows`; ưu tiên tra theo tên.

### Metadata về setting không thay thế cấu hình ghi thực tế

`EventType.getSettingDescriptors()` cho biết loại setting được event type **hỗ trợ**; các settings như `enabled`, `threshold`, `stackTrace`, `period` có thể được recording điều chỉnh. Không lấy danh sách descriptors rồi kết luận event nhất định đã được ghi với từng giá trị default. File JFR là dữ liệu được thu **sau khi** các settings có hiệu lực; đọc trực tiếp các fields/thời gian thực có ý nghĩa hơn là suy đoán một config không được lưu.

### Vấn đề tương thích nhiều bản JDK

Built-in event types, một số field names và metadata có thể thay đổi giữa bản JDK. Đừng viết parser chỉ dựa vào danh sách field cố định của một bản JDK khác. Với custom events do bạn kiểm soát, hãy đặt tên có namespace ổn định, duy trì schema và version hóa khi thay đổi phá vỡ compatibility.

## 5. `ValueDescriptor`: schema của một field

`ValueDescriptor` mô tả **field có tồn tại, tên gì, type gì, đơn vị gì**; nó **không chứa giá trị của từng recorded event instance**.

| `ValueDescriptor` API | Ý nghĩa |
| --- | --- |
| `getName()` | Tên field dùng trong typed getters |
| `getTypeName()` | Tên kiểu Java được ghi, ví dụ `"int"` hoặc `"java.lang.String"` |
| `getLabel()` | Nhãn dễ đọc (có thể `null`) |
| `getDescription()` | Mô tả (có thể `null`) |
| `getAnnotation(Timespan.class)` | Có metadata đơn vị thời gian `@Timespan` hay không |
| `getAnnotation(DataAmount.class)` | Có metadata lượng dữ liệu `@DataAmount` hay không |
| `getAnnotationElements()` | Danh sách annotation metadata |
| `getFields()` | Các fields con nếu kiểu phức hợp được JFR mô tả |
| `isArray()` | Schema field có mô tả mảng hay không |

Ví dụ phân biệt **giá trị 25 mili-giây** và **metadata cho phép diễn giải đơn vị**:

```java
ValueDescriptor duration = type.getField("backendMillis");
if (duration != null) {
    boolean hasUnit =
            duration.getAnnotation(Timespan.class) != null;
    System.out.println("hasUnit=" + hasUnit);
}
```

Đây là đoạn minh họa với `type` là `EventType`. Nếu field ghi `long backendMillis` và mang `@Timespan(Timespan.MILLISECONDS)`, metadata giúp phương thức `RecordedObject.getDuration("backendMillis")` chuyển giá trị số sang `java.time.Duration` tương ứng. Nó **không tự đo** thời gian xử lý hoặc thay đổi giá trị thô.

**Lưu ý về `isArray()` và custom events:** khi đọc built-in metadata của JVM, JFR có thể có những cấu trúc field/array mà API consumer mô tả. Nhưng trong một custom event `extends Event` của Java 11, **không phải mọi Java array/object field đều được ghi**. Hãy kiểm tra schema file thật; đừng suy rằng một `String[]` được định nghĩa trong event class chắc chắn đã tồn tại trong file. Mã runnable ở mục 7 sẽ xác minh trường array và `transient` bị bỏ qua.

### Metadata dạng cấp bậc và cấu trúc lồng nhau

Một số built-in event field có kiểu dữ liệu JFR phức hợp, chẳng hạn `RecordedThread`, `RecordedClass` hay `RecordedStackTrace`. `ValueDescriptor.getFields()` cho phép duyệt metadata con của loại phức hợp khi có. Khi hiển thị schema, đặt giới hạn độ sâu, độ dài và bảo vệ trường hợp thiếu/null: không nên biến việc inspect một file lớn thành in vô hạn metadata hay dữ liệu nhạy cảm.

## 6. `RecordedObject` và `RecordedEvent`: lấy giá trị an toàn

### 6.1. Kiểm tra tồn tại trước khi đọc

`RecordedEvent` kế thừa `RecordedObject`, cung cấp:

```java
if (event.hasField("rows")) {
    int rows = event.getInt("rows");
    System.out.println(rows);
}
```

`hasField(name)` kiểm tra **schema của event** có field đó không; nó **không nói rằng giá trị không null**. Một field tham chiếu có thể **tồn tại** nhưng giá trị `null`.

**Ba trạng thái khác nhau:**

1. **Field không tồn tại**: `hasField("optionalNote")==false`; `getValue("optionalNote")` thường ném `IllegalArgumentException`.
2. **Field tồn tại nhưng giá trị null**: `hasField("optionalNote")==true` và `getValue("optionalNote")==null`.
3. **Field tồn tại và có giá trị**: dùng typed getter phù hợp sau khi kiểm tra kiểu/schema.

Đừng dùng `getValue("field")==null` làm cách duy nhất để hỏi field có tồn tại không: hàm có thể ném exception khi không có field.

### 6.2. Typed getters và cách chọn cho đúng type

| Kiểu field JFR | API đọc thường dùng | Kết quả |
| --- | --- | --- |
| `boolean` | `getBoolean("success")` | `boolean` |
| `byte` | `getByte("code")` | `byte` |
| `short` | `getShort("shard")` | `short`, có hỗ trợ widening từ byte |
| `char` | `getChar("symbol")` | `char` |
| `int` | `getInt("rows")` | `int` (có widening từ các primitive nhỏ thích hợp) |
| `long` | `getLong("bytes")` | `long` (có widening từ int/short/char/byte thích hợp) |
| `float` | `getFloat("ratio")` | `float` |
| `double` | `getDouble("load")` | `double` |
| `String` | `getString("operation")` | `String` hoặc `null` |
| `Class` | `getClass("owner")` | `RecordedClass` hoặc `null` |
| `Thread` | `getThread("originThread")` | `RecordedThread` hoặc `null` |
| Field có `@Timespan` | `getDuration("backendMillis")` | `Duration` theo đơn vị của metadata |
| Field có `@Timestamp` | `getInstant("timestampField")` | `Instant` theo timestamp metadata |
| Kiểu khác hay field cấu trúc | `getValue("field")` | Giá trị tương ứng, có thể `null`; cần kiểm soát kiểu |

**Không phải getter nào cũng chuyển mọi kiểu.** `getInt` chỉ widening một số primitive số nhỏ; `getLong` chấp nhận một số trường có kiểu phù hợp; không mặc định `getString` sẽ tự gọi `toString()` trên mọi field. Dùng typed getter sai type hoặc field không có trong schema có thể ném `IllegalArgumentException`. Một số getter có xử lý `@Unsigned` khi widening; không tự hiểu mọi long âm là lỗi hay giá trị unsigned nếu chưa biết metadata.

### 6.3. `getValue(name)` là API linh hoạt nhưng không phải cast tùy ý

`getValue(String)` trả kiểu tổng quát `<T> T` để có thể lấy primitive/wrapper hoặc object kiểu JFR theo field, và hỗ trợ chuỗi tên lồng nhau bằng dấu chấm (`"parent.child"`).

```java
if (event.hasField("owner")) {
    RecordedClass cls = event.getValue("owner");
    if (cls != null) {
        String name = cls.getName();
        // Dùng name cho việc phân tích nếu hợp lệ.
    }
}
```

Đây là đoạn minh họa với `event` kiểu `RecordedEvent` và import `RecordedClass`. Dù cú pháp generic cho phép gán vào biến kiểu `T`, **kiểu runtime không tự chuyển** thành object khác. Ví dụ field `Class<?> owner` từ lúc ghi được đọc thành `RecordedClass`; ép sang `Class<?>` là sai.

Nếu query field nested (`"originThread.javaName"` hoặc đường dẫn JFR phù hợp), các cấp trung gian phải tồn tại và **không null**. Nếu trung gian null, Javadoc `RecordedObject` cho phép ném `NullPointerException`. Vì vậy, với dữ liệu có thể thiếu, an toàn hơn là đọc `RecordedThread thread = event.getThread("originThread")` rồi kiểm tra null, sau đó gọi `thread.getJavaName()`, thay vì đi thẳng qua một chuỗi đường dẫn chưa được kiểm chứng.

### 6.4. Thời gian của event khác với field đo thời gian

`RecordedEvent` có:

- `getStartTime(): Instant` — thời điểm bắt đầu.
- `getEndTime(): Instant` — thời điểm kết thúc; với instant event, bằng start.
- `getDuration(): Duration` — **duration chuẩn của event**, thường lấy từ `Event.begin()/end()`.
- `getThread(): RecordedThread` — thread gắn với event nếu có, **có thể null**.
- `getStackTrace(): RecordedStackTrace` — stack trace nếu được thu, **có thể null**.

Trong khi đó, `getDuration("backendMillis")` là một **field riêng** có annotation `@Timespan`. Nếu giá trị thô `backendMillis=10` và đơn vị MILLISECONDS, getter chuyển về `Duration.ofMillis(10)`. **Không được** đồng nhất 10 ms nghiệp vụ đó với `RecordedEvent.getDuration()`: duration chuẩn của event có thể chỉ vài micro/millisecond.

Tương tự, metadata từ `@Timestamp` cần được hiểu theo đơn vị timestamp; không tự quy đổi epoch millis/nanos bằng phỏng đoán nếu schema đã có đơn vị chính thức.

## 7. Chương trình Java hoàn chỉnh: tạo file, truy vấn field values và metadata

Bài demo sau dùng **toàn API Java 11**, không cần Internet và không đụng tới repository của một tiến trình khác. Nó ghi một custom event type gồm nhiều field, xuất file `.jfr` vào thư mục tạm rồi đọc lại:

- Kiểm tra metadata type: tên, label, category và kiểu `int`.
- Kiểm tra `@Timespan(MILLISECONDS)`, `@DataAmount(BYTES)` thông qua `ValueDescriptor.getAnnotation`.
- Kiểm tra field `transient` và array **không có trong JFR schema**.
- Đọc 3 instances bằng `RecordedEvent.getString/getInt/getLong/getBoolean/getDuration(field)`.
- Kiểm tra field tham chiếu `optionalNote` **có tồn tại nhưng null**.
- Kiểm tra `Class<?>` và `Thread` được đọc thành `RecordedClass`/`RecordedThread`.
- Không phụ thuộc thời gian thực, file size, event type ID hay thứ tự events của JFR; dùng `TreeMap` cho kết quả ổn định.
- Đóng `Recording` và `RecordingFile`, dọn output sau khi thử.

Lưu vào file **`JfrMetadataQueryDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import java.util.TreeMap;
import jdk.jfr.Category;
import jdk.jfr.DataAmount;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.EventType;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.Timespan;
import jdk.jfr.ValueDescriptor;
import jdk.jfr.consumer.RecordedClass;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedThread;
import jdk.jfr.consumer.RecordingFile;

public class JfrMetadataQueryDemo {
    @Name("demo.QueryOperation")
    @Label("Query Operation")
    @Description("Small example of custom event metadata.")
    @Category({"Demo", "Metadata"})
    static class QueryOperation extends Event {
        @Label("Operation") String operation;
        @Label("Row Count") int rows;
        @Timespan(Timespan.MILLISECONDS) long backendMillis;
        @DataAmount(DataAmount.BYTES) long bytes;
        boolean success;
        Class<?> owner;
        Thread originThread;
        String optionalNote;
        transient String ignoredTransient = "no";
        String[] ignoredArray = {"no"};
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("jfr-query-");
        Path output = dir.resolve("query.jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                recording.enable(QueryOperation.class)
                        .withThreshold(Duration.ZERO)
                        .withoutStackTrace();
                recording.start();
                for (int i = 1; i <= 3; i++) {
                    QueryOperation e = new QueryOperation();
                    e.operation = "op-" + i;
                    e.rows = i;
                    e.backendMillis = i * 5L;
                    e.bytes = i * 128L;
                    e.success = i != 2;
                    e.owner = JfrMetadataQueryDemo.class;
                    e.originThread = Thread.currentThread();
                    e.begin();
                    e.end();
                    e.commit();
                }
                recording.stop();
                recording.dump(output);
            }

            EventType schema = null;
            Map<String, String> values = new TreeMap<>();
            int count = 0;
            int successCount = 0;
            int totalRows = 0;
            long totalBytes = 0;
            boolean metadataFromFile = false;
            boolean ownerCorrect = true;
            boolean threadCorrect = true;
            boolean durationsConsistent = true;
            boolean nullableValue = true;
            boolean stackTracesDisabled = true;
            boolean startTimePresent = true;
            try (RecordingFile file = new RecordingFile(output)) {
                for (EventType type : file.readEventTypes()) {
                    if (type.getName().equals("demo.QueryOperation")) {
                        schema = type;
                    }
                }
                metadataFromFile = schema != null;
                while (file.hasMoreEvents()) {
                    RecordedEvent e = file.readEvent();
                    if (!e.getEventType().getName()
                            .equals("demo.QueryOperation")) {
                        continue;
                    }
                    count++;
                    if (e.getBoolean("success")) {
                        successCount++;
                    }
                    totalRows += e.getInt("rows");
                    totalBytes += e.getLong("bytes");
                    String op = e.getString("operation");
                    values.put(op, e.getInt("rows") + ":" +
                            e.getDuration("backendMillis").toMillis());
                    RecordedClass owner = e.getClass("owner");
                    RecordedThread thread = e.getThread("originThread");
                    ownerCorrect &= owner != null &&
                            owner.getName().equals("JfrMetadataQueryDemo");
                    threadCorrect &= thread != null &&
                            "main".equals(thread.getJavaName());
                    durationsConsistent &=
                            e.getDuration("backendMillis").toMillis() ==
                            e.getLong("backendMillis");
                    nullableValue &= e.hasField("optionalNote") &&
                            e.getValue("optionalNote") == null;
                    stackTracesDisabled &= e.getStackTrace() == null;
                    startTimePresent &= e.getStartTime() != null &&
                            !e.getDuration().isNegative();
                }
            }
            if (!metadataFromFile) {
                throw new IllegalStateException("Missing event schema");
            }
            ValueDescriptor durationField = schema.getField("backendMillis");
            ValueDescriptor bytesField = schema.getField("bytes");
            System.out.println("eventType=" + schema.getName());
            System.out.println("eventLabel=" + schema.getLabel());
            System.out.println("categories=" +
                    String.join("/", schema.getCategoryNames()));
            System.out.println("rowsType=" +
                    schema.getField("rows").getTypeName());
            System.out.println("hasDurationAnnotation=" +
                    (durationField.getAnnotation(Timespan.class) != null));
            System.out.println("hasBytesAnnotation=" +
                    (bytesField.getAnnotation(DataAmount.class) != null));
            System.out.println("ignoredTransient=" +
                    (schema.getField("ignoredTransient") == null));
            System.out.println("ignoredArray=" +
                    (schema.getField("ignoredArray") == null));
            System.out.println("missingField=" +
                    (schema.getField("nonexistent") == null));
            System.out.println("fromRecordingMetadata=" + metadataFromFile);
            System.out.println("events=" + count);
            System.out.println("successful=" + successCount);
            System.out.println("totalRows=" + totalRows);
            System.out.println("totalBytes=" + totalBytes);
            System.out.println("ownerAsRecordedClass=" + ownerCorrect);
            System.out.println("threadAsRecordedThread=" + threadCorrect);
            System.out.println("durationFieldConverted=" +
                    durationsConsistent);
            System.out.println("nullableField=" + nullableValue);
            System.out.println("noStackTraces=" + stackTracesDisabled);
            System.out.println("startTimeAndDuration=" + startTimePresent);
            for (Map.Entry<String, String> row : values.entrySet()) {
                System.out.println(row.getKey() + "=" + row.getValue());
            }
        } finally {
            Files.deleteIfExists(output);
            Files.deleteIfExists(dir);
        }
    }
}
```

**Biên dịch và chạy:** sử dụng JDK 11 trở lên (có module `jdk.jfr`). Lệnh `--release 11` xác nhận chương trình không gọi API bổ sung sau Java 11:

```bash
javac --release 11 JfrMetadataQueryDemo.java
java JfrMetadataQueryDemo
```

**Stdout chính xác** trên JDK có JFR khả dụng, được phép ghi thư mục tạm:

```text
eventType=demo.QueryOperation
eventLabel=Query Operation
categories=Demo/Metadata
rowsType=int
hasDurationAnnotation=true
hasBytesAnnotation=true
ignoredTransient=true
ignoredArray=true
missingField=true
fromRecordingMetadata=true
events=3
successful=2
totalRows=6
totalBytes=768
ownerAsRecordedClass=true
threadAsRecordedThread=true
durationFieldConverted=true
nullableField=true
noStackTraces=true
startTimeAndDuration=true
op-1=1:5
op-2=2:10
op-3=3:15
```

Ví dụ đã được **biên dịch thực tế bằng `javac --release 11` và chạy trên OpenJDK 24**, cho đúng **23 dòng** như trên. Trong JVM dựng bằng `jlink` thiếu module JFR, JFR bị vô hiệu hóa hoặc không có quyền ghi tệp tạm, chương trình cần môi trường thích hợp. Dùng `FlightRecorder.isAvailable()` để kiểm tra khả dụng khi tích hợp vào CI đa nền tảng.

### Đọc 23 dòng output

**Nhóm metadata:**

- `eventType`, `eventLabel`, `categories` là thông tin của `EventType` mà reader lấy từ metadata bên trong file, không phải chuỗi tự suy đoán từ tên class.
- `rowsType=int` lấy trực tiếp từ `ValueDescriptor.getTypeName()`.
- `hasDurationAnnotation=true` chứng minh field `backendMillis` có `@Timespan`, nên reader có thể diễn giải bằng `getDuration("backendMillis")`.
- `hasBytesAnnotation=true` chứng minh `bytes` có `@DataAmount(BYTES)`. Annotation chỉ định **đơn vị**; nó không đo và không sửa dữ liệu.
- `ignoredTransient=true` / `ignoredArray=true` chứng minh các Java fields đó **không được ghi vào custom event schema JFR**, dù chúng tồn tại trong source code.
- `missingField=true` chứng minh `getField("nonexistent") == null`; cần kiểm tra trước khi gọi typed getter.
- `fromRecordingMetadata=true` xác nhận type tìm thấy trong `RecordingFile.readEventTypes()`.

**Nhóm data values:**

- `events=3`, `successful=2`: ba custom instances, một instance có `success=false`.
- `totalRows=6` và `totalBytes=768`: tổng cộng 1+2+3 rows và 128+256+384 bytes.
- `ownerAsRecordedClass=true`, `threadAsRecordedThread=true`: truy vấn `getClass("owner")` / `getThread("originThread")` và đọc metadata name, không thử cast thành đối tượng Java live.
- `durationFieldConverted=true`: `getDuration("backendMillis").toMillis()` khớp giá trị `getLong("backendMillis")` ở những events có annotation MILLISECONDS.
- `nullableField=true`: `optionalNote` **có trong schema** nhưng chưa gán, nên giá trị đọc là `null`. Đây không giống missing field.
- `noStackTraces=true`: recording đặt `withoutStackTrace()`, nên `RecordedEvent.getStackTrace()` không có dữ liệu.
- `startTimeAndDuration=true`: thời gian bắt đầu tồn tại và duration không âm; demo **không assert chính xác thời gian chạy**, vốn biến động theo môi trường.
- `op-1`, `op-2`, `op-3`: `TreeMap` sắp theo tên `operation`, không phụ thuộc event order hoặc thread scheduling của JFR.

### Vì sao không hardcode tổng số fields hoặc kích thước file?

JFR còn có những **standard fields** và metadata phụ trợ; số lượng có thể khác theo event type/JDK. Recording file có thể chứa nhiều built-in events dù demo chỉ bật type cần quan tâm. File size, event type ID, thời điểm và stack traces không phải những số ổn định cho mọi JVM. Test đúng mục tiêu là **schema mong đợi tồn tại**, **typed values đúng**, và **các fields không hỗ trợ bị bỏ qua**.

## 8. Trường cấu trúc, thread và stack trace: đọc đến đâu?

Một số JFR events ghi những thông tin phức hợp như thread, class hoặc stack frames. Chúng được mô hình hóa dưới `RecordedObject`:

```java
RecordedThread thread = event.getThread("originThread");
if (thread != null) {
    String name = thread.getJavaName();
    long id = thread.getJavaThreadId();
}
RecordedClass owner = event.getClass("owner");
if (owner != null) {
    String className = owner.getName();
}
```

Đây là đoạn **minh họa** với `event` thuộc type có các field tương ứng. `getJavaThreadId()` là ID thread được ghi, không đảm bảo một giá trị có ý nghĩa ngoài phạm vi JVM gốc; `RecordedClass.getId()` cũng không phải khóa toàn cục ổn định giữa các lần chạy.

**Stack trace:**

```java
RecordedStackTrace trace = event.getStackTrace();
if (trace != null) {
    for (RecordedFrame frame : trace.getFrames()) {
        // Kiểm tra frame.isJavaFrame(), getMethod(), getLineNumber()...
    }
}
```

Đây là đoạn minh họa, cần import `RecordedStackTrace` và `RecordedFrame`. Nếu event setting tắt stack trace, `getStackTrace()` trả `null`; nếu có, một số frames không nhất thiết có line number/source mapping đầy đủ. Đừng coi stack trace **luôn có** chỉ vì ứng dụng có code Java.

Một field phức hợp có thể truy vấn bằng `getValue("parent.child")` khi metadata và giá trị trung gian hợp lệ. Tuy nhiên, khi cần code ổn định qua JDK versions, đọc object cha, kiểm tra null/schema, rồi dùng typed API cụ thể. Khi xuất báo cáo, tránh log toàn bộ stack trace/thread/class metadata ở hệ thống công khai nếu có đường dẫn hệ thống hoặc tên nghiệp vụ nhạy cảm.

## 9. Phân tích metadata độc lập trước khi trích giá trị

Khi nhận file `.jfr` từ một service không cùng version với công cụ đọc, nên **kiểm tra schema trước khi xử lý hàng loạt**.

Quy trình gợi ý:

1. Mở file đáng tin bằng `RecordingFile` và đọc `readEventTypes()`.
2. Tìm type bằng tên định danh ổn định như `"demo.QueryOperation"`, **không** bằng ID runtime.
3. Lấy `getFields()` hoặc `getField("rows")`, xác nhận tên/kiểu/annotations cần thiết.
4. Nếu field bắt buộc thiếu hoặc đổi type không tương thích, báo lỗi schema rõ ràng hoặc kích hoạt logic migration đã định nghĩa; **không nuốt lỗi bằng cách ép sang 0**.
5. Nếu field tùy chọn thiếu, cung cấp default có chủ ý; phân biệt **missing** với **present-but-null** khi nghiệp vụ cần.
6. Duyệt events và đọc typed getters chỉ sau bước kiểm tra. Tổng hợp một số chỉ số có ý nghĩa; không in toàn bộ payload chưa được kiểm soát.
7. Đóng file trong `try-with-resources`, bảo vệ đường dẫn output và thông tin trong báo cáo.

Pseudo-code minh họa (không độc lập):

```java
EventType schema = event.getEventType();
ValueDescriptor rows = schema.getField("rows");
if (rows == null) {
    throw new IllegalArgumentException("Missing rows field");
}
if (!"int".equals(rows.getTypeName())) {
    throw new IllegalArgumentException("Unexpected type: " +
            rows.getTypeName());
}
int count = event.getInt("rows");
```

Đừng tạo chuỗi dynamic path từ dữ liệu người dùng không được kiểm chứng rồi gọi `getValue(path)` vô tội vạ. Các field names/nested structures có thể không tồn tại và parser có thể phải làm nhiều thao tác phản chiếu nội bộ. Với file rất lớn, kiểm tra schema một lần cho mỗi type và tận dụng các accessor thích hợp thay vì lặp lại bước phân tích metadata nặng cho từng event.

### Metadata của JFR không phải cơ chế bảo mật

Annotations như `@Label`, `@Category`, `@Description`, `@Timespan`, `@DataAmount` mô tả hiển thị/ngữ nghĩa. Chúng **không redaction**, **không mã hóa**, **không quyết định được phép truy cập**. Tên class, thread, paths, query IDs, user identifiers hay trường custom có thể nhạy cảm khi gộp nhiều events.

Lưu file `.jfr` tại vị trí có quyền đọc giới hạn, áp dụng retention, tránh đưa access token/PII vào event fields từ đầu. Khi tool phân tích được chia sẻ, chỉ xuất những trường thật sự cần cho điều tra.

## 10. Dùng CLI để kiểm tra nhanh metadata và values

Bên cạnh Java API, CLI của JDK có:

```bash
jfr summary sample.jfr
jfr metadata sample.jfr
jfr print --events demo.QueryOperation sample.jfr
```

Đây là **các lệnh minh họa** trên một file `sample.jfr` đã được tạo và giữ lại ở thư mục hiện tại (hoặc dùng đường dẫn đầy đủ). Trong bài runnable ở mục 7, file được xóa ở `finally`; nếu muốn dùng CLI sau khi chạy, hãy sửa chương trình để giữ file và đưa đường dẫn vào nơi do bạn kiểm soát.

- `jfr summary`: xem event types, counts và thông tin khái quát; không phải bảng raw field values cho từng instance.
- `jfr metadata`: xem mô tả type/fields/annotations để tìm schema đúng.
- `jfr print --events ...`: lọc các event instances theo type và in dữ liệu/metadata liên quan.

Output text có thể khác giữa các bản JDK hoặc tùy event fields; không nên dùng string match nguyên toàn bộ output CLI làm kiểm thử bền vững. Với tự động hóa, ưu tiên Java API typed getters và kiểm tra schema như trong demo.

**Khác biệt về version:** Java 11 có `RecordingFile` cho file hoàn tất. JDK mới hơn còn có những API xử lý stream thời gian thực trong JFR consumer (như `RecordingStream` từ các phiên bản sau Java 11); đó là **bài toán khác**. Nếu source phải biên dịch bằng `--release 11`, hãy dùng đúng API hiện diện trong Java 11, không chép nhầm method/class chỉ có ở JDK mới.

## 11. Những lỗi thường gặp

| Lỗi/hiểu lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ `readEventTypes()` trả các event instances | Nhầm metadata với data | `readEventTypes()` cho `EventType`; `readEvent()` cho `RecordedEvent` |
| Đọc field mà không lọc đúng event type | Typed getter lỗi khi type khác không có field | Lọc `event.getEventType().getName()` trước |
| Nghĩ `EventType.getField("x") == null` và `getValue("x") == null` là tương đương | Trộn missing với present-but-null | Kiểm tra schema bằng `getField/hasField` rồi xét value |
| Dùng label `"Row Count"` thay field name `"rows"` | Field không tồn tại trong lookup | Dùng tên Java field trong schema |
| Dùng `getString("rows")` vì muốn in số | Sai type; getter có thể ném `IllegalArgumentException` | Dùng `getInt("rows")` rồi format khi hiển thị |
| Ép giá trị Class/Thread sang live `Class`/`Thread` | `ClassCastException` hoặc logic sai | Dùng `RecordedClass`/`RecordedThread` |
| Nghĩ `getDuration("backendMillis")` là duration chuẩn của event | Gộp sai hai đại lượng | Dùng `getDuration()` cho event, overload có name cho timespan field |
| Bỏ qua `@Timespan`/`@DataAmount` | Diễn giải số đo sai đơn vị | Đọc `ValueDescriptor` annotations |
| Nghĩ `getFields()` chứa đúng các field custom và đúng thứ tự khai báo | Có thể có standard fields; order không phải khóa semantic | Tra theo tên, kiểm tra type |
| Coi event type ID là ID cố định xuyên process | ID là metadata runtime/file context | Dùng tên type có namespace và schema/version |
| In nguyên `event.toString()` cho mọi events | Lộ dữ liệu nhạy cảm, log/chi phí lớn | Lọc loại event và field cần thiết |
| Dùng `readAllEvents(path)` cho recording rất lớn | Dễ tốn RAM | Duyệt tuần tự bằng `RecordingFile` |
| Không xử lý `null` ở thread/stack trace | `NullPointerException` | Kiểm tra null trước khi truy cập |
| Dùng đường dẫn nested khi object giữa null | Có thể gây `NullPointerException` | Đọc từng cấp và kiểm tra |
| Lấy metadata từ class hiện tại để đoán schema của file cũ | File có thể ghi từ JDK hoặc app khác | Lấy schema từ `RecordingFile.readEventTypes()` |
| Nghĩ type có mặt trong metadata nghĩa file chứa instances của type | Có thể có type nhưng không có event cùng type | Đếm instances sau khi filter |
| Đọc repository như tệp `.jfr` | Không phải path file recording hoàn tất | Dump file hợp lệ rồi đọc |
| Coi JFR là audit log không mất dữ liệu | Sampling, thresholds, buffers, retention có thể lọc/làm mất | Dùng durable log cho yêu cầu không mất dữ liệu |

## 12. Câu hỏi tự kiểm tra

**Câu 1:** `RecordingFile.readEventTypes()` và `RecordingFile.readEvent()` trả cùng kiểu không?

**Đáp án:** Không. `readEventTypes()` trả danh sách `EventType` (metadata/schema); `readEvent()` trả một `RecordedEvent` (instance có giá trị fields).

**Câu 2:** Khi biết field có `@Label("Row Count") int rows;`, gọi getter bằng `"Row Count"` hay `"rows"`?

**Đáp án:** `"rows"`. Label chỉ để hiển thị, không thay tên field trong schema.

**Câu 3:** Nếu `hasField("optionalNote")==true` nhưng `getValue("optionalNote")==null`, có nghĩa field đã bị xóa?

**Đáp án:** Không. Field vẫn tồn tại trong schema; giá trị instance hiện tại là `null`.

**Câu 4:** `RecordedEvent.getDuration()` và `getDuration("backendMillis")` khác nhau thế nào?

**Đáp án:** Phương thức không tham số trả duration chuẩn của event; overload có tham số là một field `@Timespan` được JFR quy đổi theo đơn vị của field đó.

**Câu 5:** `getClass("owner")` trả `java.lang.Class<?>` không?

**Đáp án:** Không. Nó trả `RecordedClass`, một đối tượng metadata phục vụ đọc file JFR.

**Câu 6:** Một file chứa metadata event type `demo.QueryOperation` có chắc chứa ít nhất một event instance cùng type không?

**Đáp án:** Không. Phải duyệt và đếm `RecordedEvent` cùng type để xác nhận có dữ liệu.

**Câu 7:** Khi nâng cấp JDK, parser kiểm tra field bằng tên và type có ích gì?

**Đáp án:** Nó phát hiện schema thay đổi/field thiếu trước khi typed getter ném lỗi hoặc code suy diễn số đo sai. Có thể áp dụng migration hoặc fallback có chủ đích.

**Câu 8:** Tại sao không assert file size và event type ID cố định trong integration test JFR?

**Đáp án:** Chúng phụ thuộc implementation, metadata, event load và JDK. Test bền hơn khi xác minh schema, field values, conversions và các điều kiện có ý nghĩa.

**Ghi nhớ:** Khi **đọc bản ghi JFR** trên Java 11+, dùng **`RecordingFile`** để lấy `EventType` và `RecordedEvent`; dùng **`EventType` + `ValueDescriptor`** để hiểu tên/type/label/annotations; dùng **`RecordedObject.hasField` và typed getters** để đọc giá trị an toàn. Tách missing field khỏi null value, tách event duration khỏi `@Timespan` field, và tách `RecordedClass/RecordedThread` khỏi object sống. Đọc file đáng tin, duyệt tuần tự với bản ghi lớn, quản lý dữ liệu nhạy cảm và không dùng JFR thay durable audit.

**Tài liệu chính thức:** [Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html); [Java SE 11 — RecordedEvent](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html); [Java SE 11 — RecordedObject](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html); [Java SE 11 — EventType](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventType.html); [Java SE 11 — ValueDescriptor](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/ValueDescriptor.html); [Java SE 11 — RecordedThread](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedThread.html); [Java SE 11 — RecordedClass](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedClass.html); [Java SE 25 — RecordedObject](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html).
