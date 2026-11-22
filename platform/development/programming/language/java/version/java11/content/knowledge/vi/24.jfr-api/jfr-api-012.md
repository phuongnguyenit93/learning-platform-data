# Kiểm thử JFR API: sự kiện được ghi đúng trường, thời điểm và điều kiện (Java 11+)

## 1. Mục tiêu của bài học

**JDK Flight Recorder (JFR)** là hệ thống ghi sự kiện chẩn đoán của JVM. Java 11 cung cấp public API `jdk.jfr.Event`, `Recording`, `EventSettings`, `RecordingFile` và `RecordedEvent` để ứng dụng tự phát và kiểm tra sự kiện. Chỉ nhìn thấy một file `.jfr` chưa đủ khẳng định sự kiện nghiệp vụ đã được ghi đúng.

Một **integration test JFR** nên chứng minh đầy đủ:

1. **Đúng fields:** các giá trị `long`, `String`, `int`, `boolean` phải được ghi đúng tên và kiểu; không có những trường `static` hoặc `transient` không thuộc event schema.
2. **Đúng event type:** kiểm tra `@Name`, `@Label`, `@Category` qua `EventType`, lọc chính xác custom event thay vì đếm mọi JVM event.
3. **Đúng thời điểm:** `getStartTime()`, `getEndTime()`, `getDuration()` phải nhất quán với khoảng xử lý và ngưỡng thời lượng.
4. **Đúng điều kiện:** event chỉ được ghi khi recording đang chạy, event được bật, vượt threshold và code thực hiện `commit()` theo business rule.
5. **Đọc lại sau khi dump:** dùng `RecordingFile`/`RecordedEvent` để assert nội dung thực, không kết luận chỉ từ `event.commit()` hoặc stdout của application.

Toàn bộ API sử dụng **vẫn còn áp dụng trong JDK hiện đại** và tương thích **Java 11 trở lên**. Không dựa vào API nội bộ `jdk.internal.*`, thư viện JFR lỗi thời hay tiện ích chỉ có ở một phiên bản JDK mới.

Bài có **hai chương trình Java 11 độc lập đã được biên dịch và chạy thật**: một kiểm tra fields, timestamp và business condition; một kiểm tra trường hợp event bị threshold lọc. Đầu ra của cả hai được ghi chính xác để học và tái hiện.

## 2. Luồng dữ liệu từ Event đến RecordedEvent

```text
@Name, @Label, @Category, public fields
             |
      Custom Event class
             |
             v
  Recording + EventSettings
 enabled / threshold / stackTrace
             |
      recording.start()
             |
   +---------+-----------------------------+
   |         |                             |
   v         v                             v
event đúng  disabled / under threshold  business rule false
fields      có thể gọi commit nhưng      không gọi commit
begin/end   JFR không ghi
commit()
   |         |                             |
   +---------+-----------------------------+
             |
        recording.stop()
        recording.dump(.jfr)
             |
        RecordingFile
             |
   lọc EventType.getName()
             |
   assert count + fields + metadata + thời gian
```

**`.jfr` là file recording nhị phân**, không phải cấu hình `.jfc`. JVM có thể ghi các loại event khác nhau; `RecordingFile.readAllEvents(file).size()` không phải số custom events nghiệp vụ. Filter bằng event name trước khi xác minh.

## 3. Định nghĩa event có dữ liệu và metadata rõ ràng

```java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Threshold;

@Name("lesson.OrderValidation")
@Label("Order validation")
@Category({"Learning", "JFR"})
@Threshold("10 ms")
public class OrderValidation extends Event {
    @Label("Order ID")
    public long orderId;

    @Label("Status")
    public String status;

    @Label("Quantity")
    public int quantity;

    @Label("Approved")
    public boolean approved;
}
```

Đây là **một class Java dùng để minh họa**, có thể lưu thành `OrderValidation.java`. Trong chương trình đầy đủ ở mục 8, một class tương đương được khai báo dưới dạng nested class để thuận tiện chạy một file.

| Thành phần | Hợp đồng cần kiểm tra |
| --- | --- |
| `@Name` | Tên định danh ổn định `lesson.OrderValidation`, dùng để filter |
| `@Label` | Nhãn thân thiện `Order validation`, qua `EventType.getLabel()` |
| `@Category` | Hai nhóm `Learning`, `JFR`, qua `EventType.getCategoryNames()` |
| `@Threshold("10 ms")` | Threshold mặc định của timed event, có thể override |
| `long orderId` | Đọc bằng `RecordedEvent.getLong("orderId")` |
| `String status` | Đọc bằng `getString("status")` |
| `int quantity` | Đọc bằng `getInt("quantity")` |
| `boolean approved` | Đọc bằng `getBoolean("approved")` |

**Name khác Label:** label có thể thay đổi để đẹp hơn trong công cụ JFR; name là định danh mà consumer code nên dùng. Nếu test lọc bằng label, việc chỉnh UI metadata có thể làm test fail ngoài ý muốn.

### 3.1. Field types và những field bị bỏ qua

Theo Javadoc `jdk.jfr.Event`, field có thể dùng các kiểu primitive Java (`boolean`, `char`, `byte`, `short`, `int`, `long`, `float`, `double`) và các kiểu tham chiếu được hỗ trợ như `String`, `Thread`, `Class`. Các field `static` và `transient` **không được ghi vào event data**.

```java
public long orderId;                     // Được ghi.
public String status;                    // Được ghi.
public transient String notRecorded;     // Bị loại.
public static String note = "constant";  // Bị loại.
```

`List<String>`, array, enum hoặc một POJO tùy ý **không tự được serialize như field JFR**. Nếu cần lưu thông tin, chọn một biểu diễn đơn giản được hỗ trợ, có giới hạn: `itemCount`, `operation`, `latencyNanos`... Không đưa password, token, cookie hay dữ liệu khách hàng nhạy cảm vào event hoặc file .jfr.

### 3.2. Kiểm tra kiểu trường qua EventType

```java
EventType type = e.getEventType();
boolean orderIdIsLong = type.getFields().stream()
        .anyMatch(f -> f.getName().equals("orderId")
                    && f.getTypeName().equals("long"));
```

Đây là snippet có biến `RecordedEvent e` từ file và import `EventType`. `ValueDescriptor.getName()/getTypeName()` giúp kiểm tra schema ngay cả khi field value tạm thời bằng 0 hoặc null.

## 4. Vòng đời Event và ý nghĩa commit

### 4.1. Instant event

```java
OrderValidation e = new OrderValidation();
e.orderId = 101L;
e.status = "APPROVED";
e.quantity = 3;
e.approved = true;
e.commit();
```

Một event chỉ `commit()`, không `begin()`/`end()`, thông thường có start time bằng end time và duration 0 (instant event). Nếu recording đặt threshold dương cho event thời lượng, instant event này có thể **bị lọc**, dù đã gọi commit.

### 4.2. Timed event

```java
OrderValidation e = new OrderValidation();
e.orderId = 101L;
e.status = "APPROVED";

e.begin();
performWork(); // Hàm nghiệp vụ minh họa, chưa định nghĩa.
e.end();

if (e.shouldCommit()) {
    e.commit();
}
```

Đây là snippet minh họa cần class event và hàm `performWork`; chương trình đầy đủ dùng `Thread.sleep(45)` thay cho `performWork()`.

- `begin()`: ghi nhận thời điểm bắt đầu.
- `end()`: kết thúc đo thời lượng; phải gọi sau begin. Nếu đã begin nhưng chưa end, `commit()` tự kết thúc event theo contract.
- `commit()`: cố ghi field values, timestamp và duration vào JFR nếu thỏa settings hiện tại; **không trả boolean cho biết đã có trong file**.
- `isEnabled()`: true nếu **ít nhất một recording đang chạy** bật loại event.
- `shouldCommit()`: true khi event instance thỏa enabled và duration/threshold để có thể được ghi.

**Gọi `shouldCommit()` sau `end()`** với timed event; nếu duration chưa xác định, kết luận về threshold sẽ không phản ánh khoảng xử lý hoàn tất.

### 4.3. `isEnabled()` không giống `shouldCommit()`

| Trạng thái | `isEnabled()` | `shouldCommit()` |
| --- | --- | --- |
| Không có recording đang bật event | false | false |
| Đã bật event, duration chưa đủ threshold | true | false |
| Đã bật event, duration >= threshold | true | true |
| Business rule false nhưng JFR vẫn bật | Có thể true | Có thể true; **ứng dụng vẫn không commit** |

Ví dụ event enabled, duration 2 ms, threshold 15 ms: `isEnabled` có thể true, nhưng `shouldCommit` false. Ngược lại, `shouldCommit` true **không đồng nghĩa** business policy muốn ghi event.

## 5. Cấu hình Recording và điều kiện ghi

```java
try (Recording recording = new Recording()) {
    recording.enable(OrderValidation.class)
            .withThreshold(Duration.ofMillis(15))
            .withoutStackTrace();
    recording.start();
    // Phát event trong khoảng recording đang chạy.
    recording.stop();
    recording.dump(Path.of("validated.jfr"));
}
```

Đây là snippet cần imports `Recording`, `Duration`, `Path` và class event. Nó cho thấy:

1. `@Threshold("10 ms")` là **mặc định trên event class**.
2. `Recording.enable(...).withThreshold(Duration.ofMillis(15))` chọn threshold **15 ms cho recording này**, ghi đè default.
3. `withoutStackTrace()` giúp giảm event overhead khi test không cần stack traces.
4. `start()` phải diễn ra trước `commit`; sau `stop()` không thu thập event mới cho recording đã dừng.
5. `dump(...)` tạo .jfr đọc được; gọi trong vòng đời recording, trước `close()`.
6. `try-with-resources` đảm bảo cleanup kể cả khi có exception.

### 5.1. Nhiều recording trong cùng một JVM

Nếu recording A disable loại event nhưng recording B đang enable cùng loại, `e.isEnabled()` vẫn có thể **true**. `shouldCommit()` xét những setting của các recording đang chạy, không phải một bản ghi riêng lẻ.

Để test cô lập: không khởi động JFR từ startup flag cùng event, không để test khác giữ recording đang chạy, và tốt nhất mỗi suite điều kiện nhạy cảm với `isEnabled` chạy trong JVM process riêng.

### 5.2. Lọc theo duration và business rule

Một event được bật vẫn có thể không ghi vì **duration < threshold**. Khi cần lọc nghiệp vụ, dùng:

```java
if (approvedByPolicy && event.shouldCommit()) {
    event.commit();
}
```

Biến `approvedByPolicy` do application tính; nếu false, **không gọi commit**. Đừng nhầm conditional branch trong ứng dụng với JFR threshold. Cũng không nên gộp cả điều kiện disabled và threshold cao vào cùng một negative test, vì sẽ khó chỉ ra nguyên nhân riêng.

## 6. Xác minh một file recording thật

```java
List<RecordedEvent> events =
        RecordingFile.readAllEvents(recordingPath).stream()
        .filter(e -> "lesson.OrderValidation"
                .equals(e.getEventType().getName()))
        .collect(Collectors.toList());
```

Snippet cần imports `List`, `Collectors`, `RecordedEvent`, `RecordingFile` và biến `Path recordingPath`.

Với một sự kiện hợp lệ, assert đầy đủ:

```java
if (events.size() != 1) {
    throw new AssertionError("Expected exactly one event");
}
RecordedEvent event = events.get(0);
boolean correct =
        event.getLong("orderId") == 20261107L
        && "APPROVED".equals(event.getString("status"))
        && event.getInt("quantity") == 3
        && event.getBoolean("approved");
```

**Không chỉ kiểm tra có một event bất kỳ:** file .jfr có thể chứa JVM events. Và **không chỉ kiểm tra field tồn tại:** các kiểu primitive có giá trị mặc định 0/false ngay cả khi quên gán.

### 6.1. Metadata và field bị loại

```java
EventType type = event.getEventType();
boolean metadataCorrect =
        "lesson.OrderValidation".equals(type.getName())
        && "Order validation".equals(type.getLabel())
        && type.getCategoryNames()
               .equals(Arrays.asList("Learning", "JFR"));

boolean transientAbsent = type.getFields().stream()
        .noneMatch(f -> f.getName().equals("notRecorded"));
boolean staticAbsent = type.getFields().stream()
        .noneMatch(f -> f.getName().equals("staticNote"));
```

Kiểm tra này phát hiện một thay đổi không mong muốn về event metadata và tránh vô tình đưa field nhạy cảm vào event schema. Nên dùng assertions thật để fail test nếu giá trị khác, không chỉ in ra console rồi tuyên bố PASS.

## 7. Kiểm thử thời điểm: start, end, duration, thread

`RecordedEvent` cung cấp:

| API | Kiểu | Dùng để kiểm tra |
| --- | --- | --- |
| `getStartTime()` | `Instant` | Mốc bắt đầu event |
| `getEndTime()` | `Instant` | Mốc kết thúc |
| `getDuration()` | `Duration` | Khoảng thời gian đã đo |
| `getThread()` | `RecordedThread` hoặc null | Thread ghi event nếu có metadata |
| `getEventType()` | `EventType` | Schema và metadata |

Trong code test:

```java
Instant before = Instant.now();
event.begin();
Thread.sleep(45);
event.end();
event.commit();
Instant after = Instant.now();
```

Sau khi đọc lại `RecordedEvent recorded`:

```java
Instant start = recorded.getStartTime();
Instant end = recorded.getEndTime();
Duration duration = recorded.getDuration();

boolean ordered = !end.isBefore(start);
boolean withinWindow =
        !start.isBefore(before.minusSeconds(2))
        && !end.isAfter(after.plusSeconds(2));
boolean consistent =
        Duration.between(start, end).equals(duration);
```

Đây là snippets, cần import `Instant`, `Duration` và khai báo các biến tương ứng.

### 7.1. Vì sao không so thời gian chính xác?

`Thread.sleep(45)` không có cam kết chỉ ngủ đúng 45.000 ms. GC pause, OS scheduling, CPU load, clock resolution, virtualization và việc JFR chuyển timestamp sang `Instant` đều có thể ảnh hưởng. Test exact nanosecond sẽ dễ flaky.

**Kiểm tra tốt:** duration ít nhất threshold (15ms), start/end đúng thứ tự, start và end nằm trong cửa sổ đủ rộng quanh thao tác test (ví dụ ±2 giây). Đây là kiểm thử **đúng giai đoạn**, không phải benchmark chuẩn đo latency production.

Nếu muốn so thời lượng ở độ chính xác cao, thiết kế benchmark và dữ liệu đo riêng; không dùng `System.currentTimeMillis()` làm monotonic latency timer.

### 7.2. Thread metadata

Khi `event.getThread()!=null`, `getJavaName()` giúp xem thread. Trong demo đồng bộ chạy từ `main`, đầu ra được kiểm thử là `thread name: main`. Với async executor, thread name có thể khác; đừng hardcode `main` ngoài unit test cô lập. Trường hợp event không có thread metadata, `getThread()` có thể trả null.

### 7.3. Timestamp tự định nghĩa khác JFR timestamp

Nếu cần lưu thêm thời điểm nghiệp vụ:

```java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Timestamp;
import jdk.jfr.Timespan;

@Name("lesson.TimingMetadata")
public class TimingMetadata extends Event {
    @Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)
    public long receivedAtMillis;

    @Timespan(Timespan.NANOSECONDS)
    public long queueWaitNanos;
}
```

Đây là class minh họa, không thuộc chương trình đầy đủ. `@Timestamp`/`@Timespan` giúp diễn giải **field do ứng dụng gán**; không thay thế `getStartTime()/getEndTime()/getDuration()` do JFR ghi. Không ghi `System.nanoTime()` vào field được chú thích epoch milliseconds.


## 8. Ví dụ Java 11 hoàn chỉnh: kiểm tra trường, thời gian và điều kiện nghiệp vụ

Chương trình `JfrEventValidationDemo.java` dưới đây đã được biên dịch bằng `javac --release 11`, chạy trên JDK có JFR mà không cần Internet/Maven/Gradle. Nó tạo **hai recording riêng**:

- Recording thứ nhất: event disabled, dù gọi commit nhưng count đọc lại bằng **0**.
- Recording thứ hai: event enabled, threshold 15 ms, một event kéo dài ~45 ms được commit; một event bị business rule từ chối **không được commit**.
- Sau khi `stop/dump`, đọc file và assert count, fields, metadata, timestamps, duration, static/transient và thread name.

### 8.1. Tệp `JfrEventValidationDemo.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.EventType;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.Threshold;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrEventValidationDemo {
    @Name("lesson.OrderValidation")
    @Label("Order validation")
    @Category({"Learning", "JFR"})
    @Threshold("10 ms")
    public static class OrderValidation extends Event {
        @Label("Order ID")
        public long orderId;
        @Label("Status")
        public String status;
        @Label("Quantity")
        public int quantity;
        @Label("Approved")
        public boolean approved;
        public transient String notRecorded;
        public static String staticNote = "not-event-data";
    }

    static List<RecordedEvent> onlyOrderEvents(Path file) throws Exception {
        return RecordingFile.readAllEvents(file).stream()
                .filter(e -> e.getEventType().getName()
                        .equals("lesson.OrderValidation"))
                .collect(Collectors.toList());
    }

    static void verify(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass output directory");
        }
        Path dir = Path.of(args[0]);
        Path offFile = dir.resolve("disabled.jfr");

        try (Recording off = new Recording()) {
            off.disable(OrderValidation.class);
            off.start();
            OrderValidation omitted = new OrderValidation();
            boolean enabledWhenDisabled = omitted.isEnabled();
            omitted.orderId = -1L;
            omitted.commit();
            off.stop();
            off.dump(offFile);
            verify(!enabledWhenDisabled,
                    "disabled event mistakenly enabled");
            System.out.println("disabled isEnabled: " + enabledWhenDisabled);
        }

        List<RecordedEvent> disabled = onlyOrderEvents(offFile);
        verify(disabled.isEmpty(), "disabled event was recorded");
        System.out.println("disabled file event count: " + disabled.size());

        Path onFile = dir.resolve("validated.jfr");
        Instant before, after;
        boolean commitAllowed;
        boolean enabledWhenRunning;
        boolean rejectedByBusinessRule = true;

        try (Recording on = new Recording()) {
            on.enable(OrderValidation.class)
                    .withThreshold(Duration.ofMillis(15))
                    .withoutStackTrace();
            on.start();

            OrderValidation good = new OrderValidation();
            enabledWhenRunning = good.isEnabled();
            good.orderId = 20261107L;
            good.status = "APPROVED";
            good.quantity = 3;
            good.approved = true;
            good.notRecorded = "should-not-appear";

            before = Instant.now();
            good.begin();
            Thread.sleep(45);
            good.end();
            commitAllowed = good.shouldCommit();
            verify(commitAllowed,
                    "45 ms event not eligible for 15 ms threshold");
            good.commit();
            after = Instant.now();

            OrderValidation rejected = new OrderValidation();
            rejected.orderId = 404;
            rejected.status = "REJECTED";
            rejected.approved = false;
            if (rejected.approved && rejected.shouldCommit()) {
                rejected.begin();
                rejected.end();
                rejected.commit();
                rejectedByBusinessRule = false;
            }
            on.stop();
            on.dump(onFile);
        }

        verify(enabledWhenRunning, "running event not enabled");
        System.out.println("active isEnabled: " + enabledWhenRunning);
        System.out.println("positive shouldCommit: " + commitAllowed);
        System.out.println("business rule skipped event: " + rejectedByBusinessRule);

        List<RecordedEvent> events = onlyOrderEvents(onFile);
        verify(events.size() == 1,
                "Expected exactly one event, got " + events.size());
        RecordedEvent event = events.get(0);

        System.out.println("recorded event count: " + events.size());
        System.out.println("correct fields: " +
                (event.getLong("orderId") == 20261107L &&
                 event.getString("status").equals("APPROVED") &&
                 event.getInt("quantity") == 3 &&
                 event.getBoolean("approved")));
        System.out.println("correct event name: " +
                event.getEventType().getName()
                        .equals("lesson.OrderValidation"));
        System.out.println("correct event label: " +
                event.getEventType().getLabel()
                        .equals("Order validation"));
        System.out.println("correct categories: " +
                event.getEventType().getCategoryNames()
                        .equals(Arrays.asList("Learning", "JFR")));
        System.out.println("duration >= 15 ms: " +
                (event.getDuration()
                        .compareTo(Duration.ofMillis(15)) >= 0));
        System.out.println("timestamps bracketed: " +
                (!event.getStartTime().isBefore(before.minusSeconds(2)) &&
                 !event.getEndTime().isAfter(after.plusSeconds(2)) &&
                 !event.getEndTime().isBefore(event.getStartTime())));
        System.out.println("times add up: " +
                Duration.between(event.getStartTime(), event.getEndTime())
                        .equals(event.getDuration()));

        EventType type = event.getEventType();
        System.out.println("transient excluded: " +
                type.getFields().stream().noneMatch(
                        f -> f.getName().equals("notRecorded")));
        System.out.println("static excluded: " +
                type.getFields().stream().noneMatch(
                        f -> f.getName().equals("staticNote")));
        System.out.println("thread name: " +
                event.getThread().getJavaName());
        System.out.println("recording file nonempty: " +
                (Files.size(onFile) > 0));
    }
}
```

### 8.2. Lệnh chạy

Linux/macOS:

```bash
mkdir -p jfr-test-output
javac --release 11 -encoding UTF-8 JfrEventValidationDemo.java
java JfrEventValidationDemo jfr-test-output
jfr summary jfr-test-output/validated.jfr
jfr print --events lesson.OrderValidation jfr-test-output/validated.jfr
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path .\jfr-test-output
javac --release 11 -encoding UTF-8 JfrEventValidationDemo.java
java JfrEventValidationDemo .\jfr-test-output
jfr summary .\jfr-test-output\validated.jfr
jfr print --events lesson.OrderValidation .\jfr-test-output\validated.jfr
```

**Đầu ra chính xác đã chạy thử (17 dòng):**

```text
disabled isEnabled: false
disabled file event count: 0
active isEnabled: true
positive shouldCommit: true
business rule skipped event: true
recorded event count: 1
correct fields: true
correct event name: true
correct event label: true
correct categories: true
duration >= 15 ms: true
timestamps bracketed: true
times add up: true
transient excluded: true
static excluded: true
thread name: main
recording file nonempty: true
```

Lệnh `jfr summary` đã nhận diện đúng **1 event `lesson.OrderValidation`**; tổng số event JVM, timestamp và file size là các con số phụ thuộc runtime và không được dùng làm expected stdout cố định.

### 8.3. Giải thích assertions

1. `disabled file event count: 0`: gọi `commit()` chưa đủ khi recording disabled.
2. `positive shouldCommit: true`: event sau begin/end vượt threshold 15 ms.
3. `business rule skipped event: true`: event `REJECTED` bị ứng dụng loại, không xuất hiện trong file.
4. `recorded event count: 1`: không mất event hợp lệ và không xuất hiện event không mong đợi.
5. `correct fields`: `orderId=20261107L`, `status="APPROVED"`, `quantity=3`, `approved=true` đều khớp.
6. `correct event name/label/categories`: metadata đúng như annotations.
7. `duration >= 15 ms` và `timestamps bracketed`: duration và thời điểm ghi đúng giai đoạn thử nghiệm, có dung sai.
8. `times add up`: duration bằng khoảng chênh lệch giữa end/start trong dữ liệu đã đọc.
9. `transient excluded` và `static excluded`: hai field bị bỏ qua đúng hợp đồng JFR.
10. `thread name: main`: chương trình chạy đồng bộ trên main thread; ứng dụng async không nên hardcode kết quả này.
11. `recording file nonempty`: file đã có dữ liệu, nhưng đây **không phải assertion duy nhất**.

Nếu muốn tránh mọi biến động do lịch chạy của OS, hãy kiểm tra bất biến **threshold** và **vùng thời gian** thay vì số milli giây cụ thể của event.


## 9. Chương trình thứ hai: âm tính do threshold quá cao

Mục 8 có negative cases disabled và business condition. Để chứng minh một event **bị lọc chỉ vì duration dưới threshold**, dùng recording **riêng biệt** với threshold một giờ, trong khi event chỉ kéo dài khoảng vài milli giây.

**Tệp `JfrThresholdFilterDemo.java`:**

```java
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.stream.Collectors;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrThresholdFilterDemo {
    @Name("lesson.ThresholdTest")
    static class Timed extends Event {
        int unit = 7;
    }

    public static void main(String[] args) throws Exception {
        Path file = Path.of(args[0], "threshold.jfr");
        boolean mayCommit;
        try (Recording r = new Recording()) {
            r.enable(Timed.class).withThreshold(Duration.ofHours(1));
            r.start();

            Timed t = new Timed();
            t.begin();
            Thread.sleep(5);
            t.end();
            mayCommit = t.shouldCommit();
            t.commit();

            r.stop();
            r.dump(file);
        }
        List<RecordedEvent> list =
                RecordingFile.readAllEvents(file).stream()
                .filter(e -> e.getEventType().getName()
                        .equals("lesson.ThresholdTest"))
                .collect(Collectors.toList());

        if (mayCommit || !list.isEmpty()) {
            throw new AssertionError("unexpected event");
        }
        System.out.println("large threshold shouldCommit: " + mayCommit);
        System.out.println("threshold event count: " + list.size());
    }
}
```

Lệnh chạy, trong thư mục nguồn và đã có `jfr-test-output`:

```bash
javac --release 11 -encoding UTF-8 JfrThresholdFilterDemo.java
java JfrThresholdFilterDemo jfr-test-output
```

**Đầu ra chính xác đã kiểm thử:**

```text
large threshold shouldCommit: false
threshold event count: 0
```

Dù `r.enable(Timed.class)` và đã gọi `t.commit()`, JFR vẫn **không ghi** vì duration không đạt ngưỡng 1 giờ. Không dùng ngưỡng quá sát khoảng `sleep` (ví dụ 5ms so 6ms) để test stable: scheduler, JVM pauses và timer resolution có thể làm test flaky.

## 10. Kiểm thử nhiều events, schema và thứ tự

Với các events có `orderId` khác nhau, kiểm tra đúng **tập ID và số lượng**, không chỉ dùng `findFirst()`. Nếu có duplicate, kiểm tra tập ID không đủ vì `Set` làm mất thông tin số lần xuất hiện.

Ví dụ snippet Java 11:

```java
Set<Long> actualIds = events.stream()
        .map(e -> e.getLong("orderId"))
        .collect(Collectors.toSet());

Set<Long> expectedIds = Set.of(10L, 20L, 30L);
if (!actualIds.equals(expectedIds) || events.size() != 3) {
    throw new AssertionError("Missing or duplicate events");
}
```

Snippet cần import `Set`, `Collectors` và khai báo `events`. Nếu requirement có thứ tự nghiệp vụ, nên dùng sequence ID được ghi rõ vào event để assert; không phụ thuộc thứ tự của **mọi JVM events** không liên quan.

### 10.1. Custom `@SettingDefinition` cho bộ lọc phức tạp

JFR hỗ trợ `@SettingDefinition` và `SettingControl` để định nghĩa custom event setting có thể cấu hình theo recording. Tuy nhiên đây là tính năng nâng cao; khi có **nhiều recording** phải hiểu cách kết hợp các giá trị setting, đặc biệt `SettingControl.combine(Set<String>)`.

Nếu mục tiêu chỉ là ghi khi đơn hàng đã được phê duyệt, điều kiện application:

```java
if (approvedByPolicy && event.shouldCommit()) {
    event.commit();
}
```

rõ ràng hơn, dễ test hơn và không tạo thêm state trong JFR settings. Chỉ sử dụng custom setting khi có nhu cầu quản trị cụ thể và đã kiểm thử đầy đủ hợp đồng giữa recordings.

## 11. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tệp .jfr tồn tại nên báo PASS | Không chứng minh có event nghiệp vụ | Lọc chính xác EventType.getName và assert count |
| Gọi commit rồi in success | commit không bảo đảm ghi | Đọc lại từ RecordingFile |
| `isEnabled()==true` nên luôn ghi | Chưa xét threshold | Dùng `shouldCommit()` sau end |
| Quên begin/end khi đo duration | Instant event có thể duration 0 | Gọi đúng timed lifecycle |
| Assert sleep 45 ms bằng duration đúng 45 | Scheduler/GC gây flaky | Assert > threshold và timestamp window |
| Kiểm tra tổng số JFR events | Lẫn các sự kiện JVM | Lọc custom event name |
| Sai tên field/getter type | Đọc lỗi hoặc giá trị không đúng | Kiểm tra metadata + value |
| Trường `List<String>` không xuất hiện | JFR không tự serialize collection | Dùng field đơn giản được hỗ trợ |
| `static`/`transient` không có | Đây là hành vi đúng của JFR | Test schema âm tính |
| Negative disabled vẫn isEnabled true | Một recording khác trong JVM đang bật | Test isolation, đóng recordings |
| Event dưới threshold vẫn được ghi vào recording khác | Các recordings có settings khác nhau | Không coi shouldCommit là sự đảm bảo cho mọi recording |
| Chỉ so tập ID, không so count | Trùng ID bị Set loại | Assert cả count và ID |
| Async task commit sau recording.stop | Event không được ghi | Chờ future/executor hoàn thành trước stop/dump |
| `getThread()==null` gây NPE | Thread metadata có thể không tồn tại | Kiểm tra null và settings |
| Dữ liệu field bị sửa sau commit | Thời điểm ghi không như mong muốn | Gán field đầy đủ trước commit |
| Đọc file nhiều GB bằng `readAllEvents` | OOM / RAM lớn | Dùng `RecordingFile` streaming |
| Ghi token/password vào event | Rò rỉ qua tệp .jfr | Omit/mask và kiểm soát retention |
| Dùng JFR thay audit log giao dịch | Có thể mất/filtered event | Sử dụng audit system có durability phù hợp |

### 11.1. Nhiều recording và isolation

`Event.isEnabled()` trả true khi **ít nhất một recording đang chạy bật event type**. `Event.shouldCommit()` cũng có thể true theo cấu hình tổng hợp dù một recording riêng đang disable hoặc đặt threshold cao hơn. Để test đúng nhánh disabled, phải tránh recording khác cùng JVM đang bật event.

Không chạy các unit tests JFR dùng chung static event class và recording ở nhiều threads/process context mà không có isolation. Với một test suite lớn, cân nhắc JVM riêng theo nhóm test và chỉ để một recording hoạt động trong các assertions nhạy cảm về enabled.

### 11.2. Không dùng JFR làm nguồn audit duy nhất

JFR là hệ thống profiling/diagnostics, có thể filtered theo event settings và giới hạn bởi lifecycle của recording, dung lượng, flush và tình huống JVM crash. Một test PASS không chứng minh event luôn được lưu bền vững trong mọi điều kiện sự cố. Audit giao dịch cần thiết kế lưu trữ chuyên dụng.

## 12. Đọc tệp lớn theo streaming

`RecordingFile.readAllEvents(...)` nạp danh sách các event và phù hợp test file nhỏ. Trong production với file lớn:

```java
long count = 0L;
try (RecordingFile input = new RecordingFile(recordingPath)) {
    while (input.hasMoreEvents()) {
        RecordedEvent event = input.readEvent();
        if ("lesson.OrderValidation"
                .equals(event.getEventType().getName())) {
            count++;
        }
    }
}
```

Snippet cần import `RecordingFile`, `RecordedEvent`, `Path` cùng biến `recordingPath`. Không giữ toàn bộ payload vào memory hoặc console nếu chỉ cần count/aggregate. Một số API streaming JFR khác được thêm ở JDK mới; code bài học giữ phạm vi **Java 11** với `RecordingFile`.

## 13. Cách đưa test vào CI

- Dùng JDK có module `jdk.jfr`; biên dịch với `javac --release 11` để tránh vô tình gọi API mới.
- Tạo thư mục output tạm có quyền ghi; đóng recording và xóa artifacts khi hoàn thành.
- Chạy riêng các negative cases disabled/threshold/business rule để tìm đúng nguyên nhân.
- Test count của **event type**, field values, schema, metadata, duration/time window và các trường bị loại.
- Khi có async tasks, chờ tasks hoàn tất trước `stop()/dump()`; không cho event commit sau khi recording đã dừng.
- Không assert exact thời gian, số event hệ thống hoặc kích thước file .jfr.
- Khi lỗi, có thể dùng `jfr summary` và `jfr print --events lesson.OrderValidation` để chẩn đoán, nhưng bảo vệ file có dữ liệu nhạy cảm.
- Nếu test framework có JUnit, chuyển `verify`/`AssertionError` thành assertions tương ứng; ví dụ ở mục 8/9 cố tình không cần thư viện test ngoài JDK.

## 14. Bài tập tự kiểm tra

**Câu 1.** Gọi `Event.commit()` là đã ghi vào file .jfr chắc chắn chưa?  
**Trả lời:** Chưa. Phải xét recording active/enabled/threshold và đọc lại file.

**Câu 2.** `isEnabled()` và `shouldCommit()` khác gì?  
**Trả lời:** isEnabled xác nhận event type được bật ở ít nhất một recording, shouldCommit còn xét duration/threshold của instance.

**Câu 3.** `@Name` có ý nghĩa gì?  
**Trả lời:** Là tên định danh event type ổn định; dùng để filter thay vì label chỉ để hiển thị.

**Câu 4.** `getStartTime()` và `getDuration()` trả cùng kiểu?  
**Trả lời:** Không, `Instant` và `Duration`.

**Câu 5.** Vì sao `Thread.sleep(45)` không đảm bảo duration đúng 45 ms?  
**Trả lời:** OS scheduling, GC, JVM runtime và clock precision ảnh hưởng.

**Câu 6.** Field `transient` có xuất hiện trong JFR metadata?  
**Trả lời:** Không, JFR bỏ qua static và transient fields.

**Câu 7.** Khi recording A disabled, recording B enabled, `isEnabled()` chắc false?  
**Trả lời:** Không, vì event type được bật ở B.

**Câu 8.** Vì sao phải lọc đúng event name khi đếm?  
**Trả lời:** Vì .jfr có thể có nhiều event hệ thống, tổng count không bằng custom event count.

**Câu 9.** Test threshold 1 giờ với event vài ms chứng minh gì?  
**Trả lời:** Event enabled nhưng không đủ duration, nên `shouldCommit=false` và không được ghi.

**Câu 10.** JFR có thay thế audit log đảm bảo mọi giao dịch?  
**Trả lời:** Không; JFR dành cho diagnostics/profiling với filtering/retention.

## 15. Tổng kết và nguồn tham khảo

- **Event** là nguồn field dữ liệu; **Recording** quyết định khi nào/loại nào được thu thập.
- **EventType** mô tả schema/label/category; **RecordedEvent** chứa giá trị fields, timestamp và duration.
- **RecordingFile** là nơi đọc kết quả từ .jfr để assert; đừng báo PASS chỉ vì đã gọi commit.
- **`begin/end`** đo timed event, **`shouldCommit`** xét enabled/threshold, **`commit`** gửi dữ liệu đủ điều kiện.
- **Kiểm thử âm tính riêng** cho disabled, dưới threshold và business condition để tránh giả kết luận.
- **Không assert thời gian chính xác** bằng sleep hay cứng số event JVM. Dùng cửa sổ thời gian và các bất biến.
- **Hai ví dụ Java 11 đã chạy thật:** 17 dòng cho `JfrEventValidationDemo` và 2 dòng cho `JfrThresholdFilterDemo`.

**Tài liệu chính thức còn áp dụng:**

1. [Oracle Java 11 — Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html).
2. [Oracle Java 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html).
3. [Oracle Java 11 — EventSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html).
4. [Oracle Java 11 — EventType](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventType.html).
5. [Oracle Java 11 — RecordedEvent](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html).
6. [Oracle Java 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
7. [Oracle Java 11 — jdk.jfr package](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
8. [Oracle Java 26 — Event API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Event.html).
9. [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328).