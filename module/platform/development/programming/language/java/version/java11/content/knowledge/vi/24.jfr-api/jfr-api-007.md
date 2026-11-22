# JFR API — Metadata đơn vị, nội dung và stack trace (Java 11+)

## Mục tiêu học tập

**Java Flight Recorder (JFR)** thu thập các sự kiện (*events*) để quan sát và chẩn đoán JVM. Khi tự định nghĩa event, việc ghi lại `long bytes = 2048` hay `long elapsed = 12` **chưa đủ** để một người đọc recording biết ý nghĩa con số: 2048 là byte hay bit? 12 là mili-giây hay nano-giây? Một giá trị 0.75 là tỉ lệ 75% hay số đo độc lập? Stack trace có được thu thập hay không?

Từ **Java 11**, module chuẩn `jdk.jfr` cung cấp các annotation và API metadata để giải thích **tên sự kiện, nhãn, mô tả, loại nội dung, đơn vị đo, danh mục và stack trace**. Module `jdk.jfr.consumer` cho phép đọc lại event và metadata trong file `.jfr`. Các API này vẫn còn hiện hành trên JDK mới; bài không phụ thuộc flag thương mại cũ hoặc API chỉ có từ các bản Java về sau.

Sau bài học, bạn có thể:

1. Phân biệt **giá trị raw**, **metadata mô tả ý nghĩa/đơn vị**, **settings điều khiển recording** và **stack trace thực sự được ghi**.
2. Dùng `@Name`, `@Label`, `@Description`, `@Category` để định nghĩa sự kiện có schema rõ ràng.
3. Dùng `@DataAmount`, `@Timespan`, `@Timestamp`, `@Percentage` và hiểu cách `@ContentType` giúp công cụ phân tích định dạng.
4. Dùng `EventType` và `ValueDescriptor` để đọc tên, nhãn, mô tả, loại nội dung và đơn vị từ metadata.
5. Bật hoặc tắt stack trace bằng `@StackTrace` và `Recording.enable(...).withStackTrace()/withoutStackTrace()`; kiểm tra `RecordedEvent.getStackTrace()`, kể cả trường hợp `null`.
6. Viết chương trình **Java 11 hoàn chỉnh**, ghi file `.jfr` bằng `Recording.dump`, đọc bằng `RecordingFile.readAllEvents` và xác nhận **stdout chính xác**.
7. Thiết kế custom event hữu ích, giới hạn overhead/stack depth và tránh làm lộ dữ liệu nhạy cảm khi xuất recording.

**Phạm vi:** đây là bài về **JFR API metadata, units/content types và stack traces**, không phải hướng dẫn thay thế profiler tổng quát. Các lệnh `jfr metadata/print` chỉ là công cụ kiểm chứng thêm. Những chú ý an toàn áp dụng cả cho Java 11 và JDK mới.

---

## 1. Bốn tầng ý nghĩa của một sự kiện JFR

Xét ví dụ ghi sự kiện truyền dữ liệu:

```text
Sự kiện: demo.Transfer
  Nhãn: "Demo transfer"
  Category: Learning / Network

  bytes = 2048                     [@DataAmount(BYTES)]
  latencyMs = 12                   [@Timespan(MILLISECONDS)]
  observedEpochMs = 1700000000000 [@Timestamp(MILLISECONDS_SINCE_EPOCH)]
  successFraction = 0.75           [@Percentage]
  operation = "copy"               [String]
  stackTrace = ...                 [phụ thuộc event settings]
```

Một event có các tầng khác nhau:

| Tầng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Giá trị payload** | `bytes=2048L`, `successFraction=0.75` | Con số/chuỗi thực được ghi |
| **Metadata của type/field** | `@Label`, `@Description`, `@DataAmount(BYTES)` | Giúp công cụ phân tích hiểu và trình bày |
| **Recording settings** | `enabled`, `threshold`, `stackTrace` | Quyết định event có được thu và stack có được lưu |
| **Runtime context** | timestamp/duration, event thread, recorded stack frames | Được JFR lấy lúc thu event khi cấu hình cho phép |

**Metadata không thay đổi nội dung tính toán của chương trình.** `@Timespan(MILLISECONDS)` không tự biến `latencyMs=12` thành 12 nanosecond; nó mô tả rằng trường đó **mang đơn vị mili-giây** để consumer/formatter hiểu đúng. Tương tự `@Percentage` không nhân trường raw `0.75` thành `75.0` trong Java object; một công cụ hiển thị có thể định dạng thành **75%**.

**Stack trace không phải một field `String` thông thường.** JFR lưu nó dưới dạng cấu trúc có các Java frames khi event được thu cùng setting tương ứng. Một event vẫn có thể được ghi mà **không** có stack trace; consumer trả `null` trong trường hợp đó.

### Metadata là schema, không phải quyền truy cập hoặc mã hóa

Việc gắn `@Label("Customer ID")` lên một field không có nghĩa JFR sẽ mã hóa hoặc che ID đó. JFR metadata giúp mô tả, còn chính code và chính sách thu thập phải bảo vệ **token, password, email, dữ liệu người dùng và internal identifiers**.

## 2. Metadata ở mức event type

Các annotation cơ bản từ `jdk.jfr`:

| Annotation | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `@Name` | `@Name("demo.Transfer")` | Tên type ổn định để enable/filter |
| `@Label` | `@Label("Demo transfer")` | Nhãn dễ đọc trong JMC/JFR tools |
| `@Description` | `@Description("Tracks a sample transfer")` | Giải thích event được phát khi nào/để làm gì |
| `@Category` | `@Category({"Learning","Network"})` | Đường dẫn nhóm event trong UI/phân loại |
| `@StackTrace` | `@StackTrace(true)` | Đặt **mặc định** có stack trace hay không cho event type |
| `@Threshold` | `@Threshold("10 ms")` | Đặt mặc định ngưỡng duration để ghi event |
| `@Enabled` | `@Enabled(false)` | Đặt mặc định event có được enable không |
| `@Registered` | `@Registered(false)` | Điều khiển đăng ký event type khi cần thiết, không phải công cụ lọc business logic |

Ở bài này, ta cần rõ nhất **Name, Label, Description, Category và StackTrace**.

Ví dụ minh họa:

```java
@Name("demo.Transfer")
@Label("Demo transfer")
@Description("Tracks a sample transfer without personal data.")
@Category({"Learning", "Network"})
@StackTrace(true)
static final class Transfer extends Event {
    // Các field được khai báo bên dưới.
}
```

Đây là **đoạn minh họa bên trong lớp có chứa nested class**, chưa phải chương trình độc lập. Ví dụ hoàn chỉnh ở phần 7 sẽ có toàn bộ imports/methods.

### Tên có cấu trúc khác nhãn hiển thị

- `@Name("demo.Transfer")`: tên nhận diện event dùng trong `Recording.enable("demo.Transfer")` hoặc bộ lọc `jfr print --events demo.Transfer`.
- `@Label("Demo transfer")`: tên người đọc thấy trên giao diện; có thể thay đổi cách diễn đạt cho dễ hiểu.
- `@Description`: câu mô tả, nên nói rõ **đơn vị, lúc ghi và ý nghĩa trường**.
- `@Category`: các chuỗi tạo danh mục phân cấp, không tạo package/class Java mới.

Không nên đổi tùy tiện tên event trong các pipeline phân tích đang lọc theo string. Nếu schema là contract monitoring/analytics, hãy quản lý thay đổi tên/field tương tự versioning của một API.

### Những nội dung nên tránh trong metadata

Không nhúng secret, tên khách hàng hoặc dữ liệu request thật vào nhãn và mô tả của type. Thông tin đó có thể được ghi vào metadata recording và xuất hiện khi file được chia sẻ. Nhãn, category và description nên là **tĩnh, rõ ràng, ít nhạy cảm**.

## 3. Field metadata: nhãn, mô tả và kiểu dữ liệu

Event payload được viết bằng fields:

```java
@Label("Payload")
@Description("Size of payload transferred")
@DataAmount(DataAmount.BYTES)
long bytes;

@Label("Operation")
String operation;
```

Đây là các đoạn field khai báo bên trong class con của `Event`. Trong Java 11, các field có thể được ghi dưới dạng kiểu nguyên thủy như `boolean`, `int`, `long`, `double` và kiểu tham chiếu hỗ trợ gồm `String`, `Thread`, `Class`. **Array, enum hay object tùy ý không được ghi như payload JFR đơn giản chỉ vì field khai báo trong Event**; theo Javadoc, các loại reference không được hỗ trợ có thể bị bỏ qua.

Một số lưu ý:

- `static` fields không phải payload riêng của mỗi event.
- `transient` fields có thể được dùng để **loại khỏi event schema**.
- Đừng đưa `byte[]` chứa payload request rồi trông chờ JFR tự tuần tự hóa nó thành nội dung an toàn; thiết kế các field đo lường tổng hợp thay vì payload lớn.
- `@Label` trên field giúp người đọc hiểu nó, còn **tên Java field** vẫn dùng khi đọc bằng `RecordedObject.getLong("bytes")`.
- `@Description` nên giải thích ý nghĩa đo lường, ví dụ “số byte payload thực đã truyền, chưa gồm transport overhead” thay vì “data”.

### Các kiểu annotation không giống kiểu Java

Một trường `long bytes` vẫn có type `long`; `@DataAmount` là **metadata bổ sung**. Consumer có thể lấy:

- `ValueDescriptor.getTypeName()` → kiểu dữ liệu Java được JFR ghi.
- `ValueDescriptor.getName()` → tên field, ví dụ `bytes`.
- `ValueDescriptor.getLabel()` → nhãn người đọc.
- `ValueDescriptor.getDescription()` → mô tả.
- `ValueDescriptor.getContentType()` → định danh loại nội dung, ví dụ `jdk.jfr.DataAmount`.
- `ValueDescriptor.getAnnotation(DataAmount.class)` → annotation cụ thể có `value()` như `BYTES`.

**Content type và unit có liên hệ nhưng không giống nhau.** `getContentType()` cho biết trường là loại “lượng dữ liệu”; giá trị `@DataAmount.value()` cho biết đo bằng **BYTES** hay **BITS**.

## 4. Units và content types vẫn còn áp dụng trên Java hiện đại

### 4.1. `@DataAmount` — lượng dữ liệu

```java
@Label("Transferred bytes")
@DataAmount(DataAmount.BYTES)
long bytesTransferred;

@Label("Link capacity bits")
@DataAmount(DataAmount.BITS)
long bitsTransferred;
```

Cả hai field là `long`, nhưng chúng biểu diễn **đơn vị khác nhau**. `@DataAmount` có các hằng `BYTES` và `BITS`.

**Sai lầm:** truyền 1024 *bits* vào field có `@DataAmount(BYTES)` rồi nghĩ JFR tự chia 8. Nó **không sửa số**. Nếu field gắn BYTES, code phải ghi giá trị đã được tính theo bytes.

### 4.2. `@Timespan` — khoảng thời gian

```java
@Label("Latency")
@Timespan(Timespan.MILLISECONDS)
long latencyMs;
```

Các unit có từ Java 11 gồm `NANOSECONDS`, `MICROSECONDS`, `MILLISECONDS`, `SECONDS` và `TICKS`. Trong demo, `latencyMs=12` có nghĩa **12 mili-giây**, không phải “12 lần gọi” hoặc “12 nanosecond”.

**Điểm dễ nhầm:** duration **tự động** của Event khi dùng `event.begin()` và `event.end()` là đặc tính của bản ghi JFR. Field tùy chỉnh `latencyMs` là một **business metric khác**, có thể do code tính riêng. Hai giá trị không nhất thiết bằng nhau.

Nếu sử dụng `TICKS`, cần hiểu đó là đơn vị nội bộ với cơ chế timestamp của JVM/JFR, không phải số mili-giây epoch hoặc tick 100 ns được đảm bảo trên mọi nền tảng. Khi muốn một số mili-giây mà code có thể giải thích qua các JVM, dùng `Timespan.MILLISECONDS` với payload đúng unit.

### 4.3. `@Timestamp` — một thời điểm

```java
@Label("Observed at")
@Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)
long observedEpochMs;
```

Đây là **thời điểm tuyệt đối** tính từ Unix epoch theo milli-second, không phải duration. Java 11 hỗ trợ `Timestamp.MILLISECONDS_SINCE_EPOCH` và `Timestamp.TICKS`.

Ví dụ:

- `System.currentTimeMillis()` phù hợp khi muốn ghi timestamp epoch milliseconds.
- `System.nanoTime()` là nguồn đo thời gian **tương đối/monotonic**, **không** đại diện cho epoch timestamp; đừng gắn `MILLISECONDS_SINCE_EPOCH` cho raw `nanoTime()`.
- `event.getInstant("observedEpochMs")` bên consumer có thể diễn giải field theo annotation timestamp đã chọn.

**Phân biệt với `RecordedEvent.getStartTime()`:** getStartTime là timestamp JFR cho chính event; field `observedEpochMs` là một timestamp **do ứng dụng chủ động gán**. Hai giá trị không bắt buộc giống nhau.

### 4.4. `@Percentage` — tỉ lệ

```java
@Label("Success fraction")
@Percentage
double successFraction;
```

Thông thường giá trị raw là **phân số**, ví dụ `0.75` nghĩa **75%**, không phải `75.0`. Công cụ biểu diễn có thể hiển thị 75% khi nhận được content type `jdk.jfr.Percentage`. **Không tự động ép** giá trị vào khoảng 0..1; code của bạn vẫn phải xác định ý nghĩa và kiểm tra dữ liệu.

Ví dụ nếu gửi `75.0` vào `successFraction`, một formatter coi đó là phân số sẽ có thể hiển thị **7500%**. Đây là lỗi dữ liệu, không phải lỗi JFR.

### 4.5. Các content type khác

JFR còn có annotations như:

| Annotation | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `@Frequency` | Tần số đo theo Hz | Dùng khi payload thật sự là frequency |
| `@MemoryAddress` | Địa chỉ bộ nhớ | Có thể nhạy cảm và có ý nghĩa rất phụ thuộc runtime |
| `@Unsigned` | Giá trị được hiểu theo kiểu không dấu | Không có nghĩa Java tự đổi `long` thành `BigInteger` |
| `@TransitionFrom` / `@TransitionTo` | Quan hệ chuyển trạng thái liên quan thread | Dùng theo ngữ nghĩa của JFR |
| `@ContentType` | Meta-annotation nhận diện annotation biểu thị content type | Dùng khi tự định nghĩa content type phù hợp hệ thống |

**Không áp cùng lúc nhiều content type xung đột** lên một field mà không có hợp đồng rõ ràng. Mục đích là giúp consumer hiển thị đúng ý nghĩa, không phải trang trí annotation càng nhiều càng tốt.

### 4.6. Tự định nghĩa content type

Với metadata phức tạp, JFR cho phép định nghĩa **annotation của riêng bạn**, và các meta-annotations như `@ContentType`/`@MetadataDefinition` giúp runtime nhận diện và giữ thông tin có ý nghĩa. Đây là API hiện hành nhưng đòi hỏi kiểm tra retention/target và tương thích tool/phân tích.

Trước khi tạo một content type mới, hãy cân nhắc có dùng được các loại chuẩn `DataAmount`, `Timespan`, `Timestamp`, `Percentage` không. Một đơn vị riêng khó được JMC hoặc mọi consumer hiểu ngay như những content type chuẩn.

**Không nhầm `@ContentType` với việc serializing field.** Nó mô tả cách **diễn giải** một giá trị đã được JFR lưu, chứ không biến object tùy ý thành dữ liệu ghi được.

## 5. Metadata và API phản chiếu của JFR

Có hai nơi đọc metadata:

**A. Trong JVM khi event type đã được khai báo**

```java
EventType type = EventType.getEventType(Transfer.class);
System.out.println(type.getName());
System.out.println(type.getLabel());
System.out.println(type.getCategoryNames());

for (ValueDescriptor field : type.getFields()) {
    System.out.println(field.getName());
    System.out.println(field.getContentType());
}
```

**Đây chỉ là đoạn minh họa**: cần event class `Transfer` được khai báo như ví dụ đầy đủ bên dưới, import `EventType`/`ValueDescriptor` và chạy trong một method.

**B. Trong file recording đã được xuất**

```java
for (RecordedEvent event : RecordingFile.readAllEvents(path)) {
    EventType eventType = event.getEventType();
    // Metadata vẫn có thể dùng qua eventType.getFields().
}
```

Đoạn này cần `Path path` trỏ tới một file `.jfr` hợp lệ, imports và xử lý `IOException`. Khi phân tích recording trong JVM khác với JVM tạo recording, metadata trong file giúp consumer hiểu tên và loại field **mà không cần load lại mã application event class**.

### `EventType`: thông tin mức event

| API | Ví dụ ý nghĩa |
| --- | --- |
| `getName()` | `demo.Transfer` |
| `getLabel()` | `Demo transfer` |
| `getDescription()` | Mô tả ứng dụng đã định nghĩa |
| `getCategoryNames()` | `["Learning", "Network"]` |
| `getFields()` | Các `ValueDescriptor` của payload và field hệ thống |
| `getSettings()` | Descriptors cho các setting của event type |
| `getAnnotationElements()` | Các metadata annotations để tool phân tích |

**Đừng dựa vào event type ID** làm định danh ổn định giữa các JVM/recordings. Nếu xây pipeline phân tích, ưu tiên tên event có namespace và schema do bạn quản lý; ID là chi tiết runtime và có thể thay đổi.

### `ValueDescriptor`: thông tin mức field

Các method tiêu biểu:

```java
ValueDescriptor bytes = requireField(type, "bytes");
String label = bytes.getLabel();
String description = bytes.getDescription();
String contentType = bytes.getContentType();

DataAmount amount = bytes.getAnnotation(DataAmount.class);
String unit = amount.value(); // "BYTES" trong ví dụ này
```

Đây là đoạn minh họa sử dụng helper `requireField` ở chương trình hoàn chỉnh. `getAnnotation(...)` có thể trả **null** nếu annotation không có; code production nên kiểm tra trước khi gọi `value()`.

**Phân biệt `null` một cách chính xác:**

- Field không có content type: `getContentType()` có thể là `null`.
- Field không có annotation mong đợi: `getAnnotation(...)` có thể là `null`.
- Event không được ghi stack: `RecordedEvent.getStackTrace()` là `null`.

Không coi các giá trị `null` này đương nhiên là lỗi file. Có khi đó là lựa chọn schema/recording hoàn toàn hợp lệ.

## 6. Stack trace: annotation mặc định và setting thực tế

Stack trace cho biết **chuỗi phương thức Java** ở thời điểm JFR ghi event. Nó giúp trả lời “ai đã phát event?” hoặc “mã đang chạy ở đường gọi nào?”, nhưng không phải toàn bộ lịch sử xử lý của request và không tự bao gồm tất cả các thread liên quan.

### 6.1. `@StackTrace` đặt mặc định của event

```java
@Name("demo.Transfer")
@StackTrace(true)
static final class Transfer extends Event {
    long bytes;
}
```

Annotation `@StackTrace(true)` xác định **default event setting**. Nó không bảo đảm mọi recording đều giữ stack: cấu hình của một recording cụ thể có thể **ghi đè** mặc định.

### 6.2. Điều khiển bằng Recording/EventSettings

```java
try (Recording recording = new Recording()) {
    recording.enable(Transfer.class)
            .withThreshold(Duration.ZERO)
            .withStackTrace();

    recording.enable(NoStack.class)
            .withoutStackTrace();

    recording.start();
    // Sinh các events...
    recording.stop();
}
```

Đây là **đoạn minh họa**, thiếu định nghĩa Transfer/NoStack và sinh event. Trong ví dụ hoàn chỉnh, cả hai type đều có `@StackTrace(true)` nhưng recording **tắt** stack đối với `NoStack` bằng `withoutStackTrace()`. Điều này làm rõ **cấu hình recording có thể ghi đè default annotation**.

Những APIs vẫn hiện hành trên Java 11+:

| API | Kết quả |
| --- | --- |
| `@StackTrace(true/false)` | Default stack trace của event type |
| `EventSettings.withStackTrace()` | Bật thu stack cho type trong recording |
| `EventSettings.withoutStackTrace()` | Tắt thu stack cho type trong recording |
| `EventSettings.withThreshold(Duration)` | Chỉ ghi event đáp ứng ngưỡng duration |
| `RecordedEvent.getStackTrace()` | `RecordedStackTrace` hoặc `null` |
| `RecordedStackTrace.getFrames()` | Danh sách `RecordedFrame` |
| `RecordedStackTrace.isTruncated()` | Cho biết stack có bị cắt ngắn do giới hạn không |

**Chi phí:** stack collection có overhead (CPU, memory, tệp JFR) và có thể làm file lớn. Với event rất dày, không bật stack cho mọi occurrence nếu không cần. Điều chỉnh thresholds/sampling/duration theo mục tiêu đo và chính sách vận hành.

### 6.3. Stack trace của event được ghi khi nào?

Theo mô tả API, JFR chụp stack trace khi event được **commit** (nếu bật). Vì vậy đừng nhầm stack này với stack ở thời điểm `begin()`, cũng đừng suy rằng nó bao quát tất cả phương thức đã chạy **trong suốt duration** của event.

Nếu event được tạo trong wrapper/helper, các frames trên cùng có thể là helper ấy. Khi một công cụ lọc stack, việc bỏ các frames không cần thiết là công đoạn phân tích, **không phải thay đổi bản chất event**.

### 6.4. Vì sao stack có thể `null` hoặc không đầy đủ?

- Recording đã cấu hình `withoutStackTrace()`.
- Event mặc định không ghi stack hoặc bị settings override.
- Event không được enable hoặc không được ghi do threshold → thậm chí không có `RecordedEvent` để đọc.
- JFR bị giới hạn depth, stack có thể **truncated**.
- Consumer/JVM/runtime khác có thể cung cấp frames khác nhau (compiler optimization, inlining, async processing).

**Không assert số lượng frames chính xác** trên mọi JDK. Test nên xác minh **stack tồn tại và có ít nhất một frame** khi bật, hoặc `getStackTrace()==null` khi tắt trên fixture kiểm soát.

### 6.5. `RecordedFrame` và độ sâu

Khi cần phân tích:

```java
RecordedStackTrace trace = event.getStackTrace();

if (trace != null) {
    boolean truncated = trace.isTruncated();
    for (RecordedFrame frame : trace.getFrames()) {
        String method = frame.getMethod().getName();
        // Phân tích method, không mặc định mọi frame đều giống nhau.
    }
}
```

Đây là đoạn minh họa cần `RecordedEvent event` và imports `RecordedStackTrace`/`RecordedFrame`. Stack frames có thể trỏ tới method/class metadata, line number hoặc thông tin khác. Đừng log nguyên stack trace cho các request nhạy cảm nếu không được phép; class/method names và đường dẫn gọi có thể là dữ liệu nội bộ.

**Stack depth khác việc bật/tắt stack.** Tăng giới hạn depth (qua JFR options/config tùy JDK) có thể giúp điều tra call path sâu hơn nhưng cũng tăng chi phí/tệp. Dù depth lớn, không có bảo đảm mọi ngăn xếp được tái dựng chính xác khi runtime tối ưu hóa.

## 7. Chương trình hoàn chỉnh Java 11: metadata + units + stack on/off

Chương trình dưới đây dùng **Java SE** và module `jdk.jfr`, không cần HTTP server, database hoặc thư viện ngoài. Nó:

1. Định nghĩa hai event types `demo.Transfer` và `demo.NoStack`.
2. Dùng `@Label/@Description/@Category` trên event; `@DataAmount/@Timespan/@Timestamp/@Percentage` trên fields.
3. Lấy metadata ngay trong JVM qua `EventType.getEventType` và `ValueDescriptor`.
4. Tạo recording, bật cả hai event; ghi stack cho Transfer, **tắt stack cho NoStack**.
5. Ghi transfer event với values ổn định, có duration và một event NoStack.
6. `Recording.dump` ra file tạm, đọc lại bằng `RecordingFile.readAllEvents`.
7. Kiểm tra unit conversion của `getDuration(field)` và `getInstant(field)`, cùng stack presence/absence.

### 7.1. Tệp `JfrMetadataDemo.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
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
import jdk.jfr.StackTrace;
import jdk.jfr.Timespan;
import jdk.jfr.Timestamp;
import jdk.jfr.ValueDescriptor;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrMetadataDemo {
    @Name("demo.Transfer")
    @Label("Demo transfer")
    @Description("Tracks a sample transfer without personal data.")
    @Category({"Learning", "Network"})
    @StackTrace(true)
    static final class Transfer extends Event {
        @Label("Payload")
        @Description("Size of payload transferred")
        @DataAmount(DataAmount.BYTES)
        long bytes;

        @Label("Latency")
        @Timespan(Timespan.MILLISECONDS)
        long latencyMs;

        @Label("Observed")
        @Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)
        long observedEpochMs;

        @Label("Success fraction")
        @Percentage
        double successFraction;

        @Label("Operation")
        String operation;
    }

    @Name("demo.NoStack")
    @Label("Demo without stack")
    @StackTrace(true)
    static final class NoStack extends Event {
        @Label("Sequence")
        long sequence;
    }

    private static ValueDescriptor requireField(
            EventType type, String field) {
        for (ValueDescriptor value : type.getFields()) {
            if (value.getName().equals(field)) {
                return value;
            }
        }
        throw new AssertionError("Missing field " + field);
    }

    public static void main(String[] args) throws Exception {
        EventType type = EventType.getEventType(Transfer.class);
        ValueDescriptor bytes = requireField(type, "bytes");
        ValueDescriptor latency = requireField(type, "latencyMs");
        ValueDescriptor observed = requireField(type, "observedEpochMs");
        ValueDescriptor fraction = requireField(type, "successFraction");

        System.out.println("type=" + type.getName());
        System.out.println("label=" + type.getLabel());
        System.out.println("category="
                + String.join("/", type.getCategoryNames()));
        System.out.println("bytesContentType=" + bytes.getContentType());
        System.out.println("bytesUnit="
                + bytes.getAnnotation(DataAmount.class).value());
        System.out.println("latencyUnit="
                + latency.getAnnotation(Timespan.class).value());
        System.out.println("timestampUnit="
                + observed.getAnnotation(Timestamp.class).value());
        System.out.println("ratioContentType="
                + fraction.getContentType());

        Path file = Files.createTempFile("jfr-metadata-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(Transfer.class)
                        .withThreshold(Duration.ZERO)
                        .withStackTrace();
                recording.enable(NoStack.class)
                        .withThreshold(Duration.ZERO)
                        .withoutStackTrace();
                recording.start();

                Transfer transfer = new Transfer();
                transfer.bytes = 2048L;
                transfer.latencyMs = 12L;
                transfer.observedEpochMs = 1700000000000L;
                transfer.successFraction = 0.75d;
                transfer.operation = "copy";
                transfer.begin();
                Thread.sleep(15);
                transfer.end();
                transfer.commit();

                NoStack noStack = new NoStack();
                noStack.sequence = 1L;
                noStack.commit();

                recording.stop();
                recording.dump(file);
            }

            List<RecordedEvent> events =
                    RecordingFile.readAllEvents(file);
            RecordedEvent transfer = null;
            RecordedEvent noStack = null;
            for (RecordedEvent event : events) {
                if ("demo.Transfer".equals(event.getEventType().getName())) {
                    transfer = event;
                }
                if ("demo.NoStack".equals(event.getEventType().getName())) {
                    noStack = event;
                }
            }
            if (transfer == null || noStack == null) {
                throw new AssertionError("Recorded events missing");
            }

            System.out.println("recordedBytes="
                    + transfer.getLong("bytes"));
            System.out.println("recordedLatencyMs="
                    + transfer.getDuration("latencyMs").toMillis());
            System.out.println("timestampCorrect="
                    + Instant.ofEpochMilli(1700000000000L)
                        .equals(transfer.getInstant("observedEpochMs")));
            System.out.println("fraction="
                    + transfer.getDouble("successFraction"));
            System.out.println("eventDurationPositive="
                    + (transfer.getDuration().toNanos() > 0));
            System.out.println("stackEnabled="
                    + (transfer.getStackTrace() != null
                        && !transfer.getStackTrace()
                            .getFrames().isEmpty()));
            System.out.println("stackDisabled="
                    + (noStack.getStackTrace() == null));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

### 7.2. Biên dịch/chạy

Lưu đúng tên `JfrMetadataDemo.java` vào một thư mục thử nghiệm. Trên JDK 11 hoặc JDK mới hơn:

```bash
javac --release 11 -encoding UTF-8 JfrMetadataDemo.java
java JfrMetadataDemo
```

**Stdout chính xác đã được kiểm tra với `javac --release 11` và chạy trên một JDK hiện đại:**

```text
type=demo.Transfer
label=Demo transfer
category=Learning/Network
bytesContentType=jdk.jfr.DataAmount
bytesUnit=BYTES
latencyUnit=MILLISECONDS
timestampUnit=MILLISECONDS_SINCE_EPOCH
ratioContentType=jdk.jfr.Percentage
recordedBytes=2048
recordedLatencyMs=12
timestampCorrect=true
fraction=0.75
eventDurationPositive=true
stackEnabled=true
stackDisabled=true
```

**Đây là output đã chạy thực tế**, không phải dự đoán. Mã dùng đúng API Java 11 để compile, tạo/đọc recording bằng chính JVM, kiểm chứng **cả metadata và các sự kiện trong file**. Giá trị timestamp cố định `1700000000000L` được dùng làm fixture kiểm thử, **không được hiểu là thời điểm máy thực sự chạy**.

### 7.3. Giải thích dòng kết quả

- `type=demo.Transfer` lấy từ `@Name`, không suy từ class simple name.
- `label=Demo transfer` lấy từ `@Label` trên event.
- `category=Learning/Network` là `String.join("/", type.getCategoryNames())`; API thực trả về một danh sách, không phải chuỗi đường dẫn duy nhất.
- `bytesContentType=jdk.jfr.DataAmount` chỉ ra field `bytes` được xem là content type **data amount**.
- `bytesUnit=BYTES` đọc từ `@DataAmount.value()`. Nếu đổi annotation sang BITS, code phải đổi cách tính giá trị cho đúng.
- `latencyUnit=MILLISECONDS` được gắn với `@Timespan(MILLISECONDS)`.
- `timestampUnit=MILLISECONDS_SINCE_EPOCH` xác nhận cách diễn giải field thời điểm.
- `ratioContentType=jdk.jfr.Percentage` là gợi ý để formatter hiểu `0.75` tương đương **75%**.
- `recordedBytes=2048` là **giá trị raw**, không phải text “2 KiB” do formatter tạo.
- `recordedLatencyMs=12` được đọc bằng `RecordedObject.getDuration("latencyMs")` rồi `toMillis()`.
- `timestampCorrect=true` được tính khi `RecordedObject.getInstant("observedEpochMs")` khớp fixture `Instant.ofEpochMilli(...)`.
- `fraction=0.75` chứng minh người đọc nhận giá trị raw, dù content type hướng dẫn format tỉ lệ.
- `eventDurationPositive=true` kiểm chứng JFR `begin/end` có duration, **độc lập với field `latencyMs`**.
- `stackEnabled=true`: event Transfer có stack trace **không rỗng**.
- `stackDisabled=true`: NoStack event vẫn được ghi nhưng `getStackTrace() == null`. Nó chứng minh recording setting `withoutStackTrace()` thực sự ghi đè mặc định `@StackTrace(true)` trong fixture.

### 7.4. Vì sao có thể đọc metadata trước khi recording?

`EventType.getEventType(Transfer.class)` trả metadata về **loại sự kiện đã đăng ký**; không cần chờ một file `.jfr` được dump mới đọc được tên field. Khi consumer mở file, `RecordedEvent.getEventType()` cho biết metadata được ghi kèm recording.

Đây là lý do metadata phải **ổn định về tên và kiểu** nếu nhiều phiên bản ứng dụng ghi file mà một dashboard phân tích chung. Đổi từ bytes sang bits nhưng vẫn dùng cùng tên field sẽ tạo một thay đổi ngữ nghĩa khó phát hiện.

### 7.5. Vì sao `@StackTrace(true)` không đồng nghĩa luôn có stack?

Chương trình cố ý khai báo cả hai type có `@StackTrace(true)`, nhưng:

```java
recording.enable(Transfer.class).withStackTrace();
recording.enable(NoStack.class).withoutStackTrace();
```

Nên chỉ Transfer có stack trong recording đang kiểm thử. Tương tự, một recording có thể dùng `withThreshold(Duration.ofMillis(10))` để không ghi những event ngắn hơn ngưỡng — khi event không được ghi, consumer **không có RecordedEvent** để gọi `getStackTrace()`.

### 7.6. Vì sao ví dụ không cố định số stack frames?

Số frames phụ thuộc runtime, inlining, helper call, stack depth configuration và cách event được commit. Chúng có thể khác nhau giữa Java 11 và JDK mới. Ví dụ chỉ kiểm tra **non-null và non-empty** cho một event được bật stack, và **null** cho event bị tắt, tránh assert một danh sách method cụ thể có thể không ổn định.

## 8. Công cụ ngoài chương trình: jfr metadata và jfr print

Nếu muốn kiểm tra bằng dòng lệnh thay vì consumer API, bạn có thể xuất recording ra tệp có tên dễ nhớ rồi dùng JDK `jfr`. Trong chương trình chính, file tạm được xóa ở `finally` để không để lại artifact; muốn quan sát thủ công, có thể **đổi file tạm thành một file cố định phục vụ test** trước khi xóa.

Ví dụ khi đã có file `demo.jfr`:

```bash
jfr summary demo.jfr
jfr metadata demo.jfr
jfr print --events demo.Transfer demo.jfr
jfr print --events demo.Transfer --stack-depth 10 demo.jfr
```

Các lệnh thuộc JDK có hỗ trợ công cụ `jfr`; khi dùng runtime Java 11 hoặc JDK mới, tra cứu `jfr help`/`jfr help metadata` để xác nhận cú pháp phiên bản thực tế.

| Lệnh | Dùng để làm gì |
| --- | --- |
| `jfr summary` | Thống kê event types và số bản ghi |
| `jfr metadata` | Xem event schema, fields, annotations, categories |
| `jfr print --events ...` | In những events thuộc type cần điều tra |
| `--stack-depth N` | Giới hạn số frames **hiển thị trong output công cụ** |

**Phân biệt:** `--stack-depth 10` trong công cụ print **không làm JVM quay ngược thời gian thu thêm frames đã không được ghi**. Việc thu stack xảy ra khi event commit và phải được enable từ recording. Nếu file vốn không có stack, tăng số frame hiển thị không thể tái tạo stack bị thiếu.

### JDK Mission Control

[JDK Mission Control (JMC)](https://openjdk.org/projects/jmc/) có thể trình bày event types, metadata, durations, histogram, flame graph/stack theo chức năng của bản JMC. Các nhãn và content types giúp hiển thị dễ hiểu hơn, nhưng **mức hỗ trợ custom annotations và đơn vị phụ thuộc bản tool**. Không dựa vào giao diện mà quên kiểm tra raw values khi cần tính toán chính xác.

## 9. Những tính năng có liên quan nhưng không thay thế metadata

### `Event.begin()` và `Event.end()`

Sử dụng khi cần đo một thao tác kéo dài:

```java
Transfer event = new Transfer();
event.bytes = 2048L;

event.begin();
try {
    // Thực hiện tác vụ thực.
} finally {
    event.end();
    event.commit();
}
```

Đây là đoạn minh họa cần event class và imports từ ví dụ trên. Nếu bạn muốn ghi **chỉ khi duration đạt threshold**, có thể kiểm tra `event.shouldCommit()` trước khi thực hiện thao tác **thu thập payload đắt tiền**. Trong ví dụ, `bytes` được gán trước; với production phải tính giá trị sau khi thực sự biết số bytes.

**Duration JFR** từ begin/end khác với `@Timespan latencyMs` mà bạn tự ghi. Không gắn nhãn mili-giây cho duration của JFR chỉ vì ứng dụng có một field tên vậy; JFR có metadata/timebase riêng.

### `Event.isEnabled()` và `Event.shouldCommit()`

- `event.isEnabled()` cho biết event type có được enable trong ít nhất một recording đang chạy.
- `event.shouldCommit()` xét cả các yếu tố như threshold để quyết định có thể ghi event không.

Khi payload đắt tiền, một pattern thường dùng là:

```java
Transfer event = new Transfer();
event.begin();
// Làm công việc cần quan sát ...
event.end();

if (event.shouldCommit()) {
    event.bytes = computeBytesForRecording();
    event.commit();
}
```

Đây là **mã minh họa**: `computeBytesForRecording()` là hàm ứng dụng tự định nghĩa, không phải Java SE API. Không gọi việc tính payload nhạy cảm/đắt tiền khi chưa cần. Với nhiều recording và settings khác nhau, semantics enable/threshold có thể thay đổi; tránh coi `isEnabled()` và `shouldCommit()` là những cache bất biến cho suốt đời JVM.

### Event thread và stack trace

`RecordedEvent.getThread()` và `getStackTrace()` là hai trường khác nhau. Có thể có thread metadata nhưng **không có stack**. Ngược lại, một stack được chụp trong thread commit event không đại diện tự động cho **toàn bộ chuỗi xử lý async** của một yêu cầu đã đi qua nhiều thread.

Nếu cần correlation giữa các tác vụ async, có thể thiết kế một **correlation ID không nhạy cảm** trong event payload và quản lý nó theo context; không suy ra rằng stack sẽ tự chứa request ID. Cân nhắc hashing/aggregation nếu ID có thể được dùng để liên kết tới một cá nhân.

## 10. Thiết kế schema JFR có chất lượng

Một custom event hữu ích nên có:

| Thành phần | Tiêu chí |
| --- | --- |
| Name | Có namespace, dễ lọc và ổn định, ví dụ `com.example.CacheMiss` |
| Label | Ngắn và đủ diễn giải |
| Description | Nói khi nào event được commit và đo điều gì |
| Category | Nhóm hợp lý, không quá nhiều cấp |
| Field name | Thống nhất convention, ví dụ `bytesWritten`, `durationMs` |
| Field type | Java primitive/String/Thread/Class được JFR hỗ trợ |
| Unit | Chính xác với raw payload, ví dụ `BYTES` hay `MILLISECONDS` |
| Content type | Có annotation giúp formatter/consumer hiểu số liệu |
| Stack trace | Chỉ thu nếu cần nguồn gốc call path |
| Threshold | Không ghi vô tội vạ mọi thao tác có duration rất ngắn |
| Sensitivity | Không ghi secret, token, payload hoặc PII không cần thiết |
| Versioning | Có kế hoạch khi đổi field/semantics/danh mục |

### Quy tắc không đổi đơn vị ngầm

Nếu phiên bản A ghi `latencyMs=12` với `@Timespan(MILLISECONDS)`, phiên bản B không nên đột ngột ghi `12` nano-giây nhưng vẫn giữ tên/annotation cũ. Nếu thay đổi thật sự, hãy đổi tên field hoặc version schema theo một contract rõ ràng để không làm sai dashboard phân tích dữ liệu lịch sử.

### Quy tắc phần trăm

Nếu bạn dùng `@Percentage`, hãy quyết định contract là **fraction**, ví dụ 0.75 ↔ 75%; tài liệu hóa và test biên như 0, 1, values ngoài phạm vi nếu nghiệp vụ không cho phép. Chỉ annotation **không phải validation**.

### Content types tự định nghĩa

Chỉ tạo custom `@ContentType` khi formatter/analytics của bạn **thực sự hiểu** kiểu đó. Với dữ liệu quen thuộc, dùng annotation tiêu chuẩn để tăng khả năng tương tác giữa các công cụ, recording và JDK.

## 11. Bảo mật, chi phí và giới hạn của stack trace

Một stack trace có thể tiết lộ:

- Tên package/class/method nội bộ.
- Đường đi thực thi qua framework, tên method nghiệp vụ.
- Thông tin về thư viện, kiến trúc và những điểm xử lý nhạy cảm.
- Kết hợp với metadata khác có thể giúp suy luận về request/tenant.

JFR không tự xóa những thông tin này theo một quy tắc bảo mật của ứng dụng. Trong production:

1. Chỉ bật stack cho **event types cần điều tra**; ghi lại lý do sử dụng.
2. Đặt `threshold` cho events có duration và volume cao để giảm noise.
3. Dùng recording settings `default`/`profile` phù hợp, theo dõi overhead thực tế.
4. Hạn chế stack depth/retention và dung lượng repository/file, không thu dữ liệu vô hạn.
5. Không ghi credentials, auth headers, secret tokens, payload JSON, SQL chứa PII hoặc private identifiers.
6. Bảo vệ file `.jfr` bằng quyền truy cập, mã hóa lưu trữ/chuyển file và chính sách retention.
7. Khi cần chia sẻ recording với bên thứ ba, kiểm tra schema/payload và stack trước khi cung cấp.
8. Không coi `@Label` hay `@Description` là cơ chế che dữ liệu; chúng chỉ là metadata.
9. Với event rất dày, đo cả CPU allocation của producer và chi phí xử lý của JFR.
10. Tránh ghi ra logging đầy đủ của mỗi JFR event một cách vô điều kiện: việc tạo log có thể đắt hơn việc thu event.

**Stack trace có thể bị cắt:** API `RecordedStackTrace.isTruncated()` giúp nhận biết giới hạn độ sâu, nhưng không thể tái tạo frames đã bị thiếu sau khi recording hoàn tất. Khác biệt JDK/vendor/provider, JIT và tối ưu hóa có thể khiến những stack frames chi tiết không hoàn toàn giống nhau.

### Xử lý multi-thread/async

Nếu một tác vụ được tạo ở thread A, chuyển qua queue và commit event ở thread B, JFR stack tại commit **thường phản ánh thread B**. Muốn hiểu toàn bộ hành trình, cần correlation/tracing nghiệp vụ, không mặc định JFR stack chứa đầy đủ call chain qua ranh giới async.

## 12. Lỗi phổ biến và cách khắc phục

| Sai lầm | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| Ghi `2048` nhưng không có unit | Người đọc không biết bytes/bits | `@DataAmount(BYTES)` và description rõ |
| Gắn `@DataAmount(BYTES)` lên giá trị thực đo bằng bits | Metadata nói sai, JFR không tự chia 8 | Chuyển số hoặc sửa annotation |
| Gắn `@Timespan(MILLISECONDS)` cho một số nano-giây | Consumer giải thích sai duration | Đảm bảo đúng time unit |
| Dùng `System.nanoTime()` làm epoch milliseconds | nanoTime là mốc tương đối | Dùng epoch millis khi khai báo `@Timestamp(MILLISECONDS_SINCE_EPOCH)` |
| Dùng `@Percentage` nhưng gán 75 thay vì 0.75 | Formatter có thể hiển thị 7500% | Contract fraction và validation |
| Tưởng `getContentType()` luôn có chuỗi | Field thường có thể không có content type | Xử lý `null` |
| Tưởng `getAnnotation(...)` luôn non-null | Annotation có thể không tồn tại | Kiểm tra null |
| Cho rằng `@StackTrace(true)` bắt buộc lưu stack | Recording settings có thể override | Xem `withStackTrace/withoutStackTrace` |
| Tưởng event không có stack đồng nghĩa event không được ghi | Event vẫn có thể tồn tại với stack null | Kiểm tra `RecordedEvent` và settings riêng |
| Tưởng `getStackTrace()` luôn non-null | Stack có thể bị tắt hoặc không có | Kiểm tra null trước `getFrames()` |
| Assert chính xác N stack frames trên mọi JDK | Optimizations và cấu hình khác nhau | Kiểm tra các bất biến phù hợp |
| Tưởng `--stack-depth 100` bổ sung frames không được lưu | Chỉ thay cách **in** dữ liệu đã có | Bật ghi stack trước khi commit |
| Ghi field kiểu `List`, `Map` hay `byte[]` và nghĩ JFR tự serialize | Event payload JFR chỉ hỗ trợ một số kiểu field | Dùng numeric/String/Thread/Class fields hoặc aggregate |
| Ghi static field mong xuất thành payload từng event | Static không là field bản ghi | Dùng instance field được hỗ trợ |
| Coi metadata là cơ chế xác thực/mã hóa | Nhãn/mô tả không bảo vệ dữ liệu | Thiết kế privacy trước khi commit |
| Không test nội dung file sau dump | Compile không đảm bảo runtime JFR ghi đúng | Dùng RecordingFile/jfr print kiểm chứng |
| Dùng EventType ID làm khóa ổn định giữa JVM | ID có thể thay đổi | Dùng event name + schema/version |
| Bật stack cho event 100k lần/giây không đo overhead | CPU/disk tăng và nhiều noise | Threshold, sampling, chọn event cần stack |
| Nhầm event duration với field latencyMs | Hai đồng hồ/ngữ nghĩa có thể khác | Đặt tên, annotation và test riêng |
| Chỉ test raw values, bỏ qua units/metadata | Dashboard có thể trình bày sai | Kiểm tra ValueDescriptor và content types |

## 13. Test tự động cho metadata và stack trace

Một bộ kiểm thử tốt cần cả **metadata QA** lẫn **recording QA**:

### A. Metadata schema test

- `EventType.getName()` khớp tên contract.
- `getLabel()`/`getDescription()`/`getCategoryNames()` rõ ràng.
- `getFields()` có các field mong đợi, type names đúng.
- `getContentType()` khớp những field có ý nghĩa đơn vị.
- `getAnnotation(DataAmount.class).value()` là `BYTES` hoặc `BITS` được thiết kế.
- `@Timespan/@Timestamp` khớp unit mà code thực sự ghi.
- `@Percentage` được dùng cho fraction 0..1 khi đó là contract.
- Không có fields nhạy cảm trong schema nếu chính sách cấm.

### B. Recording round-trip test

- Tạo recording chỉ enable các custom types cần test.
- Ghi event với fixture values ổn định.
- Dump ra file và đọc qua `RecordingFile.readAllEvents`.
- Lọc theo event name, không assert thứ tự xuất hiện nếu không cần.
- Đối chiếu raw bytes, duration unit, timestamp unit và fraction.
- Đối chiếu `getDuration()` của event > 0 nếu test có thời gian chạy cụ thể.
- Xác nhận khi stack on thì `getStackTrace()!=null`/frames nonempty theo fixture.
- Xác nhận khi stack off thì `getStackTrace()==null`.
- Đóng `Recording` và dọn tệp tạm trong finally/teardown.

### C. Kiểm thử cross-JDK

- Biên dịch với `javac --release 11` khi ứng dụng yêu cầu API Java 11.
- Nếu **cam kết chạy runtime Java 11**, cần thực sự chạy test trên JDK 11; chỉ compile với `--release 11` trên JDK mới là chưa đủ.
- Chạy thêm trên phiên bản JDK production hiện tại để phát hiện khác biệt provider/settings/stack frames.
- Không dựa vào thứ tự toàn bộ event trong file JFR hoặc ID nội bộ.
- Kiểm tra phân tích file trên công cụ JFR/JMC mục tiêu, đặc biệt custom metadata.
- Nếu API/tool mới chỉ tồn tại từ JDK mới hơn, đặt một test tách riêng và nâng baseline có chủ đích, không trộn vào bài Java 11.

### Kết quả ổn định và không ổn định

| Có thể dùng làm assertion | Không nên hardcode |
| --- | --- |
| Event name = `demo.Transfer` | JFR type ID dạng số qua mọi JVM |
| DataAmount unit = `BYTES` | Byte-size của file .jfr |
| Latency unit = `MILLISECONDS` | Số event hệ thống do JVM tự phát |
| Raw bytes = 2048 | Thời điểm timestamp hiện tại của máy |
| Recorded timestamp matches fixed fixture | PID, process path và runtime hostname |
| Transfer stack present; NoStack absent | Số stack frames và absolute method line numbers |
| Recording read succeeds | Thứ tự các event types ngoài logic fixture |

## 14. Bài tập và đáp án

**Bài 1 — Content type.** Field `bytes` có `@DataAmount(BYTES)`, `ValueDescriptor.getContentType()` có thể trả gì? **`jdk.jfr.DataAmount`**; `getAnnotation(DataAmount.class).value()` là **`BYTES`**.

**Bài 2 — Duration.** `latencyMs=12` và `@Timespan(MILLISECONDS)` có nghĩa bao nhiêu giây? **0,012 giây**. Điều đó không ép `RecordedEvent.getDuration()` bằng 12ms.

**Bài 3 — Timestamp.** Gắn `@Timestamp(MILLISECONDS_SINCE_EPOCH)` nhưng ghi raw `System.nanoTime()` có đúng không? **Không**. Dùng dữ liệu epoch milliseconds thật.

**Bài 4 — Percentage.** `successFraction=0.75` với `@Percentage` có thể được formatter hiển thị thế nào? **75%**, trong khi raw value vẫn là `0.75`.

**Bài 5 — Annotation vs settings.** Event có `@StackTrace(true)` nhưng recording gọi `withoutStackTrace()`. Khi đọc event đã ghi, `getStackTrace()` thế nào? **Có thể là null; trong fixture của bài là null**.

**Bài 6 — Duration vs stack.** `event.begin()`/`end()` đo duration; `getStackTrace()` thu stack tại điểm nào? **Khi commit** theo cách thu của JFR, không phải toàn bộ mọi hàm đã chạy giữa begin/end.

**Bài 7 — Field annotation.** Field không có `@Timespan`, `getAnnotation(Timespan.class)` trả gì? **null**, không tự quy định một đơn vị do tên field gợi ý.

**Bài 8 — Data unit.** Có thể ghi 8.000 bits vào `@DataAmount(BYTES)` và mong JFR tự đổi thành 1.000 bytes? **Không**; code phải tự chuyển đúng unit.

**Bài 9 — Stack depth.** `jfr print --stack-depth 100` có khôi phục frames chưa từng được ghi không? **Không**; nó chỉ thay số frames công cụ hiển thị từ dữ liệu có sẵn.

**Bài 10 — Type metadata.** Có thể đọc metadata trước khi start recording không? **Có**, qua `EventType.getEventType(YourEvent.class)` cho type đã đăng ký.

**Bài 11 — Serialization.** Nếu thêm `List<String> payload` trong Event, JFR có tự ghi toàn bộ list không? **Không** theo event field types được hỗ trợ. Nên ghi aggregate numeric hoặc chuỗi đã chọn lọc phù hợp privacy.

**Bài 12 — Async.** A tạo event, B commit sau khi xử lý qua thread pool. Stack trace có chứa đầy đủ call chain từ thread A không? **Không mặc định**. Cần correlation/tracing ở tầng ứng dụng.

### Checklist trước production

1. Tên event có namespace và schema ổn định?
2. Label/Description/Category mô tả đúng semantics?
3. Unit của raw values chính xác: bytes/bits, millis/nanos, epoch timestamp?
4. Percentage là fraction hay số đã nhân 100, có contract/test?
5. Có kiểm tra metadata qua EventType/ValueDescriptor?
6. Có phân biệt event duration, user field duration và timestamp?
7. Stack trace được bật/tắt theo đúng recording settings?
8. Có kiểm tra null/truncated stack và không hardcode frame count?
9. Event payload không chứa token/PII/secret không cần thiết?
10. Có đo overhead và đặt threshold/retention/file permissions?
11. Có test roundtrip Recording → .jfr → RecordingFile?
12. Có xác minh trên JDK 11 thật khi cam kết runtime Java 11?

## Tài liệu tham khảo

- [Oracle Java SE 11 — jdk.jfr package](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html): custom events, annotations, types và event settings.
- [Oracle Java SE 11 — Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html): begin/end/commit/shouldCommit và types được hỗ trợ.
- [Oracle Java SE 11 — DataAmount](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/DataAmount.html): BITS/BYTES và annotation metadata.
- [Oracle Java SE 11 — Timespan](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Timespan.html): time units cho field thời lượng.
- [Oracle Java SE 11 — Timestamp](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Timestamp.html): epoch-millis và ticks cho timestamp fields.
- [Oracle Java SE 11 — EventType](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventType.html): tên, category, fields và settings metadata.
- [Oracle Java SE 11 — ValueDescriptor](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/ValueDescriptor.html): content type/label/annotations của field.
- [Oracle Java SE 11 — EventSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): withStackTrace/withoutStackTrace/threshold.
- [Oracle Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): enable/start/stop/dump/close.
- [Oracle Java SE 11 — RecordedEvent](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): getEventType/getDuration/getStackTrace.
- [Oracle Java SE 11 — RecordedStackTrace](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedStackTrace.html): getFrames/isTruncated.
- [Oracle Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc và lọc sự kiện từ file JFR.
- [Oracle Java SE 25 — jdk.jfr package](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html): xác nhận hệ API JFR vẫn hiện hành.
- [Oracle Java SE 25 — jfr command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): jfr metadata/summary/print và stack-depth.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR được tích hợp trong OpenJDK từ Java 11.
- [JDK Mission Control](https://openjdk.org/projects/jmc/): giao diện phân tích, xem event metadata và stack.

**Kết luận:** metadata JFR **không chỉ là tên field**: `@DataAmount`, `@Timespan`, `@Timestamp` và `@Percentage` xác định **ý nghĩa/đơn vị của raw values**, giúp consumer và công cụ phân tích hiển thị đúng. `@StackTrace` chỉ đặt mặc định; `EventSettings.withStackTrace()/withoutStackTrace()` mới kiểm soát việc thu stack trong recording. Muốn kiểm chứng đúng, hãy đọc cả **EventType/ValueDescriptor metadata** và **RecordedEvent payload/stack** từ file `.jfr`, đồng thời quản lý overhead và quyền riêng tư.