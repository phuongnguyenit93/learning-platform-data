# Chờ RecordingStream kết thúc: có thể ngắt hoặc có thời hạn

## Mục tiêu

Trong Java Flight Recorder (JFR), `RecordingStream` cho phép một ứng dụng **nhận sự kiện JFR trong khi JVM vẫn đang chạy**. Khi gọi `startAsync()`, quá trình nhận và xử lý sự kiện diễn ra bất đồng bộ. Nếu phương thức điều phối cần **chờ tới khi stream kết thúc**, Java cung cấp hai overload:

- `awaitTermination()`: chờ cho tới khi stream kết thúc hoặc thread đang đợi bị ngắt.
- `awaitTermination(Duration timeout)`: chờ với **thời hạn tối đa**, cũng có thể bị ngắt.

Cả hai đều **trả về `void`**, đều có thể ném `InterruptedException`, và **không phải phương thức đóng stream**. Đây là khác biệt quan trọng với một số API concurrency khác như `ExecutorService.awaitTermination(...)` có giá trị trả về `boolean`.

Sau bài này, bạn sẽ:

- Hiểu vòng đời `RecordingStream`: cấu hình → `startAsync()` → xử lý sự kiện → `close()` → kết thúc.
- Nắm chính xác hợp đồng của `awaitTermination()` và `awaitTermination(Duration)`.
- Phân biệt **timeout**, **interruption** và **stream đã đóng**.
- Xử lý `InterruptedException` đúng cách, bao gồm **khôi phục interrupt flag** khi bắt ngoại lệ ở lớp không thể/không muốn truyền ngoại lệ lên trên.
- Dùng `try-with-resources` và `finally` để tránh bỏ quên việc đóng stream.
- Biết cách dùng `onClose(...)`, `CountDownLatch` hoặc cờ được cập nhật an toàn giữa các thread khi cần phân biệt đã kết thúc với đã hết thời gian chờ.
- Chọn giữa `start()` (đồng bộ), `startAsync()` cộng `awaitTermination(...)`, và `setEndTime(...)` khi muốn stream tự kết thúc theo một mốc thời gian.
- Biên dịch/chạy ví dụ **Java 17+**, xác nhận chính xác các trường hợp timeout, interrupt và đóng chủ động.

**Phạm vi Java hiện hành:** JFR Event Streaming được bổ sung trong **Java 14** ([JEP 349](https://openjdk.org/jeps/349)), và các API `jdk.jfr.consumer.RecordingStream`/`EventStream` vẫn được hỗ trợ trong Java hiện đại. Ví dụ dùng **JDK 17+**, không cần `--enable-preview` hoặc thư viện ngoài JDK.

## 1. RecordingStream dùng để làm gì?

`RecordingStream` thuộc module **`jdk.jfr`**, package **`jdk.jfr.consumer`**. Nó khởi tạo một recording stream từ **JVM hiện tại** để tiêu thụ các sự kiện JFR, chẳng hạn tải CPU, GC, hoạt động I/O, contention hoặc custom events do ứng dụng tạo ra.

Mẫu sử dụng điển hình:

~~~java
import java.time.Duration;
import jdk.jfr.consumer.RecordingStream;

// Đoạn minh họa trong một phương thức throws InterruptedException.
try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad")
          .withPeriod(Duration.ofSeconds(1));

    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(event);
    });

    stream.startAsync();
    stream.awaitTermination(Duration.ofSeconds(5));
}
~~~

Điểm đáng chú ý:

1. `enable(...)` bật loại sự kiện quan tâm.
2. `onEvent(...)` đăng ký hành động được gọi khi có event phù hợp.
3. `startAsync()` bắt đầu xử lý trên **thread khác**, cho phép thread gọi tiếp tục.
4. `awaitTermination(Duration.ofSeconds(5))` chờ **tối đa khoảng 5 giây**; nó không có trách nhiệm tự đóng stream khi hết thời hạn.
5. Khi rời `try-with-resources`, `close()` được gọi tự động để giải phóng tài nguyên.

**Không có đầu ra CPU cố định** cho ví dụ: số lượng `jdk.CPULoad` events, thời gian callback và số liệu phụ thuộc JVM, cấu hình cùng workload thực tế.

### Chờ kết thúc là gì?

“Termination” trong ngữ cảnh này chỉ việc **tiến trình xử lý sự kiện đã kết thúc, hoặc stream đã được đóng và những hành động liên quan đã hoàn thành** theo hợp đồng của `EventStream`. Nó **không** có nghĩa toàn bộ JVM dừng, tất cả thread ứng dụng hoàn thành, hay một tác vụ nghiệp vụ được xác nhận.

`RecordingStream` thực hiện quan sát/diagnostics; nó **không phải** message broker hoặc queue đảm bảo xử lý đủ mọi business event.

## 2. Vòng đời và vị trí của awaitTermination

Có thể hình dung:

~~~text
new RecordingStream()
        |
        v
enable(...), onEvent(...), onClose(...)
        |
        v
startAsync()
        |
        +----------------------------+
        |                            |
        v                            v
JFR xử lý events             Thread điều phối gọi
ở thread riêng               awaitTermination(...)
        |                            |
        |                    +-------+---------+
        |                    |       |         |
        v                    v       v         v
được yêu cầu close()       đóng   timeout   interrupt
        |                    |       |         |
        v                    |       |         |
stream kết thúc <------------+       |         |
        |                            |         |
        v                            |         |
onClose(...)                        |         |
        |                            |         |
        +------> thread chờ có thể tiếp tục <---+
                        |
                        v
            finally / try-with-resources
                     close()
~~~

Sơ đồ này mô tả **các tình huống có thể làm lời gọi chờ kết thúc**, chứ không khẳng định tất cả đều đồng thời xảy ra. Điều quan trọng là **timeout hoặc interrupt không tương đương với việc gọi `close()`**.

Trước khi chờ, hãy khởi động stream đúng cách. Với hoạt động bất đồng bộ, dùng `startAsync()`; với `start()` đồng bộ, chính lời gọi `start()` đã chặn thread hiện tại cho tới khi quá trình kết thúc.

## 3. Hai overload chính xác theo Java API

| API | Kiểu trả về | Khi nào thoát | Ngoại lệ đáng chú ý |
|---|---|---|---|
| `void awaitTermination()` | `void` | Khi các hành động kết thúc/stream đóng hoặc thread chờ bị ngắt | `InterruptedException` |
| `void awaitTermination(Duration timeout)` | `void` | Các điều kiện trên **hoặc** đạt thời hạn chờ | `InterruptedException`; `IllegalArgumentException` nếu timeout âm; `NullPointerException` nếu timeout null |

Hai phương thức này được mô tả trong interface `EventStream`, và `RecordingStream` triển khai chúng.

### 3.1. Không nhận lại `boolean`

**Sai kiểu biên dịch:**

~~~java
// Đoạn cố ý SAI, chỉ để giải thích lỗi:
boolean finished = stream.awaitTermination(Duration.ofSeconds(3));
~~~

Sai vì giá trị trả về là **`void`**, không phải `boolean`. Không thể dùng `if (stream.awaitTermination(...))`.

Một số API quen thuộc có tên tương tự nhưng hợp đồng khác, ví dụ:

~~~java
// Đoạn so sánh API, KHÔNG phải lời gọi RecordingStream:
boolean ended = executor.awaitTermination(3, TimeUnit.SECONDS);
~~~

`ExecutorService.awaitTermination(long, TimeUnit)` trả `boolean` theo hợp đồng của **executor**, nhưng không áp dụng quy tắc ấy cho JFR `RecordingStream` chỉ vì tên tương tự.

### 3.2. Không có overload nhận số mili-giây thuần túy

Hãy truyền `java.time.Duration`:

~~~java
stream.awaitTermination(Duration.ofMillis(200));
stream.awaitTermination(Duration.ofSeconds(5));
stream.awaitTermination(Duration.ofMinutes(1));
~~~

Đây là **các lời gọi minh họa**, giả định biến `stream` đã tạo, bắt đầu và phương thức xử lý `InterruptedException`.

`Duration` âm không hợp lệ. `Duration` quá ngắn có thể kết thúc đợi trước khi JVM kịp phát sự kiện có ý nghĩa; thời hạn chờ và **chu kỳ phát sự kiện** là hai thiết lập khác nhau.

**Khuyến nghị:** Khi muốn **chờ không giới hạn theo đồng hồ**, dùng overload không đối số `awaitTermination()`. Khi muốn có giới hạn rõ ràng, dùng `Duration` dương có ý nghĩa nghiệp vụ, không phụ thuộc giả định mơ hồ về `Duration.ZERO`.

## 4. Chờ không có timeout: awaitTermination()

Mẫu cơ bản:

~~~java
// Đoạn minh họa; phải có nơi khác chủ động close stream.
try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad")
          .withPeriod(Duration.ofSeconds(1));
    stream.startAsync();
    stream.awaitTermination();
}
~~~

Điều cần hiểu:

- `startAsync()` khởi động xử lý không đồng bộ.
- `awaitTermination()` **chặn thread đang gọi** cho đến khi stream kết thúc/đóng hoặc thread bị interrupt.
- Nếu không có điều kiện nào khiến stream kết thúc và không có nơi khác gọi `close()`, lời chờ **có thể kéo dài vô hạn**.
- `try-with-resources` **chỉ đóng khi control rời block**. Nếu đang kẹt chờ không giới hạn ở ngay trong block, chưa có lý do tự động để `close()` được chạy.

Do đó, với một stream dự kiến chạy liên tục, phải có **chiến lược shutdown thực sự**: shutdown hook phù hợp, signal từ component quản lý, cancel/close từ thread khác, hoặc set một thời điểm kết thúc trước khi start. Không kỳ vọng rằng câu lệnh `awaitTermination()` sẽ tự quyết định khi nào dừng.

### Khi nào thích hợp?

- Main/worker cần chờ một JFR stream chạy cho tới khi quản lý ứng dụng phát lệnh dừng.
- Một component giám sát được đóng bởi service lifecycle; thread điều phối đợi việc xử lý event kết thúc.
- Test tích hợp có một thread khác bảo đảm gọi `close()` tại thời điểm xác định.

**Không nên dùng lời chờ vô hạn** trong HTTP request thread, thread UI hoặc bất kỳ đường thực thi nào có deadline ngắn, trừ khi đó là hợp đồng đã được thiết kế rõ.

## 5. Chờ có thời hạn: awaitTermination(Duration)

~~~java
// Đoạn minh họa, giả định stream đã được startAsync().
stream.awaitTermination(Duration.ofSeconds(3));
~~~

Lời gọi này trả về khi:

1. Stream đã kết thúc/đóng và các hành động liên quan hoàn tất; **hoặc**
2. Khoảng thời gian chờ tối đa đã trôi qua; **hoặc**
3. Thread đang chờ bị interrupt, trong trường hợp này nó ném `InterruptedException`.

**Mấu chốt:** Nếu quá ba giây mà stream vẫn chạy, lời gọi **trả về bình thường (`void`)**. Nó không tự thực hiện `stream.close()`. Nó cũng không trả về một cờ cho biết “timeout” hay “đóng bình thường”.

Nếu mục tiêu nghiệp vụ là “chờ tối đa ba giây rồi ngừng quan sát”, cần **hai hành động**:

~~~java
// Đoạn minh họa; cần xử lý InterruptedException ở caller.
try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad");
    stream.startAsync();

    // Chờ tối đa 3 giây, nhưng KHÔNG tự dừng stream.
    stream.awaitTermination(Duration.ofSeconds(3));

    // Đóng rõ ràng khi không còn cần quan sát.
    stream.close();
}
~~~

Cách viết này **luôn đóng stream khi hết phần đợi**, kể cả khi lời đợi trở về do stream đã kết thúc. Nếu bạn chỉ muốn đóng **trong nhánh thực sự timeout**, phải có thêm một tín hiệu để phân biệt, chẳng hạn một callback `onClose` cập nhật trạng thái hoặc `CountDownLatch`; bản thân giá trị trả về `void` không phân biệt được.

### Dùng onClose để theo dõi stream kết thúc

~~~java
// Đoạn minh họa; cần import java.util.concurrent.atomic.AtomicBoolean.
AtomicBoolean closed = new AtomicBoolean();

try (RecordingStream stream = new RecordingStream()) {
    stream.onClose(() -> closed.set(true));
    stream.startAsync();

    stream.awaitTermination(Duration.ofSeconds(3));
    if (!closed.get()) {
        // Stream chưa được xác nhận đã đóng tại thời điểm kiểm tra.
        stream.close();
    }
}
~~~

Ví dụ chỉ mang tính minh họa về coordination: **đọc `closed.get()` không phải một đồng hồ timeout**, và giữa lần đọc cờ với `close()`, thread khác có thể đã đóng stream. Vì thế không nên đưa vào đây một giả định cần tính nguyên tử kiểu “exactly once business action”. `close()` là phần của giải phóng tài nguyên, không phải transaction.

Nếu ứng dụng cần tín hiệu kết thúc để hợp nhất nhiều futures/lifecycle objects, có thể cho `onClose` gọi `CountDownLatch.countDown()` hoặc hoàn tất `CompletableFuture`; sau đó dùng API chờ có kết quả trả về của đối tượng coordination đó. Đây là **cơ chế riêng do ứng dụng quản lý**, không phải kết quả của `RecordingStream.awaitTermination(Duration)`.

## 6. Chờ có thể bị ngắt: InterruptedException

Cả hai overload đều khai báo `throws InterruptedException`. Interruption có nghĩa **thread đang chờ** nhận tín hiệu hủy/chuyển trạng thái. Nó **không đồng nghĩa** stream JFR đã đóng.

~~~java
// Đoạn minh họa, đặt trong một phương thức.
try {
    stream.awaitTermination();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt(); // Khôi phục interrupt flag.
    // Caller cần có chính sách xử lý dừng/giải phóng stream.
}
~~~

Tại sao cần gọi `Thread.currentThread().interrupt()` trong nhiều trường hợp? Khi phương thức blocking ném `InterruptedException`, interrupt status của thread có thể đã được **xóa**. Nếu lớp hiện tại **bắt ngoại lệ và không truyền nó lên**, việc khôi phục cờ giúp các tầng điều phối bên trên vẫn biết có yêu cầu ngắt.

**Hai chiến lược đúng tùy contract:**

1. **Cho phép truyền `InterruptedException` lên caller**: khai báo `throws InterruptedException` và để caller quyết định đóng tài nguyên, hủy tác vụ hay dừng xử lý.
2. **Bắt và xử lý ngay**: trong `catch` khôi phục interrupt flag, sau đó kết thúc công việc đang làm theo chính sách của component; dùng `finally` hoặc `try-with-resources` để đóng stream.

Ví dụ robust khi phải đóng tài nguyên:

~~~java
// Đoạn minh họa; không tự động lưu toàn bộ callback trước khi đóng.
try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad");
    stream.startAsync();
    try {
        stream.awaitTermination();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        // Tiếp tục rời block để try-with-resources đóng stream.
    }
}
~~~

**Không nên bỏ qua ngoại lệ** bằng `catch (InterruptedException ignored) {}` rồi tiếp tục vòng lặp vô hạn: component mất tín hiệu shutdown và có thể không thoát đúng thời điểm.

### Sự khác biệt giữa interrupt và close

| Hành động | Ảnh hưởng trực tiếp tới thread đợi | Có tự đóng RecordingStream không? |
|---|---|---|
| `waiter.interrupt()` | `awaitTermination(...)` có thể ném `InterruptedException` | **Không** |
| Timeout của `awaitTermination(Duration)` | Lời đợi trả về bình thường | **Không** |
| `stream.close()` | Kết thúc stream, giải phóng tài nguyên; thread đợi có thể tiếp tục | **Có** |
| Rời `try (RecordingStream stream = ...)` | `close()` được gọi tự động | **Có** |
| `setEndTime(...)` trước khi start, khi đến mốc đã đặt | Stream kết thúc theo mốc thời gian đã cấu hình | **Có**, theo lifecycle của stream |

*Ghi chú:* “Có thể ném” ở hàng interrupt phản ánh tình huống thread đang hoặc sẽ thực hiện thao tác chờ interruptible. Phải xử lý cả trường hợp thread đã kết thúc chờ vì lý do khác trước khi bạn gọi `interrupt()`.

## 7. Ví dụ Java 17 hoàn chỉnh, có kết quả xác định

Ví dụ dưới đây được thiết kế để **không cần có sự kiện CPU nhất định xuất hiện**. Nó bật `jdk.CPULoad` nhằm minh họa RecordingStream nhưng chỉ in các trạng thái mà chương trình chủ động kiểm soát.

Tạo tệp **`JfrAwaitTerminationDemo.java`**:

~~~java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import jdk.jfr.consumer.RecordingStream;

public final class JfrAwaitTerminationDemo {
    static void timedWait() throws InterruptedException {
        AtomicBoolean closed = new AtomicBoolean();

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable("jdk.CPULoad")
                  .withPeriod(Duration.ofSeconds(1));
            stream.onClose(() -> closed.set(true));
            stream.startAsync();

            // Chờ tối đa 200 ms, không chủ động đóng stream.
            stream.awaitTermination(Duration.ofMillis(200));
            System.out.println("afterTimeoutClosed=" + closed.get());

            stream.close();
            stream.awaitTermination();
            System.out.println("afterCloseClosed=" + closed.get());
        }
    }

    static void interruptedWait() throws InterruptedException {
        AtomicBoolean closed = new AtomicBoolean();
        AtomicBoolean caughtInterrupt = new AtomicBoolean();
        AtomicBoolean interruptRestored = new AtomicBoolean();

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable("jdk.CPULoad")
                  .withPeriod(Duration.ofSeconds(1));
            stream.onClose(() -> closed.set(true));
            stream.startAsync();

            CountDownLatch waiting = new CountDownLatch(1);
            Thread waiter = new Thread(() -> {
                waiting.countDown();
                try {
                    stream.awaitTermination();
                } catch (InterruptedException ex) {
                    caughtInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    interruptRestored.set(
                            Thread.currentThread().isInterrupted());
                }
            }, "jfr-waiter");

            waiter.start();
            waiting.await();
            waiter.interrupt();
            waiter.join(2_000);

            System.out.println("caughtInterrupt="
                    + caughtInterrupt.get());
            System.out.println("interruptRestored="
                    + interruptRestored.get());
            System.out.println("interruptClosesStream="
                    + closed.get());

            stream.close();
            stream.awaitTermination();
            System.out.println("closedAfterExplicitClose="
                    + closed.get());
        }
    }

    public static void main(String[] args) throws InterruptedException {
        timedWait();
        interruptedWait();
    }
}
~~~

Lệnh chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 JfrAwaitTerminationDemo.java
java JfrAwaitTerminationDemo
~~~

**Đầu ra đã thực sự biên dịch và chạy kiểm chứng:**

~~~text
afterTimeoutClosed=false
afterCloseClosed=true
caughtInterrupt=true
interruptRestored=true
interruptClosesStream=false
closedAfterExplicitClose=true
~~~

Giải thích kết quả:

1. `afterTimeoutClosed=false`: sau `awaitTermination(Duration.ofMillis(200))`, stream vẫn chạy vì chương trình chưa gọi `close()`.
2. `afterCloseClosed=true`: sau `close()` và `awaitTermination()`, callback `onClose(...)` đã cập nhật cờ trạng thái.
3. `caughtInterrupt=true`: thread `jfr-waiter` đang chờ `awaitTermination()` bị ngắt và bắt được `InterruptedException`.
4. `interruptRestored=true`: thread khôi phục interrupt flag bằng `Thread.currentThread().interrupt()`.
5. `interruptClosesStream=false`: việc ngắt waiter **không** khiến `RecordingStream` bị đóng.
6. `closedAfterExplicitClose=true`: main thread gọi `close()`, chờ xử lý kết thúc, và nhận tín hiệu đã đóng.

**Ranh giới kiểm thử:** Output trên đã được xác nhận với một lần chạy JDK biên dịch `--release 17` và môi trường có JFR hoạt động. Trong môi trường đang bị shutdown hoặc gặp sự cố hệ thống khác, một stream có thể đóng sớm hơn dự kiến; không nên biến `afterTimeoutClosed=false` thành một định luật bất biến cho mọi tiến trình hoặc mọi cuộc đua thread. Ý nghĩa cần học là **timeout không tự đóng stream** và **interrupt waiter không tự đóng stream**.

**Vì sao dùng `AtomicBoolean`?** Callback `onClose` có thể chạy trên một thread khác thread đọc trạng thái. `AtomicBoolean` cung cấp khả năng quan sát giá trị giữa các threads mà không dựa vào một biến `boolean` không được đồng bộ hóa.

**Vì sao dùng `CountDownLatch`?** `waiting.countDown()` giúp main thread biết waiter đã đi vào đoạn chờ theo trình tự chương trình. Nó không đảm bảo waiter đã hoàn tất thao tác `awaitTermination()` trước lệnh `interrupt()`; tuy vậy nếu interrupt đến trước thao tác blocking, thao tác chờ interruptible vẫn sẽ nhận tín hiệu ngắt. Đây là pattern kiểm thử lifecycle, không phải bằng chứng chính xác tới từng nanosecond.

**Vì sao có `waiter.join(2_000)`?** Test không muốn đợi vô hạn cho thread mẫu. Trong ứng dụng thật, nếu waiter vẫn sống sau thời hạn join, phải có cơ chế báo lỗi/hủy phù hợp; đừng chỉ in `caughtInterrupt=false` rồi mặc định thành công. Mã mẫu có `close()` phía sau để đảm bảo stream được dọn dẹp.

## 8. Nếu cần biết chờ đã timeout hay đã kết thúc, dùng tín hiệu riêng

Chính `awaitTermination(Duration)` trả về `void` nên không cung cấp kết quả phân biệt. Một cách đơn giản để **có giá trị boolean của hoạt động chờ** là dùng `CountDownLatch` với `onClose`:

~~~java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import jdk.jfr.consumer.RecordingStream;

// Đoạn minh họa trong phương thức throws InterruptedException.
CountDownLatch closed = new CountDownLatch(1);

try (RecordingStream stream = new RecordingStream()) {
    stream.onClose(closed::countDown);
    stream.enable("jdk.CPULoad");
    stream.startAsync();

    boolean closedWithinTime =
            closed.await(3, TimeUnit.SECONDS);

    if (!closedWithinTime) {
        // Quyết định dừng quan sát nếu quá deadline.
        stream.close();
    }
}
~~~

**Đọc đúng kết quả:**

- `CountDownLatch.await(long, TimeUnit)` **trả boolean**, phản ánh latch đã đạt 0 trong khoảng chờ hay chưa.
- Điều này **khác API `RecordingStream.awaitTermination(Duration)`** vốn trả `void`.
- `onClose` là hành động do stream gọi khi nó được đóng; một callback có thể bị trễ so với khoảnh khắc tín hiệu dừng được yêu cầu. Vì thế kết quả phản ánh **tín hiệu callback**, không phải một phép đo chính xác thời điểm stop tại cấp nanosecond.
- Nếu caller bị interrupt trong lúc `closed.await(...)`, `InterruptedException` phải được truyền/khôi phục và `try-with-resources` vẫn bảo đảm gọi `close()`.

**Đừng dùng latch làm một transaction guarantee.** Đóng JFR stream không bảo đảm từng event đang buffer đã được chuyển tới một hệ thống nghiệp vụ. Với dữ liệu giám sát, hãy định nghĩa chính sách chấp nhận mất samples/buffer và kiểm tra dữ liệu thực thu được.

## 9. Tự động dừng stream theo đồng hồ: setEndTime(...)

Một cách khác để tránh chờ vô hạn là **cấu hình điểm kết thúc của chính stream** trước khi start:

~~~java
import java.time.Instant;
import jdk.jfr.consumer.RecordingStream;

// Đoạn minh họa trong phương thức throws InterruptedException.
try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad");
    stream.setEndTime(Instant.now().plusSeconds(5));
    stream.startAsync();
    stream.awaitTermination();
}
~~~

Theo API `EventStream.setEndTime(Instant)`, khi đến điểm kết thúc đã thiết lập, stream được đóng. Phương thức này phải được gọi **trước khi start**, nếu stream đã bắt đầu thì có thể ném `IllegalStateException`.

**Phân biệt:**

| Mục đích | Công cụ phù hợp |
|---|---|
| “Main thread chỉ đợi tối đa 5 giây rồi tiếp tục làm việc” | `awaitTermination(Duration.ofSeconds(5))` |
| “Bản thân stream phải kết thúc gần thời điểm X” | `setEndTime(Instant X)` trước `startAsync()` |
| “Yêu cầu dừng stream ngay bây giờ” | `stream.close()` |
| “Đợi cho tới lúc có tín hiệu đã đóng” | `awaitTermination()` hoặc `onClose` + latch/future |
| “Một thread quản lý yêu cầu hủy chờ” | `waiter.interrupt()` rồi xử lý `InterruptedException` |
| “Biết chắc latch hoàn thành trước deadline hay không” | `CountDownLatch.await(timeout, unit)` (boolean) |

Các cơ chế có thể **kết hợp**: đặt end time của stream, sau đó chờ có một giới hạn an toàn riêng cho caller; khi hết giới hạn, đóng/huỷ tài nguyên nếu chính sách yêu cầu.

Đừng giả định `setEndTime` sẽ chạy đúng từng milli/microsecond trong mọi môi trường: streaming events phụ thuộc quá trình xử lý và scheduling. Nếu logic nghiệp vụ đòi một deadline tuyệt đối, dùng hạ tầng timeouts/cancellation của ứng dụng chứ không biến JFR thành đồng hồ giao dịch.

## 10. So sánh start(), startAsync() và awaitTermination()

| Lời gọi | Ảnh hưởng tới thread gọi | Khi dùng |
|---|---|---|
| `start()` | Chạy xử lý các event actions **ngay trên thread hiện tại**, thường chặn cho tới khi stream đóng | Một thread chuyên dụng dành riêng cho giám sát |
| `startAsync()` | Khởi chạy xử lý ở **thread khác**, trả quyền điều khiển cho caller | Cần tiếp tục làm công việc khác hoặc phối hợp shutdown |
| `awaitTermination()` | Thread caller chờ không có timeout riêng (có thể bị interrupt) | Caller muốn đợi stream đã chạy kết thúc |
| `awaitTermination(Duration)` | Caller chờ có thời hạn riêng (có thể bị interrupt) | Cần giới hạn thời gian block |
| `close()` | Yêu cầu stream dừng và giải phóng tài nguyên | Shutdown, hết thời hạn nghiệp vụ, kết thúc test |

Tránh thiết kế như sau:

~~~java
// Đoạn minh họa lỗi thiết kế: stream chạy trong cùng thread.
stream.start();       // Có thể chặn rất lâu.
stream.awaitTermination(); // Có thể không bao giờ đi tới dòng này.
~~~

Nếu muốn gọi `awaitTermination(...)` ngay sau khi start mà caller vẫn giữ quyền điều khiển, dùng `startAsync()`. Nếu chọn `start()` đồng bộ, đặt nó trên thread chuyên dụng và đảm bảo có nơi khác đóng stream.

## 11. Các lỗi hay gặp

| Sai lầm | Vì sao nguy hiểm/sai | Cách sửa |
|---|---|---|
| Dùng `if (stream.awaitTermination(timeout))` | Phương thức trả `void`, lỗi compile | Tự quản lý completion flag/latch nếu cần boolean |
| Nhầm API với `ExecutorService.awaitTermination` | Executor API trả `boolean`, JFR API không | Đọc đúng Javadoc `RecordingStream`/`EventStream` |
| Nghĩ hết timeout là stream tự dừng | Timeout chỉ giới hạn **lời chờ** | Gọi `close()` nếu chính sách yêu cầu dừng |
| Ngắt waiter và nghĩ JFR đã dừng | Interrupt tác động thread chờ, không phải lifecycle stream | Đóng stream rõ ràng khi cần shutdown |
| Bắt `InterruptedException` rồi bỏ qua | Mất tín hiệu hủy, shutdown có thể trễ | Propagate hoặc khôi phục interrupt flag |
| Gọi `awaitTermination()` khi không có lối thoát | Có thể block vô hạn | Cơ chế shutdown, thời hạn hoặc `setEndTime(...)` |
| Gọi `start()` rồi mong ngay sau đó được await | `start()` đã block trong thread hiện tại | Dùng `startAsync()` nếu cần quản lý bất đồng bộ |
| Đọc `boolean` giữa threads không đồng bộ | Có thể không thấy cập nhật đúng | Dùng `AtomicBoolean`, latch/future hoặc đồng bộ phù hợp |
| Dùng một timeout rất ngắn để “đợi đủ events” | Events được phát theo batch/period và có độ trễ | Chọn thời hạn thu thập dựa trên workload; không dùng event count làm đồng hồ |
| Đóng stream từ nhánh code nhưng quên finally | Rò rỉ tài nguyên khi lỗi/interrupt | `try-with-resources` hoặc `finally` |
| Giả định `onClose` đồng nghĩa mọi event đã xử lý nghiệp vụ | JFR là công cụ diagnostics, không phải durable event bus | Tách yêu cầu giao dịch khỏi stream quan sát |
| Gọi `setEndTime` sau `startAsync()` | Không hợp lệ theo lifecycle | Thiết lập trước khi khởi động |
| Dùng `Duration` âm | API ném `IllegalArgumentException` | Kiểm tra timeout không âm và có ý nghĩa |
| Gọi `awaitTermination(Duration)` mà bỏ qua ngoại lệ | `InterruptedException` là checked exception | Khai báo `throws` hoặc dùng `try/catch` phù hợp |
| Mặc định “không có event” là “không có hoạt động” | JFR có sampling/batching/threshold; timeout không ép có event | Kiểm tra config/period/threshold, không suy luận quá mức |

## 12. Quy trình thiết kế shutdown cho một component quan sát

Khi dùng JFR trong một service hiện đại, hãy phân biệt rõ **lifecycle của nguồn dữ liệu** với **lifecycle của thread điều phối**:

1. **Khởi tạo và cấu hình**: tạo `RecordingStream`, bật những event types cần thiết, đăng ký `onEvent`, `onError` và `onClose` nếu có ích.
2. **Chọn mô hình chạy**: `startAsync()` nếu caller còn công việc hoặc phải quản lý deadline; `start()` cho thread chuyên dụng.
3. **Xác định cơ chế dừng**: shutdown từ application lifecycle, `close()` chủ động, hoặc `setEndTime(...)` trước start.
4. **Chọn cách chờ**: `awaitTermination()` khi thật sự có người khác dừng stream; `awaitTermination(Duration)` khi caller có thời hạn.
5. **Nếu timeout**: nhớ `void` không cho biết lý do trở về; dùng cờ/latch nếu phải phân biệt. Đóng stream có chủ đích theo policy.
6. **Nếu bị interrupt**: truyền ngoại lệ hoặc khôi phục flag khi bắt; giải phóng stream qua `finally`/`try-with-resources`.
7. **Nếu cần xác nhận hoàn thành**: `onClose` + `CountDownLatch`/`CompletableFuture` và một thời hạn riêng cho tín hiệu đó.
8. **Dọn tài nguyên**: đóng stream; nếu lưu recording ra file thì quản lý quyền truy cập, dung lượng và dữ liệu nhạy cảm.
9. **Test ba trường hợp**: kết thúc bình thường, timeout nhưng stream còn mở, interruption không tự đóng stream. Tránh phụ thuộc vào lượng CPU/GC events không xác định.

**Khi cần logging:** ghi thời gian bắt đầu/chờ/đóng và lý do shutdown bằng hệ thống log của service; không cho rằng JFR đã tự ghi dấu vết nghiệp vụ theo yêu cầu.

## 13. Bài tự kiểm tra

**Câu 1.** Đoạn nào đúng cú pháp?

~~~java
// A (SAI)
boolean success = stream.awaitTermination(Duration.ofSeconds(2));

// B (ĐÚNG nếu caller xử lý InterruptedException)
stream.awaitTermination(Duration.ofSeconds(2));
~~~

**Đáp án:** B. Overload JFR trả `void`, không có trạng thái `boolean`.

**Câu 2.** `awaitTermination(Duration.ofSeconds(2))` trả về sau hai giây. Stream có chắc đã đóng?

**Đáp án:** Không. Lời chờ có thể hết timeout mà stream vẫn chạy. Cần tín hiệu khác hoặc gọi `close()` nếu phải dừng.

**Câu 3.** Một worker bị `interrupt()` trong lúc chờ `stream.awaitTermination()`. Stream có tự bị đóng không?

**Đáp án:** Không. Interruption nhắm tới thread đợi. `InterruptedException` phải được xử lý, và stream phải được đóng theo chính sách riêng.

**Câu 4.** Vì sao cần `Thread.currentThread().interrupt()` trong `catch (InterruptedException ex)` khi không propagate?

**Đáp án:** Để khôi phục cờ interrupt có thể đã bị xóa khi API ném ngoại lệ, giúp tầng trên biết thread cần hủy/dừng.

**Câu 5.** Bạn muốn method chỉ chờ tối đa 10 giây rồi **đóng stream**, cần làm gì?

**Đáp án:** `startAsync()`, `awaitTermination(Duration.ofSeconds(10))` trong block có quản lý ngoại lệ, sau đó `close()` (hoặc để `try-with-resources` đóng khi rời block). Không chỉ gọi await rồi tin nó đã dừng.

**Câu 6.** Nếu mục tiêu là stream tự đóng sau khoảng 10 giây, thay vì chỉ caller chờ 10 giây, dùng API nào?

**Đáp án:** `stream.setEndTime(Instant.now().plusSeconds(10))` **trước `startAsync()`**, rồi chờ/làm việc theo policy.

**Câu 7.** Có thể dùng gì để biết callback `onClose` đã chạy trong một deadline?

**Đáp án:** `CountDownLatch` và `closed.await(timeout, TimeUnit)` để nhận `boolean`, hoặc một `CompletableFuture` riêng. Đừng gán kết quả đó cho `RecordingStream.awaitTermination(Duration)`.

**Câu 8.** Một phiên `RecordingStream` không có sự kiện `jdk.CPULoad` trong 200 ms. Có phải stream hỏng?

**Đáp án:** Không có đủ dữ kiện. Event có chu kỳ/sampling và xử lý theo batch, trong khi timeout 200 ms quá ngắn để bảo đảm nhận mẫu. Kiểm tra settings, thời gian ghi và trạng thái lifecycle.

## Tài liệu chính thức

- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): streaming API được đưa vào Java 14.
- [Oracle Java 17 — `RecordingStream`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): `startAsync`, `close`, `awaitTermination()` và `awaitTermination(Duration)`.
- [Oracle Java 17 — `EventStream`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): hợp đồng chính thức của hai overload await; `onClose`, `onError`, `setEndTime` và lifecycle.
- [Oracle Java 25 — `EventStream`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): đối chiếu rằng hai overload `void awaitTermination(...)` vẫn hiện diện trong Java hiện đại.
- [Oracle Java 17 — JFR API Programmer's Guide](https://docs.oracle.com/en/java/javase/17/jfapi/index.html): kiến trúc recordings, streaming, events và cách sử dụng.
- [Java SE 17 — `InterruptedException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InterruptedException.html): cơ chế interruption của thread.
- [Java SE 17 — `Thread.interrupt()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#interrupt()): cách gửi và kiểm tra tín hiệu interrupt.
- [Java SE 17 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): chờ completion signal có thời hạn, trả `boolean`.
- [Java SE 17 — `Duration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): biểu diễn thời hạn chờ.
- [Java SE 17 — `AtomicBoolean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html): đọc/ghi cờ trạng thái xuyên threads.

**Ghi nhớ:** `RecordingStream.awaitTermination(Duration)` là một **lời chờ có thời hạn**, **không phải lệnh timeout để dừng JFR**. `awaitTermination()` là **lời chờ có thể bị ngắt**, **không tự đóng stream khi interrupt**. Cả hai trả về **`void`** và có thể ném `InterruptedException`. Muốn dừng thật sự, hãy thiết kế `close()`/`setEndTime(...)`; muốn nhận tín hiệu kết thúc có boolean, dùng `onClose` với một cơ chế đồng bộ riêng.