# JFR API: `@Name`, `@Label`, `@Description` và `@Category` (Java 11)

## 1. Mục tiêu bài học

**JDK Flight Recorder (JFR)** thu thập các sự kiện (*events*) có cấu trúc từ JVM, JDK và ứng dụng. Khi bạn tự tạo event bằng cách kế thừa `jdk.jfr.Event`, những field Java chỉ nói lên **dữ liệu**; để công cụ phân tích hiểu **sự kiện là gì, được hiển thị ra sao và thuộc nhóm nào**, JFR cung cấp các annotation metadata như **`@Name`, `@Label`, `@Description`, `@Category`**.

Bốn annotation này phục vụ những nhu cầu khác nhau:

- **`@Name`:** định danh có cấu trúc để cấu hình, lọc và đọc event ổn định qua nhiều lần build.
- **`@Label`:** tên dễ đọc, hiển thị cho người vận hành trong công cụ JFR.
- **`@Description`:** giải thích ý nghĩa nghiệp vụ/kỹ thuật và cách diễn giải event hoặc field.
- **`@Category`:** đường dẫn nhóm nhiều cấp để sắp xếp event trong giao diện phân tích.

Từ **Java 11**, các annotation này đều thuộc module **`jdk.jfr`**. Đây là API JFR còn được sử dụng trên các JDK hiện đại, không phải workaround dành cho công nghệ đã lỗi thời.

Sau bài học, bạn có thể:

1. Khai báo đủ bốn annotation trên một custom JFR event, áp annotation lên field phù hợp.
2. Phân biệt **định danh event** với **nhãn hiển thị**, **mô tả** và **nhóm trong công cụ**.
3. Hiểu vì sao đổi `@Name` có thể làm hỏng filter, cấu hình `.jfc` và consumer, trong khi đổi `@Label` thường chỉ ảnh hưởng cách trình bày.
4. Dùng `EventType` và `ValueDescriptor` để xác minh metadata bằng API Java 11.
5. Ghi event thật vào `Recording` rồi dùng `RecordingFile` kiểm tra event name và tên field đã được `@Name` đổi.
6. Thiết kế một taxonomy event dễ mở rộng, chi phí hợp lý và tránh đưa secret/dữ liệu cá nhân vào event.
7. Phân biệt metadata annotation với những cơ chế khác như `@Enabled`, `@Threshold`, `@StackTrace` hay `Recording.enable`.

**Phạm vi trực tiếp:** bốn annotation metadata trong Java 11. Bài có một chương trình chạy độc lập và các ví dụ minh họa việc đặt tên, phân loại, tương thích schema và vận hành. JFR Event Streaming API (`RecordingStream`) chỉ ra đời từ JDK 14; bài dùng `Recording`/`RecordingFile` có sẵn ở Java 11.

## 2. Mô hình event và metadata trong JFR

Trong Java, một custom JFR event thường được khai báo như sau:

```java
import jdk.jfr.*;

@Name("com.example.orders.Operation")
@Label("Order Operation")
@Description("Measures a synthetic order operation")
@Category({"Application", "Orders"})
class OrderOperation extends Event {
    @Label("Processed Units")
    public int units;

    @Label("Outcome")
    public String outcome;
}
```

Đây là **trích đoạn khai báo class**, không có `main`; muốn ghi sự kiện cần tạo đối tượng, gán field, gọi `commit()` trong khi recording phù hợp đang chạy. Annotation gắn **metadata cố định của event type** chứ không thay thế việc ghi giá trị cụ thể của một event instance.

Có ba tầng cần hiểu:

| Tầng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Event type** | `com.example.orders.Operation` | Định nghĩa chung: tên, nhãn, category, field schema, settings |
| **Event instance** | Một lần `new OrderOperation().commit()` | Một bản ghi có thời gian, thread, field values |
| **Recording** | `Recording.enable(OrderOperation.class)` | Quyết định khi nào/những event nào thực sự được lưu |

Cùng một `EventType` có thể sinh hàng nghìn `RecordedEvent` khác nhau. Các instance **không có nhãn riêng tùy biến theo từng request**: nhãn và nhóm là metadata được khai báo trên **type**, còn field values có thể thay đổi theo từng lần phát sự kiện.

Ví dụ một event type có:

```text
Name        = com.example.orders.Operation
Label       = Order Operation
Description = Measures a synthetic order operation
Category    = Application / Orders
Field       = units (int), outcome (String)
```

Một instance có thể có `units=2` và `outcome="OK"`, instance khác `units=5` và `outcome="RETRY"`. Không tạo mỗi user/order một event type riêng chỉ để có tên hiển thị động; dùng cùng schema và **field có giá trị an toàn**.

## 3. Bảng so sánh bốn annotation

| Annotation | Target Java 11 | Kiểu đối số | Vai trò | API để đọc |
| --- | --- | --- | --- | --- |
| `@Name` | `TYPE`, `FIELD`, `METHOD` | `String` | Định danh kỹ thuật của event/field/setting | `EventType.getName()`; `ValueDescriptor.getName()` |
| `@Label` | `TYPE`, `FIELD`, `METHOD` | `String` | Tên ngắn, dễ đọc trong UI | `EventType.getLabel()`; `ValueDescriptor.getLabel()` |
| `@Description` | `TYPE`, `FIELD`, `METHOD` | `String` | Một hoặc hai câu giải thích ý nghĩa | `EventType.getDescription()`; `ValueDescriptor.getDescription()` |
| `@Category` | **`TYPE`** | **`String[]`** | Đường dẫn phân loại event theo cấp | `EventType.getCategoryNames()` |

**Cần phân biệt:** `TYPE/FIELD/METHOD` là phạm vi `@Target` của annotation trong Java SE 11. `@Name`, `@Label` và `@Description` dùng được cho event type và event fields; `METHOD` chủ yếu hữu ích khi định nghĩa event settings bằng cơ chế phù hợp như `@SettingDefinition`, **không** có nghĩa JFR tự biến một method Java bất kỳ thành field.

`@Category` chỉ áp ở **cấp event class**, không phải field. Mã này **không biên dịch**:

```java
class InvalidCategoryEvent extends Event {
    @Category({"Application", "Orders"}) // Sai target: FIELD.
    public int units;
}
```

Đây là **mẫu lỗi để nhận diện**, không chạy. Với trường `units`, nếu cần văn bản rõ nghĩa hãy dùng `@Label` và `@Description`; nếu cần thể hiện đơn vị đo còn có annotation khác như `@DataAmount`/`@Timespan` tùy kiểu dữ liệu.

### Metadata không phải quy tắc bảo mật hoặc filtering

- `@Name` **không** cho phép/từ chối quyền xem.
- `@Label` **không** biến `outcome="OK"` thành secret-safe.
- `@Description` **không** validate field values.
- `@Category` **không** giới hạn event frequency, độ dài field, tốc độ ghi hay quyền đọc file `.jfr`.
- Muốn bật/tắt/ngưỡng ghi, dùng `Recording`/`EventSettings` và các annotation settings tương ứng.
- Muốn bảo vệ dữ liệu, **thiết kế schema allowlist** và kiểm soát truy cập/retention file JFR.

## 4. `@Name`: định danh kỹ thuật cần ổn định

### 4.1. Gắn trên event class

```java
@Name("com.example.orders.Operation")
public static class OrderOperation extends Event {
    public int units;
}
```

Đây là **trích đoạn lớp lồng** (đặt trong một lớp Java khác), không phải file chạy độc lập. Chuỗi `"com.example.orders.Operation"` là **event type name**. Nó giúp người vận hành, `jfr print`, JFR configuration và các consumer lọc chính xác loại event cần quan sát.

Trong Java SE 11, `@Name` phải là một tên hợp lệ theo quy tắc identifier Java tương ứng: với event class, có thể là tên gồm các thành phần phân tách bằng dấu chấm; với field hoặc event setting, là identifier hợp lệ. Ví dụ hợp lệ:

```text
com.example.orders.Operation
com.example.storage.FileSync
com.example.http.ClientCall
```

Những chuỗi sau **không nên dùng** làm `@Name`:

```text
Order Operation      (chứa khoảng trắng)
Application / Orders (dạng đường dẫn hiển thị, không phải identifier)
request?id=123       (giá trị biến đổi theo request)
HTTP-Call            (dấu '-' không phải ký tự identifier Java hợp lệ)
```

Tên event nên **ổn định, ngắn, có namespace**, không chứa ID người dùng, URL, token, random UUID hoặc timestamp. `@Name` cũng không phải một kênh localization: bản địa hóa trình bày thì dùng `@Label`/`@Description`, **đừng** biến định danh thành chuỗi dịch.

Nếu **không** có `@Name`, tên event mặc định đến từ **fully qualified Java class name**. Điều đó phù hợp lúc thử nghiệm, nhưng việc đổi package/refactor tên class có thể đổi event ID. Dùng `@Name` ổn định cho event được consumer/config ngoài source code sử dụng.

### 4.2. `@Name` trên field thay đổi tên ở bản ghi

```java
@Name("units")
@Label("Processed Units")
@Description("Number of synthetic units processed")
int processedUnits;
```

Đây là **trích đoạn field trong lớp `extends Event`**. Trong Java source bạn gán:

```java
event.processedUnits = 3;
```

Nhưng trong **JFR schema** field được lưu dưới tên `units`. Consumer đọc:

```java
RecordedEvent recorded = /* event đã đọc từ RecordingFile */;
int count = recorded.getInt("units");
```

Đây là **trích đoạn**, không phải chương trình tự chạy. Không gọi `recorded.getInt("processedUnits")` chỉ vì Java field mang tên ấy; `@Name("units")` đã thay đổi **JFR field name**. Ví dụ chạy đầy đủ ở mục 8 kiểm chứng trực tiếp điểm này.

**Hệ quả khi đổi tên field:** nếu đã xuất recording và tool/report đọc field `units`, đổi `@Name("units")` thành `@Name("quantity")` là thay đổi **schema**. Nếu cần tương thích dữ liệu cũ, cần versioning/migration consumer hoặc hỗ trợ cả hai schema. Đổi `@Label("Processed Units")` thành `@Label("Units Processed")` thường không buộc code đọc field đổi tên.

### 4.3. Tên event liên quan `.jfc` và cấu hình

JFR setting key thường có dạng:

```text
<event-name>#<setting-name>
```

Ví dụ event name cố định:

```text
com.example.orders.Operation#enabled
com.example.orders.Operation#threshold
com.example.orders.Operation#stackTrace
```

Một `Recording` có thể enable trực tiếp theo class hoặc name:

```java
recording.enable(OrderOperation.class).withoutThreshold();
recording.enable("com.example.orders.Operation").withoutStackTrace();
```

Đây là **hai trích đoạn lựa chọn**, trong thực tế bạn có thể kết hợp setting trên **cùng một instance EventSettings**, không cần gọi enable hai lần chỉ để chứng minh nguyên tắc. Sự khác biệt: dùng class reference thuận tiện trong code biên dịch cùng event; dùng **tên ổn định** phù hợp khi cấu hình ngoài source, trong `.jfc`, CLI hoặc consumer cần lựa chọn theo type name.

**Không coi `EventType.getId()` là định danh ổn định qua JVM restart**: ID này là định danh trong một JVM instance. Nếu cần filter/persist contract qua lần triển khai, ưu tiên `EventType.getName()` đã thiết kế ổn định. Khi nhiều classloader cùng định nghĩa một event type name, cần giải quyết việc phân biệt schema/ID theo điều kiện runtime; không tự cho rằng chỉ chuỗi name là đủ để tránh collision.

## 5. `@Label`: văn bản hiển thị, không phải định danh

### 5.1. Trên event class

```java
@Name("com.example.orders.Operation")
@Label("Order Operation")
class OrderOperation extends Event {
}
```

`@Label` định nghĩa **human-readable name**. Oracle Java 11 hướng dẫn dùng kiểu viết **headline-style capitalization** cho nhãn và không thêm dấu câu cuối. Ví dụ:

- `Order Operation`
- `Processed Units`
- `Socket Read Duration`
- `Request Outcome`

Nhãn thường ngắn, thuận lợi để JDK Mission Control hoặc các công cụ JFR hiển thị danh sách sự kiện, biểu đồ và lời giải thích bên cạnh dữ liệu.

Một nhãn `Order Operation` **không** thay thế định danh `com.example.orders.Operation`. Vì thế đừng lọc sự kiện bằng label khi `getName()` có sẵn.

### 5.2. Trên field

```java
@Label("Processed Units")
public int units;
```

Trong source, field tên `units`; JFR schema cũng tên `units` nếu không có `@Name` khác; nhãn giúp người dùng hiểu đó là **số đơn vị đã xử lý**, chứ không chỉ một biến `units` chung chung.

Khi hệ thống mở rộng sang nhiều nhóm vận hành, nhãn phải dễ hiểu **mà không cần đọc code Java**. Tuy nhiên, label nên đủ ngắn để không lấn bảng và không chứa dữ liệu biến động như ID request.

**Đổi label có an toàn?** Thường an toàn cho consumer sử dụng `EventType.getName()` và `ValueDescriptor.getName()`, nhưng vẫn có thể ảnh hưởng dashboard/rule nào đang dựa vào text hiển thị. Hãy kiểm tra dependency trước khi thay metadata trong thư viện dùng chung.

### 5.3. `@Label` không phải bản dịch động theo locale

`@Label("Order Operation")` được khai báo cố định trong classfile. Nó **không tự bản địa hóa** theo ngôn ngữ của người xem, không thay theo user locale và không sinh thêm event type theo quốc gia. Công cụ hiển thị có thể có logic trình bày riêng, nhưng đừng thiết kế contract dựa trên một hành vi localization JFR chưa xác nhận.

## 6. `@Description`: giải thích ý nghĩa và đơn vị của dữ liệu

`@Description` cung cấp **một hoặc hai câu mô tả** event/field để người đọc phân tích hiểu **event đo gì, khi nào được tạo, field đại diện cho cái gì**.

Trên event:

```java
@Description("Measures a synthetic order operation")
class OrderOperation extends Event {
}
```

Trên field:

```java
@Description("Number of synthetic units processed")
public int units;
```

Oracle Java 11 khuyên viết theo **sentence-style capitalization** và nếu chỉ một câu thì không cần dấu chấm cuối. Mô tả cần chính xác nhưng không nên biến thành một bài hướng dẫn quá dài.

### 6.1. Description tốt nên trả lời câu hỏi nào?

- Event thể hiện **thời điểm** hay **duration**?
- Nó xảy ra khi **bắt đầu**, **kết thúc** hay **đạt một điều kiện**?
- `units` đếm **item**, **byte**, **request** hay **lần thử**?
- `duration` đo từ lúc chờ queue hay chỉ thời gian chạy phương thức?
- `resultCode` có thể có những giá trị cố định nào?
- Có **threshold**/sampling khiến một số event bị bỏ qua không?
- Các giá trị có phải là **metadata giả lập**, không phải dữ liệu nghiệp vụ nhạy cảm?

Ví dụ mô tả rõ hơn:

```java
@Description(
    "Measures time spent processing a synthetic batch after dequeue")
class BatchProcessing extends Event {
    @Description("Number of items handled by this batch")
    public int itemCount;
}
```

Đây là **trích đoạn**, có thể kèm `@Name`, `@Label` và `@Category` khi tích hợp thật.

### 6.2. Description không thay đơn vị đo có kiểu

Mặc dù mô tả `"Elapsed duration in milliseconds"` giúp người đọc, JFR còn cung cấp các annotation metadata chuyên biệt như `@Timespan`, `@Timestamp`, `@DataAmount`, `@Percentage` cho những kiểu field phù hợp. Khi đã có metadata kiểu/đơn vị chính xác, công cụ có thể hiển thị tốt hơn. Không dùng `@Description` để “đánh lừa” parser rằng một `String` chứa `"12ms"` là duration number.

Mô tả phải đúng với cách code tạo data. Nếu `units` thực tế là số item **được yêu cầu** chứ không phải **đã xử lý**, mô tả `"Number of ... processed"` là sai, dù chương trình vẫn biên dịch và ghi được event.

### 6.3. Description không được chứa bí mật

Annotation tồn tại trong metadata, có thể được đọc bởi JFR tools và phân phối theo classfile/recording. Đừng đưa URL nội bộ chứa credential, private key, token, thông tin khách hàng, connection string có mật khẩu hoặc ID phiên cụ thể vào `@Description`. Chỉ nên mô tả **ý nghĩa field**, không đưa **giá trị dữ liệu thực**.

## 7. `@Category`: sắp xếp event theo đường dẫn nhóm

`@Category` của Java 11 là annotation dành cho **event TYPE**, có đối số **`String[]`** theo thứ tự từ gốc đến cấp con:

```java
@Category({"Application", "Orders"})
class OrderOperation extends Event {
}
```

Tại runtime:

```java
EventType type = EventType.getEventType(OrderOperation.class);
String path = String.join(" / ", type.getCategoryNames());
```

Kết quả tương ứng: `Application / Orders`.

### 7.1. Mỗi phần tử mảng là một cấp

Ví dụ các nhóm:

```java
@Category({"Application", "Orders"})
class OrderOperation extends Event {}

@Category({"Application", "Payments"})
class PaymentOperation extends Event {}

@Category({"Application", "Storage", "Uploads"})
class UploadOperation extends Event {}
```

Đây là các **khai báo trích đoạn** để minh họa taxonomy, không có method `main`.

Công cụ trực quan có thể dựng cây:

```text
Application
├── Orders
│   └── Order Operation
├── Payments
│   └── Payment Operation
└── Storage
    └── Uploads
        └── Upload Operation
```

Không nhầm `@Category({"Application", "Orders"})` với `@Category("Application / Orders")`: trường hợp sau chỉ có **một chuỗi trong một cấp**, nên không đại diện cùng đường dẫn hai phần tử. Java hỗ trợ cú pháp ngắn `@Category("Application")` cho một phần tử mảng, nhưng với nhiều cấp nên viết rõ dấu ngoặc nhọn.

### 7.2. Category hỗ trợ giao diện/timeline, không phải security boundary

Theo Oracle Java 11, category quyết định cách event được trình bày và thường giúp nhóm các event cùng chủ đề trên đồ thị và dạng cây. Khi thiết kế các event **duration lồng nhau**, nên cân nhắc các category tách biệt để tránh việc hiển thị chồng nhau khó hiểu trong một số biểu đồ.

Tuy nhiên:

- Hai event trong cùng category **không** nhất thiết liên quan về class inheritance.
- Category **không** tạo quan hệ cha-con giữa các **event instances** trên timeline.
- Category **không** định nghĩa transaction boundary và **không** quyết định sampling, enabled, threshold hoặc thứ tự recording.
- Category **không** ngăn user có quyền xem recording đọc các event khác.
- Category **không** phải cách nhận diện duy nhất một event khi đọc `RecordedEvent`.

Nếu không chỉ định category, Java 11 `EventType.getCategoryNames()` trả danh sách gồm `"Uncategorized"`. Đây là **trạng thái mặc định cho trình bày**, không phải lỗi ghi event.

### 7.3. Thiết kế taxonomy bền vững

Một mô hình dễ quản lý:

```text
Application / HTTP
Application / Orders
Application / Storage
Application / Background Jobs
```

Nên dùng một vài nhóm **ổn định theo lĩnh vực kỹ thuật/nghiệp vụ**, không dùng category theo:

- Mỗi user ID, email hoặc session ID.
- Mỗi URL với query string.
- Mỗi tên file chứa thông tin nhạy cảm.
- Mỗi lần retry, request ID hoặc timestamp.
- Mỗi node/pod thay đổi liên tục trong hạ tầng.

**Phân nhóm cho người xem** và **định danh máy đọc** là hai việc khác nhau. Nếu cần đổi category để cải thiện JMC visualization, giữ `@Name` nếu consumer vẫn phụ thuộc vào event ID.

## 8. Chương trình Java 11 hoàn chỉnh: kiểm tra đủ bốn annotation và đọc file JFR

Chương trình dưới đây sử dụng **tất cả bốn annotation**, bao gồm `@Name` trên event **và** trên field. Nó:

1. Đọc metadata bằng `EventType.getEventType(...)` và `ValueDescriptor`.
2. Tạo một `Recording` chỉ bật custom event được quan tâm.
3. Ghi hai event dùng **dữ liệu tổng hợp**.
4. Dừng recording, dump ra file `.jfr` tạm.
5. Đọc từng `RecordedEvent` bằng `RecordingFile`, filter theo event name và field name **`"units"`**.
6. Đối chiếu số event và tổng đơn vị, rồi xóa file tạm.

**Ví dụ đã được biên dịch với `javac --release 11` và chạy trên OpenJDK 24**. Nó không cần server/network, không in timestamp, đường dẫn hay secret.

Tạo file **`JfrEventMetadataDemo.java`**:

```java
import jdk.jfr.*;
import jdk.jfr.consumer.*;
import java.nio.file.*;

public class JfrEventMetadataDemo {
    @Name("com.example.orders.Operation")
    @Label("Order Operation")
    @Description("Measures a synthetic order operation")
    @Category({"Application", "Orders"})
    static class OrderOperation extends Event {
        @Name("units")
        @Label("Processed Units")
        @Description("Number of synthetic units processed")
        int processedUnits;

        @Label("Outcome")
        @Description("Safe outcome code")
        String outcome;
    }

    public static void main(String[] args) throws Exception {
        if (!FlightRecorder.isAvailable()) {
            System.out.println("jfr_available=false");
            return;
        }

        EventType type = EventType.getEventType(OrderOperation.class);
        ValueDescriptor units = type.getField("units");
        if (units == null) {
            throw new AssertionError("Missing units field");
        }

        System.out.println("event_name=" + type.getName());
        System.out.println("event_label=" + type.getLabel());
        System.out.println("event_description=" + type.getDescription());
        System.out.println("event_category="
                + String.join(" / ", type.getCategoryNames()));
        System.out.println("field_name=" + units.getName());
        System.out.println("field_label=" + units.getLabel());
        System.out.println("field_description=" + units.getDescription());

        Path output = Files.createTempFile("jfr-meta-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(OrderOperation.class)
                        .withoutThreshold()
                        .withoutStackTrace();
                recording.start();

                for (int i = 1; i <= 2; i++) {
                    OrderOperation event = new OrderOperation();
                    event.processedUnits = i;
                    event.outcome = "OK";
                    event.commit();
                }

                recording.stop();
                recording.dump(output);
            }

            int count = 0;
            int total = 0;
            try (RecordingFile file = new RecordingFile(output)) {
                while (file.hasMoreEvents()) {
                    RecordedEvent e = file.readEvent();
                    if (!"com.example.orders.Operation".equals(
                            e.getEventType().getName())) {
                        continue;
                    }
                    count++;
                    total += e.getInt("units");
                    if (!"OK".equals(e.getString("outcome"))) {
                        throw new AssertionError("Bad outcome");
                    }
                }
            }
            System.out.println("recorded_events=" + count);
            System.out.println("total_units=" + total);
            System.out.println("verified=" + (count == 2 && total == 3));
        } finally {
            Files.deleteIfExists(output);
        }
    }
}
```

**Biên dịch và chạy:**

```bash
javac --release 11 -encoding UTF-8 JfrEventMetadataDemo.java
java JfrEventMetadataDemo
```

**Output khi module JFR khả dụng (đã đối chiếu thực tế):**

```text
event_name=com.example.orders.Operation
event_label=Order Operation
event_description=Measures a synthetic order operation
event_category=Application / Orders
field_name=units
field_label=Processed Units
field_description=Number of synthetic units processed
recorded_events=2
total_units=3
verified=true
```

Các event chứa `units=1` và `units=2` nên có hai bản ghi, tổng `3`. Chú ý dòng `field_name=units`: ở Java source field tên `processedUnits`, nhưng JFR schema đã nhận `@Name("units")` nên `e.getInt("units")` trả đúng dữ liệu.

### 8.1. Giải thích các API được dùng

| API | Vì sao dùng |
| --- | --- |
| `EventType.getEventType(OrderOperation.class)` | Lấy mô tả một event type đã định nghĩa |
| `EventType.getName()` | Lấy định danh kỹ thuật sau `@Name` |
| `EventType.getLabel()` | Lấy nhãn từ `@Label` |
| `EventType.getDescription()` | Lấy mô tả từ `@Description` |
| `EventType.getCategoryNames()` | Lấy category path thành `List<String>` |
| `EventType.getField("units")` | Lấy field descriptor theo **JFR field name** |
| `ValueDescriptor.getName()/getLabel()/getDescription()` | Đọc metadata field |
| `Recording.enable(OrderOperation.class)` | Bật event này cho recording |
| `withoutThreshold()` | Đảm bảo event demo cực ngắn không bị lọc bởi duration threshold |
| `withoutStackTrace()` | Không ghi stack trace khi chỉ cần kiểm tra metadata/field |
| `Event.commit()` | Gửi giá trị của event instance vào JFR khi đủ điều kiện |
| `Recording.dump(output)` | Xuất recording ra file `.jfr` |
| `RecordingFile.hasMoreEvents()/readEvent()` | Đọc từng event, tránh nạp file lớn một lần |
| `RecordedEvent.getInt("units")` | Đọc giá trị field với tên **đã đổi bởi @Name** |

**Không nhầm metadata của type với field values.** `type.getField("units").getLabel()` trả **`Processed Units`**, còn `e.getInt("units")` trả giá trị của **event instance** là 1 hoặc 2. Một là mô tả schema, một là dữ liệu đo.

### 8.2. Vì sao ví dụ có `FlightRecorder.isAvailable()`?

Code dùng module `jdk.jfr`. Nếu module có mặt nhưng JFR không khả dụng trên runtime, chương trình in `jfr_available=false` và kết thúc. Trong một custom runtime `jlink` **không chứa module `jdk.jfr`**, việc load các lớp import JFR có thể thất bại trước cả guard; muốn chạy ví dụ phải có module phù hợp.

Do metadata/runtime có thể khác giữa JDK vendors, ví dụ ghi rõ cần **môi trường có JFR hoạt động**. Không kỳ vọng kết quả cố định nếu JFR bị tắt, recording thất bại vì quyền/disk hoặc process bị dừng giữa lúc ghi.

### 8.3. Vì sao `try-with-resources` và file tạm?

`Recording` và `RecordingFile` cần đóng để giải phóng tài nguyên; file JFR cũng cần xóa trong bài test. `Files.deleteIfExists(output)` được đặt ở `finally` nên thường dọn được file tạm ngay cả khi có exception; nếu bị process khác khóa trên Windows, xóa có thể thất bại và test báo lỗi.

Trong hệ thống production, file JFR dùng điều tra sự cố **không nhất thiết xóa ngay**. Phải có nơi lưu, phân quyền, mã hóa, quota, hạn lưu và quy trình chia sẻ an toàn riêng.

## 9. Trình tự từ khai báo annotation đến công cụ phân tích

Luồng hoạt động:

```text
Java source
  @Name/@Label/@Description/@Category
      |
      v
Custom Event extends jdk.jfr.Event
      |
      v
EventType metadata
  getName/getLabel/getDescription/getCategoryNames
      |
      +--------------------+
      |                    |
  Recording              Analyzer/consumer
  enable + commit           lấy schema
      |
      v
  JFR repository
      |
      v
    .jfr file
      |
      v
RecordingFile / JMC / jfr print
      |
      +-- filter theo event name
      +-- đọc field theo field name
      +-- trình bày label/description/category
```

**Không phải tất cả metadata đều là dữ liệu biến đổi theo record.** Metadata định nghĩa cách một *type* được mô tả. Event instance có time, thread, duration, field values. `@Label` không đổi code/byte dữ liệu field; `@Category` không tự quyết định event nào cần thu thập.

### 9.1. Xem event metadata bằng Java API

Lấy danh sách event types đã đăng ký:

```java
FlightRecorder.getFlightRecorder().getEventTypes()
        .stream()
        .filter(t -> t.getName().startsWith("com.example."))
        .forEach(t -> System.out.println(
                t.getName() + " : " + t.getLabel()));
```

Đây là **trích đoạn**, cần module JFR, import `jdk.jfr.FlightRecorder` và chạy trên JVM có quyền sử dụng. Nếu event class chưa được đăng ký/load, nó có thể chưa có trong danh sách; có thể chủ động lấy `EventType.getEventType(OrderOperation.class)` như demo. Dùng tên loại để filter **không** phụ thuộc vào nhãn hiển thị.

### 9.2. Xem file bằng `jfr` CLI

Với một file `.jfr` **được giữ lại**:

```bash
jfr summary /secure/path/example.jfr
jfr print --events com.example.orders.Operation /secure/path/example.jfr
```

Đây là **lệnh vận hành minh họa**; `/secure/path/example.jfr` cần được thay bằng đường dẫn file có thật và quyền đọc tương ứng. Lệnh `jfr print --events` dùng **event name** chứ không phải label `Order Operation`.

**Trong demo, file tạm được xóa ngay**, vì vậy muốn thử CLI với file demo, phải **chủ động giữ một bản dump an toàn trong môi trường test** và đổi bước cleanup phù hợp. Đừng dùng `/secure/path/example.jfr` theo nghĩa một file đã được tạo sẵn.

JDK Mission Control có thể nhóm event theo `@Category` và hiển thị `@Label`/`@Description`, nhưng JMC là công cụ có vòng đời/phân phối riêng; không giả định GUI JMC có sẵn trong mọi JDK server image.

## 10. Thay đổi metadata: cái gì ổn định, cái gì gây breaking change?

Một hệ thống production thường có những consumer khác nhau: CLI `jfr print`, công cụ đọc `RecordingFile`, JMC plugin, dashboard, cấu hình `.jfc` và rule/alert. Cần quản lý metadata như một **schema contract**.

| Thay đổi | Ảnh hưởng thường gặp | Độ rủi ro |
| --- | --- | --- |
| Đổi Java class name nhưng **giữ `@Name`** | Event type name ổn định; code consumer theo name không đổi | Thường thấp, nhưng vẫn test classloading |
| Đổi `@Name` của event | Filter name, `.jfc` settings, consumer theo name có thể mất event | **Breaking** |
| Bỏ `@Name` | Quay về fully-qualified class name; có thể đổi event ID | **Breaking** |
| Đổi `@Name` của field | `getInt("oldName")`/`getString("oldName")` không còn đọc được dữ liệu mới | **Breaking** |
| Đổi field Java name nhưng **giữ @Name** | JFR field name có thể giữ nguyên | Thường dễ tương thích hơn |
| Đổi `@Label` | Thay tên hiển thị trong UI/report | Thường không breaking đối với consumer theo name |
| Đổi `@Description` | Thay giải thích, có thể đổi rule/documentation | Không đổi tên/giá trị, vẫn cần review |
| Đổi `@Category` | Event di chuyển vị trí trong cây/biểu đồ | Không đổi event name, nhưng UI/dashboard grouping có thể đổi |
| Thêm field tương thích | Consumer cũ có thể bỏ qua field mới | Cần review size/privacy và format |
| Đổi type của field | Consumer getters có thể lỗi, kết quả bị diễn giải sai | **Breaking** |
| Bỏ field | Consumer đọc field cũ thất bại | **Breaking** |

### 10.1. Phiên bản hóa event type

Nếu thật sự đổi **ý nghĩa** của một event không thể giữ tương thích, nên cân nhắc **event name phiên bản mới** có chính sách rõ ràng:

```text
com.example.orders.OperationV1
com.example.orders.OperationV2
```

Đây là ví dụ về **quản trị schema**, không phải yêu cầu phải thêm V1/V2 vào mọi tên ngay từ đầu. Nếu ý nghĩa không đổi, đừng đổi tên chỉ vì refactor Java package. Với một bản ghi gồm nhiều phiên bản event, consumer cần nhận diện theo event type name và field descriptors phù hợp, không chỉ dựa vào UI labels.

### 10.2. Hỗ trợ nhiều classloader

JFR `EventType.getId()` cung cấp ID riêng trong JVM instance. Khi cùng tên event xuất hiện ở nhiều classloaders khác nhau, dùng name có thể gây nhập nhằng một số tác vụ cấu hình/consumer. Java SE 11 cho phép setting key dùng event **ID** khi cần phân biệt trong cùng JVM.

Không cố tạo `@Name` chứa classloader identity hoặc UUID ngẫu nhiên để “giải quyết” vấn đề, vì sẽ mất ổn định qua restart. Với plugin architecture, cần naming convention, classloader policy, và test recording thực tế, hoặc sử dụng ID runtime cho tình huống đã được kiểm soát.

## 11. Quy tắc đặt tên cho thư viện và ứng dụng lớn

Một bộ quy ước có thể dùng:

| Thành phần | Quy tắc | Ví dụ |
| --- | --- | --- |
| Namespace event | Bắt đầu bằng tên tổ chức/product, ổn định | `com.example.orders` |
| Event type name | Danh từ chỉ loại hoạt động/điểm quan sát | `com.example.orders.Operation` |
| Event label | Nhan đề ngắn, human-readable | `Order Operation` |
| Event description | Giải thích chính xác loại sự kiện và ý nghĩa | `Measures duration of an order operation` |
| Category cấp 1 | Phần lớn theo ứng dụng/nhóm rộng | `Application` |
| Category cấp 2 | Theo lĩnh vực | `Orders`, `Storage`, `Networking` |
| Field name | Identifier ngắn, ổn định, có kiểu | `units`, `outcome` |
| Field label | Nhãn thân thiện | `Processed Units`, `Outcome` |
| Field description | Giải thích đơn vị/phạm vi/giá trị | `Number of synthetic units processed` |

### 11.1. Khi nào nên dùng `@Name` trên field?

Nếu tên Java field phù hợp và đã ổn định, **không nhất thiết** phải thêm `@Name` cho từng field:

```java
@Label("Result Code")
@Description("Safe classification of the operation outcome")
public String resultCode;
```

JFR field name mặc định sẽ là `resultCode`. Thêm `@Name("result")` khi bạn muốn **schema name khác Java field name**, ví dụ để giữ tương thích qua refactor hoặc phối hợp định dạng consumer hiện hữu. Cần test byte-level/event getter như ở demo.

### 11.2. Khi nào category chỉ một cấp là đủ?

Một ứng dụng nhỏ có thể dùng:

```java
@Category("Application")
class BackgroundJobEvent extends Event {
}
```

Không bắt buộc mọi ứng dụng phải có bốn cấp. Cây phân loại quá sâu làm JMC khó duyệt, đặc biệt khi các nhóm chỉ có một event. Chọn độ sâu giúp phân biệt **nhóm để điều tra**, không phải phản ánh mọi package trong source.

### 11.3. Dùng description để ngăn diễn giải sai

Tên `Order Operation` có thể chưa đủ rõ: event được phát sau khi order đã **commit** hay khi bắt đầu **xử lý**? `@Description` nên giải thích, chẳng hạn:

```java
@Description(
    "Measures processing time before the order commit is attempted")
class OrderOperation extends Event {
}
```

Nếu thay đổi vị trí instrument từ trước commit sang sau commit, phải **cập nhật mô tả** và xem xét thay đổi ý nghĩa schema. Một description lỗi thời khiến người vận hành kết luận sai dù dữ liệu vẫn được ghi đúng.

## 12. Annotation metadata không làm event tự xuất hiện

Đây là một trong những hiểu nhầm lớn khi mới dùng JFR:

```java
@Name("com.example.jobs.Sync")
@Label("Sync Operation")
@Description("Records the duration of a synchronization operation")
@Category({"Application", "Jobs"})
class SyncEvent extends Event {
    public String outcome;
}
```

Chỉ khai báo annotation **không** tự tạo bản ghi. Bạn phải tạo instance, gán field, commit, và có một recording tương ứng:

```java
SyncEvent event = new SyncEvent();
event.outcome = "SUCCESS";
event.begin();
// Thực hiện công việc cần đo ...
event.commit();
```

Đây là hai **trích đoạn**, không có `main` độc lập. Dấu `...` chỉ là phần giải thích nằm trong comment, không phải code đã kiểm chứng. `commit()` sau `begin()` tự kết thúc interval ở thời điểm commit theo Javadoc Java 11. Nếu muốn đo chính xác thời điểm kết thúc độc lập với xử lý field, có thể gọi `end()` trước `commit()`.

Phải có recording đang chạy và event enabled, đạt điều kiện threshold/setting thì event mới thực sự được lưu. `@Name`, `@Label`, `@Description`, `@Category` **không thay thế** `Recording.enable`, `Event.shouldCommit()` hoặc `Event.commit()`.

### 12.1. Cấu hình default và overhead

Nếu custom event phát cực nhiều lần, chỉ trang trí bằng metadata không giải quyết overhead. Hãy đặt settings phù hợp:

```java
recording.enable(OrderOperation.class)
        .withThreshold(java.time.Duration.ofMillis(10))
        .withoutStackTrace();
```

Đây là **trích đoạn**; chỉ có ý nghĩa với một **duration event** được `begin()/end()` hoặc `begin()/commit()` đúng. Ví dụ full chương trình cố ý gọi `withoutThreshold()` vì muốn ghi đúng hai event ngắn cho mục đích test, **không phải** cấu hình production áp cho mọi thao tác.

Nếu thu thập field cần tính toán đắt đỏ, có thể dùng:

```java
OrderOperation event = new OrderOperation();
event.begin();
try {
    doBusinessWork();
} finally {
    event.end();
    if (event.shouldCommit()) {
        event.outcome = "OK"; // Mã an toàn; thực tế cần phản ánh đúng kết quả.
        event.commit();
    }
}
```

Đây là **trích đoạn**, cần định nghĩa `doBusinessWork()` và phân loại outcome đúng trên cả nhánh lỗi; không gán `OK` cứng cho thao tác lỗi. `shouldCommit()` giúp tránh thu thập metadata đắt khi event disabled hoặc dưới ngưỡng. Không sử dụng JFR để thay thế exception handling hoặc audit nghiệp vụ.

## 13. Field schema và kiểu dữ liệu được JFR hỗ trợ

Javadoc Java SE 11 của `jdk.jfr.Event` chỉ rõ những kiểu được JFR hỗ trợ làm event field:

- Primitives: `boolean`, `char`, `byte`, `short`, `int`, `long`, `float`, `double`.
- Reference types: **`String`, `Thread`, `Class`**.
- `static` fields không được lưu như dữ liệu event.
- `transient` fields được loại khỏi schema.
- Arrays, enum và các reference types khác **không** tự động trở thành JFR event fields; JFR có thể bỏ qua chúng.

Ví dụ **không nên suy ra từ code**:

```java
@Label("Items")
public java.util.List<String> items;  // Không phải JFR field type được hỗ trợ.

@Label("Status")
public Status status; // Enum không được tự ghi như JFR field.
```

Đây là **trích đoạn minh họa** trong event class, với `Status` là enum do ứng dụng định nghĩa. `@Label` không thể ép `List`/enum thành event value. Khi cần trạng thái, chuyển thành một **String code** đã được allowlist hoặc một primitive field đúng nghĩa; tránh dùng `toString()` trên object bất kỳ vì có thể chứa bí mật và dữ liệu rất lớn.

### Tên và kiểu field không phải là một

`@Name("units")` ảnh hưởng **tên trường**. `@Label("Processed Units")` ảnh hưởng **nhãn**. `@Description(...)` ảnh hưởng **giải thích**. Còn `int` mới quyết định data type và getter phù hợp `RecordedEvent.getInt("units")`.

Đừng dùng `@Name("long")`, `@Label("Number")` rồi nghĩ có thể đọc một `String` như `long`. Consumer cần kiểm tra đúng field type/schema và xử lý phiên bản tương ứng.

## 14. Bảo vệ dữ liệu nhạy cảm trong custom events

Một custom JFR event **không phải nơi ghi log tùy ý**. File `.jfr` có thể được dump, sao chép, lưu trong kho chung và mở bởi người vận hành với tool đọc metadata. Nếu field chứa credential, token, địa chỉ cá nhân, full URL hoặc request body, các giá trị đó vẫn có thể rò rỉ dù nằm trong định dạng nhị phân.

**Chính sách đề xuất:**

| Trường | Có nên ghi mặc định? | Ghi chú |
| --- | --- | --- |
| `operationCode` từ enum/danh mục cố định | Thường được, nếu được phép | Không ghi nguyên request |
| `durationMs` hoặc duration của event | Có thể hữu ích | Định nghĩa thời điểm bắt đầu/kết thúc |
| `units`, `byteCount` | Có điều kiện | Độ chi tiết có thể tiết lộ hành vi, cần review |
| `outcome` là mã lỗi cố định | Thường được | Không dùng raw exception message |
| `userEmail`, `phone` | Không mặc định | Dữ liệu cá nhân, có thể không cần cho chẩn đoán |
| `accessToken`, `sessionCookie` | **Không** | Bí mật có thể dùng lại |
| `rawUrl`, `query`, `requestBody` | **Không** | Có thể chứa token/PII |
| `orderId` thực hoặc correlation bền vững | Có điều kiện chặt | Có thể định danh; ưu tiên ID ngắn hạn phi bí mật |
| `Throwable.getMessage()` | Không ghi tự động | Message có thể chứa URL/token/PII |
| `Class` và `Thread` metadata | Theo chính sách | Có thể tiết lộ tên nội bộ |

**Cũng phải rà annotation values.** Không nên viết:

```java
@Description("Connects to https://api.example.test?token=REAL_SECRET")
class UnsafeEvent extends Event {}
```

Đây là **anti-pattern**, chuỗi chỉ là minh họa, không phải secret thật. Metadata type có thể tồn tại trong classfile và recordings; annotation không phải chỗ lưu config runtime có credential.

Với các event có thể phát hàng nghìn lần/giây, ngoài privacy còn phải xét **tần suất**, kích thước file, retention, chi phí field creation và stack trace. Bốn annotation metadata không tự giới hạn volume; dùng threshold/setting/recording policy riêng.

## 15. Lỗi phổ biến khi sử dụng `@Name`, `@Label`, `@Description`, `@Category`

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Lọc event bằng `@Label` | Label có thể đổi; không phải identifier | Filter theo `EventType.getName()` |
| Dùng `@Name("Order Operation")` | Dấu cách không hợp lệ với event name | Dùng dotted identifier hợp lệ |
| Đổi event `@Name` khi refactor mà không migrate | `.jfc`/consumer mất event | Giữ tên ổn định hoặc version/migrate |
| Không dùng `@Name` cho library event công khai | FQCN thay khi rename package | Chọn namespace ổn định |
| Gọi `getInt("processedUnits")` sau `@Name("units")` | Field name không khớp schema | Đọc `getInt("units")` |
| Nghĩ `@Name` thay đổi tên Java field | Source Java vẫn dùng `processedUnits` | Phân biệt source vs JFR schema |
| Áp `@Category` vào field | **Compile error** do sai `@Target` | Category trên event TYPE |
| Dùng chuỗi `"Application / Orders"` làm một category cấp đơn | Không tạo cây 2 cấp | `@Category({"Application","Orders"})` |
| Dùng category chứa user ID | Taxonomy nổ lớn, lộ dữ liệu | Nhóm kỹ thuật cố định |
| Nghĩ category cấp quyền xem | Không có security boundary | Phân quyền file/JFR tooling riêng |
| Đưa bí mật vào `@Description` | Rò trong metadata | Chỉ mô tả ý nghĩa chung |
| Trông chờ annotation tự ghi event | Không có `commit`/recording | Tạo event, enable và commit |
| Nghĩ `@Label` tự đổi kiểu/đơn vị | Getter vẫn theo field type | Dùng đúng primitive và metadata đơn vị |
| Ghi enum/array vào field và nghĩ sẽ có dữ liệu | Unsupported reference types có thể bị bỏ qua | Dùng primitive/String code phù hợp |
| Dùng `EventType.getId()` như persistent key xuyên JVM restart | ID là runtime-scoped | Dùng event name ổn định |
| Đổi label nhưng không kiểm tra UI dashboard | Dashboard hiển thị/group có thể thay | Review presentation dependency |
| Ghi mọi object bằng `toString()` vào event | Rò secret, tăng heap/bytes | Allowlist field ngắn, có kiểu |
| Dùng `withoutThreshold` cho hot path liên tục | Có thể phát quá nhiều event | Đặt threshold/sampling theo workload |
| Kỳ vọng `RecordingStream` trong Java 11 | API chỉ có từ JDK 14 | Dùng `RecordingFile` trên Java 11 |

## 16. Kiểm thử schema và metadata để tránh thay đổi ngoài ý muốn

Khi một custom event được nhiều service/công cụ dùng, nên có test xác minh **contract**:

1. `EventType.getName()` đúng chuỗi định danh đã công bố.
2. `getLabel()` và `getDescription()` có thông điệp rõ, không chứa giá trị bí mật.
3. `getCategoryNames()` đúng danh sách các cấp.
4. `getField("units")` tồn tại sau `@Name("units")`, type/getter phù hợp.
5. `getField("processedUnits")` không được dùng như một fallback tên schema nếu `@Name` đã đổi.
6. Bản ghi tạo bởi recording thực đọc được theo event name và field name.
7. Không có field arrays/enum/object bị tưởng nhầm là serialized tự động.
8. Kết quả consumer trên file đã lưu từ phiên bản cũ vẫn được giải thích theo schema của file đó.
9. Đổi Java package không làm tên event công khai thay đổi nếu giữ `@Name`.
10. Đổi category/label đã được kiểm tra với JMC/dashboard cần hỗ trợ.
11. Test chạy với đúng `--release 11` nếu triển khai Java 11.
12. Có test không rò secret sentinel vào fields và metadata.

### 16.1. Kiểm thử không dựa vào thời gian hoặc event ID

`EventType.getId()` có thể khác giữa các JVM, thời gian và thread ID cũng thay đổi. Trong bài tập, chương trình **in metadata ổn định và số đếm**, không in event ID, timestamp hay path. Đây là cách tạo test có output tin cậy mà vẫn kiểm chứng việc ghi/đọc thực.

Nếu muốn dùng unit test JUnit, assertion nên kiểm đúng các giá trị quan trọng:

```java
EventType type = EventType.getEventType(OrderOperation.class);

if (!"com.example.orders.Operation".equals(type.getName())) {
    throw new AssertionError("Event name changed");
}
if (!type.getCategoryNames().equals(
        java.util.Arrays.asList("Application", "Orders"))) {
    throw new AssertionError("Event category changed");
}
if (type.getField("units") == null) {
    throw new AssertionError("Field name changed");
}
```

Đây là **trích đoạn có thể đặt vào test method**, cần `OrderOperation` đã khai báo. Nó minh họa kiểm tra schema mà không phụ thuộc thứ tự event records khác loại hay JFR JVM-assigned type ID.

### 16.2. Test schema nhiều phiên bản

Nếu bạn phải đọc file `.jfr` được tạo từ các bản ứng dụng khác nhau, hãy lưu fixture/test vector với những event names/fields tiêu biểu và kiểm tra consumer xử lý tương thích. Không tự giả định JFR tự “rename field cũ sang field mới” khi bạn thay `@Name`; việc migration là trách nhiệm ứng dụng phân tích hoặc phiên bản hóa schema.

## 17. Bài luyện tập và đáp án

**Bài 1.** Muốn filter event bằng `jfr print --events ...`, nên dùng `"Order Operation"` hay `"com.example.orders.Operation"`?

**Đáp án:** Dùng **`com.example.orders.Operation`**, tức `@Name`/`EventType.getName()`. `Order Operation` là label cho người xem.

**Bài 2.** Event field được khai báo `@Name("units") int processedUnits`. Java code gán giá trị bằng thuộc tính nào, consumer đọc bằng tên nào?

**Đáp án:** Code Java gán `event.processedUnits`; JFR consumer dùng `recordedEvent.getInt("units")` vì `@Name` đổi field name trong metadata/schema.

**Bài 3.** `@Category({"Application","Orders"})` có nghĩa giống `@Category("Application / Orders")`?

**Đáp án:** Không. Mảng hai chuỗi tạo **hai cấp** trong category path, một chuỗi có dấu `/` là **một phần tử**.

**Bài 4.** Có thể gắn `@Category` vào từng `String outcome` để nó hiện trong nhóm `Success` hay `Failure` không?

**Đáp án:** Không. `@Category` có target `TYPE` và phân loại **event type**, không phân loại riêng mỗi field value. Dùng field `outcome` đã allowlist để filter bản ghi; không tạo event category động theo dữ liệu.

**Bài 5.** Đổi `@Label("Order Operation")` thành `@Label("Order Processing")` có buộc consumer `getEventType().getName()` đổi theo không?

**Đáp án:** Không. `@Label` và `@Name` độc lập. Tuy vậy, dashboard hiển thị có thể cần cập nhật nếu dựa vào label cũ.

**Bài 6.** Vì sao cần `@Description` nếu đã có `@Label`?

**Đáp án:** Label giúp nhận diện nhanh, Description giải thích ý nghĩa, phạm vi đo và đơn vị/diễn giải. Một nhãn `Processed Units` có thể chưa rõ tính trước/sau khi commit, còn description làm rõ semantics.

**Bài 7.** Nếu bỏ `@Name` trên event, JFR sử dụng tên nào?

**Đáp án:** Mặc định dùng tên class Java đầy đủ (*fully qualified class name*). Refactor package/class có thể đổi tên event, nên public event thường đặt `@Name` ổn định.

**Bài 8.** Có thể dùng một `@Name` tên `order-12345` cho mỗi đơn hàng để tra cứu dễ không?

**Đáp án:** Không nên. `@Name` phải hợp lệ theo identifier Java và phải ổn định ở **event type level**; ID đơn hàng còn có nguy cơ nhạy cảm. Dùng một event type cố định và field code/correlation được kiểm soát nếu thật sự cần.

**Bài 9.** Chỉ cần bốn annotation là recording đã chứa event chưa?

**Đáp án:** Chưa. Cần tạo event instance, gán field, gọi `commit()` và có recording đang chạy bật loại event, đáp ứng threshold/settings.

**Bài 10.** Mã Java thêm `@Label` vào một field `List<String>`. JFR có tự serialize list không?

**Đáp án:** Không. Theo Javadoc Java 11, mảng và các reference types khác ngoài `String`/`Thread`/`Class` không phải event field types hỗ trợ, có thể bị bỏ qua. Chuyển thành primitive hoặc String code phù hợp, không ghi object tùy ý.

**Bài 11.** Một JMC view chuyển `Order Operation` sang nhóm `Storage` sau khi đổi `@Category`. Điều đó có thay khả năng `RecordedEvent.getInt("units")` không?

**Đáp án:** Không, nếu event/field name và type giữ nguyên. Category thay cách nhóm trong UI, không thay field name và data type.

**Bài 12.** Làm sao tránh test flaky vì event ID và timestamp thay đổi giữa các lần chạy?

**Đáp án:** Assert định danh `getName()`, label/description/category, tồn tại field name, số lượng và tổng giá trị từ file thật; không hardcode `getId()`, timestamp hay file path.

## 18. Checklist code review

- [ ] Event có **`@Name` ổn định, hợp lệ và có namespace** khi là public/consumer-facing event?
- [ ] `@Label` ngắn, dễ đọc, không bị dùng làm key cấu hình?
- [ ] `@Description` giải thích event/field đúng nghĩa, không chứa dữ liệu nhạy cảm?
- [ ] `@Category` được gắn trên **event TYPE**, phân cấp đúng bằng `String[]`?
- [ ] Taxonomy không tạo category theo user/request/URL động?
- [ ] Tên field do `@Name` override đã được consumer đọc đúng không?
- [ ] Schema field types phù hợp với các kiểu JFR hỗ trợ?
- [ ] Không ghi secret, token, session ID, PII hoặc object serialization tùy ý?
- [ ] Recording enabled và event commit đúng lifecycle?
- [ ] Threshold/stackTrace/retention đã được chọn theo workload, không giả định metadata miễn phí?
- [ ] Có test với `EventType`/`ValueDescriptor` và một `RecordingFile` thật?
- [ ] Việc đổi event name/field name có kế hoạch tương thích hoặc versioning?
- [ ] Dự án Java 11 không sử dụng `RecordingStream` JDK 14+?
- [ ] Quyền truy cập và retention file `.jfr` đã được quản lý?

## 19. Tóm tắt và nguồn tham khảo

**Bốn vai trò cần nhớ:**

- **`@Name` = identifier:** dùng để cấu hình và đọc dữ liệu ổn định; đổi tên event/field có thể là breaking change.
- **`@Label` = display name:** đặt tên ngắn cho người vận hành; không dùng làm machine key.
- **`@Description` = giải thích:** giúp diễn giải đúng điều được đo; không thay validation, field types hay data security.
- **`@Category` = đường dẫn phân loại:** nhóm event trong UI, **chỉ áp trên event type**, không dùng để kiểm soát tần suất hay phân quyền.

Metadata ở **event type** giúp công cụ hiểu schema; các **event instances** mang giá trị dữ liệu và thời gian; **recording/settings** quyết định việc thu thập. Thiết kế tốt cần giữ tên ổn định, mô tả rõ, phân nhóm dễ hiểu, tránh field nhạy cảm và test được file JFR thật.

**Tài liệu chính thức, tiếp tục áp dụng trên Java hiện đại:**

- [Oracle Java SE 11 — `jdk.jfr.Name`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Name.html): định danh event/field/setting.
- [Oracle Java SE 11 — `jdk.jfr.Label`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Label.html): human-readable label, quy tắc viết nhãn.
- [Oracle Java SE 11 — `jdk.jfr.Description`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Description.html): mô tả event/field.
- [Oracle Java SE 11 — `jdk.jfr.Category`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Category.html): nhóm và category path trong công cụ.
- [Oracle Java SE 11 — `jdk.jfr.EventType`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventType.html): `getName`, `getLabel`, `getDescription`, `getCategoryNames`, `getField`.
- [Oracle Java SE 11 — `jdk.jfr.Event`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html): types của event field, `commit` và `shouldCommit`.
- [Oracle Java SE 11 — package `jdk.jfr`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html): metadata, recording settings, dynamic event factory.
- [Oracle Java SE 11 — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): điều khiển recording.
- [Oracle Java SE 11 — `jdk.jfr.consumer.RecordingFile`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc bản ghi.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): tích hợp JFR trong OpenJDK 11.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): phân biệt API streaming JDK 14+ với API recording Java 11.
- [Oracle Java SE 25 — `EventType`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/EventType.html): đối chiếu API metadata còn được sử dụng trên JDK hiện đại.
