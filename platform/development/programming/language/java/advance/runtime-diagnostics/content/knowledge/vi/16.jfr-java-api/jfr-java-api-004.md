# 16.4 Name, Label, Category, Description và annotation mô tả đơn vị dữ liệu trong JFR

## 1. Vì sao custom JFR event cần metadata?

Trong Java Flight Recorder (JFR), một **custom event** là lớp Java kế thừa `jdk.jfr.Event`. Các trường của lớp mô tả dữ liệu nghiệp vụ cần chẩn đoán: mã thao tác, số byte, thời gian chờ, tỷ lệ cache hit, số lần retry… Khi ghi thành file `.jfr`, công cụ như `jfr` CLI hay JDK Mission Control (JMC) cần biết **tên ổn định của event**, **nhãn dễ đọc**, **nhóm hiển thị**, **ý nghĩa các trường** và **đơn vị của giá trị**.

Các annotation trong package `jdk.jfr` giải quyết việc đó:

- `@Name`: định danh máy có thể dùng trong event settings, tìm kiếm và bộ đọc recording.
- `@Label`: tên dễ đọc cho người dùng của event, field hoặc setting.
- `@Category`: đường dẫn phân nhóm event trong công cụ phân tích.
- `@Description`: mô tả ngữ nghĩa để người khác hiểu đúng dữ liệu.
- `@Timespan`, `@Timestamp`, `@DataAmount`, `@Percentage` và các content-type annotation khác: **metadata mô tả đơn vị/cách diễn giải trường**.

**Điểm mấu chốt:** metadata **không tự tạo phép đo, không đổi giá trị Java, không bật recording và không tự chuyển đổi đơn vị**. Lập trình viên vẫn phải gán dữ liệu đúng đơn vị, dùng `begin()/end()/commit()` hoặc `Recording` đúng cách, và bảo đảm cấu hình JFR thu event. Metadata làm file ghi được **dễ đọc và có hợp đồng rõ ràng**.

Bài học dùng API chuẩn **JDK 17+**, thuộc module `jdk.jfr`; ví dụ cũng dùng `java.time`, `java.nio.file` trong JDK thông thường, không cần thư viện ngoài.

## 2. Phân biệt bốn annotation mô tả chính

| Annotation | Áp dụng điển hình | Trả lời câu hỏi | Ví dụ | Có phải định danh ổn định? |
| --- | --- | --- | --- | --- |
| `@Name` | Event class, field, setting | “Máy/API gọi nó là gì?” | `@Name("com.example.checkout.Attempt")` | **Có**, đặc biệt với event name |
| `@Label` | Event class, field, setting | “Người phân tích nhìn thấy nhãn nào?” | `@Label("Checkout Attempt")` | **Không**; là nhãn hiển thị |
| `@Category` | **Event class** | “Event nằm trong nhóm/lane nào?” | `@Category({"Application", "Checkout"})` | **Không**; là đường dẫn trình bày |
| `@Description` | Event class, field, setting | “Giá trị hoặc sự kiện có ý nghĩa gì?” | `@Description("One checkout attempt")` | **Không**; là tài liệu ngữ nghĩa |

Ví dụ chỉ metadata của class, chưa có phần ghi sự kiện:

```java
import jdk.jfr.Category;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.example.checkout.Attempt")
@Label("Checkout Attempt")
@Category({"Application", "Checkout"})
@Description("One checkout attempt, including queue wait and payload size")
public class CheckoutAttempt extends Event {
}
```

Đoạn trên là ví dụ class, yêu cầu lưu trong file `CheckoutAttempt.java` nếu dùng nguyên dạng public class. Nó định nghĩa event metadata nhưng **chưa tạo event instance hay recording**. Ví dụ đầy đủ, độc lập và có thể chạy ở mục 6.

### Ba tầng thông tin cần tách bạch

1. **Schema/identity:** `@Name` quyết định tên event/field trong metadata JFR, cho phép chọn event chính xác bằng tên.
2. **Presentation/documentation:** `@Label`, `@Category`, `@Description` giúp hiển thị, nhóm và đọc hiểu; đổi label/category không nhất thiết đổi schema.
3. **Value semantics:** `@Timespan`, `@DataAmount`… nói cách hiểu **giá trị số đã được ghi**; annotation không thực hiện tính toán hoặc chuyển kiểu.

## 3. `@Name`: tên định danh phải ổn định

`@Name` có thể đặt cho lớp event và các field/setting hỗ trợ. Với **event class**, tên phải là tên lớp hợp lệ theo cú pháp tên Java, thường dùng namespace reverse-domain:

```java
@Name("com.example.checkout.Attempt")
```

Nếu không gắn `@Name`, JFR dùng **fully qualified Java class name** làm event name. Điều này tiện cho thí nghiệm nhưng dễ vỡ khi refactor package/class: ví dụ đổi `com.example.CheckoutEvent` thành `com.example.events.CheckoutEvent` khiến tên event mặc định khác đi. Trong ứng dụng production, nên đặt event name chủ động và duy trì ổn định.

Với **field** hoặc setting, giá trị `@Name` phải là một định danh Java hợp lệ, ví dụ `payloadBytes`; không dùng dấu cách như `"Payload Bytes"`. Theo Javadoc, khi tên `@Name` không hợp lệ, annotation bị bỏ qua. **Không nên dựa vào việc bị bỏ qua**; hãy xác nhận metadata thực nhận bằng `EventType.getName()`, `ValueDescriptor.getName()` và `jfr metadata`.

Quy tắc thiết kế:

- Dùng tên ổn định, có namespace của tổ chức, ngắn gọn, đủ phân biệt: `com.example.checkout.Attempt`.
- Không lấy `@Label("...")` làm key tra cứu event; người biên tập có thể đổi label mà event name giữ nguyên.
- Không tùy ý đổi event `@Name` khi dashboard, `.jfc`, `jfr print --events`, parser hoặc alert đang tham chiếu tên đó.
- Tránh đụng namespace built-in `jdk.*` và tránh tên trùng của hai event khác ý nghĩa.
- Tránh nhét nhãn hiển thị, environment, phiên bản release hay giá trị nghiệp vụ biến động vào event name; lưu chúng dưới dạng field nếu cần.

Ví dụ **đổi nhãn nhưng không đổi identity**:

```java
@Name("com.example.checkout.Attempt")
@Label("Payment Attempt")
@Category({"Application", "Payments"})
```

Trong ví dụ này, event name vẫn là `com.example.checkout.Attempt`; công cụ lọc bằng tên đó vẫn có thể tìm event. Nhãn và category thay đổi cách trình bày trong UI.

## 4. `@Label`, `@Description`, `@Category`: tối ưu trải nghiệm phân tích

### `@Label`

`@Label` đặt tên người đọc dễ hiểu, ví dụ `@Label("Payload Size")` hoặc `@Label("Queue Wait")`. Nó được JMC và những công cụ hiểu metadata dùng như nhãn; API `EventType.getLabel()` hoặc `ValueDescriptor.getLabel()` đọc được.

Nhãn nên ngắn, cụ thể, nhất quán và không chứa dấu kết thúc câu. **Không dùng label làm định danh ổn định**. Ví dụ field Java `queueWaitMs` có label `Queue Wait`; người dùng thấy tên đẹp trong UI, nhưng code đọc field vẫn dùng key `queueWaitMs`.

### `@Description`

Dùng một hoặc hai câu để giải thích **thời điểm đo, phạm vi, nguồn và ý nghĩa**. Ví dụ:

```java
@Label("Queue Wait")
@Description("Time spent waiting in the work queue before processing")
@Timespan(Timespan.MILLISECONDS)
public long queueWaitMs;
```

`@Description` cho biết thời lượng đo từ khi vào queue đến khi bắt đầu xử lý, không phải toàn bộ thời gian HTTP request. Chú thích có ích nhất là chú thích **ngăn diễn giải sai**; tránh chỉ lặp lại tên trường kiểu “Queue wait duration”. Đặc biệt cần ghi rõ: đo trên server hay client, đã bao gồm network/queue/retry hay chưa, có thể âm/khuyết hay không, và nguồn đồng hồ nào.

### `@Category`

`@Category({"Application", "Checkout"})` khai báo **đường dẫn phân cấp**: root `Application` → nhánh `Checkout`. Các phần tử mảng **không phải hai tag độc lập**. Các event cùng đường dẫn thường được nhóm trong cây hoặc timeline của JMC; đường dẫn category có thể đổi để phục vụ cách tổ chức mà không bắt buộc đổi event name.

`@Category` áp dụng cho **event type**, không gắn vào field. Với sự kiện có thời gian chồng lên nhau trong timeline, tách category hợp lý có thể giúp công cụ hiển thị thành những lane khác nhau. Không cần tạo category quá sâu; ví dụ `Application / Checkout` đủ rõ hơn `Application / System / Runtime / Services / Payment / Checkout / Attempts` nếu tổ chức không có nhu cầu như vậy.

## 5. Các annotation mô tả đơn vị và ý nghĩa giá trị

Các annotation này còn được gọi là **content-type annotations**; chúng cung cấp **gợi ý diễn giải/format** cho JFR reader. Trong Java, field vẫn giữ kiểu gốc `long`, `int`, `double`, `boolean`… tương ứng.

| Annotation | Ý nghĩa và đơn vị | Giá trị ví dụ | Cách hiểu đúng |
| --- | --- | --- | --- |
| `@Timespan(Timespan.MILLISECONDS)` | Khoảng **thời gian** theo mili giây | `15L` | 15 ms, không phải timestamp |
| `@Timespan(Timespan.NANOSECONDS)` | Khoảng thời gian theo nano giây | `1_500_000L` | 1,5 ms nếu chuyển đổi |
| `@Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)` | **Thời điểm** tính theo milliseconds từ Unix epoch | `System.currentTimeMillis()` | Mốc thời gian thực, không phải duration |
| `@DataAmount(DataAmount.BYTES)` | Lượng dữ liệu theo byte | `2048L` | 2048 bytes |
| `@DataAmount(DataAmount.BITS)` | Lượng dữ liệu theo bit | `16L` | 16 bits |
| `@Percentage` | Tỷ lệ dạng **phân số**, thường trong `0.0–1.0` | `0.75` | Hiển thị dạng 75%, không phải 0,75% |
| `@Frequency` | Tần suất theo Hz | `60L` | 60 lần/giây nếu ngữ nghĩa field đúng |
| `@MemoryAddress` | Địa chỉ bộ nhớ để tool hiểu/format như địa chỉ | Giá trị `long` | Không phải kích thước buffer |
| `@Unsigned` | Gợi ý diễn giải số không dấu | Giá trị nguyên | Không thay đổi kiểu Java có dấu |
| `@BooleanFlag` | Flag true/false cho UI/metadata | `true` | Không biến một số tùy ý thành boolean |

Các hằng đơn vị chính thức gồm `Timespan.NANOSECONDS`, `MICROSECONDS`, `MILLISECONDS`, `SECONDS`, `TICKS`; `DataAmount.BYTES`/`BITS`; `Timestamp.MILLISECONDS_SINCE_EPOCH` và `TICKS`. Nếu không truyền tham số, `@Timespan` mặc định **nanoseconds**, `@DataAmount` mặc định **bytes**, `@Timestamp` mặc định **milliseconds since epoch**. Viết tường minh trong code nghiệp vụ giúp giảm nhầm lẫn.

**Hai bẫy lớn:**

1. `@Timespan(Timespan.MILLISECONDS)` trên giá trị tạo từ `System.nanoTime()` mà chưa đổi đơn vị → tool hiểu 1.000.000 nano giây thành **1.000.000 mili giây**, sai gấp một triệu lần. Dùng `TimeUnit.NANOSECONDS.toMillis(...)` hoặc đổi annotation sang `NANOSECONDS`.
2. `@Percentage` trên số `75.0` trong khi contract yêu cầu phân số `0.75` → UI có thể diễn giải là 7.500%. Annotation **không chia tự động cho 100**.

Tương tự, `@Timestamp(MILLISECONDS_SINCE_EPOCH)` không được điền trực tiếp `System.nanoTime()`, vì `nanoTime()` là đồng hồ đơn điệu với điểm gốc tùy ý, **không phải** Unix epoch. Muốn timestamp, dùng `System.currentTimeMillis()`; muốn đo khoảng thời gian, lấy hiệu của hai lần `System.nanoTime()` và gắn `@Timespan` đúng đơn vị.

**Điểm mở rộng:** `@BooleanFlag`, `@Frequency`, `@MemoryAddress`, `@Unsigned` hữu ích khi field thật sự mang ngữ nghĩa đó; đừng gắn bừa chỉ để báo cáo có thêm biểu tượng. `@DataAmount` chỉ biểu thị lượng dữ liệu, không tự biết dữ liệu là request payload, heap memory hay network transfer; `@Description` phải giải thích điều ấy.

## 6. Ví dụ hoàn chỉnh chạy được trên Java 17+: event có metadata và file JFR

Lưu vào **`JfrMetadataDemo.java`**. Đây là **một file Java độc lập**, không phụ thuộc framework hoặc file config bên ngoài. Class event đặt lồng trong class main để có thể biên dịch với một lệnh `javac`.

```java
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import jdk.jfr.Category;
import jdk.jfr.DataAmount;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.EventType;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Percentage;
import jdk.jfr.Recording;
import jdk.jfr.Timespan;
import jdk.jfr.Timestamp;
import jdk.jfr.ValueDescriptor;

public class JfrMetadataDemo {

    @Name("com.example.checkout.Attempt")
    @Label("Checkout Attempt")
    @Category({"Application", "Checkout"})
    @Description("A checkout attempt with payload and queue wait")
    public static final class CheckoutAttempt extends Event {

        @Label("Order ID")
        @Description("Opaque identifier of the order")
        public String orderId;

        @Label("Payload Size")
        @Description("Number of bytes in the request payload")
        @DataAmount(DataAmount.BYTES)
        public long payloadBytes;

        @Label("Queue Wait")
        @Description("Time spent waiting before execution")
        @Timespan(Timespan.MILLISECONDS)
        public long queueWaitMs;

        @Label("Cache Hit Fraction")
        @Description("Fraction of operations served from cache")
        @Percentage
        public double cacheHitFraction;

        @Label("Requested At")
        @Description("Wall-clock time at the start of the attempt")
        @Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)
        public long requestedAtMillis;
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("checkout-attempt.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(CheckoutAttempt.class)
                     .withThreshold(Duration.ZERO);
            recording.start();

            CheckoutAttempt event = new CheckoutAttempt();
            event.orderId = "sample-001";
            event.payloadBytes = 2048L;
            event.queueWaitMs = 12L;
            event.cacheHitFraction = 0.75;
            event.requestedAtMillis = System.currentTimeMillis();

            event.begin();
            event.end();
            event.commit();

            recording.stop();
            recording.dump(output);
        }

        EventType type = EventType.getEventType(CheckoutAttempt.class);
        System.out.println("name=" + type.getName());
        System.out.println("label=" + type.getLabel());
        System.out.println("category=" +
                String.join(" / ", type.getCategoryNames()));

        for (String fieldName : List.of(
                "payloadBytes", "queueWaitMs",
                "cacheHitFraction", "requestedAtMillis")) {
            ValueDescriptor field = type.getField(fieldName);
            System.out.println(fieldName + "=" + field.getContentType());
        }

        System.out.println("file=" + output.getFileName());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên, với quyền ghi file tại working directory:

```bash
javac --release 17 JfrMetadataDemo.java
java JfrMetadataDemo
```

**Các dòng stdout do chính chương trình in ra, theo thứ tự:**

```text
name=com.example.checkout.Attempt
label=Checkout Attempt
category=Application / Checkout
payloadBytes=jdk.jfr.DataAmount
queueWaitMs=jdk.jfr.Timespan
cacheHitFraction=jdk.jfr.Percentage
requestedAtMillis=jdk.jfr.Timestamp
file=checkout-attempt.jfr
```

Chú ý: đầu ra công cụ JVM khác (nếu cấu hình ghi log) có thể kèm thông báo riêng; đây là phần do `System.out.println` của ứng dụng tạo ra. Giá trị timestamp thực thay đổi theo lúc chạy **nhưng không được in**, nên stdout bên trên ổn định. File `checkout-attempt.jfr` nằm trong working directory của tiến trình. Nếu môi trường cấm ghi file, hãy chọn thư mục có quyền ghi trước khi chạy.

### Giải thích cơ chế từng bước

1. `recording.enable(CheckoutAttempt.class)` bật custom event trong **recording được tạo bởi chương trình**. `withThreshold(Duration.ZERO)` cho phép ghi cả event rất ngắn; nếu threshold lớn hơn thời lượng event, recording có thể bỏ qua.
2. `recording.start()` bắt đầu thu. Tạo instance `CheckoutAttempt`, gán dữ liệu như field Java thông thường. Annotation không tự lấy giá trị từ HTTP request, queue hay cache.
3. `event.begin()`/`event.end()` ghi thời gian bắt đầu/kết thúc **event** trong metadata chuẩn; `event.commit()` mới gửi event vào recorder nếu được bật và đáp ứng settings. `queueWaitMs=12` là **giá trị ví dụ gán thủ công** cho field queue wait, không phải thời lượng được JFR đo giữa `begin` và `end`.
4. `recording.stop()` dừng thu; `recording.dump(output)` xuất thành `.jfr`. `try-with-resources` đóng tài nguyên `Recording`.
5. `EventType.getEventType(...)` đọc metadata của loại event, `getName()`/`getLabel()`/`getCategoryNames()` trả metadata class. `getField("queueWaitMs")` trả `ValueDescriptor`; `getContentType()` phản ánh annotation đơn vị, ví dụ chuỗi `jdk.jfr.Timespan`.
6. Các giá trị JFR như `payloadBytes=2048` và `cacheHitFraction=0.75` vẫn được lưu theo số gốc; các công cụ JFR có thể hiển thị theo bytes/percent nhờ metadata.

Đoạn `event.begin(); event.end();` liên tiếp tạo event rất ngắn nên ta đặt threshold bằng `Duration.ZERO`. Khi code thực tế có thao tác cần đo, đặt `begin()` **trước** và `end()` **sau** phần việc để thời lượng event mang ý nghĩa nghiệp vụ. Nếu dữ liệu bổ sung đắt đỏ, dùng `event.isEnabled()`/`event.shouldCommit()` và lựa chọn cách thu thập phù hợp để hạn chế overhead.

## 7. Kiểm tra metadata trong file bằng `jfr` CLI

Sau khi chạy ví dụ, kiểm tra file `.jfr` thực sự chứa event và schema:

```bash
jfr summary checkout-attempt.jfr
jfr metadata --events com.example.checkout.Attempt checkout-attempt.jfr
jfr print --events com.example.checkout.Attempt checkout-attempt.jfr
```

- `jfr summary` kiểm tra file đọc được, loại event nào có trong recording và số lượng event.
- `jfr metadata --events ...` đọc **schema/metadata** của event được chọn: tên, nhãn, description, category, các trường và đơn vị.
- `jfr print --events ...` đọc **bản ghi thực tế**. Số liệu có thể hiển thị theo định dạng của phiên bản `jfr`, không nhất thiết giống GUI JMC, nhưng phần dữ liệu vẫn dựa trên field gốc.

Tên lọc là `com.example.checkout.Attempt` từ `@Name`, **không phải** `Checkout Attempt` từ `@Label`, và **không phải** tên Java class `JfrMetadataDemo.CheckoutAttempt`. `@Category` giúp nhóm trong JMC; nếu muốn chọn event trong CLI nên dùng event name.

Khi tìm không thấy event, kiểm tra **recording đã bật đúng loại event hay chưa**, threshold/enable settings, thời điểm `commit()`, file vừa ghi có bị đọc nhầm và cách lọc `--events`. Metadata có thể có trong file khi loại event được biết nhưng số record thực tế bằng 0, ví dụ threshold loại bỏ event.

## 8. Đọc metadata trực tiếp qua API

Không cần parse văn bản `jfr print` để biết nghĩa một field. JDK cung cấp lớp metadata:

```java
EventType type = EventType.getEventType(CheckoutAttempt.class);
String name = type.getName();
String label = type.getLabel();
String description = type.getDescription();
List<String> categories = type.getCategoryNames();

ValueDescriptor field = type.getField("queueWaitMs");
String fieldName = field.getName();
String fieldLabel = field.getLabel();
String fieldDescription = field.getDescription();
String contentType = field.getContentType(); // jdk.jfr.Timespan
```

Đây là **mảnh mã minh họa** đặt trong bối cảnh `JfrMetadataDemo` (cần import `jdk.jfr.*` và `java.util.List`); nếu dán vào một file hoàn toàn riêng sẽ cần thêm class wrapper và định nghĩa `CheckoutAttempt`. Những phương thức trên cho phép kiểm tra chương trình độc lập với cách hiển thị cụ thể của JMC.

Một vài API hữu ích:

| API | Dùng để |
| --- | --- |
| `EventType.getName()` | Lấy định danh event đã áp dụng `@Name` |
| `EventType.getLabel()` | Lấy nhãn dễ đọc |
| `EventType.getDescription()` | Lấy mô tả |
| `EventType.getCategoryNames()` | Lấy chuỗi cấp category từ root tới nhánh |
| `EventType.getFields()` / `getField(name)` | Lấy danh sách hoặc một descriptor của field |
| `ValueDescriptor.getName()` / `getLabel()` / `getDescription()` | Lấy định danh và metadata văn bản của field |
| `ValueDescriptor.getContentType()` | Lấy tên content-type để công cụ định dạng/diễn giải |
| `getAnnotationElements()` / `getAnnotation(...)` | Truy xuất các annotation được đưa vào JFR metadata |

Ví dụ `ValueDescriptor.getContentType()` trả `"jdk.jfr.Percentage"` với field `@Percentage`. Nếu không có content-type annotation, phương thức có thể trả `null`. Với custom units, hãy đọc thêm `getAnnotationElements()` hoặc các annotation tương ứng thay vì đoán chỉ từ kiểu số.

**Quan trọng:** `getContentType()` không trả đơn vị chi tiết như “MILLISECONDS” trực tiếp; để biết chính xác đơn vị của `@Timespan`, xem annotation `@Timespan`/value trong metadata. Hai field cùng content type `jdk.jfr.Timespan` có thể mang đơn vị **khác nhau** nếu một cái dùng `MILLISECONDS` còn cái kia dùng `NANOSECONDS`.

## 9. Khi nào dùng `@Name` ở cấp field?

Bình thường, JFR lấy tên field từ định danh Java:

```java
@Label("Payload Size")
@DataAmount(DataAmount.BYTES)
public long payloadBytes;
```

JFR field name là `payloadBytes`. Nếu cần ổn định schema khi refactor Java code, có thể khai báo riêng:

```java
@Name("payloadBytes")
@Label("Payload Size")
@DataAmount(DataAmount.BYTES)
public long requestBodySize;
```

Ở ví dụ thứ hai, tên biến Java là `requestBodySize` còn **tên metadata JFR** được yêu cầu là `payloadBytes`. Đây là cách bảo tồn field identity mà không buộc giữ tên biến Java cũ. Không lạm dụng vì làm code và schema khác tên nhau, đòi hỏi chú thích và kiểm thử. Tên field phải là identifier hợp lệ, không phải câu có dấu cách.

Nếu muốn đổi ý nghĩa field từ “request body bytes” sang “response compressed bytes”, **đừng giữ nguyên `@Name` để giả vờ schema không đổi**; đó là thay đổi ngữ nghĩa. Tạo field mới hoặc event name/version mới khi thay đổi contract khiến downstream có thể diễn giải sai.

## 10. Phân biệt timestamp, timespan và thời lượng event tích hợp

Trong JFR có ba loại dữ liệu thời gian thường nhầm lẫn:

| Dữ liệu | Nguồn | Ý nghĩa |
| --- | --- | --- |
| Event `startTime` | JFR khi `begin()/commit()` | Mốc bắt đầu sự kiện |
| Event `duration` | JFR đo giữa `begin()` và `end()` (hoặc thời lượng tức thời nếu không đo) | Khoảng thời gian event đã bao phủ |
| Custom field `queueWaitMs` | Ứng dụng chủ động tính/gán | Riêng thời gian nằm trong queue, có thể khác duration event |
| Custom field `requestedAtMillis` | `System.currentTimeMillis()` trong ví dụ | Mốc thời gian thực theo Unix epoch milliseconds |

Ví dụ đo thực tế queue wait:

```java
long enqueueNanos = System.nanoTime();
// ... công việc được đặt vào queue, rồi tới lúc dequeue ...
long waitNanos = System.nanoTime() - enqueueNanos;
event.queueWaitMs = java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(waitNanos);
```

Đây là **mảnh minh họa**, cần được gọi ở đúng hai mốc nghiệp vụ. Vì dùng `toMillis`, annotation ở field phải là `@Timespan(Timespan.MILLISECONDS)`. Nếu muốn giữ độ phân giải cao và tránh làm tròn ở queue wait ngắn, lưu `waitNanos` vào field dùng `@Timespan(Timespan.NANOSECONDS)`.

**Không gắn `@Timestamp` vào hiệu thời gian**, cũng không gắn `@Timespan` cho thời điểm “2026-10-29 17:00”. Dù cả hai đều là `long`, cách diễn giải hoàn toàn khác.

## 11. Các tình huống chọn annotation đơn vị đúng

### A. Theo dõi HTTP/request size

```java
@Label("Request Size")
@Description("Uncompressed request body size in bytes")
@DataAmount(DataAmount.BYTES)
public long requestBytes;
```

Nếu muốn phân tích kích thước payload trước hay sau giải nén, mô tả rõ. `@DataAmount` không phân biệt byte trên mạng, bytes trong bộ đệm hay memory retained.

### B. Theo dõi tỷ lệ cache hit

```java
@Label("Cache Hit Ratio")
@Percentage
public double hitFraction; // Ví dụ: 0.875 nghĩa là 87,5%
```

Nếu nguồn metric trả về `87.5` theo đơn vị “percentage points”, cần chuyển sang `0.875` **trước khi gán**. Annotation không tự điều chỉnh.

### C. Theo dõi thời gian đợi DB pool

```java
@Label("Connection Wait")
@Description("Time waited for a database pool connection")
@Timespan(Timespan.MILLISECONDS)
public long acquireMillis;
```

Khác `Event.duration` của cả request. Nếu DB pool không cấp được connection và request fail, quy ước giá trị sentinel/không có dữ liệu phải được mô tả rõ.

### D. Theo dõi tần suất và thời điểm

```java
@Label("Retry Rate")
@Frequency
public long retriesPerSecond;

@Label("Observed At")
@Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)
public long observedAtMillis;
```

`@Frequency` mang ý nghĩa Hz, không phải “đã retry bao nhiêu lần từ đầu service”. `@Timestamp` yêu cầu epoch milliseconds phù hợp, không phải `System.nanoTime()`.

### E. Theo dõi số bit, địa chỉ hoặc giá trị không dấu

Dùng `@DataAmount(DataAmount.BITS)` khi số liệu thực sự tính bằng bits. `@MemoryAddress` có ý nghĩa với trường địa chỉ native, không phải kích thước. `@Unsigned` cung cấp metadata diễn giải không dấu cho số nguyên nhưng **không đổi semantics của toán tử số nguyên Java**. Chỉ đưa địa chỉ native hoặc dữ liệu nhạy cảm vào JFR khi phục vụ một nhu cầu chẩn đoán cụ thể.

## 12. Annotation không thay đổi vòng đời event

Metadata đẹp không có nghĩa recording chắc chắn có event. Một custom event muốn xuất hiện trong `.jfr` thường cần:

1. **Định nghĩa** một lớp `extends Event` cùng các field được hỗ trợ.
2. **Bật** loại event trong cấu hình đang chạy: `Recording.enable(YourEvent.class)`, hoặc cấu hình JFR event name phù hợp qua startup/`jcmd`/file `.jfc`.
3. **Gán field** và đo thời gian nếu cần.
4. **Commit** bằng `event.commit()`; JFR có thể loại nếu recording không chạy, event bị tắt hoặc threshold/filter không đạt.
5. **Dump/stop recording** để tạo file phân tích, ví dụ `recording.dump(Path.of("..."))`.

`@Label` hoặc `@Category` **không bật event**, `@Description` **không log một dòng nào**, `@Timespan` **không đo thời gian**. `@Enabled`, `@Threshold`, `@StackTrace` mới liên quan đến default settings của event; đó là nhóm annotation cấu hình hành vi khác. Việc một recording bật loại event bằng tên nào phụ thuộc `@Name`/event type, **không phụ thuộc label/category**.

Nếu payload đắt đỏ (serialize object, lấy stack trace bổ sung, nối chuỗi lớn…), dùng `event.isEnabled()` hoặc `event.shouldCommit()` để tránh công việc không cần thiết. `shouldCommit()` dựa trên settings và trạng thái event; nếu dùng threshold theo duration, gọi ở thời điểm phù hợp để nhận quyết định đáng tin, thay vì gọi trước khi có thời lượng đã đo.

## 13. Những lỗi phổ biến khi thiết kế schema JFR

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `@Label` làm tên filter trong `jfr print --events` | Không tìm thấy loại event | Dùng `@Name`, ví dụ `com.example.checkout.Attempt`. |
| Không khai báo `@Name` ở production | Refactor Java class/package làm đổi event name | Đặt tên có namespace ổn định và regression test. |
| Dùng `@Category({"App", "Checkout"})` như hai tags độc lập | Nhóm event sai kỳ vọng | Hiểu là **đường dẫn phân cấp** root → branch. |
| Đổi `@Name` chỉ vì đổi tên hiển thị | Phá dashboard/parser/.jfc đang tham chiếu event name cũ | Đổi `@Label`/`@Category` nếu chỉ đổi presentation. |
| `@Percentage` trên giá trị `75` | GUI có thể hiểu thành 7500% | Lưu `0.75` cho 75%. |
| `@Timespan(MILLISECONDS)` trên nanoseconds | Thời gian hiển thị sai hàng triệu lần | Chuyển đơn vị khi gán hoặc sửa annotation. |
| `@Timestamp` trên `System.nanoTime()` | Epoch timestamp vô nghĩa | Dùng epoch millis cho timestamp, nanoTime cho duration. |
| Đổi đơn vị nhưng giữ nguyên tên field | Dữ liệu nhiều phiên bản bị đọc lẫn | Giữ contract hoặc version/schema field mới. |
| Chỉ gắn `@Label`/`@Description` mà không `commit` | Không có event được thu | Kiểm tra enable, threshold, recording và commit. |
| Chỉ xem kiểu `long` và bỏ qua annotation | Không biết số là bytes, ms hay epoch | Đọc `ValueDescriptor.getContentType()` và annotation values. |
| Field chứa object phức tạp/nhạy cảm tùy ý | Không hợp lệ, không hữu ích, tăng overhead hoặc lộ thông tin | Chọn primitive/String/Thread/Class hợp lệ, giảm payload và áp dụng chính sách dữ liệu. |
| Xem `jfr print` chỉ có số thô rồi nghĩ annotation hỏng | CLI hiển thị khác GUI hoặc format tool khác JDK | Dùng `jfr metadata` và JMC để kiểm tra metadata gốc. |

Đặc biệt, **event name và field name là một phần hợp đồng dữ liệu**. Nếu nhiều dịch vụ/phiên bản ghi cùng tên nhưng fields mang ý nghĩa khác nhau, một báo cáo tổng hợp có thể “đúng về mặt cú pháp” nhưng sai về phân tích. Lập bảng schema và kiểm thử tương thích khi đổi ý nghĩa/kiểu/đơn vị.

## 14. Kiểm thử metadata có ý nghĩa, không chỉ kiểm tra file tồn tại

Một kiểm thử tốt nên kiểm tra cả **metadata** và **sự kiện thực**. Với ví dụ ở mục 6:

- `EventType.getName()` phải là `com.example.checkout.Attempt`.
- `EventType.getLabel()` là `Checkout Attempt`, category là `Application / Checkout`.
- `ValueDescriptor.getContentType()` của `payloadBytes` là `jdk.jfr.DataAmount`; `queueWaitMs` là `jdk.jfr.Timespan`; `cacheHitFraction` là `jdk.jfr.Percentage`; `requestedAtMillis` là `jdk.jfr.Timestamp`.
- Metadata `@Timespan` thật sự có `MILLISECONDS` và `@DataAmount` có `BYTES`; không chỉ kiểm tra chung content-type.
- `jfr summary` cho thấy event xuất hiện, `jfr print` cho thấy `orderId="sample-001"`, `payloadBytes=2048`, `cacheHitFraction=0.75` theo contract giá trị gốc.
- Khi đổi Java class/package nhưng giữ `@Name`, event name phải giữ nguyên; khi chỉ đổi `@Label`/`@Category`, parser đọc bằng `@Name` không bị ảnh hưởng.
- Khi đổi đơn vị dữ liệu, kiểm thử phải phát hiện sự khác biệt giữa **value thực** và **annotation** (ví dụ 1.500.000 ns tương ứng 1,5 ms).

Nếu viết test tự động, đừng dùng chỉ lệnh Java `assert` rồi quên `-ea`; có thể dùng JUnit assertions hoặc kiểm tra `if (...) throw new AssertionError(...)`. Một test chỉ chứng minh field gắn `@Timespan` nhưng không kiểm tra phép đổi ns → ms sẽ bỏ sót lỗi quan trọng nhất.

## 15. Checklist khi thêm custom event vào ứng dụng

- [ ] `@Name` có namespace của ứng dụng, đúng cú pháp Java, ổn định trong thời gian dài.
- [ ] `@Label` ngắn gọn, dễ hiểu; `@Description` nói rõ đơn vị, nguồn, phạm vi và thời điểm đo.
- [ ] `@Category` phản ánh cách nhóm event trong JMC; không dùng category để thay thế định danh.
- [ ] Tên field, kiểu dữ liệu, ý nghĩa và đơn vị được ghi thành contract, có kiểm thử.
- [ ] `@Timespan` dùng với **khoảng thời gian**, `@Timestamp` với **mốc thời gian**, `@DataAmount` với bytes/bits, `@Percentage` với tỷ lệ 0–1.
- [ ] Với data có thể bắt đầu từ `System.nanoTime()`, đã chuyển đơn vị đúng trước khi gán.
- [ ] Các trường tùy chọn về `Frequency`/`MemoryAddress`/`Unsigned` chỉ gắn khi đúng ngữ nghĩa.
- [ ] Event được enable trong recording, có `commit()` và threshold phù hợp; có file `.jfr` để xác minh.
- [ ] Dùng `jfr metadata`, `jfr summary` và `jfr print` hoặc JMC để kiểm tra cả schema lẫn dữ liệu.
- [ ] Refactor class, đổi nhãn, đổi đơn vị đều được đánh giá tác động đến parser, dashboard, file cấu hình JFR và tài liệu.
- [ ] Không ghi dữ liệu định danh cá nhân, token, bí mật, payload lớn hoặc object nhạy cảm khi không cần.
- [ ] Đã đo overhead của custom event ở tần suất thực tế và giới hạn cardinality/size của trường string.

## 16. Nguồn API chính thức

Các tài liệu sau là Javadoc của **Java SE 26** (các API nền tảng được dùng trong ví dụ đã có ở JDK 17), giúp kiểm tra trực tiếp các contract và annotation values:

1. Package `jdk.jfr` — hướng dẫn định nghĩa custom event và event metadata: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/package-summary.html
2. `@Name` — quy tắc định danh hợp lệ và ổn định: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Name.html
3. `@Label` — nhãn người dùng: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Label.html
4. `@Category` — đường dẫn nhóm event: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Category.html
5. `@Description` — chú thích ngữ nghĩa: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Description.html
6. `@Timespan` — hằng đơn vị nanos, micros, millis, seconds và ticks: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Timespan.html
7. `@Timestamp` — epoch millis hoặc ticks: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Timestamp.html
8. `@DataAmount` — bytes và bits: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/DataAmount.html
9. `@Percentage` — phần trăm dùng giá trị phân số: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Percentage.html
10. `EventType` và `ValueDescriptor` — đọc metadata bằng API: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/EventType.html và https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/ValueDescriptor.html
11. `Event` và `Recording` — vòng đời ghi JFR: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Event.html và https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Recording.html

**Nguyên tắc cuối:** dùng `@Name` làm **identity**, `@Label`/`@Category`/`@Description` để giúp **con người hiểu**, và content-type annotation để xác định **đơn vị/ý nghĩa của dữ liệu**. Một event hữu ích phải đúng cả ba tầng; nếu metadata và giá trị thực mâu thuẫn, file JFR có thể đọc được nhưng kết luận chẩn đoán sẽ sai.
