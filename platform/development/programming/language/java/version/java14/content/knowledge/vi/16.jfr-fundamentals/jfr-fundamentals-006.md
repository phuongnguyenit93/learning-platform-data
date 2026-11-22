# Chu kỳ, ngưỡng và stack trace trong `EventSettings` của Java Flight Recorder (JFR)

## 1. Mục tiêu và bản chất của `EventSettings`

Java Flight Recorder (**JFR**) thu thập các sự kiện có cấu trúc của JVM và ứng dụng để phân tích hiệu năng, độ trễ, tải CPU, I/O, cấp phát bộ nhớ và hành vi thực thi. Trong Java, lớp **`jdk.jfr.EventSettings`** giúp cấu hình **một loại sự kiện** cho một bản ghi (*recording*), ví dụ:

```java
import java.time.Duration;
import jdk.jfr.Recording;

try (Recording recording = new Recording()) {
    recording.enable("jdk.CPULoad")
            .withPeriod(Duration.ofSeconds(1));

    recording.enable("jdk.FileRead")
            .withThreshold(Duration.ofMillis(10))
            .withStackTrace();

    recording.start();
    // Thực thi workload cần quan sát...
    recording.stop();
}
```

**Đây là ví dụ cấu hình ngắn**, không bảo đảm cả hai loại sự kiện luôn xuất hiện: JFR phải thực sự có hoạt động tương ứng trong lúc recording chạy. Một chương trình tự tạo sự kiện, chạy và đọc lại file `.jfr` hoàn chỉnh nằm ở mục 9.

Ba loại cấu hình trọng tâm có ý nghĩa **khác nhau**:

| Cấu hình | API của `EventSettings` | Tác dụng chính | Áp dụng điển hình |
| --- | --- | --- | --- |
| **Chu kỳ** (*period*) | `withPeriod(Duration)` | Đặt khoảng thời gian yêu cầu cho **sự kiện định kỳ** | `jdk.CPULoad`, custom periodic event đã đăng ký hook |
| **Ngưỡng** (*threshold*) | `withThreshold(Duration)`, `withoutThreshold()` | Chỉ ghi các sự kiện có **thời lượng đạt ngưỡng** | I/O chậm, chờ khóa, custom duration event |
| **Stack trace** | `withStackTrace()`, `withoutStackTrace()` | Bật/tắt lưu ngăn xếp lời gọi đi kèm sự kiện | Điều tra vị trí gọi `commit()` hoặc hành vi chậm |

Các thiết lập này giúp cân bằng **mức chi tiết dữ liệu** và **chi phí quan sát**; chúng **không** thay thế nhau. Một `threshold` 20 ms không biến sự kiện thành bộ lấy mẫu mỗi 20 ms; một `period` 200 ms không có nghĩa “chỉ ghi sự kiện kéo dài trên 200 ms”.

**Tình trạng hiện nay:** `jdk.jfr` và `EventSettings` có từ Java 9 và tiếp tục được duy trì trong các bản JDK hiện đại. Ví dụ trong bài được biên dịch và chạy bằng **JDK 17**, không sử dụng API preview hay cơ chế JFR lỗi thời. Khi học trong module Java 14, cần phân biệt thời điểm giới thiệu tính năng liên quan với API ổn định vẫn dùng hiện nay.

## 2. Cách lấy và cấu hình `EventSettings`

Có hai overload thường dùng trên `Recording`:

```java
// Dùng tên sự kiện:
EventSettings a = recording.enable("jdk.CPULoad");

// Dùng Class của custom JFR event:
EventSettings b = recording.enable(MyEvent.class);
```

Hai dòng trên là **trích đoạn minh họa**, yêu cầu đã có biến `recording` kiểu `Recording` và class `MyEvent extends jdk.jfr.Event`. `enable(...)` vừa bật loại sự kiện tương ứng cho recording vừa trả về đối tượng cấu hình cho **loại sự kiện đó**.

`EventSettings` cho phép **method chaining**:

```java
recording.enable("jdk.FileRead")
        .withThreshold(Duration.ofMillis(10))
        .withStackTrace();
```

Mỗi method cấu hình trả về `EventSettings` để tiếp tục gọi. Không cần tự khởi tạo `new EventSettings()` vì đây là lớp abstract; lấy nó từ API như `Recording.enable(...)`.

**Khuyến nghị:** cấu hình các event **trước** `recording.start()` để có trạng thái khởi đầu nhất quán và tránh thay đổi cấu hình giữa workload. Một số settings có thể thay đổi khi recording đang chạy, nhưng dữ liệu thu được trước/sau thời điểm đổi có thể không đồng nhất.

### 2.1. Các phương thức liên quan

| Phương thức | Ý nghĩa |
| --- | --- |
| `withPeriod(Duration.ofSeconds(1))` | Đặt khoảng thời gian của loại periodic event |
| `withThreshold(Duration.ofMillis(20))` | Yêu cầu duration ít nhất 20 ms để event đủ điều kiện được ghi |
| `withoutThreshold()` | Không dùng ngưỡng lọc duration; tương đương `with("threshold", "0 s")` |
| `withStackTrace()` | Bật stack trace; tương đương `with("stackTrace", "true")` |
| `withoutStackTrace()` | Tắt stack trace; tương đương `with("stackTrace", "false")` |
| `with(String name, String value)` | Thiết lập một setting theo tên/giá trị dạng chuỗi, ví dụ `with("period", "1 s")` |

Với một loại event, những setting **được hỗ trợ** còn phụ thuộc vào metadata/kiểu event. Không nên tùy tiện đưa `period` vào event không có cơ chế định kỳ rồi kỳ vọng JVM tự phát event theo lịch. Tương tự, cấu hình `stackTrace` không tạo stack trace cho event bị tắt hay chưa từng được ghi.

## 3. `withPeriod(Duration)` — khoảng thời gian của *periodic event*

Một **periodic event** là loại sự kiện được JFR yêu cầu phát theo chu kỳ, thay vì chỉ xuất hiện khi code thực hiện một thao tác nghiệp vụ. Ví dụ built-in:

```java
recording.enable("jdk.CPULoad")
        .withPeriod(Duration.ofSeconds(1));
```

Mục đích là thu thập mức tải CPU khoảng mỗi giây. Giá trị `Duration` ở đây là **khoảng thời gian cấu hình**, không phải thời lượng chạy của một event. `withPeriod` chỉ có ý nghĩa với loại sự kiện **định kỳ được JFR hỗ trợ**.

### 3.1. Cấu hình một periodic event do ứng dụng tự tạo

Với custom JFR event, thường cần:

1. Một lớp `extends Event` có tên sự kiện rõ ràng (`@Name`).
2. Khai báo mặc định `@Period("1 s")` nếu cần.
3. Đăng ký một hook bằng `FlightRecorder.addPeriodicEvent(EventClass.class, Runnable)`. Hook này sẽ tạo và `commit()` event.
4. Trong `Recording`, gọi `enable(...).withPeriod(...)` để thay đổi khoảng thời gian so với mặc định.

Ví dụ rút gọn (được tích hợp đầy đủ trong mục 9):

```java
@Name("demo.Tick")
@Period("1 s")
static class Tick extends Event {
    int sequence;
}

AtomicInteger counter = new AtomicInteger();

Runnable hook = () -> {
    Tick event = new Tick();
    event.sequence = counter.incrementAndGet();
    event.commit();
};

FlightRecorder.addPeriodicEvent(Tick.class, hook);

try (Recording recording = new Recording()) {
    recording.enable("demo.Tick")
            .withPeriod(Duration.ofMillis(200));
    recording.start();
    Thread.sleep(1100);
    recording.stop();
} finally {
    FlightRecorder.removePeriodicEvent(hook);
}
```

Đoạn rút gọn **cần nằm trong class và import đúng**, và chủ yếu minh họa cấu hình; mục 9 có mã độc lập chạy được.

**Ý nghĩa:**
- `@Period("1 s")` khai báo **giá trị mặc định** cho periodic setting của kiểu `Tick`.
- `withPeriod(Duration.ofMillis(200))` là **thiết lập của recording**, đặt mục tiêu chu kỳ 200 ms.
- Hook phải **trả về nhanh**, tránh thao tác nặng vì nó được gọi bởi cơ chế lập lịch của JFR và có thể cản trở các công việc ghi/chẩn đoán khác.
- Số event thực tế **không phải bảo đảm thời gian thực**; phụ thuộc thời gian chạy, lịch JVM, tải hệ thống, trạng thái enable và ghi file. Vì vậy không nên có unit test yêu cầu chính xác 5 sự kiện khi ngủ 1 giây.

### 3.2. `period` có thể có giá trị đặc biệt

Ngoài chu kỳ thời gian như `"200 ms"`, metadata JFR hỗ trợ các giá trị chu kỳ gắn với **chunk** (phân đoạn recording), trong đó `"everyChunk"` nghĩa là phát ít nhất một lần theo mỗi chunk theo cách cơ chế JFR cung cấp. Ví dụ một số built-in JFR events dùng `everyChunk` hoặc các giai đoạn chunk tương ứng.

Có thể cấu hình kiểu chuỗi cho loại hỗ trợ:

```java
recording.enable("jdk.ThreadAllocationStatistics")
        .with("period", "everyChunk");
```

**Đây là cấu hình minh họa**: tần suất chunk phụ thuộc việc quay vòng/chốt dữ liệu, không tương đương `Duration.ofSeconds(...)` hay một timer cố định. Không sử dụng `everyChunk` để hứa số event/giây. Với custom event, chỉ chọn chế độ chu kỳ phù hợp với cách JFR đã đăng ký hook và tính chất dữ liệu.

## 4. `withThreshold(Duration)` — lọc sự kiện theo thời lượng

Một **duration event** có thời điểm bắt đầu/kết thúc và thời lượng đo được. Đối với những event có setting ngưỡng, `withThreshold(d)` lọc các event có `duration` **nhỏ hơn `d`**; những event đạt ngưỡng trở lên mới đủ điều kiện ghi nếu các settings khác cho phép.

```java
recording.enable("jdk.FileRead")
        .withThreshold(Duration.ofMillis(10))
        .withStackTrace();
```

Ví dụ trên nhắm tới các `FileRead` **chậm từ khoảng 10 ms trở lên**, thay vì ghi mọi thao tác đọc file bất kể độ dài. Ngưỡng là thời gian của **event**, không phải kích thước file, số byte hay tổng thời gian recording.

### 4.1. Custom event với `begin()`, `end()` và `commit()`

```java
@Name("demo.Timed")
static class Timed extends Event {
    String label;
}

// Phần nằm trong một phương thức sau khi recording.start():
Timed slow = new Timed();
slow.label = "slow";
slow.begin();
Thread.sleep(80);
slow.end();
slow.commit();
```

Nếu loại `demo.Timed` được cấu hình:

```java
recording.enable("demo.Timed")
        .withThreshold(Duration.ofMillis(20))
        .withStackTrace();
```

thì một event đo khoảng 80 ms **vượt ngưỡng 20 ms** và có thể được ghi. Nếu tạo event tức thời bằng `new Timed().commit()` mà không bao quanh công việc bằng `begin/end`, duration bằng 0 và bị loại bởi threshold 20 ms.

**Lưu ý:** một lời gọi `Thread.sleep(80)` là ví dụ minh họa thời lượng, không phải cách đo benchmark chính xác. Khi phân tích thật, hãy kiểm tra `RecordedEvent.getDuration()`, sự kiện được bật và cách event bao phủ đoạn công việc.

### 4.2. `withoutThreshold()` không có nghĩa tắt event

```java
recording.enable("demo.NoStack")
        .withoutThreshold()
        .withoutStackTrace();
```

`withoutThreshold()` tương đương **`with("threshold", "0 s")`**, tức là **không dùng ngưỡng loại sự kiện dựa vào duration**. Nó **không** đồng nghĩa `Recording.disable(...)`. Nếu event type đã enabled và có `commit()`, một instant event vẫn có thể được ghi.

Mặc định `@Threshold` của custom JFR event là `"0 ns"`, nhưng JFR configuration hoặc code có thể thay đổi; muốn hợp đồng rõ ràng, cấu hình tường minh khi cần.

### 4.3. Ngưỡng và chu kỳ khác nhau hoàn toàn

| Tình huống | Có thay đổi không? |
| --- | --- |
| Event chạy 5 ms, threshold 20 ms | Event không qua bộ lọc thời lượng |
| Event chạy 80 ms, threshold 20 ms | Event qua ngưỡng; vẫn cần enabled và `commit()` |
| Periodic event có period 200 ms | JFR cố gắng gọi hook theo khoảng thời gian tương ứng |
| Threshold 20 ms | **Không** gây event được gọi mỗi 20 ms |
| Period 200 ms | **Không** tự bỏ các event dưới 200 ms |
| Threshold 0 | Không có bộ lọc duration; nhưng vẫn có thể có các bộ lọc/giới hạn khác |

Không dùng `withThreshold(Duration.ZERO)` như một phương án mặc định cho mọi event có tần suất rất cao. Ghi thêm event có thể làm tăng lượng dữ liệu và chi phí thu thập.

## 5. `withStackTrace()` và `withoutStackTrace()`

### 5.1. Khi bật stack trace

```java
recording.enable("demo.Timed")
        .withStackTrace();
```

Thiết lập này yêu cầu JFR ghi lại **ngăn xếp lời gọi** cho các sự kiện đã được ghi, nếu loại sự kiện và runtime hỗ trợ. Với event ứng dụng kế thừa `jdk.jfr.Event`, tài liệu `@StackTrace` mô tả stack trace gắn với **thời điểm gọi `Event.commit()`**; không tự động có nghĩa là stack tại thời điểm `begin()` hoặc nguồn gốc mọi thao tác trước đó.

Khi đọc file `.jfr`:

```java
RecordedEvent event = ...; // Event đã đọc từ RecordingFile.
boolean hasStack = event.getStackTrace() != null;
```

`RecordedEvent.getStackTrace()` trả `null` nếu event **không có stack trace**. Với event có trace, có thể xem `getFrames()` để điều tra các frame liên quan. Kết quả phụ thuộc loại event, runtime và thiết lập; không kết luận tuyệt đối rằng stack trace phải có frame ở mọi môi trường.

### 5.2. Khi tắt stack trace

```java
recording.enable("demo.NoStack")
        .withoutStackTrace();
```

Thiết lập `stackTrace=false` giảm lượng dữ liệu và chi phí lưu/capture stack trên những loại event nơi ngăn xếp không cần thiết. **Event vẫn có thể được ghi** với timestamp, duration và các trường dữ liệu được định nghĩa. Trong ví dụ đã thử nghiệm, `RecordedEvent.getStackTrace()` của `demo.NoStack` trả `null`.

### 5.3. Vì sao không bật stack trace vô điều kiện?

- Mỗi stack trace tăng metadata phải ghi, xử lý, truyền và phân tích.
- Tần suất event và độ sâu stack ảnh hưởng lượng dữ liệu; nhiều sự kiện ngắn nhưng có trace có thể tốn nhiều hơn một bộ event có ngưỡng phù hợp.
- Trong production, chỉ bật trace cho những loại sự kiện hỗ trợ điều tra nguyên nhân, và theo dõi overhead thực tế.
- Việc bật stack trace **không** bảo đảm tìm ra nguyên nhân nguồn gốc (root cause); đó là bức tranh về lời gọi tại vị trí ghi event.

**Khác với Java exception stack trace:** `withStackTrace` cấu hình thông tin của **JFR event**, không bật/tắt `Throwable.getStackTrace()` của exception Java nói chung.

## 6. Annotation mặc định và cấu hình theo recording

Các annotation ở cấp **loại sự kiện** thiết lập mặc định:

```java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Period;
import jdk.jfr.StackTrace;
import jdk.jfr.Threshold;

@Name("demo.DatabaseRequest")
@Threshold("15 ms")
@StackTrace(true)
class DatabaseRequest extends Event {
    String operation;
}

@Name("demo.Tick")
@Period("1 s")
class Tick extends Event {
    int sequence;
}
```

Những khai báo trên là **ví dụ lớp riêng biệt**; `Tick` còn cần periodic hook nếu muốn JFR phát theo chu kỳ. `@Threshold` quy định **mặc định** duration cần đạt; `@StackTrace` quy định **mặc định** có ghi trace; `@Period` quy định **mặc định** period.

Recording có thể override:

```java
try (Recording r = new Recording()) {
    r.enable("demo.DatabaseRequest")
            .withThreshold(Duration.ofMillis(30))
            .withoutStackTrace();

    r.enable("demo.Tick")
            .withPeriod(Duration.ofMillis(200));
}
```

Ở đây, dù `@Threshold("15 ms")` và `@StackTrace(true)` nằm trên class, recording chủ động dùng threshold 30 ms và stackTrace=false. Với `demo.Tick`, cấu hình chu kỳ 200 ms thay cho mặc định 1 giây.

**Khi một JVM có nhiều recording đồng thời**, cơ chế thu thập và các setting hiệu dụng có thể chịu ảnh hưởng bởi cách JVM kết hợp nhu cầu của các recording; đừng mặc nhiên coi JFR luôn tạo một bộ event độc lập tại nguồn cho mỗi recording. Hãy dựa vào dữ liệu thực tế đọc từ từng recording, và thử nghiệm khi cần điều chỉnh production settings.

### 6.1. Tên setting dùng với `with(String, String)`

Các tên chuẩn:

```java
eventSettings.with("period", "200 ms");
eventSettings.with("threshold", "20 ms");
eventSettings.with("stackTrace", "true");
eventSettings.with("stackTrace", "false");
```

Những dòng trên là **trích đoạn** với biến `eventSettings` kiểu `EventSettings`. Khi có convenience method, nên dùng `withPeriod`, `withThreshold`, `withStackTrace` và `withoutStackTrace` để giảm lỗi gõ tên/đơn vị và rõ ý hơn.

Tên setting khác có thể tồn tại cho event cụ thể; tra metadata từ `EventType.getSettingDescriptors()` trước khi dựa vào một tên không chuẩn.

## 7. `Recording.getSettings()`, tên event và ID

JFR cung cấp:

```java
Map<String, String> settings = recording.getSettings();
```

Trong `Map`, key thường có dạng **`eventName#settingName`** hoặc **`eventId#settingName`**, phụ thuộc cách bạn gọi `Recording.enable(...)`. Với overload nhận **String**:

```java
recording.enable("demo.Timed")
        .withThreshold(Duration.ofMillis(20));
```

có thể đọc key `"demo.Timed#threshold"`; còn overload nhận `Class` có thể sử dụng **ID event type** trong key, ví dụ `"1855#threshold"`. **Không hardcode event ID**, vì ID do runtime cấp và không ổn định giữa các lần chạy.

Giá trị `Duration` có thể được chuẩn hóa khi lưu setting thành chuỗi đơn vị nanosecond. Trên JDK 17 đã kiểm thử:

```text
demo.Tick#period       = 200000000 ns
demo.Timed#threshold   = 20000000 ns
demo.NoStack#stackTrace = false
```

Đây là ví dụ representation khi dùng `enable("demo...")`, **không phải định dạng output phải parse cứng xuyên mọi JDK**. Nếu cần xác minh cấu hình, đọc map và metadata trên runtime thực tế, chú ý bạn đang dùng overload nào.

### Tại sao `getSettings()` không đủ để biết event đã xuất hiện?

`getSettings()` chỉ cho thấy **cấu hình được yêu cầu**. Một periodic event vẫn có thể không xuất hiện nếu chưa đăng ký hook, recording chạy quá ngắn, event disabled hoặc hệ thống không phát. Một duration event có thể không qua threshold hoặc không `commit()`. Để xác minh dữ liệu thực có trong file, dùng API consumer như `RecordingFile.readAllEvents(...)`.

## 8. Quy trình tạo, ghi, đọc JFR một cách đúng đắn

1. **Xác định event type** cần quan sát (ví dụ built-in `jdk.CPULoad`, `jdk.FileRead`, hoặc custom `demo.Timed`).
2. **Xác định kiểu phát event:** có phải periodic event có hook, hay duration/instant event do code `commit()`?
3. **Bật và cấu hình** mỗi loại bằng `Recording.enable(...)` và `EventSettings` **trước khi `start()`**.
4. **Bắt đầu recording**, chạy workload; với custom duration event, gọi `begin()`, `end()`, `commit()`; với periodic event, hook sẽ tạo và commit theo cơ chế JFR.
5. **Dừng recording**, `dump(Path)` để lưu file `.jfr` nếu cần phân tích ngoài tiến trình.
6. **Đọc lại** bằng `RecordingFile` hoặc công cụ `jfr` / JDK Mission Control; đối chiếu duration, stack trace, số lượng event và điều kiện lọc.
7. **Giải phóng tài nguyên** với `try-with-resources` cho `Recording`, tháo periodic hook nếu tự đăng ký, và xử lý file tạm nếu có.

Với production, có thể sử dụng template JFR sẵn có (như `default.jfc` hoặc cấu hình riêng) và bật/tắt linh hoạt theo mục tiêu chẩn đoán. Tránh lấy mã demo gọi `Thread.sleep` làm một cấu hình thu thập mẫu chung cho production.

## 9. Chương trình Java 17+ hoàn chỉnh, đã kiểm chứng

Ví dụ này tạo **ba custom JFR event types** để kiểm tra độc lập **threshold**, **period** và **stack trace**. Lưu tệp **`JfrEventSettingsDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import jdk.jfr.Event;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Name;
import jdk.jfr.Period;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrEventSettingsDemo {
    @Name("demo.Timed")
    static class Timed extends Event {
        String label;
    }

    @Name("demo.NoStack")
    static class NoStack extends Event {
        String label;
    }

    @Name("demo.Tick")
    @Period("1 s")
    static class Tick extends Event {
        int sequence;
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger counter = new AtomicInteger();

        Runnable hook = () -> {
            Tick event = new Tick();
            event.sequence = counter.incrementAndGet();
            event.commit();
        };

        FlightRecorder.addPeriodicEvent(Tick.class, hook);
        Path path = Files.createTempFile("jfr-eventsettings-", ".jfr");

        try {
            try (Recording recording = new Recording()) {
                recording.enable("demo.Timed")
                        .withThreshold(Duration.ofMillis(20))
                        .withStackTrace();

                recording.enable("demo.NoStack")
                        .withoutThreshold()
                        .withoutStackTrace();

                recording.enable("demo.Tick")
                        .withPeriod(Duration.ofMillis(200))
                        .withoutStackTrace();

                System.out.println("periodSetting=" +
                        recording.getSettings().get("demo.Tick#period"));
                System.out.println("thresholdSetting=" +
                        recording.getSettings().get("demo.Timed#threshold"));
                System.out.println("traceSetting=" +
                        recording.getSettings().get("demo.NoStack#stackTrace"));

                recording.start();

                Timed fast = new Timed();
                fast.label = "fast";
                fast.commit(); // Duration = 0, dưới threshold 20 ms.

                Timed slow = new Timed();
                slow.label = "slow";
                slow.begin();
                Thread.sleep(80);
                slow.end();
                slow.commit(); // Đạt threshold 20 ms.

                NoStack brief = new NoStack();
                brief.label = "instant";
                brief.commit(); // Không có threshold.

                Thread.sleep(1100); // Cho hook định kỳ cơ hội chạy.

                recording.stop();
                recording.dump(path);
            }

            List<RecordedEvent> events = RecordingFile.readAllEvents(path);

            long fast = events.stream()
                    .filter(e -> e.getEventType().getName().equals("demo.Timed"))
                    .filter(e -> e.getString("label").equals("fast"))
                    .count();

            List<RecordedEvent> slow = events.stream()
                    .filter(e -> e.getEventType().getName().equals("demo.Timed"))
                    .filter(e -> e.getString("label").equals("slow"))
                    .toList();

            List<RecordedEvent> noStack = events.stream()
                    .filter(e -> e.getEventType().getName().equals("demo.NoStack"))
                    .toList();

            List<RecordedEvent> ticks = events.stream()
                    .filter(e -> e.getEventType().getName().equals("demo.Tick"))
                    .toList();

            System.out.println("fastRecorded=" + (fast > 0));
            System.out.println("slowRecorded=" + (slow.size() == 1));
            System.out.println("slowHasStack=" +
                    (slow.size() == 1 && slow.get(0).getStackTrace() != null));
            System.out.println("noStackRecorded=" + (noStack.size() == 1));
            System.out.println("noStackHasStack=" +
                    (!noStack.isEmpty() && noStack.get(0).getStackTrace() != null));
            System.out.println("periodicRecorded=" + (!ticks.isEmpty()));
            System.out.println("periodicHasStack=" +
                    (!ticks.isEmpty() && ticks.get(0).getStackTrace() != null));
        } finally {
            FlightRecorder.removePeriodicEvent(hook);
            Files.deleteIfExists(path);
        }
    }
}
```

Biên dịch và chạy với JDK có JFR (JDK 17+ thông thường):

```bash
javac --release 17 JfrEventSettingsDemo.java
java JfrEventSettingsDemo
```

Kết quả đã kiểm chứng trên JDK 17:

```text
periodSetting=200000000 ns
thresholdSetting=20000000 ns
traceSetting=false
fastRecorded=false
slowRecorded=true
slowHasStack=true
noStackRecorded=true
noStackHasStack=false
periodicRecorded=true
periodicHasStack=false
```

**Diễn giải 10 dòng:**

1. `periodSetting=200000000 ns`: 200 ms được biểu diễn tương ứng 200 triệu nanosecond trong setting map của bản JDK đã thử.
2. `thresholdSetting=20000000 ns`: threshold 20 ms được lưu tương ứng 20 triệu nanosecond.
3. `traceSetting=false`: loại `demo.NoStack` được cấu hình không lưu stack trace.
4. `fastRecorded=false`: event `fast` không gọi `begin/end`, duration bằng 0 nên **bị threshold 20 ms loại**.
5. `slowRecorded=true`: event `slow` ngủ 80 ms, vượt threshold và được ghi.
6. `slowHasStack=true`: `demo.Timed` có `withStackTrace()`; event ghi nhận kèm stack trace.
7. `noStackRecorded=true`: `withoutThreshold()` cho phép instant event `demo.NoStack` được ghi.
8. `noStackHasStack=false`: `withoutStackTrace()` làm `getStackTrace()` trả `null` cho event đó.
9. `periodicRecorded=true`: hook của `demo.Tick` được JFR gọi trong khoảng recording và có event được ghi.
10. `periodicHasStack=false`: hook phát event, nhưng cấu hình loại `demo.Tick` không lưu stack trace.

**Tính ổn định của ví dụ:** các dòng là kết quả của lần chạy đã kiểm tra. Số lượng periodic events, chính tả/đơn vị của map settings hoặc việc event kịp phát trong một recording cực ngắn có thể thay đổi theo JDK và lịch hệ thống; bởi vậy code chỉ kiểm tra **có ít nhất một tick**, không khẳng định tick count chính xác. Nếu môi trường rất bận hoặc JFR chưa khả dụng, tăng thời gian quan sát/kiểm tra cấu hình JDK thay vì coi đó là quy tắc API.

## 10. Những nhầm lẫn và lỗi thường gặp

### Lỗi A — Lấy `period` làm bộ lọc duration

`withPeriod(Duration.ofMillis(200))` **không** có nghĩa chỉ lưu event dài ít nhất 200 ms. Nó đặt chu kỳ cho loại event **định kỳ**. Muốn lọc event chậm, dùng `withThreshold` trên loại có duration/threshold setting.

### Lỗi B — Lấy `threshold` làm bộ lấy mẫu

`withThreshold(Duration.ofMillis(20))` **không** yêu cầu JFR phát event sau mỗi 20 ms. Nó chỉ lọc những event có duration ngắn hơn 20 ms. Với event không được tạo hoặc không commit, threshold không tự làm gì cả.

### Lỗi C — Đặt period cho custom event nhưng quên hook

`@Period("1 s")` và `withPeriod(...)` không tự chạy logic ứng dụng. Custom periodic event cần đăng ký `FlightRecorder.addPeriodicEvent` với một `Runnable` **phát và commit event**. Nhớ tháo hook bằng `removePeriodicEvent` khi không còn dùng.

### Lỗi D — Nghĩ `withoutStackTrace()` tắt luôn event

`withoutStackTrace()` chỉ tắt trace, **không** tắt dữ liệu event khác. Ví dụ `demo.NoStack` vẫn được ghi khi `withoutThreshold()` và `commit()`. Muốn tắt hẳn loại event, dùng cơ chế `Recording.disable(...)`.

### Lỗi E — Nghĩ `withoutThreshold()` nghĩa là không thu thập event

Sai. Đó là `threshold = 0`, loại bỏ bộ lọc duration, có thể **tăng** số sự kiện được ghi. Việc event được tạo, enabled và đi qua các điều kiện khác vẫn quan trọng.

### Lỗi F — Cấu hình stackTrace nhưng không thấy stack

Hãy kiểm tra: event type có enabled không? Nó có được commit và vượt threshold không? Recording đã chạy và dump thành công chưa? Loại event/runtime có hỗ trợ stack không? `RecordedEvent.getStackTrace()` có thể trả `null` khi không có dữ liệu, không nên truy cập `getFrames()` ngay mà không kiểm tra null.

### Lỗi G — Dùng `Recording.getSettings()` để suy ra số event chắc chắn

Map settings mô tả giá trị **cấu hình**, không phải số event thực tế. Phải đọc recording bằng `RecordingFile`, `jfr print` hoặc công cụ hỗ trợ để biết event nào đã được thu thập.

### Lỗi H — Hardcode event ID trong key cấu hình

`Recording.enable(MyEvent.class)` có thể tạo key gắn với **ID event type** trong `getSettings()`. ID không phải một tên ổn định; muốn dễ đọc, dùng `enable("demo.Timed")` theo `@Name` và đọc chính key được hệ thống trả về.

### Lỗi I — Bật ngưỡng 0 và stack trace cho mọi event

Mọi sự kiện ngắn đều có thể được ghi và trace có thể tăng overhead. Cần chọn event types phù hợp vấn đề, đặt threshold/period thận trọng, xem dữ liệu thật rồi điều chỉnh. Thử nghiệm trên workload đại diện trước khi áp dụng production.

### Lỗi J — Dựa vào thứ tự/số lượng sự kiện định kỳ tuyệt đối

JFR có thể điều chỉnh lịch lấy mẫu và ghi chunk tùy môi trường; không nên viết test bắt buộc đúng **N** events nếu period cố định và thời gian chạy cố định. Test nên xác thực setting đã áp dụng, dữ liệu xuất hiện và tính đúng đắn của trường nội dung; sử dụng khoảng thời gian đủ dài khi cần.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Có thể cấu hình `jdk.CPULoad` lấy mẫu khoảng 1 giây và `jdk.FileRead` chỉ ghi những thao tác chậm hơn ngưỡng 10 ms bằng những phương thức nào?

**Đáp án:** `recording.enable("jdk.CPULoad").withPeriod(Duration.ofSeconds(1))` và `recording.enable("jdk.FileRead").withThreshold(Duration.ofMillis(10))`; thêm `withStackTrace()` cho file read khi cần điều tra call site.

**Câu 2.** Vì sao event tức thời duration 0 không được ghi khi threshold 20 ms nhưng có thể được ghi sau `withoutThreshold()`?

**Đáp án:** `withThreshold(20 ms)` loại event dưới 20 ms. `withoutThreshold()` tương đương ngưỡng 0, nên instant event có thể qua bộ lọc duration, miễn enabled và commit.

**Câu 3.** `withStackTrace()` có bắt JVM lưu mọi Java exception stack trace không?

**Đáp án:** Không. Nó bật trace cho **loại JFR event liên quan**, không cấu hình `Throwable` nói chung.

**Câu 4.** Vì sao `@Period("1 s")` chưa đủ để một custom event xuất hiện mỗi giây?

**Đáp án:** Vì còn cần **periodic hook** đăng ký qua `FlightRecorder.addPeriodicEvent` để phát/commit event. Cấu hình period chỉ định khoảng yêu cầu, không tự có logic tạo dữ liệu.

**Câu 5.** Vì sao `r.enable("demo.Timed").withThreshold(...)` thường dễ kiểm tra `r.getSettings()` hơn `r.enable(Timed.class)`?

**Đáp án:** Overload nhận String có thể tạo key `demo.Timed#threshold`, còn overload nhận Class có thể dùng event ID trong key. ID không ổn định giữa các lần chạy.

**Câu 6.** Dòng `recording.enable("demo.NoStack").withoutStackTrace()` có ngăn code gọi `new NoStack().commit()` không?

**Đáp án:** Không. `commit()` vẫn được gọi; nếu event được bật và đủ điều kiện, dữ liệu vẫn được ghi nhưng không có stack trace.

**Câu 7.** Nếu `period=200 ms`, sau 1 giây có chắc chắn chính xác 5 events không?

**Đáp án:** Không. Đây là cấu hình tần suất, không phải cam kết realtime; lịch JVM và lifecycle recording có thể ảnh hưởng số event.

**Câu 8.** Để đọc stack trace từ file `.jfr`, dùng API nào và cần phòng vệ gì?

**Đáp án:** `RecordingFile.readAllEvents(path)` trả các `RecordedEvent`; gọi `event.getStackTrace()`, kiểm tra `!= null` trước khi dùng `getFrames()`.

## 12. Checklist triển khai thực tế

- [ ] Xác định sự kiện cần đo là **periodic**, **duration** hay **instant**, đừng dùng sai loại setting.
- [ ] Lấy `EventSettings` từ `Recording.enable(String/Class)`; dùng method chaining rõ ràng.
- [ ] Cấu hình **trước `Recording.start()`** khi có thể.
- [ ] Với periodic event: chọn `withPeriod(Duration)` và bảo đảm có hook khi tự tạo event.
- [ ] Với duration event: chọn `withThreshold(Duration)` phù hợp mục tiêu; hiểu `withoutThreshold` là ngưỡng 0.
- [ ] Bật `withStackTrace` khi cần điều tra call site; tắt bằng `withoutStackTrace` khi overhead không đáng.
- [ ] Nếu cần giá trị mặc định ở class event, dùng `@Period`/`@Threshold`/`@StackTrace`; cấu hình recording có thể ghi đè.
- [ ] Không hardcode ID của JFR event trong `getSettings()`; đọc đúng tên/ID được runtime cung cấp.
- [ ] Phân biệt **cấu hình** và **dữ liệu thực đã ghi**; đọc file `.jfr` để xác nhận duration/trace/periodic events.
- [ ] Bảo đảm `Recording` được đóng, periodic hooks được tháo, file JFR được bảo vệ phù hợp do có thể chứa thông tin kỹ thuật nhạy cảm.
- [ ] Không áp đặt test định lượng cứng về số event định kỳ hoặc message/đơn vị settings xuyên mọi JDK.
- [ ] Đo chi phí trong workload thực tế; đừng bật threshold 0 + stack trace cho toàn bộ event tần suất cao một cách mặc định.

## 13. Tài liệu chính thức đang áp dụng

1. [Oracle Java SE 25 — `jdk.jfr.EventSettings`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): API `withPeriod`, `withThreshold`, `withoutThreshold`, `withStackTrace`, `withoutStackTrace` và `with`.
2. [Oracle Java SE 25 — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html): `enable`/`disable`, `start`, `stop`, `dump`, `getSettings`.
3. [Oracle Java SE 25 — `jdk.jfr.Period`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Period.html): period mặc định và periodic hooks, `everyChunk`.
4. [Oracle Java SE 25 — `jdk.jfr.Threshold`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Threshold.html): ngưỡng duration mặc định và tên setting.
5. [Oracle Java SE 25 — `jdk.jfr.StackTrace`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/StackTrace.html): setting `stackTrace` và ghi stack tại `Event.commit()`.
6. [Oracle Java SE 25 — `jdk.jfr.FlightRecorder`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/FlightRecorder.html): `addPeriodicEvent` và `removePeriodicEvent`.
7. [Oracle Java SE 25 — `RecordedEvent`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): `getDuration()`, `getStackTrace()` và metadata event được ghi.
