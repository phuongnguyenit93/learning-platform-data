# Đăng ký `onEvent` cho một loại hoặc mọi sự kiện bằng `RecordingStream`

## 1. Bối cảnh: nhận sự kiện JFR của JVM đang chạy

**Java Flight Recorder (JFR)** là cơ chế thu thập các sự kiện của JVM và ứng dụng để quan sát hoạt động runtime. `jdk.jfr.consumer.RecordingStream` cung cấp một luồng sự kiện được ghi từ **JVM hiện tại**, cho phép đăng ký hàm xử lý (callback) rồi nhận sự kiện khi stream chạy.

Hai overload cần nắm vững:

~~~java
void onEvent(String eventName, Consumer<RecordedEvent> action);
void onEvent(Consumer<RecordedEvent> action);
~~~

Cả hai thuộc giao diện `jdk.jfr.consumer.EventStream` và được `RecordingStream` triển khai.

- **Theo tên loại sự kiện:** `stream.onEvent("jdk.GarbageCollection", event -> { ... })` chỉ gọi callback đó đối với các `RecordedEvent` có **tên loại sự kiện** phù hợp với `"jdk.GarbageCollection"`.
- **Cho mọi sự kiện trong stream:** `stream.onEvent(event -> { ... })` gọi callback cho **mọi sự kiện được stream phân phối**. “Mọi” ở đây nghĩa là mọi **sự kiện đã được ghi, khả dụng và tới luồng này**, **không phải** mọi loại sự kiện có thể tồn tại trong JVM hay mọi thao tác của ứng dụng.
- Có thể đăng ký **cả hai overload trên cùng stream**. Một event trùng tên có thể được chuyển tới **cả callback theo tên và callback tổng quát**. Hai callback là hai đăng ký độc lập.

Để nhận được sự kiện, **đăng ký callback chưa đủ**. Sự kiện cần được **bật ghi** hoặc được bật bởi cấu hình, phải thực sự xảy ra và được ghi, và stream phải được khởi động.

Ví dụ cấu trúc tiêu chuẩn:

~~~java
try (var stream = new RecordingStream()) {
    stream.enable("jdk.GarbageCollection");
    stream.onEvent("jdk.GarbageCollection", event -> {
        System.out.println(event.getEventType().getName());
    });
    stream.startAsync();
    // Các thao tác ứng dụng diễn ra trong khi stream còn hoạt động.
}
~~~

Đoạn này **minh họa cấu trúc**, không bảo đảm phát sinh một GC trong khoảng sống của stream; nếu ứng dụng không có GC được ghi thì callback có thể không chạy. Trong hai chương trình đầy đủ bên dưới, bài dùng **sự kiện JFR tự định nghĩa** và đồng bộ bằng `CountDownLatch` để kiểm tra kết quả một cách rõ ràng.

**Phiên bản:** `RecordingStream` và `EventStream.onEvent(...)` có từ **Java 14** và vẫn được hỗ trợ ở Java 17, 21, 26 và các bản JDK hiện đại. Ví dụ biên dịch bằng **`javac --release 17`**; không sử dụng API đã lỗi thời hoặc cú pháp preview.

## 2. Phân biệt hai overload `onEvent`

| Mục tiêu | Cú pháp | Khi nào callback chạy? |
| --- | --- | --- |
| Theo dõi một tên loại JFR | `onEvent("lesson.Payment", handler)` | Khi sự kiện được phân phối có tên loại **`lesson.Payment`** |
| Nhận tất cả các sự kiện đã được stream phân phối | `onEvent(handler)` | Mỗi sự kiện mà stream cung cấp, thuộc bất kỳ tên loại nào được ghi |
| Theo dõi vài loại đã biết | Gọi `onEvent(name, handler)` nhiều lần với từng tên | Mỗi callback chỉ nhận loại đã đăng ký |
| Quan sát tổng quát và tự phân loại | `onEvent(event -> { String n = event.getEventType().getName(); ... })` | Callback nhận tất cả, tự chọn xử lý theo tên |

**Tên sự kiện** là `event.getEventType().getName()`, không nhất thiết trùng với tên class đơn giản `Payment`. Với class sự kiện có annotation:

~~~java
@jdk.jfr.Name("lesson.Payment")
static class Payment extends jdk.jfr.Event {
    long amount;
}
~~~

tên loại JFR là **`lesson.Payment`**; do đó đăng ký:

~~~java
stream.onEvent("lesson.Payment", event -> {
    long value = event.getLong("amount");
    System.out.println(value);
});
~~~

Hai đoạn là **mã minh họa đặt trong class/phương thức thích hợp**, không phải file chạy độc lập. Nếu viết `onEvent("Payment", ...)` thì không khớp với tên sự kiện đã công bố trong `@Name`. Với các sự kiện built-in của JDK, tên thường có dạng `jdk.CPULoad`, `jdk.GarbageCollection` hoặc `jdk.ThreadSleep`.

Nếu muốn **chỉ nhận một hoặc vài loại**, Javadoc khuyến nghị cân nhắc overload theo tên thay vì cho callback tổng quát nhận mọi sự kiện rồi tự lọc, vì lọc theo tên của stream thường hiệu quả hơn khi khối lượng sự kiện lớn.

## 3. `enable(...)` khác hoàn toàn `onEvent(...)`

Đây là điểm quan trọng nhất khi không thấy callback được gọi:

- **`stream.enable("lesson.Payment")`** hoặc **`stream.enable(Payment.class)`**: cấu hình cho **loại sự kiện được phép ghi**. Nó không gắn một handler và không tự làm phát sinh event.
- **`stream.onEvent("lesson.Payment", handler)`**: đăng ký hành động chỉ cho **event cùng tên** mà stream nhận. Nó **không tự bật** việc ghi loại event đó.
- **`stream.onEvent(handler)`**: đăng ký hành động chung cho các event đã tới stream; không mặc nhiên bật toàn bộ danh sách các loại JFR trong JVM.
- **`stream.start()`** hoặc **`stream.startAsync()`**: bắt đầu việc ghi/tiêu thụ và phân phối sự kiện tới các callback đã đăng ký.
- **Event thực sự được ghi**: một JFR custom event cần được tạo và gọi `commit()` (hoặc sự kiện built-in thực sự xảy ra); các cài đặt threshold, period và enabled có thể khiến một số event không có trong luồng.

Ví dụ về chuỗi thao tác:

~~~text
1. Khởi tạo RecordingStream
2. Bật loại event cần theo dõi bằng enable(...)
3. Đăng ký onEvent("tên", handler) hoặc onEvent(handler)
4. Gọi startAsync() / start()
5. JVM hoặc ứng dụng ghi event có loại đang được bật
6. Stream đọc event và chạy callback phù hợp
7. Đóng stream bằng close() / try-with-resources
~~~

Đừng nhầm hai bộ lọc:

| Cơ chế | Ảnh hưởng |
| --- | --- |
| `enable/disable` và các `EventSettings` | Loại event nào có thể được **ghi** trong recording |
| `onEvent("name", ...)` | Callback nào được **gọi** đối với event đã xuất hiện |
| `onEvent(event -> if (...) ...)` | Nhận mọi event rồi **tự lọc trong callback** |

Nếu một sự kiện đã bị vô hiệu hóa hoặc không được ghi do threshold, việc thêm `onEvent("name", ...)` không “cứu” được sự kiện đó. Ngược lại, một event có thể vẫn được ghi trong stream khi bạn chỉ đăng ký callback theo tên của một event khác.

### Bật theo class hoặc theo chuỗi tên?

`stream.enable(Payment.class)` thuận tiện khi code có class `Payment extends Event`. `stream.enable("lesson.Payment")` thuận tiện khi chỉ biết tên sự kiện, ví dụ theo dõi sự kiện built-in. Để tránh nhầm tên, có thể dùng `Payment.class` khi bật và dùng tên do `@Name` quy định khi đăng ký handler.

Với event xảy ra rất nhanh trong ví dụ, `stream.enable(Payment.class).withoutThreshold()` làm rõ rằng sự kiện **không bị loại chỉ vì duration ngắn hơn threshold**. Trong ứng dụng thật, threshold là một công cụ giảm dữ liệu và overhead hữu ích; không nên tự động tắt threshold trên mọi event khi theo dõi production.

## 4. Chương trình chạy được: một stream, hai loại event, cả callback theo tên và tổng quát

Tạo file **`RecordingStreamOnEventDemo.java`**:

~~~java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class RecordingStreamOnEventDemo {
    @Name("lesson.Payment")
    static class Payment extends Event {
        long amount;
    }

    @Name("lesson.Audit")
    static class Audit extends Event {
        String action;
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger namedPayment = new AtomicInteger();
        AtomicInteger allPayment = new AtomicInteger();
        AtomicInteger allAudit = new AtomicInteger();
        AtomicReference<Throwable> callbackError = new AtomicReference<>();
        CountDownLatch callbacks = new CountDownLatch(3);

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable(Payment.class).withoutThreshold();
            stream.enable(Audit.class).withoutThreshold();

            stream.onEvent("lesson.Payment", event -> {
                if (event.getLong("amount") != 450L) {
                    throw new AssertionError("Wrong amount");
                }
                namedPayment.incrementAndGet();
                callbacks.countDown();
            });

            stream.onEvent(event -> {
                String name = event.getEventType().getName();
                if (name.equals("lesson.Payment")) {
                    allPayment.incrementAndGet();
                    callbacks.countDown();
                } else if (name.equals("lesson.Audit")) {
                    allAudit.incrementAndGet();
                    callbacks.countDown();
                }
            });
            stream.onError(callbackError::set);
            stream.startAsync();

            Payment payment = new Payment();
            payment.amount = 450L;
            payment.commit();

            Audit audit = new Audit();
            audit.action = "created";
            audit.commit();

            if (!callbacks.await(12, TimeUnit.SECONDS)) {
                throw new AssertionError("Timed out waiting for events");
            }
            if (callbackError.get() != null) {
                throw new AssertionError("Callback failed", callbackError.get());
            }
            System.out.println("namedPayment=" + namedPayment.get());
            System.out.println("allPayment=" + allPayment.get());
            System.out.println("allAudit=" + allAudit.get());
            System.out.println("bothCallbacksForPayment="
                    + (namedPayment.get() == 1 && allPayment.get() == 1));
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ có hỗ trợ module `jdk.jfr`:

~~~bash
javac --release 17 -encoding UTF-8 RecordingStreamOnEventDemo.java
java RecordingStreamOnEventDemo
~~~

**Stdout trong lần kiểm thử thực tế:**

~~~text
namedPayment=1
allPayment=1
allAudit=1
bothCallbacksForPayment=true
~~~

### Phân tích từng mốc

1. Hai class mở rộng `jdk.jfr.Event` định nghĩa **hai loại riêng**: `lesson.Payment` và `lesson.Audit`. `@Name` là tên loại JFR được dùng khi lọc và truy vấn metadata.
2. Hai lần gọi `enable(Class)` cho phép ghi cả hai loại. `withoutThreshold()` giúp sự kiện ngắn vẫn có thể ghi.
3. Callback theo tên chỉ có:
   `stream.onEvent("lesson.Payment", ...)`.
   Nó chỉ được gọi cho Payment; truy cập field `amount` qua `RecordedEvent.getLong("amount")`.
4. Callback tổng quát:
   `stream.onEvent(event -> { ... })`.
   Nó được gọi cho các sự kiện stream phân phối, có thể bao gồm cả những sự kiện built-in khác. Ví dụ **chỉ đếm hai tên custom** bằng `event.getEventType().getName()` để stdout ổn định.
5. Sự kiện Payment kích hoạt **hai callback**: một callback theo tên và một callback tổng quát. Sự kiện Audit chỉ đi vào callback tổng quát trong hai handler do ta đăng ký. Vì thế có ba lần giảm bộ đếm `CountDownLatch(3)`.
6. `CountDownLatch.await(12, TimeUnit.SECONDS)` cho callback bất đồng bộ cơ hội chạy và từ chối test nếu không nhận đủ trong thời gian chờ. Đây là **giới hạn chờ của ví dụ**, không phải cam kết mọi JVM và tải hệ thống luôn phát sự kiện trong 12 giây.
7. `AtomicInteger` và `AtomicReference` được dùng vì callback xử lý trên thread khác với `main` khi gọi `startAsync()`. Không dựa vào biến `int` thường bị cập nhật đồng thời mà thiếu đồng bộ.
8. `try-with-resources` đảm bảo gọi `close()` khi rời khối, kể cả có lỗi. Test chỉ in kết quả sau khi đã nhận đủ callback; không dùng `Thread.sleep(...)` như một bảo đảm rằng event chắc chắn đã được nhận.

**Không suy ra** mọi event đều đi tới cả hai callback. Chỉ event khớp tên `lesson.Payment` mới vào callback riêng theo tên; callback tổng quát là luồng riêng cho mọi sự kiện mà stream cung cấp.

**Giới hạn chạy:** chương trình cần JVM có JFR hoạt động và có thể tạo repository. Khi môi trường không hỗ trợ hoặc không cho phép truy cập Flight Recorder, khởi tạo `RecordingStream` có thể thất bại. Điều này là giới hạn môi trường, không phải sai cú pháp.

## 5. Chương trình thứ hai: chỉ đăng ký một loại event, dù loại khác vẫn được ghi

Ví dụ này chứng minh **chọn callback không đồng nghĩa tắt ghi loại khác**. Chúng ta bật cả hai loại, nhưng chỉ đăng ký một callback theo tên cho `lesson.Sensor`.

Tạo file **`RecordingStreamNamedOnlyDemo.java`**:

~~~java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class RecordingStreamNamedOnlyDemo {
    @Name("lesson.Sensor")
    static class Sensor extends Event {
        int temperature;
    }

    @Name("lesson.Debug")
    static class DebugEvent extends Event {
        String detail;
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger selected = new AtomicInteger();
        AtomicInteger lastTemperature = new AtomicInteger();
        CountDownLatch delivered = new CountDownLatch(1);

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable(Sensor.class).withoutThreshold();
            stream.enable(DebugEvent.class).withoutThreshold();

            stream.onEvent("lesson.Sensor", event -> {
                lastTemperature.set(event.getInt("temperature"));
                selected.incrementAndGet();
                delivered.countDown();
            });

            stream.startAsync();

            DebugEvent debug = new DebugEvent();
            debug.detail = "ignored";
            debug.commit();

            Sensor sensor = new Sensor();
            sensor.temperature = 24;
            sensor.commit();

            if (!delivered.await(12, TimeUnit.SECONDS)) {
                throw new AssertionError("Sensor event not received");
            }
            System.out.println("selectedCount=" + selected.get());
            System.out.println("lastTemperature=" + lastTemperature.get());
            System.out.println("namedOnly=true");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 RecordingStreamNamedOnlyDemo.java
java RecordingStreamNamedOnlyDemo
~~~

Stdout đã kiểm tra:

~~~text
selectedCount=1
lastTemperature=24
namedOnly=true
~~~

Trong ví dụ:

- `lesson.Sensor` và `lesson.Debug` đều được bật bằng `enable(Class)`, và ta chủ động gọi `commit()` cho một event của mỗi loại.
- Không có `onEvent("lesson.Debug", ...)` hay callback tổng quát, vì vậy code **không xử lý Debug**. Event Debug không kích hoạt callback dành cho Sensor.
- `lastTemperature=24` được lấy từ **RecordedEvent** trong callback sau khi đọc `getInt("temperature")`, không phải trực tiếp đọc field của object `sensor` trong main.
- Chỉ một callback được đăng ký, nên `selectedCount=1` trong lần chạy kiểm thử.
- Dòng `namedOnly=true` là nhãn do chương trình in để minh họa trường hợp chỉ có callback theo tên; không phải một property tự động của `RecordingStream`.

Nếu muốn ngừng **ghi** event Debug, phải dùng `disable(DebugEvent.class)` hoặc không bật event đó tùy cấu hình áp dụng; việc không đăng ký callback chỉ quyết định **ai xử lý** event.

## 6. Callback tổng quát: đọc tên loại và lọc có chủ đích

Overload:

~~~java
stream.onEvent(event -> {
    String name = event.getEventType().getName();
    System.out.println("type=" + name);
});
~~~

đăng ký một callback cho **mọi `RecordedEvent` trong stream**. Đây là đoạn minh họa bên trong code có biến `stream`, không phải chương trình độc lập.

Khi khối lượng sự kiện lớn, in toàn bộ event vào console có thể tạo overhead đáng kể; mỗi sự kiện còn có metadata và fields khác nhau, nên không được giả định tất cả đều có field `"amount"` hay `"temperature"`.

Cách phân loại:

~~~java
stream.onEvent(event -> {
    String type = event.getEventType().getName();

    if (type.equals("lesson.Payment")) {
        long amount = event.getLong("amount");
        processPaymentAmount(amount);
    } else if (type.equals("lesson.Audit")) {
        String operation = event.getString("action");
        processAuditAction(operation);
    }
});
~~~

Đây là **mã minh họa**, với `processPaymentAmount` và `processAuditAction` là các hàm nghiệp vụ chưa định nghĩa. Nó diễn giải ý tưởng đọc metadata trước khi truy cập field đặc thù.

**Nên chọn overload nào?**

- Nếu chỉ cần một vài loại đã biết: **`onEvent(name, action)`** thường đơn giản và tránh để callback xử lý mỗi event không liên quan. Có thể đăng ký nhiều lần cho các tên khác nhau.
- Nếu cần đếm thống kê **tất cả event được ghi**, thử nghiệm khám phá loại event hoặc viết collector chung: **`onEvent(action)`** thích hợp. Khi dùng để phân loại, tránh làm việc nặng trong callback.
- Nếu cần **cả metric chung và xử lý đặc thù**: có thể dùng **cả hai**, nhưng phải hiểu một event có thể kích hoạt hai đoạn xử lý độc lập, dễ dẫn đến **đếm trùng** nếu bạn cộng chung kết quả của cả hai handler.

Với dữ liệu trong callback, `event.getEventType().getName()` là cách xác định tên loại trực tiếp. Các getter như `getInt("temperature")`, `getLong("amount")` hoặc `getString("action")` yêu cầu field tương ứng thật sự tồn tại và có kiểu phù hợp; nếu thiếu hoặc sai kiểu, chương trình có thể ném exception.

## 7. Thời điểm đăng ký, khởi động và dừng luồng

### `start()` và `startAsync()`

- `stream.start()` chạy xử lý các callback trong **thread đang gọi**, và thường **chặn** cho đến khi stream kết thúc. Nếu gọi từ main mà không có cơ chế đóng stream phù hợp, chương trình có thể tiếp tục chờ sự kiện.
- `stream.startAsync()` tạo luồng xử lý **bất đồng bộ**. Các callback được thực thi trên một thread xử lý riêng, nên code sau `startAsync()` có thể tiếp tục tạo event.
- Thực hành rõ ràng: **bật event và đăng ký callback trước khi start**, rồi sau đó tạo hoặc chờ sự kiện. Điều này tránh phải suy luận về event đã xảy ra trước khi handler sẵn sàng.
- `close()` đóng và giải phóng tài nguyên stream. Dùng `try (RecordingStream stream = ...) { ... }` để không bỏ sót việc đóng khi có exception.
- `RecordingStream.stop()` là API khác `close()` và có hành vi chờ các event đang ghi được tiêu thụ theo tài liệu; **không nên gọi `stop()` ngay trong callback `onEvent`**, vì nó có thể chặn không kết thúc khi thread xử lý tự chờ chính nó. Nếu cần kết thúc từ callback, xem cách sử dụng `close()` hoặc báo tín hiệu cho thread điều khiển.

### Không kỳ vọng callback xảy ra ngay tức thì

JFR chuyển sự kiện theo **batches**. Có thể có độ trễ giữa `commit()` và việc callback được gọi. Không nên viết:

~~~java
stream.startAsync();
event.commit();
System.out.println(counter.get()); // không bảo đảm đã tăng
~~~

Đây là **mã minh họa chứa các biến giả định** và cố ý trình bày lỗi kiểm thử bất đồng bộ. Ngay sau `commit()`, thread xử lý JFR có thể chưa nhận batch.

Cách đáng tin hơn cho test là dùng `CountDownLatch` hoặc một cơ chế đồng bộ tương đương có **timeout**, như hai chương trình hoàn chỉnh. Đừng dựa vào `Thread.sleep(100)` như tiêu chuẩn chắc chắn event được giao đúng hạn; nó tạo test không ổn định khi máy chậm hoặc tải cao.

### `onError` và ngoại lệ trong callback

`stream.onError(action)` đăng ký một hành động nếu lỗi không mong đợi xảy ra trong callback. Khi không có handler, runtime có thể in stack trace vào stderr. Khi đang học hoặc xây môi trường thử nghiệm, nên xử lý lỗi callback theo cách có thể quan sát, ví dụ lưu vào `AtomicReference<Throwable>` hoặc log. Không tự cho rằng exception ném trong callback async sẽ xuất hiện nguyên vẹn trong thread main.

**Lưu ý:** nếu callback ném exception trước khi giảm `CountDownLatch`, test có thể timeout; do đó báo lỗi callback rõ ràng giúp tìm nguyên nhân thay vì chỉ nhìn thấy timeout.

## 8. `RecordedEvent` là dữ liệu stream, không phải object `Event` ban đầu

Hai lớp thường dễ nhầm:

| Loại | Dùng ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `jdk.jfr.Event` | Ứng dụng định nghĩa/custom event | Tạo event, điền field, gọi `commit()` để ghi |
| `jdk.jfr.consumer.RecordedEvent` | Callback `onEvent(...)` | Bản ghi đã được tiêu thụ, đọc metadata và các field qua getter |
| `jdk.jfr.EventType` | `event.getEventType()` | Metadata của **loại** event, bao gồm tên |
| `Consumer<RecordedEvent>` | Tham số `onEvent` | Hàm xử lý cho từng event được phân phối |

Ví dụ: `Payment payment = new Payment(); payment.amount = 450; payment.commit();` ở phía tạo event; handler nhận `RecordedEvent event` và dùng `event.getLong("amount")` ở phía tiêu thụ.

Một chi tiết quan trọng của `EventStream`: khi cho phép **tái sử dụng RecordedEvent** (`setReuse(true)`), đối tượng event có thể bị dùng lại trong những lần dispatch tiếp theo. Khi đó, không giữ tham chiếu `RecordedEvent` sau khi callback hoàn tất. Trong chương trình minh họa, handler đọc tên và giá trị primitive **ngay bên trong callback**, rồi ghi chúng vào `AtomicInteger`; đây là cách tránh phải giữ reference của event. Nếu thật sự cần giữ `RecordedEvent` để xử lý sau callback, hãy cân nhắc `setReuse(false)`, nhu cầu bộ nhớ, và bảo đảm thread safety phù hợp.

## 9. Đăng ký nhiều handler, bỏ đăng ký và hiệu năng

Có thể gọi `onEvent` nhiều lần; mỗi lần là một đăng ký mới. Ví dụ:

~~~java
java.util.function.Consumer<jdk.jfr.consumer.RecordedEvent> handler =
        event -> System.out.println(event.getEventType().getName());

stream.onEvent("lesson.Payment", handler);
stream.onEvent(handler);
~~~

Đây là mã minh họa nằm trong scope có biến `stream`. Nếu một Payment được ghi và phân phối, **hai đăng ký** trên có thể gọi cùng handler hai lần. Đó là hành vi đăng ký, không phải JVM tự nhân đôi event.

Muốn bỏ callback, `EventStream.remove(Object action)` có thể hủy đăng ký hành động tương ứng. Để làm được điều đó, hãy **giữ tham chiếu đến object handler**:

~~~java
boolean removed = stream.remove(handler);
~~~

Ghi nhớ: `remove(...)` bỏ handler, **không disable việc ghi loại JFR**. Nếu đã đăng ký cùng action object nhiều lần, `remove` bỏ tất cả các đăng ký của action đó theo tài liệu API. Cần xác định vòng đời handler rõ ràng để tránh đăng ký trùng ngoài ý muốn.

Về hiệu năng và độ tin cậy:

1. **Ưu tiên lọc theo tên từ sớm** nếu chỉ cần một nhóm nhỏ event: `onEvent("name", action)` tránh chạy callback tổng quát cho mọi loại event.
2. **Chỉ enable event cần thiết:** số lượng event được ghi, threshold và metadata có thể tạo chi phí quan sát đáng kể.
3. **Callback nên xử lý nhanh:** nếu phải làm I/O, gọi mạng hoặc tính toán nặng, nên cân nhắc chuyển dữ liệu cần thiết sang một hàng đợi có giới hạn và xử lý ở nơi khác.
4. **Thread safety:** với `startAsync()`, callback không chạy trên thread main; dùng các primitive đồng bộ như `AtomicInteger`, `CountDownLatch` hoặc collections thread-safe khi cần chia sẻ trạng thái.
5. **Không dựa vào thứ tự tương đối của các callback như một sự thật nghiệp vụ:** events được xử lý theo batches, lịch flush có thể ảnh hưởng thời điểm nhận. Khi cần bảo đảm thứ tự hoặc đầy đủ qua giai đoạn đóng stream, phải thiết kế đồng bộ rõ ràng.
6. **Kiểm tra tính khả dụng của JFR:** VM không hỗ trợ JFR, quyền truy cập không đủ hoặc repository không tạo được có thể khiến khởi tạo/thực thi thất bại; cần quản lý lỗi vận hành.

## 10. Các lỗi phổ biến và cách sửa

**Lỗi 1 — Nghĩ `onEvent("jdk.CPULoad", ...)` tự bật CPU Load.**  
Sai. `onEvent` chỉ đăng ký callback; nếu event chưa được bật trong recording, cần `enable("jdk.CPULoad")` hoặc dùng cấu hình đã bật event đó.

**Lỗi 2 — Nghĩ `onEvent(action)` sẽ tự bật toàn bộ sự kiện JVM.**  
Sai. Nó chỉ nhận **mọi event đang được phân phối trong stream**. Số loại được ghi phụ thuộc cấu hình và những sự kiện thật sự phát sinh.

**Lỗi 3 — Dùng tên class đơn giản thay cho tên JFR.**  
Với `@Name("lesson.Payment")`, đăng ký đúng là `onEvent("lesson.Payment", ...)`. Nếu không rõ tên, xem annotation hoặc `event.getEventType().getName()` khi có callback tổng quát.

**Lỗi 4 — Đọc field không có ở mọi loại event.**  
Callback tổng quát có thể nhận `lesson.Payment`, `lesson.Audit` hoặc event built-in. Không gọi `event.getLong("amount")` vô điều kiện cho mọi loại.

**Lỗi 5 — Gọi `onEvent(...)` nhưng không start.**  
Đăng ký thành công không làm handler tự chạy. Phải gọi `start()` hoặc `startAsync()`.

**Lỗi 6 — Commit event trước khi sẵn sàng ghi/nhận.**  
Nếu event xảy ra trước khi stream được cấu hình/start, bạn không thể mặc định event đó xuất hiện trong luồng. Đăng ký và start trước khi tạo event trong ví dụ.

**Lỗi 7 — Test bằng `sleep` ngắn rồi kết luận mất event.**  
JFR dùng batches và việc giao callback bất đồng bộ có thể trễ. Dùng latch/timeout hoặc cơ chế đồng bộ được thiết kế cho stream.

**Lỗi 8 — In/đếm hai lần khi dùng cả hai overload.**  
Một event khớp tên có thể đi qua callback theo tên **và** callback chung. Nếu cả hai cùng tăng một metric, tổng sẽ đếm trùng.

**Lỗi 9 — Giữ trực tiếp `RecordedEvent` ngoài callback trong chế độ reuse.**  
Khi tái sử dụng được bật, nội dung đối tượng có thể đổi sau callback. Hãy sao chép giá trị cần lưu hoặc cấu hình reuse phù hợp.

**Lỗi 10 — Quên đóng stream.**  
Dùng try-with-resources; nếu theo dõi dài hạn, quản lý vòng đời rõ ràng. Không gọi `stop()` từ chính callback rồi khiến stream tự chờ.

## 11. Quy trình lựa chọn overload trong dự án

| Câu hỏi | Quyết định |
| --- | --- |
| Chỉ muốn theo dõi `jdk.GarbageCollection`? | Bật loại đó nếu cần, rồi `onEvent("jdk.GarbageCollection", handler)` |
| Muốn theo dõi `jdk.CPULoad` và `jdk.GarbageCollection` riêng? | Hai callback theo tên, hoặc một callback tổng quát có nhánh lọc nếu có lý do |
| Muốn thống kê mọi loại event stream nhận? | `onEvent(handler)` và đọc `event.getEventType().getName()` |
| Muốn vừa thống kê chung vừa xử lý Payment riêng? | Kết hợp hai overload, chú ý khả năng cùng event kích hoạt cả hai |
| Callback không bao giờ chạy? | Kiểm tra tên event, `enable`, threshold, event có thực sự được commit, stream có start và còn mở, lỗi callback |
| Test callback không ổn định? | Tạo custom events để chủ động commit; dùng latch có timeout, không phụ thuộc sự kiện GC/CPU có xuất hiện |
| Cần giảm overhead? | Enable đúng loại, dùng threshold hợp lý, callback theo tên, xử lý nhanh |
| Cần bỏ một handler? | Giữ tham chiếu `Consumer<RecordedEvent>` rồi `remove(handler)` |

## 12. Câu hỏi luyện tập

**Câu 1.** Khác biệt giữa `onEvent("lesson.A", handler)` và `onEvent(handler)` là gì?  
**Đáp án:** Cái đầu chỉ gọi handler cho các sự kiện có tên loại `lesson.A`; cái sau gọi handler cho mọi event được phân phối trong stream.

**Câu 2.** Chỉ gọi `onEvent("lesson.A", handler)`, chưa bật ghi event A, có đảm bảo callback chạy không?  
**Đáp án:** Không. Cần event được ghi trong recording, thực sự xảy ra và được stream xử lý; có thể phải gọi `enable(...)`.

**Câu 3.** Có thể dùng cả hai overload trên một `RecordingStream` không?  
**Đáp án:** Có. Khi event A khớp tên, nó có thể được chuyển cho cả callback theo tên và callback chung.

**Câu 4.** `onEvent(handler)` nghĩa là tất cả loại JFR trong JVM đều được bật ghi?  
**Đáp án:** Không. “Mọi” giới hạn trong **các event đã được phân phối**, không liên quan đến việc bật ghi các loại khác.

**Câu 5.** Có thể dùng `event.getLong("amount")` trong callback tổng quát cho mọi event không?  
**Đáp án:** Không. Chỉ đọc field sau khi biết loại và schema của event có field đó với kiểu tương ứng.

**Câu 6.** Vì sao kiểm thử `Thread.sleep(100)` sau `commit()` là không đáng tin?  
**Đáp án:** Stream chạy bất đồng bộ, sự kiện tới theo batch; thời điểm dispatch không được bảo đảm trong 100 ms. Nên dùng latch có timeout.

**Câu 7.** Muốn callback nhận các giá trị event sau khi nó kết thúc, cần chú ý điều gì?  
**Đáp án:** Đối tượng `RecordedEvent` có thể được tái sử dụng theo cấu hình; đọc/sao chép các giá trị cần thiết trong callback hoặc cân nhắc `setReuse(false)`.

**Câu 8.** `remove(handler)` có tắt ghi loại event không?  
**Đáp án:** Không. Nó chỉ hủy đăng ký callback; bật/tắt ghi thuộc về `enable/disable` và event settings.

## Nguồn Java chính thức

- Oracle Java SE 17 — `jdk.jfr.consumer.RecordingStream`, hai overload `onEvent`, `enable`, `startAsync` và `close`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html
- Oracle Java SE 17 — `jdk.jfr.consumer.EventStream`, quy tắc callback, `remove`, `setReuse`, `onError` và event batches: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html
- Oracle Java SE 26 — `jdk.jfr.consumer.EventStream` (API hiện đại, các overload `onEvent` vẫn được hỗ trợ): https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html
- Oracle Java SE 17 — `jdk.jfr.Event`, tạo và commit custom event: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Event.html
- Oracle Java SE 17 — `jdk.jfr.consumer.RecordedEvent`, đọc fields và metadata: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html
- Oracle Java Flight Recorder API Programmer's Guide — RecordingStream và hành động `onEvent`: https://docs.oracle.com/en/java/javase/17/jfapi/