# Tránh kết thúc ứng dụng trước khi luồng bất đồng bộ của `RecordingStream` xử lý sự kiện

## 1. Vấn đề: `startAsync()` không đồng nghĩa sự kiện đã được nhận

`jdk.jfr.consumer.RecordingStream` là API dùng để **ghi và tiêu thụ sự kiện Java Flight Recorder (JFR) trong khi JVM đang chạy**. Nó cho phép đăng ký callback bằng `onEvent(...)` rồi bắt đầu streaming. Điểm cần chú ý là lựa chọn giữa hai cách khởi động:

- `start()`: bắt đầu xử lý sự kiện theo cách **đồng bộ**, và lời gọi chặn luồng hiện tại cho đến khi stream kết thúc.
- `startAsync()`: bắt đầu xử lý **bất đồng bộ** trên luồng khác và **trả quyền điều khiển cho mã gọi** mà không đợi các callback chạy xong.

Do đó, thứ tự mã sau **không chứng minh rằng event đã được xử lý**:

```java
stream.startAsync();
performWork();          // Có thể phát sinh JFR event.
System.out.println("Done");
```

Đây là đoạn minh họa trong một phương thức đã có biến `stream` kiểu `RecordingStream` và phương thức `performWork()` phù hợp. `Done` chỉ cho biết luồng gọi đã chạy tới câu lệnh in; callback `onEvent` có thể vẫn chưa nhận được sự kiện. Sự kiện cần thời gian để được commit, đưa vào cơ chế ghi/streaming và chuyển tới consumer. Việc `Event.commit()` đã trả về **không đồng nghĩa** callback đã chạy.

**Chủ đề của bài:** làm thế nào để ứng dụng không tự kết thúc, không đóng `RecordingStream` quá sớm và không kiểm tra kết quả trước khi phần xử lý bất đồng bộ thực sự hoàn thành.

**Ngữ cảnh phiên bản:** JFR Event Streaming được giới thiệu ở **Java 14** (JEP 349) và vẫn là API áp dụng trong Java 17/21+ hiện nay. Các ví dụ sử dụng Java 17 trở lên, **không** dùng cú pháp preview hay giải pháp legacy.

## 2. Hiểu đúng vòng đời của RecordingStream

Một luồng sử dụng phổ biến:

1. Tạo `RecordingStream`.
2. Chọn event type với `enable(...)` và điều chỉnh threshold/setting cần thiết.
3. Đăng ký `onEvent(...)` và `onError(...)` trước khi bắt đầu.
4. Gọi `startAsync()`.
5. Cho ứng dụng thực hiện công việc và tạo sự kiện.
6. **Giữ stream tồn tại** cho đến khi các callback cần thiết được xử lý hoặc khi dịch vụ nhận tín hiệu dừng.
7. Đóng stream với `close()`, thường thông qua `try-with-resources` hoặc `finally`.

Mô hình thời gian:

```text
Luồng gọi/main              Luồng xử lý JFR
      |                            |
      | đăng ký onEvent            |
      | bật event type             |
      | startAsync()               |
      |--------------------------->| bắt đầu xử lý stream
      | startAsync trả về          |
      | công việc sinh event       |
      | Event.commit()             |
      |                            | nhận event sau một khoảng trễ
      |                            | chạy callback onEvent(...)
      |<------ tín hiệu latch -----|
      | xác nhận đã xử lý          |
      | close() stream             |
      v                            v
  ứng dụng hoàn tất         stream ngừng hoạt động
```

Khoảng trễ giữa `commit` và callback **không phải lỗi**. Nó là đặc điểm quan trọng của xử lý bất đồng bộ và cơ chế buffer/chunk của JFR. Không nên giả định callback chạy ngay trong cùng một lời gọi `commit()`.

### Đừng dựa vào giả định về daemon thread

Một lỗi lập luận là cho rằng “`startAsync()` chắc chắn tạo daemon thread nên `main` trả về thì JVM kết thúc”, hoặc ngược lại “luồng JFR sẽ giữ JVM sống nên không cần đóng stream”. **Không xây logic vòng đời từ một giả định về trạng thái daemon**: chi tiết thực thi và môi trường chạy có thể khác, trong khi framework, container, `System.exit(...)` hoặc shutdown bên ngoài vẫn có thể kết thúc ứng dụng.

Điều phải bảo đảm ở cấp thiết kế là: **mã đang sở hữu RecordingStream chịu trách nhiệm giữ stream sống khi còn cần và đóng nó khi hoàn thành**. Trạng thái daemon không phải cơ chế xác nhận callback đã xử lý event.

## 3. Anti-pattern: đóng stream ngay sau `startAsync()`

Đoạn sau nhìn có vẻ có quản lý tài nguyên tốt nhưng rất dễ làm mất cơ hội tiêu thụ event:

```java
// Đoạn minh họa nguy cơ; phụ thuộc DemoEvent và biến event.
try (RecordingStream stream = new RecordingStream()) {
    stream.enable(DemoEvent.class);
    stream.onEvent("demo.DemoEvent",
            event -> System.out.println("Received"));
    stream.startAsync();
    new DemoEvent().commit();
} // close() chạy ngay khi khối try kết thúc.
```

Vì `startAsync()` không chờ callback, `try-with-resources` có thể gọi `close()` **trước khi** consumer xử lý event. Đầu ra `Received` không được bảo đảm sẽ xuất hiện. Đây là **ví dụ anti-pattern**, chưa phải một chương trình hoàn chỉnh vì `DemoEvent` chưa được định nghĩa.

**Lỗi không nằm ở `try-with-resources`.** Công cụ đó rất tốt để bảo đảm `close()`; lỗi là **phạm vi sống của stream bị rút ngắn** so với công việc bất đồng bộ cần hoàn tất. Cách sửa là đợi đúng tín hiệu hoàn thành **bên trong** khối `try`, rồi để nó đóng stream ở cuối.

Tương tự, gọi `System.exit(0)` hoặc yêu cầu container dừng ngay sau `startAsync()` có thể ngăn xử lý hoàn tất. Không thể lấy câu lệnh đã gọi `startAsync()` làm bằng chứng sự kiện đã được nhận.

## 4. Giải pháp cho ứng dụng ngắn: `CountDownLatch` chờ callback

Khi bài toán có **một event cụ thể** cần nhận trước khi kết thúc, `CountDownLatch` là cơ chế đồng bộ rõ ràng:

- Khởi tạo `CountDownLatch(1)`.
- Đăng ký `onEvent(eventName, callback)`.
- Khi callback nhận đúng event, lưu kết quả và gọi `countDown()`.
- Mã chính gọi `await(timeout, TimeUnit.SECONDS)`.
- Nếu hết hạn chờ, báo lỗi rõ ràng; nếu consumer lỗi, xử lý lỗi.
- Chỉ **sau khi** xác nhận kết quả, khối `try-with-resources` mới kết thúc và `close()` được gọi.

`CountDownLatch.await(...)` tạo quan hệ đồng bộ giữa callback và luồng chờ. Khi callback giảm latch đến 0, luồng chính được đánh thức và có thể dùng kết quả vừa được ghi, không cần đoán khoảng thời gian đủ dài. Ví dụ dưới đây còn dùng `AtomicReference` để truyền dữ liệu/lỗi qua ranh giới luồng một cách tường minh.

### Chương trình Java 17+ hoàn chỉnh

Lưu toàn bộ đoạn mã sau thành tệp **`Main.java`**. Nó dùng **custom JFR event** để tạo kết quả có thể kiểm thử mà không phụ thuộc vào việc JVM có tình cờ phát sinh GC, CPU sample hay socket event trong vài giây hay không.

```java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public class Main {
    @Name("demo.TaskCompleted")
    @Label("Task Completed")
    static class TaskCompleted extends Event {
        String taskId;
        int items;
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch signal = new CountDownLatch(1);
        AtomicReference<String> observed = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable(TaskCompleted.class).withThreshold(Duration.ZERO);

            stream.onEvent("demo.TaskCompleted", recorded -> {
                observed.set(recorded.getString("taskId")
                        + ":" + recorded.getInt("items"));
                signal.countDown();
            });
            stream.onError(error -> {
                failure.compareAndSet(null, error);
                signal.countDown();
            });

            stream.startAsync();

            TaskCompleted event = new TaskCompleted();
            event.taskId = "JOB-7";
            event.items = 3;
            event.commit();

            if (!signal.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for JFR event");
            }
            if (failure.get() != null) {
                throw new IllegalStateException("JFR consumer failed", failure.get());
            }

            System.out.println("RECEIVED=" + observed.get());
            System.out.println("HANDLER_FINISHED=true");
        }

        System.out.println("STREAM_CLOSED=true");
    }
}
```

**Biên dịch và chạy với JDK 17 trở lên:**

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

**Stdout đã kiểm chứng trong môi trường hỗ trợ JFR:**

```text
RECEIVED=JOB-7:3
HANDLER_FINISHED=true
STREAM_CLOSED=true
```

Cửa sổ chờ là **tối đa 10 giây**, không phải một độ trễ cố định. Nếu runtime quá tải, stream lỗi hoặc event không đến, chương trình sẽ thông báo lỗi thay vì in giả kết quả thành công. Giá trị timeout phù hợp với ứng dụng thực tế cần được cân nhắc theo thời gian ghi/tiêu thụ event và yêu cầu vận hành.

### Tại sao ví dụ hoạt động?

1. **`@Name("demo.TaskCompleted")`:** đặt tên định danh JFR event. `@Label` là nhãn hiển thị; callback lọc bằng **tên type** `demo.TaskCompleted`.
2. **`stream.enable(TaskCompleted.class)`:** bật event này trước khi streaming. `withThreshold(Duration.ZERO)` cho phép cả những event có thời lượng rất ngắn, giúp ví dụ có thể được ghi.
3. **`stream.onEvent(...)`:** đăng ký hàm xử lý từ trước. Callback lấy hai trường `taskId`, `items` từ `RecordedEvent`.
4. **`stream.startAsync()`:** trả về trong khi xử lý stream diễn ra bất đồng bộ. Dòng tiếp theo phát sinh event bằng `event.commit()`.
5. **`signal.await(10, TimeUnit.SECONDS)`:** giữ luồng chính **không kết thúc phạm vi `try`** khi callback chưa báo hoàn thành. Đây là bước ngăn đóng stream sớm.
6. **`stream.onError(...)`:** ghi nhận lỗi phía consumer vào `failure` và đánh thức luồng chờ để nó không phải đứng đợi đến hết timeout khi callback báo lỗi.
7. **`try-with-resources`:** sau khi đã xử lý thành công hoặc xảy ra lỗi/timeout, stream được đóng. Phần in `STREAM_CLOSED=true` chỉ chạy ở đường thành công sau khi thoát khối `try`.

**Ý nghĩa quan trọng của latch:** `CountDownLatch(1)` chỉ chứng minh **một callback tương ứng đã chạy**. Nếu stream ghi nhiều event và ứng dụng muốn xử lý *toàn bộ*, cần một giao thức hoàn tất khác (biết số lượng, sentinel event, đồng bộ producer/consumer hoặc lifecycle được quản lý), không suy luận “đã nhận một event” nghĩa là “không còn event nào chưa xử lý”.

## 5. Vì sao `Thread.sleep(...)` không phải giải pháp chính?

Một cách vá thường gặp:

```java
stream.startAsync();
produceEvents();
Thread.sleep(1000); // Chỉ đoán rằng 1 giây là đủ.
```

Đây là đoạn minh họa trong phương thức có `produceEvents()` được định nghĩa. Nó có thể “hoạt động” trong một lần thử nhưng **không ràng buộc** việc callback hoàn tất. Thời gian xử lý JFR có thể thay đổi theo tải, cơ chế buffering, CPU, GC, môi trường CI và hệ điều hành.

Nếu sleep quá ngắn, test chập chờn. Nếu sleep rất dài, chương trình chậm không cần thiết. Khi có lỗi ở consumer, sleep cũng không tự báo rằng sự kiện đã không được xử lý.

**Lựa chọn nên ưu tiên:**

- Biết chính xác event đang chờ: `CountDownLatch` hoặc `CompletableFuture` hoàn tất khi callback nhận event.
- Chờ nhiều công việc: cơ chế đồng bộ theo số lượng hoặc trạng thái producer/consumer rõ ràng.
- Dịch vụ sống lâu: gắn `RecordingStream` với lifecycle của dịch vụ và tín hiệu shutdown.
- Cần đọc recording sau một khoảng thời gian: thiết kế rõ lúc bắt đầu, lúc dừng, phần xác nhận dữ liệu và nơi lưu, không xem sleep là bằng chứng event đã tới callback.

Có thể dùng `Thread.sleep` để **mô phỏng workload hoặc tạo khoảng thời gian thử nghiệm**, nhưng nó không thay thế tín hiệu “công việc đã hoàn thành”.

## 6. Phân biệt `awaitTermination()` với việc chờ **một event**

`RecordingStream`/`EventStream` có các phương thức:

```java
stream.awaitTermination();
stream.awaitTermination(java.time.Duration.ofSeconds(10));
```

Đây là các lệnh minh họa trong phương thức có `stream` phù hợp. Ý nghĩa: **chờ stream kết thúc**, không phải “chờ event tiếp theo” hoặc “chờ callback cụ thể”. Nếu stream đang chạy liên tục, đợi termination có thể tiếp tục chờ rất lâu mà event mục tiêu đã được xử lý từ trước.

| Muốn chờ điều gì? | Công cụ thích hợp | Không nên nhầm với |
| --- | --- | --- |
| Callback nhận event `demo.TaskCompleted` | `CountDownLatch` được callback `countDown()` | `awaitTermination()` |
| Kết quả bất đồng bộ có dữ liệu hoặc lỗi | `CompletableFuture` hoàn tất bởi callback | `Thread.sleep(...)` |
| Toàn bộ stream đã kết thúc | `awaitTermination(...)` trong thiết kế có logic dừng | “Event đã đến” |
| Dừng và giải phóng tài nguyên | `close()` qua `try-with-resources`/`finally` | “Đóng thì mọi event chưa đọc chắc chắn đã xử lý xong” |

Dạng `awaitTermination(Duration)` là overload chờ có giới hạn, nhưng **không trả về Boolean xác nhận một event cụ thể**. Vì vậy đừng thay `signal.await(...)` trong ví dụ bằng `stream.awaitTermination(Duration.ofSeconds(10))` rồi suy luận rằng kết quả `observed` chắc chắn có dữ liệu.

Khi muốn tiêu thụ sự kiện liên tục tới khi có yêu cầu dừng, một cách hợp lý là thiết kế đường dừng rõ ràng, sau đó đợi termination trong giới hạn phù hợp. Điều này khác với trường hợp one-shot chỉ cần một callback.

## 7. Dịch vụ chạy lâu: quản lý stream theo vòng đời ứng dụng

Trong server, service hoặc tiến trình chạy nền, thường **không có một số lượng event cố định** để chờ. Mục tiêu là bắt sự kiện trong suốt thời gian dịch vụ hoạt động, rồi dừng có kiểm soát.

Mẫu cấu trúc có thể là:

```java
// Đoạn minh họa bên trong một phương thức quản lý lifecycle.
// shutdownSignal là CountDownLatch được tạo/điều khiển bởi ứng dụng.
// handleEvent là callback xử lý đã được định nghĩa.

try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.JavaMonitorEnter")
            .withThreshold(java.time.Duration.ofMillis(20));
    stream.onEvent("jdk.JavaMonitorEnter", event -> handleEvent(event));

    stream.startAsync();

    // Service không thoát khỏi try ngay sau startAsync().
    shutdownSignal.await();
} // Stream được đóng khi ứng dụng thực sự nhận yêu cầu dừng.
```

Đây là **mẫu tích hợp**, không chạy độc lập: `shutdownSignal` và `handleEvent` phải được định nghĩa bởi hệ thống sở hữu service. Latch này là **tín hiệu shutdown từ application lifecycle**, không phải tín hiệu chờ sự kiện đầu tiên.

Một thiết kế đầy đủ cần quy định:

1. **Ai sở hữu stream?** Thành phần nào tạo và chịu trách nhiệm đóng?
2. **Khi nào bắt đầu?** Thường sau khi cấu hình event và callback, trước khoảng workload cần quan sát.
3. **Khi nào dừng?** Khi service shutdown, tác vụ hoàn tất hoặc lệnh quản trị yêu cầu dừng.
4. **Lỗi được xử lý ở đâu?** Đăng ký `onError(...)`, đưa thông tin chẩn đoán vào logging phù hợp và phát tín hiệu nếu consumer không thể tiếp tục.
5. **Dữ liệu có cần giữ lại?** Khi cần lưu phân tích dài hạn, lựa chọn cơ chế recording/dump JFR thích hợp; callback realtime không tự thay thế chiến lược lưu trữ.
6. **Tài nguyên được giải phóng thế nào?** Đóng stream trong đường shutdown bình thường, kể cả khi luồng chính bị gián đoạn hoặc tác vụ khác ném lỗi.

**Lưu ý:** Khi JVM bị kill đột ngột, tiến trình crash hoặc container bị cưỡng bức dừng, không thể hứa mọi event buffered đều được giao cho callback trước khi kết thúc. Vì vậy với dữ liệu chẩn đoán quan trọng, cần thiết kế shutdown/retention phù hợp và không coi streaming là một hàng đợi thông điệp bền vững có bảo đảm delivery tuyệt đối.

## 8. `start()` và `startAsync()` khác nhau ở đâu?

| Tiêu chí | `start()` | `startAsync()` |
| --- | --- | --- |
| Lời gọi có chờ vòng đời xử lý stream? | Có, chặn luồng gọi cho tới khi stream kết thúc | Không, trả về sớm |
| Callback chạy như thế nào? | Xử lý event trong quá trình streaming được khởi động đồng bộ | Xử lý event trên luồng khác |
| Luồng gọi tiếp tục làm công việc khác ngay sau start? | Không, trừ khi có luồng khác quản lý dừng | Có |
| Khi nào phù hợp? | Một chương trình/worker chuyên dùng để tiêu thụ stream | Ứng dụng vừa chạy nghiệp vụ vừa muốn quan sát JFR |
| Phải có đường dừng và đóng stream? | Có | Có |
| Lời gọi trả về có chứng minh event mục tiêu đã nhận? | Không thể suy luận số lượng event tùy ý từ việc kết thúc | Không |

Có thể dùng `start()` trong một luồng chuyên dụng khi muốn tiêu thụ liên tục; hoặc dùng `startAsync()` và tự đồng bộ với phần còn lại của ứng dụng. **Không có lựa chọn nào tự động biến việc tiêu thụ event thành xử lý “đúng đủ và bền vững”**.

Trong các ứng dụng có framework quản lý thread pool, scheduler hoặc lifecycle, nên tích hợp việc mở/đóng stream vào thành phần phù hợp thay vì đặt một vòng chờ tùy ý trong HTTP request handler hoặc giao diện người dùng.

## 9. Race condition thường gặp

### 9.1. Callback được đăng ký sau khi start

```java
// Không nên bố trí như sau:
stream.startAsync();
stream.onEvent("demo.TaskCompleted", event -> process(event));
```

Đây là đoạn minh họa, `process` chưa được định nghĩa. Event có thể phát sinh trước khi callback được đăng ký hoặc trước khi cấu hình hoàn tất, nên giai đoạn đầu bị bỏ lỡ. **Cấu hình và đăng ký callback trước khi khởi động stream.**

### 9.2. Đọc kết quả ngay sau `startAsync()`

```java
AtomicReference<String> latest = new AtomicReference<>();

stream.onEvent("demo.TaskCompleted", event ->
        latest.set(event.getString("taskId")));
stream.startAsync();

System.out.println(latest.get()); // Có thể vẫn là null.
```

Dữ liệu `null` trong ví dụ không nhất thiết chứng minh stream lỗi; đơn giản callback có thể chưa chạy. Hãy chờ tín hiệu cập nhật nếu ứng dụng cần kết quả đó để ra quyết định.

### 9.3. Khởi động và đóng trong cùng một hàm rất ngắn

```java
static void badLifecycle() {
    try (RecordingStream stream = new RecordingStream()) {
        stream.startAsync();
    }
}
```

Phương thức này **hợp lệ về cú pháp** khi ở lớp đã import `RecordingStream`, nhưng việc đóng diễn ra ngay sau `startAsync()`. Nếu mong xử lý event về sau, vòng đời này không đáp ứng mục đích.

### 9.4. Không xử lý lỗi trong callback

Nếu callback có thể ném ngoại lệ, không nên im lặng để luồng chính tiếp tục như thể mọi dữ liệu đã được xử lý. Hãy:

- Đăng ký `onError(...)` để biết vấn đề trong xử lý stream.
- Với thao tác nghiệp vụ quan trọng, xử lý ngoại lệ ở phạm vi callback và chuyển trạng thái lỗi sang luồng chờ bằng cơ chế thread-safe.
- Không để callback chờ vô hạn vào chính luồng đang phụ trách đọc event, vì có thể làm stream bị nghẽn.
- Hạn chế làm công việc nặng hoặc thao tác chặn trong callback; nếu cần, bàn giao dữ liệu sang queue/executor có giới hạn và theo dõi độ trễ xử lý ở tầng đó.

Trong `Main.java` đã kiểm thử, `onError` cập nhật `AtomicReference<Throwable>` và đánh thức latch. Lỗi vì thế được báo tới luồng chính thay vì biến thành timeout khó phân tích.

### 9.5. Coi `close()` là cách “chờ mọi thứ xong”

`close()` chủ yếu phục vụ **chấm dứt stream và giải phóng tài nguyên**. Không sử dụng việc vừa gọi `close()` như bằng chứng mọi event còn đang chờ đã đi qua callback. Thiết kế cần phân biệt tín hiệu hoàn thành của workload, tín hiệu callback đã xử lý và thời điểm dừng recording/stream.

Nếu yêu cầu lưu **toàn bộ recording** để phân tích offline, cân nhắc API ghi/dump JFR và chính sách retention thích hợp; không thay yêu cầu lưu dữ liệu bằng giả định rằng mọi callback realtime chắc chắn đã chạy.

## 10. Timeout, gián đoạn và cleanup

Trong ví dụ:

```java
if (!signal.await(10, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Timed out waiting for JFR event");
}
```

`await` trả `false` nếu hết timeout và latch chưa về 0. Đây là cơ chế chờ có **giới hạn** để một lỗi stream không làm ứng dụng bị treo vô hạn. Trong ứng dụng thực tế, thời gian chờ cần tính theo tải, độ trễ tiêu thụ và yêu cầu nghiệp vụ; không lấy 10 giây làm chuẩn chung.

Nếu thread đang chờ bị **interrupt**, `CountDownLatch.await(...)` ném `InterruptedException`. Với `try-with-resources`, stream vẫn được đóng trên đường thoát do exception. Khi viết API không thể truyền `InterruptedException` ra ngoài, thường cần phục hồi cờ interrupt bằng `Thread.currentThread().interrupt()` nếu bắt ngoại lệ, rồi xử lý dừng phù hợp.

**Phân biệt hai vấn đề:**

- **Timeout xử lý event:** callback chưa xác nhận event trong khoảng cho phép.
- **Lỗi của consumer:** callback/stream báo lỗi; cần báo nguyên nhân riêng, không giả định nó chỉ là chậm.
- **Shutdown chủ động:** ứng dụng yêu cầu dừng; phải đóng stream theo lifecycle đã định.
- **Crash/cưỡng bức dừng:** không thể đảm bảo cơ hội xử lý tiếp hoặc cleanup bình thường.

Đừng thiết kế vòng `while (...)` bận kiểm tra biến Boolean không có đồng bộ. Dùng `CountDownLatch`, `CompletableFuture` hoặc primitive đồng bộ thích hợp để vừa tránh race condition vừa không lãng phí CPU.

## 11. Kiểm thử vòng đời bất đồng bộ

Khi viết unit/integration test cho `RecordingStream`, xác nhận ít nhất:

| Trường hợp | Điều cần kiểm tra |
| --- | --- |
| Stream được bật và callback đăng ký trước `startAsync()` | Event type và handler được cấu hình đúng |
| Event mục tiêu được commit | Callback nhận được event **trong thời hạn test** |
| Callback nhận dữ liệu | Các trường lấy từ `RecordedEvent` đúng, không chỉ kiểm tra “đã có callback” |
| Đường thành công | Chỉ đánh dấu hoàn tất **sau** tín hiệu callback |
| Đường timeout | Test thất bại rõ, không in “success” giả |
| Stream báo lỗi | Lỗi được chuyển tới luồng chờ; không lặng lẽ mất |
| Exception/interrupt xảy ra | Stream vẫn được đóng trên đường thoát |
| Ứng dụng dừng bình thường | Có tín hiệu dừng, stream được close |
| Nhiều event liên tiếp | Không suy luận một latch đếm 1 là đã xử lý toàn bộ |

Với test cần nhận event của một loại cụ thể, tự định nghĩa custom event như `demo.TaskCompleted` giúp điều kiện kiểm thử có ý nghĩa hơn việc mong JVM nhất định tạo `jdk.GarbageCollection` hay `jdk.CPULoad` trong một khoảng thời gian rất ngắn.

**Không nên assert thời điểm chính xác callback chạy**, vì scheduling và JFR buffering làm thời gian giao event biến thiên. Thay vào đó xác nhận **eventually received within a reasonable bound**, và luôn giải phóng stream ở cuối test.

## 12. Checklist thực hành

Trước khi triển khai `RecordingStream.startAsync()`:

1. **Tôi có đăng ký `onEvent` và `onError` trước khi start không?**
2. **Có ai giữ tham chiếu stream và sở hữu trách nhiệm `close()` không?**
3. **Nếu là tác vụ ngắn, luồng chính chờ callback bằng gì?** Có timeout và phân biệt lỗi không?
4. **Nếu là service sống lâu, tín hiệu shutdown và cleanup được quản lý ở đâu?**
5. **Tôi có nhầm `Event.commit()` với callback đã chạy không?**
6. **Tôi có nhầm `awaitTermination()` với “đã nhận event” không?**
7. **Tôi có đang dựa vào `Thread.sleep` hoặc giả định daemon thread để quyết định kết thúc không?**
8. **Nếu cần xử lý mọi event, giao thức hoàn tất có mạnh hơn một latch đếm 1 không?**
9. **Nếu JVM bị dừng đột ngột, hệ thống có chấp nhận mất event streaming chưa xử lý không?**

**Ghi nhớ:** `startAsync()` giúp ứng dụng tiếp tục công việc mà không bị chặn bởi quá trình đọc JFR, nhưng **không bảo đảm callback đã chạy trước khi phần mã hiện tại kết thúc**. Hãy thiết kế vòng đời stream một cách tường minh: cấu hình trước khi start, chờ đúng tín hiệu hoàn tất khi cần, xử lý lỗi và timeout, rồi đóng stream tại điểm hợp lý. Mã bất đồng bộ đúng không dựa vào việc “ngủ đủ lâu” hay việc JVM có tình cờ còn sống.

### Tài liệu tham khảo chính thức

- [JEP 349 — JFR Event Streaming (Java 14)](https://openjdk.org/jeps/349).
- [Java SE API — RecordingStream](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html).
- [Java SE API — EventStream](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html).
- [Java SE API — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html).
- [Java SE API — Event](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html).
