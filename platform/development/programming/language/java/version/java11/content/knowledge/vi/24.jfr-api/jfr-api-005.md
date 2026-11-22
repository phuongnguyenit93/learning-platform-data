# Event tùy biến và trường dữ liệu trong Java Flight Recorder (Java 11+)

## 1. Event tùy biến là gì, và khi nào cần tạo?

**Java Flight Recorder (JFR)** là hệ thống quan sát/ghi dữ liệu chẩn đoán hiệu năng tích hợp vào JVM. Từ **Java 11**, OpenJDK cung cấp JFR chính thức theo **JEP 328** và module công khai `jdk.jfr`. Ngoài những event do JVM phát ra (GC, thread, I/O...), ứng dụng có thể định nghĩa **custom events** để ghi lại các mốc có ý nghĩa với sản phẩm, như một bước xử lý đơn hàng, cache miss, thao tác đọc dữ liệu chậm, hoặc một pha của batch job.

Một custom event gồm:

1. **Event type**: kiểu sự kiện do một class `extends jdk.jfr.Event` định nghĩa; mô tả **tên, danh mục, metadata và schema trường dữ liệu**.
2. **Event instance**: một đối tượng của event type được tạo khi ứng dụng đang thực hiện công việc. Mỗi instance có thể mang **giá trị trường riêng**.
3. **Thời gian**: timestamp và duration mà JFR có thể ghi cho event; mặc định có những thông tin như thread/stack trace tùy setting.
4. **Settings**: cấu hình của recording quyết định event có được bật, có đạt threshold, có lấy stack trace hay không.
5. **Commit**: ứng dụng gọi `event.commit()` để gửi dữ liệu tới hệ thống ghi JFR. **Commit không bảo đảm** mọi instance đều xuất hiện trong tệp `.jfr`: event có thể bị tắt, dưới threshold, hoặc dữ liệu có thể không được giữ do hạn chế buffer/retention.

Luồng khái niệm:

```text
class OrderStep extends Event
       |              (schema: stepName, itemCount, payloadBytes...)
       v
new OrderStep() + gán field
       |
       +-- begin() --> code nghiệp vụ --> end()
       |
       +-- isEnabled()/shouldCommit() kiểm tra nhu cầu ghi
       |
       v
commit() --> JFR recorder/buffers --> recording/chunks --> dump .jfr
                                                       |
                                                       v
                                     RecordingFile / jfr print
                                     đọc event + field values
```

JFR là **công cụ chẩn đoán**, không phải log giao dịch bền vững bắt buộc giữ đủ mọi event. Nếu cần audit, accounting hay exactly-once records, dùng cơ chế lưu bền vững riêng. Những API `Event`, `Recording`, `EventType` và `RecordingFile` trong bài vẫn áp dụng trên các JDK hiện đại; ví dụ được viết cho **Java 11** để tránh API mới không có ở phiên bản đó.

## 2. Khai báo custom event bằng `extends Event`

Cách đơn giản và thường tối ưu nhất khi biết schema từ lúc biên dịch là tạo một class kế thừa `jdk.jfr.Event`:

```java
import jdk.jfr.Category;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("demo.OrderStep")
@Label("Order Step")
@Description("Records a completed order processing step.")
@Category({"Demo", "Orders"})
class OrderStep extends Event {
    @Label("Step Name")
    String stepName;

    @Label("Item Count")
    int itemCount;

    @Label("Succeeded")
    boolean success;
}
```

Đây là **class minh họa**, không chứa `main` và chưa mở `Recording`. Các điểm cần hiểu:

- `@Name("demo.OrderStep")` đặt tên định danh ổn định cho event type. Nếu không đặt, JFR thường lấy tên class đủ package. Một tên có namespace rõ giúp các công cụ lọc và tránh trùng với built-in events như `jdk.*`.
- `@Label` cung cấp **nhãn dễ đọc**, không phải tên field mà API dùng khi gọi `RecordedEvent.getString("stepName")`. Getter dùng **tên Java field**.
- `@Description` bổ sung mô tả cho người điều tra.
- `@Category({"Demo", "Orders"})` biểu diễn **đường dẫn danh mục**; metadata có thể được truy vấn bằng `EventType.getCategoryNames()`.
- Những field instance kiểu được hỗ trợ (như `String`, `int`, `boolean`) là **payload của event**. Không cần khai báo method setter cho từng field để JFR đọc được.
- **Không có “tự động gửi event” chỉ vì class được khai báo.** Ứng dụng phải tạo instance, gán giá trị và gọi `commit()` trong khi recording phù hợp hoạt động.

Khi schema được biết trước, cách khai báo tĩnh thường tốt hơn `EventFactory`: JFR/JVM có thể tối ưu đường phát event, kể cả hạn chế chi phí khi event bị tắt. `EventFactory` vẫn là API công khai, nhưng chỉ dùng khi thật sự phải tạo schema **lúc runtime** (mục 8).

## 3. Kiểu dữ liệu nào được JFR ghi thành field?

Theo Javadoc `jdk.jfr.Event` của **Java 11 và các JDK hiện đại**, các **instance fields** có kiểu sau được hỗ trợ:

| Kiểu Java | Ví dụ field | Đọc lại từ `RecordedEvent` |
| --- | --- | --- |
| `boolean` | `boolean success;` | `getBoolean("success")` |
| `byte` | `byte state;` | `getByte("state")` |
| `short` | `short shard;` | `getShort("shard")` |
| `char` | `char kind;` | `getChar("kind")` |
| `int` | `int itemCount;` | `getInt("itemCount")` |
| `long` | `long payloadBytes;` | `getLong("payloadBytes")` |
| `float` | `float load;` | `getFloat("load")` |
| `double` | `double ratio;` | `getDouble("ratio")` |
| `String` | `String stepName;` | `getString("stepName")` |
| `Thread` | `Thread sourceThread;` | `getThread("sourceThread")` → `RecordedThread` |
| `Class` | `Class<?> component;` | `getClass("component")` → `RecordedClass` |

**Chỉ những kiểu tham chiếu `String`, `Thread` và `Class` được hỗ trợ trực tiếp** ngoài primitive. Những kiểu như `List`, `Map`, `UUID`, `BigDecimal`, `Instant`, enum, array hoặc một object domain bất kỳ **không được JFR tự serialize** thành field event.

Ví dụ các field JFR **bỏ qua một cách im lặng**:

```java
class DataEvent extends jdk.jfr.Event {
    String description;              // Được hỗ trợ.
    long bytes;                      // Được hỗ trợ.

    static String shared = "static"; // KHÔNG được ghi: static.
    transient String temp;           // KHÔNG được ghi: transient.
    String[] tags;                   // KHÔNG được ghi: array.
    java.util.List<String> details;  // KHÔNG được ghi: kiểu tham chiếu khác.
    Status status;                   // KHÔNG được ghi: enum.
}

enum Status { OK, FAILED }
```

Đây là **đoạn mã minh họa** (không có `main`). Code Java vẫn có các field trên, nhưng schema JFR **không chứa** chúng. Đây là điểm nguy hiểm: chương trình có thể compile/run và `commit()` mà **không có exception** dù những field bạn mong muốn không tồn tại trong recording.

Nếu muốn ghi enum, hãy chuyển nó thành một `String` có ý nghĩa, ví dụ `event.statusName = status.name()`; nếu muốn ghi object, hãy chọn **một số primitive/String fields có ích** (request type, số lượng, byte count, tên bước, result code...), không dùng `object.toString()` bừa bãi vì có thể dài, không ổn định hoặc lộ bí mật.

### Giá trị mặc định và rủi ro gán thiếu

Nếu chưa gán, instance primitive fields theo quy tắc Java mang giá trị mặc định (số 0, `false`); reference fields là `null`. JFR không suy ra rằng `0` nghĩa “chưa biết” hay `false` nghĩa “lỗi”. Ứng dụng nên thiết kế schema có ý nghĩa và gán field nhất quán **trước `commit()`**. Khi cần phân biệt không có giá trị, cân nhắc một field `boolean hasX` hoặc một quy ước được tài liệu hóa, không ép sentinel tùy tiện vào kiểu đo lường.

### Field của `Class`/`Thread` không phải Java object được serialize

Một field `Class<?>` hoặc `Thread` được ghi theo mô hình metadata của JFR. Khi đọc file, bạn lấy **`RecordedClass`** hoặc **`RecordedThread`**, không phải instance `Class`/`Thread` đang sống có thể gọi lại vào JVM ban đầu. Không cố downcast `RecordedThread` thành `Thread` hay dùng nó để điều khiển thread ở thời điểm phân tích.

## 4. Metadata annotations: tên, nhãn, đơn vị và cách công cụ hiển thị

Các annotations của `jdk.jfr` cung cấp **ngữ nghĩa** cho event type và từng field:

| Annotation | Áp dụng | Ý nghĩa và lưu ý |
| --- | --- | --- |
| `@Name("demo.OrderStep")` | Event type | Tên định danh dùng để lọc; nên có namespace ổn định |
| `@Label("Order Step")` | Type hoặc field | Nhãn dễ đọc, không đổi tên Java field dùng trong getters |
| `@Description("...")` | Type hoặc field | Mô tả mục đích và cách diễn giải |
| `@Category({"Demo", "Orders"})` | Event type | Nhóm phân cấp trong công cụ phân tích |
| `@Timespan(Timespan.MILLISECONDS)` | Field số đo duration | Cho biết giá trị field **đang dùng đơn vị mili-giây** |
| `@DataAmount(DataAmount.BYTES)` | Field kích thước dữ liệu | Cho biết field biểu diễn số **byte** |
| `@Unsigned` | Field số nguyên | Gợi ý cách diễn giải unsigned; **không tự kiểm tra** giá trị bạn gán |
| `@Percentage` | Field số tỷ lệ | Metadata phần trăm/tỷ lệ cho công cụ hiển thị |
| `@Enabled(false)` | Event type | Mặc định type không được bật; recording vẫn có thể bật tường minh |
| `@Threshold("10 ms")` | Event type | Giá trị threshold mặc định; recording có thể override qua settings |
| `@StackTrace(false)` | Event type | Mặc định không lưu stack trace; có thể điều chỉnh bằng recording settings |

**Annotations không tự tính toán đơn vị hoặc giá trị.** Nếu field được khai báo:

```java
@Label("Business Duration")
@Timespan(Timespan.MILLISECONDS)
long businessMillis;

@Label("Payload Size")
@DataAmount(DataAmount.BYTES)
long payloadBytes;
```

thì ứng dụng **phải tự gán** số mili-giây/số byte tương ứng. `@Timespan` không gọi đồng hồ hệ thống để tính duration hộ bạn; `@DataAmount` không tự đo độ dài request body. Những metadata này giúp `jfr print`, JDK Mission Control và API reader **hiểu đơn vị**.

**Phân biệt hai loại thời lượng:**

- **Duration chuẩn của event**, lấy bằng `RecordedEvent.getDuration()`: JFR tính từ `Event.begin()` tới `Event.end()` (hoặc thời điểm `commit()` nếu chưa `end()`).
- **Một field nghiệp vụ `businessMillis`**: do code ứng dụng gán; nó có thể biểu diễn thời gian chờ một service khác, không nhất thiết bằng duration đo bởi JFR cho chính event.

Khi đọc field có `@Timespan`, có thể dùng `RecordedEvent.getDuration("businessMillis")` để JFR diễn giải thành `Duration`; hoặc `getLong("businessMillis")` để nhận giá trị thô. Đừng lấy `event.getDuration()` rồi coi đó là `businessMillis` nếu hai đại lượng không được đo cùng cách.

**Những annotation đó không mã hóa dữ liệu, không bỏ qua dữ liệu nhạy cảm và không quyết định lưu giữ.** Quyết định ghi hay không thuộc về event settings/`commit()` và recording; quyết định giữ lịch sử thuộc về repository/retention.

## 5. Vòng đời của một event: tạo, đo, gán field và `commit()`

Phương thức cốt lõi của `jdk.jfr.Event` là:

| API | Ý nghĩa |
| --- | --- |
| `new MyEvent()` | Tạo object event; chưa phải bản ghi trong `.jfr` |
| `begin()` | Bắt đầu đo thời gian cho event |
| `end()` | Kết thúc khoảng thời gian; phải gọi sau `begin()` |
| `commit()` | Gửi các giá trị field cùng thời gian/duration vào hệ thống JFR |
| `isEnabled()` | `true` nếu có ít nhất một recording đang chạy bật event type |
| `shouldCommit()` | `true` nếu event được bật và duration đạt threshold đang có |
| `set(int,Object)` | **Chỉ dùng với events tạo bằng `EventFactory`**, không dùng làm setter thông thường cho subclass |

Hai lối phát event thường gặp:

**Event tức thời**, khi chỉ cần đánh dấu “đã xảy ra”:

```java
OrderStep e = new OrderStep();
e.stepName = "cache-miss";
e.itemCount = 1;
e.success = true;
e.commit();
```

**Event có duration**, khi muốn đo một bước xử lý:

```java
OrderStep e = new OrderStep();
if (e.isEnabled()) {
    e.begin();
    try {
        performBusinessStep(); // Hàm do ứng dụng định nghĩa.
        e.success = true;
    } catch (RuntimeException ex) {
        e.success = false;
        throw ex;
    } finally {
        e.end();
        if (e.shouldCommit()) {
            e.stepName = "business-step";
            e.commit();
        }
    }
}
```

Hai đoạn trên là **mã minh họa không độc lập** (cần class `OrderStep` và hàm `performBusinessStep()` tương ứng). Đoạn thứ hai dành để giải thích control flow; ứng dụng thật **vẫn phải thực thi business step dù event bị tắt**. Nghĩa là điều kiện `isEnabled()` nên dùng để **bỏ công việc đo đạc/chuẩn bị payload đắt đỏ**, không được vô tình bỏ luôn logic nghiệp vụ. Một dạng triển khai an toàn hơn là chạy nghiệp vụ bên ngoài nhánh kiểm tra, hoặc tạo event luôn nhưng chỉ bật việc thu thập phụ khi cần.

### Cách áp dụng an toàn trong ứng dụng

```java
OrderStep e = new OrderStep();
boolean capture = e.isEnabled();
if (capture) {
    e.begin();
}
try {
    // Nghiệp vụ chính luôn chạy, dù JFR đang bật hay tắt.
    performBusinessStep();
} finally {
    if (capture) {
        e.end();
        if (e.shouldCommit()) {
            e.stepName = "business-step";
            e.commit();
        }
    }
}
```

Đây vẫn là **minh họa**, không có `performBusinessStep`. Nếu muốn ghi cả outcome thành công/thất bại, thêm biến `success` được cập nhật rõ trong `try/catch` thay vì mặc định true. Trong ứng dụng nhiều threads, **không dùng cùng một `Event` object để nhiều thread gán field/commit cạnh tranh**. Thường tạo **một instance cho một thao tác**, rồi gán field và commit trong phạm vi kiểm soát.

### Cẩn thận với điều kiện `shouldCommit()`

`isEnabled()` chỉ xét event có bật bởi recording đang chạy; `shouldCommit()` còn xét threshold/duration. Khi nhiều recordings đồng thời với threshold khác nhau, nó xét ngưỡng áp dụng theo cơ chế JFR; không phải một boolean cam kết event sẽ còn trong **mọi** recording. Chẳng hạn một recording thu event ≥10 ms và recording khác chỉ thu ≥100 ms: một event 20 ms có thể xuất hiện ở recording thứ nhất nhưng không ở recording thứ hai.

Một số event định nghĩa duration rất ngắn; trong demo runnable dưới đây dùng `withThreshold(Duration.ZERO)` để bảo đảm threshold không lọc mất các event thao tác nhanh. Không biến threshold 0 thành mặc định mọi production event: nếu workload phát triệu events/giây, việc bật mọi sự kiện có thể tiêu tốn CPU, memory và disk.

## 6. Ví dụ hoàn chỉnh: custom fields, metadata, recording và đọc lại

Đây là **chương trình Java 11+ chạy độc lập**, không cần Internet. Chương trình cho thấy:

- Dùng `@Name`, `@Label`, `@Description`, `@Category` ở event type và `@Unsigned`/`@DataAmount`/`@Timespan` ở các field.
- Có những field **được ghi**: `String`, `int`, `long`, `boolean`, `Class<?>`, `Thread`.
- Có những field **bị bỏ qua**: `static`, `transient` và `String[]`.
- Tạo hai event riêng dưới một `Recording` có cấu hình bật type/threshold 0.
- Dump file `.jfr`, dùng `RecordingFile` đọc từng `RecordedEvent`, lọc theo tên và lấy giá trị bằng typed getters.
- In kết quả ổn định, không in thời điểm, thread ID hay tên thư mục tạm ngẫu nhiên; dọn tài nguyên qua `try-with-resources` và `finally`.

Lưu tệp **`JfrCustomFieldsDemo.java`**:

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
import jdk.jfr.Unsigned;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrCustomFieldsDemo {
    @Name("demo.OrderStep")
    @Label("Order Step")
    @Description("Records a completed order processing step.")
    @Category({"Demo", "Orders"})
    static class OrderStep extends Event {
        @Label("Step Name") String stepName;
        @Label("Item Count") @Unsigned int itemCount;
        @Label("Payload Size") @DataAmount(DataAmount.BYTES)
        long payloadBytes;
        @Label("Business Duration") @Timespan(Timespan.MILLISECONDS)
        long businessMillis;
        @Label("Succeeded") boolean success;
        @Label("Component Class") Class<?> component;
        @Label("Source Thread") Thread sourceThread;
        transient String transientNote = "not-recorded";
        static String staticNote = "not-recorded";
        String[] unsupportedTags = {"not-recorded"};
    }

    public static void main(String[] args) throws Exception {
        EventType type = EventType.getEventType(OrderStep.class);
        System.out.println("eventType=" + type.getName());
        System.out.println("category=" +
                String.join("/", type.getCategoryNames()));
        System.out.println("hasPayloadField=" +
                (type.getField("payloadBytes") != null));
        System.out.println("timespanAnnotated=" +
                (type.getField("businessMillis")
                        .getAnnotation(Timespan.class) != null));
        System.out.println("hasTransientField=" +
                (type.getField("transientNote") != null));
        System.out.println("hasStaticField=" +
                (type.getField("staticNote") != null));
        System.out.println("hasArrayField=" +
                (type.getField("unsupportedTags") != null));

        Path dir = Files.createTempDirectory("jfr-fields-");
        Path output = dir.resolve("events.jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                recording.enable(OrderStep.class)
                        .withThreshold(Duration.ZERO)
                        .withoutStackTrace();
                recording.start();
                System.out.println("enabledDuringRecording=" +
                        new OrderStep().isEnabled());
                for (int i = 1; i <= 2; i++) {
                    OrderStep e = new OrderStep();
                    e.stepName = i == 1 ? "validated" : "charged";
                    e.itemCount = i + 2;
                    e.payloadBytes = i * 256L;
                    e.businessMillis = i * 10L;
                    e.success = true;
                    e.component = JfrCustomFieldsDemo.class;
                    e.sourceThread = Thread.currentThread();
                    e.begin();
                    e.end();
                    if (e.shouldCommit()) {
                        e.commit();
                    }
                }
                recording.stop();
                recording.dump(output);
            }

            Map<String, String> rows = new TreeMap<>();
            try (RecordingFile file = new RecordingFile(output)) {
                while (file.hasMoreEvents()) {
                    RecordedEvent e = file.readEvent();
                    if (!e.getEventType().getName().equals("demo.OrderStep")) {
                        continue;
                    }
                    rows.put(e.getString("stepName"),
                            e.getInt("itemCount") + ":" +
                            e.getLong("payloadBytes") + ":" +
                            e.getLong("businessMillis") + ":" +
                            e.getBoolean("success"));
                }
            }

            System.out.println("recordedEvents=" + rows.size());
            for (Map.Entry<String, String> row : rows.entrySet()) {
                System.out.println(row.getKey() + "=" + row.getValue());
            }
            System.out.println("outputFileExists=" +
                    Files.isRegularFile(output));
        } finally {
            Files.deleteIfExists(output);
            Files.deleteIfExists(dir);
        }
    }
}
```

**Biên dịch/chạy:** cài JDK 17+ hoặc JDK 11 có module `jdk.jfr`; mã được kiểm tra ở API/bytecode Java 11 bằng `--release 11`:

```bash
javac --release 11 JfrCustomFieldsDemo.java
java JfrCustomFieldsDemo
```

**Stdout chính xác** trong môi trường có JFR và quyền ghi thư mục tạm:

```text
eventType=demo.OrderStep
category=Demo/Orders
hasPayloadField=true
timespanAnnotated=true
hasTransientField=false
hasStaticField=false
hasArrayField=false
enabledDuringRecording=true
recordedEvents=2
charged=4:512:20:true
validated=3:256:10:true
outputFileExists=true
```

Chương trình này đã **được biên dịch bằng `javac --release 11` và chạy trên OpenJDK 24**, đúng toàn bộ 12 dòng stdout trên. Nếu JVM build không cung cấp JFR hoặc không có quyền ghi thư mục tạm, chương trình cần môi trường khác; có thể dùng `FlightRecorder.isAvailable()` để kiểm tra JFR có sẵn.

### Đọc output và ý nghĩa của schema

1. `eventType=demo.OrderStep` là **tên định danh `@Name`**, không phải `@Label`.
2. `category=Demo/Orders` thể hiện metadata phân cấp từ `@Category`.
3. `hasPayloadField=true` và `timespanAnnotated=true` chứng minh `EventType.getField(...)` tìm thấy mô tả field được hỗ trợ, kèm annotation đơn vị.
4. `hasTransientField=false`, `hasStaticField=false` và `hasArrayField=false` chứng minh ba field Java vẫn tồn tại nhưng **không nằm trong schema ghi JFR**. Đây là kiểm tra rất có giá trị khi thêm hoặc đổi schema.
5. `enabledDuringRecording=true` cho biết recording đã chạy và bật event type. Nếu không có recording phù hợp, `isEnabled()` có thể là false.
6. `recordedEvents=2`: trong một bài kiểm thử tải nhẹ, cả hai instance đã được ghi và xuất. `withThreshold(Duration.ZERO)` tránh lọc do event quá nhanh, `withoutStackTrace()` giảm overhead.
7. Các dòng `charged=...`, `validated=...` là kết quả đọc typed field values. `TreeMap` sắp theo `stepName` cho output ổn định; không suy ra thứ tự vật lý của mọi event từ bảng này.
8. `outputFileExists=true`: `recording.dump(output)` đã xuất file. Đây là **file recording** để đọc, không phải một event instance hoặc repository tạm. File được xóa cuối chương trình để bài demo không để lại dữ liệu.

Lưu ý: chương trình gán `businessMillis=10` hoặc `20` để trình bày đơn vị; **nó không thực sự ngủ 10/20 ms**. Duration chuẩn của JFR từ `begin/end` rất ngắn. Không được nhầm metadata field này với `RecordedEvent.getDuration()`.

### Vì sao dùng `recording.dump(...)` và `RecordingFile`?

`recording.start()` cho phép ghi events; `stop()` kết thúc phiên ghi; `dump(Path)` tạo một file `.jfr` có thể đọc được. `RecordingFile` là API Java 11 cho phép duyệt events **theo luồng từ file**, không cần gom toàn bộ dữ liệu vào bộ nhớ. Mỗi file có thể có các built-in events khác; đoạn code lọc tên `demo.OrderStep` để chỉ tính những event do ứng dụng tự định nghĩa.

Nếu mục tiêu là chạy ví dụ rồi **giữ file để phân tích bằng CLI**, bỏ bước xóa `output` trong `finally` và lưu đúng đường dẫn do bạn quản lý. Với bài demo này, việc dọn file là có chủ ý.

## 7. Truy vấn schema và đọc field theo type

Hai cấp API thường dùng:

- **`EventType`** mô tả schema: `getName()`, `getLabel()`, `getCategoryNames()`, `getDescription()`, `getFields()`, `getField("name")`, `getSettingDescriptors()`.
- **`RecordedEvent`** chứa một instance đã ghi: `getEventType()`, `getStartTime()`, `getEndTime()`, `getDuration()`, `getThread()`, `getStackTrace()`; các getter kế thừa từ `RecordedObject` đọc field có tên.

Bảng ví dụ:

| Cần đọc | API Java 11 | Kiểu kết quả |
| --- | --- | --- |
| Tên type | `event.getEventType().getName()` | `String` |
| Tên bước | `event.getString("stepName")` | `String` |
| Số lượng | `event.getInt("itemCount")` | `int` |
| Số byte | `event.getLong("payloadBytes")` | `long` |
| Kết quả | `event.getBoolean("success")` | `boolean` |
| Duration do JFR đo | `event.getDuration()` | `Duration` |
| Timespan field nghiệp vụ | `event.getDuration("businessMillis")` | `Duration` nếu field có metadata phù hợp |
| Loại Java | `event.getClass("component")` | `RecordedClass` |
| Thread được gán vào field | `event.getThread("sourceThread")` | `RecordedThread` |
| Kiểm tra schema | `event.hasField("stepName")` | `boolean` |

**Không dùng `getValue(...)` rồi ép kiểu Java tùy tiện.** Với field `Class<?>`, giá trị đọc là `RecordedClass`; với `Thread`, là `RecordedThread`. Đối với một số built-in events, field có cấu trúc lồng nhau; `RecordedObject` còn hỗ trợ đường dẫn dấu chấm khi đọc, nhưng schema có thể thay đổi theo JDK. Với custom event do chính bạn định nghĩa, ưu tiên schema/tên field ổn định, có kiểm tra `hasField(...)` khi cần tương thích file từ các version khác.

Mã minh họa trong vòng đọc event:

```java
if (event.hasField("component") && event.getClass("component") != null) {
    String javaClassName = event.getClass("component").getName();
    // Sử dụng javaClassName cho chẩn đoán nếu phù hợp.
}
if (event.hasField("sourceThread") &&
        event.getThread("sourceThread") != null) {
    String threadName = event.getThread("sourceThread").getJavaName();
}
```

Đoạn trên là **minh họa**, cần biến `event` kiểu `RecordedEvent` cùng import liên quan. Khi xử lý dữ liệu nhạy cảm, tránh gửi trực tiếp các tên class, thread hoặc field mang user IDs vào logging public. Và vì JFR lưu snapshot của metadata, giá trị sau khi đọc file không phải reference tới object live.

### Đọc metadata của field

`EventType.getField("businessMillis")` trả một `ValueDescriptor`. Có thể đọc `getName()`, `getTypeName()`, `getLabel()` và `getAnnotation(Timespan.class)` để hiểu schema/đơn vị. Không nhất thiết phải có nhãn ở mọi field; cần xử lý khả năng `getLabel() == null`. `getField(...)` cũng trả null nếu field không tồn tại; **đừng gọi `.getTypeName()` ngay trên kết quả chưa kiểm tra**.

`EventType.getFields()` có thể bao gồm cả các trường chuẩn phục vụ JFR (timestamp, duration, thread...) bên cạnh fields do bạn khai báo; **đừng khẳng định số fields bằng số field trong source code**. Tốt hơn hãy kiểm tra sự tồn tại và type của những fields mà hệ thống quan tâm.

## 8. Event động bằng `EventFactory` và `Event.set(index, value)`

Khi **schema chỉ biết ở runtime** (ví dụ plugin tạo event type khác nhau), Java 11 có `jdk.jfr.EventFactory`. API tạo event type từ danh sách **`ValueDescriptor`** và **`AnnotationElement`**. Kiểu event được tạo có thể instantiate qua `newEvent()` và gán dữ liệu bằng `Event.set(index,Object)`.

Ví dụ Java 11 **độc lập**, không cần recording (dùng để minh họa schema; `commit()` khi không có recording phù hợp không nhất thiết tạo bản ghi):

Lưu tệp **`JfrDynamicEventDemo.java`**:

```java
import java.util.Arrays;
import jdk.jfr.AnnotationElement;
import jdk.jfr.Event;
import jdk.jfr.EventFactory;
import jdk.jfr.Name;
import jdk.jfr.ValueDescriptor;

public class JfrDynamicEventDemo {
    public static void main(String[] args) {
        EventFactory factory = EventFactory.create(
                Arrays.asList(
                    new AnnotationElement(Name.class, "demo.RuntimeStep")),
                Arrays.asList(
                    new ValueDescriptor(String.class, "phase"),
                    new ValueDescriptor(int.class, "items")));
        try {
            Event event = factory.newEvent();
            event.set(0, "runtime");
            event.set(1, 7);
            event.commit();
            System.out.println("dynamicEventType=" +
                    factory.getEventType().getName());
            System.out.println("customFields=" +
                    (factory.getEventType().getField("phase") != null &&
                     factory.getEventType().getField("items") != null));
        } finally {
            factory.unregister();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 11 JfrDynamicEventDemo.java
java JfrDynamicEventDemo
```

**Stdout chính xác:**

```text
dynamicEventType=demo.RuntimeStep
customFields=true
```

Ví dụ đã **biên dịch và chạy trên OpenJDK 24 với target Java 11**, đúng output. Các **chỉ số 0 và 1** trong `event.set(...)` khớp **thứ tự `ValueDescriptor` lúc tạo EventFactory**; chúng không phải chỉ số trong `EventType.getFields()` sau khi JFR bổ sung built-in fields.

**Chỉ dùng `Event.set(int,Object)` cho instance do `EventFactory` tạo.** Nếu gọi nó trên một subclass `extends Event` thông thường, API có thể ném `UnsupportedOperationException`. Với schema được biết từ source, nên dùng field assignment như `event.stepName = "validated"` vì rõ, type-safe và thường tối ưu hơn.

`factory.unregister()` hủy đăng ký event type động khi không còn cần dùng; không phải thao tác xóa vĩnh viễn các events đã được ghi trong file `.jfr`. Đừng tạo hàng ngàn event types mới trên mỗi request nếu chỉ khác **giá trị field**; thông thường một type ổn định và nhiều instances rẻ/dễ phân tích hơn.

## 9. Thiết kế trường dữ liệu hữu ích, ít overhead và không rò bí mật

Custom events tốt thường có schema **nhỏ, ổn định và có ý nghĩa chẩn đoán**:

| Nhu cầu | Field gợi ý | Vì sao |
| --- | --- | --- |
| Phân biệt bước nghiệp vụ | `String operation` (giá trị nhóm cố định) | Dễ filter/aggregate |
| Phân biệt kết quả | `boolean success` hoặc `int statusCode` | Dễ so sánh tỉ lệ lỗi |
| Số lượng | `int itemCount` | Không phải biến object thành chuỗi |
| Kích thước request/response | `@DataAmount long bytes` | Công cụ hiểu đơn vị |
| Thời gian thao tác | `@Timespan long elapsedNanos` | Phân biệt thời lượng nghiệp vụ với duration JFR chuẩn |
| Thành phần Java | `Class<?> component` | Định danh nơi xử lý khi có ích |
| Thread liên quan | `Thread sourceThread` | JFR có thể lưu thread metadata; cân nhắc overhead |

**Những điều nên tránh:**

- Không ghi **mật khẩu, access token, session token, API key, dữ liệu thẻ thanh toán, thông tin sức khỏe hoặc nội dung request riêng tư** vào field. File `.jfr` và công cụ phân tích có thể làm thông tin lan ra.
- Không ghi nguyên request/response body; chọn **byte count, status, loại thao tác, timing** và mã lỗi đã chuẩn hóa.
- Không biến mọi object thành `toString()`. Cách này vừa khó phân tích, vừa có thể ném lỗi hoặc chứa bí mật.
- Tránh chuỗi có **cardinality quá cao** như raw UUID của từng request nếu mục tiêu là tổng hợp; nếu cần correlation ID, phải có chính sách giảm nhạy cảm, retention và quyền truy cập.
- Không tính payload nặng chỉ để commit một event đã bị tắt/dưới threshold: dùng `isEnabled()` trước phần đo đạc phụ và `shouldCommit()` trước khi tính metadata tốn kém.
- Dùng `withoutStackTrace()` hoặc cấu hình threshold hợp lý khi stack traces của từng event không cần cho chẩn đoán; dữ liệu stack có thể tăng chi phí.
- Định nghĩa **units** và semantics chính xác bằng annotations. Đừng gán mili-giây vào field có `@Timespan(NANOSECONDS)`.
- Dùng tên type và tên field ổn định khi công cụ hậu xử lý phụ thuộc vào schema; thay tên field có thể khiến truy vấn file lịch sử lỗi.

### Quan hệ với thread và xử lý bất đồng bộ

Nếu một tác vụ bắt đầu ở thread A và kết thúc ở thread B, hãy thiết kế cách chuyển thông tin đo lường/chủ sở hữu event rõ ràng; không gán state vào cùng một `Event` instance từ nhiều thread **đồng thời** mà thiếu đồng bộ. JFR có thể lưu thread của lúc commit và field `Thread` do ứng dụng gán, nhưng **hai thông tin này có thể khác nhau**; phân biệt chúng trong phân tích.

Đừng đo performance bằng cách log thời gian tường từng microsecond rồi khẳng định JFR luôn giữ mọi event và mọi giá trị chính xác. Sự kiện được thu theo settings và điều kiện thực tế; time/sampling/flush đều có chi phí và hạn chế. Với workload quan trọng, nên benchmark overhead trước/sau khi bật event có stack traces.

### Quản lý output file

- `Recording.setToDisk(true)` cho phép JFR ghi chunk vào repository tạm; không có nghĩa mỗi commit đã thành một file riêng.
- `Recording.dump(Path)` xuất một file `.jfr` có thể lưu/phân tích; `close()` giải phóng dữ liệu recording.
- Cấu hình `maxage/maxsize` và dọn file output theo policy để tránh đầy đĩa.
- Kiểm soát quyền đọc và thời hạn lưu file JFR; ngay cả field không phải secret cũng có thể làm lộ tên hệ thống và topology qua metadata.
- JFR **không thay thế** durable tracing/logging nếu yêu cầu giữ mọi event hoặc tìm kiếm phân tán theo thời gian thực.

## 10. Kiểm thử custom event có hệ thống

Khi một team bổ sung event mới, kiểm tra **cả schema lẫn dữ liệu thực**:

1. **Schema check:** `EventType.getEventType(MyEvent.class)` phải có đúng tên, label/category và các fields cần thiết. Kiểm tra field bị đánh dấu `static`/`transient`/unsupported không bị ghi.
2. **Settings:** bật event trong một `Recording` test và đặt `threshold=0`. Nếu cần kiểm thử threshold, tạo riêng kịch bản duration ngắn/dài; đừng trộn vào bài kiểm thử schema.
3. **Lifecycle:** `start()` trước khi commit, `stop()` và `dump()` trước khi `close()`. Kiểm tra file được tạo và đọc được.
4. **Round-trip:** lọc `RecordedEvent` theo `getEventType().getName()`; kiểm tra typed field values. Đừng giả định file không có built-in events.
5. **Metadata units:** kiểm tra `ValueDescriptor.getAnnotation(Timespan.class)` / `DataAmount` nếu công cụ phân tích dựa trên đơn vị.
6. **Độc lập môi trường:** không assert duration nanosecond, thread IDs, event type ID, file size hoặc thứ tự events ngoài những điều đã được ứng dụng kiểm soát.
7. **Cleanup:** đóng `Recording`/`RecordingFile` qua `try-with-resources` và xóa file test đã tạo.
8. **Khả dụng:** CI/JVM phải hỗ trợ JFR và quyền ghi file. Nếu môi trường cấm, tách bài test logic khỏi integration test JFR; không kết luận API sai chỉ vì thiếu quyền file tạm.

**Đọc file bằng CLI** sau khi giữ lại output:

```bash
jfr summary events.jfr
jfr print --events demo.OrderStep events.jfr
jfr metadata events.jfr
```

Đây là lệnh minh họa, `events.jfr` phải nằm ở thư mục làm việc hiện tại hoặc thay bằng path thật. `jfr print` có thể hiển thị nhãn/đơn vị, thời điểm và fields; format output phụ thuộc công cụ/JDK, nên không sao chép một mẫu CLI stdout giả làm kết quả ổn định.

## 11. Những lỗi thường gặp

| Sai lầm | Vì sao nguy hiểm/sai | Cách sửa |
| --- | --- | --- |
| Chỉ định nghĩa `extends Event` rồi tưởng JFR tự ghi | Chưa có instance và `commit()` | Tạo, gán field, commit khi recording bật |
| Nghĩ `commit()` luôn làm event xuất hiện trong file | Có thể bị tắt, dưới threshold, mất do buffer/retention | Kiểm tra settings và round-trip file |
| Dùng `String[]`, enum, `Map` làm JFR payload | Kiểu không được hỗ trợ, có thể bị bỏ qua im lặng | Chuyển thành primitive/String/Thread/Class fields có ý nghĩa |
| Đặt dữ liệu quan trọng trong `static`/`transient` | Hai loại field không được ghi | Dùng instance fields hợp lệ |
| Nghĩ `@Label` đổi tên field để đọc | Label chỉ là metadata hiển thị | Getter dùng tên Java field như `"stepName"` |
| Nghĩ `@Timespan` tự đo thời gian | Chỉ gắn đơn vị | Tự gán số đúng đơn vị; `Event.begin/end` đo duration chuẩn |
| Nghĩ `@Unsigned` làm Java `int` không thể âm | Chỉ là metadata/diễn giải | Validate giá trị theo domain logic |
| Gọi `event.set(0,x)` trên subclass tĩnh | API dành cho event do `EventFactory` tạo | Gán trực tiếp field ở subclass |
| Đọc `RecordedEvent.getClass("x")` và ép sang `Class<?>` | JFR trả `RecordedClass` | Dùng `RecordedClass.getName()` |
| Nhầm `getDuration()` với `getDuration("field")` | Một cái duration chuẩn của event, một cái field timespan | Chọn API đúng đại lượng |
| Bật mọi custom event với threshold 0 trên luồng nóng | Gây overhead/dung lượng lớn | Chọn threshold/stack trace/settings theo mục tiêu |
| Thu thập payload nặng rồi mới kiểm tra `isEnabled()` | Lãng phí CPU khi recorder không cần dữ liệu | Kiểm tra sớm; `shouldCommit()` trước phần field tốn kém |
| Đưa token, raw payload/PII vào event | File JFR có thể bị copy/đọc bởi người khác | Giảm nhạy cảm, giữ schema tối thiểu |
| Assert chính xác số byte file, event duration hoặc event type ID | Phụ thuộc JDK, tốc độ ghi, môi trường | Assert schema/type và giá trị field do test tự gán |
| Gọi `close()` trước `dump()` rồi mong file tồn tại | Đã giải phóng dữ liệu recording | Dump trước khi close |
| Tạo `EventFactory` type mới cho mỗi request | Phát sinh metadata/types không cần thiết | Dùng một event type với field values thay đổi |

## 12. Câu hỏi tự kiểm tra

**Câu 1:** `@Name("demo.OrderStep")`, `@Label("Order Step")` và Java field `stepName` khác nhau ở đâu?

**Đáp án:** `@Name` đặt định danh event type để lọc; `@Label` là nhãn người đọc; `stepName` là tên field để `RecordedEvent.getString("stepName")` lấy giá trị.

**Câu 2:** Các field `String[] tags` và `transient String temp` có xuất hiện trong schema JFR Java 11 không?

**Đáp án:** Không. Array không thuộc nhóm kiểu field được hỗ trợ; transient fields bị loại dù kiểu `String` vốn hỗ trợ.

**Câu 3:** `Event.commit()` có chắc chắn làm event thành một bản ghi tồn tại trong file không?

**Đáp án:** Không. Event phải được bật, thỏa threshold, recording chạy và dữ liệu còn được lưu/được dump.

**Câu 4:** `isEnabled()` và `shouldCommit()` có giống nhau không?

**Đáp án:** Không. `isEnabled()` xét có recording bật event type; `shouldCommit()` còn xét duration/threshold. Dùng chúng để tránh instrumentation tốn kém không cần thiết.

**Câu 5:** Nếu field `businessMillis=20` có `@Timespan(MILLISECONDS)`, `RecordedEvent.getDuration()` có bắt buộc là 20 ms không?

**Đáp án:** Không. `getDuration()` là duration chuẩn từ `begin/end`; `businessMillis` là field ứng dụng tự gán. Có thể đọc field riêng qua `getLong("businessMillis")` hoặc `getDuration("businessMillis")`.

**Câu 6:** Vì sao `getThread("sourceThread")` không thể trả lại object `Thread` cũ để bạn gọi `interrupt()`?

**Đáp án:** File recording chứa metadata/snapshot đã ghi; API reader trả `RecordedThread` để phân tích, không phải live thread của tiến trình gốc.

**Câu 7:** `Event.set(1, 7)` dùng trong hoàn cảnh nào?

**Đáp án:** Chỉ khi event được `EventFactory.newEvent()` tạo từ schema động, với index tương ứng thứ tự `ValueDescriptor` lúc tạo factory. Với subclass tĩnh, gán field trực tiếp.

**Câu 8:** Vì sao test không nên khẳng định thời gian `Event.getDuration()` luôn chính xác một số nano/milli-giây cố định?

**Đáp án:** Scheduling, VM và workload làm thời gian thực tế biến động. Cần kiểm tra giá trị ứng dụng chủ động gán và ràng buộc có ý nghĩa, thay vì một duration tuyệt đối.

**Ghi nhớ:** Custom JFR event trong Java 11+ là một **class `extends Event` với các instance fields thuộc kiểu được hỗ trợ**; annotations mô tả name/label/category/units; `begin/end` đo duration; `commit` đề nghị ghi. Khi cần, `isEnabled/shouldCommit` giảm overhead; `Recording` bật event và xuất `.jfr`, `RecordingFile` đọc `RecordedEvent`. Chỉ 8 primitive types cùng `String`, `Thread`, `Class` được hỗ trợ trực tiếp; các array/enum/object khác, `static` và `transient` không thành field JFR. Dùng `EventFactory` chỉ khi phải định nghĩa schema động, và luôn bảo vệ dữ liệu nhạy cảm.

**Tài liệu chính thức (API vẫn còn hiệu lực):** [Java SE 11 — jdk.jfr.Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html); [Java SE 11 — package jdk.jfr](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html); [Java SE 11 — EventType](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventType.html); [Java SE 11 — EventFactory](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventFactory.html); [Java SE 11 — RecordedObject](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html); [Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html); [Java SE 25 — Event](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Event.html); [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328).
