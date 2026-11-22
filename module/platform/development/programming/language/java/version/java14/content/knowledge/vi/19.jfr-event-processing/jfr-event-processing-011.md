# Theo dõi sự kiện tự định nghĩa bằng cùng cơ chế streaming trong Java JFR

## 1. Mục tiêu: custom event cũng đi qua luồng JFR như sự kiện của JDK

**Java Flight Recorder (JFR)** cung cấp các sự kiện JVM/JDK như `jdk.CPULoad`, `jdk.GarbageCollection`, `jdk.ThreadSleep` và cũng cho phép ứng dụng **tự định nghĩa loại sự kiện mới**. Một custom event không đòi hỏi một “hệ thống streaming khác”: khi được **bật trong recording** và được **commit**, nó có thể được tiêu thụ bằng chính API `jdk.jfr.consumer.EventStream`, sử dụng cùng cách đăng ký callback `onEvent(...)` như sự kiện JDK.

Ví dụ về ý tưởng:

~~~java
// Event có tên "app.BatchFinished" được ghi bởi code ứng dụng.
stream.onEvent("app.BatchFinished", event -> {
    System.out.println(event.getInt("itemCount"));
});
~~~

Callback nhận một `RecordedEvent`, không phải object custom event gốc. Giá trị được đọc bằng các phương thức như `getString("stage")`, `getInt("itemCount")` hoặc `getDuration()` tùy schema.

Phân biệt rõ **ba vai trò**:

1. **Producer:** mã ứng dụng tạo `Event`, gán các trường và gọi `commit()`.
2. **Recording/configuration:** JFR xác định event type có được thu thập không, threshold bao nhiêu, có stack trace hay không, giữ dữ liệu bao lâu.
3. **Consumer:** `RecordingStream` hoặc `EventStream` nhận sự kiện đã được ghi/flush rồi đưa vào callback qua `onEvent`.

Để nhận được sự kiện, **cả ba** phần phải đúng. Chỉ có class kế thừa `Event` nhưng không có recording enable, hoặc có recording nhưng không `commit()`, đều không tạo ra event cho stream tiêu thụ.

`EventStream` và `RecordingStream` được giới thiệu trong **Java 14** (JEP 349). Chúng tiếp tục được hỗ trợ trên Java hiện nay. Các ví dụ bài này nhắm **Java 17+**, không dùng preview API hay cách cấu hình JFR đã lỗi thời.

## 2. Định nghĩa một custom event đúng kiểu

Ví dụ ứng dụng xử lý các lô dữ liệu và muốn ghi một event khi xử lý xong:

~~~java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.StackTrace;

@Name("app.BatchFinished")
@Label("Batch Finished")
@Category({"Application", "Processing"})
@StackTrace(false)
class BatchFinished extends Event {
    @Label("Stage")
    String stage;

    @Label("Item Count")
    int itemCount;
}
~~~

Đây là **mảnh khai báo event**, chưa bao gồm `main`. Chương trình hoàn chỉnh ở mục 6 dùng dạng class lồng để dễ biên dịch.

Giải thích:

- **`extends jdk.jfr.Event`:** xác định loại event mà JFR có thể ghi nhận.
- **`@Name("app.BatchFinished")`:** đặt *tên ổn định dùng để định danh event type*. Cùng tên đó được đưa vào `onEvent("app.BatchFinished", ...)`.
- **`@Label` và `@Category`:** cung cấp metadata dễ đọc cho công cụ JFR/JMC; không làm event tự ghi hay tự bật.
- **Các instance fields:** là payload của event. `String stage` và `int itemCount` đều thuộc các kiểu được JFR hỗ trợ.
- **`@StackTrace(false)`:** đặt mặc định không ghi stack trace cho event này; hữu ích khi không cần đường gọi và muốn giảm dữ liệu/chi phí.
- **Không có constructor đặc biệt bắt buộc:** có thể tạo `new BatchFinished()`, gán field rồi `commit()`.

Tên event nên được tổ chức với namespace theo domain ứng dụng, chẳng hạn `com.example.inventory.BatchFinished`, để tránh vô tình trùng với tên built-in `jdk.*` hoặc custom events của thư viện khác. Một bản ghi có thể chứa nhiều event types từ nhiều class loader.

### Những kiểu field JFR hỗ trợ

Theo API `jdk.jfr.Event`, event fields phổ biến là các kiểu primitive: `boolean`, `char`, `byte`, `short`, `int`, `long`, `float`, `double`, và reference types `String`, `Thread`, `Class`.

**Không** mặc định ghi được một object tùy ý bằng cách khai báo:

~~~java
class InvalidPayload extends Event {
    java.util.List<String> items; // Không là trường event hợp lệ.
    int[] values;                 // Mảng không được ghi như event field.
}
~~~

Đây là **ví dụ phản diện về thiết kế payload**: các field có kiểu không được hỗ trợ sẽ bị JFR bỏ qua khỏi schema. Đừng coi việc source compile là bằng chứng các field sẽ xuất hiện trong `RecordedEvent`.

Một số quy tắc khác:

- `static` fields không trở thành event fields.
- `transient` fields không được ghi như event fields.
- Cần tránh object graph lớn hoặc dữ liệu cá nhân; JFR event nên chứa **giá trị đo lường nhỏ và có hợp đồng rõ**.
- Event type schema được quyết định từ class/metadata; muốn đổi cấu trúc hoặc tên field trong ứng dụng thực, phải xem tác động tới các consumer đang truy cập field theo tên.

## 3. Phát event: tạo, gán dữ liệu, commit

Để ghi một custom event tức thời:

~~~java
BatchFinished event = new BatchFinished();
event.stage = "aggregate";
event.itemCount = 42;
event.commit();
~~~

`commit()` ghi các giá trị field, timestamp và duration của event vào cơ chế Flight Recorder **nếu cấu hình recording cho phép ghi**. Không nhất thiết callback sẽ chạy ngay đúng lúc `commit()` trả về: EventStream giao event theo batch/flush.

Nếu việc thu thập payload tốn CPU hoặc tạo nhiều chuỗi, dùng kiểm tra trước:

~~~java
BatchFinished event = new BatchFinished();

if (event.isEnabled()) {
    // Chỉ dựng payload khi có ít nhất một recording bật event.
    event.stage = "aggregate";
    event.itemCount = expensiveCount();
    if (event.shouldCommit()) {
        event.commit();
    }
}
~~~

Đây là **mảnh mã tích hợp**; `expensiveCount()` phải là hàm có thật trong ứng dụng.

Phân biệt:

| API | Ý nghĩa |
| --- | --- |
| `event.isEnabled()` | Có ít nhất một recording đang chạy và bật loại event này? |
| `event.shouldCommit()` | Event hiện tại có được ghi theo enabled/threshold hay không? |
| `event.commit()` | Ghi event khi đủ điều kiện; không có callback trực tiếp đồng bộ tới `onEvent` |
| `event.begin()` | Đánh dấu bắt đầu một duration event |
| `event.end()` | Đánh dấu kết thúc một duration event |

Với **event tức thời**, code thường chỉ gán và `commit()`. Với **event đo thời lượng**, hãy gọi `begin()` trước thao tác cần đo, `end()` sau đó, rồi `shouldCommit()`/`commit()` để threshold có ý nghĩa.

Không nên tạo chuỗi chứa request body hoặc SQL có tham số riêng tư trước `isEnabled()` rồi kỳ vọng JFR sẽ tự loại bỏ chi phí hoặc tự mã hóa bảo mật chúng.

## 4. Bật event và đăng ký callback: hai thao tác khác nhau

Trong `RecordingStream`, có thể thiết lập:

~~~java
try (var stream = new jdk.jfr.consumer.RecordingStream()) {
    stream.enable(BatchFinished.class)
          .withoutThreshold()
          .withoutStackTrace();

    stream.onEvent("app.BatchFinished", event -> {
        System.out.println(
            event.getString("stage") + ":" +
            event.getInt("itemCount")
        );
    });

    stream.startAsync();
    // Code ở đây phải tạo event và quản lý thời gian sống stream.
}
~~~

Đây là **mảnh mã**; nếu thoát try-with-resources ngay sau `startAsync()` thì stream bị đóng sớm và có thể **chưa kịp nhận sự kiện**. Chương trình mục 6 sử dụng `CountDownLatch` để chờ callback một cách có giới hạn.

**`stream.enable(BatchFinished.class)`** cấu hình JFR thu thập event type. **`stream.onEvent("app.BatchFinished", ...)`** đăng ký consumer theo tên event type. Chỉ gọi `onEvent` không đảm bảo event được bật; chỉ gọi `enable` không có nghĩa ứng dụng đã đăng ký callback.

### Bật bằng Class và bằng String

~~~java
stream.enable(BatchFinished.class);
stream.enable("app.BatchFinished");
~~~

Cả hai đều có thể dùng. Với custom event class nằm trong code của bạn, **`enable(Class)` rõ hơn** và tránh bất ngờ khi các class loader khác nhau nạp các event có cùng tên. Tài liệu `RecordingStream.enable(String)` nêu rằng nếu nhiều event classes cùng có một tên, lời gọi bằng tên có thể bật **tất cả** các loại có tên đó.

Ngược lại, `onEvent("app.BatchFinished", callback)` đăng ký consumer **theo event name**; nếu có xung đột tên, ứng dụng cần nhận diện event type chính xác theo thiết kế và metadata, không tin tên trùng là cùng một schema.

### Cấu hình threshold/stack trace

~~~java
stream.enable(BatchFinished.class)
      .withoutThreshold()
      .withoutStackTrace();
~~~

- `withoutThreshold()` chọn không áp ngưỡng duration, giúp ví dụ ghi các event tức thời.
- `withoutStackTrace()` không thu stack trace cho loại event này ở recording đó.
- Nếu đo thời lượng, có thể dùng `withThreshold(Duration.ofMillis(10))` để chỉ ghi các event đạt ngưỡng. **Cần kiểm tra event đã được `end()` trước `shouldCommit()`** để duration phù hợp.
- Chỉ chọn những event types và fields có ích, tránh stream/log mọi sự kiện khi không cần.

**Ghi nhớ:** annotation metadata, event settings của recording và callback của consumer là các tầng **khác nhau**.

## 5. Cùng một cơ chế onEvent cho event built-in và custom

JFR built-in event:

~~~java
stream.onEvent("jdk.CPULoad", event -> {
    System.out.println(event.getFloat("jvmUser"));
});
~~~

Custom event:

~~~java
stream.onEvent("app.BatchFinished", event -> {
    System.out.println(event.getInt("itemCount"));
});
~~~

Hai callback có cùng kiểu nhận **`jdk.jfr.consumer.RecordedEvent`**. Khác nhau nằm ở **tên event và schema fields**:

- `jdk.CPULoad` được định nghĩa trong JDK; các trường dùng theo metadata event của JDK đang chạy.
- `app.BatchFinished` được định nghĩa trong ứng dụng; consumer dùng tên field do event class khai báo.
- Cả hai đi qua pipeline JFR recording → flush → dispatch → `onEvent`.
- Có thể đăng ký **nhiều callback** trên một stream. Nếu chỉ quan tâm một số loại, dùng overload `onEvent(String, Consumer)` thay vì nhận mọi event rồi tự lọc.
- `onEvent(Consumer)` nhận tất cả events được dispatch; cần thiết khi làm công cụ tổng quát, nhưng có thể tốn công hơn khi chỉ cần một event type.

**Không thể lấy field bằng tên tùy ý.** `event.getInt("itemCount")` chỉ đúng nếu schema chứa field `itemCount` với kiểu có thể đọc tương ứng. Sai tên hoặc kiểu có thể gây `IllegalArgumentException`. Dùng `RecordedEvent.getEventType()` và các `ValueDescriptor` khi xây dựng consumer động cần introspection.

## 6. Chương trình Java 17+ hoàn chỉnh: stream live rồi đọc lại cùng file

Ví dụ này đã được **biên dịch và chạy trên OpenJDK 24**. Nó dùng:

1. Một custom event `BatchProcessed extends Event` có hai trường `stage` và `items`.
2. `RecordingStream` để **vừa bật recording vừa nhận custom events trực tiếp**.
3. `CountDownLatch` để chờ ba callback trước khi đóng stream và dump.
4. `EventStream.openFile(path)` để **đọc lại chính file recording bằng cùng cơ chế `onEvent(name, callback)`**.
5. Các counter thread-safe để không phụ thuộc thứ tự sự kiện hoặc thời gian flush.
6. File tạm và `finally` để dọn dữ liệu demo, không đụng vào file thật của người dùng.

Tạo file **`CustomJfrStreamingDemo.java`**:

~~~java
import java.nio.file.*;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import jdk.jfr.*;
import jdk.jfr.consumer.*;

public class CustomJfrStreamingDemo {

    @Name("demo.BatchProcessed")
    @Label("Batch Processed")
    @Category({"Demo", "Operations"})
    @StackTrace(false)
    static class BatchProcessed extends Event {
        @Label("Stage") String stage;
        @Label("Items") int items;
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("jfr-custom-", ".jfr");
        try {
            AtomicInteger liveCount = new AtomicInteger();
            AtomicInteger liveTotal = new AtomicInteger();
            CountDownLatch received = new CountDownLatch(3);

            // RecordingStream tạo recording và xử lý event cùng JVM.
            try (RecordingStream stream = new RecordingStream()) {
                stream.setMaxAge(Duration.ofMinutes(2));
                stream.setMaxSize(32L * 1024 * 1024);
                stream.enable(BatchProcessed.class)
                      .withoutThreshold()
                      .withoutStackTrace();

                stream.onEvent("demo.BatchProcessed", event -> {
                    liveCount.incrementAndGet();
                    liveTotal.addAndGet(event.getInt("items"));
                    received.countDown();
                });

                stream.startAsync();

                for (int count : new int[] {2, 3, 5}) {
                    BatchProcessed event = new BatchProcessed();
                    if (event.isEnabled()) {
                        event.stage = "aggregate";
                        event.items = count;
                        if (event.shouldCommit()) {
                            event.commit();
                        }
                    }
                }

                if (!received.await(15, TimeUnit.SECONDS)) {
                    throw new AssertionError(
                        "Live event callback timeout"
                    );
                }

                // Dump lúc stream vẫn chạy, trước khi close().
                stream.dump(file);
            }

            AtomicInteger replayCount = new AtomicInteger();
            AtomicInteger replayTotal = new AtomicInteger();

            // EventStream nhận cùng type/name nhưng từ tệp .jfr.
            try (EventStream replay = EventStream.openFile(file)) {
                replay.onEvent("demo.BatchProcessed", event -> {
                    replayCount.incrementAndGet();
                    replayTotal.addAndGet(event.getInt("items"));
                });
                replay.start();
            }

            System.out.println("live-count=" + liveCount.get());
            System.out.println("live-total=" + liveTotal.get());
            System.out.println("replay-count=" + replayCount.get());
            System.out.println("replay-total=" + replayTotal.get());
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Lệnh biên dịch/chạy trên JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 CustomJfrStreamingDemo.java
java CustomJfrStreamingDemo
~~~

**Đầu ra đã kiểm chứng khi chạy trên OpenJDK 24:**

~~~text
live-count=3
live-total=10
replay-count=3
replay-total=10
~~~

### Phân tích chi tiết kết quả

- Tên `demo.BatchProcessed` do annotation `@Name` quyết định; cùng chuỗi này dùng cho cả callback live lẫn file replay.
- `stream.enable(BatchProcessed.class)` bật event type trong `RecordingStream`; không cần một hệ thống log hay event bus riêng để phát/nhận custom event.
- Ba `BatchProcessed` lần lượt mang `items=2,3,5`; callback cộng `2 + 3 + 5 = 10`.
- `stream.startAsync()` cho producer chạy tiếp trong thread `main`; consumer dispatch ở thread khác. `CountDownLatch` bảo đảm chương trình **không đóng stream trước khi nhận đủ ba callback**, với timeout hữu hạn.
- `AtomicInteger` giúp cập nhật counter an toàn trên callback thread và đọc từ main thread. Nếu xử lý thông tin phức tạp hơn, cần chính sách thread safety và backpressure.
- `setMaxAge` và `setMaxSize` giới hạn dữ liệu được giữ cho recording stream; đây là cấu hình kiểm soát tài nguyên, **không phải cam kết rằng mọi bản dump luôn nhỏ hơn giới hạn**.
- `stream.dump(file)` viết dữ liệu recording vào file **trước khi stream bị đóng**. Tệp có thể chứa các events JDK khác; callback replay lọc theo tên custom event nên chỉ đếm ba event mong muốn.
- `EventStream.openFile(file)` đọc dữ liệu hữu hạn đã lưu; `replay.start()` thực hiện callback đồng bộ tới khi xử lý xong file.
- `Files.deleteIfExists(file)` xóa bản ghi **tạm do ví dụ tạo**; không sao chép việc này mù quáng sang các tệp JFR cần lưu làm bằng chứng sự cố.

Mã demo cố ý **không in đường dẫn tạm, timestamp, kích thước file hoặc thứ tự event**, vì các giá trị ấy thay đổi theo môi trường. Kết quả counter là điều cần kiểm chứng.

**Giới hạn kiểm thử:** khi chạy trên máy rất chậm, môi trường cấm JFR hoặc disk repository không dùng được, demo có thể thất bại/timeout. Đó là điều kiện môi trường, không phải cam kết mọi JVM luôn giao event trong 15 giây.

## 7. Hai con đường streaming và khi nào nên chọn

| Tiêu chí | `RecordingStream` | `EventStream` |
| --- | --- | --- |
| Vai trò | Tạo/điều khiển recording của **JVM hiện tại** và nhận events | Tiêu thụ events từ file hoặc repository đã có |
| Cách tạo | `new RecordingStream()` hoặc dùng `Configuration` | `EventStream.openFile(path)`, `openRepository()` |
| Bật custom event | `enable(MyEvent.class)` / `enable(name)` | Không có `enable(...)` trên interface; event phải được recording khác thu thập |
| Nhận custom event | `onEvent("app.MyEvent", callback)` | `onEvent("app.MyEvent", callback)` |
| Live monitoring | Phù hợp khi app tự cấu hình recording | `openRepository` phù hợp với repository có recording đang ghi |
| Đọc lại file | `dump(path)` xuất bản ghi, không phải API replay chính | `openFile(path)` đọc lại file, hữu ích cho chẩn đoán hậu kỳ |
| Lifecycle | Có `start/startAsync`, `close`, settings/retention; các API mới hơn còn có `stop()` | Có `start/startAsync`, `close`, callback/metadata |

**Lưu ý về phiên bản:** `RecordingStream.stop()` là API có từ Java 20, vì vậy trong ví dụ tương thích Java 17 ta dùng **`close()`/try-with-resources** thay vì gọi `stop()`. Không suy rằng mọi method trong tài liệu JDK 25 đều có mặt trong Java 17.

### Một consumer cho event từ repository

Nếu một `Recording` khác đã bật `app.BatchFinished` trong cùng JVM và đang phát sự kiện, có thể mở stream repository:

~~~java
try (EventStream stream = EventStream.openRepository()) {
    stream.onEvent("app.BatchFinished", event -> {
        System.out.println(event.getInt("itemCount"));
    });
    stream.start();
}
~~~

Đây là **mảnh mã minh họa**: stream này có thể chờ vô hạn nếu không có nguồn sự kiện hoặc không được đóng. Trong ứng dụng thực, cần quản lý lifecycle, thread và timeout. **`openRepository()` không tự bật event type**; hãy chắc chắn đã có recording thu thập sự kiện.

Mặc định, stream repository bắt đầu từ các sự kiện **được flush tiếp theo**, không tự hồi sinh lịch sử đã bị loại khỏi repository. Nếu muốn đọc một khoảng đã xảy ra, cần nguồn dữ liệu còn lưu và có thể dùng `setStartTime` trước khi `start()`. Đọc file là lựa chọn rõ ràng hơn cho hậu kiểm tái lập được.

## 8. Theo dõi duration event bằng cùng cơ chế

Custom event không chỉ biểu diễn “một điểm thời gian”. Nó có thể đo một đoạn xử lý:

~~~java
@Name("app.TaskDuration")
@Label("Task Duration")
static class TaskDuration extends Event {
    String taskType;
}
~~~

Trong code thực thi:

~~~java
TaskDuration event = new TaskDuration();
if (event.isEnabled()) {
    event.taskType = "catalog-read";
    event.begin();
    try {
        runCatalogRead();
    } finally {
        event.end();
        if (event.shouldCommit()) {
            event.commit();
        }
    }
} else {
    runCatalogRead();
}
~~~

Hai đoạn trên là **mảnh tích hợp**, không phải chương trình độc lập; `runCatalogRead()` do ứng dụng định nghĩa. Cấu trúc `try/finally` bảo đảm đo tới cuối ngay cả khi công việc ném exception. Việc ghi event phụ thuộc isEnabled/threshold; không được dùng JFR như hệ thống nghiệp vụ duy nhất để xác nhận thao tác đã hoàn thành.

Thiết lập threshold:

~~~java
stream.enable(TaskDuration.class)
      .withThreshold(Duration.ofMillis(20));
stream.onEvent("app.TaskDuration", event -> {
    System.out.println(event.getDuration());
});
~~~

Đây là **mảnh cấu hình**, cần có stream thích hợp và import `Duration`. Event có duration không đủ 20 ms sẽ không được ghi vào recording với cấu hình trên. Vì vậy nếu callback không chạy, có thể **không có event đạt threshold**, chứ chưa chắc listener bị sai.

**Thời điểm `begin/end` là ranh giới đo:** gọi `shouldCommit()` trước `end()` có thể khiến phép kiểm tra ngưỡng không phản ánh duration hoàn chỉnh. Với event tức thời, dùng cách viết ngắn của mục 6.

## 9. Khi callback không chạy: chuỗi kiểm tra

Một custom event không xuất hiện thường do một trong các nguyên nhân sau:

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Không có event nào | Không có recording đang chạy hoặc event type chưa bật | Gọi `event.isEnabled()`; kiểm tra `stream.enable(MyEvent.class)` trước start |
| Đã tạo event nhưng không có callback | Không gọi `commit()` hoặc `shouldCommit() == false` | Kiểm tra đường phát event và threshold |
| Listener không nhận nhưng file có event | `onEvent` dùng sai tên (`@Name` không khớp) | Đọc `getEventType().getName()` hoặc `jfr metadata` |
| Lỗi khi đọc field | Sai tên hoặc kiểu field; field không được JFR hỗ trợ | Đối chiếu schema trong `RecordedEvent.getEventType()` |
| `startAsync()` xong rồi thoát try ngay | Stream bị đóng trước lúc flush/dispatch | Chờ tín hiệu callback/giới hạn thời gian trước khi close |
| Callback đến muộn | JFR giao dữ liệu theo batch, sau flush | Phân biệt commit time và callback delivery time |
| Số events ít hơn mong muốn | Threshold, giới hạn recording, event bị disable, mất dữ liệu/timeout | Đo enabled, shouldCommit, kiểm tra repository/retention |
| Chương trình treo ở `start()` | Nguồn live không kết thúc; `start()` là đồng bộ | Dùng async với lifecycle rõ hoặc đọc file hữu hạn |
| Đọc lại tệp chỉ thấy event JDK | File được dump từ recording khác, custom event chưa bật | Kiểm tra đúng producer/recording và event name |
| Callback ném exception | Trình xử lý lỗi không rõ hoặc chỉ in stack trace ra stderr | Đăng ký `onError`, ghi log an toàn, kiểm thử riêng |
| Không giữ được data sau callback | `RecordedEvent` có thể được reuse | Trích field ngay trong callback hoặc `setReuse(false)` |

Khi debug, tránh thay đổi cùng lúc event name, threshold, sampling, retention và cách start stream. Hãy bật một custom event tối giản, xác minh `event.isEnabled()` và callback, rồi tăng dần mức chi tiết.

## 10. Callback và metadata trong luồng JFR

API `EventStream` có nhiều hook:

| Hook | Dùng khi nào |
| --- | --- |
| `onEvent(String, Consumer<RecordedEvent>)` | Chỉ muốn một event type theo tên |
| `onEvent(Consumer<RecordedEvent>)` | Muốn quan sát mọi event type trong stream |
| `onMetadata(Consumer<MetadataEvent>)` | Muốn biết event types mới xuất hiện và metadata của chúng |
| `onFlush(Runnable)` | Muốn tổng hợp kết quả sau khi một batch được flush |
| `onError(Consumer<Throwable>)` | Muốn xử lý lỗi callback/stream theo chính sách ứng dụng |
| `onClose(Runnable)` | Muốn được thông báo khi stream đóng |

Trong các phiên bản Java hiện đại, có thể đăng ký `onMetadata` để nhận metadata event type mới, sau đó quyết định đăng ký listener theo tên của event type. Đây là hướng xây dựng công cụ quan sát nhiều custom events **không biết trước tất cả tên**.

**Chú ý:** `onMetadata` được đưa vào JDK 16. Nếu viết code chỉ nhắm Java 14 gốc, cần kiểm tra API của JDK đích; với ví dụ Java 17+ trong bài, nó đã có. Việc đăng ký listener trong callback metadata là một cơ chế được tài liệu API hỗ trợ, nhưng code tổng quát cần kiểm soát schema/name collisions.

### Trích dữ liệu ngay trong callback

Theo tài liệu, `EventStream` có thể **tái sử dụng cùng đối tượng `RecordedEvent`** cho nhiều lần dispatch. Vì vậy đừng giữ nguyên object đó trong một danh sách rồi đọc các field về sau khi chưa đổi chính sách reuse.

An toàn hơn:

~~~java
stream.onEvent("app.BatchFinished", event -> {
    int count = event.getInt("itemCount");
    String stage = event.getString("stage");
    acceptSummary(stage, count);
});
~~~

Đây là **mảnh mã tích hợp** với hàm `acceptSummary` do ứng dụng định nghĩa. Nó trích các giá trị ngay trong callback. Nếu cần giữ hẳn `RecordedEvent` sau callback, có thể gọi `stream.setReuse(false)` **trước start** để nhận các object riêng, nhưng điều đó có thể tăng cấp phát bộ nhớ.

### Đồng bộ, bất đồng bộ và thứ tự

- `start()` gọi các action trong thread gọi và có thể block lâu nếu nguồn là repository đang mở.
- `startAsync()` dispatch trong thread riêng; dữ liệu chung phải có chính sách concurrency.
- Trong mỗi batch, events được sắp theo thời điểm kết thúc khi ordering bật; **thứ tự giữa các batches không nhất thiết hoàn toàn tăng theo timestamp**. Không dựa trên việc callbacks luôn theo thứ tự chính xác của producer khi cần semantics nghiệp vụ.
- Callback chậm có thể khiến việc tiêu thụ sự kiện bị trễ và tạo áp lực lên hệ thống quan sát; nên thực hiện xử lý ngắn, thống kê hoặc đẩy sang hàng đợi có giới hạn nếu cần xử lý nặng.
- Gọi `close()` không bảo đảm mọi callback đang chờ đã hoàn tất trước khi trả về. Với kết quả cần chắc chắn đã nhận, dùng signal/lifecycle rõ như `CountDownLatch` ở mục 6.

## 11. Đo chi phí và tránh rò rỉ dữ liệu custom events

Việc dùng JFR là quan sát **trong JVM**, không phải cơ chế truyền thông nghiệp vụ bền vững. Cần đặc biệt chú ý:

### 11.1. Chi phí tạo và tiêu thụ sự kiện

Commit một custom event cho **mọi request** trên đường nóng có thể tạo overhead CPU, cấp phát, buffer, I/O, kích thước file và callback processing. Chi phí phụ thuộc loại event, số lượng, threshold, stack trace, cách dựng payload và cấu hình recording.

Các cách kiểm soát:

1. Chỉ định nghĩa event khi nó trả lời một câu hỏi chẩn đoán hữu ích.
2. Dùng `isEnabled/shouldCommit` trước các phép tính payload tốn công.
3. Dùng duration threshold hoặc lấy mẫu theo thiết kế phù hợp khi lưu lượng cao.
4. Không ghi stack trace khi không dùng.
5. Giới hạn `maxAge/maxSize`, thời gian ghi, số event types và quyền truy cập vào recording.
6. So sánh overhead trên workload thật: throughput, p95/p99 latency, CPU, GC và disk I/O.

Không khẳng định JFR hoàn toàn miễn phí chỉ vì cơ chế streaming được thiết kế hiệu quả.

### 11.2. Trường dữ liệu nhạy cảm

Một event có thể dễ bị thiết kế sai:

~~~java
class RiskyRequestEvent extends Event {
    String userEmail;
    String rawAuthorizationHeader;
    String requestBody;
}
~~~

Đây là **ví dụ phản diện** về nguy cơ. Nếu recording bật và event được commit, các trường `String` này có thể trở thành dữ liệu lưu trong JFR. Không dựa vào việc file có đuôi nhị phân `.jfr` để coi nó vô hại.

Nên dùng:

~~~java
class SafeRequestEvent extends Event {
    String routeGroup;  // Nhãn cố định, không gồm query riêng tư.
    int itemCount;      // Số liệu tổng hợp.
}
~~~

Những field này cần được gán giá trị đã được kiểm tra theo chính sách dữ liệu. Ngay cả nhãn nhóm/ID nếu có khả năng tái định danh vẫn cần xem xét.

**Không nên** đưa token, mật khẩu, cookie, raw URL có query parameters, SQL chứa dữ liệu người dùng, request/response body hoặc PII vào custom event khi chỉ cần đo hiệu năng. File JFR cũng có thể chứa built-in metadata về class, method, thread, file/network hoặc environment; nên coi recording chưa được review là artifact nội bộ có thể nhạy cảm.

### 11.3. Vai trò của streaming không thay thế hệ thống logging/queue

JFR có thể drop/không ghi event theo configuration, threshold hoặc retention. Dispatch có thể chậm do flush. Vì vậy:

- **Không dùng custom JFR events làm nguồn duy nhất của business audit**, đối soát tiền, xuất hóa đơn, bảo đảm giao dịch, hoặc message delivery có tính chính xác tuyệt đối.
- Với telemetry chẩn đoán, event name và payload nhỏ, có thể đo được chi phí là lựa chọn hợp lý.
- Nếu cần độ tin cậy nghiệp vụ, dùng hệ thống lưu trữ/queue/audit được thiết kế với guarantee cụ thể; JFR chỉ bổ sung quan sát.
- Không mặc nhiên đẩy raw JFR file lên hệ thống ngoài tổ chức; kiểm tra nội dung và quyền truy cập trước.

## 12. Kiểm tra schema và nội dung bằng công cụ JDK

Nếu có file `recording.jfr` được phép xem:

~~~bash
jfr summary recording.jfr
jfr metadata recording.jfr
jfr print --events demo.BatchProcessed recording.jfr
~~~

- `jfr summary` cho biết số lượng và loại events trong file.
- `jfr metadata` giúp xác định event name, field names và field types.
- `jfr print --events demo.BatchProcessed` chỉ **hiển thị** các event phù hợp; nó không xóa events khác khỏi file.

Đây là **lệnh tích hợp**: cần file đã được lưu và có công cụ `jfr` tương ứng trong JDK. Các bản JDK hiện đại cũng cho phép kiểm tra qua API `RecordedEvent.getEventType()` và `EventType.getFields()`.

Chú ý bảo mật: khi `jfr print`, dữ liệu có thể xuất ra console, CI logs hoặc file text; đó cũng là một bản sao cần được quản lý theo quy định.

### Định danh tên và class loader

Nếu nhiều class loader nạp event classes có cùng `@Name`, `enable(String)` có thể bật tất cả; consumer `onEvent(name)` không tự đảm bảo schema của mọi event class trùng tên hoàn toàn giống nhau.

Khi xây framework plugin, có thể cân nhắc:

- Đặt namespace đủ duy nhất cho event names.
- Bật producer đã biết bằng `enable(Class)`.
- Kiểm tra metadata trước khi đọc fields trong listener tổng quát.
- Quản lý phiên bản schema của custom events khi ứng dụng/consumer thay đổi.

Không hard-code logic nhạy cảm dựa trên giả định mọi event name chỉ có đúng một class loader trên toàn bộ hệ thống.

## 13. Những lỗi phổ biến và cách sửa

| Lỗi | Tại sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ `new MyEvent()` mà không `commit()` | Chưa gửi event cho JFR | Gọi `commit()` khi event đủ điều kiện |
| Chỉ `onEvent(...)` mà không bật recording/event | Không có nguồn dữ liệu được thu thập | Dùng `RecordingStream.enable(...)` hoặc cấu hình recording bên ngoài |
| `onEvent("wrong.name", ...)` | Listener không khớp `@Name` | So event name với metadata/type thật |
| Dùng `List<String>` làm field event rồi đọc bằng `getString` | List không phải field type JFR hỗ trợ | Dùng primitive/String/Thread/Class thích hợp hoặc aggregate |
| Mong `commit()` gọi callback ngay cùng thread | JFR dispatch theo flush/batches | Dùng đồng bộ hóa/timeout hợp lý |
| `startAsync()` rồi đóng stream tức thì | Callback chưa có thời gian nhận event | Chờ tín hiệu callback, kiểm soát lifecycle |
| Dùng `RecordingStream.stop()` trong code target Java 17 | API `stop()` có từ Java 20 | Dùng `close()` và kiểm soát nhận events bằng cơ chế phù hợp |
| Không nhận duration event | Threshold chưa đạt hoặc gọi shouldCommit sai thời điểm | Dùng begin/end và kiểm tra shouldCommit sau end |
| Đọc sai tên field trong callback | Schema không chứa tên/kiểu đó | Dùng metadata và accessor đúng |
| Dùng `ArrayList` chung giữa threads mà không đồng bộ | Có thể gây race | Dùng counter atomic, thread-safe collection hoặc xử lý đồng bộ |
| Giữ `RecordedEvent` sau callback khi reuse bật | Object có thể bị reuse cho event sau | Đọc field ngay hoặc `setReuse(false)` |
| Mặc định raw JFR file an toàn để gửi | Có thể chứa metadata và payload nhạy cảm | Review, hạn quyền, retention, giảm dữ liệu tại nguồn |

## 14. Checklist trước khi triển khai

1. **Vấn đề cần đo là gì?** Event mới có bổ sung thông tin chẩn đoán chưa có ở built-in JFR events không?
2. **Tên event đã ổn định và đủ riêng biệt chưa?** `@Name` có namespace rõ ràng không?
3. **Các field có nằm trong danh sách kiểu hỗ trợ?** Không giả định mảng, List, enum hoặc object phức tạp sẽ được serial hóa.
4. **Có nơi bật event không?** `RecordingStream.enable`, `Recording.enable` hoặc cấu hình recording được kiểm soát?
5. **Producer có gọi commit không?** Với duration event, có `begin/end/shouldCommit` theo thứ tự đúng không?
6. **Consumer đăng ký đúng tên trước khi start chưa?** Đọc field bằng đúng tên và kiểu chưa?
7. **Live hay replay?** `RecordingStream` cho JVM hiện tại, `EventStream.openFile` cho file JFR có thật, `openRepository` cho repository.
8. **Async lifecycle có được chốt?** Timeout, latch, error callback, close, worker thread và khả năng callback trễ?
9. **Có kỳ vọng sai về giao sự kiện?** Event có thể mất, đến muộn, sắp xếp theo batch chứ không phải giao dịch đảm bảo exactly-once.
10. **Có hạn chế chi phí?** Threshold, event count, stack trace, buffer, maxAge/maxSize và baseline overhead?
11. **Có bảo vệ dữ liệu?** Không chứa PII/token trong field; file dump được phân loại/giới hạn quyền truy cập?
12. **Đã kiểm chứng cả live và file replay?** Kiểm tra số event, tổng số liệu, schema và error handling trên JDK mục tiêu?

## 15. Bài tập thực hành

### Bài 1 — Custom event tối thiểu

Tạo `@Name("lab.CacheRefresh") class CacheRefresh extends Event` với `String cacheGroup` và `int entryCount`. Bật event trong `RecordingStream`, đăng ký listener với tên đúng và phát ba events. Hãy viết chương trình tổng hợp `entryCount` thay vì in toàn bộ raw payload.

**Gợi ý:** tái sử dụng cấu trúc `CustomJfrStreamingDemo`, thay `BatchProcessed` bằng `CacheRefresh`, sửa name trong `onEvent` và dùng `AtomicInteger`.

### Bài 2 — Tên event không khớp

Đổi `onEvent("demo.BatchProcessed", ...)` thành `onEvent("demo.WrongName", ...)` nhưng giữ nguyên producer. Hỏi vì sao `CountDownLatch.await` timeout.

**Đáp án:** recording có thể vẫn thu custom event, nhưng consumer chỉ đăng ký callback cho một tên khác nên không nhận ba event mong đợi. Khôi phục tên đúng hoặc kiểm tra `getEventType().getName()`.

### Bài 3 — Duration threshold

Tạo `TaskDuration extends Event` và bật `withThreshold(Duration.ofMillis(20))`. Đo hai công việc giả lập: một khoảng 5 ms và một khoảng 50 ms. Hỏi callback nào có khả năng xuất hiện.

**Đáp án:** với threshold được áp dụng đúng, event ngắn dưới 20 ms bị lọc, event đủ dài được ghi. Thời gian sleep thực tế có thể lệch nên không dùng sleep đúng ngưỡng để tạo test tuyệt đối; đo/kiểm tra threshold một cách ổn định.

### Bài 4 — Live và replay

Chạy nguyên mẫu mục 6 và xác nhận:

~~~text
live-count=3
live-total=10
replay-count=3
replay-total=10
~~~

Sau đó đổi dãy `{2, 3, 5}` thành `{1, 4, 6}`. Dự đoán hai tổng đều là `11`, còn số lượng đều là `3`. Quan sát rằng **cùng callback schema** có thể đọc hai nguồn.

### Bài 5 — Quyền riêng tư

Một lập trình viên thêm `String sessionToken` và `String customerEmail` vào custom event vì “sẽ dễ tra cứu hơn”. Hãy đề xuất các field thay thế phục vụ đo hiệu năng mà không có dữ liệu cá nhân.

**Đáp án gợi ý:** route/category cố định đã được phép, số lượng item, thời lượng, nhóm trạng thái hoặc mã lỗi được chuẩn hóa; tránh raw URL/query, token/email và các nhóm đủ nhỏ để tái định danh.

### Bài 6 — Làm rõ vòng đời bất đồng bộ

Bỏ `received.await(...)` khỏi ví dụ, gọi `stream.dump(file)` ngay sau phát events rồi đóng. Hỏi vì sao kết quả replay có thể không phản ánh đầy đủ dữ liệu.

**Đáp án:** dispatch xảy ra sau flush/batch; việc stream đóng/dump quá sớm có thể dẫn tới sự kiện chưa được callback giao hoặc file không đủ dữ liệu kỳ vọng. Cần một cơ chế đồng bộ và giới hạn thời gian rõ ràng khi test.

## 16. Tài liệu chính thức còn áp dụng

- [Oracle JDK 25 — Event API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Event.html): cách định nghĩa event, field types hỗ trợ, `isEnabled()`, `shouldCommit()`, `begin/end` và `commit()`.
- [Oracle JDK 17 — RecordingStream API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): tạo recording của JVM hiện tại, `enable(Class)`, `onEvent`, `startAsync`, `dump`, giới hạn retention.
- [Oracle JDK 17 — EventStream API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): `openFile`, `openRepository`, `onEvent`, `onMetadata`, `onFlush`, reuse và callback lifecycle.
- [Oracle JDK 17 — jdk.jfr Package](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html): metadata, annotations, settings và custom event conventions.
- [Oracle JDK 17 — RecordedEvent API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): đọc field, timestamp, event type và duration trong consumer.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): thiết kế cơ chế stream được đưa vào Java 14.
- [Oracle — Java Flight Recorder API Programmer's Guide (Java 17)](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api-programmers-guide.pdf): hướng dẫn định nghĩa event và streaming.
