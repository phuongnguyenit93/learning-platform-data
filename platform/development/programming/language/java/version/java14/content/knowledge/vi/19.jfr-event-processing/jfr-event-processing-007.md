# `onFlush`, `onError`, `onClose` và hủy đăng ký callback của `EventStream` (Java 14+)

> **Mục tiêu:** biết khi nào nên dùng `onFlush(Runnable)` để xử lý hoàn thành một batch JFR, `onError(Consumer<Throwable>)` để tập trung xử lý lỗi, `onClose(Runnable)` để phản ứng khi stream đóng và `remove(Object)` để hủy một hoặc nhiều lần đăng ký. Phân biệt rõ các callback này với `onEvent(...)`, hiểu vòng đời `start`/`startAsync`/`close` và tránh các giả định sai về luồng, thứ tự, số lần gọi. API `jdk.jfr.consumer.EventStream` là tính năng chính thức từ Java 14 và vẫn được hỗ trợ trong JDK hiện hành; ví dụ chạy bằng JDK 17+.

## 1. Bối cảnh: xử lý sự kiện JFR bằng `EventStream`

**Java Flight Recorder (JFR)** ghi lại hoạt động của JVM ở dạng những sự kiện có kiểu, thời điểm và các thuộc tính. Giao diện `jdk.jfr.consumer.EventStream` đại diện một luồng đọc các sự kiện đó và chuyển chúng tới các callback đã đăng ký.

Có thể tạo `EventStream` từ tệp recording `.jfr` bằng `EventStream.openFile(path)`, hoặc đọc repository JFR thông qua `EventStream.openRepository()` / `openRepository(path)`. `RecordingStream` (thuộc cùng package) triển khai `EventStream` và còn quản lý quá trình tạo recording. Bốn phương thức ở tiêu đề thuộc **giao diện `EventStream`**, nên các kiểu stream tương ứng có thể áp dụng.

Một stream thường trải qua vòng đời:

1. **Mở nguồn** và tạo đối tượng `EventStream`.
2. **Đăng ký hành động**: `onEvent` để nhận dữ liệu, `onFlush` để gom/đẩy kết quả sau mỗi batch, `onError` để tiếp nhận lỗi, `onClose` để dọn state hoặc phát tín hiệu kết thúc.
3. **Bắt đầu xử lý**: `start()` xử lý đồng bộ trên thread gọi; `startAsync()` xử lý trong một thread riêng.
4. **Theo dõi và kết thúc**: khi nguồn kết thúc hoặc `close()` được gọi, stream đi vào quá trình đóng; cần giải phóng tài nguyên qua `try-with-resources` khi phù hợp.

Đăng ký callback **không tự khởi chạy stream**. Phải gọi `start()` hoặc `startAsync()`. Trong một ứng dụng có nhiều thread, cần chuẩn bị callback và state liên quan trước khi bắt đầu xử lý; đừng dựa vào việc đăng ký callback sau khi start sẽ luôn kịp nhận mọi event.

### Bảng chữ ký API

| Phương thức | Kiểu callback | Công việc / thời điểm |
|---|---|---|
| `onEvent(Consumer<RecordedEvent>)` | `Consumer<RecordedEvent>` | Nhận sự kiện trong stream |
| `onEvent(String, Consumer<RecordedEvent>)` | `Consumer<RecordedEvent>` | Chỉ nhận event khớp **tên event** |
| `onFlush(Runnable)` | `Runnable` | Được gọi **sau khi stream được flush**, ở ranh giới batch |
| `onError(Consumer<Throwable>)` | `Consumer<Throwable>` | Xử lý exception xảy ra trong quá trình streaming / callback |
| `onClose(Runnable)` | `Runnable` | Thực hiện hành động khi stream đóng |
| `remove(Object action)` | Chính đối tượng callback từng đăng ký | Hủy đăng ký; trả `true` nếu tìm thấy và gỡ ít nhất một lần |

Những phương thức này **không trả về subscription handle**. Muốn tháo callback, ứng dụng phải **giữ lại chính đối tượng `Runnable` hoặc `Consumer` đã đăng ký** để truyền vào `remove`. `remove` là phương thức chung, không phải `removeEvent`/`removeFlush` có tên riêng.

## 2. `onFlush(Runnable)`: biết khi nào một batch đã được giao

JFR chuyển dữ liệu trong **các batch**. Khi batch hiện tại đã được xử lý qua các callback sự kiện, `EventStream.onFlush(Runnable)` cho phép một hành động chạy sau khi stream được flush.

```java
import java.util.concurrent.atomic.AtomicLong;
import jdk.jfr.consumer.EventStream;

AtomicLong count = new AtomicLong();

try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("demo.Callback", event -> count.incrementAndGet());
    stream.onFlush(() -> {
        System.out.println("events processed so far: " + count.get());
    });
    stream.start();
}
```

Đây là **snippet** trong một phương thức có biến `Path file` trỏ đến tệp JFR hợp lệ và xử lý `IOException`; event `demo.Callback` phải tồn tại trong file nếu muốn nhận dữ liệu. Mục đích là mô tả cách nhận **tín hiệu flush/batch**, không cam kết stdout có số lần hoặc tổng count cụ thể.

**Những điều được phép suy ra:**

- Sau `onEvent` xử lý các sự kiện trong batch, `onFlush` tạo một điểm thích hợp để **đẩy số liệu tổng hợp**, cập nhật bộ đệm, ghi báo cáo, hoặc phát tín hiệu dữ liệu mới.
- Theo JavaDoc, các event trong **cùng một batch** được sắp theo thời điểm kết thúc; các batch khác nhau không được cam kết sắp xếp toàn cục. Nếu thứ tự không quan trọng, `setOrdered(false)` có thể giảm chi phí sắp xếp.
- Một lần flush không nhất thiết có đúng một event; cũng không có bảo đảm mỗi event sẽ được theo sau bởi một `onFlush` riêng.
- `onFlush` **không phải** lệnh “gọi ngay lúc này hãy ép hệ thống JFR flush”, không phải lịch hẹn định kỳ mỗi N mili giây và không tương đương `OutputStream.flush()` của Java I/O.
- Việc callback flush chạy **không tự chứng minh** dữ liệu ứng dụng đã ghi thành công vào cơ sở dữ liệu, đã được gửi qua mạng hoặc đã được commit vào một hệ thống khác. Những cơ chế đó có hợp đồng riêng.

Một ví dụ thiết kế: mỗi `onEvent` cập nhật bộ đếm/aggregate trong bộ nhớ, còn `onFlush` lấy snapshot và đẩy ra hệ thống metrics. Khi dùng `startAsync()`, dữ liệu cũng có thể được thread nghiệp vụ khác đọc; hãy quản lý đồng bộ hoặc dùng các primitive thread-safe như `AtomicLong`, `ConcurrentHashMap` phù hợp.

**Chú ý đến `RecordedEvent`:** `EventStream` có thể tái sử dụng cùng đối tượng `RecordedEvent` cho nhiều sự kiện, tùy `setReuse(boolean)`. Nếu cần giữ đối tượng event **sau khi callback kết thúc**, đặt `setReuse(false)` trước start, hoặc chỉ trích xuất dữ liệu bất biến như `String`/`long` và lưu chúng. Không lưu tùy tiện tham chiếu `RecordedEvent` vào list dùng ở `onFlush` rồi giả định mỗi entry vẫn đại diện một event độc lập.

## 3. `onError(Consumer<Throwable>)`: tiếp nhận lỗi đúng cách

`onError` nhận `Consumer<Throwable>`. JavaDoc ghi rõ: nếu **không đăng ký** action xử lý lỗi, stream in stack trace của exception ra **standard error (`stderr`)**. Nếu có đăng ký `onError`, action đã đăng ký **thay thế hành vi mặc định** này.

```java
stream.onError(error -> {
    System.err.println(
        "JFR stream error: " + error.getClass().getSimpleName());
});
```

Đây là **snippet** có biến `EventStream stream`; ví dụ chỉ in loại exception, khi xử lý lỗi thực tế có thể dùng logging có chính sách bảo vệ dữ liệu. Phương thức `onError` không có nghĩa toàn bộ exception sẽ được **nuốt bỏ rồi chắc chắn tiếp tục stream**. Hành vi tiếp tục/dừng phụ thuộc loại lỗi và trạng thái luồng.

**Quy tắc khi nhiều error action:** theo JavaDoc, nhiều `onError` action được thực thi **theo thứ tự đăng ký**. Vì tự đăng ký handler thay thế hành vi mặc định, nếu muốn có thông tin điều tra, chính handler của bạn cần ghi log phù hợp; không mặc định sẽ vẫn có stack trace trên stderr.

**Giới hạn đặc biệt:** nếu **chính một `onError` callback ném exception**, tài liệu nói hành vi kết quả **không xác định (undefined)**. Do đó error handler cần đơn giản, tránh ném lỗi mới, tránh thao tác có nguy cơ deadlock và có fallback khi logging không hoạt động. Không nên thêm `throw error` trong consumer khi chưa hiểu ảnh hưởng đến stream.

### Lỗi ném từ chính `onEvent`

Khi một callback `onEvent` ném `IllegalStateException`, luồng có thể chuyển exception đó tới `onError` đã đăng ký. Trong chương trình kiểm chứng ở mục 8, hai event tùy chỉnh làm handler cố ý ném lỗi, và `onError` ghi nhận hai lần `IllegalStateException` khi chạy trên OpenJDK 24.

Điều này giúp phân biệt hai khía cạnh: **callback dữ liệu** có thể thất bại vì logic người dùng; **callback xử lý lỗi** quan sát lỗi ấy. Đây là ví dụ kiểm thử có kiểm soát, không phải khuyến nghị cố ý ném exception để điều khiển luồng JFR trong production.

### Vì sao không nên log mọi lỗi theo cách in trực tiếp ra người dùng?

Một `Throwable` có thể chứa thông tin hệ thống: đường dẫn, tên lớp, stack trace, thông tin thread hoặc thậm chí nội dung dữ liệu. Log nội bộ cần lọc secrets, có giới hạn tần suất/khối lượng, và không gửi raw stack trace tới UI công khai. Nếu lỗi nghiêm trọng, cần chính sách thoát hoặc khởi tạo lại stream ở lớp quản lý, không cứ lặp vô hạn cùng một lỗi.

## 4. `onClose(Runnable)`: tín hiệu stream kết thúc

`onClose` đăng ký `Runnable` được gọi khi stream đóng. Stream có thể đóng vì:

- Code gọi `close()` thủ công hoặc thoát khỏi `try-with-resources`.
- Một stream file đi đến cuối nguồn và tự kết thúc.
- Các điều kiện dừng/ngoại lệ khi streaming hoặc nguồn JVM được giám sát chấm dứt.

```java
stream.onClose(() -> {
    System.out.println("JFR stream closed");
});
```

**Điểm quan trọng trong JavaDoc:** nếu stream **đã đóng trước khi đăng ký `onClose`**, action được thực thi **ngay lập tức trên thread đang gọi `onClose`**.

```java
try (EventStream stream = EventStream.openFile(file)) {
    stream.close();
    stream.onClose(() -> System.out.println("already closed"));
}
```

Đây là snippet với file hợp lệ. In `already closed` xảy ra ngay tại lời gọi `onClose` do stream đã đóng, không phải một đăng ký chờ tương lai.

**Không coi `onClose` là lệnh tự động hủy toàn bộ tài nguyên bên ngoài** như database connection, HTTP client hay executor do ứng dụng tạo. Action nên thực hiện giải phóng những tài nguyên **mà ứng dụng sở hữu** theo đúng vòng đời, và có khả năng chạy an toàn nếu bị gọi lại. Trong thử nghiệm JDK 24, không nên lấy **số lần gọi chính xác `onClose`** làm kết luận từ một chuỗi `start()` + `try-with-resources`: ví dụ mục 8 chỉ kiểm tra callback đóng **đã xảy ra**.

### `close()` không đồng nghĩa “mọi callback đã hoàn tất”

Theo JavaDoc, `EventStream.close()` giải phóng tài nguyên và yêu cầu dừng xử lý, nhưng **KHÔNG bảo đảm toàn bộ các registered actions hoàn tất trước khi `close()` trả về**. Khi xử lý async, một callback có thể vẫn đang chạy hoặc một vòng xử lý khác có thể đang chấm dứt.

`awaitTermination()` và `awaitTermination(Duration)` giúp thread điều khiển chờ theo hợp đồng của API. Tài liệu quy định chờ cho đến khi các hành động hoàn tất, stream bị đóng hoặc thread bị interrupt (hoặc hết timeout), tùy điều kiện nào đến trước. Vì vậy đừng biến nó thành một lời hứa tuyệt đối về việc **mọi side effect ngoài JFR đã hoàn tất**. Khi cần acknowledgment chính xác, dùng cơ chế đồng bộ/bất biến của ứng dụng, ví dụ `CountDownLatch`, `CompletableFuture` hoặc hàng đợi có tín hiệu hoàn thành.

**Tránh khóa chéo:** đừng vừa giữ lock của ứng dụng vừa gọi `close()`/`awaitTermination()` nếu callback phải lấy chính lock ấy để hoàn tất.

## 5. `remove(Object)`: hủy callback đã đăng ký

Chữ ký:

```java
boolean remove(Object action)
```

`remove` cho phép bỏ một action khỏi stream. JavaDoc quy định:

1. Truyền **chính đối tượng callback** từng đăng ký, không truyền tên event hoặc một lambda mới dù có cùng mã lệnh.
2. Nếu đối tượng action đã được đăng ký **nhiều lần**, `remove` bỏ **tất cả lần đăng ký** của nó.
3. Trả về `true` khi thực sự hủy được action đã đăng ký, `false` nếu không có action cần gỡ.
4. `action` không được `null`.
5. Áp dụng với các callback được đăng ký bằng `onEvent`, `onFlush`, `onError` và `onClose` như phần “See Also” của API.

### Đúng: giữ tham chiếu callback để gỡ

```java
import java.util.function.Consumer;
import jdk.jfr.consumer.RecordedEvent;

Consumer<RecordedEvent> listener = event ->
    System.out.println(event.getEventType().getName());

stream.onEvent("jdk.CPULoad", listener);
stream.onEvent("jdk.CPULoad", listener);

boolean removed = stream.remove(listener); // true nếu hai lần đăng ký có mặt.
boolean again = stream.remove(listener);   // false vì đã gỡ hết.
```

Đây là snippet bên trong phương thức có `EventStream stream` và import tương ứng. Việc `onEvent` đăng ký hai lần **cùng một object** là có chủ đích để minh họa quy tắc gỡ tất cả.

**Sai:** gọi `stream.remove(event -> System.out.println(...))` với lambda mới. Tên `remove` chỉ nhận object; code lambda mới thường là một đối tượng khác với callback đã đăng ký, nên không gỡ được action cũ.

**Khác biệt giữa gỡ và đóng stream:**

- `remove(listener)` chỉ bỏ việc gọi callback đó trong các lần dispatch phù hợp; stream và các callback khác vẫn có thể hoạt động.
- `close()` yêu cầu dừng **cả stream**, giải phóng tài nguyên của stream.
- `remove` **không phải** cách vô hiệu hóa recording hoặc tắt một event type trong JFR. Nếu chỉ muốn dừng ghi event khi dùng `RecordingStream`, kiểm tra API `disable(...)` hoặc cấu hình recording.
- Khi callback đã bắt đầu chạy trong thread xử lý, `remove` không nên được coi là cơ chế **hủy ngay lập tức một tác vụ đang chạy**. Dùng logic hủy và đồng bộ ở ứng dụng nếu cần bảo đảm mạnh hơn.

### Gỡ callback `onFlush`, `onError`, `onClose`

Cơ chế giống nhau, miễn lưu đúng tham chiếu:

```java
Runnable flushAction = () -> System.out.println("flushed");
Runnable closeAction = () -> System.out.println("closed");
Consumer<Throwable> errorAction = error ->
    System.err.println(error.getClass().getName());

stream.onFlush(flushAction);
stream.onClose(closeAction);
stream.onError(errorAction);

stream.remove(flushAction);
stream.remove(errorAction);
// closeAction vẫn còn được đăng ký.
```

Đây là **snippet** thuộc một phương thức có biến `stream`; đặt các import tương ứng. Gỡ tất cả `onError` handlers đồng nghĩa lỗi về sau có thể quay lại hành vi mặc định in stack trace ra `stderr`, tùy trạng thái stream. Gỡ một `onClose` handler khiến action ấy không còn nhận thông báo đóng trong các lần dispatch tương lai, nhưng không thay đổi việc stream thực sự được đóng.

**Cẩn trọng khi đăng ký trễ:** JavaDoc cho phép `onClose` chạy ngay nếu stream đã đóng, nên `remove(closeAction)` sau đó không thể “rút lại” hành động vừa chạy. Để tránh hành vi bất ngờ, đăng ký lifecycle callbacks **trước khi start**.

## 6. Lưu ý về thứ tự và concurrency của callback

Một số ngữ nghĩa được API xác định rõ, một số khác không nên giả định:

| Chủ đề | Điều có thể dựa vào | Điều không nên giả định |
|---|---|---|
| Sự kiện trong batch | Event được sắp theo thời gian kết thúc trong batch mặc định | Các batch khác nhau luôn tạo thứ tự thời gian toàn cục |
| `onFlush` | Hành động sau flush/batch | Mỗi event có đúng một flush, hoặc flush theo timer cố định |
| Nhiều `onError` action | Chạy theo **thứ tự đăng ký** | Lỗi do `onError` ném có hành vi được xác định |
| `onClose` sau khi đã đóng | Chạy ngay trên thread gọi `onClose` | Luôn chờ một thread riêng trong tương lai |
| `close()` | Giải phóng tài nguyên và dừng stream | Trả về sau khi mọi action chắc chắn hoàn tất |
| `remove` | Bỏ tất cả lần đăng ký của action object đó | Hủy tức thì callback đang thực thi ở một thread khác |
| `start()` | Xử lý trên thread đang gọi | Thích hợp để chạy vô hạn trên UI/HTTP request thread |
| `startAsync()` | Xử lý trên một thread khác | Callback được phép tùy tiện ghi state chung không đồng bộ |

Ví dụ có `startAsync`: callback có thể chạy trên thread streaming khác với thread gọi `stream.remove(...)` hoặc `stream.close()`. Nếu cả hai cùng thay đổi `ArrayList` hay map thường, có nguy cơ data race. Dùng `AtomicInteger`, `ConcurrentLinkedQueue`, `ConcurrentHashMap` hoặc đồng bộ phù hợp, và thiết kế lifecycle callback theo hướng **idempotent**.

Không nên gọi tác vụ blocking dài từ `onFlush`, `onError` hoặc `onClose` nếu tác vụ ấy chặn chính thread dùng để chuyển sự kiện. Với logging hoặc gửi dữ liệu qua mạng, cân nhắc enqueue tác vụ sang worker của ứng dụng rồi quản lý acknowledgment rõ ràng.

## 7. Kiểm thử hành vi bằng file JFR cố định

Muốn kiểm tra `onFlush/onError/onClose/remove`, **đọc một file JFR đã có dữ liệu kiểm soát** ổn định hơn phụ thuộc số event hệ thống xuất hiện vào một khoảng thời gian ngắn.

Trong chương trình mục 8:

1. Định nghĩa một custom event mang tên `demo.Callback` với field `label`.
2. Tạo một `Recording`, bật event này, commit `one` và `two`, rồi `dump` ra file `.jfr`.
3. Mở `EventStream.openFile(file)`, đăng ký **cùng một callback** hai lần, gọi `remove` để gỡ, và đăng ký callback khác để nhận sự kiện.
4. Đăng ký `onFlush`, `onClose` và `onError`, sau đó `start()` xử lý file đồng bộ.
5. Mở file lần hai; event handler cố ý ném `IllegalStateException` để xác nhận `onError` nhận lỗi trong môi trường kiểm chứng.
6. Mở lần ba, `close()` trước rồi đăng ký `onClose` để kiểm tra hành động được thực hiện ngay.

Chương trình giữ count `flushes`/`closes` nhưng chỉ in **`> 0`** để không biến số lần callback thành hằng số cam kết trên mọi runtime. Các nhãn `one` và `two` được sắp xếp trước khi in giúp đầu ra xác định, không dùng kết quả này để kết luận global ordering của JFR.

## 8. Chương trình Java 17+ hoàn chỉnh và stdout đã kiểm tra

Tạo tệp **`EventStreamCallbacksDemo.java`** với mã sau:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.EventStream;
import jdk.jfr.consumer.RecordedEvent;

public class EventStreamCallbacksDemo {
    @Name("demo.Callback")
    static class Probe extends Event {
        String label;
        Probe(String label) { this.label = label; }
    }

    static void emit(String label) {
        new Probe(label).commit();
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("callback-demo-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(Probe.class).withoutThreshold();
                recording.start();
                emit("one");
                emit("two");
                recording.stop();
                recording.dump(file);
            }

            List<String> seen = new ArrayList<>();
            AtomicInteger removedCalls = new AtomicInteger();
            AtomicInteger flushes = new AtomicInteger();
            AtomicInteger closes = new AtomicInteger();
            List<String> unexpectedErrors = new ArrayList<>();
            Consumer<RecordedEvent> removed =
                event -> removedCalls.incrementAndGet();
            Consumer<RecordedEvent> kept =
                event -> seen.add(event.getString("label"));
            boolean firstRemove;
            boolean secondRemove;

            try (EventStream stream = EventStream.openFile(file)) {
                stream.onEvent("demo.Callback", removed);
                stream.onEvent("demo.Callback", removed);
                stream.onEvent("demo.Callback", kept);
                firstRemove = stream.remove(removed);
                secondRemove = stream.remove(removed);
                stream.onFlush(() -> flushes.incrementAndGet());
                stream.onClose(() -> closes.incrementAndGet());
                stream.onError(error ->
                    unexpectedErrors.add(error.getClass().getSimpleName()));
                stream.start();
            }

            Collections.sort(seen);
            System.out.println("seen=" + seen);
            System.out.println("removedCalls=" + removedCalls.get());
            System.out.println("removeFirst=" + firstRemove);
            System.out.println("removeAgain=" + secondRemove);
            System.out.println("flushOccurred=" + (flushes.get() > 0));
            System.out.println("closeObserved=" + (closes.get() > 0));
            System.out.println("unexpectedErrors=" + unexpectedErrors);

            List<String> errors = new ArrayList<>();
            try (EventStream stream = EventStream.openFile(file)) {
                stream.onError(error ->
                    errors.add(error.getClass().getSimpleName()));
                stream.onEvent("demo.Callback", event -> {
                    throw new IllegalStateException("demo handler failure");
                });
                stream.start();
            }
            System.out.println("handledErrors=" + errors);

            final boolean[] immediateClose = {false};
            try (EventStream stream = EventStream.openFile(file)) {
                stream.close();
                stream.onClose(() -> immediateClose[0] = true);
            }
            System.out.println("lateCloseAction=" + immediateClose[0]);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17+ có module `jdk.jfr`**, không cần flag preview:

```bash
javac -encoding UTF-8 EventStreamCallbacksDemo.java
java EventStreamCallbacksDemo
```

**Stdout chính xác đã xác minh trên OpenJDK 24:**

```text
seen=[one, two]
removedCalls=0
removeFirst=true
removeAgain=false
flushOccurred=true
closeObserved=true
unexpectedErrors=[]
handledErrors=[IllegalStateException, IllegalStateException]
lateCloseAction=true
```

**Diễn giải kết quả theo đúng hợp đồng và giới hạn:**

- `seen=[one, two]`: callback được giữ lại đọc được hai custom events trong file; danh sách được sort trước khi in.
- `removedCalls=0`: callback đã đăng ký hai lần nhưng được `remove` trước `start` nên không được gọi.
- `removeFirst=true`, `removeAgain=false`: lần đầu gỡ mọi lần đăng ký của cùng callback object, lần sau không còn action đó.
- `flushOccurred=true`: stream có kích hoạt flush callback; số flush cụ thể không được dùng làm assertion.
- `closeObserved=true`: ít nhất một close callback đã chạy; không assert callback đóng luôn đúng một lần.
- `unexpectedErrors=[]`: luồng file thông thường không phát sinh lỗi cho error consumer trong lần thử.
- `handledErrors=[IllegalStateException, IllegalStateException]`: hai lần xử lý event cố ý ném lỗi trên JDK thử nghiệm, và `onError` nhận được hai exception tương ứng.
- `lateCloseAction=true`: `onClose` được đăng ký **sau** khi đóng stream nên thực thi ngay theo JavaDoc.

**Đừng kiểm thử “số lần flush” hoặc “số lần close” bằng một con số mặc định tự chế.** Đối với CI trên JDK khác, có thể viết assertion vào những hành vi API được đặc tả (ví dụ `remove` true/false, `onClose` chạy khi đăng ký sau đóng) và dùng thời gian/chốt đồng bộ cho các sự kiện async.

## 9. Lỗi phổ biến và cách sửa

| Lỗi/triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| Callback `onEvent` không chạy | Quên gọi `start()`/`startAsync()`, event không có trong file hoặc chưa được bật | Kiểm tra nguồn, đăng ký trước start và đảm bảo event được ghi |
| Mong `onFlush` chạy sau **mọi** event | JFR xử lý dữ liệu theo batch | Dùng `onEvent` cho từng event; `onFlush` cho tổng hợp sau batch |
| Mong `onFlush` tự ép flush xuống đĩa/mạng | Nó là callback **thông báo**, không phải lệnh flush I/O tùy ý | Gọi API I/O thích hợp trong action nếu cần, kèm kiểm soát lỗi |
| Đăng ký `onError` rồi không thấy stderr khi exception xảy ra | Error action đã **thay thế mặc định** in stack trace | Ghi log hợp lệ bên trong handler |
| Error handler lại `throw` exception | JavaDoc nói hành vi undefined | Làm handler đơn giản, xử lý lỗi log nội bộ, không ném ra |
| Cứ `remove(e -> ...)` với lambda mới | Không phải object callback cũ | Giữ callback trong biến và truyền **cùng tham chiếu** |
| Gọi `remove` một lần nhưng thấy vẫn có callback khác cùng chức năng | Những lambda/object khác vẫn được đăng ký riêng | Gỡ đúng mọi object cụ thể; một object trùng đăng ký được gỡ hết một lần |
| Đăng ký `onClose` sau khi stream đóng mà action chạy ngay | Hành vi **được tài liệu quy định** | Đăng ký trước start hoặc thiết kế action có thể chạy tức thời |
| Giả định `close()` chờ mọi tác vụ đã xong | JavaDoc không đưa ra bảo đảm đó | Dùng cơ chế acknowledgment/đồng bộ ứng dụng phù hợp |
| Lưu `RecordedEvent` sau callback rồi đọc sai dữ liệu | Event object có thể được tái sử dụng | `setReuse(false)` khi cần giữ event, hoặc lưu bản sao giá trị cần dùng |
| `ArrayList` bị truy cập đồng thời từ callback và thread điều khiển | `startAsync` dùng thread riêng | Dùng cấu trúc dữ liệu đồng bộ hoặc thiết kế ownership theo thread |
| Nhầm hủy callback với tắt recording | `remove` chỉ thay đổi đăng ký action | Dùng API cấu hình JFR nếu muốn disable event |

## 10. Checklist khi triển khai production

1. Mở đúng nguồn JFR: `openFile`, `openRepository` hoặc `RecordingStream` theo yêu cầu.
2. Đăng ký `onEvent`, `onFlush`, `onError` và `onClose` **trước start**; biết rõ mục đích của từng loại.
3. Dùng `onFlush` cho xử lý sau batch, không suy luận nó là timer hay một event một lần.
4. Error handler có log hữu ích và không ném lỗi mới; xem xét chính sách retry/stop ở lớp quản lý stream.
5. Close handler an toàn khi chạy ngay, không phụ thuộc số lần gọi cố định; dọn tài nguyên do ứng dụng sở hữu.
6. Giữ tham chiếu `Consumer`/`Runnable` thật nếu dự kiến `remove`; kiểm tra boolean kết quả và giả định hợp lệ về concurrency.
7. Xử lý stream async bằng thread-safe state; không blocking vô hạn callback.
8. Nếu lưu event vượt callback, dùng `setReuse(false)` hoặc lưu dữ liệu đã trích xuất.
9. Quản lý `try-with-resources` và lifecycle; không coi `close()` là hàng rào cho mọi side effect.
10. Kiểm thử bằng custom events/tệp `.jfr` có dữ liệu biết trước, không phụ thuộc số lượng event ngẫu nhiên của JVM.
11. Bảo vệ log và dữ liệu JFR chứa chi tiết hạ tầng hoặc dữ liệu nhạy cảm; chỉ dùng API JDK hiện đại.

## Tài liệu chính thức

- Oracle Java SE 26 API, `jdk.jfr.consumer.EventStream` — `onFlush`, `onError`, `onClose`, `remove` và `close`: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html
- Oracle Java SE 17 API, `EventStream` — chữ ký API, callback lifecycle và các quy tắc đăng ký: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html
- Oracle Java SE 25 API, `EventStream` — batch, sorting, event object reuse: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html
- Oracle Java SE 17 API, `RecordingStream`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html
- Oracle Java SE 17 API, `Recording` — bật event và dump file JFR: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html
- Oracle Java SE 17 API, `RecordedEvent`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html
