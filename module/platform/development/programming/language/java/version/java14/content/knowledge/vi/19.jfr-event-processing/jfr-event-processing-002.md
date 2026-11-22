# Đọc thời điểm bắt đầu, thời lượng và thông tin luồng của sự kiện JFR

> **Ngữ cảnh:** Java 14 → *Xử lý sự kiện JFR* → **Đọc thời điểm bắt đầu, thời lượng và thông tin luồng**. JFR Event Streaming API (`RecordingStream`) xuất hiện ở Java 14 (JEP 349); các lớp `RecordedEvent`, `RecordedThread` và `RecordingFile` vẫn thuộc API `jdk.jfr.consumer` được hỗ trợ trong JDK hiện đại. Bài dùng **Java 17+** và phân biệt rõ một số khả năng chỉ có từ **Java 21+**. Không cần `--enable-preview` hay API legacy.

## 1. Tại sao cần ba nhóm thông tin này?

Khi phân tích một sự kiện Java Flight Recorder (JFR), ta thường cần biết:

1. **Sự kiện bắt đầu lúc nào?** Dùng `RecordedEvent.getStartTime()` để nhận `Instant`.
2. **Sự kiện kéo dài bao lâu, kết thúc khi nào?** Dùng `getDuration()` để nhận `Duration` và `getEndTime()` để nhận `Instant`.
3. **Luồng nào gắn với sự kiện?** Dùng `getThread()` để nhận `RecordedThread`, nếu thông tin luồng được ghi; từ đó đọc tên và ID của luồng.

Ba nhóm thông tin phục vụ các câu hỏi thực tế:

- Một tác vụ mất bao lâu; có vượt ngưỡng theo dõi không?
- Sự kiện phát sinh trước hay sau một mốc thời gian?
- Những sự kiện chậm xuất hiện trên các luồng Java nào?
- Là sự kiện của luồng tạo ra công việc hay chỉ là **luồng đọc JFR stream**?
- Event được ghi lúc nào so với lúc consumer callback nhận được nó?

**Điểm cốt lõi:** `RecordedEvent` là **dữ liệu sự kiện đã được ghi lại**. Thời gian và thread trong đó thường mô tả **sự kiện tại JVM**, không mô tả thời gian callback Java hiện tại vừa được gọi.

## 2. Bảng API chuẩn hiện hành

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `event.getStartTime()` | `java.time.Instant` | Thời điểm bắt đầu sự kiện |
| `event.getEndTime()` | `java.time.Instant` | Thời điểm kết thúc sự kiện |
| `event.getDuration()` | `java.time.Duration` | Thời lượng sự kiện, với độ phân giải tới nanosecond |
| `event.getThread()` | `RecordedThread` hoặc `null` | Luồng mà sự kiện được commit từ đó, **nếu có ghi** |
| `event.getEventType().getName()` | `String` | Tên loại sự kiện, ví dụ `jdk.ThreadSleep` hoặc `demo.TimedTask` |
| `event.getStackTrace()` | `RecordedStackTrace` hoặc `null` | Stack trace nếu event có thu thập stack trace |
| `event.getString("fieldName")` | `String` hoặc `null` | Trường dữ liệu riêng của loại event nếu đúng tên/kiểu |
| `thread.getJavaName()` | `String` hoặc `null` | Tên Java thread được ghi |
| `thread.getJavaThreadId()` | `long` | ID của Java thread, hoặc `-1` nếu không có Java thread |
| `thread.getId()` | `long` | ID JFR của recorded thread; không đồng nhất với Java/OS thread ID |
| `thread.getOSName()` | `String` hoặc `null` | Tên OS thread nếu có |
| `thread.getOSThreadId()` | `long` | ID OS thread, hoặc `-1` nếu không có |
| `thread.getThreadGroup()` | `RecordedThreadGroup` hoặc `null` | Nhóm luồng nếu có thông tin |

Các phương thức liệt kê ở trên có trong **JDK 17**. Riêng `RecordedThread.isVirtual()` chỉ có từ **Java 21**, nên **không gọi nó** trong file biên dịch `--release 17`. Nếu dự án dùng JDK 21+, có thể phân biệt virtual thread theo API này, nhưng không nên suy ra virtual/platform chỉ từ `getOSThreadId()`.

Trong JFR, tên event và danh sách field có thể khác nhau giữa event types và phiên bản JDK. Hãy dùng API có kiểu trả về rõ ràng như `getStartTime()`, `getDuration()`, `getThread()` cho các metadata chung; đọc những field riêng chỉ sau khi kiểm tra schema của loại event.

## 3. Đọc thời điểm: `Instant` khác độ dài `Duration`

### 3.1. Thời điểm bắt đầu và kết thúc

~~~java
Instant begin = event.getStartTime();
Instant end = event.getEndTime();
~~~

Đây là **đoạn đặt trong handler hoặc phương thức nhận `RecordedEvent event`**, cần import `java.time.Instant`. Theo Javadoc, `getStartTime()` và `getEndTime()` trả `Instant` không null. Với **instant event** (sự kiện tức thời), hai giá trị này bằng nhau.

`Instant` là **mốc thời gian trên UTC timeline**, không mặc định là giờ địa phương của JVM, console hay hệ thống người dùng. Để hiển thị theo múi giờ:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
String displayed = event.getStartTime().atZone(zone).toString();
~~~

Đoạn code trên cần import `java.time.ZoneId`. Việc đổi múi giờ chỉ thay **cách biểu diễn** một mốc thời gian; nó không làm thay đổi thời điểm JFR đã ghi. Dùng `Instant` cho lưu trữ, so sánh và liên hệ sự kiện; chọn múi giờ rõ ràng khi hiển thị báo cáo.

### 3.2. Thời lượng

~~~java
Duration duration = event.getDuration();
long millis = duration.toMillis();
long nanos = duration.toNanos();
~~~

Đây cũng là **đoạn code trong phương thức**, cần import `java.time.Duration`. `getDuration()` trả `Duration` không null; `toMillis()` chuyển sang mili giây bằng cách loại bỏ phần nhỏ hơn 1 ms. Một event kéo dài 500 microsecond có thể trả `toMillis() == 0` dù **không phải** có thời lượng bằng 0.

`Duration.toNanos()` có thể ném `ArithmeticException` nếu thời lượng quá lớn để biểu diễn bằng một `long`; hãy giữ kiểu `Duration` khi không thật sự cần số nguyên nanosecond. `Duration.toString()` hiển thị định dạng ISO-8601 phù hợp để debug, ví dụ `PT0.08S`, nhưng không cam kết event sẽ kéo dài đúng 80 ms chỉ vì chương trình gọi `Thread.sleep(80)`.

Nếu muốn đo sự kiện theo đơn vị milliseconds cho dashboard:

~~~java
double milliseconds =
        event.getDuration().toNanos() / 1_000_000.0;
~~~

Cách này hợp lý với **những duration nhỏ có giới hạn** (như ví dụ JFR đo tác vụ); với duration có thể rất lớn, hãy xử lý khả năng tràn `long` trước khi gọi `toNanos()`.

### 3.3. Những điều `getDuration()` KHÔNG đo

- Không phải thời gian `onEvent(...)` handler mất để chạy.
- Không phải thời gian từ lúc `commit()` đến khi stream callback nhận được event.
- Không phải tuổi của JVM hay thời gian kể từ khi `RecordingStream.start()` được gọi.
- Không bắt buộc bằng thời gian từ một phép `System.currentTimeMillis()` khác ở phía consumer.

Đó là **thời lượng do JFR ghi cho sự kiện**. Với sự kiện custom có `begin()` và `end()`, thời lượng tương ứng khoảng hoạt động mà producer đánh dấu; với một instant event, theo Javadoc `getStartTime()` bằng `getEndTime()` và duration bằng 0.

**Giới hạn độ chính xác:** số liệu phụ thuộc cách event được tạo, timestamp resolution, cấu hình ngưỡng và lịch chạy JVM. Không viết unit test yêu cầu một tác vụ có `Thread.sleep(80)` phải có `duration.toMillis() == 80`.

## 4. Đọc thông tin luồng: `RecordedThread` không phải `Thread` đang chạy

~~~java
RecordedThread recordedThread = event.getThread();

if (recordedThread != null) {
    String javaName = recordedThread.getJavaName();
    long javaId = recordedThread.getJavaThreadId();
    long jfrId = recordedThread.getId();
}
~~~

Đây là **đoạn trong handler**, cần import `jdk.jfr.consumer.RecordedThread`.

`RecordedEvent.getThread()` trả luồng **từ đó sự kiện được commit**, hoặc `null` nếu không ghi thông tin luồng. Nó **không** có cùng kiểu với `java.lang.Thread` và không có nghĩa “luồng hiện tại đang chạy handler”.

### 4.1. Phân biệt các ID

- `getJavaThreadId()`: Java thread ID, khớp với khái niệm ID của `java.lang.Thread`; **-1** nếu không tồn tại Java thread tương ứng.
- `getId()`: định danh JFR của recorded thread, khác hệ ID Java và khác OS thread ID; không tự thay thế các giá trị này cho nhau.
- `getOSThreadId()`: OS thread ID, **-1** nếu không tồn tại/không được ghi. Với virtual threads hoặc thread đặc biệt, không được mặc định luôn có OS thread ID 1:1.

Để phân tích log hoặc liên kết các event trong **cùng JVM/lần ghi**, nên lưu ID cùng tên event, timestamp và ngữ cảnh. **Tên thread có thể đổi, có thể trùng**, và không phải định danh duy nhất. ID thread không phải global ID giữa nhiều JVM hoặc giữa các lần khởi động.

### 4.2. Xử lý nullable fields

~~~java
RecordedThread thread = event.getThread();

String displayName = thread == null
        ? "(thread not recorded)"
        : thread.getJavaName();

if (displayName == null) {
    displayName = "(Java name unavailable)";
}
~~~

**Không** viết `event.getThread().getJavaName()` khi không biết event type chắc chắn ghi thread, vì `getThread()` có thể trả null. `getOSName()` và `getThreadGroup()` cũng có thể null; `getJavaThreadId()` và `getOSThreadId()` có thể là `-1`.

Đừng dùng tên thread như giá trị bắt buộc trong mọi event, cũng đừng coi null thread metadata là lỗi mặc định của JFR. Có sự kiện JVM và dữ liệu hệ thống không gắn với một Java thread thông thường.

### 4.3. Không nhầm luồng commit event với luồng consumer

Khi dùng `RecordingStream.onEvent(...)`:

- **Producer** là luồng mà sự kiện JFR xuất hiện/được commit; `event.getThread()` mô tả thông tin đó nếu được ghi.
- **Consumer** là luồng đang thực thi callback Java. `Thread.currentThread()` **trong handler** chỉ cho biết consumer callback thread.
- `RecordingStream.start()` xử lý action trên **luồng gọi `start()`**; `startAsync()` xử lý action trên một luồng riêng.
- Event có thể được giao sau khi một batch được flush. Không giả định `event.commit()` làm callback chạy đồng bộ tức thì.

Ví dụ, một worker mang tên `jfr-worker` có thể phát event, nhưng thread chạy `onEvent` là `main` nếu `main` đã gọi `stream.start()`. Cả hai tên thread **đều đúng**, nhưng trả lời cho **hai câu hỏi khác nhau**.

## 5. Chương trình chạy được: ghi event và đọc metadata từ file JFR

Để kết quả minh họa ổn định, ví dụ tạo một **sự kiện custom có tên cố định**, ghi bằng `Recording`, dừng ghi, rồi đọc bản ghi bằng `RecordingFile.readAllEvents(...)`. Các giá trị timestamp, duration thực tế và thread ID khác nhau giữa lần chạy, nên chương trình chỉ in **các thuộc tính có thể kiểm chứng**.

**File: `JfrEventFieldsDemo.java`**

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedThread;
import jdk.jfr.consumer.RecordingFile;

public class JfrEventFieldsDemo {

    @Name("demo.TimedTask")
    public static class TimedTask extends Event {
        public String operation;
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("jfr-fields-", ".jfr");

        try {
            try (Recording recording = new Recording()) {
                recording.enable(TimedTask.class).withoutThreshold();
                recording.start();

                Thread worker = new Thread(() -> {
                    TimedTask event = new TimedTask();
                    event.operation = "load";

                    event.begin();
                    try {
                        Thread.sleep(80);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }
                    event.end();

                    event.commit();
                }, "jfr-worker");

                worker.start();
                worker.join();

                recording.stop();
                recording.dump(file);
            }

            List<RecordedEvent> events =
                    RecordingFile.readAllEvents(file);

            RecordedEvent selected = events.stream()
                    .filter(event -> "demo.TimedTask"
                            .equals(event.getEventType().getName()))
                    .findFirst()
                    .orElseThrow();

            RecordedThread thread = selected.getThread();

            System.out.println(
                    "type=" + selected.getEventType().getName());
            System.out.println(
                    "operation=" + selected.getString("operation"));
            System.out.println(
                    "startPresent=" + (selected.getStartTime() != null));
            System.out.println(
                    "endPresent=" + (selected.getEndTime() != null));
            System.out.println(
                    "durationPositive=" + selected.getDuration().isPositive());
            System.out.println(
                    "ordered=" + !selected.getEndTime()
                            .isBefore(selected.getStartTime()));
            System.out.println(
                    "thread=" + (thread == null
                            ? "missing" : thread.getJavaName()));
            System.out.println(
                    "threadIdPositive=" + (thread != null
                            && thread.getJavaThreadId() > 0));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+ hỗ trợ mô-đun `jdk.jfr`:

~~~bash
javac --release 17 -encoding UTF-8 JfrEventFieldsDemo.java
java JfrEventFieldsDemo
~~~

**Stdout trong lần kiểm thử JDK 24:**

~~~text
type=demo.TimedTask
operation=load
startPresent=true
endPresent=true
durationPositive=true
ordered=true
thread=jfr-worker
threadIdPositive=true
~~~

### Đọc code theo từng giai đoạn

1. `@Name("demo.TimedTask")` tạo một tên event rõ ràng để lọc, tránh phụ thuộc tên class lồng nhau.
2. `recording.enable(TimedTask.class).withoutThreshold()` bảo đảm custom event ngắn không bị loại vì ngưỡng duration. Không mặc định mọi event type đều có cùng thiết lập ghi.
3. Worker có tên `jfr-worker` gọi `event.begin()`, thực hiện tác vụ mô phỏng rồi `event.end()` và `event.commit()`. Timestamps và duration được ghi vào event.
4. `worker.join()` bảo đảm worker đã chạy xong trước khi `recording.stop()` và `recording.dump(file)`. Nhờ đó, custom event có cơ hội được ghi vào file khi dừng.
5. `RecordingFile.readAllEvents(file)` đọc mọi event từ file, không chỉ `demo.TimedTask`; phải **lọc theo tên loại event** trước khi lấy field riêng `operation`.
6. `selected.getStartTime()`, `getEndTime()` và `getDuration()` trả các kiểu dữ liệu thời gian; ví dụ in boolean thay vì một thời điểm và duration cứng.
7. `getThread().getJavaName()` cho biết worker đã commit event, không phải luồng đọc file. ID được kiểm tra chỉ để chứng minh có Java thread ID hợp lệ.
8. File tạm được xóa trong `finally`, kể cả khi có lỗi; `Recording` được đóng bằng `try-with-resources`.

**Lưu ý về môi trường:** Ví dụ cần một JDK phân phối có Flight Recorder hoạt động và quyền tạo file tạm. Độ trễ JVM, tải hệ thống hoặc khác biệt cấu hình khiến **thời gian chính xác không thể được cố định**; nếu JFR bị vô hiệu hóa hoặc không ghi event, chương trình sẽ ném lỗi ở `orElseThrow()`, thay vì âm thầm báo thành công.

Trong sản phẩm thật, đọc toàn bộ file bằng `readAllEvents` có thể tiêu tốn bộ nhớ nếu file lớn. Cân nhắc dùng `RecordingFile` theo kiểu lặp `hasMoreEvents()` và `readEvent()`, hoặc xử lý streaming để không tải toàn bộ file vào một danh sách.

## 6. Tương đương trong `RecordingStream.onEvent(...)`

Từ Java 14, `RecordingStream` cho phép đọc sự kiện đang được phát trong **JVM hiện tại**. Lời gọi callback nhận một `RecordedEvent`, vì vậy **cách đọc các metadata thời gian/thread là giống nhau**:

~~~java
try (var stream = new jdk.jfr.consumer.RecordingStream()) {
    stream.enable("jdk.ThreadSleep").withoutThreshold();

    stream.onEvent("jdk.ThreadSleep", event -> {
        var start = event.getStartTime();
        var duration = event.getDuration();
        var thread = event.getThread();

        String name = thread == null
                ? "(unknown)" : thread.getJavaName();

        System.out.println(
                start + " | " + duration + " | " + name);
    });

    stream.setEndTime(
            java.time.Instant.now().plusSeconds(3));

    stream.start();
}
~~~

Đây là **đoạn minh họa đặt trong một phương thức**, không phải file độc lập. Nó dùng một event JDK thông dụng (`jdk.ThreadSleep`), nhưng **không cam kết chắc chắn in ra sự kiện** nếu JVM không có sleep event phù hợp hoặc chưa kịp flush trước khi stream đóng. Bản thân `start()` **chặn luồng gọi** trong thời gian xử lý, nên cần `setEndTime` hoặc một cách đóng từ luồng khác.

Phân biệt với `startAsync()`:

~~~java
stream.startAsync(); // onEvent chạy trên luồng stream riêng.
doUsefulWork();      // Phương thức do ứng dụng định nghĩa.
// Sau khi hoàn tất hoạt động đã định, hãy đóng stream có chủ đích.
stream.close();
~~~

Đây chỉ là **mẫu cấu trúc** sau khi đã tạo/cấu hình stream. Không gọi `startAsync()` rồi ngay lập tức thoát `try-with-resources` nếu mục đích là nhận sự kiện, vì stream có thể bị đóng trước khi batch được xử lý.

### Ghi nhận event và thời điểm callback nhận event khác nhau

~~~java
stream.onEvent("jdk.ThreadSleep", event -> {
    java.time.Instant eventStart = event.getStartTime();
    java.time.Instant receivedAt = java.time.Instant.now();

    // Không thay eventStart bằng receivedAt.
    // Chênh lệch gồm thời gian sự kiện và độ trễ xử lý/flush.
});
~~~

`receivedAt` chỉ là thời điểm **consumer thực hiện callback**. Trong JFR Event Streaming, việc giao event có thể qua bộ đệm/flush nên không được dùng `receivedAt` làm `getStartTime()`. Tương tự, `event.getDuration()` **không phải** thời lượng xử lý callback.

## 7. Các chi tiết về timestamp và duration cần lưu ý

### 7.1. Instant event khác duration event

- **Instant event** (mốc tức thời): theo Javadoc, `getStartTime()` = `getEndTime()`; `getDuration()` tương ứng `Duration.ZERO`.
- **Duration event**: có khoảng thời gian từ lúc bắt đầu đến lúc kết thúc, ví dụ custom event dùng `begin()`/`end()`. Đừng giả định mọi event đều có duration dương; nhiều sự kiện chỉ đánh dấu một mốc.
- **Ngưỡng JFR:** một số event có threshold; event có duration ngắn có thể không được ghi nếu không vượt ngưỡng đã cấu hình. Với custom event trong ví dụ, `withoutThreshold()` giúp ghi cả event ngắn.
- **Nanosecond vs millisecond:** `Duration` cho phép biểu diễn nanosecond; chuyển `toMillis()` có thể thành 0 đối với event rất ngắn. Đây không nhất thiết là lỗi.
- **Duration quá lớn:** nếu chuyển sang integer `toNanos()`, cân nhắc overflow; giữ `Duration` hoặc dùng đơn vị phù hợp với phạm vi dữ liệu.

### 7.2. Thời gian event không phải thứ tự callback tuyệt đối

Có thể ghi nhiều event trên các thread khác nhau, rồi consumer nhận qua các batch. Khi phân tích, nên dùng timestamp event để xếp thứ tự/tương quan, không chỉ thứ tự các dòng log in ra từ callback.

Không giả định một event luôn được giao ngay khi producer gọi `commit()`. Không giả định hai sự kiện có cùng timestamp nhất thiết phát sinh trên cùng thread. Nếu cần đồng bộ logic nghiệp vụ, JFR **không thay thế message queue hay cơ chế transaction**.

### 7.3. Không tính thủ công mọi duration từ đồng hồ khác

`event.getEndTime().toEpochMilli() - event.getStartTime().toEpochMilli()` có thể mất phần nhỏ hơn một millisecond; kết quả 0 không nói lên event không có thời lượng. Để đọc duration, dùng **`event.getDuration()`** là API chủ đích.

Nếu cần hiển thị theo giờ địa phương, chuyển `Instant` sang `ZonedDateTime` bằng một `ZoneId` rõ ràng. Tránh nối các chuỗi thời gian không có múi giờ rồi so sánh bằng cách sort từ vựng.

## 8. Metadata luồng: sai lầm thường gặp

### 8.1. `getThread()` và `getThread("fieldName")` là hai API khác nhau

`RecordedEvent` kế thừa từ `RecordedObject` nên cũng có dạng truy cập **một field cụ thể**:

~~~java
RecordedThread eventThread = event.getThread();

if (event.hasField("someThreadField")) {
    RecordedThread related =
            event.getThread("someThreadField");
}
~~~

Đây là **đoạn minh họa**, với `someThreadField` chỉ là **tên ví dụ**, không phải trường chung có mặt trong mọi JFR event. `event.getThread()` trả metadata **event/commit thread**; `event.getThread(String)` truy vấn **một field chứa Thread** trong schema của loại event và có thể ném `IllegalArgumentException` nếu trường không tồn tại hoặc sai kiểu.

**Cách làm đúng:** chỉ gọi `getThread("fieldName")` khi bạn đã biết schema của event type (ví dụ từ `event.getFields()`, `getEventType()` hoặc tài liệu JDK tương ứng). `hasField(...)` chỉ xác nhận tên có tồn tại, **không tự bảo đảm kiểu field là Thread**.

### 8.2. ID JFR khác Java thread ID và OS thread ID

~~~java
RecordedThread thread = event.getThread();

if (thread != null) {
    long jfrId = thread.getId();
    long javaId = thread.getJavaThreadId();
    long osId = thread.getOSThreadId();

    String javaName = thread.getJavaName();
    String osName = thread.getOSName();
}
~~~

Đây là **đoạn minh họa trong method**. Không coi ba ID là giống nhau, không dùng tên thread làm khóa duy nhất, không nghĩ thiếu OS ID có nghĩa JVM bị lỗi. Đối với event không ghi thread, `getThread()` có thể null, nên phải kiểm tra.

**Virtual threads:** từ **Java 21**, `RecordedThread.isVirtual()` cho biết đó có phải virtual thread không. Virtual thread không tương đương một OS thread riêng; đừng suy ra sự tồn tại của `getOSThreadId()` với mô hình 1:1. Nếu bài biên dịch bằng `--release 17`, không gọi `isVirtual()` vì phương thức đó chưa có trong API Java 17.

### 8.3. Thread name có thể thay đổi và không phải ID bền vững

Tên Java thread là thông tin tốt để debug, nhưng có thể trùng hoặc thay đổi do ứng dụng đặt lại. Khi gộp event theo thread, nên dùng định danh thread trong **phạm vi một recording/JVM**, cùng event type và timestamp phù hợp. Không dùng `getJavaName()` làm ID toàn cục giữa nhiều máy hoặc phiên JVM.

### 8.4. Stack trace không nhất thiết có mặt

`event.getStackTrace()` có thể null, vì một số event không thu thập stack trace hoặc cấu hình không bật. Nếu cần call stack, hãy bật/cấu hình stack trace đối với event hỗ trợ và xử lý trường hợp không có. **Không** suy luận thread name hay duration từ một chuỗi stack trace tự render.

## 9. Bảng đối chiếu cách đọc với mục tiêu phân tích

| Câu hỏi phân tích | API chính | Cẩn trọng |
| --- | --- | --- |
| Sự kiện bắt đầu lúc nào? | `getStartTime()` | Trả `Instant`, múi giờ khi trình bày phải rõ |
| Sự kiện kết thúc lúc nào? | `getEndTime()` | Instant event có end bằng start |
| Event chạy trong bao lâu? | `getDuration()` | Không phải thời gian consumer callback; tránh mất nano khi `toMillis` |
| Event thuộc loại gì? | `getEventType().getName()` | Phải biết event type trước khi truy vấn các field riêng |
| Luồng nào đã commit event? | `getThread()` | Có thể null; khác `Thread.currentThread()` của consumer |
| Tên Java thread là gì? | `RecordedThread.getJavaName()` | Có thể null/trùng/đổi tên |
| ID Java thread? | `getJavaThreadId()` | `-1` nếu không phải Java thread |
| ID OS thread? | `getOSThreadId()` | `-1` nếu không tồn tại/không có thông tin |
| ID JFR thread? | `getId()` | Không đồng nhất với Java/OS ID; gắn phạm vi JVM |
| Là virtual thread? | `isVirtual()` (Java 21+) | Không có trong API Java 17 |
| Có call stack? | `getStackTrace()` | Có thể null; phụ thuộc event/configuration |
| Thời điểm callback nhận event? | `Instant.now()` trong callback | Đó là thời điểm consumer, không phải thời gian event |

## 10. Các lỗi thực hành và cách sửa

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi `getDuration()` là thời gian xử lý callback | Đánh giá sai độ trễ giám sát | Dùng thời gian do callback tự đo nếu cần, tách với thời lượng event |
| In `Instant.now()` rồi gọi đó là event start | Trộn event time và receive time | Dùng `getStartTime()` |
| In `getDuration().toMillis() == 0` rồi kết luận event không có thời lượng | Mất phần dưới mili giây | Giữ `Duration`/dùng nano khi phù hợp |
| Gọi `event.getThread().getJavaName()` không kiểm tra null | Có thể `NullPointerException` | Kiểm tra `getThread() != null` |
| Dùng `Thread.currentThread().getName()` trong `onEvent` để gán producer | Đó là thread chạy callback | Dùng `event.getThread()` |
| Coi `getId()`, `getJavaThreadId()` và `getOSThreadId()` là cùng một số | Correlation sai | Lưu đúng tên và ý nghĩa từng ID |
| Dùng `getJavaName()` làm khóa duy nhất | Tên trùng/đổi | Ưu tiên ID theo phạm vi recording/JVM |
| Gọi `RecordedThread.isVirtual()` trong mã `--release 17` | Không biên dịch | Chỉ gọi với Java 21+ hoặc thiết kế mã tương thích |
| Gọi `getThread("someField")` cho mọi loại event | Có thể field không có/sai type | Kiểm tra schema event và field descriptor |
| Giả định callback luôn nhận đủ event đã commit ngay lập tức | Sai vì batch/flush/threshold | Chọn cấu hình đúng, theo dõi lifecycle và lỗi |
| Test timestamp bằng một số epoch cố định | Không ổn định theo lần chạy | Test sự hiện diện, thứ tự và điều kiện định tính |
| Đọc toàn bộ file JFR rất lớn bằng `readAllEvents` | Chiếm RAM đáng kể | Dùng API đọc tuần tự hoặc streaming |
| Gọi `getStackTrace()` rồi dereference ngay | Có thể NPE | Kiểm tra null và cấu hình event |

## 11. Checklist xử lý một `RecordedEvent` đúng cách

- [ ] Xác định **event type** bằng `getEventType().getName()` trước khi xử lý field riêng.
- [ ] Dùng `getStartTime()/getEndTime()` cho các mốc thời gian, `getDuration()` cho độ dài.
- [ ] Biểu diễn thời gian bằng `Instant`/`Duration`; không giả định milliseconds là đơn vị gốc.
- [ ] Dùng timezone rõ ràng khi đưa lên UI hoặc báo cáo.
- [ ] Không nhầm callback receipt time với event start/end.
- [ ] Lấy `RecordedThread` bằng `getThread()` và **xử lý null**.
- [ ] Phân biệt tên, Java thread ID, JFR thread ID và OS thread ID.
- [ ] Không nhầm producer thread với `Thread.currentThread()` trong callback.
- [ ] Không dùng API Java 21+ trong mã cần biên dịch `--release 17`.
- [ ] Không cho rằng mọi field tùy biến đều tồn tại trên mọi event type.
- [ ] Không cố định số event, timestamp hoặc duration trong test JFR.
- [ ] Với dữ liệu lớn, chọn đọc tuần tự/streaming và chỉ giữ metadata cần thiết.
- [ ] Thiết kế quyền truy cập file, nơi ghi bản ghi, tài nguyên JFR và cleanup thích hợp.

## 12. Bài tập tự luyện

1. Chạy `JfrEventFieldsDemo`. Thay `Thread.sleep(80)` bằng `Thread.sleep(150)` và so sánh duration thực tế bằng `getDuration().toMillis()`. Vì sao không nên assert chính xác `150`?
2. Đổi tên worker thành `"billing-jfr-worker"` và xác minh `getThread().getJavaName()`. So sánh với `Thread.currentThread().getName()` khi đọc file.
3. Thêm một event instant bằng `new TimedTask().commit()` (điền `operation` trước), lọc đúng event và kiểm tra `getStartTime().equals(getEndTime())` và `Duration.ZERO`.
4. In `start.atZone(ZoneId.of("UTC"))` và `start.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))`; tại sao kết quả hiển thị khác nhưng là cùng một `Instant`?
5. In `getJavaThreadId()`, `getId()`, `getOSThreadId()` cho cùng recorded event. Có nên giả định ba số bằng nhau giữa JDK/platform không?
6. Viết `RecordingStream.onEvent("jdk.ThreadSleep", e -> ...)` in start, duration và thread name khi có event; cấu hình một cơ chế dừng để tránh chặn vô hạn. Giải thích vì sao event count có thể khác nhau.
7. Viết guard xử lý `event.getThread() == null` và `thread.getJavaName() == null` theo một quy tắc hiển thị rõ ràng.
8. Dùng `hasField("someThreadField")` rồi xem `getFields()` để biết field có kiểu Thread hay không trước khi gọi `getThread("someThreadField")`.
9. Chạy trên JDK 21+ và thử `RecordedThread.isVirtual()` với virtual thread. Sau đó thử `javac --release 17` để hiểu sự khác biệt của API.
10. Từ một file JFR lớn, viết vòng lặp với `RecordingFile.hasMoreEvents()` và `readEvent()`, chỉ lưu thời gian/thread cho loại sự kiện quan tâm.

## 13. Tài liệu chuẩn để đối chiếu

- [Oracle Java SE 25 – RecordedEvent](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): `getStartTime`, `getEndTime`, `getDuration`, `getThread`, `getEventType` và ngữ nghĩa.
- [Oracle Java SE 17 – RecordedEvent](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): xác nhận API có thể dùng trong chương trình `--release 17`.
- [Oracle Java SE 17 – RecordedThread](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedThread.html): ID, Java/OS names, null và ý nghĩa từng trường.
- [Oracle Java SE 25 – RecordedThread](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedThread.html): `isVirtual()` và hành vi cập nhật từ Java 21+.
- [Oracle Java SE 25 – RecordingStream](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): xử lý live events.
- [Oracle Java SE 25 – RecordingFile](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc events từ bản ghi.
- [OpenJDK JEP 349 – JFR Event Streaming](https://openjdk.org/jeps/349): streaming JFR được bổ sung trong Java 14.

**Ghi nhớ:** `RecordedEvent.getStartTime()` và `getEndTime()` cho các mốc `Instant`; `getDuration()` cho `Duration` của **sự kiện**, không phải callback. `getThread()` cung cấp **RecordedThread của luồng commit sự kiện** nếu có, khác luồng đang thực thi consumer callback. Đọc các giá trị bằng API có kiểu rõ ràng, kiểm tra trường hợp không có metadata và bảo đảm code chỉ gọi những phương thức có ở phiên bản JDK đang hỗ trợ.