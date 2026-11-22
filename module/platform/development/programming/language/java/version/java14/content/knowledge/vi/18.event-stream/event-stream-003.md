# Đọc sự kiện từ tệp ghi bằng `EventStream.openFile(Path)` trong Java Flight Recorder

## 1. Tổng quan và kết quả cần đạt

Java Flight Recorder (**JFR**) thu thập các **sự kiện có cấu trúc** do JVM và ứng dụng phát ra, rồi có thể lưu vào tệp ghi có phần mở rộng **`.jfr`**. Để xử lý sự kiện từ một **tệp đã ghi**, Java cung cấp API:

```java
jdk.jfr.consumer.EventStream.openFile(Path file)
```

Phương thức này trả về một **`EventStream`** — một luồng tiêu thụ sự kiện theo **mô hình đăng ký callback**. Ta đăng ký các hành động `onEvent(...)`, bắt đầu xử lý bằng `start()` hoặc `startAsync()`, rồi đóng stream để giải phóng tài nguyên.

Khác với `Stream<T>` của `java.util.stream`, **`EventStream` của JFR không phải Java Stream API** với `map/filter/collect` trực tiếp. Nó là một interface có các callback và vòng đời riêng, nhằm đọc các `RecordedEvent` từ nguồn JFR.

Trong bài này, người học sẽ:

1. Hiểu `openFile(Path)` dùng cho **tệp recording**, không phải kho sự kiện đang chạy.
2. Nắm luồng **`Recording` → tệp `.jfr` → `EventStream.openFile` → `onEvent` → `start`**.
3. Đọc trường có kiểu từ `RecordedEvent` theo tên sự kiện được đăng ký bằng `@Name`.
4. Sử dụng `onError`, `onClose`, `setReuse`, `setOrdered` và lọc theo khoảng thời gian khi cần.
5. Chọn giữa `EventStream.openFile`, `RecordingFile`, `openRepository` và `RecordingStream` theo mục tiêu.
6. Tránh các lỗi vòng đời, giữ tham chiếu đến event bị tái sử dụng, nhầm tên event và rủi ro khi mở file không đáng tin cậy.

**Tính tương thích hiện hành:** JFR Event Streaming được giới thiệu với **JDK 14 (JEP 349)**; `EventStream.openFile(Path)` vẫn được hỗ trợ trong **Java 17, 21, 25, 26** và các JDK hiện đại. Ví dụ chính sử dụng các API ổn định với **`javac --release 17`**; không cần bật preview, không dùng cơ chế legacy.

## 2. Điều kiện cần để `openFile` hoạt động

Tối thiểu cần:

- **Một JDK có module `jdk.jfr`** và runtime cho phép sử dụng Java Flight Recorder. Với JDK 17+ tiêu chuẩn, module này có sẵn.
- **Tệp `.jfr` hợp lệ** do JFR tạo từ một recording, ví dụ từ `Recording.dump(Path)` hoặc lệnh JDK `jcmd ... JFR.dump` trong quy trình vận hành được cấp quyền.
- **`Path` trỏ đúng tệp**, có thể đọc được, được cung cấp từ nguồn **đáng tin cậy**.
- **Loại sự kiện cần đọc đã được ghi vào tệp**: một callback có tên đúng nhưng không có sự kiện tương ứng sẽ không tự sinh dữ liệu.

Ví dụ với tệp đã tồn tại:

```java
import java.nio.file.Path;
import jdk.jfr.consumer.EventStream;

Path file = Path.of("capture.jfr");

try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("jdk.CPULoad", event -> {
        float machineTotal = event.getFloat("machineTotal");
        System.out.println("CPU ratio: " + machineTotal);
    });

    stream.start();
}
```

Đây là **trích đoạn cần đặt trong method có xử lý exception**, không phải một class độc lập. Nó chỉ in dòng khi `capture.jfr` có event `jdk.CPULoad` và field `machineTotal` có kiểu phù hợp. **Không có event không phải lỗi API.** Tên `jdk.CPULoad` là *event name*, không phải tên class của callback.

API `openFile` khai báo `throws IOException` khi không mở được file hoặc phát sinh lỗi I/O khi đọc; ngoài ra cần lưu ý quyền truy cập tệp của môi trường chạy. Một file rỗng hoặc chứa dữ liệu tùy ý **không được coi là file recording hợp lệ** chỉ vì có phần mở rộng `.jfr`.

### 2.1. Nguồn tệp `.jfr` đến từ đâu?

Trong code Java, một `Recording` có thể chủ động ghi kết quả:

```java
import jdk.jfr.Recording;
import java.nio.file.Path;

try (Recording recording = new Recording()) {
    recording.start();

    // Chạy workload cần ghi sự kiện.

    recording.stop();
    recording.dump(Path.of("capture.jfr"));
}
```

`Recording` quản lý **việc thu thập**; `EventStream.openFile` quản lý **việc đọc lại** file. Có thể thực hiện hai việc ở những tiến trình/máy khác nhau, miễn file được chuyển an toàn và runtime reader hỗ trợ cấu trúc dữ liệu cần đọc.

Bài demo ở mục 5 tự tạo tệp tạm, tự ghi custom events, đọc lại bằng `openFile` và xóa tệp khi kết thúc, nên chạy độc lập không cần một file upload có sẵn.

## 3. Quy trình cơ bản: `openFile`, đăng ký callback, `start`

Mẫu đọc đúng:

```java
try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("demo.OrderPlaced", event -> {
        String id = event.getString("orderId");
        long amount = event.getLong("amount");
        System.out.println(id + ": " + amount);
    });

    stream.onError(error -> {
        System.err.println("JFR error: " + error.getClass().getSimpleName());
    });

    stream.start();
}
```

Đây là **trích đoạn** với `file` kiểu `Path` và event type `demo.OrderPlaced` đã có trong file. Các bước theo đúng thứ tự:

1. **Mở stream:** `EventStream.openFile(file)` — mặc định bắt đầu đọc từ **event đầu tiên trong file**.
2. **Đăng ký callback:** `onEvent("demo.OrderPlaced", ...)` — chỉ nhận event có **tên phù hợp**, không phải mọi event của JVM.
3. **Đăng ký xử lý lỗi:** `onError(...)`, để kiểm soát phản hồi khi callback/stream gặp lỗi trong quá trình dispatch.
4. **Bắt đầu xử lý:** `start()` — dispatch sự kiện **trên thread đang gọi**; với tệp hữu hạn, xử lý kết thúc khi đọc xong file hoặc stream được đóng.
5. **Giải phóng:** `try-with-resources` gọi `close()` ngay cả khi có exception; stream từ file cũng tự đóng khi kết thúc xử lý.

**Lưu ý:** chỉ gọi `openFile` và `onEvent` không làm sự kiện tự được xử lý. **Phải gọi `start()` hoặc `startAsync()`**. Đồng thời hãy đăng ký callback và thiết lập cấu hình **trước khi bắt đầu** để tránh bỏ lỡ các event đầu tiên.

### 3.1. Hai dạng `onEvent`

| API | Nhận sự kiện nào? | Khi nào phù hợp? |
| --- | --- | --- |
| `onEvent(Consumer<RecordedEvent>)` | Tất cả các loại event được stream dispatch | Công cụ khám phá tổng quát hoặc xử lý nhiều loại |
| `onEvent(String eventName, Consumer<RecordedEvent>)` | Chỉ loại event có tên `eventName` | Chỉ cần một vài loại, tránh xử lý không liên quan |

Với tệp JFR nhiều loại sự kiện, **ưu tiên callback có event name** khi bạn chỉ quan tâm một loại; tài liệu API ghi nhận cách này có thể hiệu quả hơn lọc bằng `if` bên trong callback tổng quát.

Nếu chưa chắc tên sự kiện, dùng metadata của file hoặc `EventType.getName()`, không suy đoán từ label hiển thị của công cụ. Một `@Name("demo.OrderPlaced")` có tên `demo.OrderPlaced`; `getLabel()` hay tên class Java không nhất thiết giống.

## 4. Đọc `RecordedEvent` và các trường có kiểu

Callback nhận một object **`jdk.jfr.consumer.RecordedEvent`**. Những API quan trọng:

| API | Tác dụng |
| --- | --- |
| `event.getEventType().getName()` | Tên loại sự kiện, ví dụ `demo.OrderPlaced` |
| `event.getString("orderId")` | Đọc trường `orderId` kiểu `String` |
| `event.getLong("amount")` | Đọc trường số `amount` với kiểu hỗ trợ |
| `event.getInt("count")` | Đọc trường số nguyên phù hợp |
| `event.getStartTime()` | Thời điểm bắt đầu event (`Instant`) |
| `event.getEndTime()` | Thời điểm kết thúc event (`Instant`) |
| `event.getDuration()` | Thời lượng (`Duration`) |
| `event.getStackTrace()` | Stack trace của event, có thể `null` |
| `event.hasField("name")` | Kiểm tra có field tên `name` trước khi đọc |
| `event.getFields()` | Metadata các trường có trong event |

Ví dụ trong một callback:

```java
stream.onEvent("demo.OrderPlaced", event -> {
    String id = event.getString("orderId");
    long amount = event.getLong("amount");

    System.out.println("Order " + id + ", amount=" + amount);
});
```

**Phải khớp schema:** `getString("orderId")` chỉ phù hợp nếu sự kiện có field `orderId` kiểu chuỗi. Nếu field không tồn tại hoặc có kiểu không tương thích, có thể phát sinh exception khi đọc. Với các built-in events, danh sách fields có thể thay đổi giữa phiên bản JDK; nên kiểm tra bằng `hasField`/metadata khi làm công cụ phân tích đa phiên bản.

Một event **có thể không có stack trace** nếu cấu hình recording đã tắt tính năng này hoặc không có dữ liệu tương ứng. Hãy kiểm tra `event.getStackTrace() != null` trước khi gọi `getFrames()`.

## 5. Chương trình Java 17+ độc lập: tạo file rồi dùng `openFile` đọc lại

Chương trình sau tạo hai loại custom events:

- `demo.OrderPlaced`: có `orderId` và `amount`.
- `demo.StockWarning`: có `sku`.

Nó ghi **3 đơn hàng + 1 cảnh báo** vào một tệp `.jfr`, sau đó dùng **`EventStream.openFile(Path)`** để nhận các sự kiện theo tên, lưu lại `RecordedEvent` an toàn với `setReuse(false)`, thống kê kết quả rồi dọn tệp tạm.

Lưu nguyên mã thành **`JfrOpenFileDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.EventStream;
import jdk.jfr.consumer.RecordedEvent;

public class JfrOpenFileDemo {
    @Name("demo.OrderPlaced")
    static class OrderPlaced extends Event {
        String orderId;
        long amount;
    }

    @Name("demo.StockWarning")
    static class StockWarning extends Event {
        String sku;
    }

    static void emit(String id, long amount) {
        OrderPlaced event = new OrderPlaced();
        event.orderId = id;
        event.amount = amount;
        event.commit();
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("jfr-open-file-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(OrderPlaced.class)
                         .withThreshold(Duration.ZERO);
                recording.enable(StockWarning.class)
                         .withThreshold(Duration.ZERO);

                recording.start();

                emit("O-101", 120);
                emit("O-102", 250);
                emit("O-103", 80);

                StockWarning warning = new StockWarning();
                warning.sku = "SKU-7";
                warning.commit();

                recording.stop();
                recording.dump(file);
            }

            List<RecordedEvent> orders = new ArrayList<>();
            List<RecordedEvent> warnings = new ArrayList<>();
            List<Throwable> errors = new ArrayList<>();
            AtomicBoolean closed = new AtomicBoolean(false);

            try (EventStream stream = EventStream.openFile(file)) {
                stream.setReuse(false);

                stream.onEvent("demo.OrderPlaced", orders::add);
                stream.onEvent("demo.StockWarning", warnings::add);
                stream.onError(errors::add);
                stream.onClose(() -> closed.set(true));

                stream.start(); // Đồng bộ: đọc file và gọi callback.
            }

            if (!errors.isEmpty()) {
                throw new IllegalStateException(
                        "JFR parse error", errors.get(0));
            }

            List<String> ids = orders.stream()
                    .map(e -> e.getString("orderId"))
                    .sorted()
                    .toList();

            long total = orders.stream()
                    .mapToLong(e -> e.getLong("amount"))
                    .sum();

            System.out.println("fileRecorded=" + (Files.size(file) > 0));
            System.out.println("orders=" + orders.size());
            System.out.println("ids=" + ids);
            System.out.println("total=" + total);
            System.out.println("warnings=" + warnings.size());
            System.out.println("warningSku=" +
                    warnings.get(0).getString("sku"));
            System.out.println("closed=" + closed.get());
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

### 5.1. Biên dịch và chạy

JDK 17+ có module JFR:

```bash
javac --release 17 JfrOpenFileDemo.java
java JfrOpenFileDemo
```

**Kết quả chuẩn đã được kiểm chứng:**

```text
fileRecorded=true
orders=3
ids=[O-101, O-102, O-103]
total=450
warnings=1
warningSku=SKU-7
closed=true
```

### 5.2. Giải thích từng kết quả

1. **`fileRecorded=true`:** `Recording.dump(file)` tạo ra tệp JFR có nội dung; phép `Files.size(file) > 0` trả `true`. Đây không phải kiểm tra chi tiết format, nhưng sau đó `openFile` đọc thành công và xác thực được sự kiện mong đợi.
2. **`orders=3`:** callback `onEvent("demo.OrderPlaced", ...)` nhận đúng ba event của loại này; cảnh báo `StockWarning` không bị tính nhầm vào danh sách orders.
3. **`ids=[O-101, O-102, O-103]`:** các trường `orderId` được đọc **sau khi `start()` hoàn tất**, an toàn vì đã gọi `setReuse(false)`. Danh sách được `sorted()` để không phụ thuộc vào việc hiển thị thứ tự giữa các batch JFR.
4. **`total=450`:** ba field `amount` lần lượt là 120, 250, 80; `getLong("amount")` cho giá trị số để tổng hợp.
5. **`warnings=1`:** callback thứ hai chỉ nhận một `demo.StockWarning` đã được `commit()`.
6. **`warningSku=SKU-7`:** trường `sku` của event cảnh báo được đọc bằng `getString("sku")`.
7. **`closed=true`:** `onClose(...)` đã chạy khi stream kết thúc; `try-with-resources` cũng bảo đảm giải phóng tài nguyên.

**Về tính tái lập:** dữ liệu event demo cố định, không dựa vào số lượng các sự kiện nội bộ khác của JVM. Kích thước tệp, timestamp và số event JDK thu thêm có thể khác theo runtime, nhưng callback chỉ chọn **hai loại event ứng dụng** và in số liệu của chúng. Chương trình đã được biên dịch/chạy trực tiếp bằng `javac --release 17` để xác minh 7 dòng stdout trên.

### 5.3. Vì sao ví dụ dùng `withThreshold(Duration.ZERO)`?

Custom JFR event có thể mang duration và loại sự kiện có threshold setting. `withThreshold(Duration.ZERO)` đảm bảo ví dụ không bỏ các **instant events** vì ngưỡng thời lượng lớn hơn 0. Việc loại sự kiện có thực sự được ghi vẫn phụ thuộc cấu hình enabled, vòng đời `Recording` và `commit()`. Trong demo, cả hai event types được enable tường minh.

### 5.4. Vì sao `finally` xóa file chỉ ở demo?

Vì tệp được tạo bởi `Files.createTempFile` **cho riêng chương trình thử nghiệm**, nên `finally` có thể xóa sau khi kiểm chứng. Với tệp `.jfr` lấy từ sự cố production hoặc phục vụ audit, **không được tự xóa** sau khi phân tích nếu hợp đồng lưu trữ không cho phép. Dọn file luôn dựa vào quyền sở hữu dữ liệu.

## 6. Quy tắc rất quan trọng: `RecordedEvent` có thể được tái sử dụng

Tài liệu `EventStream` mô tả rằng **mặc định cùng một object `RecordedEvent` có thể được tái sử dụng** để biểu diễn nhiều sự kiện khác nhau và được đưa qua các callback khác nhau.

Ví dụ **dễ sai**:

```java
List<RecordedEvent> captured = new ArrayList<>();

try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("demo.OrderPlaced", captured::add);
    stream.start();
}

// Không an toàn nếu giả định mỗi captured[i] là object độc lập
// khi chưa cấu hình setReuse(false).
```

Đoạn trên là **trích đoạn** cần có imports và biến `file` phù hợp. Vì các object có thể bị tái sử dụng, nhiều phần tử trong danh sách có nguy cơ trỏ tới cùng instance được thay đổi để biểu diễn event khác. Kết quả có thể gây sai dữ liệu khi tổng hợp sau callback.

**Cách sửa 1 — tắt reuse trước khi start:**

```java
stream.setReuse(false);
stream.onEvent("demo.OrderPlaced", captured::add);
stream.start();
```

`setReuse(false)` khiến stream không tái sử dụng `RecordedEvent` theo cách gây hỏng dữ liệu khi giữ reference ngoài callback. Đây là cách chương trình hoàn chỉnh đã dùng.

**Cách sửa 2 — không giữ `RecordedEvent`, chỉ trích xuất dữ liệu ngay trong callback:**

```java
AtomicLong amountTotal = new AtomicLong();

stream.onEvent("demo.OrderPlaced", event ->
        amountTotal.addAndGet(event.getLong("amount")));
stream.start();

System.out.println(amountTotal.get());
```

Dùng `AtomicLong` ở đây minh họa biến thống kê có thể sử dụng qua lambda; nếu xử lý **đồng bộ**, callback chạy trên thread gọi `start()`, nên cấu trúc đơn giản khác cũng có thể dùng. Khi chỉ trích xuất giá trị primitive/String trong callback, có thể không cần tắt reuse và không cần lưu từng event, giúp tiết kiệm bộ nhớ cho file lớn.

**Quy tắc:** nếu object `RecordedEvent` được sử dụng **sau khi callback hoàn tất**, hãy bảo đảm không có reuse. Nếu xử lý **ngay trong callback** và chỉ lưu giá trị đã trích xuất, tránh giữ reference đến `RecordedEvent`.

## 7. `start()`, `startAsync()` và vòng đời stream từ file

### 7.1. `start()` đồng bộ — lựa chọn đơn giản nhất khi đọc file

```java
try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("demo.OrderPlaced", event -> {
        // Xử lý ở thread gọi start().
    });
    stream.start();

    // Ở đây, callback đã được dispatch cho đến khi stream kết thúc.
}
```

`start()` thực hiện các actions trên **thread hiện tại**, tránh phải tự đồng bộ hoặc chờ worker khác. Với file JFR hữu hạn, đây là cách rõ ràng cho các công việc phân tích offline hoặc xử lý theo batch. Sau khi đọc hết nguồn, stream kết thúc và tự đóng.

### 7.2. `startAsync()` dành cho xử lý không chặn thread gọi

```java
try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("demo.OrderPlaced", event -> {
        System.out.println(event.getString("orderId"));
    });

    stream.startAsync();
    stream.awaitTermination();
}
```

`startAsync()` gọi callback trên một thread khác. **Không được** mở `try`, gọi `startAsync()` rồi lập tức thoát `try` nếu muốn đọc toàn bộ file: `close()` có thể làm luồng dừng trước khi các callback xử lý xong.

`awaitTermination()` giúp chờ tới khi các actions hoàn tất hoặc stream đóng (hoặc thread chờ bị gián đoạn). Có overload `awaitTermination(Duration timeout)`, nhưng timeout là giới hạn **chờ**, không có nghĩa rằng mọi event đã xử lý xong; cần kiểm tra thiết kế khi timeout thực sự xảy ra.

Trong ứng dụng có async processing:

- Các collections/chỉ số dùng chung với thread callback cần bảo đảm **thread safety** và có quy tắc đọc sau khi callback kết thúc.
- `close()` không bảo đảm tất cả callback hoàn thành trước khi method trả về nếu stream đang xử lý bất đồng bộ.
- `onError` và `onClose` cũng nên được thiết kế không gây blocking lâu, tránh chi phí và deadlock không cần thiết.

### 7.3. `onClose`

```java
stream.onClose(() -> System.out.println("JFR stream closed"));
```

Đăng ký hành động khi stream đóng vì đọc xong file, bị dừng hoặc do ngoại lệ. Callback này giúp **dọn state/ghi log**, nhưng không có nghĩa dữ liệu nghiệp vụ đã được commit vào một hệ thống khác. Với stream đã đóng, tài liệu cho biết action đăng ký `onClose` sau đó có thể chạy ngay trong thread gọi.

## 8. `onError` và ngoại lệ: không bỏ qua lỗi âm thầm

Một sai lầm trong xử lý file là dùng callback mà không nhìn thấy lỗi của quá trình dispatch:

```java
try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("demo.OrderPlaced", event -> {
        String id = event.getString("orderId");
        // Xử lý id...
    });
    stream.start();
}
```

Nếu callback ném exception mà không có `onError`, `EventStream` mặc định in exception và stack trace ra **stderr** theo hợp đồng API. Đối với một job xử lý tự động, chỉ in stderr có thể chưa đủ để đánh dấu job thất bại.

Ví dụ chương trình hoàn chỉnh đăng ký:

```java
List<Throwable> errors = new ArrayList<>();

stream.onError(errors::add);
stream.start();

if (!errors.isEmpty()) {
    throw new IllegalStateException("JFR parse error", errors.get(0));
}
```

Vì demo dùng `start()` đồng bộ, việc kiểm tra `errors` sau khi start hoàn tất là trực tiếp. Với `startAsync()`, cần bảo đảm cách lưu/chuyển thông tin exception **an toàn đa luồng**, và chờ kết thúc trước khi quyết định trạng thái công việc.

**Lưu ý quan trọng:**

- `openFile(file)` có thể ném `IOException` **ngay khi mở**; lỗi ở bước này cần xử lý bằng `try/catch` của caller, **không mong `onError` xử lý một stream chưa tạo được**.
- Lỗi phát sinh trong quá trình dispatch/callback có thể được chuyển đến `onError`.
- Nếu `onError` tự ném exception, tài liệu API nói hành vi kết quả **không được xác định**; vì vậy handler lỗi nên đơn giản, chắc chắn và tránh lại gây lỗi.
- Không trả thẳng stack trace hoặc nội dung JFR nhạy cảm cho người dùng không có quyền.

### 8.1. Phân biệt lỗi và “không tìm thấy event”

Nếu callback `onEvent("demo.OrderPlaced", ...)` không chạy lần nào, có thể do:
- File hoàn toàn **không chứa** loại event `demo.OrderPlaced`.
- Gõ sai **event name**.
- Event không được enable/commit trong giai đoạn ghi.
- Bộ lọc thời gian khiến event không thuộc khoảng được đọc.
- Recording/file không đúng nguồn dự kiến.

Không nên gọi việc nhận **0 event** là lỗi I/O nếu không có bằng chứng khác. Kiểm tra tên event từ file và bước recording trước.

## 9. Chọn chế độ đọc và lọc đúng nhu cầu

### 9.1. Mặc định đọc từ event đầu tiên

`EventStream.openFile(file)` mặc định **bắt đầu ở event đầu tiên trong file**. Điều này khác với `EventStream.openRepository()`, vốn mặc định bắt đầu từ **event tiếp theo được flush** trong repository đang được theo dõi.

Muốn chỉ đọc một khoảng thời gian lịch sử, thiết lập trước khi start:

```java
try (EventStream stream = EventStream.openFile(file)) {
    stream.setStartTime(startInstant);
    stream.setEndTime(endInstant);

    stream.onEvent("demo.OrderPlaced", event -> {
        // Chỉ xử lý trong khoảng thời gian yêu cầu.
    });

    stream.start();
}
```

Đây là **trích đoạn** với `startInstant`/`endInstant` kiểu `java.time.Instant` đã được xác định. API sẽ giới hạn khoảng thời gian của stream. Cần đặt `setStartTime` và `setEndTime` **trước `start()`**; gọi sau khi stream đã bắt đầu là sai theo quy tắc của API.

Để chọn khoảng thời gian chính xác, ưu tiên timestamp tương ứng với dữ liệu JFR (và múi giờ khi trình bày) hơn việc suy đoán thời gian tệp được tạo. Một file có thể chứa nhiều chunks và event từ thời điểm khác nhau.

### 9.2. `setOrdered(boolean)` và giới hạn thứ tự

`EventStream` hỗ trợ:

```java
stream.setOrdered(true);  // Muốn sắp sự kiện theo thời gian.
stream.setOrdered(false); // Không yêu cầu sắp, có thể giảm chi phí.
```

Theo tài liệu API, các event được dispatch theo **batches**, trong cùng batch được sắp theo **thời gian kết thúc** khi ordering được bật. **Không bảo đảm một thứ tự thời gian tuyệt đối giữa mọi batch**, vì một event trong batch sau vẫn có thể có end time trước một event đã dispatch ở batch trước.

Vì vậy:

- Nếu yêu cầu hiển thị tổng hợp có thứ tự quyết định, thu thập **các giá trị cần thiết** rồi sắp xếp ở bước tổng hợp khi phù hợp.
- Không suy ra một giao dịch nghiệp vụ “xảy ra trước” chỉ vì callback nhận trước, đặc biệt nếu có nhiều thread, chunks, clock hoặc event duration khác nhau.
- Trong demo, `ids.sorted()` được dùng để đảm bảo output ổn định, không dựa vào thứ tự dispatch ngẫu nhiên của các event nằm trong file.

### 9.3. `onFlush(Runnable)` và `onMetadata(Consumer)`

`onFlush(...)` đăng ký action khi **một batch sự kiện** được flush. Có thể dùng để đẩy phần thống kê đã tổng hợp ra hệ thống khác theo từng batch. **Đừng** nhầm callback flush với dấu hiệu tất cả file đã xử lý xong; một file có thể có nhiều batch.

`onMetadata(...)` (có từ Java 16, vẫn hỗ trợ trong Java 17+) giúp nhận metadata các loại event mới xuất hiện. Hữu ích khi bạn không biết trước toàn bộ event names hoặc muốn động đăng ký `onEvent` theo `EventType.getName()` và pattern. Không cần dùng metadata callback cho demo đơn giản với hai event names đã biết.

Ví dụ minh họa:

```java
stream.onMetadata(meta -> {
    meta.getAddedEventTypes().stream()
            .map(jdk.jfr.EventType::getName)
            .filter(name -> name.startsWith("demo."))
            .forEach(name ->
                    stream.onEvent(name, event -> {
                        // Xử lý event ứng dụng.
                    }));
});
```

Đây là **đoạn mẫu trong phạm vi biến `stream`**, cần chạy với JDK 17+, và chỉ dùng khi thực sự cần khám phá event types. Theo tài liệu, đăng ký `onMetadata` trước khi start; khi metadata của event type đến, JFR bảo đảm type được báo trước actual event. Việc đăng ký tên động giúp tránh đọc/dispatch cả những loại không quan tâm.

## 10. So sánh `openFile` với các API JFR khác

| API | Nguồn | Mô hình xử lý | Lựa chọn phù hợp |
| --- | --- | --- | --- |
| `EventStream.openFile(Path)` | **Tệp `.jfr` đã ghi** | Đăng ký callback và `start`/`startAsync` | Phân tích file theo event types, xử lý có điều kiện hoặc aggregate streaming |
| `RecordingFile` / `readAllEvents` | Tệp `.jfr` | Đọc từng event hoặc tạo list tất cả | Phân tích offline đơn giản, cần truy cập ngẫu nhiên/tổng thể dữ liệu nhỏ |
| `EventStream.openRepository()` | Kho JFR trên đĩa của JVM hiện tại | Theo dõi sự kiện được flush, thường từ event kế tiếp | Đọc dòng sự kiện từ repository, không phải snapshot file cố định |
| `RecordingStream` | Một recording do ứng dụng tạo và theo dõi | Cấu hình recording + tiêu thụ event liên tục | Quan sát tiến trình Java đang chạy với cơ chế streaming |
| `jfr print` (JDK command-line tool) | Tệp `.jfr` | In dữ liệu ra terminal/file | Khám phá tệp nhanh, không cần viết code |

Nếu muốn đọc file và **chỉ đếm hoặc tổng hợp một vài loại sự kiện**, `EventStream.openFile` thường thuận tiện vì callback cho phép xử lý ngay mà không cần giữ toàn bộ events trong bộ nhớ.

Nếu muốn load tất cả event của **một file nhỏ** thành list để dùng Java Stream API, có thể:

```java
List<RecordedEvent> events =
        RecordingFile.readAllEvents(file);
```

Đây là **trích đoạn** cần import `jdk.jfr.consumer.RecordingFile`, `RecordedEvent`, `List` và có `Path file`. `readAllEvents` lưu các event vào bộ nhớ, nên cân nhắc đối với file rất lớn. Nếu chỉ cần duyệt lần lượt mà không muốn callback, có thể dùng `RecordingFile` với `hasMoreEvents()`/`readEvent()`.

**Không nhầm:** `EventStream.openFile` đọc **một file nguồn**; nó không phải cách mặc định để tail/đăng ký sự kiện mới liên tục từ JVM. Để stream hiện tại, xem `RecordingStream` hoặc `openRepository` theo hoàn cảnh.

## 11. Hiệu năng, an toàn và xử lý tệp lớn

### 11.1. Tránh giữ mọi event trong RAM

Bài demo lưu vài `RecordedEvent` để giải thích `setReuse(false)`. Trong ứng dụng đọc hàng triệu sự kiện, nên chọn:

```java
LongAdder total = new LongAdder();

try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("demo.OrderPlaced", event ->
            total.add(event.getLong("amount")));

    stream.start();
}

System.out.println(total.sum());
```

Đây là **trích đoạn cần import `java.util.concurrent.atomic.LongAdder`**. Kỹ thuật này chỉ lưu tổng đã tính, không giữ mọi event. Nếu dùng cấu trúc có thể thay đổi trong `startAsync()`, cần lập kế hoạch đồng bộ và chờ kết thúc trước khi dùng kết quả.

### 11.2. Callback nên ngắn và dự đoán được

Các callback thực thi trong vòng đời dispatch của EventStream. Xử lý quá nặng, I/O chậm hoặc lock kéo dài có thể làm thời gian đọc file tăng và cản trở tiến độ dispatch.

Trong thực tế có thể:
- Chỉ lọc/đếm/tổng hợp gọn ngay callback.
- Chuyển dữ liệu đã được trích xuất sang worker/queue **có giới hạn dung lượng** nếu cần xử lý nặng.
- Có cơ chế báo lỗi hoặc hủy khi downstream lỗi; không làm mất lỗi trong `onError`.

### 11.3. Chỉ mở file JFR đáng tin

Javadoc `openFile(Path)` nêu rõ **chỉ mở recording files từ nguồn đáng tin cậy**. File `.jfr` là dữ liệu nhị phân có cấu trúc; không tải file bất kỳ từ người lạ rồi đưa vào hệ thống phân tích nhạy cảm một cách vô điều kiện.

Nếu cần xử lý file do người dùng cung cấp, dùng quy trình kiểm soát nguồn, giới hạn dung lượng, tài nguyên tính toán, thời gian xử lý và quyền file phù hợp. Không dựa vào phần mở rộng `.jfr` để xác định file an toàn.

JFR có thể chứa tên class/method, đường dẫn, stack trace, thông tin thread và trường custom do ứng dụng ghi. Hãy bảo vệ quyền truy cập các file, tránh vô tình ghi dữ liệu bí mật vào JFR events hoặc log khi đọc.

## 12. Lỗi thường gặp

### Lỗi A — Quên `start()`

```java
try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("demo.OrderPlaced", event -> System.out.println(event));
    // Quên stream.start();
}
```

Không có callback được dispatch vì stream chưa được bắt đầu. Phải gọi `start()` hoặc `startAsync()`.

### Lỗi B — Gọi `startAsync()` rồi thoát `try` ngay

```java
try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("demo.OrderPlaced", event -> doWork(event));
    stream.startAsync();
} // Đóng stream, có thể chưa kịp đọc hết.
```

`doWork` là tên phương thức giả định. Sửa bằng `stream.awaitTermination()` hoặc thiết kế vòng đời async rõ ràng trước khi đóng. Nếu có timeout, cần có cơ chế nhận biết chưa hoàn tất.

### Lỗi C — Đăng ký event name sai

`onEvent("OrderPlaced", ...)` không tương đương `onEvent("demo.OrderPlaced", ...)` khi `@Name` khai báo tên thứ hai. Sử dụng tên `EventType.getName()` thực có trong file.

### Lỗi D — Lưu `RecordedEvent` rồi quên `setReuse(false)`

Một object có thể được tái sử dụng cho nhiều event; danh sách object lưu lại có thể không phản ánh dữ liệu từng event như kỳ vọng. Sửa bằng `stream.setReuse(false)` trước `start`, hoặc trích xuất immutable/primitive values ngay callback.

### Lỗi E — Nhầm `EventStream` với `Stream<RecordedEvent>`

Không thể gọi thẳng `EventStream.openFile(file).filter(...)` vì đây không phải `java.util.stream.Stream`. Dùng `onEvent` để xử lý theo callback, hoặc dùng `RecordingFile.readAllEvents(file).stream()` nếu muốn Java Stream API và file đủ nhỏ.

### Lỗi F — Giữ toàn bộ file trong RAM khi chỉ cần tổng

Không nên mặc định dùng `readAllEvents` hay đưa mọi `RecordedEvent` vào list với file lớn. Dùng callback để tích lũy thống kê, sau đó chỉ lưu kết quả cần thiết.

### Lỗi G — Tưởng tất cả loại event trong JVM đều nằm trong tệp

Một loại event chỉ được ghi nếu recording đã enable, có event phát sinh và vượt qua các settings như threshold. `openFile` **không tạo ra dữ liệu** khi file thiếu event cần quan sát.

### Lỗi H — Bỏ qua `onError` hoặc làm handler ném lỗi tiếp

Không có `onError`, lỗi callback có thể chỉ được in ra stderr. Handler lỗi cần đơn giản, có cơ chế chuyển trạng thái job thất bại, tránh ném exception mới trong chính handler khi API không bảo đảm hành vi đó.

### Lỗi I — Coi `setOrdered(true)` là bảo đảm thứ tự thời gian tuyệt đối của mọi event

Theo Javadoc, ordering được bảo đảm trong từng batch, không nhất thiết bảo đảm toàn cục giữa các batches. Nếu kết quả cần thứ tự quyết định, sắp xếp phần dữ liệu đã trích xuất theo tiêu chí phù hợp.

### Lỗi J — Mở nhầm hoặc file chưa ghi xong

Một file chưa tồn tại, bị cắt, không hợp lệ hoặc bị ứng dụng khác thay đổi khi đọc có thể gây I/O/format error. Xác nhận file thuộc recording đã hoàn tất, có quyền đọc; với ứng dụng nhiều tiến trình, dùng cách bàn giao file an toàn thay vì đọc file chưa được xuất xong.

### Lỗi K — Xóa file production vì sao chép cleanup demo

`Files.deleteIfExists(file)` trong chương trình độc lập chỉ xóa **tệp tạm do demo tự tạo**. Khi đọc file chẩn đoán do người khác quản lý, chỉ xóa/di chuyển khi được ủy quyền và đã hoàn tất yêu cầu lưu trữ.

## 13. Bài tập tự kiểm tra

**Câu 1.** `openFile(Path)` khác `openRepository()` thế nào về điểm bắt đầu mặc định?

**Đáp án:** `openFile` mặc định bắt đầu từ **event đầu tiên trong tệp**, còn `openRepository` mặc định theo dõi các event được flush **tiếp theo** trong repository.

**Câu 2.** `onEvent("demo.OrderPlaced", ...)` có được gọi cho event tên `demo.StockWarning` không?

**Đáp án:** Không. Callback có tên chỉ nhận sự kiện khớp **event name**. Để nhận cả hai, đăng ký hai callback hoặc dùng `onEvent(Consumer)` tổng quát.

**Câu 3.** Vì sao `stream.setReuse(false)` quan trọng khi lưu `RecordedEvent` vào list?

**Đáp án:** Vì mặc định object có thể được tái sử dụng, không an toàn để giữ reference sau callback. Tắt reuse giúp giữ được từng event độc lập để xử lý sau.

**Câu 4.** `start()` và `startAsync()` khác nhau ở đâu?

**Đáp án:** `start()` xử lý callback trong thread gọi, còn `startAsync()` xử lý trong thread riêng. Với async, thường cần `awaitTermination()` trước khi kết luận đã đọc xong tệp và đóng stream.

**Câu 5.** Nếu muốn chỉ đọc event trong một khoảng thời gian, đặt settings ở đâu?

**Đáp án:** Gọi `setStartTime(Instant)` và `setEndTime(Instant)` **trước `start()`**, sau đó đăng ký callback và bắt đầu đọc.

**Câu 6.** Trong demo, vì sao `orders.size() == 3` nhưng tổng số event trong file có thể lớn hơn 4?

**Đáp án:** Demo còn có thể ghi built-in JFR events của JVM. Callback `demo.OrderPlaced` chỉ nhận sự kiện tên đó, nên không phụ thuộc tổng số loại event không liên quan.

**Câu 7.** Nếu `event.getString("orderId")` báo field không tồn tại, nên làm gì?

**Đáp án:** Kiểm tra `event.getEventType().getName()` và metadata `event.hasField("orderId")`, đối chiếu schema của event thực. Không suy đoán tên field theo class Java không được ghi vào file.

**Câu 8.** Vì sao phải có `try-with-resources` khi `openFile`?

**Đáp án:** `EventStream` là `AutoCloseable`; đóng stream giải phóng tài nguyên xử lý. Đọc đến cuối file thường tự đóng, nhưng `try` vẫn an toàn trong trường hợp exception hoặc dừng sớm.

**Câu 9.** Vì sao callback nên tổng hợp primitive values thay vì lưu mọi `RecordedEvent` với file rất lớn?

**Đáp án:** Giảm bộ nhớ tiêu thụ, tránh phải tắt reuse/giữ hàng triệu object; dễ đặt giới hạn và xử lý kết quả. Khi thật sự cần phân tích chi tiết tất cả event, cân nhắc chiến lược lưu trữ/streaming phù hợp.

## 14. Checklist khi dùng `openFile` trong ứng dụng thật

- [ ] Xác nhận file JFR hợp lệ và đến từ **nguồn đáng tin cậy**; có chính sách quyền và dung lượng.
- [ ] Chọn `EventStream.openFile` khi muốn đọc **tệp đã ghi**, không lẫn với `openRepository` hoặc `RecordingStream` cho dữ liệu đang được tạo.
- [ ] Mở bằng `try (EventStream stream = EventStream.openFile(file))` để quản lý tài nguyên.
- [ ] Đăng ký callback `onEvent(...)` và `onError(...)` **trước khi `start`**.
- [ ] Nếu biết tên event, dùng `onEvent("event.name", callback)`; lấy tên thực từ `@Name`/`EventType.getName()`.
- [ ] Dùng `RecordedEvent.getString/getLong/getDuration/...` phù hợp schema; xác minh field của các event khác phiên bản.
- [ ] Nếu giữ `RecordedEvent` qua callback, đặt `setReuse(false)`; nếu chỉ tổng hợp, ưu tiên trích xuất primitive/immutable values ngay trong callback.
- [ ] Dùng `start()` cho file xử lý đồng bộ; với `startAsync()`, cần chờ hoàn tất và thiết kế thread safety trước khi đóng.
- [ ] Khi cần giới hạn thời gian, cấu hình `setStartTime`/`setEndTime` trước khi start.
- [ ] Không mặc định ordering là tuyệt đối giữa mọi batches; sắp xếp dữ liệu đầu ra nếu thứ tự có ý nghĩa nghiệp vụ.
- [ ] Kiểm tra lỗi trong `onError` và cả exception khi `openFile`; không bỏ qua lỗi chỉ vì callback đã được đăng ký.
- [ ] Không mặc định file chứa mọi loại event; phải xét cấu hình recording và event thực sự đã được commit.
- [ ] Đóng stream, xử lý file theo quyền sở hữu, không xóa tệp của người khác nếu chưa được phép.
- [ ] Với file lớn, dùng xử lý incremental thay vì mặc định giữ toàn bộ sự kiện trong RAM.

## 15. Tài liệu API chính thức còn áp dụng

1. [Oracle Java SE 26 — EventStream](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): `openFile`, `onEvent`, `start/startAsync`, `awaitTermination`, `setReuse`, `setOrdered`, `onError` và bảo mật tệp JFR.
2. [Oracle Java SE 17 — EventStream](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): tương thích Java 17, `onMetadata` từ Java 16 và hành vi callback/stream.
3. [Oracle Java SE 17 — Recording](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html): thu thập sự kiện, `enable`, `start/stop` và `dump(Path)`.
4. [Oracle Java SE 17 — RecordedEvent](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): `getEventType`, `getDuration`, `getStartTime`, `getEndTime` và stack trace.
5. [Oracle Java SE 17 — RecordingFile](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): phương án đọc từng event hoặc `readAllEvents` từ file JFR.
6. [Oracle Java SE 17 — RecordedObject](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): `getString`, `getLong`, `hasField` và cách đọc field theo kiểu.
7. [OpenJDK — JEP 349: JFR Event Streaming](https://openjdk.org/jeps/349): bổ sung khả năng phát sự kiện JFR qua streaming API từ JDK 14.
