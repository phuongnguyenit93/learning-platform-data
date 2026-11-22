# Xử lý nguồn dữ liệu kết thúc hoặc lỗi I/O với JFR EventStream

## 1. Bài toán cần giải quyết

`jdk.jfr.consumer.EventStream` cho phép chương trình Java xử lý **luồng sự kiện Java Flight Recorder (JFR)** thông qua callback. Luồng có thể đọc từ tệp recording `.jfr` đã hoàn tất hoặc theo dõi **JFR repository** có sự kiện tiếp tục xuất hiện. Khi xây dựng một consumer thực tế, ngoài việc đọc `onEvent(...)`, phải trả lời ba câu hỏi:

1. **Nguồn kết thúc bình thường:** Khi đã đọc hết tệp, chương trình làm thế nào biết stream đóng và hoàn tất phần tổng hợp?
2. **Nguồn không mở được hoặc gặp lỗi I/O:** Lỗi phát sinh ở lúc `openFile(...)`, khi đang xử lý hay từ callback? Bắt và báo cáo ra sao?
3. **Dừng chủ động hoặc dừng bất thường:** `close()`, `onClose(...)`, `startAsync()` và `awaitTermination(...)` phối hợp thế nào để không treo thread hoặc tuyên bố sai là xử lý thành công?

Đây không chỉ là vấn đề cú pháp. Một consumer phân tích sự cố có thể đọc thiếu dữ liệu vì tệp hỏng, file chưa hoàn tất, process bị dừng hoặc callback ném exception; nếu mọi trường hợp đều được báo “đã đọc xong thành công”, kết quả thống kê có thể gây hiểu lầm.

**Tính hiện hành:** JFR Event Streaming được giới thiệu chính thức ở **Java 14 (JEP 349)**. `EventStream` thuộc module `jdk.jfr`, package `jdk.jfr.consumer` và vẫn có trong các JDK hiện đại. Các ví dụ ở đây sử dụng **Java 17+**, API chuẩn đang được hỗ trợ, **không dùng API preview hay cách thiết lập JFR cũ đã lỗi thời**.

Mục tiêu sau bài:
- Phân biệt **EOF bình thường**, **đóng stream**, **I/O error** và **lỗi callback**.
- Dùng đúng `onEvent`, `onClose`, `onError`, `start`, `startAsync`, `awaitTermination` và `close`.
- Bắt `IOException` khi mở nguồn **ngay bên ngoài `openFile(...)`**, không chỉ trông chờ `onError`.
- Biết cách ghi nhận trạng thái xử lý một cách trung thực, nhất là khi làm bất đồng bộ.
- Chạy được một chương trình tạo tệp JFR rồi đọc hết tệp, thử tệp không tồn tại, mô phỏng lỗi callback và xác nhận stream đóng.

## 2. Chọn đúng loại nguồn: file, repository hay recording mới

`EventStream` là interface; bạn lấy stream qua factory chuẩn, không cần tự implement interface.

| Cách tạo nguồn | Dùng khi nào? | Đặc điểm kết thúc |
| --- | --- | --- |
| `EventStream.openFile(Path)` | Đọc một tệp `.jfr` đã có | **Hữu hạn**: khi xử lý hết nội dung tệp, luồng kết thúc và tự đóng |
| `EventStream.openRepository()` | Theo dõi repository JFR của JVM hiện tại | Có thể **liên tục** nhận các đợt sự kiện; thông thường cần chủ động `close()` hoặc giới hạn thời gian |
| `EventStream.openRepository(Path)` | Theo dõi một disk repository được phép truy cập | Có thể liên tục; phải xử lý lỗi truy cập repository và việc nguồn dừng |
| `new RecordingStream()` | Muốn **vừa tạo recording vừa stream events** trong JVM | Là một implementation của `EventStream` có khả năng quản lý recording; dừng/đóng theo vòng đời ứng dụng |

Điểm khác biệt quan trọng:

- `openFile` khởi đầu từ **sự kiện đầu tiên trong tệp** theo mặc định.
- `openRepository` theo mặc định bắt đầu từ **sự kiện được flush kế tiếp**, không tự động đọc toàn bộ quá khứ trong repository.
- `EventStream.openRepository()` **không đồng nghĩa khởi động một recording mới**. Nếu cần stream đồng thời quản lý recording, `RecordingStream` phù hợp hơn.
- `EventStream` không đảm bảo mọi event type đều được bật, được giữ lại hoặc xuất hiện đúng một lần. Điều này phụ thuộc recording và cơ chế flush/retention.

Vì hai loại nguồn có vòng đời khác nhau, **đừng chờ `start()` của một repository liên tục tự trả về như cách đọc tệp hữu hạn**, nếu chưa có thời điểm kết thúc hoặc cơ chế đóng rõ ràng.

## 3. Vòng đời EventStream

Luồng đơn giản cho tệp hữu hạn:

~~~text
openFile(file)
    |
    v
Tạo stream; đăng ký callback onEvent/onError/onClose
    |
    v
start()  -- đọc event, thực hiện callbacks trên thread hiện tại
    |
    +-- đọc hết tệp (kết thúc bình thường)
    |          |
    |          v
    |       Stream tự đóng -> onClose chạy
    |
    +-- phát sinh exception trong action
    |          |
    |          v
    |       onError nhận Throwable (nếu được đăng ký)
    |       Không tự suy ra toàn bộ stream đã thất bại hay vẫn an toàn
    |
    +-- ứng dụng / hệ thống gọi close()
               |
               v
            Stream dừng, onClose chạy
               |
               v
   Sau start(): kiểm tra lỗi và trạng thái, phát hành kết quả
~~~

**Điểm mấu chốt:** `onClose()` cho biết **stream đã đóng**, không cho biết **vì sao** nó đóng. Những nguyên nhân có thể là:
- Đọc hết một tệp hữu hạn.
- Ứng dụng gọi `close()`.
- Hết giới hạn thời gian đặt bằng `setEndTime(...)`.
- Nguồn/JVM theo dõi kết thúc hoặc một tình huống bất thường khiến stream tự đóng.

Do đó **`onClose` không phải `onSuccess`**. Không nên cập nhật một job là “thành công” chỉ vì callback này được gọi. Cần có thêm thông tin lỗi, yêu cầu xử lý, kiểu nguồn và lý do dừng.

### 3.1. Điều gì được đảm bảo về đóng tài nguyên?

`EventStream` extends `AutoCloseable`, nên dùng **try-with-resources**:

~~~java
try (EventStream stream = EventStream.openFile(path)) {
    stream.onEvent("my.Event", event -> {
        // Xử lý event.
    });
    stream.start();
}
~~~

Đây là **đoạn minh họa**, cần khai báo `path` và các import. Dù `start()` hoàn tất bình thường hay rời khối do lỗi, `try-with-resources` vẫn gọi `close()` để giải phóng tài nguyên. Việc gọi `close()` lặp lại trên stream đã đóng **không có tác dụng phụ thêm** theo hợp đồng.

**Không suy diễn** rằng `close()` sẽ chờ mọi callback bất đồng bộ hoàn tất: tài liệu API nêu rõ `close()` có thể dừng ngay hoặc sau một lần flush kế tiếp và **không bảo đảm tất cả registered actions hoàn tất trước khi nó trả về**. Khi cần phối hợp thread, phải thiết kế cơ chế chờ hoặc trạng thái riêng.

## 4. Các callback cần dùng đúng vai trò

| API | Khi nào có ích? | Cẩn trọng |
| --- | --- | --- |
| `onEvent(String, Consumer<RecordedEvent>)` | Xử lý event của một loại được chỉ định | Callback có thể ném exception; tránh xử lý quá nặng làm chậm consumer |
| `onEvent(Consumer<RecordedEvent>)` | Nhận mọi event được stream giao | Có thể tạo overhead cao nếu chỉ cần một vài loại |
| `onFlush(Runnable)` | Đưa số đếm/tổng hợp sau một batch sang hệ thống khác | Flush **không** đồng nghĩa EOF hoặc thành công của cả luồng |
| `onError(Consumer<Throwable>)` | Nhận thông báo khi có exception trong quá trình stream/callback | Handler **không được để tự ném exception**; tài liệu mô tả kết quả là không xác định nếu error handler tự lỗi |
| `onClose(Runnable)` | Phát tín hiệu rằng stream đã đóng | Callback có thể xảy ra khi EOF, đóng thủ công hoặc bất thường |
| `start()` | Bắt đầu xử lý trong **thread gọi hàm** | Có thể block cho đến khi nguồn kết thúc/đóng |
| `startAsync()` | Bắt đầu xử lý trên **một thread khác** | Caller cần phối hợp bằng callback, trạng thái chia sẻ và/hoặc `awaitTermination` |
| `awaitTermination()` | Chờ hành động hoàn thành hoặc stream đóng/interrupt | Có thể chờ vô hạn nếu stream liên tục và không có ai đóng |
| `awaitTermination(Duration)` | Chờ tối đa một khoảng thời gian | Trả về `void`; chỉ hàm trả về **không chứng minh xử lý đã kết thúc** |
| `close()` | Dừng và giải phóng tài nguyên | Không bảo đảm mọi action đã chạy xong trước khi trả về |

### 4.1. Đăng ký handler trước khi bắt đầu

~~~java
try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("com.example.Request", e -> {
        System.out.println(e.getStartTime());
    });
    stream.onError(error -> {
        System.err.println("EventStream failure: " + error);
    });
    stream.onClose(() -> System.out.println("stream closed"));
    stream.start();
}
~~~

Đây là đoạn minh họa cần tệp recording `file` và đúng event type. Đăng ký handler trước `start()`/`startAsync()` giúp tránh bỏ lỡ các event hoặc kết thúc sớm trước khi handler sẵn sàng.

### 4.2. Nhiều error handlers được phép

Có thể đăng ký nhiều `onError` callbacks; theo tài liệu, chúng được gọi theo thứ tự đăng ký. Nếu **không** đăng ký `onError`, hành vi mặc định là in exception và stack trace ra `System.err`. Khi đã đăng ký handler, bạn **thay thế hành vi mặc định**; nếu chỉ tăng counter nhưng không log lỗi, nguyên nhân có thể mất khỏi log.

**Cách thực tế:** Trong `onError`, ghi logger có traceback, tăng counter lỗi và đánh dấu kết quả không đáng tin cậy. Không ném exception mới từ chính handler, bởi hợp đồng API không định nghĩa hành vi khi handler lỗi.

## 5. Nguồn tệp kết thúc bình thường (EOF)

Với tệp `.jfr` hữu hạn:

~~~java
AtomicInteger seen = new AtomicInteger();
AtomicBoolean closed = new AtomicBoolean();

try (EventStream stream = EventStream.openFile(path)) {
    stream.onEvent("com.example.Request", event -> seen.incrementAndGet());
    stream.onClose(() -> closed.set(true));
    stream.start(); // Xử lý trong thread hiện tại.
}
System.out.println("events=" + seen.get());
System.out.println("closed=" + closed.get());
~~~

Đây là **đoạn minh họa**, cần import `java.util.concurrent.atomic.*`, `jdk.jfr.consumer.EventStream` và biến `path`. Nếu tệp được mở thành công và không có lỗi bất thường, `start()` chạy đến cuối luồng; stream tự đóng và `onClose` được gọi.

**Không nhầm EOF với I/O exception.** Đọc hết các event trong một tệp JFR hợp lệ là **trạng thái bình thường**, không cần ném lỗi hoặc tự tạo lỗi “hết dữ liệu”.

### 5.1. Mốc “đã đọc hết” chưa đủ để biết có xử lý đầy đủ hay không

`onClose` đúng + `seen == 0` không nhất thiết là lỗi. Có thể:
- Tệp không chứa event type đang theo dõi.
- Event type không được bật khi ghi recording.
- Không có sự kiện thuộc khoảng thời gian chọn.
- Các callback chỉ đăng ký một tên event không tồn tại trong tệp.

Nếu bài toán yêu cầu tối thiểu một event, hãy đặt **điều kiện nghiệp vụ riêng** sau khi kết thúc, ví dụ `if (seen.get() == 0) throw new IllegalStateException("No required events");`. Đây là validation của ứng dụng, không phải đặc tính EOF của EventStream.

### 5.2. Phân biệt đọc hết tệp với đóng trước hạn

Nếu một thread khác gọi `close()` giữa chừng, `onClose` cũng chạy nhưng có thể chưa xử lý mọi event. Muốn phân biệt phải theo dõi **ý định hủy** hoặc **trạng thái thực thi** ở tầng ứng dụng, thay vì dựa vào một boolean `closed` duy nhất.

Trong một batch, các event được phát theo thứ tự thời gian kết thúc, nhưng thứ tự giữa các batch có thể không tạo ra một thứ tự toàn cục chính xác tuyệt đối. Khi làm tổng hợp phức tạp, đừng ngầm coi callback cuối cùng luôn là event có timestamp lớn nhất trong recording.

## 6. I/O lỗi ngay lúc mở nguồn: bắt `IOException` bên ngoài

`EventStream.openFile(Path)` và `openRepository(...)` có thể ném **`IOException`**, ví dụ:
- Không có tệp hoặc đường dẫn không thể mở.
- Không thể truy cập source/repository.
- Lỗi I/O khi đọc dữ liệu hoặc mở cấu trúc recording.

Nếu `openFile(...)` thất bại, **đối tượng EventStream chưa được trả về**, nên `onError` hay `onClose` của stream đó **chưa thể được đăng ký**. Vì vậy chỉ đăng ký `onError` bên trong `try` là chưa đủ.

~~~java
import java.io.IOException;
import java.nio.file.Path;
import jdk.jfr.consumer.EventStream;

class ReadFileSafely {
    static void consume(Path file) {
        try (EventStream stream = EventStream.openFile(file)) {
            stream.onEvent(event -> {
                // Xử lý event.
            });
            stream.onError(error -> {
                System.err.println("during streaming: " + error);
            });
            stream.start();
        } catch (IOException io) {
            System.err.println("cannot open/read JFR file: " + io);
        }
    }
}
~~~

Đây là **kiểu Java minh họa hoàn chỉnh về cú pháp**, nhưng không có `main`. Lưu ý: một lỗi I/O có thể xuất hiện ở các giai đoạn khác nhau và cách chuyển lỗi qua callback hay exception phụ thuộc hoàn cảnh/implementation. Đoạn code chủ động xử lý **cả đường throw của factory** và **đường báo lỗi của stream**.

### 6.1. Không dựa vào lớp con chính xác của `IOException`

Với tệp không tồn tại, một JDK có thể ném `FileNotFoundException` (là subtype của `IOException`). Thay vì viết logic chỉ bắt `FileNotFoundException` rồi bỏ qua các lỗi khác, **bắt `IOException`** theo hợp đồng API và ghi đầy đủ cause/path trong log bảo mật.

Không công bố những đường dẫn nội bộ nhạy cảm, token hoặc dữ liệu cá nhân trong thông báo lỗi trả cho người dùng cuối; có thể đưa chẩn đoán chi tiết vào log nội bộ và trả mã lỗi an toàn.

### 6.2. Lỗi khi đọc/giải mã nguồn sau khi stream đã mở

Nếu dữ liệu `.jfr` bị hỏng, không còn đủ quyền, ổ đĩa gặp vấn đề hoặc repository biến mất, nguồn có thể không cung cấp được các event tiếp theo. `onError` là nơi xử lý **exception được stream báo**; sau khi nhận bất kỳ lỗi nào, hãy đánh dấu kết quả **incomplete/failed** theo hợp đồng job, đừng gộp nó vào “EOF thành công” chỉ vì `onClose` được gọi sau đó.

**Quan trọng:** `onError` cũng nhận lỗi từ **callback của chính bạn**; do đó không được kết luận mọi `Throwable` do `onError` nhận đều là `IOException`. Nếu cần phân loại, xem loại exception và stack trace. Những lỗi nghiêm trọng có thể cần chính sách ngừng job/alert riêng; không giả định stream tiếp tục hay dừng đúng một cách trên mọi implementation.

## 7. Lỗi từ callback không phải lỗi I/O nguồn

Xét:

~~~java
stream.onEvent("lesson.FlowEvent", event -> {
    if (event.getInt("index") == 2) {
        throw new IllegalStateException("bad-handler");
    }
});
stream.onError(error -> System.err.println(error));
~~~

Đây là **đoạn minh họa** với stream đang được tạo đúng trước khi chạy. Ở đây tệp vẫn có thể hoàn toàn hợp lệ; **code xử lý event** cố tình ném `IllegalStateException`. `onError` nhận exception đó theo API.

Tình huống này khác với:
- `openFile(missingFile)` ném `IOException` trước khi có stream.
- `onClose` chạy do đã đọc hết tệp.
- `close()` chạy theo yêu cầu dừng.

Một ứng dụng thực tế cần **phân loại và theo dõi riêng**:
- `SOURCE_OPEN_ERROR`: không mở được nguồn.
- `STREAM_ERROR`: xử lý luồng gặp lỗi bất ngờ.
- `HANDLER_ERROR`: logic xử lý event lỗi (nếu nhận diện được).
- `CANCELLED`: dừng theo yêu cầu.
- `COMPLETED`: hoàn tất theo điều kiện thành công của job.

Đây là **các nhãn trạng thái do ứng dụng tự thiết kế**, không phải enum do `EventStream` tự cung cấp.

### 7.1. Error handler không nên ném exception khác

Theo tài liệu `EventStream.onError`: nếu một `onError` action tự ném exception, hành vi kết quả **không được xác định**. Vì vậy:

~~~java
stream.onError(error -> {
    try {
        safeLogger(error);
    } catch (RuntimeException loggingFailure) {
        // Chuyển sang phương án tối thiểu không ném exception.
        System.err.println("Could not record streaming failure.");
    }
});
~~~

Đây là **đoạn minh họa**: `safeLogger(...)` là hàm ứng dụng giả định, không phải Java API. Khi soạn chương trình thực, cần cung cấp logging implementation cụ thể. Đừng viết `throw error` từ error handler hoặc vô tình dùng logger có thể ném ra ngoài mà không có cơ chế dự phòng.

### 7.2. Callback lỗi có thể ảnh hưởng tính đầy đủ dữ liệu

Một event handler thất bại có thể khiến bạn bỏ qua việc ghi số đếm, bỏ mất phép kiểm tra hoặc tạo dữ liệu sai. Trong thử nghiệm Java 17 ở phần 9, stream vẫn xử lý event thứ ba sau khi handler ném lỗi ở event thứ hai; **đó là quan sát của bài demo**, không phải lý do để giả định mọi lỗi/implementation đều phục hồi và không mất dữ liệu.

Nếu yêu cầu xử lý chính xác, lưu trạng thái lỗi và **không phát hành báo cáo thành công** khi có handler error chưa được khắc phục.

## 8. Đồng bộ và bất đồng bộ: `start()`, `startAsync()`, `awaitTermination()`

### 8.1. `start()` chạy callback trong thread gọi

~~~java
try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent(event -> process(event));
    stream.start();
    // Đến đây stream của tệp hữu hạn đã kết thúc hoặc bị đóng.
}
~~~

Đây là mã minh họa; `process(...)` do ứng dụng định nghĩa. Với tệp hữu hạn và không bị hủy sớm, `start()` thường là lựa chọn **đơn giản nhất**: sau khi trả về có thể xem bộ đếm/tổng hợp mà không phải đồng bộ thread xử lý riêng.

Nếu dùng repository liên tục, `start()` có thể chiếm thread hiện tại lâu dài. Hãy xác định cơ chế stop trước khi gọi.

### 8.2. `startAsync()` trả quyền điều khiển ngay

~~~java
AtomicInteger processed = new AtomicInteger();
AtomicBoolean closed = new AtomicBoolean();

try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent(event -> processed.incrementAndGet());
    stream.onClose(() -> closed.set(true));
    stream.startAsync();
    stream.awaitTermination(Duration.ofSeconds(10));
    System.out.println("closed=" + closed.get());
}
~~~

Đây là mã minh họa cần import `java.time.Duration`, `java.util.concurrent.atomic.*` và biến `file`. Callbacks chạy trên **thread khác**, nên dữ liệu chia sẻ cần an toàn cho đa luồng; `AtomicInteger` và `AtomicBoolean` hữu ích khi chỉ có một số đếm hoặc cờ.

**Cẩn thận với timeout:** `awaitTermination(Duration)` trả về `void` dù dừng vì stream kết thúc hay **hết thời gian chờ**. Khi nó trả, **phải xem trạng thái do bạn ghi nhận**, không in “completed” chỉ dựa vào việc phương thức trở về.

Ví dụ logic sau khi chờ:

~~~java
if (!closed.get()) {
    // Quá giới hạn chờ theo ứng dụng; cần đóng stream/cancel có chủ đích.
    stream.close();
    // Không coi dữ liệu xử lý đến đây là hoàn chỉnh.
}
~~~

Với job cần bảo đảm toàn bộ callback hoàn thành, phải thiết kế thêm cơ chế điều phối phù hợp và tránh race condition. `close()` tự nó **không có bảo đảm join toàn bộ callback**.

### 8.3. Đừng quên xử lý `InterruptedException`

`awaitTermination(...)` có thể bị ngắt:

~~~java
try {
    stream.awaitTermination(Duration.ofSeconds(10));
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    stream.close();
    // Báo job bị hủy / interrupted theo hợp đồng ứng dụng.
}
~~~

Đây là đoạn minh họa với stream đã tạo. **Khôi phục interrupt flag** là thói quen quan trọng khi không ném tiếp exception lên caller, để tầng bên trên biết thread có yêu cầu ngừng.

### 8.4. `onClose` có thể chạy trên thread khác

Với `startAsync()`, các callback được gọi trên thread xử lý stream; với `onClose` đã đăng ký, callback có thể chạy khi stream kết thúc hoặc khi có thao tác đóng. Tài liệu còn nêu: đăng ký `onClose` **sau khi stream đã đóng** sẽ gọi action ngay trong thread hiện tại. Vì vậy không nên giả định callback đóng luôn chạy trên cùng thread mà bạn khởi tạo stream.

Sử dụng các cấu trúc an toàn đa luồng nếu thay đổi trạng thái chia sẻ, và tránh block lâu bên trong callback.

## 9. Chương trình Java 17+ hoàn chỉnh đã kiểm chứng

Chương trình sau tạo một recording JFR trong bộ nhớ, bật custom event `lesson.FlowEvent`, ghi **3 event**, lưu xuống tệp `flow-events.jfr`. Sau đó chương trình kiểm tra bốn kịch bản:

1. Đọc hết một tệp hợp lệ bằng `start()` → đếm đủ event, `onClose` chạy, không có onError.
2. Mở tệp không tồn tại → `IOException` được bắt ở tầng gọi `openFile(...)`.
3. Callback `onEvent` cố tình ném `IllegalStateException` ở event thứ hai → `onError` nhận lỗi.
4. Đọc tệp bằng `startAsync()` + `awaitTermination(...)` → đếm event và xác nhận stream đã đóng.

Lưu mã vào **`EventStreamEndErrorDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.EventStream;

public class EventStreamEndErrorDemo {
    @Name("lesson.FlowEvent")
    static class FlowEvent extends Event {
        int index;
    }

    static Path createRecording(Path output) throws IOException {
        try (Recording rec = new Recording()) {
            rec.enable(FlowEvent.class).withThreshold(Duration.ZERO);
            rec.start();
            for (int i = 1; i <= 3; i++) {
                FlowEvent e = new FlowEvent();
                e.index = i;
                e.commit();
            }
            rec.stop();
            rec.dump(output);
        }
        return output;
    }

    static void readFile(Path recording) throws IOException {
        AtomicInteger count = new AtomicInteger();
        AtomicInteger errors = new AtomicInteger();
        AtomicBoolean closed = new AtomicBoolean();

        try (EventStream stream = EventStream.openFile(recording)) {
            stream.onEvent("lesson.FlowEvent", event -> {
                count.incrementAndGet();
                System.out.println("event=" + event.getInt("index"));
            });
            stream.onError(t -> errors.incrementAndGet());
            stream.onClose(() -> closed.set(true));
            stream.start();

            System.out.println("sync-event-count=" + count.get());
            System.out.println("sync-errors=" + errors.get());
            System.out.println("sync-closed=" + closed.get());
        }
    }

    static void missingFile(Path missing) {
        try (EventStream stream = EventStream.openFile(missing)) {
            stream.start();
        } catch (IOException ex) {
            System.out.println("missing-file-io=" + (ex instanceof IOException));
            System.out.println("missing-file-class="
                    + ex.getClass().getSimpleName());
        }
    }

    static void callbackFailure(Path recording) throws IOException {
        AtomicInteger errors = new AtomicInteger();
        AtomicInteger processed = new AtomicInteger();
        AtomicBoolean closed = new AtomicBoolean();

        try (EventStream stream = EventStream.openFile(recording)) {
            stream.onEvent("lesson.FlowEvent", event -> {
                processed.incrementAndGet();
                if (event.getInt("index") == 2) {
                    throw new IllegalStateException("bad-handler");
                }
            });
            stream.onError(t -> {
                errors.incrementAndGet();
                System.out.println("callback-error-type="
                        + t.getClass().getSimpleName());
                System.out.println("callback-error-message=" + t.getMessage());
            });
            stream.onClose(() -> closed.set(true));
            stream.start();
        }

        System.out.println("callback-attempts=" + processed.get());
        System.out.println("callback-errors=" + errors.get());
        System.out.println("callback-closed=" + closed.get());
    }

    static void asyncFile(Path recording)
            throws IOException, InterruptedException {
        AtomicInteger seen = new AtomicInteger();
        AtomicBoolean closed = new AtomicBoolean();

        try (EventStream stream = EventStream.openFile(recording)) {
            stream.onEvent("lesson.FlowEvent", event -> seen.incrementAndGet());
            stream.onClose(() -> closed.set(true));
            stream.startAsync();
            stream.awaitTermination(Duration.ofSeconds(10));
            System.out.println("async-events=" + seen.get());
            System.out.println("async-closed=" + closed.get());
        }
    }

    public static void main(String[] args) throws Exception {
        Path recording = createRecording(
                Path.of(args[0], "flow-events.jfr"));

        readFile(recording);
        missingFile(Path.of(args[0], "does-not-exist.jfr"));
        callbackFailure(recording);
        asyncFile(recording);
    }
}
~~~

### 9.1. Biên dịch và chạy

Dùng **JDK 17 trở lên** có module `jdk.jfr`. Chương trình cần **một đối số là thư mục đã tồn tại và có quyền ghi**. Ví dụ chạy ngay trong thư mục dự án:

~~~bash
javac -encoding UTF-8 --release 17 EventStreamEndErrorDemo.java
java EventStreamEndErrorDemo .
jfr summary flow-events.jfr
~~~

Lệnh `jfr summary` là bước kiểm tra tệp được sinh, không phải stdout của chương trình Java. Trong lần kiểm chứng, event type `lesson.FlowEvent` có **Count = 3**.

**Stdout đã kiểm chứng trên một JDK HotSpot:**

~~~text
event=1
event=2
event=3
sync-event-count=3
sync-errors=0
sync-closed=true
missing-file-io=true
missing-file-class=FileNotFoundException
callback-error-type=IllegalStateException
callback-error-message=bad-handler
callback-attempts=3
callback-errors=1
callback-closed=true
async-events=3
async-closed=true
~~~

**Lưu ý về tính di động:** Dòng `missing-file-class=FileNotFoundException` phản ánh **lần chạy đã kiểm chứng**, không phải cam kết `openFile` luôn ném đúng subtype này trên mọi JVM/OS. Hợp đồng API chỉ cần bắt `IOException`. Số event và thời gian hoàn tất trong ví dụ được kiểm tra trên môi trường cho phép recording hoạt động; một hệ thống bị giới hạn quyền, dung lượng hoặc tài nguyên có thể tạo kết quả khác hoặc ném exception cần xử lý.

### 9.2. Đọc hiểu từng nhóm kết quả

**`sync-event-count=3`**: handler `onEvent("lesson.FlowEvent", ...)` thấy ba event đã ghi.

**`sync-errors=0`**: không có exception được gửi tới `onError` trong đoạn đọc tệp bình thường. Đây là một điều kiện tốt nhưng **không phải bảo đảm toàn bộ pipeline luôn chính xác** nếu ứng dụng có lỗi logic không ném exception.

**`sync-closed=true`**: ở đường đọc file hữu hạn, stream đã đóng sau khi hết dữ liệu. Điều đó phù hợp với hợp đồng tự đóng khi stream kết thúc.

**`missing-file-io=true`**: mở tệp không tồn tại làm `openFile(...)` ném `IOException`, và code bắt nó **bên ngoài**; không cần `onError` cho đối tượng stream chưa tạo được.

**`callback-error-type=IllegalStateException`**, **`callback-error-message=bad-handler`**: error đến từ logic của application handler. Đây **không phải** hỏng file hoặc lỗi ổ đĩa.

**`callback-attempts=3`**: trong lần chạy này, chương trình vẫn vào callback cho cả ba events dù callback ở event thứ hai ném exception; không nên dựa vào hành vi đó để mặc định “event nào lỗi cũng được bỏ qua, mọi thứ vẫn thành công”.

**`callback-errors=1`**: có một exception đã được báo, nên đường xử lý này cần trạng thái khác với `COMPLETED` ở một job production đòi hỏi dữ liệu đầy đủ.

**`callback-closed=true`**: stream đã đóng dù có lỗi callback; minh chứng rằng **closed không đồng nghĩa successful**.

**`async-events=3`**, **`async-closed=true`**: lần đọc bất đồng bộ đã hoàn thành với ba event và stream đã đóng trong giới hạn chờ của demo.

## 10. Xử lý trạng thái lỗi trong chương trình thực tế

Demo ở phần 9 in ra console để dễ học; hệ thống production nên có một **kết quả cuối rõ ràng**. Ví dụ các trạng thái:

| Trạng thái ứng dụng (đề xuất, không phải enum Java sẵn có) | Ý nghĩa | Hành động tiếp |
| --- | --- | --- |
| `COMPLETED` | Nguồn hữu hạn đã kết thúc đúng kỳ vọng, không có lỗi không xử lý, đã kiểm tra điều kiện dữ liệu | Phát hành kết quả |
| `EMPTY` | Nguồn đọc được nhưng không có event mục tiêu | Có thể chấp nhận hoặc cảnh báo tùy nghiệp vụ |
| `OPEN_FAILED` | Không mở được tệp/repository | Log cause, kiểm tra path/quyền/source |
| `PROCESSING_FAILED` | Handler hoặc stream báo exception | Không công bố kết quả như thể đã đầy đủ |
| `CANCELLED` | Người dùng/hệ thống dừng chủ động | Giữ trạng thái hủy, xem dữ liệu là chưa hoàn chỉnh |
| `TIMED_OUT` | Chờ bất đồng bộ quá giới hạn | Đóng stream và xử lý timeout rõ ràng |

### 10.1. Phân loại trước khi gộp kết quả

Một sơ đồ logic:

~~~text
Thử openFile(...)
   |
   +-- IOException -> OPEN_FAILED -> log và kết thúc
   |
   +-- Thành công -> đăng ký onError / onClose / onEvent
                         |
                         v
                   start / startAsync
                         |
                         +-- onError -> Đánh dấu PROCESSING_FAILED
                         |
                         +-- chủ động close -> CANCELLED
                         |
                         +-- timeout -> TIMED_OUT
                         |
                         +-- file đọc xong và đã đóng
                                   |
                                   +-- có lỗi? -> FAILED
                                   +-- không lỗi, đủ dữ liệu? -> COMPLETED
                                   +-- không lỗi, thiếu dữ liệu bắt buộc? -> EMPTY/FAILED
~~~

Đây là **quy trình ứng dụng tự đặt**, không phải máy trạng thái chính thức có thể truy vấn trực tiếp từ `EventStream`. Nếu hệ thống có reconnect/retry, phải xét khả năng **đọc lại hoặc bỏ sót sự kiện** theo cơ chế nguồn. Không tự coi resume là exactly-once khi API không cung cấp một cam kết như vậy.

### 10.2. Cách xử lý lỗi không che mất stack trace

Ví dụ callback đăng ký:

~~~java
AtomicReference<Throwable> firstFailure = new AtomicReference<>();

stream.onError(error -> {
    firstFailure.compareAndSet(null, error);
    System.err.println("Stream action failed:");
    error.printStackTrace(System.err);
});
~~~

Đây là đoạn minh họa; cần import `java.util.concurrent.atomic.AtomicReference` và stream đang tồn tại. Khi job kết thúc, kiểm tra `firstFailure.get() != null` để **không phát hành báo cáo thành công**. Không ném lại exception từ chính `onError`; tài liệu API không xác định kết quả khi error handler ném exception.

Với production, dùng logger có chính sách an toàn dữ liệu, phân loại lỗi và hệ thống cảnh báo phù hợp; ví dụ dùng `System.err` chỉ để minh họa.

## 11. Rủi ro của `onClose` và việc dữ liệu còn dang dở

### 11.1. Đóng stream không nhất thiết làm xong tất cả callback

Tài liệu ghi rõ `close()`:
- Có thể dừng ngay hoặc sau lần flush kế tiếp.
- **Không bảo đảm toàn bộ registered actions hoàn tất trước khi trả về**.
- Gọi lại trên stream đã đóng không có hiệu lực thêm.

Vì thế nếu cần dữ liệu chính xác, đừng:

~~~java
stream.startAsync();
stream.close();
publishResults(); // Sai lầm: giả định mọi event đã xử lý.
~~~

Đây là **mã minh họa**, trong đó `publishResults` là hàm giả định. Ngay khi stream bị đóng, có thể còn event chưa giao cho callback hoặc tác vụ xử lý phụ chưa hoàn tất. Nếu callback lại giao việc sang một worker pool khác, trách nhiệm đợi pool hoàn thành thuộc **ứng dụng**, không phải `EventStream`.

### 11.2. Có thể gặp event object được tái sử dụng

Tài liệu `EventStream` nêu rằng theo mặc định một đối tượng `RecordedEvent` có thể được **tái sử dụng** để biểu diễn nhiều sự kiện; giữ reference tới event sau callback có thể khiến dữ liệu không còn là bản snapshot mà bạn nghĩ.

Nếu ứng dụng cần giữ từng `RecordedEvent` để xử lý sau callback:

~~~java
stream.setReuse(false);
~~~

Đây là đoạn minh họa cần gọi **trước khi** xử lý event. Hoặc tốt hơn: trích các field cần thiết thành một object/record bất biến của ứng dụng trong callback. Đừng đem reference đến một object có thể tái sử dụng sang thread khác một cách ngây thơ.

### 11.3. `onFlush` không phải tín hiệu hoàn tất

~~~java
stream.onFlush(() -> {
    // Một batch đã hoàn tất; có thể đẩy tổng hợp tạm thời.
});
~~~

`onFlush` chạy sau một đợt dữ liệu; có thể còn các batch tiếp theo. Không đánh dấu job hoàn tất, không đóng nguồn và không phát hành báo cáo cuối chỉ vì có một lần flush.

### 11.4. Xử lý bất đồng bộ đòi hỏi thread-safe state

Với `startAsync()`, handler và thread gọi là hai execution contexts khác nhau. Một `int count` thông thường bị nhiều thread đọc/ghi không có đồng bộ có thể dẫn đến giá trị hiển thị không đáng tin. `AtomicInteger`, `AtomicBoolean`, `AtomicReference`, `ConcurrentHashMap` hoặc mô hình message queue có thể phù hợp tùy bài toán.

Điều quan trọng là **tránh race condition giữa callback đang chạy và thread phát hành kết quả**. Trước khi công bố `COMPLETED`, phải có điều kiện hoàn tất đáng tin cậy và xử lý các timeout/interrupt/cancel.

## 12. Nguồn repository liên tục và kết thúc bất thường

### 12.1. Vì sao `openRepository` khác `openFile`?

~~~java
try (EventStream stream = EventStream.openRepository()) {
    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(event.getFloat("jvmUser"));
    });
    stream.start(); // Có thể tiếp tục chờ các batch mới.
}
~~~

Đây là **chương trình minh họa một khối code**, không bảo đảm có `jdk.CPULoad` nếu recording chưa bật loại event đó. Repository là nguồn **sống**, không mặc nhiên đạt EOF chỉ vì chưa có event trong vài giây.

Nếu muốn theo dõi CPU liên tục, hãy thiết kế:
- Tín hiệu dừng của service/process.
- Chính sách timeout hoặc `setEndTime(...)` đặt **trước khi stream bắt đầu** nếu phù hợp.
- Cách log và báo động khi stream đóng ngoài dự kiến.
- Retry/backoff có giới hạn nếu source tạm thời không truy cập được.
- Cơ chế giữ tránh trùng dữ liệu khi thu lại event cũ.

### 12.2. `setEndTime` như một giới hạn nội dung

`EventStream.setEndTime(Instant)` chỉ định end time và API mô tả rằng **tại end time stream được đóng**. Phải đặt **trước khi gọi `start()` / `startAsync()`**:

~~~java
stream.setEndTime(java.time.Instant.now().plusSeconds(30));
stream.start();
~~~

Đây là đoạn minh họa. End time không phải cơ chế khôi phục trong mọi sự cố: nó không thay cho quy tắc timeout, quyền truy cập, kiểm tra error hoặc đóng resource khi application hủy job. `awaitTermination(Duration)` cũng là **hạn mức chờ của caller**, không phải thứ tự tương đương với `setEndTime` lọc và giới hạn event của stream.

### 12.3. Khi JVM được theo dõi thoát

API cho biết stream có thể tự đóng trong tình huống ngoại lệ, ví dụ JVM đang được theo dõi thoát. `onClose` được gọi, nhưng không nên đánh dấu source “đã xử lý thành công” theo cùng tiêu chí EOF của một tệp `.jfr` hữu hạn. Đối với một subscription theo dõi JVM, đóng ngoài yêu cầu có thể cần alert hoặc retry/recreate stream.

### 12.4. File/repository chỉ nên mở từ nguồn tin cậy

Tài liệu API khuyến nghị chỉ mở **recording file và disk repository tin cậy**. Không nhận một đường dẫn đến tệp tùy ý từ bên ngoài rồi đọc như nguồn chuẩn mà không xét quyền truy cập, kích thước, quota, loại dữ liệu và giới hạn resource. JFR có thể chứa stack trace, tên method, đường dẫn và metadata nội bộ.

## 13. Các lỗi thường gặp và cách sửa

| Lỗi thiết kế | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ có `stream.onError(...)` nhưng không `catch IOException` khi `openFile` | Nếu mở file thất bại, chưa có stream để gọi handler | Bắt `IOException` quanh factory/try-with-resources |
| Coi `onClose` là thành công | Đóng thủ công, source lỗi hoặc JVM thoát vẫn có thể gọi callback | Theo dõi error/cancel/timeout và điều kiện thành công riêng |
| Dùng `start()` cho repository liên tục trên main thread mà không có cách stop | Ứng dụng bị giữ lại lâu | Có lifecycle rõ ràng hoặc dùng `startAsync` kèm shutdown |
| Dùng `startAsync` và lập tức đọc `count` | Callback có thể chưa chạy | `awaitTermination`/state đồng bộ |
| `awaitTermination(Duration)` trả về là tuyên bố COMPLETED | Có thể do timeout | Kiểm tra cờ `closed`, error/cancel và policy |
| Để `onError` tự ném exception | Hành vi không xác định theo API | Error handler chỉ ghi nhận/log an toàn |
| Thấy `onError` rồi kết luận lỗi ổ đĩa | Handler nghiệp vụ cũng có thể ném exception | Xem subtype, stack và stage |
| Đọc EOF của file rồi tạo IOException “hết dữ liệu” | Biến kết thúc bình thường thành thất bại giả | EOF là hoàn tất nếu hợp đồng job đáp ứng |
| Gọi `close` rồi tin callback xử lý xong | API không bảo đảm | Chủ động đồng bộ và quản lý phần việc còn tồn |
| Giữ `RecordedEvent` ngoài callback khi mặc định reuse | Có thể tham chiếu object đã được dùng lại | `setReuse(false)` hoặc copy field cần dùng |
| Đánh dấu hoàn tất khi `onFlush` chạy | Flush chỉ là ranh giới batch | Chờ stream lifecycle phù hợp |
| Không log error sau khi đăng ký `onError` | Bạn đã thay hành vi in stack trace mặc định | Ghi log/trạng thái có đầy đủ cause |
| Tin tệp không có event nghĩa là hỏng | Có thể do filter/event type không xuất hiện | Phân biệt source hợp lệ rỗng với nguồn bị lỗi |
| Retry stream file mà không xét duplicate | Có thể xử lý lại event đã tiêu thụ | Có chiến lược idempotency/checkpoint theo nghiệp vụ |

## 14. Bài tập kiểm tra kiến thức

### Bài 1 — Đọc hết file là lỗi hay thành công?

~~~java
try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("lesson.FlowEvent", event -> count.incrementAndGet());
    stream.onClose(() -> closed.set(true));
    stream.start();
}
~~~

**Câu hỏi:** `onClose` chạy sau khi đọc hết tệp có nghĩa đã xảy ra exception không?

**Đáp án:** **Không.** Stream hữu hạn tự đóng khi kết thúc bình thường. `onClose` chỉ nói rằng stream đóng, không hàm ý có exception hoặc có bao nhiêu event. Nếu ứng dụng yêu cầu dữ liệu đầy đủ, phải xem các error/cancel và điều kiện số bản ghi riêng.

### Bài 2 — Mở tệp không tồn tại

~~~java
EventStream stream = EventStream.openFile(
        Path.of("missing-recording.jfr"));
~~~

**Câu hỏi:** Chỉ cần đăng ký `onError` cho stream này là đủ không?

**Đáp án:** **Không.** `openFile` có thể ném `IOException` trước khi trả một `EventStream`. Cần `catch(IOException)` ở bên ngoài, nơi gọi factory; lúc chưa có stream không thể đăng ký callback.

### Bài 3 — Handler ném exception

~~~java
stream.onEvent("lesson.FlowEvent", event -> {
    throw new IllegalStateException("bad handler");
});
stream.onError(error -> System.err.println(error));
~~~

**Câu hỏi:** Lỗi này có chứng minh tệp `.jfr` bị hỏng không?

**Đáp án:** **Không.** Exception do **logic xử lý event** cố ý tạo ra. `onError` được dùng để thông báo lỗi trong quá trình stream/callback; cần phân biệt stage và loại lỗi trước khi kết luận lỗi I/O.

### Bài 4 — Timeout bất đồng bộ

~~~java
stream.startAsync();
stream.awaitTermination(Duration.ofMillis(1));
System.out.println("complete");
~~~

**Câu hỏi:** Có thể tuyên bố “complete” vì `awaitTermination` đã trả về không?

**Đáp án:** **Không.** Phương thức có thể trả về do timeout. Cần tín hiệu trạng thái đáng tin cậy từ consumer, chính sách cancel nếu chưa xong, và xem cả lỗi được báo. Thời lượng 1 ms chỉ để minh họa điều kiện dễ bị timeout.

### Bài 5 — Xác định lỗ hổng dữ liệu

Một job ghi 500 events vào JFR, nhưng consumer chỉ xử lý được 260 events thì bị đóng theo yêu cầu người dùng. `onClose` đã gọi và `onError` không báo lỗi.

**Câu hỏi:** Job nên được đánh dấu `COMPLETED` không?

**Đáp án:** Không. Đây là **hủy trước hạn (CANCELLED)**, dù stream đã đóng và không có lỗi trong các callback. Không thể công bố báo cáo như thể đã xử lý toàn bộ 500 events.

### Bài 6 — Chọn cách đọc cho một tệp hữu hạn

Bạn cần đọc `.jfr` từ một batch job, tổng hợp số sự kiện rồi ghi báo cáo cuối, không cần thread khác.

**Đáp án gợi ý:** Chọn `EventStream.openFile(file)`, đăng ký `onEvent` + `onError`, gọi `start()` đồng bộ trong `try-with-resources`, bắt `IOException` khi mở source, kiểm tra lỗi/điều kiện dữ liệu sau khi `start()` trả về, rồi phát hành báo cáo. `startAsync` chỉ cần thiết nếu ứng dụng có lý do quản lý xử lý bất đồng bộ.

## 15. Checklist vận hành an toàn

- [ ] Biết rõ nguồn là **file hữu hạn** hay **repository liên tục**.
- [ ] Thử mở nguồn và bắt `IOException` **bên ngoài factory**.
- [ ] Đăng ký `onEvent`, `onError`, `onClose` **trước** khi bắt đầu.
- [ ] `onError` ghi nhận lỗi mà **không ném exception**.
- [ ] Không suy diễn **closed = successful**.
- [ ] Dùng `try-with-resources` để đóng resource ở mọi đường thoát.
- [ ] Khi bất đồng bộ, có `awaitTermination`, timeout/cancel và trạng thái an toàn đa luồng.
- [ ] Không coi một timeout chờ là bằng chứng xử lý hoàn tất.
- [ ] Kiểm tra event count/data quality bằng quy tắc ứng dụng riêng.
- [ ] Không dùng `onFlush` thay cho EOF và không quên khả năng event object reuse.
- [ ] Nguồn recording/repository được **tin cậy và được phép truy cập**.
- [ ] Retry, nếu có, phải tính đến khả năng trùng event và việc thay đổi cửa sổ dữ liệu.

## 16. Tóm tắt

- **EOF của file JFR** là kết thúc bình thường; stream tự đóng và `onClose` chạy.
- **`onClose` không nói lý do đóng**: EOF, đóng thủ công, end time hay tình huống bất thường đều có thể kích hoạt.
- **`openFile(...)` / `openRepository(...)` có thể ném `IOException` trước khi có stream**; bắt ở tầng gọi factory.
- **`onError(Consumer<Throwable>)` nhận exception trong quá trình stream/callback**; lỗi handler không tự động là lỗi I/O nguồn.
- **Không để chính `onError` ném exception**; API không định nghĩa hành vi đó.
- **`start()` đồng bộ; `startAsync()` bất đồng bộ**; `awaitTermination(Duration)` không trả trạng thái thành công.
- **`close()` không đảm bảo mọi callback đã hoàn tất**; trạng thái job phải do ứng dụng quản lý.
- Với phân tích nghiêm túc, phân biệt rõ `COMPLETED`, `OPEN_FAILED`, `PROCESSING_FAILED`, `CANCELLED` và `TIMED_OUT`.

**Nguồn chính thức vẫn còn áp dụng:**
- [Java SE 17 API — `jdk.jfr.consumer.EventStream`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): `openFile`, `onError`, `onClose`, `start`, `startAsync`, `awaitTermination` và `close`.
- [Java SE 25 API — `EventStream`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): đối chiếu hành vi API trên một bản JDK hiện đại.
- [Java SE 17 API — `RecordingStream`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): xử lý nguồn vừa ghi recording vừa stream.
- [Java SE 17 API — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html): tạo recording để thực hành.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): mô hình streaming và giới thiệu EventStream từ Java 14.
