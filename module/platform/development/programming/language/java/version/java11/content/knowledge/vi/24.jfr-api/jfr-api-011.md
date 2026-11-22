# EventFactory, ValueDescriptor và sự kiện động trong JFR API (Java 11)

## 1. Mục tiêu và bối cảnh

**Java Flight Recorder (JFR)** là cơ chế thu thập sự kiện chẩn đoán nằm trong JDK. Một event có thể mô tả lúc bắt đầu, thời lượng, thread thực thi và các dữ liệu nghiệp vụ giúp phân tích hiệu năng, lỗi hoặc hành vi ứng dụng. **JFR API** nằm trong module **`jdk.jfr`**; phía đọc dữ liệu có package **`jdk.jfr.consumer`**.

Có hai cách tạo event JFR:

- **Event tĩnh (statically defined):** viết một lớp `extends jdk.jfr.Event`, khai các fields tại thời điểm biên dịch. Đây là cách **nên ưu tiên khi biết schema trước**, vì JVM có cơ hội tối ưu mạnh hơn và công cụ dễ nhận diện metadata.
- **Event động (dynamically defined):** dùng **`EventFactory.create(...)`** để tạo một event type ngay **lúc runtime**, mô tả fields bằng **`ValueDescriptor`**, metadata bằng **`AnnotationElement`** và điền giá trị qua **`Event.set(index, value)`**. Dùng khi schema thực sự chỉ biết sau khi chương trình chạy, ví dụ plugin, adapter có field set do cấu hình runtime, hoặc hệ thống quan sát nhiều loại công việc được nạp động.

Cả `EventFactory`, `ValueDescriptor` và `AnnotationElement` đã có từ Java 9 và vẫn được hỗ trợ trên **Java 11 lẫn JDK hiện hành**. Nội dung này dùng API công khai, không dựa vào `jdk.internal.*` hay cách dùng thư viện JFR độc quyền lỗi thời. Mọi ví dụ chạy đầy đủ sử dụng **Java 11-compatible source**.

Sau bài này, bạn có thể:

1. Giải thích cách tạo event động và lý do không nên dùng nó khi schema đã cố định.
2. Dùng `ValueDescriptor(Class<?> type, String name, List<AnnotationElement>)` để khai type, tên và metadata của trường.
3. Dùng `AnnotationElement` mô phỏng các annotation `@Name`, `@Label`, `@Description`, `@Category`, `@Timespan`, `@Registered` mà không cần khai báo một lớp Event mới trong source.
4. Hiểu **thứ tự ValueDescriptor quyết định chỉ số `Event.set(index,Object)`**, không được tự suy ra từ `EventType.getFields()`.
5. Tạo event bằng `EventFactory.newEvent()`, gọi `begin/end`, kiểm `isEnabled/shouldCommit`, rồi `commit`.
6. Cấu hình `Recording.enable(name).withThreshold(Duration.ZERO)` để event được ghi; `stop`, `dump` và đọc lại bằng `RecordingFile`, `RecordedEvent`.
7. Hiểu đăng ký mặc định và vòng đời thủ công `@Registered(false)`, `register()`, `unregister()`.
8. Nhận diện các kiểu field được JFR hỗ trợ, tránh đưa trực tiếp `Map`, `List`, `UUID` hay JSON object vào ValueDescriptor.
9. Thực hiện bài kiểm thử Java 11 độc lập, gồm Unicode tiếng Việt, metadata, loại số, lỗi index/identifier, file JFR thật và đăng ký thủ công.
10. Áp dụng các khuyến nghị hiện hành về **overhead, schema stability, event cardinality, không thu thập secret/PII, memory bounds và resource cleanup**.

## 2. Khi nào dùng EventFactory thay vì lớp Event?

### 2.1. Lớp sự kiện tĩnh

Khi schema đã biết, thường khai trực tiếp:

~~~java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("demo.orders.WorkFinished")
@Label("Work Finished")
class WorkFinishedEvent extends Event {
    @Label("Message")
    String message;

    @Label("Count")
    int count;
}
~~~

Đây là **lớp minh họa**, chưa có `main`. Ứng dụng có thể tạo `new WorkFinishedEvent()`, gán `message`/`count` và gọi `commit()`. JVM có thể tối ưu instrument event loại này, thậm chí loại bỏ hoạt động nếu không có recording phù hợp.

### 2.2. Event động

Nếu chỉ khi tải plugin hoặc cấu hình runtime mới biết các trường, ta mô tả chúng bằng dữ liệu:

~~~java
List<ValueDescriptor> fields = Arrays.asList(
    new ValueDescriptor(String.class, "message"),
    new ValueDescriptor(int.class, "count")
);

List<AnnotationElement> annotations = Arrays.asList(
    new AnnotationElement(Name.class, "demo.orders.DynamicWork"),
    new AnnotationElement(Label.class, "Dynamic Work")
);

EventFactory factory = EventFactory.create(annotations, fields);
Event event = factory.newEvent();
event.set(0, "Xin chào");
event.set(1, 3);
event.commit();
~~~

Đây là **đoạn minh họa**, giả định đã import `java.util` và các lớp `jdk.jfr`. Để event thực sự có mặt trong file, cần **ít nhất một Recording đang chạy và đã bật đúng event type** (hoặc cấu hình JFR phù hợp). Một lời gọi `commit()` khi event không được enabled không tự tạo file JFR hoặc bảo đảm dữ liệu được lưu.

**Quan trọng:** nếu layout đã biết từ lúc compile, Oracle khuyến nghị **event tĩnh**. EventFactory sinh type ở runtime, có chi phí và khả năng tối ưu thấp hơn; công cụ downstream có thể khó hiểu schema mới nếu chưa có metadata hoặc chưa được cấu hình để nhận event type mới.

### 2.3. Sơ đồ vòng đời

~~~text
Runtime schema (field names/types/annotations)
           |
           v
EventFactory.create(eventAnnotations, fields)
           |
           +--> event class/type created and usually registered
           |          |
           |          +--> EventFactory.getEventType() -> metadata
           |
           v
Recording.enable(eventName).withThreshold(...)
Recording.start()
           |
           v
EventFactory.newEvent()
           |
           +--> Event.begin() / Event.end() for duration
           +--> Event.set(0, message)
           +--> Event.set(1, count)
           +--> Event.shouldCommit()
           +--> Event.commit()
           |
           v
Recording.stop() -> Recording.dump(path)
           |
           v
RecordingFile / RecordedEvent consumer
           |
           v
Recording.close() + EventFactory.unregister() when no longer needed
~~~

Đây là đường đi điển hình; thực tế có thể chạy nhiều recordings đồng thời. **EventFactory tạo event type và event objects, không phải một recording**; `Recording` mới quyết định kích hoạt và lưu event.

## 3. ValueDescriptor: schema của trường runtime

### 3.1. Hai constructor

~~~java
ValueDescriptor plain =
        new ValueDescriptor(String.class, "message");

ValueDescriptor labeled = new ValueDescriptor(
        long.class,
        "elapsedNanos",
        Arrays.asList(
                new AnnotationElement(Label.class, "Elapsed ns"),
                new AnnotationElement(Timespan.class, Timespan.NANOSECONDS))
);
~~~

Một `ValueDescriptor` ghi nhận:

- **`type`:** kiểu Java/JFR của field.
- **`name`:** định danh của field, phải là **Java identifier hợp lệ**.
- **`annotations`:** metadata tùy chọn như label, description, unit/timespan.

Constructor của `ValueDescriptor` có thể ném `IllegalArgumentException` nếu tên sai. Ví dụ `"elapsed-nanos"` hoặc `"not valid"` có dấu gạch ngang/khoảng trắng nên **không phải định danh Java hợp lệ**. Đặt `"elapsedNanos"`, còn chữ hiển thị thân thiện đưa vào `@Label` dưới dạng `AnnotationElement`.

Một lỗi thường gặp là hiểu tên field JFR như bất kỳ key JSON nào. **Field JFR có tên và type thuộc schema**, không phải map các keys tùy ý có thể thêm/bớt ở từng instance.

### 3.2. Các kiểu field được hỗ trợ

Theo `ValueDescriptor` Javadoc Java 11, khi **tạo event động**, những kiểu sau được hỗ trợ:

| Nhóm | `Class<?>` đưa cho ValueDescriptor | Ví dụ |
| --- | --- | --- |
| Số nguyên | `byte.class`, `short.class`, `int.class`, `long.class` | số lần retry, dung lượng, số bản ghi |
| Số thực | `float.class`, `double.class` | tỉ lệ, throughput, phép đo |
| Ký tự | `char.class` | trạng thái một ký tự (ít dùng) |
| Luận lý | `boolean.class` | success/failure |
| Văn bản | `String.class` | action, module, thông báo đã lọc |
| Kiểu Java | `Class.class` | lớp nguồn gây event |
| Thread | `Thread.class` | thread liên quan tới event |

**Không** dùng `List.class`, `Map.class`, `UUID.class`, `BigDecimal.class`, một domain POJO, enum hoặc array tùy ý làm event field động rồi mong JFR tự serialize nó như JSON. Có thể chuyển metadata thực sự cần thành một `String` hoặc các scalar fields xác định trước; nhưng không serialize toàn bộ object graph thiếu kiểm soát.

Với `Class`/`Thread`, **consumer** JFR có các representation chuyên biệt như `RecordedClass` và `RecordedThread`. Chúng không tương đương object Java sống đang được tham chiếu lúc record. Khi học cách đọc fields kiểu này, xem Javadoc consumer để dùng accessor phù hợp, không ép luôn về `String`.

### 3.3. Metadata và ý nghĩa đơn vị

Khai `ValueDescriptor(long.class,"elapsedNanos", ...)` khác với việc chỉ ghi một long rồi đặt tên tùy ý. Thêm:

~~~java
new AnnotationElement(Timespan.class, Timespan.NANOSECONDS)
~~~

để mô tả rằng con số đó có **đơn vị thời gian là nano giây**. Các công cụ JFR hiểu annotation kiểu `Timespan` có thể trình bày/chuyển đổi hợp lý hơn.

Một số annotation hữu ích khác:

| Metadata | Đối tượng | Tác dụng |
| --- | --- | --- |
| `Name` | Event type | Đặt định danh sự kiện ổn định, ví dụ `demo.app.WorkCompleted` |
| `Label` | Event hoặc field | Tên hiển thị dễ đọc |
| `Description` | Event hoặc field | Diễn giải ý nghĩa/nguồn gốc của event |
| `Category` | Event type | Nhóm event trong công cụ phân tích, ví dụ Demo → Operations |
| `Timespan` | Field có giá trị thời gian | Đơn vị duration |
| `Timestamp` | Field thời điểm | Diễn giải timestamp/đơn vị thích hợp |
| `Percentage` | Field tỷ lệ | Gợi ý hiển thị dạng phần trăm theo JFR |
| `Registered` | Event type | Chọn tự động đăng ký hay đăng ký thủ công |
| `StackTrace` | Event type | Cấu hình lấy stack trace mặc định |
| `Threshold` | Event type | Giá trị threshold mặc định của duration event |

**Chỉ chọn annotation có ý nghĩa thực:** không gắn `Timespan(NANOSECONDS)` lên một field số đếm hoặc `Percentage` lên byte-size. Annotation là metadata hỗ trợ consumer, **không biến giá trị sai thành đúng** hay thay thế xác nhận dữ liệu ở bên phát.

### 3.4. ValueDescriptor metadata có thể đọc lại

~~~java
EventType type = factory.getEventType();
ValueDescriptor descriptor = type.getField("elapsedNanos");

String fieldName = descriptor.getName();
String jfrType = descriptor.getTypeName();
String label = descriptor.getLabel();
List<AnnotationElement> metadata = descriptor.getAnnotationElements();
~~~

`EventType.getField(name)` trả `null` nếu không có field. `getFields()` trả danh sách descriptors của event type và **có thể chứa cả JFR implicit fields** như thời điểm, duration, event thread và stack trace; không nên dùng vị trí trong danh sách này để suy ra chỉ số `Event.set(index, value)`.

Nếu cần kiểm metadata có đầy đủ, dùng `getField("message")`, `getField("count")` theo **tên**. Với một ứng dụng có schema version, nên có test so field name/type/annotation ở lúc khởi động hoặc sau khi nạp plugin.

## 4. EventFactory.create: tạo event type và chú thích

### 4.1. Chữ ký và thứ tự đối số

~~~java
EventFactory create(
    List<AnnotationElement> annotationElements,
    List<ValueDescriptor> fields
)
~~~

Đây là cách viết dạng chữ ký đơn giản. Phương thức thực là **static `EventFactory.create(...)`**. Hai danh sách mang ý nghĩa khác nhau:

- `annotationElements`: metadata áp dụng lên **event type**.
- `fields`: descriptors của những **data fields do ứng dụng thêm**.

**Thứ tự của `fields` là hợp đồng của `Event.set(int,Object)`.** Ví dụ:

~~~text
fields[0] = ValueDescriptor(String, "requestId")
fields[1] = ValueDescriptor(int, "attempt")
fields[2] = ValueDescriptor(boolean, "success")

event.set(0, "REQ-123")      // requestId
event.set(1, 2)              // attempt
event.set(2, true)           // success
~~~

Nếu đổi danh sách fields mà không sửa code ghi giá trị, bạn có thể gán sai kiểu/sai nghĩa. Việc `EventType.getFields()` có nhiều field metadata được JFR bổ sung **không làm offset của các field ứng dụng tăng lên**. Chỉ số gửi vào `set` tính từ chính danh sách `ValueDescriptor` lúc tạo factory.

### 4.2. AnnotationElement tạo runtime metadata

~~~java
List<AnnotationElement> metadata = Arrays.asList(
    new AnnotationElement(Name.class, "demo.app.WorkCompleted"),
    new AnnotationElement(Label.class, "Work Completed"),
    new AnnotationElement(Description.class,
            "Observes the result of one work item"),
    new AnnotationElement(Category.class,
            new String[]{"Application", "Work"})
);
~~~

Đây là **đoạn minh họa**. `Name.class` đặt event name theo định danh ổn định; `Label.class` cho tiêu đề người đọc; `Category.class` chứa các nhóm. `new AnnotationElement(Category.class, new String[]{...})` là cú pháp được ví dụ chính thức của `EventFactory` sử dụng.

Phân biệt: annotation `Name` dùng chuỗi có dấu chấm như `"demo.app.WorkCompleted"` (tên event type), còn **ValueDescriptor field name** là một **Java identifier**, ví dụ `"requestId"`. Không dùng cùng một validation rule cho hai loại tên.

### 4.3. Schema động phải được quản trị

Việc tạo thêm một `EventFactory` có thể dẫn tới một event type mới và dữ liệu metadata mới. Đừng tạo **một factory mới cho mỗi request** hoặc đưa user ID, trace ID, timestamp ngẫu nhiên vào **event type name**. Một event type riêng cho mỗi request làm nổ **metadata cardinality**, gây tăng chi phí quản lý types, ảnh hưởng tools/dashboard.

Khuyến nghị:

1. Tạo factory **một lần cho mỗi schema** trong vòng đời plugin/module; cache/giữ nó khi thực sự cần.
2. Dùng **event name** ổn định có namespace, ví dụ `demo.app.WorkCompleted`; dùng fields để ghi `requestId` chứ không nhúng vào tên event type.
3. Nếu schema thay đổi không tương thích, version hóa schema có chủ đích và kiểm consumer trước khi rollout.
4. Giới hạn số field, kích cỡ String và tần suất commit; không đưa object graph hay raw payload lớn vào JFR.
5. Khi plugin bị unload hoặc schema không cần nữa, áp dụng `unregister()` và thả các references phù hợp; **unregister không xóa những sự kiện đã ghi trong recording file cũ**.

## 5. Event.set(index, value) và vòng đời event

### 5.1. newEvent tạo một event object mới

~~~java
Event event = factory.newEvent();
event.set(0, "sample");
event.set(1, 100);
event.commit();
~~~

Mỗi `newEvent()` tạo instance cho một sự kiện logic. **Không** chia sẻ cùng một event object mutable giữa nhiều thread cho nhiều lần ghi độc lập. Hãy tạo instance mới, điền fields, commit một lần trong luồng xử lý tương ứng.

Theo `Event.set` Javadoc:

- Có hiệu lực cho **event được định nghĩa động bằng EventFactory**.
- `index` bắt đầu từ 0 theo vị trí `ValueDescriptor` đưa vào `create`.
- Index nhỏ hơn 0 hoặc lớn hơn/equal số field gây **`IndexOutOfBoundsException`**.
- API tài liệu hóa **`UnsupportedOperationException`** nếu event không được tạo động. Tuy nhiên không dùng `set` trên static event làm đường làm việc hợp lệ; source event tĩnh nên gán trực tiếp field.
- `value` có thể là `null` theo chữ ký, nhưng ứng dụng vẫn phải tôn trọng field type, meaning và khả năng biểu diễn của JFR. Không coi null hợp lệ cho mọi kiểu primitive hoặc mọi ngữ cảnh.

Với field kiểu `int.class`, điền `Integer` thông qua autoboxing (`event.set(1, 100)`). Không truyền `String` `"100"` rồi mong JFR tự parse thành integer: đó là sai schema, có thể gây runtime error. Hãy validate/convert dữ liệu trước khi gọi `set`.

### 5.2. begin, end, commit

~~~java
Event event = factory.newEvent();
event.begin();

// Thực hiện công việc cần đo. Gán dữ liệu cho các field.
event.set(0, "completed");
event.set(1, 1);

event.end();
event.commit();
~~~

- `begin()` đánh dấu thời điểm bắt đầu.
- `end()` đánh dấu kết thúc; `end` phải theo sau `begin`.
- `commit()` ghi values, timestamp, duration vào Flight Recorder **nếu event đáp ứng điều kiện enabled/threshold**.
- Nếu đã `begin` mà không `end` rõ ràng, Javadoc nói `commit` sẽ kết thúc event lúc commit.
- Thời lượng event mặc định là một thuộc tính JFR. **Không** nhầm với field business duration `elapsedNanos` nếu bạn tự thêm. Hai con số có thể khác nhau: một cái đo thời gian bao quanh `begin/end`, cái còn lại có thể là số đo từ hệ thống khác.

### 5.3. isEnabled và shouldCommit

~~~java
Event event = factory.newEvent();
if (event.isEnabled()) {
    event.begin();
    // Làm việc nghiệp vụ
    event.end();
    if (event.shouldCommit()) {
        // Chỉ thu thập field đắt tiền khi event sẽ được ghi.
        event.set(0, "sample");
        event.commit();
    }
}
~~~

Đây là **đoạn minh họa**: công việc nghiệp vụ cần chạy **dù recording bật hay tắt**; không nên bọc toàn bộ business logic trong `if(isEnabled())`. Hãy dùng điều kiện này **chỉ để tránh chi phí tạo dữ liệu quan sát** (ví dụ format stack trace, serialize string dài, đọc thông tin hệ thống).

- `isEnabled()` báo có ít nhất một recording đang chạy và event type enabled.
- `shouldCommit()` xét enabled và **threshold theo duration**. Nó là tín hiệu có thể ghi event tại thời điểm kiểm, không cam kết retention vĩnh viễn hay event nhất định xuất hiện trong một file đã bị xóa.
- `commit()` phải được gọi để nộp event cho JFR; `shouldCommit() == true` một mình không ghi event.
- Không bắt event data vì `isEnabled()` đang false rồi tự gửi sang log như một fallback bí mật; dùng logging/metrics theo chính sách riêng.

## 6. Recording, RecordingFile và consumer

### 6.1. Cấu hình kích hoạt event động

Khi event type đã đăng ký, có thể enable bằng tên:

~~~java
try (Recording recording = new Recording()) {
    recording.enable("demo.app.WorkCompleted")
             .withThreshold(Duration.ZERO);
    recording.start();

    // Tạo và commit dynamic events khi recording đang chạy.

    recording.stop();
    recording.dump(path);
}
~~~

Đây là **đoạn minh họa**, giả định `path` và imports đã có. Với một dynamic event, `Recording.enable(String name)` phù hợp vì class Event thực sự được JVM sinh ở runtime và không có một source class literal cố định để truyền `enable(MyEvent.class)`.

`withThreshold(Duration.ZERO)` giúp các event có duration rất ngắn vẫn qua ngưỡng do recording này cấu hình. Nếu threshold lớn, event quá ngắn có thể bị bỏ qua dù code gọi `commit()`. Không mặc định bật threshold bằng 0 trên **mọi event tần suất cao trong production**: điều đó có thể tạo overhead/khối lượng dữ liệu lớn; thiết kế threshold theo nhu cầu chẩn đoán.

### 6.2. Dump và đọc file

~~~java
recording.stop();
recording.dump(path);

for (RecordedEvent item : RecordingFile.readAllEvents(path)) {
    if ("demo.app.WorkCompleted".equals(
            item.getEventType().getName())) {
        String message = item.getString("message");
        int count = item.getInt("count");
        // Xử lý giá trị đã được JFR record.
    }
}
~~~

`RecordingFile.readAllEvents(path)` tiện cho **recording nhỏ/ứng dụng test**. Nó đọc tất cả events vào một `List`, nên không phải lựa chọn mặc định cho file hàng GB. Với file lớn, dùng:

~~~java
try (RecordingFile reader = new RecordingFile(path)) {
    while (reader.hasMoreEvents()) {
        RecordedEvent item = reader.readEvent();
        // Lọc, xử lý theo luồng, giới hạn bộ nhớ.
    }
}
~~~

Đây cũng là đoạn minh họa. Javadoc `RecordingFile` nhắc chỉ đọc **recording files từ nguồn tin cậy**; không tải một file `.jfr` chưa tin cậy từ Internet rồi tùy tiện parse trong JVM production có quyền rộng.

**JFR event file là dữ liệu quan sát**, có thể có stack traces, tên thread, class và field values. Nó không tự thực hiện redaction/anonymization; người viết event phải kiểm trường nào có thể đưa vào file, retention, quyền đọc và chính sách chia sẻ.

### 6.3. RecordedEvent và EventType là hai cấp khác nhau

- `EventFactory.getEventType()` trả **metadata của event type**: định danh, label, category, descriptors, settings.
- `RecordingFile.readAllEvents` trả **recorded event instances**: timestamp, duration, thread, các giá trị được ghi lúc commit.
- `RecordedEvent.getEventType()` cho phép nối một recorded instance với metadata của type đã được ghi vào recording file.
- `RecordedEvent.getString/getInt/getLong/getBoolean` đọc giá trị theo **field name**, không theo chỉ số `Event.set`.

Không dùng `EventType.getFields().get(0)` để suy ra `Event.set(0,...)` nếu có implicit JFR fields. Khi dùng consumer, tên field là lựa chọn rõ ràng và dễ bảo trì.

## 7. Chương trình Java 11 độc lập: tạo, ghi và đọc event động

### 7.1. Kịch bản kiểm thử

Chương trình **JfrDynamicEventDemo.java** không cần thư viện ngoài. Nó chạy một recording thật và kiểm tra:

| Nhóm | Kiểm tra | Kỳ vọng |
| --- | --- | --- |
| Metadata | `@Name`, `@Label`, `@Category`, field labels/type, `@Timespan` | Factory tạo đúng metadata |
| Validation | `ValueDescriptor` tên field sai; `Event.set` index vượt biên | Từ chối bằng exception tương ứng |
| Recording | `Recording.enable(name)`, `start`, `begin/end`, `shouldCommit`, `commit` | Event đủ điều kiện được ghi |
| Unicode + data | Tiếng Việt/emoji, int, long, boolean | Đọc lại đúng qua `RecordedEvent` |
| File JFR | `stop`, `dump`, `RecordingFile.readAllEvents` | Tìm đúng một event của type đã khai |
| Registration | `@Registered(false)`, `register`, `getEventType`, `unregister` | Metadata chỉ có khi được đăng ký |

Ứng dụng tạo file `.jfr` tạm bằng `Files.createTempFile(...)`, ghi, đọc, assert và **xóa file trong finally**. Vì vậy sau khi demo kết thúc không còn file để đưa cho lệnh `jfr print`; nếu muốn mở bằng JDK Mission Control hoặc CLI, sửa demo để giữ file tại một đường dẫn đã chọn.

### 7.2. File JfrDynamicEventDemo.java

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import jdk.jfr.AnnotationElement;
import jdk.jfr.Category;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.EventFactory;
import jdk.jfr.EventType;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.Registered;
import jdk.jfr.Timespan;
import jdk.jfr.ValueDescriptor;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrDynamicEventDemo {
    private static final String EVENT_NAME = "demo.dynamic.WorkCompleted";
    private static final String MESSAGE =
            "Ti\u1ebfng Vi\u1ec7t " + new String(Character.toChars(0x1F642));

    private static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    private static EventFactory createFactory() {
        List<AnnotationElement> eventMetadata = Arrays.asList(
                new AnnotationElement(Name.class, EVENT_NAME),
                new AnnotationElement(Label.class, "Work Completed"),
                new AnnotationElement(Description.class,
                        "Result of one application work item"),
                new AnnotationElement(Category.class,
                        new String[]{"Demo", "Dynamic Events"}));
        List<ValueDescriptor> fields = Arrays.asList(
                new ValueDescriptor(String.class, "message",
                        Arrays.asList(
                                new AnnotationElement(Label.class,
                                        "Message"),
                                new AnnotationElement(Description.class,
                                        "Human readable result"))),
                new ValueDescriptor(int.class, "count",
                        Arrays.asList(new AnnotationElement(Label.class,
                                "Count"))),
                new ValueDescriptor(long.class, "elapsedNanos",
                        Arrays.asList(
                                new AnnotationElement(Label.class,
                                        "Elapsed ns"),
                                new AnnotationElement(Timespan.class,
                                        Timespan.NANOSECONDS))),
                new ValueDescriptor(boolean.class, "success"));
        return EventFactory.create(eventMetadata, fields);
    }

    private static void invalidSetIndex(EventFactory factory) {
        Event event = factory.newEvent();
        boolean caught = false;
        try {
            event.set(4, "out of bounds");
        } catch (IndexOutOfBoundsException expected) {
            caught = true;
        }
        check(caught, "invalid dynamic field index rejected");
    }

    private static void invalidDescriptor() {
        boolean caught = false;
        try {
            new ValueDescriptor(String.class, "not valid");
        } catch (IllegalArgumentException expected) {
            caught = true;
        }
        check(caught, "invalid Java identifier rejected");
    }

    private static void registrationLifecycle() {
        EventFactory manual = EventFactory.create(
                Arrays.asList(
                        new AnnotationElement(Name.class,
                                "demo.dynamic.ManualEvent"),
                        new AnnotationElement(Registered.class, false)),
                Arrays.asList(new ValueDescriptor(String.class, "message")));
        boolean notRegistered = false;
        try {
            manual.getEventType();
        } catch (IllegalStateException expected) {
            notRegistered = true;
        }
        check(notRegistered,
                "Registered(false) does not auto-register");
        manual.register();
        check("demo.dynamic.ManualEvent".equals(
                manual.getEventType().getName()),
                "register exposes metadata");
        manual.unregister();
        boolean unregistered = false;
        try {
            manual.getEventType();
        } catch (IllegalStateException expected) {
            unregistered = true;
        }
        check(unregistered,
                "unregister removes runtime event registration");
        System.out.println("PASS explicit registration lifecycle");
    }

    public static void main(String[] args) throws Exception {
        EventFactory factory = createFactory();
        EventType type = factory.getEventType();
        check(EVENT_NAME.equals(type.getName()), "event name");
        check("Work Completed".equals(type.getLabel()), "event label");
        check(Arrays.asList("Demo", "Dynamic Events")
                .equals(type.getCategoryNames()), "event category");
        check("message".equals(type.getField("message").getName())
                && "Message".equals(
                        type.getField("message").getLabel()),
                "field annotation metadata");
        check("long".equals(
                type.getField("elapsedNanos").getTypeName()),
                "field primitive type metadata");
        check("jdk.jfr.Timespan".equals(
                type.getField("elapsedNanos")
                        .getAnnotationElements().stream()
                        .filter(a -> a.getTypeName()
                                .equals("jdk.jfr.Timespan"))
                        .findFirst().orElseThrow()
                        .getTypeName()), "timespan annotation");
        System.out.println("PASS event and field metadata");

        invalidDescriptor();
        invalidSetIndex(factory);
        System.out.println("PASS descriptor and set validation");

        Path file = Files.createTempFile("jfr-dynamic-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(EVENT_NAME)
                        .withThreshold(Duration.ZERO);
                recording.start();

                Event event = factory.newEvent();
                check(event.isEnabled(), "event enabled by recording");
                event.begin();
                event.set(0, MESSAGE);
                event.set(1, 7);
                event.set(2, 456_000L);
                event.set(3, true);
                event.end();
                check(event.shouldCommit(), "event eligible to commit");
                event.commit();
                System.out.println("PASS JFR enabled timing and commit");

                recording.stop();
                recording.dump(file);
            }
            List<RecordedEvent> matches = new ArrayList<>();
            for (RecordedEvent event :
                    RecordingFile.readAllEvents(file)) {
                if (EVENT_NAME.equals(event.getEventType().getName())) {
                    matches.add(event);
                }
            }
            check(matches.size() == 1, "exactly one event recorded");
            RecordedEvent saved = matches.get(0);
            check(MESSAGE.equals(saved.getString("message")),
                    "Unicode message preserved");
            check(saved.getInt("count") == 7, "int field preserved");
            check(saved.getLong("elapsedNanos") == 456_000L,
                    "long field preserved");
            check(saved.getBoolean("success"), "boolean field preserved");
            check(!saved.getDuration().isNegative(),
                    "measured duration is not negative");
            System.out.println("PASS recorded Unicode and numeric values");
            System.out.println("PASS recording dump and JFR consumer");
        } finally {
            Files.deleteIfExists(file);
        }
        registrationLifecycle();
        factory.unregister();
        System.out.println("ALL JFR DYNAMIC EVENT TESTS PASSED");
    }
}
~~~

### 7.3. Biên dịch và chạy

Sử dụng JDK 11+ có module `jdk.jfr`. Tại thư mục chứa file:

~~~bash
javac --release 11 --add-modules jdk.jfr -encoding UTF-8 JfrDynamicEventDemo.java
java --add-modules jdk.jfr JfrDynamicEventDemo
~~~

`--add-modules jdk.jfr` làm rõ module cần sử dụng. Trên nhiều JDK đầy đủ, module này đã được nhận diện tự động khi compile/run code trực tiếp từ classpath, nhưng khai tường minh giúp ví dụ rõ dependency. Custom runtime image xây bằng `jlink` phải bao gồm module `jdk.jfr` nếu ứng dụng cần JFR.

Chương trình **không gọi `Thread.sleep(...)` để hy vọng event được ghi**; nó gọi `Recording.stop()` rồi `dump(...)` trước khi đọc file. JFR vẫn có các thread/buffers nội bộ, nhưng việc stop/dump tạo ranh giới xác định cho bài test.

**Stdout dự kiến khi toàn bộ assertions thành công:**

~~~text
PASS event and field metadata
PASS descriptor and set validation
PASS JFR enabled timing and commit
PASS recorded Unicode and numeric values
PASS recording dump and JFR consumer
PASS explicit registration lifecycle
ALL JFR DYNAMIC EVENT TESTS PASSED
~~~

Khi có lỗi, `check(...)` ném `AssertionError` để test luôn hoạt động mà không cần `-ea`. Chương trình chỉ in các dòng PASS phía trên, không in toàn bộ event hay stack trace ở đường thành công, để output ổn định và dễ so.

### 7.4. Tại sao ví dụ kiểm các chi tiết đó?

**Metadata:** `EventFactory.getEventType()` trả event type. Test kiểm tên `demo.dynamic.WorkCompleted`, label, category và `ValueDescriptor.getLabel/getTypeName`, gồm `Timespan` annotation của field thời lượng.

**Validation:** một field name chứa khoảng trắng không phải Java identifier, nên `ValueDescriptor` constructor từ chối. Với bốn fields có chỉ số **0..3**, gọi `event.set(4, ...)` gây `IndexOutOfBoundsException`.

**Recording:** chỉ khi event type được enable và recording đã `start`, `event.isEnabled()` mới cho kết quả phù hợp. `begin/end` đo thời lượng của event; `shouldCommit()` xác nhận event thỏa threshold đã cấu hình trước `commit()`.

**Unicode:** `MESSAGE` được tạo từ các Unicode escapes của chữ tiếng Việt và một code point bổ sung U+1F642. `RecordedEvent.getString("message")` trả đúng nội dung sau khi dump/parse. Trường `int`, `long`, `boolean` được đọc qua accessor đúng kiểu.

**File:** mã lọc event theo **tên event type**, không giả định file chỉ có một sự kiện; JFR có thể ghi một số event nội bộ khác trong cùng recording. Test chỉ đếm những event có name chính xác.

**Lifecycle:** factory `ManualEvent` mang `Registered(false)`, nên `getEventType()` ban đầu ném `IllegalStateException`. Sau `register()` có metadata, sau `unregister()` không thể tiếp tục lấy metadata như một registered type.

**Cleanup:** `Recording` nằm trong try-with-resources, file tạm được xóa ở `finally`, factory được unregister khi kết thúc. Chương trình không cần kết nối Internet, không upload JFR file và không lưu dữ liệu test dài hạn.

## 8. Đăng ký EventFactory và Registered(false)

### 8.1. Hành vi mặc định

`EventFactory.create(...)` **thường tự đăng ký** event type ngay khi tạo. Điều này giúp `EventFactory.getEventType()` hoạt động và các recordings có thể enable nó theo name.

Muốn trì hoãn đăng ký, thêm annotation động:

~~~java
List<AnnotationElement> metadata = Arrays.asList(
        new AnnotationElement(Name.class, "demo.app.ManualEvent"),
        new AnnotationElement(Registered.class, false)
);

EventFactory factory = EventFactory.create(
        metadata,
        Arrays.asList(new ValueDescriptor(String.class, "message")));
~~~

Trước khi register, `factory.getEventType()` ném **`IllegalStateException`**. Khi sẵn sàng:

~~~java
factory.register();
EventType type = factory.getEventType();
// Sử dụng factory; cuối vòng đời:
factory.unregister();
~~~

`register()` khi đã registered và `unregister()` khi chưa registered có thể được coi là thao tác bỏ qua theo Javadoc, không cần tự viết nhiều tầng điều kiện. Không tự tạo nhiều factories trùng tên event để «cập nhật schema in-place» mà không quản lý vòng đời; event type ID và metadata của JFR thuộc runtime JVM cụ thể.

### 8.2. Unregister không có nghĩa xóa dữ liệu đã ghi

`EventFactory.unregister()` khiến type không còn đăng ký để **ghi những event mới** và metadata không xuất hiện như một registered event type khi truy vấn live FlightRecorder. Nó **không phải công cụ redaction file JFR** và không xóa records đã được ghi vào recording trước đó.

Đặc biệt khi plugin/module unload, hãy dừng producer phát event, xử lý những event objects còn sống theo chính sách, rồi unregister. Nếu muốn xóa file chẩn đoán do application tạo, đó là một **quy trình file retention/quyền truy cập riêng**, không phải trách nhiệm của `unregister`.

### 8.3. Event name và EventType ID

- **`EventType.getName()`** là định danh có thể dùng ở cấu hình recording và consumer.
- **`EventType.getId()`** là ID duy nhất trong phạm vi **một JVM instance**, không là định danh bền vững qua restarts/hosts.
- Nhiều class loaders có thể tạo event types có cùng name; khi cần phân biệt, cấu hình của JFR có thể dùng event ID. Tránh chọn tên không đủ namespace và tránh hard-code ID qua nhiều lần chạy.
- Trong biểu đồ/dashboard lâu dài, dùng name có versioning rõ khi schema thay đổi, đồng thời chú ý metadata/type ID.

## 9. Thu thập dữ liệu hiệu quả và an toàn

### 9.1. Không tính thông tin đắt tiền khi event không được ghi

Một event có thể xuất hiện trong hot path hàng chục nghìn lần mỗi giây. Mặc dù JFR được thiết kế với overhead thấp, **tạo String quá lớn, serialize JSON, đọc stack trace hoặc gọi database để bổ sung metadata** vẫn có chi phí của ứng dụng ngay cả khi JFR event bị disable.

Mẫu ý tưởng:

~~~java
Event event = factory.newEvent();
if (event.isEnabled()) {
    event.begin();
    // Bắt đầu đo nếu việc đo là cần thiết.
    event.end();
    if (event.shouldCommit()) {
        event.set(0, formatSmallSafeMessage());
        event.commit();
    }
}
~~~

Đây là **mã minh họa**; method `formatSmallSafeMessage()` do ứng dụng cung cấp và không có trong demo runnable. Trong code thực, công việc nghiệp vụ phải chạy độc lập với nhánh quan sát JFR; đừng dùng `if(isEnabled)` để bỏ qua business processing.

`shouldCommit` đặc biệt hữu ích sau `begin/end` với event có threshold, vì bạn có thể đợi biết thời lượng mới quyết định có nên tạo field metadata đắt tiền.

### 9.2. Giới hạn kích thước, tần suất và số type

Các risk cần kiểm soát:

- **Cardinality:** không tạo một type mới cho từng user/request/trace ID. Type count lớn ảnh hưởng metadata, bộ nhớ và khả năng phân tích.
- **Event rate:** không commit mọi thao tác cực nhỏ nếu không cần, chọn threshold/sampling hợp lý.
- **String size:** không ghi body HTTP, SQL params, stack trace format dài hoặc serialized object lớn cho mọi event.
- **Số fields:** càng nhiều trường càng tăng chi phí ghi/đọc/schema governance. Chỉ thu thập dữ liệu cần thiết.
- **Lưu trữ:** `Recording` có ``setMaxSize`/`setMaxAge``, tùy policy; không mặc định ghi vô hạn trong production.
- **Consumer:** với file lớn dùng `RecordingFile` streaming, không dùng `readAllEvents` để nạp hết vào RAM.
- **Lifecycle:** unregister những dynamic types không còn dùng và close recordings/reader; tránh giữ references tới factory/class loader của plugin đã unload.

### 9.3. Quyền riêng tư và bảo mật

Một field `message` có thể dễ dàng chứa token, địa chỉ email, identifier nhạy cảm hoặc raw HTTP payload nếu người lập trình không lọc. JFR files và tools có thể tồn tại lâu, được sao chép cho hỗ trợ, tải xuống từ production hoặc chia sẻ giữa các nhóm.

Nên:

1. Tạo **schema allowlist** với các scalar fields cần cho chẩn đoán.
2. Không ghi password, access token, session cookie, private key, authorization header hay raw request body.
3. Giới hạn độ dài thông điệp, loại bỏ control chars nếu đưa vào báo cáo/log, áp dụng masking/redaction phù hợp.
4. Kiểm quyền truy cập JFR files, retention, dữ liệu chuyển giao và đường dẫn export.
5. Tránh tạo event type names từ dữ liệu user-controlled; dùng category/name ổn định và validate tên/field schema.
6. Không tự động đọc file JFR do người lạ tải lên bằng process production có quyền rộng; Javadoc `RecordingFile` yêu cầu tin cậy nguồn file.

**JFR là công cụ quan sát chứ không phải cơ chế xác thực, phân quyền hay bảo vệ dữ liệu**. Metadata labels/descriptions cũng không làm dữ liệu nhạy cảm trở nên an toàn.

## 10. Lỗi thường gặp và cách chẩn đoán

| Vấn đề | Nguyên nhân phổ biến | Cách giải quyết |
| --- | --- | --- |
| `EventFactory.create` ném `IllegalArgumentException` | Field name không hợp lệ, type không được hỗ trợ, annotation không hợp lệ/không resolve được | Validate schema trước khi create, dùng loại scalar được hỗ trợ |
| `ValueDescriptor(String.class,"not valid")` thất bại | Tên field chứa khoảng trắng | Dùng Java identifier `notValid`, Label riêng |
| `event.set(4, ...)` lỗi khi chỉ có 4 descriptors | Index hợp lệ là `0..3` | Ghi constant mapping của schema, kiểm field count |
| Fields bị tráo dữ liệu | `set(index)` không theo đúng thứ tự tạo factory | Ánh xạ index ↔ original ValueDescriptor list, không dựa EventType.getFields order |
| `Event.set` trên static Event | API chỉ dành cho dynamic event | Gán field trực tiếp đối với event tĩnh |
| Truyền `"10"` cho field int | Nhầm schema JFR với JSON coercion | Parse thành Integer/int trước, validate kiểu |
| `EventFactory.getEventType()` ném `IllegalStateException` | Factory tạo với `Registered(false)` và chưa register/đã unregister | Register trước khi truy vấn metadata |
| Không tìm thấy event trong file | Recording chưa start, event name sai, setting disabled, threshold loại event, chưa commit, stop/dump không đúng | Kiểm type registration, `Recording.enable`, `isEnabled/shouldCommit`, commit, dump |
| `isEnabled()` là false | Không có running recording enable type | Đảm bảo recording đã start và setting name đúng |
| `shouldCommit()` là false | Disabled hoặc duration chưa đạt threshold | Dùng threshold phù hợp; test dùng ZERO |
| `RecordedEvent.getString` với field int | Accessor sai kiểu | Dùng `getInt/getLong/getBoolean` theo descriptor |
| Không có field do JFR implicit metadata | Đọc nhầm tên hoặc nhầm index | Dùng `EventType.getField(name)` và consumer getter theo tên |
| Unicode sai | Code convert/encode text bên ngoài JFR không nhất quán | Giữ `String`, kiểm UTF-8 ở các boundary ngoài JFR, test code points |
| File JFR lớn gây OOM | `RecordingFile.readAllEvents` load tất cả | Dùng `RecordingFile.hasMoreEvents/readEvent` |
| Schema thay đổi làm dashboard không đọc được | Event type name ổn định nhưng field đổi nghĩa/type | Quản lý version/schema compatibility và test consumer |
| Quá nhiều types | Tạo EventFactory per request | Cache per schema, bounded types, unregister đúng lúc |
| CPU tăng | Commit quá nhiều, tạo metadata/strings đắt tiền | Enable/threshold/sampling, shouldCommit gate, đo overhead |
| File JFR chứa secret/PII | Đưa raw data vào event field | Allowlist/redaction, access control, retention |
| `NoClassDefFoundError: jdk/jfr/...` | Runtime image/JDK thiếu module `jdk.jfr` | Sử dụng JDK/runtime image có JFR, khai module dependency |
| `Recording` không tạo được | JFR không available/repository không dùng được | Kiểm runtime, quyền ghi repository/đĩa, exception thực |
| Consumer không parse JFR file | File không hợp lệ, bị cắt, không cùng định dạng được hỗ trợ hoặc nguồn không tin cậy | Chỉ dùng file tin cậy, kiểm source/runtime và version compatibility |

### 10.1. Một checklist debug ngắn

1. Kiểm **EventFactory đã tạo đúng metadata**: `getEventType().getName()`, `getField("...")`, label/category.
2. Kiểm **tên event enable** trong `Recording.enable(...)` khớp chính xác tên factory.
3. Kiểm `Recording.start` đã chạy trước khi tạo/commit event; nhìn `isEnabled`.
4. Nếu duration event không xuất hiện, kiểm threshold và `shouldCommit` sau `end`.
5. Kiểm `Event.set` đúng **original field indexes** và types.
6. Đảm bảo `commit` đã được gọi, `Recording.stop/dump` hoàn tất.
7. Lọc events theo `RecordedEvent.getEventType().getName()` và đọc bằng accessor đúng kiểu.
8. Nếu test chạy trên custom JDK image, xác minh `jdk.jfr` module tồn tại.
9. Với production, kiểm những vấn đề bảo mật/retention và hiệu năng thay vì tự tăng ghi log cho mọi request.

## 11. Câu hỏi tự đánh giá

**1. Khi nào nên dùng EventFactory?** — Khi schema của event **chỉ biết ở runtime**. Nếu layout biết từ compile time, ưu tiên một lớp `extends Event` được định nghĩa tĩnh.

**2. ValueDescriptor mô tả những gì?** — Java type, tên field hợp lệ và metadata của field (Label/Description/Timespan...).

**3. Index của `Event.set(0, ...)` lấy từ đâu?** — Vị trí của `ValueDescriptor` trong danh sách `fields` đưa vào `EventFactory.create`, không phải vị trí field đầu tiên trong `EventType.getFields()`.

**4. Có thể đưa `Map.class` vào ValueDescriptor để JFR tự ghi JSON không?** — Không phải kiểu field động được hỗ trợ theo Javadoc. Dùng các kiểu scalar hỗ trợ và định nghĩa schema rõ ràng.

**5. `Name` và `Label` có khác nhau không?** — Có. Name là **identifier ổn định** để cấu hình/filter; Label là chuỗi hiển thị thân thiện.

**6. `EventFactory.create` có tự động lưu sự kiện vào file không?** — Không. Factory tạo event type, còn `Recording` phải chạy và enable type; event instance phải commit.

**7. `isEnabled()` và `shouldCommit()` khác thế nào?** — `isEnabled` xét recording đang chạy và enabled; `shouldCommit` còn xét threshold duration của event.

**8. Event có `begin` nhưng không `end` rồi gọi `commit` có được không?** — Javadoc nói `commit` sẽ kết thúc event tại thời điểm commit. Tuy nhiên đo lường rõ ràng nên gọi `end` khi công việc kết thúc.

**9. Dùng annotation `Registered(false)` thì có thể gọi `getEventType()` ngay không?** — Chưa; nó ném `IllegalStateException` nếu event chưa register thủ công.

**10. `unregister()` có xóa event đã ghi trong một file `.jfr` cũ không?** — Không. Nó tác động tới đăng ký event type để ghi dữ liệu mới và truy vấn metadata live, không phải cơ chế xóa file.

**11. Vì sao `readAllEvents` không nên dùng bừa bãi cho file JFR rất lớn?** — Nó nạp một danh sách tất cả events, có thể tốn nhiều RAM. Dùng `RecordingFile` streaming.

**12. Nếu ứng dụng chạy bằng custom runtime image, điều gì cần lưu ý?** — Image phải chứa module `jdk.jfr`, và sản phẩm phải cho phép JFR/repository hoạt động theo runtime policy.

**13. Metadata event có thể bị thay đổi ngẫu nhiên theo từng request không?** — Không nên. Tạo nhiều type/fields không kiểm soát gây metadata cardinality và phá consumer schema compatibility.

**14. `RecordedEvent.getDuration()` có luôn bằng field `elapsedNanos` do app tự set không?** — Không. Một cái là duration JFR đo theo `begin/end`; cái kia là trường dữ liệu ứng dụng tự điền, có ngữ nghĩa tùy schema.

**15. JFR có tự che token/PII nếu một `String` field chứa dữ liệu đó không?** — Không. Người thiết kế event phải redaction/filter và quản lý quyền truy cập file theo chính sách dữ liệu.

## 12. Checklist hoàn thành

- [ ] Phân biệt event tĩnh và event động, biết vì sao static nên được ưu tiên khi schema cố định.
- [ ] Biết `EventFactory.create(eventAnnotations, fields)` và cách JFR tạo event type.
- [ ] Khai `ValueDescriptor` với supported type, Java identifier và metadata.
- [ ] Sử dụng `AnnotationElement` cho Name/Label/Category/Description/Timespan.
- [ ] Biết thứ tự ValueDescriptor quyết định `Event.set` indexes.
- [ ] Không gọi `Event.set` trên static event như một đường thao tác dữ liệu chính.
- [ ] Tạo một event object mới bằng `newEvent()`, điều khiển `begin/end` và `commit`.
- [ ] Dùng `isEnabled/shouldCommit` để hạn chế chi phí thu thập dữ liệu quan sát.
- [ ] Cấu hình `Recording.enable(eventName).withThreshold(...)` và `Recording.start/stop/dump`.
- [ ] Đọc `RecordedEvent` từ `RecordingFile` và kiểm field values theo tên.
- [ ] Quản lý `Registered(false)`, `register`, `unregister` khi thực sự cần.
- [ ] Giới hạn event count/types, overhead, field length và dữ liệu nhạy cảm.
- [ ] Chạy được `JfrDynamicEventDemo.java` bằng `javac --release 11` và kiểm đúng bảy dòng PASS/kết quả cuối.
- [ ] Nếu môi trường sản phẩm thật yêu cầu Java 11 runtime, chạy thêm trên **runtime Java 11 trong CI**, không chỉ compile target 11 trên JDK mới.

## 13. Tài liệu chính thức

1. [Java SE 11 — EventFactory: create, newEvent, getEventType, register, unregister](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventFactory.html)
2. [Java SE 11 — ValueDescriptor: kiểu field, tên, label, annotations](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/ValueDescriptor.html)
3. [Java SE 11 — AnnotationElement: metadata cho event động](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/AnnotationElement.html)
4. [Java SE 11 — Event: begin/end/commit/isEnabled/shouldCommit/set](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html)
5. [Java SE 11 — EventType: name, ID, category, fields](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventType.html)
6. [Java SE 11 — Recording: enable, threshold, start, stop, dump](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html)
7. [Java SE 11 — RecordingFile: đọc JFR file và streaming](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
8. [Java SE 11 — RecordedEvent: đọc giá trị của event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html)
9. [Java SE 11 — Java Flight Recorder package overview](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
10. [Java SE 26 — EventFactory: API vẫn được hỗ trợ và khuyến nghị dùng static event nếu biết field layout](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/EventFactory.html)
11. [Java SE 26 — jdk.jfr package: dynamic events, metadata và overhead](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
