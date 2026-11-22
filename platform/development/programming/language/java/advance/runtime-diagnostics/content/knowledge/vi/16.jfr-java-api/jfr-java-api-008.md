# 16.8. RecordingStream với đăng ký callback, start hoặc startAsync và close

## 1. Đặt vấn đề: nhận sự kiện JFR ngay trong mã Java

`RecordingStream` thuộc module `jdk.jfr`, package `jdk.jfr.consumer`. API này tạo một recording của **JVM hiện tại** và chuyển các sự kiện JFR đã được ghi thành các đối tượng `RecordedEvent` cho callback do ứng dụng đăng ký. Chúng ta có thể phát hiện một lần GC, xem CPU load, hoặc nhận sự kiện custom khi chương trình đang chạy, thay vì đợi xuất toàn bộ file `.jfr` để phân tích về sau.

Ví dụ thực tế: dịch vụ cần thống kê số lần một hoạt động nội bộ xảy ra để hỗ trợ chẩn đoán. Dịch vụ có thể định nghĩa `Event` riêng, bật loại sự kiện đó trong `RecordingStream`, đăng ký `onEvent(...)` và xử lý số đo trong callback. Muốn dùng lâu dài phải kiểm soát vòng đời stream, thread, tốc độ callback và chi phí thu thập.

**Sau bài này, bạn sẽ:**

- Hiểu rõ `RecordingStream` tạo và nhận sự kiện như thế nào, phân biệt nó với `Recording` và `EventStream.openFile(...)`.
- Đăng ký đúng callback `onEvent`, `onError`, `onFlush`, `onClose`; sử dụng `enable` và đọc `RecordedEvent` đúng trường.
- Quyết định dùng `start()` khi muốn xử lý trên thread hiện tại hoặc `startAsync()` khi muốn thread gọi tiếp tục công việc.
- Đóng stream chắc chắn bằng `close()` hoặc `try-with-resources`; hiểu vì sao close không cam kết mọi event đã được xử lý.
- Viết ví dụ Java 17+ chạy được, bao gồm **hai chế độ start và startAsync**, kiểm tra callback và đảm bảo tài nguyên được giải phóng.
- Tránh các lỗi về thứ tự đăng ký, sự kiện chưa flush, race condition, block callback và shutdown thiếu kiểm soát.

Bài tập trung vào **lifecycle của stream và callback trong JVM**, không đi sâu vào thiết kế custom event, phân tích file dump hoặc thiết lập kết nối JFR từ xa.

## 2. Cơ chế hoạt động và nơi callback thực thi

Dòng dữ liệu khái quát:

~~~text
Code ứng dụng hoặc HotSpot tạo JFR event
            │
            ▼
    JFR recording trong cùng JVM
            │
            ▼
     JFR buffer / flush thành batch
            │
            ▼
     RecordingStream đọc batch
            │
            ├─ onEvent("tên loại", Consumer<RecordedEvent>)
            ├─ onEvent(Consumer<RecordedEvent>)  [mọi event được stream giao]
            ├─ onFlush(Runnable)                 [sau batch flush]
            ├─ onError(Consumer<Throwable>)      [khi có lỗi]
            └─ onClose(Runnable)                 [khi stream đóng]
~~~

Giao diện `EventStream` định nghĩa các callback và hành vi đọc sự kiện. `RecordingStream` vừa sở hữu recording cục bộ vừa triển khai `EventStream`, nên có thể `enable`/`disable` loại event và gọi `start` hoặc `startAsync`. Các sự kiện đến theo **batch sau khi dữ liệu được flush**; đó không phải lời hứa callback chạy tức thời đúng tại lệnh `event.commit()`.

**Dòng thời gian điển hình:**

~~~text
Thread khởi tạo      | tạo RecordingStream -> enable -> onEvent/onError/onClose
                     | startAsync() -> trả về; thread này tiếp tục
Producer thread      | tạo Event -> commit()
JFR/stream thread    | đọc batch sau flush -> onEvent(RecordedEvent)
Thread điều phối      | đến hạn/đóng dịch vụ -> close() -> cleanup
~~~

Với `start()`, **thread gọi `start()` chính là thread xử lý callback**, và lời gọi đó chặn cho đến khi stream kết thúc. Với `startAsync()`, các callback được thực hiện trên **một thread riêng**, còn method gọi trả về sau khi khởi động cơ chế xử lý bất đồng bộ. Callback của một stream được dispatch tuần tự trên thread xử lý stream theo tài liệu API, nhưng các producer có thể chạy trên nhiều thread; dữ liệu chia sẻ với ứng dụng vẫn cần cơ chế đồng bộ/atomic phù hợp.

Không suy ra mọi event đã `commit` chắc chắn được nhận: còn phụ thuộc event type có bật hay không, threshold, việc ghi/flush, retention, thời gian bắt đầu và thời điểm stream được đóng.

## 3. Phân biệt RecordingStream và các API JFR khác

| API | Trách nhiệm | Cách dùng đặc trưng |
| --- | --- | --- |
| `jdk.jfr.Event` | Tạo **custom event** bằng subclass, gắn fields và gọi `commit()` | Nguồn sự kiện nghiệp vụ |
| `jdk.jfr.Recording` | Điều khiển recording, thời gian, settings, dump file | Thu dữ liệu cho phân tích ngoại tuyến |
| `RecordingStream` | Ghi và stream sự kiện **trong JVM hiện tại**, cho phép bật event và nhận callback | Phản ứng trực tiếp, thống kê chẩn đoán cục bộ |
| `EventStream.openFile(path)` | Đọc sự kiện có trong một file `.jfr` | Đọc offline; không tạo recording mới |
| `EventStream.openRepository(...)` | Theo dõi dữ liệu từ JFR repository | Đọc các chunk của repository; cần quyền và repository phù hợp |
| `RemoteRecordingStream` | Dùng JFR qua `jdk.management.jfr` cho JVM remote thông qua quản lý JVM | Kịch bản giám sát từ xa; cấu hình và quyền khác |

**Không nhầm** `RecordingStream.start()` với `Recording.start()`. Cùng tên method nhưng `Recording.start()` bắt đầu trạng thái recording và trả về; `RecordingStream.start()` bắt đầu quá trình **tiêu thụ event và gọi callback**, nên nó chặn caller. Nếu bạn muốn caller tiếp tục chạy ngay, dùng `RecordingStream.startAsync()`.

`RecordingStream` có từ Java 14; các ví dụ ở đây hướng đến **Java 17+**. Một số method mới hơn như `RecordingStream.stop()` được thêm từ Java 20, nên ví dụ dùng `close()` để giữ khả năng tương thích Java 17.

## 4. Đăng ký callback trước khi bắt đầu

### 4.1. Bật đúng event và chọn callback có lọc

Đoạn minh họa (nằm trong method có biến `RecordingStream stream`, không phải chương trình độc lập):

~~~java
stream.enable("jdk.CPULoad").withPeriod(java.time.Duration.ofSeconds(1));
stream.onEvent("jdk.CPULoad", event -> {
    double machine = event.getDouble("machineTotal");
    System.out.println("Machine CPU ratio: " + machine);
});
~~~

Ở đây `enable("jdk.CPULoad")` yêu cầu thu loại event này, `withPeriod(...)` quy định chu kỳ lấy mẫu cho sự kiện định kỳ, còn `onEvent("jdk.CPULoad", ...)` chỉ nhận event trùng **tên JFR event type**. Giá trị `machineTotal` là tỷ lệ CPU, không phải mặc định phần trăm; nếu cần hiển thị %, nhân 100 và đối chiếu tài liệu field của JDK đang chạy. Tên/field của JFR event phải kiểm tra đúng schema, không suy diễn từ tên class Java.

Có hai cách đăng ký:

~~~java
// Đoạn minh họa, stream đã được tạo:
stream.onEvent("jdk.GarbageCollection", event -> handleGc(event));
stream.onEvent(event -> handleAnyEvent(event));
~~~

- `onEvent(String, Consumer<RecordedEvent>)` lọc theo loại, thường hiệu quả hơn tự if/else mọi event trong callback chung.
- `onEvent(Consumer<RecordedEvent>)` nhận mọi event mà stream giao, phù hợp khảo sát ban đầu nhưng có thể rất tốn khi nhiều event.
- Việc **đăng ký callback không tự động đảm bảo event type được bật**; phải hiểu cấu hình recording. Thực hành nên gọi `enable(EventClass.class)` hoặc `enable("event.name")` có chủ đích.
- Với custom event, `@Name("lesson.DemoEvent")` xác định tên JFR event type, còn tên Java class chỉ là chi tiết khai báo. Lấy field bằng API typed như `getInt("marker")`, `getString("message")` và xác minh field có tồn tại.
- `onMetadata(...)` (Java 16+) có thể nhận metadata loại sự kiện rồi đăng ký callbacks theo tên khi schema xuất hiện; hữu ích với luồng thay đổi schema. Với phần lớn bài tập, đăng ký theo tên biết trước là rõ nhất.

### 4.2. Các callback còn lại

| Callback | Khi nào gọi | Lưu ý khi áp dụng |
| --- | --- | --- |
| `onEvent(String, Consumer)` | Có event đúng tên được dispatch | Đọc nhanh field; tránh I/O chặn lâu |
| `onEvent(Consumer)` | Có event bất kỳ trong stream | Event số lượng lớn làm tăng tải handler |
| `onFlush(Runnable)` | Sau khi một batch sự kiện được flush | Có thể chuyển số liệu đã cộng dồn sang metric/queue; không giả định mỗi flush đúng một giây |
| `onError(Consumer<Throwable>)` | Có exception khi xử lý stream/callback | Nếu không đăng ký, mặc định stack trace được in stderr; handler tự lỗi có hậu quả không xác định |
| `onClose(Runnable)` | Stream đóng, gồm đóng thủ công hay tự kết thúc | Hỗ trợ notification/cleanup; không đồng nghĩa đã xử lý hết event |
| `remove(Object action)` | Bỏ đăng ký callback đã thêm trước đó | Truyền **chính instance Consumer/Runnable** đã đăng ký; lambda tạo mới sẽ không khớp |

Ví dụ bỏ đăng ký callback (đoạn method minh họa; cần `stream` và import đúng):

~~~java
java.util.function.Consumer<jdk.jfr.consumer.RecordedEvent> consumer =
        event -> System.out.println(event.getEventType().getName());
stream.onEvent("jdk.GarbageCollection", consumer);
// Khi cần thay đổi đăng ký:
boolean removed = stream.remove(consumer);
~~~

Nếu một action được đăng ký nhiều lần, `remove(action)` gỡ các lần đăng ký trùng của action đó. Đăng ký các callback thiết yếu, đặc biệt `onError` và `onClose`, **trước khi start** để không đánh mất giai đoạn khởi tạo hoặc đóng sớm.

**Callback có thể làm stream lỗi:** nếu handler ném exception, nó đi vào cơ chế báo lỗi của stream. Không nên “nuốt” mọi lỗi trong `onError` rồi tiếp tục báo trạng thái healthy. Ghi log/nguyên nhân và chuyển trạng thái để hệ thống chủ động xử lý.

## 5. Bảng quyết định: start(), startAsync(), close() và stop()

| Method | Thread và blocking | Thực tế nên dùng |
| --- | --- | --- |
| `start()` | Chạy callback trên **thread gọi** và **chặn** cho tới khi stream kết thúc | Một chương trình chỉ làm nhiệm vụ theo dõi; vòng đời kết thúc từ thread khác, thời hạn hoặc signal |
| `startAsync()` | Dispatch callback trên **một thread riêng**, trả về để thread gọi tiếp tục | Dịch vụ/ứng dụng còn phải thực hiện công việc khác |
| `close()` | Giải phóng tài nguyên; yêu cầu kết thúc stream ngay hoặc tại flush kế | Trong `finally`, `try-with-resources`, shutdown hook hoặc lifecycle stop |
| `awaitTermination()` / `awaitTermination(Duration)` | Đợi trạng thái kết thúc/hoàn tất action trong giới hạn API | Điều phối khi dùng async; overload có timeout là `void`, không trả boolean “đã hoàn tất” |
| `stop()` (**Java 20+**) | Dừng và chờ event của recording được tiêu thụ | Khi cần drain trước khi phân tích; tránh gọi **ngay trong callback** vì có thể deadlock |

**Hai khác biệt quan trọng:**

1. `close()` **không đảm bảo** tất cả callback đã chạy xong **trước khi method trả về**. Đừng dùng “đã gọi close” làm bằng chứng mọi event cuối cùng đã vào database/metric. Nếu cần một tín hiệu cụ thể, thiết kế `CountDownLatch` hoặc cơ chế completion riêng; với Java 20+, cân nhắc `stop()` từ thread điều phối sau khi đã cân nhắc latency/timeout.
2. `startAsync()` **không bảo đảm** một event `commit()` ngay dòng kế đã được callback nhận: việc khởi động/flush là bất đồng bộ. Nếu cần chứng minh callback hoạt động, phát event và **đợi có giới hạn** theo tín hiệu từ handler, thay vì `Thread.sleep(10)` rồi tự kết luận.

Ví dụ sai dễ gặp:

~~~java
try (var stream = new jdk.jfr.consumer.RecordingStream()) {
    stream.onEvent(System.out::println);
    stream.startAsync();
} // Stream bị close gần như ngay lập tức!
~~~

`try-with-resources` trong đoạn này đóng stream ngay sau `startAsync()`, nên thường không có thời gian nhận event. Đúng hơn là để lifetime của resource bao trùm lifetime của ứng dụng/công việc cần theo dõi, hoặc dùng scope hữu hạn có điều kiện dừng rõ ràng.

## 6. Ví dụ chạy được trên Java 17+: cả sync lẫn async

Ví dụ sau cố ý dùng **custom event nhỏ**, để kết quả không phụ thuộc việc JDK có đang tạo sự kiện GC/CPU cụ thể hay không. Nó sử dụng `CountDownLatch` làm tín hiệu đã nhận, `AtomicReference` để chuyển lỗi từ callback sang thread kiểm tra, và `try-with-resources` để dọn tài nguyên. Khi chạy thành công, stdout được xác định.

Lưu thành **`RecordingStreamLifecycleDemo.java`**:

~~~java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public class RecordingStreamLifecycleDemo {
    @Name("lesson.DemoEvent")
    static class DemoEvent extends Event {
        int marker;
    }

    private static boolean emitUntilSeen(CountDownLatch seen, int marker)
            throws InterruptedException {
        for (int i = 0; i < 30; i++) {
            DemoEvent event = new DemoEvent();
            event.marker = marker;
            event.commit();
            if (seen.await(250, TimeUnit.MILLISECONDS)) {
                return true;
            }
        }
        return false;
    }

    private static void subscribe(RecordingStream stream,
                                  CountDownLatch seen, int marker,
                                  AtomicReference<Throwable> failure) {
        stream.enable(DemoEvent.class).withoutStackTrace();
        stream.onEvent("lesson.DemoEvent", event -> {
            if (event.getInt("marker") == marker) {
                seen.countDown();
            }
        });
        stream.onError(failure::set);
    }

    private static void asyncDemo() throws Exception {
        CountDownLatch seen = new CountDownLatch(1);
        CountDownLatch closed = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        try (RecordingStream stream = new RecordingStream()) {
            stream.setMaxAge(Duration.ofSeconds(15));
            subscribe(stream, seen, 1, failure);
            stream.onClose(closed::countDown);
            stream.startAsync();
            if (!emitUntilSeen(seen, 1)) {
                throw new IllegalStateException("No async event received");
            }
        }
        if (!closed.await(3, TimeUnit.SECONDS) || failure.get() != null) {
            throw new IllegalStateException("Async stream did not close cleanly",
                                            failure.get());
        }
        System.out.println("asyncReceived=true");
        System.out.println("asyncClosed=true");
    }

    private static void syncDemo() throws Exception {
        CountDownLatch seen = new CountDownLatch(1);
        CountDownLatch closed = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        AtomicReference<Throwable> producerFailure = new AtomicReference<>();

        try (RecordingStream stream = new RecordingStream()) {
            subscribe(stream, seen, 2, failure);
            stream.onClose(closed::countDown);

            Thread producer = new Thread(() -> {
                try {
                    if (!emitUntilSeen(seen, 2)) {
                        producerFailure.set(new IllegalStateException("No event"));
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    producerFailure.set(e);
                } finally {
                    stream.close(); // Wake the thread blocked in start().
                }
            }, "event-producer");
            producer.start();
            stream.start();       // Processes callbacks on this thread; blocks.
            producer.join();
        }

        if (seen.getCount() != 0 || !closed.await(3, TimeUnit.SECONDS)
                || failure.get() != null || producerFailure.get() != null) {
            throw new IllegalStateException("Sync stream did not finish cleanly");
        }
        System.out.println("syncReceived=true");
        System.out.println("syncStartReturned=true");
    }

    public static void main(String[] args) throws Exception {
        asyncDemo();
        syncDemo();
    }
}
~~~

Chạy trong thư mục chứa tệp, với **JDK 17+ có hỗ trợ JFR**:

~~~bash
javac RecordingStreamLifecycleDemo.java
java RecordingStreamLifecycleDemo
~~~

Stdout khi bài lab chạy thành công (đã kiểm tra trực tiếp trên JDK 24):

~~~text
asyncReceived=true
asyncClosed=true
syncReceived=true
syncStartReturned=true
~~~

### 6.1. Tại sao ví dụ không chỉ sleep cố định?

- `emitUntilSeen` phát một event rồi chờ tối đa 250 ms, lặp tới 30 lần để bù cho startup và batch flush trễ. Nó **không giả định** callback xảy ra ngay khi `commit()`; chỉ in thành công nếu đã quan sát đúng event.
- `onEvent("lesson.DemoEvent", ...)` đọc `marker` và chỉ đếm khi giá trị phù hợp, nên hai thử nghiệm không xác nhận nhầm event.
- `asyncDemo` gọi `startAsync()`, caller vẫn có thể tiếp tục phát sự kiện. Khi thoát `try-with-resources`, `close()` được gọi và chương trình đợi `onClose` để kiểm tra.
- `syncDemo` khởi động một thread producer riêng, sau đó gọi `start()` từ thread main. Producer phát event tới khi thấy callback, **gọi `close()` từ thread riêng**, giúp `start()` trả về. Đây là lý do `start()` không làm main chạy tiếp được nếu không có cơ chế đóng độc lập.
- `AtomicReference<Throwable>` cho phép nhận diện lỗi callback/producer mà không dựa vào exception có thể xảy ra trên thread khác.
- Nếu stream không nhận event trong thời gian đã đặt, demo **ném exception** để người học thấy điều kiện không thỏa; không in PASS giả. Máy quá tải hoặc JFR flush chậm có thể cần thời gian lớn hơn.

Không dùng benchmark CPU/latency từ vòng lặp nhỏ này; đây là minh chứng lifecycle. Số lần phát thực tế có thể nhiều hơn số callback được đếm, và chương trình không cố nhận tất cả các event trước khi đóng.

## 7. Từng bước áp dụng lifecycle đúng trong ứng dụng

**Cách dùng sync — thread giám sát riêng:**

~~~text
Tạo stream
    -> Cấu hình event/retention
    -> Đăng ký onEvent, onError, onClose
    -> Có một cách đóng độc lập (signal/shutdown/thread khác)
    -> start() [chặn thread hiện tại]
    -> đóng / kết thúc -> start() trả về
    -> tài nguyên được giải phóng
~~~

Ví dụ công cụ terminal chuyên nghe JFR có thể dùng `start()` trong main thread, rồi nhận tín hiệu dừng qua shutdown hook. Nếu không có thời hạn hoặc tín hiệu đóng, nó sẽ tiếp tục chặn; đó là hành vi đúng thiết kế, không phải lỗi treo API.

**Cách dùng async — service theo dõi song song:**

~~~text
Application.start()
    -> new RecordingStream()
    -> enable + đăng ký callback
    -> startAsync()
    -> ứng dụng phục vụ yêu cầu
Application.stop()
    -> ngừng phát công việc nếu cần
    -> close stream đúng một lần (idempotent theo tài liệu)
    -> đợi completion theo nhu cầu, với giới hạn
    -> giải phóng queue/worker của ứng dụng
~~~

Một service thực cần chủ sở hữu rõ ràng cho stream, ví dụ `AutoCloseable` bean/resource của ứng dụng. Đừng tạo một stream mới mỗi request rồi quên đóng: bạn sẽ thêm ghi dữ liệu, callback thread, buffer và các tài nguyên JFR không cần thiết.

### 7.1. Ai nên gọi close?

- **`try-with-resources`:** tốt cho chương trình/bài test có phạm vi lexical rõ, bảo đảm đóng kể cả khi exception.
- **Hook đóng service:** khi ứng dụng quản lý stream suốt vòng đời, gọi `close()` trong lifecycle stop/shutdown và xử lý lỗi; bảo đảm hook thực sự chạy trong quá trình dừng bình thường.
- **Thread điều phối:** dùng khi gọi `start()` ở một thread khác để tránh chặn không thời hạn.
- **Callback:** có thể đóng để ngừng ngay, nhưng không nên dùng `stop()` ngay trong callback vì thao tác chờ drain có thể làm luồng tự chờ chính nó (deadlock). Đơn giản hơn là báo tín hiệu cho thread điều phối thực hiện shutdown.

Đối với Java 17, **`close()` là API di động trong phạm vi bài**; với JDK 20+, `stop()` có thể đợi các event của recording được tiêu thụ trước khi xử lý tiếp, nhưng cách chờ phải được thiết kế riêng và không nên thực hiện từ callback.

### 7.2. Chờ async hoàn tất và đọc lỗi đúng cách

`awaitTermination(Duration)` của `EventStream` không trả một boolean cho biết timed out hay đã xong. Vì thế với một sự kiện nghiệp vụ cần xác nhận, dùng tín hiệu độc lập, ví dụ `CountDownLatch.await(timeout, unit)` (trả boolean), `CompletableFuture`, hoặc một trạng thái kết quả đồng bộ. Gọi `awaitTermination` có thể hữu ích khi điều phối shutdown, nhưng **không** biến nó thành kiểm chứng việc một loại event cụ thể đã xuất hiện.

Nếu thread bị interrupt khi chờ, không im lặng nuốt `InterruptedException`. Khôi phục interrupt status hoặc cho exception đi lên, đồng thời đóng stream trong `finally`. Hãy đặt timeout hữu hạn để shutdown không chặn vô hạn do nguồn sự kiện hoặc handler bị lỗi.

## 8. Quy tắc về thứ tự, đồng bộ và hiệu năng callback

### 8.1. Thứ tự event không phải là tổng thứ tự tuyệt đối trên toàn thời gian

JFR chuyển event theo **các batch**. Trong một batch được giao, event được sắp theo end time khi chế độ ordering hoạt động. Một event trong batch sau có thể có timestamp sớm hơn event đã đến từ batch trước vì phụ thuộc lúc flush; đừng xây logic nghiệp vụ “event đến sau = xảy ra sau” mà không kiểm tra timestamp/ID.

Nếu thứ tự không quan trọng, `setOrdered(false)` có thể giảm chi phí sắp xếp. Nhưng sau đó handler phải chấp nhận thứ tự arrival. Đối với thống kê số lần hoặc histogram, thứ tự thường không quan trọng; đối với dựng timeline, cần xử lý event timestamp và khả năng out-of-order.

### 8.2. Không giữ RecordedEvent tùy tiện sau callback

Theo tài liệu `EventStream`, object `RecordedEvent` có thể được **tái sử dụng** cho các event khác. Đừng đưa trực tiếp `RecordedEvent` vào queue và sử dụng nó rất lâu sau callback khi chưa kiểm soát reuse. Cách an toàn thường là **đọc ngay field cần thiết thành immutable DTO**:

~~~java
// Minh họa bên trong callback:
int marker = event.getInt("marker");
long at = event.getStartTime().toEpochMilli();
queue.offer(new EventSummary(marker, at)); // EventSummary/queue là kiểu do ứng dụng định nghĩa.
~~~

Đây là đoạn minh họa, **không phải source độc lập**; bạn phải định nghĩa `EventSummary` và queue. API `setReuse(false)` thay đổi cách tái sử dụng event object nhưng có thể tăng cấp phát; vẫn nên chuyển thành DTO nhỏ và kiểm soát lifecycle dữ liệu. Nếu không cần giữ, hãy cập nhật counter hoặc trạng thái atomic ngay trong callback.

### 8.3. Callback nên ngắn và không block lâu

Một callback chậm tạo tình trạng consumer xử lý không kịp nguồn event. Các vấn đề thường gặp:

- Gọi HTTP/database, ghi log quá nhiều hoặc serialize payload lớn trong mọi `onEvent`.
- Giữ object lớn từ event hoặc callback closure trong một registry suốt đời ứng dụng.
- Dùng queue không giới hạn làm tăng bộ nhớ khi event rate vượt throughput downstream.
- Gọi `stop()` (Java 20+) ngay trong callback, dẫn đến nguy cơ deadlock vì `stop()` phải chờ drain.
- Đọc/ghi state chia sẻ không thread-safe giữa callback thread, request threads và shutdown thread.

Thiết kế thực tế: **callback chỉ trích các trường cần thiết**, cập nhật `LongAdder`/counter hoặc đưa DTO nhỏ vào bounded queue, để worker khác xử lý I/O. Định nghĩa rõ chính sách khi queue đầy: drop có đếm, sampling, hoặc giảm loại/chu kỳ event. Không tự chặn vô hạn callback để chờ downstream. Theo dõi event rate, callback latency, queue depth, dropped events, số lỗi và trạng thái stream.

### 8.4. Nhiều stream và cấu hình event

Nhiều `RecordingStream` trong cùng JVM có thể chia sẻ công việc JFR ở mức nền tảng, nhưng có mỗi callback/retention riêng. Đừng mặc định cost bằng 0 khi thêm stream; cũng không tự cộng tuyến tính overhead của từng stream. Cần đo thực tế với loại event và tải thực. Event settings có thể thay đổi hiệu quả thu ở JVM; hãy giữ các stream có chủ sở hữu rõ và tránh tạo tùy tiện theo từng request.

Một `RecordingStream` có thể `dump(Path)` thành `.jfr` khi đã start và chưa close; API khuyên đặt `setMaxAge` hoặc `setMaxSize` trước khi start để bảo đảm có dữ liệu giữ. **Streaming callback không tự sinh file dump cuối cùng**: muốn phân tích offline phải chủ động dump theo policy, quản lý quyền truy cập, dung lượng và cleanup.

## 9. Những lỗi dễ gặp và cách xác định nguyên nhân

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `onEvent` không bao giờ chạy | Quên `start/startAsync`, event type chưa enable, sai tên, threshold lọc hết | Kiểm tra `@Name`/event metadata, `enable`, thời điểm bắt đầu, có phát event thật |
| Gọi `start()` xong chương trình “treo” | `start()` cố ý blocking; không có thread/điều kiện đóng | Dùng `startAsync()` hoặc thiết kế close từ thread khác |
| `startAsync()` rồi thoát method không nhận event | Scope `try-with-resources` đóng quá sớm | Giữ resource sống đủ lâu và đợi tín hiệu callback có hạn |
| Sau `commit()` vẫn chưa thấy callback | JFR flush theo batch, event chưa được đọc hoặc stream chưa ready | Chờ có timeout, xác minh onError/flush, không giả định realtime tức thời |
| `close()` được gọi nhưng vài event cuối thiếu | `close` có thể dừng trước khi xử lý hết event | Dùng completion protocol, khi cần drain trên JDK20+ xem `stop()` từ bên ngoài callback |
| `startAsync()` sau khi stream đã đóng | Stream đã CLOSED hoặc đã start | Không restart cùng object; tạo stream mới theo lifecycle |
| App rất chậm dù JFR nhẹ | Callback làm blocking I/O, log mỗi event, queue không giới hạn | Tối giản callback, bounded queue, giảm event volume và đo overhead |
| Đã có `onError` nhưng không thấy stack trace | Handler `onError` thay thế hành vi stderr mặc định | Tự log, đếm lỗi và quyết định fail/restart thay vì im lặng |
| Dashboard dữ liệu lệch thứ tự | JFR event batch không bảo đảm thứ tự toàn cục | Dùng timestamp/sequence, chấp nhận event trễ hoặc sort lại |
| Lưu `RecordedEvent` rồi field thay đổi bất ngờ | Object có thể được reuse sau callback | Copy field thành DTO hoặc `setReuse(false)` nếu thật sự phù hợp |
| Shutdown vẫn chờ mãi | Không gọi close, callback block hoặc chờ latch vô hạn | Close đúng owner, timeout hữu hạn, tránh I/O đồng bộ trong callback |
| Callback bị đăng ký nhiều lần | Setup lifecycle chạy trùng | Quản lý một stream instance/owner, `remove` đúng action khi cần |

**Đừng gọi stream là “healthy” chỉ vì `startAsync()` không ném exception.** Điều kiện vận hành tốt cần ít nhất: stream chưa đóng bất ngờ, không có lỗi, có các event loại cần thiết trong cửa sổ đo và downstream không bị nghẽn. Nếu event loại đó hiếm, health check có thể dựa vào một custom heartbeat event hoặc thống kê flush phù hợp; không bắt mọi JVM phải có GC mỗi giây.

## 10. Bài tập áp dụng

**Bài 1 — phân biệt blocking.** Một main method có dòng `stream.start(); System.out.println("READY");`. Khi nào “READY” xuất hiện? **Chỉ sau khi stream kết thúc/đóng**. Nếu muốn main tiếp tục ngay, dùng `startAsync()` và giữ resource sống đủ lâu.

**Bài 2 — callback không chạy.** Đã đăng ký `onEvent("lesson.Payment", handler)`, nhưng code phát class có `@Name("lesson.PaymentCreated")`. Vì sao không thấy event? **Tên không khớp**; cũng cần bật đúng event class và xét threshold/flush.

**Bài 3 — đóng quá sớm.** Một hàm tạo stream, gọi `startAsync()` rồi thoát khối `try`. Làm sao sửa? Đưa resource vào service có vòng đời rõ, đóng ở stop hook; test bằng `CountDownLatch` thay vì sleep ngắn.

**Bài 4 — thread đang làm gì?** Với `start()`, callback chạy trên thread nào? **Thread gọi `start()`**. Với `startAsync()`? **Thread riêng do stream dùng để dispatch callback**. Khi dùng object chia sẻ với request thread phải đồng bộ phù hợp.

**Bài 5 — muốn đủ event trước khi chốt số liệu.** Gọi `close()` rồi đếm snapshot có đủ mọi event không? **Không được đảm bảo**. Với JDK 20+, xem `stop()` từ điều phối (không ở callback), hoặc giao thức completion với producer và tín hiệu đã xử lý.

**Bài 6 — queue tăng không giới hạn.** Mỗi callback đẩy một DTO vào queue vô hạn, downstream chỉ xử lý 100 item/s, trong khi JFR phát 10.000 item/s. Hệ quả? Queue tăng khoảng **9.900 item/s** nếu tốc độ ổn định; nguy cơ OOM. Dùng bounded queue, đo dropped events và điều chỉnh thu thập.

**Bài 7 — lỗi onError.** Khi thêm `onError(t -> {})` trống, ứng dụng không còn in stack trace mặc định. Đây có phải xử lý lỗi tốt? **Không**. Callback lỗi cần telemetry và trạng thái xử lý, tránh im lặng làm mất tín hiệu.

**Bài 8 — event nhận trễ.** Event A có timestamp 10:00:00.200 đến callback sau event B timestamp 10:00:00.500. API có sai không? **Không nhất thiết**: ordering theo batch không là tổng thứ tự giữa các batch. Xây lại timeline bằng timestamp nếu thực sự cần.

## 11. Checklist áp dụng nhanh

1. Khởi tạo `RecordingStream` đúng JVM, chọn settings và chỉ bật loại event cần thiết.
2. Đăng ký `onEvent`, `onError`, `onClose` **trước start**; chọn filter theo tên để tránh xử lý thừa.
3. Chọn `start()` nếu caller chịu trách nhiệm chạy vòng stream; chọn `startAsync()` nếu caller còn phải làm việc khác.
4. Xác định owner và thời điểm `close()`; đừng để resource chết ngay sau `startAsync` hoặc không bao giờ được đóng.
5. Với async, dùng tín hiệu/timeout để kiểm chứng event quan trọng và trạng thái kết thúc; đừng coi `close` đồng nghĩa drain hoàn tất.
6. Đọc/copy field cần thiết trong callback, xử lý nhanh, giữ queue bounded và theo dõi lỗi/độ trễ.
7. Kiểm tra event schema, batch/ordering, `RecordedEvent` reuse và khả năng không nhận đủ event khi shutdown.
8. Thử với Java/JDK thực tế, tự đo overhead, và chỉ dump file khi có nhu cầu phân tích offline.

## Tài liệu tham khảo

- Oracle Java SE 21, [RecordingStream API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html) — constructors, enable, callback, start/startAsync, close, awaitTermination, stop, dump, maxAge/maxSize.
- Oracle Java SE 21, [EventStream API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html) — dispatch theo batch, event ordering/reuse, onError/onClose/onFlush, chờ kết thúc.
- Oracle Java SE 21, [RecordedEvent API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html) — đọc các trường của sự kiện, timestamp và duration.
- Oracle Java SE 21, [JFR Event API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html) và [EventSettings API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html) — custom event, enable, threshold, stack trace và period.
- Oracle Java SE 21, [Java Flight Recorder API Programmer’s Guide](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api-programmers-guide.html) — làm việc với JFR qua Java code.
