# Đóng `RecordingStream` bằng `try-with-resources`

## 1. Vấn đề: vì sao cần đóng `RecordingStream`?

`jdk.jfr.consumer.RecordingStream` là API **Java Flight Recorder (JFR)** cho phép ứng dụng nhận sự kiện phát sinh trong **JVM hiện tại**. Một recording stream có thể thu thập và chuyển các sự kiện như sử dụng CPU, garbage collection, các thao tác I/O hoặc sự kiện do ứng dụng tự định nghĩa tới các callback.

Đây là một **tài nguyên có vòng đời**: khi hoạt động, stream có thể gắn với cơ chế ghi và tiêu thụ dữ liệu JFR, có luồng xử lý sự kiện và sử dụng bộ đệm/tài nguyên JVM. Vì vậy, một ứng dụng **phải đóng stream khi không còn cần dùng**.

`RecordingStream` triển khai `AutoCloseable` (thông qua cả `EventStream`), nên cách quản lý thông thường là:

```java
try (RecordingStream stream = new RecordingStream()) {
    // Cấu hình stream, đăng ký callback và bắt đầu nhận sự kiện.
}
// Ra khỏi khối: Java tự gọi stream.close().
```

Đây là **mẫu mã minh họa**, không phải chương trình chạy độc lập vì chưa khai báo `import` và chưa bắt đầu stream. Ý tưởng cốt lõi: **ngay cả khi một lệnh trong khối `try` ném ngoại lệ, Java vẫn gọi `close()` cho tài nguyên đã được tạo thành công**. Điều đó giúp giảm rủi ro để stream chạy ngoài ý muốn.

**Phạm vi phiên bản:** `RecordingStream` xuất hiện trong Java 14 và tiếp tục được cung cấp trong Java 17, 21 và các JDK mới. `try-with-resources` là cú pháp Java đã ổn định từ lâu; bài này tập trung vào cách dùng còn phù hợp hiện nay, không dựa vào cờ preview hay API đã lỗi thời.

## 2. `AutoCloseable` và cơ chế đóng tự động

`RecordingStream` có chữ ký loại hình như sau (lược bớt chi tiết):

```java
public final class RecordingStream implements AutoCloseable, EventStream {
    // Các phương thức API do JDK cung cấp.
}
```

Đoạn này **chỉ để mô tả API**, không được dùng để tự định nghĩa lớp `RecordingStream` thay cho JDK.

`AutoCloseable` cung cấp giao thức `close()`. Với cú pháp:

```java
try (RecordingStream stream = new RecordingStream()) {
    stream.startAsync();
    System.out.println("Stream đã bắt đầu");
}
```

Java thực hiện về mặt ngữ nghĩa:

1. Khởi tạo biến tài nguyên `stream`.
2. Chạy thân khối `try`.
3. Khi thoát khối, **tự gọi `stream.close()`** trước khi chuyển sang câu lệnh sau khối.
4. Nếu thân `try` ném ngoại lệ, tài nguyên vẫn được đóng trong quá trình rời khối; ngoại lệ chính tiếp tục được lan truyền nếu không được bắt.

Đây là điểm khác với việc chỉ viết:

```java
RecordingStream stream = new RecordingStream();
stream.startAsync();
// Nếu một câu lệnh sau đây ném lỗi và không có finally,
// stream.close() có thể không được gọi.
```

Phương án thủ công dùng `try/finally` cũng hợp lệ, nhưng `try-with-resources` thường **ngắn hơn, rõ quyền sở hữu tài nguyên hơn và khó quên đóng hơn**.

### Cú pháp Java 9+ khi tài nguyên đã được khai báo

Bạn có thể khai báo biến trước rồi đưa nó vào danh sách tài nguyên, miễn biến đó **final hoặc effectively final**:

```java
RecordingStream stream = new RecordingStream();
try (stream) {
    stream.startAsync();
}
// Từ đây stream đã đóng, dù biến Java vẫn còn trong phạm vi.
```

Đây là cách dùng sẽ xuất hiện trong **chương trình kiểm chứng** ở phần 5 để minh họa trạng thái sau khi đóng. Với mã ứng dụng thông thường, nên ưu tiên khai báo tài nguyên **ngay trong dấu ngoặc `try (...)`** nếu không cần giữ tên biến bên ngoài.

**Không nhầm biến còn trong phạm vi với stream còn sống:** sau khi khối `try` kết thúc, gọi `startAsync()` lại trên stream đã đóng sẽ ném `IllegalStateException`.

## 3. `start()` và `startAsync()` ảnh hưởng cách dùng `try-with-resources`

`RecordingStream` có hai cách khởi chạy phổ biến, đều được cung cấp trong Java 17+.

| Phương thức | Cách chạy | Ý nghĩa với `try-with-resources` |
| --- | --- | --- |
| `start()` | Xử lý callback trên **luồng gọi phương thức** và **chặn** trong khi stream còn chạy | Luồng không rời khối `try` chỉ vì đã gọi `start()`; phải có điều kiện đóng/kết thúc khác |
| `startAsync()` | Bắt đầu xử lý trên **luồng riêng**, trả quyền điều khiển về luồng gọi | Phù hợp với một phạm vi công việc có điểm bắt đầu và kết thúc rõ ràng; hết phạm vi thì tự đóng |

Ví dụ theo hướng *bất đồng bộ*:

```java
import java.time.Duration;
import jdk.jfr.consumer.RecordingStream;

try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad")
            .withPeriod(Duration.ofSeconds(1));
    stream.onEvent("jdk.CPULoad", event -> {
        // Xử lý mẫu CPU đã nhận.
    });

    stream.startAsync();

    // Luồng gọi vẫn tiếp tục chạy đến hết khối try.
}
```

Đây là **đoạn mã minh họa**, cần đặt bên trong một phương thức thích hợp. `close()` được tự động gọi khi rời khối, kể cả nếu lúc đó chưa nhận được sự kiện CPU nào. **Không có bảo đảm** rằng một khối `try` ngắn sẽ nhận được event định kỳ; việc event được nhận phụ thuộc thời điểm phát sinh, chu kỳ, cấu hình và lịch xử lý.

Với `start()`:

```java
try (RecordingStream stream = new RecordingStream()) {
    stream.onEvent(System.out::println);
    stream.start(); // Chặn ở đây cho tới khi stream kết thúc.
}
```

Mã này cũng **hợp lệ** khi đặt trong phương thức đầy đủ, nhưng không phải mẫu “tự thoát khi đến dấu `}`”. Vì `start()` có thể tiếp tục chặn, việc đóng do `try-with-resources` chỉ diễn ra **sau khi lệnh `start()` trả về hoặc ném ngoại lệ**. Nếu cần dừng chủ động, hãy thiết kế tín hiệu kết thúc, thời hạn hoặc cơ chế gọi `close()` từ nơi khác. Tránh đặt `start()` trực tiếp vào luồng xử lý HTTP request nếu không có cơ chế kết thúc phù hợp.

## 4. Đăng ký callback và đặt ranh giới sở hữu tài nguyên

Một trình tự rõ ràng thường là:

1. Tạo `RecordingStream` trong danh sách tài nguyên của `try`.
2. Chọn các loại event bằng `enable(...)` hoặc tắt loại không cần.
3. Đăng ký callback bằng `onEvent(...)` và handler lỗi bằng `onError(...)` nếu thích hợp.
4. Gọi `startAsync()`.
5. Thực hiện công việc cần quan sát khi stream còn sống.
6. Rời khỏi phạm vi `try` để tự gọi `close()`.

Ví dụ:

```java
try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad")
            .withPeriod(Duration.ofSeconds(1));

    stream.onEvent("jdk.CPULoad", event -> {
        double machine = event.getDouble("machineTotal");
        // Đưa machine vào hệ thống quan sát có kiểm soát.
    });

    stream.onError(error -> {
        System.err.println("JFR callback failed: " + error);
    });

    stream.startAsync();
    Thread.sleep(2_500);
}
```

Đoạn này minh họa **cấu hình và thời gian tồn tại có giới hạn**; nó cần được đặt trong một phương thức `throws InterruptedException` hoặc có cơ chế xử lý ngắt. Số sự kiện CPU nhận được không cố định: **đừng viết kiểm thử yêu cầu chính xác 2 hoặc 3 event** chỉ vì ngủ 2,5 giây.

Phạm vi `try` nên **bao trọn thời gian công việc cần quan sát**. Nếu stream bị đóng ngay sau `startAsync()` mà công việc lại chạy **sau** dấu `}`, bạn sẽ không thu được sự kiện của công việc đó.

### Đăng ký `onError` không thay thế đóng tài nguyên

`onError(Consumer<Throwable>)` nhận lỗi trong quá trình xử lý sự kiện. Khi không đăng ký handler lỗi, JFR có thể in stack trace mặc định ra stderr. Việc thêm `onError` giúp kiểm soát log, nhưng **không phải lệnh đóng stream** và không bảo đảm mọi callback đều thành công. `try-with-resources` vẫn là cách quản lý vòng đời chính.

### `onClose` là callback về việc đóng

`onClose(Runnable)` cho phép đăng ký một hành động khi stream được đóng. Có thể dùng để cập nhật trạng thái quan sát hoặc giải phóng phụ trợ, nhưng **không nên giả định mọi callback sự kiện đã hoàn thành chỉ vì `close()` đã trả về**. Chỉ báo đóng và bảo đảm đã tiêu thụ tất cả sự kiện là hai vấn đề khác nhau.

## 5. Chương trình Java 17+ hoàn chỉnh: đóng trong đường đi thường và đường đi lỗi

Lưu toàn bộ ví dụ dưới đây vào tệp **`RecordingStreamResourceDemo.java`**:

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import jdk.jfr.FlightRecorder;
import jdk.jfr.consumer.RecordingStream;

public class RecordingStreamResourceDemo {
    public static void main(String[] args) {
        if (!FlightRecorder.isAvailable()) {
            System.out.println("JFR unavailable");
            return;
        }

        AtomicInteger samples = new AtomicInteger();
        RecordingStream stream = new RecordingStream();
        try (stream) {
            stream.enable("jdk.CPULoad")
                    .withPeriod(Duration.ofSeconds(1));
            stream.onEvent("jdk.CPULoad",
                    event -> samples.incrementAndGet());

            stream.startAsync();
            System.out.println("started=true");
        }

        try {
            stream.startAsync();
            System.out.println("closed=false");
        } catch (IllegalStateException expected) {
            System.out.println("closed=true");
        }

        RecordingStream exceptional = new RecordingStream();
        try (exceptional) {
            throw new IllegalArgumentException("demo failure");
        } catch (IllegalArgumentException expected) {
            System.out.println("caught=" + expected.getMessage());
        }

        try {
            exceptional.startAsync();
            System.out.println("closedAfterException=false");
        } catch (IllegalStateException expected) {
            System.out.println("closedAfterException=true");
        }

        System.out.println("finished=true");
    }
}
```

Chạy bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 RecordingStreamResourceDemo.java
java RecordingStreamResourceDemo
```

**Đầu ra đã kiểm chứng trên OpenJDK có hỗ trợ JFR:**

```text
started=true
closed=true
caught=demo failure
closedAfterException=true
finished=true
```

**Giải thích:**

- `FlightRecorder.isAvailable()` là kiểm tra khả năng JFR của JVM. Nếu runtime không hỗ trợ JFR, chương trình in `JFR unavailable` rồi thoát; không cố khởi tạo stream.
- `AtomicInteger samples` minh họa cách callback có thể cập nhật dữ liệu chia sẻ an toàn giữa luồng xử lý JFR và luồng gọi. Ví dụ **không in số lượng event CPU** vì số lần callback là không xác định trong một khoảng thời gian ngắn.
- `startAsync()` trả quyền điều khiển về `main`. Dòng `started=true` cho biết phương thức đã trả về thành công, **không chứng minh rằng event CPU đã được xử lý**.
- Khi ra khỏi `try (stream)`, Java gọi `stream.close()`. Mã cố tình thử gọi `startAsync()` lại sau khi đóng, bắt `IllegalStateException` để in `closed=true`. Đây là **kỹ thuật minh họa trạng thái**, **không phải khuyến nghị** thử khởi chạy lại tài nguyên đã đóng trong mã sản xuất.
- Trong trường hợp `exceptional`, thân `try` cố ý ném `IllegalArgumentException`. Java **vẫn đóng stream** trước khi vào nhánh `catch`; vì vậy đoạn kiểm tra sau đó cho `closedAfterException=true`.
- Dòng `finished=true` xác nhận chương trình tiếp tục chạy sau khi xử lý ngoại lệ.

**Tại sao không dùng `close()` trực tiếp ở cuối?** Vì chính mục tiêu của `try-with-resources` là bảo đảm việc đóng kể cả khi có nhánh trả về, ném exception hoặc khối xử lý kết thúc sớm.

Chương trình đã được biên dịch bằng `javac --release 17` và chạy thành công trên JDK hỗ trợ JFR. Thông báo khi JFR không khả dụng là **một nhánh khác**, không phải đầu ra năm dòng ở trên.

## 6. `close()` không phải cơ chế “chờ xử lý hết mọi event”

Đây là lưu ý rất quan trọng trong API `EventStream.close()`:

> Khi đóng stream đang chạy, quá trình xử lý sẽ được dừng ngay hoặc sau lần flush tiếp theo; **không có bảo đảm rằng mọi hành động callback đã hoàn thành trước khi `close()` trả về**.

Hệ quả thực tế:

- `try-with-resources` bảo đảm **yêu cầu đóng/giải phóng tài nguyên** tại điểm kết thúc phạm vi.
- Nó **không phải** là lệnh “đợi mọi event đang nằm trong hàng chờ được xử lý xong”.
- Nếu thoát khối `try` ngay sau khi tạo event, callback có thể không kịp nhận event đó.
- Không nên phụ thuộc `close()` để xác nhận một phép đếm `AtomicInteger` trong callback đã thấy toàn bộ event.

### Vậy làm thế nào khi thực sự cần chờ một sự kiện?

Một chiến lược là đăng ký callback với một `CountDownLatch` và dùng **thời hạn chờ hữu hạn** trong khối `try`. Ví dụ cấu trúc:

```java
CountDownLatch seen = new CountDownLatch(1);

try (RecordingStream stream = new RecordingStream()) {
    stream.enable("demo.Operation").withThreshold(Duration.ZERO);
    stream.onEvent("demo.Operation", event -> seen.countDown());
    stream.startAsync();

    // Thực hiện thao tác làm phát sinh event demo.Operation.
    boolean delivered = seen.await(10, TimeUnit.SECONDS);
    if (!delivered) {
        throw new IllegalStateException("JFR event not observed in time");
    }
}
```

Đây là **đoạn mã mô tả kỹ thuật đồng bộ**, **không phải chương trình chạy độc lập**: cần import `CountDownLatch`, `TimeUnit`, `Duration`, khai báo một loại event `demo.Operation` phù hợp và thực sự phát sinh event. `await(...)` phải được xử lý `InterruptedException` hoặc khai báo `throws`. Cách này đợi **callback mục tiêu** đã chạy, nhưng không chứng minh **mọi** event khác cũng được xử lý.

Với giám sát lâu dài, có thể dùng `awaitTermination(...)` để đợi luồng tiêu thụ kết thúc **trong một số điều kiện**, nhưng không nên gọi không giới hạn trên stream vẫn đang chạy rồi mong nó tự đóng. Thời hạn, tín hiệu dừng và mô hình ownership phải được thiết kế rõ.

### `stop()` khác `close()` — chú ý phiên bản

Từ **Java 20**, `RecordingStream` có phương thức `stop()` dành cho trường hợp cần **dừng stream và chờ các event trong recording đã được tiêu thụ**. Phương thức này **không có trong API `RecordingStream` của Java 17**.

- **Java 17+:** `close()` và `try-with-resources` là cách đóng tài nguyên thông dụng; không gọi `stop()` trong chương trình biên dịch với `--release 17`.
- **Java 20+:** nếu thật sự cần xử lý hết những sự kiện đã ghi trước khi tiếp tục, cân nhắc `stop()` ở luồng điều khiển phù hợp, sau đó vẫn đóng tài nguyên bằng `try-with-resources`.
- **Không gọi `stop()` ngay trong callback `onEvent(...)`**: theo tài liệu API, điều này có thể làm luồng xử lý chặn vô thời hạn. Khi cần yêu cầu dừng từ callback, xem xét `close()` và cơ chế điều phối phù hợp.

Do đề bài tập trung **đóng bằng `try-with-resources`**, điều quan trọng là phân biệt mục tiêu **giải phóng tài nguyên** với mục tiêu **đảm bảo tất cả event đã được tiêu thụ**.

## 7. Xử lý ngoại lệ, ngắt luồng và tài nguyên liên quan

### 7.1. Thân `try` ném ngoại lệ

`try-with-resources` tuân theo quy tắc Java: khi thân `try` ném ngoại lệ, runtime thực hiện `close()` trên các tài nguyên đã khởi tạo trước khi ngoại lệ được xử lý ở tầng ngoài.

Trong chương trình phần 5:

```java
RecordingStream exceptional = new RecordingStream();
try (exceptional) {
    throw new IllegalArgumentException("demo failure");
} catch (IllegalArgumentException expected) {
    System.out.println(expected.getMessage());
}
```

Dòng `close()` không có trong mã nhưng vẫn được gọi. Nếu cả thân `try` và `close()` đều ném ngoại lệ, quy tắc **suppressed exceptions** của Java áp dụng: ngoại lệ từ thân khối thường là ngoại lệ chính; lỗi đóng được gắn vào danh sách suppressed. Với `RecordingStream.close()` bình thường, không có checked exception bắt buộc, nhưng hiểu cơ chế giúp xử lý tài nguyên Java nói chung.

### 7.2. Khởi tạo tài nguyên thất bại

Nếu `new RecordingStream()` đã ném `IllegalStateException` hoặc ngoại lệ khác trước khi trả về đối tượng hợp lệ, bản thân stream ấy **chưa được tạo thành công**, nên không có đối tượng để `close()`. `FlightRecorder.isAvailable()` giúp kiểm tra điều kiện hỗ trợ, nhưng không đảm bảo việc tạo repository, quyền hoặc môi trường lúc chạy đều luôn thành công.

### 7.3. Khi có `Thread.sleep` hoặc phép chờ trong khối

Ví dụ giám sát theo thời gian:

```java
try (RecordingStream stream = new RecordingStream()) {
    stream.startAsync();
    Thread.sleep(5_000);
}
```

Đoạn mã minh họa cần được đặt trong phương thức xử lý `InterruptedException`. Nếu `sleep` bị ngắt, luồng rời khối và **stream vẫn được đóng tự động**. Khi bắt `InterruptedException` trong mã ứng dụng, thường nên phục hồi cờ ngắt bằng `Thread.currentThread().interrupt()` hoặc cho ngoại lệ lan truyền theo hợp đồng, không im lặng nuốt tín hiệu ngắt.

### 7.4. Một tài nguyên, một nơi chịu trách nhiệm đóng

Nếu ứng dụng chuyển `RecordingStream` tới nhiều component, đừng để mỗi component tự ý gọi `close()` khi component khác vẫn cần stream. **Ownership** nên rõ ràng: ví dụ một service giám sát sở hữu stream, tạo từ lúc service start và đóng ở giai đoạn shutdown.

Với thời gian sống ngắn, `try-with-resources` thể hiện ownership rất rõ. Với một service theo dõi liên tục, có thể giữ stream làm trường của đối tượng quản lý và đóng trong lifecycle shutdown của service. Không giữ stream mãi chỉ vì quên `close()`, nhưng cũng không nhét nó vào một khối `try` ngắn hơn công việc cần theo dõi.

## 8. Lỗi thường gặp và cách sửa

| Sai sót | Hệ quả | Cách sửa |
| --- | --- | --- |
| Tạo `RecordingStream` rồi quên `close()` | Có thể giữ thread/buffer/tài nguyên JFR không cần thiết | Dùng `try-with-resources` hoặc shutdown lifecycle rõ ràng |
| Gọi `startAsync()` rồi kết thúc `try` ngay | Stream đóng trước khi kịp nhận event | Đặt **toàn bộ công việc cần theo dõi** trong phạm vi `try` |
| Gọi `start()` và mong tự đến cuối khối `try` sau vài câu lệnh | `start()` là blocking | Dùng `startAsync()` hoặc thiết kế điểm kết thúc từ luồng khác |
| Tin rằng `close()` chờ mọi callback hoàn thành | API không bảo đảm | Chờ event cụ thể hoặc dùng `stop()` chỉ với Java 20+ nếu cần drain |
| Dùng `stream.startAsync()` sau khi đã đóng | `IllegalStateException` | Tạo stream mới khi muốn bắt đầu một session khác |
| Dùng `stop()` trong project target Java 17 | Lỗi biên dịch: API chưa có | Dùng `close()`; chỉ dùng `stop()` khi target Java 20+ |
| Gọi `stop()` bên trong callback | Có thể chặn luồng xử lý lâu dài | Điều phối dừng bên ngoài callback, hoặc dùng `close()` phù hợp |
| In ngay số callback sau `close()` và coi đó là toàn bộ event | Có thể bỏ sót event đang chờ | Đồng bộ mục tiêu với deadline và kiểm tra chiến lược thu thập |
| Đăng ký `onError` và tưởng đó là lệnh đóng | Lỗi callback vẫn phải được xử lý riêng với ownership | Dùng `try-with-resources` song song handler lỗi |
| Để `start()` trong thread request không có tín hiệu dừng | Có thể treo request | Dùng `startAsync()` và cấu hình vòng đời có thời hạn |
| In dữ liệu JFR thô ra log công khai | Có thể lộ thông tin vận hành/nhạy cảm | Giới hạn dữ liệu, kiểm soát logging và quyền truy cập |
| Thử xử lý event JVM nhưng không đăng ký `enable` hoặc callback phù hợp | Không thấy dữ liệu mong muốn | Chọn event và cấu hình trước `startAsync()` |

## 9. Tự kiểm tra kiến thức

**Câu 1.** Vì sao `RecordingStream` dùng được trong `try-with-resources`?  
**Đáp án:** Vì lớp triển khai `AutoCloseable`, nên Java tự gọi `close()` khi khối `try` kết thúc.

**Câu 2.** Nếu thân `try` ném `IllegalArgumentException`, stream đã được tạo có được đóng không?  
**Đáp án:** Có, `try-with-resources` tự đóng trước khi ngoại lệ tiếp tục được xử lý.

**Câu 3.** `start()` và `startAsync()` khác nhau ra sao?  
**Đáp án:** `start()` xử lý trong luồng gọi và chặn; `startAsync()` sử dụng luồng khác rồi trả quyền điều khiển cho luồng gọi.

**Câu 4.** Tại sao không nên rời khối `try` ngay sau `startAsync()` nếu muốn theo dõi một công việc?  
**Đáp án:** Vì khi đó `close()` sẽ được gọi trước công việc, dẫn tới không thu được sự kiện cần theo dõi.

**Câu 5.** `close()` có bảo đảm mọi callback đã chạy xong khi trả về không?  
**Đáp án:** Không. Tài liệu `EventStream.close()` nói rõ không bảo đảm tất cả hành động đã hoàn thành.

**Câu 6.** Trong dự án Java 17, có gọi được `RecordingStream.stop()` không?  
**Đáp án:** Không; phương thức được bổ sung từ Java 20. Với Java 17, đóng bằng `close()` hoặc `try-with-resources`.

**Câu 7.** Vì sao dùng `AtomicInteger` trong callback ở ví dụ?  
**Đáp án:** Callback chạy trên luồng riêng khi dùng `startAsync()`, nên việc chia sẻ bộ đếm cần cơ chế thread-safe; ví dụ không dựa vào số event nhận được để xác định đầu ra.

**Câu 8.** Khi tạo stream cho service chạy suốt vòng đời ứng dụng, có nên đóng ngay sau mỗi request không?  
**Đáp án:** Không, nếu service đó **sở hữu một stream dùng chung** để giám sát liên tục. Cần gắn `close()` vào lifecycle shutdown thích hợp.

**Câu 9.** Một `RecordingStream` đã đóng có thể được `startAsync()` lại không?  
**Đáp án:** Không; `IllegalStateException` là hành vi được API công bố. Tạo đối tượng stream mới để bắt đầu phiên khác.

## 10. Ghi nhớ và tài liệu chính thức

**Công thức an toàn cho phạm vi ngắn:** tạo `RecordingStream` trong `try (...)`, cấu hình và đăng ký callback **trước khi start**, gọi `startAsync()`, thực hiện công việc cần theo dõi **trong phạm vi `try`**, rồi để Java tự `close()`.

- `try-with-resources` xử lý **quyền sở hữu và đóng tài nguyên**, kể cả khi có ngoại lệ.
- `start()` **blocking**; `startAsync()` **non-blocking** đối với luồng gọi.
- `close()` **không phải** bảo đảm mọi sự kiện/callback đã được tiêu thụ.
- Nếu cần đồng bộ event, dùng cơ chế chờ phù hợp; `stop()` là tùy chọn **Java 20+** để chờ drain, không dùng trong mã Java 17.
- Khi giám sát lâu dài, thiết kế ownership và thời điểm shutdown rõ ràng.

**Nguồn tham khảo chính thức:**

- [Oracle Java SE 17 — `RecordingStream`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): `AutoCloseable`, `start()`, `startAsync()`, `close()` và ví dụ `try-with-resources`.
- [Oracle Java SE 21 — `EventStream`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): vòng đời, bảo đảm và giới hạn của `close()`, `onError`, `onClose`.
- [Oracle Java SE 21 — `RecordingStream`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): tham số, callback, `stop()` và ghi chú từ Java 20.
- [Oracle Java SE 17 — `FlightRecorder`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/FlightRecorder.html): kiểm tra JFR khả dụng với `isAvailable()`.
- [JLS Java SE 17 `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): quy tắc đóng resource, đường đi ngoại lệ và suppressed exceptions.
