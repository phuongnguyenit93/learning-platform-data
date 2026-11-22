# RecordedEvent, EventType và các trường có kiểu trong Java Flight Recorder

## Mục tiêu

Khi ứng dụng đã thu thập được **Java Flight Recorder (JFR) events**, bước tiếp theo là **đọc và hiểu đúng dữ liệu sự kiện**. Trong API Java hiện đại, ba khái niệm cần nắm chắc là:

- **`RecordedEvent`**: một **sự kiện đã được ghi lại**, với thời điểm, duration, thread, stack trace (nếu có) và các giá trị fields.
- **`EventType`**: mô tả **loại sự kiện**, gồm tên định danh, nhãn, category, các fields, metadata và các event settings.
- **`ValueDescriptor`**: metadata của **một field**, chẳng hạn tên, kiểu dữ liệu, nhãn và annotations xác định đơn vị đo.

Cả ba kết hợp cho phép bạn viết **consumer có kiểm tra schema**, tránh nhầm `int` với `String`, `long` lưu số mili-giây với `Duration`, hoặc đọc một field không có trong loại event đang xử lý.

Sau bài này, bạn sẽ:

1. Phân biệt **event instance** với **event type**, và giá trị của field với metadata field.
2. Đọc events từ file `.jfr` bằng `RecordingFile` và xử lý tương tự với callback `RecordingStream.onEvent(...)`.
3. Tra tên/kiểu của field bằng `EventType.getField`, `getFields` và `ValueDescriptor`.
4. Sử dụng đúng **typed getters** `getString`, `getInt`, `getLong`, `getBoolean`, `getDouble`, `getDuration`, `getInstant` và `getValue`.
5. Xử lý **field không tồn tại, sai kiểu, null, nested fields** và khác biệt schema giữa các JDK/recordings.
6. Đọc an toàn timestamp, duration, thread và stack trace của event, không nhầm với những trường có tên tương tự.
7. Biên dịch và chạy một ví dụ **Java 17+** tạo event tùy chỉnh, dump recording rồi đọc lại đầy đủ các giá trị có kiểu.

**Phạm vi hiện hành:** JFR có trong OpenJDK từ Java 11 (JEP 328); việc streaming events được bổ sung trong **Java 14** (JEP 349). Các API trong bài thuộc module `jdk.jfr` và vẫn được hỗ trợ ở Java hiện đại. Ví dụ dùng **JDK 17 trở lên**, không dùng cú pháp preview hoặc thư viện đã lỗi thời.

## 1. Từ một hiện tượng tới RecordedEvent

Khi JVM hoặc ứng dụng phát sinh một sự kiện đủ điều kiện thu thập, JFR có thể ghi lại dữ liệu của nó vào một recording.

~~~text
JVM/application activity
        |
        v
Event type: schema + settings
        |
        v
Event instance: values + time + context
        |
        v
JFR recording hoặc streaming
        |
        +--> File .jfr --> RecordingFile --> RecordedEvent
        |
        +--> RecordingStream.onEvent(...) --> RecordedEvent
                           |
                           v
                  EventType và typed getters
~~~

**Ý nghĩa của từng đối tượng:**

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `EventType` | Bản mô tả **loại** sự kiện, không phải một lần xảy ra | `jdk.GarbageCollection` hoặc `demo.OrderMeasured` |
| `RecordedEvent` | **Một lần ghi nhận** dữ liệu đã xảy ra trong recording | Đơn hàng `ORD-7` có 3 sản phẩm |
| `ValueDescriptor` | Mô tả một field của event type | `units` có kiểu `int`, `elapsedMillis` có kiểu `long` |
| `Recording` | Phiên thu thập events theo loại/cấu hình | Bật `demo.OrderMeasured` với threshold 0 |
| `RecordingFile` | API đọc tuần tự các events từ file `.jfr` | `readEvent()` |
| `RecordingStream` | API callback nhận events khi JVM hiện tại đang chạy | `onEvent("jdk.CPULoad", e -> ...)` |

**Không nhầm:** `jdk.jfr.Event` là **lớp cơ sở để tạo custom event trước khi ghi**, còn `jdk.jfr.consumer.RecordedEvent` là **đối tượng dữ liệu đã ghi được consumer đọc ra**. Bạn không làm `new RecordedEvent()` để phát một sự kiện.

Một `RecordedEvent` luôn gắn với một `EventType` phù hợp với nó, nhưng một `EventType` có thể mô tả **rất nhiều instances** trong file.

## 2. Nhìn đúng lớp và package

Các lớp chính:

~~~java
import jdk.jfr.Event;
import jdk.jfr.EventType;
import jdk.jfr.ValueDescriptor;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedObject;
import jdk.jfr.consumer.RecordingFile;
import jdk.jfr.consumer.RecordingStream;
~~~

Chúng thuộc module `jdk.jfr`. `RecordedEvent` **kế thừa `RecordedObject`** nên dùng được các phương thức đọc fields theo tên từ `RecordedObject`.

Những mối quan hệ quan trọng:

- `RecordedEvent.getEventType()` trả về `EventType` **không null** để xác định schema của instance.
- `EventType.getName()` là **tên định danh ổn định theo khai báo loại event**, ví dụ `jdk.CPULoad`, hoặc tên ứng dụng định nghĩa bằng `@Name`.
- `EventType.getLabel()` là **nhãn để đọc**, có thể null, không phải khóa định danh kỹ thuật.
- `EventType.getFields()` trả danh sách `ValueDescriptor` mô tả các trường của loại event.
- `EventType.getField("units")` trả descriptor nếu field tồn tại, hoặc **null** khi không có.
- `RecordedObject.hasField("units")` cho biết object đọc được có trường mang tên đó hay không.
- `RecordedEvent.getString("orderId")` hoặc `getInt("units")` đọc **giá trị** field theo kiểu tương ứng.

**Vì sao phải phân biệt metadata và value?** `EventType.getField("units").getTypeName()` cho biết field có kiểu `int`; nhưng số lượng `3` hoặc `5` phải lấy bằng `recordedEvent.getInt("units")` ở từng event instance.

## 3. EventType: tên, metadata và tập field

Ví dụ một loại event tùy chỉnh:

~~~java
@Name("demo.OrderMeasured")
@Label("Order measured")
static class OrderMeasured extends Event {
    String orderId;
    int units;
    boolean successful;
}
~~~

Đây là **đoạn minh họa trong một lớp Java**, chưa phải chương trình độc lập; phần 7 cung cấp đầy đủ imports, lớp, `main` và lệnh chạy.

`EventType` mô tả loại này:

~~~java
EventType type = recorded.getEventType();
System.out.println(type.getName());
System.out.println(type.getLabel());
~~~

Biến `recorded` là một `RecordedEvent` đã được đọc. Kết quả tên định danh là `demo.OrderMeasured`, còn label do `@Label` định nghĩa là `Order measured`.

### 3.1. Các API metadata hay dùng

| API | Trả về | Dùng cho |
|---|---|---|
| `type.getName()` | `String` | Xác định/fil­ter đúng **loại** event, thay vì dựa vào label |
| `type.getLabel()` | `String` hoặc null | Hiển thị tên thân thiện |
| `type.getDescription()` | `String` hoặc null | Mô tả loại event nếu được khai báo |
| `type.getCategoryNames()` | `List<String>` | Phân nhóm trong công cụ hiển thị |
| `type.getId()` | `long` | ID của event type **trong JVM**, không phải khóa bền vững liên ứng dụng |
| `type.getFields()` | `List<ValueDescriptor>` | Duyệt schema, xây bảng dữ liệu/validator |
| `type.getField("units")` | `ValueDescriptor` hoặc null | Kiểm tra một field cụ thể trước khi đọc |
| `type.getSettingDescriptors()` | `List<SettingDescriptor>` | Hiểu các settings của event type, như enabled/threshold/stack trace khi được hỗ trợ |

**Không sử dụng `getId()` làm định danh có thể lưu vĩnh viễn** xuyên JVM/process. Theo JDK, ID duy nhất trong bối cảnh JVM chứa event type và không phải khóa dùng để so sánh độc lập mọi bản ghi. Khi xây consumer đọc nhiều files/phiên bản, thường cần **event name + schema của từng file**.

### 3.2. ValueDescriptor là mô tả, không phải dữ liệu

~~~java
ValueDescriptor descriptor = type.getField("units");
if (descriptor != null) {
    String name = descriptor.getName();
    String typeName = descriptor.getTypeName();
    String label = descriptor.getLabel();
}
~~~

Đây là **đoạn minh họa** với `type` đã được lấy từ `RecordedEvent`.

- `getName()`: tên field, ví dụ `units`.
- `getTypeName()`: tên kiểu mô tả trong JFR, ví dụ `int` hoặc `java.lang.String`.
- `getLabel()`: nhãn hiển thị, **có thể null**.
- `getAnnotationElements()`/`getAnnotation(...)`: metadata annotations, hữu ích để xác định đơn vị thời gian, dữ liệu hoặc ý nghĩa field khi cần.
- `getFields()` trên descriptor của kiểu dữ liệu phức hợp có thể mô tả các trường nested của kiểu đó.

**Lưu ý đặc biệt:** Metadata cho biết field là một số `long`, nhưng **chưa đủ để suy ra đơn vị**. Chẳng hạn `elapsedMillis` được đánh dấu `@Timespan(Timespan.MILLISECONDS)` mới cho phép đọc đúng ý nghĩa thời lượng của field qua `getDuration("elapsedMillis")`; tên Java `elapsedMillis` là quy ước của tác giả, không thay thế annotation/schema.

### 3.3. `EventType.getFields()` và `RecordedEvent.getFields()`

Cả hai đều cung cấp metadata fields, nhưng khác điểm xuất phát:

~~~java
List<ValueDescriptor> typeFields = type.getFields();
List<ValueDescriptor> recordedFields = recorded.getFields();
~~~

Đây là **đoạn minh họa** cần import `java.util.List` và các biến liên quan.

- `type.getFields()` là schema của **loại event**.
- `recorded.getFields()` mô tả các fields có trong **đối tượng đã đọc** (API kế thừa/override từ `RecordedObject`).

Với consumer tổng quát, hãy dùng metadata đúng với `RecordedEvent` đang xử lý. Đừng hardcode mọi field name của một event `jdk.*` từ một bản JDK khác: schema có thể được bổ sung, thay đổi hoặc thiếu đi giữa versions/recordings.

## 4. RecordedEvent: timestamp, duration, thread, stack trace

Các getter đặc thù của `RecordedEvent`:

| Getter | Kiểu trả về | Lưu ý |
|---|---|---|
| `getStartTime()` | `java.time.Instant` | Điểm bắt đầu, không null |
| `getEndTime()` | `java.time.Instant` | Điểm kết thúc, không null |
| `getDuration()` | `java.time.Duration` | Độ dài của **bản thân event**, không null |
| `getThread()` | `RecordedThread` hoặc null | Thread gắn với event **nếu được ghi** |
| `getStackTrace()` | `RecordedStackTrace` hoặc null | Stack trace tại commit **nếu có** |
| `getEventType()` | `EventType` | Schema, không null |

~~~java
// Đoạn minh họa trong consumer; event có kiểu RecordedEvent.
Instant began = event.getStartTime();
Instant ended = event.getEndTime();
Duration measuredByJfr = event.getDuration();

if (event.getThread() != null) {
    System.out.println(event.getThread().getJavaName());
}
if (event.getStackTrace() != null) {
    System.out.println(event.getStackTrace().getFrames().size());
}
~~~

**Không nhầm hai loại duration:**

- `event.getDuration()`: thời lượng **được ghi cho event** (JFR tạo từ begin/end hoặc quy tắc của event type).
- `event.getDuration("elapsedMillis")`: **giá trị của field tên `elapsedMillis`** được đánh dấu metadata `@Timespan`; field này có thể mô tả một phép đo nghiệp vụ **khác** duration event.

Tương tự, `event.getStartTime()` lấy timestamp của event theo JFR, còn `event.getInstant("createdMillis")` đọc một field `long` được đánh dấu `@Timestamp`. Hai giá trị có thể khác nhau; đừng giả định luôn bằng nhau.

### Instant event

Theo Javadoc, với event tức thời, start time và end time bằng nhau; duration tương ứng có thể là `Duration.ZERO`. Không phải event nào cũng đại diện một khoảng đo được. Vì vậy không dùng `getDuration() > 0` như điều kiện chung để xác nhận “event hợp lệ”.

### Thread/stack trace có thể vắng

Một số events không ghi thông tin thread hoặc stack trace theo cấu hình/schema; `getThread()` và `getStackTrace()` có thể trả `null`. Không gọi `event.getThread().getJavaName()` hoặc `event.getStackTrace().getFrames()` khi chưa kiểm tra null.

Ngay cả khi có stack, đó là ngữ cảnh được ghi ở thời điểm phù hợp, **không bảo đảm** bao trọn toàn bộ lịch sử call stack hay giải thích mọi nguyên nhân hiệu năng.

## 5. Typed getters: đọc trường theo kiểu đã định nghĩa

Vì `RecordedEvent extends RecordedObject`, bạn có thể dùng các phương thức đọc theo tên:

| Getter | Kiểu dữ liệu đọc ra | Một trường hợp nên dùng |
|---|---|---|
| `getString("orderId")` | `String`, có thể null | Mã nghiệp vụ hoặc mô tả |
| `getInt("units")` | `int`, cho phép một số primitive widening hợp lệ | Số lượng, số đếm |
| `getLong("bytes")` | `long`, cho phép widening từ số nguyên nhỏ hơn | Bytes hoặc bộ đếm |
| `getBoolean("successful")` | `boolean` | Trạng thái đúng/sai |
| `getDouble("ratio")` | `double`, chấp nhận widening từ một số primitive số | Giá trị đo đã được định nghĩa |
| `getDuration("elapsedMillis")` | `Duration` | Field số có **`@Timespan`** |
| `getInstant("createdMillis")` | `Instant` | Field số có **`@Timestamp`** |
| `getThread("eventThread")` | `RecordedThread` hoặc null | Field kiểu `Thread` |
| `getClass("eventClass")` | `RecordedClass` hoặc null | Field kiểu `Class` |
| `getValue("units")` | generic `T`, cần chú ý runtime type | Consumer động muốn kiểm tra/dispatch theo metadata |
| `hasField("units")` | `boolean` | Kiểm tra tên field trước khi đọc |

**Đúng kiểu quan trọng hơn tên getter trông gần giống.**

~~~java
int n = event.getInt("units");       // units có schema kiểu int
String id = event.getString("orderId"); // orderId có kiểu String
long size = event.getLong("bytes");  // bytes có kiểu long
~~~

Các dòng là **đoạn minh họa trong consumer**.

### 5.1. Lỗi sai kiểu là lỗi của caller, không phải tự động convert mọi thứ

~~~java
// Sai kiểu: orderId là String, không phải int.
int bad = event.getInt("orderId");
~~~

Khi gọi `getInt` trên trường có kiểu `String`, JFR ném `IllegalArgumentException`. Đó là lỗi chọn accessor, **không tự parse** chuỗi số thành `int`.

### 5.2. Một số primitive widening được hỗ trợ

Theo Javadoc `RecordedObject`, các getter số có thể chấp nhận một số kiểu primitive **có thể widening** sang kiểu đích; ví dụ một field `int` có thể đọc qua `getLong(...)`. Nhưng **không** có quy tắc tự narrowing tùy tiện: field `long` không mặc định đọc được bằng `getInt(...)`.

**Thiết kế consumer tốt:** Dùng getter khớp type schema khi đã biết. Chỉ dùng widening nếu được Javadoc bảo đảm và bạn thật sự cần. Không dựa vào cách cast thô hoặc ép kiểu mất thông tin.

### 5.3. `getValue(...)` không tự bảo đảm cast đúng

~~~java
Object raw = event.getValue("units");
if (raw instanceof Integer count) {
    System.out.println(count);
}
~~~

Đây là **đoạn minh họa Java 17**. `getValue` giúp consumer xử lý dynamic fields, nhưng không thay thế validation về type. Đừng viết ngay `(String) event.getValue("units")` nếu field thực tế là `int` đã boxed thành `Integer`: ép kiểu sai sẽ thất bại.

Khi cần thao tác có type safety, ưu tiên `getInt`, `getString`, `getDuration` hoặc `getInstant` nếu schema tương ứng. Với bảng dữ liệu động, kết hợp `ValueDescriptor` và xử lý cụ thể cho từng kiểu field.

## 6. Metadata đơn vị: @Timespan, @Timestamp và @DataAmount

**Kiểu Java không đủ để xác định đơn vị đo.** Cùng kiểu `long` có thể đại diện bytes, nanos, milliseconds hoặc epoch time. JFR cung cấp các annotations metadata để diễn đạt ý nghĩa:

~~~java
// Đoạn minh họa bên trong class extends jdk.jfr.Event.
@DataAmount(DataAmount.BYTES)
long bytes;

@Timespan(Timespan.MILLISECONDS)
long elapsedMillis;

@Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)
long createdMillis;
~~~

### 6.1. `@Timespan` và `getDuration(fieldName)`

`@Timespan(Timespan.MILLISECONDS)` chỉ rõ field số lưu **mili-giây**. `recorded.getDuration("elapsedMillis")` đọc dữ liệu và chuyển thành `java.time.Duration`.

Ví dụ trường lưu `25`, kết quả `getDuration("elapsedMillis").toMillis()` là `25`. Đừng lấy raw `25` rồi tùy ý gọi `Duration.ofNanos(25)`: đó là sai đơn vị.

**Mặc định của `@Timespan` là nanoseconds** khi không chỉ rõ unit. Nếu field không được annotate đúng, `getDuration(name)` có thể ném `IllegalArgumentException`. Hãy kiểm tra metadata và khai báo đơn vị có chủ đích.

### 6.2. `@Timestamp` và `getInstant(fieldName)`

`@Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)` diễn đạt field lưu milliseconds từ Unix epoch UTC. `getInstant("createdMillis")` chuyển field đó thành `java.time.Instant`.

Ví dụ:

~~~java
long millis =
        Instant.parse("2026-01-02T03:04:05Z").toEpochMilli();
~~~

Khi lưu `millis` ở field có annotation trên, `getInstant("createdMillis")` sẽ cho `2026-01-02T03:04:05Z`.

**Không nhầm**:

- `event.getStartTime()`: thời điểm sự kiện bắt đầu theo dữ liệu JFR.
- `event.getInstant("createdMillis")`: timestamp **do code ứng dụng lưu** trong field cùng tên.

### 6.3. `@DataAmount` và bytes

`@DataAmount(DataAmount.BYTES)` mô tả ý nghĩa của một field như số bytes. Nó **không đổi kiểu primitive** của field: field vẫn là `long`, nên bạn đọc qua `getLong("bytes")`, không phải một getter trả `DataSize`.

### 6.4. Trường null và thiếu metadata

- Một `String` field có thể là null; `getString` có thể trả null. Code consumer phải xử lý theo hợp đồng.
- Primitive numeric/boolean fields không mang null theo Java primitive semantics; nhưng field **không tồn tại** là vấn đề khác.
- Không suy ra sự tồn tại hay ý nghĩa của field chỉ từ tên dễ đoán. Xác minh `EventType.getField(name)` hoặc `recorded.hasField(name)`; kiểm tra annotation nếu cách đọc phụ thuộc đơn vị.

## 7. Chương trình Java 17 hoàn chỉnh: tạo và đọc 6 trường có kiểu

Chương trình dưới đây tự tạo một custom JFR event. Nó chỉ dùng module `jdk.jfr` có trong JDK, không yêu cầu Maven/Gradle hay thư viện thứ ba.

Bài thực hành chủ động chọn các giá trị cố định để đầu ra có thể so sánh chính xác; **timestamp của event thực tế vẫn do JVM sinh ra** và không được in như một giá trị cố định.

### 7.1. Tệp `JfrTypedFieldsDemo.java`

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;

import jdk.jfr.Category;
import jdk.jfr.DataAmount;
import jdk.jfr.Event;
import jdk.jfr.EventType;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.Timespan;
import jdk.jfr.Timestamp;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrTypedFieldsDemo {
    @Name("demo.OrderMeasured")
    @Label("Order measured")
    @Category({"Demo", "Orders"})
    static class OrderMeasured extends Event {
        String orderId;
        int units;
        boolean successful;

        @DataAmount(DataAmount.BYTES)
        long bytes;

        @Timespan(Timespan.MILLISECONDS)
        long elapsedMillis;

        @Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)
        long createdMillis;
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("jfr-fields-", ".jfr");
        try {
            try (Recording rec = new Recording()) {
                rec.enable(OrderMeasured.class)
                   .withThreshold(Duration.ZERO);
                rec.start();

                OrderMeasured event = new OrderMeasured();
                event.orderId = "ORD-7";
                event.units = 3;
                event.successful = true;
                event.bytes = 2048;
                event.elapsedMillis = 25;
                event.createdMillis =
                        Instant.parse(
                                "2026-01-02T03:04:05Z").toEpochMilli();
                event.commit();

                rec.stop();
                rec.dump(file);
            }

            int count = 0;
            try (RecordingFile reader = new RecordingFile(file)) {
                while (reader.hasMoreEvents()) {
                    RecordedEvent event = reader.readEvent();
                    EventType type = event.getEventType();

                    if (!"demo.OrderMeasured".equals(type.getName())) {
                        continue;
                    }

                    count++;
                    System.out.println(
                            "eventType=" + type.getName());
                    System.out.println("metadata=" +
                            type.getField("units").getTypeName()
                            + "," +
                            type.getField("elapsedMillis").getTypeName());
                    System.out.println("fields=" +
                            event.hasField("orderId")
                            + "," + event.hasField("unknown"));
                    System.out.println("values=" +
                            event.getString("orderId")
                            + "," + event.getInt("units")
                            + "," + event.getBoolean("successful")
                            + "," + event.getLong("bytes"));
                    System.out.println("elapsed=" +
                            event.getDuration("elapsedMillis").toMillis());
                    System.out.println("created=" +
                            event.getInstant("createdMillis"));
                    System.out.println("rawInt=" +
                            (event.getValue("units") instanceof Integer));
                    System.out.println("timeOrder=" +
                            !event.getStartTime().isAfter(
                                    event.getEndTime()));

                    try {
                        event.getInt("orderId");
                        System.out.println(
                                "wrongGetterRejected=false");
                    } catch (IllegalArgumentException ex) {
                        System.out.println(
                                "wrongGetterRejected=true");
                    }

                    try {
                        event.getString("unknown");
                        System.out.println(
                                "missingGetterRejected=false");
                    } catch (IllegalArgumentException ex) {
                        System.out.println(
                                "missingGetterRejected=true");
                    }
                }
            }
            System.out.println("matchedEvents=" + count);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch/chạy trên JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 JfrTypedFieldsDemo.java
java JfrTypedFieldsDemo
~~~

**Đầu ra đã kiểm chứng bằng biên dịch và chạy Java thật:**

~~~text
eventType=demo.OrderMeasured
metadata=int,long
fields=true,false
values=ORD-7,3,true,2048
elapsed=25
created=2026-01-02T03:04:05Z
rawInt=true
timeOrder=true
wrongGetterRejected=true
missingGetterRejected=true
matchedEvents=1
~~~

### 7.2. Vì sao kết quả như vậy?

1. **`eventType=demo.OrderMeasured`**: `@Name` gán tên loại custom event. Khi đọc file, `getEventType().getName()` cho đúng định danh.
2. **`metadata=int,long`**: hai field `units` và `elapsedMillis` có **kiểu lưu trữ primitive** `int` và `long`, dù field `elapsedMillis` mang annotation đơn vị `@Timespan`.
3. **`fields=true,false`**: `hasField("orderId")` có, còn `hasField("unknown")` không.
4. **`values=ORD-7,3,true,2048`**: các typed getters `getString`, `getInt`, `getBoolean` và `getLong` trả đúng loại và giá trị.
5. **`elapsed=25`**: `getDuration("elapsedMillis")` chuyển giá trị `25` milliseconds thành `Duration`.
6. **`created=2026-01-02T03:04:05Z`**: `@Timestamp(MILLISECONDS_SINCE_EPOCH)` cho phép `getInstant` khôi phục đúng thời điểm đã ghi trong field, không phụ thuộc thời điểm chạy chương trình.
7. **`rawInt=true`**: `getValue("units")` trả giá trị boxed `Integer` khi field là `int`.
8. **`timeOrder=true`**: thời điểm bắt đầu không lớn hơn kết thúc của event, nhưng program không hardcode timestamp thực tế.
9. **`wrongGetterRejected=true`**: thử đọc `orderId` (String) bằng `getInt` thất bại với `IllegalArgumentException`.
10. **`missingGetterRejected=true`**: thử đọc tên `unknown` không tồn tại cũng thất bại, khác với trường có giá trị null.
11. **`matchedEvents=1`**: code commit một custom event và lọc theo tên. File `.jfr` có thể chứa các loại events khác; vòng lặp chỉ in loại mong muốn.

**Vì sao dùng `Duration.ZERO` khi bật event?** Chương trình chỉ chạy thời gian ngắn và muốn ghi cả event tức thời; setting threshold 0 tránh loại bỏ nó vì duration quá nhỏ.

**Vì sao có `Files.deleteIfExists(...)`?** Ví dụ dùng file tạm và dọn sau khi đọc. Nếu cần mở kết quả bằng JDK Mission Control hoặc lệnh `jfr`, hãy dùng file cố định, bỏ bước xóa và quản lý quyền truy cập/dung lượng trước khi chia sẻ.

**Ranh giới đầu ra:** Event timestamp thật, thread ID và stack trace phụ thuộc JVM/workload; bài không giả định các giá trị runtime đó cố định. Kết quả đã nêu chỉ in các trường mẫu chủ động đặt và các kiểm tra logic.

## 8. Viết consumer chịu được khác biệt schema

Các event `jdk.*` có thể khác fields giữa phiên bản JDK, tùy nền tảng hoặc cấu hình thu thập. Một consumer tổng quát cần **kiểm tra schema trước khi đọc**.

### 8.1. Lọc theo event name trước

~~~java
// Mã minh họa trong consumer; event là RecordedEvent.
if (!"jdk.SocketRead".equals(event.getEventType().getName())) {
    return;
}
~~~

Đoạn minh họa có `return` nên giả định được đặt trong một callback/phương thức có kiểu trả về `void`. Không dùng `getLabel()` để so sánh định danh: label có thể dành cho hiển thị, bản địa hóa hoặc không tồn tại.

### 8.2. Kiểm tra field/kiểu trước khi gọi getter

~~~java
// Đoạn minh họa, với event có kiểu RecordedEvent.
EventType t = event.getEventType();
ValueDescriptor field = t.getField("bytesRead");
if (field != null && "long".equals(field.getTypeName())) {
    long count = event.getLong("bytesRead");
    System.out.println(count);
}
~~~

Trong một số JFR events, tên/kiểu có thể khác giả định. Đây là **mẫu kiểm tra**, không cam kết mọi JDK có `bytesRead` trong mọi event. Khi muốn hỗ trợ widening hoặc dynamic schemas, dùng metadata để chọn nhánh chứ không gắn cứng mọi field cùng getter.

### 8.3. Không đánh đồng missing field và null value

**Trường hợp A:** metadata không có `orderId`. Khi đó `hasField("orderId")` là `false`; `getString("orderId")` có thể ném `IllegalArgumentException` vì tên không tồn tại.

**Trường hợp B:** metadata có `orderId` kiểu `String`, nhưng giá trị thực là null. `hasField("orderId")` vẫn có thể là `true`; `getString("orderId")` trả **null**. Đây là hai tình huống khác nhau, cần xử lý riêng.

Thói quen tốt:

~~~java
if (!event.hasField("orderId")) {
    // Schema không cung cấp field này.
} else {
    String id = event.getString("orderId");
    if (id == null) {
        // Field tồn tại nhưng không có giá trị trong instance.
    }
}
~~~

Đây là **đoạn minh họa trong method**.

### 8.4. Nested fields và đường dẫn có dấu chấm

`RecordedObject` hỗ trợ truy cập một số nested fields qua cú pháp `"a.b.c"` khi schema thực sự chứa cấu trúc lồng nhau, chẳng hạn thông tin thread/class:

~~~java
// Pseudocode minh họa, không giả định mọi event có field này.
if (event.hasField("eventThread.javaName")) {
    String javaName = event.getString("eventThread.javaName");
}
~~~

**Cẩn thận:** Khi đi qua nested object mà giá trị trung gian null, API có thể ném `NullPointerException` ngay cả khi schema mô tả đường dẫn ấy. Không nên tin rằng `hasField("a.b")` tự chứng minh mọi intermediate value đều khác null; dùng API typed cho nested object hoặc xử lý ngoại lệ/kiểm tra null theo hợp đồng của field.

## 9. Đọc file, đọc stream và điều tra schema bằng CLI

### 9.1. RecordingFile: đọc tuần tự để tránh tải cả file lớn

~~~java
// Mã minh họa; path là Path trỏ tới file JFR tin cậy.
try (RecordingFile file = new RecordingFile(path)) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        System.out.println(event.getEventType().getName());
    }
}
~~~

`RecordingFile.readAllEvents(path)` là API tiện lợi để lấy một `List<RecordedEvent>`, nhưng Javadoc khuyến nghị dùng cho trường hợp đơn giản, **không phù hợp để đọc file rất lớn chỉ trong một lần**. Với recording có dung lượng lớn, duyệt tuần tự theo `hasMoreEvents()` / `readEvent()` và lọc sớm sẽ tiết kiệm memory hơn.

**Không đọc file JFR không tin cậy tùy tiện**: `RecordingFile` là parser dữ liệu nhị phân và Javadoc khuyến nghị chỉ dùng với nguồn đáng tin. Giới hạn kích thước, quyền truy cập và đường dẫn theo yêu cầu vận hành.

### 9.2. RecordingStream: cùng kiểu RecordedEvent trong callback

~~~java
import java.time.Duration;
import jdk.jfr.consumer.RecordingStream;

// Đoạn minh họa: ứng dụng được phép ghi events JFR.
try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad")
          .withPeriod(Duration.ofSeconds(1));
    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(event.getEventType().getName());
        // Đọc các fields của event sau khi xác minh schema.
    });
    stream.startAsync();
    Thread.sleep(3_000);
}
~~~

Callback `onEvent` nhận đối tượng **`RecordedEvent`**, nên có thể áp dụng cùng mô hình `getEventType`, `getFields` và typed getters như đọc file.

**Không bảo đảm chính xác ba samples** trong ba giây: events phát sinh theo chu kỳ, khả năng thu thập và scheduling; ví dụ không cố định stdout. Khi dừng block, `try-with-resources` đóng stream.

### 9.3. Dùng jfr metadata để thấy schema thật

Với một file recording tin cậy:

~~~bash
jfr summary recording.jfr
jfr metadata recording.jfr
jfr print --events jdk.CPULoad recording.jfr
~~~

`jfr metadata` giúp tra types và fields thực trong file trước khi viết consumer hardcode. `jfr print` giúp đối chiếu giá trị thực. Những lệnh này dùng công cụ `jfr` đi kèm JDK hiện đại; `recording.jfr` là file minh họa, không giả định sẵn có trên máy người học.

### 9.4. Đọc thời lượng và timestamp đúng tầng

Trong công cụ phân tích, có thể tồn tại:

- Timestamp bản thân event (start/end).
- Thời lượng event (`getDuration()`).
- Field có đơn vị thời gian riêng (`@Timespan`).
- Field dữ liệu thời gian của ứng dụng (`@Timestamp`).

Đừng đổi tất cả về `long` và tự suy diễn đơn vị, vì mỗi con đường truy xuất có thể mang semantics khác nhau. Ưu tiên `Duration`/`Instant` do API trả ra khi phù hợp.

## 10. Lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách đúng |
|---|---|---|
| Nhầm `Event` và `RecordedEvent` | Một cái dùng để phát custom event, một cái là event đã ghi để consumer xử lý | Phân biệt `jdk.jfr.Event` với `jdk.jfr.consumer.RecordedEvent` |
| Dùng `EventType` như một instance chứa giá trị | EventType chỉ mô tả schema | Lấy fields bằng getter của từng `RecordedEvent` |
| Lọc theo `getLabel()` | Label là tên hiển thị, có thể null hoặc thay đổi | Lọc theo `getName()` |
| Hardcode `EventType.getId()` xuyên runs | ID được cấp trong JVM, không phải ID lâu bền giữa recordings/JVM | Dùng name/schema hoặc khóa nghiệp vụ tường minh |
| Chọn `getInt` chỉ vì giá trị “trông như số” | Field có thể là `String` hoặc `long` | Xem `ValueDescriptor.getTypeName` trước |
| Gọi `getInt("orderId")` | Field `orderId` là String | Dùng `getString`; nếu muốn số, parse/validate ở tầng ứng dụng |
| Dùng `getInt` cho field `long` | Narrowing không được tự thực hiện | Dùng `getLong` và kiểm tra overflow nếu cần chuyển hẹp |
| Dùng `getDuration("bytes")` | Bytes không phải field `@Timespan` | Dùng `getLong("bytes")` và metadata `@DataAmount` |
| Coi `getDuration()` giống `getDuration("elapsedMillis")` | Một bên là duration event, một bên là field được annotate | Giải thích, đặt tên và kiểm thử tách biệt |
| Tự coi mọi `long` là milliseconds | Có thể là bytes, ticks, nanos hoặc timestamp | Đọc annotations/field schema, dùng typed conversions |
| Gọi `getInstant("x")` trên field không có `@Timestamp` | Không đủ metadata chuyển đổi đúng | Chỉ dùng với timestamp field hợp lệ |
| Không kiểm tra field tồn tại | Event schema có thể khác phiên bản | `getField(...)`/`hasField(...)` trước khi đọc |
| Nhầm missing với null | Lỗi schema khác dữ liệu instance không có giá trị | Xử lý hai trường hợp tách biệt |
| Dereference `getThread()`/`getStackTrace()` khi null | Một số event không ghi những context này | Kiểm tra null và cấu hình recording |
| Tin `getValue` luôn đúng kiểu generic mong muốn | Có thể cần cast và sai runtime type | Xử lý theo metadata; ưu tiên typed getter |
| Đọc file nhiều GB bằng `readAllEvents` | Tốn memory không cần thiết | Đọc tuần tự bằng `RecordingFile` |
| In mọi field/event vào log production | Tạo overhead, phơi bày dữ liệu nhạy cảm | Lọc loại sự kiện và field, kiểm soát quyền truy cập/retention |
| Tin số event nhận được bằng mọi hoạt động thực tế | Sampling/threshold/period có thể bỏ qua hoạt động | Diễn giải trong phạm vi recording và settings |

## 11. Checklist thiết kế consumer JFR

1. **Xác định nguồn:** file `.jfr` hay stream đang chạy? Có quyền truy cập và dữ liệu tin cậy không?
2. **Lọc event type:** dựa trên `getEventType().getName()`; tránh dùng nhãn hiển thị.
3. **Kiểm tra schema:** `EventType.getField/getFields` hoặc `RecordedEvent.hasField`.
4. **Chọn getter phù hợp:** string/int/long/boolean, hoặc annotation-aware duration/timestamp.
5. **Kiểm tra null:** dữ liệu reference có thể null; `RecordedThread`/`RecordedStackTrace` có thể null.
6. **Hiểu đơn vị đo:** metadata `@Timespan`, `@Timestamp`, `@DataAmount`; tránh tự ép raw long sang một đơn vị tùy ý.
7. **Xử lý schema khác JDK:** field có thể được thêm/bỏ/đổi kiểu; ghi rõ JDK, recording settings và nguồn dữ liệu.
8. **Giới hạn chi phí:** đọc file lớn tuần tự, tránh xử lý nặng trên callback stream; lọc events trước khi tính toán.
9. **Bảo vệ dữ liệu:** recording có thể chứa stack traces, tên class/paths và custom payload. Không ghi token, mật khẩu hay dữ liệu cá nhân không cần thiết vào custom events.
10. **Viết test:** kiểm tra cả success cases, thiếu field, sai getter và conversion có annotation. Nếu phải suy luận hiệu năng, xét sampling/threshold và đặt event vào đúng ngữ cảnh thời gian.

## 12. Tự kiểm tra

**Câu 1.** `EventType.getField("units")` và `RecordedEvent.getInt("units")` khác nhau thế nào?

**Đáp án:** API đầu trả **metadata field** (hoặc null) để biết tên/kiểu/annotations; API sau trả **giá trị `int` của field** trong instance đã ghi, và ném lỗi nếu tên/kiểu không phù hợp.

**Câu 2.** `getInt("orderId")` có tự chuyển mã `"123"` thành số nguyên không?

**Đáp án:** Không. Typed getter tuân schema; field kiểu `String` phải đọc bằng `getString`. Nếu ứng dụng cần số, parse/validate sau đó ở tầng nghiệp vụ.

**Câu 3.** Nếu `event.hasField("name")` là `true` nhưng `event.getString("name")` trả null, có mâu thuẫn không?

**Đáp án:** Không. Field có thể **tồn tại trong schema**, còn **giá trị cụ thể** trong event instance là null.

**Câu 4.** Vì sao không nên dùng `event.getDuration()` để thay cho `event.getDuration("elapsedMillis")`?

**Đáp án:** `getDuration()` mô tả duration của **chính event**; overload có tên field đọc một số được annotate `@Timespan`. Hai đại lượng có thể khác nhau.

**Câu 5.** Với `@Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH) long createdMillis`, getter nào tạo ra `Instant`?

**Đáp án:** `event.getInstant("createdMillis")`. Getter `getStartTime()` lấy timestamp riêng của JFR event, không phải field tùy chỉnh.

**Câu 6.** Nếu một event có field `long bytes` với `@DataAmount(DataAmount.BYTES)`, nên đọc thế nào?

**Đáp án:** `event.getLong("bytes")`, sau đó hiểu đơn vị là bytes dựa trên metadata. `@DataAmount` không đổi kiểu primitive thành `Duration`.

**Câu 7.** Bạn viết consumer đọc file JFR từ bản JDK khác và không tìm thấy field quen thuộc. Có nên mặc định giá trị bằng 0 rồi kết luận không có hoạt động?

**Đáp án:** Không. Cần kiểm tra event type, schema, cấu hình, phiên bản JDK và lý do field không tồn tại. “Missing field” không đồng nghĩa “giá trị 0” hoặc “không có hiện tượng”.

**Câu 8.** `getThread()` có bảo đảm khác null không? Vì sao?

**Đáp án:** Không. Loại event/cấu hình có thể không ghi thread. Nếu cần Java thread name, kiểm tra null trước khi gọi `getJavaName()`.

**Câu 9.** Với một file JFR rất lớn, nên dùng `RecordingFile.readAllEvents` hay vòng lặp `hasMoreEvents/readEvent`?

**Đáp án:** Ưu tiên vòng lặp tuần tự để không phải đưa toàn bộ recording vào memory cùng lúc; lọc sớm theo tên event và fields cần thiết.

**Câu 10.** Vì sao `getValue("units") instanceof Integer` trả true trong chương trình mẫu?

**Đáp án:** Field được khai báo kiểu primitive `int` và dữ liệu được truy xuất dưới dạng object được boxed thành `Integer`. `getValue` không tự đổi nó thành `String`.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): nền tảng JFR trong OpenJDK.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): sự kiện streaming và API tiêu thụ từ Java 14.
- [Java SE 17 — `RecordedEvent`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): event time, duration, thread, stack trace, event type.
- [Java SE 17 — `RecordedObject`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): typed getters, nested fields, `hasField`, `getValue`.
- [Java SE 17 — `EventType`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/EventType.html): tên, ID, fields, settings và metadata của loại event.
- [Java SE 17 — `ValueDescriptor`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/ValueDescriptor.html): tên và kiểu dữ liệu của một field, annotations/labels.
- [Java SE 17 — `RecordingFile`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc `.jfr` tuần tự; khuyến cáo chỉ đọc files tin cậy và không dùng `readAllEvents` cho files lớn.
- [Java SE 17 — `RecordingStream`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): nhận `RecordedEvent` trong callback khi streaming.
- [Java SE 17 — `Timespan`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Timespan.html): đơn vị đo và annotation cho duration field.
- [Java SE 17 — `Timestamp`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Timestamp.html): đơn vị epoch/ticks cho timestamp field.
- [Java SE 17 — `DataAmount`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/DataAmount.html): đơn vị số lượng dữ liệu như bytes.
- [Oracle Java 17 — `jfr` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `summary`, `metadata`, `print` để kiểm chứng file JFR.

**Ghi nhớ:** `RecordedEvent` là **một event đã được ghi**, `EventType` là **schema của loại event**, còn `ValueDescriptor` mô tả **kiểu và metadata của từng field**. Hãy kiểm tra event type/field tồn tại, chọn **typed getter đúng với schema** và chú ý annotations đơn vị; không gộp mọi field về `String` hoặc `long` một cách tùy tiện. Khi xử lý JFR trong hệ thống thật, kiểm soát version, sampling, quyền truy cập và khối lượng dữ liệu trước khi rút ra kết luận.