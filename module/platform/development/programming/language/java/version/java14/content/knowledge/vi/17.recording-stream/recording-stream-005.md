# Khởi chạy chặn bằng `RecordingStream.start()` trong Java Flight Recorder

> **Chủ đề:** Java 14 → *RecordingStream* → **Khởi chạy chặn bằng start**. JFR Event Streaming API (`jdk.jfr.consumer.RecordingStream` và `EventStream`) được giới thiệu từ **Java 14 (JEP 349)** và vẫn được hỗ trợ trong JDK hiện đại. Các ví dụ chính dùng **JDK 17+**, không dựa vào tính năng preview, API đã bị loại bỏ hay cách khởi động JFR kiểu cũ.

## 1. `start()` có nghĩa là gì?

`RecordingStream` là một lớp của **Java Flight Recorder (JFR)**, dùng để **bắt đầu ghi các JFR events và tiếp nhận sự kiện từ chính JVM hiện tại**. Khác với việc đọc một tệp `.jfr` đã tạo sẵn, `RecordingStream` quản lý một bản ghi đang hoạt động cùng luồng tiêu thụ sự kiện.

Cú pháp điển hình:

~~~java
try (var stream = new jdk.jfr.consumer.RecordingStream()) {
    stream.enable("jdk.CPULoad")
            .withPeriod(java.time.Duration.ofSeconds(1));

    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(event.getEventType().getName());
    });

    stream.start(); // CHẶN luồng đang gọi
}
~~~

Đây là **đoạn minh họa** chứ không phải ví dụ nên chạy mãi trong ứng dụng. Mấu chốt:

- `stream.start()` **khởi động việc xử lý sự kiện trên luồng đang gọi** (*current/calling thread*). Nếu gọi từ `main`, handler sự kiện cũng chạy trên chính luồng ấy trong quá trình `start()`.
- Khi `start()` đang chạy, **luồng gọi không thực hiện tiếp câu lệnh phía sau**. Nó đang xử lý các action/callback của stream, không phải lập tức trả về như một hàm “start rồi thoát”.
- `start()` thường **chỉ trả về khi stream kết thúc**, ví dụ được `close()` từ một luồng khác, đạt end time đã cấu hình, hoặc kết thúc theo điều kiện của hệ thống.
- `start()` không trả về một `Thread`, `Future` hay `RecordedEvent`; chữ ký là `void start()`.
- Nếu cần thực hiện công việc khác đồng thời trên luồng gọi, hãy cân nhắc **`startAsync()`**, hoặc tạo một luồng do ứng dụng quản lý để gọi `start()`.

**Phân biệt ngắn gọn:** `start()` = **xử lý đồng bộ, giữ luồng gọi**; `startAsync()` = **xử lý bất đồng bộ trên một luồng riêng**.

API JFR không phải một tính năng preview của `record` hay `switch`; không cần `--enable-preview`. Nhưng cần một runtime JDK có mô-đun `jdk.jfr` và khả năng tạo bản ghi Flight Recorder.

## 2. Thứ tự các bước đúng

Trước khi gọi `start()`, ứng dụng thông thường sẽ:

1. **Tạo** `RecordingStream`.
2. **Bật loại event cần theo dõi** bằng `enable("jdk.CPULoad")`, `enable(MyEvent.class)` hoặc chọn cấu hình có sẵn. Có thể cấu hình `withPeriod`, `withoutThreshold`, giới hạn dữ liệu lưu... theo ý nghĩa event.
3. **Đăng ký handler** bằng `onEvent("tên.event", action)` để nhận event, có thể thêm `onError`, `onClose`, `onFlush`.
4. **Xác định cách kết thúc** trước khi chặn: dùng `setEndTime(...)`, một thread gọi `close()`, hoặc điều kiện nghiệp vụ gọi `close()` từ callback.
5. Gọi **`start()` trên luồng được phép bị chiếm giữ**.
6. Khi stream dừng và `start()` trả về, chạy mã phía sau, rồi `try-with-resources` bảo đảm tài nguyên được đóng.

~~~text
Luồng gọi (ví dụ main)                  JVM / JFR
------------------------                -----------------------
new RecordingStream() ----------------> chuẩn bị ghi và streaming
enable(...), onEvent(...)
println("before")
start() -------------------------------> bắt đầu thu nhận/đọc sự kiện
   |                                    event được ghi, flush theo batch
   |<----------------------------------- chuyển event tới onEvent(...)
   | chạy callback trên luồng gọi
   | chạy tiếp vòng xử lý/đợi event
   |                         luồng khác có thể gọi stream.close()
   |<----------------------------------- stream kết thúc
start() trả về
println("after")
đóng tài nguyên cuối try-with-resources
~~~

**Điểm quan trọng về `try-with-resources`:** nó **không tự gọi `close()` trong lúc luồng vẫn đang mắc ở `start()`**. Phần `finally` của try-with-resources chỉ chạy khi việc thực thi rời khỏi thân khối try. Vì thế, đoạn mã đặt `stream.start()` mà không có cách dừng phù hợp có thể giữ chương trình mãi trong vòng streaming.

## 3. Chương trình hoàn chỉnh: một luồng khác gọi `close()` để giải phóng `start()`

Đây là minh họa dễ kiểm chứng: main thread gọi `start()`, một helper thread chờ một lát rồi gọi `close()`. Handler được đăng ký nhưng không in event, để stdout minh họa thứ tự đồng bộ **không phụ thuộc số lượng event mà JFR thực sự phát ra**.

Lưu dưới tên **`JfrBlockingCloseDemo.java`**:

~~~java
import java.time.Duration;
import jdk.jfr.consumer.RecordingStream;

public class JfrBlockingCloseDemo {

    public static void main(String[] args)
            throws InterruptedException {

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable("jdk.CPULoad")
                    .withPeriod(Duration.ofSeconds(1));

            // Handler thật; không in để output minh họa ổn định.
            stream.onEvent("jdk.CPULoad", event -> {
                // Đọc event và gửi metric nếu ứng dụng có nhu cầu.
            });

            Thread closer = new Thread(() -> {
                try {
                    Thread.sleep(700);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }

                System.out.println("worker: closing");
                stream.close();
            }, "jfr-closer");

            System.out.println("main: before start");
            closer.start();

            stream.start(); // main bị giữ tại đây đến khi stream dừng.

            System.out.println("main: after start");
            closer.join();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ có `jdk.jfr`:

~~~bash
javac --release 17 -encoding UTF-8 JfrBlockingCloseDemo.java
java JfrBlockingCloseDemo
~~~

**Stdout trong lần chạy kiểm thử:**

~~~text
main: before start
worker: closing
main: after start
~~~

**Giải thích thứ tự:**

1. Main in `main: before start`, tạo và khởi chạy helper thread.
2. Main gọi `stream.start()` và bắt đầu xử lý stream trên chính luồng main. Vì lời gọi này **blocking**, main chưa thể in `main: after start`.
3. Helper thread ngủ khoảng 700 ms, rồi in `worker: closing` và gọi `stream.close()`. Chính lời gọi `close()` mới yêu cầu dừng streaming đang hoạt động.
4. Khi `start()` hoàn tất việc dừng, main tiếp tục đến `main: after start`. `closer.join()` chỉ bảo đảm helper thread đã kết thúc trước khi rời khối.
5. Thời gian thực tế có thể dài hơn 700 ms do khởi tạo JFR, lịch chạy của JVM, thời gian flush và độ tải hệ thống. **Không dùng thời lượng tuyệt đối của lần chạy làm một hợp đồng hiệu năng.**

**Tính chất cần nhớ:** `close()` có thể dừng stream ngay hoặc sau lần flush kế tiếp; theo API, nó **không hứa hẹn tất cả callback đã hoàn thành trước thời điểm `close()` trả về**. Ví dụ bảo đảm **thứ tự các dòng in của luồng minh họa** chứ không cam kết sự kiện JFR nào được nhận.

### Tại sao không đóng stream bằng một lệnh ngay sau `start()`?

~~~java
try (var stream = new RecordingStream()) {
    stream.start();
    stream.close(); // Không thể đóng đúng lúc nếu start() vẫn đang chặn.
}
~~~

Đoạn code này **chỉ để minh họa lỗi thiết kế**, giả định đã import `RecordingStream`. Lệnh `close()` đứng sau `start()` trên **cùng luồng** sẽ không chạy được khi `start()` còn chặn. Phải có **cách kết thúc độc lập**, hoặc chọn `startAsync()`.

## 4. Chương trình hoàn chỉnh thứ hai: đặt `setEndTime()` trước khi gọi `start()`

Không phải ứng dụng nào cũng cần một helper thread. Khi mục tiêu là **thu thập trong một khoảng thời gian hữu hạn**, `EventStream.setEndTime(Instant)` cho phép chỉ định **thời điểm kết thúc**, và tài liệu JDK quy định stream đóng tại end time.

Lưu dưới tên **`JfrEndTimeDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;
import jdk.jfr.consumer.RecordingStream;

public class JfrEndTimeDemo {

    public static void main(String[] args) {
        try (RecordingStream stream = new RecordingStream()) {
            stream.enable("jdk.CPULoad")
                    .withPeriod(Duration.ofSeconds(1));

            // Ứng dụng có thể đăng ký xử lý event ở đây.
            stream.onEvent("jdk.CPULoad", event -> {
                // Không in: số event có thể khác nhau tùy hệ thống.
            });

            stream.setEndTime(Instant.now().plusSeconds(2));

            System.out.println("before");
            stream.start(); // Chặn cho đến khi stream kết thúc.
            System.out.println("after");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 JfrEndTimeDemo.java
java JfrEndTimeDemo
~~~

**Stdout:**

~~~text
before
after
~~~

- `setEndTime(...)` cần được cấu hình **trước** `start()`. Không nhầm với `awaitTermination(Duration)`: nó thiết lập **thời điểm đóng**, chứ không chỉ là chờ một khoảng rồi trả về.
- `start()` vẫn là lời gọi blocking. `after` chỉ xuất hiện khi stream đã kết thúc, không phải vì `start()` được chạy nền.
- `Instant.now().plusSeconds(2)` lấy thời điểm từ lúc gọi cấu hình; đây là ví dụ hữu hạn, **không bảo đảm thời gian chạy chính xác 2,000 ms**. Việc khởi tạo JFR và dispatch event có độ trễ.
- `jdk.CPULoad` được bật để minh họa cấu hình theo dõi event, nhưng **stdout cố ý không in các event**, vì không thể hứa số event luôn như nhau trên mọi JVM.

### Khi nào dùng từng cách dừng?

| Cách dừng | Khi phù hợp | Điều cần chú ý |
| --- | --- | --- |
| `stream.setEndTime(instant)` trước `start()` | Theo dõi theo thời hạn xác định | Thời điểm tính theo đồng hồ và phải được thiết lập trước khi bắt đầu |
| `stream.close()` từ thread khác | Người dùng hủy theo dõi, service shutdown, kết thúc một tác vụ | Dừng tức thời hoặc sau flush, không bảo đảm drain hết callback |
| `stream.close()` từ `onEvent` | Đủ điều kiện nghiệp vụ thì chấm dứt | Có thể còn callback trong batch/đường xử lý đã nhận; viết handler idempotent |
| `startAsync()` rồi `close()` | Luồng chính phải tiếp tục công việc khác | Có thể đóng quá sớm nếu khối try kết thúc ngay |
| `stop()` trên Java 20+ | Muốn dừng và đợi tiêu thụ các event đã ghi | Không gọi `stop()` **ngay trong callback**, có thể chặn vô hạn; không có trong ví dụ `--release 17` |

**Phân biệt `stop()` và `close()`:** `RecordingStream.stop()` là API mới từ **Java 20**, vẫn dùng trong JDK hiện đại để dừng và chờ tiêu thụ các event của bản ghi; còn `close()` có từ API cơ bản và dùng được khi viết ví dụ Java 17+. Dùng `stop()` trong chương trình biên dịch bằng `--release 17` sẽ lỗi vì API này chưa tồn tại trong Java 17.

## 5. Luồng chạy callback khi gọi `start()`

Theo hợp đồng `EventStream`:

- `start()` thực hiện các action **trên current thread**. Nếu gọi `start()` từ `main`, các `onEvent` actions được dispatch tại `main` trong khi streaming.
- `startAsync()` thực hiện actions **trên một luồng riêng** do stream quản lý.
- Dù chạy trên current thread, **JFR vẫn có thể sinh event từ những luồng JVM khác**. Luồng **phát sinh event** và luồng **nhận callback** là hai khái niệm khác nhau.
- Callback có thể được gọi khi JVM có batch event được flush; không nên giả định `event.commit()` ở một luồng sẽ ngay lập tức kích hoạt callback trên luồng đang xử lý `start()`.

Ví dụ tự định nghĩa một event và đăng ký handler (**đoạn đặt trong một lớp/phương thức, không phải file độc lập**):

~~~java
@jdk.jfr.Name("demo.Ping")
public static class Ping extends jdk.jfr.Event {
    public String message;
}

// Trong method, sau khi đã tạo RecordingStream stream:
Thread caller = Thread.currentThread();

stream.enable(Ping.class).withoutThreshold();
stream.onEvent("demo.Ping", event -> {
    System.out.println(event.getString("message"));
    System.out.println(
            Thread.currentThread() == caller);
});
~~~

Nếu class chứa đoạn trên có thể tạo event `Ping` và có một luồng khác gọi `commit()` trong lúc `stream.start()` đang chạy, handler sẽ chạy trên **luồng đã gọi `start()`**. Tài liệu không bảo đảm **thời điểm, số lượng** hay **thứ tự giữa các batch** như một event bus đồng bộ. Đừng viết test mong đợi callback chạy ngay sau câu `new Ping().commit()`.

### Tránh giữ callback quá lâu

Các callback cùng chạy trong vòng xử lý streaming của `start()`. Nếu callback thực hiện I/O chậm, block trên network hoặc giữ lock lâu, việc tiếp nhận các event tiếp theo có thể bị trễ, tăng độ trễ giám sát. Với ứng dụng thực:

- Giữ handler ngắn; trích xuất dữ liệu cần thiết, đưa sang cấu trúc hàng đợi/consumer riêng nếu xử lý nặng.
- Tránh khóa có thể gây deadlock với những thread đang gọi `close()` hoặc sinh event.
- Ghi rõ khả năng mất/bỏ sót event do cấu hình, giới hạn lưu trữ, buffer và chu kỳ flush; JFR không phải hệ thống message queue bảo đảm giao hàng theo từng event.
- Không giữ tham chiếu `RecordedEvent` ngoài callback nếu stream đang bật reuse object. Theo hợp đồng `EventStream`, các object `RecordedEvent` có thể được tái sử dụng; nếu cần giữ event sau callback, cân nhắc `setReuse(false)` hoặc **sao chép các trường cần thiết**.
- Đừng gán ý nghĩa thời gian thực tuyệt đối cho `onFlush`: nó phản ánh các đợt batch được flush, không phải đồng hồ callback từng mili giây.

## 6. So sánh `start()` với `startAsync()` và `awaitTermination()`

| Phương thức | Trả về ngay? | Callback chạy ở đâu? | Tình huống điển hình |
| --- | --- | --- | --- |
| `start()` | **Không**; chặn đến khi stream kết thúc | **Luồng gọi** | Một luồng dành riêng cho giám sát, tác vụ CLI chạy đến khi dừng |
| `startAsync()` | Thường **trả về sau khi khởi chạy luồng xử lý**, không đợi stream kết thúc | **Một luồng riêng** của stream | Ứng dụng cần tiếp tục công việc trên luồng gọi |
| `awaitTermination()` | **Chặn** đến khi kết thúc/đóng hoặc bị interrupt | Không khởi chạy stream; chỉ chờ | Chờ `startAsync()` kết thúc |
| `awaitTermination(Duration)` | Chặn **tối đa thời gian chỉ định**, trừ khi kết thúc sớm/interrupt | Không phải cơ chế tự đóng stream | Đợi hữu hạn cho stream đã được khởi chạy |

Với `startAsync()`, đoạn sau là **một mẫu cấu trúc hợp lý**:

~~~java
try (var stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad")
            .withPeriod(Duration.ofSeconds(1));
    stream.onEvent("jdk.CPULoad", event -> {
        // Xử lý event mà không chặn main ở startAsync().
    });

    stream.startAsync();
    doSomeOtherWork(); // Hàm do ứng dụng định nghĩa.
    stream.close();
}
~~~

Đây là **đoạn minh họa**, cần import `RecordingStream`/`Duration` và cài đặt `doSomeOtherWork()`. `startAsync()` cho phép luồng gọi **chạy `doSomeOtherWork()`**. Hãy bảo đảm stream vẫn còn sống trong khi công việc diễn ra. Nếu phần try đóng ngay sau `startAsync()`, stream có thể bị đóng quá sớm, trước khi bất cứ event nào được xử lý.

Nếu chỉ cần chờ hữu hạn:

~~~java
stream.startAsync();
stream.awaitTermination(Duration.ofSeconds(3));
// Hết 3 giây chờ KHÔNG có nghĩa stream đã tự dừng.
// Gọi close() nếu muốn kết thúc thực sự.
stream.close();
~~~

Đây là đoạn minh họa trong một phương thức có thể khai báo `throws InterruptedException`. `awaitTermination(Duration)` có thể trả về vì hết timeout **trong khi stream còn chạy**. Đừng đồng nhất nó với `setEndTime(Instant)`, vì `setEndTime` mới là cấu hình **đóng stream ở một thời điểm**.

## 7. Xử lý lỗi và vòng đời stream

### 7.1. `IllegalStateException` khi gọi sai trạng thái

`start()` và `startAsync()` là thao tác bắt đầu vòng đời xử lý stream; theo API có thể ném `IllegalStateException` nếu stream đã được bắt đầu hoặc đã đóng. Không gọi `start()` lần hai trên cùng một `RecordingStream` chỉ vì muốn “đợi thêm event”. Nếu cần một phiên giám sát mới, tạo một `RecordingStream` mới và cấu hình lại.

Tạo stream cũng có thể thất bại (ví dụ JVM thiếu hỗ trợ Flight Recorder hoặc nơi lưu repository không truy cập được). Những trường hợp này cần xử lý/ghi log rõ ràng; không mặc định mọi runtime rút gọn đều có đủ mô-đun và cấu hình JFR.

### 7.2. `onError` không thay thế mọi `try/catch`

~~~java
stream.onError(error -> {
    System.err.println("JFR action error: " + error);
});
~~~

Đây là **đoạn minh họa sau khi tạo stream**. `onError(Consumer<Throwable>)` xử lý lỗi bất ngờ trong các action/callback mà JFR phát hiện; nếu không đăng ký, mặc định có thể in stack trace ra stderr. Bản thân `onError` không nên ném lỗi tiếp. Lỗi khi khởi tạo stream, cấu hình sai, `IllegalStateException` do gọi lifecycle sai vẫn cần được xử lý ở tầng tạo/khởi động phù hợp.

### 7.3. `onClose` và các điều kiện thoát

~~~java
stream.onClose(() -> {
    System.out.println("JFR stream closed");
});
~~~

Dùng `onClose` khi cần biết stream đã đóng để dọn trạng thái/đánh dấu kết thúc. Không mặc định `onClose` luôn chạy trên luồng `main`: nó là một action gắn với thời điểm đóng và có thể được thực hiện trong ngữ cảnh phù hợp của stream/luồng gọi close; API còn quy định nếu đăng ký sau khi stream đã đóng thì callback được gọi ngay trên current thread.

`close()` được phép gọi lại trên một stream đã đóng mà không tạo thêm tác động. Tuy nhiên, **đóng không bảo đảm mọi action đã hoàn thành trước khi close trả về**; nếu cần drain toàn bộ các event của recording, đối chiếu `stop()` trên JDK hỗ trợ và tránh gọi nó trong callback.

### 7.4. Đừng chặn UI thread hoặc request thread

Với ứng dụng GUI, server HTTP hay hệ thống xử lý yêu cầu đồng thời, gọi `start()` trực tiếp trong UI thread hoặc thread phục vụ request có thể làm giao diện mất phản hồi / request bị giữ vô hạn. Có thể:

- Gọi `startAsync()`, giữ vòng đời của stream trong một service/component chuyên trách.
- Hoặc tạo luồng giám sát riêng, đặt `start()` trong luồng ấy; chủ động dừng bằng `close()` khi service shutdown.
- Đặt chính sách resource lifecycle, giới hạn dữ liệu (ví dụ `setMaxAge`/`setMaxSize`) và xử lý lỗi rõ ràng trước khi chạy liên tục.

Điều cần quyết định **không chỉ** là “dùng start hay startAsync”, mà là **thread nào được phép chờ, ai sở hữu stream, và luồng nào có quyền kết thúc nó**.

## 8. Điều kiện dừng từ callback: lưu ý về batch và khả năng chặn

Một trường hợp hữu ích là dừng khi đã thấy sự kiện cần tìm:

~~~java
java.util.concurrent.atomic.AtomicBoolean finished =
        new java.util.concurrent.atomic.AtomicBoolean();

stream.onEvent("demo.Ping", event -> {
    if (finished.compareAndSet(false, true)) {
        // Đã nhận một event phù hợp.
        stream.close();
    }
});
~~~

Đây là đoạn trong phương thức sau khi tạo `stream` và cài đặt loại event `demo.Ping`; **không tự tạo event**. Vì JFR giao event theo batch, `close()` được gọi trong callback **không cam kết rằng sẽ tuyệt đối không còn callback nào khác được gọi** trước khi streaming thực sự kết thúc. `AtomicBoolean` giúp logic dừng chỉ kích hoạt một lần. Mã ứng dụng cần chấp nhận callback có thể còn nhìn thấy những event đã được buffer.

**Cảnh báo phiên bản hiện đại:** từ Java 20, `RecordingStream.stop()` cho phép dừng recording và **chờ tất cả event trong recording được tiêu thụ**. Tài liệu Oracle cảnh báo **không gọi `stop()` từ một action như `onEvent`** vì có thể gây **chặn vô hạn**; dùng `close()` nếu cần ngắt stream từ action. Ví dụ `start()` Java 17+ ở đây dùng `close()` để tương thích rộng và không yêu cầu API mới hơn.

Để tránh ứng dụng treo khi **không có event nào khớp**, khi thiết kế thực tế nên có cơ chế dừng độc lập (timeout tổng thể, shutdown hook, luồng điều phối hoặc `setEndTime`), chứ không chỉ trông chờ một loại event có thể không bao giờ xảy ra.

## 9. Hạn chế về event và timing không nên bỏ qua

- `RecordingStream` đọc sự kiện qua **JFR Event Streaming**, sự kiện có thể được phân phối theo **batch/flush**; không đồng nhất với một lời gọi đồng bộ kiểu `event.commit()` trực tiếp chạy `onEvent`.
- Khi cần một event nhất định, phải **bật event phù hợp** và đặt ngưỡng/chu kỳ tương thích: ví dụ `enable("jdk.ThreadSleep").withoutThreshold()` hoặc `enable("jdk.CPULoad").withPeriod(Duration.ofSeconds(1))`. Có event không được phát sinh trong điều kiện đang chạy.
- Event delivery trong batch có thứ tự theo end time của các event trong batch nếu sắp xếp bật, nhưng không giả định mọi batch của cả phiên là một thứ tự toàn cục tuyệt đối; JFR không phải event bus đảm bảo từng event đến tức thì.
- Nếu việc chạy ngắn hoặc đóng sớm, có thể **không kịp nhận** event đã tạo. `close()` không hứa sẽ drain toàn bộ; cân nhắc `stop()` ở JDK mới khi mục đích là bảo toàn batch đã ghi.
- Handler có thể nhận một `RecordedEvent` được tái sử dụng nếu bật reuse. Không giữ object đó sau callback nếu không hiểu rõ `setReuse`; trích xuất primitive/`String` cần thiết và truyền sang hàng đợi nội bộ.
- JFR có chi phí lưu trữ/CPU dù được tối ưu cho observability. Với stream dài hạn, quyết định thời gian sống, loại event và giới hạn lưu trữ.

## 10. Lỗi hiểu sai phổ biến

| Sai sót | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “`start()` chỉ khởi động rồi trả về ngay.” | Nó **chặn** trên luồng gọi trong suốt thời gian streaming. | Dùng `startAsync()` hoặc luồng chuyên trách nếu không muốn chặn. |
| Đặt `close()` ngay sau `start()` trên cùng luồng | Lệnh `close()` không chạy cho đến khi `start()` trả về. | Dừng từ luồng khác, callback, hoặc end time. |
| Nghĩ `try-with-resources` tự thoát khi vào `start()` | `close()` tự động chạy **khi rời** try, không phải trong lúc đang mắc ở `start()`. | Thiết kế điều kiện kết thúc trước khi gọi. |
| Dùng `awaitTermination(Duration)` như lệnh stop | Nó chỉ chờ có timeout, **không đóng** stream. | `close()` hoặc `setEndTime`/`stop()` (JDK phù hợp). |
| Gọi `start()` hai lần trên cùng stream | Sai vòng đời, có thể ném `IllegalStateException`. | Tạo stream mới cho phiên mới. |
| Giả định handler `onEvent` chạy trên luồng đã commit event | Với `start()`, actions chạy trên **luồng gọi start**. | Phân biệt producer và consumer. |
| Giả định `event.commit()` khiến callback chạy ngay | Events có batch/flush và lịch scheduling. | Thiết kế xử lý bất đồng bộ theo JFR delivery. |
| Gọi `stop()` bên trong `onEvent` | Có thể deadlock/chặn vô hạn khi đợi event tiêu thụ. | Dùng `close()` từ callback; `stop()` khi thích hợp từ luồng điều phối. |
| Chỉ dựa vào một event hiếm để kết thúc | Nếu event không đến, `start()` có thể chặn vô hạn. | Thêm end time hoặc cơ chế shutdown độc lập. |
| Đóng stream ngay sau `startAsync()` | Stream có thể đóng trước khi event được nhận. | Giữ scope/lifecycle đủ lâu. |
| Callback làm I/O/block dài | Làm chậm xử lý event trên luồng streaming. | Handler ngắn, offload xử lý nặng. |
| Giả định `close()` đồng bộ với toàn bộ callback | API không bảo đảm đã xử lý xong mọi action trước khi close trả về. | Thiết kế theo semantics của close/stop và kiểm tra chính sách drain. |
| Lấy count event làm output cố định giữa các JVM | Số event và thời điểm flush biến thiên. | Chỉ assert các quan hệ về lifecycle có bảo đảm; kiểm thử event có điều kiện. |

## 11. Checklist khi dùng `RecordingStream.start()`

- [ ] JVM có mô-đun `jdk.jfr` và hỗ trợ Flight Recorder; dự án dùng API hiện hành (Java 17+ cho mã ví dụ).
- [ ] `RecordingStream` được tạo trong phạm vi có chủ sở hữu rõ, thường là `try-with-resources`.
- [ ] Đã bật đúng event cần theo dõi và đặt ngưỡng/chu kỳ phù hợp.
- [ ] Các handler quan trọng đã được đăng ký trước khi streaming để không bỏ lỡ giai đoạn khởi động.
- [ ] Đã xác định **luồng nào sẽ bị chặn** khi gọi `start()`; không dùng UI/request thread nếu không muốn giữ nó.
- [ ] Đã thiết lập ít nhất một **cách dừng độc lập**: `setEndTime`, đóng từ luồng khác, hoặc sự kiện có guard và fallback.
- [ ] Không đặt logic đóng stream duy nhất **sau `start()`** trên cùng luồng.
- [ ] Handler xử lý ngắn, không deadlock, không giữ `RecordedEvent` bị reuse ngoài vòng đời callback.
- [ ] Phân biệt `close()` và `stop()` (Java 20+) khi quyết định có cần drain event hay không.
- [ ] `onError`/`onClose` được dùng khi giúp chẩn đoán sự cố hoặc quản lý lifecycle; không ném lỗi từ error handler.
- [ ] Có chính sách thời gian chạy, giới hạn lưu trữ, số lượng event và shutdown cho môi trường production.
- [ ] Chương trình được kiểm tra với tình huống **không có event nào xuất hiện**, không chỉ tình huống có event.

## 12. Bài tập thực hành

1. Chạy `JfrBlockingCloseDemo`. Dự đoán vì sao `main: after start` phải xuất hiện **sau** `worker: closing`. Đổi thời gian sleep của helper thread; điều gì về **thứ tự** vẫn phải giữ?
2. Chạy `JfrEndTimeDemo` và dùng đồng hồ đo thời gian toàn chương trình. Giải thích vì sao không nên viết test yêu cầu thời lượng chính xác bằng 2.000 ms.
3. Tự thêm handler `onEvent("jdk.CPULoad", ...)` in một giá trị CPU. Tăng end time đủ dài; giải thích vì sao số dòng/event có thể khác nhau giữa các lần chạy.
4. Viết `new RecordingStream(); stream.start(); stream.close();` trong cùng luồng (có sẵn JFR). Lý giải vì sao đó là một lỗi thiết kế nếu không có cơ chế dừng khác.
5. Thay `stream.start()` trong một tác vụ bằng `stream.startAsync()`; cho luồng chính chạy một công việc, rồi đóng stream khi công việc hoàn tất. So sánh callback thread.
6. Thử `awaitTermination(Duration.ofSeconds(1))` sau `startAsync()`; khi trả về do timeout, tại sao stream có thể vẫn đang chạy?
7. Định nghĩa một `jdk.jfr.Event` tùy chỉnh, bật bằng `enable(MyEvent.class)`, phát sự kiện từ thread khác và kiểm tra handler nhận trên thread đang gọi `start()`.
8. Đọc Javadoc `RecordingStream.stop()` của Java 25 và giải thích vì sao gọi `stop()` trực tiếp trong `onEvent` có thể chặn vô hạn, còn `close()` thích hợp hơn để ngắt.
9. Thiết kế cơ chế shutdown an toàn cho một service theo dõi JFR: ai tạo stream, ai đóng, luồng nào xử lý callback, làm sao tránh mất tài nguyên khi khởi động thất bại.
10. Viết test xác nhận thứ tự `before → close từ helper → after` thay vì assert chính xác bao nhiêu JFR events được gửi trong 700 ms.

## 13. Tài liệu chuẩn hiện hành

- [Oracle Java SE 25 – RecordingStream](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): `start`, `startAsync`, `close`, `stop`, `enable` và vòng đời RecordingStream.
- [Oracle Java SE 25 – EventStream](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): callback chạy trên current thread với `start()`, cách đóng, xử lý lỗi, batching và `awaitTermination`.
- [Oracle JFR API Guide – Create Event Stream in Process, Active](https://docs.oracle.com/en/java/javase/25/jfapi/create-event-stream-process-active.html): ví dụ dùng RecordingStream trong JVM và xác nhận `start()` chặn cho đến khi đóng.
- [OpenJDK JEP 349 – JFR Event Streaming](https://openjdk.org/jeps/349): tính năng chính thức được đưa vào từ Java 14.
- [Oracle Java 17 – RecordingStream API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): API có thể dùng khi biên dịch ví dụ với `--release 17`.

**Ghi nhớ:** `RecordingStream.start()` không phải “bắt đầu rồi quay lại” — nó **chiếm luồng gọi để xử lý JFR event** và chỉ trả về khi streaming kết thúc. Hãy cấu hình events và handlers trước, **thiết kế cách dừng trước khi chặn**, rồi chọn `start()` hoặc `startAsync()` theo nhu cầu quản lý luồng và vòng đời ứng dụng.