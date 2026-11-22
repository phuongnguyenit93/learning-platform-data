# Thứ tự sự kiện JFR và tùy chọn `setOrdered` trong `RecordingStream`

## 1. Mục tiêu và kết luận cốt lõi

**Java Flight Recorder (JFR)** ghi nhận các sự kiện liên quan JVM và ứng dụng. Với **`jdk.jfr.consumer.RecordingStream`**, chương trình Java có thể đăng ký callback `onEvent(...)` và nhận dữ liệu sự kiện liên tục từ **JVM hiện tại**, thay vì chỉ đọc một file recording sau khi kết thúc.

Từ **Java 14**, JEP 349 đưa tính năng **JFR Event Streaming** vào Java. Trong API này, người học thường cần biết: *thứ tự callback có phản ánh đúng thứ tự thời gian của mọi sự kiện hay không?* Và khi nào nên gọi:

```java
stream.setOrdered(true);  // Sắp xếp theo thời gian trong từng batch.
stream.setOrdered(false); // Tắt việc sắp xếp do stream thực hiện.
```

Đây là **hai cấu hình lựa chọn**, không phải yêu cầu gọi liên tiếp trên cùng stream: trong thực tế hãy **chọn một** tùy mục đích xử lý.

Theo Javadoc chính thức Java 17 và Java 25:

- Sự kiện đến theo **các batch** (*lô sự kiện*). Với **`setOrdered(true)`**, các sự kiện **trong cùng một batch** được sắp theo thứ tự thời gian dựa trên **thời điểm kết thúc sự kiện** (`RecordedEvent.getEndTime()`).
- **Không có cam kết thứ tự thời gian toàn cục giữa các batch**: một sự kiện của batch sau vẫn có thể mang thời điểm kết thúc **sớm hơn** một sự kiện đã được callback trong batch trước.
- **`setOrdered(false)`** bỏ thao tác sắp xếp để tránh chi phí sorting không cần thiết khi ứng dụng không quan tâm thứ tự; điều đó **không bắt buộc** các sự kiện phải xuất hiện lộn xộn. Chúng vẫn *có thể tình cờ* đến theo thời gian.
- Hai giá trị chỉ ảnh hưởng **thứ tự phân phối event tới callback**, **không** thay đổi thời điểm sự kiện thật xảy ra, timestamp được ghi, loại event đã enable, tốc độ tạo event, vòng đời stream hoặc giới hạn giữ dữ liệu.

**Điểm cần phân biệt:** câu mô tả phương thức `setOrdered` trong Javadoc nói đến *chronological order / time committed to stream*, trong khi phần tổng quan `EventStream` giải thích rõ **sắp theo end time trong mỗi batch** và chỉ có bảo đảm trong phạm vi batch. Khi cần kiểm chứng, dùng **`RecordedEvent.getEndTime()`** và đối chiếu theo **batch**, không tự suy ra mọi callback của cả ứng dụng sẽ có timestamp tăng mãi mãi.

Bài sử dụng API **ổn định Java 17+** có mặt trong JDK hiện đại, không cần `--enable-preview` hay workaround từ phiên bản cũ. Mọi mã chạy độc lập trong bài đã được kiểm tra bằng `javac --release 17`.

Sau khi học, bạn sẽ biết tạo stream, chọn `true`/`false` phù hợp, hiểu `onFlush`, kiểm chứng thứ tự bằng dữ liệu thay vì giả định, tránh nhầm timestamp/sequence và xử lý trường hợp cần thứ tự toàn cục.

## 2. Các khái niệm cần hiểu trước

### 2.1. `Event`, `RecordedEvent` và callback

Một event JFR là thông tin về một hoạt động. Ứng dụng có thể tự định nghĩa một class mở rộng `jdk.jfr.Event` hoặc sử dụng những loại event có sẵn như `jdk.CPULoad` và `jdk.GarbageCollection`.

Khi stream xử lý dữ liệu recording, callback nhận **`jdk.jfr.consumer.RecordedEvent`**:

```java
stream.onEvent("jdk.CPULoad", event -> {
    System.out.println(event.getEndTime());
});
```

Đây là **snippet** cần đặt trong phạm vi có `RecordingStream stream` và bật event cần thiết. `getEndTime()` trả thời điểm kết thúc event dưới dạng `Instant`. Nếu event có thời lượng, `getStartTime()` và `getEndTime()` có thể khác nhau.

Không nhầm:

- **Thời điểm bắt đầu:** `event.getStartTime()` — thời điểm bắt đầu hoạt động được ghi.
- **Thời điểm kết thúc:** `event.getEndTime()` — thời điểm kết thúc, làm mốc sắp xếp trong batch theo tài liệu `EventStream`.
- **Thời điểm callback chạy:** khi consumer thực sự xử lý event; có thể muộn hơn do buffer, chunk/flush, scheduling, tải và hoạt động stream.
- **Trường sequence nghiệp vụ:** một `long sequence` bạn tự lưu trong event; **không tự thay thế timestamp** và không tự chứng minh mọi nguồn đã được xếp theo quan hệ nhân quả.

### 2.2. Batch và `onFlush(Runnable)`

`EventStream` giao dữ liệu theo từng **batch**. Khi một batch kết thúc, stream có thể gọi hành động đã đăng ký:

```java
stream.onFlush(() -> {
    System.out.println("Finished one batch");
});
```

Callback `onFlush` là nơi phù hợp để tổng hợp hoặc đẩy dữ liệu đã xử lý của batch ra nơi khác, khi JVM chuẩn bị batch kế tiếp.

Hình dung:

```text
Sự kiện được ghi ở JVM
       |
       v
JFR repository / dữ liệu có sẵn tại một lần flush
       |
       v
Batch A: [event A1, A2, A3] -- sắp xếp nếu ordered=true
       |
       v
onEvent(A1), onEvent(A2), onEvent(A3), onFlush()
       |
       v
Batch B: [event B1, B2] -- sắp xếp độc lập
       |
       v
onEvent(B1), onEvent(B2), onFlush()
```

**Quan trọng:** thứ tự theo end time chỉ có bảo đảm **trong tập sự kiện sẵn có ở cùng batch**. Một event đến từ thread khác hoặc chỉ vừa được công bố ở batch tiếp theo có thể có end time **nhỏ hơn** event của batch trước.

### 2.3. Thứ tự callback không phải bằng chứng quan hệ nhân quả

Giả sử event X bắt đầu trước event Y nhưng hoàn thành sau Y. Nếu sắp theo **end time**, Y có thể được callback trước X — **đúng** với quy tắc JFR, không phải lỗi. Một timestamp bằng nhau cũng không tự xác định một tie-breaker nghiệp vụ ổn định.

Với xử lý nghiệp vụ cần “bước 1 phải đến trước bước 2”, hãy ghi thêm **request/trace ID** hoặc **sequence** đáng tin cậy và thiết kế chính sách đồng bộ/ghép sự kiện riêng. `setOrdered(true)` không thiết lập *happens-before* giữa hai thread, không xây dựng total order cho toàn hệ thống và không cung cấp bảo đảm exactly-once.

## 3. Cú pháp, nơi khai báo và phạm vi tác dụng

Lớp `RecordingStream` implement interface `EventStream`. `setOrdered(boolean)` được định nghĩa trong `jdk.jfr.consumer.EventStream` và được `RecordingStream` triển khai.

**Bật sắp xếp khi cần thời gian tương đối trong batch:**

```java
try (var stream = new jdk.jfr.consumer.RecordingStream()) {
    stream.setOrdered(true);
    stream.enable("jdk.CPULoad");
    stream.onEvent("jdk.CPULoad",
                   event -> System.out.println(event.getEndTime()));
    stream.start(); // Chặn luồng hiện tại tới khi stream đóng.
}
```

Đây là **snippet minh họa cách cấu hình và lifecycle**. Trong service dài hạn phải có một luồng khác/điều kiện để gọi `close()` hoặc dùng `startAsync()`. Ví dụ không phải chương trình có stdout cố định.

**Tắt sorting nếu chỉ tính tổng hợp không phụ thuộc thứ tự:**

```java
try (var stream = new jdk.jfr.consumer.RecordingStream()) {
    stream.setOrdered(false);
    stream.enable("jdk.CPULoad");
    stream.onEvent("jdk.CPULoad",
                   event -> updateMetrics(event));
    stream.start();
}
```

Đoạn thứ hai giả định tồn tại phương thức `updateMetrics(RecordedEvent)` trong ứng dụng; nó là **snippet minh họa**, chưa phải chương trình chạy độc lập. Ứng dụng chỉ đếm, cộng tổng hoặc gom histogram không cần sorting có thể chọn `false`.

**Thông lệ tốt:** chọn và đặt `setOrdered(...)` **trước khi `start()`/`startAsync()`** cùng với `enable` và callbacks, giúp policy rõ ràng từ batch đầu tiên. Đừng khẳng định gọi setter sau khi bắt đầu *luôn* là lỗi: Javadoc `setOrdered` không mô tả cùng hạn chế “must be set before starting” như một số setter thời điểm bắt đầu/kết thúc.

### 3.1. Có bắt buộc gọi setter không?

Không. Javadoc `EventStream` mô tả việc sắp xếp event trong batch như hành vi thông thường; bạn có thể gọi `setOrdered(true)` tường minh để thể hiện ý định phụ thuộc thứ tự. Nếu không quan tâm, dùng `setOrdered(false)` để tránh công việc sắp xếp. Khi đo hiệu năng, ghi rõ JVM/JDK và cấu hình thay vì ngầm coi “bỏ sorting chắc chắn nhanh hơn X%”.

### 3.2. Không nhầm `RecordingStream` với `EventStream.openFile`

| Kiểu stream | Mục đích | Có `setOrdered`? |
| --- | --- | --- |
| `RecordingStream` | Vừa thu thập vừa tiêu thụ JFR của JVM hiện tại | Có |
| `EventStream.openFile(Path)` | Đọc các sự kiện từ file `.jfr` đã có | Có |
| `EventStream.openRepository()` | Đọc sự kiện từ repository theo API | Có |
| `jdk.jfr.Recording` | Điều khiển một recording và dump dữ liệu | Không có `setOrdered` của stream consumer |

Tài liệu Java 17/25 vẫn công bố `setOrdered` trong `EventStream` và `RecordingStream`. Dù `EventStream.openFile` hữu ích để kiểm thử trên dữ liệu cố định, **câu hỏi bài học là `RecordingStream`**, và cùng một quy tắc ordering áp dụng cho interface mà nó triển khai.

## 4. Chương trình Java 17+: xử lý stream trong JVM hiện tại

Để không phụ thuộc vào GC/CPU events vốn thay đổi theo máy, chương trình tạo một event tùy chỉnh tên `demo.OrderingPulse`. Nó chạy stream ở cả hai chế độ, đợi nhận **ít nhất một** event trong tối đa 10 giây, và kiểm tra non-decreasing end time **trong các batch đã quan sát** khi `ordered=true`.

**Tệp `RecordingStreamOrderingDemo.java`:**

```java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public class RecordingStreamOrderingDemo {
    @Name("demo.OrderingPulse")
    static class Pulse extends Event {
        long sequence;
    }

    static void observe(boolean ordered) throws Exception {
        CountDownLatch seen = new CountDownLatch(1);
        AtomicReference<Instant> previous = new AtomicReference<>();
        AtomicBoolean orderedInsideBatch = new AtomicBoolean(true);

        try (RecordingStream stream = new RecordingStream()) {
            stream.setOrdered(ordered);
            stream.setMaxAge(Duration.ofMinutes(2));
            stream.setMaxSize(8L * 1024 * 1024);
            stream.enable(Pulse.class).withoutThreshold();

            stream.onEvent("demo.OrderingPulse", event -> {
                Instant time = event.getEndTime();
                Instant old = previous.getAndSet(time);
                if (old != null && time.isBefore(old)) {
                    orderedInsideBatch.set(false);
                }
                seen.countDown();
            });

            stream.onFlush(() -> previous.set(null));
            stream.startAsync();

            for (long i = 0; i < 100; i++) {
                Pulse p = new Pulse();
                p.sequence = i;
                p.commit();
            }

            boolean received = seen.await(10, TimeUnit.SECONDS);
            System.out.println("orderedFlag=" + ordered);
            System.out.println("observedAnEvent=" + received);

            if (ordered) {
                System.out.println("orderedWithinObservedBatches=" +
                        orderedInsideBatch.get());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        observe(true);
        observe(false);
    }
}
```

**Biên dịch và chạy Java 17+:**

```bash
javac --release 17 -encoding UTF-8 RecordingStreamOrderingDemo.java
java RecordingStreamOrderingDemo
```

**Kết quả quan sát được trên HotSpot JDK 24:**

```text
orderedFlag=true
observedAnEvent=true
orderedWithinObservedBatches=true
orderedFlag=false
observedAnEvent=true
```

Các dòng `observedAnEvent` phụ thuộc khả năng JFR hoạt động, tiến độ flush và tốc độ môi trường: nếu không nhận được event trước deadline, có thể là `false`. Ví dụ có chủ ý **không in số sự kiện cố định** hoặc thứ tự các `sequence`; việc callback được gọi bất đồng bộ không cho phép giả định nhận đủ 100 event trong 10 giây. Trong môi trường JFR không khả dụng hoặc repository không truy cập được, khởi tạo `RecordingStream` có thể lỗi.

### 4.1. Phân tích từng cấu trúc

1. `@Name("demo.OrderingPulse")` đặt tên loại event tự định nghĩa. `Pulse extends Event` có một component dữ liệu `sequence`, được cập nhật và `commit()` trong vòng lặp.
2. `setOrdered(ordered)` đặt chế độ cho stream. Cùng class được chạy với hai giá trị khác nhau, dễ so sánh không cần hai lớp riêng.
3. `setMaxAge` và `setMaxSize` giới hạn lịch sử lưu trên JFR disk repository; chúng **khác** chuyện sắp xếp callback. Đây là cấu hình vận hành bổ trợ, không phải điều kiện bắt buộc của `setOrdered`.
4. `stream.enable(Pulse.class).withoutThreshold()` cho phép thu thập event tùy chỉnh với threshold phù hợp cho demo.
5. `stream.onEvent("demo.OrderingPulse",...)` nhận `RecordedEvent`; `getEndTime()` được so với giá trị trước đó qua `AtomicReference`. Nếu nhỏ hơn, chương trình đánh dấu thứ tự giảm.
6. `onFlush(() -> previous.set(null))` **đặt lại mốc ở cuối batch**, để không nhầm một event của batch sau có end time nhỏ hơn batch trước là vi phạm quy tắc ordering.
7. `startAsync()` chuyển xử lý callbacks sang luồng riêng. `CountDownLatch` đợi nhận ít nhất một event; chương trình không dùng `Thread.sleep(...)` như bằng chứng đã có flush.
8. `try-with-resources` bảo đảm `close()`, tránh để luồng JFR chạy vô thời hạn. Ở nhánh `ordered=false`, không kiểm tra/tuyên bố gì về thứ tự; mặc dù events *có thể* đến theo thời gian, không có bảo đảm cần dựa vào.

**Hạn chế kiểm thử:** `orderedWithinObservedBatches=true` chỉ phản ánh dữ liệu **đã callback** trong lần chạy đó, không chứng minh toàn bộ stream đã nhận đủ event hoặc mọi batch có kích thước lớn. `setOrdered(true)` có ngữ nghĩa từ Javadoc; chương trình là minh họa để thấy cách kiểm tra, không phải bằng chứng thay thế đặc tả.

### 4.2. Vì sao không in và so sánh `sequence` để kiểm tra sắp xếp thời gian?

`sequence` trong `Pulse` là thứ tự vòng lặp tạo sự kiện. Nó không phải một clock chuẩn, cũng không luôn khớp với `getEndTime()` khi event có thời lượng hoặc được tạo từ nhiều thread. Vì vậy, dù `setOrdered(true)` hoạt động đúng theo **end time trong batch**, `sequence` không được dùng làm tiêu chuẩn duy nhất để nhận định sort đúng/sai.

Nếu mục tiêu nghiệp vụ đòi hỏi một **thứ tự logic** (ví dụ các bước transaction), hãy đưa sequence/correlation ID vào event và dùng cơ chế ứng dụng để xác nhận chuỗi sự kiện, thay vì suy ra thứ tự logic chỉ từ timestamp JFR.

## 5. Ví dụ có kết quả ổn định: kiểm tra cùng file JFR với `true` và `false`

Live streaming có timing bất đồng bộ. Để kiểm tra hành vi `setOrdered` mà không phụ thuộc tốc độ nhận realtime, có thể tự tạo một file JFR chứa **10 custom events**, đọc file đó qua `EventStream.openFile(...)` hai lần, rồi so sánh số event và thuộc tính thứ tự theo batch.

Ví dụ này vẫn sử dụng **cùng `EventStream.setOrdered` mà `RecordingStream` triển khai**. Nó không nhằm chứng minh rằng `false` nhất thiết làm events đảo lộn; nó kiểm tra hai chế độ tiêu thụ dữ liệu cố định.

**Tệp `OrderedFileEventsDemo.java` — Java 17+:**

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.EventStream;

public class OrderedFileEventsDemo {
    @Name("demo.OrderedPulse")
    static class Pulse extends Event {
        int index;
    }

    record Stats(int count, boolean monotonicWithinBatches,
                 int batches) {}

    static Stats consume(Path file, boolean ordered) throws Exception {
        AtomicInteger count = new AtomicInteger();
        AtomicInteger batches = new AtomicInteger();
        AtomicReference<Instant> last = new AtomicReference<>();
        boolean[] monotonic = {true};

        try (EventStream events = EventStream.openFile(file)) {
            events.setOrdered(ordered);
            events.onEvent("demo.OrderedPulse", event -> {
                Instant end = event.getEndTime();
                Instant previous = last.get();

                if (previous != null && end.isBefore(previous)) {
                    monotonic[0] = false;
                }

                last.set(end);
                count.incrementAndGet();
            });
            events.onFlush(() -> {
                batches.incrementAndGet();
                last.set(null);
            });
            events.start();
        }

        return new Stats(count.get(), monotonic[0], batches.get());
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("jfr-order-demo-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(Pulse.class).withoutThreshold();
                recording.start();

                for (int i = 0; i < 10; i++) {
                    Pulse pulse = new Pulse();
                    pulse.index = i;
                    pulse.commit();
                }

                recording.stop();
                recording.dump(file);
            }

            Stats ordered = consume(file, true);
            Stats unordered = consume(file, false);

            System.out.println("orderedCount=" + ordered.count());
            System.out.println("orderedWithinBatchNondecreasing=" +
                    ordered.monotonicWithinBatches());
            System.out.println("unorderedCount=" + unordered.count());
            System.out.println("sameCount=" +
                    (ordered.count() == unordered.count()));
            System.out.println("orderedFlushCallbacks=" + ordered.batches());
            System.out.println("unorderedFlushCallbacks=" + unordered.batches());
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

**Biên dịch và chạy:**

```bash
javac --release 17 -encoding UTF-8 OrderedFileEventsDemo.java
java OrderedFileEventsDemo
```

**Kết quả đã kiểm chứng trên HotSpot JDK 24:**

```text
orderedCount=10
orderedWithinBatchNondecreasing=true
unorderedCount=10
sameCount=true
orderedFlushCallbacks=1
unorderedFlushCallbacks=1
```

Số `FlushCallbacks` phản ánh cách JFR chia file trong **lần chạy cụ thể**, có thể khác trên một JVM/điều kiện ghi dữ liệu khác. Khi file đọc được chứa đúng 10 custom events, số đếm cho mỗi cách đọc sẽ là 10. Kết quả `sameCount=true` chứng minh việc bật/tắt sorting không có ý nghĩa lọc bớt sự kiện. Trên môi trường khác, thời điểm flush/đóng chunk có thể khác; **không dùng số batch cố định làm điều kiện đúng/sai cho API**.

### 5.1. Tại sao so sánh theo `getEndTime()` và reset theo `onFlush`?

- Bản ghi JFR có thể chứa event có thời lượng, nên `getStartTime()` và `getEndTime()` khác nhau; đặc tả ordering ở phần tổng quan `EventStream` nói tới end time.
- `last` là mốc trong **batch hiện tại**. Sau `onFlush`, mốc đặt lại `null` để không so một batch mới với batch trước.
- `ordered.monotonicWithinBatches()` phản ánh điều kiện “timestamp không giảm trong các event đã nhận **của cùng batch**”, không đánh giá global order.
- Hàm `consume(file, false)` vẫn có tính toán `monotonic` phục vụ kiểm chứng nhưng chương trình không gán ý nghĩa bảo đảm cho kết quả đó. `setOrdered(false)` **bỏ cam kết sorting**, không có nghĩa mọi batch chắc chắn chứa inversion.
- `Files.deleteIfExists(file)` dọn file tạm khi xong, tránh giữ recording chứa thông tin nội bộ không cần thiết.

### 5.2. Có bảo đảm `getEndTime()` tăng *nghiêm ngặt* không?

**Không.** Các sự kiện có thể có timestamp bằng nhau do độ phân giải thời gian hoặc cách ghi. Quy tắc phù hợp khi kiểm tra ordered batch là **không giảm** (`!current.isBefore(previous)`), không phải **tăng nghiêm ngặt** (`current.isAfter(previous)`). Khi timestamp bằng nhau, đừng giả định thư tự cố định theo tên event, thread ID hay `sequence`, trừ khi contract ứng dụng của bạn chủ động định nghĩa tie-breaker.

## 6. `setOrdered(true)`: khi nào có giá trị?

Cân nhắc `true` nếu consumer cần xem các sự kiện trong từng batch **theo diễn tiến thời gian**:

- **Timeline phân tích performance:** in lần lượt event GC, I/O, lock hoặc CPU theo end time để dễ theo dõi.
- **Phân tích khoảng cách thời gian:** tính chênh lệch các event trong batch, không cần tự sort lại từng batch.
- **Hiển thị dashboard/chẩn đoán:** thứ tự trong từng lô giúp kết quả hiển thị dễ đọc hơn.
- **Xử lý chuỗi sự kiện cục bộ:** một đoạn xử lý có thể dựa vào order trong batch, nhưng vẫn cần xử lý tình huống batch mới mang timestamp cũ.
- **Offline stream:** đọc file JFR và muốn thứ tự trong mỗi batch khi xuất dữ liệu.

Đặt `true` không thể giải quyết mọi nhu cầu phân phối:

1. Nó **không tạo ra** một lịch sử toàn cục đã sắp xếp vĩnh viễn qua nhiều batch.
2. Nó **không đảm bảo** delivery tức thời hoặc đủ mọi event khi JFR bị quá tải, event bị disable/sampling, retention loại dữ liệu hoặc consumer không theo kịp.
3. Nó **không thay đổi** event start/end timestamps.
4. Nó **không tạo** quan hệ nhân quả giữa các hoạt động đa thread.
5. Nó **không định nghĩa** thứ tự ổn định cho các event có end time bằng nhau.

**Ví dụ trong thực tế:** nếu hệ thống observability của bạn vẽ timeline theo batch rồi ghép tất cả batch đơn giản bằng append, biểu đồ có thể chứa vài điểm end time giảm ở ranh giới giữa batch. Đây là hệ quả JFR đã mô tả trong Javadoc, không phải chắc chắn bug của `setOrdered(true)`.

## 7. `setOrdered(false)`: khi nào nên tắt sorting?

Cân nhắc `false` khi **kết quả tính toán không phụ thuộc vào thứ tự callback**:

- Đếm số lần xuất hiện của một loại event.
- Cộng tổng thời lượng hoặc số byte được ghi.
- Tính histogram độ trễ, phân phối thời lượng, min/max/average có xử lý thread-safe phù hợp.
- Gom metrics theo loại event, service hoặc interval sau khi đã đọc timestamp.
- Đẩy sự kiện sang hệ thống downstream có pipeline sắp xếp/ghép dữ liệu của riêng nó.

Ví dụ:

```java
java.util.concurrent.atomic.LongAdder total =
        new java.util.concurrent.atomic.LongAdder();

stream.setOrdered(false);
stream.onEvent("jdk.GarbageCollection", event -> total.increment());
```

Đây là **snippet** trong một phương thức có `RecordingStream stream` và đã enable loại event phù hợp. Giá trị của tổng số event đã xử lý **không bị ảnh hưởng** bởi thứ tự callback.

Tắt sorting có thể giảm công việc CPU/bộ nhớ cần thiết cho bước sắp xếp, nhưng **không cam kết mức cải thiện hiệu năng cụ thể**. Với workload nhỏ, sự khác biệt có thể không đo được; với hệ thống khác, cost còn phụ thuộc số event, batch size, callback work và phần ghi JFR. Hãy benchmark trên cùng event settings, JDK và tải thực tế.

### 7.1. `false` có đồng nghĩa sắp xếp ngược không?

Không. `setOrdered(false)` có nghĩa stream **không cần sắp xếp các event trước khi gửi tới callback**. Khi đọc một file vốn đã có event gần theo thời gian, ngay cả chế độ `false` vẫn có thể trông hoàn toàn tăng dần. **Không viết unit test mong chắc chắn có đảo thứ tự** chỉ để chứng minh đã tắt sorting.

### 7.2. Có làm thay đổi số lượng event không?

Tham số `ordered` chỉ kiểm soát ordering. Nó **không phải bộ lọc** và không phải setting chọn event. Nếu một phép đọc file giống nhau được thực thi đầy đủ ở hai chế độ, số event phù hợp được đọc không nên thay đổi *chỉ vì* `setOrdered`. Tuy nhiên, trong **live stream** không nên so số callback của hai lần chạy riêng biệt một cách máy móc: dữ liệu runtime và thời điểm đóng stream khác nhau.

## 8. Khi nào cần thứ tự toàn cục?

Javadoc nói rõ stream không hứa hẹn chronological order **giữa các batch**. Một số ứng dụng cần thứ tự rộng hơn, ví dụ ghép timeline nhiều nguồn, phân tích chuỗi trace hoặc xây lại một sự cố sau khi dữ liệu đến muộn.

**Với file hữu hạn hoặc tập dữ liệu đã thu thập đầy đủ**, có thể lưu snapshot bất biến của những trường cần thiết rồi sort sau khi đọc xong:

```java
record Point(java.time.Instant endedAt,
             String eventName,
             long sequence) {}

java.util.List<Point> points = new java.util.ArrayList<>();

stream.onEvent("demo.OrderingPulse", event -> {
    points.add(new Point(
        event.getEndTime(),
        event.getEventType().getName(),
        event.getLong("sequence")));
});

// Sau khi stream hoàn tất và không còn callback ghi vào points:
points.sort(java.util.Comparator
    .comparing(Point::endedAt)
    .thenComparingLong(Point::sequence));
```

Đây là **snippet minh họa**, cần đặt `Point` và biến `stream` đúng phạm vi; không phải chương trình độc lập. `sequence` trong ví dụ giả định event source thật sự có field ấy. Với tập dữ liệu lớn, cần giới hạn số phần tử và tránh giữ toàn bộ event trong heap.

**Chú ý:** việc sort theo `endedAt` và `sequence` chỉ định một **thứ tự kết quả trong danh sách**. Nó **không chứng minh** mối quan hệ causal giữa các event, không khôi phục dữ liệu chưa bao giờ được ghi và không đảm bảo rằng timestamp từ mọi hệ thống có cùng chất lượng đồng hồ.

### 8.1. Streaming vô hạn cần cửa sổ và chính sách đến muộn

Với luồng thời gian thực kéo dài vô hạn, bạn không thể bảo đảm rằng **không bao giờ** có event cũ đến trong tương lai nếu không có giả định về độ trễ tối đa. Một cách tiếp cận thực tế:

1. Xác định mức độ trễ tối đa chấp nhận được dựa trên nguồn dữ liệu và yêu cầu nghiệp vụ.
2. Đưa events vào **buffer có giới hạn** theo thời điểm kết thúc và khóa correlation thích hợp.
3. Phát kết quả sau một **watermark/cửa sổ chờ** đã chọn; chấp nhận chính sách xử lý event đến muộn.
4. Nếu một event đến sau cửa sổ, quyết định bỏ qua, cập nhật lại số liệu hoặc ghi correction.
5. Theo dõi độ trễ, bộ nhớ buffer, sự kiện đến muộn và dữ liệu bị loại do retention.

Đây là **thiết kế pipeline của ứng dụng**, không phải chức năng tự động của `RecordingStream.setOrdered(true)`. Lưu ý tính bất định do đồng hồ giữa các hệ thống, event có duration và các nguồn khác nhau.

### 8.2. Đảm bảo thứ tự logic nhờ sequence/correlation

Khi cần dựng thứ tự **bước xử lý trong một request**, hãy ghi `requestId` và sequence do ứng dụng quản lý. Không lấy mỗi end time làm thứ tự logic giữa các threads. Nếu một request gồm nhiều event được tạo ở các thời điểm khác nhau, application sequence giúp diễn giải các bước; nhưng phải đảm bảo cách cấp sequence là thread-safe và có ý nghĩa trong domain.

## 9. Phân biệt `setOrdered` với các cấu hình JFR khác

| Nhóm | API | Tác dụng |
| --- | --- | --- |
| Thứ tự callback | `setOrdered(boolean)` | Bật/tắt sorting theo end time **trong từng batch** |
| Giữ dữ liệu theo tuổi | `RecordingStream.setMaxAge(Duration)` | Retention của dữ liệu recording trong repository |
| Giữ dữ liệu theo byte | `RecordingStream.setMaxSize(long)` | Retention dung lượng, loại chunk cũ |
| Chọn event | `enable(Class/String)`, `disable(...)` | Event type nào được ghi |
| Điều kiện ghi event | `EventSettings.withThreshold`, `withPeriod` | Ngưỡng/chu kỳ tùy loại event |
| Nhận callback | `onEvent(...)` | Xử lý event đã được stream tiêu thụ |
| Batch boundary | `onFlush(Runnable)` | Báo batch đã flush xong, phù hợp tổng hợp |
| Đối tượng callback được tái sử dụng | `setReuse(boolean)` | Có thể tái sử dụng instance `RecordedEvent` |
| Bắt đầu xử lý | `start()`, `startAsync()` | Cách thực thi callback: chặn hoặc bất đồng bộ |
| Đóng stream | `close()` | Dừng/giải phóng tài nguyên |
| Mốc thời gian tiêu thụ | `setStartTime(Instant)`, `setEndTime(Instant)` | Chọn phần thời gian để đọc/đóng |
| Tạo file recording | `Recording.dump(Path)` hoặc API export phù hợp | Lưu JFR ra file, không phải sorting |

**Quan trọng về `setReuse`:** theo Javadoc `EventStream`, cùng một đối tượng `RecordedEvent` có thể được tái sử dụng để biểu diễn nhiều event. Nếu muốn **giữ nguyên đối tượng event sau khi callback kết thúc**, cần xem `setReuse(false)`. Trong nhiều trường hợp tốt hơn là **trích các trường cần thiết thành bản sao bất biến** (ví dụ record `Point` ở mục trước) thay vì cất trực tiếp reference `RecordedEvent` vào một `List` không giới hạn.

Không nhầm `setReuse(false)` với `setOrdered(false)`: một cái điều khiển **object reuse**, cái còn lại điều khiển **sorting**. Mặc định object reuse có thể ảnh hưởng cách bạn lưu, ghép và kiểm tra timestamp về sau; vì vậy đây là chú ý quan trọng khi xây pipeline cần sorting toàn cục.

## 10. Các lỗi phổ biến và cách tránh

### Lỗi 1 — Cho rằng `setOrdered(true)` sắp xếp toàn bộ lịch sử vĩnh viễn

Không đúng. Đúng là sắp xếp **theo batch** cho những event mà JVM có tại lần flush. Batch sau có thể mang timestamp cũ hơn batch trước. **Sửa:** nếu cần global order, xử lý thêm ở downstream hoặc sort file sau khi thu thập đầy đủ.

### Lỗi 2 — Cho rằng `setOrdered(false)` cố tình đảo ngược thứ tự

Không đúng. Nó chỉ **tắt sorting**, không shuffle hay reverse. **Sửa:** đừng viết test yêu cầu phải nhìn thấy inversion; hãy kiểm tra kết quả nghiệp vụ không phụ thuộc callback order.

### Lỗi 3 — Dùng `getStartTime()` để khẳng định `setOrdered` bị lỗi

Event có thể kéo dài: event A bắt đầu trước B nhưng kết thúc sau B. JFR sắp theo **end time trong batch**. **Sửa:** dùng `getEndTime()` cho phép kiểm chứng phù hợp, và cân nhắc duration khi phân tích timeline.

### Lỗi 4 — Kiểm tra global monotonic mà không reset mốc ở `onFlush`

Nếu một event trong batch sau cũ hơn batch trước, global check có thể báo lỗi sai về API. **Sửa:** reset mốc tại batch boundary hoặc dùng kiểm thử cố ý đánh giá global lateness khác với hợp đồng của `setOrdered`.

### Lỗi 5 — Giả định mọi event sẽ được callback

Filtering, threshold, sampling, flush, retention và thời gian đóng stream đều có thể ảnh hưởng số event quan sát được. **Sửa:** đo callback thực, dùng đồng bộ hữu hạn, và không bắt buộc đủ N callback chỉ vì đã gọi N lần `commit()` trong demo live.

### Lỗi 6 — Nhầm thứ tự logic với chronological order

Thread scheduling và async work có thể khiến thứ tự kết thúc khác thứ tự yêu cầu được gửi. **Sửa:** ghi sequence/correlation ID nếu cần biểu diễn thứ tự nghiệp vụ và bảo đảm cách cấp ID phù hợp.

### Lỗi 7 — Quên dùng `onFlush` khi phân tích batch

Nếu cần theo dõi thứ tự trong batch, thiếu boundary dễ tạo kết luận sai giữa hai batch. **Sửa:** đăng ký `onFlush` và xác định rõ dữ liệu đã xử lý của batch nào.

### Lỗi 8 — Đưa xử lý nặng trực tiếp vào callback

CPU/I/O nặng trong `onEvent` có thể làm stream bị trễ, tăng tài nguyên và giảm khả năng xử lý. **Sửa:** callback ngắn, pipeline/queue có giới hạn nếu cần tách xử lý, đo độ trễ và hiệu năng.

### Lỗi 9 — Lưu `RecordedEvent` lâu dài mà không xét `setReuse`

Object event có thể được tái sử dụng theo Javadoc. **Sửa:** dùng `setReuse(false)` khi cần giữ reference, hoặc snapshot fields thành object riêng; quản lý bộ nhớ rõ ràng.

### Lỗi 10 — Bật `setOrdered(false)` rồi tin rằng không còn sự kiện nào đến theo thời gian

Không có sorting guarantee không có nghĩa thứ tự bắt buộc sai. **Sửa:** đừng suy từ một lần chạy may mắn rằng `false` vẫn được JVM đảm bảo chronologically ordered.

### Lỗi 11 — Dùng `setMaxAge` thay `setOrdered`

`maxAge` giới hạn tuổi dữ liệu ghi lưu trên disk repository, không quyết định thứ tự callback. **Sửa:** chọn API đúng trách nhiệm.

### Lỗi 12 — Nghĩ sorting không có chi phí hoặc luôn nhanh/chậm như nhau

Sorting có thêm xử lý; bỏ sorting có thể hữu ích cho throughput, nhưng hiệu quả phụ thuộc batch size/JDK/CPU/tải. **Sửa:** benchmark với dữ liệu thực, không công bố tốc độ cải thiện cố định nếu không đo.

### Lỗi 13 — Quên đóng stream

`start()` có thể chặn luồng gọi, `startAsync()` tiếp tục xử lý riêng. Stream không được đóng có thể giữ tài nguyên ngoài ý muốn. **Sửa:** `try-with-resources` và policy đóng phù hợp.

### Lỗi 14 — Phụ thuộc thứ tự khi cùng timestamp

Hai event có `getEndTime()` bằng nhau không có tie-breaker nghiệp vụ do `setOrdered` bảo đảm. **Sửa:** nếu cần kết quả ổn định, sort thêm bằng một khóa có nghĩa do bạn quản lý (ví dụ sequence trong cùng request).

### Lỗi 15 — So sánh hai lần live recording khác nhau như một benchmark tuyệt đối

Đếm/thứ tự callback có thể khác vì tải JVM, thời điểm flush và dữ liệu không đồng nhất. **Sửa:** với kiểm thử thuật toán sorting, dùng file JFR cố định; với benchmark live, cố định tải, settings và theo dõi độ trễ/cpu qua nhiều lần chạy.

## 11. Kiểm thử và vận hành có trách nhiệm

Khi xây dịch vụ nhận JFR liên tục, cần kiểm tra các mục sau:

- [ ] Chọn rõ `setOrdered(true)` nếu thứ tự trong batch quan trọng, `false` nếu chỉ tính toán độc lập thứ tự.
- [ ] Tài liệu của consumer nói rõ **không cam kết chronological order toàn cục**.
- [ ] Dùng `RecordedEvent.getEndTime()` để xác minh ordering phù hợp Javadoc.
- [ ] Theo dõi batch boundary bằng `onFlush` nếu có logic phụ thuộc từng batch.
- [ ] Không coi `false` là chế độ đảo event và không viết test phụ thuộc có inversion.
- [ ] Giữ event callback ngắn, không chặn bằng I/O dài hoặc tính toán quá nặng.
- [ ] Nếu cache dữ liệu, dùng buffer bounded và hiểu `setReuse`.
- [ ] Phân biệt retention ở `setMaxAge`/`setMaxSize` với ordering.
- [ ] Kiểm thử trong JDK và môi trường có JFR đang hoạt động.
- [ ] Với live stream, dùng timeout và chấp nhận timing không tất định.
- [ ] Với file JFR, có test cố định cùng dữ liệu cho cả hai chế độ.
- [ ] Nếu cần global ordering, có chính sách late events, window/watermark hoặc offline sort.
- [ ] Nếu dữ liệu chứa thread names, stack traces hoặc thông tin ứng dụng nhạy cảm, kiểm soát quyền đọc/export/retention.
- [ ] Có cleanup `close()` và monitor latency/batch size/flush rate.
- [ ] Không suy ra quan hệ nhân quả từ mỗi timestamp hoặc thứ tự gọi callback.

## 12. Bài tập thực hành

1. **Phân biệt khái niệm:** nêu hai lý do mà `setOrdered(true)` không bảo đảm thứ tự tuyệt đối giữa mọi callback của một stream dài hạn.
2. **Cú pháp:** tạo `RecordingStream`, bật `jdk.CPULoad` và chọn `setOrdered(false)` vì chỉ muốn đếm số sự kiện.
3. **Kiểm chứng trong batch:** dùng `onFlush` để reset `Instant last`, trong `onEvent` so sánh `getEndTime()` của event mới với event trước.
4. **Start vs end:** tạo hai sự kiện duration khác nhau sao cho event bắt đầu trước lại kết thúc sau. Dự đoán quy tắc ordering nếu cùng batch.
5. **Unordered:** chạy cùng file JFR với `true` và `false`. Vì sao `false` vẫn có thể hiện ra theo thời gian?
6. **Offline:** sửa `OrderedFileEventsDemo` để tạo 30 `Pulse`; kiểm tra count và non-decreasing end time trong mỗi batch.
7. **Callback reuse:** thử lưu trực tiếp `RecordedEvent` vào danh sách rồi đọc lại sau callback; tìm trong Javadoc vì sao cần `setReuse(false)` hoặc snapshot fields.
8. **Giữ lịch sử:** giải thích vì sao `setMaxAge(Duration.ofMinutes(5))` không đồng nghĩa `setOrdered(true)`.
9. **Throughput:** đề xuất benchmark đo cost sorting với cùng một file có nhiều events, chạy nhiều lần và so sánh hợp lý.
10. **Global order:** với các event đến muộn qua hai batch, đề xuất buffer/cửa sổ/watermark hoặc offline sort.
11. **Sequence:** thêm `requestId` và `sequence` vào custom event; phân biệt thứ tự logic theo sequence với thứ tự kết thúc theo end time.
12. **Production:** đề xuất một dashboard có chỉ số event rate, callback lag, số batch, số event không kịp xử lý, disk pressure và độ dài queue.
13. **Điều kiện race:** nếu nhiều thread cùng tạo events, tại sao không dùng thứ tự vòng lặp của một thread làm bằng chứng thứ tự toàn cục?
14. **Bảo mật:** khi dump `.jfr` để kiểm tra ordering, cần những giới hạn quyền truy cập và retention gì?

**Gợi ý đáp án:** (1) sorting chỉ trong batch; batch sau có thể chứa timestamp cũ; (2) dùng `setOrdered(false)` cho phép đếm độc lập order; (3) so theo `getEndTime()` trong batch, reset ở `onFlush`; (4) sắp theo kết thúc, không phải bắt đầu; (5) tắt sorting không đảo events; (6) file cố định giúp test ít biến động; (7) reuse có thể làm reference cũ phản ánh event khác; (8) retention khác ordering; (9) benchmark có kiểm soát, tránh suy từ một lần; (10) cần chính sách late events riêng; (11) logical sequence khác clock; (12–14) monitor, quyền và lifecycle được quản lý riêng.

## 13. Tài liệu chính thức

- **Oracle Java SE 17 Javadoc — `jdk.jfr.consumer.EventStream`:** thứ tự **trong batch theo end time**, giới hạn giữa batches, `setOrdered(boolean)`, `onFlush`, `setReuse`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html
- **Oracle Java SE 17 Javadoc — `jdk.jfr.consumer.RecordingStream`:** `RecordingStream` implement `EventStream` và expose `setOrdered`, `startAsync`, `onEvent`, `setMaxAge`/`setMaxSize`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html
- **Oracle Java SE 25 Javadoc — `EventStream`:** xác nhận API và semantics ordering/batch vẫn còn áp dụng trong JDK hiện đại: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html
- **OpenJDK JEP 349 — JFR Event Streaming:** API event stream được đưa vào Java 14: https://openjdk.org/jeps/349
- **Oracle Java SE 17 Javadoc — `RecordedEvent`:** `getStartTime()`, `getEndTime()`, truy cập fields: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html
- **Oracle Java SE 17 Javadoc — `Recording`:** tạo, bắt đầu, dừng và dump recording `.jfr` làm fixture kiểm thử: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html

**Ghi nhớ:** `setOrdered(true)` chỉ bảo đảm sorting **theo end time trong từng batch**; `setOrdered(false)` bỏ công việc sorting khi thứ tự không quan trọng. **Không coi bất kỳ chế độ nào là bảo đảm thứ tự toàn cục, thứ tự causal hay độ đầy đủ của mọi event.** Hãy dùng `onFlush` để phân biệt batch, chọn cơ chế downstream riêng nếu cần global timeline, và đo thực tế trước khi tối ưu hiệu năng.