# Mở luồng từ repository của JVM hiện tại bằng EventStream.openRepository()

## 1. Bài toán và kết quả cần đạt

**Java Flight Recorder (JFR)** ghi nhận các sự kiện liên quan đến hoạt động JVM và ứng dụng: tải CPU, cấp phát bộ nhớ, garbage collection, I/O, lock contention hoặc các sự kiện do lập trình viên tự định nghĩa. Nếu muốn **xử lý sự kiện ngay khi JFR chuyển chúng thành các lô dữ liệu có thể đọc** mà không cần chờ xuất một file `.jfr` hoàn chỉnh, bạn có thể sử dụng API **`jdk.jfr.consumer.EventStream`**.

Chủ đề của bài này là chính xác một factory method:

~~~java
EventStream.openRepository()
~~~

Phương thức **không có tham số** này tạo một luồng đọc sự kiện từ **disk repository của JVM hiện tại** — tức JVM đang thực thi lời gọi. Bạn không cần biết đường dẫn thư mục repository và không truyền tên recording. Sau khi mở stream, bạn đăng ký callback bằng `onEvent(...)`, rồi gọi `start()` hoặc `startAsync()` để xử lý dữ liệu.

**Phân biệt ngay từ đầu:** mở luồng **không đồng nghĩa bắt đầu một recording có các event settings mong muốn**. Muốn bảo đảm custom event được ghi, bạn phải có một recording đang hoạt động với sự kiện đó được bật và chế độ ghi vào repository phù hợp, hoặc chọn `RecordingStream` nếu muốn chính consumer vừa quản lý recording vừa đọc sự kiện.

`EventStream` được giới thiệu từ **Java 14** và tiếp tục hiện diện trong các API Java hiện đại. Các ví dụ dùng **Java 17+** ổn định, không dựa vào preview, flags mở khóa thương mại hay cách làm legacy.

## 2. Recording, repository, EventStream và RecordedEvent khác nhau thế nào?

| Khái niệm | Vai trò | Điều không nên nhầm |
|---|---|---|
| **JFR recording** | Phiên ghi logic với danh sách sự kiện được bật, chính sách dữ liệu và vòng đời start/stop | Không phải chính luồng callback |
| **Disk repository** | Nơi JVM/JFR quản lý dữ liệu recording trên đĩa dưới dạng các chunk | Không phải file xuất `.jfr` đã được đặt tên |
| **EventStream** | Giao diện đăng ký callback và tiêu thụ sự kiện từ repository hoặc file | Không mặc nhiên bật sự kiện hay tự tạo recording phù hợp với nhu cầu |
| **RecordedEvent** | Đối tượng mô tả một event đã được JFR ghi và consumer nhận | Không phải subclass `jdk.jfr.Event` được dùng để phát sinh custom event |
| **RecordingStream** | Consumer gắn với việc tạo/quản lý recording trên JVM hiện tại | Khác với `EventStream.openRepository()` chỉ đọc repository |
| **RecordingFile** | API đọc trực tiếp file recording `.jfr` đã tạo | Không phải API stream live từ repository |

Luồng hoạt động điển hình:

~~~text
   Ứng dụng / JVM tạo sự kiện
               |
               v
       JFR recording đang chạy
         (disk=true, event enabled)
               |
               v
        JFR buffers / flush
               |
               v
      Repository của JVM hiện tại
       (các chunk do JFR quản lý)
               |
               v
     EventStream.openRepository()
               |
        onEvent / onFlush
               |
               v
     Callback xử lý RecordedEvent
~~~

Sơ đồ này mô tả **luồng dữ liệu logic**, không phải bảo đảm rằng mỗi `commit()` làm callback được gọi ngay lập tức. JFR thường chuyển dữ liệu theo **batch/flush**; độ trễ nhận sự kiện phụ thuộc tình trạng recording, bộ đệm, I/O và lịch flush.

Điều quan trọng: phương thức không tham số mở **repository của chính tiến trình JVM**, không phải repository của mọi Java process trên máy. Nếu muốn mở repository khác bằng đường dẫn, dùng overload `openRepository(Path)` có chủ đích và thận trọng về dữ liệu đáng tin cậy.

## 3. Chữ ký API và điều kiện tiên quyết

Trong module `jdk.jfr` và package `jdk.jfr.consumer`:

~~~java
import jdk.jfr.consumer.EventStream;

EventStream stream = EventStream.openRepository();
~~~

`openRepository()` là phương thức `static` trả về `EventStream` và khai báo `throws IOException`. Vì vậy trong code thực tế phải khai báo ngoại lệ hoặc xử lý `IOException`. Java 17 API cũng liệt kê `SecurityException` cho các môi trường có security manager áp dụng quyền JFR; đây là thông tin hợp đồng API, **không phải khuyến nghị sử dụng security manager mới**.

Các điều kiện thực tế:

1. Chạy trên một **JDK/JVM có JFR**, với module `jdk.jfr` khả dụng. Nếu sử dụng module descriptor `module-info.java`, khai báo `requires jdk.jfr;`.
2. JVM phải có các sự kiện được ghi vào repository nếu muốn consumer có gì để đọc. Stream mở thành công không bảo đảm sẽ có event ngay.
3. Với custom event, recording phải **enable** loại event đó và chạy đủ lâu để dữ liệu được flush. Một `Recording` cấu hình `setToDisk(true)` là phương án minh họa phù hợp.
4. Chương trình cần quyền truy cập repository theo điều kiện môi trường và quyền filesystem.
5. Chuẩn bị cơ chế **đóng stream** vì đọc live có thể chạy vô thời hạn.

Nếu cần chỉ đọc dữ liệu đã được xuất thành file, không dùng `openRepository()` rồi tự đoán vị trí file: API dành cho việc đó là `EventStream.openFile(Path)` hoặc `RecordingFile`.

### Ví dụ tối giản về vòng đời

~~~java
import jdk.jfr.consumer.EventStream;

try (EventStream stream = EventStream.openRepository()) {
    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(event.getEndTime());
    });
    stream.start(); // chặn thread hiện tại, thường chạy cho tới khi đóng
}
~~~

Đoạn này là **mảnh code đặt trong một phương thức có xử lý IOException**; nó không tự tạo recording bật `jdk.CPULoad`. Nếu repository không có những sự kiện cần tìm, callback có thể không chạy dù cú pháp đúng.

## 4. Cách đăng ký callback và bắt đầu tiêu thụ

### 4.1. Chỉ nhận một loại sự kiện

~~~java
stream.onEvent("jdk.GarbageCollection", event -> {
    System.out.println(event.getEndTime());
});
~~~

`onEvent(String, Consumer<RecordedEvent>)` lọc theo **tên event đầy đủ**. Nếu tên không khớp event được ghi vào repository, callback không nhận sự kiện. Đoạn trên cần biến `EventStream stream` đã mở và một bối cảnh xử lý phù hợp.

### 4.2. Nhận tất cả các loại sự kiện

~~~java
stream.onEvent(event -> {
    System.out.println(event.getEventType().getName());
});
~~~

Dạng một đối số nhận mọi event và có thể tạo lượng xử lý rất lớn. Trong ứng dụng production, ưu tiên lọc tên event, tránh in từng event liên tục và áp dụng giới hạn tốc độ/logging.

### 4.3. Đăng ký onFlush và onError

~~~java
stream.onFlush(() -> {
    // Có thể gom số liệu khi một batch flush hoàn tất.
});
stream.onError(error -> {
    System.err.println("JFR stream error: " + error);
});
~~~

`onFlush(Runnable)` chạy khi hoàn tất một đợt flush, hữu ích để gộp thống kê theo batch. `onError(Consumer<Throwable>)` xử lý lỗi phát sinh trong callback; nếu không khai báo handler, mặc định exception có thể được in kèm stack trace ra stderr. Trong code vận hành thực tế, lỗi nghiêm trọng phải có chiến lược báo và dừng rõ ràng, không chỉ log rồi bỏ qua mọi thứ.

### 4.4. start() hay startAsync()?

| Phương thức | Hành vi | Khi nên dùng |
|---|---|---|
| `start()` | Xử lý callback trong **thread hiện tại** và chặn tại lời gọi | Worker thread dành riêng cho stream |
| `startAsync()` | Bắt đầu xử lý trong thread khác, trả về để caller tiếp tục | Ứng dụng cần vừa phát sinh công việc vừa nhận sự kiện |
| `awaitTermination()` | Chờ đến khi callback hoàn tất, stream đóng hoặc thread bị ngắt theo hợp đồng API | Đồng bộ quá trình kết thúc |
| `awaitTermination(Duration)` | Giới hạn thời gian chờ | Shutdown có timeout |
| `close()` | Đóng stream và giải phóng tài nguyên | Đường dừng chủ động hoặc try-with-resources |

**Quan trọng:** `close()` không cam kết tất cả callback đã hoàn thành trước khi nó trả về. Nếu ứng dụng cần đảm bảo xử lý xong một tập dữ liệu, cần thiết kế cơ chế đồng bộ, điều kiện hoàn thành và xử lý lỗi riêng.

### 4.5. Thời điểm phải đăng ký callback

Hãy cấu hình `onEvent`, `onFlush`, `onError`, `setStartTime` và các tùy chọn của stream **trước khi gọi `start()/startAsync()`**. Các cấu hình giới hạn thời gian như `setStartTime` và `setEndTime` phải được thiết lập trước khi stream bắt đầu.

Mẫu dễ đọc:

~~~java
try (EventStream stream = EventStream.openRepository()) {
    stream.onEvent("demo.MyEvent", event -> process(event));
    stream.onError(error -> report(error));
    stream.startAsync();
    // Chạy phần việc khác; sau đó đóng stream ở thời điểm phù hợp.
}
~~~

Đoạn này là **minh họa**: `process` và `report` phải được định nghĩa. Nếu khối `try` kết thúc ngay sau `startAsync()`, stream sẽ bị đóng quá sớm và có thể chưa nhận được bất kỳ sự kiện nào. Trong chương trình live thật, phải giữ stream tồn tại khi còn cần quan sát.

## 5. Mặc định đọc từ sự kiện được flush tiếp theo

Tài liệu `EventStream.openRepository()` nêu rõ: **mặc định stream bắt đầu với sự kiện được Flight Recorder flush tiếp theo**, không tự động phát lại toàn bộ lịch sử repository từ lúc JVM khởi chạy.

Điều đó kéo theo:

- Một event đã xuất hiện trước thời điểm đọc nhưng không nằm trong khoảng bắt đầu mặc định có thể không được callback nhận.
- Với live monitoring, hành vi đọc “từ tiếp theo” thường phù hợp: không cần quét lịch sử cũ.
- Nếu cần đọc dữ liệu cũ hơn **mà vẫn còn được giữ trong repository**, có thể dùng `stream.setStartTime(Instant)` **trước `start()`**.
- `setStartTime(Instant.EPOCH)` không phải lời hứa có thể khôi phục mọi event kể từ khi JVM được tạo. Các chunk cũ có thể đã bị retention xóa hoặc chưa từng được lưu lên đĩa.
- `setEndTime(Instant)` có thể xác định thời điểm stream kết thúc theo mốc thời gian sự kiện.

Ví dụ chọn mốc thời gian:

~~~java
import java.time.Instant;
import java.time.Duration;

Instant since = Instant.now().minus(Duration.ofMinutes(1));
stream.setStartTime(since);
~~~

Đoạn này minh họa khi biến `stream` đã mở và chưa chạy. Tùy repository thực tế, có thể nhận một phần sự kiện trong một phút vừa qua hoặc không có sự kiện nào. Dùng `Instant.EPOCH` để yêu cầu sớm nhất có thể trong repository sẽ làm tăng chi phí đọc nếu dữ liệu lịch sử lớn.

### Batch ordering và thời gian sự kiện

JFR giao event cho stream **theo lô**. Trong một batch, các event được sắp theo thời điểm kết thúc; nhưng những event ở các batch khác nhau không được bảo đảm thành một chuỗi thời gian toàn cục hoàn hảo. API có `setOrdered(boolean)` để điều chỉnh sắp xếp, đổi lại có thể ảnh hưởng hiệu năng.

Không dùng thứ tự callback như một bằng chứng tuyệt đối về thứ tự các hành động trên nhiều thread. Khi cần phân tích trình tự, hãy lưu **timestamp**, loại event và những trường định danh thích hợp.

## 6. Ví dụ Java 17+ hoàn chỉnh: mở repository JVM hiện tại

Ví dụ dưới đây chứng minh đúng trọng tâm của bài:

1. Tạo một **JFR recording ghi đĩa** trong JVM hiện tại.
2. Bật một **custom JFR event** với tên rõ ràng.
3. Mở stream bằng **`EventStream.openRepository()` không tham số**.
4. Đăng ký callback và bắt đầu đọc bất đồng bộ.
5. Phát sinh custom event, chờ trong một thời gian có giới hạn, đọc dữ liệu từ `RecordedEvent`.
6. Đóng stream/recording đúng vòng đời.

Tạo file **`CurrentJvmRepositoryDemo.java`**:

~~~java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.EventStream;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CurrentJvmRepositoryDemo {

    @Name("demo.CurrentPulse")
    @Label("Current JVM Pulse")
    static class Pulse extends Event {
        @Label("Sequence")
        int sequence;
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch received = new CountDownLatch(1);
        AtomicInteger observedSequence = new AtomicInteger(-1);

        try (Recording recording = new Recording()) {
            recording.setName("local-jfr-demo");
            recording.setToDisk(true);
            recording.enable(Pulse.class)
                    .withThreshold(Duration.ZERO)
                    .withoutStackTrace();
            recording.start();

            try (EventStream stream = EventStream.openRepository()) {
                stream.onEvent("demo.CurrentPulse", event -> {
                    int value = event.getInt("sequence");
                    if (value == 42) {
                        observedSequence.set(value);
                        received.countDown();
                    }
                });

                stream.onError(error ->
                        System.err.println(
                                "JFR stream error: " + error
                        )
                );

                stream.startAsync();

                Pulse pulse = new Pulse();
                pulse.sequence = 42;
                pulse.commit();

                boolean delivered =
                        received.await(15, TimeUnit.SECONDS);

                System.out.println("repository-opened=true");
                System.out.println(
                        "recording-to-disk=" + recording.isToDisk()
                );
                System.out.println("event-committed=true");
                System.out.println("event-received=" + delivered);
                if (delivered) {
                    System.out.println(
                            "sequence=" + observedSequence.get()
                    );
                }
            }

            recording.stop();
        }
    }
}
~~~

Chạy với JDK 17 trở lên (JFR khả dụng):

~~~bash
javac --release 17 CurrentJvmRepositoryDemo.java
java CurrentJvmRepositoryDemo
~~~

**Kết quả mẫu khi event đã được flush và callback nhận trong 15 giây:**

~~~text
repository-opened=true
recording-to-disk=true
event-committed=true
event-received=true
sequence=42
~~~

**Đây là output điều kiện, không phải cam kết thời gian flush.** Trên JVM quá chậm, cấu hình JFR bị hạn chế hoặc repository có vấn đề, việc chờ có thể hết 15 giây. Nếu không nhận được callback trước timeout, chương trình in:

~~~text
repository-opened=true
recording-to-disk=true
event-committed=true
event-received=false
~~~

Không có dòng `sequence=42` trong trường hợp này. Điều đó phản ánh **timeout quan sát**, không chứng minh `pulse.commit()` thất bại; event có thể còn trong buffer/chưa được flush đúng lúc hoặc có vấn đề cấu hình. Nếu có lỗi IO/JFR, chương trình có thể ném ngoại lệ hay in thông báo ở stderr thay vì một trong hai output bình thường.

### Vì sao ví dụ có hai try-with-resources?

- `Recording` quản lý **việc phát sinh/ghi** event. Chúng ta bật `disk=true` và event `demo.CurrentPulse` để tạo điều kiện cho repository có dữ liệu.
- `EventStream` chỉ **đọc** repository. Nó không cần biết tên recording và không giữ đối tượng `Pulse` sau khi `commit()`.
- `EventStream` được đóng ở cuối block bên trong để ngừng consumer; sau đó recording được stop rồi đóng.
- Không tạo file `.jfr` vì bài toán là **live streaming trong cùng JVM**, không phải dump recording ra file.

### Vì sao dùng CountDownLatch và AtomicInteger?

Callback chạy trên thread do `startAsync()` tạo ra, khác thread của `main`. `CountDownLatch` cho phép thread chính chờ với timeout; `AtomicInteger` dùng để trao đổi số thứ tự một cách an toàn giữa các thread. Nếu bạn giữ tham chiếu trực tiếp đến `RecordedEvent` để dùng sau callback, xem thêm `setReuse(false)` ở mục sau; ở ví dụ này callback chỉ đọc dữ liệu ngay rồi lưu một số nguyên.

### Vì sao không in timestamp, số chunk hoặc độ trễ cụ thể?

Những số đó phụ thuộc nhịp flush, tải máy, lựa chọn sự kiện và lịch xử lý. Việc bịa một dòng stdout có timestamp cố định sẽ gây hiểu sai. Ví dụ dùng một custom event cố định `sequence=42` để người học tập trung vào khả năng đọc **dữ liệu của event đã được commit và flush**.

## 7. Ba factory method dễ nhầm nhất

`EventStream` có ba phương thức tạo stream quan trọng:

| Factory | Nguồn dữ liệu | Ngữ nghĩa |
|---|---|---|
| `EventStream.openRepository()` | Repository của **JVM hiện tại** | Đọc live, mặc định từ event được flush tiếp theo |
| `EventStream.openRepository(Path directory)` | Một **disk repository được chỉ rõ** | Đọc repository theo đường dẫn; chỉ mở repository đáng tin cậy |
| `EventStream.openFile(Path file)` | Một **recording file `.jfr` đã tồn tại** | Đọc file; mặc định bắt đầu từ event đầu tiên trong file |

### Không thay openRepository bằng openFile

Nếu đã có file dump ở đường dẫn:

~~~java
import java.nio.file.Path;
import jdk.jfr.consumer.EventStream;

try (EventStream stream =
        EventStream.openFile(Path.of("capture.jfr"))) {
    stream.onEvent(event ->
            System.out.println(event.getEventType().getName())
    );
    stream.start();
}
~~~

Đây là đoạn minh họa trong phương thức có xử lý `IOException`, chạy khi file tồn tại và hợp lệ. Nó phù hợp để phân tích **dữ liệu đã kết thúc/đã xuất**. Ngược lại, `openRepository()` dùng khi bạn cần các batch dữ liệu của JVM hiện tại mà không biết tên file dump.

### openRepository(Path) không tương đương file .jfr

~~~java
EventStream stream =
        EventStream.openRepository(Path.of("/var/tmp/jfr-repo"));
~~~

Đoạn minh họa trên cần xử lý `IOException` và import `Path`, `EventStream`. `Path` phải trỏ tới **thư mục repository JFR**, không phải một file `.jfr`. API khuyến nghị chỉ mở **repository đáng tin cậy**, vì đọc dữ liệu không tin cậy có nguy cơ an toàn và ổn định ứng dụng. Không tự suy luận cấu trúc thư mục repository từ tên các file ngẫu nhiên khi JVM đang chạy.

## 8. Khi nào nên dùng RecordingStream thay cho EventStream.openRepository?

`RecordingStream` là một class triển khai `EventStream`. Nó cho phép **vừa cấu hình sự kiện cần thu thập, vừa nhận callback** trong cùng một abstraction. Nếu ứng dụng muốn theo dõi sự kiện của **chính JVM hiện tại** và chưa có recording hoạt động, đây thường là lựa chọn đơn giản hơn.

Ví dụ Java 17 minh họa (đặt trong phương thức có xử lý `InterruptedException` nếu cần):

~~~java
import jdk.jfr.consumer.RecordingStream;
import java.time.Duration;

try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad")
            .withPeriod(Duration.ofSeconds(1));
    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(event.getFloat("machineTotal"));
    });
    stream.startAsync();
    Thread.sleep(3_000);
}
~~~

Đoạn này không phải chương trình độc lập và **không có stdout cố định** vì số lượng/giá trị sự kiện `jdk.CPULoad` phụ thuộc JVM/máy. Khi khối `try` kết thúc, stream được đóng. Không tạo một `Recording` tường minh riêng.

**Chọn đúng công cụ:**

- Dùng **`EventStream.openRepository()`** khi bạn muốn **tiêu thụ những sự kiện JFR đã được recording khác thu thập vào repository JVM hiện tại**.
- Dùng **`RecordingStream`** khi bạn muốn chính luồng này **quản lý việc thu thập**, bật event settings và streaming trong một chỗ.
- Dùng **`EventStream.openFile(Path)`** để đọc một file `.jfr` đã có.
- Với **JVM khác hoặc container khác**, đừng gọi `openRepository()` và mong nó tự attach sang JVM đó. Cần thiết kế kết nối/cơ chế truy cập khác, hoặc xuất/đọc file với quyền phù hợp.

## 9. Vòng đời stream: onFlush, onClose, onError và shutdown

### onFlush: cơ hội xử lý theo batch

~~~java
stream.onFlush(() -> {
    // Công bố số liệu tổng hợp của batch hiện tại.
});
~~~

JFR gửi các event theo batch. Callback `onFlush` thích hợp để gom/công bố metric khi kết thúc một lượt flush. Nếu ứng dụng muốn phân tích thứ tự sự kiện, hãy nhớ rằng **trong một batch** event được sắp theo thời điểm kết thúc, nhưng không có bảo đảm thứ tự toàn cục hoàn hảo qua nhiều batch. Nếu không cần sorting, `setOrdered(false)` có thể giảm chi phí xử lý.

### onError: có handler để nhận lỗi callback

~~~java
stream.onError(error -> {
    System.err.println("Problem consuming JFR: " + error);
});
~~~

Nếu callback `onEvent` ném ngoại lệ không được xử lý, handler có thể được gọi. Đừng để callback làm công việc blocking dài hay có nguy cơ treo, vì nó làm chậm consumer; nên có queue có giới hạn và worker xử lý riêng nếu cần.

### onClose và kết thúc an toàn

~~~java
stream.onClose(() -> {
    System.out.println("JFR event stream closed");
});
~~~

`onClose` được gọi khi stream đóng, kể cả khi đóng do lỗi/điều kiện kết thúc. Cần tránh làm quá nhiều công việc trong handler. Đóng stream nhiều lần không gây yêu cầu phải dọn lại tài nguyên nhiều lần.

Nếu dùng `startAsync()`, một chiến lược shutdown thường gồm: **ngừng phát sinh nhu cầu theo dõi → đóng stream → chờ callback/worker riêng hoàn tất có timeout**. Đừng tuyên bố `close()` đồng bộ chờ mọi callback xong: Java API nói rõ điều đó **không được bảo đảm**.

## 10. Vấn đề reuse của RecordedEvent

Một chi tiết dễ gây lỗi: theo Java 17 API, **mặc định cùng một đối tượng `RecordedEvent` có thể được tái sử dụng để biểu diễn nhiều sự kiện**. Nếu callback lưu tham chiếu `event` vào danh sách để xử lý sau mà không thay đổi cấu hình, giá trị của tham chiếu đó có thể không còn đại diện cho sự kiện ban đầu khi xử lý về sau.

Có hai lựa chọn:

1. **Đọc/trích xuất dữ liệu cần thiết ngay trong callback**, chẳng hạn `getInt("sequence")` hoặc `getEndTime()` rồi lưu kiểu dữ liệu bất biến/giá trị. Cách này thường tiết kiệm bộ nhớ.
2. Nếu thật sự cần giữ nguyên đối tượng `RecordedEvent` sau khi callback kết thúc, gọi **`stream.setReuse(false)` trước `start()`** để tạo đối tượng mới cho mỗi event, chấp nhận chi phí cấp phát bổ sung.

Ví dụ (minh họa):

~~~java
stream.setReuse(false);
stream.onEvent("demo.CurrentPulse", event -> {
    // Có thể giữ tham chiếu event để dùng sau callback.
    queue.offer(event);
});
~~~

`queue` phải là cấu trúc thread-safe được định nghĩa trong ứng dụng, có chính sách giới hạn kích thước và xử lý quá tải. Chỉ gọi `setReuse(false)` không tự giải quyết vấn đề bộ nhớ tăng khi consumer nhận quá nhiều event mà downstream không theo kịp.

## 11. Xử lý sự kiện và đồng thời: tránh hai lỗi thường gặp

### 11.1. Không đóng stream ngay sau startAsync

**Sai về ý định, dù hợp lệ về cú pháp:**

~~~java
try (EventStream stream = EventStream.openRepository()) {
    stream.onEvent("demo.CurrentPulse", event ->
            System.out.println(event.getInt("sequence"))
    );
    stream.startAsync();
} // Đóng ngay: chưa cho stream thời gian nhận flush.
~~~

Đây là đoạn minh họa trong phương thức có xử lý IOException. `startAsync()` trả về ngay, nên scope ngắn có thể đóng stream trước khi batch event đến. Cần giữ stream còn sống trong thời gian quan sát hoặc dùng cơ chế chờ/điều kiện dừng phù hợp.

### 11.2. Không đọc dữ liệu runtime mà không có recording/event tương ứng

**Không đảm bảo có callback:**

~~~java
try (EventStream stream = EventStream.openRepository()) {
    stream.onEvent("my.company.MissingEvent", event ->
            System.out.println(event)
    );
    stream.start();
}
~~~

Nếu không có recording bật loại sự kiện đó, chương trình có thể chờ mãi. Điều này **không phải lỗi của `openRepository()`**; nó đơn thuần là không có dữ liệu đúng tên event trong repository. Đặt timeout hoặc cơ chế dừng và bảo đảm cấu hình recording phù hợp.

### 11.3. Callback có thể chạy trên thread khác

Với `startAsync()`, callback không chạy trên `main`. Dùng `AtomicInteger`, `CountDownLatch`, queue thread-safe hoặc primitive đồng bộ phù hợp khi truyền dữ liệu giữa các thread. Tránh cập nhật collection thường từ nhiều thread mà không đồng bộ.

### 11.4. Không suy ra đã mất event chỉ vì timeout

Stream nhận dữ liệu khi JFR đã flush đủ để consumer thấy. Nếu một sự kiện vừa `commit()` nhưng chưa được flush trong khoảng chờ, timeout **chỉ nói rằng caller chưa quan sát được event**, không tự xác minh sự kiện đó đã biến mất vĩnh viễn. Cần kiểm tra tình trạng recording, quyền ghi đĩa, event settings và nhịp flush trước khi kết luận.

## 12. Chỉ đọc repository tin cậy và chú ý thông tin nhạy cảm

JFR event có thể chứa tên class, thread, stack trace, thông tin I/O hoặc trường do chính ứng dụng tự tạo. Nếu sự kiện chứa dữ liệu nghiệp vụ nhạy cảm, việc stream ra hệ thống log/metric cũng có nguy cơ lộ dữ liệu như việc xuất file `.jfr`.

- Không đưa bí mật như password, access token hoặc dữ liệu khách hàng vào custom JFR events chỉ để debug.
- Không mở repository không rõ nguồn gốc với `openRepository(Path)`; Javadoc nhấn mạnh **trusted disk repositories**.
- Không tự sửa, đổi tên, xóa hoặc di chuyển các chunk repository do JVM đang sử dụng.
- Tránh handler quá chậm, cấp phát liên tục hoặc in log mỗi event ở hệ thống tải cao.
- Khi cần lấy snapshot để lưu trữ/chia sẻ, sử dụng API dump hoặc `jcmd ... JFR.dump` thay vì coi file tạm repository là một artifact hoàn chỉnh.

Với ứng dụng dài hạn, cần có giám sát chi phí memory/I/O, chính sách retention cho recording ghi đĩa, quyền đối với thư mục repository và chiến lược shutdown khi dừng dịch vụ.

## 13. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách đúng |
|---|---|---|
| Tưởng `openRepository()` tự tạo recording | Không có event đúng yêu cầu được ghi | Tạo recording riêng và bật event, hoặc dùng `RecordingStream` |
| Tưởng stream không tham số kết nối JVM bất kỳ trên máy | Đọc nhầm phạm vi hoặc không thấy dữ liệu | Hiểu nó dùng **repository của JVM hiện tại** |
| Gọi `start()` trên main rồi mong main làm tiếp ngay | Main bị chặn | Dùng `startAsync()` hoặc thread chuyên trách |
| Gọi `startAsync()` rồi thoát `try` ngay | Stream đóng trước khi nhận được event | Giữ stream sống, chờ có giới hạn |
| Đăng ký sai tên event | Không nhận callback | Dùng tên event đầy đủ do JFR công bố |
| Không bật event trong recording | Dữ liệu không tồn tại trong repository | Cấu hình `recording.enable(...)` đúng |
| Dùng recording `disk=false` nhưng muốn stream đọc lịch sử trên đĩa | Không có dữ liệu disk tương ứng để đọc | Dùng `disk=true` cho bài toán repository streaming |
| Cho rằng callback đến ngay sau `commit()` | Kết luận sai khi có delay | Tính đến nhịp batch/flush và timeout |
| Muốn replay mọi event từ trước nhưng không đặt start time | Mặc định đọc từ event được flush tiếp theo | Gọi `setStartTime(...)` trước start nếu cần và dữ liệu còn |
| Coi thứ tự callback là thứ tự toàn JVM tuyệt đối | Sai trong trường hợp nhiều batch/thread | Dùng timestamp, correlation IDs |
| Lưu tham chiếu `RecordedEvent` với reuse mặc định | Đối tượng có thể được tái sử dụng | Trích dữ liệu ngay hoặc `setReuse(false)` |
| Handler gọi I/O chậm trên mỗi event | Consumer tụt hậu | Gộp, batch, queue giới hạn |
| Không đóng stream | Rò tài nguyên hoặc không shutdown được | `try-with-resources` hoặc quy trình close có chủ đích |
| Xem `close()` là “đã xử lý hết callback” | Dữ liệu downstream có thể chưa hoàn tất | Đồng bộ riêng, chờ với timeout |
| Dùng `openFile(Path)` cho thư mục repository | Sai nguồn dữ liệu | Dùng `openRepository(Path)` cho repository, `openFile(Path)` cho file |
| Dùng `openRepository(Path)` với dữ liệu không tin cậy | Rủi ro xử lý dữ liệu | Chỉ mở repository đáng tin cậy, phân quyền đúng |

## 14. Quy trình triển khai trong dịch vụ thực

**Bước 1 — Xác định nhu cầu:** chỉ giám sát sự kiện của JVM hiện tại hay cần đọc file đã export? Với nhu cầu live từ repository, `openRepository()` là đúng factory.

**Bước 2 — Thiết lập nguồn sự kiện:** bảo đảm một recording ghi đĩa đã chạy với những loại event cần thiết. Không thay thế bước này bằng mở consumer.

**Bước 3 — Mở và đăng ký:** gọi `openRepository()`, gắn `onEvent("fully.qualified.EventName", ...)`, `onError(...)` và nếu cần `onFlush(...)`, `onClose(...)`.

**Bước 4 — Chọn mốc thời gian:** nếu chỉ muốn dữ liệu tiếp theo, giữ mặc định; nếu muốn replay dữ liệu còn lưu trong repository, chọn `setStartTime(Instant)` trước khi start.

**Bước 5 — Chạy stream:** dùng `start()` trong thread chuyên biệt hoặc `startAsync()` khi cần main tiếp tục.

**Bước 6 — Quản lý callback:** thực hiện xử lý nhẹ, tránh gọi API blocking kéo dài; nếu chuyển sang worker khác, dùng hàng đợi có giới hạn và tính đến reuse.

**Bước 7 — Theo dõi vấn đề vận hành:** log lỗi handler, giám sát backlog, tránh ghi nhiều event hơn khả năng xử lý, và xác minh JFR event settings.

**Bước 8 — Kết thúc:** đóng stream, bảo đảm callback/downstream kết thúc theo chính sách ứng dụng, rồi dừng recording do ứng dụng sở hữu nếu không còn cần.

### Checklist kiểm thử

- JFR khả dụng và một recording `disk=true` đang chạy?
- Event được bật, tên được đăng ký trong `onEvent` chính xác?
- `start()/startAsync()` được gọi **sau khi đăng ký callback**?
- Lời gọi `startAsync()` có đủ thời gian nhận các batch flush không?
- Trường hợp không có event có dừng được bằng timeout hoặc close không?
- Có handler lỗi để phân biệt lỗi I/O, quyền truy cập và lỗi trong callback không?
- Dữ liệu chia sẻ giữa callback và main có được đồng bộ an toàn không?
- Nếu lưu `RecordedEvent` qua callback, đã xét `setReuse(false)`?
- Tài nguyên được đóng khi ứng dụng dừng, kể cả khi có ngoại lệ?
- Repository và event data có được bảo vệ khỏi truy cập trái phép?

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `EventStream.openRepository()` mở dữ liệu của JVM nào?

**Đáp án:** JVM hiện tại đang chạy lời gọi. Đó không phải kết nối tới mọi tiến trình Java trên máy.

**Câu 2.** Nếu chỉ gọi `openRepository()` và `onEvent("demo.Pulse", ...)`, chương trình có chắc chắn nhận event không?

**Đáp án:** Không. Cần sự kiện `demo.Pulse` thật sự được một recording bật và ghi vào repository; event phải được flush và stream phải còn sống khi batch đến.

**Câu 3.** Mặc định stream bắt đầu đọc lại toàn bộ repository từ lúc JVM khởi chạy hay từ event được flush tiếp theo?

**Đáp án:** Từ **event được flush tiếp theo**. Nếu cần dữ liệu cũ còn lưu trên disk, có thể đặt `setStartTime(...)` trước khi start.

**Câu 4.** Khác biệt căn bản giữa `start()` và `startAsync()`?

**Đáp án:** `start()` xử lý ở thread gọi và chặn thread; `startAsync()` chạy ở thread riêng, caller tiếp tục. Cả hai đều cần đóng stream khi kết thúc.

**Câu 5.** Tại sao không nên thoát `try-with-resources` ngay sau `startAsync()`?

**Đáp án:** Stream có thể bị đóng trước khi JFR flush batch mới, khiến callback chưa nhận được event nào.

**Câu 6.** Khi cần đọc file đã dump `capture.jfr`, nên dùng factory nào?

**Đáp án:** `EventStream.openFile(Path.of("capture.jfr"))`. `openRepository()` không tự đọc file dump theo tên.

**Câu 7.** Tại sao callback không nên giữ trực tiếp `RecordedEvent` nếu dùng reuse mặc định?

**Đáp án:** Java API cho phép tái sử dụng cùng đối tượng `RecordedEvent` cho nhiều event. Nên trích dữ liệu cần dùng ngay hoặc `setReuse(false)` trước khi start nếu phải giữ event object.

**Câu 8.** Có thể kết luận event bị mất chỉ vì `CountDownLatch.await(15, SECONDS)` trả `false`?

**Đáp án:** Không. Đó là timeout quan sát; cần xét flush, event settings, recording, I/O và trạng thái stream trước khi kết luận.

**Câu 9.** `close()` có bảo đảm toàn bộ callback hoàn tất trước khi trả về không?

**Đáp án:** Không. API nêu rõ close có thể dừng ngay hoặc sau flush và **không bảo đảm** tất cả callback hoàn tất trước khi trả về. Thiết kế đồng bộ riêng nếu cần.

**Câu 10.** Để vừa tạo recording vừa stream sự kiện cùng một API, nên xem xét gì?

**Đáp án:** `jdk.jfr.consumer.RecordingStream`; nó khác `EventStream.openRepository()` là mở consumer cho repository của JVM hiện tại.

## 16. Tài liệu tham khảo

- [Oracle Java SE 17 — jdk.jfr.consumer.EventStream](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): `openRepository()`, `openRepository(Path)`, `openFile(Path)`, `onEvent`, `startAsync`, `awaitTermination`, `setReuse`, `setStartTime`, `onFlush`.
- [Oracle Java SE 17 — jdk.jfr.consumer.RecordingStream](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): cách đồng thời bật recording và nhận event trên JVM hiện tại.
- [Oracle Java SE 17 — jdk.jfr.Recording](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html): cấu hình `setToDisk`, `enable`, `start`, `stop`, `close` và `dump`.
- [Oracle Java SE 17 — jdk.jfr.consumer.RecordedEvent](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): cách đọc các trường sự kiện đã ghi.
- [Inside Java — JFR Event Stream](https://inside.java/2022/05/12/sip49/): ví dụ phân biệt các kiểu EventStream trong JDK.
- [Oracle Java SE 26 — EventStream](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): đối chiếu API vẫn tồn tại trên JDK hiện đại.

**Ghi nhớ:** **`EventStream.openRepository()` là một consumer cho repository JFR của JVM hiện tại, không phải câu lệnh “bật recording”.** Hãy bảo đảm recording phù hợp đang phát sinh sự kiện lên disk, đăng ký callback trước khi bắt đầu, hiểu thời điểm flush/batch, quản lý vòng đời stream, và chỉ dùng `openFile(Path)` khi thực sự muốn đọc file `.jfr` đã xuất.