# Đọc bản ghi JFR: Lọc theo loại, khoảng thời gian và ngữ cảnh (Java 11)

## 1. Vì sao phải lọc một bản ghi JFR?

Một file **JDK Flight Recorder (JFR)** có thể chứa hàng nghìn đến hàng triệu sự kiện từ JVM, JDK và ứng dụng: GC, CPU sampling, thread park, lock contention, file/socket I/O và custom events. Khi điều tra một sự cố, in ra toàn bộ `.jfr` thường tạo quá nhiều dữ liệu và che mất nguyên nhân.

Ba câu hỏi nền tảng:

1. **Loại sự kiện nào?** Ví dụ `jdk.GarbageCollection`, `jdk.SocketRead` hoặc custom type `lesson.Work`.
2. **Khoảng thời gian nào?** Chỉ quan tâm 10:02–10:05 UTC, hoặc khoảng trước/sau một đợt tăng latency.
3. **Ngữ cảnh nào?** Chỉ các event có `operation="load"`, `outcome="OK"`, cùng một correlation code an toàn, hoặc thuộc thread/stack/call site cần khảo sát.

Cách làm có hệ thống là **lọc theo phép giao (AND)** trên ba chiều, sau đó mới tổng hợp số lượng, duration, byte count hoặc phát hiện bất thường. Trong Java 11, bạn có thể dùng **`jdk.jfr.consumer.RecordingFile`** và **`RecordedEvent`** để đọc file JFR theo từng sự kiện, không cần nạp toàn bộ file vào heap.

**Mục tiêu bài học:** hiểu đúng type/time/context, sử dụng `Instant` và khoảng nửa mở `[from, to)`, kiểm tra field schema trước khi đọc, phân biệt start time với duration overlap, chạy ví dụ Java 11 hoàn chỉnh, dùng `jfr` CLI khi phù hợp, và tránh các lỗi performance/privacy/correlation.

**Phạm vi phiên bản:** JFR được tích hợp vào OpenJDK 11 theo JEP 328. `RecordingFile`, `RecordedEvent`, `EventType` và `RecordedThread` còn được hỗ trợ trên JDK hiện đại. Không dùng `RecordingStream` trong mã phải biên dịch `--release 11`: **JFR Event Streaming ra đời ở JDK 14 (JEP 349)**. Bài dùng API Java 11 và những quy tắc vẫn áp dụng hiện nay.

## 2. Sơ đồ đọc: file → event → predicate → kết quả

```text
                         incident.jfr
                              |
                    RecordingFile(path)
                              |
                       hasMoreEvents?
                              |
                          readEvent()
                              |
              +---------------+-----------------+
              |               |                 |
        Type predicate   Time predicate   Context predicate
       EventType.name    Instant [a,b)   event fields/thread
              |               |                 |
              +---------------+-----------------+
                              |
                  Tất cả điều kiện đúng?
                       /             \
                     KHÔNG           CÓ
                      |               |
                    bỏ qua     count / duration / sum
                              |
                       báo cáo tối thiểu
```

JFR event đã có **cấu trúc**, không nên parse output text của `RecordedEvent.toString()` như thể mỗi event là một dòng log ổn định. Dùng API lấy từng trường có kiểu rõ ràng.

Các lớp quan trọng trong Java 11:

| API | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `RecordingFile(Path)` | Mở một file `.jfr` | Chỉ đọc file từ nguồn đáng tin; đóng bằng try-with-resources |
| `hasMoreEvents()` | Kiểm tra còn event chưa đọc | Kết hợp với `readEvent()` |
| `readEvent()` | Đọc sự kiện kế tiếp | Có thể ném `IOException` khi file sai hoặc lỗi I/O |
| `RecordedEvent.getEventType()` | Lấy type metadata | `getName()` là định danh, không phải `getLabel()` |
| `RecordedEvent.getStartTime()` | `Instant` thời điểm bắt đầu | Tốt cho lọc theo thời gian bắt đầu |
| `RecordedEvent.getEndTime()` | `Instant` kết thúc | Với instant event, end = start |
| `RecordedEvent.getDuration()` | `Duration` của event | Không phải mọi loại event có duration hữu ích |
| `RecordedEvent.hasField(name)` | Kiểm tra schema có field không | Nên dùng trước khi đọc field giữa nhiều JDK/schema |
| `getString(name)`, `getInt(name)` | Đọc field có kiểu | Sai tên/kiểu có thể ném `IllegalArgumentException` |
| `RecordedEvent.getThread()` | Thread gắn với event, nếu có | Có thể là `null` |
| `RecordedEvent.getStackTrace()` | Stack trace, nếu được ghi | Có thể là `null` vì settings hoặc event type |
| `RecordingFile.readEventTypes()` | Xem type metadata trong file | Có thể dùng xác nhận schema trước khi lọc |
| `RecordingFile.readAllEvents(path)` | Nạp toàn bộ event thành `List` | Javadoc nói **không dành cho file lớn** |

Phân biệt **loại sự kiện** (được khai báo và metadata hóa khi ghi) với **bản ghi cụ thể** (có start time, thread, values). Bạn không thể lấy `event.getString("operation")` một cách an toàn trên mọi event type, bởi `jdk.GarbageCollection` chưa chắc có field `operation` của custom event.

## 3. Chọn đúng sự kiện bằng type name

### 3.1. Định danh type không phải label hoặc category

JFR có type name như:

```text
jdk.GarbageCollection
jdk.CPULoad
jdk.JavaMonitorEnter
jdk.SocketRead
lesson.Work
```

Với custom event:

```java
@Name("lesson.Work")
@Label("Synthetic Work")
@Category({"Application", "Diagnostics"})
static class WorkEvent extends Event {
    public String operation;
}
```

Đây là **trích đoạn** đặt trong một lớp Java khác; cần import `jdk.jfr.*`. Khi đọc, lọc đúng tên:

```java
if ("lesson.Work".equals(event.getEventType().getName())) {
    // Chỉ lúc này mới đọc schema riêng của lesson.Work.
}
```

`@Name` là **machine-readable identifier**. `@Label` là tên hiển thị; `@Category` là đường dẫn nhóm cho giao diện JFR. Filter theo label có thể bị hỏng khi người phát triển chỉnh văn bản trình bày; giữ type name cố định sẽ ổn định hơn cho consumer.

Không lọc bằng Java simple class name `WorkEvent` nếu `@Name` đã đặt tên khác. Khi không có `@Name`, type name thường dựa trên tên class đầy đủ, nhưng refactor package/class cũng có thể đổi tên và làm mất sự kiện trong truy vấn cũ.

### 3.2. Khác event type và event field

`jdk.CPULoad` là type; `jvmUser` hoặc `jvmSystem` là field theo schema của loại đó. `lesson.Work` là type; các field do bài học định nghĩa gồm `operation`, `context`, `outcome` và `units`.

Không dùng `hasField("outcome")` để đoán event là `lesson.Work`: nhiều loại khác cũng có thể có field cùng tên nhưng ý nghĩa/kiểu khác. **Kiểm tra type trước, sau đó mới kiểm tra field.**

Predicate chuẩn:

```java
if (!"lesson.Work".equals(event.getEventType().getName())) {
    continue;
}
if (!event.hasField("context") ||
    !event.hasField("operation") ||
    !event.hasField("outcome") ||
    !event.hasField("units")) {
    throw new IOException("Unexpected Work event schema");
}
```

Đây là **trích đoạn bên trong phương thức `throws IOException`**, có biến `RecordedEvent event` và nằm trong vòng lặp đọc. Chương trình hoàn chỉnh ở phần sau dùng đúng cách này.

### 3.3. Lọc một hoặc nhiều loại

Nếu cần GC và monitor contention:

```java
String name = event.getEventType().getName();
if (!"jdk.GarbageCollection".equals(name) &&
    !"jdk.JavaMonitorEnter".equals(name)) {
    continue;
}
```

Đây là **trích đoạn**, cho phép hai type (**OR**). Sau đó phải phân nhánh theo từng type để đọc đúng fields. Đừng chạy `getInt("units")` cho tất cả chỉ vì các type đã lọt qua filter.

Trong ứng dụng lớn có thể dùng một `Set<String>` immutable cho danh sách tên loại; nhưng tập tên phải đến từ cấu hình được duyệt, không cho user truyền regex/glob không giới hạn lên file khổng lồ mà không đặt quota.

## 4. Lọc theo khoảng thời gian: dùng `Instant` và biên rõ ràng

### 4.1. Biểu diễn mốc thời gian với múi giờ

`RecordedEvent.getStartTime()` trả `java.time.Instant`, đại diện một thời điểm trên trục thời gian, độc lập timezone hiển thị. Một API consumer nên nhận từ–đến ở format **ISO-8601 có offset**, rồi chuẩn hóa về `Instant`.

Ví dụ:

```java
Instant from = Instant.parse("2026-11-07T03:00:00Z");
Instant to = Instant.parse("2026-11-07T03:05:00Z");
```

Hai dòng là **trích đoạn**, cần `java.time.Instant`. Chỉ dùng **mốc thời gian minh họa**, không có file recording thật kèm theo. Hậu tố `Z` là UTC; khi người dùng nhập giờ địa phương, chuyển rõ qua `ZonedDateTime`/`OffsetDateTime` trước khi so với `Instant`. Tránh dùng chuỗi `"2026-11-07 10:00"` không timezone rồi đoán múi giờ của server.

### 4.2. Định nghĩa khoảng nửa mở `[from, to)`

Đối với lọc theo **thời điểm bắt đầu**:

- **Bao gồm** event nếu `start >= from`.
- **Loại** event nếu `start >= to`.
- Tương đương `!start.isBefore(from) && start.isBefore(to)`.
- Yêu cầu `from.isBefore(to)`; nếu ngược hoặc bằng nhau thì xử lý như input không hợp lệ hoặc kết quả rỗng theo hợp đồng API.

```java
Instant start = event.getStartTime();
boolean inWindow =
        !start.isBefore(from) && start.isBefore(to);
```

Khoảng nửa mở loại bỏ đếm trùng tại điểm nối hai khoảng:

```text
Window A: [10:00:00Z, 10:05:00Z)
Window B: [10:05:00Z, 10:10:00Z)

Event bắt đầu đúng 10:05:00Z:
  Không thuộc A
  Thuộc B
```

Nếu dùng cả hai đầu **đóng** `[from,to]`, event đúng biên chung có thể bị tính hai lần khi xử lý các cửa sổ liên tiếp. Nếu dùng cả hai đầu mở, có thể bỏ lỡ event tại biên.

### 4.3. Thời điểm bắt đầu khác sự kiện chồng lấn khoảng

Một **duration event** có `startTime` và `endTime`. Khi truy vấn những event **bắt đầu** trong một khoảng, dùng `getStartTime` như trên. Khi muốn tìm event **có ít nhất một phần duration** xảy ra trong khoảng, predicate khác:

```java
boolean overlaps =
        event.getStartTime().isBefore(to) &&
        event.getEndTime().isAfter(from);
```

Với hai interval nửa mở có **duration dương** `[eventStart,eventEnd)` và `[from,to)`, điều kiện trên đúng khi có phần giao không rỗng. Nhưng với **instant event** (start=end), predicate overlap này **không** giống “timestamp nằm trong cửa sổ”. Nếu muốn xử lý cả hai, ví dụ:

```java
boolean match;
if (event.getStartTime().equals(event.getEndTime())) {
    Instant at = event.getStartTime();
    match = !at.isBefore(from) && at.isBefore(to);
} else {
    match = event.getStartTime().isBefore(to) &&
            event.getEndTime().isAfter(from);
}
```

Đây là **trích đoạn**, không phải chương trình tự chạy; cần biến `RecordedEvent event` và `Instant from/to` đã hợp lệ. Trong bài demo chính, chúng ta **chỉ lọc theo start time**, nên output không phụ thuộc các trường hợp overlap.

**Ví dụ quan trọng:** một I/O event bắt đầu 10:04:59 và kết thúc 10:05:02. Nếu cửa sổ là `[10:05:00,10:06:00)`, lọc theo **start** loại nó; lọc theo **overlap** nhận nó. Hai cách có mục đích khác nhau, không phải một trong hai luôn đúng.

### 4.4. Timestamp không phải thứ tự xử lý tuyệt đối

JFR lưu timestamp độ chính xác cao, nhưng đừng giả định:

- Mọi event được in theo cùng một thứ tự logic với business transactions.
- Duration/stack samples phản ánh mọi operation thật.
- Hai event của hai thread khác nhau có quan hệ *happens-before* chỉ vì timestamp gần nhau.
- Timezone từ UI giống timezone của máy ghi hay máy đọc.
- Không có event trong khoảng đồng nghĩa ứng dụng hoàn toàn không làm việc.

Khi điều tra đa JVM/máy, clock skew và đồng bộ thời gian hạ tầng ảnh hưởng việc so mốc trên nhiều file. `Instant` giúp so cùng trục thời gian; nó không tự sửa clock drift.

## 5. “Ngữ cảnh” là gì khi đọc file JFR?

Từ **ngữ cảnh** có thể chỉ những thứ rất khác nhau. Để lọc đúng cần nêu **nguồn và ngữ nghĩa** của context:

| Nguồn ngữ cảnh | Ví dụ | Có sẵn tự động? | Cách lọc |
| --- | --- | --- | --- |
| **Custom field** | `context="run-demo"` | **Chỉ khi code đã ghi** | `hasField` và `getString("context")` |
| **Mã operation** | `operation="load"` | Chỉ khi event schema có field đó | So đúng mã cố định |
| **Outcome/error class** | `outcome="OK"` hoặc mã lỗi | Theo loại event | Lọc cùng field type/semantics |
| **Thread** | `event.getThread().getJavaName()` | Có thể có, tùy event/settings | Kiểm tra `null` và so thread name an toàn |
| **Stack trace** | Method/class trong call stack | Có thể vắng nếu disabled | `getStackTrace()` + kiểm tra frames |
| **Event category** | `Application / Diagnostics` | Metadata type nếu có | `EventType.getCategoryNames()` |
| **JVM/process metadata** | JVM name, process ID, host | Tùy event/file/environment | Đọc metadata phù hợp, không suy từ field không có |
| **Distributed trace/span** | Correlation token an toàn | **Không có mặc định** chỉ vì dùng JFR | Phải tích hợp theo thư viện/giao thức được duyệt |

**JFR không tự gắn một distributed trace ID cho mọi event trong JVM Java 11.** Nếu cần correlation theo request, ứng dụng phải đưa một mã tương quan được phép vào **custom event**, hoặc dùng công cụ tích hợp trace context có thiết kế và bảo mật riêng.

Không lấy **user email, access token, session cookie, raw URL hoặc request body** làm context. JFR file có thể được dump và chia sẻ cho đội điều tra. Dùng code tổng hợp `run-demo` trong bài học; trong hệ thống thật dùng mã ngắn hạn, không chứa bí mật và có chính sách retention phù hợp.

### 5.1. Context string nên là gì?

Trong ví dụ, `context="run-demo"` là **mã test tổng hợp**, không định danh người dùng hay đối tác. Khi mở rộng:

- `operation`: giá trị từ một danh mục ổn định, ví dụ `load`, `transform`, `save`.
- `outcome`: mã an toàn, ví dụ `OK`, `ERROR`, `TIMEOUT`.
- `context`: correlation code phi bí mật, ngắn hạn, chỉ được thêm nếu cần xác định nhóm event cụ thể.
- `units`: primitive number để cộng/tính trung bình không cần lưu raw payload.

Tránh gắn hàng trăm field String lớn hoặc dùng `toString()` trên object nghiệp vụ: vừa tăng CPU/heap/recording size, vừa dễ lộ PII/credentials.

### 5.2. Thread không đồng nghĩa request

Trong backend dùng thread pool, một thread có thể xử lý **nhiều request liên tiếp**. Một request reactive/async có thể chạy trên **nhiều thread**. Vì thế, `RecordedEvent.getThread()` là một **gợi ý điều tra kỹ thuật**, không phải định danh đáng tin của request.

```java
RecordedThread thread = event.getThread();
String threadName = thread == null
        ? "(no-thread)" : thread.getJavaName();
```

Đây là **trích đoạn**; cần import `jdk.jfr.consumer.RecordedThread` và một `RecordedEvent event`. Đừng lọc chỉ theo tên `pool-1-thread-3` rồi kết luận mọi event là của cùng một yêu cầu.

### 5.3. Stack trace có thể không tồn tại

```java
RecordedStackTrace stack = event.getStackTrace();
if (stack != null) {
    // Chỉ xét frames khi JFR thật sự ghi stack trace.
}
```

Đây là **trích đoạn**, cần `jdk.jfr.consumer.RecordedStackTrace`. Recording có thể tắt `stackTrace` để giảm overhead; event type có thể không ghi stack, hoặc sampling/threshold có quy tắc riêng. **Không có stack** không có nghĩa thao tác “không đi qua method nào”.

Khi thực sự muốn lọc theo method, cần duyệt `RecordedFrame`/`RecordedMethod` và so class/method theo tên; kiểm tra null/availability, không parse `toString()` của cả stack, và không xuất stack ra file công khai.

## 6. Phép lọc ba chiều phải là phép giao

Một truy vấn đầy đủ:

```text
MATCH(event) =
  (event.type == "lesson.Work")
  AND (from <= event.startTime < to)
  AND (event.context == "run-demo")
  AND (event.operation == "load")
  AND (event.outcome == "OK")
```

Sắp xếp điều kiện có lợi:

1. **Type trước:** tránh đọc field sai schema.
2. **Time tiếp:** thường là predicate rẻ, không cần decode nhiều field.
3. **Schema check:** xác nhận field cần dùng tồn tại.
4. **Context/operation/outcome:** đọc đúng kiểu `String`/`int`, không ép kiểu tùy tiện.
5. **Aggregate:** tăng count, cộng số units, tính duration hoặc ghi **chỉ các trường cần thiết**.

```java
if (!"lesson.Work".equals(event.getEventType().getName())) {
    continue;
}
Instant start = event.getStartTime();
if (start.isBefore(from) || !start.isBefore(to)) {
    continue;
}
if (!event.hasField("context") || !event.hasField("units")) {
    throw new IOException("Unexpected Work event schema");
}
if (!wantedContext.equals(event.getString("context"))) {
    continue;
}
count++;
totalUnits += event.getInt("units");
```

Đây là **trích đoạn**, cần thêm lọc `operation/outcome` nếu truy vấn yêu cầu; chương trình mục 8 dùng đầy đủ. Nếu schema bắt buộc bị thiếu, ứng dụng nên **fail với thông báo rõ** thay vì âm thầm đếm 0 và kết luận “không có lỗi”.

### 6.1. Bảng đối chiếu các điều kiện

Giả sử cửa sổ `[t1,t4)` và context `run-demo`, operation `load`, outcome `OK`:

| Event | Type | Thời điểm | Context | Operation | Outcome | Kết luận |
| --- | --- | --- | --- | --- | --- | --- |
| A | `lesson.Work` | `t1` | `run-demo` | `load` | `OK` | **Giữ** |
| B | `lesson.Work` | `t2` | `run-demo` | `load` | `OK` | **Giữ** |
| C | `lesson.Work` | `t3` | `another-run` | `load` | `OK` | **Bỏ — context** |
| D | `lesson.Work` | `t4` | `run-demo` | `load` | `ERROR` | **Bỏ — đúng biên trên và outcome** |
| E | `lesson.Marker` | bất kỳ | — | — | — | **Bỏ — type** |

Điều này minh họa **AND**: chỉ A+B được cộng, không phải hợp của tất cả event thỏa từng điều kiện riêng rẽ.

## 7. Đọc tuần tự để giữ heap ổn định

### 7.1. Cách đọc khuyến nghị

```java
try (RecordingFile input = new RecordingFile(pathToJfr)) {
    while (input.hasMoreEvents()) {
        RecordedEvent event = input.readEvent();
        // Filter và aggregate ngay, không giữ toàn bộ event.
    }
}
```

Đây là **trích đoạn**; cần `Path pathToJfr`, `RecordingFile`, `RecordedEvent` và xử lý `IOException`. `try-with-resources` bảo đảm đóng file kể cả khi filter lỗi.

`RecordingFile.readAllEvents(path)` có thể tiện cho **file nhỏ**, nhưng Javadoc Java 11 nêu rõ phương thức này **không nhằm đọc file lớn**. Trên file nhiều GB, việc giữ toàn bộ `List<RecordedEvent>` có thể tạo áp lực heap hoặc OutOfMemoryError.

### 7.2. Không nhầm “đọc từng event” với random-access index

Vòng lặp `hasMoreEvents()/readEvent()` xử lý từng event; nó **không** biến `RecordingFile` thành một index database tối ưu cho mọi truy vấn. Để biết một event có nằm trong khoảng sau hay không, parser vẫn có thể phải đi qua nhiều event/chunk, vì vậy:

- Hạn chế file nguồn theo thời gian incident nếu có thể.
- Dùng event type filter càng sớm càng tốt ở chương trình.
- Chỉ trích xuất fields cần dùng; không xây lại JSON khổng lồ.
- Không in raw event khi không cần, vì tạo string và I/O rất tốn kém.
- Đặt quota thời gian, kích thước file, số lượng file và số event xử lý.
- Với báo cáo nhiều file, tổng hợp kết quả kiểu count/sum/percentile có giới hạn memory, không giữ toàn bộ event objects.

**Không suy rằng vòng lặp trên là O(1) CPU.** CPU còn phụ thuộc kích thước recording và các event cần decode. Lợi ích chủ yếu là **không giữ mọi event trong bộ nhớ cùng lúc**.

## 8. Chương trình Java 11 đầy đủ: tạo file JFR và lọc theo type, time, context

Ví dụ tự chạy này minh họa **cả ba chiều lọc** trong một JVM, không cần network/server, không dùng dữ liệu thật. Nó tạo:

- 4 event kiểu **`lesson.Work`** có `operation`, `context`, `outcome` và `units` khác nhau.
- 1 event kiểu **`lesson.Marker`** để kiểm tra type filtering.
- Một recording chỉ bật hai custom types trong test.
- Một file `.jfr` tạm, được đọc **hai lượt tuần tự**: lượt đầu lấy mốc thời gian từ chính bản ghi tổng hợp, lượt hai áp dụng đủ predicate.

**Tại sao lấy mốc từ dữ liệu test thay vì hardcode giờ?** Vì `Instant.now()` và lịch chạy JFR khác nhau giữa máy/CI. Lấy start time của event `units=2` làm `from` và event `units=7` làm `to` tạo cửa sổ có biên xác minh được. `Thread.sleep(40)` chỉ **tách khoảng cách timestamp của dữ liệu demo**, không phải cách chờ JFR đồng bộ; chương trình đã `stop()/dump()` trước khi đọc.

Chương trình **đã được biên dịch với `javac --release 11` và chạy xác minh trên OpenJDK hiện đại**. Tạo tệp **`JfrWindowFilterDemo.java`**:

```java
import jdk.jfr.*;
import jdk.jfr.consumer.*;
import java.io.IOException;
import java.nio.file.*;
import java.time.Instant;

public class JfrWindowFilterDemo {

    @Name("lesson.Work")
    @Label("Synthetic Work")
    @Category({"Application", "Diagnostics"})
    static class WorkEvent extends Event {
        @Label("Operation") String operation;
        @Label("Context") String context;
        @Label("Outcome") String outcome;
        @Label("Units") int units;
    }

    @Name("lesson.Marker")
    @Label("Synthetic Marker")
    @Category({"Application", "Diagnostics"})
    static class MarkerEvent extends Event {
        String tag;
    }

    static void emit(String operation, String context,
                     String outcome, int units) {
        WorkEvent event = new WorkEvent();
        event.operation = operation;
        event.context = context;
        event.outcome = outcome;
        event.units = units;
        event.commit();
    }

    static final class Summary {
        int matches;
        int units;
    }

    static Summary scan(Path path, Instant from, Instant to,
                        String wantedContext) throws IOException {
        if (!from.isBefore(to)) {
            throw new IllegalArgumentException("Empty or reversed window");
        }
        Summary result = new Summary();
        try (RecordingFile input = new RecordingFile(path)) {
            while (input.hasMoreEvents()) {
                RecordedEvent event = input.readEvent();
                if (!"lesson.Work".equals(event.getEventType().getName())) {
                    continue;
                }
                Instant start = event.getStartTime();
                if (start.isBefore(from) || !start.isBefore(to)) {
                    continue;
                }
                if (!event.hasField("context") ||
                    !event.hasField("operation") ||
                    !event.hasField("outcome") ||
                    !event.hasField("units")) {
                    throw new IOException("Unexpected Work event schema");
                }
                if (!wantedContext.equals(event.getString("context"))) {
                    continue;
                }
                if (!"load".equals(event.getString("operation")) ||
                    !"OK".equals(event.getString("outcome"))) {
                    continue;
                }
                result.matches++;
                result.units += event.getInt("units");
            }
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        if (!FlightRecorder.isAvailable()) {
            System.out.println("jfr_available=false");
            return;
        }
        Path dump = Files.createTempFile("jfr-window-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                recording.enable(WorkEvent.class)
                         .withoutThreshold().withoutStackTrace();
                recording.enable(MarkerEvent.class)
                         .withoutThreshold().withoutStackTrace();
                recording.start();
                emit("load", "run-demo", "OK", 2);
                Thread.sleep(40);
                emit("load", "run-demo", "OK", 3);
                Thread.sleep(40);
                emit("load", "another-run", "OK", 5);
                Thread.sleep(40);
                emit("load", "run-demo", "ERROR", 7);
                MarkerEvent marker = new MarkerEvent();
                marker.tag = "ignore";
                marker.commit();
                recording.stop();
                recording.dump(dump);
            }

            Instant from = null;
            Instant to = null;
            try (RecordingFile input = new RecordingFile(dump)) {
                while (input.hasMoreEvents()) {
                    RecordedEvent event = input.readEvent();
                    if (!"lesson.Work".equals(event.getEventType().getName())) {
                        continue;
                    }
                    int units = event.getInt("units");
                    if (units == 2) {
                        from = event.getStartTime();
                    } else if (units == 7) {
                        to = event.getStartTime();
                    }
                }
            }
            if (from == null || to == null || !from.isBefore(to)) {
                throw new AssertionError("Cannot derive test window");
            }
            Summary result = scan(dump, from, to, "run-demo");
            System.out.println("window_valid=" + from.isBefore(to));
            System.out.println("matched_events=" + result.matches);
            System.out.println("matched_units=" + result.units);
            System.out.println("verified="
                    + (result.matches == 2 && result.units == 5));
        } finally {
            Files.deleteIfExists(dump);
        }
    }
}
```

### 8.1. Biên dịch và chạy

Trên JDK có module `jdk.jfr`, dùng:

```bash
javac --release 11 -encoding UTF-8 JfrWindowFilterDemo.java
java JfrWindowFilterDemo
```

**Output kiểm chứng khi JFR khả dụng:**

```text
window_valid=true
matched_events=2
matched_units=5
verified=true
```

Code không in timestamp hay đường dẫn tệp vì chúng thay đổi theo lần chạy. Dữ liệu tổng hợp xác định: event đầu có `units=2`, event thứ hai `units=3`, tổng `5`. Event `another-run` có `units=5` nhưng bị loại bởi context. Event `units=7` nằm **chính tại biên trên** `to` nên bị loại; nó còn có `outcome=ERROR` nên cũng không đạt predicate nếu mở rộng window. `MarkerEvent` bị loại ngay theo type name.

### 8.2. Giải thích từng lớp và bước

1. **`WorkEvent`** khai báo schema có 4 field, category `Application/Diagnostics` và name ổn định `lesson.Work`.
2. **`MarkerEvent`** có type `lesson.Marker`. Dù cùng category, nó không lọt qua điều kiện `lesson.Work`.
3. **`emit(...)`** tạo instance và `commit()`. Chúng là event tổng hợp, không liên quan request hay user thật.
4. **Recording** bật hai loại event và `withoutThreshold()` để các event rất ngắn không bị lọc trong test; `withoutStackTrace()` tránh dữ liệu không cần.
5. Các lần `Thread.sleep(40)` chỉ làm timestamp trong file tách nhau, **không phải** đợi `commit()` hoàn tất ở thread khác.
6. **`recording.stop(); recording.dump(dump)`** chốt dữ liệu để phân tích trong một file ổn định.
7. **Lượt đọc đầu** chọn `from` và `to` từ event có `units=2` và `units=7`, vì đây là dataset tổng hợp chúng ta kiểm soát. Không dùng cách chọn bằng `units` làm heuristic trên file production.
8. **`scan`** kiểm tra `from < to`, mở file và đọc tuần tự. Type predicate chạy trước, sau đó start-time `[from,to)`, rồi schema fields, context, operation và outcome.
9. **`hasField`** ngăn việc đọc nhầm field thiếu; nếu schema không đúng, code fail rõ thay vì âm thầm nói có 0 event.
10. **`Summary`** chỉ giữ `matches` và `units`, không gom toàn bộ `RecordedEvent` vào một list.
11. **`finally`** xóa file temp kể cả khi assertion thất bại; file incident thật phải có retention và permissions riêng.
12. `FlightRecorder.isAvailable()` xử lý trường hợp JFR không khả dụng trên runtime có module; một custom runtime image thiếu cả `jdk.jfr` cần được cấu hình thêm module trước khi chạy code.

**Điểm cần nhớ:** bộ lọc chính xác được đặt trong `scan`. Lượt đầu tạo mốc chỉ nhằm test kết quả xác định không phụ thuộc ngày/giờ của máy. Trong production, truyền `from`/`to` từ user hoặc alert (được parse/validate) và gọi `scan` trực tiếp.

### 8.3. Tại sao không truyền `Instant.now()` tùy tiện?

Nếu đo `Instant from = Instant.now()` ngay trước hoặc sau `event.commit()`, bạn có thể vô tình tạo boundary không chứa event do khác thời điểm đo, chuyển đổi JFR timestamps hoặc scheduling. Lấy mốc từ event thật ở test ổn định hơn cho minh họa. Trong hệ thống production, mốc incident đến từ monitoring và phải có timezone/clock policy rõ.

### 8.4. Chi phí của hai lượt đọc

Hai lượt đọc ở demo giúp **tự tạo window**, không phải yêu cầu của JFR. Nếu biết sẵn `from/to` và context, production chỉ cần **một lượt**. Đọc hai lượt trên file hàng GB làm tăng I/O; không nên làm nếu không có lý do.

## 9. Bộ lọc có thể tái dùng trên file thật

Nếu làm công cụ phân tích incident thực tế, nên nhận đầu vào rõ:

```text
file      = /secure-jfr/incident.jfr
eventType = lesson.Work
from      = 2026-11-07T03:00:00Z
to        = 2026-11-07T03:05:00Z
context   = run-demo
operation = load
outcome   = OK
```

Đây là **ví dụ cấu hình**, không phải một file hoặc incident có thật. Chuyển mốc bằng:

```java
Instant from = Instant.parse(fromArg);
Instant to = Instant.parse(toArg);
if (!from.isBefore(to)) {
    throw new IllegalArgumentException("from must precede to");
}
```

Đây là **trích đoạn**, hai biến `String fromArg/toArg` đến từ input đã validate; không phải chương trình hoàn chỉnh. Nếu cần chấp nhận offset `+07:00`, có thể dùng:

```java
Instant from = java.time.OffsetDateTime
        .parse("2026-11-07T10:00:00+07:00")
        .toInstant();
```

Giá trị này **bằng** `2026-11-07T03:00:00Z`. Không sửa timestamp bằng cách trừ 7 giờ thủ công ở nhiều nơi; để API thời gian xử lý timezone/offset, nhất là hệ thống chạy ở nhiều vùng địa lý.

Nên giới hạn:

- Độ dài cửa sổ tối đa theo nghiệp vụ.
- File size và lượng file input.
- Event types được phép query, nếu chạy từ giao diện người dùng.
- Số dòng/tổng dữ liệu trả về; ưu tiên aggregation và pagination có giới hạn.
- Thời gian xử lý/I/O và CPU.
- Quyền truy cập file và tính nhạy cảm của fields.
- Lỗi parse/unsupported schema, không hiển thị exception chứa raw event payload.

## 10. Bộ lọc theo thời gian xảy ra khác bộ lọc lúc capture

Hai giai đoạn cần phân biệt:

| Giai đoạn | Việc đang làm | Ảnh hưởng |
| --- | --- | --- |
| **Capture** | Enable `jdk.SocketRead` hoặc custom `lesson.Work`, chọn threshold/period/stack trace | Quyết định event nào **được ghi** vào repository/file |
| **Consumer** | Đọc file và lọc type/time/context | Chỉ chọn trong số event **đã có trong file** |

Một consumer không thể “khôi phục” event chưa bao giờ được ghi vì:

- Event bị disabled.
- Duration không vượt threshold.
- Sampling bỏ qua lần hoạt động đó.
- Rolling retention đã loại chunk cũ.
- Recording thiếu khoảng thời gian cần tìm.
- JVM/process kết thúc trước khi dump hoặc dump thất bại.

Ví dụ, nếu recording chỉ bật `jdk.CPULoad` nhưng không bật custom `lesson.Work`, sau đó lọc `lesson.Work` sẽ có **0 event**. Đó **không** chứng minh không có công việc `load`. Vì vậy, báo cáo nên ghi **cấu hình recording, file coverage và lý do có thể không quan sát được**.

### 10.1. Kiểm tra schema trước khi lập báo cáo

Java 11 cho phép đọc type metadata đã lưu:

```java
try (RecordingFile input = new RecordingFile(pathToJfr)) {
    boolean known = input.readEventTypes().stream()
            .anyMatch(t -> "lesson.Work".equals(t.getName()));
    if (!known) {
        System.out.println("Event type not present in file metadata");
    }
}
```

Đây là **trích đoạn**, cần `Path pathToJfr`, `RecordingFile` và import phù hợp. Metadata hiện diện **không bảo đảm file chứa một instance** trong cửa sổ bạn chọn; metadata vắng thì cần xem file/version/recording settings. Không kết luận nghiệp vụ không xảy ra chỉ từ bộ lọc trả rỗng.

## 11. Dùng `jfr` CLI để lọc nhanh theo loại hoặc category

JDK có công cụ `jfr` cho việc xem file JFR. Với file đã được tạo và bạn có quyền đọc:

```bash
jfr summary /secure-jfr/incident.jfr
jfr metadata /secure-jfr/incident.jfr
jfr print --events jdk.GarbageCollection /secure-jfr/incident.jfr
jfr print --events lesson.Work /secure-jfr/incident.jfr
jfr print --categories Application /secure-jfr/incident.jfr
```

**`/secure-jfr/incident.jfr` chỉ là đường dẫn minh họa**. Trên Windows, dùng đường dẫn phù hợp; đọc từ file của nguồn tin cậy. `jfr summary` giúp xem tổng quan event counts/types; `jfr metadata` giúp kiểm tra type schema; `jfr print` hiển thị nội dung đã chọn.

**Một lưu ý về tổ hợp filter rất dễ sai:**

```bash
jfr print --events jdk.CPULoad --categories GC /secure-jfr/incident.jfr
```

Theo hướng dẫn `jfr`, khi cung cấp cả `--events` và `--categories`, kết quả gồm các event phù hợp **một trong hai** filter (phép **OR/union**), **không** phải “chỉ CPULoad thuộc GC” (phép AND). Do đó **không thể dựa vào tổ hợp CLI này để khẳng định lọc ba chiều type AND time AND context**.

Các phiên bản `jfr` có thể hỗ trợ `--json` hoặc `--xml` khi in:

```bash
jfr print --json --events lesson.Work /secure-jfr/incident.jfr
```

Nếu xử lý máy, JSON từ CLI có thể dùng trong một pipeline riêng, nhưng phải kiểm tra version công cụ, schema và kích thước output. Với Java 11, lựa chọn rõ ràng, kiểm soát memory tốt cho điều kiện **thời gian + context + nhiều field** vẫn là **`RecordingFile` với predicate Java**. Đừng tự khẳng định `jfr print` Java 11 có tham số thời gian `--from/--to` mà chưa kiểm tra `jfr help print` ở JDK đang dùng.

### 11.1. CLI không phải backend truy vấn tùy ý

`jfr print --events ...` lọc theo **symbolic event name**, `--categories` lọc nhóm, chứ không hiểu chuỗi điều kiện như SQL. Để giới hạn theo field như `context="run-demo"` và start time nửa mở, nên dùng Java consumer hoặc công cụ phân tích JFR phù hợp.

Ngoài ra, output của `jfr print` có thể chứa **stack traces, hostnames, file paths, network addresses và custom field values**. Đừng đăng thẳng nguyên dump lên ticket/chat không được phân quyền.

## 12. Context và correlated events giữa các thread/process

### 12.1. Một request không nằm mãi trên một thread

Với executors, CompletableFuture hoặc các framework reactive, một request có thể đi qua nhiều thread. Cùng tên `pool-worker-1` lại có thể xử lý nhiều request liên tiếp. Vì vậy, filter `getThread().getJavaName()` chỉ trả lời **“event ghi trên thread này”**, không chứng minh **“cùng một request”**.

Ví dụ:

```text
HTTP request R
  ├─ thread-A: parse
  ├─ thread-B: downstream call
  └─ thread-C: write result

Nếu cả ba event có context="run-demo":
  filter context có thể nối đúng nhóm các custom events.

Nếu chỉ filter thread-A:
  dễ bỏ lỡ B/C.
```

**Không có tự động propagation** của application context chỉ vì dùng JFR. Bạn phải thiết kế event fields và propagation của mã correlation theo các boundary async/thread một cách an toàn. Với thư viện tracing, có thể tương tác với trace context, nhưng phải xem quy tắc API/version và bảo vệ privacy.

### 12.2. Correlation ID không phải credential

Mã `context` lý tưởng:

- Không tiết lộ user identity trực tiếp.
- Không phải session token hoặc bearer token có thể dùng để đăng nhập.
- Chỉ giữ trong thời hạn incident/recording cần thiết.
- Có namespace/phạm vi rõ để tránh va chạm ngoài dự kiến.
- Không thay đổi tùy từng event trong cùng một đơn vị cần liên kết.
- Có tài liệu mô tả ý nghĩa: request ID, batch ID hay operation group.

Ngay cả một ID “ngẫu nhiên” có thể liên kết hành vi sử dụng hệ thống nếu lưu dài và ghép với nguồn khác. Hãy thiết kế dựa trên threat model/privacy policy, không mặc định mọi correlation ID đều vô hại.

### 12.3. Type + thread + stack không thay thế context thật

Một event `jdk.SocketRead` và một event custom `lesson.Work` xảy ra gần nhau trên cùng thread có thể là dấu hiệu liên quan, nhưng **chưa đủ để chứng minh causal link**. Giữa chúng có thể là queue/async boundary hoặc operation khác. Khi cần xác định nhân quả nghiệp vụ, dựa vào explicit context/spans/traces đã xác thực, kết hợp timeline JFR như một nguồn chẩn đoán.

## 13. Schema compatibility giữa JDK và version ứng dụng

Không nên đọc tùy tiện field với giả định mọi runtime JDK có schema giống nhau:

- Tên event built-in có thể thay đổi/tồn tại khác tùy bản JDK và loại collector.
- Fields có thể thêm, đổi kiểu hoặc vắng theo JDK/provider/runtime.
- Custom event `@Name` và field `@Name` có thể thay đổi trong ứng dụng.
- `getString("field")` yêu cầu kiểu String; `getInt("field")` yêu cầu primitive tương thích.
- `EventType.getLabel()` không phải machine key. Dùng `getName()` và danh sách field descriptors.
- Category là đường dẫn trình bày; không suy `@Category` là field ở mỗi event instance.
- Event ID (metadata numeric) có thể thay đổi giữa JVM/session; không dùng làm persistent identifier mặc định.

**Cách fail rõ:** với một schema bắt buộc, sau khi xác nhận type hãy kiểm tra `hasField` trước, rồi đọc đúng getter; nếu thiếu/khác kiểu thì trả một lỗi schema actionable. Không âm thầm bỏ event sai để báo “0 event OK” khiến điều tra bị lệch.

**Cách hỗ trợ nhiều version:** định nghĩa adapter per schema version, hoặc dùng type name/version riêng khi thay đổi breaking. Test với fixtures `.jfr` thực từ những version được hỗ trợ, thay vì test toàn bộ bằng dữ liệu chỉ sinh trên một JDK mới.

## 14. Thời gian sự cố, timezone và giới hạn bản ghi

Một incident thường có thời gian xuất phát từ dashboard ở múi giờ người vận hành, trong khi JFR lưu timestamp dạng `Instant`. Trước khi lọc:

1. Ghi rõ timezone của alert.
2. Chuyển sang UTC/`Instant`.
3. Nới khoảng trước/sau một cách có lý do để tìm nguyên nhân dẫn đến spike (ví dụ 2 phút trước, 1 phút sau).
4. Chọn **start-in-window** hay **duration-overlap**, và ghi vào báo cáo.
5. Kiểm tra file JFR có **coverage** phần thời gian đó.
6. Nếu nhiều JVM, kiểm tra clock sync/skew.
7. Không trộn timestamp event với thời gian file được dump/export.

**Ví dụ sai:** file dump được tạo lúc 10:10 thì suy ra mọi event đều xảy ra lúc 10:10. Thời điểm dump chỉ là lúc xuất file, không phải timestamp mỗi event. Một JFR recording kéo dài 30 phút có thể chứa nhiều thời điểm trước dump.

**Ví dụ thời gian biên:** event bắt đầu đúng `2026-11-07T03:05:00Z` bị loại khỏi window kết thúc ở mốc ấy, theo định nghĩa `[from,to)`, dù UI có thể làm tròn thành `10:05:00` giờ địa phương. So sánh bằng `Instant` tránh sai lệch do format hiển thị.

## 15. Hiệu năng và độ tin cậy của consumer

| Rủi ro | Sai lầm phổ biến | Hướng đúng |
| --- | --- | --- |
| OOME | `readAllEvents` trên file nhiều GB | `RecordingFile` tuần tự |
| CPU cao | Format/parse toàn bộ `toString()` dù không match | Lọc type/time trước, chỉ đọc field cần |
| Output quá lớn | In hàng triệu event | Tổng hợp count/sum, giới hạn rows/bytes |
| Schema sai | Gọi `getInt("units")` cho GC event | Kiểm tra type và `hasField` |
| Mốc thời gian sai | So `String` timestamp theo định dạng địa phương | `Instant`, UTC và boundary policy |
| Filter sai logic | Dùng OR giữa type/time/context | Điều kiện AND theo truy vấn |
| Thống kê sai | Sampling event được coi là toàn bộ hành vi | Ghi rõ threshold/period/sampling |
| File không đáng tin | Parse recording upload từ người lạ trong JVM có quyền cao | Chỉ nguồn được kiểm duyệt, sandbox/quota |
| IO lỗi giữa chừng | Coi thống kê partial là kết quả đầy đủ | Fail/report partial status rõ |
| Data leak | Dump raw URL/secret/stack vào báo cáo | Allowlist, redaction, access control |
| Multi-file duplicate | Cộng trùng các file snapshot có khoảng chồng | Kiểm tra coverage/overlap/dedup policy |
| Khác clock | Ghép nhiều JVM bằng timestamp giả định đồng bộ | NTP/clock skew margin, correlation |
| Concurrency | Dùng chung một `RecordingFile` qua nhiều thread tùy ý | Dùng consumer tuần tự hoặc chia file an toàn |

Một hàm lọc chỉ an toàn về mặt vận hành khi có giới hạn **size, thời gian, CPU, memory, quyền đọc và dữ liệu xuất**. Nếu cần phân tích hàng trăm recording, cân nhắc pipeline riêng có lưu chỉ số đã tổng hợp, thay vì liên tục nạp file và xây một list event khổng lồ.

### 15.1. Event nào được ghi còn tùy capture settings

JFR không phải audit log chính xác cho mọi operation. Các event duration có thể chỉ xuất hiện nếu vượt `threshold`; execution samples không phải số lần method thực thi; event có thể bị tắt hoặc rolling retention đã loại dữ liệu cũ. Không có match cần được diễn giải là **“không quan sát thấy event phù hợp trong file với các điều kiện này”**, không phải “ứng dụng không xảy ra hoạt động đó”.

### 15.2. Đọc file từ nguồn tin cậy

Javadoc Java SE 11 của `RecordingFile` nói chỉ nên dùng với recording files từ **nguồn tin cậy**. Nếu ứng dụng cho người lạ upload file `.jfr`, hãy thiết kế sandbox, file size limit, timeout, quota, parser isolation, giảm quyền và chống path traversal. Đừng chạy parser trong JVM chứa khóa và quyền cao rồi trả toàn bộ stack/field qua HTTP công khai.

## 16. Dùng kết quả lọc để tìm nguyên nhân, không chỉ đếm event

Đếm `2` event ở ví dụ là bài thực hành; khi điều tra thật cần chuyển match thành một giả thuyết có bằng chứng.

Một workflow ví dụ:

1. Metrics báo spike p99 latency.
2. Chọn timestamp alert đã chuẩn hóa UTC và window trước/sau.
3. Kiểm tra file JFR có đúng khoảng thời gian và event types cần phân tích.
4. Lọc `jdk.JavaMonitorEnter`, `jdk.ThreadPark`, `jdk.SocketRead` trong window để tìm wait/I/O.
5. Lọc custom event theo `operationCode` và `outcome` nếu ứng dụng có instrument.
6. So duration distribution, byte count hoặc mẫu stack ở cùng thời điểm.
7. Liên kết bằng correlation context đã được ghi an toàn nếu có, không tự nhận một thread = một request.
8. Tách hiện tượng đồng thời khỏi quan hệ nhân quả, đối chiếu logs/traces.
9. Thử tái hiện trong staging bằng load và settings tương đương.
10. Ghi kết luận kèm **độ bao phủ recording, filters, threshold, sampling** và hạn chế.

**Ví dụ:** thấy nhiều `jdk.SocketRead` dài trong window không chứng minh dịch vụ mạng là nguồn duy nhất gây chậm. Có thể service đã chờ lock hoặc GC trước I/O. Nên xem timeline chung và mức độ liên hệ với request/operation được báo chậm.

## 17. Kiểm thử: những trường hợp bắt buộc

| Tình huống | Test input | Kỳ vọng |
| --- | --- | --- |
| Lọc đúng event type | `lesson.Work` và `lesson.Marker` cùng file | Chỉ `lesson.Work` được xét tiếp |
| Biên dưới `from` | Event bắt đầu đúng `from` | Được tính |
| Biên trên `to` | Event bắt đầu đúng `to` | Bị loại |
| Khoảng ngược | `from >= to` | Báo lỗi, không âm thầm dùng window khác |
| Context khác | `another-run` | Bị loại |
| Operation khác | `transform` thay vì `load` | Bị loại |
| Outcome khác | `ERROR` thay `OK` | Bị loại |
| Schema thiếu | Không có field `context` | Lỗi schema rõ, hoặc chính sách explicit skip |
| Event type khác schema | Built-in GC cùng file | Không gọi getter của custom type |
| Instant event | `start==end` | Lọc start theo `[from,to)` |
| Duration crossing window | `start<from<end` | Khác giữa start-based và overlap-based |
| Không có event phù hợp | Filter hợp lệ nhưng không match | Count 0, ghi rõ không quan sát thấy |
| Sampling/threshold | Event bị disable/lọc từ capture | Consumer không tự khôi phục được |
| File lớn | Nhiều event nhiều GB | Duyệt tuần tự với quota; không OOME |
| File lỗi/không tin cậy | Không phải JFR, truncated hoặc corrupt | IOException/fail closed |
| Clock khác nguồn | File JVM A/B khác timezone/skew | Chuẩn hóa Instant, ghi giới hạn |
| Privacy | Context có secret giả | Test phát hiện và cấm xuất secret |
| Multi-file overlap | Hai dump có thời gian chồng nhau | Không cộng trùng mà không có chính sách |

**Một test quan trọng của bài:** event `units=2` nằm đúng `from`, event `units=7` nằm đúng `to`; vậy kể cả khi context/outcome thay đổi, **quy tắc biên** vẫn xác định. Các event ở giữa chỉ được giữ khi đủ cả type và context/operation/outcome.

## 18. Những hiểu nhầm thường gặp

| Hiểu nhầm | Điều đúng cần nhớ |
| --- | --- |
| “In toàn bộ `.jfr` rồi grep là đủ” | Nên dùng typed fields, Instant và predicate có cấu trúc |
| “Label là event name” | `EventType.getName()` mới là định danh filter ổn định |
| “Category là field của từng event instance” | Category là **metadata event type** để nhóm hiển thị |
| “Kết hợp `--categories` và `--events` trong CLI là AND” | Tài liệu `jfr print` nói **union/OR**, không phải phép giao |
| “`jfr print` Java 11 chắc chắn có `--from/--to`” | Không tự suy đoán; dùng API Java `RecordingFile` để lọc thời gian |
| “Dùng `LocalDateTime` thiếu timezone vẫn ổn” | Dễ lệch múi giờ; dùng `Instant`/offset rõ |
| “Khoảng `[from,to]` và `[from,to)` giống nhau” | Khác ở biên trên, có thể bị double count |
| “Bắt đầu trong window = overlap window” | Duration event có thể bắt đầu trước nhưng còn kéo dài vào window |
| “`getThread()` luôn không null” | Có event không ghi thread |
| “Thread name là request ID” | Thread pool tái dùng thread, async đổi thread |
| “Stack trace luôn có” | Phụ thuộc event/settings, có thể null |
| “JFR tự thu trace ID cho tất cả event” | Cần instrument/correlation theo protocol ứng dụng |
| “Không thấy event là không có hoạt động” | Threshold/period/sampling/retention có thể loại event |
| “`hasField` là đủ không cần kiểm type” | Hai event types có thể có field trùng tên nhưng khác nghĩa |
| “`readAllEvents` an toàn với mọi file” | Javadoc không khuyến nghị cho file lớn |
| “Snapshot liên tiếp không chồng nội dung” | Dump có thể chứa cùng chunk/event đã giữ |
| “JFR file là file công khai được” | Có thể chứa hostname, paths, stack, PII và secrets |
| “`RecordingStream` đã có trong Java 11” | API Event Streaming xuất hiện từ JDK 14 |
| “Cứ đúng timestamp là cùng transaction” | Cần correlation/causal evidence thực, không chỉ cùng thời điểm |

## 19. Bài luyện tập có đáp án

**Bài 1.** File chứa `jdk.GarbageCollection` và `lesson.Work`. Vì sao cần lọc type trước khi `getString("context")`?

**Đáp án:** Không phải event type nào cũng có field `context`. Nếu gọi getter không kiểm tra schema, code có thể ném `IllegalArgumentException` hoặc diễn giải sai. So `getEventType().getName()` trước rồi `hasField`.

**Bài 2.** Với window `[10:00:00,10:05:00)`, event bắt đầu đúng 10:05:00 có được tính?

**Đáp án:** **Không.** Khoảng nửa mở loại biên trên. Event đó thuộc cửa sổ tiếp theo `[10:05:00,10:10:00)` nếu dữ liệu vẫn được ghi.

**Bài 3.** Event bắt đầu 10:04:59, kết thúc 10:05:02; truy vấn `[10:05,10:06)` thì sao?

**Đáp án:** Lọc **start-in-window** loại event; lọc **duration-overlap** giữ event. Cần chọn đúng semantics theo mục tiêu điều tra và xử lý instant events riêng.

**Bài 4.** `jfr print --events jdk.CPULoad --categories GC file.jfr` trả event nào?

**Đáp án:** Sự kiện phù hợp **CPULoad hoặc category GC**. Theo tài liệu, các filter CLI này kết hợp **OR**, không phải chỉ CPULoad thuộc GC.

**Bài 5.** Trong ví dụ Java, tại sao `matched_events=2` và `matched_units=5`?

**Đáp án:** Chỉ hai `lesson.Work` có start time trong `[from,to)`, `context=run-demo`, `operation=load`, `outcome=OK` được tính, với `units=2` và `3`. Các event còn lại bị loại bởi type/context/biên trên/outcome.

**Bài 6.** Vì sao không dùng `RecordingFile.readAllEvents` cho file 8 GiB?

**Đáp án:** Nó dựng danh sách toàn bộ event trong heap, không dành cho file lớn. Duyệt tuần tự bằng `RecordingFile.hasMoreEvents/readEvent` và aggregate ngay; vẫn đặt quota CPU/I/O.

**Bài 7.** Có thể lọc mọi request chỉ dựa trên `getThread().getJavaName()`?

**Đáp án:** Không. Thread pool tái dùng thread và request async có thể qua nhiều thread. Cần field correlation hợp lệ được instrument, hoặc tracing phù hợp.

**Bài 8.** Vì sao JFR trống trong window không chứng minh JVM không bị GC?

**Đáp án:** Cần xem file coverage, event enabled, recording settings, threshold/sampling và rolling retention. “Không quan sát thấy” khác “không xảy ra”.

**Bài 9.** Vì sao dùng `Instant` thay vì so chuỗi giờ `"10:00"`?

**Đáp án:** Chuỗi thiếu múi giờ/ngày, có thể có định dạng khác nhau; `Instant` so những thời điểm tuyệt đối. Chuyển input với offset/timezone rõ trước khi lọc.

**Bài 10.** Nếu muốn tìm event bị block kéo dài xuyên đầu window, dùng start-time hay overlap?

**Đáp án:** Dùng **overlap** với `getStartTime()/getEndTime()` cho duration events, đồng thời xử lý instant events và ranh giới nửa mở đúng.

**Bài 11.** Tại sao không in raw `RecordedEvent.toString()` lên ticket production?

**Đáp án:** Có thể rò hostnames, stack traces, đường dẫn, custom field chứa bí mật và tạo output lớn. Chỉ xuất các trường đã allowlist và tổng hợp sau khi phân quyền.

**Bài 12.** Java 11 báo không có `RecordingStream`. Cách làm tương đương trong bài này?

**Đáp án:** Dùng `Recording`/`jcmd` để ghi và `RecordingFile` để đọc snapshot `.jfr`. Nếu thực sự cần Event Streaming gần realtime, đó là API được bổ sung từ JDK 14, phải nâng runtime hoặc dùng giải pháp phù hợp riêng.

## 20. Checklist trước khi chốt kết quả điều tra

- [ ] Đã chọn **event type names** thực sự có trong file, không dùng labels làm machine keys?
- [ ] Đã xác định file `.jfr` đúng JVM, version và khoảng dữ liệu bao phủ?
- [ ] `from/to` có timezone/offset rõ, được chuẩn hóa thành `Instant`?
- [ ] Đã định nghĩa start-in-window hay duration-overlap? Ranh giới `[from,to)` nhất quán?
- [ ] Type filter chạy trước field getters để không đọc sai schema?
- [ ] Có kiểm tra `hasField`, kiểu field và khác biệt JDK/schema?
- [ ] Context/operation/outcome đã được ghi từ application, không tự suy từ thread?
- [ ] Thread/stack có kiểm tra null và không bị dùng như request ID?
- [ ] Logic của các điều kiện là **AND** như mục tiêu, không nhầm CLI union/OR?
- [ ] Đọc file tuần tự, giới hạn kích thước/CPU/I/O/output, không giữ tất cả events?
- [ ] Có tôn trọng threshold/period/sampling và retention khi diễn giải trường hợp không match?
- [ ] Correlation field không chứa credential, user PII hay dữ liệu không được phép?
- [ ] File chỉ đến từ nguồn tin cậy, xử lý lỗi parse và bảo vệ snapshot đúng chính sách?
- [ ] Đã test event ở biên `from` và `to`, khác type/context, missing field và file hỏng?
- [ ] Báo cáo ghi rõ cửa sổ, loại event, predicate, số match và giới hạn về độ bao phủ?

## 21. Ghi nhớ và tài liệu chính thức

**Công thức đơn giản của bài:** lọc **đúng type** (`getEventType().getName()`), **đúng time** (`getStartTime()` và `Instant` với `[from,to)`), **đúng context** (các fields được instrument/validate), rồi tổng hợp theo đúng metric. Khi điều tra event duration giao với window, cân nhắc `getEndTime()` và xử lý instant events riêng.

**Đừng nhầm JFR với audit log hoặc hệ thống tracing tự động**: chỉ phân tích những gì recording đã giữ; event type có threshold/sampling; request context chỉ tồn tại nếu instrument đúng. Dùng `RecordingFile` tuần tự để giảm áp lực heap; không log thô secrets.

Nguồn có thẩm quyền, còn phù hợp với JDK hiện đại:

- [Oracle Java SE 11 — `RecordingFile`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): mở, đọc từng event, `hasMoreEvents`, `readEventTypes` và cảnh báo về file lớn/nguồn tin cậy.
- [Oracle Java SE 11 — `RecordedEvent`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): `getStartTime`/`getEndTime`/`getDuration`, event type, thread, stack.
- [Oracle Java SE 11 — `RecordedObject`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): `hasField`, `getString`, `getInt` và typed getters.
- [Oracle Java SE 11 — `RecordedThread`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedThread.html): thread metadata có thể dùng làm ngữ cảnh kỹ thuật.
- [Oracle Java SE 11 — `EventType`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventType.html): tên event, label, category và field schema.
- [Oracle Java SE 11 — `Recording`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): ghi event và dump ra file.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): tích hợp JFR vào Java 11.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): API streaming từ JDK 14, phân biệt với consumer Java 11.
- [Oracle Java SE 11 — Diagnostic Tools/JFR](https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html): JFR trong chẩn đoán, presets và công cụ.
- [Oracle Java SE 17 — `jfr` CLI](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `jfr print` theo type/category và cơ chế hợp các filters, hỗ trợ phân tích tương ứng.
- [Oracle Java SE 25 — `RecordedEvent`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): đối chiếu khả năng tiêu thụ event còn hiện diện trong JDK hiện đại.
