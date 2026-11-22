# Phân biệt ghi sự kiện với tiêu thụ sự kiện liên tục trong Java Flight Recorder (JFR)

> **Phạm vi:** Chủ đề **Java 14 → Nền tảng JFR**. Bài giải thích hai công việc khác nhau: **ghi dữ liệu sự kiện** và **tiêu thụ các sự kiện qua stream liên tục**. JFR và API streaming giới thiệu từ Java 14 vẫn được hỗ trợ trong Java hiện hành; ví dụ dùng **JDK 17 trở lên**, không yêu cầu `--enable-preview` và không sử dụng các khả năng preview cũ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả đường đi của một JFR event từ **producer** qua cơ chế ghi, repository/file đến **consumer**.
2. Phân biệt `jdk.jfr.Event` và `Event.commit()` với `jdk.jfr.Recording`, `RecordingFile`, `EventStream`, `RecordingStream`.
3. Giải thích vì sao `commit()` **không phải** lời gọi đồng bộ tới `onEvent(...)`.
4. Chọn giữa **record → stop/dump → đọc file offline** và **record + callback liên tục** tùy nhu cầu.
5. Hiểu `EventStream.openRepository()` chỉ **đọc repository**, còn `RecordingStream` **tạo recording trong JVM hiện tại và stream event**.
6. Viết custom event và code Java 17+ chạy được cho cả chế độ ghi và stream.
7. Nắm điều kiện phát sinh event: `enable`, `threshold`, `isEnabled`, `shouldCommit`.
8. Quản lý `start`/`stop`/`dump`/`close`, giới hạn `maxAge/maxSize`, batching/flush và thread safety.
9. Biết giới hạn bảo đảm của JFR, tránh xem nó như cơ sở dữ liệu giao dịch hoặc message broker có delivery guarantee.

**Kết luận nền tảng:** *Ghi sự kiện* tạo dữ liệu chẩn đoán trong JFR; *tiêu thụ sự kiện liên tục* là đọc các dữ liệu đó khi chúng được JVM flush và chuyển cho callback. Chúng liên quan nhưng không đồng nhất.

## 2. Bức tranh tổng thể

**Java Flight Recorder (JFR)** là cơ chế thu thập các sự kiện liên quan runtime, như CPU, GC, thread, I/O và các sự kiện tùy biến do ứng dụng định nghĩa. Nó phục vụ quan sát, profiling, điều tra sự cố và phát hiện tín hiệu hiệu năng.

```text
Custom event / JVM event
          |
          | e.commit() hoặc JVM ghi event nội bộ
          v
JFR engine thu thập sự kiện
          |
          +----------------------+------------------+
          |                      |                  |
          v                      v                  v
Recording đang chạy     Repository/chunks      RecordingStream
          |                      |                  |
          v                      v                  v
stop + dump(file)      EventStream.openRepository    onEvent(callback)
          |
          v
File .jfr
          |
          +--> RecordingFile.readEvent/readAllEvents
          +--> EventStream.openFile
          +--> jfr print, jfr summary, công cụ phân tích
```

Sơ đồ thể hiện các cách nhìn dữ liệu. Nó **không** khẳng định mọi sự kiện đều được ghi, giữ nguyên mãi trong repository hay xuất hiện tức thời ở callback. Setting, ngưỡng thời gian, flush, retention, thời điểm bắt đầu consumer và giới hạn môi trường có thể làm thay đổi tập dữ liệu thực tế.

### Tên và trách nhiệm các API

| API | Chịu trách nhiệm | Có tự tạo recording? |
| --- | --- | --- |
| `jdk.jfr.Event` | Lớp cha của custom event, dùng `begin`/`end`/`commit` | Không |
| `jdk.jfr.Recording` | Cấu hình, `start`, `stop`, `dump` để thu thập dữ liệu | **Có** |
| `jdk.jfr.consumer.RecordingFile` | Đọc các event đã lưu ở file `.jfr` | Không |
| `jdk.jfr.consumer.EventStream` | Đăng ký `onEvent` và tiêu thụ từ file/repository | **Không** với `openFile`/`openRepository` |
| `jdk.jfr.consumer.RecordingStream` | Recording kết hợp stream cho **JVM hiện tại** | **Có** |
| `jdk.jfr.consumer.RecordedEvent` | Đại diện dữ liệu event mà consumer đọc được | Không |

Một `Recording` không tự phát callback trực tiếp. Một `EventStream` đọc repository không tự bật loại event. Một `RecordingStream` kết hợp được cả hai việc trong cùng JVM.

## 3. Producer: tạo và commit custom event

Một custom event kế thừa `jdk.jfr.Event`, có thể gắn annotation `@Name` để ổn định tên:

```java
import jdk.jfr.Event;
import jdk.jfr.Name;

@Name("demo.OrderPlaced")
class OrderPlaced extends Event {
    public int orderId;
    public String status;
}
```

Sau đó ứng dụng có thể tạo và commit:

```java
OrderPlaced e = new OrderPlaced();
e.orderId = 101;
e.status = "ACCEPTED";
e.commit();
```

Hai đoạn code trên là **mã minh họa**, chưa có `main`. `e.commit()` ghi sự kiện qua hệ thống JFR **nếu cấu hình recording và điều kiện của event cho phép**. Nó không trả về object `RecordedEvent` và không chờ consumer `onEvent` xử lý xong.

**Những điểm quan trọng:**

- Có thể không có recording đang bật event `demo.OrderPlaced`; lúc đó không được giả định event đã được lưu.
- Event settings như `enabled` và `threshold` quyết định có ghi sự kiện hay không.
- `Event.isEnabled()` kiểm tra trạng thái bật ghi; `Event.shouldCommit()` giúp tránh thu thập payload đắt đỏ khi event không vượt các điều kiện ghi.
- Event fields của JFR chỉ hỗ trợ những kiểu nhất định; primitive, `String`, `Thread` và `Class` là các kiểu được Javadoc `Event` nêu. Không mặc định mọi custom object/collection sẽ được ghi nguyên vẹn.
- `commit()` không có nghĩa tạo một file riêng; ghi file là một hoạt động **khác** của recording.
- Không ghi bí mật, token, dữ liệu cá nhân nhạy cảm hoặc payload lớn không cần thiết vào JFR.

Có thể dùng pattern:

```java
OrderPlaced e = new OrderPlaced();
if (e.shouldCommit()) {
    e.orderId = 101;
    e.status = calculateDiagnosticStatus();
    e.commit();
}
```

Trong mẫu minh họa này, `calculateDiagnosticStatus()` là tên hàm do ứng dụng giả định có, **không phải API Java/JFR**. Mục đích là để hiểu cách tránh tính toán payload khi sự kiện không cần ghi.

## 4. Ghi bằng `Recording`: thu thập trước, đọc sau

`Recording` quản lý một khoảng ghi được cấu hình rõ:

```text
new Recording()      → trạng thái NEW
recording.start()    → RUNNING
recording.stop()     → STOPPED
recording.dump(path) → dữ liệu đã ghi được xuất ra file .jfr
recording.close()    → giải phóng tài nguyên
```

Các bước thường dùng:

1. Tạo recording (`new Recording()` hoặc dùng `Configuration` như `"default"`).
2. Bật loại sự kiện cần ghi, ví dụ `recording.enable(OrderPlaced.class).withoutThreshold()`.
3. Khi muốn giữ dữ liệu qua disk repository, cấu hình `setToDisk(true)`; có thể giới hạn bằng `setMaxAge(...)` và `setMaxSize(...)`.
4. Gọi `start()`, thực hiện tác vụ ứng dụng, rồi `stop()` nếu muốn kết thúc khoảng ghi.
5. Gọi `dump(Path)` để xuất file `.jfr`, rồi đóng tài nguyên.
6. Đọc bằng `RecordingFile` hoặc dùng công cụ `jfr`/JDK Mission Control.

**Cần tách ba khái niệm:** `stop()` kết thúc thu thập, `dump()` xuất dữ liệu, `close()` giải phóng recording. Đừng cho rằng ba thao tác này là một hoặc rằng `stop` luôn tự tạo file ở đường dẫn bạn muốn.

### 4.1. Chương trình Java độc lập: ghi hai event và đọc lại

Lưu file **`JfrRecordingDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;

public class JfrRecordingDemo {
    @Name("demo.OrderPlaced")
    public static class OrderPlaced extends Event {
        public int orderId;
        public String status;
    }

    static void placeOrder(int id) {
        OrderPlaced event = new OrderPlaced();
        event.orderId = id;
        event.status = "ACCEPTED";
        event.commit();
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("jfr-orders-", ".jfr");

        try {
            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                recording.enable(OrderPlaced.class).withoutThreshold();

                recording.start();
                placeOrder(101);
                placeOrder(102);
                recording.stop();
                recording.dump(file);
            }

            // Đọc file sau khi recording đã kết thúc.
            List<Integer> ids = RecordingFile.readAllEvents(file)
                    .stream()
                    .filter(e -> e.getEventType().getName()
                            .equals("demo.OrderPlaced"))
                    .map(e -> e.getInt("orderId"))
                    .sorted()
                    .toList();

            System.out.println("recorded=" + ids);
            System.out.println("count=" + ids.size());
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch trên JDK 17+ có module `jdk.jfr`:

```bash
javac --release 17 JfrRecordingDemo.java
java JfrRecordingDemo
```

**Stdout dự kiến trên một JDK hỗ trợ JFR và có quyền ghi file:**

```text
recorded=[101, 102]
count=2
```

**Giải thích:**

- `@Name("demo.OrderPlaced")` đặt tên cho loại custom event. Field `orderId` là kiểu số nguyên được hỗ trợ.
- `enable(...).withoutThreshold()` bật event type và bỏ ngưỡng thời lượng đối với recording này, để event rất ngắn cũng có thể được ghi.
- `recording.start()` bắt đầu ghi, rồi `placeOrder` thực hiện hai `commit()`.
- `stop()` kết thúc thu thập; `dump(file)` tạo nội dung file `.jfr` để đọc.
- `RecordingFile.readAllEvents` đọc các events từ file, lọc đúng loại custom event và lấy field bằng `getInt("orderId")`.
- `sorted()` làm kết quả hiển thị ổn định; không phụ thuộc thứ tự những loại event hệ thống có thể được ghi cùng file.
- `finally` xóa file tạm, tránh tích lũy dữ liệu quan sát trên đĩa.

**Cảnh báo dữ liệu lớn:** Javadoc `RecordingFile.readAllEvents` nói phương thức này dành cho trường hợp thuận tiện, **không nên dùng để đọc toàn bộ file rất lớn vào heap**. Với file lớn, dùng `RecordingFile` và duyệt tăng dần bằng `hasMoreEvents()/readEvent()`.

**Đặc tính của chế độ này:** Bạn có **artifact `.jfr`** để phân tích, nhưng consumer chỉ được gọi sau khi file đã có. Đây là **tiêu thụ offline**, không phải callback live.

## 5. Đọc file đã ghi: `RecordingFile` và `EventStream.openFile`

Có hai cách đọc một file `.jfr`:

**Cách A — duyệt tuần tự** bằng `RecordingFile`:

```java
// Code minh họa trong một phương thức có throws Exception.
// File "trace.jfr" phải được tạo trước.
try (var file = new jdk.jfr.consumer.RecordingFile(
        java.nio.file.Path.of("trace.jfr"))) {
    while (file.hasMoreEvents()) {
        var event = file.readEvent();
        if (event.getEventType().getName().equals("jdk.GarbageCollection")) {
            System.out.println(event.getEndTime());
        }
    }
}
```

**Cách B — callback nhưng vẫn offline** bằng `EventStream.openFile`:

```java
// Code minh họa trong một phương thức có throws Exception.
try (var stream = jdk.jfr.consumer.EventStream.openFile(
        java.nio.file.Path.of("trace.jfr"))) {
    stream.onEvent("jdk.GarbageCollection",
                   event -> System.out.println(event.getEndTime()));
    stream.start();
}
```

`EventStream.openFile` đọc file hữu hạn và thường kết thúc khi hết event. **Chữ «stream» ở tên API không biến file tĩnh thành nguồn theo dõi runtime liên tục.**

Hai cách này **không** tạo thêm recording. File phải tồn tại và có dữ liệu đáng tin cậy; Javadoc khuyên chỉ đọc file recording từ nguồn tin cậy.

## 6. Tiêu thụ sự kiện liên tục bằng `EventStream`

`EventStream` là giao diện của một stream sự kiện. Đối tượng consumer đăng ký action:

```java
// Code minh họa trong một phương thức có throws Exception.
try (var stream = jdk.jfr.consumer.EventStream.openRepository()) {
    stream.onEvent("jdk.GarbageCollection", event -> {
        System.out.println("gc-end=" + event.getEndTime());
    });
    stream.start();
}
```

Điều cần hiểu:

- `openRepository()` đọc repository của JVM hiện tại, **không tự bắt đầu recording hoặc bật sự kiện GC**.
- Nếu một recording khác đã ghi event phù hợp, consumer có thể thấy các event đó khi chúng được flush.
- Mặc định, repository stream bắt đầu từ **sự kiện được JFR flush tiếp theo**, không mặc nhiên phát lại mọi event quá khứ.
- `onEvent(name, callback)` chỉ lọc và đăng ký callback, **không thiết lập event settings trên producer**.
- `start()` xử lý callback trên thread hiện tại và có thể block cho đến khi stream đóng.
- `startAsync()` xử lý callback trên thread riêng. Gọi `close()` để dừng stream và giải phóng tài nguyên.
- Đóng `EventStream.openRepository()` không bắt buộc dừng một `Recording` độc lập đã được cấu hình ở chỗ khác.

**Một lỗi điển hình:** Mở repository stream, đăng ký `onEvent("demo.OrderPlaced", ...)` nhưng không có producer/recording nào enable `demo.OrderPlaced`. Kết quả không có callback không đủ để kết luận API hỏng.

### 6.1. Có thể bắt đầu đọc từ một thời điểm cũ hơn không?

`EventStream` có `setStartTime(Instant)` và `setEndTime(Instant)` để chọn khoảng thời gian. Tuy vậy, yêu cầu lấy dữ liệu lịch sử chỉ có ý nghĩa nếu **repository còn giữ** những chunks tương ứng. Retention, việc xoay vòng file và thời điểm recording được bật quyết định dữ liệu có sẵn. Không xem `setStartTime` như một cách tự khôi phục events chưa từng được ghi.

## 7. `RecordingStream`: tự ghi và tự tiêu thụ từ JVM hiện tại

`jdk.jfr.consumer.RecordingStream` kết hợp **recording + event stream** trong JVM đang chạy. Nó implement `EventStream`, bổ sung khả năng chọn event types qua `enable(String)` hoặc `enable(Class<? extends Event>)`.

```text
RecordingStream được tạo
    |
    +--> enable(custom JFR events)
    +--> onEvent(name, callback)
    +--> onError(handler)
    |
    v
startAsync() hoặc start()
    |
    +--> JVM ghi event
    +--> JFR flush events thành batches
    +--> callbacks được gọi khi có event phù hợp
    |
    v
close() qua try-with-resources
```

Khác với `EventStream.openRepository()`, bạn không cần tạo một `Recording` khác chỉ để bắt đầu ghi event của JVM hiện tại.

**Lưu ý:** Gọi `onEvent(...)` không thay thế `enable(...)` khi event chưa được bật. `RecordingStream` tự có recording, nhưng phải cấu hình đúng **loại event** và ngưỡng.

### 7.1. Chương trình Java 17+ chạy được, có timeout

Lưu file **`JfrStreamingDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public class JfrStreamingDemo {
    @Name("demo.Heartbeat")
    public static class Heartbeat extends Event {
        public int sequence;
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch received = new CountDownLatch(1);

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable(Heartbeat.class).withoutThreshold();

            stream.onEvent("demo.Heartbeat", event -> {
                if (event.getInt("sequence") > 0) {
                    received.countDown();
                }
            });
            stream.onError(Throwable::printStackTrace);
            stream.startAsync();

            boolean observed = false;
            for (int i = 1; i <= 50 && !observed; i++) {
                Heartbeat event = new Heartbeat();
                event.sequence = i;
                event.commit();

                // Callback có thể đến sau khi JFR flush một batch.
                observed = received.await(100, TimeUnit.MILLISECONDS);
            }

            System.out.println("callback-observed=" + observed);
            // close() được gọi khi ra khỏi try-with-resources.
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 JfrStreamingDemo.java
java JfrStreamingDemo
```

**Output minh họa khi event được flush và nhận kịp thời:**

```text
callback-observed=true
```

**Đây không phải stdout được bảo đảm trên mọi máy/tải.** Nếu callback chưa có cơ hội xử lý sự kiện trong thời gian chờ hữu hạn, chương trình có thể in `callback-observed=false`. Đây là đặc điểm **asynchronous delivery**, không phải xác nhận rằng mọi JFR event sẽ thất lạc. Chương trình có timeout để tránh treo vô hạn.

Phân tích kỹ:

1. `RecordingStream` tạo recording và consumer trong JVM hiện tại.
2. `stream.enable(Heartbeat.class).withoutThreshold()` bật custom event, không loại những event quá ngắn.
3. `onEvent("demo.Heartbeat", ...)` gắn callback với một loại event. Dữ liệu trong callback là `RecordedEvent`, không phải object `Heartbeat` gốc.
4. `startAsync()` chạy processing ở thread riêng; main thread vẫn có thể tạo `Heartbeat`.
5. `CountDownLatch` giúp hai thread trao đổi tín hiệu an toàn, tránh dùng biến `boolean` thường mà thiếu synchronization.
6. Phát nhiều event thay vì chỉ một giúp giảm rủi ro race khi bắt đầu stream, nhưng **không** biến callback thành lời hứa đúng thời điểm.
7. Try-with-resources luôn `close()` stream, kể cả khi xảy ra ngoại lệ.

**Nếu cần kiểm tra toàn bộ chính xác một khoảng công việc**, dùng `Recording` rồi `stop()/dump()/RecordingFile` thường dễ xác định ranh giới hơn. Nếu cần nhận tín hiệu trong lúc ứng dụng vẫn hoạt động, `RecordingStream` phù hợp hơn.

## 8. Bảng chọn cơ chế đúng

| Nhu cầu | API nên xét | Vì sao |
| --- | --- | --- |
| Muốn lưu lịch sử của một tác vụ để phân tích hôm sau | `Recording` → `dump` → `RecordingFile`/JFR tools | Có file phân tích offline |
| Muốn assert số custom events sau khi tác vụ kết thúc | `Recording` + `RecordingFile` | Có ranh giới stop/dump rõ |
| Muốn callback khi app đang chạy | `RecordingStream` | Kết hợp ghi và tiêu thụ |
| Muốn nghe sự kiện của một recording đã được bật trong JVM | `EventStream.openRepository()` | Consumer không tự sở hữu recording |
| Muốn callback khi đọc một file đã lưu | `EventStream.openFile()` | Callback style, nguồn dữ liệu vẫn là file |
| Muốn bảo đảm giao dịch được lưu đúng một lần, có xác nhận nhận bản tin | Database/transaction log/message broker chuyên dụng | JFR là kênh chẩn đoán, không bảo đảm exactly-once |

**Không nên đánh đồng:** Ghi event vào JFR không phải ghi log văn bản và cũng không phải publish vào message queue. Một sự kiện có thể được sử dụng để quan sát gần thời gian thực, được ghi file hoặc cả hai, tùy cấu hình.

## 9. Khi `commit()` xảy ra, callback đã chạy chưa?

**Chưa chắc.** Javadoc `EventStream` quy định sự kiện được giao theo **batches**; khi JFR flush thì consumer mới có dữ liệu để phân phối.

```text
Producer                  JFR / repository                 Consumer
   |                            |                            |
   | event.commit()             |                            |
   +--------------------------->| buffer / lưu sự kiện       |
   |                            |                            |
   | làm việc tiếp              | flush một batch            |
   |                            +--------------------------->| onEvent()
   |                            |                            | callback xử lý
```

Hệ quả:

- `commit()` không chờ `onEvent` xong.
- Có thể có **độ trễ** từ producer đến callback.
- `onFlush(Runnable)` chạy sau một batch flush, không phải sau mỗi sự kiện riêng lẻ.
- `setOrdered(boolean)` điều chỉnh việc sắp thứ tự; Javadoc mô tả ordering trong batch và giới hạn giữa các batch, **không có bảo đảm thứ tự toàn cục tuyệt đối** khi events chưa sẵn sàng cùng lúc.
- Nếu callback chậm, hệ thống có thể không bắt kịp tốc độ sự kiện; cần giảm chi phí callback và giới hạn lưu trữ.
- Streaming không thay thế hệ thống có ràng buộc delivery, replay và transactional semantics.

### 9.1. `onEvent` và `onFlush` khác nhau

`onEvent("demo.Heartbeat", action)` chạy action theo **event phù hợp** được phân phối.

`onFlush(action)` chạy action **sau một đợt flush**, hữu ích để đẩy số liệu gộp theo batch. Một batch có thể có nhiều events, nên không thể dùng `onFlush` làm bộ đếm sự kiện trực tiếp nếu không chủ động tổng hợp trong các `onEvent` callback trước đó.

### 9.2. Về thời điểm mở repository stream

`EventStream.openRepository()` mặc định bắt đầu từ **event mới được flush tiếp theo**. Nếu consumer khởi động muộn, những sự kiện trước đó không tự được phát lại trừ khi bạn dùng API thời gian bắt đầu thích hợp và dữ liệu vẫn còn trong repository.

Với `RecordingStream`, cấu hình callback và enable **trước khi `start()`/`startAsync()`** để giảm race do đăng ký muộn.

## 10. Quản lý vòng đời và tài nguyên

### 10.1. `Recording`

- `new Recording()` tạo recording ở trạng thái mới.
- `start()` bắt đầu; `stop()` kết thúc. Một recording đã stop không được start lại.
- `dump(path)` xuất nội dung theo điều kiện Javadoc, có thể dump khi recording còn chạy hoặc đã stop nếu đã ghi ra disk đúng cấu hình.
- `setDestination(path)` là lựa chọn khác để ghi file tự động khi stop; đừng trộn lẫn với `dump` mà không nắm vòng đời.
- `setMaxAge(Duration)` và `setMaxSize(long)` giới hạn lịch sử giữ trong disk repository.
- `close()` giải phóng dữ liệu/tài nguyên recording.

### 10.2. `EventStream` và `RecordingStream`

- Đăng ký `onEvent`, `onError`, `onFlush` trước khi start.
- `start()` chạy callbacks ở thread hiện tại và có thể block.
- `startAsync()` chạy callbacks ở thread riêng; cần giữ scope sống đủ lâu.
- `close()` giải phóng stream. Với `RecordingStream`, nó cũng kết thúc recording do stream quản lý.
- Việc đóng `EventStream.openRepository()` **không tự đóng mọi recording độc lập** đang ghi.
- Không đưa mã blocking dài vào callback. Tách sang queue có giới hạn nếu xử lý nặng.

**Chú ý phiên bản:** Một số phương thức mới trên `RecordingStream` có mốc ra đời sau Java 17. Các ví dụ Java 17 của bài chỉ dùng `enable`, `onEvent`, `onError`, `startAsync` và `close`, không sử dụng phương thức yêu cầu JDK mới hơn.

### 10.3. Giới hạn lưu trữ và chi phí

- `setToDisk(true)` giúp `Recording` dùng disk repository; cấu hình này có ảnh hưởng tới khả năng dump/getStream.
- `maxAge` và `maxSize` hạn chế dữ liệu giữ lại; khi quá giới hạn, lịch sử cũ có thể không còn.
- Event có nhiều stack traces, payload lớn hoặc tần suất cao làm tăng overhead.
- Không tự động mở toàn bộ file recording lớn bằng `readAllEvents`; xử lý tuần tự hoặc bằng công cụ phân tích.
- Không giữ vô hạn các `RecordedEvent` trong một list; nên lọc/tổng hợp theo nhu cầu.

**Quan trọng:** Một đoạn `RecordingStream` có callback thành công không chứng minh dữ liệu sẽ được giữ lâu dài. Nếu cần artifact `.jfr`, thiết kế riêng quy trình dump/lưu trữ với chính sách retention.

## 11. Thread safety và `RecordedEvent`

Khi gọi `startAsync()`, callback có thể chạy ở thread riêng. Mọi state chia sẻ với main thread cần visibility/synchronization đúng, chẳng hạn:

- `AtomicInteger` cho bộ đếm;
- `CountDownLatch` hoặc `CompletableFuture` cho tín hiệu hoàn tất;
- Concurrent queue có giới hạn để chuyển payload sang worker chuyên biệt.

`RecordedEvent` mang nội dung đã ghi. Nó **không** phải cùng instance với custom `Event` do producer tạo ra.

Ví dụ:

```java
// Code minh họa trong một method có biến stream.
stream.onEvent("demo.OrderPlaced", recorded -> {
    int id = recorded.getInt("orderId");
    java.time.Instant timestamp = recorded.getEndTime();
    // Đưa dữ liệu id/timestamp vào bộ tổng hợp thread-safe nếu cần.
});
```

Javadoc `EventStream` cho phép cùng một `RecordedEvent` object có thể được **tái sử dụng** khi phân phối. Nếu cần dùng event object **sau callback**, hãy xem `setReuse(false)` hoặc chỉ sao chép những giá trị cần thiết, không giả định object sẽ bất biến/sống độc lập mãi.

**Không lưu dữ liệu diagnostic nhạy cảm quá lâu** chỉ vì callback đã nhận nó: thiết lập giới hạn và quyền truy cập cho cả file, queue và hệ thống metrics.

## 12. Công cụ dòng lệnh JFR

Với một JVM đang chạy, các công cụ của JDK như `jcmd` và `jfr` cho phép điều khiển/đọc recording:

```bash
# Xem những tiến trình JVM có thể thao tác:
jcmd -l

# Dùng PID thực tế của JVM mục tiêu thay cho số minh họa 12345:
jcmd 12345 JFR.start name=app-monitor settings=default
jcmd 12345 JFR.dump name=app-monitor filename=app-monitor.jfr

# Đọc dữ liệu file đã tạo:
jfr summary app-monitor.jfr
jfr print --events jdk.GarbageCollection app-monitor.jfr
```

**Số `12345` chỉ là ví dụ**, phải thay bằng PID của một JVM bạn được phép quản lý. Khả năng sử dụng `jcmd` phụ thuộc quyền attach, toolchain JDK và môi trường triển khai. Không chạy lệnh ở JVM sản xuất mà chưa kiểm tra tác động và quyền quản trị.

- `JFR.start` bắt đầu **recording**.
- `JFR.dump` xuất dữ liệu thành file.
- `jfr summary` / `jfr print` **đọc file offline**.
- `RecordingStream` / `EventStream` là API để **tiêu thụ qua callback** trong code Java.

Không nhầm công cụ `jfr print` với một lời gọi `onEvent` đang theo dõi runtime liên tục.

## 13. Bài toán thực tế

### Trường hợp A — Phân tích sự cố đã xảy ra

Bạn muốn có lịch sử GC/CPU/thread trước và sau lúc ứng dụng chậm. Hãy bật recording phù hợp, có giới hạn lưu, rồi dump dữ liệu và phân tích bằng công cụ JFR.

**Hướng chọn:** Recording + file offline. Lý do: bạn cần *bối cảnh liên tục của một khoảng thời gian* để phân tích sau.

### Trường hợp B — Cập nhật metric khi có GC

`RecordingStream` cho phép đăng ký event hệ thống:

```java
// Code minh họa trong phương thức có throws Exception.
try (var stream = new jdk.jfr.consumer.RecordingStream()) {
    stream.enable("jdk.GarbageCollection");
    stream.onEvent("jdk.GarbageCollection", event -> {
        System.out.println("gc-end=" + event.getEndTime());
    });
    stream.startAsync();
    Thread.sleep(5_000);
}
```

Output phụ thuộc workload và cấu hình JVM: có thể **không** có sự kiện GC trong năm giây. Không hứa callback GC sẽ xuất hiện theo lịch cố định và không dùng `System.gc()` như một cam kết GC phải xảy ra.

### Trường hợp C — Đếm chính xác custom events trong một test tích hợp

Muốn xác nhận tác vụ phát sinh đúng hai `demo.OrderPlaced`, dùng `Recording`, enable đúng event type, thực thi tác vụ, stop/dump, đọc file rồi assert số lượng. Một stream có timeout có thể phục vụ integration test riêng, nhưng không nên dùng timing ngẫu nhiên làm tiêu chí duy nhất cho correctness của producer.

### Trường hợp D — Quan sát một recording đã được bật sẵn

Nếu một thành phần khác đang quản lý vòng đời recording, consumer có thể dùng `EventStream.openRepository()`. Chú ý quyền truy cập repository, event settings và thời điểm stream bắt đầu.

## 14. Sai lầm phổ biến và cách khắc phục

| Sai lầm | Vì sao không đúng | Cách khắc phục |
| --- | --- | --- |
| Nghĩ `commit()` đồng nghĩa callback đã chạy | Producer và consumer qua batching/flush | Test riêng việc ghi và việc nhận stream |
| Tưởng tạo `Recording` là tự in sự kiện liên tục | `Recording` không đăng ký `onEvent` | Dùng `RecordingStream` hoặc consumer khác |
| Tưởng `onEvent` tự enable event | Nó chỉ đăng ký callback | Cấu hình `enable` trên recording/RecordingStream |
| Dùng `EventStream.openRepository` khi không có recording | Không có nguồn dữ liệu phù hợp để nhận | Bắt đầu một recording phù hợp hoặc dùng RecordingStream |
| Nghĩ `EventStream.openFile` là realtime | Nó đọc file hữu hạn | Dùng repository stream hoặc RecordingStream để quan sát live |
| `startAsync()` rồi đóng ngay | Callback chưa kịp nhận flush | Giữ stream sống, dùng timeout/synchronization |
| Dùng `start()` trên main thread rồi chờ code phía sau chạy ngay | `start()` có thể block | Dùng async hoặc đóng stream từ đường điều khiển khác |
| Tin mọi event đều được nhận đúng một lần | JFR không là message broker có exactly-once | Dùng hệ thống transactional khi cần |
| Đọc `.jfr` khổng lồ bằng `readAllEvents` | Có thể chiếm nhiều heap | Duyệt từng event với RecordingFile |
| Giả định thứ tự tuyệt đối giữa mọi batch | Stream có giới hạn ordering | Tổng hợp không phụ thuộc thứ tự toàn cục |
| Giữ raw `RecordedEvent` sau callback | Object có thể được reuse | `setReuse(false)` hoặc copy field cần thiết |
| Bỏ qua cấu hình retention | Có thể hết dung lượng hoặc mất lịch sử | Cấu hình maxAge/maxSize, vòng đời file |
| Ghi bí mật vào JFR event | File/callback có thể tiết lộ thông tin | Thiết kế event schema tối thiểu và quyền truy cập |

## 15. Lưu ý bảo mật, hiệu năng và môi trường

JFR có ích ở production nhưng vẫn cần chính sách:

- **Bảo mật:** Nội dung event có thể có tên class, thread, stack trace, đường dẫn, địa chỉ và custom fields. Hạn chế dữ liệu nhạy cảm; chỉ cho phép đọc file/repository trong phạm vi được cấp quyền.
- **Hiệu năng:** Chọn những event thực sự cần, hạn chế tần suất, stack trace và chi phí payload. Dùng `shouldCommit()` khi bước tạo payload đắt đỏ.
- **Callback:** Xử lý nhanh, tránh network call nặng hoặc I/O chậm trực tiếp trên streaming thread; nếu cần, chuyển payload rút gọn sang queue có giới hạn.
- **Dung lượng:** Giới hạn lưu `maxAge/maxSize`, quy định thời hạn giữ file `.jfr` và cách xóa.
- **Khả năng triển khai:** Runtime tạo riêng có thể không gồm module `jdk.jfr`; JFR có thể không hoạt động do quyền ghi repository hoặc hạn chế JVM. Kiểm tra môi trường trước khi vận hành.
- **Độ tin cậy:** JFR ưu tiên quan sát/chẩn đoán, không phải cơ sở dữ liệu giao dịch có xác nhận delivery và replay không mất dữ liệu.

**Không dùng JFR để lưu dữ liệu định danh người dùng hay giao dịch bắt buộc chính xác chỉ vì việc emit event rất tiện.** Tách hệ thống quan sát khỏi hệ thống lưu trữ nghiệp vụ.

## 16. Checklist để review mã JFR

1. **Mục tiêu:** cần lịch sử file hay tín hiệu liên tục? Có cần file artifact để phân tích sau không?
2. **Event schema:** tên event, field types, dữ liệu nhạy cảm và chi phí tính payload có hợp lý?
3. **Producer settings:** event đã enable chưa, threshold/period đúng chưa?
4. **Nguồn consumer:** file, repository hay recording do RecordingStream tự tạo?
5. **Lifecycle:** start/stop/dump/close đúng chỗ, có try-with-resources không?
6. **Async:** callback có được đăng ký trước khi start, main thread có chờ hoặc đóng quá sớm không?
7. **Test:** kết quả offline được kiểm chứng bằng stop/dump/read file; streaming có timeout hợp lý.
8. **Batching:** người dùng có hiểu callback không tức thời, `onFlush` khác `onEvent`?
9. **Retention:** chính sách maxAge/maxSize và xóa file có rõ ràng?
10. **Thread safety:** callback có sửa state chia sẻ đúng kỹ thuật? Có giữ `RecordedEvent` quá lâu?
11. **Vận hành:** JDK cung cấp module `jdk.jfr`, quyền repository và công cụ JFR ở môi trường đích?
12. **Giới hạn tin cậy:** nếu cần exactly-once hoặc lưu vĩnh viễn, cơ chế khác đã chịu trách nhiệm chưa?

## 17. Câu hỏi tự kiểm tra

**Câu 1 — Chọn đúng API:** Cần ghi một khoảng 30 giây rồi gửi file `.jfr` cho người phân tích sau.

**Đáp án:** `Recording` + `dump(Path)`, đọc bằng `RecordingFile` hoặc công cụ JFR. Không cần `onEvent` trực tiếp.

**Câu 2 — Lý do không thấy callback:** Đã gọi `EventStream.openRepository()` và `onEvent("demo.OrderPlaced", ...)`, nhưng không thấy event.

**Đáp án:** Stream chỉ tiêu thụ repository; cần recording đang bật và enable đúng loại sự kiện, có dữ liệu flush, stream đang chạy và retention phù hợp.

**Câu 3 — `commit()` có chờ callback không?**

**Đáp án:** Không. JFR ghi/đệm event, rồi consumer nhận theo batch/flush; một commit không xác nhận callback đã hoàn tất.

**Câu 4 — `RecordingStream` khác `Recording` thế nào?**

**Đáp án:** `Recording` phục vụ cấu hình/thu thập và xuất dữ liệu; `RecordingStream` vừa tạo recording trong JVM hiện tại, vừa phân phối event cho callback.

**Câu 5 — Dùng `EventStream.openFile` để giám sát app realtime được không?**

**Đáp án:** Nó tiêu thụ file đã có, không tự khởi tạo recording đang chạy. Để giám sát live, dùng repository stream với recording đang hoạt động hoặc `RecordingStream`.

**Câu 6 — Vì sao cần `CountDownLatch` trong ví dụ async?**

**Đáp án:** Callback chạy ở thread riêng. Latch cho phép main thread chờ tín hiệu một cách thread-safe, tránh race của biến thường.

**Câu 7 — `RecordingFile.readAllEvents` có phù hợp với file rất lớn không?**

**Đáp án:** Không nên; nó đọc toàn bộ vào `List`. Dùng `RecordingFile` duyệt tuần tự hoặc công cụ phân tích chuyên dụng.

**Câu 8 — JFR có phải message queue bền vững không?**

**Đáp án:** Không. Đây là hệ thống chẩn đoán. Không nên dựa vào nó để thực hiện nghiệp vụ cần exactly-once, xác nhận nhận bản tin hoặc replay không mất sự kiện.

**Câu 9 — Muốn một callback mỗi khi `commit()` thực thi, có làm được bằng JFR không?**

**Đáp án:** Không có cam kết như lời gọi hàm đồng bộ. Callback chỉ đến khi event được ghi và stream nhận sau flush; tốc độ, cấu hình và retention đều ảnh hưởng.

**Câu 10 — Phân biệt `RecordedEvent` với custom `Event`:**

**Đáp án:** Custom `Event` do producer tạo và commit; `RecordedEvent` là dữ liệu được consumer giải mã. Không phải cùng một Java object.

## 18. Tài liệu chính thức còn áp dụng

1. [Java SE 25 — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html): start/stop, dump, disk, maxAge, maxSize và vòng đời recording.
2. [Java SE 25 — `jdk.jfr.Event`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Event.html): custom events, commit, shouldCommit, supported fields.
3. [Java SE 25 — `jdk.jfr.consumer.RecordingStream`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): vừa ghi vừa stream từ JVM hiện tại, callback và startAsync.
4. [Java SE 25 — `jdk.jfr.consumer.EventStream`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): onEvent, onFlush, openRepository, openFile, batch, ordering và reuse.
5. [Java SE 25 — `jdk.jfr.consumer.RecordingFile`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): duyệt/đọc dữ liệu từ file; cảnh báo với `readAllEvents`.
6. [Java SE 25 — `jdk.jfr.EventSettings`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): withoutThreshold, withThreshold và các setting.
7. [Java SE 17 — `RecordingStream`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): đối chiếu API trên `--release 17`.
8. [JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): streaming được đưa vào Java 14, tiếp tục là API ổn định.
9. [Java SE 25 — package `jdk.jfr.consumer`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/package-summary.html): tổng quan tiêu thụ dữ liệu JFR.

**Ghi nhớ:** `Event.commit()` phát sinh event; `Recording` thu thập và lưu một recording; `RecordingFile` đọc file offline; `EventStream` tiêu thụ từ file/repository; `RecordingStream` kết hợp recording và streaming trong JVM hiện tại. Ghi và tiêu thụ có thể chạy đồng thời, nhưng **không đồng bộ từng event**, vì JFR áp dụng batch/flush và retention.