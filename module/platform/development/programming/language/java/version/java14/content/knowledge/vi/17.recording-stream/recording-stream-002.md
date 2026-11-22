# RecordingStream: bật hoặc tắt sự kiện JFR theo tên và theo lớp (Java 14+)

## 1. Bài toán: chỉ nhận những JFR event thực sự cần thiết

**Java Flight Recorder (JFR)** là cơ chế quan sát hoạt động JVM bằng các **sự kiện (events)**. Sự kiện có thể phản ánh thu gom rác, hoạt động CPU, truy cập tệp, giao tiếp mạng hoặc thao tác nghiệp vụ do ứng dụng tự phát ra. Với `jdk.jfr.consumer.RecordingStream`, ứng dụng Java có thể **đăng ký xử lý các sự kiện được ghi trong chính JVM đang chạy** mà không cần tự đọc tệp `.jfr` sau khi chương trình kết thúc.

Trong thực tế, ta thường chỉ muốn quan sát một số loại sự kiện:

- Khi điều tra hiệu năng: nhận `jdk.CPULoad` với chu kỳ cụ thể.
- Khi điều tra tác động bộ nhớ: nhận `jdk.GarbageCollection`.
- Khi theo dõi một hoạt động riêng: phát sự kiện tùy chỉnh `demo.OrderChecked`.
- Khi không còn cần một loại sự kiện: **tắt việc ghi loại đó trong stream** để tránh ghi nhận thêm dữ liệu không hữu ích.

`RecordingStream` cung cấp **bốn overload** chính cho nhu cầu này:

```java
EventSettings enable(String name);
EventSettings enable(Class<? extends Event> eventClass);

EventSettings disable(String name);
EventSettings disable(Class<? extends Event> eventClass);
```

Đây là **chữ ký API rút gọn để giải thích**, không phải một class Java độc lập. Các phương thức đều thuộc `RecordingStream`; `Event` và `EventSettings` thuộc `jdk.jfr`.

**Mục tiêu bài học:** chọn chính xác giữa **tên sự kiện (`String`)** và **lớp sự kiện (`Class<? extends Event>`)**, hiểu việc bật/tắt trong phạm vi stream, phối hợp với `onEvent`/`startAsync`, kiểm thử được một sự kiện thực tế, và tránh những kết luận sai về event bị buffer hoặc lớp trùng tên.

### Phiên bản và tính ứng dụng hiện nay

`RecordingStream` có mặt từ **Java 14** và vẫn được hỗ trợ trong các JDK hiện đại. Cách sử dụng trong bài là **API chính thức**, không phải một preview feature. Các ví dụ có thể biên dịch bằng **Java 17+**; không cần `--enable-preview`. API thuộc **module `jdk.jfr`**, không phải một phần của `java.base`. Chạy trên một bản phân phối JDK/JVM **có hỗ trợ JFR**; nếu runtime không có JFR hoặc không tạo được JFR repository, constructor có thể ném `IllegalStateException`.

## 2. Hiểu ba khâu riêng: cấu hình ghi, phát sự kiện và nhận callback

Một sự kiện tùy chỉnh có thể được phát bằng `Event.commit()`, nhưng không có nghĩa mọi `RecordingStream` sẽ nhận nó. Đường đi tư duy là:

```text
Code phát event (Event.commit)
          |
          v
JFR runtime kiểm tra các recording/event settings đang có
          |
          +--- loại event không được ghi / không đạt threshold
          |        -> không có sự kiện ghi lại cho stream này
          |
          +--- event được ghi lại
                   |
                   v
         RecordingStream đọc các event đã được ghi
                   |
                   v
         onEvent(...) chọn callback có tên phù hợp
                   |
                   v
            Consumer<RecordedEvent>
```

**Bật/tắt và đăng ký callback là hai việc khác nhau**:

- `stream.enable(...)`: cấu hình để một loại JFR event **được ghi** cho recording do stream quản lý.
- `stream.disable(...)`: cấu hình để loại event **không còn được ghi** cho recording đó.
- `stream.onEvent(name, handler)`: đăng ký **hành động xử lý** khi stream đọc được một event có tên khớp.
- `stream.start()` hoặc `stream.startAsync()`: bắt đầu **tiêu thụ** các event từ recording.
- `stream.close()`: giải phóng tài nguyên; dùng `try-with-resources` để đóng ngay cả khi phát sinh ngoại lệ.

Chỉ gọi `enable` **không tự in sự kiện**; chỉ gọi `onEvent` **không tự bật sự kiện bị vô hiệu hóa**. Một ví dụ muốn vừa phát vừa quan sát event tùy chỉnh cần cả **enable**, **onEvent**, **start** và code **commit event**.

## 3. Bật/tắt theo tên: `enable(String)` và `disable(String)`

Một số event tích hợp sẵn của JVM có tên như:

- `jdk.CPULoad`: sự kiện CPU Load.
- `jdk.GarbageCollection`: sự kiện GC.
- `jdk.FileRead`, `jdk.FileWrite`: hoạt động I/O liên quan.

Dùng tên nếu code chỉ biết event dưới dạng chuỗi, nhất là các **event tích hợp sẵn của JDK** hoặc hệ thống cấu hình theo danh sách tên.

```java
// Snippet nằm trong try (RecordingStream stream = new RecordingStream()).
stream.enable("jdk.GarbageCollection");
stream.enable("jdk.CPULoad")
      .withPeriod(java.time.Duration.ofSeconds(1));

stream.onEvent("jdk.CPULoad", event -> {
    System.out.println(event.getEventType().getName());
});

stream.startAsync();
// ... ứng dụng thực hiện công việc ...
// Khi không muốn ghi thêm CPULoad cho recording này:
stream.disable("jdk.CPULoad");
```

Đoạn này **không phải chương trình độc lập** và không hứa in được sự kiện trong một khoảng thời gian cố định; JVM cần tạo event, stream cần hoạt động và consumer cần nhận được sự kiện. Việc thay đổi cấu hình sau `startAsync()` có thể cần thời gian để có hiệu lực; sự kiện đã commit hoặc nằm trong buffer trước đó vẫn có thể tới callback sau khi gọi `disable`.

### Tên của event đến từ đâu?

Đối với event tùy chỉnh:

```java
import jdk.jfr.Event;
import jdk.jfr.Name;

@Name("demo.OrderChecked")
class OrderChecked extends Event {
    public String orderId;
}
```

Annotation `@Name` khai báo tên sự kiện **`demo.OrderChecked`**. Nếu không cung cấp `@Name`, JFR có cơ chế xác định tên từ lớp, nhưng **nên đặt tên ổn định rõ ràng** khi dùng tên làm hợp đồng trong config, dashboard hoặc handler.

Có thể truy vấn tên thực thay vì đoán:

```java
String eventName = jdk.jfr.EventType
        .getEventType(OrderChecked.class).getName();
```

Ví dụ trên là snippet cần đặt sau khi khai báo `OrderChecked`. Nó giúp tránh sai chính tả hoặc sai tên khi class được đổi package.

### Điểm tinh tế: tên có thể không chỉ một lớp

Theo hợp đồng API, nếu **nhiều event có cùng tên**, chẳng hạn các lớp được nạp bởi **những class loader khác nhau**, `enable(String name)` và `disable(String name)` áp dụng cho **mọi event type có tên khớp** trong phạm vi recording liên quan. Do đó:

- `enable("demo.OrderChecked")` có thể bật nhiều event type trùng tên.
- `disable("demo.OrderChecked")` có thể tắt nhiều event type trùng tên.
- Nếu phải phân biệt chính xác một **lớp JFR event cụ thể**, ưu tiên overload nhận `Class`.
- API còn chấp nhận **chuỗi biểu diễn event type ID** để nhắm một event type cụ thể khi chỉ có định danh đó; không nên nhầm type ID với một cái tên đẹp dành cho con người.

Đây là lý do **bật/tắt theo tên** rất tiện cho quan sát JDK event, nhưng có thể rộng hơn mong muốn trong hệ thống plugin/class-loader phức tạp.

## 4. Bật/tắt theo lớp: `enable(Class)` và `disable(Class)`

Khi ứng dụng đã có một lớp kế thừa `jdk.jfr.Event`, dùng `Class` sẽ làm cấu hình rõ ràng và an toàn về kiểu:

```java
// Snippet trong try-with-resources có biến stream.
stream.enable(OrderChecked.class).withoutThreshold();

// ... cần ngừng ghi sự kiện của lớp này ...
stream.disable(OrderChecked.class);

// ... bật lại nếu cần theo dõi tiếp ...
stream.enable(OrderChecked.class).withoutThreshold();
```

Các điểm cần nhớ:

1. Tham số có kiểu `Class<? extends Event>`: compiler giúp bảo đảm loại truyền vào liên quan tới `Event`, không phải bất kỳ class thông thường nào.
2. `enable(Class)` / `disable(Class)` nhắm **lớp event cụ thể**, không phải toàn bộ các lớp tình cờ mang cùng `@Name`.
3. Class truyền vào phải là lớp event hợp lệ, **không trừu tượng**. API có thể ném `IllegalArgumentException` nếu đưa lớp trừu tượng hoặc lớp không kế thừa `Event` qua mã dùng raw type/unchecked.
4. `null` không hợp lệ. Nếu class/tên đến từ config hay reflection, xác minh đầu vào trước khi truyền cho API.
5. Đây là việc bật/tắt **một loại sự kiện** cho stream, không phải `close()` hoặc tắt toàn bộ JFR trong JVM.

### Khi nào chọn tên, khi nào chọn lớp?

| Tiêu chí | `enable/disable(String)` | `enable/disable(Class<? extends Event>)` |
| --- | --- | --- |
| Biết event qua cấu hình văn bản | Rất phù hợp | Cần resolve class |
| Sự kiện tích hợp như `jdk.CPULoad` | Thông thường dùng tên | Thường không có lớp `Event` công khai để truyền vào |
| Sự kiện tùy chỉnh do ứng dụng định nghĩa | Có thể dùng tên `@Name` | Phù hợp khi có reference tới lớp |
| Có nhiều event cùng tên từ class loaders khác nhau | Có thể cùng bị ảnh hưởng | Nhắm chính xác lớp đã truyền |
| Lỗi chính tả trong tên | Có thể làm config không nhắm event dự tính | Compiler kiểm tra reference lớp |
| Kết hợp `EventSettings` | Có | Có |
| Tự nhận callback | Không | Không; vẫn cần `onEvent` và start |

**Điểm chung:** cả hai overload là **API cấu hình của RecordingStream**, không phải công tắc chung cho tất cả recordings và không thay thế callback đăng ký nhận event.

## 5. Cả bật và tắt đều trả `EventSettings`

Chữ ký phương thức không phải `void` hoặc `boolean`; cả bốn overload đều trả **`jdk.jfr.EventSettings`**. Object này cho phép **tiếp tục đặt setting** cho loại event, ví dụ:

```java
stream.enable("jdk.CPULoad")
      .withPeriod(java.time.Duration.ofSeconds(1));

stream.enable(OrderChecked.class)
      .withoutThreshold()
      .withoutStackTrace();
```

Với `withPeriod`, chọn khoảng thời gian cho **loại event có tính chu kỳ** như `jdk.CPULoad`. Với `withoutThreshold`, yêu cầu không dùng ngưỡng thời lượng để loại bỏ event; phù hợp nếu muốn thấy event nghiệp vụ tùy chỉnh rất ngắn. `withoutStackTrace` giảm dữ liệu stack trace khi không cần. Các setting được hỗ trợ và có ý nghĩa cụ thể tùy **loại event**.

**Không được hiểu `EventSettings` trả về là “event đã được nhận”.** Nó là đối tượng cấu hình, không phải `RecordedEvent` và không phải trạng thái thành công/thất bại của một callback.

Ví dụ sai về nhận thức:

```java
// Sai về kỳ vọng kiểu dữ liệu:
// boolean enabled = stream.enable(OrderChecked.class);

// Đúng: nhận object cấu hình.
jdk.jfr.EventSettings settings =
        stream.enable(OrderChecked.class);
```

`disable(...)` cũng trả `EventSettings`, **không trả `false`** khi tắt. Để kiểm chứng event thật sự được stream nhận, cần một consumer như `onEvent` và kiểm tra dòng sự kiện xảy ra trong điều kiện chạy phù hợp.

### Một số setting liên quan

| Cấu hình | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Không dùng ngưỡng thời lượng | `withoutThreshold()` | Không bỏ event chỉ vì ngắn hơn threshold |
| Đặt ngưỡng | `withThreshold(Duration.ofMillis(10))` | Chỉ ghi những event duration đáp ứng ngưỡng theo semantics event |
| Chu kỳ sự kiện | `withPeriod(Duration.ofSeconds(1))` | Áp dụng cho event định kỳ có hỗ trợ period |
| Tắt stack trace | `withoutStackTrace()` | Không lưu stack trace cho event trong setting |
| Bật stack trace | `withStackTrace()` | Đề nghị lưu stack trace, có overhead |
| Setting mở rộng | `with("enabled", "true")` | Dùng cặp tên/giá trị setting theo hợp đồng của JFR |

Chỉ dùng những setting cần thiết và phù hợp loại event. Bật nhiều event tần suất cao hoặc stack trace chi tiết có thể tạo chi phí CPU, bộ nhớ, lưu trữ và xử lý callback.

## 6. Ví dụ hoàn chỉnh Java 17+: chuyển cấu hình theo tên/lớp và nhận một event thật

Để có bài kiểm chứng không phụ thuộc số lượng GC hoặc nhịp phát CPU event của từng máy, ta tạo **event tùy chỉnh** và dùng `CountDownLatch` để đợi callback trong một thời hạn hữu hạn.

Tạo tệp **`JfrEventToggleDemo.java`**:

```java
import jdk.jfr.Event;
import jdk.jfr.EventSettings;
import jdk.jfr.EventType;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class JfrEventToggleDemo {
    @Name("demo.OrderChecked")
    @Label("Order checked")
    public static class OrderChecked extends Event {
        @Label("Order ID")
        public String orderId;
    }

    public static void main(String[] args)
            throws InterruptedException {
        String name = EventType
                .getEventType(OrderChecked.class).getName();

        CountDownLatch received = new CountDownLatch(1);
        AtomicReference<String> observed = new AtomicReference<>();
        AtomicReference<Throwable> error = new AtomicReference<>();

        try (RecordingStream stream = new RecordingStream()) {
            // Hai cách bật/tắt đều trả EventSettings.
            EventSettings byClass = stream.enable(OrderChecked.class)
                    .withoutThreshold();
            EventSettings offByName = stream.disable(name);
            EventSettings byName = stream.enable(name).withoutThreshold();
            EventSettings offByClass = stream.disable(OrderChecked.class);

            // Trạng thái cấu hình cuối cùng: bật lớp event cụ thể.
            stream.enable(OrderChecked.class).withoutThreshold();

            if (byClass == null || offByName == null
                    || byName == null || offByClass == null) {
                throw new AssertionError("Missing EventSettings");
            }

            // Đăng ký xử lý trước khi khởi động stream.
            stream.onEvent(name, event -> {
                if ("ORDER-42".equals(event.getString("orderId"))) {
                    observed.set(event.getString("orderId"));
                    received.countDown();
                }
            });
            stream.onError(error::set);
            stream.startAsync();

            // Chờ JFR truyền được event với giới hạn thời gian.
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(12);
            while (received.getCount() != 0
                    && System.nanoTime() < deadline) {
                OrderChecked event = new OrderChecked();
                event.orderId = "ORDER-42";
                event.commit();
                received.await(300, TimeUnit.MILLISECONDS);
            }

            if (error.get() != null) {
                throw new AssertionError(
                        "Recording stream failed", error.get());
            }
            if (received.getCount() != 0) {
                throw new AssertionError(
                        "Event not observed before timeout");
            }

            System.out.println("eventName=" + name);
            System.out.println("settingsReturned=true");
            System.out.println("received=" + observed.get());
            System.out.println("byClassAndName=true");
        }
    }
}
```

**Biên dịch và chạy** trên một bản JDK 17+ có hỗ trợ JFR:

```bash
javac --release 17 -encoding UTF-8 JfrEventToggleDemo.java
java JfrEventToggleDemo
```

**Kết quả khi chạy đạt trên môi trường kiểm thử có JFR:**

```text
eventName=demo.OrderChecked
settingsReturned=true
received=ORDER-42
byClassAndName=true
```

Chương trình đã được kiểm thử với `javac --release 17` và `java` trong môi trường có JFR. **Đầu ra chỉ có những dòng trên khi các assert thành công**; nếu runtime không hỗ trợ JFR hoặc stream không nhận được event trước timeout, chương trình ném ngoại lệ thay vì giả vờ báo thành công. Thời điểm nhận callback JFR có thể khác nhau giữa máy và môi trường tải cao.

### 6.1. Vì sao đọc tên bằng `EventType`?

`EventType.getEventType(OrderChecked.class).getName()` trả **tên JFR event thực tế** dựa trên `@Name("demo.OrderChecked")`. Đây là cách bảo đảm cùng một `String` được dùng ở:

- `stream.disable(name)`;
- `stream.enable(name)`;
- `stream.onEvent(name, handler)`.

Nếu vô tình gõ `"demo.OrderCheck"` thay vì `"demo.OrderChecked"`, handler sẽ không nhận event như kỳ vọng. Dùng `EventType` hoặc một hằng tên được quản lý tập trung giúp giảm lỗi chính tả.

### 6.2. Trình tự bật/tắt trong ví dụ

Mã lần lượt:

1. `enable(OrderChecked.class)`: bật **theo lớp**.
2. `disable(name)`: tắt **theo tên**.
3. `enable(name)`: bật lại **theo tên**.
4. `disable(OrderChecked.class)`: tắt **theo lớp**.
5. `enable(OrderChecked.class)`: bật lại **theo lớp** để chuẩn bị nhận event.

Tất cả những thao tác trên được thực hiện **trước `startAsync()`**. Mục đích là minh họa rõ từng overload mà không phụ thuộc độ trễ cập nhật cấu hình khi stream đang chạy. **Cấu hình cuối cùng** bật event tùy chỉnh.

Các biến `byClass`, `offByName`, `byName` và `offByClass` đều có kiểu `EventSettings` và không phải `null`. Điều đó xác nhận API trả object cấu hình, **không có nghĩa đã nhận event**.

### 6.3. Tại sao lại có `onEvent` và vòng lặp có giới hạn?

`stream.onEvent(name, handler)` đăng ký callback chỉ cho event có tên `demo.OrderChecked`. Callback đọc trường dữ liệu `orderId` bằng `RecordedEvent.getString("orderId")`, lưu giá trị nhận được và giảm `CountDownLatch`.

`startAsync()` chạy việc xử lý stream trên một thread riêng, để thread `main` có thể tiếp tục tạo và `commit()` sự kiện. Vòng lặp tạo các event cùng `orderId` cho đến khi nhận được một event hoặc hết **12 giây**. Nó không dựa vào việc JFR sẽ flush ngay lập tức sau một lần commit.

`AtomicReference` và `CountDownLatch` giúp truyền kết quả giữa callback thread và main thread an toàn. `onError(error::set)` lưu lỗi phát sinh trong quá trình xử lý stream để main thread kiểm tra.

Khi nhận được một event, chương trình in `received=ORDER-42`. Nó **không khẳng định chỉ có đúng một event được commit**: trong vòng lặp có thể đã commit nhiều event trước khi consumer quan sát được event đầu tiên; đây là điều bình thường với xử lý bất đồng bộ.

### 6.4. Vì sao dùng `try-with-resources`?

`RecordingStream` triển khai `AutoCloseable`. Khối:

```java
try (RecordingStream stream = new RecordingStream()) {
    // enable, onEvent, startAsync, ...
}
```

bảo đảm `close()` được gọi ngay cả khi có `AssertionError`/exception trong thân. Không để stream chạy vô hạn khi chương trình hoặc testcase đã kết thúc.

## 7. Bật/tắt khi stream đang chạy: hiểu đúng tính chất bất đồng bộ

Các ứng dụng giám sát dài hạn có thể cần thay đổi cấu hình trong lúc stream còn hoạt động:

```java
// Snippet minh họa; đặt trong khối đã có RecordingStream stream.
// Giả định đã đăng ký callback và gọi stream.startAsync().
stream.disable(OrderChecked.class);

// ... một thời gian sau, cần quan sát lại event ...
stream.enable(OrderChecked.class).withoutThreshold();
```

Các lời gọi thay đổi **event settings** của stream đang sống. Tuy nhiên, không nên hiểu `disable(...)` như một “van chặn tuyệt đối” khiến mọi callback dừng ngay tại đúng nanosecond gọi hàm:

- **Các event đã được ghi/commit** trước thời điểm vô hiệu hóa có thể vẫn nằm trong buffer và được dispatch về sau.
- Việc cập nhật cấu hình recording, producer và consumer có thể có **độ trễ quan sát**.
- Nếu có **recording khác** trong cùng JVM vẫn bật loại event đó, việc gọi `Event.isEnabled()` trên producer có thể phản ánh trạng thái tổng hợp của JVM chứ không chỉ trạng thái của một `RecordingStream`.
- Nếu muốn kiểm tra “sau disable không nhận event nào”, phải thiết kế kiểm thử đồng bộ và ngữ nghĩa ranh giới thời gian rõ ràng; **không nên chỉ `sleep(100)` rồi assert count không đổi**.

Vì vậy, khi cần **bật/tắt cấu hình chính xác** trong code không phụ thuộc thời gian, thiết lập trước `startAsync()` như ví dụ hoàn chỉnh là lựa chọn dễ kiểm thử. Khi cần bật/tắt động, giám sát theo khoảng thời gian và chấp nhận khả năng có event “đến muộn” do buffer.

## 8. `disable` không phải `remove`, `close` hay `stop`

Những API sau có vai trò khác nhau:

| API | Nó thay đổi điều gì? |
| --- | --- |
| `stream.disable(name)` / `stream.disable(EventClass.class)` | Tắt ghi **loại event** tương ứng cho recording trong stream |
| `stream.onEvent(name, action)` | Đăng ký callback nhận event có tên khớp |
| `stream.remove(action)` | Gỡ bỏ action đã được đăng ký (theo hợp đồng `EventStream`) |
| `stream.close()` | Đóng stream và giải phóng tài nguyên |
| `stream.startAsync()` | Bắt đầu quá trình tiêu thụ event ở thread khác |
| `stream.setSettings(map)` | Thay thế **toàn bộ** map setting của recording bằng cấu hình được cung cấp |

**Ví dụ:** Bạn tắt `demo.OrderChecked` rồi bật lại nhưng không hề đăng ký callback thì stream vẫn không biết phải thực thi hành động gì khi nhận event. Ngược lại, callback có thể còn đăng ký sau khi `disable`, nhưng sẽ không nhận **event mới do stream đó ghi khi event đã tắt**, trừ những dữ liệu đã được ghi/buffer trước thời điểm thay đổi.

`setSettings(Map<String,String>)` là API thay **toàn bộ** settings, không phải “chỉ thêm một event”. Vì thế, nếu gọi nó sau nhiều `enable/disable`, đừng mặc định tất cả cấu hình trước vẫn được giữ nguyên.

**Lưu ý phiên bản:** `RecordingStream` có thêm một số phương thức ở các bản JDK mới hơn, nhưng bài này tập trung API **đã có và dùng được trên Java 17**. Với lifecycle, cách viết `try-with-resources`/`close()` là đủ và nhất quán cho các ví dụ.

## 9. Những vấn đề về event name, class loader, ID và phạm vi JVM

### 9.1. Tên khác `Class.getSimpleName()`

Tên sự kiện JFR không phải chỉ là tên lớp ngắn:

```java
@Name("demo.OrderChecked")
public static class OrderChecked extends Event { /* ... */ }
```

`OrderChecked.class.getSimpleName()` là `OrderChecked`, còn tên JFR là `demo.OrderChecked`. Dùng `EventType.getEventType(OrderChecked.class).getName()` hoặc tên đã khai báo tường minh.

### 9.2. Trùng tên event giữa class loader

Trong hệ thống plugin hoặc tải lớp động, hai lớp `Event` có thể được đăng ký cùng tên. Khi đó:

- `enable(name)` và `disable(name)` chọn **mọi event type có tên đó** theo hợp đồng API.
- `enable(theClass)` và `disable(theClass)` nhắm **lớp xác định**.
- Nếu chỉ có type ID thay vì reference `Class`, API cho phép dùng dạng chuỗi của **event type ID** để nhắm một loại cụ thể.

**Không đánh đồng** “tên đúng” với “chắc chắn chỉ có một lớp”. Khi lựa chọn event type có rủi ro ảnh hưởng nhiều plugin, dùng tham chiếu `Class` hoặc event type ID đáng tin cậy.

### 9.3. RecordingStream chỉ nhận event từ JVM hiện tại

`RecordingStream` theo hợp đồng tạo sự kiện từ **JVM hiện tại**. Nó không tự kết nối tới một JVM khác qua mạng; không nhầm với các giải pháp theo dõi JFR từ xa. Muốn giám sát nhiều process/JVM, cần kiến trúc tương ứng ngoài phạm vi `RecordingStream` cục bộ.

### 9.4. Trạng thái của một stream khác trạng thái “toàn JVM”

Một JVM có thể có nhiều recording. Nếu stream A tắt event, nhưng recording B vẫn bật, producer có thể tiếp tục ghi event cho B. Vì thế `event.isEnabled()` hoặc thống kê JVM không nhất thiết chứng minh **stream A đã bật hay tắt**. Cần kiểm thử trên consumer/recording mình quản lý và hiểu ảnh hưởng của các recording đồng thời.

## 10. Lựa chọn thông số và chi phí khi bật event

Khi bật nhiều JFR event, ta đang yêu cầu hệ thống **ghi thêm dữ liệu** và có thể tiêu thụ thêm tài nguyên. Những cân nhắc thường gặp:

1. **Chỉ bật loại event cần điều tra.** `jdk.CPULoad` theo chu kỳ có thể phù hợp cho biểu đồ tải, nhưng theo dõi mọi `FileRead`/`FileWrite` trong ứng dụng I/O nặng có thể tạo rất nhiều event.
2. **Dùng threshold hợp lý** với event đo thời lượng để bỏ những tác vụ rất ngắn không cần phân tích. `withoutThreshold()` hữu ích cho demo hoặc khi cần thấy mọi event, nhưng có thể tăng số lượng event thực tế.
3. **Cân nhắc stack trace.** `withStackTrace()` giúp tìm nơi phát sinh hành vi nhưng tăng chi phí thu thập và kích thước dữ liệu.
4. **Chọn period cho event định kỳ** khi loại event đó hỗ trợ, tránh đặt period quá dày chỉ vì có thể.
5. **Giới hạn dữ liệu lưu.** Với luồng chạy lâu, xem `setMaxAge(Duration)` và `setMaxSize(long)` để tránh phần dữ liệu trên disk tăng vô hạn.
6. **Tránh xử lý nặng trong callback.** Callback chạy trong tuyến tiêu thụ event; nếu làm I/O, gọi mạng hay phân tích lớn tại đây, tốc độ nhận event có thể bị ảnh hưởng. Có thể đưa dữ liệu sang queue bounded và tiêu thụ riêng, kèm chính sách bỏ tải.
7. **Không log bí mật hoặc PII** trong trường event tùy chỉnh. Event JFR có thể được lưu và xem bằng công cụ chẩn đoán khác, nên cần cân nhắc độ nhạy của payload.
8. **Đóng stream** khi kết thúc vòng đời task, kiểm thử hay ứng dụng.

Sự lựa chọn giữa **bật theo tên** và **bật theo lớp** ảnh hưởng *đối tượng được chọn*; các ngưỡng, stack trace, period và retention ảnh hưởng *lượng dữ liệu được thu thập*.

## 11. Lỗi phổ biến và cách khắc phục

| Lỗi hoặc hiểu nhầm | Vấn đề | Cách làm đúng |
| --- | --- | --- |
| Chỉ gọi `onEvent(name, callback)` rồi chờ event | Callback không tự bật loại event đang bị tắt | Gọi `enable(name/class)` và start stream |
| Chỉ gọi `enable` rồi chờ console in event | Không có callback hoặc consumer được bắt đầu | Đăng ký `onEvent` và gọi `start/startAsync` |
| Cho `enable` trả `boolean` | API thực tế trả `EventSettings` | Dùng object để cấu hình thêm; test event bằng consumer |
| Cho `disable` đóng stream | Chỉ tắt một loại event | Dùng `close()` để kết thúc stream |
| Dùng `OrderChecked.class.getSimpleName()` để tìm event | Tên JFR có thể là `demo.OrderChecked` | Dùng `@Name`/`EventType.getName()` |
| Chọn tên khi tồn tại nhiều class loader dùng chung event name | Có thể ảnh hưởng nhiều event type | Chọn `Class` hoặc type ID |
| Truyền một class không phải `Event` qua raw reflection | Không hợp lệ về API, có thể gây exception | Giữ generic type `Class<? extends Event>` |
| Đổi config sau `startAsync` rồi mong callback dừng ngay | Event cũ có thể nằm trong buffer | Thiết kế ranh giới thời gian và test đúng tính async |
| Thấy `Event.isEnabled() == true` rồi suy ra riêng stream A bật | Recording khác có thể bật cùng event | Xem trạng thái ở đúng recording/consumer |
| Bật `jdk.CPULoad` rồi mong có event ngay lập tức | Event định kỳ phụ thuộc thời gian và runtime | Cấu hình period, cho thời gian tạo event, xử lý timeout |
| Quên `withoutThreshold` khi muốn thấy event cực ngắn | Event có thể không đạt ngưỡng | Chọn threshold phù hợp và test trên runtime thực |
| Dùng `setSettings` tưởng chỉ thêm một setting | Có thể thay thế cấu hình đã có | Xây map đầy đủ hoặc chỉ dùng `enable/disable` có mục tiêu |
| Không đóng stream trong worker/test | Rò rỉ tài nguyên, xử lý nền kéo dài | `try-with-resources` |
| Dùng event chứa mật khẩu/token để debug | Dữ liệu nhạy cảm có thể bị ghi vào JFR | Chỉ thu thập trường thật sự cần |

## 12. Quy trình áp dụng trong dự án

Khi cần thêm một loại event vào hệ thống quan sát JVM:

1. **Xác định nguồn sự kiện.** Là event JDK như `jdk.CPULoad` hay event tùy chỉnh kế thừa `jdk.jfr.Event`?
2. **Chọn định danh phù hợp.** Có lớp trong code thì dùng `EventClass.class`; chỉ có tên từ cấu hình thì dùng `String`. Kiểm tra khả năng trùng tên trong ứng dụng có plugin/class loader.
3. **Xác định vòng đời stream.** Dùng `try-with-resources` hoặc quản lý `close()` tại điểm dừng dịch vụ.
4. **Bật một cách có mục đích.** Gọi `enable(...)`; chỉ thêm threshold, period, stack trace nếu có yêu cầu và event hỗ trợ.
5. **Đăng ký callback đúng tên.** Đảm bảo `onEvent` khớp event định phát và thực hiện trước khi start.
6. **Bắt đầu nhận event.** Dùng `start()` khi muốn chặn thread hiện tại; `startAsync()` khi ứng dụng vẫn phải tiếp tục xử lý.
7. **Kiểm tra dữ liệu nhận được.** Với event tùy chỉnh, phát `Event.commit()` và dùng latch/timeout khi test; không dựa vào đoán thời điểm flush.
8. **Tắt khi không cần.** Dùng `disable(name/class)` đúng loại, chấp nhận sự kiện đã nằm trong buffer có thể còn được dispatch.
9. **Theo dõi chi phí.** Giới hạn retention và điều tiết callback; tắt nhóm event quá tốn kém.
10. **Kiểm tra quyền/trang bị JVM.** Nếu tạo `RecordingStream` thất bại vì không hỗ trợ JFR hoặc repository, báo lỗi môi trường rõ ràng thay vì coi là lỗi do `enable`.

### Bài tập tự kiểm tra

**1. Tên và lớp khác nhau thế nào khi bật event?** Theo tên có thể bật mọi event type có cùng name; theo lớp chỉ nhắm class event truyền vào.

**2. Gọi `stream.disable("demo.OrderChecked")` có gỡ callback `onEvent("demo.OrderChecked", ...)` không?** Không. Nó điều chỉnh việc ghi event, không hủy đăng ký action đã có.

**3. Vì sao `stream.enable(OrderChecked.class)` không thể gán vào `boolean`?** Vì API trả `EventSettings`, dùng để cấu hình bổ sung.

**4. Bật lại event sau khi đã `startAsync()` có tác dụng ngay tại từng callback không?** Không thể coi đó là ranh giới tuyệt đối tức thời; các event đã ghi/buffer và việc xử lý bất đồng bộ cần được xét.

**5. Sử dụng `EventType.getEventType(...).getName()` có lợi gì?** Lấy đúng tên event theo khai báo JFR, tránh đoán nhầm tên từ class hoặc package.

**6. Khi nào dùng `withoutThreshold()`?** Khi muốn event ngắn cũng có thể được ghi; nhớ rằng điều này có thể tăng lượng dữ liệu cần xử lý.

**7. Tại sao `event.isEnabled()` không luôn phản ánh riêng một `RecordingStream`?** Vì một JVM có thể có nhiều recording đang bật cùng loại event; trạng thái producer có thể bị ảnh hưởng bởi các recording đó.

## 13. Tài liệu chính thức hiện còn áp dụng

- [Oracle Java 25 API — RecordingStream](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): bốn overload `enable/disable`, cách ghi event, callback và vòng đời stream.
- [Oracle Java 17 API — RecordingStream](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): đối chiếu API dùng được với JDK 17.
- [Oracle Java 25 API — EventSettings](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): `withThreshold`, `withoutThreshold`, `withPeriod`, `withStackTrace` và `withoutStackTrace`.
- [Oracle Java 25 API — EventType](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/EventType.html): truy vấn tên và định danh loại event.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): nền tảng streaming JFR được bổ sung trong Java 14.

**Ghi nhớ:** `RecordingStream.enable(String/Class)` và `disable(String/Class)` là cách **bật hoặc tắt việc ghi một loại JFR event** trong stream theo **tên** hoặc **lớp**. Cả bốn trả `EventSettings`; còn việc xử lý event cần `onEvent` và `start/startAsync`. Chọn đúng phạm vi event, kiểm thử bất đồng bộ, giới hạn overhead và luôn đóng stream khi hoàn thành.
