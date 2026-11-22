# Tạo luồng sự kiện từ JVM hiện tại bằng RecordingStream

## Mục tiêu học tập

`RecordingStream` thuộc **JDK Flight Recorder (JFR)** cho phép chương trình Java **tiếp nhận các JFR event được ghi trong chính JVM đang chạy**, trong khi chương trình vẫn hoạt động. Bạn không bắt buộc phải xuất tệp `.jfr` rồi đọc lại sau khi ứng dụng kết thúc. Đây là cơ sở để xây dựng chẩn đoán liên tục, quan sát hiệu năng, phát hiện hành vi bất thường và các bài kiểm thử có thu thập sự kiện.

Sau bài này, bạn có thể:

1. Hiểu sự khác nhau giữa `RecordingStream`, một `Recording` JFR thông thường và việc đọc file bằng `RecordingFile`.
2. Tạo stream mới từ JVM hiện tại, bật event cần quan sát, đăng ký callback, bắt đầu và đóng đúng vòng đời.
3. Dùng `startAsync()` và `CountDownLatch` để xác nhận một **custom JFR event** thực sự đến được consumer.
4. Phân biệt custom event do ứng dụng `commit()` với các event có sẵn của JVM như `jdk.CPULoad`.
5. Nhận diện các rủi ro: callback chưa chạy kịp, event bị lọc theo threshold/period, callback ném exception, tài nguyên lưu giữ tăng, hoặc môi trường không hỗ trợ JFR.
6. Biết cách kiểm thử mà không giả định tốc độ phân phối tức thời hay số lượng event hệ thống cố định.

**Tính hiện hành:** JFR Event Streaming API, bao gồm `jdk.jfr.consumer.RecordingStream`, được giới thiệu chính thức trong **Java 14** (JEP 349) và vẫn có trong Java hiện đại. Ví dụ dùng **JDK 17 trở lên**, không cần `--enable-preview` và không sử dụng cú pháp hoặc cách chạy Java đã legacy.

## 1. RecordingStream thực sự đọc sự kiện từ đâu?

`RecordingStream` là một class `final` trong module `jdk.jfr`, package `jdk.jfr.consumer`. Constructor:

```java
RecordingStream stream = new RecordingStream();
```

tạo **một event stream cho JVM của chính tiến trình đang thực thi câu lệnh**. Những event JFR được bật và ghi trong JVM này có thể được stream xử lý và chuyển vào các callback. Vì vậy, đây là **quan sát nội bộ trong cùng tiến trình**, không phải kết nối mặc định đến một JVM khác, không phải luồng log từ `System.out` và cũng không phải công cụ phân tích source code.

JFR ghi thông tin theo **event**, mỗi event có metadata mô tả loại và các giá trị như thời gian, tên thread, trường dữ liệu hoặc stack trace (tùy cấu hình). Các event có thể do JVM phát sinh, chẳng hạn sự kiện GC/CPU, hoặc do chính ứng dụng tạo bằng subclass của `jdk.jfr.Event`.

Luồng xử lý khái quát:

```text
Ứng dụng + JVM hiện tại
          |
          | JFR events đã được bật và ghi
          v
  JFR recording/repository
          |
          v
    RecordingStream
          |
          | callback onEvent(...)
          v
  phân tích / đếm / cảnh báo / kiểm thử
          |
          v
   close() khi hoàn thành
```

**Từ “streaming” không có nghĩa đồng bộ tức thời với từng lệnh `commit()`.** Các event được đẩy qua cơ chế ghi và xử lý dữ liệu của JFR; có thể có độ trễ do buffer, chunk, flush và lịch chạy thread. Vì vậy cần chờ một khoảng hợp lý trong test và không hứa mọi event được giao lập tức tại cùng thời điểm phát sinh.

## 2. So sánh ba công cụ để tránh chọn nhầm

| Công cụ | Dùng để làm gì? | Khi nên chọn |
| --- | --- | --- |
| `RecordingStream` | Tạo và tiêu thụ luồng JFR events trong **JVM hiện tại** | Quan sát liên tục trong ứng dụng, test có callback |
| `Recording` | Điều khiển một phiên JFR recording, cấu hình và quản lý vòng đời dữ liệu | Muốn quản lý recording và lưu/trích xuất dữ liệu theo chủ đích |
| `RecordingFile` | Đọc các event trong một **tệp `.jfr` đã có** | Phân tích kết quả ghi trước đó hoặc xử lý offline |

Cả ba là API của hệ sinh thái JFR, nhưng **`RecordingStream()` không cần được truyền đường dẫn file**. Nếu bạn bắt đầu từ một file recording đã tồn tại thì `RecordingFile` thích hợp hơn; nếu cần lấy sự kiện từ tiến trình hiện tại để phản ứng trong lúc chạy, dùng `RecordingStream`.

Một số API khác hỗ trợ streaming từ repository hoặc chẩn đoán JVM bên ngoài, nhưng **constructor không tham số của `RecordingStream` không tự kết nối JVM từ xa**. Khi mục tiêu là ứng dụng khác, phải thiết kế rõ cách truy cập tiến trình, quyền và kênh dữ liệu phù hợp.

## 3. Trình tự tạo một RecordingStream hợp lệ

Các bước thường dùng:

1. Kiểm tra môi trường có hỗ trợ JFR bằng `FlightRecorder.isAvailable()` nếu cần thông báo lỗi thân thiện. Đây là **kiểm tra nhanh**, không bảo đảm mọi thao tác repository sẽ thành công.
2. Tạo `new RecordingStream()` hoặc `new RecordingStream(configuration)` khi cần dùng cấu hình có sẵn.
3. Chỉ định event cần ghi bằng `enable("jdk.CPULoad")` hoặc `enable(MyEvent.class)`, và cấu hình thêm threshold/period nếu loại event đó hỗ trợ.
4. Đăng ký callback bằng `onEvent("event.Name", action)`. Có thể dùng `onEvent(action)` cho mọi event, nhưng chọn theo tên khi biết loại event thường tiết kiệm xử lý hơn.
5. Đăng ký `onError(action)` nếu muốn quản lý lỗi callback/stream rõ ràng.
6. Bắt đầu bằng `startAsync()` nếu thread gọi cần tiếp tục làm việc, hoặc `start()` nếu chấp nhận **chạy xử lý đồng bộ và bị chặn** đến khi stream kết thúc/được đóng.
7. Chủ động giới hạn thời gian chạy, lưu giữ dữ liệu và đóng `close()`; dùng **try-with-resources** để bảo đảm đóng kể cả khi có exception.

Ví dụ mẫu ở mức **đoạn mã trong method**, dùng sự kiện JVM có sẵn:

```java
try (var stream = new jdk.jfr.consumer.RecordingStream()) {
    stream.enable("jdk.CPULoad")
          .withPeriod(java.time.Duration.ofSeconds(1));

    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println("CPU event at: " + event.getStartTime());
    });

    stream.startAsync();
    Thread.sleep(3_000);
}
```

Đoạn này minh họa API có thật của JDK 17+; cần đặt trong method có khai báo/xử lý `InterruptedException`. Nó **không có stdout cố định**: event `jdk.CPULoad` là loại sự kiện định kỳ phụ thuộc cấu hình JVM, lịch ghi/flush và môi trường. Chạy ba giây **không** phải cam kết callback sẽ nhận chính xác ba event.

Trong thực tế, `startAsync()` là lựa chọn phù hợp khi bạn không muốn chặn main thread; stream xử lý callback ở **một thread riêng**. Callback nên nhanh, tránh I/O chậm kéo dài hoặc thao tác đồng bộ có nguy cơ làm nghẽn luồng xử lý event.

## 4. Tự định nghĩa một JFR event để kiểm tra đường đi

JFR cho phép ứng dụng tạo event có cấu trúc:

```java
@jdk.jfr.Name("lesson.Pulse")
@jdk.jfr.Label("Lesson pulse")
public static class Pulse extends jdk.jfr.Event {
    @jdk.jfr.Label("Message")
    public String message;
}
```

Đây là **khai báo class lồng có `static`**, cần đặt trong một class chứa nó. `Pulse` là một event type tùy chỉnh; `@Name` đặt tên JFR là `lesson.Pulse`, còn field `message` chứa payload.

Một instance event có thể được ghi bằng:

```java
Pulse pulse = new Pulse();
pulse.message = "hello";
pulse.commit();
```

`commit()` chuyển dữ liệu sang hệ thống ghi JFR **nếu event được bật và thỏa điều kiện ghi**. Việc gọi `commit()` **không đồng nghĩa callback đã chạy xong**. Nếu stream chưa thực sự bắt đầu đọc hoặc event bị lọc, không thể suy ra consumer chắc chắn đã nhận. Vì vậy ví dụ đầy đủ bên dưới **bật event, lặp tạo một vài event trong thời hạn giới hạn và chờ tín hiệu callback**, thay vì gọi `commit()` một lần rồi kiểm tra ngay.

Không cần gọi `begin()`/`end()` đối với ví dụ event tức thời đơn giản. Với event đo một đoạn công việc, bạn có thể dùng `begin()`/`end()` rồi `commit()`; khi đó threshold về thời lượng có ý nghĩa đặc biệt quan trọng.

## 5. Ví dụ đầy đủ Java 17+: tạo stream từ JVM hiện tại và nhận event

Lưu thành tệp **`CurrentJvmRecordingStreamDemo.java`**:

```java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import jdk.jfr.Event;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public final class CurrentJvmRecordingStreamDemo {
    private CurrentJvmRecordingStreamDemo() {
    }

    @Name("lesson.Pulse")
    @Label("Lesson pulse")
    public static class Pulse extends Event {
        @Label("Message")
        public String message;
    }

    public static void main(String[] args)
            throws InterruptedException {

        if (!FlightRecorder.isAvailable()) {
            throw new IllegalStateException(
                    "JFR is not available in this JVM");
        }

        CountDownLatch received = new CountDownLatch(1);
        AtomicReference<String> observed = new AtomicReference<>();

        try (RecordingStream stream = new RecordingStream()) {
            // Limit retention in the stream's JFR repository.
            stream.setMaxAge(Duration.ofMinutes(1));

            // Enable our custom event without a duration threshold.
            stream.enable(Pulse.class).withoutThreshold();

            // Register callback before starting the stream.
            stream.onEvent("lesson.Pulse", event -> {
                String text = event.getString("message");
                if ("hello".equals(text)) {
                    observed.compareAndSet(null, text);
                    received.countDown();
                }
            });

            stream.onError(error -> error.printStackTrace(System.err));
            stream.startAsync();

            // startAsync() is asynchronous. Send several bounded
            // events so a startup/flush delay does not lose the test.
            long deadline = System.nanoTime()
                    + Duration.ofSeconds(20).toNanos();

            do {
                Pulse pulse = new Pulse();
                pulse.message = "hello";
                pulse.commit();

                if (received.await(250, TimeUnit.MILLISECONDS)) {
                    break;
                }
            } while (System.nanoTime() < deadline);

            if (received.getCount() != 0) {
                throw new IllegalStateException(
                        "No matching JFR event within deadline");
            }

            if (!"hello".equals(observed.get())) {
                throw new AssertionError("Unexpected event payload");
            }

            System.out.println("received=" + observed.get());
        }

        System.out.println("streamClosed=true");
    }
}
```

**Biên dịch và chạy:**

```bash
javac --release 17 CurrentJvmRecordingStreamDemo.java
java CurrentJvmRecordingStreamDemo
```

**Stdout mong đợi khi JFR khả dụng và callback nhận được event trong thời hạn:**

```text
received=hello
streamClosed=true
```

Đây là **đầu ra kỳ vọng cho ca thành công**, không phải bảo đảm trên mọi JVM và mọi điều kiện tải. Nếu JFR không được tích hợp, repository không truy cập được hoặc event không đến trước deadline, chương trình **báo lỗi rõ ràng** thay vì in giả một kết quả thành công. Đặc biệt, thời hạn 20 giây chỉ là một giới hạn kiểm thử, không chứng minh JFR có độ trễ cố định hay đảm bảo giao event trong mọi môi trường.

### Giải thích từng bước chạy

1. `FlightRecorder.isAvailable()` kiểm tra nhanh JVM có khả năng JFR; nó không thay thế xử lý lỗi có thể xảy ra khi constructor cần tạo repository.
2. `new RecordingStream()` tạo luồng event cho **JVM đang thực thi ví dụ**, không cần PID của tiến trình khác và không có đường dẫn `.jfr`.
3. `setMaxAge(Duration.ofMinutes(1))` đặt giới hạn tuổi dữ liệu giữ trong recording/repository của stream, tránh lưu giữ vô hạn khi monitor chạy lâu. Trong hệ thống thật cũng nên xem xét `setMaxSize(...)` theo mức tài nguyên cho phép.
4. `enable(Pulse.class).withoutThreshold()` bật loại event tự tạo. `withoutThreshold()` bỏ điều kiện thời lượng tối thiểu, phù hợp với event cực ngắn. Đây là cấu hình cần thiết khi bạn không muốn bỏ event do ngưỡng thời gian.
5. `onEvent("lesson.Pulse", ...)` đăng ký consumer trước khi gọi `startAsync()`. Callback nhận `RecordedEvent`, dùng `getString("message")` để đọc field được ghi.
6. `CountDownLatch` đếm về 0 sau khi callback nhìn thấy payload `"hello"`. `AtomicReference` lưu giá trị qua hai thread một cách có đồng bộ; khi main thread tiếp tục sau `await`, nó kiểm tra payload thực sự đã nhận.
7. `startAsync()` khởi động xử lý event trên một thread riêng. Main thread **không chặn tại lệnh khởi động**, nên có thể phát sự kiện bằng `Pulse.commit()`.
8. Vòng lặp giới hạn số lần chờ và thời gian toàn cục, giảm rủi ro tạo event **trước khi stream sẵn sàng** hoặc kiểm tra **trước khi dữ liệu được flush**. Nó cũng tránh vòng lặp bận chạy liên tục.
9. Nếu thời gian hết mà callback chưa nhận, chương trình ném `IllegalStateException`. Điều này là một **thất bại kiểm thử thật**, không nên “chữa” bằng cách luôn in `PASS`.
10. Khi rời khối `try-with-resources`, `close()` được gọi để đóng stream, giải phóng tài nguyên. Dòng `streamClosed=true` chỉ được in sau khi khối quản lý tài nguyên kết thúc bình thường.

Ví dụ này không in mỗi event trong callback, vì thời điểm và số lần callback chạy có thể thay đổi. Thay vào đó, chương trình chỉ in giá trị đã xác nhận nhận được. Đây là cách tạo **stdout kiểm thử có thể dự đoán** dù cơ chế truyền event là bất đồng bộ.

## 6. Dùng sự kiện JVM có sẵn thay vì custom event

Một ứng dụng quan sát thường không tự sinh event mà bật các loại event sẵn trong JVM. Ví dụ:

| Event JFR | Nội dung quan sát | Lưu ý |
| --- | --- | --- |
| `jdk.CPULoad` | Thông tin sử dụng CPU theo kỳ | Là event định kỳ; khoảng lấy mẫu/ghi phụ thuộc cấu hình và runtime |
| `jdk.GarbageCollection` | Một đợt hoạt động GC | Chỉ xuất hiện khi có hoạt động GC tương ứng và event được ghi |
| `jdk.ThreadSleep` | Các hoạt động sleep theo ngưỡng/cấu hình | Có thể bị lọc khi duration dưới threshold |
| `jdk.SocketRead`, `jdk.SocketWrite` | Hoạt động I/O mạng của JVM | Có thể chứa thông tin ứng dụng; nên hạn chế quyền và dữ liệu thu thập |
| `jdk.ExceptionThrown` | Ngoại lệ được ghi khi bật loại event này | Có thể tạo nhiều dữ liệu/overhead; không nên bật vô điều kiện trong production |

Tên event, field và tùy chọn có thể thay đổi theo phân phối/phiên bản JDK; kiểm tra **`EventType`/metadata của runtime** khi tích hợp một hệ thống bền vững. Không khẳng định mọi JVM đều sinh các event đó liên tục.

Một snippet Java hợp lệ trong method (cần xử lý `InterruptedException`):

```java
try (var rs = new jdk.jfr.consumer.RecordingStream()) {
    rs.setMaxAge(java.time.Duration.ofMinutes(5));

    rs.enable("jdk.GarbageCollection");
    rs.onEvent("jdk.GarbageCollection", event ->
            System.out.println("GC at " + event.getStartTime()));

    rs.startAsync();
    Thread.sleep(5_000);
}
```

Đoạn này có thể **không in dòng GC nào** nếu trong thời gian thử không phát sinh sự kiện GC được ghi. Không cố ép `System.gc()` để suy ra một số GC event cố định: lời gọi đó là một yêu cầu với JVM, không phải cam kết có GC ngay.

Nếu quan tâm quan sát định kỳ, `jdk.CPULoad` với `withPeriod(Duration.ofSeconds(1))` thường dễ thấy kết quả hơn trong một thử nghiệm dài đủ lâu, nhưng **không dùng số dòng event làm output chính xác**.

## 7. start(), startAsync(), close() và vòng đời

| API | Hành vi | Lưu ý |
| --- | --- | --- |
| `new RecordingStream()` | Tạo stream cho JVM hiện tại | Có thể thất bại khi JFR/repository không khả dụng |
| `new RecordingStream(Configuration)` | Tạo stream với settings từ cấu hình JFR | Phù hợp khi có profile/default JFR có sẵn |
| `enable(...)` | Bật loại event muốn ghi và trả `EventSettings` | Có thể cấu hình threshold/period |
| `onEvent(name, callback)` | Đăng ký hành động khi event cùng tên được phân phối | Nên đăng ký trước khi start |
| `start()` | Xử lý callback **trên thread hiện tại**, có thể chặn | Cần cơ chế đóng/kết thúc từ bên ngoài nếu chạy lâu |
| `startAsync()` | Xử lý callback trên **thread riêng** | Main thread có thể tiếp tục; phải giữ stream sống đủ lâu |
| `close()` | Đóng stream, giải phóng tài nguyên | Dùng `try-with-resources` khi có thể |
| `awaitTermination(...)` | Chờ stream kết thúc/đóng hoặc tới giới hạn chờ | Không có nghĩa stream tự dừng sau timeout |
| `setMaxAge(...)`, `setMaxSize(...)` | Giới hạn tuổi/dung lượng dữ liệu được lưu | Nên cân nhắc với monitor dài hạn |
| `onError(...)` | Đăng ký xử lý exception từ stream/actions | Không để handler tự gây lỗi chưa xử lý |

### start() chặn main thread

```java
try (var rs = new jdk.jfr.consumer.RecordingStream()) {
    rs.enable("jdk.CPULoad")
      .withPeriod(java.time.Duration.ofSeconds(1));
    rs.onEvent("jdk.CPULoad", event -> {
        System.out.println(event.getStartTime());
    });
    rs.start(); // Chặn thread này khi stream còn hoạt động.
}
```

Đoạn này **chỉ để giải thích semantics**, không nên chạy nguyên xi trong một bài test muốn kết thúc nhanh: nếu không có cơ chế đóng hoặc giới hạn thời gian, `start()` có thể tiếp tục chờ lâu. `startAsync()` thường phù hợp cho ví dụ nằm bên trong ứng dụng vẫn cần làm công việc khác.

### Không đóng ngay sau startAsync()

Cách dễ làm mất event:

```java
try (var rs = new jdk.jfr.consumer.RecordingStream()) {
    rs.onEvent("jdk.CPULoad", System.out::println);
    rs.startAsync();
}
// Stream đã bị đóng trước khi có đủ thời gian phân phối sự kiện.
```

Đoạn trên **biên dịch được** nhưng không bảo đảm nhận sự kiện nào. Hãy giữ stream sống tới khi điều kiện kiểm chứng đạt, công việc quan sát hoàn tất hoặc hết một thời hạn hợp lý. Có thể dùng `CountDownLatch`, `awaitTermination` theo ngữ cảnh hoặc vòng đời ứng dụng; không nên dùng `Thread.sleep` cố định như một cam kết đồng bộ tuyệt đối.

## 8. EventSettings: bật event không đồng nghĩa chắc chắn nhận được

`rs.enable("event.Name")` thiết lập việc event **được phép ghi**. Để thực sự được giao tới consumer, còn cần các điều kiện:

- **Event phải thực sự xảy ra.** Bật `jdk.GarbageCollection` không tạo ra một lần GC.
- **Threshold:** với event đo thời lượng, ngưỡng có thể bỏ những event quá ngắn. `withoutThreshold()` bỏ ngưỡng; `withThreshold(Duration.ofMillis(...))` đặt ngưỡng mới.
- **Period:** các event định kỳ như `jdk.CPULoad` có thể có `withPeriod(Duration.ofSeconds(1))`, nhưng thời điểm phát thực tế vẫn chịu ảnh hưởng của runtime.
- **Thời điểm bắt đầu:** nếu event xảy ra và kết thúc trước khi stream/recording sẵn sàng, callback không nhất thiết nhận được.
- **Phân phối không tức thời:** JFR dùng buffering/flush; callback có thể chạy sau thời điểm `commit()`.
- **Cấu hình, JDK và môi trường:** event có thể không có trong runtime, có settings khác hoặc bị giới hạn bởi quyền/tài nguyên.

Ví dụ kiểm tra việc tối ưu thu thập payload ở nguồn:

```java
Pulse event = new Pulse();
if (event.shouldCommit()) {
    event.message = "small payload";
    event.commit();
}
```

`shouldCommit()` hữu ích khi việc tạo nội dung payload tốn kém; nó kiểm tra tình trạng enabled và threshold tại thời điểm gọi. Đây là đoạn minh họa giả định class `Pulse` được khai báo như mục 4, không phải chương trình độc lập. Với bài kiểm chứng, mẫu `commit()` được lặp trong thời hạn để giảm rủi ro không có event đầu tiên.

## 9. Callback chạy ở đâu và nên làm gì?

Với `startAsync()`, API thực hiện các callback trên **một thread xử lý riêng**. Vì vậy bạn cần nghĩ đến an toàn luồng:

- Không tự động giả định field ở main thread sẽ nhìn thấy giá trị mới mà callback gán nếu không có đồng bộ. Dùng `CountDownLatch`, `AtomicReference`, `volatile` hoặc cấu trúc concurrency thích hợp.
- Tránh làm việc chậm hoặc chặn trong callback, ví dụ gọi dịch vụ mạng đồng bộ hoặc ghi một lượng log lớn. Callback xử lý chậm có thể làm tăng độ trễ và khối lượng sự kiện chờ xử lý.
- Không để exception từ callback bị lờ đi. `onError` có thể ghi nhận hoặc chuyển lỗi sang hệ thống quan sát; việc callback thất bại không đồng nghĩa caller đã nhận exception trực tiếp trên thread chính.
- Chọn `onEvent("jdk.CPULoad", action)` thay vì callback nhận mọi event nếu bạn chỉ quan tâm một loại; có thể giảm công lọc không cần thiết.
- Nếu bạn muốn đưa dữ liệu vào queue để xử lý ngoài callback, đặt giới hạn kích thước, chính sách từ chối/bỏ sự kiện và đo mức trễ. **Không** giữ vô hạn dữ liệu event trong RAM.
- Nếu dùng `setReuse(true)` ở API tương ứng, không giữ tham chiếu `RecordedEvent` lâu ngoài callback; event object có thể được tái sử dụng. Nếu muốn giữ dữ liệu lâu, sao chép các trường cần thiết thành một giá trị riêng.

Ví dụ trong bài giữ callback rất ngắn: chỉ đọc `message`, cập nhật `AtomicReference` và `CountDownLatch`. Không in mỗi event và không lưu cả `RecordedEvent` lâu dài.

## 10. Quản lý tài nguyên và an toàn dữ liệu

JFR thu thập các thông tin có thể bao gồm đường dẫn file, lệnh/chương trình, network endpoint hoặc thông tin chuyên biệt của ứng dụng. Event tùy chỉnh có thể vô tình chứa dữ liệu nhạy cảm như token hoặc thông tin người dùng.

**Nguyên tắc khi chạy ở production:**

1. Chỉ bật **những loại event và trường cần cho mục đích rõ ràng**; đừng bật mọi event và in toàn bộ payload khi không cần.
2. Với event tần suất cao, cân nhắc threshold, period và thời gian quan sát; theo dõi overhead CPU/I/O và memory.
3. Thiết lập `setMaxAge` và/hoặc `setMaxSize` nếu recording có thể tồn tại lâu. Giới hạn này kiểm soát dữ liệu lưu trong repository, **không tự giới hạn** collection hoặc queue mà ứng dụng của bạn tự xây.
4. Đóng stream đúng lúc bằng `try-with-resources` hoặc một cơ chế shutdown rõ ràng. Không để stream tồn tại mãi chỉ vì đã gọi `startAsync()`.
5. Chuyển những dữ liệu cần xuất ra ngoài theo chính sách bảo mật, giới hạn quyền đọc log và retention.
6. Không coi event stream là cơ chế **giao tin chính xác một lần** hay event bus nghiệp vụ bắt buộc: nó là kênh quan sát/chẩn đoán; latency, buffer và cấu hình ảnh hưởng sự kiện được tiêu thụ.

## 11. Các lỗi thường gặp và hướng sửa

### Lỗi A — Tưởng RecordingStream mở một file `.jfr`

`new RecordingStream()` tạo stream của JVM hiện tại. Đọc file `.jfr` đã có cần API `RecordingFile`; khi muốn dump recording hiện hành cần API/cấu hình phù hợp, không thể suy rằng constructor không tham số tự động đọc mọi file trong thư mục.

### Lỗi B — Bật event nhưng không đăng ký callback hoặc quên start

`enable(...)` chỉ quyết định event được bật trong recording; để tiêu thụ cần `onEvent(...)` và `start()`/`startAsync()`. Ngược lại, chỉ có `onEvent(...)` nhưng event bị tắt hoặc không xảy ra thì có thể không nhận gì.

### Lỗi C — Đóng stream quá sớm

`startAsync()` trả về trước khi callback nhất thiết chạy. Khối `try-with-resources` kết thúc ngay lập tức sau đó có thể đóng stream quá sớm. Cần một điều kiện chờ phù hợp và deadline để test không treo vô hạn.

### Lỗi D — Chờ start() xong rồi mới phát event trên cùng thread

`start()` xử lý đồng bộ và có thể chặn. Nếu cùng một thread phải phát event **sau** lệnh `start()`, phần phát có thể không được thực hiện. Dùng `startAsync()` hoặc một producer thread riêng.

### Lỗi E — Giả định callback giao sự kiện lập tức

Sự kiện commit xong không đồng nghĩa callback đã chạy; không test bằng `received.get()` ngay sau `commit()` nếu hai luồng chưa đồng bộ. Hãy dùng latch/future cùng timeout và xử lý ca không nhận.

### Lỗi F — Callback truy cập field không tồn tại

`recordedEvent.getString("fieldName")` có thể ném exception nếu field không có hoặc kiểu không phù hợp. Với event tùy chỉnh, giữ tên field nhất quán; với event built-in, kiểm tra metadata hoặc `hasField(...)` trước khi đọc các field không chắc chắn.

### Lỗi G — Bật mọi loại event trong production

Một số event có overhead và lượng dữ liệu đáng kể. Không tự cấu hình toàn bộ event với ngưỡng 0 mà chưa đánh giá tác động tài nguyên, quyền riêng tư và nhu cầu phân tích.

### Lỗi H — Không xử lý lỗi stream

`RecordingStream` có thể ném `IllegalStateException` khi không khởi tạo được Flight Recorder, hoặc callback gặp lỗi. Tạo chiến lược xử lý phù hợp; đừng chỉ dựa vào stdout để kết luận stream chắc chắn hoạt động.

## 12. Checklist kiểm chứng

| Mục cần kiểm | Cách xác nhận | Kỳ vọng |
| --- | --- | --- |
| JVM hỗ trợ JFR | `FlightRecorder.isAvailable()` | `true` trên JDK hỗ trợ và được cấu hình phù hợp |
| Đúng JVM nguồn | Tạo `new RecordingStream()` ngay trong app | Nhận dữ liệu của JVM đang chạy, không tự kết nối remote |
| Event được bật | `enable(Pulse.class).withoutThreshold()` | Custom event có thể được ghi |
| Callback đã đăng ký | `onEvent("lesson.Pulse", ...)` trước start | Consumer nhận đúng event name |
| Luồng xử lý khởi động | `startAsync()` | Main thread tiếp tục, callback xử lý bất đồng bộ |
| Event đã phát sinh | Tạo `Pulse` và gọi `commit()` | Có sự kiện nguồn để JFR ghi |
| Consumer xác nhận | `CountDownLatch` + kiểm tra payload | Không in PASS trước khi nhận |
| Kết thúc có kiểm soát | Deadline và try-with-resources | Không chờ mãi; `close()` được gọi |
| Đầu ra test | Hai dòng ở mục 5 | Chỉ khi đúng điều kiện nhận và đóng |
| Production | Cấu hình retention, event selection, callback | Không lưu vô hạn hoặc tạo overhead không kiểm soát |

Đối với event JVM có sẵn, thay vì đếm số dòng cố định, hãy kiểm thử **metadata/hình dạng** của event thực tế và điều kiện chạy cụ thể. Nếu không có event trong cửa sổ quan sát, hãy phân biệt “không phát sinh”, “bị lọc”, “chưa flush” và “không hỗ trợ”.

## 13. Bài tập thực hành

**Bài 1 — luồng từ JVM hiện tại:** Tạo `@Name("lesson.OrderProcessed")` cho class `OrderProcessed extends Event` với hai field `String orderType` và `long amount`. Tạo `RecordingStream`, bật loại event này, đăng ký `onEvent("lesson.OrderProcessed", ...)`, sau đó start async và tự commit vài event. Đếm số event callback nhận bằng `AtomicInteger`; xác nhận ít nhất một event có `orderType` bạn chủ động phát.

**Bài 2 — sự kiện có sẵn:** Bật `jdk.CPULoad` mỗi giây và in `getStartTime()` trong 5–10 giây. Giải thích vì sao số dòng và thời điểm callback **không cố định** theo chương trình. Chỉ ghi nhận kết quả thực tế, không khẳng định có đúng 5 hay 10 event.

**Bài 3 — lỗi vòng đời:** Thử phiên bản gọi `startAsync()` rồi rời `try` ngay; so sánh với phiên bản dùng `CountDownLatch`. Giải thích vì sao sự khác nhau có thể phụ thuộc tốc độ flush và thread scheduling.

**Bài 4 — chặn callback:** Cố ý đưa `Thread.sleep(500)` vào callback trong môi trường thử nghiệm, tạo nhiều sự kiện và quan sát độ trễ. Sau đó bỏ `sleep`, chỉ đẩy dữ liệu ngắn sang một queue có giới hạn. Giải thích ảnh hưởng đến tốc độ tiêu thụ và rủi ro tích tụ dữ liệu.

**Bài 5 — xử lý thất bại:** Đặt timeout ngắn cho latch. Nếu không có event đến, hãy trả lỗi test và thông tin cấu hình; không sửa test thành “luôn PASS”. Nhấn mạnh phân biệt **không có event nguồn** và **chưa nhận event qua stream**.

**Tiêu chí hoàn thành:** Bạn chứng minh được một event của **JVM hiện tại** đã tới callback qua `RecordingStream`, trình bày được vai trò của `enable`, `onEvent`, `startAsync` và `close`, và thiết kế được bài thử có đồng bộ/timeout thay vì dựa vào timing may rủi.

## Tài liệu chính thức

- [Oracle JDK 26 — RecordingStream API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): mô tả current JVM, constructors, settings, callback, vòng đời mới nhất.
- [Oracle JDK 17 — RecordingStream API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): các API xuất hiện trong chương trình Java 17+ ở bài.
- [Oracle JDK 17 — Event API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Event.html): subclass, `commit`, `isEnabled`, `shouldCommit`.
- [Oracle JDK 17 — RecordedEvent API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): metadata, thời gian và field của event đã ghi.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): API được bổ sung vào Java 14.
- [dev.java — Configuring the JDK Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/): cách chọn event, threshold, period và cấu hình JFR.

**Ghi nhớ:** `new RecordingStream()` là điểm khởi đầu cho **sự kiện JFR của JVM hiện tại**. Muốn nhận event, cần bật đúng loại, đăng ký callback, khởi động stream và giữ nó sống đủ lâu. Để code an toàn, hãy quản lý tài nguyên, giới hạn dữ liệu lưu, đồng bộ callback và kiểm chứng kết quả mà không giả định streaming là tức thời.